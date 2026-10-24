"""Eval v2 Part 5: the smoke check (agent SC). Standard library only. No LLM call, no network.

Reads the smoke files (output/eval_v2/smoke/), the soft-stop spend, the 55 saved fork points and their fork rates,
Part 1's cost numbers (checks/part1_checks.json) and the earlier p10 runs (times), and prints one JSON report:
  1. short re-checks of the Stage A and Stage B smoke files;
  2. the spend: guard/soft_stop.spent_report() against a hand sum of the smoke files;
  3. the frozen inputs and the from_shieldagent/ copies (sha256);
  4. the projection for Part 6 (strong, weak) and Part 8, and the total;
  5. the time per conversation and per try, and the expected wall time.
Run from predicate_correctness/:
  PYTHONDONTWRITEBYTECODE=1 /home/azureuser/miniconda3/bin/python3 -B -m scoring.v2_p5_smoke_check
Never imports gold code, the runner copy or tau-bench.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sys

sys.dont_write_bytecode = True

from guard import soft_stop                      # noqa: E402  (stdlib only)
from state_tracker import paths                  # noqa: E402

OUT = paths.OUTPUT_DIR
EV2 = os.path.join(OUT, "eval_v2")
SMOKE_A = os.path.join(EV2, "smoke", "stage_a", "luna")
SMOKE_B = os.path.join(EV2, "smoke", "stage_b")
GUARDS = ("tgr_frozen", "tgr_tracker")
MODELS = {"luna-dev": {"agent": "gpt-6-luna", "user": "gpt-6-luna", "guard": "gpt-6-luna"},
          "nano-agent-luna": {"agent": "gpt-5-nano", "user": "gpt-6-luna", "guard": "gpt-6-luna"}}
AGENT_OF = {"luna-dev": "strong", "nano-agent-luna": "weak"}

# The plan's numbers (overview.md, p6.md, p8.md, part1.md section 6).
STAGE_A_TASKS = 500
STAGE_A_GUARDS = 2
BRANCHES = 2
TRIES = 5
SLOTS = 4 * 8                    # 4 processes x 8 workers (HANDOFF.md section 4)
# Fork rates of Stage A: the saved retail train runs, as in part1.md section 6 (frozen = partner TGR, tracker = p10).
RATE_RUNS = {"strong": {"tgr_frozen": "luna_train_v5", "tgr_tracker": "p10_luna_train"},
             "weak": {"tgr_frozen": "nano_train", "tgr_tracker": "p10_nano_train"}}
# Cost of one try in Part 1 (part1.md section 6), the prior that the smoke test measures again.
PRIOR_TRY = {"strong": 0.0028, "weak": 0.0154}
# Earlier retail runs for time (output/p10_runs.md): DONE logs and episodes, 1 process x 8 workers each.
P10_TIME = {"strong": ("p10_luna_train", "p10_luna_train_retail.log"),
            "weak": ("p10_nano_train", "p10_nano_train_retail.log")}


def jl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def jload(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def r6(x):
    return round(float(x), 6)


# ---------------------------------------------------------------- 1. Stage A
def check_stage_a():
    rep, problems = {"guards": {}}, []
    for g in GUARDS:
        lines = jl(os.path.join(SMOKE_A, g, "episodes.jsonl"))
        keys = [(r.get("task_index"), r.get("trial")) for r in lines]
        n_checks = n_trk = lookup_err = mism = 0
        hand = {"agent": 0.0, "user": 0.0, "guard": 0.0}
        for r in lines:
            t = r.get("task_index")
            if r.get("error") is not None or r.get("done") is not True or not isinstance(r.get("reward_info"), dict):
                problems.append(f"A {g} task {t}: error/done/reward_info {r.get('error')}/{r.get('done')}")
            if r.get("task_split") != "train" or r.get("models") != MODELS["luna-dev"] or r.get("profile") != "luna-dev":
                problems.append(f"A {g} task {t}: split/models/profile")
            for k in hand:
                hand[k] += float((r.get("cost") or {}).get(k) or 0.0)
            for a in r.get("attempts") or []:
                gr = a.get("guard") or {}
                n_checks += 1
                if "tracker" in gr:
                    n_trk += 1
                    tr = gr["tracker"]
                    lookup_err += bool(tr.get("lookup_errors"))
                    mism += (tr.get("state") or {}).get("mismatches") or 0
        if len(set(keys)) != len(keys):
            problems.append(f"A {g}: duplicate (task, trial)")
        want_trk = n_checks if g == "tgr_tracker" else 0
        if n_trk != want_trk:
            problems.append(f"A {g}: {n_trk} checks with a tracker part, want {want_trk}")
        secs = [float(r.get("seconds") or 0) for r in lines]
        rep["guards"][g] = {
            "lines": len(lines), "tasks": sorted(k[0] for k in keys),
            "rewards": {r.get("task_index"): r.get("reward") for r in sorted(lines, key=lambda x: x.get("task_index"))},
            "reward_sum": sum(float(r.get("reward") or 0) for r in lines),
            "errors": sum(r.get("error") is not None for r in lines),
            "guard_checks": n_checks, "checks_with_tracker_part": n_trk,
            "tracker_lookup_error_checks": lookup_err, "tracker_replay_mismatches": mism,
            "hand_cost": {k: r6(v) for k, v in hand.items()}, "hand_cost_total": sum(hand.values()),
            "cost_per_conv": r6(sum(hand.values()) / len(lines)),
            "seconds_mean": round(sum(secs) / len(secs), 1), "seconds_max": max(secs),
        }
    allc = [rep["guards"][g] for g in GUARDS]
    n = sum(x["lines"] for x in allc)
    rep["conversations"] = n
    rep["hand_cost_total"] = sum(x["hand_cost_total"] for x in allc)
    rep["cost_per_conv"] = r6(rep["hand_cost_total"] / n)
    rep["seconds_mean"] = round(sum(x["seconds_mean"] * x["lines"] for x in allc) / n, 1)
    rep["problems"] = problems
    return rep


# ---------------------------------------------------------------- 2. Stage B
def check_stage_b(points):
    rep, problems, tries = {}, [], []
    src_cache = {}
    for p in sorted(glob.glob(os.path.join(SMOKE_B, "*", "*", "*.json"))):
        d = jload(p)
        fid, br = d.get("fork_id"), d.get("branch")
        fp = points.get(fid)
        if fp is None:
            problems.append(f"B {p}: fork id not in fork_points_saved.jsonl")
            continue
        cost_sum = sum(float(v or 0) for v in (d.get("cost") or {}).values())
        if abs(cost_sum - float(d.get("cost_usd") or 0)) > 1e-9:
            problems.append(f"B {fid} {br}: cost_usd {d.get('cost_usd')} != sum of cost {cost_sum}")
        want_dec = fp["decision_a"] if br == "A" else fp["decision_b"]
        if d.get("fork_decision") != want_dec:
            problems.append(f"B {fid} {br}: fork_decision {d.get('fork_decision')} != planned {want_dec}")
        if d.get("error") is not None:
            problems.append(f"B {fid} {br}: error {d.get('error')}")
        m = d.get("models") or {}
        want_m = MODELS.get(d.get("profile")) or {}
        # the try record also names the model that built the frozen rules ("rulebuild"); it must be an allowed one
        if {k: m.get(k) for k in want_m} != want_m or not set(m.values()) <= {"gpt-6-luna", "gpt-5-nano"}:
            problems.append(f"B {fid} {br}: models {m}")
        # the part before the fork equals the source conversation (messages up to and including the fork call)
        ep = os.path.join(paths.PC_DIR, fp["episodes_path"])
        if ep not in src_cache:
            src_cache[ep] = jl(ep)
        src = [r for r in src_cache[ep] if r.get("task_index") == fp["task_index"] and r.get("trial") == fp["trial"]]
        i = int(fp["attempt_index"])
        prefix_ok = None
        if len(src) == 1:
            k = 2 + 2 * i + 1
            prefix_ok = (d.get("messages") or [])[:k] == (src[0].get("messages") or [])[:k]
            if not prefix_ok:
                problems.append(f"B {fid} {br}: message prefix differs from the source")
        else:
            problems.append(f"B {fid} {br}: {len(src)} source lines")
        n_msgs, n_att = len(d.get("messages") or []), len(d.get("attempts") or [])
        tries.append({"fork_id": fid, "branch": br, "profile": d.get("profile"), "agent": AGENT_OF.get(d.get("profile")),
                      "kind": fp.get("kind"), "decision": d.get("fork_decision"), "planned": want_dec,
                      "reward": d.get("reward"), "done": d.get("done"), "error": d.get("error"),
                      "cost_usd": float(d.get("cost_usd") or 0), "seconds": float(d.get("seconds") or 0),
                      "prefix_equals_source": prefix_ok, "messages_eq_2_plus_2x_attempts": n_msgs == 2 + 2 * n_att,
                      "judge_seed_written": (d.get("judge_seed") or {}).get("written")})
    runs = []
    for p in sorted(glob.glob(os.path.join(SMOKE_B, "run_*.json"))):
        d = jload(p)
        runs.append({"file": os.path.basename(p), "cost_usd": d.get("cost_usd")})
    rep["tries"] = tries
    rep["run_files"] = runs
    rep["hand_cost_total"] = sum(t["cost_usd"] for t in tries)
    for ag in ("strong", "weak"):
        ts = [t for t in tries if t["agent"] == ag]
        rep[ag] = {"tries": len(ts), "cost_total": r6(sum(t["cost_usd"] for t in ts)),
                   "cost_per_try": r6(sum(t["cost_usd"] for t in ts) / len(ts)) if ts else None,
                   "seconds_per_try": round(sum(t["seconds"] for t in ts) / len(ts), 1) if ts else None}
    rep["problems"] = problems
    return rep


# ---------------------------------------------------------------- 3. frozen inputs and copies
def check_frozen():
    txt = open(os.path.join(paths.PC_DIR, "guard", "tgr_tracker.py"), encoding="utf-8").read()
    frozen = {}
    for rel in ("output/predicate_types.json", "state_tracker/lookups_airline.json",
                "state_tracker/lookups_retail.json"):
        h = sha256(os.path.join(paths.PC_DIR, rel))
        frozen[rel] = {"sha256": h, "equals_FROZEN_SHA256": h in txt}
    sums_ok = sums_bad = 0
    bad = []
    with open(paths.SHA256SUMS, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            want, rel = line.strip().split(None, 1)
            p = os.path.join(paths.FROM_SA, rel)
            if os.path.exists(p) and sha256(p) == want:
                sums_ok += 1
            else:
                sums_bad += 1
                bad.append(rel)
    return {"frozen": frozen, "from_shieldagent_sha256sums": {"ok": sums_ok, "bad": sums_bad, "bad_files": bad[:20]}}


# ---------------------------------------------------------------- 4. + 5. projection and time
def p10_times():
    out = {}
    for ag, (tag, log) in P10_TIME.items():
        lines = jl(os.path.join(OUT, "online", tag, "retail", "tgr_tracker", "episodes.jsonl"))
        secs = [float(r.get("seconds") or 0) for r in lines if r.get("error") is None]
        m = None
        lp = os.path.join(paths.LOGS_DIR, log)
        if os.path.exists(lp):
            for x in open(lp, encoding="utf-8", errors="replace"):
                mm = re.search(r"DONE: (\d+) episodes in (\d+)s", x)
                if mm:
                    m = (int(mm.group(1)), int(mm.group(2)))
        mean = sum(secs) / len(secs)
        eff = (m[0] * mean) / (8 * m[1]) if m else None       # busy share of 8 workers over the wall time
        out[ag] = {"tag": tag, "conversations": len(secs), "seconds_mean": round(mean, 1),
                   "done_line": {"episodes": m[0], "wall_s": m[1]} if m else None,
                   "worker_efficiency": round(eff, 3) if eff else None}
    return out


def project(a, b, spent):
    p1 = jload(os.path.join(EV2, "checks", "part1_checks.json"))["cost"]
    prior_conv = {"strong": (p1["luna_train_v5/retail"]["mean_cost"] + p1["p10_luna_train/retail"]["mean_cost"]) / 2,
                  "weak": (p1["nano_train/retail"]["mean_cost"] + p1["p10_nano_train/retail"]["mean_cost"]) / 2}
    ratio = prior_conv["weak"] / prior_conv["strong"]
    conv = {"strong": a["cost_per_conv"], "weak": a["cost_per_conv"] * ratio}
    n_conv = STAGE_A_TASKS * STAGE_A_GUARDS
    p6 = {ag: n_conv * conv[ag] for ag in conv}
    p6_prior = {ag: n_conv * prior_conv[ag] for ag in conv}

    rates = jload(os.path.join(EV2, "fork_rates_saved.json"))
    rate_of = {(r["run"], r["domain"]): r["fork_rate"] for r in rates["rows"]}
    known = {"strong": 0, "weak": 0}
    for fp in jl(os.path.join(EV2, "fork_points_saved.jsonl")):
        known[AGENT_OF[fp["profile"]]] += 1
    forks_a = {ag: sum(STAGE_A_TASKS * rate_of[(run, "retail")] for run in RATE_RUNS[ag].values()) for ag in known}
    forks = {ag: known[ag] + forks_a[ag] for ag in known}
    per_try = {ag: b[ag]["cost_per_try"] for ag in known}
    per_try_caution = {ag: max(per_try[ag], PRIOR_TRY[ag]) for ag in known}
    n_try = BRANCHES * TRIES
    p8 = {ag: forks[ag] * n_try * per_try[ag] for ag in known}
    p8_caution = {ag: forks[ag] * n_try * per_try_caution[ag] for ag in known}
    total = spent + sum(p6.values()) + sum(p8.values())
    total_caution = spent + sum(p6_prior.values()) + sum(p8_caution.values())
    cost_per_fork = sum(p8.values()) / sum(forks.values())
    room_p8 = soft_stop.SOFT_STOP_USD - spent - sum(p6.values())
    proj = {
        "prior_cost_per_conv": {k: r6(v) for k, v in prior_conv.items()}, "weak_strong_ratio": round(ratio, 3),
        "cost_per_conv": {k: r6(v) for k, v in conv.items()},
        "part6_usd": {k: round(v, 2) for k, v in p6.items()},
        "part6_prior_usd": {k: round(v, 2) for k, v in p6_prior.items()},
        "fork_rates_used": {ag: {g: rate_of[(run, "retail")] for g, run in RATE_RUNS[ag].items()} for ag in known},
        "forks_known": known, "forks_stage_a_expected": {k: round(v, 1) for k, v in forks_a.items()},
        "forks_total": {k: round(v, 1) for k, v in forks.items()},
        "tries_per_fork": n_try, "per_try_usd": {k: r6(v) for k, v in per_try.items()},
        "per_try_caution_usd": {k: r6(v) for k, v in per_try_caution.items()},
        "part8_usd": {k: round(v, 2) for k, v in p8.items()}, "part8_total_usd": round(sum(p8.values()), 2),
        "part8_caution_usd": round(sum(p8_caution.values()), 2),
        "spent_usd": r6(spent), "total_usd": round(total, 2), "total_caution_usd": round(total_caution, 2),
        "under_100": total < soft_stop.SOFT_STOP_USD, "caution_under_100": total_caution < soft_stop.SOFT_STOP_USD,
        "cost_per_fork_mix_usd": r6(cost_per_fork),
        "max_forks_under_100": int(room_p8 / cost_per_fork),
    }
    return proj, forks, n_try


def timing(a, b, forks, n_try):
    p10 = p10_times()
    sec_conv = {"strong": a["seconds_mean"],
                "weak": a["seconds_mean"] * p10["weak"]["seconds_mean"] / p10["strong"]["seconds_mean"]}
    eff = {ag: p10[ag]["worker_efficiency"] for ag in p10}
    n_conv = STAGE_A_TASKS * STAGE_A_GUARDS
    wall6 = {ag: n_conv * sec_conv[ag] / (SLOTS * eff[ag]) / 60 for ag in sec_conv}
    sec_try = {ag: b[ag]["seconds_per_try"] for ag in ("strong", "weak")}
    work8 = {ag: forks[ag] * n_try * sec_try[ag] for ag in sec_try}
    wall8 = sum(work8.values()) / (SLOTS * eff["weak"]) / 60
    return {
        "p10_retail": p10, "seconds_per_conv": {k: round(v, 1) for k, v in sec_conv.items()},
        "minutes_per_conv": {k: round(v / 60, 2) for k, v in sec_conv.items()},
        "slots": SLOTS, "part6_wall_min": {k: round(v, 1) for k, v in wall6.items()},
        "seconds_per_try": sec_try, "minutes_per_try": {k: round(v / 60, 2) for k, v in sec_try.items()},
        "part8_worker_hours": {k: round(v / 3600, 2) for k, v in work8.items()},
        "part8_wall_min": round(wall8, 1),
    }


def main():
    points = {fp["fork_id"]: fp for fp in jl(os.path.join(EV2, "fork_points_saved.jsonl"))}
    a = check_stage_a()
    b = check_stage_b(points)
    sp = soft_stop.spent_report()
    smoke_a_scan = sum(v for k, v in sp["by_file"].items() if k.startswith("smoke/stage_a/"))
    smoke_b_scan = sum(v for k, v in sp["by_file"].items() if k.startswith("smoke/stage_b/"))
    other = {k: v for k, v in sp["by_file"].items() if not k.startswith("smoke/")}
    hand = a["hand_cost_total"] + b["hand_cost_total"]
    spend = {"spent_report_total_usd": r6(sp["total_usd"]), "hand_sum_usd": r6(hand),
             "difference_usd": sp["total_usd"] - hand, "equal": abs(sp["total_usd"] - hand) < 1e-9,
             "stage_a_scan_usd": r6(smoke_a_scan), "stage_a_hand_usd": r6(a["hand_cost_total"]),
             "stage_b_scan_usd": r6(smoke_b_scan), "stage_b_hand_usd": r6(b["hand_cost_total"]),
             "files_outside_smoke": other, "episode_files": sp["episode_files"], "stage_b_files": sp["stage_b_files"],
             "error_lines": sp["error_lines"], "unreadable": sp["unreadable"], "no_cost_usd": sp["no_cost_usd"]}
    proj, forks, n_try = project(a, b, sp["total_usd"])
    rep = {"stage_a": a, "stage_b": b, "spend": spend, "frozen": check_frozen(), "projection": proj,
           "time": timing(a, b, forks, n_try)}
    rep["problems"] = a["problems"] + b["problems"]
    print(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
