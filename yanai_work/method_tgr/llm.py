"""Metered structured calls with a per-call output budget. The model and client are whatever the running process
activated (exp_core.models.activate re-points repro_core.llm.structured_llm); cost and tokens are recorded in a
repro_runtime.calls.Meter (cache hits report their original usage, as in the reproduction)."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import threading
import time
from typing import Optional

from repro_runtime import calls

_llms = {}
_lock = threading.Lock()


def _llm(max_output_tokens: Optional[int]):
    base = calls.shared_llm()
    if not max_output_tokens or max_output_tokens == base.max_output_tokens:
        return base
    with _lock:
        key = (id(base), max_output_tokens)
        if key not in _llms:
            _llms[key] = dataclasses.replace(base, max_output_tokens=max_output_tokens, usage={}, _lock=threading.Lock())
        return _llms[key]


def structured(meter: calls.Meter, *, stage: str, system: str, user: str, schema: dict, schema_name: str, effort: str,
               max_output_tokens: Optional[int] = None) -> dict:
    llm = _llm(max_output_tokens)
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
