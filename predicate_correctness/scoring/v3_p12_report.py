"""Tracker v3 p12 step 6: write the p12 report (output/eval_v3/p12_report.md) and its 2 figures. $0.

No LLM call, no network, no guard or label code: it only reads the saved outputs of p12 and writes markdown + PNG.
Standard library, plus matplotlib for the figures (if it is missing, the figures are skipped and the report says so).

Order of the report (docs/planning/tracker_v3/p12.md step 6):
  1. the hold-out first (the result): P12.2, main counts, length split, tiny vs judge by question, the reviewer's
     verdicts, the recount (P12.3), unclear answers and failed quotes;
  2. the development bug check (marked "development check, not a result"): P12.1 before / after the K2 batch;
  3. cost and calls (p12a, the re-ask, p12b);
  4. a recommendation slot (left for the main chat).
A missing input gives a "not yet available" line for its section; the script still runs.

Inputs (defaults; every one can be changed with an option):
  hold-out   output/eval_v3/p12_holdout.json, p12_tiny_vs_judge_holdout.jsonl, p12_answers_holdout.md,
             p12_recount_holdout.md, p12_tiny_vs_judge_review_holdout.md
  dev        output/eval_v3/p12_devcheck*.json (every dev run found; before / after the K2 batch by its time),
             p12_answers_dev.md (p12a), p12_answers_dev_*.md (the re-ask), docs/planning/tracker_v3/k2_fix.md
  cost log   docs/planning/tracker_v3/approval_request.md (the "## Cost log" table)
Outputs:
  default    output/eval_v3/p12_report.md, docs/reports/figures/v3_tiny_llm_share.png, v3_tiny_disagreements.png
  --out-dir  all three in that folder (figures in <out-dir>/figures/)

Test mode (--test): needs --out-dir; every hold-out input must be given by option (dev files as stand-ins), a
hold-out input not given is "not yet available" and is never read; any input whose file name has "holdout" in it is
refused. Every heading and figure is marked TEST. --test-fill-json fills the hold-out-only parts (changes, audit,
LLM share) from p11's development JSON, so that code runs too (TEST only).

Run from predicate_correctness/:
  PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 /home/azureuser/miniconda3/bin/python3 -B scoring/v3_p12_report.py \
      > output/logs/v3_p12rep_run.log 2>&1
"""
from __future__ import annotations

import argparse
import collections
import glob
import hashlib
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

sys.dont_write_bytecode = True

PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(PC_DIR)
EV = os.path.join(PC_DIR, "output", "eval_v3")
PLAN = os.path.join(ROOT, "docs", "planning", "tracker_v3")
FIG_DIR = os.path.join(ROOT, "docs", "reports", "figures")
REPORT = os.path.join(EV, "p12_report.md")
FIG_SHARE = "v3_tiny_llm_share.png"
FIG_DIS = "v3_tiny_disagreements.png"

DEFAULTS = {
    "holdout_json": os.path.join(EV, "p12_holdout.json"),
    "holdout_cmp": os.path.join(EV, "p12_tiny_vs_judge_holdout.jsonl"),
    "holdout_answers": os.path.join(EV, "p12_answers_holdout.md"),
    "recount": os.path.join(EV, "p12_recount_holdout.md"),
    "review": os.path.join(EV, "p12_tiny_vs_judge_review_holdout.md"),
    "dev_answers": os.path.join(EV, "p12_answers_dev.md"),
    "k2fix": os.path.join(PLAN, "k2_fix.md"),
    "approval": os.path.join(PLAN, "approval_request.md"),
}
DEV_RUN_GLOB = os.path.join(EV, "p12_devcheck*.json")
REASK_GLOB = os.path.join(EV, "p12_answers_dev_*.md")
HOLDOUT_KEYS = ("holdout_json", "holdout_cmp", "holdout_answers", "recount", "review")

# The K2 batch of fixes was approved at 14:02 UTC (preregistration change log); a dev run written later is "after".
K2_BATCH_TIME = "2026-10-23 14:02 UTC"
# The first dev run (before the K2 batch), copied from output/eval_v3/p12_devcheck.json of 2026-10-23 13:44 UTC
# (rows sha256 ef5e3871…). Used only when that file has been overwritten by the re-run.
DEV_RUN1_SNAPSHOT = {
    "_label": "run 1 (built-in copy of p12_devcheck.json, 13:44 UTC; the file was overwritten)",
    "meta": {"when": "2026-10-23 13:44 UTC", "rows_sha256": "ef5e3871086c423043a221760602d2d3f60bc51b6f09579ba7c779383064996d"},
    "pass_marks": {"P11.1": {"pass": True}, "P11.2": {"pass": True}, "P11.3": {"pass": True, "bad": 0},
                   "P11.5": {"pass": True}, "missing_answers": {"pass": True, "missing": 0}, "all_pass": True},
    "data": {"conversations": 200, "checks": 2164, "saved_blocks": 32, "tiny_blocks": 207, "standin_blocks": 31,
             "tiny_vs_standin_changed": 184},
    "answers": {"used_status": {"no": 1340, "quote_failed": 4, "unclear": 38, "yes": 414}},
    "unclear_blocks": {"counts": {"only from an answer problem": 41}},
    "compare": {"counts": {"asked facts": 2030, "agree": 1818, "disagree": 211},
                "by_question": {"K1": {"disagree": 22}, "K2": {"disagree": 121}, "K3": {"disagree": 5},
                                "K4": {"disagree": 8}, "K5": {"disagree": 13}, "K8": {"disagree": 3},
                                "K9": {"disagree": 3}, "K12": {"disagree": 5}, "K13": {"disagree": 44},
                                "K15": {"disagree": 2}, "K16": {"disagree": 8}}},
    "changes_short": {"added": 180, "removed": 5},
}
CLASSES = ("good", "bad", "suspect", "reported_unwanted_allow", "undecided")
BINS = ("bin=<12k", "bin=12-24k", "bin=>24k")
PASS_IDS = (("P11.1", "state errors, fact errors, message fallbacks, guard errors: 0"),
            ("P11.2", "database facts vs τ-bench's tool: 0 disagreements"),
            ("P11.3", "new allows the tool refuses on a check mapped to a v3 fact: 0"),
            ("P11.5", "core structure facts: added blocks with no objective reason: 0"),
            ("missing_answers", "answers missing from the store: 0"))


