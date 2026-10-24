"""Eval v2, Part 1: checks with no LLM call (docs/planning/tracker_eval_v2/p1.md, subtasks 1-6).

Standard library only. Scoring and checks only: this file may load gold code (subtask 4); guard/, state_tracker/
and fork/ never import it.

  1. the task sets of τ-bench in the venv (read only; parsed with `ast`, nothing from tau_bench is imported);
  2. the 500 extra retail tasks (tasks_train.py): count, index range, overlap with the 115 test tasks;
  3. checks on all 500 tasks and a fixed-seed sample of 20 (tools, arguments, users, replay of the expected actions);
  4. gold scorer v2 (the partner's p6_gold_score.py through output/eval/, scoring only) on 5 tasks, expected actions
     only, plus a variant with a login and a confirmation before each write;
  5. the conversation formats needed for forks, on every saved conversation (partner runs and our p10 runs);
  6. the numbers for the cost estimate (cost per conversation, fork points, the share of a conversation after a fork).

Output: output/eval_v2/checks/part1_checks.json. The prose is in output/eval_v2/checks/part1.md.

Run from predicate_correctness/ (stdlib Python):
    python3 -B -m scoring.v2_p1_checks > output/logs/v2_p1_checks.log 2>&1
"""
from __future__ import annotations

import collections
import importlib.util
import json
import os
import random
import re
import statistics
import sys
from typing import Any, Dict, List, Optional

sys.dont_write_bytecode = True

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "scoring"

from guard import write_guard                                               # noqa: E402  (stdlib)
from scoring.v2_task_files import VENV_TAU, task_files                     # noqa: E402  (stdlib, ast)
from state_tracker import decide_again as DA                                # noqa: E402
from state_tracker import paths, tau_copy                                   # noqa: E402
from state_tracker.state import load_db, run_tool                           # noqa: E402
from state_tracker.tgr_to_aspm import load_rule_set, to_aspm                 # noqa: E402

PC = paths.PC_DIR
OUT = paths.OUTPUT_DIR
CHECKS_DIR = os.path.join(OUT, "eval_v2", "checks")
OUT_JSON = os.path.join(CHECKS_DIR, "part1_checks.json")
EVAL_ROOT = os.path.join(OUT, "eval")                     # built by scoring/p10_eval.py build (symlinks)
SEED = 20261022
CAP = 3                                                    # repro_online/episode.py run_episode(cap=3)
MAX_STEPS = 30                                             # --max-steps default (copy and our wrapper)
GREETING = "Hi! How can I help you today?"                # tau_bench/envs/user.py LLMUserSimulationEnv.reset

# Saved conversations: (source, agent, run tag, folder with episodes.jsonl per domain)
SOURCES = [
    ("partner frozen TGR", "luna", "luna_train_v5", os.path.join(paths.RUNS_DIR, "luna_train_v5", "{d}", "tgr")),
    ("partner frozen TGR", "nano", "nano_train", os.path.join(paths.RUNS_DIR, "nano_train", "{d}", "tgr")),
    ("partner frozen TGR", "luna", "luna_val", os.path.join(paths.RUNS_DIR, "luna_val", "{d}", "tgr")),
    ("our TGR + tracker", "luna", "p10_luna_train", os.path.join(OUT, "online", "p10_luna_train", "{d}", "tgr_tracker")),
    ("our TGR + tracker", "nano", "p10_nano_train", os.path.join(OUT, "online", "p10_nano_train", "{d}", "tgr_tracker")),
    ("our TGR + tracker", "luna", "p10_luna_val", os.path.join(OUT, "online", "p10_luna_val", "{d}", "tgr_tracker")),
]


# ============================================================================================ 1. task files (ast)
# scoring/v2_task_files.py: task_files() parses the venv's task files with `ast` (no tau_bench import).


# ============================================================================================ 2-3. task checks
ID_PATTERNS = {
    "order id (#W...)": re.compile(r"#W\d{7}"),
    "payment method id": re.compile(r"\b(credit_card|paypal|gift_card)_\d+\b"),
    "item id (10 digits)": re.compile(r"\b\d{10}\b"),
}


