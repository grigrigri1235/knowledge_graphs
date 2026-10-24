"""Tracker v3, part 13 step 3: the online runner wrapper for the paid runs of p14 (docs/planning/tracker_v3/p13.md,
p14.md; overview Q11-Q14). The eval v2 runner (guard/run_online.py) is not changed; this file only imports it.

What it runs
  - the strong agent only: profile luna-dev (gpt-6-luna for the agent, the user simulator and the guard role);
  - five arms, each a guard for the copied episode loop (repro_online/episode.py::run_episode, unchanged):
      none             the copy's own: repro_online.guards.build("none", domain, tools_info)
      direct           the copy's DirectGuard with the policy loader of step 1 (guard/direct_facts_v3.py
                       direct_guard: the copy's __init__ opens a policy_docs/ folder the copy does not have)
      direct_facts_v3  guard/direct_facts_v3.py build(domain) (Direct + the "Facts checked by code" block)
      tgr_frozen       frozen TGR, fresh, built exactly as the v2 runner builds it (guard/run_online.py
                       build_guard("tgr_frozen", ...) -> the copy's exp_core/run_online.py build_guard("tgr", ...))
      tgr_tracker_v3   guard/tgr_tracker_v3.py build(domain, facts="v3", meaning="tiny", messages="rule") (Q11),
                       the tiny questions online (state_tracker/v3/questions.py RealBackend: gpt-6-luna, low effort,
                       as p12). Their cost is added to the guard record's usage (rec["usage"]["cost_usd"]), so it is
                       counted once, in the episode line's guard cost. Their answers go to a fresh store inside the
                       run folder (questions/answers_shard<i>of<n>.jsonl), never to questions_answers.jsonl.
    One judge LLM object (and cache folder) per LLM arm (the v2 JudgeRouter), so no answer is shared across arms.
    A structured call from the none or tgr_tracker_v3 arm fails (no LLM object for it).
  - the tasks: output/eval_v3/online_tasks.json (sha256 TASKS_FILE_SHA256, written by the tasks-file command): the 99
    hard tasks we may use, from τ-bench's test task files, each marked val or train (the partner's split,
    from_shieldagent/splits/splits.json): val 23 retail + 10 airline, train 46 retail + 20 airline. The partner's test
    group is refused everywhere (the file has none, a task id of it is refused, every task is re-checked against
    splits.json at start).
  - unit order: one list with both domains (the file's order: val first, then train; in each block the domains are
    interleaved evenly), try by try (every task's try 1 first), the 5 arms of a (task, try) next to each other, the
    first arm rotating with the task position (arm order = ARMS rotated by position mod 5). The shards split the tasks
    by position (p mod n == i), so each shard has both domains and every try of its tasks.
  - steps (soft_stop_v3.STEP_LIMITS_USD): B1 smoke (exactly 2 tasks, fixed: the first retail and the first airline
    task of the file's order, retail:4 and airline:4, both val; 1 try = trial index 0), B2 (99 tasks x 3
    tries), B2v (the extra-tries mode: the 33 val tasks only, tries 4-6 = trial indices 3-5, needs --b2v-approved,
    which raises the cap to $110). B3 (p14, optional; approval_request_B3_draft.md): the 64 Stage A retail tasks with
    3 or more expected actions x 1 try (trial index 0), from τ-bench's retail TRAIN task file (get_env(...,
    task_split="train")), listed in output/eval_v3/b3_tasks.json (B3_TASKS_FILE_SHA256, written by b3-tasks-file);
    1-4 shards, hard limit $20 (soft_stop_v3.STEP_LIMITS_USD["B3"]), the same $95 cap and the same stops. The train
    file is not in the partner's split (it covers only the test file), so no B3 task can be of its test group; B3
    lines carry task_split "train" and task_group "stage_a".

Run folder: output/eval_v3/<step>/<run_id>/, run id <step>_<UTC time>_<uuid8> (new-id prints one)
  run.json            written once by the first shard process (atomic): the plan identity (step, tasks, tries,
                      shards, arms, models, approval quote, cap, limit), the command, the sha256 of every guard input,
                      the soft stop's settings. Every later process must have the same plan and the same input
                      hashes, or it is refused.
  pids.txt            one line per process: pid, process group, shard, start time
  <arm>/episodes_shard<i>of<n>.jsonl   one line per conversation (append only), the v2 runner's fields plus arm,
                      task_group (val/train), step, run_id, unit_attempt, shard
  dropped_groups_shard<i>of<n>.jsonl   (task, try) groups dropped from all arms (a unit failed twice)
  questions/answers_shard<i>of<n>.jsonl   the tiny-question answers of this run (fresh)
  live/shard<i>of<n>.json             running units and units left in open groups (the reserve of every shard)
  shard<i>of<n>_<UTC time>.json       each process's start record (argv, guards built, plan of the shard)
  STOP                written by the main chat: no new (task, try) group starts
  Judge caches: output/_llmcache/v3_<run_id>/<arm>/structured (fresh: the folder must not exist when the run starts).

Stops (guard/soft_stop_v3.py SoftStopV3): before the first unit, can_start_step(); before each new (task, try)
group, can_start_group(running, left in open groups, the group's units, run folder): the STOP file, the step's hard
limit, the v3 cap, the reserve (all shards' live counts), the cost and error rules; plus the runner's own rule: the
3rd v3 state error (checks of the tgr_tracker_v3 arm with a state error or a fact error, all shards' lines). A stop
is sticky: no new group starts; open groups finish all 5 arms (paired). A failed unit (an error line) is re-run once
at once; if it fails again, its (task, try) group is dropped from all arms (not-started arms are skipped; the group
is listed in dropped_groups_*.jsonl; its lines stay, they hold spend). Resume: the same command again, after the main
chat COPIED (cp, never mv) the shard files to *.jsonl.before_resume (files are append only): a unit with a line
without error is done; a unit with two error lines drops its group; a group with a done unit is open and finishes
(even under a stop). The run is refused if a backup under the step folder has no live file of at least the same size
with the same first bytes (it was moved), and each backup's spend counts as the larger of backup and live.

Fixes after audits B and C (p13): one process per shard (an flock lock file locks/shard<i>of<n>.lock in the step
folder, held for the run; a second process exits non-zero before any call); before each unit of an open group (and
before a re-run) the step's hard limit and the cap are checked (a refused unit drops its group); a failed re-run is
skipped when its group is already dropped; a failed real tiny-question call (questions.RealCallFailed) makes the v3
unit an error line (with its cost so far), re-run once / drop group as the other arms, and is not a v3 state error;
the state-error count covers every run folder of the step; error lines of direct, direct_facts_v3 and tgr_frozen
carry their judge cost (usage_roles.guard_judge, counted by v2's line_cost); a failed line write cancels the queued
units and stops the run; --b2v-approved only with --step B2v; outside the sandbox B1 runs exactly its fixed 2 tasks
(b1_tasks: the first retail and the first airline task of the file) x 1 try and B2 / B2v all their tasks x 3 tries
(--tries and --task-ids refused); --workers <= 8; litellm's
price map is local (LITELLM_LOCAL_MODEL_COST_MAP); a dry run lists what the network block refused; B1's pass check
(b1-check, also printed at the end of a B1 run) needs 0 Direct + facts facts failures and 0 v3 state errors.

Safety: the write guard (guard/write_guard.py) refuses writes outside predicate_correctness/output/ and any access
under ~/ShieldAgent; models must be gpt-6-luna; the tool schemas must give the rule sets' tools_sha256; the frozen
rule sets are checked; the eval v2 manifest (state_tracker/v3/frozen.py) is checked at start; a real run needs the
user's approval words (--approval, the rules of questions.check_real_mode) and its stdout must be the log file
output/logs/v3_<step>_<run_id>_s<i>.log. Sandbox runs: an out root under output/eval_v3/dryrun/ blocks the network
(questions.block_network), refuses every write outside output/eval_v3/dryrun/, uses fake tiny-question answers, and
never builds a real client (the caller puts a fake client in exp_core.models._base_client; without one, every call
fails). --dry-run: plan only (network blocked, no client, guards built, nothing written).

Commands (run from predicate_correctness/, ~/venvs/tau-bench/bin/python -B, PYTHONDONTWRITEBYTECODE=1):
  python -B -m guard.run_online_v3 tasks-file [--check]          write (or check) output/eval_v3/online_tasks.json
  python -B -m guard.run_online_v3 b3-tasks-file [--check]       write (or check) output/eval_v3/b3_tasks.json
  python -B -m guard.run_online_v3 new-id --step B2              print a fresh run id
  python -B -m guard.run_online_v3 run --step B2 --run-id <id> --shard <i>/4 --workers 6 --approval "<words>"
  python -B -m guard.run_online_v3 b1-check --run-id <id>                  B1's pass check ($0, reads files only)
Find processes with: ps -eo pid,pgid,etimes,cmd | grep '[r]un_online_v3'

Our code. Imports the runner copy through guard/runner_path.py (lazily, inside the commands), never imports gold code
or any metrics module, and makes no LLM call itself.
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import fcntl
import hashlib
import io
import json
import os
import re
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

sys.dont_write_bytecode = True
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")   # litellm must not fetch its price map (audit B #10)

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "guard"

from guard import soft_stop, soft_stop_v3, write_guard                      # noqa: E402
from state_tracker import paths                                            # noqa: E402

PFX = "[v3-online]"
NAME = "run_online_v3"
VERSION = "v3.p13.3"
PC_DIR = paths.PC_DIR
OUTPUT_DIR = paths.OUTPUT_DIR
V3_ROOT = soft_stop_v3.V3_ROOT                                   # output/eval_v3
DRYRUN_ROOT = os.path.join(V3_ROOT, soft_stop_v3.DRYRUN_DIRNAME)  # output/eval_v3/dryrun
LLMCACHE_DIR = os.path.join(OUTPUT_DIR, "_llmcache")
LOGS_DIR = paths.LOGS_DIR
TASKS_REL = "output/eval_v3/online_tasks.json"
TASKS_FILE = os.path.join(PC_DIR, *TASKS_REL.split("/"))
TASKS_FILE_SHA256 = "5f7b9b71c727531c29cbe1ab8e7189b4bcf67195bb5b78f02437f98d08baf96e"
SPLITS_FILE = paths.SPLITS_FILE
B3_TASKS_REL = "output/eval_v3/b3_tasks.json"                   # B3 only (p14, optional)
B3_TASKS_FILE = os.path.join(PC_DIR, *B3_TASKS_REL.split("/"))
B3_TASKS_FILE_SHA256 = "0394a99ad08d3c832419f63333bc22b78096b993af5fb39c36c20a47917b33ff"
B3_GROUP = "stage_a"                                              # task_group of B3 lines (not a partner group)
B3_TASK_SPLIT = "train"                                           # τ-bench's retail train task file (Stage A)
B3_MIN_ACTIONS = 3
B3_N_TRAIN = 500
B3_BUILD = "v3.p14.b3"

PROFILE = "luna-dev"
ALLOWED_MODELS = ("gpt-6-luna",)
ARMS = ("none", "direct", "direct_facts_v3", "tgr_frozen", "tgr_tracker_v3")
LLM_ARMS = ("direct", "direct_facts_v3", "tgr_frozen")           # structured calls (one judge cache each)
V3_ARM = "tgr_tracker_v3"
V3_SWITCHES = {"facts": "v3", "meaning": "tiny", "messages": "rule"}
QUESTION_MODEL, QUESTION_EFFORT = "gpt-6-luna", "low"
DOMAINS = ("retail", "airline")
GROUPS = ("val", "train")
WANT_COUNTS = {"val": {"retail": 23, "airline": 10}, "train": {"retail": 46, "airline": 20}}
TASK_SPLIT = "test"                                               # τ-bench's test task files
MAX_STEPS = 30
MAX_SHARDS = 4
UNIT_ATTEMPTS = 2                                                 # a failed unit is re-run once
STATE_ERROR_STOP = 3                                              # the 3rd v3 state error stops new groups
MAX_WORKERS = 8                                                   # per shard (audit B #8)
TINY_CALL_FAILURES = ("RealCallFailed",)                          # questions.py: a real tiny call failed 3 times
B1_POINT_USD = 0.12                                               # p14: B1's point estimate, 10 conversations
B1_CONVERSATIONS = 10
CONTENT_FILTER_RE = re.compile(r"content[ _-]?filter|content[ _-]?policy|responsibleaipolicy", re.I)
STEPS: Dict[str, dict] = {
    "B1": {"tries": 1, "first_try": 0, "groups": ("val", "train"), "n_tasks": 2, "shards": (1,),
           "max_calls": 2000},
    "B2": {"tries": 3, "first_try": 0, "groups": ("val", "train"), "n_tasks": 99, "shards": (1, 2, 3, 4),
           "max_calls": 40000},
    "B2v": {"tries": 3, "first_try": 3, "groups": ("val",), "n_tasks": 33, "shards": (1, 2, 3, 4),
            "max_calls": 15000},
    "B3": {"tries": 1, "first_try": 0, "groups": (B3_GROUP,), "n_tasks": 64, "shards": (1, 2, 3, 4),
           "max_calls": 10000},
}
RUN_ID_RE = re.compile(r"^(B1|B2|B2v|B3)_(\d{8}T\d{6}Z)_([0-9a-f]{8})$")
TIMING_KEYS = ("seconds", "api_seconds", "latency", "seconds_facts")   # left out when records are compared
PLACEHOLDER_RE = re.compile(r"[<>]")

_write_lock = threading.Lock()


class RunRefused(SystemExit):
    """A safety rule refuses the run."""


def _under(path: str, root: str) -> bool:
    p, r = os.path.realpath(path), os.path.realpath(root)
    return p == r or p.startswith(r + os.sep)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def canonical(x: Any) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def utc_stamp(t: Optional[float] = None) -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(t))


# ================================================================================================ the tasks file

def load_splits(path: str = SPLITS_FILE) -> Dict[str, Dict[str, str]]:
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return {dom: dict(d[dom]["split"]) for dom in DOMAINS}


def interleave(by_domain: Dict[str, List[int]]) -> List[Tuple[str, int]]:
    """Both domains in one list, spread evenly: item j of a domain with n items sits at (j + 0.5) / n."""
    keyed = [((j + 0.5) / len(ids), DOMAINS.index(d), d, t) for d, ids in by_domain.items() for j, t in enumerate(ids)]
    return [(d, t) for _, _, d, t in sorted(keyed)]


def tau_test_tasks() -> Dict[str, Tuple[list, str]]:
    """{domain: (τ-bench test tasks, sha256 of the task file)} from the venv's τ-bench (what get_env runs)."""
    import tau_bench
    from tau_bench.envs.airline.tasks_test import TASKS as airline
    from tau_bench.envs.retail.tasks_test import TASKS_TEST as retail
    base = os.path.join(os.path.dirname(tau_bench.__file__), "envs")
    return {"retail": (retail, sha256_file(os.path.join(base, "retail", "tasks_test.py"))),
            "airline": (airline, sha256_file(os.path.join(base, "airline", "tasks_test.py")))}


