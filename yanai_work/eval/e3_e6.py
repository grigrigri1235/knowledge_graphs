"""E3 (logic equivalence), E4 (circuit recall), E5 (enforcement / value-source agreement), E6 (cost).

E3/E5 read a MANUAL mapping file eval/labels/<tag>_e3.json:
  {"pairs": [{"gold_clause": "...", "gold_rule": "<gold ASPM rule_id>", "auto_rule": "<auto rule id (S5, pre-replication)>",
              "map": {"<auto condition predicate>": "<expression over gold predicates, e.g. 'x', 'NOT x', 'x AND y', 'TRUE'>" | null},
              "note": "..."}]}
Action predicates of both rules are set to TRUE (the pair is compared on the action it constrains).
"""
from __future__ import annotations

import argparse
import glob
import itertools
import json
import os
import re
from collections import Counter, defaultdict

from eval.common import ROOT, auto, auto_rules_final, gold, load_json

OPS = {"AND", "OR", "NOT", "IMPLIES"}


def _parser():
    import scripts.validate_aspm as vm
    return vm.Parser, vm.kleene


def _names(expr):
    return [t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr) if t not in OPS and t not in ("TRUE", "FALSE")]


def compare(gold_logic, gold_actions, auto_logic, auto_actions, mapping):
    """Return (verdict, detail): equivalent | auto_stricter | auto_weaker | not_equivalent | not_comparable."""
    Parser, kleene = _parser()
    if any(v is None for v in mapping.values()):
        return "not_comparable", [k for k, v in mapping.items() if v is None]
    gtree, atree = Parser(gold_logic).parse(), Parser(auto_logic).parse()
    mtrees = {k: Parser(v).parse() for k, v in mapping.items()}
    variables = sorted({n for n in _names(gold_logic) if n not in gold_actions} |
                       {n for v in mapping.values() for n in _names(v)})
    g_only = a_only = 0
    for vals in itertools.product([False, True], repeat=len(variables)):
        env = dict(zip(variables, vals), TRUE=True, FALSE=False)
        genv = dict(env, **{a: True for a in gold_actions})
        g = kleene(gtree, genv)
        aenv = {a: True for a in auto_actions}
        for k, t in mtrees.items():
            aenv[k] = kleene(t, env)
        a = kleene(atree, aenv)
        if g and not a:
            a_only += 1      # auto forbids what gold allows
        if a and not g:
            g_only += 1      # auto allows what gold forbids
    if not a_only and not g_only:
        return "equivalent", {}
    if a_only and not g_only:
        return "auto_stricter", {"assignments_auto_forbids_gold_allows": a_only}
    if g_only and not a_only:
        return "auto_weaker", {"assignments_auto_allows_gold_forbids": g_only}
    return "not_equivalent", {"auto_stricter": a_only, "auto_weaker": g_only}


def e3_e5(domain, run_dir, mapping_path):
    G, A = gold(domain), auto(run_dir)
    grules = {r["rule_id"]: r for r in G["aspm"]["rule_list"]}
    arules = auto_rules_final(A)
    areg = {p["name"]: p for p in A["registry"]["predicates"]}
    pairs = load_json(mapping_path)["pairs"]
    out, enf, vsrc = [], Counter(), Counter()
    for p in pairs:
        g, a = grules[p["gold_rule"]], arules[p["auto_rule"]]
        gacts = [x[0] for x in g["predicates"] if x[3] == "action"]
        aacts = [x[0] for x in a["predicates"] if x[3] == "action"]
        verdict, detail = compare(g["logic"], gacts, a["logic"], aacts, p["map"])
        out.append({**p, "gold_logic": g["logic"], "auto_logic": a["logic"], "verdict": verdict, "detail": detail,
                    "gold_enforcement": g["enforcement"], "auto_enforcement": a.get("enforcement")})
        enf[(g["enforcement"], a.get("enforcement"))] += 1
        for ap, expr in p["map"].items():
            if expr is None:
                continue
            gnames = _names(expr)
            if len(gnames) != 1 or ap not in areg:
                continue
            gtype = G["registry"][gnames[0]]["type"]
            gclass = {"state": "data", "tool_log": "data", "structural": "structural", "dialogue": "dialogue"}[gtype]
            vs = set(areg[ap]["value_source"])
            aclass = "dialogue" if vs == {"dialogue"} else ("data" if "dialogue" not in vs else "mixed")
            vsrc[(gclass, aclass)] += 1
    verdicts = Counter(o["verdict"] for o in out)
    n_enf = sum(enf.values())
    vs_comp = sum(n for (g, a), n in vsrc.items() if g in ("data", "dialogue"))
    vs_agree = sum(n for (g, a), n in vsrc.items() if g == a)
    return {"domain": domain, "pairs": len(out), "e3_verdicts": dict(verdicts),
            "e3_equivalent_rate": round(verdicts["equivalent"] / max(1, len(out)), 3),
            "e5_enforcement_agreement": round(sum(n for (g, a), n in enf.items() if g == a) / max(1, n_enf), 3),
            "e5_enforcement_confusion_gold_x_auto": {f"{g}->{a}": n for (g, a), n in sorted(enf.items(), key=str)},
            "e5_value_source_agreement": round(vs_agree / max(1, vs_comp), 3), "e5_value_source_n": vs_comp,
            "e5_value_source_confusion_gold_x_auto": {f"{g}->{a}": n for (g, a), n in sorted(vsrc.items())},
            "details": out}