def identity_in_instruction(instr: str, user: dict) -> Dict[str, bool]:
    low = instr.lower()
    name = f"{user['name']['first_name']} {user['name']['last_name']}".lower()
    return {"name": name in low, "zip": user["address"]["zip"] in instr, "email": user["email"].lower() in low}


def check_task(task: dict, db: dict, schemas: Dict[str, dict]) -> dict:
    """Checks on one retail task, on a fresh database copy (db is changed: the expected actions are replayed)."""
    out = {"user_id": task["user_id"], "annotator": task.get("annotator"), "n_actions": len(task["actions"]),
           "tools": [a["name"] for a in task["actions"]], "outputs": task.get("outputs") or [],
           "instruction_chars": len(task["instruction"]), "problems": []}
    user = db["users"].get(task["user_id"])
    out["user_in_db"] = user is not None
    if user is None:
        out["problems"].append("user not in the database")
    else:
        out["identity"] = identity_in_instruction(task["instruction"], user)
        idt = out["identity"]
        if not (idt["email"] or (idt["name"] and idt["zip"])):
            out["problems"].append("instruction has neither the email nor the name and zip")
    if not task["instruction"].strip():
        out["problems"].append("empty instruction")
    out["ids_in_instruction"] = {k: bool(p.search(task["instruction"])) for k, p in ID_PATTERNS.items()}
    replay = []
    for a in task["actions"]:
        name, kw = a["name"], a["kwargs"]
        sch = schemas.get(name)
        if sch is None:
            out["problems"].append(f"tool {name} is not a retail tool")
            continue
        params = sch["function"]["parameters"]
        unknown = sorted(set(kw) - set(params.get("properties", {})))
        missing = sorted(set(params.get("required", [])) - set(kw))
        if unknown or missing:
            out["problems"].append(f"{name}: arguments unknown {unknown} missing {missing}")
        oid = kw.get("order_id")
        if oid is not None:
            order = db["orders"].get(oid)
            if order is None:
                out["problems"].append(f"{name}: order {oid} not in the database")
            elif order["user_id"] != task["user_id"]:
                out["problems"].append(f"{name}: order {oid} belongs to {order['user_id']}")
        res = run_tool("retail", db, name, kw)
        failed = not isinstance(res, str) or res.startswith("Error") or res.startswith("Unknown action")
        replay.append({"tool": name, "failed": failed, "output_head": (res if isinstance(res, str) else str(res))[:120]})
        if failed:
            out["problems"].append(f"{name}: replay gives {str(res)[:100]}")
    out["replay"] = replay
    out["writes"] = [a["name"] for a in task["actions"] if a["name"] in WRITE_TOOLS]
    return out


WRITE_TOOLS = {"cancel_pending_order", "exchange_delivered_order_items", "modify_pending_order_address",
               "modify_pending_order_items", "modify_pending_order_payment", "modify_user_address",
               "return_delivered_order_items"}


def task_set_stats(checked: List[dict]) -> dict:
    n = len(checked)
    tools = collections.Counter(t for c in checked for t in c["tools"])
    return {
        "tasks": n,
        "annotators": dict(collections.Counter(str(c["annotator"]) for c in checked)),
        "mean_actions": round(statistics.mean(c["n_actions"] for c in checked), 2),
        "mean_write_actions": round(statistics.mean(len(c["writes"]) for c in checked), 2),
        "tasks_without_write": sum(not c["writes"] for c in checked),
        "tasks_with_outputs": sum(bool(c["outputs"]) for c in checked),
        "mean_instruction_chars": round(statistics.mean(c["instruction_chars"] for c in checked), 1),
        "tool_counts": dict(tools.most_common()),
        "login_tool_in_actions": sum(any(t.startswith("find_user_id") for t in c["tools"]) for c in checked),
        "ids_in_instruction": {k: sum(c["ids_in_instruction"][k] for c in checked) for k in ID_PATTERNS},
        "identity": {k: sum((c.get("identity") or {}).get(k, False) for c in checked) for k in ("name", "zip", "email")},
        "users_missing": sum(not c["user_in_db"] for c in checked),
        "tasks_with_problems": sum(bool(c["problems"]) for c in checked),
        "replay_failed_actions": sum(r["failed"] for c in checked for r in c["replay"]),
        "problem_kinds": dict(collections.Counter(re.sub(r"[#\w]*\d[\w]*", "<id>", p) for c in checked
                                                  for p in c["problems"]).most_common(20)),
    }


