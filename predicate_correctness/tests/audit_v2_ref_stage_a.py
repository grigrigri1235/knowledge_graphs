"""R3 reference for the Part 4 audit (eval v2), part A: the Stage A task list (the 500 extra retail tasks).

Independent of the wrapper (guard/run_online.py is not read or imported). The tasks come from tau-bench in the venv,
built the way the copied runner builds an env (get_env), but with user_strategy="human": no user-simulator LLM call
(output/eval_v2/checks/part1.md 5.7 trap 2). The network is blocked inside this process. No LLM call.

For every train index: user_id, sha256 of the instruction, sha256 of the canonical actions JSON, number of actions,
and a check against the 115 test tasks (same user + same instruction, same instruction, same user + same actions).

Run from predicate_correctness/ with the venv Python:
  LITELLM_LOCAL_MODEL_COST_MAP=True PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B tests/audit_v2_ref_stage_a.py
Output: output/eval_v2/checks/ref/ref_stage_a_tasks.json and output/eval_v2/checks/ref/ref_stage_a.md
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import time

sys.dont_write_bytecode = True
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")      # litellm must not fetch its price map


def _no_network(*_a, **_k):
    raise RuntimeError("network blocked in the R3 reference (no LLM call allowed)")


socket.socket.connect = _no_network                                  # type: ignore[assignment]
socket.socket.connect_ex = _no_network                               # type: ignore[assignment]
socket.create_connection = _no_network                               # type: ignore[assignment]

PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(PC_DIR, "output", "eval_v2", "checks", "ref")
OUT_JSON = os.path.join(OUT_DIR, "ref_stage_a_tasks.json")
OUT_MD = os.path.join(OUT_DIR, "ref_stage_a.md")
SPLITS = os.path.join(PC_DIR, "from_shieldagent", "splits", "splits.json")
RULES_MANIFEST = os.path.join(PC_DIR, "from_shieldagent", "rules", "retail", "manifest.json")


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def canonical_actions(task) -> str:
    """The canonical actions JSON: [{"kwargs": ..., "name": ...}, ...] in task order, keys sorted, no spaces."""
    return json.dumps([{"name": a.name, "kwargs": a.kwargs} for a in task.actions], sort_keys=True,
                      ensure_ascii=False, separators=(",", ":"))


def write_file(path: str, text: str) -> None:
    path = os.path.abspath(path)
    if not path.startswith(OUT_DIR + os.sep) or not os.path.basename(path).startswith("ref_stage_a"):
        raise RuntimeError(f"refusing to write {path}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main() -> int:
    t0 = time.time()
    import tau_bench
    from tau_bench.envs import get_env
    from tau_bench.envs.retail.tasks_dev import TASKS_DEV
    from tau_bench.envs.retail.tasks_test import TASKS_TEST
    from tau_bench.envs.retail.tasks_train import TASKS_TRAIN

    tb_dir = os.path.dirname(os.path.abspath(tau_bench.__file__))
    retail_dir = os.path.join(tb_dir, "envs", "retail")

    def build(split: str, index: int = 0):
        return get_env("retail", user_strategy="human", user_model="none", task_split=split, task_index=index)

    env_train, env_test, env_dev = build("train"), build("test"), build("dev")
    checks = {}
    checks["env_train_tasks_is_TASKS_TRAIN"] = env_train.tasks is TASKS_TRAIN
    checks["env_test_tasks_is_TASKS_TEST"] = env_test.tasks is TASKS_TEST
    checks["env_dev_tasks_is_TASKS_DEV"] = env_dev.tasks is TASKS_DEV
    checks["user_simulator_class"] = type(env_train.user).__name__
    train, test, dev = env_train.tasks, env_test.tasks, env_dev.tasks

    # index range as the runner sees it: get_env(task_index=t) -> env.tasks[t]; reset(task_index=t) -> env.tasks[t]
    checks["train_index_499_builds"] = build("train", 499).task is train[499]
    try:
        build("train", len(train))
        checks["train_index_len_raises"] = None
    except IndexError as e:
        checks["train_index_len_raises"] = f"IndexError: {e}"
    try:
        get_env("airline", user_strategy="human", user_model="none", task_split="train", task_index=0)
        checks["airline_train_raises"] = None
    except ValueError as e:
        checks["airline_train_raises"] = f"ValueError: {e}"

    # same tools and policy for train and test envs (the rule set and the tool-schema check still apply)
    def tools_hash(tools_info, **kw) -> str:
        return sha256_text(json.dumps(tools_info, **kw))
    manifest = json.load(open(RULES_MANIFEST, encoding="utf-8"))
    want_tools = manifest["input"]["tools_sha256"]
    conventions = {"json.dumps(tools_info, sort_keys=True)": {"sort_keys": True},
                   "json.dumps(tools_info)": {},
                   "json.dumps(tools_info, sort_keys=True, ensure_ascii=False)": {"sort_keys": True, "ensure_ascii": False},
                   "json.dumps(tools_info, ensure_ascii=False)": {"ensure_ascii": False}}
    tools = {}
    for label, kw in conventions.items():
        tools[label] = {"train": tools_hash(env_train.tools_info, **kw), "test": tools_hash(env_test.tools_info, **kw)}
    match = [label for label, h in tools.items() if h["train"] == want_tools]
    checks["tools_info_train_equals_test"] = env_train.tools_info == env_test.tools_info
    checks["wiki_train_equals_test"] = env_train.wiki == env_test.wiki
    checks["tools_sha256_rule_set_manifest"] = want_tools
    checks["tools_sha256_train_matches_manifest_with"] = match
    checks["tools_sha256_train"] = tools[match[0]]["train"] if match else tools["json.dumps(tools_info, sort_keys=True)"]["train"]

    # the 115 test tasks and the partner's labels on them
    splits = json.load(open(SPLITS, encoding="utf-8"))["retail"]["split"]
    test_group = sorted(int(k) for k, v in splits.items() if v == "test")
    by_instr, by_user_instr, by_user_actions, by_user = {}, {}, {}, {}
    for j, t in enumerate(test):
        by_instr.setdefault(t.instruction, []).append(j)
        by_user_instr.setdefault((t.user_id, t.instruction), []).append(j)
        by_user_actions.setdefault((t.user_id, canonical_actions(t)), []).append(j)
        by_user.setdefault(t.user_id, []).append(j)
    dev_instr = {t.instruction for t in dev}
    train_instr_count = {}
    for t in train:
        train_instr_count[t.instruction] = train_instr_count.get(t.instruction, 0) + 1

    rows = []
    for i, t in enumerate(train):
        acts = canonical_actions(t)
        same_ui = by_user_instr.get((t.user_id, t.instruction), [])
        same_i = by_instr.get(t.instruction, [])
        same_ua = by_user_actions.get((t.user_id, acts), [])
        shared_user = by_user.get(t.user_id, [])
        rows.append({
            "index": i,
            "user_id": t.user_id,
            "instruction_sha256": sha256_text(t.instruction),
            "actions_sha256": sha256_text(acts),
            "n_actions": len(t.actions),
            "action_names": [a.name for a in t.actions],
            "n_outputs": len(t.outputs),
            "test_same_user_and_instruction": same_ui,
            "test_same_instruction": same_i,
            "test_same_user_and_actions": same_ua,
            "is_test_task": bool(same_ui or same_i),
            "test_tasks_with_same_user": shared_user,
            "test_group_tasks_with_same_user": [j for j in shared_user if j in test_group],
            "same_instruction_as_dev_task": t.instruction in dev_instr,
            "duplicate_instruction_in_train": train_instr_count[t.instruction] > 1,
        })

    list_canon = json.dumps([[r["index"], r["user_id"], r["instruction_sha256"], r["actions_sha256"], r["n_actions"]]
                             for r in rows], separators=(",", ":"))
    summary = {
        "n_tasks": len(rows),
        "index_min": rows[0]["index"] if rows else None,
        "index_max": rows[-1]["index"] if rows else None,
        "indices_contiguous": [r["index"] for r in rows] == list(range(len(rows))),
        "n_test_tasks": len(test),
        "n_dev_tasks": len(dev),
        "n_is_test_task": sum(r["is_test_task"] for r in rows),
        "n_same_user_and_instruction": sum(bool(r["test_same_user_and_instruction"]) for r in rows),
        "n_same_instruction": sum(bool(r["test_same_instruction"]) for r in rows),
        "n_same_user_and_actions": sum(bool(r["test_same_user_and_actions"]) for r in rows),
        "n_share_user_with_a_test_task": sum(bool(r["test_tasks_with_same_user"]) for r in rows),
        "n_share_user_with_a_test_group_task": sum(bool(r["test_group_tasks_with_same_user"]) for r in rows),
        "n_same_instruction_as_dev": sum(r["same_instruction_as_dev_task"] for r in rows),
        "n_duplicate_instruction_in_train": sum(r["duplicate_instruction_in_train"] for r in rows),
        "n_actions_total": sum(r["n_actions"] for r in rows),
        "n_unique_users": len({r["user_id"] for r in rows}),
        "list_sha256": sha256_text(list_canon),
        "list_sha256_definition": ("sha256 of json.dumps([[index, user_id, instruction_sha256, actions_sha256, n_actions] "
                                   "for every task in index order], separators=(',', ':'))"),
    }
    out = {
        "what": "R3 reference: tau-bench retail task_split 'train' (Stage A tasks), from the venv, no LLM",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "how": {
            "python": sys.executable,
            "tau_bench_dir": tb_dir,
            "env_build": "get_env('retail', user_strategy='human', user_model='none', task_split=<split>, task_index=t)",
            "files_sha256": {f: sha256_file(os.path.join(retail_dir, f)) for f in
                             ("tasks_train.py", "tasks_test.py", "tasks_dev.py", "env.py")},
            "instruction_sha256": "sha256(task.instruction.encode('utf-8'))",
            "actions_sha256": ("sha256 of json.dumps([{'name': a.name, 'kwargs': a.kwargs} for a in task.actions], "
                               "sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')"),
            "is_test_task": "same (user_id, instruction) as a test task, or same instruction as a test task",
            "splits_json": SPLITS,
            "splits_json_sha256": sha256_file(SPLITS),
            "test_group_indices": test_group,
        },
        "checks": checks,
        "summary": summary,
        "tasks": rows,
    }
    write_file(OUT_JSON, json.dumps(out, indent=1, ensure_ascii=False) + "\n")

    ok = (summary["n_tasks"] == 500 and summary["indices_contiguous"] and summary["n_is_test_task"] == 0
          and summary["n_same_user_and_actions"] == 0 and checks["env_train_tasks_is_TASKS_TRAIN"]
          and checks["tools_info_train_equals_test"] and checks["wiki_train_equals_test"])
    s = summary
    md = f"""# R3 reference: Stage A tasks

