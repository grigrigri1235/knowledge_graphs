"""Tests for state_tracker/type_counts.py (Part 3, subtask 3), on hand-made step records. Standard library only.

Run from predicate_correctness/:  python3 -B -m unittest tests.test_type_counts -v
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_tracker import type_counts as tc  # noqa: E402

TYPES = {
    "user_authenticated": {"type": "event", "reason": "x"},
    "payment_method_is_gift_card": {"type": "argument", "reason": "x"},
    "gift_card_balance_covers_order_total": {"type": "database fact", "reason": "x"},
    "user_explicitly_confirmed_pending_action": {"type": "conversation", "reason": "x"},
}


def rec(allowed, judge, violated=()):
    return {"action_allowed": allowed, "executed": False,
            "judge": {k: {"value": v, "evidence": ""} for k, v in judge.items()},
            "violated_rules": [{"rule_id": str(i), "description": "", "logic": lg} for i, lg in enumerate(violated)]}


class TestTypeCounts(unittest.TestCase):
    def test_logic_predicates_token_match(self):
        got = tc.logic_predicates("act IMPLIES NOT payment_method_is_gift_card OR gift_card_balance_covers_order_total",
                                  TYPES)
        self.assertEqual(got, {"payment_method_is_gift_card", "gift_card_balance_covers_order_total"})
        self.assertEqual(tc.logic_predicates("act IMPLIES user_authenticated_x", TYPES), set())

    def test_block_with_code_and_conversation_rules(self):
        r = rec(False, {"user_authenticated": True, "user_explicitly_confirmed_pending_action": False,
                        "payment_method_is_gift_card": True, "gift_card_balance_covers_order_total": None},
                ["act IMPLIES user_explicitly_confirmed_pending_action",
                 "act IMPLIES NOT payment_method_is_gift_card OR gift_card_balance_covers_order_total"])
        info = tc.step_info(r, TYPES)
        self.assertTrue(info["blocked"])
        self.assertTrue(info["any_code"])
        self.assertFalse(info["all_rules_code"])          # the conversation rule has no code-type predicate
        self.assertTrue(info["judged_code"])
        c = tc.count_run([r], TYPES)
        self.assertEqual(c["blocked"], 1)
        self.assertEqual(c["any_code"], 1)
        self.assertEqual(c["causing"][("argument", "true")], 1)
        self.assertEqual(c["causing"][("database fact", "unknown")], 1)
        self.assertEqual(c["causing"][("conversation", "false")], 1)
        self.assertEqual(c["causing"][("event", "true")], 0)   # judged, but not in a violated rule
        self.assertEqual(c["values"][("event", "true")], 1)
        self.assertEqual(sum(c["values"].values()), 4)
        self.assertFalse(c["problems"])

    def test_only_conversation_block(self):
        r = rec(False, {"user_authenticated": True, "user_explicitly_confirmed_pending_action": False},
                ["act IMPLIES user_explicitly_confirmed_pending_action"])
        c = tc.count_run([r], TYPES)
        self.assertEqual((c["any_code"], c["all_rules_code"], c["judged_code"]), (0, 0, 1))

    def test_allowed_steps_and_problems(self):
        ok = rec(True, {"user_authenticated": True})
        bad = rec(True, {"user_authenticated": True}, ["act IMPLIES user_authenticated"])
        unknown_pred = rec(True, {"made_up": True})
        c = tc.count_run([ok, bad, unknown_pred], TYPES)
        self.assertEqual(c["blocked"], 0)
        self.assertEqual(c["problems"]["allowed step with violated rules"], 1)
        self.assertEqual(c["problems"]["judged predicate has no type"], 1)


if __name__ == "__main__":
    unittest.main()
