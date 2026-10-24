"""Tracker v4: the K2 line checks as code (state_tracker/v4/listing_v4.py).

Made-up listings (written from the v1 policy text only) for every write tool of both domains, on the v1 database:
each accepted form passes, each missing line is reported with its expected value, the detail one message earlier
counts (D6), the user's own words count, stray digits do not count, unchanged flights / passengers need no line, and
the DB-only form-check traps (output/eval_v4/form_check.md) hold. No LLM call, no network.

Run from predicate_correctness/:  ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v4_listing
"""
from __future__ import annotations

import copy
import json
import os
import sys
import unittest

sys.dont_write_bytecode = True

from state_tracker import lookup_format as L                 # noqa: E402
from state_tracker import paths                               # noqa: E402
from state_tracker.v3 import facts_format_v3 as F            # noqa: E402
from state_tracker.v4 import listing_v4 as LV                # noqa: E402
from tests.test_v3_message_view import Ctx, build            # noqa: E402

# retail (v1 data)
OLIVIA = "olivia_ito_3591"        # gift_card_7794233 ($56), paypal_8049766, credit_card_9753331 (visa 9182)
ORDER = "#W5442520"               # pending: Gaming Mouse 3330317167, Patio Umbrella 3111466194, Hiking Boots 2648909398
ORDER2 = "#W7941031"              # pending, Olivia
DELIVERED = "#W5866402"           # delivered, Olivia: Espresso Machine 6242772310, Sneakers 9727387530; paid by PayPal
MEI_ORDER = "#W5009508"           # mei_johansson_1199: visa 3945811 last four 4044, mastercard 7574044 last four 7930
BACKPACKS = "#W7913362"           # mohamed_lee_5442: Backpack 5917587651 (medium, laptop), 6309044598 (large, hydration)
NEW_ADDR = {"address1": "100 Main Street", "address2": "Suite 200", "city": "Austin", "state": "TX",
            "country": "USA", "zip": "78701"}
DEFAULT_ADDR = {"address1": "570 Elm Avenue", "address2": "Suite 175", "city": "Denver", "state": "CO",
                "country": "USA", "zip": "80218"}
# airline (v1 data)
MIA = "mia_li_3668"               # visa 4421486 (7447), visa 1955700 (1907), certificate 4856383 ($100), 7504069 ($250)
RES = "NO6JO3"                    # Mia: business, HAT083 + HAT221 on 2024-05-16, Mia Li; paid with credit_card_1955700
RES2 = "AIXC49"                   # Mia: basic economy, passenger Amelia Ahmed 1957-03-21
SNAKIO = "SNAKIO"                 # a letters-only reservation id (ivan_lopez_9956)


def run(domain, steps, tool, args):
    """(missing records, ctx) of a pending call after a tiny conversation."""
    hist, st, view = build(domain, steps, {"tool": tool, "args": args})
    ctx = Ctx(st, view, args)
    ctx.fact, ctx.part_id = "fact_x", "b"
    return LV.listing_missing_v4(ctx), ctx


def lines(missing):
    return [m["line"] for m in missing]


def say(*texts):
    """agent / user turns: ("a", text) or ("u", text)."""
    return [("agent" if r == "a" else "user", t) for r, t in texts]


class Base(unittest.TestCase):
    def ok(self, domain, steps, tool, args):
        missing, _ = run(domain, steps, tool, args)
        self.assertEqual(missing, [], missing)

    def miss(self, domain, steps, tool, args, want):
        missing, _ = run(domain, steps, tool, args)
        self.assertEqual(lines(missing), [w[0] for w in want], missing)
        for m, (_, exp) in zip(missing, want):
            if exp is not None:
                self.assertIn(exp, m["expected"], m)
            self.assertTrue(m["forms"], m)
            self.assertEqual((m["fact"], m["part"]), ("fact_x", "b"))
        return missing


# ----------------------------------------------------------------------------------------------- retail

CANCEL = {"order_id": ORDER, "reason": "no longer needed"}


