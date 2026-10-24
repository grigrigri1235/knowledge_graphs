"""Tracker v4: tests of the v4 guard (guard/tgr_tracker_v4.py, build agent A6).

$0: no LLM call and no network. TGR's own judge and the runner's LLM call raise if reached; tiny questions get fake
answers only (v3's FakeBackend, or small doubles). No saved conversation is read: every conversation is made up here
from τ-bench's own tool outputs (v1 data), as tests/test_v3_message_view.py does. The fact files are fixture COPIES of
the v3 fact files (tests/fixtures_v4/guard/facts_v4_<domain>.json): the real v4 files are built later by the merge
script, and these tests check the guard's machinery, not the v4 definitions.

Covered: build (switches, v3 freeze still checked, the v4 freeze flag, fact file checks, text facts); the record
(rec["v3"] with version v4, rec["v4"] with every field of code_change_map.md section 0.2 item 6, blocking_facts on
every block, asked_facts as v3); the escape (fires only after 2 tiny blocks on one write key; not after database-only
blocks, not on 1 + 1 different keys, not after the write ran, not across episodes or threads, not on a state error;
survives TGR.step retries and cap overrides); hard stops propagate (no silent block) and a failed real call is a fact
error "RealCallFailed"; lazy probe and counts; v4 keywords through the probe and the counting hook (re-asks with
status1 / status2, unclear allowed); v3's code reused unchanged; the v3 module untouched (sha).

Run from predicate_correctness/:
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v4_guard -v \\
        > output/logs/v4_A6_tests.txt 2>&1
"""
from __future__ import annotations

import collections
import copy
import hashlib
import json
import os
import sys
import threading
import types
import unittest
from unittest import mock

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from guard import tgr_tracker_v3 as V3                                   # noqa: E402
from guard import tgr_tracker_v4 as G                                    # noqa: E402
from method_tgr import llm as tgr_llm                                    # noqa: E402  (runner copy)
from method_tgr import runtime as RT                                     # noqa: E402  (runner copy)
from repro_online.guards import make_step                                # noqa: E402  (runner copy)
from state_tracker import state as S                                     # noqa: E402
from state_tracker.v3 import facts_format_v3 as F                        # noqa: E402
from state_tracker.v3 import questions as Q                              # noqa: E402

FIX_DIR = os.path.join(PC_DIR, "tests", "fixtures_v4", "guard")
FIX = {d: os.path.join(FIX_DIR, f"facts_v4_{d}.json") for d in ("retail", "airline")}
V3_GUARD_SHA256 = "3afdc3a5c0ab33d63bce874a6b171672f0f47718994bc719c2377ef3b434f377"   # output/eval_v3/v3_freeze.md
EMAIL = "olivia.ito5204@example.com"
ORDER = "#W5442520"                       # Olivia's pending order
ORDER2 = "#W3657213"                      # a second order id (another write key)
TRANSFER_FACT = "request_cannot_be_handled_within_scope"
CALLS: collections.Counter = collections.Counter()
_S: dict = {}


def _refuse(name):
    def f(*a, **k):
        CALLS[name] += 1
        raise AssertionError(f"{name} was called in a unit test")
    return f


def setUpModule():
    _S["judge"], RT.TGR._judge = RT.TGR._judge, _refuse("TGR._judge")
    _S["structured"], tgr_llm.structured = tgr_llm.structured, _refuse("method_tgr.llm.structured")
    Q.block_network()


def tearDownModule():
    RT.TGR._judge = _S["judge"]
    tgr_llm.structured = _S["structured"]


# ----------------------------------------------------------------------------------------------- made-up conversations
def history(domain, steps):
    """A made-up executed history; a call's output comes from τ-bench's own tool code."""
    db = S.load_db(domain)
    h = [{"role": "system", "content": "policy"}]
    for i, s in enumerate(steps):
        if s[0] == "user":
            h.append({"role": "user", "content": s[1]})
        elif s[0] == "agent":
            h.append({"role": "assistant", "content": s[1], "tool_calls": None})
        else:
            out = S.run_tool(domain, db, s[1], copy.deepcopy(s[2]))
            cid = f"call_{i}"
            h.append({"role": "assistant", "content": None, "tool_calls": [
                {"id": cid, "type": "function", "function": {"name": s[1], "arguments": json.dumps(s[2])}}]})
            h.append({"role": "tool", "tool_call_id": cid, "name": s[1], "content": out})
    return h


def call(tool, args, cid="c_pending"):
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": cid, "type": "function", "function": {"name": tool, "arguments": json.dumps(args)}}]}


BASE = [("user", "Hi, my email is " + EMAIL), ("call", "find_user_id_by_email", {"email": EMAIL}),
        ("user", f"Please cancel order {ORDER}, I no longer need it."),
        ("call", "get_order_details", {"order_id": ORDER}),
        ("agent", f"I will cancel order {ORDER} for the reason 'no longer needed'. Shall I go ahead?"),
        ("user", "Hmm, let me think.")]
