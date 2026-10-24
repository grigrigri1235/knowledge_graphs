"""Eval v2: one progress line for output/eval_v2/progress.md (main chat; standard library, read only, no LLM).

Counts the Stage A lines per agent and guard (good / error), the Stage B try files, the spend (guard/soft_stop.py),
and the runner processes alive. Run from predicate_correctness/:
  /home/azureuser/miniconda3/bin/python3 -B -m scoring.v2_progress_tick
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import time

sys.dont_write_bytecode = True
PC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PC)

from guard import soft_stop  # noqa: E402

EVAL = os.path.join(PC, "output", "eval_v2")


def stage_a() -> str:
    parts = []
    for agent in ("luna", "nano"):
        counts = {}
        for guard in ("tgr_frozen", "tgr_tracker"):
            good, bad = set(), 0
            for path in glob.glob(os.path.join(EVAL, "stage_a", agent, guard, "episodes*.jsonl")):
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        try:
                            d = json.loads(line)
                        except ValueError:
                            continue
                        if d.get("error"):
                            bad += 1
                        else:
                            good.add((d.get("task_index"), d.get("trial")))
            counts[guard] = (len(good), bad)
        if any(g or b for g, b in counts.values()):
            parts.append(f"{agent}: frozen {counts['tgr_frozen'][0]}/500, tracker {counts['tgr_tracker'][0]}/500"
                         + (f", error lines {counts['tgr_frozen'][1] + counts['tgr_tracker'][1]}"
                            if counts['tgr_frozen'][1] + counts['tgr_tracker'][1] else ""))
    return "; ".join(parts) or "no lines yet"


def stage_b() -> str:
    tries = [p for p in glob.glob(os.path.join(EVAL, "stage_b", "*", "*", "*.json")) if ".failed" not in p]
    return f"Stage B tries {len(tries)}" if tries else ""


def alive() -> int:
    out = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True).stdout
    return sum(1 for line in out.splitlines()
               if ("guard.run_online" in line or "fork.run_all" in line) and "--dry-run" not in line)


def main() -> None:
    line = f"- {time.strftime('%H:%M', time.gmtime())} auto: Stage A {stage_a()}"
    b = stage_b()
    if b:
        line += f"; {b}"
    line += f"; runner processes {alive()}; spend ${soft_stop.spent_usd():.2f}"
    print(line)


if __name__ == "__main__":
    main()
