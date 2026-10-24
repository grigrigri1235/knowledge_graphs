"""Tracker v4, K1 rebuild: the go-ahead helpers (state_tracker/v4/helpers_go_ahead_v4.py) and the A2 fact overlays
(output/eval_v4/overlays/facts_A2_<domain>.json). Made-up conversations over the v1 database, with τ-bench's own
tool outputs (tests.test_v3_message_view.build). The K1 / K17 questions are doubles: no LLM call, no network.

Run from predicate_correctness/:
    PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v4_go_ahead
"""
from __future__ import annotations

import copy
import json
import os
import sys
import unittest

sys.dont_write_bytecode = True

from state_tracker import lookup_format as L                     # noqa: E402
from state_tracker import paths                                   # noqa: E402
from state_tracker import state as S                              # noqa: E402
from state_tracker.v3 import facts_format_v3 as F                # noqa: E402
from state_tracker.v4 import helpers_go_ahead_v4 as G            # noqa: E402
from tests.test_v3_message_view import Ctx, build                 # noqa: E402

OV_DIR = os.path.join(paths.OUTPUT_DIR, "eval_v4", "overlays")
V3_FACTS = {d: F.load_facts(d)["facts"] for d in paths.DOMAINS}
DB = {d: S.load_db(d) for d in paths.DOMAINS}

# retail fixtures (v1 database)
YUSUF = "yusuf_garcia_3055"           # paypal_7503218, credit_card_8405687 (mastercard 3762), gift_card_7588375
O1, O2 = "#W2286012", "#W4794911"     # both delivered, paid with paypal_7503218
TOOTHBRUSH, SPEAKER, PERFUME = "8098621301", "6455132774", "5421902839"
LAMP, TSHIRT = "9190635437", "9647292434"
YUSUF_MC = "credit_card_8405687"
YUSUF_PP = "paypal_7503218"
MEI_J = "mei_johansson_1199"          # credit_card_3945811 (visa, last four 4044); credit_card_7574044 (mc 7930)
MEI_J_ORDER = "#W5009508"
# airline fixtures
MEI_H = "mei_hernandez_8984"          # credit_card_2140654 (mastercard 1698), credit_card_6082923 (visa 3202), ...
RES = "R9QDGB"                        # passengers Mei Hernandez, Liam Kovacs, Anya Anderson


def ret(order, items, pm):
    return {"order_id": order, "item_ids": items, "payment_method_id": pm}


def ctx_of(domain, steps, pending):
    hist, st, view = build(domain, steps, pending)
    return Ctx(st, view)


class FakeAsk:
    """The double of questions_v4.ask_first_yes_v4: records each call, answers a fixed value."""

    def __init__(self, value=True):
        self.value, self.calls = value, []

    def __call__(self, ctx, qid, candidates, **kw):
        self.calls.append((qid, [list(c) for c in candidates], kw))
        if self.value == "unclear":
            raise F.UseBlockingValue("unclear", kind="unclear")
        return self.value


class WithFakeAsk(unittest.TestCase):
    def setUp(self):
        self.ask = FakeAsk(True)
        G._ASK_OVERRIDE = self.ask

    def tearDown(self):
        G._ASK_OVERRIDE = None


# ----------------------------------------------------------------------------------------------- D8 fast path

class TestFastPath(unittest.TestCase):
    def test_plain_yes_forms(self):
        for t in ("Yes.", "yes", "YES!", "Yes, please.", "Please proceed.", "please proceed", "Yes, go ahead.",
                  "Yes please go ahead", "Thank you, yes.", "Ok so go ahead", "Sounds good, thanks!",
                  "That's correct.", "Yes, that's correct.", "Yes, I confirm.", "Confirmed", "Yep", "Sure.",
                  "Go ahead and proceed.", "Yes, book it.", "Yes, cancel it.", "Yes, submit it.", "Please do."):
            self.assertTrue(G.is_short_go_ahead_v4(t), t)

    def test_not_plain(self):
        for t in ("Yes?", "Yes, but use PayPal.", "yes but use paypal", "Wait.", "Wait, yes.", "Yes, wait",
                  "Not yet", "Yes, only the first one.", "Yes, change the address too.", "yes instead",
                  "Yes, please go ahead with both returns.", "Please submit the returns for all four items.",
                  "Okay, I need to think about it.", "Sure, let me check with my wife first.", "", None,
                  "Before you do it, what is the refund amount?", "Yes yes yes yes yes yes yes yes yes"):
            self.assertFalse(G.is_short_go_ahead_v4(t), t)

    def test_every_phrase_passes_the_belt_rule(self):
        for ph in G.FAST_PATH_PHRASES:
            self.assertLessEqual(len(ph.split()), G.MAX_FAST_WORDS, ph)
            self.assertIsNone(G._EXCLUDED_WORDS.search(ph), ph)
            self.assertTrue(G.is_short_go_ahead_v4(ph.capitalize() + "."), ph)

    def test_helper_on_a_ref(self):
        c = ctx_of("retail", [("agent", f"Shall I return the Perfume of order {O1}?"), ("user", "Yes, please.")],
                   {"tool": "return_delivered_order_items", "args": ret(O1, [PERFUME], YUSUF_PP)})
        self.assertTrue(G.short_go_ahead_v4(c, 1))
        self.assertFalse(G.short_go_ahead_v4(c, 0))


