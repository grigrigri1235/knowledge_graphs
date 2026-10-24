"""Tests for state_tracker/replay.py (Part 6). Standard library only, no LLM calls.

Run from predicate_correctness/:  python3 -B -m unittest tests.test_replay -v

The states are built from hand-made conversations (τ-bench's tool code on a copy of the data, as in
tests/test_lookup_format.py). The judge values in the hand-made records are made up for the test.
"""
from __future__ import annotations

import json
import os
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_tracker import paths  # noqa: E402
from state_tracker import lookup_format as L  # noqa: E402
from state_tracker import replay as R  # noqa: E402
from state_tracker import state as S  # noqa: E402
from tests.test_lookup_format import _conv  # noqa: E402


def _rec(domain, action, kwargs, judge, history, allowed=True):
    return {"step_id": "t/x/task0/trial0/step0/attempt1", "run": "t", "domain": domain, "task": 0, "trial": 0,
            "exec_step": 0, "attempt": 1, "episode_line": 0, "history_len": len(history), "action": action,
            "kwargs": kwargs, "judge": judge, "action_allowed": allowed, "executed": allowed, "cap_override": False,
            "judge_history_cut": False, "circuit": [], "violated_rules": [], "margin": 0.0, "action_text": action}


class TestCompare(unittest.TestCase):
    def test_classes(self):
        self.assertEqual(R.compare(True, True), "agree_true")
        self.assertEqual(R.compare(False, False), "agree_false")
        self.assertEqual(R.compare(True, False), "judge_true_tracker_false")
        self.assertEqual(R.compare(False, True), "judge_false_tracker_true")
        self.assertEqual(R.compare(None, True), "judge_unknown")
        self.assertEqual(R.compare(False, None), "tracker_unknown")
        self.assertEqual(R.compare(None, None), "both_unknown")
        self.assertNotIn("both_unknown", R.DISAGREE)
        self.assertEqual(set(R.CLASSES), set(R.DISAGREE) | {"agree_true", "agree_false", "both_unknown"})