def build_tasks_doc() -> dict:
    """The tasks file content (deterministic: no time in it)."""
    splits = load_splits()
    tau = tau_test_tasks()
    order: List[Tuple[str, str, int]] = []
    for g in GROUPS:
        by = {d: sorted(int(k) for k, v in splits[d].items() if v == g) for d in DOMAINS}
        order += [(g, d, t) for d, t in interleave(by)]
    tasks = []
    for pos, (g, d, t) in enumerate(order):
        task = tau[d][0][t]
        dump = task.model_dump()
        tasks.append({"pos": pos, "domain": d, "task_index": t, "group": g, "user_id": dump.get("user_id"),
                      "task_sha256": sha256_text(canonical(dump))})
    counts = {g: {d: sum(1 for x in tasks if x["group"] == g and x["domain"] == d) for d in DOMAINS} for g in GROUPS}
    if counts != WANT_COUNTS:
        raise RunRefused(f"task counts {counts} != {WANT_COUNTS}")
    if any(splits[x["domain"]][str(x["task_index"])] not in GROUPS for x in tasks):
        raise RunRefused("a task of the partner's test group got into the task list")
    return {"written_by": f"guard/run_online_v3.py tasks-file ({VERSION})",
            "what": "the 99 hard tasks we may use (p14.md, Q12): τ-bench test-split tasks of the partner's val and "
                    "train groups; the partner's test group is never used",
            "task_split": TASK_SPLIT, "groups": list(GROUPS), "counts": counts, "n_tasks": len(tasks),
            "order": "val block first, then train; in each block both domains interleaved evenly "
                     "((j + 0.5) / n per domain); pos is the run position of the task",
            "source": {"splits": {"path": "from_shieldagent/splits/splits.json", "sha256": sha256_file(SPLITS_FILE)},
                       "tau_bench_tasks_test": {d: {"path": f"tau_bench (venv) envs/{d}/tasks_test.py",
                                                    "sha256": tau[d][1], "n": len(tau[d][0])} for d in DOMAINS},
                       "task_sha256": "sha256 of the task's model_dump() as sorted-key compact JSON"},
            "tasks": tasks}


def tasks_doc_text(doc: dict) -> str:
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def load_tasks_file(path: str = TASKS_FILE, want_sha256: Optional[str] = TASKS_FILE_SHA256) -> dict:
    """The tasks file, sha256 checked, every task re-checked against splits.json (val or train only)."""
    got = sha256_file(path)
    if want_sha256 is not None and got != want_sha256:
        raise RunRefused(f"{path}: sha256 {got} != recorded {want_sha256}")
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    splits = load_splits()
    for x in doc["tasks"]:
        lab = splits[x["domain"]].get(str(x["task_index"]))
        if lab != x["group"] or lab not in GROUPS:
            raise RunRefused(f"task {x['domain']}:{x['task_index']} is {lab!r} in splits.json, the file says "
                             f"{x['group']!r}: refused (never the partner's test group)")
    if doc.get("counts") != WANT_COUNTS or len(doc["tasks"]) != 99:
        raise RunRefused(f"{path}: counts {doc.get('counts')} (99 tasks expected)")
    doc["sha256"] = got
    return doc


def parse_task_ids(spec: Optional[str]) -> Optional[List[Tuple[str, int]]]:
    """'retail:5,airline:3' -> [("retail", 5), ("airline", 3)]."""
    if spec is None:
        return None
    out = []
    for part in [p.strip() for p in spec.split(",") if p.strip()]:
        m = re.fullmatch(r"(retail|airline):(\d+)", part)
        if not m:
            raise RunRefused(f"--task-ids {spec!r}: use domain:index, e.g. retail:5,airline:3")
        out.append((m.group(1), int(m.group(2))))
    if not out or len(set(out)) != len(out):
        raise RunRefused(f"--task-ids {spec!r}: no task, or a task repeated")
    return out


def step_task_split(step: str) -> str:
    """τ-bench's task file of a step: "train" for B3, "test" for B1 / B2 / B2v."""
    return B3_TASK_SPLIT if step == "B3" else TASK_SPLIT


def tau_train_tasks() -> Tuple[list, str]:
    """(τ-bench's retail train tasks, sha256 of tasks_train.py) from the venv's τ-bench (what get_env runs)."""
    import tau_bench
    from tau_bench.envs.retail.tasks_train import TASKS_TRAIN as retail
    base = os.path.join(os.path.dirname(tau_bench.__file__), "envs")
    return retail, sha256_file(os.path.join(base, "retail", "tasks_train.py"))


def build_b3_tasks_doc() -> dict:
    """The B3 tasks file content (deterministic): every retail train task with B3_MIN_ACTIONS or more expected
    actions (len(task.actions)), in task index order."""
    tau, sha = tau_train_tasks()
    if len(tau) != B3_N_TRAIN:
        raise RunRefused(f"τ-bench's retail train file has {len(tau)} tasks, not {B3_N_TRAIN}")
    tasks = []
    for t, task in enumerate(tau):
        dump = task.model_dump()
        n = len(dump["actions"])
        if n < B3_MIN_ACTIONS:
            continue
        tasks.append({"pos": len(tasks), "domain": "retail", "task_index": t, "group": B3_GROUP,
                      "user_id": dump.get("user_id"), "task_sha256": sha256_text(canonical(dump)),
                      "n_expected_actions": n})
    if len(tasks) != STEPS["B3"]["n_tasks"]:
        raise RunRefused(f"B3: {len(tasks)} train tasks with {B3_MIN_ACTIONS}+ expected actions, expected "
                         f"{STEPS['B3']['n_tasks']}")
    return {"written_by": f"guard/run_online_v3.py b3-tasks-file ({B3_BUILD})",
            "what": "B3 (p14, optional): the Stage A retail tasks with 3 or more expected actions, from τ-bench's "
                    "retail train task file (the 500 easy tasks of eval v2 Stage A); the train file is not in the "
                    "partner's split (its test group is never used)",
            "task_split": B3_TASK_SPLIT, "groups": [B3_GROUP], "counts": {B3_GROUP: {"retail": len(tasks)}},
            "n_tasks": len(tasks),
            "order": "τ-bench train task index, ascending; pos is the run position of the task",
            "source": {"tau_bench_tasks_train": {"retail": {"path": "tau_bench (venv) envs/retail/tasks_train.py",
                                                            "sha256": sha, "n": len(tau)}},
                       "selection": f"len(task.actions) >= {B3_MIN_ACTIONS} (τ-bench's expected actions)",
                       "task_sha256": "sha256 of the task's model_dump() as sorted-key compact JSON"},
            "tasks": tasks}


