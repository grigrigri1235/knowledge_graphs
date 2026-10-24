"""Tracker v3, part 14: the after-run report of the paid online test (docs/planning/tracker_v3/p14.md,
preregistration_online.md). $0: no LLM call, no network. Reads run folders and metrics only; never the gold scorer
(task success = τ-bench's own reward in the episode lines), never a saved val run, never the partner's test group.

What it writes (default: the repo's docs/reports/):
  <out-dir>/tracker_v3_report.md
  <out-dir>/figures/v3_online_success.png   success per arm, 95 % ranges (all 99, val 33, train 66)
  <out-dir>/figures/v3_online_paired.png    paired differences (v3 - frozen TGR with the -0.10 line, S1, S2,
                                            v3 - no guard), all 99, val 33, train 66
The report holds: the main claim's verdict (all 99 tasks, the 95 % range, pass or fail), the leak check (val 33 vs
train 66), S1 and S2 (no multiple-testing correction), safety, the five-arm table, the 18 refusal tasks, the
reported-only items, the stops that fired, spend vs limits, and warnings (fewer than 99 tasks, mixed runs, ...).

Input, one of:
  --metrics-json <file>   the output of scoring/v3_online_metrics.py run --run-dir ... --out <file>
  --run-dir <dir> ...     the same metrics computed here (the same functions as that command)
The run folders (for stops, spend, run.json) come from --run-dir, else from the metrics file's "run_dirs".

TEST mode: when a run folder is under output/eval_v3/dryrun/ (or its run.json says sandbox), every output is marked
TEST (dry-run data, fake LLMs) and --out-dir must be under output/eval_v3/dryrun/p14report/. The real docs/reports/
is refused in TEST mode, before anything is written.

Commands (from predicate_correctness/; analysis python):
  PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 /home/azureuser/miniconda3/bin/python3 -B -m scoring.v3_online_metrics \
      run --run-dir output/eval_v3/B2/<run_id> --out output/logs/v3_B2_<run_id>_metrics.json \
      > output/logs/v3_B2_<run_id>_metrics.log 2>&1
  PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 /home/azureuser/miniconda3/bin/python3 -B -m scoring.v3_p14_report \
      --metrics-json output/logs/v3_B2_<run_id>_metrics.json > output/logs/v3_B2_<run_id>_report.log 2>&1
Imports: scoring.v3_online_metrics, scoring.v3_online_interim, guard.soft_stop_v3 (reads files only); matplotlib
inside the figure function only.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Sequence

sys.dont_write_bytecode = True

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "scoring"

from scoring import v3_online_metrics as M                      # noqa: E402
from scoring import v3_online_interim as I                      # noqa: E402
from guard import soft_stop_v3 as SS                             # noqa: E402

PC_DIR = M.PC_DIR
REPO_DIR = os.path.dirname(PC_DIR)
REAL_OUT_DIR = os.path.join(REPO_DIR, "docs", "reports")
DRYRUN_ROOT = os.path.join(PC_DIR, "output", "eval_v3", "dryrun")
TEST_OUT_ROOT = os.path.join(DRYRUN_ROOT, "p14report")
LOGS_DIR = os.path.join(PC_DIR, "output", "logs")
REPORT_NAME = "tracker_v3_report.md"
FIG_SUCCESS = "v3_online_success.png"
FIG_PAIRED = "v3_online_paired.png"
TEST_MARK = "TEST (dry-run data, fake LLMs)"

ARMS = M.ARMS
LABEL = M.ARM_LABEL
SETS = ("all", "val", "train")
SET_LABEL = {"all": "all 99", "val": "val 33 (unseen)", "train": "train 66 (seen)"}
# p14.md: cost per conversation, point and high estimate (high = the stop threshold / 3)
POINT_USD = {"none": 0.0068, "direct": 0.0127, "direct_facts_v3": 0.0131, "tgr_frozen": 0.0120,
             "tgr_tracker_v3": 0.0104}
HIGH_USD = {a: SS.ARM_MEAN_STOP_USD[a] / 3 for a in ARMS}
B2_ESTIMATE = "$15-22, point $16.4"
# the last sha256 logged in the preregistration change log (prefixes)
LOGGED_SHA = {"scoring/v3_online_metrics.py": "8f83b1f3", "scoring/v3_online_interim.py": "f30eba6d",
              "guard/run_online_v3.py": "45ee28bd", "guard/soft_stop_v3.py": "f83a04b4",
              "guard/direct_facts_v3.py": "3913e600"}


# ----------------------------------------------------------------------------------------------- small helpers
def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _under(path: str, root: str) -> bool:
    ap, rp = os.path.abspath(path), os.path.abspath(root)
    return ap == rp or ap.startswith(rp + os.sep)


def f3(x: Any, sign: bool = False) -> str:
    if x is None:
        return "n/a"
    return f"{x:+.3f}" if sign else f"{x:.3f}"


def pct(x: Any) -> str:
    return "n/a" if x is None else f"{100 * x:.1f} %"


def usd(x: Any, dp: int = 4) -> str:
    return "n/a" if x is None else f"${x:.{dp}f}"


def rng(lo: Any, hi: Any, sign: bool = False) -> str:
    return f"[{f3(lo, sign)}, {f3(hi, sign)}]"


def table(head: Sequence[str], rows: Sequence[Sequence[Any]]) -> List[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out


def read_json(path: str) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ----------------------------------------------------------------------------------------------- inputs
def compute_metrics(run_dirs: Sequence[str], rule_broken: Optional[str] = None) -> dict:
    """The same as `v3_online_metrics.py run --run-dir ...` (its main(), without the file write)."""
    raw = M.load_raw_lines(run_dirs)
    convs = M.load_run_dirs(run_dirs)
    offline = None
    if rule_broken:
        offline = {(r["domain"], int(r["task"]), int(r["trial"]), M.ALIASES.get(r["arm"], r["arm"]),
                    r["exec_step"], r["attempt"]): r["decision"] for r in M.read_jsonl(rule_broken)}
    try:
        doc = M.report(convs, complete=True, offline_rule_broken=offline, raw=raw)
    except M.MissingArm as e:
        raise SystemExit(f"refused: {e}")
    doc["run_dirs"] = [os.path.relpath(os.path.abspath(d), PC_DIR) for d in run_dirs]
    doc["dropped_groups_listed"] = sorted(list(k) for k in M.dropped_groups(run_dirs))
    return M._jsonable(doc)


def run_info(run_dir: str) -> dict:
    """run.json, the STOP file, the shard logs' stop and done lines, pids."""
    rj = read_json(os.path.join(run_dir, "run.json")) or {}
    ident = rj.get("ident") or {}
    step, run_id = ident.get("step"), ident.get("run_id")
    if not run_id:
        run_id = os.path.basename(os.path.abspath(run_dir))
        step = step or os.path.basename(os.path.dirname(os.path.abspath(run_dir)))
    logs = sorted(glob.glob(os.path.join(LOGS_DIR, f"v3_{step}_{run_id}_s*.log")))
    stopped, done = [], []
    for p in logs:
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if "STOPPED:" in line:
                        stopped.append(f"{os.path.basename(p)}: {line.strip()[:300]}")
                    elif " DONE:" in line:
                        done.append(f"{os.path.basename(p)}: {line.strip()[:300]}")
        except OSError:
            pass
    return {"run_dir": run_dir, "step": step, "run_id": run_id, "run_json": bool(rj),
            "sandbox": bool(rj.get("sandbox")) or _under(run_dir, DRYRUN_ROOT),
            "approval_quote": ident.get("approval_quote") or rj.get("approval_quote"),
            "created": rj.get("created"), "cap_usd": ident.get("cap_usd"),
            "hard_limit_usd": ident.get("hard_limit_usd"), "tasks": ident.get("n_tasks"), "tries": ident.get("tries"),
            "shards": ident.get("n_shards"), "runner_version": ident.get("runner_version"),
            "stop_file": os.path.exists(os.path.join(run_dir, SS.STOP_FILENAME)),
            "logs": [os.path.relpath(p, PC_DIR) for p in logs], "log_stopped": stopped, "log_done": done}


