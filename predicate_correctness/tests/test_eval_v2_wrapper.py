"""Eval v2 Part 2: tests of the Stage A wrapper (guard/run_online.py) and the soft stop (guard/soft_stop.py).

No test makes an LLM call:
  - the standard-library tests use fake modules, fake files and a fake judge (guard/offline.py::FakeJudge);
  - the end-to-end tests run the real wrapper main() in a fresh venv process with the network blocked (audit hook)
    and a fake Azure client behind every LLM seam (agent, user simulator, judge). They are skipped if the venv is
    missing. One more test runs the real --dry-run (no fake; the dry run blocks the network itself).
Temporary files go to output/_tmp_test_eval_v2_wrapper/ (removed after each test).
Fix round 1 (F1, output/eval_v2/checks/audit.md): TestTauCopyThreads, TestJobFile, TestWriteGuardV2, the new
refusal cases in TestMainRefusals, test_later_left_usd_in_the_30_dollar_rule, and the e2e tests for the env-build
failure, the 8-worker tracker run, mixed shard counts, --later-left-usd and the total spend in the DONE line.

Run from predicate_correctness/:  python3 -B -m unittest tests.test_eval_v2_wrapper -v
Standard library only.
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import unittest

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from guard import offline, run_online, runner_path, soft_stop            # noqa: E402
from guard.run_online import RunRefused                                  # noqa: E402
from state_tracker import paths, tau_copy                                # noqa: E402
from tests.test_guard import cancel_msg, history                         # noqa: E402

VENV_PY = os.path.expanduser("~/venvs/tau-bench/bin/python")
VENV_TAU = os.path.expanduser("~/venvs/tau-bench/lib/python3.12/site-packages/tau_bench")
TMP_ROOT = os.path.join(paths.OUTPUT_DIR, "_tmp_test_eval_v2_wrapper")
EARLIER_LINE_KEYS = {"attempts", "calls", "cost", "done", "env", "error", "executed", "guard", "latency", "messages",
                     "models", "n_blocks", "n_cap_overrides", "n_exec_steps", "profile", "reward", "reward_info",
                     "seconds", "task_index", "trial", "usage_roles"}


def tmp_dir(name: str) -> str:
    d = os.path.join(TMP_ROOT, f"{name}_{os.getpid()}_{threading.get_ident()}")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    return d


def write_jsonl(path: str, rows, partial: str | None = None) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write((r if isinstance(r, str) else json.dumps(r)) + "\n")
        if partial is not None:
            f.write(partial)


def write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj))


def ep(cost: dict | None = None, error=None, usage=None, **kw) -> dict:
    r = {"task_index": kw.pop("task_index", 0), "trial": kw.pop("trial", 0), "error": error}
    if cost is not None:
        r["cost"] = cost
    if usage is not None:
        r["usage_roles"] = usage
    r.update(kw)
    return r


def count_tasks(path: str, var: str) -> int:
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for st in tree.body:
        if isinstance(st, ast.Assign) and any(isinstance(t, ast.Name) and t.id == var for t in st.targets):
            return len(st.value.elts)
    raise ValueError(var)


class TmpCase(unittest.TestCase):
    def setUp(self):
        self.dirs = []

    def tmp(self, name: str) -> str:
        d = tmp_dir(name)
        self.dirs.append(d)
        return d

    def tearDown(self):
        for d in self.dirs:
            shutil.rmtree(d, ignore_errors=True)
        try:
            os.rmdir(TMP_ROOT)
        except OSError:
            pass


# ================================================================================================ task source

class TestTaskSource(unittest.TestCase):

    def test_all_500_train_tasks(self):
        t = run_online.task_list("retail", run_online.TAU_RETAIL_TRAIN, None)
        self.assertEqual(t, list(range(500)))
        self.assertEqual(run_online.task_split_of(run_online.TAU_RETAIL_TRAIN), "train")
        for s in ("train", "val", "test"):
            self.assertEqual(run_online.task_split_of(s), "test")

    def test_count_matches_tau_bench_task_file(self):
        path = os.path.join(VENV_TAU, "envs", "retail", "tasks_train.py")
        if not os.path.exists(path):
            self.skipTest("τ-bench venv not found")
        self.assertEqual(count_tasks(path, "TASKS_TRAIN"), run_online.TAU_RETAIL_TRAIN_N)

    def test_splits_json_is_not_read_for_the_new_source(self):
        missing = os.path.join(TMP_ROOT, "no_such_splits.json")
        self.assertEqual(len(run_online.task_list("retail", run_online.TAU_RETAIL_TRAIN, None, missing)), 500)
        self.assertEqual(run_online.task_list("retail", run_online.TAU_RETAIL_TRAIN, "1,24,499", missing),
                         [1, 24, 499])

    def test_airline_refused(self):
        with self.assertRaises(RunRefused):
            run_online.task_list("airline", run_online.TAU_RETAIL_TRAIN, None)
        with self.assertRaises(RunRefused):
            run_online.task_list("airline", run_online.TAU_RETAIL_TRAIN, "1,2")

    def test_bad_task_ids_refused(self):
        for ids in ("500", "-1", "1,1", "abc", "0,500", ","):
            with self.assertRaises(RunRefused, msg=ids):
                run_online.task_list("retail", run_online.TAU_RETAIL_TRAIN, ids)

    def test_test_group_still_refused_in_the_earlier_source(self):
        """The earlier behaviour is unchanged: train/val labels of splits.json (test split), test refused."""
        with open(paths.SPLITS_FILE) as f:
            split = json.load(f)
        for env in paths.DOMAINS:
            s = split[env]["split"]
            test_ids = sorted(int(k) for k, v in s.items() if v == "test")
            train = run_online.task_list(env, "train", None)
            self.assertEqual(train, sorted(int(k) for k, v in s.items() if v == "train"))
            self.assertEqual(run_online.task_list(env, "val", None), sorted(int(k) for k, v in s.items() if v == "val"))
            for src in ("test", "dev", "tau_retail_test"):
                with self.assertRaises(RunRefused):
                    run_online.task_list(env, src, None)
            for t in test_ids[:5]:
                for src in ("train", "val", "test"):
                    with self.assertRaises(RunRefused):
                        run_online.task_list(env, src, str(t))
            self.assertEqual(run_online.task_split_of("train"), "test")

    def test_earlier_source_label_checked_with_task_ids(self):
        """F1 item 3 (audit A1 W2): an unknown --tasks label is refused also with --task-ids; a bad id, no id or a
        repeated id is a clean RunRefused (not a ValueError)."""
        with open(paths.SPLITS_FILE) as f:
            s = json.load(f)["retail"]["split"]
        train_id = sorted(int(k) for k, v in s.items() if v == "train")[0]
        for label in ("foo", "test", "dev", ""):
            with self.assertRaises(RunRefused, msg=label):
                run_online.task_list("retail", label, str(train_id))
        for ids in ("2,x", "abc", "1.5", ",", f"{train_id},{train_id}"):
            with self.assertRaises(RunRefused, msg=ids):
                run_online.task_list("retail", "train", ids)
        self.assertEqual(run_online.task_list("retail", "train", str(train_id)), [train_id])   # as before

    def test_new_source_indices_are_train_split(self):
        """Indices that are test-group labels in splits.json are allowed in the new source, because they name
        train-split tasks (task_split "train"), never test-split tasks."""
        with open(paths.SPLITS_FILE) as f:
            s = json.load(f)["retail"]["split"]
        test_ids = sorted(int(k) for k, v in s.items() if v == "test")[:5]
        got = run_online.task_list("retail", run_online.TAU_RETAIL_TRAIN, ",".join(map(str, test_ids)))
        self.assertEqual(got, test_ids)
        self.assertEqual(run_online.task_split_of(run_online.TAU_RETAIL_TRAIN), "train")


# ================================================================================================ units and shards

class TestUnitsAndShards(unittest.TestCase):

    def test_plan_interleaves_and_flips(self):
        tasks = list(range(500))
        u = run_online.plan_units(tasks, 1, run_online.STAGE_A_GUARDS)
        self.assertEqual(len(u), 1000)
        self.assertEqual(len(set(u)), 1000)
        for pos, t in enumerate(tasks):
            pair = u[2 * pos: 2 * pos + 2]
            self.assertEqual({x[0] for x in pair}, {t})
            self.assertEqual({x[2] for x in pair}, set(run_online.STAGE_A_GUARDS))
            self.assertEqual(pair[0][2], run_online.STAGE_A_GUARDS[pos % 2])
        firsts = [u[2 * p][2] for p in range(500)]
        self.assertEqual(firsts.count("tgr_frozen"), 250)

    def test_shards_cover_every_unit_once(self):
        tasks = list(range(500))
        for n in range(1, run_online.MAX_SHARDS + 1):
            u = run_online.plan_units(tasks, 1, run_online.STAGE_A_GUARDS, n)
            self.assertEqual(sorted(u), sorted(run_online.plan_units(tasks, 1, run_online.STAGE_A_GUARDS)))
            parts = [run_online.shard_units(u, tasks, (i, n)) for i in range(n)]
            flat = [x for p in parts for x in p]
            self.assertEqual(sorted(flat), sorted(u), n)
            self.assertEqual(len(flat), len(set(flat)))
            for p in parts:
                for g in run_online.STAGE_A_GUARDS:            # both guards of every task in the same shard
                    self.assertEqual({x[0] for x in p if x[2] == g}, {x[0] for x in p})
                self.assertEqual([x for x in u if x in set(p)], p)   # the run order is kept
            self.assertLessEqual(max(map(len, parts)) - min(map(len, parts)), 2)
            for p in parts:                                    # the first guard alternates inside every shard
                firsts = [p[j][2] for j in range(0, len(p), 2)]
                self.assertEqual(firsts, [run_online.STAGE_A_GUARDS[j % 2] for j in range(len(firsts))], n)

    def test_subset_and_one_guard(self):
        tasks = [1, 24, 30, 88, 99]
        u = run_online.plan_units(tasks, 1, ("tgr_frozen",))
        self.assertEqual(u, [(t, 0, "tgr_frozen") for t in tasks])
        sh = run_online.shard_units(run_online.plan_units(tasks, 1, run_online.STAGE_A_GUARDS), tasks, (1, 2))
        self.assertEqual(sorted({x[0] for x in sh}), [24, 88])

    def test_parse_shard(self):
        self.assertEqual(run_online.parse_shard(None), (0, 1))
        self.assertEqual(run_online.parse_shard("3/4"), (3, 4))
        for bad in ("4/4", "0/0", "1/5", "x", "-1/4", "1/"):
            with self.assertRaises(RunRefused, msg=bad):
                run_online.parse_shard(bad)

    def test_parse_guards(self):
        self.assertEqual(run_online.parse_guards(None, None, True), ("tgr_frozen", "tgr_tracker"))
        self.assertEqual(run_online.parse_guards(None, None, False), ("tgr_tracker",))
        self.assertEqual(run_online.parse_guards("tgr_frozen", None, False), ("tgr_frozen",))
        self.assertEqual(run_online.parse_guards(None, "tgr_tracker,tgr_frozen", True), ("tgr_tracker", "tgr_frozen"))
        for g, gs, sa in ((None, "tgr", True), (None, "tgr_frozen,tgr_frozen", True), (None, "shield", True),
                          (None, "tgr_frozen,tgr_tracker", False)):
            with self.assertRaises(RunRefused):
                run_online.parse_guards(g, gs, sa)

    def test_compact(self):
        self.assertEqual(run_online.compact(list(range(500))), "0-499")
        self.assertEqual(run_online.compact([5, 1, 2, 3, 9]), "1-3,5,9")


# ================================================================================================ paths and caches

class TestStageAPaths(unittest.TestCase):

    def test_layout(self):
        for prof, agent in (("luna-dev", "luna"), ("nano-agent-luna", "nano")):
            p = run_online.resolve_stage_a_paths(prof, run_online.STAGE_A_GUARDS, (2, 4))
            base = os.path.join(paths.OUTPUT_DIR, "eval_v2", "stage_a", agent)
            self.assertEqual(p["agent_dir"], base)
            for g in run_online.STAGE_A_GUARDS:
                self.assertEqual(p["guards"][g]["episodes"], os.path.join(base, g, "episodes_shard2of4.jsonl"))
                self.assertEqual(p["guards"][g]["structured_cache"],
                                 os.path.join(paths.OUTPUT_DIR, "_llmcache", f"v2_stage_a_{agent}", g, "structured"))
            self.assertEqual(p["spend_root"], soft_stop.EVAL_V2_DIR)
            one = run_online.resolve_stage_a_paths(prof, run_online.STAGE_A_GUARDS, (0, 1))
            self.assertEqual(one["guards"]["tgr_frozen"]["episodes"], os.path.join(base, "tgr_frozen", "episodes.jsonl"))
            self.assertTrue(soft_stop.is_episodes_file(os.path.basename(p["guards"]["tgr_frozen"]["episodes"])))
            self.assertFalse(soft_stop.is_episodes_file(os.path.basename(p["lock"])))

    def test_separate_cache_per_guard(self):
        p = run_online.resolve_stage_a_paths("luna-dev", run_online.STAGE_A_GUARDS, (0, 1))
        a, b = (p["guards"][g]["structured_cache"] for g in run_online.STAGE_A_GUARDS)
        self.assertNotEqual(a, b)
        self.assertFalse(a.startswith(b) or b.startswith(a))
        with self.assertRaises(RunRefused):
            run_online.resolve_stage_a_paths("luna-dev", run_online.STAGE_A_GUARDS, (0, 1),
                                             cache_root=os.path.join(soft_stop.EVAL_V2_DIR, "stage_a", "luna"))

    def test_default_tags_never_share_the_stage_a_cache(self):
        self.assertEqual(run_online.default_stage_a_tag(run_online.STAGE_A_DIR, "luna"), "v2_stage_a_luna")
        smoke = os.path.join(soft_stop.EVAL_V2_DIR, "smoke", "stage_a")
        self.assertEqual(run_online.default_stage_a_tag(smoke, "luna"), "v2_smoke_stage_a_luna")
        other = os.path.join(paths.OUTPUT_DIR, "_tmp", "stage_a")
        self.assertNotIn(run_online.default_stage_a_tag(other, "luna"), ("v2_stage_a_luna", "v2_smoke_stage_a_luna"))

    def test_refusals(self):
        g = run_online.STAGE_A_GUARDS
        for kw in ({"out_root": os.path.expanduser("~/ShieldAgent/output")}, {"out_root": PC_DIR},
                   {"cache_root": os.path.join(PC_DIR, "from_shieldagent")},
                   {"out_root": os.path.join(paths.OUTPUT_DIR, "elsewhere")},          # not under the spend root
                   {"spend_root": os.path.expanduser("~")}, {"tag": "../x"}):
            with self.assertRaises(RunRefused, msg=kw):
                run_online.resolve_stage_a_paths("luna-dev", g, (0, 1), **kw)
        ok = run_online.resolve_stage_a_paths("luna-dev", g, (0, 1), out_root=os.path.join(TMP_ROOT, "x", "stage_a"),
                                              spend_root=os.path.join(TMP_ROOT, "x"))
        self.assertTrue(ok["agent_dir"].startswith(TMP_ROOT))

    def test_earlier_paths_unchanged(self):
        p = run_online.resolve_paths("tagx", "retail", "tgr_tracker")
        self.assertEqual(p["episodes"], os.path.join(paths.OUTPUT_DIR, "online", "tagx", "retail", "tgr_tracker",
                                                     "episodes.jsonl"))
        self.assertEqual(p["structured_cache"], os.path.join(paths.OUTPUT_DIR, "_llmcache", "tagx", "structured"))


class _FakeLLM:
    def __init__(self, cache_dir):
        self.cache_dir = cache_dir


class TestJudgeRouter(unittest.TestCase):
    """The router with fake modules (the real seam is checked end to end in TestFakeRunEndToEnd)."""

    def make(self):
        models = type("M", (), {})()
        models.CACHE_ROOT = "/root-of-the-process"
        calls = type("C", (), {})()
        calls._llm = "old"
        calls.structured_llm = lambda raw_dir=None: _FakeLLM(os.path.join(models.CACHE_ROOT, "structured"))
        dirs = {g: os.path.join("/c", g, "structured") for g in run_online.STAGE_A_GUARDS}
        r = run_online.JudgeRouter(dirs)
        r.build(models, calls)
        r.install(calls)
        return r, models, calls, dirs

    def test_each_guard_gets_its_own_llm(self):
        r, models, calls, dirs = self.make()
        self.assertEqual(models.CACHE_ROOT, "/root-of-the-process")          # restored
        self.assertIsNone(calls._llm)
        for g in run_online.STAGE_A_GUARDS:
            with r.use(g):
                self.assertEqual(calls.shared_llm().cache_dir, dirs[g])
        self.assertIsNot(r.llms["tgr_frozen"], r.llms["tgr_tracker"])

    def test_call_outside_a_unit_fails(self):
        r, _, calls, _ = self.make()
        with self.assertRaises(RuntimeError):
            calls.shared_llm()
        r2 = run_online.JudgeRouter({"tgr_frozen": "/c/tgr_frozen/structured"})   # not built (dry run)
        with r2.use("tgr_frozen"):
            with self.assertRaises(RuntimeError):
                r2.route()

    def test_threads_get_their_own_guard(self):
        r, _, calls, dirs = self.make()
        seen, errors = [], []

        def work(g):
            try:
                with r.use(g):
                    for _ in range(200):
                        seen.append((g, calls.shared_llm().cache_dir))
                        time.sleep(0)
            except Exception as e:  # noqa: BLE001
                errors.append(e)
        ts = [threading.Thread(target=work, args=(g,)) for g in run_online.STAGE_A_GUARDS * 4]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(errors, [])
        self.assertTrue(all(d == dirs[g] for g, d in seen))
        self.assertEqual(r.calls, {g: 800 for g in run_online.STAGE_A_GUARDS})

    def test_build_checks_the_folder(self):
        models = type("M", (), {})()
        models.CACHE_ROOT = "/x"
        calls = type("C", (), {})()
        calls.structured_llm = lambda raw_dir=None: _FakeLLM("/somewhere/else")
        r = run_online.JudgeRouter({"tgr_frozen": "/c/tgr_frozen/structured"})
        with self.assertRaises(RuntimeError):
            r.build(models, calls)
        self.assertEqual(models.CACHE_ROOT, "/x")


# ================================================================================================ both guard names

class TestGuardNames(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        runner_path.setup()
        from repro_runtime import calls
        cls.calls = calls
        cls.saved_llm = calls._llm
        cls.tools = tau_copy.tools_info("retail")

    def tearDown(self):
        self.calls._llm = self.saved_llm

    def test_both_names_build(self):
        from repro_online.guards import TGRGuard
        from guard.tgr_tracker import TGRTrackerGuard
        g1, i1 = run_online.build_guard("tgr_frozen", "retail", self.tools)
        g2, i2 = run_online.build_guard("tgr_tracker", "retail", self.tools)
        self.assertIs(type(g1), TGRGuard)                     # the copy's class itself, not a subclass
        self.assertIsInstance(g2, TGRTrackerGuard)
        self.assertEqual(g1.name, "tgr")                       # as the copied runner names it (--guard tgr)
        self.assertEqual((g1.config.judge_effort, g1.config.epsilon, g1.config.actionable_feedback),
                         ("medium", 0.1, True))
        for info in (i1, i2):
            self.assertEqual(info["rules_dir"], os.path.join(paths.RULES_DIR, "retail"))
            self.assertEqual(info["rule_set_sha256"], run_online.FROZEN_RULES_SHA256["retail"])
        self.assertEqual(i1["guard"], "tgr_frozen")
        self.assertEqual(i2["guard"], "tgr_tracker")
        with self.assertRaises(ValueError):
            run_online.build_guard("tgr", "retail", self.tools)
        self.assertEqual(run_online.GUARDS, ("tgr_tracker", "tgr_frozen"))

    def test_frozen_rule_sha(self):
        for env, want in run_online.FROZEN_RULES_SHA256.items():
            self.assertEqual(run_online.sha256_file(paths.rule_set_path(env)), want)

    def test_frozen_rule_check_in_every_mode(self):
        """F1 item 2 (audit A1 W1): tgr_frozen needs the frozen rule set in the earlier mode too; tgr_tracker in
        the earlier mode is not checked (as before); in Stage A every guard is."""
        ok = run_online.FROZEN_RULES_SHA256["retail"]
        P = run_online.frozen_rules_problem
        for stage_a in (True, False):
            self.assertIsNone(P("tgr_frozen", "retail", stage_a, ok))
            self.assertIsNotNone(P("tgr_frozen", "retail", stage_a, "0" * 64))
        self.assertIsNotNone(P("tgr_tracker", "retail", True, "0" * 64))
        self.assertIsNone(P("tgr_tracker", "retail", False, "0" * 64))
        run_online.check_frozen_rules_early(("tgr_frozen", "tgr_tracker"), "retail", False, None)   # default: fine
        run_online.check_frozen_rules_early(("tgr_frozen",), "airline", False, None)

    def test_tgr_frozen_is_plain_tgr(self):
        """With the same (fake) judge answers, tgr_frozen gives what the copied TGR runtime gives, with the same
        judge prompt; and it differs from tgr_tracker where the tracker changes a value (no login)."""
        from method_tgr.runtime import TGR, Conversation, TGRConfig, load_rule_set
        from repro_online.guards import make_step
        g, _ = run_online.build_guard("tgr_frozen", "retail", self.tools)
        tr, _ = run_online.build_guard("tgr_tracker", "retail", self.tools)
        rs = load_rule_set(paths.rule_set_path("retail"))
        negated = {x for r in rs["rules"] if r["id"] in rs["circuits"]["cancel_pending_order"]
                   for x in rs["predicates"] if f"NOT {x}" in r["logic"]}
        execd, msg = history(login=False), cancel_msg()
        idx = sum(m["role"] == "assistant" for m in execd)
        out = {}
        for name, fn in (("frozen", lambda: g.check(g.new_episode(), execd, msg, idx)),
                         ("plain", lambda: TGR(rs, self.tools,
                                               TGRConfig(actionable_feedback=True, judge_effort="medium", epsilon=0.1)
                                               ).step(Conversation(), make_step(execd, msg, idx))),
                         ("tracker", lambda: tr.check(tr.new_episode(), execd, msg, idx))):
            judge = offline.FakeJudge(lambda names: {n: n not in negated for n in names})   # every rule satisfied
            offline.install_fake(judge)
            out[name] = (fn(), judge.calls)
        (f, fc), (p, pc), (t, _) = out["frozen"], out["plain"], out["tracker"]
        for k in ("action_allowed", "margin", "violated_rules", "circuit", "trace_position", "judge"):
            self.assertEqual(f[k], p[k], k)
        self.assertEqual(f.get("feedback_text"), p.get("feedback_text"))
        self.assertEqual([(c["system"], c["user"]) for c in fc], [(c["system"], c["user"]) for c in pc])
        self.assertNotIn("tracker", f)
        self.assertTrue(f["action_allowed"])                   # the judge says the user logged in
        self.assertFalse(t["action_allowed"])                  # the tracker sees no login
        self.assertIn("user_authenticated", t["tracker"]["changed"])


# ================================================================================================ soft stop

class TestSoftStopRule(unittest.TestCase):

    def test_constants(self):
        self.assertEqual((soft_stop.SOFT_STOP_USD, soft_stop.FINISH_IF_LEFT_USD), (100.0, 30.0))
        self.assertEqual(soft_stop.EVAL_V2_DIR, os.path.join(PC_DIR, "output", "eval_v2"))

    def test_decide(self):
        cases = [(0, 1e9, True), (99.99, 1e9, True), (100, 0, True), (100, 30, True), (100, 30.0001, False),
                 (250, 29.99, True), (250, 31, False), (100.0, 1e9, False)]
        for spent, left, want in cases:
            go, reason = soft_stop.decide(spent, left)
            self.assertIs(go, want, (spent, left, reason))
            self.assertIsInstance(reason, str)
            self.assertIn(f"${spent:.2f}", reason)

    def test_gate_is_sticky(self):
        d = tmp_dir("gate")
        try:
            left = {"v": 50.0}
            g = soft_stop.Gate(lambda: left["v"], root=d)
            write_json(os.path.join(d, "stage_b", "f", "A", "0.json"), {"cost_usd": 99.0})
            self.assertTrue(g.check()[0])
            write_json(os.path.join(d, "stage_b", "f", "A", "1.json"), {"cost_usd": 2.0})
            go, reason, spent, lft = g.check()
            self.assertFalse(go)
            self.assertAlmostEqual(spent, 101.0)
            left["v"] = 0.0                                    # would allow now, but the stop is sticky
            self.assertFalse(g.check()[0])
            self.assertEqual(g.stopped["left"], 50.0)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestSpent(TmpCase):

    def build_tree(self, d):
        write_jsonl(os.path.join(d, "stage_a", "luna", "tgr_frozen", "episodes.jsonl"),
                    [ep({"agent": 0.01, "user": 0.002, "guard": 0.003}),
                     ep({"agent": 0.02, "user": 0.0, "guard": 0.01}, task_index=1),
                     ep(None, error="RuntimeError: x", usage={"agent": {"cost": 0.004}, "user": {"cost": 0.001}}),
                     "{not json", "[1, 2]"],
                    partial='{"cost": {"agent": 1000.0}}')         # last line, no newline yet
        write_jsonl(os.path.join(d, "stage_a", "luna", "tgr_tracker", "episodes_shard1of4.jsonl"),
                    [ep({"agent": 0.1, "user": 0.1, "guard": 0.1})])
        write_jsonl(os.path.join(d, "smoke", "stage_a", "luna", "tgr_frozen", "episodes.jsonl"),
                    [ep({"agent": 1.0, "user": 0.0, "guard": 0.0})])
        write_jsonl(os.path.join(d, "stage_a", "luna", "tgr_frozen", "other.jsonl"), [ep({"agent": 500.0})])
        write_json(os.path.join(d, "stage_b", "f1", "A", "0.json"), {"cost_usd": 0.25, "reward": 1})
        write_json(os.path.join(d, "stage_b", "f1", "B", "0.json"), {"cost_usd": 0.5})
        write_json(os.path.join(d, "stage_b", "f1", "B", "1.json"), "{broken")
        write_json(os.path.join(d, "stage_b", "f1", "meta.json"), {"note": "no cost"})
        write_json(os.path.join(d, "smoke", "stage_b", "f9", "A", "0.json"), {"cost_usd": 2.0})
        write_json(os.path.join(d, "checks", "x.json"), {"cost_usd": 700.0})       # not under stage_b: ignored

    def test_spent_usd_on_fake_files(self):
        d = self.tmp("spent")
        self.build_tree(d)
        want_ep = 0.015 + 0.03 + 0.005 + 0.3 + 1.0 + 1000.0        # the last line without newline is read in a full scan
        want_b = 0.25 + 0.5 + 2.0
        self.assertAlmostEqual(soft_stop.spent_usd(d), want_ep + want_b, places=9)
        rep = soft_stop.spent_report(d)
        self.assertAlmostEqual(rep["episodes_usd"], want_ep, places=9)
        self.assertAlmostEqual(rep["stage_b_usd"], want_b, places=9)
        self.assertEqual(rep["episode_files"], 3)
        self.assertEqual(rep["error_lines"], 1)
        self.assertAlmostEqual(rep["error_lines_usd"], 0.005)
        self.assertEqual(rep["stage_b_files"], 5)
        self.assertEqual(rep["no_cost_usd"], [os.path.join("stage_b", "f1", "meta.json")])
        bad = sorted((b["path"], b["line"]) for b in rep["unreadable"])
        self.assertEqual(bad, [(os.path.join("stage_a", "luna", "tgr_frozen", "episodes.jsonl"), 4),
                               (os.path.join("stage_a", "luna", "tgr_frozen", "episodes.jsonl"), 5),
                               (os.path.join("stage_b", "f1", "B", "1.json"), None)])

    def test_bad_partial_last_line_is_listed(self):
        d = self.tmp("partial")
        write_jsonl(os.path.join(d, "x", "episodes.jsonl"), [ep({"agent": 1.0})], partial='{"cost": {"ag')
        rep = soft_stop.spent_report(d)
        self.assertAlmostEqual(rep["total_usd"], 1.0)
        self.assertEqual([b["line"] for b in rep["unreadable"]], [2])

    def test_empty_and_missing_root(self):
        self.assertEqual(soft_stop.spent_usd(os.path.join(TMP_ROOT, "nothing_here")), 0.0)
        d = self.tmp("empty")
        self.assertEqual(soft_stop.spent_usd(d), 0.0)
        self.assertIsInstance(soft_stop.spent_usd(d), float)

    def test_incremental_scanner(self):
        d = self.tmp("incr")
        f = os.path.join(d, "a", "episodes.jsonl")
        write_jsonl(f, [ep({"agent": 1.0})], partial='{"cost": {"agent": 2.0}')
        sc = soft_stop.SpendScanner(d)
        self.assertAlmostEqual(sc.total(), 1.0)                 # the line being written is held back
        with open(f, "a") as fh:
            fh.write('}\n')
        self.assertAlmostEqual(sc.total(), 3.0)
        write_jsonl(f, [ep({"guard": 0.5})])
        self.assertAlmostEqual(sc.total(), 3.5)
        self.assertAlmostEqual(sc.total(), 3.5)                 # nothing new: same total
        write_json(os.path.join(d, "stage_b", "x", "A", "0.json"), {"cost_usd": 1.0})
        self.assertAlmostEqual(sc.total(), 4.5)
        write_json(os.path.join(d, "stage_b", "x", "A", "0.json"), {"cost_usd": 1.25, "pad": "xxxxx"})
        self.assertAlmostEqual(sc.total(), 4.75)                # a changed try file is read again
        tmp = f + ".new"
        write_jsonl(tmp, [ep({"agent": 0.25})])
        os.replace(tmp, f)                                      # replaced: counted again from the start, once
        self.assertAlmostEqual(sc.total(), 0.25 + 1.25)
        os.remove(f)
        self.assertAlmostEqual(sc.total(), 1.25)
        self.assertAlmostEqual(soft_stop.spent_usd(d), 1.25)

    def test_line_cost(self):
        self.assertAlmostEqual(soft_stop.line_cost({"cost": {"agent": 0.1, "user": 0.2, "guard": 0.3}}), 0.6)
        self.assertAlmostEqual(soft_stop.line_cost({"error": "x", "usage_roles": {"agent": {"cost": 0.1},
                                                                                  "user": {"cost": 0.05}}}), 0.15)
        self.assertEqual(soft_stop.line_cost({"cost": {"agent": "a", "user": None, "guard": True}}), 0.0)
        self.assertEqual(soft_stop.line_cost([1]), 0.0)
        self.assertEqual(soft_stop.line_cost({}), 0.0)

    def test_same_as_the_p10_cost_tables(self):
        """On our earlier runs, the spend equals the sum of cost_of (p10 runs check script) over all lines."""
        root = os.path.join(paths.OUTPUT_DIR, "online", "p10_luna_val")
        if not os.path.isdir(root):
            self.skipTest("no p10 run")
        want = 0.0
        for dirpath, _, files in os.walk(root):
            for name in files:
                if soft_stop.is_episodes_file(name):
                    with open(os.path.join(dirpath, name), encoding="utf-8") as f:
                        for line in f:
                            want += sum((json.loads(line).get("cost") or {}).values())
        self.assertGreater(want, 0)
        self.assertAlmostEqual(soft_stop.spent_usd(root), want, places=9)


class TestJobProgress(TmpCase):

    def test_done_units_across_shard_files(self):
        d = self.tmp("prog")
        exp = {"profile": "luna-dev", "env": "retail", "task_split": "train"}
        dirs = {g: os.path.join(d, g) for g in run_online.STAGE_A_GUARDS}
        keys = {(g, t, 0) for g in dirs for t in range(5)}
        line = lambda g, t, err=None, c=1.0: dict(exp, guard=g, task_index=t, trial=0, error=err,   # noqa: E731
                                                  cost={"agent": c})
        write_jsonl(os.path.join(dirs["tgr_frozen"], "episodes_shard0of2.jsonl"),
                    [line("tgr_frozen", 0), line("tgr_frozen", 1, err="E"), line("tgr_frozen", 2, c=3.0)])
        write_jsonl(os.path.join(dirs["tgr_frozen"], "episodes_shard1of2.jsonl"), [line("tgr_frozen", 0, c=9.0)])
        write_jsonl(os.path.join(dirs["tgr_tracker"], "episodes.jsonl"), [line("tgr_tracker", 3)])
        pr = run_online.JobProgress(dirs, keys, exp, prior_usd=0.5)
        pr.update()
        self.assertEqual(pr.problems, [])
        self.assertEqual(set(pr.done()), {("tgr_frozen", 0, 0), ("tgr_frozen", 2, 0), ("tgr_tracker", 3, 0)})
        self.assertEqual(pr.error_lines, 1)
        usd, left, mean = pr.left_estimate(running_here=2)
        self.assertEqual(left, 10 - 3 - 2)
        self.assertEqual(len(pr.done()), 3)
        self.assertAlmostEqual(mean, (1.0 + 3.0 + 1.0) / 3)    # first good line per unit (files in name order)
        self.assertAlmostEqual(usd, left * mean)
        self.assertEqual(run_online.JobProgress(dirs, set(), exp, 0.5).mean_cost(), 0.5)

    def test_foreign_lines_are_problems(self):
        d = self.tmp("foreign")
        exp = {"profile": "luna-dev", "env": "retail", "task_split": "train"}
        dirs = {"tgr_frozen": os.path.join(d, "tgr_frozen")}
        for bad in ({"profile": "nano-agent-luna"}, {"task_split": "test"}, {"guard": "tgr_tracker"}):
            shutil.rmtree(dirs["tgr_frozen"], ignore_errors=True)
            row = dict(exp, guard="tgr_frozen", task_index=0, trial=0, error=None, cost={})
            row.update(bad)
            write_jsonl(os.path.join(dirs["tgr_frozen"], "episodes.jsonl"), [row])
            pr = run_online.JobProgress(dirs, {("tgr_frozen", 0, 0)}, exp, 0.5)
            pr.update()
            self.assertEqual(len(pr.problems), 1, bad)
            self.assertEqual(pr.done(), {})


class TestRunUnitsSoftStop(TmpCase):
    """The scheduling loop with a fake unit runner (no LLM): it writes one line with a fixed cost per unit."""

    def fake_job(self, d, n_tasks, unit_cost, spent_before, workers=1, prior=1.0):
        guards = run_online.STAGE_A_GUARDS
        tasks = list(range(n_tasks))
        units = run_online.plan_units(tasks, 1, guards)
        write_json(os.path.join(d, "stage_b", "f", "A", "0.json"), {"cost_usd": spent_before})
        dirs = {g: os.path.join(d, "stage_a", "luna", g) for g in guards}
        exp = {"profile": "luna-dev", "env": "retail", "task_split": "train"}
        prog = run_online.JobProgress(dirs, {(g, t, k) for t, k, g in units}, exp, prior)
        live, ran, stops = {}, [], []
        lock = threading.Lock()

        def run_one(u):
            t, k, g = u
            with lock:
                ran.append(u)
            write_jsonl(os.path.join(dirs[g], "episodes.jsonl"),
                        [dict(exp, guard=g, task_index=t, trial=k, error=None,
                              cost={"agent": unit_cost, "user": 0.0, "guard": 0.0})])
            return {"guard": g, "task_index": t, "trial": k}
        gate = soft_stop.Gate(lambda: prog.left_estimate(live.get("running", 0))[0], root=d)
        st = run_online.run_units(units, run_one, workers, gate, None, lambda *a: stops.append(a), state=live)
        return st, ran, stops, units

    def test_stops_when_left_is_over_30(self):
        d = self.tmp("stop")
        st, ran, stops, units = self.fake_job(d, 6, unit_cost=5.0, spent_before=99.0)
        self.assertEqual(ran, units[:1])                        # 99 < 100: the first unit runs; then 104 and 11 x 5 = 55
        self.assertEqual((st["started"], st["finished"], st["not_started"], st["running"]), (1, 1, 11, 0))
        self.assertEqual(len(stops), 1)
        reason, spent, left = stops[0]
        self.assertAlmostEqual(spent, 104.0)
        self.assertAlmostEqual(left, 55.0)
        self.assertIn("> $30.00", reason)

    def test_finishes_when_left_is_30_or_less(self):
        d = self.tmp("finish")
        st, ran, stops, units = self.fake_job(d, 3, unit_cost=5.0, spent_before=99.0)
        self.assertEqual(ran, units)                            # after the first: 104 spent, 5 x 5 = 25 <= 30 left
        self.assertEqual((st["started"], st["not_started"]), (6, 0))
        self.assertEqual(stops, [])
        self.assertAlmostEqual(soft_stop.spent_usd(d), 99.0 + 30.0)

    def test_no_stop_under_100(self):
        d = self.tmp("under")
        st, ran, stops, units = self.fake_job(d, 5, unit_cost=1.0, spent_before=10.0, workers=3)
        self.assertEqual(sorted(ran), sorted(units))
        self.assertEqual(stops, [])

    def fake_job_later(self, d, later):
        """As test_finishes_when_left_is_30_or_less, with --later-left-usd `later` in the left estimate."""
        guards = run_online.STAGE_A_GUARDS
        units = run_online.plan_units([0, 1, 2], 1, guards)
        write_json(os.path.join(d, "stage_b", "f", "A", "0.json"), {"cost_usd": 99.0})
        dirs = {g: os.path.join(d, "stage_a", "luna", g) for g in guards}
        exp = {"profile": "luna-dev", "env": "retail", "task_split": "train"}
        prog = run_online.JobProgress(dirs, {(g, t, k) for t, k, g in units}, exp, 1.0)
        live, stops = {}, []

        def run_one(u):
            t, k, g = u
            write_jsonl(os.path.join(dirs[g], "episodes.jsonl"),
                        [dict(exp, guard=g, task_index=t, trial=k, error=None, cost={"agent": 5.0})])
            return {"guard": g, "task_index": t, "trial": k}
        gate = soft_stop.Gate(lambda: run_online.stage_a_left_usd(prog, live.get("running", 0), later), root=d)
        st = run_online.run_units(units, run_one, 1, gate, None, lambda *a: stops.append(a), state=live)
        return st, stops

    def test_later_left_usd_in_the_30_dollar_rule(self):
        """F1 item 7: after the first unit, spent $104 and this job's left is 5 x $5 = $25. With $5 of later jobs
        the left is $30: finish. With $5.01: $30.01 > $30: stop."""
        st, stops = self.fake_job_later(self.tmp("later_ok"), 5.0)
        self.assertEqual((st["started"], st["not_started"]), (6, 0))
        self.assertEqual(stops, [])
        st, stops = self.fake_job_later(self.tmp("later_stop"), 5.01)
        self.assertEqual((st["started"], st["not_started"]), (1, 5))
        self.assertEqual(len(stops), 1)
        self.assertAlmostEqual(stops[0][2], 25.0 + 5.01)
        self.assertIn("$30.01 > $30.00", stops[0][0])

    def test_running_units_finish_after_a_stop(self):
        """Several workers: units already running when the stop comes are finished and written."""
        d = self.tmp("running")
        st, ran, stops, units = self.fake_job(d, 20, unit_cost=50.0, spent_before=99.0, workers=4)
        self.assertEqual(len(stops), 1)
        self.assertEqual(st["started"], st["finished"])
        self.assertEqual(st["started"] + st["not_started"], len(units))
        self.assertGreaterEqual(st["started"], 1)
        self.assertLess(st["started"], len(units))
        n_lines = 0
        for dirpath, _, fs in os.walk(os.path.join(d, "stage_a")):
            for f in fs:
                with open(os.path.join(dirpath, f), encoding="utf-8") as fh:
                    n_lines += sum(1 for _ in fh)
        self.assertEqual(n_lines, st["started"])


# ================================================================================================ the job file

class TestJobFile(TmpCase):
    """F1 item 4 (audit A2 W3): one shard count n per Stage A job (agent folder)."""

    def want(self, n, tasks=(1, 2, 3, 4)):
        return run_online.job_identity(n, list(tasks), run_online.STAGE_A_GUARDS, "luna-dev", "retail", "train")

    def test_first_process_writes_it_and_same_n_joins(self):
        d = os.path.join(self.tmp("job_same"), "luna")
        self.assertIsNone(run_online.read_job_file(d))
        self.assertEqual(run_online.job_problems(d, self.want(4)), [])
        e = run_online.ensure_job_file(d, self.want(4))
        self.assertEqual((e["created"], e["n_shards"]), (True, 4))
        job = run_online.read_job_file(d)
        self.assertEqual({k: job[k] for k in self.want(4)}, self.want(4))
        self.assertEqual(sorted(os.listdir(d)), [run_online.JOB_FILE])          # no temporary file left
        e2 = run_online.ensure_job_file(d, self.want(4))                        # a later process with the same n
        self.assertFalse(e2["created"])
        write_jsonl(os.path.join(d, "tgr_frozen", "episodes_shard2of4.jsonl"), ["{}"])
        self.assertEqual(run_online.job_problems(d, self.want(4)), [])

    def test_other_n_refused_both_ways(self):
        for first, later in ((4, 1), (1, 4), (4, 2), (2, 3)):
            d = os.path.join(self.tmp(f"job_{first}_{later}"), "luna")
            run_online.ensure_job_file(d, self.want(first))
            probs = run_online.job_problems(d, self.want(later))
            self.assertEqual(len(probs), 1, (first, later, probs))
            self.assertIn("no --shard" if first == 1 else f"--shard i/{first}", probs[0])
            with self.assertRaises(RunRefused):
                run_online.ensure_job_file(d, self.want(later))

    def test_episode_files_of_another_n_refused_without_a_job_file(self):
        for name, n_ok in (("episodes_shard0of2.jsonl", 2), ("episodes.jsonl", 1)):
            d = os.path.join(self.tmp("job_files"), "luna")
            write_jsonl(os.path.join(d, "tgr_tracker", name), ["{}"])
            write_jsonl(os.path.join(d, "tgr_tracker", "episodes_old_copy.jsonl"), ["{}"])   # not a job file name
            self.assertEqual(run_online.job_problems(d, self.want(n_ok)), [])
            for n in {1, 2, 4} - {n_ok}:
                self.assertEqual(len(run_online.job_problems(d, self.want(n))), 1, (name, n))
            shutil.rmtree(d)

    def test_task_list_must_match_when_sharded(self):
        d = os.path.join(self.tmp("job_tasks"), "luna")
        run_online.ensure_job_file(d, self.want(4, tasks=range(500)))
        self.assertEqual(len(run_online.job_problems(d, self.want(4, tasks=[1, 24, 30]))), 1)
        self.assertEqual(run_online.job_problems(d, self.want(4, tasks=range(500))), [])
        d1 = os.path.join(self.tmp("job_tasks1"), "luna")
        run_online.ensure_job_file(d1, self.want(1, tasks=[1, 2]))
        self.assertEqual(run_online.job_problems(d1, self.want(1, tasks=[3])), [])   # one process: no overlap

    def test_bad_job_file_refused(self):
        d = os.path.join(self.tmp("job_bad"), "luna")
        write_json(os.path.join(d, run_online.JOB_FILE), "{broken")
        with self.assertRaises(RunRefused):
            run_online.read_job_file(d)
        write_json(os.path.join(d, run_online.JOB_FILE), {"note": "no n"})
        with self.assertRaises(RunRefused):
            run_online.job_problems(d, self.want(4))

    def test_two_processes_starting_at_once(self):
        """Two starts with different n at the same moment: exactly one wins, the other is refused."""
        for k in range(20):
            d = os.path.join(self.tmp(f"job_race{k}"), "luna")
            barrier = threading.Barrier(2)
            res = {}

            def start(n):
                barrier.wait()
                try:
                    run_online.ensure_job_file(d, self.want(n))
                    res[n] = "ok"
                except RunRefused:
                    res[n] = "refused"
            ts = [threading.Thread(target=start, args=(n,)) for n in (1, 4)]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
            self.assertEqual(sorted(res.values()), ["ok", "refused"], res)
            self.assertEqual(run_online.read_job_file(d)["n_shards"], [n for n, v in res.items() if v == "ok"][0])


# ================================================================================================ write guard

_WRITE_GUARD_PROBE_V2 = r"""
import glob, json, os, shutil, sys
sys.dont_write_bytecode = True
pc, tmp = sys.argv[1], sys.argv[2]
sys.path.insert(0, pc)
from guard import write_guard
write_guard.install()
shield = os.path.expanduser("~/ShieldAgent")
res = {}
def attempt(name, fn):
    try:
        fn()
        res[name] = "allowed"
    except PermissionError as e:
        res[name] = "refused" if "write guard" in str(e) else "PermissionError (not the guard)"
    except Exception as e:  # noqa: BLE001
        res[name] = type(e).__name__
