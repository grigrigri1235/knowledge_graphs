"""Tracker v4: the block messages (guard/feedback_v4.py) and the two new message checks (scoring/v4_message_check.py).

Made-up states only: tiny conversations built with τ-bench's own tool outputs (tests/test_v3_message_view.py build), on
a made-up v4 fact file = the v3 fact file plus tests/fixtures_v4/feedback/facts_patch_v4.json (the section 1.1 change
list of code_change_map.md). Unchanged facts are evaluated by the v3 evaluator with fake tiny answers (no LLM call);
the changed facts get made-up results (their v4 helpers are never run here), with made-up notes in the formats of
listing_v4 ({"missing": [records]}, {"option_clash": [...]}) and helpers_go_ahead_v4 ({"clash", "named", "call"}).

Covered: the missing line + expected value (order id, card, a listing that says another value); hidden before login;
another user's value hidden; advice per kind (K1, payment, clash, listing, K3, K7, K13 / K16, strict no); "do not
repeat" only when no step can fix it; VERSION 2 and render unchanged; the v4 fact file path; a port of the v3 message
tests (first line, policy, who and closing, several ways, unknowns, safety, bad input, simple, pure); and the message
check's P10.1 parse, P10.9 and P10.10 on these messages.

Run from predicate_correctness/:
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v4_feedback
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

from guard import feedback_v3 as FB3                                    # noqa: E402
from guard import feedback_v4 as FB                                     # noqa: E402
from method_tgr import feedback as TGR_FB                               # noqa: E402  (runner copy, via FB)
from state_tracker import paths                                          # noqa: E402
from state_tracker import state as S                                     # noqa: E402
from state_tracker.v3 import facts_format_v3 as F                       # noqa: E402
from state_tracker.v3 import questions as Q                             # noqa: E402
from tests.test_v3_message_view import MIA, OLIVIA, OLIVIA_EMAIL, ORDER, build   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PATCH_PATH = os.path.join(HERE, "fixtures_v4", "feedback", "facts_patch_v4.json")
TABLE = {d: json.load(open(F.rule_table_path(d), encoding="utf-8")) for d in paths.DOMAINS}
RULE_SET = {d: json.load(open(paths.rule_set_path(d), encoding="utf-8")) for d in paths.DOMAINS}
DB = {d: S.load_db(d) for d in paths.DOMAINS}
LOGIN = [("user", "Hi, my email is " + OLIVIA_EMAIL), ("call", "find_user_id_by_email", {"email": OLIVIA_EMAIL})]


def fixture_doc(domain):
    """The made-up v4 fact file of a domain: v3's file plus the patch (overlay form, code_change_map.md 0.3)."""
    doc = copy.deepcopy(F.load_facts(domain))
    patch = json.load(open(PATCH_PATH, encoding="utf-8"))[domain]
    for name, ch in patch.items():
        e = doc["facts"][name]
        for k in ("combine", "sources", "who"):
            if k in ch:
                e[k] = ch[k]
        for pid, part in ch.get("parts", {}).items():
            if part is None:
                e["parts"].pop(pid, None)
            else:
                e["parts"][pid] = dict(part)
    return doc


DOCS = {d: fixture_doc(d) for d in paths.DOMAINS}
DEFS = {d: DOCS[d]["facts"] for d in paths.DOMAINS}
PATCHED = {d: set(json.load(open(PATCH_PATH, encoding="utf-8"))[d]) for d in paths.DOMAINS}


def use_fixture():
    for d in paths.DOMAINS:
        FB.use_fact_file(d, DOCS[d])


def setUpModule():
    use_fixture()


def tearDownModule():
    for d in paths.DOMAINS:
        FB.use_fact_file(d, None)


def answers(table=None, default="no"):
    table = table or {}
    return Q.Questions(Q.FakeBackend(lambda qid, inputs, norm: table.get(qid, default)))


def made_up(entry, name, spec):
    """An evaluator-like result of a changed fact: spec {pid: value | (value, [notes]) | None (not run)}; parts not in
    spec are true."""
    parts, known = {}, {}
    for pid, p in entry["parts"].items():
        v = spec.get(pid, True) if spec else True
        notes = []
        if isinstance(v, tuple):
            v, notes = v
        how = "not_run" if v is None else "value"
        parts[pid] = {"value": v, "source": p["source"], "who": F.effective_who(entry, p), "reads": [], "how": how,
                      "detail": None, "notes": list(notes)}
        if v is not None:
            known[pid] = v
    value = F.combine_value(F.parse_combine(entry["combine"]), known)
    if value is None:
        value = bool(entry["blocking_value"])
    return {"fact": name, "value": bool(value), "source": list(entry.get("sources") or []), "how": "value",
            "parts": parts, "items": None, "deciding_item": None,
            "evidence": {"text": entry.get("evidence"),
                         "notes": [{"part": p, "item": None, "note": n} for p, r in parts.items() for n in r["notes"]]},
            "reads": [], "problems": [], "problems_ignored": [], "blocking_value": entry["blocking_value"]}


def case(domain, steps, tool, args, hook=None, v4=None):
    """(domain, tool, args, facts, violated rule ids, state, view, history) of one pending call."""
    hist, st, view = build(domain, steps, {"tool": tool, "args": args})
    hook = hook or answers()
    v4 = v4 or {}
    names = sorted({f for r in TABLE[domain]["rules"] if tool in r["actions"] for f in r["facts"]})
    facts = {}
    for n in names:
        if n in PATCHED[domain]:
            facts[n] = made_up(DEFS[domain][n], n, v4.get(n))
        else:
            facts[n] = F.evaluate(DEFS[domain][n], st, args, view=view, answers=hook, name=n)
    violated = []
    for r in TABLE[domain]["rules"]:
        if tool not in r["actions"]:
            continue
        vals = {f: facts[f]["value"] for f in r["facts"]}
        row = next(x for x in r["rows"] if x["action"] == tool and x["values"] == vals)
        if not row["holds"]:
            violated.append(r["id"])
    return domain, tool, args, facts, violated, st, view, hist


