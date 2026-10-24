"""gpt-5-nano calls through the existing Azure client, with structured output, disk cache and usage accounting.

Deployment facts (probed 2026-10-14 against the Azure `gpt-5-nano` deployment, Responses API):
  - supported: `reasoning={"effort": minimal|low|medium|high}`, `max_output_tokens`,
    `text={"format": {"type": "json_schema", "strict": true, ...}}` (structured outputs);
  - rejected: `temperature` (400 "not supported with this model"), `seed` (not a Responses parameter).
  Sampling is therefore not controllable; reproducibility comes from the cache, and k-sample votes use
  distinct cache keys (sample index is part of the key).
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CACHE = os.path.join(ROOT, "output", "auto_aspm", "_cache")

_client = None
_deployment = None
_client_lock = threading.Lock()


def _get_client():
    """The existing Azure OpenAI client (utility/utils.py: Managed Identity, gpt-5-nano deployment)."""
    global _client, _deployment
    with _client_lock:
        if _client is None:
            import sys
            if ROOT not in sys.path:
                sys.path.insert(0, ROOT)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                from utility.utils import client, deployment_name
            _client, _deployment = client, deployment_name
    return _client, _deployment


@dataclass
class StageUsage:
    calls: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    api_seconds: float = 0.0
    errors: int = 0


@dataclass
class LLM:
    """Thread-safe structured-output caller. One instance per pipeline run."""
    cache_dir: str = DEFAULT_CACHE
    raw_dir: Optional[str] = None            # per-run copy of raw responses
    model: str = "gpt-5-nano"
    max_output_tokens: int = 16000
    max_retries: int = 5
    usage: dict = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self):
        os.makedirs(self.cache_dir, exist_ok=True)
        if self.raw_dir:
            os.makedirs(self.raw_dir, exist_ok=True)

    def _stage(self, stage) -> StageUsage:
        with self._lock:
            return self.usage.setdefault(stage, StageUsage())

    def call(self, *, stage: str, system: str, user: str, schema: dict, schema_name: str,
             effort: str = "low", sample: int = 0) -> dict:
        """Return the parsed JSON object. `sample` distinguishes k-sample votes in the cache key."""
        params = {"model": self.model, "effort": effort, "max_output_tokens": self.max_output_tokens,
                  "schema_name": schema_name, "schema": schema, "sample": sample}
        key = hashlib.sha256(json.dumps({"system": system, "user": user, "params": params}, sort_keys=True).encode()).hexdigest()
        path = os.path.join(self.cache_dir, key[:2], key + ".json")
        st = self._stage(stage)
        if os.path.exists(path):
            rec = json.load(open(path))
            with self._lock:
                st.calls += 1
                st.cache_hits += 1
            self._copy_raw(key, rec)
            return rec["parsed"]
        client, deployment = _get_client()
        last_err = None
        for attempt in range(self.max_retries):
            t0 = time.time()
            try:
                resp = client.responses.create(
                    model=deployment,
                    input=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    reasoning={"effort": effort},
                    max_output_tokens=self.max_output_tokens,
                    text={"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}},
                )
                dt = time.time() - t0
                text = resp.output_text
                parsed = json.loads(text)
                u = resp.usage
                rec = {"key": key, "stage": stage, "params": params, "system": system, "user": user,
                       "output_text": text, "parsed": parsed, "response": resp.model_dump(mode="json"),
                       "usage": {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                                 "reasoning_tokens": getattr(u.output_tokens_details, "reasoning_tokens", 0) or 0},
                       "seconds": dt, "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
                os.makedirs(os.path.dirname(path), exist_ok=True)
                tmp = path + f".tmp{threading.get_ident()}"
                json.dump(rec, open(tmp, "w"))
                os.replace(tmp, path)
                with self._lock:
                    st.calls += 1
                    st.input_tokens += rec["usage"]["input_tokens"]
                    st.output_tokens += rec["usage"]["output_tokens"]
                    st.reasoning_tokens += rec["usage"]["reasoning_tokens"]
                    st.api_seconds += dt
                self._copy_raw(key, rec)
                return parsed
            except Exception as e:  # transient API errors, truncated / invalid JSON
                last_err = e
                with self._lock:
                    st.errors += 1
                time.sleep(min(60, 2 ** attempt * 2))
        raise RuntimeError(f"LLM call failed after {self.max_retries} attempts ({stage}): {last_err}")

    def _copy_raw(self, key, rec):
        if self.raw_dir:
            p = os.path.join(self.raw_dir, key + ".json")
            if not os.path.exists(p):
                json.dump({k: rec[k] for k in ("stage", "params", "output_text", "usage")}, open(p, "w"))

    def usage_report(self) -> dict:
        return {s: vars(u) for s, u in sorted(self.usage.items())}
