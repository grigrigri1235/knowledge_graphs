"""Tests for A16's dev-check scripts (scoring/v4_offline_eval.py, v4_dev_check.py, v4_dev_answers.py, v4_cases.py).
Fakes only: no LLM call, no network, no saved conversation is read.

Run from predicate_correctness/:
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v4_devcheck
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from scoring import v4_cases as C                                  # noqa: E402
from scoring import v4_dev_answers as DA                           # noqa: E402
from scoring import v4_dev_check as DC                             # noqa: E402
from scoring import v4_offline_eval as OE                          # noqa: E402
from state_tracker.v3 import questions as Q                        # noqa: E402


# ----------------------------------------------------------------------------------------------- fixtures
def arm(d="allow", f=None, asks=None, status=None, v4=None, serr=None, fix=None, parts=None, msg=None):
    out = {"d": d, "viol": [], "f": f or {}, "probs": {}, "serr": serr or [], "ferr": [], "fb": False,
           "unknown": 0, "v4": v4 or {}}
    if asks is not None:
        out["asks"] = asks
        out["status"] = status or {}
        out["parts"] = parts or {}
    if fix is not None:
        out["fix"] = fix
    if msg is not None:
        out["msg"] = msg
    return out


def row(i, main, standin, tool="cancel_pending_order", dom="retail", conv="c1"):
    return {"ck": f"ds|{conv}|{i}", "conv": conv, "i": i, "dom": dom, "tool": tool, "ds": "ds",
            OE.MAIN: main, OE.STANDIN: standin}


DOC2 = {"retail": {"facts": {
    "fx": {"combine": "a AND b", "blocking_value": False,
           "parts": {"a": {"source": "structure"}, "b": {"source": "question"}}},
}}}


class FakeHook:
    """A fake answers hook: statuses per (qid, wording, message text)."""

    def __init__(self, answers, default="no"):
        self.answers = answers
        self.default = default
        self.calls = []
        self.where = None

    def ask(self, qid, inputs, *, fact=None, part=None, wording=1):
        msg = inputs.get("message") or inputs.get("listing") or ""
        self.calls.append((qid, wording, msg))
        return {"status": self.answers.get((qid, wording, msg), self.answers.get((qid, wording), self.default))}


# ----------------------------------------------------------------------------------------------- offline eval
class TestRealFlags(unittest.TestCase):
    def test_zero_backends_need_nothing(self):
        for b in ("fake", "standin", "saved", "count"):
            self.assertIsNone(OE.check_real_flags(b, main_chat=False, approved=None, max_usd=None, max_calls=None))

    def test_approval_words_on_a_free_backend_refused(self):
        with self.assertRaises(Q.RealModeRefused):
            OE.check_real_flags("fake", main_chat=True, approved="the user approved the dev check", max_usd=1,
                                max_calls=10)

    def test_real_refused_without_main_chat(self):
        with self.assertRaises(Q.RealModeRefused):
            OE.check_real_flags("real", main_chat=False, approved="the user approved the dev check", max_usd=1,
                                max_calls=10)

    def test_real_refused_above_the_dev_limit(self):
        with self.assertRaises(Q.RealModeRefused):
            OE.check_real_flags("real", main_chat=True, approved="the user approved the dev check", max_usd=2.5,
                                max_calls=10)

    def test_real_refused_without_words_or_calls(self):
        for approved, calls in (("yes", 10), (None, 10), ("the user approved the dev check", None)):
            with self.assertRaises(Q.RealModeRefused):
                OE.check_real_flags("real", main_chat=True, approved=approved, max_usd=1, max_calls=calls)

    def test_real_accepted_with_every_flag(self):
        if Q.network_blocked():
            self.skipTest("this process blocks the network")
        with tempfile.TemporaryDirectory() as d:
            led = os.path.join(d, "ledger.jsonl")
            try:
                got = OE.check_real_flags("real", main_chat=True, approved="the user approved the dev check",
                                          max_usd="1.5", max_calls=100, ledger=led,
                                          questions=[os.path.join(d, "none.jsonl")])
            finally:
                OE.unlock_ledger(led)
        self.assertEqual(got, ("the user approved the dev check", 1.5, 100))

    def test_refused_class_is_v3s(self):
        self.assertIn(Q.RealModeRefused, OE.hard_stops())
        self.assertIn(Q.BudgetExceeded, OE.hard_stops())


class TestFakePolicy(unittest.TestCase):
    def test_words(self):
        self.assertEqual(OE.fake_policy("yes")("K1", {}), "yes")
        self.assertEqual(OE.fake_policy("yes")("K17", {}), "added")
        self.assertEqual(OE.fake_policy("no")("K17b", {}), "not_added")
        self.assertEqual(OE.fake_policy("unclear")("K17", {}), "unclear")
        with self.assertRaises(ValueError):
            OE.fake_policy("maybe")


class TestStoresAndAsks(unittest.TestCase):
    def test_merged_first_wins(self):
        with tempfile.TemporaryDirectory() as d:
            p4, p3 = os.path.join(d, "v4.jsonl"), os.path.join(d, "v3.jsonl")
            with open(p4, "w") as f:
                f.write(json.dumps({"key": "k1", "status": "yes"}) + "\n")
            with open(p3, "w") as f:
                f.write(json.dumps({"key": "k1", "status": "no"}) + "\n" + json.dumps({"key": "k2", "status": "no"})
                        + "\n" + '{"key": "half')
            recs, infos, origin = OE.merged_records([p4, p3, os.path.join(d, "none.jsonl")])
            self.assertEqual(recs["k1"]["status"], "yes")
            self.assertEqual(sorted(recs), ["k1", "k2"])
            self.assertEqual(infos[1]["partial_last_line"], 1)
            self.assertFalse(infos[2]["exists"])
            self.assertTrue(origin["k2"].endswith("v3.jsonl"))
            self.assertEqual(len(OE.memory_store(recs)), 2)

    def test_asks_since_filters_by_where(self):
        w1 = {"run_id": "r", "check": 1}
        hook = type("H", (), {})()
        hook.ask_lines = [{"key": "old", "where": w1},
                          {"key": "a", "qid": "K1", "fact": "f", "part": "b", "cached": False, "wording": 1,
                           "status": "unclear", "where": w1},
                          {"key": "x", "qid": "K3", "where": {"run_id": "r", "check": 2}, "status": "yes"},
                          {"key": "a2", "qid": "K1", "fact": "f", "part": "b", "cached": True, "wording": 2,
                           "status": "yes", "where": w1}]
        asks, status = OE.asks_since(hook, 1, w1)
        self.assertEqual([a[0] for a in asks], ["a", "a2"])
        self.assertEqual(asks[1][5], 2)
        self.assertEqual(status, {"a": "unclear", "a2": "yes"})

    def test_store_only_counts_missing(self):
        b = OE.StoreOnlyV4()
        b.where = "ck1"
        out = b.answer(qid="K1", key="k", fact="f", part="b", wording=2)
        self.assertTrue(out["bad_output"])
        self.assertEqual(b.missing[0]["where"], "ck1")


class FakeConv:
    def __init__(self, trace):
        self.trace = trace


class FakeTGR:
    """Appends one block entry per check to conv.v4_blocks (as the v4 guard does)."""

    def __init__(self, replace=False):
        self.seen = []
        self.replace = replace

    def set_given(self, judged):
        self.given = judged

    def _step(self, conv, step):
        self.seen.append(list(conv.v4_blocks))
        if self.replace:
            conv.v4_blocks = list(conv.v4_blocks) + [{"tiny": True}]
        else:
            conv.v4_blocks.append({"tiny": True})
        return {"action_allowed": False, "violated_rules": [{"rule_id": 30}], "feedback_text": "BLOCKED"}


class FakeCheck:
    history, msg, n_exec, past = [{"role": "user"}], {"role": "assistant"}, 0, []


class TestRunGuard(unittest.TestCase):
    def test_block_memory_is_kept_per_conversation(self):
        for replace in (False, True):
            g, blocks = FakeTGR(replace), []
            for _ in range(3):
                res = OE.run_guard_v4(g, FakeCheck(), {}, blocks, conv_cls=FakeConv,
                                      make_step_fn=lambda h, m, n: ("step", len(h)))
            self.assertEqual([len(x) for x in g.seen], [0, 1, 2])
            self.assertEqual(len(blocks), 3)
            self.assertEqual(res["decision"], "block")

    def test_short_v4(self):
        res = {"decision": "block", "feedback_text": "BLOCKED ...", "record": {
            "violated_rules": [{"rule_id": 30}], "v4": {"tiny_block": True},
            "v3": {"facts": {"f": {"value": False, "source": "question", "parts": {"b": {"value": False,
                                                                                       "source": "question"}}}},
                   "state_errors": [{"kind": "replay_mismatch"}]}}}
        out = OE.short_v4(res, asks=[["k", "K1", "f", "b", False, 1]], status={"k": "no"})
        self.assertEqual(out["viol"], ["30"])
        self.assertEqual(out["serr"], ["replay_mismatch"])
        self.assertEqual(out["msg"], "BLOCKED ...")
        self.assertEqual(out["parts"]["f"]["b"][0], False)
        self.assertEqual(out["status"], {"k": "no"})
        self.assertTrue(out["v4"]["tiny_block"])
        self.assertIsNone(OE.short_v4(None))

    def test_outputs_never_under_eval_v3(self):
        with self.assertRaises(RuntimeError):
            OE.outputs("saved", os.path.join(OE.paths.OUTPUT_DIR, "eval_v3"))
        out = OE.outputs("fake_yes")
        self.assertTrue(out["rows"].endswith("offline_fake_yes_rows.jsonl"))
        self.assertEqual(OE.tag_of("count", "no"), "count_no")
        self.assertEqual(OE.tag_of("saved", "yes"), "saved")

    def test_conv_rows_refuses_holdout(self):
        from scoring import v3_labels as L

        class C_:
            side, conv_key = "holdout", "ours.p10_luna_val|retail/1/0"
        with self.assertRaises(L.HoldOutData):
            OE.conv_rows(None, C_(), 0, None, None, [], [])

    def test_parse_args_limits(self):
        with self.assertRaises(SystemExit):
            OE.parse_args(["--workers", "9"])
        with self.assertRaises(SystemExit):
            OE.parse_args(["--limit", "51"])
        self.assertEqual(OE.parse_args([]).backend, "standin")

    def test_main_refuses_real_without_flags(self):
        self.assertEqual(OE.main(["--backend", "real"]), 2)


class TestFixCheck(unittest.TestCase):
    def test_no_capture_is_a_failure(self):
        self.assertFalse(OE.fix_check(object(), "retail", None)["ok"])
        self.assertFalse(OE.fix_check(object(), "retail", {"data": None})["ok"])

    def test_capture_wraps_feedback(self):
        import threading

        class G:
            def __init__(self):
                self._v3tls = threading.local()
                self._v3tls.data = {"tool": "t"}

            def _feedback(self, *a):
                return "text"
        g = OE.attach_capture(G())
        self.assertEqual(g._feedback(1, 2, [{"rule_id": 3}], 4, 5, 6, 7), "text")
        cap = OE.take_capture(g)
        self.assertEqual(cap["violated"], [{"rule_id": 3}])
        self.assertIsNone(OE.take_capture(g))


# ----------------------------------------------------------------------------------------------- dev check
class TestDevCheckMarks(unittest.TestCase):
    def test_base_qid(self):
        for q in ("K1", "K1b", "K1v4", "K1v4b"):
            self.assertEqual(DC.base_qid(q), "K1")
        self.assertEqual(DC.base_qid("K13b"), "K13")

    def test_tiny_ratio(self):
        rows = [row(i, arm("block"), arm("block" if i < 2 else "allow")) for i in range(3)]
        m = DC.mark_tiny_blocks(rows)
        self.assertEqual((m["tiny_blocks"], m["standin_blocks"]), (3, 2))
        self.assertTrue(m["pass"])                                  # 3 <= 1.5 x 2
        rows.append(row(3, arm("block"), arm("allow")))
        self.assertFalse(DC.mark_tiny_blocks(rows)["pass"])         # 4 > 3
        self.assertTrue(DC.mark_tiny_blocks([row(0, arm(), arm())])["pass"])
        self.assertEqual(DC.mark_tiny_blocks([row(0, arm(), None)])["checks"], 0)

    def test_unclear_share(self):
        asks = [[f"k{i}", "K1", "f", "b", False, 1] for i in range(100)]
        status = {f"k{i}": "no" for i in range(100)}
        status["k0"] = "unclear"
        status["k1"] = "quote_failed"
        rows = [row(0, arm(asks=asks, status=status), arm())]
        m = DC.mark_unclear(rows)
        self.assertEqual((m["tiny_calls"], m["unclear"]), (100, 2))
        self.assertTrue(m["pass"])
        status["k2"] = "bad_output"
        self.assertFalse(DC.mark_unclear(rows)["pass"])
        m = DC.mark_unclear(rows, missing_keys=["k3"])
        self.assertEqual(m["status"]["missing"], 1)
        self.assertEqual(m["by_question"]["K1"]["unclear"], 1)

    def test_unclear_counts_a_key_once(self):
        asks = [["k", "K1", "f", "b", False, 1], ["k", "K1", "g", "b", True, 1]]
        self.assertEqual(DC.mark_unclear([row(0, arm(asks=asks, status={"k": "yes"}), arm()),
                                          row(1, arm(asks=asks, status={"k": "yes"}), arm())])["tiny_calls"], 1)

    def test_two_keys(self):
        bad = arm(asks=[["k", "K1", "fx", "b", False, 1]], parts={"fx": {"a": [False, "structure", "value"],
                                                                        "b": [True, "question", "value"]}})
        good = arm(asks=[["k", "K1", "fx", "b", False, 1]], parts={"fx": {"a": [True, "structure", "value"],
                                                                         "b": [True, "question", "value"]}})
        m = DC.mark_two_keys([row(0, bad, arm()), row(1, good, arm())], DOC2)
        self.assertEqual(m["disagreements"], 1)
        self.assertFalse(m["pass"])
        self.assertEqual(m["by_fact"], {"fx": 1})
        self.assertTrue(DC.mark_two_keys([row(1, good, arm())], DOC2)["pass"])

    def test_state_errors(self):
        m = DC.mark_state_errors([row(0, arm(serr=["replay_mismatch"]), arm(serr=["replay_mismatch"]))])
        self.assertEqual(m["state_errors"], 2)
        self.assertFalse(m["pass"])
        self.assertTrue(DC.mark_state_errors([row(0, arm(), arm())])["pass"])

    def test_messages(self):
        ok = row(0, arm("block", fix={"ok": True, "problems": []}), arm())
        bad = row(1, arm("block", fix={"ok": False, "problems": ["generic step line: f"]}), arm())
        unchecked = row(2, arm("block"), arm())
        self.assertTrue(DC.mark_messages([ok, row(3, arm(), arm())])["pass"])
        m = DC.mark_messages([ok, bad, unchecked])
        self.assertEqual((m["blocks"], m["named"], m["unchecked"]), (3, 1, 1))
        self.assertFalse(m["pass"])
        self.assertIn("cancel_pending_order: generic step line", m["fail_patterns"])

    def test_validity(self):
        self.assertTrue(DC.validity({"counts": {"checks": 3}, "missing": []})["valid"])
        self.assertFalse(DC.validity({"counts": {"errors: v4": 1}})["valid"])
        self.assertFalse(DC.validity({"missing": [{"key": "k"}]})["valid"])

    def test_patterns_counts_only(self):
        asks = [["k1", "K1", "fx", "b", False, 1], ["k2", "K1b", "fx", "b", False, 2]]
        m = arm("block", f={"fx": [False, "question"]}, asks=asks,
                v4={"missing": {"fx": [{"line": "order id", "expected": "#W1"}]}})
        s = arm("allow", f={"fx": [True, "saved_judge"]})
        p = DC.patterns([row(0, m, s), row(1, arm("allow", f={"fx": [True, "question"]}, asks=asks),
                                            arm("allow", f={"fx": [True, "code"]}))], DOC2)
        self.assertEqual(p["by_question"]["K1"], {"disagree: tiny blocks": 1, "agree": 1})
        self.assertEqual(p["by_fact"]["fx"], {"disagree: tiny blocks": 1})
        self.assertEqual(p["decisions_by_tool"], {"tiny block, stand-in allow": {"cancel_pending_order": 1}})
        self.assertEqual(p["missing_lines_at_tiny_only_blocks"], {"order id": 1})
        self.assertNotIn("ds|c1", json.dumps(p))                     # no single check named

    def test_evaluate_and_render(self):
        rows = [row(0, arm("block", fix={"ok": True}, asks=[["k", "K1", "fx", "b", False, 1]],
                           status={"k": "no"}, f={"fx": [False, "question"]},
                           parts={"fx": {"a": [True, "structure", "v"], "b": [False, "question", "v"]}}),
                    arm("block", f={"fx": [False, "saved_judge"]}))]
        res = DC.evaluate(rows, {"backend": "fake", "run_id": "r", "counts": {}, "missing": []}, DOC2)
        self.assertTrue(res["all_pass"], res["marks"])
        md = DC.render(res, os.path.join(PC_DIR, "output", "x_rows.jsonl"))
        for k in ("D1", "D2", "D3", "D4", "D5", "Overall: **PASS**"):
            self.assertIn(k, md)


# ----------------------------------------------------------------------------------------------- dev answers
class TestDevAnswers(unittest.TestCase):
    def test_count_and_price(self):
        rows = [row(0, arm(asks=[["a", "K1", "f", "b", False, 1], ["b", "K3", "f", "b", True, 1]]), None, conv="c1"),
                row(1, arm(asks=[["a", "K1", "f", "b", True, 1], ["c", "K7b", "f", "b", False, 2]]), None, conv="c2")]
        p = DA.count_pass(rows, stored={"b"})
        self.assertEqual((p["asked_keys"], p["reused_keys"], p["new_keys"]), (3, 1, 2))
        self.assertEqual(p["new_by_question"], {"K1": 1, "K7": 1})
        self.assertEqual(p["max_per_conversation"], 2)       # c2: a (asked first in c1) and c
        pr = DA.price({"K1": 100, "K7": 100}, {"K1"})
        self.assertAlmostEqual(pr["usd"], 100 * 0.000046 * 1.25 + 100 * 0.000046, places=9)
        c = DA.combine({"yes": p, "no": DA.count_pass([row(0, arm(asks=[["d", "K8", "f", "b", False, 1]]), None)],
                                                      set())}, {"K1"})
        self.assertEqual(c["upper"]["calls"], 3)
        self.assertEqual(c["point"]["pass"], "yes")
        self.assertTrue(c["request"]["fits_limit"])
        self.assertIn("**3 calls", DA.render({"passes": {"yes": p}, "combined": c, "stores": []}))

    def test_few_shot(self):
        self.assertEqual(DA.few_shot_qids(None), set(DA.FEW_SHOT_FALLBACK))
        self.assertEqual(DA.few_shot_qids({"questions": {"K1": {"few_shot": [1]}, "K7": {"few_shot": []}}}), {"K1"})


# ----------------------------------------------------------------------------------------------- cases
QDOC = {"domain_texts": {"tools": {"retail": "RETAIL TOOLS", "airline": "AIRLINE TOOLS"}}, "questions": {
    "K1": {"inputs": [{"name": "listing", "type": "message"}, {"name": "replies", "type": "messages"},
                      {"name": "action", "type": "text", "from": "call"}]},
    "K13": {"inputs": [{"name": "message", "type": "message"}, {"name": "tools", "type": "text", "from": "domain"}]},
    "K17": {"inputs": [{"name": "agent_message", "type": "message", "optional": True},
                       {"name": "user_message", "type": "message", "optional": True}]},
    "K3": {"inputs": [{"name": "message", "type": "message"}, {"name": "items_action", "type": "choice"},
                      {"name": "verb", "type": "choice"}]}}}


class TestCases(unittest.TestCase):
    def test_load_and_sides(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "K17.jsonl"), "w") as f:
                f.write(json.dumps({"A": "a", "B": "b", "expect": "added", "kind": "yes_to_question"}) + "\n")
                f.write(json.dumps({"A": "a", "B": "", "expect": "not_said", "kind": "question_no_reply"}) + "\n\n")
                f.write("not json\n")
            with open(os.path.join(d, "K1.jsonl"), "w") as f:
                f.write(json.dumps({"A": "a", "B": ["yes"], "action": "x", "expect": "no"}) + "\n")
            with open(os.path.join(d, "SHA256SUMS"), "w") as f:
                f.write("x\n")
            cases, problems = C.load_cases(d)
            self.assertEqual(sorted(cases), ["K1", "K17"])
            self.assertEqual(len(problems), 1)
            self.assertEqual([C.side_of(c) for c in cases["K17"]], ["yes", "hard_no"])
            self.assertEqual(C.side_of(cases["K1"][0]), "hard_no")
            self.assertEqual(cases["K1"][0]["id"], "K1-001")
            self.assertEqual(C.side_of({"side": "easy", "expect": "no"}), "yes")

    def test_inputs(self):
        inp, many = C.case_inputs({"A": "list", "B": ["yes", "ok"], "action": "cancel #W1"}, QDOC["questions"]["K1"],
                                  QDOC)
        self.assertEqual(inp, {"listing": "list", "replies": ["yes", "ok"], "action": "cancel #W1"})
        self.assertIsNone(many)
        inp, many = C.case_inputs({"user_messages": ["first", "second"], "domain": "retail"},
                                  QDOC["questions"]["K13"], QDOC)
        self.assertEqual((inp["tools"], many, inp["message"]), ("RETAIL TOOLS", "message", ["first", "second"]))
        inp, _ = C.case_inputs({"user_messages": ["only"], "domain": "airline"}, QDOC["questions"]["K13"], QDOC)
        self.assertEqual(inp["message"], "only")
        inp, _ = C.case_inputs({"A": "ask?", "B": ""}, QDOC["questions"]["K17"], QDOC)
        self.assertEqual(inp, {"agent_message": "ask?"})
        inp, _ = C.case_inputs({"A": "m", "items_action": "exchanged", "verb": "exchange"}, QDOC["questions"]["K3"],
                               QDOC)
        self.assertEqual(inp["verb"], "exchange")
        with self.assertRaises(ValueError):
            C.case_inputs({"A": "m"}, QDOC["questions"]["K3"], QDOC)
        with self.assertRaises(ValueError):
            C.case_inputs({"user_messages": ["x"]}, QDOC["questions"]["K13"], QDOC)

    def test_ask_case_first_yes_newest_first_and_reask(self):
        h = FakeHook({("K13", 1, "second"): "unclear", ("K13", 2, "second"): "no", ("K13", 1, "first"): "yes"})
        a = C.ask_case(h, "K13", {"message": ["first", "second"], "tools": "T"}, "message")
        self.assertEqual([c[2] for c in h.calls], ["second", "second", "first"])
        self.assertEqual(a["final"], "yes")
        self.assertEqual(a["asks"][0], {"status1": "unclear", "status2": "no"})
        h = FakeHook({("K1", 1): "unclear", ("K1", 2): "unclear"})
        a = C.ask_case(h, "K1", {"listing": "L"}, None)
        self.assertEqual((a["final"], a["first_wording"]), ("unclear", "unclear"))
        h = FakeHook({("K17", 1): "not_said"})
        self.assertEqual(C.ask_case(h, "K17", {"agent_message": "x"}, None)["final"], "not_said")

    def test_score_marks(self):
        def res(q, side, right, n):
            return [{"qid": q, "side": side, "right": i < right, "final": "yes", "kind": "k"} for i in range(n)]
        sc = C.score(res("K1", "yes", 28, 30) + res("K1", "hard_no", 30, 30))
        self.assertTrue(sc["by_question"]["K1"]["pass"])
        self.assertTrue(sc["all_pass"])
        sc = C.score(res("K1", "yes", 27, 30) + res("K1", "hard_no", 30, 30))
        self.assertFalse(sc["by_question"]["K1"]["pass"])
        self.assertEqual(sc["by_question"]["K1"]["wrong_by_kind"], {"yes: k": 3})
        sc = C.score(res("K3", "yes", 29, 29) + res("K3", "hard_no", 30, 30))
        self.assertFalse(sc["by_question"]["K3"]["pass"])           # fewer than 30 cases
        self.assertFalse(C.score([])["all_pass"])

    def test_run_cases_fake_hook(self):
        cases = {"K1": [{"id": "a", "A": "L", "B": ["yes"], "action": "x", "expect": "yes", "_qid": "K1"},
                        {"id": "b", "A": "L2", "B": ["no"], "action": "x", "expect": "no", "_qid": "K1"},
                        {"id": "c", "A": "L3", "expect": "no", "_qid": "K1"}],
                 "K99": [{"id": "d", "A": "x", "expect": "yes", "_qid": "K99"}]}
        h = FakeHook({("K1", 1, "L"): "yes"})
        out = C.run_cases(cases, h, QDOC, "run")
        self.assertEqual([r["right"] for r in out], [True, True, False, False])
        self.assertIn("required input 'replies'", out[2]["error"])
        self.assertIn("not in the questions file", out[3]["error"])
        self.assertEqual(h.where["step"], "CASES")
        md = C.render(C.score(out), {"backend": "fake", "policy": "expect", "cases": 4, "problems": []})
        self.assertIn("shape check", md)

    def test_main_refuses_real(self):
        self.assertEqual(C.main(["--backend", "real", "--max-usd", "1", "--max-calls", "5"]), 2)


class TestCasesWithQuestionsV4(unittest.TestCase):
    """The real QuestionsV4 hook with A3's fake backend, on the merged questions file (skipped until it exists)."""

    def test_expect_policy_scores_everything(self):
        path = os.path.join(PC_DIR, "state_tracker", "v4", "questions_v4.json")
        if not os.path.isfile(path):
            self.skipTest("state_tracker/v4/questions_v4.json is not merged yet")
        QV4 = OE._QV4()
        doc = QV4.load_questions_v4(path)
        cases, _ = C.load_cases(C.CASES_DIR)
        cases = {q: v[:4] for q, v in cases.items() if q in doc["questions"]}
        hook, _, exp = C.make_case_hook("fake", "expect", doc, None, "")
        out = C.run_cases(cases, hook, doc, "t", exp)
        errs = [r for r in out if r["error"]]
        self.assertEqual(errs, [])
        self.assertTrue(all(r["right"] for r in out), [r for r in out if not r["right"]][:3])


