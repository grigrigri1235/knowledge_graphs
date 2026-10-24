"""Eval v2 Part 5, Stage A smoke test: checks of the 10 smoke conversations (standard library only, no LLM call).

Reads output/eval_v2/smoke/stage_a/luna/<guard>/{episodes.jsonl, run_*.json}, the job file, the two judge cache
folders (output/_llmcache/v2_smoke_stage_a_luna/<guard>/structured) and the soft-stop spend. Prints one JSON report.
Run from predicate_correctness/:
  PYTHONDONTWRITEBYTECODE=1 /home/azureuser/miniconda3/bin/python3 -B -m scoring.v2_p5_smoke_a_check
Never imports gold code, the runner copy or τ-bench.
"""
from __future__ import annotations

import glob
import json
import os
import sys

sys.dont_write_bytecode = True

from guard import soft_stop                      # noqa: E402  (stdlib only)
from state_tracker import paths                  # noqa: E402

AGENT_DIR = os.path.join(paths.OUTPUT_DIR, "eval_v2", "smoke", "stage_a", "luna")
CACHE_ROOT = os.path.join(paths.OUTPUT_DIR, "_llmcache", "v2_smoke_stage_a_luna")
GUARDS = ("tgr_frozen", "tgr_tracker")
TASKS = [1, 24, 30, 88, 99]
MODELS = {"agent": "gpt-6-luna", "user": "gpt-6-luna", "guard": "gpt-6-luna"}


def count_files(root):
    return sum(len(f) for _, _, f in os.walk(root)) if os.path.isdir(root) else 0


def cache_names(root):
    out = set()
    for d, _, fs in os.walk(root):
        out.update(fs)
    return out


