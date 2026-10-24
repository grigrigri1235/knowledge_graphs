"""Eval v2 Part 7 (agent P7A): fork points of the Stage A strong (luna) run, and the Stage B dry run on them. No LLM.

Why a wrapper (no code change in fork/): the Stage A weak (nano) run is live in output/eval_v2/stage_a/nano/ and must
not be read. fork/find_points.py lists every agent folder of stage_a/ (and reads a tgr_tracker folder's run_*.json
for its judge cache) before its --runs filter is applied; fork/run_all.py's soft-stop scan reads every episodes file
under output/eval_v2/. So this wrapper:
  - installs an audit hook first: any open / listdir / scandir of output/eval_v2/stage_a/nano, of the nano judge
    cache output/_llmcache/v2_stage_a_nano or of output/logs/v2_stage_a_nano_* is refused (PermissionError) and
    counted; the counts are printed at the end (find_points must show 0 attempts);
  - points: limits fork.find_points.AGENTS to luna (so the nano folder is not even listed), then runs
    fork.find_points.main(--source stage_a --runs stage_a/luna/tgr_frozen,stage_a/luna/tgr_tracker ...), which runs
    its own rebuild checks (fork/rebuild_check.py; in the venv also the env and continuation checks; network blocked);
  - dry: runs fork.run_all.main(<points> --profile luna-dev --dry-run) unchanged. Its soft-stop scan cannot list the
    nano folder (the hook refuses it, os.walk skips it), so the spend it prints leaves out the running nano job. A dry
    run decides nothing on that number.
  - counts: standard library only (no fork import): the Part 7 counts from the points and rates files.
Run from predicate_correctness/ (venv for points and dry; any Python for counts):
  PYTHONDONTWRITEBYTECODE=1 nice -n 10 ~/venvs/tau-bench/bin/python -B -m scoring.v2_p7a_stage_a_luna points
  PYTHONDONTWRITEBYTECODE=1 nice -n 10 ~/venvs/tau-bench/bin/python -B -m scoring.v2_p7a_stage_a_luna dry
  PYTHONDONTWRITEBYTECODE=1 /home/azureuser/miniconda3/bin/python3 -B -m scoring.v2_p7a_stage_a_luna counts
Never imports gold code.
"""
from __future__ import annotations

import collections
import json
import os
import sys

sys.dont_write_bytecode = True

PC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CWD = os.getcwd()
OUT = os.path.join(PC, "output")
EV2 = os.path.join(OUT, "eval_v2")
POINTS = os.path.join(EV2, "fork_points_stage_a_luna.jsonl")
RATES = os.path.join(EV2, "fork_rates_stage_a_luna.json")
MD = os.path.join(EV2, "checks", "rebuild_stage_a_luna.md")
RUNS = ("stage_a/luna/tgr_frozen", "stage_a/luna/tgr_tracker")
FORBIDDEN = (os.path.join(EV2, "stage_a", "nano"), os.path.join(OUT, "_llmcache", "v2_stage_a_nano"))
FORBIDDEN_PREFIX = (os.path.join(OUT, "logs", "v2_stage_a_nano_"),)
SOCKET_EVENTS = ("socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.create_connection")

BLOCKED = []                                   # (event, path) refused by the hook
SEEN = collections.Counter()                   # opened / listed paths under stage_a/luna, by event
NET = collections.Counter()                    # socket events seen (the fork code's own hooks refuse them)


def _path(x):
    if isinstance(x, int) or x is None:
        return None
    try:
        p = os.fsdecode(os.fspath(x))
    except TypeError:
        return None
    if not os.path.isabs(p):
        p = os.path.join(CWD, p)
    return os.path.normpath(p)


def _forbidden(p):
    return any(p == r or p.startswith(r + os.sep) for r in FORBIDDEN) or any(p.startswith(r) for r in FORBIDDEN_PREFIX)


