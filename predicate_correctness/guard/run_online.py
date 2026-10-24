"""Our wrapper around the copied conversation runner (from_shieldagent/runner/exp_core/run_online.py).
Part 10 of the earlier plan, extended in eval v2 Part 2 (docs/planning/tracker_eval_v2/p2.md) for Stage A.

It runs the same loop as the copy's main(): the copied episode loop (repro_online/episode.py::run_episode), the copied
model routing (exp_core/models.py: activate, make_completion), τ-bench from the venv, resumable output, one line per
conversation. The copy is not edited and its main() is not called, because it builds its paths from its own folder.

Two modes, chosen by --tasks:

1. Earlier online test (--tasks train | val, the labels of our splits.json copy on τ-bench's *test* split), as in
   Part 10, unchanged except two points marked (*):
  - outputs:  output/online/<tag>/<env>/<guard>/episodes.jsonl and run_<time>.json (copy: ShieldAgent's output/);
  - LLM cache: output/_llmcache/<tag>/structured (copy: output/tgr/_llmcache under its own folder), set through the
    module constant exp_core.models.CACHE_ROOT before activate(). A new, empty cache per tag. Agent and user-simulator
    calls have no cache in the copy (fresh);
  - task list: our copy of splits.json; tasks labelled test are refused; one guard per process (--guard);
  - (*) every line also gets "task_split": "test";
  - (*) the probe env (for the tool schemas and the policy text) is built with user_strategy="human": no LLM call.
    Before, it was built with "llm", which made one thrown-away user-simulator call per process (part1.md 5.7).

2. Stage A of eval v2 (--tasks tau_retail_train): τ-bench's 500 extra retail tasks (tasks_train.py, get_env(...,
   task_split="train"), indices 0-499). Retail only. These indices are never looked up in splits.json (they collide
   with test-split indices: train task 5 is not test task 5).
  - guards: both by default, tgr_frozen and tgr_tracker (--guards to choose). tgr_frozen is the copied TGR guard
    unchanged, built by the copied runner's own builder exp_core/run_online.py::build_guard("tgr", env, tools_info,
    None, from_shieldagent/rules/<env>) (repro_online.guards.TGRGuard; judge effort medium, epsilon 0.1, feedback C).
    tgr_tracker is guard/tgr_tracker.py (the guard of the earlier online test). Both use the frozen rule set; its
    sha256 must equal the frozen copy's;
  - same period: one job runs units (task, guard). The two units of a task are next to each other in the queue, and
    the guard that goes first flips from task to task (inside each process). So at any time both guards have nearly
    the same tasks done, and a stop leaves paired data. --shard i/n (n <= 4) splits the tasks (by position p,
    p % n == i) between n processes; each process writes its own files and holds a lock file for its shard (never
    two processes appending to one file). Use the same n for all processes of a job: the first real process writes
    <out_root>/<agent>/job.json (n, task list sha256, guards); a later process with another n (also no --shard while
    a sharded job exists, and the reverse), or with n > 1 and another task list, is refused, also when only episode
    files of another n exist (eval v2 fix F1 item 4). A dry run checks this too, and writes nothing;
  - same profile, max steps (30), cap (3) and 1 try (--trials 1, the only value allowed) for both guards;
  - outputs: output/eval_v2/stage_a/<agent>/<guard>/episodes.jsonl (1 shard) or episodes_shard<i>of<n>.jsonl, and
    run_<time>[_shard<i>of<n>].json per process in each guard folder; <agent> is luna (luna-dev) or nano
    (nano-agent-luna). The lines have the fields of the earlier lines, plus task_split ("train"). Resume: every
    process reads all episodes*.jsonl of the guard folders; a (task, try) with a line without error is done;
  - judge cache: one fresh folder per guard, <cache_root>/<guard>/structured, cache_root default
    output/_llmcache/v2_<out_root below eval_v2, with "_">_<agent> (v2_stage_a_luna, v2_stage_a_nano). The copy
    has one shared LLM object per process (repro_runtime/calls.py::shared_llm); the wrapper re-points that seam (as
    exp_core.models.activate re-points its seams) to a router that gives each worker thread the LLM object of the
    guard it is running, built by the copy's own activated factory with that guard's cache folder. No judge answer
    is shared across guards; a judge call outside a unit fails;
  - the thrown-away user-simulator call at env build (part1.md 5.7, trap 2) is kept, as in every earlier run, for both
    guards (the same code path builds every env): one short call per conversation, in usage_roles.user;
  - soft stop (guard/soft_stop.py): before each new unit, spent = all LLM cost recorded under output/eval_v2/
    (--spend-root) and left estimate = units of the whole job (all shards) not done and not running here x mean cost
    per done unit (a prior per profile if none is done), plus --later-left-usd X (default 0: the cost of later or
    concurrent jobs, given by the main chat; F1 item 7). At $100 or more, units are started only if the left
    estimate is $30 or less. Otherwise no new unit starts (running units finish), and the run prints
    "[v2-stage-a] STOPPED (soft stop): ...". The stop is sticky. The DONE line ends with the total spend under the
    spend root (F1 item 6);
  - a failure while building a unit's env (get_env, which makes the thrown-away user call) gives an error line for
    that unit, as any failed conversation; the run goes on and ends with its DONE line (F1 item 5).

Safety, both modes: profiles luna-dev and nano-agent-luna only (no grok-4.7); the models of every role must be
gpt-6-luna or gpt-5-nano; the write guard (guard/write_guard.py) is installed before any runner import and refuses any
write outside predicate_correctness/output/, and opening or listing anything under ~/ShieldAgent; the tool schemas
must give the tools_sha256 of the rule set's manifest (the rules were built for them); tgr_frozen (in every mode) and
every Stage A guard must use the frozen rule set (sha256 checked before any runner import, and again on the built
guard; F1 item 2); --tasks must be train, val or tau_retail_train, also with --task-ids, and --task-ids must be
distinct integers (F1 item 3). The copied τ-bench tools and data modules are loaded in the main thread before any
worker starts (state_tracker/tau_copy.py preload; F1 item 1: with lazy loading in 8 workers, some tracker checks
got a half-loaded module and fell back to the judge).
--dry-run: resolve and print everything (tasks, units, shards, paths, caches, models, guards), build the guards, then
stop before the first conversation. The network is blocked in a dry run (audit hook), so no LLM call can happen;
the counts of agent, user and judge calls and of blocked network attempts are printed. Nothing is written.

Run from predicate_correctness/ with the venv (long runs with setsid nohup, output to output/logs/).
Earlier online test:
  ~/venvs/tau-bench/bin/python -B -m guard.run_online --profile luna-dev --env retail --tasks train --trials 3 \
      --tag luna_train --workers 8
  Progress lines "[p10-online] ..."; final line "[p10-online] <env>/<guard> DONE: ...".
Stage A, strong agent, 4 processes (then the same with --profile nano-agent-luna and logs v2_stage_a_nano_s<i>.log):
  cd /home/azureuser/code_projects/predicate_correctness && for i in 0 1 2 3; do PYTHONDONTWRITEBYTECODE=1 \
      setsid nohup ~/venvs/tau-bench/bin/python -B -m guard.run_online --profile luna-dev --env retail \
      --tasks tau_retail_train --shard $i/4 --workers 8 > output/logs/v2_stage_a_luna_s$i.log 2>&1 & done
  Check first with the same command plus --dry-run (no LLM call). Progress lines "[v2-stage-a] ..."; final line
  "[v2-stage-a] retail/tgr_frozen+tgr_tracker DONE: ..." (after "[v2-stage-a] STOPPED (soft stop): ..." if stopped).
Smoke test (Part 5), 5 tasks, outputs apart from Stage A (cache v2_smoke_stage_a_luna):
  ~/venvs/tau-bench/bin/python -B -m guard.run_online --profile luna-dev --env retail --tasks tau_retail_train \
      --task-ids 1,24,30,88,99 --out-root output/eval_v2/smoke/stage_a --workers 8
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import math
import os
import re
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional, Sequence, Tuple

sys.dont_write_bytecode = True

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "guard"

from guard import runner_path, soft_stop, write_guard                     # noqa: E402
from state_tracker import paths                                            # noqa: E402

OUTPUT_DIR = paths.OUTPUT_DIR
ONLINE_DIR = os.path.join(OUTPUT_DIR, "online")
LLMCACHE_DIR = os.path.join(OUTPUT_DIR, "_llmcache")
EVAL_V2_DIR = soft_stop.EVAL_V2_DIR
STAGE_A_DIR = os.path.join(EVAL_V2_DIR, "stage_a")
SPLITS_FILE = paths.SPLITS_FILE
ALLOWED_PROFILES = ("luna-dev", "nano-agent-luna")
AGENT_OF_PROFILE = {"luna-dev": "luna", "nano-agent-luna": "nano"}       # fork/schema.py AGENTS, reversed
ALLOWED_SPLITS = ("train", "val")
TAU_RETAIL_TRAIN = "tau_retail_train"   # τ-bench retail tasks_train.py (TASKS_TRAIN), get_env(task_split="train")
TAU_RETAIL_TRAIN_N = 500
TASK_SOURCES = ALLOWED_SPLITS + (TAU_RETAIL_TRAIN,)
ALLOWED_MODELS = ("gpt-6-luna", "gpt-5-nano")
GUARDS = ("tgr_tracker", "tgr_frozen")
STAGE_A_GUARDS = ("tgr_frozen", "tgr_tracker")
# sha256 of the frozen rule sets (from_shieldagent/PROVENANCE.md; = ~/ShieldAgent/tgr_rules/<env>/frozen/)
FROZEN_RULES_SHA256 = {
    "airline": "27e2eafa05fd919d41083e8d4dfeb7c4a6d9a789fa2ad7c5da645584d05bc5a4",
    "retail": "9e395e2fc259cdf228612c4cd078a5bb3836bad4fe42af4493ffc9359fb63d7b",
}
MAX_SHARDS = 4                   # the VM: at most 4 heavy processes at once
JOB_FILE = "job.json"            # <agent_dir>/job.json: the shard count n and task list of the Stage A job (F1 item 4)
EPISODES_NAME_RE = re.compile(r"^episodes(?:_shard(\d+)of(\d+))?\.jsonl$")
PRIOR_USD_PER_UNIT = {"luna-dev": 0.0125, "nano-agent-luna": 0.024}      # part1.md section 6 (saved retail runs)
MAX_STEPS = 30
TAG_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
NET_EVENTS = ("socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyname_ex",
              "socket.gethostbyaddr", "socket.sendto", "socket.sendmsg")

_write_lock = threading.Lock()
NETWORK_ATTEMPTS: List[str] = []
_net = {"blocked": False}


class RunRefused(SystemExit):
    """A safety rule refuses the run (wrong profile, split, model or path)."""


def _under(path: str, root: str) -> bool:
    p, r = os.path.realpath(path), os.path.realpath(root)
    return p == r or p.startswith(r + os.sep)


# ------------------------------------------------------------------------------------------------- tasks and units

def task_split_of(tasks: str) -> str:
    """τ-bench task split of a task source: "train" for tau_retail_train, "test" for the splits.json labels."""
    return "train" if tasks == TAU_RETAIL_TRAIN else "test"


def task_list(env: str, tasks: str, task_ids: Optional[str], splits_file: str = SPLITS_FILE) -> list:
    """The task indices to run.
    tau_retail_train: retail only; indices 0-499 of τ-bench's TASKS_TRAIN (all, or --task-ids); splits.json is not
    read. Otherwise (as before): every task must be labelled train or val in splits.json (τ-bench's test split)."""
    if tasks == TAU_RETAIL_TRAIN:
        if env != "retail":
            raise RunRefused(f"--tasks {TAU_RETAIL_TRAIN} is retail only (τ-bench has no extra {env} tasks): refused")
        if not task_ids:
            return list(range(TAU_RETAIL_TRAIN_N))
        try:
            out = [int(x) for x in task_ids.split(",") if x.strip()]
        except ValueError:
            raise RunRefused(f"--task-ids {task_ids!r}: integers only") from None
        bad = [t for t in out if not 0 <= t < TAU_RETAIL_TRAIN_N]
        if bad or not out:
            raise RunRefused(f"tasks {bad} are not {TAU_RETAIL_TRAIN} indices (0-{TAU_RETAIL_TRAIN_N - 1}): refused")
        if len(set(out)) != len(out):
            raise RunRefused(f"--task-ids {task_ids!r} has repeated tasks: refused")
        return out
    if tasks not in ALLOWED_SPLITS:                     # also with --task-ids (audit A1 W2)
        raise RunRefused(f"--tasks {tasks!r} refused: only {TASK_SOURCES}")
    with open(splits_file, encoding="utf-8") as f:
        split = json.load(f)[env]["split"]
    if task_ids:
        try:
            out = [int(x) for x in task_ids.split(",") if x.strip()]
        except ValueError:
            raise RunRefused(f"--task-ids {task_ids!r}: integers only") from None
        if not out:
            raise RunRefused(f"--task-ids {task_ids!r}: no task given")
        if len(set(out)) != len(out):
            raise RunRefused(f"--task-ids {task_ids!r} has repeated tasks: refused")
    else:
        out = sorted(int(k) for k, v in split.items() if v == tasks)
    bad = [t for t in out if split.get(str(t)) not in ALLOWED_SPLITS]
    if bad:
        raise RunRefused(f"tasks {bad} are not train or val tasks in splits.json: refused")
    return out


def parse_guards(guard: Optional[str], guards: Optional[str], stage_a: bool) -> Tuple[str, ...]:
    """The guards of this run: --guards (comma list), else --guard, else both (Stage A) or tgr_tracker (earlier)."""
    if guards:
        out = tuple(g.strip() for g in guards.split(",") if g.strip())
    elif guard:
        out = (guard,)
    else:
        out = STAGE_A_GUARDS if stage_a else ("tgr_tracker",)
    bad = [g for g in out if g not in GUARDS]
    if bad or not out or len(set(out)) != len(out):
        raise RunRefused(f"guards {out} refused: only distinct names from {GUARDS}")
    if not stage_a and len(out) != 1:
        raise RunRefused("--tasks train/val runs one guard per process (as before); several guards: Stage A only")
    return out


def needs_frozen_rules(guard: str, stage_a: bool) -> bool:
    """tgr_frozen must run the frozen rule set in every mode (audit A1 W1); in Stage A every guard must."""
    return stage_a or guard == "tgr_frozen"


def frozen_rules_problem(guard: str, env: str, stage_a: bool, rule_set_sha256: Optional[str]) -> Optional[str]:
    """Why this guard's rule set is refused (None: it is fine)."""
    if not needs_frozen_rules(guard, stage_a):
        return None
    want = FROZEN_RULES_SHA256.get(env)
    if rule_set_sha256 != want:
        return f"{guard}: the rule set is not the frozen one (sha256 {rule_set_sha256}, frozen {want})"
    return None


def check_frozen_rules_early(guards: Sequence[str], env: str, stage_a: bool, rules_dir: Optional[str]) -> None:
    """Before any runner import: the rule_set.json that build_guard will load must be the frozen one, for every
    guard that needs it. Raises RunRefused."""
    rdir = rules_dir or os.path.join(paths.RULES_DIR, env)
    path = os.path.join(rdir, "rule_set.json")
    for g in guards:
        if not needs_frozen_rules(g, stage_a):
            continue
        try:
            got = sha256_file(path)
        except OSError as e:
            raise RunRefused(f"{g}: cannot read the rule set {path}: {e}") from None
        prob = frozen_rules_problem(g, env, stage_a, got)
        if prob:
            raise RunRefused(f"{prob}; rules dir {rdir}")


def parse_shard(spec: Optional[str]) -> Tuple[int, int]:
    """'i/n' -> (i, n), 0 <= i < n <= MAX_SHARDS. None -> (0, 1)."""
    if spec is None:
        return 0, 1
    m = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", spec)
    if not m:
        raise RunRefused(f"--shard {spec!r}: use i/n, for example 0/4")
    i, n = int(m.group(1)), int(m.group(2))
    if not (1 <= n <= MAX_SHARDS and 0 <= i < n):
        raise RunRefused(f"--shard {spec!r}: need 0 <= i < n <= {MAX_SHARDS}")
    return i, n


def shard_suffix(shard: Tuple[int, int]) -> str:
    i, n = shard
    return "" if n == 1 else f"_shard{i}of{n}"


def plan_units(tasks: Sequence[int], trials: int, guards: Sequence[str], n_shards: int = 1
               ) -> List[Tuple[int, int, str]]:
    """Every unit (task, trial, guard) of the job, in run order: trial by trial, task by task, the guards of one
    task next to each other. The guard that goes first flips from one task to the next inside each shard (task at
    position p: flipped when (p // n_shards) is odd), so it also alternates inside every process. The set of units
    does not depend on n_shards, only their order."""
    out = []
    for k in range(trials):
        for pos, t in enumerate(tasks):
            order = list(guards) if (pos // n_shards) % 2 == 0 else list(guards)[::-1]
            out += [(t, k, g) for g in order]
    return out


def shard_units(units: Sequence[Tuple[int, int, str]], tasks: Sequence[int], shard: Tuple[int, int]
                ) -> List[Tuple[int, int, str]]:
    """The units of shard i of n: the tasks at positions p with p % n == i (all guards and trials of a task)."""
    i, n = shard
    pos = {t: p for p, t in enumerate(tasks)}
    return [u for u in units if pos[u[0]] % n == i]


def compact(ids: Sequence[int]) -> str:
    """[0, 1, 2, 5] -> '0-2,5'."""
    out, s = [], sorted(ids)
    j = 0
    while j < len(s):
        k = j
        while k + 1 < len(s) and s[k + 1] == s[k] + 1:
            k += 1
        out.append(str(s[j]) if j == k else f"{s[j]}-{s[k]}")
        j = k + 1
    return ",".join(out)


# ------------------------------------------------------------------------------------------------- paths

def resolve_paths(tag: str, env: str, guard: str, out_root: str = ONLINE_DIR, cache_root: str | None = None) -> dict:
    """Paths of the earlier online test (one guard, one file)."""
    if not TAG_RE.match(tag):
        raise RunRefused(f"--tag {tag!r}: use letters, digits, '_', '.', '-' only")
    out_dir = os.path.join(out_root, tag, env, guard)
    cache = cache_root or os.path.join(LLMCACHE_DIR, tag)
    for name, p in (("output folder", out_dir), ("LLM cache", cache)):
        if not _under(p, OUTPUT_DIR):
            raise RunRefused(f"{name} {p} is not under {OUTPUT_DIR}")
    return {"out_dir": out_dir, "episodes": os.path.join(out_dir, "episodes.jsonl"), "cache_root": cache,
            "structured_cache": os.path.join(cache, "structured"), "tool_loop_cache": os.path.join(cache, "tool_loop")}


def default_stage_a_tag(out_root: str, agent: str) -> str:
    """v2_<out_root below eval_v2, '/' -> '_'>_<agent>, e.g. v2_stage_a_luna, v2_smoke_stage_a_luna. An out_root
    outside eval_v2 gets v2_out_<out_root below output/>_<agent>, so it never shares the Stage A cache."""
    real = os.path.realpath(out_root)
    if _under(real, EVAL_V2_DIR):
        rel = os.path.relpath(real, os.path.realpath(EVAL_V2_DIR))
    else:
        rel = "out_" + os.path.relpath(real, os.path.realpath(OUTPUT_DIR))
    return "v2_" + re.sub(r"[^A-Za-z0-9_-]", "_", rel.replace(os.sep, "_")) + "_" + agent


def resolve_stage_a_paths(profile: str, guards: Sequence[str], shard: Tuple[int, int], tag: Optional[str] = None,
                          out_root: str = STAGE_A_DIR, cache_root: Optional[str] = None,
                          spend_root: str = EVAL_V2_DIR) -> dict:
    """Paths of a Stage A process: <out_root>/<agent>/<guard>/episodes[_shard<i>of<n>].jsonl, one judge cache folder
    per guard (<cache_root>/<guard>/structured), the shard's lock file, the spend root of the soft stop."""
    agent = AGENT_OF_PROFILE[profile]
    out_root, spend_root = os.path.abspath(out_root), os.path.abspath(spend_root)
    cache_root = os.path.abspath(cache_root) if cache_root else None
    tag = tag or default_stage_a_tag(out_root, agent)
    if not TAG_RE.match(tag):
        raise RunRefused(f"--tag {tag!r}: use letters, digits, '_', '.', '-' only")
    sfx = shard_suffix(shard)
    agent_dir = os.path.join(out_root, agent)
    cache = cache_root or os.path.join(LLMCACHE_DIR, tag)
    g_paths = {g: {"out_dir": os.path.join(agent_dir, g),
                   "episodes": os.path.join(agent_dir, g, f"episodes{sfx}.jsonl"),
                   "structured_cache": os.path.join(cache, g, "structured")} for g in guards}
    checks = [("output folder", agent_dir), ("LLM cache", cache), ("spend root", spend_root)]
    for name, p in checks:
        if not _under(p, OUTPUT_DIR):
            raise RunRefused(f"{name} {p} is not under {OUTPUT_DIR}")
    if not _under(agent_dir, spend_root):
        raise RunRefused(f"output folder {agent_dir} is not under the spend root {spend_root}: the soft stop would "
                         f"not count this run's own cost")
    if _under(cache, agent_dir) or _under(agent_dir, cache):
        raise RunRefused("the LLM cache and the output folder must be apart")
    caches = [v["structured_cache"] for v in g_paths.values()]
    if len(set(caches)) != len(caches):
        raise RunRefused("each guard needs its own judge cache folder")
    return {"agent": agent, "tag": tag, "out_root": out_root, "agent_dir": agent_dir, "shard": f"{shard[0]}/{shard[1]}",
            "shard_suffix": sfx, "guards": g_paths, "lock": os.path.join(agent_dir, f".lock{sfx or '_shard0of1'}"),
            "cache_root": cache, "tool_loop_cache": os.path.join(cache, "tool_loop"), "spend_root": spend_root}


def tools_sha256(tools_info: list) -> str:
    return hashlib.sha256(json.dumps(tools_info, sort_keys=True).encode()).hexdigest()


def sha256_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def count_files(root: str) -> int:
    return sum(len(f) for _, _, f in os.walk(root)) if os.path.isdir(root) else 0


# ------------------------------------------------------------------------------------------------- the job file

def job_identity(n_shards: int, tasks: Sequence[int], guards: Sequence[str], profile: str, env: str,
                 task_split: str) -> dict:
    """What every process of one Stage A job must share (F1 item 4): the shard count n and, with n > 1, the task
    list (the shards split it by position). Guards, profile and env are recorded for information."""
    return {"n_shards": int(n_shards), "tasks_sha256": hashlib.sha256(json.dumps(list(tasks)).encode()).hexdigest(),
            "n_tasks": len(tasks), "guards": sorted(guards), "profile": profile, "env": env, "task_split": task_split}


def read_job_file(agent_dir: str) -> Optional[dict]:
    """<agent_dir>/job.json, or None if there is none. An unreadable file refuses the run."""
    path = os.path.join(agent_dir, JOB_FILE)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            job = json.load(f)
    except (OSError, ValueError) as e:
        raise RunRefused(f"cannot read the job file {path}: {e}") from None
    if not isinstance(job, dict) or not isinstance(job.get("n_shards"), int):
        raise RunRefused(f"the job file {path} has no shard count")
    return job


def _shard_words(n: int) -> str:
    return "no --shard" if n == 1 else f"--shard i/{n}"


def job_problems(agent_dir: str, want: dict, job: Optional[dict] = None) -> List[str]:
    """Why a process with `want` (job_identity) cannot join the job in agent_dir; [] if it can. Checks the job file
    (`job`, read if None) and the names of the episode files already in the guard folders (so a missing job file
    does not hide a job of another n)."""
    n = want["n_shards"]
    probs: List[str] = []
    if job is None:
        job = read_job_file(agent_dir)
    if job is not None:
        if job["n_shards"] != n:
            probs.append(f"the job in {agent_dir} runs {job['n_shards']} shard(s) ({JOB_FILE}); this process has {n}: "
                         f"use {_shard_words(job['n_shards'])} for every process of this job")
        elif n > 1 and job.get("tasks_sha256") != want["tasks_sha256"]:
            probs.append(f"the job in {agent_dir} has another task list ({job.get('n_tasks')} tasks, {JOB_FILE}); "
                         f"with {n} shards the processes would repeat units")
    for g in GUARDS:
        d = os.path.join(agent_dir, g)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            m = EPISODES_NAME_RE.match(name)
            if not m:
                continue
            m_n = int(m.group(2)) if m.group(2) else 1
            if m_n != n:
                probs.append(f"{os.path.join(d, name)} is from a job with {m_n} shard(s); this process has {n} "
                             f"(use {_shard_words(m_n)})")
    return probs


def ensure_job_file(agent_dir: str, want: dict) -> dict:
    """Real runs only, after the shard lock is taken: create <agent_dir>/job.json if there is none (atomic: written
    to a temporary file, then linked; if two processes race, one link wins), then check it. Raises RunRefused."""
    os.makedirs(agent_dir, exist_ok=True)
    path = os.path.join(agent_dir, JOB_FILE)
    tmp = f"{path}.tmp_{os.getpid()}_{threading.get_ident()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dict(want, created=time.strftime("%Y-%m-%dT%H:%M:%S"), by="guard/run_online.py"), f, indent=1)
    try:
        os.link(tmp, path)
        created = True
    except FileExistsError:
        created = False
    finally:
        os.remove(tmp)
    job = read_job_file(agent_dir)
    probs = job_problems(agent_dir, want, job)
    if probs:
        raise RunRefused("mixed shard counts refused: " + "; ".join(probs[:3]))
    return {"path": path, "created": created, "n_shards": job["n_shards"]}


# ------------------------------------------------------------------------------------------------- guards

def build_guard(name: str, env: str, tools_info: list, rules_dir: Optional[str] = None):
    """(guard object, info). Needs runner_path.setup() first.
    tgr_tracker: guard/tgr_tracker.py (the guard of the earlier online test).
    tgr_frozen:  the copied TGR guard unchanged, built by the copied runner's own builder,
                 exp_core/run_online.py::build_guard("tgr", env, tools_info, None, rules_dir)."""
    rules_dir = rules_dir or os.path.join(paths.RULES_DIR, env)
    if name == "tgr_tracker":
        from guard import tgr_tracker
        g = tgr_tracker.build(name, env, tools_info, rules_dir)
        return g, dict(g.info)
    if name == "tgr_frozen":
        from exp_core.run_online import build_guard as copied_build_guard
        g = copied_build_guard("tgr", env, tools_info, None, rules_dir)
        cfg = g.config
        return g, {"guard": name, "built_by": "exp_core/run_online.py::build_guard('tgr', env, tools_info, None, "
                                              "rules_dir) (copied runner, unchanged)",
                   "class": f"{type(g).__module__}.{type(g).__qualname__}", "copy_name": g.name, "domain": env,
                   "rules_dir": rules_dir, "rule_set_sha256": sha256_file(os.path.join(rules_dir, "rule_set.json")),
                   "judge_effort": cfg.judge_effort, "epsilon": cfg.epsilon,
                   "actionable_feedback": cfg.actionable_feedback, "history_chars": cfg.history_chars}
    raise ValueError(f"unknown guard {name!r} (our wrapper knows {GUARDS})")


class JudgeRouter:
    """One judge LLM object (and cache folder) per guard, in one process.

    The copied TGR code takes its LLM object from repro_runtime.calls.shared_llm() (one per process). install()
    re-points that seam to route(): each worker thread says which guard it runs (`with router.use(guard)`), and gets
    that guard's LLM object. build() makes each object with the copy's own activated factory
    (repro_runtime.calls.structured_llm, set by exp_core.models.activate), with exp_core.models.CACHE_ROOT set to the
    guard's folder while it runs, so the objects differ only in their cache folder. A call outside a unit, or for a
    guard without an object, raises."""

    def __init__(self, cache_dirs: Dict[str, str]):
        self.cache_dirs = dict(cache_dirs)          # guard -> <cache_root>/<guard>/structured
        self.llms: Dict[str, object] = {}
        self.calls: Dict[str, int] = {g: 0 for g in cache_dirs}
        self._tls = threading.local()
        self._lock = threading.Lock()
        self.calls_module = None

    def build(self, models_module, calls_module) -> None:
        """Build every guard's LLM object (main thread, before the workers start). Creates the cache folders."""
        old = models_module.CACHE_ROOT
        try:
            for g, d in self.cache_dirs.items():
                models_module.CACHE_ROOT = os.path.dirname(d)
                llm = calls_module.structured_llm()
                if os.path.realpath(llm.cache_dir) != os.path.realpath(d):
                    raise RuntimeError(f"judge cache of {g}: {llm.cache_dir} != {d}")
                self.llms[g] = llm
        finally:
            models_module.CACHE_ROOT = old

    def install(self, calls_module) -> None:
        calls_module._llm = None
        calls_module.shared_llm = self.route
        self.calls_module = calls_module

    @contextlib.contextmanager
    def use(self, guard: str):
        prev = getattr(self._tls, "guard", None)
        self._tls.guard = guard
        try:
            yield
        finally:
            self._tls.guard = prev

    def route(self):
        g = getattr(self._tls, "guard", None)
        if g is None:
            raise RuntimeError("judge call outside a unit (no guard set for this thread)")
        llm = self.llms.get(g)
        if llm is None:
            raise RuntimeError(f"no judge LLM object for guard {g!r} (dry run, or not built)")
        with self._lock:
            self.calls[g] += 1
        return llm


class CallCounter:
    """Counts the agent and user-simulator calls of this process (a pass-through wrapper)."""

    def __init__(self):
        self.n: Dict[str, int] = {"agent": 0, "user": 0}
        self._lock = threading.Lock()

    def wrap(self, role: str, fn: Callable) -> Callable:
        def counted(*args, **kw):
            with self._lock:
                self.n[role] += 1
            return fn(*args, **kw)
        return counted


# ------------------------------------------------------------------------------------------------- progress and run

class JobProgress:
    """Which units of the whole job (all shards) are done: a line without error in any episodes*.jsonl of the guard
    folders (first such line per unit). Also checks that every line belongs to this job (guard, profile, env,
    task_split); a line that does not is a problem (the run is refused at start)."""

    def __init__(self, guard_dirs: Dict[str, str], plan_keys, expect: Dict[str, str], prior_usd: float):
        self.guard_dirs = dict(guard_dirs)
        self.plan_keys = set(plan_keys)            # {(guard, task, trial)}
        self.expect = dict(expect)                 # {"profile", "env", "task_split"}
        self.prior_usd = prior_usd
        self._tail = soft_stop.JsonlTail()
        self._by_path: Dict[str, Dict[tuple, float]] = {}
        self.problems: List[str] = []
        self.lines = 0
        self.error_lines = 0

    def update(self) -> None:
        for g, d in self.guard_dirs.items():
            if not os.path.isdir(d):
                continue
            for name in sorted(os.listdir(d)):
                if not soft_stop.is_episodes_file(name):
                    continue
                path = os.path.join(d, name)
                bad: List[dict] = []
                recs, restarted = self._tail.read_new(path, bad=bad)
                got = self._by_path.setdefault(path, {})
                if restarted:
                    got.clear()
                for b in bad:
                    self.problems.append(f"{path} line {b['line']}: {b['error']}")
                for r in recs:
                    self.lines += 1
                    want = dict(self.expect, guard=g)
                    diff = {k: (r.get(k), v) for k, v in want.items() if r.get(k) != v}
                    if diff:
                        self.problems.append(f"{path}: a line of another job {diff}")
                        continue
                    if r.get("error") is not None:
                        self.error_lines += 1
                        continue
                    key = (g, r.get("task_index"), r.get("trial"))
                    if key not in got:
                        got[key] = soft_stop.line_cost(r)

    def done(self) -> Dict[tuple, float]:
        out: Dict[tuple, float] = {}
        for got in self._by_path.values():
            for k, c in got.items():
                if k in self.plan_keys and k not in out:
                    out[k] = c
        return out

    def mean_cost(self) -> float:
        d = self.done()
        return sum(d.values()) / len(d) if d else self.prior_usd

    def left_estimate(self, running_here: int) -> Tuple[float, int, float]:
        """(USD, units left, mean cost per unit). Units left = units of the job not done and not running here."""
        self.update()
        left = max(0, len(self.plan_keys) - len(self.done()) - running_here)
        mean = self.mean_cost()
        return left * mean, left, mean


def stage_a_left_usd(progress: JobProgress, running_here: int, later_left_usd: float = 0.0) -> float:
    """The left estimate of one soft-stop check: this job's work left (all shards; not done, not running here) plus
    the cost of later or concurrent jobs that the main chat gives with --later-left-usd (F1 item 7)."""
    return progress.left_estimate(running_here)[0] + float(later_left_usd)


def run_units(units: Sequence, run_one: Callable, workers: int, gate: Optional[soft_stop.Gate] = None,
              on_result: Optional[Callable] = None, on_stop: Optional[Callable] = None,
              state: Optional[dict] = None) -> dict:
    """Run the units on a thread pool, in order. With a gate: before each unit starts, gate.check(); when it says
    stop, that unit and every later one are not started (running units finish); on_stop(reason, spent, left) once.
    on_result(record, n_finished) in the main thread. `state` (optional): a dict that gets the live counts, so the
    gate can read state["running"] (the gate is asked while the counts are locked). Returns the counts: started,
    finished, not_started, running (0 at the end), stop (None, or the first stop's reason, spent, left)."""
    st = state if state is not None else {}
    st.update({"started": 0, "finished": 0, "not_started": 0, "running": 0, "stop": None})
    lock = threading.Lock()

    def job(u):
        with lock:
            if gate is not None:
                go, reason, spent, left = gate.check()
                if not go:
                    st["not_started"] += 1
                    first = st["stop"] is None
                    if first:
                        st["stop"] = {"reason": reason, "spent": spent, "left": left}
                    if first and on_stop is not None:
                        on_stop(reason, spent, left)
                    return None
            st["started"] += 1
            st["running"] += 1
        try:
            return run_one(u)
        finally:
            with lock:
                st["running"] -= 1
                st["finished"] += 1

    with ThreadPoolExecutor(max_workers=workers) as ex:
        n = 0
        for fut in as_completed([ex.submit(job, u) for u in units]):
            r = fut.result()
            if r is None:
                continue
            n += 1
            if on_result is not None:
                on_result(r, n)
    return st


def block_network() -> None:
    """Dry run: refuse every network access in this process (audit hook; cannot be removed). Each attempt is listed
    in NETWORK_ATTEMPTS."""
    if _net["blocked"]:
        return

    def hook(event, args):
        if event in NET_EVENTS:
            what = args[1] if event in ("socket.connect", "socket.sendto") and len(args) > 1 else (args[0] if args else "")
            NETWORK_ATTEMPTS.append(f"{event} {what}")
            raise PermissionError(f"network blocked in this dry run ({event} {what})")

    sys.addaudithook(hook)
    _net["blocked"] = True


def _lock_shard(path: str):
    """Hold an exclusive lock on the shard's lock file for the life of the process (refuse if another holds it)."""
    import fcntl
    os.makedirs(os.path.dirname(path), exist_ok=True)
    f = open(path, "a", encoding="utf-8")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        raise RunRefused(f"another process holds {path}: this shard is already running") from None
    return f


# ------------------------------------------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", required=True, choices=ALLOWED_PROFILES)
    ap.add_argument("--env", required=True, choices=paths.DOMAINS)
    ap.add_argument("--guard", default=None, choices=GUARDS, help="one guard (default tgr_tracker; Stage A: both)")
    ap.add_argument("--guards", default=None, help="Stage A: comma list (default tgr_frozen,tgr_tracker)")
    ap.add_argument("--tasks", default="train", help=f"one of {TASK_SOURCES} (train/val: splits.json labels)")
    ap.add_argument("--task-ids", default=None, help="comma-separated task indices of the source (a subset)")
    ap.add_argument("--trials", type=int, default=None, help="default 3 (train/val); Stage A: 1 (only value)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--tag", default=None, help="train/val: required; Stage A: the cache name (default v2_..._<agent>)")
    ap.add_argument("--max-steps", type=int, default=MAX_STEPS)
    ap.add_argument("--rules-dir", default=None, help="default: from_shieldagent/rules/<env> (frozen TGR)")
    ap.add_argument("--out-root", default=None,
                    help="default: output/online (train/val), output/eval_v2/stage_a (Stage A); under output/")
    ap.add_argument("--cache-root", default=None, help="default: output/_llmcache/<tag> (must be under output/)")
    ap.add_argument("--shard", default=None, help=f"Stage A: i/n, run the tasks at positions p %% n == i (n <= {MAX_SHARDS})")
    ap.add_argument("--spend-root", default=EVAL_V2_DIR, help="Stage A soft stop: spend is counted under this folder")
    ap.add_argument("--later-left-usd", type=float, default=0.0,
                    help="Stage A soft stop: USD of later or concurrent jobs, added to the left estimate of every "
                         "check (default 0)")
    ap.add_argument("--dry-run", action="store_true", help="resolve and print everything, build the guards, stop")
    a = ap.parse_args(argv)
    stage_a = a.tasks == TAU_RETAIL_TRAIN
    pfx = "[v2-stage-a]" if stage_a else "[p10-online]"

    # ---- safety first: refuse writes outside output/ (and, in a dry run, any network) before any runner import
    write_guard.install([OUTPUT_DIR])
    if a.dry_run:
        block_network()
    tasks = task_list(a.env, a.tasks, a.task_ids)
    task_split = task_split_of(a.tasks)
    guards = parse_guards(a.guard, a.guards, stage_a)
    if a.workers < 1:
        raise RunRefused("--workers must be at least 1")
    later_left = a.later_left_usd
    if not (math.isfinite(later_left) and later_left >= 0):
        raise RunRefused(f"--later-left-usd {later_left}: need a number >= 0")
    if not stage_a and later_left != 0:
        raise RunRefused("--later-left-usd is for Stage A (--tasks tau_retail_train) only: the soft stop")
    check_frozen_rules_early(guards, a.env, stage_a, a.rules_dir)
    if stage_a:
        trials = 1 if a.trials is None else a.trials
        if trials != 1:
            raise RunRefused(f"Stage A runs 1 try per task and guard (--trials {trials} refused)")
        shard = parse_shard(a.shard)
        p = resolve_stage_a_paths(a.profile, guards, shard, a.tag, a.out_root or STAGE_A_DIR, a.cache_root,
                                  a.spend_root)
        job_want = job_identity(shard[1], tasks, guards, a.profile, a.env, task_split)
        job_now = read_job_file(p["agent_dir"])
        job_probs = job_problems(p["agent_dir"], job_want, job_now)
        if job_probs:                                   # F1 item 4 (audit A2 W3); a dry run refuses too
            raise RunRefused("mixed shard counts refused: " + "; ".join(job_probs[:3]))
    else:
        if a.tag is None:
            raise RunRefused("--tag is required for --tasks train/val")
        if a.shard is not None:
            raise RunRefused("--shard is for Stage A (--tasks tau_retail_train) only")
        trials = 3 if a.trials is None else a.trials
        shard = (0, 1)
        p = resolve_paths(a.tag, a.env, guards[0], a.out_root or ONLINE_DIR, a.cache_root)

    runner_path.setup()
    import repro_runtime.calls  # noqa: F401  (loaded before activate so its seams are re-pointed; as the copy)
    import repro_runtime.plan  # noqa: F401
    from repro_runtime import calls as calls_module
    from exp_core import models
    models.CACHE_ROOT = p["cache_root"]           # the copy's structured_llm and run_tool_loop read it at call time
    act = models.activate(a.profile, "guard")
    used = {r: act["roles"][r]["model"] for r in ("agent", "user", "guard")}
    if any(m not in ALLOWED_MODELS for m in used.values()):
        raise RunRefused(f"models {used} refused: only {ALLOWED_MODELS}")
    import tau_bench.envs.user as user_mod
    from tau_bench.envs import get_env
    from repro_online import episode
    counter = CallCounter()
    user_mod.completion = episode.timed_user_completion(counter.wrap("user", models.make_completion("user")))
    agent_completion = counter.wrap("agent", models.make_completion("agent"))
    user_model = act["roles"]["user"]["model"]
    # probe env for the tool schemas and the policy: user_strategy "human" makes no LLM call (part1.md 5.7)
    with contextlib.redirect_stdout(io.StringIO()):
        probe = get_env(a.env, user_strategy="human", user_model=user_model, user_provider="azure",
                        task_split=task_split, task_index=0)
    tools_info, wiki = probe.tools_info, probe.wiki
    if stage_a and len(probe.tasks) != TAU_RETAIL_TRAIN_N:
        raise RunRefused(f"τ-bench retail train split has {len(probe.tasks)} tasks, expected {TAU_RETAIL_TRAIN_N}")
    got = tools_sha256(tools_info)
    built, infos = {}, {}
    for g in guards:
        built[g], infos[g] = build_guard(g, a.env, tools_info, a.rules_dir)
        rdir = infos[g]["rules_dir"]
        with open(os.path.join(rdir, "manifest.json"), encoding="utf-8") as f:
            want = json.load(f)["input"]["tools_sha256"]
        if got != want:
            raise RunRefused(f"tool schemas {got} differ from the rule set's tools_sha256 {want}")
        prob = frozen_rules_problem(g, a.env, stage_a, infos[g]["rule_set_sha256"])    # every mode for tgr_frozen
        if prob:
            raise RunRefused(f"{prob}; rules dir {rdir}")
    # the copied τ-bench tools and data modules, in the main thread before any worker (audit A2 blocker, F1 item 1)
    from state_tracker import tau_copy
    preloaded = dict(tau_copy.preload(a.env), thread="main, before the workers")
    router = None
    if stage_a:
        router = JudgeRouter({g: p["guards"][g]["structured_cache"] for g in guards})
        router.install(calls_module)              # dry run: no LLM object is built, so any judge call would fail

    import tau_bench
    plan = {"argv": sys.argv, "profile": a.profile, "models": used, "env": a.env,
            "tasks_label": None if (a.task_ids and not stage_a) else a.tasks, "task_split": task_split,
            "trials": trials, "workers": a.workers, "max_steps": a.max_steps, "cap": 3,
            "splits_file": None if stage_a else SPLITS_FILE, "models_CACHE_ROOT": models.CACHE_ROOT,
            "tau_bench": tau_bench.__file__, "runner_dir": runner_path.RUNNER_DIR, "tools_sha256": got,
            "probe_user_strategy": "human (no LLM call)",
            "user_call_at_env_build": "kept: get_env(user_strategy='llm') per conversation, as in every earlier run "
                                      "(one thrown-away user call, counted in usage_roles.user)",
            "tau_copy_preloaded": preloaded,
            "write_guard": {"installed": write_guard.installed(), "allowed": [OUTPUT_DIR]}}
    if not stage_a:
        g = guards[0]
        done_units = set()
        if os.path.exists(p["episodes"]):
            for line in open(p["episodes"], encoding="utf-8"):
                r = json.loads(line)
                if r.get("error") is None:
                    done_units.add((r["task_index"], r["trial"]))
        units = [(t, k, g) for k in range(trials) for t in tasks if (t, k) not in done_units]
        plan.update({"guard": g, "tasks": tasks, "units_to_run": len(units), "already_done": len(done_units),
                     "paths": p, "guard_info": infos[g]})
        episodes_of = {g: p["episodes"]}
        out_dirs = {g: p["out_dir"]}
        gate = progress = None
    else:
        all_units = plan_units(tasks, trials, guards, shard[1])
        plan_keys = {(g, t, k) for t, k, g in all_units}
        progress = JobProgress({g: p["guards"][g]["out_dir"] for g in guards}, plan_keys,
                               {"profile": a.profile, "env": a.env, "task_split": task_split},
                               PRIOR_USD_PER_UNIT.get(a.profile, 0.025))
        progress.update()
        if progress.problems:
            raise RunRefused(f"the output folders hold lines that do not belong to this job: {progress.problems[:3]}")
        done = progress.done()
        mine = shard_units(all_units, tasks, shard)
        units = [u for u in mine if (u[2], u[0], u[1]) not in done]
        n_sh = shard[1]
        table = {f"{i}/{n_sh}": len(shard_units(all_units, tasks, (i, n_sh))) for i in range(n_sh)}
        covered = sorted(u for i in range(n_sh) for u in shard_units(all_units, tasks, (i, n_sh)))
        spend = soft_stop.spent_report(p["spend_root"])
        plan.update({
            "stage": "A", "agent": p["agent"], "guards": list(guards), "tasks": f"{len(tasks)} tasks: {compact(tasks)}",
            "n_tasks": len(tasks), "units_in_job": len(all_units), "units_in_shard": len(mine),
            "already_done_in_job": len(done), "already_done_in_shard": len(mine) - len(units),
            "units_to_run": len(units), "units_to_run_by_guard": {g: sum(u[2] == g for u in units) for g in guards},
            "first_units": [list(u) for u in units[:8]], "shard": p["shard"], "units_per_shard": table,
            "shards_cover_every_unit_once": covered == sorted(all_units),
            "paths": p, "guard_info": infos,
            "judge_cache_files_now": {g: count_files(p["guards"][g]["structured_cache"]) for g in guards},
            "job": {"file": os.path.join(p["agent_dir"], JOB_FILE), "exists_now": job_now is not None,
                    "n_shards_in_file": None if job_now is None else job_now["n_shards"], "this_process": job_want},
            "soft_stop": {"spend_root": p["spend_root"], "spent_usd_now": round(spend["total_usd"], 4),
                          "unreadable_now": len(spend["unreadable"]), "soft_stop_usd": soft_stop.SOFT_STOP_USD,
                          "finish_if_left_usd": soft_stop.FINISH_IF_LEFT_USD,
                          "prior_usd_per_unit": progress.prior_usd,
                          "this_job_left_now_usd": round(progress.left_estimate(0)[0], 4),
                          "later_left_usd": later_left,
                          "left_estimate_now_usd": round(stage_a_left_usd(progress, 0, later_left), 4),
                          "decide_now": soft_stop.decide(spend["total_usd"], stage_a_left_usd(progress, 0, later_left))}})
        episodes_of = {g: p["guards"][g]["episodes"] for g in guards}
        out_dirs = {g: p["guards"][g]["out_dir"] for g in guards}
    label = "+".join(guards)

    if a.dry_run:
        print(f"{pfx} DRY RUN (no LLM call, nothing written):")
        print(json.dumps(plan, indent=1, default=str))
        judge_calls = sum(router.calls.values()) if router else 0
        print(f"{pfx} LLM calls in this dry run: agent {counter.n['agent']}, user {counter.n['user']}, judge "
              f"{judge_calls}; network attempts blocked {len(NETWORK_ATTEMPTS)} {NETWORK_ATTEMPTS[:5]}; refused "
              f"writes {len(write_guard.REFUSED)}")
        print(f"{pfx} {a.env}/{label} DRY RUN DONE")
        return plan

    lock = _lock_shard(p["lock"]) if stage_a else None       # noqa: F841  (held until the process ends)
    if stage_a:
        plan["job"]["ensured"] = ensure_job_file(p["agent_dir"], job_want)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    for g in guards:
        os.makedirs(out_dirs[g], exist_ok=True)
        json.dump({"argv": sys.argv, "activation": act, "tasks": tasks, "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "wrapper": "predicate_correctness/guard/run_online.py", "plan": plan},
                  open(os.path.join(out_dirs[g], f"run_{stamp}{p.get('shard_suffix', '')}.json"), "w"), indent=1,
                  default=str)
    if router is not None:
        router.build(models, calls_module)
    if stage_a:
        print(f"{pfx} {a.env}/{label} ({a.profile}) start: {len(units)} episodes ({plan['already_done_in_job']} "
              f"already done in the job), {len(tasks)} tasks × {trials} trials × {len(guards)} guards, shard "
              f"{p['shard']}; output {p['agent_dir']}; later jobs ${later_left:.2f} added to the left estimate",
              flush=True)
    else:
        print(f"{pfx} {a.env}/{label} ({a.profile}) start: {len(units)} episodes ({plan['already_done']} already "
              f"done), {len(tasks)} tasks × {trials} trials; output {p['episodes']}", flush=True)
    started = time.time()

    def run_one(unit):
        t, k, g = unit
        models.reset_episode_usage()
        try:
            # inside the try (F1 item 5): a failed env build (it makes the thrown-away user call) gives an error line
            env = get_env(a.env, user_strategy="llm", user_model=user_model, user_provider="azure",
                          task_split=task_split, task_index=t)
            with (router.use(g) if router is not None else contextlib.nullcontext()):
                rec = episode.run_episode(env, agent_completion, tools_info, wiki, built[g], t,
                                          max_num_steps=a.max_steps)
            rec["error"] = None
        except Exception as e:  # noqa: BLE001 - recorded as a failed episode (as the copy)
            rec = {"task_index": t, "reward": 0.0, "error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()}
        u = json.loads(json.dumps(models.episode_usage()))
        rec["usage_roles"] = u
        if "cost" in rec:
            rec["cost"]["agent"], rec["cost"]["user"] = u["agent"]["cost"], u["user"]["cost"]
        rec.update({"env": a.env, "guard": g, "trial": k, "profile": a.profile, "models": used,
                    "task_split": task_split})
        with _write_lock:
            with open(episodes_of[g], "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return rec

    gate = None
    live: dict = {}                  # run_units' live counts (the left estimate leaves out the units running here)
    if stage_a:
        def left_fn():
            return stage_a_left_usd(progress, live.get("running", 0), later_left)
        gate = soft_stop.Gate(left_fn, scanner=soft_stop.SpendScanner(p["spend_root"]))

    def on_result(r, n):
        c = r.get("cost") or {}
        tail = ""
        if gate is not None and gate.last is not None:
            tail = f" spent ${gate.last['spent']:.2f}"
        print(f"{pfx} {a.env}/{r['guard']} task {r['task_index']} trial {r['trial']}: reward {r['reward']} "
              f"blocks {r.get('n_blocks')} cap {r.get('n_cap_overrides')} err {r['error'] is not None} "
              f"cost {sum(c.values()):.4f} {r.get('seconds')}s ({n}/{len(units)}, {time.time() - started:.0f}s)"
              f"{tail}", flush=True)

    def on_stop(reason, spent, left):
        print(f"{pfx} STOPPED (soft stop): {reason}; no new unit starts, running units finish", flush=True)

    st = run_units(units, run_one, a.workers, gate, on_result, on_stop if stage_a else None, state=live)
    extra = ""
    if stage_a:
        js = {g: router.llms[g].usage_report() for g in guards}
        print(f"{pfx} judge calls per guard {router.calls}; judge cache use {json.dumps(js, default=str)}", flush=True)
        if st["not_started"]:
            extra = f"; soft stop: {st['not_started']} units not started"
        final = soft_stop.spent_report(p["spend_root"])                  # F1 item 6: the total at the end
        extra += f"; total spend ${final['total_usd']:.4f} under {p['spend_root']}"
        if final["unreadable"]:
            extra += f" ({len(final['unreadable'])} unreadable lines or files counted 0)"
    print(f"{pfx} {a.env}/{label} DONE: {st['finished']} episodes in {time.time() - started:.0f}s; refused writes "
          f"{len(write_guard.REFUSED)}{extra}", flush=True)
    return plan


if __name__ == "__main__":
    main()