def main():
    rep = {"agent_dir": AGENT_DIR, "cache_root": CACHE_ROOT, "guards": {}}
    for g in GUARDS:
        d = os.path.join(AGENT_DIR, g)
        lines = [json.loads(x) for x in open(os.path.join(d, "episodes.jsonl"), encoding="utf-8") if x.strip()]
        convs, problems = [], []
        n_checks = n_with_tracker = n_judge_vals = n_judge_vals_with_source = 0
        trk = {"checks": 0, "with_judge_values": 0, "with_replaced": 0, "with_changed_field": 0,
               "lookup_errors_nonempty": 0, "state_mismatches": 0, "state_parse_problems": 0, "state_problems": 0,
               "not_applied": 0, "judge_skipped": 0, "replaced_values": 0, "changed_values": 0,
               "source_tracker_values": 0, "source_judge_values": 0, "changed_list": []}
        usage_calls = usage_hits = 0
        usage_cost = 0.0
        blocks = []
        for r in lines:
            c = r.get("cost") or {}
            u = r.get("usage_roles") or {}
            calls = r.get("calls") or {}
            row = {"task": r["task_index"], "trial": r["trial"], "reward": r["reward"], "done": r.get("done"),
                   "error": r.get("error"), "has_reward_info": isinstance(r.get("reward_info"), dict),
                   "n_attempts": len(r.get("attempts") or []), "n_exec": r.get("n_exec_steps"),
                   "n_blocks": r.get("n_blocks"), "n_cap": r.get("n_cap_overrides"), "seconds": r.get("seconds"),
                   "cost_agent": c.get("agent"), "cost_user": c.get("user"), "cost_guard": c.get("guard"),
                   "cost_total": round(soft_stop.line_cost(r), 6),
                   "agent_calls": calls.get("agent"), "user_calls_loop": calls.get("user"),
                   "user_calls_usage": (u.get("user") or {}).get("calls"),
                   "guard_checks": calls.get("guard_checks"), "guard_llm": calls.get("guard_llm")}
            convs.append(row)
            if r.get("task_split") != "train":
                problems.append(f"task {r['task_index']}: task_split {r.get('task_split')!r}")
            if r.get("models") != MODELS:
                problems.append(f"task {r['task_index']}: models {r.get('models')}")
            if r.get("profile") != "luna-dev" or r.get("env") != "retail" or r.get("guard") != g:
                problems.append(f"task {r['task_index']}: profile/env/guard {r.get('profile')}/{r.get('env')}/{r.get('guard')}")
            if r.get("error") is not None:
                problems.append(f"task {r['task_index']}: error {r['error']}")
            if row["user_calls_usage"] != (row["user_calls_loop"] or 0) + 1:
                problems.append(f"task {r['task_index']}: user calls usage {row['user_calls_usage']} != loop + 1")
            for i, a in enumerate(r.get("attempts") or []):
                gr = a.get("guard") or {}
                n_checks += 1
                us = gr.get("usage") or {}
                usage_calls += us.get("n_llm_calls") or 0
                usage_hits += us.get("cache_hits") or 0
                usage_cost += us.get("cost_usd") or 0.0
                jv = gr.get("judge") or {}
                n_judge_vals += len(jv)
                n_judge_vals_with_source += sum(1 for v in jv.values() if isinstance(v, dict) and "source" in v)
                if a.get("blocked"):
                    blocks.append({"task": r["task_index"], "attempt_idx": i, "action": a.get("action"),
                                   "attempt": a.get("attempt"), "cap_override": a.get("cap_override"),
                                   "violated_rules": [v.get("rule_id") if isinstance(v, dict) else v
                                                      for v in (gr.get("violated_rules") or [])],
                                   "margin": gr.get("margin"),
                                   "feedback_start": (a.get("feedback") or "")[:160]})
                if "tracker" not in gr:
                    continue
                n_with_tracker += 1
                t = gr["tracker"]
                trk["checks"] += 1
                trk["with_judge_values"] += isinstance(t.get("judge_values"), dict)
                trk["with_replaced"] += isinstance(t.get("replaced"), list)
                trk["with_changed_field"] += isinstance(t.get("changed"), list)
                trk["lookup_errors_nonempty"] += bool(t.get("lookup_errors"))
                st = t.get("state") or {}
                trk["state_mismatches"] += st.get("mismatches") or 0
                trk["state_parse_problems"] += st.get("parse_problems") or 0
                trk["state_problems"] += st.get("problems") or 0
                trk["not_applied"] += not t.get("applied")
                trk["judge_skipped"] += bool(t.get("judge_skipped"))
                trk["replaced_values"] += len(t.get("replaced") or [])
                trk["changed_values"] += len(t.get("changed") or [])
                trk["source_tracker_values"] += sum(1 for v in jv.values() if isinstance(v, dict) and v.get("source") == "tracker")
                trk["source_judge_values"] += sum(1 for v in jv.values() if isinstance(v, dict) and v.get("source") == "judge")
                # every replaced predicate must be marked source tracker, every other one source judge
                for k, v in jv.items():
                    want = "tracker" if k in (t.get("replaced") or []) else "judge"
                    if not isinstance(v, dict) or v.get("source") != want:
                        problems.append(f"task {r['task_index']} att {i}: {k} source {v.get('source') if isinstance(v, dict) else v} != {want}")
                if t.get("changed"):
                    trk["changed_list"].append({"task": r["task_index"], "attempt_idx": i, "action": a.get("action"),
                                                "blocked": a.get("blocked"), "changed": t.get("changed"),
                                                "judge_values": {k: t["judge_values"].get(k) for k in t["changed"]},
                                                "used": {k: (jv.get(k) or {}).get("value") for k in t["changed"]}})
        convs.sort(key=lambda x: x["task"])
        n = len(convs)
        tot = lambda k: round(sum((x[k] or 0) for x in convs), 6)          # noqa: E731
        runs = sorted(glob.glob(os.path.join(d, "run_*.json")))
        run_caches = []
        for rp in runs:
            plan = json.load(open(rp, encoding="utf-8"))["plan"]
            run_caches.append({k: v["structured_cache"] for k, v in plan["paths"]["guards"].items()})
        cache_dir = os.path.join(CACHE_ROOT, g, "structured")
        rep["guards"][g] = {
            "lines": n, "tasks": sorted(x["task"] for x in convs), "trials": sorted({x["trial"] for x in convs}),
            "conversations": convs, "problems": problems,
            "rewards": {x["task"]: x["reward"] for x in convs}, "reward_sum": tot("reward"),
            "cost": {"agent": tot("cost_agent"), "user": tot("cost_user"), "guard": tot("cost_guard"),
                     "total": tot("cost_total")},
            "cost_per_conv": {k: round(v / n, 6) for k, v in
                              {"agent": tot("cost_agent"), "user": tot("cost_user"), "guard": tot("cost_guard"),
                               "total": tot("cost_total")}.items()},
            "seconds_per_conv": round(tot("seconds") / n, 1), "seconds_max": max(x["seconds"] for x in convs),
            "guard_checks": n_checks, "checks_with_tracker_field": n_with_tracker,
            "judge_values": n_judge_vals, "judge_values_with_source": n_judge_vals_with_source,
            "guard_usage": {"llm_calls": usage_calls, "cache_hits": usage_hits, "cost_usd": round(usage_cost, 6)},
            "blocks": blocks,
            "tracker": trk if g == "tgr_tracker" else None,
            "run_files": [os.path.basename(x) for x in runs], "run_file_caches": run_caches,
            "judge_cache_dir": cache_dir, "judge_cache_files": count_files(cache_dir),
        }
    a, b = (cache_names(os.path.join(CACHE_ROOT, g, "structured")) for g in GUARDS)
    rep["judge_cache_shared_file_names"] = len(a & b)
    rep["cache_root_entries"] = sorted(os.listdir(CACHE_ROOT)) if os.path.isdir(CACHE_ROOT) else None
    rep["cache_root_files_total"] = count_files(CACHE_ROOT)
    jp = os.path.join(AGENT_DIR, "job.json")
    rep["job_file"] = json.load(open(jp, encoding="utf-8")) if os.path.exists(jp) else None
    rep["agent_dir_entries"] = sorted(os.listdir(AGENT_DIR))
    sp = soft_stop.spent_report()
    rep["spend_now"] = {"total_usd": round(sp["total_usd"], 6), "by_file": sp["by_file"],
                        "unreadable": sp["unreadable"], "error_lines": sp["error_lines"]}
    smoke_a = sum(v for k, v in sp["by_file"].items() if k.startswith("smoke/stage_a/"))
    rep["spend_this_run_usd"] = round(smoke_a, 6)
    rep["total_conversations"] = sum(rep["guards"][g]["lines"] for g in GUARDS)
    rep["total_cost_usd"] = round(sum(rep["guards"][g]["cost"]["total"] for g in GUARDS), 6)
    print(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
