"""Tracker v4, agent A5: the code-fact helpers (state_tracker/v4/helpers_v4.py) and A5's fact overlays
(output/eval_v4/overlays/facts_A5_<domain>.json), on made-up conversations with tau-bench's own tool outputs.

The question helpers of questions_v4 (A3) are replaced by doubles for the fact tests (a scripted answer per
question id), so no LLM is called. The go-ahead code of A2 (anchors, fast path, clash) and A1's flight line check run
for real in the booking tests (predicate_table.md: the booking fact uses the shared K1v4 go-ahead). One
class checks that the doubles have the real helpers' signatures and that the overlays validate with the real
modules (skipped when they cannot be imported). $0: no LLM call, no network.

Run from predicate_correctness/:  ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v4_code_facts
"""
from __future__ import annotations

import copy
import importlib
import json
import os
import re
import sys
import unittest

sys.dont_write_bytecode = True

from state_tracker import paths                                # noqa: E402
from state_tracker.v3 import facts_format_v3 as F              # noqa: E402
from state_tracker.v3 import code_helpers                      # noqa: E402,F401  (registers v3 names)
from state_tracker.v3 import message_view as MV                # noqa: E402
from state_tracker.v3 import questions as Q3                   # noqa: E402,F401  (registers v3 names)
from state_tracker.v4 import helpers_v4 as H                   # noqa: E402
from state_tracker.v4 import helpers_go_ahead_v4 as GA          # noqa: E402,F401  (A2: go-ahead names, real)
from tests.test_v3_message_view import (MIA, OLIVIA, OLIVIA_EMAIL, Ctx, build)   # noqa: E402

OVERLAY_DIR = os.path.join(paths.OUTPUT_DIR, "eval_v4", "overlays")
MINE = {
    "retail": {"request_cannot_be_handled_within_scope", "request_is_for_another_user",
               "response_performs_task_for_another_user", "user_specific_information_disclosed"},
    "airline": {"booking_required_information_established", "user_complained_about_relevant_flight_situation",
                "cancelled_flight_certificate_send_conditions_met", "delayed_flight_certificate_send_conditions_met",
                "cancelled_flight_certificate_response_conditions_and_amount_met",
                "delayed_flight_certificate_response_conditions_and_amount_met",
                "pending_response_offers_cancelled_flight_certificate",
                "pending_response_offers_delayed_flight_certificate",
                "pending_response_offers_any_compensation_certificate",
                "request_cannot_be_handled_with_available_tools", "user_explicitly_requested_compensation"},
}
FROZEN_FIELDS = ("rules", "blocking_value", "policy", "who")
GONE_QUESTIONS = {"K2", "K5", "K9", "K11", "K14", "K15"}
V3_QUESTION_HELPERS = re.compile(r"(?<![A-Za-z0-9_])(ask|ask_first_yes|offer_kind|offer_amount_ok)\(")

V3_FACTS = {d: F.load_facts(d) for d in paths.DOMAINS}


def load_overlay(domain):
    with open(os.path.join(OVERLAY_DIR, f"facts_A5_{domain}.json"), encoding="utf-8") as f:
        return json.load(f)


def merge(domain):
    """The v3 fact file with A5's overlay applied (code_change_map.md section 0.3: a part replaces the whole part,
    null removes it; other fields replace the field)."""
    doc = copy.deepcopy(V3_FACTS[domain])
    for fact, change in load_overlay(domain)["facts"].items():
        e = doc["facts"][fact]
        for field, value in change.items():
            if field != "parts":
                e[field] = copy.deepcopy(value)
        for pid, part in (change.get("parts") or {}).items():
            if part is None:
                del e["parts"][pid]
            else:
                e["parts"][pid] = copy.deepcopy(part)
    return doc


MERGED = {d: merge(d) for d in paths.DOMAINS}

# ----------------------------------------------------------------------------------------------- doubles

SCRIPT = {}          # qid -> function(text) -> "yes" | "no" | "unclear"
CALLS = []           # (helper, qid or None, detail)


def _text(ctx, m):
    if isinstance(m, (list, tuple)):
        return " | ".join(_text(ctx, x) for x in m)
    if isinstance(m, int) and not isinstance(m, bool):
        return ctx.view.text(m)
    return str(m)


def _answer(qid, text):
    return SCRIPT.get(qid, lambda t: "no")(text)


def d_ask_first_yes(ctx, qid, candidates, focus=None, items=None, limit=None, on_unclear=None):
    unclear = False
    for c in list(candidates or [])[:limit]:
        t = _text(ctx, c)
        a = _answer(qid, t)
        CALLS.append(("ask_first_yes_v4", qid, t))
        if a == "yes":
            return True
        unclear = unclear or a == "unclear"
    if unclear:
        CALLS.append(("unclear", qid, on_unclear))
        if on_unclear is None:
            raise F.UseBlockingValue(f"{qid}: unclear", kind="unclear")
        return on_unclear
    return False


