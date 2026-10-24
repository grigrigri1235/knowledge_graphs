"""Tests for the online metrics and the interim check (scoring/v3_online_metrics.py, scoring/v3_online_interim.py;
docs/planning/tracker_v3/p13.md steps 4-5).

Built records only, plus the partner's saved TRAIN runs (from_shieldagent/runs/luna_train_v5, read-only) for the
reproduction of their published train numbers. Never a val run (the hold-out lock is tested), no LLM, no network.

Run from predicate_correctness/:
    /home/azureuser/miniconda3/bin/python3 -B -m unittest tests.test_v3_online_metrics -v
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

from scoring import v3_online_interim as I     # noqa: E402
from scoring import v3_online_metrics as M     # noqa: E402

SPLITS = M.load_splits()


def tasks_of(domain, split, n):
    return sorted(t for (d, t), s in SPLITS.items() if d == domain and s == split)[:n]


WRITE = {"name": "cancel_pending_order", "kwargs": {"order_id": "#W1", "reason": "no longer needed"}}


def rec(domain, task, trial, arm, reward=1.0, error=None, cost=0.01, attempts=None, actions=(WRITE,), cap=0):
    return {"env": domain, "task_index": task, "trial": trial, "arm": arm, "guard": arm, "reward": reward,
            "error": error, "cost": {"agent": cost, "user": 0.0, "guard": 0.0}, "attempts": attempts or [],
            "reward_info": {"actions": list(actions)}, "n_cap_overrides": cap}


def att(action, kwargs=None, blocked=False, cap=False, obs="ok", feedback=None, guard=None):
    a = {"action": action, "kwargs": kwargs or {}, "blocked": blocked, "cap_override": cap, "guard": guard}
    if blocked:
        a["feedback"] = feedback or "BLOCKED"
    else:
        a["observation"] = obs
    return a


def convs_of(recs):
    return M.latest(M.make_conv(r, SPLITS) for r in recs)


class TestLoading(unittest.TestCase):

    def test_test_group_refused(self):
        t = sorted(t for (d, t), s in SPLITS.items() if d == "retail" and s == "test")[0]
        with self.assertRaises(M.TestGroupRefused):
            M.make_conv(rec("retail", t, 0, "none"), SPLITS)

    def test_holdout_locked(self):
        with self.assertRaises(M.HoldOutLocked):
            M.load_partner_run(M.PARTNER_VAL)
        with self.assertRaises(M.HoldOutLocked):                      # the default is locked (audit A, 1)
            M.load_run_dirs([os.path.join(PC_DIR, "output", "online", "p10_luna_val")])
        with self.assertRaises(SystemExit):
            M.main(["partner-val"])
        self.assertTrue(M.is_saved_val_path(os.path.join(M.PARTNER_RUNS, "luna_val", "retail")))
        self.assertTrue(M.is_saved_val_path(os.path.join(M.PARTNER_RUNS, "some_val_copy")))
        self.assertFalse(M.is_saved_val_path(M.PARTNER_RUNS))        # the parent itself is not; each file below is
        self.assertFalse(M.is_saved_val_path(os.path.join(M.PARTNER_RUNS, "luna_train_v5")))
        self.assertFalse(M.is_saved_val_path(os.path.join(PC_DIR, "output", "eval_v3", "B2v", "B2v_x_1")))

    def _p14_folder(self, root, step="B2"):
        """A p14-style run folder, <root>/<step>/<run_id>/<arm>/episodes_shard0of1.jsonl, with val task lines."""
        t = tasks_of("retail", "val", 1)[0]
        run = os.path.join(root, step, f"{step}_20261024T000000Z_abcd1234")
        for a in M.ARMS:
            os.makedirs(os.path.join(run, a))
            with open(os.path.join(run, a, "episodes_shard0of1.jsonl"), "w") as f:
                f.write(json.dumps(dict(rec("retail", t, 0, a), task_group="val", step=step, unit_attempt=1,
                                        run_id=os.path.basename(run))) + "\n")
        return run

    def test_val_lock_by_path_not_task_group(self):
        """A folder named like the partner's saved val run is refused (run, raw lines, interim); a p14-style run
        folder with val task lines loads without any flag."""
        with tempfile.TemporaryDirectory() as d:
            ok = self._p14_folder(os.path.join(d, "eval_v3"), "B2v")
            self.assertEqual(len(M.load_run_dirs([ok])), 5)
            self.assertFalse(I.interim([ok])["any_stop"])
            bad = self._p14_folder(os.path.join(d, "luna_val"))
            for f in (M.load_run_dirs, M.load_raw_lines, I.interim):
                with self.assertRaises(M.HoldOutLocked):
                    f([bad])
            with self.assertRaises(M.HoldOutLocked):
                M.main(["run", "--run-dir", bad])
            parent = os.path.join(d, "runs_copy")
            os.makedirs(os.path.join(parent, "airline"))
            os.rename(os.path.join(d, "luna_val"), os.path.join(parent, "airline", "luna_val"))
            with self.assertRaises(M.HoldOutLocked):                  # a file below a harmless parent
                M.load_run_dirs([parent])
            self.assertEqual(len(M.load_run_dirs([os.path.join(parent, "airline", "luna_val")], allow_val=True)), 5)

    def test_missing_arm_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            run = self._p14_folder(d)
            cs = M.load_run_dirs([run])
            self.assertIn("main_claim", M.report(cs))
            import shutil
            shutil.rmtree(os.path.join(run, M.DF))
            with self.assertRaises(M.MissingArm):
                M.report(M.load_run_dirs([run]))
            with self.assertRaises(SystemExit) as cm:
                M.main(["run", "--run-dir", run])
            self.assertIn("direct_facts_v3", str(cm.exception.code))

    def test_warnings_and_task_count(self):
        with tempfile.TemporaryDirectory() as d:
            r1 = self._p14_folder(d, "B1")
            r2 = self._p14_folder(d, "B2")
            rep = M.report(M.load_run_dirs([r1, r2]), raw=M.load_raw_lines([r1, r2]))
            self.assertTrue(any("more than one step" in w for w in rep["warnings"]))
            self.assertTrue(any("more than one run_id" in w for w in rep["warnings"]))
            self.assertEqual(rep["main_claim"]["n_tasks"], 1)
            self.assertTrue(any("rests on 1 tasks, not 99" in w for w in rep["warnings"]))
            c = rep["guard"][M.V3]["all"]["cost_range"]
            self.assertEqual((c["low"], c["high"], c["n_tasks"]), (0.01, 0.01, 1))

    def test_latest_backups_alias(self):
        t = tasks_of("retail", "val", 1)[0]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s0")
            os.makedirs(p)
            with open(os.path.join(p, "episodes_shard0of4.jsonl"), "w") as f:
                f.write(json.dumps(rec("retail", t, 0, "tgr", error="boom")) + "\n")
                f.write(json.dumps(rec("retail", t, 0, "tgr")) + "\n")
            with open(os.path.join(p, "episodes_shard0of4.jsonl.before_resume"), "w") as f:
                f.write(json.dumps(rec("retail", t, 1, "none")) + "\n")
            cs = M.load_run_dirs([d])
        self.assertEqual(len(cs), 1)
        self.assertEqual(cs[0]["arm"], "tgr_frozen")
        self.assertIsNone(cs[0]["error"])

    def test_dropped_groups_and_unit_attempt(self):
        """The runner's layout: <run>/<arm>/episodes_shard<i>of<n>.jsonl and <run>/dropped_groups_shard<i>of<n>.jsonl.
        A listed group leaves every arm (its lines stay for the spend, which the interim check still counts); a re-run
        unit (unit_attempt 2) wins over its first line, wherever it is read."""
        t1, t2 = tasks_of("retail", "val", 2)
        with tempfile.TemporaryDirectory() as d:
            for a in M.ARMS:
                os.makedirs(os.path.join(d, a))
                with open(os.path.join(d, a, "episodes_shard0of2.jsonl"), "w") as f:
                    for t in (t1, t2):
                        r = dict(rec("retail", t, 0, a, cost=0.01), unit_attempt=1, task_group="val")
                        if a == M.V3 and t == t2:                     # dropped group: a bad allow + a state error
                            r["error"] = "boom"
                            r["attempts"] = [att("cancel_pending_order", WRITE["kwargs"],
                                                 obs="Error: non-pending order cannot be cancelled",
                                                 guard={"v3": {"state_errors": [{"kind": "x"}]}})]
                        f.write(json.dumps(r) + "\n")
                    if a == M.V3:
                        f.write(json.dumps(dict(rec("retail", t1, 0, a, reward=0.0), unit_attempt=2)) + "\n")
                        f.write(json.dumps(dict(rec("retail", t2, 0, a, error="boom2"), unit_attempt=2)) + "\n")
            with open(os.path.join(d, M.V3, "episodes_shard1of2.jsonl"), "w") as f:     # an older line read later
                f.write(json.dumps(dict(rec("retail", t1, 0, M.V3, reward=1.0), unit_attempt=1)) + "\n")
            with open(os.path.join(d, "dropped_groups_shard0of2.jsonl"), "w") as f:
                f.write(json.dumps({"env": "retail", "task_index": t2, "trial": 0, "reason": "failed twice"}) + "\n")
            cs = M.load_run_dirs([d])
            self.assertEqual({(c["task"], c["arm"]) for c in cs}, {(t1, a) for a in M.ARMS})
            v3 = [c for c in cs if c["arm"] == M.V3][0]
            self.assertEqual((v3["rec"]["unit_attempt"], v3["success"]), (2, 0.0))
            self.assertEqual(len(M.load_run_dirs([d], drop_listed=False)), 10)
            self.assertEqual(M.report(cs)["complete_groups"]["complete_groups"], 1)
            rep = M.report(cs, raw=M.load_raw_lines([d]))
            self.assertEqual(rep["safety"]["bad"], 1)                       # every v3 line (audit A, 3)
            self.assertFalse(rep["safety"]["pass"])
            self.assertEqual(rep["safety_complete_groups_info"]["bad"], 0)
            it = I.interim([d])
            self.assertEqual(it["state"]["count"], 1)                       # every line, as the runner (audit A, 5)
            self.assertEqual(it["errors"]["error_lines"], 2)                # dropped lines still counted
            self.assertEqual(it["cost"]["arms"][M.V3]["lines"], 5)
            # a line whose task_group disagrees with splits.json is refused
            with open(os.path.join(d, "none", "episodes_shard1of2.jsonl"), "w") as f:
                f.write(json.dumps(dict(rec("retail", t1, 1, "none"), task_group="train")) + "\n")
            with self.assertRaises(ValueError):
                M.load_run_dirs([d])

    def test_complete_groups(self):
        t = tasks_of("retail", "val", 1)[0]
        recs = [rec("retail", t, 0, a) for a in M.ARMS] + [rec("retail", t, 1, a) for a in M.ARMS[:4]]
        recs.append(rec("retail", t, 2, M.V3, error="x"))
        recs += [rec("retail", t, 2, a) for a in M.ARMS[:4]]
        keep, info = M.complete_groups(convs_of(recs))
        self.assertEqual(len(keep), 5)
        self.assertEqual(info["complete_groups"], 1)
        self.assertEqual(len(info["dropped"]), 2)


class TestStatistics(unittest.TestCase):

    def test_percentile(self):
        self.assertAlmostEqual(M.percentile([0, 1, 2, 3], 0.5), 1.5)
        self.assertAlmostEqual(M.percentile([0, 10], 0.025), 0.25)

    def test_strat_boot_fixed_domains_and_seed(self):
        vals = {("airline", 1): 1.0, ("airline", 2): 1.0, ("retail", 3): 0.0, ("retail", 4): 0.0}
        r = M.strat_boot(vals, n=500)
        # stratified: every resample has 2 airline (1.0) and 2 retail (0.0) tasks, so the range is a point
        self.assertEqual((r["low"], r["high"], r["mean"]), (0.5, 0.5, 0.5))
        vals[("retail", 4)] = 1.0
        self.assertEqual(M.strat_boot(vals, n=500), M.strat_boot(vals, n=500))

    def test_main_claim_pass_rule(self):
        recs = []
        for dom, n in (("airline", 10), ("retail", 23)):
            for i, t in enumerate(tasks_of(dom, "val", n)):
                for k in range(3):
                    ok = 1.0 if (i + k) % 2 else 0.0
                    recs += [rec(dom, t, k, a, reward=ok) for a in M.ARMS]
        cs = convs_of(recs)
        full = M.main_claim(cs)
        mc = full["val"]
        self.assertEqual(mc["diff"], 0.0)
        self.assertTrue(mc["pass"])
        self.assertFalse(mc["seen_tasks"])
        self.assertEqual(mc["by_domain"], {"airline": 10, "retail": 23})
        self.assertEqual(full["headline"], "all")
        self.assertEqual(full["pass"], full["all"]["pass"])
        # v3 fails everything: clearly worse
        bad = [dict(r, reward=0.0) if r["arm"] == M.V3 else r for r in recs]
        self.assertFalse(M.main_claim(convs_of(bad))["pass"])

    def _two_sets(self, arm_ok):
        """val 33 + train 66 tasks, 3 tries; arm_ok(arm, split, i, k) -> success."""
        recs = []
        for split, counts in (("val", (("airline", 10), ("retail", 23))), ("train", (("airline", 20), ("retail", 46)))):
            for dom, n in counts:
                for i, t in enumerate(tasks_of(dom, split, n)):
                    for k in range(3):
                        recs += [rec(dom, t, k, a, reward=arm_ok(a, split, i, k)) for a in M.ARMS]
        return convs_of(recs)

    def test_main_on_all_99_and_leak_check(self):
        base = lambda i, k: 1.0 if (i + k) % 2 else 0.0                   # noqa: E731
        # v3 much better than frozen on train (seen), equal on val: possible leak
        cs = self._two_sets(lambda a, s, i, k: 1.0 if (a == M.V3 and s == "train") else base(i, k))
        mc = M.main_claim(cs)
        self.assertEqual(mc["all"]["n_tasks"], 99)
        self.assertEqual(mc["all"]["by_domain"], {"airline": 30, "retail": 69})
        self.assertTrue(mc["pass"])
        self.assertEqual(mc["leak_check"]["verdict"], M.POSSIBLE_LEAK)
        cs = self._two_sets(lambda a, s, i, k: base(i, k))
        self.assertEqual(M.main_claim(cs)["leak_check"]["verdict"], "no sign of a leak")

    def test_secondary_verdicts(self):
        base = lambda i, k: 1.0 if (i + k) % 2 else 0.0                   # noqa: E731
        # Direct + facts always succeeds: facts help (S1); v3 at the base rate: rules worse (S2)
        cs = self._two_sets(lambda a, s, i, k: 1.0 if a == M.DF else base(i, k))
        sec = M.secondary(cs)
        self.assertEqual(sec["S1"]["verdict"], "facts help")
        self.assertEqual(sec["S2"]["verdict"], "rules worse")
        self.assertEqual(sec["S1"]["all"]["n_tasks"], 99)
        self.assertEqual(sec["S1"]["val"]["verdict"], "facts help")
        # Direct + facts always fails: facts hurt, rules better
        sec = M.secondary(self._two_sets(lambda a, s, i, k: 0.0 if a == M.DF else base(i, k)))
        self.assertEqual((sec["S1"]["verdict"], sec["S2"]["verdict"]), ("facts hurt", "rules better"))
        sec = M.secondary(self._two_sets(lambda a, s, i, k: base(i, k)))
        self.assertEqual((sec["S1"]["verdict"], sec["S2"]["verdict"]), (M.NO_CLEAR, M.NO_CLEAR))
        self.assertIn("no multiple-testing correction", sec["multiple_testing"])
        self.assertEqual(M.verdict(-0.1, 0.0, "x", "y"), M.NO_CLEAR)        # an end exactly at 0 is not clear

    def test_pass_chance_plan_values(self):
        self.assertAlmostEqual(M.pass_chance(0.031, 0.0), 0.90, places=2)
        self.assertAlmostEqual(M.pass_chance(0.022, -0.03), 0.89, places=2)


class TestConversationMetrics(unittest.TestCase):

    def test_safety_and_writes(self):
        t = tasks_of("retail", "val", 1)[0]
        refused = att("cancel_pending_order", WRITE["kwargs"], obs="Error: non-pending order cannot be cancelled")
        r_bad = rec("retail", t, 0, M.V3, attempts=[refused])
        r_cap = rec("retail", t, 1, M.V3, attempts=[dict(refused, cap_override=True)], cap=1)
        r_ok = rec("retail", t, 2, M.V3, attempts=[att("cancel_pending_order", WRITE["kwargs"])])
        cs = convs_of([r_bad, r_cap, r_ok])
        s = M.safety(cs)
        self.assertEqual((s["bad"], s["refused_cap_overrides"], s["allowed_writes"]), (1, 1, 2))
        self.assertEqual(s["cases"][0]["mapped_facts"], ["order_status_checked_pending"])
        ea = M.expected_action_metrics(cs, M.V3)
        self.assertAlmostEqual(ea["expected_writes_done_share"], 1 / 3)
        self.assertEqual(M.rule_broken(cs, M.V3)["executed_breaking"], 1)
        self.assertIsNone(M.rule_broken(cs, "direct")["executed_breaking"])

    def test_refusal_and_handover(self):
        t = tasks_of("airline", "train", 1)[0]
        r1 = rec("airline", t, 0, "none", actions=[{"name": "get_user_details", "kwargs": {}}],
                 attempts=[att("transfer_to_human_agents")])
        cs = convs_of([r1])
        rm = M.refusal_metrics(cs, ("none",))
        self.assertEqual(rm["counts"]["train"], 1)
        self.assertEqual(rm["per_arm"]["train"]["none"]["any_write_sent"], 0.0)
        self.assertTrue(M.handed_over(r1))

    def test_advice_followed(self):
        msg = ("BLOCKED by policy guardrail. x\nNot met:\n- a: false\nWhat makes it true:\n"
               "1. Do this step first: look it up with get_order_details (order_id #W1). Then try again.\n"
               "When this is done, call cancel_pending_order again.")
        a1 = att("cancel_pending_order", blocked=True, feedback=msg)
        r = rec("retail", tasks_of("retail", "val", 1)[0], 0, M.V3,
                attempts=[a1, att("get_order_details", {"order_id": "#W1"})])
        br = M.block_responses(r)
        self.assertEqual(br[0]["advice_tools"], ["get_order_details"])
        self.assertTrue(br[0]["followed"])
        self.assertEqual(M.parse_advice("BLOCKED. plain")["rule_message"], False)

    def test_llm_share(self):
        self.assertTrue(M.check_uses_llm({"usage": {"n_llm_calls": 1}}))
        self.assertFalse(M.check_uses_llm({"usage": {"n_llm_calls": 0}, "v3": {"facts": {"f": {"source": "code"}}}}))
        self.assertTrue(M.check_uses_llm({"v3": {"facts": {"f": {"source": "question"}}}}))


class TestInterim(unittest.TestCase):

    def test_harm_halfway(self):
        recs = []
        tasks = [(d, t) for d, n in (("airline", 20), ("retail", 46)) for t in tasks_of(d, "train", n)]
        for k in range(3):
            for d, t in tasks:
                recs += [rec(d, t, k, a, reward=0.0 if a == M.V3 else 1.0) for a in M.ARMS]
        cs = convs_of(recs)
        h = I.harm_check(cs)
        self.assertTrue(h["reached"])            # 198 groups x 5 = 990 >= 742
        self.assertTrue(h["fire"])
        self.assertFalse(I.harm_check(cs[:700])["reached"])

    def test_cost_error_state(self):
        lines = {"f": [rec("retail", 1, i, "none", cost=0.03) for i in range(50)]}
        self.assertTrue(I.cost_check(lines)["fire"])
        lines = {"f": [rec("retail", 1, i, "none", cost=0.01) for i in range(49)] + [rec("retail", 1, 49, "none",
                                                                                       cost=0.3)]}
        self.assertTrue(I.cost_check(lines)["fire"])
        lines = {"f": [rec("retail", 1, i, "none", error="e" if i < 5 else None) for i in range(200)]}
        self.assertTrue(I.error_check(lines)["fire"])
        lines = {"f": [rec("retail", 1, i, "none", error="e" if i % 3 == 0 and i < 27 else None)
                       for i in range(300)]}
        self.assertFalse(I.error_check(lines)["fire"])            # 9 errors, no streak of 5
        t = tasks_of("retail", "val", 1)[0]
        g = {"v3": {"state_errors": [{"kind": "x"}], "fact_errors": []}}
        lines = {"f": [rec("retail", t, 0, M.V3, attempts=[att("respond", guard=g)] * 2),
                       rec("retail", t, 0, M.V3, attempts=[att("respond", guard=g)])]}      # a re-run unit counts too
        self.assertTrue(I.state_check(lines)["fire"])
        self.assertFalse(I.state_check({"f": lines["f"][:1]})["fire"])


class TestPartnerTrainReproduction(unittest.TestCase):

    def test_published_train_numbers(self):
        convs = M.load_partner_run(M.PARTNER_TRAIN)
        self.assertEqual({c["split"] for c in convs}, {"train"})
        rep = M.reproduce(convs, M.PUBLISHED_TRAIN)
        self.assertEqual(rep["mismatches"], [])
        self.assertEqual(rep["values_checked"], 54)
        self.assertEqual(M.refusal_metrics(convs, ("none",))["counts"]["train"], 12)


if __name__ == "__main__":
    unittest.main()
