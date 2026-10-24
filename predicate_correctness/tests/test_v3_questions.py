"""Tests for the tiny questions (tracker v3, part 8): state_tracker/v3/questions.py, questions_v3.json, the p8
overlays (output/eval_v3/p8_parts/exprs_<domain>.json) and the counting core of scoring/v3_p8_dryrun.py.

Pass marks P8.1 (every question renders; the quote check; unclear -> the blocking value; the two keys) and the code
side of P8.2 (the audit hook refuses every network socket; a fake run makes 0 network events). Also: the cache key and
"asked once", inputs never cut, the real mode's guards (approval words, budget, network) and its budget stop (with a
fake client: no network), the stand-in hook for p9, and the dry run's exact counts on built cases.

Fake answers only. No LLM call, no network: the network tests run in a separate Python process with the audit hook
installed. No file named questions_answers.jsonl or episodes*.jsonl is created (temporary folders only).

Run from predicate_correctness/:  python3 -B -m unittest tests.test_v3_questions -v
"""
from __future__ import annotations

import collections
import contextlib
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from state_tracker import lookup_format as L             # noqa: E402
from state_tracker import state as S                     # noqa: E402
from state_tracker import tau_copy                       # noqa: E402
from state_tracker.v3 import facts_format_v3 as F        # noqa: E402
from state_tracker.v3 import questions as Q              # noqa: E402
from scoring import v3_p8_dryrun as D                    # noqa: E402

OVERLAY = os.path.join(PC_DIR, "output", "eval_v3", "p8_parts", "exprs_{}.json")
DOMAINS = ("retail", "airline")
# The one question part with no code part ANDed to it (output/eval_v3/p5_parts/airline_b_notes.md, note 6: "K13 has
# no code key beyond the quote check").
UNKEYED = {("airline", "request_cannot_be_handled_with_available_tools", "a")}


# ----------------------------------------------------------------------------------------------- builders

class FakeView:
    """The two things the question helpers read from p7's view: text(ref) and the pending reply's ref."""

    def __init__(self, texts, pending_text=None):
        self.entries = [{"role": r, "text": t} for r, t in texts]
        self.pending_ref = len(self.entries)
        self.pending_text = pending_text

    def text(self, ref):
        if ref == self.pending_ref:
            return self.pending_text
        return self.entries[ref]["text"]


