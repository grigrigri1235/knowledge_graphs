"""Tracker v3, part 9: tests of the v3 guard (guard/tgr_tracker_v3.py). Pass marks P9.1-P9.5 (preregistration.md).

No LLM call and no network: the runner's LLM client fails every call, TGR's own LLM judge method is replaced by a
counter that raises, and the tiny questions get fake answers only (questions.FakeBackend). Saved checks are read only
from the development data (fork/offline_v3.py side "dev"; hold-out conversations are skipped unread).

  P9.1  0 judge calls in every mode (TGR._judge and the runner's structured LLM call counted, both 0); the judge
        stand-in refuses when no values are given.
  P9.2  every fact has a value and a source (tiny fakes: always true / false; saved_judge: None only as
        "saved_unknown", where code does not decide).
  P9.3  a state error (replay mismatch, build error) and an evaluator error (FactEvalError, NotDefinedYet): the
        affected facts take the blocking value, counted.
  P9.4  eval v2's guard gives the saved records field by field (with v3 loaded and registered), the same records as in
        a fresh process without the v3 module, and the past-trace length (trace_len_before) of the saved records.
  P9.5  facts = v2, meaning = saved_judge reproduces the saved v2 records (Gate 0 fields and trace_len_before).
  Also: the three switches in every record; lazy = full decisions (fake answers and the stand-in); the rule
  builder's interface; a builder exception gives TGR's own message, counted; the simple message; FROZEN_SHA256.

Run from predicate_correctness/ (the runner copy needs the venv for τ-bench's tools):
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v3_guard -v \\
        > output/logs/v3_p9_<nn>_tests.log 2>&1
"""
from __future__ import annotations

import collections
import copy
import hashlib
import json
import os
import subprocess
import sys
import types
import unittest

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from fork import offline_v3 as O                                         # noqa: E402
from guard import tgr_tracker_v3 as G                                    # noqa: E402
from method_tgr import llm as tgr_llm                                    # noqa: E402  (runner copy)
from method_tgr import runtime as RT                                     # noqa: E402  (runner copy)
from repro_runtime import calls                                          # noqa: E402  (runner copy)
from scoring import v3_p9_run as RUN                                     # noqa: E402
from state_tracker import paths                                          # noqa: E402
from state_tracker.v3 import questions as Q                              # noqa: E402

CALLS: collections.Counter = collections.Counter()


class _NoLLM:
    """Any LLM call through the runner's client fails loudly."""
    model, max_output_tokens = "no-llm", 16000
    cache_dir = os.path.join(paths.OUTPUT_DIR, "_no_llm_never_written")

    def call(self, **_):
        CALLS["runner LLM client"] += 1
        raise AssertionError("an LLM call was attempted in a unit test")


def _judge_refused(self, *a, **k):
    CALLS["TGR._judge"] += 1
    raise AssertionError("TGR's LLM judge was called")


def _structured_refused(*a, **k):
    CALLS["method_tgr.llm.structured"] += 1
    raise AssertionError("an LLM call was attempted")


calls._llm = _NoLLM()

SAMPLE_DATASETS = ("stage_a.luna.tgr_tracker", "stage_a.nano.tgr_frozen", "stage_a.nano.tgr_tracker",
                   "ours.p10_nano_train", "partner.nano_train", "stage_b")
SAMPLE_CONVS = 2                     # conversations per data set
V2_DATASETS = ("stage_a.luna.tgr_tracker", "stage_a.nano.tgr_tracker", "ours.p10_luna_train", "ours.p10_nano_train")
V2_CONVS = 3
_S: dict = {}


def sample_checks(datasets=SAMPLE_DATASETS, n_convs=SAMPLE_CONVS, v2_only=False):
    """The checks of the first n development conversations of each data set (in order), with their conversation."""
    out = []
    for d in datasets:
        k = 0
        for conv in O.iter_conversations([d]):
            if conv.side != O.DEV:
                continue
            if v2_only and conv.saved_guard != "tgr_tracker":
                continue
            k += 1
            if k > n_convs:
                break
            out += [(conv, ch) for ch in conv.checks()]
    return out


def judged_of(ch):
    j = ch.saved_judge()
    return {} if j is None else j