def spend_info(run_dirs: Sequence[str], infos: Sequence[dict], test: bool) -> dict:
    """This run's spend from its lines (every line: errors, re-runs and dropped groups included), per arm; the
    step limit; the v3 total (soft_stop_v3.v3_spend, real folders only) and the cap."""
    per_arm: Dict[str, dict] = {}
    for c in M.load_raw_lines(run_dirs):
        a = per_arm.setdefault(c["arm"], {"lines": 0, "usd": 0.0, "errors": 0, "max_usd": 0.0})
        a["lines"] += 1
        a["usd"] += c["cost"]
        a["errors"] += c["error"] is not None
        a["max_usd"] = max(a["max_usd"], c["cost"])
    for a in per_arm.values():
        a["mean_usd"] = a["usd"] / a["lines"] if a["lines"] else None
    run_usd = sum(a["usd"] for a in per_arm.values())
    steps = sorted({i["step"] for i in infos if i.get("step")})
    limit = None
    lims = [i["hard_limit_usd"] for i in infos if i.get("hard_limit_usd") is not None]
    if lims:
        limit = max(lims)
    elif len(steps) == 1 and steps[0] in SS.STEP_LIMITS_USD:
        limit = SS.STEP_LIMITS_USD[steps[0]]
    caps = [i["cap_usd"] for i in infos if i.get("cap_usd") is not None]
    try:
        tot = SS.v3_spend()
        total = {"total_usd": tot["total_usd"], "questions_usd": tot["questions_usd"],
                 "episodes_usd": tot["episodes_usd"], "backups_extra_usd": tot["backups_extra_usd"],
                 "dryrun_usd_not_counted": tot["dryrun_usd_not_counted"], "unreadable": len(tot["unreadable"])}
    except Exception as e:  # noqa: BLE001 - shown in the report
        total = {"error": f"{type(e).__name__}: {e}"}
    return {"per_arm": per_arm, "run_usd": run_usd, "steps": steps, "hard_limit_usd": limit,
            "cap_usd": max(caps) if caps else SS.V3_CAP_USD, "v3_total": total, "test": test}


