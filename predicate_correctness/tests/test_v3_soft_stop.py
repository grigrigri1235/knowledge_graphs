"""Tracker v3, part 13 step 2: the spend limits and stop rules (guard/soft_stop_v3.py).

  - the v2 SpendScanner, line_cost, is_episodes_file are imported unchanged (same objects; the v2 file matches the
    eval v2 manifest);
  - backups *.jsonl.before_resume: a copied backup counts once (in its live file); a moved backup counts in full
    (the larger of backup and live) and refuses the step start (audit B #1); the dry-run folder is not counted;
    fake-LLM lines cost 0 (in this test; the runner's fake-LLM dry-run lines carry made-up costs, only the folder
    keeps them out);
  - v3's tiny-question cost is counted once (in the episode line's guard cost, not again in a questions file);
    p12's questions file is counted, with failed attempts (spent_usd) and several writer runs;
  - cap and reserve edges (equal is allowed, a cent more is not), B2v needs the $110 cap;
  - each stop rule fires at its threshold and not below; the STOP file; stops are sticky; the per-unit check of
    the hard limit and the cap (audit B #8);
  - the module writes nothing.
All on temporary folders with made-up lines; no LLM, no network.

Run from predicate_correctness/:  python3 -B -m unittest tests.test_v3_soft_stop -v
Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True

from guard import soft_stop as V2  # noqa: E402
from guard import soft_stop_v3 as S  # noqa: E402

PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ep(cost=0.01, guard="tgr_tracker_v3", error=None, split=None, **kw):
    """One episodes line: cost split over agent / user / guard like the runner's lines."""
    if error is not None:
        rec = {"task_index": 0, "reward": 0.0, "error": error,
               "usage_roles": {"agent": {"cost": cost}, "user": {"cost": 0.0}}}
        if guard:
            rec["guard"] = guard
        return rec
    a, u, g = split if split is not None else (cost, 0.0, 0.0)
    rec = {"task_index": 0, "trial": 0, "guard": guard, "error": None, "cost": {"agent": a, "user": u, "guard": g}}
    rec.update(kw)
    return rec


def write_jsonl(path, recs, mode="w"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode, encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")


def tree(root):
    out = {}
    for dp, dn, fn in os.walk(root):
        for n in fn:
            p = os.path.join(dp, n)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root)] = hashlib.sha256(f.read()).hexdigest()
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="v3_soft_stop_")
        self.root = os.path.join(self._td.name, "eval_v3")
        os.makedirs(self.root)
        self.qfile = os.path.join(self.root, "questions_answers.jsonl")

    def tearDown(self):
        self._td.cleanup()

    def total(self):
        return S.v3_spend(self.root, (self.qfile,))


class TestV2Unchanged(unittest.TestCase):
    def test_same_objects(self):
        self.assertIs(S.SpendScanner, V2.SpendScanner)
        self.assertIs(S.line_cost, V2.line_cost)
        self.assertIs(S.is_episodes_file, V2.is_episodes_file)
        self.assertIs(S.JsonlTail, V2.JsonlTail)

    def test_v2_file_matches_manifest(self):
        man = os.path.join(PC_DIR, "output", "eval_v3", "manifest_eval_v2_data.sha256")
        with open(man, encoding="utf-8") as f:
            want = [ln.split()[0] for ln in f if ln.rstrip().endswith("  guard/soft_stop.py")]
        self.assertEqual(len(want), 1)
        self.assertEqual(S.file_sha256(os.path.join(PC_DIR, "guard", "soft_stop.py")), want[0])

    def test_questions_path_is_p12_file(self):
        from state_tracker.v3 import questions as Q
        self.assertEqual(S.QUESTIONS_FILES, (Q.ANSWERS_PATH,))

    def test_constants(self):
        # the plan's cap is $95 (it calls it the sum of the limits; 26 + 2 + 45 + 20 is $93, so the cap has $2 of
        # slack); with B2v approved the cap rises by B2v's $15 limit
        self.assertEqual(S.V3_CAP_USD, 95.0)
        self.assertLessEqual(sum(S.STEP_LIMITS_USD[k] for k in ("p12", "B1", "B2", "B3")), S.V3_CAP_USD)
        self.assertEqual(S.V3_CAP_WITH_B2V_USD, S.V3_CAP_USD + S.STEP_LIMITS_USD["B2v"])
        self.assertEqual((S.cap_usd(False), S.cap_usd(True)), (95.0, 110.0))
        self.assertEqual(S.ARM_MEAN_STOP_USD, {"none": 0.023, "direct": 0.044, "direct_facts_v3": 0.049,
                                               "tgr_frozen": 0.041, "tgr_tracker_v3": 0.061})

    def test_no_network_or_write_code(self):
        with open(S.__file__, encoding="utf-8") as f:
            src = f.read()
        for bad in ("import socket", "urllib", "http.client", "requests", "openai", '"w"', "'w'", '"a"',
                    "os.remove", "os.rename", "shutil"):
            self.assertNotIn(bad, src, bad)