def _hook(event, args):
    if event in SOCKET_EVENTS:
        NET[event] += 1
        return
    if event not in ("open", "os.listdir", "os.scandir", "glob.glob", "glob.glob/2"):
        return
    p = _path(args[0]) if args else None
    if p is None:
        return
    if _forbidden(p):
        BLOCKED.append((event, p))
        if event.startswith("glob"):
            return                              # glob then calls scandir, which is refused
        raise PermissionError(f"P7A: the live nano run is not read ({event} {p})")
    if p.startswith(os.path.join(EV2, "stage_a", "luna") + os.sep):
        SEEN[event] += 1


def _summary(extra):
    out = {"blocked_nano_accesses": len(BLOCKED), "blocked_examples": BLOCKED[:10],
           "stage_a_luna_accesses": dict(SEEN), "socket_events_seen": dict(NET)}
    out.update(extra)
    print("[p7a] SUMMARY " + json.dumps(out, default=str), flush=True)


def points() -> int:
    import fork.find_points as FP
    FP.AGENTS = {"luna": FP.AGENTS["luna"]}                 # only the luna folder of stage_a/ is listed
    rc = FP.main(["--source", "stage_a", "--runs", ",".join(RUNS), "--out", POINTS, "--rates", RATES, "--md", MD])
    from fork import rebuild_check as RC
    from guard import write_guard
    _summary({"find_points_rc": rc, "network_attempts_refused": len(RC.NETWORK_ATTEMPTS),
              "refused_writes": list(write_guard.REFUSED), "venv": RC.venv_available()})
    return rc


def dry() -> int:
    from fork import run_all as RA
    from guard import write_guard
    rt = RA.TauRuntime(RA.BRANCHES)
    res = RA.main([POINTS, "--profile", "luna-dev", "--dry-run"], runtime=rt)
    d = res.get("dry_run") or {}
    _summary({"forks": res.get("forks"), "forks_by_kind": res.get("forks_by_kind"),
              "forks_by_source": res.get("forks_by_source"), "dry_run": d,
              "agent_user_usage_main_thread": rt.usage(), "refused_writes": list(write_guard.REFUSED),
              "write_guard": res.get("write_guard"), "network_blocked": res.get("network_blocked"),
              "soft_stop_status_without_nano": res.get("soft_stop")})
    return 0 if not d.get("problems") else 1


