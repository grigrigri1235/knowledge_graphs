"""Tests for state_tracker/load_steps.py (Part 2). Standard library only, no LLM calls.

Run from predicate_correctness/:  python3 -B -m unittest tests.test_load_steps -v

The hand-made episode tests use plain facts of the input (which attempts have a judge, which ran), not judgements.
The tests on the saved files run only after `python3 -m state_tracker.load_steps` has written them.
"""
from __future__ import annotations

import collections
import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_tracker import load_steps as ls  # noqa: E402
from state_tracker import paths  # noqa: E402


def _call(i: int, name: str, args: dict) -> dict:
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def _tool(i: int, name: str, out: str) -> dict:
    return {"role": "tool", "tool_call_id": f"c{i}", "name": name, "content": out}


def _guard(step: int, kind: str, name: str, judge=None, allowed: bool = True) -> dict:
    tp = {"find_user_id_by_email": False, "get_order_details": False, "cancel_pending_order": False, "respond": False}
    tp[name] = True
    g = {"step_index": step, "kind": kind, "name": name, "action_text": f"{name}(...)", "matched": [name],
         "trace_position": tp, "circuit": [], "action_allowed": allowed, "margin": None, "epsilon": 0.1,
         "violated_rules": [], "trace_len_before": step, "usage": {"n_llm_calls": 0, "cache_hits": 0, "cost_usd": 0.0}}
    if judge is not None:
        g.update({"circuit": ["1"], "judge": judge, "margin": 0.0 if allowed else -0.5, "allowed_eps0": allowed,
                  "unknown_predicates": [], "mln": []})
        tp.update({k: v["value"] for k, v in judge.items()})
    return g


def _attempt(step, n, action, kwargs, prefix, guard, blocked=False, cap=False, obs=None) -> dict:
    a = {"exec_step": step, "attempt": n, "action": action, "kwargs": kwargs, "agent_text": "", "blocked": blocked,
         "cap_override": cap, "executed_prefix_len": prefix, "guard": guard}
    if blocked:
        a["feedback"] = "BLOCKED by policy guardrail."
    else:
        a["observation"] = obs
    return a


def make_episode() -> dict:
    """4 executed steps; step 2 is blocked once and then runs (with an error output)."""
    cancel = {"order_id": "#W1", "reason": "no longer needed"}
    executed = [
        {"role": "system", "content": "policy"}, {"role": "user", "content": "Cancel my order #W1."},
        _call(1, "find_user_id_by_email", {"email": "a@b.c"}), _tool(1, "find_user_id_by_email", "a_1"),
        _call(2, "get_order_details", {"order_id": "#W1"}), _tool(2, "get_order_details", '{"order_id": "#W1"}'),
        _call(4, "cancel_pending_order", cancel), _tool(4, "cancel_pending_order", "Error: non-pending order"),
        {"role": "assistant", "content": "It could not be cancelled."}, {"role": "user", "content": "###STOP###"},
    ]
    yes = {"user_authenticated": {"value": True, "evidence": "lookup worked"}}
    no = {"user_confirmed": {"value": False, "evidence": "no yes yet"}}
    attempts = [
        _attempt(0, 1, "find_user_id_by_email", {"email": "a@b.c"}, 2,
                 _guard(0, "tool_call", "find_user_id_by_email"), obs="a_1"),                     # no rules: no judge
        _attempt(1, 1, "get_order_details", {"order_id": "#W1"}, 4,
                 _guard(1, "tool_call", "get_order_details", yes), obs='{"order_id": "#W1"}'),
        _attempt(2, 1, "cancel_pending_order", cancel, 6,
                 _guard(2, "tool_call", "cancel_pending_order", no, allowed=False), blocked=True),  # blocked
        _attempt(2, 2, "cancel_pending_order", cancel, 6,
                 _guard(2, "tool_call", "cancel_pending_order", yes), obs="Error: non-pending order"),
        _attempt(3, 1, "respond", {"content": "It could not be cancelled."}, 8,
                 _guard(3, "respond", "respond", yes), obs="###STOP###"),
    ]
    return {"task_index": 7, "trial": 1, "n_exec_steps": 4, "models": {"agent": "a", "guard": "g"},
            "executed": executed, "attempts": attempts}


