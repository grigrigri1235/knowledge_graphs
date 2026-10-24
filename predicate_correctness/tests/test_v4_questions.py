"""Tests of state_tracker/v4/questions_v4.py: the file format, keys, render, quote check, parse, stores, hook, ask
log with `where`, real-mode refusal, no network. $0: fake backends only; the network is blocked for the process.

    cd predicate_correctness && ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v4_questions
"""
from __future__ import annotations

import copy
import json
import os
import socket
import tempfile
import threading
import unittest

from state_tracker.v3 import facts_format_v3 as F
from state_tracker.v3 import questions as Q
from state_tracker.v4 import questions_v4 as Q4

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "fixtures_v4", "questions_v4_fixture.json")
A4_OVERLAY = os.path.join(os.path.dirname(HERE), "output", "eval_v4", "overlays", "questions_A4.json")


def setUpModule():
    Q4.block_network()
    Q4.set_questions_path_v4(FIXTURE)


def tearDownModule():
    Q4.set_questions_path_v4(None)


def fx() -> dict:
    return Q4.load_questions_v4(FIXTURE)


def v3() -> dict:
    return Q.load_questions()          # the v3 questions file (texts only; never the v3 answers file)


class StoreAt(Q4.MemoryStore):
    """A memory store that claims a path (to test the refusals without opening any project file)."""

    def __init__(self, path, writable=True):
        super().__init__()
        self.path = path
        self.writable = writable


class TestReuse(unittest.TestCase):
    def test_exceptions_are_v3_classes(self):
        for name in ("BudgetExceeded", "NetworkBlocked", "RealModeRefused", "AnswerNotSaved", "RealCallFailed",
                     "QuestionsFileError"):
            self.assertIs(getattr(Q4, name), getattr(Q, name), name)
        self.assertFalse([n for n in dir(Q4) if isinstance(getattr(Q4, n), type)
                          and issubclass(getattr(Q4, n), BaseException) and getattr(Q4, n).__module__ != Q.__name__])

    def test_reused_objects(self):
        for name in ("MemoryStore", "JsonlStore", "SavedBackend", "Budget", "Stats", "StandInAnswers",
                     "check_real_mode", "block_network", "network_events", "normalize_text", "message_text",
                     "cache_key"):
            self.assertIs(getattr(Q4, name), getattr(Q, name), name)
        self.assertIs(Q4.FakeBackend, Q4.FakeBackendV4)
        self.assertIs(Q4.FakeBackendV3, Q.FakeBackend)

    def test_helpers_registered_v4_names_only(self):
        reg = F.registered_names()
        for name, src in (("ask_v4", "question"), ("ask_first_yes_v4", "question"), ("offer_kind_v4", "question"),
                          ("offer_amount_ok_v4", "structure"), ("insurance_stated_v4", "question")):
            self.assertIn(name, reg)
            self.assertEqual(reg[name].source, src)
        self.assertEqual(reg["ask_first_yes_v4"].keywords, ("focus", "items", "limit", "on_unclear"))
        for name in ("ask", "ask_first_yes", "offer_kind", "offer_amount_ok"):
            self.assertEqual(reg[name].func.__module__, Q.__name__)
        self.assertEqual(Q4.register_helpers_v4(), [h[0] for h in Q4.HELPERS_V4])     # again: no change


