"""Tracker v3, part 1 (fork/offline_v3.py): the one offline base that every later v3 part uses. No LLM call.

For one saved guard check, a registered guard gets the saved judge values and runs its own code on the saved
history. TGR + tracker builds the state itself (state_tracker/state.py build_state), exactly as it did online. The
result is
    {guard, decision ("allow" | "block"), allowed, margin, violated_rules, facts: {name: {value, source}}, unknown,
     feedback_text (the block message the episode loop sends; None when the guard allows), record (the full guard
     record)}

Guards (registry GUARDS; register_guard() adds one; p9 adds "v3"):
    frozen   frozen TGR: fork/points_tgr.py GivenJudgeTGR (the copied runtime, only its judge call replaced by the
             given values)
    v2       TGR + tracker, version b: fork/points_tgr.py OfflineTrackerTGR (guard/tgr_tracker.py TrackerTGR above
             the same given-values judge)
A guard factory takes a domain and returns a TGR-like object with set_given(judged) and _step(conv, step).

Saved checks (iter_conversations / iter_checks). Data sets, in this order (DATASETS):
    stage_a.<luna|nano>.<tgr_frozen|tgr_tracker>   output/eval_v2/stage_a/<agent>/<guard>/episodes*.jsonl
                                                   (the *.before_resume backups do not match the pattern)
    ours.<p10_luna_train|p10_nano_train|p10_luna_val>   output/online/<tag>/<domain>/tgr_tracker/episodes.jsonl
    partner.<luna_train_v5|nano_train|luna_val>    from_shieldagent/runs/<run>/<domain>/tgr/episodes.jsonl
                                                   (frozen TGR; the none/direct folders are never read)
    stage_b                                        output/eval_v2/stage_b/<fork_id>/<A|B>/<try>.json
Line rule for episode files (as fork/find_points.py load_conversations): lines with an error, of another domain,
with models other than gpt-6-luna / gpt-5-nano, or of another profile or guard are dropped (counted); the FIRST good
line per (domain, task_split, task, trial) is kept. Stage B: every try file without an error.

The check key, shared with p3 (tool labels) and every later part:
    ckey = "<dataset>|<conv_id>|<check_idx>"
    conv_id   episode files: "<domain>/<task_index>/<trial>" (unique per data set after the line rule, so no shard
              is needed; checked: 0 duplicate keys); Stage B: "<fork_id>/<A|B>/<try>"
    check_idx the 0-based index of the attempt in the saved record's `attempts` list. Each attempt is exactly one
              guard check (the TGR guards return a record for every attempt, judged or not; asserted), in the order
              the guard made them, so check_idx is also the index among ALL guard checks of the conversation. The
              agent's message of the check is messages[2 + 2 * check_idx]. Stage B: the index into the try's
              `attempts` list, which starts with the source conversation's attempts before the fork
              (fork_part "prefix") and the fork attempt (no guard call); only the attempts after the fork
              (fork_part "after") are checks of the try and are yielded.
A check gives: history = executed[:executed_prefix_len] (what the guard and the judge saw), msg (the agent's
message; tool and arguments come from it, never from attempts[i].kwargs), n_exec = exec_step, past = the guard's
trace before the check (trace_position of every earlier attempt that was not blocked; cap overrides included, as
fork/rebuild.py trace_before), the saved attempt and guard record, and the metadata.

Task key on every check: (domain, split, task_id, trial). Split names that cannot be confused:
    tau_train       Stage A: τ-bench's own "train" task file
    partner_train / partner_val   the partner's split (splits.json) of τ-bench's test task file
The partner's test group is never used: a check from it raises ForbiddenTestGroup. Stage B tries take the task key
of their source conversation (trial = the source trial; the try index is in conv_id).

Hold-out (preregistration.md, "Data split"): the val conversations of the strong agent (ours.p10_luna_val and
partner.luna_val) and the Stage B tries forked from one of them (fork run p10_luna_val or luna_val; the fork id then
contains "luna_val"). Development data: everything else.

History length of a check: len(render_history(history)), as the judge's view measures it before its cut
(from_shieldagent/runner/method_tgr/runtime.py lines 43 and 127; repro_core.taubench_steps.render_history of the
runner copy, no max_chars). Bins: "<12k" (< 12,000), "12-24k" (12,000 to 24,000, not cut), ">24k" (> 24,000, cut).

Standard library only (the runner copy and the τ-bench copy are imported through fork/points_tgr.py). Never sets an
LLM client and never imports the scorer.
"""
from __future__ import annotations

