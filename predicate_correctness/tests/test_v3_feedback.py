"""Tracker v3, part 10: the block messages built from the rule (guard/feedback_v3.py).

Tiny conversations are built with τ-bench's own tool outputs (tests/test_v3_message_view.py build), the facts are set
by the v3 evaluator with fake tiny-question answers (state_tracker/v3/questions.py FakeBackend, no LLM call), and the
violated rules come from the rule table. Covered (docs/planning/tracker_v3/p10.md, step 2): each `who` x closing case;
a rule with several ways (airline rule 25); a user_only way (airline rule 33); a strict no; the safety rules; negated
facts; "not established"; bad input raises a clear error (the caller then sends TGR's own message); the simple
version; the builder changes none of its inputs.

Run from predicate_correctness/:  python3 -B -m unittest tests.test_v3_feedback -v
"""
from __future__ import annotations

import copy
import json
import sys
import unittest

sys.dont_write_bytecode = True

from guard import feedback_v3 as FB                                     # noqa: E402
from method_tgr import feedback as TGR_FB                               # noqa: E402  (runner copy, via FB)
from state_tracker import paths                                          # noqa: E402
from state_tracker import state as S                                     # noqa: E402
from state_tracker.v3 import facts_format_v3 as F                       # noqa: E402
from state_tracker.v3 import questions as Q                             # noqa: E402
from tests.test_v3_message_view import MIA, OLIVIA, OLIVIA_EMAIL, ORDER, build   # noqa: E402

TABLE = {d: json.load(open(F.rule_table_path(d), encoding="utf-8")) for d in paths.DOMAINS}
RULE_SET = {d: json.load(open(paths.rule_set_path(d), encoding="utf-8")) for d in paths.DOMAINS}
DEFS = {d: F.load_facts(d)["facts"] for d in paths.DOMAINS}
DB = {d: S.load_db(d) for d in paths.DOMAINS}
LOGIN = [("user", "Hi, my email is " + OLIVIA_EMAIL), ("call", "find_user_id_by_email", {"email": OLIVIA_EMAIL})]


def answers(table=None, default="no"):
    """A fake answers hook: table {question id: "yes" | "no"}; the rest get `default`."""
    table = table or {}
    return Q.Questions(Q.FakeBackend(lambda qid, inputs, norm: table.get(qid, default)))


def case(domain, steps, tool, args, hook=None):
    """(facts, violated rule ids, state, view) of one pending call."""
    _, st, view = build(domain, steps, {"tool": tool, "args": args})
    hook = hook or answers()
    names = sorted({f for r in TABLE[domain]["rules"] if tool in r["actions"] for f in r["facts"]})
    facts = {n: F.evaluate(DEFS[domain][n], st, args, view=view, answers=hook, name=n) for n in names}
    violated = []
    for r in TABLE[domain]["rules"]:
        if tool not in r["actions"]:
            continue
        vals = {f: facts[f]["value"] for f in r["facts"]}
        row = next(x for x in r["rows"] if x["action"] == tool and x["values"] == vals)
        if not row["holds"]:
            violated.append(r["id"])
    return facts, violated, st, view


def msg(domain, tool, args, facts, violated, st, view, kind="rule"):
    return FB.build(kind, domain, tool, args, violated, facts, st, view, TABLE[domain], RULE_SET[domain])


def plan(domain, tool, args, facts, violated, st, view):
    return FB.explain(domain, tool, args, violated, facts, st, view, TABLE[domain], RULE_SET[domain])


def kinds(p):
    return [a["type"] for a in FB.advice_lines(p["advice"])]


def strings(x, out):
    """Every string value of a record (field names are not values; payment method keys are ids, so they count)."""
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


# ================================================================================================ cases
def retail_cancel(extra=(), hook=None, reason="no longer needed"):
    steps = LOGIN + [("user", f"Please cancel order {ORDER}, I no longer need it.")] + list(extra)
    args = {"order_id": ORDER, "reason": reason}
    return ("retail", "cancel_pending_order", args) + case("retail", steps, "cancel_pending_order", args, hook)


