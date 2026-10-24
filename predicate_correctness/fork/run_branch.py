"""Eval v2 Part 3b (fork/run_branch.py): continue one conversation from its fork point in one branch (Stage B).

Input: a ForkState (fork/rebuild.py rebuild(fork_point)), a branch ("A" or "B") and a try index. Output: one record,
saved by fork/run_all.py as output/eval_v2/stage_b/<fork_id>/<branch>/<try>.json.

What a branch does (docs/planning/tracker_eval_v2/p3.md subtask 3; formats: output/eval_v2/checks/part1.md 5.1-5.7):
  1. The fork attempt (state.pending, the agent message at attempt i) gets the branch's decision. Branch A uses
     fork.decision_a / fork.feedback_a (frozen TGR), branch B fork.decision_b / fork.feedback_b (TGR + tracker).
     There is no guard call and no LLM call for it. Then exactly what repro_online/episode.py::run_episode does with
     a guard record of that decision:
       - allow: env.step(action) (a tool call, or a reply to the user, which calls the user simulator); the message
         and the answer go to `messages` and `executed`; the action is added to the guard trace (TGR._step appends
         an allowed step's trace_position);
       - block, fewer than `cap` blocks in a row before: not run; the message and the block message go to `messages`
         only (a tool message with the same tool_call_id for a tool call, a system message for a reply); the block
         counts in the blocks in a row;
       - block with `cap` (3) blocks in a row before: cap override, as run_episode: guard.commit (adds it to the
         trace), then it runs. Marked `fork_cap_override` in the record.
  2. Then run_episode's loop, line by line, with the branch's guard (A: frozen TGR, B: TGR + tracker; see
     fork/guards_build.py), fresh agent calls (agent_completion), the user simulator inside env, the same cap and the
     same limit of executed steps (max_steps = 30, counted from state.n_exec). The counts continue from the rebuild:
     the trace (state.trace), the blocks in a row (state.consecutive_blocks) and the executed steps (state.n_exec).
  3. τ-bench scores the conversation as in run_episode: the env.step that ends it (###STOP### or a transfer) runs
     calculate_reward on the final database (env.data) and env.actions. At the 30-step limit the reward stays 0 and
     reward_info null, as in run_episode and in every saved run (the task is not done).

The fork action's trace position (no LLM call; documented choice):
  - TGR's trace_position of a step = {each action predicate: whether it is this action} + {each predicate of the
    action's rules: its value used for the decision}. The source run saved it for the fork attempt
    (attempts[i].guard.trace_position), with the source guard's values.
  - If the branch's guard is the source run's kind (A on a frozen TGR source "tgr"/"tgr_frozen", B on a
    "tgr_tracker" source), that saved trace position is used as it is.
  - Otherwise the values of the changed predicates (fork.changed_predicates: name, judge, tracker) are swapped to the
    branch's: the tracker's values for B, the judge's values for A. This is exact: TGR + tracker uses the judge's
    value for every predicate except the replaced ones, and a replaced value that equals the judge's is the same.
  - The trace before the fork (state.trace) is the source run's. With the frozen A+B rule sets this cannot change a
    decision: their rules have no temporal operator, and repro_runtime/verify.py rule_value evaluates a non-temporal
    rule at the last trace position only (the current step). Only the trace length is recorded (trace_len_before).
  - The result is checked against the fork point's own values of the branch (fork.values_a / fork.values_b, the
    values each guard used at the fork); a difference stops the try with an error.

The record (episode-compatible: the same fields as an episodes.jsonl line of the wrapper, for the whole conversation):
  task_index, trial (= the try index), env, guard (tgr_frozen | tgr_tracker), profile, models, messages, executed,
  attempts (the source run's attempts before the fork, then the fork attempt and the new ones; each has
  fork_part = "prefix" | "fork" | "after"), reward, done, reward_info, n_exec_steps, n_blocks, n_cap_overrides (whole
  conversation), cost, latency, calls, usage_roles (this try's calls only), seconds, error.
  Stage B fields: stage "B", fork_id, branch, try, task_split, fork (the ForkPoint), fork_attempt_index,
  fork_decision, fork_feedback, fork_cap_override, fork_trace_position, n_*_before/after_fork, user_messages_final,
  and cost_usd = the LLM cost of this try only (agent + user + guard, after the fork).
  The fork attempt's guard record is made here (fork_applied: branch, guard, decision; usage 0; margin,
  violated_rules and values_used of the branch's guard at the fork, see fork_guard_record); the source run's guard
  record of that attempt is kept in it as source_record.
  Cost accounting is the runner's: a judge cache hit inside a try counts its cost (as in every saved run), so
  cost_usd is a small over-estimate, which is the safe side for the soft stop.
  Before run_branch, fork/run_all.py seeds the try's judge cache with the source judge's answer to the fork attempt
  (fork/judge_seed.py, audit A5 W1): an exact repeat of the blocked fork call is then a cache hit with the same
  answer, as in the source run. The record gets judge_seed (written or not, and why).
  One deviation from run_episode, in the record only: attempts[k].kwargs is a deep copy taken before env.step (the
  τ-bench tools can change the passed lists in place, part1.md 5.7 trap 1). The env gets the same action.

Launched by fork/run_all.py (its docstring has the commands); there is no command line here.

Where the LLM calls go (the seams, for fakes in tests and audits; nothing else needs a change):
  - agent: the agent_completion argument (signature of exp_core.models.make_completion("agent"));
  - user simulator: inside env (env.user is an LLMUserSimulationEnv made without __init__), through the module
    global tau_bench.envs.user.completion;
  - judge: the copied TGR code, through method_tgr.llm.structured -> repro_runtime.calls.shared_llm() ->
    calls._llm (fork/run_all.py puts the per-try cache proxy of fork/branch_cache.py there).
  The fork attempt itself makes no call. The blocks in a row continue from state.consecutive_blocks (a fork at the
  2nd or 3rd try of a retried blocked action keeps its 1 or 2 earlier blocks; at the 4th try a block is a cap
  override).

Never imports gold code. The runner copy and τ-bench are imported lazily (inside run_branch / load_source callers).
"""
from __future__ import annotations

