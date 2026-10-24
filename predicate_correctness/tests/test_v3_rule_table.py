"""Tests for state_tracker/v3/rule_table.py (tracker v3, part 2; pass mark P2.4). Standard library only, no LLM call.

Hand-made rules: one fact, OR, AND, NOT, an implication, the 6-fact shape; the smallest flip sets; the blocking
value (also a fact that blocks with both values); a rule that cannot hold; a fact that never matters; action
predicates are not facts; a rule in two circuits; a temporal rule (skipped). Every hand-made table is also checked
against TGR's own decision code (scoring.v3_p2_rule_table_check.check_table: mln.decide and the brute force).
Then the two frozen rule sets: rules by fact count, rule 25 of the airline set, one blocking value per pair, no rule
set name in rule_table.py (P2.3, with a planted-name check of the detector), and the written tables equal a fresh
build.

Run from predicate_correctness/:  python3 -B -m unittest tests.test_v3_rule_table -v
"""
from __future__ import annotations

import json
import os
import sys
import unittest

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from state_tracker.v3 import rule_table as RT                     # noqa: E402  (sets up the runner path)
from repro_core import ltlf                                       # noqa: E402  (runner copy)
from scoring.v3_p2_rule_table_check import RULE_TABLE_PY, check_table, generic_hits, generic_hits_text  # noqa: E402

ACTIONS = ("act", "other_act")


def make_rule_set(*rules, circuits=None):
    """rules: (id, action, condition), written as TGR writes them with flags a and b ("<action> IMPLIES (<cond>)")."""
    out_rules, preds, circ = [], {}, {}
    for rid, action, cond in rules:
        f = ltlf.parse(f"{action} IMPLIES ({cond})")
        for n in f.atoms:
            if n not in ACTIONS:
                preds[n] = {"name": n, "description": f"fact {n}", "source": []}
        out_rules.append({"id": rid, "action": action, "condition": cond, "description": f"rule {rid}",
                          "sentences": ["S1", "S9"], "logic": f.canonical(), "actions": [action], "model_id": f"R{rid}"})
        circ.setdefault(action, []).append(rid)
    return {"flags": {"a": True, "b": True, "label": "A+B"}, "action_names": list(ACTIONS), "actions": {},
            "predicates": preds, "rules": out_rules, "circuits": circuits or circ,
            "sentences": [{"id": "S1", "text": "Sentence one.", "heading": "H"},
                          {"id": "S2", "text": "Sentence two.", "heading": "H"}],
            "dispositions": [{"sentence": "S1", "disposition": "rule", "rule_ids": [r[0] for r in rules]},
                             {"sentence": "S2", "disposition": "fact", "rule_ids": []}]}


def one(cond):
    """(rule set, table, the rule's entry) for one rule `act IMPLIES (cond)`."""
    rs = make_rule_set(("1", "act", cond))
    t = RT.build_table(rs)
    return rs, t, (t["rules"][0] if t["rules"] else None)


def row(entry, action="act", **values):
    found = [r for r in entry["rows"] if r["action"] == action and r["values"] == values]
    assert len(found) == 1, (values, found)
    return found[0]