def d_ask(ctx, qid, *messages, focus=None, items=None, on_unclear=None):
    t = _text(ctx, messages[0])
    a = _answer(qid, t)
    CALLS.append(("ask_v4", qid, t))
    if a == "unclear":
        if on_unclear is None:
            raise F.UseBlockingValue(f"{qid}: unclear", kind="unclear")
        return on_unclear
    return a == "yes"


def d_offer_kind(ctx, reply, kind, db_kinds=None):
    ks = set(db_kinds or [])
    CALLS.append(("offer_kind_v4", kind, sorted(ks)))
    if ("cancelled" in ks) != ("delayed" in ks):
        return kind in ks
    t = _text(ctx, reply).lower()
    if _answer("K12", t) == "no":
        return False
    c, d = "cancel" in t, "delay" in t
    if c != d:
        return c if kind == "cancelled" else d
    return True


def d_offer_amount_ok(ctx, reply, rate, counts):
    CALLS.append(("offer_amount_ok_v4", rate, list(counts)))
    amounts = [float(x) for x in re.findall(r"\$(\d+(?:\.\d+)?)", _text(ctx, reply))]
    return not amounts or any(abs(a - rate * n) < 0.005 for a in amounts for n in counts)


# name -> (double, min, max, keywords, source): the real helpers' signatures (checked in TestRealModules)
DOUBLES = {
    "ask_v4": (d_ask, 2, 3, ("focus", "items", "on_unclear"), "question"),
    "ask_first_yes_v4": (d_ask_first_yes, 2, 2, ("focus", "items", "limit", "on_unclear"), "question"),
    "offer_kind_v4": (d_offer_kind, 2, 3, (), "question"),
    "offer_amount_ok_v4": (d_offer_amount_ok, 3, 3, (), "structure"),
}


class WithDoubles(unittest.TestCase):
    """Swaps the doubles into the shared helper registry for the class, and puts the real helpers back after."""
    saved = {}

    @classmethod
    def setUpClass(cls):
        cls.saved = {}
        for name, (func, lo, hi, kws, src) in DOUBLES.items():
            old = F.registered_names().get(name)
            if old is not None:
                cls.saved[name] = old
                F.unregister_name(name)
            F.register_name(name, func, lo, hi, kws, source=src)

    @classmethod
    def tearDownClass(cls):
        for name in DOUBLES:
            F.unregister_name(name)
            old = cls.saved.get(name)
            if old is not None:
                F.register_name(old.name, old.func, old.min_args, old.max_args, old.keywords, old.source, old.doc)

    def setUp(self):
        SCRIPT.clear()
        CALLS.clear()

    def fact(self, domain, name, steps, pending):
        hist, st, view = build(domain, steps, pending)
        return F.evaluate(MERGED[domain]["facts"][name], st, None, view=view, answers=object(), name=name)

    def asked(self, qid=None):
        return [c for c in CALLS if c[0] in ("ask_v4", "ask_first_yes_v4") and (qid is None or c[1] == qid)]


def reply(text):
    return {"tool": "respond", "args": {"content": text}}


def ctx(domain, steps, pending=None):
    hist, st, view = build(domain, steps, pending)
    return Ctx(st, view)


LOGIN = [("user", "Hi, my email is " + OLIVIA_EMAIL), ("call", "find_user_id_by_email", {"email": OLIVIA_EMAIL})]
TRANSFER = {"tool": "transfer_to_human_agents", "args": {"summary": "x"}}

# ----------------------------------------------------------------------------------------------- overlay files


