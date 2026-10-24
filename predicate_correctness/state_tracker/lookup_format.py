"""Part 5: the lookup format. A validator (Python's ast) and an evaluator.

A lookup computes one predicate's value from the state (state.py) and the pending call's arguments. It is one Python
expression that may use only (p5.md, "Format"):
  - the names  args, db(kind, id), db_all(kind), shown(kind, id), shown_all(kind), events(tool=..., ok=...), today,
    date(text);
  - comparisons (== != < <= > >= in, not in, is, is not), and, or, not;
  - len, sum, any, all;
  - simple list comprehensions and generator expressions (`for` target: a name or a tuple of names; `if` filters);
  - indexing on dicts and lists (x["field"], x[0], x[-1]; no slices) and x.get(field) / x.get(field, default);
  - constants (text, numbers, True, False, None) and list or tuple displays of allowed expressions.
Anything else is rejected: no other names or functions, no other attributes, no arithmetic, no assignments, no
lambdas, no imports.

Meaning of the names (bound to the State methods of state.py):
  db(kind, id)      state.db_get     the object in the database copy, or None          (fact)
  db_all(kind)      state.db_all     all objects of a kind in the database copy        (fact)
  shown(kind, id)   state.shown_get  the newest version shown before the step, or None (shown)
  shown_all(kind)   state.shown_all  all shown objects of a kind                       (shown)
  events(tool, ok)  state.events_where  earlier executed tool calls (event dicts)
  today             state.today      the policy's current time (airline) or None (retail)
  date(text)        state.parse_date 'YYYY-MM-DD[ HH:MM:SS]' -> datetime, or None
  args              the pending call's arguments (dict)

Result: True, False or None (unknown).
  - The expression's value must be True, False or None. None, and a missing object or field on the way (KeyError,
    IndexError, TypeError, e.g. None["status"] or a comparison with None), give the lookup's `if_missing` value:
    "false" -> False, "unknown" -> None.
  - Any other result (a number, a dict, ...) and an unknown kind are errors in the lookup itself (LookupEvalError).

Standard library only. No LLM calls. Never imports gold code.
"""
from __future__ import annotations

import ast
import datetime
import functools
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Optional, Set

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "state_tracker"

from state_tracker import paths                      # noqa: E402

LOOKUP_FIELDS = ("expr", "uses", "if_missing", "plain", "reason")
USES = ("fact", "shown")
IF_MISSING = {"false": False, "unknown": None}

# name -> (min positional args, max positional args, allowed keywords)
FUNCTIONS: Dict[str, tuple] = {
    "db": (2, 2, ()),
    "db_all": (1, 1, ()),
    "shown": (2, 2, ()),
    "shown_all": (1, 1, ()),
    "events": (0, 1, ("tool", "ok")),
    "date": (1, 1, ()),
    "len": (1, 1, ()),
    "sum": (1, 1, ()),
    "any": (1, 1, ()),
    "all": (1, 1, ()),
}
VALUES = ("args", "today")
KIND_FUNCTIONS = ("db", "db_all", "shown", "shown_all")     # first argument: a kind, written as a text constant
FACT_FUNCTIONS = ("db", "db_all")
SHOWN_FUNCTIONS = ("shown", "shown_all")

_BOOL_OPS = (ast.And, ast.Or)
_CMP_OPS = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot)
_GET = "__get"            # internal helper that x.get(...) is rewritten to; not usable in a lookup


class LookupFormatError(ValueError):
    """The expression is not in the lookup format."""


class LookupEvalError(RuntimeError):
    """The lookup ran but is wrong in itself (unknown kind, a result that is not True/False/None)."""


class _Missing(Exception):
    """x.get(...) on None: a needed object is missing."""


MISSING_ERRORS = (KeyError, IndexError, TypeError, _Missing)


# ----------------------------------------------------------------------------------------------- validator

