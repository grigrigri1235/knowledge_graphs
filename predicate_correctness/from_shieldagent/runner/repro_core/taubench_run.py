"""Run τ-bench (pinned installed copy, never the reference clone) with gpt-5-nano on Azure.

τ-bench's own ToolCallingAgent and LLMUserSimulationEnv are used unchanged. Only the `litellm.completion`
function they import is replaced by `azure_completion`, which calls the existing Azure client (Chat Completions)
and returns the attributes those classes read (`choices[0].message`, `_hidden_params["response_cost"]`).
Adaptations (documented): `temperature` is dropped (the deployment rejects any value but the default); messages
are reduced to the standard chat fields; cost is computed from token usage at the configured list price.

Usage (inside ~/venvs/tau-bench):
  python -m repro_core.taubench_run --env airline --task-index 0 --out output/repro/smoke
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import threading
import time
from types import SimpleNamespace
from typing import Any, Dict, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

KEEP = {"role", "content", "tool_calls", "tool_call_id", "name"}
_stats_lock = threading.Lock()
STATS: Dict[str, Dict[str, float]] = {}


def _pricing():
    with open(os.path.join(ROOT, "repro_core", "config.json"), encoding="utf-8") as f:
        return json.load(f)["pricing"]


def _clean(m: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in m.items() if k in KEEP and v is not None}
    if out.get("role") == "assistant" and "content" not in out:
        out["content"] = None if out.get("tool_calls") else ""
    if out.get("tool_calls"):
        out["tool_calls"] = [{"id": tc["id"], "type": "function",
                              "function": {"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]}}
                             for tc in out["tool_calls"]]
    return out


def make_completion(role: str):
    """A drop-in for litellm.completion(model, custom_llm_provider, messages, tools=None, temperature=None)."""
    with contextlib.redirect_stdout(io.StringIO()):
        from utility.utils import client, deployment_name
    price = _pricing()

    def azure_completion(model=None, custom_llm_provider=None, messages=None, tools=None, temperature=None, **_):
        kw = {"model": deployment_name, "messages": [_clean(m) for m in messages]}
        if tools:
            kw["tools"] = tools
        last = None
        for attempt in range(5):
            t0 = time.time()
            try:
                r = client.chat.completions.create(**kw)
                break
            except Exception as e:  # noqa: BLE001 - transient API errors
                last = e
                time.sleep(min(60, 2 ** attempt * 2))
        else:
            raise RuntimeError(f"azure_completion failed: {last}")
        u = r.usage
        cost = (u.prompt_tokens * price["input_per_m"] + u.completion_tokens * price["output_per_m"]) / 1e6
        with _stats_lock:
            s = STATS.setdefault(role, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "cost": 0.0, "seconds": 0.0})
            s["calls"] += 1
            s["input_tokens"] += u.prompt_tokens
            s["output_tokens"] += u.completion_tokens
            s["reasoning_tokens"] += getattr(u.completion_tokens_details, "reasoning_tokens", 0) or 0
            s["cost"] += cost
            s["seconds"] += time.time() - t0
        msg = r.choices[0].message
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], _hidden_params={"response_cost": cost})

    return azure_completion


def patch_tau_bench():
    import tau_bench.agents.tool_calling_agent as tca
    import tau_bench.envs.user as user_mod
    tca.completion = make_completion("agent")
    user_mod.completion = make_completion("user")
    return tca, user_mod


def run_task(env_name: str, task_index: int, split: str = "test", max_steps: int = 30) -> Dict[str, Any]:
    tca, _ = patch_tau_bench()
    import tau_bench
    from tau_bench.envs import get_env
    env = get_env(env_name, user_strategy="llm", user_model="gpt-5-nano", user_provider="azure", task_split=split,
                  task_index=task_index)
    agent = tca.ToolCallingAgent(tools_info=env.tools_info, wiki=env.wiki, model="gpt-5-nano", provider="azure", temperature=0.0)
    t0 = time.time()
    res = agent.solve(env, task_index=task_index, max_num_steps=max_steps)
    return {"env": env_name, "task_index": task_index, "split": split, "reward": res.reward,
            "seconds": round(time.time() - t0, 1), "tau_bench_file": tau_bench.__file__,
            "usage": STATS, "total_cost": round(sum(s["cost"] for s in STATS.values()), 5),
            "messages": res.messages, "info": res.info}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", required=True)
    ap.add_argument("--task-index", type=int, default=0)
    ap.add_argument("--split", default="test")
    ap.add_argument("--out", default=os.path.join(ROOT, "output", "repro", "smoke"))
    a = ap.parse_args()
    out = run_task(a.env, a.task_index, a.split)
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, f"{a.env}_{a.split}_{a.task_index}.json")
    json.dump(out, open(path, "w"), indent=1, default=str)
    print(json.dumps({k: v for k, v in out.items() if k not in ("messages", "info")}, indent=1))
    print("written", path)


if __name__ == "__main__":
    main()