class TestOverlayFiles(unittest.TestCase):
    def test_owned_facts_and_top_fields(self):
        for d in paths.DOMAINS:
            ov = load_overlay(d)
            self.assertEqual(ov["domain"], d)
            self.assertEqual(ov["by"], "A5")
            self.assertLessEqual(set(ov), {"domain", "by", "facts", "_about"})
            self.assertEqual(set(ov["facts"]), MINE[d])

    def test_no_frozen_field_and_no_rename(self):
        for d in paths.DOMAINS:
            for fact, change in load_overlay(d)["facts"].items():
                self.assertFalse(set(change) & set(FROZEN_FIELDS), fact)
            self.assertEqual(set(MERGED[d]["facts"]), set(V3_FACTS[d]["facts"]))
            for fact, e in MERGED[d]["facts"].items():
                v3 = V3_FACTS[d]["facts"][fact]
                for k in FROZEN_FIELDS:
                    self.assertEqual(e.get(k), v3.get(k), (fact, k))
                if fact not in MINE[d]:
                    self.assertEqual(e, v3, fact)

    def test_no_v3_question_helper_and_no_dropped_question(self):
        for d in paths.DOMAINS:
            for fact in MINE[d]:
                for pid, p in MERGED[d]["facts"][fact]["parts"].items():
                    self.assertIsNone(V3_QUESTION_HELPERS.search(p["expr"]), (fact, pid, p["expr"]))
                    self.assertNotIn(p.get("question"), GONE_QUESTIONS, (fact, pid))
                    for k in re.findall(r"'(K\d+)'", p["expr"]):
                        self.assertNotIn(k, GONE_QUESTIONS, (fact, pid))

    def test_on_unclear_allows_for_k4_k13_k16_only(self):
        for d in paths.DOMAINS:
            for fact in MINE[d]:
                e = MERGED[d]["facts"][fact]
                for pid, p in e["parts"].items():
                    m = re.search(r"on_unclear=(True|False)", p["expr"])
                    qids = set(re.findall(r"'(K\d+)'", p["expr"]))
                    if qids & {"K4", "K13", "K16"}:
                        self.assertIsNotNone(m, (fact, pid))
                        self.assertEqual(m.group(1) == "True", not e["blocking_value"], (fact, pid))
                    else:
                        self.assertIsNone(m, (fact, pid))

    def test_code_only_facts(self):
        for name in ("response_performs_task_for_another_user", "user_specific_information_disclosed"):
            e = MERGED["retail"]["facts"][name]
            self.assertEqual((e["combine"], e["sources"], list(e["parts"])), ("a", ["structure"], ["a"]))
            self.assertEqual(e["parts"]["a"], V3_FACTS["retail"]["facts"][name]["parts"]["a"])
            self.assertNotIn("reply_names_other_db_user_v4", json.dumps(e))
        e = MERGED["airline"]["facts"]["booking_required_information_established"]
        self.assertEqual(e["combine"], "a AND (b OR (c AND g AND h)) AND (d OR (e AND g AND h))")
        self.assertEqual(e["parts"]["a"], V3_FACTS["airline"]["facts"]["booking_required_information_established"]["parts"]["a"])
        self.assertEqual(e["parts"]["g"]["expr"],
                         "go_ahead_fast_v4() or ask_first_yes_v4('K1', go_ahead_candidates_v4(), limit=2)")


class TestValidateWithDoubles(WithDoubles):
    def test_merged_files_validate(self):
        for d in paths.DOMAINS:
            self.assertEqual(F.validate(MERGED[d], d), [], d)


class TestRealModules(unittest.TestCase):
    """The doubles have the real signatures; the overlays validate with the real v4 modules (when importable)."""

    def setUp(self):
        try:
            importlib.import_module("state_tracker.v4.questions_v4")
        except Exception as e:  # noqa: BLE001
            self.skipTest(f"a v4 module of another agent does not import yet: {type(e).__name__}: {e}")

    def test_double_signatures_equal_the_real_ones(self):
        reg = F.registered_names()
        for name, (_, lo, hi, kws, src) in DOUBLES.items():
            h = reg[name]
            self.assertEqual((h.min_args, h.max_args, set(h.keywords), h.source), (lo, hi, set(kws), src), name)

    def test_merged_files_validate_with_the_real_helpers(self):
        for d in paths.DOMAINS:
            self.assertEqual(F.validate(MERGED[d], d), [], d)


# ----------------------------------------------------------------------------------------------- helpers


class TestReplyNamesOtherUser(unittest.TestCase):
    def val(self, steps, text):
        c = ctx("retail", steps, reply(text))
        return H.reply_names_other_db_user_v4(c), c.notes

    def test_other_users_full_name(self):
        v, notes = self.val(LOGIN, "I also see an account for Mia Moore.")
        self.assertTrue(v)
        self.assertEqual(notes[-1], {"other_db_user": [{"kind": "name"}]})
        self.assertNotIn("Mia", json.dumps(notes))

    def test_other_users_email(self):
        self.assertTrue(self.val(LOGIN, "That account is mia.moore8091@example.com.")[0])

    def test_name_the_user_said_first(self):
        steps = LOGIN + [("user", "Can you look at Mia Moore's order?")]
        self.assertFalse(self.val(steps, "I cannot help with Mia Moore's order.")[0])

    def test_own_name_first_name_and_public_name(self):
        self.assertFalse(self.val(LOGIN, "Thanks, Olivia Ito.")[0])
        self.assertFalse(self.val(LOGIN, "Mia, your order is on its way.")[0])
        self.assertFalse(self.val(LOGIN, "That poem is by Robert Frost.")[0])

    def test_shared_full_name_is_mine(self):
        db = MV._initial_db("retail")["users"]
        same = sorted(u for u, x in db.items() if (x["name"]["first_name"], x["name"]["last_name"]) == ("Olivia", "Smith"))
        self.assertGreaterEqual(len(same), 2)
        email = db[same[0]]["email"]
        steps = [("user", "my email is " + email), ("call", "find_user_id_by_email", {"email": email})]
        self.assertFalse(self.val(steps, "Welcome back, Olivia Smith.")[0])

    def test_before_login_and_not_a_reply(self):
        self.assertFalse(self.val([("user", "hi")], "Is your name Mia Moore?")[0])
        c = ctx("retail", LOGIN, {"tool": "get_user_details", "args": {"user_id": MIA}})
        self.assertFalse(H.reply_names_other_db_user_v4(c))


