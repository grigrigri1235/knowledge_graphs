"""Tests of the p14 after-run tools: scoring/v3_p14_report.py and scoring/v3_b1_summary.py. $0, no network, no LLM.

Input: the sandbox B1 run folder of p13 (output/eval_v3/dryrun/equality_check_after_fix/v3/B1/...; fake LLMs) and a
SYNTHETIC B2-shaped folder built here from its lines (99 tasks x 3 tries x 5 arms, made-up rewards and costs; 18
refusal tasks marked by an empty expected-action list; one re-run unit; one dropped group). Everything is written
under output/eval_v3/dryrun/p14report/ and marked TEST. docs/reports/ is never written: a test checks the refusal.

Run from predicate_correctness/:
  PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v3_p14_report -v
"""
from __future__ import annotations

import copy
import json
import os
import random
import shutil
import sys
import unittest

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

DRY = os.path.join(PC_DIR, "output", "eval_v3", "dryrun")
B1_RUN = os.path.join(DRY, "equality_check_after_fix", "v3", "B1", "B1_20261023T133328Z_1dd95a76")
OUT = os.path.join(DRY, "p14report")
SYNTH_ID = "B2_20261023T150000Z_5e5e5e5e"
SYNTH = os.path.join(OUT, "synth", "B2", SYNTH_ID)
ARMS = ("none", "direct", "direct_facts_v3", "tgr_frozen", "tgr_tracker_v3")
RATE = {"none": 0.0, "direct": 0.03, "direct_facts_v3": 0.05, "tgr_frozen": 0.06, "tgr_tracker_v3": 0.04}
COST = {"none": 0.0068, "direct": 0.0127, "direct_facts_v3": 0.0131, "tgr_frozen": 0.0120, "tgr_tracker_v3": 0.0104}


