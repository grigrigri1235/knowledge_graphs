"""Tests of guard/run_online_v4.py and guard/soft_stop_v4.py (tracker v4, part P1; owner P1e).

Fast tests (standard library; τ-bench parts skipped without the venv): arms and steps (v3's arm not runnable), the
task lists and unit counts of every step (P10 arm plan: B1v4 4, B2v4 594, B3v4 188, Hv4 594; DEV20v4 dropped), shards (up to 6)
cover every unit once, run ids and paths (output/eval_v4), the refusal of the partner's test 66, the refusals before
any runner import (the dropped DEV20v4 and its old flag, shards, workers, --tries / --task-ids, out root), the approval words (--approval and
--approved), `where` and the conversation id on every tiny answer (ConversationStore, AskLog, make_answers_hook with
a QuestionsV4 stand-in), the freeze check adapter, the real backend's approval flag, the soft stop's limits, cap, thresholds, reserve, the per-unit
check and the halfway rule, resume backups (cp counts once, mv refused), B1v4's check, the group pool.
Audit P7 fixes: the main chat's flag on the real path (TestRefusalsBeforeTheRunner), the B1 gate (TestB1Gate,
TestB1GateInASandbox), the freeze manifest's coverage of every runner input (TestFreezeCheck), the step flock, the
units in flight and the split tiny budget (TestGroupPoolShardRace), other live steps against the cap
(TestCapWithLiveSteps), killed shards' units (TestKilledShardSpend).
DEV20v4 dropped (user decision; TestDroppedDev20) and the halfway watcher scoring/v4_interim.sh with fake pids and a
fake check command (TestHalfwayWatcher, $0, no venv needed).

Slow tests (a fresh venv process each, network blocked, the REAL v4 modules guard/tgr_tracker_v4.py,
guard/direct_facts_v4.py, state_tracker/v4/questions_v4.py (FakeBackendV4), with a spy around the tracker's build):
  - the dry run of every step (0 LLM calls, nothing written, get_env only with user_strategy="human"): the unit counts
    and the shard cover;
  - a sandbox B1v4 run with a fake Azure client behind every LLM seam (as v3's equality check): 10 lines, 0 errors,
    conversation_id on every episode line and every tiny answer record, `where` with the check index at every v4
    check, Conversation.v4_blocks = [] at each conversation's first check, writes only under output/eval_v4/dryrun/;
  - a second process on a locked shard and a moved backup exit before any call.

  ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v4_run_online        (from predicate_correctness/)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from guard import run_online_v4 as R                                          # noqa: E402
from guard import soft_stop_v4 as S                                           # noqa: E402

# audit P9 #6: the v4 total reads the dev spend ledger (<v4 root>/dev/dev_spend_ledger.jsonl). These tests never read
# the real one (a paid dev check may be writing it): every scan in this process resolves it to a path that does not
# exist; the ledger tests give their own temp ledger.
_REAL_DEV_LEDGER_RELPATH = S.DEV_LEDGER_RELPATH
S.DEV_LEDGER_RELPATH = "/nonexistent/v4_tests_never_read_the_dev_ledger.jsonl"
VENV_PY = os.path.expanduser("~/venvs/tau-bench/bin/python")
FIVE_ARMS = ("none", "direct", "direct_facts_v4", "tgr_frozen", "tgr_tracker_v4")   # made-up groups of the pool tests
B1_ARMS = ("direct_facts_v4", "tgr_tracker_v4")                                    # P10: B1v4's live arms
CHECK_TASKS = "retail:4,airline:4"
try:
    import tau_bench  # noqa: F401
    HAVE_TAU = True
except ImportError:
    HAVE_TAU = False
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0", LITELLM_LOCAL_MODEL_COST_MAP="True")


def docs():
    return {"online": R.load_tasks_file(), "b3": R.load_b3_tasks_file() if HAVE_TAU else None}


def step_doc(d, step):
    return d[R.STEPS[step]["tasks"]]


# ================================================================================================ constants

class TestArmsAndSteps(unittest.TestCase):

    def test_arms(self):
        self.assertEqual(R.ARMS, ("none", "direct", "tgr_frozen", "tgr_tracker_v3", "direct_facts_v4", "tgr_tracker_v4"))
        self.assertEqual(R.LLM_ARMS, ("direct", "direct_facts_v4", "tgr_frozen"))
        self.assertEqual(R.V4_ARM, "tgr_tracker_v4")
        self.assertNotIn("direct_facts_v3", R.ARMS)
        self.assertEqual(R.V3_ARM_STEPS, ("B3v4", "Hv4"))                # tgr_tracker_v3 only where the plan runs it
        for arm in ("tgr_tracker_v3", "direct_facts_v3"):
            with self.assertRaises(ValueError) as cm:                # refused before any import of the copy
                R.build_arm(arm, "retail", [])
            self.assertIn("not runnable", str(cm.exception))
        self.assertEqual(S.ALL_ARMS, R.ARMS)
        for step in ("B1v4", "B2v4"):                                      # build_arm refuses v3's tracker there
            with self.assertRaises(ValueError):
                R.build_arm("tgr_tracker_v3", "retail", [], step=step)
        # the P10 arm plan (user decision)
        v4 = ("direct_facts_v4", "tgr_tracker_v4")
        self.assertEqual(S.GROUP_ARMS, v4)
        self.assertEqual(S.UNITS_PER_GROUP, 2)
        self.assertEqual({s: S.step_live_arms(s) for s in R.STEPS},
                         {"B1v4": v4, "B2v4": v4, "B3v4": R.ARMS, "Hv4": R.ARMS})
        self.assertEqual(S.group_arms("B3v4", "retail", 368), R.ARMS)       # a fill task: all 6
        self.assertEqual(S.group_arms("B3v4", "retail", 0), v4)
        self.assertEqual(S.group_arms("Hv4", "airline", 4), R.ARMS)
        self.assertEqual(S.B3_FILL_ARMS, ("none", "direct", "tgr_frozen", "tgr_tracker_v3"))
        self.assertEqual(sorted(t for _, t in S.B3_FILL_TASKS), [368, 380, 393, 415, 416, 427, 431, 433, 434, 445,
                                                                 451, 462, 464, 474, 497])

    def test_steps_profiles_and_models(self):
        self.assertEqual(sorted(R.STEPS), ["B1v4", "B2v4", "B3v4", "Hv4"])
        self.assertEqual({s: c["profile"] for s, c in R.STEPS.items()},
                         {"B1v4": "luna-dev", "B2v4": "luna-dev", "B3v4": "luna-dev", "Hv4": "nano-agent-luna"})
        self.assertEqual(R.ROLE_MODELS["nano-agent-luna"], {"agent": "gpt-5-nano", "user": "gpt-6-luna",
                                                            "guard": "gpt-6-luna"})
        self.assertEqual(set(R.ROLE_MODELS["luna-dev"].values()), {"gpt-6-luna"})
        R.check_role_models("nano-agent-luna", {"agent": "gpt-5-nano", "user": "gpt-6-luna", "guard": "gpt-6-luna"})
        for prof, used in (("luna-dev", {"agent": "gpt-5-nano", "user": "gpt-6-luna", "guard": "gpt-6-luna"}),
                           ("nano-agent-luna", {"agent": "gpt-5-nano", "user": "gpt-5-nano", "guard": "gpt-6-luna"}),
                           ("nano-agent-luna", {"agent": "gpt-5-nano", "user": "gpt-6-luna", "guard": "gpt-5-nano"})):
            with self.assertRaises(R.RunRefused):
                R.check_role_models(prof, used)
        self.assertEqual(R.MAX_SHARDS, 6)
        self.assertEqual(R.STEPS["B1v4"]["shards"], (1,))
        for s in ("B2v4", "B3v4", "Hv4"):
            self.assertEqual(R.STEPS[s]["shards"], (1, 2, 3, 4, 5, 6))
        self.assertEqual(R.WANT_UNITS, {"B1v4": 4, "B2v4": 594, "B3v4": 188, "Hv4": 594})
        self.assertEqual((R.QUESTION_MODEL, R.QUESTION_EFFORT), ("gpt-6-luna", "low"))

    def test_limits_and_cap(self):
        # 2026-10-24, user decision "finish H": Hv4 $8 -> $15; B2v4, B3v4 (finished) $10 -> $7, $6 -> $4
        self.assertEqual(S.STEP_LIMITS_USD, {"dev": 2.0, "B1v4": 1.0, "B2v4": 7.0, "B3v4": 4.0, "Hv4": 15.0})
        self.assertEqual(S.V4_CAP_USD, 30.0)
        self.assertEqual(S.STEPS, ("B1v4", "B2v4", "B3v4", "Hv4"))
        self.assertEqual(S.DROPPED_STEPS, ("DEV20v4",))
        self.assertEqual(S.cap_usd(), 30.0)
        self.assertEqual(S.HALFWAY_GROUPS, {"B2v4": 149, "B3v4": 32})
        self.assertEqual(S.HALFWAY_CONVERSATIONS, {"B2v4": 298, "B3v4": 64})
        self.assertEqual(R.B1_CONVERSATIONS, 4)
        self.assertEqual(R.B1_MEAN_COST_LIMIT_USD, 0.032)
        self.assertTrue(S.V4_ROOT.endswith(os.path.join("output", "eval_v4")))
        self.assertEqual(R.V4_ROOT, S.V4_ROOT)
        self.assertEqual(S.P90_PRIOR_USD, 0.061)

    def test_thresholds_from_the_preregistration(self):
        b2 = {"none": 0.022, "direct": 0.044, "direct_facts_v4": 0.043, "tgr_frozen": 0.039, "tgr_tracker_v3": 0.030,
              "tgr_tracker_v4": 0.030}
        b3 = {"none": 0.045, "direct": 0.086, "direct_facts_v4": 0.085, "tgr_frozen": 0.083, "tgr_tracker_v3": 0.063,
              "tgr_tracker_v4": 0.063}
        for s in ("B1v4", "B2v4", "Hv4"):
            self.assertEqual(S.arm_thresholds(s), b2, s)
            self.assertEqual(S.unknown_arm_threshold(s), 0.044)
        self.assertEqual(S.arm_thresholds("B3v4"), b3)
        self.assertEqual(S.unknown_arm_threshold("B3v4"), 0.086)
        self.assertEqual(set(S.ARM_MEAN_STOP_USD_BY_STEP), {"B1v4", "B2v4", "B3v4", "Hv4"})
        self.assertEqual(set(S.UNKNOWN_ARM_BY_STEP), {"B1v4", "B2v4", "B3v4", "Hv4"})
        self.assertEqual(S.todo_markers(), [])


# ================================================================================================ tasks

class TestTasks(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.d = docs()

    def test_online_file_is_v3s_and_read_only(self):
        doc = self.d["online"]
        self.assertEqual(doc["sha256"], R.TASKS_FILE_SHA256)
        self.assertEqual(R.TASKS_REL, "output/eval_v3/online_tasks.json")
        self.assertEqual(R.B3_TASKS_REL, "output/eval_v3/b3_tasks.json")

    @unittest.skipUnless(HAVE_TAU, "τ-bench (venv) not importable")
    def test_fresh_builds_equal_v3s_files(self):
        with open(R.TASKS_FILE, encoding="utf-8") as f:
            self.assertEqual(f.read(), R.tasks_doc_text(R.build_tasks_doc()))
        with open(R.B3_TASKS_FILE, encoding="utf-8") as f:
            self.assertEqual(f.read(), R.tasks_doc_text(R.build_b3_tasks_doc()))

    @unittest.skipUnless(HAVE_TAU, "τ-bench (venv) not importable")
    def test_units_of_every_step(self):
        for step, want in R.WANT_UNITS.items():
            cfg = R.STEPS[step]
            tasks = R.select_tasks(step_doc(self.d, step), step, None)
            units = R.plan_units(tasks, cfg["tries"], cfg["first_try"], step)
            self.assertEqual(len(units), want, step)
            self.assertEqual(len(set(units)), len(units))
            self.assertEqual(sorted({u[2] for u in units}), list(range(cfg["tries"])), step)
            i = 0
            while i < len(units):                                             # each group's live arms side by side
                g = units[i][:3]
                arms = S.group_arms(step, g[0], g[1])
                self.assertEqual(sorted(u[3] for u in units[i:i + len(arms)]), sorted(arms), (step, g))
                self.assertEqual({u[:3] for u in units[i:i + len(arms)]}, {g})
                i += len(arms)
            if step == "B3v4":                                                # 64 x 2 + the 15 fill tasks x 4
                fill = [u for u in units if u[3] in S.B3_FILL_ARMS]
                self.assertEqual(len(fill), 60)
                self.assertEqual({u[:2] for u in fill}, set(S.B3_FILL_TASKS))
                self.assertTrue(set(S.B3_FILL_TASKS) <= {(x["domain"], x["task_index"]) for x in tasks})
            for n in cfg["shards"]:
                got = []
                for i in range(n):
                    mine = R.shard_units(units, tasks, (i, n))
                    got += mine
                    if step in ("B2v4", "Hv4"):
                        self.assertEqual({u[0] for u in mine}, {"retail", "airline"}, (step, n, i))
                self.assertEqual(sorted(got), sorted(units), (step, n))
        b1 = R.select_tasks(self.d["online"], "B1v4", None)
        self.assertEqual([(x["domain"], x["task_index"]) for x in b1], [("retail", 4), ("airline", 4)])
        h = R.select_tasks(self.d["online"], "Hv4", None)
        self.assertEqual(h, R.select_tasks(self.d["online"], "B2v4", None))   # H: the same 99 tasks
        self.assertEqual(R.step_task_split("B3v4"), "train")
        self.assertEqual({R.step_task_split(s) for s in ("B1v4", "B2v4", "Hv4")}, {"test"})

    def test_partner_test_66_refused(self):
        sp = R.load_splits()
        test = {d: sorted(int(k) for k, v in sp[d].items() if v == "test") for d in R.DOMAINS}
        self.assertEqual({d: len(v) for d, v in test.items()}, R.PARTNER_TEST_COUNTS)       # 46 + 20 = 66
        online = {(x["domain"], x["task_index"]) for x in self.d["online"]["tasks"]}
        self.assertFalse(online & {(d, t) for d, ts in test.items() for t in ts})
        for dom in R.DOMAINS:
            t = test[dom][0]
            other = "airline" if dom == "retail" else "retail"
            with self.assertRaises(R.RunRefused) as cm:
                R.select_tasks(self.d["online"], "B1v4", R.parse_task_ids(f"{dom}:{t},{other}:4"))
            self.assertIn("test", str(cm.exception))
            for step in ("B2v4", "Hv4"):
                with self.assertRaises(R.RunRefused):
                    R.select_tasks(self.d["online"], step, [(dom, t)])
        if self.d["b3"] is not None:
            with self.assertRaises(R.RunRefused):
                R.select_tasks(self.d["b3"], "B3v4", [("retail", test["retail"][0])])
        with tempfile.TemporaryDirectory() as d:                    # a file that sneaks a test task in
            p = os.path.join(d, "t.json")
            with open(R.TASKS_FILE, encoding="utf-8") as f:
                text = f.read()
            with open(p, "w", encoding="utf-8") as f:
                f.write(text.replace('"group": "val"', '"group": "test"', 1))
            with self.assertRaises(R.RunRefused):
                R.load_tasks_file(p)
            with self.assertRaises(R.RunRefused):
                R.load_tasks_file(p, want_sha256=None)


class TestIdsAndPaths(unittest.TestCase):

    def test_run_ids(self):
        for step in R.STEPS:
            rid = R.new_run_id(step)
            self.assertRegex(rid, rf"^{step}_\d{{8}}T\d{{6}}Z_[0-9a-f]{{8}}$")
            R.check_run_id(step, rid)
        self.assertNotEqual(R.new_run_id("B2v4"), R.new_run_id("B2v4"))
        for step, bad in (("B1v4", R.new_run_id("B2v4")), ("B2v4", "B2_20261023T000000Z_00000000"), ("Hv4", ""),
                          ("B3v4", "B3_20261023T000000Z_00000000")):
            with self.assertRaises(R.RunRefused):
                R.check_run_id(step, bad)
        with self.assertRaises(R.RunRefused):
            R.new_run_id("B2")

    def test_paths(self):
        rid = R.new_run_id("B2v4")
        p = R.resolve_paths(R.V4_ROOT, "B2v4", rid, (5, 6))
        self.assertEqual(p["run_dir"], os.path.join(R.V4_ROOT, "B2v4", rid))
        self.assertFalse(p["sandbox"])
        self.assertEqual(p["log"], os.path.join(R.LOGS_DIR, f"v4_B2v4_{rid}_s5.log"))
        self.assertEqual(p["cache_root"], os.path.join(R.LLMCACHE_DIR, f"v4_{rid}"))
        self.assertEqual(p["questions_store"], os.path.join(p["run_dir"], "questions", "answers_shard5of6.jsonl"))
        self.assertEqual(p["asks_log"], os.path.join(p["run_dir"], "questions", "asks_shard5of6.jsonl"))
        self.assertEqual(p["episodes"]["tgr_tracker_v4"], os.path.join(p["run_dir"], "tgr_tracker_v4",
                                                                       "episodes_shard5of6.jsonl"))
        s = R.resolve_paths(os.path.join(R.DRYRUN_ROOT, "x"), "B1v4", R.new_run_id("B1v4"), (0, 1))
        self.assertTrue(s["sandbox"])
        self.assertTrue(s["cache_root"].startswith(R.DRYRUN_ROOT + os.sep))
        v3_root = os.path.join(R.OUTPUT_DIR, "eval_v3")
        for bad in (R.OUTPUT_DIR, v3_root, os.path.join(v3_root, "dryrun", "x"), os.path.join(R.V4_ROOT, "B2v4"),
                    "/tmp"):
            with self.assertRaises(R.RunRefused):
                R.resolve_paths(bad, "B2v4", rid, (0, 6))
        self.assertEqual(R.parse_shard("5/6"), (5, 6))
        for bad in ("6/6", "0/7", "x"):
            with self.assertRaises(R.RunRefused):
                R.parse_shard(bad)

    def test_guard_inputs(self):
        files = set(R.guard_input_files())
        for rel in ("guard/run_online_v4.py", "guard/soft_stop_v4.py", "guard/run_online.py",
                    "guard/tgr_tracker_v3.py", "from_shieldagent/runner/repro_online/episode.py",
                    "from_shieldagent/rules/retail/rule_set.json", R.TASKS_REL):
            self.assertIn(rel, files)
        sv4 = os.path.join(PC_DIR, "state_tracker", "v4")
        if os.path.isdir(sv4):                                     # the state_tracker walk covers state_tracker/v4
            for fn in os.listdir(sv4):
                if fn.endswith((".py", ".json")):
                    self.assertIn(f"state_tracker/v4/{fn}", files)
        if os.path.exists(os.path.join(PC_DIR, "scoring", "v4_freeze.py")):
            self.assertIn("scoring/v4_freeze.py", files)

    def test_approval_words(self):
        for bad in (None, "", "yes", "ok", "<the user's words>", "short"):
            self.assertIsNotNone(R.approval_problem(bad), bad)
        self.assertIsNone(R.approval_problem("go with B1 smoke now, approved by me"))


class TestRefusalsBeforeTheRunner(unittest.TestCase):
    """These refusals come before the write guard and before any runner import."""

    def refused(self, argv, text):
        with self.assertRaises(R.RunRefused) as cm:
            R.main(argv)
        self.assertIn(text, str(cm.exception))

    def test_refusals(self):
        b2, b1 = R.new_run_id("B2v4"), R.new_run_id("B1v4")
        self.refused(["run", "--step", "B1v4", "--run-id", b2], "--run-id")
        self.refused(["run", "--step", "B2v4", "--run-id", b2, "--shard", "0/6", "--dev20-enabled"],
                     "DEV20v4 is dropped")
        self.refused(["run", "--step", "B1v4", "--run-id", b1, "--shard", "0/2"], "shard")
        self.refused(["run", "--step", "B2v4", "--run-id", b2, "--shard", "0/7"], "--shard")
        self.refused(["run", "--step", "B2v4", "--run-id", b2, "--shard", "0/6", "--workers", "9"], "--workers")
        self.refused(["run", "--step", "B2v4", "--run-id", b2, "--shard", "0/6", "--task-ids", "retail:4"],
                     "--task-ids")
        self.refused(["run", "--step", "Hv4", "--run-id", R.new_run_id("Hv4"), "--shard", "0/6", "--tries", "1"],
                     "--tries")
        self.refused(["run", "--step", "B1v4", "--run-id", b1, "--shard", "0/1", "--task-ids", CHECK_TASKS],
                     "fixed pair")
        self.refused(["run", "--step", "B2v4", "--run-id", b2, "--shard", "0/6", "--out-root",
                      os.path.join(R.OUTPUT_DIR, "eval_v3")], "--out-root")
        with self.assertRaises(SystemExit):
            R.main(["run", "--step", "B2", "--run-id", "B2_x"])          # v3's step names are not built
        with self.assertRaises(SystemExit):
            R.main(["run", "--step", "B2v4", "--run-id", b2, "--b2v-approved"])

    def test_approved_alias(self):
        seen = {}
        orig = R.cmd_run
        try:
            R.cmd_run = lambda a, argv: seen.setdefault("a", a)
            R.main(["run", "--step", "B1v4", "--run-id", R.new_run_id("B1v4"), "--approved", "the user's words here"])
            self.assertEqual(seen["a"].approval, "the user's words here")
            self.assertFalse(seen["a"].main_chat)
            seen.clear()
            R.main(["run", "--step", "B1v4", "--run-id", R.new_run_id("B1v4"), "--approved", "the user's words here",
                    R.MAIN_CHAT_FLAG])
            self.assertTrue(seen["a"].main_chat)
        finally:
            R.cmd_run = orig

    def test_real_path_needs_the_main_chat_flag(self):
        """audit P7 #1: not a sandbox and not --dry-run -> refused without --i-am-the-main-chat (before the write
        guard, any runner import or any call)."""
        self.assertEqual(R.MAIN_CHAT_FLAG, "--i-am-the-main-chat")
        with open(os.path.join(PC_DIR, "scoring", "v4_offline_eval.py"), encoding="utf-8") as f:
            self.assertIn('MAIN_CHAT_FLAG = "--i-am-the-main-chat"', f.read())       # the same name
        words = ["--approved", "the user's own words for this paid step"]
        for step, shard in (("B1v4", "0/1"), ("B2v4", "0/6"), ("B3v4", "0/6"), ("Hv4", "0/6")):
            self.refused(["run", "--step", step, "--run-id", R.new_run_id(step), "--shard", shard] + words,
                         R.MAIN_CHAT_FLAG)
        # the real backend's approval flag only on the real path with the flag; never in a sandbox or a dry run
        self.assertTrue(R.real_approval_flag(sandbox=False, dry=False, main_chat=True))
        for sb, dry, mc in ((False, False, False), (True, False, True), (False, True, True), (True, True, True),
                            (True, False, False), (False, True, False)):
            self.assertFalse(R.real_approval_flag(sb, dry, mc), (sb, dry, mc))
        self.assertFalse(R.main_chat_given(types.SimpleNamespace()))              # an old namespace: no flag

    def test_tiny_budget_is_split_across_shards(self):
        """audit P7 #4: the shards' tiny-question budgets add up to at most the step's."""
        for step, cfg in R.STEPS.items():
            limit = S.STEP_LIMITS_USD[step]
            for n in cfg["shards"]:
                usd, calls = R.tiny_budget(limit, cfg["max_calls"], n)
                self.assertLessEqual(usd * n, limit + 1e-9, (step, n))
                self.assertLessEqual(calls * n, cfg["max_calls"], (step, n))
                self.assertGreater(calls, 0)
        self.assertEqual(R.tiny_budget(2.0, 2000, 1), (2.0, 2000))