class TestOtherPersonPrecondition(unittest.TestCase):
    def val(self, steps, tool, args):
        return H.other_person_precondition_v4(ctx("retail", steps, {"tool": tool, "args": args}))

    def test_own_email_login_no_reason(self):
        self.assertFalse(self.val([("user", "Hi, my email is " + OLIVIA_EMAIL)], "find_user_id_by_email",
                                  {"email": OLIVIA_EMAIL}))

    def test_own_name_zip_login_no_reason(self):
        self.assertFalse(self.val([("user", "I'm Olivia Ito, zip 80218.")], "find_user_id_by_name_zip",
                                  {"first_name": "Olivia", "last_name": "Ito", "zip": "80218"}))

    def test_relation_word_fires(self):
        steps = [("user", "I need help with my wife's order."), ("agent", "Email?"), ("user", OLIVIA_EMAIL)]
        self.assertTrue(self.val(steps, "find_user_id_by_email", {"email": OLIVIA_EMAIL}))

    def test_value_not_typed_by_the_user_fires(self):
        self.assertTrue(self.val([("user", "my email is " + OLIVIA_EMAIL)], "find_user_id_by_email",
                                 {"email": "mia.moore8091@example.com"}))
        self.assertTrue(self.val([("user", "I'm Olivia Ito")], "find_user_id_by_name_zip",
                                 {"first_name": "Olivia", "last_name": "Ito", "zip": "80218"}))

    def test_after_login_and_other_calls_false(self):
        self.assertFalse(self.val(LOGIN + [("user", "my friend's email is mia.moore8091@example.com")],
                                  "find_user_id_by_email", {"email": "mia.moore8091@example.com"}))
        self.assertFalse(self.val(LOGIN + [("user", "my son's order")], "get_order_details", {"order_id": "#W5442520"}))

    def test_catalog_read_latest_message(self):
        p = {"product_id": "5713490933"}
        self.assertTrue(self.val(LOGIN + [("user", "my son wants a gaming mouse")], "get_product_details", p))
        self.assertFalse(self.val(LOGIN + [("user", "I want a gaming mouse")], "get_product_details", p))

    def test_missing_argument(self):
        with self.assertRaises(F.MissingArgument):
            self.val([("user", "hi")], "find_user_id_by_email", {})


class TestAirports(unittest.TestCase):
    def named(self, text, code):
        return H.user_named_airport_v4(ctx("airline", [("user", text)]), code)

    def test_code_and_city(self):
        self.assertTrue(self.named("from Dallas to LAX please", "DFW"))
        self.assertTrue(self.named("from Dallas to LAX please", "LAX"))
        self.assertTrue(self.named("fly me to las vegas", "LAS"))
        self.assertTrue(self.named("LaGuardia, please", "LGA"))
        self.assertFalse(self.named("from jfk", "JFK"))                  # a code counts only in upper case
        self.assertFalse(self.named("from LAX", "LAS"))

    def test_metro_names(self):
        for code in ("JFK", "LGA", "EWR"):
            self.assertTrue(self.named("I live in NYC", code))
            self.assertTrue(self.named("leaving from new york", code))
        self.assertTrue(self.named("to LA on Friday", "LAX"))
        self.assertFalse(self.named("la la land", "LAX"))                # short names only in upper case
        self.assertTrue(self.named("going to Vegas", "LAS"))
        self.assertTrue(self.named("la guardia airport", "LGA"))
        self.assertTrue(self.named("visiting Philly", "PHL"))
        self.assertFalse(self.named("visiting Philly", "PHX"))

    def test_agent_words_and_bad_code(self):
        c = ctx("airline", [("user", "a flight please"), ("agent", "From DFW to LAX?")])
        self.assertFalse(H.user_named_airport_v4(c, "DFW"))
        self.assertFalse(H.user_named_airport_v4(c, None))


def booking(ftype, flights, origin="DFW", destination="LAX", user="chen_jackson_3290"):
    return {"tool": "book_reservation", "args": {
        "user_id": user, "origin": origin, "destination": destination, "flight_type": ftype, "cabin": "economy",
        "flights": [{"flight_number": n, "date": d} for n, d in flights],
        "passengers": [{"first_name": "Chen", "last_name": "Jackson", "dob": "1956-07-07"}],
        "payment_methods": [{"payment_id": "gift_card_3576581", "amount": 100}], "total_baggages": 0,
        "nonfree_baggages": 0, "insurance": "no"}}


OUT = ("HAT170", "2024-05-22")          # DFW -> LAX
BACK = ("HAT022", "2024-05-26")         # LAX -> DFW