def gift_card_payment():
    steps = LOGIN + [("call", "get_order_details", {"order_id": ORDER}), ("user", "Pay it with my gift card.")]
    args = {"order_id": ORDER, "payment_method_id": "gift_card_7794233"}
    return ("retail", "modify_pending_order_payment", args) + case("retail", steps, "modify_pending_order_payment",
                                                                   args)


def air_cancel(r, look=False, words="change of plans", hook=None):
    uid, rid = r["user_id"], r["reservation_id"]
    steps = [("user", f"Hi, I am {uid}. Please cancel reservation {rid}: {words}.")]
    if look:
        steps.append(("call", "get_reservation_details", {"reservation_id": rid}))
    args = {"reservation_id": rid}
    return ("airline", "cancel_reservation", args) + case("airline", steps, "cancel_reservation", args,
                                                          hook or answers({"K7": "yes"}))


def offer_reply(complaint="yes", request="no"):
    r = ares(lambda r: True)
    steps = [("user", f"Hi, I am {r['user_id']}. My flight was cancelled and I am very upset.")]
    args = {"content": "I am sorry. As a gesture I can offer you a $100 certificate."}
    hook = answers({"K8": complaint, "K9": complaint, "K10": request, "K12": "yes"})
    return ("airline", "respond", args) + case("airline", steps, "respond", args, hook)


# ================================================================================================ tests
class TestFirstLineAndPolicy(unittest.TestCase):
    def test_first_line_is_tgr_own(self):
        c = retail_cancel()
        text = msg(*c)
        want = TGR_FB.actionable("tool_call", "cancel_pending_order", [], None, {}, {}, {}).split("\n")[0]
        self.assertEqual(text.split("\n")[0], want)
        self.assertTrue(want.startswith("BLOCKED by policy guardrail. The cancel_pending_order call was NOT executed"))
        c = offer_reply()
        want = TGR_FB.actionable("respond", "respond", [], None, {}, {}, {}).split("\n")[0]
        self.assertEqual(msg(*c).split("\n")[0], want)

    def test_policy_quotes_the_cited_sentences(self):
        d, tool, args, facts, viol, st, view = retail_cancel()
        text = msg(d, tool, args, facts, viol, st, view)
        rules = {r["id"]: r for r in RULE_SET[d]["rules"]}
        sents = {s["id"]: s["text"] for s in RULE_SET[d]["sentences"]}
        want = []
        for rid in viol:
            for sid in rules[rid]["sentences"]:
                if sents[sid] not in want:
                    want.append(sents[sid])
        policy = next(x for x in text.split("\n") if x.startswith("Policy: "))
        self.assertEqual(policy, "Policy: " + " ".join(f"\"{s}\"" for s in want))

    def test_never_the_predicate_descriptions(self):
        for c in (retail_cancel(), gift_card_payment(), air_cancel(ares(lambda r: r["cabin"] == "business")),
                  offer_reply()):
            text = msg(*c)
            for p in RULE_SET[c[0]]["predicates"].values():
                self.assertNotIn(p["description"], text)
            self.assertNotIn("earlier tool output", text.lower())


