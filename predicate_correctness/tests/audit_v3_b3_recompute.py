"""Independent recompute of tracker v3's B3 run (p14, optional side result), from the rules text and the raw lines only.

Rules: docs/planning/tracker_v3/preregistration_online.md, change log row 2026-10-23 19:08 ("B3 reading rule"), with
sections 2 (what counts), 6 (safety) and 7-8 (reported) for the parts the row does not restate.
It does not import or read scoring/v3_online_metrics.py or any other project metrics / report code. Standard library
only. No network, no LLM, no gold scorer. It only reads the run folder; it writes only the two --out files.

What it does, for one B3 run folder:
  1. reads every <arm>/episodes_shard*.jsonl (5 arms) and dropped_groups_*.jsonl in the run folder;
  2. keeps, per unit (arm, domain, task_index, trial), the line with the highest unit_attempt (a tie: the later line);
  3. a (task, try) group counts only if it is not dropped and all 5 arms have a kept line with no error and a reward;
  4. task success = the line's `reward` (tau-bench's own); per task = mean over its counted tries (B3: 1 try);
     per arm = mean over the tasks with a counted group;
  5. main: v3 (tgr_tracker_v3) - tgr_frozen, paired by task (mean of per-task differences), over the counted tasks
     (64 if the run is whole); also S1 direct_facts_v3 - direct, S2 tgr_tracker_v3 - direct_facts_v3, v3 - none
     (these three reported only, no verdict);
  6. 95 % range: bootstrap over tasks (B3 is one domain, so no strata), 10,000 resamples, a fresh
     random.Random(20261023) per quantity, tasks in sorted (domain, task_index) order, each resample = n draws of
     randrange(n); percentile range with linear interpolation (position q * (B - 1) in the sorted values);
  7. verdict: "not clearly worse" if the main lower end > -0.10, else "not shown";
  8. cost per conversation = sum of the line's cost{...} (if missing: sum of usage_roles[*].cost); mean per arm over
     the counted lines (with a bootstrap range over tasks), and totals over all lines;
  9. error lines (all lines and kept lines), dropped and incomplete groups, tasks with no counted group;
 10. safety (section 6): on every tgr_tracker_v3 line, each write attempt that v3 allowed (not blocked, no cap
     override) whose tool output starts with "Error" is matched to a v3 fact by the tool's error text (the mapping of
     docs/planning/tracker_v3/p3.md, written out below by hand). A match = a safety failure (pass mark 0). Unmapped
     refusals and cap-override refusals are listed apart. Counted on all v3 lines and, apart, on counted lines.

Run from predicate_correctness/:
  python3 -B tests/audit_v3_b3_recompute.py --run-dir <B3 run folder> --out <prefix>
writes <prefix>.json and <prefix>.md.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import random
import re
import sys

sys.dont_write_bytecode = True

PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_FILE = os.path.join(PC_DIR, "output", "eval_v3", "b3_tasks.json")
ARMS = ("none", "direct", "direct_facts_v3", "tgr_frozen", "tgr_tracker_v3")
V3_ARM = "tgr_tracker_v3"
SEED = 20261023
N_BOOT = 10000
MAIN_BAR = -0.10
N_TASKS_EXPECTED = 64
COMPARISONS = {
    "main_v3_minus_frozen": ("tgr_tracker_v3", "tgr_frozen"),
    "S1_facts_minus_direct": ("direct_facts_v3", "direct"),
    "S2_v3_minus_facts": ("tgr_tracker_v3", "direct_facts_v3"),
    "v3_minus_none": ("tgr_tracker_v3", "none"),
}

# write tools of tau-bench (retail and airline)
WRITE_TOOLS = {
    "cancel_pending_order", "modify_pending_order_address", "modify_pending_order_items",
    "modify_pending_order_payment", "modify_user_address", "return_delivered_order_items",
    "exchange_delivered_order_items",
    "book_reservation", "cancel_reservation", "update_reservation_baggages", "update_reservation_flights",
    "update_reservation_passengers",
}

# tool error text -> the v3 fact it decides (p3.md "How it works", step 2). Written by hand from that text.
_GC_DIFF = "gift_card_balance_covers_price_difference"
_REPL = "item_replacements_are_available_same_product_different_option"
TOOL_FACT_MAP = {
    "cancel_pending_order": [(r"non-pending order", "order_status_checked_pending")],
    "modify_pending_order_address": [(r"non-pending order", "order_status_checked_pending")],
    "modify_pending_order_items": [
        (r"non-pending order", "order_status_checked_pending"),
        (r"insufficient gift card balance to pay for the (price difference|new item)", _GC_DIFF),
        (r"the number of items .*should match", _REPL),
        (r"new item .* not found or available", _REPL),
        (r"^Error: \S+ not found$", _REPL),  # "<item_id> not found" (not "order/payment method not found")
    ],
    "exchange_delivered_order_items": [
        (r"non-delivered order", "order_status_checked_delivered"),
        (r"insufficient gift card balance to pay for the (price difference|new item)", _GC_DIFF),
        (r"the number of items .*should match", _REPL),
        (r"new item .* not found or available", _REPL),
        (r"^Error: \S+ not found$", _REPL),
    ],
    "modify_pending_order_payment": [
        (r"non-pending order", "order_status_checked_pending"),
        (r"new payment method should be different", "payment_method_differs_from_original"),
        (r"insufficient gift card balance to pay for the order", "gift_card_balance_covers_order_total"),
    ],
    "return_delivered_order_items": [
        (r"non-delivered order", "order_status_checked_delivered"),
        (r"payment method should be either the original payment method or a gift card",
         "return_refund_method_is_original_or_existing_gift_card"),
    ],
    "book_reservation": [(r"payment method .*not found", "booking_payment_methods_found_in_user_profile")],
    "update_reservation_passengers": [(r"number of passengers does not match", "pending_passenger_count_unchanged")],
}
_NOT_ITEM = re.compile(r"^Error: (order|user|payment method|reservation|some item)\b", re.I)


def map_refusal(tool, text):
    """Return the v3 fact a tool refusal text maps to, or None (unmapped)."""
    t = text.strip()
    for pat, fact in TOOL_FACT_MAP.get(tool, []):
        if pat.startswith("^Error: \\S+ not found") and _NOT_ITEM.match(t):
            continue
        if re.search(pat, t, flags=re.I):
            return fact
    return None


def read_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append((n, json.loads(line)))
            except json.JSONDecodeError:
                out.append((n, None))  # a half-written last line of a live run
    return out


def line_cost(r):
    c = r.get("cost")
    if isinstance(c, dict) and c:
        return math.fsum(float(v or 0.0) for v in c.values() if isinstance(v, (int, float)) or v is None)
    ur = r.get("usage_roles") or {}
    return math.fsum(float(v.get("cost") or 0.0) for v in ur.values() if isinstance(v, dict))


def percentile(sorted_vals, q):
    n = len(sorted_vals)
    pos = q * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def bootstrap_mean(vals, seed=SEED, n_boot=N_BOOT):
    """Plain bootstrap over tasks of the mean of `vals` (already in task order). Returns (lo, hi)."""
    n = len(vals)
    if n == 0:
        return None, None
    rng = random.Random(seed)
    stats = []
    for _ in range(n_boot):
        s = 0.0
        for _ in range(n):
            s += vals[rng.randrange(n)]
        stats.append(s / n)
    stats.sort()
    return percentile(stats, 0.025), percentile(stats, 0.975)


def load_run(run_dir, warnings):
    lines = []
    files = {}
    bad_json = 0
    for arm in ARMS:
        paths = sorted(glob.glob(os.path.join(run_dir, arm, "episodes_shard*.jsonl")))
        files[arm] = [os.path.relpath(p, run_dir) for p in paths]
        for p in paths:
            for n, r in read_jsonl(p):
                where = f"{os.path.relpath(p, run_dir)}:{n}"
                if r is None:
                    bad_json += 1
                    warnings.append(f"{where}: not valid JSON (skipped; a line still being written?)")
                    continue
                if r.get("arm", arm) != arm:
                    warnings.append(f"{where}: arm field {r.get('arm')!r} in folder {arm}")
                lines.append((arm, r, where))
    extra = [d for d in sorted(os.listdir(run_dir))
             if os.path.isdir(os.path.join(run_dir, d)) and d not in ARMS
             and glob.glob(os.path.join(run_dir, d, "episodes_shard*.jsonl"))]
    if extra:
        warnings.append(f"episode folders that are not one of the 5 arms (ignored): {extra}")
    missing = [a for a in ARMS if not files[a]]
    if missing:
        warnings.append(f"arms with no episode file yet: {missing}")
    backups = sorted(glob.glob(os.path.join(run_dir, "*", "*.before_resume")))
    if backups:
        warnings.append(f"{len(backups)} *.before_resume files present (not read)")
    dropped = set()
    dropped_lines = 0
    for p in sorted(glob.glob(os.path.join(run_dir, "dropped_groups_*.jsonl"))):
        for n, r in read_jsonl(p):
            if r is None:
                warnings.append(f"{os.path.relpath(p, run_dir)}:{n}: not valid JSON (skipped)")
                continue
            dropped_lines += 1
            dropped.add((r["env"], int(r["task_index"]), int(r["trial"])))
    return lines, files, dropped, dropped_lines, bad_json


def safety_scan(arm_lines):
    """arm_lines: [(record, where)] of the v3 arm. Returns a dict of counts and examples."""
    out = {"lines": 0, "write_attempts": 0, "allowed_writes": 0, "allowed_writes_refused": 0,
           "failures_mapped": [], "allowed_refused_unmapped": [], "cap_override_refused": [],
           "blocked_writes": 0, "cap_override_writes": 0, "no_observation_allowed_writes": 0}
    for r, where in arm_lines:
        out["lines"] += 1
        for i, a in enumerate(r.get("attempts") or []):
            tool = a.get("action")
            if tool not in WRITE_TOOLS:
                continue
            out["write_attempts"] += 1
            blocked = bool(a.get("blocked"))
            cap = bool(a.get("cap_override"))
            obs = a.get("observation")
            refused = isinstance(obs, str) and obs.strip().startswith("Error")
            item = {"where": where, "task": [r.get("env"), r.get("task_index"), r.get("trial")],
                    "unit_attempt": r.get("unit_attempt"), "attempt_no": i, "exec_step": a.get("exec_step"),
                    "tool": tool, "tool_output": (obs or "")[:300] if isinstance(obs, str) else obs}
            if cap:
                out["cap_override_writes"] += 1
                if refused:
                    item["fact"] = map_refusal(tool, obs)
                    out["cap_override_refused"].append(item)
                continue
            if blocked:
                out["blocked_writes"] += 1
                continue
            out["allowed_writes"] += 1
            if obs is None:
                out["no_observation_allowed_writes"] += 1
            if not refused:
                continue
            out["allowed_writes_refused"] += 1
            fact = map_refusal(tool, obs)
            if fact is None:
                out["allowed_refused_unmapped"].append(item)
                continue
            g = a.get("guard") if isinstance(a.get("guard"), dict) else {}
            v3 = g.get("v3") if isinstance(g.get("v3"), dict) else {}
            facts = v3.get("facts") if isinstance(v3.get("facts"), dict) else {}
            fv = facts.get(fact)
            item["fact"] = fact
            item["v3_value_of_fact"] = fv.get("value") if isinstance(fv, dict) else None
            item["v3_source_of_fact"] = fv.get("source") if isinstance(fv, dict) else None
            out["failures_mapped"].append(item)
    out["n_failures_mapped"] = len(out["failures_mapped"])
    out["n_allowed_refused_unmapped"] = len(out["allowed_refused_unmapped"])
    out["n_cap_override_refused"] = len(out["cap_override_refused"])
    out["pass"] = out["n_failures_mapped"] == 0
    return out


def recompute(run_dir, tasks_file=TASKS_FILE, seed=SEED, n_boot=N_BOOT):
    warnings = []
    lines, files, dropped, dropped_lines, bad_json = load_run(run_dir, warnings)
    with open(tasks_file, encoding="utf-8") as fh:
        tasks = json.load(fh)["tasks"]
    task_set = {(t["domain"], int(t["task_index"])) for t in tasks}
    if len(task_set) != N_TASKS_EXPECTED:
        warnings.append(f"tasks file has {len(task_set)} tasks, not {N_TASKS_EXPECTED}")

    # line metadata checks
    steps = sorted({str(r.get("step")) for _, r, _ in lines})
    run_ids = sorted({str(r.get("run_id")) for _, r, _ in lines})
    splits = sorted({str(r.get("task_split")) for _, r, _ in lines})
    if len(steps) > 1 or (steps and steps != ["B3"]):
        warnings.append(f"step field(s) {steps}, expected only 'B3'")
    if len(run_ids) > 1:
        warnings.append(f"more than one run_id: {run_ids}")
    if splits and splits != ["train"]:
        warnings.append(f"task_split field(s) {splits}, expected only 'train'")
    not_in_file = sorted({(r.get("env"), int(r.get("task_index"))) for _, r, _ in lines} - task_set)
    if not_in_file:
        warnings.append(f"{len(not_in_file)} tasks in the lines are not in b3_tasks.json: {not_in_file[:10]}")

    n_lines = {a: 0 for a in ARMS}
    err_all = {a: 0 for a in ARMS}
    spend_all = {a: 0.0 for a in ARMS}
    for arm, r, _ in lines:
        n_lines[arm] += 1
        spend_all[arm] += line_cost(r)
        if r.get("error"):
            err_all[arm] += 1

    # latest unit attempt per unit
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
    error_texts = {}
    for arm, r, where in lines:
        if r.get("error"):
            error_texts.setdefault(arm, []).append({"where": where, "unit_attempt": r.get("unit_attempt"),
                                                    "error": str(r.get("error"))[:200]})

    groups = sorted({k[1:] for k in kept} | dropped)
    complete, incomplete, dropped_seen = [], [], []
    for g in groups:
        if g in dropped:
            dropped_seen.append(g)
            continue
        ok = all((a,) + g in kept and not kept[(a,) + g][1].get("error")
                 and kept[(a,) + g][1].get("reward") is not None for a in ARMS)
        (complete if ok else incomplete).append(g)

    trials = sorted({g[2] for g in complete})
    if trials and trials != [0]:
        warnings.append(f"counted tries {trials}; B3 has 1 try (trial 0)")
    reward_vs_info = 0
    for g in complete:
        for a in ARMS:
            r = kept[(a,) + g][1]
            ri = r.get("reward_info")
            if isinstance(ri, dict) and ri.get("reward") is not None and float(ri["reward"]) != float(r["reward"]):
                reward_vs_info += 1
    if reward_vs_info:
        warnings.append(f"{reward_vs_info} counted lines where reward != reward_info.reward (the `reward` field is used)")

    per_task = {}
    per_task_cost = {}
    for g in complete:
        tk = (g[0], g[1])
        d = per_task.setdefault(tk, {a: [] for a in ARMS})
        c = per_task_cost.setdefault(tk, {a: [] for a in ARMS})
        for a in ARMS:
            r = kept[(a,) + g][1]
            d[a].append(float(r["reward"]))
            c[a].append(line_cost(r))
    task_order = sorted(per_task)
    task_mean = {tk: {a: math.fsum(per_task[tk][a]) / len(per_task[tk][a]) for a in ARMS} for tk in task_order}
    task_cost = {tk: {a: math.fsum(per_task_cost[tk][a]) / len(per_task_cost[tk][a]) for a in ARMS}
                 for tk in task_order}
    domains = sorted({tk[0] for tk in task_order})
    if len(domains) > 1:
        warnings.append(f"more than one domain {domains}; the bootstrap here is not stratified")
    tasks_no_group = sorted({(g[0], g[1]) for g in groups} - set(task_mean))
    n_t = len(task_order)
    if n_t != N_TASKS_EXPECTED:
        warnings.append(f"{n_t} tasks counted, not {N_TASKS_EXPECTED}: this is not the B3 reading")

    arm_success = {}
    for a in ARMS:
        vals = [task_mean[t][a] for t in task_order]
        lo, hi = bootstrap_mean(vals, seed, n_boot)
        arm_success[a] = {"mean": (math.fsum(vals) / n_t if n_t else None), "lo": lo, "hi": hi, "n_tasks": n_t}

    comps = {}
    for name, (a, b) in COMPARISONS.items():
        diffs = [task_mean[t][a] - task_mean[t][b] for t in task_order]
        lo, hi = bootstrap_mean(diffs, seed, n_boot)
        comps[name] = {"arms": f"{a} - {b}", "n_tasks": n_t,
                       "point": (math.fsum(diffs) / n_t if n_t else None), "lo": lo, "hi": hi,
                       "tasks_better": sum(1 for x in diffs if x > 0), "tasks_worse": sum(1 for x in diffs if x < 0),
                       "tasks_same": sum(1 for x in diffs if x == 0)}

    m = comps["main_v3_minus_frozen"]
    verdict = (None if m["lo"] is None else "not clearly worse" if m["lo"] > MAIN_BAR else "not shown")

    costs = {}
    for a in ARMS:
        cs = [line_cost(kept[(a,) + g][1]) for g in complete]
        tv = [task_cost[t][a] for t in task_order]
        lo, hi = bootstrap_mean(tv, seed, n_boot)
        costs[a] = {"mean_per_conversation_counted": (math.fsum(cs) / len(cs) if cs else None),
                    "lo": lo, "hi": hi, "n_counted": len(cs),
                    "total_all_lines": spend_all[a], "n_all_lines": n_lines[a],
                    "mean_per_line_all": (spend_all[a] / n_lines[a] if n_lines[a] else None)}

    v3_all = [(r, where) for arm, r, where in lines if arm == V3_ARM]
    v3_counted = [(kept[(V3_ARM,) + g][1], kept[(V3_ARM,) + g][2]) for g in complete]
    safety = {"rule": "0 v3 allows that tau-bench's own tool then refuses, at a check that maps to a v3 fact",
              "all_v3_lines": safety_scan(v3_all), "counted_v3_lines": safety_scan(v3_counted)}

    return {
        "what": "independent recompute of B3 from preregistration_online.md (change log row 2026-10-23 19:08) and "
                "the raw run folder; no project metrics code read or imported",
        "run_dir": os.path.abspath(run_dir),
        "tasks_file": os.path.abspath(tasks_file),
        "settings": {"seed": seed, "n_boot": n_boot, "percentile": "linear interpolation, q*(B-1)",
                     "rng": "python random.Random(seed), fresh per quantity; tasks in sorted (domain, task_index) "
                            "order; n draws of randrange(n); not stratified (one domain)",
                     "main_bar": MAIN_BAR, "n_tasks_expected": N_TASKS_EXPECTED},
        "files": files,
        "line_fields": {"step": steps, "run_id": run_ids, "task_split": splits},
        "counts": {"lines": n_lines, "bad_json_lines": bad_json,
                   "error_lines_all": err_all, "error_lines_kept": err_kept, "error_texts": error_texts,
                   "groups_seen": len(groups), "groups_complete": len(complete),
                   "groups_dropped": len(dropped_seen), "dropped_file_lines": dropped_lines,
                   "groups_incomplete_not_dropped": len(incomplete),
                   "incomplete_list": [list(g) for g in incomplete], "dropped_list": [list(g) for g in dropped_seen],
                   "tasks_counted": n_t, "tasks_with_no_counted_group": len(tasks_no_group),
                   "tasks_with_no_counted_group_list": [list(t) for t in tasks_no_group],
                   "tasks_in_file_not_seen": len(task_set - {(g[0], g[1]) for g in groups})},
        "arm_success": arm_success,
        "comparisons": comps,
        "verdict_main": verdict,
        "verdict_note": "B3 is a side result (seen many-step Stage A tasks); never pooled with B2, never changes "
                        "B2's verdict; S1, S2 and v3 - none are reported only",
        "costs": costs,
        "total_spend_all_lines": math.fsum(spend_all.values()),
        "safety": safety,
        "warnings": warnings,
        "note": "point estimates are exact (must match another implementation to ~1e-12); bootstrap ranges match "
                "only if the resampling is the same",
    }


def f(x, nd=4, sign=True):
    return "-" if x is None else f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"


def to_md(res):
    c = res["counts"]
    out = ["# B3 independent recompute", "",
           f"Run folder: `{res['run_dir']}`", "",
           "Made from the rules text (pre-registration change log row 19:08) and the raw lines only (no project "
           "metrics code). Point estimates are exact and must match; the 95 % ranges come from my own bootstrap over "
           "tasks (seed 20261023, 10,000) and match only if the resampling is the same.", "",
           "## Counts",
           f"- lines per arm: " + ", ".join(f"{a} {c['lines'][a]}" for a in ARMS)
           + (f"; bad JSON lines {c['bad_json_lines']}" if c["bad_json_lines"] else ""),
           f"- groups seen {c['groups_seen']}, complete {c['groups_complete']}, dropped {c['groups_dropped']}, "
           f"incomplete (not dropped) {c['groups_incomplete_not_dropped']}",
           f"- tasks counted {c['tasks_counted']} of {res['settings']['n_tasks_expected']}; tasks seen with no counted "
           f"group {c['tasks_with_no_counted_group']}; tasks in the file not seen yet {c['tasks_in_file_not_seen']}",
           "- error lines (all / kept): " + ", ".join(f"{a} {c['error_lines_all'][a]}/{c['error_lines_kept'][a]}"
                                                      for a in ARMS), "",
           "## Task success per arm (mean over counted tasks [95 % range])", "",
           "| arm | success | n tasks |", "|---|---|---|"]
    for a in ARMS:
        s = res["arm_success"][a]
        out.append(f"| {a} | {f(s['mean'], 3, False)} [{f(s['lo'], 3, False)}, {f(s['hi'], 3, False)}] | "
                   f"{s['n_tasks']} |")
    out += ["", "## Differences, paired by task (point [95 % range])", "",
            "| comparison | point [range] | n tasks | tasks better / worse / same |", "|---|---|---|---|"]
    for name, cm in res["comparisons"].items():
        out.append(f"| {name} ({cm['arms']}) | {f(cm['point'])} [{f(cm['lo'])}, {f(cm['hi'])}] | {cm['n_tasks']} | "
                   f"{cm['tasks_better']} / {cm['tasks_worse']} / {cm['tasks_same']} |")
    out += ["", "## Verdict",
            f"- main (v3 - frozen TGR; lower end > -0.10): **{res['verdict_main']}**",
            f"- {res['verdict_note']}", "",
            "## Cost per conversation", "",
            "| arm | mean $ (counted) [95 % range] | n counted | all lines total $ | n all lines |",
            "|---|---|---|---|---|"]
    for a in ARMS:
        cc = res["costs"][a]
        out.append(f"| {a} | {f(cc['mean_per_conversation_counted'], 5, False)} [{f(cc['lo'], 5, False)}, "
                   f"{f(cc['hi'], 5, False)}] | {cc['n_counted']} | {f(cc['total_all_lines'], 4, False)} | "
                   f"{cc['n_all_lines']} |")
    out.append(f"\nTotal spend, all lines: ${res['total_spend_all_lines']:.4f}")
    out += ["", "## Safety (v3 allows that the tool refuses at a mapped check; pass mark 0)", "",
            "| lines | v3 lines | write attempts | allowed writes | allowed + refused | mapped (failures) | unmapped | "
            "cap-override refused |", "|---|---|---|---|---|---|---|---|"]
    for k in ("all_v3_lines", "counted_v3_lines"):
        s = res["safety"][k]
        out.append(f"| {k} | {s['lines']} | {s['write_attempts']} | {s['allowed_writes']} | "
                   f"{s['allowed_writes_refused']} | **{s['n_failures_mapped']}** | {s['n_allowed_refused_unmapped']} | "
                   f"{s['n_cap_override_refused']} |")
    fails = res["safety"]["all_v3_lines"]["failures_mapped"]
    if fails:
        out += ["", "Safety failures (all v3 lines):"]
        for it in fails:
            out.append(f"- `{it['where']}` {it['tool']} -> {it['fact']} (v3 said {it['v3_value_of_fact']!r}): "
                       f"{it['tool_output']}")
    if res["warnings"]:
        out += ["", "## Warnings"] + [f"- {w}" for w in res["warnings"]]
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--out", required=True, help="output prefix; writes <prefix>.json and <prefix>.md")
    ap.add_argument("--tasks-file", default=TASKS_FILE)
    args = ap.parse_args(argv)
    out_abs = os.path.abspath(args.out)
    if os.path.commonpath([out_abs, os.path.abspath(args.run_dir)]) == os.path.abspath(args.run_dir):
        ap.error("--out must not be inside the run folder")
    res = recompute(args.run_dir, args.tasks_file)
    os.makedirs(os.path.dirname(out_abs), exist_ok=True)
    with open(args.out + ".json", "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, sort_keys=False)
    with open(args.out + ".md", "w", encoding="utf-8") as fh:
        fh.write(to_md(res))
    print(f"wrote {args.out}.json and {args.out}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
