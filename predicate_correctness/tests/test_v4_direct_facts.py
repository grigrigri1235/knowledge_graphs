"""Tracker v4: tests of the Direct + facts v4 guard (guard/direct_facts_v4.py, lesson L2.6).

No LLM call and no network: the runner's LLM seam (repro_runtime.calls.shared_llm) gives a fake LLM that records the
prompts and returns fixed decisions; the real client getter and every socket connect raise and are counted (0 at the
end). Data: made-up conversations only, whose tool outputs are τ-bench's own on a fresh copy of the database, and
made-up fact entries and results. No saved conversation of any run is read (purity: no B2, B3 or hold-out data).

  signs      made-up states (true / false / unknown facts, AND / OR parts, parts that did not run, before and after
             login): every fact line is "- <fact>: YES | NO | UNKNOWN"; a false fact's words and a false part's text
             never appear on a line without "NO"; a part that did not run shows no text; "true" / "false" never;
  regression the v3 bug (a gold user's "The user U is a regular member" printed with "(false)" far from the text):
             v4 prints "part a = NO: ... ? NO" and the database value 'membership = "gold"';
  pending    for every action of both rule sets, before and after login: the block shows exactly the code-only facts
             of the rules whose actions include the pending action (each shown fact's rules meet them);
  same as v3 for a fixed input: the system message, the call (stage, schema, effort) and the record equal v3's; the
             user message equals v3's once the v4 block is swapped for v3's block; no block -> byte-identical; the
             facts and values equal v3's; the constants (prompt, effort, history, title, note) and the code-only facts
             equal v3's;
  provider   FACTS_SOURCE "v3" is the default; "v4" raises FactsSourceNotReady until registered; an injected or
             registered provider is used and recorded (facts_source).

Run from predicate_correctness/:
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v4_direct_facts \\
        -v > output/logs/v4_p1d_tests.txt 2>&1
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

from guard import direct_facts_v3 as DF3                                 # noqa: E402
from guard import direct_facts_v4 as DF                                  # noqa: E402
from repro_online.guards import make_step                                # noqa: E402  (runner copy)
from repro_runtime import calls                                          # noqa: E402  (runner copy)
from state_tracker import paths, tau_copy                                # noqa: E402

DOMAINS = ("retail", "airline")
COUNT: collections.Counter = collections.Counter()
SIGNS = (DF.SIGN_YES, DF.SIGN_NO, DF.SIGN_UNKNOWN)
FACT_LINE = re.compile(r"^- ([a-z0-9 ]+): (YES|NO|UNKNOWN)$")
PART_LINE = re.compile(r'^  - part ([A-Za-z0-9_]+) = (YES|NO|UNKNOWN): is it so that ".*"\? \2 \([a-z -]+\)$')
NOT_RAN_LINE = re.compile(r"^  - part ([A-Za-z0-9_]+): not checked \((not needed for the value|not run)\)$")
LINE_BEFORE_LOGIN = re.compile(r"^(- [a-z0-9 ]+: (YES|NO|UNKNOWN)"
                               r"|  \(a problem: [a-z0-9_, ]+; the value is the rule's safe default\))$")
V3_VALUE = re.compile(r"(: (true|false|not set)$|\((true|false|not needed)\):)")


# ----------------------------------------------------------------------------------------------- safety and fakes
class FakeLLM:
    """The runner's LLM object, faked: records every call, returns a fixed decision. Never a client."""
    model, max_output_tokens = "fake-llm", 16000
    cache_dir = os.path.join(paths.OUTPUT_DIR, "_fake_llm_never_written")      # only read by the seam, never made

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
_G = {}


def guard(domain, v=4):
    if (domain, v) not in _G:
        _G[(domain, v)] = (DF if v == 4 else DF3).DirectFactsGuard(domain)
    return _G[(domain, v)]


def facts(domain, v=4):
    return guard(domain, v).facts


def _call(cid, name, args):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


