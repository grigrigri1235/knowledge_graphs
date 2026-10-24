"""Tracker v3, part 13 step 1: tests of the Direct + facts guard (guard/direct_facts_v3.py).

No LLM call and no network: the runner's LLM seam (repro_runtime.calls.shared_llm) gives a fake LLM that records the
prompts and returns fixed decisions; the real client getter (policy_pipeline.llm._get_client) and every socket connect
raise and are counted (0 at the end). Saved checks are read only from the development data (fork/offline_v3.py side
"dev"; hold-out conversations are skipped unread).

  inputs     the policy loader (sha256, equal to the τ-bench copy's policy text), Direct's runner-copy files and
             defaults (effort medium, history 24,000), direct_guard() = the copy's DirectGuard with the loader;
  prompt     no block: the prompt and the record equal the copy's own direct(); with a block: the only difference is
             the block (removing it gives Direct's prompt, its sha256 recorded), placed right after the action line;
             the 24,000-char cut is recorded and the facts still come from the whole conversation;
  shapes     every action of both rule sets (so every rule): the block lists exactly the circuit's code-only facts
             (none: no block), before and after login; every part source, a for_each fact, a problem value;
             state error / fact error / facts failure: left out, recorded, the prompt is Direct's;
  values     on >= 300 saved development checks of both domains: the block's facts and values equal the v3 guard's
             (guard/tgr_tracker_v3.py, the current code), fact by fact;
  leaks      before login every fact line is "- <fact>: true | false" and nothing else; after login every database
             line shown is of the logged-in user's records or catalog records.

Run from predicate_correctness/:
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v3_direct_facts \\
        -v > output/logs/v3_p13a_tests.log 2>&1
"""
from __future__ import annotations

import collections
import copy
import json
import os
import re
import socket
import sys
import unittest

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from guard import direct_facts_v3 as DF                                  # noqa: E402
from guard import tgr_tracker_v3 as V3                                   # noqa: E402
from fork import offline_v3 as O                                         # noqa: E402
from repro_core.taubench_steps import Step, render_history               # noqa: E402  (runner copy)
from repro_online.guards import DirectGuard, make_step                   # noqa: E402  (runner copy)
from repro_runtime import calls                                          # noqa: E402  (runner copy)
from repro_runtime import direct as copy_direct                          # noqa: E402  (runner copy)
from repro_runtime.shield import action_text, render_feedback            # noqa: E402  (runner copy)
from state_tracker import paths, tau_copy                                # noqa: E402

DOMAINS = ("retail", "airline")
DEV_DATASETS = tuple(d for d in O.DATASETS if d not in ("ours.p10_luna_val", "partner.luna_val"))
SAMPLE_EVERY = 37            # every 37th development conversation of each data set ...
SAMPLE_PER_DATASET = 40      # ... until 40 checks of the data set
MIN_CHECKS, MIN_AIRLINE = 300, 40
V3_TEST_NAME = "v3_for_direct_facts_test"
COUNT: collections.Counter = collections.Counter()
LINE_BEFORE_LOGIN = re.compile(r"^(- [a-z0-9 ]+: (true|false)"
                               r"|  \(a problem: [a-z0-9_, ]+; the value is the rule's safe default\))$")
PROBLEM_NOTE = "  (a problem: {}; the value is the rule's safe default)"


# ----------------------------------------------------------------------------------------------- safety and fakes
class FakeLLM:
    """The runner's LLM object, faked: records every call, returns a fixed decision. Never a client."""
    model, max_output_tokens = "fake-llm", 16000
    cache_dir = os.path.join(paths.OUTPUT_DIR, "_fake_llm_never_written")

    def __init__(self, safe: bool = True):
        self.safe = safe
        self.calls = []

    def call(self, *, stage, system, user, schema, schema_name, effort):
        self.calls.append({"stage": stage, "system": system, "user": user, "schema": schema,
                           "schema_name": schema_name, "effort": effort})
        COUNT["fake LLM calls"] += 1
        if self.safe:
            return {"safe": True, "violated_policy_statements": [], "explanation": "fine"}
        return {"safe": False, "violated_policy_statements": ["Sentence one.", "Sentence two."],
                "explanation": "not allowed"}


