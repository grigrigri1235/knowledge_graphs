"""Eval v2 Part 6, strong run (luna-dev): checks and raw numbers of Stage A (standard library only, no LLM call).

Reads only (never writes there):
  output/eval_v2/stage_a/luna/<guard>/episodes*.jsonl   (the glob skips the *.jsonl.before_resume backups)
  output/eval_v2/stage_a/luna/<guard>/run_*.json and job.json
  output/logs/v2_stage_a_luna_s{0,1,2,3}.log and v2_stage_a_luna_s0_resume1.log
  output/_llmcache/v2_stage_a_luna/<guard>/structured  (file names only)
  guard/soft_stop.spent_report()  (it scans every episodes*.jsonl under output/eval_v2, read only)
Never opens output/eval_v2/stage_a/nano/ itself.

Checks: one good line (error null) per (task, guard) for all 500 tasks, first good line kept; error lines; models,
task_split, profile; tracker part in every check of tgr_tracker (lookup errors, replay mismatches, judge skipped);
no tracker part in tgr_frozen; own judge cache per guard. Numbers (raw, no ranges; Part 9 does the analysis):
success, blocks, cap overrides, transfers (partner's definition: the last allowed attempt is transfer_to_human*),
cost (agent / user / judge; total = soft_stop.line_cost), seconds, and the tasks where the tracker changed a decision
(tracker.changed not empty and TGR's decision with tracker.judge_values differs from the saved one; decision code
from state_tracker/decide_again.py, as in scoring/p10_metrics.py).

Run from predicate_correctness/:
  PYTHONDONTWRITEBYTECODE=1 nice -n 10 /home/azureuser/miniconda3/bin/python3 -B -m scoring.v2_p6_strong_check \
      > output/logs/v2_c6s_check.json 2> output/logs/v2_c6s_check.err
Never imports gold code, the runner copy or τ-bench.
"""
from __future__ import annotations

import collections
import datetime as dt
import glob
import json
import os
import re
import sys

sys.dont_write_bytecode = True

from guard import soft_stop                                         # noqa: E402  (stdlib only)
from state_tracker import paths                                     # noqa: E402
from state_tracker import decide_again as DA                        # noqa: E402  (stdlib; copied mln)
from state_tracker.tgr_to_aspm import load_rule_set, to_aspm        # noqa: E402

AGENT_DIR = os.path.join(paths.OUTPUT_DIR, "eval_v2", "stage_a", "luna")
CACHE_ROOT = os.path.join(paths.OUTPUT_DIR, "_llmcache", "v2_stage_a_luna")
LOG_DIR = os.path.join(paths.OUTPUT_DIR, "logs")
LOGS = [f"v2_stage_a_luna_s{i}.log" for i in range(4)] + ["v2_stage_a_luna_s0_resume1.log"]
GUARDS = ("tgr_frozen", "tgr_tracker")
N_TASKS = 500
MODELS = {"agent": "gpt-6-luna", "user": "gpt-6-luna", "guard": "gpt-6-luna"}
TOL = 1e-9
DONE_RE = re.compile(r"DONE: (\d+) episodes in (\d+)s; refused writes (\d+); total spend \$([0-9.]+)")
JUDGE_RE = re.compile(r"judge cache use (\{.*\})\s*$")


def count_files(root):
    return sum(len(f) for _, _, f in os.walk(root)) if os.path.isdir(root) else 0


def file_names(root):
    out = set()
    for _, _, fs in os.walk(root):
        out.update(fs)
    return out


def r6(x):
    return round(float(x), 6)


