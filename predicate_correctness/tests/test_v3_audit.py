"""Tests for the tracker v3 decision audit (scoring/v3_audit.py; docs/planning/tracker_v3/p4.md).

Built cases only (no saved data is read, except the hold-out guard, which raises before reading anything):
  - every class cell of decision_class;
  - the canonical-argument match and "near";
  - ran later / ran before (the executed_prefix_len rule for blocked and run checks);
  - a saved unknown is looked up as its blocking value and marked unknown-tipped;
  - blame patterns (suspect fact, suspect rule);
  - one blame test on a built case (P4.0 counts: removed, added, kept; first divergence), the variant values, and
    the rule-set variant.

Run from predicate_correctness/:
    /home/azureuser/miniconda3/bin/python3 -B -m unittest tests.test_v3_audit -v
Standard library only.
"""
from __future__ import annotations

import collections
import json
import os
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scoring import v3_audit as A  # noqa: E402


def _msg(tool, args):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": "c", "type": "function", "function": {"name": tool, "arguments": json.dumps(args)}}]}


def _call_of(m):
    fn = m["tool_calls"][0]["function"]
    return fn["name"], json.loads(fn["arguments"])


class TestClasses(unittest.TestCase):
    def test_every_cell(self):
        dc = A.decision_class
        self.assertEqual(dc("block", False, "exact", True, False, False), "too_strict")
        self.assertEqual(dc("block", False, "exact", True, True, False), "delayed")
        self.assertEqual(dc("block", True, "exact", True, False, False), "delayed")        # its own cap override ran
        self.assertEqual(dc("block", False, "exact", True, False, True), "unclear_done_before")
        self.assertEqual(dc("block", False, "exact", True, True, True), "unclear_done_before")
        self.assertEqual(dc("block", False, "near", True, False, False), "unclear_near_block")
        self.assertEqual(dc("block", False, "none", True, False, False), "unclear_other_block")
        self.assertEqual(dc("block", False, "exact", False, False, False), "block_tool_refuses")
        self.assertEqual(dc("block", True, "none", False, False, False), "block_tool_refuses")
        self.assertEqual(dc("allow", False, "exact", True, False, False), "right_allow")
        self.assertEqual(dc("allow", False, "near", True, False, False), "unclear_near_allow")
        self.assertEqual(dc("allow", False, "none", True, False, False), "allowed_unwanted")
        self.assertEqual(dc("allow", False, "exact", False, False, False), "allow_tool_refuses")
        self.assertEqual(set(A.CLASS_TEXT), set(A.CLASSES))

    def test_refused_on_mapped_fact(self):
        self.assertTrue(A.refused_on_mapped_fact({"accepted": False, "facts": {"order_status_checked_pending": False}}))
        self.assertFalse(A.refused_on_mapped_fact({"accepted": False, "facts": {}}))           # e.g. not enough seats
        self.assertFalse(A.refused_on_mapped_fact({"accepted": False, "facts": {"x": None}}))
        self.assertFalse(A.refused_on_mapped_fact({"accepted": True, "facts": {"x": True}}))
        self.assertFalse(A.refused_on_mapped_fact(None))


