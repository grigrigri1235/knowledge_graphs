"""Part 10 subtask 7: status and checks of the full runs (stdlib only, no LLM call).

For each run tag and domain (output/online/<tag>/<env>/tgr_tracker/episodes.jsonl) it prints:
  - lines in the file, units done without error (one per (task, trial)), lines with an error, units missing;
  - mean reward over done units (first good line per unit), blocks, cost so far;
  - guard-record checks: checks without a tracker part, lookup errors, replay mismatches, replaced predicates that are
    not code types, values replaced / changed, judge skipped, tracker unknowns.
Then a spend projection: spend so far (all p10 tags, smoke included) + the remaining units of these runs at the mean
cost per unit seen so far (partner TGR's mean if none done yet) + the val run (partner luna_val TGR cost x our cost
ratio against partner TGR on luna train). It prints "OVER CAP" if the projection is above the cap.

Usage: python3 -B scoring/p10_runs_check.py [--cap 25] tag:expected_units_airline:expected_units_retail ...
       e.g. python3 -B scoring/p10_runs_check.py p10_luna_train:60:138 p10_nano_train:60:138
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "output")
PARTNER = "/home/azureuser/ShieldAgent/output/tgr/online"     # read only
TYPES = os.path.join(OUT, "predicate_types.json")
CODE_TYPES = {"argument", "database fact", "event"}
PARTNER_RUN = {"p10_luna_train": "luna_train_v5", "p10_nano_train": "nano_train", "p10_luna_val": "luna_val"}


def load(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def code_preds(env):
    with open(TYPES, encoding="utf-8") as f:
        t = json.load(f)
    d = t.get(env, t)
    if isinstance(d, dict) and "predicates" in d:
        d = d["predicates"]
    return {n for n, v in d.items() if (v.get("type") if isinstance(v, dict) else v) in CODE_TYPES}


def cost_of(r):
    return sum((r.get("cost") or {}).values())


def main():
    args = sys.argv[1:]
    cap = 25.0
    if "--cap" in args:
        i = args.index("--cap")
        cap = float(args[i + 1])
        del args[i:i + 2]
    runs = []
    for a in args:
        tag, na, nr = a.split(":")
        runs.append((tag, {"airline": int(na), "retail": int(nr)}))

    spent_all = 0.0
    for tag in sorted(os.listdir(os.path.join(OUT, "online"))):
        if not tag.startswith("p10_"):
            continue
        for env in ("airline", "retail"):
            spent_all += sum(cost_of(r) for r in load(os.path.join(OUT, "online", tag, env, "tgr_tracker",
                                                                  "episodes.jsonl")))
    remaining = 0.0
    ratio_num = ratio_den = 0.0
    problems_total = 0
    print(f"{'tag':16} {'env':8} lines good err_lines missing  reward  blocks/conv  cost_so_far  cost/conv  "
          f"partnerTGR_cost/conv")
    for tag, expect in runs:
        for env in ("airline", "retail"):
            rows = load(os.path.join(OUT, "online", tag, env, "tgr_tracker", "episodes.jsonl"))
            good = {}
            err = [r for r in rows if r.get("error")]
            for r in rows:
                if not r.get("error"):
                    good.setdefault((r["task_index"], r["trial"]), r)
            n_good = len(good)
            missing = expect[env] - n_good
            spent = sum(cost_of(r) for r in rows)
            per = (sum(cost_of(r) for r in good.values()) / n_good) if n_good else None
            prow = [r for r in load(os.path.join(PARTNER, PARTNER_RUN[tag], env, "tgr", "episodes.jsonl"))
                    if not r.get("error")]
            pper = sum(cost_of(r) for r in prow) / len(prow) if prow else 0.0
            if tag == "p10_luna_train" and n_good:
                pmean = {}
                for r in prow:
                    pmean.setdefault(r["task_index"], []).append(cost_of(r))
                for (t, _k), r in good.items():
                    if t in pmean:
                        ratio_num += cost_of(r)
                        ratio_den += sum(pmean[t]) / len(pmean[t])
            remaining += max(missing, 0) * (per if per is not None else pper)
            rew = sum(r.get("reward") or 0 for r in good.values()) / n_good if n_good else float("nan")
            blk = sum(r.get("n_blocks") or 0 for r in good.values()) / n_good if n_good else float("nan")
            print(f"{tag:16} {env:8} {len(rows):5} {n_good:4} {len(err):9} {missing:7}  {rew:6.3f}  {blk:11.2f}  "
                  f"{spent:11.3f}  {per if per is not None else float('nan'):9.4f}  {pper:9.4f}")
            for r in err:
                print(f"     error line: task {r['task_index']} trial {r.get('trial')}: {str(r['error'])[:200]}")
            # guard-record checks
            cp = code_preds(env)
            c = {"checks": 0, "no_tracker": 0, "lookup_err": 0, "mismatch": 0, "non_code_replaced": 0, "replaced": 0,
                 "changed": 0, "skipped": 0, "unknown": 0, "judge_calls": 0, "cap": 0}
            for r in good.values():
                c["cap"] += r.get("n_cap_overrides") or 0
                for a in r.get("attempts") or []:
                    g = a.get("guard") or {}
                    tr = g.get("tracker")
                    c["checks"] += 1
                    c["judge_calls"] += (g.get("usage") or {}).get("n_llm_calls", 0)
                    if tr is None:
                        if g.get("judge"):
                            c["no_tracker"] += 1
                        continue
                    c["lookup_err"] += len(tr.get("lookup_errors") or [])
                    mis = (tr.get("state") or {}).get("mismatches")
                    c["mismatch"] += len(mis) if isinstance(mis, list) else (mis or 0)
                    c["skipped"] += bool(tr.get("judge_skipped"))
                    c["replaced"] += len(tr.get("replaced") or [])
                    c["changed"] += len(tr.get("changed") or [])
                    c["non_code_replaced"] += sum(1 for p in tr.get("replaced") or [] if p not in cp)
                    for tv in (tr.get("tracker_values") or {}).values():
                        if (tv.get("value") if isinstance(tv, dict) else tv) in (None, "unknown"):
                            c["unknown"] += 1
            problems_total += c["no_tracker"] + c["non_code_replaced"]
            print(f"     guard: {json.dumps(c)}")
    ratio = ratio_num / ratio_den if ratio_den else 1.0
    val = sum(cost_of(r) for env in ("airline", "retail")
              for r in load(os.path.join(PARTNER, "luna_val", env, "tgr", "episodes.jsonl")) if not r.get("error"))
    proj = spent_all + remaining + val * max(ratio, 1.0)
    print(f"\nspent so far (all p10 tags, smoke included): ${spent_all:.3f}")
    print(f"remaining units of these runs at the current cost per unit: ${remaining:.3f}")
    print(f"cost ratio ours / partner TGR on luna train (same tasks): {ratio:.3f}")
    print(f"val run (partner luna_val TGR ${val:.3f} x max(ratio, 1)): ${val * max(ratio, 1.0):.3f}")
    print(f"projected total Part 10 spend: ${proj:.3f} (cap ${cap:.2f}) -> {'OVER CAP' if proj > cap else 'under cap'}")
    print(f"record problems (no tracker part with a judge, non-code replaced): {problems_total}")


if __name__ == "__main__":
    main()
