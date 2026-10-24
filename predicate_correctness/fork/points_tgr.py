"""Eval v2 Part 3 (fork/points_tgr.py): frozen TGR and TGR + tracker, run offline on one saved guard check.

No LLM call. The judge's values are given (saved), not asked. Everything else is the guards' own code:
  - frozen TGR (branch A) = the copied runtime from_shieldagent/runner/method_tgr/runtime.py (class TGR), with only
    its judge call (`_judge`) replaced by the given values;
  - TGR + tracker (branch B) = guard/tgr_tracker.py's TrackerTGR (version b), with the same replacement placed
    below it. So the tracker part runs exactly as online: the state is built from the executed history
    (state_tracker/state.py build_state), the frozen lookups run, the values are merged (merge), and the judge is
    skipped when every predicate is a code type with a known value.
  - circuit, decision (repro_runtime mln.decide, epsilon 0.1), violated rules and the block message (method_tgr
    feedback.py, component C) are the runtime's own `_step` code.

Main API:
    off = OfflineGuards("retail")
    rec = off.check("A", history, msg, n_exec, past, judged)   # frozen TGR; judged = {name: {value, evidence}}
    rec = off.check("B", history, msg, n_exec, past, judged)   # TGR + tracker (judged = the judge's own values)
  rec is the guard record the online guard would write (action_allowed, margin, violated_rules, feedback_text,
  judge, trace_position, ...; B also has `tracker`).
    judge_prompt(...), judge_cache_key(...), judge_evidence_from_cache(...): find the judge's own evidence of a
  tgr_tracker run in that run's judge cache (the online guard keeps only the judge's values when the tracker changed
  one; the cache file of the same judge call has the evidence too).

Never sets any global LLM client: importing this module changes nothing. Never imports gold code.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

from guard import tgr_tracker                                            # sets up the runner path (runner_path)
from method_tgr import prompts as tgr_prompts                            # noqa: E402  (runner copy)
from method_tgr.runtime import JUDGE_SCHEMA, TGR, Conversation, TGRConfig, load_rule_set   # noqa: E402
from repro_core.llm import llm_config                                    # noqa: E402  (runner copy; reads config.json)
from repro_core.taubench_steps import render_history                     # noqa: E402
from repro_online.guards import make_step                                # noqa: E402

from state_tracker import lookup_format as L                             # noqa: E402
from state_tracker import paths                                          # noqa: E402
from state_tracker.predicate_types import load_types                     # noqa: E402

NOT_RETURNED = "(not returned by the judge)"       # what TGR writes when the judge skipped a predicate
DEFAULT_FEEDBACK = "BLOCKED by policy guardrail."   # what the episode loop sends when a block has no text
JUDGE_STAGE, JUDGE_SCHEMA_NAME = "tgr_judge", "predicate_values"


class GivenJudgeTGR(TGR):
    """The copied TGR with its judge call replaced by given values (set with set_given before each check)."""

    def _given_store(self) -> threading.local:
        st = self.__dict__.get("_given_tls")
        if st is None:
            st = self.__dict__["_given_tls"] = threading.local()
        return st

    def set_given(self, judged: Dict[str, dict]) -> None:
        self._given_store().values = judged

    def _judge(self, step, a_text: str, circuit: List[str], names: List[str], meter) -> Dict[str, dict]:
        given = getattr(self._given_store(), "values", None)
        if given is None:
            raise RuntimeError("GivenJudgeTGR: no judge values given (set_given was not called)")
        self._given_store().asked = list(names)
        out = {}
        for n in names:
            v = given.get(n)
            out[n] = ({"value": v.get("value"), "evidence": v.get("evidence", "")} if v is not None
                      else {"value": None, "evidence": NOT_RETURNED})
        return out

    def asked(self) -> Optional[List[str]]:
        """The predicate names of the last judge call (None if the judge was not called)."""
        return getattr(self._given_store(), "asked", None)


class OfflineTrackerTGR(tgr_tracker.TrackerTGR, GivenJudgeTGR):
    """guard/tgr_tracker.py's TrackerTGR; its call to the judge (super()._judge) reaches GivenJudgeTGR._judge."""