def setUpModule():
    RT.TGR._judge, _S["judge"] = _judge_refused, RT.TGR._judge
    tgr_llm.structured, _S["structured"] = _structured_refused, tgr_llm.structured
    Q.block_network()
    G.register()
    _S["checks"] = sample_checks()
    _S["v2"] = sample_checks(V2_DATASETS, V2_CONVS, v2_only=True)


def tearDownModule():
    RT.TGR._judge = _S["judge"]
    tgr_llm.structured = _S["structured"]


_TINY: dict = {}


def tiny(domain, policy="yes", lazy=True, messages="frozen"):
    """A meaning = tiny guard with a fake answers hook (built once per domain, fake, lazy and messages)."""
    key = (domain, policy, lazy, messages)
    if key not in _TINY:
        _TINY[key] = G.build(domain, facts="v3", meaning="tiny", messages=messages, lazy=lazy,
                             answers=Q.Questions(Q.FakeBackend(RUN.mixed_policy if policy == "mixed" else policy)))
    return _TINY[key]


def run(tgr, ch, judged=None):
    return O.run_guard(tgr, ch.history, ch.msg, ch.n_exec, ch.past, judged_of(ch) if judged is None else judged)


def first_block(policy="unclear"):
    """A development check that the tiny-fake guard blocks, with its record (cached)."""
    key = ("block", policy)
    if key not in _S:
        for conv, ch in _S["checks"]:
            g = tiny(conv.domain, policy)
            rec = run(g, ch, {})
            if not rec.get("action_allowed", True) and rec["v3"]["facts"]:
                _S[key] = (conv, ch, rec)
                break
        else:
            raise AssertionError("no blocked check in the sample")
    return _S[key]


# ----------------------------------------------------------------------------------------------- switches
class TestSwitches(unittest.TestCase):
    def test_bad_switches_are_refused(self):
        hook = Q.Questions(Q.FakeBackend("yes"))
        for kw in ({"facts": "v4"}, {"meaning": "judge"}, {"messages": "nice"},
                   {"facts": "v2", "meaning": "tiny", "answers": hook},
                   {"facts": "v2", "messages": "rule"},
                   {"meaning": "tiny"},
                   {"meaning": "tiny", "answers": Q.StandInAnswers({})}):
            with self.subTest(kw=kw):
                with self.assertRaises(ValueError):
                    G.build("retail", **kw)

    def test_every_record_holds_the_switches(self):
        conv, ch = _S["checks"][0]
        nofact = next(((c, x) for c, x in _S["checks"] if not x.saved.get("circuit")), None)
        guards = [G.build(conv.domain, facts=f, meaning="saved_judge", messages=m)
                  for f, m in (("v3", "frozen"), ("v3", "simple"), ("v3", "rule"), ("v2", "frozen"), ("v2", "simple"))]
        guards.append(tiny(conv.domain, "yes"))
        for g in guards:
            for c, x in [(conv, ch)] + ([nofact] if nofact and nofact[0].domain == conv.domain else []):
                rec = run(g, x)
                self.assertEqual(rec["v3"]["switches"], g.switches)
                self.assertEqual(set(rec["v3"]["switches"]), {"facts", "meaning", "messages"})
                self.assertIn("lazy", rec["v3"])


# ----------------------------------------------------------------------------------------------- P9.1
class TestNoJudge(unittest.TestCase):
    def test_zero_judge_calls_in_every_mode(self):
        before = dict(CALLS)
        n = 0
        for conv, ch in _S["checks"][:60]:
            for name in ("v3", "v3_full", "v3_simple", "v3_v2facts"):
                O.decide(ch, name, judged=judged_of(ch))
                n += 1
            run(tiny(conv.domain, "mixed"), ch, {})
            n += 1
        self.assertGreater(n, 200)
        self.assertEqual(dict(CALLS), before)
        self.assertEqual(CALLS["TGR._judge"] + CALLS["method_tgr.llm.structured"] + CALLS["runner LLM client"], 0)

    def test_the_stand_in_refuses_without_values(self):
        g = ch = None
        for conv, x in _S["checks"]:
            if not x.judged:
                continue
            g = O.guard_for("v3_v2facts", conv.domain)
            if not run(g, x)["tracker"]["judge_skipped"]:
                ch = x
                break
        self.assertIsNotNone(ch, "no check where eval v2's tracker needs the judge")
        g.set_given(None)
        from repro_online.guards import make_step                        # runner copy
        step = make_step(list(ch.history), ch.msg, ch.n_exec)
        with self.assertRaises(G.JudgeCallRefused):
            g._step(RT.Conversation(trace=list(ch.past)), step)

    def test_class_order_never_reaches_tgr_judge(self):
        mro = G.TrackerTGRv3.__mro__
        self.assertLess(mro.index(G.TrackerTGR), mro.index(G._NoLLMJudge))
        self.assertLess(mro.index(G._NoLLMJudge), mro.index(RT.TGR))
        self.assertIn("_judge", G._NoLLMJudge.__dict__)