class Conv:
    """A made-up conversation whose tool outputs are τ-bench's own (run on a fresh copy of the data)."""

    def __init__(self, domain):
        self.domain = domain
        self.data = tau_copy.load_data_fresh(domain)
        self.tools = tau_copy.tools(domain)
        self.msgs = [{"role": "system", "content": tau_copy.policy_text(domain)}]
        self.n = 0

    def user(self, text):
        self.msgs.append({"role": "user", "content": text})
        return self

    def tool(self, name, **args):
        self.n += 1
        cid = f"call_{self.n}"
        out = self.tools[name].invoke(data=self.data, **args)
        self.msgs.append(_call(cid, name, args))
        self.msgs.append({"role": "tool", "tool_call_id": cid, "name": name, "content": out})
        return out

    def step(self, name, args):
        msg = {"role": "assistant", "content": None, "tool_calls": _call("pending", name, args)["tool_calls"]} \
            if name != "respond" else {"role": "assistant", "content": args.get("content", "")}
        return make_step(list(self.msgs), msg, 0)


def logged_in_retail():
    c = Conv("retail")
    for uid, u in sorted(c.data["users"].items()):
        if u.get("orders") and u.get("email"):
            break
    c.user(f"Hi, my email is {u['email']}.")
    assert c.tool("find_user_id_by_email", email=u["email"]) == uid
    return c, uid, u


def airline_user(data, membership):
    for uid, u in sorted(data["users"].items()):
        if u.get("membership") == membership and u.get("reservations"):
            return uid, u
    raise AssertionError(f"no {membership} user")


def airline_compensation(membership):
    """A made-up airline conversation: the user gives their id and a reservation; the agent offers a certificate."""
    c = Conv("airline")
    uid, u = airline_user(c.data, membership)
    rid = u["reservations"][0]
    c.user(f"Hi, my user id is {uid}. My flight in reservation {rid} was delayed.")
    c.tool("get_reservation_details", reservation_id=rid)
    return c, uid, rid, c.step("respond", {"content": "I can offer you a $50 certificate."})


def logged_in_airline():
    c = Conv("airline")
    uid = sorted(c.data["users"])[0]
    c.user(f"Hello, my user id is {uid}.")
    return c, uid


def rule_facts(fb, tool):
    """The facts of the rules whose actions include `tool` (straight from the rule set) and those rules' ids."""
    rids = {str(r["id"]) for r in fb.rule_set["rules"] if tool in (r.get("actions") or [])}
    names = {n for rid in rids for n in fb.aspm.rules[rid].atoms} - fb.aspm.action_predicates
    return names, rids


def check_signed(test, block, entries, ev, where=""):
    """The L2.6 checks on one block: signed fact lines; every part text only with its sign; no v3 wording."""
    lines = block.split("\n")
    test.assertEqual(lines[:2], [DF.BLOCK_TITLE, DF.BLOCK_NOTE], where)
    for ln in lines[2:]:
        test.assertIsNone(V3_VALUE.search(ln), (where, ln))
    shown = [FACT_LINE.match(ln) for ln in lines if ln.startswith("- ")]
    test.assertTrue(all(shown), (where, [ln for ln in lines if ln.startswith("- ")]))
    test.assertEqual([m.group(1) for m in shown], [DF.FB.words(n) for n in ev["names"]], where)
    starts = [i for i, ln in enumerate(lines) if ln.startswith("- ")] + [len(lines)]
    for k, (m, n) in enumerate(zip(shown, ev["names"])):
        test.assertEqual(m.group(2), DF._sign(ev["results"][n]["value"]), (where, n))
        if ev["results"][n]["value"] is False:            # a false fact's words: only on lines with NO
            for ln in lines:
                if DF.FB.words(n) in ln:
                    test.assertIn(f" {DF.SIGN_NO}", ln, (where, n, ln))
        r = ev["results"][n]
        section = lines[starts[k] + 1: starts[k + 1]]     # this fact's own lines
        for pid, part in entries[n]["parts"].items():
            pr = (r.get("parts") or {}).get(pid) or {}
            text = DF.first_sentence(part.get("plain"))
            probe = text[:40]
            hits = [ln for ln in section if probe and probe in ln and not ln.startswith("    ")]   # not evidence
            ran = pr.get("how") in DF.FB.PART_RAN
            if not ran:
                test.assertEqual(hits, [], (where, n, pid))  # a part that did not run: no text at all
                COUNT["parts not run (no text)"] += 1
                continue
            for ln in hits:
                pm = PART_LINE.match(ln)
                test.assertTrue(pm, (where, n, pid, ln))
                test.assertEqual(pm.group(2), DF._sign(pr.get("value")), (where, n, pid, ln))
                if pr.get("value") is False:
                    test.assertTrue(ln.startswith(f"  - part {pid} = NO: ") and ln.split("? ")[-1].startswith("NO "),
                                    (where, n, pid, ln))
                    COUNT["false parts shown with NO"] += 1
            # (the full plain text after its first sentence is never printed)
            rest = " ".join(str(part.get("plain") or "").split())[len(text) + 2:]
            if len(rest) > 30:
                test.assertNotIn(rest[:30], block, (where, n, pid))


