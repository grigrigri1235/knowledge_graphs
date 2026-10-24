"""LTLf (linear temporal logic over finite traces) with Kleene three-valued semantics.

Syntax: the operator keywords of the paper's rule-extraction prompt (App. H): NOT, AND, OR, IMPLIES, ALWAYS,
EVENTUALLY, NEXT, UNTIL, plus TRUE / FALSE and parentheses. Predicates are snake_case identifiers.

Precedence, loosest first: IMPLIES (right-associative) < OR < AND < UNTIL (right-associative)
< unary NOT / ALWAYS / EVENTUALLY / NEXT. App. C.3 (Eq. 7) defines the semantics over finite traces:
  ALWAYS φ      φ holds at every position from the current one to the end
  EVENTUALLY φ  φ holds at some position from the current one to the end
  NEXT φ        strong next: there is a next position and φ holds there (false at the last position)
  φ1 UNTIL φ2   φ2 holds at some position j ≥ current, and φ1 holds at every position before j
A trace is a list of dicts {predicate: True | False | None}; a missing key or None means "unknown".
Kleene logic: NOT unknown = unknown; AND is false if any operand is false, else unknown if any is unknown;
OR is the dual. evaluate() returns True, False or None (unknown). Kleene evaluation is sound (a decided value
holds for every completion of the unknowns) but not complete (`p IMPLIES p` with p unknown is unknown); callers
that need exact answers, such as MLN enumeration, must enumerate the unknown predicates.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

UNARY = ("NOT", "ALWAYS", "EVENTUALLY", "NEXT")
BINARY = ("AND", "OR", "IMPLIES", "UNTIL")
TEMPORAL = ("ALWAYS", "EVENTUALLY", "NEXT", "UNTIL")
KEYWORDS = set(UNARY + BINARY + ("TRUE", "FALSE"))
NAME_RE = re.compile(r"[a-z][a-z0-9_]*\Z")
TOKEN_RE = re.compile(r"\s*(?:(\()|(\))|([A-Za-z_][A-Za-z0-9_]*)|(\S))")

Node = Tuple  # ("atom", name) | ("const", bool) | (unary_op, child) | (binary_op, left, right)


class LTLfSyntaxError(ValueError):
    pass


def tokenize(text: str) -> List[str]:
    out, pos = [], 0
    text = text.rstrip()
    while pos < len(text):
        m = TOKEN_RE.match(text, pos)
        if not m:
            break
        if m.group(4):
            raise LTLfSyntaxError(f"unexpected character {m.group(4)!r} at position {m.start(4)}")
        out.append(m.group(1) or m.group(2) or m.group(3))
        pos = m.end()
    return out


class _Parser:
    def __init__(self, tokens: List[str]):
        self.t, self.i = tokens, 0

    def peek(self) -> Optional[str]:
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self, expected: Optional[str] = None, what: Optional[str] = None) -> str:
        tok = self.peek()
        if tok is None:
            want = what or expected
            raise LTLfSyntaxError(f"unexpected end of formula{f' (expected {want})' if want else ''}")
        if expected is not None and tok != expected:
            raise LTLfSyntaxError(f"expected {expected!r}, found {tok!r}")
        self.i += 1
        return tok

    def parse(self) -> Node:
        if not self.t:
            raise LTLfSyntaxError("empty formula")
        node = self.implies()
        if self.peek() is not None:
            raise LTLfSyntaxError(f"unexpected token {self.peek()!r} after a complete formula")
        return node

    def implies(self) -> Node:
        left = self.or_()
        if self.peek() == "IMPLIES":
            self.take()
            return ("IMPLIES", left, self.implies())
        return left

    def or_(self) -> Node:
        node = self.and_()
        while self.peek() == "OR":
            self.take()
            node = ("OR", node, self.and_())
        return node

    def and_(self) -> Node:
        node = self.until()
        while self.peek() == "AND":
            self.take()
            node = ("AND", node, self.until())
        return node

    def until(self) -> Node:
        left = self.unary()
        if self.peek() == "UNTIL":
            self.take()
            return ("UNTIL", left, self.until())
        return left

    def unary(self) -> Node:
        tok = self.peek()
        if tok in UNARY:
            self.take()
            return (tok, self.unary())
        return self.atom()

    def atom(self) -> Node:
        tok = self.take(what="a predicate, constant or '('")
        if tok == "(":
            node = self.implies()
            self.take(")")
            return node
        if tok in ("TRUE", "FALSE"):
            return ("const", tok == "TRUE")
        if tok in KEYWORDS or tok == ")":
            raise LTLfSyntaxError(f"operator {tok!r} where a predicate was expected")
        if not NAME_RE.match(tok):
            raise LTLfSyntaxError(f"predicate name {tok!r} is not snake_case (lower-case letters, digits, underscores)")
        return ("atom", tok)


@dataclass(frozen=True)
class Formula:
    text: str
    tree: Node = field(repr=False)

    @property
    def atoms(self) -> Tuple[str, ...]:
        return tuple(sorted(_atoms(self.tree)))

    @property
    def operators(self) -> Tuple[str, ...]:
        return tuple(sorted(_ops(self.tree)))

    @property
    def has_temporal(self) -> bool:
        return any(op in TEMPORAL for op in _ops(self.tree))

    def canonical(self) -> str:
        return to_string(self.tree)


def parse(text: str) -> Formula:
    return Formula(text, _Parser(tokenize(text)).parse())


def syntax_errors(text: str, predicate_names: Optional[Sequence[str]] = None) -> List[str]:
    """Empty list if `text` parses and, when predicate_names is given, uses exactly declared predicates."""
    try:
        f = parse(text)
    except LTLfSyntaxError as e:
        return [f"syntax: {e}"]
    errs = []
    if predicate_names is not None:
        declared = set(predicate_names)
        undeclared = sorted(set(f.atoms) - declared)
        if undeclared:
            errs.append(f"undeclared predicates in logic: {undeclared}")
    return errs


def _atoms(n: Node) -> set:
    if n[0] == "atom":
        return {n[1]}
    if n[0] == "const":
        return set()
    return set().union(*(_atoms(c) for c in n[1:]))


def _ops(n: Node) -> set:
    if n[0] in ("atom", "const"):
        return set()
    return {n[0]}.union(*(_ops(c) for c in n[1:]))


_PREC = {"IMPLIES": 1, "OR": 2, "AND": 3, "UNTIL": 4}


def to_string(n: Node, parent_prec: int = 0) -> str:
    """Canonical text with minimal parentheses (re-parses to the same tree)."""
    op = n[0]
    if op == "atom":
        return n[1]
    if op == "const":
        return "TRUE" if n[1] else "FALSE"
    if op in UNARY:
        child = n[1]
        inner = to_string(child, 5)
        return f"{op} {inner}"
    p = _PREC[op]
    right_assoc = op in ("IMPLIES", "UNTIL")
    left = to_string(n[1], p + (1 if right_assoc else 0))
    right = to_string(n[2], p + (0 if right_assoc else 1))
    s = f"{left} {op} {right}"
    return f"({s})" if p < parent_prec else s


# ---------------------------------------------------------------- semantics (Kleene)

def _not(a):
    return None if a is None else (not a)


def _and(a, b):
    if a is False or b is False:
        return False
    if a is None or b is None:
        return None
    return True


def _or(a, b):
    if a is True or b is True:
        return True
    if a is None or b is None:
        return None
    return False


def evaluate(formula, trace: Sequence[Dict[str, Optional[bool]]], pos: int = 0) -> Optional[bool]:
    """Truth value of `formula` (Formula, tree or text) at position `pos` of the finite `trace`."""
    if isinstance(formula, str):
        formula = parse(formula)
    tree = formula.tree if isinstance(formula, Formula) else formula
    if not trace:
        raise ValueError("LTLf traces must have at least one position")
    if not 0 <= pos < len(trace):
        raise ValueError(f"position {pos} outside the trace (length {len(trace)})")
    frozen = tuple(tuple(sorted(step.items())) for step in trace)
    return _eval(tree, frozen, pos)


@lru_cache(maxsize=200_000)
def _eval(n: Node, trace: Tuple, i: int) -> Optional[bool]:
    op = n[0]
    if op == "atom":
        for k, v in trace[i]:
            if k == n[1]:
                return v
        return None
    if op == "const":
        return n[1]
    if op == "NOT":
        return _not(_eval(n[1], trace, i))
    if op == "AND":
        return _and(_eval(n[1], trace, i), _eval(n[2], trace, i))
    if op == "OR":
        return _or(_eval(n[1], trace, i), _eval(n[2], trace, i))
    if op == "IMPLIES":
        return _or(_not(_eval(n[1], trace, i)), _eval(n[2], trace, i))
    last = len(trace) - 1
    if op == "NEXT":
        return False if i >= last else _eval(n[1], trace, i + 1)
    if op == "ALWAYS":
        v = True
        for j in range(i, last + 1):
            v = _and(v, _eval(n[1], trace, j))
            if v is False:
                break
        return v
    if op == "EVENTUALLY":
        v = False
        for j in range(i, last + 1):
            v = _or(v, _eval(n[1], trace, j))
            if v is True:
                break
        return v
    if op == "UNTIL":
        result, prefix = False, True  # prefix: φ1 at every position i..j-1
        for j in range(i, last + 1):
            result = _or(result, _and(prefix, _eval(n[2], trace, j)))
            if result is True:
                break
            prefix = _and(prefix, _eval(n[1], trace, j))
            if prefix is False:
                break
        return result
    raise ValueError(f"unknown operator {op!r}")


def to_flloat(n: Node) -> str:
    """The same formula in flloat's LTLf syntax (used only by the oracle test)."""
    op = n[0]
    if op == "atom":
        return n[1]
    if op == "const":
        return "true" if n[1] else "false"
    sym = {"NOT": "!", "ALWAYS": "G", "EVENTUALLY": "F", "NEXT": "X"}
    if op in sym:
        return f"{sym[op]}({to_flloat(n[1])})"
    bsym = {"AND": "&", "OR": "|", "IMPLIES": "->", "UNTIL": "U"}
    return f"({to_flloat(n[1])} {bsym[op]} {to_flloat(n[2])})"