class TestCancel(Base):
    def reason_ok(self, steps, args=CANCEL):
        hist, st, view = build("retail", steps, {"tool": "cancel_pending_order", "args": args})
        ctx = Ctx(st, view, args)
        ctx.fact, ctx.part_id = "f", "c"
        return LV.h_listing_reason_ok_v4(ctx), ctx

    def test_order_line_and_exact_reason(self):
        steps = say(("a", f"I will cancel order {ORDER} because you no longer need it. Shall I proceed?"),
                    ("u", "yes"))
        self.ok("retail", steps, "cancel_pending_order", CANCEL)
        self.assertTrue(self.reason_ok(steps)[0])

    def test_order_id_without_hash_any_case(self):
        self.ok("retail", say(("a", "Cancel w5442520? reason: no longer needed"), ("u", "yes")),
                "cancel_pending_order", CANCEL)

    def test_missing_order_id_names_the_value(self):
        self.miss("retail", say(("a", "Shall I cancel it because you no longer need it?"), ("u", "yes")),
                  "cancel_pending_order", CANCEL, [("order id", ORDER)])

    def test_reason_said_by_the_user_counts(self):
        steps = say(("u", f"Please cancel {ORDER}, I no longer need it."), ("a", f"Cancel order {ORDER}?"),
                    ("u", "yes"))
        self.assertTrue(self.reason_ok(steps)[0])

    def test_paraphrased_reason_goes_to_k18(self):
        steps = say(("a", f"Cancel order {ORDER} since you do not want it any more?"), ("u", "yes"))
        val, ctx = self.reason_ok(steps)
        self.assertFalse(val)
        self.assertEqual(ctx.notes[-1]["missing"][0]["line"], "cancel reason")
        self.assertEqual(ctx.notes[-1]["missing"][0]["expected"], "no longer needed")
        self.assertTrue(LV.h_listing_reason_candidates_v4(ctx))
        self.assertLessEqual(len(LV.h_listing_reason_candidates_v4(ctx)), LV.REASON_LIMIT)

    def test_ordered_by_mistake_phrase(self):
        args = {"order_id": ORDER, "reason": "ordered by mistake"}
        self.assertTrue(self.reason_ok(say(("u", "I ordered it by mistake"), ("a", f"Cancel {ORDER}?"),
                                           ("u", "yes")), args)[0])
        self.assertFalse(self.reason_ok(say(("a", f"Cancel {ORDER}, no longer needed?"), ("u", "yes")), args)[0])

    def test_reason_line_is_not_a_code_line(self):
        specs = LV.line_specs_v4(None, "retail", "cancel_pending_order", CANCEL)
        self.assertEqual([s.get("decided_by") for s in specs], [None, "K18"])

    def test_other_tools_need_no_reason(self):
        args = {"order_id": ORDER, "payment_method_id": "paypal_8049766"}
        hist, st, view = build("retail", say(("a", "x"), ("u", "y")),
                               {"tool": "modify_pending_order_payment", "args": args})
        ctx = Ctx(st, view, args)
        self.assertTrue(LV.h_listing_reason_ok_v4(ctx))
        self.assertEqual(LV.h_listing_reason_candidates_v4(ctx), [])

    def test_order_id_one_message_earlier_before_the_last_write_counts(self):
        steps = [("user", f"I want to cancel order {ORDER} and also update my address."),
                 ("agent", "First the address: 100 Main Street, Suite 200, Austin, TX 78701. Confirm?"),
                 ("user", "yes"),
                 ("call", "modify_user_address", dict(NEW_ADDR, user_id=OLIVIA)),
                 ("user", "thanks, now the cancel"),
                 ("agent", "I will cancel it because you no longer need it. Proceed?"), ("user", "yes")]
        self.ok("retail", steps, "cancel_pending_order", CANCEL)

    def test_another_order_named_since_does_not_count(self):
        steps = [("user", f"I want to cancel order {ORDER} and also update my address."),
                 ("agent", "First the address: 100 Main Street, Suite 200, Austin, TX 78701. Confirm?"),
                 ("user", "yes"),
                 ("call", "modify_user_address", dict(NEW_ADDR, user_id=OLIVIA)),
                 ("user", "thanks"), ("agent", f"By the way, order {ORDER2} is pending too."),
                 ("agent", "Cancel it because you no longer need it? yes or no"), ("user", "yes")]
        self.miss("retail", steps, "cancel_pending_order", CANCEL, [("order id", ORDER)])

    def test_longer_number_is_not_the_order_id(self):
        self.miss("retail", say(("a", "Cancel #W54425201? no longer needed"), ("u", "yes")),
                  "cancel_pending_order", CANCEL, [("order id", ORDER)])


