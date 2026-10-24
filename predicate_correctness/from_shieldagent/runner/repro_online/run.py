"""P6 runner: online τ-bench episodes for one domain and one guard configuration.

  python -m repro_online.run --env airline --guard shield --tasks test --trials 3 --workers 12
  python -m repro_online.run --env retail --guard none --task-ids 0,1,7 --trials 1 --tag smoke
Tasks: τ-bench test-split task indices whose splits.json label is the requested split (default "test").
Output: output/repro/p6/<tag>/<env>/<guard>/episodes.jsonl (resumable: finished (task, trial) units are skipped).
Progress lines "[p6] ..."; final line "[p6] <env>/<guard> DONE".
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_write_lock = threading.Lock()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True)
    ap.add_argument("--guard", required=True, choices=["none", "direct", "shield", "tgr", "tgr_nob", "tgr_noc", "tgr_noa"])
    ap.add_argument("--tasks", default="test", help="splits.json label")
    ap.add_argument("--task-ids", default=None, help="comma-separated task indices (overrides --tasks)")
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--tag", default="full")
    ap.add_argument("--max-steps", type=int, default=30)
    a = ap.parse_args(argv)
    from repro_core.taubench_run import make_completion
    import tau_bench.envs.user as user_mod
    from tau_bench.envs import get_env
    from repro_online import episode, guards
    user_mod.completion = episode.timed_user_completion(make_completion("user"))
    agent_completion = make_completion("agent")
    if a.task_ids:
        tasks = [int(x) for x in a.task_ids.split(",")]
    else:
        split = json.load(open(os.path.join(ROOT, "output", "reproduction", "labels", "splits.json")))[a.env]["split"]
        tasks = sorted(int(k) for k, v in split.items() if v == a.tasks)
    out_dir = os.path.join(ROOT, "output", "repro", "p6", a.tag, a.env, a.guard)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "episodes.jsonl")
    done_units = set()
    if os.path.exists(path):
        for line in open(path):
            r = json.loads(line)
            if r.get("error") is None:
                done_units.add((r["task_index"], r["trial"]))
    with contextlib.redirect_stdout(io.StringIO()):
        probe = get_env(a.env, user_strategy="llm", user_model="gpt-5-nano", user_provider="azure", task_split="test", task_index=0)
    tools_info, wiki = probe.tools_info, probe.wiki
    guard = guards.build(a.guard, a.env, tools_info)
    units = [(t, k) for k in range(a.trials) for t in tasks if (t, k) not in done_units]
    print(f"[p6] {a.env}/{a.guard} start: {len(units)} episodes ({len(done_units)} already done), {len(tasks)} tasks × {a.trials} trials", flush=True)
    started = time.time()

    def job(unit):
        t, k = unit
        # no redirect_stdout here: it swaps sys.stdout for the whole process and swallowed the progress lines (bug P6-B1)
        env = get_env(a.env, user_strategy="llm", user_model="gpt-5-nano", user_provider="azure", task_split="test", task_index=t)
        try:
            rec = episode.run_episode(env, agent_completion, tools_info, wiki, guard, t, max_num_steps=a.max_steps)
            rec["error"] = None
        except Exception as e:  # noqa: BLE001 - recorded as a failed episode
            rec = {"task_index": t, "reward": 0.0, "error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()}
        rec.update({"env": a.env, "guard": a.guard, "trial": k})
        with _write_lock:
            with open(path, "a") as f:
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return rec

    n = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for fut in as_completed([ex.submit(job, u) for u in units]):
            r = fut.result()
            n += 1
            print(f"[p6] {a.env}/{a.guard} task {r['task_index']} trial {r['trial']}: reward {r['reward']} "
                  f"blocks {r.get('n_blocks')} cap {r.get('n_cap_overrides')} err {r['error'] is not None} "
                  f"{r.get('seconds')}s ({n}/{len(units)}, {time.time() - started:.0f}s)", flush=True)
    print(f"[p6] {a.env}/{a.guard} DONE: {n} episodes in {time.time() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
