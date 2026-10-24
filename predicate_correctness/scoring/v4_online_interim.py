"""Tracker v4: the halfway check and the stop rules of a live run (docs/planning/tracker_v4/overview.md section 9),
as v3's scoring/v3_online_interim.py, for the v4 arms and steps. $0, no LLM call, no network. Writes nothing, except
<run>/halfway.json once the halfway mark is reached (see below; --no-halfway-file: never) and the STOP file of a run
folder when asked (--write-stop) and a stop fires.

Stops (lenient on purpose: they catch a broken run, not a normal one):
  harm      the halfway check, decided ONCE (preregistration_v4.md section 11: "at the first moment ... checked once").
            The live lines are put in line-time order (the time of the unit's "end" line in <run>/ledger/units_*.jsonl,
            which the runner writes right after the episode line; ties: ledger file, then line position; a line
            without a ledger "end" comes after every timed line, by its position in its file, then the file path) and
            replayed (latest line per unit, as the metrics: a higher unit_attempt wins). P10 arm plan (user decision):
            a GROUP is the two live v4 arms (direct_facts_v4, tgr_tracker_v4) of one (task, try), complete when both
            have a latest line without error (groups listed in dropped_groups*.jsonl of the live or baseline folder
            left out). The snapshot is the first HALF[step] complete groups in the order they became complete: B2v4
            149, B3v4 32. On those keys: tgr_tracker_v4 (live) - tgr_frozen, task success paired by task (tries
            averaged), the main task set; frozen TGR from v3's baseline run named in run.json (read by code only, and
            only once the mark is reached; on a B3v4 fill task the live frozen line as replayed up to that moment); a
            key whose frozen line is missing or an error line is left out of the pair (counted). Fire if <= HARM
            (-0.15; a tie fires). So a late look gives the answer an on-time look
            would have given. The decision is saved to <run>/halfway.json (O_EXCL: never replaced); every later call
            reads it and never computes again (a fire stays a fire). Before the mark: "not yet", nothing saved.
            Other steps (B1v4, Hv4): no halfway rule (H's claim is harm). DEV20v4 is dropped (user decision).
  state     the 3rd v4 state error: guard checks of the v4 arm with a state error or a fact error (the tracker record
            rec["v4"], else rec["v3"]: state_errors / fact_errors), every v4 line counted (error lines, re-runs and
            dropped groups included), over all shards of the step.
  cost      an arm's mean cost per conversation, after COST_MIN_LINES (50) of its lines, over its threshold (3 x its
            high estimate; preregistration_v4.md section 11: COST_STOP for B2v4 / Hv4 / B1v4, COST_STOP_B3 for
            B3v4; an unknown arm takes the "unknown" value), or one conversation over $0.25.
  errors    per arm file (preregistration_v4.md section 11: "per arm file, per step"; the runner writes one file per
            arm and shard, <run>/<arm>/episodes_shard<i>of<n>.jsonl): in one file, 10 or more error lines that are
            also over 5 % of its lines, or 5 error lines in a row (file order). One file is enough to fire.
The rules are those of preregistration_v4.md section 11 (binding).
One step per check (mixed steps are refused). Run folders under output/eval_v3/ and saved val runs are refused by path
(scoring/v4_online_metrics.py check_path). A live shard's cut-off last line (no newline at the end, not JSON yet) is
skipped; a bad line anywhere else is an error.

--write-stop: when any stop fires, write the file STOP in every given run folder that has none yet (the runner's soft
stop only checks that it exists: no new (task, try) group starts, open groups finish). An existing STOP file is never
changed. The STOP file holds one JSON line: the rules that fired, the time, and this script's name.
--no-halfway-file: compute the halfway snapshot but do not save halfway.json (a saved one is still read and used).

Run from predicate_correctness/:
  /home/azureuser/miniconda3/bin/python3 -B -m scoring.v4_online_interim --run-dir output/eval_v4/B2v4/<run_id> \\
      [--write-stop] > output/logs/v4_B2v4_interim.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, List, Optional, Sequence, Tuple

sys.dont_write_bytecode = True

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "scoring"

from scoring import v4_online_metrics as M                       # noqa: E402

HALF = {M.STEP_B2: 149, M.STEP_B3: 32}                          # complete live GROUPS (P10; 2 live arms each)
GROUP_ARMS = M.LIVE_ARMS
HARM = -0.15
EPS = 1e-9                                                       # float sums: a tie at -0.15 fires
STATE_ERRORS_STOP = 3
COST_STOP = {"none": 0.022, "direct": 0.044, "direct_facts_v4": 0.043, "tgr_frozen": 0.039, "tgr_tracker_v4": 0.030,
             "unknown": 0.044}                                   # B2v4, Hv4 (and B1v4); tgr_tracker_v3: "unknown"
COST_STOP_B3 = {"none": 0.045, "direct": 0.086, "direct_facts_v4": 0.085, "tgr_frozen": 0.083,
                "tgr_tracker_v4": 0.063, "unknown": 0.086}       # B3v4
COST_MIN_LINES = 50
CONV_COST_STOP = 0.25
ERR_MIN, ERR_SHARE, ERR_STREAK = 10, 0.05, 5
STOP_FILENAME = "STOP"
HALFWAY_FILENAME = "halfway.json"
LEDGER_DIRNAME = "ledger"                                        # guard/soft_stop_v4.py LEDGER_DIRNAME (not imported)


# ----------------------------------------------------------------------------------------------- reading
def _read_tolerant(path: str) -> List[dict]:
    """The lines of a JSONL file; a cut-off last line (the file does not end with a newline and the last line is not
    JSON: a shard is writing it now) is skipped. A bad line anywhere else raises."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    parts = text.split("\n")
    cut = not text.endswith("\n")
    out = []
    for i, line in enumerate(parts):
        s = line.strip()
        if not s:
            continue
        try:
            out.append(json.loads(s))
        except json.JSONDecodeError:
            if cut and i == len(parts) - 1:
                continue
            raise
    return out