class TestWhoAndClosing(unittest.TestCase):
    def test_agent_login_then_call_again(self):
        args = {"order_id": ORDER}
        facts, viol, st, view = case("retail", [("user", f"What is in order {ORDER}?")], "get_order_details", args)
        p = plan("retail", "get_order_details", args, facts, viol, st, view)
        self.assertEqual(kinds(p), ["user_args_call"])
        step = FB.advice_lines(p["advice"])[0]
        self.assertEqual(step["arg_names"], {"find_user_id_by_email": ["email"],
                                             "find_user_id_by_name_zip": ["first_name", "last_name", "zip"]})
        self.assertFalse(p["forbid"])
        self.assertEqual(p["closing"], "When this is done, call get_order_details again.")
        self.assertEqual(p["advice_class"], "agent")

    def test_agent_lookup_ask_and_step_then_call_again(self):
        p = plan(*retail_cancel())
        ks = kinds(p)
        self.assertIn("lookup", ks)
        self.assertIn("ask", ks)
        self.assertIn("step", ks)                     # list the details (consequential_action_details_listed)
        look = next(a for a in FB.advice_lines(p["advice"]) if a["type"] == "lookup")
        self.assertEqual((look["tool"], look["args"]), ("get_order_details", {"order_id": ORDER}))
        self.assertFalse(p["forbid"])
        self.assertEqual(p["closing"], "When this is done, call cancel_pending_order again.")
        self.assertEqual(p["advice_class"], "agent+ask")

    def test_ask_only_then_call_again(self):
        listing = ("agent", f"I will cancel order {ORDER} (reason: no longer needed). Shall I go ahead?")
        p = plan(*retail_cancel([("call", "get_order_details", {"order_id": ORDER}), listing,
                                 ("user", "Hmm, let me think about it.")], hook=answers({"K2": "yes"})))
        self.assertEqual(set(kinds(p)), {"ask"})
        self.assertFalse(p["forbid"])
        self.assertTrue(p["closing"].startswith("When this is done"))

    def test_none_then_do_not_repeat(self):
        d, tool, args, facts, viol, st, view = gift_card_payment()
        p = plan(d, tool, args, facts, viol, st, view)
        self.assertIn("52", viol)
        rule52 = next(r for r in p["rules"] if r["rule_id"] == "52")
        self.assertFalse(rule52["fixable"])
        self.assertTrue(p["forbid"])
        self.assertEqual(p["closing"], "Do not repeat the same call as it stands.")
        text = msg(d, tool, args, facts, viol, st, view)
        self.assertIn("Not possible with these arguments: gift card balance covers order total is false.", text)
        self.assertIn("payment_methods.gift_card_7794233.balance = 56", text)       # the value that fails
        self.assertIn("payment_history[0].amount = 663.85", text)

    def test_user_only_never_a_step(self):
        r = ares(lambda r: True)
        args = {"user_id": r["user_id"], "amount": 100}
        facts, viol, st, view = case("airline", [("user", f"Hi, I am {r['user_id']}. I want to change my flight.")],
                                     "send_certificate", args)
        p = plan("airline", "send_certificate", args, facts, viol, st, view)
        self.assertTrue(set(kinds(p)) <= {"user_only"}, kinds(p))
        self.assertTrue(p["forbid"])
        text = msg("airline", "send_certificate", args, facts, viol, st, view)
        self.assertIn("Do not lead the user to say it.", text)
        self.assertNotIn("Ask the user", text)
        self.assertNotIn("Do this step first", text)
        self.assertTrue(text.endswith("Do not repeat the same call as it stands."))

    def test_negated_agent_fact_reply(self):
        p = plan(*offer_reply())
        self.assertIn("change", kinds(p))
        self.assertEqual(p["closing"], "When this is done, send your message again.")
        text = msg(*offer_reply())
        self.assertIn("- pending response offers any compensation certificate: true", text)
        self.assertIn("Change your message so that this is no longer true", text)

    def test_strict_no(self):
        listing = ("agent", f"I will cancel order {ORDER} because it is no longer needed. Confirm?")
        c = retail_cancel([("call", "get_order_details", {"order_id": ORDER}), listing, ("user", "No, wait.")],
                          hook=answers(default="yes"))
        p = plan(*c)
        self.assertIsNotNone(p["strict_no"])
        self.assertIn("ask_no", kinds(p))
        self.assertNotIn("ask", kinds(p))
        self.assertTrue(p["forbid"])
        text = msg(*c)
        self.assertIn("The user said no (\"No, wait.\")", text)
        self.assertTrue(text.endswith("Do not repeat the same call as it stands."))

    def test_one_rule_fixable_one_not(self):
        c = retail_cancel([("call", "get_order_details", {"order_id": ORDER})], reason="other")
        p = plan(*c)
        fix = {r["rule_id"]: r["fixable"] for r in p["rules"]}
        self.assertFalse(fix["45"])                   # the reason argument: none
        self.assertTrue(any(fix.values()))
        self.assertTrue(p["forbid"])
        self.assertIn("the call's reason = \"other\"", msg(*c))


