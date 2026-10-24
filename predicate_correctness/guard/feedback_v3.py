"""Tracker v3, part 10: the block message built from the rule (docs/planning/tracker_v3/p10.md). No LLM call.

When the v3 guard blocks, the agent is told which fact of the rule is not met, the evidence, and what makes it true.
No hand-written text per fact. The text comes from:
  - the rule table (output/eval_v3/rule_table_<domain>.json, p2): the facts of the rule and every smallest way to make
    it hold (flip sets);
  - the policy sentences the rule cites, quoted from the rule set;
  - the fact definitions (state_tracker/v3/facts_v3_<domain>.json, p5) and the evaluator's results (p6-p8): the parts,
    their sources, values and `who`, the database values the parts read, the missing events.
Never from the rule set's predicate descriptions (the old "an earlier tool output shows ..." framing), never from a
judge's text.

    from guard import feedback_v3 as FB
    text = FB.build_message(domain, tool, args, violated_rules, facts, state, view, rule_table, rule_set)   # rule
    text = FB.build_simple(domain, tool, args, violated_rules, facts, state, view, rule_table, rule_set)    # simple
    text = FB.build("rule" | "simple", domain, tool, ...)
    plan = FB.explain(domain, tool, ...)          # the structure behind the rule message (the checks and tests)

Inputs: violated_rules = TGR's list ({"rule_id", ...}) or rule ids; facts = {fact: the evaluator's result
(facts_format_v3.evaluate), or for a stand-in unknown a dict with value None}; state = the State of the check
(state_tracker/state.py); view = the message view (state_tracker/v3/message_view.py build_view); rule_table and
rule_set of the domain. Bad input raises MessageInputError (a clear error, never a wrong message); the caller (p9's
_feedback) then sends TGR's own message and counts it.

The message (messages = rule):
    BLOCKED by policy guardrail. <TGR's own first line, unchanged>
    Policy: "<the sentences the violated rules cite>"
    Not met:
    - <fact in words>: <the value that breaks the rule: false, or true for a negated fact; a stand-in unknown is
      "not established">
      - <evidence of the parts that break it: the missing event, the database values read, the call's arguments>
    What makes it true:
    1. <advice by the part's who>
    <closing line>

Not established: a fact with value None (p9's stand-in unknown), a fact p9's lazy evaluation skipped (how
"lazy_skip": no rule needed it, so it took its blocking value), a fact with an "unclear" answer, and a fact that took
its blocking value with no part value (a state or fact error) are shown as "not established".

Ways. For each violated rule, the rule table row of the current values (a fact that is not established takes its
blocking value) gives the flip sets. For each fact of a flip set, the parts that must change come from the fact's `combine` and its
parts' values (a part that did not run takes the value that keeps the fact where it is). The `who` of a part (p5 rule
6): its own `who`; else `none` for a database or arguments part (p10: "none (database, arguments)"); else the fact's.
  - a part-way is "fixable" when every part in it is agent or ask; "user_only" when one is user_only (and none is
    none); "none" when one is none;
  - a fact is fixable when one of its part-ways is; else user_only when one of its part-ways needs a user_only part;
    else none;
  - a flip set is "excluded" when one of its facts is user_only (a user_only fact the user has not given: never
    offered, never named); "fixable" when all its facts are; else "not_possible".
Every flip set that is not excluded is named. A rule with no named flip set gets the user_only line (a statement,
not a step).

Advice (one line per fact, plus one line per look-up):
  agent, event part  "Do this step first: look it up with <tool> (<key> <value>). Then try again." / for an event of
                     several tools: "call <tool> (<its required arguments>) or ... with details the user gives you"
  agent, other part  "Do this step first, so that this becomes true: <fact>. Then try again." (a negated fact:
                     "Change your call / message so that this is no longer true: <fact>.")
  ask                "Ask the user (the policy tells you to): <fact>. If the user says yes, try again. If the user
                     says no, do not do it." After a strict no: "The user said no ("<their words>"). Do not do it."
  user_only          "This depends only on what the user says (<fact>). Do not lead the user to say it. Without it,
                     this action is not allowed."
  none               "Not possible with these arguments: <fact> is <value>." (the value that fails is in Not met)
Closing: "Do not repeat the same call as it stands." (a reply: "Do not send the same message as it stands.") when a
violated rule has no fixable flip set, or after a strict no (the user's latest message, message_view.is_strict_no);
else "When this is done, call <tool> again." (a reply: "When this is done, send your message again.").

Safety: database values are shown only after login (`me`, p7) and only from records of `me` or catalog records
(products, flights); each such line is also passed through the info classes (p7; user_data_values with owner `me`)
and left out if they find user data there. Before login no database value is shown. The call's own arguments, the
event log and the user's own words may be shown. No judge text is read.

The simple version (messages = simple): TGR's own message (method_tgr/feedback.py of the runner copy, unchanged) for
the same values, without evidence (no judge text), without its closing "violated ... do not repeat" line, and without
the "What to do:" heading when nothing is left under it.

Standard library only (plus the runner copy through guard/runner_path.py). No LLM call, no network. Imports no
gold code and no scoring module.
"""
from __future__ import annotations

import ast
import copy
import itertools
import json
import os
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "guard"

from guard import runner_path                                            # noqa: E402

runner_path.setup()