class _Validator:
    def __init__(self, kinds: Optional[Iterable[str]]):
        self.kinds = set(kinds) if kinds is not None else None
        self.calls: Set[str] = set()          # functions used
        self.kinds_used: Set[str] = set()

    def fail(self, node: ast.AST, msg: str) -> None:
        col = getattr(node, "col_offset", None)
        raise LookupFormatError(f"{msg}" + (f" (at column {col})" if col is not None else ""))

    def visit(self, node: ast.AST, bound: frozenset) -> None:
        if isinstance(node, ast.Expression):
            return self.visit(node.body, bound)
        if isinstance(node, ast.BoolOp):
            if not isinstance(node.op, _BOOL_OPS):
                self.fail(node, "only 'and' and 'or' are allowed")
            for v in node.values:
                self.visit(v, bound)
            return
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return self.visit(node.operand, bound)
            if (isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant)
                    and type(node.operand.value) in (int, float)):
                return                                    # a negative number, e.g. x[-1]
            self.fail(node, f"unary operator {type(node.op).__name__} is not allowed (only 'not' and a negative number)")
        if isinstance(node, ast.Compare):
            for op in node.ops:
                if not isinstance(op, _CMP_OPS):
                    self.fail(node, f"comparison {type(op).__name__} is not allowed")
            self.visit(node.left, bound)
            for c in node.comparators:
                self.visit(c, bound)
            return
        if isinstance(node, ast.Call):
            return self.visit_call(node, bound)
        if isinstance(node, ast.Name):
            if not isinstance(node.ctx, ast.Load):
                self.fail(node, "assignment is not allowed")
            if node.id in bound or node.id in VALUES:
                return
            if node.id in FUNCTIONS:
                self.fail(node, f"function {node.id!r} may only be called")
            self.fail(node, f"name {node.id!r} is not allowed")
        if isinstance(node, ast.Constant):
            if node.value is None or type(node.value) in (bool, int, float, str):
                return
            self.fail(node, f"constant of type {type(node.value).__name__} is not allowed")
        if isinstance(node, (ast.List, ast.Tuple)):
            if not isinstance(node.ctx, ast.Load):
                self.fail(node, "assignment is not allowed")
            for e in node.elts:
                if isinstance(e, ast.Starred):
                    self.fail(e, "'*' is not allowed")
                self.visit(e, bound)
            return
        if isinstance(node, ast.Subscript):
            if not isinstance(node.ctx, ast.Load):
                self.fail(node, "assignment is not allowed")
            if isinstance(node.slice, ast.Slice):
                self.fail(node, "slices are not allowed (only x[key] and x[index])")
            self.visit(node.value, bound)
            self.visit(node.slice, bound)
            return
        if isinstance(node, (ast.ListComp, ast.GeneratorExp)):
            return self.visit_comp(node, bound)
        if isinstance(node, ast.Attribute):
            self.fail(node, f"attribute .{node.attr} is not allowed (only x.get(field) as a call)")
        if isinstance(node, ast.BinOp):
            self.fail(node, f"arithmetic ({type(node.op).__name__}) is not allowed; use sum([...]) to add")
        self.fail(node, f"{type(node).__name__} is not allowed")

    def visit_call(self, node: ast.Call, bound: frozenset) -> None:
        f = node.func
        for a in node.args:
            if isinstance(a, ast.Starred):
                self.fail(a, "'*args' is not allowed")
        for k in node.keywords:
            if k.arg is None:
                self.fail(node, "'**kwargs' is not allowed")
        if isinstance(f, ast.Attribute):                   # x.get(field) or x.get(field, default)
            if f.attr != "get":
                self.fail(node, f"method .{f.attr}() is not allowed (only .get)")
            if node.keywords or not 1 <= len(node.args) <= 2:
                self.fail(node, ".get takes one or two positional arguments")
            self.visit(f.value, bound)
            for a in node.args:
                self.visit(a, bound)
            self.calls.add("get")
            return
        if not isinstance(f, ast.Name) or f.id not in FUNCTIONS or f.id in bound:
            name = f.id if isinstance(f, ast.Name) else type(f).__name__
            self.fail(node, f"call of {name!r} is not allowed")
        lo, hi, kws = FUNCTIONS[f.id]
        for k in node.keywords:
            if k.arg not in kws:
                self.fail(node, f"{f.id}() has no keyword {k.arg!r}")
        if not lo <= len(node.args) <= hi:
            self.fail(node, f"{f.id}() takes {lo}" + (f" to {hi}" if hi != lo else "") + " positional arguments")
        if f.id == "events" and node.args and any(k.arg == "tool" for k in node.keywords):
            self.fail(node, "events(): tool given twice")
        if f.id in KIND_FUNCTIONS:
            kind = node.args[0]
            if not (isinstance(kind, ast.Constant) and isinstance(kind.value, str)):
                self.fail(node, f"{f.id}(): the kind must be written as a text constant")
            if self.kinds is not None and kind.value not in self.kinds:
                self.fail(node, f"{f.id}(): unknown kind {kind.value!r}; known: {sorted(self.kinds)}")
            self.kinds_used.add(kind.value)
        self.calls.add(f.id)
        for a in node.args:
            self.visit(a, bound)
        for k in node.keywords:
            self.visit(k.value, bound)

    def visit_comp(self, node: ast.AST, bound: frozenset) -> None:
        inner = bound
        for gen in node.generators:
            if gen.is_async:
                self.fail(node, "async comprehensions are not allowed")
            self.visit(gen.iter, inner)
            inner = inner | self.targets(gen.target)
            for cond in gen.ifs:
                self.visit(cond, inner)
        self.visit(node.elt, inner)

    def targets(self, t: ast.AST) -> frozenset:
        if isinstance(t, ast.Name):
            if t.id in FUNCTIONS or t.id in VALUES or t.id.startswith("_"):
                self.fail(t, f"name {t.id!r} cannot be used as a loop variable")
            return frozenset([t.id])
        if isinstance(t, ast.Tuple):
            out: frozenset = frozenset()
            for e in t.elts:
                out |= self.targets(e)
            return out
        self.fail(t, "a loop variable must be a name or a tuple of names")
        return frozenset()


