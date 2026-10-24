#!/usr/bin/env python3
"""Compare gold v1 and gold v2 scoring of one run (SCORING ONLY; no LLM calls).

Reads <base>/<env>/<guard>/{episodes,gold,gold_v2}.jsonl (base = output/repro/p6/<tag>, as p6_gold_score.py) and
reports per env/guard:
  - executed write calls flagged by v1 and by v2, and the calls only v2 flags ("missed by v1"), split by the rules v2
    adds (AIR-R002 / RET-R005 explicit confirmation, AIR-R042 cancellation eligibility; the airline confirmation scope
    includes cancel_reservation, an interpretation of gold v1, so that part is listed separately) and by API acceptance;
  - conversations with ≥ 1 missed call; successful conversations without any gold violation under v1 and under v2;
  - block precision on scorable (write) blocks under v1 and v2.
Uses the latest record per (task, trial), as p6_metrics.py.
python scripts/reproduction/gold_compare.py <tag>   → <base>/gold_compare.json and a markdown table on stdout
"""
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NEW_RULES = {"AIR-R002": "confirmation", "RET-R005": "confirmation", "AIR-R042": "cancel_eligibility"}


def load(path):
    return [json.loads(l) for l in open(path)] if os.path.exists(path) else []


def latest(rows):
    last = {}
    for r in rows:
        last[(r["task_index"], r["trial"])] = r
    return last


def main():
    tag = sys.argv[1]
    base = f"{ROOT}/output/repro/p6/{tag}"
    out = {}
    for env in ("airline", "retail"):
        for guard in ("none", "direct", "shield", "tgr", "tgr_nob", "tgr_noc", "tgr_noa"):
            d = f"{base}/{env}/{guard}"
            eps = latest(load(f"{d}/episodes.jsonl"))
            g1, g2 = latest(load(f"{d}/gold.jsonl")), latest(load(f"{d}/gold_v2.jsonl"))
            if not eps or not g2:
                continue
            c = Counter({k: 0 for k in ("write_calls", "v1_violating", "v2_violating", "missed_by_v1", "missed_by_v1_api_accepted")})
            missed_eps, by_rule, by_tool = set(), Counter(), Counter()
            succ = comp1 = comp2 = 0
            blk = {"v1": [0, 0], "v2": [0, 0]}
            for key, e in eps.items():
                if e.get("error") is not None:
                    continue
                a, b = g1[key]["gold"], g2[key]["gold"]
                assert len(a["write_calls"]) == len(b["write_calls"])
                for ca, cb in zip(a["write_calls"], b["write_calls"]):
                    c["write_calls"] += 1
                    c["v1_violating"] += bool(ca["violations"])
                    c["v2_violating"] += bool(cb["violations"])
                    new = [v for v in cb["violations"] if v not in ca["violations"]]
                    if new and not ca["violations"]:
                        c["missed_by_v1"] += 1
                        c["missed_by_v1_api_accepted"] += not cb["api_rejected"]
                        missed_eps.add(key)
                    for v in new:
                        by_rule[v] += 1
                        if NEW_RULES.get(v) == "confirmation":
                            by_tool[cb["name"]] += 1
                if e["reward"] == 1.0:
                    succ += 1
                    comp1 += a["n_violating_calls"] == 0
                    comp2 += b["n_violating_calls"] == 0
                for ver, g in (("v1", a), ("v2", b)):
                    for x in g["blocks"]:
                        if x["scorable"] and not x["cap_override"]:
                            blk[ver][0] += 1
                            blk[ver][1] += bool(x["gold_violations"])
            n = len([e for e in eps.values() if e.get("error") is None])
            out[f"{env}/{guard}"] = {
                **c, "episodes": n, "episodes_with_missed_call": len(missed_eps),
                "missed_by_rule": dict(by_rule), "confirmation_missed_by_tool": dict(by_tool),
                "v1_violating_per_episode": c["v1_violating"] / n, "v2_violating_per_episode": c["v2_violating"] / n,
                "successful": succ, "success_compliant_v1": comp1, "success_compliant_v2": comp2,
                "block_precision_scorable_v1": blk["v1"][1] / blk["v1"][0] if blk["v1"][0] else None,
                "block_precision_scorable_v2": blk["v2"][1] / blk["v2"][0] if blk["v2"][0] else None,
                "scorable_blocks": blk["v2"][0], "blocks_confirmed_v1": blk["v1"][1], "blocks_confirmed_v2": blk["v2"][1],
            }
    json.dump(out, open(f"{base}/gold_compare.json", "w"), indent=1)
    f = lambda x: "–" if x is None else f"{x:.2f}"
    print("| env/guard | write calls | violating v1 | violating v2 | missed by v1 (API-accepted) | conv. with a missed call "
          "| missed: confirmation / cancel eligibility | success & compliant v1 → v2 | block precision v1 → v2 (scorable) |")
    print("|" + "---|" * 9)
    for k, v in out.items():
        r = v["missed_by_rule"]
        conf = r.get("AIR-R002", 0) + r.get("RET-R005", 0)
        print(f"| {k} | {v['write_calls']} | {v['v1_violating']} | {v['v2_violating']} | {v['missed_by_v1']} "
              f"({v['missed_by_v1_api_accepted']}) | {v['episodes_with_missed_call']}/{v['episodes']} | {conf} / "
              f"{r.get('AIR-R042', 0)} | {v['success_compliant_v1']}/{v['successful']} → {v['success_compliant_v2']}/"
              f"{v['successful']} | {f(v['block_precision_scorable_v1'])} → {f(v['block_precision_scorable_v2'])} "
              f"(n={v['scorable_blocks']}; {v['blocks_confirmed_v1']} → {v['blocks_confirmed_v2']}) |")


if __name__ == "__main__":
    main()
