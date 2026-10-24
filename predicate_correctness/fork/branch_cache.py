"""Eval v2 Part 3b (fork/branch_cache.py): a fresh, empty judge cache for every Stage B try.

Why this is needed:
  - The copied TGR code sends every judge call through one LLM object per process: repro_runtime/calls.py
    shared_llm() returns calls._llm (a policy_pipeline.llm.LLM with one cache folder). Its cache key is the prompt
    and the model only. So two tries, or the two branches, that reach the same judge prompt would share the answer
    (output/eval_v2/checks/part1.md 5.4). With several worker threads in one process, one cache folder per try cannot
    be set on that one object.

What it does:
  - PerTryLLM stands in for calls._llm. A worker thread sets its try's folder with `use(folder)`. Every judge call
    in that thread then goes to a copy of the base LLM (dataclasses.replace: same model, same max_output_tokens, same
    client and retries) whose cache_dir is that folder.
  - A judge call with no folder set raises NoTryCache, so there is never a silent shared cache.
  - Inside one try the cache works as in every earlier run: the copied runtime reads each call's usage back from its
    cache record (for the cost), and an identical judge prompt in the same try gets the same answer.
  - Before the try runs, fork/judge_seed.py puts the source judge's answer to the fork attempt in the try's folder
    (audit A5 W1): an exact repeat of the blocked fork call is then a cache hit, as in the source run. It uses
    per_try_llm() (the try's LLM copy: its folder, model, max_output_tokens) and judge_for_this_thread().

Standard library only. Never imports gold code.
"""
from __future__ import annotations

import contextlib
import dataclasses
import threading
from typing import Any, Iterator, Optional


class NoTryCache(RuntimeError):
    """A judge call outside a Stage B try (no per-try cache folder is set in this thread)."""


class PerTryLLM:
    """Stand-in for repro_runtime.calls._llm: each thread uses the LLM copy of its current try."""

    def __init__(self, base: Any):
        self.base = base
        self._tls = threading.local()

    # attributes the copied code reads (method_tgr/llm.py and repro_runtime/calls.py structured())
    @property
    def model(self) -> str:
        return self.base.model

    @property
    def max_output_tokens(self) -> int:
        return self.base.max_output_tokens

    @property
    def cache_dir(self) -> str:
        return self.current().cache_dir

    def current(self) -> Any:
        llm = getattr(self._tls, "llm", None)
        if llm is None:
            raise NoTryCache("judge call outside a Stage B try: no per-try cache folder is set in this thread")
        return llm

    def call(self, **kw) -> Any:
        return self.current().call(**kw)

    @contextlib.contextmanager
    def use(self, cache_dir: str) -> Iterator[Any]:
        """All judge calls of this thread go to an LLM whose cache folder is `cache_dir` (created on first use)."""
        if getattr(self._tls, "llm", None) is not None:
            raise RuntimeError("a per-try judge cache is already set in this thread")
        if dataclasses.is_dataclass(self.base):
            self._tls.llm = dataclasses.replace(self.base, cache_dir=cache_dir, usage={}, _lock=threading.Lock())
            self._tls.copy = True
        else:                   # a test or audit fake that is not an LLM dataclass: used as it is (its own caching)
            self._tls.llm = self.base
            self._tls.copy = False
        try:
            yield self._tls.llm
        finally:
            self._tls.llm = None
            self._tls.copy = False

    def per_try_llm(self) -> Optional[Any]:
        """This thread's per-try LLM copy (inside use(), when the base is an LLM dataclass), else None."""
        llm = getattr(self._tls, "llm", None)
        return llm if llm is not None and getattr(self._tls, "copy", False) else None

    @contextlib.contextmanager
    def swap(self, llm: Any) -> Iterator[Any]:
        """For this thread only, judge calls go to `llm` inside the block (fork/judge_seed.py SeedLLM)."""
        old, old_copy = getattr(self._tls, "llm", None), getattr(self._tls, "copy", False)
        self._tls.llm, self._tls.copy = llm, False
        try:
            yield llm
        finally:
            self._tls.llm, self._tls.copy = old, old_copy


def install(base: Any) -> PerTryLLM:
    """Put a PerTryLLM over `base` at repro_runtime.calls._llm (call it after exp_core.models.activate, which resets
    calls._llm). Returns it."""
    from repro_runtime import calls                     # runner copy (guard/runner_path.py must be set up)
    proxy = PerTryLLM(base)
    calls._llm = proxy
    return proxy


def current_per_try_llm() -> Optional[Any]:
    """The per-try LLM copy of this thread (None outside a try, or when the judge is a fake used as it is)."""
    from repro_runtime import calls
    proxy = calls._llm
    return proxy.per_try_llm() if isinstance(proxy, PerTryLLM) else None


@contextlib.contextmanager
def judge_for_this_thread(llm: Any) -> Iterator[Any]:
    """Every judge call of this thread goes to `llm` inside the block: through the per-try proxy's thread slot when
    one is installed (the real runs, many threads), else by setting repro_runtime.calls._llm for the block (only for
    single-threaded callers: the dry run and tests)."""
    from repro_runtime import calls
    proxy = calls._llm
    if isinstance(proxy, PerTryLLM):
        with proxy.swap(llm):
            yield llm
        return
    calls._llm = llm
    try:
        yield llm
    finally:
        calls._llm = proxy