def code_shas() -> List[dict]:
    out = []
    for rel, want in LOGGED_SHA.items():
        p = os.path.join(PC_DIR, *rel.split("/"))
        s = sha256_file(p) if os.path.exists(p) else None
        out.append({"file": rel, "sha256": s, "logged_prefix": want, "same": bool(s and s.startswith(want))})
    return out


# ----------------------------------------------------------------------------------------------- figures
def make_figures(doc: dict, fig_dir: str, test: bool) -> List[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    os.makedirs(fig_dir, exist_ok=True)
    plt.rcParams.update({"font.size": 10, "axes.edgecolor": "#444444", "axes.linewidth": 0.8})
    style = {"all": dict(marker="o", ms=8, mfc="black", mec="black", color="black", lw=2.0),
             "val": dict(marker="s", ms=7, mfc="white", mec="black", color="black", lw=1.2),
             "train": dict(marker="^", ms=7, mfc="#888888", mec="black", color="#666666", lw=1.2)}
    off = {"all": -0.22, "val": 0.0, "train": 0.22}
    pre = f"{TEST_MARK}: " if test else ""
    paths = []

    # 1. success per arm
    fig, ax = plt.subplots(figsize=(8.0, 5.2), dpi=150)
    for i, arm in enumerate(ARMS):
        for ts in SETS:
            r = (doc.get("arm_success") or {}).get(arm, {}).get(ts) or {}
            if r.get("rate") is None:
                continue
            y = i + off[ts]
            lo, hi = r.get("low"), r.get("high")
            if lo is not None and hi is not None:
                ax.plot([lo, hi], [y, y], color=style[ts]["color"], lw=style[ts]["lw"], solid_capstyle="butt")
            ax.plot([r["rate"]], [y], linestyle="none", marker=style[ts]["marker"], ms=style[ts]["ms"],
                    mfc=style[ts]["mfc"], mec=style[ts]["mec"])
            if ts == "all":
                ax.annotate(f"{r['rate']:.2f}", (hi if hi is not None else r["rate"], y), xytext=(5, 0),
                            textcoords="offset points", ha="left", va="center", fontsize=8)
    ax.set_yticks(range(len(ARMS)))
    ax.set_yticklabels([LABEL[a] for a in ARMS])
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("task success (τ-bench reward; tries averaged per task)")
    ax.grid(axis="x", color="#dddddd", lw=0.6)
    ax.set_axisbelow(True)
    for ts in SETS:
        ax.plot([], [], linestyle="-", marker=style[ts]["marker"], ms=style[ts]["ms"], mfc=style[ts]["mfc"],
                mec=style[ts]["mec"], color=style[ts]["color"], lw=style[ts]["lw"], label=SET_LABEL[ts])
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=3, fontsize=8, frameon=False,
              title="tasks (marker = point; line = 95 % range)", title_fontsize=8)
    ax.set_title(f"{pre}\ntask success per arm, with 95 % ranges" if pre else
                 "task success per arm, with 95 % ranges", fontsize=10.5)
    fig.tight_layout()
    p = os.path.join(fig_dir, FIG_SUCCESS)
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    paths.append(p)

    # 2. paired differences
    mc, sec, rep = doc.get("main_claim") or {}, doc.get("secondary") or {}, doc.get("reported") or {}
    rows = [("v3 − frozen TGR\n(main claim)", mc),
            ("S1: Direct + facts − Direct", sec.get("S1") or {}),
            ("S2: v3 − Direct + facts", sec.get("S2") or {}),
            ("v3 − no guard\n(reported)", rep.get(f"{M.V3}_vs_none") or {})]
    fig, ax = plt.subplots(figsize=(8.0, 5.2), dpi=150)
    xs = []
    for i, (_name, rec) in enumerate(rows):
        for ts in SETS:
            r = rec.get(ts) or {}
            if r.get("diff") is None:
                continue
            y = i + off[ts]
            lo, hi = r.get("low"), r.get("high")
            if lo is not None and hi is not None:
                ax.plot([lo, hi], [y, y], color=style[ts]["color"], lw=style[ts]["lw"], solid_capstyle="butt")
                xs += [lo, hi]
            xs.append(r["diff"])
            ax.plot([r["diff"]], [y], linestyle="none", marker=style[ts]["marker"], ms=style[ts]["ms"],
                    mfc=style[ts]["mfc"], mec=style[ts]["mec"])
            if ts == "all":
                ax.annotate(f"{r['diff']:+.3f}", (hi if hi is not None else r["diff"], y), xytext=(5, 0),
                            textcoords="offset points", ha="left", va="center", fontsize=8)
    ax.axvline(0, color="black", lw=0.9)
    ax.axvline(M.MARGIN, color="black", lw=1.2, linestyle=(0, (5, 3)))
    ax.text(M.MARGIN, len(rows) - 0.15, " −0.10: main-claim pass mark\n (its lower end must be above it)",
            fontsize=7.5, ha="left", va="bottom")
    span = max([0.25] + [abs(x) + 0.05 for x in xs])
    ax.set_xlim(-span, span)
    ax.set_ylim(len(rows) - 0.1, -0.5)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows], fontsize=9)
    ax.set_xlabel("difference in task success, paired by task (a − b)")
    ax.grid(axis="x", color="#dddddd", lw=0.6)
    ax.set_axisbelow(True)
    for ts in SETS:
        ax.plot([], [], linestyle="-", marker=style[ts]["marker"], ms=style[ts]["ms"], mfc=style[ts]["mfc"],
                mec=style[ts]["mec"], color=style[ts]["color"], lw=style[ts]["lw"], label=SET_LABEL[ts])
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=3, fontsize=8, frameon=False,
              title="tasks (marker = point; line = 95 % range)", title_fontsize=8)
    t2 = "paired differences, 95 % ranges (no multiple-testing correction)"
    ax.set_title(f"{pre}\n{t2}" if pre else t2, fontsize=10.5)
    fig.tight_layout()
    p = os.path.join(fig_dir, FIG_PAIRED)
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    paths.append(p)
    return paths