class TestRuleShapes(unittest.TestCase):

    def assert_decide_agrees(self, rs, t):
        c = check_table(t, rs)
        self.assertEqual(c["failures"], [])
        self.assertEqual(c["structure_errors"], [])
        self.assertEqual(c["blocking_errors"], [])
        self.assertEqual(c["polarity_disagreements"], [])
        self.assertEqual(c["block_pass"], c["failing_rows"])
        self.assertEqual(c["flip_allow_pass"], c["flip_sets"])
        self.assertEqual(c["bf_unlisted_pass"], c["bf_unlisted"])
        self.assertEqual(c["hold_allow_pass"], c["hold_rows"])
        return c

    def test_one_fact(self):
        rs, t, e = one("p")
        self.assertEqual((e["facts"], e["n_facts"], e["n_combinations"], e["n_rows"]), (["p"], 1, 2, 2))
        self.assertEqual(row(e, p=False)["flip_sets"], [["p"]])
        self.assertFalse(row(e, p=False)["holds"])
        self.assertEqual(row(e, p=False)["tipping_facts"], ["p"])
        self.assertTrue(row(e, p=True)["holds"])
        self.assertEqual(row(e, p=True)["flip_sets"], [])
        self.assertEqual(e["blocking_values"], {"p": [False]})
        self.assertEqual(e["polarity"], {"p": "positive"})
        self.assertEqual(e["cannot_hold"], [])
        self.assert_decide_agrees(rs, t)

    def test_or(self):
        rs, t, e = one("p OR q")
        self.assertEqual(row(e, p=False, q=False)["flip_sets"], [["p"], ["q"]])
        self.assertEqual(sum(not r["holds"] for r in e["rows"]), 1)
        self.assertEqual(e["blocking_values"], {"p": [False], "q": [False]})
        self.assert_decide_agrees(rs, t)

    def test_and(self):
        rs, t, e = one("p AND q")
        self.assertEqual(row(e, p=False, q=False)["flip_sets"], [["p", "q"]])
        self.assertEqual(row(e, p=False, q=True)["flip_sets"], [["p"]])
        self.assertEqual(row(e, p=True, q=False)["flip_sets"], [["q"]])
        self.assertTrue(row(e, p=True, q=True)["holds"])
        self.assert_decide_agrees(rs, t)

    def test_not(self):
        rs, t, e = one("NOT p")
        self.assertFalse(row(e, p=True)["holds"])
        self.assertEqual(row(e, p=True)["flip_sets"], [["p"]])
        self.assertTrue(row(e, p=False)["holds"])
        self.assertEqual(e["blocking_values"], {"p": [True]})
        self.assertEqual(e["polarity"], {"p": "negative"})
        self.assert_decide_agrees(rs, t)

    def test_implication(self):
        # the plan's example: NOT gift card OR balance covers; gift card true and covers false -> {covers} or {gift}
        for cond in ("NOT gift OR covers", "gift IMPLIES covers"):
            rs, t, e = one(cond)
            self.assertEqual(row(e, gift=True, covers=False)["flip_sets"], [["covers"], ["gift"]], cond)
            # rows in order (covers, gift) = FF, FT, TF, TT
            self.assertEqual([r["holds"] for r in e["rows"]], [True, False, True, True], cond)
            self.assertEqual(e["blocking_values"], {"covers": [False], "gift": [True]}, cond)
            self.assertEqual(e["polarity"], {"covers": "positive", "gift": "negative"}, cond)
            self.assert_decide_agrees(rs, t)

    def test_six_fact_shape(self):
        # airline rule 25's shape: a OR b OR c OR d AND e AND f
        rs, t, e = one("p1 OR p2 OR p3 OR p4 AND p5 AND p6")
        self.assertEqual((e["n_facts"], e["n_combinations"], e["n_rows"]), (6, 64, 64))
        self.assertEqual(sum(not r["holds"] for r in e["rows"]), 7)
        f = dict.fromkeys(e["facts"], False)
        self.assertEqual(row(e, **f)["flip_sets"], [["p1"], ["p2"], ["p3"], ["p4", "p5", "p6"]])
        self.assertEqual(row(e, **dict(f, p4=True))["flip_sets"], [["p1"], ["p2"], ["p3"], ["p5", "p6"]])
        self.assertEqual(row(e, **dict(f, p4=True, p6=True))["flip_sets"], [["p1"], ["p2"], ["p3"], ["p5"]])
        self.assertEqual(row(e, **f)["tipping_facts"], e["facts"])
        self.assertTrue(all(v == [False] for v in e["blocking_values"].values()))
        c = self.assert_decide_agrees(rs, t)
        self.assertEqual(c["bf_subsets"], 7 * 64)

    def test_smallest_sets_only(self):
        rs, t, e = one("(p AND q) OR r")
        # {p, r} and {q, r} also make it hold, but contain {r}: not listed
        self.assertEqual(row(e, p=False, q=False, r=False)["flip_sets"], [["r"], ["p", "q"]])
        self.assertEqual(row(e, p=True, q=False, r=False)["flip_sets"], [["q"], ["r"]])
        self.assert_decide_agrees(rs, t)

    def test_smallest_flip_sets_function(self):
        def test(v):
            return v["a"] and (v["b"] or v["c"])
        got = RT.smallest_flip_sets(test, ["a", "b", "c"], {"a": False, "b": False, "c": False})
        self.assertEqual(got, [["a", "b"], ["a", "c"]])
        self.assertEqual(RT.smallest_flip_sets(lambda v: False, ["a"], {"a": True}), [])

    def test_fact_blocks_with_both_values(self):
        rs, t, e = one("(p AND q) OR (NOT p AND r)")
        self.assertEqual(e["polarity"]["p"], "both")
        self.assertEqual(e["blocking_values"], {"p": [False, True], "q": [False], "r": [False]})
        self.assertEqual(row(e, p=True, q=False, r=False)["flip_sets"], [["q"], ["p", "r"]])
        self.assertEqual(row(e, p=False, q=False, r=False)["flip_sets"], [["r"], ["p", "q"]])
        self.assertEqual(t["counts"]["pairs_with_two_blocking_values"], [["1", "p"]])
        self.assertEqual(t["counts"]["pairs_with_both_polarities"], [["1", "p"]])
        self.assert_decide_agrees(rs, t)

    def test_cannot_hold(self):
        for cond, facts in (("p AND NOT p", ["p"]), ("FALSE", [])):
            rs, t, e = one(cond)
            self.assertEqual(e["facts"], facts, cond)
            self.assertEqual(e["cannot_hold"], ["act"], cond)
            self.assertTrue(all(not r["holds"] and r["flip_sets"] == [] for r in e["rows"]), cond)
            self.assertEqual(t["counts"]["cannot_hold_rules"], ["1"], cond)
            self.assert_decide_agrees(rs, t)

    def test_fact_that_never_matters(self):
        rs, t, e = one("p OR NOT p")
        self.assertTrue(all(r["holds"] for r in e["rows"]))
        self.assertEqual(e["blocking_values"], {"p": []})
        self.assertEqual(t["counts"]["pairs_that_never_block"], [["1", "p"]])
        self.assert_decide_agrees(rs, t)

    def test_action_predicates_are_not_facts(self):
        # another action predicate is false while `act` is pending (TGR._step: current = {a: a in matched})
        rs, t, e = one("NOT other_act OR p")
        self.assertEqual(e["facts"], ["p"])
        self.assertTrue(all(r["holds"] for r in e["rows"]))
        self.assert_decide_agrees(rs, t)

    def test_rule_in_two_circuits(self):
        rs = make_rule_set(("1", "act", "p"), circuits={"act": ["1"], "other_act": ["1"]})
        t = RT.build_table(rs)
        e = t["rules"][0]
        self.assertEqual(e["actions"], ["act", "other_act"])
        self.assertEqual(e["n_rows"], 4)
        self.assertEqual(row(e, "act", p=False)["flip_sets"], [["p"]])
        self.assertTrue(row(e, "other_act", p=False)["holds"])
        self.assert_decide_agrees(rs, t)

    def test_temporal_rule_is_skipped(self):
        rs, t, e = one("ALWAYS p")
        self.assertIsNone(e)
        self.assertEqual([s["id"] for s in t["skipped"]], ["1"])
        self.assertEqual(t["counts"]["skipped_rules"], 1)

    def test_fields_and_order(self):
        rs = make_rule_set(("10", "act", "p"), ("2", "act", "NOT q"), ("1", "other_act", "r"))
        t = RT.build_table(rs)
        self.assertEqual([e["id"] for e in t["rules"]], ["1", "2", "10"])   # numeric order, as TGR's circuits
        e = t["rules"][1]
        self.assertEqual(e["rule"], rs["rules"][1])
        self.assertEqual(e["cited_sentences"], [{"id": "S1", "text": "Sentence one.", "heading": "H"}])
        self.assertEqual(e["missing_sentence_ids"], ["S9"])
        self.assertEqual(e["dispositions"], [{"sentence": "S1", "disposition": "rule"}])
        self.assertEqual(t["counts"]["rules_by_fact_count"], {"1": 3})
        self.assertEqual(RT.render(t), RT.render(RT.build_table(rs)))
        self.assertEqual(json.loads(RT.render(t)), t)


