"""Tracker v3: spend limits and stop rules for the paid runs (docs/planning/tracker_v3/p13.md step 2 and step 5).

A thin module on top of the eval v2 soft stop: it imports the v2 SpendScanner, line_cost, is_episodes_file and
JsonlTail unchanged (guard/soft_stop.py is not edited) and adds the v3 limits. It only reads files. It never writes,
never calls an LLM and never opens the network.

API for the runner (guard/run_online_v3.py)
-------------------------------------------
    ss = SoftStopV3(step="B2", cap_usd=cap_usd(b2v_approved=False))   # or step_dir=..., hard_limit_usd=...
    ok, reason = ss.can_start_step()        # once, before the first unit of the step
    ok, reason = ss.can_start_group(running_units=r, units_left_open=u)   # before each new (task, try) group
    ok, reason = ss.can_start_unit()        # before each unit of an open group: the hard limit and the cap only
    stops = ss.check_stops(run_dir)         # [] or a list of {"rule", "detail"}; also called by can_start_group
    ss.run_json()                           # a dict to store in run.json under "soft_stop_v3"
    ss.report()                             # spend now: total, p12 questions, this step, per arm, errors

  Every "no" is sticky inside one SoftStopV3 object: once a group check says stop, every later one says stop.
  A stop starts no new (task, try) group; open groups finish all 5 arms (the runner does that).

Pure helpers (the same rules, for tests and the main chat's $0 checks):
    cap_usd(b2v_approved) -> 95.0 or 110.0
    v3_spend(root, questions) -> dict           one full scan: the v3 total and its parts
    step_spend(step_dir) -> dict                one full scan of one step folder (v2 SpendScanner)
    questions_spend(paths) -> dict              p12's question-answer spend
    step_start_ok(total, step_spent, limit, cap, step) -> (ok, reason)
    group_start_ok(step_spent, limit, running_units, units_left_open, p90, new_units, total, cap) -> (ok, reason)
    p90_cost(costs, prior, min_done) -> float
    stop_reasons(lines_by_file, arm_of) -> list  the cost and error stop rules
    stop_file_present(run_dir) -> bool           the file STOP in the run folder (written by the main chat)
    backup_problems(folder, full) -> list        backups *.jsonl.before_resume without a matching live file

What counts as v3 spend (all at the logged list price, read only)
-----------------------------------------------------------------
  - p12: the "cost_usd" of every line of output/eval_v3/questions_answers.jsonl (state_tracker/v3/questions.py,
    real mode). Failed API attempts are in the running "spent_usd" of the records but not in "cost_usd"; so the
    p12 spend is max(sum of cost_usd, sum over writer runs of the highest spent_usd). A writer run starts where
    spent_usd falls below half of the highest value seen so far (a new process starts again near 0; the small
    out-of-order steps of 8 workers do not split a run).
  - p14 steps: every episodes*.jsonl line under output/eval_v3/ (v2 SpendScanner and line_cost: the "cost" of the
    line summed over agent + user + guard; an error line counts its usage_roles). v3's tiny questions in p14 are
    counted once, inside the episode line's guard cost. Question files inside a run folder are never counted.
  - backups named *.jsonl.before_resume (made at a resume; is_episodes_file is False for them): for each backup,
    the larger of the backup's spend and its live file's spend is counted (audit B, blocker 1), so a backup that was
    moved (mv) instead of copied (cp) can never hide spend. A copied backup (the live file starts with the same
    bytes and is at least as long) adds nothing: its lines are counted once, in the live file.
    A step does not start (and a running step starts no new group) while any backup under its folder has no live
    file of at least the same size with the same first bytes (backup_problems; the runner refuses too).
  - not counted: the dry-run folder output/eval_v3/dryrun/ (the network is blocked there and the LLMs are fake; what
    its lines say is shown in report()["dryrun_usd_not_counted"]).

Limits
------
  - Per-step hard limit (STEP_LIMITS_USD): B1 $2, B2 $45, B2v $15, B3 $20 (p12 $26 is the plan value; p12 has its
    own budget stop in questions.py).
  - v3 total cap: $95, the plan's value (the plan calls it the sum p12 $26 + B1 $2 + B2 $45 + B3 $20, which is
    $93: the cap keeps $2 of slack); $110 if the optional B2v is approved (+$15). The cap is a parameter and is
    written to run.json. B2v cannot start under a cap below $110.
  - A step starts only if  total so far + (its hard limit - its own spend so far) <= cap.  Equal is allowed.
  - Reserve: a new (task, try) group starts only if
        step spend + (running units + units left in open groups + the new group's units) x p90 <= the step's limit
    (and the same with the v3 total and the cap). p90 = the 90th percentile (nearest rank) of the cost per unit of
    the step's lines; P90_PRIOR_USD until P90_MIN_DONE lines exist. The new group's units (new_units, default 5,
    one per arm) are included because an open group must finish all 5 arms.
  - The step's spend >= its limit, or the total >= the cap: stop.

Stop rules (p13 step 5; lenient on purpose)
-------------------------------------------
  - cost: an arm's mean cost per conversation, after 50 or more of its conversations, over ARM_MEAN_STOP_USD
    (3 x its high estimate: none $0.023, direct $0.044, direct_facts_v3 $0.049, tgr_frozen $0.041,
    tgr_tracker_v3 $0.061); an arm with another name uses the highest of these. Or one conversation over $0.25.
  - errors: 10 or more error lines and over 5 % of the lines, or 5 error lines in a row (in one file, line order).
    An error line is a line whose "error" is not None.
  - the file STOP in the run folder.
  "Over" is strict: a value equal to the threshold does not fire (1e-9 tolerance for float sums).
  The arm of a line is its "guard" field, else its "arm" field, else the name of its folder.
  Not here: the 3rd v3 state error and the halfway harm check (the runner and the main chat do those).

Standard library only. Never imports gold code, the scoring folder or the runner copy.
"""
from __future__ import annotations

