"""Tracker v3, part 5: the one v3 fact evaluator, and the validator of the fact files.

A fact file (state_tracker/v3/facts_v3_<domain>.json; docs/planning/tracker_v3/p5.md) defines every fact of the frozen
TGR rules as a two-valued state: true or false. A fact has parts. Each part has a source (database, event, arguments,
structure, question) and an expression `expr`. `combine` joins the parts with AND, OR, NOT and parentheses.

    from state_tracker.v3 import facts_format_v3 as F
    problems = F.validate(doc, "retail")                    # [] when the file is fine
    r = F.evaluate(doc["facts"][name], state, args, view=None, answers=None, name=name)
    r["value"]        True or False (always)
    r["source"]       the fact's sources (a list)
    r["how"]          "combine" (the parts decided) or "blocking_value" (a problem: the fact takes its blocking value)
    r["parts"]        {part id: {"value", "source", "who", "reads", "how", "detail", "notes"}}; "who" is the part's
                      own `who` when it has one, else the fact's (p10 picks the advice per part)
    r["items"]        None, or (a fact with for_each) one {"index", "value", "parts"} per item; r["parts"] is then
                      the deciding item's parts (r["deciding_item"]: the first false item, else the last one)
    r["evidence"]     {"text": the entry's evidence text, "notes": what the helpers noted}
    r["reads"]        what the expressions read (replay.RecordingState entries: db / shown / events ...)
    r["problems"]     [{"kind", "part", "item", "detail"}]: counted by the caller, never silent
    r["problems_ignored"]  question parts' unclear answers that did not decide the value (another OR branch did)
    F.blocking_result(entry, kind, detail)   the same result shape for an error found outside (p9: a state error)

Optional fields, added to the fixed schema (absent = null):
  part `who`            agent | ask | user_only | none: overrides the fact's `who` for this part;
  part `if_nonexistent` true | false: the part's value for a nonexistent object (below; default false);
  fact `for_each`       {"arg": "<argument path, e.g. passengers>", "if_empty": true | false}: combine holds for
                        EACH item of that list argument (dot-separated keys from args). The parts run once per item
                        and read it as `item` (allowed only in such a fact); the fact is true only if every item
                        gives true. An empty list gives if_empty. A missing list is a missing argument; a value that
                        is not a list is a type_error. A missing field of the item is a missing argument.

The expression language is the frozen v2 lookup format (state_tracker/lookup_format.py, imported unchanged: names
args, db, db_all, shown, shown_all, events, today, date, len, sum, any, all; no arithmetic), plus only the NEW names
registered here with register_name() (p6 helpers, p7 structure helpers, p8 question helpers). A registered helper is
validated like a built-in name (number of positional arguments, keywords). Unknown names stay rejected.
A helper is called as func(ctx, *args, **keywords); ctx is a Context (the part's recording state, the pending call's
arguments, the message view, the answers hook). Which parts may call a helper depends on the helper's source
(HELPER_USE): a question helper only in a question part, a structure helper in structure and question parts, a
database / event / arguments helper in any part. A question part must call a question helper.

Values when something is missing (p5.md, "The fact sources", rule 5):
  - a missing argument (the expression reads args[...] that the call does not have) -> the fact takes its
    blocking_value; problem "missing_argument";
  - a nonexistent object (x[k] or x.get(k) on None: db(kind, id) or shown(kind, id) found nothing, or .get gave None
    and the expression reads into it) -> the part takes its `if_nonexistent` value (an optional part field;
    default false, as p5 says "a nonexistent id is false"). Not a problem. An expression may also test None itself;
  - a missing field of an object that exists (x[k] on a real dict without k; a list index out of range) -> a bug:
    the fact takes its blocking_value; problem "missing_field";
  - a TypeError on the way (a comparison with None, ...) -> the blocking value; problem "type_error";
  - a helper may raise UseBlockingValue(kind, detail), e.g. p8's "unclear" -> the blocking value; problem kind.
    An "unclear" in a QUESTION part (p12 fix) gives only that part the fact's blocking value: combine (AND / OR) then
    goes on with it, so the other branch of an OR is still evaluated. When the fact's value rests on such a part (it
    would differ with the part's other value; with AND / OR only, the value is then the blocking value), the problem
    is in r["problems"] and "how" is "blocking_value", as before. When the other branch decided the value, "how" is
    "combine", r["problems"] is empty and the unclear answers are listed in r["problems_ignored"] (so a caller that
    reads "problems -> blocking value" stays right). Every other problem (any kind in a code part, any other kind in
    a question part) gives the whole fact its blocking value, as before.
Definition errors raise, they never become a value: NotDefinedYet (a part with expr null, or a name not registered
yet), LookupFormatError (not in the format), FactEvalError (a result that is not True or False: two values only),
LookupEvalError (unknown kind).

Order: every code part (database, event, arguments, structure) runs. A question part runs only while `combine` still
needs it (a tiny question is asked only when a check needs it, p8). After a problem in a code part, no question part
runs. A part that did not run has value None and says why in "how" ("not_needed", "not_run").

CLI (run from predicate_correctness/; main() first checks the eval v2 manifest, state_tracker/v3/frozen.py):
    python -B -m state_tracker.v3.facts_format_v3 --check retail airline
    python -B -m state_tracker.v3.facts_format_v3 --check airline --file <path> [--partial]
Standard library only. No LLM call, no network. Never imports gold code or any scoring module. No side effects on
import (state_tracker.replay is imported only when evaluate() runs).
"""
from __future__ import annotations

import argparse
import ast
import collections
import json
import keyword
import os
import re
import sys
from typing import Any, Callable, Dict, Iterable, List, NamedTuple, Optional, Sequence, Set, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    __package__ = "state_tracker.v3"

from state_tracker import lookup_format as L          # noqa: E402  (frozen; imported unchanged)
from state_tracker import paths                        # noqa: E402

SCHEMA_VERSION = 1
SOURCES = ("database", "event", "arguments", "structure", "question")
CODE_SOURCES = ("database", "event", "arguments", "structure")
WHO = ("agent", "ask", "user_only", "none")
READING_QS = ("Q4", "Q6", "Q7")

TOP_FIELDS = ("_about", "domain", "schema_version", "facts")
TOP_OPTIONAL = ("part",)                                # the airline file comes in two parts; accepted and ignored
FACT_FIELDS = ("sources", "parts", "combine", "start", "update", "who", "evidence", "policy", "rules",
               "blocking_value", "missing", "reading", "fixed", "reason", "v2")