_SAVED = {}


def _refuse_client(*a, **k):
    COUNT["real client requested"] += 1
    raise AssertionError("a real LLM client was requested in a unit test")


def _refuse_connect(*a, **k):
    COUNT["network connects"] += 1
    raise AssertionError("a network connection was attempted in a unit test")


def use_fake(fake):
    calls._llm = None
    calls.shared_llm = lambda: fake


def setUpModule():
    import policy_pipeline.llm as v1
    _SAVED.update(shared=calls.shared_llm, client=v1._get_client, connect=socket.socket.connect,
                  create=socket.create_connection)
    v1._get_client = _refuse_client
    calls.shared_llm = lambda: _refuse_client()
    socket.socket.connect = _refuse_connect
    socket.create_connection = _refuse_connect


def tearDownModule():
    import policy_pipeline.llm as v1
    calls.shared_llm = _SAVED["shared"]
    v1._get_client = _SAVED["client"]
    socket.socket.connect = _SAVED["connect"]
    socket.create_connection = _SAVED["create"]
    assert COUNT["real client requested"] == 0 and COUNT["network connects"] == 0, dict(COUNT)


# ----------------------------------------------------------------------------------------------- helpers
_GUARDS = {}
_FB = {}


def guard(domain):
    if domain not in _GUARDS:
        _GUARDS[domain] = DF.DirectFactsGuard(domain)
    return _GUARDS[domain]


def facts(domain):
    if domain not in _FB:
        _FB[domain] = guard(domain).facts
    return _FB[domain]


def _call(cid, name, args):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


class Conv:
    """A synthetic conversation whose tool outputs are τ-bench's own (run on a fresh copy of the data)."""

    def __init__(self, domain):
        self.domain = domain
        self.data = tau_copy.load_data_fresh(domain)
        self.tools = tau_copy.tools(domain)
        self.msgs = [{"role": "system", "content": tau_copy.policy_text(domain)}]
        self.n = 0

    def user(self, text):
        self.msgs.append({"role": "user", "content": text})
        return self

    def agent(self, text):
        self.msgs.append({"role": "assistant", "content": text})
        return self

    def tool(self, name, **args):
        self.n += 1
        cid = f"call_{self.n}"
        out = self.tools[name].invoke(data=self.data, **args)
        self.msgs.append(_call(cid, name, args))
        self.msgs.append({"role": "tool", "tool_call_id": cid, "name": name, "content": out})
        return out

    def step(self, name, args):
        """The pending call as the guard sees it (make_step: history = the executed messages)."""
        msg = {"role": "assistant", "content": None, "tool_calls": _call("pending", name, args)["tool_calls"]} \
            if name != "respond" else {"role": "assistant", "content": args.get("content", "")}
        return make_step(list(self.msgs), msg, 0)


def retail_user(data):
    for uid, u in sorted(data["users"].items()):
        if u.get("orders") and u.get("email"):
            return uid, u
    raise AssertionError("no retail user")


def logged_in_retail():
    c = Conv("retail")
    uid, u = retail_user(c.data)
    c.user(f"Hi, my email is {u['email']}.")
    out = c.tool("find_user_id_by_email", email=u["email"])
    assert out == uid, out
    return c, uid, u


def logged_in_airline():
    c = Conv("airline")
    uid = sorted(c.data["users"])[0]
    c.user(f"Hello, my user id is {uid}.")
    return c, uid, c.data["users"][uid]


def block_lines(block):
    return block.split("\n")


def fact_lines(block):
    return [ln for ln in block_lines(block)[2:] if ln.startswith("- ")]


# ----------------------------------------------------------------------------------------------- the dev sample
_SAMPLE = []