# ----------------------------------------------------------------------------------------------- D2 / D3 / D4

LISTING_4 = (f"Here is what I will do: return the Electric Toothbrush and the Perfume from order {O1}, and the "
             f"Desk Lamp and the T-Shirt from order {O2}. The refunds go to your PayPal account. Shall I go ahead?")


class TestBatch(WithFakeAsk):
    """One go-ahead for a listed batch across two orders (retail/92 pattern: 'please submit the returns')."""

    def steps(self, reply):
        return [("user", "I want to return four items."), ("agent", LISTING_4), ("user", reply)]

    def test_first_write_of_the_batch(self):
        c = ctx_of("retail", self.steps("Please submit the returns for all four items."),
                   {"tool": "return_delivered_order_items", "args": ret(O1, [TOOTHBRUSH, PERFUME], YUSUF_PP)})
        self.assertEqual(G.go_ahead_anchors_v4(c), [1])
        self.assertEqual(G.own_anchors_v4(c), [1])
        self.assertEqual(G.go_ahead_candidates_v4(c), [[1, [2]]])
        self.assertTrue(G.clash_free_v4(c))
        self.assertTrue(G.go_ahead_yes_v4(c))
        self.assertEqual(self.ask.calls, [("K1", [[1, [2]]], {"limit": 2})])

    def test_second_write_same_listing_after_a_worked_batch_member(self):
        steps = self.steps("Please submit the returns for all four items.") + [
            ("call", "return_delivered_order_items", ret(O1, [TOOTHBRUSH, PERFUME], YUSUF_PP))]
        c = ctx_of("retail", steps,
                   {"tool": "return_delivered_order_items", "args": ret(O2, [LAMP, TSHIRT], YUSUF_PP)})
        self.assertEqual(G.span_start_v4(c), -1)          # the worked return has no user message after it
        self.assertEqual(G.go_ahead_candidates_v4(c), [[1, [2]]])
        self.assertTrue(G.clash_free_v4(c))
        self.assertTrue(G.go_ahead_yes_v4(c))
        self.assertEqual(self.ask.calls[0][1], [[1, [2]]])

    def test_a_worked_write_with_a_user_message_after_it_starts_a_new_span(self):
        steps = self.steps("Please submit the returns for all four items.") + [
            ("call", "return_delivered_order_items", ret(O1, [TOOTHBRUSH, PERFUME], YUSUF_PP)),
            ("agent", "The first return is done."), ("user", "Great, thanks.")]
        c = ctx_of("retail", steps,
                   {"tool": "return_delivered_order_items", "args": ret(O2, [LAMP, TSHIRT], YUSUF_PP)})
        self.assertEqual(G.go_ahead_anchors_v4(c), [])     # the listing is before the span
        self.assertEqual(G.go_ahead_candidates_v4(c), [])
        self.assertFalse(G.go_ahead_yes_v4(c))
        self.assertEqual(self.ask.calls, [])