def counts() -> int:
    """The Part 7 counts (standard library only)."""
    with open(RATES, encoding="utf-8") as f:
        rates = json.load(f)
    with open(POINTS, encoding="utf-8") as f:
        kept = [json.loads(x) for x in f if x.strip()]
    dropped = {r["fork_id"]: r["reasons"] for r in (rates.get("rebuild_check") or {}).get("dropped") or []}
    by_run = {}
    for r in rates["rows"]:
        g = r["run"].split("/")[-1]
        n = r.get("conversations", 0)
        pts = [p for p in kept if p["run"] == r["run"]]
        rebuilt_a = [p for p in pts if p.get("feedback_a_source") == "rebuilt"]
        by_run[g] = {
            "files": r.get("files"), "judge_cache": r.get("judge_cache"),
            "lines": r.get("lines", 0), "error lines": r.get("error lines", 0),
            "later duplicate lines (first kept)": r.get("later duplicate lines (first kept)", 0),
            "skipped: models": r.get("skipped: models not gpt-6-luna / gpt-5-nano", 0),
            "skipped: other profile": r.get("skipped: other profile", 0),
            "skipped: other guard": r.get("skipped: other guard", 0),
            "conversations": n, "checks compared": r.get("checks compared", 0),
            "checks not comparable": r.get("checks not comparable", 0), "offline errors": r.get("offline errors", 0),
            "changed attempts: block removed": r.get("changed attempts: block removed", 0),
            "changed attempts: block added": r.get("changed attempts: block added", 0),
            "forks found": r.get("with fork", 0), "found: block removed": r.get("block removed", 0),
            "found: block added": r.get("block added", 0),
            "fork rate found": r.get("fork_rate"),
            "forks kept": len(pts),
            "kept: block removed": sum(p["kind"] == "block removed" for p in pts),
            "kept: block added": sum(p["kind"] == "block added" for p in pts),
            "fork rate kept": round(len(pts) / n, 4) if n else None,
            "fork rate kept: block removed": round(sum(p["kind"] == "block removed" for p in pts) / n, 4) if n else None,
            "fork rate kept: block added": round(sum(p["kind"] == "block added" for p in pts) / n, 4) if n else None,
            "dropped": sorted(k for k in dropped if k.startswith(f"stage_a.{r['run'].replace('/', '_')}.")),
            "no-effect differences skipped": r.get("differences skipped: cap override, no effect", 0),
            "conversations with only no-effect differences": r.get("conversations with only no-effect differences", 0),
            "not comparable before the fork (forks)": r.get("not comparable before the fork", 0),
            "not comparable before the fork (checks, kept forks)": sum(p.get("not_comparable_before", 0) for p in pts),
            "no_effect_before (kept forks)": sum(p.get("no_effect_before", 0) for p in pts),
            "cap-override forks (found)": r.get("fork at a cap override try", 0),
            "cap-override forks (kept)": sum(bool(p.get("cap_override_at_fork")) for p in pts),
            "fork at a later try (kept)": sum(p.get("attempt", 1) > 1 for p in pts),
            "frozen block messages rebuilt (A blocks, tracker source)": len(rebuilt_a),
            "judge evidence of rebuilt frozen block messages": dict(collections.Counter(
                s for p in rebuilt_a for s in (p.get("judge_evidence_from") or {}).values())),
            "rebuilt frozen block messages with missing evidence": sum(
                "missing" in (p.get("judge_evidence_from") or {}).values() for p in rebuilt_a),
            "rebuilt frozen block messages with cache evidence": sum(
                "cache" in (p.get("judge_evidence_from") or {}).values() for p in rebuilt_a),
            "frozen without judge evidence (rates row)": r.get("frozen block message without judge evidence", 0),
            "feedback sources (A / B)": dict(collections.Counter(
                f"{p.get('feedback_a_source')} / {p.get('feedback_b_source')}" for p in pts)),
            "actions at the fork": dict(collections.Counter(p["action"] for p in pts).most_common()),
            "changed predicates at the fork": dict(collections.Counter(
                c["name"] for p in pts for c in p.get("changed_predicates") or []).most_common()),
            "source reward of kept forks": dict(collections.Counter(str(p.get("source_reward")) for p in pts)),
            "domains": sorted({p["domain"] for p in pts}), "task_split": sorted({p["task_split"] for p in pts}),
            "profiles": sorted({p["profile"] for p in pts}),
        }
    all_kept = len(kept)
    out = {"points_found": rates.get("points_found"), "points_kept": rates.get("points_kept"),
           "kept_in_file": all_kept, "dropped": dropped,
           "rebuild_check": {k: v for k, v in (rates.get("rebuild_check") or {}).items() if k != "dropped"},
           "by_guard": by_run, "totals": rates.get("totals"),
           "kinds_kept": dict(collections.Counter(p["kind"] for p in kept)),
           "fork ids unique": len({p["fork_id"] for p in kept}) == all_kept,
           "sources": sorted({p["source"] for p in kept}), "agents": sorted({p["agent"] for p in kept}),
           "episodes paths": sorted({p["episodes_path"] for p in kept})}
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode in ("points", "dry"):
        sys.addaudithook(_hook)                 # first, before any fork code is imported
        sys.exit(points() if mode == "points" else dry())
    if mode == "counts":
        sys.exit(counts())
    raise SystemExit("usage: python -B -m scoring.v2_p7a_stage_a_luna points | dry | counts")