CANCEL = {"order_id": ORDER, "reason": "no longer needed"}
BAD_REASON = {"order_id": ORDER, "reason": "I hate it"}
TRANSFER = {"summary": "The user wants a human."}


def base_history():
    if "hist" not in _S:
        _S["hist"] = history("retail", BASE)
    return list(_S["hist"])


def executed_after(h, tool, args):
    """h plus the call executed (its τ-bench output), as the episode loop adds an executed write."""
    return history("retail", BASE + [("call", tool, args)])


# answer policies (v3 fake backend)
P_NO = "no"                                                    # every answer no: K1 / K2 blocks are tiny; K13 no
P_DB = lambda qid, inputs, norm: "no" if qid == "K13" else "yes"         # noqa: E731  only code facts block


def hook(policy):
    return Q.Questions(Q.FakeBackend(policy))


def guard(policy=P_NO, lazy=True, messages="frozen", answers=None, **kw):
    return G.build("retail", meaning="tiny", messages=messages, lazy=lazy,
                   answers=answers if answers is not None else hook(policy), facts_path=FIX["retail"], **kw)


def check(g, conv, h, tool, args, index=3):
    return g._step(conv, make_step(h, call(tool, args), index))


def two_tiny_blocks(g, conv, h=None):
    h = base_history() if h is None else h
    recs = [check(g, conv, h, "cancel_pending_order", CANCEL) for _ in range(2)]
    return recs


# ----------------------------------------------------------------------------------------------- build
class TestBuild(unittest.TestCase):
    def test_build_both_domains(self):
        for d in ("retail", "airline"):
            g = G.build(d, facts_path=FIX[d])
            self.assertIsInstance(g, G.TrackerTGRv4)
            self.assertIsInstance(g, V3.TrackerTGRv3)
            self.assertEqual(g.switches["facts"], "v4")
            self.assertEqual(g.info["guard"], "tgr_tracker_v4")
            self.assertEqual(g.info["version"], "v4.p1.1")
            self.assertIn("frozen_sha256_v3", g.info)
            self.assertTrue(g.text_facts)
            self.assertIn(G.TRANSFER_FACTS[d], g.text_facts)
            self.assertIsNotNone(g.config)

    def test_bad_switches_are_refused(self):
        h = hook(P_NO)
        for kw in ({"facts": "v3"}, {"facts": "v2"}, {"meaning": "judge"}, {"messages": "nice"},
                   {"meaning": "tiny"}, {"meaning": "tiny", "answers": Q.StandInAnswers({})}):
            with self.subTest(kw=kw):
                with self.assertRaises(ValueError):
                    G.build("retail", facts_path=FIX["retail"], **kw)
        G.build("retail", meaning="tiny", messages="rule", answers=h, require_freeze=False, facts_path=FIX["retail"])

    def test_v3_freeze_still_checked(self):
        bad = {"guard/tgr_tracker_v3.py": "0" * 64}
        with self.assertRaises(V3.FrozenInputChangedV3):
            G.build("retail", frozen_table=bad, facts_path=FIX["retail"])

    def test_v4_freeze_flag(self):
        ok = types.SimpleNamespace(DEFAULT_MANIFEST="m.json", check=lambda m: {
            "ok": True, "checked": 7, "manifest_sha256": "a" * 64, "problems": []})
        bad = types.SimpleNamespace(DEFAULT_MANIFEST="m.json", check=lambda m: {
            "ok": False, "checked": 0, "manifest_sha256": None, "problems": ["manifest missing: m.json"]})
        refuse = types.SimpleNamespace(DEFAULT_MANIFEST="m.json", check=lambda m: (_ for _ in ()).throw(SystemExit(1)))
        with self.assertRaises(G.FreezeV4Failed):
            G.build("retail", require_freeze=True, freeze_module=bad, facts_path=FIX["retail"])
        with self.assertRaises(G.FreezeV4Failed):
            G.build("retail", require_freeze=True, freeze_module=refuse, facts_path=FIX["retail"])
        g = G.build("retail", require_freeze=False, freeze_module=bad, facts_path=FIX["retail"])
        self.assertFalse(g.freeze["frozen"])
        g = G.build("retail", meaning="tiny", answers=hook(P_NO), require_freeze=True, freeze_module=ok,
                    facts_path=FIX["retail"])
        self.assertEqual(g.freeze, {"manifest_sha256": "a" * 64, "n_files": 7, "frozen": True})
        rec = check(g, RT.Conversation(), base_history(), "cancel_pending_order", CANCEL)
        self.assertTrue(rec["v4"]["frozen"])
        self.assertEqual(rec["v4"]["manifest_sha256"], "a" * 64)

    def test_real_freeze_module_api(self):
        st = G.freeze_status_v4(False)                         # the real module, check(manifest); never raises here
        self.assertEqual(set(st), {"manifest_sha256", "n_files", "frozen"})

    def test_fact_file_checks(self):
        with self.assertRaises(G.FactFileProblem):
            G.load_checked_facts_v4("retail", os.path.join(FIX_DIR, "no_such_file.json"))
        doc = G.load_checked_facts_v4("retail", FIX["retail"])
        self.assertEqual(sorted(doc["facts"]), sorted(F.load_facts("retail")["facts"]))
        self.assertIs(G.FactFileProblem, V3.FactFileProblem)

    def test_text_facts_of(self):
        doc = {"facts": {
            "a": {"parts": {"a": {"source": "structure", "expr": "listing_ok_v4()", "question": None}}},
            "b": {"parts": {"a": {"source": "structure", "expr": "len(go_ahead_candidates_v4()) > 0"}}},
            "c": {"parts": {"a": {"source": "question", "expr": "ask_v4('K12', 1)", "question": "K12"}}},
            "d": {"parts": {"a": {"source": "database", "expr": "user_not_found_v4()", "question": None}}}}}
        self.assertEqual(G.text_facts_of(doc), frozenset({"a", "b", "c"}))

    def test_write_key(self):
        self.assertEqual(G.write_key_v4("retail", "cancel_pending_order", CANCEL), ["cancel_pending_order", ORDER])
        self.assertEqual(G.write_key_v4("retail", "modify_user_address", {"user_id": "u1", "zip": "1"}),
                         ["modify_user_address", "u1"])
        self.assertEqual(G.write_key_v4("airline", "cancel_reservation", {"reservation_id": "ABC123"}),
                         ["cancel_reservation", "ABC123"])
        self.assertEqual(G.write_key_v4("airline", "book_reservation", {"user_id": "u2", "flights": []}),
                         ["book_reservation", "u2"])
        self.assertEqual(G.write_key_v4("airline", "send_certificate", {"user_id": "u3", "amount": 50}),
                         ["send_certificate", "u3"])
        self.assertIsNone(G.write_key_v4("retail", "get_order_details", {"order_id": ORDER}))
        self.assertIsNone(G.write_key_v4("retail", "transfer_to_human_agents", TRANSFER))
        self.assertIsNone(G.write_key_v4("retail", "respond", {"content": "hi"}))

    def test_offline_variants_registered(self):
        from fork import offline_v3 as O
        self.assertEqual(G.register(), ["v4", "v4_rule", "v4_full"])
        self.assertEqual(G.register(), ["v4", "v4_rule", "v4_full"])          # again changes nothing
        for n in ("v4", "v4_rule", "v4_full"):
            self.assertIn(n, O.GUARDS)
        self.assertFalse(G.VARIANTS["v4_full"]["lazy"])
        self.assertEqual(G.VARIANTS["v4_rule"]["messages"], "rule")