class TestWindow(WithFakeAsk):
    def test_please_proceed_without_a_typed_yes_takes_the_fast_path(self):
        c = ctx_of("retail", [("agent", f"I will return the Perfume from order {O1} to your PayPal. Confirm?"),
                              ("user", "Please proceed.")],
                   {"tool": "return_delivered_order_items", "args": ret(O1, [PERFUME], YUSUF_PP)})
        self.assertTrue(G.go_ahead_yes_v4(c))
        self.assertEqual(self.ask.calls, [])               # no question asked
        self.assertIn({"fast_path": True, "question": "K1", "message": 1, "anchor": 0, "text": "Please proceed."},
                      c.notes)

    def test_every_user_message_after_the_listing_is_in_B(self):
        steps = [("agent", f"I will return the Perfume from order {O1} to your PayPal. Shall I proceed?"),
                 ("user", "Hmm, one moment."), ("agent", "Sure, take your time."), ("user", "Okay, go for it then.")]
        c = ctx_of("retail", steps, {"tool": "return_delivered_order_items", "args": ret(O1, [PERFUME], YUSUF_PP)})
        self.assertEqual(G.go_ahead_candidates_v4(c), [[0, [1, 3]]])
        self.assertTrue(G.go_ahead_yes_v4(c))
        self.assertEqual(self.ask.calls[0][1], [[0, [1, 3]]])

    def test_question_back_is_asked_and_the_answer_decides(self):
        self.ask.value = False
        c = ctx_of("retail", [("agent", f"I will return the Perfume from order {O1} to your PayPal. OK?"),
                              ("user", "Before you do it, what is the refund amount?")],
                   {"tool": "return_delivered_order_items", "args": ret(O1, [PERFUME], YUSUF_PP)})
        self.assertFalse(G.go_ahead_yes_v4(c))
        self.assertEqual(len(self.ask.calls), 1)

    def test_unclear_goes_up(self):
        self.ask.value = "unclear"
        c = ctx_of("retail", [("agent", f"Return the Perfume of {O1} to PayPal?"), ("user", "Hmm, I guess so?")],
                   {"tool": "return_delivered_order_items", "args": ret(O1, [PERFUME], YUSUF_PP)})
        with self.assertRaises(F.UseBlockingValue):
            G.go_ahead_yes_v4(c)

    def test_strict_no_drops_the_candidate_without_a_call(self):
        c = ctx_of("retail", [("agent", f"I will return the Perfume from order {O1} to your PayPal. OK?"),
                              ("user", "No, wait.")],
                   {"tool": "return_delivered_order_items", "args": ret(O1, [PERFUME], YUSUF_PP)})
        self.assertEqual(G.go_ahead_anchors_v4(c), [0])
        self.assertEqual(G.go_ahead_candidates_v4(c), [])
        self.assertFalse(G.go_ahead_yes_v4(c))
        self.assertEqual(self.ask.calls, [])

    def test_no_thats_all_is_not_a_strict_no(self):
        c = ctx_of("retail", [("agent", f"I will return the Perfume from order {O1}. Anything else first?"),
                              ("user", "No, that's all. Go ahead.")],
                   {"tool": "return_delivered_order_items", "args": ret(O1, [PERFUME], YUSUF_PP)})
        self.assertEqual(G.go_ahead_candidates_v4(c), [[0, [1]]])

    def test_an_agent_message_without_a_detail_is_not_an_anchor(self):
        c = ctx_of("retail", [("agent", "How can I help you today?"), ("user", "Yes.")],
                   {"tool": "return_delivered_order_items", "args": ret(O1, [PERFUME], YUSUF_PP)})
        self.assertEqual(G.go_ahead_anchors_v4(c), [])
        self.assertFalse(G.go_ahead_yes_v4(c))

    def test_at_most_two_anchors_newest_first(self):
        steps = [("agent", f"Order {O1} has a Perfume."), ("user", "ok"), ("agent", f"Return the Perfume of {O1}?"),
                 ("user", "hm"), ("agent", f"So: return the Perfume of {O1} to PayPal?"), ("user", "Yes.")]
        c = ctx_of("retail", steps, {"tool": "return_delivered_order_items", "args": ret(O1, [PERFUME], YUSUF_PP)})
        self.assertEqual(G.go_ahead_anchors_v4(c), [4, 2])
        self.assertEqual(G.own_anchors_v4(c), [4, 2])      # the fallback agrees with A1's listing_anchors_v4


# ----------------------------------------------------------------------------------------------- clashes

