"""Tests for the v4 halfway check and stop rules (scoring/v4_online_interim.py). Made-up lines only (no real
conversation is read), no LLM, no network. Run folders are temporary folders (removed at the end).

Covers: the halfway decision is made once and saved (halfway.json, O_EXCL), a later call returns the saved decision
even with more lines; a late look gives the on-time answer (line-time order from the ledger, group completion
moment, re-runs); a live shard's cut-off last line; the error stop per arm file; the CLI.

Run from predicate_correctness/:
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 /home/azureuser/miniconda3/bin/python3 -B -m unittest tests.test_v4_interim -v
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

from scoring import v4_online_interim as I     # noqa: E402
from scoring import v4_online_metrics as M     # noqa: E402

SPLITS = M.load_splits()
RETAIL = sorted(t for (d, t), s in SPLITS.items() if d == "retail" and s in ("train", "val"))


def rec(task, arm, reward=1.0, error=None, trial=0, step="B2v4", attempt=1, domain="retail"):
    return {"env": domain, "task_index": task, "trial": trial, "arm": arm, "guard": arm, "reward": reward,
            "error": error, "cost": {"agent": 0.001, "user": 0.0, "guard": 0.0}, "attempts": [],
            "reward_info": {"actions": []}, "n_cap_overrides": 0, "step": step, "run_id": "R1",
            "unit_attempt": attempt, "task_split": "test", "task_group": SPLITS[(domain, task)],
            "conversation_id": f"R1/{arm}/{domain}/{task}/{trial}/{attempt}"}


def group(task, v4_wins, t0, step="B2v4"):
    """The 6 arms of one (task, try 0) group, one line each at times t0, t0+1, ...; v4_wins: True v4 1 / frozen 0,
    False v4 0 / frozen 1, None both 1 (a tie). On B2v4 the 4 old arms go to the made-up v3 baseline (write())."""
    out = []
    for i, arm in enumerate(M.ARMS):
        r = 1.0
        if arm == M.V4:
            r = 0.0 if v4_wins is False else 1.0
        elif arm == M.FROZEN:
            r = 0.0 if v4_wins is True else 1.0
        out.append((rec(task, arm, r, step=step), t0 + i))
    return out


def stamp(t):
    return f"20261024T01{t // 60:02d}{t % 60:02d}Z"


TASK_SHA_B2 = "5f7b9b71c727531c29cbe1ab8e7189b4bcf67195bb5b78f02437f98d08baf96e"
TASK_SHA = {"B2v4": TASK_SHA_B2, "B3v4": "0394a99ad08d3c832419f63333bc22b78096b993af5fb39c36c20a47917b33ff"}
BASE_ROOT = tempfile.mkdtemp(prefix="v4_interim_v3base_")         # made-up v3 baselines (removed at the end)


def tearDownModule():
    import shutil
    shutil.rmtree(BASE_ROOT, ignore_errors=True)


def baseline_of(run, step):
    """P10 arm plan (made-up data): the made-up v3 baseline folder of a run, named in its run.json."""
    plan = M.BASELINE_PLAN[step]
    base = os.path.join(BASE_ROOT, os.path.abspath(run).strip("/").replace("/", "_"), plan["run_id"])
    if not os.path.exists(os.path.join(base, "run.json")):
        for a in plan["arms"]:
            os.makedirs(os.path.join(base, a), exist_ok=True)
        with open(os.path.join(base, "run.json"), "w") as f:
            json.dump({"ident": {"step": plan["v3_step"], "run_id": plan["run_id"], "tasks_file_sha256": TASK_SHA[step]}},
                      f)
        os.makedirs(run, exist_ok=True)
        with open(os.path.join(run, "run.json"), "w") as f:
            json.dump({"ident": {"step": step, "run_id": "R1"},
                       "baseline": {"run_dir": base, "run_id": plan["run_id"], "arms": list(plan["arms"]),
                                    "task_file_sha256": TASK_SHA[step]}}, f)
    return base


def write(run, items, shard="0of1", ledger=True):
    """Append (line, time) items: the episode line to <run>/<arm>/episodes_shard<shard>.jsonl and, if ledger, the
    unit's "end" line to <run>/ledger/units_shard<shard>.jsonl (as the runner does). P10 arm plan: on B2v4 a line of an
    old arm goes to the made-up v3 baseline instead (step B2, no ledger line: v3's saved run)."""
    for r, t in items:
        if r["step"] in M.BASELINE_PLAN and not M.live_for(r["step"], r["arm"], r["env"], r["task_index"]):
            base = baseline_of(run, r["step"])
            with open(os.path.join(base, r["arm"], "episodes_shard0of1.jsonl"), "a") as f:
                f.write(json.dumps(dict(r, step=M.BASELINE_PLAN[r["step"]]["v3_step"])) + "\n")
            continue
        d = os.path.join(run, r["arm"])
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"episodes_shard{shard}.jsonl"), "a") as f:
            f.write(json.dumps(r) + "\n")
        if ledger:
            os.makedirs(os.path.join(run, "ledger"), exist_ok=True)
            with open(os.path.join(run, "ledger", f"units_shard{shard}.jsonl"), "a") as f:
                f.write(json.dumps({"event": "end", "conversation_id": r["conversation_id"], "time": stamp(t)})
                        + "\n")
    return run