def load_b3_tasks_file(path: Optional[str] = None, want_sha256: Optional[str] = B3_TASKS_FILE_SHA256) -> dict:
    """The B3 tasks file, sha256 checked and equal to a fresh build from τ-bench's train file (retail only, train
    split, 64 tasks with 3+ expected actions, each task's sha256)."""
    path = path or B3_TASKS_FILE
    got = sha256_file(path)
    if want_sha256 is not None and got != want_sha256:
        raise RunRefused(f"{path}: sha256 {got} != recorded {want_sha256}")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if text != tasks_doc_text(build_b3_tasks_doc()):
        raise RunRefused(f"{path} differs from a fresh build from τ-bench's retail train file: refused")
    doc = json.loads(text)
    if doc.get("task_split") != B3_TASK_SPLIT or any(x["domain"] != "retail" or x["group"] != B3_GROUP
                                                     for x in doc["tasks"]):
        raise RunRefused(f"{path}: B3 runs retail train-file tasks only")
    doc["sha256"] = got
    return doc


def select_b3_tasks(doc: dict, task_ids: Optional[List[Tuple[str, int]]]) -> List[dict]:
    """B3's tasks, in the file's order (all 64, or a sandbox's --task-ids, each in the file)."""
    by_key = {(x["domain"], x["task_index"]): x for x in doc["tasks"]}
    if task_ids is not None:
        bad = [f"{d}:{t}" for d, t in task_ids if (d, t) not in by_key]
        if bad:
            raise RunRefused(f"tasks {bad} are not in the B3 task list (retail train tasks with "
                             f"{B3_MIN_ACTIONS}+ expected actions): refused")
        keys = set(task_ids)
        out = [x for x in doc["tasks"] if (x["domain"], x["task_index"]) in keys]
    else:
        out = list(doc["tasks"])
        if len(out) != STEPS["B3"]["n_tasks"]:
            raise RunRefused(f"B3: {len(out)} tasks, expected {STEPS['B3']['n_tasks']}")
    if any(x["domain"] != "retail" or x["group"] != B3_GROUP for x in out):
        raise RunRefused("B3 runs retail Stage A (train file) tasks only")
    return [dict(x) for x in out]


def b1_tasks(doc: dict) -> List[Tuple[str, int]]:
    """B1's fixed pair: the first retail and the first airline task in the file's order (retail:4, airline:4)."""
    first: Dict[str, Tuple[str, int]] = {}
    for x in doc["tasks"]:
        first.setdefault(x["domain"], (x["domain"], x["task_index"]))
    return [first["retail"], first["airline"]]


def select_tasks(doc: dict, step: str, task_ids: Optional[List[Tuple[str, int]]]) -> List[dict]:
    """The tasks of a step, in the file's order. Refuses any task that is not in the file (the partner's test group
    is not in it)."""
    if step == "B3":                                # its own list (τ-bench's train file, not in splits.json)
        return select_b3_tasks(doc, task_ids)
    cfg = STEPS[step]
    by_key = {(x["domain"], x["task_index"]): x for x in doc["tasks"]}
    splits = load_splits()
    if task_ids is not None:
        bad = [k for k in task_ids if k not in by_key]
        if bad:
            labels = {f"{d}:{t}": splits.get(d, {}).get(str(t)) for d, t in bad}
            raise RunRefused(f"tasks {labels} are not in the online task list (val / train only; the partner's test "
                             f"group is never run): refused")
        keys = set(task_ids)
        out = [x for x in doc["tasks"] if (x["domain"], x["task_index"]) in keys]
    else:
        if step == "B1":                           # the fixed pair (a sandbox may give its own with --task-ids)
            return select_tasks(doc, step, b1_tasks(doc))
        out = list(doc["tasks"])
    out = [x for x in out if x["group"] in cfg["groups"]] if task_ids is None else out
    bad = [f"{x['domain']}:{x['task_index']}" for x in out if x["group"] not in cfg["groups"]]
    if bad:
        raise RunRefused(f"{step} runs {cfg['groups']} tasks only; {bad} refused")
    if step == "B1":
        doms = sorted(x["domain"] for x in out)
        if doms != ["airline", "retail"]:
            raise RunRefused(f"B1 runs exactly 1 retail and 1 airline task (got {doms})")
    elif task_ids is None and len(out) != cfg["n_tasks"]:
        raise RunRefused(f"{step}: {len(out)} tasks, expected {cfg['n_tasks']}")
    for x in out:                                   # belt and braces: splits.json says val or train
        if splits[x["domain"]].get(str(x["task_index"])) not in GROUPS:
            raise RunRefused(f"task {x['domain']}:{x['task_index']} is in the partner's test group: refused")
    return [dict(x) for x in out]


# ================================================================================================ units and shards

def arm_order(pos: int) -> List[str]:
    r = pos % len(ARMS)
    return list(ARMS[r:] + ARMS[:r])


def plan_units(tasks: Sequence[dict], tries: int, first_try: int = 0) -> List[Tuple[str, int, int, str]]:
    """Every unit (domain, task, trial, arm) of the step, in run order: try by try, task by task (the list's order),
    the 5 arms of a (task, try) next to each other, the first arm rotating with the task's position in the list."""
    out = []
    for k in range(first_try, first_try + tries):
        for p, x in enumerate(tasks):
            out += [(x["domain"], x["task_index"], k, a) for a in arm_order(p)]
    return out


def shard_units(units: Sequence[tuple], tasks: Sequence[dict], shard: Tuple[int, int]) -> List[tuple]:
    """The units of shard i of n: the tasks at list positions p with p % n == i (every try and arm of them)."""
    i, n = shard
    pos = {(x["domain"], x["task_index"]): p for p, x in enumerate(tasks)}
    return [u for u in units if pos[(u[0], u[1])] % n == i]


def parse_shard(spec: Optional[str]) -> Tuple[int, int]:
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
    return f"_shard{shard[0]}of{shard[1]}"


def new_run_id(step: str, t: Optional[float] = None) -> str:
    if step not in STEPS:
        raise RunRefused(f"unknown step {step!r} (built: {sorted(STEPS)})")
    return f"{step}_{utc_stamp(t)}_{uuid.uuid4().hex[:8]}"


def check_run_id(step: str, run_id: str) -> None:
    m = RUN_ID_RE.match(run_id or "")
    if not m or m.group(1) != step:
        raise RunRefused(f"--run-id {run_id!r}: use the id of new-id for step {step} (<step>_<UTC time>_<uuid8>)")


def is_sandbox(out_root: str) -> bool:
    return _under(out_root, DRYRUN_ROOT)


def resolve_paths(out_root: str, step: str, run_id: str, shard: Tuple[int, int]) -> dict:
    out_root = os.path.abspath(out_root)
    if not (_under(out_root, V3_ROOT)):
        raise RunRefused(f"--out-root {out_root} is not under {V3_ROOT}")
    if out_root != os.path.realpath(V3_ROOT) and not is_sandbox(out_root):
        raise RunRefused(f"--out-root: {V3_ROOT} (real runs) or a folder under {DRYRUN_ROOT} (sandbox) only")
    sandbox = is_sandbox(out_root)
    run_dir = os.path.join(out_root, step, run_id)
    sfx = shard_suffix(shard)
    cache = (os.path.join(out_root, "_llmcache", f"v3_{run_id}") if sandbox
             else os.path.join(LLMCACHE_DIR, f"v3_{run_id}"))
    return {"out_root": out_root, "sandbox": sandbox, "step_dir": os.path.join(out_root, step), "run_dir": run_dir,
            "run_json": os.path.join(run_dir, "run.json"), "pids": os.path.join(run_dir, "pids.txt"),
            "stop_file": os.path.join(run_dir, soft_stop_v3.STOP_FILENAME),
            "episodes": {a: os.path.join(run_dir, a, f"episodes{sfx}.jsonl") for a in ARMS},
            "dropped": os.path.join(run_dir, f"dropped_groups{sfx}.jsonl"),
            "questions_store": os.path.join(run_dir, "questions", f"answers{sfx}.jsonl"),
            "live": os.path.join(run_dir, "live", f"shard{shard[0]}of{shard[1]}.json"),
            "shard_record": os.path.join(run_dir, f"shard{shard[0]}of{shard[1]}_{utc_stamp()}.json"),
            "cache_root": cache, "structured_cache": {a: os.path.join(cache, a, "structured") for a in LLM_ARMS},
            "log": os.path.join(LOGS_DIR, f"v3_{step}_{run_id}_s{shard[0]}.log"), "shard_suffix": sfx}


# ================================================================================================ guard inputs

def guard_input_files() -> List[str]:
    """Every file a guard of the five arms (or the loop around it) reads, relative to predicate_correctness/."""
    out = set()
    roots = [("from_shieldagent/runner", (".py", ".json", ".md", ".txt")),
             ("from_shieldagent/rules", (".json",)), ("from_shieldagent/policies", (".txt",)),
             ("state_tracker", (".py", ".json")), ("guard", (".py",))]
    for rel, exts in roots:
        base = os.path.join(PC_DIR, *rel.split("/"))
        for dp, dns, fns in os.walk(base):
            dns[:] = sorted(d for d in dns if d != "__pycache__")
            for f in fns:
                if f.endswith(exts):
                    out.add(os.path.relpath(os.path.join(dp, f), PC_DIR).replace(os.sep, "/"))
    out |= {"output/eval_v3/rule_table_retail.json", "output/eval_v3/rule_table_airline.json",
            "output/predicate_types.json", "from_shieldagent/splits/splits.json", "from_shieldagent/SHA256SUMS",
            TASKS_REL}
    return sorted(out)


def guard_inputs_sha256() -> Dict[str, str]:
    got = {rel: sha256_file(os.path.join(PC_DIR, *rel.split("/"))) for rel in guard_input_files()}
    try:
        for d, (_, h) in tau_test_tasks().items():
            got[f"tau_bench(venv)/envs/{d}/tasks_test.py"] = h
    except ImportError:
        pass
    return got


def approval_problem(quote: Any) -> Optional[str]:
    """The rules of questions.check_real_mode for the approval words (without the network rule)."""
    if not isinstance(quote, str) or len(quote.strip()) < 8 or PLACEHOLDER_RE.search(quote) \
            or quote.strip().lower() in ("yes", "approved", "ok", "proceed", "go ahead"):
        return "the user's own approval words for this paid step are needed (--approval, 8+ characters, no <...>)"
    return None


# ================================================================================================ the v3 arm online