# ----------------------------------------------------------------------------------------------- P9.2
class TestFacts(unittest.TestCase):
    def test_every_fact_has_a_value_and_a_source_tiny(self):
        n = 0
        for policy in ("yes", "unclear", "mixed"):
            for conv, ch in _S["checks"][:80]:
                rec = run(tiny(conv.domain, policy), ch, {})
                v = rec["v3"]
                if v["facts"] is None:
                    continue
                self.assertEqual(sorted(v["facts"]), sorted(rec["judge"]))
                for name, f in v["facts"].items():
                    n += 1
                    self.assertIsInstance(f["value"], bool, (ch.ckey, name))
                    self.assertIn(f["source"], G.KINDS)
                    self.assertEqual(rec["judge"][name]["value"], f["value"])
                    self.assertEqual(rec["judge"][name]["source"], f["source"])
                    if f["source"] in ("lazy_skip", "blocking_value", "state_error", "fact_error"):
                        self.assertEqual(f["value"], G.load_checked_facts(conv.domain)["facts"][name]["blocking_value"])
                self.assertEqual(v["unknown"], [])
                self.assertEqual(rec["unknown_predicates"], [])
        self.assertGreater(n, 300)

    def test_saved_unknown_is_three_valued(self):
        """With every saved judge value unknown, a fact is None only where code does not decide it: then the
        answer yes and the answer no give different values."""
        n_unknown = n_code = 0
        for conv, ch in _S["checks"][:80]:
            g = O.guard_for("v3_full", conv.domain)
            names = sorted(ch.saved.get("judge") or {})
            rec = run(g, ch, {n: {"value": None, "evidence": ""} for n in names})
            v = rec["v3"]
            if v["facts"] is None:
                continue
            for name, f in v["facts"].items():
                if f["value"] is None:
                    n_unknown += 1
                    self.assertEqual(f["source"], "saved_unknown")
                    self.assertIn(name, v["unknown"])
                    vals = {}
                    for ans in (True, False):
                        r2 = run(g, ch, {name: {"value": ans, "evidence": ""}})
                        vals[ans] = r2["v3"]["facts"][name]["value"]
                    self.assertNotEqual(vals[True], vals[False], (ch.ckey, name))
                else:
                    self.assertIsInstance(f["value"], bool)
                    if "first_question" in f and f["source"] == "code":
                        n_code += 1                       # a question fact that code decided anyway
            self.assertEqual(sorted(v["unknown"]), sorted(rec["unknown_predicates"]))
        self.assertGreater(n_unknown, 0)