class TestMatch(unittest.TestCase):
    EXP = [("modify_pending_order_items", {"order_id": "#W1", "item_ids": ["a", "b"], "new_item_ids": ["c", "d"],
                                           "payment_method_id": "gift_card_1"}),
           ("modify_user_address", {"user_id": "u1", "zip": "10001", "city": "NY"}),
           ("book_reservation", {"user_id": "u2", "payment_methods": [{"payment_id": "p", "amount": 100}]})]

    def test_exact_ignores_key_order_and_integral_floats(self):
        args = {"payment_method_id": "gift_card_1", "new_item_ids": ["c", "d"], "item_ids": ["a", "b"],
                "order_id": "#W1"}
        self.assertEqual(A.match_expected("modify_pending_order_items", args, self.EXP), "exact")
        self.assertEqual(A.match_expected("book_reservation",
                                          {"payment_methods": [{"amount": 100.0, "payment_id": "p"}], "user_id": "u2"},
                                          self.EXP), "exact")
        self.assertEqual(A.canon({"b": 1.0, "a": [2.5, True]}), '{"a":[2.5,true],"b":1}')

    def test_near_is_same_tool_and_main_id(self):
        swapped = {"order_id": "#W1", "item_ids": ["b", "a"], "new_item_ids": ["d", "c"],
                   "payment_method_id": "gift_card_1"}                     # list order differs: not exact
        self.assertEqual(A.match_expected("modify_pending_order_items", swapped, self.EXP), "near")
        self.assertEqual(A.match_expected("modify_user_address", {"user_id": "u1", "zip": "10002", "city": "NY"},
                                          self.EXP), "near")
        self.assertEqual(A.match_expected("modify_pending_order_items", dict(swapped, order_id="#W2"), self.EXP),
                         "none")
        self.assertEqual(A.match_expected("cancel_pending_order", {"order_id": "#W1", "reason": "x"}, self.EXP), "none")
        self.assertEqual(A.main_id({"order_id": "#W1", "user_id": "u"}), ("order_id", "#W1"))
        self.assertIsNone(A.main_id({"reason": "x"}))


class TestRanLater(unittest.TestCase):
    def setUp(self):
        call = ("cancel_pending_order", {"order_id": "#W1", "reason": "ordered by mistake"})
        other = ("get_order_details", {"order_id": "#W1"})
        # executed = [system, user, (assistant, tool or user)*]; executed_prefix_len = 2 + 2 * exec_step
        self.executed = [{"role": "system"}, {"role": "user"},
                         _msg(*other), {"role": "tool"},          # 2, 3
                         _msg(*call), {"role": "tool"},           # 4, 5: the call ran here
                         {"role": "assistant", "content": "done"}, {"role": "user"}]
        self.calls = A.executed_calls(self.executed, _call_of)
        self.key = (call[0], A.canon(call[1]))

    def test_executed_calls(self):
        self.assertEqual([(p, t) for p, t, _ in self.calls], [(2, "get_order_details"), (4, "cancel_pending_order")])

    def test_blocked_check_before_the_run(self):
        # a block at exec_step 1 (prefix 4): the next executed step, at position 4, is the same call -> ran later
        self.assertTrue(A.ran_later(self.calls, *self.key, prefix=4, ran_here=False))
        self.assertFalse(A.ran_before(self.calls, *self.key, prefix=4))

    def test_run_check_itself_is_not_later(self):
        # the allowed check whose call is executed[4]: not "later", and nothing after it
        self.assertFalse(A.ran_later(self.calls, *self.key, prefix=4, ran_here=True))
        # a later block of the same call (prefix 6): it ran before
        self.assertTrue(A.ran_before(self.calls, *self.key, prefix=6))
        self.assertFalse(A.ran_later(self.calls, *self.key, prefix=6, ran_here=False))


def _table():
    """A built rule table: rule 9 = act IMPLIES (NOT a) OR b (blocking: a True, b False), rule 7 = act IMPLIES b."""
    def row(vals, holds, sets):
        return {"action": "act", "values": vals, "holds": holds, "flip_sets": sets,
                "tipping_facts": sorted({f for s in sets for f in s})}
    r9 = {"id": "9", "facts": ["a", "b"], "blocking_values": {"a": [True], "b": [False]},
          "rows": [row({"a": False, "b": False}, True, []), row({"a": False, "b": True}, True, []),
                   row({"a": True, "b": False}, False, [["a"], ["b"]]), row({"a": True, "b": True}, True, [])]}
    r7 = {"id": "7", "facts": ["b"], "blocking_values": {"b": [False]},
          "rows": [row({"b": False}, False, [["b"]]), row({"b": True}, True, [])]}
    return A.index_table({"rules": [r9, r7]})