def msg(c, kind="rule"):
    d, tool, args, facts, viol, st, view = c[:7]
    return FB.build(kind, d, tool, args, viol, facts, st, view, TABLE[d], RULE_SET[d])


def plan(c):
    d, tool, args, facts, viol, st, view = c[:7]
    return FB.explain(d, tool, args, viol, facts, st, view, TABLE[d], RULE_SET[d])


def kinds(p):
    return [a["type"] for a in FB.advice_lines(p["advice"])]


def strings(x, out):
    if isinstance(x, str):
        out.append(x)
    elif isinstance(x, dict):
        for k, v in x.items():
            if isinstance(k, str) and k.startswith(("credit_card_", "gift_card_", "paypal_", "certificate_")):
                out.append(k)
            strings(v, out)
    elif isinstance(x, list):
        for v in x:
            strings(v, out)
    return out


def ares(pred):
    db = DB["airline"]
    return next(db["reservations"][k] for k in sorted(db["reservations"]) if pred(db["reservations"][k]))


def statuses(r):
    fl = DB["airline"]["flights"]
    return [fl[f["flight_number"]]["dates"].get(f["date"], {}).get("status") for f in r["flights"]]


OLD = "2024-05-14T15:00:00"


def other_order(user):
    db = DB["retail"]
    return next(o for o in sorted(db["orders"]) if db["orders"][o]["user_id"] == user)


def olivia_card():
    pms = DB["retail"]["users"][OLIVIA]["payment_methods"]
    return next(pid for pid, pm in sorted(pms.items()) if pm["source"] == "credit_card")


def mia_card():
    pms = DB["retail"]["users"][MIA]["payment_methods"]
    return next(pid for pid in sorted(pms))


def miss(*records):
    return [{"missing": list(records)}]


LISTED = "consequential_action_details_listed"
CONFIRMED = "user_explicitly_confirmed_pending_action"
CANCEL_OK = "user_confirmed_cancellation_order_and_reason"


# ================================================================================================ cases
def cancel(extra=(), v4=None, login=True, order=ORDER, reason="no longer needed", hook=None):
    steps = (LOGIN if login else []) + [("call", "get_order_details", {"order_id": order}),
                                        ("user", f"Please cancel order {order}, I no longer need it.")] + list(extra)
    return case("retail", steps, "cancel_pending_order", {"order_id": order, "reason": reason}, hook, v4)


def pay_change(pid, v4=None, extra=()):
    steps = LOGIN + [("call", "get_order_details", {"order_id": ORDER}),
                     ("user", "Please change the payment of my order.")] + list(extra)
    return case("retail", steps, "modify_pending_order_payment", {"order_id": ORDER, "payment_method_id": pid},
                v4=v4)


def gift_card_payment():
    steps = LOGIN + [("call", "get_order_details", {"order_id": ORDER}), ("user", "Pay it with my gift card.")]
    args = {"order_id": ORDER, "payment_method_id": "gift_card_7794233"}
    return case("retail", steps, "modify_pending_order_payment", args)


def air_cancel(r, look=False, words="change of plans", hook=None, v4=None):
    uid, rid = r["user_id"], r["reservation_id"]
    steps = [("user", f"Hi, I am {uid}. Please cancel reservation {rid}: {words}.")]
    if look:
        steps.append(("call", "get_reservation_details", {"reservation_id": rid}))
    return case("airline", steps, "cancel_reservation", {"reservation_id": rid}, hook or answers({"K7": "yes"}), v4)


def offer_reply(complaint="yes", request="no"):
    r = ares(lambda r: True)
    steps = [("user", f"Hi, I am {r['user_id']}. My flight was cancelled and I am very upset.")]
    args = {"content": "I am sorry. As a gesture I can offer you a $100 certificate."}
    hook = answers({"K8": complaint, "K9": complaint, "K10": request, "K12": "yes"})
    return case("airline", steps, "respond", args, hook)


# ================================================================================================ v4: module
class TestModule(unittest.TestCase):
    def test_version_and_render_unchanged(self):
        self.assertEqual(FB.VERSION, 2)
        self.assertEqual(inspect.getsource(FB.render), inspect.getsource(FB3.render))
        p = plan(cancel(v4={CONFIRMED: {"b": False}}))
        self.assertEqual(FB.render(p), FB3.render(p))

    def test_fact_file_is_v4(self):
        self.assertTrue(FB.fact_file_path("retail").endswith(os.path.join("state_tracker", "v4",
                                                                          "facts_v4_retail.json")))
        try:
            FB.use_fact_file("retail", "/nonexistent/facts_v4_retail.json")
            with self.assertRaisesRegex(FB.MessageInputError, "does not exist"):
                FB.fact_definitions("retail")
            with self.assertRaises(FB.MessageInputError):
                FB.use_fact_file("retail", 5)
        finally:
            use_fixture()
        self.assertIs(FB.fact_definitions("retail"), DEFS["retail"])
        self.assertIsNot(FB.fact_definitions("retail"), FB3.fact_definitions("retail"))

    def test_part_kinds(self):
        k = lambda e: FB.part_kind(e)["kind"]                      # noqa: E731
        self.assertEqual(k("ask_first_yes_v4('K1', go_ahead_candidates_v4())"), "go_ahead")
        self.assertEqual(k("ask_first_yes_v4('K1', go_ahead_candidates_v4(focus='payment'))"), "ask_payment")
        self.assertEqual(k("clash_free_v4()"), "clash")
        self.assertEqual(k("listing_ok_v4()"), "listing")
        self.assertEqual(k("len(listing_window_v4()) > 0"), "listing")
        self.assertEqual(k("len(go_ahead_candidates_v4()) > 0"), "go_ahead")
        self.assertEqual(k("ask_first_yes_v4('K3', reminder_candidates(args['order_id']), items='x')"), "reminder")
        self.assertEqual(k("ask_first_yes_v4('K7', user_messages())"), "ask_why")
        self.assertEqual(k("ask_first_yes_v4('K13', user_messages(), on_unclear=True)"), "tools")
        self.assertEqual(k("ask_first_yes_v4('K16', user_messages(), on_unclear=True)"), "tools")
        self.assertIsNone(k("db('order', args['order_id']) is not None"))
        self.assertIsNone(k("ask_first_yes_v4('K10', user_messages())"))

    def test_missing_records_formats(self):
        rec = {"line": "order id", "expected": ORDER, "forms": [ORDER], "fact": LISTED, "part": "b"}
        res = made_up(DEFS["retail"][LISTED], LISTED, {"b": (False, [{"missing": [rec]}, {"note": "JUDGE"},
                                                                     "free text", {"question": "K1", "missing": "x"}])})
        got = FB.missing_records(LISTED, res)
        self.assertEqual([r["line"] for r in got], ["order id"])
        res2 = made_up(DEFS["retail"][LISTED], LISTED, {"b": (False, [{"option_clash": [
            {"line": "new item for Water Bottle", "expected": "silver", "also_named": ["black"]}]}])})
        self.assertEqual(FB.missing_records(LISTED, res2)[0]["said"], ["black"])
        self.assertEqual(len(FB.missing_records(LISTED, res, [rec])), 1)          # the guard's copy: no repeat

    def test_payment_parts(self):
        self.assertEqual(FB.payment_parts("credit_card_1 (Visa, last four 1234), $5.00"), ("credit_card_1", ", $5.00"))
        self.assertEqual(FB.payment_parts("gift_card_7"), ("gift_card_7", ""))
        self.assertEqual(FB.payment_parts("#W1234567"), (None, ""))


