"""Tracker v4: spend limits and stop rules for the paid runs (docs/planning/tracker_v4/overview.md section 9,
preregistration_v4.md sections 11-12).

A copy of guard/soft_stop_v3.py (sha256 f83a04b4..., left byte-identical), changed only in: the root
(output/eval_v4), the questions files, the steps and their limits, the v4 cap, the per-step cost thresholds, and the
halfway rule as a helper (computed and reported; applied only when asked: the pre-registered check is
scoring/v4_online_interim.py's). It imports the v2 SpendScanner, line_cost,
is_episodes_file and JsonlTail unchanged (guard/soft_stop.py is not edited). It only reads files. It never writes,
never calls an LLM and never opens the network.

API for the runner (guard/run_online_v4.py)
-------------------------------------------
    ss = SoftStopV4(step="B2v4", cap_usd=V4_CAP_USD)   # or step_dir=..., hard_limit_usd=...
    ok, reason = ss.can_start_step()        # once, before the first unit of the step
    ok, reason = ss.can_start_group(running_units=r, units_left_open=u)   # before each new (task, try) group
    ok, reason = ss.can_start_unit(running_units=n)   # before each unit of an open group: the hard limit and the
                                            # cap, with the units in flight (all shards) at p90
    stops = ss.check_stops(run_dir)         # [] or a list of {"rule", "detail"}; also called by can_start_group
    ss.run_json()                           # a dict to store in run.json under "soft_stop_v4"
    ss.report()                             # spend now: total, dev questions, this step, per arm, errors, halfway

  Every "no" is sticky inside one SoftStopV4 object: once a group check says stop, every later one says stop.
  A stop starts no new (task, try) group; open groups finish all 5 arms (the runner does that).

Pure helpers (the same rules, for tests and the main chat's $0 checks):
    v4_spend(root, questions) -> dict           one full scan: the v4 total and its parts
    step_spend(step_dir) -> dict                one full scan of one step folder (v2 SpendScanner)
    questions_spend(paths) -> dict              the dev check's question-answer spend
    step_start_ok(total, step_spent, limit, cap, step) -> (ok, reason)
    group_start_ok(step_spent, limit, running_units, units_left_open, p90, new_units, total, cap) -> (ok, reason)
    p90_cost(costs, prior, min_done) -> float
    arm_thresholds(step) -> {arm: usd}          the cost stop thresholds of a step
    stop_reasons(lines_by_file, arm_of, thresholds) -> list  the cost and error stop rules
    complete_groups(lines_by_file, arms) -> {(env, task, trial): {arm: reward}}
    halfway_check(lines_by_file, mark, ...) -> dict          the halfway harm rule
    stop_file_present(run_dir) -> bool           the file STOP in the run folder (written by the main chat)
    backup_problems(folder, full) -> list        backups *.jsonl.before_resume without a matching live file

What counts as v4 spend (all at the logged list price, read only)
-----------------------------------------------------------------
  - the dev check and the made-up cases (P2): the "cost_usd" of every line of the answers files in QUESTIONS_FILES
    (output/eval_v4/questions_answers_v4.jsonl, output/eval_v4/cases/answers.jsonl; code_change_map.md section 1.2);
    failed API attempts are in the running "spent_usd" of the records but not in "cost_usd"; so the spend is
    max(sum of cost_usd, sum over writer runs of the highest spent_usd). A writer run starts where spent_usd falls
    below half of the highest value seen so far. A missing file counts $0. The dev part of the v4 total is
    max(that, the dev spend ledger output/eval_v4/dev/dev_spend_ledger.jsonl) (audit P9 #6; dev_ledger_spend: read
    only, at every scan, no lock; questions_spend() itself is unchanged, scoring/v4_offline_eval.py dev_room uses it).
  - the live steps: every episodes*.jsonl line under output/eval_v4/ (v2 SpendScanner and line_cost: the "cost" of the
    line summed over agent + user + guard; an error line counts its usage_roles). The v4 tiny questions of a live
    run are counted once, inside the episode line's guard cost. Question files inside a run folder are never counted.
  - backups named *.jsonl.before_resume (made at a resume by cp, never mv; is_episodes_file is False for them): for
    each backup, the larger of the backup's spend and its live file's spend is counted, so a backup that was moved
    instead of copied can never hide spend. A copied backup adds nothing: its lines are counted once, in the live file.
    A step does not start (and a running step starts no new group) while any backup under its folder has no live
    file of at least the same size with the same first bytes (backup_problems; the runner refuses too).
  - units of killed shards (audit P7 #6): a "start" line in <run_dir>/ledger/units_shard<i>of<n>.jsonl (written by
    the runner before the unit's first call) with no "end" line and no live runner process of its pid counts
    ORPHAN_UNIT_USD ($0.25) + the tiny-question cost_usd of its conversation id in the run's answers stores.
  - not counted: the dry-run folder output/eval_v4/dryrun/ (network blocked, fake LLMs; its lines are shown in
    report()["dryrun_usd_not_counted"]). v3's spend (output/eval_v3/) is not part of the v4 cap.

Limits (preregistration_v4.md section 12)
-----------------------------------------
  - Per-step hard limit (STEP_LIMITS_USD; P10 arm plan, user decision): dev $2, B1v4 $1, B2v4 $10, B3v4 $6, Hv4 $8;
    after Hv4's money stop (user decision "finish H", 2026-10-24): B2v4 $7, B3v4 $4 (both finished), Hv4 $15.
    (DEV20v4, the retail-dev-20 side check, is dropped: the build saw those tasks, so they are not unseen; no limit,
    no step.)
  - v4 total cap: $30 (V4_CAP_USD; was $80 before the P10 arm plan). The cap is a parameter and is written to run.json.
  - The P10 arm plan (STEP_ARMS, group_arms): B1v4 / B2v4 run only direct_facts_v4 and tgr_tracker_v4 (v3's B2 run is
    the baseline of the other arms); B3v4 those two on all 64 tasks plus none, direct, tgr_frozen, tgr_tracker_v3 on the
    15 B3_FILL_TASKS; Hv4 all six arms. A group = the live arms of one (domain, task, try).
  - A step starts only if  total so far + (its hard limit - its own spend so far) + the unspent hard limits of the
    other live steps (a shard lock under <step>/locks/ held by a live runner pid; audit P7 #5) <= cap.  Equal is
    allowed.
  - A unit of an open group starts only if the step's spend and the v4 total are under the limit and the cap, and
    spend + (units in flight in all shards, this one included) x p90 stays within both (audit P7 #4); near the limit
    (what is left < 2 x p90 x shards) each unit in flight counts $0.25 instead of p90 (audit P9 #3).
  - Reserve: a new (task, try) group starts only if
        step spend + (running units + units left in open groups + the new group's units) x p90 <= the step's limit
    (and the same with the v4 total and the cap). p90 = the 90th percentile (nearest rank) of the cost per unit of
    the step's lines; $0.061 (P90_PRIOR_USD) until P90_MIN_DONE (20) lines exist.
  - The step's spend >= its limit, or the total >= the cap: stop.

Stop rules (preregistration_v4.md section 11; lenient on purpose, as v3)
------------------------------------------------------------------------
  - cost: an arm's mean cost per conversation, after 50 or more of its conversations in the step, over its step's
    threshold (3 x the arm's high estimate): B2v4 / Hv4 (and B1v4): none $0.022, direct $0.044,
    direct_facts_v4 $0.043, tgr_frozen $0.039, tgr_tracker_v4 $0.030, another arm $0.044; B3v4: none $0.045,
    direct $0.086, direct_facts_v4 $0.085, tgr_frozen $0.083, tgr_tracker_v4 $0.063, another arm $0.086. Or one
    conversation over $0.25.
  - errors: 10 or more error lines and over 5 % of the lines, or 5 error lines in a row (in one file, line order).
  - halfway harm (P10: B2v4 at 149 complete groups of the v4 arms, B3v4 at 32 groups of the 64 v4 tasks;
    HALFWAY_GROUPS, HALFWAY_CONVERSATIONS = 2 per group): at the first moment the mark is reached, tgr_tracker_v4
    vs frozen TGR (v3's baseline run: frozen TGR is not live); <= -0.15 fires. Checked once. The pre-registered check is run by scoring/v4_online_interim.py (main chat or its timer; it writes STOP);
    here it is computed and reported (report()["halfway"]) and applied only with SoftStopV4(halfway_stop=True). Hv4
    and B1v4 have no halfway check.
  - the file STOP in the run folder.
  "Over" is strict: a value equal to the threshold does not fire (1e-9 tolerance for float sums); the halfway rule
  fires at equality ("<= -0.15").
  The arm of a line is its "guard" field, else its "arm" field, else the name of its folder.
  Not here: the 3rd v4 state error (the runner does that).

Standard library only. Never imports gold code, the scoring folder or the runner copy.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import threading
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from guard.soft_stop import JsonlTail, SpendScanner, is_episodes_file, line_cost
from state_tracker import paths

V4_ROOT = os.path.join(paths.OUTPUT_DIR, "eval_v4")
# the dev check's and the made-up cases' answers files (code_change_map.md section 1.2, run_online_v4 row); a missing
# file counts $0
QUESTIONS_FILES = (os.path.join(V4_ROOT, "questions_answers_v4.jsonl"), os.path.join(V4_ROOT, "cases", "answers.jsonl"))
DRYRUN_DIRNAME = "dryrun"
BACKUP_SUFFIX = ".jsonl.before_resume"
STOP_FILENAME = "STOP"

STEPS = ("B1v4", "B2v4", "B3v4", "Hv4")
# preregistration_v4.md section 12. DEV20v4 (the retail-dev-20 side check) is DROPPED (user decision: the build saw
# those 20 tasks, so they are not unseen); it has no step and no limit here.
DROPPED_STEPS = ("DEV20v4",)
# P10 arm plan (user decision): fewer live arms, so lower limits: dev $2 (unchanged), B1v4 $1, B2v4 $10, B3v4 $6,
# Hv4 $8; the v4 total cap $30.
# 2026-10-24, user decision "finish H": Hv4 hit its $8 money stop at 285 of 594 conversations (about $0.024 each, 3x
# the estimate); Hv4 $8 -> $15. B2v4 and B3v4 had finished ($6.25, $3.72) and were lowered to $7 and $4, so the
# limits still add up to <= the cap ($29 <= $30).
STEP_LIMITS_USD: Dict[str, float] = {"dev": 2.0, "B1v4": 1.0, "B2v4": 7.0, "B3v4": 4.0, "Hv4": 15.0}
V4_CAP_USD = 30.0                 # the v4 total cap (P10 arm plan; was $80)

# ---- the P10 arm plan (user decision): live runs no longer run every arm. Every arm the runner knows:
ALL_ARMS = ("none", "direct", "tgr_frozen", "tgr_tracker_v3", "direct_facts_v4", "tgr_tracker_v4")
V4_LIVE_ARMS = ("direct_facts_v4", "tgr_tracker_v4")            # the new arms: live in every step
B3_FILL_ARMS = ("none", "direct", "tgr_frozen", "tgr_tracker_v3")  # B3v4: live only on the B3_FILL_TASKS
# the 15 B3 tasks (retail, τ-bench train file) missing from v3's B3 run (output/eval_v3/B3/B3_20261023T190740Z_9bf882c0,
# 49 tasks per arm): B3v4 runs the fill arms on these only, so every arm has all 64 tasks
B3_FILL_TASKS = tuple(("retail", t) for t in (368, 380, 393, 415, 416, 427, 431, 433, 434, 445, 451, 462, 464, 474, 497))
STEP_ARMS: Dict[str, Tuple[str, ...]] = {"B1v4": V4_LIVE_ARMS, "B2v4": V4_LIVE_ARMS, "B3v4": V4_LIVE_ARMS,
                                         "Hv4": ALL_ARMS}       # Hv4: all 6 arms live on the nano agent


def group_arms(step: str, domain: Any = None, task: Any = None) -> Tuple[str, ...]:
    """The live arms of one (domain, task, try) group of a step: its STEP_ARMS, and for a B3v4 fill task the fill
    arms too (6 arms, in ALL_ARMS order)."""
    arms = STEP_ARMS[step]
    if step == "B3v4" and (domain, task) in B3_FILL_TASKS:
        return tuple(a for a in ALL_ARMS if a in set(arms) | set(B3_FILL_ARMS))
    return tuple(arms)


def step_live_arms(step: str) -> Tuple[str, ...]:
    """Every arm that runs live in a step (any group)."""
    extra = B3_FILL_ARMS if step == "B3v4" else ()
    return tuple(a for a in ALL_ARMS if a in set(STEP_ARMS[step]) | set(extra))

# preregistration_v4.md section 11: 3 x each arm's high estimate (v3's measured upper ends), rounded up to $0.001.
# B2' (B2v4) and H (Hv4) (B1v4 too) use the B2' column; B3' (B3v4) its own.
B2_ARM_MEAN_STOP_USD: Dict[str, float] = {"none": 0.022, "direct": 0.044, "direct_facts_v4": 0.043,
                                          "tgr_frozen": 0.039, "tgr_tracker_v3": 0.030, "tgr_tracker_v4": 0.030}
B3_ARM_MEAN_STOP_USD: Dict[str, float] = {"none": 0.045, "direct": 0.086, "direct_facts_v4": 0.085,
                                          "tgr_frozen": 0.083, "tgr_tracker_v3": 0.063, "tgr_tracker_v4": 0.063}
UNKNOWN_ARM_STOP_USD: Dict[str, float] = {"B2": 0.044, "B3": 0.086}     # an arm with another name
ARM_MEAN_STOP_USD_BY_STEP: Dict[str, Dict[str, float]] = {
    "B1v4": dict(B2_ARM_MEAN_STOP_USD), "B2v4": dict(B2_ARM_MEAN_STOP_USD), "B3v4": dict(B3_ARM_MEAN_STOP_USD),
    "Hv4": dict(B2_ARM_MEAN_STOP_USD)}
UNKNOWN_ARM_BY_STEP: Dict[str, float] = {"B1v4": 0.044, "B2v4": 0.044, "B3v4": 0.086, "Hv4": 0.044}
ARM_MEAN_STOP_USD: Dict[str, float] = dict(B2_ARM_MEAN_STOP_USD)   # the default (an unknown step)
ARM_MIN_CONVERSATIONS = 50
ONE_CONVERSATION_STOP_USD = 0.25
ERROR_MIN_LINES = 10
ERROR_MIN_SHARE = 0.05
ERROR_IN_A_ROW = 5

# the halfway harm rule (preregistration_v4.md section 11): conversations in complete groups; checked once at the
# first moment the count is >= the mark; v4 - frozen TGR <= -0.15 fires. The pre-registered check is run by
# scoring/v4_online_interim.py from the main chat (it writes STOP); this module only computes and reports it unless
# SoftStopV4(halfway_stop=True) is asked for.
# P10: the halfway mark in complete live groups of the v4 arms (HALFWAY_GROUP_ARMS): B2v4 the first 149 groups, B3v4
# 32 groups of the 64 v4 tasks; in conversations of those arms (2 per group). The decision itself (v4 vs v3's
# tgr_frozen baseline) is scoring/v4_online_interim.py's saved halfway.json; here it is only reported.
HALFWAY_GROUPS: Dict[str, int] = {"B2v4": 149, "B3v4": 32}
HALFWAY_GROUP_ARMS = V4_LIVE_ARMS
HALFWAY_CONVERSATIONS: Dict[str, int] = {s: g * len(HALFWAY_GROUP_ARMS) for s, g in HALFWAY_GROUPS.items()}
HALFWAY_DIFF_STOP = -0.15
HALFWAY_ARMS = ("tgr_tracker_v4", "tgr_frozen")   # (new, old): the difference is new - old
GROUP_ARMS = V4_LIVE_ARMS        # a B1v4 / B2v4 group, and the v4 part of every group (complete_groups' default)

P90_MIN_DONE = 20
P90_PRIOR_USD = 0.061             # preregistration_v4.md section 11: $0.061 until 20 lines exist
UNITS_PER_GROUP = len(GROUP_ARMS)  # 2: the live v4 arms of one (task, try); a 6-arm group (Hv4, B3v4 fill) gives its own
EPS = 1e-9

# A unit of a killed shard (audit P7 #6): the runner writes a "start" line to <run_dir>/ledger/units_shard<i>of<n>.jsonl
# before a unit's first call and an "end" line after its episode line. A start without an end whose process is gone
# is an orphan: its money is in no episode line, so it is counted at ORPHAN_UNIT_USD (the one-conversation stop) plus
# the tiny-question cost_usd that the run's answers stores give for its conversation id.
LEDGER_DIRNAME = "ledger"
LOCKS_DIRNAME = "locks"
ORPHAN_UNIT_USD = ONE_CONVERSATION_STOP_USD
RUNNER_CMD_MARK = b"run_online_v4"   # a live runner process has this in /proc/<pid>/cmdline
# the dev check's shared spend ledger (scoring/v4_offline_eval.py DEV_LEDGER), relative to the v4 root; read only
# (audit P9 #6: the dev spend is max(this ledger, the answers files))
DEV_LEDGER_RELPATH = os.path.join("dev", "dev_spend_ledger.jsonl")
DEV_LEDGER_PARTIAL_USD = 0.01        # a cut or bad ledger line (as v4_offline_eval.PARTIAL_LINE_USD)


def arm_thresholds(step: Optional[str]) -> Dict[str, float]:
    """The cost stop thresholds of a step (ARM_MEAN_STOP_USD for an unknown step)."""
    return dict(ARM_MEAN_STOP_USD_BY_STEP.get(step or "", ARM_MEAN_STOP_USD))


def unknown_arm_threshold(step: Optional[str]) -> float:
    """The threshold of an arm with another name in this step (preregistration_v4.md section 11)."""
    return UNKNOWN_ARM_BY_STEP.get(step or "", max(ARM_MEAN_STOP_USD.values()))


def _num(x) -> Optional[float]:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x == x else None


def _over(x: float, limit: float) -> bool:
    """x is over the limit (strictly, with a float tolerance)."""
    return x - limit > EPS


def cap_usd() -> float:
    return V4_CAP_USD


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------------- the dev check: question answers

class QuestionsScanner:
    """The dev check's question-answer spend (rules in the module docstring). Incremental, like SpendScanner."""

    def __init__(self, files: Sequence[str] = QUESTIONS_FILES, final: bool = False):
        self.files = tuple(os.path.abspath(p) for p in files)
        self.final = final
        self._tail = JsonlTail()
        self._st: Dict[str, dict] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _new() -> dict:
        return {"lines": 0, "cost_usd": 0.0, "closed_runs_usd": 0.0, "run_max": 0.0, "runs": 0, "bad": []}

    def _scan(self, path: str) -> None:
        if not os.path.exists(path):
            self._st.pop(path, None)
            self._tail.forget(path)
            return
        s = self._st.setdefault(path, self._new())
        bad: List[dict] = []
        recs, restarted = self._tail.read_new(path, final=self.final, bad=bad)
        if restarted:
            s.clear()
            s.update(self._new())
        s["bad"].extend(bad)
        for rec in recs:
            s["lines"] += 1
            c = _num(rec.get("cost_usd"))
            if c is not None and c > 0:
                s["cost_usd"] += c
            sp = _num(rec.get("spent_usd"))
            if sp is None:
                continue
            if s["runs"] == 0:
                s["runs"] = 1
            elif sp < 0.5 * s["run_max"]:                      # a new writer process started near 0
                s["closed_runs_usd"] += s["run_max"]
                s["run_max"] = 0.0
                s["runs"] += 1
            s["run_max"] = max(s["run_max"], sp)

    def scan(self) -> dict:
        with self._lock:
            for p in self.files:
                self._scan(p)
            by_file = {}
            for p, s in sorted(self._st.items()):
                runs_usd = s["closed_runs_usd"] + s["run_max"]
                by_file[p] = {"lines": s["lines"], "cost_usd_sum": round(s["cost_usd"], 8),
                              "writer_runs": s["runs"], "spent_usd_runs_sum": round(runs_usd, 8),
                              "usd": max(s["cost_usd"], runs_usd), "unreadable": list(s["bad"])}
            return {"usd": float(sum(v["usd"] for v in by_file.values())), "files": list(self.files),
                    "by_file": by_file}


