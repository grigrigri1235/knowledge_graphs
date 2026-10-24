"""Online τ-bench episodes with per-role models (exp_core/model_profiles.json).

Same loop as repro_online/run.py (it reuses repro_online.episode.run_episode and the guards unchanged); differences:
  - --profile selects the role models (agent, user simulator, guard); exp_core.models.activate routes every call;
  - --aspm-dir: the ASPM the ShieldAgent guard loads (default: the published gpt-5-nano one, aspm_repro/<env>);
  - --rules-dir: the rule set a TGR guard (tgr, tgr_nob, tgr_noc, tgr_noa) loads (default: tgr_rules/<env>/<variant>);
  - output under output/tgr/online/<tag>/<env>/<guard>/episodes.jsonl (resumable, as P6);
  - agent and user cost/tokens are metered per episode by exp_core.models (τ-bench's user simulator keeps only the
    cost of its last call, so P6's per-episode user cost was the last call's cost), recorded in rec["usage_roles"]
    and used for rec["cost"]["agent"/"user"].

  python -m exp_core.run_online --profile luna-dev --env retail --guard none --tasks train --trials 1 --tag dev
Progress lines "[tgr-online] ..."; final line "[tgr-online] <env>/<guard> DONE".
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


def build_guard(name: str, env: str, tools_info: list, aspm_dir: str | None, rules_dir: str | None = None):
    from repro_online import guards
    if name == "shield" and aspm_dir:
        return ShieldGuardAt(aspm_dir, tools_info)
    return guards.build(name, env, tools_info, rules_dir=rules_dir)


def _shield_guard_at():
    from repro_online.guards import ShieldGuard

    class _ShieldGuardAt(ShieldGuard):
        """repro_online.guards.ShieldGuard (Stage-A config) loading an ASPM from a given run directory
        (aspm.json + weights.json + alg2.json of a repro_pipeline run) instead of aspm_repro/<domain>."""

        def __init__(self, aspm_dir: str, tools_info: list, aux_effort: str = "low", planner_effort: str = "medium",
                     epsilon: float = 0.1):
            from repro_runtime import aspm as A
            from repro_runtime.shield import Shield, ShieldConfig
            a2 = json.load(open(os.path.join(aspm_dir, "alg2.json")))
            aspm = A.load(aspm_dir, type_conflicts=sorted({c["name"] for c in a2["type_conflicts"]}))
            self.config = ShieldConfig(aux_effort=aux_effort, planner_effort=planner_effort, epsilon=epsilon)
            self.shield = Shield(aspm, tools_info, self.config)

    return _ShieldGuardAt


def ShieldGuardAt(aspm_dir, tools_info, **kw):
    return _shield_guard_at()(aspm_dir, tools_info, **kw)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--env", required=True)
    ap.add_argument("--guard", required=True)
    ap.add_argument("--tasks", default="train", help="splits.json label")
    ap.add_argument("--task-ids", default=None, help="comma-separated task indices (overrides --tasks)")
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--max-steps", type=int, default=30)
    ap.add_argument("--aspm-dir", default=None, help="ShieldAgent ASPM run directory (aspm.json, weights.json, alg2.json)")
    ap.add_argument("--rules-dir", default=None, help="TGR rule-set directory (rule_set.json; exp_core/tgr_build.py output)")
    a = ap.parse_args(argv)
    import repro_runtime.calls  # noqa: F401  (loaded before activate so its seams are re-pointed)
    import repro_runtime.plan  # noqa: F401
    from exp_core import models
    act = models.activate(a.profile, "guard")
    import tau_bench.envs.user as user_mod
    from tau_bench.envs import get_env
    from repro_online import episode
    user_mod.completion = episode.timed_user_completion(models.make_completion("user"))
    agent_completion = models.make_completion("agent")
    if a.task_ids:
        tasks = [int(x) for x in a.task_ids.split(",")]
    else:
        split = json.load(open(os.path.join(ROOT, "output", "reproduction", "labels", "splits.json")))[a.env]["split"]
        tasks = sorted(int(k) for k, v in split.items() if v == a.tasks)
    out_dir = os.path.join(ROOT, "output", "tgr", "online", a.tag, a.env, a.guard)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "episodes.jsonl")
    json.dump({"argv": sys.argv, "activation": act, "tasks": tasks, "started": time.strftime("%Y-%m-%dT%H:%M:%S")},
              open(os.path.join(out_dir, f"run_{time.strftime('%Y%m%d_%H%M%S')}.json"), "w"), indent=1)
    done_units = set()
    if os.path.exists(path):
        for line in open(path):
            r = json.loads(line)
            if r.get("error") is None:
                done_units.add((r["task_index"], r["trial"]))
    user_model = act["roles"]["user"]["model"]
    with contextlib.redirect_stdout(io.StringIO()):
        probe = get_env(a.env, user_strategy="llm", user_model=user_model, user_provider="azure", task_split="test", task_index=0)
    tools_info, wiki = probe.tools_info, probe.wiki
    guard = build_guard(a.guard, a.env, tools_info, a.aspm_dir, a.rules_dir)
    units = [(t, k) for k in range(a.trials) for t in tasks if (t, k) not in done_units]
    print(f"[tgr-online] {a.env}/{a.guard} ({a.profile}) start: {len(units)} episodes ({len(done_units)} already done), "
          f"{len(tasks)} tasks × {a.trials} trials", flush=True)
    started = time.time()

    def job(unit):
        t, k = unit
        models.reset_episode_usage()
        env = get_env(a.env, user_strategy="llm", user_model=user_model, user_provider="azure", task_split="test", task_index=t)
        try:
            rec = episode.run_episode(env, agent_completion, tools_info, wiki, guard, t, max_num_steps=a.max_steps)
            rec["error"] = None
        except Exception as e:  # noqa: BLE001 - recorded as a failed episode
            rec = {"task_index": t, "reward": 0.0, "error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()}
        u = json.loads(json.dumps(models.episode_usage()))
        rec["usage_roles"] = u
        if "cost" in rec:
            rec["cost"]["agent"], rec["cost"]["user"] = u["agent"]["cost"], u["user"]["cost"]
        rec.update({"env": a.env, "guard": a.guard, "trial": k, "profile": a.profile,
                    "models": {r: act["roles"][r]["model"] for r in ("agent", "user", "guard")}})
        with _write_lock:
            with open(path, "a") as f:
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return rec

    n = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for fut in as_completed([ex.submit(job, u) for u in units]):
            r = fut.result()
            n += 1
            c = r.get("cost") or {}
            print(f"[tgr-online] {a.env}/{a.guard} task {r['task_index']} trial {r['trial']}: reward {r['reward']} "
                  f"blocks {r.get('n_blocks')} cap {r.get('n_cap_overrides')} err {r['error'] is not None} "
                  f"cost {sum(c.values()):.4f} {r.get('seconds')}s ({n}/{len(units)}, {time.time() - started:.0f}s)", flush=True)
    print(f"[tgr-online] {a.env}/{a.guard} DONE: {n} episodes in {time.time() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
