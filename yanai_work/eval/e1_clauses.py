"""E1: clause segmentation vs gold clauses (alignment by quote span overlap in the policy text)."""
from __future__ import annotations

import argparse
import json

from eval.common import aligned, auto, gold, overlap


def e1(domain, run_dir):
    G, A = gold(domain), auto(run_dir)
    gc, ac = G["clauses"], [c for c in A["s1"]["clauses"] if c.get("span")]
    gn = [g for g in gc if g["kind"] == "normative"]
    an = [a for a in ac if a["kind"] == "normative"]
    recall_norm = [g for g in gn if any(aligned(a["span"], g["span"]) for a in an)]
    recall_any = [g for g in gn if any(aligned(a["span"], g["span"]) for a in ac)]
    precision = [a for a in an if any(aligned(a["span"], g["span"]) for g in gn)]
    # kind accuracy: each auto clause vs its best-overlapping gold clause
    pairs = []
    for a in ac:
        best = max(gc, key=lambda g: overlap(a["span"], g["span"]))
        if aligned(a["span"], best["span"]):
            pairs.append((a, best))
    kind_acc = sum(a["kind"] == g["kind"] for a, g in pairs) / max(1, len(pairs))
    confusion = {}
    for a, g in pairs:
        k = f"gold={g['kind']} auto={a['kind']}"
        confusion[k] = confusion.get(k, 0) + 1
    return {
        "domain": domain, "run": run_dir,
        "gold_clauses": len(gc), "gold_normative": len(gn), "auto_clauses": len(ac), "auto_normative": len(an),
        "normative_recall": round(len(recall_norm) / len(gn), 3), "normative_recall_n": f"{len(recall_norm)}/{len(gn)}",
        "normative_recall_any_kind": round(len(recall_any) / len(gn), 3),
        "normative_precision": round(len(precision) / max(1, len(an)), 3), "normative_precision_n": f"{len(precision)}/{len(an)}",
        "kind_accuracy": round(kind_acc, 3), "kind_pairs": len(pairs), "kind_confusion": confusion,
        "missed_gold_normative": [g["clause_id"] for g in gn if g not in recall_norm],
        "missed_gold_normative_but_aligned_as_fact": [g["clause_id"] for g in gn if g in recall_any and g not in recall_norm],
        "unaligned_auto_normative": [(a["clause_id"], a["quote"]) for a in an if a not in precision],
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("domain")
    ap.add_argument("run_dir")
    a = ap.parse_args()
    print(json.dumps(e1(a.domain, a.run_dir), indent=1, ensure_ascii=False))