def questions_spend(files: Sequence[str] = QUESTIONS_FILES) -> dict:
    return QuestionsScanner(files, final=True).scan()


# ------------------------------------------------------------------------------------------ live steps: episode lines

PREFIX_QUICK_BYTES = 1 << 16          # group checks compare the first 64 KiB; the step start compares every byte


def _walk_backups(root: str, skip_dryrun: bool = True) -> List[str]:
    """Every *.jsonl.before_resume under root (sorted; the top-level dry-run folder left out if skip_dryrun)."""
    out: List[str] = []
    if not os.path.isdir(root):
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        if skip_dryrun and os.path.abspath(dirpath) == os.path.abspath(root):
            dirnames[:] = [d for d in dirnames if d != DRYRUN_DIRNAME]
        dirnames.sort()
        out += [os.path.join(dirpath, n) for n in sorted(filenames) if n.endswith(BACKUP_SUFFIX)]
    return out


def live_of(backup: str) -> str:
    """The live file of a backup: episodes_x.jsonl.before_resume -> episodes_x.jsonl."""
    return backup[: -len(".before_resume")]


def _same_start(backup: str, live: str, limit: Optional[int] = None) -> bool:
    """The live file starts with the backup's bytes (all of them, or the first `limit`)."""
    left = os.path.getsize(backup) if limit is None else min(limit, os.path.getsize(backup))
    with open(backup, "rb") as fb, open(live, "rb") as fl:
        while left > 0:
            n = min(left, 1 << 20)
            a, b = fb.read(n), fl.read(n)
            if a != b or len(a) < n:
                return False
            left -= n
    return True