# ----------------------------------------------------------------------------------------------- P9.3
class TestStateErrors(unittest.TestCase):
    def _check_with_tool_output(self):
        for conv, ch in _S["checks"]:
            if ch.saved.get("circuit") and len(ch.saved.get("judge") or {}) >= 2 and any(
                    m.get("role") == "tool" for m in ch.history):
                return conv, ch
        raise AssertionError("no check with a tool output in the sample")

    def _assert_all_blocking(self, rec, domain, kind):
        doc = G.load_checked_facts(domain)
        v = rec["v3"]
        self.assertTrue(v["facts"])
        for name, f in v["facts"].items():
            self.assertEqual(f["source"], "state_error")
            self.assertEqual(f["value"], doc["facts"][name]["blocking_value"])
            self.assertEqual(rec["judge"][name]["value"], doc["facts"][name]["blocking_value"])
            self.assertEqual(f["problems"], [kind])
        self.assertEqual([e["kind"] for e in v["state_errors"]], [kind])

    def test_replay_mismatch_gives_the_blocking_values(self):
        conv, ch = self._check_with_tool_output()
        hist = copy.deepcopy(ch.history)
        i = max(k for k, m in enumerate(hist) if m.get("role") == "tool")
        hist[i]["content"] = "Error: a changed output that the replay does not give"
        g = G.build(conv.domain)
        n0 = g.counters["state_errors"]
        g.set_given(judged_of(ch))
        rec = O.run_guard(g, hist, ch.msg, ch.n_exec, ch.past, judged_of(ch))
        self._assert_all_blocking(rec, conv.domain, "replay_mismatch")
        self.assertEqual(g.counters["state_errors"], n0 + 1)
        self.assertEqual(rec["tracker"]["version"], G.TRACKER_VERSION)
        self.assertTrue(rec["tracker"]["lookup_errors"])

    def test_state_build_error_gives_the_blocking_values(self):
        conv, ch = self._check_with_tool_output()
        g = G.build(conv.domain)

        def broken(history, tool, args):
            raise RuntimeError("the state cannot be built")

        g.state_source = broken
        rec = run(g, ch)
        self._assert_all_blocking(rec, conv.domain, "state_build_error")
        self.assertEqual(g.counters["state_errors"], 1)

    def test_evaluator_errors_give_the_blocking_value(self):
        conv, ch = self._check_with_tool_output()
        names = sorted(ch.saved["judge"])
        doc = copy.deepcopy(G.load_checked_facts(conv.domain))
        bad1, bad2 = names[0], names[-1]
        e1 = doc["facts"][bad1]
        pid = next(iter(e1["parts"]))
        e1["parts"] = {pid: dict(e1["parts"][pid], source="arguments", expr="len(args)")}   # not True / False
        e1["combine"] = pid
        e2 = doc["facts"][bad2]
        pid2 = next(iter(e2["parts"]))
        e2["parts"][pid2] = dict(e2["parts"][pid2], expr=None)                             # NotDefinedYet
        g = G.build(conv.domain, facts_doc=doc)
        rec = run(g, ch)
        v = rec["v3"]
        errs = {e["fact"]: e["error"] for e in v["fact_errors"]}
        self.assertEqual(errs.get(bad1), "FactEvalError")
        if bad2 != bad1:
            self.assertEqual(errs.get(bad2), "NotDefinedYet")
        for name in {bad1, bad2}:
            self.assertEqual(v["facts"][name]["source"], "fact_error")
            self.assertEqual(v["facts"][name]["value"], doc["facts"][name]["blocking_value"])
        self.assertEqual(g.counters["fact_errors"], len({bad1, bad2}))
        others = [n for n in v["facts"] if n not in (bad1, bad2)]
        self.assertTrue(all(v["facts"][n]["source"] != "fact_error" for n in others))


# ----------------------------------------------------------------------------------------------- P9.4 / P9.5
_DIGEST_CODE = r"""
import hashlib, json, sys
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
from fork import offline_v3 as O
from repro_runtime import calls
class _NoLLM:
    model, max_output_tokens, cache_dir = "no-llm", 16000, "/nonexistent"
    def call(self, **_):
        raise AssertionError("LLM call")
calls._llm = _NoLLM()
from scoring import v3_p9_run as RUN
datasets, n_convs = json.loads(sys.argv[2])
out = {}
for d in datasets:
    k = 0
    for conv in O.iter_conversations([d]):
        if conv.side != O.DEV or conv.saved_guard != "tgr_tracker":
            continue
        k += 1
        if k > n_convs:
            break
        for ch in conv.checks():
            j = ch.saved_judge()
            rec = O.decide(ch, "v2", judged={} if j is None else j)["record"]
            out[ch.ckey] = hashlib.sha256(RUN.comparable(rec).encode("utf-8")).hexdigest()
print(json.dumps({"digests": out, "v3_loaded": "guard.tgr_tracker_v3" in sys.modules}))
"""