import collections
import copy
import glob
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Tuple

from fork import points_tgr as PT                                         # sets up the runner path
from fork.find_points import ALLOWED_MODELS, LLMCACHE_DIR, _find_cache_dir, load_splits   # noqa: F401
from fork.schema import AGENTS, BRANCH_GUARD, EVAL_V2_DIR, STAGE_A_DIR, STAGE_B_DIR
from method_tgr.runtime import Conversation                               # noqa: E402  (runner copy)
from repro_core.taubench_steps import _args, render_history              # noqa: E402  (runner copy)
from repro_online.guards import make_step                                # noqa: E402  (runner copy)
from state_tracker import paths
from state_tracker.state import build_state

ONLINE_DIR = os.path.join(paths.OUTPUT_DIR, "online")
STAGE_A_AGENTS = ("luna", "nano")
STAGE_A_GUARDS = ("tgr_frozen", "tgr_tracker")
OURS = {"p10_luna_train": "luna", "p10_nano_train": "nano", "p10_luna_val": "luna"}
PARTNER = {"luna_train_v5": "luna", "nano_train": "nano", "luna_val": "luna"}
PAIRS = {"p10_luna_train": "luna_train_v5", "p10_nano_train": "nano_train", "p10_luna_val": "luna_val"}
VAL_RUNS = ("p10_luna_val", "luna_val")                # the strong agent's val runs: the hold-out
HOLDOUT, DEV = "holdout", "dev"
SPLIT_NAMES = ("tau_train", "partner_train", "partner_val")
SAVED_TO_GUARD = {"tgr": "frozen", "tgr_frozen": "frozen", "tgr_tracker": "v2"}
BINS = ("<12k", "12-24k", ">24k")
BIN_LOW, BIN_HIGH = 12000, 24000
TRACKER_KEYS = ("version", "applied", "code_predicates", "judge_skipped", "judge_values", "tracker_values",
                "replaced", "changed", "lookup_errors")
MISS_CLASSES = ("source_run_fallback", "judge_retry", "bug")
LISTED_MISS_CLASSES = ("source_run_fallback", "judge_retry")
_TRY_RE = re.compile(r"^(\d+)\.json$")


class ForbiddenTestGroup(RuntimeError):
    """A check comes from the partner's test group (or a task without a train / val label)."""


class DataProblem(RuntimeError):
    """A saved record does not have the shape the offline base relies on."""


class NotDecidable(RuntimeError):
    """The saved judge values of a check are not known (the judge was skipped in the source run)."""


# ----------------------------------------------------------------------------------------------- data sets
def _datasets() -> List[str]:
    out = [f"stage_a.{a}.{g}" for a in STAGE_A_AGENTS for g in STAGE_A_GUARDS]
    out += [f"ours.{t}" for t in OURS] + [f"partner.{r}" for r in PARTNER] + ["stage_b"]
    return out


DATASETS: Tuple[str, ...] = tuple(_datasets())


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    family: str                      # stage_a | ours | partner | stage_b
    run: str                         # stage_a/<agent>/<guard> | <tag> | <run> | stage_b
    agent: Optional[str]             # luna | nano (Stage B: per try)
    saved_guard: Optional[str]       # tgr | tgr_frozen | tgr_tracker (Stage B: per try)
    files: Tuple[Tuple[Optional[str], str], ...]   # (domain or None: from the line, path); oldest first