class TestDoc(unittest.TestCase):
    def test_fixture_ok(self):
        self.assertEqual(Q4.check_doc_v4(fx()), [])
        self.assertEqual(Q4.v3_identity_problems_v4(fx(), v3()), [])

    def test_changed_text_needs_new_hash(self):
        d = copy.deepcopy(fx())
        d["questions"]["K8"]["question"] += " x"
        self.assertTrue(any("text_sha256" in p for p in Q4.check_doc_v4(d)))
        d = copy.deepcopy(fx())
        d["questions"]["K4"]["second"]["question"] += " x"
        self.assertTrue(any("second text_sha256" in p for p in Q4.check_doc_v4(d)))
        d = copy.deepcopy(fx())
        d["systems"]["2"]["system"] += " x"
        self.assertTrue(any("system_sha256" in p for p in Q4.check_doc_v4(d)))

    def test_system1_must_be_v3(self):
        d = copy.deepcopy(fx())
        q = d["questions"]["K4"]
        q["question"] += " changed"
        q["text_sha256"] = Q.question_hash(q)
        self.assertEqual(Q4.check_doc_v4(d), [])
        self.assertTrue(Q4.v3_identity_problems_v4(d, v3()))

    def test_bad_on_unclear_and_missing_second(self):
        d = copy.deepcopy(fx())
        q = d["questions"]["K8"]
        q["on_unclear"] = "maybe"
        del q["second"]
        q["text_sha256"] = Q.question_hash(q)
        probs = " ".join(Q4.check_doc_v4(d))
        self.assertIn("missing fields ['second']", probs)

    def test_a4_overlay_in_merge_layout(self):
        if not os.path.exists(A4_OVERLAY):
            self.skipTest("A4 overlay not there")
        with open(A4_OVERLAY, encoding="utf-8") as f:
            a4 = json.load(f)
        doc = {k: val for k, val in v3().items() if k not in ("questions", "domain_texts")}
        doc.update(domain_texts=a4["domain_texts"], system_v2=a4["system_v2"],
                   questions={k: val for k, val in a4["questions"].items() if val})
        self.assertEqual(Q4.check_doc_v4(doc), [])
        d = Q4.normalize_doc_v4(doc)
        self.assertEqual(sorted(d["systems"]), ["1", "2"])
        self.assertEqual(set(d["systems"]["2"]["schema"]["properties"]), {"answer", "quote", "missing"})
        self.assertEqual(Q4.schema_v4("K17", d)[0]["properties"]["answer"]["enum"], list(Q4.K17_ANSWERS))
        for qid in Q4.question_ids_v4(d):
            for w in (1, 2):
                p = Q4.render_v4(qid, Q4.sample_inputs_v4(qid, d), d, w)
                self.assertEqual(p["system"], a4["system_v2"]["system"])
                self.assertNotRegex(p["user"], r"\{[a-z_]+\}", qid)       # every placeholder filled
        u = Q4.render_v4("K18", {"message": "I don't need it", "reason": "ordered by mistake"}, d)["user"]
        self.assertIn("the order was placed by accident", u)
        hook = Q4.QuestionsV4(Q4.FakeBackendV4("yes"), doc=doc)
        self.assertEqual(hook.ask("K3", {"message": "Are these all the items?", "items_action": "modified"}
                                  )["status"], "yes")


class TestKeysAndRender(unittest.TestCase):
    inputs = {"K4": {"message": "Can you look at my wife's order #W1234567?"},
              "K10": {"message": "I want some compensation for this."},
              "K12": {"reply": "I can send you a $100 certificate."}}

    def test_unchanged_questions_keep_v3_keys(self):
        h3 = Q.Questions(Q.FakeBackend("yes"), doc=v3())
        h4 = Q4.QuestionsV4(Q4.FakeBackendV4("yes"), doc=fx())
        for qid, inp in self.inputs.items():
            self.assertEqual(Q4.key_version_v4(qid, fx()), Q.key_version(qid, v3()))
            self.assertEqual(h4.key(qid, inp), h3.key(qid, inp), qid)
            self.assertNotEqual(h4.key(qid, inp, wording=2), h3.key(qid, inp))

    def test_system1_render_byte_equal_to_v3(self):
        for qid, inp in self.inputs.items():
            self.assertEqual(Q4.render_v4(qid, inp, fx()), Q.render(qid, inp, v3()), qid)

    def test_changed_question_key_differs(self):
        inp = {"message": "I need a refund to a gift card", "tools": "x"}
        k4 = Q4.key_v4("K13", inp, fx())
        k3 = Q.cache_key("K13", Q.key_version("K13", v3()), "gpt-6-luna", "low",
                         Q.normalized_inputs("K13", {"message": inp["message"], "tools": "x"}, v3()))
        self.assertNotEqual(k4, k3)
        self.assertEqual(Q4.key_version_v4("K13", fx()), "q3.s2")
        self.assertEqual(Q4.key_version_v4("K13", fx(), 2), "q1b.s2")

    def test_render_v2_few_shot_second_and_placeholders(self):
        p = Q4.render_v4("K1", {"listing": "Cancel order #W1?", "replies": ["ok do it"], "action": "cancel #W1"},
                         fx())
        self.assertEqual(p["system"], fx()["systems"]["2"]["system"])
        u = p["user"]
        self.assertTrue(u.startswith("Question K1 (version 4)."))
        self.assertIn("Made-up examples", u)
        self.assertIn('Answer: {"answer": "yes", "quote": "please take care of it", "missing": ""}', u)
        self.assertIn("at least this action: cancel #W1)", u)
        self.assertNotIn("The action:", u)                          # used inline, not shown again
        self.assertIn(Q4.MISSING_LINE, u)
        p2 = Q4.render_v4("K1", {"listing": "Cancel order #W1?", "replies": ["ok do it"], "action": "cancel #W1"},
                          fx(), wording=2)
        self.assertTrue(p2["user"].startswith("Question K1b (version 1)."))
        self.assertIn("carry out cancel #W1?", p2["user"])
        u3 = Q4.render_v4("K3", {"message": "Is that all?", "items_action": "exchanged"}, fx())["user"]
        self.assertIn("want to exchange?", u3)
        self.assertIn("The verb: modify", u3)                      # the example's choice
        u17 = Q4.render_v4("K17", {"user_message": "No thanks"}, fx())["user"]
        self.assertIn("Answer added, not_added, not_said or unclear", u17)
        self.assertNotIn("Message A, from the agent:\n<<<\n\n", u17)

    def test_schema_by_system_version(self):
        s1, n1 = Q4.schema_v4("K4", fx())
        self.assertEqual(set(s1["properties"]), {"answer", "quote"})
        s2, n2 = Q4.schema_v4("K17", fx())
        self.assertEqual(set(s2["properties"]), {"answer", "quote", "missing"})
        self.assertEqual(s2["properties"]["answer"]["enum"], list(Q4.K17_ANSWERS))
        self.assertNotEqual(n1, n2)


