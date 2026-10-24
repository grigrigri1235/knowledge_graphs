"""Tests for tracker v3 part 6: the database, event and argument parts of the v3 facts (P6.5) and the nonexistent-id
check of p5 (P5.4).

The expressions are the p6 overlays (output/eval_v3/p6_parts/exprs_<domain>.json), merged in memory into the fact files
(scoring/v3_p6_agreement.py merged_facts; the fact files are never written). The helper names are
state_tracker/v3/code_helpers.py. Each test builds a tiny conversation whose tool outputs are made by τ-bench's own
tool code on a separate copy of the data (as tests/test_state.py), then evaluates a fact for a pending call. Where a
τ-bench write tool decides the same thing, the test also runs the tool on a copy of the state
(state_tracker/v3/tool_check.py) and compares. The objects are picked from the τ-bench data files by plain data facts
(an order's status, a flight's status on a date), never from judge answers. Some tests change a value in the state's
own database copy (a balance, a price, a created_at) to reach an edge; the data files are never changed.

For each fact with a p6 part: true, false, a nonexistent id, a missing argument, and each fixed reading of p5:
  - the signed price difference (a refund needs no gift-card balance);
  - each tool's own rounding (exchange rounds the difference to cents; modify items and modify payment do not);
  - an exchange / modification for the same item is blocked;
  - the reservation's cabin is the cabin of the last worked flight update (τ-bench never updates the cabin field);
  - a past segment with status "cancelled" was not flown;
  - "not a gift card": the gift-card balance fact is false and the rule's other branch holds.

Run from predicate_correctness/:  python3 -B -m unittest tests.test_v3_code_facts -v
Standard library only. No LLM call, no network.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import unittest

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from scoring import v3_p6_agreement as P6              # noqa: E402
from state_tracker import state as S                    # noqa: E402
from state_tracker.v3 import code_helpers as CH        # noqa: E402
from state_tracker.v3 import facts_format_v3 as F      # noqa: E402
from state_tracker.v3 import tool_check as TC          # noqa: E402

_CACHE: dict = {}


def docs(domain):
    if ("doc", domain) not in _CACHE:
        _CACHE[("doc", domain)] = P6.merged_facts(domain)
    return _CACHE[("doc", domain)]


def data(domain):
    if ("db", domain) not in _CACHE:
        _CACHE[("db", domain)] = S.load_db(domain)
    return _CACHE[("db", domain)]


def rs():
    if "rs" not in _CACHE:
        _CACHE["rs"] = P6.retail_sample()
    return _CACHE["rs"]


def state(domain, calls, tool, args):
    return P6.state_for(domain, calls, tool, args)


def ev(domain, fact, st, args=None, part=None):
    """The fact (code-only) or one p6 part of it, for the state's pending call (or the given args)."""
    return P6.evaluate_code(docs(domain), fact, st, args, part)


def kinds(r):
    return sorted({p["kind"] for p in r["problems"]})


def label(st, fact, call=None):
    """τ-bench's own label of a fact for the state's pending call (or `call`), from tool_check on a copy."""
    return TC.check(st, call)["facts"].get(fact)


def rule(domain, rid):
    return next(r for r in P6.rule_table(domain)["rules"] if r["id"] == rid)


class Base(unittest.TestCase):
    domain = "retail"

    def value(self, fact, st, want, part=None, args=None, problems=()):
        r = ev(self.domain, fact, st, args, part)
        self.assertIs(r["value"], want, f"{fact} {part}: {r['parts']} {r['problems']}")
        self.assertEqual(kinds(r), sorted(problems), f"{fact} {part}: problems {r['problems']}")
        return r


# ================================================================================================ retail
def login():
    return [("find_user_id_by_email", {"email": rs()["email"]})]


def another_order(status=None):
    db = data("retail")
    return next(o for o in sorted(db["orders"]) if db["orders"][o]["user_id"] != rs()["user"]
                and (status is None or db["orders"][o]["status"] == status))


def other_product_variant(product_id):
    db = data("retail")
    return next(v for p in sorted(db["products"]) if p != product_id
                for v, x in sorted(db["products"][p]["variants"].items()) if x["available"])


class TestArgumentFacts(Base):
    def test_reason_allowed(self):
        oid = rs()["pending"]
        for reason, want in (("no longer needed", True), ("ordered by mistake", True), ("too expensive", False),
                             ("No longer needed", False)):
            args = {"order_id": oid, "reason": reason}
            st = state("retail", login(), "cancel_pending_order", args)
            self.value("cancellation_reason_is_allowed", st, want)
            lab = TC.check(st)
            self.assertEqual(lab["check"] == "invalid_reason", not want)          # τ-bench's own exact test
        st = state("retail", login(), "cancel_pending_order", {"order_id": oid})
        self.value("cancellation_reason_is_allowed", st, False, problems=["missing_argument"])

    def test_payment_method_is_gift_card(self):
        for pid, want in (("gift_card_0000000", True), (rs()["gc"], True), ("credit_card_1", False),
                          ("paypal_1", False)):
            st = state("retail", login(), "modify_pending_order_payment",
                       {"order_id": rs()["pending"], "payment_method_id": pid})
            self.value("payment_method_is_gift_card", st, want)
        st = state("retail", login(), "modify_pending_order_payment", {"order_id": rs()["pending"]})
        self.value("payment_method_is_gift_card", st, True, problems=["missing_argument"])    # blocking value true
        st = state("retail", login(), "modify_pending_order_payment",
                   {"order_id": rs()["pending"], "payment_method_id": 123})
        self.value("payment_method_is_gift_card", st, True, problems=["type_error"])


class TestUserAuthenticated(Base):
    def test_event(self):
        s = rs()
        args = {"order_id": s["pending"]}
        self.value("user_authenticated", state("retail", [], "get_order_details", args), False)
        failed = [("find_user_id_by_email", {"email": "nobody.at.all@example.com"})]
        st = state("retail", failed, "get_order_details", args)
        self.assertTrue(st.events[0]["output"].startswith("Error"))
        self.value("user_authenticated", st, False)
        self.value("user_authenticated", state("retail", login(), "get_order_details", args), True)
        by_zip = [("find_user_id_by_name_zip", {"first_name": s["first"], "last_name": s["last"], "zip": s["zip"]})]
        self.value("user_authenticated", state("retail", by_zip, "get_order_details", args), True)
        later = login() + failed + [("get_order_details", {"order_id": P6.NO_ORDER})]
        self.value("user_authenticated", state("retail", later, "respond", {"content": "hi"}), True)