class TestSeveralWays(unittest.TestCase):
    """Airline rule 25: four ways (within 24 hours; airline cancelled; business; economy + insurance + reason)."""

    def test_business_not_looked_up(self):
        r = ares(lambda r: r["created_at"] < OLD and r["cabin"] == "business" and set(statuses(r)) == {"available"})
        c = air_cancel(r)
        p = plan(*c)
        r25 = next(x for x in p["rules"] if x["rule_id"] == "25")
        self.assertEqual(len(r25["ways"]), 4)
        self.assertEqual([w["status"] for w in r25["named"]], ["not_possible", "not_possible", "fixable"])
        self.assertEqual([w["status"] for w in r25["ways"] if w not in r25["named"]], ["excluded"])
        text = msg(*c)
        self.assertIn(FB.ANY_ONE, text)
        self.assertIn(f"c) Do this step first: look it up with get_reservation_details (reservation_id "
                      f"\"{r['reservation_id']}\")", text)
        self.assertNotIn("insured", text)             # the user_only way is never named
        self.assertFalse(p["forbid"])

    def test_insured_way_named_when_the_reason_is_given(self):
        r = ares(lambda r: r["created_at"] < OLD and r["cabin"] == "economy" and r["insurance"] == "yes"
                 and set(statuses(r)) == {"available"})
        c = air_cancel(r, words="I broke my leg and cannot fly", hook=answers({"K6": "yes", "K7": "yes"}))
        p = plan(*c)
        r25 = next(x for x in p["rules"] if x["rule_id"] == "25")
        way4 = [w for w in r25["ways"] if "reservation_has_travel_insurance" in w["facts"]]
        self.assertEqual(len(way4), 1)
        self.assertEqual(way4[0]["status"], "fixable")
        self.assertNotIn("insured_cancellation_condition_met", way4[0]["facts"])   # already true
        self.assertFalse(p["forbid"])

    def test_no_way_left(self):
        r = ares(lambda r: r["created_at"] < OLD and r["cabin"] == "economy" and r["insurance"] == "no"
                 and set(statuses(r)) == {"available"})
        c = air_cancel(r, look=True)
        p = plan(*c)
        self.assertTrue(p["forbid"])
        text = msg(*c)
        self.assertIn(f"reservation {r['reservation_id']}: created_at = \"{r['created_at']}\"", text)
        self.assertIn("cabin = \"economy\"", text)
        self.assertNotIn("insured", text)
        self.assertNotIn("health", text)
        self.assertTrue(text.endswith("Do not repeat the same call as it stands."))


class TestUserOnlyWay(unittest.TestCase):
    """Airline rule 33: the reply offers compensation AND NOT (complaint AND request)."""

    def test_request_way_excluded(self):
        for complaint in ("yes", "no"):
            c = offer_reply(complaint=complaint, request="no")
            p = plan(*c)
            r33 = next(x for x in p["rules"] if x["rule_id"] == "33")
            self.assertTrue(any(w["status"] == "excluded" for w in r33["ways"]))
            self.assertEqual([w["facts"] for w in r33["named"]], [["pending_response_offers_any_compensation_certificate"]])
            text = msg(*c)
            self.assertNotIn("requested compensation", text)
            self.assertNotIn("complained", text)
            for a in FB.advice_lines(p["advice"]):
                self.assertNotEqual(a["who"], "user_only")


