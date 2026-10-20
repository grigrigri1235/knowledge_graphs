"""Runtime judge load (Step 3 planning): rules, block rules and distinct condition predicates per write-tool circuit,
auto (every condition predicate is LLM-judged) vs gold (only `dialogue` predicates need the judge).

python -m eval.runtime_load   -> prints tables, writes eval/results/judge_load.json
"""
import json

from eval.common import ROOT, load_json

def circuit_rules(aspm, tool):
    parents = {}
    def walk(n, ps):
        name = n["name"] if isinstance(n, dict) else n
        parents[name] = ps
        if isinstance(n, dict):
            for k in ("L2_children", "L3_children"):
                for c in n.get(k, []): walk(c, ps + [name])
    for l1 in aspm["action_tree"]["L1_actions"]: walk(l1, [])
    ids = set()
    for node in [tool] + parents.get(tool, []):
        ids.update(aspm["actions"].get(node, {}).get("soft_rule_ids", []))
    by = {r["rule_id"]: r for r in aspm["rule_list"]}
    return [by[i] for i in ids]
out = {}
for dom, auto_dir in (("airline", "output/auto_aspm/airline/v1"), ("retail", "output/auto_aspm/retail/v1"), ("airline_addendum", "output/auto_aspm/airline/v1_addendum")):
    d = dom.split("_")[0]
    A = load_json(f"{ROOT}/{auto_dir}/aspm.json")
    G = load_json(f"{ROOT}/aspm/{d}_aspm.json")
    greg = {p["name"]: p for p in load_json(f"{ROOT}/policies/predicates/{d}_predicates.json")["predicates"]}
    writes = [t["name"] for t in load_json(f"{ROOT}/policies/tau_bench/{d}_tools.json")["tools"] if t["writes_db"]]
    rows = {}
    for t in writes:
        ar, gr = circuit_rules(A, t), circuit_rules(G, t)
        ap = {p[0] for r in ar for p in r["predicates"] if p[3] == "condition"}
        gp = {p[0] for r in gr for p in r["predicates"] if p[3] == "condition"}
        gdlg = {p for p in gp if greg.get(p, {}).get("type") == "dialogue"}
        rows[t] = {"auto_rules": len(ar), "auto_block": sum(r.get("enforcement") == "block" for r in ar), "auto_preds_judged": len(ap),
                   "gold_rules": len(gr), "gold_block": sum(r.get("enforcement") == "block" for r in gr), "gold_preds": len(gp), "gold_preds_judged": len(gdlg)}
    tot = {k: sum(v[k] for v in rows.values()) for k in next(iter(rows.values()))}
    out[dom] = {"per_tool": rows, "sum": tot, "mean_auto_preds_per_call": round(tot["auto_preds_judged"] / len(rows), 1),
                "mean_gold_judged_preds_per_call": round(tot["gold_preds_judged"] / len(rows), 1)}
    print(f"== {dom}")
    print(f"{'tool':32} {'A rules':>7} {'A blk':>5} {'A preds':>7} | {'G rules':>7} {'G blk':>5} {'G preds':>7} {'G dlg':>5}")
    for t, v in rows.items():
        print(f"{t:32} {v['auto_rules']:7} {v['auto_block']:5} {v['auto_preds_judged']:7} | {v['gold_rules']:7} {v['gold_block']:5} {v['gold_preds']:7} {v['gold_preds_judged']:5}")
    print("mean auto judged preds/call", out[dom]["mean_auto_preds_per_call"], "| mean gold judged preds/call", out[dom]["mean_gold_judged_preds_per_call"])
json.dump(out, open(f"{ROOT}/eval/results/judge_load.json", "w"), indent=1)
