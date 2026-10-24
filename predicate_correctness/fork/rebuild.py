"""Eval v2 Part 3 (fork/rebuild.py): rebuild a saved conversation at its fork point (part1.md 5.6).

    from fork.rebuild import rebuild, make_env
    state = rebuild(fork_point)                      # ForkState (standard library; both Pythons)
    env = make_env(state, user_model="gpt-6-luna")   # a τ-bench env at the fork (venv Python only)

rebuild(fork_point) -> ForkState, at attempt i = fork_point.attempt_index of the saved conversation
(fork_point.episodes_path, raw line fork_point.line_no):
  messages            ep["messages"][:2 + 2i]         what the agent saw before the fork attempt
  pending             ep["messages"][2 + 2i]          the agent's message at the fork (one tool call, or a text)
  executed            ep["executed"][:prefix]         the history the guard and the judge see (prefix =
                                                      attempts[i].executed_prefix_len = 2 + 2 * exec_step)
  data                τ-bench's data, fresh, with every executed tool call of `executed` replayed in order
                      (state_tracker/state.py Tracker; arguments from the message, copied before the call; cap
                      override attempts ran, so they are in `executed` and are replayed; blocked ones are not)
  env_actions         every executed agent message as a τ-bench action {name, kwargs}, replies to the user included
                      (as τ-bench's message_to_action; env.actions; the scorer checks reply texts in it)
  user_messages       the user simulator's message list (part1.md 5.3): its system prompt (task instruction), the
                      greeting, its first message, then for every executed reply: the agent's text as "user" and its
                      answer as "assistant" (with tool_calls None, as LLMUserSimulationEnv stores it)
  trace               trace_position of every executed attempt before i, in order (cap overrides included)
  consecutive_blocks  attempts[i].attempt - 1         n_exec = attempts[i].exec_step     max_steps 30, cap 3
  task_split, task_index   "test" for sources 1-2 (τ-bench test split; splits.json train/val labels), "train" for
                      Stage A (τ-bench TASKS_TRAIN)
  extra               {domain, agent, profile, run, source, instruction, user_id, replay: {tool_calls, mismatches,
                      problems}, source_episode: {reward, done, n_attempts, n_exec_steps}}
rebuild() never calls an LLM and never builds a τ-bench env.

How to load a τ-bench env for a ForkState without an LLM call (B3): call make_env(state, user_model=<the profile's
user model>). It
  1. builds the env with get_env(domain, user_strategy="human", task_split=state.task_split,
     task_index=state.task_index): a human user env makes no LLM call (part1.md 5.7 trap 2). It never calls
     env.reset() (reset calls the user simulator);
  2. sets env.task_index, env.task = env.tasks[index], env.data = env.data_load_func(), and replays every executed
     tool call through env.tools_map[name].invoke with a deep copy of its kwargs (exceptions -> "Error: ...", as
     Env.step; replay_into_env), and sets env.actions (replies included). It checks: every replayed output equals the
     saved one, env.data equals state.data, and env.actions equals state.env_actions;
  3. sets env.user to an LLMUserSimulationEnv made WITHOUT its __init__ (which would make one LLM call): messages =
     state.user_messages, model = user_model, provider = user_provider, total_cost = 0. It checks that τ-bench's own
     build_system_prompt(env.task.instruction) equals state.user_messages[0].
  Any failed check raises RebuildError. The user simulator's next call goes through the module global
  tau_bench.envs.user.completion, so point it at the profile's user model first, as guard/run_online.py does:
      user_mod.completion = episode.timed_user_completion(models.make_completion("user"))
  Then env.step(action) works as in a normal run, and the env.step that ends the conversation scores it from
  env.data and env.actions (τ-bench's calculate_reward). Score test-split tasks with task_split "test" and Stage A
  tasks with "train": make_env uses state.task_split.

Standard library only at import time (make_env imports tau_bench inside). Never imports gold code.
"""
from __future__ import annotations

import copy
import json
import os
import threading
from typing import Any, Dict, List, Optional, Tuple

from fork import rebuild_tasks
from fork.schema import ForkPoint, ForkState
from state_tracker import paths
from state_tracker.state import Tracker

RESPOND = "respond"


class RebuildError(RuntimeError):
    """The saved conversation does not give a consistent state at the fork point."""


# ----------------------------------------------------------------------------------------------- reading lines
_INDEX: Dict[str, Tuple[int, List[int]]] = {}       # path -> (file size when indexed, byte offset of each line)
_INDEX_LOCK = threading.Lock()


def abs_path(rel: str) -> str:
    return rel if os.path.isabs(rel) else os.path.join(paths.PC_DIR, rel)