# ----------------------------------------------------------------------------------------------- made-up provider
PLAIN = {"a": "The user is a regular member (membership 'regular' in the database). More details follow here.",
         "b": "The order is pending (status 'pending' in the database). The rest of the text.",
         "c": "The user gave an order id in a message. Further notes."}


def made_up_entries():
    def part(src, key):
        return {"source": src, "plain": PLAIN[key], "expr": "db('user', args['user_id'])['membership'] == 'regular'",
                "question": None, "about": None}
    return {
        "and_fact": {"combine": "a AND b", "parts": {"a": part("structure", "a"), "b": part("database", "b")},
                     "sources": ["structure", "database"]},
        "or_fact": {"combine": "a OR (b AND c)", "parts": {"a": part("structure", "a"), "b": part("database", "b"),
                                                           "c": part("arguments", "c")},
                    "sources": ["structure", "database", "arguments"]},
        "one_part_fact": {"combine": "c", "parts": {"c": part("arguments", "c")}, "sources": ["arguments"]},
        "unknown_fact": {"combine": "a AND b", "parts": {"a": part("structure", "a"), "b": part("database", "b")},
                         "sources": ["structure", "database"]},
    }


def made_up_results():
    def pr(v, how="value"):
        return {"value": v, "how": how}
    return {
        "and_fact": {"value": False, "problems": [], "parts": {"a": pr(False), "b": pr(True)}},
        "or_fact": {"value": True, "problems": [],
                    "parts": {"a": pr(True), "b": pr(None, "not_needed"), "c": pr(None, "not_run")}},
        "one_part_fact": {"value": True, "problems": [], "parts": {"c": pr(True)}},
        "unknown_fact": {"value": None, "problems": [{"kind": "missing_argument"}],
                         "parts": {"a": pr(None, "problem"), "b": pr(False)}},
    }


class MadeUpProvider:
    """A facts provider (the V3CodeFacts contract) with made-up entries and results."""
    name = "made_up"

    def __init__(self, domain="retail", results=None, **kw):
        self.domain = domain
        self.entries = made_up_entries()
        self.code_facts = sorted(self.entries)
        self.results = results if results is not None else made_up_results()
        self.rule_set, self.aspm = None, None

    def circuit_names(self, tool):
        return sorted(self.results)

    def block_names(self, tool):
        return sorted(self.results), {}

    def evaluate(self, step):
        names = sorted(self.results)
        return {"tool": "x", "args": {"user_id": "u1"}, "names": names, "left_out": {},
                "results": copy.deepcopy(self.results),
                "kinds": {n: "code" if not self.results[n]["problems"] else "blocking_value" for n in names},
                "state": None, "view": None, "state_error": None, "fact_errors": [], "state_info": None,
                "seconds": 0.0}