class TestOrderStatus(Base):
    def test_pending(self):
        s = rs()
        p = s["pending"]
        args = {"order_id": p, "reason": "no longer needed"}
        f = "order_status_checked_pending"
        r = self.value(f, state("retail", login() + [("get_order_details", {"order_id": p})],
                                "cancel_pending_order", args), True)
        self.assertEqual((r["parts"]["a"]["value"], r["parts"]["b"]["value"]), (True, True))
        r = self.value(f, state("retail", login(), "cancel_pending_order", args), False)        # not looked up
        self.assertEqual((r["parts"]["a"]["value"], r["parts"]["b"]["value"]), (False, True))
        other = [("get_order_details", {"order_id": s["delivered"]})]
        self.value(f, state("retail", login() + other, "cancel_pending_order", args), False)  # another order looked up
        st = state("retail", login() + [("get_order_details", {"order_id": s["delivered"]})], "cancel_pending_order",
                   {"order_id": s["delivered"], "reason": "no longer needed"})
        r = self.value(f, st, False)                                                          # looked up, delivered
        self.assertEqual(r["parts"]["b"]["value"], label(st, f))
        # the order changes later in the conversation: the database at the check is read
        calls = login() + [("get_order_details", {"order_id": p}),
                           ("cancel_pending_order", {"order_id": p, "reason": "ordered by mistake"})]
        st = state("retail", calls, "modify_pending_order_address", dict(order_id=p, address1="1 Main St",
                   address2="", city="Austin", state="TX", country="USA", zip="78701"))
        r = self.value(f, st, False)
        self.assertEqual((r["parts"]["a"]["value"], r["parts"]["b"]["value"]), (True, False))
        self.assertIs(label(st, f), False)                                                    # τ-bench: non-pending
        calls = login() + [("get_order_details", {"order_id": p}),
                           ("modify_pending_order_items", {"order_id": p, "item_ids": [s["p_item"]],
                                                           "new_item_ids": [s["p_new"]],
                                                           "payment_method_id": s["other"]})]
        st = state("retail", calls, "cancel_pending_order", args)
        self.assertEqual(st.db_get("order", p)["status"], "pending (item modified)")
        self.value(f, st, False)                                                   # 'pending (item modified)'
        self.assertIs(label(st, f), False)
        # nonexistent id: the look-up failed and the database has no such order
        st = state("retail", login() + [("get_order_details", {"order_id": P6.NO_ORDER})], "cancel_pending_order",
                   {"order_id": P6.NO_ORDER, "reason": "no longer needed"})
        r = self.value(f, st, False)
        self.assertEqual((r["parts"]["a"]["value"], r["parts"]["b"]["how"]), (False, "nonexistent"))
        self.value(f, state("retail", login(), "cancel_pending_order", {"reason": "no longer needed"}), False,
                   problems=["missing_argument"])
        st = state("retail", login() + [("get_order_details", {"order_id": p})], "cancel_pending_order", args)
        del st.db["orders"][p]["status"]
        self.value(f, st, False, problems=["missing_field"])                  # an existing order without status

    def test_delivered(self):
        s = rs()
        d = s["delivered"]
        f = "order_status_checked_delivered"
        ret = {"order_id": d, "item_ids": [s["d_item"]], "payment_method_id": s["d_orig"]}
        look = [("get_order_details", {"order_id": d})]
        st = state("retail", login() + look, "return_delivered_order_items", ret)
        self.value(f, st, True)
        self.assertIs(label(st, f), True)
        self.value(f, state("retail", login(), "return_delivered_order_items", ret), False)
        st = state("retail", login() + look + [("return_delivered_order_items", ret)],
                   "exchange_delivered_order_items",
                   {"order_id": d, "item_ids": [s["d_item"]], "new_item_ids": [s["d_new"]], "payment_method_id": s["gc"]})
        self.assertEqual(st.db_get("order", d)["status"], "return requested")
        self.value(f, st, False)                                              # already returned: database at the check
        self.assertIs(label(st, f), False)
        self.value(f, state("retail", login(), "return_delivered_order_items", dict(ret, order_id=P6.NO_ORDER)), False)
        self.value(f, state("retail", login(), "return_delivered_order_items", {"item_ids": []}), False,
                   problems=["missing_argument"])


class TestPaymentDiffers(Base):
    def test_values(self):
        s = rs()
        p = s["pending"]
        orig = data("retail")["orders"][p]["payment_history"][0]["payment_method_id"]
        f = "payment_method_differs_from_original"
        for pid, want in ((s["gc"], True), (orig, False)):
            st = state("retail", login(), "modify_pending_order_payment", {"order_id": p, "payment_method_id": pid})
            self.value(f, st, want)
            self.assertIs(label(st, f), want)
        self.value(f, state("retail", login(), "modify_pending_order_payment",
                            {"order_id": P6.NO_ORDER, "payment_method_id": s["gc"]}), False)
        self.value(f, state("retail", login(), "modify_pending_order_payment", {"order_id": p}), False,
                   problems=["missing_argument"])
        st = state("retail", login(), "modify_pending_order_payment", {"order_id": p, "payment_method_id": s["gc"]})
        st.db["orders"][p]["payment_history"] = []
        self.value(f, st, False, problems=["missing_field"])


class TestGiftCardOrderTotal(Base):
    f = "gift_card_balance_covers_order_total"

    def st(self, pid=None, oid=None, balance=None):
        s = rs()
        args = {"order_id": oid or s["pending"], "payment_method_id": pid or s["gc"]}
        st = state("retail", login(), "modify_pending_order_payment", args)
        if balance is not None:
            st.db["users"][s["user"]]["payment_methods"][s["gc"]]["balance"] = balance
        return st

    def amount(self):
        return data("retail")["orders"][rs()["pending"]]["payment_history"][0]["amount"]

    def test_balance(self):
        a = self.amount()
        for bal, want in ((a + 1, True), (a, True), (round(a - 1, 2), False), (0, False)):
            st = self.st(balance=bal)
            self.value(self.f, st, want)
            self.assertIs(label(st, self.f), want, bal)

    def test_no_rounding(self):
        """modify_pending_order_payment compares the unrounded amount: a balance 0.004 below it is not enough."""
        st = self.st(balance=self.amount() - 0.004)
        self.value(self.f, st, False)
        self.assertIs(label(st, self.f), False)

    def test_not_a_gift_card(self):
        s = rs()
        st = self.st(pid=s["other"])
        self.value(self.f, st, False)
        self.assertIsNone(label(st, self.f))                     # τ-bench checks the balance of gift cards only
        gc = ev("retail", "payment_method_is_gift_card", st)["value"]
        self.assertIs(gc, False)
        self.assertEqual(P6.rule_outcome(rule("retail", "52"), {"payment_method_is_gift_card": gc, self.f: False}),
                         "allows")                                # the rule's other branch holds

    def test_nonexistent_and_missing(self):
        self.value(self.f, self.st(pid=P6.NO_GC), False)
        self.value(self.f, self.st(oid=P6.NO_ORDER), False)
        st = state("retail", login(), "modify_pending_order_payment", {"order_id": rs()["pending"]})
        self.value(self.f, st, False, problems=["missing_argument"])
        st = self.st()
        del st.db["users"][rs()["user"]]["payment_methods"][rs()["gc"]]["balance"]
        self.value(self.f, st, False, problems=["missing_field"])


class TestGiftCardPriceDifference(Base):
    f = "gift_card_balance_covers_price_difference"

    def setup(self, tool, old_price, new_price, balance, pid=None):
        s = rs()
        oid, item, new = ((s["pending"], s["p_item"], s["p_new"]) if tool == "modify_pending_order_items"
                          else (s["delivered"], s["d_item"], s["d_new"]))
        calls = login() + [("get_order_details", {"order_id": oid})]
        args = {"order_id": oid, "item_ids": [item], "new_item_ids": [new], "payment_method_id": pid or s["gc"]}
        st = state("retail", calls, tool, args)
        order = st.db["orders"][oid]
        it = next(x for x in order["items"] if x["item_id"] == item)
        it["price"] = old_price
        st.db["products"][it["product_id"]]["variants"][new]["price"] = new_price
        st.db["users"][s["user"]]["payment_methods"][s["gc"]]["balance"] = balance
        return st

    def test_positive_difference(self):
        for tool in ("modify_pending_order_items", "exchange_delivered_order_items"):
            for bal, want in ((10.0, True), (9.99, False), (50, True), (0, False)):
                st = self.setup(tool, 20.0, 30.0, bal)
                self.value(self.f, st, want)
                self.assertIs(label(st, self.f), want, (tool, bal))

    def test_signed_difference_refund(self):
        """A cheaper new item is a refund: no balance is needed (the signed difference, not its size)."""
        for tool in ("modify_pending_order_items", "exchange_delivered_order_items"):
            st = self.setup(tool, 30.0, 20.0, 0)
            self.value(self.f, st, True)
            self.assertIs(label(st, self.f), True)

    def test_each_tools_rounding(self):
        """10.3 - 10.1 = 0.20000000000000107: exchange rounds it to 0.2, modify does not."""
        self.assertNotEqual(10.3 - 10.1, 0.2)
        st = self.setup("exchange_delivered_order_items", 10.1, 10.3, 0.2)
        self.value(self.f, st, True)
        self.assertIs(label(st, self.f), True)
        st = self.setup("modify_pending_order_items", 10.1, 10.3, 0.2)
        self.value(self.f, st, False)
        self.assertIs(label(st, self.f), False)

    def test_not_a_gift_card(self):
        st = self.setup("modify_pending_order_items", 20.0, 30.0, 0, pid=rs()["other"])
        self.value(self.f, st, False)
        self.assertIsNone(label(st, self.f))
        self.assertEqual(P6.rule_outcome(rule("retail", "56"), {"payment_method_is_gift_card": False, self.f: False}),
                         "allows")

    def test_nonexistent_missing_and_unpriceable(self):
        s = rs()
        base = {"order_id": s["pending"], "item_ids": [s["p_item"]], "new_item_ids": [s["p_new"]],
                "payment_method_id": s["gc"]}
        tool = "modify_pending_order_items"
        self.value(self.f, state("retail", login(), tool, dict(base, payment_method_id=P6.NO_GC)), False)
        self.value(self.f, state("retail", login(), tool, dict(base, order_id=P6.NO_ORDER)), False)
        self.value(self.f, state("retail", login(), tool, dict(base, new_item_ids=[P6.NO_ITEM])), False)
        wrong = other_product_variant(data("retail")["orders"][s["pending"]]["items"][0]["product_id"])
        self.value(self.f, state("retail", login(), tool, dict(base, new_item_ids=[wrong])), False)
        args = {k: v for k, v in base.items() if k != "new_item_ids"}
        self.value(self.f, state("retail", login(), tool, args), False, problems=["missing_argument"])
        self.value(self.f, state("retail", login(), tool, dict(base, item_ids="x")), False, problems=["type_error"])

    def test_needs_the_pending_tool(self):
        s = rs()
        st = S.build_state(P6.conversation("retail", login()), None, domain="retail")
        args = {"order_id": s["pending"], "item_ids": [s["p_item"]], "new_item_ids": [s["p_new"]],
                "payment_method_id": s["gc"]}
        self.value(self.f, st, False, args=args, problems=["no_pending_call"])