def dev_sample():
    """>= 300 saved development checks of both domains: (check, step, v3 guard record facts, block_for result)."""
    if _SAMPLE:
        return _SAMPLE
    v3 = {d: V3.build(d, facts="v3", meaning="saved_judge", messages="frozen", frozen_table={}) for d in DOMAINS}
    O.register_guard(V3_TEST_NAME, lambda dom: v3[dom], replace=True)
    for name in DEV_DATASETS:
        n = 0
        for conv in O.iter_conversations([name]):
            if conv.side != O.DEV:
                COUNT["hold-out conversations skipped (not read)"] += 1
                continue
            if conv.ordinal % SAMPLE_EVERY != 0:
                continue
            for ch in conv.checks():
                step = make_step(list(ch.history), ch.msg, ch.n_exec)
                b = facts(ch.domain).block_for(step)
                res = O.decide(ch, V3_TEST_NAME, judged=ch.saved_judge() or {})
                _SAMPLE.append((ch, step, res["record"]["v3"], b))
                n += 1
            if n >= SAMPLE_PER_DATASET:
                break
    return _SAMPLE


# ----------------------------------------------------------------------------------------------- tests
class TestInputs(unittest.TestCase):
    def test_policy_loader(self):
        for d in DOMAINS:
            text = DF.load_policy(d)
            self.assertEqual(DF.sha256_text(text), DF.POLICY_SHA256[d])
            self.assertEqual(text, tau_copy.policy_text(d))
        with self.assertRaises(ValueError):
            DF.load_policy("test")
        old = dict(DF.POLICY_SHA256)
        try:
            DF.POLICY_SHA256["retail"] = "0" * 64
            with self.assertRaises(DF.DirectInputChanged):
                DF.load_policy("retail")
            with self.assertRaises(DF.DirectInputChanged):
                DF.check_direct_inputs()
        finally:
            DF.POLICY_SHA256.update(old)

    def test_direct_inputs_and_defaults(self):
        got = DF.check_direct_inputs()
        self.assertEqual(len(got), 2 + len(DF.DIRECT_FILES))
        self.assertEqual(DF.EFFORT, "medium")
        self.assertEqual(DF.HISTORY_CHARS, 24000)
        self.assertEqual(DF.STAGE, "direct")
        self.assertEqual(DF.SCHEMA_NAME, "direct_decision")

    def test_copy_direct_guard_needs_the_loader(self):
        with self.assertRaises(FileNotFoundError):              # the copy has no policy_docs/ folder
            DirectGuard("retail")
        g = DF.direct_guard("airline")
        self.assertIsInstance(g, DirectGuard)
        self.assertEqual((g.policy, g.effort), (DF.load_policy("airline"), "medium"))

    def test_build(self):
        g = DF.build("retail", frozen_table={})
        self.assertEqual(g.info["guard"], DF.NAME)
        self.assertEqual(g.info["policy_sha256"], DF.POLICY_SHA256["retail"])
        bad = {"state_tracker/v3/facts_v3_retail.json": "0" * 64}
        with self.assertRaises(V3.FrozenInputChangedV3):
            DF.build("retail", frozen_table=bad)