class TestTripFits(unittest.TestCase):
    def fits(self, pending):
        return H.trip_fits_v4(ctx("airline", [("user", "book it")], pending))

    def test_one_way_and_round_trip(self):
        self.assertTrue(self.fits(booking("one_way", [OUT])))
        self.assertTrue(self.fits(booking("round_trip", [OUT, BACK])))
        self.assertTrue(self.fits(booking("round_trip", [BACK, OUT])))          # any order in the call

    def test_one_stop_chain_in_any_order(self):
        legs = [("HAT287", "2024-05-24"), ("HAT235", "2024-05-24")]             # CLT -> BOS -> MCO
        self.assertTrue(self.fits(booking("one_way", legs, "CLT", "MCO")))
        self.assertTrue(self.fits(booking("one_way", legs[::-1], "CLT", "MCO")))
        self.assertFalse(self.fits(booking("one_way", legs[:1], "CLT", "MCO")))

    def test_mismatches(self):
        self.assertFalse(self.fits(booking("round_trip", [OUT])))
        self.assertFalse(self.fits(booking("one_way", [OUT, BACK])))
        self.assertFalse(self.fits(booking("one_way", [OUT], origin="JFK")))
        self.assertFalse(self.fits(booking("multi_city", [OUT])))
        self.assertFalse(self.fits(booking("one_way", [])))

    def test_unknown_flight_is_nonexistent(self):
        with self.assertRaises(F.MissingObject):
            self.fits(booking("one_way", [("HAT999", "2024-05-22")]))


class TestOfferDbKinds(unittest.TestCase):
    def kinds(self, text):
        return H.offer_db_kinds_v4(ctx("airline", [("user", text)], reply("x")))

    def test_one_kind(self):
        self.assertEqual(self.kinds("I am amelia_khan_8728, reservation 9FNHDR"), ["cancelled"])
        self.assertEqual(self.kinds("I am liam_ito_4473, reservation LWTEDF"), ["delayed"])

    def test_both_kinds_and_none(self):
        self.assertEqual(self.kinds("I am lucas_sanchez_1853, reservation GCZ58I"), ["cancelled", "delayed"])
        self.assertEqual(self.kinds("I am amelia_khan_8728"), [])

    def test_eligible_reservations_first(self):
        # GAOUDL: cancelled flight, regular member, no insurance, basic economy (not eligible);
        # LWTEDF: delayed flight, silver member (eligible)
        self.assertEqual(self.kinds("I am liam_johnson_6488 (GAOUDL) and liam_ito_4473 (LWTEDF)"), ["delayed"])
        self.assertEqual(self.kinds("I am liam_johnson_6488, reservation GAOUDL"), ["cancelled"])


class TestTransferCodePaths(unittest.TestCase):
    def test_user_not_found(self):
        bad = [("call", "find_user_id_by_email", {"email": "nobody1@example.com"}),
               ("call", "find_user_id_by_email", {"email": "nobody2@example.com"})]
        steps = [("user", "I am nobody")]
        self.assertTrue(H.user_not_found_v4(ctx("retail", steps + bad, TRANSFER)))
        self.assertFalse(H.user_not_found_v4(ctx("retail", steps + bad[:1], TRANSFER)))
        self.assertFalse(H.user_not_found_v4(ctx("retail", steps + bad + LOGIN[1:], TRANSFER)))

    def test_cancel_attempted(self):
        steps = [("user", "I am amelia_davis_8890, cancel I6M8JQ"),
                 ("call", "cancel_reservation", {"reservation_id": "I6M8JQ"})]
        c = ctx("airline", steps, TRANSFER)
        self.assertTrue(H.cancel_attempted_v4(c, ["I6M8JQ"]))
        self.assertFalse(H.cancel_attempted_v4(c, ["9FNHDR"]))
        self.assertFalse(H.cancel_attempted_v4(ctx("airline", steps[:1], TRANSFER), ["I6M8JQ"]))


# ----------------------------------------------------------------------------------------------- retail facts