FACT_OPTIONAL = ("for_each",)                           # schema addition (see the module text)
PART_FIELDS = ("source", "plain", "expr", "question", "about")
PART_OPTIONAL = ("if_nonexistent", "who")               # schema additions (see the module text)
READING_FIELDS = ("q", "default", "other")
FOR_EACH_FIELDS = ("arg", "if_empty")
ITEM = "item"                                           # the current item in a for_each fact
TEXT_FIELDS = ("update", "evidence", "missing", "reason", "v2")

PROBLEM_KINDS = ("missing_argument", "missing_field", "type_error")   # built in; helpers may add kinds
COMBINE_WORDS = ("AND", "OR", "NOT")

# Which part sources may call a helper of a given source.
HELPER_USE = {"database": SOURCES, "event": SOURCES, "arguments": SOURCES,
              "structure": ("structure", "question"), "question": ("question",)}

FACTS_DIR = os.path.dirname(os.path.abspath(__file__))
RULE_TABLE_DIR = os.path.join(paths.OUTPUT_DIR, "eval_v3")

_K_ID = re.compile(r"^K[1-9][0-9]*$")
_S_ID = re.compile(r"^S[1-9][0-9]*$")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ARG_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_GET = "__get"            # x.get(k[, d]) is rewritten to __get(x, k[, d])
_SUB = "__sub"            # x[k] is rewritten to __sub(x, k)


# ----------------------------------------------------------------------------------------------- errors

class NotDefinedYet(RuntimeError):
    """A fact cannot run yet: a part has no expression, or it uses a name that is not registered yet."""


class UnknownName(L.LookupFormatError):
    """The expression uses a name that is neither in the lookup format nor registered."""

    def __init__(self, name: str, message: str):
        super().__init__(message)
        self.name = name


class FactEvalError(L.LookupEvalError):
    """A part's expression gave something that is not True or False (two values only)."""


class MissingInput(RuntimeError):
    """A helper needs the message view or the answers hook, and evaluate() did not get it."""


class UseBlockingValue(Exception):
    """Raised on the way: the fact takes its blocking value, and the problem `kind` is recorded."""
    kind = "use_blocking_value"

    def __init__(self, detail: str = "", kind: Optional[str] = None):
        super().__init__(detail)
        if kind is not None:
            self.kind = kind
        self.detail = detail


class MissingArgument(UseBlockingValue):
    """The expression read an argument that the pending call does not have."""
    kind = "missing_argument"


class MissingField(UseBlockingValue):
    """The expression read a field (or list index) that an existing object does not have: a bug (p5 rule 5)."""
    kind = "missing_field"


class MissingObject(Exception):
    """The expression read into None: the object does not exist. The part takes its if_nonexistent value."""


class CombineError(ValueError):
    """`combine` is not a valid AND / OR / NOT expression over part ids."""


# ----------------------------------------------------------------------------------------------- the registry

class Helper(NamedTuple):
    name: str
    func: Callable
    min_args: int
    max_args: int
    keywords: Tuple[str, ...]
    source: str
    doc: str


_REGISTRY: Dict[str, Helper] = {}
_STATE = {"version": 0}                     # changes on every register / unregister (the compile cache uses it)


def register_name(name: str, func: Callable, min_args: int, max_args: int, keywords: Iterable[str] = (),
                  source: Optional[str] = None, doc: str = "") -> Helper:
    """Register a NEW name for fact expressions. It is called as func(ctx, *positional, **keywords) with
    min_args..max_args positional arguments and only the given keywords. `source` is one of SOURCES and says which
    parts may call it (HELPER_USE). A built-in lookup name, a Python keyword, a name starting with '_' or a name that
    is already registered (with another function or other limits) is refused (ValueError). Registering the very same
    helper twice changes nothing."""
    kws = tuple(keywords)
    if not isinstance(name, str) or not _IDENT.match(name) or name.startswith("_") or keyword.iskeyword(name):
        raise ValueError(f"helper name {name!r}: must be a plain name (letters, digits, '_'; not starting with '_')")
    if name in L.FUNCTIONS or name in L.VALUES or name in ("get", ITEM) or name.upper() in COMBINE_WORDS:
        raise ValueError(f"helper name {name!r} is a built-in name of the lookup format; only new names are added")
    if not callable(func):
        raise ValueError(f"helper {name!r}: func is not callable")
    if (not isinstance(min_args, int) or not isinstance(max_args, int) or isinstance(min_args, bool)
            or isinstance(max_args, bool) or not 0 <= min_args <= max_args):
        raise ValueError(f"helper {name!r}: need 0 <= min_args <= max_args (got {min_args!r}, {max_args!r})")
    for k in kws:
        if not isinstance(k, str) or not _IDENT.match(k) or keyword.iskeyword(k):
            raise ValueError(f"helper {name!r}: bad keyword {k!r}")
    if len(set(kws)) != len(kws):
        raise ValueError(f"helper {name!r}: a keyword is listed twice")
    if source not in SOURCES:
        raise ValueError(f"helper {name!r}: source must be one of {SOURCES}, not {source!r}")
    h = Helper(name, func, min_args, max_args, kws, source, doc)
    old = _REGISTRY.get(name)
    if old is not None:
        if old == h:
            return old
        raise ValueError(f"helper {name!r} is already registered (source {old.source}); unregister it first")
    _REGISTRY[name] = h
    _STATE["version"] += 1
    return h


def unregister_name(name: str) -> None:
    """Remove a registered name (KeyError if it is not registered)."""
    del _REGISTRY[name]
    _STATE["version"] += 1


def registered_names() -> Dict[str, Helper]:
    """A copy of the registry: name -> Helper."""
    return dict(_REGISTRY)


# ----------------------------------------------------------------------------------------------- expressions