import collections
import copy
import json
import os
import re
import threading
import time
import traceback
from typing import Any, Callable, Dict, List, Optional

from fork.schema import BRANCH_GUARD, BRANCHES, DECISIONS, KINDS, ForkPoint, ForkState
from state_tracker import paths

RESPOND = "respond"                         # tau_bench.types.RESPOND_ACTION_NAME
FORK_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
SOURCE_GUARDS = ("tgr", "tgr_frozen", "tgr_tracker")
TRACKER_GUARD = "tgr_tracker"
ZERO_USAGE = {"n_llm_calls": 0, "cache_hits": 0, "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0,
              "api_seconds": 0.0, "cost_usd": 0.0, "calls_by_stage": {}}


class ForkMismatch(RuntimeError):
    """The fork state does not match the fork point or the source conversation."""


# ------------------------------------------------------------------------------------------------ paths

def check_fork_id(fork_id: str) -> str:
    if not isinstance(fork_id, str) or not FORK_ID_RE.match(fork_id) or fork_id in (".", ".."):
        raise ForkMismatch(f"fork_id {fork_id!r}: use letters, digits, '.', '_', '-' only")
    return fork_id


def try_path(out_root: str, fork_id: str, branch: str, try_index: int) -> str:
    """output/eval_v2/stage_b/<fork_id>/<branch>/<try>.json"""
    return os.path.join(out_root, check_fork_id(fork_id), branch, f"{int(try_index)}.json")


def try_cache_dir(cache_root: str, fork_id: str, branch: str, try_index: int) -> str:
    """output/_llmcache/eval_v2_stage_b/<fork_id>/<branch>/<try>/ (the judge cache goes to its structured/)."""
    return os.path.join(cache_root, check_fork_id(fork_id), branch, str(int(try_index)))


# ------------------------------------------------------------------------------------------------ the source run

_SOURCE_CACHE: "collections.OrderedDict[tuple, dict]" = collections.OrderedDict()
_SOURCE_LOCK = threading.Lock()
SOURCE_CACHE_SIZE = 1024                    # all forks of a run (a few hundred kB each)


def source_path(fork: ForkPoint) -> str:
    """The source episodes file (fork.episodes_path is relative to predicate_correctness/)."""
    if os.path.isabs(fork.episodes_path):
        raise ForkMismatch(f"episodes_path {fork.episodes_path!r} must be relative to predicate_correctness/")
    p = os.path.realpath(os.path.join(paths.PC_DIR, fork.episodes_path))
    if not p.startswith(os.path.realpath(paths.PC_DIR) + os.sep):
        raise ForkMismatch(f"episodes_path {fork.episodes_path!r} is not under predicate_correctness/")
    return p