# ================================================================================================ v4: missing lines
class TestMissingLines(unittest.TestCase):
    def test_order_id(self):
        rec = {"line": "order id", "expected": ORDER, "forms": [ORDER, ORDER[1:]], "fact": LISTED, "part": "b"}
        c = cancel(v4={LISTED: {"b": (False, miss(rec))}})
        text = msg(c)
        self.assertIn(f"  - Not stated in your listing: the order id {ORDER}.", text)
        self.assertIn("List the missing details above in one message to the user, then ask for a yes.", text)
        p = plan(c)
        self.assertEqual(p["safety"]["missing_lines"], 1)
        self.assertEqual(p["closing"], "When this is done, call cancel_pending_order again.")

    def test_card(self):
        card = olivia_card()
        pm = DB["retail"]["users"][OLIVIA]["payment_methods"][card]
        rec = {"line": "new payment method", "expected": f"{card} (Visa, last four {pm['last_four']})",
               "forms": [], "fact": LISTED, "part": "b"}
        text = msg(pay_change(card, v4={LISTED: {"b": (False, miss(rec))}}))
        brand = pm["brand"][0].upper() + pm["brand"][1:]
        tail = re.sub(r"\D", "", card)[-4:]
        extra = f"; the user may call it 'ending in {tail}'" if tail != pm["last_four"] else ""
        self.assertIn(f"Not stated: the new payment method. The call uses {card} ({brand}, last four "
                      f"{pm['last_four']}{extra}).", text)

    def test_card_id_only_record(self):
        card = olivia_card()
        rec = {"line": "card", "expected": card, "forms": [], "fact": LISTED, "part": "b"}
        text = msg(pay_change(card, v4={LISTED: {"b": (False, miss(rec))}}))
        self.assertRegex(text, rf"Not stated: the card\. The call uses {card} \(.+, last four \d{{4}}")

    def test_listing_says_another_value(self):
        rec = {"line": "new item", "of": "1586641416", "said": "black", "expected": "silver", "fact": LISTED,
               "part": "b"}
        text = msg(cancel(v4={LISTED: {"b": (False, miss(rec))}}))
        self.assertIn("Your listing says 'black' but the new item 1586641416 is silver.", text)
        clash = {"line": "new item for Water Bottle", "expected": "silver", "also_named": ["black"]}
        text = msg(cancel(v4={LISTED: {"b": (False, [{"option_clash": [clash]}])}}))
        self.assertIn("Your listing says 'black' but the new item for Water Bottle is silver.", text)

    def test_hidden_before_login(self):
        card = olivia_card()
        recs = [{"line": "order id", "expected": ORDER, "fact": LISTED, "part": "b"},
                {"line": "card", "expected": card, "fact": LISTED, "part": "b"}]
        c = cancel(login=False, v4={LISTED: {"b": (False, miss(*recs))}})
        p = plan(c)
        self.assertFalse(p["safety"]["logged_in"])
        self.assertEqual(p["safety"]["missing_hidden_login"], 2)
        text = msg(c)
        self.assertIn("  - Not stated in your listing: the order id.\n", text)
        self.assertIn("  - Not stated in your listing: the card.\n", text)
        self.assertIn(FB.HIDDEN_BEFORE_LOGIN, text)
        pm = DB["retail"]["users"][OLIVIA]["payment_methods"][card]
        self.assertNotIn(pm["last_four"], text)
        self.assertNotIn("last four", text)

    def test_other_users_order_hidden(self):
        theirs = other_order(MIA)
        o = DB["retail"]["orders"][theirs]
        recs = [{"line": "zip", "expected": o["address"]["zip"], "fact": LISTED, "part": "b"},
                {"line": "order id", "expected": theirs, "fact": LISTED, "part": "b"}]
        c = cancel(order=theirs, v4={LISTED: {"b": (False, miss(*recs))}})
        p = plan(c)
        self.assertTrue(p["safety"]["logged_in"])
        self.assertEqual(p["safety"]["missing_hidden_other"], 2)
        text = msg(c)
        self.assertIn("Not stated in your listing: the zip.", text)
        self.assertIn(FB.HIDDEN_OTHER, text)
        self.assertNotIn(o["address"]["zip"], text)
        self.assertNotIn(MIA, text)

    def test_other_users_card_hidden_on_own_order(self):
        rec = {"line": "card", "expected": mia_card(), "fact": LISTED, "part": "b"}
        c = pay_change(olivia_card(), v4={LISTED: {"b": (False, miss(rec))}})
        text = msg(c)
        self.assertNotIn(mia_card(), text.split("Not met:")[1].split("What makes it true:")[0].replace(
            "the call's", ""))
        self.assertIn("Not stated in your listing: the card.", text)
        self.assertEqual(plan(c)["safety"]["missing_hidden_other"], 1)

    def test_llm_text_never_shown(self):
        notes = [{"question": "K1", "quote": "yes", "missing": "SECRET MODEL TEXT"},
                 {"missing": "SECRET MODEL TEXT 2"}]
        text = msg(cancel(v4={CONFIRMED: {"b": (False, notes)}}))
        self.assertNotIn("SECRET", text)