class _Validator(L._Validator):
    """The frozen lookup-format validator, plus the registered names. Every other check is the frozen one."""

    def __init__(self, kinds: Optional[Iterable[str]], registry: Dict[str, Helper], values: Iterable[str] = ()):
        super().__init__(kinds)
        self.registry = registry
        self.values = tuple(values)                  # extra value names (ITEM in a for_each fact)
        self.helpers: Set[str] = set()
        self.values_used: Set[str] = set()

    def visit(self, node: ast.AST, bound: frozenset) -> None:
        if (isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in bound
                and node.id not in L.VALUES and node.id not in L.FUNCTIONS):
            if node.id in self.values:
                self.values_used.add(node.id)
                return None
            if node.id in self.registry:
                self.fail(node, f"function {node.id!r} may only be called")
            raise UnknownName(node.id, f"name {node.id!r} is not allowed: not in the lookup format and not registered"
                                       f" (at column {node.col_offset})")
        return super().visit(node, bound)

    def visit_call(self, node: ast.Call, bound: frozenset) -> None:
        f = node.func
        if isinstance(f, ast.Name) and f.id not in bound and f.id not in L.FUNCTIONS:
            h = self.registry.get(f.id)
            if h is None:
                raise UnknownName(f.id, f"call of {f.id!r} is not allowed: not in the lookup format and not "
                                        f"registered (at column {node.col_offset})")
            for a in node.args:
                if isinstance(a, ast.Starred):
                    self.fail(a, "'*args' is not allowed")
            for k in node.keywords:
                if k.arg is None:
                    self.fail(node, "'**kwargs' is not allowed")
                if k.arg not in h.keywords:
                    self.fail(node, f"{f.id}() has no keyword {k.arg!r}")
            if not h.min_args <= len(node.args) <= h.max_args:
                self.fail(node, f"{f.id}() takes {h.min_args}"
                          + (f" to {h.max_args}" if h.max_args != h.min_args else "") + " positional arguments")
            self.helpers.add(f.id)
            self.calls.add(f.id)
            for a in node.args:
                self.visit(a, bound)
            for k in node.keywords:
                self.visit(k.value, bound)
            return
        return super().visit_call(node, bound)

    def targets(self, t: ast.AST) -> frozenset:
        if isinstance(t, ast.Name) and (t.id in self.registry or t.id in self.values):
            self.fail(t, f"name {t.id!r} cannot be used as a loop variable")
        return super().targets(t)


def validate_expr(expr: str, kinds: Optional[Iterable[str]] = None, values: Iterable[str] = ()) -> dict:
    """Check one part expression: the frozen lookup format plus the registered names (and the extra value names
    `values`: ITEM in a for_each fact). Returns {"calls", "kinds", "helpers", "values"}. Raises LookupFormatError
    (UnknownName for a name that is not registered)."""
    tree = L.parse(expr)
    v = _Validator(kinds, _REGISTRY, values)
    v.visit(tree, frozenset())
    return {"calls": sorted(v.calls), "kinds": sorted(v.kinds_used), "helpers": sorted(v.helpers),
            "values": sorted(v.values_used)}


def helper_use_problems(part_source: str, helpers: Iterable[str]) -> List[str]:
    """Problems with the registered helpers a part calls, for the part's source (HELPER_USE)."""
    out = []
    used = [_REGISTRY[h] for h in helpers if h in _REGISTRY]
    for h in used:
        if part_source not in HELPER_USE[h.source]:
            out.append(f"{h.name}() is a {h.source} helper; a part with source {part_source!r} may not call it")
    if part_source == "question" and not any(h.source == "question" for h in used):
        out.append("a question part must call a registered question helper (p8)")
    return out


class _RewriteAccess(ast.NodeTransformer):
    """x.get(k[, d]) -> __get(x, k[, d]) and x[k] -> __sub(x, k): so a missing argument, a nonexistent object and a
    missing field are told apart."""

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            return ast.copy_location(ast.Call(func=ast.Name(id=_GET, ctx=ast.Load()),
                                              args=[node.func.value] + node.args, keywords=[]), node)
        return node

    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:
        self.generic_visit(node)
        return ast.copy_location(ast.Call(func=ast.Name(id=_SUB, ctx=ast.Load()), args=[node.value, node.slice],
                                          keywords=[]), node)


_COMPILED: Dict[tuple, tuple] = {}


def compile_expr(expr: str, kinds: Optional[Iterable[str]] = None, values: Iterable[str] = ()) -> tuple:
    """(code, validate_expr info). Validated first; cached by text, kinds, extra values and registry version."""
    values = tuple(values)
    key = (expr, tuple(sorted(kinds)) if kinds else None, values, _STATE["version"])
    if key not in _COMPILED:
        info = validate_expr(expr, kinds, values)
        tree = ast.fix_missing_locations(_RewriteAccess().visit(L.parse(expr)))
        _COMPILED[key] = (compile(tree, "<v3 fact part>", "eval"), info)
    return _COMPILED[key]


class _ArgDict(dict):
    """The pending call's arguments (a plain dict that knows it holds arguments)."""


class _ArgList(list):
    """A list inside the pending call's arguments."""


def wrap_args(x: Any) -> Any:
    """A copy of the call's arguments in which every dict and list knows it is an argument."""
    if isinstance(x, dict):
        return _ArgDict((k, wrap_args(v)) for k, v in x.items())
    if isinstance(x, list):
        return _ArgList(wrap_args(v) for v in x)
    return x


def _sub(obj: Any, key: Any) -> Any:
    if isinstance(obj, (_ArgDict, _ArgList)):
        try:
            return obj[key]
        except (KeyError, IndexError):
            raise MissingArgument(f"the call has no argument [{key!r}]") from None
    if obj is None:
        raise MissingObject(f"[{key!r}] read on None: the object does not exist")
    try:
        return obj[key]
    except (KeyError, IndexError) as e:
        raise MissingField(f"{type(e).__name__}: [{key!r}] on an existing {type(obj).__name__}") from None


def _get(obj: Any, key: Any, default: Any = None) -> Any:
    if obj is None:
        raise MissingObject(f".get({key!r}) on None: the object does not exist")
    if not isinstance(obj, dict):
        raise TypeError(f".get on a {type(obj).__name__}, not a dict")
    return obj.get(key, default)


# ----------------------------------------------------------------------------------------------- combine

_TOKEN = re.compile(r"\s*(?:(\()|(\))|([A-Za-z_][A-Za-z0-9_]*))")


def _tokens(text: str) -> List[str]:
    out, pos = [], 0
    text = text.rstrip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise CombineError(f"unexpected character {text[pos:].lstrip()[:1]!r} at {pos}")
        out.append(m.group(1) or m.group(2) or m.group(3))
        pos = m.end()
    return out


