"""Eval v2 Part 3b (fork/branch_env.py): the τ-bench env of one Stage B try, set to the fork state, with no LLM call.

  - make_env(state, user_model): used only when fork/rebuild.py has no make_env(state). It builds the env with
    user_strategy="human" (no user-model call; same tools_info and wiki as "llm", output/eval_v2/checks/part1.md 5.7
    trap 2), then sets (part1.md 5.5):
      env.task_index, env.task   = the fork's task (get_env with the fork's task_split and task_index);
      env.data                   = a deep copy of the replayed database (state.data);
      env.actions                = the executed history as τ-bench actions, replies included (state.env_actions);
      env.user                   = an LLMUserSimulationEnv made without __init__ (its __init__ calls the user model
                                   once), with messages = the rebuilt user-simulator list (state.user_messages).
    env.reset() is never called (it reloads the data and calls the user simulator).
  - check_env(env, state): run on every env before a try, whoever built it. It checks the task, the data, the
    actions and the user simulator's list against the fork state.

τ-bench (the venv package) is imported only inside make_env. Never imports gold code.
"""
from __future__ import annotations

import contextlib
import copy
import io
from typing import Any

from fork.schema import ForkState

# number of tasks per (domain, task_split) in τ-bench (part1.md section 1)
TASK_COUNTS = {("retail", "test"): 115, ("retail", "train"): 500, ("airline", "test"): 50}


class EnvMismatch(RuntimeError):
    """The env does not match the fork state."""


def make_env(state: ForkState, user_model: str, provider: str = "azure") -> Any:
    from tau_bench.envs import get_env                  # venv τ-bench
    from tau_bench.envs.user import LLMUserSimulationEnv
    from tau_bench.types import Action
    fork = state.fork
    with contextlib.redirect_stdout(io.StringIO()):
        env = get_env(fork.domain, user_strategy="human", user_model=user_model, user_provider=provider,
                      task_split=state.task_split, task_index=state.task_index)
    user = LLMUserSimulationEnv.__new__(LLMUserSimulationEnv)   # no __init__: it would call the user model once
    user.messages = copy.deepcopy(state.user_messages)
    user.model = user_model
    user.provider = provider
    user.total_cost = 0.0
    env.user = user
    env.task_index = state.task_index
    env.task = env.tasks[state.task_index]
    env.data = copy.deepcopy(state.data)
    env.actions = [Action(name=a["name"], kwargs=copy.deepcopy(a["kwargs"])) for a in state.env_actions]
    return env


def check_env(env: Any, state: ForkState) -> None:
    """Raise EnvMismatch if the env is not at the fork state."""
    fork = state.fork
    want_n = TASK_COUNTS.get((fork.domain, state.task_split))
    if want_n is None:
        raise EnvMismatch(f"no τ-bench task split {state.task_split!r} for {fork.domain}")
    if len(env.tasks) != want_n:
        raise EnvMismatch(f"env has {len(env.tasks)} tasks; {fork.domain}/{state.task_split} has {want_n}")
    if env.task_index != state.task_index or env.task is not env.tasks[state.task_index]:
        raise EnvMismatch(f"env task {env.task_index} is not the fork's task {state.task_index}")
    user = env.user
    if type(user).__name__ not in ("LLMUserSimulationEnv",) and not getattr(user, "is_test_fake", False):
        raise EnvMismatch(f"env.user is a {type(user).__name__}, not an LLMUserSimulationEnv")
    if user.messages != state.user_messages:
        raise EnvMismatch("env.user.messages differ from the rebuilt user-simulator list")
    build = getattr(user, "build_system_prompt", None)
    if build is not None and (not user.messages or user.messages[0].get("content") != build(env.task.instruction)):
        raise EnvMismatch("the user simulator's system prompt is not the one of this task's instruction")
    got = [(a.name, a.kwargs) for a in env.actions]
    want = [(a["name"], a["kwargs"]) for a in state.env_actions]
    if got != want:
        raise EnvMismatch(f"env.actions ({len(got)}) differ from the executed history ({len(want)})")
    if env.data != state.data:
        raise EnvMismatch("env.data differs from the replayed database")