def _read(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def build_synth() -> str:
    """A synthetic B2 folder (TEST only) from the sandbox B1 lines."""
    if os.path.isdir(os.path.dirname(os.path.dirname(SYNTH))):
        shutil.rmtree(os.path.dirname(os.path.dirname(SYNTH)))
    tmpl = {}
    for a in ARMS:
        for r in _read(os.path.join(B1_RUN, a, "episodes_shard0of1.jsonl")):
            tmpl[(a, r["env"])] = r
    with open(os.path.join(PC_DIR, "output", "eval_v3", "online_tasks.json"), encoding="utf-8") as f:
        tasks = json.load(f)["tasks"]
    rnd = random.Random(20261023)
    refusal = {(t["domain"], t["task_index"]) for t in [x for x in tasks if x["group"] == "val"][:6]}
    refusal |= {(t["domain"], t["task_index"]) for t in [x for x in tasks if x["group"] == "train"][:12]}
    files = {}
    for a in ARMS:
        os.makedirs(os.path.join(SYNTH, a), exist_ok=True)
        for i in range(2):
            files[(a, i)] = open(os.path.join(SYNTH, a, f"episodes_shard{i}of2.jsonl"), "w", encoding="utf-8")
    dropped = []
    try:
        for t in tasks:
            base = rnd.uniform(0.15, 0.85)
            for k in range(3):
                for a in ARMS:
                    r = copy.deepcopy(tmpl[(a, t["domain"])])
                    ok = rnd.random() < min(1.0, base + RATE[a])
                    c = COST[a] * rnd.uniform(0.6, 1.5)
                    r.update({"task_index": t["task_index"], "trial": k, "task_group": t["group"], "step": "B2",
                              "run_id": SYNTH_ID, "unit_attempt": 1, "shard": f"{t['pos'] % 2}/2",
                              "reward": 1.0 if ok else 0.0, "error": None,
                              "cost": {"agent": c * 0.5, "user": c * 0.3, "guard": c * 0.2}})
                    if (t["domain"], t["task_index"]) in refusal:
                        r["reward_info"] = dict(r.get("reward_info") or {}, actions=[])
                    f = files[(a, t["pos"] % 2)]
                    if t["pos"] == 5 and k == 0 and a == "direct":        # a re-run unit: error, then a good line
                        e = dict(r, error="RuntimeError: synthetic failure", reward=0.0)
                        f.write(json.dumps(e) + "\n")
                        r["unit_attempt"] = 2
                    if t["pos"] == 7 and k == 2 and a == "tgr_tracker_v3":  # a dropped group: two errors
                        for att in (1, 2):
                            f.write(json.dumps(dict(r, error="RuntimeError: synthetic failure", reward=0.0,
                                                    unit_attempt=att)) + "\n")
                        dropped.append({"env": t["domain"], "task_index": t["task_index"], "trial": k,
                                        "reason": "synthetic", "time": "2026-10-23T15:00:00Z"})
                        continue
                    f.write(json.dumps(r) + "\n")
    finally:
        for f in files.values():
            f.close()
    with open(os.path.join(SYNTH, "dropped_groups_shard1of2.jsonl"), "w", encoding="utf-8") as f:
        for d in dropped:
            f.write(json.dumps(d) + "\n")
    with open(os.path.join(SYNTH, "run.json"), "w", encoding="utf-8") as f:
        json.dump({"ident": {"step": "B2", "run_id": SYNTH_ID, "n_tasks": 99, "tries": 3, "n_shards": 2,
                             "cap_usd": 95.0, "hard_limit_usd": 45.0, "runner_version": "synthetic",
                             "approval_quote": "TEST synthetic data, no money"},
                   "sandbox": True, "created": "2026-10-23T15:00:00Z"}, f, indent=1)
    return SYNTH


class TestP14Report(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_synth()

    def _report(self, run_dir, sub):
        from scoring import v3_p14_report as R
        out = os.path.join(OUT, sub)
        self.assertEqual(R.main(["--run-dir", run_dir, "--out-dir", out, "--overwrite"]), 0)
        with open(os.path.join(out, R.REPORT_NAME), encoding="utf-8") as f:
            text = f.read()
        for fig in (R.FIG_SUCCESS, R.FIG_PAIRED):
            p = os.path.join(out, "figures", fig)
            self.assertTrue(os.path.getsize(p) > 10000, p)
        return text

    def test_b1_dryrun_report(self):
        text = self._report(B1_RUN, "b1_dryrun")
        self.assertIn("TEST (dry-run data, fake LLMs)", text.splitlines()[0])
        self.assertIn("the main claim rests on 2 tasks, not 99", text)
        self.assertIn("no multiple-testing correction", text)
        self.assertIn("Only 2 tasks, not 99", text)

    def test_synth_report(self):
        from scoring import v3_online_metrics as M
        text = self._report(SYNTH, "synth_report")
        self.assertIn("TEST (dry-run data, fake LLMs)", text.splitlines()[0])
        self.assertNotIn("rests on", text)
        self.assertIn("Found 18 (val 6, train 12)", text)
        self.assertIn("group(s) listed as dropped by the runner", text)
        for word in ("Leak check", "S1", "S2", "Safety", "The five arms", "Stops", "Spend vs limits"):
            self.assertIn(word, text)
        # the same numbers through the metrics command's JSON
        mj = os.path.join(OUT, "synth_metrics.json")
        self.assertEqual(M.main(["run", "--run-dir", SYNTH, "--out", mj]), 0)
        from scoring import v3_p14_report as R
        out2 = os.path.join(OUT, "synth_report_from_json")
        self.assertEqual(R.main(["--metrics-json", mj, "--out-dir", out2, "--overwrite"]), 0)
        with open(mj, encoding="utf-8") as f:
            doc = json.load(f)
        mc = doc["main_claim"]["all"]
        self.assertEqual(doc["main_claim"]["n_tasks"], 99)
        with open(os.path.join(out2, R.REPORT_NAME), encoding="utf-8") as f:
            t2 = f.read()
        self.assertIn(f"{mc['diff']:+.3f}", t2)
        self.assertIn(f"[{mc['low']:+.3f}, {mc['high']:+.3f}]", t2)
        self.assertIn("PASS" if doc["main_claim"]["pass"] else "FAIL", t2)
        # the complete-group rule: 99 x 3 = 297 groups, one dropped
        self.assertEqual(doc["complete_groups"]["complete_groups"], 296)

    def test_refuses_real_reports_dir_for_test_data(self):
        from scoring import v3_p14_report as R
        real = os.path.join(R.REAL_OUT_DIR, R.REPORT_NAME)
        before = os.path.getmtime(real) if os.path.exists(real) else None
        figs = [os.path.join(R.REAL_OUT_DIR, "figures", f) for f in (R.FIG_SUCCESS, R.FIG_PAIRED)]
        figs_before = [os.path.getmtime(p) if os.path.exists(p) else None for p in figs]
        with self.assertRaises(SystemExit):
            R.main(["--run-dir", B1_RUN, "--overwrite"])
        with self.assertRaises(SystemExit):
            R.main(["--run-dir", B1_RUN, "--out-dir", os.path.join(DRY, "elsewhere"), "--overwrite"])
        after = os.path.getmtime(real) if os.path.exists(real) else None
        self.assertEqual(before, after)
        self.assertEqual(figs_before, [os.path.getmtime(p) if os.path.exists(p) else None for p in figs])
        self.assertFalse(os.path.exists(os.path.join(DRY, "elsewhere")))

    def test_refuses_saved_val_run(self):
        from scoring import v3_p14_report as R
        from scoring import v3_online_metrics as M
        with self.assertRaises(M.HoldOutLocked):        # the path alone is refused; nothing is opened
            R.main(["--run-dir", os.path.join(PC_DIR, "output", "nowhere", "luna_val"), "--out-dir",
                    os.path.join(OUT, "x")])


class TestB1Summary(unittest.TestCase):
    def test_pass_on_dryrun(self):
        from scoring import v3_b1_summary as S
        out = os.path.join(OUT, "b1_summary_dryrun.md")
        self.assertEqual(S.main(["--run-dir", B1_RUN, "--out", out]), 0)
        with open(out, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("TEST (dry-run data, fake LLMs)", text.splitlines()[0])
        self.assertIn("Verdict: **PASS**", text)
        with open(out[:-3] + ".json", encoding="utf-8") as f:
            s = json.load(f)
        self.assertEqual(s["check"]["conversations"], 10)
        self.assertEqual(s["check"]["direct_facts_facts_failures"], 0)

    def test_fail_with_an_error_line(self):
        from scoring import v3_b1_summary as S
        bad = os.path.join(OUT, "b1_fail", "B1", os.path.basename(B1_RUN))
        if os.path.isdir(os.path.dirname(os.path.dirname(bad))):
            shutil.rmtree(os.path.dirname(os.path.dirname(bad)))
        shutil.copytree(B1_RUN, bad)
        p = os.path.join(bad, "direct", "episodes_shard0of1.jsonl")
        r = _read(p)[0]
        r.update({"error": "RuntimeError: synthetic API failure", "reward": 0.0, "unit_attempt": 1})
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(r) + "\n")
        out = os.path.join(OUT, "b1_summary_fail.md")
        self.assertEqual(S.main(["--run-dir", bad, "--out", out]), 0)
        with open(out, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("Verdict: **FAIL**", text)
        self.assertIn("synthetic API failure", text)

    def test_refuses_out_outside_test_folder(self):
        from scoring import v3_b1_summary as S
        target = os.path.join(PC_DIR, "output", "eval_v3", "B1_test_should_not_exist.md")
        with self.assertRaises(SystemExit):
            S.main(["--run-dir", B1_RUN, "--out", target])
        self.assertFalse(os.path.exists(target))


if __name__ == "__main__":
    unittest.main()
