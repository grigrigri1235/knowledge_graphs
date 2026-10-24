"""Tests for state_tracker/p7_sample.py (Part 7, sample and review sheet). Standard library only, no LLM calls.

Run from predicate_correctness/:  python3 -B -m unittest tests.test_p7_sample -v

The sample tests use made-up rows. The last test class reads the written outputs (if they exist) and checks that the
sheet is blind and matches the key.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_tracker import p7_sample as P  # noqa: E402


def _rows():
    rows = []
    classes = (["agree_true"] * 300 + ["agree_false"] * 100 + ["judge_true_tracker_false"] * 20 +
               ["judge_false_tracker_true"] * 20 + ["judge_unknown"] * 20 + ["tracker_unknown"] * 2)
    for i, c in enumerate(classes):
        rows.append({"step_id": f"r/d/task{i}/trial0/step1/attempt1", "predicate": f"p{i % 3}", "agreement": c,
                     "blocked": (i % 4 == 0), "tracker_value": True, "judge_value": False})
    return rows


class TestSample(unittest.TestCase):
    def test_strata(self):
        rows = _rows()
        s = P.draw_sample(rows, seed=1, n_other=10, n_agree=50)
        dis_blocked = [r for r in rows if r["agreement"] in P.DISAGREE and r["blocked"]]
        got = [r for r, st in s if st == P.STRATA[0]]
        self.assertEqual(sorted(map(P.row_key, got)), sorted(map(P.row_key, dis_blocked)))   # all of them
        self.assertEqual(sum(st == P.STRATA[1] for _, st in s), 10)
        self.assertEqual(sum(st == P.STRATA[2] for _, st in s), 50)
        for r, st in s:
            if st == P.STRATA[1]:
                self.assertTrue(r["agreement"] in P.DISAGREE and not r["blocked"])
            if st == P.STRATA[2]:
                self.assertIn(r["agreement"], ("agree_true", "agree_false"))
        self.assertEqual(len({P.row_key(r) for r, _ in s}), len(s))                          # no repeats

    def test_fixed_seed(self):
        rows = _rows()
        a = [P.row_key(r) for r, _ in P.draw_sample(rows, seed=5)]
        b = [P.row_key(r) for r, _ in P.draw_sample(list(reversed(rows)), seed=5)]   # input order does not matter
        self.assertEqual(a, b)
        self.assertNotEqual(a, [P.row_key(r) for r, _ in P.draw_sample(rows, seed=6)])

    def test_blind(self):
        s = P.draw_sample(_rows(), seed=1)
        e = P.shuffle_and_blind(s, seed=1)
        self.assertEqual([x["id"] for x in e], [f"P7-{i:03d}" for i in range(1, len(s) + 1)])
        for x in e:
            self.assertEqual({x["A"], x["B"]}, {"tracker", "judge"})
        n_a = sum(x["A"] == "tracker" for x in e)
        self.assertTrue(0 < n_a < len(e))
        self.assertEqual(e, P.shuffle_and_blind(s, seed=1))


class TestAnswers(unittest.TestCase):
    MD = ("# x\n\n### P7-001\n\ntext\n\n**Answer** (A right / B right / both wrong / both right / predicate unclear): "
          "B right\n\n**Note:** the order was shown\n\n---\n\n### P7-002\n\n**Answer** (A right / B right / both "
          "wrong / both right / predicate unclear): \n\n**Note:** \n\n### P7-003\n\n**Answer** (A right / B right / "
          "both wrong / both right / predicate unclear): `predicate unclear`.\n\n**Note:** x\n\n### P7-004\n\n"
          "**Answer** (A right / B right / both wrong / both right / predicate unclear): maybe\n")

    def test_read(self):
        a = P.read_answers(self.MD)
        self.assertEqual(a["P7-001"], {"answer": "B right", "note": "the order was shown", "error": None})
        self.assertIsNone(a["P7-002"]["answer"])
        self.assertIsNone(a["P7-002"]["error"])
        self.assertEqual(a["P7-003"]["answer"], "predicate unclear")
        self.assertIsNotNone(a["P7-004"]["error"])

    def test_normalize(self):
        self.assertEqual(P.normalize_answer(" A RIGHT "), "A right")
        self.assertIsNone(P.normalize_answer(""))
        with self.assertRaises(ValueError):
            P.normalize_answer("A")


class TestExcerpt(unittest.TestCase):
    def test_select(self):
        hist = [{"role": "system", "content": "policy"},
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": None,
                 "tool_calls": [{"id": "c1", "function": {"name": "get_order_details",
                                                          "arguments": "{\"order_id\": \"#W1\"}"}}]},
                {"role": "tool", "tool_call_id": "c1", "name": "get_order_details", "content": "{...}"},
                {"role": "user", "content": "ok"},
                {"role": "assistant", "content": "a"},
                {"role": "user", "content": "b"},
                {"role": "assistant", "content": "c"},
                {"role": "user", "content": "d"},
                {"role": "assistant", "content": "e"}]
        idx = P.select_messages(hist, {"#W1"}, set(), last_n=2)
        self.assertEqual(idx, [1, 2, 3, 8, 9])            # first user message, the call and its output, last 2
        self.assertNotIn(0, P.select_messages(hist, set(), {0}, last_n=2))   # never the policy
        text = P.render_excerpt([P.message_view(i, hist[i]) for i in idx], len(hist))
        self.assertIn("[messages #4-#7 left out]", text)
        self.assertIn("calls: get_order_details", text)

    def test_ids(self):
        args = {"order_id": "#W1", "item_ids": ["11", "12"], "reason": "no longer needed",
                "flights": [{"flight_number": "HAT001", "date": "2024-05-20"}]}
        self.assertEqual(P._ids_in(args), {"#W1", "11", "12", "HAT001"})

    def test_flight_trim(self):
        db = {"flight_number": "HAT001", "dates": {"2024-05-20": {"status": "available"},
                                                   "2024-05-21": {"status": "available"}}}
        out = P._trim_flight(db, {"dates": {}}, {"2024-05-20"})
        self.assertEqual(list(out["dates"]), ["2024-05-20"])
        self.assertIn("dates_left_out", out)


@unittest.skipUnless(os.path.exists(P.SHEET_MD) and os.path.exists(P.KEY_JSON), "outputs not written yet")
class TestWrittenOutputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(P.SHEET_MD, encoding="utf-8") as f:
            cls.md = f.read()
        with open(P.KEY_JSON, encoding="utf-8") as f:
            cls.key = json.load(f)
        with open(P.ITEMS_JSON, encoding="utf-8") as f:
            cls.items = json.load(f)["items"]

    def test_same_ids(self):
        ids_md = re.findall(r"^### (P7-\d{3})$", self.md, re.M)
        self.assertEqual(ids_md, [x["id"] for x in self.key["items"]])
        self.assertEqual(ids_md, [x["id"] for x in self.items])

    def test_values_match_key(self):
        name = {True: "true", False: "false", None: "unknown"}
        for it, k in zip(self.items, self.key["items"]):
            self.assertEqual(it["value_A"]["value"], name[k[f"{k['A']}_value"]])
            self.assertEqual(it["value_B"]["value"], name[k[f"{k['B']}_value"]])
            self.assertEqual(it["step"], k["step_id"])

    def test_blind(self):
        body = self.md[self.md.index("## Items"):]
        for word in ("judge", "tracker", "disagree", "agreement", "p7_key"):
            self.assertNotIn(word, body.lower(), word)
        for it in self.items:
            text = json.dumps({k: v for k, v in it.items() if k not in ("excerpt",)}).lower()
            for word in ("judge", "tracker", "disagree"):
                self.assertNotIn(word, text, f"{it['id']} {word}")

    def test_sample_rules(self):
        st = [x["stratum"] for x in self.key["items"]]
        self.assertEqual(st.count(P.STRATA[0]), self.key["population"][P.STRATA[0]])   # all blocked disagreements
        self.assertEqual(st.count(P.STRATA[2]), P.N_AGREE)
        self.assertEqual(self.key["seed"], P.SEED)
        self.assertIn(f"Seed: {P.SEED}", self.md)

    def test_every_item_has_answer_line(self):
        a = P.read_answers(self.md)
        self.assertEqual(len(a), len(self.items))
        self.assertTrue(all(v["error"] is None for v in a.values()))


if __name__ == "__main__":
    unittest.main()
