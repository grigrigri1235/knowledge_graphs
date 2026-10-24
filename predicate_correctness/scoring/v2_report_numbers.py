"""Eval v2 report numbers (main chat; standard library, read only, no LLM, no gold code).

Stage A: task success per guard and the paired difference (tracker - frozen) per agent, with a 95 % bootstrap range
over tasks; where the tracker changed values and decisions; the gift-card "unknown -> false" case.
Stage B (stopped early): finished tries per branch, and the mean effect per fork (B - A) over forks with tries in both
branches, with a bootstrap range over forks. Spend from guard/soft_stop.py.

Run from predicate_correctness/:
  /home/azureuser/miniconda3/bin/python3 -B -m scoring.v2_report_numbers > output/logs/v2_report_numbers.json
"""
from __future__ import annotations

import collections
import glob
import json
import os
import random
import sys

sys.dont_write_bytecode = True
PC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PC)

from guard import soft_stop  # noqa: E402

EVAL = os.path.join(PC, "output", "eval_v2")
GIFT = "gift_card_balance_covers_price_difference"
SEED = 20261022
N_BOOT = 10000


def val(v):
    """A predicate value as 'true' / 'false' / 'unknown' (values may be stored as dicts, bools or strings)."""
    if isinstance(v, dict):
        v = v.get("value")
    if v is True:
        return "true"
    if v is False:
        return "false"
    return str(v).lower() if v is not None else "none"


def first_good(agent, guard):
    out = {}
    for path in sorted(glob.glob(os.path.join(EVAL, "stage_a", agent, guard, "episodes*.jsonl"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                if d.get("error"):
                    continue
                out.setdefault(d["task_index"], d)
    return out


def boot_mean(xs, rng):
    n = len(xs)
    means = sorted(sum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(N_BOOT))
    return [round(means[int(0.025 * N_BOOT)], 4), round(means[int(0.975 * N_BOOT) - 1], 4)]


def stage_a(agent, rng):
    fr, tr = first_good(agent, "tgr_frozen"), first_good(agent, "tgr_tracker")
    tasks = sorted(set(fr) & set(tr))
    diffs = [(tr[t].get("reward") or 0) - (fr[t].get("reward") or 0) for t in tasks]
    both = sum(1 for t in tasks if fr[t].get("reward") and tr[t].get("reward"))
    only_tr = sum(1 for t in tasks if tr[t].get("reward") and not fr[t].get("reward"))
    only_fr = sum(1 for t in tasks if fr[t].get("reward") and not tr[t].get("reward"))
    # tracker side: changed values and changed decisions
    changed_pred = collections.Counter()
    gift_pairs = collections.Counter()
    gift_block_same = 0
    tasks_changed_decision = set()
    for t in tasks:
        for a in tr[t].get("attempts", []):
            g = a.get("guard") or {}
            tk = g.get("tracker")
            if not tk:
                continue
            for p in tk.get("changed") or []:
                name = p if isinstance(p, str) else (p.get("name") if isinstance(p, dict) else str(p))
                changed_pred[name] += 1
                if name == GIFT:
                    jv = (tk.get("judge_values") or {}).get(GIFT)
                    tv = (tk.get("tracker_values") or {}).get(GIFT)
                    gift_pairs[f"judge {val(jv)} -> tracker {val(tv)}"] += 1
                    if not g.get("action_allowed"):
                        gift_block_same += 1
    return {
        "tasks": len(tasks),
        "success_frozen": round(sum(fr[t].get("reward") or 0 for t in tasks) / len(tasks), 4),
        "success_tracker": round(sum(tr[t].get("reward") or 0 for t in tasks) / len(tasks), 4),
        "diff_tracker_minus_frozen": round(sum(diffs) / len(diffs), 4),
        "diff_range_95": boot_mean(diffs, rng),
        "both": both, "only_tracker": only_tr, "only_frozen": only_fr,
        "neither": len(tasks) - both - only_tr - only_fr,
        "blocks_per_conv_frozen": round(sum(fr[t].get("n_blocks") or 0 for t in tasks) / len(tasks), 3),
        "blocks_per_conv_tracker": round(sum(tr[t].get("n_blocks") or 0 for t in tasks) / len(tasks), 3),
        "changed_values_by_predicate_tracker_side": dict(changed_pred.most_common(8)),
        "gift_card_changes_tracker_side": dict(gift_pairs),
        "gift_card_changes_still_blocked": gift_block_same,
        "cost_frozen": round(sum(soft_stop.line_cost(fr[t]) for t in tasks), 3),
        "cost_tracker": round(sum(soft_stop.line_cost(tr[t]) for t in tasks), 3),
    }


def stage_b(rng):
    tries = collections.defaultdict(lambda: {"A": [], "B": []})
    meta = {}
    n_files = 0
    for path in glob.glob(os.path.join(EVAL, "stage_b", "*", "*", "*.json")):
        if ".failed" in path:
            continue
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("error"):
            continue
        n_files += 1
        fid, br = d.get("fork_id"), d.get("branch")
        tries[fid][br].append(d.get("reward") or 0)
        meta[fid] = fid
    kinds = {}
    with open(os.path.join(EVAL, "fork_points.jsonl"), encoding="utf-8") as f:
        for line in f:
            fp = json.loads(line)
            kinds[fp["fork_id"]] = (fp.get("agent"), fp.get("kind"), fp.get("source"))
    rows = []
    for fid, b in tries.items():
        if b["A"] and b["B"]:
            a_m, b_m = sum(b["A"]) / len(b["A"]), sum(b["B"]) / len(b["B"])
            ag, kind, src = kinds.get(fid, ("?", "?", "?"))
            rows.append({"fork": fid, "agent": ag, "kind": kind, "source": src, "a": a_m, "b": b_m,
                         "n_a": len(b["A"]), "n_b": len(b["B"])})
    out = {"finished_tries": n_files, "forks_with_both_branches": len(rows)}
    for label, sel in (("all", lambda r: True),
                       ("strong", lambda r: r["agent"] == "luna"), ("weak", lambda r: r["agent"] == "nano"),
                       ("block removed", lambda r: r["kind"] == "block removed"),
                       ("block added", lambda r: r["kind"] == "block added")):
        rs = [r for r in rows if sel(r)]
        if not rs:
            continue
        d = [r["b"] - r["a"] for r in rs]
        out[label] = {"forks": len(rs), "success_A": round(sum(r["a"] for r in rs) / len(rs), 4),
                      "success_B": round(sum(r["b"] for r in rs) / len(rs), 4),
                      "effect_B_minus_A": round(sum(d) / len(d), 4), "range_95": boot_mean(d, rng),
                      "mean_tries_per_branch": round(sum(r["n_a"] + r["n_b"] for r in rs) / (2 * len(rs)), 2)}
    return out


def main():
    rng = random.Random(SEED)
    res = {"spend_usd": round(soft_stop.spent_usd(), 4),
           "stage_a": {"strong (luna-dev)": stage_a("luna", rng), "weak (nano-agent-luna)": stage_a("nano", rng)},
           "stage_b_partial": stage_b(rng)}
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
