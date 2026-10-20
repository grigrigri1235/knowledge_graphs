"""E3 worksheet: for every gold clause labelled 'covered' (manual E2 labels), pair the clause's first gold ASPM rule with
the first matched automatic rule and print both formulas and predicate lists, for MANUAL predicate mapping."""
import argparse
import json

from eval.common import auto, auto_rules_final, gold, load_json


def pairs(domain, run_dir, labels_path):
    G, A = gold(domain), auto(run_dir)
    lab = load_json(labels_path)["labels"]
    arules = auto_rules_final(A)
    gaspm = G["aspm"]["rule_list"]
    out, seen = [], set()
    for cid, l in lab.items():
        if l["status"] != "covered" or not l["auto_rules"]:
            continue
        cur = [r["rule_id"] for r in G["rules"] if cid in r["source_clause_ids"]]
        g = next((r for c in cur for r in gaspm if r["curated_rule_id"] == c), None)
        a = arules.get(l["auto_rules"][0])
        if g is None or a is None or (g["rule_id"], a["rule_id"]) in seen:
            continue
        seen.add((g["rule_id"], a["rule_id"]))
        out.append({"gold_clause": cid, "gold_rule": g["rule_id"], "curated": g["curated_rule_id"], "gold_logic": g["logic"],
                    "gold_preds": {p[0]: p[1] for p in g["predicates"] if p[3] == "condition"},
                    "auto_rule": a["rule_id"], "auto_logic": a["logic"],
                    "auto_preds": {p[0]: p[1] for p in a["predicates"] if p[3] == "condition"}})
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("domain"); ap.add_argument("run_dir"); ap.add_argument("labels")
    a = ap.parse_args()
    for p in pairs(a.domain, a.run_dir, a.labels):
        print(f"== {p['gold_clause']} | gold {p['gold_rule']} ({p['curated']}) | auto {p['auto_rule']}")
        print(f"   G: {p['gold_logic']}")
        for k, v in p["gold_preds"].items():
            print(f"      g.{k}: {v}")
        print(f"   A: {p['auto_logic']}")
        for k, v in p["auto_preds"].items():
            print(f"      a.{k}: {v}")