# ================================================================================================ v4: advice
class TestAdvice(unittest.TestCase):
    def test_k1_go_ahead(self):
        c = cancel(v4={CONFIRMED: {"b": False}, CANCEL_OK: {"b": False}})
        text = msg(c)
        want = f"Ask: 'Shall I go ahead with cancelling order {ORDER} (reason: no longer needed)? Please reply yes or no.'"
        self.assertIn(want, text)
        self.assertEqual(text.count(want), 1)                    # two facts, one line
        self.assertNotIn("Ask the user (the policy tells you to)", text)
        self.assertTrue(text.endswith("When this is done, call cancel_pending_order again."))
        self.assertIn("go_ahead", kinds(plan(c)))

    def test_payment_ask(self):
        c = pay_change(olivia_card(), v4={"user_chose_pending_payment_method": {"a": False, "c": False}})
        self.assertIn(f"Ask: 'Which payment method should order {ORDER} use?'", msg(c))

    def test_clash_names_both_values(self):
        card = olivia_card()
        note = {"clash": "payment", "named": ["paypal_8049766"], "call": [card], "message": 5, "text": "use paypal"}
        c = pay_change(card, v4={CONFIRMED: {"c": (False, [note])}})
        text = msg(c)
        self.assertRegex(text, rf"The user named 'paypal_8049766 \(PayPal\)' but the call uses {card} \(.+\)\. Ask "
                               r"the user which one they want\.")
        self.assertNotIn("use paypal", text)

    def test_clash_record_from_user(self):
        zipc = DB["retail"]["orders"][ORDER]["address"]["zip"]          # Olivia's own order: may be shown
        rec = {"line": "zip", "expected": zipc, "said": "my zip is 10001", "by": "user", "fact": CONFIRMED}
        c = cancel(v4={CONFIRMED: {"c": (False, [{"missing": [rec]}])}})
        text = msg(c)
        self.assertNotIn("Your listing says", text)                # a clash, not a listing line
        self.assertIn(f"The user named 'my zip is 10001' but the call uses {zipc}.", text)
        theirs = other_order(MIA)                                   # another user's zip: hidden
        rec2 = dict(rec, expected=DB["retail"]["orders"][theirs]["address"]["zip"])
        text = msg(cancel(v4={CONFIRMED: {"c": (False, [{"missing": [rec2]}])}}))
        if rec2["expected"] != zipc:
            self.assertNotIn(rec2["expected"], text)

    def test_k3_exact_sentence(self):
        order = DB["retail"]["orders"][ORDER]
        it = order["items"][0]
        args = {"order_id": ORDER, "item_ids": [it["item_id"]], "new_item_ids": [it["item_id"]],
                "payment_method_id": "paypal_8049766"}
        steps = LOGIN + [("call", "get_order_details", {"order_id": ORDER}), ("user", "Change my item please.")]
        c = case("retail", steps, "modify_pending_order_items", args,
                 v4={"agent_reminded_user_to_include_all_items_for_modification": {"b": False}})
        self.assertIn(f"Before this change, ask the user: 'Are the {it['name']} all the items you want to modify in "
                      f"order {ORDER}? This can be done only once.'", msg(c))

    def test_k7_ask_why(self):
        r = ares(lambda r: r["created_at"] < OLD and r["cabin"] == "business" and set(statuses(r)) == {"available"})
        c = air_cancel(r, look=True, v4={"cancellation_context_established": {"d": False}})
        text = msg(c)
        self.assertIn(f"Ask the user why they want to cancel reservation {r['reservation_id']} (change of plan, the "
                      f"airline cancelled the flight, or another reason).", text)

    def test_k6_ask_why_never_suggests(self):
        an = {"fact": "insured_cancellation_condition_met", "value": False, "status": "user_only", "shown": "false",
              "chosen": {"parts": ["b"], "who": {"b": "user_only"}}, "part_values": {"a": True, "b": False}}
        lines = FB.fact_advice("airline", an, {"reservation_id": "ABC123"}, None, "tool_call", None,
                               tool="cancel_reservation")
        self.assertEqual([a["text"] for a in lines],
                         ["Ask the user why they want to cancel reservation ABC123. Do not suggest a reason."])

    def test_k13_tools_line(self):
        note = {"question": "K13", "quote": "cancel my order", "missing": "cancel_pending_order can do it; JUDGE"}
        steps = LOGIN + [("user", f"I want to cancel order {ORDER}, get me a human.")]
        c = case("retail", steps, "transfer_to_human_agents", {"summary": "user wants a human"},
                 v4={"request_cannot_be_handled_within_scope": {"b": (False, [note])}})
        text = msg(c)
        quote = f"I want to cancel order {ORDER}, get me a human."
        self.assertIn(f"Do not transfer yet: the user's request (\"{quote}\") can be done with cancel_pending_order. "
                      f"Do it, or deny it if the policy forbids it.", text)
        self.assertNotIn("JUDGE", text)
        self.assertNotIn("Do not lead the user", text)
        self.assertTrue(text.endswith("Do not repeat the same call as it stands."))     # no step makes it true
        # no tool in the notes: the tool comes from the user's own words (code), never the generic line
        c = case("retail", steps, "transfer_to_human_agents", {"summary": "x"},
                 v4={"request_cannot_be_handled_within_scope": {"b": False}})
        text = msg(c)
        self.assertIn(f"Do not transfer yet: the user's request (\"{quote}\") can be done with cancel_pending_order.",
                      text)
        self.assertNotIn("Your tools can do this request", text)
        line = next(a for a in FB.advice_lines(plan(c)["advice"]) if a["type"] == "tools")
        self.assertEqual((line["tools"], line["tools_from"]), (["cancel_pending_order"], "request"))

    def test_airline_k13(self):
        r = ares(lambda r: True)
        steps = [("user", f"Hi, I am {r['user_id']}. I want a human.")]
        c = case("airline", steps, "transfer_to_human_agents", {"summary": "x"},
                 v4={"request_cannot_be_handled_with_available_tools": {
                     "a": (False, [{"question": "K13", "missing": "update_reservation_flights"}]), "c": False}})
        self.assertIn(f"Do not transfer yet: the user's request (\"Hi, I am {r['user_id']}. I want a human.\") can be "
                      f"done with update_reservation_flights. Do it, or deny it if the policy forbids it.", msg(c))

    def test_transfer_names_the_tools_of_the_newest_request(self):
        """Fix 2: the transfer line names the tool(s) from the newest user message whose words a tool does (newest
        first; several tools in the order the message names them); the older request is not used."""
        r = ares(lambda r: True)
        newest = f"Please cancel reservation {r['reservation_id']} and change my other trip to a nonstop flight."
        steps = [("user", f"Hi, I am {r['user_id']}. I want to add a bag."),
                 ("user", newest), ("user", "Yes, thank you.")]
        c = case("airline", steps, "transfer_to_human_agents", {"summary": "x"},
                 v4={"request_cannot_be_handled_with_available_tools": {"a": False, "b": False, "c": False}})
        text = msg(c)
        self.assertIn(f"Do not transfer yet: the user's request (\"{newest}\") can be done with cancel_reservation, "
                      f"update_reservation_flights. Do it, or deny it if the policy forbids it.", text)
        self.assertNotIn("update_reservation_baggages", text)
        self.assertNotIn("Your tools can do this", text)
        steps = [("user", f"Hi, I am {r['user_id']}. My flight was delayed, what compensation can you give me?")]
        c = case("airline", steps, "transfer_to_human_agents", {"summary": "x"},
                 v4={"request_cannot_be_handled_with_available_tools": {"a": False, "b": False, "c": False}})
        self.assertIn("can be done with send_certificate.", msg(c))

    def test_transfer_falls_back_to_the_called_tools(self):
        """Fix 2: no request words a tool does: the write tools the agent already called name the tool."""
        r = ares(lambda r: True)
        rid = r["reservation_id"]
        steps = [("user", f"Hi, I am {r['user_id']}."),
                 ("call", "update_reservation_baggages", {"reservation_id": rid, "total_baggages": 0,
                                                          "nonfree_baggages": 0, "payment_id": "x"}),
                 ("user", "Yes, make that change please.")]
        c = case("airline", steps, "transfer_to_human_agents", {"summary": "x"},
                 v4={"request_cannot_be_handled_with_available_tools": {"a": False, "b": False, "c": False}})
        text = msg(c)
        self.assertIn("Do not transfer yet: the user's request (\"Yes, make that change please.\") can be done with "
                      "update_reservation_baggages.", text)
        line = next(a for a in FB.advice_lines(plan(c)["advice"]) if a["type"] == "tools")
        self.assertEqual(line["tools_from"], "events")

    def test_request_tools_helpers(self):
        r = ares(lambda r: True)
        _, _, _, _, _, _, view, _ = case("airline", [("user", f"I am {r['user_id']}."), ("user", "x " * 200)],
                                         "transfer_to_human_agents", {"summary": "x"})
        self.assertEqual(FB.request_tools("airline", view), ([], None))
        q = FB.user_quote(view, None)
        self.assertTrue(q.endswith(" ...") and len(q) <= FB.MAX_QUOTE_CHARS + 4, q)
        self.assertEqual(FB.request_tools("airline", None), ([], None))
        self.assertIsNone(FB.user_quote(None, None))
        for d in FB.REQUEST_TOOLS:                                  # every pattern names a real tool of the domain
            for t, rx in FB.REQUEST_TOOLS[d]:
                self.assertIn(t, FB.tool_schemas(d))
                self.assertNotEqual(t, "transfer_to_human_agents")
                re.compile(rx)

    def test_v4_line_drops_the_generic_step_line(self):
        """Fix 1 (P10.9, partner.luna_train_v5|airline/5/2|16): the listing + go-ahead lines cover the fact, so v3's
        generic 'Do this step first, so that this becomes true: <fact>' line of its kind-less part (a, the anchor) is
        not added."""
        f = "pending_database_change_details_listed_and_explicitly_confirmed"
        entry = {"combine": "a AND b AND c", "who": "ask", "blocking_value": False, "parts": {
            "a": {"source": "structure", "expr": "len(go_ahead_anchors_v4()) > 0", "who": "agent"},
            "b": {"source": "structure", "expr": "len(go_ahead_candidates_v4()) > 0"},
            "c": {"source": "structure", "expr": "listing_ok_v4()", "who": "agent"}}}
        doc = copy.deepcopy(DOCS["airline"])
        doc["facts"][f] = entry
        rec = {"line": "payment method", "expected": "gift_card_1", "fact": f, "part": "c"}
        res = made_up(entry, f, {"a": False, "b": False, "c": (False, miss(rec))})
        an = {"fact": f, "value": False, "status": "fixable", "shown": "false",
              "chosen": {"parts": ["a", "b", "c"], "who": {"a": "agent", "b": "ask", "c": "agent"}},
              "part_values": {"a": False, "b": False, "c": False}}
        try:
            FB.use_fact_file("airline", doc)
            lines = FB.fact_advice("airline", an, {"reservation_id": "ABC123"}, None, "tool_call", None,
                                   result=res, tool="update_reservation_baggages")
        finally:
            use_fixture()
        self.assertEqual([a["type"] for a in lines], ["go_ahead", "listing"])
        self.assertFalse(any(a["text"].startswith("Do this step first, so that this becomes true") for a in lines))
        # a fact with no v4 line keeps v3's generic step (unchanged)
        an2 = dict(an, chosen={"parts": ["a"], "who": {"a": "agent"}}, part_values={"a": False, "b": True, "c": True})
        try:
            FB.use_fact_file("airline", doc)
            lines = FB.fact_advice("airline", an2, {}, None, "tool_call", None, result=res, tool="book_reservation")
        finally:
            use_fixture()
        self.assertEqual([a["type"] for a in lines], ["step"])

    def test_strict_no_turns_asks_into_no(self):
        c = cancel([("agent", f"I will cancel order {ORDER}. Confirm?"), ("user", "No, wait.")],
                   v4={CONFIRMED: {"b": False}})
        p = plan(c)
        self.assertIn("ask_no", kinds(p))
        self.assertNotIn("go_ahead", kinds(p))
        self.assertTrue(p["forbid"])
        self.assertTrue(msg(c).endswith("Do not repeat the same call as it stands."))

    def test_do_not_repeat_only_when_no_step(self):
        self.assertEqual(plan(gift_card_payment())["closing"], "Do not repeat the same call as it stands.")
        p = plan(cancel(v4={CONFIRMED: {"b": False}}))
        self.assertFalse(p["forbid"])

    def test_airline_listing_and_go_ahead(self):
        r = ares(lambda r: r["cabin"] != "basic_economy")
        f = "pending_database_change_details_listed_and_explicitly_confirmed"
        rec = {"line": "reservation id", "expected": r["reservation_id"], "fact": f, "part": "c"}
        steps = [("user", f"Hi, I am {r['user_id']}. Add a bag to {r['reservation_id']}."),
                 ("call", "get_reservation_details", {"reservation_id": r["reservation_id"]})]
        args = {"reservation_id": r["reservation_id"], "total_baggages": 3, "nonfree_baggages": 1,
                "payment_id": next(iter(DB["airline"]["users"][r["user_id"]]["payment_methods"]))}
        c = case("airline", steps, "update_reservation_baggages", args,
                 v4={f: {"c": (False, miss(rec)), "d": False}})
        text = msg(c)
        self.assertIn(f"Not stated in your listing: the reservation id {r['reservation_id']}.", text)
        self.assertIn(f"Ask: 'Shall I go ahead with changing the checked bags of reservation {r['reservation_id']} "
                      f"to 3 in total? Please reply yes or no.'", text)


