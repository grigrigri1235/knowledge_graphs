"""Eval v2: read τ-bench's task files from the venv without importing tau_bench (standard library, `ast`).

The task files are Python lists of Task(...) / Action(...) calls with literal arguments. This turns them into plain
dicts {annotator, user_id, instruction, actions: [{name, kwargs}], outputs}. Read only; nothing is written.
Part 1 checks that the result equals what τ-bench itself loads (scoring/v2_p1_venv_check.py).
"""
from __future__ import annotations

import ast
import os
from typing import Dict, List

VENV_TAU = os.path.expanduser("~/venvs/tau-bench/lib/python3.12/site-packages/tau_bench")

# split name -> (file, variable). These are the splits MockRetailDomainEnv / MockAirlineDomainEnv accept.
TASK_FILES = {
    "retail/test": (os.path.join(VENV_TAU, "envs", "retail", "tasks_test.py"), "TASKS_TEST"),
    "retail/train": (os.path.join(VENV_TAU, "envs", "retail", "tasks_train.py"), "TASKS_TRAIN"),
    "retail/dev": (os.path.join(VENV_TAU, "envs", "retail", "tasks_dev.py"), "TASKS_DEV"),
    "airline/test": (os.path.join(VENV_TAU, "envs", "airline", "tasks_test.py"), "TASKS"),
}


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


def parse_tasks(path: str, var: str) -> List[dict]:
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    for st in tree.body:
        if isinstance(st, ast.Assign) and any(isinstance(t, ast.Name) and t.id == var for t in st.targets):
            return _value(st.value)
    raise ValueError(f"{var} not found in {path}")


def task_files() -> Dict[str, dict]:
    return {k: {"path": p, "var": v, "tasks": parse_tasks(p, v)} for k, (p, v) in TASK_FILES.items()}