def overlap(train: List[dict], other: List[dict]) -> dict:
    key_ui = collections.defaultdict(list)
    for i, t in enumerate(other):
        key_ui[(t["user_id"], t["instruction"])].append(i)
    instr = {t["instruction"]: i for i, t in enumerate(other)}
    users = {t["user_id"] for t in other}
    acts = {(t["user_id"], json.dumps(t["actions"], sort_keys=True)) for t in other}
    return {
        "same_user_and_instruction": [i for i, t in enumerate(train) if (t["user_id"], t["instruction"]) in key_ui],
        "same_instruction": [i for i, t in enumerate(train) if t["instruction"] in instr],
        "same_user_and_actions": [i for i, t in enumerate(train)
                                  if (t["user_id"], json.dumps(t["actions"], sort_keys=True)) in acts],
        "train_tasks_whose_user_is_in_the_other_set": sum(t["user_id"] in users for t in train),
    }


# ============================================================================================ 4. gold scorer v2
def load_gold_scorer():
    """The partner's p6_gold_score.py (copy), loaded from output/eval/ so that its ROOT is output/eval/ (symlinks to
    from_shieldagent/scoring/ and from_shieldagent/gold/). Scoring only."""
    path = os.path.join(EVAL_ROOT, "scripts", "reproduction", "p6_gold_score.py")
    spec = importlib.util.spec_from_file_location("v2_p1_p6_gold_score", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def synth_episode(task: dict, policy: str, realistic: bool) -> dict:
    """An episode record (the run_episode shape) with the task's expected actions as the executed tool calls.
    realistic=False: the expected actions only. realistic=True: a login call, then get_order_details for each order
    in the write calls, and before each write an agent message that lists the call and asks for a yes, and a user
    "yes". At the end, one blocked attempt (a copy of the first write call) to run the scorer's block path too."""
    db = load_db("retail")
    user = db["users"][task["user_id"]]
    executed = [{"role": "system", "content": policy}, {"role": "user", "content": "Hi, I need help with my order."}]
    attempts = []
    n = [0]

    def call(name, kw, text=""):
        out = run_tool("retail", db, name, kw)
        tc = {"id": f"call_{n[0]}", "type": "function", "function": {"name": name, "arguments": json.dumps(kw)}}
        attempts.append({"exec_step": n[0], "attempt": 1, "action": name, "kwargs": kw, "agent_text": text,
                         "blocked": False, "cap_override": False, "executed_prefix_len": len(executed),
                         "observation": out})
        executed.extend([{"role": "assistant", "content": text, "tool_calls": [tc]},
                         {"role": "tool", "tool_call_id": tc["id"], "name": name, "content": out}])
        n[0] += 1

    def talk(agent, reply):
        attempts.append({"exec_step": n[0], "attempt": 1, "action": "respond", "kwargs": {"content": agent},
                         "agent_text": agent, "blocked": False, "cap_override": False,
                         "executed_prefix_len": len(executed), "observation": reply})
        executed.extend([{"role": "assistant", "content": agent, "tool_calls": None},
                         {"role": "user", "content": reply}])
        n[0] += 1

    if realistic:
        call("find_user_id_by_name_zip", {"first_name": user["name"]["first_name"],
                                          "last_name": user["name"]["last_name"], "zip": user["address"]["zip"]})
        for oid in sorted({a["kwargs"]["order_id"] for a in task["actions"] if "order_id" in a["kwargs"]}):
            call("get_order_details", {"order_id": oid})
    first_write = None
    for a in task["actions"]:
        name, kw = a["name"], a["kwargs"]
        if realistic and name in WRITE_TOOLS:
            talk(f"Here are the details: {name} with {json.dumps(kw)}. Do you confirm? Please answer yes to proceed.",
                 "Yes, please proceed.")
        if first_write is None and name in WRITE_TOOLS:
            first_write = (name, kw, len(executed))
        call(name, kw)
    if first_write:
        name, kw, prefix = first_write
        attempts.append({"exec_step": 0, "attempt": 1, "action": name, "kwargs": kw, "agent_text": "",
                         "blocked": True, "cap_override": False, "executed_prefix_len": prefix,
                         "feedback": "BLOCKED (synthetic)"})
    return {"task_index": None, "trial": 0, "reward": None, "error": None, "executed": executed,
            "attempts": attempts}


def gold_check(train: List[dict], picks: List[int]) -> dict:
    mod = load_gold_scorer()
    scorer = mod.GoldScorer("retail", "v2")
    policy = tau_copy.policy_text("retail")
    rows = []
    for i in picks:
        t = train[i]
        row = {"task": i, "writes": [a["name"] for a in t["actions"] if a["name"] in WRITE_TOOLS]}
        for variant, realistic in (("expected actions only", False), ("with login and yes", True)):
            try:
                g = scorer.score_episode(synth_episode(t, policy, realistic))
                row[variant] = {"error": None, "write_calls": len(g["write_calls"]),
                                "violations": sorted({v for c in g["write_calls"] for v in c["violations"]}),
                                "n_violating_calls": g["n_violating_calls"],
                                "blocks": [{"action": b["action"], "scorable": b["scorable"],
                                            "gold_violations": b.get("gold_violations")} for b in g["blocks"]]}
            except Exception as e:  # noqa: BLE001 - this is what the check looks for
                row[variant] = {"error": f"{type(e).__name__}: {e}"}
        rows.append(row)
    return {"scorer": os.path.relpath(os.path.join(EVAL_ROOT, "scripts", "reproduction", "p6_gold_score.py"), PC),
            "version": "v2", "rules_scored": len(scorer.rules), "tasks": rows,
            "errors": sum(1 for r in rows for v in ("expected actions only", "with login and yes") if r[v]["error"])}


# ============================================================================================ 5. episode formats
def load_episodes(path: str) -> List[dict]:
    """The runner's rule on resume: drop lines with an error, keep the last line per (task, trial)."""
    keep = {}
    n_lines = n_err = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            n_lines += 1
            r = json.loads(line)
            if r.get("error") is not None:
                n_err += 1
                continue
            keep[(r["task_index"], r["trial"])] = r
    return [keep[k] for k in sorted(keep)], n_lines, n_err


def user_sim_turns(executed: List[dict]) -> List[dict]:
    """The user simulator's own message list, rebuilt from the executed messages (tau_bench/envs/user.py
    LLMUserSimulationEnv): its system prompt and greeting come first (built from the task's instruction, not saved);
    each of its replies is an assistant message; each agent text it received is a user message."""
    turns = [{"role": "assistant", "content": executed[1]["content"]}]
    for i in range(2, len(executed) - 1, 2):
        m, r = executed[i], executed[i + 1]
        if r.get("role") == "user":
            turns.append({"role": "user", "content": m.get("content")})
            turns.append({"role": "assistant", "content": r.get("content")})
    return turns


def check_episode(ep: dict, policy: str) -> Dict[str, Any]:
    """Every relation a fork needs. Returns counts and a list of problems."""
    P = []
    msgs, exe, atts = ep["messages"], ep["executed"], ep["attempts"]
    if len(msgs) != 2 + 2 * len(atts):
        P.append(f"len(messages) {len(msgs)} != 2 + 2 * attempts {len(atts)}")
    if msgs[:2] != exe[:2]:
        P.append("messages[:2] != executed[:2]")
    if exe[0].get("role") != "system" or exe[0].get("content") != policy:
        P.append("executed[0] is not the policy")
    if exe[1].get("role") != "user":
        P.append("executed[1] is not a user message")
    n_exec, consecutive, trace = 0, 0, []
    c = collections.Counter()
    for i, a in enumerate(atts):
        if 3 + 2 * i >= len(msgs):
            P.append(f"attempt {i}: no messages")
            break
        m, r, g = msgs[2 + 2 * i], msgs[3 + 2 * i], a.get("guard") or {}
        tcs = m.get("tool_calls")
        if m.get("role") != "assistant":
            P.append(f"attempt {i}: messages[{2 + 2 * i}] is not the agent's")
        if (m.get("content") or "") != a["agent_text"]:
            P.append(f"attempt {i}: agent_text differs from the message")
        if a["action"] != "respond":
            if not (tcs and len(tcs) == 1 and tcs[0]["function"]["name"] == a["action"]):
                P.append(f"attempt {i}: tool call differs from action")
            elif json.loads(tcs[0]["function"]["arguments"]) != a["kwargs"]:
                # attempts[i].kwargs is the dict that went into the tool; a τ-bench tool can keep a list of it in the
                # database (book_reservation: payment_history), and a later call can change that list in place.
                # The message's arguments string is not changed. Counted, not a problem of the format.
                c["kwargs changed after the call (aliasing)"] += 1
                c["kwargs aliasing at " + f"{ep['task_index']}/{ep['trial']}/attempt{i}/{a['action']}"] += 1
        else:
            if tcs and tcs[0].get("function") is not None:
                P.append(f"attempt {i}: respond with a tool call")
            if a["kwargs"].get("content") != m.get("content"):
                P.append(f"attempt {i}: respond content differs")
            c["respond empty content"] += not m.get("content")
        if a["exec_step"] != n_exec:
            P.append(f"attempt {i}: exec_step {a['exec_step']} != {n_exec}")
        if a["attempt"] != consecutive + 1:
            P.append(f"attempt {i}: attempt {a['attempt']} != blocks in a row + 1 = {consecutive + 1}")
        if a["executed_prefix_len"] != 2 + 2 * n_exec:
            P.append(f"attempt {i}: executed_prefix_len {a['executed_prefix_len']} != {2 + 2 * n_exec}")
        if g.get("trace_len_before") != len(trace) or g.get("step_index") != n_exec:
            P.append(f"attempt {i}: trace_len_before/step_index != executed steps before")
        gblock = not g.get("action_allowed", True)
        override = gblock and consecutive >= CAP
        if a["cap_override"] != override or a["blocked"] != (gblock and not override):
            P.append(f"attempt {i}: blocked/cap_override do not follow the guard and the cap")
        if a["blocked"]:
            c["blocked " + ("respond" if a["action"] == "respond" else "tool call")] += 1
            fb = g.get("feedback_text") or "BLOCKED by policy guardrail."
            if a.get("feedback") != fb or "observation" in a:
                P.append(f"attempt {i}: feedback field")
            if a["action"] != "respond":
                if not (r.get("role") == "tool" and r.get("tool_call_id") == tcs[0]["id"]
                        and r.get("name") == a["action"] and r.get("content") == fb):
                    P.append(f"attempt {i}: blocked tool call answer is not a tool message with the feedback")
            elif not (r.get("role") == "system" and r.get("content") == fb):
                P.append(f"attempt {i}: blocked reply answer is not a system message with the feedback")
            consecutive += 1
            continue
        c["cap overrides"] += a["cap_override"]
        if exe[2 + 2 * n_exec: 4 + 2 * n_exec] != [m, r]:
            P.append(f"attempt {i}: executed[{2 + 2 * n_exec}:+2] != messages[{2 + 2 * i}:+2]")
        if r.get("content") != a.get("observation"):
            P.append(f"attempt {i}: observation differs from the answer message")
        if a["action"] == "respond" and r.get("role") != "user":
            P.append(f"attempt {i}: executed reply not followed by a user message")
        if a["action"] != "respond" and not (r.get("role") == "tool" and r.get("tool_call_id") == tcs[0]["id"]):
            P.append(f"attempt {i}: executed tool call not followed by its tool message")
        trace.append(g.get("trace_position"))
        consecutive = 0
        n_exec += 1
    if len(exe) != 2 + 2 * n_exec or n_exec != ep["n_exec_steps"]:
        P.append(f"executed length {len(exe)} / n_exec_steps {ep['n_exec_steps']} != {n_exec} steps")
    if ep["n_blocks"] != sum(a["blocked"] for a in atts) or ep["n_cap_overrides"] != sum(a["cap_override"] for a in atts):
        P.append("n_blocks / n_cap_overrides")
    last = exe[-1] if len(exe) > 2 else {}
    if ep["done"]:
        if last.get("role") == "user" and "###STOP###" in (last.get("content") or ""):
            end = "user ###STOP###"
        elif last.get("role") == "tool" and last.get("name") == "transfer_to_human_agents":
            end = "transfer_to_human_agents"
        else:
            end = "done, other"
            P.append("done, but the last message is neither ###STOP### nor a transfer")
    else:
        end = "max steps" if n_exec == MAX_STEPS else "not done, other"
        if n_exec != MAX_STEPS:
            P.append(f"not done but only {n_exec} executed steps")
    if bool(ep["done"]) != (ep.get("reward_info") is not None):
        P.append("reward_info present iff done: no")
    turns = user_sim_turns(exe)
    n_user = sum(1 for x in exe if x.get("role") == "user")
    if n_user != (len(turns) + 1) // 2:
        P.append("user messages in executed != user-simulator replies")
    ur, cr = ep.get("usage_roles") or {}, ep.get("calls") or {}
    return {"problems": P, "counts": c, "end": end, "n_exec": n_exec, "n_attempts": len(atts),
            "user_calls_saved": cr.get("user"), "user_calls_metered": (ur.get("user") or {}).get("calls"),
            "agent_calls_saved": cr.get("agent"), "agent_calls_metered": (ur.get("agent") or {}).get("calls"),
            "user_sim_turns": len(turns)}


def format_checks() -> dict:
    out = {}
    policies = {d: tau_copy.policy_text(d) for d in paths.DOMAINS}
    for source, agent, tag, pattern in SOURCES:
        for d in paths.DOMAINS:
            path = os.path.join(pattern.format(d=d), "episodes.jsonl")
            eps, n_lines, n_err = load_episodes(path)
            res = [check_episode(ep, policies[d]) for ep in eps]
            probs = [(ep["task_index"], ep["trial"], p) for ep, r in zip(eps, res) for p in r["problems"]]
            cnt = collections.Counter()
            for r in res:
                cnt.update(r["counts"])
            extra_user = collections.Counter((r["user_calls_metered"] or 0) - (r["user_calls_saved"] or 0) for r in res)
            extra_agent = collections.Counter((r["agent_calls_metered"] or 0) - (r["agent_calls_saved"] or 0) for r in res)
            out[f"{tag}/{d}"] = {
                "source": source, "agent": agent, "path": os.path.relpath(path, PC), "lines": n_lines,
                "error_lines": n_err, "conversations": len(eps),
                "conversations_with_problems": sum(bool(r["problems"]) for r in res),
                "problems_first": probs[:10], "attempts": sum(r["n_attempts"] for r in res),
                "executed_steps": sum(r["n_exec"] for r in res), "counts": dict(cnt),
                "ends": dict(collections.Counter(r["end"] for r in res)),
                "metered_minus_saved_user_calls": dict(extra_user),
                "metered_minus_saved_agent_calls": dict(extra_agent),
                "max_attempt_number": max((a["attempt"] for ep in eps for a in ep["attempts"]), default=0),
            }
            print(f"[format] {tag}/{d}: {len(eps)} conversations, problems in "
                  f"{out[f'{tag}/{d}']['conversations_with_problems']}", flush=True)
    return out


# ============================================================================================ 6. cost and forks
def cost_of(ep: dict) -> float:
    return sum((ep.get("cost") or {}).values())


def cost_numbers() -> dict:
    out = {}
    for source, agent, tag, pattern in SOURCES:
        for d in paths.DOMAINS:
            eps, _, _ = load_episodes(os.path.join(pattern.format(d=d), "episodes.jsonl"))
            costs = [cost_of(e) for e in eps]
            by_role = {r: round(statistics.mean((e.get("cost") or {}).get(r, 0.0) for e in eps), 5)
                       for r in ("agent", "user", "guard")}
            out[f"{tag}/{d}"] = {"conversations": len(eps), "mean_cost": round(statistics.mean(costs), 5),
                                 "mean_cost_by_role": by_role, "total_cost": round(sum(costs), 3),
                                 "mean_attempts": round(statistics.mean(len(e["attempts"]) for e in eps), 2),
                                 "mean_exec_steps": round(statistics.mean(e["n_exec_steps"] for e in eps), 2)}
    return out


def fork_numbers() -> dict:
    """First changed decision per conversation, and the share of the conversation after it (by attempts).
    Partner runs: output/p8_changes.jsonl, version b. Our p10 runs: the decision again with tracker.judge_values
    (as scoring/p10_metrics.py section 4)."""
    eps_cache = {}

    def episodes(tag, d, pattern):
        k = (tag, d)
        if k not in eps_cache:
            eps, _, _ = load_episodes(os.path.join(pattern.format(d=d), "episodes.jsonl"))
            eps_cache[k] = {(e["task_index"], e["trial"]): e for e in eps}
        return eps_cache[k]

    pattern_of = {tag: pattern for _, _, tag, pattern in SOURCES}
    forks = []
    # partner runs
    with open(os.path.join(OUT, "p8_changes.jsonl"), encoding="utf-8") as f:
        changes = [json.loads(line) for line in f]
    first = {}
    for ch in changes:
        if not (ch.get("b") or {}).get("change"):
            continue
        key = (ch["run"], ch["domain"], ch["task"], ch["trial"])
        if key not in first or (ch["exec_step"], ch["attempt"]) < (first[key]["exec_step"], first[key]["attempt"]):
            first[key] = ch
    for (run, d, t, k), ch in sorted(first.items()):
        ep = episodes(run, d, pattern_of[run])[(t, k)]
        idx = next(i for i, a in enumerate(ep["attempts"])
                   if a["exec_step"] == ch["exec_step"] and a["attempt"] == ch["attempt"])
        forks.append({"source": "partner frozen TGR", "tag": run, "domain": d, "task": t, "trial": k,
                      "attempt_index": idx, "kind": ch["b"]["change"], "reward": ep["reward"],
                      "n_attempts": len(ep["attempts"]), "cost": cost_of(ep),
                      "after_share": (len(ep["attempts"]) - idx) / len(ep["attempts"])})
    n_partner_changes = sum(1 for ch in changes if (ch.get("b") or {}).get("change"))
    # our p10 runs
    aspm = {d: to_aspm(load_rule_set(d)) for d in paths.DOMAINS}
    for tag in ("p10_luna_train", "p10_nano_train", "p10_luna_val"):
        for d in paths.DOMAINS:
            for (t, k), ep in episodes(tag, d, pattern_of[tag]).items():
                past = []
                for i, a in enumerate(ep["attempts"]):
                    rec = a["guard"]
                    tr = rec.get("tracker") or {}
                    jv = tr.get("judge_values")
                    if tr.get("applied") and jv is not None and rec.get("circuit"):
                        jd = DA.decide(aspm[d], rec, jv, past)
                        kind = DA.change_kind(jd["allowed"], rec["action_allowed"])
                        if kind:
                            forks.append({"source": "our TGR + tracker", "tag": tag, "domain": d, "task": t,
                                          "trial": k, "attempt_index": i, "kind": kind, "reward": ep["reward"],
                                          "n_attempts": len(ep["attempts"]), "cost": cost_of(ep),
                                          "after_share": (len(ep["attempts"]) - i) / len(ep["attempts"])})
                            break
                    if rec.get("action_allowed") or a.get("cap_override"):
                        past.append(rec["trace_position"])
    summary = {}
    for f_ in forks:
        k = f"{f_['tag']}/{f_['domain']}"
        s = summary.setdefault(k, {"forks": 0, "block removed": 0, "block added": 0, "after_share": [],
                                   "branch_try_cost": []})
        s["forks"] += 1
        s[f_["kind"]] += 1
        s["after_share"].append(f_["after_share"])
        s["branch_try_cost"].append(f_["cost"] * f_["after_share"])
    for k, s in summary.items():
        s["mean_after_share"] = round(statistics.mean(s.pop("after_share")), 3)
        s["mean_branch_try_cost"] = round(statistics.mean(s.pop("branch_try_cost")), 5)
    return {"partner_changed_steps_version_b": n_partner_changes, "forks": forks, "by_run": summary}


# ============================================================================================ main
def main() -> int:
    write_guard.install([OUT])
    os.makedirs(CHECKS_DIR, exist_ok=True)
    res: Dict[str, Any] = {"seed": SEED}

    # 1-2. task sets
    tf = task_files()
    res["task_files"] = {k: {"path": v["path"], "variable": v["var"], "count": len(v["tasks"])} for k, v in tf.items()}
    train, test, dev = tf["retail/train"]["tasks"], tf["retail/test"]["tasks"], tf["retail/dev"]["tasks"]
    res["train_index_range"] = [0, len(train) - 1]
    res["overlap_train_vs_test"] = overlap(train, test)
    res["overlap_train_vs_dev"] = overlap(train, dev)
    dup = collections.Counter((t["user_id"], t["instruction"]) for t in train)
    res["train_duplicates_within"] = sum(v - 1 for v in dup.values() if v > 1)
    print("[tasks]", json.dumps(res["task_files"]), flush=True)

    # 3. checks on every task (and the test set, for comparison), then the sample of 20
    schemas = {s["function"]["name"]: s for s in tau_copy.tools_info("retail")}
    checked = {}
    for name, tasks in (("train", train), ("test", test)):
        checked[name] = [check_task(t, load_db("retail"), schemas) for t in tasks]
        res[f"stats_{name}"] = task_set_stats(checked[name])
        print(f"[tasks] {name}: {json.dumps(res[f'stats_{name}'])[:400]}", flush=True)
    res["train_tasks_with_problems"] = [{"task": i, "problems": c["problems"]}
                                        for i, c in enumerate(checked["train"]) if c["problems"]]
    rng = random.Random(SEED)
    sample = sorted(rng.sample(range(len(train)), 20))
    res["sample_20"] = [{"task": i, "instruction": train[i]["instruction"], "actions": train[i]["actions"],
                         **{k: checked["train"][i][k] for k in ("user_id", "user_in_db", "identity", "n_actions",
                                                                "tools", "writes", "outputs", "problems",
                                                                "ids_in_instruction")},
                         "replay_failed": [r["tool"] for r in checked["train"][i]["replay"] if r["failed"]]}
                        for i in sample]

    # 4. gold scorer v2 on 5 tasks of the sample: the first one for each different first write tool, then fill up
    picks, seen = [], set()
    for i in sample:
        w = tuple(sorted(set(checked["train"][i]["writes"])))
        if w and w not in seen:
            picks.append(i)
            seen.add(w)
    picks = (picks + [i for i in sample if i not in picks])[:5]
    res["gold_v2"] = gold_check(train, picks)
    print("[gold]", json.dumps({k: v for k, v in res["gold_v2"].items() if k != "tasks"}), flush=True)

    # 5. formats
    res["formats"] = format_checks()

    # 6. cost and fork numbers
    res["cost"] = cost_numbers()
    res["forks"] = fork_numbers()
    print("[forks]", json.dumps(res["forks"]["by_run"]), flush=True)

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, ensure_ascii=False, default=str)
    print("wrote", OUT_JSON, "| refused writes:", len(write_guard.REFUSED), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