from method_tgr import feedback as tgr_feedback                          # noqa: E402  (runner copy, unchanged)
from method_tgr.rules import to_aspm                                     # noqa: E402  (runner copy, unchanged)

from state_tracker import tau_copy                                       # noqa: E402
from state_tracker.v3 import facts_format_v3 as F                        # noqa: E402
from state_tracker.v3 import code_helpers                                # noqa: E402,F401  (registers names)
from state_tracker.v3 import message_view as MV                          # noqa: E402  (registers names)
from state_tracker.v3 import info_classes as IC                          # noqa: E402
from state_tracker.v3 import questions as _questions                     # noqa: E402,F401  (registers names)

VERSION = 1
MESSAGES = ("rule", "simple")
WHO = ("agent", "ask", "user_only", "none")
VALUE_SOURCES = ("database", "arguments")        # a part of these sources without its own who is `none`
CATALOG_KINDS = ("product", "variant", "flight", "airport", "product_type")
MAX_RECORDS = 3                                   # database records shown per part (the last ones read)
MAX_FIELDS = 4                                    # fields shown per record (the last ones read)
MAX_ARGS = 3                                      # call arguments shown per part
MAX_ARG_CHARS = 100
MAX_QUOTE_CHARS = 160
# results the guard did not establish (shown as "not established"; the rule table reads their blocking value):
# p9's lazy skip (no rule needed the fact, so it took its blocking value) and a stand-in unknown
NOT_ESTABLISHED_HOW = ("lazy_skip", "saved_unknown")
PART_RAN = ("value", "nonexistent", "problem")    # a part's "how" after it ran (facts_format_v3)
HIDDEN_BEFORE_LOGIN = "(database values are not shown before the user is identified)"
HIDDEN_OTHER = "(a record that does not belong to the identified user is not shown)"

FIRST_LINE_PREFIX = "BLOCKED by policy guardrail."
NOT_MET = "Not met:"
WHAT = "What makes it true:"
ANY_ONE = "Any one of these is enough:"


class MessageInputError(ValueError):
    """The inputs cannot give a right message (a missing fact, a rule that is not in the table, ...)."""


# ----------------------------------------------------------------------------------------------- small helpers

def words(name: str) -> str:
    """A fact name in words: underscores become spaces."""
    return str(name).replace("_", " ").strip()


def shown_value(v: Optional[bool]) -> str:
    return "not established" if v is None else ("true" if v else "false")


def jtext(x: Any) -> str:
    """A value as JSON text (strings in double quotes)."""
    return json.dumps(x, ensure_ascii=False, sort_keys=True)


def path_text(path: Sequence[Any]) -> str:
    """("payment_history", 0, "payment_method_id") -> payment_history[0].payment_method_id"""
    out = ""
    for k in path:
        if isinstance(k, int) and not isinstance(k, bool):
            out += f"[{k}]"
        else:
            out += ("." if out else "") + str(k)
    return out


def _rule_key(rid: Any) -> tuple:
    s = str(rid)
    return (0, int(s), "") if s.isdigit() else (1, 0, s)


_CACHE: Dict[Tuple[str, int], Tuple[Any, Any]] = {}


def _cached(kind: str, obj: Any, make) -> Any:
    """A value computed once per object (the object itself is kept, so its id is not reused)."""
    key = (kind, id(obj))
    hit = _CACHE.get(key)
    if hit is not None and hit[0] is obj:
        return hit[1]
    val = make(obj)
    _CACHE[key] = (obj, val)
    return val


def _aspm(rule_set: dict) -> Any:
    return _cached("aspm", rule_set, to_aspm)


def _table_index(rule_table: dict) -> Dict[str, dict]:
    def make(t):
        out = {}
        for e in t.get("rules") or []:
            rows = {}
            for row in e["rows"]:
                rows[(row["action"], tuple(bool(row["values"][f]) for f in e["facts"]))] = row
            out[str(e["id"])] = {"entry": e, "rows": rows}
        return out
    return _cached("table", rule_table, make)


def _sentences(rule_set: dict) -> Dict[str, dict]:
    return _cached("sentences", rule_set, lambda rs: {s["id"]: s for s in rs.get("sentences") or []})


def _rules_by_id(rule_set: dict) -> Dict[str, dict]:
    return _cached("rules", rule_set, lambda rs: {str(r["id"]): r for r in rs.get("rules") or []})


_DEFS: Dict[str, dict] = {}


def fact_definitions(domain: str) -> Dict[str, dict]:
    """The fact entries of the domain's fact file (loaded once)."""
    if domain not in _DEFS:
        _DEFS[domain] = F.load_facts(domain)["facts"]
    return _DEFS[domain]


_SCHEMAS: Dict[str, Dict[str, dict]] = {}


def tool_schemas(domain: str) -> Dict[str, dict]:
    """tool name -> its τ-bench schema (get_info()["function"])."""
    if domain not in _SCHEMAS:
        _SCHEMAS[domain] = {t["function"]["name"]: t["function"] for t in tau_copy.tools_info(domain)}
    return _SCHEMAS[domain]


def advice_who(entry: dict, part: dict) -> str:
    """The who of a part for the advice (module text): its own; none for database / arguments; else the fact's."""
    if part.get("who"):
        return part["who"]
    if part.get("source") in VALUE_SOURCES:
        return "none"
    return entry.get("who") or "none"


# ----------------------------------------------------------------------------------------------- expressions