def parse(expr: str) -> ast.Expression:
    if not isinstance(expr, str) or not expr.strip():
        raise LookupFormatError("the expression must be a non-empty text")
    try:
        return ast.parse(expr.strip(), mode="eval")
    except SyntaxError as e:
        raise LookupFormatError(f"not a Python expression: {e.msg}") from None


def validate(expr: str, kinds: Optional[Iterable[str]] = None) -> dict:
    """Check that `expr` is in the lookup format. With `kinds`, also check the kinds named in db/db_all/shown/
    shown_all. Returns {"calls": functions used, "kinds": kinds used}. Raises LookupFormatError."""
    tree = parse(expr)
    v = _Validator(kinds)
    v.visit(tree, frozenset())
    return {"calls": sorted(v.calls), "kinds": sorted(v.kinds_used)}


def domain_kinds(domain: str) -> List[str]:
    """The kinds known for a domain (state_tracker/tool_table.json)."""
    with open(os.path.join(paths.STATE_TRACKER_DIR, "tool_table.json"), encoding="utf-8") as f:
        return sorted(json.load(f)["domains"][domain]["kinds"])


# ----------------------------------------------------------------------------------------------- evaluator

class _RewriteGet(ast.NodeTransformer):
    """x.get(k[, d]) -> __get(x, k[, d]), so that .get on None counts as a missing object."""

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            return ast.copy_location(ast.Call(func=ast.Name(id=_GET, ctx=ast.Load()),
                                              args=[node.func.value] + node.args, keywords=[]), node)
        return node


@functools.lru_cache(maxsize=None)
def compile_lookup(expr: str):
    """Validate (without kinds) and compile an expression. Cached by text."""
    validate(expr)
    tree = ast.fix_missing_locations(_RewriteGet().visit(parse(expr)))
    return compile(tree, "<lookup>", "eval")


def _get(obj: Any, key: Any, default: Any = None) -> Any:
    if obj is None:
        raise _Missing("get on None")
    if not isinstance(obj, dict):                          # e.g. a passenger given as text: malformed data
        raise TypeError(f".get on a {type(obj).__name__}, not a dict")
    return obj.get(key, default)


def _date(text: Any) -> Optional[datetime.datetime]:
    from state_tracker.state import parse_date
    return parse_date(text)


def bindings(state: Any, args: Optional[dict] = None) -> Dict[str, Any]:
    """The names a lookup can use, bound to one State. `args` defaults to the state's pending call's arguments."""
    if args is None:
        args = (state.pending or {}).get("args") or {}
    kinds = set(getattr(state, "_kinds", {}) or {})

    def check_kind(kind: str) -> None:
        if kinds and kind not in kinds:
            raise LookupEvalError(f"unknown kind {kind!r} for {state.domain}")

    def db(kind, oid):
        check_kind(kind)
        return state.db_get(kind, oid)

    def db_all(kind):
        check_kind(kind)
        return state.db_all(kind)

    def shown(kind, oid):
        check_kind(kind)
        return state.shown_get(kind, oid)

    def shown_all(kind):
        check_kind(kind)
        return state.shown_all(kind)

    def events(tool=None, ok=None):
        return state.events_where(tool=tool, ok=ok)

    return {"__builtins__": {}, "args": args, "today": state.today, "db": db, "db_all": db_all, "shown": shown,
            "shown_all": shown_all, "events": events, "date": _date, "len": len, "sum": sum, "any": any, "all": all,
            _GET: _get}


