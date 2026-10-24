"""Tracker v4: the online runner for the paid runs (docs/planning/tracker_v4/overview.md sections 4, 5, 9, 10).

A copy of guard/run_online_v3.py (v3.p13.3 + B3, sha256 0daab01d..., left byte-identical). The eval v2 runner
(guard/run_online.py) and the v3 runner are not changed; this file only imports them. What changed, and nothing else:
  - the arms (P10 arm plan, user decision): none, direct, tgr_frozen, tgr_tracker_v3, direct_facts_v4, tgr_tracker_v4;
    each step runs only its live arms (soft_stop_v4.STEP_ARMS / group_arms): B1v4, B2v4 direct_facts_v4 +
    tgr_tracker_v4; B3v4 those on all 64 tasks + none, direct, tgr_frozen, tgr_tracker_v3 on the 15 fill tasks; Hv4
    all six. tgr_tracker_v3 (B3v4, Hv4 only) is built by v3's runner (make_answers_hook, build_arm; unchanged). The
    arms not run come from the v3 baseline runs (BASELINES; recorded in run.json, checked by counts / keys only on the
    real path; `baseline-check` is the $0 check);
  - the steps: B1v4, B2v4, B3v4, Hv4 (below); DEV20v4 is dropped and refused (DROPPED_STEPS);
  - the conversation id is saved with every tiny answer record and every episode line (lesson L3.10);
  - the limits and stops: guard/soft_stop_v4.py (dev $2, B1v4 $2, B2v4 $40, B3v4 $20, Hv4 $15, cap $80; the halfway
    harm check at 742 / 160 conversations runs by script, scoring/v4_interim.sh, and the runner applies the same
    saved decision itself between groups as a backup: halfway_backup, audit P9 #1a);
  - up to 6 shards; the run folders under output/eval_v4/<step>/; logs output/logs/v4_<step>_<run_id>_s<i>.log; judge
    caches output/_llmcache/v4_<run_id>/.

What it runs
  - profiles: luna-dev (gpt-6-luna for the agent, the user simulator and the guard role) for every step but Hv4;
    Hv4: nano-agent-luna (from_shieldagent/runner/exp_core/model_profiles.json: the agent gpt-5-nano with P6's
    settings, chat API; the user simulator, the guards and the tiny questions stay gpt-6-luna). The models of every
    role are checked against ROLE_MODELS before any call.
  - five arms, each a guard for the copied episode loop (repro_online/episode.py::run_episode, unchanged):
      none             the copy's own: repro_online.guards.build("none", domain, tools_info)
      direct           the copy's DirectGuard with the policy loader of guard/direct_facts_v3.py direct_guard (as v3)
      direct_facts_v4  guard/direct_facts_v4.py build(domain) (Direct + the code facts as final values with their
                       sign; written by another agent, imported lazily)
      tgr_frozen       frozen TGR, fresh, built exactly as the v2 runner builds it (as v3)
      tgr_tracker_v4   guard/tgr_tracker_v4.py build(domain, tools_info, answers=<hook>, **switches
                       [, require_freeze=<real run>]) (TrackerTGRv4, a subclass of TrackerTGRv3: the same step /
                       commit interface; written by others, imported lazily). The switches are the module's
                       ONLINE_SWITCHES (DEFAULT_V4_SWITCHES = meaning tiny, messages rule, if it has none).
                       new_episode() gives the copy's Conversation with v4_blocks = [] (the escape's block memory).
                       The tiny questions online: state_tracker/v4/questions_v4.py QuestionsV4 with the doc
                       load_questions_v4(); RealBackendV4 (gpt-6-luna, low effort; approval_flag=True only on the real
                       path, after the approval words and the freeze) in a real run, FakeBackendV4 in the sandbox. Their cost is added to the guard record's usage (counted once, in the episode
                       line's guard cost). Their answers go to a fresh store in the run folder
                       (questions/answers_shard<i>of<n>.jsonl; each record also gets conversation_id and
                       where), and every ask (asked or read from the store) is one line of
                       questions/asks_shard<i>of<n>.jsonl (QuestionsV4's own ask log when it takes ask_log=, else
                       the runner's). `where` (code_change_map.md section 0.2 item 7) = {run_id, step, domain, task,
                       trial, arm, check} (+ attempt, conversation_id) is set on the hook per unit and per check.
    One judge LLM object (and cache folder) per LLM arm (the v2 JudgeRouter), so no answer is shared across arms.
  - the conversation id: "<run_id>:<arm>:<domain>:<task>:<trial>:a<attempt>" (episode line field conversation_id).
  - the freeze: a real run refuses unless scoring/v4_freeze.py's check passes AND the manifest lists every
    freeze_required_files() path (guard_input_files(), this file, guard/soft_stop_v4.py, the merged
    facts_v4_*.json, questions_v4.json, b3_tasks.json) with its current sha256; run.json gets v4_manifest_sha256.
  - the B1 gate (preregistration_v4.md section 13): B2v4, B3v4 and Hv4 refuse to start unless a B1v4 run
    folder under the same out root passes b1_check and scoring/v4_b1_summary.py's section 13 check (imported lazily,
    reads files only) with the same v4 manifest sha256 (a real step: a real B1v4 run). A sandbox sees only sandbox
    B1v4 folders of its own dry-run root; a dry run only reports the gate.
  - the main chat's flag: the real path needs --i-am-the-main-chat (as scoring/v4_offline_eval.py); RealBackendV4's
    approval_flag is True only with it.
  - shards: a step-level flock (<step>/locks/group_start.flock) around a new group's check and the live-file write;
    a unit's check counts the units in flight in all shards at p90; each shard's tiny-question budget is its share
    of the step's (limit / n, max_calls // n); a unit ledger (<run>/ledger/units_shard<i>of<n>.jsonl) lets
    soft_stop_v4 count a killed shard's unit.
  - the steps (soft_stop_v4.STEP_LIMITS_USD):
      B1v4     smoke: the fixed pair retail:4, airline:4 (the first retail and airline task of online_tasks.json, both
               val) x 1 try (trial 0) x 2 live arms = 4 conversations; 1 shard
      B2v4     output/eval_v3/online_tasks.json (99 tasks: val 33 + train 66), 3 tries x 2 arms = 594
      B3v4     output/eval_v3/b3_tasks.json (64 Stage A retail train-file tasks with 3+ expected actions), 1 try:
               64 x 2 + 15 fill tasks x 4 = 188
      Hv4      the 99 tasks of B2v4, 1 try (trial 0), the weak agent (nano-agent-luna), 6 arms = 594
      DEV20v4  DROPPED (user decision): the retail-dev-20 side check is not unseen (the build saw those 20 tasks).
               `--step DEV20v4` (and the old --dev20-enabled flag) is refused; the 20 dev tasks stay unused.
    The task files are v3's, read only (sha256 checked, B3 equal to a fresh build). The partner's test group (66 tasks:
    retail 46, airline 20) is refused everywhere: it is in no task list, a task id of it is refused, and every task of
    a test-file step is re-checked against splits.json at start. B3v4's tasks come from τ-bench's train file, which
    the partner's split does not cover.
  - unit order and shards as v3: try by try, the 5 arms of a (task, try) together, the first arm rotating with the
    task position; shard i of n takes the tasks at positions p with p mod n == i.

Run folder: output/eval_v4/<step>/<run_id>/, run id <step>_<UTC time>_<uuid8> (new-id prints one); the files as v3's
(run.json, pids.txt, watcher_command.txt, <arm>/episodes_shard<i>of<n>.jsonl, dropped_groups_*.jsonl, questions/, live/, shard records,
STOP). Stops, re-run once / drop group, resume (backups by cp, never mv; a moved backup refuses the run), one process
per shard (flock), the per-unit money check: as v3 (see guard/run_online_v3.py), with guard/soft_stop_v4.py and the
3rd v4 state error (checks of the tgr_tracker_v4 arm with a state error or a fact-code error, all run folders of the
step).

Safety: as v3 (the write guard; models per ROLE_MODELS; the tool schemas give the rule sets' tools_sha256; the eval v2
manifest is checked); a real run needs the user's approval words (--approval or --approved "<the user's words>", the
rules of questions.check_real_mode) and its stdout must be the log file. Sandbox runs: an out root under
output/eval_v4/dryrun/ blocks the network, refuses every write outside output/eval_v4/dryrun/, uses fake tiny-question
answers and never builds a real client. --dry-run: plan only (network blocked, no client, guards built, nothing
written, 0 LLM calls; get_env is only called with user_strategy="human").

Commands (run from predicate_correctness/, ~/venvs/tau-bench/bin/python -B, PYTHONDONTWRITEBYTECODE=1):
  python -B -m guard.run_online_v4 tasks-file                    check output/eval_v3/online_tasks.json (never written)
  python -B -m guard.run_online_v4 b3-tasks-file                 check output/eval_v3/b3_tasks.json (never written)
  python -B -m guard.run_online_v4 new-id --step B2v4            print a fresh run id
  python -B -m guard.run_online_v4 run --step B2v4 --run-id <id> --shard <i>/6 --workers 6 --approved "<words>" \
      --i-am-the-main-chat
  python -B -m guard.run_online_v4 b1-check --run-id <id>                  B1v4's pass check ($0, reads files only)
Find processes with: ps -eo pid,pgid,etimes,cmd | grep '[r]un_online_v4'
The halfway watcher (once per run, main chat, in the background, BEFORE the shards: a real B2v4 / B3v4 start is
refused unless it is live, i.e. holds output/logs/v4_<step>_<run_id>_watch.lock; it waits up to 900 s for pids.txt;
the start line prints it, and it is in <run_dir>/watcher_command.txt):
  bash scoring/v4_interim.sh <run_dir> <run_dir>/pids.txt > output/logs/v4_<step>_<run_id>_watcher_stdout.txt 2>&1
A real start is also refused when its approval words are in another step's run.json (one approval, one step), and
any start (not a dry run) while another run id of the same step has a live runner (audit P9 #2, #5).

Our code. Imports the runner copy through guard/runner_path.py (lazily, inside the commands), never imports gold code,
imports a scoring module only lazily (scoring/v4_freeze.py; scoring/v4_b1_summary.py for the B1 gate, read only;
scoring/v4_online_interim.py for the halfway backup, which reads files and writes only halfway.json / STOP),
and makes no LLM call itself.
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import fcntl
import hashlib
import importlib
import inspect
import io
import json
import os
import re
import sys
import threading
import time
import traceback
import types
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

sys.dont_write_bytecode = True
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")   # litellm must not fetch its price map (audit B #10)

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "guard"

from guard import soft_stop, soft_stop_v4, write_guard                      # noqa: E402
from state_tracker import paths                                            # noqa: E402

PFX = "[v4-online]"
NAME = "run_online_v4"
VERSION = "v4.p1.1"
V3_VERSION = "v3.p13.3"            # the v3 runner version written into online_tasks.json (its fresh build must match)
PC_DIR = paths.PC_DIR
OUTPUT_DIR = paths.OUTPUT_DIR
V4_ROOT = soft_stop_v4.V4_ROOT                                   # output/eval_v4
DRYRUN_ROOT = os.path.join(V4_ROOT, soft_stop_v4.DRYRUN_DIRNAME)  # output/eval_v4/dryrun
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
B3_BUILD = "v3.p14.b3"                                            # written into b3_tasks.json (v3's file)
# DEV20v4 (the retail-dev-20 side check) is DROPPED (user decision: the build saw those 20 tasks, so they are not
# unseen). It has no step, no limit and no task list; every way to ask for it is refused with this text.
DROPPED_STEPS = {"DEV20v4": "DEV20v4 is dropped (user decision): the retail-dev-20 side check is not unseen (the build "
                            "saw those 20 tasks), so it is not run; the steps are B1v4, B2v4, B3v4, Hv4"}
DROPPED_FLAGS = ("--dev20-enabled",)

PROFILE = "luna-dev"                                              # every step but Hv4
H_PROFILE = "nano-agent-luna"                                     # Hv4: the weak agent only (user, guards: luna)
ROLE_MODELS = {"luna-dev": {"agent": "gpt-6-luna", "user": "gpt-6-luna", "guard": "gpt-6-luna"},
               "nano-agent-luna": {"agent": "gpt-5-nano", "user": "gpt-6-luna", "guard": "gpt-6-luna"}}
ALLOWED_MODELS = ("gpt-6-luna", "gpt-5-nano")                     # per role: ROLE_MODELS
# P10 arm plan (user decision; soft_stop_v4.STEP_ARMS / group_arms): every arm the runner knows; each step runs only
# its live arms (B1v4 / B2v4: direct_facts_v4 + tgr_tracker_v4; B3v4: those on all 64 tasks + none, direct,
# tgr_frozen, tgr_tracker_v3 on the 15 fill tasks; Hv4: all six)
ARMS = soft_stop_v4.ALL_ARMS
STEP_ARMS = soft_stop_v4.STEP_ARMS
B3_FILL_ARMS = soft_stop_v4.B3_FILL_ARMS
B3_FILL_TASKS = soft_stop_v4.B3_FILL_TASKS
LLM_ARMS = ("direct", "direct_facts_v4", "tgr_frozen")           # structured calls (one judge cache each)
V4_ARM = "tgr_tracker_v4"
V3_ARM = "tgr_tracker_v3"                                         # v3's tracker, built by v3's runner (unchanged)
V3_ARM_STEPS = ("B3v4", "Hv4")                                    # the only steps where tgr_tracker_v3 is runnable
V3_RUNNER_MODULE = "guard.run_online_v3"                          # its make_answers_hook / build_arm (import only)
NOT_RUNNABLE_ARMS = ("direct_facts_v3",)                          # v3's Direct + facts: never an arm here
V4_MODULE = "guard.tgr_tracker_v4"                                # TrackerTGRv4 (other agents; imported lazily)
DF4_MODULE = "guard.direct_facts_v4"                              # Direct + facts v4 (another agent; lazily)
QV4_MODULE = "state_tracker.v4.questions_v4"                     # QuestionsV4, RealBackendV4 (agent A3; lazily)
FREEZE_MODULE = "scoring.v4_freeze"                               # the freeze check (P1b; lazily)
B1_SUMMARY_MODULE = "scoring.v4_b1_summary"                       # section 13's B1 pass mark (read only; lazily)
QUESTIONS_FILES_V4 = soft_stop_v4.QUESTIONS_FILES                 # the dev / cases answers files: never a run store
# the real path needs this flag (the same name and meaning as scoring/v4_offline_eval.py MAIN_CHAT_FLAG): only the
# main chat runs a paid step; RealBackendV4's approval_flag is set only when it is given (audit P7 #1)
MAIN_CHAT_FLAG = "--i-am-the-main-chat"
# preregistration_v4.md section 13: these steps start only after a passing B1v4 run with the same v4 manifest
# (audit P7 #2). The B1v4 folder is looked up under the run's own out root: output/eval_v4/B1v4/ for a real run;
# a sandbox finds only sandbox B1v4 folders (under its own dry-run root), and a real run never reads those.
B1_GATED_STEPS = ("B2v4", "B3v4", "Hv4")
# the freeze manifest must list these too (besides every guard_input_files() path), with matching sha256 (audit P7 #3)
# (audit P9 #4: also the B1 gate's summary, the metrics, the diagnosis, the halfway check and its watcher)
FREEZE_REQUIRED_EXTRA = ("guard/run_online_v4.py", "guard/soft_stop_v4.py", "state_tracker/v4/questions_v4.json",
                         "output/eval_v3/b3_tasks.json", "scoring/v4_b1_summary.py", "scoring/v4_online_metrics.py",
                         "scoring/v4_diagnosis.py", "scoring/v4_online_interim.py", "scoring/v4_interim.sh")
FACTS_V4_DIR = "state_tracker/v4"                                 # the merged facts_v4_<domain>.json files
LEDGER_DIRNAME = soft_stop_v4.LEDGER_DIRNAME                      # <run_dir>/ledger/units_shard<i>of<n>.jsonl
# the keywords for guard/tgr_tracker_v4.py build() (code_change_map.md section 1.2: build(domain, tools, *, meaning,
# messages, lazy, answers, require_freeze)); its ONLINE_SWITCHES win when it has them
DEFAULT_V4_SWITCHES = {"facts": "v4", "meaning": "tiny", "messages": "rule"}
QUESTION_MODEL, QUESTION_EFFORT = "gpt-6-luna", "low"
DOMAINS = ("retail", "airline")
GROUPS = ("val", "train")
WANT_COUNTS = {"val": {"retail": 23, "airline": 10}, "train": {"retail": 46, "airline": 20}}
PARTNER_TEST_COUNTS = {"retail": 46, "airline": 20}               # the partner's test 66: never run
TASK_SPLIT = "test"                                               # τ-bench's test task files
MAX_STEPS = 30
MAX_SHARDS = 6
UNIT_ATTEMPTS = 2                                                 # a failed unit is re-run once
STATE_ERROR_STOP = 3                                              # the 3rd v4 state error stops new groups
MAX_WORKERS = 8                                                   # per shard (audit B #8)
TINY_CALL_FAILURES = ("RealCallFailed",)                          # questions.py: a real tiny call failed 3 times
# preregistration_v4.md section 13: B1v4's mean cost per conversation is at most 3 x the point estimate
# = 3 x $0.0106 (v3 B2's measured mean per conversation) = $0.032
B1_POINT_USD_PER_CONVERSATION = 0.0106
B1_MEAN_COST_LIMIT_USD = 0.032
B1_CONVERSATIONS = 4                                              # P10: 2 tasks x 2 live arms
CONTENT_FILTER_RE = re.compile(r"content[ _-]?filter|content[ _-]?policy|responsibleaipolicy", re.I)
SHARDS_ANY = (1, 2, 3, 4, 5, 6)
STEPS: Dict[str, dict] = {
    "B1v4": {"tries": 1, "first_try": 0, "groups": ("val", "train"), "n_tasks": 2, "shards": (1,),
             "max_calls": 2000, "profile": PROFILE, "tasks": "online"},
    "B2v4": {"tries": 3, "first_try": 0, "groups": ("val", "train"), "n_tasks": 99, "shards": SHARDS_ANY,
             "max_calls": 40000, "profile": PROFILE, "tasks": "online"},
    "B3v4": {"tries": 1, "first_try": 0, "groups": (B3_GROUP,), "n_tasks": 64, "shards": SHARDS_ANY,
             "max_calls": 10000, "profile": PROFILE, "tasks": "b3"},
    "Hv4": {"tries": 1, "first_try": 0, "groups": ("val", "train"), "n_tasks": 99, "shards": SHARDS_ANY,
            "max_calls": 15000, "profile": H_PROFILE, "tasks": "online"},
}
WANT_UNITS = {"B1v4": 4, "B2v4": 594, "B3v4": 188, "Hv4": 594}   # P10: 2x2x1, 99x3x2, 64x2 + 15x4, 99x6
# P10: the v3 runs that stand in for the arms a step does not run (counts and keys only are read, never content)
BASELINES: Dict[str, dict] = {
    "B2v4": {"run_id": "B2_20261023T155537Z_c842d895", "run_dir": "output/eval_v3/B2/B2_20261023T155537Z_c842d895",
             "arms": ("none", "direct", "tgr_frozen", "tgr_tracker_v3"), "task_file": TASKS_REL,
             "task_file_sha256": TASKS_FILE_SHA256, "lines_per_arm": 297},
    "B3v4": {"run_id": "B3_20261023T190740Z_9bf882c0", "run_dir": "output/eval_v3/B3/B3_20261023T190740Z_9bf882c0",
             "arms": ("none", "direct", "tgr_frozen", "tgr_tracker_v3"), "task_file": B3_TASKS_REL,
             "task_file_sha256": B3_TASKS_FILE_SHA256, "tasks_per_arm": 49, "missing_tasks": B3_FILL_TASKS},
}
RUN_ID_RE = re.compile(r"^(B1v4|B2v4|B3v4|Hv4)_(\d{8}T\d{6}Z)_([0-9a-f]{8})$")
# the halfway watcher (scoring/v4_interim.sh): the runner prints its command at start and writes it into the run
# folder (WATCHER_FILENAME), for the main chat to start once per step
WATCHER_SCRIPT = "scoring/v4_interim.sh"
WATCHER_FILENAME = "watcher_command.txt"
# audit P9 #1d: a real start of these steps (the ones with the halfway rule) is refused unless the watcher of that run
# is live (it holds its lock output/logs/v4_<step>_<run_id>_watch.lock); the main chat starts it FIRST (it waits up to
# 900 s for pids.txt), then the shards
WATCHED_STEPS = ("B2v4", "B3v4")
# audit P9 #1a: the runner's own halfway backup between groups (scoring/v4_online_interim.py's once-only decision,
# halfway.json; never a second rule); a fresh look at most every HALFWAY_BACKUP_EVERY_S seconds per shard until saved
INTERIM_MODULE = "scoring.v4_online_interim"
HALFWAY_BACKUP_EVERY_S = 60.0
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
    return {"written_by": f"guard/run_online_v3.py tasks-file ({V3_VERSION})",      # v3's file: v3's text
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
    """τ-bench's task file of a step: "train" for B3v4, "test" for B1v4 / B2v4 / Hv4."""
    kind = STEPS[step]["tasks"]
    return B3_TASK_SPLIT if kind == "b3" else TASK_SPLIT


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
    if len(tasks) != STEPS["B3v4"]["n_tasks"]:
        raise RunRefused(f"B3: {len(tasks)} train tasks with {B3_MIN_ACTIONS}+ expected actions, expected "
                         f"{STEPS['B3v4']['n_tasks']}")
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
        if len(out) != STEPS["B3v4"]["n_tasks"]:
            raise RunRefused(f"B3v4: {len(out)} tasks, expected {STEPS['B3v4']['n_tasks']}")
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
    cfg = STEPS[step]
    if cfg["tasks"] == "b3":                        # its own list (τ-bench's train file, not in splits.json)
        return select_b3_tasks(doc, task_ids)
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
        if step == "B1v4":                         # the fixed pair (a sandbox may give its own with --task-ids)
            return select_tasks(doc, step, b1_tasks(doc))
        out = list(doc["tasks"])
    out = [x for x in out if x["group"] in cfg["groups"]] if task_ids is None else out
    bad = [f"{x['domain']}:{x['task_index']}" for x in out if x["group"] not in cfg["groups"]]
    if bad:
        raise RunRefused(f"{step} runs {cfg['groups']} tasks only; {bad} refused")
    if step == "B1v4":
        doms = sorted(x["domain"] for x in out)
        if doms != ["airline", "retail"]:
            raise RunRefused(f"B1v4 runs exactly 1 retail and 1 airline task (got {doms})")
    elif task_ids is None and len(out) != cfg["n_tasks"]:
        raise RunRefused(f"{step}: {len(out)} tasks, expected {cfg['n_tasks']}")
    for x in out:                                   # belt and braces: splits.json says val or train
        if splits[x["domain"]].get(str(x["task_index"])) not in GROUPS:
            raise RunRefused(f"task {x['domain']}:{x['task_index']} is in the partner's test group: refused")
    return [dict(x) for x in out]