# ----------------------------------------------------------------------------------------------- the report
def build_warnings(doc: dict, infos: Sequence[dict], spend: dict, interim: Optional[dict], test: bool) -> List[str]:
    w = []
    if test:
        w.append(f"{TEST_MARK}: these numbers are not a result")
    w += list(doc.get("warnings") or [])
    n = (doc.get("main_claim") or {}).get("n_tasks")
    if n is not None and n < 99 and not any("rests on" in x for x in w):
        w.append(f"the main claim rests on {n} tasks, not 99")
    tc = doc.get("task_counts") or {}
    for ts, want in (doc.get("expected_task_counts") or {}).items():
        got = tc.get(ts) or {}
        if got != want:
            w.append(f"task counts of {ts}: {got} (planned {want})")
    steps = {i.get("step") for i in infos}
    rids = {i.get("run_id") for i in infos}
    if len(steps) > 1 or len(rids) > 1:
        w.append(f"more than one run folder: steps {sorted(map(str, steps))}, run ids {sorted(map(str, rids))}")
    rc = (doc.get("refusal_tasks") or {}).get("counts") or {}
    if rc and rc.get("all") != 18:
        w.append(f"refusal tasks found: {rc.get('all')} (planned 18 = 6 val + 12 train)")
    cg = doc.get("complete_groups") or {}
    if cg.get("dropped"):
        w.append(f"{len(cg['dropped'])} (task, try) group(s) are not complete and left the test")
    if doc.get("dropped_groups_listed"):
        w.append(f"{len(doc['dropped_groups_listed'])} (task, try) group(s) listed as dropped by the runner")
    for i in infos:
        if not i.get("run_json"):
            w.append(f"{i['run_dir']}: no run.json")
        if i.get("stop_file"):
            w.append(f"{i['run_dir']}: the STOP file is present")
        if i.get("log_stopped"):
            w.append(f"{i['run_dir']}: a shard log says STOPPED ({len(i['log_stopped'])} lines)")
    if interim and interim.get("any_stop"):
        w.append("a stop rule fires when recomputed on the final data (see Stops)")
    lim = spend.get("hard_limit_usd")
    if lim is not None and spend["run_usd"] > lim:
        w.append(f"the run's spend ${spend['run_usd']:.2f} is over its hard limit ${lim:.2f}")
    if not doc.get("safety", {}).get("pass", True):
        w.append("safety FAILS (see Safety)")
    for s in code_shas():
        if not s["same"]:
            w.append(f"{s['file']}: sha256 {str(s['sha256'])[:8]}… is not the last logged {s['logged_prefix']}… "
                     "(check the preregistration change log)")
    return w


