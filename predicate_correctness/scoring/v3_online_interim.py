"""Tracker v3, part 13 step 4: the interim check and the stop rules of the paid run, as a read-only report for the main
chat (docs/planning/tracker_v3/p13.md step 5, "stops"). $0, no LLM call, no network, writes nothing (stdout only).

Stops (lenient on purpose: they catch a broken run, not a normal one):
  harm      at the halfway point (HALF = 742 conversations in complete (task, try) groups: all arms present, no
            error), v3 - frozen TGR <= HARM (-0.15), task success paired by task (tries averaged), all tasks of the
            complete groups. Before the halfway point: not checked ("not yet").
  state     the 3rd v3 state error: guard checks of the v3 arm with a state error or a fact error (an exception in
            the fact code; rec["v3"]["state_errors"] / ["fact_errors"]), counted together, both shown; every v3 line
            counts, as in the runner (error lines, re-run units and dropped groups included).
The saved val runs (luna_val, ...) are refused by path (scoring/v3_online_metrics.py is_saved_val_path); our own run
folders, which hold val tasks by design, load.
  cost      an arm's mean cost per conversation, after 50 or more of its lines, over COST_STOP[arm] (3 x its high
            estimate), or one conversation over $0.25.
  errors    10 or more error lines and over 5 % of the lines, or 5 error lines in a row (file order per shard file).
B3 (p14, optional): a run folder with B3 lines is checked alone (B3 and other lines together are refused); its
halfway point is B3_HALF = 160 conversations (64 tasks x 1 try x 5 arms = 320), on its 64 tasks; the other stops are
the same.

Run from predicate_correctness/:
  /home/azureuser/miniconda3/bin/python3 -B -m scoring.v3_online_interim --run-dir output/eval_v3/B2/<run_id> \
      > output/logs/v3_B2_interim.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional, Sequence

sys.dont_write_bytecode = True

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "scoring"

from scoring import v3_online_metrics as M                       # noqa: E402

HALF = 742
B3_HALF = 160                                    # B3: 320 conversations, half 160
HARM = -0.15
STATE_ERRORS_STOP = 3
COST_STOP = {"none": 0.023, "direct": 0.044, "direct_facts_v3": 0.049, "tgr_frozen": 0.041, "tgr_tracker_v3": 0.061}
COST_MIN_LINES = 50
CONV_COST_STOP = 0.25
ERR_MIN, ERR_SHARE, ERR_STREAK = 10, 0.05, 5


def raw_lines(run_dirs: Sequence[str]) -> Dict[str, List[dict]]:
    """Every line of every episodes*.jsonl (no latest-line rule: error lines and re-runs all count), per file."""
    out = {}
    for d in run_dirs:
        M._check_holdout(d, False)
        for p in M.episode_files(d):
            M._check_holdout(p, False)
            out[p] = M.read_jsonl(p)
    return out


def harm_check(convs: Sequence[dict], arms: Sequence[str] = M.ARMS, half: int = HALF,
               task_set: str = "all") -> dict:
    comp, info = M.complete_groups(convs, arms)
    n = len(comp)
    out = {"conversations_in_complete_groups": n, "complete_groups": info["complete_groups"], "half": half,
           "threshold": HARM}
    if n < half:
        out.update({"reached": False, "fire": False})
        return out
    d = M.paired(comp, M.V3, M.FROZEN, task_set)
    diff = sum(d.values()) / len(d) if d else None
    out.update({"reached": True, "diff": diff, "n_tasks": len(d), "fire": diff is not None and diff <= HARM})
    return out


def state_check(lines: Dict[str, List[dict]]) -> dict:
    """Every v3 line counts (as guard/run_online_v3.py counts them: error lines, re-run units and dropped groups
    included): guard checks with a state error or a fact error."""
    st = fe = 0
    either = 0
    for recs in lines.values():
        for r in recs:
            if M.arm_of(r) != M.V3:
                continue
            for a in r.get("attempts") or []:
                v3 = (a.get("guard") or {}).get("v3") or {}
                s, f = bool(v3.get("state_errors")), bool(v3.get("fact_errors"))
                st += s
                fe += f
                either += 1 if (s or f) else 0
    return {"checks_with_state_error": st, "checks_with_fact_error": fe, "count": either,
            "fire": either >= STATE_ERRORS_STOP, "counted_on": "every v3 line"}


def cost_check(lines: Dict[str, List[dict]]) -> dict:
    per_arm: Dict[str, List[float]] = {}
    over = []
    for p, recs in lines.items():
        for r in recs:
            c = M.line_cost(r)
            per_arm.setdefault(M.arm_of(r), []).append(c)
            if c > CONV_COST_STOP:
                over.append({"file": p, "task": r.get("task_index"), "trial": r.get("trial"), "cost": c})
    arms = {}
    fire = bool(over)
    for a, cs in sorted(per_arm.items()):
        mean = sum(cs) / len(cs)
        lim = COST_STOP.get(a)
        f = lim is not None and len(cs) >= COST_MIN_LINES and mean > lim
        fire = fire or f
        arms[a] = {"lines": len(cs), "mean": mean, "limit": lim, "fire": f}
    return {"arms": arms, "conversations_over_0.25": over, "fire": fire}


def error_check(lines: Dict[str, List[dict]]) -> dict:
    total = errs = 0
    streak_max = 0
    for recs in lines.values():
        streak = 0
        for r in recs:
            total += 1
            if r.get("error") is not None:
                errs += 1
                streak += 1
                streak_max = max(streak_max, streak)
            else:
                streak = 0
    share = errs / total if total else 0.0
    return {"lines": total, "error_lines": errs, "share": share, "longest_streak": streak_max,
            "fire": (errs >= ERR_MIN and share > ERR_SHARE) or streak_max >= ERR_STREAK}


def interim(run_dirs: Sequence[str]) -> dict:
    lines = raw_lines(run_dirs)
    convs = M.load_run_dirs(run_dirs)
    b3 = any(r.get("step") == M.B3_STEP for recs in lines.values() for r in recs)
    if b3 and any(r.get("step") != M.B3_STEP for recs in lines.values() for r in recs):
        raise M.B3Mixed("B3 lines and other lines in one interim check: B3 is checked alone")
    harm = harm_check(convs, half=B3_HALF, task_set=M.B3_SET) if b3 else harm_check(convs)
    out = {"run_dirs": list(run_dirs), "harm": harm, "state": state_check(lines),
           "cost": cost_check(lines), "errors": error_check(lines)}
    if b3:
        out["step"] = M.B3_STEP
    out["any_stop"] = any(out[k]["fire"] for k in ("harm", "state", "cost", "errors"))
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run-dir", action="append", required=True)
    a = ap.parse_args(argv)
    rep = interim(a.run_dir)
    print(json.dumps(M._jsonable(rep), indent=1))
    print(f"[v3-interim] harm {rep['harm']['fire']} state {rep['state']['fire']} cost {rep['cost']['fire']} "
          f"errors {rep['errors']['fire']} -> {'STOP' if rep['any_stop'] else 'go on'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