def _const(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return None


def _arg_key(node: ast.AST) -> Optional[str]:
    """'k' when the node is args['k']."""
    if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "args"
            and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str)):
        return node.slice.value
    return None


_EXPR_INFO: Dict[str, dict] = {}


def expr_info(expr: str) -> dict:
    """What an expression uses: event helper calls and top-level argument keys (cached by text)."""
    if expr in _EXPR_INFO:
        return _EXPR_INFO[expr]
    tree = ast.parse(expr, mode="eval")
    looked, events, keys = [], [], []
    for node in ast.walk(tree):
        k = _arg_key(node)
        if k is not None and k not in keys:
            keys.append(k)
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id == "looked_up" and len(node.args) == 3:
            tool, key = _const(node.args[0]), _const(node.args[1])
            if isinstance(tool, str) and isinstance(key, str):
                looked.append({"tool": tool, "key": key, "arg": _arg_key(node.args[2])})
        elif node.func.id == "events":
            kw = {x.arg: _const(x.value) for x in node.keywords}
            tools = kw.get("tool")
            tools = [tools] if isinstance(tools, str) else [t for t in (tools or []) if isinstance(t, str)]
            if tools:
                events.append({"tools": tools, "ok": kw.get("ok")})
    # ast.walk is breadth first; keep the keys in text order
    keys.sort(key=lambda k: expr.find(f"args['{k}']") if f"args['{k}']" in expr else len(expr))
    _EXPR_INFO[expr] = {"looked_up": looked, "events": events, "arg_keys": keys}
    return _EXPR_INFO[expr]


# ----------------------------------------------------------------------------------------------- traced reads

class _Log:
    def __init__(self) -> None:
        self.reads: List[dict] = []

    def add(self, entry: dict) -> None:
        self.reads.append(entry)


def _wrap(v: Any, log: _Log, kind: str, oid: Any, path: tuple) -> Any:
    if isinstance(v, dict) and not isinstance(v, _TDict):
        return _TDict(v, log, kind, oid, path)
    if isinstance(v, list) and not isinstance(v, _TList):
        return _TList(v, log, kind, oid, path)
    if not isinstance(v, (dict, list)):
        log.add({"op": "get", "kind": kind, "id": oid, "path": path, "value": v})
    return v


class _TDict(dict):
    """A database object that records which fields an expression reads (a shallow copy; nested objects are wrapped
    when read)."""

    def __init__(self, data: dict, log: _Log, kind: str, oid: Any, path: tuple):
        super().__init__(data)
        self._log, self._kind, self._oid, self._path = log, kind, oid, path

    def __getitem__(self, k: Any) -> Any:
        v = dict.__getitem__(self, k)
        return _wrap(v, self._log, self._kind, self._oid, self._path + (k,))

    def get(self, k: Any, default: Any = None) -> Any:
        if dict.__contains__(self, k):
            return self[k]
        self._log.add({"op": "has", "kind": self._kind, "id": self._oid, "path": self._path, "key": k,
                       "value": False})
        return default

    def __contains__(self, k: Any) -> bool:
        r = dict.__contains__(self, k)
        self._log.add({"op": "has", "kind": self._kind, "id": self._oid, "path": self._path, "key": k, "value": r})
        return r


class _TList(list):
    def __init__(self, data: list, log: _Log, kind: str, oid: Any, path: tuple):
        super().__init__(data)
        self._log, self._kind, self._oid, self._path = log, kind, oid, path

    def __getitem__(self, i: Any) -> Any:
        v = list.__getitem__(self, i)
        if isinstance(i, slice):
            return v
        if isinstance(i, int) and i < 0:
            i = len(self) + i
        return _wrap(v, self._log, self._kind, self._oid, self._path + (i,))

    def __iter__(self):
        for i in range(len(self)):
            yield _wrap(list.__getitem__(self, i), self._log, self._kind, self._oid, self._path + (i,))


class _TracedState:
    """The check's state; db_get gives objects that record their reads. Everything else is the state's own."""

    def __init__(self, state: Any, log: _Log):
        self._st = state
        self._log = log

    def __getattr__(self, name: str) -> Any:
        return getattr(self._st, name)

    def db_get(self, kind: str, oid: Any) -> Any:
        obj = self._st.db_get(kind, oid)
        if obj is None:
            self._log.add({"op": "missing", "kind": kind, "id": oid, "path": (), "value": None})
            return None
        return _wrap(obj, self._log, kind, oid, ())


def traced_reads(entry: dict, pid: str, state: Any, args: dict, view: Any, name: str) -> Tuple[Optional[bool], List[dict]]:
    """Re-run one database / arguments part on its own on the state, recording the database fields it reads.
    (its value, the reads). Only parts of these sources are re-run (no question is ever asked here)."""
    part = entry["parts"][pid]
    if part.get("source") not in VALUE_SOURCES:
        raise MessageInputError(f"{name}: part {pid} is not a database or arguments part")
    one = dict(entry)
    one["parts"] = {pid: part}
    one["combine"] = pid
    log = _Log()
    r = F.evaluate(one, _TracedState(state, log), copy.deepcopy(args), view=view, answers=None, name=name)
    v = None if r["problems"] else r["value"]
    return v, log.reads


# ----------------------------------------------------------------------------------------------- who is logged in