def render(doc: dict, infos: Sequence[dict], spend: dict, interim: Optional[dict], warnings: Sequence[str],
           test: bool, metrics_src: str, fig_rel: str) -> str:
    L: List[str] = []
    mc = doc.get("main_claim") or {}
    allc = mc.get("all") or {}
    title = "# Tracker v3: the paid online test (p14), report"
    if test:
        title = f"# {TEST_MARK}: tracker v3 online report (format check only)"
    L += [title, ""]
    if test:
        L += [f"> **{TEST_MARK}.** Made from a sandbox run folder with fake LLMs and a scripted user. "
              "No number here is a result. The real report is written only from a real run folder.", ""]
    L += [f"Made {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} by `scoring/v3_p14_report.py` "
          f"from `{metrics_src}`. $0, no LLM call. Task success = τ-bench's own reward; no gold scorer.", ""]

    # --- headline
    verdict = mc.get("pass")
    L += ["## Main claim: is v3 clearly worse than frozen TGR? (all 99 tasks)", ""]
    if verdict is None:
        L += ["**No verdict**: no paired tasks.", ""]
    else:
        word = "PASS" if verdict else "FAIL"
        meaning = ("v3 is not clearly worse than frozen TGR" if verdict
                   else "we cannot say v3 is not clearly worse than frozen TGR")
        L += [f"**{word}**: v3 − frozen TGR = **{f3(allc.get('diff'), True)}**, 95 % range "
              f"**{rng(allc.get('low'), allc.get('high'), True)}**, on {allc.get('n_tasks')} tasks "
              f"(pass mark: the lower end above {M.MARGIN:+.2f}). So: {meaning}."
              + ("" if (allc.get("n_tasks") or 0) >= 99 else
                 f" **Only {allc.get('n_tasks')} tasks, not 99: this is not the pre-registered test.**"), ""]
    L += table(["tasks", "n tasks", "v3", "frozen TGR", "v3 − frozen [95 % range]", "lower end > −0.10?"],
               [[SET_LABEL[ts], (mc.get(ts) or {}).get("n_tasks"), f3((mc.get(ts) or {}).get("rate_a")),
                 f3((mc.get(ts) or {}).get("rate_b")),
                 f"{f3((mc.get(ts) or {}).get('diff'), True)} {rng((mc.get(ts) or {}).get('low'), (mc.get(ts) or {}).get('high'), True)}",
                 ("yes" if (mc.get(ts) or {}).get("pass") else "no") + ("" if ts == "all" else " (shown only)")]
                for ts in SETS])
    L += ["", "Bootstrap by task, stratified by domain, 10,000 resamples, seed 20261023, percentile range. "
          "A task's tries are averaged first. Only complete (task, try) groups count.", ""]

    # --- warnings early
    L += ["## Warnings", ""]
    L += [f"- {x}" for x in warnings] if warnings else ["- none"]
    L += [""]

    # --- leak check
    lc = mc.get("leak_check") or {}
    L += ["## Leak check (val 33 unseen vs train 66 seen)", "",
          f"**{lc.get('verdict') or 'n/a'}**: val's upper end {f3(lc.get('val_high'), True)} vs train's point "
          f"{f3(lc.get('train_diff'), True)}. Rule: \"possible leak\" if val's upper end is below train's point. "
          "This is a weak warning sign, not a pass mark (val alone passes only 47-66 % of the time if v3 equals "
          "frozen TGR).", ""]

    # --- secondary
    sec = doc.get("secondary") or {}
    L += ["## Secondary claims S1 and S2", "",
          "Two pre-registered claims, **no multiple-testing correction** (so read them with care). "
          "Verdict on all 99; val and train shown apart.", ""]
    rows = []
    for name, what in (("S1", "Direct + facts − Direct (do code facts help an LLM guard?)"),
                       ("S2", "v3 − Direct + facts (rules vs an LLM with the same facts)")):
        rec = sec.get(name) or {}
        for ts in SETS:
            r = rec.get(ts) or {}
            rows.append([name if ts == "all" else "", what if ts == "all" else "", SET_LABEL[ts], r.get("n_tasks"),
                         f3(r.get("diff"), True), rng(r.get("low"), r.get("high"), True),
                         (f"**{r.get('verdict') or 'n/a'}**" if ts == "all" else
                          f"{r.get('verdict') or 'n/a'} (shown only)")])
    L += table(["claim", "what", "tasks", "n", "difference", "95 % range", "verdict"], rows)
    L += [""]

    # --- safety
    sf = doc.get("safety") or {}
    sfc = doc.get("safety_complete_groups_info") or {}
    L += ["## Safety (pass mark: 0)", "",
          f"**{'PASS' if sf.get('pass') else 'FAIL'}**: {sf.get('bad')} v3 allows that τ-bench's tool then refused "
          f"at a check mapped to a v3 fact, out of {sf.get('allowed_writes')} writes v3 allowed (counted on every v3 "
          f"line, dropped groups included). Complete groups only: {sfc.get('bad')} of {sfc.get('allowed_writes')}.",
          "",
          f"- refused allows at an unmapped check (not a failure): {sf.get('refused_allows_unmapped_check')}",
          f"- refused cap overrides (v3 blocked; not an allow): {sf.get('refused_cap_overrides')}", ""]
    if sf.get("cases"):
        L += table(["domain", "task", "try", "set", "attempt", "tool", "check", "v3 facts"],
                   [[c["domain"], c["task"], c["trial"], c["split"], c["attempt"], c["tool"], c["check"],
                     ", ".join(c["mapped_facts"])] for c in sf["cases"][:30]])
        L += [""]
    oth = doc.get("safety_all_arms_info") or {}
    if oth:
        L += ["The same count for every arm (information only): " + "; ".join(
            f"{LABEL[a]} {(oth.get(a) or {}).get('bad')}/{(oth.get(a) or {}).get('allowed_writes')}" for a in ARMS
            if a in oth) + ".", ""]

    # --- five arms
    L += ["## The five arms (all 99 tasks, complete groups)", ""]
    rows = []
    for a in ARMS:
        s = ((doc.get("arm_success") or {}).get(a) or {}).get("all") or {}
        g = ((doc.get("guard") or {}).get(a) or {}).get("all") or {}
        cr = g.get("cost_range") or {}
        rows.append([LABEL[a], s.get("n_conversations"), f"{f3(s.get('rate'))} {rng(s.get('low'), s.get('high'))}",
                     f"{usd(cr.get('mean_over_tasks'))} [{usd(cr.get('low'))}, {usd(cr.get('high'))}]",
                     f"{usd(POINT_USD[a])} / {usd(HIGH_USD[a])}", f3(g.get("blocks_per_conversation")),
                     g.get("conversations_with_block"),
                     f"{g.get('hand_overs')} ({pct(g.get('hand_over_share'))})", g.get("cap_overrides"),
                     pct(g.get("checks_with_llm_share"))])
    L += table(["arm", "conv.", "success [95 % range]", "cost / conv. [95 % range]", "estimate point / high",
                "blocks / conv.", "conv. with a block", "hand-overs", "cap overrides", "checks with an LLM"], rows)
    L += ["", f"![success per arm]({fig_rel}/{FIG_SUCCESS})", "",
          "Success per arm by task set:", ""]
    rows = []
    for a in ARMS:
        r = [LABEL[a]]
        for ts in SETS:
            s = ((doc.get("arm_success") or {}).get(a) or {}).get(ts) or {}
            r.append(f"{f3(s.get('rate'))} {rng(s.get('low'), s.get('high'))}")
        rows.append(r)
    L += table(["arm"] + [SET_LABEL[ts] for ts in SETS], rows)
    rp = (doc.get("reported") or {}).get(f"{M.V3}_vs_none") or {}
    L += ["", "**v3 − no guard** (reported, no pass mark): " + "; ".join(
        f"{SET_LABEL[ts]} {f3((rp.get(ts) or {}).get('diff'), True)} "
        f"{rng((rp.get(ts) or {}).get('low'), (rp.get(ts) or {}).get('high'), True)}" for ts in SETS) + ".", "",
        f"![paired differences]({fig_rel}/{FIG_PAIRED})", ""]

    # --- refusal tasks
    rf = doc.get("refusal_tasks") or {}
    cnt = rf.get("counts") or {}
    L += ["## The refusal tasks (no write expected)", "",
          f"Found {cnt.get('all')} (val {cnt.get('val')}, train {cnt.get('train')}); planned 18 (6 + 12).", ""]
    rows = []
    for a in ARMS:
        r = ((rf.get("per_arm") or {}).get("all") or {}).get(a)
        if not r:
            continue
        sr = r.get("success_range") or {}
        rows.append([LABEL[a], r["conversations"], f"{f3(r['success'])} {rng(sr.get('low'), sr.get('high'))}",
                     pct(r["any_write_sent"]), pct(r["any_write_accepted"]), r["conversations_with_write_accepted"]])
    L += table(["arm", "conv.", "success [95 % range]", "any write sent", "any write accepted",
                "conv. with a write accepted"], rows) if rows else ["(none found)"]
    L += [""]

    # --- reported only
    L += ["## Reported only (no pass mark; all 99 tasks)", ""]
    rows = []
    for a in ARMS:
        e = ((doc.get("expected_actions") or {}).get(a) or {}).get("all") or {}
        rb = (doc.get("rule_broken") or {}).get(a) or {}
        g = ((doc.get("guard") or {}).get(a) or {}).get("all") or {}
        br = g.get("block_response") or {}
        rows.append([LABEL[a], pct(e.get("expected_writes_done_share")), pct(e.get("all_expected_writes_done_share")),
                     f3(e.get("unwanted_writes_per_conversation")), pct(e.get("conversations_with_unwanted_write")),
                     "n/a" if rb.get("executed_breaking") is None else
                     f"{rb.get('executed_breaking')} ({rb.get('source')})",
                     f"{pct(br.get('repeat'))} / {pct(br.get('respond'))} / {pct(br.get('other'))} "
                     f"(n {g.get('block_response_n')})",
                     f"{pct(g.get('advice_followed_share'))} (n {g.get('advice_n')})"])
    L += table(["arm", "expected writes done", "all expected writes done", "unwanted writes / conv.",
                "conv. with an unwanted write", "\"rule broken\" (v3's rules)", "after a block: repeat / respond / other",
                "advice followed"], rows)
    gv = ((doc.get("guard") or {}).get(M.V3) or {}).get("all") or {}
    L += ["", f"- v3 fact sources: {json.dumps(gv.get('v3_fact_sources') or {})}",
          f"- v3 tiny-question answers per conversation: {f3(gv.get('v3_question_answers_per_conversation'))}; "
          f"share of v3 blocks that used a question fact: {pct(gv.get('v3_blocked_checks_with_question_fact_share'))}",
          f"- v3 checks with a state error: {gv.get('v3_checks_with_state_error')}; with a fact error: "
          f"{gv.get('v3_checks_with_fact_error')}",
          "- \"rule broken\" for the other arms needs a $0 offline v3 pass (`--rule-broken`); n/a means it was not "
          "given.", "",
          "Cost per conversation by role (all lines of complete groups):", ""]
    rows = []
    for a in ARMS:
        g = ((doc.get("guard") or {}).get(a) or {}).get("all") or {}
        br = g.get("cost_per_conversation_by_role") or {}
        rows.append([LABEL[a], usd(br.get("agent")), usd(br.get("user")), usd(br.get("guard")),
                     usd(g.get("cost_p90")), usd(g.get("cost_max"))])
    L += table(["arm", "agent", "user", "guard", "p90", "max"], rows)
    L += [""]

    # --- stops
    L += ["## Stops", ""]
    rows = []
    for i in infos:
        rows.append(["STOP file (manual)", i["run_id"], "present" if i["stop_file"] else "no"])
        rows.append(["shard logs: STOPPED lines", i["run_id"],
                     "; ".join(i["log_stopped"][:5]) if i["log_stopped"] else
                     ("none" if i["logs"] else "no shard log found")])
    if interim:
        h = interim.get("harm") or {}
        rows.append(["harm (v3 − frozen ≤ −0.15 at 742 conv.), recomputed on the final data", "all",
                     ("fires" if h.get("fire") else "no") + (f" (diff {f3(h.get('diff'), True)}, "
                                                             f"{h.get('conversations_in_complete_groups')} conv.)"
                                                             if h.get("reached") else
                                                             f" (not reached: {h.get('conversations_in_complete_groups')} conv.)")])
        st = interim.get("state") or {}
        rows.append(["v3 state errors (3rd stops)", "all", ("fires" if st.get("fire") else "no") +
                     f" ({json.dumps({k: v for k, v in st.items() if k != 'fire'})[:200]})"])
        co = interim.get("cost") or {}
        parts = [f"{LABEL.get(k, k)} {usd(v.get('mean'))} / {usd(v.get('limit'), 3)} ({v.get('lines')} lines)"
                 for k, v in sorted((co.get("arms") or {}).items()) if isinstance(v, dict)]
        extra = {k: v for k, v in co.items() if k not in ("fire", "arms")}
        rows.append(["cost (arm mean over 3 × high after 50, or one conv. > $0.25)", "all",
                     ("fires" if co.get("fire") else "no") + " (mean / threshold: " + "; ".join(parts) + ")"
                     + (f" {json.dumps(extra, default=str)[:200]}" if extra else "")])
        er = interim.get("errors") or {}
        rows.append(["errors (≥ 10 and > 5 %, or 5 in a row)", "all",
                     ("fires" if er.get("fire") else "no") + f" ({er.get('error_lines')} of {er.get('lines')} "
                     f"lines, longest streak {er.get('longest_streak')})"])
    L += table(["rule", "run", "result"], rows)
    L += ["", "The halfway harm check is run by the main chat during the run (`scoring/v3_online_interim.py`); the row "
          "above recomputes it on the final data. The runner's own stops are in the shard logs.", ""]
    for i in infos:
        if i["log_done"]:
            L += [f"- {x}" for x in i["log_done"][:4]]
    L += [""]

    # --- spend
    L += ["## Spend vs limits (logged list price; the real bill is about 0.55× of this)", ""]
    rows = []
    for a in ARMS:
        s = spend["per_arm"].get(a) or {}
        rows.append([LABEL[a], s.get("lines"), s.get("errors"), usd(s.get("usd")), usd(s.get("mean_usd")),
                     usd(POINT_USD[a]), usd(HIGH_USD[a]), usd(SS.ARM_MEAN_STOP_USD[a], 3), usd(s.get("max_usd"))])
    L += table(["arm", "lines", "error lines", "spend", "mean / line", "estimate point", "estimate high",
                "stop threshold", "max line"], rows)
    lim = spend.get("hard_limit_usd")
    tot = spend.get("v3_total") or {}
    L += ["", f"- this run: **{usd(spend['run_usd'], 2)}** of its hard limit {usd(lim, 2)} "
          f"({pct(spend['run_usd'] / lim) if lim else 'n/a'}); B2 estimate {B2_ESTIMATE}",
          f"- v3 total so far (all real p12 and p14 lines, `soft_stop_v3.v3_spend`): "
          f"{usd(tot.get('total_usd'), 2)} of the cap {usd(spend.get('cap_usd'), 0)}"
          + (f" (questions {usd(tot.get('questions_usd'), 2)}, episodes {usd(tot.get('episodes_usd'), 2)})"
             if "total_usd" in tot else f" ({tot.get('error')})")]
    if test:
        L += ["- TEST: the run's spend above is fake-LLM spend in the dry-run folder, never counted toward the cap; "
              "the v3 total is the real one."]
    L += [""]

    # --- groups, tries, provenance
    cg = doc.get("complete_groups") or {}
    L += ["## Groups, tries, inputs", "",
          f"- (task, try) groups: {cg.get('groups')}, complete {cg.get('complete_groups')}, not complete "
          f"{len(cg.get('dropped') or [])}; dropped by the runner: {len(doc.get('dropped_groups_listed') or [])}",
          f"- lines per set/try (complete groups): {json.dumps(doc.get('tries') or {})}",
          f"- task counts: {json.dumps(doc.get('task_counts') or {})}"]
    for i in infos:
        L += [f"- run `{i['run_id']}` (step {i['step']}): `{os.path.relpath(os.path.abspath(i['run_dir']), PC_DIR)}`, "
              f"created {i['created']}, runner {i['runner_version']}, {i['tasks']} tasks × {i['tries']} tries, "
              f"{i['shards']} shards, approval words \"{i['approval_quote']}\", sandbox {i['sandbox']}"]
    L += ["", "Code (sha256 now vs the last one logged in the preregistration change log):", ""]
    L += table(["file", "sha256", "same as logged"],
               [[f"`{s['file']}`", f"`{s['sha256']}`", "yes" if s["same"] else "**no**"] for s in code_shas()])
    L += ["", "Rebuild: `scoring/v3_online_metrics.py run --run-dir <run folder> --out <json>`, then "
          "`scoring/v3_p14_report.py --metrics-json <json>` (commands in the module docstring).", ""]
    if test:
        L += [f"*{TEST_MARK}.*", ""]
    return "\n".join(L)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--metrics-json", help="output of scoring/v3_online_metrics.py run ... --out")
    src.add_argument("--run-dir", action="append", help="run folder(s); the metrics are computed here")
    ap.add_argument("--rule-broken", help="with --run-dir: jsonl of an offline v3 pass (as the metrics command)")
    ap.add_argument("--out-dir", default=REAL_OUT_DIR, help="where tracker_v3_report.md and figures/ go "
                    "(default: docs/reports; TEST data: under output/eval_v3/dryrun/p14report/)")
    ap.add_argument("--metrics-out", help="with --run-dir: also save the metrics JSON (under output/)")
    ap.add_argument("--overwrite", action="store_true", help="replace an existing report")
    a = ap.parse_args(argv)

    if a.metrics_json:
        doc = read_json(a.metrics_json)
        if doc is None:
            raise SystemExit(f"refused: cannot read {a.metrics_json}")
        run_dirs = [os.path.join(PC_DIR, d) if not os.path.isabs(d) else d for d in doc.get("run_dirs") or []]
        metrics_src = os.path.relpath(os.path.abspath(a.metrics_json), PC_DIR)
    else:
        run_dirs = [os.path.abspath(d) for d in a.run_dir]
        doc = None
        metrics_src = "computed here from " + ", ".join(os.path.relpath(d, PC_DIR) for d in run_dirs)
    if not run_dirs:
        raise SystemExit("refused: no run folder")
    for d in run_dirs:
        M._check_holdout(d, False)                             # never a saved val run
        if not os.path.isdir(d):
            raise SystemExit(f"refused: {d} is not a folder")
    infos = [run_info(d) for d in run_dirs]
    test = any(i["sandbox"] for i in infos)
    out_dir = os.path.abspath(a.out_dir)
    # the TEST guard comes before any write
    if test and not _under(out_dir, TEST_OUT_ROOT):
        raise SystemExit(f"refused: TEST data (a dry-run folder) may only be written under {TEST_OUT_ROOT}, "
                         f"not {out_dir}")
    if not test and _under(out_dir, DRYRUN_ROOT):
        raise SystemExit("refused: a real run's report does not go into the dry-run folder")
    if not (_under(out_dir, REPO_DIR)):
        raise SystemExit(f"refused: {out_dir} is outside {REPO_DIR}")
    report_path = os.path.join(out_dir, REPORT_NAME)
    if os.path.exists(report_path) and not a.overwrite:
        raise SystemExit(f"refused: {report_path} exists (use --overwrite)")

    if doc is None:
        doc = compute_metrics(run_dirs, a.rule_broken)
        if a.metrics_out:
            M.write_out(a.metrics_out, doc)
    try:
        interim = M._jsonable(I.interim(run_dirs))
    except Exception as e:  # noqa: BLE001 - shown as a warning
        interim = None
        doc.setdefault("warnings", []).append(f"interim recompute failed: {type(e).__name__}: {e}")
    spend = spend_info(run_dirs, infos, test)
    warnings = build_warnings(doc, infos, spend, interim, test)
    os.makedirs(out_dir, exist_ok=True)
    figs = make_figures(doc, os.path.join(out_dir, "figures"), test)
    text = render(doc, infos, spend, interim, warnings, test, metrics_src, "figures")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    mc = doc.get("main_claim") or {}
    print(f"[v3-p14-report] {'TEST ' if test else ''}wrote {report_path}")
    for p in figs:
        print(f"[v3-p14-report] figure {p}")
    print(f"[v3-p14-report] main claim: pass {mc.get('pass')} on {mc.get('n_tasks')} tasks; "
          f"{len(warnings)} warnings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
