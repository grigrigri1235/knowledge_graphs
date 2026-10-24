"""Tracker v3, part 1 (scoring.v3_p1_gate0): Gate 0, the length per check, the task key and the hold-out split.

No LLM call and no network ($0). The network is blocked, every judge call fails, and writes go only under output/
(fork/rebuild_check.py safety_setup). main() first checks the eval v2 manifest (state_tracker/v3/frozen.py).

Gate 0 (preregistration.md P1.5): on every saved check of every data set of fork/offline_v3.py, the source guard
(frozen TGR or TGR + tracker) runs offline with the saved judge values (fork/offline_v3.py decide), and its
decision, margin (exact), violated rules (id, description, logic) and block-message bytes must equal the saved ones;
for TGR + tracker sources the tracker part too (judge values, tracker values, replaced, changed, lookup errors,
state counts). A cap-override check (the 4th try, run anyway, no message sent) counts on its decision only. Each
miss gets a class (fork/offline_v3.py miss_class): source_run_fallback, judge_retry (the two listed classes) or bug.
Pass: 0 bugs, and listed misses at most 0.5 % of the judged checks of each data set.

Also, per check: the history length as the judge's view measures it, its bin, the task key (domain, split, task id,
trial; P1.6: no check from the partner's test group), and the side (hold-out or development data).

Outputs (output/eval_v3/):
    p1_check_index.jsonl   one compact line per saved check (no histories, no messages)
    split.json             the conversation keys of the hold-out and of the development data, with counts
    p1_reproduction.md     the report

Run from predicate_correctness/ (the hash seed must be fixed):
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m scoring.v3_p1_gate0 --workers 2 \\
        > output/logs/v3_p1b_<nn>_gate0.log 2>&1
Standard library only (the venv Python is the one the guards ran with online). Never imports the scorer.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import multiprocessing
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

sys.dont_write_bytecode = True

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "scoring"

from fork import offline_v3 as O                                          # noqa: E402
from state_tracker import paths                                           # noqa: E402

OUT_DIR = os.path.join(paths.OUTPUT_DIR, "eval_v3")
INDEX = os.path.join(OUT_DIR, "p1_check_index.jsonl")
SPLIT = os.path.join(OUT_DIR, "split.json")
REPORT = os.path.join(OUT_DIR, "p1_reproduction.md")
CAP = 0.005                                                               # the hard cap per data set (0.5 %)
OWN_FILES = ("fork/offline_v3.py", "tests/test_v3_offline.py", "scoring/v3_p1_gate0.py")
EXAMPLES_PER_DATASET = 5
# Earlier $0 counts (output/logs/v3_crit_d_result.md, critic d's recount), shown next to ours.
EXPECTED = {"judged": 38579, "blocks": 4885, "cap_overrides": 415, "stage_b_judged": 3260,
            "bins_judged": (31168, 5779, 1632), "bins_blocks": (2973, 1318, 594)}


def say(msg: str) -> None:
    print(msg, flush=True)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ----------------------------------------------------------------------------------------------- one part
def check_row(ch: O.SavedCheck) -> Tuple[Dict[str, Any], Optional[str], Optional[Dict[str, Any]], Optional[str]]:
    """(index line, miss class or None, comparison or None, error text or None) of one saved check."""
    cmp, err = None, None
    try:
        res = O.decide(ch)
        cmp = O.compare_with_saved(ch, res)
    except Exception as e:  # noqa: BLE001 - counted as a miss (class bug unless a listed class applies)
        err = f"{type(e).__name__}: {e}"
    cls = O.miss_class(ch, cmp, err)
    n = ch.history_len()
    a = ch.attempt
    line = {"ckey": ch.ckey, "dataset": ch.dataset, "domain": ch.domain, "split": ch.conv.split,
            "task_id": ch.conv.task_id, "trial": ch.conv.trial, "agent": ch.conv.agent,
            "source_guard": ch.conv.saved_guard, "tool": ch.tool, "judged": ch.judged,
            "saved_decision": ch.saved_decision, "blocked": ch.blocked, "cap_override": ch.cap_override,
            "exec_step": a["exec_step"], "attempt": a["attempt"], "history_len": n, "bin": O.length_bin(n),
            "side": ch.side, "gate0": "pass" if cls is None else f"miss:{cls}"}
    if cls is not None:
        line["gate0_differs"] = cmp["differs"] if cmp is not None else ["error"]
    return line, cls, cmp, err


def process_part(task: Tuple[str, int, int, Optional[int]]) -> Dict[str, Any]:
    """Gate 0 on the conversations of one data set with ordinal % n == k (limit: at most that many of them)."""
    dataset, k, n, limit = task
    t0 = time.time()
    c: collections.Counter = collections.Counter()
    lines: List[Tuple[int, int, str]] = []
    misses: List[Dict[str, Any]] = []
    convs: List[Dict[str, Any]] = []
    line_counts: Dict[str, collections.Counter] = {}
    for conv in O.iter_conversations([dataset], part=(k, n), counts=line_counts):
        if limit is not None and len(convs) >= limit:
            break
        c["conversations"] += 1
        c[f"side {conv.side} conversations"] += 1
        c[f"split {conv.split} conversations"] += 1
        max_all, max_judged, n_checks = 0, None, 0
        for ch in conv.checks():
            line, cls, cmp, err = check_row(ch)
            lines.append((conv.ordinal, ch.check_idx, json.dumps(line, ensure_ascii=False, separators=(",", ":"))))
            n_checks += 1
            b = line["bin"]
            c["checks"] += 1
            c[f"side {conv.side} checks"] += 1
            c[f"bin checks {b}"] += 1
            max_all = max(max_all, line["history_len"])
            ok_all = cls is None
            if err is not None:
                c["errors"] += 1
            if not ch.judged:
                c["not judged"] += 1
                c["not judged reproduced"] += ok_all
                if cls is not None:
                    c[f"not judged miss {cls}"] += 1
                    if len(misses) < EXAMPLES_PER_DATASET:
                        misses.append(_example(ch, cls, cmp, err))
                continue
            max_judged = max(max_judged or 0, line["history_len"])
            c["judged"] += 1
            c[f"bin judged {b}"] += 1
            c["reproduced"] += ok_all
            if cmp is not None:
                m = cmp["main"]
                c["decision equal"] += m["decision"]
                c["margin equal"] += m["margin"]
                c["violated rules equal"] += m["violated_rules"]
                c["message equal (judged)"] += m["message"]
                c["all main fields equal"] += cmp["ok"]
                c["all main and extra fields equal"] += cmp["ok"] and not cmp["differs_extra"]
                if "tracker" in m:
                    c["tracker checks"] += 1
                    c["tracker equal"] += m["tracker"]
                for x in cmp["differs_extra"]:
                    c[f"extra field differs: {x}"] += 1
            if ch.cap_override:
                c["cap overrides"] += 1
                c["cap decision equal"] += bool(cmp and cmp["main"]["decision"])
                c["cap all main fields equal"] += bool(cmp and cmp["ok"])
            elif ch.blocked:
                c["blocks"] += 1
                c[f"bin blocks {b}"] += 1
                c["block message equal"] += bool(cmp and cmp["main"]["message"])
            else:
                c["allows"] += 1
            if cls is not None:
                c[f"miss {cls}"] += 1
                if len(misses) < EXAMPLES_PER_DATASET:
                    misses.append(_example(ch, cls, cmp, err))
        c[f"bin conversations {O.length_bin(max_all)}"] += 1
        if max_judged is not None:
            c[f"bin conversations (judged) {O.length_bin(max_judged)}"] += 1
        convs.append({"conv_key": conv.conv_key, "ordinal": conv.ordinal, "side": conv.side,
                      "task_key": list(conv.task_key), "checks": n_checks, "max_len": max_all})
    return {"dataset": dataset, "k": k, "n": n, "counts": dict(c), "lines": lines, "misses": misses, "convs": convs,
            "line_counts": {d: dict(v) for d, v in line_counts.items()}, "seconds": round(time.time() - t0, 1)}


def _example(ch: O.SavedCheck, cls: str, cmp: Optional[Dict[str, Any]], err: Optional[str]) -> Dict[str, Any]:
    out = {"ckey": ch.ckey, "class": cls, "tool": ch.tool, "saved_decision": ch.saved_decision,
           "cap_override": ch.cap_override, "error": err}
    if cmp is not None:
        out["differs"] = cmp["differs"]
        out["differs_extra"] = cmp["differs_extra"]
    return out


# ----------------------------------------------------------------------------------------------- the whole run
def _init_worker() -> None:
    from fork import rebuild_check as RC
    RC.safety_setup()


def run(datasets: Optional[List[str]] = None, workers: int = 2, limit: Optional[int] = None,
        log=say) -> Dict[str, Any]:
    """Gate 0 on the data sets (default all). Returns {parts: [...], seconds}. limit: conversations per part."""
    datasets = list(datasets or O.DATASETS)
    n = max(1, int(workers))
    tasks = [(d, k, n, limit) for d in datasets for k in range(n)]
    t0 = time.time()
    parts: List[Dict[str, Any]] = []
    if n == 1:
        for t in tasks:
            parts.append(process_part(t))
            log(f"[gate0] {t[0]} part {t[1]}/{t[2]}: {parts[-1]['counts'].get('checks', 0)} checks, "
                f"{parts[-1]['seconds']} s")
    else:
        ctx = multiprocessing.get_context("spawn")
        with ctx.Pool(n, initializer=_init_worker) as pool:
            for p in pool.imap_unordered(process_part, tasks):
                parts.append(p)
                log(f"[gate0] {p['dataset']} part {p['k']}/{p['n']}: {p['counts'].get('checks', 0)} checks, "
                    f"misses {sum(v for k_, v in p['counts'].items() if k_.startswith('miss '))}, {p['seconds']} s, "
                    f"{time.time() - t0:.0f} s since start")
    order = {d: i for i, d in enumerate(O.DATASETS)}
    parts.sort(key=lambda p: (order[p["dataset"]], p["k"]))
    return {"parts": parts, "seconds": round(time.time() - t0, 1), "datasets": datasets, "workers": n,
            "limit": limit}


def merge(res: Dict[str, Any]) -> Dict[str, Any]:
    """Counts per data set, conversations, line counts and miss examples of all parts."""
    by: Dict[str, collections.Counter] = collections.OrderedDict()
    convs: Dict[str, List[Dict[str, Any]]] = collections.OrderedDict()
    misses: Dict[str, List[Dict[str, Any]]] = collections.OrderedDict()
    line_counts: Dict[str, Dict[str, int]] = {}
    for p in res["parts"]:
        d = p["dataset"]
        by.setdefault(d, collections.Counter()).update(p["counts"])
        convs.setdefault(d, []).extend(p["convs"])
        misses.setdefault(d, []).extend(p["misses"])
        line_counts[d] = p["line_counts"].get(d, {})          # every part reads every line of the data set
    for d in convs:
        convs[d].sort(key=lambda x: x["ordinal"])
        misses[d] = misses[d][:EXAMPLES_PER_DATASET]
    return {"by": by, "convs": convs, "misses": misses, "line_counts": line_counts}


def index_lines(res: Dict[str, Any]) -> List[str]:
    order = {d: i for i, d in enumerate(O.DATASETS)}
    rows = []
    for p in res["parts"]:
        for ordinal, idx, text in p["lines"]:
            rows.append((order[p["dataset"]], ordinal, idx, text))
    rows.sort(key=lambda r: r[:3])
    return [r[3] for r in rows]


def task_key_checks(m: Dict[str, Any]) -> Dict[str, Any]:
    """Our 495 and the partner's 495: the same (domain, split, task, trial) keys, per run pair."""
    out = {}
    for ours, partner in O.PAIRS.items():
        a = {tuple(x["task_key"]) for x in m["convs"].get(f"ours.{ours}", [])}
        b = {tuple(x["task_key"]) for x in m["convs"].get(f"partner.{partner}", [])}
        if a or b:
            out[f"ours.{ours} = partner.{partner}"] = {"ours": len(a), "partner": len(b), "common": len(a & b),
                                                        "same": a == b}
    return out