def circuit(aspm, tool, key):
    """Set of `key` values of the rules in the circuit of `tool` (own + ancestors)."""
    parents = {}

    def walk(n, ps):
        name = n["name"] if isinstance(n, dict) else n
        parents[name] = ps
        if isinstance(n, dict):
            for k in ("L2_children", "L3_children"):
                for c in n.get(k, []):
                    walk(c, ps + [name])
    for l1 in aspm["action_tree"]["L1_actions"]:
        walk(l1, [])
    if tool not in parents:
        return set(), 0
    ids = set()
    for node in [tool] + parents[tool]:
        ids.update(aspm["actions"].get(node, {}).get("soft_rule_ids", []))
    by_id = {r["rule_id"]: r for r in aspm["rule_list"]}
    return {by_id[i].get(key) for i in ids}, len(ids)


def e4(domain, run_dir, labels_path):
    G, A = gold(domain), auto(run_dir)
    labels = load_json(labels_path)["labels"]
    tools_json = load_json(f"{ROOT}/policies/tau_bench/{domain}_tools.json")["tools"]
    writes = [t["name"] for t in tools_json if t["writes_db"]]
    gclauses = {c["clause_id"]: c for c in G["clauses"]}
    curated = {r["rule_id"]: r for r in G["rules"]}
    res = {}
    for tool in writes:
        gcur, gsize = circuit(G["aspm"], tool, "curated_rule_id")
        acur, asize = circuit(A["aspm"], tool, "auto_rule_id")
        found = []
        for cid in sorted(gcur):
            norm = [c for c in curated[cid]["source_clause_ids"] if gclauses[c]["kind"] == "normative"]
            matched = {r for c in norm if labels.get(c, {}).get("status") in ("covered", "partial") for r in labels[c].get("auto_rules", [])}
            found.append((cid, bool(matched & acur)))
        res[tool] = {"gold_curated_rules": len(gcur), "recalled": sum(f for _, f in found),
                     "recall": round(sum(f for _, f in found) / max(1, len(gcur)), 3),
                     "missed": [c for c, f in found if not f], "gold_circuit_size": gsize, "auto_circuit_size": asize}
    tot_g = sum(v["gold_curated_rules"] for v in res.values())
    tot_r = sum(v["recalled"] for v in res.values())
    return {"domain": domain, "per_tool": res, "micro_recall": round(tot_r / max(1, tot_g), 3)}


def e6(run_dir):
    """Cost of the run as if uncached: usage of every call the run made (raw/ keeps one record per distinct call)."""
    per = defaultdict(lambda: Counter())
    for p in glob.glob(os.path.join(run_dir, "raw", "*.json")):
        r = load_json(p)
        st = per[r["stage"]]
        st["calls"] += 1
        for k, v in r["usage"].items():
            st[k] += v
    man = load_json(os.path.join(run_dir, "manifest.json"))
    tot = Counter()
    for v in per.values():
        tot.update(v)
    return {"per_stage": {k: dict(v) for k, v in sorted(per.items())}, "total": dict(tot),
            "stage_wall_seconds": man["stage_seconds"], "wall_seconds_total": round(sum(man["stage_seconds"].values()), 1),
            "note": "wall seconds of a re-run with a warm cache are lower; tokens are the full cost of the distinct calls"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("e3"); a.add_argument("domain"); a.add_argument("run_dir"); a.add_argument("mapping")
    b = sub.add_parser("e4"); b.add_argument("domain"); b.add_argument("run_dir"); b.add_argument("labels")
    c = sub.add_parser("e6"); c.add_argument("run_dir")
    args = ap.parse_args()
    if args.cmd == "e3":
        r = e3_e5(args.domain, args.run_dir, args.mapping)
        print(json.dumps({k: v for k, v in r.items() if k != "details"}, indent=1))
    elif args.cmd == "e4":
        print(json.dumps(e4(args.domain, args.run_dir, args.labels), indent=1))
    else:
        print(json.dumps(e6(args.run_dir), indent=1))
