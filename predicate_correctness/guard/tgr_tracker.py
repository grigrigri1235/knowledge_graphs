"""Part 10: the guard "TGR + tracker" (p10.md, "The guard").

Base: frozen TGR, as the copied runner runs it (from_shieldagent/runner/method_tgr/runtime.py, used unchanged): the
frozen rule set (from_shieldagent/rules/<domain>/rule_set.json), the same judge prompt, the same decision formula
(ε = 0.1, all weights 1) and the same feedback (component C).

The one change, version (b) of Part 8. Before the decision, for the predicates of the tool's rules:
  1. code-type predicates (output/predicate_types.json: argument, database fact, event) get the tracker's value:
     the state is built from the executed conversation (state_tracker/state.py build_state, as in Part 4) and the
     frozen lookup runs on it with the pending call's arguments (state_tracker/lookup_format.py,
     state_tracker/lookups_<domain>.json);
  2. if a lookup gives unknown, or fails, the judge's value is kept (version b; a failure is logged, never raised);
  3. the judge is called exactly as TGR calls it (same prompt, all predicates of the rules), unless every predicate is
     a code type and every lookup gave true or false: then the judge is not called.

The decision and the feedback then use these values. Each guard record gets:
  - `judge`: the values used, per predicate {value, evidence, source: "judge" | "tracker"};
  - `tracker`: {version, code_predicates, judge_values (the judge's own values; null if not called), tracker_values,
    replaced (values taken from the tracker), changed (replaced and different from the judge's value), judge_skipped,
    lookup_errors, state (counts), seconds}.

Our code. It imports the runner copy through guard/runner_path.py and never imports gold code.
"""
from __future__ import annotations

import hashlib
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

from method_tgr.runtime import TGR, TGRConfig, load_rule_set              # noqa: E402  (runner copy)
from repro_online.guards import TGRGuard                                 # noqa: E402  (runner copy)

from state_tracker import lookup_format as L                             # noqa: E402
from state_tracker import paths                                          # noqa: E402
from state_tracker.predicate_types import TYPES_JSON, is_code_type, load_types   # noqa: E402
from state_tracker.state import build_state                              # noqa: E402

NAME = "tgr_tracker"
VERSION = "b"                 # Part 8: a tracker unknown is replaced by the judge's value
JUDGE_EFFORT = "medium"       # as repro_online/guards.py::TGRGuard
EPSILON = 0.1

# Frozen inputs (docs/planning/state_tracking_exp/overview.md). The guard refuses to start if one differs.
FROZEN_SHA256 = {
    TYPES_JSON: "20dade34ca42965be3a3ae139749651b385b268de7d6bd4eb07ca12a21ee1889",
    L.lookups_path("airline"): "882ca35ed6a1bbda1ea97d1eed87dd36246b2111cc1d4d47c5645ce12b701dc7",
    L.lookups_path("retail"): "77918b7727831f8c18353f5b5dce89d7e05017aa4db11f31722ee23cc41044a4",
}


class FrozenInputChanged(RuntimeError):
    """A frozen input file (types, lookups) differs from its recorded sha256."""


def sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def check_frozen() -> Dict[str, str]:
    """sha256 of every frozen input; raises FrozenInputChanged if one differs."""
    got = {}
    for path, want in FROZEN_SHA256.items():
        got[os.path.relpath(path, paths.PC_DIR)] = h = sha256(path)
        if h != want:
            raise FrozenInputChanged(f"{path}: sha256 {h} != frozen {want}")
    return got


def tracker_evidence(lookup: dict, detail: dict) -> str:
    """The evidence text for a value set by the tracker (shown in the feedback when it differs from the judge)."""
    text = "State tracker: " + lookup["plain"].strip()
    if detail.get("missing"):
        text += " No earlier tool output or call argument gives it."
    return text