class TestClash(WithFakeAsk):
    def test_yes_but_use_paypal_is_a_clash(self):
        c = ctx_of("retail", [("agent", f"I will return the Perfume of {O1} and refund your Mastercard ending 3762."),
                              ("user", "Yes, but use PayPal.")],
                   {"tool": "return_delivered_order_items", "args": ret(O1, [PERFUME], YUSUF_MC)})
        self.assertFalse(G.clash_free_v4(c))
        note = [n for n in c.notes if n.get("clash")][0]
        self.assertEqual((note["clash"], note["named"], note["call"]), ("payment", [YUSUF_PP], [YUSUF_MC]))
        self.assertEqual(G.go_ahead_candidates_v4(c, focus="payment"), [])

    def test_negated_other_method_is_no_clash(self):
        c = ctx_of("retail", [("agent", f"Refund the Perfume of {O1} to your Mastercard?"),
                              ("user", "Yes, to the Mastercard, not PayPal.")],
                   {"tool": "return_delivered_order_items", "args": ret(O1, [PERFUME], YUSUF_MC)})
        self.assertTrue(G.clash_free_v4(c))

    def test_switch_from_one_method_to_the_call_method_is_no_clash(self):
        c = ctx_of("retail", [("agent", f"Refund the Perfume of {O1} to your Mastercard?"),
                              ("user", "Yes, the gift card and the Mastercard both work, use the Mastercard.")],
                   {"tool": "return_delivered_order_items", "args": ret(O1, [PERFUME], YUSUF_MC)})
        self.assertTrue(G.clash_free_v4(c))

    def test_the_detail_stated_by_the_user_by_id_digits(self):
        """'the card ending in 5687' = credit_card_8405687 (its last four is 3762): a match, not a clash."""
        c = ctx_of("retail", [("agent", f"I can return the Perfume of {O1}. Where should the refund go?"),
                              ("user", "Refund it to the credit card ending in 5687, please go ahead.")],
                   {"tool": "return_delivered_order_items", "args": ret(O1, [PERFUME], YUSUF_MC)})
        self.assertTrue(G.clash_free_v4(c))
        self.assertEqual(G.go_ahead_candidates_v4(c, focus="payment"), [[0, [1]]])

    def test_the_original_payment_method(self):
        pend = {"tool": "return_delivered_order_items", "args": ret(O1, [PERFUME], YUSUF_PP)}
        c = ctx_of("retail", [("agent", f"Return the Perfume of {O1}?"),
                              ("user", "Yes, to the original payment method.")], pend)
        self.assertEqual(G.go_ahead_candidates_v4(c, focus="payment"), [[0, [1]]])
        pend_mc = {"tool": "return_delivered_order_items", "args": ret(O1, [PERFUME], YUSUF_MC)}
        c = ctx_of("retail", [("agent", f"Return the Perfume of {O1} to the Mastercard?"),
                              ("user", "Yes, but to the original payment method.")], pend_mc)
        self.assertFalse(G.clash_free_v4(c))                # the original is PayPal

    def test_yes_to_a_different_item_is_a_clash(self):
        c = ctx_of("retail", [("agent", f"Shall I return the Perfume of order {O1} to PayPal?"),
                              ("user", "Yes, return the Bluetooth Speaker.")],
                   {"tool": "return_delivered_order_items", "args": ret(O1, [PERFUME], YUSUF_PP)})
        self.assertFalse(G.clash_free_v4(c))
        self.assertEqual([n for n in c.notes if n.get("clash")][0]["named"], [SPEAKER])

    def test_naming_the_call_item_and_keeping_another_is_no_clash(self):
        c = ctx_of("retail", [("agent", f"Shall I return the Perfume of order {O1} to PayPal?"),
                              ("user", "Yes, return the Perfume and keep the Bluetooth Speaker.")],
                   {"tool": "return_delivered_order_items", "args": ret(O1, [PERFUME], YUSUF_PP)})
        self.assertTrue(G.clash_free_v4(c))

    def test_yes_to_a_different_action_goes_to_K1(self):
        """L proposes an exchange; the call is a return of the same order: code sees no clash, K1 decides."""
        self.ask.value = False
        c = ctx_of("retail", [("agent", f"I can exchange the Perfume of order {O1} for a larger bottle. OK?"),
                              ("user", "Yes, I'd like the exchange.")],
                   {"tool": "return_delivered_order_items", "args": ret(O1, [PERFUME], YUSUF_PP)})
        self.assertTrue(G.clash_free_v4(c))
        self.assertFalse(G.go_ahead_yes_v4(c))
        self.assertEqual(len(self.ask.calls), 1)

    def test_ambiguous_4044_is_neither_a_match_nor_a_clash(self):
        """mei_johansson_1199: '4044' is the Visa's last four AND the Mastercard's id ending."""
        pend = {"tool": "modify_pending_order_payment",
                "args": {"order_id": MEI_J_ORDER, "payment_method_id": "credit_card_7574044"}}
        c = ctx_of("retail", [("agent", f"Which card should order {MEI_J_ORDER} use?"),
                              ("user", "The card ending in 4044, please go ahead.")], pend)
        self.assertTrue(G.clash_free_v4(c))
        self.assertEqual(G.go_ahead_candidates_v4(c, focus="payment"), [])
        c = ctx_of("retail", [("agent", f"Which card should order {MEI_J_ORDER} use?"),
                              ("user", "The Visa ending in 4044, please.")], pend)
        self.assertFalse(G.clash_free_v4(c))                # the brand picks the Visa: another card
        c = ctx_of("retail", [("agent", f"Which card should order {MEI_J_ORDER} use?"),
                              ("user", "The Mastercard ending in 4044, please.")], pend)
        self.assertTrue(G.clash_free_v4(c))
        self.assertEqual(G.go_ahead_candidates_v4(c, focus="payment"), [[0, [1]]])

    def test_option_whole_value_gold_vs_rose_gold(self):
        found = None
        for oid, o in DB["retail"]["orders"].items():
            if o["status"] != "pending":
                continue
            for it in o["items"]:
                if it["name"] == "Smartphone":
                    found = (oid, it)
                    break
            if found:
                break
        self.assertIsNotNone(found)
        oid, it = found
        prod = DB["retail"]["products"][it["product_id"]]
        gold = [iid for iid, v in prod["variants"].items() if v["options"]["color"] == "gold"
                and it["options"]["color"] != "gold"]
        self.assertTrue(gold)
        u = DB["retail"]["users"][DB["retail"]["orders"][oid]["user_id"]]
        pm = next(iter(u["payment_methods"]))
        pend = {"tool": "modify_pending_order_items",
                "args": {"order_id": oid, "item_ids": [it["item_id"]], "new_item_ids": [gold[0]],
                         "payment_method_id": pm}}
        listing = f"I will change the Smartphone of order {oid} to the gold color. Shall I proceed?"
        c = ctx_of("retail", [("agent", listing), ("user", "Yes, but in rose gold.")], pend)
        self.assertFalse(G.clash_free_v4(c))
        note = [n for n in c.notes if n.get("clash")][0]
        self.assertEqual((note["clash"], note["named"]), ("option", ["rose gold"]))
        c = ctx_of("retail", [("agent", listing), ("user", "Yes, the gold one is right.")], pend)
        self.assertTrue(G.clash_free_v4(c))

    def test_address_clash_by_zip(self):
        args = {"order_id": O1, "address1": "1 Elm Street", "address2": "Suite 2", "city": "Austin",
                "state": "TX", "country": "USA", "zip": "78701"}
        c = ctx_of("retail", [("agent", f"Change the address of {O1} to 1 Elm Street, Suite 2, Austin TX 78701?"),
                              ("user", "Yes, but the zip is 78702.")],
                   {"tool": "modify_pending_order_address", "args": args})
        self.assertFalse(G.clash_free_v4(c))
        c = ctx_of("retail", [("agent", f"Change the address of {O1} to 1 Elm Street, Austin TX 78701?"),
                              ("user", "Yes, 78701 is right.")],
                   {"tool": "modify_pending_order_address", "args": args})
        self.assertTrue(G.clash_free_v4(c))