# ================================================================================================ where + conversation id

class _Inner:
    path = None
    writable = True

    def __init__(self):
        self.d = {}

    def get(self, k):
        return self.d.get(k)

    def put(self, k, rec):
        self.d[k] = rec

    def __len__(self):
        return len(self.d)

    def keys(self):
        return list(self.d)


class TestWhereAndConversationId(unittest.TestCase):

    def test_where_per_unit_and_per_check_per_thread(self):
        class Hook:
            def __init__(self):
                self._tl = threading.local()

            @property
            def where(self):
                return getattr(self._tl, "where", None)

            @where.setter
            def where(self, v):
                self._tl.where = v

        hook, store, out = Hook(), R.ConversationStore(_Inner()), {}

        def work(task):
            w = R.unit_where("B2v4_20261023T000000Z_00000000", "B2v4", "retail", task, 0, R.V4_ARM, 1)
            R.set_conversation(w, hook)
            self.assertIsNone(hook.where["check"])
            R.set_check(3, hook)
            store.put(f"k{task}", {"key": f"k{task}", "answer": "yes"})
            out[task] = (dict(hook.where), R.current_conversation())
            R.set_conversation(None, hook)
            self.assertIsNone(R.current_where())

        ts = [threading.Thread(target=work, args=(t,)) for t in (1, 2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        for t in (1, 2):
            where, cid = out[t]
            self.assertEqual({k: where[k] for k in ("run_id", "step", "domain", "task", "trial", "arm", "check")},
                             {"run_id": "B2v4_20261023T000000Z_00000000", "step": "B2v4", "domain": "retail",
                              "task": t, "trial": 0, "arm": R.V4_ARM, "check": 3})
            self.assertEqual(cid, f"B2v4_20261023T000000Z_00000000:{R.V4_ARM}:retail:{t}:0:a1")
            rec = store.get(f"k{t}")
            self.assertEqual(rec["conversation_id"], cid)
            self.assertEqual(rec["where"]["check"], 3)
            self.assertEqual(rec["answer"], "yes")

    def test_ask_log_lines(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "questions", "asks_shard0of1.jsonl")
            log = R.AskLog(path)
            R.set_conversation(R.unit_where("B1v4_x", "B1v4", "airline", 4, 0, R.V4_ARM, 2))
            R.set_check(7)
            log.on_ask("abc", "K1", "fact_x", "b", False)
            log.on_ask("abc", "K1", "fact_x", "b", True)
            R.set_conversation(None)
            with open(path, encoding="utf-8") as f:
                lines = [json.loads(x) for x in f]
            self.assertEqual([x["cached"] for x in lines], [False, True])
            self.assertTrue(all(x["conversation_id"] == f"B1v4_x:{R.V4_ARM}:airline:4:0:a2" for x in lines))
            self.assertTrue(all(x["where"]["check"] == 7 for x in lines))
            self.assertEqual(log.n, {"asked": 1, "cached": 1})

    def test_make_answers_hook_real_questions_v4(self):
        from state_tracker.v3 import questions as Q3
        from state_tracker.v4 import questions_v4 as Q4
        with tempfile.TemporaryDirectory() as d:
            store = os.path.join(d, "questions", "answers_shard0of1.jsonl")
            asks = os.path.join(d, "questions", "asks_shard0of1.jsonl")
            hook, meter = R.make_answers_hook(True, store, "x", 1.0, 10, lambda s: None, asks_path=asks, qmod=Q4)
            self.assertIsInstance(hook, Q4.QuestionsV4)
            self.assertIsInstance(hook.backend, Q4.FakeBackendV4)
            self.assertIsInstance(hook.store, R.ConversationStore)
            self.assertIsInstance(hook.store.inner, Q3.JsonlStore)
            self.assertEqual(hook.store.path, os.path.abspath(store))
            self.assertEqual(hook.ask_log_path, os.path.abspath(asks))           # QuestionsV4's own ask log
            self.assertEqual(hook.doc["model"], "gpt-6-luna")
            # one real ask through the hook: the record and the ask line carry the conversation id and `where`
            qid = Q4.question_ids_v4(hook.doc)[0]
            inputs = Q4.sample_inputs_v4(qid, hook.doc)
            R.set_conversation(R.unit_where("B2v4_x", "B2v4", "retail", 5, 1, R.V4_ARM, 1), hook)
            R.set_check(2, hook)
            hook.ask(qid, inputs)
            hook.ask(qid, inputs)                                                 # read from the store
            R.set_conversation(None, hook)
            with open(store, encoding="utf-8") as f:
                recs = [json.loads(x) for x in f]
            with open(asks, encoding="utf-8") as f:
                lines = [json.loads(x) for x in f]
            self.assertEqual(len(recs), 1)
            self.assertEqual(recs[0]["conversation_id"], f"B2v4_x:{R.V4_ARM}:retail:5:1:a1")
            self.assertEqual(recs[0]["where"]["check"], 2)
            self.assertEqual(recs[0]["where_first"]["check"], 2)
            self.assertEqual([x["cached"] for x in lines], [False, True])
            self.assertTrue(all(x["where"]["task"] == 5 and x["where"]["check"] == 2 for x in lines))
            self.assertEqual(meter.total["calls"], 1)
            # memory store (the dry run); ChainStore (v4 store, then a read-only second store) behind the wrapper
            hook2, _ = R.make_answers_hook(True, None, "x", 1.0, 10, lambda s: None, memory=True, qmod=Q4)
            self.assertIsInstance(hook2.store.inner, Q3.MemoryStore)
            v3mem = Q3.MemoryStore()
            v3mem.put("k3", {"key": "k3", "answer": "yes"})
            cs = R.ConversationStore(Q4.ChainStore(Q3.MemoryStore(), v3mem))
            self.assertEqual(cs.store_of("k3"), "v3")
            self.assertEqual(cs.get("k3")["answer"], "yes")
            cs.put("k4", {"key": "k4"})
            self.assertEqual(cs.store_of("k4"), "v4")
            with self.assertRaises(RuntimeError):                                 # never written to the v3 store
                cs.put("k3", {"key": "k3"})
            # the project answers files are refused before they are opened
            for bad in (Q3.ANSWERS_PATH,) + tuple(S.QUESTIONS_FILES):
                with self.assertRaises(R.RunRefused):
                    R.make_answers_hook(True, bad, "x", 1.0, 10, lambda s: None, qmod=Q4)

    def test_real_backend_needs_the_approval_flag(self):
        from state_tracker.v3 import questions as Q3
        from state_tracker.v4 import questions_v4 as Q4
        with tempfile.TemporaryDirectory() as d:
            store = os.path.join(d, "answers_shard0of1.jsonl")
            with self.assertRaises(Q3.RealModeRefused):                           # the real path without the flag
                R.make_answers_hook(False, store, "approved by the user for this test", 1.0, 10, lambda s: None,
                                    qmod=Q4, approval_flag=False)
            with self.assertRaises(R.RunRefused):                                 # never the flag in a sandbox
                R.make_answers_hook(True, store, "x", 1.0, 10, lambda s: None, qmod=Q4, approval_flag=True)
        self.assertTrue(R._accepts(Q4.RealBackendV4.__init__, "approval_flag"))


# ================================================================================================ freeze

def full_manifest(path, drop=(), wrong=()):
    """A temp manifest in v4_freeze's layout listing every freeze_required_files() path with its sha256 (minus
    `drop`; `wrong` with a bad sha256)."""
    files = []
    for rel in R.freeze_required_files():
        if rel in drop:
            continue
        sha = "0" * 64 if rel in wrong else R.sha256_file(os.path.join(PC_DIR, *rel.split("/")))
        files.append({"path": f"predicate_correctness/{rel}", "role": "method", "sha256": sha, "bytes": 1})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"root": os.path.dirname(PC_DIR), "files": files}, f)
    return path