class TestAddress(Base):
    ARGS = dict(NEW_ADDR, order_id=ORDER)

    def test_every_field_with_short_forms_no_country(self):
        self.ok("retail", say(("a", f"New address for {ORDER}: 100 Main St., Ste 200, Austin, Texas 78701. Ok?"),
                              ("u", "yes")), "modify_pending_order_address", self.ARGS)

    def test_unit_number_after_line_1(self):
        self.ok("retail", say(("a", f"{ORDER} ships to 100 Main Street 200, Austin TX 78701?"), ("u", "yes")),
                "modify_pending_order_address", self.ARGS)

    def test_missing_zip_is_reported(self):
        self.miss("retail", say(("a", f"{ORDER}: 100 Main Street, Suite 200, Austin, TX. Ok?"), ("u", "yes")),
                  "modify_pending_order_address", self.ARGS, [("zip of the new address", "78701")])

    def test_user_typed_zip_counts(self):
        steps = say(("u", "My new zip is 78701."), ("a", f"{ORDER}: 100 Main Street, Suite 200, Austin, TX. Ok?"),
                    ("u", "yes"))
        self.ok("retail", steps, "modify_pending_order_address", self.ARGS)

    def test_lower_case_state_code_is_a_word_not_the_state(self):
        args = dict(self.ARGS, state="IN")
        self.miss("retail", say(("a", f"{ORDER}: 100 Main Street, Suite 200, Austin 78701, in the morning"),
                                ("u", "yes")), "modify_pending_order_address", args, [("state of the new address",
                                                                                         "IN")])
        self.ok("retail", say(("a", f"{ORDER}: 100 Main Street, Suite 200, Austin, IN 78701"), ("u", "yes")),
                "modify_pending_order_address", args)

    def test_unchanged_fields_need_no_line(self):
        args = dict(DEFAULT_ADDR, order_id=ORDER, address1="571 Elm Avenue")
        specs = LV.line_specs_v4(build("retail", [])[1], "retail", "modify_pending_order_address", args)
        self.assertEqual([s["line"] for s in specs], ["order id", "street (line 1) of the new address"])

    def test_back_to_the_default_address(self):
        steps = [("agent", f"Move {ORDER} to 100 Main Street, Suite 200, Austin, TX 78701?"), ("user", "yes"),
                 ("call", "modify_pending_order_address", dict(NEW_ADDR, order_id=ORDER)),
                 ("user", "Sorry, put it back."),
                 ("agent", f"I will change order {ORDER} back to your default address. Ok?"), ("user", "yes")]
        self.ok("retail", steps, "modify_pending_order_address", dict(DEFAULT_ADDR, order_id=ORDER))

    def test_modify_user_address(self):
        args = dict(NEW_ADDR, user_id=OLIVIA)
        self.ok("retail", say(("a", "Your profile address becomes 100 Main Street, Suite 200, Austin, TX 78701."),
                              ("u", "yes")), "modify_user_address", args)
        self.miss("retail", say(("a", "Your profile address becomes 100 Main Street, Austin, TX 78701."),
                                ("u", "yes")), "modify_user_address", args, [("line 2 of the new address",
                                                                              "Suite 200")])


class TestPayment(Base):
    def pay(self, oid, pid, text, user=None):
        steps = say(("a", text), ("u", user or "yes"))
        return run("retail", steps, "modify_pending_order_payment", {"order_id": oid, "payment_method_id": pid})[0]

    def test_kind_word_alone_retail(self):
        self.assertEqual(self.pay(ORDER, "paypal_8049766", f"Switch {ORDER} to PayPal?"), [])
        self.assertEqual(self.pay(ORDER, "gift_card_7794233", f"Switch {ORDER} to your gift card?"), [])

    def test_card_forms(self):
        for t in ("visa ending in 9182", "card ending in 3331", "card 9753331", "credit_card_9753331",
                  "the card ending 753331", "your Visa", "your credit card"):
            self.assertEqual(self.pay(ORDER2, "credit_card_9753331", f"Pay {ORDER2} with {t}?"), [], t)

    def test_missing_card_names_it(self):
        m = self.pay(ORDER, "gift_card_7794233", f"Switch {ORDER} to your card?")
        self.assertEqual(lines(m), ["new payment method"])
        self.assertEqual(m[0]["expected"], "gift_card_7794233")

    def test_negated_method_does_not_count(self):
        self.assertEqual(lines(self.pay(ORDER, "paypal_8049766", f"For {ORDER}: not PayPal, the gift card?")),
                         ["new payment method"])

    def test_user_said_the_method(self):
        self.assertEqual(self.pay(ORDER, "paypal_8049766", f"Switch {ORDER}?", user="yes, use my PayPal"), [])

    def test_trap_ambiguous_4_digits_mei(self):
        # visa credit_card_3945811 has last four 4044; the mastercard's id credit_card_7574044 ends in 4044
        visa, mc = "credit_card_3945811", "credit_card_7574044"
        self.assertEqual(lines(self.pay(MEI_ORDER, visa, f"Pay {MEI_ORDER} with the card ending in 4044?")),
                         ["new payment method"])
        self.assertEqual(lines(self.pay(MEI_ORDER, mc, f"Pay {MEI_ORDER} with the card ending in 4044?")),
                         ["new payment method"])
        self.assertEqual(self.pay(MEI_ORDER, mc, f"Pay {MEI_ORDER} with the card ending in 74044?"), [])
        self.assertEqual(self.pay(MEI_ORDER, mc, f"Pay {MEI_ORDER} with the mastercard ending in 7930?"), [])
        self.assertEqual(self.pay(MEI_ORDER, visa, f"Pay {MEI_ORDER} with your Visa?"), [])
        self.assertEqual(lines(self.pay(MEI_ORDER, visa, f"Pay {MEI_ORDER} with your credit card?")),
                         ["new payment method"])                         # two credit cards

    def test_brand_clash_next_to_digits(self):
        self.assertEqual(lines(self.pay(MEI_ORDER, "credit_card_7574044",
                                        f"Pay {MEI_ORDER} with the Visa ending in 7930?")), ["new payment method"])

    def test_stray_digits(self):
        for t in ("the total is $9182", "a total of 9182.50", "zip 91820", "ref 197533310"):
            self.assertEqual(lines(self.pay(ORDER2, "credit_card_9753331", f"For {ORDER2}: {t}. Ok?")),
                             ["new payment method"], t)


