"""Tracker v4: scoring.v4_cases asks a K3 conversation case on the guard's own window (reminder_candidates).

No LLM call, no network (fake backend, memory store). Run from predicate_correctness/:
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v4_cases_window -v
"""
from __future__ import annotations

import os
import sys
import unittest

PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from scoring import v4_cases as C                                  # noqa: E402

REMIND_OTHER = "Is the Desk Fan the only item you want to exchange from order #W1000001?"
CONFIRM = "Order #W1000002: Reading Lamp blue -> red, no price difference. Shall I proceed?"
REMIND_RIGHT = "For order #W1000002, is the Reading Lamp the only item you want to exchange?"


def case(conv, expect="no", **kw):
    c = {"id": "T-1", "kind": "t", "A": conv[1]["text"], "items_action": "exchanged", "verb": "exchange",
         "order_id": "#W1000002", "conversation": conv, "expect": expect, "_qid": "K3"}
    c.update(kw)
    return c


def run(c, policy):
    C.OE._Q().block_network()
    doc = C.OE._QV4().load_questions_v4()
    hook, _, exp = C.make_case_hook("fake", policy, doc, None, C.OE.CASES_STORE)
    return C.run_cases({"K3": [c]}, hook, doc, "test", exp)[0]


class TestK3Window(unittest.TestCase):
    def test_reminder_before_the_order_id_is_left_out(self):
        conv = [{"role": "user", "text": "I want to exchange things."}, {"role": "agent", "text": REMIND_OTHER},
                {"role": "user", "text": "No, it is order #W1000002, the Reading Lamp."},
                {"role": "agent", "text": CONFIRM}, {"role": "user", "text": "Yes."}]
        self.assertEqual(C.window_candidates("K3", case(conv)), [CONFIRM])

    def test_reminder_after_the_order_id_is_kept_newest_last(self):
        conv = [{"role": "user", "text": "Exchange from order #W1000002 please."},
                {"role": "agent", "text": REMIND_RIGHT}, {"role": "user", "text": "Yes, only that."},
                {"role": "agent", "text": CONFIRM}, {"role": "user", "text": "Yes."}]
        self.assertEqual(C.window_candidates("K3", case(conv)), [REMIND_RIGHT, CONFIRM])

    def test_no_candidate_is_no_without_a_call(self):
        conv = [{"role": "user", "text": "Hi."}, {"role": "agent", "text": REMIND_OTHER},
                {"role": "user", "text": "Thanks."}]
        r = run(case(conv), "yes")                       # a fake yes on any call would make it yes
        self.assertEqual((r["final"], r["asks"], r["window"], r["error"]), ("no", [], 0, None))
        self.assertTrue(r["right"])

    def test_window_messages_are_asked(self):
        conv = [{"role": "user", "text": "Hi."}, {"role": "agent", "text": REMIND_OTHER},
                {"role": "user", "text": "It is #W1000002."}, {"role": "agent", "text": CONFIRM},
                {"role": "user", "text": "Yes."}]
        r = run(case(conv), "yes")
        self.assertEqual((r["final"], len(r["asks"]), r["window"]), ("yes", 1, 1))

    def test_case_without_conversation_is_asked_as_given(self):
        self.assertIsNone(C.window_candidates("K3", {"A": REMIND_RIGHT, "order_id": "#W1000002"}))
        self.assertIsNone(C.window_candidates("K13", {"conversation": [{"role": "user", "text": "x"}]}))


if __name__ == "__main__":
    unittest.main()
