"""Tests of B3 (p14, optional; docs/planning/tracker_v3/approval_request_B3_draft.md): the runner's step B3
(guard/run_online_v3.py), its task list (output/eval_v3/b3_tasks.json) and the B3 side report of the metrics and the
interim check (scoring/v3_online_metrics.py report_b3, scoring/v3_online_interim.py). Built records only for the
metrics; τ-bench's train file (read-only) for the task list. No LLM, no network, no gold code.

Run from predicate_correctness/:
    ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v3_b3 -v       (the τ-bench parts need the venv)
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from guard import run_online_v3 as R, soft_stop_v3 as SS        # noqa: E402
from scoring import v3_online_interim as I                       # noqa: E402
from scoring import v3_online_metrics as M                       # noqa: E402

try:
    import tau_bench  # noqa: F401
    HAVE_TAU = True
except ImportError:
    HAVE_TAU = False

B3_TASKS = [12, 20, 29, 35, 43, 46, 53, 68, 69, 70, 76, 80, 99, 127, 130, 139, 141, 146, 148, 166, 176, 190, 192, 197,
            203, 222, 231, 233, 243, 245, 248, 252, 255, 265, 275, 277, 290, 298, 305, 314, 317, 319, 329, 331, 334,
            345, 351, 360, 368, 369, 380, 393, 415, 416, 427, 431, 433, 434, 445, 451, 462, 464, 474, 497]


def b3_doc():
    with open(R.B3_TASKS_FILE, encoding="utf-8") as f:
        return json.load(f)


class TestB3Steps(unittest.TestCase):

    def test_b1_b2_unchanged(self):
        self.assertEqual(R.STEPS["B1"], {"tries": 1, "first_try": 0, "groups": ("val", "train"), "n_tasks": 2,
                                         "shards": (1,), "max_calls": 2000})
        self.assertEqual(R.STEPS["B2"], {"tries": 3, "first_try": 0, "groups": ("val", "train"), "n_tasks": 99,
                                         "shards": (1, 2, 3, 4), "max_calls": 40000})
        self.assertEqual(R.STEPS["B2v"], {"tries": 3, "first_try": 3, "groups": ("val",), "n_tasks": 33,
                                          "shards": (1, 2, 3, 4), "max_calls": 15000})
        for s in ("B1", "B2", "B2v"):
            self.assertEqual(R.step_task_split(s), "test")
        self.assertEqual(R.TASK_SPLIT, "test")
        self.assertEqual(R.TASKS_FILE_SHA256, "5f7b9b71c727531c29cbe1ab8e7189b4bcf67195bb5b78f02437f98d08baf96e")

    def test_b3_step(self):
        self.assertEqual(R.STEPS["B3"], {"tries": 1, "first_try": 0, "groups": ("stage_a",), "n_tasks": 64,
                                         "shards": (1, 2, 3, 4), "max_calls": 10000})
        self.assertEqual(R.step_task_split("B3"), "train")
        self.assertEqual(SS.STEP_LIMITS_USD["B3"], 20.0)
        self.assertEqual(SS.cap_usd(False), 95.0)
        rid = R.new_run_id("B3")
        self.assertRegex(rid, r"^B3_\d{8}T\d{6}Z_[0-9a-f]{8}$")
        R.check_run_id("B3", rid)
        for step, bad in (("B3", R.new_run_id("B2")), ("B2", rid), ("B3", "B3_x")):
            with self.assertRaises(R.RunRefused):
                R.check_run_id(step, bad)
        p = R.resolve_paths(R.V3_ROOT, "B3", rid, (2, 4))
        self.assertEqual(p["run_dir"], os.path.join(R.V3_ROOT, "B3", rid))
        self.assertEqual(p["log"], os.path.join(R.LOGS_DIR, f"v3_B3_{rid}_s2.log"))

    def test_plan_identity_default_is_the_old_one(self):
        tasks = [{"domain": "retail", "task_index": 4, "group": "val"}]
        a = R.plan_identity("B2", "B2_x", tasks, 3, 0, 4, "words", 95.0, 45.0, "sha")
        self.assertEqual((a["task_split"], a["tasks_file"]), ("test", R.TASKS_REL))
        b = R.plan_identity("B3", "B3_x", tasks, 1, 0, 4, "words", 95.0, 20.0, "sha", task_split="train",
                            tasks_file=R.B3_TASKS_REL)
        self.assertEqual((b["task_split"], b["tasks_file"]), ("train", R.B3_TASKS_REL))
        self.assertEqual(list(a), list(b))

    def test_refusals_outside_the_sandbox(self):
        rid = R.new_run_id("B3")
        for extra, text in ((["--task-ids", "retail:12"], "--task-ids"), (["--tries", "2"], "--tries"),
                            (["--shard", "0/5"], "--shard"), (["--b2v-approved"], "--b2v-approved"),
                            (["--workers", "9"], "--workers")):
            with self.assertRaises(SystemExit) as cm:
                R.main(["run", "--step", "B3", "--run-id", rid, "--shard", "0/4"] + extra
                       if "--shard" not in extra else ["run", "--step", "B3", "--run-id", rid] + extra)
            self.assertIn(text, str(cm.exception))


@unittest.skipUnless(HAVE_TAU, "τ-bench (venv) needed")
class TestB3Tasks(unittest.TestCase):

    def test_file_sha_and_fresh_build(self):
        doc = R.load_b3_tasks_file()
        self.assertEqual(doc["sha256"], R.B3_TASKS_FILE_SHA256)
        self.assertEqual([x["task_index"] for x in doc["tasks"]], B3_TASKS)
        self.assertEqual([x["pos"] for x in doc["tasks"]], list(range(64)))
        self.assertEqual(doc["task_split"], "train")
        self.assertEqual(doc["counts"], {"stage_a": {"retail": 64}})
        tau, _sha = R.tau_train_tasks()
        self.assertEqual(len(tau), 500)
        want = [t for t, x in enumerate(tau) if len(x.actions) >= 3]
        self.assertEqual(want, B3_TASKS)
        for x in doc["tasks"]:
            self.assertEqual(x["n_expected_actions"], len(tau[x["task_index"]].actions))
            self.assertEqual(x["task_sha256"], R.sha256_text(R.canonical(tau[x["task_index"]].model_dump())))
            self.assertEqual((x["domain"], x["group"]), ("retail", "stage_a"))

    def test_changed_file_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "b3_tasks.json")
            doc = b3_doc()
            doc["tasks"] = doc["tasks"][:-1]
            with open(p, "w", encoding="utf-8") as f:
                f.write(R.tasks_doc_text(doc))
            with self.assertRaises(R.RunRefused):
                R.load_b3_tasks_file(p)
            with self.assertRaises(R.RunRefused):                # right sha, other content: still refused
                R.load_b3_tasks_file(p, want_sha256=R.sha256_file(p))

    def test_select_units_shards(self):
        doc = R.load_b3_tasks_file()
        tasks = R.select_tasks(doc, "B3", None)
        self.assertEqual(len(tasks), 64)
        units = R.plan_units(tasks, R.STEPS["B3"]["tries"], R.STEPS["B3"]["first_try"])
        self.assertEqual(len(units), 320)
        self.assertEqual({u[2] for u in units}, {0})
        self.assertEqual({u[0] for u in units}, {"retail"})
        got = []
        for i in range(4):
            mine = R.shard_units(units, tasks, (i, 4))
            self.assertEqual(len(mine), 80)
            self.assertEqual({mine[j][3] for j in range(0, len(mine), 5)}, set(R.ARMS))
            got += mine
        self.assertEqual(sorted(got), sorted(units))
        sub = R.select_tasks(doc, "B3", R.parse_task_ids("retail:20,retail:12"))
        self.assertEqual([x["task_index"] for x in sub], [12, 20])
        for bad in ("retail:0", "airline:12", "retail:12,retail:500"):        # 1 expected action; airline; none
            with self.assertRaises(R.RunRefused):
                R.select_tasks(doc, "B3", R.parse_task_ids(bad))
        with self.assertRaises(R.RunRefused):              # B2 never takes the B3 file's tasks
            R.select_tasks(R.load_tasks_file(), "B2", [("retail", 300)])


# ================================================================================================ metrics

WRITE = {"name": "cancel_pending_order", "kwargs": {"order_id": "#W1", "reason": "no longer needed"}}


def b3rec(task, arm, reward=1.0, error=None, trial=0, step="B3"):
    return {"env": "retail", "task_index": task, "trial": trial, "arm": arm, "guard": arm, "reward": reward,
            "error": error, "cost": {"agent": 0.01, "user": 0.0, "guard": 0.0}, "attempts": [],
            "reward_info": {"actions": [WRITE, WRITE, WRITE]}, "n_cap_overrides": 0, "step": step,
            "task_split": "train", "task_group": "stage_a", "run_id": "B3_20261024T000000Z_abcd1234",
            "unit_attempt": 1}


def write_run(root, recs, step="B3"):
    run = os.path.join(root, step, f"{step}_20261024T000000Z_abcd1234")
    for r in recs:
        p = os.path.join(run, r["arm"], "episodes_shard0of1.jsonl")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(r) + "\n")
    return run


class TestB3Metrics(unittest.TestCase):

    def recs(self, n=64, v3_fail=0):
        out = []
        for j, t in enumerate(B3_TASKS[:n]):
            for a in M.ARMS:
                out.append(b3rec(t, a, reward=0.0 if (a == M.V3 and j < v3_fail) else 1.0))
        return out

    def test_b3_line_never_looked_up_in_splits(self):
        sp = M.load_splits()
        c = M.make_conv(b3rec(300, "none"), sp)              # train index 300: not in splits.json at all
        self.assertEqual(c["split"], M.B3_SET)
        t = sorted(t for (d, t), s in sp.items() if d == "retail" and s == "test")[0]
        self.assertEqual(M.make_conv(b3rec(t, "none"), sp)["split"], M.B3_SET)   # a test-group index of the TEST file
        for bad in (dict(b3rec(12, "none"), task_split="test"), dict(b3rec(12, "none"), task_group="train"),
                    dict(b3rec(12, "none"), env="airline"), b3rec(500, "none")):
            with self.assertRaises(ValueError):
                M.make_conv(bad, sp)
        with self.assertRaises(M.TestGroupRefused):          # a non-B3 line still goes through splits.json
            M.make_conv(dict(b3rec(t, "none"), step="B2", task_split="test", task_group=None), sp)

    def test_report_b3_side_result(self):
        sp = M.load_splits()
        convs = M.latest(M.make_conv(r, sp) for r in self.recs())
        doc = M.report_b3(convs)
        side = doc["b3_side_result"]
        self.assertTrue(doc["side_result_only"])
        self.assertNotIn("main_claim", doc)
        self.assertEqual(side["n_tasks"], 64)
        self.assertEqual(side["diff"], 0.0)
        self.assertEqual(side["words"], "not clearly worse")
        self.assertEqual(doc["task_counts"], {"stage_a": {"airline": 0, "retail": 64}})
        self.assertEqual(doc["tasks_without_expected_write"]["count"], 0)
        self.assertEqual(doc["warnings"], [])
        bad = M.latest(M.make_conv(r, sp) for r in self.recs(v3_fail=20))
        s2 = M.report_b3(bad)["b3_side_result"]
        self.assertAlmostEqual(s2["diff"], -20 / 64)
        self.assertEqual(s2["words"], "not shown")

    def test_never_pooled(self):
        sp = M.load_splits()
        b3 = [M.make_conv(r, sp) for r in self.recs(4)]
        t = sorted(t for (d, t), s in sp.items() if d == "retail" and s == "val")[0]
        b2 = [M.make_conv({**b3rec(t, a), "step": "B2", "task_split": "test", "task_group": "val"}, sp)
              for a in M.ARMS]
        with self.assertRaises(M.B3Mixed):
            M.report(b3 + b2)
        with self.assertRaises(M.B3Mixed):
            M.report(b2, raw=b2 + b3)
        with self.assertRaises(M.B3Mixed):
            M.report_b3(b3 + b2)
        M.report(b2)                                         # B2 alone: as before

    def test_cli_and_interim(self):
        with tempfile.TemporaryDirectory() as d:
            run = write_run(os.path.join(d, "eval_v3"), self.recs(40, v3_fail=2))
            so = io.StringIO()
            with contextlib.redirect_stdout(so):
                M.main(["run", "--run-dir", run])
            text = so.getvalue()
            doc = json.loads(text[text.find("{"):])
            self.assertEqual(doc["step"], "B3")
            self.assertEqual(doc["b3_side_result"]["n_tasks"], 40)
            self.assertIn("rests on 40 tasks", " ".join(doc["warnings"]))
            rep = I.interim([run])
            self.assertEqual(rep["step"], "B3")
            self.assertEqual(rep["harm"]["half"], 160)
            self.assertTrue(rep["harm"]["reached"])          # 200 conversations in complete groups
            self.assertAlmostEqual(rep["harm"]["diff"], -2 / 40)
            self.assertFalse(rep["harm"]["fire"])
            small = write_run(os.path.join(d, "small"), self.recs(31))
            self.assertFalse(I.interim([small])["harm"]["reached"])      # 155 < 160
            t = sorted(t for (dd, t), s in M.load_splits().items() if dd == "retail" and s == "val")[0]
            b2 = write_run(os.path.join(d, "b2"), [{**b3rec(t, a), "step": "B2", "task_split": "test",
                                                    "task_group": "val"} for a in M.ARMS], step="B2")
            with self.assertRaises(M.B3Mixed):
                I.interim([run, b2])
            with self.assertRaises(SystemExit):
                with contextlib.redirect_stdout(io.StringIO()):
                    M.main(["run", "--run-dir", run, "--run-dir", b2])
            self.assertNotIn("step", I.interim([b2]))
            self.assertEqual(I.interim([b2])["harm"]["half"], I.HALF)


if __name__ == "__main__":
    unittest.main()