tree = os.path.join(tmp, "tree")
os.makedirs(os.path.join(tree, "a", "b"))
for p in ("a/x.txt", "a/b/y.txt", "z.txt"):
    open(os.path.join(tree, p), "w").close()
attempt("rmtree_inside_output", lambda: shutil.rmtree(tree))
res["tree_gone"] = not os.path.exists(tree)
os.makedirs(os.path.join(tmp, "d"))
fd_out = os.open(os.path.join(tmp, "d"), os.O_RDONLY)
attempt("mkdir_dir_fd_inside_output", lambda: os.mkdir("m", dir_fd=fd_out))
attempt("rename_dir_fd_inside_output", lambda: os.rename("m", "m2", src_dir_fd=fd_out, dst_dir_fd=fd_out))
attempt("rmdir_dir_fd_inside_output", lambda: os.rmdir("m2", dir_fd=fd_out))
fd_pc = os.open(pc, os.O_RDONLY)
os.chdir(tmp)            # the current folder is inside output/: a guard that ignores dir_fd would allow the next ones
attempt("remove_dir_fd_outside_output", lambda: os.remove("_f1_no_such_file.txt", dir_fd=fd_pc))
attempt("mkdir_dir_fd_outside_output", lambda: os.mkdir("_f1_probe_dir", dir_fd=fd_pc))
res["probe_dir_exists"] = os.path.exists(os.path.join(pc, "_f1_probe_dir"))
attempt("rename_into_pc_with_dir_fd", lambda: os.rename("nope", "nope2", src_dir_fd=fd_out, dst_dir_fd=fd_pc))
attempt("listdir_output", lambda: os.listdir(tmp))
attempt("listdir_shieldagent", lambda: os.listdir(shield))
attempt("scandir_shieldagent", lambda: list(os.scandir(shield)))
attempt("walk_shieldagent", lambda: next(os.walk(shield)))
attempt("glob_shieldagent", lambda: glob.glob(os.path.join(shield, "*")))
attempt("open_read_shieldagent", lambda: open(os.path.join(shield, "README.md")).close())
attempt("stat_shieldagent (no audit event)", lambda: os.stat(shield))
os.chdir(pc)
os.close(fd_out)
os.close(fd_pc)
shutil.rmtree(os.path.join(tmp, "d"))
res["refused"] = len(write_guard.REFUSED)
print(json.dumps(res))
"""


class TestWriteGuardV2(TmpCase):
    """F1 item 8: dir_fd-relative paths (shutil.rmtree inside output/ works; outside is refused), and folder
    listings under ~/ShieldAgent are refused. Every refused probe is refused by the hook before the system call."""

    def test_in_a_fresh_process(self):
        d = self.tmp("wg")
        r = subprocess.run([sys.executable, "-B", "-c", _WRITE_GUARD_PROBE_V2, PC_DIR, d], capture_output=True,
                           text=True, cwd=PC_DIR, timeout=120)
        probe_dir = os.path.join(PC_DIR, "_f1_probe_dir")
        if os.path.isdir(probe_dir):                       # only if the guard failed
            os.rmdir(probe_dir)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        res = json.loads(r.stdout.strip().splitlines()[-1])
        want = {"rmtree_inside_output": "allowed", "tree_gone": True,
                "mkdir_dir_fd_inside_output": "allowed", "rename_dir_fd_inside_output": "allowed",
                "rmdir_dir_fd_inside_output": "allowed",
                "remove_dir_fd_outside_output": "refused", "mkdir_dir_fd_outside_output": "refused",
                "probe_dir_exists": False, "rename_into_pc_with_dir_fd": "refused", "listdir_output": "allowed",
                "listdir_shieldagent": "refused", "scandir_shieldagent": "refused", "walk_shieldagent": "refused",
                "glob_shieldagent": "refused", "open_read_shieldagent": "refused",
                "stat_shieldagent (no audit event)": "allowed"}
        if not os.path.isdir(os.path.expanduser("~/ShieldAgent")):
            self.skipTest("~/ShieldAgent not found")
        self.assertEqual({k: res.get(k) for k in want}, want)
        self.assertEqual(res["refused"], sum(v == "refused" for v in want.values()))


# ================================================================================================ tau_copy threads

_RACE_PROBE = r"""
import json, sys, threading
sys.dont_write_bytecode = True
def _no_net(event, args):
    if event.startswith("socket."):
        raise PermissionError("network blocked in this test")
