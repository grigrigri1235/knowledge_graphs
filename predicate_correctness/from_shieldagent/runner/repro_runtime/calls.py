"""Metered gpt-5-nano calls for the runtime.

Structured calls go through v1's cached `LLM.call` (via repro_core.structured_llm). After each call the cache record
is read back, so every call reports its tokens and API seconds whether it was fresh or a cache hit (fresh-equivalent
accounting). A `Meter` collects the calls of one shielded step.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import List

from repro_core.llm import llm_config, structured_llm

_llm = None
_llm_lock = threading.Lock()


def shared_llm():
    global _llm
    with _llm_lock:
        if _llm is None:
            _llm = structured_llm()
        return _llm


def _price():
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "repro_core", "config.json")) as f:
        return json.load(f)["pricing"]


PRICE = _price()


def cost(input_tokens: float, output_tokens: float) -> float:
    return input_tokens / 1e6 * PRICE["input_per_m"] + output_tokens / 1e6 * PRICE["output_per_m"]


@dataclass
class Meter:
    calls: List[dict] = field(default_factory=list)

    def add(self, stage, effort, hit, usage, seconds, n=1):
        """One entry; `n` > 1 for an aggregated tool loop (n turns, `hit` = number of cached turns)."""
        self.calls.append({"stage": stage, "effort": effort, "n": n, "cache_hit": int(hit), "seconds": round(seconds, 2),
                           **{k: usage.get(k, 0) for k in ("input_tokens", "output_tokens", "reasoning_tokens")}})

    def summary(self) -> dict:
        tot = {k: sum(c.get(k, 0) for c in self.calls) for k in ("input_tokens", "output_tokens", "reasoning_tokens")}
        by = {}
        for c in self.calls:
            by[c["stage"]] = by.get(c["stage"], 0) + c["n"]
        return {"n_llm_calls": sum(c["n"] for c in self.calls), "cache_hits": sum(c["cache_hit"] for c in self.calls), **tot,
                "api_seconds": round(sum(c["seconds"] for c in self.calls), 1),
                "cost_usd": round(cost(tot["input_tokens"], tot["output_tokens"]), 6), "calls_by_stage": by}


def structured(meter: Meter, *, stage: str, system: str, user: str, schema: dict, schema_name: str, effort: str) -> dict:
    llm = shared_llm()
    params = {"model": llm.model, "effort": effort, "max_output_tokens": llm.max_output_tokens,
              "schema_name": schema_name, "schema": schema, "sample": 0}
    key = hashlib.sha256(json.dumps({"system": system, "user": user, "params": params}, sort_keys=True).encode()).hexdigest()
    path = os.path.join(llm.cache_dir, key[:2], key + ".json")
    hit = os.path.exists(path)
    t0 = time.time()
    out = llm.call(stage=stage, system=system, user=user, schema=schema, schema_name=schema_name, effort=effort)
    try:
        rec = json.load(open(path))
        meter.add(stage, effort, hit, rec["usage"], rec.get("seconds", time.time() - t0))
    except (OSError, KeyError, json.JSONDecodeError):
        meter.add(stage, effort, hit, {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}, time.time() - t0)
    return out


def tool_loop_cache_dir() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, llm_config()["cache_dir"], "tool_loop")