class TinyMeter:
    """Per-thread cost of the tiny questions: the backend's budget.spend (real mode: every call's list price, and
    the estimate of a failed attempt) and the backend calls, for the check in progress and for the episode."""

    def __init__(self, backend: Any):
        self.backend = backend
        self._tls = threading.local()
        self.total = {"calls": 0, "usd": 0.0}
        self._lock = threading.Lock()
        inner = backend.answer
        backend.answer = self._answer(inner)
        budget = getattr(backend, "budget", None)
        if budget is not None:
            spend = budget.spend

            def metered_spend(usd, _spend=spend):
                _spend(usd)
                self._add(usd=float(usd))
            budget.spend = metered_spend

    def _st(self) -> dict:
        st = getattr(self._tls, "st", None)
        if st is None:
            st = self._tls.st = {"check": {"calls": 0, "usd": 0.0}, "episode": {"calls": 0, "usd": 0.0}}
        return st

    def _add(self, calls: int = 0, usd: float = 0.0) -> None:
        st = self._st()
        for k in ("check", "episode"):
            st[k]["calls"] += calls
            st[k]["usd"] += usd
        with self._lock:
            self.total["calls"] += calls
            self.total["usd"] += usd

    def _answer(self, inner: Callable) -> Callable:
        def answer(**kw):
            self._add(calls=1)
            try:
                return inner(**kw)
            except Exception as e:  # noqa: BLE001 - remembered for the check, then raised as before
                if is_tiny_call_failure(e):
                    self._st()["failed"] = f"{type(e).__name__}: {e}"[:400]
                raise
        return answer

    def start_episode(self) -> None:
        self._st()["episode"] = {"calls": 0, "usd": 0.0}

    def start_check(self) -> None:
        st = self._st()
        st["check"] = {"calls": 0, "usd": 0.0}
        st["failed"] = None

    def check_failed(self) -> Optional[str]:
        """The failed real tiny-question call of the check in progress (None if none)."""
        return self._st().get("failed")

    def check(self) -> dict:
        return dict(self._st()["check"])

    def episode(self) -> dict:
        return dict(self._st()["episode"])


def is_tiny_call_failure(e: BaseException) -> bool:
    """A failed real tiny-question API call (questions.RealCallFailed, by class name: v3 code is not imported here)."""
    return any(c.__name__ in TINY_CALL_FAILURES for c in type(e).__mro__)


def is_api_fact_error(err: Any) -> bool:
    """A v3 fact error that came from a failed real tiny-question call (not an exception in the fact code)."""
    if not isinstance(err, dict):
        return False
    return err.get("error") in TINY_CALL_FAILURES or any(f"{n}:" in str(err.get("detail") or "")
                                                         for n in TINY_CALL_FAILURES)


class TinyQuestionCallFailed(RuntimeError):
    """A v3 check needed a tiny question whose real API call failed: the unit becomes an error line (re-run once,
    then its group is dropped), as an API error of any other arm."""


def finish_v3_check(rec: dict, meter: "TinyMeter") -> dict:
    """The online wrapper's part of a v3 check: the tiny questions' cost and calls go into the record's usage; a
    failed real tiny-question call raises TinyQuestionCallFailed (audit B #2)."""
    c = meter.check()
    u = rec.setdefault("usage", {"n_llm_calls": 0, "cost_usd": 0.0})
    u["n_llm_calls"] = int(u.get("n_llm_calls") or 0) + c["calls"]
    u["cost_usd"] = round(float(u.get("cost_usd") or 0.0) + c["usd"], 8)
    if c["calls"]:
        by = dict(u.get("calls_by_stage") or {})
        by["tiny_question"] = by.get("tiny_question", 0) + c["calls"]
        u["calls_by_stage"] = by
    rec["tiny_questions"] = {"backend_calls": c["calls"], "cost_usd": round(c["usd"], 8)}
    api = [e for e in ((rec.get("v3") or {}).get("fact_errors") or []) if is_api_fact_error(e)]
    failed = meter.check_failed()
    if failed or api:
        raise TinyQuestionCallFailed(f"a tiny question's API call failed in a v3 check: "
                                     f"{failed or api[0].get('detail')}"[:500])
    return rec


class JudgeMeter:
    """Per-thread judge cost of the LLM arms (audit B #4): wraps the copy's repro_runtime.calls.Meter.add (a pass-
    through: every judge call of Direct, Direct + facts and frozen TGR goes through a Meter), priced as the copy's
    Meter.summary (calls.cost of the tokens; cache hits at their first price). Only error lines use it."""

    def __init__(self):
        self._tls = threading.local()
        self.total = {"calls": 0, "usd": 0.0}
        self._lock = threading.Lock()

    def install(self, calls_module: Any) -> None:
        M = calls_module.Meter
        if getattr(M.add, "_v3_judge_meter", None) is not None:
            M.add = M.add._v3_inner
        inner, price, meter = M.add, calls_module.cost, self

        def add(self_, stage, effort, hit, usage, seconds, n=1):
            out = inner(self_, stage, effort, hit, usage, seconds, n=n)
            try:
                usd = float(price(float((usage or {}).get("input_tokens", 0) or 0),
                                  float((usage or {}).get("output_tokens", 0) or 0)))
            except Exception:  # noqa: BLE001 - the meter never changes the guard's work
                usd = 0.0
            meter._add(int(n or 1), usd)
            return out
        add._v3_judge_meter = self
        add._v3_inner = inner
        M.add = add

    def _st(self) -> dict:
        st = getattr(self._tls, "st", None)
        if st is None:
            st = self._tls.st = {"calls": 0, "usd": 0.0}
        return st

    def _add(self, calls: int, usd: float) -> None:
        st = self._st()
        st["calls"] += calls
        st["usd"] += usd
        with self._lock:
            self.total["calls"] += calls
            self.total["usd"] += usd

    def start_episode(self) -> None:
        self._tls.st = {"calls": 0, "usd": 0.0}

    def episode(self) -> dict:
        return dict(self._st())


def make_answers_hook(sandbox: bool, store_path: str, approval: str, max_usd: float, max_calls: int,
                      log: Callable[[str], None], fake_policy: str = "yes"):
    """(questions.Questions hook, TinyMeter). Sandbox: FakeBackend; real: RealBackend (the user's approval words,
    a dollar budget = the step's hard limit, a call budget). The store is fresh, inside the run folder."""
    from state_tracker.v3 import questions as Q
    if _under(store_path, Q.ANSWERS_PATH) or os.path.abspath(store_path) == os.path.abspath(Q.ANSWERS_PATH):
        raise RunRefused("the tiny-question answers of a p14 run never go to questions_answers.jsonl")
    doc = Q.load_questions()
    if (doc["model"], doc["effort"]) != (QUESTION_MODEL, QUESTION_EFFORT):
        raise RunRefused(f"tiny questions: {doc['model']} / {doc['effort']} != {QUESTION_MODEL} / {QUESTION_EFFORT}")
    if sandbox:
        backend = Q.FakeBackend(fake_policy)
    else:
        backend = Q.RealBackend(approval, max_usd, max_calls, doc=doc, log=log)
    meter = TinyMeter(backend)
    hook = Q.Questions(backend, Q.JsonlStore(store_path), doc=doc, keep_log=False)
    return hook, meter


def build_v3_guard(domain: str, tools_info: list, answers: Any, meter: TinyMeter):
    """The tgr_tracker_v3 arm: guard/tgr_tracker_v3.py's guard (facts v3, meaning tiny, messages rule) behind the
    copy's TGRGuard interface (new_episode / check / commit unchanged); check() adds the tiny questions' cost and
    calls of the check to the record's usage, so the copied loop counts them in the guard's cost."""
    from guard import tgr_tracker_v3 as V3
    from repro_online.guards import TGRGuard, make_step

    class OnlineTGRv3Guard(TGRGuard):
        name = V3_ARM

        def __init__(self):                                     # noqa: D401 - TGRGuard's fields, our TGR object
            self.name = V3_ARM
            self.domain = domain
            self.tgr = V3.build(domain, tools_info, answers=answers, **V3_SWITCHES)
            self.config = self.tgr.config
            self.meter = meter
            self.info = dict(self.tgr.info, arm=V3_ARM, online_wrapper="guard/run_online_v3.py OnlineTGRv3Guard")

        def check(self, state, executed, msg, index):
            self.meter.start_check()
            n = len(state.trace)
            rec = self.tgr.step(state, make_step(executed, msg, index))
            rec["trace_len_before"] = n
            return finish_v3_check(rec, self.meter)        # raises on a failed real tiny-question call

    return OnlineTGRv3Guard()


def build_arm(arm: str, domain: str, tools_info: list, answers: Any = None, meter: Optional[TinyMeter] = None):
    """(guard object, info) of one arm and domain. Needs runner_path.setup() first."""
    if arm == "none":
        from repro_online import guards
        g = guards.build("none", domain, tools_info)
        return g, {"arm": arm, "built_by": "repro_online.guards.build('none', domain, tools_info) (copy)"}
    if arm == "direct":
        from guard import direct_facts_v3 as DF
        g = DF.direct_guard(domain)
        return g, {"arm": arm, "built_by": "guard/direct_facts_v3.py direct_guard(domain): the copy's DirectGuard "
                                           "with the policy loader (check() unchanged)",
                   "class": f"{type(g).__module__}.{type(g).__qualname__}", "effort": g.effort,
                   "policy_sha256": sha256_text(g.policy)}
    if arm == "direct_facts_v3":
        from guard import direct_facts_v3 as DF
        g = DF.build(domain)
        return g, dict(getattr(g, "info", {}), arm=arm)
    if arm == "tgr_frozen":
        from guard import run_online as V2                     # the eval v2 runner's own builder (unchanged)
        g, info = V2.build_guard("tgr_frozen", domain, tools_info)
        return g, dict(info, arm=arm, built_by_v3="guard/run_online.py build_guard('tgr_frozen', ...) (v2 runner)")
    if arm == V3_ARM:
        if answers is None or meter is None:
            raise ValueError("the tgr_tracker_v3 arm needs the answers hook and its meter")
        g = build_v3_guard(domain, tools_info, answers, meter)
        return g, dict(g.info)
    raise ValueError(f"unknown arm {arm!r} (arms: {ARMS})")


# ================================================================================================ progress on disk

def unit_key(r: dict) -> Tuple[str, int, int, str]:
    return (r.get("env"), r.get("task_index"), r.get("trial"), r.get("guard"))


def v3_state_error_checks(rec: dict) -> int:
    """The checks of a tgr_tracker_v3 line with a state error or a fact error of the fact code (a fact error from a
    failed real tiny-question call is left out: the pre-registered stop is for an exception in the fact code)."""
    n = 0
    for at in rec.get("attempts") or []:
        v3 = (at.get("guard") or {}).get("v3") or {}
        fe = [e for e in v3.get("fact_errors") or [] if not is_api_fact_error(e)]
        if v3.get("state_errors") or fe:
            n += 1
    return n