class TestItems(Base):
    BOOTS = {"order_id": ORDER, "item_ids": ["2648909398"], "new_item_ids": ["8106223139"],
             "payment_method_id": "credit_card_9753331"}

    def test_modify_items_name_and_named_option(self):
        self.ok("retail", say(("a", f"In {ORDER}, change the Hiking Boots to size 9, paid with the original "
                                    "payment method. Confirm?"), ("u", "yes")), "modify_pending_order_items",
                self.BOOTS)

    def test_word_of_the_name_and_new_item_id(self):
        self.ok("retail", say(("a", f"{ORDER}: the boots become item 8106223139, visa 9182"), ("u", "yes")),
                "modify_pending_order_items", self.BOOTS)

    def test_bare_short_number_value_needs_the_option_name(self):
        m = self.miss("retail", say(("a", f"{ORDER}: change the Hiking Boots to 9, with visa 9182"), ("u", "yes")),
                      "modify_pending_order_items", self.BOOTS, [("new item for Hiking Boots", "size 8 → 9")])
        self.assertIn("8106223139", m[0]["expected"])

    def test_user_typed_the_new_size(self):
        steps = say(("u", "I want size 9 instead"), ("a", f"{ORDER}: Hiking Boots, visa 9182. Ok?"), ("u", "yes"))
        self.ok("retail", steps, "modify_pending_order_items", self.BOOTS)

    def test_missing_old_item_and_payment(self):
        self.miss("retail", say(("a", f"{ORDER}: new item 8106223139. Ok?"), ("u", "yes")),
                  "modify_pending_order_items", self.BOOTS,
                  [("item", "Hiking Boots"), ("payment method for the price difference", "credit_card_9753331")])

    def test_option_clash_is_logged_not_blocked(self):
        args = {"order_id": ORDER, "item_ids": ["3330317167"], "new_item_ids": ["2880340443"],
                "payment_method_id": "paypal_8049766"}
        missing, ctx = run("retail", say(("a", f"{ORDER}: Gaming Mouse, now in white (not RGB), PayPal"),
                                         ("u", "yes")), "modify_pending_order_items", args)
        self.assertEqual(missing, [])
        self.assertEqual(ctx.notes[-1]["option_clash"][0]["also_named"], ["RGB"])

    def test_trap_gold_is_not_rose_gold(self):
        args = {"order_id": "#W3038897", "item_ids": ["3187628796"], "new_item_ids": ["1631373418"],
                "payment_method_id": "credit_card_6821943"}
        steps = say(("a", "#W3038897: the Smartphone in rose gold with 6GB RAM, card 6821943"), ("u", "yes"))
        self.miss("retail", steps, "exchange_delivered_order_items", args, [("new item for Smartphone", "gold")])
        self.ok("retail", say(("a", "#W3038897: swap the Smartphone for the gold one, 6GB, card 6821943"),
                              ("u", "yes")), "exchange_delivered_order_items", args)

    def test_trap_polarized_is_not_non_polarized(self):
        args = {"order_id": "#W6015009", "item_ids": ["4245201809"], "new_item_ids": ["2177260429"],
                "payment_method_id": "credit_card_5884162"}
        self.miss("retail", say(("a", "#W6015009: Sunglasses, non-polarized lenses, card 5884162"), ("u", "yes")),
                  "exchange_delivered_order_items", args, [("new item for Sunglasses", "polarized")])
        self.ok("retail", say(("a", "#W6015009: Sunglasses with polarized lenses, card 5884162"), ("u", "yes")),
                "exchange_delivered_order_items", args)

    def test_trap_black_under_two_option_names(self):
        # 9672174103 (frame brown, lens brown, plastic) -> 2198125883 (frame silver, lens black, metal)
        args = {"order_id": "#W6015009", "item_ids": ["9672174103"], "new_item_ids": ["2198125883"],
                "payment_method_id": "credit_card_5884162"}
        self.ok("retail", say(("a", "#W6015009: Sunglasses, silver metal frame with black lenses, card 5884162"),
                              ("u", "yes")), "exchange_delivered_order_items", args)
        self.miss("retail", say(("a", "#W6015009: Sunglasses, silver metal, black, card 5884162"), ("u", "yes")),
                  "exchange_delivered_order_items", args, [("new item for Sunglasses", "black")])

    def test_trap_wifi_is_not_wifi_cellular(self):
        args = {"order_id": "#W3897284", "item_ids": ["5418781403"], "new_item_ids": ["6268080249"],
                "payment_method_id": "gift_card_3410768"}
        self.miss("retail", say(("a", "#W3897284: E-Reader, Wi-Fi + Cellular, gift card 3410768"), ("u", "yes")),
                  "modify_pending_order_items", args, [("new item for E-Reader", "Wi-Fi")])
        self.ok("retail", say(("a", "#W3897284: E-Reader, Wi-Fi only, gift card 3410768"), ("u", "yes")),
                "modify_pending_order_items", args)

    def test_unchanged_new_item_needs_no_line(self):
        specs = LV.line_specs_v4(build("retail", [])[1], "retail", "modify_pending_order_items",
                                 dict(self.BOOTS, new_item_ids=["2648909398"]))
        self.assertEqual([s["line"] for s in specs], ["order id", "item", "payment method for the price difference"])


