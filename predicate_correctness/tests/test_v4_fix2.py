"""Tracker v4, fix round 2 (docs/planning/tracker_v4/fix_round2_plan.md): the K3 reminder facts and the K13 window.

1. K3: fix round 1 gave K3 a second choice input (verb, filled by code from items_action). The K3 facts still called
   v3's ask_first_yes, which does not know `follows` and raised ValueError on every ask (76 fact errors on the 200
   dev conversations, 64 extra blocks). The facts now call ask_first_yes_v4 (overlay facts_F2_retail.json). These
   tests run the REAL merged facts (state_tracker/v4/facts_v4_retail.json) and the REAL questions file with a fake
   backend: no LLM call, no network.
2. No v4 fact may call a v3 ask helper on a question that has a `follows` input (the bug class, checked on all
   facts).
3. K13 v5: each user message is asked with the agent's text message just before it (helpers_v4
   .user_messages_with_agent_before_v4); the agent message is context only.

Run from predicate_correctness/:
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v4_fix2 -v
"""
from __future__ import annotations

import json
import os
import re
import sys
import unittest

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from state_tracker.v3 import facts_format_v3 as F                 # noqa: E402
from state_tracker.v3 import message_view as MV                   # noqa: E402,F401  (registers v3 helpers)
from state_tracker.v3 import code_helpers as CH                   # noqa: E402,F401
from state_tracker.v3 import info_classes as IC                   # noqa: E402,F401
from state_tracker.v4 import questions_v4 as Q4                   # noqa: E402
from state_tracker.v4 import helpers_v4 as H4                     # noqa: E402
from state_tracker.v4 import helpers_go_ahead_v4 as GA            # noqa: E402,F401
from state_tracker.v4 import listing_v4 as LV                     # noqa: E402,F401
from tests.test_v3_message_view import Ctx, build                 # noqa: E402

V4_DIR = os.path.join(PC_DIR, "state_tracker", "v4")
PENDING_ORDER = "#W5918442"      # v1 retail database: pending, Perfume 1725100896 + Skateboard 5312063289
DELIVERED_ORDER = "#W4817420"    # v1 retail database: delivered, Water Bottle 6777246137 + Bookshelf 4900661478
K3_FACTS = {"modify_pending_order_items": ("agent_reminded_user_to_include_all_items_for_modification", "modified",
                                           "modify", PENDING_ORDER, "1725100896"),
            "exchange_delivered_order_items": ("agent_reminded_user_to_include_all_items_for_exchange", "exchanged",
                                               "exchange", DELIVERED_ORDER, "6777246137")}
V3_ASK = re.compile(r"(?<![\w.])(ask_first_yes|ask)\(\s*['\"](K[1-9][0-9]*)['\"]")


def _facts(domain):
    with open(os.path.join(V4_DIR, f"facts_v4_{domain}.json"), encoding="utf-8") as f:
        return json.load(f)["facts"]


class Recorder:
    """A fake answer policy that records every (qid, inputs) it is asked."""

    def __init__(self, word="yes"):
        self.word, self.seen = word, []

    def __call__(self, qid, inputs, norm):
        self.seen.append((qid, dict(inputs)))
        return self.word


def _evaluate(domain, fact, steps, tool, args, word="yes", second=None):
    hist, st, view = build(domain, steps, {"tool": tool, "args": args})
    rec = Recorder(word)
    doc = Q4.load_questions_v4()
    hook = Q4.QuestionsV4(Q4.FakeBackendV4(rec, second=second, doc=doc), doc=doc)
    r = F.evaluate(_facts(domain)[fact], st, args, view, hook, name=fact)
    return r, rec, view