def dataset_spec(name: str) -> DatasetSpec:
    """The files of one data set (globbed now)."""
    if name not in DATASETS:
        raise ValueError(f"unknown data set {name!r} (one of {DATASETS})")
    fam = name.split(".")[0]
    if fam == "stage_a":
        _, agent, g = name.split(".")
        files = tuple((None, p) for p in sorted(glob.glob(os.path.join(STAGE_A_DIR, agent, g, "episodes*.jsonl"))))
        return DatasetSpec(name, fam, f"stage_a/{agent}/{g}", agent, g, files)
    if fam == "ours":
        tag = name.split(".", 1)[1]
        files = tuple((d, os.path.join(ONLINE_DIR, tag, d, "tgr_tracker", "episodes.jsonl")) for d in paths.DOMAINS)
        return DatasetSpec(name, fam, tag, OURS[tag], "tgr_tracker", files)
    if fam == "partner":
        run = name.split(".", 1)[1]
        files = tuple((d, paths.episodes_path(run, d)) for d in paths.DOMAINS)
        return DatasetSpec(name, fam, run, PARTNER[run], "tgr", files)
    return DatasetSpec(name, fam, "stage_b", None, None, ())


# ----------------------------------------------------------------------------------------------- small helpers
def rel(path: str) -> str:
    return os.path.relpath(os.path.abspath(path), paths.PC_DIR)


def length_bin(n: int) -> str:
    """"<12k" (n < 12,000), "12-24k" (12,000 <= n <= 24,000: the judge's view is not cut), ">24k" (cut)."""
    if n < BIN_LOW:
        return BINS[0]
    if n <= BIN_HIGH:
        return BINS[1]
    return BINS[2]


def history_length(history: List[dict]) -> int:
    """len(render_history(history)) with no max_chars: the length the judge's view has before its cut."""
    return len(render_history(history))


_SPLITS: Optional[Dict[str, Dict[int, str]]] = None


def splits() -> Dict[str, Dict[int, str]]:
    global _SPLITS
    if _SPLITS is None:
        _SPLITS = load_splits()
    return _SPLITS


def split_name(task_split: Optional[str], domain: str, task_id: int,
               labels: Optional[Dict[str, Dict[int, str]]] = None) -> str:
    """tau_train (τ-bench's train file), or partner_train / partner_val (the partner's split of τ-bench's test file).
    Raises ForbiddenTestGroup for the partner's test group or a task without a label."""
    if task_split == "train":
        return "tau_train"
    if task_split not in (None, "test"):
        raise DataProblem(f"unknown task_split {task_split!r}")
    lab = (labels if labels is not None else splits()).get(domain, {}).get(int(task_id))
    if lab == "train":
        return "partner_train"
    if lab == "val":
        return "partner_val"
    raise ForbiddenTestGroup(f"{domain} task {task_id} (τ-bench test file) is labelled {lab!r}: the partner's test "
                             f"group (or no label) is never used")


def side_of(dataset: str, fork_run: Optional[str] = None, fork_id: Optional[str] = None) -> str:
    """HOLDOUT for the strong agent's val conversations and the Stage B tries forked from one; DEV otherwise."""
    if dataset in ("ours.p10_luna_val", "partner.luna_val"):
        return HOLDOUT
    if dataset == "stage_b":
        by_run = fork_run in VAL_RUNS
        if fork_id is not None and by_run != ("luna_val" in fork_id):
            raise DataProblem(f"fork {fork_id}: run {fork_run!r} and fork id disagree on the hold-out")
        return HOLDOUT if by_run else DEV
    return DEV


def _jn(x: Any) -> Any:
    """A JSON round trip (the saved records went through one)."""
    return json.loads(json.dumps(x, default=str))


def call_of(msg: dict) -> Tuple[str, Dict[str, Any]]:
    """(tool or "respond", arguments) of the agent's message, parsed as the guard parses them (make_step)."""
    calls = msg.get("tool_calls") or []
    if calls and calls[0].get("function") is not None:
        fn = calls[0]["function"]
        return fn["name"], _args(fn.get("arguments"))
    return "respond", {"content": msg.get("content") or ""}


