"""Per-role model configuration (exp_core/model_profiles.json) for the post-reproduction experiments.

The reproduction code reaches the LLM through three seams; `activate()` re-points each of them at the configured role
model for the current process, without editing any existing module (repro_core/ and repro_pipeline/ are frozen):
  1. structured calls (rule building, guard): `policy_pipeline.llm` shared client/deployment, and every `LLM` made by
     `repro_core.llm.structured_llm` carries `model=<role model>`, which is part of `LLM.call`'s cache key;
  2. the planner tool loop: `repro_runtime.plan.run_tool_loop` is replaced by `run_tool_loop` below (a copy of
     `repro_core.llm.run_tool_loop` with the model as a parameter and in the cache key);
  3. τ-bench agent / user simulator: `make_completion(role)` below, a drop-in for `litellm.completion` that routes by
     role, never by the `model` argument the callers pass.
One process serves one structured role (P1 process: rulebuild; online process: guard). Caches live under
output/tgr/_llmcache, apart from the gpt-5-nano caches. Cost: list prices of the role model (model_profiles.json).
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys
import threading
import time
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
CACHE_ROOT = os.path.join(ROOT, "output", "tgr", "_llmcache")
ROLES = ("rulebuild", "guard", "agent", "user")

_state: Dict[str, Any] = {}
_base_client = None
_lock = threading.Lock()


def load_profiles() -> dict:
    with open(os.path.join(ROOT, "exp_core", "model_profiles.json"), encoding="utf-8") as f:
        return json.load(f)


def profile(name: str) -> Dict[str, dict]:
    p = load_profiles()["profiles"][name]
    missing = [r for r in ROLES if r not in p]
    if missing:
        raise ValueError(f"profile {name} lacks roles {missing}")
    return p


def price(model: str) -> dict:
    return load_profiles()["pricing"][model]


def cost(model: str, input_tokens: float, output_tokens: float) -> float:
    p = price(model)
    return input_tokens / 1e6 * p["input_per_m"] + output_tokens / 1e6 * p["output_per_m"]


def base_client():
    """The existing Azure AI Foundry client (utility/utils.py: endpoint + Managed Identity), with a request timeout
    and no hidden retries (callers retry)."""
    global _base_client
    with _lock:
        if _base_client is None:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                from utility.utils import client
            from repro_core.llm import llm_config
            _base_client = client.with_options(timeout=llm_config().get("request_timeout_s", 420), max_retries=0)
        return _base_client


def role(name: str) -> dict:
    if not _state:
        raise RuntimeError("exp_core.models.activate(profile, structured_role) was not called")
    return _state["roles"][name]


# ---------------------------------------------------------------- 1 + 2: structured calls and the planner tool loop

def activate(profile_name: str, structured_role: str) -> dict:
    """Route this process's LLM traffic to the profile's role models. structured_role: 'rulebuild' or 'guard'."""
    roles = profile(profile_name)
    model = roles[structured_role]["model"]
    _state.update(profile=profile_name, roles=roles, structured_role=structured_role, structured_model=model)
    import policy_pipeline.llm as v1
    import repro_core.llm as rc
    v1._client, v1._deployment = base_client(), model
    v1._repro_configured = True                      # repro_core._configure_client must not replace the client

    def structured_llm(raw_dir: Optional[str] = None):
        cfg = rc.llm_config()
        return v1.LLM(cache_dir=os.path.join(CACHE_ROOT, "structured"), raw_dir=raw_dir, model=model,
                      max_output_tokens=cfg["max_output_tokens"])

    rc.structured_llm = structured_llm
    for modname in ("repro_pipeline.run", "repro_runtime.calls"):
        mod = sys.modules.get(modname)
        if mod is not None:
            mod.structured_llm = structured_llm
    calls = sys.modules.get("repro_runtime.calls")
    if calls is not None:
        calls._llm = None
        p = price(model)
        calls.PRICE.update(input_per_m=p["input_per_m"], output_per_m=p["output_per_m"])
    plan = sys.modules.get("repro_runtime.plan")
    if plan is not None:
        plan.run_tool_loop = run_tool_loop
    return {"profile": profile_name, "structured_role": structured_role, "structured_model": model,
            "roles": roles}


def run_tool_loop(*, system: str, user: str, tools: List[Dict[str, Any]], handlers: Dict[str, Callable[..., Any]],
                  stage: str = "tool_loop", max_turns: int = 15, effort: Optional[str] = None,
                  cache_dir: Optional[str] = None, model: Optional[str] = None):
    """repro_core.llm.run_tool_loop with the model as a parameter (default: the active structured model) and in the
    cache key; the passed cache_dir is ignored (the gpt-5-nano cache stays untouched). Records keep the turn input."""
    from repro_core.llm import ToolLoopResult, _usage_dict, llm_config
    cfg = llm_config()
    model = model or _state["structured_model"]
    effort = effort or cfg["reasoning_effort"]
    cache_dir = os.path.join(CACHE_ROOT, "tool_loop")
    tool_defs = [{"type": "function", "name": t["name"], "description": t.get("description", ""),
                  "parameters": t["parameters"], "strict": False} for t in tools]
    items: List[Dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    transcript: List[Dict[str, Any]] = []
    usage = {"calls": 0, "cache_hits": 0, "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "api_seconds": 0.0}
    for turn in range(1, max_turns + 1):
        key = hashlib.sha256(json.dumps({"model": model, "items": items, "tools": tool_defs, "effort": effort,
                                         "max_output_tokens": cfg["max_output_tokens"]}, sort_keys=True).encode()).hexdigest()
        path = os.path.join(cache_dir, key[:2], key + ".json")
        usage["calls"] += 1
        if os.path.exists(path):
            rec = json.load(open(path))
            usage["cache_hits"] += 1
        else:
            last = None
            for attempt in range(5):
                t0 = time.time()
                try:
                    resp = base_client().responses.create(model=model, input=items, tools=tool_defs,
                                                          reasoning={"effort": effort},
                                                          max_output_tokens=cfg["max_output_tokens"])
                    break
                except Exception as e:  # noqa: BLE001 - transient API errors
                    last = e
                    time.sleep(min(60, 2 ** attempt * 2))
            else:
                raise RuntimeError(f"tool loop call failed ({stage}, {model}): {last}")
            rec = {"model": model, "stage": stage, "effort": effort, "input": items,
                   "output": [o.model_dump(mode="json", exclude_none=True) for o in resp.output],
                   "output_text": resp.output_text, "usage": _usage_dict(resp.usage),
                   "cached_tokens": getattr(getattr(resp.usage, "input_tokens_details", None), "cached_tokens", 0) or 0,
                   "seconds": time.time() - t0}
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + f".tmp{threading.get_ident()}"
            json.dump(rec, open(tmp, "w"))
            os.replace(tmp, path)
            for k in ("input_tokens", "output_tokens", "reasoning_tokens"):
                usage[k] += rec["usage"][k]
            usage["api_seconds"] += rec["seconds"]
        calls = [o for o in rec["output"] if o.get("type") == "function_call"]
        items = items + rec["output"]
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


# ---------------------------------------------------------------- 3: τ-bench agent and user simulator

_tls = threading.local()


def episode_usage() -> Dict[str, Dict[str, float]]:
    """Per-thread (= per-episode) usage of the agent and user roles; reset with reset_episode_usage()."""
    if not hasattr(_tls, "usage"):
        reset_episode_usage()
    return _tls.usage


def reset_episode_usage():
    _tls.usage = {r: {"calls": 0, "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0,
                      "cost": 0.0, "seconds": 0.0} for r in ("agent", "user")}


class _Message:
    """Chat-completions-shaped assistant message (what τ-bench and repro_online read)."""

    def __init__(self, content: Optional[str], tool_calls: Optional[List[dict]]):
        self.content, self.tool_calls, self.role = content, tool_calls, "assistant"

    def model_dump(self, **_) -> dict:
        return {"role": "assistant", "content": self.content,
                "tool_calls": json.loads(json.dumps(self.tool_calls)) if self.tool_calls else None}


def chat_to_responses_input(messages: List[dict]) -> List[dict]:
    items = []
    for m in messages:
        r = m.get("role")
        if r == "tool":
            items.append({"type": "function_call_output", "call_id": m["tool_call_id"], "output": m.get("content") or ""})
        elif r == "assistant":
            if m.get("content"):
                items.append({"role": "assistant", "content": m["content"]})
            for tc in m.get("tool_calls") or []:
                items.append({"type": "function_call", "call_id": tc["id"], "name": tc["function"]["name"],
                              "arguments": tc["function"]["arguments"]})
        else:
            items.append({"role": r, "content": m.get("content") or ""})
    return items


def chat_tools_to_responses(tools: Optional[List[dict]]) -> Optional[List[dict]]:
    if not tools:
        return None
    return [{"type": "function", "name": t["function"]["name"], "description": t["function"].get("description", ""),
             "parameters": t["function"]["parameters"], "strict": False} for t in tools]


_KEEP = {"role", "content", "tool_calls", "tool_call_id", "name"}


def _clean_chat(m: dict) -> dict:
    out = {k: v for k, v in m.items() if k in _KEEP and v is not None}
    if out.get("role") == "assistant" and "content" not in out:
        out["content"] = None if out.get("tool_calls") else ""
    if out.get("tool_calls"):
        out["tool_calls"] = [{"id": tc["id"], "type": "function", "function": {"name": tc["function"]["name"],
                              "arguments": tc["function"]["arguments"]}} for tc in out["tool_calls"]]
    return out


def make_completion(role_name: str):
    """Drop-in for litellm.completion(model, custom_llm_provider, messages, tools=None, temperature=None).
    The role's model/api/effort decide the request; `model` and `temperature` from the caller are ignored
    (neither model accepts temperature 0 on every path; see docs/tgr/p0_report.md)."""
    cfg = role(role_name)
    model, api, effort = cfg["model"], cfg.get("api", "responses"), cfg.get("effort")
    pr = price(model)

    def completion(model=None, custom_llm_provider=None, messages=None, tools=None, temperature=None, **_):
        last = None
        for attempt in range(5):
            t0 = time.time()
            try:
                if api == "responses":
                    kw = {"model": cfg["model"], "input": chat_to_responses_input(messages),
                          "max_output_tokens": 16000}
                    if tools:
                        kw["tools"] = chat_tools_to_responses(tools)
                    if effort:
                        kw["reasoning"] = {"effort": effort}
                    r = base_client().responses.create(**kw)
                    calls = [o for o in r.output if o.type == "function_call"]
                    tcs = [{"id": c.call_id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
                           for c in calls] or None
                    text = r.output_text or ("" if not tcs else None)
                    u = r.usage
                    inp, out = u.input_tokens, u.output_tokens
                    reas = getattr(u.output_tokens_details, "reasoning_tokens", 0) or 0
                    cached = getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0
                    msg = _Message(text, tcs)
                else:
                    kw = {"model": cfg["model"], "messages": [_clean_chat(m) for m in messages]}
                    if tools:
                        kw["tools"] = tools
                    if effort:
                        kw["reasoning_effort"] = effort
                    r = base_client().chat.completions.create(**kw)
                    u = r.usage
                    reas = getattr(u.completion_tokens_details, "reasoning_tokens", 0) or 0
                    inp = u.prompt_tokens
                    out = u.completion_tokens + (reas if pr.get("chat_completion_tokens_exclude_reasoning") else 0)
                    cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
                    m = r.choices[0].message
                    msg = _Message(m.content, [tc.model_dump() for tc in m.tool_calls] if m.tool_calls else None)
                break
            except Exception as e:  # noqa: BLE001 - transient API errors
                last = e
                time.sleep(min(60, 2 ** attempt * 2))
        else:
            raise RuntimeError(f"{role_name} completion failed ({cfg['model']}): {last}")
        c = cost(cfg["model"], inp, out)
        s = episode_usage()[role_name]
        s["calls"] += 1
        s["input_tokens"] += inp
        s["cached_tokens"] += cached
        s["output_tokens"] += out
        s["reasoning_tokens"] += reas
        s["cost"] += c
        s["seconds"] += time.time() - t0
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], _hidden_params={"response_cost": c})

    return completion