class TestReturn(Base):
    def test_all_items_and_original_method(self):
        args = {"order_id": DELIVERED, "item_ids": ["6242772310", "9727387530"], "payment_method_id": "paypal_8049766"}
        self.ok("retail", say(("a", f"Return all the items of {DELIVERED} to the original payment method?"),
                              ("u", "yes")), "return_delivered_order_items", args)

    def test_all_items_does_not_name_one_of_two(self):
        args = {"order_id": DELIVERED, "item_ids": ["9727387530"], "payment_method_id": "paypal_8049766"}
        self.miss("retail", say(("a", f"Return all the items of {DELIVERED} to PayPal?"), ("u", "yes")),
                  "return_delivered_order_items", args, [("returned item", "Sneakers")])
        self.ok("retail", say(("a", f"Return the sneakers of {DELIVERED} to PayPal?"), ("u", "yes")),
                "return_delivered_order_items", args)

    def test_two_items_of_one_product(self):
        args = {"order_id": BACKPACKS, "item_ids": ["5917587651"], "payment_method_id": "credit_card_8169552"}
        steps = say(("a", f"Return the Backpack from {BACKPACKS} to card 8169552?"), ("u", "yes"))
        self.miss("retail", steps, "return_delivered_order_items", args, [("returned item", "Backpack")])
        self.ok("retail", say(("a", f"Return the medium Backpack from {BACKPACKS} to card 8169552?"), ("u", "yes")),
                "return_delivered_order_items", args)
        self.ok("retail", say(("a", f"Return item 5917587651 from {BACKPACKS} to card 8169552?"), ("u", "yes")),
                "return_delivered_order_items", args)
        both = dict(args, item_ids=["5917587651", "6309044598"])
        self.ok("retail", say(("a", f"Return both Backpacks from {BACKPACKS} to card 8169552?"), ("u", "yes")),
                "return_delivered_order_items", both)


