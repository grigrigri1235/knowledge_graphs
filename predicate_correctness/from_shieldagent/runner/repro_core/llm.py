"""gpt-5-nano access for the reproduction.

- `structured_llm(run_dir)`: v1's structured-output caller (policy_pipeline.llm.LLM, reused unmodified) with the
  reproduction's own cache directory and uniform reasoning effort (repro_core/config.json → "llm").
- `run_tool_loop(...)`: an Azure Responses API function-calling loop (P2 planner needs it). Each turn sends the
  accumulated input (previous output items + function_call_output items); every turn is cached on disk by a hash
  of its full input, so re-runs replay without API calls.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from policy_pipeline.llm import LLM, _get_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def llm_config() -> dict:
    with open(os.path.join(ROOT, "repro_core", "config.json"), encoding="utf-8") as f:
        return json.load(f)["llm"]


def _configure_client(cfg) -> None:
    """Give v1's shared client an explicit request timeout and no hidden retries (v1's LLM.call retries itself).
    Without it a stalled request blocks for the openai default (600 s × 3 attempts)."""
    import policy_pipeline.llm as v1
    client, _ = _get_client()
    if not getattr(v1, "_repro_configured", False):
        v1._client = client.with_options(timeout=cfg.get("request_timeout_s", 420), max_retries=0)
        v1._repro_configured = True


def structured_llm(raw_dir: Optional[str] = None) -> LLM:
    cfg = llm_config()
    _configure_client(cfg)
    return LLM(cache_dir=os.path.join(ROOT, cfg["cache_dir"]), raw_dir=raw_dir, max_output_tokens=cfg["max_output_tokens"])


@dataclass
class ToolLoopResult:
    final_text: str
    turns: int
    transcript: List[Dict[str, Any]]
    usage: Dict[str, float] = field(default_factory=dict)
    stopped: str = "final_text"   # final_text | max_turns


_tool_lock = threading.Lock()


def _usage_dict(u) -> dict:
    return {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
            "reasoning_tokens": getattr(u.output_tokens_details, "reasoning_tokens", 0) or 0}


def run_tool_loop(*, system: str, user: str, tools: List[Dict[str, Any]], handlers: Dict[str, Callable[..., Any]],
                  stage: str = "tool_loop", max_turns: int = 15, effort: Optional[str] = None,
                  cache_dir: Optional[str] = None) -> ToolLoopResult:
    """tools: [{"name", "description", "parameters" (JSON schema)}]; handlers: name -> callable(**arguments)."""
    cfg = llm_config()
    effort = effort or cfg["reasoning_effort"]
    cache_dir = cache_dir or os.path.join(ROOT, cfg["cache_dir"], "tool_loop")
    os.makedirs(cache_dir, exist_ok=True)
    tool_defs = [{"type": "function", "name": t["name"], "description": t.get("description", ""),
                  "parameters": t["parameters"], "strict": False} for t in tools]
    items: List[Dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    transcript: List[Dict[str, Any]] = []
    usage = {"calls": 0, "cache_hits": 0, "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "api_seconds": 0.0}
    for turn in range(1, max_turns + 1):
        key = hashlib.sha256(json.dumps({"items": items, "tools": tool_defs, "effort": effort,
                                         "max_output_tokens": cfg["max_output_tokens"]}, sort_keys=True).encode()).hexdigest()
        path = os.path.join(cache_dir, key[:2], key + ".json")
        usage["calls"] += 1
        if os.path.exists(path):
            rec = json.load(open(path))
            usage["cache_hits"] += 1
        else:
            client, deployment = _get_client()
            t0 = time.time()
            resp = client.responses.create(model=deployment, input=items, tools=tool_defs, reasoning={"effort": effort},
                                           max_output_tokens=cfg["max_output_tokens"])
            rec = {"output": [o.model_dump(mode="json", exclude_none=True) for o in resp.output],
                   "output_text": resp.output_text, "usage": _usage_dict(resp.usage), "seconds": time.time() - t0}
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with _tool_lock:
                tmp = path + f".tmp{threading.get_ident()}"
                json.dump(rec, open(tmp, "w"))
                os.replace(tmp, path)
            for k in ("input_tokens", "output_tokens", "reasoning_tokens"):
                usage[k] += rec["usage"][k]
            usage["api_seconds"] += rec["seconds"]
        calls = [o for o in rec["output"] if o.get("type") == "function_call"]
        items.extend(rec["output"])
        if not calls:
            transcript.append({"turn": turn, "final_text": rec["output_text"]})
            return ToolLoopResult(rec["output_text"], turn, transcript, usage)
        for c in calls:
            try:
                args = json.loads(c.get("arguments") or "{}")
                result = handlers[c["name"]](**args)
            except Exception as e:  # noqa: BLE001 - the error is returned to the model as the tool output
                result = {"error": f"{type(e).__name__}: {e}"}
            out = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
            items.append({"type": "function_call_output", "call_id": c["call_id"], "output": out})
            transcript.append({"turn": turn, "tool": c["name"], "arguments": c.get("arguments"), "output": out})
    return ToolLoopResult("", max_turns, transcript, usage, stopped="max_turns")