class TestV2Identical(unittest.TestCase):
    def test_eval_v2_guard_equals_the_saved_records(self):
        """P9.4 and P9.5 on the sample: eval v2's guard and the v2-facts guard give the saved v2 records."""
        n = 0
        for conv, ch in _S["v2"]:
            j = judged_of(ch)
            for name in ("v2", "v3_v2facts"):
                res = O.decide(ch, name, judged=j)
                rec = res["record"]
                cmp = O.compare_with_saved(ch, res)
                self.assertTrue(cmp["pass"], (name, ch.ckey, cmp["differs"]))
                self.assertEqual(rec["trace_len_before"], ch.saved["trace_len_before"], (name, ch.ckey))
                self.assertEqual(RUN.comparable(rec), RUN.comparable(ch.saved), (name, ch.ckey,
                                                                                  RUN.field_diffs(rec, ch.saved)))
                n += 1
        self.assertGreater(n, 100)

    def test_eval_v2_guard_is_the_same_without_the_v3_module(self):
        here = {ch.ckey: hashlib.sha256(RUN.comparable(O.decide(ch, "v2", judged=judged_of(ch))["record"])
                                        .encode("utf-8")).hexdigest() for _, ch in _S["v2"]}
        env = dict(os.environ, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1")
        p = subprocess.run([sys.executable, "-B", "-c", _DIGEST_CODE, PC_DIR, json.dumps([V2_DATASETS, V2_CONVS])],
                           capture_output=True, text=True, cwd=PC_DIR, env=env, timeout=1200)
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])
        got = json.loads(p.stdout.strip().splitlines()[-1])
        self.assertFalse(got["v3_loaded"])
        self.assertEqual(got["digests"], here)
        self.assertIn("guard.tgr_tracker_v3", sys.modules)

    def test_v2_facts_record_differs_only_by_the_v3_part(self):
        conv, ch = _S["v2"][0]
        a = O.decide(ch, "v2", judged=judged_of(ch))["record"]
        b = O.decide(ch, "v3_v2facts", judged=judged_of(ch))["record"]
        self.assertEqual(set(b) - set(a), {"v3"})
        self.assertEqual(b["v3"]["facts"], None)
        self.assertEqual(RUN.comparable(a), RUN.comparable(b))


# ----------------------------------------------------------------------------------------------- lazy = full
class TestLazy(unittest.TestCase):
    def test_lazy_equals_full_with_fake_answers(self):
        totals = collections.Counter()
        for policy in ("yes", "no", "unclear", "mixed"):
            guards = {(d, lz): tiny(d, policy, lazy=lz) for d in paths.DOMAINS for lz in (True, False)}
            last, ws = None, None
            for conv, ch in _S["checks"]:
                if conv is not last:                      # one walk per conversation (checks are in order)
                    last, ws = conv, RUN.WalkStates(conv, collections.Counter(), verify_every=5)
                out = {}
                for lz in (True, False):
                    g = guards[(conv.domain, lz)]
                    g.state_source = ws
                    try:
                        out[lz] = run(g, ch, {})
                    finally:
                        g.state_source = None
                a, b = out[True], out[False]
                self.assertEqual(a["action_allowed"], b["action_allowed"], (policy, ch.ckey))
                self.assertEqual([r["rule_id"] for r in a["violated_rules"]],
                                 [r["rule_id"] for r in b["violated_rules"]], (policy, ch.ckey))
                self.assertEqual(a.get("margin"), b.get("margin"), (policy, ch.ckey))
                if a["v3"]["facts"]:
                    la = sum(a["v3"]["questions"]["asked"].values())
                    fa = sum(b["v3"]["questions"]["asked"].values())
                    self.assertLessEqual(la, fa)
                    self.assertEqual(b["v3"]["questions"]["skipped_facts"], [])
                    totals[f"{policy} asks lazy"] += la
                    totals[f"{policy} asks full"] += fa
                    totals[f"{policy} facts skipped"] += len(a["v3"]["questions"]["skipped_facts"])
                    for n in a["v3"]["questions"]["skipped_facts"]:
                        self.assertEqual(a["v3"]["facts"][n]["source"], "lazy_skip")
                totals[f"{policy} checks"] += 1
        print("\nlazy vs full (fake answers, sample):", json.dumps(dict(sorted(totals.items()))))
        self.assertTrue(any(totals[f"{p} facts skipped"] for p in ("yes", "no", "unclear", "mixed")))

    def test_lazy_equals_full_with_the_stand_in(self):
        n = 0
        for conv, ch in _S["checks"]:
            j = judged_of(ch)
            a = O.decide(ch, "v3", judged=j)
            b = O.decide(ch, "v3_full", judged=j)
            self.assertEqual((a["decision"], [r["rule_id"] for r in a["violated_rules"]]),
                             (b["decision"], [r["rule_id"] for r in b["violated_rules"]]), ch.ckey)
            n += 1
        self.assertGreater(n, 50)

    def test_rule_decided(self):
        rule = {"rows": [{"action": "x", "values": {"a": False, "b": False}, "holds": False},
                         {"action": "x", "values": {"a": False, "b": True}, "holds": True},
                         {"action": "x", "values": {"a": True, "b": False}, "holds": True},
                         {"action": "x", "values": {"a": True, "b": True}, "holds": True}]}     # a OR b
        self.assertTrue(G.rule_decided(rule, {"a": True}, "x"))
        self.assertFalse(G.rule_decided(rule, {"a": False}, "x"))
        self.assertFalse(G.rule_decided(rule, {"a": None}, "x"))
        self.assertTrue(G.rule_decided(rule, {"a": False, "b": False}, "x"))