class TestWindow(Base):
    def test_listing_before_the_last_write_with_a_reply_does_not_count(self):
        args = {"order_id": ORDER, "payment_method_id": "paypal_8049766"}
        steps = [("agent", f"Switch {ORDER} to PayPal, and change {ORDER2} to PayPal too?"), ("user", "yes"),
                 ("call", "modify_pending_order_payment", {"order_id": ORDER2, "payment_method_id": "paypal_8049766"}),
                 ("user", "great, what about the other one?"), ("agent", "Shall I go ahead?"), ("user", "yes")]
        self.miss("retail", steps, "modify_pending_order_payment", args, [("order id", ORDER),
                                                                           ("new payment method", "paypal_8049766")])

    def test_batch_member_shares_the_listing(self):
        args = {"order_id": ORDER, "payment_method_id": "paypal_8049766"}
        steps = [("agent", f"Switch {ORDER} to PayPal, and change {ORDER2} to PayPal too?"), ("user", "yes"),
                 ("call", "modify_pending_order_payment", {"order_id": ORDER2, "payment_method_id": "paypal_8049766"})]
        self.ok("retail", steps, "modify_pending_order_payment", args)

    def test_window_refs(self):
        steps = [("user", "hi"), ("agent", f"Switch {ORDER} to PayPal?"), ("user", "yes"),
                 ("call", "modify_pending_order_payment", {"order_id": ORDER2, "payment_method_id": "paypal_8049766"}),
                 ("user", "next"), ("agent", f"{ORDER} to PayPal?"), ("user", "yes")]
        hist, st, view = build("retail", steps, {"tool": "modify_pending_order_payment",
                                                 "args": {"order_id": ORDER, "payment_method_id": "paypal_8049766"}})
        ctx = Ctx(st, view)
        self.assertEqual(LV.span_refs_v4(ctx), [4, 5, 6])
        self.assertEqual(LV.listing_window_v4(ctx), [6, 5, 4])
        self.assertEqual(LV.listing_anchors_v4(ctx), [5])

    def test_failed_write_does_not_start_a_span(self):
        args = {"order_id": ORDER, "payment_method_id": "paypal_8049766"}
        steps = [("agent", f"Switch {ORDER} to PayPal?"), ("user", "yes"),
                 ("call", "modify_pending_order_payment", {"order_id": ORDER, "payment_method_id": "paypal_0000000"}),
                 ("user", "oops, try again")]
        self.ok("retail", steps, "modify_pending_order_payment", args)


# ----------------------------------------------------------------------------------------------- airline

BOOK = {"user_id": MIA, "origin": "DFW", "destination": "LAX", "flight_type": "round_trip", "cabin": "economy",
        "flights": [{"flight_number": "HAT170", "date": "2024-05-22"}, {"flight_number": "HAT022", "date": "2024-05-26"}],
        "passengers": [{"first_name": "Mia", "last_name": "Li", "dob": "1990-04-05"},
                       {"first_name": "Amelia", "last_name": "Ahmed", "dob": "1957-03-21"}],
        "payment_methods": [{"payment_id": "certificate_7504069", "amount": 250},
                            {"payment_id": "credit_card_4421486", "amount": 386}],
        "total_baggages": 2, "nonfree_baggages": 0, "insurance": "no"}
GOOD_BOOK = ("Booking: HAT 170 on May 22 and HAT022 on 5/26, economy, for Mia Li and Amelia Ahmed, 2 checked bags, "
             "$250 from your $250 certificate and $386 on your visa ending in 1486. Shall I book?")


class TestBook(Base):
    def test_full_listing_no_dob_no_paid_bags(self):
        self.ok("airline", say(("a", GOOD_BOOK), ("u", "yes")), "book_reservation", BOOK)

    def test_insurance_is_left_to_k17(self):
        specs = LV.line_specs_v4(None, "airline", "book_reservation", BOOK)
        self.assertEqual([s["line"] for s in specs if s.get("decided_by")], ["travel insurance"])
        self.assertNotIn("paid bags", [s["line"] for s in specs])                        # trap 7: 0 paid

    def test_flight_number_needs_its_date(self):
        text = GOOD_BOOK.replace("HAT022 on 5/26", "HAT022")
        self.miss("airline", say(("a", text), ("u", "yes")), "book_reservation", BOOK,
                  [("flight", "HAT022 on 2024-05-26")])

    def test_flight_word_form(self):
        self.ok("airline", say(("a", GOOD_BOOK.replace("HAT 170", "flight 170")), ("u", "yes")),
                "book_reservation", BOOK)

    def test_trap_basic_economy_is_not_economy(self):
        text = GOOD_BOOK.replace("economy", "basic economy")
        self.miss("airline", say(("a", text), ("u", "yes")), "book_reservation", BOOK, [("cabin", "economy")])
        self.ok("airline", say(("a", text), ("u", "yes")), "book_reservation", dict(BOOK, cabin="basic_economy"))

    def test_trap_two_visas_and_two_certificates(self):
        text = GOOD_BOOK.replace("your visa ending in 1486", "your Visa").replace(
            "$250 from your $250 certificate", "250 dollars from your certificate")
        self.miss("airline", say(("a", text), ("u", "yes")), "book_reservation", BOOK,
                  [("payment method", "certificate_7504069"), ("payment method", "credit_card_4421486")])

    def test_amounts_needed_with_two_methods(self):
        text = GOOD_BOOK.replace("$386 on", "the rest on")
        self.miss("airline", say(("a", text), ("u", "yes")), "book_reservation", BOOK,
                  [("payment method", "$386")])

    def test_missing_passenger(self):
        self.miss("airline", say(("a", GOOD_BOOK.replace(" and Amelia Ahmed", "")), ("u", "yes")),
                  "book_reservation", BOOK, [("passenger", "Amelia Ahmed")])

    def test_paid_bags_line_when_more_than_zero(self):
        args = dict(BOOK, total_baggages=3, nonfree_baggages=1)
        self.miss("airline", say(("a", GOOD_BOOK.replace("2 checked", "3 checked")), ("u", "yes")),
                  "book_reservation", args, [("paid bags", "1 paid")])
        self.ok("airline", say(("a", GOOD_BOOK.replace("2 checked bags", "3 checked bags (1 extra bag, $50)")),
                               ("u", "yes")), "book_reservation", args)