class TestQuote(unittest.TestCase):
    def test_pieces_split_at_any_punctuation(self):
        self.assertEqual(Q4.quote_pieces_v4('Yes, go ahead - cancel it! (the "blue" one); thanks: ok? — done'),
                         ["yes", "go ahead", "cancel it", "the", "blue", "one", "thanks", "ok", "done"])
        self.assertEqual(Q4.quote_pieces_v4("a. b"), [])                  # pieces < 2 characters dropped
        self.assertEqual(Q4.quote_pieces_v4("line one\nline two… three...four"),
                         ["line one", "line two", "three", "four"])

    def test_pieces_in_the_same_source(self):
        src = ["I want the blue one, please. Go ahead and cancel it.", "Thanks!"]
        self.assertTrue(Q4.quote_in_v4("blue one - go ahead", src))
        self.assertTrue(Q4.quote_in_v4("**Go ahead** and cancel", src))
        self.assertFalse(Q4.quote_in_v4("go ahead; thanks", src))         # pieces in two sources
        self.assertFalse(Q4.quote_in_v4("", src))
        self.assertFalse(Q.quote_in("blue one - go ahead", src))           # v3 does not split at '-' or ','

    def test_answer_status(self):
        q17 = fx()["questions"]["K17"]
        self.assertEqual(Q4.answer_status_v4("added", "Yes.", False, ["Yes."], q17), "added")
        self.assertEqual(Q4.answer_status_v4("added", "zz", False, ["Yes."], q17), "quote_failed")
        self.assertEqual(Q4.answer_status_v4("not_said", "", False, ["Hm"], q17), "not_said")
        self.assertEqual(Q4.answer_status_v4("yes", "Yes.", False, ["Yes."], q17), "bad_output")
        self.assertEqual(Q4.answer_status_v4("yes", "ok", False, ["ok"]), "yes")
        self.assertEqual(Q4.answer_status_v4("no", "", False, ["ok"]), "no")
        self.assertEqual(Q4.answer_status_v4("unclear", "", False, ["ok"]), "unclear")
        self.assertEqual(Q4.answer_status_v4("no", "", True, ["ok"]), "bad_output")

    def test_parse_keeps_missing(self):
        self.assertEqual(Q4.parse_answer_v4('{"answer": "no", "quote": "", "missing": "the zip"}'),
                         {"answer": "no", "quote": "", "missing": "the zip"})
        self.assertEqual(Q4.parse_answer_v4('{"answer": "yes", "quote": "ok"}')["missing"], "")
        self.assertIsNone(Q4.parse_answer_v4('{"answer": "no", "quote": "", "missing": 3}'))
        self.assertIsNone(Q4.parse_answer_v4('{"answer": "added", "quote": ""}'))
        self.assertEqual(Q4.parse_answer_v4('{"answer": "added", "quote": "x", "missing": ""}', Q4.K17_ANSWERS)
                         ["answer"], "added")
        self.assertIsNone(Q4.parse_answer_v4("not json"))


