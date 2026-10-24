"""Part 10, subtask 5: unit tests of the guard "TGR + tracker" (guard/tgr_tracker.py) and the wrapper's safety rules.

A fake judge (guard/offline.py::FakeJudge) stands in for the LLM client behind TGR's judge call, so no test makes an
LLM call. The conversations are built from τ-bench's copied data and tool code (real outputs).

Run from predicate_correctness/:  python3 -B -m unittest tests.test_guard -v
Standard library only. The offline check on all luna_train_v5 retail records takes about 1-2 minutes.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from guard import offline, run_online, runner_path, tgr_tracker            # noqa: E402
from method_tgr.runtime import TGR, Conversation, TGRConfig, load_rule_set  # noqa: E402  (runner copy)
from repro_online.guards import make_step                                   # noqa: E402  (runner copy)
from repro_runtime import calls                                             # noqa: E402  (runner copy)
from state_tracker import paths, tau_copy                                   # noqa: E402
from state_tracker.state import load_db, run_tool                           # noqa: E402


class _NoLLM:
    """Installed whenever no fake judge is: any judge call fails loudly (never a real client, never a cache)."""
    model, max_output_tokens = "no-llm", 16000
    cache_dir = os.path.join(paths.OUTPUT_DIR, "_no_llm_never_written")

    def call(self, **_):
        raise AssertionError("an LLM call was attempted in a unit test")


calls._llm = _NoLLM()

DOMAIN = "retail"
RS_PATH = os.path.join(paths.RULES_DIR, DOMAIN, "rule_set.json")


def pending_order() -> tuple:
    """(order_id, user email) of the first pending order in τ-bench's retail data."""
    data = load_db(DOMAIN)
    oid = sorted(o for o, x in data["orders"].items() if x["status"] == "pending")[0]
    return oid, data["users"][data["orders"][oid]["user_id"]]["email"]