class _Ctx:
    def __init__(self, state: Any, view: Any, domain: str):
        self.state, self.view, self.domain = state, view, domain
        self.args: dict = {}
        self.notes: List[Any] = []

    def need_view(self):
        return self.view

    def note(self, x: Any) -> None:
        self.notes.append(x)


def logged_in_user(state: Any, view: Any, domain: str) -> Optional[str]:
    """`me` (p7): retail, the first worked find_user_id_* output; airline, the first user id the user typed that
    exists in the database."""
    return MV.me(_Ctx(state, view, domain))


def record_owner(state: Any, kind: str, oid: Any) -> Tuple[Optional[str], bool]:
    """(the user who owns a database record, the record is catalog data)."""
    if kind in CATALOG_KINDS:
        return None, True
    if kind == "user":
        return (oid if isinstance(oid, str) else None), False
    obj = state.db_get(kind, oid)
    if not isinstance(obj, dict):
        return None, False
    uid = obj.get("user_id")
    return (uid if isinstance(uid, str) else None), False


def strict_no(view: Any) -> Optional[dict]:
    """The user's latest message when it is a strict no (message_view.is_strict_no), else None."""
    refs = view.user_refs()
    if not refs:
        return None
    r = refs[-1]
    if not MV.is_strict_no(view.norm(r)):
        return None
    text = re.sub(r"\s+", " ", view.text(r)).strip()
    if len(text) > MAX_QUOTE_CHARS:
        text = text[:MAX_QUOTE_CHARS].rstrip() + " ..."
    return {"ref": r, "quote": text}


# ----------------------------------------------------------------------------------------------- the ways

def _smallest_sets(test, names: Sequence[str], values: Dict[str, bool]) -> List[List[str]]:
    found: List[set] = []
    for size in range(1, len(names) + 1):
        for subset in itertools.combinations(sorted(names), size):
            s = set(subset)
            if any(f <= s for f in found):
                continue
            v = dict(values)
            for n in subset:
                v[n] = not v[n]
            if test(v):
                found.append(s)
    return [sorted(s) for s in found]


def part_ways(entry: dict, result: dict, current: bool) -> Tuple[List[List[str]], Dict[str, bool]]:
    """The smallest sets of parts that, changed, turn the fact from `current` to the other value. A part without a
    value (not run, a problem, a stand-in unknown) takes the value that keeps the fact at `current`."""
    tree = F.parse_combine(entry["combine"])
    pids = list(entry["parts"])
    got = (result.get("parts") or {}) if isinstance(result, dict) else {}
    vals: Dict[str, bool] = {}
    for p in pids:
        v = (got.get(p) or {}).get("value")
        vals[p] = v if isinstance(v, bool) else current        # combine is monotone: keeps the fact where it is
    target = not current
    if F.combine_value(tree, vals) is not current:
        # the parts do not explain the value (e.g. a problem forced the blocking value): every part may matter
        vals = {p: current for p in pids}
        if F.combine_value(tree, vals) is not current:
            return [sorted(pids)], vals
    ways = _smallest_sets(lambda v: F.combine_value(tree, v) is target, pids, vals)
    return (ways or [sorted(pids)]), vals


def _status_of(whos: Iterable[str]) -> str:
    """A part-way that needs a user_only part is user_only (never offered, even if a none part is also needed)."""
    ws = set(whos)
    if "user_only" in ws:
        return "user_only"
    if "none" in ws:
        return "none"
    return "fixable"


def analyse_fact(domain: str, name: str, result: dict, current: bool, unknown: bool) -> dict:
    """The fact's part-ways and their status (module text)."""
    entry = fact_definitions(domain).get(name)
    if entry is None:
        raise MessageInputError(f"fact {name!r} is not in the {domain} fact definitions")
    ways, vals = part_ways(entry, result, current)
    out_ways = []
    for w in ways:
        whos = {p: advice_who(entry, entry["parts"][p]) for p in w}
        out_ways.append({"parts": w, "who": whos, "status": _status_of(whos.values())})
    stats = [w["status"] for w in out_ways]
    if "fixable" in stats:
        status = "fixable"
    elif "user_only" in stats:
        status = "user_only"
    else:
        status = "none"
    chosen = next(w for w in out_ways if w["status"] == status)
    return {"fact": name, "value": current, "unknown": unknown, "shown": "not established" if unknown else
            shown_value(current), "status": status, "part_ways": out_ways, "chosen": chosen, "part_values": vals,
            "fact_who": entry.get("who"), "sources": {p: entry["parts"][p]["source"] for p in entry["parts"]}}


# ----------------------------------------------------------------------------------------------- evidence

def _event_done(state: Any, tool: str, key: Optional[str], value: Any) -> bool:
    for e in state.events_where(tool=tool, ok=True):
        a = e.get("args")
        if key is None or (isinstance(a, dict) and key in a and a[key] == value):
            return True
    return False


def _arg_line(key: str, value: Any) -> Optional[dict]:
    if key == "content":
        return None                                   # a reply's own text is not repeated
    t = jtext(value)
    if len(t) <= MAX_ARG_CHARS:
        return {"type": "arg", "key": key, "value": value, "text": f"the call's {key} = {t}"}
    if isinstance(value, list):
        return {"type": "arg_len", "key": key, "n": len(value), "text": f"the call's {key}: {len(value)} entries"}
    return None


