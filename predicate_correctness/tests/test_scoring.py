"""Tests for scoring/ (Part 7, subtasks 4 and 5): gold loader, gold mapping, three-valued logic, accuracy.

Run from predicate_correctness/:  python3 -B -m unittest tests.test_scoring -v
Standard library only. No LLM calls.
"""
from __future__ import annotations

import json
import os
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scoring import gold_loader as G  # noqa: E402
from scoring import p7_results as R   # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")


def _tc(i, name, args):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": f"c{i}", "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)}}]}


def _out(i, name, content):
    return {"role": "tool", "tool_call_id": f"c{i}", "name": name, "content": content}


def _load(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestThreeValued(unittest.TestCase):

    def test_and3(self):
        self.assertIs(R.and3([True, True]), True)
        self.assertIs(R.and3([True, None]), None)
        self.assertIs(R.and3([None, False]), False)

    def test_not3_and_combine(self):
        self.assertIs(R.not3(None), None)
        self.assertIs(R.combine("not", [True]), False)
        self.assertIs(R.combine("same", [None]), None)
        with self.assertRaises(ValueError):
            R.combine("or", [True])

    def test_wilson(self):
        lo, hi = R.wilson(0, 50)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.0713, places=3)
        lo, hi = R.wilson(50, 50)
        self.assertAlmostEqual(lo, 0.9287, places=3)


class TestScoring(unittest.TestCase):

    def _key(self):
        return {"items": [
            {"id": "X1", "A": "tracker", "B": "judge", "tracker_value": True, "judge_value": False},
            {"id": "X2", "A": "judge", "B": "tracker", "tracker_value": False, "judge_value": None},
        ]}

    def test_answers_match_key(self):
        ok = {"X1": {"answer": "A right", "correct_value": "true"},
              "X2": {"answer": "B right", "correct_value": "false"}}
        self.assertEqual(R.check_answers_match_key(self._key(), ok), [])
        bad = {"X1": {"answer": "B right", "correct_value": "true"},
               "X2": {"answer": "B right", "correct_value": "false"}}
        self.assertEqual(len(R.check_answers_match_key(self._key(), bad)), 1)

    def test_tally_and_weighted(self):
        items = [{"group": "agreement", "tracker_ok": True, "judge_ok": True},
                 {"group": "disagreement, other", "tracker_ok": True, "judge_ok": False},
                 {"group": "disagreement, blocked step", "tracker_ok": False, "judge_ok": True}]
        c = R.tally(items)
        self.assertEqual((c["n"], c["tracker_ok"], c["judge_ok"], c["both_wrong"]), (3, 2, 2, 0))
        ws = R.weighted(items, {"agreement": 8, "disagreement, other": 1, "disagreement, blocked step": 1})
        self.assertAlmostEqual(ws["tracker"][0], 0.9)
        self.assertAlmostEqual(ws["judge"][0], 0.9)


class TestGoldLoader(unittest.TestCase):

    def test_load_leaves_no_stub_and_no_bytecode(self):
        for d in ("airline", "retail"):
            preds = G.load_gold(d)
            self.assertIn("user_authenticated" if d == "retail" else "flights_changed", preds)
        self.assertFalse([m for m in sys.modules if m == "agent" or m.startswith("agent.")])
        self.assertFalse(os.path.exists(os.path.join(G.GOLD_DIR, "__pycache__")))

    def test_mapping_names_exist(self):
        for d in ("airline", "retail"):
            preds = G.load_gold(d)
            for ours, (how, names, why) in R.GOLD_MAP[d].items():
                self.assertIn(how, ("same", "and", "not"))
                self.assertTrue(why)
                for n in names:
                    self.assertIn(n, preds, f"{d}: {ours} -> {n}")

    def test_gold_on_hand_made_history(self):
        retail = G.load_gold("retail")
        hist = [{"role": "system", "content": "policy"}, {"role": "user", "content": "hi"},
                _tc(1, "find_user_id_by_email", {"email": "a@b.c"}), _out(1, "find_user_id_by_email", "a_1")]
        call = G.gold_call("cancel_pending_order", {"order_id": "#W1", "reason": "no longer needed"})
        self.assertIs(retail["user_authenticated"](call, hist, {}), True)
        self.assertIs(retail["user_authenticated"](call, hist[:2], {}), False)
        self.assertIs(retail["cancel_reason_is_valid"](call, hist, {}), True)
        self.assertIs(retail["order_status_is_pending"](call, hist, {}), None)      # order never shown

    def test_gold_effective_cabin(self):
        airline = G.load_gold("airline")
        res = {"reservation_id": "R1", "user_id": "u", "cabin": "basic_economy", "flights": [], "passengers": []}
        hist = [_tc(1, "get_reservation_details", {"reservation_id": "R1"}), _out(1, "x", json.dumps(res)),
                _tc(2, "update_reservation_flights", {"reservation_id": "R1", "cabin": "economy", "flights": []}),
                _out(2, "x", json.dumps(res))]
        call = G.gold_call("update_reservation_flights", {"reservation_id": "R1", "cabin": "economy", "flights": []})
        self.assertIs(airline["reservation_is_basic_economy"](call, hist[:2], G.GOLD_CONFIG["airline"]), True)
        self.assertIs(airline["reservation_is_basic_economy"](call, hist, G.GOLD_CONFIG["airline"]), False)


@unittest.skipUnless(os.path.exists(os.path.join(OUT, "p7_scored_items.jsonl")), "run scoring.p7_results first")
class TestWrittenOutputs(unittest.TestCase):

    def test_scored_items(self):
        rows = [json.loads(line) for line in _load(os.path.join(OUT, "p7_scored_items.jsonl")).splitlines()]
        key = json.loads(_load(os.path.join(OUT, "p7_key.json")))
        self.assertEqual(len(rows), len(key["items"]))
        for r in rows:
            self.assertEqual(r["tracker_ok"], r["tracker"] == r["correct"])
            self.assertEqual(r["judge_ok"], r["judge"] == r["correct"])
            self.assertIn(r["predicate"], R.GOLD_MAP[r["domain"]])
            self.assertIn(r["gold"], ("true", "false", "unknown"))

    def test_results_md_has_sections(self):
        text = _load(os.path.join(OUT, "p7_review_results.md"))
        for s in ("person review is pending", "## Accuracy by sample group", "## Disagreements by type",
                  "## Main reasons for errors", "## Gold check", "### Mapping"):
            self.assertIn(s, text)


if __name__ == "__main__":
    unittest.main()
