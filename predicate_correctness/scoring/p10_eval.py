"""Part 10, subtask 9: run the partner's metric and gold scorer scripts (copies) on our runs and the baselines.

The copies are in from_shieldagent/scoring/ with the partner's folder layout (scripts/, policies/, aspm/, exp_core/).
They find every input and output from ROOT = three folders above the script file, and they know only the guard names
none, direct, shield, tgr, tgr_nob, tgr_noc, tgr_noa. So, without editing the copies:

1. `build` makes an evaluation root, output/eval/, that looks like the partner's repository:
     output/eval/scripts   -> ../../from_shieldagent/scoring/scripts     (symlink; ROOT of a script = output/eval,
     output/eval/policies  -> ../../from_shieldagent/scoring/policies     because os.path.abspath keeps symlinks)
     output/eval/aspm      -> ../../from_shieldagent/scoring/aspm
     output/eval/exp_core  -> ../../from_shieldagent/scoring/exp_core
     output/eval/agent/predicates -> ../../../from_shieldagent/gold        (gold code, Part 7 copy; scoring only)
     output/eval/output/repro/p6/                                          (empty; the scripts' base path)
     output/eval/output/tgr/online/<tag>/<env>/<guard>/episodes.jsonl     (symlinks to the runs)
   Tags (one pair per experiment):
     <baseline tag> (luna_train_v5, nano_train, luna_val): none, direct, tgr = the partner's runs (our copies in
                     from_shieldagent/runs/);
     <our tag> (p10_luna_train, p10_nano_train, p10_luna_val): none and direct = the same baseline files, and
                     tgr = OUR tgr_tracker run (output/online/<tag>/<env>/tgr_tracker/episodes.jsonl). The folder is
                     named "tgr" only because the copied scripts know no other name; it holds tgr_tracker.
   The smoke tag p10_smoke is not used.
2. `score <tag> ...` runs, for each tag, the same 5 steps as the copy's scripts/tgr/metrics.py (p6_gold_score v1,
   p6_metrics v1, p6_gold_score v2, p6_metrics v2, gold_compare), then metrics.py --skip-p6. Each step runs in a new
   Python process (-B, PYTHONDONTWRITEBYTECODE=1) started through `launch`, which first installs our write guard
   (guard/write_guard.py: every write must land in predicate_correctness/output/, any access to ~/ShieldAgent is
   refused). The outputs (gold.jsonl, gold_v2.jsonl, metrics.json, metrics_gold_v2.json, gold_compare.json,
   metrics_tgr.json) land in output/eval/output/tgr/online/<tag>/...
3. `launch <script> [args]` (internal): install the write guard, then run the script as __main__.

Run from predicate_correctness/ with the standard-library Python:
    python3 -B -m scoring.p10_eval build
    python3 -B -m scoring.p10_eval score luna_train_v5 p10_luna_train
No LLM calls. Gold code is used here only for scoring (overview.md ground rule 5).
"""
from __future__ import annotations

import os
import runpy
import subprocess
import sys
import time

sys.dont_write_bytecode = True

PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(PC_DIR, "output")
EVAL = os.path.join(OUT, "eval")
FROM_SA = os.path.join(PC_DIR, "from_shieldagent")
SCORING_COPY = os.path.join(FROM_SA, "scoring")
GOLD_COPY = os.path.join(FROM_SA, "gold")
ENVS = ("airline", "retail")
BASE_GUARDS = ("none", "direct", "tgr")

# experiment -> (baseline tag = partner run name, our tag)
EXPERIMENTS = {
    "train, luna-dev": ("luna_train_v5", "p10_luna_train"),
    "train, nano-agent-luna": ("nano_train", "p10_nano_train"),
    "val, luna-dev": ("luna_val", "p10_luna_val"),
}
OUR_TAGS = {ours: base for base, ours in EXPERIMENTS.values()}
BASE_TAGS = {base for base, _ in EXPERIMENTS.values()}

# The 5 steps of the copy's scripts/tgr/metrics.py (same order and arguments), then metrics.py --skip-p6.
STEPS = (("p6_gold_score.py", []), ("p6_metrics.py", []), ("p6_gold_score.py", ["--gold", "v2"]),
         ("p6_metrics.py", ["--gold", "v2"]), ("gold_compare.py", []))


