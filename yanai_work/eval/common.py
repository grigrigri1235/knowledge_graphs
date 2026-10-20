"""Shared loaders for evaluating automatic ASPM runs against the gold standard (Steps 1-2).
Evaluation code MAY read gold artifacts; the pipeline (policy_pipeline/) may not."""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from policy_pipeline.common import find_span  # noqa: E402

WIKI = {"airline": "policy_docs/airline_wiki.txt", "retail": "policy_docs/retail_wiki.txt"}
OVERLAP = 0.5   # E1 alignment: overlap / shorter span >= 0.5


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def policy_text(domain):
    with open(os.path.join(ROOT, WIKI[domain]), encoding="utf-8") as f:
        return f.read()


def gold(domain):
    clauses = load_json(f"{ROOT}/policies/curated/{domain}_clauses.json")["clauses"]
    rules = load_json(f"{ROOT}/policies/curated/{domain}_curated_rules.json")["rules"]
    aspm = load_json(f"{ROOT}/aspm/{domain}_aspm.json")
    registry = {p["name"]: p for p in load_json(f"{ROOT}/policies/predicates/{domain}_predicates.json")["predicates"]}
    text = policy_text(domain)
    starts = [0]
    for line in text.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    for c in clauses:
        lo, hi = starts[c["wiki_line"] - 1], starts[c["wiki_line"]]
        c["span"] = find_span(text, c["text"], lo, hi)
        assert c["span"], c["clause_id"]
    return {"clauses": clauses, "rules": rules, "aspm": aspm, "registry": registry, "text": text}


def auto(run_dir):
    def opt(name):
        p = os.path.join(run_dir, name)
        return load_json(p) if os.path.exists(p) else None
    return {"dir": run_dir, "s0": opt("stage0_tools.json"), "s1": opt("stage1_clauses.json"), "s2": opt("stage2_rules.json"),
            "s3": opt("stage3_pruned.json"), "s4": opt("stage4_logic.json"), "s5": opt("stage5_vocab.json"),
            "aspm": opt("aspm.json"), "registry": opt("predicates.json"), "manifest": opt("manifest.json")}


def overlap(a, b):
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    if hi <= lo:
        return 0.0
    return (hi - lo) / max(1, min(a[1] - a[0], b[1] - b[0]))


def aligned(a_span, g_span):
    return overlap(a_span, g_span) >= OVERLAP


def auto_rules_final(A):
    """Auto rules after S5 (pre-replication), keyed by auto rule id; enforcement attached from the ASPM."""
    rules = {r["rule_id"]: r for r in A["s5"]["rules"] if not r.get("s5_errors")}
    enf = {}
    for rr in A["aspm"]["rule_list"]:
        enf.setdefault(rr["auto_rule_id"], rr.get("enforcement"))
    for rid, r in rules.items():
        r["enforcement"] = enf.get(rid)
    return rules