class TestReservationChanges(Base):
    FLIGHTS = {"reservation_id": RES, "cabin": "business", "payment_id": "credit_card_1955700",
               "flights": [{"flight_number": "HAT083", "date": "2024-05-16"},
                           {"flight_number": "HAT221", "date": "2024-05-17"}]}

    def test_changed_flight_only_original_payment(self):
        self.ok("airline", say(("a", f"For {RES}: move HAT221 to May 17, charged to the original payment method."),
                               ("u", "yes")), "update_reservation_flights", self.FLIGHTS)

    def test_unchanged_flight_and_cabin_need_no_line(self):
        specs = LV.line_specs_v4(build("airline", [])[1], "airline", "update_reservation_flights", self.FLIGHTS)
        self.assertEqual([s["expected"] for s in specs if s["line"] == "flight"], ["HAT221 on 2024-05-17"])
        self.assertNotIn("cabin", [s["line"] for s in specs])
        specs = LV.line_specs_v4(build("airline", [])[1], "airline", "update_reservation_flights",
                                 dict(self.FLIGHTS, cabin="economy"))
        self.assertIn("cabin", [s["line"] for s in specs])

    def test_missing_reservation_and_payment(self):
        self.miss("airline", say(("a", "Move HAT221 to May 17?"), ("u", "yes")), "update_reservation_flights",
                  self.FLIGHTS, [("reservation id", RES), ("payment method", "credit_card_1955700")])

    def test_trap_letters_only_reservation_id_any_case(self):
        args = {"reservation_id": SNAKIO}
        self.ok("airline", say(("a", "Cancel reservation snakio?"), ("u", "yes")), "cancel_reservation", args)
        self.miss("airline", say(("a", "Cancel reservation SNAKIOX?"), ("u", "yes")), "cancel_reservation", args,
                  [("reservation id", SNAKIO)])

    def test_reservation_named_before_the_last_write(self):
        steps = [("user", f"My reservation is {RES}. Add one bag."), ("agent", f"{RES}: 3 bags in total. Ok?"),
                 ("user", "yes"),
                 ("call", "update_reservation_baggages", {"reservation_id": RES, "total_baggages": 3,
                                                          "nonfree_baggages": 0, "payment_id": "credit_card_1955700"}),
                 ("user", "now change the second flight"), ("agent", "HAT221 moves to May 17, original card. Ok?"),
                 ("user", "yes")]
        self.ok("airline", steps, "update_reservation_flights", self.FLIGHTS)

    def test_bags_total_or_added_payment_only_when_charged(self):
        args = {"reservation_id": RES, "total_baggages": 3, "nonfree_baggages": 0, "payment_id": "credit_card_1955700"}
        self.ok("airline", say(("a", f"{RES}: I will add 1 bag. Ok?"), ("u", "yes")), "update_reservation_baggages",
                args)
        self.ok("airline", say(("a", f"{RES}: 3 bags in total. Ok?"), ("u", "yes")), "update_reservation_baggages",
                args)
        paid = dict(args, nonfree_baggages=1, payment_id="credit_card_4421486")
        self.miss("airline", say(("a", f"{RES}: 3 bags in total. Ok?"), ("u", "yes")), "update_reservation_baggages",
                  paid, [("payment method", "credit_card_4421486")])
        self.ok("airline", say(("a", f"{RES}: 3 bags in total, $50 on the visa ending 7447. Ok?"), ("u", "yes")),
                "update_reservation_baggages", paid)

    def test_passengers_changed_only_dob_when_it_changed(self):
        new_dob = {"reservation_id": RES2, "passengers": [{"first_name": "Amelia", "last_name": "Ahmed",
                                                           "dob": "1957-03-22"}]}
        self.miss("airline", say(("a", f"{RES2}: Amelia Ahmed. Ok?"), ("u", "yes")), "update_reservation_passengers",
                  new_dob, [("passenger", "1957-03-22")])
        self.ok("airline", say(("a", f"{RES2}: Amelia Ahmed, born March 22, 1957. Ok?"), ("u", "yes")),
                "update_reservation_passengers", new_dob)
        new_name = {"reservation_id": RES2, "passengers": [{"first_name": "John", "last_name": "Doe",
                                                            "dob": "1980-01-01"}]}
        self.ok("airline", say(("a", f"{RES2}: replace the passenger with John Doe. Ok?"), ("u", "yes")),
                "update_reservation_passengers", new_name)
        same = {"reservation_id": RES2, "passengers": [{"first_name": "Amelia", "last_name": "Ahmed",
                                                        "dob": "1957-03-21"}]}
        self.assertEqual([s["line"] for s in LV.line_specs_v4(build("airline", [])[1], "airline",
                                                               "update_reservation_passengers", same)],
                         ["reservation id"])

    def test_send_certificate_amount(self):
        args = {"user_id": MIA, "amount": 100}
        self.ok("airline", say(("a", "I can send you a $100 certificate."), ("u", "yes")), "send_certificate", args)
        self.miss("airline", say(("a", "I can send you a $1000 certificate."), ("u", "yes")), "send_certificate",
                  args, [("certificate amount", "$100")])


