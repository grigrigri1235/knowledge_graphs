"""Tracker v4: the v4 guard (docs/planning/tracker_v4/code_change_map.md section 1.2, the tgr_tracker_v4.py row).

The idea in plain words: v4 is the v3 guard with the v4 fact files and one new rule, the transfer escape. The class
`TrackerTGRv4` is a small subclass of `guard/tgr_tracker_v3.py`'s `TrackerTGRv3`, which stays byte-identical. The probe,
lazy evaluation, the two keys, the OR branch rule, state-error handling and the re-raise of the hard stops (budget,
network, real mode, answer not saved) are v3's own code: `_v3_values`, `_answer` and `_feedback` are v3's functions
run with three names swapped (`_rebind` below: same code object, other globals), never rewritten.

What v4 adds:
  1. Facts from the v4 fact files `state_tracker/v4/facts_v4_<domain>.json` (validated with facts_format_v3.validate).
     The switch facts = "v4" (the only value accepted here).
  2. Hooks that accept v4's ask keywords. A v4 question helper calls `hook.ask(qid, inputs, fact=, part=, wording=2)`
     for its second wording; v3's probe and counting hook take no `wording`, so a v4 helper would get a TypeError
     (a fact error: a silent block). `_ProbeV4` and `_CountingHookV4` take any keyword; the counting hook passes it on
     (a stand-in hook gets none: its answer does not depend on the wording) and logs every ask for rec["v4"].
  3. Write key (interface 1): (tool, object id) of a write call (tool_table.json changes_db); object id = the first of
     order_id, reservation_id, user_id in the arguments. Saved as a list [tool, id].
  4. Tiny block (interface 2): a block of a write call where at least one blocking fact (below) is a text fact. Text
     facts (TEXT_FACTS): facts with a question part, or with a part whose expression calls a listing_*_v4 or
     go_ahead_*_v4 helper; computed from the fact file when the guard is built.
  5. Blocking facts (on every record: rec["blocking_facts"], also rec["v4"]["blocking_facts"]; [] on an allow): the
     facts a block rests on. Per violated rule: the rule table rows for this action that fit the values used (an
     unknown fits both) and do not hold; their tipping facts, plus the rule's unknown facts. A rule with no table entry:
     its facts that are unknown or at their blocking value. Each item {fact, value, source, text, rules}.
  6. Block memory: `conv.v4_blocks`, a list on the episode's Conversation (made when missing). Every write check
     appends one entry {write_key, tiny, blocked, executed, cap_override, step_index, hist_len} after its record is
     complete (so a retried TGR step never counts twice: a failed attempt's entries are removed). commit() (the cap
     override) marks the entry executed.
  7. Transfer escape (interface 3): on a transfer_to_human_agents check, if one write key has 2 or more tiny blocks
     after its last executed attempt (executed = an allowed or cap-overridden check of that key, or the key's call in
     the executed history), the transfer fact (retail request_cannot_be_handled_within_scope, airline
     request_cannot_be_handled_with_available_tools) is set true with source "escape". Only when it was not true
     already, and not on a state error (every fact keeps its blocking value then, as v3). Counted:
     rec["v4"]["escape"] (None or {fact, write_key, tiny_blocks, value_before, source_before, keys}) and
     counters["escapes"].
  8. rec["v3"]: v3's layout, version = VERSION. rec["tracker"]["version"] = "v4".
  9. rec["v4"] (interface 6): {version, manifest_sha256, frozen, write_key, tiny_block, escape, reasks: [{qid, fact,
     part, key1, key2, status1, status2}], unclear_allowed: [{fact, qid}], missing: {fact: [missing records]},
     fast_path: [fact], ask_keys: {fact: [key16]}, blocking_facts, memory_index, memory, state_errors, fact_errors}.
     state_errors and fact_errors are copies of rec["v3"]'s: readers that look at rec["v4"] first (the runner's
     tracker_part) must still see them.
     Where the v4 fields come from (conventions for the helpers):
       reasks          the question helpers' notes {"v4": "reask", qid, fact, part, key1, key2, status1, status2}
                       (questions_v4.py); plus, for a re-ask no note covers, the counting hook's log: an ask with
                       wording 2 (keyword `wording`, or a qid "K<n>b") paired with the earlier wording-1 ask of the
                       same question, fact and part (status2 = the status after the second wording; keys in full).
       unclear_allowed the helpers' notes {"v4": "unclear_allowed", fact, qid}; plus a logged re-ask whose second
                       status is not yes / no while the fact did not take its blocking value.
       missing         helper notes that are missing records ({"line", "expected", ...}) or {"missing": [records]}.
       fast_path       a helper note {"fast_path": True, ...} on the fact.
       ask_keys        every ask's key (16 chars) per fact.

build() is v3's build plus: V3.check_frozen_v3() still runs (proves the v3 files unchanged), the v4 freeze check
(the freeze module's check; require_freeze=True refuses a run without a passing manifest), and the v4 fact files.
The freeze module is loaded only inside build() (by name, FREEZE_MODULE; standard library only, no gold data).

register() adds the offline variants v4 / v4_rule / v4_full to fork/offline_v3.py's registry (called by drivers,
not at import). Note for an offline driver: the escape needs ONE Conversation per conversation, passed to every
check in order (fork/offline_v3.run_guard makes a new one per check, so it never escapes).

Our code. No LLM call, no network call, no gold import.
"""
from __future__ import annotations

