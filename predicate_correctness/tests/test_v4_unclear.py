"""Tests of the v4 unclear handling (predicate_table.md D10) and the v4 question helpers of
state_tracker/v4/questions_v4.py: re-ask with the second wording, block (counted) or allow + log, the notes and
events, ask_first_yes_v4, insurance_stated_v4 (K17), offer_kind_v4, offer_amount_ok_v4. $0: fake backends only.

    cd predicate_correctness && ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v4_unclear
"""
from __future__ import annotations

import os
import unittest

from state_tracker.v3 import facts_format_v3 as F
from state_tracker.v3 import questions as Q
from state_tracker.v4 import questions_v4 as Q4

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "fixtures_v4", "questions_v4_fixture.json")


def setUpModule():
    Q4.block_network()
    Q4.set_questions_path_v4(FIXTURE)


def tearDownModule():
    Q4.set_questions_path_v4(None)


class State:
    """A tiny stand-in for the recording state: a domain, a pending call and a few database rows."""

    def __init__(self, domain="retail", tool=None, rows=None):
        self.domain = domain
        self.pending = {"tool": tool} if tool else None
        self.rows = rows or {}

    def db_get(self, table, key):
        return self.rows.get((table, key))

    def db_all(self, table):
        return [v for (t, _), v in self.rows.items() if t == table]


def make_ctx(hook, fact="some_fact", part="b", domain="retail", tool=None, args=None, rows=None):
    return F.Context(fact, part, {}, State(domain, tool, rows), dict(args or {}), None, hook)


def by_text(table, default="no"):
    """A fake policy: the answer word by a word in the (first) message."""
    def p(qid, inputs, norm):
        text = " ".join(str(v) for v in norm.values() if isinstance(v, str)) + " ".join(
            " ".join(v) for v in norm.values() if isinstance(v, list))
        for word, ans in table.items():
            if word in text:
                return ans
        return default
    return p


def hook_of(first, second=None, **kw):
    return Q4.QuestionsV4(Q4.FakeBackendV4(first, second=second, **kw), doc=Q4.load_questions_v4(FIXTURE))


class TestReask(unittest.TestCase):
    def test_write_check_unclear_then_yes(self):
        h = hook_of("unclear", second="yes")
        ctx = make_ctx(h, fact="user_complained_about_relevant_flight_situation", domain="airline")
        self.assertTrue(Q4.h_ask_v4(ctx, "K8", "My flight got cancelled, this is awful."))
        ev = [n for n in ctx.notes if isinstance(n, dict) and n.get("v4") == "reask"]
        self.assertEqual(len(ev), 1)
        self.assertEqual((ev[0]["status1"], ev[0]["status2"], ev[0]["qid"]), ("unclear", "yes", "K8"))
        self.assertNotEqual(ev[0]["key1"], ev[0]["key2"])
        self.assertEqual(h.take_events_v4(), ev)
        self.assertEqual(h.take_events_v4(), [])
        self.assertEqual(h.stats.reasks["K8"], 1)
        self.assertEqual([x["wording"] for x in h.ask_lines], [1, 2])
        self.assertEqual(h.backend.wordings, {1: 1, 2: 1})

    def test_write_check_still_unclear_blocks_and_counts(self):
        h = hook_of("unclear", second="unclear")
        ctx = make_ctx(h, domain="airline")
        with self.assertRaises(F.UseBlockingValue) as cm:
            Q4.h_ask_v4(ctx, "K8", "Something about my flight.")
        self.assertEqual(cm.exception.kind, "unclear")
        self.assertEqual(h.stats.blocking["K8"], 1)
        self.assertEqual(h.stats.reasks["K8"], 1)

    def test_failed_quote_and_bad_output_count_as_unclear(self):
        h = hook_of("bad_quote", second="yes")
        self.assertTrue(Q4.h_ask_v4(make_ctx(h, domain="airline"), "K8", "My flight was delayed 6 hours."))
        h = hook_of(lambda q, i, n: {"answer": "maybe", "quote": ""}, second="no")
        self.assertFalse(Q4.h_ask_v4(make_ctx(h, domain="airline"), "K8", "My flight was delayed 6 hours."))
        self.assertEqual(h.stats.reasks["K8"], 1)

    def test_clear_first_answer_no_reask(self):
        h = hook_of("no")
        self.assertFalse(Q4.h_ask_v4(make_ctx(h, domain="airline"), "K8", "Is my flight on time?"))
        self.assertEqual(h.backend.wordings, {1: 1})

    def test_no_message_no_question(self):
        h = hook_of("yes")
        self.assertFalse(Q4.h_ask_v4(make_ctx(h), "K8", "   "))
        self.assertEqual(h.backend.calls, 0)
        self.assertEqual(h.stats.no_message["K8"], 1)