class TestLocate(unittest.TestCase):
    def test_unknown_is_looked_up_as_blocking_value(self):
        t = _table()
        out = A.locate(t, "retail", "act", ["9"], {"a": (True, "tracker"), "b": (None, "judge")})
        self.assertEqual(len(out), 1)
        it = out[0]
        self.assertEqual(it["rule"], "retail:9")
        self.assertFalse(it["holds"])
        self.assertEqual(it["row"]["values"], {"a": True, "b": False})       # b unknown -> its blocking value False
        tip = {x["fact"]: x for x in it["tipping"]}
        self.assertEqual(set(tip), {"a", "b"})
        self.assertEqual(tip["b"]["source"], "judge-unknown")
        self.assertTrue(tip["b"]["unknown"])
        self.assertEqual(tip["a"]["source"], "tracker")
        self.assertFalse(tip["a"]["unknown"])

    def test_known_values_and_missing_rule(self):
        t = _table()
        out = A.locate(t, "retail", "act", ["7", "99"], {"b": (False, "judge")})
        self.assertEqual(out[0]["tipping"], [{"fact": "b", "value": False, "unknown": False, "source": "judge"}])
        self.assertEqual(out[1]["problem"], "rule not in the table")

    def test_allowing_value(self):
        tables = {"retail": _table()}
        self.assertIs(A.allowing_value(tables, "a"), False)
        self.assertIs(A.allowing_value(tables, "b"), True)
        self.assertIsNone(A.allowing_value(tables, "zzz"))


class TestBlamePatterns(unittest.TestCase):
    def test_suspects(self):
        def loc(rule, *facts):
            return {"rule": rule, "tipping": [{"fact": f, "source": "judge", "unknown": f == "c"} for f in facts]}
        wrong = [{"ckey": "k1", "dataset": "d1", "agent": "nano", "located": [loc("r:1", "a")]},
                 {"ckey": "k2", "dataset": "d2", "agent": "nano", "located": [loc("r:2", "a", "c")]},
                 {"ckey": "k3", "dataset": "d1", "agent": "luna", "located": [loc("r:3", "b")]}]
        bp = A.blame_patterns(wrong)
        self.assertEqual(bp["suspect_facts"], ["a"])                 # a: wrong in rules r:1 and r:2
        self.assertEqual(bp["suspect_rules"], ["r:2"])               # r:2: wrong with facts a and c
        fa = next(r for r in bp["facts"] if r["fact"] == "a")
        self.assertEqual((fa["wrong"], fa["n_rules"], fa["datasets"]), (2, 2, {"d1": 1, "d2": 1}))
        self.assertEqual(next(r for r in bp["facts"] if r["fact"] == "c")["unknown_tipped"], 1)
        self.assertEqual(bp["facts"][0]["fact"], "a")                # sorted by count