def quiet(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fn(*a, **kw)
    return rc, buf.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self._half = dict(I.HALF)
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        I.HALF[M.STEP_B2] = 2                       # 2 complete live groups (P10: direct_facts_v4 + v4)

    def tearDown(self):
        I.HALF.clear()
        I.HALF.update(self._half)
        self._tmp.cleanup()

    def run_dir(self, name):
        p = os.path.join(self.root, name)
        os.makedirs(p, exist_ok=True)
        return p


class TestHalfwayOnce(Base):

    def test_second_call_returns_saved_even_with_more_lines(self):
        run = self.run_dir("R")
        write(run, group(RETAIL[0], False, 0) + group(RETAIL[1], False, 10))
        rep = I.interim([run])
        h = rep["harm"]
        self.assertEqual((h["reached"], h["diff"], h["fire"], h["source"]), (True, -1.0, True, "computed now"))
        p = os.path.join(run, I.HALFWAY_FILENAME)
        self.assertEqual(h["saved_to"], [p])
        with open(p, "rb") as f:
            first = f.read()
        # more lines: v4 now wins 4 groups; a new computation over everything would not fire
        write(run, [x for k in range(2, 6) for x in group(RETAIL[k], True, 20 + 10 * k)])
        I.HALF[M.STEP_B2] = 6                       # even a changed mark does not recompute
        rep2 = I.interim([run])
        h2 = rep2["harm"]
        self.assertEqual((h2["source"], h2["diff"], h2["fire"], h2["file"]), ("saved", -1.0, True, p))
        self.assertEqual(h2["groups"], h["groups"])
        self.assertIn("harm", rep2["fired"])                       # a fire stays a fire
        with open(p, "rb") as f:
            self.assertEqual(f.read(), first)                      # never replaced
        self.assertEqual(I.save_halfway([run], h2), [])            # O_EXCL: an existing file is never changed
        with open(p, "rb") as f:
            self.assertEqual(f.read(), first)

    def test_not_reached_saves_nothing_and_no_file_flag(self):
        run = self.run_dir("R")
        write(run, group(RETAIL[0], False, 0))
        h = I.interim([run])["harm"]
        self.assertEqual((h["reached"], h["fire"]), (False, False))
        self.assertFalse(os.path.exists(os.path.join(run, I.HALFWAY_FILENAME)))
        write(run, group(RETAIL[1], False, 10))
        h = I.interim([run], save_halfway=False)["harm"]
        self.assertEqual((h["reached"], h["fire"]), (True, True))
        self.assertFalse(os.path.exists(os.path.join(run, I.HALFWAY_FILENAME)))
        rc, out = quiet(I.main, ["--run-dir", run, "--no-halfway-file"])
        self.assertFalse(os.path.exists(os.path.join(run, I.HALFWAY_FILENAME)))
        rc, out = quiet(I.main, ["--run-dir", run])
        self.assertTrue(os.path.exists(os.path.join(run, I.HALFWAY_FILENAME)))

    def test_tie_fires_and_no_rule_for_h(self):
        I.HALF[M.STEP_B2] = 20                      # 20 groups: 3 losses, 17 ties -> -3 / 20 = -0.15 exactly
        run = self.run_dir("T")
        write(run, [x for k in range(20) for x in group(RETAIL[k], False if k < 3 else None, 10 * k)])
        h = I.interim([run])["harm"]
        self.assertAlmostEqual(h["diff"], -0.15)
        self.assertEqual((h["n_tasks"], h["fire"]), (20, True))
        h_run = self.run_dir("H")
        write(h_run, group(RETAIL[0], False, 0, step="Hv4") + group(RETAIL[1], False, 10, step="Hv4"))
        h = I.interim([h_run])["harm"]
        self.assertEqual((h["reached"], h["fire"]), (None, False))
        self.assertFalse(os.path.exists(os.path.join(h_run, I.HALFWAY_FILENAME)))

    def test_saved_decision_of_another_step_refused(self):
        run = self.run_dir("R")
        write(run, group(RETAIL[0], False, 0) + group(RETAIL[1], False, 10))
        with open(os.path.join(run, I.HALFWAY_FILENAME), "w") as f:
            json.dump({"step": "B3v4", "fire": False}, f)
        with self.assertRaises(M.StepMixed):
            I.interim([run])

    def test_cli_writes_stop_and_keeps_line_format(self):
        run = self.run_dir("R")
        write(run, group(RETAIL[0], False, 0) + group(RETAIL[1], False, 10))
        rc, out = quiet(I.main, ["--run-dir", run, "--write-stop"])
        self.assertEqual(rc, 0)
        self.assertIn("[v4-interim] B2v4: harm True state False cost False errors False -> STOP", out)
        self.assertIn("STOP files written: 1", out)
        rc, out = quiet(I.main, ["--run-dir", run, "--write-stop"])      # the watcher's next look
        self.assertIn("-> STOP; STOP files written: 0", out)


class TestLateLook(Base):

    def scenario(self):
        """Line times: group X has its arms at t 20-24 but its v4 arm ends at t 90; group A (shard 1, t 0-4);
        group B (shard 0, t 10-15, its v4 unit errors once and is re-run); then groups C-F (shard 0, late) where v4
        wins. First 2 complete groups in line-time order: A, B (v4 loses both: -1, fires). Over everything: no."""
        a, b, x = RETAIL[0], RETAIL[1], RETAIL[2]
        late = [x_ for k in range(3, 7) for x_ in group(RETAIL[k], True, 30 + 10 * k)]
        xs = [(r, t + 20) for r, t in group(x, True, 0)]        # t 20-24; its last arm is moved to t 90 below
        b_lines = [(rec(b, M.V4, 0.0, error="RateLimitError: x"), 10)]            # v4 unit fails once at t 10
        others = [r for r, _t in group(b, False, 0) if r["arm"] != M.V4]
        b_lines += [(r, 11 + i) for i, r in enumerate(others)]                     # t 11-14
        b_lines.append((rec(b, M.V4, 0.0, attempt=2), 15))                         # its re-run ends at t 15
        return {"A": group(a, False, 0), "B": b_lines, "X4": xs[:-1], "X5": [(xs[-1][0], 90)], "late": late}

    def test_late_look_equals_on_time_look(self):
        s = self.scenario()
        on_time = self.run_dir("on_time")             # what a look right after t 15 would have seen
        write(on_time, s["X4"], shard="0of2")
        write(on_time, s["A"], shard="1of2")
        write(on_time, s["B"], shard="0of2")
        late = self.run_dir("late")                   # a look long after: every line, files in another order
        write(late, s["X4"], shard="0of2")
        write(late, s["B"], shard="0of2")
        write(late, s["late"], shard="0of2")
        write(late, s["X5"], shard="0of2")
        write(late, s["A"], shard="1of2")
        h1 = I.interim([on_time], save_halfway=False)["harm"]
        h2 = I.interim([late], save_halfway=False)["harm"]
        self.assertEqual((h1["reached"], h1["diff"], h1["fire"]), (True, -1.0, True))
        for k in ("reached", "diff", "fire", "groups", "n_tasks", "complete_groups",
                  "conversations_in_complete_groups"):
            self.assertEqual(h1[k], h2[k], k)
        self.assertEqual([g[1] for g in h2["groups"]], [RETAIL[0], RETAIL[1]])     # A then B; X completes at t 90
        self.assertEqual(h2["last_line"]["time"], stamp(15))
        self.assertEqual(h2["order"]["untimed"], 0)
        # the old rule (every complete group at a late look) would not fire here
        comp, _ = M.complete_groups(M.load_step([late])["latest"], M.ARMS)      # pooled with the v3 baseline
        d = M._paired(M.per_task(comp, M.V4, "all"), M.per_task(comp, M.FROZEN, "all"))
        self.assertGreater(sum(d.values()) / len(d), I.HARM)

    def test_dropped_group_left_out(self):
        run = self.run_dir("R")
        write(run, group(RETAIL[0], False, 0) + group(RETAIL[1], True, 10) + group(RETAIL[2], True, 20))
        with open(os.path.join(run, "dropped_groups_shard0of1.jsonl"), "w") as f:
            f.write(json.dumps({"env": "retail", "task_index": RETAIL[0], "trial": 0, "reason": "x"}) + "\n")
        h = I.interim([run], save_halfway=False)["harm"]
        self.assertEqual([g[1] for g in h["groups"]], [RETAIL[1], RETAIL[2]])
        self.assertEqual(h["fire"], False)

    def test_no_ledger_is_deterministic(self):
        run = self.run_dir("R")
        write(run, group(RETAIL[0], False, 0) + group(RETAIL[1], False, 10), ledger=False)
        h = I.interim([run], save_halfway=False)["harm"]
        self.assertEqual((h["reached"], h["diff"], h["order"]["timed_by_ledger"]), (True, -1.0, 0))


class TestPooledHalfway(Base):
    """P10 arm plan: a group = the 2 live v4 arms; frozen TGR from v3's baseline (B3v4 fill tasks: the live frozen
    line); a key whose frozen line is an error line is left out of the pair."""

    @staticmethod
    def b3(task, arm, reward=1.0, error=None):
        r = rec(RETAIL[0], arm, reward, error=error, step="B3v4")
        r.update(task_index=task, task_split="train", task_group="stage_a",
                 conversation_id=f"R1/{arm}/retail/{task}/0/1")
        return r

    def test_b3_fill_frozen_live_and_error_left_out(self):
        I.HALF[M.STEP_B3] = 3
        fill = M.B3_FILL_TASKS[0][1]
        items, t = [], 0
        for task, frozen_err in ((12, None), (20, "boom"), (fill, None)):
            for arm in M.ARMS:
                r = 0.0 if arm == M.V4 else 1.0
                items.append((self.b3(task, arm, r, error=frozen_err if arm == M.FROZEN else None), t))
                t += 1
        run = self.run_dir("B3")
        write(run, items)
        h = I.interim([run], save_halfway=False)["harm"]
        self.assertEqual((h["reached"], h["complete_groups"], h["n_tasks"], h["diff"], h["fire"]),
                         (True, 3, 2, -1.0, True))
        self.assertEqual(h["groups_without_frozen_pair"], [["retail", 20, 0]])
        self.assertEqual(h["baseline_run_id"], M.BASELINE_PLAN["B3v4"]["run_id"])
        self.assertTrue(os.path.exists(os.path.join(run, M.FROZEN, "episodes_shard0of1.jsonl")))   # fill: live

    def test_live_old_arm_refused(self):
        run = self.run_dir("R")
        write(run, group(RETAIL[0], False, 0))
        os.makedirs(os.path.join(run, M.FROZEN), exist_ok=True)
        with open(os.path.join(run, M.FROZEN, "episodes_shard0of1.jsonl"), "a") as f:
            f.write(json.dumps(rec(RETAIL[1], M.FROZEN)) + "\n")
        with self.assertRaises(M.BaselineRefused):
            I.interim([run], save_halfway=False)


class TestCutOffShard(Base):

    def test_cut_off_last_line_skipped(self):
        run = self.run_dir("R")
        write(run, group(RETAIL[0], False, 0) + group(RETAIL[1], False, 10))
        p = os.path.join(run, M.V4, "episodes_shard0of1.jsonl")
        with open(p, "a") as f:
            f.write(json.dumps(rec(RETAIL[2], M.V4))[:40])          # a shard is writing this line now
        with open(os.path.join(run, "ledger", "units_shard0of1.jsonl"), "a") as f:
            f.write('{"event": "end", "conv')
        self.assertEqual(len(I.read_lines(p)), 2)
        rep = I.interim([run], save_halfway=False)
        self.assertEqual((rep["harm"]["reached"], rep["harm"]["fire"]), (True, True))
        self.assertEqual(rep["errors"]["files"][p]["lines"], 2)

    def test_bad_line_in_the_middle_raises(self):
        p = os.path.join(self.root, "episodes_x.jsonl")
        with open(p, "w") as f:
            f.write('{"a": 1}\n{"b": \n{"c": 3}\n')
        with self.assertRaises(json.JSONDecodeError):
            I._read_tolerant(p)
        with open(p, "w") as f:
            f.write('{"a": 1}\n{"c": 3}\n{"d": ')
        self.assertEqual(I._read_tolerant(p), [{"a": 1}, {"c": 3}])
        with open(p, "w") as f:
            f.write('{"a": 1}\n{"c": 3}')                            # complete last line without a newline: kept
        self.assertEqual(I._read_tolerant(p), [{"a": 1}, {"c": 3}])


class TestErrorsPerArmFile(unittest.TestCase):

    @staticmethod
    def lines(n, errs, at_end=False):
        out = [rec(RETAIL[0], M.V4) for _ in range(n)]
        idx = range(n - errs, n) if at_end else range(0, 2 * errs, 2)
        for i in idx:
            out[i] = dict(out[i], error="X")
        return out

    def test_pooled_would_fire_per_file_does_not(self):
        files = {f"f{i}": self.lines(20, 2) for i in range(5)}      # 10 errors of 100 lines, 2 per file
        r = I.error_check(files)
        self.assertEqual((r["error_lines"], r["lines"]), (10, 100))
        self.assertFalse(r["fire"])
        self.assertEqual(r["per"], "arm file")

    def test_one_file_fires_alone(self):
        files = {"bad": self.lines(100, 10), "ok1": self.lines(300, 0)}   # 10 / 100 = 10 % in one file; 2.5 % pooled
        r = I.error_check(files)
        self.assertTrue(r["fire"])
        self.assertEqual(r["fired_files"], ["bad"])
        self.assertFalse(I.error_check({"bad": self.lines(250, 10), "ok": self.lines(10, 0)})["fire"])  # 4 %

    def test_streak_per_file(self):
        self.assertTrue(I.error_check({"a": self.lines(100, 5, at_end=True)})["fire"])
        self.assertFalse(I.error_check({"a": self.lines(100, 4, at_end=True),
                                        "b": self.lines(100, 4, at_end=True)})["fire"])
        self.assertEqual(I.error_check({"a": []})["fire"], False)


if __name__ == "__main__":
    unittest.main()