import collections
import functools
import importlib
import inspect
import json
import os
import re
import sys
import threading
import types
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "guard"

from guard import tgr_tracker_v3 as V3                                   # noqa: E402  (v3, frozen, unchanged)
from guard.tgr_tracker_v3 import FactFileProblem                         # noqa: E402,F401  (reused, not redefined)
from method_tgr.rules import RESPOND                                     # noqa: E402  (runner copy)
from method_tgr.runtime import TGRConfig, load_rule_set                  # noqa: E402  (runner copy)

from state_tracker import lookup_format as L                             # noqa: E402
from state_tracker import paths                                          # noqa: E402
from state_tracker.predicate_types import load_types                     # noqa: E402
from state_tracker.state import build_state, tool_table                  # noqa: E402
from state_tracker.v3 import facts_format_v3 as F                        # noqa: E402
from state_tracker.v3 import questions as Q                              # noqa: E402,F401  (v3 hook classes; HARD_STOPS are its exceptions)
# the v4 helpers: importing registers their _v4 names in the shared registry
from state_tracker.v4 import questions_v4 as QV4                         # noqa: E402,F401  (A3)
from state_tracker.v4 import listing_v4 as LV4                           # noqa: E402,F401  (A1)
from state_tracker.v4 import helpers_go_ahead_v4 as GA4                  # noqa: E402,F401  (A2)
from state_tracker.v4 import helpers_v4 as H4                            # noqa: E402,F401  (A5)

NAME = "tgr_tracker_v4"
VERSION = "v4.p1.1"
TRACKER_VERSION = "v4"                       # rec["tracker"]["version"]
FEEDBACK_MODULE = "guard.feedback_v4"
FREEZE_MODULE = "scoring.v4_freeze"          # P1b's freeze check (loaded in build() only)
FACTS = ("v4",)
ESCAPE = "escape"
KINDS = V3.KINDS + (ESCAPE,)
HARD_STOPS = V3.HARD_STOPS                   # v3's classes, reused (never new ones)
TRANSFER_TOOL = "transfer_to_human_agents"
TRANSFER_FACTS = {"retail": "request_cannot_be_handled_within_scope",
                  "airline": "request_cannot_be_handled_with_available_tools"}
ESCAPE_MIN_TINY = 2
OBJECT_ID_KEYS = ("order_id", "reservation_id", "user_id")
FACTS_V4_REL = "state_tracker/v4/facts_v4_{}.json"
TEXT_HELPER_RE = re.compile(r"\b(?:listing_\w*_v4|go_ahead_\w*_v4)\s*\(")
SECOND_QID_RE = re.compile(r"^(K[1-9][0-9]*)b$")
ANSWER_WORDS = ("yes", "no")
# the files this guard runs on besides the shared ones (relative to predicate_correctness/), for the run's input hashes
INPUT_FILES = ("guard/tgr_tracker_v4.py", "guard/tgr_tracker_v3.py", "guard/feedback_v4.py",
               "state_tracker/v4/__init__.py", "state_tracker/v4/questions_v4.py", "state_tracker/v4/listing_v4.py",
               "state_tracker/v4/helpers_go_ahead_v4.py", "state_tracker/v4/helpers_v4.py",
               "state_tracker/v4/questions_v4.json", "state_tracker/v4/facts_v4_retail.json",
               "state_tracker/v4/facts_v4_airline.json")

# domain -> the text facts of the domain's v4 fact file (filled by load_checked_facts_v4)
TEXT_FACTS: Dict[str, FrozenSet[str]] = {}