import hashlib
import math
import os
import threading
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from guard.soft_stop import JsonlTail, SpendScanner, is_episodes_file, line_cost
from state_tracker import paths

V3_ROOT = os.path.join(paths.OUTPUT_DIR, "eval_v3")
QUESTIONS_FILES = (os.path.join(V3_ROOT, "questions_answers.jsonl"),)      # = questions.ANSWERS_PATH
DRYRUN_DIRNAME = "dryrun"
BACKUP_SUFFIX = ".jsonl.before_resume"
STOP_FILENAME = "STOP"

STEP_LIMITS_USD: Dict[str, float] = {"p12": 26.0, "B1": 2.0, "B2": 45.0, "B2v": 15.0, "B3": 20.0}
V3_CAP_USD = 95.0                 # the plan's cap (p12 26 + B1 2 + B2 45 + B3 20 is 93: $2 of slack)
V3_CAP_WITH_B2V_USD = 110.0       # + B2v 15, only if the user approves B2v
B2V_STEP = "B2v"

ARM_MEAN_STOP_USD: Dict[str, float] = {"none": 0.023, "direct": 0.044, "direct_facts_v3": 0.049,
                                       "tgr_frozen": 0.041, "tgr_tracker_v3": 0.061}
ARM_MIN_CONVERSATIONS = 50
ONE_CONVERSATION_STOP_USD = 0.25
ERROR_MIN_LINES = 10
ERROR_MIN_SHARE = 0.05
ERROR_IN_A_ROW = 5

P90_PRIOR_USD = 0.061             # the highest arm threshold, until P90_MIN_DONE lines are done
P90_MIN_DONE = 20
UNITS_PER_GROUP = 5               # the 5 arms of one (task, try)
EPS = 1e-9


def _num(x) -> Optional[float]:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x == x else None


def _over(x: float, limit: float) -> bool:
    """x is over the limit (strictly, with a float tolerance)."""
    return x - limit > EPS


def cap_usd(b2v_approved: bool = False) -> float:
    return V3_CAP_WITH_B2V_USD if b2v_approved else V3_CAP_USD


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------------------------------- p12: question answers

class QuestionsScanner:
    """p12's question-answer spend (rules in the module docstring). Incremental, like SpendScanner."""

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


# ----------------------------------------------------------------------------------------------- p14: episode lines

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


