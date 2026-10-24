"""Tracker v3, part 7: the structure parts of the fact files, as p7's overlay writes them
(output/eval_v3/p7_parts/exprs_<domain>.json), run by the v3 evaluator (facts_format_v3.evaluate) on tiny
conversations with τ-bench's own tool outputs. Each part is evaluated on its own (the other parts of a fact belong to
p6 and p8). Also: the info classes, and that every structure part of the fact files has a valid expression.

Run from predicate_correctness/:  python3 -B -m unittest tests.test_v3_structure_facts -v
"""
from __future__ import annotations

import json
import os
import sys
import unittest

sys.dont_write_bytecode = True

from state_tracker import lookup_format as L                # noqa: E402
from state_tracker import paths                              # noqa: E402
from state_tracker.v3 import facts_format_v3 as F           # noqa: E402
from state_tracker.v3 import info_classes as IC              # noqa: E402
from state_tracker.v3 import message_view as MV             # noqa: E402
from tests.test_v3_message_view import (MIA, OLIVIA, OLIVIA_EMAIL, ORDER, Ctx, build)   # noqa: E402

FACTS = {d: F.load_facts(d)["facts"] for d in paths.DOMAINS}
OV = {}
for _d in paths.DOMAINS:
    with open(os.path.join(paths.OUTPUT_DIR, "eval_v3", "p7_parts", f"exprs_{_d}.json"), encoding="utf-8") as _f:
        OV[_d] = json.load(_f)["exprs"]


def part(domain, fact, pid, st, view, args=None):
    """The result of one structure part of a fact, evaluated on its own."""
    entry = FACTS[domain][fact]
    e = dict(entry)
    e["parts"] = {pid: dict(entry["parts"][pid], expr=OV[domain][fact][pid]["expr"])}
    e["combine"] = pid
    return F.evaluate(e, st, args, view=view, name=fact)


def val(domain, fact, pid, steps, pending):
    hist, st, view = build(domain, steps, pending)
    r = part(domain, fact, pid, st, view)
    return r["value"] if not r["problems"] else ("problem", r["problems"][0]["kind"])


LOGIN = [("user", "Hi, my email is " + OLIVIA_EMAIL), ("call", "find_user_id_by_email", {"email": OLIVIA_EMAIL})]


def reply(text):
    return {"tool": "respond", "args": {"content": text}}


class TestOverlay(unittest.TestCase):
    def test_every_structure_part_has_a_valid_expression(self):
        for d in paths.DOMAINS:
            kinds = L.domain_kinds(d)
            n = 0
            for f, e in FACTS[d].items():
                for pid, p in e["parts"].items():
                    if p["source"] != "structure":
                        continue
                    n += 1
                    expr = OV[d][f][pid]["expr"]
                    probs = F.validate_part(f, pid, dict(p, expr=expr), e["sources"], kinds,
                                            ("item",) if e.get("for_each") else ())
                    self.assertEqual(probs, [], (d, f, pid))
            self.assertEqual(n, {"retail": 18, "airline": 42}[d])
            for f, parts in OV[d].items():
                for pid in parts:
                    self.assertEqual(FACTS[d][f]["parts"][pid]["source"], "structure", (f, pid))


