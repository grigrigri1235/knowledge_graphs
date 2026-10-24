#!/usr/bin/env python3
"""P6 metrics per domain and guard: pass^1 / pass^3 (bootstrap 95 % CI over tasks), blocks, cap overrides,
D9 gold compliance, block precision proxy, top blocking rules, cost and latency, failures.
python scripts/reproduction/p6_metrics.py <tag> [--trials 3] [--gold v1|v2]   (run p6_gold_score.py <tag> [--gold ..] first)
   --gold v1 (default) reads gold.jsonl and writes metrics.json; v2 reads gold_v2.jsonl and writes metrics_gold_v2.json
"""
import argparse
import json
import os
import random
from collections import Counter, defaultdict
from math import comb

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def pass_k(succ, n, k):
    return comb(succ, k) / comb(n, k) if n >= k else float("nan")


def boot(per_task, stat, B=10000, seed=0):
    rnd = random.Random(seed)
    tasks = list(per_task)
    vals = []
    for _ in range(B):
        sample = [per_task[rnd.choice(tasks)] for _ in tasks]
        vals.append(stat(sample))
    vals.sort()
    return vals[int(0.025 * B)], vals[int(0.975 * B) - 1]


def load(path):
    return [json.loads(l) for l in open(path)] if os.path.exists(path) else []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--gold", choices=("v1", "v2"), default="v1")
    a = ap.parse_args()
    gold_file, out_file = ("gold.jsonl", "metrics.json") if a.gold == "v1" else (f"gold_{a.gold}.jsonl", f"metrics_gold_{a.gold}.json")
    base = f"{ROOT}/output/repro/p6/{a.tag}"
    out = {}
    for env in [d for d in ("airline", "retail") if os.path.isdir(f"{base}/{d}")]:
        for guard in ("none", "direct", "shield", "tgr", "tgr_nob", "tgr_noc", "tgr_noa"):
            eps = load(f"{base}/{env}/{guard}/episodes.jsonl")
            if not eps:
                continue
            gold = {(g["task_index"], g["trial"]): g["gold"] for g in load(f"{base}/{env}/{guard}/{gold_file}")}
            # keep the latest record per (task, trial) (a resumed run may append a retry after an error)
            last = {}
            for e in eps:
                last[(e["task_index"], e["trial"])] = e
            eps = list(last.values())
            ok = [e for e in eps if e.get("error") is None]
            per_task = defaultdict(list)
            for e in eps:
                per_task[e["task_index"]].append(1.0 if (e.get("error") is None and e["reward"] == 1.0) else 0.0)
            k = min(a.trials, min(len(v) for v in per_task.values()))
            p1 = sum(sum(v) / len(v) for v in per_task.values()) / len(per_task)
            p1_ci = boot({t: v for t, v in per_task.items()}, lambda s: sum(sum(v) / len(v) for v in s) / len(s))
            pk = sum(pass_k(int(sum(v)), len(v), k) for v in per_task.values()) / len(per_task)
            pk_ci = boot({t: v for t, v in per_task.items()}, lambda s: sum(pass_k(int(sum(v)), len(v), k) for v in s) / len(s))
            succ = [e for e in ok if e["reward"] == 1.0]
            g_succ = [gold.get((e["task_index"], e["trial"])) for e in succ]
            g_all = [gold.get((e["task_index"], e["trial"])) for e in ok]
            compliant = sum(1 for g in g_succ if g and g["n_violating_calls"] == 0)
            compliant_acc = sum(1 for g in g_succ if g and g["n_violating_calls_api_accepted"] == 0)
            viol_per_ep = sum(g["n_violating_calls"] for g in g_all if g) / max(len(g_all), 1)
            viol_rules = Counter(v for g in g_all if g for c in g["write_calls"] for v in c["violations"])
            blocks = [b for g in g_all if g for b in g["blocks"] if not b["cap_override"]]
            scorable = [b for b in blocks if b["scorable"]]
            prec_all = sum(1 for b in scorable if b["gold_violations"]) / len(blocks) if blocks else None
            prec_scor = sum(1 for b in scorable if b["gold_violations"]) / len(scorable) if scorable else None
            atts = [x for e in ok for x in e["attempts"]]
            blocked_atts = [x for x in atts if x["blocked"]]
            rule_counter = Counter(v["rule_id"] for x in blocked_atts for v in (x["guard"] or {}).get("violated_rules", []))
            block_kinds = Counter("respond" if x["action"] == "respond" else x["action"] for x in blocked_atts)
            cost = {r: sum(e["cost"][r] for e in ok) / max(len(ok), 1) for r in ("agent", "user", "guard")}
            lat = {r: sum(e["latency"][r] for e in ok) / max(len(ok), 1) for r in ("agent", "user", "guard")}
            checks = sum(e["calls"]["guard_checks"] for e in ok)
            res = {
                "episodes": len(eps), "errors": len(eps) - len(ok), "tasks": len(per_task), "trials_per_task": k,
                "pass1": p1, "pass1_ci": p1_ci, f"pass{k}": pk, f"pass{k}_ci": pk_ci,
                "not_done_max_steps": sum(1 for e in ok if not e["done"]),
                "blocks_per_episode": len(blocked_atts) / max(len(ok), 1),
                "cap_overrides": sum(e["n_cap_overrides"] for e in ok),
                "successful_episodes": len(succ),
                "compliance_success_no_gold_violation": compliant / len(succ) if succ else None,
                "compliance_success_no_api_accepted_violation": compliant_acc / len(succ) if succ else None,
                "gold_violating_calls_per_episode": viol_per_ep,
                "gold_violated_rules": viol_rules.most_common(10),
                "blocks_total": len(blocks), "blocks_scorable_write": len(scorable),
                "block_precision_all_blocks": prec_all, "block_precision_scorable_blocks": prec_scor,
                "blocked_action_kinds": block_kinds.most_common(), "top_blocking_rules": rule_counter.most_common(10),
                "cost_per_episode": cost, "cost_total": sum(sum(e["cost"].values()) for e in ok),
                "latency_per_episode_s": lat, "wall_per_episode_s": sum(e["seconds"] for e in ok) / max(len(ok), 1),
                "guard_latency_per_check_s": (sum(e["latency"]["guard"] for e in ok) / checks) if checks else None,
                "guard_cost_per_check": (sum(e["cost"]["guard"] for e in ok) / checks) if checks else None,
                "error_examples": [e["error"] for e in eps if e.get("error")][:5],
            }
            out[f"{env}/{guard}"] = res
            print(f"\n## {env} / {guard}")
            for kk, vv in res.items():
                print(f"- {kk}: {vv}")
    json.dump(out, open(f"{base}/{out_file}", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