class RunFiles:
    """What the run folder says (all shards): units done (a line without error), error lines per unit, dropped
    groups; and the v3 state errors (checks of the tgr_tracker_v3 arm with a state error or a fact-code error) of
    every run folder of the step (step_dir; audit B #12)."""

    def __init__(self, run_dir: str, step_dir: Optional[str] = None):
        self.run_dir = run_dir
        self.step_dir = step_dir
        self._tail = soft_stop.JsonlTail()
        self.done: set = set()
        self.errors: collections.Counter = collections.Counter()
        self.dropped: Dict[tuple, dict] = {}
        self._v3_err: Dict[str, int] = {}                       # v3 episodes file -> state-error checks
        self.problems: List[str] = []
        self._lock = threading.Lock()

    @property
    def v3_state_errors(self) -> int:
        return sum(self._v3_err.values())

    def _other_runs(self) -> None:
        """The v3 arm's files of the step's other run folders (state errors only)."""
        if not self.step_dir or not os.path.isdir(self.step_dir):
            return
        mine = os.path.realpath(self.run_dir)
        for rd in sorted(os.listdir(self.step_dir)):
            d = os.path.join(self.step_dir, rd, V3_ARM)
            if os.path.realpath(os.path.join(self.step_dir, rd)) == mine or not os.path.isdir(d):
                continue
            for name in sorted(os.listdir(d)):
                if not soft_stop.is_episodes_file(name):
                    continue
                path = os.path.join(d, name)
                recs, restarted = self._tail.read_new(path)
                if restarted:
                    self._v3_err[path] = 0
                self._v3_err[path] = self._v3_err.get(path, 0) + sum(v3_state_error_checks(r) for r in recs
                                                                     if r.get("guard") == V3_ARM)

    def scan(self) -> "RunFiles":
        with self._lock:
            self._other_runs()
            if not os.path.isdir(self.run_dir):
                return self
            for a in ARMS:
                d = os.path.join(self.run_dir, a)
                if not os.path.isdir(d):
                    continue
                for name in sorted(os.listdir(d)):
                    if not soft_stop.is_episodes_file(name):
                        continue
                    bad: List[dict] = []
                    path = os.path.join(d, name)
                    recs, restarted = self._tail.read_new(path, bad=bad)
                    if restarted:
                        self.problems.append(f"{a}/{name} was cut or replaced (episode files are append only)")
                        self._v3_err[path] = 0
                    self.problems += [f"{a}/{name} line {b['line']}: {b['error']}" for b in bad]
                    for r in recs:
                        if r.get("guard") != a:
                            self.problems.append(f"{a}/{name}: a line of arm {r.get('guard')!r}")
                            continue
                        k = unit_key(r)
                        if r.get("error") is None:
                            self.done.add(k)
                        else:
                            self.errors[k] += 1
                        if a == V3_ARM:
                            self._v3_err[path] = self._v3_err.get(path, 0) + v3_state_error_checks(r)
            for name in sorted(os.listdir(self.run_dir)):
                if name.startswith("dropped_groups") and name.endswith(".jsonl"):
                    recs, _ = self._tail.read_new(os.path.join(self.run_dir, name))
                    for r in recs:
                        self.dropped.setdefault((r["env"], r["task_index"], r["trial"]), r)
        return self


def write_line(path: str, rec: dict) -> None:
    with _write_lock:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


def write_atomic_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp_{os.getpid()}_{threading.get_ident()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, default=str)
    os.replace(tmp, path)


def others_live(run_dir: str, mine: str) -> Tuple[int, int]:
    """(running, left in open groups) of the other shards (their live files)."""
    d = os.path.join(run_dir, "live")
    run = left = 0
    if os.path.isdir(d):
        for name in os.listdir(d):
            p = os.path.join(d, name)
            if not name.endswith(".json") or os.path.abspath(p) == os.path.abspath(mine):
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    x = json.load(f)
                run += int(x.get("running", 0))
                left += int(x.get("left_open", 0))
            except (OSError, ValueError, TypeError):
                continue
    return run, left


# ================================================================================================ the group pool

class PoolAborted(RuntimeError):
    """A unit job raised (for example a line could not be written): the queued units were cancelled."""


class GroupPool:
    """Runs the units of one shard on a thread pool, in order, by (task, try) group.

    can_start(units_of_group, running, left_open) -> (ok, reason) is asked before the first unit of each new group
    (under the lock). After a "no", the stop is sticky: no new group starts; units of open groups still start.
    can_start_unit() -> (ok, reason) (optional) is asked before every other unit of an open group and before a re-run:
    a "no" drops the unit's group from all arms (on_drop) and sets the stop (audit B #8).
    run_unit(unit, attempt) -> record (the line written); a record with an error is re-run once (attempt 2) while the
    unit has fewer than UNIT_ATTEMPTS error lines in all and its group is not dropped yet; then its group is dropped:
    on_drop(group, record) once, and its units not started yet are skipped.
    open_groups: groups that already have a line (a resume): they are open from the start and finish, even under a
    stop (audit B #9). stop: a stop that holds from the start (only open groups run).
    If a job raises (a line cannot be written), the queued units are cancelled, the running ones finish, and run()
    raises PoolAborted (audit B #5)."""

    def __init__(self, units: Sequence[tuple], run_unit: Callable, can_start: Callable, workers: int,
                 prior_errors: Optional[Dict[tuple, int]] = None, dropped: Sequence[tuple] = (),
                 on_result: Optional[Callable] = None, on_stop: Optional[Callable] = None,
                 on_drop: Optional[Callable] = None, on_live: Optional[Callable] = None,
                 can_start_unit: Optional[Callable] = None, open_groups: Sequence[tuple] = (),
                 stop: Optional[str] = None):
        self.units = list(units)
        self.run_unit, self.can_start, self.workers = run_unit, can_start, workers
        self.can_start_unit = can_start_unit
        self.prior_errors = dict(prior_errors or {})
        self.on_result, self.on_stop, self.on_drop, self.on_live = on_result, on_stop, on_drop, on_live
        self.group_units: Dict[tuple, int] = collections.Counter(u[:3] for u in self.units)
        self.state: Dict[tuple, str] = {g: "new" for g in self.group_units}
        for g in dropped:
            if g in self.state:
                self.state[g] = "dropped"
        self.not_started_in_group: Dict[tuple, int] = dict(self.group_units)
        self.counts = {"started": 0, "finished": 0, "lines": 0, "not_started": 0, "skipped_dropped": 0,
                       "retries": 0, "dropped_groups": 0, "running": 0, "groups_started": 0, "groups_resumed": 0,
                       "units_refused": 0, "reruns_skipped_dropped": 0, "cancelled": 0}
        for g in open_groups:
            if self.state.get(g) == "new":
                self.state[g] = "open"
                self.counts["groups_resumed"] += 1
        self.stop: Optional[str] = stop
        self.abort: Optional[str] = None
        self._lock = threading.Lock()

    def left_open(self) -> int:
        return sum(n for g, n in self.not_started_in_group.items() if self.state[g] == "open")

    def _live(self) -> None:
        if self.on_live is not None:
            self.on_live(self.counts["running"], self.left_open())

    def _refuse_unit(self, g: tuple, reason: str) -> bool:
        """Under the lock: the unit is refused (money); its group is dropped. True if this dropped the group."""
        self.counts["units_refused"] += 1
        first = self.state[g] != "dropped"
        self.state[g] = "dropped"
        if first:
            self.counts["dropped_groups"] += 1
        if self.stop is None:
            self.stop = reason
            if self.on_stop is not None:
                self.on_stop(reason)
        return first

    def _job(self, u: tuple):
        g = u[:3]
        refused = None
        with self._lock:
            if self.abort is not None:
                self.counts["cancelled"] += 1
                self.not_started_in_group[g] -= 1
                return []
            st = self.state[g]
            if st == "dropped":
                self.counts["skipped_dropped"] += 1
                self.not_started_in_group[g] -= 1
                return []
            if st == "new":
                if self.stop is None:
                    ok, reason = self.can_start(self.group_units[g], self.counts["running"], self.left_open())
                    if not ok:
                        self.stop = reason
                        if self.on_stop is not None:
                            self.on_stop(reason)
                if self.stop is not None:
                    self.state[g] = "skipped"
                else:
                    self.state[g] = "open"
                    self.counts["groups_started"] += 1
            elif st == "open" and self.can_start_unit is not None:
                ok, reason = self.can_start_unit()
                if not ok:
                    self.not_started_in_group[g] -= 1
                    refused = (self._refuse_unit(g, reason), reason)
            if refused is None and self.state[g] == "skipped":
                self.counts["not_started"] += 1
                self.not_started_in_group[g] -= 1
                return []
            if refused is None:
                self.not_started_in_group[g] -= 1
                self.counts["started"] += 1
                self.counts["running"] += 1
                self._live()
        if refused is not None:
            if refused[0] and self.on_drop is not None:
                self.on_drop(g, {"guard": u[3], "error": refused[1], "drop_reason": f"{u[3]}: {refused[1]}"})
            return []
        out = []
        try:
            errors = self.prior_errors.get(u, 0)
            while True:
                rec = self.run_unit(u, errors + 1)
                out.append(rec)
                if rec.get("error") is None:
                    break
                errors += 1
                if errors >= UNIT_ATTEMPTS:
                    with self._lock:
                        first = self.state[g] != "dropped"
                        self.state[g] = "dropped"
                        if first:
                            self.counts["dropped_groups"] += 1
                    if first and self.on_drop is not None:
                        self.on_drop(g, rec)
                    break
                with self._lock:
                    if self.state[g] == "dropped":           # another arm dropped the group: no paid re-run
                        self.counts["reruns_skipped_dropped"] += 1
                        break
                    if self.can_start_unit is not None:
                        ok, reason = self.can_start_unit()
                        if not ok:
                            first = self._refuse_unit(g, reason)
                            refused = (first, reason)
                    if refused is None:
                        self.counts["retries"] += 1
                if refused is not None:
                    if refused[0] and self.on_drop is not None:
                        self.on_drop(g, dict(rec, drop_reason=f"{u[3]} failed once; its re-run {refused[1]}"))
                    break
        except BaseException as e:
            with self._lock:
                if self.abort is None:
                    self.abort = f"{type(e).__name__}: {e}"[:400]
            raise
        finally:
            with self._lock:
                self.counts["running"] -= 1
                self.counts["finished"] += 1
                self._live()
        return out

    def run(self) -> dict:
        ex = ThreadPoolExecutor(max_workers=self.workers)
        try:
            n = 0
            futs = [ex.submit(self._job, u) for u in self.units]
            for fut in as_completed(futs):
                for r in fut.result():
                    n += 1
                    self.counts["lines"] += 1
                    if self.on_result is not None:
                        self.on_result(r, n)
        except BaseException as e:
            with self._lock:
                if self.abort is None:
                    self.abort = f"{type(e).__name__}: {e}"[:400]
                if self.stop is None:
                    self.stop = f"aborted: {self.abort}"
            ex.shutdown(wait=True, cancel_futures=True)       # queued units never start; running ones finish
            raise PoolAborted(f"the run stopped: {self.abort}; queued units cancelled") from e
        ex.shutdown(wait=True)
        return dict(self.counts, stop=self.stop)


# ================================================================================================ sandbox safety