class FreezeV4Failed(RuntimeError):
    """require_freeze=True and the v4 freeze manifest is missing or does not pass its check."""


# ----------------------------------------------------------------------------------------------- v3 code, rebound
def _rebind(func: Any, **names: Any) -> Any:
    """v3's function with the same code object and closure, run with some module names swapped (the v4 hooks)."""
    g = dict(func.__globals__)
    g.update(names)
    f = types.FunctionType(func.__code__, g, func.__name__, func.__defaults__, func.__closure__)
    f.__kwdefaults__ = func.__kwdefaults__
    f.__doc__, f.__qualname__ = func.__doc__, func.__qualname__
    return f


_SINK = threading.local()                    # .asks: the counting hooks' ask log of the check on this thread


def _wording(qid: str, kw: Dict[str, Any]) -> Tuple[str, int]:
    m = SECOND_QID_RE.match(qid or "")
    if m:
        return m.group(1), 2
    try:
        return qid, int(kw.get("wording", 1) or 1)
    except (TypeError, ValueError):
        return qid, 1


class _ProbeV4(V3._Probe):
    """v3's probe; ask() takes v4's keywords too (wording=...). Stops at the first ask, as v3's."""

    def ask(self, qid: str, inputs: Dict[str, Any], *, fact: Optional[str] = None, part: Optional[str] = None,
            **kw: Any) -> dict:
        raise V3._Deferred(qid)


def _accepts_kw(func: Any, name: str) -> bool:
    try:
        ps = inspect.signature(func).parameters.values()
    except (TypeError, ValueError):
        return True
    return any(p.name == name or p.kind is inspect.Parameter.VAR_KEYWORD for p in ps)


class _CountingHookV4(V3._CountingHook):
    """v3's counting hook; ask() passes v4's keywords on (dropped only for a stand-in hook without them) and logs
    every ask (fact, part, qid, wording, key, status) for rec["v4"]. Other attributes come from the inner hook."""

    def ask(self, qid: str, inputs: Dict[str, Any], *, fact: Optional[str] = None, part: Optional[str] = None,
            **kw: Any) -> dict:
        self.asked[qid] += 1
        call = dict(kw)
        if call and getattr(self.inner, "standin", False):
            call = {k: v for k, v in call.items() if _accepts_kw(self.inner.ask, k)}
        rec = self.inner.ask(qid, inputs, fact=fact, part=part, **call)
        log = getattr(_SINK, "asks", None)
        if log is not None:
            base, w = _wording(qid, kw)
            r = rec if isinstance(rec, dict) else {}
            log.append({"fact": fact, "part": part, "qid": base, "wording": w, "key": r.get("key"),
                        "key16": (r.get("key") or "")[:16] or None, "status": r.get("status")})
        return rec

    def __getattr__(self, name: str) -> Any:
        if name == "inner":
            raise AttributeError(name)
        return getattr(self.inner, name)


_V3_VALUES = _rebind(V3.TrackerTGRv3._v3_values, _Probe=_ProbeV4)
_V3_ANSWER = _rebind(V3.TrackerTGRv3._answer, _CountingHook=_CountingHookV4)
_V3_FEEDBACK = _rebind(V3.TrackerTGRv3._feedback, FEEDBACK_MODULE=FEEDBACK_MODULE)


# ----------------------------------------------------------------------------------------------- small helpers
def text_facts_of(doc: Optional[dict]) -> FrozenSet[str]:
    """The text facts of a fact file: a part with source / question "question", or an expression that calls a
    listing_*_v4 or go_ahead_*_v4 helper."""
    out = set()
    for name, e in ((doc or {}).get("facts") or {}).items():
        for p in (e.get("parts") or {}).values():
            if not isinstance(p, dict):
                continue
            if p.get("source") == "question" or p.get("question") or TEXT_HELPER_RE.search(str(p.get("expr") or "")):
                out.add(name)
                break
    return frozenset(out)


def write_tools(domain: str) -> FrozenSet[str]:
    tools = ((tool_table().get("domains") or {}).get(domain) or {}).get("tools") or {}
    return frozenset(t for t, x in tools.items() if x.get("changes_db"))


def write_key_v4(domain: str, tool: str, args: Any, writes: Optional[FrozenSet[str]] = None) -> Optional[list]:
    """[tool, object id] of a write call (interface 1); None for any other call. A missing id gives [tool, None]."""
    writes = write_tools(domain) if writes is None else writes
    if tool not in writes:
        return None
    a = args if isinstance(args, dict) else {}
    return [tool, next((a[k] for k in OBJECT_ID_KEYS if k in a), None)]