class TestReplayOneValue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lk = L.load_lookups("retail")
        db = S.load_db("retail")
        cls.order = next(o for o in db["orders"].values() if o["status"] == "pending")
        user = db["users"][cls.order["user_id"]]
        cls.hist = _conv("retail", [
            ("find_user_id_by_email", {"email": user["email"]}),
            ("get_order_details", {"order_id": cls.order["order_id"]}),
        ])
        cls.state = S.build_state(cls.hist, domain="retail")

    def test_recording_state_records_reads(self):
        rs = R.RecordingState(self.state)
        v = L.evaluate(self.lk["order_status_checked_pending"], rs, args={"order_id": self.order["order_id"]})
        self.assertIs(v, True)
        self.assertEqual(rs.reads, [{"read": "shown", "kind": "order", "id": self.order["order_id"], "found": True}])
        rs = R.RecordingState(self.state)
        L.evaluate(self.lk["user_authenticated"], rs, args={})
        self.assertEqual(rs.reads[0]["read"], "events")
        self.assertEqual(rs.reads[0]["indices"], [0])

    def test_agreement_has_no_disagreement_row(self):
        rec = _rec("retail", "cancel_pending_order", {"order_id": self.order["order_id"], "reason": "no longer needed"},
                   {"order_status_checked_pending": {"value": True, "evidence": "e"}}, self.hist)
        row, dis = R.one_value(rec, "order_status_checked_pending", "database fact",
                               self.lk["order_status_checked_pending"], self.state, False, False, "desc")
        self.assertEqual(row["agreement"], "agree_true")
        self.assertIsNone(dis)
        self.assertIs(row["tracker_value"], True)
        self.assertEqual(row["judge_evidence"], "e")
        self.assertIsNone(row["unknown_reason"])

    def test_disagreement_row_has_the_objects_and_events(self):
        rec = _rec("retail", "cancel_pending_order", {"order_id": self.order["order_id"], "reason": "no longer needed"},
                   {"order_status_checked_pending": {"value": False, "evidence": "not shown"},
                    "user_authenticated": {"value": False, "evidence": "no login"}}, self.hist, allowed=False)
        row, dis = R.one_value(rec, "order_status_checked_pending", "database fact",
                               self.lk["order_status_checked_pending"], self.state, True, True, "desc")
        self.assertEqual(row["agreement"], "judge_false_tracker_true")
        obj = dis["context"]["objects"][0]
        self.assertEqual((obj["kind"], obj["id"]), ("order", self.order["order_id"]))
        self.assertEqual(obj["db"]["status"], "pending")
        self.assertEqual(obj["shown"]["status"], "pending")
        self.assertEqual(obj["shown_by"]["tool"], "get_order_details")
        self.assertEqual(dis["description"], "desc")
        self.assertTrue(dis["blocked"])
        json.dumps(dis)                                       # the row can be saved
        row, dis = R.one_value(rec, "user_authenticated", "event", self.lk["user_authenticated"], self.state,
                               True, True, "desc")
        self.assertEqual(row["agreement"], "judge_false_tracker_true")
        ev = dis["context"]["events"][0]
        self.assertEqual(ev["returned"], [0])
        self.assertEqual(ev["events"][0]["tool"], "find_user_id_by_email")

    def test_not_shown_object_is_false_with_db_value_kept(self):
        other = next(o for o in S.load_db("retail")["orders"].values()
                     if o["status"] == "pending" and o["order_id"] != self.order["order_id"])
        rec = _rec("retail", "cancel_pending_order", {"order_id": other["order_id"], "reason": "x"},
                   {"order_status_checked_pending": {"value": True, "evidence": "e"}}, self.hist)
        row, dis = R.one_value(rec, "order_status_checked_pending", "database fact",
                               self.lk["order_status_checked_pending"], self.state, False, False, "desc")
        self.assertEqual(row["agreement"], "judge_true_tracker_false")
        self.assertIsNotNone(row["tracker_missing"])
        obj = dis["context"]["objects"][0]
        self.assertIsNone(obj["shown"])
        self.assertEqual(obj["db"]["status"], "pending")
        self.assertEqual(dis["group"], "an object the lookup needs was not shown (if_missing)")

    def test_tracker_unknown_has_a_reason(self):
        rec = _rec("retail", "modify_pending_order_items", {"order_id": "#W0"},
                   {"payment_method_is_gift_card": {"value": False, "evidence": "e"}}, self.hist)
        row, _ = R.one_value(rec, "payment_method_is_gift_card", "argument", self.lk["payment_method_is_gift_card"],
                             self.state, False, False, "desc")
        self.assertIsNone(row["tracker_value"])
        self.assertEqual(row["agreement"], "tracker_unknown")
        self.assertIn("payment_method_id", row["unknown_reason"])

    def test_judge_view_and_login_group(self):
        long_msg = {"role": "user", "content": "x" * (R.JUDGE_HISTORY_CHARS + 10)}
        hist = list(self.hist) + [long_msg]            # pushes the login output out of the last 24,000 characters
        self.assertEqual(set(R.judge_view(self.hist).values()), {True})
        view = R.judge_view(hist)
        self.assertEqual(set(view.values()), {False})
        rec = _rec("retail", "cancel_pending_order", {"order_id": self.order["order_id"], "reason": "x"},
                   {"user_authenticated": {"value": False, "evidence": "no login"}}, hist, allowed=False)
        rec["history"], rec["judge_history_cut"] = hist, True
        row, dis = R.one_value(rec, "user_authenticated", "event", self.lk["user_authenticated"], self.state,
                               True, True, "desc")
        self.assertIs(dis["context"]["events"][0]["events"][0]["in_judge_view"], False)
        self.assertEqual(dis["group"], R.GROUPS[0])

    def test_circuit_predicates_follow_the_rules(self):
        with open(paths.rule_set_path("retail"), encoding="utf-8") as f:
            rs = json.load(f)
        rules = {r["id"]: r for r in rs["rules"]}
        rid = next(r["id"] for r in rs["rules"] if "gift_card_balance_covers_price_difference" in r["logic"])
        preds = R.circuit_predicates({"circuit": [rid]}, rules, rs["predicates"])
        self.assertIn("gift_card_balance_covers_price_difference", preds)
        self.assertIn("payment_method_is_gift_card", preds)


if __name__ == "__main__":
    unittest.main()