# ================================================================================================ port of v3's tests
class TestPortFirstLineAndPolicy(unittest.TestCase):
    def test_first_line_is_tgr_own(self):
        want = TGR_FB.actionable("tool_call", "cancel_pending_order", [], None, {}, {}, {}).split("\n")[0]
        self.assertEqual(msg(cancel(v4={CONFIRMED: {"b": False}})).split("\n")[0], want)
        want = TGR_FB.actionable("respond", "respond", [], None, {}, {}, {}).split("\n")[0]
        self.assertEqual(msg(offer_reply()).split("\n")[0], want)

    def test_policy_quotes_the_cited_sentences(self):
        c = cancel(v4={CONFIRMED: {"b": False}})
        text = msg(c)
        rules = {r["id"]: r for r in RULE_SET["retail"]["rules"]}
        sents = {s["id"]: s["text"] for s in RULE_SET["retail"]["sentences"]}
        want = []
        for rid in c[4]:
            for sid in rules[rid]["sentences"]:
                if sents[sid] not in want:
                    want.append(sents[sid])
        policy = next(x for x in text.split("\n") if x.startswith("Policy: "))
        self.assertEqual(policy, "Policy: " + " ".join(f"\"{s}\"" for s in want))

    def test_never_the_predicate_descriptions(self):
        for c in (cancel(v4={CONFIRMED: {"b": False}}), gift_card_payment(),
                  air_cancel(ares(lambda r: r["cabin"] == "business")), offer_reply()):
            text = msg(c)
            for p in RULE_SET[c[0]]["predicates"].values():
                self.assertNotIn(p["description"], text)