class _CombineParser:
    """or := and ('OR' and)* ; and := not ('AND' not)* ; not := 'NOT' not | atom ; atom := part id | '(' or ')'.
    AND and OR mixed at one level without parentheses is refused (write (A AND B) OR C)."""

    def __init__(self, text: str):
        if not isinstance(text, str) or not text.strip():
            raise CombineError("combine must be a non-empty text")
        self.toks = _tokens(text)
        self.i = 0

    def peek(self) -> Optional[str]:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def take(self) -> str:
        t = self.peek()
        if t is None:
            raise CombineError("unexpected end")
        self.i += 1
        return t

    def parse(self) -> tuple:
        tree = self.parse_or()
        if self.peek() is not None:
            raise CombineError(f"unexpected {self.peek()!r} after a complete expression")
        return _strip_groups(tree)

    def parse_or(self) -> tuple:
        terms = [self.parse_and()]
        while self.peek() == "OR":
            self.take()
            terms.append(self.parse_and())
        if len(terms) == 1:
            return terms[0]
        if any(t[0] == "AND" for t in terms):
            raise CombineError("AND and OR mixed without parentheses; write e.g. (a AND b) OR c")
        return ("OR", terms)

    def parse_and(self) -> tuple:
        terms = [self.parse_not()]
        while self.peek() == "AND":
            self.take()
            terms.append(self.parse_not())
        return terms[0] if len(terms) == 1 else ("AND", terms)

    def parse_not(self) -> tuple:
        if self.peek() == "NOT":
            self.take()
            return ("NOT", self.parse_not())
        return self.parse_atom()

    def parse_atom(self) -> tuple:
        t = self.take()
        if t == "(":
            inner = self.parse_or()
            if self.take() != ")":
                raise CombineError("')' expected")
            return ("GROUP", inner)
        if t == ")" or t in COMBINE_WORDS:
            raise CombineError(f"a part id or '(' expected, got {t!r}")
        if t.upper() in COMBINE_WORDS:
            raise CombineError(f"{t!r}: write AND, OR, NOT in capitals")
        return ("ID", t)


def _strip_groups(t: tuple) -> tuple:
    if t[0] == "GROUP":
        return _strip_groups(t[1])
    if t[0] == "NOT":
        return ("NOT", _strip_groups(t[1]))
    if t[0] in ("AND", "OR"):
        return (t[0], [_strip_groups(x) for x in t[1]])
    return t


_COMBINE_CACHE: Dict[str, tuple] = {}


def parse_combine(text: str) -> tuple:
    """The tree of a combine text: ("ID", part id) | ("NOT", t) | ("AND", [t, ...]) | ("OR", [t, ...]).
    Raises CombineError."""
    if not isinstance(text, str):
        raise CombineError("combine must be a non-empty text")
    if text not in _COMBINE_CACHE:
        _COMBINE_CACHE[text] = _CombineParser(text).parse()
    return _COMBINE_CACHE[text]


def combine_ids(tree: tuple) -> List[str]:
    """The part ids of a combine tree, in left-to-right order, without repeats."""
    out: List[str] = []

    def walk(t):
        if t[0] == "ID":
            if t[1] not in out:
                out.append(t[1])
        elif t[0] == "NOT":
            walk(t[1])
        else:
            for x in t[1]:
                walk(x)

    walk(tree)
    return out


def combine_value(tree: tuple, values: Dict[str, Optional[bool]]) -> Optional[bool]:
    """The value of a combine tree. A part id missing from `values` (or None) is not known yet; the result is then
    None unless the known parts already decide it (AND with a false part, OR with a true part)."""
    op = tree[0]
    if op == "ID":
        v = values.get(tree[1])
        return v if v is None else bool(v)
    if op == "NOT":
        v = combine_value(tree[1], values)
        return None if v is None else not v
    vals = [combine_value(x, values) for x in tree[1]]
    if op == "AND":
        return False if any(v is False for v in vals) else (True if all(v is True for v in vals) else None)
    return True if any(v is True for v in vals) else (False if all(v is False for v in vals) else None)


# ----------------------------------------------------------------------------------------------- the evaluator

class Context:
    """What a registered helper gets as its first argument.
    fact, part_id, part   the fact name, the part id and the part entry
    state                 the part's recording state (replay.RecordingState): the helper's reads are recorded
    args                  the pending call's arguments
    view, answers         the message view (p7) and the answers hook (p8), as given to evaluate()
    item                  the current item in a for_each fact (else None)
    note(x)               add an evidence note (shown by the messages, p10)
    arg(key)              an argument, or MissingArgument (the fact takes its blocking value)
    need_view(), need_answers()   the view / the answers, or MissingInput"""

    def __init__(self, fact: str, part_id: str, part: dict, state: Any, args: dict, view: Any, answers: Any,
                 item: Any = None):
        self.fact = fact
        self.part_id = part_id
        self.part = part
        self.state = state
        self.args = args
        self.view = view
        self.answers = answers
        self.item = item
        self.domain = getattr(state, "domain", None)
        self.notes: List[Any] = []

    def note(self, x: Any) -> None:
        self.notes.append(x)

    def arg(self, key: str) -> Any:
        if not isinstance(self.args, dict) or key not in self.args:
            raise MissingArgument(f"the call has no argument [{key!r}]")
        return self.args[key]

    def need_view(self) -> Any:
        if self.view is None:
            raise MissingInput(f"{self.fact}: part {self.part_id!r} needs the message view (view=...)")
        return self.view

    def need_answers(self) -> Any:
        if self.answers is None:
            raise MissingInput(f"{self.fact}: part {self.part_id!r} needs the answers hook (answers=...)")
        return self.answers


def _bind(h: Helper, ctx: Context) -> Callable:
    def call(*a, **kw):
        return h.func(ctx, *a, **kw)
    call.__name__ = h.name
    return call


def compile_entry(entry: dict, name: str = "<fact>", kinds: Optional[Iterable[str]] = None) -> Dict[str, tuple]:
    """part id -> (code, info) for every part. Raises NotDefinedYet (expr null, or a name not registered yet) or
    LookupFormatError. Every part is checked before any part runs, so an unfinished fact never runs. In a fact with
    for_each the parts may read ITEM."""
    values = (ITEM,) if entry.get("for_each") else ()
    out = {}
    for pid, part in entry["parts"].items():
        expr = part.get("expr")
        if expr is None:
            raise NotDefinedYet(f"{name}: part {pid!r} ({part.get('source')}) has no expression yet "
                                f"(p6: database, event, arguments; p7: structure; p8: question)")
        try:
            code, info = compile_expr(expr, kinds, values)
        except UnknownName as e:
            raise NotDefinedYet(f"{name}: part {pid!r} uses {e.name!r}, which is not registered (yet): {e}") from None
        bad = helper_use_problems(part.get("source"), info["helpers"])
        if bad:
            raise L.LookupFormatError(f"{name}: part {pid!r}: " + "; ".join(bad))
        out[pid] = (code, info)
    return out