class TestAllowAndLog(unittest.TestCase):
    def test_k13_still_unclear_allows_and_logs(self):
        h = hook_of("unclear", second="unclear")
        h.where = {"run_id": "r", "check": 4}
        ctx = make_ctx(h, fact="request_cannot_be_handled_within_scope", part="b")
        self.assertTrue(Q4.h_ask_first_yes_v4(ctx, "K13", ["I want a free replacement"], on_unclear=True))
        ev = [e for e in h.take_events_v4() if e["v4"] == "unclear_allowed"]
        self.assertEqual(len(ev), 1)
        self.assertEqual((ev[0]["fact"], ev[0]["qid"], ev[0]["value"]),
                         ("request_cannot_be_handled_within_scope", "K13", True))
        self.assertEqual(h.stats.unclear_allowed["K13"], 1)
        self.assertEqual(h.stats.blocking["K13"], 0)
        self.assertTrue(all(x["where"] == {"run_id": "r", "check": 4} for x in h.ask_lines))
        self.assertIn("unclear_allowed", h.stats.as_dict()["K13"])

    def test_k4_allow_value_false(self):
        h = hook_of("unclear", second="unclear")
        self.assertFalse(Q4.h_ask_first_yes_v4(make_ctx(h), "K4", ["I'm Lei, zip 76192"], on_unclear=False))

    def test_k16_second_wording_decides(self):
        h = hook_of("unclear", second="yes")
        self.assertTrue(Q4.h_ask_first_yes_v4(make_ctx(h, domain="airline"), "K16", ["get rid of my booking"],
                                              on_unclear=False))
        self.assertEqual(h.stats.unclear_allowed["K16"], 0)

    def test_policy_mismatch_is_a_build_error(self):
        h = hook_of("unclear", second="unclear")
        with self.assertRaises(ValueError):
            Q4.h_ask_first_yes_v4(make_ctx(h), "K13", ["x request"])            # file says allow, no value
        with self.assertRaises(ValueError):
            Q4.h_ask_v4(make_ctx(h, domain="airline"), "K8", "my flight", on_unclear=True)   # file says block
        with self.assertRaises(TypeError):
            Q4.h_ask_first_yes_v4(make_ctx(h), "K13", ["x request"], on_unclear="yes")

    def test_yes_elsewhere_wins_over_unclear(self):
        h = hook_of(by_text({"vague": "unclear", "store credit": "yes"}),
                    second=by_text({"vague": "unclear", "store credit": "yes"}))
        ctx = make_ctx(h)
        self.assertTrue(Q4.h_ask_first_yes_v4(ctx, "K13", ["something vague", "give me store credit"],
                                              on_unclear=False))
        self.assertEqual(h.stats.unclear_allowed["K13"], 0)