# ----------------------------------------------------------------------------------------------- the record
V4_KEYS = {"version", "manifest_sha256", "frozen", "write_key", "tiny_block", "escape", "reasks", "unclear_allowed",
           "missing", "fast_path", "ask_keys"}


class TestRecord(unittest.TestCase):
    def test_layout_of_a_block_and_an_allow(self):
        g = guard(P_NO)
        conv = RT.Conversation()
        blk = check(g, conv, base_history(), "cancel_pending_order", CANCEL)
        self.assertFalse(blk["action_allowed"])
        g2 = guard(P_DB)
        ok = check(g2, RT.Conversation(), base_history(), "cancel_pending_order", CANCEL)
        self.assertTrue(ok["action_allowed"])
        for rec in (blk, ok):
            self.assertEqual(rec["v3"]["version"], "v4.p1.1")
            self.assertEqual(rec["v3"]["switches"], {"facts": "v4", "meaning": "tiny", "messages": "frozen"})
            self.assertEqual(rec["tracker"]["version"], "v4")
            self.assertTrue(V4_KEYS <= set(rec["v4"]), V4_KEYS - set(rec["v4"]))
            self.assertEqual(rec["v4"]["version"], "v4.p1.1")
            self.assertEqual(rec["v4"]["write_key"], ["cancel_pending_order", ORDER])
            self.assertIsInstance(rec["v4"]["reasks"], list)
            self.assertIsInstance(rec["v4"]["unclear_allowed"], list)
            self.assertIsInstance(rec["v4"]["fast_path"], list)
            self.assertIsInstance(rec["v4"]["missing"], dict)
            self.assertIsInstance(rec["v4"]["ask_keys"], dict)
            self.assertIsNone(rec["v4"]["escape"])
            self.assertEqual(rec["v4"]["state_errors"], rec["v3"]["state_errors"])
            self.assertEqual(rec["v4"]["fact_errors"], rec["v3"]["fact_errors"])
            self.assertIn("blocking_facts", rec)
            self.assertEqual(rec["blocking_facts"], rec["v4"]["blocking_facts"])
            self.assertTrue(rec["v3"]["questions"]["asked_facts"])                # filled as in v3
            json.dumps(rec)                                                          # the record is JSON
            for n, f in rec["v3"]["facts"].items():
                self.assertIn(f["source"], G.KINDS)
                self.assertEqual(rec["judge"][n]["value"], f["value"])
        self.assertEqual(ok["blocking_facts"], [])
        self.assertFalse(ok["v4"]["tiny_block"])
        self.assertTrue(blk["v4"]["tiny_block"])
        bf = blk["blocking_facts"]
        self.assertTrue(bf)
        for b in bf:
            self.assertEqual(set(b), {"fact", "value", "source", "text", "rules"})
            self.assertIn(b["fact"], blk["judge"])
            self.assertTrue(set(b["rules"]) <= {str(v["rule_id"]) for v in blk["violated_rules"]})
        self.assertTrue(all(b["text"] for b in bf))
        # every violated rule is covered by some blocking fact
        self.assertEqual({r for b in bf for r in b["rules"]}, {str(v["rule_id"]) for v in blk["violated_rules"]})

    def test_database_only_block(self):
        g = guard(P_DB)
        rec = check(g, RT.Conversation(), base_history(), "cancel_pending_order", BAD_REASON)
        self.assertFalse(rec["action_allowed"])
        self.assertFalse(rec["v4"]["tiny_block"])
        self.assertEqual([b["fact"] for b in rec["blocking_facts"]], ["cancellation_reason_is_allowed"])
        self.assertEqual(rec["blocking_facts"][0]["source"], "code")
        self.assertFalse(rec["blocking_facts"][0]["text"])

    def test_blocking_facts_on_a_non_write_block(self):
        g = guard(P_NO)
        rec = check(g, RT.Conversation(), base_history(), "transfer_to_human_agents", TRANSFER)
        self.assertFalse(rec["action_allowed"])
        self.assertEqual([b["fact"] for b in rec["blocking_facts"]], [TRANSFER_FACT])
        self.assertIsNone(rec["v4"]["write_key"])
        self.assertFalse(rec["v4"]["tiny_block"])                                # not a write: never tiny

    def test_no_fact_record(self):
        g = guard(P_NO)
        rec = check(g, RT.Conversation(), base_history(), "think", {"thought": "x"})
        self.assertTrue(rec["action_allowed"])
        self.assertEqual(rec["tracker"]["version"], "v4")
        self.assertEqual(rec["blocking_facts"], [])
        self.assertTrue(V4_KEYS <= set(rec["v4"]))