class V3SpendScanner:
    """The v3 total: p12 questions + episodes lines under root, minus the dry-run folder. Incremental."""

    def __init__(self, root: str = V3_ROOT, questions: Sequence[str] = QUESTIONS_FILES, final: bool = False):
        self.root = os.path.abspath(root)
        self.final = final
        self._all = SpendScanner(self.root, final=final)
        self._dry = SpendScanner(os.path.join(self.root, DRYRUN_DIRNAME), final=final)
        self._q = QuestionsScanner(questions, final=final)
        self._b = BackupSpend(self.root, skip_dryrun=True)

    def scan(self) -> dict:
        a, d, q = self._all.scan(), self._dry.scan(), self._q.scan()
        episodes = a["total_usd"] - d["total_usd"]
        by_file = {k: v for k, v in a["by_file"].items() if not k.split(os.sep)[0] == DRYRUN_DIRNAME}
        b = self._b.scan(by_file)
        return {"total_usd": q["usd"] + episodes + b["extra_usd"], "questions_usd": q["usd"],
                "episodes_usd": episodes, "backups_usd": b["backups_usd"], "backups_extra_usd": b["extra_usd"],
                "dryrun_usd_not_counted": d["total_usd"], "episode_lines": a["episode_lines"] - d["episode_lines"],
                "unreadable": a["unreadable"] + [b for v in q["by_file"].values() for b in v["unreadable"]],
                "questions": q, "by_file": by_file, "backups": b["by_backup"]}

    def total(self) -> float:
        return self.scan()["total_usd"]


def v3_spend(root: str = V3_ROOT, questions: Sequence[str] = QUESTIONS_FILES) -> dict:
    """One full scan: the v3 total and its parts (see the module docstring)."""
    return V3SpendScanner(root, questions, final=True).scan()


class StepSpend:
    """One step folder's spend: the v2 SpendScanner (incremental) plus the extra of its backups (BackupSpend)."""

    def __init__(self, step_dir: str, final: bool = False):
        self.step_dir = os.path.abspath(step_dir)
        self._s = SpendScanner(self.step_dir, final=final)
        self._b = BackupSpend(self.step_dir, skip_dryrun=False)

    def scan(self) -> dict:
        r = self._s.scan()
        b = self._b.scan(r["by_file"])
        return dict(r, total_usd=r["total_usd"] + b["extra_usd"], live_usd=r["total_usd"],
                    backups_usd=b["backups_usd"], backups_extra_usd=b["extra_usd"], backups=b["by_backup"])

    def total(self) -> float:
        return self.scan()["total_usd"]


def step_spend(step_dir: str) -> dict:
    """One full scan of one step folder (all its runs): the v2 SpendScanner report, plus the extra of its backups."""
    return StepSpend(step_dir, final=True).scan()


# ----------------------------------------------------------------------------------------------- the limit checks