def _useful(reads: List[dict]) -> List[dict]:
    """The reads without noise:
      - a 'has' read that found the key is dropped (a later read of the field shows it, or it only checked that a
        field exists); a 'has' read that did not find it is kept;
      - a field whose value is only used to find another record or field (the id of another record read, or a key
        on the path of a read: a flight number, a date, the owner's user id) is dropped."""
    ids = {jtext(r["id"]) for r in reads}
    keys = set()
    for r in reads:
        keys.update(jtext(k) for k in r["path"] if isinstance(k, str))       # dict keys, not list positions
        if r["op"] == "has":
            keys.add(jtext(r["key"]))
    out = []
    for r in reads:
        if r["op"] == "has" and r["value"] is True:
            continue
        if r["op"] == "get" and not isinstance(r["value"], (dict, list)):
            v = jtext(r["value"])
            if (v in ids and v != jtext(r["id"])) or v in keys:
                continue
        out.append(r)
    return out


def _db_lines(reads: List[dict]) -> List[dict]:
    """The reads as lines: the last MAX_RECORDS records read, each with its last MAX_FIELDS fields."""
    order: List[tuple] = []
    by_rec: Dict[tuple, List[dict]] = {}
    for r in _useful(reads):
        rec = (r["kind"], jtext(r["id"]))
        if rec in by_rec:
            order.remove(rec)
        else:
            by_rec[rec] = []
        order.append(rec)
        if r["op"] == "get" and isinstance(r["value"], (dict, list)):
            continue
        by_rec[rec].append(r)
    lines = []
    for rec in order[-MAX_RECORDS:]:
        items: List[dict] = []
        seen = set()
        for r in reversed(by_rec[rec]):
            k = (r["op"], tuple(map(str, r["path"])), jtext(r.get("key")))
            if k in seen:
                continue
            seen.add(k)
            items.append(r)
            if len(items) >= MAX_FIELDS:
                break
        for r in reversed(items):
            oid = r["id"]
            label = f"{r['kind']} {oid}"
            if r["op"] == "missing":
                text = f"{label}: not in the database"
            elif r["op"] == "has":
                p = path_text(r["path"]) or "record"
                text = f"{label}: {p} has {jtext(r['key'])}: {'yes' if r['value'] else 'no'}"
            else:
                text = f"{label}: {path_text(r['path'])} = {jtext(r['value'])}"
            lines.append(dict(r, type="db", text=text, path=list(r["path"])))
    return lines


def fact_evidence(domain: str, an: dict, result: dict, tool: str, args: dict, state: Any, view: Any,
                  me: Optional[str], safety: dict) -> List[dict]:
    """The evidence lines of the parts in the fact's chosen part-way (module text: events, database values,
    arguments). Database values only after login and only of `me` or the catalog."""
    entry = fact_definitions(domain)[an["fact"]]
    lines: List[dict] = []
    hidden_login = hidden_other = False
    for pid in an["chosen"]["parts"]:
        part = entry["parts"][pid]
        src = part["source"]
        info = expr_info(part["expr"])
        if src == "event":
            for lu in info["looked_up"]:
                val = args.get(lu["arg"]) if lu["arg"] else None
                if lu["arg"] and lu["arg"] not in args:
                    continue
                if _event_done(state, lu["tool"], lu["key"], val):
                    continue
                lines.append({"type": "event", "tool": lu["tool"], "key": lu["key"], "value": val,
                              "text": f"{lu['tool']} with {lu['key']} {jtext(val)}: not done before this call"})
            for ev in info["events"]:
                if any(_event_done(state, t, None, None) for t in ev["tools"]):
                    continue
                lines.append({"type": "no_event", "tools": list(ev["tools"]),
                              "text": f"a {' or '.join(ev['tools'])} call that worked: none yet"})
            continue
        if src not in VALUE_SOURCES:
            continue
        v, reads = traced_reads(entry, pid, state, args, view, an["fact"])
        given = ((result.get("parts") or {}).get(pid) or {}).get("value")
        if isinstance(given, bool) and v is not given:
            safety["trace_mismatch"] += 1
            continue
        db = _db_lines(reads)
        shown_ids = {jtext(r["id"]) for r in reads}
        arg_lines = []
        for k in info["arg_keys"]:
            if k not in args or jtext(args[k]) in shown_ids:
                continue
            al = _arg_line(k, args[k])
            if al is not None:
                arg_lines.append(al)
        lines += arg_lines[:MAX_ARGS]
        for d in db:
            if me is None:
                hidden_login = True
                continue
            owner, catalog = record_owner(state, d["kind"], d["id"])
            if d["kind"] == "payment_method":
                owner, catalog = _payment_owner(state, d["id"]), False
            if not catalog and owner != me:
                hidden_other = True
                continue
            if IC.user_data_values(d["text"], view, state, owner_ok=[me]):
                hidden_other = True
                continue
            lines.append(d)
    if hidden_login:
        lines.append({"type": "hidden", "text": HIDDEN_BEFORE_LOGIN})
        safety["hidden_before_login"] += 1
    if hidden_other:
        lines.append({"type": "hidden", "text": HIDDEN_OTHER})
        safety["hidden_other"] += 1
    return lines


def _payment_owner(state: Any, pm_id: Any) -> Optional[str]:
    obj = state.db_get("payment_method", pm_id)
    uid = obj.get("user_id") if isinstance(obj, dict) else None
    return uid if isinstance(uid, str) else None