# ----------------------------------------------------------------------------------------------- the escape
class TestEscape(unittest.TestCase):
    def transfer(self, g, conv, h=None):
        return check(g, conv, base_history() if h is None else h, "transfer_to_human_agents", TRANSFER)

    def test_fires_after_two_tiny_blocks_on_one_key(self):
        g = guard(P_NO)
        conv = RT.Conversation()
        self.assertFalse(self.transfer(g, conv)["action_allowed"])              # 0 blocks: K13 no blocks
        b1 = check(g, conv, base_history(), "cancel_pending_order", CANCEL)
        self.assertTrue(b1["v4"]["tiny_block"])
        r1 = self.transfer(g, conv)
        self.assertFalse(r1["action_allowed"])                                  # 1 tiny block: no escape
        self.assertIsNone(r1["v4"]["escape"])
        n0 = g.counters["escapes"]
        check(g, conv, base_history(), "cancel_pending_order", CANCEL)
        r2 = self.transfer(g, conv)
        self.assertTrue(r2["action_allowed"])
        esc = r2["v4"]["escape"]
        self.assertEqual(esc["fact"], TRANSFER_FACT)
        self.assertEqual(esc["write_key"], ["cancel_pending_order", ORDER])
        self.assertEqual(esc["tiny_blocks"], 2)
        self.assertIs(esc["value_before"], False)
        self.assertEqual(r2["v3"]["facts"][TRANSFER_FACT]["source"], "escape")
        self.assertIs(r2["v3"]["facts"][TRANSFER_FACT]["value"], True)
        self.assertEqual(r2["judge"][TRANSFER_FACT]["source"], "escape")
        self.assertEqual(g.counters["escapes"], n0 + 1)
        self.assertEqual(len(conv.v4_blocks), 2)                                # transfers are not write entries

    def test_not_after_database_only_blocks(self):
        g = guard(P_DB)
        conv = RT.Conversation()
        for _ in range(3):
            self.assertFalse(check(g, conv, base_history(), "cancel_pending_order", BAD_REASON)["v4"]["tiny_block"])
        r = self.transfer(g, conv)
        self.assertFalse(r["action_allowed"])
        self.assertIsNone(r["v4"]["escape"])

    def test_not_on_one_block_each_of_two_keys(self):
        g = guard(P_NO)
        conv = RT.Conversation()
        check(g, conv, base_history(), "cancel_pending_order", CANCEL)
        check(g, conv, base_history(), "cancel_pending_order", {"order_id": ORDER2, "reason": "no longer needed"})
        self.assertEqual(len({json.dumps(e["write_key"]) for e in conv.v4_blocks}), 2)
        self.assertIsNone(self.transfer(g, conv)["v4"]["escape"])

    def test_not_after_the_write_ran(self):
        g = guard(P_NO)
        conv = RT.Conversation()
        two_tiny_blocks(g, conv)
        h2 = executed_after(base_history(), "cancel_pending_order", CANCEL)    # the write then executed
        r = self.transfer(g, conv, h2)
        self.assertFalse(r["action_allowed"])
        self.assertIsNone(r["v4"]["escape"])
        two_tiny_blocks(g, conv, h2)                                            # 2 more tiny blocks after it ran
        self.assertIsNotNone(self.transfer(g, conv, h2)["v4"]["escape"])

    def test_not_after_an_allowed_check_of_the_key(self):
        g = guard(P_NO)
        conv = RT.Conversation()
        two_tiny_blocks(g, conv)
        conv.v4_blocks.append({"write_key": ["cancel_pending_order", ORDER], "tiny": False, "blocked": False,
                               "executed": True, "cap_override": False, "step_index": 3, "hist_len": 50})
        self.assertIsNone(self.transfer(g, conv)["v4"]["escape"])

    def test_not_across_episodes(self):
        g = guard(P_NO)
        two_tiny_blocks(g, RT.Conversation())
        r = self.transfer(g, RT.Conversation())                                # a new episode: empty memory
        self.assertIsNone(r["v4"]["escape"])
        self.assertFalse(r["action_allowed"])

    def test_not_across_threads(self):
        g = guard(P_NO)
        out, errs = {}, []

        def run(name, n_blocks):
            try:
                conv = RT.Conversation()
                conv.v4_blocks = []
                for _ in range(n_blocks):
                    check(g, conv, base_history(), "cancel_pending_order", CANCEL)
                out[name] = self.transfer(g, conv)["v4"]["escape"]
            except Exception as e:  # noqa: BLE001
                errs.append(repr(e))

        ts = [threading.Thread(target=run, args=(f"t{i}", n)) for i, n in enumerate((2, 1, 0, 2))]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(errs, [])
        self.assertIsNotNone(out["t0"])
        self.assertIsNone(out["t1"])
        self.assertIsNone(out["t2"])
        self.assertIsNotNone(out["t3"])

    def test_survives_retries(self):
        """TGR.step retries a failed _step: a failed attempt leaves no memory entry, the retried one leaves one."""
        inner = hook(P_NO)

        class Flaky:
            standin, doc, stats = False, inner.doc, inner.stats
            n = 0

            def ask(self, qid, inputs, *, fact=None, part=None, **kw):
                Flaky.n += 1
                if Flaky.n == 1:
                    raise Q.NetworkBlocked("transient, once")
                return inner.ask(qid, inputs, fact=fact, part=part)

        g = guard(answers=Flaky())
        conv = RT.Conversation()
        with mock.patch.object(RT.time, "sleep", lambda s: None):
            r1 = g.step(conv, make_step(base_history(), call("cancel_pending_order", CANCEL), 3))
            self.assertEqual(r1["attempts"], 2)
            self.assertEqual(len(conv.v4_blocks), 1)
            g.step(conv, make_step(base_history(), call("cancel_pending_order", CANCEL), 3))
            self.assertEqual(len(conv.v4_blocks), 2)
            r = g.step(conv, make_step(base_history(), call("transfer_to_human_agents", TRANSFER), 3))
        self.assertTrue(r["action_allowed"])
        self.assertEqual(r["v4"]["escape"]["tiny_blocks"], 2)

    def test_cap_override(self):
        g = guard(P_NO)
        conv = RT.Conversation()
        recs = two_tiny_blocks(g, conv)
        n_trace = len(conv.trace)
        g.commit(conv, recs[-1])                                                # the cap override executes it
        self.assertEqual(len(conv.trace), n_trace + 1)                          # TGR's own commit still runs
        self.assertTrue(conv.v4_blocks[1]["executed"])
        self.assertTrue(conv.v4_blocks[1]["cap_override"])
        self.assertIsNone(self.transfer(g, conv)["v4"]["escape"])              # the write ran: no escape

    def test_blocks_survive_a_cap_override_of_another_key(self):
        g = guard(P_NO)
        conv = RT.Conversation()
        check(g, conv, base_history(), "cancel_pending_order", CANCEL)
        other = check(g, conv, base_history(), "cancel_pending_order", {"order_id": ORDER2, "reason": "no longer needed"})
        g.commit(conv, other)
        self.assertIsNone(self.transfer(g, conv)["v4"]["escape"])
        check(g, conv, base_history(), "cancel_pending_order", CANCEL)
        esc = self.transfer(g, conv)["v4"]["escape"]
        self.assertEqual(esc["write_key"], ["cancel_pending_order", ORDER])

    def test_memory_made_when_missing(self):
        g = guard(P_NO)
        conv = RT.Conversation()
        self.assertFalse(hasattr(conv, "v4_blocks"))
        check(g, conv, base_history(), "cancel_pending_order", CANCEL)
        self.assertEqual(len(conv.v4_blocks), 1)

    def test_not_on_a_state_error(self):
        g = guard(P_NO)
        conv = RT.Conversation()
        two_tiny_blocks(g, conv)
        bad = base_history()
        i = next(i for i, m in enumerate(bad) if m.get("role") == "tool")
        bad[i] = dict(bad[i], content=bad[i]["content"] + " (changed)")       # a replay mismatch
        r = self.transfer(g, conv, bad)
        self.assertTrue(r["v3"]["state_errors"])
        self.assertEqual(r["v4"]["state_errors"], r["v3"]["state_errors"])
        self.assertIsNone(r["v4"]["escape"])
        self.assertFalse(r["action_allowed"])

    def test_no_escape_when_already_true(self):
        g = guard(lambda qid, inputs, norm: "yes" if qid == "K13" else "no")
        conv = RT.Conversation()
        two_tiny_blocks(g, conv)
        r = self.transfer(g, conv)
        self.assertTrue(r["action_allowed"])
        self.assertIsNone(r["v4"]["escape"])
        self.assertEqual(r["v3"]["facts"][TRANSFER_FACT]["source"], "question")

    def test_escape_candidate_order_and_counts(self):
        k = ["cancel_pending_order", ORDER]
        blocks = [{"write_key": k, "tiny": True, "hist_len": 5}, {"write_key": k, "tiny": True, "hist_len": 5},
                  {"write_key": k, "executed": True, "tiny": False, "hist_len": 7},
                  {"write_key": k, "tiny": True, "hist_len": 9}]
        self.assertIsNone(G.escape_candidate("retail", blocks, [], G.write_tools("retail")))
        blocks.append({"write_key": k, "tiny": True, "hist_len": 9})
        self.assertEqual(G.escape_candidate("retail", blocks, [], G.write_tools("retail"))["tiny_blocks"], 2)