class TestPrompt(unittest.TestCase):
    def _both(self, domain, step, safe=True):
        """(the copy's direct() call and record, our call and record) with the same fake."""
        f1, f2 = FakeLLM(safe), FakeLLM(safe)
        use_fake(f1)
        rec1 = copy_direct.direct(DF.load_policy(domain), step, "medium")
        use_fake(f2)
        rec2 = guard(domain).decide(step)
        self.assertEqual((len(f1.calls), len(f2.calls)), (1, 1))
        return f1.calls[0], rec1, f2.calls[0], rec2

    @staticmethod
    def _strip(rec):
        r = {k: v for k, v in rec.items() if k not in ("seconds", "direct_facts")}
        r["usage"] = {k: v for k, v in r["usage"].items() if k != "api_seconds"}
        return r

    def test_no_block_prompt_and_record_equal_direct(self):
        c = Conv("airline")
        c.user("What airports do you fly to?")
        for safe in (True, False):
            step = c.step("list_all_airports", {})            # no rule: no fact, no block
            a, r1, b, r2 = self._both("airline", step, safe)
            self.assertEqual(a, b)                            # system, user, schema, schema name, effort, stage
            self.assertEqual(self._strip(r1), self._strip(r2))
            self.assertFalse(r2["direct_facts"]["block"])
            self.assertEqual(r2["direct_facts"]["prompt_sha256"], r2["direct_facts"]["direct_prompt_sha256"])
            self.assertEqual(r2["direct_facts"]["direct_prompt_sha256"], DF.prompt_sha256(a["system"], a["user"]))
            if not safe:
                self.assertEqual(r2["feedback_text"], render_feedback(r2["violated_rules"], "not allowed", ""))
                self.assertEqual([v["rule_id"] for v in r2["violated_rules"]], ["P1", "P2"])

    def test_block_is_the_only_difference(self):
        c, uid, u = logged_in_retail()
        oid = u["orders"][0]
        c.tool("get_order_details", order_id=oid)
        cases = [("get_order_details", {"order_id": oid}), ("respond", {"content": "Here is your order."}),
                 ("cancel_pending_order", {"order_id": oid, "reason": "no longer needed"})]
        pre = Conv("retail").user("hi")
        cases_pre = [("get_user_details", {"user_id": uid})]
        for conv, cs in ((c, cases), (pre, cases_pre)):
            for tool, args in cs:
                step = conv.step(tool, args)
                a, r1, b, r2 = self._both("retail", step, safe=False)
                part = r2["direct_facts"]
                self.assertTrue(part["block"], tool)
                block = guard("retail").facts.block_for(step)["block"]
                self.assertEqual(a["system"], b["system"])
                self.assertEqual({k: v for k, v in a.items() if k != "user"},
                                 {k: v for k, v in b.items() if k != "user"})
                self.assertNotEqual(a["user"], b["user"])
                self.assertEqual(b["user"].replace(DF.SEP + block, "", 1), a["user"])
                self.assertEqual(b["user"].count(DF.BLOCK_TITLE), 1)
                self.assertIn("The agent's next action: " + action_text(step) + DF.SEP + block + DF.template_tail(),
                              b["user"])
                self.assertEqual(part["direct_prompt_sha256"], DF.prompt_sha256(a["system"], a["user"]))
                self.assertEqual(part["prompt_sha256"], DF.prompt_sha256(b["system"], b["user"]))
                self.assertEqual(part["block_sha256"], DF.sha256_text(block))
                self.assertEqual(part["block_chars"], len(block))
                self.assertEqual(self._strip(r1), self._strip(r2))   # parsing and feedback are Direct's

    def test_history_cut_is_recorded_and_facts_use_the_whole_conversation(self):
        c, uid, u = logged_in_retail()
        for i in range(60):
            c.agent(f"Message {i}: " + "x" * 400)
            c.user(f"Reply {i}: " + "y" * 400)
        step = c.step("get_user_details", {"user_id": uid})
        self.assertGreater(len(render_history(step.history)), DF.HISTORY_CHARS)
        a, r1, b, r2 = self._both("retail", step)
        part = r2["direct_facts"]
        self.assertTrue(part["history_cut"])
        self.assertGreater(part["history_chars"], DF.HISTORY_CHARS)
        self.assertNotIn("find_user_id_by_email", b["user"].split(DF.BLOCK_TITLE)[0])   # cut away from the history
        self.assertEqual(part["facts"]["user_authenticated"]["value"], True)            # still known by code
        short = logged_in_retail()[0].step("get_user_details", {"user_id": uid})
        use_fake(FakeLLM())
        self.assertFalse(guard("retail").decide(short)["direct_facts"]["history_cut"])