class TestReplacements(Base):
    f = "item_replacements_are_available_same_product_different_option"

    def call(self, tool="modify_pending_order_items", **kw):
        s = rs()
        oid, item, new = ((s["pending"], s["p_item"], s["p_new"]) if tool == "modify_pending_order_items"
                          else (s["delivered"], s["d_item"], s["d_new"]))
        args = {"order_id": oid, "item_ids": [item], "new_item_ids": [new], "payment_method_id": s["gc"]}
        args.update(kw)
        return state("retail", login(), tool, args)

    def test_true_for_both_tools(self):
        for tool in ("modify_pending_order_items", "exchange_delivered_order_items"):
            st = self.call(tool)
            self.value(self.f, st, True)
            self.assertIs(label(st, self.f), True)

    def test_same_item_is_blocked(self):
        """The policy says "different product option": the same item id is false, though τ-bench accepts it."""
        s = rs()
        for tool, item in (("modify_pending_order_items", s["p_item"]), ("exchange_delivered_order_items", s["d_item"])):
            st = self.call(tool, new_item_ids=[item])
            self.value(self.f, st, False)
            self.assertIsNone(label(st, self.f))
            self.assertTrue(TC.check(st)["accepted"] or TC.check(st)["check"] == "gift_card_insufficient")

    def test_false_cases_agree_with_the_tool(self):
        s = rs()
        order = data("retail")["orders"][s["pending"]]
        pid = order["items"][0]["product_id"]
        wrong = other_product_variant(pid)
        st = self.call(new_item_ids=[wrong])                               # a variant of another product
        self.value(self.f, st, False)
        self.assertIs(label(st, self.f), False)
        st = self.call()                                                   # an unavailable variant
        st.db["products"][pid]["variants"][s["p_new"]]["available"] = False
        self.value(self.f, st, False)
        self.assertIs(label(st, self.f), False)
        st = self.call(item_ids=[s["p_item"], s["p_item"]], new_item_ids=[s["p_new"], s["p_new"]])
        n_in_order = sum(1 for it in order["items"] if it["item_id"] == s["p_item"])
        self.value(self.f, st, n_in_order >= 2)                            # duplicates are counted
        self.assertIs(label(st, self.f), n_in_order >= 2)
        st = self.call(item_ids=[s["p_item"]], new_item_ids=[s["p_new"], s["p_new"]])
        self.value(self.f, st, False)
        self.assertIs(label(st, self.f), False)
        st = self.call(new_item_ids=[P6.NO_ITEM])
        self.value(self.f, st, False)
        self.assertIs(label(st, self.f), False)
        st = self.call(item_ids=[P6.NO_ITEM])
        self.value(self.f, st, False)
        self.assertIs(label(st, self.f), False)

    def test_empty_list_nonexistent_missing(self):
        self.value(self.f, self.call(item_ids=[], new_item_ids=[]), False)        # no item changed: no modification
        self.value(self.f, self.call(order_id=P6.NO_ORDER), False)
        s = rs()
        st = state("retail", login(), "modify_pending_order_items",
                   {"order_id": s["pending"], "item_ids": [s["p_item"]], "payment_method_id": s["gc"]})
        self.value(self.f, st, False, problems=["missing_argument"])
        st = self.call()
        pid = data("retail")["orders"][s["pending"]]["items"][0]["product_id"]
        del st.db["products"][pid]["variants"][s["p_new"]]["available"]
        self.value(self.f, st, False, problems=["missing_field"])


class TestRefundMethod(Base):
    f = "return_refund_method_is_original_or_existing_gift_card"

    def call(self, pid, oid=None):
        s = rs()
        return state("retail", login(), "return_delivered_order_items",
                     {"order_id": oid or s["delivered"], "item_ids": [s["d_item"]], "payment_method_id": pid})

    def test_values(self):
        s = rs()
        for pid, want in ((s["d_orig"], True), (s["gc"], True)):
            st = self.call(pid)
            self.value(self.f, st, want)
            self.assertIs(label(st, self.f), want)
        st = self.call("credit_card_9999999")
        st.db["users"][s["user"]]["payment_methods"]["credit_card_9999999"] = {
            "source": "credit_card", "brand": "visa", "last_four": "9999", "id": "credit_card_9999999"}
        self.value(self.f, st, False)                                      # in the profile, not original, not a gift card
        self.assertIs(label(st, self.f), False)

    def test_not_in_profile(self):
        """τ-bench refuses at its check 3 ("payment method not found"); p3's label is None, the v3 fact false."""
        db = data("retail")
        other_gc = next(p for u in sorted(db["users"]) if u != rs()["user"]
                        for p, m in sorted(db["users"][u]["payment_methods"].items()) if m["source"] == "gift_card")
        st = self.call(other_gc)
        self.value(self.f, st, False)
        lab = TC.check(st)
        self.assertEqual(lab["check"], "payment_method_not_found")
        self.assertIsNone(lab["facts"][self.f])

    def test_nonexistent_and_missing(self):
        self.value(self.f, self.call(rs()["d_orig"], oid=P6.NO_ORDER), False)
        self.value(self.f, self.call(P6.NO_GC), False)
        st = state("retail", login(), "return_delivered_order_items",
                   {"order_id": rs()["delivered"], "item_ids": [rs()["d_item"]]})
        self.value(self.f, st, False, problems=["missing_argument"])


class TestChosePaymentPartD(Base):
    def test_values(self):
        s = rs()
        db = data("retail")
        other_pm = next(p for u in sorted(db["users"]) if u != s["user"] for p in sorted(db["users"][u]["payment_methods"]))
        cases = (("user_chose_pending_payment_method", "modify_pending_order_payment",
                  {"order_id": s["pending"]}),
                 ("user_chose_price_difference_payment_method", "modify_pending_order_items",
                  {"order_id": s["pending"], "item_ids": [s["p_item"]], "new_item_ids": [s["p_new"]]}),
                 ("user_chose_price_difference_payment_method", "exchange_delivered_order_items",
                  {"order_id": s["delivered"], "item_ids": [s["d_item"]], "new_item_ids": [s["d_new"]]}))
        for fact, tool, base in cases:
            for pid, want in ((s["gc"], True), (s["other"], True), (other_pm, False), (P6.NO_CC, False)):
                st = state("retail", login(), tool, dict(base, payment_method_id=pid))
                self.value(fact, st, want, part="d")
                lab = TC.check(st)
                self.assertEqual(lab["check"] == "payment_method_not_found", not want, (fact, pid, lab))
            st = state("retail", login(), tool, dict(base, payment_method_id=s["gc"], order_id=P6.NO_ORDER))
            self.value(fact, st, False, part="d")
            self.value(fact, state("retail", login(), tool, base), False, part="d", problems=["missing_argument"])