def backup_problems(folder: str, full: bool = True, skip_dryrun: bool = True) -> List[str]:
    """Backups under folder whose live file is missing, shorter, or does not start with the same bytes (the backup
    was moved, not copied). full=False compares only the first PREFIX_QUICK_BYTES bytes (for the group checks)."""
    out = []
    for b in _walk_backups(os.path.abspath(folder), skip_dryrun):
        live = live_of(b)
        try:
            if not os.path.exists(live):
                out.append(f"{b}: no live file {os.path.basename(live)} (moved, not copied?)")
            elif os.path.getsize(live) < os.path.getsize(b):
                out.append(f"{b}: the live file is shorter than the backup")
            elif not _same_start(b, live, None if full else PREFIX_QUICK_BYTES):
                out.append(f"{b}: the live file does not start with the backup's bytes")
        except OSError as e:
            out.append(f"{b}: {type(e).__name__}: {e}")
    return out


class BackupSpend:
    """The spend of the backups under root (each backup read once per version) and the extra spend to count: for
    each backup, max(0, backup spend - its live file's spend), so the larger of the two is counted."""

    def __init__(self, root: str, skip_dryrun: bool = True):
        self.root = os.path.abspath(root)
        self.skip_dryrun = skip_dryrun
        self._cache: Dict[str, Tuple[tuple, float]] = {}

    def _usd(self, path: str) -> float:
        st = os.stat(path)
        key = (st.st_ino, st.st_size, st.st_mtime_ns)
        old = self._cache.get(path)
        if old is not None and old[0] == key:
            return old[1]
        recs, _ = JsonlTail().read_new(path, final=True)
        usd = float(sum(line_cost(r) for r in recs))
        self._cache[path] = (key, usd)
        return usd

    def scan(self, live_usd_by_rel: Dict[str, float]) -> dict:
        """live_usd_by_rel: {path relative to root: spend} of the live files (the SpendScanner's by_file)."""
        raw = extra = 0.0
        by = {}
        for b in _walk_backups(self.root, self.skip_dryrun):
            try:
                usd = round(self._usd(b), 6)
            except OSError:
                continue
            rel_live = os.path.relpath(live_of(b), self.root)
            live = round(float(live_usd_by_rel.get(rel_live, 0.0)), 6)
            raw += usd
            extra += max(0.0, usd - live)
            by[os.path.relpath(b, self.root)] = {"usd": usd, "live_usd": live, "extra_usd": max(0.0, usd - live)}
        return {"backups_usd": raw, "extra_usd": extra, "by_backup": by}