# ----------------------------------------------------------------------------------------------- hard stops
class _Raising:
    standin = False

    def __init__(self, exc, inner):
        self.exc, self.inner = exc, inner
        self.doc, self.stats = inner.doc, inner.stats

    def ask(self, qid, inputs, *, fact=None, part=None, **kw):
        raise self.exc(f"{self.exc.__name__} in a test")


class TestHardStops(unittest.TestCase):
    def test_hard_stops_propagate(self):
        for exc in (Q.BudgetExceeded, Q.NetworkBlocked, Q.RealModeRefused, Q.AnswerNotSaved):
            with self.subTest(exc=exc.__name__):
                g = guard(answers=_Raising(exc, hook(P_NO)))
                conv = RT.Conversation()
                with self.assertRaises(exc):
                    check(g, conv, base_history(), "cancel_pending_order", CANCEL)
                self.assertEqual(conv.v4_blocks, [])                            # no block was recorded
                with mock.patch.object(RT.time, "sleep", lambda s: None):
                    with self.assertRaises(RuntimeError) as cm:
                        g.step(conv, make_step(base_history(), call("cancel_pending_order", CANCEL), 3))
                self.assertIn("in a test", str(cm.exception))
                self.assertEqual(conv.v4_blocks, [])
                self.assertEqual(conv.trace, [])
        self.assertEqual(G.HARD_STOPS, V3.HARD_STOPS)

    def test_failed_real_call_is_a_fact_error(self):
        g = guard(answers=_Raising(Q.RealCallFailed, hook(P_NO)))
        rec = check(g, RT.Conversation(), base_history(), "cancel_pending_order", CANCEL)
        fe = rec["v3"]["fact_errors"]
        self.assertTrue(fe)
        self.assertTrue(all(e["error"] == "RealCallFailed" for e in fe))
        self.assertEqual(rec["v4"]["fact_errors"], fe)
        self.assertFalse(rec["action_allowed"])

    def test_no_llm_call(self):
        before = dict(CALLS)
        g = guard(P_NO)
        conv = RT.Conversation()
        two_tiny_blocks(g, conv)
        check(g, conv, base_history(), "transfer_to_human_agents", TRANSFER)
        self.assertEqual(dict(CALLS), before)