# ----------------------------------------------------------------------------------------------- advice

def _required_args(domain: str, tool: str) -> List[str]:
    fn = tool_schemas(domain).get(tool) or {}
    return list((fn.get("parameters") or {}).get("required") or [])


def fact_advice(domain: str, an: dict, args: dict, state: Any, kind: str, no: Optional[dict]) -> List[dict]:
    """The advice lines of one fact (module text)."""
    name, w = an["fact"], words(an["fact"])
    entry = fact_definitions(domain)[name]
    out: List[dict] = []
    if an["status"] == "none":
        what = "this message" if kind == "respond" else "these arguments"
        out.append({"who": "none", "type": "none", "fact": name,
                    "text": f"Not possible with {what}: {w} is {an['shown']}."})
        return out
    if an["status"] == "user_only":
        out.append({"who": "user_only", "type": "user_only", "fact": name,
                    "text": f"This depends only on what the user says ({w}). Do not lead the user to say it. "
                            f"Without it, this action is not allowed."})
        return out
    whos = set()
    for pid in an["chosen"]["parts"]:
        part = entry["parts"][pid]
        who = an["chosen"]["who"][pid]
        info = expr_info(part["expr"])
        if part["source"] == "event" and who == "agent" and (info["looked_up"] or info["events"]):
            for lu in info["looked_up"]:
                val = args.get(lu["arg"]) if lu["arg"] else None
                if (lu["arg"] and lu["arg"] not in args) or _event_done(state, lu["tool"], lu["key"], val):
                    continue
                out.append({"who": "agent", "type": "lookup", "fact": name, "tool": lu["tool"],
                            "args": {lu["key"]: val},
                            "text": f"Do this step first: look it up with {lu['tool']} ({lu['key']} {jtext(val)}). "
                                    f"Then try again."})
            for ev in info["events"]:
                if any(_event_done(state, t, None, None) for t in ev["tools"]):
                    continue
                calls = [f"{t} ({', '.join(_required_args(domain, t))})" for t in ev["tools"]]
                out.append({"who": "agent", "type": "user_args_call", "fact": name, "tools": list(ev["tools"]),
                            "arg_names": {t: _required_args(domain, t) for t in ev["tools"]},
                            "text": f"Do this step first: call {' or '.join(calls)} with details the user gives "
                                    f"you; the call must work. Then try again."})
            continue
        whos.add(who)
    if whos:
        thing = "message" if kind == "respond" else "call"
        if an["value"] is True:                      # a negated fact: it must become false
            if "ask" in whos and "agent" not in whos:
                text = f"Ask the user (the policy tells you to) about this, and change your {thing} so that this " \
                       f"is no longer true: {w}."
                typ, who = "ask", "ask"
            else:
                text = f"Change your {thing} so that this is no longer true: {w}."
                typ, who = "change", "agent"
        elif whos == {"agent"}:
            text = f"Do this step first, so that this becomes true: {w}. Then try again."
            typ, who = "step", "agent"
        else:
            first = "Do this step first, then ask" if "agent" in whos else "Ask"
            text = (f"{first} the user (the policy tells you to): {w}. If the user says yes, try again. "
                    f"If the user says no, do not do it.")
            typ, who = "ask", "ask"
        if typ == "ask" and no is not None:
            text = f"The user said no (\"{no['quote']}\"). Do not do it: {w}."
            typ = "ask_no"
        out.append({"who": who, "type": typ, "fact": name, "text": text, "whos": sorted(whos)})
    if not out:                                      # every event it needs already happened: the generic step
        out.append({"who": "agent", "type": "step", "fact": name, "whos": ["agent"],
                    "text": f"Do this step first, so that this becomes true: {w}. Then try again."})
    return out


# ----------------------------------------------------------------------------------------------- the plan

def _check_inputs(domain: str, tool: Any, args: Any, violated_rules: Any, facts: Any, state: Any, view: Any,
                  rule_table: Any, rule_set: Any) -> List[str]:
    if domain not in ("retail", "airline"):
        raise MessageInputError(f"unknown domain {domain!r}")
    if not isinstance(tool, str) or not tool:
        raise MessageInputError(f"tool must be a tool name or 'respond', not {tool!r}")
    if not isinstance(args, dict):
        raise MessageInputError(f"args must be a dict, not {type(args).__name__}")
    if not isinstance(facts, dict):
        raise MessageInputError(f"facts must be a dict, not {type(facts).__name__}")
    if not isinstance(rule_table, dict) or not isinstance(rule_table.get("rules"), list):
        raise MessageInputError("rule_table must be a rule table (a dict with 'rules')")
    if not isinstance(rule_set, dict) or not isinstance(rule_set.get("rules"), list):
        raise MessageInputError("rule_set must be a rule set (a dict with 'rules')")
    if state is None or not hasattr(state, "db_get") or not hasattr(state, "events_where"):
        raise MessageInputError("state must be the State of the check")
    if view is None or not hasattr(view, "user_refs"):
        raise MessageInputError("view must be the message view of the check")
    if not isinstance(violated_rules, (list, tuple)) or not violated_rules:
        raise MessageInputError("violated_rules must be a non-empty list")
    ids = []
    for v in violated_rules:
        rid = v.get("rule_id") if isinstance(v, dict) else v
        if rid is None or isinstance(rid, bool) or not isinstance(rid, (str, int)):
            raise MessageInputError(f"a violated rule without an id: {v!r}")
        if str(rid) not in ids:
            ids.append(str(rid))
    return ids


