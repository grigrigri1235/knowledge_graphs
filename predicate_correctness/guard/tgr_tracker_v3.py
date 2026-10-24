"""Tracker v3, part 9: the v3 guard, with no judge (docs/planning/tracker_v3/p9.md).

One guard, `TrackerTGRv3`, a subclass of eval v2's `TrackerTGR` (guard/tgr_tracker.py, unchanged). TGR's own code
(rules, circuit, mln.decide, trace, feedback) runs unchanged. The guard never calls the LLM judge: below TrackerTGR in
the class order sits `_NoLLMJudge`, the only `_judge` TrackerTGR can reach, and it returns given (saved) values or
refuses. TGR's own LLM judge (method_tgr.runtime.TGR._judge) is never reached.

Three switches, stored in every guard record (rec["v3"]["switches"]):
  facts     v2   eval v2's tracker: TrackerTGR's lookups for the code-type predicates, the saved judge values for the
                 rest (as fork/points_tgr.py OfflineTrackerTGR: the eval v2 guard, offline);
            v3   every fact from the ONE v3 evaluator (state_tracker/v3/facts_format_v3.py) on the v3 fact files;
  meaning   saved_judge  offline stand-in: the judge's saved value of the fact stands in for the tiny-question answer,
                 wherever the fact's definition asks one (true -> yes, false -> no; questions.StandInAnswers). Code
                 parts stay code. A saved "unknown" stays unknown: the fact is evaluated with the answer yes and with
                 the answer no; if both give the same value, code decided it; else the fact is unknown (None) and
                 TGR's own three-valued decision handles it, as in eval v2;
            tiny the tiny questions of p8 through the answers hook given to the guard (fake answers in all p9 tests);
  messages  frozen  TGR's own block message;
            simple  TGR's message without its closing "violated ... do not repeat" line (and without a "What to do:"
                    header left empty by that);
            rule    guard.feedback_v3.build_message(domain, tool, args, violated_rules, facts, state, view,
                    rule_table, rule_set) (p10); facts = {name: the evaluator's result dict, plus "v3_source" (the
                    source kind below); a stand-in unknown has value None}. Any exception there gives TGR's own
                    message, counted (TrackerTGRv3.counters["message_fallbacks"]), so TGR.step never retries and
                    raises.

Hooks (TGR's hook names):
  _judge          facts = v2: TrackerTGR._judge (its judge call reaches _NoLLMJudge: the given values).
                  facts = v3: no judge at all. tracker_values() sets every fact; returns {name: {value, evidence,
                  source}} for TGR's decision.
  tracker_values  facts = v2: TrackerTGR's own. facts = v3: builds the state WITH the pending call
                  (state.build_state(history, {"tool", "args"}, domain)), the message view (p7), evaluates the facts,
                  and keeps the state, the view and the per-fact results (thread-local) for the message.
                  (Offline speed only: `state_source`, a callable that returns the same state from one walk over
                  the conversation; the p9 driver checks the equality with build_state. Default and online: None.)
  _feedback       the message (the switch above).
  _step           adds rec["v3"]: {version, switches, lazy, facts: {name: {value, source, how, sources, parts: {id:
                  {value, source, who, how}}, problems, ...}}, unknown, state_errors, fact_errors, questions,
                  standin, message, seconds}.

Only the facts a rule still needs (lazy = True, the default): every fact is first run with a probe answers hook that
stops at the first question (a problem of kind "deferred_question"), so the code parts of every fact run first. A fact
that needs a question is answered only while some rule of the circuit that holds it is not decided by the values
known so far (the rule table's rows for the pending action: decided = every row that fits the known values gives the
same result; an unknown value fits both). A skipped fact takes its blocking value (it cannot change any rule).
lazy = False answers every such fact (the comparison of the p9 tests and driver).

Fact sources (rec["v3"]["facts"][name]["source"]):
  code            decided by code parts (no question answer used)
  question        a tiny-question answer (meaning = tiny)
  saved_judge     the judge's saved value stood in for the answer (meaning = saved_judge)
  saved_unknown   the judge's saved value is unknown and code does not decide: value None
  lazy_skip       no rule of the circuit needed it: its blocking value
  blocking_value  a problem on the way (missing argument, unclear answer, ...): its blocking value
  state_error     the state could not be trusted (build error, replay mismatch, parse problem, state problem, view
                  error): every fact of the check takes its blocking value (facts_format_v3.blocking_result), counted
  fact_error      the evaluator raised (NotDefinedYet, FactEvalError, a helper error): that fact takes its blocking
                  value, counted. No judge fallback (Q1).

FROZEN_SHA256 lists every v3 file the guard reads and the v2 files it relies on, with their known sha256 (the v2
values are those of output/eval_v3/manifest_eval_v2_data.sha256). build() checks them; a changed file stops the run
(FrozenInputChangedV3). An entry with None would be a file not recorded yet (none is left: guard/feedback_v3.py is
p10's final); it is reported in build()'s info, never silently passed.

Registered only from new files: register() adds the offline variants to fork/offline_v3.py's registry (called by the
drivers, not at import); guard/run_online_v3.py registers the online guard in p13.

Our code. It imports the runner copy through guard/runner_path.py, never imports gold code or a scoring module, and
makes no LLM call and no network call.
"""
from __future__ import annotations

import collections
import functools
import hashlib
import importlib
import json
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "guard"

from guard import runner_path                                            # noqa: E402