class TestAirline(WithFakeAsk):
    def flights_call(self, pid):
        fl = [{"flight_number": "HAT034", "date": "2024-05-28"}, {"flight_number": "HAT026", "date": "2024-05-28"},
              {"flight_number": "HAT247", "date": "2024-05-30"}, {"flight_number": "HAT232", "date": "2024-05-30"}]
        return {"tool": "update_reservation_flights",
                "args": {"reservation_id": RES, "cabin": "business", "flights": fl, "payment_id": pid}}

    def test_brand_next_to_the_digits_must_match(self):
        pend = self.flights_call("credit_card_2140654")        # mastercard, last four 1698
        steps = [("user", f"I am {MEI_H}."), ("agent", f"I will upgrade reservation {RES} to business. Card?")]
        c = ctx_of("airline", steps + [("user", "Yes, use my Visa ending 1698.")], pend)
        self.assertFalse(G.clash_free_v4(c))
        c = ctx_of("airline", steps + [("user", "Yes, the Mastercard ending in 1698.")], pend)
        self.assertTrue(G.clash_free_v4(c))
        self.assertEqual(G.go_ahead_candidates_v4(c, focus="payment"), [[1, [2]]])

    def test_same_brand_cards_brand_alone_is_ambiguous(self):
        uid = pm_a = pm_b = None
        for u_id, u in DB["airline"]["users"].items():
            cards = [m for m in u["payment_methods"].values() if m["source"] == "credit_card"]
            visas = [m for m in cards if m["brand"] == "visa"]
            if len(visas) >= 2 and u["reservations"] and not any(m["source"] == "gift_card"
                                                                    for m in u["payment_methods"].values()):
                uid, pm_a, pm_b = u_id, visas[0]["id"], visas[1]["id"]
                break
        self.assertIsNotNone(uid)
        rid = DB["airline"]["users"][uid]["reservations"][0]
        pend = {"tool": "update_reservation_baggages",
                "args": {"reservation_id": rid, "total_baggages": 3, "nonfree_baggages": 1, "payment_id": pm_a}}
        steps = [("user", f"I am {uid}."), ("agent", f"I will set reservation {rid} to 3 bags. Which card?")]
        c = ctx_of("airline", steps + [("user", "Yes, my Visa.")], pend)
        self.assertTrue(G.clash_free_v4(c))                 # "my Visa" fits two cards: no clash ...
        self.assertEqual(G.go_ahead_candidates_v4(c, focus="payment"), [])   # ... and no match
        lf_b = DB["airline"]["users"][uid]["payment_methods"][pm_b]["last_four"]
        c = ctx_of("airline", steps + [("user", f"Yes, the Visa ending in {lf_b}.")], pend)
        self.assertFalse(G.clash_free_v4(c))                # the digits pick the other Visa

    def test_passenger_clash(self):
        pend = {"tool": "update_reservation_passengers",
                "args": {"reservation_id": RES, "passengers": [
                    {"first_name": "Mei", "last_name": "Hernandez", "dob": "1981-01-11"},
                    {"first_name": "Liam", "last_name": "Garcia", "dob": "1996-08-21"},
                    {"first_name": "Anya", "last_name": "Anderson", "dob": "1959-05-28"}]}}
        steps = [("user", f"I am {MEI_H}."),
                 ("agent", f"In reservation {RES} I will change Liam Kovacs to Liam Garcia. Proceed?")]
        c = ctx_of("airline", steps + [("user", "Yes, change Liam Kovacs to Liam Garcia.")], pend)
        self.assertTrue(G.clash_free_v4(c))
        self.assertTrue(G.go_ahead_yes_v4(c))
        c = ctx_of("airline", steps + [("user", "Yes, and it is Anya Anderson I meant, not Liam Kovacs.")], pend)
        self.assertTrue(G.clash_free_v4(c))                 # Anya is in the call too
        pend2 = copy.deepcopy(pend)
        pend2["args"]["passengers"] = pend2["args"]["passengers"][:2]
        c = ctx_of("airline", steps + [("user", "Yes, and change Anya Anderson as well.")], pend2)
        self.assertFalse(G.clash_free_v4(c))

    def test_insurance_candidates(self):
        steps = [("user", f"I am {MEI_H}, book a flight from LAX to SFO."),
                 ("agent", "Would you like travel insurance for $30 per passenger?"), ("user", "No thanks."),
                 ("agent", "Booking HAT034 on May 28, economy, Visa ending 3202. Shall I book?"),
                 ("user", "Yes. Actually, add the insurance after all.")]
        pend = {"tool": "book_reservation", "args": {"user_id": MEI_H, "insurance": "yes"}}
        c = ctx_of("airline", steps, pend)
        self.assertEqual(G.insurance_candidates_v4(c), [[4], [1, 2]])
        c = ctx_of("airline", steps[:4] + [("user", "Yes.")], pend)
        self.assertEqual(G.insurance_candidates_v4(c), [[1, 2]])


