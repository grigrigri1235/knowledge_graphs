"""Eval v2 report figures (main chat; reads output/logs/v2_report_numbers.json; no LLM).

  /home/azureuser/miniconda3/bin/python3 -B -m scoring.v2_report_figures
Writes docs/reports/figures/tracker_eval_v2_effects.png and tracker_eval_v2_changed_values.png.
"""
from __future__ import annotations

import json
import os
import sys

sys.dont_write_bytecode = True
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG = os.path.join(os.path.dirname(PC), "docs", "reports", "figures")
SURFACE, INK, INK2, GRID, SERIES = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6"


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=10)
    ax.xaxis.grid(True, color=GRID, linewidth=1)
    ax.set_axisbelow(True)


def forest(ax, rows, title, xlabel, xlim):
    style(ax)
    ys = list(range(len(rows)))[::-1]
    ax.axvline(0, color=INK2, linewidth=1.2, linestyle="--")
    for y, (label, mean, lo, hi, note) in zip(ys, rows):
        ax.plot([lo, hi], [y, y], color=SERIES, linewidth=2, solid_capstyle="round")
        ax.plot([mean], [y], "o", color=SERIES, markersize=9, markeredgecolor=SURFACE, markeredgewidth=2)
        ax.text(1.02, y, f"{mean:+.3f}\n[{lo:+.3f}, {hi:+.3f}]", transform=ax.get_yaxis_transform(),
                va="center", ha="left", fontsize=9.5, color=INK, clip_on=False)
        ax.text(xlim[0], y - 0.32, note, va="center", fontsize=8.5, color=INK2)
    ax.set_yticks(ys)
    ax.set_yticklabels([r[0] for r in rows], fontsize=10.5, color=INK)
    ax.set_ylim(-0.8, len(rows) - 0.4)
    ax.set_xlim(*xlim)
    ax.set_xlabel(xlabel, fontsize=10, color=INK2)
    ax.set_title(title, fontsize=11.5, color=INK, loc="left", pad=10)


def main():
    with open(os.path.join(PC, "output", "logs", "v2_report_numbers.json"), encoding="utf-8") as f:
        n = json.load(f)
    os.makedirs(FIG, exist_ok=True)
    a, b = n["stage_a"], n["stage_b_partial"]
    s, w = a["strong (luna-dev)"], a["weak (nano-agent-luna)"]

    fig, axes = plt.subplots(1, 2, figsize=(13, 3.6), facecolor=SURFACE, gridspec_kw={"wspace": 0.75})
    forest(axes[0], [
        ("strong agent", s["diff_tracker_minus_frozen"], *s["diff_range_95"], "500 tasks, paired"),
        ("weak agent", w["diff_tracker_minus_frozen"], *w["diff_range_95"], "500 tasks, paired"),
    ], "Stage A: task success, tracker minus frozen TGR", "difference in task success (per task)", (-0.12, 0.12))
    forest(axes[1], [
        ("strong agent", b["strong"]["effect_B_minus_A"], *b["strong"]["range_95"],
         f"{b['strong']['forks']} forks, about {b['strong']['mean_tries_per_branch']:.0f} tries per branch"),
        ("weak agent", b["weak"]["effect_B_minus_A"], *b["weak"]["range_95"],
         f"{b['weak']['forks']} forks, about {b['weak']['mean_tries_per_branch']:.0f} try per branch (stopped early)"),
    ], "Stage B: effect of one changed decision (B minus A)", "difference in task success (per fork)", (-0.9, 0.9))
    fig.text(0.01, 0.01, "Dots: mean. Lines: 95 % bootstrap range. Dashed line: no effect.", fontsize=8.5,
             color=INK2)
    fig.subplots_adjust(left=0.09, right=0.88, bottom=0.24, top=0.85)
    fig.savefig(os.path.join(FIG, "tracker_eval_v2_effects.png"), dpi=150, facecolor=SURFACE)

    preds = w["changed_values_by_predicate_tracker_side"]
    names = list(preds)[:6][::-1]
    fig, ax = plt.subplots(figsize=(9, 3.4), facecolor=SURFACE)
    style(ax)
    ax.barh(range(len(names)), [preds[k] for k in names], color=SERIES, height=0.6, edgecolor=SURFACE,
            linewidth=2)
    for i, k in enumerate(names):
        ax.text(preds[k] + 6, i, str(preds[k]), va="center", fontsize=9.5, color=INK)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=9.5, color=INK)
    ax.set_xlabel("guard checks where the tracker changed the judge's value", fontsize=10,
                  color=INK2)
    ax.set_title("Weak agent, Stage A: which facts the tracker changed", fontsize=11.5, color=INK, loc="left",
                 pad=10)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG, "tracker_eval_v2_changed_values.png"), dpi=150, facecolor=SURFACE)
    print("ok", FIG)


if __name__ == "__main__":
    main()