class HandMadeEpisode(unittest.TestCase):
    def setUp(self):
        self.ep = make_episode()
        self.recs = ls.episode_records("run", "retail", 0, self.ep, 1, "train")

    def test_one_record_per_judged_attempt(self):
        self.assertEqual([(r["exec_step"], r["attempt"]) for r in self.recs], [(1, 1), (2, 1), (2, 2), (3, 1)])

    def test_history_is_executed_prefix(self):
        self.assertEqual([r["history_len"] for r in self.recs], [4, 6, 6, 8])
        for r in self.recs:
            self.assertEqual(r["history"], self.ep["executed"][:r["history_len"]])
        # the blocked attempt is not in the history of the next try at the same step
        self.assertEqual(self.recs[1]["history"], self.recs[2]["history"])

    def test_past_trace_is_earlier_executed_steps(self):
        self.assertEqual([len(r["past_trace"]) for r in self.recs], [1, 2, 2, 3])
        self.assertTrue(self.recs[3]["past_trace"][2]["cancel_pending_order"])

    def test_flags(self):
        self.assertEqual([r["executed"] for r in self.recs], [True, False, True, True])
        self.assertEqual([r["api_error"] for r in self.recs], [False, False, True, False])
        self.assertIsNone(self.recs[1]["observation"])
        self.assertEqual(self.recs[3]["kind"], "respond")
        self.assertEqual(self.recs[0]["step_id"], "run/retail/task7/trial1/step1/attempt1")

    def test_checks_pass(self):
        self.assertEqual(ls.check_episode(self.ep, self.recs), collections.Counter())

    def test_checks_find_a_wrong_output(self):
        ep = copy.deepcopy(self.ep)
        ep["executed"][7]["content"] = "something else"
        recs = ls.episode_records("run", "retail", 0, ep, 1, "train")
        self.assertEqual(ls.check_episode(ep, recs)["executed[history_len + 1] is not the saved output"], 1)

    def test_checks_find_a_wrong_prefix(self):
        ep = copy.deepcopy(self.ep)
        ep["attempts"][4]["executed_prefix_len"] = 6
        recs = ls.episode_records("run", "retail", 0, ep, 1, "train")
        bad = ls.check_episode(ep, recs)
        self.assertGreater(bad["history_len != 2 + 2 * trace_len_before"], 0)

    def test_saved_form_drops_in_memory_fields(self):
        saved = ls.to_saved(self.recs[0])
        self.assertNotIn("history", saved)
        self.assertNotIn("past_trace", saved)
        json.dumps(saved)

    def test_trial_without_key(self):
        seen = collections.Counter()
        eps = [{"task_index": 3}, {"task_index": 5}, {"task_index": 3}, {"task_index": 3, "trial": 9}]
        self.assertEqual([ls.episode_trial(e, seen) for e in eps], [0, 0, 1, 9])


@unittest.skipUnless(all(os.path.exists(paths.steps_path(r, d)) for r, d in paths.RUN_DOMAINS),
                     "steps files not written yet")
class SavedFiles(unittest.TestCase):
    def test_read_back_equals_built(self):
        for run, domain in paths.RUN_DOMAINS:
            built = list(ls.iter_steps(run, domain))
            saved = list(ls.read_steps(run, domain))
            self.assertEqual(len(built), len(saved), (run, domain))
            for b, s in zip(built, saved):
                self.assertEqual(b, s, b["step_id"])

    def test_counts(self):
        for run, domain in paths.RUN_DOMAINS:
            recs = list(ls.read_steps(run, domain, with_history=False))
            values = sum(len(r["judge"]) for r in recs)
            blocked = sum(1 for r in recs if r["action_allowed"] is False)
            self.assertEqual(values, ls.EXPECTED[(run, domain)]["judge_values"], (run, domain))
            self.assertEqual(blocked, ls.EXPECTED[(run, domain)]["blocked"], (run, domain))
            self.assertTrue(all(r["split"] == "train" for r in recs))
            self.assertEqual(len({r["step_id"] for r in recs}), len(recs))


if __name__ == "__main__":
    unittest.main()