class TestIdentity(unittest.TestCase):
    def test_email_typed(self):
        self.assertTrue(val("retail", "email_identity_provided_by_user", "a", [("user", "It is " + OLIVIA_EMAIL)],
                            {"tool": "find_user_id_by_email", "args": {"email": OLIVIA_EMAIL}}))

    def test_email_typed_in_upper_case(self):
        self.assertTrue(val("retail", "email_identity_provided_by_user", "a",
                            [("user", "It is " + OLIVIA_EMAIL.upper() + ".")],
                            {"tool": "find_user_id_by_email", "args": {"email": OLIVIA_EMAIL}}))

    def test_email_only_written_by_the_agent(self):
        self.assertFalse(val("retail", "email_identity_provided_by_user", "a",
                             [("user", "find me"), ("agent", "Is it " + OLIVIA_EMAIL + "?")],
                             {"tool": "find_user_id_by_email", "args": {"email": OLIVIA_EMAIL}}))

    def test_name_zip_plus_four_and_accents(self):
        self.assertTrue(val("retail", "name_and_zip_identity_provided_by_user", "a",
                            [("user", "I am Olívia Itô"), ("agent", "zip?"), ("user", "80218-4411")],
                            {"tool": "find_user_id_by_name_zip",
                             "args": {"first_name": "Olivia", "last_name": "Ito", "zip": "80218"}}))

    def test_name_zip_missing_one_value(self):
        self.assertFalse(val("retail", "name_and_zip_identity_provided_by_user", "a", [("user", "I am Olivia Ito")],
                             {"tool": "find_user_id_by_name_zip",
                              "args": {"first_name": "Olivia", "last_name": "Ito", "zip": "80218"}}))

    def test_missing_argument_takes_the_blocking_value(self):
        hist, st, view = build("retail", [("user", OLIVIA_EMAIL)], {"tool": "find_user_id_by_email", "args": {}})
        r = part("retail", "email_identity_provided_by_user", "a", st, view)
        self.assertEqual(r["problems"][0]["kind"], "missing_argument")
        self.assertIs(r["value"], False)


class TestDisclosure(unittest.TestCase):
    F_ = "user_specific_information_disclosed"

    def test_nothing_shown_nothing_disclosed(self):
        steps = [("user", "Hi, I want to return something")]
        p = reply("Sure, please give me your email first.")
        self.assertFalse(val("retail", self.F_, "a", steps, p))
        self.assertFalse(val("retail", self.F_, "b", steps, p))

    def test_order_ids_from_a_cap_override_output(self):
        steps = [("user", "Hi, I need my orders"), ("call", "get_user_details", {"user_id": OLIVIA})]
        p = reply("Your orders are #W5866402 and #W5353646.")
        self.assertTrue(val("retail", self.F_, "a", steps, p))
        self.assertTrue(val("retail", self.F_, "b", steps, p))

    def test_repeating_the_users_own_words_is_not_disclosure(self):
        steps = [("user", "Is order W5442520 shipped? my zip is 80218")]
        self.assertFalse(val("retail", self.F_, "a", steps, reply("I can check order #W5442520 for zip 80218.")))

    def test_catalog_item_shown_by_product_lookup_is_not_user_data(self):
        steps = [("user", "What gaming mice do you have?"),
                 ("call", "get_product_details", {"product_id": "5713490933"})]
        self.assertFalse(val("retail", self.F_, "a", steps, reply("Item 3330317167 is a black optical wired mouse.")))

    def test_year_is_not_a_last_four(self):
        steps = [("user", "hello")]
        self.assertFalse(val("retail", self.F_, "a", steps, reply("Our policy changed on May 15, 2024.")))

    def test_example_zip_before_any_tool_call_is_not_disclosure(self):
        """RC11 M1 (partner.nano_train|retail/49/0|0): the first reply gives an example ZIP that happens to be a
        user's ZIP in τ-bench's data. No tool output ran, so the agent disclosed nothing: part a is false."""
        steps = [("user", "Hi, I'm Aarav Anderson in Philadelphia. I'd like to exchange earbuds.")]
        text = "Please give your first name, last name and zip code (e.g., Aarav Anderson, 19104)."
        hist, st, view = build("retail", steps, reply(text))
        self.assertTrue(IC.user_data_values(text, view, st))                 # 19104 is a database ZIP
        self.assertFalse(IC.user_data_values(text, view, st, seen_only=True))
        self.assertFalse(val("retail", self.F_, "a", steps, reply(text)))
        self.assertFalse(val("retail", self.F_, "b", steps, reply(text)))

    def test_value_shown_by_a_tool_output_counts(self):
        steps = [("user", "Hi"), ("call", "get_user_details", {"user_id": OLIVIA})]
        self.assertTrue(val("retail", self.F_, "a", steps, reply("Your zip code is 80218.")))
        self.assertTrue(val("retail", self.F_, "a", steps, reply("Your gift card ending in 4233 has a balance.")))

    def test_database_value_no_output_showed_is_left_to_k14(self):
        """After a data output, a database value that no output showed is not part a's; part b is true, so K14 (the
        question) decides."""
        steps = [("user", "Hi"), ("call", "get_user_details", {"user_id": OLIVIA})]
        p = reply("For example, a zip code looks like 19104.")
        self.assertFalse(val("retail", self.F_, "a", steps, p))
        self.assertTrue(val("retail", self.F_, "b", steps, p))

    def test_amount_alone_is_not_user_data(self):
        steps = [("user", "hello")]
        self.assertFalse(val("retail", self.F_, "a", steps, reply("A $56.00 balance would be typical.")))


