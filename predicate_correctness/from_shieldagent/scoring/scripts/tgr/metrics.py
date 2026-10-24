#!/usr/bin/env python3
"""Metrics for TGR-stage online runs (output/tgr/online/<tag>/), the same as P6 plus repeat-after-block.

1. runs the P6 gold scorer and P6 metrics (scripts/reproduction/p6_gold_score.py, p6_metrics.py) with gold v1 and
   gold v2 (policies/gold_v2, scoring only), and gold_compare.py; their base path is output/repro/p6/<tag>, so they get
   the relative tag ../../tgr/online/<tag>;
2. adds, per env/guard (→ <base>/metrics_tgr.json):
   - response to a block: for every blocked (non-override) attempt, the next attempt in the same conversation is
     "repeat" (same action and same arguments), "respond" (a reply to the user) or "other" (another action);
     the P6 report (§3) used the same definition (computed ad hoc there);
   - per-role tokens and the cost with cached-input billing (agent/user; guard at list price);
   - paired Δ pass^1 vs no shield and vs Direct (per-task mean difference, bootstrap 95 % CI over tasks as P6);
   - conversations with ≥ 1 block and the maximum number of blocks in one conversation (P6 §3 columns);
   - violations under gold v2: attempted (executed violating write calls + blocked violating write attempts),
     blocked (caught) and executed, per conversation and in total;
3. prints a compact table.
python scripts/tgr/metrics.py <tag> [--guards none,direct,shield]
"""
import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = sys.executable
sys.path.insert(0, os.path.join(ROOT, "scripts", "reproduction"))
from p6_metrics import boot  # noqa: E402  (same bootstrap as P6: B = 10,000, seed 0)


def load(path):
    return [json.loads(l) for l in open(path)] if os.path.exists(path) else []


def latest(eps):
    last = {}
    for e in eps:
        last[(e["task_index"], e["trial"])] = e
    return list(last.values())


def per_task_success(eps):
    per_task = defaultdict(list)
    for e in eps:
        per_task[e["task_index"]].append(1.0 if (e.get("error") is None and e["reward"] == 1.0) else 0.0)
    return {t: sum(v) / len(v) for t, v in per_task.items()}


def paired_delta(a, b):
    """pass^1(a) − pass^1(b), paired by task; bootstrap CI over tasks."""
    tasks = sorted(set(a) & set(b))
    d = {t: a[t] - b[t] for t in tasks}
    return {"delta": sum(d.values()) / len(d), "ci": boot(d, lambda s: sum(s) / len(s)), "tasks": len(d)}