_NO_ITEM = object()


def effective_who(entry: dict, part: dict) -> Optional[str]:
    """The part's own `who` when it has one, else the fact's."""
    return part.get("who") or entry.get("who")


def _blank_part(entry: dict, part: dict) -> dict:
    return {"value": None, "source": part["source"], "who": effective_who(entry, part), "reads": [],
            "how": "not_run", "detail": None, "notes": []}


def _run_part(name: str, pid: str, entry: dict, code: Any, info: dict, state: Any, wargs: dict, item: Any,
              view: Any, answers: Any, recording: type) -> dict:
    """One part, once: {"value", "source", "who", "reads", "how", "detail", "notes"} and maybe "problem"."""
    part = entry["parts"][pid]
    rs = recording(state)
    ctx = Context(name, pid, part, rs, wargs, view, answers, None if item is _NO_ITEM else item)
    env = L.bindings(rs, wargs)
    env[_GET] = _get
    env[_SUB] = _sub
    if item is not _NO_ITEM:
        env[ITEM] = item
    for h in info["helpers"]:
        env[h] = _bind(_REGISTRY[h], ctx)
    out = dict(_blank_part(entry, part), reads=rs.reads, how="value", notes=ctx.notes)
    try:
        raw = eval(code, env)                     # noqa: S307 - validated expression, no builtins
    except MissingObject as e:
        out.update(value=bool(part.get("if_nonexistent") or False), how="nonexistent", detail=str(e))
        return out
    except UseBlockingValue as e:
        out.update(how="problem", detail=e.detail or str(e), problem=e.kind)
        return out
    except (KeyError, IndexError) as e:          # inside a helper or a built-in: a missing field
        out.update(how="problem", detail=f"{type(e).__name__}: {e}", problem="missing_field")
        return out
    except TypeError as e:
        out.update(how="problem", detail=f"TypeError: {e}", problem="type_error")
        return out
    if raw is not True and raw is not False:
        raise FactEvalError(f"{name}: part {pid!r} gave a {type(raw).__name__} ({str(raw)[:80]}), not True or False "
                            f"(two values only)")
    out["value"] = raw
    return out


SOFT_KIND = "unclear"        # the problem kind that gives only its question part the blocking value (p12 fix)


class _Pass:
    """The parts of a fact, evaluated once (once per item in a for_each fact)."""

    def __init__(self, name: str, entry: dict, compiled: Dict[str, tuple], tree: tuple, state: Any, wargs: dict,
                 item: Any, index: Optional[int], view: Any, answers: Any, recording: type):
        self.name, self.entry, self.compiled, self.tree = name, entry, compiled, tree
        self.state, self.wargs, self.item, self.index = state, wargs, item, index
        self.view, self.answers, self.recording = view, answers, recording
        self.parts = {pid: _blank_part(entry, p) for pid, p in entry["parts"].items()}
        self.problems: List[dict] = []
        self.known: Dict[str, bool] = {}
        self.soft: List[str] = []                # question parts whose "unclear" gave them the blocking value
        self.value: Optional[bool] = None

    def run(self, pid: str) -> None:
        code, info = self.compiled[pid]
        r = _run_part(self.name, pid, self.entry, code, info, self.state, self.wargs, self.item, self.view,
                      self.answers, self.recording)
        kind = r.pop("problem", None)
        if kind is not None:
            self.problems.append({"kind": kind, "part": pid, "item": self.index, "detail": r["detail"]})
            if kind == SOFT_KIND and self.entry["parts"][pid]["source"] == "question":
                self.known[pid] = bool(self.entry["blocking_value"])      # this part only (p12 fix)
                self.soft.append(pid)
        else:
            self.known[pid] = r["value"]
        self.parts[pid] = r

    def hard_problems(self) -> List[dict]:
        """The problems that give the whole fact its blocking value (all but a question part's unclear)."""
        return [x for x in self.problems if x["part"] not in self.soft]

    def rests_on_soft(self) -> bool:
        """True when the value would differ (or be undecided) with any soft part's other value."""
        for pid in self.soft:
            flipped = dict(self.known, **{pid: not self.known[pid]})
            if combine_value(self.tree, flipped) != self.value:
                return True
        return False

    def run_code(self) -> None:
        """Every code part (database, event, arguments, structure)."""
        for pid, p in self.entry["parts"].items():
            if p["source"] != "question":
                self.run(pid)

    def resolve(self) -> Optional[bool]:
        """Run the question parts that combine still needs, one at a time; the value, or None after a problem that
        gives the whole fact its blocking value (a question part's unclear gives only that part the blocking value)."""
        order = combine_ids(self.tree)
        while not self.hard_problems():
            v = combine_value(self.tree, self.known)
            if v is not None:
                self.value = v
                return v
            unknown = [p for p in order if p not in self.known]
            pick = next((p for p in unknown if combine_value(self.tree, dict(self.known, **{p: True}))
                         != combine_value(self.tree, dict(self.known, **{p: False}))), unknown[0])
            self.run(pick)
        return None

    def mark_not_needed(self) -> None:
        for r in self.parts.values():
            if r["how"] == "not_run":
                r["how"] = "not_needed"


def _arg_path(wargs: Any, path: str) -> Any:
    x = wargs
    for key in path.split("."):
        x = _sub(x, key)
    return x


def _result(name: str, entry: dict, value: bool, how: str, parts: dict, items: Optional[list],
            deciding: Optional[int], passes: Sequence[_Pass], problems: List[dict],
            ignored: Optional[List[dict]] = None) -> dict:
    reads: List[dict] = []
    notes: List[dict] = []
    for p in passes:
        for pid, r in p.parts.items():
            for x in r["reads"]:
                if x not in reads:
                    reads.append(x)
            notes += [{"part": pid, "item": p.index, "note": n} for n in r["notes"]]
    return {
        "fact": name,
        "value": bool(value),
        "source": list(entry.get("sources") or []),
        "how": how,
        "parts": parts,
        "items": items,
        "deciding_item": deciding,
        "evidence": {"text": entry.get("evidence"), "notes": notes},
        "reads": reads,
        "problems": problems,
        "problems_ignored": list(ignored or []),
        "blocking_value": entry["blocking_value"],
    }