_SANDBOX = {"installed": False}


def install_sandbox() -> None:
    """Sandbox runs: no network (questions.block_network), and no write outside output/eval_v3/dryrun/."""
    from state_tracker.v3 import questions as Q
    Q.block_network()
    if _SANDBOX["installed"]:
        return
    root = os.path.realpath(DRYRUN_ROOT)
    events = {"os.mkdir": 0, "os.rename": 1, "os.replace": 1, "os.remove": 0, "os.rmdir": 0, "os.link": 1,
              "shutil.rmtree": 0}

    def hook(event, args):
        p = None
        if event == "open" and len(args) >= 3:
            mode, flags = args[1], args[2]
            writes = (isinstance(mode, str) and any(c in mode for c in "wax+")) or \
                (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC))
            if writes and isinstance(args[0], (str, bytes, os.PathLike)):
                p = os.fsdecode(args[0])
        elif event in events and len(args) > events[event] and isinstance(args[events[event]],
                                                                         (str, bytes, os.PathLike)):
            p = os.fsdecode(args[events[event]])
        if p is not None and not p.startswith("/dev/"):
            rp = os.path.realpath(p)
            if not (rp == root or rp.startswith(root + os.sep)):
                raise PermissionError(f"sandbox run: write outside {DRYRUN_ROOT} refused ({event} {p})")

    sys.addaudithook(hook)
    _SANDBOX["installed"] = True


class _NoClient:
    """Stands in for the Azure client in a sandbox or dry run without a fake: any use fails (no real client)."""

    def with_options(self, **_):
        return self

    def __getattr__(self, name):
        raise RuntimeError(f"no LLM client in this sandbox / dry run (attribute {name!r})")


def stdout_target() -> Optional[str]:
    try:
        return os.path.realpath(os.readlink("/proc/self/fd/1"))
    except OSError:
        return None


# ---- what the network block refused (audit B #10): a recorder hook added before the block, so it sees each attempt
_NET_SEEN: List[str] = []
_NET_REC = {"installed": False}
_NET_WATCH = ("socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr",
              "socket.getnameinfo", "socket.sendto", "socket.sendmsg", "urllib.Request", "http.client.connect",
              "http.client.send", "socket.__new__")


def _net_recorder(event: str, args: tuple) -> None:
    if not event.startswith(("socket.", "urllib.", "http.client.")) or event not in _NET_WATCH:
        return
    try:
        import socket as _s
        if event == "socket.__new__":
            fam = int(args[1]) if len(args) > 1 else -1
            if fam not in (-1, int(_s.AF_INET), int(getattr(_s, "AF_INET6", _s.AF_INET))):
                return
            what = "AF_INET6" if fam == int(getattr(_s, "AF_INET6", -2)) else ("AF_INET" if fam == int(_s.AF_INET)
                                                                              else "family -1")
        elif event in ("socket.connect", "socket.sendto"):
            what = repr(args[1])[:120] if len(args) > 1 else "?"
        elif event == "http.client.connect":
            what = f"{args[1]}:{args[2]}" if len(args) > 2 else "?"
        else:
            what = repr(args[0])[:120] if args else "?"
        _NET_SEEN.append(f"{event} ({what})")
    except Exception:  # noqa: BLE001 - the recorder never raises
        _NET_SEEN.append(f"{event} (?)")


def install_net_recorder() -> None:
    """Install before questions.block_network (audit hooks run in order; the block raises, so a later hook would not
    see the attempt). If the block is already on, the recorder sees nothing and network_events() is the fallback."""
    if not _NET_REC["installed"]:
        sys.addaudithook(_net_recorder)
        _NET_REC["installed"] = True


def net_seen() -> List[str]:
    return list(_NET_SEEN)


# ---- one process per shard (audit B #3)
def shard_lock_path(step_dir: str, shard: Tuple[int, int]) -> str:
    return os.path.join(step_dir, "locks", f"shard{shard[0]}of{shard[1]}.lock")


def acquire_shard_lock(path: str) -> int:
    """An exclusive fcntl.flock on the shard's lock file, held until release (or the process ends). Raises RunRefused
    if another process holds it. Returns the file descriptor."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise RunRefused(f"another process runs this shard (the lock {path} is held): refused; one process per "
                         f"shard, never a second one on a paused shard")
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()} {utc_stamp()}\n".encode())
    return fd


def shard_lock_held(path: str) -> Optional[bool]:
    """Dry run: is the lock held now? (None: no lock file; nothing is created.)"""
    if not os.path.exists(path):
        return None
    fd = os.open(path, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    except OSError:
        return True
    finally:
        os.close(fd)


def release_shard_lock(fd: Optional[int]) -> None:
    if fd is None:
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


# ---- B1's pass check (pre-registration section 10; audit C #4)
def _lines_of(path: str) -> List[dict]:
    recs, _ = soft_stop.JsonlTail().read_new(path, final=True)
    return recs


def b1_check(run_dir: str) -> dict:
    """B1 passes when: 2 tasks x 5 arms = 10 conversations, each with a line without error; 0 error lines (1
    content-filter error allowed); the mean cost per conversation <= 3 x the point estimate ($0.12 / 10); and (audit
    C #4) 0 Direct + facts checks with a facts failure and 0 v3 state errors (checks with a state error or a fact-code
    error). Reads the run folder only."""
    lines: Dict[str, List[dict]] = {}
    for a_ in ARMS:
        d = os.path.join(run_dir, a_)
        if os.path.isdir(d):
            for name in sorted(os.listdir(d)):
                if soft_stop.is_episodes_file(name):
                    lines.setdefault(a_, []).extend(_lines_of(os.path.join(d, name)))
    allr = [r for rs in lines.values() for r in rs]
    done = {unit_key(r) for r in allr if r.get("error") is None}
    errs = [r for r in allr if r.get("error") is not None]
    cf = [r for r in errs if CONTENT_FILTER_RE.search(str(r.get("error")))]
    units = {unit_key(r) for r in allr}
    df_fail = df_state = 0
    for r in lines.get("direct_facts_v3", []):
        for at in r.get("attempts") or []:
            part = (at.get("guard") or {}).get("direct_facts") or {}
            df_fail += part.get("facts_failure") is not None
            df_state += part.get("state_error") is not None
    v3_state = sum(v3_state_error_checks(r) for r in lines.get(V3_ARM, []))
    v3_state_only = sum(1 for r in lines.get(V3_ARM, []) for at in r.get("attempts") or []
                        if ((at.get("guard") or {}).get("v3") or {}).get("state_errors"))
    cost = sum(soft_stop.line_cost(r) for r in allr)
    n_conv = len(units)
    mean = cost / n_conv if n_conv else 0.0
    limit = 3 * B1_POINT_USD / B1_CONVERSATIONS
    want_done = B1_CONVERSATIONS - (1 if len(cf) == 1 and len(errs) == 1 else 0)
    checks = {"conversations": n_conv == B1_CONVERSATIONS, "units_done": len(done) >= want_done,
              "error_lines": len(errs) == 0 or (len(errs) == 1 and len(cf) == 1),
              "mean_cost": mean <= limit + 1e-12, "direct_facts_facts_failures": df_fail == 0,
              "v3_state_errors": v3_state == 0}
    return {"run_dir": run_dir, "pass": all(checks.values()), "checks": checks, "conversations": n_conv,
            "units_done": len(done), "lines": len(allr), "error_lines": len(errs), "content_filter_errors": len(cf),
            "cost_usd": round(cost, 6), "mean_cost_usd": round(mean, 6), "mean_cost_limit_usd": round(limit, 6),
            "direct_facts_facts_failures": df_fail, "direct_facts_state_errors": df_state,
            "v3_state_errors": v3_state, "v3_checks_with_state_errors": v3_state_only,
            "per_arm_lines": {a_: len(v) for a_, v in sorted(lines.items())}}


# ================================================================================================ the run command

def plan_identity(step: str, run_id: str, tasks: Sequence[dict], tries: int, first_try: int, n_shards: int,
                  approval: str, cap: float, limit: float, tasks_sha: str, task_split: str = TASK_SPLIT,
                  tasks_file: str = TASKS_REL) -> dict:
    """What every process of one run must share."""
    return {"step": step, "run_id": run_id, "profile": PROFILE, "arms": list(ARMS), "v3_switches": dict(V3_SWITCHES),
            "questions": {"model": QUESTION_MODEL, "effort": QUESTION_EFFORT}, "task_split": task_split,
            "tasks_file": tasks_file, "tasks_file_sha256": tasks_sha,
            "tasks": [f"{x['domain']}:{x['task_index']}:{x['group']}" for x in tasks], "n_tasks": len(tasks),
            "tries": tries, "first_try": first_try, "n_shards": n_shards, "max_steps": MAX_STEPS, "cap": 3,
            "approval_quote": approval, "cap_usd": cap, "hard_limit_usd": limit,
            "unit_attempts": UNIT_ATTEMPTS, "state_error_stop": STATE_ERROR_STOP, "runner_version": VERSION}


def ensure_run_json(path: str, ident: dict, extra: dict) -> Tuple[dict, bool]:
    """Create run.json once (atomic link; a race has one winner), then check that this process has the same plan
    and the same guard input hashes. Raises RunRefused."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    created = False
    if not os.path.exists(path):
        tmp = f"{path}.tmp_{os.getpid()}_{threading.get_ident()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dict(ident=ident, **extra), f, indent=1, default=str)
        try:
            os.link(tmp, path)
            created = True
        except FileExistsError:
            pass
        finally:
            os.remove(tmp)
    with open(path, encoding="utf-8") as f:
        have = json.load(f)
    if have.get("ident") != json.loads(json.dumps(ident, default=str)):
        diff = sorted(k for k in set(ident) | set(have.get("ident") or {})
                      if (have.get("ident") or {}).get(k) != json.loads(json.dumps(ident.get(k), default=str)))
        raise RunRefused(f"{path}: this process's plan differs from the run's ({diff}): refused")
    if have.get("guard_inputs_sha256") != extra["guard_inputs_sha256"]:
        a, b = have.get("guard_inputs_sha256") or {}, extra["guard_inputs_sha256"]
        diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        raise RunRefused(f"guard inputs changed since the run started ({len(diff)}: {diff[:5]}): refused")
    return have, created