def _kstr(key: Any) -> str:
    return json.dumps(key, sort_keys=True, default=str)


def memory_of(conv: Any) -> list:
    """The episode's block memory (conv.v4_blocks), made when missing."""
    m = getattr(conv, "v4_blocks", None)
    if not isinstance(m, list):
        m = []
        conv.v4_blocks = m
    return m


def _call_args(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        out = json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return {}
    return out if isinstance(out, dict) else {}


def executed_positions(domain: str, history: List[dict], writes: FrozenSet[str]) -> Dict[str, int]:
    """write key (as text) -> the newest message index of an executed call of that key in the history."""
    out: Dict[str, int] = {}
    for i, m in enumerate(history or []):
        if not isinstance(m, dict) or m.get("role") != "assistant":
            continue
        for tc in m.get("tool_calls") or []:
            fn = (tc or {}).get("function") or {}
            k = write_key_v4(domain, fn.get("name"), _call_args(fn.get("arguments")), writes)
            if k is not None:
                out[_kstr(k)] = i
    return out


def escape_candidate(domain: str, blocks: List[dict], history: List[dict], writes: FrozenSet[str],
                     minimum: int = ESCAPE_MIN_TINY) -> Optional[dict]:
    """The write key with >= minimum tiny blocks after its last executed attempt (the one with the most such blocks;
    the first such key on a tie), or None."""
    last = executed_positions(domain, history, writes)
    for e in blocks:
        if e.get("executed") and e.get("write_key") is not None:
            k = _kstr(e["write_key"])
            last[k] = max(last.get(k, -1), int(e.get("hist_len", -1)))
    counts: Dict[str, int] = collections.OrderedDict()
    keys: Dict[str, Any] = {}
    for e in blocks:
        if not e.get("tiny") or e.get("write_key") is None:
            continue
        k = _kstr(e["write_key"])
        if int(e.get("hist_len", -1)) > last.get(k, -1):
            counts[k] = counts.get(k, 0) + 1
            keys[k] = e["write_key"]
    ready = [(k, n) for k, n in counts.items() if n >= minimum]
    if not ready:
        return None
    best = max(ready, key=lambda x: x[1])
    return {"write_key": list(keys[best[0]]), "tiny_blocks": best[1],
            "keys": [{"write_key": list(keys[k]), "tiny_blocks": n} for k, n in ready]}


def _missing_records(fact: str, notes: Iterable[dict]) -> List[dict]:
    out = []
    for n in notes or []:
        x = n.get("note") if isinstance(n, dict) else None
        if not isinstance(x, dict):
            continue
        recs = x.get("missing") if isinstance(x.get("missing"), list) else ([x] if "line" in x and "expected" in x
                                                                            else [])
        for r in recs:
            if isinstance(r, dict):
                out.append(dict(r, fact=r.get("fact", fact), part=r.get("part", n.get("part"))))
    return out


def _note_flags(notes: Iterable[dict], key: str) -> List[dict]:
    return [n["note"] for n in notes or [] if isinstance(n, dict) and isinstance(n.get("note"), dict)
            and n["note"].get(key)]


def _notes_of(res: dict) -> List[dict]:
    ev = res.get("evidence") if isinstance(res, dict) else None
    return list((ev or {}).get("notes") or []) if isinstance(ev, dict) else []


def v4_fields(asks: List[dict], results: Dict[str, dict], entries: Dict[str, dict]) -> Dict[str, Any]:
    """reasks, unclear_allowed, missing, fast_path, ask_keys of one check (see the module text). The question
    helpers' own notes ({"v4": "reask" | "unclear_allowed", ...}) come first; the counting hook's ask log adds what
    no note covers (a helper that re-asks without a note)."""
    reasks: List[dict] = []
    unclear: List[dict] = []
    missing: Dict[str, List[dict]] = {}
    fast: List[str] = []
    seen_r, seen_u = set(), set()
    for f, res in results.items():
        notes = _notes_of(res)
        for n in notes:
            x = n.get("note") if isinstance(n, dict) else None
            if not isinstance(x, dict):
                continue
            if x.get("v4") == "reask":
                r = {k: x.get(k) for k in ("qid", "fact", "part", "key1", "key2", "status1", "status2")}
                r["fact"] = r["fact"] or f
                reasks.append(r)
                seen_r.add((r["qid"], r["fact"], r["part"], (r["key2"] or "")[:16]))
            elif x.get("v4") == "unclear_allowed" or x.get("unclear_allowed") is True:
                q = x.get("qid") or x.get("question")
                if (f, q) not in seen_u:
                    seen_u.add((f, q))
                    unclear.append({"fact": f, "qid": q})
        m = _missing_records(f, notes)
        if m:
            missing[f] = m
        if _note_flags(notes, "fast_path"):
            fast.append(f)
    ask_keys: Dict[Any, List[str]] = collections.OrderedDict()
    for i, a in enumerate(asks):
        if a.get("key16"):
            ask_keys.setdefault(a.get("fact"), []).append(a["key16"])
        if a.get("wording", 1) < 2 or (a.get("qid"), a.get("fact"), a.get("part"), a.get("key16") or "") in seen_r:
            continue
        first = next((b for b in reversed(asks[:i]) if b.get("wording", 1) == 1 and b.get("qid") == a.get("qid")
                      and b.get("fact") == a.get("fact") and b.get("part") == a.get("part")), None)
        reasks.append({"qid": a.get("qid"), "fact": a.get("fact"), "part": a.get("part"),
                       "key1": first.get("key") if first else None, "key2": a.get("key"),
                       "status1": first.get("status") if first else None, "status2": a.get("status")})
        f = a.get("fact")
        res = results.get(f) or {}
        bv = (entries.get(f) or {}).get("blocking_value")
        if a.get("status") not in ANSWER_WORDS and isinstance(res.get("value"), bool) and res["value"] != bv \
                and (f, a.get("qid")) not in seen_u:
            seen_u.add((f, a.get("qid")))
            unclear.append({"fact": f, "qid": a.get("qid")})
    return {"reasks": reasks, "unclear_allowed": unclear, "missing": missing, "fast_path": sorted(fast),
            "ask_keys": dict(ask_keys)}


def check_switches_v4(facts: str, meaning: str, messages: str, answers: Any = None) -> None:
    if facts not in FACTS:
        raise ValueError(f"facts must be one of {FACTS}, not {facts!r}")
    V3.check_switches("v3", meaning, messages, answers)          # v3's rules for the other switches


# ----------------------------------------------------------------------------------------------- the guard
class TrackerTGRv4(V3.TrackerTGRv3):
    """TrackerTGRv3 with the v4 fact file, v4 hooks, block memory, the transfer escape and rec["v4"]."""

    def __init__(self, rule_set: dict, tools: List[dict], config: TGRConfig, domain: str,
                 lookups: Dict[str, dict], types: Dict[str, dict], *, facts: str = "v4",
                 meaning: str = "saved_judge", messages: str = "frozen", lazy: bool = True, answers: Any = None,
                 facts_doc: Optional[dict] = None, rule_table: Optional[dict] = None,
                 freeze: Optional[dict] = None, text_facts: Optional[Iterable[str]] = None):
        check_switches_v4(facts, meaning, messages, answers)
        super().__init__(rule_set, tools, config, domain, lookups, types, facts="v3", meaning=meaning,
                         messages=messages, lazy=lazy, answers=answers, facts_doc=facts_doc, rule_table=rule_table)
        self.switches["facts"] = facts                          # "v4": v3's evaluator path on the v4 fact file
        self.freeze = dict(freeze) if freeze else {"manifest_sha256": None, "n_files": None, "frozen": False}
        self.text_facts = frozenset(text_facts) if text_facts is not None else text_facts_of(facts_doc)
        self.write_tools = write_tools(domain)
        self.transfer_fact = TRANSFER_FACTS.get(domain)
        self._v4tls = threading.local()

    # --------------------------------------------------------------------------------------------- v3 code, rebound
    _answer = _V3_ANSWER
    _feedback = _V3_FEEDBACK

    def _v3_values(self, step, names: List[str], circuit: Optional[List[str]]):
        out, errors, info = _V3_VALUES(self, step, names, circuit)
        d = self._v3tls.data
        self._v4tls.data = d
        tool = RESPOND if step.kind == "respond" else step.name
        fact = self.transfer_fact
        conv = getattr(self._v4tls, "conv", None)
        if tool == TRANSFER_TOOL and fact in out and d is not None and not d["state_errors"] and conv is not None:
            esc = escape_candidate(self.domain, memory_of(conv), step.history, self.write_tools)
            if esc is not None and out[fact]["value"] is not True:
                before = {"value_before": out[fact]["value"], "source_before": out[fact]["source"]}
                res = dict(d["results"][fact], value=True, how=ESCAPE, v3_source=ESCAPE)
                d["results"][fact], d["kinds"][fact] = res, ESCAPE
                out[fact] = {"value": True, "source": ESCAPE,
                             "evidence": f"v4 escape: {esc['tiny_blocks']} tiny blocks on the write "
                                         f"{esc['write_key'][0]} {esc['write_key'][1]} and no later executed attempt"}
                self._v4tls.escape = dict(esc, fact=fact, **before)
                self._count("escapes")
        return out, errors, info

    def _v3_part(self, d, message, seconds):
        out = super()._v3_part(d, message, seconds)
        out["version"] = VERSION
        return out

    # --------------------------------------------------------------------------------------------- blocking facts
    def _rule_blocking_facts(self, rid: Any, cur: Dict[str, Optional[bool]], tool: str) -> set:
        r = self._rt_rules.get(str(rid))
        if r is not None:
            rows = [row for row in r["rows"] if row.get("action") in (None, tool) and not row["holds"]
                    and all(cur.get(f) is None or cur[f] == v for f, v in row["values"].items())]
            s = set()
            for row in rows:
                s |= set(row.get("tipping_facts") or []) | {f for fs in row.get("flip_sets") or [] for f in fs}
            s |= {f for f in r["facts"] if f in cur and cur[f] is None}
            return s or {f for f in r["facts"] if f in cur}
        try:
            atoms = set(self.aspm.rules[rid].atoms) - set(self.aspm.action_predicates)
        except (KeyError, AttributeError):
            return set()
        entries = (self.facts_doc or {}).get("facts") or {}
        return {f for f in atoms if f in cur and (cur[f] is None or cur[f] == (entries.get(f) or {}).get(
            "blocking_value"))}

    def blocking_facts(self, rec: dict, tool: str, kinds: Optional[Dict[str, str]] = None) -> List[dict]:
        """The facts a block rests on (module text, point 5); [] for an allowed check."""
        if rec.get("action_allowed", True):
            return []
        judged = rec.get("judge") or {}
        cur = {n: (v or {}).get("value") for n, v in judged.items()}
        found: Dict[str, List[str]] = {}
        for v in rec.get("violated_rules") or []:
            rid = v.get("rule_id")
            for f in sorted(self._rule_blocking_facts(rid, cur, tool)):
                found.setdefault(f, []).append(str(rid))
        kinds = kinds or {}
        return [{"fact": f, "value": cur.get(f), "source": kinds.get(f) or (judged.get(f) or {}).get("source"),
                 "text": f in self.text_facts, "rules": rids} for f, rids in sorted(found.items())]

    # --------------------------------------------------------------------------------------------- TGR hooks
    def _step(self, conv, step) -> dict:
        blocks = memory_of(conv)
        n0 = len(blocks)
        tls = self._v4tls
        tls.conv, tls.data, tls.escape = conv, None, None
        _SINK.asks = []
        try:
            rec = super()._step(conv, step)
        except BaseException:
            del blocks[n0:]                                    # as TGR.step's trace: a failed attempt leaves nothing
            raise
        finally:
            tls.conv = None
            asks, _SINK.asks = list(getattr(_SINK, "asks", None) or []), None
        d, esc = tls.data, tls.escape
        tls.data = tls.escape = None
        if d is None:
            rec["tracker"] = {"version": TRACKER_VERSION, "applied": False, "code_predicates": [],
                              "judge_skipped": False}
        elif isinstance(rec.get("tracker"), dict):
            rec["tracker"]["version"] = TRACKER_VERSION
        tool = RESPOND if step.kind == "respond" else step.name
        args = step.arguments if isinstance(step.arguments, dict) else {}
        allowed = bool(rec.get("action_allowed", True))
        wk = write_key_v4(self.domain, tool, args, self.write_tools)
        kinds = (d or {}).get("kinds") or {}
        bf = self.blocking_facts(rec, tool, kinds)
        tiny = (not allowed) and wk is not None and any(b["text"] for b in bf)
        fields = v4_fields(asks, (d or {}).get("results") or {}, (self.facts_doc or {}).get("facts") or {})
        entry = None
        if wk is not None:
            entry = {"write_key": wk, "tiny": tiny, "blocked": not allowed, "executed": allowed,
                     "cap_override": False, "step_index": step.index, "hist_len": len(step.history or [])}
        since = [e for e in blocks + ([entry] if entry else []) if wk is not None and e.get("tiny")
                 and _kstr(e.get("write_key")) == _kstr(wk)]
        v3p = rec.get("v3") or {}
        rec["blocking_facts"] = bf
        rec["v4"] = dict(
            version=VERSION, manifest_sha256=self.freeze.get("manifest_sha256"),
            frozen=bool(self.freeze.get("frozen")), write_key=wk, tiny_block=tiny, escape=esc, **fields,
            blocking_facts=bf, memory_index=(len(blocks) if entry is not None else None),
            memory={"entries_before": len(blocks), "tiny_blocks_on_key": len(since)},
            state_errors=list(v3p.get("state_errors") or []), fact_errors=list(v3p.get("fact_errors") or []))
        if entry is not None:
            blocks.append(entry)                               # last: the record is complete
        return rec

    def commit(self, conv, rec: dict) -> None:
        """TGR's commit (a step executed through the cap override), plus: its memory entry is marked executed."""
        super().commit(conv, rec)
        if rec.get("action_allowed", True):
            return
        v4 = rec.get("v4") or {}
        idx, blocks = v4.get("memory_index"), memory_of(conv)
        if isinstance(idx, int) and 0 <= idx < len(blocks) and _kstr(blocks[idx].get("write_key")) == \
                _kstr(v4.get("write_key")):
            blocks[idx]["executed"] = blocks[idx]["cap_override"] = True
        elif v4.get("write_key") is not None:                  # no entry found: record the executed attempt
            blocks.append({"write_key": v4["write_key"], "tiny": False, "blocked": True, "executed": True,
                           "cap_override": True, "step_index": rec.get("step_index"),
                           "hist_len": max([int(e.get("hist_len", -1)) for e in blocks] + [0])})


# ----------------------------------------------------------------------------------------------- building
def facts_path_v4(domain: str) -> str:
    return os.path.join(paths.PC_DIR, *FACTS_V4_REL.format(domain).split("/"))


_DOCS: Dict[Tuple[str, str], dict] = {}
_DOCS_LOCK = threading.Lock()


def load_checked_facts_v4(domain: str, path: Optional[str] = None) -> dict:
    """The domain's v4 fact file (or `path`), validated once per process (0 problems, or FactFileProblem). The
    default file also fills TEXT_FACTS[domain]."""
    p = os.path.abspath(path or facts_path_v4(domain))
    with _DOCS_LOCK:
        if (domain, p) not in _DOCS:
            if not os.path.isfile(p):
                raise FactFileProblem(f"{domain}: the v4 fact file {p} does not exist (the merge script builds it)")
            doc = F.load_facts(domain, path=p)
            problems = F.validate(doc, domain)
            if problems:
                raise FactFileProblem(f"{domain}: {len(problems)} v4 fact file problems: {problems[:3]}")
            _DOCS[(domain, p)] = doc
            if path is None:
                TEXT_FACTS[domain] = text_facts_of(doc)
        return _DOCS[(domain, p)]


def freeze_status_v4(require: bool, module: Any = None, manifest: Optional[str] = None) -> Dict[str, Any]:
    """{manifest_sha256, n_files, frozen} from the freeze module's check(manifest) -> {ok, checked, manifest_sha256,
    problems, ...} (manifest: the module's DEFAULT_MANIFEST unless given). frozen = ok. require=True and no passing
    manifest: FreezeV4Failed (a SystemExit of the module is turned into it)."""
    mod = module if module is not None else importlib.import_module(FREEZE_MODULE)
    try:
        res = mod.check(manifest or getattr(mod, "DEFAULT_MANIFEST"))
    except SystemExit as e:
        raise FreezeV4Failed(f"the v4 freeze check refused: {e}") from None
    res = res if isinstance(res, dict) else {}
    ok = bool(res.get("ok")) and res.get("manifest_sha256") is not None
    out = {"manifest_sha256": res.get("manifest_sha256"), "n_files": res.get("checked"), "frozen": ok}
    if require and not ok:
        raise FreezeV4Failed(f"the v4 freeze manifest does not pass: {res.get('problems') or res}"[:600])
    return out


def build(domain: str, tools: Optional[List[dict]] = None, *, facts: str = "v4", meaning: str = "saved_judge",
          messages: str = "frozen", lazy: bool = True, answers: Any = None, require_freeze: bool = False,
          rules_dir: Optional[str] = None, frozen_table: Optional[Dict[str, Optional[str]]] = None,
          facts_doc: Optional[dict] = None, facts_path: Optional[str] = None, freeze_module: Any = None
          ) -> TrackerTGRv4:
    """The v4 guard of one domain: V3.build's checks (rule set flags, the eval v2 inputs, V3.check_frozen_v3: the v3
    files unchanged, the lookups), the v4 freeze check, the v4 fact file (0 problems). facts_doc / facts_path /
    freeze_module: tests only."""
    check_switches_v4(facts, meaning, messages, answers)
    if domain not in paths.DOMAINS:
        raise ValueError(f"unknown domain {domain!r}")
    rules_dir = rules_dir or os.path.join(paths.RULES_DIR, domain)
    rs_path = os.path.join(rules_dir, "rule_set.json")
    rs = load_rule_set(rs_path)
    if rs["flags"]["a"] is not True or rs["flags"]["b"] is not True:
        raise ValueError(f"{NAME} needs a rule set built with A and B; {rules_dir} has {rs['flags']}")
    frozen_v2 = V3.T.check_frozen()
    frozen_v3 = V3.check_frozen_v3(frozen_table)
    problems = L.check_lookups(domain)
    if problems:
        raise V3.T.FrozenInputChanged(f"lookup file problems: {problems[:3]}")
    types_ = load_types()[domain]
    missing = sorted(set(rs["predicates"]) - set(types_))
    if missing:
        raise ValueError(f"predicates without a type: {missing}")
    freeze = freeze_status_v4(require_freeze, freeze_module)
    doc = facts_doc if facts_doc is not None else load_checked_facts_v4(domain, facts_path)
    rt = V3.load_rule_table(domain)
    config = TGRConfig(actionable_feedback=True, judge_effort=V3.T.JUDGE_EFFORT, epsilon=V3.T.EPSILON)
    tgr = TrackerTGRv4(rs, list(tools or []), config, domain, L.load_lookups(domain), types_, facts=facts,
                       meaning=meaning, messages=messages, lazy=lazy, answers=answers, facts_doc=doc, rule_table=rt,
                       freeze=freeze)
    build_state([], None, domain=domain)          # load the τ-bench copy and data once, before worker threads
    fp = None if facts_doc is not None else os.path.abspath(facts_path or facts_path_v4(domain))
    tgr.info = {"guard": NAME, "version": VERSION, "domain": domain, "switches": dict(tgr.switches), "lazy": lazy,
                "rules_dir": rules_dir, "rule_set_sha256": V3.sha256(rs_path), "frozen_sha256_v2": frozen_v2,
                "frozen_sha256_v3": frozen_v3["sha256"], "unrecorded_v3": frozen_v3["unrecorded"],
                "v4_freeze": freeze, "require_freeze": bool(require_freeze),
                "facts_file": None if fp is None else os.path.relpath(fp, paths.PC_DIR),
                "facts_sha256": None if fp is None else V3.sha256(fp),
                "text_facts": sorted(tgr.text_facts),
                "answers": type(answers).__name__ if answers is not None else None,
                "backend": getattr(getattr(answers, "backend", None), "name", None)}
    return tgr


# ----------------------------------------------------------------------------------------------- offline registry
VARIANTS: Dict[str, Dict[str, Any]] = {
    "v4": {"meaning": "saved_judge", "messages": "frozen", "lazy": True},
    "v4_rule": {"meaning": "saved_judge", "messages": "rule", "lazy": True},
    "v4_full": {"meaning": "saved_judge", "messages": "frozen", "lazy": False},
}
_REGISTERED: Dict[str, Any] = {}


def register(names: Optional[List[str]] = None) -> List[str]:
    """Add the offline variants to fork/offline_v3.py's registry (once per process). Called by drivers only."""
    from fork import offline_v3 as O
    done = []
    for name in (names or list(VARIANTS)):
        if name not in _REGISTERED:
            factory = functools.partial(build, **VARIANTS[name])
            O.register_guard(name, lambda domain, f=factory: f(domain))
            _REGISTERED[name] = factory
        done.append(name)
    return done


def register_tiny(name: str, answers: Any, *, messages: str = "frozen", lazy: bool = True) -> str:
    """Register (or replace) an offline variant with meaning = tiny and this answers hook (fake answers)."""
    from fork import offline_v3 as O
    check_switches_v4("v4", "tiny", messages, answers)
    factory = functools.partial(build, meaning="tiny", messages=messages, lazy=lazy, answers=answers)
    O.register_guard(name, lambda domain, f=factory: f(domain), replace=True)
    _REGISTERED[name] = factory
    return name
