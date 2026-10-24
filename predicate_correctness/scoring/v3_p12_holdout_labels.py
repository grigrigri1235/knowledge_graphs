"""Tracker v3, part 12 step 4 (scoring.v3_p12_holdout_labels): τ-bench's tool labels (p3) for the HOLD-OUT write
attempts. $0: no LLM call, no network.

The hold-out (preregistration.md, "Data split"): ours.p10_luna_val, partner.luna_val and the Stage B tries forked from
a val conversation (fork id with p10_luna_val or luna_val). It is opened ONCE, by the main chat, in p12 step 4. So this
script is LOCKED: it runs only with both flags
    --holdout --i-am-the-main-chat-holdout-look
and refuses (exit 2, before any data file is read) without them. It never writes the development files
(output/eval_v3/tool_labels.jsonl, p3_tool_labels.md): it writes
    output/eval_v3/tool_labels_holdout.jsonl     one line per labelled hold-out write attempt (p3's line format)
    output/eval_v3/p3_tool_labels_holdout.md     a short report
and refuses to overwrite them (the hold-out is labelled once; move the old files away by hand to run it again).

The labels come from scoring/v3_p3_labels.py's own code, unchanged (label_conversation: the state before the attempt
rebuilt from executed[:executed_prefix_len], the call read from the agent's message, never from attempts[i].kwargs,
τ-bench's tool code on a scratch copy). v3_p3_labels.py is imported, not edited, so its sha256 in p3's report stays
valid and its development refusals stay as they are. The hold-out episode sets and Stage B forks are the ones of
v3_p3_labels.episode_sets(holdout=True) / is_holdout_fork(); a task that is not "val" in splits.json is skipped and
counted (the partner's test group is never used).

Run from predicate_correctness/ (standard library only):
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 /home/azureuser/miniconda3/bin/python3 -B -m scoring.v3_p12_holdout_labels \\
        --holdout --i-am-the-main-chat-holdout-look --workers 2 > output/logs/v3_p12_03_labels_holdout.log 2>&1
Never imports gold code.
"""
from __future__ import annotations

import argparse
import collections
import json
import multiprocessing
import os
import sys
import time
from typing import Any, Callable, Dict, Iterator, List, Optional

sys.dont_write_bytecode = True

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scoring import v3_p3_labels as P3  # noqa: E402
from state_tracker import paths  # noqa: E402

LOOK_FLAG = "--i-am-the-main-chat-holdout-look"
HOLDOUT_LABELS = os.path.join(P3.EVAL_V3, "tool_labels_holdout.jsonl")
HOLDOUT_REPORT = os.path.join(P3.EVAL_V3, "p3_tool_labels_holdout.md")
DEV_FILES = (P3.LABELS, P3.REPORT)
HOLDOUT_DATASETS = ("ours.p10_luna_val", "partner.luna_val")


class HoldoutLocked(SystemExit):
    """The hold-out lock refused the run (exit code 2)."""

    def __init__(self, msg: str):
        super().__init__(2)
        self.msg = msg


def check_lock(holdout: bool, look: bool) -> None:
    """Both flags, or HoldoutLocked (nothing is read before this check)."""
    if not (holdout and look):
        raise HoldoutLocked(f"the hold-out is locked: it is opened once, by the main chat, with --holdout {LOOK_FLAG}")


def check_outputs(out: str, report: str, replace_ok: bool = False) -> None:
    """Never a development file; never an existing hold-out file (labelled once)."""
    for p in (out, report):
        ap = os.path.abspath(p)
        if ap in {os.path.abspath(x) for x in DEV_FILES}:
            raise HoldoutLocked(f"{P3.rel(ap)} is a development file: hold-out labels never go there")
        if os.path.exists(ap) and not replace_ok:
            raise HoldoutLocked(f"{P3.rel(ap)} exists: the hold-out is labelled once (move it away by hand first)")
    if os.path.abspath(out) == os.path.abspath(report):
        raise HoldoutLocked("--out and --report are the same file")