def split_doc(m: Dict[str, Any]) -> Dict[str, Any]:
    sides = {O.HOLDOUT: [], O.DEV: []}
    by_ds: Dict[str, Dict[str, int]] = {}
    checks = collections.Counter()
    for d, cs in m["convs"].items():
        by_ds[d] = {O.HOLDOUT: 0, O.DEV: 0}
        for x in cs:
            sides[x["side"]].append(x["conv_key"])
            by_ds[d][x["side"]] += 1
            checks[x["side"]] += x["checks"]
    forks = collections.Counter(x["conv_key"].split("|", 1)[1].split("/")[0] for x in m["convs"].get("stage_b", [])
                                if x["side"] == O.HOLDOUT)
    return {"written_by": "scoring.v3_p1_gate0 (tracker v3 part 1, agent p1b)",
            "stage_b_holdout_forks": {f: {"tries": n} for f, n in sorted(forks.items())},
            "rule": "hold-out: the strong agent's val conversations (ours.p10_luna_val, partner.luna_val) and the "
                    "Stage B tries forked from one of them (fork run p10_luna_val or luna_val; the fork id contains "
                    "'luna_val'); development data: everything else (preregistration.md, Data split)",
            "key": "<dataset>|<conv_id> (the ckey without its check index)",
            "counts": {s: len(v) for s, v in sides.items()}, "checks": dict(checks), "by_dataset": by_ds,
            "holdout": {"count": len(sides[O.HOLDOUT]), "conversations": sides[O.HOLDOUT]},
            "dev": {"count": len(sides[O.DEV]), "conversations": sides[O.DEV]}}


