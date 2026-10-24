"""Tests for state_tracker/tgr_to_aspm.py (Part 1). Standard library only, no LLM calls.

Run from predicate_correctness/:  python3 -m unittest tests.test_tgr_to_aspm -v
"""
from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_tracker import paths  # noqa: E402
from state_tracker.tgr_to_aspm import load_rule_set, to_aspm  # noqa: E402
from repro_runtime import mln  # noqa: E402  (path added by state_tracker.tgr_to_aspm)

EXPECTED = {"airline": {"rules": 34, "predicates": 42}, "retail": {"rules": 64, "predicates": 24}}
SAMPLE = 25          # judged guard records per run file
SAMPLE_BLOCKED = 10  # blocked guard records per run file


def guard_records(run: str, domain: str):
    """(judged sample, blocked sample) of saved guard records that have a judge."""
    judged, blocked = [], []
    with open(paths.episodes_path(run, domain), encoding="utf-8") as f:
        for line in f:
            ep = json.loads(line)
            for att in ep["attempts"]:
                g = att.get("guard")
                if not g or not g.get("judge"):
                    continue
                if len(judged) < SAMPLE:
                    judged.append(g)
                if g.get("action_allowed") is False and len(blocked) < SAMPLE_BLOCKED:
                    blocked.append(g)
            if len(judged) >= SAMPLE and len(blocked) >= SAMPLE_BLOCKED:
                break
    return judged, blocked


def redo_decision(aspm, g: dict) -> dict:
    """The decision of TGR's runtime (method_tgr/runtime.py::_step) from the saved judge values."""
    matched = g["matched"]
    current = {a: (a in matched) for a in aspm.action_predicates}
    current.update({n: v["value"] for n, v in g["judge"].items()})
    per_action = [mln.decide(aspm, g["circuit"], a, current, [], 0.1, 16) for a in matched]
    return {"allowed": all(d["allowed"] for d in per_action), "margin": min(d["margin"] for d in per_action)}


class TestStructure(unittest.TestCase):
    def test_counts_and_circuits(self):
        for domain, exp in EXPECTED.items():
            rs = load_rule_set(domain)
            aspm = to_aspm(rs)
            self.assertEqual(len(aspm.rules), exp["rules"], domain)
            conditions = {n for n, t in aspm.declared_types.items() if t == {"condition"}}
            self.assertEqual(len(conditions), exp["predicates"], domain)
            self.assertEqual(aspm.action_predicates, set(rs["action_names"]), domain)
            self.assertEqual(aspm.circuits, {a: list(ids) for a, ids in rs["circuits"].items()}, domain)
            for rule in aspm.rules.values():
                self.assertFalse(rule.formula.has_temporal, f"{domain} rule {rule.rule_id} is temporal")


class TestSavedDecisions(unittest.TestCase):
    def test_redo_matches_saved(self):
        for domain in paths.DOMAINS:
            aspm = to_aspm(load_rule_set(domain))
            for run in paths.RUNS:
                judged, blocked = guard_records(run, domain)
                self.assertTrue(judged, f"{run}/{domain}: no judged guard record")
                for g in judged + blocked:
                    got = redo_decision(aspm, g)
                    self.assertEqual(got["allowed"], g["action_allowed"], f"{run}/{domain} step {g.get('step_index')}")
                    self.assertAlmostEqual(got["margin"], g["margin"], places=9)


if __name__ == "__main__":
    unittest.main()
