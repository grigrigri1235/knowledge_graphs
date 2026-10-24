"""Eval v2 Part 7 (agent P7B): merge the fork points of all sources, the fork rates, the counts, the projected Stage B
cost and the Stage B launch plan. No LLM call, no network, standard library only. Never imports gold code.

Modes (run from predicate_correctness/ with the analysis Python):
  PYTHONDONTWRITEBYTECODE=1 /home/azureuser/miniconda3/bin/python3 -B -m scoring.v2_p7b_fork_plan merge
      checks the three passing points files against their rates files (each point passed its rebuild check; ids
      unique), then writes output/eval_v2/fork_points.jsonl and output/eval_v2/fork_rates.json
  ... -m scoring.v2_p7b_fork_plan counts  > output/logs/v2_p7b_counts.json
      the Part 7 counts of the merged file, with the judge's view at each fork (history over 24,000 characters)
  ... -m scoring.v2_p7b_fork_plan plan    > output/logs/v2_p7b_plan.json
      spend now (guard/soft_stop.spent_report), the projected Stage B cost, sampling only if spend + projection is
      over $100, the split into processes, output/eval_v2/stage_b_ids_<k>.txt and output/eval_v2/stage_b_launch.md
The paid run is not started here: the main chat starts it (docs/planning/tracker_eval_v2/orchestration.md, 15:40).
"""
from __future__ import annotations

import collections
import json
import math
import os
import random
import sys
import time

sys.dont_write_bytecode = True

from state_tracker import paths                       # noqa: E402  (standard library only)

PC = paths.PC_DIR
EV2 = os.path.join(paths.OUTPUT_DIR, "eval_v2")
PARTS = (                                               # (name, points file, rates file); each written by find_points
    ("saved", "fork_points_saved.jsonl", "fork_rates_saved.json"),
    ("stage_a_luna", "fork_points_stage_a_luna.jsonl", "fork_rates_stage_a_luna.json"),
    ("stage_a_nano", "fork_points_stage_a_nano.jsonl", "fork_rates_stage_a_nano.json"),
)
MERGED = os.path.join(EV2, "fork_points.jsonl")
MERGED_ALL = os.path.join(EV2, "fork_points_all.jsonl")
LEFT_OUT = os.path.join(EV2, "fork_points_left_out.jsonl")
RATES = os.path.join(EV2, "fork_rates.json")
LAUNCH_MD = os.path.join(EV2, "stage_b_launch.md")
JUDGE_CHARS = 24000                                     # TGRConfig.history_chars (state_tracker/load_steps.py)

BRANCHES, TRIES, WORKERS = 2, 5, 8
PER_TRY = {"luna": 0.00478, "nano": 0.01296}           # measured, output/eval_v2/checks/smoke.md
PER_TRY_CAUTIOUS = {"luna": 0.00478, "nano": 0.0154}   # cautious weak = Part 1 prior (smoke.md); strong: measured
MIN_PER_TRY = {"luna": 0.45, "nano": 2.31}              # smoke.md "Time": strong 27 s, weak 139 s per try
BUSY = {"luna": 0.92, "nano": 0.90}                     # busy share of the earlier retail runs (smoke.md, p10_runs.md)
PROFILE = {"luna": "luna-dev", "nano": "nano-agent-luna"}
SOFT_STOP, SPARE, SEED = 100.0, 5.0, 20261022
N_NANO_PROCS = 3
PY = "/home/azureuser/venvs/tau-bench/bin/python"


def rel(p: str) -> str:
    return os.path.relpath(os.path.abspath(p), PC)


def read_jsonl(p: str) -> list:
    with open(p, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def write_jsonl(p: str, rows: list) -> None:
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, p)


def rate(n_with: int, n: int):
    return round(n_with / n, 4) if n else None