# ----------------------------------------------------------------------------------------------- the report
def _f(n: Any) -> str:
    return f"{n:,}" if isinstance(n, int) else str(n)


def gate_rows(m: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for d, c in m["by"].items():
        listed = sum(c.get(f"miss {k}", 0) for k in O.LISTED_MISS_CLASSES)
        bug = c.get("miss bug", 0) + c.get("not judged miss bug", 0)
        judged = c.get("judged", 0)
        share = listed / judged if judged else 0.0
        rows.append({"dataset": d, "c": c, "listed": listed, "bug": bug, "share": share,
                     "pass": bug == 0 and share <= CAP and c.get("errors", 0) == 0})
    return rows


def write_report(path: str, res: Dict[str, Any], m: Dict[str, Any], tk: Dict[str, Any], sp: Dict[str, Any],
                 shas: Dict[str, str], argv: List[str], manifest_info: Any) -> None:
    rows = gate_rows(m)
    L: List[str] = []
    w = L.append
    w("# Tracker v3, part 1: Gate 0, length per check, task key and split")
    w("")
    w(f"Written by `scoring.v3_p1_gate0` (agent p1b) on {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. "
      "No LLM call and no network ($0): the network was blocked, every judge call was set to fail, and writes "
      "were allowed only under `output/`. The eval v2 manifest was checked first "
      f"(`state_tracker/v3/frozen.py check_manifest`: {manifest_info}).")
    w("")
    allpass = all(r["pass"] for r in rows)
    tot = collections.Counter()
    for d, c in m["by"].items():
        if d != "stage_b":
            tot.update(c)
    sb = m["by"].get("stage_b", collections.Counter())
    w("## Summary")
    w(f"- **P1.5 Gate 0: {'PASS' if allpass else 'FAIL'}.** "
      f"Stage A + ours + the partner's: {_f(tot['reproduced'])} of {_f(tot['judged'])} judged checks reproduced "
      f"({_f(tot['blocks'])} blocks, {_f(tot['cap overrides'])} cap overrides); Stage B after the forks: "
      f"{_f(sb['reproduced'])} of {_f(sb['judged'])}. Bugs (unlisted misses): "
      f"{sum(r['bug'] for r in rows)}. Listed misses: {sum(r['listed'] for r in rows)}.")
    w(f"- **P1.6 task key: {'PASS' if tk.get('test_group_checks', 0) == 0 else 'FAIL'}.** "
      f"{tk.get('test_group_checks', 0)} checks from the partner's test group (the iterator raises on one). "
      "Our 495 and the partner's 495 are the same (task, trial) pairs: "
      f"{'yes' if tk['pairs'] and all(v['same'] for v in tk['pairs'].values()) else 'NO'}.")
    w(f"- Expected counts (critic d, `output/logs/v3_crit_d_result.md`): judged {_f(EXPECTED['judged'])}, blocks "
      f"{_f(EXPECTED['blocks'])}, cap overrides {_f(EXPECTED['cap_overrides'])}, Stage B judged "
      f"{_f(EXPECTED['stage_b_judged'])}. Ours: {_f(tot['judged'])}, {_f(tot['blocks'])}, "
      f"{_f(tot['cap overrides'])}, {_f(sb['judged'])}.")
    w(f"- Run: {res['workers']} worker processes, {res['seconds']} s"
      + (f", at most {res['limit']} conversations per part (NOT the full run)" if res.get("limit") else "") + ".")
    w("")
    w("## Gate 0 per data set")
    w("Judged = the guard record has judge values (`guard.judge` not empty). Blocks = judged checks that were "
      "blocked and whose message was sent (cap overrides apart). Reproduced = judged checks whose decision, margin "
      "(exact float), violated rules (id, description, logic) and block-message bytes equal the saved ones, and, "
      "for TGR + tracker sources, the tracker part too; a cap override counts on its decision only. "
      f"Pass: 0 bugs and listed misses at most {CAP:.1%} of the judged checks.")
    w("")
    w("| data set | conv. | checks | judged | blocks | cap overr. | reproduced | decision | margin | violated rules "
      "| block messages | tracker | cap decision | miss: bug | miss: source-run fallback | miss: judge retry "
      "| listed share | pass |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        c = r["c"]
        tr = f"{_f(c['tracker equal'])} / {_f(c['tracker checks'])}" if c.get("tracker checks") else "-"
        w(f"| {r['dataset']} | {_f(c['conversations'])} | {_f(c['checks'])} | {_f(c['judged'])} | {_f(c['blocks'])} "
          f"| {_f(c['cap overrides'])} | {_f(c['reproduced'])} | {_f(c['decision equal'])} | {_f(c['margin equal'])} "
          f"| {_f(c['violated rules equal'])} | {_f(c['block message equal'])} / {_f(c['blocks'])} | {tr} "
          f"| {_f(c['cap decision equal'])} / {_f(c['cap overrides'])} | {r['bug']} | "
          f"{c.get('miss source_run_fallback', 0)} | {c.get('miss judge_retry', 0)} | {r['share']:.2%} | "
          f"{'pass' if r['pass'] else 'FAIL'} |")
    w(f"| **Stage A + ours + partner** | {_f(tot['conversations'])} | {_f(tot['checks'])} | {_f(tot['judged'])} | "
      f"{_f(tot['blocks'])} | {_f(tot['cap overrides'])} | {_f(tot['reproduced'])} | {_f(tot['decision equal'])} | "
      f"{_f(tot['margin equal'])} | {_f(tot['violated rules equal'])} | {_f(tot['block message equal'])} / "
      f"{_f(tot['blocks'])} | {_f(tot['tracker equal'])} / {_f(tot['tracker checks'])} | "
      f"{_f(tot['cap decision equal'])} / {_f(tot['cap overrides'])} | {tot['miss bug']} | "
      f"{tot['miss source_run_fallback']} | {tot['miss judge_retry']} | | |")
    w("")
    w("Checks that are not judged (no rules for the action, or no predicate): the guard allows without a judge "
      "call; offline it must give the same record.")
    w("")
    w("| data set | not judged | reproduced | all main and extra fields equal (judged) | cap overrides: all fields "
      "equal | errors |")
    w("|---|---|---|---|---|---|")
    for r in rows:
        c = r["c"]
        w(f"| {r['dataset']} | {_f(c['not judged'])} | {_f(c['not judged reproduced'])} | "
          f"{_f(c['all main and extra fields equal'])} / {_f(c['judged'])} | {_f(c['cap all main fields equal'])} / "
          f"{_f(c['cap overrides'])} | {c['errors']} |")
    extra = sorted({k for c in m["by"].values() for k in c if k.startswith("extra field differs")})
    w("")
    w("Extra fields (reported, not part of the pass mark): every value with its evidence and source (`judge`), "
      "`trace_position`, `circuit`, `matched`, `mln`, `unknown_predicates`, `allowed_eps0`, and the saved "
      "`feedback_text`. " + ("Differences: " + "; ".join(
          f"{k[len('extra field differs: '):]} {sum(c.get(k, 0) for c in m['by'].values())}" for k in extra)
          if extra else "They are equal on every judged check."))
    w("")
    w("Earlier reproductions (eval v2): 5,793 / 5,793 and 7,555 / 7,555 decisions (Stage A tracker, "
      "`output/eval_v2/stage_a_runs.md`), 4,903 / 4,903 decisions and 417 / 417 messages "
      "(`output/p10_guard_offline_check.md`, `output/p10_audit.md`).")
    w("")
    w("## Misses by class")
    any_miss = False
    for d, ex in m["misses"].items():
        for e in ex:
            any_miss = True
            w(f"- `{e['ckey']}` ({d}): class {e['class']}, tool {e['tool']}, saved {e['saved_decision']}"
              f"{', cap override' if e['cap_override'] else ''}; differs: {', '.join(e.get('differs') or []) or '-'}"
              f"{'; error: ' + e['error'] if e.get('error') else ''}")
    if not any_miss:
        w("None: every saved check was reproduced. Classes kept ready: `source_run_fallback` (our p10 online runs; "
          "the saved tracker part shows a lookup or state error, so the judge's value was used), `judge_retry` "
          "(the guard record shows more than one try), `bug` (anything else).")
    w("")
    w("## Length per check")
    w("`len(render_history(executed[:executed_prefix_len]))` (runner copy `repro_core.taubench_steps`, no "
      "max_chars), as the judge's view measures it before its 24,000-character cut (`method_tgr/runtime.py` lines "
      "43 and 127). Bins: `<12k` (< 12,000), `12-24k` (12,000-24,000, not cut), `>24k` (> 24,000, cut). "
      "Conversations: the bin of their largest check (over all their checks; Stage B: the checks after the fork).")
    w("")
    w("| data set | checks <12k / 12-24k / >24k | judged | blocks | conversations |")
    w("|---|---|---|---|---|")
    totb = collections.Counter()
    for d, c in m["by"].items():
        def b3(kind: str) -> str:
            return " / ".join(_f(c.get(f"bin {kind} {b}", 0)) for b in O.BINS)
        if d != "stage_b":
            for kind in ("checks", "judged", "blocks", "conversations"):
                for b in O.BINS:
                    totb[f"{kind} {b}"] += c.get(f"bin {kind} {b}", 0)
        w(f"| {d} | {b3('checks')} | {b3('judged')} | {b3('blocks')} | {b3('conversations')} |")
    w("| **Stage A + ours + partner** | " + " | ".join(
        " / ".join(_f(totb[f'{kind} {b}']) for b in O.BINS) for kind in ("checks", "judged", "blocks",
                                                                         "conversations")) + " |")
    w("")
    w(f"Expected judged bins (critic d): {' / '.join(_f(x) for x in EXPECTED['bins_judged'])}; blocks: "
      f"{' / '.join(_f(x) for x in EXPECTED['bins_blocks'])}.")
    w("")
    w("## Task key and split")
    w("Task key on every check: (domain, split, task id, trial). Split names: `tau_train` (Stage A: τ-bench's own "
      "train task file), `partner_train` / `partner_val` (the partner's split, `from_shieldagent/splits/splits.json`, "
      "of τ-bench's test task file). Stage B tries take the task key of their source conversation (trial = the "
      "source trial).")
    w("")
    w("| data set | tau_train | partner_train | partner_val | hold-out conv. | dev conv. | hold-out checks | dev "
      "checks |")
    w("|---|---|---|---|---|---|---|---|")
    for d, c in m["by"].items():
        w(f"| {d} | {_f(c.get('split tau_train conversations', 0))} | {_f(c.get('split partner_train conversations', 0))}"
          f" | {_f(c.get('split partner_val conversations', 0))} | {_f(c.get('side holdout conversations', 0))} | "
          f"{_f(c.get('side dev conversations', 0))} | {_f(c.get('side holdout checks', 0))} | "
          f"{_f(c.get('side dev checks', 0))} |")
    w("")
    w(f"- Split (`output/eval_v3/split.json`): hold-out {_f(sp['counts'][O.HOLDOUT])} conversations "
      f"({_f(sp['checks'].get(O.HOLDOUT, 0))} checks), development {_f(sp['counts'][O.DEV])} conversations "
      f"({_f(sp['checks'].get(O.DEV, 0))} checks). Rule: {sp['rule']}.")
    w("- Stage B tries in the hold-out (forked from a val conversation): " + ("; ".join(
        f"`{f}`: {v['tries']} tries" for f, v in sp["stage_b_holdout_forks"].items()) or "none") + ".")
    w("- Our 495 vs the partner's 495, per run pair (domain, split, task, trial): " + "; ".join(
        f"{k}: {v['ours']} / {v['partner']}, common {v['common']}, same {v['same']}" for k, v in tk["pairs"].items()))
    w(f"- Partner's test group: {tk.get('test_group_checks', 0)} checks (the run would stop with "
      "ForbiddenTestGroup on the first one).")
    w("")
    w("Line counts per data set (the line rule of `fork/offline_v3.py`): " + "; ".join(
        f"{d}: " + ", ".join(f"{k} {v}" for k, v in sorted(lc.items())) for d, lc in m["line_counts"].items()) + ".")
    w("")
    w("## The check key")
    w("`ckey = \"<dataset>|<conv_id>|<check_idx>\"`.")
    w("- dataset: `stage_a.<luna|nano>.<tgr_frozen|tgr_tracker>`, `ours.<p10_luna_train|p10_nano_train|"
      "p10_luna_val>`, `partner.<luna_train_v5|nano_train|luna_val>`, `stage_b`.")
    w("- conv_id: episode files `<domain>/<task_index>/<trial>` (unique per data set after the line rule: the first "
      "good line per (domain, task_split, task, trial) is kept, error lines are dropped; 0 duplicates, so no shard "
      "is needed); Stage B `<fork_id>/<A|B>/<try>`.")
    w("- check_idx: the 0-based index of the attempt in the saved record's `attempts` list. Every attempt is one "
      "guard check (asserted: every attempt has a guard record), in the order the guard made them, judged or not. "
      "The agent's message is `messages[2 + 2 * check_idx]`, the history `executed[:attempts[check_idx]"
      ".executed_prefix_len]`. Stage B: the index into the try's `attempts` list, which starts with the source "
      "conversation's attempts before the fork and the fork attempt; only the attempts after the fork "
      "(`fork_part` \"after\") are checks of the try.")
    w("- To join: `ckey.rsplit('|', 1)` gives the conversation key (as in `split.json`) and the attempt index.")
    w("")
    w("## Files")
    w("| file | sha256 |")
    w("|---|---|")
    for k, v in shas.items():
        w(f"| `{k}` | `{v}` |")
    w("")
    w("## Commands")
    w("```")
    w("cd predicate_correctness")
    w("PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m scoring.v3_p1_gate0 "
      "--workers 2 > output/logs/v3_p1b_<nn>_gate0.log 2>&1")
    w("python3 -B -m unittest tests.test_v3_offline -v > output/logs/v3_p1b_<nn>_tests.log 2>&1")
    w("python3 -B -m unittest discover -s tests -t . > output/logs/v3_p1b_<nn>_suite.log 2>&1")
    w("```")
    w(f"This run: `{' '.join(argv)}`.")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    os.replace(path + ".tmp", path)


# ----------------------------------------------------------------------------------------------- main
def write_outputs(res: Dict[str, Any], argv: List[str], manifest_info: Any, out_dir: str = OUT_DIR
                  ) -> Dict[str, Any]:
    m = merge(res)
    os.makedirs(out_dir, exist_ok=True)
    index, split, report = (os.path.join(out_dir, os.path.basename(p)) for p in (INDEX, SPLIT, REPORT))
    lines = index_lines(res)
    with open(index + ".tmp", "w", encoding="utf-8") as f:
        for text in lines:
            f.write(text + "\n")
    os.replace(index + ".tmp", index)
    sp = split_doc(m)
    with open(split + ".tmp", "w", encoding="utf-8") as f:
        json.dump(sp, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(split + ".tmp", split)
    # every conversation's split went through offline_v3.split_name, which raises on the partner's test group; this
    # count is the second look (a split name other than the three allowed ones)
    bad = sum(x["checks"] for cs in m["convs"].values() for x in cs if x["task_key"][1] not in O.SPLIT_NAMES)
    tk = {"pairs": task_key_checks(m), "test_group_checks": bad}
    shas = {f: sha256_file(os.path.join(paths.PC_DIR, f)) for f in OWN_FILES
            if os.path.exists(os.path.join(paths.PC_DIR, f))}
    shas[O.rel(index)] = sha256_file(index)
    shas[O.rel(split)] = sha256_file(split)
    write_report(report, res, m, tk, sp, shas, argv, manifest_info)
    return {"merged": m, "task_keys": tk, "split": sp, "sha256": shas, "index_lines": len(lines)}


def main(argv: Optional[List[str]] = None) -> int:
    from state_tracker.v3.frozen import check_manifest
    manifest_info = check_manifest()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--workers", type=int, default=2, help="worker processes (at most 2 on this machine)")
    ap.add_argument("--datasets", default=None, help="comma list (default: all)")
    ap.add_argument("--limit", type=int, default=None, help="at most this many conversations per part (smoke)")
    ap.add_argument("--out-dir", default=OUT_DIR)
    a = ap.parse_args(argv)
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise SystemExit("set PYTHONHASHSEED=0 (the hash seed must be fixed before Python starts)")
    from fork import rebuild_check as RC
    RC.safety_setup()
    datasets = a.datasets.split(",") if a.datasets else None
    say(f"[gate0] manifest: {_short(manifest_info)}")
    res = run(datasets, workers=a.workers, limit=a.limit)
    out = write_outputs(res, [os.path.basename(sys.executable)] + ["-m", "scoring.v3_p1_gate0"] + list(
        argv if argv is not None else sys.argv[1:]), _short(manifest_info), a.out_dir)
    rows = gate_rows(out["merged"])
    for r in rows:
        c = r["c"]
        say(f"[gate0] {r['dataset']}: judged {c.get('judged', 0)}, reproduced {c.get('reproduced', 0)}, bug "
            f"{r['bug']}, listed {r['listed']} ({r['share']:.2%}), {'pass' if r['pass'] else 'FAIL'}")
    say(f"[gate0] pairs: {out['task_keys']['pairs']}")
    say(f"[gate0] split: {out['split']['counts']}, checks {out['split']['checks']}")
    say(f"[gate0] index lines {out['index_lines']}; sha256 {out['sha256']}")
    say(f"[gate0] done in {res['seconds']} s: {'PASS' if all(r['pass'] for r in rows) else 'FAIL'}")
    return 0 if all(r["pass"] for r in rows) else 1


def _short(info: Any) -> str:
    """A short text for the manifest check's return value."""
    if isinstance(info, (dict, list, tuple)):
        return f"ok ({len(info)} entries)"
    return "ok" if info is None else f"ok ({str(info)[:120]})"


if __name__ == "__main__":
    sys.exit(main())
