"""Part 10, subtask 10: two extra checks for the report. No LLM calls, stdlib only, reads output/ only.

1. Executed gold v2 violations: how many ran through the cap override (blocked 3 times, run on the 4th attempt)?
2. Rough noise check: paired delta pass^1 (TGR + tracker - frozen TGR) on tasks where the tracker changed no decision in
   any of our 3 trials, against tasks where it changed at least one. If the tracker caused the gain, the "no change"
   tasks should show about 0.

Writes output/p10_report_extra.json and prints a short summary.
"""
import collections
import json
import os
import sys

sys.dont_write_bytecode = True
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "scoring"

from scoring import p10_metrics as PM                                     # noqa: E402
from scoring.p10_eval import EXPERIMENTS, ENVS, OUT                        # noqa: E402

M = PM.M


def violations_by_route(exp, env, guard):
    tag, g = PM.where(exp, guard)
    eps = PM.good_episodes(PM.eps_path(exp, env, guard))
    g2 = {(r["task_index"], r["trial"]): r["gold"]
          for r in M.load(os.path.join(PM.ONLINE, tag, env, g, "gold_v2.jsonl"))}
    executed = cap = 0
    for e in eps:
        gd = g2.get((e["task_index"], e["trial"]))
        if not gd:
            continue
        executed += gd["n_violating_calls"]
        cap += sum(1 for b in gd["blocks"] if b["scorable"] and b["cap_override"] and b["gold_violations"])
    return {"executed": executed, "through_cap_override": cap, "other": executed - cap}


def changed_tasks(exp, env, aspm):
    """Tasks where, in at least one of our trials, the tracker's values changed a decision."""
    eps = PM.good_episodes(PM.eps_path(exp, env, "tgr_tracker"))
    out = set()
    for ep in eps:
        past = []
        for att in ep["attempts"]:
            rec = att.get("guard")
            if not rec:
                continue
            tr = rec.get("tracker") or {}
            jv = tr.get("judge_values")
            if tr.get("applied") and jv is not None and rec.get("circuit") and tr.get("changed"):
                jd = PM.DA.decide(aspm, rec, jv, past)
                if PM.DA.change_kind(jd["allowed"], rec["action_allowed"]):
                    out.add(ep["task_index"])
            if rec.get("action_allowed") or att.get("cap_override"):
                past.append(rec["trace_position"])
    return out


def main():
    res = {"violations": {}, "noise_check": {}}
    for exp in EXPERIMENTS:
        pooled = {"changed": ({}, {}), "unchanged": ({}, {})}
        for env in ENVS:
            aspm = PM.to_aspm(PM.load_rule_set(env))
            for guard in ("tgr", "tgr_tracker"):
                res["violations"][f"{exp} | {env} | {guard}"] = violations_by_route(exp, env, guard)
            ch = changed_tasks(exp, env, aspm)
            sa, sb = PM.success(exp, env, "tgr_tracker"), PM.success(exp, env, "tgr")
            for part, keep in (("changed", lambda t: t in ch), ("unchanged", lambda t: t not in ch)):
                a = {t: v for t, v in sa.items() if keep(t)}
                b = {t: v for t, v in sb.items() if keep(t)}
                res["noise_check"][f"{exp} | {env} | {part}"] = {"tasks": len(a), **(M.paired_delta(a, b) if a else {})}
                pooled[part][0].update({(env, t): v for t, v in a.items()})
                pooled[part][1].update({(env, t): v for t, v in b.items()})
        for part in ("changed", "unchanged"):
            a, b = pooled[part]
            res["noise_check"][f"{exp} | both | {part}"] = {"tasks": len(a), **(M.paired_delta(a, b) if a else {})}
    with open(os.path.join(OUT, "p10_report_extra.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, sort_keys=True)
    for k, v in res["violations"].items():
        print("VIOL", k, v)
    for k, v in res["noise_check"].items():
        print("NOISE", k, json.dumps(v))
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