def load_source(fork: ForkPoint) -> Dict[str, Any]:
    """What the branch needs from the source conversation (line fork.line_no of fork.episodes_path): the attempts
    before the fork, the fork attempt (its saved guard record and trace position), and the saved prefixes (for the
    checks). Cached (the last SOURCE_CACHE_SIZE forks). Callers must not change the result."""
    key = (fork.episodes_path, fork.line_no, fork.attempt_index)
    with _SOURCE_LOCK:
        if key in _SOURCE_CACHE:
            _SOURCE_CACHE.move_to_end(key)
            return _SOURCE_CACHE[key]
    path = source_path(fork)
    ep = None
    with open(path, encoding="utf-8") as f:
        for k, line in enumerate(f):
            if k == fork.line_no:
                ep = json.loads(line)
                break
    if ep is None:
        raise ForkMismatch(f"{fork.episodes_path} has no line {fork.line_no}")
    i = fork.attempt_index
    problems = []
    if ep.get("error") is not None:
        problems.append(f"source line has an error: {ep.get('error')}")
    if ep.get("task_index") != fork.task_index:
        problems.append(f"source task {ep.get('task_index')} != fork task {fork.task_index}")
    if "trial" in ep and ep["trial"] != fork.trial:
        problems.append(f"source trial {ep['trial']} != fork trial {fork.trial}")
    if "env" in ep and ep["env"] != fork.domain:
        problems.append(f"source env {ep['env']} != fork domain {fork.domain}")
    if ep.get("task_split", "test") != fork.task_split:
        problems.append(f"source task_split {ep.get('task_split', 'test')} != fork task_split {fork.task_split}")
    if "profile" in ep and ep["profile"] != fork.profile:
        problems.append(f"source profile {ep['profile']} != fork profile {fork.profile}")
    if not 0 <= i < len(ep.get("attempts") or []):
        problems.append(f"attempt_index {i} is not an attempt of the source ({len(ep.get('attempts') or [])})")
    if problems:
        raise ForkMismatch(f"{fork.fork_id}: " + "; ".join(problems))
    a = ep["attempts"][i]
    if not isinstance(a.get("guard"), dict) or not isinstance(a["guard"].get("trace_position"), dict):
        raise ForkMismatch(f"{fork.fork_id}: the source fork attempt has no guard trace_position")
    out = {"path": os.path.relpath(path, paths.PC_DIR), "line_no": fork.line_no,
           "attempts_prefix": ep["attempts"][:i], "fork_attempt": a,
           "fork_trace_position": a["guard"]["trace_position"],
           "messages_prefix": ep["messages"][:2 + 2 * i], "pending": ep["messages"][2 + 2 * i],
           "executed_prefix": ep["executed"][:a["executed_prefix_len"]],
           "source": {k: ep.get(k) for k in ("task_index", "trial", "env", "guard", "profile", "models", "reward",
                                             "done", "n_exec_steps", "n_blocks", "n_cap_overrides")}}
    with _SOURCE_LOCK:
        _SOURCE_CACHE[key] = out
        while len(_SOURCE_CACHE) > SOURCE_CACHE_SIZE:
            _SOURCE_CACHE.popitem(last=False)
    return out


# ------------------------------------------------------------------------------------------------ checks

def _pending_action(msg: dict) -> tuple:
    calls = msg.get("tool_calls") or []
    if calls and calls[0].get("function") is not None:
        fn = calls[0]["function"]
        return fn["name"], json.loads(fn.get("arguments") or "{}")
    return RESPOND, {"content": msg.get("content")}


