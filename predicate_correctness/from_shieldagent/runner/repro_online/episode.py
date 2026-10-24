"""One online τ-bench episode with a guard (p2_design §6, spec P2-6).

Same loop as tau_bench.agents.tool_calling_agent.ToolCallingAgent.solve, plus the guard:
  - a blocked tool call is not executed; its tool response (same tool_call_id) is the feedback text;
  - a blocked respond message is not sent to the user; the agent receives the feedback as a system note after its
    blocked message and produces a new turn (adaptation: τ-bench has no channel for a note to the agent);
  - after `cap` consecutive blocks at the same step, the next attempt is executed even if blocked (`cap_override`;
    still shielded for the log, and recorded as taken in the trace store);
  - `max_num_steps` counts executed actions (env.step calls), as in τ-bench; blocked attempts never reach the env.
Two message lists are kept: `messages` (what the agent sees: everything, incl. blocked attempts and feedback) and
`executed` (what happened: the shield's history, P2-6).
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List

_tls = threading.local()


def user_timer() -> dict:
    if not hasattr(_tls, "user"):
        _tls.user = {"seconds": 0.0, "calls": 0}
    return _tls.user


def timed_user_completion(inner):
    def completion(*args, **kw):
        t0 = time.time()
        try:
            return inner(*args, **kw)
        finally:
            u = user_timer()
            u["seconds"] += time.time() - t0
            u["calls"] += 1
    return completion


def _slim(rec: dict) -> dict:
    """Guard record without the bulky planner transcript (kept: everything needed for audits and metrics)."""
    if rec is None:
        return None
    out = dict(rec)
    if out.get("planner"):
        out["planner"] = {k: v for k, v in out["planner"].items() if k != "transcript"}
    return out


def run_episode(env, agent_completion, tools_info, wiki: str, guard, task_index: int, max_num_steps: int = 30,
                cap: int = 3) -> Dict[str, Any]:
    from tau_bench.agents.tool_calling_agent import message_to_action
    from tau_bench.types import RESPOND_ACTION_NAME
    _tls.user = {"seconds": 0.0, "calls": 0}
    t_start = time.time()
    reset = env.reset(task_index=task_index)
    info = reset.info.model_dump()
    messages: List[Dict[str, Any]] = [{"role": "system", "content": wiki}, {"role": "user", "content": reset.observation}]
    executed: List[Dict[str, Any]] = list(messages)
    state = guard.new_episode()
    attempts, reward, done = [], 0.0, False
    agent = {"calls": 0, "cost": 0.0, "seconds": 0.0}
    gcost = {"calls": 0, "cost": 0.0, "seconds": 0.0, "llm_calls": 0}
    n_exec, consecutive = 0, 0
    while n_exec < max_num_steps:
        t0 = time.time()
        res = agent_completion(messages=messages, model="gpt-5-nano", custom_llm_provider="azure", tools=tools_info,
                               temperature=0.0)
        agent["seconds"] += time.time() - t0
        agent["calls"] += 1
        agent["cost"] += res._hidden_params.get("response_cost") or 0.0
        msg = res.choices[0].message.model_dump()
        action = message_to_action(msg)
        if action.name != RESPOND_ACTION_NAME:
            msg["tool_calls"] = msg["tool_calls"][:1]
        rec = guard.check(state, executed, msg, n_exec)
        if rec is not None:
            gcost["calls"] += 1
            gcost["cost"] += rec["usage"]["cost_usd"]
            gcost["seconds"] += rec["seconds"]
            gcost["llm_calls"] += rec["usage"]["n_llm_calls"]
        blocked = rec is not None and not rec["action_allowed"]
        override = blocked and consecutive >= cap
        att = {"exec_step": n_exec, "attempt": consecutive + 1, "action": action.name, "kwargs": action.kwargs,
               "agent_text": msg.get("content") or "", "blocked": blocked and not override, "cap_override": override,
               "executed_prefix_len": len(executed), "guard": _slim(rec)}
        if blocked and not override:
            consecutive += 1
            fb = rec.get("feedback_text") or "BLOCKED by policy guardrail."
            att["feedback"] = fb
            attempts.append(att)
            if action.name != RESPOND_ACTION_NAME:
                tc = msg["tool_calls"][0]
                messages += [msg, {"role": "tool", "tool_call_id": tc["id"], "name": tc["function"]["name"], "content": fb}]
            else:
                messages += [msg, {"role": "system", "content": fb}]
            continue
        if override:
            guard.commit(state, rec)
        consecutive = 0
        env_response = env.step(action)
        reward = env_response.reward
        info = {**info, **env_response.info.model_dump()}
        att["observation"] = env_response.observation
        attempts.append(att)
        if action.name != RESPOND_ACTION_NAME:
            tc = msg["tool_calls"][0]
            new = [msg, {"role": "tool", "tool_call_id": tc["id"], "name": tc["function"]["name"], "content": env_response.observation}]
        else:
            new = [msg, {"role": "user", "content": env_response.observation}]
        messages += new
        executed += new
        n_exec += 1
        if env_response.done:
            done = True
            break
    user_cost = env.user.get_total_cost() if hasattr(env.user, "get_total_cost") else 0.0
    return {"task_index": task_index, "reward": reward, "done": done, "n_exec_steps": n_exec,
            "n_blocks": sum(a["blocked"] for a in attempts), "n_cap_overrides": sum(a["cap_override"] for a in attempts),
            "seconds": round(time.time() - t_start, 1),
            "cost": {"agent": agent["cost"], "user": user_cost, "guard": gcost["cost"]},
            "latency": {"agent": round(agent["seconds"], 1), "user": round(user_timer()["seconds"], 1), "guard": round(gcost["seconds"], 1)},
            "calls": {"agent": agent["calls"], "user": user_timer()["calls"], "guard_checks": gcost["calls"], "guard_llm": gcost["llm_calls"]},
            "attempts": attempts, "messages": messages, "executed": executed,
            "reward_info": json.loads(json.dumps(info.get("reward_info"), default=str)) if info.get("reward_info") else None}