class TestAnotherUserPartA(Base):
    f = "request_is_for_another_user"

    def test_orders_and_users(self):
        s = rs()
        mine, theirs = s["pending"], another_order()
        self.value(self.f, state("retail", [], "get_order_details", {"order_id": theirs}), False, part="a")  # no me
        self.value(self.f, state("retail", login(), "get_order_details", {"order_id": mine}), False, part="a")
        self.value(self.f, state("retail", login(), "get_order_details", {"order_id": theirs}), True, part="a")
        self.value(self.f, state("retail", login(), "cancel_pending_order",
                                 {"order_id": another_order("pending"), "reason": "no longer needed"}), True, part="a")
        self.value(self.f, state("retail", login(), "cancel_pending_order",
                                 {"order_id": P6.NO_ORDER, "reason": "no longer needed"}), False, part="a")
        other_user = data("retail")["orders"][theirs]["user_id"]
        self.value(self.f, state("retail", login(), "get_user_details", {"user_id": other_user}), True, part="a")
        self.value(self.f, state("retail", login(), "get_user_details", {"user_id": s["user"]}), False, part="a")
        self.value(self.f, state("retail", login(), "get_user_details", {"user_id": P6.NO_USER}), True, part="a")
        self.value(self.f, state("retail", login(), "get_user_details", {}), True, part="a",
                   problems=["missing_argument"])                         # blocking value true
        self.value(self.f, state("retail", login(), "get_product_details", {"product_id": s["product"]}), False,
                   part="a")
        self.value(self.f, state("retail", login(), "list_all_product_types", {}), False, part="a")

    def test_lookups_after_login(self):
        s = rs()
        db = data("retail")
        other = db["users"][db["orders"][another_order()]["user_id"]]
        self.value(self.f, state("retail", login(), "find_user_id_by_email", {"email": other["email"].upper()}),
                   True, part="a")                                        # τ-bench compares in lower case
        self.value(self.f, state("retail", login(), "find_user_id_by_email", {"email": s["email"]}), False, part="a")
        self.value(self.f, state("retail", login(), "find_user_id_by_email",
                                 {"email": "nobody.at.all@example.com"}), False, part="a")
        self.value(self.f, state("retail", login(), "find_user_id_by_name_zip",
                                 {"first_name": other["name"]["first_name"].lower(),
                                  "last_name": other["name"]["last_name"], "zip": other["address"]["zip"]}),
                   True, part="a")
        self.value(self.f, state("retail", [], "find_user_id_by_email", {"email": other["email"]}), False, part="a")

    def test_me_is_the_first_login(self):
        db = data("retail")
        theirs = another_order()
        other = db["users"][db["orders"][theirs]["user_id"]]
        calls = login() + [("find_user_id_by_email", {"email": other["email"]})]
        self.value(self.f, state("retail", calls, "get_order_details", {"order_id": theirs}), True, part="a")


# ================================================================================================ airline
def ares(pred):
    db = data("airline")
    return next(db["reservations"][k] for k in sorted(db["reservations"]) if pred(db["reservations"][k]))


def statuses(r):
    fl = data("airline")["flights"]
    return [fl[f["flight_number"]]["dates"].get(f["date"], {}).get("status") for f in r["flights"]]


def looked(rid):
    return [("get_reservation_details", {"reservation_id": rid})]


class AirBase(Base):
    domain = "airline"