def check_fork_point(fork: ForkPoint) -> List[str]:
    """Problems of a fork point on its own (decisions, kind, feedback, changed predicates)."""
    p = []
    try:
        check_fork_id(fork.fork_id)
    except ForkMismatch as e:
        p.append(str(e))
    if fork.decision_a not in DECISIONS or fork.decision_b not in DECISIONS:
        p.append(f"decisions {fork.decision_a!r}, {fork.decision_b!r} not in {DECISIONS}")
    elif fork.decision_a == fork.decision_b:
        p.append(f"both branches decide {fork.decision_a!r}: not a fork")
    want_kind = {("block", "allow"): "block removed", ("allow", "block"): "block added"}.get(
        (fork.decision_a, fork.decision_b))
    if fork.kind not in KINDS or (want_kind and fork.kind != want_kind):
        p.append(f"kind {fork.kind!r} does not match the decisions (A {fork.decision_a}, B {fork.decision_b})")
    for b, d, fb in (("A", fork.decision_a, fork.feedback_a), ("B", fork.decision_b, fork.feedback_b)):
        if d == "block" and not (isinstance(fb, str) and fb.strip()):
            p.append(f"branch {b} blocks but has no block message")
    if fork.source_guard not in SOURCE_GUARDS:
        p.append(f"source_guard {fork.source_guard!r} not in {SOURCE_GUARDS}")
    if not fork.changed_predicates:
        p.append("no changed predicates (the decisions can differ only through changed values)")
    for c in fork.changed_predicates:
        if not isinstance(c, dict) or "name" not in c or any(k not in c or not _is_value(c[k])
                                                               for k in ("judge", "tracker")):
            p.append(f"changed predicate {c!r}: needs name, judge and tracker (true, false or null)")
    return p


def _is_value(v: Any) -> bool:
    return v is True or v is False or v is None


def check_state(state: ForkState, source: Dict[str, Any], wiki: Optional[str] = None) -> None:
    """Raise ForkMismatch unless the fork state is the source conversation at the fork attempt (part1.md 5.6)."""
    f = state.fork
    i = f.attempt_index
    p = check_fork_point(f)
    a = source["fork_attempt"]
    if (state.task_split, state.task_index) != (f.task_split, f.task_index):
        p.append(f"state task {state.task_split}/{state.task_index} != fork {f.task_split}/{f.task_index}")
    if len(state.messages) != 2 + 2 * i or state.messages != source["messages_prefix"]:
        p.append(f"state.messages ({len(state.messages)}) != the source messages before attempt {i}")
    if state.pending != source["pending"]:
        p.append("state.pending is not the source agent message of the fork attempt")
    if len(state.executed) != 2 + 2 * state.n_exec or state.executed != source["executed_prefix"]:
        p.append(f"state.executed ({len(state.executed)}) != the source executed history before the fork")
    if len(state.trace) != state.n_exec:
        p.append(f"trace length {len(state.trace)} != executed steps {state.n_exec}")
    if (a.get("exec_step"), a.get("attempt"), a.get("executed_prefix_len")) != \
            (state.n_exec, state.consecutive_blocks + 1, len(state.executed)):
        p.append(f"source attempt (exec_step {a.get('exec_step')}, attempt {a.get('attempt')}) != state "
                 f"(n_exec {state.n_exec}, blocks in a row {state.consecutive_blocks})")
    if (f.exec_step, f.attempt) != (state.n_exec, state.consecutive_blocks + 1):
        p.append(f"fork point (exec_step {f.exec_step}, attempt {f.attempt}) != state")
    if not 0 <= state.n_exec < state.max_steps or state.consecutive_blocks < 0 or state.cap < 1:
        p.append(f"counts out of range: n_exec {state.n_exec}, max_steps {state.max_steps}, "
                 f"blocks in a row {state.consecutive_blocks}, cap {state.cap}")
    try:
        name, args = _pending_action(state.pending)
        if name != f.action:
            p.append(f"pending action {name} != fork action {f.action}")
        elif name != RESPOND and args != f.arguments:
            p.append("pending arguments differ from fork.arguments")
    except (ValueError, TypeError, KeyError) as e:
        p.append(f"pending message unreadable: {e}")
    if wiki is not None and (not state.messages or state.messages[0].get("content") != wiki):
        p.append("the system message is not this env's policy (wiki)")
    if p:
        raise ForkMismatch(f"{f.fork_id}: " + "; ".join(p))


# ------------------------------------------------------------------------------------------------ the fork attempt

def branch_decision(fork: ForkPoint, branch: str) -> tuple:
    """(decision, block message or None) of a branch at the fork."""
    if branch not in BRANCHES:
        raise ValueError(f"branch {branch!r} not in {BRANCHES}")
    return (fork.decision_a, fork.feedback_a) if branch == "A" else (fork.decision_b, fork.feedback_b)


