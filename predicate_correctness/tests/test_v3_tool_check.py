"""Tests for state_tracker/v3/tool_check.py (tracker v3 part 3). Standard library only, no LLM calls.

Run from predicate_correctness/:  python3 -B -m unittest tests.test_v3_tool_check -v

Pass marks (output/eval_v3/preregistration.md):
  P3.1  one built case per Error text, in the tool's own order          -> TestOneCasePerErrorText
  P3.2  the real state is unchanged after a check                        -> TestRealStateUnchanged
  P3.4  a fact checked after the first failing check is "not decided"    -> TestNotDecidedAfterFirstError
The states are built from hand-made conversations whose tool outputs are made by τ-bench's own tool code on a separate
copy of the data (as tests/test_state.py does). The objects used (an order with status "pending", a gift card whose
balance is below an order's total, ...) are found in τ-bench's data files by plain field comparisons.
"""
from __future__ import annotations

import copy
import inspect
import json
import os
import re
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_tracker import paths, tau_copy  # noqa: E402
from state_tracker import state as S  # noqa: E402
from state_tracker.v3 import tool_check as TC  # noqa: E402

PEND, DELIV = TC.PENDING, TC.DELIVERED
DIFF, GCT, REPL, GCD, REF, BPM, PAX = (TC.DIFFERS, TC.GC_TOTAL, TC.REPLACE, TC.GC_DIFF, TC.REFUND, TC.BOOK_PM,
                                       TC.PAX)
NO_ORDER, NO_USER, NO_RES, NO_PM, NO_FLIGHT = "#W0000000", "nobody_00000", "ZZZZZZ", "credit_card_0000000", "HAT999"
PAX1 = [{"first_name": "Ann", "last_name": "Lee", "dob": "1990-01-01"}]