# ----------------------------------------------------------------------------------------------- conversations
@dataclass
class SavedConversation:
    dataset: str
    conv_id: str
    ordinal: int                      # position in the data set (iteration order)
    domain: str
    split: str                        # tau_train | partner_train | partner_val
    task_id: int
    trial: int
    agent: str                        # luna | nano
    saved_guard: str                  # tgr | tgr_frozen | tgr_tracker
    ep: Dict[str, Any] = field(repr=False)
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def source_guard(self) -> str:
        """The registry name of the guard that made the saved checks: frozen | v2."""
        return SAVED_TO_GUARD[self.saved_guard]

    @property
    def conv_key(self) -> str:
        return f"{self.dataset}|{self.conv_id}"

    @property
    def side(self) -> str:
        return side_of(self.dataset, self.meta.get("fork_run"), self.meta.get("fork_id"))

    @property
    def task_key(self) -> Tuple[str, str, int, int]:
        return (self.domain, self.split, self.task_id, self.trial)

    def check_indices(self) -> List[int]:
        atts = self.ep["attempts"]
        if self.dataset == "stage_b":
            return [i for i, a in enumerate(atts) if a.get("fork_part") == "after"]
        return list(range(len(atts)))

    def checks(self, judged_only: bool = False) -> Iterator["SavedCheck"]:
        """The saved checks, in order, each with its history, message and the guard's trace before it."""
        ep = self.ep
        atts, messages, executed = ep["attempts"], ep["messages"], ep["executed"]
        if len(messages) != 2 + 2 * len(atts):
            raise DataProblem(f"{self.conv_key}: {len(messages)} messages for {len(atts)} attempts")
        wanted = set(self.check_indices())
        past: List[Any] = []
        for i, a in enumerate(atts):
            g = a.get("guard")
            if not isinstance(g, dict):
                raise DataProblem(f"{self.conv_key}: attempt {i} has no guard record")
            if i in wanted and (g.get("judge") or not judged_only):
                prefix = a["executed_prefix_len"]
                if prefix != 2 + 2 * a["exec_step"] or len(executed) < prefix:
                    raise DataProblem(f"{self.conv_key}: attempt {i}: executed_prefix_len {prefix}, exec_step "
                                      f"{a['exec_step']}, {len(executed)} executed messages")
                msg = messages[2 + 2 * i]
                if msg.get("role") != "assistant":
                    raise DataProblem(f"{self.conv_key}: messages[{2 + 2 * i}] is not the agent's message")
                yield SavedCheck(self, i, a, executed[:prefix], msg, a["exec_step"], list(past))
            if not a["blocked"]:
                past.append(copy.deepcopy(g.get("trace_position")))


