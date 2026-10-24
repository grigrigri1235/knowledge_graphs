"""Eval v2 Part 3b (fork/run_all.py): run the Stage B branch tries for a set of fork points (resumable).

For each fork point × branch (A: frozen TGR, B: TGR + tracker) × try: check the source line (run_branch.load_source),
rebuild the fork state (fork/rebuild.py), build the env at the fork (no LLM call), continue the conversation in that
branch (fork/run_branch.py) and save output/eval_v2/stage_b/<fork_id>/<branch>/<try>.json. Each try has its own fresh
judge cache, output/_llmcache/eval_v2_stage_b/<fork_id>/<branch>/<try>/structured/ (fork/branch_cache.py), with one
record put in before the try starts: the source judge's answer to the fork attempt's prompt (fork/judge_seed.py;
audit A5 W1). So an exact repeat of the blocked fork call is a cache hit with the same answer, as in the source run;
every other judge prompt is a fresh call. The try file's judge_seed says whether the seed was written. Agent and
user calls are never cached (fresh, as in the wrapper).

Launch commands (run from predicate_correctness/ with the venv Python; long runs with setsid nohup, command output
to output/logs/; one process per profile, never two processes on the same forks and out-root):
  dry run first (resolves and prints everything, rebuilds every fork, builds both guards; no LLM call, the network
  is blocked, nothing is written):
    ~/venvs/tau-bench/bin/python -B -m fork.run_all output/eval_v2/fork_points.jsonl --profile luna-dev --dry-run \
        > output/logs/v2_stage_b_luna_dry.log 2>&1
  the runs (Part 8):
    setsid nohup ~/venvs/tau-bench/bin/python -B -m fork.run_all output/eval_v2/fork_points.jsonl \
        --profile luna-dev --branches A,B --tries 5 --workers 8 > output/logs/v2_stage_b_luna.log 2>&1 &
    setsid nohup ~/venvs/tau-bench/bin/python -B -m fork.run_all output/eval_v2/fork_points.jsonl \
        --profile nano-agent-luna --branches A,B --tries 5 --workers 8 > output/logs/v2_stage_b_nano.log 2>&1 &
  smoke test (Part 5), 3 forks × 2 branches × 1 try, in its own folder:
    ~/venvs/tau-bench/bin/python -B -m fork.run_all output/eval_v2/fork_points.jsonl --profile <profile> \
        --ids <id1>,<id2> --tries 1 --out-root output/eval_v2/smoke/stage_b > output/logs/v2_smoke_b_<profile>.log 2>&1
  The same command again resumes: finished tries (a file with error null) are skipped; a failed try is run again
  after its file is renamed to <try>.failed<k>.json (its cache folder to <try>.failed<k>).
Progress lines "[v2-stage-b] ..."; "[v2-stage-b] STOPPED (soft stop): ..." when the soft stop stops new tries; the
final line "[v2-stage-b] DONE: ..." (counts and cost).

Safety, as the wrapper (guard/run_online.py):
  - the write guard (guard/write_guard.py) is installed before any runner code is imported: writes only under
    predicate_correctness/output/ (in a dry run: nowhere), no access to ~/ShieldAgent;
  - profiles luna-dev and nano-agent-luna only; the model of every role of the profile must be gpt-6-luna or
    gpt-5-nano; each fork's profile must be its agent's (fork/schema.py AGENTS);
  - tasks: task_split "test" only for tasks labelled train or val in splits.json (never test); task_split "train"
    only for retail indices 0-499 (Stage A; not looked up in splits.json, the indices collide);
  - the tool schemas must give the rule set's tools_sha256, and the frozen rule files their sha256
    (fork/guards_build.py); TGR + tracker also checks its frozen types and lookups;
  - every fork state is checked against its source conversation (run_branch.check_state) and every env against the
    fork state (branch_env.check_env) before a try;
  - the soft stop (guard/soft_stop.py: spent_usd, decide) before each new try: left_estimate = tries not started ×
    the mean cost of the finished tries (the Part 1 prior per profile if none yet) + --later-left-usd (the main chat
    passes the cost of the later and concurrent jobs, e.g. the other Stage B process; default 0). spent = all LLM spend under
    output/eval_v2/ (soft_stop.SpendScanner before every try, which reads only new or changed files; without it
    spent_usd() every --soft-stop-refresh seconds), plus this run's own spend since the last scan (all of it if the
    out-root is not a stage_b folder under output/eval_v2/, which the scan does not see).

Never imports gold code. Standard library at import time; the runner copy, τ-bench and fork/rebuild.py are imported
inside main().
"""
from __future__ import annotations

import argparse
import contextlib
import inspect
import io
import json
import os
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

sys.dont_write_bytecode = True

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "fork"