# ------------------------------------------------------------------------------------------------ merge
def load_parts() -> list:
    """[(name, points, rates)], each points file checked against its rates file."""
    out = []
    for name, pf, rf in PARTS:
        pts = read_jsonl(os.path.join(EV2, pf))
        with open(os.path.join(EV2, rf), encoding="utf-8") as f:
            rates = json.load(f)
        rc = rates.get("rebuild_check") or {}
        ids = [p["fork_id"] for p in pts]
        dropped = {d["fork_id"] for d in rc.get("dropped") or []}
        problems = []
        if rates.get("points_file") != rel(os.path.join(EV2, pf)):
            problems.append(f"rates points_file {rates.get('points_file')!r}")
        if rates.get("points_kept") != len(pts) or rc.get("passed") != len(pts):
            problems.append(f"kept {rates.get('points_kept')} / passed {rc.get('passed')} != {len(pts)} lines")
        if rc.get("checked") != rates.get("points_found"):
            problems.append("not every point found was checked")
        if not rc.get("venv_checks"):
            problems.append("the venv checks (env, continuation) did not run")
        if dropped & set(ids):
            problems.append(f"dropped ids in the points file: {sorted(dropped & set(ids))}")
        if len(set(ids)) != len(ids):
            problems.append("ids not unique inside the file")
        kept_rows = sum(r.get("with fork, kept after the rebuild checks", 0) for r in rates["rows"])
        if kept_rows != len(pts):
            problems.append(f"rows say {kept_rows} kept")
        if any(str(p.get("episodes_path", "")).endswith(".before_resume") for p in pts):
            problems.append("a point reads a .before_resume backup")
        if problems:
            raise SystemExit(f"{pf}: " + "; ".join(problems))
        out.append((name, pts, rates))
    return out


def agg(rows: list, kept: list) -> dict:
    """Totals of rate rows, with the forks kept after the rebuild checks."""
    c = collections.Counter()
    keys = ("conversations", "lines", "error lines", "later duplicate lines (first kept)", "checks compared",
            "checks not comparable", "offline errors", "changed attempts: block removed",
            "changed attempts: block added", "with fork", "block removed", "block added",
            "differences skipped: cap override, no effect", "conversations with only no-effect differences",
            "fork at a later try (attempt > 1)", "fork at a cap override try", "not comparable before the fork",
            "frozen block message without judge evidence")
    for r in rows:
        for k in keys:
            c[k] += r.get(k, 0)
    n = c["conversations"]
    kr = sum(p["kind"] == "block removed" for p in kept)
    ka = sum(p["kind"] == "block added" for p in kept)
    return {**{k: c[k] for k in keys}, "forks found": c["with fork"], "forks kept": len(kept),
            "kept: block removed": kr, "kept: block added": ka,
            "fork rate (found)": rate(c["with fork"], n), "fork rate (kept)": rate(len(kept), n),
            "fork rate kept: block removed": rate(kr, n), "fork rate kept: block added": rate(ka, n)}