runner_path.setup()

from guard import tgr_tracker as T                                       # noqa: E402  (eval v2, frozen)
from guard.tgr_tracker import TrackerTGR                                 # noqa: E402
from method_tgr.rules import RESPOND                                     # noqa: E402  (runner copy)
from method_tgr.runtime import TGR, TGRConfig, load_rule_set              # noqa: E402  (runner copy)

from state_tracker import lookup_format as L                             # noqa: E402
from state_tracker import paths                                          # noqa: E402
from state_tracker.predicate_types import load_types                     # noqa: E402
from state_tracker.state import build_state                              # noqa: E402
from state_tracker.v3 import facts_format_v3 as F                        # noqa: E402
from state_tracker.v3 import code_helpers                                # noqa: E402,F401  (registers p6 names)
from state_tracker.v3 import message_view as MV                          # noqa: E402  (p7: the view; registers)
from state_tracker.v3 import info_classes                                # noqa: E402,F401  (p7)
from state_tracker.v3 import questions as Q                              # noqa: E402  (p8: registers the helpers)

NAME = "tgr_tracker_v3"
VERSION = "v3.p9.1"
TRACKER_VERSION = "v3"                       # rec["tracker"]["version"] when facts = v3

FACTS = ("v2", "v3")
MEANINGS = ("saved_judge", "tiny")
MESSAGES = ("frozen", "rule", "simple")
DEFAULT_SWITCHES = {"facts": "v3", "meaning": "saved_judge", "messages": "frozen"}

KINDS = ("code", "question", "saved_judge", "saved_unknown", "lazy_skip", "blocking_value", "state_error",
         "fact_error")
DEFERRED = "deferred_question"               # the probe's problem kind: the fact needs a question
STANDIN_OFFER = "offer(standin)"             # questions.offer_kind / offer_amount_ok under a stand-in hook
NOT_RETURNED = "(not returned by the judge)"  # as fork/points_tgr.py GivenJudgeTGR (TGR's own text)
FEEDBACK_MODULE = "guard.feedback_v3"
RULE_TABLE_REL = "output/eval_v3/rule_table_{}.json"
CLOSING_PREFIX = "- Rule(s) "
CLOSING_MARK = " are violated as things stand: do not "
WHAT_TO_DO = "What to do:"
HARD_STOPS = (Q.BudgetExceeded, Q.NetworkBlocked, Q.RealModeRefused, Q.AnswerNotSaved)

# Every file the v3 guard reads (relative to predicate_correctness/) -> sha256. v3 files: recorded by p9 on 2026-10-23
# (fact files and message_view.py after p7's last screen change, 07:00 UTC; feedback_v3.py: p10's final); None = not
# recorded yet. v2 files: the hashes of the eval v2 manifest. Updated 2026-10-23 by p12 step 0 (RC11 M1 and m3 fixes on
# development data; questions.py thread-safe for --workers): both fact files, message_view.py, info_classes.py,
# questions.py.
FROZEN_SHA256: Dict[str, Optional[str]] = {
    # --- v3 (new files)
    "state_tracker/v3/facts_v3_retail.json": "0122a87da75543f824806612c346edc67d37e63a63464270216d20327a3f3eba",
    "state_tracker/v3/facts_v3_airline.json": "c49deb8c410247a0dd1b4f5d0a743a5148bf8e899d140595110d7c25f5f16783",
    "state_tracker/v3/facts_format_v3.py": "c4de3e63502e1ec8532e622f77333deb3faa066891c65c23b6578d75614ce727",
    "state_tracker/v3/code_helpers.py": "53f08edd0675bb3bfc5ca60dcd0c26d3e98f6a903ca2e0203cc3b295789b090d",
    "state_tracker/v3/message_view.py": "4d302a75b1508403b925b8822b6376cbd447108c85464bbf1b3d24beff0cfad4",
    "state_tracker/v3/info_classes.py": "ba55362a818d7edbdd4ec2a64ae17461f9dabf5194eebfba1a10c0f72c119ce7",
    "state_tracker/v3/questions.py": "0d43eb12827237ee147e23d14f6cccb21b191ddcd1c36f104b167a7acd27f4ab",
    "state_tracker/v3/questions_v3.json": "892b0ea5ace3084bedb950d9cb28300b5bae3ae6116b597c66456f45e4391ed0",
    "output/eval_v3/rule_table_retail.json": "1d288c284351337e2316926d6ca0c68b5980fd5af2a6bdb22215202cb817cd3f",
    "output/eval_v3/rule_table_airline.json": "ea2f654a6b5e7d5f1e99bf76e24c08aef4199e4516e1ce2074e5fc27ddbd0c69",
    "guard/feedback_v3.py": "d7c7085eaeb413e7f373e8a4eb5df112b5a191d80ef975174889316d21870f5d",   # p10's final
    # --- v2 (frozen; the eval v2 manifest's hashes)
    "guard/tgr_tracker.py": "a8d65e8f2fb9857b6c88cc6da09776cefccd48026c48a5eb625dd2bd7aadc229",
    "output/predicate_types.json": "20dade34ca42965be3a3ae139749651b385b268de7d6bd4eb07ca12a21ee1889",
    "state_tracker/lookups_airline.json": "882ca35ed6a1bbda1ea97d1eed87dd36246b2111cc1d4d47c5645ce12b701dc7",
    "state_tracker/lookups_retail.json": "77918b7727831f8c18353f5b5dce89d7e05017aa4db11f31722ee23cc41044a4",
    "state_tracker/lookup_format.py": "934a074f660d4317bc8034f607d4ab9f8a240c5e9a698b8b22ce55b31937ed70",
    "state_tracker/replay.py": "6259af674649e29633999e5d5b5496397a5ad142e7a6c1cd368366796c86035c",
    "state_tracker/state.py": "a61b7f6214c33e27748c1bbefcee1700865b4654a19e58570ef8f75701542ea0",
    "state_tracker/tau_copy.py": "339bfc40d8aff4f31ce8eb32cf355ffeb8dd45a12f20707ff456a9baadc4a2cc",
    "from_shieldagent/runner/method_tgr/runtime.py": "895659215ab45db55b0ded2f5ff0caaba45864fd84e5d2fa946f8a5f0b5d5fb8",
    "from_shieldagent/runner/method_tgr/feedback.py": "6e9bb5c83fbe1c11f8ee40ba26e7c21a6ae5fcaed25aff10690af8b7a892c3d8",
    "from_shieldagent/runner/repro_runtime/mln.py": "6873ce704dab26664e103f680da9c2b9b4ab8ee6862e20548bc8778ca0340c37",
    "from_shieldagent/rules/retail/rule_set.json": "9e395e2fc259cdf228612c4cd078a5bb3836bad4fe42af4493ffc9359fb63d7b",
    "from_shieldagent/rules/airline/rule_set.json": "27e2eafa05fd919d41083e8d4dfeb7c4a6d9a789fa2ad7c5da645584d05bc5a4",
}