def step_start_ok(total_spent: float, step_spent: float, limit: float, cap: float,
                  step: Optional[str] = None) -> Tuple[bool, str]:
    """A step starts only if total so far + (its limit - its own spend so far) <= cap, and its limit is not used up."""
    if step == B2V_STEP and cap < V3_CAP_WITH_B2V_USD - EPS:
        return False, f"B2v needs the cap raised to ${V3_CAP_WITH_B2V_USD:.0f} (B2v approved); cap is ${cap:.2f}"
    if not _over(limit, step_spent):
        return False, f"the step spent ${step_spent:.4f}, its hard limit ${limit:.2f} is used up"
    need = total_spent + (limit - step_spent)
    if _over(need, cap):
        return False, (f"spent ${total_spent:.4f} + the step's limit left ${limit - step_spent:.4f} = ${need:.4f} "
                       f"could pass the v3 cap ${cap:.2f}")
    return True, f"spent ${total_spent:.4f} + limit left ${limit - step_spent:.4f} = ${need:.4f} <= cap ${cap:.2f}"


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
    with total_spent and cap, the v3 cap)."""
    units = int(running_units) + int(units_left_open) + int(new_units)
    reserve = units * float(p90)
    if _over(step_spent + reserve, limit):
        return False, (f"reserve: step spend ${step_spent:.4f} + {units} units x p90 ${p90:.4f} = "
                       f"${step_spent + reserve:.4f} could pass the step's limit ${limit:.2f}")
    if total_spent is not None and cap is not None and _over(total_spent + reserve, cap):
        return False, (f"reserve: v3 spend ${total_spent:.4f} + {units} units x p90 ${p90:.4f} = "
                       f"${total_spent + reserve:.4f} could pass the v3 cap ${cap:.2f}")
    return True, f"reserve ok: ${step_spent:.4f} + {units} x ${p90:.4f} <= ${limit:.2f}"


# ----------------------------------------------------------------------------------------------- the stop rules

def default_arm_of(rec: dict, path: str) -> str:
    for k in ("guard", "arm"):
        v = rec.get(k)
        if isinstance(v, str) and v:
            return v
    return os.path.basename(os.path.dirname(path)) or "?"


def stop_reasons(lines_by_file: Dict[str, Sequence[dict]],
                 arm_of: Callable[[dict, str], str] = default_arm_of) -> List[dict]:
    """The cost and error stop rules of p13 step 5 on these episode lines (each file in line order)."""
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
    top = max(ARM_MEAN_STOP_USD.values())
    for arm, cs in sorted(arms.items()):
        thr = ARM_MEAN_STOP_USD.get(arm, top)
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

class SoftStopV3:
    """One step's limits and stops (see the module docstring). Thread-safe; every stop is sticky."""

    def __init__(self, step: str, *, cap_usd: float = V3_CAP_USD, hard_limit_usd: Optional[float] = None,
                 step_dir: Optional[str] = None, root: str = V3_ROOT, questions: Sequence[str] = QUESTIONS_FILES,
                 p90_prior_usd: float = P90_PRIOR_USD, p90_min_done: int = P90_MIN_DONE,
                 arm_of: Callable[[dict, str], str] = default_arm_of):
        if hard_limit_usd is None:
            if step not in STEP_LIMITS_USD:
                raise ValueError(f"unknown step {step!r}: give hard_limit_usd")
            hard_limit_usd = STEP_LIMITS_USD[step]
        self.step = step
        self.cap = float(cap_usd)
        self.limit = float(hard_limit_usd)
        self.root = os.path.abspath(root)
        self.step_dir = os.path.abspath(step_dir or os.path.join(self.root, step))
        self.p90_prior, self.p90_min_done = float(p90_prior_usd), int(p90_min_done)
        self.arm_of = arm_of
        self._total = V3SpendScanner(self.root, questions)
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
            ok, reason = step_start_ok(total, step_spent, self.limit, self.cap, self.step)
            probs = backup_problems(self.step_dir, full=True)
            if probs:
                ok, reason = False, (f"{len(probs)} backup(s) without a live file of at least the same size and the "
                                     f"same first bytes (copy, never move): {probs[:3]}")
            self.started = {"ok": ok, "reason": reason, "total_usd": total, "step_usd": step_spent}
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
            out.append({"rule": "v3_cap", "detail": f"v3 spend ${total:.4f} >= cap ${self.cap:.2f}"})
        out += stop_reasons(self._lines.scan(), self.arm_of)
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

    def can_start_unit(self) -> Tuple[bool, str]:
        """Before each unit of an open group (and before a re-run): the step's hard limit and the v3 cap only (no
        reserve, no STOP file: open groups finish). A "no" is sticky for new groups too."""
        with self._lock:
            total, step_spent = self._spend()
            if not _over(self.limit, step_spent):
                reason = f"unit refused: step spend ${step_spent:.4f} >= its hard limit ${self.limit:.2f}"
            elif not _over(self.cap, total):
                reason = f"unit refused: v3 spend ${total:.4f} >= the cap ${self.cap:.2f}"
            else:
                return True, f"unit ok: step ${step_spent:.4f} < ${self.limit:.2f}, v3 ${total:.4f} < ${self.cap:.2f}"
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
                    "dryrun_usd_not_counted": t["dryrun_usd_not_counted"], "step_usd": st["total_usd"],
                    "step_backups_usd": st["backups_usd"], "step_backups_extra_usd": st["backups_extra_usd"],
                    "p90_usd": p90_cost(self._lines.costs(), self.p90_prior, self.p90_min_done),
                    "per_arm": per_arm, "stopped": self.stopped, "unreadable": t["unreadable"] + self._lines.bad}

    def run_json(self) -> dict:
        here = os.path.abspath(__file__)
        v2 = os.path.join(os.path.dirname(here), "soft_stop.py")
        return {"module": "guard/soft_stop_v3.py", "module_sha256": file_sha256(here),
                "v2_soft_stop_sha256": file_sha256(v2), "step": self.step, "cap_usd": self.cap,
                "hard_limit_usd": self.limit, "step_dir": self.step_dir, "root": self.root,
                "step_limits_usd": dict(STEP_LIMITS_USD), "arm_mean_stop_usd": dict(ARM_MEAN_STOP_USD),
                "arm_min_conversations": ARM_MIN_CONVERSATIONS, "one_conversation_stop_usd": ONE_CONVERSATION_STOP_USD,
                "error_min_lines": ERROR_MIN_LINES, "error_min_share": ERROR_MIN_SHARE,
                "error_in_a_row": ERROR_IN_A_ROW, "p90_prior_usd": self.p90_prior, "p90_min_done": self.p90_min_done,
                "units_per_group": UNITS_PER_GROUP, "at_start": self.started}