class TestRetailFacts(WithDoubles):
    def test_scope_k13_reads_every_user_message(self):
        SCRIPT["K13"] = lambda t: "yes" if "free replacement" in t else "no"
        steps = [("user", "Send me a free replacement and a store credit."), ("agent", "a"), ("user", "b"),
                 ("agent", "c"), ("user", "ok")]
        r = self.fact("retail", "request_cannot_be_handled_within_scope", steps, TRANSFER)
        self.assertIs(r["value"], True)
        self.assertEqual(len(self.asked("K13")), 3)                    # the oldest message is in the window

    def test_scope_k13_no_and_unclear(self):
        steps = [("user", "change my address")]
        r = self.fact("retail", "request_cannot_be_handled_within_scope", steps, TRANSFER)
        self.assertIs(r["value"], False)
        SCRIPT["K13"] = lambda t: "unclear"
        r = self.fact("retail", "request_cannot_be_handled_within_scope", steps, TRANSFER)
        self.assertIs(r["value"], True)                                 # unclear -> allow + log
        self.assertIn(("unclear", "K13", True), CALLS)

    def test_scope_user_not_found_needs_no_question(self):
        steps = [("user", "I am nobody"), ("call", "find_user_id_by_email", {"email": "nobody1@example.com"}),
                 ("call", "find_user_id_by_name_zip", {"first_name": "No", "last_name": "Body", "zip": "00000"})]
        r = self.fact("retail", "request_cannot_be_handled_within_scope", steps, TRANSFER)
        self.assertIs(r["value"], True)
        self.assertEqual(self.asked(), [])

    def test_another_user_own_login_asks_nothing(self):
        r = self.fact("retail", "request_is_for_another_user", [("user", "Hi, my email is " + OLIVIA_EMAIL)],
                      {"tool": "find_user_id_by_email", "args": {"email": OLIVIA_EMAIL}})
        self.assertIs(r["value"], False)
        self.assertEqual(self.asked(), [])

    def test_another_user_relation_asks_k4(self):
        steps = [("user", "I want to check my wife's order, her email is " + OLIVIA_EMAIL)]
        p = {"tool": "find_user_id_by_email", "args": {"email": OLIVIA_EMAIL}}
        SCRIPT["K4"] = lambda t: "yes"
        self.assertIs(self.fact("retail", "request_is_for_another_user", steps, p)["value"], True)
        self.assertEqual(len(self.asked("K4")), 1)
        SCRIPT["K4"] = lambda t: "unclear"
        r = self.fact("retail", "request_is_for_another_user", steps, p)
        self.assertIs(r["value"], False)                                # unclear -> allow + log
        self.assertIn(("unclear", "K4", False), CALLS)

    def test_another_user_order_by_database(self):
        mia_order = MV._initial_db("retail")["users"][MIA]["orders"][0]
        r = self.fact("retail", "request_is_for_another_user", LOGIN + [("user", "order " + mia_order)],
                      {"tool": "get_order_details", "args": {"order_id": mia_order}})
        self.assertIs(r["value"], True)
        self.assertEqual(self.asked(), [])

    def test_reply_for_another_user_by_code_only(self):
        f = "response_performs_task_for_another_user"
        # part a alone (main chat decision): a name without another user's data value does not count
        self.assertIs(self.fact("retail", f, LOGIN, reply("I also found Mia Moore's account."))["value"], False)
        self.assertIs(self.fact("retail", f, LOGIN, reply("That's Shakespeare's Sonnet 18."))["value"], False)
        self.assertIs(self.fact("retail", f, LOGIN, reply("It is mia.moore8091@example.com."))["value"], True)
        self.assertEqual(self.asked(), [])

    def test_disclosure_by_code_only(self):
        f = "user_specific_information_disclosed"
        steps = [("user", "Hi, I need my orders"), ("call", "get_user_details", {"user_id": OLIVIA})]
        self.assertIs(self.fact("retail", f, steps, reply("Your orders are #W5866402 and #W5353646."))["value"], True)
        self.assertIs(self.fact("retail", f, [("user", "hi")], reply("Please give me your email first."))["value"],
                      False)
        # a database value no tool output showed: v3 left it to K14; v4 code says false
        self.assertIs(self.fact("retail", f, [("user", "hi")], reply("Is your order #W5866402?"))["value"], False)
        self.assertEqual(self.asked(), [])


# ----------------------------------------------------------------------------------------------- airline facts

AMELIA = [("user", "I am amelia_khan_8728 and my flight in reservation 9FNHDR was cancelled! This is awful.")]
LIAM_CHANGED = [("user", "I am liam_ito_4473, reservation LWTEDF. My flight is delayed, this is terrible, "
                         "please add a bag."),
                ("call", "update_reservation_baggages", {"reservation_id": "LWTEDF", "total_baggages": 1,
                                                         "nonfree_baggages": 0, "payment_id": "credit_card_5260935"})]
COMPLAINT = lambda t: "yes" if ("awful" in t or "terrible" in t) else "no"   # noqa: E731


LISTING_TEXT = ("I can book flight HAT170 on May 22 from Dallas (DFW) to Los Angeles (LAX), economy, for Chen "
                "Jackson, paid with your gift card. Shall I book it?")