class TestHook(unittest.TestCase):
    def test_saved_status_rederived_with_v4_check(self):
        store = Q4.MemoryStore()
        h = Q4.QuestionsV4(Q4.FakeBackendV4("yes"), store, doc=fx())
        inp = {"message": "Please cancel it - I won't fly, my plans changed."}
        key = h.key("K16", inp)
        store.put(key, {"key": key, "qid": "K16", "answer": "yes", "quote": "cancel it, I won't fly",
                        "status": "quote_failed", "source": "real",
                        "raw": '{"answer": "yes", "quote": "cancel it, I won\'t fly", "missing": ""}'})
        rec = h.ask("K16", inp)
        self.assertEqual((rec["status"], rec["status_saved"]), ("yes", "quote_failed"))
        self.assertEqual(h.backend.calls, 0)
        self.assertEqual(store.get(key)["status"], "quote_failed")       # the store is never changed

    def test_record_fields_and_wording_2(self):
        h = Q4.QuestionsV4(Q4.FakeBackendV4("no", second="yes", missing="the reason"), doc=fx())
        h.where = {"run_id": "r1", "step": "B1v4", "domain": "airline", "task": 3, "trial": 0, "arm": "tgr", "check": 2}
        inp = {"message": "My flight was cancelled and I'm stuck."}
        r1 = h.ask("K8", inp, fact="f", part="b")
        r2 = h.ask("K8", inp, fact="f", part="b", wording=2)
        self.assertEqual((r1["status"], r1["wording"], r1["missing"], r1["qid_asked"]), ("no", 1, "the reason", "K8"))
        self.assertEqual((r2["status"], r2["wording"], r2["qid_asked"], r2["version"]), ("yes", 2, "K8b", "q1b.s2"))
        self.assertEqual(r1["where_first"]["check"], 2)
        self.assertNotEqual(r1["key"], r2["key"])
        self.assertEqual(h.backend.wordings, {1: 1, 2: 1})
        self.assertEqual(h.stats.calls["K8"], 1)
        self.assertEqual(h.stats.calls["K8b"], 1)
        with self.assertRaises(ValueError):
            h.ask("K8", inp, wording=3)

    def test_ask_log_has_where_cached_or_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "questions", "asks_shard1of1.jsonl")
            h = Q4.QuestionsV4(Q4.FakeBackendV4("yes"), doc=fx(), ask_log=path)
            w = {"run_id": "r", "step": "B1v4", "domain": "retail", "task": 7, "trial": 1, "arm": "tgr_tracker_v4",
                 "check": 0}
            h.where = w
            inp = {"message": "I need help with my husband's account"}
            h.ask("K4", inp, fact="request_is_for_another_user", part="c")
            h.where = dict(w, check=1)
            h.ask("K4", inp, fact="request_is_for_another_user", part="c")
            with open(path, encoding="utf-8") as f:
                lines = [json.loads(x) for x in f]
        self.assertEqual(len(lines), 2)
        self.assertEqual([x["cached"] for x in lines], [False, True])
        self.assertEqual([x["where"]["check"] for x in lines], [0, 1])
        self.assertTrue(all(set(Q4.WHERE_KEYS) <= set(x["where"]) for x in lines))
        self.assertEqual(lines[0]["key"], lines[1]["key"])
        self.assertEqual(h.ask_lines, lines)

    def test_where_per_thread_and_one_call_per_key(self):
        gate = threading.Event()

        def slow(qid, inputs, norm):
            gate.wait(5)
            return "yes"
        h = Q4.QuestionsV4(Q4.FakeBackendV4(slow), doc=fx())
        inp = {"message": "Cancel my trip please"}
        out = {}

        def run(i):
            h.where = {"check": i}
            out[i] = h.ask("K16", inp)
        ts = [threading.Thread(target=run, args=(i,)) for i in range(4)]
        for t in ts:
            t.start()
        gate.set()
        for t in ts:
            t.join(10)
        self.assertEqual(h.backend.calls, 1)
        self.assertEqual(sorted(x["where"]["check"] for x in h.ask_lines), [0, 1, 2, 3])
        self.assertEqual(sum(not x["cached"] for x in h.ask_lines), 1)
        self.assertEqual(len({r["key"] for r in out.values()}), 1)

    def test_chain_store_reads_v3_writes_v4(self):
        v3store, v4store = Q4.MemoryStore(), Q4.MemoryStore()
        h3 = Q.Questions(Q.FakeBackend("no"), v3store, doc=v3())
        inp = {"message": "Is my order shipped?"}
        h3.ask("K4", inp)
        fake = Q4.FakeBackendV4("yes")
        h = Q4.QuestionsV4(fake, Q4.ChainStore(v4store, v3store), doc=fx())
        rec = h.ask("K4", inp)                                  # unchanged key: v3's saved answer
        self.assertEqual((rec["status"], fake.calls), ("no", 0))
        self.assertEqual(h.ask_lines[-1]["store"], "v3")
        h.ask("K16", inp)                                       # changed question: asked, saved in v4 only
        self.assertEqual(fake.calls, 1)
        self.assertEqual((len(v3store), len(v4store)), (1, 1))
        self.assertEqual(h.ask_lines[-1]["store"], "v4")

    def test_refuses_project_answer_files(self):
        with self.assertRaises(Q.RealModeRefused):
            Q4.QuestionsV4(Q4.FakeBackendV4("yes"), StoreAt(Q4.V3_ANSWERS_PATH), doc=fx())
        with self.assertRaises(Q.RealModeRefused):
            Q4.QuestionsV4(Q4.FakeBackendV4("yes"), StoreAt(Q4.V4_ANSWERS_PATH), doc=fx())
        with self.assertRaises(Q.RealModeRefused):              # v3's file as the v4 (written) part of a chain
            Q4.QuestionsV4(Q4.FakeBackendV4("yes"), Q4.ChainStore(StoreAt(Q4.V3_ANSWERS_PATH), Q4.MemoryStore()),
                           doc=fx())
        Q4.QuestionsV4(Q4.FakeBackendV4("yes"), Q4.ChainStore(Q4.MemoryStore(), StoreAt(Q4.V3_ANSWERS_PATH)),
                       doc=fx())                                # read-only second part: fine
        Q4.QuestionsV4(Q4.FakeBackendV4("yes"), StoreAt(Q4.V4_ANSWERS_PATH, writable=False), doc=fx())

    def test_check_inputs(self):
        h = Q4.QuestionsV4(Q4.FakeBackendV4("added"), doc=fx())
        with self.assertRaises(ValueError):
            h.ask("K17", {})                                    # both optional, but one message is needed
        self.assertEqual(h.ask("K17", {"agent_message": "Insurance is included.", "user_message": "Great, book"}
                               )["status"], "added")
        with self.assertRaises(ValueError):
            h.ask("K4", {"nope": "x"})