from fork import branch_env, run_branch as rb                                  # noqa: E402
from fork.schema import AGENTS, BRANCH_GUARD, BRANCHES, EVAL_V2_DIR, STAGE_B_DIR, ForkPoint   # noqa: E402
from guard import runner_path, write_guard                                     # noqa: E402
from state_tracker import paths                                                # noqa: E402

OUTPUT_DIR = paths.OUTPUT_DIR
LLMCACHE_DIR = os.path.join(OUTPUT_DIR, "_llmcache")
ALLOWED_PROFILES = ("luna-dev", "nano-agent-luna")
ALLOWED_MODELS = ("gpt-6-luna", "gpt-5-nano")
ALLOWED_TEST_LABELS = ("train", "val")
TRAIN_TASKS = {"retail": 500}                      # τ-bench's extra tasks (task_split "train"), retail only
PRIOR_USD_PER_TRY = {"luna-dev": 0.0028, "nano-agent-luna": 0.0154}   # output/eval_v2/checks/part1.md section 6
TAG = "[v2-stage-b]"

_print_lock = threading.Lock()


class RunRefused(SystemExit):
    """A safety rule refuses the run (profile, model, task, path or fork point)."""


def say(text: str) -> None:
    with _print_lock:
        print(f"{TAG} {text}", flush=True)


def _under(path: str, root: str) -> bool:
    p, r = os.path.realpath(path), os.path.realpath(root)
    return p == r or p.startswith(r + os.sep)


# ------------------------------------------------------------------------------------------------ fork points

def load_points(files: List[str], ids: Optional[str] = None) -> List[ForkPoint]:
    """Fork points from one or more jsonl files, in file order; the same fork_id twice must be the same point."""
    seen: Dict[str, dict] = {}
    order: List[str] = []
    for fn in files:
        with open(fn, encoding="utf-8") as f:
            for n, line in enumerate(f):
                if not line.strip():
                    continue
                d = json.loads(line)
                fid = d.get("fork_id")
                if fid in seen:
                    if seen[fid] != d:
                        raise RunRefused(f"fork_id {fid!r} appears twice with different content ({fn} line {n})")
                    continue
                seen[fid] = d
                order.append(fid)
    if ids:
        want = [x.strip() for x in ids.split(",") if x.strip()]
        missing = [x for x in want if x not in seen]
        if missing:
            raise RunRefused(f"--ids not in the fork points files: {missing}")
        order = [x for x in order if x in set(want)]
    return [ForkPoint.from_dict(seen[x]) for x in order]


def task_refusal(f: ForkPoint, labels: Dict[str, Dict[str, str]]) -> Optional[str]:
    """Why a fork's task is refused (None if allowed). Never the partner's test group."""
    if f.task_split == "test":
        label = labels.get(f.domain, {}).get(str(f.task_index))
        if label not in ALLOWED_TEST_LABELS:
            return (f"{f.fork_id}: {f.domain} test-split task {f.task_index} is labelled {label!r} in splits.json "
                    f"(only {ALLOWED_TEST_LABELS})")
    elif f.task_split == "train":
        n = TRAIN_TASKS.get(f.domain)
        if n is None or not 0 <= f.task_index < n:
            return f"{f.fork_id}: train-split task {f.domain}/{f.task_index} refused (only retail 0-499)"
    else:
        return f"{f.fork_id}: task_split {f.task_split!r} refused (only 'test' with label train/val, or 'train')"
    return None


def check_points(forks: List[ForkPoint], splits_file: str = paths.SPLITS_FILE) -> None:
    """Refuse the run if any fork point breaks a safety rule or is inconsistent."""
    with open(splits_file, encoding="utf-8") as f:
        labels = {d: v["split"] for d, v in json.load(f).items()}
    problems = []
    for fp in forks:
        if fp.domain not in paths.DOMAINS:
            problems.append(f"{fp.fork_id}: unknown domain {fp.domain!r}")
        if fp.profile not in ALLOWED_PROFILES or AGENTS.get(fp.agent) != fp.profile:
            problems.append(f"{fp.fork_id}: agent {fp.agent!r} / profile {fp.profile!r} refused "
                            f"(only {AGENTS})")
        r = task_refusal(fp, labels)
        if r:
            problems.append(r)
        problems += [f"{fp.fork_id}: {p}" for p in rb.check_fork_point(fp)]
    if problems:
        raise RunRefused(f"{len(problems)} fork point problem(s): " + " | ".join(problems[:20]))


def pick_profile(forks: List[ForkPoint], profile: Optional[str]) -> tuple:
    """(profile, forks of that profile, number of forks of another profile). One process serves one profile."""
    profs = sorted({f.profile for f in forks})
    if profile is None:
        if len(profs) != 1:
            raise RunRefused(f"the fork points have profiles {profs}: pass --profile (one process per profile)")
        profile = profs[0]
    if profile not in ALLOWED_PROFILES:
        raise RunRefused(f"profile {profile!r} refused: only {ALLOWED_PROFILES}")
    mine = [f for f in forks if f.profile == profile]
    return profile, mine, len(forks) - len(mine)