# ----------------------------------------------------------------------------------------------- small helpers
def rel(p: str) -> str:
    """A path as the report shows it: relative to predicate_correctness/ or to code_projects/."""
    ap = os.path.abspath(p)
    for base in (PC_DIR, ROOT):
        if ap.startswith(base + os.sep):
            return os.path.relpath(ap, base)
    return ap


def sha256_file(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def read_text(p: Optional[str]) -> Optional[str]:
    if not p or not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return f.read()


def read_json(p: Optional[str]) -> Optional[Any]:
    t = read_text(p)
    return None if t is None else json.loads(t)


def read_jsonl(p: Optional[str]) -> Optional[List[dict]]:
    t = read_text(p)
    if t is None:
        return None
    return [json.loads(x) for x in t.splitlines() if x.strip()]


def g(d: Any, *keys: str, default: Any = None) -> Any:
    """Nested get: g(d, "a", "b") = d["a"]["b"], or default."""
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d


def n(x: Any) -> str:
    if x is None:
        return "-"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, int):
        return f"{x:,}"
    if isinstance(x, float):
        return f"{x:,.4f}".rstrip("0").rstrip(".") if abs(x) < 1000 else f"{x:,.0f}"
    return str(x)


def pct(a: Any, b: Any) -> str:
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or not b:
        return "-"
    return f"{100.0 * a / b:.1f} %"


def bound(x: Any) -> str:
    return "-" if not isinstance(x, (int, float)) else f"{x:.2e}"