class TestSpendCounting(Base):
    def test_copied_backup_counts_once(self):
        d = os.path.join(self.root, "B2", "run1", "direct")
        live = os.path.join(d, "episodes_shard0of4.jsonl")
        write_jsonl(live, [ep(5.0), ep(7.0)])
        with open(live, "rb") as f, open(live + ".before_resume", "wb") as g:     # cp
            g.write(f.read())
        write_jsonl(live, [ep(1.0)], mode="a")                                  # the resumed run adds a line
        self.assertEqual(S.backup_problems(os.path.join(self.root, "B2")), [])
        r = self.total()
        self.assertAlmostEqual(r["total_usd"], 13.0)
        self.assertAlmostEqual(r["backups_usd"], 12.0)
        self.assertAlmostEqual(r["backups_extra_usd"], 0.0)
        self.assertAlmostEqual(S.step_spend(os.path.join(self.root, "B2"))["total_usd"], 13.0)
        ss = S.SoftStopV3("B2", root=self.root, questions=(self.qfile,))
        self.assertTrue(ss.can_start_step()[0])
        self.assertAlmostEqual(ss.report()["step_usd"], 13.0)
        self.assertEqual(sum(a["conversations"] for a in ss.report()["per_arm"].values()), 3)

    def test_moved_backup_refuses_the_start_and_still_counts(self):
        d = os.path.join(self.root, "B2", "run1", "direct")
        live = os.path.join(d, "episodes_shard0of4.jsonl")
        write_jsonl(live + ".before_resume", [ep(5.0), ep(7.0)])                # mv: no live file
        probs = S.backup_problems(os.path.join(self.root, "B2"))
        self.assertEqual(len(probs), 1)
        self.assertIn("no live file", probs[0])
        self.assertAlmostEqual(self.total()["total_usd"], 12.0)                 # the backup's spend is not hidden
        self.assertAlmostEqual(S.step_spend(os.path.join(self.root, "B2"))["total_usd"], 12.0)
        ss = S.SoftStopV3("B2", root=self.root, questions=(self.qfile,))
        ok, reason = ss.can_start_step()
        self.assertFalse(ok)
        self.assertIn("copy, never move", reason)
        self.assertFalse(ss.can_start_group(0, 0)[0])                           # sticky
        # a new live file after the mv (the resumed run started again): shorter, other bytes -> still refused;
        # the larger of backup and live counts
        write_jsonl(live, [ep(1.0)])
        probs = S.backup_problems(os.path.join(self.root, "B2"))
        self.assertEqual(len(probs), 1)
        self.assertIn("shorter", probs[0])
        self.assertAlmostEqual(self.total()["total_usd"], 12.0)
        self.assertFalse(S.SoftStopV3("B2", root=self.root, questions=(self.qfile,)).can_start_step()[0])
        # as long, but other first bytes
        write_jsonl(live, [ep(9.0), ep(9.0), ep(9.0)])
        self.assertIn("does not start", S.backup_problems(os.path.join(self.root, "B2"))[0])
        self.assertAlmostEqual(self.total()["total_usd"], 27.0)                 # live 27 > backup 12
        # a backup in another step's folder does not refuse this step
        self.assertEqual(S.backup_problems(os.path.join(self.root, "B1")), [])
        # a running step: the group check sees a moved backup too (sticky stop)
        b1 = os.path.join(self.root, "B1", "r", "none", "episodes_shard0of1.jsonl")
        write_jsonl(b1, [ep(0.01)])
        s3 = S.SoftStopV3("B1", root=self.root, questions=(self.qfile,), cap_usd=200.0)
        self.assertTrue(s3.can_start_step()[0])
        os.rename(b1, b1 + ".before_resume")
        ok, reason = s3.can_start_group(0, 0)
        self.assertFalse(ok)
        self.assertIn("backup_moved", reason)

    def test_dryrun_backups_not_in_the_total(self):
        write_jsonl(os.path.join(self.root, "dryrun", "x", "episodes_s0.jsonl.before_resume"), [ep(50.0)])
        self.assertAlmostEqual(self.total()["total_usd"], 0.0)

    def test_tiny_questions_counted_once(self):
        d = os.path.join(self.root, "B1", "run1")
        # the tiny questions' $0.003 is inside the guard cost of the line
        write_jsonl(os.path.join(d, "episodes_s0.jsonl"), [ep(split=(0.006, 0.001, 0.003))])
        # the run's own fresh answer store holds the same $0.003 again: not counted
        write_jsonl(os.path.join(d, "questions_answers.jsonl"),
                    [{"key": "k1", "cost_usd": 0.002, "spent_usd": 0.002},
                     {"key": "k2", "cost_usd": 0.001, "spent_usd": 0.003}])
        write_jsonl(os.path.join(d, "questions_cache", "answers.jsonl"), [{"key": "k3", "cost_usd": 0.5}])
        r = self.total()
        self.assertAlmostEqual(r["total_usd"], 0.010)
        self.assertAlmostEqual(r["questions_usd"], 0.0)
        # p12's file (the project's questions_answers.jsonl) is counted
        write_jsonl(self.qfile, [{"key": "a", "cost_usd": 0.25, "spent_usd": 0.25}])
        r = self.total()
        self.assertAlmostEqual(r["questions_usd"], 0.25)
        self.assertAlmostEqual(r["total_usd"], 0.26)

    def test_p12_failed_attempts_and_writer_runs(self):
        recs = [  # run 1: a failed attempt of $0.01 between line 1 and line 2 (spent_usd jumps by 0.03)
            {"key": "1", "cost_usd": 0.01, "spent_usd": 0.01},
            {"key": "2", "cost_usd": 0.02, "spent_usd": 0.04},
            {"key": "3", "cost_usd": 0.01, "spent_usd": 0.06},   # 8 workers: written out of order
            {"key": "4", "cost_usd": 0.01, "spent_usd": 0.05},
            # run 2 (a new process, spent starts again)
            {"key": "5", "cost_usd": 0.01, "spent_usd": 0.01},
            {"key": "6", "cost_usd": 0.01, "spent_usd": 0.02},
            {"key": "7", "answer": "no"},                          # a fake or old record: no cost
        ]
        write_jsonl(self.qfile, recs)
        q = S.questions_spend((self.qfile,))
        v = q["by_file"][os.path.abspath(self.qfile)]
        self.assertEqual(v["writer_runs"], 2)
        self.assertAlmostEqual(v["cost_usd_sum"], 0.07)
        self.assertAlmostEqual(v["spent_usd_runs_sum"], 0.08)
        self.assertAlmostEqual(q["usd"], 0.08)
        # without spent_usd: the cost_usd sum
        write_jsonl(self.qfile, [{"key": "1", "cost_usd": 0.5}, {"key": "2", "cost_usd": 0.25}])
        self.assertAlmostEqual(S.questions_spend((self.qfile,))["usd"], 0.75)
        os.remove(self.qfile)
        self.assertEqual(S.questions_spend((self.qfile,))["usd"], 0.0)

    def test_fake_dryrun_lines_cost_zero(self):
        # fake-LLM lines (no price): cost 0 wherever they are
        write_jsonl(os.path.join(self.root, "B1", "r", "episodes_s0.jsonl"), [ep(split=(0.0, 0.0, 0.0))] * 3)
        # the dry-run folder is not counted, even if a fake LLM wrote a made-up cost there
        write_jsonl(os.path.join(self.root, "dryrun", "x", "episodes_s0.jsonl"), [ep(120.0)])
        r = self.total()
        self.assertEqual(r["total_usd"], 0.0)
        self.assertEqual(r["episode_lines"], 3)
        self.assertAlmostEqual(r["dryrun_usd_not_counted"], 120.0)
        self.assertFalse(any(k.startswith("dryrun") for k in r["by_file"]))

    def test_error_line_counts_usage_roles(self):
        write_jsonl(os.path.join(self.root, "B2", "r", "episodes_s0.jsonl"), [ep(0.04, error="Boom")])
        self.assertAlmostEqual(self.total()["total_usd"], 0.04)

    def test_incremental_growth_and_replace(self):
        p = os.path.join(self.root, "B2", "r", "episodes_s0.jsonl")
        write_jsonl(p, [ep(1.0)])
        sc = S.V3SpendScanner(self.root, (self.qfile,))
        self.assertAlmostEqual(sc.total(), 1.0)
        write_jsonl(p, [ep(2.0)], mode="a")
        self.assertAlmostEqual(sc.total(), 3.0)
        self.assertAlmostEqual(sc.total(), 3.0)
        os.remove(p)
        write_jsonl(p, [ep(0.5)])
        self.assertAlmostEqual(sc.total(), 0.5)

    def test_reads_only(self):
        write_jsonl(os.path.join(self.root, "B1", "r", "episodes_s0.jsonl"), [ep(0.01)] * 3)
        write_jsonl(self.qfile, [{"key": "a", "cost_usd": 0.1, "spent_usd": 0.1}])
        before = tree(self._td.name)
        ss = S.SoftStopV3("B1", root=self.root, questions=(self.qfile,))
        ss.can_start_step()
        ss.can_start_group(0, 0, run_dir=os.path.join(self.root, "B1", "r"))
        ss.report()
        ss.run_json()
        self.total()
        self.assertEqual(tree(self._td.name), before)


