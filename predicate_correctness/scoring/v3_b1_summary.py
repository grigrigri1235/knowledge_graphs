"""Tracker v3, part 14: a short report after B1, the paid smoke test (docs/planning/tracker_v3/p14.md,
preregistration_online.md section 10, approval_request.md Request 2). $0: no LLM call, no network; reads the run
folder only. Never the gold scorer, never a saved val run.

The pass mark is the runner's own check (guard/run_online_v3.py b1_check, the same code as `run_online_v3 b1-check`):
10 conversations; 0 error lines (1 content-filter error allowed); mean cost <= 3 x the point ($0.12 / 10); and
(audit C) 0 Direct + facts facts failures and 0 v3 state errors. This file adds: spend vs the $2 limit and the $95
cap, the errors, per-arm cost vs the p14 estimates, a B2 cost projection from B1's costs, and anything odd.

TEST mode: a run folder under output/eval_v3/dryrun/ (or run.json "sandbox") marks the output TEST (dry-run data, fake
LLMs), and --out must be under output/eval_v3/dryrun/p14report/. A real run's --out must be under output/ (not the
dry-run folder).

Command (from predicate_correctness/; guard code inside, so the runner's python):
  PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m scoring.v3_b1_summary \
      --run-id $RUN_ID --out output/eval_v3/B1_${RUN_ID}_summary.md > output/logs/v3_B1_${RUN_ID}_summary.log 2>&1
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time
from typing import Dict, List, Optional

sys.dont_write_bytecode = True

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "scoring"

PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PC_DIR, "output")
V3_ROOT = os.path.join(OUTPUT_DIR, "eval_v3")
DRYRUN_ROOT = os.path.join(V3_ROOT, "dryrun")
TEST_OUT_ROOT = os.path.join(DRYRUN_ROOT, "p14report")
LOGS_DIR = os.path.join(OUTPUT_DIR, "logs")
TEST_MARK = "TEST (dry-run data, fake LLMs)"
ARMS = ("none", "direct", "direct_facts_v3", "tgr_frozen", "tgr_tracker_v3")
LABEL = {"none": "no guard", "direct": "Direct", "direct_facts_v3": "Direct + facts", "tgr_frozen": "frozen TGR",
         "tgr_tracker_v3": "v3"}
POINT_USD = {"none": 0.0068, "direct": 0.0127, "direct_facts_v3": 0.0131, "tgr_frozen": 0.0120,
             "tgr_tracker_v3": 0.0104}                  # p14.md, per conversation
B2_CONVS_PER_ARM = 99 * 3
B2_LIMIT_USD = 45.0
B2_EST = (15.0, 22.0, 16.4)                              # p14.md: low, high, point
ONE_CONV_STOP_USD = 0.25


def _under(path: str, root: str) -> bool:
    ap, rp = os.path.abspath(path), os.path.abspath(root)
    return ap == rp or ap.startswith(rp + os.sep)


def usd(x, dp: int = 4) -> str:
    return "n/a" if x is None else f"${x:.{dp}f}"


def summarize(run_dir: str) -> dict:
    """Everything the summary shows, as a dict (also written next to the md as JSON)."""
    from guard import run_online_v3 as R                  # the runner's own B1 check (reads files only)
    from guard import soft_stop, soft_stop_v3 as SS
    from scoring import v3_online_metrics as M

    M._check_holdout(run_dir, False)
    chk = R.b1_check(run_dir)
    rj = {}
    try:
        with open(os.path.join(run_dir, "run.json"), encoding="utf-8") as f:
            rj = json.load(f)
    except (OSError, ValueError):
        pass
    ident = rj.get("ident") or {}
    test = bool(rj.get("sandbox")) or _under(run_dir, DRYRUN_ROOT)
    lines: Dict[str, List[dict]] = {}
    for a in ARMS:
        d = os.path.join(run_dir, a)
        if os.path.isdir(d):
            for name in sorted(os.listdir(d)):
                if soft_stop.is_episodes_file(name):
                    lines.setdefault(a, []).extend(R._lines_of(os.path.join(d, name)))
    per_arm, errors, odd = {}, [], []
    for a in ARMS:
        rs = lines.get(a, [])
        costs = [soft_stop.line_cost(r) for r in rs]
        n = len(rs)
        mean = sum(costs) / n if n else None
        per_arm[a] = {"lines": n, "errors": sum(r.get("error") is not None for r in rs), "usd": sum(costs),
                      "mean_usd": mean, "point_usd": POINT_USD[a], "high_usd": SS.ARM_MEAN_STOP_USD[a] / 3,
                      "ratio_to_point": (mean / POINT_USD[a]) if mean is not None else None,
                      "rewards": [r.get("reward") for r in rs], "blocks": sum(int(r.get("n_blocks") or 0) for r in rs),
                      "cap_overrides": sum(int(r.get("n_cap_overrides") or 0) for r in rs),
                      "max_exec_steps": max([int(r.get("n_exec_steps") or 0) for r in rs], default=None),
                      "not_done": sum(1 for r in rs if r.get("error") is None and not r.get("done"))}
        if not rs:
            odd.append(f"no line of arm {a}")
        for r in rs:
            if r.get("error") is not None:
                errors.append({"arm": a, "domain": r.get("env"), "task": r.get("task_index"),
                               "attempt": r.get("unit_attempt"), "error": str(r.get("error"))[:300]})
            c = soft_stop.line_cost(r)
            if c > ONE_CONV_STOP_USD:
                odd.append(f"{a} {r.get('env')} task {r.get('task_index')}: one conversation costs ${c:.3f} "
                           f"(> ${ONE_CONV_STOP_USD})")
            if r.get("step") != "B1" or (ident.get("run_id") and r.get("run_id") != ident.get("run_id")):
                odd.append(f"{a}: a line of step {r.get('step')} / run {r.get('run_id')}")
            if int(r.get("unit_attempt") or 1) > 1:
                odd.append(f"{a} {r.get('env')} task {r.get('task_index')}: re-run unit (attempt "
                           f"{r.get('unit_attempt')})")
            if r.get("error") is None and not isinstance(r.get("cost"), dict):
                odd.append(f"{a} {r.get('env')} task {r.get('task_index')}: no cost field")
        p = per_arm[a]
        if p["mean_usd"] is not None and p["mean_usd"] > p["high_usd"]:
            odd.append(f"{LABEL[a]}: mean cost {usd(p['mean_usd'])} is above its high estimate "
                       f"{usd(p['high_usd'])} (only 2 conversations; noisy)")
        if p["not_done"]:
            odd.append(f"{LABEL[a]}: {p['not_done']} conversations ended without done (step limit?)")
    all_lines = [r for rs in lines.values() for r in rs]
    ok_lines = [r for r in all_lines if r.get("error") is None]
    if ok_lines and all(r.get("reward") != 1.0 for r in ok_lines):
        odd.append("no conversation got reward 1 (possible with 2 hard tasks; check the agent did real work)")
    if os.path.exists(os.path.join(run_dir, SS.STOP_FILENAME)):
        odd.append("the STOP file is present")
    dropped = []
    for name in sorted(os.listdir(run_dir)) if os.path.isdir(run_dir) else []:
        if name.startswith("dropped_groups") and name.endswith(".jsonl"):
            dropped += R._lines_of(os.path.join(run_dir, name))
    if dropped:
        odd.append(f"{len(dropped)} dropped groups")
    # the tiny questions of v3
    qs = collections.Counter()
    qdir = os.path.join(run_dir, "questions")
    if os.path.isdir(qdir):
        for name in sorted(os.listdir(qdir)):
            if name.endswith(".jsonl"):
                for r in R._lines_of(os.path.join(qdir, name)):
                    qs[str(r.get("status") or r.get("answer"))] += 1
    if qs.get("unclear"):
        odd.append(f"{qs['unclear']} tiny-question answers are unclear")
    # shard logs
    step, run_id = ident.get("step") or "B1", ident.get("run_id") or os.path.basename(os.path.abspath(run_dir))
    log_lines = []
    logp = os.path.join(LOGS_DIR, f"v3_{step}_{run_id}_s0.log")
    if os.path.exists(logp):
        with open(logp, encoding="utf-8", errors="replace") as f:
            for line in f:
                if "STOPPED:" in line or " DONE:" in line or "Traceback" in line:
                    log_lines.append(line.strip()[:300])
        if any("STOPPED:" in x for x in log_lines):
            odd.append("the shard log says STOPPED")
    # spend
    run_usd = sum(p["usd"] for p in per_arm.values())
    try:
        tot = SS.v3_spend()
        total = {"total_usd": tot["total_usd"], "questions_usd": tot["questions_usd"],
                 "episodes_usd": tot["episodes_usd"]}
    except Exception as e:  # noqa: BLE001
        total = {"error": f"{type(e).__name__}: {e}"}
    # B2 projection from B1's mean cost per arm (2 conversations per arm: a rough check only)
    proj = {a: (per_arm[a]["mean_usd"] or 0.0) * B2_CONVS_PER_ARM for a in ARMS}
    proj_total = sum(proj.values())
    if proj_total > B2_LIMIT_USD:
        odd.append(f"B2 projected from B1's costs: ${proj_total:.1f}, over B2's hard limit ${B2_LIMIT_USD:.0f}")
    return {"run_dir": run_dir, "test": test, "check": chk, "ident": ident, "per_arm": per_arm, "errors": errors,
            "odd": odd, "dropped": dropped, "questions": dict(qs), "log": logp if os.path.exists(logp) else None,
            "log_lines": log_lines, "run_usd": run_usd, "limit_usd": ident.get("hard_limit_usd", 2.0),
            "cap_usd": ident.get("cap_usd", SS.V3_CAP_USD), "v3_total": total, "b2_projection": proj,
            "b2_projection_total": proj_total}


def render(s: dict) -> str:
    c = s["check"]
    L = []
    t = "# B1 smoke test: summary"
    if s["test"]:
        t = f"# {TEST_MARK}: B1 summary (format check only)"
    L += [t, ""]
    if s["test"]:
        L += [f"> **{TEST_MARK}.** Sandbox run folder, fake LLMs. Not a result. Not B1.", ""]
    L += [f"Made {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} by `scoring/v3_b1_summary.py`, $0. Run "
          f"`{s['ident'].get('run_id')}`, folder `{os.path.relpath(os.path.abspath(s['run_dir']), PC_DIR)}`.", "",
          f"## Verdict: **{'PASS' if c['pass'] else 'FAIL'}** (pre-registered B1 pass mark)", ""]
    names = {"conversations": f"10 conversations (found {c['conversations']})",
             "units_done": f"units done without error (found {c['units_done']})",
             "error_lines": f"0 error lines, 1 content-filter error allowed (found {c['error_lines']}, content "
                            f"filter {c['content_filter_errors']})",
             "mean_cost": f"mean cost ≤ 3 × point = {usd(c['mean_cost_limit_usd'])} (found {usd(c['mean_cost_usd'])})",
             "direct_facts_facts_failures": f"Direct + facts `facts_failure` = 0 (found "
                                            f"{c['direct_facts_facts_failures']})",
             "v3_state_errors": f"v3 state errors = 0 (found {c['v3_state_errors']}; checks with a state error "
                                f"{c['v3_checks_with_state_errors']})"}
    L += ["| check | result |", "|---|---|"]
    L += [f"| {names.get(k, k)} | {'ok' if v else '**FAIL**'} |" for k, v in c["checks"].items()]
    L += ["", f"Also: Direct + facts `state_error` count {c['direct_facts_state_errors']} (shown, not a pass check).",
          "", "## Spend", "",
          f"- B1: **{usd(s['run_usd'])}** of the hard limit {usd(s['limit_usd'], 2)} (estimate $0.12, high $0.48)"]
    tot = s["v3_total"]
    L += [f"- v3 total so far (`soft_stop_v3.v3_spend`): {usd(tot.get('total_usd'), 2)} of the cap "
          f"{usd(s['cap_usd'], 0)}" + (f" (questions {usd(tot.get('questions_usd'), 2)}, episodes "
                                       f"{usd(tot.get('episodes_usd'), 2)})" if "total_usd" in tot else
                                       f" ({tot.get('error')})")]
    if s["test"]:
        L += ["- TEST: the B1 spend above is fake-LLM spend in the dry-run folder, not counted toward the cap."]
    L += ["", "## Per arm: cost vs the p14 estimates", "",
          "| arm | lines | errors | mean cost | point | high | mean / point | rewards | blocks | cap overrides | "
          "max steps |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for a in ARMS:
        p = s["per_arm"][a]
        ratio = "n/a" if p["ratio_to_point"] is None else f"{p['ratio_to_point']:.2f}×"
        L += [f"| {LABEL[a]} | {p['lines']} | {p['errors']} | {usd(p['mean_usd'])} | {usd(p['point_usd'])} | "
              f"{usd(p['high_usd'])} | {ratio} | {p['rewards']} | {p['blocks']} | {p['cap_overrides']} | "
              f"{p['max_exec_steps']} |"]
    L += ["", f"B2 projected from these means (× {B2_CONVS_PER_ARM} conversations per arm): "
          f"**${s['b2_projection_total']:.2f}** (" + ", ".join(f"{LABEL[a]} ${v:.2f}"
                                                         for a, v in s["b2_projection"].items()) +
          f"); p14 estimate ${B2_EST[0]:.0f}-{B2_EST[1]:.0f} (point ${B2_EST[2]}); B2 hard limit "
          f"${B2_LIMIT_USD:.0f}. Two conversations per arm: a rough check only.", "",
          "## Errors", ""]
    L += ([f"- {e['arm']} {e['domain']} task {e['task']} (attempt {e['attempt']}): `{e['error']}`" for e in s["errors"]]
          or ["- none"])
    L += ["", "## Anything odd", ""]
    L += [f"- {x}" for x in s["odd"]] or ["- nothing found"]
    L += ["", f"Tiny-question answers (v3): {json.dumps(s['questions'])}.", ""]
    if s["log_lines"]:
        L += ["Shard log (`" + os.path.relpath(s["log"], PC_DIR) + "`):", ""]
        L += [f"    {x}" for x in s["log_lines"][:10]]
        L += [""]
    else:
        L += ["Shard log: " + ("no STOPPED / DONE line" if s["log"] else "not found") + ".", ""]
    L += ["Next: a cost-log row in `approval_request.md`, then **stop**. B2 needs its own new approval.", ""]
    if s["test"]:
        L += [f"*{TEST_MARK}.*", ""]
    return "\n".join(L)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--run-id", help="B1 run id (folder output/eval_v3/B1/<id>)")
    g.add_argument("--run-dir", help="a B1 run folder")
    ap.add_argument("--out-root", default=V3_ROOT, help="with --run-id: the root holding B1/<id>")
    ap.add_argument("--out", required=True, help="the summary .md (a .json with the same numbers goes next to it)")
    a = ap.parse_args(argv)
    run_dir = os.path.abspath(a.run_dir) if a.run_dir else os.path.join(os.path.abspath(a.out_root), "B1", a.run_id)
    if not os.path.isdir(run_dir):
        raise SystemExit(f"refused: {run_dir} is not a folder")
    out = os.path.abspath(a.out)
    test = _under(run_dir, DRYRUN_ROOT)
    try:
        with open(os.path.join(run_dir, "run.json"), encoding="utf-8") as f:
            test = test or bool(json.load(f).get("sandbox"))
    except (OSError, ValueError):
        pass
    if test and not _under(out, TEST_OUT_ROOT):                    # before any write
        raise SystemExit(f"refused: TEST data may only be written under {TEST_OUT_ROOT}")
    if not test and (not _under(out, OUTPUT_DIR) or _under(out, DRYRUN_ROOT)):
        raise SystemExit(f"refused: a real B1 summary goes under {OUTPUT_DIR} (not the dry-run folder)")
    if not out.endswith(".md"):
        raise SystemExit("refused: --out must end in .md")
    s = summarize(run_dir)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(s) + "\n")
    with open(out[:-3] + ".json", "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1, default=str)
        f.write("\n")
    print(f"[v3-b1-summary] {'TEST ' if s['test'] else ''}{'PASS' if s['check']['pass'] else 'FAIL'}; wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
