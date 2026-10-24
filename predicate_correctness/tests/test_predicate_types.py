"""Tests for output/predicate_types.json and state_tracker/predicate_types.py (Part 3). Standard library only.

Run from predicate_correctness/:  python3 -B -m unittest tests.test_predicate_types -v
"""
from __future__ import annotations

import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_tracker import predicate_types as pt  # noqa: E402


class TestTypesFile(unittest.TestCase):
    def setUp(self):
        self.types = pt.load_types()

    def test_every_frozen_predicate_has_one_valid_type(self):
        self.assertEqual(pt.check_types(self.types), [])
        self.assertEqual(len(self.types["airline"]), 42)
        self.assertEqual(len(self.types["retail"]), 24)

    def test_check_finds_problems(self):
        bad = copy.deepcopy(self.types)
        del bad["retail"]["user_authenticated"]
        bad["airline"]["booking_has_at_most_five_passengers"]["type"] = "fact"
        bad["airline"]["made_up_predicate"] = {"type": "event", "reason": "x"}
        problems = pt.check_types(bad)
        self.assertTrue(any("user_authenticated has no type" in p for p in problems))
        self.assertTrue(any("'fact' not in" in p for p in problems))
        self.assertTrue(any("made_up_predicate is not a frozen predicate" in p for p in problems))

    def test_overview_examples_that_are_not_borderline(self):
        # overview.md examples; user_chose_pending_payment_method is a documented deviation (see predicate_types.md)
        r = self.types["retail"]
        self.assertEqual(r["cancellation_reason_is_allowed"]["type"], "argument")
        self.assertEqual(r["order_status_checked_pending"]["type"], "database fact")
        self.assertEqual(r["gift_card_balance_covers_order_total"]["type"], "database fact")
        self.assertEqual(r["user_authenticated"]["type"], "event")
        self.assertEqual(r["user_explicitly_confirmed_pending_action"]["type"], "conversation")

    def test_review_status_is_not_a_domain(self):
        self.assertEqual(sorted(self.types), ["airline", "retail"])
        self.assertIn("person review pending", pt.load_meta()["status"])

    def test_agent_review_covers_every_predicate(self):
        review = pt.load_agent_review()
        self.assertEqual(pt.check_agent_review(review, self.types), [])
        bad = copy.deepcopy(review)
        del bad["retail"]["user_authenticated"]
        bad["airline"]["booking_has_at_most_five_passengers"] = "maybe"
        problems = pt.check_agent_review(bad, self.types)
        self.assertEqual(len(problems), 2)

    def test_md_has_one_verdict_per_row(self):
        md = pt.render_md(self.types)
        rows = [ln for ln in md.splitlines() if ln.startswith("| ") and ln.split("|")[2].strip().startswith("`")
                and ln.split("|")[1].strip().isdigit()]
        self.assertEqual(len(rows), 66)
        self.assertTrue(all(ln.rstrip().split("|")[-2].strip().startswith(("agree", "change to")) for ln in rows))

    def test_rule_tools(self):
        tools = pt.rule_tools(pt.load_rule_set("retail"))
        self.assertEqual(tools["cancellation_reason_is_allowed"], ["cancel_pending_order"])
        self.assertIn("respond", tools["user_authenticated"])


if __name__ == "__main__":
    unittest.main()
