"""Tests for state_tracker/decide_again.py (Part 8). Standard library only, no LLM calls.

Run from predicate_correctness/:  python3 -B -m unittest tests.test_decide_again -v
"""
from __future__ import annotations

import collections
import itertools
import json
import os
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_tracker import paths  # noqa: E402
from state_tracker import decide_again as D  # noqa: E402
from state_tracker.load_steps import read_steps  # noqa: E402
from state_tracker.tgr_to_aspm import load_rule_set, to_aspm  # noqa: E402

SAMPLE = 60   # saved records per run and domain for the check-1 test


class TestHelpers(unittest.TestCase):
    def test_replaced_versions(self):
        judge = {"p": True, "q": False, "r": None, "s": True}
        tracker = {"p": False, "q": None, "r": True}
        self.assertEqual(D.replaced(judge, tracker, "a"), {"p": False, "q": None, "r": True, "s": True})
        self.assertEqual(D.replaced(judge, tracker, "b"), {"p": False, "q": False, "r": True, "s": True})
        self.assertEqual(judge, {"p": True, "q": False, "r": None, "s": True})   # not changed in place
        with self.assertRaises(ValueError):
            D.replaced(judge, tracker, "c")

    def test_differing_keeps_three_values_apart(self):
        self.assertEqual(D.differing({"p": None, "q": False, "r": True}, {"p": False, "q": False, "r": None}), ["p", "r"])

    def test_change_and_verdict(self):
        self.assertIsNone(D.change_kind(True, True))
        self.assertEqual(D.change_kind(False, True), "block removed")
        self.assertEqual(D.change_kind(True, False), "block added")
        self.assertEqual(D.judge_by_reference(False, True, True), "fixes an error")
        self.assertEqual(D.judge_by_reference(False, True, False), "adds an error")
        self.assertEqual(D.judge_by_reference(True, False, False), "fixes an error")
        self.assertIsNone(D.judge_by_reference(True, False, None))
        self.assertIsNone(D.judge_by_reference(True, True, True))

    def test_choose(self):
        def c(wb_a, wa_a, wb_b, wa_b):
            return {"a": {"wrong": collections.Counter({("a", "wrong block"): wb_a, ("a", "wrong allow"): wa_a})},
                    "b": {"wrong": collections.Counter({("b", "wrong block"): wb_b, ("b", "wrong allow"): wa_b})}}
        self.assertEqual(D.choose(c(1, 0, 2, 0))[0], "a")
        self.assertEqual(D.choose(c(3, 5, 2, 9))[0], "b")
        self.assertEqual(D.choose(c(2, 1, 2, 3))[0], "a")
        self.assertEqual(D.choose(c(2, 1, 2, 1))[0], "b")


class TestSavedRecords(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.aspm = {d: to_aspm(load_rule_set(d)) for d in paths.DOMAINS}

    def test_check1_on_a_sample(self):
        """The rebuilt input equals the saved trace position, and the decision equals the saved one."""
        n = blocked = 0
        for run, domain in paths.RUN_DOMAINS:
            for rec in itertools.islice(read_steps(run, domain), SAMPLE):
                jv = D.judge_values(rec)
                self.assertEqual(D.current_of(self.aspm[domain], rec, jv), rec["trace_position"], rec["step_id"])
                for past in (rec["past_trace"], []):
                    d = D.decide(self.aspm[domain], rec, jv, past)
                    self.assertEqual(d["allowed"], rec["action_allowed"], rec["step_id"])
                    self.assertAlmostEqual(d["margin"], rec["margin"], places=9)
                n += 1
                blocked += not rec["action_allowed"]
        self.assertEqual(n, 4 * SAMPLE)
        self.assertGreater(blocked, 0)

    def test_saved_changes_reproduce(self):
        """Every 'alone' predicate in output/p8_changes.jsonl flips its saved record's decision on its own."""
        if not os.path.exists(D.CHANGES_JSONL):
            self.skipTest("run state_tracker.decide_again first")
        with open(D.CHANGES_JSONL, encoding="utf-8") as f:
            changes = {r["step_id"]: r for r in map(json.loads, f)}
        seen = 0
        for run, domain in paths.RUN_DOMAINS:
            for rec in read_steps(run, domain):
                ch = changes.get(rec["step_id"])
                if not ch or not ch["a"]["change"]:
                    continue
                jv = D.judge_values(rec)
                for n in ch["a"]["alone_flips"]:
                    v = D.NAME_VALUE[ch["a"]["values"][n]["tracker"]]
                    d = D.decide(self.aspm[domain], rec, dict(jv, **{n: v}))
                    self.assertNotEqual(d["allowed"], rec["action_allowed"], (rec["step_id"], n))
                    seen += 1
        self.assertGreater(seen, 0)


class TestReview(unittest.TestCase):
    def test_load_review(self):
        rv = D.load_review()
        self.assertEqual(len(rv), 266)
        self.assertTrue(all(x["correct"] in (True, False) for x in rv.values()))
        self.assertEqual(sum(x["tracker_ok"] for x in rv.values()), 263)    # Part 7 result
        self.assertEqual(sum(x["judge_ok"] for x in rv.values()), 52)


if __name__ == "__main__":
    unittest.main()