class TestShapes(unittest.TestCase):
    def test_every_action_of_both_rule_sets(self):
        for d in DOMAINS:
            fb = facts(d)
            covered = set()
            for login in (False, True):
                if d == "retail":
                    conv = logged_in_retail()[0] if login else Conv("retail").user("hello")
                else:
                    conv = logged_in_airline()[0] if login else Conv("airline").user("hello")
                for act in sorted(fb.aspm.action_predicates):
                    args = {"content": "Sure."} if act == "respond" else {}
                    step = conv.step(act, args)
                    circuit = fb.aspm.circuit([act])
                    covered |= set(circuit)
                    names = sorted({n for r in circuit for n in fb.aspm.rules[r].atoms} - fb.aspm.action_predicates)
                    want = [n for n in names if DF.code_only(fb.entries[n])]
                    b = fb.block_for(step)
                    ev = b["eval"]
                    self.assertIsNone(ev["state_error"], (d, act))
                    self.assertEqual(ev["names"], want, (d, act))
                    self.assertEqual(set(ev["left_out"]), set(names) - set(want), (d, act))
                    self.assertTrue(all(v == "needs_question" for v in ev["left_out"].values()))
                    if not want:
                        self.assertIsNone(b["block"], (d, act))
                        continue
                    lines = block_lines(b["block"])
                    self.assertEqual(lines[:2], [DF.BLOCK_TITLE, DF.BLOCK_NOTE])
                    self.assertEqual([ln.split(":")[0][2:] for ln in fact_lines(b["block"])],
                                     [n.replace("_", " ") for n in want])
                    self.assertEqual(b["info"]["logged_in"], login, (d, act))
                    if not login:                      # the fact line, and the problem note if any (audit C #2)
                        exp = []
                        for n in want:
                            exp.append(f"- {n.replace('_', ' ')}: {'true' if ev['results'][n]['value'] else 'false'}")
                            kinds = sorted({p.get("kind") for p in ev["results"][n].get("problems") or []
                                            if p.get("kind")})
                            if kinds:
                                exp.append(PROBLEM_NOTE.format(", ".join(kinds)))
                        self.assertEqual(lines[2:], exp)
                    else:
                        self.assertGreater(len(lines), 2 + len(want), (d, act))     # parts and evidence
            self.assertEqual(covered, {str(r["id"]) for r in fb.rule_set["rules"]}, d)   # every rule

    def test_every_code_part_source_renders(self):
        seen = collections.Counter()
        for d in DOMAINS:
            fb = facts(d)
            for n in fb.code_facts:
                for p in fb.entries[n]["parts"].values():
                    seen[p["source"]] += 1
        self.assertEqual(set(seen), {"database", "event", "arguments", "structure"})
        c, uid, u = logged_in_retail()
        oid = u["orders"][0]
        c.tool("get_order_details", order_id=oid)
        pm = sorted(u["payment_methods"])[0]
        b = facts("retail").block_for(c.step("modify_pending_order_payment",
                                             {"order_id": oid, "payment_method_id": pm}))["block"]
        for words in ("database (", "tool-call log (", "call arguments ("):
            self.assertIn(words, b)
        self.assertIn(f"get_order_details with order_id {json.dumps(oid)}: done before this call", b)
        self.assertIn(f"order {oid}: ", b)                 # a database value of the logged-in user's order
        b2 = facts("retail").block_for(Conv("retail").user(f"I am {u['name']['first_name']} "
                                                           f"{u['name']['last_name']}, zip {u['address']['zip']}")
                                       .step("find_user_id_by_name_zip",
                                             {"first_name": u["name"]["first_name"],
                                              "last_name": u["name"]["last_name"], "zip": u["address"]["zip"]}))
        self.assertEqual(b2["eval"]["results"]["name_and_zip_identity_provided_by_user"]["value"], True)

    def test_for_each_fact_and_a_problem_value(self):
        c, uid, u = logged_in_airline()
        p = (u.get("saved_passengers") or [{"first_name": u["name"]["first_name"],
                                            "last_name": u["name"]["last_name"], "dob": u["dob"]}])[0]
        c.user(f"Book for {p['first_name']} {p['last_name']}, born {p['dob']}.")
        step = c.step("book_reservation", {"user_id": uid, "passengers": [p]})
        b = facts("airline").block_for(step)
        self.assertIn("passenger_identity_details_established", b["eval"]["names"])
        self.assertIn("(checked for each of 1 item(s) of the call's passengers", b["block"])
        self.assertIn("(a problem: missing_argument; the value is the rule's safe default)", b["block"])
        kinds = b["eval"]["kinds"]
        self.assertIn("blocking_value", kinds.values())

    def test_problem_note_before_login(self):
        """Audit C #2: before login a safe-default value keeps its "(a problem ...)" note (no database value)."""
        c = Conv("airline")
        c.user("Book a flight for me and my friend Ann Lee.")
        step = c.step("book_reservation", {"passengers": [{"first_name": "Ann", "last_name": "Lee"}]})
        b = facts("airline").block_for(step)
        self.assertFalse(b["info"]["logged_in"])
        probs = {n: r["problems"] for n, r in b["eval"]["results"].items() if r["problems"]}
        self.assertTrue(probs, b["eval"]["results"].keys())
        self.assertIn("(a problem: ", b["block"])
        self.assertIn("; the value is the rule's safe default)", b["block"])
        for ln in block_lines(b["block"])[2:]:
            self.assertRegex(ln, LINE_BEFORE_LOGIN)

    def test_block_text_and_evidence_lines_saved(self):
        """Audit C #5: the record keeps the block as sent and its evidence lines."""
        c, uid, u = logged_in_retail()
        oid = u["orders"][0]
        c.tool("get_order_details", order_id=oid)
        pm = sorted(u["payment_methods"])[0]
        step = c.step("modify_pending_order_payment", {"order_id": oid, "payment_method_id": pm})
        f = FakeLLM()
        use_fake(f)
        part = guard("retail").decide(step)["direct_facts"]
        self.assertTrue(part["block"])
        self.assertIn(part["block_text"], f.calls[0]["user"])
        self.assertEqual(part["block_sha256"], DF.sha256_text(part["block_text"]))
        self.assertEqual(len(part["block_text"]), part["block_chars"])
        self.assertTrue(part["evidence_lines"])
        for e in part["evidence_lines"]:
            self.assertEqual(set(e), {"fact", "part", "source", "text"})
            self.assertIn(f"    {e['text']}", part["block_text"])
        n_ev = sum(part["evidence"][k] for k in ("db_lines", "arg_lines", "event_lines"))
        self.assertEqual(len(part["evidence_lines"]), n_ev)
        json.dumps(part)
        # no block: block_text is None, no evidence lines
        use_fake(FakeLLM())
        p2 = guard("retail").decide(Conv("retail").user("hello").step("respond", {"content": "Hi."}))["direct_facts"]
        if not p2["block"]:
            self.assertIsNone(p2["block_text"])
            self.assertEqual(p2["evidence_lines"], [])

    def test_state_error_fact_error_and_failure_give_direct_prompt(self):
        c, uid, u = logged_in_retail()
        c.msgs[-1] = dict(c.msgs[-1], content="someone_else_1234")          # a replay mismatch
        step = c.step("get_user_details", {"user_id": uid})
        f = FakeLLM()
        use_fake(f)
        rec = guard("retail").decide(step)
        part = rec["direct_facts"]
        self.assertFalse(part["block"])
        self.assertEqual(part["state_error"]["kind"], "replay_mismatch")
        self.assertTrue(part["left_out"]["user_authenticated"].startswith("state_error"))
        self.assertEqual(part["prompt_sha256"], part["direct_prompt_sha256"])
        self.assertNotIn(DF.BLOCK_TITLE, f.calls[0]["user"])
        # a fact error: that fact is left out, recorded
        c2, uid2, u2 = logged_in_retail()
        real = DF.F.evaluate

        def broken(entry, *a, name=None, **k):
            if name == "user_authenticated":
                raise DF.F.FactEvalError("planted")
            return real(entry, *a, name=name, **k)
        DF.F.evaluate = broken
        try:
            use_fake(FakeLLM())
            rec2 = guard("retail").decide(c2.step("get_user_details", {"user_id": uid2}))
        finally:
            DF.F.evaluate = real
        self.assertEqual(rec2["direct_facts"]["left_out"]["user_authenticated"], "fact_error")
        self.assertEqual(rec2["direct_facts"]["fact_errors"][0]["fact"], "user_authenticated")
        self.assertFalse(rec2["direct_facts"]["block"])
        # any failure of the facts code: no block, Direct's prompt, counted
        g = guard("retail")
        old = g.facts.block_for
        g.facts.block_for = lambda step: (_ for _ in ()).throw(RuntimeError("planted"))
        try:
            n0 = g.counters["facts_failures"]
            use_fake(FakeLLM())
            rec3 = g.decide(c2.step("get_user_details", {"user_id": uid2}))
        finally:
            g.facts.block_for = old
        self.assertEqual(g.counters["facts_failures"], n0 + 1)
        self.assertIn("planted", rec3["direct_facts"]["facts_failure"])
        self.assertEqual(rec3["direct_facts"]["prompt_sha256"], rec3["direct_facts"]["direct_prompt_sha256"])

    def test_guard_interface(self):
        c, uid, u = logged_in_retail()
        msg = {"role": "assistant", "content": None,
               "tool_calls": _call("x", "get_user_details", {"user_id": uid})["tool_calls"]}
        g = guard("retail")
        self.assertIsNone(g.new_episode())
        use_fake(FakeLLM())
        rec = g.check(None, list(c.msgs), msg, 3)
        self.assertEqual(rec["step_index"], 3)
        self.assertTrue(rec["direct_facts"]["block"])
        self.assertIsNone(g.commit(None, rec))
        self.assertEqual(g.name, "direct_facts_v3")