# ----------------------------------------------------------------------------------------------- messages
class _FakeBuilder:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def build_message(self, domain, tool, args, violated_rules, facts, state, view, rule_table, rule_set):
        self.calls.append({"domain": domain, "tool": tool, "args": args, "violated_rules": violated_rules,
                           "facts": facts, "state": state, "view": view, "rule_table": rule_table,
                           "rule_set": rule_set})
        if self.fail:
            raise KeyError("a builder bug")
        return f"RULE MESSAGE for {tool}"


class TestMessages(unittest.TestCase):
    def _with_builder(self, builder):
        mod = types.ModuleType(G.FEEDBACK_MODULE)
        mod.build_message = builder.build_message
        old = sys.modules.get(G.FEEDBACK_MODULE)
        sys.modules[G.FEEDBACK_MODULE] = mod
        return old

    def _restore(self, old):
        if old is None:
            sys.modules.pop(G.FEEDBACK_MODULE, None)
        else:
            sys.modules[G.FEEDBACK_MODULE] = old

    def test_rule_message_uses_the_builder_with_the_fixed_interface(self):
        conv, ch, frozen = first_block("unclear")
        b = _FakeBuilder()
        old = self._with_builder(b)
        try:
            g = tiny(conv.domain, "unclear", messages="rule")
            rec = run(g, ch, {})
        finally:
            self._restore(old)
        self.assertFalse(rec["action_allowed"])
        self.assertEqual(rec["feedback_text"], f"RULE MESSAGE for {rec['name']}")
        self.assertEqual(rec["v3"]["message"], {"mode": "rule", "built": "rule", "fallback": False})
        self.assertEqual(len(b.calls), 1)
        c = b.calls[0]
        self.assertEqual(c["domain"], conv.domain)
        self.assertEqual(c["tool"], rec["name"])
        self.assertEqual(c["args"], ch.args)
        self.assertEqual(c["violated_rules"], rec["violated_rules"])
        self.assertEqual(sorted(c["facts"]), sorted(rec["judge"]))
        for name, r in c["facts"].items():
            self.assertIn("value", r)
            self.assertIn("parts", r)
            self.assertEqual(r["value"], rec["judge"][name]["value"])
            self.assertEqual(r["v3_source"], rec["v3"]["facts"][name]["source"])
            self.assertIn(r["v3_source"], G.KINDS)
        self.assertTrue(hasattr(c["state"], "db") and c["state"].pending["tool"] == rec["name"])
        self.assertTrue(hasattr(c["view"], "entries"))
        self.assertIn("rules", c["rule_table"])
        self.assertIn("predicates", c["rule_set"])
        self.assertEqual(rec["action_allowed"], frozen["action_allowed"])
        self.assertEqual(rec["margin"], frozen["margin"])

    def test_builder_exception_gives_tgr_message_counted(self):
        conv, ch, frozen = first_block("unclear")
        old = self._with_builder(_FakeBuilder(fail=True))
        try:
            g = tiny(conv.domain, "unclear", messages="rule")
            n0 = g.counters["message_fallbacks"]
            rec = run(g, ch, {})
        finally:
            self._restore(old)
        self.assertEqual(rec["feedback_text"], frozen["feedback_text"])
        self.assertEqual(g.counters["message_fallbacks"], n0 + 1)
        self.assertTrue(rec["v3"]["message"]["fallback"])
        self.assertIn("KeyError", rec["v3"]["message"]["error"])
        # TGR.step (the online path) does not retry or raise
        from repro_online.guards import make_step                        # runner copy
        old = self._with_builder(_FakeBuilder(fail=True))
        try:
            g.set_given({})
            out = g.step(RT.Conversation(trace=list(ch.past)), make_step(list(ch.history), ch.msg, ch.n_exec))
        finally:
            self._restore(old)
        self.assertEqual(out["attempts"], 1)
        self.assertEqual(out["feedback_text"], frozen["feedback_text"])

    def test_simple_message(self):
        conv, ch, frozen = first_block("unclear")
        rec = run(tiny(conv.domain, "unclear", messages="simple"), ch, {})
        self.assertEqual(rec["feedback_text"], G.simple_message(frozen["feedback_text"]))
        self.assertNotIn("are violated as things stand: do not", rec["feedback_text"])
        self.assertTrue(rec["feedback_text"].startswith("BLOCKED by policy guardrail."))
        t = ("BLOCKED by policy guardrail. x\n- [3] r (rule: a)\n    a = false: d\nWhat to do:\n"
             "- Rule(s) 3 are violated as things stand: do not repeat the same call. Proceed only if ...")
        self.assertEqual(G.simple_message(t), "BLOCKED by policy guardrail. x\n- [3] r (rule: a)\n    a = false: d")
        t2 = ("BLOCKED. y\nWhat to do:\n- Not established yet (a): ask the user and wait for the answer; then try "
              "again.\n- Rule(s) 3 are violated as things stand: do not repeat the same call. Proceed ...")
        self.assertEqual(G.simple_message(t2), "BLOCKED. y\nWhat to do:\n- Not established yet (a): ask the user "
                                               "and wait for the answer; then try again.")

    def test_messages_change_no_decision(self):
        conv, ch, frozen = first_block("unclear")
        for m in ("simple", "frozen"):
            rec = run(tiny(conv.domain, "unclear", messages=m), ch, {})
            self.assertEqual((rec["action_allowed"], rec["margin"], rec["violated_rules"]),
                             (frozen["action_allowed"], frozen["margin"], frozen["violated_rules"]))