def tbl(head: List[str], rows: List[List[Any]]) -> List[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        out.append("| " + " | ".join(n(x) if not isinstance(x, str) else x for x in r) + " |")
    return out


def qkey(q: str) -> Tuple[int, str]:
    m = re.match(r"K(\d+)", q or "")
    return (int(m.group(1)) if m else 999, q or "")


def not_yet(what: str, path: Optional[str]) -> str:
    where = f"`{rel(path)}` does not exist yet" if path else "no input given (test mode: hold-out inputs are not read)"
    return f"_Not yet available: {what} ({where})._"


def pf(x: Any) -> str:
    return "**PASS**" if x is True else "**FAIL**" if x is False else "-"


def answers_numbers(md: Optional[str]) -> Optional[dict]:
    """The '## Numbers (JSON)' block of a v3_p8_dryrun report (p12_answers_*.md)."""
    if md is None:
        return None
    m = re.search(r"## Numbers \(JSON\)\s*```(?:json)?\s*(\{.*?\})\s*```", md, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def answers_when(md: Optional[str]) -> Optional[str]:
    m = re.search(r"on (\d{4}-\d\d-\d\d \d\d:\d\d UTC)", md or "")
    return m.group(1) if m else None


# ----------------------------------------------------------------------------------------------- free-text inputs
def summary_lines(md: str, limit: int = 30) -> List[str]:
    """The section of md under the first heading with 'summary' or 'verdict' (else the first lines), quoted."""
    lines = md.splitlines()
    start, level = None, 0
    for i, ln in enumerate(lines):
        m = re.match(r"(#+)\s+(.*)", ln)
        if m and re.search(r"(?i)summary|verdict|result", m.group(2)) and i > 0:
            start, level = i, len(m.group(1))
            break
    if start is None:
        body = [x for x in lines if x.strip()][:limit]
    else:
        body = [lines[start]]
        for ln in lines[start + 1:]:
            m = re.match(r"(#+)\s", ln)
            if m and len(m.group(1)) <= level:
                break
            body.append(ln)
        body = [x for x in body if x.strip()][:limit]
    return ["> " + x for x in body]


def review_verdicts(md: str) -> Dict[str, int]:
    """Counts of 'verdict: <words>' lines (the reviewer's per-entry verdicts), normalised to lower case."""
    c: collections.Counter = collections.Counter()
    for ln in md.splitlines():
        m = re.search(r"(?i)\bverdict\b\**\s*[:=]\s*\**\s*([A-Za-z][A-Za-z0-9 _'/-]{0,40})", ln)
        if m:
            v = re.split(r"[.;,(*|]", m.group(1))[0].strip().lower()
            if v:
                c[v] += 1
    return dict(c.most_common())


def recount_verdict(md: str) -> Tuple[str, str]:
    """(verdict, how found): 'equal', 'not equal' or 'unclear' from the recount file's text."""
    for ln in md.splitlines():
        if "P12.3" in ln:
            if re.search(r"\bFAIL\b", ln):
                return "not equal", f"line with P12.3: {ln.strip()[:160]}"
            if re.search(r"\bPASS\b", ln):
                return "equal", f"line with P12.3: {ln.strip()[:160]}"
    neg = re.findall(r"(?i)\b(not equal|unequal|different|differs?|mismatch(?:es)?|disagree(?:s|ment)?)\b", md)
    pos = re.findall(r"(?i)\b(all equal|counts? (?:are )?equal|equal counts|match(?:es)? exactly|identical)\b", md)
    if pos and not neg:
        return "equal", f"words found: {sorted(set(x.lower() for x in pos))}"
    if neg and not pos:
        return "not equal", f"words found: {sorted(set(x.lower() for x in neg))}"
    return "unclear", f"no clear verdict in the text (equal words {len(pos)}, unequal words {len(neg)}): read it by hand"


# ----------------------------------------------------------------------------------------------- figures
def _plt():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        return plt
    except Exception:                                           # noqa: BLE001 - figures are optional
        return None


def fig_llm_share(ls: dict, path: str, tag: str) -> Optional[str]:
    plt = _plt()
    if plt is None:
        return "matplotlib is not installed"
    fz, v3 = ls.get("frozen") or {}, ls.get("v3") or {}
    groups = [("blocks with a value\nset by an LLM", "blocks with an LLM-set value", "blocks"),
              ("values behind blocks\nset by an LLM", "llm", "values")]
    fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=150)
    w = 0.36
    for i, (lab, num, den) in enumerate(groups):
        for j, (name, d, style) in enumerate((("frozen TGR (judge)", fz, dict(color="0.15", edgecolor="black")),
                                              ("v3 (tiny questions)", v3, dict(color="white", edgecolor="black",
                                                                                hatch="///")))):
            a, b = d.get(num, 0), d.get(den, 0)
            y = 100.0 * a / b if b else 0.0
            x = i + (j - 0.5) * w
            ax.bar(x, y, w * 0.92, label=name if i == 0 else None, linewidth=1.2, **style)
            ax.text(x, y + 1.5, f"{y:.0f} %\n({a:,} of {b:,})" if b else "n/a\n(no data)", ha="center",
                    va="bottom", fontsize=8.5)
    ax.set_xticks(range(len(groups)))
    ax.set_xticklabels([x[0] for x in groups], fontsize=9.5)
    ax.set_ylim(0, 135)
    ax.set_yticks(range(0, 101, 20))
    ax.set_ylabel("share (%)")
    ax.set_title(f"{tag}Hold-out: share of blocks decided by an LLM\nfrozen TGR (LLM judge) vs v3 (code + tiny questions)",
                 fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="0.85", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper center", ncol=2, fontsize=9)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return None


def fig_disagreements(rows: List[Tuple[str, int, int, int, int]], path: str, tag: str) -> Optional[str]:
    """rows: (question, tiny gives the blocking value, tiny gives the allowing value, direction unknown, asked)."""
    plt = _plt()
    if plt is None:
        return "matplotlib is not installed"
    if not rows:
        rows = [("(none)", 0, 0, 0, 0)]
    fig, ax = plt.subplots(figsize=(7.2, 0.42 * len(rows) + 1.9), dpi=150)
    ys = list(range(len(rows)))[::-1]
    segs = (("tiny gives the blocking value (stricter)", 1, dict(color="0.2", edgecolor="black")),
            ("tiny gives the allowing value (looser)", 2, dict(color="white", edgecolor="black", hatch="///")),
            ("direction not known", 3, dict(color="0.75", edgecolor="black", hatch="..")))
    left = [0] * len(rows)
    for name, k, style in segs:
        vals = [r[k] for r in rows]
        if not any(vals):
            continue
        ax.barh(ys, vals, 0.7, left=left, label=name, linewidth=1.0, **style)
        left = [a + b for a, b in zip(left, vals)]
    top = max(left) if max(left) else 1
    for y, r, tot in zip(ys, rows, left):
        ax.text(tot + top * 0.01, y, f"{tot}" + (f" of {r[4]:,} asked" if r[4] else ""), va="center", fontsize=8.5)
    ax.set_yticks(ys)
    ax.set_yticklabels([r[0] for r in rows])
    ax.set_xlim(0, top * 1.3)
    ax.set_xlabel("disagreements (facts where the tiny answer differs from the judge's saved answer)")
    ax.set_title(f"{tag}Hold-out: tiny answers vs the judge, disagreements by question", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", color="0.85", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="lower right", fontsize=8.5)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return None


# ----------------------------------------------------------------------------------------------- sections
class Ctx:
    def __init__(self, a: argparse.Namespace):
        self.a = a
        self.test = a.test
        self.tag = "TEST (development files as stand-ins) - " if a.test else ""
        self.out_dir = a.out_dir
        self.report = os.path.join(a.out_dir, "p12_report.md") if a.out_dir else REPORT
        self.fig_dir = os.path.join(a.out_dir, "figures") if a.out_dir else FIG_DIR
        self.inputs_used: List[str] = []

    def use(self, p: Optional[str]) -> None:
        if p and os.path.isfile(p) and os.path.abspath(p) not in self.inputs_used:
            self.inputs_used.append(os.path.abspath(p))


def h(ctx: Ctx, level: int, text: str) -> str:
    return f"{'#' * level} {'TEST - ' if ctx.test else ''}{text}"


def sec_holdout(ctx: Ctx, L: List[str]) -> None:
    a = ctx.a
    w = L.append
    w(h(ctx, 2, "1. The hold-out (the result)"))
    w("")
    if ctx.test:
        w("> **TEST.** The \"hold-out\" numbers below come from the development files given by option, not from the "
          "hold-out. They only test this script. They are not a result.")
        w("")
    hj = read_json(a.holdout_json)
    ctx.use(a.holdout_json)
    if hj is None:
        w(not_yet("the hold-out run (P12.2)", a.holdout_json))
        w("")
        hj = {}
    fill = read_json(a.test_fill_json) if ctx.test and a.test_fill_json else None
    filled = []
    if fill is not None:
        ctx.use(a.test_fill_json)
        for k in ("changes", "audit"):
            if k not in hj and k in fill:
                hj[k] = fill[k]
                filled.append(k)
        if "llm_share" not in hj and isinstance(fill.get("llm"), dict):      # p11's shape -> p12's shape (TEST)
            hj["llm_share"] = {gg: dict(g(fill, "llm", "values", gg, "all", default={}),
                                        **g(fill, "llm", "blocks", gg, "all", default={}))
                               for gg in ("frozen", "v3")}
            filled.append("llm_share")
        if filled:
            w(f"> **TEST:** {', '.join(filled)} are not in the development check's JSON; filled from "
              f"`{rel(a.test_fill_json)}` (p11, all development data, both agents) so this code runs. Their numbers come from another data set, so they "
              f"do not fit the other rows (e.g. frozen blocks above 100 % of checks). TEST only.")
            w("")
    d, pm, m = hj.get("data") or {}, hj.get("pass_marks") or {}, hj.get("meta") or {}
    if hj.get("data"):
        w(f"Input: `{rel(a.holdout_json)}` (written {m.get('when', '-')}, side `{hj.get('side', '-')}`). "
          f"{n(d.get('conversations'))} conversations, {n(d.get('checks'))} checks ({n(d.get('write_checks'))} write "
          f"checks). Per data set: " + ", ".join(f"{k} {n(g(d, 'conversations_by_dataset', k))} conv. / {n(v)} checks"
                                                 for k, v in (d.get("by_dataset") or {}).items()) + ".")
        w(f"$0 run: network events {n(m.get('network_events'))}, judge calls refused "
          f"{n(sum((m.get('judge_calls') or {}).values()))}, guard errors {len(m.get('errors') or [])}. Answers from the "
          f"store only (sha256 `{str(g(hj, 'store', 'sha256', default='-'))[:16]}…`, {n(g(hj, 'store', 'kept'))} answers).")
        w("")

    # P12.2
    w(h(ctx, 3, f"P12.2 (the zero-count marks on the hold-out): {pf(pm.get('all_pass')) if pm else '-'}"))
    w("")
    if pm:
        rows = []
        p1, p2, p3, p5, ma = (pm.get(k) or {} for k in ("P11.1", "P11.2", "P11.3", "P11.5", "missing_answers"))
        res = {
            "P11.1": f"state errors {n(p1.get('state_errors'))}, fact errors {n(p1.get('fact_errors'))}, message "
                     f"fallbacks {n(p1.get('message_fallbacks_rule'))}, guard errors "
                     f"{n(p1.get('guard_run_errors_all_arms'))}, checks with no tiny decision "
                     f"{n(p1.get('checks_without_tiny'))} (3/n: state {bound(p1.get('bound_state'))}, fact "
                     f"{bound(p1.get('bound_fact'))})",
            "P11.2": f"disagree {n(p2.get('disagree'))}, agree {n(p2.get('agree'))}, not decided by the tool "
                     f"{n(p2.get('not_decided'))} (3/n {bound(p2.get('bound'))})",
            "P11.3": f"bad {n(p3.get('bad'))} (order-blind {n(p3.get('bad_order_blind'))}) of "
                     f"{n(p3.get('new_allows_at_write_checks'))} new allows at write checks (3/n {bound(p3.get('bound'))})",
            "P11.5": f"without an objective reason {n(p5.get('without_reason'))} (added blocks with a core fact "
                     f"{n(p5.get('added_with_core_fact'))})",
            "missing_answers": f"missing {n(ma.get('missing'))}",
        }
        for k, txt in PASS_IDS:
            rows.append([k, txt, res[k], pf((pm.get(k) or {}).get("pass"))])
        L.extend(tbl(["id", "pass mark", "result", "pass"], rows))
        w("")
    else:
        w(not_yet("P12.2", a.holdout_json))
        w("")

    # main counts
    w(h(ctx, 3, "Main counts"))
    w("")
    if d:
        ls = hj.get("llm_share") or {}
        ch_all = g(hj, "changes", "counts", "all", "all", default=None)
        ch_first = g(hj, "changes", "counts", "first", "all", default={}) or {}
        cs = hj.get("changes_short") or {}
        checks = d.get("checks")
        fz_blocks = g(ls, "frozen", "blocks")
        rows = [["blocks: saved guard", d.get("saved_blocks"), pct(d.get("saved_blocks"), checks)],
                ["blocks: frozen TGR", fz_blocks, pct(fz_blocks, checks)],
                ["blocks: v3, judge stand-in", d.get("standin_blocks"), pct(d.get("standin_blocks"), checks)],
                ["**blocks: v3, tiny questions**", d.get("tiny_blocks"), pct(d.get("tiny_blocks"), checks)],
                ["allows: saved guard", None if checks is None else checks - d.get("saved_blocks", 0), ""],
                ["**allows: v3, tiny questions**", None if checks is None else checks - d.get("tiny_blocks", 0), ""],
                ["changed decisions vs the saved guard: added blocks",
                 (ch_all or {}).get("added", cs.get("added")),
                 f"first divergence {n(ch_first.get('added', cs.get('added (first divergence)')))}"],
                ["changed decisions vs the saved guard: removed blocks",
                 (ch_all or {}).get("removed", cs.get("removed")),
                 f"first divergence {n(ch_first.get('removed', cs.get('removed (first divergence)')))}"],
                ["conversations with a divergence", cs.get("conversations with a divergence"),
                 f"of {n(d.get('conversations'))}"],
                ["tiny vs stand-in: checks with a different decision", d.get("tiny_vs_standin_changed"), ""],
                ["checks where v3 asked at least one tiny question", g(hj, "answers", "checks_with_asks"),
                 pct(g(hj, "answers", "checks_with_asks"), checks)]]
        L.extend(tbl(["count", "n", "note"], rows))
        w("")
        top = sorted(((k[len("added at "):], v) for k, v in cs.items() if k.startswith("added at ")), key=lambda x: -x[1])
        if top:
            w("Added blocks by tool: " + ", ".join(f"{t} {v}" for t, v in top) + ".")
            w("")
        # classes
        cl = hj.get("classes") or {}
        if cl:
            rows = []
            for mode in ("exact", "order_blind"):
                for grp in ("all", "part=main", "part=stage_b"):
                    x = g(cl, mode, "counts", "all", grp, default=None)
                    if x is not None or grp == "all":
                        rows.append([grp, mode] + [(x or {}).get(k, 0) for k in CLASSES])
            w("Classes of the changed decisions (τ-bench's labels; \"bad\" = a new allow the tool refuses):")
            w("")
            L.extend(tbl(["group", "matcher", *CLASSES], rows))
            w("")
            for dd in (hj.get("class_detail") or [])[:15]:
                w(f"- {dd.get('cls')}: `{dd.get('ck')}` {dd.get('tool')} ({', '.join(dd.get('changed') or []) or '-'}; "
                  f"tool accepts: {dd.get('accepted')})")
            if hj.get("class_detail"):
                w("")
        # too strict
        au = hj.get("audit") or {}
        if au:
            rows = []
            for grd in ("saved", "frozen", "v2", "v3"):
                mn, sb = g(au, grd, "part=main", default={}) or {}, g(au, grd, "part=stage_b", default={}) or {}
                ts = mn.get("too_strict", 0) + sb.get("too_strict", 0)
                wc = mn.get("write checks", 0) + sb.get("write checks", 0)
                rows.append([("**v3 (tiny)**" if grd == "v3" else grd), mn.get("too_strict", 0),
                             mn.get("write checks", 0), sb.get("too_strict", 0), sb.get("write checks", 0), ts,
                             pct(ts, wc)])
            w("Too-strict blocks (p4's audit buckets, write checks only):")
            w("")
            L.extend(tbl(["guard", "main: too strict", "main: write checks", "stage B: too strict",
                          "stage B: write checks", "all: too strict", "share"], rows))
            w("")
        else:
            w("Too-strict blocks: " + ("not in this input (the audit buckets are made on the hold-out only)." if hj else
                                       "not yet available."))
            w("")
        # LLM share
        if ls:
            rows = []
            for grd, name in (("frozen", "frozen TGR (judge)"), ("v3", "v3 (tiny questions)")):
                x = ls.get(grd) or {}
                rows.append([name, x.get("blocks"), x.get("blocks with an LLM-set value"),
                             pct(x.get("blocks with an LLM-set value"), x.get("blocks")), x.get("values"),
                             x.get("llm"), pct(x.get("llm"), x.get("values")), x.get("code", 0),
                             x.get("not_asked", 0), x.get("blocking_value", 0)])
            w("Values behind blocks: set by an LLM or by code (frozen: the judge; v3: a tiny question):")
            w("")
            L.extend(tbl(["guard", "blocks", "blocks with an LLM-set value", "share", "values", "LLM-set", "share",
                          "code", "not asked", "blocking value"], rows))
            w("")
        else:
            w("LLM share: " + ("not in this input (made on the hold-out only)." if hj else "not yet available."))
            w("")
    else:
        w(not_yet("the main counts", a.holdout_json))
        w("")

    # length split
    w(h(ctx, 3, "Length split"))
    w("")
    ch = g(hj, "changes", "counts", default=None)
    if ch:
        rows = []
        for b in BINS:
            x, f = (ch.get("all") or {}).get(b, {}), (ch.get("first") or {}).get(b, {})
            ts3 = g(hj, "audit", "v3", f"part|bin=main|{b[4:]}", "too_strict")
            tss = g(hj, "audit", "saved", f"part|bin=main|{b[4:]}", "too_strict")
            rows.append([b[4:], x.get("checks", 0), x.get("added", 0), x.get("removed", 0), f.get("added", 0),
                         f.get("removed", 0), tss, ts3])
        L.extend(tbl(["history length", "checks", "added blocks", "removed blocks", "added (first div.)",
                      "removed (first div.)", "too strict, main: saved", "too strict, main: v3"], rows))
    else:
        w(not_yet("the length split", a.holdout_json) if not hj else
          "_Not in this input: the length split is made on the hold-out only._")
    w("")

    # tiny vs judge
    w(h(ctx, 3, "Tiny answers vs the judge's saved answers, by question"))
    w("")
    cmp_ = hj.get("compare") or {}
    items = read_jsonl(a.holdout_cmp)
    ctx.use(a.holdout_cmp)
    dis_rows: List[Tuple[str, int, int, int, int]] = []
    if cmp_:
        cc = cmp_.get("counts") or {}
        w(f"Asked facts {n(cc.get('asked facts'))}: agree {n(cc.get('agree'))}, **disagree {n(cc.get('disagree'))}** "
          f"({pct(cc.get('disagree'), cc.get('asked facts'))}); tiny gives the blocking value "
          f"{n(cc.get('disagree: tiny gives the blocking value', 0))}, the allowing value "
          f"{n(cc.get('disagree: tiny gives the allowing value', 0))}; the judge has no value "
          f"{n(cc.get('judge has no value (unknown or not asked)', 0))}.")
        w("")
        per_q: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        for it in items or []:
            for q in sorted({x.get("qid") for x in it.get("asks") or [] if x.get("qid")}, key=qkey) or ["(none)"]:
                c = per_q[q]
                c["n"] += 1
                c["blocked"] += int(bool(it.get("blocked")))
                dr = it.get("direction") or ""
                c["block" if "blocking" in dr else "allow" if "allowing" in dr else "unknown"] += 1
        rows = []
        for q, x in sorted((cmp_.get("by_question") or {}).items(), key=lambda kv: qkey(kv[0])):
            asked = sum(v for k, v in x.items() if not k.startswith("disagree:"))
            dq = x.get("disagree", 0)
            p = per_q.get(q)
            rows.append([q, asked, x.get("agree", 0), dq, pct(dq, asked),
                         p["blocked"] if p else "-", p["block"] if p else "-", p["allow"] if p else "-"])
            if dq:
                if p:
                    dis_rows.append((q, p["block"], p["allow"], p["unknown"], asked))
                else:
                    dis_rows.append((q, 0, 0, dq, asked))
        L.extend(tbl(["question", "asked facts", "agree", "disagree", "disagree share", "on a blocked check",
                      "tiny stricter", "tiny looser"], rows))
        w("")
        if items is None:
            w(f"_The per-entry file is not available ({not_yet('the disagreement list', a.holdout_cmp)}); direction "
              "by question is left out._")
        else:
            w(f"From `{rel(a.holdout_cmp)}`: {len(items):,} disagreements listed, "
              f"{sum(1 for x in items if x.get('blocked')):,} on a blocked check (the reviewer's list).")
        w("")
    else:
        w(not_yet("the tiny vs judge comparison", a.holdout_json))
        w("")
    ctx.dis_rows = dis_rows                                         # type: ignore[attr-defined]
    ctx.llm_share = hj.get("llm_share")                             # type: ignore[attr-defined]

    # reviewer
    w(h(ctx, 3, "The reviewer's verdicts (second opinion, against the policy text)"))
    w("")
    rv = read_text(a.review)
    ctx.use(a.review)
    if rv is None:
        w(not_yet("the reviewer's file", a.review))
    else:
        vc = review_verdicts(rv)
        w(f"From `{rel(a.review)}` (sha256 `{sha256_file(a.review)[:16]}…`). There is no objective label for \"is "
          "this a yes\"; this is a second opinion only.")
        w("")
        if vc:
            w("Verdict lines counted (\"verdict: ...\"; read automatically, check by hand):")
            w("")
            L.extend(tbl(["verdict", "n"], [[k, v] for k, v in vc.items()]))
        else:
            w("_No \"verdict: ...\" lines found; the reviewer's summary is copied below. Count by hand._")
        w("")
        w("The reviewer's summary (copied):")
        w("")
        L.extend(summary_lines(rv))
    w("")

    # recount
    w(h(ctx, 3, "The independent recount (P12.3)"))
    w("")
    rc = read_text(a.recount)
    ctx.use(a.recount)
    if a.recount_verdict:
        w(f"**P12.3: {'PASS (equal counts)' if a.recount_verdict == 'equal' else 'FAIL (counts differ)'}** "
          f"(set by the main chat with `--recount-verdict {a.recount_verdict}`).")
        w("")
    if rc is None:
        if not a.recount_verdict:
            w(not_yet("the recount", a.recount))
    else:
        v, how = recount_verdict(rc)
        if not a.recount_verdict:
            w(f"**P12.3: {'PASS (equal counts)' if v == 'equal' else 'FAIL (counts differ)' if v == 'not equal' else 'unclear: read the recount by hand'}** "
              f"(read automatically from `{rel(a.recount)}`; {how}).")
        else:
            w(f"Automatic reading of `{rel(a.recount)}`: {v} ({how}).")
        w("")
        w("The recount's summary (copied):")
        w("")
        L.extend(summary_lines(rc))
    w("")

    # answer problems
    w(h(ctx, 3, "Unclear answers and failed quotes"))
    w("")
    an = hj.get("answers") or {}
    if an:
        us = an.get("used_status") or {}
        tot = sum(us.values())
        w(f"Answers the tiny guard used: {n(an.get('used_keys'))} distinct (question, input) keys, {n(an.get('asks'))} "
          f"asks at {n(an.get('checks_with_asks'))} checks. **Unclear {n(us.get('unclear', 0))}** "
          f"({pct(us.get('unclear', 0), tot)}), **failed quotes {n(us.get('quote_failed', 0))}** "
          f"({pct(us.get('quote_failed', 0), tot)}), yes {n(us.get('yes', 0))}, no {n(us.get('no', 0))}. Each problem "
          f"takes the fact's blocking value.")
        w("")
        rows = []
        for q, x in sorted((an.get("used_by_question") or {}).items(), key=lambda kv: qkey(kv[0])):
            prob = sum(v for k, v in x.items() if k not in ("yes", "no"))
            if prob:
                rows.append([q, sum(x.values()), x.get("unclear", 0), x.get("quote_failed", 0),
                             prob - x.get("unclear", 0) - x.get("quote_failed", 0)])
        if rows:
            L.extend(tbl(["question", "used", "unclear", "failed quote", "other problem"], rows))
            w("")
        ub, tk = g(hj, "unclear_blocks", "counts", default={}) or {}, g(hj, "two_keys", "counts", default={}) or {}
        w(f"- Blocks only from an answer problem: **{n(ub.get('only from an answer problem', 0))}** (tiny blocks with "
          f"a fact set by an answer problem {n(ub.get('tiny blocks with a fact set by an answer problem', 0))}).")
        w(f"- Two-key disagreements (answers allow, code blocks): "
          f"{n(len(g(hj, 'two_keys', 'items', default=[]) or []))}; a question decided the block "
          f"{n(tk.get('the answers block, code open (a question decided the block)', 0))}.")
    else:
        w(not_yet("the answer problems", a.holdout_json))
    w("")


def dev_runs(ctx: Ctx) -> List[dict]:
    paths = ctx.a.dev_run or sorted(glob.glob(DEV_RUN_GLOB))
    runs = []
    for p in paths:
        if os.path.basename(p).endswith("_test.json"):
            continue
        j = read_json(p)
        if not j or not j.get("pass_marks"):
            continue
        ctx.use(p)
        j["_label"] = f"`{rel(p)}`"
        runs.append(j)
    if not any(g(r, "meta", "rows_sha256") == DEV_RUN1_SNAPSHOT["meta"]["rows_sha256"] for r in runs) and not any(
            g(r, "meta", "when", default="") < K2_BATCH_TIME for r in runs):
        runs.append(dict(DEV_RUN1_SNAPSHOT))
    runs.sort(key=lambda r: g(r, "meta", "when", default=""))
    return runs


def sec_dev(ctx: Ctx, L: List[str]) -> None:
    w = L.append
    w(h(ctx, 2, "2. The development bug check (development check, not a result)"))
    w("")
    w("> **Development check, not a result.** The facts and the tiny questions were designed on these 200 "
      "conversations (the first 50 of each of the 4 strong-agent development data sets). P12.1 only shows the code does "
      "what it says. Fixes were made here, on development data, before the hold-out.")
    w("")
    runs = dev_runs(ctx)
    if not runs:
        w(not_yet("the development check", DEV_RUN_GLOB))
        w("")
    else:
        head = ["run", "written", "K2 batch", "P12.1", "P11.1", "P11.2", "P11.3", "P11.5", "missing",
                "blocks: saved / stand-in / tiny", "tiny vs stand-in differ", "tiny vs judge disagree", "K2", "K13",
                "unclear", "failed quotes", "blocks only from a problem"]
        rows = []
        for r in runs:
            pm, d = r.get("pass_marks") or {}, r.get("data") or {}
            when = g(r, "meta", "when", default="")
            us = g(r, "answers", "used_status", default={}) or {}
            bq = g(r, "compare", "by_question", default={}) or {}
            rows.append([r["_label"], when, "before" if when < K2_BATCH_TIME else "after", pf(pm.get("all_pass")),
                         *(pf((pm.get(k) or {}).get("pass")) for k in ("P11.1", "P11.2", "P11.3", "P11.5",
                                                                        "missing_answers")),
                         f"{n(d.get('saved_blocks'))} / {n(d.get('standin_blocks'))} / {n(d.get('tiny_blocks'))}",
                         d.get("tiny_vs_standin_changed"), g(r, "compare", "counts", "disagree"),
                         g(bq, "K2", "disagree", default=0), g(bq, "K13", "disagree", default=0),
                         us.get("unclear", 0), us.get("quote_failed", 0),
                         g(r, "unclear_blocks", "counts", "only from an answer problem")])
        L.extend(tbl(head, rows))
        w("")
        if len(runs) == 1:
            w("_Only one development run found: the re-run after the K2 batch is not yet available._")
            w("")
        if any(r["_label"].startswith("run 1 (built-in") for r in runs):
            w("_Run 1's numbers are a built-in copy (its file was overwritten by the re-run); the copy's source rows "
              f"sha256 is `{DEV_RUN1_SNAPSHOT['meta']['rows_sha256'][:16]}…`._")
            w("")
    w(h(ctx, 3, "What was fixed, and why (the K2 batch, approved by the user on 2026-10-23)"))
    w("")
    kf = ctx.a.k2fix
    ctx.use(kf)
    w("- **Problem (run 1):** P12.1 passed, but the tiny guard was far stricter than the judge stand-in (207 vs 31 "
      "blocks). K2 made 121 of the 211 disagreements: K2 version 1 asked for every option of every item, so good "
      "listings got \"no\".")
    w("- **K2 version 2:** message A must state every argument of the call that the user can check, each in a form "
      "the user knows (an item by name or id, a card by kind and last four digits, ...). Prices and options that stay "
      "the same are not needed. Policy line S6.")
    w("- **Quote check:** ignores `**` / `__` marks and line breaks.")
    w("- **K5 and K4:** names, ids, orders and addresses count as the user's own unless the message says otherwise "
      "(the model saw one message and could not know whose data it was).")
    w("- **K13:** one sentence added (a message that asks for nothing new is no) and the policy's \"but nothing else\".")
    w("- **Evaluator:** an OR no longer stops at the first unclear part (the unclear part keeps its blocking value).")
    w("- Only the changed questions were re-asked, on the same 200 conversations. Fixed from the policy text and the "
      "tools' arguments, not from examples; logged in the pre-registration's change log before the hold-out.")
    if os.path.isfile(kf):
        w(f"- Source: `{rel(kf)}` (sha256 `{sha256_file(kf)[:16]}…`).")
    else:
        w(f"- Source: {not_yet('k2_fix.md', kf)}")
    w("")


def sec_cost(ctx: Ctx, L: List[str]) -> None:
    a = ctx.a
    w = L.append
    w(h(ctx, 2, "3. Cost and calls"))
    w("")
    reasks = a.reask_answers if a.reask_answers is not None else sorted(glob.glob(REASK_GLOB))
    steps = [("p12a (development sample, 200 conv.)", a.dev_answers)] + [
        (f"re-ask after the K2 batch ({os.path.basename(p)})", p) for p in reasks] + [
        ("p12b (hold-out, once)" + (" - TEST stand-in" if ctx.test else ""), a.holdout_answers)]
    rows, total, total_calls = [], 0.0, 0
    for name, p in steps:
        md = read_text(p)
        ctx.use(p)
        if md is None:
            rows.append([name, "-", "-", "-", "-", "-", "-", "not yet available" if p else "not read (TEST)"])
            continue
        num = answers_numbers(md) or {}
        r = num.get("real") or {}
        u = r.get("usage") or {}
        if r:
            total += float(r.get("spent_usd_list_price") or 0)
            total_calls += int(r.get("calls") or 0)
        rows.append([name, answers_when(md) or "-", r.get("calls"), r.get("saved_answers"),
                     f"${r['spent_usd_list_price']:.4f}" if "spent_usd_list_price" in r else "-",
                     f"${r['max_usd']}" if "max_usd" in r else "-",
                     f"{n(u.get('input_tokens'))} in / {n(u.get('output_tokens'))} out",
                     f"`{rel(p)}`" if r else f"`{rel(p)}` (no real-run numbers in it)"])
    if not reasks:
        rows.insert(1, ["re-ask after the K2 batch", "-", "-", "-", "-", "-", "-",
                        f"not yet available (no `{rel(REASK_GLOB)}`; or give `--reask-answers`)"])
    L.extend(tbl(["step", "written", "calls", "saved answers", "spent (list price)", "hard limit", "tokens", "source"],
                 rows))
    w("")
    w(f"Total from these reports: **{total_calls:,} calls, ${total:.4f}** (logged list price; gpt-6-luna, low effort)."
      + (" TEST: p12b here is the development report again, so the total counts p12a twice." if ctx.test else ""))
    w("")
    ap = read_text(a.approval)
    ctx.use(a.approval)
    if ap is None:
        w(not_yet("the cost log", a.approval))
    else:
        part = ap.split("## Cost log", 1)
        lines = [x for x in (part[1].splitlines() if len(part) == 2 else []) if x.startswith("|")]
        if lines:
            w(f"The cost log (copied from `{rel(a.approval)}`, every row):")
            w("")
            L.extend(lines)
        else:
            w(f"_No \"## Cost log\" table found in `{rel(a.approval)}`._")
    w("")


def sec_reco(ctx: Ctx, L: List[str]) -> None:
    w = L.append
    w(h(ctx, 2, "4. Recommendation on p13-p14 (for the main chat to fill)"))
    w("")
    w("> **TO FILL (main chat):** the recommendation on p13-p14, in 3-6 short lines: P12.2 / P12.3 result, how much "
      "stricter or looser v3 (tiny) is than the saved guard on the hold-out, the reviewer's view, and whether p14 "
      "should go ahead as planned. Then **STOP**: the user decides on p13.")
    w("")
    w("<!-- RECOMMENDATION-PLACEHOLDER: replace this block -->")
    w("")


def build(ctx: Ctx) -> str:
    a = ctx.a
    L: List[str] = []
    w = L.append
    title = "Tracker v3 p12: the report (tiny questions, no judge)"
    w(f"# {'TEST - ' if ctx.test else ''}{title}")
    w("")
    if ctx.test:
        w("> **TEST OUTPUT.** Made by `scoring/v3_p12_report.py --test` with development files standing in for the "
          "hold-out files. Nothing here is a result. The real report is `output/eval_v3/p12_report.md`.")
        w("")
    w(f"Written by `scoring/v3_p12_report.py` on {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. $0: it only "
      "reads saved files (no LLM call, no network). The hold-out comes first: it is the result. The development check "
      "comes second: it is a bug check, not a result.")
    w("")
    figs = []
    sec_holdout(ctx, L)
    # figures (hold-out)
    os.makedirs(ctx.fig_dir, exist_ok=True)
    tag = "TEST - " if ctx.test else ""
    fig_lines = [h(ctx, 3, "Figures (hold-out)"), ""]
    ls = getattr(ctx, "llm_share", None)
    p1 = os.path.join(ctx.fig_dir, FIG_SHARE)
    if ls:
        err = fig_llm_share(ls, p1, tag)
        fig_lines.append(f"_Figure not drawn: {err}._" if err else
                         f"![Share of blocks decided by an LLM: frozen TGR vs v3]({os.path.relpath(p1, os.path.dirname(ctx.report))})")
        if not err:
            figs.append(p1)
    else:
        fig_lines.append(f"_Not yet available: `{FIG_SHARE}` needs the hold-out's LLM share._")
    fig_lines.append("")
    dr = getattr(ctx, "dis_rows", [])
    p2 = os.path.join(ctx.fig_dir, FIG_DIS)
    if dr:
        err = fig_disagreements(dr, p2, tag)
        fig_lines.append(f"_Figure not drawn: {err}._" if err else
                         f"![Tiny answers vs the judge: disagreements by question]({os.path.relpath(p2, os.path.dirname(ctx.report))})")
        if not err:
            figs.append(p2)
    else:
        fig_lines.append(f"_Not yet available: `{FIG_DIS}` needs the hold-out's comparison._")
    fig_lines.append("")
    # put the figures right after the main counts section's end (before the dev check)
    L.extend(fig_lines)
    sec_dev(ctx, L)
    sec_cost(ctx, L)
    sec_reco(ctx, L)
    w(h(ctx, 2, "Inputs and command"))
    w("")
    rows = [[f"`{rel(p)}`", f"`{sha256_file(p)}`"] for p in ctx.inputs_used]
    rows.append([f"`{rel(os.path.abspath(__file__))}` (this script)", f"`{sha256_file(os.path.abspath(__file__))}`"])
    L.extend(tbl(["file read", "sha256"], rows))
    w("")
    w("Outputs: " + ", ".join(f"`{rel(p)}`" for p in [ctx.report] + figs) + ".")
    w("")
    w("Command (from `predicate_correctness/`): `PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 "
      "/home/azureuser/miniconda3/bin/python3 -B scoring/v3_p12_report.py " + " ".join(sys.argv[1:]) +
      " > output/logs/v3_p12rep_run.log 2>&1`")
    ctx.figs = figs                                                 # type: ignore[attr-defined]
    return "\n".join(L) + "\n"


# ----------------------------------------------------------------------------------------------- main
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="python3 -B scoring/v3_p12_report.py", description=__doc__.split("\n")[0])
    ap.add_argument("--holdout-json", default=None)
    ap.add_argument("--holdout-cmp", default=None, help="the tiny-vs-judge .jsonl (hold-out)")
    ap.add_argument("--holdout-answers", default=None, help="p12b's answers report (p12_answers_holdout.md)")
    ap.add_argument("--recount", default=None)
    ap.add_argument("--review", default=None)
    ap.add_argument("--recount-verdict", choices=("equal", "different"), default=None,
                    help="P12.3 set by hand (the main chat), when the recount file has no clear verdict")
    ap.add_argument("--dev-run", action="append", default=None, help="a dev check JSON (repeat); default: every "
                    "output/eval_v3/p12_devcheck*.json")
    ap.add_argument("--dev-answers", default=DEFAULTS["dev_answers"])
    ap.add_argument("--reask-answers", action="append", default=None, help="the re-ask's answers report (repeat); "
                    "default: every output/eval_v3/p12_answers_dev_*.md")
    ap.add_argument("--k2fix", default=DEFAULTS["k2fix"])
    ap.add_argument("--approval", default=DEFAULTS["approval"])
    ap.add_argument("--out-dir", default=None, help="write the report and figures here (tests)")
    ap.add_argument("--test", action="store_true", help="test mode: needs --out-dir; hold-out inputs only by option")
    ap.add_argument("--test-fill-json", default=None, help="TEST only: fill changes / audit / LLM share from p11's JSON")
    a = ap.parse_args(argv)
    if a.test:
        if not a.out_dir:
            ap.error("--test needs --out-dir (a test never writes the real report or the docs figures)")
        for p in [getattr(a, k) for k in HOLDOUT_KEYS] + (a.dev_run or []) + (a.reask_answers or []) + [
                a.dev_answers, a.test_fill_json]:
            if p and "holdout" in os.path.basename(p).lower():
                ap.error(f"--test refuses a hold-out file: {p}")
    else:
        if a.test_fill_json:
            ap.error("--test-fill-json is for --test only")
        for k in HOLDOUT_KEYS:
            if getattr(a, k) is None:
                setattr(a, k, DEFAULTS[k])
    if a.out_dir:
        a.out_dir = os.path.abspath(a.out_dir)
        if os.path.abspath(os.path.join(a.out_dir, "p12_report.md")) == os.path.abspath(REPORT) or \
                os.path.abspath(a.out_dir) == os.path.abspath(FIG_DIR):
            ap.error("--out-dir must not be the real report's or the figures' folder")
    return a


def main(argv: Optional[List[str]] = None) -> int:
    a = parse_args(argv)
    ctx = Ctx(a)
    md = build(ctx)
    os.makedirs(os.path.dirname(ctx.report), exist_ok=True)
    with open(ctx.report, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[p12 report] wrote {rel(ctx.report)}" + "".join(f", {rel(p)}" for p in ctx.figs)
          + (" (TEST)" if a.test else ""))
    print(f"[p12 report] inputs read: {len(ctx.inputs_used)}; " + "; ".join(rel(p) for p in ctx.inputs_used))
    return 0


if __name__ == "__main__":
    sys.exit(main())