class TestLeaks(unittest.TestCase):
    def test_nothing_before_login_synthetic(self):
        c = Conv("retail")
        uid, u = retail_user(c.data)
        oid = u["orders"][0]
        c.user(f"Cancel order {oid}.")
        b = facts("retail").block_for(c.step("cancel_pending_order", {"order_id": oid, "reason": "ordered by mistake"}))
        self.assertFalse(b["info"]["logged_in"])
        for ln in block_lines(b["block"])[2:]:
            self.assertRegex(ln, LINE_BEFORE_LOGIN)
        order = c.data["orders"][oid]
        for v in (order["status"], uid, u["email"], order["payment_history"][0]["payment_method_id"]):
            self.assertNotIn(str(v), b["block"])

    def test_dev_sample_no_leak(self):
        before = after = 0
        for ch, step, v3, b in dev_sample():
            if not b["block"]:
                continue
            if not b["info"]["logged_in"]:
                before += 1
                for ln in block_lines(b["block"])[2:]:
                    self.assertRegex(ln, LINE_BEFORE_LOGIN, ch.ckey)
                continue
            after += 1
            me = DF.FB.logged_in_user(b["eval"]["state"], b["eval"]["view"], ch.domain)
            for r in b["info"]["shown_records"]:
                self.assertTrue(r["catalog"] or r["owner"] == me, (ch.ckey, r))
        self.assertGreater(before, 0)
        self.assertGreater(after, 0)