def _conv(domain, calls):
    db = S.load_db(domain)
    msgs = [{"role": "system", "content": tau_copy.policy_text(domain)}, {"role": "user", "content": "hi"}]
    for i, (name, args) in enumerate(calls):
        out = S.run_tool(domain, db, name, copy.deepcopy(args))
        msgs.append({"role": "assistant", "content": None, "tool_calls": [
            {"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "name": name, "content": out})
    return msgs


def part(source, expr, question=None, about=None, plain="a part"):
    return {"source": source, "plain": plain, "expr": expr, "question": question, "about": about}


def entry(parts, combine, blocking=False):
    srcs = sorted({p["source"] for p in parts.values()}, key=F.SOURCES.index)
    return {"sources": srcs, "parts": parts, "combine": combine, "start": False, "update": "u", "who": "agent",
            "evidence": "e", "policy": ["S1"], "rules": ["1"], "blocking_value": blocking, "missing": "m",
            "reading": None, "fixed": [], "reason": "r", "v2": "v"}


def load_overlay(domain):
    with open(OVERLAY.format(domain), encoding="utf-8") as f:
        return json.load(f)


def table_policy(table, default="no"):
    """A fake that answers by the first quote source's normalized text."""
    return Q.FakeBackend({(q, Q.normalize_text(t)): a for (q, t), a in table.items()}, default=default)


@contextlib.contextmanager
def network_flag(value):
    old = Q._NET["installed"]
    Q._NET["installed"] = value
    try:
        yield
    finally:
        Q._NET["installed"] = old


_STATES = {}


def built_state(domain):
    """One state per domain (an empty conversation on the real database copy), pending call set by the test."""
    if domain not in _STATES:
        _STATES[domain] = S.build_state(_conv(domain, []), None, domain=domain)
    return _STATES[domain]


def ev(e, domain="retail", args=None, view=None, answers=None, tool="respond", name="f"):
    st = built_state(domain)
    st.pending = {"tool": tool, "args": args or {}, "kind": "respond" if tool == "respond" else "tool_call"}
    return F.evaluate(e, st, args or {}, view=view, answers=answers, name=name)


# ----------------------------------------------------------------------------------------------- the file

class TestQuestionsFile(unittest.TestCase):

    def test_file_is_well_formed(self):
        with open(Q.QUESTIONS_PATH, encoding="utf-8") as f:
            doc = json.load(f)
        self.assertEqual(Q.check_doc(doc), [])
        self.assertEqual(Q.question_ids(), [f"K{i}" for i in range(1, 17)])
        self.assertEqual((doc["model"], doc["effort"]), ("gpt-6-luna", "low"))
        self.assertEqual(doc["answer_format"], {"answer": "yes|no|unclear", "quote": "..."})
        self.assertEqual(set(doc["schema"]["properties"]), {"answer", "quote"})
        self.assertEqual(doc["schema"]["properties"]["answer"]["enum"], ["yes", "no", "unclear"])
        self.assertEqual((doc["price"]["input_per_m"], doc["price"]["output_per_m"]), (0.1, 0.5))

    def test_every_question_renders(self):
        for qid in Q.question_ids():
            with self.subTest(qid=qid):
                q = Q.question(qid)
                inputs = Q.sample_inputs(qid)
                p = Q.render(qid, inputs)
                self.assertEqual(p["system"], Q.load_questions()["system"])
                self.assertIn(f"Question {qid} (version {q['version']})", p["user"])
                for s in q["inputs"]:
                    v = inputs[s["name"]]
                    if s["type"] == "choice":
                        self.assertIn(v, p["user"])
                    elif s["type"] == "messages":
                        for x in v:
                            self.assertIn(x, p["user"])
                    else:
                        self.assertIn(v, p["user"])
                        self.assertIn(s["label"], p["user"])
                self.assertNotIn("{", p["user"].split("Question: ")[1])     # every placeholder filled
                self.assertIn("Answer yes, no or unclear", p["user"])

    def test_inputs_are_never_cut(self):
        long = "word " * 12000 + "the very end"
        p = Q.render("K4", {"message": long})
        self.assertIn(long, p["user"])
        norm = Q.normalized_inputs("K4", {"message": long})
        self.assertTrue(norm["message"].endswith("the very end"))
        rec = Q.Questions(Q.FakeBackend("yes")).ask("K4", {"message": long})
        self.assertEqual(len(rec["input"]["message"]), len(Q.normalize_text(long)))

    def test_a_changed_text_needs_a_new_hash(self):
        doc = copy.deepcopy(Q.load_questions())
        doc["questions"]["K4"]["question"] += " (changed)"
        self.assertTrue(any("K4: text_sha256 differs" in p for p in Q.check_doc(doc)))
        doc = copy.deepcopy(Q.load_questions())
        doc["system"] += " changed"
        self.assertTrue(any("system_sha256" in p for p in Q.check_doc(doc)))
        doc = copy.deepcopy(Q.load_questions())
        doc["model"] = "gpt-5-nano"
        self.assertTrue(any("gpt-6-luna" in p for p in Q.check_doc(doc)))

    def test_bad_inputs_are_refused(self):
        with self.assertRaises(ValueError):
            Q.check_inputs("K4", {})                                      # required message missing
        with self.assertRaises(ValueError):
            Q.check_inputs("K4", {"message": "x", "other": "y"})          # unknown input
        with self.assertRaises(ValueError):
            Q.check_inputs("K3", {"message": "x", "items_action": "sold"})
        Q.check_inputs("K1", {"reply": "yes", "action": "cancel"})       # the listing is optional
        with self.assertRaises(KeyError):
            Q.question("K99")

    def test_question_parts_name_known_questions(self):
        doc = Q.load_questions()
        for d in DOMAINS:
            facts = F.load_facts(d)["facts"]
            for name, e in facts.items():
                for pid, p in e["parts"].items():
                    if p["source"] == "question":
                        with self.subTest(domain=d, fact=name, part=pid):
                            self.assertIn(p["question"], doc["questions"])
                            self.assertIn(name, doc["questions"][p["question"]]["facts"].get(d, []))
            for qid, q in doc["questions"].items():
                for name in q["facts"].get(d, []):
                    self.assertIn(name, facts, f"{qid} names an unknown {d} fact {name}")


# ----------------------------------------------------------------------------------------------- normalization, quotes

class TestNormalizeAndQuote(unittest.TestCase):

    def test_normalize(self):
        self.assertEqual(Q.normalize_text("Café “YES” ‘ok’"), "cafe \"yes\" 'ok'")
        self.assertEqual(Q.normalize_text("**Order** #W123 for `credit_card_9`"), "order #w123 for credit_card_9")
        self.assertEqual(Q.normalize_text("## Title\n- item one\n> quoted"), "title - item one quoted")
        from state_tracker.v3 import message_view as MV
        for s in ("Café **X**", "a\n\nb   c", "#W1 `x`"):
            self.assertEqual(Q.normalize_text(s), MV.normalize(s))          # the view's own normalization
        self.assertEqual(Q.normalize_text("see [the page](http://x.y/z) *now*"), "see the page now")
        self.assertEqual(Q.normalize_text(None), "")
        samples = ["**A** _b_ *c* #W1 gift_card_1", "x * y * z", "***bold italic***", "- a\n* b\n+ c",
                   "Été “q”", "1. first\n2. second", "a __b__ c"]
        for s in samples:
            n = Q.normalize_text(s)
            self.assertEqual(Q.normalize_text(n), n, s)                    # idempotent

    def test_quote_check(self):
        msg = "Yes, please **cancel** order #W123 — I’m sure."
        self.assertTrue(Q.quote_in("please cancel order #W123", [msg]))
        self.assertTrue(Q.quote_in("PLEASE   CANCEL", [msg]))                     # case, spaces
        self.assertTrue(Q.quote_in("\"I'm sure.\"", [msg]))                       # curly vs straight, quote marks
        self.assertTrue(Q.quote_in("...cancel order...", [msg]))                  # ellipsis at the edges
        self.assertFalse(Q.quote_in("please cancel my order", [msg]))             # not a substring
        self.assertFalse(Q.quote_in("", [msg]))
        self.assertFalse(Q.quote_in("   ", [msg]))
        self.assertTrue(Q.quote_in("cancel ... sure", [msg]))                     # pieces (p12 round 2)
        self.assertFalse(Q.quote_in("cancel ... not here", [msg]))               # every piece must be there
        self.assertTrue(Q.quote_in("second", ["first message", "the second one"]))
        self.assertFalse(Q.quote_in("x", []))


# ----------------------------------------------------------------------------------------------- cache and outcomes

class TestCache(unittest.TestCase):

    def test_key_is_sha256_of_question_version_model_effort_input(self):
        norm = Q.normalized_inputs("K8", {"message": "My WIFE's order"})
        want = Q.sha256_text(json.dumps({"q": "K8", "v": Q.key_version("K8"), "model": "gpt-6-luna",
                                         "effort": "low", "input": norm}, sort_keys=True, ensure_ascii=False,
                                        separators=(",", ":")))
        h = Q.Questions(Q.FakeBackend("no"))
        self.assertEqual(h.key("K8", {"message": "My WIFE's order"}), want)
        self.assertEqual(Q.key_version("K8"), "q1.s1")
        k = Q.cache_key("K8", "q1.s1", "gpt-6-luna", "low", norm)
        self.assertEqual(k, want)
        self.assertNotEqual(k, Q.cache_key("K9", "q1.s1", "gpt-6-luna", "low", norm))
        self.assertNotEqual(k, Q.cache_key("K8", "q2.s1", "gpt-6-luna", "low", norm))
        self.assertNotEqual(k, Q.cache_key("K8", "q1.s1", "gpt-5-nano", "low", norm))
        self.assertNotEqual(k, Q.cache_key("K8", "q1.s1", "gpt-6-luna", "medium", norm))
        self.assertNotEqual(k, Q.cache_key("K8", "q1.s1", "gpt-6-luna", "low", {"message": "other"}))

    def test_asked_once(self):
        fb = Q.FakeBackend("yes")
        h = Q.Questions(fb)
        a = h.ask("K4", {"message": "Can you check my wife's order?"})
        b = h.ask("K4", {"message": "can you check my WIFE’s order?"})     # the same after normalization
        self.assertEqual(fb.calls, 1)
        self.assertIs(a, b)
        self.assertEqual((h.stats.asks["K4"], h.stats.hits["K4"], h.stats.calls["K4"]), (2, 1, 1))
        h.ask("K5", {"reply": "Can you check my wife's order?"})                # another question: a new call
        self.assertEqual(fb.calls, 2)
        self.assertEqual(len(h.log), 2)
        with self.assertRaises(RuntimeError):
            h.store.put(a["key"], a)                                             # never saved twice

    def test_saved_answers_are_not_asked_again(self):
        with tempfile.TemporaryDirectory(prefix="p8_test_") as tmp:
            path = os.path.join(tmp, "answers_test.jsonl")
            h1 = Q.Questions(Q.FakeBackend("yes"), Q.JsonlStore(path))
            r1 = h1.ask("K8", {"message": "My flight was cancelled and I am upset"})
            h2 = Q.Questions(Q.SavedBackend(), Q.JsonlStore(path, writable=False))
            r2 = h2.ask("K8", {"message": "My flight was cancelled and I am upset"})
            self.assertEqual(r1, r2)
            self.assertEqual(h2.stats.calls["K8"], 0)
            with self.assertRaises(Q.AnswerNotSaved):
                h2.ask("K8", {"message": "another message"})
            with open(path, encoding="utf-8") as f:
                self.assertEqual(len(f.readlines()), 1)
            self.assertNotIn("questions_answers", os.listdir(tmp))


class TestOutcomes(unittest.TestCase):
    MSG = {"message": "My flight was delayed by five hours, this is awful."}

    def rec(self, policy):
        return Q.Questions(Q.FakeBackend(policy)).ask("K9", dict(self.MSG))

    def test_yes_no(self):
        r = self.rec("yes")
        self.assertEqual(r["status"], "yes")
        self.assertTrue(Q.quote_in(r["quote"], [self.MSG["message"]]))
        self.assertIs(Q.value_of(r), True)
        self.assertIs(Q.value_of(self.rec("no")), False)

    def test_unclear_and_failed_quotes_take_the_blocking_value(self):
        for policy, status in (("unclear", "unclear"), ("bad_quote", "quote_failed")):
            r = self.rec(policy)
            self.assertEqual(r["status"], status)
            with self.assertRaises(F.UseBlockingValue) as cm:
                Q.value_of(r)
            self.assertEqual(cm.exception.kind, "unclear")
        odd = [lambda q, i, n: {"answer": "no", "quote": "words that are in no message"},
               lambda q, i, n: {"answer": "yes", "quote": ""},
               lambda q, i, n: {"answer": "maybe", "quote": ""}]
        for f, status in zip(odd, ("quote_failed", "quote_failed", "bad_output")):
            r = Q.Questions(Q.FakeBackend(f)).ask("K9", dict(self.MSG))
            self.assertEqual(r["status"], status)
            with self.assertRaises(F.UseBlockingValue):
                Q.value_of(r)


# ----------------------------------------------------------------------------------------------- the helpers

class TestHelpersInEvaluate(unittest.TestCase):
    VIEW = FakeView([("user", "Hi, I need help with my order"),                       # 0
                     ("agent", "Sure. I will cancel order #W1 (reason: no longer needed). Confirm?"),   # 1
                     ("user", "Yes, please go ahead."),                                 # 2
                     ("agent", "Anything else?"),                                       # 3
                     ("user", "My wife also wants her order checked."),                 # 4
                     ], pending_text="Your order #W1 is cancelled.")

    def one(self, expr, blocking=False, code="True", answers=None, **kw):
        e = entry({"a": part("structure", code), "b": part("question", expr, "K4")}, "a AND b", blocking)
        return ev(e, view=self.VIEW, answers=answers, **kw)

    def test_values_and_blocking(self):
        self.assertIs(self.one("ask('K4', 4)", answers=Q.Questions(Q.FakeBackend("yes")))["value"], True)
        self.assertIs(self.one("ask('K4', 4)", answers=Q.Questions(Q.FakeBackend("no")))["value"], False)
        for blocking in (False, True):
            r = self.one("ask('K4', 4)", blocking=blocking, answers=Q.Questions(Q.FakeBackend("unclear")))
            self.assertIs(r["value"], blocking)
            self.assertEqual(r["how"], "blocking_value")
            self.assertEqual([p["kind"] for p in r["problems"]], ["unclear"])
        r = self.one("ask('K4', 4)", answers=Q.Questions(Q.FakeBackend("bad_quote")))
        self.assertEqual(r["how"], "blocking_value")
        with self.assertRaises(F.MissingInput):
            self.one("ask('K4', 4)", answers=None)                       # no answers hook: a definition error

    def test_code_part_false_asks_nothing(self):
        fb = Q.FakeBackend("yes")
        r = self.one("ask('K4', 4)", code="False", answers=Q.Questions(fb))
        self.assertIs(r["value"], False)
        self.assertEqual(r["parts"]["b"]["how"], "not_needed")
        self.assertEqual(fb.calls, 0)

    def test_first_yes_order_unclear_also_limit(self):
        t = {("K4", self.VIEW.text(0)): "no", ("K4", self.VIEW.text(2)): "yes", ("K4", self.VIEW.text(4)): "unclear"}
        h = Q.Questions(table_policy(t))
        self.assertIs(self.one("ask_first_yes('K4', [0, 2, 4])", answers=h)["value"], True)
        self.assertEqual(h.stats.calls["K4"], 2)                          # stops at the first yes
        h = Q.Questions(table_policy(t))
        self.assertIs(self.one("ask_first_yes('K4', [4, 2])", answers=h)["value"], True)    # unclear, then yes
        h = Q.Questions(table_policy(t))
        r = self.one("ask_first_yes('K4', [4, 0])", answers=h)                              # unclear, then no
        self.assertEqual((r["how"], r["problems"][0]["kind"]), ("blocking_value", "unclear"))
        h = Q.Questions(table_policy(t))
        self.assertIs(self.one("ask_first_yes('K4', [0, 2, 4], limit=1)", answers=h)["value"], False)
        self.assertEqual(h.stats.calls["K4"], 1)
        fb = Q.FakeBackend("yes")
        self.assertIs(self.one("ask_first_yes('K4', [])", answers=Q.Questions(fb))["value"], False)
        self.assertEqual(fb.calls, 0)
        fb = Q.FakeBackend("yes", exhaustive=True)
        h = Q.Questions(fb)
        self.assertIs(self.one("ask_first_yes('K4', [0, 2, 4])", answers=h)["value"], True)
        self.assertEqual(fb.calls, 3)                                     # the dry run's upper bound: all asked
        t2 = {("K2", self.VIEW.text(1)): "no", ("K1", self.VIEW.text(2)): "yes"}
        h = Q.Questions(table_policy(t2))
        self.assertIs(self.one("ask_first_yes('K1', [[1, 2]], also='K2')", answers=h)["value"], False)
        self.assertEqual((h.stats.calls["K2"], h.stats.calls["K1"]), (1, 0))   # K2 no: K1 not asked

    def test_messages_map_to_inputs(self):
        seen = []

        def spy(qid, inputs, norm):
            seen.append((qid, dict(inputs)))
            return "yes"

        h = Q.Questions(Q.FakeBackend(spy))
        self.one("ask_first_yes('K1', [[1, 2]])", answers=h, tool="cancel_pending_order",
                 args={"order_id": "#W1", "reason": "no longer needed"})
        self.one("ask_first_yes('K1', [[2]], focus='insurance')", answers=h, tool="book_reservation",
                 args={"insurance": "no"})
        self.one("ask('K14', 'Your email is a@b.c', [4, 0, 2])", answers=h)
        k1, k1b, k14 = seen
        self.assertEqual(k1[1]["listing"], self.VIEW.text(1))
        self.assertEqual(k1[1]["reply"], self.VIEW.text(2))
        self.assertIn("cancel the pending order", k1[1]["action"])
        self.assertIn("- reason: no longer needed", k1[1]["action"])
        self.assertNotIn("listing", k1b[1])                                # one message: the reply
        self.assertEqual(k1b[1]["reply"], self.VIEW.text(2))
        self.assertIn("does not buy travel insurance", k1b[1]["action"])
        self.assertEqual(k14[1]["user_said"], [self.VIEW.text(0), self.VIEW.text(2), self.VIEW.text(4)])
        self.assertEqual(k14[1]["reply"], "Your email is a@b.c")
        with self.assertRaises(F.MissingInput):                           # a ref needs the view
            e = entry({"a": part("structure", "True"), "b": part("question", "ask('K4', 4)", "K4")}, "a AND b")
            ev(e, view=None, answers=Q.Questions(Q.FakeBackend("yes")))
        r = self.one("ask('K4', '')", answers=h)                          # an empty message: no question, False
        self.assertIs(r["value"], False)
        self.assertEqual(h.stats.no_message["K4"], 1)
        with self.assertRaises(ValueError):                               # a definition error: it raises
            self.one("ask('K4', 4, focus='trip')", answers=h)            # (K4 has no call text to focus on)
        with self.assertRaises(ValueError):
            self.one("ask('K3', 3, items='sold')", answers=h)

    def test_offer_kind(self):
        def run(reply_answer, k8, k9, kind):
            def f(qid, inputs, norm):
                return {"K12": reply_answer, "K8": k8, "K9": k9}[qid]
            e = entry({"a": part("structure", "True"),
                       "c": part("question", f"offer_kind(args['content'], '{kind}', [0], [4])", "K12")},
                      "a AND c", True)
            return ev(e, view=self.VIEW, args={"content": "We offer a $100 certificate."},
                      answers=Q.Questions(Q.FakeBackend(f)))["value"]
        cancel = {"answer": "yes", "quote": "a $100 certificate"}            # neither kind word in the quote
        self.assertIs(run(cancel, "yes", "no", "cancelled"), True)          # the complaints decide
        self.assertIs(run(cancel, "yes", "no", "delayed"), False)
        self.assertIs(run(cancel, "no", "no", "delayed"), True)             # undecided: the blocking value
        self.assertIs(run(cancel, "unclear", "no", "delayed"), True)
        self.assertIs(run({"answer": "no", "quote": ""}, "yes", "yes", "cancelled"), False)    # no offer

        def run_quote(quote, kind):
            def f(qid, inputs, norm):
                return {"answer": "yes", "quote": quote} if qid == "K12" else "no"
            e = entry({"c": part("question", f"offer_kind(args['content'], '{kind}', [], [])", "K12")}, "c", True)
            return ev(e, view=self.VIEW, args={"content": "Sorry about the cancelled flight: a $100 certificate."},
                      answers=Q.Questions(Q.FakeBackend(f)))["value"]
        self.assertIs(run_quote("the cancelled flight: a $100 certificate", "cancelled"), True)
        self.assertIs(run_quote("the cancelled flight: a $100 certificate", "delayed"), False)

    def test_offer_amount_ok(self):
        def run(content, rate, counts, policy="yes"):
            fb = Q.FakeBackend(policy)
            e = entry({"e": part("question", f"offer_amount_ok(args['content'], {rate}, {counts})", "K12")}, "e")
            return ev(e, view=self.VIEW, args={"content": content}, answers=Q.Questions(fb)), fb
        r, fb = run("I can send you a certificate.", 100, [2])
        self.assertIs(r["value"], True)
        self.assertEqual(fb.calls, 0)                                      # no amount: no question
        self.assertIs(run("We offer $200 as a certificate", 100, [2])[0]["value"], True)
        self.assertIs(run("We offer $150 as a certificate", 100, [2])[0]["value"], False)
        self.assertIs(run("$100 per passenger as a certificate", 100, [3])[0]["value"], True)
        self.assertIs(run("We offer 50 dollars", 50, [1])[0]["value"], True)
        r, _ = run("We offer $150 as a certificate", 100, [2], policy="unclear")
        self.assertEqual(r["how"], "blocking_value")
        self.assertEqual([a for a, _, _ in Q.amounts_in("$1,200.50 and 30 USD")], [1200.5, 30.0])


class TestRenderAction(unittest.TestCase):

    def test_retail(self):
        st = built_state("retail")
        db = st.db
        oid, order = next((k, o) for k, o in sorted(db["orders"].items()) if o["status"] == "pending" and o["items"])
        item = order["items"][0]
        prod = db["products"][item["product_id"]]
        other = next(v for v in sorted(prod["variants"]) if v != item["item_id"])
        user = db["users"][order["user_id"]]
        pid, pm = sorted(user["payment_methods"].items())[0]
        args = {"order_id": oid, "item_ids": [item["item_id"]], "new_item_ids": [other], "payment_method_id": pid}
        t = Q.render_action(st, "modify_pending_order_items", args)
        self.assertIn(f"- order: {oid}", t)
        self.assertIn(item["name"], t)
        for v in prod["variants"][other]["options"].values():
            self.assertIn(str(v), t)
        self.assertIn(pid, t)
        self.assertEqual(t, Q.render_action(st, "modify_pending_order_items", args))         # deterministic
        g = Q.render_action(st, "cancel_pending_order", {"order_id": oid, "reason": "ordered by mistake"})
        self.assertIn("- reason: ordered by mistake", g)
        self.assertIn("payment method nope", Q.render_action(st, "modify_pending_order_payment",
                                                             {"order_id": oid, "payment_method_id": "nope"}))
        with self.assertRaises(ValueError):
            Q.render_action(st, "cancel_pending_order", {}, focus="color")

    def test_airline(self):
        st = built_state("airline")
        airports = {r["code"]: r["city"] for r in st.db_all("airport")}
        o, d = sorted(airports)[:2]
        num, fl = sorted(st.db["flights"].items())[0]
        date = sorted(fl["dates"])[0]
        args = {"user_id": "u1", "origin": o, "destination": d, "flight_type": "one_way", "cabin": "economy",
                "flights": [{"flight_number": num, "date": date}],
                "passengers": [{"first_name": "Ana", "last_name": "Lee", "dob": "1990-01-02"}],
                "payment_methods": [{"payment_id": "gift_card_1", "amount": 100}], "total_baggages": 1,
                "nonfree_baggages": 0, "insurance": "yes"}
        t = Q.render_action(st, "book_reservation", args)
        for x in (airports[o], airports[d], "one way", num, date, "Ana Lee", "1990-01-02", "travel insurance: yes"):
            self.assertIn(x, t)
        self.assertEqual(Q.trip_text(st, args), f"a one way trip from {airports[o]} ({o}) to {airports[d]} ({d})")
        self.assertIn("buys travel insurance", Q.render_action(st, "book_reservation", args, focus="insurance"))
        self.assertIn("the flight change of reservation R1",
                      Q.render_action(st, "update_reservation_flights", {"reservation_id": "R1", "payment_id": "x"},
                                      focus="payment"))


# ----------------------------------------------------------------------------------------------- K2 version 2 (p12 fix)

RETAIL_WRITES = ("cancel_pending_order", "modify_pending_order_address", "modify_user_address",
                 "modify_pending_order_payment", "modify_pending_order_items", "exchange_delivered_order_items",
                 "return_delivered_order_items")
AIRLINE_WRITES = ("book_reservation", "update_reservation_flights", "update_reservation_baggages",
                  "update_reservation_passengers", "cancel_reservation", "send_certificate")


def _retail_calls(st):
    """One call of every retail write tool on the database copy (docs/planning/tracker_v3/k2_fix.md)."""
    db = st.db
    pid, po = next((k, o) for k, o in sorted(db["orders"].items()) if o["status"] == "pending" and o["items"])
    did, do = next((k, o) for k, o in sorted(db["orders"].items()) if o["status"] == "delivered"
                   and len(o["items"]) >= 2)

    def other(it):
        return next(v for v in sorted(db["products"][it["product_id"]]["variants"]) if v != it["item_id"])
    uid = po["user_id"]
    pm = sorted(db["users"][uid]["payment_methods"])[0]
    addr = {"address1": "953 Park Avenue", "address2": "Suite 613", "city": "New York", "state": "NY",
            "country": "USA", "zip": "10064"}
    i0, d0, d1 = po["items"][0], do["items"][0], do["items"][1]
    return {
        "cancel_pending_order": {"order_id": pid, "reason": "no longer needed"},
        "modify_pending_order_address": dict(addr, order_id=pid),
        "modify_user_address": dict(addr, user_id=uid, address2=""),
        "modify_pending_order_payment": {"order_id": pid, "payment_method_id": pm},
        "modify_pending_order_items": {"order_id": pid, "item_ids": [i0["item_id"]], "new_item_ids": [other(i0)],
                                       "payment_method_id": pm},
        "exchange_delivered_order_items": {"order_id": did, "item_ids": [d0["item_id"], d1["item_id"]],
                                           "new_item_ids": [other(d0), other(d1)], "payment_method_id": pm},
        "return_delivered_order_items": {"order_id": did, "item_ids": [d0["item_id"]], "payment_method_id": pm},
    }


def _airline_calls(st):
    db = st.db
    rid, r = sorted(db["reservations"].items())[0]
    uid = r["user_id"]
    pms = sorted(db["users"][uid]["payment_methods"])
    num, fl = sorted(db["flights"].items())[0]
    date = sorted(fl["dates"])[0]
    pax = [{"first_name": "Ana", "last_name": "Lee", "dob": "1990-01-02"}]
    return {
        "book_reservation": {"user_id": uid, "origin": fl["origin"], "destination": fl["destination"],
                             "flight_type": "one_way", "cabin": "economy",
                             "flights": [{"flight_number": num, "date": date}], "passengers": pax,
                             "payment_methods": [{"payment_id": pms[0], "amount": 300}], "total_baggages": 2,
                             "nonfree_baggages": 1, "insurance": "no"},
        "update_reservation_flights": {"reservation_id": rid, "cabin": "business",
                                       "flights": [{"flight_number": num, "date": date}], "payment_id": pms[0]},
        "update_reservation_baggages": {"reservation_id": rid, "total_baggages": 2, "nonfree_baggages": 1,
                                        "payment_id": pms[0]},
        "update_reservation_passengers": {"reservation_id": rid, "passengers": pax},
        "cancel_reservation": {"reservation_id": rid},
        "send_certificate": {"user_id": uid, "amount": 150},
    }


class TestK2Version2(unittest.TestCase):

    def test_k2_is_version_2_with_the_agreed_text(self):
        q = Q.question("K2")
        self.assertEqual(q["version"], 2)
        self.assertEqual(q["question"], "Does message A state each line above, in one of the forms that line allows? "
                                        "If any line is missing or different, the answer is no. Other details "
                                        "(options that stay the same, prices) are not needed.")
        self.assertEqual(q["quote_from"], ["listing"])
        self.assertEqual([s.get("render") for s in q["inputs"]], [None, "listing_lines"])
        self.assertEqual(Q.load_questions()["answer_format"], {"answer": "yes|no|unclear", "quote": "..."})
        k1 = Q.question("K1")                                              # K1 keeps its input and version
        self.assertEqual((k1["version"], [s.get("render") for s in k1["inputs"]]), (1, [None, None, None]))
        doc = copy.deepcopy(Q.load_questions())
        doc["questions"]["K2"]["inputs"][1]["render"] = "other"
        self.assertTrue(any("render must be one of" in p for p in Q.check_doc(doc)))

    def test_renders_every_write_tool_of_both_domains(self):
        for domain, tools, calls in (("retail", RETAIL_WRITES, _retail_calls), ("airline", AIRLINE_WRITES,
                                                                               _airline_calls)):
            st = built_state(domain)
            cs = calls(st)
            self.assertEqual(set(cs), set(tools))
            for tool in tools:
                with self.subTest(domain=domain, tool=tool):
                    args = cs[tool]
                    t = Q.render_listing(st, tool, args)
                    head, *lines = t.split("\n")
                    self.assertIn(f"(tool {tool}). The lines:", head)
                    self.assertTrue(lines)
                    for ln in lines:
                        self.assertTrue(ln.startswith("- ") and " counts if " in ln, ln)
                    if "user_id" in args:
                        self.assertNotIn(args["user_id"], t)              # never the user's own id
                    self.assertNotIn("credit_card_", t)                   # never a card's internal id
                    self.assertEqual(t, Q.render_listing(st, tool, args))      # deterministic
                    if "order_id" in args:
                        self.assertIn(f"- order: {args['order_id']}", t)
                    if "reservation_id" in args:
                        self.assertIn(f"- reservation: {args['reservation_id']}", t)
        st = built_state("retail")
        self.assertIn("- reason: no longer needed", Q.render_listing(st, "cancel_pending_order",
                                                                     _retail_calls(st)["cancel_pending_order"]))
        st = built_state("airline")
        ca = _airline_calls(st)
        self.assertIn("- certificate amount: 150", Q.render_listing(st, "send_certificate", ca["send_certificate"]))
        self.assertEqual(Q.render_listing(st, "cancel_reservation", ca["cancel_reservation"]).count("\n- "), 1)

    def test_k2_uses_the_lines_and_k1_keeps_render_action(self):
        seen = []

        def spy(qid, inputs, norm):
            seen.append((qid, dict(inputs)))
            return "yes"
        st = built_state("retail")
        args = _retail_calls(st)["return_delivered_order_items"]
        for expr, qid in (("ask('K2', 'Return the items?')", "K2"),
                          ("ask('K1', 'Return the items?', 'Yes please')", "K1")):
            e = entry({"a": part("structure", "True"), "b": part("question", expr, qid)}, "a AND b")
            ev(e, domain="retail", args=args, answers=Q.Questions(Q.FakeBackend(spy)),
               tool="return_delivered_order_items")
        (q2, i2), (q1, i1) = seen
        self.assertEqual(i2["details"], Q.render_listing(st, "return_delivered_order_items", args))
        self.assertEqual(i1["action"], Q.render_action(st, "return_delivered_order_items", args))   # unchanged

    def test_changed_options(self):
        self.assertEqual(Q.changed_options({"color": "black", "size": "M"}, {"color": "red", "size": "M"}),
                         [("color", "black", "red")])
        self.assertEqual(Q.changed_options({"a": 1}, {"a": 1}), [])
        self.assertEqual(Q.changed_options({"a": 1, "b": 2}, {"b": 3, "c": 4}),
                         [("a", 1, None), ("b", 2, 3), ("c", None, 4)])
        st = built_state("retail")
        db = st.db
        for pid_, prod in sorted(db["products"].items()):
            vs = sorted(prod["variants"])
            pair = next(((a, b) for a in vs for b in vs if a != b and
                         sum(prod["variants"][a]["options"][k] != prod["variants"][b]["options"].get(k)
                             for k in prod["variants"][a]["options"]) == 1), None)
            if pair:
                break
        a, b = pair
        oa, ob = prod["variants"][a]["options"], prod["variants"][b]["options"]
        (k, va, vb), = Q.changed_options(oa, ob)
        line = Q.changed_item_line(st, a, b)
        self.assertIn(f"each option that changes: {k} {va} {Q.ARROW} {vb}", line)
        self.assertIn(f"new item for {prod['name']} [item {a}]: item {b}", line)
        for k2, v in oa.items():                                          # the options that stay are not asked
            if k2 != k:
                self.assertNotIn(f"{k2} {v}", line.split("changes:")[1])
        self.assertIn("no option changes", Q.changed_item_line(st, a, a))
        self.assertIn(f"gives the new item id", Q.changed_item_line(st, a, "0000000000"))
        self.assertNotIn("changes:", Q.changed_item_line(st, a, "0000000000"))

    def test_payment_forms(self):
        st = built_state("retail")
        db = st.db
        pms = {}
        for uid, u in sorted(db["users"].items()):
            for pid_, pm in sorted(u["payment_methods"].items()):
                pms.setdefault(pm["source"], (pid_, pm))
        pid_, pm = pms["credit_card"]
        what, forms = Q.payment_line(st, pid_)
        self.assertIn(f"ending in {pm['last_four']}", what)
        self.assertIn(f"the last four digits {pm['last_four']}", forms)
        self.assertNotIn(pid_, what + forms)                               # not the internal id
        gid, _ = pms["gift_card"]
        what, forms = Q.payment_line(st, gid)
        self.assertIn("gift card", what)
        self.assertIn(f"says gift card, or gives the gift card id ({gid})", forms)
        ppid, _ = pms["paypal"]
        self.assertEqual(Q.payment_line(st, ppid), ("PayPal", "the message says PayPal"))
        self.assertIn("amount paid with it (40)", Q.payment_line(st, gid, 40)[1])
        a = built_state("airline")
        uid, u = next((k, x) for k, x in sorted(a.db["users"].items()) if len(x["payment_methods"]) >= 2)
        p1, p2 = sorted(u["payment_methods"])[:2]
        base = {"user_id": uid, "origin": "JFK", "destination": "LAX", "flight_type": "one_way", "cabin": "economy",
                "flights": [], "passengers": [], "total_baggages": 0, "nonfree_baggages": 0, "insurance": "yes"}
        one = Q.render_listing(a, "book_reservation", dict(base, payment_methods=[{"payment_id": p1, "amount": 300}]))
        self.assertNotIn("300", one)                                       # one method: no amount needed
        two = Q.render_listing(a, "book_reservation", dict(base, payment_methods=[
            {"payment_id": p1, "amount": 300}, {"payment_id": p2, "amount": 120}]))
        self.assertIn("the amount paid with it (300)", two)
        self.assertIn("the amount paid with it (120)", two)
        self.assertIn("travel insurance: added", one)
        self.assertNotIn("JFK", one)                                       # origin / destination: not needed
        bags = {"reservation_id": "R1", "total_baggages": 2, "nonfree_baggages": 0, "payment_id": p1}
        self.assertNotIn("payment method", Q.render_listing(a, "update_reservation_baggages", bags))
        paid = Q.render_listing(a, "update_reservation_baggages", dict(bags, nonfree_baggages=1))
        self.assertIn("- payment method:", paid)
        self.assertIn("the total number of checked bags (2) and how many are paid (1)", paid)

    def test_address_and_passenger_forms(self):
        line = Q.address_line({"address1": "1 Main St", "address2": "", "city": "Austin", "state": "TX",
                               "country": "USA", "zip": "78701"})
        self.assertIn("street line 1 (1 Main St); city (Austin); state (TX); zip (78701); country (USA)", line)
        self.assertNotIn("line 2", line)                                   # an empty field is not asked
        self.assertIn("line 2 (Apt 4)", Q.address_line({"address1": "1 Main St", "address2": "Apt 4"}))
        line = Q.passenger_line({"first_name": "Ana", "last_name": "Lee", "dob": "1990-01-02"})
        self.assertIn("the first and last name (Ana Lee) and the date of birth (1990-01-02", line)
        line = Q.flight_line({"flight_number": "HAT001", "date": "2024-05-01"})
        self.assertIn("the flight number (HAT001) and the date (2024-05-01", line)
        self.assertIn("the year may be left out", line)
        st = built_state("retail")
        t = Q.render_listing(st, "modify_user_address", _retail_calls(st)["modify_user_address"])
        self.assertNotIn("- order:", t)

    def test_quote_check_ignores_markdown_marks_and_line_breaks(self):
        msg = "Order **#W6067464** is delivered.\n\nI found the **Wall Clock** (item `8917609800`) and __more__."
        self.assertTrue(Q.quote_in("Order **#W6067464** is delivered.\n\nI found the **Wall Clock**", [msg]))
        self.assertTrue(Q.quote_in("Order #W6067464 is delivered. I found the Wall Clock", [msg]))
        self.assertTrue(Q.quote_in("is delivered.\nI found", [msg]))                      # one line break
        self.assertTrue(Q.quote_in("item 8917609800) and more", [msg]))                   # backticks, __
        self.assertTrue(Q.quote_in("**953 Park Avenue**  \n**New York, NY**", ["**953 Park Avenue**\n**New York, NY**"]))
        self.assertFalse(Q.quote_in("Order #W6067464 I found", [msg]))                    # a skip is still no quote
        self.assertEqual(Q.quote_form("A **b**\n\n`c` __d__"), "a b c d")

    def test_saved_status_is_derived_again_on_read(self):
        msg = {"message": "My **flight**\nwas delayed by five hours."}
        with tempfile.TemporaryDirectory(prefix="k2fix_test_") as tmp:
            path = os.path.join(tmp, "answers_test.jsonl")
            h = Q.Questions(Q.FakeBackend("no"), Q.JsonlStore(path))
            key = h.key("K9", msg)
            old = {"key": key, "qid": "K9", "version": Q.key_version("K9"), "model": "gpt-6-luna", "effort": "low",
                   "input": Q.normalized_inputs("K9", msg), "answer": "yes", "quote": "**flight**\nwas delayed",
                   "status": "quote_failed", "source": "real",
                   "raw": json.dumps({"answer": "yes", "quote": "**flight**\nwas delayed"})}
            with open(path, "w", encoding="utf-8") as f:
                f.write(json.dumps(old) + "\n")
            with open(path, encoding="utf-8") as f:
                before = f.read()
            h2 = Q.Questions(Q.SavedBackend(), Q.JsonlStore(path, writable=False))
            r = h2.ask("K9", msg)
            self.assertEqual((r["status"], r["status_saved"]), ("yes", "quote_failed"))
            self.assertIs(Q.value_of(r), True)
            self.assertEqual(Q.saved_status(old), "yes")                   # from the record's own input too
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), before)                         # the store is never changed
            bad = dict(old, raw="not json")
            self.assertEqual(Q.saved_status(bad), "bad_output")            # the raw text decides
            same = Q.Questions(Q.FakeBackend("yes"))
            a = same.ask("K9", msg)
            self.assertIs(same.ask("K9", msg), a)                          # unchanged status: the same record
            fb = Q.Questions(Q.FakeBackend(lambda q, i, n: {"answer": "yes", "quote": "x", "bad_output": True}))
            r1 = fb.ask("K9", msg)
            self.assertEqual((r1["status"], fb.ask("K9", msg)["status"]), ("bad_output", "bad_output"))

    def test_k4_k5_k13_version_2(self):
        doc = Q.load_questions()
        for qid, words in (("K4", "count as the user's own unless message A says they belong to someone else"),
                           ("K5", "count as the user's own unless message A says otherwise"),
                           ("K13", "Judge only what message A itself asks for: a message that asks for nothing new "
                                   "(it only gives an id, a date, a reason, a choice or a yes) is no.")):
            self.assertEqual(Q.key_version(qid), "q2.s1")
            self.assertIn(words, Q.question(qid)["question"])
        retail = doc["domain_texts"]["tools"]["retail"]
        self.assertIn("Modify a pending order: its shipping address, its payment method, or the options of its items "
                      "(another option of the same product), but nothing else.", retail)
        self.assertNotIn("available", retail.split("Modify a pending order")[1].split(".")[0])
        for qid in ("K1", "K3", "K6", "K7", "K8", "K9", "K10", "K11", "K12", "K14", "K15", "K16"):
            self.assertEqual(Q.key_version(qid), "q1.s1")                 # the others keep their keys

    def test_multi_piece_quotes(self):
        """p12 round 2: a K2 quote may join pieces of message A with ';', '...', the ellipsis sign or line breaks;
        every piece must be in the same message (store examples)."""
        msg = ("I found your Las Vegas\u2013Denver round-trip reservation **GV1N64**. It includes three passengers.\n\n"
               "I can request the change to **economy for all three passengers**, keeping both flights:\n"
               "- **May 19:** HAT003, LAS to DEN\n- **May 20:** HAT290, DEN to LAS\n\n"
               "I\u2019ll use the original payment method, **gift card ending in 1642017**, for any refund.")
        q = ("GV1N64; economy for all three passengers; May 19: HAT003, LAS to DEN; May 20: HAT290, DEN to LAS; "
             "gift card ending in 1642017")
        self.assertTrue(Q.quote_in(q, [msg]))
        self.assertEqual(len(Q.quote_pieces(q)), 5)
        msg2 = ("Order **#W2092674**: I will exchange item **4510078629**, metal strap with black dial\u2014for the "
                "**leather strap with white dial**, item **1355937109**. The difference goes back to your PayPal.")
        q2 = ("#W2092674; item **4510078629**, metal strap with black dial\u2014for the **leather strap with white "
              "dial**, item **1355937109**; PayPal")
        self.assertTrue(Q.quote_in(q2, [msg2]))
        self.assertTrue(Q.quote_in("Order **#W2092674** \u2026 PayPal", [msg2]))
        self.assertTrue(Q.quote_in("#W2092674\n\nPayPal", [msg2]))
        self.assertFalse(Q.quote_in("#W2092674; Mastercard", [msg2]))              # one piece missing
        self.assertFalse(Q.quote_in("#W2092674; HAT003", [msg2, msg]))             # pieces from two messages
        self.assertFalse(Q.quote_in(" ; ... \n", [msg2]))                         # no non-empty piece
        self.assertFalse(Q.quote_in("order #W2092674 - reason: no longer needed", [msg2]))   # one edited piece
        rec = {"qid": "K2", "input": {"listing": Q.normalize_text(msg2)}, "source": "real", "status": "quote_failed",
               "raw": json.dumps({"answer": "yes", "quote": q2})}
        self.assertEqual(Q.saved_status(rec), "yes")                              # re-derived on read

    def test_only_changed_flights_and_passengers(self):
        st = built_state("airline")
        rid, r = next((k, x) for k, x in sorted(st.db["reservations"].items())
                      if len(x["flights"]) >= 2 and x["passengers"])
        same = [{"flight_number": f["flight_number"], "date": f["date"]} for f in r["flights"]]
        pm = sorted(st.db["users"][r["user_id"]]["payment_methods"])[0]
        args = {"reservation_id": rid, "cabin": "business", "flights": same, "payment_id": pm}
        t = Q.render_listing(st, "update_reservation_flights", args)
        self.assertNotIn("- flight:", t)                                          # cabin-only change: no flight
        self.assertIn("- cabin: business", t)
        self.assertIn(f"- reservation: {rid}", t)
        self.assertIn("- payment method:", t)
        moved = [dict(same[0], date="2024-05-30")] + same[1:]
        t = Q.render_listing(st, "update_reservation_flights", dict(args, flights=moved))
        self.assertEqual(t.count("- flight:"), 1)
        self.assertIn(f"- flight: {same[0]['flight_number']} on 2024-05-30", t)
        self.assertEqual(Q.changed_flights(st, "NO_SUCH", moved), moved)          # unknown reservation: all
        ps = [{k: p[k] for k in ("first_name", "last_name", "dob")} for p in r["passengers"]]
        t = Q.render_listing(st, "update_reservation_passengers", {"reservation_id": rid, "passengers": ps})
        self.assertNotIn("- passenger:", t)
        new = [dict(ps[0], dob="1999-09-09")] + ps[1:]
        t = Q.render_listing(st, "update_reservation_passengers", {"reservation_id": rid, "passengers": new})
        self.assertEqual(t.count("- passenger:"), 1)
        self.assertIn("1999-09-09", t)
        book = Q.render_listing(st, "book_reservation", {"flights": same, "passengers": ps, "cabin": "economy",
                                                         "payment_methods": [], "total_baggages": 0,
                                                         "nonfree_baggages": 0, "insurance": "no"})
        self.assertEqual(book.count("- flight:"), len(same))                      # a booking: every flight is new
        self.assertEqual(book.count("- passenger:"), len(ps))

    def test_k2_version_1_keys_are_not_reused(self):
        self.assertEqual(Q.key_version("K2"), "q2.s1")
        inputs = {"listing": "Order #W1, refund to your card.", "details": "cancel the pending order"}
        norm = Q.normalized_inputs("K2", inputs)
        v1 = Q.cache_key("K2", "q1.s1", "gpt-6-luna", "low", norm)
        h = Q.Questions(Q.FakeBackend("no"))
        self.assertNotEqual(h.key("K2", inputs), v1)
        h.store.put(v1, {"key": v1, "qid": "K2", "answer": "yes", "quote": "Order #W1", "status": "yes",
                         "input": norm, "version": "q1.s1"})
        r = h.ask("K2", inputs)
        self.assertEqual((h.stats.calls["K2"], h.stats.hits["K2"], r["version"]), (1, 0, "q2.s1"))


# ----------------------------------------------------------------------------------------------- OR parts (p12 fix)

class TestUnclearInOneBranch(unittest.TestCase):
    """facts_format_v3: an unclear answer gives only its question part the blocking value; combine goes on (the
    pattern of ours.p10_luna_train|airline/27/2|7 and partner.luna_train_v5|airline/27/0|6: K13 unclear in part a,
    used flight in part b, K16 yes in part c)."""
    K13 = "ask_first_yes('K13', ['I need to cancel; my first flight already left.'])"
    K16 = "ask_first_yes('K16', ['Please cancel my reservation.'])"

    def run_or(self, k13, k16, b="True", blocking=False):
        fb = Q.FakeBackend(lambda q, i, n: {"K13": k13, "K16": k16}[q])
        e = entry({"a": part("question", self.K13, "K13"), "b": part("structure", b),
                   "c": part("question", self.K16, "K16")}, "a OR (b AND c)", blocking)
        h = Q.Questions(fb)
        return ev(e, domain="airline", answers=h, tool="cancel_reservation", args={"reservation_id": "R1"}), h

    def test_the_combine_is_the_real_facts(self):
        e = F.load_facts("airline")["facts"]["request_cannot_be_handled_with_available_tools"]
        self.assertEqual((e["combine"], e["blocking_value"]), ("a OR (b AND c)", False))
        self.assertEqual([e["parts"][p]["question"] for p in "abc"], ["K13", None, "K16"])

    def test_unclear_in_one_branch_lets_the_other_branch_decide(self):
        r, h = self.run_or("unclear", "yes")
        self.assertIs(r["value"], True)                                    # used flight + K16 yes (S41)
        self.assertEqual(r["how"], "combine")                              # true whatever a would be
        self.assertEqual(r["problems"], [])                                # problems -> blocking value stays true
        self.assertEqual([(p["kind"], p["part"]) for p in r["problems_ignored"]], [("unclear", "a")])   # listed
        self.assertEqual((h.stats.calls["K13"], h.stats.calls["K16"]), (1, 1))
        r, h = self.run_or("unclear", "no")
        self.assertIs(r["value"], False)                                   # a's blocking value (false)
        self.assertEqual(r["how"], "blocking_value")                       # it rests on the unclear part
        self.assertEqual(([p["kind"] for p in r["problems"]], r["problems_ignored"]), (["unclear"], []))
        r, h = self.run_or("unclear", "yes", b="False")
        self.assertIs(r["value"], False)
        self.assertEqual(h.stats.calls["K16"], 0)                          # code says no: K16 not asked
        r, h = self.run_or("no", "unclear")                                # unclear in the other branch
        self.assertIs(r["value"], False)
        self.assertEqual(r["how"], "blocking_value")
        r, h = self.run_or("unclear", "unclear", blocking=True)            # blocking true: an OR part true
        self.assertIs(r["value"], True)
        self.assertEqual(h.stats.calls["K16"], 0)

    def test_unclear_in_an_and_still_blocks(self):
        for blocking in (False, True):
            fb = Q.FakeBackend(lambda q, i, n: {"K13": "yes", "K16": "unclear"}[q])
            e = entry({"a": part("structure", "True"), "b": part("question", self.K13, "K13"),
                       "c": part("question", self.K16, "K16")}, "a AND b AND c", blocking)
            r = ev(e, domain="airline", answers=Q.Questions(fb), tool="cancel_reservation")
            self.assertIs(r["value"], blocking)
            self.assertEqual((r["how"], [p["kind"] for p in r["problems"]]), ("blocking_value", ["unclear"]))

    def test_other_problems_still_block_the_whole_fact(self):
        fb = Q.FakeBackend(lambda q, i, n: {"K13": "no", "K16": "yes"}[q])
        e = entry({"a": part("question", self.K13, "K13"), "b": part("structure", "args['nope'] == 1"),
                   "c": part("question", self.K16, "K16")}, "a OR (b AND c)", False)
        h = Q.Questions(fb)
        r = ev(e, domain="airline", answers=h, tool="cancel_reservation", args={"reservation_id": "R1"})
        self.assertEqual((r["value"], r["how"]), (False, "blocking_value"))
        self.assertEqual([p["kind"] for p in r["problems"]], ["missing_argument"])
        self.assertEqual(sum(h.stats.calls.values()), 0)                   # after a code problem: no question


# ----------------------------------------------------------------------------------------------- the two keys

def _unkeyed(e):
    """Question parts whose yes alone (every code part false, every other question part no) makes combine true; and
    "all questions" when only several yes together do."""
    tree = F.parse_combine(e["combine"])
    qs = [p for p, x in e["parts"].items() if x["source"] == "question"]
    codes = {p: False for p, x in e["parts"].items() if x["source"] != "question"}
    out = {q for q in qs if F.combine_value(tree, dict(codes, **{x: x == q for x in qs}))}
    if not out and F.combine_value(tree, dict(codes, **{x: True for x in qs})):
        out.add("all questions")
    return out


LITERAL = {
    "K1": "ask('K1', 'I will cancel order #W1 for you. Shall I go ahead?', 'Yes, please go ahead.')",
    "K2": "ask('K2', 'Order #W1, reason: no longer needed, refund to your card.')",
    "K3": "ask('K3', 'Please make sure these are all the items you want to change.', items='exchanged')",
}


def literal_expr(qid, overlay_expr):
    if overlay_expr.startswith("offer_kind"):
        return "offer_kind('We can offer a certificate for the trouble.', 'cancelled', [], [])"
    if overlay_expr.startswith("offer_amount_ok"):
        return "offer_amount_ok('We can offer a certificate for the trouble.', 100, [1])"
    return LITERAL.get(qid, f"ask('{qid}', 'A message of the conversation about it.')")


class TestTwoKeys(unittest.TestCase):
    """A yes alone never makes a fact true when its code parts are false (the real fact entries, fake answers)."""

    def test_every_question_part_is_anded_with_a_code_part(self):
        found = set()
        for d in DOMAINS:
            for name, e in F.load_facts(d)["facts"].items():
                if not any(x["source"] == "question" for x in e["parts"].values()):
                    continue
                for p in _unkeyed(e):
                    found.add((d, name, p))
        self.assertEqual(found, UNKEYED)

    def _real_entries(self):
        for d in DOMAINS:
            ov = load_overlay(d)["exprs"]
            for name, e in F.load_facts(d)["facts"].items():
                if not any(p["source"] == "question" for p in e["parts"].values()):
                    continue
                yield d, name, e, ov[name]

    def _with(self, e, ov, code_value):
        e = copy.deepcopy(e)
        for pid, p in e["parts"].items():
            p["expr"] = (literal_expr(p["question"], ov[pid]["expr"]) if p["source"] == "question"
                         else ("True" if code_value else "False"))
        e.pop("for_each", None)
        return e

    def test_yes_alone_never_allows(self):
        n = 0
        for d, name, e, ov in self._real_entries():
            with self.subTest(domain=d, fact=name):
                fb = Q.FakeBackend("yes")
                r = ev(self._with(e, ov, False), d, answers=Q.Questions(fb), name=name)
                keyed = not any((d, name, p) in UNKEYED for p in e["parts"])
                if keyed:
                    self.assertIs(r["value"], False)
                    self.assertEqual(fb.calls, 0)                         # the question is not even asked
                else:
                    self.assertIs(r["value"], True)                       # the documented exception (K13 alone)
                n += 1
        self.assertEqual(n, 28)                                           # 12 retail + 16 airline facts

    def test_both_keys_allow_and_a_no_follows_combine(self):
        for d, name, e, ov in self._real_entries():
            with self.subTest(domain=d, fact=name):
                r = ev(self._with(e, ov, True), d, answers=Q.Questions(Q.FakeBackend("yes")), name=name)
                self.assertIs(r["value"], True)
                self.assertEqual(r["how"], "combine")
                r = ev(self._with(e, ov, True), d, answers=Q.Questions(Q.FakeBackend("no")), name=name)
                vals = {p: (True if x["source"] != "question" else
                            ov[p]["expr"].startswith(("offer_kind", "offer_amount_ok")))
                        for p, x in e["parts"].items()}
                # offer_kind / offer_amount_ok parts read K12 = no as "no offer": kind False, amount True
                for p, x in e["parts"].items():
                    if ov.get(p, {}).get("expr", "").startswith("offer_kind"):
                        vals[p] = False
                self.assertIs(r["value"], F.combine_value(F.parse_combine(e["combine"]), vals))

    def test_unclear_takes_the_blocking_value_on_real_entries(self):
        import itertools
        for d, name, e, ov in self._real_entries():
            with self.subTest(domain=d, fact=name):
                tree = F.parse_combine(e["combine"])
                qs = [p for p, x in e["parts"].items() if x["source"] == "question"]
                codes = [p for p, x in e["parts"].items() if x["source"] != "question"]
                pick = None                                  # code values under which the questions decide
                for vs in itertools.product([True, False], repeat=len(codes)):
                    cv = dict(zip(codes, vs))
                    if F.combine_value(tree, dict(cv, **{q: True for q in qs})) != \
                            F.combine_value(tree, dict(cv, **{q: False for q in qs})):
                        pick = cv
                        break
                self.assertIsNotNone(pick)
                e2 = self._with(e, ov, True)
                for p, v in pick.items():
                    e2["parts"][p]["expr"] = "True" if v else "False"
                r = ev(e2, d, answers=Q.Questions(Q.FakeBackend("unclear")), name=name)
                self.assertIs(r["value"], e["blocking_value"])
                self.assertEqual(r["how"], "blocking_value")
                self.assertIn("unclear", [p["kind"] for p in r["problems"]])


# ----------------------------------------------------------------------------------------------- the overlays

class TestOverlays(unittest.TestCase):

    def test_overlay_covers_exactly_the_question_parts(self):
        for d in DOMAINS:
            ov = load_overlay(d)
            self.assertEqual((ov["domain"], ov["by"]), (d, "p8"))
            facts = F.load_facts(d)["facts"]
            want = {(n, p) for n, e in facts.items() for p, x in e["parts"].items() if x["source"] == "question"}
            got = {(n, p) for n, ps in ov["exprs"].items() for p in ps}
            self.assertEqual(got, want)
            self.assertEqual(len(want), {"retail": 12, "airline": 26}[d])
            for n, ps in ov["exprs"].items():
                for p, x in ps.items():
                    with self.subTest(domain=d, fact=n, part=p):
                        expr = x["expr"]
                        L.parse(expr)
                        k = facts[n]["parts"][p]["question"]
                        if expr.startswith(("offer_kind", "offer_amount_ok")):
                            self.assertEqual(k, "K12")
                        else:
                            self.assertTrue(expr.startswith(("ask(", "ask_first_yes(")))
                            self.assertEqual(expr.split("'")[1], k)        # the question the part names

    def test_overlay_expressions_validate_with_the_structure_helpers(self):
        try:
            import state_tracker.v3.message_view  # noqa: F401  (p7: registers the structure helpers)
            import state_tracker.v3.code_helpers  # noqa: F401  (p6)
        except ImportError as e:
            self.skipTest(f"p7 / p6 helpers not importable yet: {e}")
        for d in DOMAINS:
            kinds = L.domain_kinds(d)
            for n, ps in load_overlay(d)["exprs"].items():
                for p, x in ps.items():
                    with self.subTest(domain=d, fact=n, part=p):
                        info = F.validate_expr(x["expr"], kinds)
                        self.assertEqual(F.helper_use_problems("question", info["helpers"]), [])


# ----------------------------------------------------------------------------------------------- the network

_NET_SCRIPT = r"""
import json, socket, sys, urllib.request
sys.path.insert(0, sys.argv[1])
sys.dont_write_bytecode = True
from state_tracker.v3 import questions as Q
out = {}
Q.block_network()
def tries(name, f):
    try:
        f()
        out[name] = "allowed"
    except Q.NetworkBlocked:
        out[name] = "refused"
    except Exception as e:
        out[name] = "other: " + type(e).__name__ + ": " + str(e)
tries("connect", lambda: socket.create_connection(("127.0.0.1", 9), timeout=1))
tries("getaddrinfo", lambda: socket.getaddrinfo("localhost", 80))
tries("inet_socket", lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM))
tries("urlopen", lambda: urllib.request.urlopen("http://127.0.0.1:9/", timeout=1))
a, b = socket.socketpair()
out["unix_socketpair"] = "allowed"
a.close(); b.close()
out["events_after_tries"] = len(Q.network_events())
try:
    Q.RealBackend("I approve this paid step today", 5.0, 10)
    out["real_mode"] = "started"
except Q.RealModeRefused as e:
    out["real_mode"] = "refused"
h = Q.Questions(Q.FakeBackend("yes"))
for qid in Q.question_ids():
    h.ask(qid, Q.sample_inputs(qid))
out["fake_calls"] = sum(h.stats.calls.values())
out["events_end"] = len(Q.network_events())
print(json.dumps(out))
"""

_CLEAN_SCRIPT = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
sys.dont_write_bytecode = True
from state_tracker.v3 import questions as Q
Q.block_network()
h = Q.Questions(Q.FakeBackend("yes", exhaustive=True))
for qid in Q.question_ids():
    for i in range(3):
        h.ask(qid, Q.sample_inputs(qid) if i == 0 else {**Q.sample_inputs(qid)})
print(json.dumps({"events": len(Q.network_events()), "calls": sum(h.stats.calls.values()),
                  "blocked": Q.network_blocked()}))
"""


def _run_py(script):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0")
    r = subprocess.run([sys.executable, "-B", "-c", script, PC_DIR], capture_output=True, text=True, cwd=PC_DIR,
                       timeout=300, env=env)
    if r.returncode != 0:
        raise AssertionError(r.stderr[-3000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


class TestNetworkBlock(unittest.TestCase):

    def test_the_hook_refuses_every_network_socket(self):
        out = _run_py(_NET_SCRIPT)
        for k in ("connect", "getaddrinfo", "inet_socket", "urlopen"):
            self.assertEqual(out[k], "refused", k)
        self.assertEqual(out["unix_socketpair"], "allowed")
        self.assertGreaterEqual(out["events_after_tries"], 4)
        self.assertEqual(out["real_mode"], "refused")                     # real mode never starts behind the block
        self.assertEqual(out["fake_calls"], 16)
        self.assertEqual(out["events_end"], out["events_after_tries"])   # fake answers open no socket

    def test_a_fake_run_makes_zero_network_events(self):
        out = _run_py(_CLEAN_SCRIPT)
        self.assertEqual(out, {"events": 0, "calls": 16, "blocked": True})


# ----------------------------------------------------------------------------------------------- real mode

class FakeResponse:
    def __init__(self, text, tin=1000, tout=100):
        class U:
            input_tokens = tin
            output_tokens = tout

            class output_tokens_details:
                reasoning_tokens = 40

            class input_tokens_details:
                cached_tokens = 0
        self.usage = U()
        self.output_text = text
        self.status = "completed"


class FakeClient:
    """Stands in for the OpenAI client (no network). Fails the first `fail` calls."""

    def __init__(self, text='{"answer": "yes", "quote": "my flight was cancelled"}', fail=0):
        self.calls = 0
        self.fail = fail
        self.text = text
        self.responses = self
        self.kwargs = []

    def create(self, **kw):
        self.calls += 1
        self.kwargs.append(kw)
        if self.calls <= self.fail:
            raise TimeoutError("fake timeout")
        return FakeResponse(self.text)


WORDS = "I approve the p12 tiny-question run, limit 26 dollars"


class TestRealModeGuards(unittest.TestCase):

    def test_refuses_without_approval_budget_or_with_network_blocked(self):
        with network_flag(False):
            for approved in (None, "", "yes", "ok", "<the user's approval words>", "short"):
                with self.assertRaises(Q.RealModeRefused):
                    Q.check_real_mode(approved, 10.0, 100)
            for usd in (None, 0, -1, "abc", 1000.0, float("nan")):
                with self.assertRaises(Q.RealModeRefused):
                    Q.check_real_mode(WORDS, usd, 100)
            for calls in (None, 0, -5, 1.5, True, "10"):
                with self.assertRaises(Q.RealModeRefused):
                    Q.check_real_mode(WORDS, 10.0, calls)
            self.assertEqual(Q.check_real_mode(WORDS, 10.0, 100), (WORDS, 10.0, 100))
            with self.assertRaises(Q.RealModeRefused):
                Q.RealBackend(None, 10.0, 100, client=FakeClient())
            with self.assertRaises(Q.RealModeRefused):
                Q.RealBackend(WORDS, None, 100, client=FakeClient())
            with self.assertRaises(Q.RealModeRefused):
                Q.RealBackend(WORDS, 10.0, None, client=FakeClient())
        with network_flag(True):
            with self.assertRaises(Q.RealModeRefused):
                Q.check_real_mode(WORDS, 10.0, 100)

    def test_the_answers_file_is_written_only_in_real_mode(self):
        existed = os.path.exists(Q.ANSWERS_PATH)
        with self.assertRaises(Q.RealModeRefused):
            Q.Questions(Q.FakeBackend("yes"), Q.JsonlStore(Q.ANSWERS_PATH))
        self.assertEqual(os.path.exists(Q.ANSWERS_PATH), existed)
        Q.Questions(Q.SavedBackend(), Q.JsonlStore(Q.ANSWERS_PATH, writable=False))   # reading is fine
        self.assertEqual(os.path.exists(Q.ANSWERS_PATH), existed)

    def test_dry_run_cli_guards(self):
        with self.assertRaises(SystemExit):
            D.parse_args(["--side", "holdout"])                           # the hold-out needs --count-only
        with self.assertRaises(SystemExit):
            D.parse_args(["--answers", "real", "--side", "holdout", "--count-only"])
        a = D.parse_args(["--side", "holdout", "--count-only"])
        self.assertTrue(a.count_only)


class TestBudgetStop(unittest.TestCase):
    MSG = {"message": "My flight was cancelled yesterday!"}

    def backend(self, usd, calls, client, **kw):
        with network_flag(False):
            return Q.RealBackend(WORDS, usd, calls, client=client, sleep=lambda s: None, **kw)

    def test_call_budget(self):
        c = FakeClient()
        with tempfile.TemporaryDirectory(prefix="p8_test_") as tmp:
            store = Q.JsonlStore(os.path.join(tmp, "answers_test.jsonl"))
            h = Q.Questions(self.backend(10.0, 2, c), store)
            h.ask("K8", self.MSG)
            h.ask("K8", self.MSG)                                         # saved: no call
            h.ask("K9", self.MSG)
            with self.assertRaises(Q.BudgetExceeded):
                h.ask("K16", self.MSG)
            self.assertEqual(c.calls, 2)
            b = h.backend.budget
            self.assertAlmostEqual(b.spent, 2 * (1000 * 0.1 + 100 * 0.5) / 1e6)
            with open(store.path, encoding="utf-8") as f:
                rows = [json.loads(x) for x in f]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["cost_usd"], 0.00015)
            self.assertEqual(rows[0]["source"], "real")
            self.assertEqual(rows[0]["status"], "yes")
            kw = c.kwargs[0]
            self.assertEqual((kw["model"], kw["reasoning"], kw["text"]["format"]["strict"]),
                             ("gpt-6-luna", {"effort": "low"}, True))

    def test_dollar_budget_stops_before_the_call(self):
        c = FakeClient()
        h = Q.Questions(self.backend(0.000001, 100, c))
        with self.assertRaises(Q.BudgetExceeded):
            h.ask("K8", self.MSG)
        self.assertEqual(c.calls, 0)
        c = FakeClient()
        h = Q.Questions(self.backend(0.0021, 100, c))                     # room for one worst-case call only
        h.ask("K8", self.MSG)
        with self.assertRaises(Q.BudgetExceeded):
            h.ask("K9", self.MSG)
        self.assertEqual(c.calls, 1)
        self.assertLessEqual(h.backend.budget.spent, 0.0021)

    def test_budget_stop_is_never_a_fact_value(self):
        c = FakeClient()
        h = Q.Questions(self.backend(0.000001, 100, c))
        e = entry({"a": part("structure", "True"), "b": part("question", "ask('K8', 'my flight was cancelled')",
                                                             "K8")}, "a AND b")
        with self.assertRaises(Q.BudgetExceeded):
            ev(e, "airline", answers=h)

    def test_retries_and_bad_output(self):
        c = FakeClient(fail=2)
        h = Q.Questions(self.backend(10.0, 100, c))
        self.assertEqual(h.ask("K8", self.MSG)["status"], "yes")
        self.assertEqual(c.calls, 3)
        self.assertEqual(h.backend.budget.calls, 3)                       # failed attempts count against the budget
        c = FakeClient(fail=5)
        h = Q.Questions(self.backend(10.0, 100, c, attempts=2))
        with self.assertRaises(Q.RealCallFailed):
            h.ask("K8", self.MSG)
        h = Q.Questions(self.backend(10.0, 100, FakeClient(text="not json")))
        r = h.ask("K8", self.MSG)
        self.assertEqual(r["status"], "bad_output")
        with self.assertRaises(F.UseBlockingValue):
            Q.value_of(r)
        h = Q.Questions(self.backend(10.0, 100, FakeClient(text='{"answer": "yes", "quote": "invented words"}')))
        self.assertEqual(h.ask("K8", self.MSG)["status"], "quote_failed")


class TestStandIn(unittest.TestCase):

    def test_saved_judge_value_stands_in(self):
        e = entry({"a": part("structure", "True"), "b": part("question", "ask('K4', 'my wife')", "K4")}, "a AND b",
                  True)
        self.assertIs(ev(e, answers=Q.StandInAnswers({"f": False}))["value"], False)
        self.assertIs(ev(e, answers=Q.StandInAnswers({"f": True}))["value"], True)
        r = ev(e, answers=Q.StandInAnswers({"f": None}))
        self.assertEqual((r["value"], r["how"]), (True, "blocking_value"))
        e2 = entry({"c": part("question", "offer_kind(args['content'], 'cancelled', [], [])", "K12")}, "c", True)
        self.assertIs(ev(e2, args={"content": "x"}, answers=Q.StandInAnswers({"f": False}))["value"], False)


# ----------------------------------------------------------------------------------------------- the dry run core

def _rule(rid, action, facts, holds):
    """A rule-table entry; holds(values) -> bool over every combination of the facts."""
    import itertools
    rows = [{"action": action, "values": dict(zip(facts, vs)), "holds": holds(dict(zip(facts, vs)))}
            for vs in itertools.product([False, True], repeat=len(facts))]
    return {"id": rid, "actions": [action], "facts": list(facts), "rows": rows,
            "blocking_values": {f: [False] for f in facts}}


class TestDryRunCore(unittest.TestCase):
    """Exact counts on built cases: two conversations, three checks, hand-made facts and rules."""

    def setUp(self):
        self.doc = {"facts": {
            "fc": entry({"a": part("database", "args['ok'] == True")}, "a"),
            "fq": entry({"a": part("structure", "True"),
                         "b": part("question", "ask_first_yes('K4', [0, 1, 2])", "K4")}, "a AND b"),
            "fq2": entry({"a": part("structure", "True"), "b": part("question", "ask('K16', 2)", "K16")},
                         "a AND b"),
        }}
        self.tables = {"retail": D.Rules({"rules": [
            _rule("1", "cancel_pending_order", ["fq"], lambda v: v["fq"]),
            _rule("2", "cancel_pending_order", ["fc", "fq2"], lambda v: v["fc"] or v["fq2"]),
        ]})}
        v1 = FakeView([("user", "first message"), ("user", "my wife's order"), ("user", "cancel it please")])
        v2 = FakeView([("user", "first message"), ("user", "another text"), ("user", "cancel my trip")])
        st = built_state("retail")
        mk = lambda conv, ds, agent, view, ok: D.Case(ds, conv, agent, "retail", "cancel_pending_order",
                                                      {"ok": ok}, st, view)
        self.cases = [mk("A|c1", "stage_a.luna.tgr_frozen", "luna", v1, True),
                      mk("A|c1", "stage_a.luna.tgr_frozen", "luna", v1, False),
                      mk("B|c2", "stage_a.nano.tgr_frozen", "nano", v2, False),
                      D.Case("stage_a.nano.tgr_frozen", "B|c2", "nano", "retail", "think", {}, st, v2)]

    def run_all(self):
        passes = D.default_passes()
        totals = D.run_cases(self.cases, {"retail": self.doc}, self.tables, passes)
        return D.summarize(totals, passes, None, Q.load_questions()["price"], ["all", "strong", "weak", "paid"])

    def test_exact_counts(self):
        n = self.run_all()
        up = n["groups"]["all"]["modes"]["upper"]
        # K4 on the 3 user messages of each conversation; "first message" is the same text in both: one key.
        self.assertEqual(up["by_question"], {"K4": 5, "K16": 2})
        self.assertEqual(up["calls"], 7)
        self.assertEqual(up["per_conversation"]["max"], 4)
        self.assertEqual(up["calls_sum_per_conversation"], 8)              # the shared key counts in both
        ly = n["groups"]["all"]["modes"]["lazy_yes"]
        self.assertEqual(ly["by_question"], {"K4": 1, "K16": 2})           # first yes; fq2 needed only when fc false
        ln = n["groups"]["all"]["modes"]["lazy_no"]
        self.assertEqual(ln["by_question"], {"K4": 5, "K16": 2})
        self.assertEqual(n["by_fact"]["lazy_yes"]["fq2"]["skipped_lazy"], 1)  # check 1: fc true decides rule 2
        self.assertEqual(n["by_fact"]["upper"]["fq"]["keys"], 5)
        self.assertEqual(n["groups"]["strong"]["modes"]["upper"]["calls"], 4)
        self.assertEqual(n["groups"]["weak"]["modes"]["upper"]["calls"], 4)
        self.assertEqual(n["groups"]["paid"]["conversations"], 1)
        self.assertEqual(n["checks_by_dataset"], {"stage_a.luna.tgr_frozen": 2, "stage_a.nano.tgr_frozen": 2})
        self.assertEqual(n["network_events"], 0)
        self.assertEqual(n["unclear_values"]["every_no"], {})
        self.assertEqual(up["p12_hard_limit_usd"], 10.0)
        self.assertGreater(up["input_tokens_estimate"], 0)
        md = D.render_md(n, {"when": "now", "side": "dev", "datasets": ["x"], "manifest": "ok", "reach": []})
        for h in ("## Calls per group", "## Calls per question", "## Calls per fact", "Draft text for p12"):
            self.assertIn(h, md)

    def test_rules_decided(self):
        r = self.tables["retail"].rules_for("cancel_pending_order")[1]
        self.assertTrue(D.Rules.decided(r, {"fc": True}, "cancel_pending_order"))
        self.assertFalse(D.Rules.decided(r, {"fc": False}, "cancel_pending_order"))
        self.assertEqual(self.tables["retail"].facts_for("cancel_pending_order"), ["fc", "fq", "fq2"])
        self.assertEqual(self.tables["retail"].facts_for("think"), [])

    def test_upper_bound_claim_holds_for_the_fact_files(self):
        docs = {d: F.load_facts(d) for d in DOMAINS}
        self.assertEqual(D.questions_reach_check(docs), [])

    def test_real_rule_tables_load(self):
        for d in DOMAINS:
            t = D.Rules(D.load_rule_table(d))
            self.assertIn("user_explicitly_confirmed_pending_action" if d == "retail"
                          else "pending_database_change_details_listed_and_explicitly_confirmed",
                          t.facts_for("cancel_pending_order" if d == "retail" else "book_reservation"))


# ----------------------------------------------------------------------------------------------- p12 step 0: workers

class SlowFake(Q.FakeBackend):
    """A fake that sleeps a little per call (so threads overlap) and counts the calls per key."""

    def __init__(self, policy="yes", sleep=0.003, **kw):
        super().__init__(policy, **kw)
        self.sleep = sleep
        self.seen = collections.Counter()
        self.lock = threading.Lock()

    def answer(self, **kw):
        time.sleep(self.sleep)
        with self.lock:
            self.seen[kw["key"]] += 1
        return super().answer(**kw)


class SlowClient(FakeClient):
    def __init__(self, sleep=0.003, **kw):
        super().__init__(**kw)
        self.sleep = sleep
        self.lock = threading.Lock()

    def create(self, **kw):
        time.sleep(self.sleep)
        with self.lock:
            return super().create(**kw)


POOL = ["first message", "my wife's order", "cancel it please", "another text", "cancel my trip", "hello there",
        "it is for my brother", "please go ahead", "no wait", "that is all"]


def slow_passes():
    return [D.PassCounter("every_yes_exh", SlowFake("yes", exhaustive=True), lazy=False),
            D.PassCounter("every_no", SlowFake("no"), lazy=False),
            D.PassCounter("lazy_yes", SlowFake("yes"), lazy=True),
            D.PassCounter("lazy_no", SlowFake("no"), lazy=True)]


class TestWorkers(unittest.TestCase):
    """--workers: the same answers, counts and report as one worker; each key asked once; the budget stop holds."""

    def setUp(self):
        core = TestDryRunCore()
        core.setUp()
        self.doc, self.tables = {"retail": core.doc}, core.tables
        st = built_state("retail")
        self.units = []
        for i in range(16):                       # 16 conversations; texts overlap, so threads share keys
            texts = [POOL[(i + j) % len(POOL)] for j in range(3)]
            view = FakeView([("user", t) for t in texts])
            ds, agent = (("stage_a.luna.tgr_frozen", "luna") if i % 2 else ("stage_a.nano.tgr_frozen", "nano"))
            self.units.append([D.Case(ds, f"X|c{i}", agent, "retail", "cancel_pending_order", {"ok": ok}, st, view)
                               for ok in (True, False)])

    def summary(self, passes, totals):
        n = D.summarize(totals, passes, None, Q.load_questions()["price"], ["all", "strong", "weak", "paid"])
        md = D.render_md(n, {"when": "now", "side": "dev", "datasets": ["x"], "manifest": "ok", "reach": []})
        return n, md

    def test_same_answers_counts_and_report_as_one_worker(self):
        p1 = slow_passes()
        t1 = D.run_cases([c for u in self.units for c in u], self.doc, self.tables, p1)
        n1, md1 = self.summary(p1, t1)
        for workers in (2, 8):
            p8 = slow_passes()
            t8 = D.run_parallel(self.units, lambda u: u, self.doc, self.tables, p8, workers, window=3)
            n8, md8 = self.summary(p8, t8)
            self.assertEqual(md1, md8, workers)                 # same bytes
            self.assertEqual(n1, n8)
            for a, b in zip(p1, p8):
                self.assertEqual(sorted(a.hook.store.keys()), sorted(b.hook.store.keys()))
                strip = lambda r: {k: v for k, v in r.items() if k != "created"}
                self.assertEqual({k: strip(a.hook.store.get(k)) for k in a.hook.store.keys()},
                                 {k: strip(b.hook.store.get(k)) for k in b.hook.store.keys()})
                self.assertEqual(max(b.hook.backend.seen.values()), 1)     # no key asked twice
                self.assertEqual(len(b.hook.backend.seen), len(b.hook.store))
                self.assertEqual(dict(a.hook.stats.calls), dict(b.hook.stats.calls))
                self.assertEqual(dict(a.hook.stats.asks), dict(b.hook.stats.asks))
        self.assertGreater(n1["groups"]["all"]["modes"]["upper"]["calls"], 10)

    def test_one_key_asked_once_by_many_threads_at_the_same_time(self):
        fake = SlowFake("yes", sleep=0.05)
        h = Q.Questions(fake)
        msg = {"message": "My flight was cancelled yesterday!"}
        out = []
        ts = [threading.Thread(target=lambda: out.append(h.ask("K8", msg))) for _ in range(8)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(len(out), 8)
        self.assertEqual(fake.calls, 1)
        self.assertEqual(len({id(r) for r in out}), 1)
        self.assertEqual((h.stats.calls["K8"], h.stats.asks["K8"], h.stats.hits["K8"]), (1, 8, 7))

    def test_budget_stop_with_workers(self):
        st = built_state("retail")
        units = [[D.Case("stage_a.luna.tgr_frozen", f"Y|c{i}", "luna", "retail", "cancel_pending_order",
                         {"ok": False}, st, FakeView([("user", f"unique text {i} {j}") for j in range(3)]))]
                 for i in range(20)]
        client = SlowClient()
        with network_flag(False):
            backend = Q.RealBackend(WORDS, 10.0, 5, client=client, sleep=lambda s: None)
        passes = [D.PassCounter("real", backend, lazy=False)]
        with self.assertRaises(Q.BudgetExceeded):
            D.run_parallel(units, lambda u: u, self.doc, self.tables, passes, 8, window=4)
        self.assertEqual(client.calls, 5)                        # never more calls than the budget
        self.assertEqual(backend.budget.calls, 5)
        self.assertEqual(len(passes[0].hook.store), 5)          # each answer saved once
        self.assertTrue(backend.budget.stopped)
        with self.assertRaises(Q.BudgetExceeded):
            backend.budget.reserve(1)

    def test_dollar_stop_stays_fired(self):
        b = Q.Budget(0.0021, 100, {"input_per_m": 0.1, "output_per_m": 0.5})
        with self.assertRaises(Q.BudgetExceeded):
            b.reserve(10 ** 6)                                   # a big call would pass the budget
        with self.assertRaises(Q.BudgetExceeded):
            b.reserve(1)                                         # a small one would fit, but the stop stays
        self.assertEqual(b.calls, 0)

    def test_cli_workers_holdout_real_and_out(self):
        real = ["--answers", "real", "--approved", WORDS, "--max-usd", "1.97", "--max-calls", "3613"]
        a = D.parse_args(["--side", "holdout"] + real + ["--workers", "8", "--out", "x/p12_answers_holdout.md"])
        self.assertEqual((a.side, a.answers, a.workers), ("holdout", "real", 8))
        a = D.parse_args(real + ["--limit-convs", "50", "--workers", "8", "--out", "x/p12_answers_dev.md"])
        self.assertEqual((a.limit_convs, a.workers), (50, 8))
        for bad in (["--side", "holdout"],                                     # fake, no --count-only
                    ["--side", "holdout", "--count-only"] + real + ["--out", "x.md"],   # real + count-only
                    real,                                                       # real with p8's default --out
                    real + ["--out", D.DRYRUN_MD],
                    ["--workers", "0"]):
            with self.assertRaises(SystemExit, msg=bad):
                with contextlib.redirect_stderr(io.StringIO()):
                    D.parse_args(bad)
        self.assertEqual(D.parse_args([]).workers, 1)

    def test_real_mode_refuses_other_data_sets_before_any_client(self):
        with tempfile.TemporaryDirectory(prefix="p12_test_") as tmp:
            out = os.path.join(tmp, "x.md")
            base = ["--answers", "real", "--approved", WORDS, "--max-usd", "1", "--max-calls", "5", "--out", out]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(D.main(["--side", "holdout", "--datasets", "ours.p10_luna_train"] + base), 2)
                self.assertEqual(D.main(["--datasets", "ours.p10_luna_val"] + base), 2)
                self.assertEqual(D.main(["--datasets", "stage_a.nano.tgr_frozen"] + base), 2)
            self.assertFalse(os.path.exists(out))


_DRYRUN_CMD = [sys.executable, "-B", "-m", "scoring.v3_p8_dryrun", "--datasets",
               "stage_a.luna.tgr_frozen,partner.luna_train_v5", "--limit-convs", "2", "--verify-states", "5"]


class TestWorkersOnSavedData(unittest.TestCase):
    """The script itself on a few saved development conversations (fake answers, network blocked, own process):
    --workers 1 and --workers 4 write the same report, apart from the time line."""

    def test_same_report(self):
        with tempfile.TemporaryDirectory(prefix="p12_test_") as tmp:
            mds = []
            for w in (1, 4):
                out = os.path.join(tmp, f"w{w}.md")
                env = dict(os.environ, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1")
                r = subprocess.run(_DRYRUN_CMD + ["--workers", str(w), "--out", out], cwd=PC_DIR, env=env,
                                   capture_output=True, text=True, timeout=900)
                self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
                with open(out, encoding="utf-8") as f:
                    mds.append([ln for ln in f.read().splitlines() if not ln.startswith("Written by ")])
            self.assertEqual(mds[0], mds[1])
            self.assertTrue(any(ln.startswith("| all |") for ln in mds[0]))


if __name__ == "__main__":
    unittest.main()