# ----------------------------------------------------------------------------------------------- overlays

def load_overlay(domain):
    with open(os.path.join(OV_DIR, f"facts_A2_{domain}.json"), encoding="utf-8") as f:
        return json.load(f)


def merged(domain, fact):
    e = copy.deepcopy(V3_FACTS[domain][fact])
    ov = load_overlay(domain)["facts"][fact]
    for pid, p in ov["parts"].items():
        if p is None:
            e["parts"].pop(pid, None)
        else:
            e["parts"][pid] = p
    for k in ("combine", "sources"):
        if k in ov:
            e[k] = ov[k]
    return e


class Hook:
    stats = None
    doc = None
    exhaustive = False

    def ask(self, *a, **k):
        raise AssertionError("no direct ask in these tests")


def _swap(name, func):
    """Put a double under a registered helper name (same limits and source); returns the old Helper."""
    old = F.registered_names()[name]
    F.unregister_name(name)
    F.register_name(name, func, old.min_args, old.max_args, old.keywords, source=old.source, doc="test double (A2)")
    return old


def _restore(old):
    F.unregister_name(old.name)
    F.register_name(old.name, old.func, old.min_args, old.max_args, old.keywords, source=old.source, doc=old.doc)


class TestOverlays(unittest.TestCase):
    """The overlay expressions, evaluated by the v3 evaluator, with doubles for A3's question helpers."""

    @classmethod
    def setUpClass(cls):
        import state_tracker.v4.questions_v4  # noqa: F401  (A3: registers ask_first_yes_v4, insurance_stated_v4)
        cls.ask = FakeAsk(True)
        cls.ins = []

        def insurance(ctx, candidates, value):
            cls.ins.append((list(candidates), value))
            return True
        cls.old = [_swap("ask_first_yes_v4", cls.ask), _swap("insurance_stated_v4", insurance)]

    @classmethod
    def tearDownClass(cls):
        for old in cls.old:
            _restore(old)

    def setUp(self):
        self.ask.value, self.ask.calls[:] = True, []
        self.ins[:] = []

    def test_shape_owner_and_facts(self):
        want = {"retail": {"user_explicitly_confirmed_pending_action", "user_confirmed_cancellation_order_and_reason",
                           "user_confirmed_return_order_items_and_method", "user_chose_pending_payment_method",
                           "user_chose_price_difference_payment_method"},
                "airline": {"pending_database_change_details_listed_and_explicitly_confirmed",
                            "booking_insurance_decision_established_and_matched",
                            "user_selected_eligible_flight_change_payment_method"}}
        for d in paths.DOMAINS:
            ov = load_overlay(d)
            self.assertEqual((ov["domain"], ov["by"]), (d, "A2"))
            self.assertEqual(set(ov["facts"]), want[d])
            for f, fo in ov["facts"].items():
                self.assertIn(f, V3_FACTS[d])
                self.assertLessEqual(set(fo), {"combine", "sources", "parts"})

    def test_airline_part_c_is_left_to_A1(self):
        ov = load_overlay("airline")["facts"]["pending_database_change_details_listed_and_explicitly_confirmed"]
        self.assertNotIn("c", ov["parts"])
        self.assertEqual(ov["combine"], "a AND b AND c AND e AND d")

    def test_no_A5_overlap(self):
        for d in paths.DOMAINS:
            p = os.path.join(OV_DIR, f"facts_A5_{d}.json")
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    other = set(json.load(f)["facts"])
                self.assertEqual(other & set(load_overlay(d)["facts"]), set(), d)

    def test_every_part_validates_and_calls_only_v4_helpers(self):
        v3_q = {"ask", "ask_first_yes", "offer_kind", "offer_amount_ok"}
        for d in paths.DOMAINS:
            kinds = L.domain_kinds(d)
            for f, fo in load_overlay(d)["facts"].items():
                e = merged(d, f)
                ids = F.combine_ids(F.parse_combine(e["combine"]))
                self.assertLessEqual(set(ids), set(e["parts"]), (d, f))
                for pid, p in fo["parts"].items():
                    self.assertEqual(F.validate_part(f, pid, p, e["sources"], kinds, ()), [], (d, f, pid))
                    info = F.validate_expr(p["expr"], kinds)
                    self.assertFalse(set(info["helpers"]) & v3_q, (d, f, pid))
                    if p["source"] == "question" and p["question"] == "K1":
                        self.assertTrue(p["expr"].startswith("go_ahead_fast_v4("), (d, f, pid))
                        self.assertIn("ask_first_yes_v4('K1', go_ahead_candidates_v4(", p["expr"])

    def test_feedback_reads_the_part_kinds(self):
        try:
            from guard import feedback_v4 as FB
        except ImportError:
            self.skipTest("guard/feedback_v4.py (A7) not there")
        r = load_overlay("retail")["facts"]
        k = FB.part_kind(r["user_explicitly_confirmed_pending_action"]["parts"]["b"]["expr"])
        self.assertEqual((k["kind"], k["qid"]), ("go_ahead", "K1"))
        k = FB.part_kind(r["user_chose_pending_payment_method"]["parts"]["c"]["expr"])
        self.assertEqual(k["kind"], "ask_payment")
        self.assertEqual(FB.part_kind(r["user_explicitly_confirmed_pending_action"]["parts"]["c"]["expr"])["kind"],
                         "clash")

    def ev(self, domain, fact, steps, pending, combine=None):
        hist, st, view = build(domain, steps, pending)
        e = merged(domain, fact)
        if combine:
            e["combine"] = combine
        return F.evaluate(e, st, None, view=view, answers=Hook(), name=fact)

    def test_retail_confirmation_fact_end_to_end(self):
        pend = {"tool": "return_delivered_order_items", "args": ret(O1, [PERFUME], YUSUF_PP)}
        f = "user_confirmed_return_order_items_and_method"
        listing = f"I will return the Perfume from order {O1} to your PayPal. Shall I proceed?"
        r = self.ev("retail", f, [("agent", listing), ("user", "Yes, please.")], pend)
        self.assertIs(r["value"], True)
        self.assertEqual(self.ask.calls, [])                # fast path: no question
        self.assertTrue(any(isinstance(n, dict) and n.get("fast_path") for n in r["parts"]["b"]["notes"]))
        r = self.ev("retail", f, [("agent", listing), ("user", "Yes, but use my Mastercard.")], pend)
        self.assertIs(r["value"], False)
        self.assertIs(r["parts"]["c"]["value"], False)
        self.assertEqual(self.ask.calls, [])                # clash: no question
        r = self.ev("retail", f, [("agent", listing), ("user", "That sounds right, please submit it.")], pend)
        self.assertIs(r["value"], True)
        self.assertEqual(self.ask.calls, [("K1", [[0, [1]]], {"limit": 2})])
        self.ask.value = False
        r = self.ev("retail", f, [("agent", listing), ("user", "Hmm, what would the refund be?")], pend)
        self.assertIs(r["value"], False)

    def test_retail_payment_fact_shares_the_candidates(self):
        pend = {"tool": "return_delivered_order_items", "args": ret(O1, [PERFUME], YUSUF_MC)}
        f = "user_chose_price_difference_payment_method"
        self.assertEqual(merged("retail", f)["combine"], V3_FACTS["retail"][f]["combine"])
        steps = [("agent", f"I can return the Perfume of {O1}. Where should the refund go?"),
                 ("user", "The credit card ending in 5687, go ahead and submit it.")]
        hist, st, view = build("retail", steps, pend)
        c = Ctx(st, view)
        self.assertEqual(G.go_ahead_candidates_v4(c, focus="payment"), G.go_ahead_candidates_v4(c))

    def test_airline_insurance_fact(self):
        pend = {"tool": "book_reservation", "args": {"user_id": MEI_H, "insurance": "no"}}
        f = "booking_insurance_decision_established_and_matched"
        steps = [("user", f"I am {MEI_H}."), ("agent", "Would you like travel insurance?"), ("user", "No thanks.")]
        r = self.ev("airline", f, steps, pend)
        self.assertIs(r["value"], True)
        self.assertEqual(self.ins, [([[1, 2]], "no")])
        r = self.ev("airline", f, [("user", f"I am {MEI_H}."), ("agent", "Shall I book?"), ("user", "Yes.")], pend)
        self.assertIs(r["value"], False)                    # no insurance message: part a false, K17 not asked
        self.assertEqual(len(self.ins), 1)

    def test_airline_change_fact_parts(self):
        pend = TestAirline().flights_call("credit_card_6082923")
        steps = [("user", f"I am {MEI_H}."),
                 ("agent", f"I will upgrade reservation {RES} to business, paid with your Visa ending 3202. OK?"),
                 ("user", "Yes, go ahead.")]
        f = "pending_database_change_details_listed_and_explicitly_confirmed"
        r = self.ev("airline", f, steps, pend, combine="a AND b AND e AND d")
        self.assertIs(r["value"], True)
        self.assertEqual(self.ask.calls, [])
        r = self.ev("airline", f, steps[:2] + [("user", "Wait, not yet.")], pend, combine="a AND b AND e AND d")
        self.assertIs(r["value"], False)
        self.assertIs(r["parts"]["a"]["value"], True)
        self.assertIs(r["parts"]["b"]["value"], False)
        self.assertEqual(self.ask.calls, [])

    def test_registered_names(self):
        reg = F.registered_names()
        funcs = {h[0]: h[1] for h in G.HELPERS}
        for n in G.NAMES:
            self.assertTrue(n.endswith("_v4"))
            self.assertIs(reg[n].func, funcs[n])
            self.assertEqual(reg[n].source, "structure")