# ----------------------------------------------------------------------------------------------- lazy and hooks
class _V4Hook:
    """A QuestionsV4-shaped double: ask(..., wording=1), doc, stats, answers by (qid, wording)."""
    standin = False

    def __init__(self, answers):
        self.answers, self.calls = answers, []
        self.doc, self.stats, self.where = {"double": True}, Q.Stats(), None

    def ask(self, qid, inputs, *, fact=None, part=None, wording=1):
        self.calls.append((qid, fact, part, wording))
        st = self.answers.get((qid, wording), "no")
        return {"key": f"{qid}-w{wording}-" + "0" * 20, "qid": qid, "status": st, "answer": st}


def _reask_helper_v4(ctx, note=True):
    """Test helper: asks K13 (wording 1); unclear -> wording 2 (noted as questions_v4 does when note=True); still
    unclear -> True (allow + log)."""
    h = ctx.need_answers()
    r1 = h.ask("K13", {"message": "x"}, fact=ctx.fact, part=ctx.part_id)
    if r1["status"] in ("yes", "no"):
        return r1["status"] == "yes"
    r2 = h.ask("K13", {"message": "x"}, fact=ctx.fact, part=ctx.part_id, wording=2)
    if note:
        ctx.note({"v4": "reask", "qid": "K13", "fact": ctx.fact, "part": ctx.part_id, "key1": r1["key"],
                  "key2": r2["key"], "status1": r1["status"], "status2": r2["status"]})
    if r2["status"] in ("yes", "no"):
        return r2["status"] == "yes"
    if note:
        ctx.note({"v4": "unclear_allowed", "fact": ctx.fact, "qid": "K13", "part": ctx.part_id})
    return True