class OfflineGuards:
    """Both guards of one domain, built as guard/tgr_tracker.py builds them (frozen rules, frozen inputs checked)."""

    def __init__(self, domain: str, rules_dir: Optional[str] = None):
        if domain not in paths.DOMAINS:
            raise ValueError(f"unknown domain {domain!r}")
        rules_dir = rules_dir or os.path.join(paths.RULES_DIR, domain)
        rs = load_rule_set(os.path.join(rules_dir, "rule_set.json"))
        if rs["flags"]["a"] is not True or rs["flags"]["b"] is not True:
            raise ValueError(f"the rule set in {rules_dir} is not built with A and B")
        tgr_tracker.check_frozen()
        problems = L.check_lookups(domain)
        if problems:
            raise tgr_tracker.FrozenInputChanged(f"lookup file problems: {problems[:3]}")
        config = TGRConfig(actionable_feedback=True, judge_effort=tgr_tracker.JUDGE_EFFORT,
                           epsilon=tgr_tracker.EPSILON)
        self.domain = domain
        self.rule_set = rs
        self.frozen = GivenJudgeTGR(rs, [], config)
        self.tracker = OfflineTrackerTGR(rs, [], config, domain, L.load_lookups(domain), load_types()[domain])

    def guard(self, which: str) -> GivenJudgeTGR:
        if which == "A":
            return self.frozen
        if which == "B":
            return self.tracker
        raise ValueError(f"which must be 'A' (frozen TGR) or 'B' (TGR + tracker), not {which!r}")

    def check(self, which: str, history: List[dict], msg: dict, n_exec: int, past: List[Any],
              judged: Dict[str, dict]) -> dict:
        """The guard record of one check: history = executed messages before the attempt, msg = the agent's
        message (one tool call or a text), n_exec = executed steps before, past = the guard's trace."""
        tgr = self.guard(which)
        tgr.set_given(judged)
        step = make_step(list(history), msg, n_exec)
        rec = tgr._step(Conversation(trace=list(past)), step)
        rec["trace_len_before"] = len(past)
        return rec


# ----------------------------------------------------------------------------------------------- the judge's own values
def judge_names(tgr: TGR, circuit: List[str]) -> List[str]:
    """The predicates TGR asks the judge for, as TGR._step computes them."""
    aspm = tgr.aspm
    return sorted({n for r in circuit for n in aspm.rules[r].atoms} - aspm.action_predicates)


def judge_prompt(tgr: TGR, history: List[dict], a_text: str, circuit: List[str], names: List[str]) -> Tuple[str, str]:
    """(system, user) of TGR's judge call. The same text as method_tgr/runtime.py TGR._judge (lines 122-128)."""
    aspm = tgr.aspm
    rules = "\n".join(f"[{r}] {aspm.rules[r].description}\n    logic: {aspm.rules[r].logic}" for r in circuit)
    preds = "\n".join(f"- {n}: {aspm.descriptions.get(n, '')}"
                      + (f" (evidence from: {', '.join(tgr.predicates[n]['source'])})"
                         if tgr.grounded and tgr.predicates.get(n, {}).get("source") else "") for n in names)
    facts = "\n".join(f"- {b['text']}" for b in tgr.rule_set.get("background", [])) or "(none)"
    return tgr_prompts.render("judge", history=render_history(history, max_chars=tgr.config.history_chars),
                              action=a_text, rules=rules, facts=facts, predicates=preds)


def judge_cache_key(system: str, user: str, model: str, effort: str,
                    max_output_tokens: Optional[int] = None) -> str:
    """The cache key of the judge call (policy_pipeline/llm.py LLM.call, method_tgr/llm.py structured)."""
    params = {"model": model, "effort": effort,
              "max_output_tokens": max_output_tokens or llm_config()["max_output_tokens"],
              "schema_name": JUDGE_SCHEMA_NAME, "schema": JUDGE_SCHEMA, "sample": 0}
    return hashlib.sha256(json.dumps({"system": system, "user": user, "params": params},
                                     sort_keys=True).encode()).hexdigest()