class TestAnotherUser(unittest.TestCase):
    F_ = "response_performs_task_for_another_user"

    def test_reply_with_another_users_email(self):
        steps = LOGIN + [("user", "what is my friend's email?")]
        self.assertTrue(val("retail", self.F_, "a", steps, reply("It is mia.moore8091@example.com.")))
        self.assertTrue(val("retail", self.F_, "b", steps, reply("It is mia.moore8091@example.com.")))

    def test_reply_with_own_data(self):
        steps = LOGIN + [("call", "get_user_details", {"user_id": OLIVIA})]
        self.assertFalse(val("retail", self.F_, "a", steps, reply("Your gift card is gift_card_7794233.")))

    def test_before_login_part_a_is_false(self):
        self.assertFalse(val("retail", self.F_, "a", [("user", "x")], reply("mia.moore8091@example.com")))

    def test_first_login_picks_the_message_with_the_email(self):
        steps = [("user", "Hi"), ("agent", "email?"), ("user", "it's " + OLIVIA_EMAIL), ("agent", "thanks"),
                 ("user", "ok")]
        hist, st, view = build("retail", steps, {"tool": "find_user_id_by_email", "args": {"email": OLIVIA_EMAIL}})
        c = Ctx(st, view)
        self.assertEqual(MV.another_user_pick(c), [2])
        self.assertTrue(part("retail", "request_is_for_another_user", "b", st, view)["value"])

    def test_after_login_no_pick_for_a_login(self):
        hist, st, view = build("retail", LOGIN, {"tool": "find_user_id_by_email",
                                                 "args": {"email": "mia.moore8091@example.com"}})
        self.assertFalse(part("retail", "request_is_for_another_user", "b", st, view)["value"])

    def test_catalog_read_screened(self):
        p = {"tool": "get_product_details", "args": {"product_id": "5713490933"}}
        self.assertTrue(val("retail", "request_is_for_another_user", "b",
                            LOGIN + [("user", "my son wants a gaming mouse")], p))
        self.assertFalse(val("retail", "request_is_for_another_user", "b",
                             LOGIN + [("user", "I want a gaming mouse")], p))


class TestRetailListings(unittest.TestCase):
    def test_details_listed_without_order_id(self):
        pend = {"tool": "modify_pending_order_items", "args": {
            "order_id": ORDER, "item_ids": ["3330317167"], "new_item_ids": ["2193628750"],
            "payment_method_id": "paypal_8049766"}}
        steps = LOGIN + [("user", "order #W5442520: the mouse"),
                         ("agent", "I will change the Gaming Mouse, paid by PayPal. Are these all the items?"),
                         ("user", "yes")]
        self.assertTrue(val("retail", "consequential_action_details_listed", "a", steps, pend))
        self.assertTrue(val("retail", "user_explicitly_confirmed_pending_action", "a", steps, pend))
        self.assertTrue(val("retail", "agent_reminded_user_to_include_all_items_for_modification", "a", steps, pend))
        self.assertTrue(val("retail", "user_chose_price_difference_payment_method", "b", steps, pend))
        self.assertFalse(val("retail", "user_chose_price_difference_payment_method", "a", steps, pend))

    def test_strict_no_blocks_the_confirmation(self):
        pend = {"tool": "cancel_pending_order", "args": {"order_id": ORDER, "reason": "no longer needed"}}
        steps = LOGIN + [("agent", "Cancel order #W5442520 because it is no longer needed?"), ("user", "no, wait")]
        self.assertFalse(val("retail", "user_confirmed_cancellation_order_and_reason", "a", steps, pend))

    def test_payment_exact_by_gift_card_number(self):
        pend = {"tool": "modify_pending_order_payment",
                "args": {"order_id": ORDER, "payment_method_id": "gift_card_7794233"}}
        steps = LOGIN + [("user", "pay order W5442520 with gift card 7794233")]
        self.assertTrue(val("retail", "user_chose_pending_payment_method", "a", steps, pend))

    def test_payment_nonexistent_order_is_false(self):
        pend = {"tool": "modify_pending_order_payment",
                "args": {"order_id": "#W0000001", "payment_method_id": "gift_card_7794233"}}
        hist, st, view = build("retail", LOGIN + [("user", "gift card 7794233")], pend)
        r = part("retail", "user_chose_pending_payment_method", "a", st, view)
        self.assertIs(r["value"], False)
        self.assertEqual(r["problems"], [])

    def test_transfer_scope_picks_two_user_messages(self):
        steps = [("user", "a"), ("agent", "b"), ("user", "c"), ("agent", "d"), ("user", "e")]
        hist, st, view = build("retail", steps, {"tool": "transfer_to_human_agents", "args": {"summary": "x"}})
        self.assertEqual(MV.user_messages(Ctx(st, view), 2), [4, 2])
        self.assertTrue(part("retail", "request_cannot_be_handled_within_scope", "a", st, view)["value"])