# ================================================================================================ units and shards

def arm_order(pos: int, arms: Sequence[str] = ARMS) -> List[str]:
    arms = tuple(arms)
    r = pos % len(arms)
    return list(arms[r:] + arms[:r])


def unit_arms(step: Optional[str], domain: str, task: int, only: Optional[Sequence[str]] = None) -> Tuple[str, ...]:
    """The live arms of one (domain, task) group of a step (soft_stop_v4.group_arms; P10 arm plan); a sandbox's
    --arms (`only`) replaces the step's arms for every task. No step: every arm (ARMS)."""
    if only is not None:
        return tuple(a for a in ARMS if a in set(only))
    if step is None:
        return tuple(ARMS)
    return soft_stop_v4.group_arms(step, domain, task)


def plan_units(tasks: Sequence[dict], tries: int, first_try: int = 0, step: Optional[str] = None,
               only: Optional[Sequence[str]] = None) -> List[Tuple[str, int, int, str]]:
    """Every unit (domain, task, trial, arm) of the step, in run order: try by try, task by task (the list's order),
    the live arms of a (task, try) (unit_arms) next to each other, the first arm rotating with the task's position."""
    out = []
    for k in range(first_try, first_try + tries):
        for p, x in enumerate(tasks):
            out += [(x["domain"], x["task_index"], k, a)
                    for a in arm_order(p, unit_arms(step, x["domain"], x["task_index"], only))]
    return out


def parse_arms(spec: Optional[str]) -> Optional[Tuple[str, ...]]:
    """--arms (sandbox only): a comma list of known arms ("none,direct,tgr_frozen"), in ARMS order."""
    if spec is None:
        return None
    got = [x.strip() for x in spec.split(",") if x.strip()]
    bad = [x for x in got if x not in ARMS]
    if not got or bad or len(set(got)) != len(got):
        raise RunRefused(f"--arms {spec!r}: a comma list of {ARMS}, each once")
    return tuple(a for a in ARMS if a in got)


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


def refuse_dropped(step: Optional[str]) -> None:
    """A dropped step (DROPPED_STEPS: DEV20v4) is refused with its reason."""
    if step in DROPPED_STEPS:
        raise RunRefused(f"--step {step}: refused. {DROPPED_STEPS[step]}")


def new_run_id(step: str, t: Optional[float] = None) -> str:
    refuse_dropped(step)
    if step not in STEPS:
        raise RunRefused(f"unknown step {step!r} (built: {sorted(STEPS)})")
    return f"{step}_{utc_stamp(t)}_{uuid.uuid4().hex[:8]}"


def check_run_id(step: str, run_id: str) -> None:
    m = RUN_ID_RE.match(run_id or "")
    if not m or m.group(1) != step:
        raise RunRefused(f"--run-id {run_id!r}: use the id of new-id for step {step} (<step>_<UTC time>_<uuid8>)")


def watcher_command(step: str, run_id: str, out_root: str = V4_ROOT) -> str:
    """The exact command line of the halfway watcher (scoring/v4_interim.sh) for one step's run folder: every 300 s
    it runs scoring/v4_online_interim.py --write-stop on the folder; it ends when no pid of pids.txt is alive or a
    STOP file exists. The main chat starts it once per step (in the background); its logs go to output/logs/."""
    import shlex
    run_dir = os.path.join(os.path.abspath(out_root), step, run_id)
    out = os.path.join(LOGS_DIR, f"v4_{step}_{run_id}_watcher_stdout.txt")
    return (f"bash {shlex.quote(os.path.join(PC_DIR, *WATCHER_SCRIPT.split('/')))} {shlex.quote(run_dir)} "
            f"{shlex.quote(os.path.join(run_dir, 'pids.txt'))} > {shlex.quote(out)} 2>&1")


def watcher_lock_path(step: str, run_id: str, logs_dir: str = LOGS_DIR) -> str:
    """The flock the watcher (scoring/v4_interim.sh) holds while it runs: <logs>/v4_<step>_<run_id>_watch.lock."""
    return os.path.join(logs_dir, f"v4_{step}_{run_id}_watch.lock")