def dev_ledger_spend(path: Optional[str]) -> dict:
    """The dev check's shared spend ledger (scoring/v4_offline_eval.py DevLedger, output/eval_v4/dev/
    dev_spend_ledger.jsonl), read the same way as DevLedger.read() but here (this module never imports the scoring
    folder): per "reserve" line its "spend" if written, else its worst-case "usd"; a spend without a reserve counts;
    a bad or cut line counts DEV_LEDGER_PARTIAL_USD. READ ONLY, at call time, no lock (audit P9 #6). A missing file or
    path None: $0. {"path", "usd", "calls", "bad_lines", "exists"}."""
    out = {"path": path, "usd": 0.0, "calls": 0, "bad_lines": 0, "exists": False}
    if not path or not os.path.isfile(path):
        return out
    res: Dict[str, float] = {}
    spends: Dict[str, float] = {}
    bad = 0
    try:
        with open(path, "rb") as f:
            for raw in f:
                try:
                    if not raw.endswith(b"\n"):
                        raise ValueError("cut line")
                    if not raw.strip():
                        continue
                    rec = json.loads(raw.decode("utf-8"))
                    kind, rid, usd = rec["kind"], str(rec["rid"]), float(rec["usd"])
                except (ValueError, KeyError, TypeError, UnicodeDecodeError):
                    bad += 1
                    continue
                if kind == "reserve":
                    res.setdefault(rid, max(0.0, usd))
                elif kind == "spend":
                    spends[rid] = spends.get(rid, 0.0) + max(0.0, usd)
                else:
                    bad += 1
    except OSError:
        return dict(out, exists=True, error="unreadable")
    usd = sum(spends.get(rid, u) for rid, u in res.items())
    usd += sum(v for rid, v in spends.items() if rid not in res) + bad * DEV_LEDGER_PARTIAL_USD
    return dict(out, usd=float(usd), calls=len(res) + bad, bad_lines=bad, exists=True)


class V4SpendScanner:
    """The v4 total: the dev check (max of its spend ledger and its answers files) + episodes lines under root, minus
    the dry-run folder. Incremental (the ledger is read again at every scan: it is small and append only).
    dev_ledger: "root" (default: <root>/DEV_LEDGER_RELPATH, resolved at scan time), None (not read), or a path."""

    def __init__(self, root: str = V4_ROOT, questions: Sequence[str] = QUESTIONS_FILES, final: bool = False,
                 dev_ledger: Optional[str] = "root"):
        self.root = os.path.abspath(root)
        self.final = final
        self.dev_ledger = dev_ledger
        self._all = SpendScanner(self.root, final=final)
        self._dry = SpendScanner(os.path.join(self.root, DRYRUN_DIRNAME), final=final)
        self._q = QuestionsScanner(questions, final=final)
        self._b = BackupSpend(self.root, skip_dryrun=True)
        self._o = OrphanSpend(self.root, skip_dryrun=True)

    def ledger_path(self) -> Optional[str]:
        if self.dev_ledger == "root":
            return os.path.join(self.root, DEV_LEDGER_RELPATH)
        return self.dev_ledger

    def scan(self) -> dict:
        a, d, q = self._all.scan(), self._dry.scan(), self._q.scan()
        led = dev_ledger_spend(self.ledger_path())
        dev_usd = max(float(q["usd"]), float(led["usd"]))          # audit P9 #6: max(ledger, answers files)
        episodes = a["total_usd"] - d["total_usd"]
        by_file = {k: v for k, v in a["by_file"].items() if not k.split(os.sep)[0] == DRYRUN_DIRNAME}
        b = self._b.scan(by_file)
        o = self._o.scan()
        return {"total_usd": dev_usd + episodes + b["extra_usd"] + o["usd"], "questions_usd": q["usd"],
                "dev_ledger_usd": led["usd"], "dev_usd": dev_usd, "dev_ledger": led,
                "orphans_usd": o["usd"], "orphan_units": o["units"],
                "episodes_usd": episodes, "backups_usd": b["backups_usd"], "backups_extra_usd": b["extra_usd"],
                "dryrun_usd_not_counted": d["total_usd"], "episode_lines": a["episode_lines"] - d["episode_lines"],
                "unreadable": a["unreadable"] + [b for v in q["by_file"].values() for b in v["unreadable"]],
                "questions": q, "by_file": by_file, "backups": b["by_backup"]}

    def total(self) -> float:
        return self.scan()["total_usd"]