class TestNegatedAndUnknown(unittest.TestCase):
    def test_negated_fact_shows_true(self):
        text = msg(*gift_card_payment())
        self.assertIn("- payment method is gift card: true", text)
        self.assertIn("Not possible with these arguments: payment method is gift card is true.", text)

    def test_stand_in_unknown_value_none(self):
        d, tool, args, facts, viol, st, view = retail_cancel([("call", "get_order_details", {"order_id": ORDER})])
        f = "user_explicitly_confirmed_pending_action"
        facts = dict(facts)
        facts[f] = {"value": None}                   # p9's stand-in unknown, without parts
        text = msg(d, tool, args, facts, viol, st, view)
        self.assertIn(f"- {FB.words(f)}: not established", text)
        p = plan(d, tool, args, facts, viol, st, view)
        self.assertEqual(p["facts"][f]["status"], "fixable")

    def test_stand_in_unknown_evaluator_form(self):
        steps = LOGIN + [("user", f"Please cancel order {ORDER}.")]
        args = {"order_id": ORDER, "reason": "no longer needed"}
        f = "user_explicitly_confirmed_pending_action"
        facts, viol, st, view = case("retail", steps, "cancel_pending_order", args, Q.StandInAnswers({f: None}))
        self.assertTrue(any(x["kind"] == "unclear" for x in facts[f]["problems"]) or not facts[f]["problems"])
        text = msg("retail", "cancel_pending_order", args, facts, viol, st, view)
        if facts[f]["problems"]:
            self.assertIn(f"- {FB.words(f)}: not established", text)


class TestNotEstablishedForms(unittest.TestCase):
    """p9's guard gives a fact it did not establish in three more forms; each is shown as not established."""

    def setUp(self):
        self.c = list(retail_cancel([("call", "get_order_details", {"order_id": ORDER})]))
        self.f = "user_explicitly_confirmed_pending_action"

    def text_with(self, res):
        d, tool, args, facts, viol, st, view = self.c
        facts = dict(facts)
        facts[self.f] = res
        return msg(d, tool, args, facts, viol, st, view)

    def test_lazy_skip(self):
        res = dict(self.c[3][self.f], value=False, how="lazy_skip")
        res["parts"] = {p: (dict(v, value=None, how="lazy_skip") if v["source"] == "question" else v)
                        for p, v in res["parts"].items()}
        self.assertIn(f"- {FB.words(self.f)}: not established", self.text_with(res))

    def test_saved_unknown(self):
        res = dict(self.c[3][self.f], value=None, how="saved_unknown")
        self.assertIn(f"- {FB.words(self.f)}: not established", self.text_with(res))

    def test_state_error(self):
        res = F.blocking_result(DEFS["retail"][self.f], "replay_mismatch", "1 replayed output differs", name=self.f)
        self.assertIn(f"- {FB.words(self.f)}: not established", self.text_with(res))

    def test_missing_argument_keeps_its_value(self):
        args = {"order_id": ORDER}                    # no reason: the reason fact takes its blocking value
        steps = LOGIN + [("call", "get_order_details", {"order_id": ORDER}), ("user", "cancel it")]
        facts, viol, st, view = case("retail", steps, "cancel_pending_order", args)
        self.assertEqual(facts["cancellation_reason_is_allowed"]["problems"][0]["kind"], "missing_argument")
        text = msg("retail", "cancel_pending_order", args, facts, viol, st, view)
        self.assertIn("- cancellation reason is allowed: false", text)
        self.assertIn("Not possible with these arguments: cancellation reason is allowed is false.", text)