@dataclass
class SavedCheck:
    conv: SavedConversation
    check_idx: int
    attempt: Dict[str, Any] = field(repr=False)     # the saved attempt (its guard record: attempt["guard"])
    history: List[dict] = field(repr=False)         # executed[:executed_prefix_len]
    msg: Dict[str, Any] = field(repr=False)         # messages[2 + 2 * check_idx]
    n_exec: int = 0
    past: List[Any] = field(default_factory=list, repr=False)
    _state: Any = field(default=None, repr=False)

    # --- keys
    @property
    def ckey(self) -> str:
        return f"{self.conv.dataset}|{self.conv.conv_id}|{self.check_idx}"

    @property
    def dataset(self) -> str:
        return self.conv.dataset

    @property
    def domain(self) -> str:
        return self.conv.domain

    @property
    def task_key(self) -> Tuple[str, str, int, int]:
        return self.conv.task_key

    @property
    def side(self) -> str:
        return self.conv.side

    @property
    def source_guard(self) -> str:
        return self.conv.source_guard

    # --- the saved check
    @property
    def saved(self) -> Dict[str, Any]:
        return self.attempt["guard"]

    @property
    def judged(self) -> bool:
        return bool(self.saved.get("judge"))

    @property
    def tool(self) -> str:
        return call_of(self.msg)[0]

    @property
    def args(self) -> Dict[str, Any]:
        return call_of(self.msg)[1]

    @property
    def cap_override(self) -> bool:
        return bool(self.attempt.get("cap_override"))

    @property
    def blocked(self) -> bool:
        """The guard blocked and the block message was sent (not a cap override)."""
        return bool(self.attempt.get("blocked"))

    @property
    def saved_decision(self) -> str:
        return "allow" if self.saved.get("action_allowed", True) else "block"

    @property
    def sent_message(self) -> Optional[str]:
        """The block message the agent got (None when it was not blocked; a cap override sends none)."""
        return self.attempt.get("feedback") if self.blocked else None

    def history_len(self) -> int:
        return history_length(self.history)

    def state(self):
        """The state before the check (build_state on the history; the pending call stored, not run). Cached."""
        if self._state is None:
            tool, args = call_of(self.msg)
            self._state = build_state(self.history, {"tool": tool, "args": args}, domain=self.domain)
        return self._state

    # --- the saved judge values
    def judge_cache_dir(self) -> Optional[str]:
        """The source run's judge cache (only needed for the judge's own evidence of values the tracker changed)."""
        c = self.conv
        if c.saved_guard != "tgr_tracker":
            return None
        if c.dataset == "stage_b":
            jc = c.ep.get("judge_cache")
            p = os.path.join(paths.PC_DIR, jc, "structured") if isinstance(jc, str) and jc else None
            return p if p and os.path.isdir(p) else None
        folder = os.path.dirname(c.meta["path"])
        default = os.path.join(LLMCACHE_DIR, c.meta["run"], "structured") if c.dataset.startswith("ours.") else None
        return _find_cache_dir(folder, "tgr_tracker", default)

    def saved_judge_detail(self, with_cache: bool = False) -> Tuple[Optional[Dict[str, dict]], Dict[str, Any]]:
        """The judge's own answer {name: {value, evidence}} of the saved check, and how it was found.
        Frozen TGR sources: the saved judge entry. TGR + tracker sources: tracker.judge_values, with the saved
        evidence where the tracker did not change the value; for a changed value the evidence is "" (or the judge's
        own, from the run's judge cache, with_cache=True). The v2 guard never needs that evidence: for a changed
        value it uses the tracker's. (None, info) when the judge was skipped in the source run."""
        g = self.saved
        if not g.get("judge"):
            return {}, {"evidence": {}, "cache": None, "problems": []}
        if self.conv.saved_guard in ("tgr", "tgr_frozen"):
            return PT.saved_judge_answer(g), {"evidence": {n: "saved" for n in g["judge"]}, "cache": None,
                                              "problems": []}
        tr = g.get("tracker") or {}
        if tr.get("judge_values") is None:
            return None, {"evidence": {}, "cache": None, "problems": ["judge skipped in the source run"]}
        cache = self.judge_cache_dir() if with_cache else None
        return PT.own_judge_answer(guard_for("frozen", self.domain), g, self.history, cache,
                                   (self.conv.ep.get("models") or {}).get("guard"))

    def saved_judge(self, with_cache: bool = False) -> Optional[Dict[str, dict]]:
        return self.saved_judge_detail(with_cache)[0]


# ----------------------------------------------------------------------------------------------- reading
def _episode_lines(spec: DatasetSpec, counts: collections.Counter) -> Iterator[Tuple[str, int, dict, str]]:
    """(path, line_no, episode, domain) of the kept lines of an episode data set, in file and line order (line
    rule)."""
    seen = set()
    for dom, path in spec.files:
        if not os.path.exists(path):
            raise DataProblem(f"{spec.name}: missing file {rel(path)}")
        counts["files"] += 1
        with open(path, encoding="utf-8") as f:
            for line_no, line in enumerate(f):
                if not line.strip():
                    continue
                counts["lines"] += 1
                ep = json.loads(line)
                if ep.get("error") is not None:
                    counts["error lines (dropped)"] += 1
                    continue
                domain = dom or ep.get("env")
                if dom and ep.get("env") not in (None, dom):
                    counts["lines of another domain (dropped)"] += 1
                    continue
                models = ep.get("models")
                if not isinstance(models, dict) or not models or any(m not in ALLOWED_MODELS for m in models.values()):
                    counts["lines with other models (dropped)"] += 1
                    continue
                if ep.get("profile") not in (None, AGENTS[spec.agent]):
                    counts["lines of another profile (dropped)"] += 1
                    continue
                if ep.get("guard") not in (None, spec.saved_guard):
                    raise DataProblem(f"{rel(path)}:{line_no}: guard {ep.get('guard')!r}, not {spec.saved_guard!r}")
                key = (domain, ep.get("task_split"), ep["task_index"], ep.get("trial"))
                if key in seen:
                    counts["later duplicate lines (first kept)"] += 1
                    continue
                seen.add(key)
                if domain not in paths.DOMAINS:
                    raise DataProblem(f"{rel(path)}:{line_no}: unknown domain {domain!r}")
                yield path, line_no, ep, domain