def fork_trace_position(fork: ForkPoint, branch: str, saved: Dict[str, Any]) -> Dict[str, Any]:
    """The trace position of the fork action for the branch's guard (see the module docstring)."""
    if fork.source_guard not in SOURCE_GUARDS:
        raise ForkMismatch(f"source_guard {fork.source_guard!r} not in {SOURCE_GUARDS}")
    tp = copy.deepcopy(saved)
    want_tracker = BRANCH_GUARD[branch] == TRACKER_GUARD
    if want_tracker != (fork.source_guard == TRACKER_GUARD):
        key = "tracker" if want_tracker else "judge"
        for c in fork.changed_predicates:
            if c["name"] not in tp:
                raise ForkMismatch(f"{fork.fork_id}: changed predicate {c['name']} is not in the saved trace position")
            tp[c["name"]] = c[key]
    # cross-check with the fork point's values of this branch (values_a / values_b of fork/find_points.py), if any
    vals = getattr(fork, "values_a" if branch == "A" else "values_b", None) or {}
    bad = sorted(n for n, v in vals.items()
                 if n in tp and tp[n] is not (v.get("value") if isinstance(v, dict) else v))
    if bad:
        raise ForkMismatch(f"{fork.fork_id}: branch {branch} trace position differs from the fork point's values for "
                           f"{bad}")
    return tp


def is_source_kind(fork: ForkPoint, branch: str) -> bool:
    """Is the branch's guard the source run's guard (A on a frozen TGR source, B on a tgr_tracker source)?"""
    return (BRANCH_GUARD[branch] == TRACKER_GUARD) == (fork.source_guard == TRACKER_GUARD)


def _rule_entry(rule_id: str, guard: Any) -> Dict[str, Any]:
    """{rule_id, description, logic} as TGR's violated_rules (description and logic when the guard has the rules)."""
    rules = getattr(getattr(getattr(guard, "tgr", None), "aspm", None), "rules", None) or {}
    r = rules.get(rule_id) if hasattr(rules, "get") else None
    if r is None:
        return {"rule_id": rule_id}
    return {"rule_id": rule_id, "description": r.description, "logic": r.logic}


def fork_guard_record(fork: ForkPoint, branch: str, tp: Dict[str, Any], n_exec: int, trace_len: int,
                      source_record: Optional[dict], guard: Any = None) -> Dict[str, Any]:
    """The guard record of the fork attempt in this branch (no guard call in the try). Its margin, violated rules and
    the predicate values used are the branch guard's at the fork (audit A4 W1; p6_metrics reads violated_rules):
    the saved record's when the branch's guard is the source run's guard, else the fork point's (margin_a/b,
    violated_a/b, values_a/b, from find_points)."""
    decision, feedback = branch_decision(fork, branch)
    from repro_online.episode import _slim             # runner copy
    same = is_source_kind(fork, branch) and isinstance(source_record, dict)
    if same:
        margin = source_record.get("margin")
        violated = copy.deepcopy(source_record.get("violated_rules") or []) if decision == "block" else []
        values = {n: (v.get("value") if isinstance(v, dict) else v)
                  for n, v in (source_record.get("judge") or {}).items()}
        from_ = "source record (the branch's guard is the source run's guard)"
    else:
        margin = fork.margin_a if branch == "A" else fork.margin_b
        ids = fork.violated_a if branch == "A" else fork.violated_b
        violated = [_rule_entry(str(r), guard) for r in ids] if decision == "block" else []
        values = {}
        from_ = "fork point (find_points: the branch guard's own decision at the fork, judge values given)"
    fp_values = fork.values_a if branch == "A" else fork.values_b
    if fp_values:
        values = {n: (v.get("value") if isinstance(v, dict) else v) for n, v in fp_values.items()}
    rec = {"step_index": n_exec, "kind": "respond" if fork.action == RESPOND else "tool_call", "name": fork.action,
           "trace_len_before": trace_len, "trace_position": tp, "action_allowed": decision == "allow",
           "margin": margin, "violated_rules": violated, "values_used": values,
           "fork_applied": {"branch": branch, "guard": BRANCH_GUARD[branch], "decision": decision,
                            "note": "the fork point's decision for this branch; no guard call in this try",
                            "margin_rules_values_from": from_},
           "changed_predicates": copy.deepcopy(fork.changed_predicates),
           "source_record": _slim(copy.deepcopy(source_record)) if source_record else None,
           "usage": dict(ZERO_USAGE), "seconds": 0.0}
    if decision == "block":
        rec["feedback_text"] = feedback
    return rec