def evaluate(entry: dict, state: Any, args: Optional[dict] = None, view: Any = None, answers: Any = None, *,
             name: Optional[str] = None) -> dict:
    """The value of one fact (an entry of a fact file) on a State (state.py) for the pending call's arguments
    (`args`; None: the state's pending call). See the module text for the result and the rules."""
    from state_tracker.replay import RecordingState      # frozen; imported here so validate() needs no replay

    name = name or "<fact>"
    blocking = entry.get("blocking_value")
    if not isinstance(blocking, bool):
        raise ValueError(f"{name}: blocking_value must be true or false")
    kinds = getattr(state, "_kinds", None)
    compiled = compile_entry(entry, name, sorted(kinds) if kinds else None)
    tree = parse_combine(entry["combine"])
    if args is None:
        args = (getattr(state, "pending", None) or {}).get("args") or {}
    wargs = wrap_args(args)
    fe = entry.get("for_each")
    problems: List[dict] = []
    passes: List[_Pass] = []

    def new(item: Any, index: Optional[int]) -> _Pass:
        return _Pass(name, entry, compiled, tree, state, wargs, item, index, view, answers, RecordingState)

    if fe:
        try:
            items = _arg_path(wargs, fe["arg"])
        except (MissingArgument, MissingObject):
            problems.append({"kind": "missing_argument", "part": None, "item": None,
                             "detail": f"for_each: the call has no list argument {fe['arg']!r}"})
        except TypeError as e:                           # a step of the path is not an object
            problems.append({"kind": "type_error", "part": None, "item": None,
                             "detail": f"for_each: argument path {fe['arg']!r}: {e}"})
        else:
            if isinstance(items, list):
                passes = [new(x, i) for i, x in enumerate(items)]
            else:
                problems.append({"kind": "type_error", "part": None, "item": None,
                                 "detail": f"for_each: argument {fe['arg']!r} is a {type(items).__name__}, not a list"})
    else:
        passes = [new(_NO_ITEM, None)]
    for p in passes:                                     # every code part of every item
        p.run_code()
        problems += p.problems
    value: Optional[bool] = None
    deciding: Optional[_Pass] = None
    if problems:
        deciding = next((p for p in passes if p.problems), None)
    elif not passes:                                     # for_each over an empty list
        value = bool(fe["if_empty"])
    else:
        value = True
        for p in passes:                                 # the questions, item by item, while they matter
            deciding = p
            v = p.resolve()
            problems += p.problems
            if v is None:
                break
            if v is False:
                value = False
                break
        if not any(p.hard_problems() for p in passes):
            for p in passes:
                p.mark_not_needed()
    hard = [x for x in problems if not any(x in p.problems and x["part"] in p.soft for p in passes)]
    ignored: List[dict] = []
    if hard:
        value, how = blocking, "blocking_value"
    elif problems and any(p.value is not None and p.rests_on_soft() for p in passes
                          if p is deciding or value is True):
        how = "blocking_value"           # the value rests on a question part's unclear answer: it is the blocking value
    elif problems:                       # the other branch decided: the unclear answers did not matter (p12 fix)
        how, ignored, problems = "combine", problems, []
    else:
        how = "combine"
    parts = deciding.parts if deciding is not None else {}
    items_out = [{"index": p.index, "value": p.value, "parts": p.parts} for p in passes] if fe else None
    return _result(name, entry, value, how, parts, items_out, deciding.index if (fe and deciding) else None, passes,
                   problems, ignored)


def blocking_result(entry: dict, kind: str, detail: str = "", *, name: Optional[str] = None) -> dict:
    """The result shape of evaluate() for a fact that takes its blocking value because of an error found outside the
    evaluator (p9: a replay mismatch, a parse problem). The problem is recorded; no part runs."""
    name = name or "<fact>"
    if not isinstance(entry.get("blocking_value"), bool):
        raise ValueError(f"{name}: blocking_value must be true or false")
    parts = {pid: _blank_part(entry, p) for pid, p in entry["parts"].items()}
    return _result(name, entry, entry["blocking_value"], "blocking_value", parts,
                   [] if entry.get("for_each") else None, None, [],
                   [{"kind": kind, "part": None, "item": None, "detail": detail}])


# ----------------------------------------------------------------------------------------------- the validator

def facts_path(domain: str) -> str:
    return os.path.join(FACTS_DIR, f"facts_v3_{domain}.json")


def rule_table_path(domain: str) -> str:
    return os.path.join(RULE_TABLE_DIR, f"rule_table_{domain}.json")


def _load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_facts(domain: str, path: Optional[str] = None) -> dict:
    return _load_json(path or facts_path(domain))


def _rule_key(rid: Any) -> tuple:
    s = str(rid)
    return (0, int(s), "") if s.isdigit() else (1, 0, s)


def fact_rules(rule_table: dict) -> Dict[str, dict]:
    """fact -> {"rules": rule ids (sorted), "blocking": the blocking values over those rules (sorted)}."""
    out: Dict[str, dict] = {}
    for r in rule_table["rules"]:
        for f in r["facts"]:
            e = out.setdefault(f, {"rules": [], "blocking": set()})
            e["rules"].append(str(r["id"]))
            e["blocking"].update(r["blocking_values"][f])
    return {f: {"rules": sorted(e["rules"], key=_rule_key), "blocking": sorted(e["blocking"])}
            for f, e in out.items()}


def _text(x: Any) -> bool:
    return isinstance(x, str) and bool(x.strip())


