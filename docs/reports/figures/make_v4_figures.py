"""Bar plots for the v4 presentation and report: cost, task success, harm got through.

Numbers are copied from the final metrics files (predicate_correctness/output/logs/v4_{B2v4,B3v4,Hv4}_*_metrics.md,
"Arms, set all" tables). Run: python3 docs/reports/figures/make_v4_figures.py
"""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = os.path.dirname(os.path.abspath(__file__))
STEPS = ["B2'\nmain test", "B3'\nlong tasks", "H\nweak agent"]
ARMS = ["no guard", "TGR (frozen)", "v3", "v4 (ours)"]
COLORS = ["#b5b3ab", "#eb6834", "#1baf7a", "#2a78d6"]      # neutral gray, then palette slots 2, 3, 1
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"

DATA = {   # per step, in ARMS order
    "cost": ([0.66, 1.16, 0.89, 0.78], [1.35, 2.57, 1.81, 1.49], [1.15, 3.08, 1.94, 1.39]),        # cents
    "success": ([0.667, 0.657, 0.633, 0.673], [0.719, 0.719, 0.469, 0.750], [0.561, 0.480, 0.480, 0.622]),
    "harm": ([17.8, 16.8, 17.5, 19.2], [25.4, 25.4, 15.9, 23.8], [31.6, 24.5, 20.4, 18.4]),             # %
}
SPEC = {
    "cost": ("Cost per conversation (US cents, list price)", "{:.2f}", None),
    "success": ("Task success (share of conversations done right)", "{:.2f}", (0, 0.85)),
    "harm": ("Harmful writes that got through (% of conversations, lower is better)", "{:.1f}", None),
}


def plot(key: str) -> str:
    title, fmt, ylim = SPEC[key]
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    width, gap = 0.19, 0.01
    for j, (arm, color) in enumerate(zip(ARMS, COLORS)):
        xs = [i + (j - 1.5) * (width + gap) for i in range(len(STEPS))]
        vals = [DATA[key][i][j] for i in range(len(STEPS))]
        bars = ax.bar(xs, vals, width, color=color, edgecolor=SURFACE, linewidth=2, label=arm, zorder=3)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), fmt.format(v), ha="center", va="bottom",
                    fontsize=8, color=INK if j == 3 else INK2, fontweight="bold" if j == 3 else "normal")
    ax.set_xticks(range(len(STEPS)))
    ax.set_xticklabels(STEPS, fontsize=10, color=INK)
    ax.tick_params(axis="y", colors=MUTED, labelsize=8, length=0)
    ax.tick_params(axis="x", length=0)
    ax.yaxis.grid(True, color=GRID, linewidth=0.6, zorder=0)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    if ylim:
        ax.set_ylim(*ylim)
    else:
        ax.set_ylim(0, max(max(v) for v in DATA[key]) * 1.15)
    ax.set_title(title, loc="left", fontsize=12, color=INK, pad=28)
    ax.legend(ncol=4, loc="upper left", bbox_to_anchor=(0, 1.1), frameon=False, fontsize=9,
              labelcolor=INK2, handlelength=1.2, columnspacing=1.4)
    fig.tight_layout()
    path = os.path.join(OUT, f"v4_{key}.png")
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


if __name__ == "__main__":
    for k in DATA:
        print(plot(k))