class TestAirlineBooking(WithDoubles):
    F_ = "booking_required_information_established"
    ME = ("user", "I am chen_jackson_3290 and I need a flight.")

    def val(self, steps, pending):
        return self.fact("airline", self.F_, steps, pending)["value"]

    def test_user_words_need_no_go_ahead(self):
        steps = [("user", "I am chen_jackson_3290, one way from Dallas to Los Angeles please")]
        self.assertIs(self.val(steps, booking("one_way", [OUT])), True)
        self.assertEqual(self.asked(), [])

    def test_listing_with_route_and_trip_phrase_and_plain_yes(self):
        steps = [self.ME, ("agent", LISTING_TEXT.replace("economy", "one way, economy")), ("user", "Yes.")]
        self.assertIs(self.val(steps, booking("one_way", [OUT])), True)
        self.assertEqual(self.asked(), [])                                   # fast path D8: no K1 call

    def test_listing_go_ahead_by_k1(self):
        steps = [self.ME, ("agent", LISTING_TEXT), ("user", "Alright, that all sounds right to me, book it.")]
        SCRIPT["K1"] = lambda t: "yes"
        self.assertIs(self.val(steps, booking("one_way", [OUT])), True)      # trip: L names HAT170 + date, fits
        self.assertEqual(len(self.asked("K1")), 1)
        SCRIPT["K1"] = lambda t: "no"
        self.assertIs(self.val(steps, booking("one_way", [OUT])), False)

    def test_listing_flights_must_fit(self):
        steps = [self.ME, ("agent", LISTING_TEXT), ("user", "Yes.")]
        self.assertIs(self.val(steps, booking("round_trip", [OUT])), False)  # no return leg, no round-trip phrase

    def test_strict_no_after_listing(self):
        steps = [self.ME, ("agent", LISTING_TEXT), ("user", "No, wait.")]
        self.assertIs(self.val(steps, booking("one_way", [OUT])), False)

    def test_no_route_and_no_listing(self):
        self.assertIs(self.val([("user", "I am chen_jackson_3290, a one way trip west")], booking("one_way", [OUT])),
                      False)

    def test_user_id_not_obtained(self):
        self.assertIs(self.val([("user", "a one way trip from Dallas to Los Angeles")], booking("one_way", [OUT])),
                      False)


class TestBookingHelpers(unittest.TestCase):
    def c(self, steps, pending):
        return ctx("airline", steps, pending)

    def test_route_trip_and_flights_in_anchor(self):
        c = self.c([("agent", LISTING_TEXT), ("user", "ok")], booking("one_way", [OUT]))
        self.assertTrue(H.anchor_names_route_v4(c, [0]))
        self.assertTrue(H.anchor_names_flights_v4(c, [0]))
        self.assertFalse(H.trip_type_stated_v4(c, [0]))
        self.assertFalse(H.anchor_names_route_v4(c, []))
        c2 = self.c([("agent", "HAT170 on May 23 to LAX"), ("user", "ok")], booking("one_way", [OUT]))
        self.assertFalse(H.anchor_names_flights_v4(c2, [0]))                 # wrong date
        self.assertFalse(H.anchor_names_route_v4(c2, [0]))                   # no origin

    def test_trip_phrases(self):
        for text, ftype, want in (("a round-trip please", "round_trip", True), ("return flight on the 26th",
                                  "round_trip", True), ("one way only", "one_way", True), ("oneway", "one_way", True),
                                  ("one way", "round_trip", False), ("round trip", "multi", False)):
            c = self.c([("user", text)], booking(ftype, [OUT]))
            self.assertIs(H.trip_type_stated_v4(c, []), want, text)