def read_line(path: str, line_no: int) -> dict:
    """Raw line `line_no` (0-based) of a JSONL file, parsed. Files that only grow (resumed runs) stay valid."""
    path = abs_path(path)
    size = os.path.getsize(path)
    with _INDEX_LOCK:
        known = _INDEX.get(path)
        if known is None or known[0] != size:
            offsets, pos = [], 0
            with open(path, "rb") as f:
                for line in f:
                    offsets.append(pos)
                    pos += len(line)
            _INDEX[path] = known = (size, offsets)
    offsets = known[1]
    if not 0 <= line_no < len(offsets):
        raise RebuildError(f"{path} has {len(offsets)} lines; no line {line_no}")
    with open(path, "rb") as f:
        f.seek(offsets[line_no])
        return json.loads(f.readline().decode("utf-8"))


def read_episode(fp: ForkPoint) -> dict:
    """The fork point's saved conversation; checks that the line is that conversation."""
    ep = read_line(fp.episodes_path, fp.line_no)
    want = (fp.task_index, fp.trial, fp.domain)
    got = (ep.get("task_index"), ep.get("trial"), ep.get("env"))
    if got != want:
        raise RebuildError(f"{fp.fork_id}: line {fp.line_no} of {fp.episodes_path} is {got}, not {want}")
    if ep.get("error") is not None:
        raise RebuildError(f"{fp.fork_id}: line {fp.line_no} is a failed run ({ep['error']})")
    return ep


# ----------------------------------------------------------------------------------------------- pieces
def action_of(msg: dict) -> Tuple[str, Dict[str, Any]]:
    """(name, kwargs) of an agent message, as τ-bench's message_to_action: the first tool call with its arguments
    from the message's JSON string, else a reply with the message text."""
    tcs = msg.get("tool_calls")
    if tcs and tcs[0].get("function") is not None:
        fn = tcs[0]["function"]
        raw = fn.get("arguments")
        return fn["name"], (json.loads(raw) if isinstance(raw, str) else copy.deepcopy(raw or {}))
    return RESPOND, {"content": msg.get("content")}


def env_actions(executed: List[dict]) -> List[Dict[str, Any]]:
    """Every executed agent message of executed[2:] as a τ-bench action {name, kwargs}, in order."""
    out = []
    for k in range(2, len(executed) - 1, 2):
        name, kwargs = action_of(executed[k])
        out.append({"name": name, "kwargs": kwargs})
    return out


def user_sim_messages(executed: List[dict], instruction: str) -> List[Dict[str, Any]]:
    """The user simulator's message list after `executed` (part1.md 5.3). It never sees tool calls, tool outputs,
    blocked attempts or guard messages."""
    msgs: List[Dict[str, Any]] = [
        {"role": "system", "content": rebuild_tasks.user_system_prompt(instruction)},
        {"role": "user", "content": rebuild_tasks.GREETING},
        {"role": "assistant", "content": executed[1]["content"], "tool_calls": None},
    ]
    for k in range(2, len(executed) - 1, 2):
        m, r = executed[k], executed[k + 1]
        if r.get("role") == "user":
            msgs.append({"role": "user", "content": m.get("content")})
            msgs.append({"role": "assistant", "content": r.get("content"), "tool_calls": None})
    return msgs


def trace_before(ep: dict, i: int) -> List[Any]:
    """The guard's trace at attempt i: trace_position of each executed attempt before it (cap overrides too)."""
    return [copy.deepcopy((x.get("guard") or {}).get("trace_position")) for x in ep["attempts"][:i]
            if not x["blocked"]]


def replay(domain: str, executed: List[dict]):
    """Fresh τ-bench data with the executed tool calls replayed in order (the saved outputs are compared)."""
    tr = Tracker(domain)
    tr.feed(executed)
    st = tr.finish()
    return st


