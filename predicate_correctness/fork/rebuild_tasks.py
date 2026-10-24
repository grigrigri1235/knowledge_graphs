"""Eval v2 Part 3 (fork/rebuild_tasks.py): τ-bench's tasks and the user simulator's prompt, without importing
tau_bench (standard library only).

- Tasks: the venv's task files are Python lists of Task(...) / Action(...) calls with literal arguments. They are
  read with `ast` (read only) and become plain dicts {annotator, user_id, instruction, actions: [{name, kwargs}],
  outputs}. The same method as Part 1 (part1.md section 1), which checked that the result equals what τ-bench loads.
- The user simulator's system prompt: a copy of the venv's tau_bench/envs/user.py
  LLMUserSimulationEnv.build_system_prompt (text unchanged, including its typo "satisified"). fork/rebuild.py
  make_env checks it against τ-bench's own function on every env it builds; tests check the text against the file.
"""
from __future__ import annotations

import ast
import os
from typing import Dict, List, Optional

VENV_TAU = os.path.expanduser("~/venvs/tau-bench/lib/python3.12/site-packages/tau_bench")
USER_PY = os.path.join(VENV_TAU, "envs", "user.py")

# (domain, task_split) -> (file, variable): the splits MockRetailDomainEnv / MockAirlineDomainEnv accept.
TASK_FILES = {
    ("retail", "test"): (os.path.join(VENV_TAU, "envs", "retail", "tasks_test.py"), "TASKS_TEST"),
    ("retail", "train"): (os.path.join(VENV_TAU, "envs", "retail", "tasks_train.py"), "TASKS_TRAIN"),
    ("retail", "dev"): (os.path.join(VENV_TAU, "envs", "retail", "tasks_dev.py"), "TASKS_DEV"),
    ("airline", "test"): (os.path.join(VENV_TAU, "envs", "airline", "tasks_test.py"), "TASKS"),
}

GREETING = "Hi! How can I help you today?"       # LLMUserSimulationEnv.reset: the user simulator's first input

_CACHE: Dict[tuple, List[dict]] = {}


def _value(node):
    """A literal, or Task(...) / Action(...) as a dict of its keyword arguments."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("Task", "Action"):
        if node.args:
            raise ValueError("positional arguments in a task file")
        return {kw.arg: _value(kw.value) for kw in node.keywords}
    if isinstance(node, ast.List):
        return [_value(x) for x in node.elts]
    if isinstance(node, ast.Dict):
        return {_value(k): _value(v) for k, v in zip(node.keys, node.values)}
    return ast.literal_eval(node)


def tasks(domain: str, task_split: str) -> List[dict]:
    """All tasks of a split, in τ-bench's order (index = env.tasks index)."""
    key = (domain, task_split)
    if key not in TASK_FILES:
        raise ValueError(f"no τ-bench task split {task_split!r} for {domain!r}")
    if key not in _CACHE:
        path, var = TASK_FILES[key]
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=path)
        for st in tree.body:
            if isinstance(st, ast.Assign) and any(isinstance(t, ast.Name) and t.id == var for t in st.targets):
                _CACHE[key] = _value(st.value)
                break
        else:
            raise ValueError(f"{var} not found in {path}")
    return _CACHE[key]


def task(domain: str, task_split: str, task_index: int) -> dict:
    """One task: {annotator, user_id, instruction, actions, outputs}."""
    ts = tasks(domain, task_split)
    if not 0 <= task_index < len(ts):
        raise IndexError(f"{domain}/{task_split} has {len(ts)} tasks; no index {task_index}")
    return ts[task_index]


def user_system_prompt(instruction: Optional[str]) -> str:
    """Copy of tau_bench/envs/user.py LLMUserSimulationEnv.build_system_prompt (venv, same as tau-bench-59a200c)."""
    instruction_display = (
        ("\n\nInstruction: " + instruction + "\n")
        if instruction is not None
        else ""
    )
    return f"""You are a user interacting with an agent.{instruction_display}
Rules:
- Just generate one line at a time to simulate the user's message.
- Do not give away all the instruction at once. Only provide the information that is necessary for the current step.
- Do not hallucinate information that is not provided in the instruction. For example, if the agent asks for the order id but it is not mentioned in the instruction, do not make up an order id, just say you do not remember or have it.
- If the instruction goal is satisified, generate '###STOP###' as a standalone message without anything else to end the conversation.
- Do not repeat the exact instruction in the conversation. Instead, use your own words to convey the same information.
- Try to make the conversation as natural as possible, and stick to the personalities in the instruction."""