def read_lines(path: str) -> List[dict]:
    """M.read_jsonl (which skips a cut-off last line once the metrics file does so); if it still fails on one, the
    same rule here."""
    try:
        return M.read_jsonl(path)
    except json.JSONDecodeError:
        return _read_tolerant(path)


def raw_lines(run_dirs: Sequence[str]) -> Dict[str, List[dict]]:
    """Every line of every episodes*.jsonl (no latest-line rule: error lines and re-runs all count), per file."""
    out = {}
    for d in run_dirs:
        M.check_path(d)
        for p in M.episode_files(d):
            M.check_path(p)
            out[p] = read_lines(p)
    return out


def dropped_groups(run_dirs: Sequence[str]) -> set:
    out = set()
    for d in run_dirs:
        paths = []
        for dirpath, dirnames, filenames in os.walk(d):
            dirnames[:] = sorted(x for x in dirnames if x != "__pycache__")
            paths += [os.path.join(dirpath, f) for f in sorted(filenames)
                      if f.startswith("dropped_groups") and f.endswith(".jsonl")]
        for p in paths:
            for r in read_lines(p):
                out.add((r.get("env") or r.get("domain"), int(r["task_index"]), int(r["trial"])))
    return out


def ledger_end_times(run_dirs: Sequence[str]) -> Dict[str, tuple]:
    """conversation_id -> (time, ledger file, line position) of its first "end" ledger line."""
    out: Dict[str, tuple] = {}
    for d in run_dirs:
        ld = os.path.join(d, LEDGER_DIRNAME)
        if not os.path.isdir(ld):
            continue
        for name in sorted(os.listdir(ld)):
            if not (name.startswith("units") and name.endswith(".jsonl")):
                continue
            p = os.path.join(ld, name)
            for i, r in enumerate(read_lines(p)):
                if r.get("event") == "end" and r.get("conversation_id") and r.get("time"):
                    out.setdefault(str(r["conversation_id"]), (str(r["time"]), p, i))
    return out