class TestValuesEqualV3(unittest.TestCase):
    def test_values_equal_the_v3_guard_on_development_checks(self):
        sample = dev_sample()
        by = collections.Counter(ch.domain for ch, _, _, _ in sample)
        self.assertGreaterEqual(len(sample), MIN_CHECKS)
        self.assertGreaterEqual(by["airline"], MIN_AIRLINE)
        self.assertGreaterEqual(by["retail"], MIN_AIRLINE)
        c = collections.Counter()
        for ch, step, v3, b in sample:
            ev = b["eval"]
            self.assertIsNone(ev["state_error"], ch.ckey)
            self.assertEqual(ev["fact_errors"], [], ch.ckey)
            vf = v3["facts"] or {}
            want = sorted(n for n in vf if DF.code_only(facts(ch.domain).entries[n]))
            self.assertEqual(ev["names"], want, ch.ckey)
            for n in ev["names"]:
                self.assertIs(ev["results"][n]["value"], vf[n]["value"], (ch.ckey, n))
                self.assertEqual(ev["kinds"][n], vf[n]["source"], (ch.ckey, n))
                c["facts compared"] += 1
            c["checks with a block"] += b["block"] is not None
            c["history cut"] += len(render_history(step.history)) > DF.HISTORY_CHARS
        COUNT.update({f"values: {k}": v for k, v in c.items()})
        COUNT["values: checks"] += len(sample)
        COUNT["values: airline checks"] += by["airline"]
        self.assertGreater(c["facts compared"], len(sample))


class TestZeroCalls(unittest.TestCase):
    def test_zz_no_client_no_network(self):
        self.assertEqual(COUNT["real client requested"], 0)
        self.assertEqual(COUNT["network connects"], 0)
        print("\n[direct_facts tests] counts:", json.dumps(dict(sorted(COUNT.items()))), flush=True)


if __name__ == "__main__":
    unittest.main()