class TestRealAndNetwork(unittest.TestCase):
    def test_real_refused_without_approval_flag(self):
        with self.assertRaises(Q.RealModeRefused) as cm:
            Q4.RealBackendV4("the user approved this step in words", 1.0, 10, doc=fx())
        self.assertIn("approval flag", str(cm.exception))

    def test_real_refused_when_network_blocked(self):
        self.assertTrue(Q4.network_blocked())
        with self.assertRaises(Q.RealModeRefused):
            Q4.RealBackendV4("the user approved this step in words", 1.0, 10, approval_flag=True, doc=fx())
        with self.assertRaises(Q.RealModeRefused):
            Q4.RealBackendV4("yes", 1.0, 10, approval_flag=True, doc=fx())

    def test_real_answer_uses_question_schema(self):
        """RealBackendV4.answer with a stand-in client (built without __init__: no network, no budget words)."""
        class Resp:
            output_text = '{"answer": "not_added", "quote": "No thanks", "missing": ""}'
            status = "completed"
            usage = None
        seen = {}

        class Client:
            class responses:
                @staticmethod
                def create(**kw):
                    seen.update(kw)
                    return Resp()
        b = Q4.RealBackendV4.__new__(Q4.RealBackendV4)
        b.doc = fx()
        b.budget = Q.Budget(1.0, 5, fx()["price"])
        b._client = Client()
        b._client_lock = threading.Lock()
        b.log = lambda s: None
        b.attempts = 1
        b.sleep = lambda s: None
        import collections
        b.usage = collections.Counter()
        h = Q4.QuestionsV4(b, doc=fx())
        h.backend.name = "real"
        rec = h.ask("K17", {"user_message": "No thanks"})
        self.assertEqual(rec["status"], "not_added")
        fmt = seen["text"]["format"]
        self.assertEqual(fmt["schema"]["properties"]["answer"]["enum"], list(Q4.K17_ANSWERS))
        self.assertIn("missing", fmt["schema"]["required"])
        self.assertEqual(seen["input"][0]["content"], fx()["systems"]["2"]["system"])

    def test_no_network(self):
        before = len(Q4.network_events())
        h = Q4.QuestionsV4(Q4.FakeBackendV4("yes"), doc=fx())
        for qid in Q4.question_ids_v4(fx()):
            h.ask(qid, Q4.sample_inputs_v4(qid, fx()))
        self.assertEqual(len(Q4.network_events()), before)
        with self.assertRaises(Q.NetworkBlocked):
            socket.create_connection(("127.0.0.1", 9), timeout=1)
        self.assertEqual(len(Q4.network_events()), before + 1)


if __name__ == "__main__":
    unittest.main()