# ----------------------------------------------------------------------------------------------- halfway
def timed_lines(run_dirs: Sequence[str], lines: Dict[str, List[dict]]) -> Tuple[List[Tuple[tuple, dict]], dict]:
    """Every episode line as a conversation (M.make_conv), with its line-time key, sorted by it."""
    splits = M.load_splits()
    ends = ledger_end_times(run_dirs)
    items, timed = [], 0
    for p, recs in lines.items():
        for i, rec in enumerate(recs):
            c = M.make_conv(rec, splits, None, p)
            e = ends.get(str(rec.get("conversation_id"))) if rec.get("conversation_id") else None
            if e is not None:
                key = (0, e[0], e[1], e[2], "", 0)
                timed += 1
            else:
                key = (1, "", "", i, p, 0)
            items.append((key, c))
    items.sort(key=lambda x: x[0])
    return items, {"lines": len(items), "timed_by_ledger": timed, "untimed": len(items) - timed}


def baseline_frozen(run_dirs: Sequence[str], step: str) -> Tuple[Dict[tuple, dict], Optional[dict]]:
    """(key -> the latest tgr_frozen line of v3's baseline run, the baseline spec). Code only; frozen arm only."""
    spec = M.baseline_spec(run_dirs, step)
    if spec is None:
        return {}, None
    base = M.latest(M.load_baseline_raw(spec, step, only_arms=(M.FROZEN,)))
    return {(c["domain"], c["task"], c["trial"]): c for c in base}, spec


def halfway_snapshot(run_dirs: Sequence[str], timed: Tuple[List[Tuple[tuple, dict]], dict], step: str,
                     half: int) -> dict:
    """Replay the live lines (timed_lines) in line-time order; stop at the first moment `half` live groups (both
    GROUP_ARMS without error) are complete. Returns the decision on exactly those groups (module docstring)."""
    items, order = timed
    spec = M.baseline_spec(run_dirs, step)
    gone = dropped_groups(list(run_dirs) + ([spec["run_dir"]] if spec else []))
    fill = [tuple(x) for x in (spec or {}).get("fill_tasks") or ()]
    arms = GROUP_ARMS
    latest: Dict[tuple, dict] = {}
    done: Dict[tuple, int] = {}
    groups: List[tuple] = []
    last_key = None
    snap: Dict[tuple, dict] = {}                     # a group's v4 line as it was when the group became complete
    for key, c in items:
        g = (c["domain"], c["task"], c["trial"])
        if g in gone or (g in done and c["arm"] in arms):
            continue                                 # a done group's live v4 arms keep their completion values
        k = g + (c["arm"],)
        old = latest.get(k)
        if old is not None and int(old["rec"].get("unit_attempt") or 0) > int(c["rec"].get("unit_attempt") or 0):
            continue
        latest[k] = c
        if g not in done and all(g + (a,) in latest and latest[g + (a,)]["error"] is None for a in arms):
            done[g] = len(groups)
            groups.append(g)
            snap[g] = {a: latest[g + (a,)] for a in arms}
            if len(groups) >= half:
                last_key = key
                break
    n = len(groups) * len(arms)
    out = {"step": step, "half": half, "half_unit": "complete live groups (direct_facts_v4 + tgr_tracker_v4)",
           "threshold": HARM, "conversations_in_complete_groups": n, "complete_groups": len(groups), "order": order}
    if len(groups) < half:
        out.update({"reached": False, "fire": False})
        return out
    base, _spec = baseline_frozen(run_dirs, step)          # read only now: the mark is reached
    comp, left_out = [], []
    for g in groups:
        f = latest.get(g + (M.FROZEN,)) if M.live_for(step, M.FROZEN, g[0], g[1], fill) else base.get(g)
        if f is None or f["error"] is not None:
            left_out.append(list(g))
            continue
        comp += [snap[g][M.V4], f]
    ts = M.STEP_CONF[step]["main_set"]
    d = M._paired(M.per_task(comp, M.V4, ts), M.per_task(comp, M.FROZEN, ts))
    diff = sum(d.values()) / len(d) if d else None
    last = snap[groups[-1]][arms[-1]]
    out.update({"reached": True, "diff": diff, "n_tasks": len(d), "frozen_from": "v3 baseline" if spec else "live",
                "baseline_run_id": (spec or {}).get("run_id"), "groups_without_frozen_pair": left_out,
                "fire": diff is not None and diff <= HARM + EPS,
                "groups": [list(g) for g in groups],
                "last_line": {"time": last_key[1] if last_key and last_key[0] == 0 else None,
                              "file": last["source"], "conversation_id": last["rec"].get("conversation_id")}})
    return out


