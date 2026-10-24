"""Eval v2: the $100 soft stop (docs/planning/tracker_eval_v2/overview.md, "Cost").

Rule: while the total LLM spend is under $100, go on. At $100 or more, go on only if the estimated cost of the work
left is $30 or less (then finish, and write down the final total); otherwise stop starting new work.

Fixed interface (fork/run_all.py of Part 3 imports it; do not rename):
  SOFT_STOP_USD, FINISH_IF_LEFT_USD, EVAL_V2_DIR
  spent_usd(root=EVAL_V2_DIR) -> float
  spent_report(root=EVAL_V2_DIR) -> dict
  decide(spent, left_estimate) -> (go, reason)

What counts as spend (everything recorded under root, read only):
  - every line of every file named episodes*.jsonl, at any depth (Stage A, smoke, ...): the conversation's "cost"
    field summed over its roles (agent + user + guard), as the p10 cost tables did (cost_of in the p10 runs check
    script). An error line has no "cost" field; it counts the agent and user cost in its
    "usage_roles" (the guard's cost of a failed conversation is lost inside the copied episode loop; small);
  - the top-level "cost_usd" of every *.json file at any depth under a folder named stage_b (Stage B try files).
    Do not also write episodes*.jsonl under stage_b, or that spend counts twice.
  A line or file that cannot be read counts 0 and is listed in spent_report(root)["unreadable"]; a stage_b JSON file
  without a numeric cost_usd counts 0 and is listed in ["no_cost_usd"].
Judge calls answered from the cache are counted at their first price (the copy's "fresh-equivalent" accounting), so
the spend is never under the real one for that reason.

Extra helpers for the runners: SpendScanner (incremental: reads only the new bytes of growing files), line_cost,
JsonlTail, Gate (sticky stop, used by guard/run_online.py before each new unit).
Standard library only. Never imports gold code or the runner copy.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Callable, Dict, List, Optional, Tuple

from state_tracker import paths

SOFT_STOP_USD = 100.0
FINISH_IF_LEFT_USD = 30.0
EVAL_V2_DIR = os.path.join(paths.OUTPUT_DIR, "eval_v2")
STAGE_B_DIRNAME = "stage_b"


def is_episodes_file(name: str) -> bool:
    return name.startswith("episodes") and name.endswith(".jsonl")


def _num(x) -> float:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else 0.0


def line_cost(rec) -> float:
    """The LLM cost of one episodes line: sum of rec["cost"] (agent, user, guard); for a line without "cost" (an
    error line), the agent and user cost in rec["usage_roles"]."""
    if not isinstance(rec, dict):
        return 0.0
    c = rec.get("cost")
    if isinstance(c, dict) and c:
        return sum(_num(v) for v in c.values())
    u = rec.get("usage_roles")
    if isinstance(u, dict):
        return sum(_num(r.get("cost")) for r in u.values() if isinstance(r, dict))
    return 0.0


class JsonlTail:
    """Reads the new complete lines of growing JSONL files (per file: inode and byte offset). A line still being
    written (no final newline) is kept for the next read, unless final=True (then it is read, or listed as
    unreadable)."""

    def __init__(self):
        self._pos: Dict[str, Tuple[int, int, int]] = {}      # path -> (inode, offset, line number)

    def forget(self, path: str) -> None:
        self._pos.pop(path, None)

    def read_new(self, path: str, final: bool = False, bad: Optional[List[dict]] = None) -> Tuple[List[dict], bool]:
        """(new records, restarted). restarted: the file was replaced or cut since the last read, so it was read
        again from the start (the caller must drop what it counted before). Bad lines go to `bad` (1-based line)."""
        bad = bad if bad is not None else []
        try:
            st = os.stat(path)
        except OSError as e:
            bad.append({"path": path, "line": None, "error": f"stat: {e}"})
            return [], False
        restarted = False
        inode, off, n = self._pos.get(path, (st.st_ino, 0, 0))
        if inode != st.st_ino or st.st_size < off:            # replaced or cut: read again from the start
            off, n, inode, restarted = 0, 0, st.st_ino, True
        if st.st_size == off:
            self._pos[path] = (inode, off, n)
            return [], restarted
        try:
            with open(path, "rb") as f:
                f.seek(off)
                chunk = f.read(st.st_size - off)
        except OSError as e:
            bad.append({"path": path, "line": None, "error": f"read: {e}"})
            return [], restarted
        lines = chunk.split(b"\n")
        tail = lines.pop()                                    # b"" when the chunk ends with a newline
        if tail and final:
            lines.append(tail)
            tail = b""
        self._pos[path] = (inode, off + len(chunk) - len(tail), n + len(lines))
        out = []
        for raw in lines:
            n += 1
            if not raw.strip():
                continue
            try:
                rec = json.loads(raw)
            except ValueError as e:
                bad.append({"path": path, "line": n, "error": f"json: {e}"})
                continue
            if not isinstance(rec, dict):
                bad.append({"path": path, "line": n, "error": "not a JSON object"})
                continue
            out.append(rec)
        return out, restarted


class SpendScanner:
    """The spend under `root` (rules in the module docstring). scan() can be called again and again: growing
    episodes files are read from where the last scan stopped; stage_b files are read again only when they change."""

    def __init__(self, root: str = EVAL_V2_DIR, final: bool = False):
        self.root = root
        self.final = final
        self._tail = JsonlTail()
        self._ep: Dict[str, dict] = {}     # path -> {"usd", "lines", "error_lines", "error_usd", "bad": [...]}
        self._sb: Dict[str, dict] = {}     # path -> {"key", "usd", "problem"}
        self._lock = threading.Lock()

    def _walk(self):
        eps, sbs = [], []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames.sort()
            in_b = STAGE_B_DIRNAME in os.path.relpath(dirpath, self.root).split(os.sep)
            for name in sorted(filenames):
                p = os.path.join(dirpath, name)
                if is_episodes_file(name):
                    eps.append(p)
                elif in_b and name.endswith(".json"):
                    sbs.append(p)
        return eps, sbs

    def _scan_episodes(self, path: str) -> None:
        s = self._ep.setdefault(path, {"usd": 0.0, "lines": 0, "error_lines": 0, "error_usd": 0.0, "bad": []})
        bad: List[dict] = []
        recs, restarted = self._tail.read_new(path, final=self.final, bad=bad)
        if restarted:                                         # replaced or cut: count it again from the start
            s.update(usd=0.0, lines=0, error_lines=0, error_usd=0.0, bad=[])
        s["bad"].extend(bad)
        for rec in recs:
            c = line_cost(rec)
            s["usd"] += c
            s["lines"] += 1
            if rec.get("error") is not None:
                s["error_lines"] += 1
                s["error_usd"] += c

    def _scan_stage_b(self, path: str) -> None:
        try:
            st = os.stat(path)
            key = (st.st_ino, st.st_size, st.st_mtime_ns)
        except OSError as e:
            self._sb[path] = {"key": None, "usd": 0.0, "problem": ("unreadable", f"stat: {e}")}
            return
        old = self._sb.get(path)
        if old is not None and old["key"] == key:
            return
        usd, problem = 0.0, None
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            v = d.get("cost_usd") if isinstance(d, dict) else None
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                usd = float(v)
            else:
                problem = ("no_cost_usd", "no numeric top-level cost_usd")
        except (OSError, ValueError) as e:
            problem = ("unreadable", f"{type(e).__name__}: {e}")
        self._sb[path] = {"key": key, "usd": usd, "problem": problem}

    def scan(self) -> dict:
        """Scan again; returns the report (see spent_report)."""
        with self._lock:
            if not os.path.isdir(self.root):
                self._ep, self._sb = {}, {}
                return self._report()
            eps, sbs = self._walk()
            for p in set(self._ep) - set(eps):
                self._ep.pop(p)
                self._tail.forget(p)
            for p in set(self._sb) - set(sbs):
                self._sb.pop(p)
            for p in eps:
                self._scan_episodes(p)
            for p in sbs:
                self._scan_stage_b(p)
            return self._report()

    def total(self) -> float:
        return self.scan()["total_usd"]

    def _report(self) -> dict:
        rel = lambda p: os.path.relpath(p, self.root)          # noqa: E731
        ep_usd = float(sum(s["usd"] for s in self._ep.values()))
        sb_usd = float(sum(s["usd"] for s in self._sb.values()))
        unreadable = [dict(b, path=rel(b["path"])) for s in self._ep.values() for b in s["bad"]]
        unreadable += [{"path": rel(p), "line": None, "error": s["problem"][1]} for p, s in sorted(self._sb.items())
                       if s["problem"] and s["problem"][0] == "unreadable"]
        return {
            "root": self.root, "total_usd": ep_usd + sb_usd,
            "episodes_usd": ep_usd, "episode_files": len(self._ep),
            "episode_lines": sum(s["lines"] for s in self._ep.values()),
            "error_lines": sum(s["error_lines"] for s in self._ep.values()),
            "error_lines_usd": sum(s["error_usd"] for s in self._ep.values()),
            "stage_b_usd": sb_usd, "stage_b_files": len(self._sb),
            "no_cost_usd": sorted(rel(p) for p, s in self._sb.items() if s["problem"] and s["problem"][0] == "no_cost_usd"),
            "unreadable": unreadable,
            "by_file": {rel(p): round(s["usd"], 6) for p, s in sorted({**self._ep, **self._sb}.items())},
            "soft_stop_usd": SOFT_STOP_USD, "finish_if_left_usd": FINISH_IF_LEFT_USD,
        }


def spent_report(root: str = EVAL_V2_DIR) -> dict:
    """One full scan of root: total and parts of the spend, and every line or file that counted 0 because it could
    not be read (a last line without its newline is read too)."""
    return SpendScanner(root, final=True).scan()


def spent_usd(root: str = EVAL_V2_DIR) -> float:
    """Total LLM cost (USD) recorded under root (rules in the module docstring)."""
    return spent_report(root)["total_usd"]


def decide(spent: float, left_estimate: float) -> Tuple[bool, str]:
    """(go, reason). Go while spent < $100. At $100 or more, go only if the work left is estimated at $30 or less."""
    if spent < SOFT_STOP_USD:
        return True, f"spent ${spent:.2f} < ${SOFT_STOP_USD:.2f}"
    if left_estimate <= FINISH_IF_LEFT_USD:
        return True, (f"spent ${spent:.2f} >= ${SOFT_STOP_USD:.2f}, but the work left is estimated at "
                      f"${left_estimate:.2f} <= ${FINISH_IF_LEFT_USD:.2f}: finish")
    return False, (f"spent ${spent:.2f} >= ${SOFT_STOP_USD:.2f} and the work left is estimated at "
                   f"${left_estimate:.2f} > ${FINISH_IF_LEFT_USD:.2f}")


class Gate:
    """Asked before each new unit of work. `left_fn()` gives the estimated cost (USD) of the work left. The stop is
    sticky: once a check says stop, every later check says stop too (running work is left to finish)."""

    def __init__(self, left_fn: Callable[[], float], root: str = EVAL_V2_DIR, scanner: Optional[SpendScanner] = None):
        self.left_fn = left_fn
        self.scanner = scanner or SpendScanner(root)
        self.stopped: Optional[dict] = None
        self.last: Optional[dict] = None
        self.checks = 0
        self._lock = threading.Lock()

    def check(self) -> Tuple[bool, str, float, float]:
        """(go, reason, spent, left_estimate)."""
        with self._lock:
            self.checks += 1
            if self.stopped is not None:
                s = self.stopped
                return False, s["reason"], s["spent"], s["left"]
            spent = self.scanner.total()
            left = float(self.left_fn())
            go, reason = decide(spent, left)
            self.last = {"go": go, "reason": reason, "spent": spent, "left": left}
            if not go:
                self.stopped = dict(self.last)
            return go, reason, spent, left
