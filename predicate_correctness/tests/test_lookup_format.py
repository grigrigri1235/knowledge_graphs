"""Tests for state_tracker/lookup_format.py and the lookup files (Part 5). Standard library only, no LLM calls.

Run from predicate_correctness/:  python3 -B -m unittest tests.test_lookup_format -v

The states are built from hand-made conversations: each tool output is made by running τ-bench's tool code on a
separate copy of the data, as in the real run. Expected values are plain facts of the data files (an order's status,
a reservation's dates) or of the hand-made arguments, not judgements.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_tracker import lookup_format as L  # noqa: E402
from state_tracker import state as S  # noqa: E402
from state_tracker import tau_copy  # noqa: E402


def _conv(domain, calls):
    """System, user, then per call an assistant tool call and its output (τ-bench's code on a separate copy)."""
    db = S.load_db(domain)
    msgs = [{"role": "system", "content": tau_copy.policy_text(domain)}, {"role": "user", "content": "hi"}]
    for i, (name, args) in enumerate(calls):
        out = S.run_tool(domain, db, name, copy.deepcopy(args))
        msgs.append({"role": "assistant", "content": None, "tool_calls": [
            {"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "name": name, "content": out})
    return msgs


def _state(domain, calls, tool=None, args=None):
    return S.build_state(_conv(domain, calls), None if tool is None else {"tool": tool, "args": args or {}},
                         domain=domain)


class Data:
    _db = {}

    @classmethod
    def db(cls, domain):
        if domain not in cls._db:
            cls._db[domain] = S.load_db(domain)
        return cls._db[domain]

    @classmethod
    def order(cls, status):
        return next(o for o in cls.db("retail")["orders"].values() if o["status"] == status)

    @classmethod
    def reservation(cls, test):
        return next(r for r in cls.db("airline")["reservations"].values() if test(r))


# ----------------------------------------------------------------------------------------------- validator

class TestValidator(unittest.TestCase):
    OK = [
        "args['x'] == 1",
        "not (args['x'] != 1) and args['y'] in ['a', 'b'] or args['z'] is None",
        "len(args['l']) <= 5",
        "sum([1, 2.5, args['n']]) >= 3",
        "any(p['a'] for p in args['l']) and all(p.get('a') for p in args['l'] if p)",
        "len([x for x in args['l'] for y in x if y == 1]) > 0",
        "all(a == b for a, b in args['pairs'])",
        "args['l'][0] == args['l'][-1]",
        "args.get('x', 3) == 3",
        "shown('order', args['order_id'])['status'] == 'pending'",
        "db('order', args['order_id']) is not None",
        "len(db_all('order')) > len(shown_all('order'))",
        "len(events(tool='find_user_id_by_email', ok=True)) > 0",
        "len(events('calculate')) == 0",
        "len(events()) == 0",
        "date('2024-05-16') > today",
    ]
    BAD = [
        ("__import__('os')", "not allowed"),
        ("open('x')", "not allowed"),
        ("args.keys()", "only .get"),
        ("args.__class__", "attribute"),
        ("args['x'] + 1 > 2", "arithmetic"),
        ("args['l'][1:] == []", "slices"),
        ("(lambda: True)()", "not allowed"),
        ("(x := 1) == 1", "not allowed"),
        ("{'a': 1}['a'] == 1", "not allowed"),
        ("len({x for x in args['l']}) == 1", "not allowed"),
        ("f'{args}' == ''", "not allowed"),
        ("True if args else False", "not allowed"),
        ("len == 1", "may only be called"),
        ("all(True for len in args['l'])", "loop variable"),
        ("all(True for _x in args['l'])", "loop variable"),
        ("len(*args['l']) == 1", "'*args'"),
        ("len(args['l'], 2) == 1", "positional"),
        ("len(x=args['l']) == 1", "no keyword"),
        ("events(name='x') == []", "no keyword"),
        ("events('a', tool='b') == []", "twice"),
        ("shown(args['k'], 'x') is None", "text constant"),
        ("x == 1", "not allowed"),
        ("args.get() == 1", "one or two"),
        ("b'x' == 1", "bytes"),
        ("-args['x'] == 1", "unary"),
        ("args['x'] == 1; import os", "not a Python expression"),
        ("", "non-empty"),
    ]

    def test_accepts_the_format(self):
        for expr in self.OK:
            with self.subTest(expr=expr):
                L.validate(expr)

    def test_rejects_everything_else(self):
        for expr, msg in self.BAD:
            with self.subTest(expr=expr):
                with self.assertRaises(L.LookupFormatError) as cm:
                    L.validate(expr)
                self.assertIn(msg, str(cm.exception))

    def test_kinds_are_checked_when_given(self):
        L.validate("shown('order', 'x') is None", kinds=L.domain_kinds("retail"))
        with self.assertRaises(L.LookupFormatError):
            L.validate("shown('reservation', 'x') is None", kinds=L.domain_kinds("retail"))

    def test_reports_calls_and_kinds(self):
        info = L.validate("shown('order', args['o']).get('status') == db('order', args['o'])['status']")
        self.assertEqual(info["calls"], ["db", "get", "shown"])
        self.assertEqual(info["kinds"], ["order"])

    def test_loop_variable_scope(self):
        with self.assertRaises(L.LookupFormatError):
            L.validate("all(x for x in args['l']) and x")
        L.validate("all(y for x in args['l'] for y in x)")


# ----------------------------------------------------------------------------------------------- evaluator

class TestEvaluator(unittest.TestCase):
    def setUp(self):
        self.pending = Data.order("pending")
        self.oid = self.pending["order_id"]

    def test_shown_vs_fact_and_if_missing(self):
        lk = {"expr": "shown('order', args['order_id'])['status'] == 'pending'", "if_missing": "false"}
        st = _state("retail", [], "cancel_pending_order", {"order_id": self.oid})
        self.assertIs(L.evaluate(lk, st), False)                    # not shown -> if_missing
        self.assertIsNone(L.evaluate(dict(lk, if_missing="unknown"), st))
        self.assertIs(L.evaluate("db('order', args['order_id'])['status'] == 'pending'", st), True)
        st2 = _state("retail", [("get_order_details", {"order_id": self.oid})], "cancel_pending_order",
                     {"order_id": self.oid})
        self.assertIs(L.evaluate(lk, st2), True)
        d = L.evaluate_detail(lk, st)
        self.assertIsNone(d["raw"])
        self.assertIn("TypeError", d["missing"])

    def test_newest_shown_version_counts(self):
        st = _state("retail", [("get_order_details", {"order_id": self.oid}),
                               ("cancel_pending_order", {"order_id": self.oid, "reason": "no longer needed"})])
        self.assertIs(L.evaluate("shown('order', args['order_id'])['status'] == 'pending'", st,
                                 args={"order_id": self.oid}), False)

    def test_missing_argument(self):
        st = _state("retail", [], "cancel_pending_order", {})
        d = L.evaluate_detail({"expr": "args['reason'] == 'x'", "if_missing": "unknown"}, st)
        self.assertIsNone(d["value"])
        self.assertIn("KeyError", d["missing"])

    def test_none_result_and_get_on_none(self):
        st = _state("retail", [], "x", {})
        self.assertIs(L.evaluate({"expr": "args.get('nothing')", "if_missing": "false"}, st), False)
        d = L.evaluate_detail({"expr": "shown('order', 'nope').get('status') == 'x'", "if_missing": "unknown"}, st)
        self.assertIsNone(d["value"])
        self.assertIsNotNone(d["missing"])

    def test_index_error_is_missing(self):
        st = _state("retail", [], "x", {"l": []})
        self.assertIsNone(L.evaluate("args['l'][0] == 1", st, if_missing="unknown"))

    def test_non_bool_result_is_an_error(self):
        st = _state("retail", [], "x", {"n": 3})
        with self.assertRaises(L.LookupEvalError):
            L.evaluate("len([1, 2])", st)
        with self.assertRaises(L.LookupEvalError):
            L.evaluate("args['n']", st)

    def test_unknown_kind_at_run_time_is_an_error(self):
        st = _state("retail", [], "x", {})
        with self.assertRaises(L.LookupEvalError):
            L.evaluate("shown('reservation', 'X') is None", st)

    def test_bad_if_missing(self):
        st = _state("retail", [], "x", {})
        with self.assertRaises(L.LookupFormatError):
            L.evaluate({"expr": "True", "if_missing": "true"}, st)

    def test_invalid_expression_is_not_run(self):
        st = _state("retail", [], "x", {})
        with self.assertRaises(L.LookupFormatError):
            L.evaluate("__import__('os').getcwd() == ''", st)

    def test_events(self):
        email = next(iter(Data.db("retail")["users"].values()))["email"]
        lk = "len(events(tool=['find_user_id_by_email', 'find_user_id_by_name_zip'], ok=True)) > 0"
        self.assertIs(L.evaluate(lk, _state("retail", [("find_user_id_by_email", {"email": email})])), True)
        self.assertIs(L.evaluate(lk, _state("retail", [("find_user_id_by_email", {"email": "no@x.com"})])), False)
        self.assertIs(L.evaluate("len(events(ok=False)) == 1",
                                 _state("retail", [("find_user_id_by_email", {"email": "no@x.com"})])), True)

    def test_dates_and_today(self):
        air = _state("airline", [], "x", {})
        self.assertIs(L.evaluate("date('2024-05-16') > today", air), True)
        self.assertIs(L.evaluate("date('2024-05-15') > today", air), False)      # 00:00 < 15:00
        self.assertIs(L.evaluate("date('2024-05-15 16:00:00') > today", air), True)
        ret = _state("retail", [], "x", {})                                     # retail: no current time
        self.assertIsNone(L.evaluate("date('2024-05-16') > today", ret, if_missing="unknown"))
        self.assertIsNone(L.evaluate("date('not a date') > today", air, if_missing="unknown"))

    def test_comprehensions_see_the_names(self):
        st = _state("retail", [("get_order_details", {"order_id": self.oid})], "x", {"ids": [self.oid, "#none"]})
        self.assertIs(L.evaluate("len([i for i in args['ids'] if shown('order', i) is not None]) == 1", st), True)
        self.assertIs(L.evaluate("any(shown('order', i) is None for i in args['ids'])", st), True)
        self.assertIs(L.evaluate("all(n == 2 for n in [len(args['ids'])])", st), True)

    def test_args_default_to_pending_call(self):
        st = _state("retail", [], "cancel_pending_order", {"reason": "ordered by mistake"})
        self.assertIs(L.evaluate("args['reason'] == 'ordered by mistake'", st), True)
        self.assertIs(L.evaluate("args['reason'] == 'ordered by mistake'", st, args={"reason": "x"}), False)


# ----------------------------------------------------------------------------------------------- lookup files

class TestLookupFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lk = {d: L.load_lookups(d) for d in ("airline", "retail")}

    def run_lk(self, domain, name, state, args):
        return L.evaluate(self.lk[domain][name], state, args=args)

    def test_files_pass_the_checks(self):
        for d in ("airline", "retail"):
            self.assertEqual(L.check_lookups(d), [], d)

    def test_check_finds_problems(self):
        bad = {"x": {"expr": "shown('order', 'a') is None", "uses": "fact", "if_missing": "maybe", "plain": "",
                     "reason": "r", "extra": 1}}
        problems = L.check_lookup("x", bad["x"], L.domain_kinds("retail"))
        text = " | ".join(problems)
        for part in ("'plain'", "unknown fields", "if_missing", "uses 'fact' but calls shown"):
            self.assertIn(part, text)
        self.assertTrue(any("no lookup for code-type predicate" in p for p in L.check_lookups("retail", {})))

    # --- retail
    def test_retail_order_status_and_reason(self):
        oid = Data.order("pending")["order_id"]
        none = _state("retail", [])
        seen = _state("retail", [("get_order_details", {"order_id": oid})])
        a = {"order_id": oid, "reason": "no longer needed"}
        self.assertIs(self.run_lk("retail", "order_status_checked_pending", none, a), False)
        self.assertIs(self.run_lk("retail", "order_status_checked_pending", seen, a), True)
        self.assertIs(self.run_lk("retail", "order_status_checked_delivered", seen, a), False)
        self.assertIs(self.run_lk("retail", "cancellation_reason_is_allowed", none, a), True)
        self.assertIs(self.run_lk("retail", "cancellation_reason_is_allowed", none, {"reason": "other"}), False)
        self.assertIsNone(self.run_lk("retail", "cancellation_reason_is_allowed", none, {}))

    def test_retail_payment_lookups(self):
        db = Data.db("retail")
        # a pending order with one payment whose user has a gift card other than the order's payment method
        order, gc = next((o, pm) for o in db["orders"].values() if o["status"] == "pending"
                         and len(o["payment_history"]) == 1
                         for pm in db["users"][o["user_id"]]["payment_methods"].values()
                         if pm["source"] == "gift_card" and pm["id"] != o["payment_history"][0]["payment_method_id"])
        oid, uid = order["order_id"], order["user_id"]
        st = _state("retail", [("get_order_details", {"order_id": oid}), ("get_user_details", {"user_id": uid})])
        a = {"order_id": oid, "payment_method_id": gc["id"]}
        self.assertIs(self.run_lk("retail", "payment_method_is_gift_card", st, a), True)
        self.assertIs(self.run_lk("retail", "payment_method_differs_from_original", st, a), True)
        self.assertIs(self.run_lk("retail", "payment_method_differs_from_original", st,
                                  dict(a, payment_method_id=order["payment_history"][0]["payment_method_id"])), False)
        covers = gc["balance"] >= order["payment_history"][0]["amount"]
        self.assertIs(self.run_lk("retail", "gift_card_balance_covers_order_total", st, a), covers)
        only_order = _state("retail", [("get_order_details", {"order_id": oid})])
        self.assertIs(self.run_lk("retail", "gift_card_balance_covers_order_total", only_order, a), False)

    def test_retail_item_replacements(self):
        db = Data.db("retail")
        # a delivered order and, for its first item, another available variant of the same product
        order, item, new = next((o, it, v) for o in db["orders"].values() if o["status"] == "delivered"
                                for it in o["items"][:1]
                                for v in db["products"][it["product_id"]]["variants"].values()
                                if v["available"] and v["item_id"] != it["item_id"])
        oid, pid = order["order_id"], item["product_id"]
        calls = [("get_order_details", {"order_id": oid}), ("get_product_details", {"product_id": pid})]
        st = _state("retail", calls)
        a = {"order_id": oid, "item_ids": [item["item_id"]], "new_item_ids": [new["item_id"]],
             "payment_method_id": order["payment_history"][0]["payment_method_id"]}
        name = "item_replacements_are_available_same_product_different_option"
        self.assertIs(self.run_lk("retail", name, st, a), True)
        self.assertIs(self.run_lk("retail", name, st, dict(a, new_item_ids=[item["item_id"]])), False)  # same item
        self.assertIs(self.run_lk("retail", name, _state("retail", calls[:1]), a), False)  # product not shown
        other = next(v["item_id"] for p in db["products"].values() if p["product_id"] != pid
                     for v in p["variants"].values() if v["available"])
        st2 = _state("retail", calls + [("get_product_details",
                                         {"product_id": db_product_of(db, other)})])
        self.assertIs(self.run_lk("retail", name, st2, dict(a, new_item_ids=[other])), False)  # other product
        self.assertIs(self.run_lk("retail", "return_refund_method_is_original_or_existing_gift_card", st, a), True)
        self.assertIs(self.run_lk("retail", "return_refund_method_is_original_or_existing_gift_card", st,
                                  dict(a, payment_method_id="credit_card_0000000")), False)

    def test_retail_price_difference(self):
        db = Data.db("retail")
        order, item, new, gc = next(
            (o, it, v, pm) for o in db["orders"].values() if o["status"] == "pending"
            for it in o["items"][:1]
            for v in db["products"][it["product_id"]]["variants"].values()
            if v["available"] and v["item_id"] != it["item_id"] and v["price"] > it["price"]
            for pm in db["users"][o["user_id"]]["payment_methods"].values() if pm["source"] == "gift_card")
        calls = [("get_order_details", {"order_id": order["order_id"]}),
                 ("get_product_details", {"product_id": item["product_id"]}),
                 ("get_user_details", {"user_id": order["user_id"]})]
        a = {"order_id": order["order_id"], "item_ids": [item["item_id"]], "new_item_ids": [new["item_id"]],
             "payment_method_id": gc["id"]}
        want = gc["balance"] + item["price"] >= new["price"]
        name = "gift_card_balance_covers_price_difference"
        self.assertIs(self.run_lk("retail", name, _state("retail", calls), a), want)
        self.assertIs(self.run_lk("retail", name, _state("retail", calls[:2]), a), False)   # gift card not shown

    def test_retail_user_authenticated(self):
        u = next(iter(Data.db("retail")["users"].values()))
        st = _state("retail", [("find_user_id_by_name_zip", {"first_name": u["name"]["first_name"],
                                                             "last_name": u["name"]["last_name"],
                                                             "zip": u["address"]["zip"]})])
        self.assertIs(self.run_lk("retail", "user_authenticated", st, {}), True)
        self.assertIs(self.run_lk("retail", "user_authenticated", _state("retail", []), {}), False)

    # --- airline
    def test_airline_booking_arguments(self):
        p = {"first_name": "A", "last_name": "B", "dob": "1990-01-01"}
        a = {"cabin": "economy", "flights": [{"flight_number": "HAT001", "date": "2024-05-20"}],
             "passengers": [p, p], "total_baggages": 3, "nonfree_baggages": 1,
             "payment_methods": [{"payment_id": "certificate_1", "amount": 1}, {"payment_id": "certificate_1", "amount": 1},
                                 {"payment_id": "gift_card_1", "amount": 1}, {"payment_id": "gift_card_2", "amount": 1},
                                 {"payment_id": "gift_card_3", "amount": 1}, {"payment_id": "credit_card_1", "amount": 1}]}
        st = _state("airline", [])
        run = lambda n, args: self.run_lk("airline", n, st, args)            # noqa: E731
        self.assertIs(run("booking_has_at_most_five_passengers", a), True)
        self.assertIs(run("booking_has_at_most_five_passengers", dict(a, passengers=[p] * 6)), False)
        self.assertIs(run("all_booking_passengers_share_flights_and_cabin", a), True)
        self.assertIs(run("all_booking_passengers_share_flights_and_cabin",
                          dict(a, passengers=[p, dict(p, cabin="business")])), False)
        self.assertIs(run("booking_payment_method_counts_within_limits", a), True)
        more = a["payment_methods"] + [{"payment_id": "gift_card_4", "amount": 1}]
        self.assertIs(run("booking_payment_method_counts_within_limits", dict(a, payment_methods=more)), False)
        two_cert = a["payment_methods"] + [{"payment_id": "certificate_2", "amount": 1}]
        self.assertIs(run("booking_payment_method_counts_within_limits", dict(a, payment_methods=two_cert)), False)
        # regular: 1 free per economy passenger -> 2 free; 3 bags -> 1 non-free
        self.assertIs(run("regular_member_booking_baggage_counts_correct", a), True)
        self.assertIs(run("regular_member_booking_baggage_counts_correct", dict(a, nonfree_baggages=0)), False)
        self.assertIs(run("regular_member_booking_baggage_counts_correct", dict(a, total_baggages=2, nonfree_baggages=0)), True)
        # silver: 2 free per economy passenger -> 4 free; 3 bags -> 0 non-free
        self.assertIs(run("silver_member_booking_baggage_counts_correct", a), False)
        self.assertIs(run("silver_member_booking_baggage_counts_correct", dict(a, nonfree_baggages=0)), True)
        # gold, business: 3 free each -> 6 free; 8 bags -> 2 non-free
        g = dict(a, cabin="business", total_baggages=8, nonfree_baggages=2)
        self.assertIs(run("gold_member_booking_baggage_counts_correct", g), True)
        self.assertIs(run("regular_member_booking_baggage_counts_correct", dict(a, cabin="basic_economy",
                                                                               nonfree_baggages=3)), True)
        self.assertIsNone(run("regular_member_booking_baggage_counts_correct", {"cabin": "economy"}))
        self.assertIs(run("all_pending_flight_segments_have_one_cabin", a), True)
        self.assertIs(run("all_pending_flight_segments_have_one_cabin",
                          dict(a, flights=[{"flight_number": "HAT001", "date": "2024-05-20", "cabin": "business"}])),
                      False)

    def test_airline_membership_and_profile(self):
        users = Data.db("airline")["users"]
        uid, u = next((k, v) for k, v in users.items() if v["membership"] == "silver")
        st = _state("airline", [("get_user_details", {"user_id": uid})])
        pid = next(iter(u["payment_methods"]))
        a = {"user_id": uid, "payment_methods": [{"payment_id": pid, "amount": 1}]}
        self.assertIs(self.run_lk("airline", "booking_user_is_silver_member", st, a), True)
        self.assertIs(self.run_lk("airline", "booking_user_is_gold_member", st, a), False)
        self.assertIs(self.run_lk("airline", "booking_user_is_silver_member", _state("airline", []), a), False)
        self.assertIs(self.run_lk("airline", "booking_payment_methods_found_in_user_profile", st, a), True)
        self.assertIs(self.run_lk("airline", "booking_payment_methods_found_in_user_profile", st,
                                  dict(a, payment_methods=[{"payment_id": "gift_card_0", "amount": 1}])), False)
        self.assertIs(self.run_lk("airline", "booking_payment_methods_found_in_user_profile",
                                  _state("airline", []), a), False)

    def test_airline_reservation_lookups(self):
        r = Data.reservation(lambda r: all(f["date"] > "2024-05-15" for f in r["flights"]) and "status" not in r)
        rid = r["reservation_id"]
        st = _state("airline", [("get_reservation_details", {"reservation_id": rid})])
        run = lambda n, args: self.run_lk("airline", n, st, args)            # noqa: E731
        same = [{"flight_number": f["flight_number"], "date": f["date"]} for f in r["flights"]]
        a = {"reservation_id": rid, "flights": same, "cabin": r["cabin"],
             "total_baggages": r["total_baggages"], "passengers": r["passengers"]}
        self.assertIs(run("reservation_has_no_used_flight_segments", a), True)
        self.assertIs(run("pending_flight_segments_are_unchanged", a), True)
        self.assertIs(run("pending_flight_update_changes_flights", a), False)
        self.assertIs(run("origin_destination_and_trip_type_preserved", a), True)
        changed = dict(a, flights=same[:-1] + [dict(same[-1], date="2030-01-01")])
        self.assertIs(run("pending_flight_segments_are_unchanged", changed), False)
        self.assertIs(run("pending_flight_update_changes_flights", changed), True)
        self.assertIs(run("pending_baggage_total_not_reduced", a), True)
        if r["total_baggages"] > 0:
            self.assertIs(run("pending_baggage_total_not_reduced", dict(a, total_baggages=r["total_baggages"] - 1)),
                          False)
        self.assertIs(run("pending_passenger_count_unchanged", a), True)
        self.assertIs(run("pending_passenger_count_unchanged", dict(a, passengers=r["passengers"] * 2)), False)
        cab = r["cabin"]
        self.assertIs(run("reservation_has_business_cabin", a), cab == "business")
        self.assertIs(run("reservation_has_basic_or_economy_cabin", a), cab in ("basic_economy", "economy"))
        self.assertIs(run("pending_flight_update_is_basic_economy", a), cab == "basic_economy")
        self.assertIs(run("reservation_has_travel_insurance", a), r["insurance"] == "yes")
        # nothing shown: every shown lookup is false
        empty = _state("airline", [])
        for n in ("reservation_has_no_used_flight_segments", "pending_flight_segments_are_unchanged",
                  "pending_flight_update_changes_flights", "reservation_has_business_cabin",
                  "reservation_has_travel_insurance", "origin_destination_and_trip_type_preserved"):
            self.assertIs(self.run_lk("airline", n, empty, a), False, n)

    def test_airline_used_segment(self):
        r = Data.reservation(lambda r: any(f["date"] < "2024-05-15" for f in r["flights"]))
        st = _state("airline", [("get_reservation_details", {"reservation_id": r["reservation_id"]})])
        self.assertIs(self.run_lk("airline", "reservation_has_no_used_flight_segments", st,
                                  {"reservation_id": r["reservation_id"]}), False)

    def test_airline_round_trip_route(self):
        r = Data.reservation(lambda r: r["flight_type"] == "round_trip" and len(r["flights"]) == 2)
        st = _state("airline", [("get_reservation_details", {"reservation_id": r["reservation_id"]})])
        same = [{"flight_number": f["flight_number"], "date": f["date"]} for f in r["flights"]]
        name = "origin_destination_and_trip_type_preserved"
        self.assertIs(self.run_lk("airline", name, st, {"reservation_id": r["reservation_id"], "flights": same}), True)
        self.assertIs(self.run_lk("airline", name, st, {"reservation_id": r["reservation_id"],
                                                        "flights": same[:1]}), False)     # one way only


class TestAuditFixes(unittest.TestCase):
    """Cases from the independent check (output/p5_independent_check.md) that the saved steps never reach.
    Changed lookups: output/p5_audit_responses.md."""

    @classmethod
    def setUpClass(cls):
        cls.lk = {d: L.load_lookups(d) for d in ("airline", "retail")}

    def run_lk(self, domain, name, state, args):
        return L.evaluate(self.lk[domain][name], state, args=args)

    # --- retail: old and new items are paired by position
    ITEMS = "item_replacements_are_available_same_product_different_option"

    def test_crossed_pairs_are_false(self):
        db = Data.db("retail")
        products = db["products"]

        def other(it):          # another available variant of the item's product
            return next((v["item_id"] for v in products[it["product_id"]]["variants"].values()
                         if v["available"] and v["item_id"] != it["item_id"]), None)
        order, a, b = next((o, a, b) for o in db["orders"].values() if o["status"] == "delivered"
                           for a in o["items"] for b in o["items"]
                           if a["product_id"] < b["product_id"] and other(a) and other(b))
        calls = [("get_order_details", {"order_id": order["order_id"]}),
                 ("get_product_details", {"product_id": a["product_id"]}),
                 ("get_product_details", {"product_id": b["product_id"]})]
        st = _state("retail", calls)
        args = {"order_id": order["order_id"], "item_ids": [a["item_id"], b["item_id"]],
                "payment_method_id": order["payment_history"][0]["payment_method_id"]}
        self.assertIs(self.run_lk("retail", self.ITEMS, st, dict(args, new_item_ids=[other(a), other(b)])), True)
        self.assertIs(self.run_lk("retail", self.ITEMS, st, dict(args, new_item_ids=[other(b), other(a)])), False)
        # τ-bench agrees: the crossed call fails
        out = S.run_tool("retail", S.load_db("retail"), "exchange_delivered_order_items",
                         dict(args, new_item_ids=[other(b), other(a)]))
        self.assertTrue(out.startswith("Error: new item"), out)

    def test_pair_with_an_old_item_of_the_same_product(self):
        db = Data.db("retail")
        products = db["products"]
        # a delivered order with two different items X, Y of one product; Y and a third variant Z are available
        order, x, y, z = next(
            (o, x, y, z["item_id"]) for o in db["orders"].values() if o["status"] == "delivered"
            for x in o["items"] for y in o["items"]
            if x["product_id"] == y["product_id"] and x["item_id"] != y["item_id"]
            and products[y["product_id"]]["variants"][y["item_id"]]["available"]
            for z in products[x["product_id"]]["variants"].values()
            if z["available"] and z["item_id"] not in (x["item_id"], y["item_id"]))
        st = _state("retail", [("get_order_details", {"order_id": order["order_id"]}),
                               ("get_product_details", {"product_id": x["product_id"]})])
        args = {"order_id": order["order_id"], "item_ids": [x["item_id"], y["item_id"]],
                "new_item_ids": [y["item_id"], z], "payment_method_id": order["payment_history"][0]["payment_method_id"]}
        self.assertIs(self.run_lk("retail", self.ITEMS, st, args), True)          # X -> Y, Y -> Z
        self.assertIs(self.run_lk("retail", self.ITEMS, st, dict(args, new_item_ids=[x["item_id"], z])), False)
        out = S.run_tool("retail", S.load_db("retail"), "exchange_delivered_order_items", args)
        self.assertFalse(out.startswith("Error"), out)

    # --- airline: the cabin after a successful cabin change
    def test_cabin_after_upgrade(self):
        db = Data.db("airline")

        def ok_for_economy(r):
            return all(f["date"] > "2024-05-15"
                       and db["flights"][f["flight_number"]]["dates"].get(f["date"], {}).get("status") == "available"
                       and db["flights"][f["flight_number"]]["dates"][f["date"]]["available_seats"]["economy"]
                       >= len(r["passengers"]) for f in r["flights"])
        r, card = next((r, pid) for r in db["reservations"].values()
                       if r["cabin"] == "basic_economy" and "status" not in r and ok_for_economy(r)
                       for pid, pm in db["users"][r["user_id"]]["payment_methods"].items()
                       if pm["source"] == "credit_card")
        rid = r["reservation_id"]
        same = [{"flight_number": f["flight_number"], "date": f["date"]} for f in r["flights"]]
        details = ("get_reservation_details", {"reservation_id": rid})
        upgrade = ("update_reservation_flights", {"reservation_id": rid, "cabin": "economy", "flights": same,
                                                  "payment_id": card})
        failed = ("update_reservation_flights", dict(upgrade[1], payment_id="credit_card_0"))
        changed = {"reservation_id": rid, "cabin": "economy", "payment_id": card,
                   "flights": same[:-1] + [dict(same[-1], date="2030-01-01")]}
        before, after = _state("airline", [details]), _state("airline", [details, upgrade])
        self.assertEqual(after.shown_get("reservation", rid)["cabin"], "basic_economy")   # τ-bench leaves it stale
        self.assertTrue(after.events_where(tool="update_reservation_flights", ok=True))
        for st, cab in ((before, "basic_economy"), (after, "economy"),
                        (_state("airline", [details, failed]), "basic_economy")):
            self.assertIs(self.run_lk("airline", "pending_flight_update_is_basic_economy", st, changed),
                          cab == "basic_economy")
            self.assertIs(self.run_lk("airline", "reservation_has_basic_or_economy_cabin", st, changed), True)
            self.assertIs(self.run_lk("airline", "reservation_has_business_cabin", st, changed), False)
        to_business = _state("airline", [details, ("update_reservation_flights", dict(upgrade[1], cabin="business"))])
        if to_business.events_where(tool="update_reservation_flights", ok=True):
            self.assertIs(self.run_lk("airline", "reservation_has_business_cabin", to_business, changed), True)
            self.assertIs(self.run_lk("airline", "reservation_has_basic_or_economy_cabin", to_business, changed),
                          False)
        # another reservation's update does not count
        self.assertIs(self.run_lk("airline", "pending_flight_update_is_basic_economy", after,
                                  dict(changed, reservation_id="NOT_SHOWN")), False)

    # --- airline: the route does not depend on the order of the flights
    ROUTE = "origin_destination_and_trip_type_preserved"

    def _route(self, test):
        r = Data.reservation(test)
        st = _state("airline", [("get_reservation_details", {"reservation_id": r["reservation_id"]})])
        same = [{"flight_number": f["flight_number"], "date": f["date"]} for f in r["flights"]]
        return r, st, same

    def test_round_trip_in_any_order(self):
        r, st, same = self._route(lambda r: r["flight_type"] == "round_trip" and len(r["flights"]) == 2
                                  and r["origin"] != r["destination"])
        a = {"reservation_id": r["reservation_id"]}
        self.assertIs(self.run_lk("airline", self.ROUTE, st, dict(a, flights=same)), True)
        self.assertIs(self.run_lk("airline", self.ROUTE, st, dict(a, flights=same[::-1])), True)
        flights = Data.db("airline")["flights"]
        away = next(n for n, f in flights.items() if f["origin"] == r["origin"] and f["destination"] != r["destination"])
        self.assertIs(self.run_lk("airline", self.ROUTE, st, dict(a, flights=[{"flight_number": away, "date": "2024-05-20"},
                                                                         same[1]])), False)   # other destination

    def test_one_way_routes(self):
        r, st, same = self._route(lambda r: r["flight_type"] == "one_way" and r["origin"] != r["destination"])
        a = {"reservation_id": r["reservation_id"]}
        self.assertIs(self.run_lk("airline", self.ROUTE, st, dict(a, flights=same[::-1])), True)
        flights = Data.db("airline")["flights"]
        back = next(n for n, f in flights.items() if f["origin"] == r["destination"])
        self.assertIs(self.run_lk("airline", self.ROUTE, st,
                                  dict(a, flights=same + [{"flight_number": back, "date": "2024-05-28"}])), False)
        # a one-way reservation whose origin equals its destination (a quirk of the data)
        r2, st2, same2 = self._route(lambda r: r["flight_type"] == "one_way" and r["origin"] == r["destination"])
        self.assertIs(self.run_lk("airline", self.ROUTE, st2, {"reservation_id": r2["reservation_id"],
                                                               "flights": same2}), True)


def db_product_of(db, item_id):
    return next(p["product_id"] for p in db["products"].values() if item_id in p["variants"])


if __name__ == "__main__":
    unittest.main()
