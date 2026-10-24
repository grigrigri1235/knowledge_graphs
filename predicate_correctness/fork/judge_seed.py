"""Eval v2 (fork/judge_seed.py): put the source judge's answer to the fork attempt in each Stage B try's judge cache.

Why (audit A5 W1, output/eval_v2/checks/audit_a5.md): in a source run, when the agent repeats a blocked call exactly
(same history and same call, so the same judge prompt), the judge call is a cache hit: the same answer, so the same
block again. In a Stage B try the fork attempt makes no judge call (fork/run_branch.py) and the try's judge cache
starts empty. Without a seed, that repeat asks the judge again and may get through. The weak agent does this often
(nano retail: 96 of 375 blocks were exact repeats; the strong agent: 0 of 180).

seed_try(guard, state, source, branch, target, write=True) -> info. fork/run_all.py runs it inside the try's judge
cache, before run_branch (the dry run runs it with write=False, so nothing is written):
  1. The branch's own guard code runs once on the fork attempt: guard.tgr._step (no retries) on state.executed,
     state.pending (first tool call only, as run_episode), state.n_exec and a copy of state.trace. For this thread
     only, its judge LLM is a SeedLLM (fork/branch_cache.py judge_for_this_thread).
  2. SeedLLM.call makes the cache key exactly as policy_pipeline/llm.py LLM.call does: sha256 of the sorted-key JSON of
     {system, user, params: {model, effort, max_output_tokens, schema_name, schema, sample}}, with the model and
     max_output_tokens of the try's judge LLM (`target`), and the path <target.cache_dir>/<key[:2]>/<key>.json.
     It never calls an API.
  3. The guard's record with that answer must give the branch's fork decision and block message (fork.decision_a /
     feedback_a, or _b), and (frozen TGR sources) ask the judge for the saved predicates. Otherwise SeedMismatch: the
     try fails before any LLM call. Only then the record is written (temp file, then os.replace, as LLM.call), in
     LLM.call's layout: key, stage, params, system, user, output_text, parsed, response, usage, seconds, created,
     plus "seed" (where it came from).
  In the try, a later identical judge prompt (an exact repeat of the blocked call) is then a cache hit: the same answer
  and the same usage (the copied runtime reads the usage back from the file, so the hit costs what it cost in the
  source run). Any other prompt is a fresh judge call.

Where the answer comes from:
  tgr / tgr_frozen sources: the saved guard record of the fork attempt: `judge` (value and evidence of each predicate,
      in the saved order, which is the judge's own order), usage and seconds from its tgr_judge entry in `calls` (else
      from `usage`).
  tgr_tracker sources: the source run's own judge cache record of this exact prompt (read only; the run's cache folder
      from fork/rebuild_check.py _cache_dir; the key with the source run's guard model and the runner's
      max_output_tokens), copied with its usage and seconds (key and params set to the try's). Its values must equal
      the saved tracker.judge_values. If it is not there, nothing is written (info.why says so; the dry run lists it).
  Both guards send the same judge prompt at the fork (TGR + tracker asks the judge with TGR's own prompt), so both
  branches get the same seed. When the branch's guard makes no judge call at the fork (the tracker knows every value),
  nothing is written: a repeat makes no judge call either.

info (the try record's judge_seed): written, why, branch, from, key, file, decision, decision_matches,
feedback_matches, usage, seconds, judge_calls.
Never imports gold code. The runner copy is imported inside the functions.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from fork.schema import BRANCH_GUARD, ForkState
from state_tracker import paths

JUDGE_STAGE = "tgr_judge"
VALUE_WORD = {True: "true", False: "false", None: "unknown"}
WORD_VALUE = {"true": True, "false": False, "unknown": None}
DEFAULT_FEEDBACK = "BLOCKED by policy guardrail."
FROZEN_SOURCES = ("tgr", "tgr_frozen")


class SeedMismatch(RuntimeError):
    """With the source judge's answer, the branch's guard does not give the fork point's decision or block message."""