# ----------------------------------------------------------------------------------------------- the shared dev ledger
WORDS = "the user approved the dev check"


class _Resp:
    def __init__(self, text='{"answer": "no", "quote": "", "missing": ""}', tin=1000, tout=100):
        from types import SimpleNamespace as NS
        self.usage = NS(input_tokens=tin, output_tokens=tout, output_tokens_details=NS(reasoning_tokens=0),
                        input_tokens_details=NS(cached_tokens=0))
        self.output_text = text
        self.status = "completed"


class FakeClient:
    """A fake OpenAI client (no network): records, at each call, how many reserve lines the ledger already has."""

    def __init__(self, ledger, fail_first=0):
        self.ledger = ledger
        self.fail_first = fail_first
        self.seen_reserves = []
        self.responses = self

    def create(self, **_):
        self.seen_reserves.append(_ledger_kinds(self.ledger).count("reserve"))
        if self.fail_first > 0:
            self.fail_first -= 1
            raise ConnectionError("fake transient error")
        return _Resp()


def _ledger_kinds(path):
    if not os.path.isfile(path):
        return []
    with open(path) as f:
        return [json.loads(x)["kind"] for x in f if x.strip()]


def _write_ledger(path, calls, usd_each):
    with open(path, "w") as f:
        for i in range(calls):
            f.write(json.dumps({"kind": "reserve", "rid": f"old:{i}", "run_id": "old", "usd": 0.01}) + "\n")
            f.write(json.dumps({"kind": "spend", "rid": f"old:{i}", "run_id": "old", "usd": usd_each}) + "\n")