def holdout_jobs(splits: Dict[str, Dict[int, str]], counts: Dict[str, collections.Counter]) -> Iterator[tuple]:
    """The hold-out conversations as v3_p3_labels jobs: (dataset, conv_id, domain, episode, stage_b info or None).
    The ONLY function here that reads hold-out files."""
    for spec in P3.episode_sets(holdout=True):
        lc = counts.setdefault(spec["name"], collections.Counter())
        for dom, ep in P3.episode_lines(spec["files"], spec["domain"], spec["default_split"], spec["profile"],
                                        spec["guard"], lc):
            grp = splits.get(dom, {}).get(int(ep["task_index"]))
            if grp != "val":
                lc[f"skipped: task group {grp!r} (not val)"] += 1
                continue
            lc["task group: val"] += 1
            yield (spec["name"], f"{dom}/{ep['task_index']}/{ep.get('trial')}", dom, ep, None)
    lc = counts.setdefault("stage_b", collections.Counter())
    for path, fork_id, branch, tr in P3.stage_b_files():
        if not P3.is_holdout_fork(fork_id):
            continue
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        lc["try files"] += 1
        if d.get("error") is not None:
            lc["tries with an error (dropped)"] += 1
            continue
        if (d.get("fork_id"), d.get("branch"), str(d.get("try"))) != (fork_id, branch, tr):
            lc["try file path != fork_id/branch/try fields"] += 1
        yield ("stage_b", f"{fork_id}/{branch}/{tr}", d["env"], d, {"fork_attempt_index": d["fork_attempt_index"]})


def is_holdout_line(ln: dict) -> bool:
    parts = ln["ckey"].split("|")
    if parts[0] in HOLDOUT_DATASETS:
        return True
    return parts[0] == "stage_b" and len(parts) > 1 and P3.is_holdout_fork(parts[1])


def run_labels(jobs: Iterator[tuple], out_path: str, workers: int = 1,
               log: Callable[[str], None] = print) -> Dict[str, Any]:
    """Label every job; write out_path (via a .tmp file). Every line must be a hold-out key."""
    t0 = time.time()
    counts: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    problems: List[str] = []
    lines: List[dict] = []
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as out:
        pool = multiprocessing.get_context("fork").Pool(workers) if workers > 1 else None
        try:
            results = pool.imap(P3.label_conversation, jobs, chunksize=2) if pool else map(P3.label_conversation, jobs)
            for r in results:
                counts[r["dataset"]].update(r["counts"])
                problems += r["problems"]
                for ln in r["lines"]:
                    if not is_holdout_line(ln):
                        raise RuntimeError(f"{ln['ckey']}: not a hold-out key (development data in the hold-out run)")
                    out.write(json.dumps(ln, ensure_ascii=False, separators=(",", ":")) + "\n")
                lines += r["lines"]
        finally:
            if pool:
                pool.close()
                pool.join()
    os.replace(tmp, out_path)
    log(f"[holdout labels] {len(lines)} labels, {time.time() - t0:.0f} s")
    return {"lines": lines, "counts": counts, "problems": problems, "seconds": round(time.time() - t0, 1)}