# ----------------------------------------------------------------------------------------------- tests
class TestSigns(unittest.TestCase):
    def _block(self, logged_in, results=None):
        fb = DF.FactsBlock("retail", provider=MadeUpProvider(results=results))
        fb._me = (lambda st, view: "u1") if logged_in else (lambda st, view: None)
        b = fb.block_for(None)
        return fb, b

    def test_made_up_after_login(self):
        fb, b = self._block(True)
        block, ev = b["block"], b["eval"]
        check_signed(self, block, fb.entries, ev, "made-up after login")
        lines = block.split("\n")
        self.assertIn("- and fact: NO", lines)
        self.assertIn("- or fact: YES", lines)
        self.assertIn("- unknown fact: UNKNOWN", lines)
        self.assertIn("  (YES only when: a AND b)", lines)
        self.assertIn("  (YES only when: a OR (b AND c))", lines)
        self.assertNotIn("  (YES only when: c)", lines)                  # one part: no join line
        self.assertIn('  - part a = NO: is it so that "The user is a regular member (membership \'regular\' in the '
                      'database)"? NO (message structure)', lines)
        self.assertIn('  - part b = YES: is it so that "The order is pending (status \'pending\' in the database)"? '
                      'YES (database)', lines)
        self.assertIn("  - part b: not checked (not needed for the value)", lines)
        self.assertIn("  - part c: not checked (not run)", lines)
        self.assertIn("  - part a = UNKNOWN: is it so that \"The user is a regular member (membership 'regular' in the "
                      "database)\"? UNKNOWN (message structure)", lines)
        self.assertIn("  (a problem: missing_argument; the value is the rule's safe default)", lines)
        self.assertNotIn("More details follow here", block)
        self.assertNotIn("true", block)
        self.assertNotIn("false", block)
        for ln in lines[2:]:                 # every line is a fact, a join, a part, a note or evidence
            self.assertTrue(FACT_LINE.match(ln) or PART_LINE.match(ln) or NOT_RAN_LINE.match(ln)
                            or ln.startswith("  (") or ln.startswith("    "), ln)

    def test_made_up_before_login(self):
        fb, b = self._block(False)
        lines = b["block"].split("\n")
        self.assertEqual(lines[2:], ["- and fact: NO", "- one part fact: YES", "- or fact: YES", "- unknown fact: UNKNOWN",
                                     "  (a problem: missing_argument; the value is the rule's safe default)"])
        for ln in lines[2:]:
            self.assertRegex(ln, LINE_BEFORE_LOGIN)
        check_signed(self, b["block"], fb.entries, b["eval"], "made-up before login")

    def test_every_sign_combination(self):
        """All true / false / unknown values of the AND fact's two parts and of the fact itself."""
        n = 0
        for fv in (True, False, None):
            for av in (True, False, None):
                for bv in (True, False, None):
                    res = {"and_fact": {"value": fv, "problems": [] if fv is not None else [{"kind": "type_error"}],
                                        "parts": {"a": {"value": av, "how": "value" if av is not None else "problem"},
                                                  "b": {"value": bv, "how": "value"}}}}
                    for login in (True, False):
                        fb, b = self._block(login, res)
                        check_signed(self, b["block"], fb.entries, b["eval"], (fv, av, bv, login))
                        n += 1
        self.assertEqual(n, 54)

    def test_v3_shows_the_bug_on_the_same_made_up_state(self):
        """The same made-up state in v3's wording: the false part's text sits on a line without NO (the bug)."""
        p = MadeUpProvider()
        fb3 = DF3.FactsBlock.__new__(DF3.FactsBlock)
        fb3.domain, fb3.entries = "retail", p.entries
        ev = p.evaluate(None)
        orig = DF3.FB.logged_in_user
        DF3.FB.logged_in_user = lambda st, view, domain: "u1"
        try:
            block3, _ = fb3.render(ev)
        finally:
            DF3.FB.logged_in_user = orig
        bad = [ln for ln in block3.split("\n") if "The user is a regular member" in ln and " NO" not in ln]
        self.assertTrue(bad)                               # e.g. "  - message structure (false): The user is a ..."


class TestRegression(unittest.TestCase):
    def test_gold_user_regular_member_line(self):
        c, uid, rid, step = airline_compensation("gold")
        b3 = facts("airline", 3).block_for(step)["block"]
        b = facts("airline").block_for(step)
        block = b["block"]
        self.assertIn("message structure (false): The user U is a regular member", b3)     # v3's misleading line
        self.assertIn("- compensation is prohibited for relevant reservation: NO", block.split("\n"))
        self.assertIn('  - part a = NO: is it so that "The user U is a regular member (membership \'regular\' in the '
                      'database)"? NO (message structure)', block.split("\n"))
        self.assertIn(f'    user {uid}: membership = "gold"', block.split("\n"))
        self.assertNotIn("(false)", block)
        check_signed(self, block, facts("airline").entries, b["eval"], "gold")
        print(f"\n[v4 direct_facts] made-up gold user {uid}, reservation {rid}\n--- v3 block ---\n{b3}\n"
              f"--- v4 block ---\n{block}", flush=True)

    def test_each_membership(self):
        for m in ("regular", "silver", "gold"):
            c, uid, rid, step = airline_compensation(m)
            b = facts("airline").block_for(step)
            r = b["eval"]["results"]["compensation_is_prohibited_for_relevant_reservation"]
            pa = r["parts"]["a"]["value"]
            self.assertIs(pa, m == "regular", m)
            self.assertIn(f'    user {uid}: membership = "{m}"', b["block"].split("\n"), m)
            check_signed(self, b["block"], facts("airline").entries, b["eval"], m)