class TestWithRealA3(unittest.TestCase):
    """A3's real ask_first_yes_v4 on the K1 candidates, with A4's K1 text and a hook that answers by rule."""

    def setUp(self):
        from state_tracker.v4 import questions_v4 as Q4
        with open(os.path.join(OV_DIR, "questions_A4.json"), encoding="utf-8") as f:
            ov = json.load(f)
        doc = {"systems": ov.get("system_v2") or {"2": {}}, "questions": ov["questions"],
               "domain_texts": ov.get("domain_texts") or {}}
        norm = getattr(Q4, "normalize_doc_v4", None)
        try:
            doc = norm(doc) if norm else doc
        except Exception:                                   # noqa: BLE001  (shape of a merged file only)
            pass
        self.Q4 = Q4
        test = self

        class RuleHook:
            stats = None
            exhaustive = False

            def __init__(self):
                self.doc, self.inputs = doc, []

            def ask(self, qid, inputs, *, fact=None, part=None, wording=1):
                self.inputs.append((qid, inputs, wording))
                yes = any("submit" in t.lower() for t in inputs.get("replies", []))
                return {"status": "yes" if yes else "no", "key": "k" * 16, "quote": "submit" if yes else ""}
        self.hook = RuleHook()
        test.doc = doc

    def test_candidate_shape_fits_K1_inputs(self):
        pend = {"tool": "return_delivered_order_items", "args": ret(O1, [PERFUME], YUSUF_PP)}
        hist, st, view = build("retail", [("agent", f"I will return the Perfume from order {O1}. OK?"),
                                          ("user", "Hmm, one second."), ("user", "Okay, please submit it.")], pend)
        e = merged("retail", "user_confirmed_return_order_items_and_method")
        r = F.evaluate(e, st, None, view=view, answers=self.hook, name="user_confirmed_return_order_items_and_method")
        self.assertIs(r["value"], True, r)
        qid, inputs, wording = self.hook.inputs[0]
        self.assertEqual(qid, "K1")
        self.assertEqual(inputs["replies"], ["Hmm, one second.", "Okay, please submit it."])
        self.assertIn("Perfume", inputs["listing"])
        self.assertIn(O1, inputs["action"])


if __name__ == "__main__":
    unittest.main()