def _stage_b_tries(counts: collections.Counter) -> Iterator[Tuple[str, dict]]:
    """(path, try record) of every Stage B try without an error, sorted by fork id, branch and try."""
    items = []
    if os.path.isdir(STAGE_B_DIR):
        for fid in sorted(os.listdir(STAGE_B_DIR)):
            fdir = os.path.join(STAGE_B_DIR, fid)
            if not os.path.isdir(fdir):
                continue
            for br in sorted(os.listdir(fdir)):
                bdir = os.path.join(fdir, br)
                if br not in BRANCH_GUARD or not os.path.isdir(bdir):
                    continue
                for name in os.listdir(bdir):
                    m = _TRY_RE.match(name)
                    if m:
                        items.append((fid, br, int(m.group(1)), os.path.join(bdir, name)))
    for fid, br, t, path in sorted(items):
        counts["files"] += 1
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("error") is not None:
            counts["tries with an error (dropped)"] += 1
            continue
        if (d.get("fork_id"), d.get("branch"), d.get("try"), d.get("guard")) != (fid, br, t, BRANCH_GUARD[br]):
            raise DataProblem(f"{rel(path)}: fork id / branch / try / guard do not match the path")
        yield path, d


def iter_conversations(datasets: Optional[Iterable[str]] = None, part: Optional[Tuple[int, int]] = None,
                       counts: Optional[Dict[str, collections.Counter]] = None) -> Iterator[SavedConversation]:
    """Every saved conversation of the data sets (default: all, in DATASETS order). part = (k, n): only the
    conversations whose ordinal % n == k (all ordinals stay the full data set's). counts[dataset] gets the line
    counts. Raises ForbiddenTestGroup on a check from the partner's test group."""
    labels = splits()
    for name in (list(datasets) if datasets is not None else DATASETS):
        spec = dataset_spec(name)
        c = collections.Counter()
        if counts is not None:
            counts[name] = c
        if spec.family == "stage_b":
            source = ((p, d, None, d.get("env")) for p, d in _stage_b_tries(c))
        else:
            source = ((p, ep, n, dom) for p, n, ep, dom in _episode_lines(spec, c))
        for ordinal, (path, ep, line_no, domain) in enumerate(source):
            if part is not None and ordinal % part[1] != part[0]:
                continue
            yield _conversation(spec, ordinal, path, line_no, ep, domain, labels)