class TestCapAndReserve(unittest.TestCase):
    def test_step_start_edges(self):
        self.assertTrue(S.step_start_ok(50.0, 0.0, 45.0, 95.0)[0])           # 50 + 45 = 95: equal is allowed
        self.assertFalse(S.step_start_ok(50.01, 0.0, 45.0, 95.0)[0])         # a cent more could pass
        self.assertTrue(S.step_start_ok(93.0, 0.0, 2.0, 95.0, "B1")[0])
        self.assertFalse(S.step_start_ok(93.5, 0.0, 2.0, 95.0, "B1")[0])
        # a resumed step: its own spend is in the total, only its limit left is added
        self.assertTrue(S.step_start_ok(80.0, 30.0, 45.0, 95.0, "B2")[0])    # 80 + 15 = 95
        self.assertFalse(S.step_start_ok(80.5, 30.0, 45.0, 95.0, "B2")[0])
        self.assertFalse(S.step_start_ok(46.0, 45.0, 45.0, 95.0, "B2")[0])   # limit used up
        # B2v: only under the raised cap
        self.assertFalse(S.step_start_ok(0.0, 0.0, 15.0, 95.0, "B2v")[0])
        self.assertTrue(S.step_start_ok(95.0, 0.0, 15.0, 110.0, "B2v")[0])
        self.assertFalse(S.step_start_ok(95.5, 0.0, 15.0, 110.0, "B2v")[0])

    def test_reserve_edges(self):
        # 10 + (3 running + 2 left + 5 new) x 0.5 = 15: equal is allowed
        self.assertTrue(S.group_start_ok(10.0, 15.0, 3, 2, 0.5)[0])
        self.assertFalse(S.group_start_ok(10.01, 15.0, 3, 2, 0.5)[0])
        self.assertFalse(S.group_start_ok(10.0, 15.0, 3, 3, 0.5)[0])         # one more unit left
        self.assertTrue(S.group_start_ok(10.0, 15.0, 3, 3, 0.5, new_units=4)[0])
        # the cap too, when given
        self.assertTrue(S.group_start_ok(10.0, 15.0, 3, 2, 0.5, total_spent=90.0, cap=95.0)[0])
        self.assertFalse(S.group_start_ok(10.0, 15.0, 3, 2, 0.5, total_spent=90.5, cap=95.0)[0])

    def test_p90(self):
        self.assertEqual(S.p90_cost([0.01] * 19), S.P90_PRIOR_USD)
        xs = [i / 100 for i in range(1, 21)]                                   # 0.01 .. 0.20
        self.assertAlmostEqual(S.p90_cost(xs), 0.18)                          # nearest rank: 18th of 20
        self.assertAlmostEqual(S.p90_cost([0.02] * 20), 0.02)
        self.assertEqual(S.p90_cost([], prior=0.1, min_done=0), 0.1)