def pid_cmdline(pid: Any) -> Optional[bytes]:
    """/proc/<pid>/cmdline of a running process (None: no such process or unreadable)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        pass
    except OSError:
        return None
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read()
    except OSError:
        return None


def _as_bytes(x: Any) -> bytes:
    return x if isinstance(x, bytes) else str(x).encode("utf-8")


def pid_alive(pid: Any, marks: Sequence[Any] = ()) -> bool:
    """A runner process with this pid is running now: this process, or /proc/<pid>/cmdline names run_online_v4 AND
    every given mark (the run id of the ledger / lock it came from; audit P9 #7: a reused pid of another runner of
    another run does not count as this run's live runner)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    cmd = pid_cmdline(pid)
    if cmd is None or RUNNER_CMD_MARK not in cmd:
        return False
    return all(_as_bytes(m) in cmd for m in marks if m)


def _walk_ledgers(root: str, skip_dryrun: bool = True) -> List[str]:
    """Every <run_dir>/ledger/units*.jsonl under root (sorted; the top-level dry-run folder left out if skip_dryrun)."""
    out: List[str] = []
    if not os.path.isdir(root):
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        if skip_dryrun and os.path.abspath(dirpath) == os.path.abspath(root):
            dirnames[:] = [d for d in dirnames if d != DRYRUN_DIRNAME]
        dirnames.sort()
        if os.path.basename(dirpath) == LEDGER_DIRNAME:
            out += [os.path.join(dirpath, n) for n in sorted(filenames) if n.startswith("units") and n.endswith(".jsonl")]
    return out


def ledger_open_starts(recs: Iterable[dict]) -> List[dict]:
    """The "start" lines of a ledger with no "end" line of the same (conversation_id, pid) after them."""
    open_: Dict[Tuple[Any, Any], dict] = {}
    for r in recs:
        if not isinstance(r, dict):
            continue
        k = (r.get("conversation_id"), r.get("pid"))
        if r.get("event") == "start":
            open_[k] = r
        elif r.get("event") == "end":
            open_.pop(k, None)
    return list(open_.values())


class OrphanSpend:
    """The money of units of killed shards (see ORPHAN_UNIT_USD): open ledger starts whose pid is not a live runner."""

    def __init__(self, root: str, skip_dryrun: bool = True):
        self.root = os.path.abspath(root)
        self.skip_dryrun = skip_dryrun
        self._cache: Dict[str, Tuple[tuple, List[dict]]] = {}
        self._tiny: Dict[str, Tuple[tuple, Dict[str, float]]] = {}

    def _open_starts(self, path: str) -> List[dict]:
        st = os.stat(path)
        key = (st.st_ino, st.st_size, st.st_mtime_ns)
        old = self._cache.get(path)
        if old is not None and old[0] == key:
            return old[1]
        recs, _ = JsonlTail().read_new(path, final=True)
        starts = ledger_open_starts(recs)
        self._cache[path] = (key, starts)
        return starts

    def _tiny_by_conversation(self, run_dir: str) -> Dict[str, float]:
        """{conversation_id: sum of cost_usd} of the run's tiny-question answers stores (questions/answers*.jsonl)."""
        out: Dict[str, float] = {}
        qd = os.path.join(run_dir, "questions")
        if not os.path.isdir(qd):
            return out
        for name in sorted(os.listdir(qd)):
            if not (name.startswith("answers") and name.endswith(".jsonl")):
                continue
            p = os.path.join(qd, name)
            try:
                st = os.stat(p)
            except OSError:
                continue
            key = (st.st_ino, st.st_size, st.st_mtime_ns)
            old = self._tiny.get(p)
            if old is None or old[0] != key:
                recs, _ = JsonlTail().read_new(p, final=True)
                by: Dict[str, float] = {}
                for r in recs:
                    c = _num(r.get("cost_usd")) if isinstance(r, dict) else None
                    if c and r.get("conversation_id"):
                        by[r["conversation_id"]] = by.get(r["conversation_id"], 0.0) + c
                old = self._tiny[p] = (key, by)
            for k, v in old[1].items():
                out[k] = out.get(k, 0.0) + v
        return out

    def scan(self) -> dict:
        usd, n, by = 0.0, 0, {}
        for p in _walk_ledgers(self.root, self.skip_dryrun):
            try:
                starts = self._open_starts(p)
            except OSError:
                continue
            run_id = os.path.basename(os.path.dirname(os.path.dirname(p)))
            orphans = [s for s in starts
                       if not pid_alive(s.get("pid"), (str(s.get("conversation_id") or run_id).split(":")[0],))]
            if not orphans:
                continue
            tiny = self._tiny_by_conversation(os.path.dirname(os.path.dirname(p)))
            f_usd = sum(ORPHAN_UNIT_USD + tiny.get(str(s.get("conversation_id")), 0.0) for s in orphans)
            usd += f_usd
            n += len(orphans)
            by[os.path.relpath(p, self.root)] = {"orphans": len(orphans), "usd": f_usd,
                                                 "conversation_ids": [s.get("conversation_id") for s in orphans]}
        return {"usd": usd, "units": n, "by_file": by}


def orphan_spend(root: str, skip_dryrun: bool = True) -> dict:
    return OrphanSpend(root, skip_dryrun).scan()


def live_steps(root: str = V4_ROOT, exclude: Sequence[str] = ()) -> Dict[str, List[int]]:
    """{step: [pids]} of the steps under root with a live runner process: a shard lock file
    (<step>/locks/shard*.lock, its first word the holder's pid, its third word, if any, the run id) whose pid is a
    live runner (of that run id, when the lock names one)."""
    out: Dict[str, List[int]] = {}
    for step in STEPS:
        if step in exclude:
            continue
        d = os.path.join(root, step, LOCKS_DIRNAME)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not (name.startswith("shard") and name.endswith(".lock")):
                continue
            try:
                with open(os.path.join(d, name), encoding="utf-8") as f:
                    words = f.read(200).split()
            except OSError:
                continue
            if words and words[0].isdigit() and pid_alive(int(words[0]), tuple(words[2:3])):
                out.setdefault(step, []).append(int(words[0]))
    return out


def live_steps_reserve(root: str = V4_ROOT, exclude: Sequence[str] = ()) -> dict:
    """The unspent hard limits of the other live steps: {"usd", "steps": {step: {limit, spent, left, pids}}}."""
    steps = {}
    for step, pids in live_steps(root, exclude).items():
        limit = STEP_LIMITS_USD.get(step, 0.0)
        spent = step_spend(os.path.join(root, step))["total_usd"]
        steps[step] = {"limit_usd": limit, "spent_usd": spent, "left_usd": max(0.0, limit - spent), "pids": pids}
    return {"usd": float(sum(v["left_usd"] for v in steps.values())), "steps": steps}


def v4_spend(root: str = V4_ROOT, questions: Sequence[str] = QUESTIONS_FILES, dev_ledger: Optional[str] = "root") -> dict:
    """One full scan: the v4 total and its parts (see the module docstring)."""
    return V4SpendScanner(root, questions, final=True, dev_ledger=dev_ledger).scan()


class StepSpend:
    """One step folder's spend: the v2 SpendScanner (incremental) plus the extra of its backups (BackupSpend)."""

    def __init__(self, step_dir: str, final: bool = False):
        self.step_dir = os.path.abspath(step_dir)
        self._s = SpendScanner(self.step_dir, final=final)
        self._b = BackupSpend(self.step_dir, skip_dryrun=False)
        self._o = OrphanSpend(self.step_dir, skip_dryrun=False)

    def scan(self) -> dict:
        r = self._s.scan()
        b = self._b.scan(r["by_file"])
        o = self._o.scan()
        return dict(r, total_usd=r["total_usd"] + b["extra_usd"] + o["usd"], live_usd=r["total_usd"],
                    backups_usd=b["backups_usd"], backups_extra_usd=b["extra_usd"], backups=b["by_backup"],
                    orphans_usd=o["usd"], orphan_units=o["units"], orphans=o["by_file"])

    def total(self) -> float:
        return self.scan()["total_usd"]


def step_spend(step_dir: str) -> dict:
    """One full scan of one step folder (all its runs): the v2 SpendScanner report, plus the extra of its backups."""
    return StepSpend(step_dir, final=True).scan()


# ----------------------------------------------------------------------------------------------- the limit checks

def step_start_ok(total_spent: float, step_spent: float, limit: float, cap: float,
                  step: Optional[str] = None, others_left: float = 0.0) -> Tuple[bool, str]:
    """A step starts only if total so far + (its limit - its own spend so far) + the unspent limits of the other live
    steps (others_left, audit P7 #5) <= cap, and its limit is not used up."""
    if not _over(limit, step_spent):
        return False, f"the step spent ${step_spent:.4f}, its hard limit ${limit:.2f} is used up"
    others_left = max(0.0, float(others_left or 0.0))
    need = total_spent + (limit - step_spent) + others_left
    more = f" + the other live steps' limits left ${others_left:.4f}" if others_left else ""
    if _over(need, cap):
        return False, (f"spent ${total_spent:.4f} + the step's limit left ${limit - step_spent:.4f}{more} = "
                       f"${need:.4f} could pass the v4 cap ${cap:.2f}")
    return True, (f"spent ${total_spent:.4f} + limit left ${limit - step_spent:.4f}{more} = ${need:.4f} <= cap "
                  f"${cap:.2f}")


def p90_cost(costs: Sequence[float], prior: float = P90_PRIOR_USD, min_done: int = P90_MIN_DONE) -> float:
    """The 90th percentile (nearest rank) of the cost per unit; the prior while fewer than min_done are done."""
    xs = sorted(float(c) for c in costs)
    if len(xs) < max(1, min_done):
        return float(prior)
    return xs[max(0, math.ceil(0.9 * len(xs)) - 1)]


def group_start_ok(step_spent: float, limit: float, running_units: int, units_left_open: int, p90: float,
                   new_units: int = UNITS_PER_GROUP, total_spent: Optional[float] = None,
                   cap: Optional[float] = None) -> Tuple[bool, str]:
    """The reserve rule: spend + (running + left in open groups + new) x p90 must not pass the step's limit (nor,
    with total_spent and cap, the v4 cap)."""
    units = int(running_units) + int(units_left_open) + int(new_units)
    reserve = units * float(p90)
    if _over(step_spent + reserve, limit):
        return False, (f"reserve: step spend ${step_spent:.4f} + {units} units x p90 ${p90:.4f} = "
                       f"${step_spent + reserve:.4f} could pass the step's limit ${limit:.2f}")
    if total_spent is not None and cap is not None and _over(total_spent + reserve, cap):
        return False, (f"reserve: v4 spend ${total_spent:.4f} + {units} units x p90 ${p90:.4f} = "
                       f"${total_spent + reserve:.4f} could pass the v4 cap ${cap:.2f}")
    return True, f"reserve ok: ${step_spent:.4f} + {units} x ${p90:.4f} <= ${limit:.2f}"


def unit_reserve_usd(left_usd: float, p90: float, n_shards: int = 1) -> float:
    """The reserve per unit in flight (audit P9 #3): p90, but ORPHAN_UNIT_USD ($0.25, never less than p90) when what
    is left (limit or cap minus spend) is under 2 x p90 x n_shards."""
    if left_usd < 2.0 * float(p90) * max(1, int(n_shards or 1)):
        return max(float(p90), ORPHAN_UNIT_USD)
    return float(p90)


def _reserve_word(per: float, p90: float) -> str:
    return "p90" if per == p90 else f"near the limit: ${ORPHAN_UNIT_USD:.2f} per unit"


# ----------------------------------------------------------------------------------------------- the stop rules

def default_arm_of(rec: dict, path: str) -> str:
    for k in ("guard", "arm"):
        v = rec.get(k)
        if isinstance(v, str) and v:
            return v
    return os.path.basename(os.path.dirname(path)) or "?"


def stop_reasons(lines_by_file: Dict[str, Sequence[dict]],
                 arm_of: Callable[[dict, str], str] = default_arm_of,
                 thresholds: Optional[Dict[str, float]] = None, unknown_arm: Optional[float] = None) -> List[dict]:
    """The cost and error stop rules (preregistration_v4.md section 11) on these episode lines (each file in line
    order). thresholds: {arm: usd} of the step (default ARM_MEAN_STOP_USD); unknown_arm: the threshold of an arm
    with another name (default the highest of thresholds)."""
    thr_by = dict(thresholds if thresholds is not None else ARM_MEAN_STOP_USD)
    out: List[dict] = []
    n = errors = 0
    worst_run = (0, None)
    arms: Dict[str, List[float]] = {}
    for path in sorted(lines_by_file):
        run = 0
        for i, rec in enumerate(lines_by_file[path], 1):
            n += 1
            c = line_cost(rec)
            arms.setdefault(arm_of(rec, path), []).append(c)
            if _over(c, ONE_CONVERSATION_STOP_USD):
                out.append({"rule": "one_conversation", "detail": f"{os.path.basename(path)} line {i}: "
                            f"${c:.4f} > ${ONE_CONVERSATION_STOP_USD:.2f}"})
            if rec.get("error") is not None:
                errors += 1
                run += 1
                if run > worst_run[0]:
                    worst_run = (run, path)
            else:
                run = 0
    top = float(unknown_arm) if unknown_arm is not None else max(thr_by.values())
    for arm, cs in sorted(arms.items()):
        thr = thr_by.get(arm, top)
        if len(cs) >= ARM_MIN_CONVERSATIONS:
            mean = sum(cs) / len(cs)
            if _over(mean, thr):
                out.append({"rule": "arm_mean_cost", "detail": f"arm {arm}: mean ${mean:.4f} over {len(cs)} "
                            f"conversations > ${thr:.3f}"})
    if errors >= ERROR_MIN_LINES and _over(errors / n, ERROR_MIN_SHARE):
        out.append({"rule": "error_share", "detail": f"{errors} error lines of {n} ({100 * errors / n:.1f} %)"})
    if worst_run[0] >= ERROR_IN_A_ROW:
        out.append({"rule": "errors_in_a_row", "detail": f"{worst_run[0]} error lines in a row in "
                    f"{os.path.basename(worst_run[1])}"})
    return out


def stop_file_present(run_dir: Optional[str]) -> bool:
    return bool(run_dir) and os.path.exists(os.path.join(run_dir, STOP_FILENAME))


# ----------------------------------------------------------------------------------------------- the halfway rule

def _unit(rec: dict, path: str, arm_of: Callable[[dict, str], str]) -> Tuple[Any, Any, Any, str]:
    return (rec.get("env"), rec.get("task_index"), rec.get("trial"), arm_of(rec, path))


def complete_groups(lines_by_file: Dict[str, Sequence[dict]], arms: Sequence[str] = HALFWAY_GROUP_ARMS,
                    arm_of: Callable[[dict, str], str] = default_arm_of) -> Dict[tuple, Dict[str, float]]:
    """{(env, task, trial): {arm: reward}} of the (task, try) groups where every arm has a line without error (the
    first such line of a unit counts; files in sorted order, lines in file order)."""
    by: Dict[tuple, Dict[str, float]] = {}
    for path in sorted(lines_by_file):
        for rec in lines_by_file[path]:
            if rec.get("error") is not None:
                continue
            env, t, k, arm = _unit(rec, path, arm_of)
            if arm not in arms:
                continue
            r = _num(rec.get("reward"))
            by.setdefault((env, t, k), {}).setdefault(arm, 0.0 if r is None else r)
    return {g: v for g, v in by.items() if all(a in v for a in arms)}


def halfway_check(lines_by_file: Dict[str, Sequence[dict]], mark: Optional[int],
                  arms: Sequence[str] = HALFWAY_GROUP_ARMS, new_old: Tuple[str, str] = HALFWAY_ARMS,
                  stop_at: float = HALFWAY_DIFF_STOP,
                  arm_of: Callable[[dict, str], str] = default_arm_of) -> dict:
    """The halfway harm rule: once the complete groups hold at least `mark` conversations (groups x arms), the mean
    reward of new_old[0] minus that of new_old[1] over the complete groups; stop when it is <= stop_at.
    Returns {"mark", "groups", "conversations", "reached", "diff", "stop", "detail"}. mark None: never checked."""
    groups = complete_groups(lines_by_file, arms, arm_of)
    n_conv = len(groups) * len(arms)
    out = {"mark": mark, "groups": len(groups), "conversations": n_conv, "reached": False, "diff": None,
           "stop": False, "detail": ""}
    if mark is None or n_conv < mark or not groups:
        out["detail"] = f"{n_conv} conversations in complete groups (mark {mark})"
        return out
    new, old = new_old
    if new not in arms or old not in arms:            # P10: frozen TGR is not live in B2v4 / B3v4 (v3's baseline)
        out.update(reached=True)
        out["detail"] = (f"halfway mark reached: {len(groups)} complete groups ({n_conv} conversations, mark {mark}); "
                         f"{old} is not a live arm here, so the decision ({new} vs v3's {old} baseline) is "
                         f"scoring/v4_online_interim.py's saved halfway.json")
        return out
    diff = sum(v[new] - v[old] for v in groups.values()) / len(groups)
    out.update(reached=True, diff=round(diff, 6), stop=diff - stop_at <= EPS)
    out["detail"] = (f"halfway: {new} - {old} = {diff:+.3f} on {len(groups)} complete groups ({n_conv} "
                     f"conversations, mark {mark}); stop at <= {stop_at:+.2f}")
    return out


class StepLines:
    """The episode lines of one step folder, read incrementally (a replaced or cut file is read again)."""

    def __init__(self, step_dir: str, final: bool = False):
        self.step_dir = os.path.abspath(step_dir)
        self.final = final
        self._tail = JsonlTail()
        self.lines: Dict[str, List[dict]] = {}
        self.bad: List[dict] = []

    def scan(self) -> Dict[str, List[dict]]:
        seen = set()
        if os.path.isdir(self.step_dir):
            for dirpath, dirnames, filenames in os.walk(self.step_dir):
                dirnames.sort()
                for name in sorted(filenames):
                    if not is_episodes_file(name):
                        continue
                    p = os.path.join(dirpath, name)
                    seen.add(p)
                    recs, restarted = self._tail.read_new(p, final=self.final, bad=self.bad)
                    if restarted:
                        self.lines[p] = []
                    self.lines.setdefault(p, []).extend(recs)
        for p in set(self.lines) - seen:
            self.lines.pop(p)
            self._tail.forget(p)
        return self.lines

    def costs(self) -> List[float]:
        return [line_cost(r) for recs in self.lines.values() for r in recs]


# ----------------------------------------------------------------------------------------------- the runner's object

class SoftStopV4:
    """One step's limits and stops (see the module docstring). Thread-safe; every stop is sticky."""

    def __init__(self, step: str, *, cap_usd: float = V4_CAP_USD, hard_limit_usd: Optional[float] = None,
                 step_dir: Optional[str] = None, root: str = V4_ROOT, questions: Sequence[str] = QUESTIONS_FILES,
                 p90_prior_usd: Optional[float] = None, p90_min_done: int = P90_MIN_DONE,
                 arm_of: Callable[[dict, str], str] = default_arm_of,
                 thresholds: Optional[Dict[str, float]] = None, halfway_mark: Any = "step",
                 halfway_stop: bool = False, n_shards: int = 1, dev_ledger: Optional[str] = "root"):
        """thresholds: the cost stop thresholds (default: the step's, arm_thresholds(step)); p90_prior_usd: default
        P90_PRIOR_USD; halfway_mark: "step" (HALFWAY_CONVERSATIONS of the step, None if it has none), None or a
        number of conversations; halfway_stop: False (default: the halfway rule is computed and reported, the
        pre-registered check is scoring/v4_online_interim.py's) or True (this object applies it once, at the first
        group check where the mark is reached; a fire is a sticky stop); n_shards: the step's shard count (the
        near-limit unit reserve, audit P9 #3); dev_ledger: V4SpendScanner's (default <root>/DEV_LEDGER_RELPATH)."""
        if hard_limit_usd is None:
            if step not in STEP_LIMITS_USD:
                raise ValueError(f"unknown step {step!r}: give hard_limit_usd")
            hard_limit_usd = STEP_LIMITS_USD[step]
        self.step = step
        self.cap = float(cap_usd)
        self.limit = float(hard_limit_usd)
        self.root = os.path.abspath(root)
        self.step_dir = os.path.abspath(step_dir or os.path.join(self.root, step))
        self.thresholds = dict(thresholds) if thresholds is not None else arm_thresholds(step)
        self.unknown_arm = unknown_arm_threshold(step) if thresholds is None else max(self.thresholds.values())
        if p90_prior_usd is None:
            p90_prior_usd = P90_PRIOR_USD
        self.p90_prior, self.p90_min_done = float(p90_prior_usd), int(p90_min_done)
        self.halfway_mark = HALFWAY_CONVERSATIONS.get(step) if halfway_mark == "step" else halfway_mark
        self.halfway_stop = bool(halfway_stop)
        self.halfway: Optional[dict] = None              # the halfway check, once the mark was reached (once)
        self.arm_of = arm_of
        self.n_shards = max(1, int(n_shards or 1))
        self._total = V4SpendScanner(self.root, questions, dev_ledger=dev_ledger)
        self._step = StepSpend(self.step_dir)
        self._lines = StepLines(self.step_dir)
        self.stopped: Optional[dict] = None
        self.started: Optional[dict] = None
        self.checks = 0
        self._lock = threading.Lock()

    def _spend(self) -> Tuple[float, float]:
        return self._total.total(), self._step.total()

    def can_start_step(self) -> Tuple[bool, str]:
        with self._lock:
            total, step_spent = self._spend()
            others = live_steps_reserve(self.root, exclude=(self.step,))      # audit P7 #5
            ok, reason = step_start_ok(total, step_spent, self.limit, self.cap, self.step, others_left=others["usd"])
            probs = backup_problems(self.step_dir, full=True)
            if probs:
                ok, reason = False, (f"{len(probs)} backup(s) without a live file of at least the same size and the "
                                     f"same first bytes (copy, never move): {probs[:3]}")
            self.started = {"ok": ok, "reason": reason, "total_usd": total, "step_usd": step_spent,
                            "other_live_steps": others}
            if not ok:
                self.stopped = {"rule": "step_start", "detail": reason}
            return ok, reason

    def check_stops(self, run_dir: Optional[str] = None) -> List[dict]:
        """The stop rules now: STOP file, hard limit, cap, cost and error rules. [] means go on."""
        with self._lock:
            return self._check_stops(run_dir)[0]

    def _check_stops(self, run_dir: Optional[str]) -> Tuple[List[dict], float, float]:
        out = []
        if stop_file_present(run_dir):
            out.append({"rule": "stop_file", "detail": f"{os.path.join(run_dir, STOP_FILENAME)} exists"})
        probs = backup_problems(self.step_dir, full=False)
        if probs:
            out.append({"rule": "backup_moved", "detail": f"{len(probs)} backup(s) without a matching live file: "
                                                          f"{probs[:3]}"})
        total, step_spent = self._spend()
        if not _over(self.limit, step_spent):
            out.append({"rule": "step_limit", "detail": f"step spend ${step_spent:.4f} >= ${self.limit:.2f}"})
        if not _over(self.cap, total):
            out.append({"rule": "v4_cap", "detail": f"v4 spend ${total:.4f} >= cap ${self.cap:.2f}"})
        lines = self._lines.scan()
        out += stop_reasons(lines, self.arm_of, self.thresholds, self.unknown_arm)
        if self.halfway_stop and self.halfway_mark is not None and self.halfway is None:
            h = halfway_check(lines, self.halfway_mark, arm_of=self.arm_of)
            if h["reached"]:                              # checked once, at the first moment the mark is reached
                self.halfway = h
                if h["stop"]:
                    out.append({"rule": "halfway_harm", "detail": h["detail"]})
        return out, total, step_spent

    def can_start_group(self, running_units: int, units_left_open: int, new_units: int = UNITS_PER_GROUP,
                        run_dir: Optional[str] = None) -> Tuple[bool, str]:
        """Before each new (task, try) group: no sticky stop, no stop rule, and the reserve rule holds."""
        with self._lock:
            self.checks += 1
            if self.stopped is not None:
                return False, f"stopped ({self.stopped['rule']}): {self.stopped['detail']}"
            if self.started is None:
                self.stopped = {"rule": "step_start", "detail": "can_start_step() was not called"}
                return False, "stopped: can_start_step() was not called"
            stops, total, step_spent = self._check_stops(run_dir)
            if stops:
                self.stopped = {"rule": stops[0]["rule"], "detail": "; ".join(s["detail"] for s in stops),
                                "all": stops}
                return False, f"stopped ({stops[0]['rule']}): {self.stopped['detail']}"
            p90 = p90_cost(self._lines.costs(), self.p90_prior, self.p90_min_done)
            ok, reason = group_start_ok(step_spent, self.limit, running_units, units_left_open, p90, new_units,
                                        total, self.cap)
            if not ok:
                self.stopped = {"rule": "reserve", "detail": reason}
            return ok, reason

    def can_start_unit(self, running_units: int = 0) -> Tuple[bool, str]:
        """Before each unit of an open group (and before a re-run): the step's hard limit and the v4 cap (no group
        reserve, no STOP file: open groups finish). running_units (audit P7 #4): the units in flight in every shard of
        the step, this one included; their money is not spent yet, so spend + running_units x p90 must stay within
        the hard limit and the cap too. Near the limit (what is left < 2 x p90 x n_shards; audit P9 #3) each unit in
        flight is reserved at ORPHAN_UNIT_USD ($0.25, the one-conversation stop) instead of p90 (unit_reserve_usd).
        A "no" is sticky for new groups too."""
        with self._lock:
            total, step_spent = self._spend()
            n = max(0, int(running_units or 0))
            if n:
                self._lines.scan()
            p90 = p90_cost(self._lines.costs(), self.p90_prior, self.p90_min_done)
            per_step, per_cap = unit_reserve_usd(self.limit - step_spent, p90, self.n_shards), \
                unit_reserve_usd(self.cap - total, p90, self.n_shards)
            if not _over(self.limit, step_spent):
                reason = f"unit refused: step spend ${step_spent:.4f} >= its hard limit ${self.limit:.2f}"
            elif not _over(self.cap, total):
                reason = f"unit refused: v4 spend ${total:.4f} >= the cap ${self.cap:.2f}"
            elif n and _over(step_spent + n * per_step, self.limit):
                reason = (f"unit refused: step spend ${step_spent:.4f} + {n} running units x ${per_step:.4f} "
                          f"({_reserve_word(per_step, p90)}) = ${step_spent + n * per_step:.4f} could pass its hard "
                          f"limit ${self.limit:.2f}")
            elif n and _over(total + n * per_cap, self.cap):
                reason = (f"unit refused: v4 spend ${total:.4f} + {n} running units x ${per_cap:.4f} "
                          f"({_reserve_word(per_cap, p90)}) = ${total + n * per_cap:.4f} could pass the cap "
                          f"${self.cap:.2f}")
            else:
                return True, (f"unit ok: step ${step_spent:.4f} + {n} x ${per_step:.4f} "
                              f"({_reserve_word(per_step, p90)}) <= ${self.limit:.2f}, v4 ${total:.4f} < "
                              f"${self.cap:.2f}")
            if self.stopped is None:
                self.stopped = {"rule": "unit_limit", "detail": reason}
            return False, reason

    def report(self) -> dict:
        with self._lock:
            t = self._total.scan()
            lines = self._lines.scan()
            per_arm: Dict[str, dict] = {}
            for path, recs in lines.items():
                for r in recs:
                    a = per_arm.setdefault(self.arm_of(r, path), {"conversations": 0, "usd": 0.0, "errors": 0})
                    a["conversations"] += 1
                    a["usd"] += line_cost(r)
                    a["errors"] += r.get("error") is not None
            for a in per_arm.values():
                a["mean_usd"] = a["usd"] / a["conversations"]
            st = self._step.scan()
            return {"step": self.step, "cap_usd": self.cap, "hard_limit_usd": self.limit,
                    "total_usd": t["total_usd"], "questions_usd": t["questions_usd"],
                    "dev_ledger_usd": t["dev_ledger_usd"], "dev_usd": t["dev_usd"],
                    "orphans_usd": t["orphans_usd"], "step_orphans_usd": st["orphans_usd"],
                    "dryrun_usd_not_counted": t["dryrun_usd_not_counted"], "step_usd": st["total_usd"],
                    "step_backups_usd": st["backups_usd"], "step_backups_extra_usd": st["backups_extra_usd"],
                    "p90_usd": p90_cost(self._lines.costs(), self.p90_prior, self.p90_min_done),
                    "per_arm": per_arm, "stopped": self.stopped, "unreadable": t["unreadable"] + self._lines.bad,
                    "halfway": (halfway_check(lines, self.halfway_mark, arm_of=self.arm_of)
                                if self.halfway_mark is not None else None)}

    def run_json(self) -> dict:
        here = os.path.abspath(__file__)
        v2 = os.path.join(os.path.dirname(here), "soft_stop.py")
        return {"module": "guard/soft_stop_v4.py", "module_sha256": file_sha256(here),
                "v2_soft_stop_sha256": file_sha256(v2), "step": self.step, "cap_usd": self.cap,
                "hard_limit_usd": self.limit, "step_dir": self.step_dir, "root": self.root,
                "step_limits_usd": dict(STEP_LIMITS_USD), "arm_mean_stop_usd": dict(self.thresholds),
                "unknown_arm_stop_usd": self.unknown_arm, "halfway_stop": self.halfway_stop,
                "halfway_conversations": self.halfway_mark, "halfway_diff_stop": HALFWAY_DIFF_STOP,
                "halfway_arms": list(HALFWAY_ARMS), "todo_markers": todo_markers(),
                "arm_min_conversations": ARM_MIN_CONVERSATIONS, "one_conversation_stop_usd": ONE_CONVERSATION_STOP_USD,
                "error_min_lines": ERROR_MIN_LINES, "error_min_share": ERROR_MIN_SHARE,
                "error_in_a_row": ERROR_IN_A_ROW, "p90_prior_usd": self.p90_prior, "p90_min_done": self.p90_min_done,
                "units_per_group": UNITS_PER_GROUP, "n_shards": self.n_shards,
                "near_limit_unit_reserve_usd": ORPHAN_UNIT_USD, "dev_ledger": self._total.ledger_path(),
                "at_start": self.started}


def todo_markers() -> List[str]:
    """The lines of this file with a v4-prereg TODO marker (values to replace once preregistration_v4.md gives
    them)."""
    mark = "TODO(" + "v4-prereg)"
    with open(os.path.abspath(__file__), encoding="utf-8") as f:
        return [f"{i}: {ln.strip()}" for i, ln in enumerate(f, 1) if mark in ln]