sys.addaudithook(_no_net)
sys.path.insert(0, sys.argv[1])
if sys.argv[2] == "real":
    import tau_bench.envs  # noqa: F401  (as in the wrapper: the real package is imported before the workers)
from state_tracker import tau_copy
n = int(sys.argv[3])
barrier = threading.Barrier(n)
errors, seen, lock = [], {}, threading.Lock()
def work(i):
    d = ("retail", "airline")[i % 2]
    barrier.wait()
    try:
        t = tau_copy.tools(d)
        info = tau_copy.tools_info(d)
        data = tau_copy.load_data_fresh(d) if i < 4 else None
        with lock:
            seen.setdefault(d, set()).add(id(t))
            seen.setdefault(d + "_n", set()).add((len(t), len(info)))
            if data is not None:
                seen.setdefault(d + "_data", set()).add(tuple(sorted(data)))
    except Exception as e:  # noqa: BLE001
        with lock:
            errors.append(f"{type(e).__name__}: {e}"[:200])
ts = [threading.Thread(target=work, args=(i,)) for i in range(n)]
for t in ts:
    t.start()
for t in ts:
    t.join()
print(json.dumps({"errors": errors, "seen": {k: sorted(map(str, v)) for k, v in seen.items()},
                  "tau_bench_loaded": "tau_bench" in sys.modules,
                  "tau_bench_real": getattr(sys.modules.get("tau_bench"), "__file__", None) is not None}))