class TestSafety(unittest.TestCase):
    def test_before_login_no_database_value(self):
        args = {"order_id": ORDER, "payment_method_id": "gift_card_7794233"}
        facts, viol, st, view = case("retail", [("user", "Change the payment of my order to my gift card.")],
                                     "modify_pending_order_payment", args)
        p = plan("retail", "modify_pending_order_payment", args, facts, viol, st, view)
        self.assertFalse(p["safety"]["logged_in"])
        text = msg("retail", "modify_pending_order_payment", args, facts, viol, st, view)
        for line in text.split("\n"):
            self.assertNotRegex(line, r"^  - (user|order|product|variant|payment_method) ")
        rec = strings(DB["retail"]["orders"][ORDER], []) + strings(DB["retail"]["users"][OLIVIA], [])
        typed = {ORDER, "gift_card_7794233"}                      # the call's own arguments
        specific = [s for s in rec if len(s) >= 5 and s not in typed and (any(ch.isdigit() for ch in s) or "@" in s)]
        self.assertGreater(len(specific), 10)
        for s in specific:
            self.assertNotIn(s, text, s)
        u = DB["retail"]["users"][OLIVIA]
        for name in (u["name"]["first_name"], u["name"]["last_name"]):
            self.assertNotRegex(text, rf"\b{name}\b")
        self.assertNotIn("663.85", text)
        self.assertNotIn("56", text.replace("7794233", ""))

    def test_other_users_record_hidden(self):
        theirs = other_order(MIA)
        args = {"order_id": theirs}
        facts, viol, st, view = case("retail", LOGIN + [("user", f"Show me order {theirs}.")],
                                     "get_order_details", args)
        self.assertTrue(facts["request_is_for_another_user"]["value"])
        text = msg("retail", "get_order_details", args, facts, viol, st, view)
        self.assertNotIn(MIA, text)
        self.assertIn(FB.HIDDEN_OTHER, text)
        for s in strings(DB["retail"]["users"][MIA], []):
            if len(s) >= 5:
                self.assertNotIn(s, text, s)

    def test_airline_before_me_hidden(self):
        r = ares(lambda r: r["created_at"] < OLD and r["cabin"] == "economy" and set(statuses(r)) == {"available"})
        args = {"reservation_id": r["reservation_id"]}
        facts, viol, st, view = case("airline", [("user", f"Cancel reservation {r['reservation_id']}.")],
                                     "cancel_reservation", args)
        text = msg("airline", "cancel_reservation", args, facts, viol, st, view)
        self.assertIn(FB.HIDDEN_BEFORE_LOGIN, text)
        self.assertNotIn(r["created_at"], text)
        self.assertNotIn(r["user_id"], text)

    def test_no_judge_text(self):
        d, tool, args, facts, viol, st, view = retail_cancel()
        facts = copy.deepcopy(facts)
        for n, r in facts.items():
            r["evidence"] = {"text": "JUDGE SAYS SECRET", "notes": [{"note": "JUDGE NOTE"}]}
            r["judge_evidence"] = "JUDGE SAYS SECRET"
            for part in r["parts"].values():
                part["detail"] = "JUDGE DETAIL"
        for kind in FB.MESSAGES:
            text = msg(d, tool, args, facts, viol, st, view, kind)
            self.assertNotIn("JUDGE", text)