class TestPendingActionOnly(unittest.TestCase):
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
                    names, rids = rule_facts(fb, act)
                    covered |= rids
                    want = sorted(n for n in names if DF.code_only(fb.entries[n]))
                    b = fb.block_for(step)
                    ev = b["eval"]
                    self.assertIsNone(ev["state_error"], (d, act))
                    self.assertEqual(ev["names"], want, (d, act))
                    for n in ev["names"]:                  # each shown fact is used by a rule of this action
                        self.assertTrue(set(map(str, fb.entries[n].get("rules") or [])) & rids, (d, act, n))
                    if not want:
                        self.assertIsNone(b["block"], (d, act))
                        continue
                    self.assertEqual(b["info"]["logged_in"], login, (d, act))
                    check_signed(self, b["block"], fb.entries, ev, (d, act, login))
                    other = set(fb.code_facts) - set(want)
                    shown = {ln[2:].split(":")[0] for ln in b["block"].split("\n") if ln.startswith("- ")}
                    self.assertFalse(shown & {DF.FB.words(n) for n in other}, (d, act))
                    COUNT["action blocks checked"] += 1
            self.assertEqual(covered, {str(r["id"]) for r in fb.rule_set["rules"]}, d)   # every rule


class TestSameAsV3(unittest.TestCase):
    def test_constants_and_code_facts(self):
        for k in ("EFFORT", "HISTORY_CHARS", "STAGE", "SCHEMA_NAME", "TEMPLATE", "BLOCK_TITLE", "BLOCK_NOTE", "SEP",
                  "ACTION_FIELD", "MAX_PLAIN_CHARS", "POLICY_REL", "POLICY_SHA256", "DIRECT_FILES", "SUMS_REL"):
            self.assertEqual(getattr(DF, k), getattr(DF3, k), k)
        self.assertEqual((DF.NAME, DF.VERSION), ("direct_facts_v4", "v4.p1d.1"))
        self.assertNotEqual(DF.VERSION, DF3.VERSION)
        self.assertEqual(DF.FACTS_SOURCE, "v3")
        for d in DOMAINS:
            self.assertEqual(facts(d).code_facts, facts(d, 3).code_facts, d)
            self.assertEqual(facts(d).source, "v3")
            for n, e in facts(d).entries.items():
                self.assertIs(DF.code_only(e), DF3.code_only(e), (d, n))
        self.assertEqual(DF.template_tail(), DF3.template_tail())
        self.assertEqual(DF.check_direct_inputs(), DF3.check_direct_inputs())

    @staticmethod
    def _strip(rec):
        r = {k: v for k, v in rec.items() if k not in ("seconds", "direct_facts")}
        r["usage"] = {k: v for k, v in r["usage"].items() if k != "api_seconds"}
        return r

    def _cases(self):
        c, uid, u = logged_in_retail()
        oid = u["orders"][0]
        c.tool("get_order_details", order_id=oid)
        pm = sorted(u["payment_methods"])[0]
        out = [("retail", c.step("get_order_details", {"order_id": oid})),
               ("retail", c.step("respond", {"content": "Here is your order."})),
               ("retail", c.step("cancel_pending_order", {"order_id": oid, "reason": "no longer needed"})),
               ("retail", c.step("modify_pending_order_payment", {"order_id": oid, "payment_method_id": pm})),
               ("retail", Conv("retail").user("hi").step("get_user_details", {"user_id": uid})),
               ("airline", airline_compensation("gold")[3]),
               ("airline", airline_compensation("regular")[3]),
               ("airline", Conv("airline").user("What airports do you fly to?").step("list_all_airports", {}))]
        return out

    def test_prompt_is_v3s_but_for_the_block(self):
        n_block = n_none = 0
        for d, step in self._cases():
            for safe in (True, False):
                f3, f4 = FakeLLM(safe), FakeLLM(safe)
                use_fake(f3)
                r3 = guard(d, 3).decide(step)
                use_fake(f4)
                r4 = guard(d).decide(step)
                a, b = f3.calls[0], f4.calls[0]
                self.assertEqual({k: v for k, v in a.items() if k != "user"},
                                 {k: v for k, v in b.items() if k != "user"}, d)   # system, schema, effort, stage
                self.assertEqual(self._strip(r3), self._strip(r4))               # parsing and feedback
                p3, p4 = r3["direct_facts"], r4["direct_facts"]
                self.assertEqual(p4["direct_prompt_sha256"], p3["direct_prompt_sha256"])
                self.assertEqual(p4["facts"], p3["facts"])                        # the same facts and values
                self.assertEqual(p4["left_out"], p3["left_out"])
                self.assertEqual((p4["version"], p4["facts_source"]), (DF.VERSION, "v3"))
                if not p3["block"]:
                    self.assertFalse(p4["block"])
                    self.assertEqual(a["user"], b["user"])                         # byte-identical
                    self.assertEqual(p4["prompt_sha256"], p3["prompt_sha256"])
                    n_none += 1
                    continue
                self.assertTrue(p4["block"])
                swapped = b["user"].replace(DF.SEP + p4["block_text"], DF.SEP + p3["block_text"], 1)
                self.assertEqual(swapped, a["user"])                              # only the block differs
                self.assertEqual(b["user"].replace(DF.SEP + p4["block_text"], "", 1),
                                 a["user"].replace(DF3.SEP + p3["block_text"], "", 1))
                self.assertNotEqual(p4["block_text"], p3["block_text"])
                self.assertEqual(p4["block_sha256"], DF.sha256_text(p4["block_text"]))
                n_block += 1
        self.assertGreater(n_block, 0)
        self.assertGreater(n_none, 0)
        COUNT["prompt pairs compared"] += n_block + n_none