def default_cache_root(out_root: str) -> str:
    """output/_llmcache/eval_v2_stage_b for the default out-root (one cache root per out-root)."""
    rel = os.path.relpath(os.path.realpath(out_root), os.path.realpath(OUTPUT_DIR))
    return os.path.join(LLMCACHE_DIR, rel.replace(os.sep, "_"))


def resolve_roots(out_root: str, cache_root: Optional[str]) -> tuple:
    cache_root = cache_root or default_cache_root(out_root)
    for name, p in (("--out-root", out_root), ("--cache-root", cache_root)):
        if not _under(p, OUTPUT_DIR) or os.path.realpath(p) == os.path.realpath(OUTPUT_DIR):
            raise RunRefused(f"{name} {p} is not a folder under {OUTPUT_DIR}")
    if _under(out_root, cache_root) or _under(cache_root, out_root):
        raise RunRefused("--out-root and --cache-root must not contain each other")
    return os.path.realpath(out_root), os.path.realpath(cache_root)


def spend_seen_by_soft_stop(out_root: str) -> bool:
    """Does guard/soft_stop.py spent_usd() (stage_b/ folders under output/eval_v2/) see this run's try files?"""
    if not _under(out_root, EVAL_V2_DIR):
        return False
    return "stage_b" in os.path.relpath(os.path.realpath(out_root), os.path.realpath(EVAL_V2_DIR)).split(os.sep)


# ------------------------------------------------------------------------------------------------ try files

def read_try(path: str) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def try_status(path: str) -> tuple:
    """("todo" | "done" | "failed", the record or None)."""
    if not os.path.exists(path):
        return "todo", None
    r = read_try(path)
    if r is not None and r.get("error") is None:
        return "done", r
    return "failed", r


def _free(base: str, suffix: str, ext: str = "") -> str:
    k = 1
    while os.path.exists(f"{base}.{suffix}{k}{ext}"):
        k += 1
    return f"{base}.{suffix}{k}{ext}"


def prepare_try(path: str, cache_dir: str) -> Dict[str, str]:
    """Before a try runs: keep a failed try's output (<try>.failed<k>.json, its cache <try>.failed<k>), and move a
    cache folder left without a try file (a killed run) to <try>.stale<k>, so every try starts with an empty cache."""
    moved = {}
    if os.path.exists(path):
        new = _free(path[:-len(".json")], "failed", ".json")
        os.rename(path, new)
        moved["try"] = new
        if os.path.isdir(cache_dir):
            k = new[:-len(".json")].rsplit(".failed", 1)[1]
            os.rename(cache_dir, f"{cache_dir}.failed{k}")
            moved["cache"] = f"{cache_dir}.failed{k}"
    elif os.path.isdir(cache_dir):
        new = _free(cache_dir, "stale")
        os.rename(cache_dir, new)
        moved["cache"] = new
    return moved