def judge_evidence_from_cache(tgr: TGR, cache_dir: Optional[str], history: List[dict], rec: dict, model: str
                              ) -> Tuple[Optional[Dict[str, dict]], str]:
    """The judge's own answer {name: {value, evidence}} for a saved guard record, from the run's judge cache.
    Returns (answer or None, status). Status: 'found', 'no cache folder', 'not in cache', 'unreadable'."""
    if not cache_dir or not os.path.isdir(cache_dir):
        return None, "no cache folder"
    names = judge_names(tgr, rec["circuit"])
    system, user = judge_prompt(tgr, history, rec["action_text"], rec["circuit"], names)
    key = judge_cache_key(system, user, model, tgr.config.judge_effort)
    path = os.path.join(cache_dir, key[:2], key + ".json")
    if not os.path.exists(path):
        return None, "not in cache"
    try:
        with open(path, encoding="utf-8") as f:
            parsed = json.load(f)["parsed"]
        got = {p["name"]: {"value": {"true": True, "false": False, "unknown": None}[p["value"]],
                           "evidence": p["evidence"]} for p in parsed["predicates"] if p["name"] in names}
    except (OSError, KeyError, ValueError, TypeError):
        return None, "unreadable"
    for n in names:
        got.setdefault(n, {"value": None, "evidence": NOT_RETURNED})
    return got, "found"


def own_judge_values(rec: dict) -> Dict[str, Optional[bool]]:
    """The judge's own values of a tgr_tracker guard record (tracker.judge_values); {} if the judge was skipped."""
    return dict(((rec.get("tracker") or {}).get("judge_values")) or {})


def own_judge_answer(tgr: TGR, rec: dict, history: List[dict], cache_dir: Optional[str], model: str
                     ) -> Tuple[Dict[str, dict], Dict[str, Any]]:
    """The judge's own answer {name: {value, evidence}} of a tgr_tracker guard record.

    Values: tracker.judge_values. Evidence: the saved `judge` entry where the tracker did not change the value (then
    the guard kept the judge's evidence); for a changed value, the judge's evidence from the run's judge cache, or ""
    if it is not there. info = {evidence: {name: 'saved' | 'cache' | 'missing'}, cache: status, problems: [...]}."""
    jv = own_judge_values(rec)
    changed = set((rec.get("tracker") or {}).get("changed") or [])
    saved = rec.get("judge") or {}
    out: Dict[str, dict] = {}
    info: Dict[str, Any] = {"evidence": {}, "cache": None, "problems": []}
    cached = None
    if changed:
        cached, info["cache"] = judge_evidence_from_cache(tgr, cache_dir, history, rec, model)
        if cached is not None:
            bad = [n for n in jv if cached.get(n, {}).get("value") is not jv[n]]
            if bad:
                info["problems"].append(f"cached judge values differ from tracker.judge_values: {bad}")
                cached = None
                info["cache"] = "cache values differ"
    for n, v in jv.items():
        s = saved.get(n) or {}
        if n in changed:
            if cached is not None:
                out[n] = {"value": v, "evidence": cached[n]["evidence"]}
                info["evidence"][n] = "cache"
            else:
                out[n] = {"value": v, "evidence": ""}
                info["evidence"][n] = "missing"
        else:
            if s.get("value") is not v:
                info["problems"].append(f"{n}: saved value {s.get('value')!r} != judge value {v!r} but not changed")
            out[n] = {"value": v, "evidence": s.get("evidence", "")}
            info["evidence"][n] = "saved"
    return out, info


def saved_judge_answer(rec: dict) -> Dict[str, dict]:
    """The judge's answer of a frozen TGR guard record: {name: {value, evidence}} (as TGR._judge returned it)."""
    return {n: {"value": v.get("value"), "evidence": v.get("evidence", "")} for n, v in (rec.get("judge") or {}).items()}


def feedback_of(rec: dict) -> Optional[str]:
    """The block message the episode loop sends for a guard record (None when the guard allows)."""
    if rec.get("action_allowed", True):
        return None
    return rec.get("feedback_text") or DEFAULT_FEEDBACK