class TestPortWhoAndClosing(unittest.TestCase):
    def test_agent_login_then_call_again(self):
        args = {"order_id": ORDER}
        c = case("retail", [("user", f"What is in order {ORDER}?")], "get_order_details", args)
        p = plan(c)
        self.assertEqual(kinds(p), ["user_args_call"])
        self.assertEqual(p["closing"], "When this is done, call get_order_details again.")

    def test_lookup_then_call_again(self):
        c = case("retail", LOGIN + [("user", f"Please cancel order {ORDER}.")], "cancel_pending_order",
                 {"order_id": ORDER, "reason": "no longer needed"})
        p = plan(c)
        look = next(a for a in FB.advice_lines(p["advice"]) if a["type"] == "lookup")
        self.assertEqual((look["tool"], look["args"]), ("get_order_details", {"order_id": ORDER}))
        self.assertFalse(p["forbid"])

    def test_user_only_never_a_step(self):
        r = ares(lambda r: True)
        args = {"user_id": r["user_id"], "amount": 100}
        c = case("airline", [("user", f"Hi, I am {r['user_id']}. I want to change my flight.")], "send_certificate",
                 args)
        p = plan(c)
        self.assertTrue(set(kinds(p)) <= {"user_only"}, kinds(p))
        self.assertTrue(msg(c).endswith("Do not repeat the same call as it stands."))

    def test_negated_agent_fact_reply(self):
        p = plan(offer_reply())
        self.assertIn("change", kinds(p))
        self.assertEqual(p["closing"], "When this is done, send your message again.")

    def test_one_rule_fixable_one_not(self):
        c = cancel(reason="other")
        p = plan(c)
        fix = {r["rule_id"]: r["fixable"] for r in p["rules"]}
        self.assertFalse(fix["45"])
        self.assertTrue(p["forbid"])
        self.assertIn("the call's reason = \"other\"", msg(c))