def write_try(path: str, rec: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp{threading.get_ident()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, default=str)
    os.replace(tmp, path)


def failed_record(f: ForkPoint, branch: str, t: int, e: BaseException, usage: Optional[dict]) -> dict:
    """A try that failed before or outside the branch loop (rebuild, checks, env)."""
    u = json.loads(json.dumps(usage)) if usage else None
    cost = {"agent": u["agent"]["cost"] if u else 0.0, "user": u["user"]["cost"] if u else 0.0, "guard": 0.0}
    return {"task_index": f.task_index, "reward": 0.0, "done": False, "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(), "env": f.domain, "guard": BRANCH_GUARD[branch], "trial": t,
            "profile": f.profile, "stage": "B", "fork_id": f.fork_id, "branch": branch, "try": t,
            "task_split": f.task_split, "source_trial": f.trial, "fork": f.to_dict(), "usage_roles": u,
            "cost": cost, "cost_usd": round(sum(cost.values()), 8)}


# ------------------------------------------------------------------------------------------------ soft stop

class SpendGate:
    """The soft stop before each new try (guard/soft_stop.py: spent_usd(), decide(spent, left_estimate))."""

    def __init__(self, ss: Any, prior: float, finished_costs: List[float], n_todo: int, seen_by_scan: bool,
                 refresh_s: Optional[float] = None, clock: Callable[[], float] = time.time, later_left: float = 0.0):
        self.ss, self.prior, self.costs = ss, prior, list(finished_costs)
        self.not_started = n_todo
        self.later_left = float(later_left)          # --later-left-usd: later and concurrent jobs (audit A2 W1, A5 W2)
        self.seen_by_scan, self.clock = seen_by_scan, clock
        # guard/soft_stop.py SpendScanner reads only new or changed files, so it can scan before every try; the
        # fixed interface spent_usd() reads everything, so it is called again only every refresh_s seconds
        scanner = getattr(ss, "SpendScanner", None)
        self.spend_fn = scanner().total if scanner is not None else ss.spent_usd
        self.refresh_s = refresh_s if refresh_s is not None else (0.0 if scanner is not None else 60.0)
        self.lock = threading.Lock()
        self.base: Optional[float] = None
        self.t_base = 0.0
        self.own_since_scan = 0.0
        self.own_total = 0.0
        self.stopped: Optional[str] = None

    def spent(self) -> float:
        now = self.clock()
        if self.base is None or now - self.t_base >= self.refresh_s:
            self.base, self.t_base, self.own_since_scan = float(self.spend_fn()), now, 0.0
        return self.base + (self.own_since_scan if self.seen_by_scan else self.own_total)

    def mean_cost(self) -> float:
        return sum(self.costs) / len(self.costs) if self.costs else self.prior

    def left(self, mean: float) -> float:
        """The left estimate of every soft-stop check: this run's tries not started × mean + the later jobs."""
        return self.not_started * mean + self.later_left

    def status(self) -> Dict[str, Any]:
        with self.lock:
            spent, mean = self.spent(), self.mean_cost()
            left = self.left(mean)
            go, reason = self.ss.decide(spent, left)
            return {"spent_usd": round(spent, 4), "left_estimate_usd": round(left, 4), "tries_not_started":
                    self.not_started, "mean_cost_per_try": round(mean, 6), "from_prior": not self.costs,
                    "later_left_usd": self.later_left, "go": bool(go), "reason": reason}

    def try_start(self) -> Optional[str]:
        """None: start the try (counted as started). Otherwise the stop reason; no new try starts after it."""
        with self.lock:
            if self.stopped is not None:
                return self.stopped
            spent, mean = self.spent(), self.mean_cost()
            left = self.left(mean)
            go, reason = self.ss.decide(spent, left)
            if not go:
                self.stopped = (f"spent ${spent:.2f}, left estimate ${left:.2f} ({self.not_started} tries not started "
                                f"x ${mean:.4f}{' prior' if not self.costs else ''} + later jobs "
                                f"${self.later_left:.2f}): {reason}")
                say(f"STOPPED (soft stop): {self.stopped}; no new try starts")
                return self.stopped
            self.not_started -= 1
            return None

    def finished(self, cost: float, ok: bool, write: Optional[Callable[[], None]] = None) -> None:
        """A try ended: write its file (if given) and count its cost together, so a spend scan never counts it
        twice."""
        with self.lock:
            if write is not None:
                write()
            if ok:
                self.costs.append(cost)
            self.own_since_scan += cost
            self.own_total += cost


def load_soft_stop():
    from guard import soft_stop                       # B1's module (Part 2); imported lazily
    return soft_stop


# ------------------------------------------------------------------------------------------------ runtime

def block_network() -> List[str]:
    """Dry run: refuse every network connection in this process (no LLM call can happen)."""
    tried: List[str] = []

    def hook(event, args):
        if event in ("socket.connect", "socket.getaddrinfo", "socket.gethostbyname"):
            tried.append(event)
            raise RuntimeError(f"network blocked in the Stage B dry run ({event})")
    sys.addaudithook(hook)
    return tried


class _NoJudge:
    """Dry run: calls._llm. Any judge call fails loudly."""
    model, max_output_tokens = "no-judge-in-dry-run", 16000
    cache_dir = os.path.join(OUTPUT_DIR, "_no_judge_in_dry_run_never_written")

    def call(self, **_):
        raise RuntimeError("a judge call was attempted in the Stage B dry run")


def rebuild_make_env() -> Optional[Callable]:
    """fork/rebuild.py make_env(state) if B2's module has it, else None (then fork/branch_env.py make_env)."""
    try:
        from fork import rebuild
    except ImportError:
        return None
    return getattr(rebuild, "make_env", None)


class TauRuntime:
    """The real runtime (venv): the copied model routing, τ-bench, the branch guards and the per-try judge cache.

    Fakes for tests and replay audits (no code change needed), passed to the constructor and then
    main(argv, runtime=TauRuntime(...)):
      agent_completion: used instead of exp_core.models.make_completion("agent") (same signature);
      user_completion:  put at tau_bench.envs.user.completion (wrapped by the copied timed_user_completion) instead
                        of make_completion("user");
      judge_base:       the object behind repro_runtime.calls._llm (inside the per-try cache proxy; a dataclass like
                        policy_pipeline.llm.LLM gets a copy per try, any other object is used as it is).
    setup() runs models.activate (which resets calls._llm) and then sets these seams, so fakes put on the seams
    before main() would be replaced: pass them here. A fake put on method_tgr.llm.structured is never touched."""

    def __init__(self, branches=BRANCHES, agent_completion: Optional[Callable] = None,
                 user_completion: Optional[Callable] = None, judge_base: Any = None):
        self.branches = tuple(branches)
        self.domains: Dict[str, dict] = {}
        self.judge = None
        self._fake_agent, self._fake_user, self._fake_judge = agent_completion, user_completion, judge_base

    def setup(self, profile: str, cache_root: str, dry_run: bool) -> Dict[str, Any]:
        os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")   # litellm: no cost-map download at import
        runner_path.setup()
        import repro_runtime.calls  # noqa: F401  (loaded before activate so its seams are re-pointed; as the copy)
        import repro_runtime.plan  # noqa: F401
        from exp_core import models
        self.models = models
        models.CACHE_ROOT = os.path.join(cache_root, "_base")     # never used for calls: each try has its own folder
        act = models.activate(profile, "guard")
        used = {r: act["roles"][r]["model"] for r in models.ROLES}
        if any(m not in ALLOWED_MODELS for m in used.values()):
            raise RunRefused(f"models {used} refused: only {ALLOWED_MODELS}")
        import tau_bench
        import tau_bench.envs.user as user_mod
        from tau_bench.agents.tool_calling_agent import message_to_action
        from repro_online import episode
        user_mod.completion = episode.timed_user_completion(self._fake_user or models.make_completion("user"))
        self.agent_completion = self._fake_agent or models.make_completion("agent")
        self.message_to_action = message_to_action
        self.user_model = act["roles"]["user"]["model"]
        from repro_runtime import calls
        if dry_run:
            calls._llm = _NoJudge()
        else:
            from fork import branch_cache
            self.judge = branch_cache.install(self._fake_judge if self._fake_judge is not None else self.judge_base())
        self.make_env_fn = rebuild_make_env()
        fakes = [k for k, v in (("agent", self._fake_agent), ("user", self._fake_user), ("judge", self._fake_judge))
                 if v is not None]
        return {"activation": act, "models": used, "tau_bench": tau_bench.__file__,
                "make_env": "fork.rebuild.make_env" if self.make_env_fn else "fork.branch_env.make_env",
                "fakes": fakes}

    def judge_base(self):
        import repro_core.llm as rc                     # its structured_llm was re-pointed by models.activate
        return rc.structured_llm()

    def domain(self, d: str) -> dict:
        if d not in self.domains:
            from tau_bench.envs import get_env
            from fork import guards_build
            with contextlib.redirect_stdout(io.StringIO()):
                probe = get_env(d, user_strategy="human", user_model=self.user_model, user_provider="azure",
                                task_split="test", task_index=0)
            self.domains[d] = {"tools_info": probe.tools_info, "wiki": probe.wiki,
                               "guards": guards_build.build_branch_guards(d, probe.tools_info, self.branches)}
        return self.domains[d]

    def make_env(self, state) -> Any:
        before = self.models.episode_usage()["user"]["calls"]
        if self.make_env_fn is None:
            env = branch_env.make_env(state, self.user_model)
        elif "user_model" in inspect.signature(self.make_env_fn).parameters:
            env = self.make_env_fn(state, user_model=self.user_model)
        else:
            env = self.make_env_fn(state)
        if self.models.episode_usage()["user"]["calls"] != before:
            raise branch_env.EnvMismatch("building the env called the user model")
        return env

    def reset_usage(self) -> None:
        self.models.reset_episode_usage()

    def usage(self) -> dict:
        return self.models.episode_usage()

    def judge_cache(self, folder: str):
        return self.judge.use(folder) if self.judge is not None else contextlib.nullcontext()


def preload_copies(domain: str) -> None:
    """Load the copied τ-bench tools and data in the main thread, before the worker threads. state_tracker/tau_copy.py
    tools() puts the tool module in sys.modules before it has run, so two threads loading it at once can get a
    half-loaded module ("no attribute 'ALL_TOOLS'"; seen in a test with 2 workers). The rebuild replay and the
    tracker use these copies."""
    from state_tracker import tau_copy
    from state_tracker.state import load_db
    tau_copy.tools(domain)
    load_db(domain)


def default_rebuild() -> Callable:
    from fork.rebuild import rebuild                   # B2's module (Part 3a)
    return rebuild


def seed_fork_judge(guard: Any, state: Any, source: dict, branch: str, target: Any = None,
                    write: bool = True) -> Dict[str, Any]:
    """Put the source judge's answer to the fork attempt in this try's judge cache (fork/judge_seed.py). target: the
    try's judge LLM (default: this thread's per-try copy; None for a fake judge used as it is: then no seed). The dry
    run passes a stand-in target and write=False. Raises judge_seed.SeedMismatch. No LLM call."""
    from fork import branch_cache, judge_seed
    if target is None and write:
        target = branch_cache.current_per_try_llm()
    return judge_seed.seed_try(guard, state, source, branch, target, write=write)


def dry_run_judge_target(models_used: Dict[str, str], folder: str) -> Any:
    """What the try's judge LLM would be (model, max_output_tokens, cache folder), without building it: the real
    LLM's __init__ creates its folder, and the dry run writes nothing."""
    from types import SimpleNamespace
    from repro_core.llm import llm_config               # runner copy (as exp_core.models.activate's structured_llm)
    return SimpleNamespace(model=models_used.get("guard"), max_output_tokens=llm_config()["max_output_tokens"],
                           cache_dir=folder)


# ------------------------------------------------------------------------------------------------ main

def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("points", nargs="+", help="fork points files (jsonl, one ForkPoint per line)")
    ap.add_argument("--profile", default=None, choices=ALLOWED_PROFILES,
                    help="run the forks of this profile (needed if the files have both)")
    ap.add_argument("--branches", default="A,B")
    ap.add_argument("--tries", type=int, default=5)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--ids", default=None, help="comma-separated fork ids (a subset)")
    ap.add_argument("--out-root", default=STAGE_B_DIR, help="default: output/eval_v2/stage_b (must be under output/)")
    ap.add_argument("--cache-root", default=None,
                    help="judge caches; default output/_llmcache/<out-root relative to output/, '/' -> '_'>")
    ap.add_argument("--soft-stop-refresh", type=float, default=None,
                    help="seconds between two scans of the spend (default: before every try with "
                         "guard/soft_stop.py SpendScanner, else every 60 s with spent_usd)")
    ap.add_argument("--later-left-usd", type=float, default=0.0,
                    help="USD of the later and concurrent jobs (e.g. the other Stage B process), added to the left "
                         "estimate of every soft-stop check (default 0)")
    ap.add_argument("--dry-run", action="store_true",
                    help="resolve and print everything, rebuild every fork, build both guards; no LLM call, no file")
    a = ap.parse_args(argv)
    a.branches = [b.strip() for b in a.branches.split(",") if b.strip()]
    if not a.branches or any(b not in BRANCHES for b in a.branches) or len(set(a.branches)) != len(a.branches):
        raise RunRefused(f"--branches {a.branches}: use A, B or A,B")
    if a.tries < 1 or a.workers < 1:
        raise RunRefused("--tries and --workers must be at least 1")
    if not a.later_left_usd >= 0:
        raise RunRefused("--later-left-usd must be 0 or more")
    return a


def main(argv=None, *, runtime: Any = None, rebuild_fn: Optional[Callable] = None, soft_stop: Any = None,
         safety: bool = True) -> Dict[str, Any]:
    """Tests pass a fake runtime, rebuild_fn and soft_stop, and safety=False (the write guard and the network block
    are process-wide and permanent; tests check them in a fresh process)."""
    a = parse_args(argv)
    # ---- safety first: refuse writes outside output/ (dry run: everywhere) before any runner code is imported
    net = None
    if safety:
        write_guard.install([] if a.dry_run else [OUTPUT_DIR])
        if a.dry_run:
            net = block_network()
    out_root, cache_root = resolve_roots(a.out_root, a.cache_root)
    forks_all = load_points(a.points, a.ids)
    profile, forks, other = pick_profile(forks_all, a.profile)
    check_points(forks)
    if not forks:
        raise RunRefused(f"no fork point of profile {profile}")
    rt = runtime or TauRuntime(a.branches)
    if rebuild_fn is None:
        try:
            rebuild_fn = default_rebuild()
        except ImportError as e:
            raise RunRefused(f"fork/rebuild.py rebuild() is missing ({e})")
    setup = rt.setup(profile, cache_root, a.dry_run)
    used_models = setup["models"]
    domains = sorted({f.domain for f in forks})
    for d in domains:
        rt.domain(d)
        preload_copies(d)
    if soft_stop is None:
        try:
            soft_stop = load_soft_stop()
        except ImportError as e:
            if not a.dry_run:
                raise RunRefused(f"the soft stop module guard/soft_stop.py is missing ({e}): no run without it")
            soft_stop = None

    units = [(t, f, b) for t in range(a.tries) for f in forks for b in a.branches]     # interleaved
    status = {}
    done_costs = []
    for t, f, b in units:
        st, r = try_status(rb.try_path(out_root, f.fork_id, b, t))
        status[(t, f.fork_id, b)] = st
        if st == "done":
            done_costs.append(float(r.get("cost_usd") or 0.0))
    todo = [u for u in units if status[(u[0], u[1].fork_id, u[2])] != "done"]
    n_failed = sum(1 for v in status.values() if v == "failed")
    gate = None
    if soft_stop is not None:
        gate = SpendGate(soft_stop, PRIOR_USD_PER_TRY[profile], done_costs, len(todo),
                         spend_seen_by_soft_stop(out_root), a.soft_stop_refresh, later_left=a.later_left_usd)
    plan = {"argv": sys.argv if argv is None else list(argv), "profile": profile, "models": used_models,
            "branches": a.branches, "branch_guards": {b: BRANCH_GUARD[b] for b in a.branches}, "tries": a.tries,
            "workers": a.workers, "forks": len(forks), "forks_other_profile_skipped": other,
            "forks_by_kind": _count(forks, "kind"), "forks_by_domain": _count(forks, "domain"),
            "forks_by_source": _count(forks, "source"), "units": len(units),
            "already_done": len(units) - len(todo), "failed_to_rerun": n_failed, "to_run": len(todo),
            "out_root": out_root, "cache_root": cache_root, "seen_by_soft_stop_scan": spend_seen_by_soft_stop(out_root),
            "guards": {d: {b: x["info"] for b, x in rt.domain(d)["guards"].items()} for d in domains},
            "tools_sha256": {d: _tools_sha(rt.domain(d)["tools_info"]) for d in domains},
            "setup": {k: v for k, v in setup.items() if k != "activation"},
            "runner_dir": runner_path.RUNNER_DIR, "soft_stop": gate.status() if gate else "module missing",
            "later_left_usd": a.later_left_usd,
            "write_guard": {"installed": write_guard.installed(), "allowed": [] if a.dry_run else [OUTPUT_DIR]},
            "network_blocked": net is not None, "cost_usd": 0.0}

    if a.dry_run:
        return dry_run(a, rt, rebuild_fn, forks, plan, net)

    os.makedirs(out_root, exist_ok=True)
    write_try(os.path.join(out_root, f"run_{time.strftime('%Y%m%d_%H%M%S')}_{profile}.json"),
              dict(plan, activation=setup.get("activation"), started=time.strftime("%Y-%m-%dT%H:%M:%S"),
                   fork_ids=[f.fork_id for f in forks]))
    say(f"start: profile {profile}, {len(forks)} forks x {len(a.branches)} branches x {a.tries} tries = "
        f"{len(units)} tries ({plan['already_done']} already done, {n_failed} failed to run again, {len(todo)} to "
        f"run); out {out_root}; soft stop {plan['soft_stop']}")
    started = time.time()
    counts = {"ran": 0, "ok": 0, "error": 0, "not_started": 0, "cost": 0.0, "judge_seed_written": 0}
    clock_lock = threading.Lock()

    def job(unit):
        t, f, b = unit
        stop = gate.try_start()
        if stop is not None:
            return None
        path = rb.try_path(out_root, f.fork_id, b, t)
        cache = rb.try_cache_dir(cache_root, f.fork_id, b, t)
        moved = prepare_try(path, cache)
        rt.reset_usage()
        dom = rt.domain(f.domain)
        seed = None
        try:
            source = rb.load_source(f)           # the path and source checks first (audit A5 W4), then the rebuild
            state = rebuild_fn(f)
            rb.check_state(state, source, dom["wiki"])
            env = rt.make_env(state)
            branch_env.check_env(env, state)
            guard = dom["guards"][b]["guard"]
            with rt.judge_cache(os.path.join(cache, "structured")):
                seed = seed_fork_judge(guard, state, source, b)      # before the try: no LLM call
                rec = rb.run_branch(state, b, t, env=env, guard=guard,
                                    agent_completion=rt.agent_completion, tools_info=dom["tools_info"],
                                    source=source, message_to_action=rt.message_to_action, usage_fn=rt.usage)
        except Exception as e:  # noqa: BLE001 - recorded as a failed try
            rec = failed_record(f, b, t, e, rt.usage())
        rec.update({"models": used_models, "judge_cache": os.path.relpath(cache, paths.PC_DIR), "judge_seed": seed,
                    "moved_before_rerun": {k: os.path.relpath(v, paths.PC_DIR) for k, v in moved.items()}})
        gate.finished(rec["cost_usd"], rec["error"] is None, lambda: write_try(path, rec))
        return rec

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(job, u) for u in todo]
        for fut in as_completed(futs):
            try:
                r = fut.result()
            except Exception as e:  # noqa: BLE001 - e.g. a rename before the try failed: no file written, go on
                with clock_lock:
                    counts["ran"] += 1
                    counts["error"] += 1
                say(f"a try crashed before its file was written: {type(e).__name__}: {e}")
                continue
            with clock_lock:
                if r is None:
                    counts["not_started"] += 1
                    continue
                counts["ran"] += 1
                counts["ok" if r["error"] is None else "error"] += 1
                counts["cost"] += r["cost_usd"]
                counts["judge_seed_written"] += bool((r.get("judge_seed") or {}).get("written"))
                n = counts["ran"]
            c = r.get("cost") or {}
            say(f"{r['fork_id']} {r['branch']} try {r['try']}: reward {r['reward']} done {r['done']} steps "
                f"{r.get('n_exec_steps')} blocks {r.get('n_blocks_after_fork')} cap {r.get('n_cap_overrides_after_fork')} "
                f"err {r['error'] is not None} cost {sum(float(v or 0) for v in c.values()):.4f} {r.get('seconds')}s "
                f"({n}/{len(todo)}, {time.time() - started:.0f}s)")
    spent = gate.status()["spent_usd"]
    say(f"DONE: {counts['ran']} tries run ({counts['ok']} ok, {counts['error']} with an error), "
        f"{plan['already_done']} already done, {counts['not_started']} not started (soft stop), cost of this run "
        f"${counts['cost']:.4f}, spent so far ${spent:.2f}; judge seeds written {counts['judge_seed_written']} of "
        f"{counts['ran']}; refused writes {len(write_guard.REFUSED)}; {time.time() - started:.0f}s")
    return dict(plan, counts=counts, stopped=gate.stopped)