def _lookup_parts(lookup: Any, if_missing: Optional[str]) -> tuple:
    if isinstance(lookup, str):
        return lookup, (if_missing or "unknown")
    return lookup["expr"], (if_missing or lookup.get("if_missing") or "unknown")


def evaluate_detail(lookup: Any, state: Any, args: Optional[dict] = None, if_missing: Optional[str] = None) -> dict:
    """Run a lookup (a lookup dict with 'expr' and 'if_missing', or an expression text) on a State.
    Returns {"value": True|False|None, "raw": the expression's own value or None,
             "missing": None or why if_missing was applied}.
    Raises LookupFormatError (not in the format) or LookupEvalError (the lookup is wrong in itself)."""
    expr, miss = _lookup_parts(lookup, if_missing)
    if miss not in IF_MISSING:
        raise LookupFormatError(f"if_missing must be one of {sorted(IF_MISSING)}, not {miss!r}")
    code = compile_lookup(expr)
    try:
        raw = eval(code, bindings(state, args))           # noqa: S307 - validated expression, no builtins
    except MISSING_ERRORS as e:
        return {"value": IF_MISSING[miss], "raw": None, "missing": f"{type(e).__name__}: {e}"}
    if raw is None:
        return {"value": IF_MISSING[miss], "raw": None, "missing": "the expression gave None"}
    if raw is True or raw is False:
        return {"value": raw, "raw": raw, "missing": None}
    raise LookupEvalError(f"the expression gave a {type(raw).__name__} ({str(raw)[:80]}), not True, False or None")


def evaluate(lookup: Any, state: Any, args: Optional[dict] = None, if_missing: Optional[str] = None
             ) -> Optional[bool]:
    """True, False or None (unknown). See evaluate_detail()."""
    return evaluate_detail(lookup, state, args, if_missing)["value"]


# ----------------------------------------------------------------------------------------------- lookup files

def lookups_path(domain: str) -> str:
    return os.path.join(paths.STATE_TRACKER_DIR, f"lookups_{domain}.json")


def load_lookups(domain: str, path: Optional[str] = None) -> Dict[str, dict]:
    """predicate -> {expr, uses, if_missing, plain, reason} from state_tracker/lookups_<domain>.json."""
    with open(path or lookups_path(domain), encoding="utf-8") as f:
        return json.load(f)["lookups"]


def check_lookup(name: str, lk: dict, kinds: Optional[Iterable[str]] = None) -> List[str]:
    """Problems with one lookup entry (empty list: fine)."""
    problems = []
    for field in LOOKUP_FIELDS:
        if not isinstance(lk.get(field), str) or not lk[field].strip():
            problems.append(f"{name}: field {field!r} missing or empty")
    extra = set(lk) - set(LOOKUP_FIELDS)
    if extra:
        problems.append(f"{name}: unknown fields {sorted(extra)}")
    if lk.get("uses") not in USES:
        problems.append(f"{name}: uses must be one of {USES}")
    if lk.get("if_missing") not in IF_MISSING:
        problems.append(f"{name}: if_missing must be one of {sorted(IF_MISSING)}")
    try:
        info = validate(lk.get("expr", ""), kinds)
    except LookupFormatError as e:
        problems.append(f"{name}: {e}")
    else:
        if lk.get("uses") == "fact" and set(info["calls"]) & set(SHOWN_FUNCTIONS):
            problems.append(f"{name}: uses 'fact' but calls shown()/shown_all()")
    return problems


def check_lookups(domain: str, lookups: Optional[Dict[str, dict]] = None) -> List[str]:
    """Problems with a domain's lookup file: every code-type predicate (output/predicate_types.json) has exactly one
    lookup, no other predicate has one, and each lookup passes check_lookup()."""
    from state_tracker.predicate_types import is_code_type, load_types
    lookups = load_lookups(domain) if lookups is None else lookups
    types = load_types()[domain]
    code = {n for n, e in types.items() if is_code_type(e["type"])}
    problems = [f"{domain}: no lookup for code-type predicate {n}" for n in sorted(code - set(lookups))]
    problems += [f"{domain}: lookup for {n}, which is not a code-type predicate" for n in sorted(set(lookups) - code)]
    kinds = domain_kinds(domain)
    for n in sorted(lookups):
        problems += check_lookup(n, lookups[n], kinds)
    return problems


def main(argv=None) -> int:
    """Check both lookup files."""
    problems = []
    for d in paths.DOMAINS:
        lk = load_lookups(d)
        p = check_lookups(d, lk)
        print(f"{d}: {len(lk)} lookups, {len(p)} problems")
        problems += p
    for p in problems:
        print("  PROBLEM:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.exit(main())
