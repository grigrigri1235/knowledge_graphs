"""E2: coverage of gold normative clauses by the automatic rules.

Subcommands:
  worksheet <domain> <run_dir> <out.md>   candidates per gold clause, for MANUAL labelling (Step 1 rubric)
  proxy <domain> <run_dir> <out.json>     automatic proxy labels: gpt-5-nano judge, k=3 majority
  score <domain> <run_dir> <labels.json> [--proxy proxy.json]   counts + agreement (accuracy, Cohen's kappa)

Manual label file: {"run": ..., "labels": {gold_clause_id: {"status": covered|partial|incorrect|missing,
                     "issues": [...], "auto_rules": [auto rule ids], "note": "..."}}}
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter

from eval.common import ROOT, aligned, auto, auto_rules_final, gold, load_json

STATUSES = ["covered", "partial", "incorrect", "missing"]
TAGS = ["SUBJ", "COND", "MODAL", "SCOPE", "NUM", "INV", "HALL", "MERGE", "DUP", "DROP", "TOOLS"]
ORIGINAL_EXTRACTION = {"airline": {"covered": 23, "partial": 31, "incorrect": 2, "missing": 5},
                       "retail": {"covered": 27, "partial": 11, "incorrect": 2, "missing": 6}}


def candidates(G, A, rules, top_k=3):
    from policy_pipeline.embed import embed
    gold_rules_by_clause = {}
    for r in G["rules"]:
        for c in r["source_clause_ids"]:
            gold_rules_by_clause.setdefault(c, []).append(r)
    ids = list(rules)
    E = embed([rules[i]["description"] for i in ids]) if ids else None
    out = {}
    for g in [c for c in G["clauses"] if c["kind"] == "normative"]:
        al = {a["clause_id"] for a in A["s1"]["clauses"] if a.get("span") and aligned(a["span"], g["span"])}
        by_source = [i for i in ids if set(rules[i]["source_clause_ids"]) & al]
        q = embed([g["atomic_reading"]] + [r["description"] for r in gold_rules_by_clause.get(g["clause_id"], [])])
        sims = (E @ q.T).max(axis=1) if ids else []
        by_sim = [ids[j] for j in sorted(range(len(ids)), key=lambda j: -sims[j])[:top_k]]
        out[g["clause_id"]] = {"clause": g, "gold_rules": gold_rules_by_clause.get(g["clause_id"], []),
                               "by_source": by_source, "by_similarity": [i for i in by_sim if i not in by_source],
                               "aligned_auto_clauses": sorted(al)}
    return out


def worksheet(domain, run_dir, out_md):
    G, A = gold(domain), auto(run_dir)
    rules = auto_rules_final(A)
    cand = candidates(G, A, rules)
    L = [f"# E2 worksheet — {domain} — {run_dir}", "", f"Auto rules: {len(rules)}", ""]
    for cid, c in cand.items():
        g = c["clause"]
        L += [f"## {cid}", f"- gold quote: \"{g['text']}\"", f"- gold reading: {g['atomic_reading']}",
              *[f"- GOLD {r['rule_id']}: {r['description']}" for r in c["gold_rules"]],
              f"- aligned auto clauses: {', '.join(c['aligned_auto_clauses']) or '—'}"]
        for tag, lst in (("SRC", c["by_source"]), ("SIM", c["by_similarity"])):
            for i in lst:
                r = rules[i]
                L.append(f"  - {tag} {i} [{','.join(r['related_tools'])}; {r['modality']}]: {r['description']}")
        L.append("")
    L += ["# All auto rules", ""] + [f"- {i} [{','.join(r['related_tools'])}; {r['modality']}; src {','.join(r['source_clause_ids'])}]: {r['description']}"
                                    for i, r in rules.items()]
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    open(out_md, "w").write("\n".join(L) + "\n")
    print(f"wrote {out_md}: {len(cand)} gold normative clauses, {len(rules)} auto rules")


PROXY_SYSTEM = """You evaluate how well automatically extracted rules capture one clause of a policy, by comparing them with a reference
rule written by an expert. The rules constrain an AI agent. Use this rubric for the REFERENCE CLAUSE:
- covered: some automatic rule(s) capture the clause fully and correctly: same conditions and exceptions, same modality (must / must not / only if / if and only if), same numbers and enumerations, phrased as an obligation of the agent, constraining the right actions.
- partial: the clause is captured but with a missing condition or exception, a weakened modality, a wrong scope (wrong actions/objects, too broad or narrow), or phrased as an obligation of someone other than the agent.
- incorrect: the automatic rules contradict the clause (wrong numbers or limits, inverted meaning).
- missing: no automatic rule captures the clause.
Issue tags (use the ones that apply): SUBJ (wrong subject), COND (condition dropped/added/ungrounded), MODAL (weakened modality), SCOPE (wrong scope), NUM (wrong number/enumeration), INV (inverted), HALL (invented content), MERGE (compound rule), DUP (duplicates), DROP (not extracted), TOOLS (wrong constrained actions).
Judge against the clause and the reference rule; interpretation choices that the reference states explicitly count as part of the reference. List the automatic rule ids you matched."""

PROXY_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["status", "issues", "matched_rule_ids", "reason"],
                "properties": {"status": {"type": "string", "enum": STATUSES},
                               "issues": {"type": "array", "items": {"type": "string", "enum": TAGS}},
                               "matched_rule_ids": {"type": "array", "items": {"type": "string"}}, "reason": {"type": "string"}}}


def proxy(domain, run_dir, out_json, k=3):
    from policy_pipeline.common import pmap
    from policy_pipeline.llm import LLM
    G, A = gold(domain), auto(run_dir)
    rules = auto_rules_final(A)
    cand = candidates(G, A, rules, top_k=5)
    llm = LLM(raw_dir=None)

    def judge(item):
        cid, c = item
        g = c["clause"]
        shown = c["by_source"] + c["by_similarity"]
        user = (f"REFERENCE CLAUSE (verbatim policy text): \"{g['text']}\"\nclause reading: {g['atomic_reading']}\n\n"
                + "REFERENCE RULE(S):\n" + "\n".join(f"- {r['description']}" for r in c["gold_rules"])
                + "\n\nAUTOMATIC RULES (id: description [constrained actions]):\n"
                + ("\n".join(f"- {i}: {rules[i]['description']} [{', '.join(rules[i]['related_tools'])}]" for i in shown) or "(none)"))
        samples = [llm.call(stage="e2_proxy", system=PROXY_SYSTEM, user=user, schema=PROXY_SCHEMA, schema_name="coverage",
                            effort="medium", sample=i) for i in range(k)]
        status = Counter(s["status"] for s in samples).most_common(1)[0][0]
        rep = next(s for s in samples if s["status"] == status)
        return cid, {"status": status, "votes": [s["status"] for s in samples], "issues": rep["issues"],
                     "auto_rules": rep["matched_rule_ids"], "reason": rep["reason"]}
    labels = dict(pmap(judge, list(cand.items()), 8))
    json.dump({"run": run_dir, "labels": labels, "usage": llm.usage_report()}, open(out_json, "w"), indent=1)
    print(f"wrote {out_json}: {Counter(v['status'] for v in labels.values())}")


def kappa(a, b, cats):
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = Counter(a), Counter(b)
    pe = sum(pa[c] * pb[c] for c in cats) / (n * n)
    return round((po - pe) / (1 - pe), 3) if pe < 1 else 1.0


def score(domain, run_dir, labels_path, proxy_path=None):
    G = gold(domain)
    gn = [c["clause_id"] for c in G["clauses"] if c["kind"] == "normative"]
    lab = load_json(labels_path)["labels"]
    missing = [c for c in gn if c not in lab]
    counts = Counter(lab[c]["status"] for c in gn if c in lab)
    tags = Counter(t for c in gn if c in lab for t in lab[c]["issues"])
    res = {"domain": domain, "run": run_dir, "n": len(gn), "unlabelled": missing,
           "counts": {s: counts.get(s, 0) for s in STATUSES}, "issue_tags": dict(tags.most_common()),
           "original_extraction": ORIGINAL_EXTRACTION[domain]}
    if proxy_path:
        pr = load_json(proxy_path)["labels"]
        both = [c for c in gn if c in lab and c in pr]
        a, b = [lab[c]["status"] for c in both], [pr[c]["status"] for c in both]
        conf = Counter((x, y) for x, y in zip(a, b))
        res["proxy"] = {"counts": dict(Counter(b)), "accuracy": round(sum(x == y for x, y in zip(a, b)) / max(1, len(both)), 3),
                        "kappa": kappa(a, b, STATUSES),
                        "covered_vs_not_accuracy": round(sum((x == "covered") == (y == "covered") for x, y in zip(a, b)) / max(1, len(both)), 3),
                        "confusion_manual_x_proxy": {f"{x}->{y}": n for (x, y), n in sorted(conf.items())},
                        "disagreements": [(c, lab[c]["status"], pr[c]["status"]) for c in both if lab[c]["status"] != pr[c]["status"]]}
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("worksheet"); w.add_argument("domain"); w.add_argument("run_dir"); w.add_argument("out")
    p = sub.add_parser("proxy"); p.add_argument("domain"); p.add_argument("run_dir"); p.add_argument("out")
    s = sub.add_parser("score"); s.add_argument("domain"); s.add_argument("run_dir"); s.add_argument("labels"); s.add_argument("--proxy")
    a = ap.parse_args()
    if a.cmd == "worksheet":
        worksheet(a.domain, a.run_dir, a.out)
    elif a.cmd == "proxy":
        proxy(a.domain, a.run_dir, a.out)
    else:
        print(json.dumps(score(a.domain, a.run_dir, a.labels, a.proxy), indent=1))