def watcher_live(step: str, run_id: str, logs_dir: str = LOGS_DIR) -> bool:
    """Is the halfway watcher of this run running now (its lock file exists and is held)? Reads only; never creates
    the lock file (audit P9 #1d)."""
    path = watcher_lock_path(step, run_id, logs_dir)
    if not os.path.exists(path):
        return False
    return bool(shard_lock_held(path))


def _norm_words(x: Any) -> str:
    return " ".join(str(x or "").split()).casefold()


def approval_used_elsewhere(step: str, approval: Any, root: str = V4_ROOT) -> List[str]:
    """The run.json files of OTHER steps under root (real runs only: <root>/<step>/<run_id>/run.json; the dry-run
    folder is never read) whose approval words are the same as these (whitespace and case ignored). Audit P9 #5: one
    approval is for one step."""
    want = _norm_words(approval)
    out: List[str] = []
    if not want:
        return out
    for other in sorted(STEPS):
        if other == step:
            continue
        d = os.path.join(root, other)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            rj = os.path.join(d, name, "run.json")
            if not RUN_ID_RE.match(name) or not os.path.isfile(rj):
                continue
            try:
                with open(rj, encoding="utf-8") as f:
                    doc = json.load(f)
            except (OSError, ValueError):
                continue
            words = {_norm_words(doc.get("approval_quote")), _norm_words((doc.get("ident") or {}).get("approval_quote"))}
            if want in words:
                out.append(rj)
    return out


def other_runs_live(step_dir: str, run_id: str) -> List[dict]:
    """Live runner processes of ANOTHER run id of the same step (audit P9 #2): every shard lock file of the step
    (<step>/locks/shard*.lock: "pid time [run id]") whose pid is a live run_online_v4 process (not this one) whose
    command line does not name this run id; and every pid of another run folder's pids.txt that is a live runner of
    that run. Reads only."""
    out: List[dict] = []
    mine = run_id.encode("utf-8")
    seen = set()
    d = os.path.join(step_dir, "locks")
    if os.path.isdir(d):
        for name in sorted(os.listdir(d)):
            if not (name.startswith("shard") and name.endswith(".lock")):
                continue
            try:
                with open(os.path.join(d, name), encoding="utf-8") as f:
                    words = f.read(300).split()
            except OSError:
                continue
            if not words or not words[0].isdigit() or int(words[0]) == os.getpid():
                continue
            pid = int(words[0])
            cmd = soft_stop_v4.pid_cmdline(pid)
            if cmd is None or soft_stop_v4.RUNNER_CMD_MARK not in cmd or mine in cmd:
                continue
            seen.add(pid)
            out.append({"pid": pid, "lock": os.path.join(d, name), "run_id": words[2] if len(words) > 2 else None})
    if os.path.isdir(step_dir):
        for rd in sorted(os.listdir(step_dir)):
            pf = os.path.join(step_dir, rd, "pids.txt")
            if rd == run_id or not RUN_ID_RE.match(rd) or not os.path.isfile(pf):
                continue
            try:
                with open(pf, encoding="utf-8") as f:
                    pids = [int(ln.split()[0]) for ln in f if ln.split() and ln.split()[0].isdigit()]
            except OSError:
                continue
            for pid in pids:
                if pid in seen or pid == os.getpid() or not soft_stop_v4.pid_alive(pid, (rd,)):
                    continue
                seen.add(pid)
                out.append({"pid": pid, "pids_file": pf, "run_id": rd})
    return out


def real_start_problems(step: str, run_id: str, approval: Any, root: str = V4_ROOT,
                        logs_dir: str = LOGS_DIR) -> List[str]:
    """The refusals of a real start that only read files (audit P9): the approval words already used by another
    step's run (#5), and for B2v4 / B3v4 no live halfway watcher of this run (#1d). [] = none."""
    out = []
    used = approval_used_elsewhere(step, approval, root)
    if used:
        out.append(f"these approval words were already given for another step ({used[:3]}): one approval is for one "
                   f"step, the user must approve {step} in their own words")
    if step in WATCHED_STEPS and not watcher_live(step, run_id, logs_dir):
        out.append(f"no live halfway watcher for {step}/{run_id} (its lock {watcher_lock_path(step, run_id, logs_dir)} "
                   f"is not held): the main chat starts it FIRST, in the background (it waits for pids.txt), then the "
                   f"shards: {watcher_command(step, run_id, root)}")
    return out


def is_sandbox(out_root: str) -> bool:
    return _under(out_root, DRYRUN_ROOT)


def resolve_paths(out_root: str, step: str, run_id: str, shard: Tuple[int, int]) -> dict:
    out_root = os.path.abspath(out_root)
    if not (_under(out_root, V4_ROOT)):
        raise RunRefused(f"--out-root {out_root} is not under {V4_ROOT}")
    if out_root != os.path.realpath(V4_ROOT) and not is_sandbox(out_root):
        raise RunRefused(f"--out-root: {V4_ROOT} (real runs) or a folder under {DRYRUN_ROOT} (sandbox) only")
    sandbox = is_sandbox(out_root)
    run_dir = os.path.join(out_root, step, run_id)
    sfx = shard_suffix(shard)
    cache = (os.path.join(out_root, "_llmcache", f"v4_{run_id}") if sandbox
             else os.path.join(LLMCACHE_DIR, f"v4_{run_id}"))
    return {"out_root": out_root, "sandbox": sandbox, "step_dir": os.path.join(out_root, step), "run_dir": run_dir,
            "run_json": os.path.join(run_dir, "run.json"), "pids": os.path.join(run_dir, "pids.txt"),
            "stop_file": os.path.join(run_dir, soft_stop_v4.STOP_FILENAME),
            "episodes": {a: os.path.join(run_dir, a, f"episodes{sfx}.jsonl") for a in ARMS},
            "dropped": os.path.join(run_dir, f"dropped_groups{sfx}.jsonl"),
            "questions_store": os.path.join(run_dir, "questions", f"answers{sfx}.jsonl"),
            "questions_store_v3": os.path.join(run_dir, "questions", f"answers_v3{sfx}.jsonl"),
            "live": os.path.join(run_dir, "live", f"shard{shard[0]}of{shard[1]}.json"),
            "ledger": os.path.join(run_dir, soft_stop_v4.LEDGER_DIRNAME, f"units{sfx}.jsonl"),
            "step_lock": os.path.join(out_root, step, "locks", "group_start.flock"),
            "shard_record": os.path.join(run_dir, f"shard{shard[0]}of{shard[1]}_{utc_stamp()}.json"),
            "asks_log": os.path.join(run_dir, "questions", f"asks{sfx}.jsonl"),
            "cache_root": cache, "structured_cache": {a: os.path.join(cache, a, "structured") for a in LLM_ARMS},
            "log": os.path.join(LOGS_DIR, f"v4_{step}_{run_id}_s{shard[0]}.log"), "shard_suffix": sfx}


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
    if os.path.isfile(os.path.join(PC_DIR, "scoring", "v4_freeze.py")):
        out.add("scoring/v4_freeze.py")             # the freeze check the real run needs
    for rel in extra_input_files():                 # files the v4 guards declare (INPUT_FILES), if they exist
        if os.path.isfile(os.path.join(PC_DIR, *rel.split("/"))):
            out.add(rel)
    return sorted(out)


def extra_input_files() -> List[str]:
    """INPUT_FILES (paths relative to predicate_correctness/) of the v4 guard modules already imported (never imports
    them here: the runner copy must be on the path first)."""
    out: List[str] = []
    for name in (V4_MODULE, DF4_MODULE, QV4_MODULE):
        mod = sys.modules.get(name)
        out += [str(x) for x in (getattr(mod, "INPUT_FILES", None) or ())]
    return sorted(set(out))


def guard_inputs_sha256() -> Dict[str, str]:
    got = {rel: sha256_file(os.path.join(PC_DIR, *rel.split("/"))) for rel in guard_input_files()}
    try:
        for d, (_, h) in tau_test_tasks().items():
            got[f"tau_bench(venv)/envs/{d}/tasks_test.py"] = h
    except ImportError:
        pass
    return got


def facts_v4_files() -> List[str]:
    """The merged facts files state_tracker/v4/facts_v4_*.json (relative to predicate_correctness/)."""
    d = os.path.join(PC_DIR, *FACTS_V4_DIR.split("/"))
    if not os.path.isdir(d):
        return []
    return sorted(f"{FACTS_V4_DIR}/{n}" for n in os.listdir(d) if n.startswith("facts_v4_") and n.endswith(".json"))


def freeze_required_files() -> List[str]:
    """Every file the v4 freeze manifest must list with its current sha256 before a real run starts (relative to
    predicate_correctness/): guard_input_files(), the runner and its soft stop, the merged facts_v4_*.json and
    questions_v4.json, B3's task file. scoring/v4_freeze.py --write adds them all."""
    return sorted(set(guard_input_files()) | set(FREEZE_REQUIRED_EXTRA) | set(facts_v4_files()))


def _manifest_real_path(stored: str, root: str) -> str:
    return stored if os.path.isabs(stored) else os.path.join(root, *stored.split("/"))


def freeze_coverage(manifest: Optional[str], required: Optional[Sequence[str]] = None) -> dict:
    """Is every required file (default freeze_required_files()) listed in the manifest with the sha256 it has now?
    {"ok", "manifest", "required", "unlisted": [...], "changed": [...], "problems": [...]}. Reads files only."""
    req = list(freeze_required_files() if required is None else required)
    out = {"ok": False, "manifest": manifest, "required": len(req), "unlisted": [], "changed": [], "problems": []}
    if not manifest or not os.path.isfile(manifest):
        out["problems"].append(f"manifest not found: {manifest}")
        return out
    try:
        with open(manifest, encoding="utf-8") as f:
            doc = json.load(f)
        root = doc.get("root") or os.path.dirname(PC_DIR)
        listed = {os.path.realpath(_manifest_real_path(str(e["path"]), root)): str(e.get("sha256"))
                  for e in doc["files"]}
    except (OSError, ValueError, KeyError, TypeError) as e:
        out["problems"].append(f"manifest unreadable: {type(e).__name__}: {e}")
        return out
    for rel in req:
        p = os.path.join(PC_DIR, *rel.split("/"))
        rp = os.path.realpath(p)
        if rp not in listed:
            out["unlisted"].append(rel)
        elif not os.path.isfile(p) or sha256_file(p) != listed[rp]:
            out["changed"].append(rel)
    out["ok"] = not (out["unlisted"] or out["changed"] or out["problems"])
    return out


def approval_problem(quote: Any) -> Optional[str]:
    """The rules of questions.check_real_mode for the approval words (without the network rule)."""
    if not isinstance(quote, str) or len(quote.strip()) < 8 or PLACEHOLDER_RE.search(quote) \
            or quote.strip().lower() in ("yes", "approved", "ok", "proceed", "go ahead"):
        return "the user's own approval words for this paid step are needed (--approval, 8+ characters, no <...>)"
    return None


# ================================================================================================ the v4 arm online

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
    """A v4 (or v3) fact error that came from a failed real tiny-question call (not an exception in the fact code)."""
    if not isinstance(err, dict):
        return False
    return err.get("error") in TINY_CALL_FAILURES or any(f"{n}:" in str(err.get("detail") or "")
                                                         for n in TINY_CALL_FAILURES)


class TinyQuestionCallFailed(RuntimeError):
    """A v4 check needed a tiny question whose real API call failed: the unit becomes an error line (re-run once,
    then its group is dropped), as an API error of any other arm."""


TRACKER_PART_KEYS = ("v3", "v4")          # the tracker's parts of a check record (code_change_map.md section 0.1:
#                                           the v4 guard keeps writing rec["v3"], same layout, and adds rec["v4"])


def tracker_part(rec: Optional[dict]) -> dict:
    """The state and fact errors of a v4 guard record: rec["v3"]'s lists (TrackerTGRv4 keeps TrackerTGRv3's
    record) plus rec["v4"]'s, if it has its own. {"state_errors": [...], "fact_errors": [...]}."""
    rec = rec or {}
    out: Dict[str, list] = {"state_errors": [], "fact_errors": []}
    for k in TRACKER_PART_KEYS:
        part = rec.get(k)
        if isinstance(part, dict):
            for f in out:
                out[f] += list(part.get(f) or [])
    return out