class TestBlameTest(unittest.TestCase):
    """One blame test on a built case: three checks of one conversation and one of another."""

    def setUp(self):
        acc = {"accepted": True, "check": None, "facts": {"f": True}}
        ref = {"accepted": False, "check": "non_pending", "facts": {"order_status_checked_pending": False}}
        base = {"write": True, "part": "main", "src": "frozen"}
        self.rows = {
            "c|1|0": dict(base, ckey="c|1|0", conv="c|1", idx=0, cls="too_strict", match="exact", label=acc),
            "c|1|1": dict(base, ckey="c|1|1", conv="c|1", idx=1, cls="right_allow", match="exact", label=acc),
            "c|1|2": dict(base, ckey="c|1|2", conv="c|1", idx=2, cls="block_tool_refuses", match="none", label=ref),
            "c|2|0": dict(base, ckey="c|2|0", conv="c|2", idx=0, cls="unclear_other_block", match="none", label=acc),
            "c|2|1": dict(base, ckey="c|2|1", conv="c|2", idx=1, write=False, cls=None, match=None, label=None),
        }

    def test_kept_when_it_removes_and_adds_none(self):
        changes = [("c|1|0", "block", "allow"), ("c|2|0", "block", "allow"), ("c|2|1", "block", "allow")]
        c = A.tally_changes(changes, self.rows)
        self.assertEqual((c["removed"], c["added"], c["new_allow_not_expected"], c["new_allow_not_write"]),
                         (1, 0, 1, 1))
        self.assertTrue(A.kept(c))

    def test_not_kept_when_it_adds(self):
        new_block = A.tally_changes([("c|1|0", "block", "allow"), ("c|1|1", "allow", "block")], self.rows)
        self.assertEqual((new_block["removed"], new_block["added_block"], new_block["added"]), (1, 1, 1))
        self.assertFalse(A.kept(new_block))
        wrong_allow = A.tally_changes([("c|1|0", "block", "allow"), ("c|1|2", "block", "allow")], self.rows)
        self.assertEqual((wrong_allow["added_allow_mapped"], wrong_allow["new_allow_tool_refuses"]), (1, 1))
        self.assertFalse(A.kept(wrong_allow))
        self.assertFalse(A.kept(collections.Counter()))               # removes nothing

    def test_first_divergence(self):
        changes = [("c|1|2", "block", "allow"), ("c|1|0", "block", "allow"), ("c|2|0", "block", "allow")]
        self.assertEqual(sorted(x[0] for x in A.first_divergence(changes, self.rows)), ["c|1|0", "c|2|0"])

    def test_variant_values(self):
        v = A.fact_variant_value
        self.assertIs(v("code_fact", False, True, None), True)               # the tool decides
        self.assertIs(v("code_fact", False, None, None), False)              # not decided: the saved value
        self.assertIsNone(v("code_fact", None, None, None))
        self.assertIs(v("code_fact", False, True, None, world_part_only=True), False)   # true status label: keep
        self.assertIs(v("code_fact", True, False, None, world_part_only=True), False)   # false status label: false
        self.assertIs(v("judge_flip", False, None, True), True)
        self.assertIs(v("judge_flip", None, False, False), False)

    def test_alone_fixable(self):
        one = [{"rule": "retail:9", "row": {"flip_sets": [["a"], ["b"]]}, "tipping": []}]
        two = one + [{"rule": "retail:7", "row": {"flip_sets": [["b"]]}, "tipping": []}]
        self.assertTrue(A.alone_fixable(one, "fact:a"))
        self.assertFalse(A.alone_fixable(two, "fact:a"))                    # rule 7 needs b
        self.assertTrue(A.alone_fixable(two, "fact:b"))
        self.assertTrue(A.alone_fixable(one, "rule:retail:9"))
        self.assertFalse(A.alone_fixable(two, "rule:retail:9"))
        self.assertFalse(A.alone_fixable([], "fact:a"))

    def test_rule_set_without(self):
        rs = {"rules": [{"id": "1"}, {"id": "2"}], "circuits": {"act": ["1", "2"], "other": ["2"]},
              "dispositions": [{"sentence": "S1", "rule_ids": ["1", "2"]}]}
        out = A.rule_set_without(rs, "2")
        self.assertEqual([r["id"] for r in out["rules"]], ["1"])
        self.assertEqual(out["circuits"], {"act": ["1"], "other": []})
        self.assertEqual(out["dispositions"][0]["rule_ids"], ["1"])
        self.assertEqual(len(rs["rules"]), 2)                                # the input is not changed
        with self.assertRaises(ValueError):
            A.rule_set_without(rs, "3")


class TestDevelopmentOnly(unittest.TestCase):
    def test_holdout_sets_are_refused(self):
        self.assertNotIn("ours.p10_luna_val", A.DEV_DATASETS)
        self.assertNotIn("partner.luna_val", A.DEV_DATASETS)
        for name in ("ours.p10_luna_val", "partner.luna_val"):
            with self.assertRaises(ValueError):
                next(A.iter_dev_conversations([name]))
        self.assertIn(A.HOLDOUT_FORK_MARK, "online_tracker.p10_luna_val.airline.test8.trial2.att15")


if __name__ == "__main__":
    unittest.main()