def read_lines(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for n, raw in enumerate(f, 1):
            if raw.strip():
                out.append((n, json.loads(raw)))
    return out


def transfer(ep):
    allowed = [a for a in (ep.get("attempts") or []) if not a.get("blocked")]
    return bool(allowed) and str(allowed[-1].get("action") or "").startswith("transfer_to_human")


def guard_part(g, aspm):
    d = os.path.join(AGENT_DIR, g)
    files = sorted(glob.glob(os.path.join(d, "episodes*.jsonl")))
    problems, error_lines, all_lines = [], [], []
    good = {}                                         # (task, trial) -> first good record
    dup_good = []
    for p in files:
        for n, r in read_lines(p):
            all_lines.append(r)
            key = (r.get("task_index"), r.get("trial"))
            where = f"{os.path.basename(p)}:{n}"
            if r.get("error") is not None:
                error_lines.append({"where": where, "task": key[0], "trial": key[1],
                                    "error": str(r.get("error"))[:240], "cost": r6(soft_stop.line_cost(r))})
                continue
            if key in good:
                dup_good.append({"where": where, "task": key[0], "trial": key[1]})
                continue
            good[key] = r
            good[key]["_where"] = where
    tasks = sorted(k[0] for k in good)
    missing = sorted(set(range(N_TASKS)) - set(tasks))
    trials = sorted({k[1] for k in good})

    c = collections.Counter()
    trk = collections.Counter()
    changed_tasks, changed_list, decision_problems = set(), [], []
    rows = []
    for (task, trial), r in sorted(good.items()):
        cost = r.get("cost") or {}
        u = r.get("usage_roles") or {}
        calls = r.get("calls") or {}
        atts = r.get("attempts") or []
        row = {"task": task, "reward": r.get("reward"), "done": r.get("done"), "n_blocks": r.get("n_blocks"),
               "n_cap": r.get("n_cap_overrides"), "seconds": r.get("seconds"), "n_exec": r.get("n_exec_steps"),
               "cost_agent": cost.get("agent") or 0.0, "cost_user": cost.get("user") or 0.0,
               "cost_judge": cost.get("guard") or 0.0, "cost_total": soft_stop.line_cost(r),
               "transfer": transfer(r), "attempts": len(atts)}
        rows.append(row)
        if r.get("task_split") != "train":
            problems.append(f"task {task}: task_split {r.get('task_split')!r}")
        if r.get("models") != MODELS:
            problems.append(f"task {task}: models {r.get('models')}")
        if r.get("profile") != "luna-dev" or r.get("env") != "retail" or r.get("guard") != g:
            problems.append(f"task {task}: profile/env/guard {r.get('profile')}/{r.get('env')}/{r.get('guard')}")
        if not isinstance(r.get("reward_info"), dict) and r.get("done"):
            problems.append(f"task {task}: done without reward_info")
        if r.get("n_blocks") != sum(bool(a.get("blocked")) for a in atts):
            problems.append(f"task {task}: n_blocks != blocked attempts")
        if r.get("n_cap_overrides") != sum(bool(a.get("cap_override")) for a in atts):
            problems.append(f"task {task}: n_cap_overrides != cap_override attempts")
        uu = (u.get("user") or {}).get("calls")
        if uu != (calls.get("user") or 0) + 1:
            c["user calls usage != loop + 1"] += 1
        past = []
        for i, a in enumerate(atts):
            rec = a.get("guard")
            if not rec:
                c["attempts without a guard record"] += 1
                continue
            c["guard checks"] += 1
            us = rec.get("usage") or {}
            c["judge llm calls (usage)"] += us.get("n_llm_calls") or 0
            c["judge cache hits (usage)"] += us.get("cache_hits") or 0
            c["judge cost usd x1e6 (usage)"] += round((us.get("cost_usd") or 0.0) * 1e6)
            if "tracker" in rec:
                c["checks with a tracker field"] += 1
            if g == "tgr_tracker":
                t = rec.get("tracker") or {}
                jv_used = rec.get("judge") or {}
                trk["checks"] += 1
                trk["tracker part applied"] += bool(t.get("applied"))
                trk["judge skipped"] += bool(t.get("judge_skipped"))
                trk["judge called"] += not t.get("judge_skipped")
                trk["lookup errors"] += len(t.get("lookup_errors") or [])
                trk["checks with lookup errors"] += bool(t.get("lookup_errors"))
                st = t.get("state") or {}
                trk["replay mismatches"] += st.get("mismatches") or 0
                trk["replay parse problems"] += st.get("parse_problems") or 0
                trk["replay problems"] += st.get("problems") or 0
                trk["values replaced"] += len(t.get("replaced") or [])
                trk["values changed"] += len(t.get("changed") or [])
                trk["checks where a value changed"] += bool(t.get("changed"))
                trk["tracker unknowns"] += sum(1 for v in (t.get("tracker_values") or {}).values()
                                               if isinstance(v, dict) and v.get("value") is None and not v.get("error"))
                for k, v in jv_used.items():
                    want = "tracker" if k in (t.get("replaced") or []) else "judge"
                    if not isinstance(v, dict) or v.get("source") != want:
                        trk["values with a wrong source"] += 1
                jv = t.get("judge_values")
                used = {n: (v or {}).get("value") for n, v in jv_used.items()}
                if jv is not None and rec.get("circuit"):
                    again = DA.decide(aspm, rec, used, past)
                    if again["allowed"] != rec["action_allowed"] or abs(again["margin"] - rec["margin"]) > TOL:
                        trk["decision with the used values differs from the saved one"] += 1
                        decision_problems.append(f"task {task} att {i}")
                    else:
                        trk["decision with the used values = saved"] += 1
                    jd = DA.decide(aspm, rec, jv, past)
                    kind = DA.change_kind(jd["allowed"], rec["action_allowed"])
                    if kind:
                        trk[kind] += 1
                        if not t.get("changed"):
                            trk["decision differs but changed is empty"] += 1
                        changed_tasks.add(task)
                        diff = DA.differing(jv, used)
                        changed_list.append({"task": task, "attempt_idx": i, "action": a.get("action"),
                                             "change": kind, "predicates": diff,
                                             "judge": {n: jv.get(n) for n in diff},
                                             "used": {n: used.get(n) for n in diff},
                                             "cap_override": a.get("cap_override"), "reward": r.get("reward")})
                else:
                    trk["checks without judge values or circuit"] += 1
            if rec.get("action_allowed") or a.get("cap_override"):
                past.append(rec.get("trace_position"))
    n = len(rows)
    tot = lambda k: sum((x[k] or 0) for x in rows)          # noqa: E731
    res = {
        "files": [os.path.basename(p) for p in files],
        "lines": len(all_lines), "good_lines_first_per_task": n, "error_lines": error_lines,
        "duplicate_good_lines": dup_good, "tasks_missing": missing, "trials": trials,
        "problems": problems,
        "success": {"reward_1": sum(1 for x in rows if x["reward"] == 1.0), "rate": r6(tot("reward") / n)},
        "not_done (max steps)": sum(1 for x in rows if not x["done"]),
        "blocks": {"total": tot("n_blocks"), "per_conversation": r6(tot("n_blocks") / n),
                   "conversations_with_a_block": sum(1 for x in rows if x["n_blocks"])},
        "cap_overrides": {"total": tot("n_cap"), "conversations": sum(1 for x in rows if x["n_cap"])},
        "transfers": sum(1 for x in rows if x["transfer"]),
        "cost_usd": {"agent": r6(tot("cost_agent")), "user": r6(tot("cost_user")), "judge": r6(tot("cost_judge")),
                     "total_line_cost": r6(tot("cost_total"))},
        "cost_per_conversation": {"agent": r6(tot("cost_agent") / n), "user": r6(tot("cost_user") / n),
                                  "judge": r6(tot("cost_judge") / n), "total": r6(tot("cost_total") / n)},
        "all_lines_cost_usd": r6(sum(soft_stop.line_cost(r) for r in all_lines)),
        "seconds_per_conversation": round(tot("seconds") / n, 1),
        "seconds_max": max(x["seconds"] for x in rows), "seconds_min": min(x["seconds"] for x in rows),
        "attempts_per_conversation": round(tot("attempts") / n, 2),
        "exec_steps_per_conversation": round(tot("n_exec") / n, 2),
        "counts": dict(c),
        "rewards": {x["task"]: x["reward"] for x in rows},
        "good_440": next((r["_where"] for (t, _), r in good.items() if t == 440), None),
    }
    if g == "tgr_tracker":
        res["tracker"] = dict(trk)
        res["tracker"]["tasks_with_a_changed_decision"] = sorted(changed_tasks)
        res["tracker"]["n_tasks_with_a_changed_decision"] = len(changed_tasks)
        res["tracker"]["changed_decisions"] = changed_list
        res["tracker"]["decision_problems"] = decision_problems[:20]
    # run files and their caches
    runs = sorted(glob.glob(os.path.join(d, "run_*.json")))
    res["run_files"] = []
    for rp in runs:
        j = json.load(open(rp, encoding="utf-8"))
        pl = j.get("plan") or {}
        res["run_files"].append({
            "file": os.path.basename(rp), "started": j.get("started"), "shard": pl.get("shard"),
            "units_to_run": pl.get("units_to_run"), "units_to_run_by_guard": pl.get("units_to_run_by_guard"),
            "models": pl.get("models"), "roles": {k: v.get("model") for k, v in
                                                  ((j.get("activation") or {}).get("roles") or {}).items()},
            "task_split": pl.get("task_split"), "profile": pl.get("profile"),
            "structured_cache": {k: v.get("structured_cache") for k, v in
                                 ((pl.get("paths") or {}).get("guards") or {}).items()},
            "spent_usd_at_start": (pl.get("soft_stop") or {}).get("spent_usd_now"),
            "argv": pl.get("argv")})
    cache_dir = os.path.join(CACHE_ROOT, g, "structured")
    res["judge_cache_dir"] = cache_dir
    res["judge_cache_files"] = count_files(cache_dir)
    return res, rows


def logs_part(run_starts):
    out = {}
    for name in LOGS:
        p = os.path.join(LOG_DIR, name)
        txt = open(p, encoding="utf-8").read().splitlines()
        done = [m for m in (DONE_RE.search(x) for x in txt) if m]
        judge = [m for m in (JUDGE_RE.search(x) for x in txt) if m]
        errs = [x[:200] for x in txt if " err True " in x]
        rec = {"lines": len(txt), "done_line": done[-1].group(0) if done else None, "error_progress_lines": errs,
               "stopped_lines": [x[:200] for x in txt if "STOPPED" in x],
               "traceback_lines": sum(1 for x in txt if x.startswith("Traceback"))}
        if done:
            rec.update(episodes=int(done[-1].group(1)), seconds=int(done[-1].group(2)),
                       refused_writes=int(done[-1].group(3)), total_spend_at_end=float(done[-1].group(4)))
        if judge:
            rec["judge_cache_use"] = json.loads(judge[-1].group(1))
        start = run_starts.get(name)
        if start and done:
            s = dt.datetime.fromisoformat(start)
            rec["started"] = start
            rec["ended_about"] = (s + dt.timedelta(seconds=int(done[-1].group(2)))).isoformat()
        out[name] = rec
    return out


def main():
    aspm = to_aspm(load_rule_set("retail"))
    rep = {"agent_dir": AGENT_DIR, "cache_root": CACHE_ROOT, "guards": {}}
    rows = {}
    for g in GUARDS:
        rep["guards"][g], rows[g] = guard_part(g, aspm)
    # paired raw counts (no ranges)
    a = {x["task"]: x["reward"] for x in rows["tgr_frozen"]}
    b = {x["task"]: x["reward"] for x in rows["tgr_tracker"]}
    both = sorted(set(a) & set(b))
    rep["paired_raw"] = {
        "tasks_in_both": len(both),
        "both_success": sum(1 for t in both if a[t] == 1.0 and b[t] == 1.0),
        "only_frozen_success": sum(1 for t in both if a[t] == 1.0 and b[t] != 1.0),
        "only_tracker_success": sum(1 for t in both if a[t] != 1.0 and b[t] == 1.0),
        "both_fail": sum(1 for t in both if a[t] != 1.0 and b[t] != 1.0),
        "mean_difference_tracker_minus_frozen": r6(sum(b[t] - a[t] for t in both) / len(both)),
    }
    ch = set(rep["guards"]["tgr_tracker"]["tracker"]["tasks_with_a_changed_decision"])
    rep["paired_raw"]["changed_decision_tasks"] = {
        "n": len(ch), "tracker_success": sum(1 for t in ch if b.get(t) == 1.0),
        "frozen_success_same_task": sum(1 for t in ch if a.get(t) == 1.0)}
    # caches: shared names
    na, nb = (file_names(os.path.join(CACHE_ROOT, g, "structured")) for g in GUARDS)
    rep["judge_cache_shared_file_names"] = len(na & nb)
    rep["cache_root_entries"] = sorted(os.listdir(CACHE_ROOT)) if os.path.isdir(CACHE_ROOT) else None
    rep["cache_root_files_total"] = count_files(CACHE_ROOT)
    jp = os.path.join(AGENT_DIR, "job.json")
    rep["job_file"] = json.load(open(jp, encoding="utf-8")) if os.path.exists(jp) else None
    rep["agent_dir_entries"] = sorted(os.listdir(AGENT_DIR))
    # run start times per log (both guard folders hold the same run file per process)
    starts = {}
    for rf in rep["guards"]["tgr_frozen"]["run_files"]:
        sh = (rf["shard"] or "").split("/")[0]
        name = (f"v2_stage_a_luna_s{sh}.log" if rf["units_to_run"] == 250 else "v2_stage_a_luna_s0_resume1.log")
        starts[name] = rf["started"]
    rep["logs"] = logs_part(starts)
    # run total
    rep["run_total_cost_usd"] = r6(sum(rep["guards"][g]["all_lines_cost_usd"] for g in GUARDS))
    rep["run_total_conversations_good"] = sum(rep["guards"][g]["good_lines_first_per_task"] for g in GUARDS)
    # spend
    sp = soft_stop.spent_report()
    luna = sum(v for k, v in sp["by_file"].items() if k.startswith("stage_a/luna/"))
    smoke = sum(v for k, v in sp["by_file"].items() if k.startswith("smoke/"))
    nano = sum(v for k, v in sp["by_file"].items() if k.startswith("stage_a/nano/"))
    other = {k: v for k, v in sp["by_file"].items()
             if not (k.startswith("stage_a/luna/") or k.startswith("smoke/") or k.startswith("stage_a/nano/"))}
    rep["spend_now"] = {"at": dt.datetime.utcnow().strftime("%H:%M:%S UTC"), "total_usd": r6(sp["total_usd"]),
                        "by_file": sp["by_file"], "unreadable": sp["unreadable"], "error_lines": sp["error_lines"],
                        "error_lines_usd": r6(sp["error_lines_usd"]), "episode_files": sp["episode_files"],
                        "stage_b_files": sp["stage_b_files"],
                        "stage_a_luna_usd": r6(luna), "smoke_usd": r6(smoke), "stage_a_nano_usd": r6(nano),
                        "other_files": other}
    print(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