class TestAirline(unittest.TestCase):
    def test_modification_ids_from_a_worked_output(self):
        pend = {"tool": "update_reservation_baggages",
                "args": {"reservation_id": "4WQ150", "total_baggages": 2, "nonfree_baggages": 0,
                         "payment_id": "gift_card_3576581"}}
        steps = [("user", "My reservation is 4WQ150"), ("call", "get_reservation_details",
                                                          {"reservation_id": "4WQ150"})]
        self.assertTrue(val("airline", "modification_user_and_reservation_ids_established", "b", steps, pend))
        self.assertTrue(val("airline", "modification_user_and_reservation_ids_established", "c", steps, pend))

    def test_modification_ids_only_in_the_call(self):
        pend = {"tool": "update_reservation_baggages",
                "args": {"reservation_id": "4WQ150", "total_baggages": 2, "nonfree_baggages": 0,
                         "payment_id": "gift_card_3576581"}}
        self.assertFalse(val("airline", "modification_user_and_reservation_ids_established", "c",
                             [("user", "add a bag please")], pend))

    def test_nonexistent_reservation_part_false(self):
        pend = {"tool": "update_reservation_baggages",
                "args": {"reservation_id": "ZZZZZZ", "total_baggages": 2, "nonfree_baggages": 0,
                         "payment_id": "gift_card_3576581"}}
        self.assertFalse(val("airline", "modification_user_and_reservation_ids_established", "b",
                             [("user", "chen_jackson_3290")], pend))

    def test_passenger_identity_per_item(self):
        pend = {"tool": "book_reservation", "args": {
            "user_id": "chen_jackson_3290", "origin": "DFW", "destination": "LAX", "flight_type": "one_way",
            "cabin": "economy", "flights": [{"flight_number": "HAT170", "date": "2024-05-22"}],
            "passengers": [{"first_name": "Ana", "last_name": "Diaz", "dob": "1991-12-03"},
                           {"first_name": "Raj", "last_name": "Smith", "dob": "1967-04-01"}],
            "payment_methods": [{"payment_id": "gift_card_3576581", "amount": 100}], "total_baggages": 0,
            "nonfree_baggages": 0, "insurance": "no"}}
        steps = [("user", "Passengers: Ana Diaz, born 12/3/1991, and Raj Smith, born 1 April 1967")]
        hist, st, view = build("airline", steps, pend)
        r = part("airline", "passenger_identity_details_established", "a", st, view)
        self.assertEqual([i["value"] for i in r["items"]], [True, True])
        steps2 = [("user", "Passengers: Ana Diaz, born 12/3/1991, and Raj Smith")]
        hist, st, view = build("airline", steps2, pend)
        r = part("airline", "passenger_identity_details_established", "a", st, view)
        self.assertEqual([i["value"] for i in r["items"]], [True, False])

    def test_booking_route_by_city_or_code(self):
        pend = {"tool": "book_reservation", "args": {"user_id": "chen_jackson_3290", "origin": "DFW",
                                                     "destination": "LAX"}}
        self.assertTrue(val("airline", "booking_required_information_established", "b",
                            [("user", "from Dallas to LAX please")], pend))
        self.assertFalse(val("airline", "booking_required_information_established", "b",
                             [("user", "from dfw to the west coast")], pend))

    def test_insurance_pick(self):
        steps = [("agent", "Do you want travel insurance?"), ("user", "No thanks")]
        hist, st, view = build("airline", steps, {"tool": "book_reservation", "args": {"insurance": "no"}})
        self.assertEqual(MV.insurance_pick(Ctx(st, view)), [0, 1])
        self.assertTrue(part("airline", "booking_insurance_decision_established_and_matched", "a", st,
                             view)["value"])

    def test_cancelled_flight_chain(self):
        steps = [("user", "I am amelia_khan_8728 and my flight in reservation 9FNHDR was cancelled!")]
        p = reply("I'm sorry. As a gold member you can get a $100 certificate.")
        f = "cancelled_flight_certificate_response_conditions_and_amount_met"
        for pid in "abcd":
            self.assertTrue(val("airline", f, pid, steps, p), pid)
        self.assertTrue(val("airline", "pending_response_offers_any_compensation_certificate", "a", steps, p))

    def test_compensation_prohibited_regular_basic_economy(self):
        steps = [("user", "I am liam_johnson_6488; reservation GAOUDL had a cancelled flight")]
        p = reply("Let me check.")
        f = "compensation_is_prohibited_for_relevant_reservation"
        self.assertTrue(val("airline", f, "a", steps, p))
        self.assertTrue(val("airline", f, "b", steps, p))

    def test_send_certificate_amount(self):
        steps = [("user", "I am amelia_khan_8728, reservation 9FNHDR, my flight was cancelled, compensate me")]
        ok = {"tool": "send_certificate", "args": {"user_id": "amelia_khan_8728", "amount": 100}}
        bad = {"tool": "send_certificate", "args": {"user_id": "amelia_khan_8728", "amount": 150}}
        f = "cancelled_flight_certificate_send_conditions_met"
        self.assertTrue(val("airline", f, "e", steps, ok))
        self.assertFalse(val("airline", f, "e", steps, bad))

    def test_offer_screen_without_the_word_certificate(self):
        f = "pending_response_offers_any_compensation_certificate"
        self.assertTrue(val("airline", f, "a", [("user", "x")], reply("As a courtesy I can add 50 dollars of credit.")))
        self.assertFalse(val("airline", f, "a", [("user", "x")], reply("Your flight HAT170 leaves at 9:00.")))

    def test_change_listing_and_pairs(self):
        pend = {"tool": "update_reservation_baggages",
                "args": {"reservation_id": "4WQ150", "total_baggages": 3, "nonfree_baggages": 1,
                         "payment_id": "gift_card_3576581"}}
        steps = [("user", "add bags to 4WQ150"), ("agent", "I will set 3 checked bags, 1 paid by your gift card. OK?"),
                 ("user", "yes")]
        self.assertTrue(val("airline", "pending_database_change_details_listed_and_explicitly_confirmed", "a",
                            steps, pend))
        self.assertTrue(val("airline", "pending_database_change_details_listed_and_explicitly_confirmed", "b",
                            steps, pend))
        steps2 = steps + [("user", "No, wait")]
        self.assertFalse(val("airline", "pending_database_change_details_listed_and_explicitly_confirmed", "b",
                             steps2, pend))


class TestInfoClasses(unittest.TestCase):
    def test_classes(self):
        hist, st, view = build("retail", [("user", "my order W5442520"),
                                          ("call", "get_user_details", {"user_id": OLIVIA})],
                               reply("x"))
        cl = {c["value"]: c for c in IC.classify_text("Order #W5442520, email mia.moore8091@example.com, "
                                                      "example #W0000000", view, st)}
        self.assertIn("user_typed", cl["#w5442520"]["classes"])
        self.assertIn("db_user", cl["mia.moore8091@example.com"]["classes"])
        self.assertEqual(cl["mia.moore8091@example.com"]["users"], [MIA])
        self.assertIn("policy_constant", cl["#w0000000"]["classes"])
        self.assertNotIn("db_user", cl["#w0000000"]["classes"])


if __name__ == "__main__":
    unittest.main()