class FrozenInputChangedV3(RuntimeError):
    """A file of FROZEN_SHA256 differs from its recorded sha256 (or is missing): the v3 run stops."""


class FactFileProblem(RuntimeError):
    """The v3 fact file of a domain has problems (facts_format_v3.validate) or lacks a fact of the rule set."""


class JudgeCallRefused(RuntimeError):
    """The guard was asked for judge values that it was not given (it never calls an LLM judge)."""


# ----------------------------------------------------------------------------------------------- frozen inputs
def sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def check_frozen_v3(table: Optional[Dict[str, Optional[str]]] = None) -> Dict[str, Any]:
    """sha256 of every file of the table; raises FrozenInputChangedV3 if a recorded one differs or a file is missing.
    Returns {"sha256": {rel: sha}, "unrecorded": [rel, ...]} (entries with None)."""
    table = FROZEN_SHA256 if table is None else table
    got, unrecorded, bad = {}, [], []
    for rel, want in table.items():
        p = os.path.join(paths.PC_DIR, *rel.split("/"))
        if not os.path.isfile(p):
            if want is None:
                unrecorded.append(rel)
                got[rel] = None
                continue
            bad.append(f"{rel}: missing")
            continue
        got[rel] = h = sha256(p)
        if want is None:
            unrecorded.append(rel)
        elif h != want:
            bad.append(f"{rel}: sha256 {h} != recorded {want}")
    if bad:
        raise FrozenInputChangedV3("frozen v3 guard inputs changed: " + "; ".join(bad))
    return {"sha256": got, "unrecorded": unrecorded}


# ----------------------------------------------------------------------------------------------- answers hooks
class _Deferred(F.UseBlockingValue):
    """Raised by the probe hook at the first question: the fact needs a question (detail = the question id)."""
    kind = DEFERRED


class _Probe:
    """The answers hook of the first pass: no question is asked; the first ask stops the fact (problem DEFERRED).
    standin=True mimics questions.StandInAnswers (the offer helpers then read value_for, not ask)."""
    exhaustive = False

    def __init__(self, standin: bool):
        self.standin = bool(standin)
        self.stats = Q.Stats()
        self.where: Any = None

    def ask(self, qid: str, inputs: Dict[str, Any], *, fact: Optional[str] = None, part: Optional[str] = None
            ) -> dict:
        raise _Deferred(qid)

    def value_for(self, fact: Optional[str]) -> Optional[bool]:
        raise _Deferred(STANDIN_OFFER)


class _CountingHook:
    """Wraps an answers hook (questions.Questions or StandInAnswers) and counts its asks per question id."""

    def __init__(self, inner: Any):
        self.inner = inner
        self.asked: collections.Counter = collections.Counter()

    @property
    def standin(self) -> bool:
        return bool(getattr(self.inner, "standin", False))

    @property
    def exhaustive(self) -> bool:
        return bool(getattr(self.inner, "exhaustive", False))

    @property
    def stats(self) -> Any:
        return self.inner.stats

    @property
    def doc(self) -> Any:
        return getattr(self.inner, "doc", None)

    def ask(self, qid: str, inputs: Dict[str, Any], *, fact: Optional[str] = None, part: Optional[str] = None
            ) -> dict:
        self.asked[qid] += 1
        return self.inner.ask(qid, inputs, fact=fact, part=part)

    def value_for(self, fact: Optional[str]) -> Optional[bool]:
        self.asked[STANDIN_OFFER] += 1
        return self.inner.value_for(fact)


# ----------------------------------------------------------------------------------------------- small helpers
def _word(v: Optional[bool]) -> str:
    return "not set" if v is None else ("true" if v else "false")


def simple_message(text: str) -> str:
    """TGR's message without its closing "violated as things stand: do not repeat ..." line; a "What to do:" header
    left with no item after it is dropped too."""
    lines = [ln for ln in text.split("\n") if not (ln.startswith(CLOSING_PREFIX) and CLOSING_MARK in ln)]
    if lines and lines[-1].strip() == WHAT_TO_DO:
        lines.pop()
    return "\n".join(lines)