def _fast_helper_v4(ctx):
    ctx.note({"fast_path": "K1", "message": 3})
    ctx.note({"missing": [{"line": "order id", "expected": ORDER, "forms": [ORDER], "fact": ctx.fact, "part": "a"}]})
    return True


class TestHooksAndLazy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        F.register_name("guardtest_reask_v4", _reask_helper_v4, 0, 0, ("note",), source="question")
        F.register_name("guardtest_fast_v4", _fast_helper_v4, 0, 0, (), source="structure")

    @classmethod
    def tearDownClass(cls):
        F.unregister_name("guardtest_reask_v4")
        F.unregister_name("guardtest_fast_v4")

    def doc_with(self, expr):
        doc = copy.deepcopy(G.load_checked_facts_v4("retail", FIX["retail"]))
        e = doc["facts"][TRANSFER_FACT]
        e["parts"]["b"] = dict(e["parts"]["b"], expr=expr)
        e["parts"]["c"] = {"source": "structure", "expr": "guardtest_fast_v4()", "plain": "test", "question": None,
                           "about": None}
        e["combine"] = "a AND b AND c"
        return doc

    def run_transfer(self, expr, answers):
        h = _V4Hook(answers)
        g = G.build("retail", meaning="tiny", answers=h, facts_doc=self.doc_with(expr))
        rec = check(g, RT.Conversation(), base_history(), "transfer_to_human_agents", TRANSFER)
        return rec, h

    def test_reask_and_unclear_allowed_from_notes(self):
        rec, h = self.run_transfer("guardtest_reask_v4()", {("K13", 1): "unclear", ("K13", 2): "quote_failed"})
        self.assertEqual([c[3] for c in h.calls], [1, 2])                      # wording reached the hook
        self.assertTrue(rec["action_allowed"])
        v4 = rec["v4"]
        self.assertEqual(len(v4["reasks"]), 1)                                  # the note; no double from the log
        r = v4["reasks"][0]
        self.assertEqual((r["qid"], r["fact"], r["status1"], r["status2"]), ("K13", TRANSFER_FACT, "unclear",
                                                                              "quote_failed"))
        self.assertTrue(r["key1"].startswith("K13-w1") and r["key2"].startswith("K13-w2"))
        self.assertEqual(v4["unclear_allowed"], [{"fact": TRANSFER_FACT, "qid": "K13"}])
        self.assertEqual(v4["fast_path"], [TRANSFER_FACT])
        self.assertEqual(v4["missing"][TRANSFER_FACT][0]["expected"], ORDER)
        self.assertEqual(v4["ask_keys"][TRANSFER_FACT], [("K13-w1-" + "0" * 20)[:16], ("K13-w2-" + "0" * 20)[:16]])
        self.assertEqual(rec["v3"]["questions"]["asked"], {"K13": 2})

    def test_reask_from_the_ask_log_without_notes(self):
        rec, h = self.run_transfer("guardtest_reask_v4(note=False)", {("K13", 1): "unclear", ("K13", 2): "unclear"})
        v4 = rec["v4"]
        self.assertEqual(len(v4["reasks"]), 1)
        self.assertEqual((v4["reasks"][0]["status1"], v4["reasks"][0]["status2"]), ("unclear", "unclear"))
        self.assertEqual(v4["unclear_allowed"], [{"fact": TRANSFER_FACT, "qid": "K13"}])

    def test_second_wording_answer_decides(self):
        rec, _ = self.run_transfer("guardtest_reask_v4()", {("K13", 1): "unclear", ("K13", 2): "no"})
        self.assertFalse(rec["action_allowed"])
        self.assertEqual(rec["v4"]["reasks"][0]["status2"], "no")
        self.assertEqual(rec["v4"]["unclear_allowed"], [])

    def test_probe_takes_v4_keywords(self):
        p = G._ProbeV4(standin=False)
        with self.assertRaises(V3._Deferred):
            p.ask("K1", {}, fact="f", part="b", wording=2)
        with self.assertRaises(V3._Deferred):
            p.value_for("f")

    def test_counting_hook(self):
        h = _V4Hook({("K1", 2): "yes"})
        c = G._CountingHookV4(h)
        self.assertEqual(c.doc, {"double": True})                               # doc is forwarded
        G._SINK.asks = []
        self.assertEqual(c.ask("K1", {}, fact="f", part="b", wording=2)["status"], "yes")
        self.assertEqual(h.calls, [("K1", "f", "b", 2)])
        self.assertEqual(c.asked["K1"], 1)
        self.assertEqual(G._SINK.asks[0]["wording"], 2)
        s = G._CountingHookV4(Q.StandInAnswers({"f": True}))                   # no wording keyword: dropped
        self.assertEqual(s.ask("K1", {}, fact="f", part="b", wording=2)["status"], "yes")
        G._SINK.asks = None

    def test_lazy_counts_and_decisions(self):
        cases = [(P_NO, CANCEL), (P_DB, CANCEL), (P_DB, BAD_REASON), (P_NO, BAD_REASON), (P_NO, None), (P_DB, None)]
        n_lazy = n_full = 0
        for pol, args in cases:
            recs = {}
            for lazy in (True, False):
                hk = hook(pol)
                g = guard(answers=hk, lazy=lazy)
                if args is None:                                                # a reply after login (rule 3)
                    rec = g._step(RT.Conversation(), make_step(base_history(), {
                        "role": "assistant", "content": f"Your order {ORDER} is pending."}, 3))
                else:
                    rec = check(g, RT.Conversation(), base_history(), "cancel_pending_order", args)
                asked = sum(rec["v3"]["questions"]["asked"].values())
                self.assertEqual(asked, sum(hk.stats.asks.values()))
                self.assertEqual(sum(len(v) for v in rec["v4"]["ask_keys"].values()), asked)
                recs[lazy] = (rec, asked)
            self.assertEqual(recs[True][0]["action_allowed"], recs[False][0]["action_allowed"])
            self.assertLessEqual(recs[True][1], recs[False][1])
            n_lazy += recs[True][1]
            n_full += recs[False][1]
        self.assertLess(n_lazy, n_full)                                         # lazy skips some questions