def validate_part(fact: str, pid: str, part: Any, fact_sources: Sequence[str],
                  kinds: Optional[Iterable[str]] = None, values: Iterable[str] = ()) -> List[str]:
    """Problems with one part (empty list: fine). values: extra value names the expression may read (ITEM in a
    for_each fact)."""
    pre = f"{fact}: part {pid!r}"
    if not isinstance(part, dict):
        return [f"{pre}: not an object"]
    p = [f"{pre}: missing field {f!r}" for f in PART_FIELDS if f not in part]
    p += [f"{pre}: unknown field {f!r}" for f in part if f not in PART_FIELDS + PART_OPTIONAL]
    src = part.get("source")
    if "source" in part:
        if src not in SOURCES:
            p.append(f"{pre}: source must be one of {SOURCES}, not {src!r}")
        elif isinstance(fact_sources, list) and src not in fact_sources:
            p.append(f"{pre}: source {src!r} is not in the fact's sources {fact_sources}")
    if "plain" in part and not _text(part["plain"]):
        p.append(f"{pre}: plain must be a non-empty text")
    expr = part.get("expr")
    if "expr" in part and expr is not None:
        if not _text(expr):
            p.append(f"{pre}: expr must be null or a non-empty text")
        else:
            try:
                info = validate_expr(expr, kinds, values)
            except UnknownName as e:
                hint = " (item: only in a fact with for_each)" if e.name == ITEM else ""
                p.append(f"{pre}: expr: unknown name {e.name!r} (not in the lookup format and not registered){hint}")
            except L.LookupFormatError as e:
                p.append(f"{pre}: expr: {e}")
            else:
                if src in SOURCES:
                    p += [f"{pre}: expr: {x}" for x in helper_use_problems(src, info["helpers"])]
    q = part.get("question")
    if "question" in part:
        if q is not None and not (isinstance(q, str) and _K_ID.match(q)):
            p.append(f"{pre}: question must be null or a question id K<n>, not {q!r}")
        if src == "question" and q is None:
            p.append(f"{pre}: a question part must name its question (K<n>)")
        if src != "question" and q is not None:
            p.append(f"{pre}: only a question part names a question (source is {src!r})")
    if "about" in part and part["about"] is not None and not _text(part["about"]):
        p.append(f"{pre}: about must be null or a non-empty text")
    if "if_nonexistent" in part and part["if_nonexistent"] is not None and not isinstance(part["if_nonexistent"], bool):
        p.append(f"{pre}: if_nonexistent must be null, true or false")
    if "who" in part and part["who"] is not None and part["who"] not in WHO:
        p.append(f"{pre}: who must be null or one of {WHO}, not {part['who']!r}")
    return p


def _reads_item(part: Any, kinds: Optional[Iterable[str]]) -> bool:
    """A part whose expression reads ITEM. A part with expr null counts (its expression is not written yet)."""
    if not isinstance(part, dict) or part.get("expr") is None:
        return True
    try:
        return ITEM in validate_expr(part["expr"], kinds, (ITEM,))["values"]
    except L.LookupFormatError:
        return True                                      # reported by validate_part


def validate_entry(fact: str, e: Any, sentences: Iterable[str], rule_info: Optional[dict],
                   kinds: Optional[Iterable[str]] = None) -> List[str]:
    """Problems with one fact entry (empty list: fine). rule_info: fact_rules(rule table)[fact] (None: the fact is in
    no rule)."""
    if not isinstance(e, dict):
        return [f"{fact}: the entry is not an object"]
    p: List[str] = []

    def bad(msg: str) -> None:
        p.append(f"{fact}: {msg}")

    for f in FACT_FIELDS:
        if f not in e:
            bad(f"missing field {f!r}")
    for f in e:
        if f not in FACT_FIELDS + FACT_OPTIONAL:
            bad(f"unknown field {f!r}")
    fe = e.get("for_each")
    values = (ITEM,) if fe else ()
    if fe is not None:
        if not isinstance(fe, dict):
            bad('for_each must be null or {"arg": "<argument path>", "if_empty": true | false}')
        else:
            for f in FOR_EACH_FIELDS:
                if f not in fe:
                    bad(f"for_each: missing field {f!r}")
            for f in fe:
                if f not in FOR_EACH_FIELDS:
                    bad(f"for_each: unknown field {f!r}")
            if "arg" in fe and not (isinstance(fe["arg"], str) and _ARG_PATH.match(fe["arg"])):
                bad(f"for_each: arg must be an argument path (names joined by '.'), not {fe['arg']!r}")
            if "if_empty" in fe and not isinstance(fe["if_empty"], bool):
                bad("for_each: if_empty must be true or false")
    sources = e.get("sources")
    if "sources" in e:
        if not isinstance(sources, list) or not sources:
            bad("sources must be a non-empty list")
            sources = None
        else:
            for s in sources:
                if s not in SOURCES:
                    bad(f"sources: {s!r} is not one of {SOURCES}")
            if len(set(map(str, sources))) != len(sources):
                bad("sources: a source is listed twice")
    parts = e.get("parts")
    if "parts" in e:
        if not isinstance(parts, dict) or not parts:
            bad("parts must be a non-empty object")
            parts = None
        else:
            for pid, part in parts.items():
                if not _IDENT.match(pid) or pid.upper() in COMBINE_WORDS:
                    bad(f"part id {pid!r}: must be a plain name (letters, digits, '_'), not AND / OR / NOT")
                p += validate_part(fact, pid, part, sources if isinstance(sources, list) else None, kinds, values)
            if fe and not any(_reads_item(part, kinds) for part in parts.values()):
                bad("for_each is set, but no part expression reads item")
            used = {part.get("source") for part in parts.values() if isinstance(part, dict)}
            for s in sources or []:
                if s in SOURCES and s not in used:
                    bad(f"source {s!r} is in sources, but no part has it")
    if "combine" in e:
        try:
            ids = combine_ids(parse_combine(e["combine"]))
        except CombineError as x:
            bad(f"combine: {x}")
        else:
            if isinstance(parts, dict):
                for i in ids:
                    if i not in parts:
                        bad(f"combine uses {i!r}, which is not a declared part")
                for i in parts:
                    if i not in ids:
                        bad(f"part {i!r} is declared but combine does not use it")
    if "start" in e and e["start"] is not False:
        bad(f"start must be false, not {e['start']!r}")
    for f in TEXT_FIELDS:
        if f in e and not _text(e[f]):
            bad(f"{f} must be a non-empty text")
    if "who" in e and e["who"] not in WHO:
        bad(f"who must be one of {WHO}, not {e['who']!r}")
    sent = set(sentences)
    if "policy" in e:
        pol = e["policy"]
        if not isinstance(pol, list) or not pol:
            bad("policy must be a non-empty list of sentence ids (S<n>)")
        else:
            for s in pol:
                if not (isinstance(s, str) and _S_ID.match(s)):
                    bad(f"policy: {s!r} is not a sentence id S<n>")
                elif s not in sent:
                    bad(f"policy: {s} is not a sentence of the rule set")
            if len(set(map(str, pol))) != len(pol):
                bad("policy: a sentence id is listed twice")
    want_rules = (rule_info or {}).get("rules", [])
    if rule_info is None:
        bad("the fact is in no rule of the rule table")
    if "rules" in e:
        rl = e["rules"]
        if not isinstance(rl, list) or not all(isinstance(r, str) for r in rl):
            bad("rules must be a list of rule ids (texts)")
        else:
            if len(set(rl)) != len(rl):
                bad("rules: a rule id is listed twice")
            miss = sorted(set(want_rules) - set(rl), key=_rule_key)
            extra = sorted(set(rl) - set(want_rules), key=_rule_key)
            if miss:
                bad(f"rules: missing {miss} (rule table: {want_rules})")
            if extra:
                bad(f"rules: not in the rule table for this fact: {extra} (rule table: {want_rules})")
    if "blocking_value" in e:
        bv = e["blocking_value"]
        if not isinstance(bv, bool):
            bad("blocking_value must be true or false")
        elif rule_info is not None:
            table = rule_info["blocking"]
            if len(table) != 1:
                bad(f"the rule table gives blocking values {table} for this fact, not one value")
            elif bv != table[0]:
                bad(f"blocking_value is {str(bv).lower()}, the rule table says {str(table[0]).lower()}")
    if "reading" in e and e["reading"] is not None:
        r = e["reading"]
        if not isinstance(r, dict):
            bad("reading must be null or {q, default, other}")
        else:
            for f in READING_FIELDS:
                if f not in r:
                    bad(f"reading: missing field {f!r}")
            for f in r:
                if f not in READING_FIELDS:
                    bad(f"reading: unknown field {f!r}")
            if "q" in r and r["q"] not in READING_QS:
                bad(f"reading: q must be one of {READING_QS}, not {r['q']!r}")
            for f in ("default", "other"):
                if f in r and not _text(r[f]):
                    bad(f"reading: {f} must be a non-empty text")
    if "fixed" in e:
        fx = e["fixed"]
        if not isinstance(fx, list) or not all(_text(x) for x in fx):
            bad("fixed must be a list of non-empty texts")
    return p