class TestFrozenRuleSets(unittest.TestCase):
    """The two frozen TGR rule sets (from_shieldagent/rules/<domain>/rule_set.json)."""

    @classmethod
    def setUpClass(cls):
        cls.paths = RT.rule_set_paths()
        cls.tables = {n: RT.build_for_path(p) for n, p in cls.paths.items()}

    def test_counts_by_fact_count(self):
        self.assertEqual(sorted(self.tables), ["airline", "retail"])
        self.assertEqual(self.tables["retail"]["counts"]["rules_by_fact_count"], {"1": 60, "2": 4})
        self.assertEqual(self.tables["airline"]["counts"]["rules_by_fact_count"], {"1": 22, "2": 10, "3": 1, "6": 1})
        self.assertEqual(sum(t["counts"]["rules"] for t in self.tables.values()), 98)
        self.assertEqual(sum(t["counts"]["skipped_rules"] for t in self.tables.values()), 0)

    def test_airline_rule_25(self):
        e = next(x for x in self.tables["airline"]["rules"] if x["id"] == "25")
        self.assertEqual((e["n_facts"], e["n_rows"], e["actions"]), (6, 64, ["cancel_reservation"]))
        r = row(e, "cancel_reservation", **dict.fromkeys(e["facts"], False))
        self.assertEqual(sorted(len(s) for s in r["flip_sets"]), [1, 1, 1, 3])

    def test_one_blocking_value_per_pair(self):
        for n, t in self.tables.items():
            for e in t["rules"]:
                for f in e["facts"]:
                    self.assertEqual(len(e["blocking_values"][f]), 1, (n, e["id"], f))

    def test_generic_code(self):
        # P2.3: the detector finds a planted name (as a word, any case), and rule_table.py has none
        self.assertEqual(generic_hits_text("x = 'Cancel_Reservation'  # cancel_reservation", ["cancel_reservation"]),
                         ["cancel_reservation"])
        self.assertEqual(generic_hits_text("cancel_reservation_x", ["cancel_reservation"]), [])
        names = set(self.tables)
        for p in self.paths.values():
            with open(p, encoding="utf-8") as f:
                rs = json.load(f)
            names |= set(rs["action_names"]) | set(rs["predicates"])
        self.assertEqual(generic_hits(RULE_TABLE_PY, sorted(names)), [])

    def test_written_tables_equal_fresh_build(self):
        for n, table in self.tables.items():
            path = RT.table_path(n)
            if not os.path.exists(path):
                self.skipTest(f"{path} not written yet")
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), RT.render(table), n)


if __name__ == "__main__":
    unittest.main()