def cmd_run(a, argv: Sequence[str]) -> dict:
    step, run_id = a.step, a.run_id
    if step not in STEPS:
        raise RunRefused(f"unknown step {step!r} (built: {sorted(STEPS)})")
    check_run_id(step, run_id)
    cfg = STEPS[step]
    shard = parse_shard(a.shard)
    if shard[1] not in cfg["shards"]:
        raise RunRefused(f"{step} runs with {cfg['shards']} shard(s), not {shard[1]}")
    if not 1 <= a.workers <= MAX_WORKERS:
        raise RunRefused(f"--workers {a.workers}: 1-{MAX_WORKERS} per shard")
    if step == "B2v" and not a.b2v_approved:
        raise RunRefused("B2v needs --b2v-approved (the user's approval of B2v; the cap rises to $110)")
    if a.b2v_approved and step != "B2v":
        raise RunRefused(f"--b2v-approved is for --step B2v only (step {step} keeps the ${soft_stop_v3.V3_CAP_USD:.0f} "
                         f"cap)")
    p = resolve_paths(a.out_root, step, run_id, shard)
    sandbox, dry = p["sandbox"], a.dry_run
    if not sandbox:                                           # a real run: the pre-registered size only (audit B #7)
        if a.tries is not None:
            raise RunRefused(f"{step}: --tries is fixed ({cfg['tries']}) outside the sandbox")
        if a.task_ids is not None:
            raise RunRefused(f"{step}: --task-ids is refused outside the sandbox ("
                             + ("B1 runs its fixed pair retail:4, airline:4" if step == "B1"
                                else f"all {cfg['n_tasks']} tasks run") + ")")

    # ---- safety first, before any runner import
    write_guard.install([OUTPUT_DIR])
    if sandbox or dry:
        install_net_recorder()                                # sees each refused attempt (host names)
        from state_tracker.v3 import questions as Q
        Q.block_network()
    if sandbox:
        install_sandbox()
    prob = approval_problem(a.approval)
    if prob and not (sandbox or dry):
        raise RunRefused(prob)
    if not (sandbox or dry):
        want_log = os.path.realpath(p["log"])
        if stdout_target() != want_log:
            raise RunRefused(f"stdout must be the log file {p['log']} (got {stdout_target()})")
    probs = soft_stop_v3.backup_problems(p["step_dir"], full=True)
    if probs:                                                 # audit B #1: a moved backup hides spend
        raise RunRefused(f"{len(probs)} backup(s) *.jsonl.before_resume have no live file of at least the same size "
                         f"with the same first bytes (copy, never move): {probs[:3]}")
    lock_path = shard_lock_path(p["step_dir"], shard)
    if dry:
        lock_fd = None
        if shard_lock_held(lock_path):
            raise RunRefused(f"another process runs this shard (the lock {lock_path} is held): refused")
    else:
        lock_fd = acquire_shard_lock(lock_path)
    try:
        return _cmd_run_locked(a, argv, step, run_id, cfg, shard, p, sandbox, dry, prob, lock_path)
    finally:
        release_shard_lock(lock_fd)


def _cmd_run_locked(a, argv, step, run_id, cfg, shard, p, sandbox, dry, prob, lock_path) -> dict:
    """cmd_run after the safety checks, with the shard's lock held (not in a dry run)."""
    from state_tracker.v3 import frozen
    frozen.check_manifest()                                   # eval v2 data and method unchanged
    doc = load_b3_tasks_file() if step == "B3" else load_tasks_file()
    task_split = step_task_split(step)
    tasks = select_tasks(doc, step, parse_task_ids(a.task_ids))
    tries = cfg["tries"] if a.tries is None else a.tries
    if not 1 <= tries <= 6:
        raise RunRefused(f"--tries {tries}: 1-6")
    if not sandbox and (len(tasks), tries) != ((2 if step == "B1" else cfg["n_tasks"]), cfg["tries"]):
        raise RunRefused(f"{step}: {len(tasks)} tasks x {tries} tries is not the pre-registered size")
    if not sandbox and step == "B1" and [(x["domain"], x["task_index"]) for x in tasks] != b1_tasks(doc):
        raise RunRefused(f"B1 runs only its fixed pair {b1_tasks(doc)}")
    cap = soft_stop_v3.cap_usd(b2v_approved=bool(a.b2v_approved))
    limit = soft_stop_v3.STEP_LIMITS_USD[step]
    if step == "B3":
        ident = plan_identity(step, run_id, tasks, tries, cfg["first_try"], shard[1], a.approval, cap, limit,
                              doc["sha256"], task_split=task_split, tasks_file=B3_TASKS_REL)
        ident["b3_build"] = B3_BUILD
    else:
        ident = plan_identity(step, run_id, tasks, tries, cfg["first_try"], shard[1], a.approval, cap, limit,
                              doc["sha256"])
    inputs = guard_inputs_sha256()
    if step == "B3":                                          # B3's own task list and τ-bench task file
        inputs[B3_TASKS_REL] = doc["sha256"]
        train_file = doc["source"]["tau_bench_tasks_train"]["retail"]
        inputs["tau_bench(venv)/envs/retail/tasks_train.py"] = train_file["sha256"]
    all_units = plan_units(tasks, tries, cfg["first_try"])
    mine = shard_units(all_units, tasks, shard)

    # ---- the runner copy (as the v2 runner loads it)
    from guard import runner_path
    runner_path.setup()
    import repro_runtime.calls  # noqa: F401  (loaded before activate so its seams are re-pointed; as the copy)
    import repro_runtime.plan  # noqa: F401
    from repro_runtime import calls as calls_module
    from exp_core import models
    from guard.run_online import CallCounter, JudgeRouter, tools_sha256
    if (sandbox or dry) and models._base_client is None:
        models._base_client = _NoClient()                     # never a real client in a sandbox or dry run
    models.CACHE_ROOT = p["cache_root"]
    act = models.activate(PROFILE, "guard")
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
    tools, wikis, tools_sha = {}, {}, {}
    for d in DOMAINS:
        with contextlib.redirect_stdout(io.StringIO()):
            probe = get_env(d, user_strategy="human", user_model=user_model, user_provider="azure",
                            task_split=TASK_SPLIT, task_index=0)
        tools[d], wikis[d] = probe.tools_info, probe.wiki
        tools_sha[d] = tools_sha256(probe.tools_info)
        with open(os.path.join(paths.RULES_DIR, d, "manifest.json"), encoding="utf-8") as f:
            want = json.load(f)["input"]["tools_sha256"]
        if tools_sha[d] != want:
            raise RunRefused(f"{d}: tool schemas {tools_sha[d]} differ from the rule set's tools_sha256 {want}")
    from guard import direct_facts_v3 as DF
    for d in DOMAINS:
        if DF.load_policy(d) != wikis[d]:
            raise RunRefused(f"{d}: the policy file differs from τ-bench's wiki (Direct would see another policy)")
    from state_tracker import tau_copy
    preloaded = {d: tau_copy.preload(d) for d in DOMAINS}

    log_fn = (lambda s: print(f"{PFX} tiny: {s}", flush=True)) if not dry else (lambda s: None)
    if dry:                                                   # plan only: fake answers in memory, nothing written
        from state_tracker.v3 import questions as Q
        answers = Q.Questions(Q.FakeBackend("yes"), Q.MemoryStore())
        meter = TinyMeter(answers.backend)
    else:
        answers, meter = make_answers_hook(sandbox, p["questions_store"], a.approval, limit, cfg["max_calls"],
                                           log_fn)
    guards_by: Dict[str, Dict[str, Any]] = {a_: {} for a_ in ARMS}
    infos: Dict[str, Dict[str, Any]] = {a_: {} for a_ in ARMS}
    for d in DOMAINS:
        for arm in ARMS:
            guards_by[arm][d], infos[arm][d] = build_arm(arm, d, tools[d], answers, meter)
    router = JudgeRouter(dict(p["structured_cache"]))
    router.install(calls_module)
    judge = JudgeMeter()
    judge.install(calls_module)                                # pass-through: the judge cost of error lines

    task_of = {(x["domain"], x["task_index"]): x for x in tasks}
    files = RunFiles(p["run_dir"], p["step_dir"]).scan()
    if files.problems:
        raise RunRefused(f"the run folder has problems: {files.problems[:3]}")
    todo = [u for u in mine if u not in files.done]
    prior_err = {u: files.errors[u] for u in todo if files.errors.get(u)}
    for u, n in prior_err.items():                               # resume: a unit that failed twice drops its group
        if n >= UNIT_ATTEMPTS and u[:3] not in files.dropped:
            files.dropped[u[:3]] = {"env": u[0], "task_index": u[1], "trial": u[2], "pending": True}
    left_groups = {u[:3] for u in todo}                          # resume: a group with a line is open (audit B #9)
    open_groups = sorted({u[:3] for u in mine if u in files.done or files.errors.get(u)} & left_groups
                         - set(files.dropped))
    ss = soft_stop_v3.SoftStopV3(step, cap_usd=cap, hard_limit_usd=limit, step_dir=p["step_dir"],
                                 root=p["out_root"] if sandbox else V3_ROOT)
    plan = {"argv": list(argv), "ident": ident, "models": used, "paths": p, "sandbox": sandbox, "dry_run": dry,
            "shard": f"{shard[0]}/{shard[1]}", "units_in_run": len(all_units), "units_in_shard": len(mine),
            "units_done": len(mine) - len(todo), "units_to_run": len(todo),
            "units_per_shard": {f"{i}/{shard[1]}": len(shard_units(all_units, tasks, (i, shard[1])))
                                for i in range(shard[1])},
            "shards_cover_every_unit_once": sorted(u for i in range(shard[1])
                                                   for u in shard_units(all_units, tasks, (i, shard[1])))
            == sorted(all_units),
            "domains_in_shard": sorted({u[0] for u in mine}), "first_units": [list(u) for u in todo[:10]],
            "dropped_groups_now": len(files.dropped), "v3_state_errors_now": files.v3_state_errors,
            "open_groups_at_start": [list(g) for g in open_groups], "workers": a.workers,
            "shard_lock": {"path": lock_path, "held_by_another_process": (shard_lock_held(lock_path) if dry
                                                                           else False)},
            "tools_sha256": tools_sha, "tau_copy_preloaded": preloaded, "guard_info": infos,
            "approval_problem": prob, "soft_stop_v3": ss.run_json(),
            "write_guard": {"installed": write_guard.installed(), "allowed": [OUTPUT_DIR]}}
    if dry:
        print(f"{PFX} DRY RUN (no LLM call, nothing written):")
        print(json.dumps(plan, indent=1, default=str))
        from state_tracker.v3 import questions as Q
        print(f"{PFX} LLM calls in this dry run: agent {counter.n['agent']}, user {counter.n['user']}, judge "
              f"{sum(router.calls.values())}, tiny {meter.total['calls']}; network attempts blocked "
              f"{len(Q.network_events())}; refused writes {len(write_guard.REFUSED)}")
        print(f"{PFX} network attempts refused by the block: {net_seen() or Q.network_events()}")
        print(f"{PFX} {step}/{run_id} shard {shard[0]}/{shard[1]} DRY RUN DONE")
        return plan

    # ---- the run folder (first process creates run.json; later ones must match)
    if os.path.exists(p["cache_root"]) and not os.path.exists(p["run_json"]):
        raise RunRefused(f"the cache folder {p['cache_root']} exists before the run: caches must be fresh")
    extra = {"command": list(argv), "command_line": " ".join(argv),
             "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "approval_quote": a.approval,
             "guard_inputs_sha256": inputs, "tasks_file_sha256": doc["sha256"], "models": used,
             "soft_stop_v3": ss.run_json(), "cache_root": p["cache_root"], "written_by": f"guard/run_online_v3.py "
             f"({VERSION})", "sandbox": sandbox}
    run_json, created = ensure_run_json(p["run_json"], ident, extra)
    with open(p["pids"], "a", encoding="utf-8") as f:
        f.write(f"{os.getpid()} {os.getpgid(0)} {shard[0]}/{shard[1]} {utc_stamp()}\n")
    write_atomic_json(p["shard_record"], dict(plan, pid=os.getpid(), created_run_json=created))
    ok, reason = ss.can_start_step()
    print(f"{PFX} {step}/{run_id} shard {shard[0]}/{shard[1]} start: {len(todo)} units "
          f"({len(mine) - len(todo)} already done), {len(tasks)} tasks x {tries} tries x {len(ARMS)} arms; step "
          f"start: {reason}", flush=True)
    router.build(models, calls_module)
    started = time.time()

    def run_unit(u: tuple, attempt: int) -> dict:
        d, t, k, arm = u
        models.reset_episode_usage()
        meter.start_episode()
        judge.start_episode()
        try:
            env = get_env(d, user_strategy="llm", user_model=user_model, user_provider="azure",
                          task_split=task_split, task_index=t)
            with router.use(arm):
                rec = episode.run_episode(env, agent_completion, tools[d], wikis[d], guards_by[arm][d], t,
                                          max_num_steps=MAX_STEPS)
            rec["error"] = None
        except Exception as e:  # noqa: BLE001 - recorded as a failed episode (as the copy)
            rec = {"task_index": t, "reward": 0.0, "error": f"{type(e).__name__}: {e}",
                   "traceback": traceback.format_exc()}
        usage = json.loads(json.dumps(models.episode_usage()))
        if rec["error"] is not None and arm == V3_ARM:
            ep = meter.episode()                  # the tiny questions of a failed conversation still cost money
            usage["v3_tiny_questions"] = {"calls": ep["calls"], "cost": round(ep["usd"], 8)}
        if rec["error"] is not None and arm in LLM_ARMS:
            jm = judge.episode()                  # the judge calls of a failed conversation still cost money
            usage["guard_judge"] = {"calls": jm["calls"], "cost": round(jm["usd"], 8)}
        rec["usage_roles"] = usage
        if "cost" in rec:
            rec["cost"]["agent"], rec["cost"]["user"] = usage["agent"]["cost"], usage["user"]["cost"]
        rec.update({"env": d, "guard": arm, "trial": k, "profile": PROFILE, "models": used, "task_split": task_split})
        rec.update({"arm": arm, "task_group": task_of[(d, t)]["group"], "step": step, "run_id": run_id,
                    "unit_attempt": attempt, "shard": f"{shard[0]}/{shard[1]}"})
        write_line(p["episodes"][arm], rec)
        return rec

    def on_live(running: int, left_open: int) -> None:
        try:
            write_atomic_json(p["live"], {"running": running, "left_open": left_open, "pid": os.getpid(),
                                          "updated": utc_stamp()})
        except OSError:
            pass

    def can_start_unit() -> Tuple[bool, str]:
        return ss.can_start_unit()

    def can_start(n_units: int, running: int, left_open: int) -> Tuple[bool, str]:
        files.scan()
        if files.v3_state_errors >= STATE_ERROR_STOP:
            return False, f"v3 state errors: {files.v3_state_errors} checks (stop at {STATE_ERROR_STOP})"
        if ss.stopped is not None:
            return False, f"stopped ({ss.stopped['rule']}): {ss.stopped['detail']}"
        o_run, o_left = others_live(p["run_dir"], p["live"])
        return ss.can_start_group(running + o_run, left_open + o_left, new_units=n_units, run_dir=p["run_dir"])

    def on_drop(g: tuple, rec: dict) -> None:
        reason = rec.get("drop_reason") or (f"a unit failed {UNIT_ATTEMPTS} times ({rec.get('guard')}: "
                                             f"{str(rec.get('error'))[:300]})")
        write_line(p["dropped"], {"env": g[0], "task_index": g[1], "trial": g[2], "reason": reason[:400],
                                  "time": utc_stamp()})
        print(f"{PFX} DROPPED group {g}: {str(rec.get('error'))[:200]}", flush=True)

    for g, r in list(files.dropped.items()):                     # resume: a pending drop is written now
        if r.get("pending"):
            on_drop(g, {"guard": "?", "error": "two error lines found at resume"})

    def on_result(r: dict, n: int) -> None:
        c = r.get("cost") or {}
        print(f"{PFX} {r['env']}/{r['guard']} task {r['task_index']} try {r['trial']} (attempt {r['unit_attempt']}): "
              f"reward {r['reward']} blocks {r.get('n_blocks')} cap {r.get('n_cap_overrides')} "
              f"err {r['error'] is not None} cost {sum(v for v in c.values() if isinstance(v, (int, float))):.4f} "
              f"{r.get('seconds')}s ({n} lines, {time.time() - started:.0f}s)", flush=True)

    def on_stop(reason: str) -> None:
        print(f"{PFX} STOPPED: {reason}; no new (task, try) group starts, open groups finish all arms", flush=True)

    if not ok:
        on_stop(f"step start refused: {reason}; only groups already open ({len(open_groups)}) finish")
    pool = GroupPool(todo, run_unit, can_start, a.workers, prior_errors=prior_err, dropped=list(files.dropped),
                     on_result=on_result, on_stop=on_stop, on_drop=on_drop, on_live=on_live,
                     can_start_unit=can_start_unit, open_groups=open_groups,
                     stop=None if ok else f"step start refused: {reason}")
    try:
        st = pool.run()
    except PoolAborted as e:
        print(f"{PFX} STOPPED: {e}", flush=True)
        raise
    finally:
        on_live(0, 0)
    rep = ss.report()
    print(f"{PFX} judge calls per arm {router.calls}; tiny-question backend calls {meter.total['calls']} "
          f"(${meter.total['usd']:.4f})", flush=True)
    print(f"{PFX} {step}/{run_id} shard {shard[0]}/{shard[1]} DONE: {st['lines']} lines in "
          f"{time.time() - started:.0f}s; not started {st.get('not_started', 0)}; stop: {st.get('stop')}; "
          f"step spend ${rep['step_usd']:.4f}; v3 total ${rep['total_usd']:.4f}; refused writes "
          f"{len(write_guard.REFUSED)}; judge cost metered ${judge.total['usd']:.4f} ({judge.total['calls']} calls)",
          flush=True)
    out = dict(plan, result=st, report=rep)
    if step == "B1":
        out["b1_check"] = b1_check(p["run_dir"])
        print(f"{PFX} B1 check (this shard's view of the run folder): {json.dumps(out['b1_check'], default=str)}",
              flush=True)
    return out