class TestFirstYes(unittest.TestCase):
    def test_k1_pairs_with_reply_list(self):
        h = hook_of("yes")
        ctx = make_ctx(h, fact="user_explicitly_confirmed_pending_action", tool="cancel_pending_order",
                       args={"order_id": "#W0000001", "reason": "no longer needed"})
        cands = [["I will cancel order #W0000001. Shall I?", ["hmm", "Sounds right, please do both."]]]
        self.assertTrue(Q4.h_ask_first_yes_v4(ctx, "K1", cands, limit=2))
        rec_input = h.store.get(h.ask_lines[0]["key"])["input"]
        self.assertEqual(rec_input["action"], "cancel the pending order #w0000001")
        self.assertEqual(len(rec_input["replies"]), 2)

    def test_no_yes_false_and_limit(self):
        h = hook_of("no")
        self.assertFalse(Q4.h_ask_first_yes_v4(make_ctx(h), "K13", ["a", "bb", "cc"], limit=2, on_unclear=True))
        self.assertEqual(h.backend.calls, 2)
        self.assertFalse(Q4.h_ask_first_yes_v4(make_ctx(h), "K13", [], on_unclear=True))
        with self.assertRaises(TypeError):
            Q4.h_ask_first_yes_v4(make_ctx(h), "K13", "not a list", on_unclear=True)

    def test_items_and_follows(self):
        h = hook_of("yes")
        ctx = make_ctx(h, args={"order_id": "#W1"})
        self.assertTrue(Q4.h_ask_first_yes_v4(ctx, "K3", ["Are these all the items?"], items="modified"))
        inp = h.store.get(h.ask_lines[-1]["key"])["input"]
        self.assertEqual((inp["items_action"], inp["verb"]), ("modified", "modify"))
        ctx = make_ctx(h, tool="cancel_pending_order", args={"order_id": "#W1", "reason": "ordered by mistake"})
        self.assertTrue(Q4.h_ask_first_yes_v4(ctx, "K18", ["I clicked buy by accident"], limit=4))
        inp = h.store.get(h.ask_lines[-1]["key"])["input"]
        self.assertEqual((inp["reason"], inp["gloss"]), ("ordered by mistake", "the order was placed by accident"))
        with self.assertRaises(ValueError):
            Q4.h_ask_first_yes_v4(make_ctx(h), "K8", ["x"], items="modified")

    def test_k17_not_yes_no(self):
        with self.assertRaises(ValueError):
            Q4.h_ask_v4(make_ctx(hook_of("added"), domain="airline"), "K17", "Yes.")

    def test_standin_hook_no_reask(self):
        h = Q4.StandInAnswers({"f": None})
        with self.assertRaises(F.UseBlockingValue):
            Q4.h_ask_first_yes_v4(make_ctx(h, fact="f", domain="airline"), "K8", ["my flight was cancelled"])
        self.assertEqual(h.stats.asks["K8"], 1)
        self.assertFalse(Q4.h_ask_first_yes_v4(make_ctx(h, fact="f"), "K4", ["me"], on_unclear=False))


class TestInsurance(unittest.TestCase):
    def test_first_decided_answer_wins(self):
        pol = by_text({"what does it cost": "not_said", "yes": "added"}, default="not_said")   # normalized text
        h = hook_of(pol)
        ctx = make_ctx(h, fact="booking_insurance_decision_established_and_matched", domain="airline")
        cands = ["what does it cost", ["Would you like travel insurance?", "Yes"]]
        self.assertTrue(Q4.h_insurance_stated_v4(ctx, cands, "yes"))
        self.assertFalse(Q4.h_insurance_stated_v4(make_ctx(h, domain="airline"), cands, "no"))

    def test_not_said_everywhere_false(self):
        h = hook_of("not_said")
        self.assertFalse(Q4.h_insurance_stated_v4(make_ctx(h, domain="airline"), ["hm", "ok"], "no"))
        self.assertEqual(h.stats.blocking["K17"], 0)

    def test_unclear_reask_then_next_candidate(self):
        h = hook_of(by_text({"maybe": "unclear", "skip": "not_added"}),
                    second=by_text({"maybe": "unclear", "skip": "not_added"}))
        self.assertTrue(Q4.h_insurance_stated_v4(make_ctx(h, domain="airline"), ["maybe later", "skip it"], "no"))
        self.assertEqual(h.stats.reasks["K17"], 1)
        h = hook_of("unclear", second="unclear")
        self.assertFalse(Q4.h_insurance_stated_v4(make_ctx(h, domain="airline"), ["maybe"], "yes"))
        self.assertEqual(h.stats.blocking["K17"], 1)

    def test_bad_value(self):
        h = hook_of("added")
        self.assertFalse(Q4.h_insurance_stated_v4(make_ctx(h, domain="airline"), ["Yes"], None))
        self.assertEqual(h.backend.calls, 0)