class TestK3UsesTheV4Helper(unittest.TestCase):
    def steps(self, oid, verb):
        return [("user", f"Hi, I want to {verb} the item in order {oid}."),
                ("agent", f"Sure. Is this the only item you'd like to {verb} in order {oid}? This can be done only once."),
                ("user", "Yes, that's the only one.")]

    def args(self, tool, oid, item):
        a = {"order_id": oid, "item_ids": [item], "new_item_ids": [item], "payment_method_id": "paypal_1"}
        return a

    def test_the_facts_call_ask_first_yes_v4(self):
        facts = _facts("retail")
        for tool, (fact, items, _, _, _) in K3_FACTS.items():
            expr = facts[fact]["parts"]["b"]["expr"]
            self.assertEqual(expr, f"ask_first_yes_v4('K3', reminder_candidates(args['order_id']), items='{items}')")

    def test_yes_sets_the_fact_with_both_choice_inputs(self):
        for tool, (fact, items, verb, oid, item) in K3_FACTS.items():
            r, rec, _ = _evaluate("retail", fact, self.steps(oid, verb), tool, self.args(tool, oid, item))
            self.assertIs(r["value"], True, (fact, r))
            self.assertEqual(r["problems"], [], fact)
            self.assertEqual([q for q, _ in rec.seen], ["K3"], fact)
            self.assertEqual((rec.seen[0][1]["items_action"], rec.seen[0][1]["verb"]), (items, verb), fact)

    def test_no_is_a_real_no(self):
        for tool, (fact, items, verb, oid, item) in K3_FACTS.items():
            r, rec, _ = _evaluate("retail", fact, self.steps(oid, verb), tool, self.args(tool, oid, item), word="no")
            self.assertIs(r["value"], False, fact)
            self.assertEqual(r["problems"], [], fact)            # a real "no", not an error
            self.assertEqual(len(rec.seen), 1, fact)

    def test_unclear_is_asked_again_then_blocks(self):
        for tool, (fact, items, verb, oid, item) in K3_FACTS.items():
            r, rec, _ = _evaluate("retail", fact, self.steps(oid, verb), tool, self.args(tool, oid, item),
                                  word="unclear")
            self.assertIs(r["value"], False, fact)                # K3 on_unclear: block (the blocking value)
            self.assertEqual(len(rec.seen), 2, fact)              # wording 1, then K3b (D10)
            self.assertEqual([p["kind"] for p in r["problems"]], ["unclear"], fact)

    def test_no_candidate_is_false_without_a_call(self):
        for tool, (fact, items, verb, oid, item) in K3_FACTS.items():
            steps = [("user", f"Please {verb} the item in order {oid}.")]       # no agent message after the id
            r, rec, _ = _evaluate("retail", fact, steps, tool, self.args(tool, oid, item))
            self.assertIs(r["value"], False, fact)
            self.assertEqual(rec.seen, [], fact)

    def test_v3_helper_still_fails_on_the_v4_question(self):
        """The root cause, pinned: v3's helper cannot fill a `follows` input (so it must not be used for K3 v3)."""
        hist, st, view = build("retail", self.steps(PENDING_ORDER, "modify"),
                               {"tool": "modify_pending_order_items",
                                "args": self.args("modify_pending_order_items", PENDING_ORDER, "1725100896")})
        e = {"blocking_value": False, "combine": "a",
             "parts": {"a": {"source": "question", "question": "K3",
                             "expr": "ask_first_yes('K3', reminder_candidates(args['order_id']), items='modified')"}}}
        doc = Q4.load_questions_v4()
        hook = Q4.QuestionsV4(Q4.FakeBackendV4("yes", doc=doc), doc=doc)
        with self.assertRaises(ValueError):
            F.evaluate(e, st, view.pending_args, view, hook, name="probe")


class TestNoV3AskOnFollowsQuestions(unittest.TestCase):
    def test_every_fact(self):
        q = Q4.load_questions_v4()["questions"]
        bad = []
        for d in ("retail", "airline"):
            for fact, e in _facts(d).items():
                for pid, p in e["parts"].items():
                    for helper, qid in V3_ASK.findall(p.get("expr") or ""):
                        if any(i.get("follows") for i in q[qid]["inputs"]):
                            bad.append((d, fact, pid, helper, qid))
        self.assertEqual(bad, [])


class TestK13Window(unittest.TestCase):
    STEPS = [("user", "Hi, I need help with my trip."),
             ("agent", "Sure, what is your user id?"),
             ("user", "It is ana_1."),
             ("agent", "Basic economy flights cannot be changed, so I cannot move this flight."),
             ("user", "I still need it moved. Can someone else look at it?")]

    def test_pairs_newest_first(self):
        hist, st, view = build("airline", self.STEPS, {"tool": "transfer_to_human_agents", "args": {"summary": "x"}})
        c = Ctx(st, view)
        self.assertEqual(MV.user_messages(c), [4, 2, 0])
        self.assertEqual(H4.user_messages_with_agent_before_v4(c), [[4, 3], [2, 1], 0])

    def test_newest_agent_text_between_the_user_messages(self):
        steps = [("user", "Cancel my order #W5918442 please."), ("agent", "Let me check."), ("agent", "It is pending."),
                 ("user", "ok"), ("user", "And change the email on my account.")]
        hist, st, view = build("retail", steps, {"tool": "transfer_to_human_agents", "args": {"summary": "x"}})
        self.assertEqual(H4.user_messages_with_agent_before_v4(Ctx(st, view)), [4, [3, 2], 0])

    def test_registered(self):
        self.assertIn("user_messages_with_agent_before_v4", F.registered_names())

    def test_k13_gets_message_b_as_context(self):
        args = {"summary": "user wants a flight change on a basic economy booking"}
        r, rec, view = _evaluate("airline", "request_cannot_be_handled_with_available_tools", self.STEPS,
                                 "transfer_to_human_agents", args, word="no")
        k13 = [inp for q, inp in rec.seen if q == "K13"]
        self.assertEqual([x["message"] for x in k13], [view.text(4), view.text(2), view.text(0)])
        self.assertEqual([x.get("agent_before") for x in k13], [view.text(3), view.text(1), None])
        self.assertTrue(all("tools" in x for x in k13))

    def test_k13_yes_quotes_the_user_message(self):
        args = {"summary": "x"}
        r, rec, view = _evaluate("airline", "request_cannot_be_handled_with_available_tools", self.STEPS,
                                 "transfer_to_human_agents", args, word="yes")
        self.assertIs(r["value"], True)
        self.assertEqual(len([q for q, _ in rec.seen if q == "K13"]), 1)       # first yes wins (newest)

    def test_question_file(self):
        q = Q4.load_questions_v4()["questions"]["K13"]
        self.assertEqual(q["version"], 5)
        self.assertEqual(q["second"]["version"], 2)
        spec = q["inputs"][-1]
        self.assertEqual((spec["name"], spec["type"], spec["who"], spec["optional"]),
                         ("agent_before", "message", "agent", True))
        self.assertEqual(q["quote_from"], ["message"])
        self.assertIn("this exception never covers the refused list", q["question"])
        with open(os.path.join(PC_DIR, "output", "eval_v4", "overlays", "questions_A4.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["questions"]["K13"], q)               # overlay and merged file in sync


if __name__ == "__main__":
    unittest.main()