# ================================================================================================ main

def main(argv: Optional[Sequence[str]] = None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tasks-file", help="write (or --check) output/eval_v3/online_tasks.json")
    t.add_argument("--check", action="store_true")
    t3 = sub.add_parser("b3-tasks-file", help="write (or --check) output/eval_v3/b3_tasks.json (B3)")
    t3.add_argument("--check", action="store_true")
    n = sub.add_parser("new-id", help="print a fresh run id")
    n.add_argument("--step", required=True, choices=sorted(STEPS))
    r = sub.add_parser("run", help="run one shard of a step")
    r.add_argument("--step", required=True, choices=sorted(STEPS))
    r.add_argument("--run-id", required=True)
    r.add_argument("--shard", default=None, help="i/n (n <= 4; B1: 1 shard)")
    r.add_argument("--workers", type=int, default=6, help=f"1-{MAX_WORKERS} per shard")
    r.add_argument("--approval", default=None, help="the user's own approval words for this paid step")
    r.add_argument("--task-ids", default=None, help="sandbox only (B1: 1 retail + 1 airline task); a real B1 "
                                                     "runs its fixed pair retail:4, airline:4")
    r.add_argument("--tries", type=int, default=None, help="sandbox only (real runs: fixed)")
    r.add_argument("--b2v-approved", action="store_true", help="the user approved B2v (cap $110)")
    r.add_argument("--out-root", default=V3_ROOT, help="output/eval_v3 (real) or a folder under output/eval_v3/dryrun")
    r.add_argument("--dry-run", action="store_true", help="plan only: build everything, no call, nothing written")
    c = sub.add_parser("b1-check", help="B1's pass check of a run folder ($0, reads files only)")
    c.add_argument("--run-id", required=True)
    c.add_argument("--out-root", default=V3_ROOT)
    a = ap.parse_args(argv)
    if a.cmd == "b1-check":
        check_run_id("B1", a.run_id)
        res = b1_check(os.path.join(os.path.abspath(a.out_root), "B1", a.run_id))
        print(json.dumps(res, indent=1, default=str))
        return res
    if a.cmd == "tasks-file":
        doc = build_tasks_doc()
        text = tasks_doc_text(doc)
        if a.check or os.path.exists(TASKS_FILE):
            with open(TASKS_FILE, encoding="utf-8") as f:
                same = f.read() == text
            print(f"{PFX} {TASKS_REL}: {'equal to' if same else 'DIFFERS FROM'} a fresh build; sha256 "
                  f"{sha256_file(TASKS_FILE)} (recorded {TASKS_FILE_SHA256})")
            if not same:
                raise RunRefused("the tasks file differs from a fresh build (not overwritten)")
            return doc
        write_guard.install([OUTPUT_DIR])
        with open(TASKS_FILE, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"{PFX} wrote {TASKS_REL}: {doc['n_tasks']} tasks, sha256 {sha256_file(TASKS_FILE)}")
        return doc
    if a.cmd == "b3-tasks-file":
        doc = build_b3_tasks_doc()
        text = tasks_doc_text(doc)
        if a.check or os.path.exists(B3_TASKS_FILE):
            with open(B3_TASKS_FILE, encoding="utf-8") as f:
                same = f.read() == text
            print(f"{PFX} {B3_TASKS_REL}: {'equal to' if same else 'DIFFERS FROM'} a fresh build; sha256 "
                  f"{sha256_file(B3_TASKS_FILE)} (recorded {B3_TASKS_FILE_SHA256})")
            if not same:
                raise RunRefused("the B3 tasks file differs from a fresh build (not overwritten)")
            return doc
        write_guard.install([OUTPUT_DIR])
        with open(B3_TASKS_FILE, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"{PFX} wrote {B3_TASKS_REL}: {doc['n_tasks']} tasks, sha256 {sha256_file(B3_TASKS_FILE)}")
        return doc
    if a.cmd == "new-id":
        rid = new_run_id(a.step)
        print(rid)
        return rid
    return cmd_run(a, ["-m", "guard.run_online_v3"] + argv)


if __name__ == "__main__":
    main()