def _deferred_qid(res: dict) -> Optional[str]:
    for p in res.get("problems") or []:
        if p.get("kind") == DEFERRED:
            return p.get("detail") or "?"
    return None


def evidence_text(kind: str, res: dict) -> str:
    """The evidence TGR shows (frozen / simple messages) for a v3 value: its source and its parts' values."""
    parts = res.get("parts") or {}
    bits = [f"{pid} ({p.get('source')}) {_word(p.get('value'))}" for pid, p in parts.items()]
    probs = sorted({p.get("kind") for p in res.get("problems") or [] if p.get("kind")})
    return (f"v3 {kind}: " + ("; ".join(bits) if bits else "no part ran")
            + (f"; problems: {', '.join(probs)}" if probs else ""))


def fact_summary(kind: str, res: dict) -> Dict[str, Any]:
    """The compact per-fact entry of rec["v3"]["facts"] (p10's message check and p11 read it)."""
    return {"value": res.get("value"), "source": kind, "how": res.get("how"), "sources": list(res.get("source") or []),
            "parts": {pid: {"value": p.get("value"), "source": p.get("source"), "who": p.get("who"),
                            "how": p.get("how")} for pid, p in (res.get("parts") or {}).items()},
            "problems": [p.get("kind") for p in res.get("problems") or []],
            "deciding_item": res.get("deciding_item")}


def rule_decided(rule: dict, known: Dict[str, Optional[bool]], action: str) -> bool:
    """True when every row of the rule table entry (for this action) that fits the known values gives the same
    result. A value that is None (unknown, or not set yet) fits both rows."""
    fit = set()
    for row in rule["rows"]:
        if row.get("action") not in (None, action):
            continue
        if all(known.get(f) is None or known[f] == v for f, v in row["values"].items()):
            fit.add(bool(row["holds"]))
            if len(fit) > 1:
                return False
    return True


# ----------------------------------------------------------------------------------------------- the judge stand-in
class _NoLLMJudge(TGR):
    """Placed below TrackerTGR in TrackerTGRv3's class order: the only `_judge` TrackerTGR's own judge call reaches.
    It returns the given values exactly as fork/points_tgr.py GivenJudgeTGR does (the eval v2 offline guard), or
    raises JudgeCallRefused when none are given. It never calls an LLM."""

    def _given_store(self) -> threading.local:
        st = self.__dict__.get("_given_tls")
        if st is None:
            st = self.__dict__["_given_tls"] = threading.local()
        return st

    def set_given(self, judged: Optional[Dict[str, dict]]) -> None:
        """The saved judge values {name: {value, evidence}} for the next check (offline); None clears them."""
        self._given_store().values = judged

    def given(self) -> Optional[Dict[str, dict]]:
        return getattr(self._given_store(), "values", None)

    def _judge(self, step, a_text: str, circuit: List[str], names: List[str], meter) -> Dict[str, dict]:
        given = self.given()
        if given is None:
            raise JudgeCallRefused(f"{NAME}: judge values for {names} were asked, but none were given (this guard "
                                   f"never calls an LLM judge)")
        self.standin_calls += 1
        out = {}
        for n in names:
            v = given.get(n)
            out[n] = ({"value": v.get("value"), "evidence": v.get("evidence", "")} if v is not None
                      else {"value": None, "evidence": NOT_RETURNED})
        return out