def history(login: bool = True, show_order: bool = True, tamper: bool = False) -> list:
    """A retail conversation: the user asks to cancel; the agent finds the user and shows the order."""
    oid, email = pending_order()
    db = load_db(DOMAIN)
    msgs = [{"role": "system", "content": tau_copy.policy_text(DOMAIN)},
            {"role": "user", "content": f"Hi, please cancel my order {oid}. My email is {email}."}]

    def call(name, args, cid):
        out = run_tool(DOMAIN, db, name, args)
        if tamper and name == "get_order_details":
            out = out.replace('"pending"', '"delivered"')
        msgs.append({"role": "assistant", "content": None, "tool_calls": [
            {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]})
        msgs.append({"role": "tool", "tool_call_id": cid, "name": name, "content": out})

    if login:
        call("find_user_id_by_email", {"email": email}, "c1")
    if show_order:
        call("get_order_details", {"order_id": oid}, "c2")
    return msgs


def tool_msg(name: str, args: dict) -> dict:
    return {"role": "assistant", "content": None, "tool_calls": [
        {"id": "c9", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def cancel_msg(reason: str | None = "no longer needed") -> dict:
    oid, _ = pending_order()
    args = {"order_id": oid}
    if reason is not None:
        args["reason"] = reason
    return tool_msg("cancel_pending_order", args)


class GuardTestBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tools = tau_copy.tools_info(DOMAIN)
        cls.guard = tgr_tracker.TGRTrackerGuard(DOMAIN, cls.tools)
        cls.code = cls.guard.tgr.code_types

    def tearDown(self):
        calls._llm = _NoLLM()

    @staticmethod
    def allow(n: str) -> bool:
        """The value of a predicate that satisfies its rules of cancel_pending_order ('NOT x' in a rule: false)."""
        rs = load_rule_set(RS_PATH)
        negated = {x for r in rs["rules"] if r["id"] in rs["circuits"]["cancel_pending_order"]
                   for x in rs["predicates"] if f"NOT {x}" in r["logic"]}
        return n not in negated

    def fake(self, values_for):
        """Install a fake judge; values_for(name) gives each predicate's value."""
        judge = offline.FakeJudge(lambda names: {n: values_for(n) for n in names})
        offline.install_fake(judge)
        return judge

    def run_guard(self, guard, executed, msg):
        conv = guard.new_episode()
        return guard.check(conv, executed, msg, sum(m["role"] == "assistant" for m in executed))

    def run_plain_tgr(self, executed, msg, rs=None):
        """Frozen TGR as the copied runner runs it (method_tgr.runtime.TGR, same config)."""
        tgr = TGR(rs or load_rule_set(RS_PATH), self.tools, TGRConfig(actionable_feedback=True, judge_effort="medium",
                                                                       epsilon=0.1))
        idx = sum(m["role"] == "assistant" for m in executed)
        return tgr.step(Conversation(), make_step(executed, msg, idx))


class TestReplace(GuardTestBase):

    def test_code_type_values_are_replaced(self):
        """The judge says false for every code-type predicate; the tracker sees the login, the pending order and an
        allowed reason, so it says true. The tracker's values are used, and the decision follows them."""
        judge = self.fake(lambda n: False if n in self.code else self.allow(n))
        rec = self.run_guard(self.guard, history(), cancel_msg())
        tr = rec["tracker"]
        code = sorted(n for n in rec["judge"] if n in self.code)
        self.assertEqual(code, ["cancellation_reason_is_allowed", "order_status_checked_pending", "user_authenticated"])
        self.assertEqual(len(judge.calls), 1)
        self.assertFalse(tr["judge_skipped"])
        self.assertEqual(sorted(tr["replaced"]), code)
        self.assertEqual(sorted(tr["changed"]), code)
        for n in code:
            self.assertIs(tr["judge_values"][n], False)
            self.assertIs(tr["tracker_values"][n]["value"], True)
            self.assertIs(rec["judge"][n]["value"], True)
            self.assertEqual(rec["judge"][n]["source"], "tracker")
            self.assertTrue(rec["judge"][n]["evidence"].startswith("State tracker:"))
            self.assertIs(rec["trace_position"][n], True)
        for n in rec["judge"]:
            if n not in self.code:
                self.assertEqual(rec["judge"][n]["source"], "judge")
        self.assertTrue(rec["action_allowed"])
        self.assertEqual(tr["lookup_errors"], [])
        # frozen TGR with the same judge answers blocks the call
        self.fake(lambda n: False if n in self.code else self.allow(n))
        self.assertFalse(self.run_plain_tgr(history(), cancel_msg())["action_allowed"])

    def test_tracker_false_blocks_with_tracker_evidence(self):
        """No login in the conversation: the tracker says user_authenticated is false (the judge said true)."""
        self.fake(self.allow)
        rec = self.run_guard(self.guard, history(login=False), cancel_msg())
        self.assertIs(rec["judge"]["user_authenticated"]["value"], False)
        self.assertIn("user_authenticated", rec["tracker"]["changed"])
        self.assertFalse(rec["action_allowed"])
        self.assertIn("user_authenticated = false", rec["feedback_text"])
        self.assertIn("State tracker:", rec["feedback_text"])

    def test_unknown_lookup_keeps_judge_value(self):
        """Version (b): no reason argument, so the reason lookup gives unknown; the judge's value is kept."""
        for jv in (True, False):
            self.fake(lambda n, jv=jv: jv if n == "cancellation_reason_is_allowed" else self.allow(n))
            rec = self.run_guard(self.guard, history(), cancel_msg(reason=None))
            tr = rec["tracker"]
            self.assertIsNone(tr["tracker_values"]["cancellation_reason_is_allowed"]["value"])
            self.assertNotIn("cancellation_reason_is_allowed", tr["replaced"])
            self.assertIs(rec["judge"]["cancellation_reason_is_allowed"]["value"], jv)
            self.assertEqual(rec["judge"]["cancellation_reason_is_allowed"]["source"], "judge")
            self.assertFalse(tr["judge_skipped"])

    def test_lookup_error_falls_back_to_judge(self):
        """A lookup that fails is logged, its predicate keeps the judge's value, and the conversation goes on."""
        guard = tgr_tracker.TGRTrackerGuard(DOMAIN, self.tools)
        guard.tgr.lookups = dict(guard.tgr.lookups)
        guard.tgr.lookups["order_status_checked_pending"] = dict(guard.tgr.lookups["order_status_checked_pending"],
                                                                 expr="len(args['order_id'])")   # an int: an error
        self.fake(lambda n: False if n == "order_status_checked_pending" else True)
        rec = self.run_guard(guard, history(), cancel_msg())
        tr = rec["tracker"]
        self.assertEqual([e["predicate"] for e in tr["lookup_errors"]], ["order_status_checked_pending"])
        self.assertIn("error", tr["tracker_values"]["order_status_checked_pending"])
        self.assertIs(rec["judge"]["order_status_checked_pending"]["value"], False)
        self.assertEqual(rec["judge"]["order_status_checked_pending"]["source"], "judge")
        self.assertIn("user_authenticated", tr["replaced"])

    def test_state_mismatch_falls_back_to_judge(self):
        """A saved tool output that the replay cannot reproduce: every code-type value keeps the judge's value, and
        the decision is frozen TGR's."""
        self.fake(lambda n: False if n == "user_authenticated" else True)
        rec = self.run_guard(self.guard, history(tamper=True), cancel_msg())
        tr = rec["tracker"]
        self.assertEqual(tr["replaced"], [])
        self.assertTrue(tr["lookup_errors"] and tr["lookup_errors"][0]["error"].startswith("state:"))
        self.assertEqual(tr["state"]["mismatches"], 1)
        self.fake(lambda n: False if n == "user_authenticated" else True)
        plain = self.run_plain_tgr(history(tamper=True), cancel_msg())
        self.assertEqual((rec["action_allowed"], rec["margin"]), (plain["action_allowed"], plain["margin"]))


class TestJudgeSkipped(GuardTestBase):
    """With the frozen rule sets every tool's rules have a conversation or mixed predicate, so the judge is never
    skipped in real runs. Here a rule set keeps only the rule of get_order_details that uses user_authenticated
    (a code type) only."""

    def reduced_guard(self):
        rs = copy.deepcopy(load_rule_set(RS_PATH))
        base = tgr_tracker.TGRTrackerGuard(DOMAIN, self.tools)
        aspm = base.tgr.aspm
        keep = [r for r in rs["circuits"]["get_order_details"]
                if aspm.rules[r].atoms - aspm.action_predicates <= set(self.code)]
        self.assertEqual(len(keep), 1)
        rs["circuits"]["get_order_details"] = keep
        guard = tgr_tracker.TGRTrackerGuard(DOMAIN, self.tools)
        guard.tgr = tgr_tracker.TrackerTGR(rs, self.tools, guard.config, DOMAIN, base.tgr.lookups,
                                           {n: {"type": t} for n, t in self.code.items()})
        return guard

    def test_judge_skipped_when_every_predicate_is_code(self):
        guard = self.reduced_guard()
        oid, _ = pending_order()
        judge = self.fake(lambda n: True)
        rec = self.run_guard(guard, history(show_order=False), tool_msg("get_order_details", {"order_id": oid}))
        self.assertEqual(judge.calls, [])
        self.assertTrue(rec["tracker"]["judge_skipped"])
        self.assertIsNone(rec["tracker"]["judge_values"])
        self.assertEqual(rec["usage"]["n_llm_calls"], 0)
        self.assertEqual(rec["usage"]["cost_usd"], 0)
        self.assertTrue(rec["action_allowed"])
        # no login: the tracker gives false, still no judge call, and the call is blocked
        rec = self.run_guard(guard, history(login=False, show_order=False),
                             tool_msg("get_order_details", {"order_id": oid}))
        self.assertEqual(judge.calls, [])
        self.assertTrue(rec["tracker"]["judge_skipped"])
        self.assertFalse(rec["action_allowed"])
        self.assertIn("State tracker:", rec["feedback_text"])

    def test_judge_called_when_a_lookup_gives_unknown(self):
        """Every predicate is a code type, but one lookup gives unknown: the judge is asked (version b)."""
        guard = self.reduced_guard()
        guard.tgr.lookups = dict(guard.tgr.lookups)
        guard.tgr.lookups["user_authenticated"] = dict(guard.tgr.lookups["user_authenticated"],
                                                       expr="args['no_such_argument']", if_missing="unknown")
        oid, _ = pending_order()
        judge = self.fake(lambda n: True)
        rec = self.run_guard(guard, history(show_order=False), tool_msg("get_order_details", {"order_id": oid}))
        self.assertEqual(len(judge.calls), 1)
        self.assertFalse(rec["tracker"]["judge_skipped"])
        self.assertIs(rec["judge"]["user_authenticated"]["value"], True)
        self.assertEqual(rec["judge"]["user_authenticated"]["source"], "judge")

    def test_real_rule_sets_never_skip(self):
        for d in paths.DOMAINS:
            g = tgr_tracker.TGRTrackerGuard(d, tau_copy.tools_info(d))
            aspm = g.tgr.aspm
            for act in aspm.action_predicates:
                names = {n for r in aspm.circuit([act]) for n in aspm.rules[r].atoms} - aspm.action_predicates
                if names:
                    self.assertFalse(names <= set(g.tgr.code_types), (d, act))


class TestSameAsTGRWhenTrackerAgrees(GuardTestBase):

    def compare(self, conv_value):
        """The judge gives the tracker's values for the code types: decision, margin, rules, feedback and the judge
        prompt must equal frozen TGR's."""
        def values(n):
            return True if n in self.code else conv_value(n)
        j1 = self.fake(values)
        mine = self.run_guard(self.guard, history(), cancel_msg())
        j2 = self.fake(values)
        plain = self.run_plain_tgr(history(), cancel_msg())
        self.assertEqual(mine["tracker"]["changed"], [])
        for k in ("action_allowed", "margin", "allowed_eps0", "violated_rules", "unknown_predicates", "circuit",
                  "matched", "trace_position", "mln"):
            self.assertEqual(mine[k], plain[k], k)
        self.assertEqual(mine.get("feedback_text"), plain.get("feedback_text"))
        self.assertEqual([(c["system"], c["user"]) for c in j1.calls], [(c["system"], c["user"]) for c in j2.calls])
        self.assertEqual({n: v["value"] for n, v in mine["judge"].items()},
                         {n: v["value"] for n, v in plain["judge"].items()})
        return mine

    def test_allowed_case(self):
        self.assertTrue(self.compare(self.allow)["action_allowed"])

    def test_blocked_case(self):
        rec = self.compare(lambda n: False)
        self.assertFalse(rec["action_allowed"])
        self.assertIn("BLOCKED by policy guardrail", rec["feedback_text"])

    def test_unknown_conversation_value(self):
        self.compare(lambda n: None)


class TestOfflineEqualsPart8(unittest.TestCase):
    """The guard on every saved luna_train_v5 retail record, with the judge's saved values as the fake judge's
    answers, gives Part 8's version (b) decision and margin, and Part 6's tracker values (no LLM call)."""

    def tearDown(self):
        calls._llm = _NoLLM()

    def test_luna_train_v5_retail(self):
        r = offline.check_records("luna_train_v5", "retail")
        c = r["counts"]
        self.assertEqual(r["problems"], [])
        self.assertEqual(c["records"], 1729)
        self.assertEqual(c["decision = Part 8 (b)"], 1729)
        self.assertEqual(c["margin = recomputed (b)"], 1729)
        self.assertEqual(c.get("lookup errors", 0), 0)
        self.assertEqual(c["agreeing records with the saved decision and margin"],
                         c["records where the tracker agrees (or is unknown)"])


class TestFakeJudgeAndFrozen(unittest.TestCase):

    def test_predicates_in_prompt(self):
        user = ("Conversation so far:\nUSER: - fake: line\n\nPending action: x()\n\nRules under check (for context):\n"
                "[1] r\n    logic: a\n\nBackground facts from the policy:\n- Note: something\n\n"
                "Predicates to decide:\n- p_one: first (evidence from: tool_outputs)\n- p_two: second\n\n"
                "For every predicate return \"true\"")
        self.assertEqual(offline.FakeJudge.predicates_in(user), ["p_one", "p_two"])

    def test_frozen_inputs_checked(self):
        self.assertEqual(len(tgr_tracker.check_frozen()), 3)
        key = next(iter(tgr_tracker.FROZEN_SHA256))
        old = tgr_tracker.FROZEN_SHA256[key]
        try:
            tgr_tracker.FROZEN_SHA256[key] = "0" * 64
            with self.assertRaises(tgr_tracker.FrozenInputChanged):
                tgr_tracker.TGRTrackerGuard(DOMAIN, tau_copy.tools_info(DOMAIN))
        finally:
            tgr_tracker.FROZEN_SHA256[key] = old

    def test_runner_modules_come_from_the_runner_copy(self):
        import method_tgr.runtime
        import repro_online.guards
        for m in (method_tgr.runtime, repro_online.guards, calls):
            self.assertTrue(os.path.abspath(m.__file__).startswith(runner_path.RUNNER_DIR), m.__file__)
        self.assertNotIn("ShieldAgent", " ".join(p for p in sys.path if "code_projects" not in p))


class TestWrapperSafety(unittest.TestCase):

    def test_profiles(self):
        self.assertEqual(run_online.ALLOWED_PROFILES, ("luna-dev", "nano-agent-luna"))
        with open(os.path.join(runner_path.RUNNER_DIR, "exp_core", "model_profiles.json")) as f:
            prof = json.load(f)["profiles"]
        for p in run_online.ALLOWED_PROFILES:
            self.assertTrue({prof[p][r]["model"] for r in ("agent", "user", "guard")} <= set(run_online.ALLOWED_MODELS))
        with self.assertRaises(SystemExit):                     # argparse refuses grok-eval before anything runs
            run_online.main(["--profile", "grok-eval", "--env", "retail", "--tag", "x"])

    def test_task_lists(self):
        with open(paths.SPLITS_FILE) as f:
            split = json.load(f)
        for env in paths.DOMAINS:
            s = split[env]["split"]
            train = run_online.task_list(env, "train", None)
            val = run_online.task_list(env, "val", None)
            self.assertEqual(train, sorted(int(k) for k, v in s.items() if v == "train"))
            self.assertEqual(val, sorted(int(k) for k, v in s.items() if v == "val"))
            test_ids = [int(k) for k, v in s.items() if v == "test"]
            with self.assertRaises(SystemExit):
                run_online.task_list(env, "test", None)
            with self.assertRaises(SystemExit):
                run_online.task_list(env, "train", ",".join(map(str, train[:1] + test_ids[:1])))
        self.assertEqual((len(run_online.task_list("airline", "train", None)),
                          len(run_online.task_list("retail", "train", None)),
                          len(run_online.task_list("airline", "val", None)),
                          len(run_online.task_list("retail", "val", None))), (20, 46, 10, 23))

    def test_paths_stay_in_output(self):
        p = run_online.resolve_paths("tagx", "retail", "tgr_tracker")
        self.assertEqual(p["episodes"], os.path.join(paths.OUTPUT_DIR, "online", "tagx", "retail", "tgr_tracker",
                                                     "episodes.jsonl"))
        self.assertEqual(p["structured_cache"], os.path.join(paths.OUTPUT_DIR, "_llmcache", "tagx", "structured"))
        for bad in ({"out_root": os.path.expanduser("~/ShieldAgent/output/tgr/online")},
                    {"out_root": PC_DIR}, {"cache_root": os.path.join(PC_DIR, "from_shieldagent")}):
            with self.assertRaises(SystemExit):
                run_online.resolve_paths("tagx", "retail", "tgr_tracker", **bad)
        with self.assertRaises(SystemExit):
            run_online.resolve_paths("../x", "retail", "tgr_tracker")


_WRITE_GUARD_PROBE = r"""
import json, os, sys
sys.dont_write_bytecode = True
pc = sys.argv[1]
sys.path.insert(0, pc)
from guard import write_guard
write_guard.install()
res = {}
inside = os.path.join(pc, "output", "logs", "p10_write_guard_probe.tmp")
with open(inside, "w") as f:
    f.write("x")
os.remove(inside)
res["inside"] = "ok"
outside = os.path.join(pc, "write_guard_probe.tmp")
try:
    open(outside, "w").close()
    res["outside"] = "WRITTEN"
    os.remove(outside)
except PermissionError:
    res["outside"] = "refused"
try:
    os.makedirs(os.path.join(pc, "from_shieldagent", "runner", "output", "probe"))
    res["mkdir_runner"] = "MADE"
except PermissionError:
    res["mkdir_runner"] = "refused"
try:
    open(os.path.expanduser("~/ShieldAgent/AGENTS.md")).close()
    res["read_shieldagent"] = "READ"
except PermissionError:
    res["read_shieldagent"] = "refused"
res["refused"] = len(write_guard.REFUSED)
print(json.dumps(res))
"""


class TestWriteGuard(unittest.TestCase):

    def test_write_guard_in_a_fresh_process(self):
        r = subprocess.run([sys.executable, "-B", "-c", _WRITE_GUARD_PROBE, PC_DIR], capture_output=True, text=True,
                           cwd=PC_DIR, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        res = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(res, {"inside": "ok", "outside": "refused", "mkdir_runner": "refused",
                               "read_shieldagent": "refused", "refused": 3})


if __name__ == "__main__":
    unittest.main()
