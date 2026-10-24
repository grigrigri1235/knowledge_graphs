"""Independent recompute of tracker v3's live test (p14 B2), written from the rules text and the raw data only.

Rules: docs/planning/tracker_v3/preregistration_online.md, sections 2-5 (and the cost line of 7-8).
It does not import or read the project's metrics or report code. Standard library only. No network, no LLM.

What it does, for one run folder:
  1. reads every <arm>/episodes_shard*.jsonl and dropped_groups_*.jsonl;
  2. keeps, for each (arm, domain, task_index, trial), the line with the highest unit_attempt (a tie: the later line);
  3. a (task, try) group counts only if all 5 arms have a kept line without an error and the group is not dropped;
  4. task success = the line's `reward` (tau-bench's own); per task = mean over its counted tries; per arm = mean
     over the tasks that have at least one counted group;
  5. the main claim: v3 (tgr_tracker_v3) - tgr_frozen, paired by task (mean of per-task differences), on all
     tasks, on val and on train (the line's task_group); S1: direct_facts_v3 - direct; S2: tgr_tracker_v3 -
     direct_facts_v3;
  6. 95 % range: bootstrap over tasks, stratified by domain (each resample draws, with replacement, as many tasks of
     each domain as there are), 10,000 resamples, a fresh random.Random(20261023) for each comparison and subset,
     percentile range with linear interpolation (numpy's default: position q * (B - 1) in the sorted values);
  7. verdicts: main pass if the lower end > -0.10; leak: val's upper end < train's point estimate -> "possible leak";
     S1 "facts help" / "facts hurt" / "no clear difference"; S2 "rules better" / "rules worse" / "no clear
     difference";
  8. cost per conversation = sum of the line's cost{agent, user, guard} (if that is missing: the sum of
     usage_roles[*].cost); mean per arm over the counted lines, and the total over all lines;
  9. error lines (all lines, and kept lines), dropped groups, incomplete groups, tasks with no counted group.

Point estimates are exact means (no randomness) and must match any other correct implementation (to float rounding,
~1e-12). The bootstrap ranges only match another implementation if its resampling is the same; expect them to
differ in the third decimal.

Run from predicate_correctness/:
  python3 -B tests/audit_v3_online_recompute.py --run-dir <run folder> --out <prefix>
writes <prefix>.json and <prefix>.md.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import random
import sys

sys.dont_write_bytecode = True

PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_FILE = os.path.join(PC_DIR, "output", "eval_v3", "online_tasks.json")
ARMS = ("none", "direct", "direct_facts_v3", "tgr_frozen", "tgr_tracker_v3")
SEED = 20261023
N_BOOT = 10000
MAIN_BAR = -0.10
COMPARISONS = {
    "main_v3_minus_frozen": ("tgr_tracker_v3", "tgr_frozen"),
    "S1_facts_minus_direct": ("direct_facts_v3", "direct"),
    "S2_v3_minus_facts": ("tgr_tracker_v3", "direct_facts_v3"),
    "v3_minus_none": ("tgr_tracker_v3", "none"),
}
SUBSETS = ("all", "val", "train")


def read_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if line:
                out.append((n, json.loads(line)))
    return out


def line_cost(r):
    c = r.get("cost")
    if isinstance(c, dict) and c:
        return math.fsum(float(v or 0.0) for v in c.values())
    ur = r.get("usage_roles") or {}
    return math.fsum(float(v.get("cost") or 0.0) for v in ur.values() if isinstance(v, dict))


def percentile(sorted_vals, q):
    """Linear interpolation between closest ranks (numpy's default)."""
    n = len(sorted_vals)
    pos = q * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def bootstrap(diffs_by_domain, seed=SEED, n_boot=N_BOOT):
    """diffs_by_domain: {domain: [per-task difference, ...]} (domains in sorted order). Returns (lo, hi)."""
    rng = random.Random(seed)
    doms = sorted(d for d in diffs_by_domain if diffs_by_domain[d])
    n_total = sum(len(diffs_by_domain[d]) for d in doms)
    stats = []
    for _ in range(n_boot):
        s = 0.0
        for d in doms:
            v = diffs_by_domain[d]
            k = len(v)
            for _ in range(k):
                s += v[rng.randrange(k)]
        stats.append(s / n_total)
    stats.sort()
    return percentile(stats, 0.025), percentile(stats, 0.975)


def load_run(run_dir):
    warnings = []
    lines = []  # (arm, record)
    files = {}
    for arm in ARMS:
        paths = sorted(glob.glob(os.path.join(run_dir, arm, "episodes_shard*.jsonl")))
        files[arm] = [os.path.relpath(p, run_dir) for p in paths]
        for p in paths:
            for n, r in read_jsonl(p):
                if r.get("arm", arm) != arm:
                    warnings.append(f"{p}:{n}: arm field {r.get('arm')!r} in folder {arm}")
                lines.append((arm, r, f"{os.path.relpath(p, run_dir)}:{n}"))
    extra = [d for d in sorted(os.listdir(run_dir))
             if os.path.isdir(os.path.join(run_dir, d)) and glob.glob(os.path.join(run_dir, d, "episodes_shard*.jsonl"))
             and d not in ARMS]
    if extra:
        warnings.append(f"episode folders that are not one of the 5 arms (ignored): {extra}")
    backups = sorted(glob.glob(os.path.join(run_dir, "*", "*.before_resume")))
    if backups:
        warnings.append(f"{len(backups)} *.before_resume files present (not read)")
    dropped = set()
    dropped_lines = 0
    for p in sorted(glob.glob(os.path.join(run_dir, "dropped_groups_*.jsonl"))):
        for _, r in read_jsonl(p):
            dropped_lines += 1
            dropped.add((r["env"], int(r["task_index"]), int(r["trial"])))
    return lines, files, dropped, dropped_lines, warnings


def recompute(run_dir, tasks_file=TASKS_FILE, seed=SEED, n_boot=N_BOOT):
    lines, files, dropped, dropped_lines, warnings = load_run(run_dir)
    with open(tasks_file, encoding="utf-8") as f:
        tasks = json.load(f)["tasks"]
    task_info = {(t["domain"], int(t["task_index"])): t["group"] for t in tasks}

    # error counts over all lines
    err_all = {a: 0 for a in ARMS}
    n_lines = {a: 0 for a in ARMS}
    spend_all = {a: 0.0 for a in ARMS}
    for arm, r, _ in lines:
        n_lines[arm] += 1
        spend_all[arm] += line_cost(r)
        if r.get("error"):
            err_all[arm] += 1

    # keep the highest unit_attempt per (arm, domain, task_index, trial)
    kept = {}
    ties = 0
    for arm, r, where in lines:
        key = (arm, r["env"], int(r["task_index"]), int(r["trial"]))
        att = int(r.get("unit_attempt") or 1)
        if key in kept:
            if att == kept[key][0]:
                ties += 1
            if att < kept[key][0]:
                continue
        kept[key] = (att, r, where)
    if ties:
        warnings.append(f"{ties} lines with the same unit_attempt as an earlier line of the same unit (later kept)")
    err_kept = {a: 0 for a in ARMS}
    for (arm, *_), (_, r, _) in kept.items():
        if r.get("error"):
            err_kept[arm] += 1

    # groups
    groups = sorted({k[1:] for k in kept} | dropped)
    complete, incomplete, dropped_seen = [], [], []
    for g in groups:
        if g in dropped:
            dropped_seen.append(g)
            continue
        ok = all((a,) + g in kept and not kept[(a,) + g][1].get("error") and kept[(a,) + g][1].get("reward") is not None
                 for a in ARMS)
        (complete if ok else incomplete).append(g)

    # task group (val/train) from the line field, checked against the tasks file
    tg_of = {}
    for g in complete:
        for a in ARMS:
            r = kept[(a,) + g][1]
            tk = (g[0], g[1])
            tg = r.get("task_group")
            if tg_of.setdefault(tk, tg) != tg:
                warnings.append(f"task {tk}: task_group differs between lines ({tg_of[tk]!r} vs {tg!r})")
            if tk not in task_info:
                warnings.append(f"task {tk} is not in online_tasks.json")
            elif task_info[tk] != tg:
                warnings.append(f"task {tk}: task_group {tg!r} but online_tasks.json says {task_info[tk]!r}")
    if len(task_mean_keys := {(g[0], g[1]) for g in complete}) != 99:
        warnings.append(f"{len(task_mean_keys)} tasks counted, not 99: the verdicts are not the p14 verdicts")
    reward_vs_info = 0
    for g in complete:
        for a in ARMS:
            r = kept[(a,) + g][1]
            ri = r.get("reward_info")
            if isinstance(ri, dict) and ri.get("reward") is not None and float(ri["reward"]) != float(r["reward"]):
                reward_vs_info += 1
    if reward_vs_info:
        warnings.append(f"{reward_vs_info} counted lines where reward != reward_info.reward (the `reward` field is used)")

    # per task, per arm success = mean over counted tries
    per_task = {}  # (domain, task_index) -> {arm: [rewards]}
    for g in complete:
        tk = (g[0], g[1])
        d = per_task.setdefault(tk, {a: [] for a in ARMS})
        for a in ARMS:
            d[a].append(float(kept[(a,) + g][1]["reward"]))
    task_mean = {tk: {a: math.fsum(v[a]) / len(v[a]) for a in ARMS} for tk, v in per_task.items()}
    all_tasks_seen = {(g[0], g[1]) for g in groups}
    tasks_no_group = sorted(all_tasks_seen - set(task_mean))

    def subset_tasks(sub):
        return sorted(tk for tk in task_mean if sub == "all" or tg_of.get(tk) == sub)

    arm_success = {}
    for sub in SUBSETS:
        ts = subset_tasks(sub)
        arm_success[sub] = {a: (math.fsum(task_mean[t][a] for t in ts) / len(ts) if ts else None) for a in ARMS}
        arm_success[sub]["n_tasks"] = len(ts)

    comps = {}
    for name, (a, b) in COMPARISONS.items():
        comps[name] = {"arms": f"{a} - {b}"}
        for sub in SUBSETS:
            ts = subset_tasks(sub)
            if not ts:
                comps[name][sub] = {"n_tasks": 0, "point": None, "lo": None, "hi": None}
                continue
            diffs = {t: task_mean[t][a] - task_mean[t][b] for t in ts}
            point = math.fsum(diffs.values()) / len(ts)
            by_dom = {}
            for t in ts:
                by_dom.setdefault(t[0], []).append(diffs[t])
            lo, hi = bootstrap(by_dom, seed, n_boot)
            comps[name][sub] = {"n_tasks": len(ts), "n_tasks_by_domain": {d: len(v) for d, v in sorted(by_dom.items())},
                                "point": point, "lo": lo, "hi": hi}

    def word(c, pos, neg):
        if c["lo"] is None:
            return "no data"
        return pos if c["lo"] > 0 else neg if c["hi"] < 0 else "no clear difference"

    m = comps["main_v3_minus_frozen"]
    verdicts = {
        "main": (None if m["all"]["lo"] is None else
                 "pass: v3 is not clearly worse than frozen TGR" if m["all"]["lo"] > MAIN_BAR else "fail"),
        "leak": (None if m["val"]["hi"] is None or m["train"]["point"] is None else
                 "possible leak" if m["val"]["hi"] < m["train"]["point"] else "no leak sign")
                or "not computable (val or train has no task)",
        "S1": {s: word(comps["S1_facts_minus_direct"][s], "facts help", "facts hurt") for s in SUBSETS},
        "S2": {s: word(comps["S2_v3_minus_facts"][s], "rules better", "rules worse") for s in SUBSETS},
    }

    counted_cost = {}
    for a in ARMS:
        cs = [line_cost(kept[(a,) + g][1]) for g in complete]
        counted_cost[a] = {"mean_per_conversation": (math.fsum(cs) / len(cs) if cs else None), "n": len(cs)}
    costs = {"counted_lines": counted_cost,
             "all_lines": {a: {"total": spend_all[a], "n_lines": n_lines[a],
                               "mean_per_line": (spend_all[a] / n_lines[a] if n_lines[a] else None)} for a in ARMS},
             "total_all_lines": math.fsum(spend_all.values())}

    return {
        "what": "independent recompute of p14 from preregistration_online.md sections 2-5 and the raw run folder",
        "run_dir": os.path.abspath(run_dir),
        "settings": {"seed": seed, "n_boot": n_boot, "percentile": "linear interpolation, q*(B-1)",
                     "rng": "python random.Random(seed), fresh per comparison and subset; domains in sorted order; "
                            "per domain k draws of randrange(k)", "main_bar": MAIN_BAR},
        "files": files,
        "counts": {"lines": n_lines, "error_lines_all": err_all, "error_lines_kept": err_kept,
                   "groups_seen": len(groups), "groups_complete": len(complete),
                   "groups_dropped": len(dropped_seen), "dropped_file_lines": dropped_lines,
                   "groups_incomplete_not_dropped": len(incomplete),
                   "incomplete_list": [list(g) for g in incomplete], "dropped_list": [list(g) for g in dropped_seen],
                   "tasks_with_counted_group": len(task_mean), "tasks_with_no_counted_group": len(tasks_no_group),
                   "tasks_with_no_counted_group_list": [list(t) for t in tasks_no_group],
                   "tasks_by_group": {s: len(subset_tasks(s)) for s in ("val", "train")}},
        "arm_success": arm_success,
        "comparisons": comps,
        "verdicts": verdicts,
        "costs": costs,
        "warnings": warnings,
        "note": "point estimates are exact (must match another implementation to ~1e-12); bootstrap ranges match "
                "only if the resampling is the same",
    }


def f(x, nd=4, sign=True):
    return "-" if x is None else f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"


def to_md(res):
    c = res["counts"]
    out = ["# p14 independent recompute", "",
           f"Run folder: `{res['run_dir']}`", "",
           "Made from the rules text and the raw lines only (no project metrics code). Point estimates are exact and "
           "must match; the 95 % ranges come from my own bootstrap (seed 20261023, 10,000, stratified by domain) and "
           "only match if the resampling is the same.", "",
           "## Counts",
           f"- groups seen {c['groups_seen']}, complete {c['groups_complete']}, dropped {c['groups_dropped']}, "
           f"incomplete (not dropped) {c['groups_incomplete_not_dropped']}",
           f"- tasks counted {c['tasks_with_counted_group']} (val {c['tasks_by_group']['val']}, train "
           f"{c['tasks_by_group']['train']}); tasks with no counted group {c['tasks_with_no_counted_group']}",
           "- error lines (all / kept): " + ", ".join(f"{a} {c['error_lines_all'][a]}/{c['error_lines_kept'][a]}"
                                                      for a in ARMS), "",
           "## Task success per arm", "", "| arm | all | val | train |", "|---|---|---|---|"]
    s = res["arm_success"]
    for a in ARMS:
        out.append(f"| {a} | {f(s['all'][a], 3, False)} | {f(s['val'][a], 3, False)} | {f(s['train'][a], 3, False)} |")
    out += ["", "## Differences (point [95 % range], n tasks)", "", "| comparison | all | val | train |",
            "|---|---|---|---|"]
    for name, cm in res["comparisons"].items():
        cells = []
        for sub in SUBSETS:
            x = cm[sub]
            cells.append(f"{f(x['point'])} [{f(x['lo'])}, {f(x['hi'])}] n={x['n_tasks']}")
        out.append(f"| {name} ({cm['arms']}) | " + " | ".join(cells) + " |")
    v = res["verdicts"]
    out += ["", "## Verdicts", f"- main (lower end > -0.10): **{v['main']}**", f"- leak check: **{v['leak']}**",
            f"- S1: all **{v['S1']['all']}** (val {v['S1']['val']}, train {v['S1']['train']})",
            f"- S2: all **{v['S2']['all']}** (val {v['S2']['val']}, train {v['S2']['train']})",
            "- two secondary claims, no multiple-testing correction", "",
            "## Cost per conversation (counted lines)", "", "| arm | mean $ | n | all lines total $ |", "|---|---|---|---|"]
    for a in ARMS:
        cc = res["costs"]["counted_lines"][a]
        out.append(f"| {a} | {f(cc['mean_per_conversation'], 5, False)} | {cc['n']} | "
                   f"{f(res['costs']['all_lines'][a]['total'], 4, False)} |")
    out.append(f"\nTotal spend, all lines: ${res['costs']['total_all_lines']:.4f}")
    if res["warnings"]:
        out += ["", "## Warnings"] + [f"- {w}" for w in res["warnings"]]
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--out", required=True, help="output prefix; writes <prefix>.json and <prefix>.md")
    ap.add_argument("--tasks-file", default=TASKS_FILE)
    args = ap.parse_args(argv)
    res = recompute(args.run_dir, args.tasks_file)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out + ".json", "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, sort_keys=False)
    with open(args.out + ".md", "w", encoding="utf-8") as fh:
        fh.write(to_md(res))
    print(f"wrote {args.out}.json and {args.out}.md; main: {res['verdicts']['main']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