# ------------------------------------------------------------------------------------------------ the branch

def run_branch(state: ForkState, branch: str, try_index: int, *, env: Any, guard: Any, agent_completion: Callable,
               tools_info: List[dict], source: Dict[str, Any], message_to_action: Optional[Callable] = None,
               usage_fn: Optional[Callable[[], dict]] = None, max_num_steps: Optional[int] = None,
               cap: Optional[int] = None) -> Dict[str, Any]:
    """Apply the branch's decision at the fork attempt, then continue run_episode's loop (module docstring).

    env: a τ-bench env at the fork state (fork/branch_env.py check_env). guard: the branch's guard (shared across
    threads, as in the wrapper). agent_completion: exp_core.models.make_completion("agent") (or a fake in tests).
    source: load_source(state.fork). usage_fn: exp_core.models.episode_usage (this thread's agent and user usage,
    reset before the try). The state is not changed. An exception inside the loop gives a record with `error`."""
    from repro_online import episode as ep_mod          # runner copy: _slim, the user-call timer
    if message_to_action is None:
        from tau_bench.agents.tool_calling_agent import message_to_action   # venv τ-bench
    fork = state.fork
    decision, feedback = branch_decision(fork, branch)
    max_num_steps = state.max_steps if max_num_steps is None else max_num_steps
    cap = state.cap if cap is None else cap
    ep_mod._tls.user = {"seconds": 0.0, "calls": 0}
    t_start = time.time()
    messages: List[Dict[str, Any]] = copy.deepcopy(state.messages)
    executed: List[Dict[str, Any]] = copy.deepcopy(state.executed)
    conv = guard.new_episode()
    conv.trace = copy.deepcopy(state.trace)
    prefix = copy.deepcopy(source["attempts_prefix"])
    for x in prefix:
        x["fork_part"] = "prefix"
    attempts: List[Dict[str, Any]] = []
    reward, done, info = 0.0, False, {}
    agent = {"calls": 0, "cost": 0.0, "seconds": 0.0}
    gcost = {"calls": 0, "cost": 0.0, "seconds": 0.0, "llm_calls": 0}
    n_exec, consecutive = state.n_exec, state.consecutive_blocks
    tp = fork_trace_position(fork, branch, source["fork_trace_position"])
    fork_override = False
    error, tb = None, None
    first = True
    try:
        while n_exec < max_num_steps:
            if first:                                    # the fork attempt: the branch's decision, no guard call
                first, part = False, "fork"
                msg = copy.deepcopy(state.pending)
                action = message_to_action(msg)
                if action.name != RESPOND:
                    msg["tool_calls"] = msg["tool_calls"][:1]
                rec = fork_guard_record(fork, branch, tp, n_exec, len(conv.trace), source["fork_attempt"].get("guard"),
                                        guard)
                if rec["action_allowed"]:
                    conv.trace.append(rec["trace_position"])     # as TGR._step does for an allowed step
            else:                                        # run_episode's loop body
                part = "after"
                t0 = time.time()
                res = agent_completion(messages=messages, model="gpt-5-nano", custom_llm_provider="azure",
                                       tools=tools_info, temperature=0.0)
                agent["seconds"] += time.time() - t0
                agent["calls"] += 1
                agent["cost"] += res._hidden_params.get("response_cost") or 0.0
                msg = res.choices[0].message.model_dump()
                action = message_to_action(msg)
                if action.name != RESPOND:
                    msg["tool_calls"] = msg["tool_calls"][:1]
                rec = guard.check(conv, executed, msg, n_exec)
                if rec is not None:
                    gcost["calls"] += 1
                    gcost["cost"] += rec["usage"]["cost_usd"]
                    gcost["seconds"] += rec["seconds"]
                    gcost["llm_calls"] += rec["usage"]["n_llm_calls"]
            blocked = rec is not None and not rec["action_allowed"]
            override = blocked and consecutive >= cap
            if part == "fork":
                fork_override = override
            att = {"exec_step": n_exec, "attempt": consecutive + 1, "action": action.name,
                   "kwargs": copy.deepcopy(action.kwargs), "agent_text": msg.get("content") or "",
                   "blocked": blocked and not override, "cap_override": override,
                   "executed_prefix_len": len(executed), "guard": ep_mod._slim(rec), "fork_part": part}
            if blocked and not override:
                consecutive += 1
                fb = rec.get("feedback_text") or "BLOCKED by policy guardrail."
                att["feedback"] = fb
                attempts.append(att)
                if action.name != RESPOND:
                    tc = msg["tool_calls"][0]
                    messages += [msg, {"role": "tool", "tool_call_id": tc["id"], "name": tc["function"]["name"],
                                       "content": fb}]
                else:
                    messages += [msg, {"role": "system", "content": fb}]
                continue
            if override:
                guard.commit(conv, rec)
            consecutive = 0
            env_response = env.step(action)
            reward = env_response.reward
            info = {**info, **env_response.info.model_dump()}
            att["observation"] = env_response.observation
            attempts.append(att)
            if action.name != RESPOND:
                tc = msg["tool_calls"][0]
                new = [msg, {"role": "tool", "tool_call_id": tc["id"], "name": tc["function"]["name"],
                             "content": env_response.observation}]
            else:
                new = [msg, {"role": "user", "content": env_response.observation}]
            messages += new
            executed += new
            n_exec += 1
            if env_response.done:
                done = True
                break
    except Exception as e:  # noqa: BLE001 - recorded as a failed try (as the wrapper records a failed episode)
        error, tb = f"{type(e).__name__}: {e}", traceback.format_exc()
        reward, done = 0.0, False
    user_t = ep_mod.user_timer()
    whole = prefix + attempts
    out = {"task_index": state.task_index, "reward": reward, "done": done, "n_exec_steps": n_exec,
           "n_blocks": sum(bool(x.get("blocked")) for x in whole),
           "n_cap_overrides": sum(bool(x.get("cap_override")) for x in whole),
           "seconds": round(time.time() - t_start, 1),
           "cost": {"agent": agent["cost"], "user": 0.0, "guard": gcost["cost"]},
           "latency": {"agent": round(agent["seconds"], 1), "user": round(user_t["seconds"], 1),
                       "guard": round(gcost["seconds"], 1)},
           "calls": {"agent": agent["calls"], "user": user_t["calls"], "guard_checks": gcost["calls"],
                     "guard_llm": gcost["llm_calls"]},
           "attempts": whole, "messages": messages, "executed": executed,
           "reward_info": (json.loads(json.dumps(info.get("reward_info"), default=str))
                           if info.get("reward_info") and error is None else None),
           "error": error}
    if tb:
        out["traceback"] = tb
    if usage_fn is not None:
        u = json.loads(json.dumps(usage_fn()))
        out["usage_roles"] = u
        out["cost"]["agent"], out["cost"]["user"] = u["agent"]["cost"], u["user"]["cost"]
    i = fork.attempt_index
    out.update({
        "env": fork.domain, "guard": BRANCH_GUARD[branch], "trial": int(try_index), "profile": fork.profile,
        "stage": "B", "fork_id": fork.fork_id, "branch": branch, "try": int(try_index),
        "task_split": state.task_split, "source_trial": fork.trial, "fork": fork.to_dict(),
        "fork_attempt_index": i, "fork_decision": decision, "fork_feedback": feedback if decision == "block" else None,
        "fork_cap_override": fork_override, "fork_trace_position": tp,
        "n_attempts_before_fork": i, "n_exec_before_fork": state.n_exec,
        "n_exec_after_fork": n_exec - state.n_exec,
        "n_blocks_after_fork": sum(bool(x["blocked"]) for x in attempts),
        "n_cap_overrides_after_fork": sum(bool(x["cap_override"]) for x in attempts),
        "max_steps": max_num_steps, "cap": cap,
        "user_messages_final": copy.deepcopy(getattr(getattr(env, "user", None), "messages", None)),
        "source_run": {"episodes_path": source.get("path"), "line_no": source.get("line_no"),
                       **(source.get("source") or {})},
        "cost_scope": "LLM calls of this try only (after the fork); the prefix is the source run's",
    })
    out["cost_usd"] = round(sum(float(v or 0.0) for v in out["cost"].values()), 8)
    return out