def finish_v4_check(rec: dict, meter: "TinyMeter") -> dict:
    """The online wrapper's part of a v4 check: the tiny questions' cost and calls go into the record's usage; a
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
    api = [e for e in (tracker_part(rec).get("fact_errors") or []) if is_api_fact_error(e)]
    failed = meter.check_failed()
    if failed or api:
        raise TinyQuestionCallFailed(f"a tiny question's API call failed in a v4 check: "
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


# ---- the v4 modules (written by other agents; imported lazily, after runner_path.setup())

def v4_module() -> Any:
    """guard/tgr_tracker_v4.py (TrackerTGRv4). A test may put a stand-in into sys.modules first."""
    return importlib.import_module(V4_MODULE)


def df4_module() -> Any:
    """guard/direct_facts_v4.py (Direct + facts v4). A test may put a stand-in into sys.modules first."""
    return importlib.import_module(DF4_MODULE)


def questions_v4_module() -> Any:
    """state_tracker/v4/questions_v4.py (QuestionsV4, RealBackendV4, load_questions_v4; v3's stores, FakeBackend and
    exceptions reused). A test may put a stand-in into sys.modules first."""
    return importlib.import_module(QV4_MODULE)


def freeze_module() -> Any:
    """scoring/v4_freeze.py (the freeze manifest check; owned by P1b)."""
    return importlib.import_module(FREEZE_MODULE)


def v4_switches(mod: Any = None) -> Dict[str, Any]:
    """The keywords the runner passes to the v4 tracker's build() besides answers: its ONLINE_SWITCHES, else
    DEFAULT_V4_SWITCHES."""
    mod = mod if mod is not None else v4_module()
    sw = getattr(mod, "ONLINE_SWITCHES", None)
    return dict(sw) if isinstance(sw, dict) else dict(DEFAULT_V4_SWITCHES)


def _accepts(fn: Callable, name: str) -> bool:
    """fn takes the keyword `name` (or **kwargs)."""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    return name in sig.parameters or any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values())


def freeze_check(require: bool = True, manifest: Optional[str] = None) -> dict:
    """The v4 freeze (scoring/v4_freeze.py). Returns {"ok", "manifest_sha256", "n_files", "detail", "coverage"}.
    require=True raises RunRefused unless the check passes (a real run never starts without a passing freeze).
    Accepts the published API check(require=True) -> {manifest_sha256, n_files} and the file's check(manifest) ->
    {ok, checked, manifest_sha256, ...}. The check also needs every freeze_required_files() path listed in the
    manifest with its current sha256 (freeze_coverage; audit P7 #3): a file missing from the manifest refuses."""
    path = manifest
    try:
        F = freeze_module()
        path = path or getattr(F, "DEFAULT_MANIFEST", None)
        if _accepts(F.check, "require"):
            res = F.check(require=require)
        else:
            res = F.check(path)
    except (ImportError, OSError, AttributeError) as e:
        res = {"ok": False, "problems": [f"{type(e).__name__}: {e}"]}
    except SystemExit as e:                                   # the freeze script refuses with SystemExit
        res = {"ok": False, "problems": [f"{type(e).__name__}: {e}"]}
    res = dict(res or {})
    path = res.get("manifest") or path
    ok = bool(res.get("ok", res.get("manifest_sha256") is not None)) and not res.get("problems") \
        and not res.get("changed") and not res.get("missing")
    cov = freeze_coverage(path)
    out = {"ok": ok and cov["ok"], "manifest_sha256": res.get("manifest_sha256"),
           "n_files": res.get("n_files", res.get("checked")),
           "detail": {k: res.get(k) for k in ("problems", "changed", "missing") if res.get(k)},
           "coverage": {k: cov[k] for k in ("ok", "manifest", "required", "unlisted", "changed", "problems")}}
    if not cov["ok"]:
        out["detail"]["coverage"] = {k: cov[k][:20] for k in ("unlisted", "changed", "problems") if cov[k]}
    if require and not out["ok"]:
        raise RunRefused(f"the v4 freeze check did not pass (scoring/v4_freeze.py --check, and every runner input "
                         f"listed with its sha256): {out['detail']}; a real run never starts without a passing freeze")
    return out


# ---- `where` and the conversation id on every tiny answer (code_change_map.md section 0.2 item 7; lesson L3.10)
_CONV = threading.local()


def conversation_id(run_id: str, arm: str, domain: str, task: int, trial: int, attempt: int) -> str:
    return f"{run_id}:{arm}:{domain}:{task}:{trial}:a{attempt}"


def unit_where(run_id: str, step: str, domain: str, task: int, trial: int, arm: str, attempt: int) -> dict:
    """The `where` of one unit: {run_id, step, domain, task, trial, arm, check} (check None until a check runs), plus
    the unit attempt and the conversation id."""
    return {"run_id": run_id, "step": step, "domain": domain, "task": task, "trial": trial, "arm": arm,
            "check": None, "attempt": attempt,
            "conversation_id": conversation_id(run_id, arm, domain, task, trial, attempt)}


def set_conversation(where: Optional[dict], answers: Any = None) -> None:
    """The unit the calling thread runs now (run_unit sets it before the episode, clears it after); also the hook's
    per-thread `where`."""
    _CONV.where = dict(where) if where else None
    if answers is not None:
        try:
            answers.where = dict(where) if where else None
        except AttributeError:
            pass


def set_check(index: Any, answers: Any = None) -> dict:
    """The `where` of the check in progress (the unit's where with check = index); set on the hook too."""
    w = dict(getattr(_CONV, "where", None) or {}, check=index)
    _CONV.where = w
    if answers is not None:
        try:
            answers.where = dict(w)
        except AttributeError:
            pass
    return w


def current_where() -> Optional[dict]:
    return getattr(_CONV, "where", None)


def current_conversation() -> Optional[str]:
    return (current_where() or {}).get("conversation_id")


class ConversationStore:
    """Wraps an answers store (questions.JsonlStore / MemoryStore): every new answer record is saved with the
    conversation id and the `where` of the thread that asked it ("conversation_id"; "where" = {run_id, step, domain,
    task, trial, arm, check, attempt, conversation_id}, unless QuestionsV4 already put a "where" in the record; its
    own "where_first" is kept as it is). Reads are the inner store's."""

    def __init__(self, inner: Any):
        self.inner = inner
        self.path = getattr(inner, "path", None)
        self.writable = getattr(inner, "writable", True)

    def get(self, key: str) -> Optional[dict]:
        return self.inner.get(key)

    def put(self, key: str, rec: dict) -> None:
        out = dict(rec, conversation_id=current_conversation())
        if not isinstance(out.get("where"), dict):
            out["where"] = current_where()
        self.inner.put(key, out)

    def __len__(self) -> int:
        return len(self.inner)

    def keys(self) -> List[str]:
        return self.inner.keys()

    def store_of(self, key: str) -> Optional[str]:
        """The inner store's store_of (questions_v4.ChainStore: "v4" / "v3"); "v4" / None for a plain store."""
        f = getattr(self.inner, "store_of", None)
        if callable(f):
            return f(key)
        return "v4" if self.inner.get(key) is not None else None


class AskLog:
    """questions.Questions.on_ask: one line per ask (a new call or an answer read from the store), with the asking
    thread's `where`, so a reused answer is tied to every conversation that used it. Used only when QuestionsV4 does
    not write its own ask log (no ask_log keyword). path None: count only."""

    def __init__(self, path: Optional[str]):
        self.path = path
        self.n = collections.Counter()

    def on_ask(self, key: str, qid: str, fact: Optional[str], part: Optional[str], cached: bool) -> None:
        self.n["cached" if cached else "asked"] += 1
        if self.path is not None:
            write_line(self.path, {"where": current_where(), "conversation_id": current_conversation(), "key": key,
                                   "qid": qid, "fact": fact, "part": part, "cached": bool(cached),
                                   "time": utc_stamp()})


def make_answers_hook(sandbox: bool, store_path: Optional[str], approval: str, max_usd: float, max_calls: int,
                      log: Callable[[str], None], fake_policy: Any = "yes", asks_path: Optional[str] = None,
                      memory: bool = False, qmod: Any = None, approval_flag: bool = False):
    """(QuestionsV4 hook, TinyMeter). state_tracker/v4/questions_v4.py: the doc load_questions_v4(); sandbox:
    FakeBackendV4 (the module's FakeBackend); real: RealBackendV4 (the user's approval words, a dollar budget = the
    step's hard limit, a call budget, and approval_flag: True only on the real-run path, after the approval words and
    the freeze check passed; RealBackendV4 refuses without it). The store is fresh, inside the run folder (memory=True: in memory, the dry run); each
    new record gets its conversation id and `where` (ConversationStore). The ask log: QuestionsV4's own
    (ask_log=asks_path) when it takes that keyword, else AskLog through on_ask."""
    QV4 = qmod if qmod is not None else questions_v4_module()
    doc = QV4.load_questions_v4()
    from state_tracker.v3 import questions as Q3
    if store_path is not None:
        banned = {os.path.abspath(Q3.ANSWERS_PATH)} | {os.path.abspath(p) for p in QUESTIONS_FILES_V4}
        banned |= {os.path.abspath(p) for p in (getattr(QV4, "ANSWERS_PATH", None),) if p}
        if any(os.path.abspath(store_path) == b for b in banned):
            raise RunRefused("the tiny-question answers of a v4 run never go to a project answers file "
                             "(v3's questions_answers.jsonl or the v4 dev / cases files)")
    if (doc["model"], doc["effort"]) != (QUESTION_MODEL, QUESTION_EFFORT):
        raise RunRefused(f"tiny questions: {doc['model']} / {doc['effort']} != {QUESTION_MODEL} / {QUESTION_EFFORT}")
    fake = getattr(QV4, "FakeBackend", Q3.FakeBackend)
    if sandbox:
        if approval_flag:
            raise RunRefused("approval_flag is for a real run only, never a sandbox or a dry run")
        backend = fake(fake_policy)
    else:
        kw_real: Dict[str, Any] = {"doc": doc, "log": log}
        if _accepts(QV4.RealBackendV4.__init__, "approval_flag"):
            kw_real["approval_flag"] = bool(approval_flag)
        backend = QV4.RealBackendV4(approval, max_usd, max_calls, **kw_real)
    meter = TinyMeter(backend)
    inner = (getattr(QV4, "MemoryStore", Q3.MemoryStore)() if memory or store_path is None
             else getattr(QV4, "JsonlStore", Q3.JsonlStore)(store_path))
    kw: Dict[str, Any] = {"doc": doc, "keep_log": False}
    own_log = _accepts(QV4.QuestionsV4.__init__, "ask_log") and not memory
    if own_log:
        kw["ask_log"] = asks_path
    hook = QV4.QuestionsV4(backend, ConversationStore(inner), **kw)
    if not own_log:
        hook.on_ask = AskLog(None if memory else asks_path).on_ask
    return hook, meter


def build_v4_guard(domain: str, tools_info: list, answers: Any, meter: TinyMeter, mod: Any = None,
                   require_freeze: bool = False):
    """The tgr_tracker_v4 arm: guard/tgr_tracker_v4.py's build(domain, tools_info, answers=..., **switches
    [, require_freeze=...]) behind the copy's TGRGuard interface. new_episode() returns the copy's Conversation with
    v4_blocks = [] (the per-conversation block memory of the transfer escape); check() sets the hook's `where` (with
    the check index) before tgr.step and adds the tiny questions' cost and calls of the check to the record's usage,
    so the copied loop counts them in the guard's cost; commit() is TGRGuard's (tgr.commit)."""
    V4 = mod if mod is not None else v4_module()
    switches = v4_switches(V4)
    from repro_online.guards import TGRGuard, make_step

    class OnlineTGRv4Guard(TGRGuard):
        name = V4_ARM

        def __init__(self):                                     # noqa: D401 - TGRGuard's fields, our TGR object
            self.name = V4_ARM
            self.domain = domain
            kw = dict(switches)
            if _accepts(V4.build, "require_freeze"):
                kw["require_freeze"] = require_freeze
            self.tgr = V4.build(domain, tools_info, answers=answers, **kw)
            self.config = getattr(self.tgr, "config", None)
            self.meter = meter
            self.answers = answers
            self.info = dict(getattr(self.tgr, "info", None) or {}, arm=V4_ARM, switches_online=dict(switches),
                             require_freeze=require_freeze, module=V4_MODULE,
                             online_wrapper="guard/run_online_v4.py OnlineTGRv4Guard")

        def new_episode(self):
            conv = super().new_episode()
            conv.v4_blocks = []
            return conv

        def check(self, state, executed, msg, index):
            set_check(index, self.answers)
            self.meter.start_check()
            n = len(state.trace)
            rec = self.tgr.step(state, make_step(executed, msg, index))
            rec["trace_len_before"] = n
            return finish_v4_check(rec, self.meter)        # raises on a failed real tiny-question call

    return OnlineTGRv4Guard()


def v3_runner_module() -> Any:
    """guard/run_online_v3.py (v3's runner, unchanged, import only): its make_answers_hook and build_arm build the
    tgr_tracker_v3 arm exactly as v3 did (P10 arm plan)."""
    return importlib.import_module(V3_RUNNER_MODULE)


def make_v3_answers_hook(sandbox: bool, dry: bool, store_path: Optional[str], approval: str, max_usd: float,
                         max_calls: int, log: Callable[[str], None]):
    """(v3 questions hook, v3 TinyMeter) for the tgr_tracker_v3 arm: v3's runner make_answers_hook (sandbox:
    questions.FakeBackend; real: questions.RealBackend with the approval words and this budget; a fresh store in the
    run folder, never questions_answers.jsonl). A dry run: the same fake backend over a memory store (nothing
    written)."""
    V3R = v3_runner_module()
    if dry:
        from state_tracker.v3 import questions as Q
        doc = Q.load_questions()
        backend = Q.FakeBackend("yes")
        meter = V3R.TinyMeter(backend)
        return Q.Questions(backend, Q.MemoryStore(), doc=doc, keep_log=False), meter
    return V3R.make_answers_hook(sandbox, store_path, approval, max_usd, max_calls, log)


def build_arm(arm: str, domain: str, tools_info: list, answers: Any = None, meter: Optional[TinyMeter] = None,
              require_freeze: bool = False, step: Optional[str] = None, v3_answers: Any = None,
              v3_meter: Any = None):
    """(guard object, info) of one arm and domain. Needs runner_path.setup() first. direct_facts_v3 is refused;
    tgr_tracker_v3 only for a step of V3_ARM_STEPS (B3v4, Hv4), built by v3's runner's build_arm (unchanged)."""
    if arm in NOT_RUNNABLE_ARMS or (arm == V3_ARM and step not in V3_ARM_STEPS):
        raise ValueError(f"arm {arm!r} is v3's: not runnable from the v4 runner here (step {step}; tgr_tracker_v3 "
                         f"only in {V3_ARM_STEPS}; arms: {ARMS})")
    if arm == V3_ARM:
        if v3_answers is None or v3_meter is None:
            raise ValueError("the tgr_tracker_v3 arm needs v3's answers hook and its meter")
        g, info = v3_runner_module().build_arm(V3_ARM, domain, tools_info, v3_answers, v3_meter)
        return g, dict(info, built_by_v4="guard/run_online_v3.py build_arm('tgr_tracker_v3', ...) (v3 runner, "
                                         "unchanged)")
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
    if arm == "direct_facts_v4":
        g = df4_module().build(domain)
        return g, dict(getattr(g, "info", None) or {}, arm=arm, module=DF4_MODULE)
    if arm == "tgr_frozen":
        from guard import run_online as V2                     # the eval v2 runner's own builder (unchanged)
        g, info = V2.build_guard("tgr_frozen", domain, tools_info)
        return g, dict(info, arm=arm, built_by_v4="guard/run_online.py build_guard('tgr_frozen', ...) (v2 runner)")
    if arm == V4_ARM:
        if answers is None or meter is None:
            raise ValueError("the tgr_tracker_v4 arm needs the answers hook and its meter")
        g = build_v4_guard(domain, tools_info, answers, meter, require_freeze=require_freeze)
        return g, dict(g.info)
    raise ValueError(f"unknown arm {arm!r} (arms: {ARMS})")


# ================================================================================================ progress on disk

def unit_key(r: dict) -> Tuple[str, int, int, str]:
    return (r.get("env"), r.get("task_index"), r.get("trial"), r.get("guard"))


def v4_state_error_checks(rec: dict) -> int:
    """The checks of a tgr_tracker_v4 line with a state error or a fact error of the fact code (a fact error from a
    failed real tiny-question call is left out: the pre-registered stop is for an exception in the fact code)."""
    n = 0
    for at in rec.get("attempts") or []:
        part = tracker_part(at.get("guard"))
        fe = [e for e in part.get("fact_errors") or [] if not is_api_fact_error(e)]
        if part.get("state_errors") or fe:
            n += 1
    return n


class RunFiles:
    """What the run folder says (all shards): units done (a line without error), error lines per unit, dropped
    groups; and the v4 state errors (checks of the tgr_tracker_v4 arm with a state error or a fact-code error) of
    every run folder of the step (step_dir; audit B #12)."""

    def __init__(self, run_dir: str, step_dir: Optional[str] = None):
        self.run_dir = run_dir
        self.step_dir = step_dir
        self._tail = soft_stop.JsonlTail()
        self.done: set = set()
        self.errors: collections.Counter = collections.Counter()
        self.dropped: Dict[tuple, dict] = {}
        self._v4_err: Dict[str, int] = {}                       # v4 episodes file -> state-error checks
        self.problems: List[str] = []
        self._lock = threading.Lock()

    @property
    def v4_state_errors(self) -> int:
        return sum(self._v4_err.values())

    def _other_runs(self) -> None:
        """The v4 arm's files of the step's other run folders (state errors only)."""
        if not self.step_dir or not os.path.isdir(self.step_dir):
            return
        mine = os.path.realpath(self.run_dir)
        for rd in sorted(os.listdir(self.step_dir)):
            d = os.path.join(self.step_dir, rd, V4_ARM)
            if os.path.realpath(os.path.join(self.step_dir, rd)) == mine or not os.path.isdir(d):
                continue
            for name in sorted(os.listdir(d)):
                if not soft_stop.is_episodes_file(name):
                    continue
                path = os.path.join(d, name)
                recs, restarted = self._tail.read_new(path)
                if restarted:
                    self._v4_err[path] = 0
                self._v4_err[path] = self._v4_err.get(path, 0) + sum(v4_state_error_checks(r) for r in recs
                                                                     if r.get("guard") == V4_ARM)

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
                        self._v4_err[path] = 0
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
                        if a == V4_ARM:
                            self._v4_err[path] = self._v4_err.get(path, 0) + v4_state_error_checks(r)
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


def interim_module() -> Any:
    """scoring/v4_online_interim.py (the halfway rule and its once-only decision; reads files, writes halfway.json
    once). Imported lazily. A test may put a stand-in first."""
    return importlib.import_module(INTERIM_MODULE)


def write_runner_stop(run_dir: str, stop: List[str], reason: str, **extra: Any) -> bool:
    """The STOP file of a run folder (O_EXCL: an existing one is never changed). True if this call wrote it."""
    p = os.path.join(run_dir, soft_stop_v4.STOP_FILENAME)
    line = json.dumps(dict({"stop": list(stop), "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "by": "guard/run_online_v4.py (halfway backup)", "reason": reason[:500]}, **extra),
                      sort_keys=True, default=str)
    try:
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(line + "\n")
    return True


def halfway_backup(run_dir: str, step: str, units_done: int, state: Optional[dict] = None,
                   every_s: float = HALFWAY_BACKUP_EVERY_S, mod: Any = None) -> Tuple[bool, str]:
    """The runner's own halfway check between groups (audit P9 #1a), a backup of the watcher: the SAME once-only
    decision as scoring/v4_online_interim.py (harm_check: the saved <run>/halfway.json if any, else the snapshot in
    line-time order, saved once the mark is reached; no second rule here). (ok, reason): ok False = no new group; on a
    fire the STOP file is written (reason "harm"). Steps without a halfway rule (B1v4, Hv4): always ok. Before any
    halfway.json exists, a fresh look is made only when the run has at least the mark's units done (fewer cannot fill
    the mark) and at most every `every_s` seconds (state["last"]). A check that fails (an exception) is a stop (fail
    closed) and writes STOP with the reason."""
    st = state if state is not None else {}
    try:
        half = soft_stop_v4.HALFWAY_CONVERSATIONS.get(step)     # P10: conversations of the v4 arms at the mark
        if half is None:
            return True, f"halfway: no rule for {step}"
        I = mod if mod is not None else interim_module()
        saved = I.read_halfway([run_dir])
        if saved is None:
            if units_done < half:                           # fewer done units cannot fill the mark: no look yet
                return True, f"halfway: {units_done} units done < the mark's {half}"
            now = time.time()
            if now - float(st.get("last") or 0.0) < every_s:
                return True, "halfway: looked less than a minute ago"
            st["last"] = now
            h = I.harm_check([run_dir], I.raw_lines([run_dir]), step, save=True)
        else:
            h = I.harm_check([run_dir], {}, step, save=True)      # the saved decision (a step mix-up raises)
    except Exception as e:  # noqa: BLE001 - fail closed: no new group, and STOP for the main chat to look
        why = f"halfway backup check failed ({type(e).__name__}: {e})"[:400]
        write_runner_stop(run_dir, ["halfway_check_failed"], why + "; no new group starts (fail closed)")
        return False, why + ": no new group (fail closed)"
    st["last_result"] = {k: h.get(k) for k in ("reached", "fire", "diff", "source", "complete_groups")}
    if h.get("fire"):
        why = (f"halfway harm: v4 - frozen TGR = {h.get('diff')} <= {getattr(I, 'HARM', -0.15)} on "
               f"{h.get('complete_groups')} complete groups ({h.get('source')}, scoring/v4_online_interim.py)")
        write_runner_stop(run_dir, ["harm"], why, harm_diff=h.get("diff"))
        return False, why
    if h.get("reached"):
        return True, f"halfway: reached, no fire (diff {h.get('diff')}; {h.get('source')})"
    return True, f"halfway: not reached ({h.get('conversations_in_complete_groups')} conversations)"


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
                 stop: Optional[str] = None, group_lock: Optional[Callable[[], Any]] = None):
        self.units = list(units)
        self.run_unit, self.can_start, self.workers = run_unit, can_start, workers
        self.can_start_unit = can_start_unit
        # group_lock() -> a context manager held around a new group's can_start and the live-file write that follows
        # (the step's flock: no two shards decide on a new group at the same time; audit P7 #4)
        self.group_lock = group_lock
        self._unit_check_running = can_start_unit is not None and _accepts(can_start_unit, "running")
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

    def _unit_check(self, extra: int) -> Tuple[bool, str]:
        """Under the lock: can_start_unit, with the units running in this shard (+ extra: the one about to start)."""
        if self._unit_check_running:
            return self.can_start_unit(running=self.counts["running"] + extra)
        return self.can_start_unit()

    def _job(self, u: tuple):
        g = u[:3]
        refused = None
        # the step's flock around a new group's check AND (audit P9 #3) around the unit check of an open group, so no
        # two shards decide on money in flight at the same time (taken for any group that may still start a unit)
        gl = (self.group_lock() if self.group_lock is not None and self.state.get(g) in ("new", "open")
              else contextlib.nullcontext())
        with gl, self._lock:                                  # the step's flock first, then the pool's lock
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
                ok, reason = self._unit_check(1)
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
                self._live()                                  # still under the step's flock for a new group
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
                rl = (self.group_lock() if self.group_lock is not None and self.can_start_unit is not None
                      else contextlib.nullcontext())          # the re-run's unit check under the step's flock too
                with rl, self._lock:
                    if self.state[g] == "dropped":           # another arm dropped the group: no paid re-run
                        self.counts["reruns_skipped_dropped"] += 1
                        break
                    if self.can_start_unit is not None:
                        ok, reason = self._unit_check(0)     # this unit is counted in running already
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
    """Sandbox runs: no network (questions.block_network), and no write outside output/eval_v4/dryrun/."""
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


def preload_urllib3_without_probe() -> None:
    """Sandbox / dry run only, after the network block: import urllib3 with socket.has_ipv6 False for the import, so
    its import-time check urllib3.util.connection._has_ipv6("::1") makes no socket (the block would refuse it and the
    dry run would report 1 network attempt). Only urllib3.util.connection.HAS_IPV6 (False) changes; the block stays."""
    import socket as _s
    old = _s.has_ipv6
    _s.has_ipv6 = False
    try:
        import urllib3.util.connection  # noqa: F401
    except ImportError:
        pass
    finally:
        _s.has_ipv6 = old


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


def acquire_shard_lock(path: str, run_id: Optional[str] = None) -> int:
    """An exclusive fcntl.flock on the shard's lock file, held until release (or the process ends). Raises RunRefused
    if another process holds it. Writes "<pid> <UTC> [<run id>]" into it (soft_stop_v4.live_steps and
    other_runs_live read it). Returns the file descriptor."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise RunRefused(f"another process runs this shard (the lock {path} is held): refused; one process per "
                         f"shard, never a second one on a paused shard")
    os.ftruncate(fd, 0)
    os.write(fd, (f"{os.getpid()} {utc_stamp()}" + (f" {run_id}" if run_id else "") + "\n").encode())
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


# ---- the step's group-start lock (audit P7 #4): every shard of a step takes it (blocking) around a new group's
# can_start and the live-file write after it, so two shards never decide on a new group from each other's old
# live files. A separate open file per use: threads of one process exclude each other too.
def step_lock_path(step_dir: str) -> str:
    return os.path.join(step_dir, "locks", "group_start.flock")


@contextlib.contextmanager
def step_flock(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield fd
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


# ---- the unit ledger (audit P7 #6): "start" before a unit's first call, "end" after its episode line; soft_stop_v4
# counts a start without an end whose pid is gone (a killed shard's unit) at ORPHAN_UNIT_USD + its tiny questions
def ledger_line(path: str, event: str, where: dict, unit: tuple) -> None:
    write_line(path, {"event": event, "conversation_id": where["conversation_id"], "unit": list(unit),
                      "attempt": where.get("attempt"), "pid": os.getpid(), "time": utc_stamp()})


# ---- B1v4's pass check (as v3's B1 check; audit C #4)
def _lines_of(path: str) -> List[dict]:
    recs, _ = soft_stop.JsonlTail().read_new(path, final=True)
    return recs


def b1_check(run_dir: str) -> dict:
    """B1v4 passes when: 2 tasks x 2 live arms (P10: direct_facts_v4, tgr_tracker_v4) = 4 conversations, each with a
    line without error, no line of another arm; 0 error lines (1
    content-filter error allowed); the mean cost per conversation <= B1_MEAN_COST_LIMIT_USD ($0.032 = 3 x $0.0106, v3 B2's
    mean; preregistration_v4.md section 13); and (audit C #4)
    0 Direct + facts v4 checks with a facts failure (rec["direct_facts"]["facts_failure"]) and 0 v4 state errors
    (checks with a state error or a fact-code error). Reads the run folder only."""
    lines: Dict[str, List[dict]] = {}
    for a_ in ARMS:                                       # every arm folder (a B1v4 run has only its 2 live arms)
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
    for r in lines.get("direct_facts_v4", []):
        for at in r.get("attempts") or []:
            part = (at.get("guard") or {}).get("direct_facts") or {}
            df_fail += part.get("facts_failure") is not None
            df_state += part.get("state_error") is not None
    v4_state = sum(v4_state_error_checks(r) for r in lines.get(V4_ARM, []))
    v4_state_only = sum(1 for r in lines.get(V4_ARM, []) for at in r.get("attempts") or []
                        if tracker_part(at.get("guard")).get("state_errors"))
    cost = sum(soft_stop.line_cost(r) for r in allr)
    n_conv = len(units)
    mean = cost / n_conv if n_conv else 0.0
    limit = B1_MEAN_COST_LIMIT_USD
    want_done = B1_CONVERSATIONS - (1 if len(cf) == 1 and len(errs) == 1 else 0)
    checks = {"conversations": n_conv == B1_CONVERSATIONS, "units_done": len(done) >= want_done,
              "arms": set(lines) <= set(STEP_ARMS["B1v4"]),
              "error_lines": len(errs) == 0 or (len(errs) == 1 and len(cf) == 1),
              "mean_cost": mean <= limit + 1e-12, "direct_facts_facts_failures": df_fail == 0,
              "v4_state_errors": v4_state == 0}
    return {"run_dir": run_dir, "pass": all(checks.values()), "checks": checks, "conversations": n_conv,
            "units_done": len(done), "lines": len(allr), "error_lines": len(errs), "content_filter_errors": len(cf),
            "cost_usd": round(cost, 6), "mean_cost_usd": round(mean, 6), "mean_cost_limit_usd": round(limit, 6),
            "direct_facts_facts_failures": df_fail, "direct_facts_state_errors": df_state,
            "v4_state_errors": v4_state, "v4_checks_with_state_errors": v4_state_only,
            "per_arm_lines": {a_: len(v) for a_, v in sorted(lines.items())}}


def b1_summary_module() -> Any:
    """scoring/v4_b1_summary.py (section 13's pass mark; reads files only). A test may put a stand-in first."""
    return importlib.import_module(B1_SUMMARY_MODULE)


def b1_summary_check(run_dir: str) -> dict:
    """Section 13's B1 pass mark from scoring/v4_b1_summary.py summarize(run_dir)["check"] (the mean cost <= $0.032,
    0 errors, the facts failures, the v4 state errors and the safety count; reads files only)."""
    try:
        chk = b1_summary_module().summarize(run_dir)["check"]
        return {"pass": bool(chk.get("pass")), "checks": chk.get("checks"), "mean_cost_usd": chk.get("mean_cost_usd"),
                "safety_bad": chk.get("safety_bad")}
    except Exception as e:  # noqa: BLE001 - a summary that cannot be made is a fail
        return {"pass": False, "error": f"{type(e).__name__}: {e}"[:400]}


def b1_gate(out_root: str, manifest_sha256: Optional[str], real: bool) -> dict:
    """preregistration_v4.md section 13 (audit P7 #2): B2v4, B3v4 and Hv4 start only after a B1v4 run folder
    under <out_root>/B1v4/ passes b1_check AND scoring/v4_b1_summary.py's section 13 check, with the same v4 manifest
    sha256 in its run.json as now. A real run (out_root output/eval_v4) also needs that manifest sha256 to be set and
    the B1v4 run to be a real one (run.json sandbox false, not under the dry-run folder). A sandbox finds only the B1v4
    folders of its own dry-run out root. Returns {"ok", "b1_run_dir", "tried": [...]}. Reads files only."""
    b1_dir = os.path.join(os.path.abspath(out_root), "B1v4")
    tried: List[dict] = []
    if real and manifest_sha256 is None:
        return {"ok": False, "b1_run_dir": None, "tried": [], "reason": "no v4 manifest sha256 (no passing freeze)"}
    names = sorted(os.listdir(b1_dir)) if os.path.isdir(b1_dir) else []
    for name in reversed(names):                               # the newest run id first
        rd = os.path.join(b1_dir, name)
        if not RUN_ID_RE.match(name) or not name.startswith("B1v4_") or not os.path.isdir(rd):
            continue
        why: List[str] = []
        try:
            with open(os.path.join(rd, "run.json"), encoding="utf-8") as f:
                rj = json.load(f)
        except (OSError, ValueError) as e:
            tried.append({"run_dir": rd, "why": [f"run.json unreadable: {type(e).__name__}"]})
            continue
        if (rj.get("ident") or {}).get("step") != "B1v4" or (rj.get("ident") or {}).get("run_id") != name:
            why.append("run.json is not this B1v4 run's")
        if rj.get("v4_manifest_sha256") != manifest_sha256:
            why.append(f"v4 manifest sha256 {rj.get('v4_manifest_sha256')} != now {manifest_sha256}")
        if real and (rj.get("sandbox") is not False or _under(rd, DRYRUN_ROOT)):
            why.append("a sandbox B1v4 run (a real step needs a real B1v4)")
        if os.path.exists(os.path.join(rd, soft_stop_v4.STOP_FILENAME)):
            why.append("its STOP file is present")
        rc = b1_check(rd)
        if not rc["pass"]:
            why.append(f"b1_check fails: {sorted(k for k, v in rc['checks'].items() if not v)}")
        sc = b1_summary_check(rd) if not why else {"pass": None, "skipped": True}
        if not why and not sc["pass"]:
            why.append(f"section 13 check (scoring/v4_b1_summary.py) fails: "
                       f"{sc.get('error') or sorted(k for k, v in (sc.get('checks') or {}).items() if not v)}")
        tried.append({"run_dir": rd, "why": why, "b1_check": rc["pass"], "summary_check": sc.get("pass"),
                      "mean_cost_usd": rc.get("mean_cost_usd")})
        if not why:
            return {"ok": True, "b1_run_dir": rd, "tried": tried}
    return {"ok": False, "b1_run_dir": None, "tried": tried,
            "reason": f"no passing B1v4 run under {b1_dir}" + ("" if names else " (no B1v4 folder)")}


# ---- the P10 baseline: the v3 run that stands in for the arms a step does not run (B2v4, B3v4)
def baseline_info(step: str) -> Optional[dict]:
    """The baseline of a step as run.json keeps it ("baseline": run_dir, run_id, arms, task_file_sha256), or None."""
    b = BASELINES.get(step)
    if b is None:
        return None
    return {"run_dir": b["run_dir"], "run_id": b["run_id"], "arms": list(b["arms"]),
            "task_file": b["task_file"], "task_file_sha256": b["task_file_sha256"],
            "lines_per_arm": b.get("lines_per_arm"), "tasks_per_arm": b.get("tasks_per_arm"),
            "missing_tasks": [f"{d}:{t}" for d, t in b.get("missing_tasks") or ()]}


def baseline_check(step: str, pc_dir: str = PC_DIR, all_tasks: Optional[Sequence[Tuple[str, int]]] = None) -> dict:
    """Does the step's baseline folder hold what the arm plan needs? Reads COUNTS AND KEYS ONLY (never conversation
    content): its run.json's tasks_file_sha256 (top level or ident) must be the recorded one; per baseline arm, the
    lines of <arm>/episodes*.jsonl: B2v4 exactly lines_per_arm (297) per arm; B3v4 the distinct (domain, task) keys of
    each arm (only the "env" / "task_index" fields of a line are kept) must be exactly the B3 task list minus the 15
    fill tasks (49). {"ok", "problems", "per_arm", ...}. A step without a baseline: ok. Only the real path calls it
    (and the $0 `baseline-check` command)."""
    b = BASELINES.get(step)
    out: Dict[str, Any] = {"step": step, "baseline": baseline_info(step), "ok": True, "problems": [], "per_arm": {}}
    if b is None:
        return out
    rd = os.path.join(pc_dir, *b["run_dir"].split("/"))
    probs = out["problems"]
    try:
        with open(os.path.join(rd, "run.json"), encoding="utf-8") as f:
            rj = json.load(f)
        sha = rj.get("tasks_file_sha256") or (rj.get("ident") or {}).get("tasks_file_sha256")
        if (rj.get("ident") or {}).get("run_id") not in (None, b["run_id"]):
            probs.append(f"run.json is of run {(rj.get('ident') or {}).get('run_id')}, not {b['run_id']}")
    except (OSError, ValueError) as e:
        sha = None
        probs.append(f"{b['run_dir']}/run.json unreadable: {type(e).__name__}")
    out["task_file_sha256_found"] = sha
    if sha != b["task_file_sha256"]:
        probs.append(f"task-file sha256 {sha} != recorded {b['task_file_sha256']}")
    want_tasks = None
    if b.get("tasks_per_arm") is not None:
        fill = set(b.get("missing_tasks") or ())
        if all_tasks is None:
            all_tasks = [(x["domain"], x["task_index"]) for x in load_step_tasks(step)["tasks"]]
        want_tasks = {tuple(k) for k in all_tasks} - fill
        if len(want_tasks) != b["tasks_per_arm"]:
            probs.append(f"the task list minus the fill tasks has {len(want_tasks)} tasks, not {b['tasks_per_arm']}")
    for arm in b["arms"]:
        d = os.path.join(rd, arm)
        n, keys = 0, set()
        names = sorted(x for x in os.listdir(d) if soft_stop.is_episodes_file(x)) if os.path.isdir(d) else []
        for name in names:
            with open(os.path.join(d, name), "rb") as f:
                for raw in f:
                    if not raw.strip():
                        continue
                    n += 1
                    if want_tasks is not None:
                        try:
                            r = json.loads(raw)
                            keys.add((r.get("env") or r.get("domain"), int(r.get("task_index"))))
                        except (ValueError, TypeError):
                            probs.append(f"{arm}/{name}: a line without its task key")
                        r = None                        # nothing but the key is kept
        out["per_arm"][arm] = {"files": len(names), "lines": n, "tasks": len(keys) if want_tasks is not None else None}
        if not names:
            probs.append(f"{arm}: no episodes file")
        if b.get("lines_per_arm") is not None and n != b["lines_per_arm"]:
            probs.append(f"{arm}: {n} lines, not {b['lines_per_arm']}")
        if want_tasks is not None and keys != want_tasks:
            probs.append(f"{arm}: {len(keys)} tasks, not the {len(want_tasks)} expected (missing "
                         f"{sorted(want_tasks - keys)[:5]}, extra {sorted(keys - want_tasks)[:5]})")
    out["ok"] = not probs
    return out


# ================================================================================================ the run command

def plan_identity(step: str, run_id: str, tasks: Sequence[dict], tries: int, first_try: int, n_shards: int,
                  approval: str, cap: float, limit: float, tasks_sha: str, task_split: str = TASK_SPLIT,
                  tasks_file: str = TASKS_REL, profile: str = PROFILE,
                  switches: Optional[Dict[str, Any]] = None) -> dict:
    """What every process of one run must share."""
    return {"step": step, "run_id": run_id, "profile": profile, "role_models": dict(ROLE_MODELS[profile]),
            "arms": list(ARMS), "v4_switches": dict(switches or {}),
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
    ident_diff: List[str] = []
    if have.get("ident") != json.loads(json.dumps(ident, default=str)):
        diff = sorted(k for k in set(ident) | set(have.get("ident") or {})
                      if (have.get("ident") or {}).get(k) != json.loads(json.dumps(ident.get(k), default=str)))
        if any(k not in RESUME_AMENDABLE_IDENT for k in diff):
            raise RunRefused(f"{path}: this process's plan differs from the run's ({diff}): refused")
        ident_diff = diff
    amend = resume_amendment(have, extra, ident_diff=ident_diff, ident=ident)
    if amend is not None:
        with open(os.path.join(os.path.dirname(path), AMENDMENTS_FILENAME), "a", encoding="utf-8") as f:
            f.write(json.dumps(amend, sort_keys=True) + "\n")
    return have, created


# User decision 2026-10-24 ("finish H"): after Hv4's money stop its limit was raised ($8 -> $15; B2v4 and B3v4, both
# finished, were lowered to just above their spend, so the limits still add up to <= the $30 cap). That changed
# guard/soft_stop_v4.py and this file, so the freeze was written again (the old manifest is kept as
# <manifest>.superseded_<UTC>). A resume goes on only when every file that changed since the run started is one of
# these (money limits and this resume rule; no guard logic); each such resume is logged to <run>/AMENDMENTS_FILENAME.
RESUME_AMENDABLE = ("guard/soft_stop_v4.py", "guard/run_online_v4.py", "tests/test_v4_run_online.py")
RESUME_AMENDABLE_DOCS = ("docs/planning/tracker_v4/preregistration_v4.md",)    # manifest paths (repository root)
RESUME_AMENDABLE_IDENT = ("approval_quote", "hard_limit_usd")   # plan keys: the user's new words, the raised limit
AMENDMENTS_FILENAME = "resume_amendments.jsonl"


def superseded_manifest(sha: Optional[str], manifest: Optional[str] = None) -> Optional[str]:
    """The copy <manifest>.superseded_<UTC> (scoring/v4_freeze.py --replace) whose sha256 is `sha`, else None."""
    manifest = manifest or os.path.join(V4_ROOT, "v4_freeze.json")
    d, base = os.path.split(manifest)
    if not sha or not os.path.isdir(d):
        return None
    for n in sorted(os.listdir(d)):
        if n.startswith(base + ".superseded_") and sha256_file(os.path.join(d, n)) == sha:
            return os.path.join(d, n)
    return None


def manifest_changes(old: str, new: str) -> List[str]:
    """The paths (as stored) whose sha256 differs between two manifests, or that only one of them lists."""
    def entries(p: str) -> Dict[str, str]:
        with open(p, encoding="utf-8") as f:
            return {e["path"]: e["sha256"] for e in json.load(f)["files"]}
    a, b = entries(old), entries(new)
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def resume_amendment(have: dict, extra: dict, manifest: Optional[str] = None, ident_diff: Sequence[str] = (),
                     ident: Optional[dict] = None) -> Optional[dict]:
    """None when the run's plan, guard inputs and freeze manifest are what they were at its start. Else the amendment
    record, if every changed file is in RESUME_AMENDABLE / RESUME_AMENDABLE_DOCS and every changed plan key in
    RESUME_AMENDABLE_IDENT (checked by the caller); anything else raises RunRefused. A changed plan alone (no changed
    file) is refused: the limit can only change with a re-freeze."""
    a, b = have.get("guard_inputs_sha256") or {}, extra["guard_inputs_sha256"]
    inputs_diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
    old_sha, new_sha = have.get("v4_manifest_sha256"), extra.get("v4_manifest_sha256")
    if not inputs_diff and old_sha == new_sha:
        if ident_diff:
            raise RunRefused(f"this process's plan differs from the run's ({list(ident_diff)}) with no re-freeze: refused")
        return None
    bad_inputs = [k for k in inputs_diff if k not in RESUME_AMENDABLE]
    if bad_inputs:
        raise RunRefused(f"guard inputs changed since the run started ({len(inputs_diff)}: {bad_inputs[:5]}): refused")
    manifest_diff: List[str] = []
    if old_sha != new_sha:
        manifest = manifest or os.path.join(V4_ROOT, "v4_freeze.json")
        old = superseded_manifest(old_sha, manifest)
        if old is None:
            raise RunRefused(f"the v4 freeze manifest changed since the run started ({old_sha} -> {new_sha}): refused")
        manifest_diff = manifest_changes(old, manifest)
        allowed = {f"predicate_correctness/{p}" for p in RESUME_AMENDABLE} | set(RESUME_AMENDABLE_DOCS)
        bad = [p for p in manifest_diff if p not in allowed]
        if bad:
            raise RunRefused(f"the v4 freeze manifest changed since the run started ({old_sha} -> {new_sha}) in files "
                             f"a resume may not change ({bad[:5]}): refused")
    return {"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "old_manifest_sha256": old_sha,
            "new_manifest_sha256": new_sha, "guard_inputs_changed": inputs_diff, "manifest_files_changed": manifest_diff,
            "plan_keys_changed": {k: [(have.get("ident") or {}).get(k), (ident or {}).get(k)] for k in ident_diff},
            "approval_quote": extra.get("approval_quote"), "step_limits_usd": dict(soft_stop_v4.STEP_LIMITS_USD)}


def load_step_tasks(step: str) -> dict:
    """The task list document of a step (v3's files read only, sha256 checked)."""
    kind = STEPS[step]["tasks"]
    if kind == "b3":
        return load_b3_tasks_file()
    return load_tasks_file()


def step_tasks_file(step: str) -> str:
    kind = STEPS[step]["tasks"]
    return B3_TASKS_REL if kind == "b3" else TASKS_REL


def check_role_models(profile: str, used: Dict[str, str]) -> None:
    """The models of every role must be the profile's (ROLE_MODELS): Hv4 only has gpt-5-nano, for the agent only."""
    want = ROLE_MODELS[profile]
    if used != want or any(m not in ALLOWED_MODELS for m in used.values()):
        raise RunRefused(f"models {used} refused: profile {profile} must give {want}")


def main_chat_given(a) -> bool:
    return getattr(a, "main_chat", False) is True


def real_approval_flag(sandbox: bool, dry: bool, main_chat: bool) -> bool:
    """RealBackendV4's approval_flag: True only on the real path (not a sandbox, not a dry run) with MAIN_CHAT_FLAG."""
    return (not sandbox) and (not dry) and main_chat is True


def tiny_budget(limit_usd: float, max_calls: int, n_shards: int) -> Tuple[float, int]:
    """Each shard's tiny-question budget (audit P7 #4): its share of the step's hard limit and call budget, so the
    shards together never get more than the step's (limit / n dollars, floor(max_calls / n) calls)."""
    n = max(1, int(n_shards))
    return float(limit_usd) / n, max(1, int(max_calls) // n)


def cmd_run(a, argv: Sequence[str]) -> dict:
    step, run_id = a.step, a.run_id
    refuse_dropped(step)
    if step not in STEPS:
        raise RunRefused(f"unknown step {step!r} (built: {sorted(STEPS)})")
    check_run_id(step, run_id)
    cfg = STEPS[step]
    shard = parse_shard(a.shard)
    if shard[1] not in cfg["shards"]:
        raise RunRefused(f"{step} runs with {cfg['shards']} shard(s), not {shard[1]}")
    if not 1 <= a.workers <= MAX_WORKERS:
        raise RunRefused(f"--workers {a.workers}: 1-{MAX_WORKERS} per shard")
    p = resolve_paths(a.out_root, step, run_id, shard)
    sandbox, dry = p["sandbox"], a.dry_run
    if not sandbox:                                           # a real run: the pre-registered size only (audit B #7)
        if a.tries is not None:
            raise RunRefused(f"{step}: --tries is fixed ({cfg['tries']}) outside the sandbox")
        if getattr(a, "arms", None) is not None:
            raise RunRefused(f"{step}: --arms is refused outside the sandbox (the arm plan is fixed: "
                             f"{list(soft_stop_v4.step_live_arms(step))})")
        if a.task_ids is not None:
            raise RunRefused(f"{step}: --task-ids is refused outside the sandbox ("
                             + ("B1v4 runs its fixed pair retail:4, airline:4" if step == "B1v4"
                                else f"all {cfg['n_tasks']} tasks run") + ")")
    if not (sandbox or dry) and not main_chat_given(a):       # audit P7 #1: the real path is the main chat's only
        raise RunRefused(f"a real run (not a sandbox, not --dry-run) runs only from the main chat: {MAIN_CHAT_FLAG} "
                         f"is needed (as scoring/v4_offline_eval.py's real backend)")
    if not (sandbox or dry):                                  # audit P9 #1d, #5 (reads files only; before anything)
        probs = real_start_problems(step, run_id, a.approval, p["out_root"])
        if probs:
            raise RunRefused("a real start is refused: " + " | ".join(probs))

    # ---- safety first, before any runner import
    write_guard.install([OUTPUT_DIR])
    if sandbox or dry:
        install_net_recorder()                                # sees each refused attempt (host names)
        from state_tracker.v3 import questions as Q
        Q.block_network()
        preload_urllib3_without_probe()                       # no import-time IPv6 socket (tau_bench -> litellm)
    if sandbox:
        install_sandbox()
    prob = approval_problem(a.approval)
    if prob and not (sandbox or dry):
        raise RunRefused(prob)
    if not (sandbox or dry):
        want_log = os.path.realpath(p["log"])
        if stdout_target() != want_log:
            raise RunRefused(f"stdout must be the log file {p['log']} (got {stdout_target()})")
    probs = soft_stop_v4.backup_problems(p["step_dir"], full=True)
    if probs:                                                 # audit B #1: a moved backup hides spend
        raise RunRefused(f"{len(probs)} backup(s) *.jsonl.before_resume have no live file of at least the same size "
                         f"with the same first bytes (copy, never move): {probs[:3]}")
    lock_path = shard_lock_path(p["step_dir"], shard)
    if dry:
        lock_fd = None
        if shard_lock_held(lock_path):
            raise RunRefused(f"another process runs this shard (the lock {lock_path} is held): refused")
    else:
        lock_fd = acquire_shard_lock(lock_path, run_id)
    try:
        live = other_runs_live(p["step_dir"], run_id)          # audit P9 #2: after our own lock is written (a race
        if live and not dry:                                  # of two run ids refuses at least one of them)
            raise RunRefused(f"another run id of {step} has a live runner ({live[:3]}): one run of a step at a time; "
                             f"refused")
        return _cmd_run_locked(a, argv, step, run_id, cfg, shard, p, sandbox, dry, prob, lock_path)
    finally:
        release_shard_lock(lock_fd)


def _cmd_run_locked(a, argv, step, run_id, cfg, shard, p, sandbox, dry, prob, lock_path) -> dict:
    """cmd_run after the safety checks, with the shard's lock held (not in a dry run)."""
    from state_tracker.v3 import frozen
    frozen.check_manifest()                                   # eval v2 data and method unchanged
    real = not (sandbox or dry)
    freeze = freeze_check(require=real)                       # a real run never starts without a passing freeze
    gate = None
    if step in B1_GATED_STEPS:                                # section 13: only after a passing B1v4 (audit P7 #2)
        gate = b1_gate(p["out_root"], freeze.get("manifest_sha256"), real)
        if not gate["ok"] and not dry:                        # a dry run (0 calls) only reports it
            raise RunRefused(f"{step} starts only after a passing B1v4 run (b1_check and preregistration_v4.md "
                             f"section 13, scoring/v4_b1_summary.py) with the same v4 manifest sha256: "
                             f"{gate.get('reason')}; tried {[(os.path.basename(t['run_dir']), t['why']) for t in gate['tried'][:3]]}")
    doc = load_step_tasks(step)
    task_split = step_task_split(step)
    tasks = select_tasks(doc, step, parse_task_ids(a.task_ids))
    tries = cfg["tries"] if a.tries is None else a.tries
    if not 1 <= tries <= 6:
        raise RunRefused(f"--tries {tries}: 1-6")
    if not sandbox and (len(tasks), tries) != ((2 if step == "B1v4" else cfg["n_tasks"]), cfg["tries"]):
        raise RunRefused(f"{step}: {len(tasks)} tasks x {tries} tries is not the pre-registered size")
    if not sandbox and step == "B1v4" and [(x["domain"], x["task_index"]) for x in tasks] != b1_tasks(doc):
        raise RunRefused(f"B1v4 runs only its fixed pair {b1_tasks(doc)}")
    if task_split == TASK_SPLIT:                              # belt and braces: never the partner's test 66
        sp = load_splits()
        bad = [f"{x['domain']}:{x['task_index']}" for x in tasks if sp[x["domain"]].get(str(x["task_index"]))
               not in GROUPS]
        if bad:
            raise RunRefused(f"tasks {bad} are in the partner's test group: refused")
    profile = cfg["profile"]
    cap = soft_stop_v4.cap_usd()
    limit = soft_stop_v4.STEP_LIMITS_USD[step]
    only = parse_arms(getattr(a, "arms", None))               # sandbox only (refused above outside the sandbox)
    all_units = plan_units(tasks, tries, cfg["first_try"], step, only)
    live_arms = tuple(x for x in ARMS if x in {u[3] for u in all_units})     # P10: the arms this run builds
    if not sandbox and (len(all_units) != WANT_UNITS[step] or set(live_arms) != set(soft_stop_v4.step_live_arms(step))):
        raise RunRefused(f"{step}: {len(all_units)} units, the pre-registered size is {WANT_UNITS[step]}")
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
    act = models.activate(profile, "guard")
    used = {r: act["roles"][r]["model"] for r in ("agent", "user", "guard")}
    check_role_models(profile, used)
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
    tiny_usd, tiny_calls = tiny_budget(limit, cfg["max_calls"], shard[1])   # this shard's share (audit P7 #4)
    if V3_ARM in live_arms:                                   # two tiny-question backends: each gets half
        tiny_usd, tiny_calls = tiny_usd / 2.0, max(1, tiny_calls // 2)
    if dry:                                                   # plan only: fake answers in memory, nothing written
        answers, meter = make_answers_hook(True, None, a.approval, tiny_usd, tiny_calls, log_fn, memory=True)
    else:
        if real and (prob is not None or not freeze.get("ok") or not main_chat_given(a)
                     or (gate is not None and not gate["ok"])):   # belt and braces: all checked above
            raise RunRefused("a real run needs the approval words, a passing freeze, the main chat's flag and (after "
                             "B1v4) a passing B1v4 before the real backend")
        answers, meter = make_answers_hook(sandbox, p["questions_store"], a.approval, tiny_usd, tiny_calls,
                                           log_fn, asks_path=p["asks_log"],
                                           approval_flag=real_approval_flag(sandbox, dry, main_chat_given(a)))
    v3_answers = v3_meter = None
    if V3_ARM in live_arms:                                   # P10: v3's tracker, v3's own hook (v3 runner, unchanged)
        v3_answers, v3_meter = make_v3_answers_hook(sandbox, dry, p["questions_store_v3"], a.approval, tiny_usd,
                                                    tiny_calls, log_fn)
    guards_by: Dict[str, Dict[str, Any]] = {a_: {} for a_ in live_arms}
    infos: Dict[str, Dict[str, Any]] = {a_: {} for a_ in live_arms}
    for d in DOMAINS:
        for arm in live_arms:
            guards_by[arm][d], infos[arm][d] = build_arm(arm, d, tools[d], answers, meter, require_freeze=real,
                                                         step=step, v3_answers=v3_answers, v3_meter=v3_meter)
    router = JudgeRouter(dict(p["structured_cache"]))
    router.install(calls_module)
    judge = JudgeMeter()
    judge.install(calls_module)                                # pass-through: the judge cost of error lines
    switches = v4_switches()
    ident = plan_identity(step, run_id, tasks, tries, cfg["first_try"], shard[1], a.approval, cap, limit,
                          doc["sha256"], task_split=task_split, tasks_file=step_tasks_file(step), profile=profile,
                          switches=switches)
    if cfg["tasks"] == "b3":
        ident["b3_build"] = B3_BUILD
    inputs = guard_inputs_sha256()                            # after the v4 modules are imported (INPUT_FILES)
    if cfg["tasks"] == "b3":                                  # B3v4's own task list and τ-bench task file
        inputs[B3_TASKS_REL] = doc["sha256"]
        inputs["tau_bench(venv)/envs/retail/tasks_train.py"] = doc["source"]["tau_bench_tasks_train"]["retail"][
            "sha256"]
    if real:                                                  # again, now the v4 modules (INPUT_FILES) are loaded
        cov = freeze_coverage((freeze.get("coverage") or {}).get("manifest"))
        if not cov["ok"]:
            raise RunRefused(f"the v4 freeze manifest does not list every runner input with its sha256: "
                             f"unlisted {cov['unlisted'][:10]}, changed {cov['changed'][:10]}, {cov['problems'][:3]}")

    baseline_plan = baseline_info(step)                       # P10: the v3 run standing in for the arms not run
    if baseline_plan is not None:
        if real:                                              # counts and keys only; refused if they differ
            bc = baseline_check(step, all_tasks=[(x["domain"], x["task_index"]) for x in doc["tasks"]])
            if not bc["ok"]:
                raise RunRefused(f"{step}: the baseline {baseline_plan['run_dir']} does not hold what the arm plan "
                                 f"needs: {bc['problems'][:5]}")
            baseline_plan = dict(baseline_plan, check={"ok": True, "per_arm": bc["per_arm"],
                                                       "task_file_sha256_found": bc["task_file_sha256_found"]})
        else:
            baseline_plan = dict(baseline_plan, check="real runs only (a sandbox / dry run never reads v3's runs; "
                                                      "$0 check: python -B -m guard.run_online_v4 baseline-check "
                                                      f"--step {step})")
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
    ss = soft_stop_v4.SoftStopV4(step, cap_usd=cap, hard_limit_usd=limit, step_dir=p["step_dir"],
                                 root=p["out_root"] if sandbox else V4_ROOT, n_shards=shard[1])
    plan = {"argv": list(argv), "ident": ident, "models": used, "profile": profile, "paths": p, "sandbox": sandbox,
            "dry_run": dry, "shard": f"{shard[0]}/{shard[1]}", "units_in_run": len(all_units),
            "units_in_shard": len(mine), "units_done": len(mine) - len(todo), "units_to_run": len(todo),
            "units_per_shard": {f"{i}/{shard[1]}": len(shard_units(all_units, tasks, (i, shard[1])))
                                for i in range(shard[1])},
            "shards_cover_every_unit_once": sorted(u for i in range(shard[1])
                                                   for u in shard_units(all_units, tasks, (i, shard[1])))
            == sorted(all_units),
            "domains_in_shard": sorted({u[0] for u in mine}), "first_units": [list(u) for u in todo[:10]],
            "dropped_groups_now": len(files.dropped), "v4_state_errors_now": files.v4_state_errors,
            "open_groups_at_start": [list(g) for g in open_groups], "workers": a.workers,
            "shard_lock": {"path": lock_path, "held_by_another_process": (shard_lock_held(lock_path) if dry
                                                                           else False)},
            "tools_sha256": tools_sha, "tau_copy_preloaded": preloaded, "guard_info": infos,
            "approval_problem": prob, "soft_stop_v4": ss.run_json(), "v4_freeze": freeze, "b1_gate": gate,
            "main_chat_flag": main_chat_given(a), "watcher_command": watcher_command(step, run_id, p["out_root"]),
            "watcher_needed_for_a_real_start": step in WATCHED_STEPS,
            "watcher_live": watcher_live(step, run_id) if step in WATCHED_STEPS else None,
            "other_runs_live": other_runs_live(p["step_dir"], run_id),
            "real_start_problems": (real_start_problems(step, run_id, a.approval, p["out_root"]) if dry and not sandbox
                                    else None),
            "halfway_backup": {"module": INTERIM_MODULE, "every_s": HALFWAY_BACKUP_EVERY_S,
                               "applies": step in soft_stop_v4.HALFWAY_CONVERSATIONS},
            "live_arms": list(live_arms), "arms_override": list(only) if only else None,
            "units_per_arm": dict(collections.Counter(u[3] for u in all_units)),
            "baseline": baseline_plan,
            "tiny_budget_shard": {"usd": tiny_usd, "calls": tiny_calls, "step_limit_usd": limit,
                                  "step_max_calls": cfg["max_calls"], "n_shards": shard[1]},
            "write_guard": {"installed": write_guard.installed(), "allowed": [OUTPUT_DIR]}}
    if dry:
        from state_tracker.v3 import questions as Q
        plan["llm_calls"] = {"agent": counter.n["agent"], "user": counter.n["user"],
                             "judge": sum(router.calls.values()), "tiny": meter.total["calls"]}
        plan["network_attempts_blocked"] = len(Q.network_events())
        print(f"{PFX} DRY RUN (no LLM call, nothing written):")
        print(json.dumps(plan, indent=1, default=str))
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
             "guard_inputs_sha256": inputs, "tasks_file_sha256": doc["sha256"], "models": used, "profile": profile,
             "v4_manifest_sha256": freeze.get("manifest_sha256"), "v4_freeze": freeze, "b1_gate": gate,
             "soft_stop_v4": ss.run_json(), "baseline": baseline_plan, "live_arms": list(live_arms),
             "cache_root": p["cache_root"], "written_by": f"guard/run_online_v4.py "
             f"({VERSION})", "sandbox": sandbox}
    run_json, created = ensure_run_json(p["run_json"], ident, extra)
    with open(p["pids"], "a", encoding="utf-8") as f:
        f.write(f"{os.getpid()} {os.getpgid(0)} {shard[0]}/{shard[1]} {utc_stamp()}\n")
    write_atomic_json(p["shard_record"], dict(plan, pid=os.getpid(), created_run_json=created))
    wpath = os.path.join(p["run_dir"], WATCHER_FILENAME)       # the same text from every shard (atomic replace)
    wtmp = f"{wpath}.tmp_{os.getpid()}_{threading.get_ident()}"
    with open(wtmp, "w", encoding="utf-8") as f:
        f.write(plan["watcher_command"] + "\n")
    os.replace(wtmp, wpath)
    ok, reason = ss.can_start_step()
    print(f"{PFX} {step}/{run_id} shard {shard[0]}/{shard[1]} start: {len(todo)} units "
          f"({len(mine) - len(todo)} already done), {len(tasks)} tasks x {tries} tries x {len(ARMS)} arms; profile "
          f"{profile}; step start: {reason}", flush=True)
    print(f"{PFX} halfway watcher (the main chat starts it once per run, in the background, BEFORE the shards; a "
          f"real {'/'.join(WATCHED_STEPS)} start is refused without it; also in {wpath}; live now: "
          f"{watcher_live(step, run_id)}): {plan['watcher_command']}", flush=True)
    router.build(models, calls_module)
    started = time.time()

    def run_unit(u: tuple, attempt: int) -> dict:
        d, t, k, arm = u
        models.reset_episode_usage()
        meter.start_episode()
        if v3_meter is not None:
            v3_meter.start_episode()
        judge.start_episode()
        where = unit_where(run_id, step, d, t, k, arm, attempt)
        set_conversation(where, answers)                       # `where` per unit (the guard adds the check index)
        ledger_line(p["ledger"], "start", where, u)            # before the first call (a killed shard's unit counts)
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
        finally:
            set_conversation(None, answers)
        usage = json.loads(json.dumps(models.episode_usage()))
        if rec["error"] is not None and arm == V3_ARM and v3_meter is not None:
            ep3 = v3_meter.episode()              # v3's tiny questions of a failed conversation cost money too
            usage["v3_tiny_questions"] = {"calls": ep3["calls"], "cost": round(ep3["usd"], 8)}
        if rec["error"] is not None and arm == V4_ARM:
            ep = meter.episode()                  # the tiny questions of a failed conversation still cost money
            usage["v4_tiny_questions"] = {"calls": ep["calls"], "cost": round(ep["usd"], 8)}
        if rec["error"] is not None and arm in LLM_ARMS:
            jm = judge.episode()                  # the judge calls of a failed conversation still cost money
            usage["guard_judge"] = {"calls": jm["calls"], "cost": round(jm["usd"], 8)}
        rec["usage_roles"] = usage
        if "cost" in rec:
            rec["cost"]["agent"], rec["cost"]["user"] = usage["agent"]["cost"], usage["user"]["cost"]
        rec.update({"env": d, "guard": arm, "trial": k, "profile": profile, "models": used, "task_split": task_split})
        rec.update({"arm": arm, "task_group": task_of[(d, t)]["group"], "step": step, "run_id": run_id,
                    "unit_attempt": attempt, "shard": f"{shard[0]}/{shard[1]}",
                    "conversation_id": where["conversation_id"]})
        write_line(p["episodes"][arm], rec)
        ledger_line(p["ledger"], "end", where, u)              # its money is in the episode line now
        return rec

    def on_live(running: int, left_open: int) -> None:
        try:
            write_atomic_json(p["live"], {"running": running, "left_open": left_open, "pid": os.getpid(),
                                          "updated": utc_stamp()})
        except OSError:
            pass

    def can_start_unit(running: int = 0) -> Tuple[bool, str]:
        o_run, _ = others_live(p["run_dir"], p["live"])      # in flight in every shard (audit P7 #4)
        return ss.can_start_unit(running_units=running + o_run)

    hw_state: Dict[str, Any] = {}

    def can_start(n_units: int, running: int, left_open: int) -> Tuple[bool, str]:
        files.scan()
        if files.v4_state_errors >= STATE_ERROR_STOP:
            return False, f"v4 state errors: {files.v4_state_errors} checks (stop at {STATE_ERROR_STOP})"
        if ss.stopped is not None:
            return False, f"stopped ({ss.stopped['rule']}): {ss.stopped['detail']}"
        if step in soft_stop_v4.HALFWAY_CONVERSATIONS:       # audit P9 #1a: the runner's own halfway backup
            ok_h, why_h = halfway_backup(p["run_dir"], step, len(files.done), hw_state)
            if not ok_h:
                return False, why_h
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
                     stop=None if ok else f"step start refused: {reason}",
                     group_lock=lambda: step_flock(p["step_lock"]))
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
          f"step spend ${rep['step_usd']:.4f}; v4 total ${rep['total_usd']:.4f}; refused writes "
          f"{len(write_guard.REFUSED)}; judge cost metered ${judge.total['usd']:.4f} ({judge.total['calls']} calls)",
          flush=True)
    out = dict(plan, result=st, report=rep)
    if step == "B1v4":
        out["b1_check"] = b1_check(p["run_dir"])
        print(f"{PFX} B1v4 check (this shard's view of the run folder): {json.dumps(out['b1_check'], default=str)}",
              flush=True)
    return out


# ================================================================================================ main

def _check_task_file(path: str, rel: str, want: str, text: str) -> None:
    with open(path, encoding="utf-8") as f:
        same = f.read() == text
    print(f"{PFX} {rel}: {'equal to' if same else 'DIFFERS FROM'} a fresh build; sha256 {sha256_file(path)} "
          f"(recorded {want})")
    if not same:
        raise RunRefused(f"{rel} differs from a fresh build (v3's file; the v4 runner never writes it)")


def refuse_dropped_argv(argv: Sequence[str]) -> None:
    """Before argparse (whose "invalid choice" says nothing of why): a dropped step or its old flag is refused with
    the reason (DROPPED_STEPS, DROPPED_FLAGS)."""
    for i, x in enumerate(argv):
        if x == "--step" and i + 1 < len(argv):
            refuse_dropped(argv[i + 1])
        elif x.startswith("--step="):
            refuse_dropped(x.split("=", 1)[1])
        elif x in DROPPED_FLAGS or x.split("=", 1)[0] in DROPPED_FLAGS:
            raise RunRefused(f"{x}: refused. {DROPPED_STEPS['DEV20v4']}")


def main(argv: Optional[Sequence[str]] = None):
    argv = list(sys.argv[1:] if argv is None else argv)
    refuse_dropped_argv(argv)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tasks-file", help="check output/eval_v3/online_tasks.json against a fresh build (read only)")
    t.add_argument("--check", action="store_true", help="(the default; kept for v3's command line)")
    t3 = sub.add_parser("b3-tasks-file", help="check output/eval_v3/b3_tasks.json against a fresh build (read only)")
    t3.add_argument("--check", action="store_true", help="(the default; kept for v3's command line)")
    n = sub.add_parser("new-id", help="print a fresh run id")
    n.add_argument("--step", required=True, choices=sorted(STEPS))
    r = sub.add_parser("run", help="run one shard of a step")
    r.add_argument("--step", required=True, choices=sorted(STEPS))
    r.add_argument("--run-id", required=True)
    r.add_argument("--shard", default=None, help=f"i/n (n <= {MAX_SHARDS}; B1v4: 1 shard)")
    r.add_argument("--workers", type=int, default=6, help=f"1-{MAX_WORKERS} per shard")
    r.add_argument("--approval", "--approved", dest="approval", default=None,
                   help="the user's own approval words for this paid step (copied in)")
    r.add_argument("--task-ids", default=None, help="sandbox only (B1v4: 1 retail + 1 airline task); a real B1v4 "
                                                     "runs its fixed pair retail:4, airline:4")
    r.add_argument("--tries", type=int, default=None, help="sandbox only (real runs: fixed)")
    r.add_argument("--arms", default=None, help="sandbox only: a comma list of arms instead of the step's arm plan "
                                                "(the identity check)")
    r.add_argument("--out-root", default=V4_ROOT, help="output/eval_v4 (real) or a folder under output/eval_v4/dryrun")
    r.add_argument("--dry-run", action="store_true", help="plan only: build everything, no call, nothing written")
    r.add_argument(MAIN_CHAT_FLAG, dest="main_chat", action="store_true",
                   help="the real path (not a sandbox, not --dry-run): only the main chat runs it; needed there")
    bc = sub.add_parser("baseline-check", help="P10: does the step's v3 baseline run hold what the arm plan needs? "
                                               "($0, counts and keys only; the real start runs the same check)")
    bc.add_argument("--step", required=True, choices=sorted(BASELINES))
    c = sub.add_parser("b1-check", help="B1v4's pass check of a run folder ($0, reads files only)")
    c.add_argument("--run-id", required=True)
    c.add_argument("--out-root", default=V4_ROOT)
    a = ap.parse_args(argv)
    if a.cmd == "baseline-check":
        res = baseline_check(a.step)
        print(json.dumps(res, indent=1, default=str))
        return res
    if a.cmd == "b1-check":
        check_run_id("B1v4", a.run_id)
        res = b1_check(os.path.join(os.path.abspath(a.out_root), "B1v4", a.run_id))
        print(json.dumps(res, indent=1, default=str))
        return res
    if a.cmd == "tasks-file":
        doc = build_tasks_doc()
        _check_task_file(TASKS_FILE, TASKS_REL, TASKS_FILE_SHA256, tasks_doc_text(doc))
        return doc
    if a.cmd == "b3-tasks-file":
        doc = build_b3_tasks_doc()
        _check_task_file(B3_TASKS_FILE, B3_TASKS_REL, B3_TASKS_FILE_SHA256, tasks_doc_text(doc))
        return doc
    if a.cmd == "new-id":
        rid = new_run_id(a.step)
        print(rid)
        return rid
    return cmd_run(a, ["-m", "guard.run_online_v4"] + argv)


if __name__ == "__main__":
    main()