class TestProvider(unittest.TestCase):
    def test_switch_and_injection(self):
        self.assertIsInstance(facts("retail").provider, DF.V3CodeFacts)
        with self.assertRaises(DF.FactsSourceNotReady):
            DF.FactsBlock("retail", source="v4")
        with self.assertRaises(ValueError):
            DF.FactsBlock("retail", source="v9")
        old = dict(DF.FACTS_PROVIDERS)
        try:
            DF.register_facts_provider("v4", lambda domain, **kw: MadeUpProvider(domain))
            fb = DF.FactsBlock("retail", source="v4")
            self.assertIsInstance(fb.provider, MadeUpProvider)
            old_src = DF.FACTS_SOURCE
            DF.FACTS_SOURCE = "v4"                         # the one switch
            try:
                g = DF.DirectFactsGuard("retail")
            finally:
                DF.FACTS_SOURCE = old_src
            self.assertIsInstance(g.facts.provider, MadeUpProvider)
        finally:
            DF.FACTS_PROVIDERS.clear()
            DF.FACTS_PROVIDERS.update(old)
        with self.assertRaises(DF.FactsSourceNotReady):
            DF.FactsBlock("retail", source="v4")
        g = DF.DirectFactsGuard("retail", facts_provider=MadeUpProvider("retail"))
        g.facts._me = lambda st, view: "u1"
        f = FakeLLM()
        use_fake(f)
        rec = g.decide(Conv("retail").user("hi").step("respond", {"content": "Hello."}))
        part = rec["direct_facts"]
        self.assertEqual(part["facts_source"], "made_up")
        self.assertTrue(part["block"])
        self.assertIn("- and fact: NO", f.calls[0]["user"])
        with self.assertRaises(ValueError):
            DF.FactsBlock("airline", provider=MadeUpProvider("retail"))

    def test_build(self):
        g = DF.build("retail", frozen_table={})
        self.assertEqual((g.info["guard"], g.info["version"], g.info["facts_source"]),
                         ("direct_facts_v4", DF.VERSION, "v3"))
        self.assertEqual(g.name, "direct_facts_v4")
        self.assertEqual(g.info["code_facts"], facts("retail", 3).code_facts)

    def test_failure_gives_direct_prompt(self):
        g = DF.DirectFactsGuard("retail", facts_provider=MadeUpProvider("retail"))
        g.facts.provider.evaluate = lambda step: (_ for _ in ()).throw(RuntimeError("planted"))
        use_fake(FakeLLM())
        rec = g.decide(Conv("retail").user("hi").step("respond", {"content": "Hello."}))
        self.assertIn("planted", rec["direct_facts"]["facts_failure"])
        self.assertEqual(rec["direct_facts"]["facts_source"], "made_up")
        self.assertEqual(rec["direct_facts"]["prompt_sha256"], rec["direct_facts"]["direct_prompt_sha256"])


class TestZeroCalls(unittest.TestCase):
    def test_zz_no_client_no_network(self):
        self.assertEqual(COUNT["real client requested"], 0)
        self.assertEqual(COUNT["network connects"], 0)
        print("\n[v4 direct_facts tests] counts:", json.dumps(dict(sorted(COUNT.items()))), flush=True)


if __name__ == "__main__":
    unittest.main()