def episodes_source(tag: str, env: str, guard: str) -> str:
    """The real episodes.jsonl that output/eval/output/tgr/online/<tag>/<env>/<guard>/episodes.jsonl points to."""
    if tag in BASE_TAGS:
        return os.path.join(FROM_SA, "runs", tag, env, guard, "episodes.jsonl")
    if tag in OUR_TAGS:
        if guard == "tgr":
            return os.path.join(OUT, "online", tag, env, "tgr_tracker", "episodes.jsonl")
        return os.path.join(FROM_SA, "runs", OUR_TAGS[tag], env, guard, "episodes.jsonl")
    raise ValueError(f"unknown tag {tag!r}")


def _link(target: str, link: str) -> None:
    """Make a relative symlink link -> target (replace a wrong one; never touch a real file)."""
    rel = os.path.relpath(target, os.path.dirname(link))
    if os.path.islink(link):
        if os.readlink(link) == rel:
            return
        os.remove(link)
    elif os.path.exists(link):
        raise FileExistsError(f"{link} exists and is not a symlink")
    os.makedirs(os.path.dirname(link), exist_ok=True)
    os.symlink(rel, link)


def build() -> int:
    for name in ("scripts", "policies", "aspm", "exp_core"):
        _link(os.path.join(SCORING_COPY, name), os.path.join(EVAL, name))
    _link(GOLD_COPY, os.path.join(EVAL, "agent", "predicates"))
    os.makedirs(os.path.join(EVAL, "output", "repro", "p6"), exist_ok=True)
    n = 0
    for tag in sorted(BASE_TAGS | set(OUR_TAGS)):
        for env in ENVS:
            for guard in BASE_GUARDS:
                src = episodes_source(tag, env, guard)
                if not os.path.exists(src):
                    raise FileNotFoundError(src)
                _link(src, os.path.join(EVAL, "output", "tgr", "online", tag, env, guard, "episodes.jsonl"))
                n += 1
    print(f"eval root {EVAL}: {n} episode links")
    for tag in sorted(BASE_TAGS | set(OUR_TAGS)):
        for env in ENVS:
            for guard in BASE_GUARDS:
                link = os.path.join(EVAL, "output", "tgr", "online", tag, env, guard, "episodes.jsonl")
                print(f"  {os.path.relpath(link, EVAL)} -> {os.path.relpath(os.path.realpath(link), PC_DIR)}")
    return 0


def launch(script: str, args: list) -> None:
    """Install our write guard, then run the copied script as __main__ (in this process)."""
    sys.path.insert(0, PC_DIR)
    from guard import write_guard            # our code (stdlib only); it imports nothing from scoring
    write_guard.install()
    sys.argv = [script, *args]
    runpy.run_path(script, run_name="__main__")


def score(tags: list) -> int:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    for tag in tags:
        if tag not in BASE_TAGS and tag not in OUR_TAGS:
            raise SystemExit(f"unknown tag {tag!r}")
        rel = f"../../tgr/online/{tag}"            # as metrics.py passes it to the P6 scripts
        jobs = [(os.path.join(EVAL, "scripts", "reproduction", s), [rel, *extra]) for s, extra in STEPS]
        jobs.append((os.path.join(EVAL, "scripts", "tgr", "metrics.py"), [tag, "--guards", ",".join(BASE_GUARDS),
                                                                           "--skip-p6"]))
        for script, args in jobs:
            t0 = time.time()
            r = subprocess.run([sys.executable, "-B", "-m", "scoring.p10_eval", "launch", script, *args],
                               cwd=PC_DIR, env=env, capture_output=True, text=True)
            name = os.path.relpath(script, EVAL)
            print(f"=== {tag}: {name} {' '.join(args)} (rc {r.returncode}, {time.time() - t0:.0f} s)")
            print(r.stdout[-6000:])
            if r.returncode:
                print(r.stderr[-4000:])
                raise SystemExit(f"{name} failed for {tag}")
        print(f"DONE {tag}", flush=True)
    return 0


def main(argv: list) -> int:
    if not argv:
        raise SystemExit(__doc__)
    cmd, rest = argv[0], argv[1:]
    if cmd == "build":
        return build()
    if cmd == "score":
        return score(rest)
    if cmd == "launch":
        launch(rest[0], rest[1:])
        return 0
    raise SystemExit(f"unknown command {cmd!r}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