def _count(forks: List[ForkPoint], key: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for f in forks:
        out[getattr(f, key)] = out.get(getattr(f, key), 0) + 1
    return out


def _tools_sha(tools_info: List[dict]) -> str:
    from fork import guards_build
    return guards_build.tools_sha256(tools_info)


def dry_run(a, rt, rebuild_fn, forks: List[ForkPoint], plan: Dict[str, Any], net) -> Dict[str, Any]:
    """Check every fork's source line, rebuild it, build its env, check both, compute both branches' fork trace
    positions, and make each branch's judge seed without writing it (the branch guard must give the fork decision
    and block message with the source judge's answer). No LLM call."""
    say("DRY RUN (no LLM call, network blocked, nothing written):")
    print(json.dumps(plan, indent=1, default=str), flush=True)
    ok, problems = 0, []
    seeds = {"checked": 0, "no_judge_call": 0, "not_tgr_guard": 0, "no_source_answer": []}
    for f in forks:
        t0 = time.time()
        try:
            dom = rt.domain(f.domain)
            source = rb.load_source(f)           # the path and source checks first (audit A5 W4), then the rebuild
            state = rebuild_fn(f)
            rb.check_state(state, source, dom["wiki"])
            env = rt.make_env(state)
            branch_env.check_env(env, state)
            tps = {b: rb.fork_trace_position(f, b, source["fork_trace_position"]) for b in a.branches}
            diff = sorted(k for k in tps[a.branches[0]] if any(tps[b].get(k) != tps[a.branches[0]].get(k)
                                                               for b in a.branches))
            seed_txt = []
            for b in a.branches:
                folder = os.path.join(rb.try_cache_dir(plan["cache_root"], f.fork_id, b, 0), "structured")
                s = seed_fork_judge(dom["guards"][b]["guard"], state, source, b,
                                    target=dry_run_judge_target(plan["models"], folder), write=False)
                if s["key"]:
                    seeds["checked"] += 1
                    seed_txt.append(f"{b} seed ok ({s['decision']})")
                elif "no judge call" in (s["why"] or ""):
                    seeds["no_judge_call"] += 1
                    seed_txt.append(f"{b} no judge call")
                elif "not a TGR guard" in (s["why"] or ""):
                    seeds["not_tgr_guard"] += 1
                    seed_txt.append(f"{b} stub guard")
                else:
                    seeds["no_source_answer"].append(f"{f.fork_id} {b}: {s['why']}")
                    raise judge_seed_error(f"branch {b}: no judge seed: {s['why']}")
            ok += 1
            say(f"dry run fork {f.fork_id}: {f.domain} {f.task_split}/{f.task_index} trial {f.trial} attempt "
                f"{f.attempt_index} {f.action}: A {f.decision_a}, B {f.decision_b} ({f.kind}); n_exec {state.n_exec}, "
                f"blocks in a row {state.consecutive_blocks}, trace {len(state.trace)}; trace position differs in "
                f"{diff}; judge seed: {', '.join(seed_txt)}; {time.time() - t0:.1f}s")
        except Exception as e:  # noqa: BLE001 - listed; the dry run goes on
            problems.append(f"{f.fork_id}: {type(e).__name__}: {e}")
            say(f"dry run fork {f.fork_id}: PROBLEM {type(e).__name__}: {e}")
    plan = dict(plan, dry_run={"forks_ok": ok, "problems": problems, "judge_seeds": seeds,
                               "network_attempts_blocked": len(net) if net is not None else None,
                               "refused_writes": len(write_guard.REFUSED)})
    say(f"DRY RUN DONE: {ok} of {len(forks)} forks rebuilt and checked, {len(problems)} problem(s); judge seeds "
        f"checked {seeds['checked']} (no judge call at the fork {seeds['no_judge_call']}, no source answer "
        f"{len(seeds['no_source_answer'])}); network attempts {len(net) if net is not None else 'n/a'}; refused "
        f"writes {len(write_guard.REFUSED)}")
    return plan


def judge_seed_error(text: str) -> Exception:
    from fork import judge_seed
    return judge_seed.SeedMismatch(text)


if __name__ == "__main__":
    main()