def block_responses(eps):
    c = Counter()
    for e in eps:
        atts = e["attempts"]
        for i, x in enumerate(atts[:-1]):
            if not x["blocked"]:
                continue
            nxt = atts[i + 1]
            if nxt["action"] == x["action"] and nxt["kwargs"] == x["kwargs"]:
                c["repeat"] += 1
            elif nxt["action"] == "respond":
                c["respond"] += 1
            else:
                c["other"] += 1
    n = sum(c.values())
    return {"n": n, **{k: (c[k] / n if n else None) for k in ("repeat", "respond", "other")}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--guards", default="none,direct,shield,tgr,tgr_nob,tgr_noc")
    ap.add_argument("--skip-p6", action="store_true", help="only the additions (gold.jsonl/metrics.json already made)")
    a = ap.parse_args()
    rel = f"../../tgr/online/{a.tag}"
    base = os.path.join(ROOT, "output", "tgr", "online", a.tag)
    if not a.skip_p6:
        for script, extra in (("p6_gold_score.py", []), ("p6_metrics.py", []), ("p6_gold_score.py", ["--gold", "v2"]),
                              ("p6_metrics.py", ["--gold", "v2"]), ("gold_compare.py", [])):
            r = subprocess.run([PY, os.path.join(ROOT, "scripts", "reproduction", script), rel, *extra], cwd=ROOT,
                               capture_output=True, text=True)
            if r.returncode:
                raise SystemExit(f"{script} failed:\n{r.stderr[-3000:]}")
    p6 = json.load(open(os.path.join(base, "metrics.json")))
    p6v2 = json.load(open(os.path.join(base, "metrics_gold_v2.json")))
    prices = json.load(open(os.path.join(ROOT, "exp_core", "model_profiles.json")))["pricing"]
    out = {}
    for env in ("airline", "retail"):
        succ = {g: per_task_success(latest(load(os.path.join(base, env, g, "episodes.jsonl"))))
                for g in a.guards.split(",")}
        for guard in a.guards.split(","):
            eps = load(os.path.join(base, env, guard, "episodes.jsonl"))
            ok = [e for e in latest(eps) if e.get("error") is None]
            if not ok:
                continue
            paired = {f"vs_{ref}": paired_delta(succ[guard], succ[ref])
                      for ref in ("none", "direct") if ref != guard and succ.get(ref)}
            nblk = [sum(1 for x in e["attempts"] if x["blocked"]) for e in ok]
            g2 = {(r["task_index"], r["trial"]): r["gold"] for r in load(os.path.join(base, env, guard, "gold_v2.jsonl"))}
            gold_ok = [g2.get((e["task_index"], e["trial"])) for e in ok]
            executed_v = sum(g["n_violating_calls"] for g in gold_ok if g)
            blocked_v = sum(1 for g in gold_ok if g for b in g["blocks"]
                            if b["scorable"] and not b["cap_override"] and b["gold_violations"])
            violations = {"attempted": executed_v + blocked_v, "blocked": blocked_v, "executed": executed_v,
                          "executed_api_accepted": sum(g["n_violating_calls_api_accepted"] for g in gold_ok if g)}
            tok = {r: {k: sum(e["usage_roles"][r][k] for e in ok) / len(ok) for k in
                       ("calls", "input_tokens", "cached_tokens", "output_tokens", "reasoning_tokens")} for r in ("agent", "user")}
            billed = 0.0
            for e in ok:
                pr = prices[e["models"]["agent"]]
                for r in ("agent", "user"):
                    u = e["usage_roles"][r]
                    billed += ((u["input_tokens"] - u["cached_tokens"]) * pr["input_per_m"] + u["cached_tokens"] * pr["cached_input_per_m"]
                               + u["output_tokens"] * pr["output_per_m"]) / 1e6
                billed += e["cost"]["guard"]
            out[f"{env}/{guard}"] = {"pass1_paired_delta": paired, "violations_v2": violations,
                                     "episodes_with_block": sum(1 for n in nblk if n), "max_blocks": max(nblk),
                                     "ended_with_transfer": sum(1 for e in ok if [x for x in e["attempts"] if not x["blocked"]]
                                                                and [x for x in e["attempts"] if not x["blocked"]][-1]["action"]
                                                                .startswith("transfer_to_human")),
                                     "block_response": block_responses(ok), "tokens_per_episode": tok,
                                     "cost_per_episode_cache_billed": billed / len(ok),
                                     "models": sorted({json.dumps(e["models"], sort_keys=True) for e in ok})}
    json.dump(out, open(os.path.join(base, "metrics_tgr.json"), "w"), indent=1)
    hdr = ("env/guard", "eps", "pass^1 [95% CI]", "pass^3", "blk/ep", "cap", "prec v1", "prec v2", "caught v2", "repeat",
           "viol/ep v2", "transfer", "$/ep", "s/ep")
    print("| " + " | ".join(hdr) + " |\n|" + "---|" * len(hdr))
    for k, v in out.items():
        m, m2 = p6[k], p6v2[k]
        f = lambda x, d=2: "–" if x is None else f"{x:.{d}f}"
        print(f"| {k} | {m['episodes']} | {m['pass1']:.3f} [{m['pass1_ci'][0]:.2f}, {m['pass1_ci'][1]:.2f}] | "
              f"{f(m.get('pass3'), 3)} | {m['blocks_per_episode']:.2f} | {m['cap_overrides']} | {f(m['block_precision_scorable_blocks'])} | "
              f"{f(m2['block_precision_scorable_blocks'])} | {round((m2['block_precision_scorable_blocks'] or 0) * m2['blocks_scorable_write'])} | "
              f"{f(v['block_response']['repeat'])} | {m2['gold_violating_calls_per_episode']:.3f} | {v['ended_with_transfer']} | "
              f"{sum(m['cost_per_episode'].values()):.4f} | {m['wall_per_episode_s']:.0f} |")


if __name__ == "__main__":
    main()