class TestCancelFacts(AirBase):
    """The rule-25 facts (event AND database) and rule 26."""

    def cancel(self, rid, look=True):
        return state("airline", looked(rid) if look else [], "cancel_reservation", {"reservation_id": rid})

    def test_airline_cancelled_flight(self):
        f = "airline_cancelled_flight_confirmed"
        r = ares(lambda r: "cancelled" in statuses(r))
        self.value(f, self.cancel(r["reservation_id"]), True)
        self.value(f, self.cancel(r["reservation_id"], look=False), False)
        r2 = ares(lambda r: "cancelled" not in statuses(r))
        self.value(f, self.cancel(r2["reservation_id"]), False)
        self.value(f, self.cancel(P6.NO_RES), False)
        self.value(f, state("airline", [], "cancel_reservation", {}), False, problems=["missing_argument"])
        st = self.cancel(r2["reservation_id"])
        seg = r2["flights"][0]
        del st.db["flights"][seg["flight_number"]]["dates"][seg["date"]]
        self.value(f, st, False, problems=["missing_field"])

    def test_within_24_hours(self):
        f = "cancellation_is_within_24_hours"
        new = ares(lambda r: r["created_at"] >= "2024-05-14T15:00:00")
        old = ares(lambda r: r["created_at"] < "2024-05-14T15:00:00")
        self.value(f, self.cancel(new["reservation_id"]), True)
        self.value(f, self.cancel(new["reservation_id"], look=False), False)
        self.value(f, self.cancel(old["reservation_id"]), False)
        for created, want in (("2024-05-14T15:00:00", True), ("2024-05-14T14:59:59", False),
                              ("2024-05-15T15:00:00", True)):
            st = self.cancel(old["reservation_id"])
            st.db["reservations"][old["reservation_id"]]["created_at"] = created
            self.value(f, st, want)
        st = self.cancel(old["reservation_id"])
        st.db["reservations"][old["reservation_id"]]["created_at"] = "yesterday"
        self.value(f, st, False, problems=["type_error"])
        self.value(f, self.cancel(P6.NO_RES), False)

    def test_booked_in_this_conversation(self):
        db = data("airline")
        uid = next(u for u in sorted(db["users"]) if any(m["source"] == "credit_card"
                                                          for m in db["users"][u]["payment_methods"].values()))
        u = db["users"][uid]
        cc = next(p for p, m in sorted(u["payment_methods"].items()) if m["source"] == "credit_card")
        fn, day = next((fn, d) for fn in sorted(db["flights"]) for d, x in sorted(db["flights"][fn]["dates"].items())
                       if x["status"] == "available" and x["available_seats"]["economy"] >= 1)
        fl = db["flights"][fn]
        price = fl["dates"][day]["prices"]["economy"]
        book = {"user_id": uid, "origin": fl["origin"], "destination": fl["destination"], "flight_type": "one_way",
                "cabin": "economy", "flights": [{"flight_number": fn, "date": day}],
                "passengers": [{"first_name": u["name"]["first_name"], "last_name": u["name"]["last_name"],
                                "dob": u["dob"]}],
                "payment_methods": [{"payment_id": cc, "amount": price}], "total_baggages": 0,
                "nonfree_baggages": 0, "insurance": "no"}
        st = state("airline", [("book_reservation", book)] + looked("HATHAT"), "cancel_reservation",
                   {"reservation_id": "HATHAT"})
        self.assertTrue(st.events[0]["ok"], st.events[0]["output"][:200])
        self.value("cancellation_is_within_24_hours", st, True)

    def test_cabin_after_the_last_flight_update(self):
        """τ-bench never updates the reservation's cabin field: the cabin of the last worked flight update counts."""
        db = data("airline")

        def movable(r):
            u = db["users"][r["user_id"]]
            return (r["cabin"] == "economy" and set(statuses(r)) == {"available"}
                    and any(m["source"] == "credit_card" for m in u["payment_methods"].values())
                    and all(db["flights"][f["flight_number"]]["dates"][f["date"]]["available_seats"]["business"]
                            >= len(r["passengers"]) for f in r["flights"]))
        r = ares(movable)
        rid = r["reservation_id"]
        cc = next(p for p, m in sorted(db["users"][r["user_id"]]["payment_methods"].items())
                  if m["source"] == "credit_card")
        segs = [{"flight_number": f["flight_number"], "date": f["date"]} for f in r["flights"]]
        up = ("update_reservation_flights", {"reservation_id": rid, "cabin": "business", "flights": segs,
                                             "payment_id": cc})
        st0 = self.cancel(rid)
        self.value("reservation_has_basic_or_economy_cabin", st0, True)
        self.value("reservation_has_business_cabin", st0, False)
        st = state("airline", looked(rid) + [up], "cancel_reservation", {"reservation_id": rid})
        self.assertTrue(st.events[-1]["ok"], st.events[-1]["output"][:200])
        self.assertEqual(st.db_get("reservation", rid)["cabin"], "economy")       # the field is not updated
        self.value("reservation_has_business_cabin", st, True)
        self.value("reservation_has_basic_or_economy_cabin", st, False)
        failed = ("update_reservation_flights", dict(up[1], payment_id="credit_card_0000000"))
        st = state("airline", looked(rid) + [failed], "cancel_reservation", {"reservation_id": rid})
        self.assertFalse(st.events[-1]["ok"])
        self.value("reservation_has_business_cabin", st, False)                   # a failed update is no update
        st = state("airline", looked(rid) + [up], "update_reservation_flights",
                   {"reservation_id": rid, "cabin": "business", "flights": segs, "payment_id": cc})
        self.value("pending_flight_update_is_basic_economy", st, False)
        basic = ares(lambda r: r["cabin"] == "basic_economy")
        st = state("airline", [], "update_reservation_flights",
                   {"reservation_id": basic["reservation_id"], "cabin": "basic_economy", "flights": [],
                    "payment_id": "x"})
        self.value("pending_flight_update_is_basic_economy", st, True)
        st = state("airline", [], "update_reservation_flights", {"reservation_id": P6.NO_RES, "cabin": "economy",
                                                                 "flights": [], "payment_id": "x"})
        self.value("pending_flight_update_is_basic_economy", st, False)
        self.value("reservation_has_business_cabin", self.cancel(P6.NO_RES), False)
        st = state("airline", [], "update_reservation_flights", {"cabin": "economy", "flights": [], "payment_id": "x"})
        self.value("pending_flight_update_is_basic_economy", st, True, problems=["missing_argument"])
        st = self.cancel(rid)
        del st.db["reservations"][rid]["cabin"]
        self.value("reservation_has_business_cabin", st, False, problems=["missing_field"])

    def test_travel_insurance(self):
        f = "reservation_has_travel_insurance"
        yes = ares(lambda r: r["insurance"] == "yes")
        no = ares(lambda r: r["insurance"] == "no")
        self.value(f, self.cancel(yes["reservation_id"]), True)
        self.value(f, self.cancel(yes["reservation_id"], look=False), False)
        self.value(f, self.cancel(no["reservation_id"]), False)
        self.value(f, self.cancel(P6.NO_RES), False)

    def test_no_used_segments(self):
        f = "reservation_has_no_used_flight_segments"
        free = ares(lambda r: set(statuses(r)) == {"available"})
        used = ares(lambda r: bool(set(statuses(r)) & {"landed", "flying"}))
        cancelled = ares(lambda r: "cancelled" in statuses(r) and not set(statuses(r)) & {"landed", "flying"})
        self.value(f, self.cancel(free["reservation_id"], look=False), True)      # no event part (S40-S41)
        self.value(f, self.cancel(used["reservation_id"]), False)
        self.value(f, self.cancel(cancelled["reservation_id"]), True)             # a cancelled segment was not flown
        self.value(f, self.cancel(P6.NO_RES), False)
        self.value(f, state("airline", [], "cancel_reservation", {}), False, problems=["missing_argument"])

    def test_reservation_exists_parts(self):
        rid = ares(lambda r: True)["reservation_id"]
        for fact, tool, extra in (("cancellation_context_established", "cancel_reservation", {}),
                                  ("modification_user_and_reservation_ids_established", "update_reservation_passengers",
                                   {"passengers": []})):
            self.value(fact, state("airline", [], tool, dict(extra, reservation_id=rid)), True, part="a")
            st = state("airline", [], tool, dict(extra, reservation_id=P6.NO_RES))
            self.value(fact, st, False, part="a")
            self.assertEqual(TC.check(st)["check"], "reservation_not_found")
            self.value(fact, state("airline", [], tool, extra), False, part="a", problems=["missing_argument"])


class TestFlightUpdateFacts(AirBase):
    def upd(self, rid, flights, look=True, cabin=None, payment="x"):
        r = data("airline")["reservations"].get(rid) or {"cabin": "economy"}
        return state("airline", looked(rid) if look else [], "update_reservation_flights",
                     {"reservation_id": rid, "cabin": cabin or r["cabin"], "flights": flights, "payment_id": payment})

    @staticmethod
    def segs(r):
        return [{"flight_number": f["flight_number"], "date": f["date"]} for f in r["flights"]]

    def test_segments_unchanged_and_changes(self):
        r = ares(lambda r: len(r["flights"]) >= 2 and r["flights"][0]["flight_number"] != r["flights"][1]["flight_number"])
        rid, segs = r["reservation_id"], self.segs(r)
        same, changes = "pending_flight_segments_are_unchanged", "pending_flight_update_changes_flights"
        st = self.upd(rid, list(reversed(segs)))                                  # order ignored
        self.value(same, st, True)
        self.value(changes, st, False)
        st = self.upd(rid, segs, look=False)
        self.value(same, st, False)                                               # not looked up (event part)
        self.value(changes, st, False)
        moved = copy.deepcopy(segs)
        moved[0]["date"] = "2024-05-30"
        st = self.upd(rid, moved)
        self.value(same, st, False)
        self.value(changes, st, True)
        st = self.upd(rid, [segs[0], segs[0]] + segs[2:])                         # same length, other multiset
        self.value(same, st, False)
        self.value(changes, st, True)
        st = self.upd(P6.NO_RES, segs)
        self.value(same, st, False)
        self.value(changes, st, False)                                            # nonexistent id: false
        st = state("airline", looked(rid), "update_reservation_flights",
                   {"reservation_id": rid, "cabin": "economy", "payment_id": "x"})
        self.value(same, st, False, problems=["missing_argument"])
        self.value(changes, st, True, problems=["missing_argument"])              # blocking value true
        st = self.upd(rid, [{"date": segs[0]["date"]}] + segs[1:])
        self.value(changes, st, True, problems=["missing_argument"])

    def test_origin_destination_and_trip_type(self):
        f = "origin_destination_and_trip_type_preserved"
        fl = data("airline")["flights"]
        one = ares(lambda r: r["flight_type"] == "one_way" and r["origin"] != r["destination"])
        self.value(f, self.upd(one["reservation_id"], self.segs(one)), True)
        self.value(f, self.upd(one["reservation_id"], self.segs(one), look=False), False)
        back = next(n for n in sorted(fl) if fl[n]["origin"] == one["destination"]
                    and fl[n]["destination"] == one["origin"])
        self.value(f, self.upd(one["reservation_id"], self.segs(one) + [{"flight_number": back,
                                                                         "date": "2024-05-30"}]), False)
        rt = ares(lambda r: r["flight_type"] == "round_trip" and len(r["flights"]) >= 2)
        self.value(f, self.upd(rt["reservation_id"], self.segs(rt)), True)
        outbound = [s for s in self.segs(rt) if fl[s["flight_number"]]["origin"] == rt["origin"]]
        self.value(f, self.upd(rt["reservation_id"], outbound), False)            # the way back is missing
        self.value(f, self.upd(one["reservation_id"], [{"flight_number": P6.NO_FLIGHT, "date": "2024-05-30"}]), False)
        self.value(f, self.upd(one["reservation_id"], []), False)
        self.value(f, self.upd(P6.NO_RES, self.segs(one)), False)

    def test_one_cabin(self):
        f = "all_pending_flight_segments_have_one_cabin"
        r = ares(lambda r: True)
        segs = self.segs(r)
        self.value(f, self.upd(r["reservation_id"], segs, cabin="economy"), True)
        with_cabin = [dict(s, cabin="economy") for s in segs]
        self.value(f, self.upd(r["reservation_id"], with_cabin, cabin="economy"), True)
        mixed = [dict(segs[0], cabin="business")] + segs[1:]
        self.value(f, self.upd(r["reservation_id"], mixed, cabin="economy"), False)
        st = state("airline", [], "update_reservation_flights", {"reservation_id": r["reservation_id"],
                                                                 "flights": segs, "payment_id": "x"})
        self.value(f, st, False, problems=["missing_argument"])
        self.value(f, self.upd(r["reservation_id"], "HAT001", cabin="economy"), False, problems=["type_error"])

    def test_payment_selected_part_a(self):
        f = "user_selected_eligible_flight_change_payment_method"
        db = data("airline")
        r = ares(lambda r: {m["source"] for m in db["users"][r["user_id"]]["payment_methods"].values()}
                 >= {"credit_card", "gift_card", "certificate"})
        pms = db["users"][r["user_id"]]["payment_methods"]
        by = {m["source"]: p for p, m in sorted(pms.items())}
        other_cc = next(p for u in sorted(db["users"]) if u != r["user_id"]
                        for p, m in sorted(db["users"][u]["payment_methods"].items()) if m["source"] == "credit_card")
        moved = self.segs(r)
        moved[0]["date"] = "2024-05-30"
        for pid, want in ((by["credit_card"], True), (by["gift_card"], True), (by["certificate"], False),
                          (other_cc, False)):
            st = self.upd(r["reservation_id"], moved, payment=pid)
            self.value(f, st, want, part="a")
        st = self.upd(r["reservation_id"], self.segs(r), payment=by["certificate"])
        self.assertEqual(TC.check(st)["check"], "certificate_not_allowed")
        self.value(f, self.upd(P6.NO_RES, moved, payment=by["credit_card"]), False, part="a")
        st = state("airline", [], "update_reservation_flights", {"reservation_id": r["reservation_id"],
                                                                 "cabin": "economy", "flights": moved})
        self.value(f, st, False, part="a", problems=["missing_argument"])