def _conv(domain, calls):
    """System (the policy), user, then per call an assistant message with one tool call and its tool message, whose
    content is τ-bench's own output on a separate copy of the data (as in the real run)."""
    db = S.load_db(domain)
    msgs = [{"role": "system", "content": tau_copy.policy_text(domain)}, {"role": "user", "content": "hi"}]
    for i, (name, args) in enumerate(calls):
        out = S.run_tool(domain, db, name, copy.deepcopy(args))
        msgs.append({"role": "assistant", "content": None, "tool_calls": [
            {"id": f"call_{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]})
        msgs.append({"role": "tool", "tool_call_id": f"call_{i}", "name": name, "content": out})
    return msgs


def _state(domain, calls=()):
    st = S.build_state(_conv(domain, list(calls)), domain=domain)
    assert not st.mismatches and not st.problems, (st.mismatches, st.problems)
    return st


def _snapshot(st):
    return (json.dumps(st.db, sort_keys=True), json.dumps(st.events, sort_keys=True, default=str),
            json.dumps(st.shown, sort_keys=True), json.dumps(st.pending, sort_keys=True))


# ------------------------------------------------------------------------------------------------ fixtures (data)
class Retail:
    """Objects of τ-bench's retail data used by the cases."""

    def __init__(self):
        db = self.db = S.load_db("retail")
        self.orders, self.users, self.products = db["orders"], db["users"], db["products"]

    def pms(self, o):
        return self.users[o["user_id"]]["payment_methods"]

    def orig(self, o):
        return o["payment_history"][0]["payment_method_id"]

    def order(self, status, pred=lambda o: True):
        return next(o for o in self.orders.values() if o["status"] == status and pred(o))

    def replacement(self, o, pred=lambda diff: True, same=False):
        """(old item id, new item id, price difference) of an available variant of the same product."""
        for it in o["items"]:
            for vid, v in self.products[it["product_id"]]["variants"].items():
                if v["available"] and (vid == it["item_id"]) == same and pred(v["price"] - it["price"]):
                    return it["item_id"], vid, v["price"] - it["price"]
        return None

    def gift_cards(self, o):
        return [(pid, pm["balance"]) for pid, pm in self.pms(o).items() if pm["source"] == "gift_card"]

    def non_gift(self, o, other_than=None):
        return next((pid for pid, pm in self.pms(o).items() if pm["source"] != "gift_card" and pid != other_than),
                    None)


class Airline:
    def __init__(self):
        db = self.db = S.load_db("airline")
        self.users, self.res, self.flights = db["users"], db["reservations"], db["flights"]

    def pm_of(self, uid, source):
        return next((pid for pid, pm in self.users[uid]["payment_methods"].items() if pm["source"] == source), None)

    def user_with(self, *sources):
        return next(u for u, x in self.users.items() if all(self.pm_of(u, s) for s in sources))

    def dates(self, pred):
        """(flight number, date, date data) of flight dates matching pred(date data)."""
        for fn, f in self.flights.items():
            for d, dd in f["dates"].items():
                if pred(dd):
                    yield fn, d, dd


# ------------------------------------------------------------------------------------------------ the cases
def retail_cases(R):
    """[(tool, expected check, calls before, args, expected facts)], per tool in the tool's code order."""
    cases = []
    add = lambda *c: cases.append(c)  # noqa: E731
    one_payment = lambda o: len(o["payment_history"]) == 1  # noqa: E731

    # --- cancel_pending_order
    p = R.order("pending")
    d = R.order("delivered")
    add("cancel_pending_order", "order_not_found", [], {"order_id": NO_ORDER, "reason": "no longer needed"},
        {PEND: None})
    add("cancel_pending_order", "non_pending", [], {"order_id": d["order_id"], "reason": "no longer needed"},
        {PEND: False})
    add("cancel_pending_order", "invalid_reason", [], {"order_id": p["order_id"], "reason": "too expensive"},
        {PEND: True})
    add("cancel_pending_order", None, [], {"order_id": p["order_id"], "reason": "ordered by mistake"}, {PEND: True})

    # --- modify_pending_order_address
    addr = {"address1": "1 Main St", "address2": "", "city": "Austin", "state": "TX", "country": "USA",
            "zip": "78701"}
    add("modify_pending_order_address", "order_not_found", [], dict(order_id=NO_ORDER, **addr), {PEND: None})
    add("modify_pending_order_address", "non_pending", [], dict(order_id=d["order_id"], **addr), {PEND: False})
    add("modify_pending_order_address", None, [], dict(order_id=p["order_id"], **addr), {PEND: True})

    # --- modify_pending_order_items / exchange_delivered_order_items (same checks, other status)
    for tool, status, other, sfact in (("modify_pending_order_items", "pending", "delivered", PEND),
                                       ("exchange_delivered_order_items", "delivered", "pending", DELIV)):
        o = R.order(status, lambda o: R.replacement(o) and R.non_gift(o))
        old, new, _ = R.replacement(o)
        nongc = R.non_gift(o)
        oid = o["order_id"]
        status_check = "non_pending" if status == "pending" else "non_delivered"
        x = R.order(other, lambda o: R.replacement(o))
        xo, xn, _ = R.replacement(x)
        add(tool, "order_not_found", [], dict(order_id=NO_ORDER, item_ids=[old], new_item_ids=[new],
                                              payment_method_id=nongc), {sfact: None, REPL: None, GCD: None})
        add(tool, status_check, [], dict(order_id=x["order_id"], item_ids=[xo], new_item_ids=[xn],
                                         payment_method_id=R.non_gift(x) or NO_PM),
            {sfact: False, REPL: None, GCD: None})
        add(tool, "item_not_found", [], dict(order_id=oid, item_ids=["0000000000"], new_item_ids=[new],
                                             payment_method_id=nongc), {sfact: True, REPL: False, GCD: None})
        add(tool, "item_count_mismatch", [], dict(order_id=oid, item_ids=[old], new_item_ids=[],
                                                  payment_method_id=nongc), {sfact: True, REPL: False, GCD: None})
        add(tool, "new_item_not_found_or_available", [], dict(order_id=oid, item_ids=[old],
                                                              new_item_ids=["0000000000"], payment_method_id=nongc),
            {sfact: True, REPL: False, GCD: None})
        add(tool, "payment_method_not_found", [], dict(order_id=oid, item_ids=[old], new_item_ids=[new],
                                                       payment_method_id=NO_PM),
            {sfact: True, REPL: True, GCD: None})
        # a gift card whose balance is below the price difference
        g = R.order(status, lambda o: any(R.replacement(o, lambda df, b=b: df > b) for _, b in R.gift_cards(o)))
        gid, gbal = next((pid, b) for pid, b in R.gift_cards(g) if R.replacement(g, lambda df, b=b: df > b))
        go, gn, _ = R.replacement(g, lambda df: df > gbal)
        add(tool, "gift_card_insufficient", [], dict(order_id=g["order_id"], item_ids=[go], new_item_ids=[gn],
                                                     payment_method_id=gid), {sfact: True, REPL: True, GCD: False})
        # accepted: a gift card that covers the difference -> True; another source -> the tool checks no balance
        h = R.order(status, lambda o: any(R.replacement(o, lambda df, b=b: df <= b) for _, b in R.gift_cards(o)))
        hid, hbal = next((pid, b) for pid, b in R.gift_cards(h) if R.replacement(h, lambda df, b=b: df <= b))
        ho, hn, _ = R.replacement(h, lambda df: df <= hbal)
        add(tool, None, [], dict(order_id=h["order_id"], item_ids=[ho], new_item_ids=[hn], payment_method_id=hid),
            {sfact: True, REPL: True, GCD: True})
        add(tool, None, [], dict(order_id=oid, item_ids=[old], new_item_ids=[new], payment_method_id=nongc),
            {sfact: True, REPL: True, GCD: None})
        # accepted, but a "replacement" by the same item: the tool does not check "different option"
        s = R.order(status, lambda o: R.replacement(o, same=True) and R.non_gift(o))
        so, sn, _ = R.replacement(s, same=True)
        add(tool, None, [], dict(order_id=s["order_id"], item_ids=[so], new_item_ids=[sn],
                                 payment_method_id=R.non_gift(s)), {sfact: True, REPL: None, GCD: None})

    # --- modify_pending_order_payment
    def gc_short(o):
        return any(b < o["payment_history"][0]["amount"] and pid != R.orig(o) for pid, b in R.gift_cards(o))

    def gc_enough(o):
        return any(b >= o["payment_history"][0]["amount"] and pid != R.orig(o) for pid, b in R.gift_cards(o))

    m = R.order("pending", lambda o: one_payment(o) and R.non_gift(o, other_than=R.orig(o)))
    mid, alt = m["order_id"], R.non_gift(m, other_than=R.orig(m))
    tool = "modify_pending_order_payment"
    add(tool, "order_not_found", [], {"order_id": NO_ORDER, "payment_method_id": alt},
        {PEND: None, DIFF: None, GCT: None})
    add(tool, "non_pending", [], {"order_id": d["order_id"], "payment_method_id": R.orig(d)},
        {PEND: False, DIFF: None, GCT: None})
    add(tool, "payment_method_not_found", [], {"order_id": mid, "payment_method_id": NO_PM},
        {PEND: True, DIFF: None, GCT: None})
    add(tool, "not_exactly_one_payment", [(tool, {"order_id": mid, "payment_method_id": alt})],
        {"order_id": mid, "payment_method_id": R.orig(m)}, {PEND: True, DIFF: None, GCT: None})
    add(tool, "same_payment_method", [], {"order_id": mid, "payment_method_id": R.orig(m)},
        {PEND: True, DIFF: False, GCT: None})
    g = R.order("pending", lambda o: one_payment(o) and gc_short(o))
    gid = next(pid for pid, b in R.gift_cards(g) if b < g["payment_history"][0]["amount"] and pid != R.orig(g))
    add(tool, "gift_card_insufficient", [], {"order_id": g["order_id"], "payment_method_id": gid},
        {PEND: True, DIFF: True, GCT: False})
    h = R.order("pending", lambda o: one_payment(o) and gc_enough(o))
    hid = next(pid for pid, b in R.gift_cards(h) if b >= h["payment_history"][0]["amount"] and pid != R.orig(h))
    add(tool, None, [], {"order_id": h["order_id"], "payment_method_id": hid}, {PEND: True, DIFF: True, GCT: True})
    add(tool, None, [], {"order_id": mid, "payment_method_id": alt}, {PEND: True, DIFF: True, GCT: None})

    # --- modify_user_address
    uid = p["user_id"]
    add("modify_user_address", "user_not_found", [], dict(user_id=NO_USER, **addr), {})
    add("modify_user_address", None, [], dict(user_id=uid, **addr), {})

    # --- return_delivered_order_items
    tool = "return_delivered_order_items"
    r = R.order("delivered", lambda o: R.non_gift(o, other_than=R.orig(o)))
    rid, it = r["order_id"], r["items"][0]["item_id"]
    add(tool, "order_not_found", [], {"order_id": NO_ORDER, "item_ids": [it], "payment_method_id": R.orig(r)},
        {DELIV: None, REF: None})
    add(tool, "non_delivered", [], {"order_id": p["order_id"], "item_ids": [p["items"][0]["item_id"]],
                                    "payment_method_id": R.orig(p)}, {DELIV: False, REF: None})
    add(tool, "payment_method_not_found", [], {"order_id": rid, "item_ids": [it], "payment_method_id": NO_PM},
        {DELIV: True, REF: None})
    add(tool, "refund_method_not_allowed", [], {"order_id": rid, "item_ids": [it],
                                                "payment_method_id": R.non_gift(r, other_than=R.orig(r))},
        {DELIV: True, REF: False})
    add(tool, "some_item_not_found", [], {"order_id": rid, "item_ids": ["0000000000"],
                                          "payment_method_id": R.orig(r)}, {DELIV: True, REF: True})
    add(tool, None, [], {"order_id": rid, "item_ids": [it], "payment_method_id": R.orig(r)},
        {DELIV: True, REF: True})
    q = R.order("delivered", lambda o: any(pid != R.orig(o) for pid, _ in R.gift_cards(o)))
    qg = next(pid for pid, _ in R.gift_cards(q) if pid != R.orig(q))
    add(tool, None, [], {"order_id": q["order_id"], "item_ids": [q["items"][0]["item_id"]], "payment_method_id": qg},
        {DELIV: True, REF: True})
    return cases


def airline_cases(A):
    cases = []
    add = lambda *c: cases.append(c)  # noqa: E731
    uid = A.user_with("credit_card", "gift_card")
    cc, gc = A.pm_of(uid, "credit_card"), A.pm_of(uid, "gift_card")
    gc_amount = A.users[uid]["payment_methods"][gc]["amount"]
    fn, day, dd = next(A.dates(lambda x: x["status"] == "available" and x["available_seats"]["economy"] >= 1))
    price = dd["prices"]["economy"]
    f = A.flights[fn]

    def book(**kw):
        a = dict(user_id=uid, origin=f["origin"], destination=f["destination"], flight_type="one_way",
                 cabin="economy", flights=[{"flight_number": fn, "date": day}], passengers=PAX1,
                 payment_methods=[{"payment_id": cc, "amount": price}], total_baggages=0, nonfree_baggages=0,
                 insurance="no")
        a.update(kw)
        return a

    # --- book_reservation
    tool = "book_reservation"
    add(tool, "user_not_found", [], book(user_id=NO_USER), {BPM: None})
    add(tool, "flight_not_found", [], book(flights=[{"flight_number": NO_FLIGHT, "date": day}]), {BPM: None})
    add(tool, "flight_not_found_on_date", [], book(flights=[{"flight_number": fn, "date": "2099-01-01"}]),
        {BPM: None})
    lf, ld, _ = next(A.dates(lambda x: x["status"] == "landed"))
    add(tool, "flight_not_available_on_date", [], book(flights=[{"flight_number": lf, "date": ld}]), {BPM: None})
    sf, sd, sdd = next(A.dates(lambda x: x["status"] == "available" and x["available_seats"]["economy"] <= 3))
    many = [dict(PAX1[0], first_name=f"P{i}") for i in range(sdd["available_seats"]["economy"] + 1)]
    add(tool, "not_enough_seats", [], book(flights=[{"flight_number": sf, "date": sd}], passengers=many),
        {BPM: None})
    add(tool, "payment_method_not_found", [], book(payment_methods=[{"payment_id": NO_PM, "amount": price}]),
        {BPM: False})
    add(tool, "not_enough_balance", [], book(payment_methods=[{"payment_id": gc, "amount": gc_amount + 1}]),
        {BPM: True})
    add(tool, "payment_amount_mismatch", [], book(payment_methods=[{"payment_id": cc, "amount": price + 1}]),
        {BPM: True})
    add(tool, None, [], book(), {BPM: True})

    # --- cancel_reservation
    rid = next(iter(A.res))
    add("cancel_reservation", "reservation_not_found", [], {"reservation_id": NO_RES}, {})
    add("cancel_reservation", None, [], {"reservation_id": rid}, {})

    # --- send_certificate
    add("send_certificate", "user_not_found", [], {"user_id": NO_USER, "amount": 100}, {})
    add("send_certificate", None, [], {"user_id": uid, "amount": 100}, {})

    # --- update_reservation_baggages
    def res_of(pred):
        return next(r for r in A.res.values() if pred(r))

    tool = "update_reservation_baggages"
    rc = res_of(lambda r: A.pm_of(r["user_id"], "credit_card"))
    rcert = res_of(lambda r: A.pm_of(r["user_id"], "certificate"))
    rgc = res_of(lambda r: A.pm_of(r["user_id"], "gift_card"))
    g2 = A.pm_of(rgc["user_id"], "gift_card")
    g2_amount = A.users[rgc["user_id"]]["payment_methods"][g2]["amount"]
    bag = lambda r, pid, extra=0: {"reservation_id": r["reservation_id"],  # noqa: E731
                                   "total_baggages": r["total_baggages"] + extra,
                                   "nonfree_baggages": r["nonfree_baggages"] + extra, "payment_id": pid}
    add(tool, "reservation_not_found", [], dict(bag(rc, A.pm_of(rc["user_id"], "credit_card")),
                                                reservation_id=NO_RES), {})
    add(tool, "payment_method_not_found", [], bag(rc, NO_PM), {})
    add(tool, "certificate_not_allowed", [], bag(rcert, A.pm_of(rcert["user_id"], "certificate")), {})
    add(tool, "gift_card_balance_not_enough", [], bag(rgc, g2, extra=int(g2_amount // 50) + 1), {})
    add(tool, None, [], bag(rc, A.pm_of(rc["user_id"], "credit_card")), {})

    # --- update_reservation_flights
    tool = "update_reservation_flights"

    def keep(r):
        return [{"flight_number": x["flight_number"], "date": x["date"]} for x in r["flights"]]

    def upd(r, flights, pid, cabin=None):
        return {"reservation_id": r["reservation_id"], "cabin": cabin or r["cabin"], "flights": flights,
                "payment_id": pid}

    rcc = A.pm_of(rc["user_id"], "credit_card")
    add(tool, "reservation_not_found", [], dict(upd(rc, keep(rc), rcc), reservation_id=NO_RES), {})
    add(tool, "flight_not_found", [], upd(rc, [{"flight_number": NO_FLIGHT, "date": day}], rcc), {})
    add(tool, "flight_not_found_on_date", [], upd(rc, [{"flight_number": fn, "date": "2099-01-01"}], rcc), {})
    add(tool, "flight_not_available_on_date", [], upd(rc, [{"flight_number": lf, "date": ld}], rcc), {})
    n_pax = len(rc["passengers"])
    zf, zd, _ = next(A.dates(lambda x: x["status"] == "available" and x["available_seats"][rc["cabin"]] < n_pax))
    add(tool, "not_enough_seats", [], upd(rc, [{"flight_number": zf, "date": zd}], rcc), {})
    add(tool, "payment_method_not_found", [], upd(rc, keep(rc), NO_PM), {})
    add(tool, "certificate_not_allowed", [], upd(rcert, keep(rcert), A.pm_of(rcert["user_id"], "certificate")), {})
    # a gift card below the price of one more (new) flight for every passenger
    ng = len(rgc["passengers"])
    xf, xd, _ = next(A.dates(lambda x: x["status"] == "available" and x["available_seats"][rgc["cabin"]] >= ng
                             and x["prices"][rgc["cabin"]] * ng > g2_amount))
    add(tool, "gift_card_balance_not_enough", [], upd(rgc, keep(rgc) + [{"flight_number": xf, "date": xd}], g2), {})
    add(tool, None, [], upd(rc, keep(rc), rcc), {})

    # --- update_reservation_passengers
    tool = "update_reservation_passengers"
    add(tool, "reservation_not_found", [], {"reservation_id": NO_RES, "passengers": rc["passengers"]}, {PAX: None})
    add(tool, "passenger_count_mismatch", [], {"reservation_id": rc["reservation_id"],
                                               "passengers": rc["passengers"] + PAX1}, {PAX: False})
    add(tool, None, [], {"reservation_id": rc["reservation_id"], "passengers": rc["passengers"]}, {PAX: True})
    return cases


class _Cases:
    data = None

    @classmethod
    def get(cls):
        if cls.data is None:
            cls.data = {"retail": retail_cases(Retail()), "airline": airline_cases(Airline())}
        return cls.data


# ------------------------------------------------------------------------------------------------ the tables
class TestTables(unittest.TestCase):
    def test_every_write_tool_has_a_check_list(self):
        table = S.tool_table()["domains"]
        writes = {t for d in paths.DOMAINS for t, s in table[d]["tools"].items() if s.get("changes_db")}
        self.assertEqual(set(TC.TOOL_CHECKS), writes)
        self.assertEqual(set(TC.TOOL_FACTS), writes)
        for t, d in TC.TOOL_DOMAIN.items():
            self.assertTrue(TC.is_write_tool(d, t), t)
        self.assertFalse(TC.is_write_tool("retail", "transfer_to_human_agents"))
        self.assertFalse(TC.is_write_tool("airline", "get_reservation_details"))

    def test_check_order_is_the_tools_code_order(self):
        """The Error texts of each tool's source file, in order, equal the check list (P3.1: the tool's order)."""
        for tool, checks in TC.TOOL_CHECKS.items():
            cls = tau_copy.tools(TC.TOOL_DOMAIN[tool])[tool]
            with open(inspect.getfile(cls), encoding="utf-8") as f:
                src = f.read()
            in_code = re.findall(r'f?"(Error: [^"]*)"', src)
            self.assertEqual(in_code, [tmpl for _, tmpl, _ in checks], tool)
            self.assertEqual(len({n for n, _, _ in checks}), len(checks), f"{tool}: check names not unique")

    def test_fact_names_are_predicate_names(self):
        with open(os.path.join(paths.OUTPUT_DIR, "predicate_types.json"), encoding="utf-8") as f:
            types = json.load(f)
        for tool, facts in TC.TOOL_FACTS.items():
            for fact, deciding in facts.items():
                self.assertIn(fact, types[TC.TOOL_DOMAIN[tool]], f"{tool}: {fact}")
                self.assertEqual(TC.FACT_DOMAIN[fact], TC.TOOL_DOMAIN[tool])
                names = [n for n, _, _ in TC.TOOL_CHECKS[tool]]
                for c in deciding:
                    self.assertIn(c, names, f"{tool}: {fact}: {c}")
        used = {f for facts in TC.TOOL_FACTS.values() for f in facts}
        self.assertEqual(used, set(TC.ALL_FACTS))
        self.assertEqual(len(TC.TOOL_CHECKED_FACTS), 7)

    def test_data_facts_behind_two_readings(self):
        """Two readings of the docstring rest on facts of the data files: every order's original payment method is in
        its user's profile; no two variants of one product have the same options (so a different item id of the same
        product is a different option)."""
        R = Retail()
        self.assertTrue(all(o["payment_history"][0]["payment_method_id"] in R.pms(o) for o in R.orders.values()
                            if o["payment_history"]))
        for p in R.products.values():
            opts = [json.dumps(v["options"], sort_keys=True) for v in p["variants"].values()]
            self.assertEqual(len(opts), len(set(opts)), p["product_id"])


# ------------------------------------------------------------------------------------------------ P3.1
class TestOneCasePerErrorText(unittest.TestCase):
    """P3.1: for every write tool, one built case per Error text, in the tool's code order (plus accepted cases)."""

    def test_every_error_text_has_a_case_in_order(self):
        for domain, cases in _Cases.get().items():
            for tool in (t for t, d in TC.TOOL_DOMAIN.items() if d == domain):
                got = [c[1] for c in cases if c[0] == tool and c[1] is not None]
                want = [n for n, _, _ in TC.TOOL_CHECKS[tool]]
                self.assertEqual(got, want, tool)
                self.assertTrue(any(c[0] == tool and c[1] is None for c in cases), f"{tool}: no accepted case")

    def test_cases(self):
        n = 0
        for domain, cases in _Cases.get().items():
            for tool, want_check, before, args, want_facts in cases:
                with self.subTest(domain=domain, tool=tool, check=want_check):
                    st = _state(domain, before)
                    lab = TC.check(st, {"tool": tool, "args": args}, keep_output=True)
                    self.assertEqual(lab["check"], want_check, lab["output"])
                    self.assertEqual(lab["accepted"], want_check is None)
                    self.assertEqual(lab["tool"], tool)
                    if want_check is None:
                        self.assertIsNone(lab["first_error"])
                    else:
                        self.assertEqual(lab["first_error"], lab["output"])
                        self.assertTrue(lab["first_error"].startswith("Error: "))
                    self.assertEqual(lab["facts"], want_facts)
                    n += 1
        self.assertGreaterEqual(n, 70)

    def test_output_on_the_copy_equals_the_output_of_the_real_run(self):
        """On every case, the copy's output equals what the same call gives when the conversation really runs it."""
        for domain, cases in _Cases.get().items():
            for tool, want_check, before, args, _ in cases:
                with self.subTest(domain=domain, tool=tool, check=want_check):
                    st = _state(domain, before)
                    lab = TC.check(st, (tool, args), keep_output=True)
                    ran = _state(domain, list(before) + [(tool, args)])
                    self.assertEqual(lab["output"], ran.events[-1]["output"])

    def test_other_and_ambiguous_errors_decide_nothing(self):
        R = Retail()
        p = R.order("pending", lambda o: R.replacement(o))
        old, new, _ = R.replacement(p)
        st = _state("retail")
        # an exception inside the tool code (a missing argument): no listed check
        lab = TC.check(st, ("modify_pending_order_items", {"order_id": p["order_id"], "item_ids": [old],
                                                           "new_item_ids": [new]}))
        self.assertFalse(lab["accepted"])
        self.assertEqual(lab["check"], TC.OTHER)
        self.assertEqual(lab["facts"], {PEND: None, REPL: None, GCD: None})
        # "Error: order not found" is both check 1 and "<item> not found" when an item id is "order"
        lab = TC.check(st, ("modify_pending_order_items", {"order_id": NO_ORDER, "item_ids": ["order"],
                                                           "new_item_ids": [new], "payment_method_id": NO_PM}))
        self.assertEqual(lab["first_error"], "Error: order not found")
        self.assertEqual(lab["check"], TC.AMBIGUOUS)
        self.assertEqual(lab["facts"], {PEND: None, REPL: None, GCD: None})
        # airline: a flight without a date -> KeyError in the tool -> "Error: 'date'"
        A = Airline()
        uid = A.user_with("credit_card")
        st = _state("airline")
        lab = TC.check(st, ("book_reservation", dict(user_id=uid, origin="JFK", destination="LAX",
                                                     flight_type="one_way", cabin="economy",
                                                     flights=[{"flight_number": "HAT001"}], passengers=PAX1,
                                                     payment_methods=[], total_baggages=0, nonfree_baggages=0,
                                                     insurance="no")))
        self.assertEqual((lab["check"], lab["first_error"], lab["facts"]), (TC.OTHER, "Error: 'date'", {BPM: None}))

    def test_not_a_write_tool(self):
        st = _state("retail")
        for name in ("get_order_details", "transfer_to_human_agents", "think", "delete_everything"):
            with self.assertRaises(TC.NotAWriteTool):
                TC.check(st, (name, {}))
        with self.assertRaises(TC.NotAWriteTool):
            TC.check(_state("airline"), ("cancel_pending_order", {"order_id": NO_ORDER, "reason": "x"}))

    def test_pending_call_of_the_state(self):
        R = Retail()
        p = R.order("pending")
        st = S.build_state(_conv("retail", []), {"tool": "cancel_pending_order",
                                                 "args": {"order_id": p["order_id"], "reason": "no longer needed"}},
                           domain="retail")
        self.assertEqual(TC.check(st)["facts"], {PEND: True})


# ------------------------------------------------------------------------------------------------ P3.2
class TestRealStateUnchanged(unittest.TestCase):
    """P3.2: the real state (database, events, shown set, pending action) and the call's arguments are unchanged
    after a check, also when the call works and changes the copy."""

    def test_every_case_leaves_the_state_unchanged(self):
        changed_copies = 0
        for domain, cases in _Cases.get().items():
            for tool, want_check, before, args, _ in cases:
                with self.subTest(domain=domain, tool=tool, check=want_check):
                    st = _state(domain, before)
                    snap, args_before = _snapshot(st), json.dumps(args, sort_keys=True)
                    first = TC.check(st, {"tool": tool, "args": args})
                    self.assertEqual(_snapshot(st), snap)
                    self.assertEqual(json.dumps(args, sort_keys=True), args_before)
                    self.assertEqual(TC.check(st, {"tool": tool, "args": args}), first)   # same result again
                    if want_check is None:
                        db = copy.deepcopy(st.db)
                        S.run_tool(domain, db, tool, copy.deepcopy(args))
                        changed_copies += json.dumps(db, sort_keys=True) != snap[0]
        self.assertGreaterEqual(changed_copies, 15)    # the accepted calls do change a copy; the test can see it

    def test_book_reservation_stores_the_argument_lists(self):
        """book_reservation keeps the passed payment_methods as payment_history; the check passes a copy."""
        A = Airline()
        uid = A.user_with("credit_card")
        cc = A.pm_of(uid, "credit_card")
        fn, day, dd = next(A.dates(lambda x: x["status"] == "available" and x["available_seats"]["economy"] >= 1))
        f = A.flights[fn]
        args = dict(user_id=uid, origin=f["origin"], destination=f["destination"], flight_type="one_way",
                    cabin="economy", flights=[{"flight_number": fn, "date": day}], passengers=PAX1,
                    payment_methods=[{"payment_id": cc, "amount": dd["prices"]["economy"]}], total_baggages=0,
                    nonfree_baggages=0, insurance="no")
        st = _state("airline")
        snap = _snapshot(st)
        lab = TC.check(st, ("book_reservation", args), keep_output=True)
        self.assertTrue(lab["accepted"])
        self.assertNotIn("HATHAT", st.db["reservations"])
        self.assertEqual(_snapshot(st), snap)
        self.assertNotIn("price", args["flights"][0])


# ------------------------------------------------------------------------------------------------ P3.4
class TestNotDecidedAfterFirstError(unittest.TestCase):
    """P3.4: a fact whose check comes after the first failing check is None ("not decided by the tool")."""

    def test_rule_on_every_case(self):
        """For every failing case: a fact decided by the failing check is False, a fact whose deciding checks all come
        earlier is True or None (an exception of the docstring), every other fact is None."""
        for domain, cases in _Cases.get().items():
            for tool, want_check, before, args, want_facts in cases:
                if want_check is None:
                    continue
                order = [n for n, _, _ in TC.TOOL_CHECKS[tool]]
                k = order.index(want_check)
                for fact, deciding in TC.TOOL_FACTS[tool].items():
                    with self.subTest(tool=tool, check=want_check, fact=fact):
                        if want_check in deciding:
                            self.assertIs(want_facts[fact], False)
                        elif max(order.index(c) for c in deciding) > k:
                            self.assertIsNone(want_facts[fact])
                        else:
                            self.assertIn(want_facts[fact], (True, None))

    def test_named_cases(self):
        R = Retail()
        st = _state("retail")
        d = R.order("delivered")
        # modify payment on a delivered order: the status check fails first; the payment facts are not decided
        lab = TC.check(st, ("modify_pending_order_payment", {"order_id": d["order_id"],
                                                             "payment_method_id": R.orig(d)}))
        self.assertEqual(lab["facts"], {PEND: False, DIFF: None, GCT: None})
        # return to a payment method that is not in the profile: check 3; the refund-method check (4) never ran
        lab = TC.check(st, ("return_delivered_order_items", {"order_id": d["order_id"],
                                                             "item_ids": [d["items"][0]["item_id"]],
                                                             "payment_method_id": NO_PM}))
        self.assertEqual((lab["check"], lab["facts"]), ("payment_method_not_found", {DELIV: True, REF: None}))
        # airline: a balance error at the first of two payment methods leaves the second one unchecked
        A = Airline()
        uid = A.user_with("credit_card", "gift_card")
        cc, gc = A.pm_of(uid, "credit_card"), A.pm_of(uid, "gift_card")
        amount = A.users[uid]["payment_methods"][gc]["amount"]
        fn, day, dd = next(A.dates(lambda x: x["status"] == "available" and x["available_seats"]["economy"] >= 1))
        f = A.flights[fn]
        base = dict(user_id=uid, origin=f["origin"], destination=f["destination"], flight_type="one_way",
                    cabin="economy", flights=[{"flight_number": fn, "date": day}], passengers=PAX1,
                    total_baggages=0, nonfree_baggages=0, insurance="no")
        ast = _state("airline")
        lab = TC.check(ast, ("book_reservation", dict(base, payment_methods=[
            {"payment_id": gc, "amount": amount + 1}, {"payment_id": NO_PM, "amount": 1}])))
        self.assertEqual((lab["check"], lab["facts"]), ("not_enough_balance", {BPM: None}))
        lab = TC.check(ast, ("book_reservation", dict(base, payment_methods=[
            {"payment_id": cc, "amount": 1}, {"payment_id": gc, "amount": amount + 1}])))
        self.assertEqual((lab["check"], lab["facts"]), ("not_enough_balance", {BPM: True}))
        # a flight error comes before every payment check
        lab = TC.check(ast, ("book_reservation", dict(base, flights=[{"flight_number": NO_FLIGHT, "date": day}],
                                                      payment_methods=[{"payment_id": NO_PM, "amount": 1}])))
        self.assertEqual((lab["check"], lab["facts"]), ("flight_not_found", {BPM: None}))


if __name__ == "__main__":
    unittest.main()
