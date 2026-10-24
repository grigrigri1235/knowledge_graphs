"""Tests for the p11 labels and classes (scoring/v3_labels.py; docs/planning/tracker_v3/p11.md steps 1, 3, 9).

Built cases only, plus two read-only files: the airline rule table (output/eval_v3/rule_table_airline.json, p2) and
τ-bench's airline data copy (through scoring/v3_p6_agreement.py, as tests/test_v3_code_facts.py), for the forbidden-allow
flag on a real fact result. No saved conversation, no hold-out, no LLM, no network.
  - every class cell (same_block, same_allow, good, bad, suspect, reported_unwanted_allow, undecided and its reasons),
    the order of the classes, the exact and the order-blind matcher, the repeat rule;
  - the four match kinds, item order included;
  - ran before / later (allow, block, cap override; order-blind);
  - the labels of a built conversation; the Stage B join rule of the tool labels; hold-out keys refused;
  - the first divergence and P11.7;
  - the forbidden-allow flag (rule airline:25) and world values;
  - the bootstrap by task on tiny known cases (deterministic with the seed); three_over_n.

Run from predicate_correctness/:
    /home/azureuser/miniconda3/bin/python3 -B -m unittest tests.test_v3_classify -v
Standard library only.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from scoring import v3_audit as A      # noqa: E402
from scoring import v3_labels as L     # noqa: E402

PENDING = "order_status_checked_pending"
CONFIRM = "user_explicitly_confirmed_pending_action"


# ----------------------------------------------------------------------------------------------- builders
def _msg(tool, args, cid="c"):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": cid, "type": "function", "function": {"name": tool, "arguments": json.dumps(args)}}]}


def _out(text="ok", cid="c"):
    return {"role": "tool", "tool_call_id": cid, "content": text}


def _call_of(m):
    fn = m["tool_calls"][0]["function"]
    return fn["name"], json.loads(fn["arguments"])


def lab(match="exact", accepted=True, mapped=(), repeat=False, repeat_ob=None, exact_matcher=None,
        domain="retail", tool="cancel_pending_order"):
    """A minimal write-check label for classify()."""
    if exact_matcher is None:
        exact_matcher = "near" if match == "exact_unordered" else match
    return {"match": match, "match_exact_matcher": exact_matcher, "repeat": repeat,
            "repeat_order_blind": repeat if repeat_ob is None else repeat_ob, "accepted": accepted,
            "mapped_facts": list(mapped), "domain": domain, "tool": tool}


def cls(saved, new, label, changed=(), **kw):
    return L.classify(saved, new, label, changed, **kw)["cls"]


# ----------------------------------------------------------------------------------------------- matching
CANCEL = ("cancel_pending_order", {"order_id": "#W1", "reason": "no longer needed"})
MODIFY = ("modify_pending_order_items", {"order_id": "#W2", "item_ids": ["a", "b"], "new_item_ids": ["c", "d"],
                                         "payment_method_id": "gift_card_1"})
RETURN = ("return_delivered_order_items", {"order_id": "#W3", "item_ids": ["x", "y", "z"],
                                           "payment_method_id": "paypal_1"})
FLIGHTS = ("update_reservation_flights", {"reservation_id": "ABC123", "cabin": "economy", "payment_id": "gc_1",
                                          "flights": [{"flight_number": "HAT1", "date": "2024-05-20"},
                                                      {"flight_number": "HAT2", "date": "2024-05-21"}]})
EXPECTED = [CANCEL, MODIFY, RETURN, FLIGHTS]


class TestMatchKinds(unittest.TestCase):
    def test_kinds_listed(self):
        self.assertEqual(L.MATCH_KINDS, ("exact", "exact_unordered", "near", "unwanted"))

    def test_exact_ignores_key_order_and_integral_floats(self):
        self.assertEqual(L.match_kind("cancel_pending_order", {"reason": "no longer needed", "order_id": "#W1"},
                                      EXPECTED), "exact")
        exp = [("update_reservation_baggages", {"reservation_id": "R1", "total_baggages": 2, "nonfree_baggages": 0,
                                                "payment_id": "p"})]
        self.assertEqual(L.match_kind("update_reservation_baggages", {"reservation_id": "R1", "total_baggages": 2.0,
                                                                      "nonfree_baggages": 0, "payment_id": "p"}, exp),
                         "exact")

    def test_exact_unordered_item_pairs(self):
        swapped = dict(MODIFY[1], item_ids=["b", "a"], new_item_ids=["d", "c"])       # same pairs, other order
        self.assertEqual(L.match_kind(MODIFY[0], swapped, EXPECTED), "exact_unordered")
        self.assertEqual(L.match_exact_matcher(MODIFY[0], swapped, EXPECTED), "near")    # p4's matcher
        self.assertEqual(L.unordered_canon(swapped), L.unordered_canon(MODIFY[1]))

    def test_other_pairs_are_not_unordered(self):
        repaired = dict(MODIFY[1], item_ids=["b", "a"])                                # a->d, b->c: other pairs
        self.assertEqual(L.match_kind(MODIFY[0], repaired, EXPECTED), "near")
        self.assertNotEqual(L.unordered_canon(repaired), L.unordered_canon(MODIFY[1]))

    def test_return_item_order(self):
        self.assertEqual(L.match_kind(RETURN[0], dict(RETURN[1], item_ids=["z", "x", "y"]), EXPECTED),
                         "exact_unordered")
        self.assertEqual(L.match_kind(RETURN[0], dict(RETURN[1], item_ids=["z", "x"]), EXPECTED), "near")

    def test_other_lists_keep_their_order(self):
        rev = dict(FLIGHTS[1], flights=list(reversed(FLIGHTS[1]["flights"])))
        self.assertEqual(L.match_kind(FLIGHTS[0], rev, EXPECTED), "near")

    def test_near_and_unwanted(self):
        self.assertEqual(L.match_kind("cancel_pending_order", {"order_id": "#W1", "reason": "ordered by mistake"},
                                      EXPECTED), "near")
        self.assertEqual(L.match_kind("cancel_pending_order", {"order_id": "#W9", "reason": "no longer needed"},
                                      EXPECTED), "unwanted")
        self.assertEqual(L.match_kind("modify_pending_order_address", {"order_id": "#W1"}, EXPECTED), "unwanted")
        self.assertEqual(L.match_kind("cancel_pending_order", {"reason": "no longer needed"}, EXPECTED), "unwanted")
        self.assertEqual(L.match_kind("cancel_pending_order", dict(CANCEL[1]), []), "unwanted")


# ----------------------------------------------------------------------------------------------- ran
class TestRan(unittest.TestCase):
    def setUp(self):
        # 0 system, 1 user, 2-3 cancel (ran), 4-5 modify with pairs swapped (ran), 6-7 cancel again (ran)
        swapped = dict(MODIFY[1], item_ids=["b", "a"], new_item_ids=["d", "c"])
        self.ex = [{"role": "system"}, {"role": "user"}, _msg(*CANCEL), _out(), _msg(MODIFY[0], swapped), _out(),
                   _msg(*CANCEL), _out()]
        self.calls = L.executed_calls(self.ex, _call_of)

    def test_executed_calls(self):
        self.assertEqual([(p, t) for p, t, _, _ in self.calls],
                         [(2, "cancel_pending_order"), (4, "modify_pending_order_items"), (6, "cancel_pending_order")])

    def test_allowed_check_its_own_run_is_not_later(self):
        r = L.ran_flags(self.calls, *CANCEL, prefix=6, ran_here=True)
        self.assertEqual((r["ran_before"], r["ran_later"], r["n_before"]), (True, False, 1))
        r = L.ran_flags(self.calls, *CANCEL, prefix=2, ran_here=True)
        self.assertEqual((r["ran_before"], r["ran_later"], r["n_before"]), (False, True, 0))

    def test_blocked_check_runs_later_at_the_prefix(self):
        r = L.ran_flags(self.calls, *CANCEL, prefix=2, ran_here=False)       # executed[2] is the next step
        self.assertEqual((r["ran_before"], r["ran_later"]), (False, True))

    def test_cap_override_counts_as_ran(self):
        # the run at 4-5 was a cap override (a block that ran): a later check of the same call sees it before
        r = L.ran_flags(self.calls, MODIFY[0], dict(MODIFY[1], item_ids=["b", "a"], new_item_ids=["d", "c"]),
                        prefix=6, ran_here=False)
        self.assertTrue(r["ran_before"])

    def test_order_blind_runs(self):
        r = L.ran_flags(self.calls, *MODIFY, prefix=2, ran_here=False)
        self.assertEqual((r["ran_later"], r["ran_later_unordered"]), (False, True))
        r = L.ran_flags(self.calls, *MODIFY, prefix=6, ran_here=False)
        self.assertEqual((r["ran_before"], r["ran_before_unordered"], r["n_before_unordered"]), (False, True, 1))

    def test_repeat_rule(self):
        self.assertTrue(L.repeat_of_expected(*CANCEL, EXPECTED, n_before=1))
        self.assertFalse(L.repeat_of_expected(*CANCEL, EXPECTED, n_before=0))
        self.assertFalse(L.repeat_of_expected(*CANCEL, EXPECTED + [CANCEL], n_before=1))      # expected twice
        self.assertTrue(L.repeat_of_expected(*CANCEL, EXPECTED + [CANCEL], n_before=2))
        self.assertFalse(L.repeat_of_expected("cancel_pending_order", {"order_id": "#W9"}, EXPECTED, n_before=3))
        swapped = dict(MODIFY[1], item_ids=["b", "a"], new_item_ids=["d", "c"])
        self.assertFalse(L.repeat_of_expected(MODIFY[0], swapped, EXPECTED, n_before=1))
        self.assertTrue(L.repeat_of_expected(MODIFY[0], swapped, EXPECTED, n_before=1, order_blind=True))


# ----------------------------------------------------------------------------------------------- labels of a conversation
DS = "stage_a.nano.tgr_frozen"
CONV = f"{DS}|retail/7/0"


def _conv(ep, checks, dataset=DS, conv_key=CONV, side="dev"):
    return SimpleNamespace(dataset=dataset, conv_key=conv_key, side=side, agent="nano", domain="retail",
                           split="tau_train", task_id=7, trial=0, source_guard="frozen", ep=ep,
                           checks=lambda: list(checks))


def _check(i, tool, args, prefix, saved, blocked=False, cap=False, conv_key=CONV):
    return SimpleNamespace(ckey=f"{conv_key}|{i}", check_idx=i, tool=tool, args=args,
                           attempt={"executed_prefix_len": prefix}, blocked=blocked, cap_override=cap,
                           saved_decision=saved)


class TestConversationLabels(unittest.TestCase):
    def setUp(self):
        swapped = dict(MODIFY[1], item_ids=["b", "a"], new_item_ids=["d", "c"])
        read = ("get_order_details", {"order_id": "#W1"})
        self.ex = [{"role": "system"}, {"role": "user"}, _msg(*read), _out(), _msg(*CANCEL), _out(),
                   _msg(MODIFY[0], swapped), _out(), _msg(*CANCEL), _out("Error: non-pending order cannot be "
                                                                            "cancelled")]
        self.checks = [_check(0, *read, 2, "allow"),
                       _check(1, *CANCEL, 4, "block", blocked=True),
                       _check(2, *CANCEL, 4, "allow"),
                       _check(3, MODIFY[0], swapped, 6, "block", cap=True),
                       _check(4, *CANCEL, 8, "allow")]
        self.acts = [read, CANCEL, MODIFY]
        self.ep = {"executed": self.ex, "reward": 0.0,
                   "reward_info": {"actions": [{"name": n, "kwargs": k} for n, k in self.acts]}}
        ok = {"accepted": True, "check": None, "facts": {PENDING: True}, "first_error": None, "part": None}
        self.tl = {f"{CONV}|1": ok, f"{CONV}|2": ok,
                   f"{CONV}|3": {"accepted": True, "check": None, "facts": {PENDING: True}, "first_error": None,
                                 "part": None},
                   f"{CONV}|4": {"accepted": False, "check": "non_pending", "facts": {PENDING: False},
                                 "first_error": "Error: non-pending order cannot be cancelled", "part": None}}
        self.index = {f"{CONV}|{i}": {"saved_decision": c.saved_decision, "bin": "12-24k", "history_len": 13000}
                      for i, c in enumerate(self.checks)}

    def labels(self, **kw):
        conv = _conv(kw.pop("ep", self.ep), kw.pop("checks", self.checks), **kw)
        return L.conversation_labels(conv, self.index, self.tl, expected_actions=self.acts, call_of=_call_of)

    def test_fields(self):
        out, problems = self.labels()
        self.assertEqual(problems, [])
        self.assertEqual(sorted(out), [f"{CONV}|{i}" for i in (1, 2, 3, 4)])          # writes only
        b, a, cap, rep = (out[f"{CONV}|{i}"] for i in (1, 2, 3, 4))
        self.assertEqual((b["match"], b["saved_decision"], b["ran_later"], b["ran_after_block"], b["ran_here"]),
                         ("exact", "block", True, True, False))
        self.assertEqual((a["ran_before"], a["ran_later"], a["repeat"]), (False, True, False))
        self.assertEqual((cap["match"], cap["match_exact_matcher"], cap["saved_decision"], cap["ran_here"],
                          cap["ran_after_block"]), ("exact_unordered", "near", "block", True, True))
        self.assertEqual((rep["ran_before"], rep["repeat"], rep["accepted"], rep["tool_check"], rep["mapped_facts"]),
                         (True, True, False, "non_pending", [PENDING]))
        self.assertEqual(rep["decided_facts"], {PENDING: False})
        self.assertEqual((b["task"], b["part"], b["bin"], b["history_len"], b["reward"], b["success"]),
                         ("retail/train/7", "main", "12-24k", 13000, 0.0, False))
        self.assertEqual(b["expected"], [[n, A.canon(k)] for n, k in (CANCEL, MODIFY)])     # write actions only
        self.assertEqual(b["main_id"], ["order_id", "#W1"])

    def test_problems_are_listed(self):
        ep = dict(self.ep, reward_info={"actions": [{"name": "cancel_pending_order", "kwargs": {}}]})
        bad = list(self.checks)
        bad[2] = _check(2, *CANCEL, 6, "allow")                                      # executed[6] is the modify
        _, problems = self.labels(ep=ep, checks=bad)
        self.assertEqual(len(problems), 2, problems)

    def test_missing_label_and_index_raise(self):
        del self.tl[f"{CONV}|2"]
        with self.assertRaises(KeyError):
            self.labels()

    def test_holdout_conversation_is_refused(self):
        with self.assertRaises(L.HoldOutData):
            self.labels(side="holdout")
        hk = "partner.luna_val|retail/7/0"
        with self.assertRaises(L.HoldOutData):
            self.labels(dataset="partner.luna_val", conv_key=hk)


class TestToolLabelJoin(unittest.TestCase):
    def write(self, lines):
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for d in lines:
                f.write(json.dumps(d) + "\n")
        self.addCleanup(os.remove, path)
        return path

    @staticmethod
    def line(ckey, part=None, accepted=True):
        d = {"ckey": ckey, "accepted": accepted, "check": None if accepted else "non_pending", "facts": {},
             "first_error": None, "decision": "allowed"}
        if part is not None:
            d["part"] = part
        return d

    def test_stage_b_prefix_and_fork_lines_are_dropped(self):
        sb = "stage_b|online_tracker.p10_luna_train.retail.test112.trial0.att15/A/0"
        path = self.write([self.line(f"{DS}|retail/1/0|3"), self.line(f"{sb}|12", "prefix"),
                           self.line(f"{sb}|15", "fork"), self.line(f"{sb}|16", "after")])
        got = L.load_tool_labels(path)
        self.assertEqual(sorted(got), sorted([f"{DS}|retail/1/0|3", f"{sb}|16"]))
        self.assertEqual(got[f"{sb}|16"]["part"], "after")
        self.assertIs(L.tool_label_for(got, f"{sb}|16"), got[f"{sb}|16"])
        with self.assertRaises(KeyError):
            L.tool_label_for(got, f"{sb}|12")                                        # a prefix attempt: no label

    def test_stage_b_check_needs_an_after_label(self):
        sb = "stage_b|f/A/0"
        with self.assertRaises(ValueError):
            L.tool_label_for({f"{sb}|3": {"part": "prefix"}}, f"{sb}|3")

    def test_duplicate_and_holdout_lines_raise(self):
        with self.assertRaises(ValueError):
            L.load_tool_labels(self.write([self.line(f"{DS}|retail/1/0|3"), self.line(f"{DS}|retail/1/0|3")]))
        with self.assertRaises(L.HoldOutData):
            L.load_tool_labels(self.write([self.line("ours.p10_luna_val|retail/1/0|3")]))

    def test_holdout_keys(self):
        self.assertTrue(L.is_holdout_ckey("partner.luna_val|retail/1/0|3"))
        self.assertTrue(L.is_holdout_ckey("ours.p10_luna_val|airline/2/0|1"))
        self.assertTrue(L.is_holdout_ckey("stage_b|online_tracker.p10_luna_val.retail.test1.trial0.att3/A/0|9"))
        self.assertFalse(L.is_holdout_ckey("stage_b|online_tracker.p10_luna_train.retail.test1.trial0.att3/A/0|9"))
        self.assertFalse(L.is_holdout_ckey("partner.luna_train_v5|retail/1/0|3"))

    def test_keys_and_decisions(self):
        self.assertEqual(L.conv_key_of(f"{CONV}|12"), CONV)
        self.assertEqual(L.check_index_of(f"{CONV}|12"), 12)
        self.assertEqual(L.task_key("airline", "partner_val", 3), "airline/test/3")
        for x, want in (("allow", "allow"), ("allowed", "allow"), (True, "allow"), ("block", "block"),
                        ("blocked", "block"), ("cap_override", "block"), (False, "block")):
            self.assertEqual(L.norm_decision(x), want)
        with self.assertRaises(ValueError):
            L.norm_decision("maybe")


# ----------------------------------------------------------------------------------------------- classes
class TestClasses(unittest.TestCase):
    def test_class_lists(self):
        self.assertEqual(set(L.CLASS_TEXT), set(L.CLASSES))
        self.assertEqual(set(L.CLASSES), {"good", "bad", "suspect", "reported_unwanted_allow", "undecided",
                                          "same_block", "same_allow"})

    def test_unchanged(self):
        for m in ("exact", "near", "unwanted"):
            self.assertEqual(cls("block", "block", lab(m)), "same_block")
            self.assertEqual(cls("allow", "allow", lab(m, accepted=False, mapped=[PENDING])), "same_allow")
        self.assertEqual(cls("cap_override", "block", None), "same_block")
        r = L.classify("allow", "allow", lab())
        self.assertEqual((r["direction"], r["reason"]), (None, None))

    def test_good(self):
        r = L.classify("block", "allow", lab("exact"))
        self.assertEqual((r["cls"], r["direction"], r["kind"]), ("good", "block_to_allow", "exact"))

    def test_bad_on_every_match_kind(self):
        for m in ("exact", "exact_unordered", "near", "unwanted"):
            self.assertEqual(cls("block", "allow", lab(m, accepted=False, mapped=[PENDING])), "bad", m)
        # first: a confirmation-only change or the order-blind matcher never hides one
        self.assertEqual(cls("block", "allow", lab("exact", accepted=False, mapped=[PENDING]), [CONFIRM]), "bad")
        self.assertEqual(cls("block", "allow", lab("near", accepted=False, mapped=[PENDING]), order_blind=True),
                         "bad")
        self.assertEqual(cls("blocked", "allowed", lab("exact", accepted=False, mapped=[PENDING])), "bad")

    def test_suspect(self):
        self.assertEqual(cls("allow", "block", lab("exact")), "suspect")
        r = L.classify("allow", "block", lab("exact", accepted=False, mapped=[PENDING]))
        self.assertEqual((r["cls"], r["accepted"], r["direction"]), ("suspect", False, "allow_to_block"))

    def test_reported_unwanted_allow(self):
        r = L.classify("block", "allow", lab("unwanted"), ["payment_method_is_gift_card"])
        self.assertEqual((r["cls"], r["refused_unmapped"], r["changed_facts"]),
                         ("reported_unwanted_allow", False, ["payment_method_is_gift_card"]))
        r = L.classify("block", "allow", lab("unwanted", accepted=False))          # refused, unmapped check
        self.assertEqual((r["cls"], r["refused_unmapped"]), ("reported_unwanted_allow", True))

    def test_repeat_rule(self):
        self.assertEqual(cls("block", "allow", lab("exact", repeat=True)), "reported_unwanted_allow")
        self.assertEqual(cls("block", "allow", lab("exact", repeat=True), repeat_rule=False), "good")
        r = L.classify("allow", "block", lab("exact", repeat=True))
        self.assertEqual((r["cls"], r["reason"]), ("undecided", "block_on_unwanted"))

    def test_undecided_near(self):
        for s, n in (("block", "allow"), ("allow", "block")):
            r = L.classify(s, n, lab("near"))
            self.assertEqual((r["cls"], r["reason"]), ("undecided", "near"))

    def test_undecided_confirmation_only(self):
        for s, n, m in (("block", "allow", "exact"), ("allow", "block", "exact"), ("block", "allow", "unwanted")):
            r = L.classify(s, n, lab(m), [CONFIRM, "consequential_action_details_listed"])
            self.assertEqual((r["cls"], r["reason"], r["confirmation_only"]), ("undecided", "confirmation_only", True))
        for f in L.CONFIRMATION_FACTS:
            self.assertEqual(cls("block", "allow", lab("exact"), [f]), "undecided", f)
        # a confirmation fact together with another fact is not confirmation-only
        self.assertEqual(cls("block", "allow", lab("exact"), [CONFIRM, "gift_card_balance_covers_price_difference"]),
                         "good")
        self.assertEqual(len(L.CONFIRMATION_FACTS), 6)

    def test_undecided_other(self):
        r = L.classify("block", "allow", lab("exact", accepted=False))             # refused at an unmapped check
        self.assertEqual((r["cls"], r["reason"], r["refused_unmapped"]),
                         ("undecided", "allow_exact_tool_refuses_unmapped", True))
        r = L.classify("allow", "block", lab("unwanted"))
        self.assertEqual((r["cls"], r["reason"]), ("undecided", "block_on_unwanted"))
        r = L.classify("block", "allow", None, ["user_authenticated"])               # a reply or read: no label
        self.assertEqual((r["cls"], r["reason"]), ("undecided", "no_outcome_label"))
        for reason in ("near", "confirmation_only", "allow_exact_tool_refuses_unmapped", "block_on_unwanted",
                       "no_outcome_label"):
            self.assertIn(reason, L.UNDECIDED_REASONS)

    def test_order_blind_matcher(self):
        x = lab("exact_unordered")
        self.assertEqual(L.classify("block", "allow", x)["reason"], "near")              # exact matcher: near
        self.assertEqual(cls("block", "allow", x, order_blind=True), "good")
        self.assertEqual(cls("allow", "block", x, order_blind=True), "suspect")
        self.assertEqual(cls("block", "allow", lab("exact_unordered", repeat=False, repeat_ob=True),
                             order_blind=True), "reported_unwanted_allow")
        self.assertEqual(L.wanted_kind(x), "near")
        self.assertEqual(L.wanted_kind(x, order_blind=True), "exact")
        self.assertEqual(L.wanted_kind(lab("exact", repeat=True), repeat_rule=False), "exact")

    def test_judge_value_is_not_read(self):
        # the classes use only τ-bench's labels: extra judge fields change nothing
        a = lab("exact")
        b = dict(a, judge={"user_explicitly_confirmed_pending_action": {"value": False}}, judge_own={CONFIRM: False})
        self.assertEqual(L.classify("block", "allow", a), L.classify("block", "allow", b))


# ----------------------------------------------------------------------------------------------- first divergence
class TestFirstDivergence(unittest.TestCase):
    def test_first_by_index_not_by_input_order(self):
        rows = [(f"{CONV}|5", "allow", "block"), (f"{CONV}|1", "allow", "allow"), (f"{CONV}|3", "block", "allow"),
                (f"{CONV}|10", "block", "block"), (f"{CONV}|0", "block", "block")]
        self.assertEqual(L.first_divergence(rows), f"{CONV}|3")
        roles = L.divergence_roles(rows)
        self.assertEqual(roles, {f"{CONV}|0": "before", f"{CONV}|1": "before", f"{CONV}|3": "first",
                                 f"{CONV}|5": "descriptive", f"{CONV}|10": "descriptive"})

    def test_no_divergence_and_two_conversations(self):
        other = f"{DS}|retail/8/0"
        rows = [(f"{CONV}|0", "allow", "allow"), (f"{CONV}|2", "blocked", "block"),
                (f"{other}|0", "allow", "block"), (f"{other}|1", "allow", "allow")]
        self.assertIsNone(L.first_divergence(rows[:2]))
        roles = L.divergence_roles(rows)
        self.assertEqual((roles[f"{CONV}|0"], roles[f"{CONV}|2"], roles[f"{other}|0"], roles[f"{other}|1"]),
                         ("before", "before", "first", "descriptive"))
        with self.assertRaises(ValueError):
            L.first_divergence(rows)

    def test_p11_7(self):
        rows = [(f"{CONV}|0", "allow", "allow", False), (f"{CONV}|1", "block", "allow", False),
                (f"{CONV}|2", "allow", "block", False)]
        self.assertEqual(L.p11_7_misses(rows), [f"{CONV}|1"])            # only the first divergence can miss
        rows[1] = (f"{CONV}|1", "block", "allow", True)
        self.assertEqual(L.p11_7_misses(rows), [])                       # a v3 value changed: no miss


# ----------------------------------------------------------------------------------------------- forbidden allows
R25 = ("cancellation_is_within_24_hours", "airline_cancelled_flight_confirmed", "reservation_has_business_cabin",
       "reservation_has_basic_or_economy_cabin", "reservation_has_travel_insurance")


def world25(within=False, cancelled=False, business=False, insurance=False):
    return {"cancellation_is_within_24_hours": within, "airline_cancelled_flight_confirmed": cancelled,
            "reservation_has_business_cabin": business, "reservation_has_basic_or_economy_cabin": not business,
            "reservation_has_travel_insurance": insurance}


class TestForbidden(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = A.load_tables(["airline"])

    def forb(self, world, tool="cancel_reservation"):
        return L.forbidden_by_database("airline", tool, world, self.tables["airline"])

    def test_rule_25_by_the_database(self):
        got = self.forb(world25())
        self.assertEqual([x["rule"] for x in got], ["airline:25"])
        self.assertEqual(got[0]["facts"], {f: False for f in R25 if f != "reservation_has_basic_or_economy_cabin"})
        self.assertEqual(self.forb(world25(insurance=True)), [])      # the user's reason decides: not the database
        self.assertEqual(self.forb(world25(within=True)), [])
        self.assertEqual(self.forb(world25(cancelled=True)), [])
        self.assertEqual(self.forb(world25(business=True)), [])
        self.assertEqual(self.forb({"cancellation_is_within_24_hours": False}), [])      # the rest unknown: allowing
        self.assertEqual(self.forb({}), [])
        self.assertEqual(self.forb(world25(), tool="update_reservation_baggages"), [])

    def test_rule_26_used_segment(self):
        got = self.forb({"reservation_has_no_used_flight_segments": False})
        self.assertEqual([x["rule"] for x in got], ["airline:26"])

    def test_flag_on_new_allows_the_tool_accepts(self):
        x = lab("exact", domain="airline", tool="cancel_reservation")
        r = L.classify("block", "allow", x, world=world25(), tables=self.tables)
        self.assertEqual((r["cls"], r["forbidden_allow_tool_accepts"]), ("good", True))   # reported, not a class
        self.assertEqual([y["rule"] for y in r["forbidden_rules"]], ["airline:25"])
        self.assertFalse(L.classify("block", "allow", x, world=world25(insurance=True),
                                    tables=self.tables)["forbidden_allow_tool_accepts"])
        self.assertFalse(L.classify("allow", "allow", x, world=world25(), tables=self.tables)
                         ["forbidden_allow_tool_accepts"])                                  # not a new allow
        self.assertFalse(L.classify("block", "allow", dict(x, accepted=False), world=world25(), tables=self.tables)
                         ["forbidden_allow_tool_accepts"])                                  # the tool refuses
        self.assertIsNone(L.classify("block", "allow", x)["forbidden_allow_tool_accepts"])   # no world given
        self.assertFalse(L.classify("block", "allow", None, world=world25(), tables=self.tables)
                         ["forbidden_allow_tool_accepts"])

    def test_world_value_built(self):
        ed = {"combine": "a AND b", "parts": {"a": {"source": "event"}, "b": {"source": "database"}}}
        self.assertIs(L.world_value(ed, {"value": False, "parts": {"a": {"value": False}, "b": {"value": False}}}),
                      False)
        self.assertIs(L.world_value(ed, {"value": False, "parts": {"a": {"value": False}, "b": {"value": True}}}),
                      True)                                      # not looked up yet: an agent step, not the world
        self.assertIsNone(L.world_value(ed, {"value": False, "how": "blocking_value", "parts": {}}))
        sq = {"combine": "a AND b", "parts": {"a": {"source": "structure"}, "b": {"source": "question"}}}
        self.assertIsNone(L.world_value(sq, {"value": True, "parts": {"a": {"value": True}, "b": {"value": True}}}))
        orx = {"combine": "a OR (b AND c)", "parts": {"a": {"source": "database"}, "b": {"source": "structure"},
                                                      "c": {"source": "question"}}}
        self.assertIs(L.world_value(orx, {"parts": {"a": {"value": True}}}), True)
        self.assertIsNone(L.world_value(orx, {"parts": {"a": {"value": False}}}))
        ar = {"combine": "a", "parts": {"a": {"source": "arguments"}}}
        self.assertIs(L.world_value(ar, {"parts": {"a": {"value": False}}}), False)
        self.assertIsNone(L.world_value(ar, {"parts": {"a": {"value": False}}}, sources=("database",)))
        fe = {"combine": "a OR b", "for_each": {"arg": "passengers"},
              "parts": {"a": {"source": "structure"}, "b": {"source": "database"}}}
        items = [{"parts": {"b": {"value": True}}}, {"parts": {"b": {"value": False}}}]
        self.assertIsNone(L.world_value(fe, {"items": items}))
        self.assertIs(L.world_value(fe, {"items": items[:1]}), True)


class TestForbiddenRealFacts(unittest.TestCase):
    """rule 25 on a real reservation, from the v3 facts as p6 evaluates them (τ-bench's data copy, read only)."""

    @classmethod
    def setUpClass(cls):
        from scoring import v3_p6_agreement as P6
        from state_tracker import state as S
        from state_tracker.v3 import code_helpers as CH
        cls.P6, cls.CH = P6, CH
        cls.doc = P6.merged_facts("airline")
        cls.db = S.load_db("airline")
        cls.tables = A.load_tables(["airline"])

    def setUp(self):
        self.CH.register_all()                    # another test may have emptied the helper registry

    def reservation(self, insurance):
        db = self.db

        def days(r):
            return [((db["flights"].get(f["flight_number"]) or {}).get("dates") or {}).get(f["date"])
                    for f in r["flights"]]

        def plain(r):          # every flight has an entry for its date, none cancelled
            return bool(r["flights"]) and all(d is not None and d.get("status") != "cancelled" for d in days(r))
        return next(k for k in sorted(db["reservations"]) for r in [db["reservations"][k]]
                    if r["created_at"] < "2024-05-14T15:00:00" and r["insurance"] == insurance
                    and r["cabin"] in ("basic_economy", "economy") and plain(r))

    def world(self, rid, look=True):
        calls = [("get_reservation_details", {"reservation_id": rid})] if look else []
        st = self.P6.state_for("airline", calls, "cancel_reservation", {"reservation_id": rid})
        results = {f: self.P6.evaluate_code(self.doc, f, st) for f in R25}
        return L.world_values("airline", results, self.doc), results

    def test_forbidden_cancellation(self):
        rid = self.reservation("no")
        w, res = self.world(rid)
        self.assertEqual(w, world25(), (rid, {f: r["parts"] for f, r in res.items()}))
        got = L.forbidden_by_database("airline", "cancel_reservation", w, self.tables["airline"])
        self.assertEqual([x["rule"] for x in got], ["airline:25"])
        w2, res2 = self.world(rid, look=False)                   # not looked up: the facts are false, the world same
        self.assertEqual(w2, w)
        self.assertTrue(all(r["value"] is False for r in res2.values()))

    def test_insured_cancellation_is_not_decided_by_the_database(self):
        w, _ = self.world(self.reservation("yes"))
        self.assertEqual(w, world25(insurance=True))
        self.assertEqual(L.forbidden_by_database("airline", "cancel_reservation", w, self.tables["airline"]), [])


# ----------------------------------------------------------------------------------------------- statistics
class TestStatistics(unittest.TestCase):
    def test_two_tasks_known_range(self):
        # task t1: a 1/1, b 0/1; task t2: a 0/1, b 0/1. A resample of 2 tasks gives 0, 0.5 or 1 (1/4, 1/2, 1/4).
        units = [("t1", 1, 1, 0, 1), ("t2", 0, 1, 0, 1)]
        r = L.bootstrap_rate_diff(units)
        self.assertEqual((r["diff"], r["rate_a"], r["rate_b"], r["low"], r["high"]), (0.5, 0.5, 0.0, 0.0, 1.0))
        self.assertEqual((r["n_tasks"], r["resamples"], r["seed"], r["level"], r["undefined_resamples"]),
                         (2, 10000, 20261023, 0.95, 0))
        self.assertEqual(L.bootstrap_rate_diff(list(reversed(units))), r)          # input order does not matter

    def test_deterministic_with_the_seed(self):
        units = [(f"t{i}", i % 3, 3, (i * 7) % 4, 4) for i in range(12)]
        a, b = L.bootstrap_rate_diff(units), L.bootstrap_rate_diff(units)
        self.assertEqual(a, b)
        self.assertLessEqual(a["low"], a["diff"])
        self.assertLessEqual(a["diff"], a["high"])
        c = L.bootstrap_rate_diff(units, seed=1)
        self.assertEqual(c["diff"], a["diff"])
        self.assertEqual(L.BOOT_SEED, 20261023)
        self.assertEqual(L.BOOT_N, 10000)

    def test_constant_difference(self):
        units = [(t, 1, 2, 1, 4) for t in ("a", "b", "c")]
        r = L.bootstrap_rate_diff(units, n=500)
        self.assertEqual((r["diff"], r["low"], r["high"]), (0.25, 0.25, 0.25))

    def test_units_are_summed_per_task(self):
        split = [("t1", 1, 2, 0, 2), ("t1", 1, 2, 0, 2), ("t2", 0, 3, 1, 3)]
        whole = [("t1", 2, 4, 0, 4), ("t2", 0, 3, 1, 3)]
        self.assertEqual(L.bootstrap_rate_diff(split, n=300), L.bootstrap_rate_diff(whole, n=300))

    def test_undefined_resamples_are_counted(self):
        units = [("t1", 1, 1, 0, 0), ("t2", 0, 1, 1, 1)]          # a resample of t1 only has no b denominator
        r = L.bootstrap_rate_diff(units)
        self.assertGreater(r["undefined_resamples"], 2000)
        self.assertLess(r["undefined_resamples"], 3000)
        self.assertEqual(L.bootstrap_rate_diff(units)["undefined_resamples"], r["undefined_resamples"])

    def test_one_rate(self):
        r = L.bootstrap_rate([("t1", 1, 1), ("t2", 0, 1)])
        self.assertEqual((r["rate"], r["low"], r["high"], r["n_tasks"]), (0.5, 0.0, 1.0, 2))

    def test_errors(self):
        with self.assertRaises(ValueError):
            L.bootstrap_rate_diff([])
        with self.assertRaises(ValueError):
            L.bootstrap_rate_diff([("t1", 0, 0, 0, 1)])
        with self.assertRaises(ValueError):
            L.bootstrap_rate_diff([("t1", 0, 1)])

    def test_percentile(self):
        self.assertEqual(L._percentile([0.0, 1.0, 2.0, 3.0], 0.5), 1.5)
        self.assertEqual(L._percentile([0.0, 1.0, 2.0, 3.0], 0.0), 0.0)
        self.assertEqual(L._percentile([0.0, 1.0, 2.0, 3.0], 1.0), 3.0)
        self.assertAlmostEqual(L._percentile([float(i) for i in range(101)], 0.025), 2.5)

    def test_three_over_n(self):
        self.assertEqual(L.three_over_n(100), 0.03)
        self.assertEqual(L.three_over_n(1), 3.0)
        for n in (0, -1):
            with self.assertRaises(ValueError):
                L.three_over_n(n)


if __name__ == "__main__":
    unittest.main()