class TestBagsAndPassengers(AirBase):
    def test_baggage_total_not_reduced(self):
        f = "pending_baggage_total_not_reduced"
        r = ares(lambda r: r["total_baggages"] >= 1)
        rid = r["reservation_id"]
        for total, want in ((r["total_baggages"] + 1, True), (r["total_baggages"], True),
                            (r["total_baggages"] - 1, False)):
            st = state("airline", [], "update_reservation_baggages",
                       {"reservation_id": rid, "total_baggages": total, "nonfree_baggages": 0, "payment_id": "x"})
            self.value(f, st, want)
        st = state("airline", [], "update_reservation_baggages", {"reservation_id": P6.NO_RES, "total_baggages": 9,
                                                                  "nonfree_baggages": 0, "payment_id": "x"})
        self.value(f, st, False)
        st = state("airline", [], "update_reservation_baggages", {"reservation_id": rid, "nonfree_baggages": 0,
                                                                  "payment_id": "x"})
        self.value(f, st, False, problems=["missing_argument"])

    def test_passenger_count(self):
        f = "pending_passenger_count_unchanged"
        r = ares(lambda r: True)
        pax = [{k: p[k] for k in ("first_name", "last_name", "dob")} for p in r["passengers"]]
        for passengers, want in ((pax, True), (pax + pax[:1], False)):
            st = state("airline", [], "update_reservation_passengers",
                       {"reservation_id": r["reservation_id"], "passengers": passengers})
            self.value(f, st, want)
            self.assertIs(label(st, f), want)
        st = state("airline", [], "update_reservation_passengers", {"reservation_id": P6.NO_RES, "passengers": pax})
        self.value(f, st, False)
        self.assertIsNone(label(st, f))                                   # τ-bench: reservation not found first
        st = state("airline", [], "update_reservation_passengers", {"reservation_id": r["reservation_id"]})
        self.value(f, st, False, problems=["missing_argument"])


def a_user(pred=lambda u: True):
    db = data("airline")
    return next(u for u in sorted(db["users"]) if pred(db["users"][u]))


def valid_flight():
    """The first (flight number, date) that is available with an economy seat (so τ-bench reaches its payment check)."""
    if "flight" not in _CACHE:
        fl = data("airline")["flights"]
        _CACHE["flight"] = next((fn, d) for fn in sorted(fl) for d, x in sorted(fl[fn]["dates"].items())
                                if x["status"] == "available" and x["available_seats"]["economy"] >= 1)
    return _CACHE["flight"]


def book_args(uid, **kw):
    u = data("airline")["users"][uid]
    fn, day = valid_flight()
    fl = data("airline")["flights"][fn]
    args = {"user_id": uid, "origin": fl["origin"], "destination": fl["destination"], "flight_type": "one_way",
            "cabin": "economy", "flights": [{"flight_number": fn, "date": day}],
            "passengers": [{"first_name": u["name"]["first_name"], "last_name": u["name"]["last_name"],
                            "dob": u["dob"]}],
            "payment_methods": [{"payment_id": sorted(u["payment_methods"])[0], "amount": 100}],
            "total_baggages": 0, "nonfree_baggages": 0, "insurance": "no"}
    args.update(kw)
    return args