"""


class TestTauCopyThreads(unittest.TestCase):
    """F1 item 1 (audit A2 blocker): many threads load the copied τ-bench tools at once, from a fresh process. Before
    the fix, a thread could get the half-loaded module ("no attribute 'ALL_TOOLS'")."""

    N_THREADS = 16
    N_PROCESSES = 6

    def run_probe(self, python, mode):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", LITELLM_LOCAL_MODEL_COST_MAP="True")
        outs = []
        for _ in range(self.N_PROCESSES):
            r = subprocess.run([python, "-B", "-c", _RACE_PROBE, PC_DIR, mode, str(self.N_THREADS)],
                               capture_output=True, text=True, cwd=PC_DIR, timeout=300, env=env)
            self.assertEqual(r.returncode, 0, r.stderr[-3000:])
            outs.append(json.loads(r.stdout.strip().splitlines()[-1]))
        return outs

    def check(self, outs, real):
        for o in outs:
            self.assertEqual(o["errors"], [])
            for d in paths.DOMAINS:
                self.assertEqual(len(o["seen"][d]), 1, o)              # every thread got the same table object
                self.assertEqual(len(o["seen"][d + "_n"]), 1, o)
                self.assertEqual(len(o["seen"][d + "_data"]), 1, o)
            self.assertEqual(o["tau_bench_loaded"], real)               # stdlib: the empty packages were removed
            self.assertEqual(o["tau_bench_real"], real)

    def test_threads_stdlib_python(self):
        self.check(self.run_probe(sys.executable, "stdlib"), real=False)

    @unittest.skipUnless(os.path.exists(VENV_PY), "τ-bench venv not found")
    def test_threads_with_real_tau_bench(self):
        self.check(self.run_probe(VENV_PY, "real"), real=True)


# ================================================================================================ main() refusals

_REFUSAL_PROBE = r"""
import json, sys
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
from guard import run_online, write_guard
out = []
for argv in json.loads(sys.argv[2]):
    try:
        run_online.main(argv)
        out.append({"argv": argv, "result": "RAN"})
    except SystemExit as e:
        out.append({"argv": argv, "result": "refused", "msg": str(e), "is_RunRefused": isinstance(e, run_online.RunRefused)})
