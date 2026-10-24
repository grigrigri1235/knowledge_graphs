"""Eval v2 Part 3 (fork/find_points.py): find the fork points of saved conversations. No LLM call.

A fork point is the FIRST attempt of a conversation where frozen TGR (A) and TGR + tracker (B) decide differently.
Attempts are taken in order, so:
  - a blocked action that is retried: if the guards differ on its first try, the fork is that first try;
  - if they agree on the earlier tries (both block) and differ only on a later try, the fork is that later try
    (ForkPoint.attempt > 1; consecutive blocks continue from attempt - 1);
  - a check that cannot be compared (a tgr_tracker check where the judge was skipped, so frozen TGR's values are not
    known) counts as "agree"; ForkPoint.not_comparable_before says how many came before the fork.
  - a difference at a 4th try (3 blocks in a row before) has no effect: a block there runs anyway (cap override),
    so both branches run the same action and the conversation goes on the same. It is skipped (counted per run in
    the rates file, "differences skipped: cap override, no effect"; ForkPoint.no_effect_before) and the next
    difference that has an effect is the fork (audit A3 W3, A5 W3).
Only attempts whose guard record has judge values can differ: without a circuit, or with no predicate, both guards
allow, and the tracker has nothing to change.

How each source gets the two decisions (fork/points_tgr.py runs both guards' own code offline, judge values given):
  saved_tgr       the partner's frozen TGR runs from_shieldagent/runs/{luna_train_v5,nano_train}/<domain>/tgr/.
                  A = the saved decision. B = guard/tgr_tracker.py's tracker (version b) on the same history with the
                  saved judge values: this is Part 8's version (b); output/p8_changes.jsonl must list the same
                  changed attempts (checked, see cross_checks in the rates file).
  online_tracker  our runs output/online/{p10_luna_train,p10_nano_train,p10_luna_val}/<domain>/tgr_tracker/.
                  B = the saved decision. A = frozen TGR with the judge's own values (guard.tracker.judge_values),
                  as p10_metrics section 4 (77 changed decisions there; checked).
  stage_a         output/eval_v2/stage_a/<agent>/<guard>/episodes*.jsonl (one or more files; lines with task_split).
                  tgr_frozen lines as saved_tgr, tgr_tracker lines as online_tracker.
Per conversation file: lines with an error are dropped, lines whose models are not gpt-6-luna / gpt-5-nano are
dropped (counted), and the FIRST good line per (domain, task_split, task, trial) is kept, as the wrapper's progress
(guard/run_online.py JobProgress) and Part 9 count it (later duplicates are counted). Tasks labelled "test" in
splits.json are never used (test-split tasks must be train or val). Arguments come from the agent's message
(tool_calls[0].function.arguments), never from attempts[i].kwargs.

Block messages of a fork point: the saved feedback where the source guard blocked (feedback_*_source "saved"), and
for the other guard the message made by TGR's own feedback code with that guard's values ("rebuilt"). For a
tgr_tracker source, frozen TGR's message needs the judge's own evidence of the values the tracker changed: it is
taken from the run's judge cache (the same judge call), or left empty if not found (noted in `notes`, counted in the
rates file as "frozen block message without judge evidence"; the rebuild check then fails that point). The run's
judge cache is the one its run_*.json names for that guard (_find_cache_dir): Stage A run files list both guards
(plan.paths.guards[guard].structured_cache), the earlier online runs one (plan.paths.structured_cache); run files
of one folder that disagree are refused (RunFileConflict).

CLI (run from predicate_correctness/; the venv Python also runs the τ-bench env checks of fork/rebuild_check.py):
  python -B -m fork.find_points --source saved_tgr,online_tracker --out output/eval_v2/fork_points_saved.jsonl \\
      --rates output/eval_v2/fork_rates_saved.json --md output/eval_v2/checks/rebuild.md
  --source: saved_tgr | online_tracker | stage_a | all, or a comma list. --no-check: write every point found,
  without the rebuild checks. With the checks (default), only passing points are written; dropped ones are listed
  with their reasons in the md file and in the rates file.
Never imports gold code.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

sys.dont_write_bytecode = True

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "fork"

from fork import points_tgr as PT                                              # noqa: E402
from fork.rebuild import action_of, trace_before                               # noqa: E402
from fork.schema import AGENTS, EVAL_V2_DIR, SOURCES, STAGE_A_DIR, ForkPoint    # noqa: E402
from state_tracker import paths                                                # noqa: E402

SAVED_RUNS = {"luna_train_v5": "luna", "nano_train": "nano"}               # partner frozen TGR, our train group
ONLINE_DIR = os.path.join(paths.OUTPUT_DIR, "online")
ONLINE_TAGS = {"p10_luna_train": "luna", "p10_nano_train": "nano", "p10_luna_val": "luna"}
LLMCACHE_DIR = os.path.join(paths.OUTPUT_DIR, "_llmcache")
STAGE_A_GUARDS = ("tgr_frozen", "tgr_tracker")
STYLE = {"tgr": "F", "tgr_frozen": "F", "tgr_tracker": "T"}   # F: frozen TGR saved; T: TGR + tracker saved
SAME_GUARD = {"tgr": ("tgr", "tgr_frozen"), "tgr_frozen": ("tgr_frozen", "tgr"), "tgr_tracker": ("tgr_tracker",)}
CAP = 3                                                                     # run_episode(cap=3)
P8_CHANGES = os.path.join(paths.OUTPUT_DIR, "p8_changes.jsonl")
P10_METRICS = os.path.join(paths.OUTPUT_DIR, "p10_metrics.json")
OUT_SAVED = os.path.join(EVAL_V2_DIR, "fork_points_saved.jsonl")
RATES_SAVED = os.path.join(EVAL_V2_DIR, "fork_rates_saved.json")
CHECK_MD = os.path.join(EVAL_V2_DIR, "checks", "rebuild.md")
DECISION = {True: "allow", False: "block"}
ALLOWED_MODELS = ("gpt-6-luna", "gpt-5-nano")
NO_EFFECT = "differences skipped: cap override, no effect"
MISSING_EVIDENCE = "frozen block message without judge evidence"


def say(msg: str) -> None:
    """Progress line, flushed (long runs write to a log file)."""
    print(msg, flush=True)


# ----------------------------------------------------------------------------------------------- small helpers
def rel(path: str) -> str:
    return os.path.relpath(os.path.abspath(path), paths.PC_DIR)


def load_splits() -> Dict[str, Dict[int, str]]:
    """{domain: {task_index: "train" | "val" | "test"}} from our copy of splits.json (test-split task indices)."""
    with open(paths.SPLITS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return {d: {int(k): v for k, v in data[d]["split"].items()} for d in paths.DOMAINS}


def step_id(run: str, domain: str, task: int, trial: int, exec_step: int, attempt: int) -> str:
    """The step id of state_tracker/load_steps.py (the key of output/p8_changes.jsonl)."""
    return f"{run}/{domain}/task{task}/trial{trial}/step{exec_step}/attempt{attempt}"


def fork_id(source: str, run: str, domain: str, task_split: str, task: int, trial: int, i: int) -> str:
    return f"{source}.{run.replace('/', '_')}.{domain}.{task_split}{task}.trial{trial}.att{i}"


def kind_of(a_allowed: bool, b_allowed: bool) -> Optional[str]:
    """'block removed' (A blocks, B allows), 'block added' (A allows, B blocks), None (same decision)."""
    if a_allowed == b_allowed:
        return None
    return "block removed" if b_allowed else "block added"


def differs(r: dict) -> bool:
    return bool(r.get("comparable")) and r["a"] != r["b"]


def has_effect(r: dict) -> bool:
    """A difference at a 4th try (attempt > CAP: CAP blocks in a row before) has no effect: a block there runs anyway
    (cap override), so both branches run the same action."""
    return int(r.get("attempt") or 1) <= CAP


def first_fork(rows: List[dict]) -> Optional[dict]:
    """The fork: the first comparable row (in attempt order) where the two decisions differ and the difference has an
    effect (not at a cap override)."""
    for r in rows:
        if differs(r) and has_effect(r):
            return r
    return None


def no_effect_before(rows: List[dict], fork_row: Optional[dict]) -> List[dict]:
    """The differences with no effect (cap override) before the fork (all of them when there is no fork)."""
    return [r for r in rows if differs(r) and not has_effect(r) and (fork_row is None or r["i"] < fork_row["i"])]


# ----------------------------------------------------------------------------------------------- run specs
@dataclass
class RunSpec:
    """One set of conversation files with one source guard."""
    source: str                      # one of SOURCES
    run: str                         # e.g. "luna_train_v5", "p10_nano_train", "stage_a/luna/tgr_frozen"
    agent: str                       # "luna" | "nano"
    source_guard: str                # "tgr" | "tgr_frozen" | "tgr_tracker"
    files: List[str]                 # absolute paths, oldest first (a later line replaces an earlier one)
    domain: Optional[str] = None     # None: from each line's "env" (Stage A)
    default_split: str = "test"      # task_split when a line has none (sources 1, 2: τ-bench test split)
    cache_dir: Optional[str] = None  # the run's judge cache (tgr_tracker runs; for frozen TGR's evidence)

    @property
    def style(self) -> str:
        return STYLE[self.source_guard]


class RunFileConflict(RuntimeError):
    """The run_*.json files of a folder do not name one judge cache for the guard (or belong to another guard)."""


def cache_of_run_file(d: dict, guard: str) -> Optional[str]:
    """The judge cache a run_*.json (guard/run_online.py) names for `guard`. Stage A (resolve_stage_a_paths; one
    process runs both guards): plan.paths.guards[guard].structured_cache. The earlier online runs (resolve_paths; one
    guard): plan.paths.structured_cache. Raises RunFileConflict for a run file of another guard."""
    plan = d.get("plan") if isinstance(d, dict) else None
    plan = plan if isinstance(plan, dict) else {}
    p = plan.get("paths") if isinstance(plan.get("paths"), dict) else {}
    gs = p.get("guards")
    if isinstance(gs, dict) and gs:
        if guard not in gs:
            raise RunFileConflict(f"the run file lists the guards {sorted(gs)}, not {guard!r}")
        v = (gs[guard] or {}).get("structured_cache")
    else:
        if plan.get("guard") not in (None, guard):
            raise RunFileConflict(f"the run file is of the guard {plan.get('guard')!r}, not {guard!r}")
        v = p.get("structured_cache")
    return v if isinstance(v, str) and v else None


def _find_cache_dir(folder: str, guard: str, default: Optional[str] = None) -> Optional[str]:
    """The judge cache of the guard `guard` in a run folder: the one its run_*.json files name for that guard (our
    wrapper writes them; cache_of_run_file). Every run file that names one must name the same folder, else
    RunFileConflict. Returns it if it exists (else None); `default` (if it exists) only when no run file names one."""
    named: Dict[str, str] = {}
    for p in sorted(glob.glob(os.path.join(folder, "run_*.json"))):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        try:
            v = cache_of_run_file(d, guard)
        except RunFileConflict as e:
            raise RunFileConflict(f"{rel(p)}: {e}") from None
        if v is not None:
            named[p] = os.path.normpath(os.path.abspath(v))
    found = sorted(set(named.values()))
    if len(found) > 1:
        raise RunFileConflict(f"{rel(folder)}: the run files name {len(found)} judge caches for {guard}: "
                              + "; ".join(f"{rel(k)} -> {v}" for k, v in sorted(named.items())))
    if found:
        return found[0] if os.path.isdir(found[0]) else None
    return default if default and os.path.isdir(default) else None


def specs_for(source: str, stage_a_dir: str = STAGE_A_DIR) -> List[RunSpec]:
    out: List[RunSpec] = []
    if source == "saved_tgr":
        for run, agent in SAVED_RUNS.items():
            for d in paths.DOMAINS:
                out.append(RunSpec(source, run, agent, "tgr", [paths.episodes_path(run, d)], domain=d))
    elif source == "online_tracker":
        for tag, agent in ONLINE_TAGS.items():
            for d in paths.DOMAINS:
                folder = os.path.join(ONLINE_DIR, tag, d, "tgr_tracker")
                out.append(RunSpec(source, tag, agent, "tgr_tracker", [os.path.join(folder, "episodes.jsonl")],
                                   domain=d, cache_dir=_find_cache_dir(
                                       folder, "tgr_tracker", os.path.join(LLMCACHE_DIR, tag, "structured"))))
    elif source == "stage_a":
        if os.path.isdir(stage_a_dir):
            for agent in sorted(os.listdir(stage_a_dir)):
                if agent not in AGENTS:
                    continue
                for g in STAGE_A_GUARDS:
                    folder = os.path.join(stage_a_dir, agent, g)
                    files = sorted(glob.glob(os.path.join(folder, "episodes*.jsonl")))
                    if files:
                        out.append(RunSpec(source, f"stage_a/{agent}/{g}", agent, g, files, domain=None,
                                           default_split="train",
                                           cache_dir=_find_cache_dir(folder, g) if g == "tgr_tracker" else None))
    else:
        raise ValueError(f"unknown source {source!r} (one of {SOURCES})")
    return out


# ----------------------------------------------------------------------------------------------- reading
def load_conversations(spec: RunSpec) -> Tuple[Dict[tuple, Tuple[str, int, dict]], collections.Counter]:
    """(domain, task_split, task, trial) -> (file, raw line number, episode), and line counts.
    Lines with an error, of another domain, or with models other than gpt-6-luna / gpt-5-nano are dropped; the FIRST
    good line per key is kept (as guard/run_online.py JobProgress and Part 9); later duplicates are counted."""
    keep: Dict[tuple, Tuple[str, int, dict]] = {}
    c: collections.Counter = collections.Counter()
    for path in spec.files:
        if not os.path.exists(path):
            c["missing files"] += 1
            continue
        with open(path, encoding="utf-8") as f:
            for line_no, line in enumerate(f):
                if not line.strip():
                    continue
                c["lines"] += 1
                try:
                    ep = json.loads(line)
                except ValueError:
                    c["unreadable lines"] += 1
                    continue
                if ep.get("error") is not None:
                    c["error lines"] += 1
                    continue
                domain = spec.domain or ep.get("env")
                if spec.domain and ep.get("env") not in (None, spec.domain):
                    c["lines of another domain"] += 1
                    continue
                models = ep.get("models")
                if not isinstance(models, dict) or not models or any(m not in ALLOWED_MODELS
                                                                     for m in models.values()):
                    c["skipped: models not gpt-6-luna / gpt-5-nano"] += 1
                    continue
                key = (domain, ep.get("task_split") or spec.default_split, ep["task_index"], ep.get("trial"))
                if key in keep:
                    c["later duplicate lines (first kept)"] += 1
                    continue
                keep[key] = (path, line_no, ep)
    return keep, c


# ----------------------------------------------------------------------------------------------- comparing
def compare_conversation(ep: dict, style: str, off: PT.OfflineGuards, stop_at_first: bool = False) -> List[dict]:
    """One row per attempt with judge values: {i, comparable, a, b, ...} (a, b: allowed by frozen TGR / by
    TGR + tracker). Style F (frozen TGR saved): B computed offline. Style T (TGR + tracker saved): A computed offline
    from tracker.judge_values (evidence is not needed for the decision)."""
    executed, messages, atts = ep["executed"], ep["messages"], ep["attempts"]
    rows: List[dict] = []
    past: List[Any] = []
    for i, a in enumerate(atts):
        g = a.get("guard") or {}
        if g.get("judge"):
            history = executed[:a["executed_prefix_len"]]
            msg = messages[2 + 2 * i]
            row: Dict[str, Any] = {"i": i, "exec_step": a["exec_step"], "attempt": a["attempt"]}
            try:
                if style == "F":
                    rec_b = off.check("B", history, msg, a["exec_step"], past, PT.saved_judge_answer(g))
                    row.update(comparable=True, a=bool(g["action_allowed"]), b=bool(rec_b["action_allowed"]),
                               rec_b=rec_b)
                else:
                    tr = g.get("tracker") or {}
                    jv = tr.get("judge_values")
                    if not tr.get("applied"):
                        row.update(comparable=False, why="no tracker part in the guard record")
                    elif jv is None:
                        row.update(comparable=False, why="judge skipped (frozen TGR's values unknown)")
                    else:
                        judged = {n: {"value": jv.get(n), "evidence": ""} for n in g["judge"]}
                        rec_a = off.check("A", history, msg, a["exec_step"], past, judged)
                        row.update(comparable=True, a=bool(rec_a["action_allowed"]), b=bool(g["action_allowed"]))
            except Exception as e:  # noqa: BLE001 - counted and reported; the check is then not comparable
                row.update(comparable=False, why=f"offline error: {type(e).__name__}: {e}")
            rows.append(row)
            if stop_at_first and differs(row) and has_effect(row):
                break
        if not a["blocked"]:
            past.append(g.get("trace_position"))
    return rows


def fork_point(spec: RunSpec, domain: str, task_split: str, path: str, line_no: int, ep: dict, row: dict,
               rows: List[dict], off: PT.OfflineGuards, p8: Dict[str, dict]) -> ForkPoint:
    """The ForkPoint of a conversation's first differing row."""
    i = row["i"]
    a = ep["attempts"][i]
    g = a["guard"]
    msg = ep["messages"][2 + 2 * i]
    action, arguments = action_of(msg)
    history = ep["executed"][:a["executed_prefix_len"]]
    past = trace_before(ep, i)
    notes: List[str] = []
    evidence_from: Dict[str, str] = {}
    if action != a["action"]:
        raise ValueError(f"attempt {i}: message action {action!r} != attempts[i].action {a['action']!r}")
    if spec.style == "F":
        rec_a, rec_b = g, row["rec_b"]
        values_a = {n: v.get("value") for n, v in g["judge"].items()}
        values_b = {n: v.get("value") for n, v in rec_b["judge"].items()}
        changed = list((rec_b.get("tracker") or {}).get("changed") or [])
        src_a, src_b = "saved", "rebuilt"
    else:
        judged, info = PT.own_judge_answer(off.frozen, g, history, spec.cache_dir, (ep.get("models") or {}).get("guard"))
        rec_a = off.check("A", history, msg, a["exec_step"], past, judged)
        if bool(rec_a["action_allowed"]) != row["a"]:
            raise ValueError(f"attempt {i}: frozen TGR's decision changed with the evidence")
        rec_b = g
        values_a = PT.own_judge_values(g)
        values_b = {n: v.get("value") for n, v in g["judge"].items()}
        changed = list((g.get("tracker") or {}).get("changed") or [])
        src_a, src_b = "rebuilt", "saved"
        evidence_from = dict(info["evidence"])
        missing = sorted(n for n, s in info["evidence"].items() if s == "missing")
        cached = sorted(n for n, s in info["evidence"].items() if s == "cache")
        if missing and not rec_a["action_allowed"]:
            notes.append(f"frozen TGR's block message: the judge's own evidence for {', '.join(missing)} was not "
                         f"found ({info['cache']}); it is left empty")
        if cached and not rec_a["action_allowed"]:
            notes.append(f"frozen TGR's block message: the judge's own evidence for {', '.join(cached)} is from "
                         f"the run's judge cache ({rel(spec.cache_dir)})")
        for p in info["problems"]:
            notes.append("judge evidence: " + p)
    fa, fb = PT.feedback_of(rec_a), PT.feedback_of(rec_b)
    kind = kind_of(row["a"], row["b"])
    cap_fork = a["attempt"] - 1 >= CAP
    if cap_fork:
        notes.append("the fork is at a 4th try: a block runs anyway (cap override), so both branches run the action")
    skipped = no_effect_before(rows, row)
    if skipped:
        notes.append(f"{len(skipped)} earlier difference(s) at a cap override (4th try: both branches run the action, "
                     f"no effect) skipped: attempts {[r['i'] for r in skipped]}")
    not_cmp = [r for r in rows if r["i"] < i and not r.get("comparable")]
    if not_cmp:
        notes.append(f"{len(not_cmp)} earlier check(s) could not be compared: "
                     + "; ".join(sorted({r['why'] for r in not_cmp})))
    trial = ep.get("trial")
    sid = step_id(spec.run, domain, ep["task_index"], trial, a["exec_step"], a["attempt"])
    verdict, review_items = None, []
    if spec.source == "saved_tgr":
        ch = p8.get(sid)
        if ch is not None:
            verdict = (ch.get("b") or {}).get("verdict")
            review_items = list(ch.get("review_items") or [])
            if (ch.get("b") or {}).get("change") != kind:
                notes.append(f"Part 8 version (b) gives {(ch.get('b') or {}).get('change')!r} here")
            if verdict is None:
                notes.append("Part 7 did not review every changed value here: no reviewer verdict")
        else:
            notes.append("not in output/p8_changes.jsonl")
    return ForkPoint(
        fork_id=fork_id(spec.source, spec.run, domain, task_split, ep["task_index"], trial, i),
        source=spec.source, run=spec.run, episodes_path=rel(path), line_no=line_no, agent=spec.agent,
        profile=AGENTS[spec.agent], domain=domain, task_split=task_split, task_index=ep["task_index"], trial=trial,
        attempt_index=i, exec_step=a["exec_step"], attempt=a["attempt"], action=action, arguments=arguments,
        source_guard=spec.source_guard, decision_a=DECISION[row["a"]], decision_b=DECISION[row["b"]],
        feedback_a=fa, feedback_b=fb, kind=kind,
        changed_predicates=[{"name": n, "judge": values_a.get(n), "tracker": values_b.get(n)} for n in changed],
        reviewer_verdict=verdict, notes="; ".join(notes),
        step_id=sid, review_items=review_items, values_a=values_a, values_b=values_b,
        margin_a=rec_a.get("margin"), margin_b=rec_b.get("margin"),
        violated_a=[v["rule_id"] for v in rec_a.get("violated_rules") or []] if not rec_a["action_allowed"] else [],
        violated_b=[v["rule_id"] for v in rec_b.get("violated_rules") or []] if not rec_b["action_allowed"] else [],
        feedback_a_source=src_a if fa is not None else None, feedback_b_source=src_b if fb is not None else None,
        cap_override_at_fork=cap_fork, not_comparable_before=len(not_cmp), no_effect_before=len(skipped),
        changed_attempts=sum(1 for r in rows if r.get("comparable") and r["a"] != r["b"]),
        source_reward=ep.get("reward"), n_attempts=len(ep["attempts"]), judge_evidence_from=evidence_from,
    )