class TestPortSeveralWays(unittest.TestCase):
    def test_business_not_looked_up(self):
        r = ares(lambda r: r["created_at"] < OLD and r["cabin"] == "business" and set(statuses(r)) == {"available"})
        c = air_cancel(r)
        p = plan(c)
        r25 = next(x for x in p["rules"] if x["rule_id"] == "25")
        self.assertEqual(len(r25["ways"]), 4)
        text = msg(c)
        self.assertIn(FB.ANY_ONE, text)
        self.assertIn(f"look it up with get_reservation_details (reservation_id \"{r['reservation_id']}\")", text)
        self.assertNotIn("insured", text)

    def test_no_way_left(self):
        r = ares(lambda r: r["created_at"] < OLD and r["cabin"] == "economy" and r["insurance"] == "no"
                 and set(statuses(r)) == {"available"})
        c = air_cancel(r, look=True)
        self.assertTrue(plan(c)["forbid"])
        text = msg(c)
        self.assertIn(f"reservation {r['reservation_id']}: created_at = \"{r['created_at']}\"", text)
        self.assertTrue(text.endswith("Do not repeat the same call as it stands."))


class TestPortUnknown(unittest.TestCase):
    def test_stand_in_unknown(self):
        c = list(cancel(v4={CONFIRMED: {"b": False}}))
        facts = dict(c[3])
        facts[CONFIRMED] = {"value": None}
        c[3] = facts
        self.assertIn(f"- {FB.words(CONFIRMED)}: not established", msg(c))

    def test_lazy_skip(self):
        c = list(cancel(v4={CONFIRMED: {"b": False}}))
        facts = dict(c[3])
        facts[CONFIRMED] = dict(facts[CONFIRMED], how="lazy_skip")
        c[3] = facts
        self.assertIn(f"- {FB.words(CONFIRMED)}: not established", msg(c))


class TestPortSafety(unittest.TestCase):
    def test_before_login_no_database_value(self):
        args = {"order_id": ORDER, "payment_method_id": "gift_card_7794233"}
        c = case("retail", [("user", "Change the payment of my order to my gift card.")],
                 "modify_pending_order_payment", args)
        text = msg(c)
        for line in text.split("\n"):
            self.assertNotRegex(line, r"^  - (user|order|product|variant|payment_method) ")
        self.assertNotIn("663.85", text)

    def test_other_users_record_hidden(self):
        theirs = other_order(MIA)
        c = case("retail", LOGIN + [("user", f"Show me order {theirs}.")], "get_order_details", {"order_id": theirs})
        text = msg(c)
        self.assertNotIn(MIA, text)
        for s in strings(DB["retail"]["users"][MIA], []):
            if len(s) >= 5:
                self.assertNotIn(s, text, s)

    def test_no_judge_text(self):
        c = list(cancel(v4={CONFIRMED: {"b": False}}))
        facts = copy.deepcopy(c[3])
        for r in facts.values():
            r["evidence"] = {"text": "JUDGE SAYS SECRET", "notes": [{"note": "JUDGE NOTE"}]}
            r["judge_evidence"] = "JUDGE SAYS SECRET"
            for part in r["parts"].values():
                part["detail"] = "JUDGE DETAIL"
        c[3] = facts
        for kind in FB.MESSAGES:
            self.assertNotIn("JUDGE", msg(c, kind))


class TestPortBadInput(unittest.TestCase):
    def test_bad_inputs(self):
        d, tool, args, facts, viol, st, view, _ = cancel(v4={CONFIRMED: {"b": False}})
        call = lambda **kw: FB.build_message(**dict(dict(domain=d, tool=tool, args=args, violated_rules=viol,   # noqa
                                                         facts=facts, state=st, view=view, rule_table=TABLE[d],
                                                         rule_set=RULE_SET[d]), **kw))
        bad = dict(facts)
        del bad[CONFIRMED]
        with self.assertRaisesRegex(FB.MessageInputError, CONFIRMED):
            call(facts=bad)
        with self.assertRaisesRegex(FB.MessageInputError, "not in the rule table"):
            call(violated_rules=["999"])
        with self.assertRaises(FB.MessageInputError):
            call(view=None)
        with self.assertRaises(FB.MessageInputError):
            call(missing=["x"])
        with self.assertRaises(FB.MessageInputError):
            FB.build("frozen", d, tool, args, viol, facts, st, view, TABLE[d], RULE_SET[d])

    def test_guard_missing_argument(self):
        c = cancel(v4={CONFIRMED: {"b": False}})
        d, tool, args, facts, viol, st, view, _ = c
        rec = {"line": "order id", "expected": ORDER}
        text = FB.build_message(d, tool, args, viol, facts, st, view, TABLE[d], RULE_SET[d],
                                missing={CONFIRMED: [rec]})
        self.assertIn(f"Not stated in your listing: the order id {ORDER}.", text)


class TestPortSimpleAndPure(unittest.TestCase):
    def test_simple(self):
        c = gift_card_payment()
        simple = msg(c, "simple")
        self.assertNotIn("are violated as things stand", simple)
        d, tool, args, facts, viol, st, view, _ = c
        self.assertEqual(simple, FB3.build("simple", d, tool, args, viol, facts, st, view, TABLE[d], RULE_SET[d]))

    def test_inputs_unchanged_and_same_twice(self):
        rec = {"line": "order id", "expected": ORDER}
        for c in (cancel(v4={LISTED: {"b": (False, miss(rec))}, CONFIRMED: {"b": False}}), gift_card_payment(),
                  offer_reply(), air_cancel(ares(lambda r: r["cabin"] == "business"))):
            d, tool, args, facts, viol, st, view, _ = c
            before = (copy.deepcopy(args), json.dumps(facts, sort_keys=True, default=str), copy.deepcopy(st.db))
            for kind in FB.MESSAGES:
                msg(c, kind)
            self.assertEqual(before[0], args)
            self.assertEqual(before[1], json.dumps(facts, sort_keys=True, default=str))
            self.assertTrue(before[2] == st.db)
            self.assertEqual(msg(c), msg(c))