# ----------------------------------------------------------------------------------------------- the guard
class TrackerTGRv3(TrackerTGR, _NoLLMJudge):
    """TrackerTGR (eval v2) with the v3 facts and no judge; see the module text."""

    def __init__(self, rule_set: dict, tools: List[dict], config: TGRConfig, domain: str,
                 lookups: Dict[str, dict], types: Dict[str, dict], *, facts: str = "v3",
                 meaning: str = "saved_judge", messages: str = "frozen", lazy: bool = True, answers: Any = None,
                 facts_doc: Optional[dict] = None, rule_table: Optional[dict] = None):
        check_switches(facts, meaning, messages, answers)
        super().__init__(rule_set, tools, config, domain, lookups, types)
        self.switches = {"facts": facts, "meaning": meaning, "messages": messages}
        self.lazy = bool(lazy)
        self.answers = answers
        self.facts_doc = facts_doc
        self.rule_table = rule_table
        if facts == "v3":
            if facts_doc is None or rule_table is None:
                raise ValueError("facts = v3 needs the fact file (facts_doc) and the rule table (rule_table)")
            missing = sorted(set(rule_set["predicates"]) - set(facts_doc.get("facts") or {}))
            if missing:
                raise FactFileProblem(f"{domain}: facts without a v3 entry: {missing}")
        self._rt_rules = {str(r["id"]): r for r in (rule_table or {}).get("rules", [])}
        self._v3tls = threading.local()
        self._lock = threading.Lock()
        self.counters: collections.Counter = collections.Counter()
        self.standin_calls = 0               # given-values judge stand-in (facts = v2): not an LLM call
        self.info: Dict[str, Any] = {}
        # Offline speed only: a callable (history, tool, args) -> State that must equal
        # build_state(history, {"tool": tool, "args": args}, domain) (an offline driver that walks a conversation
        # once and checks the equality). None (the default, and always online): build_state on every check.
        self.state_source: Optional[Any] = None

    # --------------------------------------------------------------------------------------------- counters
    def _count(self, key: str, n: int = 1) -> None:
        with self._lock:
            self.counters[key] += n

    # --------------------------------------------------------------------------------------------- TGR hooks
    def _step(self, conv, step) -> dict:
        self._v3tls.data = None
        self._v3tls.message = None
        t0 = time.time()
        rec = super()._step(conv, step)                      # TrackerTGR._step -> TGR._step (unchanged)
        d = self._v3tls.data
        if self.switches["facts"] == "v3" and d is None:
            rec["tracker"] = {"version": TRACKER_VERSION, "applied": False, "code_predicates": [],
                              "judge_skipped": False}
        rec["v3"] = self._v3_part(d, self._v3tls.message, round(time.time() - t0, 3))
        self._v3tls.data = None
        self._v3tls.message = None
        return rec

    def _judge(self, step, a_text: str, circuit: List[str], names: List[str], meter) -> Dict[str, dict]:
        if self.switches["facts"] == "v2":
            return TrackerTGR._judge(self, step, a_text, circuit, names, meter)
        t0 = time.time()
        values, errors, state_info = self.tracker_values(step, names, circuit=circuit)
        d = self._v3tls.data
        given = self.given() or {}
        changed = sorted(n for n in names if isinstance((given.get(n) or {}).get("value"), bool)
                         and values[n]["value"] is not None and given[n]["value"] is not values[n]["value"])
        self._tls.info = {
            "version": TRACKER_VERSION, "applied": True, "code_predicates": list(names), "judge_skipped": True,
            "judge_values": None,
            "tracker_values": {n: {"value": v["value"], "source": v["source"]} for n, v in values.items()},
            "replaced": list(names), "changed": changed, "lookup_errors": errors, "state": state_info,
            "seconds": round(time.time() - t0, 3)}
        d["changed_vs_saved_judge"] = changed
        return {n: {"value": values[n]["value"], "evidence": values[n]["evidence"], "source": values[n]["source"]}
                for n in names}

    def tracker_values(self, step, code: List[str], circuit: Optional[List[str]] = None
                       ) -> Tuple[Dict[str, dict], List[dict], Optional[dict]]:
        """facts = v2: TrackerTGR's own (unchanged). facts = v3: every fact of `code` from the v3 evaluator, on the
        state built WITH the pending call; the state, the view and the per-fact results are kept for the message.
        Never raises for a state or fact problem (blocking values, counted); hard stops of the answers hook
        (budget, network, real mode, answer not saved) and JudgeCallRefused pass through."""
        if self.switches["facts"] == "v2":
            return super().tracker_values(step, code)
        return self._v3_values(step, list(code), circuit)

    def _feedback(self, step, a_text, violated, current, judged, meter, rec) -> str:
        base = super()._feedback(step, a_text, violated, current, judged, meter, rec)     # TGR's own text
        mode = self.switches["messages"]
        if mode == "frozen":
            self._v3tls.message = {"mode": mode, "built": "frozen", "fallback": False}
            return base
        try:
            if mode == "simple":
                text = simple_message(base)
            else:
                d = self._v3tls.data
                if d is None:                                # a block with no fact (a rule on the action alone)
                    d = self._message_data(step)
                mod = importlib.import_module(FEEDBACK_MODULE)
                text = mod.build_message(self.domain, d["tool"], d["args"], violated, d["results"], d["state"],
                                         d["view"], self.rule_table, self.rule_set)
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"the {mode} message is empty or not a text ({type(text).__name__})")
            self._v3tls.message = {"mode": mode, "built": mode, "fallback": False}
            return text
        except Exception as e:  # noqa: BLE001 - counted; TGR's own message keeps TGR.step from retrying
            self._count("message_fallbacks")
            self._v3tls.message = {"mode": mode, "built": "frozen", "fallback": True,
                                   "error": f"{type(e).__name__}: {e}"[:400]}
            return base

    # --------------------------------------------------------------------------------------------- the v3 facts
    def _new_data(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        return {"tool": tool, "args": args, "state": None, "view": None, "state_info": None, "results": {},
                "kinds": {}, "state_errors": [], "fact_errors": [], "first_question": {},
                "questions": {"asked": collections.Counter(), "asked_facts": [], "skipped_facts": [],
                              "skipped_first_question": collections.Counter(), "pending_facts": 0},
                "standin": {}, "changed_vs_saved_judge": []}

    def _state_view(self, history: List[dict], tool: str, args: Dict[str, Any]
                    ) -> Tuple[Any, Any, Optional[dict], Dict[str, Any]]:
        """(state, view, state error or None, state counts). The state holds the pending call (not run)."""
        t0 = time.time()
        try:
            if self.state_source is not None:
                st = self.state_source(history, tool, args)
            else:
                st = build_state(history, {"tool": tool, "args": args}, domain=self.domain)
        except Exception as e:  # noqa: BLE001 - every fact takes its blocking value, counted
            err = {"kind": "state_build_error", "detail": f"{type(e).__name__}: {e}"[:400]}
            return None, None, err, {"error": err["detail"]}
        info = {"events": len(st.events), "mismatches": len(st.mismatches), "parse_problems": len(st.parse_problems),
                "problems": len(st.problems)}
        err = None
        if st.mismatches:
            err = {"kind": "replay_mismatch", "detail": f"{len(st.mismatches)} replayed output(s) differ from the "
                                                        f"conversation"}
        elif st.parse_problems:
            err = {"kind": "parse_problem", "detail": f"{len(st.parse_problems)} tool output(s) could not be parsed"}
        elif st.problems:
            err = {"kind": "state_problem", "detail": "; ".join(map(str, st.problems[:3]))[:400]}
        view = None
        try:
            view = MV.build_view(history, pending={"tool": tool, "args": args}, state=st, domain=self.domain)
            info["view_problems"] = len(view.problems)
        except Exception as e:  # noqa: BLE001 - every fact takes its blocking value, counted
            if err is None:
                err = {"kind": "view_error", "detail": f"{type(e).__name__}: {e}"[:400]}
        info["seconds"] = round(time.time() - t0, 3)
        return st, view, err, info

    def _message_data(self, step) -> Dict[str, Any]:
        tool = RESPOND if step.kind == "respond" else step.name
        args = step.arguments if isinstance(step.arguments, dict) else {}
        d = self._new_data(tool, args)
        d["state"], d["view"], _, d["state_info"] = self._state_view(step.history, tool, args)
        return d

    def _run(self, name: str, entry: dict, st: Any, args: Dict[str, Any], view: Any, hook: Any
             ) -> Tuple[Optional[dict], Optional[dict]]:
        """(evaluator result, None) or (None, error). Hard stops pass through."""
        try:
            return F.evaluate(entry, st, args, view=view, answers=hook, name=name), None
        except HARD_STOPS:
            raise
        except JudgeCallRefused:
            raise
        except Exception as e:  # noqa: BLE001 - the fact takes its blocking value, counted (P9.3)
            return None, {"fact": name, "kind": "fact_error", "error": type(e).__name__,
                          "detail": f"{type(e).__name__}: {e}"[:400]}

    def _given_value(self, name: str) -> Optional[bool]:
        g = (self.given() or {}).get(name)
        v = g.get("value") if isinstance(g, dict) else None
        return v if isinstance(v, bool) else None

    def _answer(self, name: str, entry: dict, st: Any, args: Dict[str, Any], view: Any, d: Dict[str, Any]
                ) -> Tuple[dict, str]:
        """A fact that needs a question, evaluated with its answers: (result, source kind)."""
        qs = d["questions"]
        if self.switches["meaning"] == "tiny":
            hook = _CountingHook(self.answers)
            r, err = self._run(name, entry, st, args, view, hook)
            qs["asked"].update(hook.asked)
            if err is not None:
                return self._error_result(entry, name, err, d), "fact_error"
            return r, ("question" if not r["problems"] else "blocking_value")
        gv = self._given_value(name)
        if gv is not None:
            hook = _CountingHook(Q.StandInAnswers({name: gv}))
            r, err = self._run(name, entry, st, args, view, hook)
            qs["asked"].update(hook.asked)
            d["standin"][name] = gv
            if err is not None:
                return self._error_result(entry, name, err, d), "fact_error"
            return r, ("saved_judge" if not r["problems"] else "blocking_value")
        # the saved judge value is unknown: the answer yes and the answer no; code decides only if both agree
        d["standin"][name] = None
        h1, h0 = _CountingHook(Q.StandInAnswers({name: True})), _CountingHook(Q.StandInAnswers({name: False}))
        r1, e1 = self._run(name, entry, st, args, view, h1)
        r0, e0 = self._run(name, entry, st, args, view, h0)
        qs["asked"].update(h0.asked)
        if e1 is not None or e0 is not None:
            return self._error_result(entry, name, e0 or e1, d), "fact_error"
        parts = {}
        for pid, p0 in (r0.get("parts") or {}).items():
            p1 = (r1.get("parts") or {}).get(pid) or {}
            same = p1.get("value") is p0.get("value") and p1.get("how") == p0.get("how")
            parts[pid] = p0 if same else dict(p0, value=None, how="saved_unknown")
        if r1["value"] is r0["value"] and r1["how"] == r0["how"]:
            res = dict(r0, parts=parts)
            return res, ("code" if r0["how"] == "combine" else "blocking_value")
        res = dict(r0, value=None, how="saved_unknown", parts=parts)
        return res, "saved_unknown"

    def _error_result(self, entry: dict, name: str, err: dict, d: Dict[str, Any]) -> dict:
        d["fact_errors"].append(err)
        self._count("fact_errors")
        return F.blocking_result(entry, err["kind"], err["detail"], name=name)

    def _needed(self, name: str, known: Dict[str, Optional[bool]], circuit: List[str], action: str) -> bool:
        """Some rule of the circuit that holds the fact is not decided by the known values."""
        for rid in circuit:
            r = self._rt_rules.get(str(rid))
            if r is None:                                      # not tabled (a temporal rule): always needed
                if name in self.aspm.rules[rid].atoms:
                    return True
                continue
            if name in r["facts"] and not rule_decided(r, known, action):
                return True
        return False

    def _v3_values(self, step, names: List[str], circuit: Optional[List[str]]
                   ) -> Tuple[Dict[str, dict], List[dict], Optional[dict]]:
        t0 = time.time()
        tool = RESPOND if step.kind == "respond" else step.name
        args = step.arguments if isinstance(step.arguments, dict) else {}
        if circuit is None:
            circuit = self.aspm.circuit([tool]) if tool in self.aspm.action_predicates else []
        d = self._new_data(tool, args)
        self._v3tls.data = d
        st, view, serr, info = self._state_view(step.history, tool, args)
        d.update(state=st, view=view, state_info=info)
        entries = self.facts_doc["facts"]
        results: Dict[str, dict] = {}
        kinds: Dict[str, str] = {}
        if serr is not None:
            d["state_errors"].append(serr)
            self._count("state_errors")
            for n in names:
                results[n] = F.blocking_result(entries[n], serr["kind"], serr["detail"], name=n)
                kinds[n] = "state_error"
        else:
            probe = _Probe(standin=self.switches["meaning"] == "saved_judge")
            probed: Dict[str, dict] = {}
            for n in names:                                    # 1. every code part (the probe stops at a question)
                r, err = self._run(n, entries[n], st, args, view, probe)
                if err is not None:
                    results[n], kinds[n] = self._error_result(entries[n], n, err, d), "fact_error"
                    continue
                qid = _deferred_qid(r)
                if qid is not None:
                    probed[n] = r
                    d["first_question"][n] = qid
                else:
                    results[n], kinds[n] = r, ("code" if not r["problems"] else "blocking_value")
            d["questions"]["pending_facts"] = len(probed)
            known = {n: results[n]["value"] for n in results}
            remaining = [n for n in names if n in probed]
            while remaining:                                   # 2. the questions some rule still needs
                pick = next((n for n in remaining if not self.lazy or self._needed(n, known, circuit, tool)), None)
                if pick is None:
                    break
                remaining.remove(pick)
                results[pick], kinds[pick] = self._answer(pick, entries[pick], st, args, view, d)
                known[pick] = results[pick]["value"]
                d["questions"]["asked_facts"].append(pick)
            for n in remaining:                                # 3. no rule needs them: the blocking value
                results[n], kinds[n] = self._skipped(entries[n], probed[n]), "lazy_skip"
                d["questions"]["skipped_facts"].append(n)
                d["questions"]["skipped_first_question"][d["first_question"][n]] += 1
        for n in names:                                        # the source kind, for the message builder (p10)
            results[n]["v3_source"] = kinds[n]
        d["results"], d["kinds"] = results, kinds
        out = {n: {"value": results[n]["value"], "source": kinds[n], "evidence": evidence_text(kinds[n], results[n])}
               for n in names}
        errors = [{"predicate": e["fact"], "error": e["detail"]} for e in d["fact_errors"]]
        if serr is not None:
            errors.insert(0, {"predicate": None, "error": f"state: {serr['kind']}: {serr['detail']}"})
        info = dict(info or {}, seconds=round(time.time() - t0, 3))
        return out, errors, json.loads(json.dumps(info, default=str))

    @staticmethod
    def _skipped(entry: dict, probed: dict) -> dict:
        res = dict(probed, value=entry["blocking_value"], how="lazy_skip",
                   problems=[p for p in probed.get("problems") or [] if p.get("kind") != DEFERRED])
        res["parts"] = {pid: (dict(p, value=None, how="lazy_skip", detail=None) if p.get("source") == "question"
                              else p) for pid, p in (probed.get("parts") or {}).items()}
        return res

    # --------------------------------------------------------------------------------------------- the record
    def _v3_part(self, d: Optional[Dict[str, Any]], message: Optional[dict], seconds: float) -> Dict[str, Any]:
        out: Dict[str, Any] = {"version": VERSION, "switches": dict(self.switches), "lazy": self.lazy,
                               "facts": None, "unknown": [], "state_errors": [], "fact_errors": [],
                               "questions": None, "standin": {}, "message": message, "seconds": seconds}
        if d is None:
            return out
        res, kinds = d["results"], d["kinds"]
        qs = d["questions"]
        out.update(
            facts={n: dict(fact_summary(kinds[n], r), **({"first_question": d["first_question"][n]}
                                                          if n in d["first_question"] else {}))
                   for n, r in res.items()},
            unknown=sorted(n for n, r in res.items() if r.get("value") is None),
            state_errors=list(d["state_errors"]), fact_errors=list(d["fact_errors"]),
            questions={"asked": dict(sorted(qs["asked"].items())), "asked_facts": list(qs["asked_facts"]),
                       "skipped_facts": list(qs["skipped_facts"]),
                       "skipped_first_question": dict(sorted(qs["skipped_first_question"].items())),
                       "pending_facts": qs["pending_facts"]},
            standin=dict(d["standin"]), changed_vs_saved_judge=list(d["changed_vs_saved_judge"]))
        return out

    def last_data(self) -> Optional[Dict[str, Any]]:
        """The kept data of the check in progress on this thread (state, view, results); None outside a check."""
        return getattr(self._v3tls, "data", None)


# ----------------------------------------------------------------------------------------------- building
def check_switches(facts: str, meaning: str, messages: str, answers: Any = None) -> None:
    if facts not in FACTS:
        raise ValueError(f"facts must be one of {FACTS}, not {facts!r}")
    if meaning not in MEANINGS:
        raise ValueError(f"meaning must be one of {MEANINGS}, not {meaning!r}")
    if messages not in MESSAGES:
        raise ValueError(f"messages must be one of {MESSAGES}, not {messages!r}")
    if facts == "v2" and meaning != "saved_judge":
        raise ValueError("facts = v2 has no tiny questions: it needs meaning = saved_judge")
    if messages == "rule" and facts != "v3":
        raise ValueError("messages = rule needs facts = v3 (the message is built from the v3 facts' parts)")
    if meaning == "tiny":
        if answers is None or not callable(getattr(answers, "ask", None)):
            raise ValueError("meaning = tiny needs an answers hook with ask() (questions.Questions)")
        if getattr(answers, "standin", False):
            raise ValueError("meaning = tiny cannot use the stand-in hook (that is meaning = saved_judge)")


def load_rule_table(domain: str) -> dict:
    with open(os.path.join(paths.PC_DIR, *RULE_TABLE_REL.format(domain).split("/")), encoding="utf-8") as f:
        return json.load(f)


_DOCS: Dict[str, dict] = {}
_DOCS_LOCK = threading.Lock()


def load_checked_facts(domain: str) -> dict:
    """The domain's v3 fact file, validated once per process (0 problems, or FactFileProblem)."""
    with _DOCS_LOCK:
        if domain not in _DOCS:
            doc = F.load_facts(domain)
            problems = F.validate(doc, domain)
            if problems:
                raise FactFileProblem(f"{domain}: {len(problems)} fact file problems: {problems[:3]}")
            _DOCS[domain] = doc
        return _DOCS[domain]


def build(domain: str, tools: Optional[List[dict]] = None, *, facts: str = "v3", meaning: str = "saved_judge",
          messages: str = "frozen", lazy: bool = True, answers: Any = None, rules_dir: Optional[str] = None,
          frozen_table: Optional[Dict[str, Optional[str]]] = None, facts_doc: Optional[dict] = None
          ) -> TrackerTGRv3:
    """The v3 guard of one domain, built as guard/tgr_tracker.py builds the eval v2 guard (frozen rules, frozen inputs
    checked), plus the v3 checks: FROZEN_SHA256 (a changed file stops the run) and the fact file (0 problems).
    facts_doc: another fact file (tests only)."""
    check_switches(facts, meaning, messages, answers)
    if domain not in paths.DOMAINS:
        raise ValueError(f"unknown domain {domain!r}")
    rules_dir = rules_dir or os.path.join(paths.RULES_DIR, domain)
    rs_path = os.path.join(rules_dir, "rule_set.json")
    rs = load_rule_set(rs_path)
    if rs["flags"]["a"] is not True or rs["flags"]["b"] is not True:
        raise ValueError(f"{NAME} needs a rule set built with A and B; {rules_dir} has {rs['flags']}")
    frozen_v2 = T.check_frozen()
    frozen = check_frozen_v3(frozen_table)
    problems = L.check_lookups(domain)
    if problems:
        raise T.FrozenInputChanged(f"lookup file problems: {problems[:3]}")
    types = load_types()[domain]
    missing = sorted(set(rs["predicates"]) - set(types))
    if missing:
        raise ValueError(f"predicates without a type: {missing}")
    doc = rt = None
    if facts == "v3":
        doc = facts_doc if facts_doc is not None else load_checked_facts(domain)
        rt = load_rule_table(domain)
    config = TGRConfig(actionable_feedback=True, judge_effort=T.JUDGE_EFFORT, epsilon=T.EPSILON)
    tgr = TrackerTGRv3(rs, list(tools or []), config, domain, L.load_lookups(domain), types, facts=facts,
                       meaning=meaning, messages=messages, lazy=lazy, answers=answers, facts_doc=doc, rule_table=rt)
    build_state([], None, domain=domain)          # load the τ-bench copy and data once, before worker threads
    tgr.info = {"guard": NAME, "version": VERSION, "domain": domain, "switches": dict(tgr.switches), "lazy": lazy,
                "rules_dir": rules_dir, "rule_set_sha256": sha256(rs_path), "frozen_sha256_v2": frozen_v2,
                "frozen_sha256": frozen["sha256"], "unrecorded": frozen["unrecorded"],
                "answers": type(answers).__name__ if answers is not None else None,
                "backend": getattr(getattr(answers, "backend", None), "name", None)}
    return tgr


# ----------------------------------------------------------------------------------------------- offline registry
# The offline variants (fork/offline_v3.py registry names): meaning = saved_judge (the stand-in) only; a tiny
# variant needs an answers hook: register_tiny().
VARIANTS: Dict[str, Dict[str, Any]] = {
    "v3": {"facts": "v3", "meaning": "saved_judge", "messages": "frozen", "lazy": True},
    "v3_full": {"facts": "v3", "meaning": "saved_judge", "messages": "frozen", "lazy": False},
    "v3_simple": {"facts": "v3", "meaning": "saved_judge", "messages": "simple", "lazy": True},
    "v3_rule": {"facts": "v3", "meaning": "saved_judge", "messages": "rule", "lazy": True},
    "v3_v2facts": {"facts": "v2", "meaning": "saved_judge", "messages": "frozen", "lazy": True},
}
_REGISTERED: Dict[str, Any] = {}


def register(names: Optional[List[str]] = None) -> List[str]:
    """Add the offline variants to fork/offline_v3.py's registry (once per process; again changes nothing).
    Called by the drivers, never at import."""
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
    """Register (or replace) an offline variant with meaning = tiny and this answers hook (fake answers in p9)."""
    from fork import offline_v3 as O
    check_switches("v3", "tiny", messages, answers)
    factory = functools.partial(build, facts="v3", meaning="tiny", messages=messages, lazy=lazy, answers=answers)
    O.register_guard(name, lambda domain, f=factory: f(domain), replace=True)
    _REGISTERED[name] = factory
    return name