# ----------------------------------------------------------------------------------------------- one run
def load_p8(path: str = P8_CHANGES) -> Dict[str, dict]:
    """Part 8's changed records (version b), by step id."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return {r["step_id"]: r for r in rows if (r.get("b") or {}).get("change")}


def process_spec(spec: RunSpec, off_by_domain: Callable[[str], PT.OfflineGuards], splits: Dict[str, Dict[int, str]],
                 p8: Dict[str, dict], log: Callable[[str], None] = say) -> Tuple[List[ForkPoint], List[dict], List[dict]]:
    """Fork points, rate rows (one per domain) and every changed attempt of one run."""
    t0 = time.time()
    convs, lines = load_conversations(spec)
    by_domain: Dict[str, List[tuple]] = collections.defaultdict(list)
    for key in sorted(convs, key=lambda k: (k[0] or "", k[1], k[2], -1 if k[3] is None else k[3])):
        by_domain[key[0]].append((key, convs[key]))
    points: List[ForkPoint] = []
    rate_rows: List[dict] = []
    changes: List[dict] = []
    for domain in sorted(by_domain):
        c: collections.Counter = collections.Counter()
        off = off_by_domain(domain)
        for (dom, split, task, trial), (path, line_no, ep) in by_domain[domain]:
            if ep.get("profile") != AGENTS[spec.agent]:
                c["skipped: other profile"] += 1
                continue
            if ep.get("guard") not in (None,) + SAME_GUARD[spec.source_guard]:
                c["skipped: other guard"] += 1
                continue
            if split == "test" and splits.get(domain, {}).get(task) not in ("train", "val"):
                c["skipped: test group or no label"] += 1
                continue
            c["conversations"] += 1
            rows = compare_conversation(ep, spec.style, off)
            c["checks compared"] += sum(1 for r in rows if r.get("comparable"))
            c["checks not comparable"] += sum(1 for r in rows if not r.get("comparable"))
            c["offline errors"] += sum(1 for r in rows if str(r.get("why", "")).startswith("offline error"))
            for r in rows:
                k = r.get("comparable") and kind_of(r["a"], r["b"])
                if k:
                    c["changed attempts: " + k] += 1
                    changes.append({"source": spec.source, "run": spec.run, "domain": domain, "task_split": split,
                                    "task": task, "trial": trial, "i": r["i"], "exec_step": r["exec_step"],
                                    "attempt": r["attempt"], "kind": k,
                                    "step_id": step_id(spec.run, domain, task, trial, r["exec_step"], r["attempt"]),
                                    "changed": sorted(((r.get("rec_b") or {}).get("tracker") or {}).get("changed")
                                                      or ((ep["attempts"][r["i"]]["guard"].get("tracker") or {})
                                                          .get("changed") or []))})
            fr = first_fork(rows)
            skipped = no_effect_before(rows, fr)
            c[NO_EFFECT] += len(skipped)
            if fr is None:
                c["conversations with only no-effect differences"] += bool(skipped)
                continue
            fp = fork_point(spec, domain, split, path, line_no, ep, fr, rows, off, p8)
            points.append(fp)
            c["with fork"] += 1
            c[MISSING_EVIDENCE] += (fp.feedback_a is not None and fp.feedback_a_source == "rebuilt"
                                    and "missing" in fp.judge_evidence_from.values())
            c[fp.kind] += 1
            c["fork at a later try (attempt > 1)"] += fp.attempt > 1
            c["fork at a cap override try"] += fp.cap_override_at_fork
            c["not comparable before the fork"] += fp.not_comparable_before > 0
        n = c["conversations"]
        for k in (NO_EFFECT, "conversations with only no-effect differences", MISSING_EVIDENCE):
            c[k] += 0                                               # always in the rate row
        rate_rows.append({
            "source": spec.source, "run": spec.run, "agent": spec.agent, "profile": AGENTS[spec.agent],
            "domain": domain, "source_guard": spec.source_guard, "files": [rel(p) for p in spec.files],
            "judge_cache": rel(spec.cache_dir) if spec.cache_dir else None,
            **{k: v for k, v in lines.items()}, **dict(c),
            "fork_rate": round(c["with fork"] / n, 4) if n else None,
            "fork_rate_block_removed": round(c["block removed"] / n, 4) if n else None,
            "fork_rate_block_added": round(c["block added"] / n, 4) if n else None,
        })
        log(f"[find_points] {spec.source} {spec.run} {domain}: {n} conversations, {c['with fork']} with a fork "
            f"(removed {c['block removed']}, added {c['block added']}); changed attempts "
            f"{c['changed attempts: block removed']} / {c['changed attempts: block added']}; not comparable "
            f"{c['checks not comparable']}; {time.time() - t0:.0f} s")
    return points, rate_rows, changes


# ----------------------------------------------------------------------------------------------- cross-checks
def cross_check_p8(changes: List[dict], p8: Dict[str, dict], processed: Optional[set] = None) -> dict:
    """Our changed attempts of the partner's runs against output/p8_changes.jsonl (version b), on the (run, domain)
    pairs processed."""
    if processed is not None:
        p8 = {s: r for s, r in p8.items() if (r["run"], r["domain"]) in processed}
    ours = {c["step_id"]: c for c in changes if c["source"] == "saved_tgr"}
    only_ours = sorted(set(ours) - set(p8))
    only_p8 = sorted(set(p8) - set(ours))
    common = sorted(set(ours) & set(p8))
    kind_diff = [s for s in common if ours[s]["kind"] != p8[s]["b"]["change"]]
    values_diff = [s for s in common if ours[s]["changed"] != sorted(p8[s]["b"].get("changed_values") or [])]
    first = {}
    for s, r in p8.items():
        k = (r["run"], r["domain"], r["task"], r["trial"])
        if k not in first or (r["exec_step"], r["attempt"]) < (first[k]["exec_step"], first[k]["attempt"]):
            first[k] = r
    return {"ours": len(ours), "p8": len(p8), "common": len(common), "only_ours": only_ours, "only_p8": only_p8,
            "kind_differs": kind_diff, "changed_values_differ": values_diff,
            "p8_conversations": len(first),
            "p8_first_changes": {k: v for k, v in collections.Counter(r["b"]["change"] for r in first.values()).items()},
            "same": not (only_ours or only_p8 or kind_diff or values_diff)}


def cross_check_p10(changes: List[dict], path: str = P10_METRICS, processed: Optional[set] = None) -> dict:
    """Our changed attempts of our p10 runs against p10_metrics section 4 (output/p10_metrics.json counts)."""
    if not os.path.exists(path):
        return {"same": None, "why": "output/p10_metrics.json not found"}
    with open(path, encoding="utf-8") as f:
        m = json.load(f)
    rows, same = [], True
    for exp, r in m["experiments"].items():
        tag = m["inputs"][exp]["our_tag"]
        for env, t in r["tracker"].items():
            if processed is not None and (tag, env) not in processed:
                continue
            want = {k: t["counts"].get(k, 0) for k in ("block removed", "block added")}
            got = {k: sum(1 for c in changes if c["source"] == "online_tracker" and c["run"] == tag
                          and c["domain"] == env and c["kind"] == k) for k in ("block removed", "block added")}
            rows.append({"experiment": exp, "tag": tag, "domain": env, "p10_metrics": want, "ours": got})
            same = same and want == got
    total = {k: sum(r["ours"][k] for r in rows) for k in ("block removed", "block added")}
    return {"rows": rows, "ours_total": total, "same": same}


# ----------------------------------------------------------------------------------------------- totals
def totals(rate_rows: List[dict]) -> dict:
    keys = ("conversations", "with fork", "block removed", "block added", "changed attempts: block removed",
            "changed attempts: block added", "checks compared", "checks not comparable", NO_EFFECT,
            "conversations with only no-effect differences", MISSING_EVIDENCE)

    def add(groups: Dict[str, dict], name: str, r: dict) -> None:
        g = groups.setdefault(name, collections.Counter())
        for k in keys:
            g[k] += r.get(k, 0)

    out: Dict[str, Dict[str, dict]] = {"by_source_agent": {}, "by_source": {}, "by_agent": {}, "by_agent_domain": {},
                                       "all": {}}
    for r in rate_rows:
        add(out["by_source_agent"], f"{r['source']} / {r['agent']}", r)
        add(out["by_source"], r["source"], r)
        add(out["by_agent"], r["agent"], r)
        add(out["by_agent_domain"], f"{r['agent']} / {r['domain']}", r)
        add(out["all"], "all", r)
    for groups in out.values():
        for name, g in groups.items():
            n = g["conversations"]
            groups[name] = dict(g, fork_rate=round(g["with fork"] / n, 4) if n else None)
    return out


# ----------------------------------------------------------------------------------------------- main
def parse_sources(text: str) -> List[str]:
    if text == "all":
        return list(SOURCES)
    out = [s.strip() for s in text.split(",") if s.strip()]
    bad = [s for s in out if s not in SOURCES]
    if bad or not out:
        raise SystemExit(f"--source: unknown {bad}; use one of {SOURCES}, 'all' or a comma list")
    return out


def find(sources: Iterable[str], stage_a_dir: str = STAGE_A_DIR, log: Callable[[str], None] = say,
         runs: Optional[Iterable[str]] = None, domains: Optional[Iterable[str]] = None) -> dict:
    """Every fork point of the sources, the rate rows, every changed attempt and the cross-checks."""
    cache: Dict[str, PT.OfflineGuards] = {}

    def off_by_domain(d: str) -> PT.OfflineGuards:
        if d not in cache:
            cache[d] = PT.OfflineGuards(d)
        return cache[d]

    splits, p8 = load_splits(), load_p8()
    points: List[ForkPoint] = []
    rate_rows: List[dict] = []
    changes: List[dict] = []
    processed: set = set()
    for s in sources:
        for spec in specs_for(s, stage_a_dir):
            if runs and spec.run not in set(runs):
                continue
            if domains and spec.domain is not None and spec.domain not in set(domains):
                continue
            p, r, ch = process_spec(spec, off_by_domain, splits, p8, log)
            processed |= {(x["run"], x["domain"]) for x in r}
            points += p
            rate_rows += r
            changes += ch
    ids = collections.Counter(p.fork_id for p in points)
    dup = [k for k, n in ids.items() if n > 1]
    if dup:
        raise RuntimeError(f"fork ids are not unique: {dup[:5]}")
    cross = {}
    if "saved_tgr" in sources:
        cross["p8_changes_version_b"] = cross_check_p8(changes, p8, processed)
    if "online_tracker" in sources:
        cross["p10_metrics_section_4"] = cross_check_p10(changes, processed=processed)
    return {"points": points, "rate_rows": rate_rows, "changes": changes, "cross_checks": cross,
            "offline_guards": cache}


def write_points(points: List[ForkPoint], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for p in points:
            f.write(json.dumps(p.to_dict(), ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def read_points(path: str) -> List[ForkPoint]:
    with open(path, encoding="utf-8") as f:
        return [ForkPoint.from_dict(json.loads(line)) for line in f if line.strip()]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--source", default="saved_tgr,online_tracker")
    ap.add_argument("--out", default=OUT_SAVED, help="fork points (JSONL, one ForkPoint per line)")
    ap.add_argument("--rates", default=None, help="fork rates (JSON); default: next to --out (fork_rates_*.json)")
    ap.add_argument("--md", default=None, help="rebuild check report (markdown); default checks/rebuild.md for the "
                                               "saved sources, checks/rebuild_<name>.md otherwise")
    ap.add_argument("--stage-a-dir", default=STAGE_A_DIR)
    ap.add_argument("--no-check", action="store_true", help="write every point found, without the rebuild checks")
    ap.add_argument("--runs", default=None, help="only these runs (comma list), e.g. p10_luna_val")
    ap.add_argument("--domains", default=None, help="only these domains (comma list)")
    a = ap.parse_args(argv)
    sources = parse_sources(a.source)
    from fork import rebuild_check as RC                    # the safety setup (no network, no LLM, writes) first
    RC.safety_setup()
    t0 = time.time()
    res = find(sources, a.stage_a_dir, runs=a.runs.split(",") if a.runs else None,
               domains=a.domains.split(",") if a.domains else None)
    points = res["points"]
    name = os.path.basename(a.out).replace("fork_points", "").replace(".jsonl", "").strip("_") or "all"
    rates_path = a.rates or os.path.join(os.path.dirname(os.path.abspath(a.out)), f"fork_rates_{name}.json")
    md_path = a.md or (CHECK_MD if name == "saved" else os.path.join(EVAL_V2_DIR, "checks", f"rebuild_{name}.md"))
    checked = None
    kept = points
    if not a.no_check:
        checked = RC.check_points(points, res["offline_guards"], log=say)
        ok_ids = {r["fork_id"] for r in checked["results"] if r["ok"]}
        kept = [p for p in points if p.fork_id in ok_ids]
        RC.write_md(md_path, points, checked, res["rate_rows"], res["cross_checks"], sources)
        print("wrote", md_path)
    write_points(kept, a.out)
    kept_ids = {p.fork_id for p in kept}
    for r in res["rate_rows"]:
        r["with fork, kept after the rebuild checks"] = sum(
            1 for p in kept if (p.source, p.run, p.domain) == (r["source"], r["run"], r["domain"]))
    rates = {"written_by": "fork/find_points.py", "date": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
             "sources": sources, "points_file": rel(a.out), "points_found": len(points), "points_kept": len(kept),
             "rows": res["rate_rows"], "totals": totals(res["rate_rows"]), "cross_checks": res["cross_checks"],
             "rebuild_check": None if checked is None else {
                 "passed": len(kept_ids), "checked": len(checked["results"]), "venv_checks": checked["venv"],
                 "dropped": [{"fork_id": r["fork_id"], "reasons": r["reasons"]} for r in checked["results"]
                             if not r["ok"]]}}
    with open(rates_path, "w", encoding="utf-8") as f:
        json.dump(rates, f, indent=1, ensure_ascii=False, default=str)
    print(f"[find_points] {len(points)} fork points found, {len(kept)} written to {rel(a.out)}; rates "
          f"{rel(rates_path)}; {time.time() - t0:.0f} s")
    for k, v in res["cross_checks"].items():
        print(f"[find_points] cross-check {k}: same = {v.get('same')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
