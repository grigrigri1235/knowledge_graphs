"""Eval v2 Part 3 (fork/schema.py): the fixed interface between the fork builders (docs/planning/tracker_eval_v2/orchestration.md).

Written by the main chat before the build wave, so that two agents can work at the same time:
  - fork/find_points.py and fork/rebuild.py (builder B2) produce ForkPoint and ForkState;
  - fork/run_branch.py and fork/run_all.py (builder B3) consume them.
Formats and the rebuild recipe: output/eval_v2/checks/part1.md (sections 5.1-5.7).

Rules for changing this file: new fields may be added, with a default value, by either builder (say so in your
result). Existing fields are never renamed or removed.
Standard library only. Never import gold code (tests/test_no_gold_import.py).
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, List, Optional

from state_tracker import paths

EVAL_V2_DIR = os.path.join(paths.OUTPUT_DIR, "eval_v2")
STAGE_A_DIR = os.path.join(EVAL_V2_DIR, "stage_a")      # stage_a/<agent>/<guard>/episodes*.jsonl (one or more files)
STAGE_B_DIR = os.path.join(EVAL_V2_DIR, "stage_b")      # stage_b/<fork_id>/<branch>/<try>.json

AGENTS = {"luna": "luna-dev", "nano": "nano-agent-luna"}   # agent name -> profile
SOURCES = ("saved_tgr", "online_tracker", "stage_a")        # 1: partner frozen TGR, 2: our p10 runs, 3: Stage A
KINDS = ("block removed", "block added")
DECISIONS = ("allow", "block")
BRANCHES = ("A", "B")
BRANCH_GUARD = {"A": "tgr_frozen", "B": "tgr_tracker"}      # A: frozen TGR decision, then frozen TGR; B: tracker


@dataclass
class ForkPoint:
    """One fork point: the first attempt of a conversation where frozen TGR and TGR + tracker decide differently.
    One line of a fork_points*.jsonl file (to_dict / from_dict)."""
    fork_id: str                  # stable and unique; letters, digits, '.', '_', '-' only (used as a folder name)
    source: str                   # one of SOURCES
    run: str                      # e.g. "luna_train_v5", "p10_nano_train", "stage_a/luna/tgr_frozen"
    episodes_path: str            # the source episodes file, relative to predicate_correctness/
    line_no: int                  # 0-based raw line number in episodes_path
    agent: str                    # "luna" | "nano"
    profile: str                  # AGENTS[agent]
    domain: str                   # "airline" | "retail"
    task_split: str               # "test" (sources 1, 2) | "train" (Stage A)
    task_index: int
    trial: int
    attempt_index: int            # i: index into ep["attempts"]; the first try of a retried blocked action
    exec_step: int                # ep["attempts"][i]["exec_step"]
    attempt: int                  # ep["attempts"][i]["attempt"] (1 = first try)
    action: str                   # tool name, or "respond" for a reply to the user
    arguments: Dict[str, Any]     # from the message's tool_calls[0].function.arguments (never attempts[i].kwargs)
    source_guard: str             # guard of the source run: "tgr" (partner frozen), "tgr_frozen" or "tgr_tracker"
    decision_a: str               # frozen TGR at the fork: "allow" | "block"
    decision_b: str               # TGR + tracker at the fork: "allow" | "block"
    feedback_a: Optional[str]     # frozen TGR's block message (None when it allows)
    feedback_b: Optional[str]     # TGR + tracker's block message (None when it allows)
    kind: str                     # "block removed" (A blocks, B allows) | "block added" (A allows, B blocks)
    changed_predicates: List[Dict[str, Any]] = field(default_factory=list)   # [{name, judge, tracker}]
    reviewer_verdict: Optional[str] = None
    notes: str = ""
    # --- added by B2 (fork/find_points.py), all with defaults ---
    step_id: str = ""                    # "<run>/<domain>/task<T>/trial<R>/step<S>/attempt<A>" (key of p8_changes.jsonl)
    review_items: List[Dict[str, Any]] = field(default_factory=list)   # Part 7 items behind reviewer_verdict
    values_a: Dict[str, Any] = field(default_factory=dict)   # predicate values frozen TGR used at the fork (judge's)
    values_b: Dict[str, Any] = field(default_factory=dict)   # predicate values TGR + tracker used at the fork
    margin_a: Optional[float] = None     # TGR's decision margin with values_a (None: no circuit)
    margin_b: Optional[float] = None     # ... with values_b
    violated_a: List[str] = field(default_factory=list)      # rule ids behind A's block ([] when A allows)
    violated_b: List[str] = field(default_factory=list)      # rule ids behind B's block ([] when B allows)
    feedback_a_source: Optional[str] = None   # "saved" (the source run's text) | "rebuilt" (TGR's feedback code) | None
    feedback_b_source: Optional[str] = None
    cap_override_at_fork: bool = False   # attempt == 4: a block there runs anyway (both branches run the action)
    not_comparable_before: int = 0       # earlier checks whose other decision is unknown (judge skipped)
    no_effect_before: int = 0            # earlier differences skipped: at a cap override (4th try), no effect (F2)
    changed_attempts: int = 0            # attempts of the whole source conversation where A and B differ
    source_reward: Optional[float] = None    # the source conversation's τ-bench reward
    n_attempts: int = 0                  # attempts in the source conversation
    # tgr_tracker sources: where the judge's evidence in the rebuilt frozen-TGR message comes from, per predicate:
    # "saved" (guard record; the tracker kept the judge's value), "cache" (the run's judge cache: the judge's full
    # answer, read only), "missing" (not found: printed without evidence). {} for frozen-TGR sources.
    judge_evidence_from: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ForkPoint":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


@dataclass
class ForkState:
    """What fork/rebuild.py::rebuild(fork_point) returns: everything needed to continue at the fork attempt."""
    fork: ForkPoint
    task_split: str
    task_index: int
    data: Dict[str, Any]          # τ-bench database at the fork (fresh data_load_func, executed calls replayed)
    env_actions: List[Dict[str, Any]]    # executed history as τ-bench actions {name, kwargs}, replies included
    messages: List[Dict[str, Any]]       # what the agent saw before the fork attempt: ep["messages"][:2 + 2 * i]
    executed: List[Dict[str, Any]]       # history the guard sees: ep["executed"][:executed_prefix_len]
    pending: Dict[str, Any]              # the agent message at the fork: ep["messages"][2 + 2 * i]
    user_messages: List[Dict[str, Any]]  # rebuilt user-simulator list (part1.md 5.3)
    trace: List[Any]                     # guard trace: trace_position of each executed attempt before i, in order
    consecutive_blocks: int              # blocks in a row at the fork: attempt - 1
    n_exec: int                          # executed steps before the fork: exec_step
    max_steps: int = 30
    cap: int = 3
    extra: Dict[str, Any] = field(default_factory=dict)   # anything else a builder needs; document what you put