class TestStopRules(unittest.TestCase):
    def rules(self, lines_by_file):
        return sorted({s["rule"] for s in S.stop_reasons(lines_by_file)})

    def test_arm_mean_each_arm(self):
        for arm, thr in S.ARM_MEAN_STOP_USD.items():
            self.assertEqual(self.rules({"f": [ep(thr, guard=arm)] * 50}), [], arm)               # equal: no
            self.assertEqual(self.rules({"f": [ep(thr + 0.001, guard=arm)] * 49}), [], arm)       # 49: no
            self.assertEqual(self.rules({"f": [ep(thr + 0.001, guard=arm)] * 50}), ["arm_mean_cost"], arm)
        # the mean of one arm only: other arms do not dilute it
        mix = [ep(0.03, guard="none")] * 50 + [ep(0.001, guard="tgr_tracker_v3")] * 500
        self.assertEqual(self.rules({"f": mix}), ["arm_mean_cost"])
        # an arm with another name uses the highest threshold
        self.assertEqual(self.rules({"f": [ep(0.061, guard="other")] * 50}), [])
        self.assertEqual(self.rules({"f": [ep(0.062, guard="other")] * 50}), ["arm_mean_cost"])

    def test_arm_from_folder(self):
        rec = {"error": "x", "usage_roles": {}}
        self.assertEqual(S.default_arm_of(rec, "/a/B2/run/direct/episodes_s0.jsonl"), "direct")
        self.assertEqual(S.default_arm_of({"arm": "none"}, "/a/b/episodes.jsonl"), "none")
        self.assertEqual(S.default_arm_of({"guard": "tgr_frozen", "arm": "none"}, "/a/b/e.jsonl"), "tgr_frozen")

    def test_one_conversation(self):
        self.assertEqual(self.rules({"f": [ep(0.25)]}), [])
        self.assertEqual(self.rules({"f": [ep(split=(0.2, 0.03, 0.0201))]}), ["one_conversation"])

    def test_error_share(self):
        def lines(n_err, n):
            # errors spread out (never 5 in a row)
            out = []
            for i in range(n):
                out.append(ep(0.001, error="E") if i % 4 == 0 and i // 4 < n_err else ep(0.001))
            return out
        self.assertEqual(self.rules({"f": lines(9, 100)}), [])                 # 9 errors: no
        self.assertEqual(self.rules({"f": lines(10, 200)}), [])                # 10 of 200 = 5.0 %: no
        self.assertEqual(self.rules({"f": lines(10, 199)}), ["error_share"])   # 10 of 199 > 5 %: yes
        self.assertEqual(self.rules({"f": lines(10, 100)}), ["error_share"])

    def test_errors_in_a_row(self):
        ok = [ep(0.001)] * 200
        self.assertEqual(self.rules({"f": ok + [ep(0.001, error="E")] * 4 + ok}), [])
        self.assertEqual(self.rules({"f": ok + [ep(0.001, error="E")] * 5 + ok}), ["errors_in_a_row"])
        # a run is counted inside one file, not across files
        self.assertEqual(self.rules({"a": ok + [ep(0.001, error="E")] * 3,
                                     "b": [ep(0.001, error="E")] * 2 + ok}), [])

    def test_stop_file(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(S.stop_file_present(d))
            self.assertFalse(S.stop_file_present(None))
            open(os.path.join(d, "STOP"), "x").close()
            self.assertTrue(S.stop_file_present(d))


class TestRunnerObject(Base):
    def setUp(self):
        super().setUp()
        self.run = os.path.join(self.root, "B1", "run1")
        self.ep_path = os.path.join(self.run, "episodes_s0.jsonl")

    def ss(self, step="B1", **kw):
        return S.SoftStopV3(step, root=self.root, questions=(self.qfile,), **kw)

    def test_step_start_uses_total(self):
        write_jsonl(self.qfile, [{"key": "a", "cost_usd": 93.0, "spent_usd": 93.0}])
        self.assertTrue(self.ss("B1").can_start_step()[0])                     # 93 + 2 = 95
        write_jsonl(os.path.join(self.root, "dryrun", "e", "episodes.jsonl"), [ep(50.0)])
        self.assertTrue(self.ss("B1").can_start_step()[0])                     # the dry run does not count
        write_jsonl(os.path.join(self.root, "B2", "r", "episodes.jsonl"), [ep(0.01)])
        s = self.ss("B1")
        self.assertFalse(s.can_start_step()[0])                                # 93.01 + 2 > 95
        self.assertFalse(s.can_start_group(0, 0)[0])                           # sticky
        self.assertTrue(self.ss("B1", cap_usd=110.0).can_start_step()[0])
        with self.assertRaises(ValueError):
            S.SoftStopV3("B9", root=self.root)

    def test_group_needs_step_start(self):
        s = self.ss()
        self.assertFalse(s.can_start_group(0, 0)[0])
        self.assertFalse(s.can_start_step()[0] and s.can_start_group(0, 0)[0])  # sticky after the first no

    def test_reserve_with_prior_then_p90(self):
        s = self.ss()                                                          # B1: limit $2
        self.assertTrue(s.can_start_step()[0])
        # prior p90 0.061: (running 20 + left 7 + new 5) x 0.061 = 1.952 <= 2
        self.assertTrue(s.can_start_group(20, 7)[0])
        s2 = self.ss()
        s2.can_start_step()
        self.assertFalse(s2.can_start_group(20, 8)[0])                         # 33 x 0.061 = 2.013 > 2
        self.assertFalse(s2.can_start_group(0, 0)[0])                          # sticky
        # after 20 lines the p90 of the lines is used: 20 x 0.01 = 0.2 spent; 0.2 + 180 x 0.01 = 2.0
        write_jsonl(self.ep_path, [ep(0.01)] * 20)
        s3 = self.ss()
        s3.can_start_step()
        self.assertTrue(s3.can_start_group(170, 5)[0])
        self.assertFalse(s3.can_start_group(171, 5)[0])

    def test_stop_rules_through_object(self):
        s = self.ss("B2")
        self.assertTrue(s.can_start_step()[0])
        write_jsonl(self.ep_path.replace("B1", "B2"), [ep(0.001)] * 20 + [ep(0.001, error="E")] * 5)
        ok, reason = s.can_start_group(0, 0)
        self.assertFalse(ok)
        self.assertIn("errors_in_a_row", reason)
        self.assertEqual(s.stopped["rule"], "errors_in_a_row")

    def test_unit_check_hard_limit_and_cap(self):
        s = self.ss()                                                          # B1: limit $2
        s.can_start_step()
        write_jsonl(self.ep_path, [ep(1.99)])
        self.assertTrue(s.can_start_unit()[0])
        self.assertIsNone(s.stopped)
        write_jsonl(self.ep_path, [ep(0.01)], mode="a")                        # 2.00: the limit is reached
        ok, reason = s.can_start_unit()
        self.assertFalse(ok)
        self.assertIn("hard limit", reason)
        self.assertEqual(s.stopped["rule"], "unit_limit")                      # no new group either
        self.assertFalse(s.can_start_group(0, 0)[0])
        # the cap: p12 spend near the cap
        write_jsonl(self.qfile, [{"key": "a", "cost_usd": 95.0, "spent_usd": 95.0}])
        t = S.SoftStopV3("B2", root=self.root, questions=(self.qfile,))
        ok, reason = t.can_start_unit()
        self.assertFalse(ok)
        self.assertIn("cap", reason)

    def test_stop_file_and_limit(self):
        s = self.ss()
        s.can_start_step()
        write_jsonl(self.ep_path, [ep(0.01)] * 2)
        self.assertEqual(s.check_stops(self.run), [])
        self.assertTrue(s.can_start_group(0, 0, run_dir=self.run)[0])
        open(os.path.join(self.run, "STOP"), "x").close()
        self.assertEqual([x["rule"] for x in s.check_stops(self.run)], ["stop_file"])
        self.assertFalse(s.can_start_group(0, 0, run_dir=self.run)[0])
        os.remove(os.path.join(self.run, "STOP"))
        self.assertFalse(s.can_start_group(0, 0, run_dir=self.run)[0])        # sticky
        # the step's hard limit: $2 reached
        t = self.ss()
        t.can_start_step()
        write_jsonl(self.ep_path, [ep(0.2)] * 9 + [ep(0.18)], mode="a")       # 0.02 + 1.98 = 2.0: reached
        self.assertIn("step_limit", [x["rule"] for x in t.check_stops(self.run)])

    def test_run_json(self):
        s = self.ss("B2v", cap_usd=S.cap_usd(True))
        self.assertTrue(s.can_start_step()[0])
        j = s.run_json()
        json.dumps(j)
        self.assertEqual((j["cap_usd"], j["hard_limit_usd"], j["step"]), (110.0, 15.0, "B2v"))
        self.assertEqual(j["module_sha256"], S.file_sha256(S.__file__))
        self.assertEqual(j["v2_soft_stop_sha256"], S.file_sha256(V2.__file__))
        self.assertTrue(j["at_start"]["ok"])

    def test_report_per_arm(self):
        write_jsonl(self.ep_path, [ep(0.01, guard="none"), ep(0.03, guard="none"), ep(0.02, guard="direct",
                                                                                       error="E")])
        r = self.ss().report()
        self.assertAlmostEqual(r["per_arm"]["none"]["mean_usd"], 0.02)
        self.assertEqual(r["per_arm"]["direct"]["errors"], 1)
        self.assertAlmostEqual(r["step_usd"], 0.06)


if __name__ == "__main__":
    unittest.main()