def _conversation(spec: DatasetSpec, ordinal: int, path: str, line_no: Optional[int], ep: dict, domain: str,
                  labels: Dict[str, Dict[int, str]]) -> SavedConversation:
    if spec.family == "stage_b":
        fork = ep["fork"]
        task_id, trial = int(ep["task_index"]), int(ep["source_trial"])
        if domain not in paths.DOMAINS:
            raise DataProblem(f"{rel(path)}: unknown domain {domain!r}")
        if (fork["domain"], fork["task_index"], fork["trial"]) != (domain, task_id, trial):
            raise DataProblem(f"{rel(path)}: the try's task differs from its fork point's")
        split = split_name(ep.get("task_split"), domain, task_id, labels)
        meta = {"path": rel(path), "fork_id": ep["fork_id"], "branch": ep["branch"], "try": ep["try"],
                "fork_run": fork["run"], "fork_source": fork["source"], "fork_attempt_index": ep["fork_attempt_index"],
                "run": "stage_b"}
        return SavedConversation(spec.name, f"{ep['fork_id']}/{ep['branch']}/{ep['try']}", ordinal, domain, split,
                                 task_id, trial, fork["agent"], ep["guard"], ep, meta)
    task_id, trial = int(ep["task_index"]), int(ep.get("trial") or 0)
    if spec.family == "stage_a" and ep.get("task_split") != "train":
        raise DataProblem(f"{rel(path)}:{line_no}: Stage A line with task_split {ep.get('task_split')!r}")
    if spec.family != "stage_a" and ep.get("task_split") not in (None, "test"):
        raise DataProblem(f"{rel(path)}:{line_no}: task_split {ep.get('task_split')!r} (τ-bench test file expected)")
    split = split_name(ep.get("task_split"), domain, task_id, labels)
    meta = {"path": rel(path), "line_no": line_no, "run": spec.run}
    return SavedConversation(spec.name, f"{domain}/{task_id}/{trial}", ordinal, domain, split, task_id, trial,
                             spec.agent, spec.saved_guard, ep, meta)


def iter_checks(datasets: Optional[Iterable[str]] = None, judged_only: bool = False,
                part: Optional[Tuple[int, int]] = None) -> Iterator[SavedCheck]:
    """Every saved guard check of the data sets, in order (see the module docstring)."""
    for conv in iter_conversations(datasets, part=part):
        yield from conv.checks(judged_only=judged_only)


# ----------------------------------------------------------------------------------------------- guards
GuardFactory = Callable[[str], Any]
GUARDS: Dict[str, GuardFactory] = {}
_GUARD_OBJECTS: Dict[Tuple[str, str], Any] = {}
_OFFLINE: Dict[str, PT.OfflineGuards] = {}


def offline_guards(domain: str) -> PT.OfflineGuards:
    """fork/points_tgr.py's two guards of one domain (built once per process)."""
    if domain not in _OFFLINE:
        _OFFLINE[domain] = PT.OfflineGuards(domain)
    return _OFFLINE[domain]


def register_guard(name: str, factory: GuardFactory, replace: bool = False) -> None:
    """Add a guard: factory(domain) -> a TGR-like object with set_given(judged) and _step(conv, step)."""
    if name in GUARDS and not replace:
        raise ValueError(f"guard {name!r} is already registered")
    GUARDS[name] = factory
    for k in [k for k in _GUARD_OBJECTS if k[0] == name]:
        del _GUARD_OBJECTS[k]


register_guard("frozen", lambda domain: offline_guards(domain).frozen)
register_guard("v2", lambda domain: offline_guards(domain).tracker)


def guard_for(name: str, domain: str) -> Any:
    if name not in GUARDS:
        raise ValueError(f"unknown guard {name!r} (registered: {sorted(GUARDS)})")
    key = (name, domain)
    if key not in _GUARD_OBJECTS:
        _GUARD_OBJECTS[key] = GUARDS[name](domain)
    return _GUARD_OBJECTS[key]


def run_guard(tgr: Any, history: List[dict], msg: dict, n_exec: int, past: List[Any], judged: Dict[str, dict]
              ) -> dict:
    """The guard record of one check, as fork/points_tgr.py OfflineGuards.check makes it (the online guard's
    check: make_step, then TGR's _step on the trace)."""
    tgr.set_given(judged)
    step = make_step(list(history), msg, n_exec)
    rec = tgr._step(Conversation(trace=list(past)), step)
    rec["trace_len_before"] = len(past)
    return rec


def result_of(rec: dict, guard: str) -> Dict[str, Any]:
    allowed = bool(rec.get("action_allowed", True))
    return {"guard": guard, "decision": "allow" if allowed else "block", "allowed": allowed,
            "margin": rec.get("margin"), "violated_rules": list(rec.get("violated_rules") or []),
            "facts": {n: {"value": v.get("value"), "source": v.get("source", "judge")}
                      for n, v in (rec.get("judge") or {}).items()},
            "unknown": list(rec.get("unknown_predicates") or []),
            "feedback_text": PT.feedback_of(rec), "record": rec}