class TestBookingFacts(AirBase):
    def book(self, **kw):
        uid = kw.pop("uid", None) or a_user()
        return state("airline", [], "book_reservation", book_args(uid, **kw))

    def test_membership(self):
        for fact in ("booking_user_is_gold_member", "booking_user_is_regular_member", "booking_user_is_silver_member"):
            tier = fact[len("booking_user_is_"):-len("_member")]
            uid = a_user(lambda u, t=tier: u["membership"] == t)
            other = a_user(lambda u, t=tier: u["membership"] != t)
            self.value(fact, self.book(uid=uid), True)
            self.value(fact, self.book(uid=other), False)
            self.value(fact, self.book(user_id=P6.NO_USER), False)
            args = book_args(a_user())
            del args["user_id"]
            self.value(fact, state("airline", [], "book_reservation", args), True, problems=["missing_argument"])

    def test_bag_counts(self):
        cases = {  # fact: (cabin, per passenger)
            "gold_member_booking_baggage_counts_correct": {"basic_economy": 2, "economy": 3, "business": 3},
            "silver_member_booking_baggage_counts_correct": {"basic_economy": 1, "economy": 2, "business": 3},
            "regular_member_booking_baggage_counts_correct": {"basic_economy": 0, "economy": 1, "business": 2},
        }
        uid = a_user()
        pax = book_args(uid)["passengers"] * 2
        for fact, table in cases.items():
            for cabin, per in table.items():
                free = 2 * per
                for total, nonfree, want in ((free + 1, 1, True), (free + 1, 0, False), (free, 0, True),
                                             (free, 1, False), (0, 0, True), (free + 3, 3, True)):
                    st = self.book(uid=uid, cabin=cabin, passengers=pax, total_baggages=total,
                                   nonfree_baggages=nonfree)
                    self.value(fact, st, want)
            for bad in (-1, 1.5, "2", True):
                self.value(fact, self.book(uid=uid, total_baggages=bad), False, problems=["bad_count"])
            self.value(fact, self.book(uid=uid, cabin="first"), False, problems=["unknown_cabin"])
            self.value(fact, self.book(uid=uid, passengers="me"), False, problems=["type_error"])
            args = book_args(uid)
            del args["nonfree_baggages"]
            self.value(fact, state("airline", [], "book_reservation", args), False, problems=["missing_argument"])

    def test_payment_counts(self):
        f = "booking_payment_method_counts_within_limits"

        def pm(*ids):
            return [{"payment_id": i, "amount": 1} for i in ids]
        for ids, want in ((("credit_card_1",), True), (("certificate_1", "certificate_2"), False),
                          (("certificate_1", "certificate_1"), True),
                          (("gift_card_1", "gift_card_2", "gift_card_3", "credit_card_1", "certificate_1"), True),
                          (("gift_card_1", "gift_card_2", "gift_card_3", "gift_card_4"), False),
                          (("credit_card_1", "credit_card_2"), False), (("paypal_1", "paypal_2"), True), ((), True)):
            self.value(f, self.book(payment_methods=pm(*ids)), want)
        self.value(f, self.book(payment_methods=[{"amount": 1}]), False, problems=["missing_argument"])
        args = book_args(a_user())
        del args["payment_methods"]
        self.value(f, state("airline", [], "book_reservation", args), False, problems=["missing_argument"])

    def test_payment_found_in_profile(self):
        f = "booking_payment_methods_found_in_user_profile"
        uid = a_user(lambda u: len(u["payment_methods"]) >= 2)
        ids = sorted(data("airline")["users"][uid]["payment_methods"])
        pm = [{"payment_id": i, "amount": 1} for i in ids]
        st = self.book(uid=uid, payment_methods=pm)
        self.value(f, st, True)
        self.value(f, self.book(uid=uid, payment_methods=pm + [{"payment_id": P6.NO_CC, "amount": 1}]), False)
        st = self.book(uid=uid, payment_methods=[{"payment_id": P6.NO_CC, "amount": 1}])
        self.value(f, st, False)
        self.assertIs(label(st, f), False)
        self.value(f, self.book(uid=uid, payment_methods=[]), True)
        self.value(f, self.book(user_id=P6.NO_USER, payment_methods=[]), False)   # no such user, whatever the list
        args = book_args(uid)
        del args["user_id"]
        self.value(f, state("airline", [], "book_reservation", args), False, problems=["missing_argument"])
        # a certificate sent during the conversation counts from then on (the database at the check)
        send = [("send_certificate", {"user_id": uid, "amount": 100})]
        st0 = state("airline", [], "book_reservation", book_args(uid))
        st = state("airline", send, "book_reservation", book_args(uid))
        new = sorted(set(st.db["users"][uid]["payment_methods"]) - set(st0.db["users"][uid]["payment_methods"]))
        self.assertEqual(len(new), 1, st.events[0]["output"])
        cert = [{"payment_id": new[0], "amount": 1}]
        self.value(f, state("airline", [], "book_reservation", book_args(uid, payment_methods=cert)), False)
        self.value(f, state("airline", send, "book_reservation", book_args(uid, payment_methods=cert)), True)

    def test_five_passengers_and_shared_flights(self):
        uid = a_user()
        p = book_args(uid)["passengers"][0]
        self.value("booking_has_at_most_five_passengers", self.book(passengers=[p] * 5), True)
        self.value("booking_has_at_most_five_passengers", self.book(passengers=[p] * 6), False)
        self.value("booking_has_at_most_five_passengers", self.book(passengers={"a": p}), False,
                   problems=["type_error"])
        args = book_args(uid)
        del args["passengers"]
        self.value("booking_has_at_most_five_passengers", state("airline", [], "book_reservation", args), False,
                   problems=["missing_argument"])
        f = "all_booking_passengers_share_flights_and_cabin"
        fl = book_args(uid)["flights"]
        self.value(f, self.book(uid=uid, passengers=[p, p]), True)
        self.value(f, self.book(uid=uid, passengers=[dict(p, cabin="economy"), p]), True)
        self.value(f, self.book(uid=uid, passengers=[dict(p, cabin="business"), p]), False)
        self.value(f, self.book(uid=uid, passengers=[dict(p, flights=fl + fl), p]), False)
        args = book_args(uid)
        del args["cabin"]
        self.value(f, state("airline", [], "book_reservation", args), False, problems=["missing_argument"])

    def test_passenger_identity_part_b(self):
        f = "passenger_identity_details_established"
        uid = a_user(lambda u: len(u["saved_passengers"]) >= 1)
        u = data("airline")["users"][uid]
        own = {"first_name": u["name"]["first_name"], "last_name": u["name"]["last_name"], "dob": u["dob"]}
        saved = {k: u["saved_passengers"][0][k] for k in ("first_name", "last_name", "dob")}
        stranger = {"first_name": "Zed", "last_name": "Nobody", "dob": "1901-01-01"}
        for pax, want in (([own], True), ([saved], True), ([own, saved], True), ([stranger], False),
                          ([own, stranger], False), ([dict(own, dob="1901-01-01")], False)):
            r = self.value(f, self.book(uid=uid, passengers=pax), want, part="b")
            self.assertEqual(len(r["items"]), len(pax))
        self.value(f, self.book(user_id=P6.NO_USER, passengers=[own]), False, part="b")
        self.value(f, self.book(uid=uid, passengers=[]), False, part="b")            # if_empty false
        self.value(f, self.book(uid=uid, passengers=[{"first_name": own["first_name"], "last_name": own["last_name"]}]),
                   False, part="b", problems=["missing_argument"])


# ================================================================================================ helpers, files
class TestHelpers(unittest.TestCase):
    def ctx(self, st=None):
        return F.Context("f", "a", {}, st, {}, None, None)

    def test_registered_with_their_sources(self):
        reg = F.registered_names()
        for name, func, lo, hi, source, _ in CH.HELPERS:
            self.assertIn(name, reg)
            self.assertEqual((reg[name].func, reg[name].min_args, reg[name].max_args, reg[name].source),
                             (func, lo, hi, source))
        CH.register_all()                                                 # registering again changes nothing

    def test_small_helpers(self):
        c = self.ctx()
        self.assertEqual(CH.pairs(c, [1, 2, 3], ["a", "b"]), [[1, "a"], [2, "b"]])
        self.assertEqual(CH.distinct(c, ["a", "b", "a", {"x": 1}, {"x": 1}]), ["a", "b", {"x": 1}])
        self.assertTrue(CH.starts_with(c, "gift_card_1", "gift_card_"))
        self.assertFalse(CH.starts_with(c, 5, "gift_card_"))
        self.assertEqual(CH.list_arg(c, [1]), [1])
        with self.assertRaises(F.UseBlockingValue) as e:
            CH.list_arg(c, "x")
        self.assertEqual(e.exception.kind, "type_error")
        allowance = [["economy", 3]]
        self.assertTrue(CH.bags_right(c, 7, 1, "economy", [{}, {}], allowance))
        self.assertTrue(CH.bags_right(c, 4.0, 0, "economy", [{}, {}], allowance))
        self.assertFalse(CH.bags_right(c, 4, 1, "economy", [{}, {}], allowance))

    def test_raw_scan_equals_the_event_log(self):
        s = rs()
        calls = login() + [("get_order_details", {"order_id": P6.NO_ORDER}), ("get_order_details",
                                                                               {"order_id": s["pending"]})]
        msgs = P6.conversation("retail", calls)
        self.assertTrue(P6.raw_event(msgs, ("get_order_details",), "order_id", s["pending"]))
        self.assertFalse(P6.raw_event(msgs, ("get_order_details",), "order_id", P6.NO_ORDER))
        self.assertTrue(P6.raw_event(msgs, ("find_user_id_by_email", "find_user_id_by_name_zip"), None, None))
        self.assertFalse(P6.raw_event(msgs[:2], ("find_user_id_by_email",), None, None))