class TestDevLedger(unittest.TestCase):
    """The $2 / 5,100-call dev limits hold across all v4 dev runs (fake client and backend only; no network)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.led = os.path.join(self.tmp.name, "dev_spend_ledger.jsonl")
        self.qfiles = [os.path.join(self.tmp.name, "questions_answers_v4.jsonl"),
                       os.path.join(self.tmp.name, "answers.jsonl")]
        from unittest import mock
        self.net = mock.patch.object(Q, "network_blocked", lambda: False)    # check_real_mode's own check only
        self.net.start()

    def tearDown(self):
        self.net.stop()
        OE.unlock_ledger(self.led)
        self.tmp.cleanup()

    def flags(self, usd=2.0, calls=5100, info=None):
        return OE.check_real_flags("real", main_chat=True, approved=WORDS, max_usd=usd, max_calls=calls,
                                   ledger=self.led, questions=self.qfiles, info=info)

    def backend(self, got, run_id, client):
        QV4 = OE._QV4()
        be = QV4.RealBackendV4(got[0], got[1], got[2], approval_flag=True, client=client, sleep=lambda s: None)
        return OE.install_ledger(be, self.led, run_id)

    def ask(self, be):
        return be.answer(qid="K1", prompt={"system": "s" * 400, "user": "u" * 400},
                         schema={"properties": {"answer": {"enum": ["yes", "no", "unclear"]}}}, schema_name="x",
                         answers=("yes", "no", "unclear"))

    def test_refused_above_the_limits_outright(self):
        for usd, calls in ((2.01, 10), (1.0, 5101)):
            with self.assertRaises(Q.RealModeRefused):
                self.flags(usd, calls)
        self.assertFalse(OE.ledger_locked(self.led))

    def test_empty_ledger_gives_the_full_limits(self):
        info = {}
        self.assertEqual(self.flags(info=info), (WORDS, 2.0, 5100))
        self.assertEqual((info["spent_usd"], info["used_calls"]), (0.0, 0))
        self.assertTrue(OE.ledger_locked(self.led))

    def test_earlier_runs_cut_this_runs_budget(self):
        _write_ledger(self.led, 5000, 0.0003)                 # 5,000 calls, $1.50
        got = self.flags()
        self.assertEqual(got[2], 100)
        self.assertAlmostEqual(got[1], 0.5, places=6)

    def test_answer_files_count_too(self):
        with open(self.qfiles[1], "w") as f:                  # the cases run's answers: $1.20 in 3 lines
            for _ in range(3):
                f.write(json.dumps({"key": "k", "cost_usd": 0.4, "spent_usd": 0.4}) + "\n")
        info = {}
        got = self.flags(info=info)
        self.assertAlmostEqual(got[1], 0.8, places=6)
        self.assertEqual(got[2], 5097)
        self.assertEqual(info["questions_lines"], 3)

    def test_nothing_left_refused(self):
        _write_ledger(self.led, 4, 0.5)                       # $2.00 spent
        with self.assertRaises(Q.RealModeRefused):
            self.flags(1.0, 10)
        self.assertFalse(OE.ledger_locked(self.led))
        os.remove(self.led)
        _write_ledger(self.led, 5100, 0.0)                    # every call used
        with self.assertRaises(Q.RealModeRefused):
            self.flags(1.0, 10)

    def test_open_and_cut_lines_count_in_full(self):
        with open(self.led, "w") as f:                        # a call that never wrote its spend, then a cut line
            f.write(json.dumps({"kind": "reserve", "rid": "r:1", "run_id": "r", "usd": 0.25}) + "\n")
            f.write('{"kind": "reserve", "rid": "r:2"')
        r = OE.DevLedger(self.led).read()
        self.assertEqual((r["calls"], r["open"], r["bad_lines"]), (2, 1, 1))
        self.assertAlmostEqual(r["usd"], 0.25 + OE.PARTIAL_LINE_USD)

    def test_second_run_at_once_refused(self):
        import fcntl
        with open(self.led + ".lock", "a+") as other:          # another process's lock
            fcntl.flock(other.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(Q.RealModeRefused):
                self.flags()

    def test_install_needs_the_lock(self):
        QV4 = OE._QV4()
        be = QV4.RealBackendV4(WORDS, 1.0, 5, approval_flag=True, client=FakeClient(self.led))
        with self.assertRaises(Q.RealModeRefused):
            OE.install_ledger(be, self.led, "r")

    def test_reserve_is_written_before_the_call(self):
        if not os.path.isfile(os.path.join(PC_DIR, "state_tracker", "v4", "questions_v4.json")):
            self.skipTest("questions_v4.json not there")
        client = FakeClient(self.led, fail_first=1)
        be = self.backend(self.flags(), "run1", client)
        self.ask(be)                                          # one failed attempt, then one answer
        self.ask(be)
        self.assertEqual(client.seen_reserves, [1, 2, 3])     # the call's reserve line was there before the call
        self.assertEqual(_ledger_kinds(self.led), ["reserve", "spend"] * 3)
        r = OE.DevLedger(self.led).read()
        self.assertEqual((r["calls"], r["open"]), (3, 0))
        self.assertAlmostEqual(r["usd"], be.budget.spent, places=7)

    def test_limits_hold_across_runs(self):
        if not os.path.isfile(os.path.join(PC_DIR, "state_tracker", "v4", "questions_v4.json")):
            self.skipTest("questions_v4.json not there")
        _write_ledger(self.led, 5098, 0.0)                    # 2 calls left
        client = FakeClient(self.led)
        be = self.backend(self.flags(), "run2", client)
        self.assertEqual(be.budget.max_calls, 2)
        self.ask(be)
        self.ask(be)
        with self.assertRaises(Q.BudgetExceeded):
            self.ask(be)
        self.assertEqual(len(client.seen_reserves), 2)        # the refused call never reached the client
        self.assertEqual(OE.DevLedger(self.led).read()["calls"], 5100)
        OE.unlock_ledger(self.led)
        with self.assertRaises(Q.RealModeRefused):            # the next dev run: nothing left
            self.flags()

    def test_ledger_write_failure_stops_before_the_call(self):
        if not os.path.isfile(os.path.join(PC_DIR, "state_tracker", "v4", "questions_v4.json")):
            self.skipTest("questions_v4.json not there")
        client = FakeClient(self.led)
        be = self.backend(self.flags(), "run3", client)

        def broken(*a, **k):
            raise OSError("disk full")
        be.budget.ledger.reserve = broken
        with self.assertRaises(Q.BudgetExceeded):
            self.ask(be)
        self.assertEqual(client.seen_reserves, [])


# ----------------------------------------------------------------------------------------------- v3's store: dev keys
class TestDevOnlyStore(unittest.TestCase):
    """v3's answers file is read line by line; only records of keys asked (dev keys) are ever kept."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p3 = os.path.join(self.tmp.name, "v3.jsonl")
        self.p4 = os.path.join(self.tmp.name, "v4.jsonl")
        with open(self.p3, "w") as f:
            f.write(json.dumps({"key": "kdev", "status": "yes", "input": {"m": "dev text"}}) + "\n")
            f.write(json.dumps({"key": "khold", "status": "no", "input": {"m": "HOLDOUT SECRET"}}) + "\n")
            f.write(json.dumps({"key": "kdev", "status": "no"}) + "\n")
            f.write("not json\n")
            f.write('{"key": "kcut", "input": "HOLDOUT')
        with open(self.p4, "w") as f:
            f.write(json.dumps({"key": "k4", "status": "yes"}) + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_nothing_kept_until_asked(self):
        s = OE.DevOnlyStore(self.p3)
        self.assertEqual(s.keys(), [])
        self.assertNotIn("SECRET", repr(vars(s)))
        self.assertEqual(s.get("kdev")["status"], "yes")      # the first line wins
        self.assertEqual(s.keys(), ["kdev"])
        self.assertNotIn("SECRET", repr(vars(s)))
        self.assertIsNone(s.get("kcut"))
        i = s.info
        self.assertEqual((i["lines"], i["indexed"], i["duplicate_keys"], i["bad_lines"], i["partial_last_line"]),
                         (4, 2, 1, 1, 1))
        self.assertNotIn("status", i)                          # no counts over non-dev answers
        with self.assertRaises(RuntimeError):
            s.put("x", {})

    def test_keep_set_filters_while_reading(self):
        s = OE.DevOnlyStore(self.p3, keep={"kdev"})
        self.assertIn("kdev", s)
        self.assertNotIn("khold", s)
        self.assertIsNone(s.get("khold"))
        self.assertEqual((s.info["not_kept"], s.info["indexed"]), (1, 1))

    def test_v3_file_never_loaded_whole(self):
        with self.assertRaises(RuntimeError):
            OE.read_records(OE.V3_STORE)                       # refused before the file is opened

    def test_count_hook_reads_v3_lazily(self):
        hook, _, info = OE.make_hook("count", policy="no", stores=(self.p4, self.p3))
        self.assertEqual(info["stores"][1]["read"], "lazy: dev keys only")
        self.assertEqual(hook.store.get("k4")["status"], "yes")
        self.assertEqual(hook.store.get("kdev")["status"], "yes")
        self.assertEqual(hook.store.second.keys(), ["kdev"])
        stored = OE.StoredKeys({"k4": {}}, hook.store.second)
        self.assertTrue("k4" in stored and "khold" in stored and "zz" not in stored)


if __name__ == "__main__":
    unittest.main()