class TestOffer(unittest.TestCase):
    def test_kind_from_database_without_call(self):
        h = hook_of("yes")
        ctx = make_ctx(h, domain="airline")
        self.assertTrue(Q4.h_offer_kind_v4(ctx, "I can offer a certificate.", "cancelled", ["cancelled"]))
        self.assertFalse(Q4.h_offer_kind_v4(ctx, "I can offer a certificate.", "delayed", {"cancelled": True,
                                                                                          "delayed": False}))
        self.assertEqual(h.backend.calls, 0)

    def test_kind_both_by_quote_words_else_true(self):
        h = hook_of("yes")      # the fake quotes the first 8 words of the reply
        r = "For the cancelled flight I can send a $100 certificate."
        self.assertTrue(Q4.h_offer_kind_v4(make_ctx(h, domain="airline"), r, "cancelled", ["cancelled", "delayed"]))
        self.assertFalse(Q4.h_offer_kind_v4(make_ctx(h, domain="airline"), r, "delayed", []))
        r2 = "Sorry about that. I can send you a certificate now."
        self.assertTrue(Q4.h_offer_kind_v4(make_ctx(h, domain="airline"), r2, "delayed", None))
        h = hook_of("no")
        self.assertFalse(Q4.h_offer_kind_v4(make_ctx(h, domain="airline"), r2, "delayed", None))
        h = hook_of("unclear", second="unclear")
        with self.assertRaises(F.UseBlockingValue):
            Q4.h_offer_kind_v4(make_ctx(h, domain="airline"), r2, "delayed", None)

    def test_amounts_from_offer_sentences(self):
        ctx = make_ctx(hook_of("yes"), domain="airline")
        ok = Q4.h_offer_amount_ok_v4
        self.assertTrue(ok(ctx, "As a gesture, I can send you a $200 certificate.", 100, [2]))
        self.assertFalse(ok(ctx, "As a gesture, I can send you a $150 certificate.", 100, [2]))
        self.assertTrue(ok(ctx, "I can issue a $100 voucher per passenger.", 100, [3]))
        self.assertTrue(ok(ctx, "The refund of $640 goes to your credit card in 5 days.", 100, [2]))
        self.assertFalse(ok(ctx, "Refund $640 to your credit card. Also a $640 certificate for you.", 100, [2]))
        self.assertTrue(ok(ctx, "We will refund $300. You also get compensation of $50 each.", 50, [4]))
        self.assertTrue(ok(ctx, "No amounts here.", 100, [1]))
        self.assertEqual(ctx.state.domain, "airline")


class TestActionLine(unittest.TestCase):
    def test_lines(self):
        st = State("retail", rows={("order", "#W1"): {"items": [{"item_id": "11", "name": "Desk Lamp",
                                                                 "options": {}}]}})
        self.assertEqual(Q4.action_line_v4(st, "return_delivered_order_items", {"order_id": "#W1", "item_ids": ["11"]}),
                         "return items of the delivered order #W1 (Desk Lamp)")
        st = State("airline")
        self.assertEqual(Q4.action_line_v4(st, "update_reservation_flights",
                                           {"reservation_id": "ABC123", "flights": [{"flight_number": "HAT001"}]}),
                         "change the flights of the reservation ABC123 (flights HAT001)")


if __name__ == "__main__":
    unittest.main()