class TestOverlays(unittest.TestCase):
    def test_every_p6_part_has_an_expression_and_validates(self):
        for d in ("retail", "airline"):
            doc = docs(d)
            self.assertEqual(F.validate(doc, d), [])
            raw = F.load_facts(d)
            ov = P6.load_overlay(d)
            for fact, e in doc["facts"].items():
                for pid, p in e["parts"].items():
                    if p["source"] in P6.MINE:
                        self.assertIsNotNone(p["expr"], (d, fact, pid))
                        self.assertIn(pid, ov["exprs"].get(fact, {}), (d, fact, pid))
                    else:
                        self.assertEqual(p, raw["facts"][fact]["parts"][pid])     # other parts untouched
            for fact, parts in ov["exprs"].items():
                for x in parts.values():
                    self.assertEqual(set(x) - {"expr", "if_nonexistent"}, set(), (fact, x))
            n = sum(len(v) for v in ov["exprs"].values())
            self.assertEqual(n, {"retail": 15, "airline": 34}[d])

    def test_valid_with_the_other_parts_names(self):
        """The merged files must stay valid when p7's and p8's helper names are registered too (a p6 loop variable
        may not use one of their names, e.g. p7's `me`)."""
        loaded = []
        for mod in ("state_tracker.v3.message_view", "state_tracker.v3.questions"):
            try:
                __import__(mod)
                loaded.append(mod)
            except ImportError:
                pass
        if not loaded:
            self.skipTest("p7 / p8 helper modules not present")
        for d in ("retail", "airline"):
            self.assertEqual(F.validate(docs(d), d), [], (d, loaded))

    def test_first_login_user_equals_p7_me(self):
        try:
            import state_tracker.v3.message_view  # noqa: F401
        except ImportError:
            self.skipTest("p7's message_view is not present")
        if "me" not in F.registered_names():
            self.skipTest("p7 registers no `me`")
        entry = {"parts": {"a": {"source": "event", "plain": "same user", "expr": "me() == first_login_user()",
                                 "question": None, "about": None}},
                 "combine": "a", "blocking_value": False, "sources": ["event"]}
        db = data("retail")
        other = db["users"][db["orders"][another_order()]["user_id"]]
        s = rs()
        for calls in ([], login(), login() + [("find_user_id_by_email", {"email": other["email"]})],
                      [("find_user_id_by_email", {"email": "nobody.at.all@example.com"})] + login(),
                      [("find_user_id_by_name_zip", {"first_name": s["first"], "last_name": s["last"],
                                                     "zip": s["zip"]})]):
            st = state("retail", calls, "respond", {"content": "hi"})
            r = F.evaluate(entry, st)
            self.assertEqual(r["problems"], [])
            self.assertIs(r["value"], True, calls)

    def test_fact_files_still_have_null_expressions_for_p6(self):
        """p6 writes overlays only; the fact files are merged by the main chat."""
        for d in ("retail", "airline"):
            raw = F.load_facts(d)
            ov = P6.load_overlay(d)
            for fact, parts in ov["exprs"].items():
                for pid in parts:
                    self.assertIn(raw["facts"][fact]["parts"][pid]["source"], P6.MINE)


# ================================================================================================ P5.4
RETAIL_EXPECTED = {
    ("find_user_id_by_email", "email"): set(),
    ("find_user_id_by_name_zip", "first_name, last_name, zip"): set(),
    ("get_user_details", "user_id"): {"17"},
    ("get_order_details", "order_id"): set(),
    ("get_product_details", "product_id"): set(),
    ("cancel_pending_order", "order_id"): {"44"},
    ("modify_pending_order_address", "order_id"): {"47"},
    ("modify_pending_order_items", "order_id"): {"48", "54", "55", "56"},
    ("modify_pending_order_items", "item_ids"): {"54", "56"},
    ("modify_pending_order_items", "new_item_ids"): {"54", "56"},
    ("modify_pending_order_items", "payment_method_id (gift card form)"): {"55", "56"},
    ("modify_pending_order_items", "payment_method_id (credit card form)"): {"55"},
    ("modify_pending_order_payment", "order_id"): {"49", "50", "51", "52"},
    ("modify_pending_order_payment", "payment_method_id (gift card form)"): {"50", "52"},
    ("modify_pending_order_payment", "payment_method_id (credit card form)"): {"50"},
    ("modify_user_address", "user_id"): {"26"},
    ("return_delivered_order_items", "order_id"): {"57", "59"},
    ("return_delivered_order_items", "item_ids"): set(),
    ("return_delivered_order_items", "payment_method_id (gift card form)"): {"59"},
    ("return_delivered_order_items", "payment_method_id (credit card form)"): {"59"},
    ("exchange_delivered_order_items", "order_id"): {"60", "62", "63", "64"},
    ("exchange_delivered_order_items", "item_ids"): {"62", "64"},
    ("exchange_delivered_order_items", "new_item_ids"): {"62", "64"},
    ("exchange_delivered_order_items", "payment_method_id (gift card form)"): {"63", "64"},
    ("exchange_delivered_order_items", "payment_method_id (credit card form)"): {"63"},
}
AIRLINE_EXPECTED = {
    ("book_reservation", "user_id"): {"10"},
    ("book_reservation", "flights[0].flight_number"): set(),
    ("book_reservation", "payment_methods[0].payment_id"): {"10"},
    ("update_reservation_flights", "reservation_id"): {"15", "19"},
    ("update_reservation_flights", "flights[0].flight_number"): {"19"},
    ("update_reservation_flights", "payment_id"): {"23"},
    ("update_reservation_baggages", "reservation_id"): {"16", "21"},
    ("update_reservation_baggages", "payment_id"): set(),
    ("update_reservation_passengers", "reservation_id"): {"17", "22"},
    ("cancel_reservation", "reservation_id"): {"24", "25", "26"},
    ("send_certificate", "user_id"): set(),
}


class TestNonexistentIds(unittest.TestCase):
    """p5's test (P5.4): a call with a nonexistent id still blocks in every rule where it should. Expected sets are
    written from the facts' `missing` texts; where no rule blocks, τ-bench's own tool refuses the call."""

    def check(self, domain, expected):
        rows = P6.nonexistent_id_table(domain, docs(domain))
        got = {}
        tau = {}
        for r in rows:
            key = (r["action"], r["variant"])
            got.setdefault(key, set())
            if r["outcome"] == "blocks":
                got[key].add(r["rule"])
            tau[key] = r["tau_output"]
            self.assertNotIn("missing_field", r["problems"], r)
        self.assertEqual(got, expected)
        for key, rules in got.items():
            self.assertTrue(tau[key].startswith("Error"), (key, tau[key]))         # τ-bench refuses every one
        return rows, tau

    def test_retail(self):
        _, tau = self.check("retail", RETAIL_EXPECTED)
        self.assertEqual(tau[("return_delivered_order_items", "item_ids")], "Error: some item not found")
        self.assertEqual(tau[("get_product_details", "product_id")], "Error: product not found")

    def test_airline(self):
        _, tau = self.check("airline", AIRLINE_EXPECTED)
        self.assertEqual(tau[("update_reservation_flights", "payment_id")], "Error: payment method not found")
        self.assertEqual(tau[("update_reservation_baggages", "payment_id")], "Error: payment method not found")
        self.assertEqual(tau[("send_certificate", "user_id")], "Error: user not found")

    def test_base_calls_are_accepted(self):
        """... and without the nonexistent id τ-bench accepts the base call (so the Error comes from the id)."""
        for domain in ("retail", "airline"):
            before, cases = P6.nonexistent_cases(domain)
            if domain == "retail":
                s = rs()
                base = {"cancel_pending_order": {"order_id": s["pending"], "reason": "no longer needed"},
                        "return_delivered_order_items": {"order_id": s["delivered"], "item_ids": [s["d_item"]],
                                                         "payment_method_id": s["d_orig"]}}
            else:
                a = P6.airline_sample()
                base = {"update_reservation_flights": {"reservation_id": a["res"], "cabin": a["cabin"],
                                                       "flights": a["moved"], "payment_id": a["cc"]},
                        "cancel_reservation": {"reservation_id": a["res"]}}
            for tool, args in base.items():
                st = state(domain, before, tool, args)
                self.assertTrue(TC.check(st)["accepted"], (tool, TC.check(st)))


if __name__ == "__main__":
    unittest.main()