class TestAirlineCompensation(WithDoubles):
    def test_complaint_merged_k8(self):
        f = "user_complained_about_relevant_flight_situation"
        steps = AMELIA + [("agent", "Let me check."), ("user", "ok")]
        SCRIPT["K8"] = COMPLAINT
        self.assertIs(self.fact("airline", f, steps, reply("I'm sorry."))["value"], True)
        self.assertEqual({c[1] for c in self.asked()}, {"K8"})
        SCRIPT["K8"] = lambda t: "no"
        self.assertIs(self.fact("airline", f, steps, reply("I'm sorry."))["value"], False)
        SCRIPT["K8"] = lambda t: "unclear"
        r = self.fact("airline", f, steps, reply("I'm sorry."))
        self.assertIs(r["value"], False)
        self.assertEqual(r["problems"][0]["kind"], "unclear")

    def test_cancelled_send(self):
        f = "cancelled_flight_certificate_send_conditions_met"
        SCRIPT["K8"] = COMPLAINT
        ok = {"tool": "send_certificate", "args": {"user_id": "amelia_khan_8728", "amount": 100}}
        self.assertIs(self.fact("airline", f, AMELIA, ok)["value"], True)
        SCRIPT["K8"] = lambda t: "no"
        self.assertIs(self.fact("airline", f, AMELIA, ok)["value"], False)

    def test_delayed_send_needs_the_change_not_k11(self):
        f = "delayed_flight_certificate_send_conditions_met"
        SCRIPT["K8"] = COMPLAINT
        p = {"tool": "send_certificate", "args": {"user_id": "liam_ito_4473", "amount": 50}}
        self.assertIs(self.fact("airline", f, LIAM_CHANGED, p)["value"], True)
        self.assertEqual({c[1] for c in self.asked()}, {"K8"})               # K9 and K11 are gone
        self.assertIs(self.fact("airline", f, LIAM_CHANGED[:1], p)["value"], False)   # no change yet (event)

    def test_cancelled_response_amount_from_every_dollar_amount(self):
        f = "cancelled_flight_certificate_response_conditions_and_amount_met"
        SCRIPT["K8"] = COMPLAINT
        self.assertIs(self.fact("airline", f, AMELIA, reply("I can send a $100 certificate."))["value"], True)
        self.assertIn(("offer_amount_ok_v4", 100, [1]), CALLS)
        self.assertIs(self.fact("airline", f, AMELIA, reply("I can send a $150 certificate."))["value"], False)

    def test_delayed_response(self):
        f = "delayed_flight_certificate_response_conditions_and_amount_met"
        SCRIPT["K8"] = COMPLAINT
        self.assertIs(self.fact("airline", f, LIAM_CHANGED, reply("Here is a $50 certificate."))["value"], True)
        self.assertIn(("offer_amount_ok_v4", 50, [1]), CALLS)
        self.assertIs(self.fact("airline", f, LIAM_CHANGED[:1], reply("Here is a $50 certificate."))["value"], False)

    def test_offer_kind_from_the_database(self):
        SCRIPT["K12"] = lambda t: "yes"
        p = reply("As a gesture I can send you a certificate.")
        c = self.fact("airline", "pending_response_offers_cancelled_flight_certificate", AMELIA, p)
        d = self.fact("airline", "pending_response_offers_delayed_flight_certificate", AMELIA, p)
        self.assertEqual((c["value"], d["value"]), (True, False))
        self.assertIn(("offer_kind_v4", "cancelled", ["cancelled"]), CALLS)

    def test_offer_kind_both_in_database_uses_quote_words(self):
        SCRIPT["K12"] = lambda t: "yes"
        steps = [("user", "I am lucas_sanchez_1853, reservation GCZ58I")]
        p = reply("For the delay, I can send you a certificate.")
        c = self.fact("airline", "pending_response_offers_cancelled_flight_certificate", steps, p)
        d = self.fact("airline", "pending_response_offers_delayed_flight_certificate", steps, p)
        self.assertEqual((c["value"], d["value"]), (False, True))

    def test_any_compensation(self):
        f = "pending_response_offers_any_compensation_certificate"
        SCRIPT["K12"] = lambda t: "yes"
        self.assertIs(self.fact("airline", f, AMELIA, reply("I can offer a $100 certificate."))["value"], True)
        self.assertEqual({c[1] for c in self.asked()}, {"K12"})
        CALLS.clear()
        self.assertIs(self.fact("airline", f, AMELIA, reply("Your flight HAT216 leaves at 9:00."))["value"], False)
        self.assertEqual(self.asked(), [])                                   # the screen did not hit

    def test_explicit_compensation_request(self):
        f = "user_explicitly_requested_compensation"
        steps = AMELIA + [("agent", "Sorry."), ("user", "I want compensation for this.")]
        SCRIPT["K10"] = lambda t: "yes" if "compensation" in t else "no"
        self.assertIs(self.fact("airline", f, steps, reply("ok"))["value"], True)
        SCRIPT["K10"] = lambda t: "no"
        self.assertIs(self.fact("airline", f, steps, reply("ok"))["value"], False)


class TestAirlineTransfer(WithDoubles):
    F_ = "request_cannot_be_handled_with_available_tools"
    FLOWN = [("user", "I am amelia_davis_8890. Please cancel my trip I6M8JQ.")]

    def test_k13_yes(self):
        SCRIPT["K13"] = lambda t: "yes"
        self.assertIs(self.fact("airline", self.F_, [("user", "Book me a hotel.")], TRANSFER)["value"], True)

    def test_k13_unclear_allows(self):
        SCRIPT["K13"] = lambda t: "unclear"
        self.assertIs(self.fact("airline", self.F_, [("user", "hmm")], TRANSFER)["value"], True)
        self.assertIn(("unclear", "K13", True), CALLS)

    def test_flown_and_cancel_attempt_needs_no_question(self):
        steps = self.FLOWN + [("call", "cancel_reservation", {"reservation_id": "I6M8JQ"})]
        r = self.fact("airline", self.F_, steps, TRANSFER)
        self.assertIs(r["value"], True)
        self.assertEqual(self.asked(), [])

    def test_flown_k16(self):
        SCRIPT["K16"] = lambda t: "yes" if "cancel" in t else "no"
        self.assertIs(self.fact("airline", self.F_, self.FLOWN, TRANSFER)["value"], True)
        self.assertTrue(self.asked("K16"))
        SCRIPT["K16"] = lambda t: "unclear"
        self.assertIs(self.fact("airline", self.F_, self.FLOWN, TRANSFER)["value"], True)
        self.assertIn(("unclear", "K16", True), CALLS)

    def test_no_flown_reservation_no_k16(self):
        SCRIPT["K16"] = lambda t: "yes"
        r = self.fact("airline", self.F_, AMELIA, TRANSFER)
        self.assertIs(r["value"], False)
        self.assertEqual(self.asked("K16"), [])


if __name__ == "__main__":
    unittest.main()