def read_halfway(run_dirs: Sequence[str]) -> Optional[dict]:
    """The saved halfway decision (the first run folder that has a readable halfway.json), else None."""
    for d in run_dirs:
        p = os.path.join(d, HALFWAY_FILENAME)
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue                              # being written by another call this instant: not used
        doc = dict(doc)
        doc["source"] = "saved"
        doc["file"] = p
        return doc
    return None


def save_halfway(run_dirs: Sequence[str], doc: dict) -> List[str]:
    """Write halfway.json (O_EXCL: an existing file is never replaced) in every run folder without one."""
    keep = {k: v for k, v in doc.items() if k not in ("source", "file")}
    keep.update({"saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "by": "scoring/v4_online_interim.py", "run_dirs": list(run_dirs)})
    text = json.dumps(M._jsonable(keep), indent=1, sort_keys=True) + "\n"
    written = []
    for d in run_dirs:
        M.check_path(d)
        p = os.path.join(d, HALFWAY_FILENAME)
        try:
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        written.append(p)
    return written


def harm_check(run_dirs: Sequence[str], lines: Dict[str, List[dict]], step: str, save: bool = True,
               timed: Optional[Tuple[List[Tuple[tuple, dict]], dict]] = None) -> dict:
    """The halfway decision: the saved one if any (never computed again), else the snapshot; saved once reached."""
    half = HALF.get(step)
    if half is None:
        return {"step": step, "half": None, "threshold": HARM, "reached": None, "fire": False,
                "note": f"no halfway rule for {step}"}
    saved = read_halfway(run_dirs)
    if saved is not None:
        if saved.get("step") != step:
            raise M.StepMixed(f"{saved['file']} is the halfway decision of {saved.get('step')}, not {step}")
        return saved
    out = halfway_snapshot(run_dirs, timed if timed is not None else timed_lines(run_dirs, lines), step, half)
    out["source"] = "computed now"
    if out["reached"] and save:
        written = save_halfway(run_dirs, out)
        if not written:                           # another call saved it first: its decision wins
            again = read_halfway(run_dirs)
            if again is not None:
                return again
        out["saved_to"] = written
    return out


def state_check(lines: Dict[str, List[dict]]) -> dict:
    st = fe = either = 0
    for recs in lines.values():
        for r in recs:
            if M.arm_of(r) != M.V4:
                continue
            for a in r.get("attempts") or []:
                t = M.tracker_info(a.get("guard"))
                s, f = bool(t.get("state_errors")), bool(t.get("fact_errors"))
                st += s
                fe += f
                either += 1 if (s or f) else 0
    return {"checks_with_state_error": st, "checks_with_fact_error": fe, "count": either,
            "fire": either >= STATE_ERRORS_STOP, "counted_on": "every v4 line"}


def cost_check(lines: Dict[str, List[dict]], step: Optional[str] = None) -> dict:
    per_arm: Dict[str, List[float]] = {}
    over = []
    for p, recs in lines.items():
        for r in recs:
            c = M.line_cost(r)
            per_arm.setdefault(M.arm_of(r), []).append(c)
            if c > CONV_COST_STOP:
                over.append({"file": p, "task": r.get("task_index"), "trial": r.get("trial"), "cost": c})
    arms = {}
    fire = bool(over)
    for a, cs in sorted(per_arm.items()):
        mean = sum(cs) / len(cs)
        table = COST_STOP_B3 if step == M.STEP_B3 else COST_STOP
        lim = table.get(a, table["unknown"])
        f = len(cs) >= COST_MIN_LINES and mean > lim
        fire = fire or f
        arms[a] = {"lines": len(cs), "mean": mean, "limit": lim, "fire": f}
    return {"arms": arms, "conversations_over_0.25": over, "fire": fire}


def error_check(lines: Dict[str, List[dict]]) -> dict:
    """Per arm file (preregistration_v4.md section 11): each file is judged on its own lines; one file fires it."""
    files = {}
    total = errs = streak_all = 0
    for p, recs in sorted(lines.items()):
        n = e = streak = streak_max = 0
        for r in recs:
            n += 1
            if r.get("error") is not None:
                e += 1
                streak += 1
                streak_max = max(streak_max, streak)
            else:
                streak = 0
        share = e / n if n else 0.0
        fire = (e >= ERR_MIN and share > ERR_SHARE) or streak_max >= ERR_STREAK
        files[p] = {"arm": M.arm_of(recs[0]) if recs else None, "lines": n, "error_lines": e, "share": share,
                    "longest_streak": streak_max, "fire": fire}
        total, errs, streak_all = total + n, errs + e, max(streak_all, streak_max)
    return {"per": "arm file", "files": files, "fired_files": [p for p, f in files.items() if f["fire"]],
            "lines": total, "error_lines": errs, "share": errs / total if total else 0.0,
            "longest_streak": streak_all, "fire": any(f["fire"] for f in files.values())}


def interim(run_dirs: Sequence[str], save_halfway: bool = True) -> dict:
    lines = raw_lines(run_dirs)
    steps = sorted({str(r.get("step")) for recs in lines.values() for r in recs})
    if len(steps) > 1:
        raise M.StepMixed(f"one step per interim check; lines of {steps}")
    step = steps[0] if steps else None
    timed = timed_lines(run_dirs, lines)          # every line checked by M.make_conv (step, task group, split)
    if step:                                      # P10 plan: a live line of an arm not live for its key is refused
        spec = M.baseline_spec(run_dirs, step)
        M.check_live_plan(step, [c for _k, c in timed[0]], [tuple(x) for x in (spec or {}).get("fill_tasks") or ()])
    out = {"run_dirs": list(run_dirs), "step": step,
           "harm": (harm_check(run_dirs, lines, step, save=save_halfway, timed=timed) if step else
                    {"fire": False, "reached": False, "note": "no lines yet"}),
           "state": state_check(lines), "cost": cost_check(lines, step), "errors": error_check(lines)}
    out["fired"] = [k for k in ("harm", "state", "cost", "errors") if out[k]["fire"]]
    out["any_stop"] = bool(out["fired"])
    return out


def write_stop(run_dirs: Sequence[str], rep: dict) -> List[str]:
    """The STOP file in every run folder without one (never changed when it exists). Returns the files written."""
    written = []
    line = json.dumps({"stop": rep["fired"], "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "by": "scoring/v4_online_interim.py --write-stop",
                       "harm_diff": rep["harm"].get("diff")}, sort_keys=True)
    for d in run_dirs:
        M.check_path(d)
        p = os.path.join(d, STOP_FILENAME)
        if os.path.exists(p):
            continue
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(line + "\n")
        written.append(p)
    return written


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run-dir", action="append", required=True)
    ap.add_argument("--write-stop", action="store_true", help="write the STOP file when a stop fires")
    ap.add_argument("--no-halfway-file", action="store_true",
                    help="do not save halfway.json (a saved one is still read and used)")
    a = ap.parse_args(argv)
    rep = interim(a.run_dir, save_halfway=not a.no_halfway_file)
    if rep["any_stop"] and a.write_stop:
        rep["stop_files_written"] = write_stop(a.run_dir, rep)
    print(json.dumps(M._jsonable(rep), indent=1))
    print(f"[v4-interim] {rep['step']}: harm {rep['harm']['fire']} state {rep['state']['fire']} cost "
          f"{rep['cost']['fire']} errors {rep['errors']['fire']} -> {'STOP' if rep['any_stop'] else 'go on'}"
          + (f"; STOP files written: {len(rep.get('stop_files_written') or [])}" if a.write_stop else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