# ----------------------------------------------------------------------------------------------- frozen inputs
class TestFrozen(unittest.TestCase):
    def test_table_matches_the_files_and_the_manifest(self):
        info = G.check_frozen_v3()
        from state_tracker.v3.frozen import read_manifest
        man = read_manifest()
        for rel, want in G.FROZEN_SHA256.items():
            if rel in man:
                self.assertEqual(want, man[rel], rel)
        self.assertTrue(all(info["sha256"][r] for r in G.FROZEN_SHA256 if r not in info["unrecorded"]))
        for rel in ("state_tracker/v3/facts_v3_retail.json", "state_tracker/v3/facts_v3_airline.json",
                    "state_tracker/v3/facts_format_v3.py", "guard/tgr_tracker.py"):
            self.assertIn(rel, G.FROZEN_SHA256)

    def test_a_changed_file_stops_the_run(self):
        table = dict(G.FROZEN_SHA256)
        table["state_tracker/v3/facts_v3_retail.json"] = "0" * 64
        with self.assertRaises(G.FrozenInputChangedV3):
            G.build("retail", frozen_table=table)
        table = dict(G.FROZEN_SHA256, **{"state_tracker/v3/no_such_file.json": "1" * 64})
        with self.assertRaises(G.FrozenInputChangedV3):
            G.check_frozen_v3(table)


# ----------------------------------------------------------------------------------------------- registry, network
class TestRegistry(unittest.TestCase):
    def test_variants_are_registered(self):
        for name in G.VARIANTS:
            self.assertIn(name, O.GUARDS)
        self.assertEqual(G.register(), list(G.VARIANTS))          # again: changes nothing
        conv, ch = _S["checks"][0]
        res = O.decide(ch, "v3", judged=judged_of(ch))
        self.assertIn(res["decision"], ("allow", "block"))
        name = G.register_tiny("v3_tiny_test", Q.Questions(Q.FakeBackend("no")))
        self.assertIn(name, O.GUARDS)
        self.assertEqual(O.guard_for(name, conv.domain).switches["meaning"], "tiny")

    def test_no_network_event(self):
        self.assertTrue(Q.network_blocked())
        for conv, ch in _S["checks"][:20]:
            run(tiny(conv.domain, "yes"), ch, {})
        self.assertEqual(Q.network_events(), [])


if __name__ == "__main__":
    unittest.main()