class TestFreezeCheck(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.man = full_manifest(os.path.join(self.tmp.name, "v4_freeze.json"))

    def tearDown(self):
        self.tmp.cleanup()

    def with_module(self, mod, fn):
        old = sys.modules.get(R.FREEZE_MODULE)
        sys.modules[R.FREEZE_MODULE] = mod
        try:
            return fn()
        finally:
            if old is None:
                sys.modules.pop(R.FREEZE_MODULE, None)
            else:
                sys.modules[R.FREEZE_MODULE] = old

    def test_published_api(self):
        m = types.ModuleType("f")
        m.DEFAULT_MANIFEST = self.man
        m.check = lambda require=True: {"manifest_sha256": "a" * 64, "n_files": 40}
        res = self.with_module(m, lambda: R.freeze_check(require=True))
        self.assertEqual({k: res[k] for k in ("ok", "manifest_sha256", "n_files", "detail")},
                         {"ok": True, "manifest_sha256": "a" * 64, "n_files": 40, "detail": {}})
        self.assertTrue(res["coverage"]["ok"])

        def failing(require=True):
            raise SystemExit("manifest missing")
        m2 = types.ModuleType("f")
        m2.check = failing
        with self.assertRaises(R.RunRefused):
            self.with_module(m2, lambda: R.freeze_check(require=True))
        self.assertFalse(self.with_module(m2, lambda: R.freeze_check(require=False))["ok"])

    def test_file_api(self):
        m = types.ModuleType("f")
        m.DEFAULT_MANIFEST = self.man
        m.check = lambda manifest: {"ok": manifest == self.man, "checked": 12, "changed": [],
                                    "missing": [], "problems": [], "manifest_sha256": "b" * 64}
        res = self.with_module(m, lambda: R.freeze_check(require=True))
        self.assertTrue(res["ok"])
        self.assertEqual(res["n_files"], 12)
        m.check = lambda manifest: {"ok": False, "checked": 12, "changed": [{"path": "guard/x_v4.py"}],
                                    "missing": [], "problems": [], "manifest_sha256": "b" * 64}
        with self.assertRaises(R.RunRefused) as cm:
            self.with_module(m, lambda: R.freeze_check(require=True))
        self.assertIn("x_v4.py", str(cm.exception))

    def test_required_files(self):
        req = set(R.freeze_required_files())
        self.assertTrue(set(R.guard_input_files()) <= req)
        for rel in ("guard/run_online_v4.py", "guard/soft_stop_v4.py", "state_tracker/v4/questions_v4.json",
                    "state_tracker/v4/facts_v4_retail.json", "state_tracker/v4/facts_v4_airline.json",
                    "output/eval_v3/b3_tasks.json", R.TASKS_REL,
                    "scoring/v4_b1_summary.py", "scoring/v4_online_metrics.py", "scoring/v4_diagnosis.py",
                    "scoring/v4_online_interim.py", "scoring/v4_interim.sh"):          # (the last 5: audit P9 #4)
            self.assertIn(rel, req)
        self.assertEqual(set(R.facts_v4_files()), {"state_tracker/v4/facts_v4_retail.json",
                                                   "state_tracker/v4/facts_v4_airline.json"})

    def test_coverage_refuses_a_missing_or_changed_file(self):
        """audit P7 #3: a manifest that passes its own check but leaves out a runner file (or has an old sha256 for
        it) refuses the real run."""
        self.assertTrue(R.freeze_coverage(self.man)["ok"])
        m = types.ModuleType("f")
        m.check = lambda manifest: {"ok": True, "checked": 3, "changed": [], "missing": [], "problems": [],
                                    "manifest_sha256": "c" * 64}
        for rel, kw, key in (("guard/soft_stop_v4.py", {"drop": ("guard/soft_stop_v4.py",)}, "unlisted"),
                             ("guard/run_online_v4.py", {"drop": ("guard/run_online_v4.py",)}, "unlisted"),
                             ("state_tracker/v4/facts_v4_retail.json",
                              {"drop": ("state_tracker/v4/facts_v4_retail.json",)}, "unlisted"),
                             ("state_tracker/v4/questions_v4.json",
                              {"wrong": ("state_tracker/v4/questions_v4.json",)}, "changed"),
                             ("guard/tgr_tracker_v4.py", {"wrong": ("guard/tgr_tracker_v4.py",)}, "changed")):
            bad = full_manifest(os.path.join(self.tmp.name, f"bad_{key}_{os.path.basename(rel)}.json"), **kw)
            cov = R.freeze_coverage(bad)
            self.assertFalse(cov["ok"], rel)
            self.assertEqual(cov[key], [rel])
            m.DEFAULT_MANIFEST = bad
            with self.assertRaises(R.RunRefused) as cm:
                self.with_module(m, lambda: R.freeze_check(require=True))
            self.assertIn(rel, str(cm.exception))
            self.assertFalse(self.with_module(m, lambda: R.freeze_check(require=False))["ok"])
        self.assertFalse(R.freeze_coverage(os.path.join(self.tmp.name, "nope.json"))["ok"])
        self.assertFalse(R.freeze_coverage(None)["ok"])

    def test_real_freeze_script_without_manifest(self):
        if not os.path.exists(os.path.join(PC_DIR, "scoring", "v4_freeze.py")):
            self.skipTest("scoring/v4_freeze.py not written yet")
        res = R.freeze_check(require=False)
        if not os.path.exists(os.path.join(R.V4_ROOT, "v4_freeze.json")):
            self.assertFalse(res["ok"])
            with self.assertRaises(R.RunRefused):
                R.freeze_check(require=True)


# ================================================================================================ the soft stop

def line(arm, task=0, trial=0, cost=0.01, error=None, reward=1.0, env="retail"):
    return {"env": env, "task_index": task, "trial": trial, "guard": arm, "error": error, "reward": reward,
            "cost": {"agent": cost, "user": 0.0, "guard": 0.0}}


def write_lines(path, recs, mode="w"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode, encoding="utf-8") as f:
        f.write("".join(json.dumps(r) + "\n" for r in recs))


class TestResumeAmendment(unittest.TestCase):
    """The resume after the limit change (user decision "finish H"): only RESUME_AMENDABLE files may differ."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.manifest = os.path.join(self.tmp.name, "v4_freeze.json")

    def tearDown(self):
        self.tmp.cleanup()

    def _manifest(self, path, files):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"files": [{"path": p, "sha256": h} for p, h in sorted(files.items())]}, f)
        return R.sha256_file(path)

    def _case(self, changed):
        base = {"predicate_correctness/guard/soft_stop_v4.py": "a", "predicate_correctness/guard/tgr_tracker_v4.py": "b",
                "docs/planning/tracker_v4/preregistration_v4.md": "c"}
        old_sha = self._manifest(self.manifest + ".superseded_20261024T000000Z", base)
        new_sha = self._manifest(self.manifest, dict(base, **{p: "z" for p in changed}))
        return {"guard_inputs_sha256": {"guard/soft_stop_v4.py": "1"}, "v4_manifest_sha256": old_sha}, new_sha

    def test_unchanged_is_none(self):
        have = {"guard_inputs_sha256": {"x": "1"}, "v4_manifest_sha256": "m"}
        self.assertIsNone(R.resume_amendment(have, {"guard_inputs_sha256": {"x": "1"}, "v4_manifest_sha256": "m"},
                                             self.manifest))

    def test_limit_change_is_allowed_and_recorded(self):
        have, new_sha = self._case(["predicate_correctness/guard/soft_stop_v4.py",
                                    "docs/planning/tracker_v4/preregistration_v4.md"])
        rec = R.resume_amendment(have, {"guard_inputs_sha256": {"guard/soft_stop_v4.py": "2"},
                                        "v4_manifest_sha256": new_sha, "approval_quote": "q"}, self.manifest)
        self.assertEqual(rec["guard_inputs_changed"], ["guard/soft_stop_v4.py"])
        self.assertEqual(rec["manifest_files_changed"], ["docs/planning/tracker_v4/preregistration_v4.md",
                                                          "predicate_correctness/guard/soft_stop_v4.py"])
        self.assertEqual(rec["approval_quote"], "q")

    def test_guard_logic_change_is_refused(self):
        have, new_sha = self._case(["predicate_correctness/guard/tgr_tracker_v4.py"])
        with self.assertRaises(R.RunRefused):
            R.resume_amendment(have, {"guard_inputs_sha256": {"guard/soft_stop_v4.py": "1"},
                                      "v4_manifest_sha256": new_sha}, self.manifest)
        with self.assertRaises(R.RunRefused):                     # a guard input outside the list
            R.resume_amendment({"guard_inputs_sha256": {"guard/tgr_tracker_v4.py": "1"}, "v4_manifest_sha256": "m"},
                               {"guard_inputs_sha256": {"guard/tgr_tracker_v4.py": "2"}, "v4_manifest_sha256": "m"},
                               self.manifest)

    def test_plan_keys(self):
        path = os.path.join(self.tmp.name, "run", "run.json")
        extra = {"guard_inputs_sha256": {"x": "1"}, "v4_manifest_sha256": "m"}
        R.ensure_run_json(path, {"step": "Hv4", "approval_quote": "a", "hard_limit_usd": 8.0}, extra)
        with self.assertRaises(R.RunRefused):          # new words and limit, but no re-freeze: refused
            R.ensure_run_json(path, {"step": "Hv4", "approval_quote": "b", "hard_limit_usd": 15.0}, extra)
        with self.assertRaises(R.RunRefused):          # another plan key: always refused
            R.ensure_run_json(path, {"step": "B2v4", "approval_quote": "a", "hard_limit_usd": 8.0}, extra)
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(path), R.AMENDMENTS_FILENAME)))

    def test_no_superseded_copy_is_refused(self):
        with self.assertRaises(R.RunRefused):
            R.resume_amendment({"guard_inputs_sha256": {}, "v4_manifest_sha256": "old"},
                               {"guard_inputs_sha256": {}, "v4_manifest_sha256": "new"}, self.manifest)


class TestSoftStop(unittest.TestCase):

    def test_step_start_and_reserve(self):
        self.assertTrue(S.step_start_ok(40.0, 0.0, 40.0, 80.0)[0])          # equal to the cap: allowed (any cap)
        self.assertFalse(S.step_start_ok(40.01, 0.0, 40.0, 80.0)[0])
        self.assertFalse(S.step_start_ok(0.0, 20.0, 20.0, 80.0)[0])          # its limit is used up
        ok, why = S.group_start_ok(38.0, 40.0, running_units=10, units_left_open=5, p90=0.061, new_units=5)
        self.assertTrue(ok, why)                                               # 38 + 20 x 0.061 = 39.22 <= 40
        self.assertFalse(S.group_start_ok(39.0, 40.0, 10, 5, 0.061, 5)[0])     # 39 + 1.22 > 40
        self.assertFalse(S.group_start_ok(1.0, 40.0, 0, 0, 0.061, 5, total_spent=79.9, cap=80.0)[0])

    def test_cost_rules(self):
        lines = {"/r/tgr_tracker_v4/episodes_shard0of1.jsonl": [line("tgr_tracker_v4", t, cost=0.031)
                                                               for t in range(50)]}
        got = S.stop_reasons(lines, thresholds=S.arm_thresholds("B2v4"))
        self.assertEqual([x["rule"] for x in got], ["arm_mean_cost"])              # 0.031 > 0.030
        self.assertEqual(S.stop_reasons(lines, thresholds=S.arm_thresholds("B3v4")), [])   # 0.031 < 0.063
        few = {"/r/x/episodes.jsonl": [line("tgr_tracker_v4", t, cost=0.031) for t in range(49)]}
        self.assertEqual(S.stop_reasons(few, thresholds=S.arm_thresholds("B2v4")), [])
        other = {"/r/x/episodes.jsonl": [line("someone", t, cost=0.045) for t in range(50)]}
        self.assertEqual(len(S.stop_reasons(other, thresholds=S.arm_thresholds("B2v4"),
                                            unknown_arm=S.unknown_arm_threshold("B2v4"))), 1)
        self.assertEqual(S.stop_reasons(other, thresholds=S.arm_thresholds("B3v4"),
                                        unknown_arm=S.unknown_arm_threshold("B3v4")), [])
        big = {"/r/x/episodes.jsonl": [line("none", cost=0.26)]}
        self.assertEqual([x["rule"] for x in S.stop_reasons(big)], ["one_conversation"])
        errs = {"/r/x/episodes.jsonl": [line("none", t, error="APIError") for t in range(5)]}
        self.assertIn("errors_in_a_row", [x["rule"] for x in S.stop_reasons(errs)])

    def test_halfway(self):
        five = ("none", "direct", "direct_facts_v4", "tgr_frozen", "tgr_tracker_v4")   # a group with frozen TGR in it

        def groups(n, v4_reward):
            out = []
            for t in range(n):
                for a in five:
                    out.append(line(a, t, reward=(v4_reward(t) if a == "tgr_tracker_v4" else 1.0)))
            return {"/r/all/episodes.jsonl": out}
        # 20 groups, v4 loses 3 of 20 -> -0.15: a tie fires
        h = S.halfway_check(groups(20, lambda t: 0.0 if t < 3 else 1.0), 100, arms=five)
        self.assertTrue(h["reached"])
        self.assertAlmostEqual(h["diff"], -0.15)
        self.assertTrue(h["stop"])
        h = S.halfway_check(groups(20, lambda t: 0.0 if t < 2 else 1.0), 100, arms=five)
        self.assertFalse(h["stop"])
        h = S.halfway_check(groups(19, lambda t: 0.0), 100, arms=five)          # 95 conversations < the mark
        self.assertFalse(h["reached"])
        self.assertFalse(h["stop"])
        g = groups(20, lambda t: 0.0)                                           # an incomplete group is left out
        g["/r/all/episodes.jsonl"] = [r for r in g["/r/all/episodes.jsonl"]
                                      if not (r["task_index"] < 18 and r["guard"] == "none")]
        self.assertEqual(S.complete_groups(g, five).keys(), {("retail", 18, 0), ("retail", 19, 0)})
        err = groups(1, lambda t: 1.0)
        err["/r/all/episodes.jsonl"][0]["error"] = "x"                          # an error line does not count
        self.assertEqual(S.complete_groups(err, five), {})
        # P10 default: the v4 arms' groups; frozen TGR is not live, so the mark is reported, the decision is the
        # interim script's (v4 vs v3's frozen baseline)
        h = S.halfway_check(groups(20, lambda t: 0.0), 40)
        self.assertTrue(h["reached"])
        self.assertIsNone(h["diff"])
        self.assertFalse(h["stop"])
        self.assertIn("v4_online_interim", h["detail"])

    def test_soft_stop_object_halfway_default_reports_only(self):
        with tempfile.TemporaryDirectory() as d:
            step = os.path.join(d, "B3v4")
            recs = [line(a, t, reward=(0.0 if a == "tgr_tracker_v4" else 1.0), cost=0.0001)
                    for t in range(32) for a in S.GROUP_ARMS]
            write_lines(os.path.join(step, "run", "all", "episodes_shard0of1.jsonl"), recs)
            ss = S.SoftStopV4("B3v4", step_dir=step, root=d, questions=())
            self.assertTrue(ss.can_start_step()[0])
            ok, why = ss.can_start_group(0, 0)
            self.assertTrue(ok, why)                                            # reported, not applied
            h = ss.report()["halfway"]
            self.assertTrue(h["reached"])                                       # 32 groups x 2 = 64 = the mark
            self.assertFalse(h["stop"])                                         # no frozen TGR live: not decided here
            ss2 = S.SoftStopV4("B3v4", step_dir=step, root=d, questions=(), halfway_stop=True)
            ss2.can_start_step()
            ok, why = ss2.can_start_group(0, 0)
            self.assertTrue(ok, why)
            self.assertEqual(ss2.run_json()["arm_mean_stop_usd"], S.arm_thresholds("B3v4"))
            self.assertEqual(S.SoftStopV4("Hv4", root=d, questions=()).halfway_mark, None)

    def test_limits_in_a_folder(self):
        with tempfile.TemporaryDirectory() as d:
            step = os.path.join(d, "B1v4")
            run = os.path.join(step, "B1v4_20261023T000000Z_00000000")
            write_lines(os.path.join(run, "none", "episodes_shard0of1.jsonl"), [line("none", cost=0.5)])
            ss = S.SoftStopV4("B1v4", step_dir=step, root=d, questions=())
            ok, _ = ss.can_start_step()
            self.assertTrue(ok)
            self.assertTrue(ss.can_start_unit()[0])
            write_lines(os.path.join(run, "none", "episodes_shard0of1.jsonl"), [line("none", 1, cost=0.5)], "a")
            ok, why = ss.can_start_unit()                                       # $1.00 >= the $1 limit
            self.assertFalse(ok)
            self.assertIn("hard limit", why)
            self.assertFalse(ss.can_start_group(0, 0)[0])                       # sticky
            # the cap: another step's spend under the same root
            write_lines(os.path.join(d, "B2v4", "r", "none", "episodes.jsonl"), [line("none", cost=29.0)])
            ss2 = S.SoftStopV4("B3v4", root=d, questions=())
            ok, why = ss2.can_start_step()                                       # 30 + 6 > 30
            self.assertFalse(ok)
            self.assertIn("cap", why)
            # dry-run lines never count
            write_lines(os.path.join(d, "dryrun", "x", "B2v4", "r", "none", "episodes.jsonl"),
                        [line("none", cost=500.0)])
            self.assertAlmostEqual(S.v4_spend(d, questions=())["total_usd"], 30.0)

    def test_questions_files_count(self):
        with tempfile.TemporaryDirectory() as d:
            q = os.path.join(d, "questions_answers_v4.jsonl")
            write_lines(q, [{"key": "a", "cost_usd": 0.01, "spent_usd": 0.01},
                            {"key": "b", "cost_usd": 0.01, "spent_usd": 0.03}])      # a failed attempt in between
            self.assertAlmostEqual(S.v4_spend(d, questions=(q,))["total_usd"], 0.03)
        self.assertEqual([os.path.basename(p) for p in S.QUESTIONS_FILES], ["questions_answers_v4.jsonl",
                                                                             "answers.jsonl"])


class TestBackupsByCopy(unittest.TestCase):
    """Resume: the shard files are COPIED (cp) to *.jsonl.before_resume; a moved (mv) backup refuses the run."""

    def test_cp_counts_once_mv_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            live = os.path.join(d, "B2v4", "r", "none", "episodes_shard0of6.jsonl")
            write_lines(live, [line("none", t, cost=0.5) for t in range(4)])
            shutil.copyfile(live, live + ".before_resume")                      # cp
            write_lines(live, [line("none", 9, cost=0.5)], "a")                 # the resumed run appends
            self.assertEqual(S.backup_problems(os.path.join(d, "B2v4")), [])
            self.assertAlmostEqual(S.step_spend(os.path.join(d, "B2v4"))["total_usd"], 2.5)
            self.assertAlmostEqual(S.v4_spend(d, questions=())["total_usd"], 2.5)
            os.replace(live, live + ".moved")                                   # now as if mv: no live file
            write_lines(live, [line("none", 9, cost=0.5)])                      # a new short live file
            probs = S.backup_problems(os.path.join(d, "B2v4"))
            self.assertEqual(len(probs), 1)
            self.assertAlmostEqual(S.step_spend(os.path.join(d, "B2v4"))["total_usd"], 2.0)   # max(backup, live)
            ss = S.SoftStopV4("B2v4", step_dir=os.path.join(d, "B2v4"), root=d, questions=())
            ok, why = ss.can_start_step()
            self.assertFalse(ok)
            self.assertIn("copy, never move", why)


# ================================================================================================ records

class TestRecords(unittest.TestCase):

    def test_tracker_part_and_state_errors(self):
        g = {"v3": {"state_errors": [{"kind": "replay_mismatch"}], "fact_errors": []},
             "v4": {"version": "v4", "escape": None}}
        self.assertEqual(len(R.tracker_part(g)["state_errors"]), 1)
        rec = {"guard": R.V4_ARM, "attempts": [{"guard": g}, {"guard": {"v3": {"fact_errors": [
            {"error": "KeyError", "detail": "x"}, {"error": "RealCallFailed", "detail": "RealCallFailed: K1"}]}}},
            {"guard": None}]}
        self.assertEqual(R.v4_state_error_checks(rec), 2)
        meter = R.TinyMeter(types.SimpleNamespace(answer=lambda **k: {}, name="fake"))
        meter.start_episode()
        meter.start_check()
        with self.assertRaises(R.TinyQuestionCallFailed):
            R.finish_v4_check({"usage": {}, "v3": {"fact_errors": [{"error": "RealCallFailed", "detail": "y"}]}},
                              meter)
        out = R.finish_v4_check({"usage": {}, "v3": {"fact_errors": []}, "v4": {}}, meter)
        self.assertEqual(out["tiny_questions"], {"backend_calls": 0, "cost_usd": 0.0})

    def test_b1_check(self):
        def lines(v4_state=False, df_failure=None, cost=0.01):
            out = {}
            for a in B1_ARMS:
                out[a] = []
                for d in ("retail", "airline"):
                    g = {}
                    if a == "direct_facts_v4":
                        g = {"direct_facts": {"facts_failure": df_failure, "state_error": None}}
                    if a == R.V4_ARM:
                        g = {"v3": {"state_errors": [{"kind": "x"}] if v4_state else [], "fact_errors": []}}
                    out[a].append({"env": d, "task_index": 4, "trial": 0, "guard": a, "error": None,
                                   "cost": {"agent": cost}, "attempts": [{"guard": g}]})
            return out
        with tempfile.TemporaryDirectory() as d:
            for i, (kw, want, failed) in enumerate([({}, True, None), ({"v4_state": True}, False, "v4_state_errors"),
                                                    ({"df_failure": "x"}, False, "direct_facts_facts_failures"),
                                                    ({"cost": 0.033}, False, "mean_cost"),
                                                    ({"cost": 0.032}, True, None)]):
                run = os.path.join(d, f"r{i}")
                for a, recs in lines(**kw).items():
                    write_lines(os.path.join(run, a, "episodes_shard0of1.jsonl"), recs)
                res = R.b1_check(run)
                self.assertEqual(res["mean_cost_limit_usd"], 0.032)        # preregistration_v4.md section 13
                self.assertEqual(res["pass"], want, (kw, res))
                self.assertEqual(res["conversations"], 4)
                if failed:
                    self.assertFalse(res["checks"][failed])


class TestGroupPool(unittest.TestCase):

    def units(self, n):
        return [("retail", t, 0, a) for t in range(n) for a in FIVE_ARMS]

    def test_stop_lets_open_groups_finish(self):
        units = self.units(4)
        ran, asked, lock = [], [], threading.Lock()

        def run_unit(u, attempt):
            time.sleep(0.005)
            with lock:
                ran.append(u)
            return {"error": None}

        def can_start(n, running, left):
            asked.append(n)
            return (len(asked) <= 1, "stop file")
        st = R.GroupPool(units, run_unit, can_start, workers=3).run()
        self.assertEqual(sorted(ran), sorted(units[:5]))
        self.assertEqual(st["not_started"], 15)

    def test_rerun_once_then_drop(self):
        units = self.units(2)
        bad = units[0]
        seen, dropped = {}, []

        def run_unit(u, attempt):
            seen.setdefault(u, []).append(attempt)
            return {"error": "boom" if u == bad else None}
        st = R.GroupPool(units, run_unit, lambda *a: (True, "ok"), workers=1,
                         on_drop=lambda g, r: dropped.append(g)).run()
        self.assertEqual(seen[bad], [1, 2])
        self.assertEqual(dropped, [("retail", 0, 0)])
        self.assertEqual(st["skipped_dropped"], 4)


class TestGroupPoolShardRace(unittest.TestCase):
    """audit P7 #4: a new group's check and the live-file write after it happen under the step's flock; the unit
    check gets the units in flight."""

    def units(self, n):
        return [("retail", t, 0, a) for t in range(n) for a in FIVE_ARMS]

    def test_group_lock_around_can_start_and_live(self):
        import contextlib
        held, seen = {"n": 0}, []

        @contextlib.contextmanager
        def gl():
            held["n"] += 1
            try:
                yield
            finally:
                held["n"] -= 1

        def can_start(n, running, left):
            seen.append(("can_start", held["n"]))
            return True, "ok"
        R.GroupPool(self.units(3), lambda u, at: {"error": None}, can_start, workers=1,
                    on_live=lambda run, left: seen.append(("live", held["n"])), group_lock=gl).run()
        starts = [i for i, s in enumerate(seen) if s[0] == "can_start"]
        self.assertEqual(len(starts), 3)
        for i in starts:
            self.assertEqual(seen[i], ("can_start", 1))
            self.assertEqual(seen[i + 1], ("live", 1))       # the live file is written before the lock is let go
        self.assertEqual(held["n"], 0)

    def test_step_flock_excludes_threads_and_processes(self):
        with tempfile.TemporaryDirectory() as d:
            path = R.step_lock_path(os.path.join(d, "B2v4"))
            order, ev = [], threading.Event()

            def holder():
                with R.step_flock(path):
                    ev.set()
                    time.sleep(0.3)
                    order.append("a_out")

            t = threading.Thread(target=holder)
            t.start()
            ev.wait(5)
            with R.step_flock(path):
                order.append("b_in")
            t.join()
            self.assertEqual(order, ["a_out", "b_in"])
            code = ("import fcntl, os, sys; fd = os.open(sys.argv[1], os.O_RDWR); "
                    "fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)")
            with R.step_flock(path):                          # another process cannot take it meanwhile
                r = subprocess.run([sys.executable, "-B", "-c", code, path], capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            r = subprocess.run([sys.executable, "-B", "-c", code, path], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_unit_check_gets_the_running_units(self):
        got = []

        def can_start_unit(running=0):
            got.append(running)
            return True, "ok"
        R.GroupPool(self.units(2), lambda u, at: (time.sleep(0.002), {"error": None})[1], lambda *a: (True, "ok"),
                    workers=3, can_start_unit=can_start_unit).run()
        self.assertEqual(len(got), 8)                                      # 2 groups x 4 units after the first
        self.assertTrue(all(1 <= x <= 3 for x in got), got)                # this one included, at most the workers
        old = []                                                           # an old-style check (no argument) still works
        R.GroupPool(self.units(1), lambda u, at: {"error": None}, lambda *a: (True, "ok"), workers=1,
                    can_start_unit=lambda: (old.append(1), (True, "ok"))[1]).run()
        self.assertEqual(len(old), 4)

    def test_soft_stop_unit_check_counts_money_in_flight(self):
        with tempfile.TemporaryDirectory() as d:
            step = os.path.join(d, "B1v4")
            write_lines(os.path.join(step, "r", "none", "episodes_shard0of1.jsonl"), [line("none", cost=1.8)])
            ss = S.SoftStopV4("B1v4", step_dir=step, root=d, questions=(), hard_limit_usd=2.0)
            ss.can_start_step()
            self.assertTrue(ss.can_start_unit()[0])                          # spent only: $1.80 < $2
            self.assertTrue(ss.can_start_unit(running_units=1)[0])           # 1.80 + 1 x 0.061 <= 2 (0.2 >= 0.122)
            self.assertTrue(ss.can_start_unit(running_units=3)[0])           # 1.80 + 3 x 0.061 = 1.983
            ok, why = ss.can_start_unit(running_units=4)                     # 1.80 + 4 x 0.061 > 2
            self.assertFalse(ok)
            self.assertIn("running units", why)
            ss2 = S.SoftStopV4("B2v4", root=d, questions=(), cap_usd=2.0)    # the cap with money in flight
            ss2.can_start_step()
            self.assertTrue(ss2.can_start_unit(running_units=3)[0])          # 1.80 + 3 x 0.061 <= 2
            self.assertFalse(ss2.can_start_unit(running_units=4)[0])

    def test_near_the_limit_a_unit_in_flight_counts_025(self):
        """audit P9 #3: when what is left is under 2 x p90 x shards, each unit in flight is reserved at $0.25."""
        self.assertEqual(S.unit_reserve_usd(1.0, 0.061, 1), 0.061)
        self.assertEqual(S.unit_reserve_usd(0.121, 0.061, 1), 0.25)        # 0.121 < 0.122
        self.assertEqual(S.unit_reserve_usd(0.7, 0.061, 6), 0.25)          # 0.7 < 2 x 0.061 x 6 = 0.732
        self.assertEqual(S.unit_reserve_usd(0.74, 0.061, 6), 0.061)
        self.assertEqual(S.unit_reserve_usd(0.1, 0.4, 1), 0.4)             # never below p90
        with tempfile.TemporaryDirectory() as d:
            step = os.path.join(d, "B1v4")
            write_lines(os.path.join(step, "r", "none", "episodes_shard0of1.jsonl"), [line("none", cost=1.9)])
            ss = S.SoftStopV4("B1v4", step_dir=step, root=d, questions=(), hard_limit_usd=2.0)
            ss.can_start_step()
            self.assertTrue(ss.can_start_unit()[0])                          # no unit in flight: spend only
            ok, why = ss.can_start_unit(running_units=1)                     # 0.1 left < 0.122: 1.90 + 0.25 > 2
            self.assertFalse(ok)
            self.assertIn("near the limit", why)
            # B2v4 with 6 shards: $39.30 spent, 0.70 left < 0.732 -> 2 units x $0.25 = 0.50 fits, 3 do not
            step2 = os.path.join(d, "B2v4")
            write_lines(os.path.join(step2, "r", "none", "episodes_shard0of6.jsonl"), [line("none", cost=39.3)])
            ss6 = S.SoftStopV4("B2v4", step_dir=step2, root=d, questions=(), n_shards=6, hard_limit_usd=40.0,
                               cap_usd=80.0)
            ss6.can_start_step()
            self.assertTrue(ss6.can_start_unit(running_units=2)[0])
            self.assertFalse(ss6.can_start_unit(running_units=3)[0])
            ss1 = S.SoftStopV4("B2v4", step_dir=step2, root=d, questions=(), n_shards=1, hard_limit_usd=40.0,
                               cap_usd=80.0)
            ss1.can_start_step()                                             # 1 shard: 0.70 >= 0.122, p90 rule
            self.assertTrue(ss1.can_start_unit(running_units=11)[0])         # 39.3 + 11 x 0.061 = 39.971
            self.assertEqual(ss6.run_json()["n_shards"], 6)


def fake_b1_run(out_root, manifest_sha=None, sandbox=True, cost=0.01, rid=None, error=None):
    """A made-up B1v4 run folder (10 lines, retail:4 + airline:4 x 5 arms, try 0) as the runner writes it."""
    rid = rid or R.new_run_id("B1v4")
    rd = os.path.join(out_root, "B1v4", rid)
    for a in B1_ARMS:
        recs = []
        for d in ("retail", "airline"):
            g = {}
            if a == "direct_facts_v4":
                g = {"direct_facts": {"facts_failure": None, "state_error": None}}
            if a == R.V4_ARM:
                g = {"v3": {"state_errors": [], "fact_errors": []}}
            recs.append({"env": d, "task_index": 4, "trial": 0, "guard": a, "arm": a, "error": error, "reward": 1.0,
                         "cost": {"agent": cost, "user": 0.0, "guard": 0.0}, "attempts": [{"guard": g}],
                         "step": "B1v4", "run_id": rid, "task_split": "test", "task_group": "val", "unit_attempt": 1,
                         "conversation_id": f"{rid}:{a}:{d}:4:0:a1"})
        write_lines(os.path.join(rd, a, "episodes_shard0of1.jsonl"), recs)
    with open(os.path.join(rd, "run.json"), "w", encoding="utf-8") as f:
        json.dump({"ident": {"step": "B1v4", "run_id": rid}, "v4_manifest_sha256": manifest_sha, "sandbox": sandbox}, f)
    return rd


class TestB1Gate(unittest.TestCase):
    """audit P7 #2: B2v4 / B3v4 / Hv4 start only after a passing B1v4 (b1_check and section 13) with the same
    v4 manifest sha256."""

    def with_summary(self, passing, fn):
        m = types.ModuleType("b1s")
        m.summarize = lambda rd: {"check": {"pass": passing(rd), "checks": {"safety": passing(rd)},
                                            "mean_cost_usd": 0.01, "safety_bad": 0}}
        old = sys.modules.get(R.B1_SUMMARY_MODULE)
        sys.modules[R.B1_SUMMARY_MODULE] = m
        try:
            return fn()
        finally:
            if old is None:
                sys.modules.pop(R.B1_SUMMARY_MODULE, None)
            else:
                sys.modules[R.B1_SUMMARY_MODULE] = old

    def test_gate_rules(self):
        self.assertEqual(R.B1_GATED_STEPS, ("B2v4", "B3v4", "Hv4"))
        sha = "d" * 64
        with tempfile.TemporaryDirectory() as d:
            yes = lambda rd: True                                            # noqa: E731
            self.assertFalse(self.with_summary(yes, lambda: R.b1_gate(d, sha, real=False))["ok"])   # no B1 folder
            bad = fake_b1_run(d, sha, cost=0.033)                            # mean cost > $0.032
            g = self.with_summary(yes, lambda: R.b1_gate(d, sha, real=False))
            self.assertFalse(g["ok"])
            self.assertTrue(any("b1_check" in w for t in g["tried"] for w in t["why"]))
            shutil.rmtree(bad)
            fake_b1_run(d, "e" * 64)                                         # another manifest
            self.assertFalse(self.with_summary(yes, lambda: R.b1_gate(d, sha, real=False))["ok"])
            rd = fake_b1_run(d, sha)
            g = self.with_summary(yes, lambda: R.b1_gate(d, sha, real=False))
            self.assertTrue(g["ok"], g)
            self.assertEqual(g["b1_run_dir"], rd)
            g = self.with_summary(lambda r: False, lambda: R.b1_gate(d, sha, real=False))   # section 13 fails
            self.assertFalse(g["ok"])
            self.assertTrue(any("section 13" in w for t in g["tried"] for w in t["why"]))
            self.assertFalse(self.with_summary(yes, lambda: R.b1_gate(d, sha, real=True))["ok"])    # a sandbox B1
            self.assertFalse(self.with_summary(yes, lambda: R.b1_gate(d, None, real=True))["ok"])   # no freeze
            real_rd = fake_b1_run(d, sha, sandbox=False)
            g = self.with_summary(yes, lambda: R.b1_gate(d, sha, real=True))
            self.assertTrue(g["ok"], g)
            self.assertEqual(g["b1_run_dir"], real_rd)
            with open(os.path.join(real_rd, "STOP"), "w") as f:
                f.write("x")
            self.assertFalse(self.with_summary(yes, lambda: R.b1_gate(d, sha, real=True))["ok"])
            errs = os.path.join(d, "errs")                                   # two error lines: b1_check fails
            fake_b1_run(errs, sha, error="APIError")
            self.assertFalse(self.with_summary(yes, lambda: R.b1_gate(errs, sha, real=False))["ok"])

    def test_real_section_13_check_on_a_sandbox_b1_folder(self):
        """The real scoring/v4_b1_summary.py check on a made-up sandbox B1v4 folder (the sandbox's only way past the
        gate; a real run looks under output/eval_v4/B1v4/ only and needs run.json sandbox false)."""
        from scoring import v4_b1_summary as B1S
        if getattr(B1S, "B1_CONVERSATIONS", None) != R.B1_CONVERSATIONS:
            self.skipTest(f"scoring/v4_b1_summary.py still expects {getattr(B1S, 'B1_CONVERSATIONS', None)} B1 "
                          f"conversations (5 arms); the P10 arm plan has {R.B1_CONVERSATIONS}: its owner updates it")
        out = _unique("p7_gate_fast")
        try:
            rd = fake_b1_run(out, None)
            sc = R.b1_summary_check(rd)
            self.assertTrue(sc["pass"], sc)
            g = R.b1_gate(out, None, real=False)
            self.assertTrue(g["ok"], g)
            self.assertFalse(R.b1_gate(out, None, real=True)["ok"])
            hi = fake_b1_run(os.path.join(out, "hi"), None, cost=0.04)
            self.assertFalse(R.b1_summary_check(hi)["pass"])
        finally:
            if os.path.exists(out):
                shutil.rmtree(out)


def dead_pid() -> int:
    """The pid of a process that has ended."""
    p = subprocess.Popen([sys.executable, "-B", "-c", "pass"])
    p.wait()
    return p.pid


class TestCapWithLiveSteps(unittest.TestCase):
    """audit P7 #5: a step start counts the unspent limits of the other live steps."""

    def test_step_start_counts_other_live_steps(self):
        # the cap logic with the limits this test was written for (B2v4 $10, B3v4 $6, Hv4 $8; the real ones changed
        # on 2026-10-24, user decision "finish H")
        from unittest import mock
        with mock.patch.dict(S.STEP_LIMITS_USD, {"B2v4": 10.0, "B3v4": 6.0, "Hv4": 8.0}):
            self._other_live_steps()

    def _other_live_steps(self):
        self.assertTrue(S.step_start_ok(40.0, 0.0, 15.0, 80.0, others_left=25.0)[0])     # 40 + 15 + 25 = 80
        ok, why = S.step_start_ok(40.0, 0.0, 15.0, 80.0, others_left=25.01)
        self.assertFalse(ok)
        self.assertIn("other live steps", why)
        with tempfile.TemporaryDirectory() as d:
            write_lines(os.path.join(d, "B2v4", "r", "none", "episodes_shard0of6.jsonl"), [line("none", cost=3.0)])
            ss = S.SoftStopV4("Hv4", root=d, questions=(), cap_usd=20.0)
            self.assertTrue(ss.can_start_step()[0])                          # 3 + 8 <= 20: B2v4 is not live
            locks = os.path.join(d, "B2v4", "locks")
            os.makedirs(locks)
            with open(os.path.join(locks, "shard0of6.lock"), "w") as f:
                f.write(f"{dead_pid()} 20261024T000000Z\n")
            self.assertEqual(S.live_steps(d), {})                            # its process is gone
            self.assertTrue(S.SoftStopV4("Hv4", root=d, questions=(), cap_usd=20.0).can_start_step()[0])
            with open(os.path.join(locks, "shard1of6.lock"), "w") as f:
                f.write(f"{os.getpid()} 20261024T000000Z\n")                 # a live runner of B2v4
            self.assertEqual(S.live_steps(d), {"B2v4": [os.getpid()]})
            self.assertEqual(S.live_steps(d, exclude=("B2v4",)), {})
            ss = S.SoftStopV4("Hv4", root=d, questions=(), cap_usd=20.0)
            ok, why = ss.can_start_step()                                    # 3 + 8 + (10 - 3) = 18 <= 20
            self.assertTrue(ok, why)
            os.makedirs(os.path.join(d, "B3v4", "locks"))
            with open(os.path.join(d, "B3v4", "locks", "shard0of1.lock"), "w") as f:
                f.write(f"{os.getpid()} x\n")
            ss = S.SoftStopV4("Hv4", root=d, questions=(), cap_usd=20.0)
            ok, why = ss.can_start_step()                                    # 18 + 6 = 24 > 20
            self.assertFalse(ok)
            self.assertIn("other live steps", why)
            self.assertEqual(sorted(ss.started["other_live_steps"]["steps"]), ["B2v4", "B3v4"])
            ok, _ = S.SoftStopV4("Hv4", root=d, questions=()).can_start_step()   # the real cap $30: 24 <= 30
            self.assertTrue(ok)


class TestKilledShardSpend(unittest.TestCase):
    """audit P7 #6: a unit started by a process that is gone (no end line) counts ORPHAN_UNIT_USD + its tiny
    questions."""

    def test_orphans_count(self):
        dead = dead_pid()
        with tempfile.TemporaryDirectory() as d:
            run = os.path.join(d, "B2v4", "B2v4_20261024T000000Z_00000000")
            led = os.path.join(run, "ledger", "units_shard0of6.jsonl")

            def ev(event, cid, pid):
                return {"event": event, "conversation_id": cid, "pid": pid, "unit": [], "time": "x"}
            write_lines(led, [ev("start", "c1", dead), ev("end", "c1", dead),          # finished: nothing extra
                              ev("start", "c2", dead),                                  # killed: an orphan
                              ev("start", "c3", os.getpid()),                           # in flight, alive
                              ev("start", "c2", 4242424), ev("end", "c2", 4242424)])    # its resume finished
            write_lines(os.path.join(run, "questions", "answers_shard0of6.jsonl"),
                        [{"key": "k", "cost_usd": 0.01, "conversation_id": "c2"},
                         {"key": "k2", "cost_usd": 0.5, "conversation_id": "c1"}])
            write_lines(os.path.join(run, "none", "episodes_shard0of6.jsonl"), [line("none", cost=1.0)])
            o = S.orphan_spend(d)
            self.assertEqual(o["units"], 1)
            self.assertAlmostEqual(o["usd"], S.ORPHAN_UNIT_USD + 0.01)
            self.assertAlmostEqual(S.step_spend(os.path.join(d, "B2v4"))["total_usd"], 1.0 + 0.26)
            self.assertAlmostEqual(S.v4_spend(d, questions=())["total_usd"], 1.0 + 0.26)
            dry = os.path.join(d, "dryrun", "x", "B2v4", "r", "ledger", "units_shard0of1.jsonl")
            write_lines(dry, [ev("start", "c9", dead)])
            self.assertAlmostEqual(S.v4_spend(d, questions=())["total_usd"], 1.26)   # the dry-run folder: not counted
            self.assertEqual(S.ORPHAN_UNIT_USD, S.ONE_CONVERSATION_STOP_USD)
            ss = S.SoftStopV4("B2v4", root=d, questions=())
            self.assertAlmostEqual(ss.report()["step_orphans_usd"], 0.26)


class TestV3Untouched(unittest.TestCase):

    def test_v3_files_unchanged(self):
        want = {"guard/run_online_v3.py": "0daab01d99c47203f3c5fb1bc7ab24afa1c0ae97f58c7c82ec9a7bc876b60cd7",
                "guard/soft_stop_v3.py": "f83a04b44c5636af389d28d67169e446566f2800ff25ecd19043bc57d3b9a391",
                "output/eval_v3/online_tasks.json": R.TASKS_FILE_SHA256,
                "output/eval_v3/b3_tasks.json": R.B3_TASKS_FILE_SHA256}
        for rel, sha in want.items():
            self.assertEqual(R.sha256_file(os.path.join(PC_DIR, *rel.split("/"))), sha, rel)


class TestDroppedDev20(unittest.TestCase):
    """DEV20v4 is dropped (user decision: the build saw the 20 retail dev tasks, so they are not unseen): no step, no
    limit, no B1 gate entry, no task list; `--step DEV20v4` and the old flag are refused with the reason."""

    def test_no_dev20_anywhere(self):
        self.assertNotIn("DEV20v4", R.STEPS)
        self.assertNotIn("DEV20v4", R.WANT_UNITS)
        self.assertNotIn("DEV20v4", R.B1_GATED_STEPS)
        self.assertNotIn("DEV20v4", S.STEP_LIMITS_USD)
        self.assertNotIn("DEV20v4", S.STEPS)
        self.assertIsNone(R.RUN_ID_RE.match("DEV20v4_20261024T000000Z_00000000"))
        for name in ("build_dev20_doc", "select_dev20_tasks", "tau_dev_tasks", "DEV20_N", "DEV20_GROUP"):
            self.assertFalse(hasattr(R, name), name)                          # the 20 dev tasks are never loaded
        self.assertEqual({c["tasks"] for c in R.STEPS.values()}, {"online", "b3"})
        # total cap unchanged; the per-step limits of the runnable steps fit in it
        self.assertEqual(S.V4_CAP_USD, 30.0)                                  # P10 arm plan
        self.assertLessEqual(sum(S.STEP_LIMITS_USD.values()), S.V4_CAP_USD)

    def test_refused_with_a_clear_message(self):
        for argv in (["run", "--step", "DEV20v4", "--run-id", "DEV20v4_20261024T000000Z_00000000", "--shard", "0/1"],
                     ["run", "--step=DEV20v4", "--run-id", "x"], ["new-id", "--step", "DEV20v4"],
                     ["run", "--step", "B2v4", "--run-id", R.new_run_id("B2v4"), "--dev20-enabled"]):
            with self.assertRaises(R.RunRefused) as cm:
                R.main(argv)
            self.assertIn("DEV20v4 is dropped (user decision)", str(cm.exception), argv)
            self.assertIn("not unseen", str(cm.exception))
        for fn in (lambda: R.new_run_id("DEV20v4"), lambda: R.refuse_dropped("DEV20v4"),
                   lambda: R.cmd_run(types.SimpleNamespace(step="DEV20v4", run_id="x"), [])):
            with self.assertRaises(R.RunRefused) as cm:
                fn()
            self.assertIn("DEV20v4 is dropped", str(cm.exception))
        R.refuse_dropped("B2v4")                                              # a built step passes


def fake_runner(argv0: str):
    """A live process whose /proc cmdline starts with argv0 (exec -a), e.g. "run_online_v4 --run-id <id>"."""
    p = subprocess.Popen(["bash", "-c", f"exec -a '{argv0}' sleep 120"])
    for _ in range(200):
        try:
            with open(f"/proc/{p.pid}/cmdline", "rb") as f:
                if f.read().startswith(argv0.encode()):
                    break
        except OSError:
            pass
        time.sleep(0.02)
    return p


class TestP9Fixes(unittest.TestCase):
    """Re-audit P9: the runner's halfway backup (#1a), the watcher needed for a real B2v4 / B3v4 start (#1d), one
    run id per step (#2), the step flock around open-group unit checks (#3), approval words tied to one step (#5),
    the dev ledger in the v4 total (#6), live pids matched to their run id (#7)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            if p.poll() is None:
                p.kill()
            p.wait()
        self.tmp.cleanup()

    def runner(self, run_id):
        p = fake_runner(f"run_online_v4 run --run-id {run_id}")
        self.procs.append(p)
        return p.pid

    # ---- #1a
    def fake_interim(self, fire):
        """A stand-in of scoring/v4_online_interim.py's API (the real one is being changed by its owner): the saved
        halfway.json wins; else a computed decision (fire / no fire) is saved once."""
        I = types.SimpleNamespace(HALF={"B2v4": 742, "B3v4": 160}, HARM=-0.15, calls=[])

        def read_halfway(dirs):
            p = os.path.join(dirs[0], "halfway.json")
            if not os.path.exists(p):
                return None
            with open(p, encoding="utf-8") as f:
                return dict(json.load(f), source="saved", file=p)

        def harm_check(dirs, lines, step, save=True):
            I.calls.append(step)
            saved = read_halfway(dirs)
            if saved is not None:
                if saved["step"] != step:
                    raise ValueError(f"the halfway decision of {saved['step']}, not {step}")
                return saved
            doc = {"step": step, "reached": True, "fire": fire, "diff": -0.5 if fire else 0.0, "complete_groups": 32}
            with open(os.path.join(dirs[0], "halfway.json"), "x", encoding="utf-8") as f:
                json.dump(doc, f)
            return dict(doc, source="computed now")
        I.read_halfway, I.harm_check, I.raw_lines = read_halfway, harm_check, lambda dirs: {}
        return I

    def test_halfway_backup_uses_the_interim_once_only_decision(self):
        real = R.interim_module()                                          # the API the backup uses
        for name in ("read_halfway", "harm_check", "raw_lines"):
            self.assertTrue(callable(getattr(real, name)), name)
        mark = S.HALFWAY_CONVERSATIONS["B3v4"]                             # 64: 32 groups x 2 v4 arms
        bad = os.path.join(self.d, "B3v4", "B3v4_20261024T000000Z_0000000a")
        os.makedirs(bad)
        I = self.fake_interim(fire=True)
        ok, why = R.halfway_backup(bad, "B3v4", units_done=mark - 1, state={}, every_s=0, mod=I)
        self.assertTrue(ok, why)                                            # fewer units than the mark: no look
        self.assertEqual(I.calls, [])
        ok, why = R.halfway_backup(bad, "B3v4", units_done=mark, state={}, every_s=0, mod=I)
        self.assertFalse(ok)
        self.assertIn("halfway harm", why)
        with open(os.path.join(bad, "STOP"), encoding="utf-8") as f:
            self.assertEqual(json.loads(f.read())["stop"], ["harm"])
        os.remove(os.path.join(bad, "STOP"))
        ok, why = R.halfway_backup(bad, "B3v4", units_done=999, state={}, every_s=0, mod=self.fake_interim(False))
        self.assertFalse(ok, why)                                           # the saved decision: a fire stays a fire
        self.assertIn("saved", why)
        good = os.path.join(self.d, "B3v4", "B3v4_20261024T000000Z_0000000b")
        os.makedirs(good)
        ok, why = R.halfway_backup(good, "B3v4", units_done=mark, state={}, every_s=0, mod=self.fake_interim(False))
        self.assertTrue(ok, why)
        self.assertIn("reached, no fire", why)
        self.assertFalse(os.path.exists(os.path.join(good, "STOP")))
        late = os.path.join(self.d, "B3v4", "B3v4_20261024T000000Z_0000000c")
        os.makedirs(late)
        I = self.fake_interim(True)
        ok, why = R.halfway_backup(late, "B3v4", units_done=999, state={"last": time.time()}, every_s=1000, mod=I)
        self.assertTrue(ok)                                                 # looked less than a minute ago
        self.assertEqual(I.calls, [])
        for step in ("B1v4", "Hv4"):                                        # no halfway rule
            self.assertTrue(R.halfway_backup(late, step, units_done=999, state={}, every_s=0, mod=I)[0])
        mixed = os.path.join(self.d, "B2v4", "B2v4_20261024T000000Z_0000000d")
        os.makedirs(mixed)
        shutil.copyfile(os.path.join(bad, "halfway.json"), os.path.join(mixed, "halfway.json"))  # a B3v4 decision
        ok, why = R.halfway_backup(mixed, "B2v4", units_done=999, state={}, every_s=0, mod=self.fake_interim(False))
        self.assertFalse(ok)                                                # fails closed ...
        self.assertIn("fail closed", why)
        with open(os.path.join(mixed, "STOP"), encoding="utf-8") as f:
            self.assertEqual(json.loads(f.read())["stop"], ["halfway_check_failed"])   # ... with STOP and the reason

    def test_runner_wires_the_backup_between_groups(self):
        import inspect
        src = inspect.getsource(R._cmd_run_locked)
        self.assertIn("halfway_backup(p[\"run_dir\"], step, len(files.done), hw_state)", src)
        self.assertLess(src.index("halfway_backup("), src.index("ss.can_start_group("))

    # ---- #1d, #5
    def test_watcher_live_and_real_start_problems(self):
        logs = os.path.join(self.d, "logs")
        os.makedirs(logs)
        rid = R.new_run_id("B2v4")
        self.assertFalse(R.watcher_live("B2v4", rid, logs))                 # no lock file
        lock = R.watcher_lock_path("B2v4", rid, logs)
        self.assertEqual(lock, os.path.join(logs, f"v4_B2v4_{rid}_watch.lock"))
        with open(lock, "a"):
            pass
        self.assertFalse(R.watcher_live("B2v4", rid, logs))                 # a watcher that ended
        import fcntl
        fh = open(lock, "a")
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            self.assertTrue(R.watcher_live("B2v4", rid, logs))
            self.assertEqual(R.real_start_problems("B2v4", rid, "the user's words for B2", self.d, logs), [])
        finally:
            fh.close()
        probs = R.real_start_problems("B2v4", rid, "the user's words for B2", self.d, logs)
        self.assertEqual(len(probs), 1)
        self.assertIn("no live halfway watcher", probs[0])
        self.assertIn("scoring/v4_interim.sh", probs[0])
        self.assertEqual(R.WATCHED_STEPS, ("B2v4", "B3v4"))
        self.assertEqual(R.real_start_problems("B3v4", R.new_run_id("B3v4"), "words for B3 here", self.d, logs)[0][:27],
                         probs[0][:27])
        for step in ("B1v4", "Hv4"):                                        # no halfway rule: no watcher needed
            self.assertEqual(R.real_start_problems(step, R.new_run_id(step), "words for this step", self.d, logs), [])
        # #5: the same words in another step's run.json refuse; the same step's other run does not
        b1 = os.path.join(self.d, "B1v4", R.new_run_id("B1v4"))
        os.makedirs(b1)
        with open(os.path.join(b1, "run.json"), "w", encoding="utf-8") as f:
            json.dump({"ident": {"approval_quote": "Yes, run B1 now please"}, "approval_quote": "Yes, run B1 now please"}, f)
        self.assertEqual(R.approval_used_elsewhere("Hv4", "yes,  run B1 NOW please", self.d), [os.path.join(b1, "run.json")])
        self.assertEqual(R.approval_used_elsewhere("B1v4", "Yes, run B1 now please", self.d), [])
        self.assertEqual(R.approval_used_elsewhere("Hv4", "Yes, run H now please", self.d), [])
        probs = R.real_start_problems("Hv4", R.new_run_id("Hv4"), "Yes, run B1 now please", self.d, logs)
        self.assertEqual(len(probs), 1)
        self.assertIn("one approval is for one step", probs[0])

    def test_real_b2_start_without_a_watcher_is_refused_first(self):
        """In process, the real path: refused by the watcher rule right after the main-chat flag, before the write
        guard, the log-file rule or any import of the runner copy (no call can happen)."""
        rid = R.new_run_id("B2v4")
        self.assertFalse(R.watcher_live("B2v4", rid))
        with self.assertRaises(R.RunRefused) as cm:
            R.main(["run", "--step", "B2v4", "--run-id", rid, "--shard", "0/6", "--approved",
                    "a test of the refusal, never a run", R.MAIN_CHAT_FLAG])
        self.assertIn("no live halfway watcher", str(cm.exception))
        self.assertFalse(os.path.exists(os.path.join(R.V4_ROOT, "B2v4", rid)))
        import inspect
        src = inspect.getsource(R.cmd_run)
        self.assertLess(src.index("real_start_problems("), src.index("write_guard.install("))

    # ---- #2, #7
    def test_one_run_id_per_step_and_pids_matched_to_their_run(self):
        step = os.path.join(self.d, "B2v4")
        mine, other = R.new_run_id("B2v4"), R.new_run_id("B2v4")
        locks = os.path.join(step, "locks")
        os.makedirs(locks)
        self.assertEqual(R.other_runs_live(step, mine), [])
        o_pid = self.runner(other)
        with open(os.path.join(locks, "shard0of4.lock"), "w") as f:
            f.write(f"{o_pid} 20261024T000000Z {other}\n")
        got = R.other_runs_live(step, mine)
        self.assertEqual([x["pid"] for x in got], [o_pid])
        self.assertEqual(R.other_runs_live(step, other), [])                # its own run: not "another"
        with open(os.path.join(locks, "shard0of4.lock"), "w") as f:
            f.write(f"{dead_pid()} 20261024T000000Z {other}\n")            # a dead holder: nothing
        self.assertEqual(R.other_runs_live(step, mine), [])
        os.makedirs(os.path.join(step, other))
        with open(os.path.join(step, other, "pids.txt"), "w") as f:
            f.write(f"{o_pid} {o_pid} 0/6 20261024T000000Z\n")
        self.assertEqual([x["pid"] for x in R.other_runs_live(step, mine)], [o_pid])
        # #7: a live runner of ANOTHER run is not this run's live runner
        self.assertTrue(S.pid_alive(o_pid))
        self.assertTrue(S.pid_alive(o_pid, (other,)))
        self.assertFalse(S.pid_alive(o_pid, (mine,)))
        self.assertTrue(S.pid_alive(os.getpid(), (mine,)))                  # this process: always
        led = os.path.join(step, mine, "ledger", "units_shard0of6.jsonl")
        write_lines(led, [{"event": "start", "conversation_id": f"{mine}:none:retail:1:0:a1", "pid": o_pid}])
        o = S.orphan_spend(self.d)                                          # o_pid runs another run: an orphan
        self.assertEqual(o["units"], 1)
        write_lines(os.path.join(step, other, "ledger", "units_shard0of6.jsonl"),
                    [{"event": "start", "conversation_id": f"{other}:none:retail:2:0:a1", "pid": o_pid}])
        self.assertEqual(S.orphan_spend(self.d)["units"], 1)                # its own run's unit is in flight
        # live_steps: a lock naming a run id needs that run id in the holder's command line
        self.assertEqual(S.live_steps(self.d), {})                          # the lock holder is dead now
        with open(os.path.join(locks, "shard1of4.lock"), "w") as f:
            f.write(f"{o_pid} 20261024T000000Z {mine}\n")
        self.assertEqual(S.live_steps(self.d), {})
        with open(os.path.join(locks, "shard1of4.lock"), "w") as f:
            f.write(f"{o_pid} 20261024T000000Z {other}\n")
        self.assertEqual(S.live_steps(self.d), {"B2v4": [o_pid]})
        # the shard lock now names its run id
        fd = R.acquire_shard_lock(os.path.join(locks, "shard5of6.lock"), mine)
        try:
            with open(os.path.join(locks, "shard5of6.lock"), encoding="utf-8") as f:
                words = f.read().split()
            self.assertEqual((words[0], words[2]), (str(os.getpid()), mine))
        finally:
            R.release_shard_lock(fd)

    # ---- #3
    def test_open_group_unit_checks_hold_the_step_flock(self):
        import contextlib
        held = {"n": 0}
        seen = []
        lk = threading.Lock()

        @contextlib.contextmanager
        def gl():                                                           # a lock, as the step's flock
            with lk:
                held["n"] += 1
                try:
                    yield
                finally:
                    held["n"] -= 1

        def can_start_unit(running=0):
            seen.append(held["n"])
            return True, "ok"
        tries = {}

        def run_unit(u, attempt):
            tries[u] = attempt
            return {"error": "boom" if (u == ("retail", 1, 0, "none") and attempt == 1) else None}
        units = [("retail", t, 0, a) for t in range(2) for a in FIVE_ARMS]
        st = R.GroupPool(units, run_unit, lambda *a: (True, "ok"), workers=2, can_start_unit=can_start_unit,
                         group_lock=gl).run()
        self.assertEqual(len(seen), 9)                                      # 2 x 4 open-group units + 1 re-run
        self.assertEqual(set(seen), {1})                                    # every unit check under the flock
        self.assertEqual(st["retries"], 1)
        self.assertEqual(held["n"], 0)

    # ---- #6
    def test_v4_total_takes_the_dev_ledger_when_it_is_higher(self):
        self.assertEqual(_REAL_DEV_LEDGER_RELPATH, os.path.join("dev", "dev_spend_ledger.jsonl"))
        with open(os.path.join(PC_DIR, "scoring", "v4_offline_eval.py"), encoding="utf-8") as f:
            self.assertIn('DEV_LEDGER = os.path.join(OUT_DIR, "dev_spend_ledger.jsonl")', f.read())
        led = os.path.join(self.d, "dev", "ledger.jsonl")
        os.makedirs(os.path.dirname(led))
        with open(led, "w", encoding="utf-8") as f:
            f.write(json.dumps({"kind": "reserve", "rid": "r1", "run_id": "x", "usd": 0.05}) + "\n")
            f.write(json.dumps({"kind": "spend", "rid": "r1", "run_id": "x", "usd": 0.01}) + "\n")
            f.write(json.dumps({"kind": "reserve", "rid": "r2", "run_id": "x", "usd": 0.03}) + "\n")   # open: worst case
            f.write('{"kind": "res')                                         # a cut line: $0.01
        got = S.dev_ledger_spend(led)
        self.assertAlmostEqual(got["usd"], 0.05)
        self.assertEqual(got["calls"], 3)
        q = os.path.join(self.d, "questions_answers_v4.jsonl")
        write_lines(q, [{"key": "a", "cost_usd": 0.02}])
        t = S.v4_spend(self.d, questions=(q,), dev_ledger=led)
        self.assertAlmostEqual(t["total_usd"], 0.05)                        # max(ledger 0.05, answers 0.02)
        self.assertAlmostEqual(t["dev_ledger_usd"], 0.05)
        self.assertAlmostEqual(S.v4_spend(self.d, questions=(q,), dev_ledger=None)["total_usd"], 0.02)
        write_lines(q, [{"key": "b", "cost_usd": 0.2}], "a")
        self.assertAlmostEqual(S.v4_spend(self.d, questions=(q,), dev_ledger=led)["total_usd"], 0.22)   # answers higher
        self.assertEqual(S.dev_ledger_spend(os.path.join(self.d, "none.jsonl"))["usd"], 0.0)
        old = S.DEV_LEDGER_RELPATH                                           # the default: <root>/<relpath>
        try:
            S.DEV_LEDGER_RELPATH = os.path.join("dev", "ledger.jsonl")
            ss = S.SoftStopV4("B1v4", root=self.d, questions=())
            self.assertAlmostEqual(ss.report()["total_usd"], 0.05)
            self.assertEqual(ss.run_json()["dev_ledger"], led)
        finally:
            S.DEV_LEDGER_RELPATH = old
        with open(led, "rb") as f:                                           # read only: the file is unchanged
            self.assertTrue(f.read().endswith(b'{"kind": "res'))


class TestP10ArmPlan(unittest.TestCase):
    """The P10 arm plan (user decision): the baseline check (counts and keys only, made-up v3 folders here; the real
    v3 runs are never read by the tests), the sandbox-only --arms."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pc = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def fake_baseline(self, step, sha=None, lines=None, tasks=None, drop_arm=None):
        b = R.BASELINES[step]
        rd = os.path.join(self.pc, *b["run_dir"].split("/"))
        os.makedirs(rd)
        with open(os.path.join(rd, "run.json"), "w", encoding="utf-8") as f:
            json.dump({"ident": {"run_id": b["run_id"], "tasks_file_sha256": sha or b["task_file_sha256"]},
                       "tasks_file_sha256": sha or b["task_file_sha256"]}, f)
        for arm in b["arms"]:
            if arm == drop_arm:
                continue
            recs = ([{"env": d, "task_index": t, "trial": 0, "guard": arm} for d, t in tasks] if tasks is not None
                    else [{"env": "retail", "task_index": i, "trial": 0, "guard": arm} for i in range(lines)])
            write_lines(os.path.join(rd, arm, "episodes_shard0of3.jsonl"), recs)
        return rd

    def test_baselines_recorded(self):
        self.assertEqual(set(R.BASELINES), {"B2v4", "B3v4"})
        info = R.baseline_info("B2v4")
        self.assertEqual({k: info[k] for k in ("run_dir", "run_id", "arms", "task_file_sha256")},
                         {"run_dir": "output/eval_v3/B2/B2_20261023T155537Z_c842d895",
                          "run_id": "B2_20261023T155537Z_c842d895",
                          "arms": ["none", "direct", "tgr_frozen", "tgr_tracker_v3"],
                          "task_file_sha256": R.TASKS_FILE_SHA256})
        self.assertEqual(R.baseline_info("B3v4")["run_dir"], "output/eval_v3/B3/B3_20261023T190740Z_9bf882c0")
        self.assertEqual(R.baseline_info("B3v4")["task_file_sha256"], R.B3_TASKS_FILE_SHA256)
        self.assertEqual(len(R.baseline_info("B3v4")["missing_tasks"]), 15)
        self.assertIsNone(R.baseline_info("Hv4"))
        self.assertTrue(R.baseline_check("Hv4", self.pc)["ok"])
        import inspect                                                    # the real path only, before run.json
        src = inspect.getsource(R._cmd_run_locked)
        self.assertIn("counts and keys only; refused if they differ", src)
        self.assertLess(src.index("baseline_check(step"), src.index("ensure_run_json("))

    def test_b2_baseline_counts(self):
        self.fake_baseline("B2v4", lines=297)
        res = R.baseline_check("B2v4", self.pc)
        self.assertTrue(res["ok"], res["problems"])
        self.assertEqual({a: v["lines"] for a, v in res["per_arm"].items()},
                         {"none": 297, "direct": 297, "tgr_frozen": 297, "tgr_tracker_v3": 297})
        shutil.rmtree(os.path.join(self.pc, "output"))
        self.fake_baseline("B2v4", lines=296)
        self.assertFalse(R.baseline_check("B2v4", self.pc)["ok"])
        shutil.rmtree(os.path.join(self.pc, "output"))
        self.fake_baseline("B2v4", lines=297, sha="0" * 64)
        res = R.baseline_check("B2v4", self.pc)
        self.assertFalse(res["ok"])
        self.assertIn("task-file sha256", res["problems"][0])
        shutil.rmtree(os.path.join(self.pc, "output"))
        self.fake_baseline("B2v4", lines=297, drop_arm="tgr_tracker_v3")
        self.assertIn("tgr_tracker_v3: no episodes file", R.baseline_check("B2v4", self.pc)["problems"])

    def test_b3_baseline_keys(self):
        all64 = [("retail", t) for t in range(49)] + list(S.B3_FILL_TASKS)
        kept = [k for k in all64 if k not in set(S.B3_FILL_TASKS)]
        self.fake_baseline("B3v4", tasks=kept + kept[:3])                  # re-run lines: the keys count
        res = R.baseline_check("B3v4", self.pc, all_tasks=all64)
        self.assertTrue(res["ok"], res["problems"])
        self.assertEqual(res["per_arm"]["none"]["tasks"], 49)
        shutil.rmtree(os.path.join(self.pc, "output"))
        self.fake_baseline("B3v4", tasks=kept[:-1] + [S.B3_FILL_TASKS[0]])  # a fill task in the baseline
        res = R.baseline_check("B3v4", self.pc, all_tasks=all64)
        self.assertFalse(res["ok"])
        self.assertIn("missing", " ".join(res["problems"]))

    def test_arms_flag_is_sandbox_only(self):
        self.assertEqual(R.parse_arms("tgr_frozen,none"), ("none", "tgr_frozen"))
        for bad in ("", "none,none", "tgr_tracker_v5", "direct_facts_v3"):
            with self.assertRaises(R.RunRefused):
                R.parse_arms(bad)
        with self.assertRaises(R.RunRefused) as cm:
            R.main(["run", "--step", "B2v4", "--run-id", R.new_run_id("B2v4"), "--shard", "0/6", "--arms", "none"])
        self.assertIn("--arms is refused outside the sandbox", str(cm.exception))
        units = R.plan_units([{"domain": "retail", "task_index": 4}], 1, 0, "B1v4", only=("none", "direct"))
        self.assertEqual(sorted(u[3] for u in units), ["direct", "none"])


WATCHER = os.path.join(PC_DIR, "scoring", "v4_interim.sh")
# a fake check: logs its argv (one JSON line per call) to $FAKE_CALLS; on call $FAKE_STOP_AT it writes the STOP file of
# its --run-dir; on call $FAKE_KILL_AT it kills $FAKE_KILL_PID; exits $FAKE_RC (default 0)
_FAKE_INTERIM = r"""
import json, os, signal, sys
calls = os.environ["FAKE_CALLS"]
with open(calls, "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\n")
with open(calls) as f:
    n = sum(1 for _ in f)
rd = sys.argv[sys.argv.index("--run-dir") + 1]
if str(n) == os.environ.get("FAKE_STOP_AT") and "--write-stop" in sys.argv:
    with open(os.path.join(rd, "STOP"), "w") as f:
        f.write(json.dumps({"stop": ["harm"], "by": "fake"}) + "\n")
if str(n) == os.environ.get("FAKE_KILL_AT"):
    os.kill(int(os.environ["FAKE_KILL_PID"]), signal.SIGKILL)
print("[v4-interim] B2v4: harm %s state False cost False errors False -> %s" % (
    str(n) == os.environ.get("FAKE_STOP_AT"), "STOP" if str(n) == os.environ.get("FAKE_STOP_AT") else "go on"))
sys.exit(int(os.environ.get("FAKE_RC", "0")))
"""


class TestHalfwayWatcher(unittest.TestCase):
    """scoring/v4_interim.sh ($0): fake runner pids (kill -0 plus the run_online_v4 cmdline mark) and a fake check
    command (V4_INTERIM_CMD); it ends on a STOP file, on no live pid, and after 3 failed checks in a row."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = _unique("p7_watch")
        self.rid = R.new_run_id("B2v4")
        self.run_dir = os.path.join(self.out, "B2v4", self.rid)
        os.makedirs(self.run_dir)
        self.pids = os.path.join(self.run_dir, "pids.txt")
        self.fake = os.path.join(self.tmp.name, "fake_interim.py")
        with open(self.fake, "w", encoding="utf-8") as f:
            f.write(_FAKE_INTERIM)
        self.calls = os.path.join(self.tmp.name, "calls.jsonl")
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            if p.poll() is None:
                p.kill()
            p.wait()
        shutil.rmtree(self.out, ignore_errors=True)
        self.tmp.cleanup()

    def runner_like(self, mark=True) -> int:
        """A live process whose cmdline has run_online_v4 (argv[0] via exec -a), or a plain sleep."""
        cmd = ["bash", "-c", "exec -a run_online_v4_fake sleep 120"] if mark else ["sleep", "120"]
        p = subprocess.Popen(cmd)
        self.procs.append(p)
        for _ in range(100):                                                  # wait until exec has happened
            try:
                with open(f"/proc/{p.pid}/cmdline", "rb") as f:
                    if (b"run_online_v4" in f.read()) == mark:
                        break
            except OSError:
                pass
            time.sleep(0.02)
        return p.pid

    def dead_pid(self) -> int:
        p = subprocess.Popen(["true"])
        p.wait()
        return p.pid

    def write_pids(self, pids):
        with open(self.pids, "w", encoding="utf-8") as f:
            f.write("not-a-pid line\n")
            for i, pid in enumerate(pids):
                f.write(f"{pid} {pid} {i}/{len(pids)} 20261024T000000Z\n")

    def watch(self, extra_env=None, args=None, timeout=60):
        env = dict(ENV, V4_INTERIM_EVERY="1", V4_INTERIM_CMD=f"{sys.executable} -B {self.fake}",
                   V4_INTERIM_LOGS=self.tmp.name, V4_INTERIM_PID_WAIT="5", FAKE_CALLS=self.calls)
        env.update(extra_env or {})
        r = subprocess.run(["bash", WATCHER] + (args if args is not None else [self.run_dir, self.pids]),
                           capture_output=True, text=True, env=env, timeout=timeout, cwd=self.tmp.name)
        return r

    def got_calls(self):
        if not os.path.exists(self.calls):
            return []
        with open(self.calls, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]

    def log(self, kind="watch"):
        with open(os.path.join(self.tmp.name, f"v4_B2v4_{self.rid}_{kind}.log"), encoding="utf-8") as f:
            return f.read()

    def test_stop_file_ends_it(self):
        live = self.runner_like()
        self.write_pids([self.dead_pid(), live])
        r = self.watch({"FAKE_STOP_AT": "2"})
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.got_calls()
        self.assertEqual(len(calls), 2)
        for c in calls:                                                       # the exact check arguments
            self.assertEqual(c, ["--write-stop", "--run-dir", os.path.realpath(self.run_dir)])
        self.assertTrue(os.path.exists(os.path.join(self.run_dir, "STOP")))
        w = self.log()
        self.assertIn("STOP file present after check 2", w)
        self.assertIn(f"alive {live};", w)
        self.assertIn("-> go on", w)
        self.assertEqual(self.log("interim").count("=== check "), 2)
        self.assertIsNone(self.procs[0].poll())                               # the watcher never kills a runner
        self.assertEqual(r.stdout, "")                                        # nothing to the terminal

    def test_no_live_pid_ends_it(self):
        live = self.runner_like()
        self.write_pids([live])
        r = self.watch({"FAKE_KILL_AT": "2", "FAKE_KILL_PID": str(live)})     # the runner dies after check 2
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.got_calls()), 2)
        self.assertFalse(os.path.exists(os.path.join(self.run_dir, "STOP")))
        self.assertIn("no runner pid of", self.log())
        self.assertIn("after 2 checks", self.log())

    def test_dead_or_foreign_pids_mean_no_check(self):
        self.write_pids([self.dead_pid(), self.runner_like(mark=False)])     # a reused pid: no run_online_v4 mark
        r = self.watch()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.got_calls(), [])
        self.assertIn("after 0 checks", self.log())

    def test_existing_stop_and_default_pids_file(self):
        self.write_pids([self.runner_like()])
        with open(os.path.join(self.run_dir, "STOP"), "w", encoding="utf-8") as f:
            f.write('{"stop": ["cost"]}\n')
        r = self.watch(args=[self.run_dir])                                   # <run_dir>/pids.txt by default
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.got_calls(), [])
        self.assertIn(f"pids file {os.path.realpath(self.pids)}", self.log())

    def test_failing_check_exits_4(self):
        self.write_pids([self.runner_like()])
        r = self.watch({"FAKE_RC": "1", "V4_INTERIM_EVERY": "0"})
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertEqual(len(self.got_calls()), 3)
        self.assertIn("failed 3 times in a row", self.log())
        # audit P9 #1c: STOP (with the reason) before exit 4, so no new group starts while nobody checks
        with open(os.path.join(self.run_dir, "STOP"), encoding="utf-8") as f:
            stop = json.loads(f.read())
        self.assertEqual(stop["stop"], ["watcher_check_failed"])
        self.assertEqual(stop["by"], "scoring/v4_interim.sh")
        self.assertIn("failed 3 times in a row", stop["reason"])
        self.assertIn("wrote", self.log())

    def test_failing_check_never_overwrites_a_stop(self):
        self.write_pids([self.runner_like()])
        r = self.watch({"FAKE_RC": "1", "V4_INTERIM_EVERY": "0", "FAKE_STOP_AT": "3"})   # the 3rd check writes one
        self.assertEqual(r.returncode, 4, r.stderr)
        with open(os.path.join(self.run_dir, "STOP"), encoding="utf-8") as f:
            self.assertEqual(json.loads(f.read())["by"], "fake")
        self.assertIn("STOP already present", self.log())

    def test_test_overrides_only_in_a_dry_run_folder(self):
        """audit P9 #1b: V4_INTERIM_CMD / _PY / _CMD_MARK / _EVERY are obeyed only under output/eval_v4/dryrun/; for a
        real run folder they are ignored (logged). The real folder is not created; no check runs (no pids file)."""
        rid = R.new_run_id("B2v4")
        real = os.path.join(R.V4_ROOT, "B2v4", rid)
        self.assertFalse(os.path.exists(real))
        r = self.watch({"V4_INTERIM_PID_WAIT": "0", "V4_INTERIM_PY": "/bin/false", "V4_INTERIM_CMD_MARK": ""},
                       args=[real])
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(self.got_calls(), [])
        with open(os.path.join(self.tmp.name, f"v4_B2v4_{rid}_watch.log"), encoding="utf-8") as f:
            w = f.read()
        self.assertIn("test overrides ignored: V4_INTERIM_EVERY V4_INTERIM_CMD V4_INTERIM_PY V4_INTERIM_CMD_MARK", w)
        self.assertIn("a check every 300s: /home/azureuser/miniconda3/bin/python3 -B -m scoring.v4_online_interim", w)
        self.assertFalse(os.path.exists(real))
        self.assertFalse(os.path.exists(os.path.join(R.V4_ROOT, "B2v4", rid)))
        r = self.watch({"V4_INTERIM_PID_WAIT": "0"})                        # a dry-run folder: obeyed
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn(f"a check every 1s: {sys.executable} -B {self.fake}", self.log())
        self.assertNotIn("overrides ignored", self.log())

    def test_no_pids_file_exits_3(self):
        r = self.watch({"V4_INTERIM_PID_WAIT": "0"})
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(self.got_calls(), [])

    def test_refusals(self):
        v3 = os.path.join(R.OUTPUT_DIR, "eval_v3", "B2", "B2_20261023T000000Z_00000000")
        d20 = os.path.join(self.out, "DEV20v4", "DEV20v4_20261024T000000Z_00000000")
        wrong = os.path.join(self.out, "B3v4", self.rid)                     # a B2v4 id in the B3v4 folder
        for args in ([], [v3], [d20], [wrong], [R.V4_ROOT], ["/tmp/x/B2v4/" + self.rid]):
            r = self.watch(args=args)
            self.assertEqual(r.returncode, 2, (args, r.stderr))
            self.assertIn("refused", r.stderr)
        self.assertEqual(self.got_calls(), [])
        self.assertFalse(os.path.exists(os.path.join(R.OUTPUT_DIR, "eval_v3", "B2", "B2_20261023T000000Z_00000000")))

    def test_runner_gives_the_watcher_command(self):
        cmd = R.watcher_command("B2v4", self.rid, self.out)
        rd = os.path.join(os.path.abspath(self.out), "B2v4", self.rid)
        self.assertEqual(cmd, f"bash {WATCHER} {rd} {rd}/pids.txt > "
                              f"{os.path.join(R.LOGS_DIR, f'v4_B2v4_{self.rid}_watcher_stdout.txt')} 2>&1")
        self.assertEqual(R.watcher_command("B3v4", "B3v4_x")[:len(f"bash {WATCHER} {R.V4_ROOT}/B3v4/B3v4_x ")],
                         f"bash {WATCHER} {R.V4_ROOT}/B3v4/B3v4_x ")
        self.assertTrue(os.access(WATCHER, os.X_OK))
        with open(WATCHER, encoding="utf-8") as f:
            text = f.read()
        self.assertEqual([x for x in text.splitlines() if "pgrep" in x and not x.lstrip().startswith("#")], [])
        self.assertIn("kill -0", text)
        self.assertIn("-m scoring.v4_online_interim", text)


# ================================================================================================ venv processes

_STANDINS = r'''
import json, os, sys, types
from state_tracker.v3 import questions as Q3

def install_standins(real_v3_tracker=False):
    """The REAL v4 modules (guard/tgr_tracker_v4.py, guard/direct_facts_v4.py, state_tracker/v4/questions_v4.py),
    with a spy around the tracker's build: it records conv.v4_blocks and the hook's `where` at every check."""
    from guard import runner_path
    runner_path.setup()
    from guard import tgr_tracker_v4 as T4
    from guard import direct_facts_v4 as DF4  # noqa: F401
    from state_tracker.v4 import questions_v4 as Q4  # noqa: F401
    T4.SEEN = {"builds": 0, "where": [], "v4_blocks": [], "require_freeze": []}
    real_build = T4.build
    class Spy:
        def __init__(self, inner, answers):
            self.inner, self.answers = inner, answers
            self.config, self.info = inner.config, inner.info
        def step(self, conv, step):
            T4.SEEN["v4_blocks"].append(list(getattr(conv, "v4_blocks", ["MISSING"])))
            T4.SEEN["where"].append(dict(self.answers.where or {}))
            return self.inner.step(conv, step)
        def commit(self, conv, rec):
            self.inner.commit(conv, rec)
    def build(domain, tools=None, **kw):
        T4.SEEN["builds"] += 1
        T4.SEEN["require_freeze"].append(kw.get("require_freeze"))
        return Spy(real_build(domain, tools, **kw), kw.get("answers"))
    T4.build = build
    return T4
'''

_DRY_DRIVER = _STANDINS + r'''
import contextlib, io
pc, out = sys.argv[1], sys.argv[2]
from guard import run_online_v4 as R
install_standins()
import tau_bench.envs as TE
STRATEGIES = []
_orig = TE.get_env
def spy(*a, **k):
    STRATEGIES.append(k.get("user_strategy"))
    if k.get("user_strategy") != "human":
        raise AssertionError("get_env with a paid user simulator in a dry run")
    return _orig(*a, **k)
TE.get_env = spy
res = {}
for step, n in (("B1v4", 1), ("B2v4", 6), ("B3v4", 6), ("Hv4", 6)):
    rid = R.new_run_id(step)
    argv = ["run", "--step", step, "--run-id", rid, "--shard", f"0/{n}", "--dry-run", "--out-root", out,
            "--workers", "8"]
    with contextlib.redirect_stdout(io.StringIO()):
        plan = R.main(argv)
    res[step] = {"units_in_run": plan["units_in_run"], "units_per_shard": plan["units_per_shard"],
                 "cover": plan["shards_cover_every_unit_once"], "llm_calls": plan["llm_calls"],
                 "profile": plan["profile"], "models": plan["models"], "run_dir_exists": os.path.exists(
                     plan["paths"]["run_dir"]), "domains": plan["domains_in_shard"],
                 "freeze_ok": plan["v4_freeze"]["ok"], "switches": plan["ident"]["v4_switches"],
                 "b1_gate_ok": (plan.get("b1_gate") or {}).get("ok"), "b1_gate": plan.get("b1_gate") is not None,
                 "main_chat_flag": plan["main_chat_flag"], "tiny_budget": plan["tiny_budget_shard"],
                 "watcher_command": plan["watcher_command"], "run_dir": plan["paths"]["run_dir"],
                 "live_arms": plan["live_arms"], "units_per_arm": plan["units_per_arm"],
                 "guard_arms": sorted(plan["guard_info"]), "baseline": plan["baseline"]}
res["strategies"] = sorted(set(STRATEGIES))
res["network_events"] = Q3.network_events()
print(json.dumps(res))
'''

_SANDBOX_DRIVER = _STANDINS + r'''
import contextlib, hashlib, io
pc, out = sys.argv[1], sys.argv[2]
WRITES = []
def _writes(event, args):
    if event == "open" and len(args) >= 3 and isinstance(args[0], (str, bytes)):
        m, fl = args[1], args[2]
        if (isinstance(m, str) and any(c in m for c in "wax+")) or (isinstance(fl, int) and fl & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC)):
            WRITES.append(os.path.realpath(os.fsdecode(args[0])))
sys.addaudithook(_writes)
Q3.block_network()
from guard import runner_path, run_online_v4 as R
T = install_standins()
R.install_sandbox()
runner_path.setup()
from exp_core import models
O = types.SimpleNamespace
LOG = {"judge": 0, "direct": 0, "agent": 0, "user": 0, "other": 0}
def usage():
    return O(input_tokens=1000, output_tokens=100, output_tokens_details=O(reasoning_tokens=7),
             input_tokens_details=O(cached_tokens=0))
class Resp:
    def __init__(self, text, output=()):
        self.output_text, self.output, self.usage, self.status = text, list(output), usage(), "completed"
    def model_dump(self, mode=None, **_):
        return {"output_text": self.output_text, "fake": True}
def preds(user):
    s = user.rfind("\nPredicates to decide:\n"); e = user.find("\n\nFor every predicate return", s)
    if s < 0 or e < 0:
        return []
    return [l[2:].split(":", 1)[0].strip() for l in user[s:e].splitlines()[2:] if l.startswith("- ") and ":" in l]
READ = {"retail": ("find_user_id_by_email", {"email": "nobody@example.com"}),
        "airline": ("get_user_details", {"user_id": "nobody_1234"})}
WRITE = {"retail": ("cancel_pending_order", {"order_id": "#W0000000", "reason": "no longer needed"}),
         "airline": ("cancel_reservation", {"reservation_id": "ZZZ999"})}
class Responses:
    def create(self, **kw):
        items = kw.get("input") or []
        if "text" in kw:
            name = kw["text"]["format"]["name"]
            user = items[1]["content"]
            if name == "predicate_values":
                LOG["judge"] += 1
                return Resp(json.dumps({"predicates": [{"name": n, "value": "true", "evidence": "fake"} for n in preds(user)]}))
            if name == "direct_decision":
                LOG["direct"] += 1
                act = user.rsplit("next action", 1)[-1]
                unsafe = "cancel_pending_order" in act or "cancel_reservation" in act
                return Resp(json.dumps({"safe": not unsafe, "violated_policy_statements": ["fake: confirm first"] if unsafe else [],
                                        "explanation": "fake decision"}))
            LOG["other"] += 1
            raise RuntimeError(f"unexpected structured call {name}")
        if kw.get("tools"):
            LOG["agent"] += 1
            names = {t["name"] for t in kw["tools"]}
            dom = "retail" if "cancel_pending_order" in names else "airline"
            first = next((i.get("content") for i in items if i.get("role") == "user"), "") or ""
            n_fc = sum(1 for i in items if i.get("type") == "function_call")
            cid = f"call_{n_fc}_{hashlib.sha256(first.encode()).hexdigest()[:8]}"
            if n_fc >= 2:
                return Resp("Done. Anything else?", [O(type="message")])
            tool, args = (READ if n_fc == 0 else WRITE)[dom]
            return Resp("", [O(type="function_call", call_id=cid, name=tool, arguments=json.dumps(args))])
        LOG["user"] += 1
        if len(items) <= 2:
            return Resp("Hi, please cancel my booking for me.", [O(type="message")])
        return Resp("###STOP###", [O(type="message")])
class Client:
    def __init__(self):
        self.responses = Responses()
    def with_options(self, **_):
        return self
models._base_client = Client()
rid = R.new_run_id("B1v4")
with contextlib.redirect_stdout(io.StringIO()) as so:
    R.main(["run", "--step", "B1v4", "--run-id", rid, "--shard", "0/1", "--workers", "2", "--task-ids", "retail:4,airline:4",
            "--out-root", out, "--approved", "sandbox check with fake LLMs, no money"])
run_dir = os.path.join(out, "B1v4", rid)
def jl(p):
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(x) for x in f if x.strip()]
lines = []
for a in R.ARMS:
    lines += jl(os.path.join(run_dir, a, "episodes_shard0of1.jsonl"))
answers = jl(os.path.join(run_dir, "questions", "answers_shard0of1.jsonl"))
asks = jl(os.path.join(run_dir, "questions", "asks_shard0of1.jsonl"))
with open(os.path.join(run_dir, "run.json")) as f:
    rj = json.load(f)
dry = os.path.realpath(R.DRYRUN_ROOT)
res = {"run_id": rid, "lines": len(lines), "errors": [l.get("error") for l in lines if l.get("error")],
       "conv_ids": sorted(l.get("conversation_id") or "" for l in lines), "arms": sorted(l["guard"] for l in lines),
       "profiles": sorted({l["profile"] for l in lines}), "answers": len(answers),
       "answers_with_cid": sum(1 for a in answers if (a.get("conversation_id") or "").startswith(rid + ":tgr_tracker_v4:")),
       "answers_with_check": sum(1 for a in answers if (a.get("where") or {}).get("check") is not None),
       "asks": len(asks), "asks_with_cid": sum(1 for a in asks if (a.get("conversation_id") or "").startswith(rid + ":")),
       "standin_where_checks": sorted({w.get("check") is not None for w in T.SEEN["where"]}),
       "standin_where_keys": sorted(set().union(*[set(w) for w in T.SEEN["where"]])) if T.SEEN["where"] else [],
       "v4_blocks_first": sorted({json.dumps(b) for i, (b, w) in enumerate(zip(T.SEEN["v4_blocks"], T.SEEN["where"])) if all(x.get("conversation_id") != w.get("conversation_id") for x in T.SEEN["where"][:i])}),
       "tracker_checks": len(T.SEEN["where"]),
       "v4_blocks_missing": sum(1 for b in T.SEEN["v4_blocks"] if b == ["MISSING"]),
       "require_freeze": sorted(set(map(str, T.SEEN["require_freeze"]))),
       "answers_with_where_first": sum(1 for a in answers if isinstance(a.get("where_first"), dict)),
       "run_json_has_manifest_key": "v4_manifest_sha256" in rj, "calls": LOG,
       "run_json_live_arms": rj.get("live_arms"), "run_json_baseline": rj.get("baseline", "MISSING"),
       "ledger_events": sorted(x["event"] for x in jl(os.path.join(run_dir, "ledger", "units_shard0of1.jsonl"))),
       "ledger_cids": len({x["conversation_id"] for x in jl(os.path.join(run_dir, "ledger", "units_shard0of1.jsonl"))}),
       "orphans_after": R.soft_stop_v4.orphan_spend(run_dir, skip_dryrun=False)["units"],
       "step_lock_exists": os.path.exists(os.path.join(out, "B1v4", "locks", "group_start.flock")),
       "network_events": Q3.network_events(),
       "writes_outside": sorted({w for w in WRITES if not (w == dry or w.startswith(dry + os.sep)) and not w.startswith("/dev/")}),
       "stdout_tail": so.getvalue()[-1500:]}
print(json.dumps(res, default=str))
'''


def _unique(name: str) -> str:
    """A dry-run folder of this process only (another process may run this module at the same time)."""
    import uuid
    return os.path.join(R.DRYRUN_ROOT, f"{name}_{os.getpid()}_{uuid.uuid4().hex[:8]}")


def _run_driver(code: str, out: str, timeout: int = 1500) -> dict:
    if os.path.exists(out):
        shutil.rmtree(out)
    try:
        r = subprocess.run([VENV_PY, "-B", "-W", "ignore", "-c", code, PC_DIR, out], capture_output=True, text=True,
                           cwd=PC_DIR, timeout=timeout, env=ENV)
        log = os.path.join(R.LOGS_DIR, f"v4_p1e_test_{os.path.basename(out).split('_')[1]}.txt")
        with open(log, "w", encoding="utf-8") as f:
            f.write(r.stdout[-30000:] + "\n----\n" + r.stderr[-30000:])
        if r.returncode != 0:
            raise AssertionError(f"driver failed ({r.returncode}): {r.stderr[-3000:]}")
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        if os.path.exists(out):
            shutil.rmtree(out)


@unittest.skipUnless(os.path.exists(VENV_PY), "τ-bench venv not found")
class TestDryRuns(unittest.TestCase):
    """The dry run of every step: 0 LLM calls, nothing written, the unit counts and the shard cover."""

    def test_every_step(self):
        res = _run_driver(_DRY_DRIVER, _unique("p1e_dry_test"))
        want = {"B1v4": 4, "B2v4": 594, "B3v4": 188, "Hv4": 594}
        for step, n in want.items():
            r = res[step]
            self.assertEqual(r["units_in_run"], n, step)
            self.assertEqual(sum(r["units_per_shard"].values()), n, step)
            self.assertTrue(r["cover"], step)
            self.assertEqual(r["llm_calls"], {"agent": 0, "user": 0, "judge": 0, "tiny": 0}, step)
            self.assertFalse(r["run_dir_exists"], step)                          # nothing written
            self.assertEqual(r["switches"], {"facts": "v4", "meaning": "tiny", "messages": "rule"})
            self.assertIn(f"scoring/v4_interim.sh {r['run_dir']} {r['run_dir']}/pids.txt > ", r["watcher_command"])
        self.assertEqual(res["B1v4"]["units_per_shard"], {"0/1": 4})
        self.assertEqual(res["Hv4"]["profile"], "nano-agent-luna")
        self.assertEqual(res["Hv4"]["models"], {"agent": "gpt-5-nano", "user": "gpt-6-luna", "guard": "gpt-6-luna"})
        for s in ("B1v4", "B2v4", "B3v4"):
            self.assertEqual(set(res[s]["models"].values()), {"gpt-6-luna"}, s)
        self.assertEqual(res["B3v4"]["domains"], ["retail"])
        # a dry run (0 calls) only reports the B1 gate: no B1v4 folder here, the plan still runs (audit P7 #2)
        self.assertFalse(res["B1v4"]["b1_gate"])
        for s in ("B2v4", "B3v4", "Hv4"):
            self.assertTrue(res[s]["b1_gate"], s)
            self.assertFalse(res[s]["b1_gate_ok"], s)
            self.assertFalse(res[s]["main_chat_flag"], s)                          # no main-chat flag needed
        self.assertEqual(res["B2v4"]["tiny_budget"]["n_shards"], 6)
        self.assertAlmostEqual(res["B2v4"]["tiny_budget"]["usd"], S.STEP_LIMITS_USD["B2v4"] / 6)
        self.assertAlmostEqual(res["Hv4"]["tiny_budget"]["usd"], S.STEP_LIMITS_USD["Hv4"] / 6 / 2)   # v3 and v4 tiny
        # P10 arm plan: the live arms, the guards built, the baseline (recorded; checked on the real path only)
        for s in R.STEPS:
            self.assertEqual(res[s]["live_arms"], list(S.step_live_arms(s)), s)
            self.assertEqual(res[s]["guard_arms"], sorted(S.step_live_arms(s)), s)
        self.assertEqual(res["B3v4"]["units_per_arm"], {"none": 15, "direct": 15, "tgr_frozen": 15,
                                                       "tgr_tracker_v3": 15, "direct_facts_v4": 64,
                                                       "tgr_tracker_v4": 64})
        self.assertEqual(res["B2v4"]["baseline"]["run_id"], "B2_20261023T155537Z_c842d895")
        self.assertEqual(res["B3v4"]["baseline"]["run_id"], "B3_20261023T190740Z_9bf882c0")
        self.assertIn("real runs only", res["B2v4"]["baseline"]["check"])
        self.assertIsNone(res["Hv4"]["baseline"])
        self.assertIsNone(res["B1v4"]["baseline"])
        self.assertEqual(res["strategies"], ["human"])                           # never user_strategy="llm"
        self.assertLessEqual(set(res["network_events"]), {"socket.__new__"})
        print(json.dumps({s: {"units_in_run": res[s]["units_in_run"], "units_per_shard": res[s]["units_per_shard"]}
                          for s in want}), file=sys.stderr)


@unittest.skipUnless(os.path.exists(VENV_PY), "τ-bench venv not found")
class TestSandboxB1(unittest.TestCase):
    """A sandbox B1v4 run with fake LLMs: the conversation id and `where` on every tiny answer."""

    def test_sandbox_b1(self):
        res = _run_driver(_SANDBOX_DRIVER, _unique("p1e_sandbox_test"))
        self.assertEqual(res["lines"], 4, res["stdout_tail"])
        self.assertEqual(res["errors"], [])
        self.assertEqual(res["arms"], sorted(list(B1_ARMS) * 2))         # P10: B1v4's 2 live arms
        self.assertEqual(res["profiles"], ["luna-dev"])
        self.assertEqual(len(set(res["conv_ids"])), 4)
        self.assertTrue(all(c.startswith(res["run_id"] + ":") and c.endswith(":a1") for c in res["conv_ids"]))
        # the fake conversations may need no tiny question (the real v4 tracker decides by code first); the store and
        # ask-log path with the real QuestionsV4 is pinned by test_make_answers_hook_real_questions_v4
        self.assertGreater(res["tracker_checks"], 0)
        self.assertEqual(res["answers_with_cid"], res["answers"])                # every tiny answer record
        self.assertEqual(res["answers_with_check"], res["answers"])
        self.assertGreaterEqual(res["asks"], res["answers"])
        self.assertEqual(res["asks_with_cid"], res["asks"])
        self.assertEqual(res["standin_where_checks"], [True])
        for k in ("run_id", "step", "domain", "task", "trial", "arm", "check"):
            self.assertIn(k, res["standin_where_keys"])
        self.assertEqual(res["v4_blocks_first"], ["[]"])         # Conversation.v4_blocks = [] at the first check
        self.assertEqual(res["v4_blocks_missing"], 0)
        self.assertEqual(res["require_freeze"], ["False"])                       # a sandbox never requires it
        self.assertEqual(res["answers_with_where_first"], res["answers"])
        self.assertTrue(res["run_json_has_manifest_key"])
        self.assertEqual(res["calls"]["other"], 0)
        self.assertGreater(res["calls"]["direct"], 0)
        self.assertLessEqual(set(res["network_events"]), {"socket.__new__"})
        self.assertEqual(res["writes_outside"], [])
        # the unit ledger (audit P7 #6): a start and an end per unit, no orphan after a clean run; the step's flock
        self.assertEqual(res["ledger_events"], ["end"] * 4 + ["start"] * 4)
        self.assertEqual(res["ledger_cids"], 4)
        self.assertEqual(res["run_json_live_arms"], list(B1_ARMS))
        self.assertIsNone(res["run_json_baseline"])
        self.assertEqual(res["orphans_after"], 0)
        self.assertTrue(res["step_lock_exists"])


@unittest.skipUnless(os.path.exists(VENV_PY), "τ-bench venv not found")
class TestB1GateInASandbox(unittest.TestCase):
    """audit P7 #2: a sandbox B2v4 / Hv4 run without a passing sandbox B1v4 folder exits before any call."""

    def test_b2_and_h_refused_without_b1(self):
        out = _unique("p7_gate")
        try:
            for step in ("B2v4", "Hv4"):
                rid = R.new_run_id(step)
                argv = ["-m", "guard.run_online_v4", "run", "--step", step, "--run-id", rid, "--shard", "0/6",
                        "--out-root", out, "--approval", "sandbox test, no money"]
                r = subprocess.run([VENV_PY, "-B"] + argv, capture_output=True, text=True, cwd=PC_DIR, timeout=300,
                                   env=ENV)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("starts only after a passing B1v4 run", r.stderr)
                self.assertFalse(os.path.exists(os.path.join(out, step, rid)))
        finally:
            if os.path.exists(out):
                shutil.rmtree(out)


@unittest.skipUnless(os.path.exists(VENV_PY), "τ-bench venv not found")
class TestShardLockAndMovedBackup(unittest.TestCase):

    def test_second_process_and_moved_backup_exit_before_any_call(self):
        out = _unique("p1e_test_lock")
        if os.path.exists(out):
            shutil.rmtree(out)
        try:
            rid = R.new_run_id("B1v4")
            step_dir = os.path.join(out, "B1v4")
            argv = ["-m", "guard.run_online_v4", "run", "--step", "B1v4", "--run-id", rid, "--shard", "0/1",
                    "--task-ids", CHECK_TASKS, "--out-root", out, "--approval", "sandbox test, no money"]
            fd = R.acquire_shard_lock(R.shard_lock_path(step_dir, (0, 1)))
            try:
                r = subprocess.run([VENV_PY, "-B"] + argv, capture_output=True, text=True, cwd=PC_DIR, timeout=300,
                                   env=ENV)
            finally:
                R.release_shard_lock(fd)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("another process runs this shard", r.stderr)
            self.assertFalse(os.path.exists(os.path.join(step_dir, rid)))
            b = os.path.join(step_dir, "B1v4_old", "none", "episodes_shard0of1.jsonl.before_resume")
            os.makedirs(os.path.dirname(b))
            with open(b, "w", encoding="utf-8") as f:
                f.write(json.dumps({"guard": "none", "error": None, "cost": {"agent": 0.01}}) + "\n")
            r = subprocess.run([VENV_PY, "-B"] + argv, capture_output=True, text=True, cwd=PC_DIR, timeout=300,
                               env=ENV)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("copy, never move", r.stderr)
        finally:
            if os.path.exists(out):
                shutil.rmtree(out)


if __name__ == "__main__":
    unittest.main()