# ----------------------------------------------------------------------------------------------- v3 reused
class TestV3Reused(unittest.TestCase):
    def test_same_code_objects(self):
        self.assertIs(G.TrackerTGRv4._answer.__code__, V3.TrackerTGRv3._answer.__code__)
        self.assertIs(G._V3_VALUES.__code__, V3.TrackerTGRv3._v3_values.__code__)
        self.assertIs(G.TrackerTGRv4._feedback.__code__, V3.TrackerTGRv3._feedback.__code__)
        self.assertIs(G._V3_VALUES.__globals__["_Probe"], G._ProbeV4)
        self.assertIs(G.TrackerTGRv4._answer.__globals__["_CountingHook"], G._CountingHookV4)
        self.assertEqual(G.TrackerTGRv4._feedback.__globals__["FEEDBACK_MODULE"], "guard.feedback_v4")
        self.assertEqual(V3.FEEDBACK_MODULE, "guard.feedback_v3")             # v3's module is not changed
        self.assertIs(V3._Probe.ask, V3.__dict__["_Probe"].ask)

    def test_rule_message_uses_feedback_v4(self):
        got = []

        def build_message(domain, tool, args, violated, results, state, view, rule_table, rule_set):
            got.append((domain, tool, [v["rule_id"] for v in violated], sorted(results)))
            return "BLOCKED by policy guardrail. stub v4 message"

        stub = types.ModuleType("guard.feedback_v4")
        stub.build_message = build_message
        with mock.patch.dict(sys.modules, {"guard.feedback_v4": stub}):
            g = guard(P_NO, messages="rule")
            rec = check(g, RT.Conversation(), base_history(), "cancel_pending_order", CANCEL)
        self.assertEqual(rec["feedback_text"], "BLOCKED by policy guardrail. stub v4 message")
        self.assertEqual(got[0][:2], ("retail", "cancel_pending_order"))
        self.assertEqual(rec["v3"]["message"], {"mode": "rule", "built": "rule", "fallback": False})

    @unittest.skipUnless(os.path.isfile(G.facts_path_v4("retail")),
                         "the real v4 fact file is not merged yet (guard/feedback_v4.py reads it)")
    def test_rule_message_with_the_real_feedback_v4(self):
        g = guard(P_NO, messages="rule")
        rec = check(g, RT.Conversation(), base_history(), "cancel_pending_order", CANCEL)
        self.assertFalse(rec["v3"]["message"]["fallback"], rec["v3"]["message"])
        self.assertTrue(rec["feedback_text"].startswith("BLOCKED"))


class TestV3Untouched(unittest.TestCase):
    def test_v3_guard_sha(self):
        with open(os.path.join(PC_DIR, "guard", "tgr_tracker_v3.py"), "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), V3_GUARD_SHA256)

    def test_v3_frozen_inputs(self):
        res = V3.check_frozen_v3()
        self.assertEqual(res["unrecorded"], [])

    def test_fixtures_are_v3_copies(self):
        for d in ("retail", "airline"):
            with open(FIX[d], "rb") as a, open(F.facts_path(d), "rb") as b:
                self.assertEqual(a.read(), b.read())


if __name__ == "__main__":
    unittest.main()