# ================================================================================================ the message check
class TestMessageCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        use_fixture()
        from scoring import v4_message_check as M
        cls.M = M
        cls.ck = M.Checker()

    def run_checks(self, c):
        M = self.M
        d, tool, args, facts, viol, st, view, hist = c
        p = plan(c)
        text = FB.render(p)
        db = M.OwnDB(d, hist).at(hist)
        fails = self.ck.check_values(d, tool, args, [str(v) for v in viol], facts, text, hist, db)
        me = M.own_me(d, hist, db)
        scan = self.ck.scan[d]
        leaks = M.missing_leaks(p, text, me, scan, M.user_texts(hist), M.arg_strings(args),
                                M.touched_records(d, hist, db, scan, args), FB)
        return p, text, fails, leaks

    def test_v4_lines_parse_and_pass(self):
        card = olivia_card()
        pm = DB["retail"]["users"][OLIVIA]["payment_methods"][card]
        cases = [
            cancel(v4={LISTED: {"b": (False, miss({"line": "order id", "expected": ORDER}))},
                       CONFIRMED: {"b": False}}),
            pay_change(card, v4={LISTED: {"b": (False, miss({"line": "new payment method",
                                                             "expected": f"{card} (Visa, last four "
                                                                         f"{pm['last_four']})"}))}}),
            pay_change(card, v4={CONFIRMED: {"c": (False, [{"clash": "payment", "named": ["paypal_8049766"],
                                                           "call": [card]}])}}),
            cancel(login=False, v4={LISTED: {"b": (False, miss({"line": "order id", "expected": ORDER}))}}),
        ]
        for c in cases:
            p, text, fails, leaks = self.run_checks(c)
            self.assertEqual(fails, [], text)
            self.assertEqual(leaks, [], text)
            self.assertEqual(self.M.fixable_line_problems(p, FB), [], text)

    def test_transfer_line_parses_and_quote_is_checked(self):
        r = ares(lambda r: True)
        steps = [("user", f"Hi, I am {r['user_id']}. Please cancel reservation {r['reservation_id']}.")]
        c = case("airline", steps, "transfer_to_human_agents", {"summary": "x"},
                 v4={"request_cannot_be_handled_with_available_tools": {"a": False, "b": False, "c": False}})
        p, text, fails, leaks = self.run_checks(c)
        self.assertIn("can be done with cancel_reservation.", text)
        self.assertEqual(fails, [], text)
        self.assertEqual(self.M.fixable_line_problems(p, FB), [], text)
        users = [m["content"] for m in c[7] if m.get("role") == "user"]
        bad = "Do not transfer yet: the user's request (\"words the user never said\") can be done with " \
              "cancel_reservation. Do it, or deny it if the policy forbids it."
        self.assertIn("quote is not a user message", self.ck.check_v4_advice(bad, "airline", {}, users))
        bad = bad.replace("(\"words the user never said\")", "(\"Hi\")").replace("cancel_reservation", "fly_me")
        self.assertIn("not a tool of the domain", self.ck.check_v4_advice(bad, "airline", {}, users))

    def test_value_check_catches_a_wrong_value(self):
        c = cancel(v4={LISTED: {"b": (False, miss({"line": "order id", "expected": "#W0000001"}))}})
        _, text, fails, _ = self.run_checks(c)
        self.assertTrue(any("missing line value not of the call" in f for f in fails), fails)

    def test_p109_generic_line_fails(self):
        p = {"advice": [{"type": "step", "fact": "x", "who": "agent", "text": "Do this step first, ..."}],
             "not_met": [{"fact": "x", "evidence": []}]}
        self.assertEqual(self.M.fixable_line_problems(p, FB), ["generic step line: x"])
        p = {"advice": [{"type": "listing", "fact": "x", "who": "agent", "text": "List ..."}],
             "not_met": [{"fact": "x", "evidence": []}]}
        self.assertEqual(self.M.fixable_line_problems(p, FB), ["listing line without a missing line: x"])

    def test_p1010_catches_a_leak(self):
        c = cancel(v4={LISTED: {"b": (False, miss({"line": "order id", "expected": ORDER}))}})
        p, text, _, _ = self.run_checks(c)
        theirs = other_order(MIA)
        zipc = DB["retail"]["orders"][theirs]["address"]["zip"]
        bad = copy.deepcopy(p)                                  # a builder bug: another user's value shown
        line = f"Not stated in your listing: the zip {zipc}."
        bad["not_met"][0]["evidence"].append({"type": "missing", "value": zipc, "text": line})
        M = self.M
        d, tool, args, facts, viol, st, view, hist = c
        db = M.OwnDB(d, hist).at(hist)
        scan = self.ck.scan[d]
        leaks = M.missing_leaks(bad, text + "\n" + line, M.own_me(d, hist, db), scan, M.user_texts(hist),
                                M.arg_strings(args), M.touched_records(d, hist, db, scan, args), FB)
        users = scan.owners.get(zipc, set())
        if OLIVIA not in users and 0 < len(users) <= M.RAW_MAX_USERS:
            self.assertTrue(any(x["why"] == "another user's value" for x in leaks), leaks)
        leaks = M.missing_leaks(bad, text + "\n" + line, None, scan, [], set(), {}, FB)
        self.assertTrue(any(x["why"] == "value before login" for x in leaks))


if __name__ == "__main__":
    unittest.main()
