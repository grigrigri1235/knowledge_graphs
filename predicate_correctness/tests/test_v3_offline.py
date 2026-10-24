"""Tracker v3 part 1: tests of fork/offline_v3.py (the offline base) and of the Gate 0 driver's row logic.

No LLM call and no network: the guards run offline with given judge values; the built conversations use τ-bench's
copied data and tool code. A few tests read one saved conversation (read only).

Run from predicate_correctness/:  python3 -B -m unittest tests.test_v3_offline -v
Standard library only.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import unittest

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from fork import offline_v3 as O                                         # noqa: E402
from fork import points_tgr as PT                                        # noqa: E402
from repro_core.taubench_steps import render_history                     # noqa: E402  (runner copy)
from repro_runtime import calls                                          # noqa: E402  (runner copy)
from state_tracker import paths, tau_copy                                # noqa: E402
from state_tracker.state import load_db, run_tool                        # noqa: E402


class _NoLLM:
    """Any judge call fails loudly (the offline base never calls the judge)."""
    model, max_output_tokens = "no-llm", 16000
    cache_dir = os.path.join(paths.OUTPUT_DIR, "_no_llm_never_written")

    def call(self, **_):
        raise AssertionError("an LLM call was attempted in a unit test")


calls._llm = _NoLLM()

DOMAIN = "retail"
TASK = 2           # a retail task of τ-bench's test file labelled "train" in splits.json (only its key is used)


def call_msg(name: str, args: dict, cid: str) -> dict:
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def text_msg(text: str) -> dict:
    return {"role": "assistant", "content": text, "tool_calls": None}


def judge_values(n_try: int) -> dict:
    """The fake judge: right on everything, except at the cancel: it misses the login (n_try >= 1), and at the first
    cancel try it also says the user did not confirm (a block both guards share)."""
    rs = O.offline_guards(DOMAIN).rule_set
    vals = {n: True for n in rs["predicates"]}
    for n in ("request_is_for_another_user", "response_performs_task_for_another_user",
              "user_specific_information_disclosed", "request_cannot_be_handled_within_scope"):
        vals[n] = False
    if n_try >= 1:
        vals["user_authenticated"] = False
    if n_try == 1:
        vals["user_explicitly_confirmed_pending_action"] = False
    return {n: {"value": v, "evidence": f"fake evidence for {n}"} for n, v in vals.items()}


def pending_order():
    db = load_db(DOMAIN)
    oid = sorted(o for o, x in db["orders"].items() if x["status"] == "pending")[0]
    return oid, db["users"][db["orders"][oid]["user_id"]]["email"]


def built_episode(guard: str) -> dict:
    """A retail conversation made by the episode loop's rules (repro_online/episode.py) with a registered guard of
    fork/offline_v3.py as the source guard. Script: login by email, show the order, ask for a yes, cancel (try 1),
    cancel (try 2), a last reply. Saved as JSON would save it."""
    tgr = O.guard_for(guard, DOMAIN)
    oid, email = pending_order()
    db = load_db(DOMAIN)
    messages = [{"role": "system", "content": tau_copy.policy_text(DOMAIN)},
                {"role": "user", "content": f"Hi, please cancel my order {oid}. My email is {email}."}]
    executed = list(messages)
    cancel = {"order_id": oid, "reason": "no longer needed"}
    script = [(call_msg("find_user_id_by_email", {"email": email}, "c1"), None, 0),
              (call_msg("get_order_details", {"order_id": oid}, "c2"), None, 0),
              (text_msg(f"I can cancel order {oid} (reason: no longer needed). Shall I go ahead (yes/no)?"), "yes", 0),
              (call_msg("cancel_pending_order", cancel, "c3"), None, 1),
              (call_msg("cancel_pending_order", cancel, "c4"), None, 2),
              (text_msg("Is there anything else?"), "###STOP###", 0)]
    attempts, n_exec, consecutive, past = [], 0, 0, []
    for msg, reply, n_try in script:
        rec = O.run_guard(tgr, executed, msg, n_exec, past, judge_values(n_try))
        name, kwargs = O.call_of(msg)
        blocked = not rec["action_allowed"]
        override = blocked and consecutive >= 3
        att = {"exec_step": n_exec, "attempt": consecutive + 1, "action": name, "kwargs": kwargs,
               "agent_text": msg.get("content") or "", "blocked": blocked and not override, "cap_override": override,
               "executed_prefix_len": len(executed), "guard": json.loads(json.dumps(rec))}
        if blocked and not override:
            consecutive += 1
            fb = rec.get("feedback_text") or PT.DEFAULT_FEEDBACK
            att["feedback"] = fb
            attempts.append(att)
            answer = ({"role": "system", "content": fb} if name == "respond" else
                      {"role": "tool", "tool_call_id": msg["tool_calls"][0]["id"], "name": name, "content": fb})
            messages += [msg, answer]
            continue
        consecutive = 0
        if name == "respond":
            new = [msg, {"role": "user", "content": reply}]
            att["observation"] = reply
        else:
            obs = run_tool(DOMAIN, db, name, copy.deepcopy(kwargs))
            new = [msg, {"role": "tool", "tool_call_id": msg["tool_calls"][0]["id"], "name": name, "content": obs}]
            att["observation"] = obs
        attempts.append(att)
        past.append(rec["trace_position"])
        messages += new
        executed += new
        n_exec += 1
    saved_guard = {"frozen": "tgr", "v2": "tgr_tracker"}[guard]
    ep = {"task_index": TASK, "trial": 0, "env": DOMAIN, "guard": saved_guard, "profile": "luna-dev",
          "models": {"agent": "gpt-6-luna", "user": "gpt-6-luna", "guard": "gpt-6-luna"},
          "messages": messages, "executed": executed, "attempts": attempts, "reward": 0.0, "error": None}
    return json.loads(json.dumps(ep))


def conversation(ep: dict, dataset: str) -> O.SavedConversation:
    spec = O.dataset_spec(dataset)
    return O._conversation(spec, 0, os.path.join(PC_DIR, "x.jsonl"), 0, ep, DOMAIN, O.splits())


_EPS = {}


def episode(guard: str) -> dict:
    if guard not in _EPS:
        _EPS[guard] = built_episode(guard)
    return copy.deepcopy(_EPS[guard])


class TestBuiltConversations(unittest.TestCase):
    def test_script_has_a_block_and_an_allow(self):
        for guard, want in (("frozen", [True, True, True, False, False, True]),
                            ("v2", [True, True, True, False, True, True])):
            ep = episode(guard)
            self.assertEqual([a["guard"]["action_allowed"] for a in ep["attempts"]], want, guard)

    def test_both_guards_reproduce_their_saved_checks(self):
        for guard, dataset in (("frozen", "partner.luna_train_v5"), ("v2", "ours.p10_luna_train")):
            conv = conversation(episode(guard), dataset)
            self.assertEqual(conv.source_guard, guard)
            n = 0
            for ch in conv.checks():
                res = O.decide(ch)
                cmp = O.compare_with_saved(ch, res)
                self.assertTrue(cmp["ok"], (guard, ch.ckey, cmp["differs"]))
                self.assertEqual(cmp["differs_extra"], [], (guard, ch.ckey))
                self.assertIsNone(O.miss_class(ch, cmp))
                self.assertEqual(res["decision"], ch.saved_decision)
                if ch.blocked:
                    self.assertEqual(res["feedback_text"], ch.sent_message)
                    self.assertTrue(res["violated_rules"])
                else:
                    self.assertIsNone(res["feedback_text"])
                n += 1
            self.assertEqual(n, 6)

    def test_block_and_allow_result_shape(self):
        conv = conversation(episode("frozen"), "partner.luna_train_v5")
        checks = list(conv.checks())
        block, allow = O.decide(checks[3]), O.decide(checks[1])
        self.assertEqual((block["decision"], block["allowed"]), ("block", False))
        self.assertIn("BLOCKED by policy guardrail", block["feedback_text"])
        self.assertEqual(block["facts"]["user_authenticated"], {"value": False, "source": "judge"})
        self.assertEqual((allow["decision"], allow["feedback_text"], allow["violated_rules"]), ("allow", None, []))
        self.assertEqual(set(block), {"guard", "decision", "allowed", "margin", "violated_rules", "facts", "unknown",
                                      "feedback_text", "record"})

    def test_v2_on_a_frozen_source_uses_the_tracker(self):
        """Frozen TGR blocks the 2nd cancel try (the judge missed the login); TGR + tracker allows it: the login
        event sets user_authenticated (source tracker)."""
        conv = conversation(episode("frozen"), "partner.luna_train_v5")
        ch = list(conv.checks())[4]
        self.assertEqual(ch.saved_decision, "block")
        res = O.decide(ch, guard="v2")
        self.assertEqual(res["decision"], "allow")
        self.assertEqual(res["facts"]["user_authenticated"], {"value": True, "source": "tracker"})
        self.assertEqual(res["record"]["tracker"]["changed"], ["user_authenticated"])

    def test_frozen_on_a_v2_source_uses_the_judges_own_values(self):
        conv = conversation(episode("v2"), "ours.p10_luna_train")
        ch = list(conv.checks())[4]
        self.assertEqual(ch.saved_decision, "allow")
        judged, info = ch.saved_judge_detail()
        self.assertIs(judged["user_authenticated"]["value"], False)
        self.assertEqual(info["evidence"]["user_authenticated"], "missing")      # changed by the tracker, no cache
        self.assertEqual(O.decide(ch, guard="frozen")["decision"], "block")

    def test_misses_get_a_class(self):
        conv = conversation(episode("v2"), "ours.p10_luna_train")
        ch = list(conv.checks())[3]
        ch.attempt["guard"]["margin"] = (ch.saved["margin"] or 0.0) + 0.5
        cmp = O.compare_with_saved(ch, O.decide(ch))
        self.assertEqual(cmp["differs"], ["margin"])
        self.assertEqual(O.miss_class(ch, cmp), "bug")
        ch.attempt["guard"]["attempts"] = 2
        self.assertEqual(O.miss_class(ch, cmp), "judge_retry")
        ch.attempt["guard"]["attempts"] = 1
        ch.attempt["guard"]["tracker"]["lookup_errors"] = [{"predicate": None, "error": "state: AttributeError"}]
        self.assertEqual(O.miss_class(ch, cmp), "source_run_fallback")
        # the same saved tracker failure outside our p10 runs is not a listed class
        conv2 = conversation(episode("v2"), "ours.p10_luna_train")
        conv2.dataset = "stage_a.luna.tgr_tracker"
        ch2 = list(conv2.checks())[3]
        ch2.attempt["guard"]["tracker"]["lookup_errors"] = [{"predicate": None, "error": "x"}]
        self.assertEqual(O.miss_class(ch2, cmp), "bug")
        self.assertEqual(O.miss_class(ch2, None, error="ValueError: x"), "bug")

    def test_message_bytes_and_cap_override(self):
        conv = conversation(episode("frozen"), "partner.luna_train_v5")
        ch = list(conv.checks())[3]
        ch.attempt["feedback"] = ch.attempt["feedback"] + " "
        cmp = O.compare_with_saved(ch, O.decide(ch))
        self.assertEqual(cmp["differs"], ["message"])
        self.assertFalse(cmp["pass"])
        ch.attempt.update(blocked=False, cap_override=True)               # a cap override counts on its decision only
        ch.attempt["guard"]["margin"] = 9.0
        cmp = O.compare_with_saved(ch, O.decide(ch))
        self.assertEqual(cmp["differs"], ["margin"])
        self.assertTrue(cmp["pass"])

    def test_arguments_come_from_the_message(self):
        conv = conversation(episode("v2"), "ours.p10_luna_train")
        ch = list(conv.checks())[4]
        ch.attempt["kwargs"] = {"order_id": "#W0000000", "reason": "ordered by mistake"}
        self.assertEqual(ch.tool, "cancel_pending_order")
        self.assertNotEqual(ch.args["order_id"], "#W0000000")
        self.assertTrue(O.compare_with_saved(ch, O.decide(ch))["ok"])
        st = ch.state()
        self.assertEqual(st.pending["args"], ch.args)
        self.assertEqual([e["tool"] for e in st.events], ["find_user_id_by_email", "get_order_details"])


class TestKeysAndTrace(unittest.TestCase):
    def test_ckey_and_check_idx(self):
        ep = episode("frozen")
        conv = conversation(ep, "partner.luna_train_v5")
        self.assertEqual(conv.conv_id, f"{DOMAIN}/{TASK}/0")
        self.assertEqual(conv.task_key, (DOMAIN, "partner_train", TASK, 0))
        for ch in conv.checks():
            self.assertEqual(ch.ckey, f"partner.luna_train_v5|{DOMAIN}/{TASK}/0|{ch.check_idx}")
            self.assertIs(ch.msg, ep["messages"][2 + 2 * ch.check_idx])
            self.assertEqual(ch.history, ep["executed"][:ep["attempts"][ch.check_idx]["executed_prefix_len"]])
        self.assertEqual([c.check_idx for c in conv.checks()], list(range(6)))
        self.assertEqual([c.check_idx for c in conv.checks(judged_only=True)],
                         [i for i, a in enumerate(ep["attempts"]) if a["guard"].get("judge")])

    def test_past_trace_skips_blocked_attempts(self):
        ep = episode("frozen")
        checks = list(conversation(ep, "partner.luna_train_v5").checks())
        tps = [a["guard"]["trace_position"] for a in ep["attempts"]]
        self.assertEqual(checks[4].past, tps[:3])                        # attempt 3 was blocked
        self.assertEqual(checks[5].past, tps[:3])
        for ch in checks:
            self.assertEqual(len(ch.past), ch.saved["trace_len_before"])

    def test_stage_b_yields_only_the_attempts_after_the_fork(self):
        ep = episode("frozen")
        parts = ["prefix", "prefix", "prefix", "fork", "after", "after"]
        for a, p in zip(ep["attempts"], parts):
            a["fork_part"] = p
        fork = {"domain": DOMAIN, "task_index": TASK, "trial": 1, "run": "luna_train_v5", "source": "saved_tgr",
                "agent": "luna"}
        ep.update(fork_id="saved_tgr.luna_train_v5.retail.test2.trial1.att3", branch="A", guard="tgr_frozen",
                  fork=fork, source_trial=1, task_split="test", fork_attempt_index=3)
        ep["try"] = 0
        conv = O._conversation(O.dataset_spec("stage_b"), 0, "x.json", None, ep, DOMAIN, O.splits())
        self.assertEqual(conv.conv_id, "saved_tgr.luna_train_v5.retail.test2.trial1.att3/A/0")
        self.assertEqual(conv.task_key, (DOMAIN, "partner_train", TASK, 1))
        self.assertEqual(conv.source_guard, "frozen")
        self.assertEqual([c.check_idx for c in conv.checks()], [4, 5])
        self.assertEqual(conv.side, O.DEV)
        self.assertEqual(list(conv.checks())[0].ckey, f"stage_b|{conv.conv_id}|4")


class TestBinsAndLength(unittest.TestCase):
    def test_bin_edges(self):
        self.assertEqual([O.length_bin(n) for n in (0, 11999, 12000, 24000, 24001)],
                         ["<12k", "<12k", "12-24k", "12-24k", ">24k"])

    def test_length_is_the_uncut_judge_view(self):
        hist = [{"role": "system", "content": "policy " * 10000}, {"role": "user", "content": "a" * 30000}]
        n = O.history_length(hist)
        self.assertEqual(n, len("USER: " + "a" * 30000))                # the system message is left out
        self.assertEqual(O.length_bin(n), ">24k")
        cut = render_history(hist, max_chars=24000)                       # the judge's cut view (runtime.py:127)
        self.assertEqual(len(cut), 24001)
        self.assertEqual(len(render_history(hist[:1] + [{"role": "user", "content": "a" * 23994}],
                                            max_chars=24000)), 24000)   # 24,000 exactly: not cut


class TestSplitRule(unittest.TestCase):
    def test_split_names(self):
        labels = O.splits()
        self.assertEqual(O.split_name("train", "retail", 7, labels), "tau_train")
        tr = next(t for t, v in labels["airline"].items() if v == "train")
        va = next(t for t, v in labels["airline"].items() if v == "val")
        self.assertEqual(O.split_name(None, "airline", tr, labels), "partner_train")
        self.assertEqual(O.split_name("test", "airline", va, labels), "partner_val")

    def test_partner_test_group_is_refused(self):
        labels = O.splits()
        te = next(t for t, v in labels["retail"].items() if v == "test")
        with self.assertRaises(O.ForbiddenTestGroup):
            O.split_name(None, "retail", te, labels)
        with self.assertRaises(O.ForbiddenTestGroup):
            O.split_name("test", "retail", 10 ** 6, labels)               # no label
        ep = episode("frozen")
        ep["task_index"] = te
        with self.assertRaises(O.ForbiddenTestGroup):
            conversation(ep, "partner.luna_train_v5")

    def test_holdout_rule(self):
        self.assertEqual(O.side_of("ours.p10_luna_val"), O.HOLDOUT)
        self.assertEqual(O.side_of("partner.luna_val"), O.HOLDOUT)
        for d in ("ours.p10_luna_train", "ours.p10_nano_train", "partner.luna_train_v5", "partner.nano_train",
                  "stage_a.luna.tgr_frozen", "stage_a.nano.tgr_tracker"):
            self.assertEqual(O.side_of(d), O.DEV, d)
        self.assertEqual(O.side_of("stage_b", "p10_luna_val", "online_tracker.p10_luna_val.airline.test8.trial2.att15"),
                         O.HOLDOUT)
        self.assertEqual(O.side_of("stage_b", "luna_val", "saved_tgr.luna_val.retail.test3.trial0.att2"), O.HOLDOUT)
        self.assertEqual(O.side_of("stage_b", "p10_luna_train", "online_tracker.p10_luna_train.retail.test1.trial0."
                                                                 "att1"), O.DEV)
        self.assertEqual(O.side_of("stage_b", "stage_a/luna/tgr_frozen",
                                   "stage_a.stage_a_luna_tgr_frozen.retail.train4.trial0.att3"), O.DEV)
        with self.assertRaises(O.DataProblem):
            O.side_of("stage_b", "p10_luna_train", "online_tracker.p10_luna_val.x")


class TestRegistry(unittest.TestCase):
    def test_registered_guards(self):
        self.assertIn("frozen", O.GUARDS)
        self.assertIn("v2", O.GUARDS)
        self.assertIs(O.guard_for("frozen", DOMAIN), O.offline_guards(DOMAIN).frozen)
        self.assertIs(O.guard_for("v2", DOMAIN), O.offline_guards(DOMAIN).tracker)
        with self.assertRaises(ValueError):
            O.guard_for("v9", DOMAIN)
        with self.assertRaises(ValueError):
            O.register_guard("frozen", lambda d: None)

    def test_a_new_guard_plugs_in(self):
        name = "_test_frozen_copy"
        O.register_guard(name, lambda d: O.offline_guards(d).frozen)
        try:
            conv = conversation(episode("frozen"), "partner.luna_train_v5")
            ch = list(conv.checks())[3]
            self.assertEqual(O.decide(ch, guard=name)["decision"], "block")
            self.assertEqual(O.decide(ch, guard=name)["guard"], name)
        finally:
            O.GUARDS.pop(name, None)
            O._GUARD_OBJECTS.pop((name, DOMAIN), None)

    def test_datasets(self):
        self.assertEqual(len(O.DATASETS), 11)
        self.assertEqual(O.DATASETS[-1], "stage_b")
        self.assertEqual(O.dataset_spec("partner.luna_val").files,
                         tuple((d, paths.episodes_path("luna_val", d)) for d in paths.DOMAINS))
        for d in O.DATASETS:
            for _, p in O.dataset_spec(d).files:
                self.assertNotIn("before_resume", p)
                self.assertNotIn(os.sep + "none" + os.sep, p)
                self.assertNotIn(os.sep + "direct" + os.sep, p)


class TestSavedData(unittest.TestCase):
    """One saved conversation per guard kind (read only): the source guard reproduces it."""

    def first_conversation(self, dataset: str) -> O.SavedConversation:
        return next(iter(O.iter_conversations([dataset])))

    def test_partner_frozen_conversation(self):
        conv = self.first_conversation("partner.luna_val")
        self.assertEqual((conv.side, conv.split, conv.agent, conv.saved_guard), (O.HOLDOUT, "partner_val", "luna",
                                                                                 "tgr"))
        for ch in conv.checks():
            self.assertTrue(O.compare_with_saved(ch, O.decide(ch))["ok"], ch.ckey)

    def test_ours_tracker_conversation(self):
        conv = self.first_conversation("ours.p10_luna_val")
        self.assertEqual(conv.source_guard, "v2")
        for ch in conv.checks(judged_only=True):
            cmp = O.compare_with_saved(ch, O.decide(ch))
            self.assertTrue(cmp["ok"], (ch.ckey, cmp["differs"]))

    def test_gate0_row(self):
        from scoring import v3_p1_gate0 as G
        conv = self.first_conversation("partner.luna_val")
        ch = next(conv.checks(judged_only=True))
        line, cls, cmp, err = G.check_row(ch)
        self.assertIsNone(cls)
        self.assertIsNone(err)
        self.assertEqual(line["gate0"], "pass")
        self.assertEqual(set(line), {"ckey", "dataset", "domain", "split", "task_id", "trial", "agent", "source_guard",
                                     "tool", "judged", "saved_decision", "blocked", "cap_override", "exec_step",
                                     "attempt", "history_len", "bin", "side", "gate0"})
        self.assertEqual(line["history_len"], len(render_history(ch.history)))


if __name__ == "__main__":
    unittest.main()