def merge() -> int:
    parts = load_parts()
    merged, seen = [], set()
    for name, pts, _ in parts:
        for p in pts:
            if p["fork_id"] in seen:
                raise SystemExit(f"fork id twice: {p['fork_id']}")
            seen.add(p["fork_id"])
            merged.append(p)
    if os.path.exists(MERGED_ALL) or os.path.exists(LEFT_OUT):
        raise SystemExit("fork_points_all.jsonl / fork_points_left_out.jsonl exist: a sample was taken; not merging again")
    write_jsonl(MERGED, merged)

    rows = []
    for name, pts, rates in parts:
        for r in rates["rows"]:
            k = [p for p in merged if (p["source"], p["run"], p["domain"]) == (r["source"], r["run"], r["domain"])]
            rows.append({"part": name, "source": r["source"], "run": r["run"], "agent": r["agent"],
                         "domain": r["domain"], "source_guard": r["source_guard"], "files": r.get("files"),
                         **agg([r], k)})
    src_rows = [(name, r) for name, _, rates in parts for r in rates["rows"]]

    def group(fn):
        g = collections.OrderedDict()
        for name, r in src_rows:
            g.setdefault(fn(r), []).append(r)
        return {k: agg(v, [p for p in merged if any((p["source"], p["run"], p["domain"]) ==
                                                    (x["source"], x["run"], x["domain"]) for x in v)])
                for k, v in g.items()}

    out = {
        "written_by": "scoring/v2_p7b_fork_plan.py merge (agent P7B, Part 7; no LLM)",
        "date": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "definition": ("fork rate = conversations with a fork point / conversations (first good line per task and "
                       "try; error lines dropped). 'found' = before the rebuild checks, 'kept' = passed them. A "
                       "conversation has at most one fork point (its first differing attempt with an effect)."),
        "inputs": [{"part": n, "points": PARTS[i][1], "rates": PARTS[i][2], "points_found": r["points_found"],
                    "points_kept": r["points_kept"], "dropped": (r.get("rebuild_check") or {}).get("dropped")}
                   for i, (n, _, r) in enumerate(parts)],
        "points_file": rel(MERGED), "points": len(merged),
        "by_run_domain": rows,
        "by_run": group(lambda r: r["run"]),
        "stage_a_by_agent_guard": {k: v for k, v in group(lambda r: r["run"]).items() if k.startswith("stage_a/")},
        "stage_a_by_agent": {k: v for k, v in group(lambda r: f"{r['source']} / {r['agent']}").items()
                             if k.startswith("stage_a")},
        "by_source_agent": group(lambda r: f"{r['source']} / {r['agent']}"),
        "by_source": group(lambda r: r["source"]),
        "by_agent": group(lambda r: r["agent"]),
        "by_agent_domain": group(lambda r: f"{r['agent']} / {r['domain']}"),
        "all": group(lambda r: "all")["all"],
    }
    with open(RATES + ".tmp", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    os.replace(RATES + ".tmp", RATES)
    print(json.dumps({"merged": len(merged), "by_part": {n: len(p) for n, p, _ in parts},
                      "unique": len(seen) == len(merged), "points_file": rel(MERGED), "rates_file": rel(RATES)}))
    return 0


# ------------------------------------------------------------------------------------------------ counts
def history_chars(points: list) -> dict:
    """fork_id -> characters of the history the judge would see at the fork, before its 24,000-character cut
    (render_history(executed[:executed_prefix_len]) of the fork attempt; the copy in from_shieldagent/code/)."""
    paths.add_code_path()
    from repro_core.taubench_steps import render_history
    want = collections.defaultdict(dict)
    for p in points:
        want[p["episodes_path"]][p["line_no"]] = p
    out = {}
    for path, lines in want.items():
        with open(os.path.join(PC, path), encoding="utf-8") as f:
            for n, line in enumerate(f):
                p = lines.get(n)
                if p is None:
                    continue
                ep = json.loads(line)
                a = ep["attempts"][p["attempt_index"]]
                if (ep["task_index"], ep.get("trial"), a["exec_step"], a["attempt"], a["action"]) != (
                        p["task_index"], p["trial"], p["exec_step"], p["attempt"], p["action"]):
                    raise SystemExit(f"{p['fork_id']}: the line does not match the fork point")
                hist = ep["executed"][:a["executed_prefix_len"]]
                out[p["fork_id"]] = {"chars": len(render_history(hist)), "messages": len(hist),
                                     "exec_step": a["exec_step"]}
        missing = [p["fork_id"] for p in lines.values() if p["fork_id"] not in out]
        if missing:
            raise SystemExit(f"lines not found: {missing}")
    return out


def bin_of(chars: int) -> str:
    """Length bins of p9.md item 11; "over 24,000" is exactly the cut view."""
    return "under 12,000" if chars < 12000 else ("12,000-24,000" if chars <= JUDGE_CHARS else "over 24,000")


def counts() -> int:
    pts = read_jsonl(MERGED)
    with open(RATES, encoding="utf-8") as f:
        rates = json.load(f)
    hc = history_chars(pts)
    C = collections.Counter
    out = {"forks": len(pts)}
    out["by_source_agent_domain_kind"] = {" / ".join(k): v for k, v in sorted(C(
        (p["source"], p["agent"], p["domain"], p["kind"]) for p in pts).items())}
    out["by_source"] = dict(C(p["source"] for p in pts))
    out["by_agent"] = dict(C(p["agent"] for p in pts))
    out["by_domain"] = dict(C(p["domain"] for p in pts))
    out["by_kind"] = dict(C(p["kind"] for p in pts))
    out["by_agent_kind"] = {" / ".join(k): v for k, v in sorted(C((p["agent"], p["kind"]) for p in pts).items())}
    out["by_run"] = {k: v for k, v in sorted(C(p["run"] for p in pts).items())}
    out["by_run_kind"] = {" / ".join(k): v for k, v in sorted(C((p["run"], p["kind"]) for p in pts).items())}
    out["by_source_agent"] = {" / ".join(k): v for k, v in sorted(C((p["source"], p["agent"]) for p in pts).items())}
    out["dropped"] = {i["part"]: i["dropped"] for i in rates["inputs"]}
    out["found_vs_kept"] = {i["part"]: [i["points_found"], i["points_kept"]] for i in rates["inputs"]}
    out["no_effect_differences_skipped"] = {
        "by_run": {k: v["differences skipped: cap override, no effect"] for k, v in rates["by_run"].items()},
        "conversations with only no-effect differences": {
            k: v["conversations with only no-effect differences"] for k, v in rates["by_run"].items()},
        "kept forks with a skipped difference before": [p["fork_id"] for p in pts if p.get("no_effect_before")]}
    out["cap_override_forks"] = [p["fork_id"] for p in pts if p.get("cap_override_at_fork")]
    out["fork_at_later_try"] = {" / ".join(k): v for k, v in sorted(C(
        (p["source"], p["agent"]) for p in pts if p["attempt"] > 1).items())}
    out["not_comparable_before"] = [p["fork_id"] for p in pts if p.get("not_comparable_before")]
    cut = [p for p in pts if hc[p["fork_id"]]["chars"] > JUDGE_CHARS]
    out["judge_view_cut_at_fork"] = {
        "rule": "len(render_history(executed[:executed_prefix_len])) > 24,000 at the fork attempt",
        "cut": len(cut), "not cut": len(pts) - len(cut),
        "by_source_agent_kind": {" / ".join(k): v for k, v in sorted(C(
            (p["source"], p["agent"], p["kind"]) for p in cut).items())},
        "by_agent": dict(C(p["agent"] for p in cut)),
        "by_kind": dict(C(p["kind"] for p in cut)),
        "bins_by_agent": {a: dict(C(bin_of(hc[p["fork_id"]]["chars"]) for p in pts if p["agent"] == a))
                          for a in sorted({p["agent"] for p in pts})},
        "bins_by_agent_kind": {" / ".join(k): v for k, v in sorted(C(
            (p["agent"], p["kind"], bin_of(hc[p["fork_id"]]["chars"])) for p in pts).items())},
        "cut_changed_predicates": dict(C(c["name"] for p in cut for c in p.get("changed_predicates") or [])),
        "chars_min_median_max": {a: _mmm([hc[p["fork_id"]]["chars"] for p in pts if p["agent"] == a])
                                 for a in sorted({p["agent"] for p in pts})},
        "cut_ids": [p["fork_id"] for p in cut],
        "per_fork": {k: v for k, v in hc.items()},
    }
    out["changed_predicates_by_agent"] = {a: dict(C(c["name"] for p in pts if p["agent"] == a
                                                    for c in p.get("changed_predicates") or []).most_common())
                                          for a in sorted({p["agent"] for p in pts})}
    out["actions_by_agent"] = {a: dict(C(p["action"] for p in pts if p["agent"] == a).most_common())
                               for a in sorted({p["agent"] for p in pts})}
    out["feedback_sources"] = dict(C(f"{p.get('feedback_a_source')} / {p.get('feedback_b_source')}" for p in pts))
    out["judge_evidence_from"] = dict(C(s for p in pts for s in (p.get("judge_evidence_from") or {}).values()))
    out["rebuilt_frozen_message_missing_evidence"] = [
        p["fork_id"] for p in pts if p.get("feedback_a_source") == "rebuilt"
        and "missing" in (p.get("judge_evidence_from") or {}).values()]
    out["source_reward_by_source_agent_kind"] = {" / ".join(k): v for k, v in sorted(C(
        (p["source"], p["agent"], p["kind"], str(p.get("source_reward"))) for p in pts).items())}
    out["reviewer_verdict"] = dict(C(str(p.get("reviewer_verdict")) for p in pts))
    out["remaining_source_attempts_by_agent"] = {
        a: _mmm([max(1, p["n_attempts"] - p["attempt_index"]) for p in pts if p["agent"] == a])
        for a in sorted({p["agent"] for p in pts})}
    out["unique_ids"] = len({p["fork_id"] for p in pts}) == len(pts)
    out["profiles"] = dict(C(f"{p['agent']} / {p['profile']}" for p in pts))
    out["task_splits"] = dict(C(f"{p['source']} / {p['task_split']}" for p in pts))
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


def _mmm(xs):
    xs = sorted(xs)
    if not xs:
        return None
    return {"min": xs[0], "median": xs[len(xs) // 2], "max": xs[-1], "mean": round(sum(xs) / len(xs), 1)}


# ------------------------------------------------------------------------------------------------ plan
def weight(p: dict) -> int:
    """Expected work of one try, relative: the source conversation's attempts from the fork on (a longer rest of the
    conversation takes longer)."""
    return max(1, int(p["n_attempts"]) - int(p["attempt_index"]))


def sample(pts: list, budget: float) -> tuple:
    """Fixed-seed sample spread over (agent, kind): the same share of each group, so the kept forks cost <= budget."""
    cost = {p["fork_id"]: BRANCHES * TRIES * PER_TRY_CAUTIOUS[p["agent"]] for p in pts}
    total = sum(cost.values())
    share = min(1.0, budget / total)
    rng = random.Random(SEED)
    groups = collections.defaultdict(list)
    for p in sorted(pts, key=lambda x: x["fork_id"]):
        groups[(p["agent"], p["kind"])].append(p)
    keep = set()
    for g in sorted(groups):
        n = max(1, math.floor(share * len(groups[g])))
        keep |= {p["fork_id"] for p in rng.sample(groups[g], n)}
    while sum(cost[i] for i in keep) > budget:            # rounding: drop the most expensive group's last pick
        g = max(groups, key=lambda k: sum(cost[p["fork_id"]] for p in groups[k] if p["fork_id"] in keep))
        drop = sorted(p["fork_id"] for p in groups[g] if p["fork_id"] in keep)[-1]
        keep.discard(drop)
    return [p for p in pts if p["fork_id"] in keep], [p for p in pts if p["fork_id"] not in keep]


def lpt(pts: list, k: int) -> list:
    """Split into k lists with about equal summed weight (longest first, into the lightest list)."""
    bins = [[] for _ in range(k)]
    sums = [0.0] * k
    for p in sorted(pts, key=lambda x: (-weight(x), x["fork_id"])):
        j = min(range(k), key=lambda i: (sums[i], i))
        bins[j].append(p)
        sums[j] += weight(p)
    return bins


def plan() -> int:
    from guard import soft_stop                       # standard library only
    rep = soft_stop.spent_report()
    spent = rep["total_usd"]
    pts = read_jsonl(MERGED)
    n = collections.Counter(p["agent"] for p in pts)
    proj = {a: BRANCHES * TRIES * n[a] * PER_TRY[a] for a in PER_TRY}
    proj_c = {a: BRANCHES * TRIES * n[a] * PER_TRY_CAUTIOUS[a] for a in PER_TRY}
    total, total_c = spent + sum(proj.values()), spent + sum(proj_c.values())
    sampled = total_c > SOFT_STOP
    left_out = []
    if sampled:
        if not os.path.exists(MERGED_ALL):
            write_jsonl(MERGED_ALL, pts)
        pts, left_out = sample(read_jsonl(MERGED_ALL), SOFT_STOP - SPARE - spent)
        write_jsonl(MERGED, pts)
        write_jsonl(LEFT_OUT, left_out)
        n = collections.Counter(p["agent"] for p in pts)
        proj = {a: BRANCHES * TRIES * n[a] * PER_TRY[a] for a in PER_TRY}
        proj_c = {a: BRANCHES * TRIES * n[a] * PER_TRY_CAUTIOUS[a] for a in PER_TRY}

    # ---- processes: 1 for the luna forks, N_NANO_PROCS for the nano forks (about equal expected work)
    by_agent = {a: [p for p in pts if p["agent"] == a] for a in ("luna", "nano")}
    mean_w = {a: (sum(weight(p) for p in v) / len(v) if v else 1.0) for a, v in by_agent.items()}
    groups = [("luna", by_agent["luna"])] + [("nano", b) for b in lpt(by_agent["nano"], N_NANO_PROCS)]
    procs = []
    for k, (a, fs) in enumerate(groups, start=1):
        if not fs:
            continue
        rel_w = sum(weight(p) for p in fs) / mean_w[a]                # forks, weighted by their expected length
        tries = BRANCHES * TRIES * len(fs)
        worker_min = BRANCHES * TRIES * rel_w * MIN_PER_TRY[a]
        procs.append({"k": k, "agent": a, "profile": PROFILE[a], "forks": len(fs), "tries": tries,
                      "weight_sum": sum(weight(p) for p in fs), "weighted_forks": round(rel_w, 2),
                      "kinds": dict(collections.Counter(p["kind"] for p in fs)),
                      "sources": dict(collections.Counter(p["source"] for p in fs)),
                      "cost_usd": round(BRANCHES * TRIES * rel_w * PER_TRY[a], 4),
                      "cost_usd_cautious": round(BRANCHES * TRIES * rel_w * PER_TRY_CAUTIOUS[a], 4),
                      "worker_minutes": round(worker_min, 1),
                      "wall_minutes": round(worker_min / (WORKERS * BUSY[a]), 1),
                      "longest_try_minutes": round(max(weight(p) for p in fs) / mean_w[a] * MIN_PER_TRY[a], 1),
                      "ids_file": f"output/eval_v2/stage_b_ids_{k}.txt",
                      "ids": sorted(p["fork_id"] for p in fs)})
    for pr in procs:
        others = sum(q["cost_usd_cautious"] for q in procs if q["k"] != pr["k"])
        pr["later_left_usd"] = int(math.ceil(others))
        core = (f"{PY} -B -m fork.run_all output/eval_v2/fork_points.jsonl --profile {pr['profile']} "
                f"--ids \"$(paste -sd, {pr['ids_file']})\" --branches A,B --tries {TRIES} --workers {WORKERS} "
                f"--later-left-usd {pr['later_left_usd']}")
        pr["command"] = (f"PYTHONDONTWRITEBYTECODE=1 setsid nohup {core} > output/logs/v2_stage_b_{pr['k']}.log 2>&1 &")
        pr["dry_command"] = (f"PYTHONDONTWRITEBYTECODE=1 {core} --dry-run > output/logs/v2_p7b_dry_stage_b_{pr['k']}.log "
                             f"2>&1")
        with open(os.path.join(PC, pr["ids_file"]) + ".tmp", "w", encoding="utf-8") as f:
            f.write("\n".join(pr["ids"]) + "\n")
        os.replace(os.path.join(PC, pr["ids_file"]) + ".tmp", os.path.join(PC, pr["ids_file"]))
    all_ids = [i for pr in procs for i in pr["ids"]]
    if sorted(all_ids) != sorted(p["fork_id"] for p in pts) or len(set(all_ids)) != len(all_ids):
        raise SystemExit("the id lists are not a disjoint cover of the fork points")
    out = {"date": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
           "spent_usd": round(spent, 4),
           "spend_parts": {k: v for k, v in rep.items() if k not in ("by_file",)},
           "spend_files": len(rep.get("by_file") or {}),
           "audit_or_tmp_files": [f for f in (rep.get("by_file") or {}) if "/_audit_" in "/" + f or "/_tmp" in "/" + f],
           "forks_by_agent": dict(n), "tries": BRANCHES * TRIES * len(pts),
           "per_try_usd": PER_TRY, "per_try_usd_cautious": PER_TRY_CAUTIOUS,
           "projection_usd": {a: round(v, 4) for a, v in proj.items()}, "projection_total_usd": round(sum(proj.values()), 4),
           "projection_cautious_usd": {a: round(v, 4) for a, v in proj_c.items()},
           "projection_cautious_total_usd": round(sum(proj_c.values()), 4),
           "projected_total_usd": round(spent + sum(proj.values()), 4),
           "projected_total_cautious_usd": round(spent + sum(proj_c.values()), 4),
           "before_sampling": {"total_usd": round(total, 4), "total_cautious_usd": round(total_c, 4)},
           "sampled": sampled, "left_out": [p["fork_id"] for p in left_out],
           "room_under_100_usd": round(SOFT_STOP - spent, 4),
           "processes": procs,
           "wall_minutes_max": max(p["wall_minutes"] for p in procs)}
    write_launch_md(out)
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0


def write_launch_md(d: dict) -> None:
    P = d["processes"]
    L = []
    w = L.append
    w("# Stage B launch plan (Part 8)")
    w("")
    w(f"Written {d['date']} by agent P7B (`scoring/v2_p7b_fork_plan.py plan`). **No LLM call was made.** The paid run")
    w("is started **only by the main chat** (`docs/planning/tracker_eval_v2/orchestration.md`, 15:40 change), after it")
    w("checks the approval (`approval_request.md`: Part 8 is inside the 13:47 approval and the $100 soft stop).")
    w("")
    w("## Short version")
    w(f"- Fork points: **{sum(p['forks'] for p in P)}** (luna {d['forks_by_agent'].get('luna', 0)}, nano "
      f"{d['forks_by_agent'].get('nano', 0)}), x 2 branches x 5 tries = **{d['tries']:,} tries**. "
      f"{'Sampled (see fork_points_left_out.jsonl).' if d['sampled'] else 'No sampling (under $100).'}")
    w(f"- Spend now: **${d['spent_usd']:.2f}** (`guard/soft_stop.spent_report()`, {d['spend_files']} files).")
    w(f"- Projected Stage B cost: **${d['projection_total_usd']:.2f}** (cautious ${d['projection_cautious_total_usd']:.2f}). "
      f"Projected total: **${d['projected_total_usd']:.2f}** (cautious ${d['projected_total_cautious_usd']:.2f}), under $100.")
    w(f"- 4 processes at once (8 workers each): process 1 runs the luna forks, processes 2-4 the nano forks. Expected "
      f"wall time: about {d['wall_minutes_max'] / 60:.1f} h (the slowest process).")
    w("")
    w("## Processes")
    w("| k | profile | forks | tries | kinds | expected cost (cautious) | expected wall time | `--later-left-usd` | id list |")
    w("|---|---|---|---|---|---|---|---|---|")
    for p in P:
        kinds = ", ".join(f"{k} {v}" for k, v in sorted(p["kinds"].items()))
        w(f"| {p['k']} | {p['profile']} | {p['forks']} | {p['tries']} | {kinds} | ${p['cost_usd']:.2f} "
          f"(${p['cost_usd_cautious']:.2f}) | about {p['wall_minutes']:.0f} min | {p['later_left_usd']} | "
          f"`{p['ids_file']}` |")
    w("")
    w("- **Disjoint:** every fork id is in exactly one list (checked); never two processes on the same forks.")
    w("- **Same default out-root** (`output/eval_v2/stage_b/`), so the soft stop of each process sees the others'"
      " try files.")
    w("- `--later-left-usd` = the cautious expected cost of the **other** processes' tries, rounded up.")
    w("- **Expected work:** one try's time is taken as the per-try time of the smoke test (strong 0.45 min, weak "
      "2.31 min) times the fork's length weight: the source conversation's attempts from the fork on, divided by the"
      " mean of that agent's forks. The nano forks are split by that weight (longest first, into the lightest list)."
      " Wall time = worker minutes / (8 workers x busy share 0.92 strong, 0.90 weak). Cost per process uses the same"
      " weight. Add a tail of up to the longest single try (column below), and more if the weak agent's silent"
      " retries are common (smoke.md problem 3).")
    w("")
    w("| k | weighted forks | worker minutes | longest try (min, expected) |")
    w("|---|---|---|---|")
    for p in P:
        w(f"| {p['k']} | {p['weighted_forks']} | {p['worker_minutes']:.0f} | {p['longest_try_minutes']} |")
    w("")
    w("## Before starting (main chat)")
    w("1. No runner is alive: `pgrep -af 'fork.run_all|guard.run_online'` prints nothing.")
    w("2. `output/eval_v2/stage_b/` and `output/_llmcache/eval_v2_stage_b/` do not exist yet (first start), and no "
      "`output/eval_v2/_audit_*` or `_tmp*` folder exists.")
    w("3. Spend + this job is under $100 (see above).")
    w("")
    w("## Commands (start a few seconds apart: the run file name has a 1-second time stamp)")
    w("```")
    w("cd /home/azureuser/code_projects/predicate_correctness")
    for i, p in enumerate(P):
        w(p["command"])
        if i < len(P) - 1:
            w("sleep 5")
    w("```")
    w("")
    w("Each process ends with a line `[v2-stage-b] DONE: ...`. The same command again resumes (finished tries are "
      "skipped; a failed try is run again and its first output kept as `<try>.failed<k>.json`).")
    w("")
    w("## Dry runs of these exact commands")
    w("Each command above, with `--dry-run` added, run in the foreground (no `setsid nohup ... &`) and with its log in "
      "`output/logs/v2_p7b_dry_stage_b_<k>.log`:")
    w("```")
    w("cd /home/azureuser/code_projects/predicate_correctness")
    for p in P:
        w(p["dry_command"])
    w("```")
    w("")
    w("(results: see the section below, added after the dry runs)")
    w("")
    with open(LAUNCH_MD + ".tmp", "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    os.replace(LAUNCH_MD + ".tmp", LAUNCH_MD)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"merge": merge, "counts": counts, "plan": plan}.get(mode)
    if fn is None:
        raise SystemExit("usage: python -B -m scoring.v2_p7b_fork_plan merge | counts | plan")
    sys.exit(fn())