class TestBadInput(unittest.TestCase):
    def setUp(self):
        self.c = list(retail_cancel())

    def call(self, **kw):
        d, tool, args, facts, viol, st, view = self.c
        a = dict(domain=d, tool=tool, args=args, violated_rules=viol, facts=facts, state=st, view=view,
                 rule_table=TABLE[d], rule_set=RULE_SET[d])
        a.update(kw)
        return FB.build_message(**a)

    def test_missing_fact(self):
        facts = dict(self.c[3])
        del facts["order_status_checked_pending"]
        with self.assertRaisesRegex(FB.MessageInputError, "order_status_checked_pending"):
            self.call(facts=facts)

    def test_bad_value(self):
        facts = dict(self.c[3])
        facts["order_status_checked_pending"] = {"value": "no"}
        with self.assertRaises(FB.MessageInputError):
            self.call(facts=facts)
        facts["order_status_checked_pending"] = False
        with self.assertRaises(FB.MessageInputError):
            self.call(facts=facts)

    def test_rule_problems(self):
        with self.assertRaisesRegex(FB.MessageInputError, "not in the rule table"):
            self.call(violated_rules=["999"])
        with self.assertRaisesRegex(FB.MessageInputError, "not a rule of"):
            self.call(violated_rules=["1"])          # find_user_id_by_email's rule
        with self.assertRaisesRegex(FB.MessageInputError, "non-empty"):
            self.call(violated_rules=[])
        facts = copy.deepcopy(self.c[3])
        facts["order_status_checked_pending"]["value"] = True
        with self.assertRaisesRegex(FB.MessageInputError, "holds"):
            self.call(violated_rules=["44"], facts=facts)

    def test_other_inputs(self):
        with self.assertRaises(FB.MessageInputError):
            self.call(view=None)
        with self.assertRaises(FB.MessageInputError):
            self.call(state=None)
        with self.assertRaises(FB.MessageInputError):
            self.call(domain="bank")
        with self.assertRaises(FB.MessageInputError):
            FB.build("frozen", *self.c[:3], self.c[4], self.c[3], self.c[5], self.c[6], TABLE["retail"],
                     RULE_SET["retail"])

    def test_tgr_records_accepted(self):
        d, tool, args, facts, viol, st, view = self.c
        recs = [{"rule_id": r, "description": "x", "logic": "y"} for r in viol]
        self.assertEqual(self.call(violated_rules=recs), self.call())


class TestSimple(unittest.TestCase):
    def test_simple_is_tgr_without_the_closing_line(self):
        d, tool, args, facts, viol, st, view = gift_card_payment()
        simple = msg(d, tool, args, facts, viol, st, view, "simple")
        aspm = FB._aspm(RULE_SET[d])
        violated = [{"rule_id": r, "description": aspm.rules[r].description, "logic": aspm.rules[r].logic}
                    for r in viol]
        cur = {n: facts[n]["value"] for r in viol for n in aspm.rules[r].atoms - aspm.action_predicates}
        full = TGR_FB.actionable("tool_call", tool, violated, aspm, cur, {n: {"value": v, "evidence": ""}
                                                                           for n, v in cur.items()},
                                 RULE_SET[d]["predicates"])
        self.assertIn("are violated as things stand", full)
        self.assertNotIn("are violated as things stand", simple)
        self.assertNotIn("do not repeat", simple.lower())
        self.assertTrue(full.startswith(simple))
        self.assertEqual(simple.split("\n")[0], msg(d, tool, args, facts, viol, st, view).split("\n")[0])
        self.assertNotIn("(evidence:", simple)

    def test_simple_keeps_what_to_do_for_unknowns(self):
        d, tool, args, facts, viol, st, view = retail_cancel()
        facts = dict(facts)
        facts["user_explicitly_confirmed_pending_action"] = {"value": None}
        simple = msg(d, tool, args, facts, viol, st, view, "simple")
        self.assertIn("What to do:", simple)
        self.assertIn("Not established yet", simple)


class TestPure(unittest.TestCase):
    def test_inputs_unchanged(self):
        for c in (retail_cancel(), gift_card_payment(), offer_reply(),
                  air_cancel(ares(lambda r: r["cabin"] == "business"))):
            d, tool, args, facts, viol, st, view = c
            before = (copy.deepcopy(args), json.dumps(facts, sort_keys=True, default=str), copy.deepcopy(st.db),
                      list(viol), len(st.events))
            for kind in FB.MESSAGES:
                msg(d, tool, args, facts, viol, st, view, kind)
            after = (args, json.dumps(facts, sort_keys=True, default=str), st.db, list(viol), len(st.events))
            self.assertEqual(before[0], after[0])
            self.assertEqual(before[1], after[1])
            self.assertTrue(before[2] == after[2])
            self.assertEqual(before[3:], after[3:])

    def test_same_message_twice(self):
        c = air_cancel(ares(lambda r: r["cabin"] == "business"))
        self.assertEqual(msg(*c), msg(*c))


if __name__ == "__main__":
    unittest.main()