# ----------------------------------------------------------------------------------------------- rebuild
def rebuild(fp: ForkPoint, ep: Optional[dict] = None) -> ForkState:
    """Everything needed to continue the saved conversation at fork attempt fp.attempt_index (module docstring)."""
    ep = ep if ep is not None else read_episode(fp)
    i = fp.attempt_index
    atts = ep["attempts"]
    if not 0 <= i < len(atts):
        raise RebuildError(f"{fp.fork_id}: no attempt {i} (the conversation has {len(atts)})")
    if len(ep["messages"]) < 3 + 2 * i:
        raise RebuildError(f"{fp.fork_id}: messages too short for attempt {i}")
    a = atts[i]
    prefix = a["executed_prefix_len"]
    if prefix != 2 + 2 * a["exec_step"]:
        raise RebuildError(f"{fp.fork_id}: executed_prefix_len {prefix} != 2 + 2 * exec_step {a['exec_step']}")
    executed = copy.deepcopy(ep["executed"][:prefix])
    if len(executed) != prefix:
        raise RebuildError(f"{fp.fork_id}: executed has {len(ep['executed'])} messages, prefix {prefix}")
    st = replay(fp.domain, executed)
    task = rebuild_tasks.task(fp.domain, fp.task_split, fp.task_index)
    return ForkState(
        fork=fp, task_split=fp.task_split, task_index=fp.task_index,
        data=st.db,
        env_actions=env_actions(executed),
        messages=copy.deepcopy(ep["messages"][:2 + 2 * i]),
        executed=executed,
        pending=copy.deepcopy(ep["messages"][2 + 2 * i]),
        user_messages=user_sim_messages(executed, task["instruction"]),
        trace=trace_before(ep, i),
        consecutive_blocks=a["attempt"] - 1,
        n_exec=a["exec_step"],
        extra={"domain": fp.domain, "agent": fp.agent, "profile": fp.profile, "run": fp.run, "source": fp.source,
               "instruction": task["instruction"], "user_id": task.get("user_id"),
               "replay": {"tool_calls": len(st.events), "mismatches": st.mismatches, "problems": st.problems,
                          "parse_problems": st.parse_problems},
               "source_episode": dict({k: ep.get(k) for k in ("reward", "done", "n_exec_steps")},
                                      n_attempts=len(atts))},
    )


# ----------------------------------------------------------------------------------------------- τ-bench env (venv)
def _jnorm(x):
    return json.loads(json.dumps(x, default=str))


def replay_into_env(env: Any, executed: List[dict], message_to_action, respond_name: str = RESPOND) -> List[str]:
    """env.data = a fresh env.data_load_func(), every executed tool call of `executed` replayed in order through
    env.tools_map[name].invoke (an exception gives "Error: ...", as Env.step), env.actions = every executed action
    (replies included). Each tool gets a deep copy of the action's kwargs: a τ-bench tool can store a passed list in
    the database (book_reservation keeps payment_methods as payment_history) and a later tool can change it in place
    (cancel_reservation appends the refund), which would change env.actions too (part1.md 5.7 trap 1; audit A4 W3).
    Returns the problems (a replayed output that differs from the saved one)."""
    env.data = env.data_load_func()
    env.actions = []
    problems: List[str] = []
    for k in range(2, len(executed) - 1, 2):
        m, r = executed[k], executed[k + 1]
        action = message_to_action(m)
        env.actions.append(action)
        if action.name == respond_name:
            continue
        if action.name in env.tools_map:
            try:
                out = env.tools_map[action.name].invoke(data=env.data, **copy.deepcopy(action.kwargs))
            except Exception as e:  # noqa: BLE001 - as Env.step
                out = f"Error: {e}"
        else:
            out = f"Unknown action {action.name}"
        if out != r.get("content"):
            problems.append(f"executed[{k}] {action.name}: replayed output differs from the saved one")
    return problems


def make_env(state: ForkState, user_model: Optional[str] = None, user_provider: str = "azure", check: bool = True):
    """A τ-bench env at the fork, with no LLM call (module docstring). Venv Python only."""
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")    # litellm: no download at import
    from tau_bench.agents.tool_calling_agent import message_to_action
    from tau_bench.envs import get_env
    from tau_bench.envs.user import LLMUserSimulationEnv
    from tau_bench.types import RESPOND_ACTION_NAME

    domain = state.extra.get("domain") or state.fork.domain
    env = get_env(domain, user_strategy="human", user_model=user_model or "none", task_split=state.task_split,
                  task_index=state.task_index)
    env.task_index = state.task_index
    env.task = env.tasks[state.task_index]
    problems = replay_into_env(env, state.executed, message_to_action, RESPOND_ACTION_NAME)
    user = LLMUserSimulationEnv.__new__(LLMUserSimulationEnv)      # no __init__: it would call the LLM once
    user.messages = copy.deepcopy(state.user_messages)
    user.model, user.provider, user.total_cost = user_model, user_provider, 0.0
    env.user = user
    if check:
        if env.data != state.data:
            problems.append("env.data after the replay differs from state.data")
        if _jnorm([x.model_dump() for x in env.actions]) != _jnorm(state.env_actions):
            problems.append("env.actions differ from state.env_actions")
        if env.task.instruction != state.extra.get("instruction"):
            problems.append("the task instruction differs from the one rebuild() read")
        if user.build_system_prompt(instruction=env.task.instruction) != state.user_messages[0]["content"]:
            problems.append("τ-bench's user system prompt differs from the rebuilt one")
    if problems:
        raise RebuildError(f"{state.fork.fork_id}: " + "; ".join(problems[:5]))
    return env