out.append({"write_guard": write_guard.installed(),
            "runner_imported": any(m.split(".")[0] in ("exp_core", "repro_online", "tau_bench", "method_tgr")
                                   for m in sys.modules)})
print(json.dumps(out))
"""


class TestMainRefusals(TmpCase):
    """main() refuses before any runner import (standard-library Python: the runner is never reached)."""

    def make_fixtures(self):
        """A rules folder whose rule_set.json differs from the frozen one by one byte; Stage A agent folders with a
        job file of n = 4, and with episode files of n = 2."""
        d = self.tmp("refusals")
        rules = os.path.join(d, "rules", "retail")
        os.makedirs(rules)
        for name in ("rule_set.json", "manifest.json"):
            shutil.copyfile(os.path.join(paths.RULES_DIR, "retail", name), os.path.join(rules, name))
        with open(os.path.join(rules, "rule_set.json"), "a", encoding="utf-8") as f:
            f.write("\n")
        job4 = os.path.join(d, "job4")
        run_online.ensure_job_file(os.path.join(job4, "stage_a", "luna"), run_online.job_identity(
            4, list(range(500)), run_online.STAGE_A_GUARDS, "luna-dev", "retail", "train"))
        files2 = os.path.join(d, "files2")
        write_jsonl(os.path.join(files2, "stage_a", "luna", "tgr_frozen", "episodes_shard1of2.jsonl"), [])
        stage = lambda root: ["--out-root", os.path.join(root, "stage_a"), "--spend-root", root]   # noqa: E731
        return rules, stage(job4), stage(files2)

    def test_refusals_before_runner_import(self):
        base = ["--profile", "luna-dev", "--env", "retail", "--dry-run"]
        with open(paths.SPLITS_FILE) as f:
            split = json.load(f)["retail"]["split"]
        test_ids = sorted(int(k) for k, v in split.items() if v == "test")
        train_id = str(sorted(int(k) for k, v in split.items() if v == "train")[0])
        rules, job4, files2 = self.make_fixtures()
        sa = base + ["--tasks", "tau_retail_train"]
        cases = [
            # F1 items 2, 3, 4, 7 (fix round 1)
            base + ["--tasks", "train", "--tag", "x", "--guard", "tgr_frozen", "--rules-dir", rules],
            sa + ["--rules-dir", rules],
            sa + ["--guards", "tgr_tracker", "--rules-dir", rules],
            base + ["--tasks", "foo", "--task-ids", train_id, "--tag", "x"],
            base + ["--tasks", "test", "--task-ids", train_id, "--tag", "x"],
            base + ["--tasks", "train", "--task-ids", f"{train_id},x", "--tag", "x"],
            base + ["--tasks", "train", "--task-ids", f"{train_id},{train_id}", "--tag", "x"],
            sa + job4,                                                             # no --shard; the job has n = 4
            sa + job4 + ["--shard", "0/2"],
            sa + files2 + ["--shard", "0/4"],
            sa + files2,
            sa + ["--later-left-usd", "-1"],
            sa + ["--later-left-usd", "nan"],
            sa + ["--later-left-usd", "inf"],
            base + ["--tasks", "train", "--tag", "x", "--later-left-usd", "5"],
            # earlier cases

            ["--profile", "luna-dev", "--env", "airline", "--tasks", "tau_retail_train", "--dry-run"],
            base + ["--tasks", "test", "--tag", "x"],
            base + ["--tasks", "train", "--task-ids", ",".join(map(str, test_ids[:3])), "--tag", "x"],
            base + ["--tasks", "val", "--task-ids", str(test_ids[-1]), "--tag", "x"],
            base + ["--tasks", "tau_retail_train", "--trials", "3"],
            base + ["--tasks", "tau_retail_train", "--shard", "4/4"],
            base + ["--tasks", "tau_retail_train", "--guards", "tgr,tgr_tracker"],
            base + ["--tasks", "tau_retail_train", "--task-ids", "500"],
            base + ["--tasks", "tau_retail_train", "--out-root", "/tmp/stage_a"],
            base + ["--tasks", "train"],                                           # no --tag
            base + ["--tasks", "train", "--tag", "x", "--shard", "0/2"],
            base + ["--tasks", "train", "--tag", "x", "--guards", "tgr_frozen,tgr_tracker"],
        ]
        r = subprocess.run([sys.executable, "-B", "-c", _REFUSAL_PROBE, PC_DIR, json.dumps(cases)],
                           capture_output=True, text=True, cwd=PC_DIR, timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        out = json.loads(r.stdout.strip().splitlines()[-1])
        for x in out[:-1]:
            self.assertEqual(x["result"], "refused", x)
            self.assertTrue(x["is_RunRefused"], x)
        self.assertEqual(out[-1], {"write_guard": True, "runner_imported": False})

    def test_argparse_refuses_grok(self):
        with self.assertRaises(SystemExit):
            run_online.main(["--profile", "grok-eval", "--env", "retail", "--tasks", "tau_retail_train"])


# ================================================================================================ end to end (venv)

_FAKE_RUN_DRIVER = r'''
import contextlib, hashlib, io, json, os, sys, types
sys.dont_write_bytecode = True
pc, cfg_path = sys.argv[1], sys.argv[2]
sys.path.insert(0, pc)
cfg = json.load(open(cfg_path))
NET = []
def _no_net(event, args):
    if event in ("socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyname_ex",
                 "socket.gethostbyaddr", "socket.sendto"):
        NET.append(event)
        raise PermissionError("network blocked in this test")
sys.addaudithook(_no_net)
from guard import runner_path, run_online
runner_path.setup()
from exp_core import models

O = types.SimpleNamespace
LOG = {"judge": 0, "agent": 0, "user": 0, "instructions": [], "judge_users": []}
PLAN = {"agent": "cancel", "fail_env": set(), "judge": "all_true"}
_NEG = []

def negated():
    """Predicates that some retail rule uses as NOT x (the judge says false for them under "satisfy")."""
    if not _NEG:
        with open(os.path.join(pc, "from_shieldagent", "rules", "retail", "rule_set.json"), encoding="utf-8") as f:
            rs = json.load(f)
        _NEG.append({n for r in rs["rules"] for n in rs["predicates"] if f"NOT {n}" in r.get("logic", "")})
    return _NEG[0]
TOK = {"in": 1000, "out": 100}

def usage():
    return O(input_tokens=TOK["in"], output_tokens=TOK["out"], output_tokens_details=O(reasoning_tokens=0),
             input_tokens_details=O(cached_tokens=0))

class Resp:
    def __init__(self, output_text, output=()):
        self.output_text, self.output, self.usage = output_text, list(output), usage()
    def model_dump(self, mode=None, **_):
        return {"output_text": self.output_text, "fake": True}

def predicates_in(user):
    start = user.rfind("\nPredicates to decide:\n")
    end = user.find("\n\nFor every predicate return", start)
    if start < 0 or end < 0:
        return []
    return [l[2:].split(":", 1)[0].strip() for l in user[start:end].splitlines()[2:] if l.startswith("- ") and ":" in l]

class Responses:
    def create(self, **kw):
        items = kw.get("input") or []
        if "text" in kw:                                    # TGR judge (structured output)
            LOG["judge"] += 1
            user = items[1]["content"]
            LOG["judge_users"].append(hashlib.sha256(user.encode()).hexdigest()[:16])
            neg = negated() if PLAN["judge"] == "satisfy" else set()   # "satisfy": every rule holds
            preds = [{"name": n, "value": "false" if n in neg else "true", "evidence": "fake"}
                     for n in predicates_in(user)]
            return Resp(json.dumps({"predicates": preds}))
        if kw.get("tools"):                                  # the agent
            LOG["agent"] += 1
            n_fc = sum(1 for i in items if i.get("type") == "function_call")
            if PLAN["agent"] == "tool2" and n_fc == 0:      # a read call first: the next check replays it
                fc = O(type="function_call", call_id=f"call_r{LOG['agent']}", name="find_user_id_by_email",
                       arguments=json.dumps({"email": "nobody@example.com"}))
                return Resp("", [fc])
            if n_fc >= (2 if PLAN["agent"] == "tool2" else 1):
                return Resp("Your request is handled. Anything else?", [O(type="message")])
            fc = O(type="function_call", call_id=f"call_{LOG['agent']}", name="cancel_pending_order",
                   arguments=json.dumps({"order_id": "#W0000000", "reason": "no longer needed"}))
            return Resp("", [fc])
        LOG["user"] += 1                                     # the user simulator
        sysmsg = items[0]["content"] if items else ""
        ins = sysmsg.split("\n\nInstruction: ", 1)[1].split("\nRules:", 1)[0].rstrip("\n") if "\n\nInstruction: " in sysmsg else None
        if len(items) <= 2:
            if ins is not None:
                LOG["instructions"].append(ins)
            rid = hashlib.sha256((ins or "").encode()).hexdigest()[:10]
            return Resp(f"Hi, my request id is {rid}. Please cancel my order #W0000000.", [O(type="message")])
        return Resp("###STOP###", [O(type="message")])

class Client:
    def __init__(self):
        self.responses = Responses()
    def with_options(self, **_):
        return self

models._base_client = Client()
import tau_bench.envs as TE                             # run_online.main() imports get_env from here at each call
_orig_get_env = TE.get_env
def _get_env(*a, **kw):
    if kw.get("user_strategy") == "llm" and kw.get("task_index") in PLAN["fail_env"]:
        raise RuntimeError("fake env build failure (test)")
    return _orig_get_env(*a, **kw)
TE.get_env = _get_env
fresh = "_pc_tau_copy_retail_tools" not in sys.modules  # nothing loaded the copied tools before main()
results = []
for run in cfg["runs"]:
    TOK.update(run.get("tokens", {}))
    PLAN["agent"] = run.get("agent_plan", "cancel")
    PLAN["fail_env"] = set(run.get("fail_env", []))
    PLAN["judge"] = run.get("judge", "all_true")
    before = {k: LOG[k] for k in ("judge", "agent", "user")}
    out = io.StringIO()
    err = None
    try:
        with contextlib.redirect_stdout(out):
            run_online.main(run["argv"])
    except SystemExit as e:
        err = f"SystemExit: {e}"
    results.append({"name": run["name"], "stdout": out.getvalue(), "error": err,
                    "expect_refused": run.get("expect_refused"),
                    "calls": {k: LOG[k] - before[k] for k in before}})
from tau_bench.envs.retail.tasks_train import TASKS_TRAIN
from tau_bench.envs.retail.tasks_test import TASKS_TEST
res = {"results": results, "network_attempts": NET, "instructions": LOG["instructions"],
       "judge_users": LOG["judge_users"], "tools_fresh_before_main": fresh,
       "train_instructions": {str(t): TASKS_TRAIN[t].instruction for t in cfg["tasks"]},
       "test_instructions": [t.instruction for t in TASKS_TEST]}
with open(cfg["result"], "w") as f:
    json.dump(res, f)
print("driver done")
'''


def read_lines(root: str):
    out = []
    for dirpath, _, files in os.walk(root):
        for name in sorted(files):
            if soft_stop.is_episodes_file(name):
                with open(os.path.join(dirpath, name), encoding="utf-8") as f:
                    for line in f:
                        out.append((os.path.relpath(os.path.join(dirpath, name), root), json.loads(line)))
    return out


@unittest.skipUnless(os.path.exists(VENV_PY), "τ-bench venv not found")
class TestFakeRunEndToEnd(TmpCase):
    """The real main() in the venv, network blocked, a fake Azure client behind every LLM seam."""

    def drive(self, name, runs, tasks):
        d = self.tmp(name)
        cfg = {"runs": runs(d), "tasks": tasks, "result": os.path.join(d, "result.json")}
        cfg_path = os.path.join(d, "cfg.json")
        write_json(cfg_path, cfg)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", LITELLM_LOCAL_MODEL_COST_MAP="True")
        r = subprocess.run([VENV_PY, "-B", "-c", _FAKE_RUN_DRIVER, PC_DIR, cfg_path], capture_output=True, text=True,
                           cwd=PC_DIR, timeout=900, env=env)
        self.assertEqual(r.returncode, 0, (r.stdout[-3000:], r.stderr[-5000:]))
        with open(cfg["result"]) as f:
            res = json.load(f)
        self.assertEqual(res["network_attempts"], [])
        for x in res["results"]:
            if x.get("expect_refused"):
                self.assertIn(x["expect_refused"], x["error"] or "", x["name"])
                self.assertEqual(x["calls"], {"judge": 0, "agent": 0, "user": 0}, x["name"])
            else:
                self.assertIsNone(x["error"], (x["name"], x["stdout"][-3000:]))
        return d, res

    @staticmethod
    def done_line(stdout):
        lines = [x for x in stdout.splitlines() if " DONE: " in x]
        assert len(lines) == 1, lines
        return lines[0]

    @staticmethod
    def total_in_done(stdout):
        """The total spend printed at the end of the DONE line (F1 item 6)."""
        return float(TestFakeRunEndToEnd.done_line(stdout).split("total spend $")[1].split(" ")[0])

    @staticmethod
    def argv(d, sub, task_ids, extra=()):
        return ["--profile", "luna-dev", "--env", "retail", "--tasks", "tau_retail_train", "--task-ids", task_ids,
                "--out-root", os.path.join(d, sub, "stage_a"), "--cache-root", os.path.join(d, sub, "cache"),
                "--spend-root", os.path.join(d, sub)] + list(extra)

    def test_two_shards_both_guards_separate_caches_resume(self):
        tasks = [1, 2, 3, 4]
        ids = ",".join(map(str, tasks))
        d, res = self.drive("e2e", lambda d: [
            {"name": "shard0", "argv": self.argv(d, "a", ids, ["--shard", "0/2", "--workers", "2"])},
            {"name": "shard1", "argv": self.argv(d, "a", ids, ["--shard", "1/2", "--workers", "2"])},
            {"name": "resume", "argv": self.argv(d, "a", ids, ["--shard", "1/2", "--workers", "2"])},
            # F1 item 4: the job has n = 2 (job.json); no --shard, or another n, is refused (0 calls, no file)
            {"name": "mixed_none", "argv": self.argv(d, "a", ids, ["--workers", "2"]),
             "expect_refused": "mixed shard counts refused"},
            {"name": "mixed_4", "argv": self.argv(d, "a", ids, ["--shard", "0/4", "--workers", "2"]),
             "expect_refused": "mixed shard counts refused"},
        ], tasks)
        root = os.path.join(d, "a")
        lines = read_lines(os.path.join(root, "stage_a"))
        self.assertEqual(len(lines), 8)
        files = {f for f, _ in lines}
        self.assertEqual(files, {os.path.join("luna", g, f"episodes_shard{i}of2.jsonl")
                                 for g in run_online.STAGE_A_GUARDS for i in (0, 1)})
        units = sorted((r["task_index"], r["guard"]) for _, r in lines)
        self.assertEqual(units, sorted((t, g) for t in tasks for g in run_online.STAGE_A_GUARDS))   # each once
        for f, r in lines:
            self.assertEqual(r["guard"], f.split(os.sep)[1])
            shard = int(f.split("shard")[1][0])
            self.assertEqual(tasks.index(r["task_index"]) % 2, shard)
            self.assertTrue(EARLIER_LINE_KEYS <= set(r), EARLIER_LINE_KEYS - set(r))
            self.assertEqual(set(r) - EARLIER_LINE_KEYS, {"task_split"})
            self.assertEqual((r["task_split"], r["profile"], r["env"], r["trial"], r["error"]),
                             ("train", "luna-dev", "retail", 0, None))
            self.assertEqual(r["models"], {"agent": "gpt-6-luna", "user": "gpt-6-luna", "guard": "gpt-6-luna"})
            self.assertTrue(r["done"])
            self.assertEqual(r["usage_roles"]["user"]["calls"], r["calls"]["user"] + 1)   # the kept thrown-away call
            self.assertEqual("tracker" in r["attempts"][0]["guard"], r["guard"] == "tgr_tracker")
        # the user simulator got the train-split instructions of exactly these tasks (never a test-split one)
        want = {res["train_instructions"][str(t)] for t in tasks}
        self.assertEqual(set(res["instructions"]), want)
        self.assertFalse(want & set(res["test_instructions"]))
        # one judge cache per guard; the same first prompts in both, so a shared cache would have answered the second
        keys = {}
        for g in run_online.STAGE_A_GUARDS:
            cdir = os.path.join(root, "cache", g, "structured")
            keys[g] = {f for _, _, fs in os.walk(cdir) for f in fs if f.endswith(".json")}
            self.assertTrue(keys[g], g)
        self.assertFalse(os.path.exists(os.path.join(root, "cache", "structured")))
        self.assertTrue(keys["tgr_frozen"] & keys["tgr_tracker"])
        for g in run_online.STAGE_A_GUARDS:          # judge calls of a guard that were not cache hits = its own files
            fresh = sum(a["guard"]["usage"]["n_llm_calls"] - a["guard"]["usage"]["cache_hits"]
                        for _, r in lines if r["guard"] == g for a in r["attempts"] if a["guard"])
            self.assertEqual(fresh, len(keys[g]), g)
        # a judge prompt reaches the (fake) model at most once per guard, and the first prompt of each task reached
        # it twice: once per guard (with one shared cache, the second guard would have got the first one's answer)
        seen = {}
        for h in res["judge_users"]:
            seen[h] = seen.get(h, 0) + 1
        self.assertLessEqual(max(seen.values()), 2)
        self.assertGreaterEqual(sum(1 for c in seen.values() if c == 2), len(tasks))
        # run files, one per guard folder and shard; resume ran nothing
        for g in run_online.STAGE_A_GUARDS:
            runs = sorted(f for f in os.listdir(os.path.join(root, "stage_a", "luna", g)) if f.startswith("run_"))
            self.assertEqual(len(runs), 3, runs)
        out = {x["name"]: x for x in res["results"]}
        for s in ("shard0", "shard1"):
            self.assertIn("[v2-stage-a] retail/tgr_frozen+tgr_tracker DONE: 4 episodes", out[s]["stdout"])
            self.assertNotIn("STOPPED", out[s]["stdout"])
        self.assertIn("DONE: 0 episodes", out["resume"]["stdout"])
        self.assertEqual(out["resume"]["calls"], {"judge": 0, "agent": 0, "user": 0})
        self.assertAlmostEqual(soft_stop.spent_usd(root), sum(soft_stop.line_cost(r) for _, r in lines), places=9)
        # F1 item 4: the job file; F1 item 6: the DONE line ends with the total spend under the spend root
        self.assertEqual(run_online.read_job_file(os.path.join(root, "stage_a", "luna"))["n_shards"], 2)
        self.assertAlmostEqual(self.total_in_done(out["resume"]["stdout"]), soft_stop.spent_usd(root), delta=6e-5)
        self.assertGreater(self.total_in_done(out["resume"]["stdout"]), 0)
        for name in ("mixed_none", "mixed_4"):
            self.assertNotIn(" DONE: ", out[name]["stdout"])
        self.assertTrue(res["tools_fresh_before_main"])

    def test_soft_stop_and_the_30_dollar_rule(self):
        tasks = [1, 2, 3, 4, 5, 6]

        def runs(d):
            write_json(os.path.join(d, "stop", "stage_b", "f", "A", "0.json"), {"cost_usd": 99.0})
            write_json(os.path.join(d, "finish", "stage_b", "f", "A", "0.json"), {"cost_usd": 99.9})
            write_json(os.path.join(d, "finish_later", "stage_b", "f", "A", "0.json"), {"cost_usd": 99.9})
            return [{"name": "stop", "tokens": {"in": 10_000_000, "out": 100},
                     "argv": self.argv(d, "stop", ",".join(map(str, tasks)), ["--workers", "1"])},
                    {"name": "finish", "tokens": {"in": 1_000_000, "out": 100},
                     "argv": self.argv(d, "finish", "1,2,3", ["--workers", "1"])},
                    {"name": "finish_later", "tokens": {"in": 1_000_000, "out": 100},
                     "argv": self.argv(d, "finish_later", "1,2,3", ["--workers", "1", "--later-left-usd", "29.5"])}]
        d, res = self.drive("softstop", runs, tasks)
        out = {x["name"]: x for x in res["results"]}
        # F1 item 7: the same as "finish", but $29.50 of later jobs is added to the left estimate: after the first
        # unit, 5 units x about $0.6 + $29.50 > $30, so it stops
        later = read_lines(os.path.join(d, "finish_later", "stage_a"))
        self.assertEqual(len(later), 1)
        self.assertGreater(soft_stop.line_cost(later[0][1]) * 5 + 29.5, 30)
        self.assertIn("[v2-stage-a] STOPPED (soft stop): spent $", out["finish_later"]["stdout"])
        self.assertIn("soft stop: 5 units not started", out["finish_later"]["stdout"])
        self.assertIn("later jobs $29.50 added to the left estimate", out["finish_later"]["stdout"])
        for g in run_online.STAGE_A_GUARDS:
            gd = os.path.join(d, "finish_later", "stage_a", "luna", g)
            with open(os.path.join(gd, [f for f in os.listdir(gd) if f.startswith("run_")][0])) as f:
                ss = json.load(f)["plan"]["soft_stop"]
            self.assertEqual(ss["later_left_usd"], 29.5)
            self.assertAlmostEqual(ss["left_estimate_now_usd"], ss["this_job_left_now_usd"] + 29.5, places=3)
        for name, sub in (("stop", "stop"), ("finish", "finish"), ("finish_later", "finish_later")):
            self.assertAlmostEqual(self.total_in_done(out[name]["stdout"]), soft_stop.spent_usd(os.path.join(d, sub)),
                                   delta=6e-5)                # printed with 4 decimals
        # stop: 99 < 100, so the first unit runs (about $6); then spent >= 100 and 11 units x about $6 > $30 left
        stop_lines = read_lines(os.path.join(d, "stop", "stage_a"))
        self.assertEqual(len(stop_lines), 1)
        unit_cost = soft_stop.line_cost(stop_lines[0][1])
        self.assertGreater(unit_cost, 30 / 11)
        self.assertIn("[v2-stage-a] STOPPED (soft stop): spent $", out["stop"]["stdout"])
        self.assertIn("DONE: 1 episodes", out["stop"]["stdout"])
        self.assertIn("soft stop: 11 units not started", out["stop"]["stdout"])
        # finish: spent passes $100 after the first unit, but 5 units x about $0.6 <= $30 are left: all 6 run
        fin = read_lines(os.path.join(d, "finish", "stage_a"))
        self.assertEqual(len(fin), 6)
        self.assertLess(max(soft_stop.line_cost(r) for _, r in fin) * 5, 30)
        self.assertGreater(soft_stop.spent_usd(os.path.join(d, "finish")), 100)
        self.assertNotIn("STOPPED", out["finish"]["stdout"])
        self.assertIn("DONE: 6 episodes", out["finish"]["stdout"])
        self.assertNotIn("soft stop:", out["finish"]["stdout"])


    def test_env_build_failure_gives_an_error_line_and_done(self):
        """F1 item 5 (audit A2 W4): get_env fails for task 2 (both guards): 2 error lines, the other units run, the
        process ends with its DONE line. A resume runs exactly the 2 failed units."""
        def runs(d):
            return [{"name": "fail", "fail_env": [2], "argv": self.argv(d, "f", "1,2,3", ["--workers", "2"])},
                    {"name": "resume", "argv": self.argv(d, "f", "1,2,3", ["--workers", "2"])}]
        d, res = self.drive("envfail", runs, [1, 2, 3])
        out = {x["name"]: x for x in res["results"]}
        self.assertIn("DONE: 6 episodes", self.done_line(out["fail"]["stdout"]))
        self.assertIn("DONE: 2 episodes", self.done_line(out["resume"]["stdout"]))
        lines = [r for _, r in read_lines(os.path.join(d, "f", "stage_a"))]
        bad = [r for r in lines if r["error"] is not None]
        self.assertEqual(sorted((r["task_index"], r["guard"]) for r in bad),
                         [(2, g) for g in sorted(run_online.STAGE_A_GUARDS)])
        for r in bad:
            self.assertEqual(r["error"], "RuntimeError: fake env build failure (test)")
            self.assertEqual((r["env"], r["trial"], r["profile"], r["task_split"]), ("retail", 0, "luna-dev", "train"))
            self.assertIn("usage_roles", r)
        good = sorted((r["task_index"], r["guard"]) for r in lines if r["error"] is None)
        self.assertEqual(good, sorted((t, g) for t in (1, 2, 3) for g in run_online.STAGE_A_GUARDS))

    def test_eight_workers_tracker_checks_have_no_lookup_error(self):
        """F1 item 1 (audit A2 blocker): tgr_tracker, 8 workers, a fresh process, a fake agent whose second call is
        checked on a history with an executed call (so the tracker replays it with the copied tools). Before the fix,
        some checks got the half-loaded tool module and fell back to the judge (lookup_errors)."""
        tasks = list(range(1, 17))

        def runs(d):
            return [{"name": "race", "agent_plan": "tool2", "judge": "satisfy",
                     "argv": self.argv(d, "r", ",".join(map(str, tasks)), ["--workers", "8", "--guards", "tgr_tracker"])}]
        d, res = self.drive("race8", runs, tasks)
        self.assertTrue(res["tools_fresh_before_main"])
        lines = [r for _, r in read_lines(os.path.join(d, "r", "stage_a"))]
        self.assertEqual(len(lines), len(tasks))
        checks = replayed = errors = 0
        for r in lines:
            self.assertIsNone(r["error"])
            for a in r["attempts"]:
                tr = (a.get("guard") or {}).get("tracker") or {}
                if tr.get("applied"):
                    checks += 1
                    replayed += (tr.get("state") or {}).get("events", 0) > 0
                errors += len(tr.get("lookup_errors") or [])
        self.assertGreaterEqual(replayed, len(tasks))         # every conversation had a check after a replay
        self.assertGreaterEqual(checks, replayed)
        self.assertEqual(errors, 0)
        gd = os.path.join(d, "r", "stage_a", "luna", "tgr_tracker")
        with open(os.path.join(gd, [f for f in os.listdir(gd) if f.startswith("run_")][0])) as f:
            pre = json.load(f)["plan"]["tau_copy_preloaded"]
        self.assertEqual((pre["domain"], pre["thread"]), ("retail", "main, before the workers"))
        self.assertGreater(pre["tools"], 0)


@unittest.skipUnless(os.path.exists(VENV_PY), "τ-bench venv not found")
class TestRealDryRun(TmpCase):
    """The real --dry-run in the venv (real client objects, no fake): no LLM call, nothing written."""

    def test_dry_run(self):
        d = self.tmp("dry")
        argv = ["--profile", "nano-agent-luna", "--env", "retail", "--tasks", "tau_retail_train", "--task-ids", "1,2",
                "--shard", "1/2", "--out-root", os.path.join(d, "stage_a"), "--cache-root", os.path.join(d, "cache"),
                "--spend-root", d, "--later-left-usd", "12.5", "--dry-run"]
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([VENV_PY, "-B", "-m", "guard.run_online"] + argv, capture_output=True, text=True,
                           cwd=PC_DIR, timeout=600, env=env)
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        self.assertIn("[v2-stage-a] LLM calls in this dry run: agent 0, user 0, judge 0;", r.stdout)
        self.assertIn("refused writes 0", r.stdout)
        self.assertIn("[v2-stage-a] retail/tgr_frozen+tgr_tracker DRY RUN DONE", r.stdout)
        plan = json.loads(r.stdout.split("DRY RUN (no LLM call, nothing written):\n", 1)[1].split("\n[v2-stage-a]")[0])
        self.assertEqual(plan["models"], {"agent": "gpt-5-nano", "user": "gpt-6-luna", "guard": "gpt-6-luna"})
        self.assertEqual((plan["task_split"], plan["agent"], plan["units_to_run"]), ("train", "nano", 2))
        self.assertEqual(plan["first_units"], [[2, 0, "tgr_frozen"], [2, 0, "tgr_tracker"]])
        self.assertTrue(plan["shards_cover_every_unit_once"])
        self.assertEqual(plan["probe_user_strategy"], "human (no LLM call)")
        ss = plan["soft_stop"]                                    # F1 item 7: printed in the plan
        self.assertEqual(ss["later_left_usd"], 12.5)
        self.assertAlmostEqual(ss["left_estimate_now_usd"], ss["this_job_left_now_usd"] + 12.5, places=3)
        self.assertEqual(plan["job"]["exists_now"], False)        # F1 item 4: checked, not written
        self.assertEqual(plan["job"]["this_process"]["n_shards"], 2)
        self.assertEqual(plan["tau_copy_preloaded"]["thread"], "main, before the workers")   # F1 item 1
        self.assertEqual(os.listdir(d), [])                       # nothing written


if __name__ == "__main__":
    unittest.main()