def _fact_value(facts: dict, name: str, rid: str) -> Tuple[Optional[bool], dict]:
    if name not in facts:
        raise MessageInputError(f"rule {rid}: fact {name!r} has no value in facts")
    r = facts[name]
    if not isinstance(r, dict) or "value" not in r:
        raise MessageInputError(f"rule {rid}: fact {name!r}: expected the evaluator's result dict with a value")
    v = r["value"]
    if v is not None and not isinstance(v, bool):
        raise MessageInputError(f"rule {rid}: fact {name!r}: value {v!r} is not true, false or None")
    if v is not None and (r.get("how") in NOT_ESTABLISHED_HOW or _no_part_ran(r) or any(
            isinstance(p, dict) and p.get("kind") == "unclear" for p in (r.get("problems") or []))):
        return None, r                               # not established: it kept its blocking value
    return v, r


def _no_part_ran(r: dict) -> bool:
    """A result that took its blocking value without any part value (an error found outside the evaluator: p9's
    state errors and fact errors, facts_format_v3.blocking_result)."""
    parts = r.get("parts")
    return (r.get("how") == "blocking_value" and isinstance(parts, dict) and bool(parts)
            and all((p or {}).get("how") not in PART_RAN for p in parts.values()))


def explain(domain: str, tool: str, args: dict, violated_rules: Any, facts: dict, state: Any, view: Any,
            rule_table: dict, rule_set: dict) -> dict:
    """The structure behind the rule message: ways, advice, evidence, closing (module text)."""
    ids = _check_inputs(domain, tool, args, violated_rules, facts, state, view, rule_table, rule_set)
    index = _table_index(rule_table)
    rs_rules = _rules_by_id(rule_set)
    sents = _sentences(rule_set)
    kind = "respond" if tool == "respond" else "tool_call"
    me = logged_in_user(state, view, domain)
    no = strict_no(view)
    safety = {"me": me, "logged_in": me is not None, "hidden_before_login": 0, "hidden_other": 0,
              "trace_mismatch": 0}
    rules: List[dict] = []
    analysed: Dict[str, dict] = {}
    for rid in ids:
        if rid not in index:
            raise MessageInputError(f"rule {rid} is not in the rule table")
        if rid not in rs_rules:
            raise MessageInputError(f"rule {rid} is not in the rule set")
        e = index[rid]["entry"]
        if tool not in e["actions"]:
            raise MessageInputError(f"rule {rid} is not a rule of {tool!r} (its actions: {e['actions']})")
        vals, unknown = {}, []
        for f in e["facts"]:
            v, _ = _fact_value(facts, f, rid)
            if v is None:
                bv = e["blocking_values"][f]
                if len(bv) != 1:
                    raise MessageInputError(f"rule {rid}: fact {f!r} is unknown and has no single blocking value")
                v = bool(bv[0])
                unknown.append(f)
            vals[f] = v
        row = index[rid]["rows"].get((tool, tuple(vals[f] for f in e["facts"])))
        if row is None:
            raise MessageInputError(f"rule {rid}: no rule table row for {tool} and {vals}")
        if row["holds"]:
            raise MessageInputError(f"rule {rid} holds with these values ({vals}); it is not violated")
        ways = []
        for s in row["flip_sets"]:
            fas = []
            for f in s:
                if f not in analysed:
                    analysed[f] = analyse_fact(domain, f, facts[f], vals[f], f in unknown)
                fas.append(analysed[f])
            st = [a["status"] for a in fas]
            status = "excluded" if "user_only" in st else ("fixable" if all(x == "fixable" for x in st)
                                                         else "not_possible")
            ways.append({"facts": list(s), "status": status})
        named = [w for w in ways if w["status"] != "excluded"]
        rules.append({"rule_id": rid, "values": vals, "unknown": unknown, "ways": ways, "named": named,
                      "fixable": any(w["status"] == "fixable" for w in named),
                      "sentences": [sid for sid in rs_rules[rid].get("sentences") or [] if sid in sents]})
    # facts named in the message, in order: the facts of the named ways; for a rule with no named way, its
    # user_only facts (stated, never offered as a step)
    order: List[str] = []
    for r in rules:
        r["shown_facts"] = ([f for w in r["named"] for f in w["facts"]] if r["named"] else
                            [f for w in r["ways"] for f in w["facts"] if analysed[f]["status"] == "user_only"])
        for f in r["shown_facts"]:
            if f not in order:
                order.append(f)
    not_met = []
    for f in order:
        an = analysed[f]
        ev = fact_evidence(domain, an, facts[f], tool, args, state, view, me, safety) \
            if an["status"] != "user_only" else []
        not_met.append({"fact": f, "words": words(f), "shown": an["shown"], "status": an["status"], "evidence": ev})
    advice_by_fact = {f: fact_advice(domain, analysed[f], args, state, kind, no) for f in order}
    items: List[dict] = []

    def add(item: dict) -> None:
        if not any(i["text"] == item["text"] and i.get("sub") == item.get("sub") for i in items):
            items.append(item)

    for r in rules:
        if len(r["named"]) <= 1:
            for f in r["shown_facts"]:
                for a in advice_by_fact[f]:
                    add(dict(a, rule=r["rule_id"]))
            continue
        subs = []
        for w in r["named"]:
            lines = [a for f in w["facts"] for a in advice_by_fact[f]]
            subs.append({"status": w["status"], "facts": w["facts"], "advice": lines,
                         "text": " And: ".join(a["text"] for a in lines)})
        add({"who": "ways", "type": "ways", "rule": r["rule_id"], "text": ANY_ONE, "sub": subs})
    if no is not None and not any(a["type"] == "ask_no" for a in advice_lines(items)):
        add({"who": "none", "type": "said_no", "fact": None, "text": f"The user said no (\"{no['quote']}\")."})
    forbid = (no is not None) or any(not r["fixable"] for r in rules)
    if kind == "respond":
        closing = "Do not send the same message as it stands." if forbid else "When this is done, send your message again."
    else:
        closing = "Do not repeat the same call as it stands." if forbid else f"When this is done, call {tool} again."
    first = tgr_feedback.actionable(kind, tool, [], None, {}, {}, {}).split("\n")[0]
    sentence_ids: List[str] = []
    for r in rules:
        for sid in r["sentences"]:
            if sid not in sentence_ids:
                sentence_ids.append(sid)
    return {"version": VERSION, "domain": domain, "tool": tool, "kind": kind, "first_line": first,
            "sentences": [{"id": sid, "text": sents[sid]["text"]} for sid in sentence_ids],
            "rules": rules, "facts": analysed, "not_met": not_met, "advice": items, "strict_no": no,
            "forbid": forbid, "closing": closing, "safety": safety, "advice_class": advice_class(items)}