def write_report(path: str, labels_path: str, res: Dict[str, Any], load_counts: Dict[str, collections.Counter],
                 argv: List[str], manifest_files: int) -> None:
    lines, counts = res["lines"], res["counts"]
    tot: collections.Counter = collections.Counter()
    for c in counts.values():
        tot.update(c)
    by_ds: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for ln in lines:
        k = ln["dataset"] + (f" ({ln['part']})" if "part" in ln else "")
        by_ds[k]["labels"] += 1
        by_ds[k]["accepted" if ln["accepted"] else "refused"] += 1
        by_ds[k][f"decision {ln['decision']}"] += 1
    L = ["# Tracker v3 p12: τ-bench tool labels of the HOLD-OUT", "",
         f"Written by `scoring/v3_p12_holdout_labels.py` on {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. "
         f"$0: no LLM call, no network. Labels: `{P3.rel(labels_path)}` (p3's line format; made by "
         "`scoring/v3_p3_labels.py`'s `label_conversation`, unchanged). The hold-out is opened once (p12 step 4).", "",
         "| data set (part) | labels | accepted | refused | allowed | blocked | cap override |", "|---|---|---|---|---|---|---|"]
    for k in sorted(by_ds):
        c = by_ds[k]
        L.append(f"| {k} | {c['labels']} | {c['accepted']} | {c['refused']} | {c['decision allowed']} | "
                 f"{c['decision blocked']} | {c['decision cap_override']} |")
    L += ["", f"- Conversations: {tot['conversations']}; write attempts found {tot['write attempts found']}; labelled "
          f"{len(lines)}; not labelled {tot['write attempts found'] - len(lines)}.",
          f"- Replayed tool calls {tot['replayed tool calls']}; replay mismatches **{tot['replay mismatches']}**; "
          f"ran but check output != saved output **{tot['ran: check output != saved output']}**.",
          f"- Manifest check passed first: {manifest_files} files.",
          "- Lines read: " + "; ".join(f"{n}: " + ", ".join(f"{k} {v}" for k, v in sorted(c.items()))
                                       for n, c in load_counts.items()),
          f"- Problems: {len(res['problems'])}" + ("" if not res["problems"] else " (first 20 below)")]
    L += [f"  - {p}" for p in res["problems"][:20]]
    L += ["", f"Run time {res['seconds']} s. Command: `python -B -m scoring.v3_p12_holdout_labels {' '.join(argv)}`",
          "", f"- `{P3.rel(labels_path)}`: `{P3.sha256_file(labels_path)}`",
          f"- `scoring/v3_p12_holdout_labels.py`: `{P3.sha256_file(os.path.abspath(__file__))}`",
          f"- `scoring/v3_p3_labels.py` (used, unchanged): `{P3.sha256_file(P3.__file__)}`"]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="python -B -m scoring.v3_p12_holdout_labels", description=__doc__.split("\n")[0])
    ap.add_argument("--holdout", action="store_true", help="label the hold-out (needs the second flag too)")
    ap.add_argument(LOOK_FLAG, dest="look", action="store_true", help="the main chat's one hold-out look")
    ap.add_argument("--workers", type=int, default=1, help="processes (at most 2 on this machine)")
    ap.add_argument("--out", default=HOLDOUT_LABELS)
    ap.add_argument("--report", default=HOLDOUT_REPORT)
    a = ap.parse_args(argv)
    if not 1 <= a.workers <= 2:
        ap.error("--workers must be 1 or 2")
    return a


def main(argv: Optional[List[str]] = None, jobs_fn: Callable[..., Iterator[tuple]] = None) -> int:
    """jobs_fn: tests only (built conversations); default holdout_jobs."""
    raw = list(sys.argv[1:] if argv is None else argv)
    a = parse_args(raw)
    try:
        check_lock(a.holdout, a.look)
        check_outputs(a.out, a.report)
    except HoldoutLocked as e:
        print(f"REFUSED: {e.msg}", flush=True)
        return 2
    from state_tracker.v3.frozen import check_manifest       # the eval v2 data must be unchanged
    manifest = check_manifest()
    splits = P3.load_splits()
    load_counts: Dict[str, collections.Counter] = {}
    jobs = (jobs_fn or holdout_jobs)(splits, load_counts)
    res = run_labels(jobs, a.out, a.workers)
    write_report(a.report, a.out, res, load_counts, raw, len(manifest))
    print(json.dumps({"labels": len(res["lines"]), "problems": len(res["problems"]), "seconds": res["seconds"],
                      "out": P3.rel(a.out), "report": P3.rel(a.report)}, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