Date {time.strftime('%Y-%m-%d', time.gmtime())}. Made by `tests/audit_v2_ref_stage_a.py` (venv Python, network blocked,
no LLM call). Data: `ref_stage_a_tasks.json` (same folder). Result: **{'OK' if ok else 'PROBLEM'}**.

## How
- τ-bench from the venv: `{tb_dir}`.
- Env built as the copied runner does (`get_env`), but with `user_strategy="human"` (no user call):
  `get_env("retail", user_strategy="human", user_model="none", task_split="train", task_index=t)`; task = `env.tasks[t]`.
- `instruction_sha256` = sha256 of the instruction (utf-8).
- `actions_sha256` = sha256 of `json.dumps([{{"name", "kwargs"}} per action], sort_keys=True, ensure_ascii=False,
  separators=(",", ":"))`.
- "Test task" = same user and same instruction as one of the 115 test-split tasks, or same instruction.
- `list_sha256` = sha256 of `json.dumps([[index, user_id, instruction_sha256, actions_sha256, n_actions], ...],
  separators=(",", ":"))`, in index order. An auditor can compute the same from the wrapper's task list.

## Result
| check | value |
|---|---|
| tasks | {s['n_tasks']} (index {s['index_min']}–{s['index_max']}, contiguous: {s['indices_contiguous']}) |
| `env.tasks` is `TASKS_TRAIN` | {checks['env_train_tasks_is_TASKS_TRAIN']} |
| index 499 builds / index {s['n_tasks']} | {checks['train_index_499_builds']} / {checks['train_index_len_raises']} |
| airline `task_split="train"` | {checks['airline_train_raises']} |
| **test tasks among them** (same user + instruction, or same instruction) | **{s['n_is_test_task']}** |
| same user and same instruction as a test task | {s['n_same_user_and_instruction']} |
| same instruction as a test task | {s['n_same_instruction']} |
| same user and same actions as a test task | {s['n_same_user_and_actions']} |
| share a user with some test task (another task, same database user) | {s['n_share_user_with_a_test_task']} |
| share a user with a partner test-group task (label "test") | {s['n_share_user_with_a_test_group_task']} |
| same instruction as a dev task | {s['n_same_instruction_as_dev']} |
| duplicate instructions inside the 500 | {s['n_duplicate_instruction_in_train']} |
| actions in total / unique users | {s['n_actions_total']} / {s['n_unique_users']} |
| tool schemas and policy: train env = test env | {checks['tools_info_train_equals_test']} / {checks['wiki_train_equals_test']} |
| tool schemas sha256 = rule set manifest (`{want_tools[:12]}…`) | {bool(match)} ({', '.join(match) or 'no convention matched'}) |
| `list_sha256` | `{s['list_sha256']}` |

File sha256 (venv): `tasks_train.py` `{out['how']['files_sha256']['tasks_train.py'][:16]}…`,
`tasks_test.py` `{out['how']['files_sha256']['tasks_test.py'][:16]}…`.

## For the auditor
- A Stage A task is `(task_split="train", task_index)` with index 0–499. The same number in `task_split="test"` is a
  different task, so `splits.json` labels say nothing about these indices.
- Compare the wrapper's list (index, user_id, instruction hash, actions hash) with `tasks` in the JSON, or just its
  `list_sha256`.
- Sharing a database user with a test task is expected (same database) and is not a test task.
"""
    write_file(OUT_MD, md)
    print(json.dumps({"ok": ok, "summary": summary, "checks": checks, "seconds": round(time.time() - t0, 1)}, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