def decide(check: SavedCheck, guard: Optional[str] = None, judged: Optional[Dict[str, dict]] = None
           ) -> Dict[str, Any]:
    """Run a registered guard (default: the source guard) on a saved check with the saved judge values (or the
    given ones). Raises NotDecidable when the saved judge values are not known."""
    guard = guard or check.source_guard
    if judged is None:
        judged = check.saved_judge()
        if judged is None:
            raise NotDecidable(f"{check.ckey}: the judge was skipped in the source run")
    rec = run_guard(guard_for(guard, check.domain), check.history, check.msg, check.n_exec, check.past, judged)
    return result_of(rec, guard)


# ----------------------------------------------------------------------------------------------- Gate 0
def _tracker_view(tr: Optional[dict]) -> Dict[str, Any]:
    tr = tr or {}
    out = {k: tr.get(k) for k in TRACKER_KEYS}
    out["state"] = {k: v for k, v in (tr.get("state") or {}).items() if k != "seconds"} if tr.get("state") else None
    return _jn(out)


def compare_with_saved(check: SavedCheck, result: Dict[str, Any]) -> Dict[str, Any]:
    """Field-by-field comparison of an offline result of the SOURCE guard with the saved check.
    main fields (Gate 0): decision, margin (exact), violated_rules (rule id, description, logic), message (the block
    message bytes: the sent one for a block, the saved feedback_text for a cap override, none for an allow) and,
    for TGR + tracker sources, tracker (TRACKER_KEYS and the state counts). extra fields (reported): values (every
    value with its evidence and source), trace_position, circuit, matched, mln, unknown_predicates, allowed_eps0.
    ok = all main fields equal; for a cap override only the decision counts (ok_decision)."""
    rec, saved = result["record"], check.saved
    main = {"decision": bool(rec.get("action_allowed", True)) == bool(saved.get("action_allowed", True)),
            "margin": _jn(rec.get("margin")) == _jn(saved.get("margin")),
            "violated_rules": _jn(rec.get("violated_rules") or []) == _jn(saved.get("violated_rules") or [])}
    want = check.sent_message if check.blocked else PT.feedback_of(saved)
    got = PT.feedback_of(rec)
    main["message"] = (got is None and want is None) or (got is not None and want is not None
                                                         and got.encode("utf-8") == want.encode("utf-8"))
    if check.conv.saved_guard == "tgr_tracker":
        main["tracker"] = _tracker_view(rec.get("tracker")) == _tracker_view(saved.get("tracker"))
    extra = {k: _jn(rec.get(k)) == _jn(saved.get(k))
             for k in ("judge", "trace_position", "circuit", "matched", "mln", "unknown_predicates", "allowed_eps0")}
    extra["saved_feedback_text"] = got == PT.feedback_of(saved)
    ok = all(main.values())
    return {"main": main, "extra": extra, "ok": ok, "ok_decision": main["decision"],
            "pass": main["decision"] if check.cap_override else ok,
            "differs": sorted(k for k, v in main.items() if not v),
            "differs_extra": sorted(k for k, v in extra.items() if not v)}


def miss_class(check: SavedCheck, cmp: Optional[Dict[str, Any]], error: Optional[str] = None) -> Optional[str]:
    """None (reproduced), or the class of a miss:
      judge_retry          the source guard's step failed and was retried (guard record attempts > 1)
      source_run_fallback  our p10 online runs only: the saved tracker part shows a tracker failure (lookup or
                           state error), so the judge's value was used (the thread race of eval v2 audit A2)
      bug                  anything else (not a listed class)"""
    if error is None and cmp is not None and cmp["pass"]:
        return None
    g = check.saved
    if int(g.get("attempts") or 1) > 1:
        return "judge_retry"
    tr = g.get("tracker") or {}
    failed = bool(tr.get("lookup_errors")) or bool((tr.get("state") or {}).get("error")) or any(
        isinstance(v, dict) and v.get("error") for v in (tr.get("tracker_values") or {}).values())
    if check.dataset.startswith("ours.") and failed:
        return "source_run_fallback"
    return "bug"