# ----------------------------------------------------------------------------------------------- facts and overlays

OVERLAYS = os.path.join(paths.OUTPUT_DIR, "eval_v4", "overlays")


def overlay(domain):
    with open(os.path.join(OVERLAYS, f"facts_A1_{domain}.json"), encoding="utf-8") as f:
        return json.load(f)


class TestOverlays(unittest.TestCase):
    def test_structure_parts_validate_and_run(self):
        doc = F.load_facts("retail")
        entry = copy.deepcopy(doc["facts"]["consequential_action_details_listed"])
        ov = overlay("retail")["facts"]["consequential_action_details_listed"]
        kinds = L.domain_kinds("retail")
        for pid in ("a", "b", "c"):
            p = ov["parts"][pid]
            self.assertEqual(F.validate_part("x", pid, p, ov["sources"], kinds, ()), [], pid)
        entry["parts"] = {k: ov["parts"][k] for k in ("a", "b", "c")}
        entry["combine"] = "a AND b AND c"
        args = {"order_id": ORDER, "payment_method_id": "paypal_8049766"}
        for text, want in ((f"Switch {ORDER} to PayPal?", True), (f"Switch {ORDER}?", False)):
            hist, st, view = build("retail", say(("a", text), ("u", "yes")),
                                   {"tool": "modify_pending_order_payment", "args": args})
            r = F.evaluate(entry, st, args, view=view, name="consequential_action_details_listed")
            self.assertEqual(r["value"], want, r)
            if not want:
                notes = r["parts"]["b"]["notes"]
                self.assertEqual(notes[0]["missing"][0]["fact"], "consequential_action_details_listed")
                self.assertEqual(notes[0]["missing"][0]["part"], "b")

    def test_airline_part_c(self):
        ov = overlay("airline")["facts"]["pending_database_change_details_listed_and_explicitly_confirmed"]
        self.assertEqual(sorted(ov["parts"]), ["c"])
        self.assertNotIn("combine", ov)
        entry = copy.deepcopy(F.load_facts("airline")["facts"][
            "pending_database_change_details_listed_and_explicitly_confirmed"])
        entry["parts"] = {"c": ov["parts"]["c"]}
        entry["combine"] = "c"
        hist, st, view = build("airline", say(("a", GOOD_BOOK), ("u", "yes")),
                               {"tool": "book_reservation", "args": BOOK})
        self.assertTrue(F.evaluate(entry, st, BOOK, view=view, name="p")["value"])

    def test_k18_part_validates_when_questions_v4_is_there(self):
        try:
            from state_tracker.v4 import questions_v4  # noqa: F401  (registers ask_first_yes_v4)
        except Exception as e:                           # pragma: no cover - another agent's file
            self.skipTest(f"questions_v4 not importable: {e}")
        ov = overlay("retail")["facts"]["consequential_action_details_listed"]
        p = ov["parts"]["d"]
        self.assertEqual(F.validate_part("x", "d", p, ov["sources"], L.domain_kinds("retail"), ()), [])

    def test_helper_names_end_in_v4(self):
        self.assertTrue(all(n.endswith("_v4") for n in LV.HELPERS))
        reg = F.registered_names()
        for n in LV.HELPERS:
            self.assertEqual(reg[n].source, "structure")


if __name__ == "__main__":
    unittest.main()