class TrackerTGR(TGR):
    """method_tgr.runtime.TGR with the code-type values replaced by the tracker's (version b).

    Only `_judge` and `_step` are wrapped; the rest of TGR (rules, decision, feedback, trace) runs unchanged."""

    def __init__(self, rule_set: dict, tools: List[dict], config: TGRConfig, domain: str,
                 lookups: Dict[str, dict], types: Dict[str, dict]):
        super().__init__(rule_set, tools, config)
        self.domain = domain
        self.lookups = lookups
        self.code_types = {n: e["type"] for n, e in types.items() if is_code_type(e["type"])}
        self._tls = threading.local()

    # --------------------------------------------------------------------------------------------- TGR hooks
    def _step(self, conv, step) -> dict:
        self._tls.info = None
        rec = super()._step(conv, step)
        info = self._tls.info
        rec["tracker"] = info if info is not None else {"version": VERSION, "code_predicates": [],
                                                        "judge_skipped": False, "applied": False}
        self._tls.info = None
        return rec

    def _judge(self, step, a_text: str, circuit: List[str], names: List[str], meter) -> Dict[str, dict]:
        t0 = time.time()
        code = [n for n in names if n in self.code_types]
        tv, errors, state_info = self.tracker_values(step, code)
        known = {n: v for n, v in tv.items() if v.get("value") is not None and not v.get("error")}
        skip = bool(names) and len(code) == len(names) and len(known) == len(code)
        judged = None if skip else super()._judge(step, a_text, circuit, names, meter)
        merged, replaced, changed = self.merge(names, judged, known)
        self._tls.info = {
            "version": VERSION, "applied": True, "code_predicates": code,
            "judge_skipped": skip,
            "judge_values": None if judged is None else {n: judged[n].get("value") for n in names},
            "tracker_values": {n: {k: v[k] for k in ("value", "missing", "error") if k in v} for n, v in tv.items()},
            "replaced": replaced, "changed": changed, "lookup_errors": errors, "state": state_info,
            "seconds": round(time.time() - t0, 3),
        }
        return merged

    # --------------------------------------------------------------------------------------------- our part
    @staticmethod
    def merge(names: List[str], judged: Optional[Dict[str, dict]], known: Dict[str, dict]
              ) -> Tuple[Dict[str, dict], List[str], List[str]]:
        """The values used for the decision: the tracker's where it gave true or false, the judge's otherwise.
        Where the two agree, the judge's evidence is kept (so the feedback text is TGR's)."""
        merged, replaced, changed = {}, [], []
        for n in names:
            j = (judged or {}).get(n)
            if n in known:
                t = known[n]["value"]
                same = j is not None and j.get("value") is t
                merged[n] = {"value": t, "evidence": j["evidence"] if same else known[n]["evidence"],
                             "source": "tracker"}
                replaced.append(n)
                if j is not None and not same:
                    changed.append(n)
            else:
                merged[n] = dict(j or {"value": None, "evidence": "(not returned by the judge)"}, source="judge")
        return merged, replaced, changed

    def tracker_values(self, step, code: List[str]) -> Tuple[Dict[str, dict], List[dict], Optional[dict]]:
        """Run the frozen lookups for the code-type predicates on the state before the step.
        Never raises: a problem gives value None with an "error", and is listed in the errors."""
        if not code:
            return {}, [], None
        t0 = time.time()
        args = step.arguments if isinstance(step.arguments, dict) else {}
        try:
            st = build_state(step.history, {"tool": step.name, "args": args}, domain=self.domain)
        except Exception as e:  # noqa: BLE001 - logged; the judge's values are used
            err = f"state: {type(e).__name__}: {e}"
            return ({n: {"value": None, "error": err} for n in code},
                    [{"predicate": None, "error": err}], {"error": err})
        state_info = {"events": len(st.events), "mismatches": len(st.mismatches),
                      "parse_problems": len(st.parse_problems), "problems": len(st.problems),
                      "seconds": round(time.time() - t0, 3)}
        bad_state = []
        if st.mismatches:
            bad_state.append(f"{len(st.mismatches)} replayed output(s) differ from the conversation")
        if st.parse_problems:
            bad_state.append(f"{len(st.parse_problems)} tool output(s) could not be parsed")
        if st.problems:
            bad_state.append("; ".join(st.problems[:3]))
        if bad_state:
            err = "state: " + "; ".join(bad_state)
            state_info["detail"] = {"mismatches": st.mismatches[:3], "parse_problems": st.parse_problems[:3],
                                    "problems": st.problems[:3]}
            return ({n: {"value": None, "error": err} for n in code},
                    [{"predicate": None, "error": err}], json.loads(json.dumps(state_info, default=str)))
        out, errors = {}, []
        for n in code:
            lk = self.lookups.get(n)
            if lk is None:
                out[n] = {"value": None, "error": "no lookup for this predicate"}
                errors.append({"predicate": n, "error": out[n]["error"]})
                continue
            try:
                d = L.evaluate_detail(lk, st, args=args)
            except Exception as e:  # noqa: BLE001 - logged; the judge's value is used
                out[n] = {"value": None, "error": f"{type(e).__name__}: {e}"}
                errors.append({"predicate": n, "error": out[n]["error"]})
                continue
            out[n] = {"value": d["value"], "missing": d["missing"], "evidence": tracker_evidence(lk, d)}
        return out, errors, state_info


class TGRTrackerGuard(TGRGuard):
    """The guard for the copied episode loop (repro_online/episode.py::run_episode): same interface and same
    new_episode / check / commit as repro_online.guards.TGRGuard; only the TGR object is ours."""

    name = NAME

    def __init__(self, domain: str, tools_info: List[dict], rules_dir: Optional[str] = None,
                 judge_effort: str = JUDGE_EFFORT, epsilon: float = EPSILON):
        if domain not in paths.DOMAINS:
            raise ValueError(f"unknown domain {domain!r}")
        rules_dir = rules_dir or os.path.join(paths.RULES_DIR, domain)
        rs_path = os.path.join(rules_dir, "rule_set.json")
        rs = load_rule_set(rs_path)
        if rs["flags"]["a"] is not True or rs["flags"]["b"] is not True:
            raise ValueError(f"{NAME} needs a rule set built with A and B; {rules_dir} has {rs['flags']}")
        frozen = check_frozen()
        problems = L.check_lookups(domain)
        if problems:
            raise FrozenInputChanged(f"lookup file problems: {problems[:3]}")
        types = load_types()[domain]
        missing = sorted(set(rs["predicates"]) - set(types))
        if missing:
            raise ValueError(f"predicates without a type: {missing}")
        self.name = NAME
        self.domain = domain
        self.config = TGRConfig(actionable_feedback=True, judge_effort=judge_effort, epsilon=epsilon)
        self.tgr = TrackerTGR(rs, tools_info, self.config, domain, L.load_lookups(domain), types)
        build_state([], None, domain=domain)          # load the τ-bench copy and data once, before worker threads
        self.info = {"guard": NAME, "version": VERSION, "domain": domain, "rules_dir": rules_dir,
                     "rule_set_sha256": sha256(rs_path), "frozen_sha256": frozen,
                     "code_predicates": sorted(n for n in rs["predicates"] if n in self.tgr.code_types),
                     "judge_effort": judge_effort, "epsilon": epsilon, "actionable_feedback": True}


def build(name: str, domain: str, tools_info: List[dict], rules_dir: Optional[str] = None):
    """Our guard registry (only our wrapper uses it): the name "tgr_tracker"."""
    if name != NAME:
        raise ValueError(f"unknown guard {name!r} (our wrapper knows only {NAME!r})")
    return TGRTrackerGuard(domain, tools_info, rules_dir=rules_dir)
