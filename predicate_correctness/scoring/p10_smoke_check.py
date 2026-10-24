"""Part 10 subtask 6: check the smoke-test conversations (stdlib only, no LLM call).

Reads output/online/<tag>/<env>/tgr_tracker/episodes.jsonl and prints, per conversation: errors, reward, blocks,
cost and time per role, guard checks, judge calls, values replaced and changed, lookup errors, replay problems,
and the text of every block (the feedback the agent saw). It also checks each guard record:
  - 'judge' has a value and a 'source' for every circuit predicate;
  - the tracker part exists, version b, and only code-type predicates were replaced;
  - a replaced value equals the tracker value (and is never unknown);
  - a predicate whose lookup gave unknown keeps the judge's value.
Then it projects the full Part 10 cost from the partner's saved TGR runs (ratio on the same tasks).

Usage: python3 -B scoring/p10_smoke_check.py <tag> [partner_online_dir]
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


def load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def code_preds(env):
    with open(TYPES, encoding="utf-8") as f:
        t = json.load(f)
    d = t.get(env, t)
    if isinstance(d, dict) and "predicates" in d:
        d = d["predicates"]
    out = set()
    for name, v in d.items():
        typ = v.get("type") if isinstance(v, dict) else v
        if typ in CODE_TYPES:
            out.add(name)
    return out


def main():
    tag = sys.argv[1]
    problems = []
    tot = {"conv": 0, "cost": 0.0, "agent": 0.0, "user": 0.0, "guard": 0.0, "sec": 0.0, "checks": 0, "judge_calls": 0,
           "skipped": 0, "replaced": 0, "changed": 0, "lookup_err": 0, "mismatch": 0, "blocks": 0, "errors": 0,
           "unknown_kept": 0, "tracker_sec": 0.0}
    per_task_cost = {}
    first_state = None
    for env in ("airline", "retail"):
        p = os.path.join(OUT, "online", tag, env, "tgr_tracker", "episodes.jsonl")
        if not os.path.exists(p):
            continue
        cp = code_preds(env)
        for r in load(p):
            tot["conv"] += 1
            if r.get("error"):
                tot["errors"] += 1
                problems.append(f"{env} task {r['task_index']}: error {r['error']}")
                continue
            c = r.get("cost") or {}
            cost = sum(c.values())
            per_task_cost[(env, r["task_index"])] = cost
            for k in ("agent", "user", "guard"):
                tot[k] += c.get(k, 0.0)
            tot["cost"] += cost
            tot["sec"] += r.get("seconds") or 0
            tot["blocks"] += r.get("n_blocks") or 0
            n_rep = n_chg = n_err = n_mis = n_sk = n_j = n_unk = 0
            for a in r["attempts"]:
                g = a.get("guard") or {}
                tr = g.get("tracker")
                tot["checks"] += 1
                n_j += (g.get("usage") or {}).get("n_llm_calls", 0)
                circuit_preds = set(g.get("judge", {}).keys())
                if tr is None:
                    problems.append(f"{env} t{r['task_index']} step {a['exec_step']}: no tracker part")
                    continue
                if first_state is None:
                    first_state = tr.get("state")
                if tr.get("version") != "b":
                    problems.append(f"{env} t{r['task_index']}: version {tr.get('version')}")
                n_sk += bool(tr.get("judge_skipped"))
                n_err += len(tr.get("lookup_errors") or [])
                st = tr.get("state") or {}
                mis = st.get("mismatches")
                n_mis += (len(mis) if isinstance(mis, list) else (mis or 0))
                tot["tracker_sec"] += st.get("seconds") or 0     # state build + lookups (no LLM)
                for pred in tr.get("replaced") or []:
                    n_rep += 1
                    if pred not in cp:
                        problems.append(f"{env} t{r['task_index']}: replaced non-code predicate {pred}")
                    used = (g["judge"].get(pred) or {})
                    tv = (tr.get("tracker_values") or {}).get(pred)
                    tvv = tv.get("value") if isinstance(tv, dict) else tv
                    if used.get("value") != tvv or tvv in (None, "unknown"):
                        problems.append(f"{env} t{r['task_index']}: {pred} used {used.get('value')} tracker {tvv}")
                n_chg += len(tr.get("changed") or [])
                for pred, tv in (tr.get("tracker_values") or {}).items():
                    tvv = tv.get("value") if isinstance(tv, dict) else tv
                    if tvv in (None, "unknown"):
                        n_unk += 1
                        jv = (tr.get("judge_values") or {}).get(pred)
                        jvv = jv.get("value") if isinstance(jv, dict) else jv
                        if (g["judge"].get(pred) or {}).get("value") != jvv:
                            problems.append(f"{env} t{r['task_index']}: unknown {pred} did not keep judge value")
                for pred, v in g.get("judge", {}).items():
                    if not isinstance(v, dict) or "source" not in v or "value" not in v:
                        problems.append(f"{env} t{r['task_index']}: judge entry {pred} lacks value/source")
                for pred in tr.get("code_predicates") or []:
                    if pred not in cp:
                        problems.append(f"{env} t{r['task_index']}: code_predicates has {pred} (not code type)")
                    if pred not in circuit_preds:
                        problems.append(f"{env} t{r['task_index']}: code predicate {pred} not in circuit")
            for k, v in (("replaced", n_rep), ("changed", n_chg), ("lookup_err", n_err), ("mismatch", n_mis),
                         ("skipped", n_sk), ("judge_calls", n_j), ("unknown_kept", n_unk)):
                tot[k] += v
            ur = r.get("usage_roles") or {}
            print(f"== {env} task {r['task_index']} trial {r['trial']}: reward {r['reward']} done {r.get('done')} "
                  f"steps {r.get('n_exec_steps')} blocks {r.get('n_blocks')} cap {r.get('n_cap_overrides')} "
                  f"seconds {r.get('seconds')} models {r.get('models')}")
            print(f"   cost agent {c.get('agent', 0):.4f} user {c.get('user', 0):.4f} guard {c.get('guard', 0):.4f} "
                  f"total {cost:.4f}; calls {r.get('calls')}; latency {r.get('latency')}")
            print(f"   usage_roles agent calls {ur.get('agent', {}).get('calls')} user calls "
                  f"{ur.get('user', {}).get('calls')}")
            print(f"   guard checks {len(r['attempts'])}, judge calls {n_j}, judge skipped {n_sk}, replaced {n_rep}, "
                  f"changed {n_chg}, tracker unknown {n_unk}, lookup errors {n_err}, replay mismatches {n_mis}")
            for a in r["attempts"]:
                g = a.get("guard") or {}
                tr = g.get("tracker") or {}
                mark = "BLOCK" if a.get("blocked") else "ok"
                print(f"   - step {a['exec_step']}.{a['attempt']} {mark} {g.get('name')} margin {g.get('margin')} "
                      f"violated {g.get('violated_rules')} changed {tr.get('changed')} "
                      f"src {sorted(set(v.get('source') for v in g.get('judge', {}).values() if isinstance(v, dict)))}")
                if a.get("blocked"):
                    print(f"     action: {str(g.get('action_text'))[:300]}")
                    print(f"     reason: {str(g.get('reason'))[:1500]}")
                    print(f"     observation (feedback to agent): {str(a.get('observation'))[:1500]}")
                    print(f"     judge values used: { {k: (v.get('value'), v.get('source')) for k, v in g['judge'].items()} }")
                    print(f"     tracker values: {tr.get('tracker_values')}")
                if tr.get("changed"):
                    print(f"     changed detail: judge {[(p, tr['judge_values'].get(p)) for p in tr['changed']]} "
                          f"tracker {[(p, tr['tracker_values'].get(p)) for p in tr['changed']]}")
    print("\n== first tracker.state record:", json.dumps(first_state)[:600])
    n = max(tot["conv"] - tot["errors"], 1)
    print("\n== totals", json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in tot.items()}))
    print(f"== per conversation: cost {tot['cost'] / n:.4f} (agent {tot['agent'] / n:.4f}, user {tot['user'] / n:.4f}, "
          f"guard {tot['guard'] / n:.4f}); seconds {tot['sec'] / n:.1f}; tracker state-build seconds per check "
          f"{tot['tracker_sec'] / max(tot['checks'], 1):.3f}")

    # Projection from the partner's saved TGR runs (read only), ratio on the same tasks.
    part = sys.argv[2] if len(sys.argv) > 2 else PARTNER
    runs = {"luna_train_v5": 3, "nano_train": 3, "luna_val": 3}
    full, same = {}, {}
    for run in runs:
        for env in ("airline", "retail"):
            p = os.path.join(part, run, env, "tgr", "episodes.jsonl")
            rows = [r for r in load(p) if not r.get("error")]
            full[(run, env)] = sum(sum((r.get("cost") or {}).values()) for r in rows)
            if run == "luna_train_v5":
                for r in rows:
                    if (env, r["task_index"]) in per_task_cost:
                        same.setdefault((env, r["task_index"]), []).append(sum((r.get("cost") or {}).values()))
    ours = sum(per_task_cost.values())
    theirs = sum(sum(v) / len(v) for v in same.values())
    ratio = ours / theirs if theirs else float("nan")
    base = sum(full.values())
    print("\n== projection")
    for k, v in full.items():
        print(f"   partner TGR {k[0]} {k[1]}: ${v:.3f}")
    print(f"   partner TGR total for the same 6 run/domain parts: ${base:.2f}")
    print(f"   smoke tasks: ours ${ours:.4f} vs partner TGR mean on the same tasks ${theirs:.4f} -> ratio {ratio:.2f}")
    print(f"   projected Part 10 cost: ${base * ratio:.2f} (ratio x partner); with ratio 1.5 margin: "
          f"${base * max(ratio, 1) * 1.5:.2f}")
    print(f"\n== problems: {len(problems)}")
    for x in problems:
        print("  ", x)


if __name__ == "__main__":
    main()