class NoSeed(Exception):
    """No source answer for this judge call (ends the seeding check; nothing is written)."""


# ------------------------------------------------------------------------------------------------ the cache key
def judge_params(model: str, max_output_tokens: int, effort: str, schema_name: str, schema: dict,
                 sample: int = 0) -> Dict[str, Any]:
    """The params of policy_pipeline/llm.py LLM.call (part of its cache key)."""
    return {"model": model, "effort": effort, "max_output_tokens": max_output_tokens,
            "schema_name": schema_name, "schema": schema, "sample": sample}


def cache_key(system: str, user: str, params: Dict[str, Any]) -> str:
    """policy_pipeline/llm.py LLM.call's cache key."""
    return hashlib.sha256(json.dumps({"system": system, "user": user, "params": params},
                                     sort_keys=True).encode()).hexdigest()


def cache_path(cache_dir: str, key: str) -> str:
    return os.path.join(cache_dir, key[:2], key + ".json")


def write_record(path: str, rec: dict) -> None:
    """As LLM.call writes a record: a temp file next to it, then os.replace."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + f".tmp{threading.get_ident()}"
    with open(tmp, "w") as f:
        json.dump(rec, f)
    os.replace(tmp, path)


# ------------------------------------------------------------------------------------------------ the answers
def saved_judge_record(saved: dict) -> Tuple[dict, dict]:
    """(record body, provenance) of a frozen TGR guard record's judge answer: parsed, output_text, usage, seconds."""
    judge = saved.get("judge") or {}
    if not judge:
        raise NoSeed("the saved guard record of the fork attempt has no judge answer")
    try:
        parsed = {"predicates": [{"name": n, "value": VALUE_WORD[v.get("value")], "evidence": v.get("evidence", "")}
                                 for n, v in judge.items()]}
    except (KeyError, TypeError, AttributeError) as e:
        raise NoSeed(f"the saved judge answer is unreadable ({type(e).__name__}: {e})")
    entries = [c for c in saved.get("calls") or [] if c.get("stage") == JUDGE_STAGE]
    u = saved.get("usage") or {}
    if len(entries) == 1:
        e = entries[0]
        usage = {k: int(e.get(k) or 0) for k in ("input_tokens", "output_tokens", "reasoning_tokens")}
        seconds, how = float(e.get("seconds") or 0.0), "guard.calls (tgr_judge)"
    elif int(u.get("n_llm_calls") or 0) == 1:
        usage = {k: int(u.get(k) or 0) for k in ("input_tokens", "output_tokens", "reasoning_tokens")}
        seconds, how = float(u.get("api_seconds") or 0.0), "guard.usage"
    else:
        usage, seconds, how = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}, 0.0, "none (0 tokens)"
    body = {"output_text": json.dumps(parsed), "parsed": parsed, "response": None, "usage": usage,
            "seconds": seconds, "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    return body, {"from": "saved guard record of the fork attempt (attempts[i].guard.judge)", "usage_from": how}


class SavedAnswer:
    """The judge's answer of a frozen TGR source (tgr / tgr_frozen): the saved guard record."""

    def __init__(self, saved: dict):
        self.saved = saved
        self.body, self.provenance = saved_judge_record(saved)

    def __call__(self, system: str, user: str, effort: str, schema_name: str, schema: dict, sample: int
                 ) -> Tuple[dict, dict]:
        return copy.deepcopy(self.body), dict(self.provenance)


class CachedAnswer:
    """The judge's answer of a tgr_tracker source: the source run's own judge cache record of this exact prompt."""

    def __init__(self, saved: dict, cache_dir: Optional[str], model: Optional[str], max_output_tokens: int):
        self.saved, self.cache_dir, self.model, self.max_output_tokens = saved, cache_dir, model, max_output_tokens

    def __call__(self, system: str, user: str, effort: str, schema_name: str, schema: dict, sample: int
                 ) -> Tuple[dict, dict]:
        if not self.cache_dir or not os.path.isdir(self.cache_dir):
            raise NoSeed(f"the source run's judge cache folder was not found ({self.cache_dir})")
        if not self.model:
            raise NoSeed("the source run's guard model is not known (source line without models.guard)")
        key = cache_key(system, user, judge_params(self.model, self.max_output_tokens, effort, schema_name, schema,
                                                   sample))
        path = cache_path(self.cache_dir, key)
        if not os.path.exists(path):
            raise NoSeed(f"the fork attempt's judge prompt is not in the source run's judge cache ({self.cache_dir})")
        try:
            with open(path, encoding="utf-8") as f:
                rec = json.load(f)
            got = {p["name"]: WORD_VALUE[p["value"]] for p in rec["parsed"]["predicates"]}
        except (OSError, KeyError, TypeError, ValueError) as e:
            raise NoSeed(f"the source run's judge cache record is unreadable ({type(e).__name__}: {e})")
        jv = ((self.saved.get("tracker") or {}).get("judge_values")) or {}
        bad = sorted(n for n, v in jv.items() if got.get(n) is not v)
        if not jv or bad:
            raise NoSeed(f"the source run's cache record does not give tracker.judge_values ({bad or 'none saved'})")
        body = {k: v for k, v in rec.items() if k not in ("key", "stage", "params", "system", "user", "seed")}
        return body, {"from": "source run's judge cache (read only)", "source_key": key,
                      "source_file": os.path.relpath(path, paths.PC_DIR)}


# ------------------------------------------------------------------------------------------------ the seeding LLM
class SeedLLM:
    """Stands in for the try's judge LLM during the seeding check (one thread): computes LLM.call's cache key with the
    try LLM's model and max_output_tokens and answers from the source; never calls an API. The records are written
    by seed_try after the checks pass."""

    def __init__(self, target: Any, answer: Callable[..., Tuple[dict, dict]]):
        self.model, self.max_output_tokens, self.cache_dir = target.model, target.max_output_tokens, target.cache_dir
        self.answer = answer
        self.seeds: List[dict] = []

    def call(self, *, stage: str, system: str, user: str, schema: dict, schema_name: str, effort: str = "low",
             sample: int = 0) -> dict:
        if stage != JUDGE_STAGE:
            raise NoSeed(f"unexpected structured call of stage {stage!r} at the fork attempt (only {JUDGE_STAGE})")
        params = judge_params(self.model, self.max_output_tokens, effort, schema_name, schema, sample)
        key = cache_key(system, user, params)
        body, provenance = self.answer(system, user, effort, schema_name, schema, sample)
        rec = {"key": key, "stage": stage, "params": params, "system": system, "user": user, **body,
               "seed": dict(provenance, note="written by fork/judge_seed.py before the try (no API call)")}
        self.seeds.append({"key": key, "path": cache_path(self.cache_dir, key), "record": rec})
        return copy.deepcopy(rec["parsed"])


# ------------------------------------------------------------------------------------------------ one try
def _branch_decision(state: ForkState, branch: str) -> Tuple[str, Optional[str]]:
    f = state.fork
    return (f.decision_a, f.feedback_a) if branch == "A" else (f.decision_b, f.feedback_b)


def answer_for(source: dict, fork: Any, cache_dir_fn: Optional[Callable[[Any], Optional[str]]] = None
               ) -> Callable[..., Tuple[dict, dict]]:
    """The answer provider of the fork's source (SavedAnswer or CachedAnswer). Raises NoSeed if there is none."""
    saved = (source.get("fork_attempt") or {}).get("guard") or {}
    if fork.source_guard in FROZEN_SOURCES:
        return SavedAnswer(saved)
    if cache_dir_fn is None:
        from fork.rebuild_check import _cache_dir as cache_dir_fn          # the run's judge cache (fix A3 W1)
    from repro_core.llm import llm_config                                   # runner copy
    model = ((source.get("source") or {}).get("models") or {}).get("guard")
    return CachedAnswer(saved, cache_dir_fn(fork), model, llm_config()["max_output_tokens"])


def seed_try(guard: Any, state: ForkState, source: dict, branch: str, target: Any, *, write: bool = True,
             cache_dir_fn: Optional[Callable[[Any], Optional[str]]] = None) -> Dict[str, Any]:
    """Seed the try's judge cache (module docstring). Returns info; raises SeedMismatch."""
    from fork import branch_cache
    fork = state.fork
    decision, feedback = _branch_decision(state, branch)
    info: Dict[str, Any] = {"written": False, "why": None, "branch": branch, "guard": BRANCH_GUARD[branch],
                            "source_guard": fork.source_guard, "from": None, "key": None, "file": None,
                            "decision": None, "decision_matches": None, "feedback_matches": None,
                            "judge_calls": 0, "usage": None, "seconds": None, "dry_run": not write}
    tgr = getattr(guard, "tgr", None)
    if tgr is None or not hasattr(tgr, "_step"):
        info["why"] = "the branch guard is not a TGR guard (a test stub): no seed"
        return info
    if target is None:
        info["why"] = "no per-try judge LLM copy in this thread (a fake judge used as it is): no seed"
        return info
    try:
        answer = answer_for(source, fork, cache_dir_fn)
    except NoSeed as e:
        info["why"] = f"no source answer: {e}"
        return info
    from method_tgr.runtime import Conversation          # runner copy
    from repro_online.guards import make_step            # runner copy
    msg = copy.deepcopy(state.pending)
    if msg.get("tool_calls"):
        msg["tool_calls"] = msg["tool_calls"][:1]
    step = make_step(copy.deepcopy(state.executed), msg, state.n_exec)
    seed_llm = SeedLLM(target, answer)
    try:
        with branch_cache.judge_for_this_thread(seed_llm):
            rec = tgr._step(Conversation(trace=copy.deepcopy(state.trace)), step)
    except NoSeed as e:
        info["why"] = f"no source answer: {e}"
        return info
    info["judge_calls"] = len(seed_llm.seeds)
    allowed = bool(rec.get("action_allowed"))
    got_fb = None if allowed else (rec.get("feedback_text") or DEFAULT_FEEDBACK)
    info["decision"] = "allow" if allowed else "block"
    info["decision_matches"] = info["decision"] == decision
    info["feedback_matches"] = got_fb == (feedback if decision == "block" else None)
    problems = []
    if not info["decision_matches"]:
        problems.append(f"the branch guard decides {info['decision']} with the source judge's answer, the fork point "
                        f"says {decision}")
    elif not info["feedback_matches"]:
        problems.append("the branch guard's block message with the source judge's answer is not the fork point's")
    if seed_llm.seeds and isinstance(answer, SavedAnswer) and \
            sorted(rec.get("judge") or {}) != sorted(answer.saved.get("judge") or {}):
        problems.append(f"the guard asked the judge for {sorted(rec.get('judge') or {})}, the saved answer has "
                        f"{sorted(answer.saved.get('judge') or {})}")
    if problems:
        raise SeedMismatch(f"{fork.fork_id} branch {branch}: " + "; ".join(problems))
    if not seed_llm.seeds:
        info["why"] = "the branch guard makes no judge call at the fork (the tracker knows every value): nothing to seed"
        return info
    s = seed_llm.seeds[0]
    info.update({"key": s["key"], "file": os.path.relpath(s["path"], paths.PC_DIR),
                 "from": s["record"]["seed"].get("from"),
                 "usage": s["record"].get("usage"), "seconds": s["record"].get("seconds")})
    if not write:
        info["why"] = "dry run: checked, not written"
        return info
    for x in seed_llm.seeds:
        if not os.path.exists(x["path"]):
            write_record(x["path"], x["record"])
    info["written"] = True
    info["why"] = "written: an exact repeat of the fork call in this try is a judge cache hit, as in the source run"
    return info