def advice_lines(items: List[dict]) -> List[dict]:
    """Every advice line of the plan, the lines inside an "any one of these" item included."""
    out = []
    for i in items:
        out += [i] if i["type"] != "ways" else [x for s in i["sub"] for x in s["advice"]]
    return out


def advice_class(items: List[dict]) -> str:
    """One class per block: the whos of the advice lines, joined ('agent', 'ask+none', ...)."""
    ws = set()
    for a in advice_lines(items):
        if a["type"] == "said_no":
            continue
        ws.add("ask" if a["type"] == "ask_no" else a["who"])
    return "+".join(w for w in WHO if w in ws) or "none"


# ----------------------------------------------------------------------------------------------- rendering

def render(plan: dict) -> str:
    lines = [plan["first_line"]]
    if plan["sentences"]:
        lines.append("Policy: " + " ".join(f"\"{s['text']}\"" for s in plan["sentences"]))
    lines.append(NOT_MET)
    for nm in plan["not_met"]:
        lines.append(f"- {nm['words']}: {nm['shown']}")
        for ev in nm["evidence"]:
            lines.append(f"  - {ev['text']}")
    lines.append(WHAT)
    for n, item in enumerate(plan["advice"], 1):
        lines.append(f"{n}. {item['text']}")
        for k, s in enumerate(item.get("sub") or []):
            lines.append(f"   {chr(ord('a') + k)}) {s['text']}")
    lines.append(plan["closing"])
    return "\n".join(lines)


def build_message(domain: str, tool: str, args: dict, violated_rules: Any, facts: dict, state: Any, view: Any,
                  rule_table: dict, rule_set: dict) -> str:
    """The block message, messages = rule (module text). Raises MessageInputError on bad input."""
    return render(explain(domain, tool, args, violated_rules, facts, state, view, rule_table, rule_set))


def build_simple(domain: str, tool: str, args: dict, violated_rules: Any, facts: dict, state: Any, view: Any,
                 rule_table: dict, rule_set: dict) -> str:
    """messages = simple: TGR's own message for the same values, without evidence and without its closing
    "violated ... do not repeat" line (module text)."""
    ids = _check_inputs(domain, tool, args, violated_rules, facts, state, view, rule_table, rule_set)
    aspm = _aspm(rule_set)
    kind = "respond" if tool == "respond" else "tool_call"
    violated, current = [], {}
    for rid in ids:
        if rid not in aspm.rules:
            raise MessageInputError(f"rule {rid} is not in the rule set")
        violated.append({"rule_id": rid, "description": aspm.rules[rid].description, "logic": aspm.rules[rid].logic})
        for n in sorted(aspm.rules[rid].atoms - aspm.action_predicates):
            _fact_value(facts, n, rid)                   # the same input checks as the rule message
            current[n] = facts[n]["value"]               # the value the decision used
    judged = {n: {"value": v, "evidence": ""} for n, v in current.items()}
    text = tgr_feedback.actionable(kind, tool, violated, aspm, current, judged, rule_set.get("predicates") or {})
    lines = [x for x in text.split("\n") if not (x.startswith("- Rule(s) ") and "are violated as things stand" in x)]
    if lines and lines[-1] == "What to do:":
        lines.pop()
    return "\n".join(lines)


def build(messages: str, domain: str, tool: str, args: dict, violated_rules: Any, facts: dict, state: Any,
          view: Any, rule_table: dict, rule_set: dict) -> str:
    """The message of one switch value: 'rule' or 'simple'."""
    if messages == "rule":
        return build_message(domain, tool, args, violated_rules, facts, state, view, rule_table, rule_set)
    if messages == "simple":
        return build_simple(domain, tool, args, violated_rules, facts, state, view, rule_table, rule_set)
    raise MessageInputError(f"messages must be one of {MESSAGES}, not {messages!r}")