def validate(doc: Any, domain: str, *, rule_set: Optional[dict] = None, rule_table: Optional[dict] = None,
             kinds: Optional[Iterable[str]] = None, partial: bool = False) -> List[str]:
    """Problems with a fact file (empty list: fine). Defaults: the frozen rule set of the domain, its rule table
    (output/eval_v3/rule_table_<domain>.json) and the domain's kinds (tool_table.json). partial=True: a part of a split
    file, so not every fact must be there (an unknown fact is still a problem)."""
    if not isinstance(doc, dict):
        return ["the file is not a JSON object"]
    rule_set = _load_json(paths.rule_set_path(domain)) if rule_set is None else rule_set
    rule_table = _load_json(rule_table_path(domain)) if rule_table is None else rule_table
    kinds = L.domain_kinds(domain) if kinds is None else list(kinds)
    p: List[str] = []
    for f in TOP_FIELDS:
        if f not in doc:
            p.append(f"missing top field {f!r}")
    for f in doc:
        if f not in TOP_FIELDS + TOP_OPTIONAL:
            p.append(f"unknown top field {f!r}")
    if "_about" in doc and not _text(doc["_about"]):
        p.append("_about must be a non-empty text")
    if "domain" in doc and doc["domain"] != domain:
        p.append(f"domain is {doc['domain']!r}, expected {domain!r}")
    if "schema_version" in doc and (type(doc["schema_version"]) is not int or doc["schema_version"] != SCHEMA_VERSION):
        p.append(f"schema_version must be {SCHEMA_VERSION}, not {doc['schema_version']!r}")
    facts = doc.get("facts")
    if "facts" in doc and not isinstance(facts, dict):
        p.append("facts must be an object")
        facts = None
    facts = facts or {}
    names = list(rule_set["predicates"])
    info = fact_rules(rule_table)
    sentences = [s["id"] for s in rule_set.get("sentences", [])]
    if not partial:
        p += [f"missing fact {n!r} (in the rule set)" for n in names if n not in facts]
    p += [f"unknown fact {n!r} (not in the rule set)" for n in facts if n not in names]
    for n, e in facts.items():
        if n in names:
            p += validate_entry(n, e, sentences, info.get(n), kinds)
    return p


def summary(doc: dict) -> dict:
    """Counts for a report: facts, parts per source, expressions written / still null, question ids, helpers used."""
    facts = doc.get("facts") or {}
    by_source: collections.Counter = collections.Counter()
    written: collections.Counter = collections.Counter()
    questions: collections.Counter = collections.Counter()
    part_who = 0
    for e in facts.values():
        for part in ((e or {}).get("parts") or {}).values():
            if not isinstance(part, dict):
                continue
            s = part.get("source")
            by_source[s] += 1
            part_who += part.get("who") is not None
            if part.get("expr") is not None:
                written[s] += 1
            if part.get("question"):
                questions[part["question"]] += 1
    return {"facts": len(facts), "parts": sum(by_source.values()), "parts_by_source": dict(by_source),
            "expr_written_by_source": dict(written), "expr_written": sum(written.values()),
            "questions": dict(sorted(questions.items(), key=lambda kv: int(kv[0][1:]) if kv[0][1:].isdigit() else 0)),
            "parts_with_own_who": part_who,
            "for_each_facts": sorted(n for n, e in facts.items() if isinstance(e, dict) and e.get("for_each")),
            "registered_helpers": sorted(_REGISTRY)}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -B -m state_tracker.v3.facts_format_v3",
                                 description="Check the v3 fact files (state_tracker/v3/facts_v3_<domain>.json).")
    ap.add_argument("--check", nargs="+", required=True, choices=paths.DOMAINS, metavar="DOMAIN")
    ap.add_argument("--file", help="check this file instead of the domain's fact file (one domain only)")
    ap.add_argument("--partial", action="store_true", help="not every fact must be there (a part of a split file)")
    a = ap.parse_args(argv)
    from state_tracker.v3.frozen import check_manifest
    check_manifest()
    if a.file and len(a.check) != 1:
        ap.error("--file needs exactly one domain")
    n_problems = 0
    for d in a.check:
        path = a.file or facts_path(d)
        if not os.path.isfile(path):
            print(f"{d}: no fact file: {path}")
            n_problems += 1
            continue
        try:
            doc = _load_json(path)
        except ValueError as e:
            print(f"{d}: {path} is not JSON: {e}")
            n_problems += 1
            continue
        problems = validate(doc, d, partial=a.partial)
        s = summary(doc) if isinstance(doc, dict) else {}
        print(f"{d}: {os.path.relpath(path, paths.PC_DIR)}: {len(problems)} problems; "
              + json.dumps(s, sort_keys=True))
        for x in problems:
            print("  PROBLEM:", x)
        n_problems += len(problems)
    return 1 if n_problems else 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.exit(main())
