"""R2 (eval v2, Part 4 reference): an independent rebuild of the state at a sample of fork-like attempts. No LLM call.

Written by R2 without reading fork/rebuild.py, fork/find_points.py, fork/run_*.py or their outputs. Only the names of
fork/schema.py (ForkState) are matched. Formats: output/eval_v2/checks/part1.md 5.1-5.7.

For each sample point (run, domain, task_index, trial, attempt_index) it computes, with its own code:
  - database: fresh data of the venv's τ-bench env, every executed tool call replayed in order (arguments from the
    message, never attempts[i].kwargs); sha256 of the canonical JSON and τ-bench's own data hash; every replayed
    output must equal the saved one;
  - agent messages before the attempt, executed history the guard sees (rebuilt from `messages` by dropping blocked
    attempts, and checked against the saved `executed`), env actions, the pending message;
  - the user-simulator list (part1.md 5.3); the real LLMUserSimulationEnv.step with a fake completion must give the next
    saved user reply, and the fake must see the next rebuilt list;
  - guard state: trace (trace_position of the executed attempts before), blocks in a row, executed steps, recomputed
    independently and checked against the attempt's fields; the trace positions are recomputed from the rule set;
  - decisions: the saved decision again from the rebuilt trace (copied mln.decide); then the real frozen TGR guard and
    the real TGR + tracker guard at the attempt, on the rebuilt state, with the replay fake judge: decision A, decision
    B, their block messages, the kind;
  - end to end: the copied loop continued from the rebuilt state with the source run's guard and the replay fakes
    must give the saved conversation exactly (messages, executed, attempts, reward, reward_info).
Hashes: sha256 of json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":")) in UTF-8.

Run from predicate_correctness/ (venv; network blocked; writes only under output/):
  LITELLM_LOCAL_MODEL_COST_MAP=True PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B \
      -m tests.audit_v2_ref_rebuild > output/logs/v2_r2_ref_rebuild.log 2>&1
  (--candidates-only: list the candidates and the sample, no rebuild; --all: also every candidate)
Writes output/eval_v2/checks/ref/ref_rebuild.jsonl (the sample), ref_rebuild_all.jsonl (--all: every candidate, so
every fork point of sources 1-2), ref_rebuild_candidates.json, ref_rebuild.md (reads ref_rebuild_fakes_selftest.json).
"""
from __future__ import annotations

import argparse
import collections
import copy
import json
import os
import random
import sys
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from tests import audit_v2_replay_fakes as RF                      # noqa: E402

REF_DIR = RF.REF_DIR
OUT_JSONL = os.path.join(REF_DIR, "ref_rebuild.jsonl")
OUT_ALL = os.path.join(REF_DIR, "ref_rebuild_all.jsonl")
OUT_CAND = os.path.join(REF_DIR, "ref_rebuild_candidates.json")
OUT_MD = os.path.join(REF_DIR, "ref_rebuild.md")
P8 = os.path.join(PC_DIR, "output", "p8_changes.jsonl")
SPLITS = os.path.join(PC_DIR, "from_shieldagent", "splits", "splits.json")
SEED = 20261022
TARGET = 32
MAX_STEPS, CAP = 30, 3
LATE_STEP = 18                 # "late": exec_step >= 18, or the judge's 24,000-character view is already cut
DOMAINS = ("airline", "retail")
KINDS = ("block removed", "block added")

RUNS = {   # run -> (source, agent, profile, episodes path pattern, judge cache)
    "luna_train_v5": ("saved_tgr", "luna", "luna-dev", "from_shieldagent/runs/luna_train_v5/{d}/tgr/episodes.jsonl"),
    "nano_train": ("saved_tgr", "nano", "nano-agent-luna", "from_shieldagent/runs/nano_train/{d}/tgr/episodes.jsonl"),
    "p10_luna_train": ("online_tracker", "luna", "luna-dev",
                       "output/online/p10_luna_train/{d}/tgr_tracker/episodes.jsonl"),
    "p10_nano_train": ("online_tracker", "nano", "nano-agent-luna",
                       "output/online/p10_nano_train/{d}/tgr_tracker/episodes.jsonl"),
    "p10_luna_val": ("online_tracker", "luna", "luna-dev", "output/online/p10_luna_val/{d}/tgr_tracker/episodes.jsonl"),
}


# ----------------------------------------------------------------------------------------------- runner pieces
class Runner:
    """The copied runner's decision code and rule sets (imported through guard/runner_path.py)."""

    def __init__(self):
        from guard import runner_path
        runner_path.setup()
        from method_tgr.rules import RESPOND, to_aspm
        from method_tgr.runtime import Conversation, TGRConfig, load_rule_set
        from repro_runtime import mln
        self.mln, self.Conversation, self.RESPOND = mln, Conversation, RESPOND
        self.cfg = TGRConfig()
        self.aspm = {d: to_aspm(load_rule_set(os.path.join(RF.RULES_DIR, d, "rule_set.json"))) for d in DOMAINS}
        self._guards: Dict[Tuple[str, str], Any] = {}
        self._env: Dict[str, Any] = {}

    def names(self, domain: str, circuit: List[str]) -> List[str]:
        a = self.aspm[domain]
        return sorted({n for r in circuit for n in a.rules[r].atoms} - a.action_predicates)

    def matched(self, domain: str, action: str) -> List[str]:
        return [action] if action in self.aspm[domain].action_predicates else []

    def position(self, domain: str, action: str, values: Dict[str, Optional[bool]], circuit: List[str]) -> dict:
        """A trace position as TGR._step builds it: every action predicate, then the predicate values used."""
        a = self.aspm[domain]
        m = self.matched(domain, action)
        cur = {p: (p in m) for p in a.action_predicates}
        cur.update({n: values.get(n) for n in self.names(domain, circuit)})
        return cur

    def decide(self, domain: str, action: str, circuit: List[str], values: Dict[str, Optional[bool]],
               past: List[dict]) -> dict:
        """TGR's decision (method_tgr/runtime.py TGR._step) for these predicate values and this past trace."""
        m = self.matched(domain, action)
        if not circuit:
            return {"allowed": True, "margin": None}
        cur = self.position(domain, action, values, circuit)
        per = [self.mln.decide(self.aspm[domain], circuit, x, cur, past, self.cfg.epsilon, self.cfg.gibbs_threshold)
               for x in m]
        return {"allowed": all(d["allowed"] for d in per), "margin": min(d["margin"] for d in per)}

    def env(self, domain: str, task_split: str, task_index: int):
        """A τ-bench env from the venv with the human user (no LLM call at build)."""
        from tau_bench.envs import get_env
        return get_env(domain, user_strategy="human", user_model="none", task_split=task_split, task_index=task_index)

    def tools(self, domain: str):
        if domain not in self._env:
            self._env[domain] = self.env(domain, "test", 0)
        return self._env[domain].tools_info, self._env[domain].wiki

    def guard(self, domain: str, which: str):
        """which: 'tgr' (frozen TGR, repro_online.guards.TGRGuard on the frozen rule set) or 'tgr_tracker'."""
        if (domain, which) not in self._guards:
            tools_info, _ = self.tools(domain)
            if which == "tgr":
                from repro_online.guards import TGRGuard
                g = TGRGuard("tgr", os.path.join(RF.RULES_DIR, domain), tools_info)
            else:
                from guard.tgr_tracker import TGRTrackerGuard
                g = TGRTrackerGuard(domain, tools_info)
            self._guards[(domain, which)] = g
        return self._guards[(domain, which)]


def used_values(rec: dict) -> Dict[str, Optional[bool]]:
    return {n: v.get("value") for n, v in (rec.get("judge") or {}).items()}


def render_len(executed_prefix: List[dict]) -> int:
    from repro_core.taubench_steps import render_history
    return len(render_history(executed_prefix))


# ----------------------------------------------------------------------------------------------- candidates
def load_runs() -> Dict[Tuple[str, str], Dict[Tuple[int, int], Tuple[int, dict]]]:
    out = {}
    for run, (_, _, _, pat) in RUNS.items():
        for d in DOMAINS:
            out[(run, d)] = RF.good_episodes(pat.format(d=d))
    return out


def _cand(run: str, d: str, line: int, ep: dict, i: int, kind: str, saved_allowed: bool, other_allowed: bool,
          changed: List[str], extra: dict) -> dict:
    att = ep["attempts"][i]
    src, agent, profile, pat = RUNS[run]
    return {"run": run, "source": src, "agent": agent, "profile": profile, "domain": d,
            "episodes_path": pat.format(d=d), "line_no": line, "task_split": "test",
            "task_index": ep["task_index"], "trial": ep["trial"], "attempt_index": i,
            "exec_step": att["exec_step"], "attempt": att["attempt"], "action": att["action"], "kind": kind,
            "saved_allowed": saved_allowed, "other_allowed": other_allowed, "changed_predicates": changed,
            "cap_override": att["cap_override"], "blocks_before": att["attempt"] - 1,
            "after_cap": any(a["cap_override"] for a in ep["attempts"][:i]),
            "n_attempts": len(ep["attempts"]), "n_exec_steps": ep["n_exec_steps"], **extra}


def candidates(R: Runner, runs) -> List[dict]:
    out = []
    # source 1: the partner's frozen TGR runs, from output/p8_changes.jsonl (version b = the guard's)
    with open(P8, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f]
    for row in rows:
        b = row.get("b") or {}
        if b.get("change") not in KINDS:
            continue
        got = runs[(row["run"], row["domain"])].get((row["task"], row["trial"]))
        if got is None:
            continue
        line, ep = got
        idx = [i for i, a in enumerate(ep["attempts"]) if a["exec_step"] == row["exec_step"]
               and a["attempt"] == row["attempt"]]
        if len(idx) != 1 or ep["attempts"][idx[0]]["action"] != row["action"]:
            raise RuntimeError(f"p8 row {row['step_id']} does not match its episode")
        out.append(_cand(row["run"], row["domain"], line, ep, idx[0], b["change"], row["saved_allowed"],
                         b["allowed"], b.get("changed_values") or [], {"p8_step_id": row["step_id"]}))
    # source 2: our TGR + tracker runs; decision with tracker.judge_values on the same past trace
    for run in RUNS:
        if RUNS[run][0] != "online_tracker":
            continue
        for d in DOMAINS:
            for (t, k), (line, ep) in sorted(runs[(run, d)].items()):
                past = []
                for i, att in enumerate(ep["attempts"]):
                    rec = att.get("guard") or {}
                    tr = rec.get("tracker") or {}
                    if tr.get("applied") and tr.get("changed") and tr.get("judge_values") is not None \
                            and rec.get("circuit"):
                        jd = R.decide(d, att["action"], rec["circuit"], tr["judge_values"], past)
                        if jd["allowed"] != rec["action_allowed"]:
                            kind = "block removed" if not jd["allowed"] else "block added"
                            out.append(_cand(run, d, line, ep, i, kind, rec["action_allowed"], jd["allowed"],
                                             list(tr["changed"]), {}))
                    if not att["blocked"]:
                        past.append(rec.get("trace_position"))
    # first change in each conversation (the fork point), and "late"
    first = {}
    for c in out:
        key = (c["run"], c["domain"], c["task_index"], c["trial"])
        first[key] = min(first.get(key, 10 ** 9), c["attempt_index"])
    for c in out:
        c["first_change_in_conversation"] = first[(c["run"], c["domain"], c["task_index"], c["trial"])] == \
            c["attempt_index"]
        ep = runs[(c["run"], c["domain"])][(c["task_index"], c["trial"])][1]
        att = ep["attempts"][c["attempt_index"]]
        c["history_chars"] = render_len(ep["executed"][:att["executed_prefix_len"]])
        c["late"] = c["exec_step"] >= LATE_STEP or c["history_chars"] > R.cfg.history_chars
    return out


def select(cands: List[dict]) -> List[dict]:
    """A fixed-seed sample spread over runs, domains, kinds, with the asked special cases."""
    rng = random.Random(SEED)
    pool = sorted(cands, key=lambda c: (c["run"], c["domain"], c["task_index"], c["trial"], c["attempt_index"]))
    rng.shuffle(pool)
    chosen: List[dict] = []
    ids = set()

    def key(c):
        return (c["run"], c["domain"], c["task_index"], c["trial"], c["attempt_index"])

    def take(c, why):
        if key(c) not in ids:
            ids.add(key(c))
            chosen.append(dict(c, selected_for=why))
            return True
        return False

    convs = collections.Counter()

    def best(cs):     # prefer fork points and conversations not chosen yet
        return sorted(cs, key=lambda c: (not c["first_change_in_conversation"],
                                         convs[(c["run"], c["domain"], c["task_index"], c["trial"])]))

    # 1. every (run, domain, kind) stratum once
    for run in RUNS:
        for d in DOMAINS:
            for kd in KINDS:
                cs = best([c for c in pool if (c["run"], c["domain"], c["kind"]) == (run, d, kd)])
                if cs and take(cs[0], "stratum"):
                    convs[key(cs[0])[:4]] += 1
    # 2. the special cases (at least 4 / 3 / 3 asked; take 5 / 4 / 4)
    for flag, n, why in (("blocks_before", 5, "blocks in a row before"), ("after_cap", 4, "after a cap override"),
                         ("late", 4, "late in a long conversation"), ("cap_override", 2, "the attempt is a cap override")):
        have = sum(1 for c in chosen if c[flag])
        for run_cycle in range(3):
            for run in RUNS:
                if have >= n:
                    break
                cs = best([c for c in pool if c[flag] and c["run"] == run and key(c) not in ids])
                if cs and take(cs[0], why):
                    convs[key(cs[0])[:4]] += 1
                    have += 1
    # 3. fill up to TARGET, round robin over runs
    while len(chosen) < TARGET:
        added = False
        for run in RUNS:
            if len(chosen) >= TARGET:
                break
            cs = best([c for c in pool if c["run"] == run and key(c) not in ids])
            if cs and take(cs[0], "fill"):
                convs[key(cs[0])[:4]] += 1
                added = True
        if not added:
            break
    return sorted(chosen, key=lambda c: (list(RUNS).index(c["run"]), c["domain"], c["task_index"], c["trial"],
                                         c["attempt_index"]))


# ----------------------------------------------------------------------------------------------- the rebuild
def replay_db(env, executed_prefix: List[dict], attempts_exec: List[Tuple[int, dict]]) -> dict:
    """Fresh data, every executed tool call replayed (as Env.step does); outputs compared with the saved ones."""
    from tau_bench.agents.tool_calling_agent import message_to_action
    from tau_bench.envs.base import consistent_hash, to_hashable
    data = env.data_load_func()
    n_calls, mism, env_actions = 0, [], []
    for q, (j, att) in enumerate(attempts_exec):
        m, ans = executed_prefix[2 + 2 * q], executed_prefix[3 + 2 * q]
        act = message_to_action(m)
        env_actions.append({"name": act.name, "kwargs": act.kwargs})
        if act.name == "respond":
            continue
        n_calls += 1
        if act.name in env.tools_map:
            try:
                out = env.tools_map[act.name].invoke(data=data, **json.loads(m["tool_calls"][0]["function"]["arguments"]))
            except Exception as e:  # noqa: BLE001 - as tau_bench.envs.base.Env.step
                out = f"Error: {e}"
        else:
            out = f"Unknown action {act.name}"
        if out != ans.get("content") or out != att.get("observation"):
            mism.append({"attempt_index": j, "action": act.name, "replayed": RF._short(out, 200),
                         "saved": RF._short(ans.get("content"), 200)})
    env_actions = RF.jnorm(env_actions)
    return {"data": data, "sha256": RF.sha(data), "tau_hash": consistent_hash(to_hashable(data)),
            "n_tool_calls": n_calls, "mismatches": mism, "env_actions": env_actions}


def continue_loop(env, agent_completion, tools_info, guard, state, messages, executed, attempts_before, n_exec,
                  consecutive, max_num_steps=MAX_STEPS, cap=CAP) -> dict:
    """The while-loop of from_shieldagent/runner/repro_online/episode.py::run_episode, started at a rebuilt state
    (reference only: copied line by line, timing and cost counters left out)."""
    from tau_bench.agents.tool_calling_agent import message_to_action
    from tau_bench.types import RESPOND_ACTION_NAME
    from repro_online.episode import _slim
    messages, executed, attempts = list(messages), list(executed), list(attempts_before)
    reward, done, info = 0.0, False, {}
    while n_exec < max_num_steps:
        res = agent_completion(messages=messages, model="gpt-5-nano", custom_llm_provider="azure", tools=tools_info,
                               temperature=0.0)
        msg = res.choices[0].message.model_dump()
        action = message_to_action(msg)
        if action.name != RESPOND_ACTION_NAME:
            msg["tool_calls"] = msg["tool_calls"][:1]
        rec = guard.check(state, executed, msg, n_exec)
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
    return {"reward": reward, "done": done, "n_exec_steps": n_exec,
            "n_blocks": sum(a["blocked"] for a in attempts), "n_cap_overrides": sum(a["cap_override"] for a in attempts),
            "attempts": attempts, "messages": messages, "executed": executed,
            "reward_info": json.loads(json.dumps(info.get("reward_info"), default=str)) if info.get("reward_info") else None}


def guard_at(R: Runner, fakes: RF.ReplayFakes, domain: str, which: str, trace, executed_prefix, pending, n_exec):
    g = R.guard(domain, which)
    st = R.Conversation(trace=copy.deepcopy(trace))
    with fakes.installed(user=False):
        rec = g.check(st, copy.deepcopy(executed_prefix), copy.deepcopy(pending), n_exec)
    return RF.jnorm(rec)


def rebuild_point(R: Runner, c: dict, ep: dict, splits: dict) -> dict:
    t0 = time.time()
    d, i = c["domain"], c["attempt_index"]
    msgs, exe, atts = ep["messages"], ep["executed"], ep["attempts"]
    att = atts[i]
    rec_i = att.get("guard") or {}
    checks: Dict[str, Any] = {}
    out: Dict[str, Any] = {k: c[k] for k in ("run", "domain", "task_index", "trial", "attempt_index", "source", "agent",
                                              "profile", "episodes_path", "line_no", "task_split", "kind",
                                              "exec_step", "attempt", "action", "selected_for", "blocks_before",
                                              "after_cap", "late", "history_chars", "first_change_in_conversation",
                                              "changed_predicates", "cap_override", "n_attempts", "n_exec_steps")}
    out["source_guard"] = ep["guard"]
    out["split_label"] = splits[d]["split"].get(str(c["task_index"]))
    checks["not_a_test_group_task"] = out["split_label"] in ("train", "val")

    # --- index rules and the executed history, from `messages` alone
    checks["messages_len_rule"] = len(msgs) == 2 + 2 * len(atts)
    exec_j = [j for j in range(i) if not atts[j]["blocked"]]
    n_exec = len(exec_j)
    consecutive = 0
    for j in range(i - 1, -1, -1):
        if atts[j]["blocked"] and atts[j]["exec_step"] == att["exec_step"]:
            consecutive += 1
        else:
            break
    pair_ok = True
    for j in range(i):
        m, ans, a = msgs[2 + 2 * j], msgs[3 + 2 * j], atts[j]
        name = "respond" if RF.is_respond(m) else m["tool_calls"][0]["function"]["name"]
        if name != a["action"]:
            pair_ok = False
        if a["blocked"]:
            if ans.get("content") != a.get("feedback") or ans.get("role") != ("system" if name == "respond" else "tool"):
                pair_ok = False
        elif ans.get("content") != a.get("observation") or ans.get("role") != ("user" if name == "respond" else "tool"):
            pair_ok = False
    checks["message_pairs_match_attempts"] = pair_ok
    executed_rebuilt = msgs[:2] + [x for j in exec_j for x in msgs[2 + 2 * j:4 + 2 * j]]
    executed_saved = exe[:att["executed_prefix_len"]]
    checks["executed_from_messages_equals_saved"] = executed_rebuilt == executed_saved
    checks["exec_step_equals_count"] = att["exec_step"] == n_exec
    checks["executed_prefix_len_rule"] = att["executed_prefix_len"] == 2 + 2 * n_exec
    checks["attempt_equals_blocks_in_a_row_plus_1"] = att["attempt"] == consecutive + 1
    checks["blocks_in_a_row_at_most_cap"] = consecutive <= CAP
    checks["cap_override_rule"] = att["cap_override"] == (not rec_i.get("action_allowed", True) and consecutive >= CAP)
    agent_messages = msgs[:2 + 2 * i]
    pending = msgs[2 + 2 * i]
    out["agent_messages"] = {"count": len(agent_messages), "sha256": RF.sha(agent_messages)}
    out["executed"] = {"count": len(executed_rebuilt), "sha256": RF.sha(executed_rebuilt)}
    out["pending"] = {"message": pending, "sha256": RF.sha(pending)}
    if not RF.is_respond(pending):
        args = json.loads(pending["tool_calls"][0]["function"]["arguments"])
        out["pending"]["arguments"] = args
        checks["pending_action_equals_attempt"] = pending["tool_calls"][0]["function"]["name"] == att["action"]
        out["pending"]["kwargs_equal_message_arguments"] = args == att["kwargs"]
    else:
        checks["pending_action_equals_attempt"] = att["action"] == "respond"
        out["pending"]["kwargs_equal_message_arguments"] = {"content": pending.get("content")} == att["kwargs"]

    # --- the database
    env = R.env(d, "test", c["task_index"])
    db = replay_db(env, executed_rebuilt, [(j, atts[j]) for j in exec_j])
    out["db"] = {"sha256": db["sha256"], "tau_hash": db["tau_hash"], "n_tool_calls_replayed": db["n_tool_calls"],
                 "n_outputs_equal": db["n_tool_calls"] - len(db["mismatches"]), "mismatches": db["mismatches"]}
    checks["replayed_outputs_equal_saved"] = not db["mismatches"]
    out["env_actions"] = {"count": len(db["env_actions"]), "sha256": RF.sha(db["env_actions"])}
    checks["env_actions_count"] = len(db["env_actions"]) == n_exec

    # --- the user simulator
    instr = RF.task_instruction(d, "test", c["task_index"])
    users = RF.user_messages_from_executed(executed_rebuilt, instr)
    n_resp = sum(1 for j in exec_j if atts[j]["action"] == "respond")
    checks["user_list_len"] = len(users) == 3 + 2 * n_resp
    loose = [{k: v for k, v in m.items() if v is not None} for m in users]
    out["user_messages"] = {"count": len(users), "sha256": RF.sha(users), "sha256_without_none_keys": RF.sha(loose),
                            "instruction_sha256": RF.sha(instr), "messages": users}
    j_next = next((j for j in range(i, len(atts)) if atts[j]["action"] == "respond" and not atts[j]["blocked"]), None)
    fakes = RF.ReplayFakes(ep, domain=d, task_split="test", instruction=instr,
                           judge_cache_dir=RF.judge_cache_for(c["run"]))
    out["judge_fake"] = {"checks_saved": sum(len(v) for v in fakes.judge_map.values()),
                         "answers_from_cache": fakes.evidence_from_cache, "problems": fakes.judge_problems}
    checks["judge_fake_map_clean"] = not fakes.judge_problems
    if j_next is None:
        out["user_step_check"] = {"next_reply": None, "note": "no executed reply to the user at or after the attempt"}
    else:
        u = RF.new_llm_user(messages=users)
        with fakes.installed(judge=False):
            reply = u.step(msgs[2 + 2 * j_next].get("content"))
        want_after = RF.user_messages_from_executed(exe[:atts[j_next]["executed_prefix_len"] + 2], instr)
        ok = reply == msgs[3 + 2 * j_next]["content"] and RF.jnorm(u.messages) == want_after
        out["user_step_check"] = {"next_reply_attempt_index": j_next, "reply_equal_saved": reply == msgs[3 + 2 * j_next]["content"],
                                  "list_after_equal_rebuilt": RF.jnorm(u.messages) == want_after}
        checks["user_step_reproduces_next_reply"] = ok

    # --- guard state
    trace = [atts[j]["guard"]["trace_position"] for j in exec_j]
    out["trace"] = {"count": len(trace), "sha256": RF.sha(trace), "positions": trace}
    checks["trace_len_equals_trace_len_before"] = len(trace) == rec_i.get("trace_len_before") == rec_i.get("step_index")
    recomputed = [R.position(d, atts[j]["action"], used_values(atts[j]["guard"]), atts[j]["guard"].get("circuit") or [])
                  for j in exec_j]
    checks["trace_positions_recomputed_from_rule_set"] = RF.jnorm(recomputed) == trace
    out["consecutive_blocks"], out["n_exec"], out["max_steps"], out["cap"] = consecutive, n_exec, MAX_STEPS, CAP

    # --- decisions at the attempt
    again = R.decide(d, att["action"], rec_i.get("circuit") or [], used_values(rec_i), trace)
    checks["saved_decision_again_from_rebuilt_trace"] = again["allowed"] == rec_i.get("action_allowed") and (
        again["margin"] is None or abs(again["margin"] - rec_i.get("margin")) < 1e-9)
    empty = R.decide(d, att["action"], rec_i.get("circuit") or [], used_values(rec_i), [])
    out["decision_with_empty_trace_same"] = empty == again       # info: the frozen rules have no temporal operator
    pre = executed_rebuilt
    ga = guard_at(R, fakes, d, "tgr", trace, pre, pending, n_exec)
    gb = guard_at(R, fakes, d, "tgr_tracker", trace, pre, pending, n_exec)
    src = ga if ep["guard"] == "tgr" else gb
    other = gb if ep["guard"] == "tgr" else ga
    dec = lambda r: "allow" if r["action_allowed"] else "block"   # noqa: E731
    out["decision_a"], out["decision_b"] = dec(ga), dec(gb)
    out["feedback_a"], out["feedback_b"] = ga.get("feedback_text"), gb.get("feedback_text")
    out["kind_from_guards"] = ("block removed" if (dec(ga), dec(gb)) == ("block", "allow") else
                               "block added" if (dec(ga), dec(gb)) == ("allow", "block") else "same")
    checks["source_guard_gives_saved_decision"] = src["action_allowed"] == rec_i.get("action_allowed")
    checks["source_guard_gives_saved_feedback"] = src.get("feedback_text") == rec_i.get("feedback_text")
    checks["source_guard_gives_saved_values"] = {n: v.get("value") for n, v in (src.get("judge") or {}).items()} == \
        used_values(rec_i)
    checks["source_guard_gives_saved_trace_position"] = src.get("trace_position") == rec_i.get("trace_position")
    checks["other_guard_gives_expected_decision"] = other["action_allowed"] == c["other_allowed"]
    checks["kind_from_guards_equals_candidate_kind"] = out["kind_from_guards"] == c["kind"]
    if ep["guard"] == "tgr_tracker" and out["decision_a"] == "block":
        out["feedback_a_note"] = ("judge evidence from the run's judge cache" if fakes.evidence_from_cache
                                  else "judge evidence of changed predicates is a placeholder (not saved)")
    if ep["guard"] == "tgr":
        out["tracker_at_fork"] = {k: (gb.get("tracker") or {}).get(k) for k in ("tracker_values", "replaced", "changed",
                                                                               "judge_skipped", "lookup_errors")}

    # --- end to end: continue the copied loop from the rebuilt state with the source guard and the fakes
    env2 = R.env(d, "test", c["task_index"])
    from tau_bench.types import Action
    env2.data = copy.deepcopy(db["data"])
    env2.actions = [Action(name=a["name"], kwargs=copy.deepcopy(a["kwargs"])) for a in db["env_actions"]]
    env2.user = RF.new_llm_user(messages=users)
    tools_info, _ = R.tools(d)
    state = R.Conversation(trace=copy.deepcopy(trace))
    try:
        with fakes.installed():
            cont = continue_loop(env2, fakes.agent, tools_info, R.guard(d, ep["guard"]), state, agent_messages,
                                 executed_rebuilt, atts[:i], n_exec, consecutive)
        cmp = RF.compare_episode(cont, ep, from_attempt=i)
        out["continue_check"] = {k: v for k, v in cmp.items() if not k.endswith("_equal") or not v}
        out["continue_check"]["fakes"] = {k: v for k, v in fakes.report().items() if k in ("calls",)}
        checks["continue_reproduces_saved_conversation"] = cmp["all_equal"]
    except Exception as e:  # noqa: BLE001 - recorded as a failed check
        out["continue_check"] = {"error": f"{type(e).__name__}: {e}"[:2000]}
        checks["continue_reproduces_saved_conversation"] = False
    out["checks"] = checks
    out["all_checks_pass"] = all(v is True for v in checks.values())
    out["seconds"] = round(time.time() - t0, 1)
    return out


# ----------------------------------------------------------------------------------------------- report
def all_section(all_points: List[dict]) -> List[str]:
    fps = [p for p in all_points if p["first_change_in_conversation"]]
    names = []
    for p in all_points:
        for k in p["checks"]:
            if k not in names:
                names.append(k)
    L = ["## All 172 candidates (`ref_rebuild_all.jsonl`)", "",
         "The same rebuild and checks for every candidate, so that the auditor can compare every fork point of "
         "sources 1 and 2 (the first change of each conversation: `first_change_in_conversation`).", "",
         f"- all checks pass at {sum(p['all_checks_pass'] for p in all_points)} of {len(all_points)} candidates, and "
         f"at {sum(p['all_checks_pass'] for p in fps)} of {len(fps)} fork points;",
         f"- fork points: saved_tgr {sum(p['source'] == 'saved_tgr' for p in fps)} (block removed "
         f"{sum(p['source'] == 'saved_tgr' and p['kind'] == 'block removed' for p in fps)}, added "
         f"{sum(p['source'] == 'saved_tgr' and p['kind'] == 'block added' for p in fps)}), online_tracker "
         f"{sum(p['source'] == 'online_tracker' for p in fps)} (removed "
         f"{sum(p['source'] == 'online_tracker' and p['kind'] == 'block removed' for p in fps)}, added "
         f"{sum(p['source'] == 'online_tracker' and p['kind'] == 'block added' for p in fps)}); luna "
         f"{sum(p['agent'] == 'luna' for p in fps)}, nano {sum(p['agent'] == 'nano' for p in fps)};",
         f"- fork points at a retry (try 2 or 3; both guards blocked the earlier tries): "
         f"{sum(p['attempt'] > 1 for p in fps)}; at a cap override: {sum(bool(p['cap_override']) for p in fps)} "
         f"(candidates at a cap override: {sum(bool(p['cap_override']) for p in all_points)});",
         f"- judge answers taken from the run's judge cache (TGR + tracker runs): "
         f"{sum(p['judge_fake']['answers_from_cache'] for p in all_points if p['source'] == 'online_tracker')} of "
         f"{sum(p['judge_fake']['checks_saved'] for p in all_points if p['source'] == 'online_tracker')} judged checks;",
         f"- decision the same with an empty past trace: {sum(bool(p.get('decision_with_empty_trace_same')) for p in all_points)} "
         f"of {len(all_points)} (the frozen rules have no temporal operator);",
         f"- pending `kwargs` equal to the message arguments: "
         f"{sum(bool(p['pending']['kwargs_equal_message_arguments']) for p in all_points)} of {len(all_points)}.", "",
         "| check | pass | fail |", "|---|---|---|"]
    for k in names:
        ok = sum(1 for p in all_points if p["checks"].get(k) is True)
        bad = sum(1 for p in all_points if k in p["checks"] and p["checks"][k] is not True)
        L.append(f"| {k} | {ok} | {bad} |")
    L += ["", "Fork points (one per conversation), the reference values to compare with a `ForkState`:", "",
          "| run | domain | task | trial | i | try | action | kind | A | B | db sha256 | messages | executed | user "
          "list sha256 | trace | blocks in a row | ok |", "|" + "---|" * 17]
    for p in sorted(fps, key=lambda p: (list(RUNS).index(p["run"]), p["domain"], p["task_index"], p["trial"])):
        L.append(f"| {p['run']} | {p['domain']} | {p['task_index']} | {p['trial']} | {p['attempt_index']} | "
                 f"{p['attempt']} | {p['action']} | {p['kind']} | {p['decision_a']} | {p['decision_b']} | "
                 f"`{p['db']['sha256'][:12]}` | {p['agent_messages']['count']} | {p['executed']['count']} | "
                 f"`{p['user_messages']['sha256'][:12]}` | {p['trace']['count']} | {p['consecutive_blocks']} | "
                 f"{'yes' if p['all_checks_pass'] else 'NO'} |")
    return L + [""]


def write_md(points: List[dict], cands: List[dict], selftest: Optional[dict],
             all_points: Optional[List[dict]] = None) -> None:
    L = ["# R2 reference rebuild (eval v2, Part 4 reference)", "",
         f"Date {time.strftime('%Y-%m-%d')}. Written by R2, an independent reference: own code only, no LLM call, "
         "network blocked, writes only under `output/`. R2 did not read `fork/rebuild.py`, `fork/find_points.py`, "
         "`fork/run_*.py` or their outputs (only the names in `fork/schema.py`).", "",
         "Code: `tests/audit_v2_ref_rebuild.py` (this rebuild), `tests/audit_v2_replay_fakes.py` (replay fakes). "
         "Data: `ref_rebuild.jsonl` (one line per sample point), `ref_rebuild_candidates.json` (all candidates), "
         "`ref_rebuild_fakes_selftest.json` (fakes self-test). Logs: `output/logs/v2_r2_*`.", ""]
    L += HOW_TEXT
    # candidates and sample
    cc = collections.Counter((c["run"], c["domain"], c["kind"]) for c in cands)
    sc = collections.Counter((p["run"], p["domain"], p["kind"]) for p in points)
    L += ["## Candidates and the sample", "",
          f"Candidates (changed decisions): {len(cands)}. Sample: {len(points)} points in "
          f"{len({(p['run'], p['domain'], p['task_index'], p['trial']) for p in points})} conversations "
          f"(seed {SEED}).", "",
          "| run | domain | kind | candidates | sampled |", "|---|---|---|---|---|"]
    for run in RUNS:
        for d in DOMAINS:
            for kd in KINDS:
                if cc[(run, d, kd)]:
                    L.append(f"| {run} | {d} | {kd} | {cc[(run, d, kd)]} | {sc[(run, d, kd)]} |")
    agents = collections.Counter(p["agent"] for p in points)
    L += ["", f"- agents: luna {agents['luna']}, nano {agents['nano']}; sources: saved_tgr "
              f"{sum(p['source'] == 'saved_tgr' for p in points)}, online_tracker "
              f"{sum(p['source'] == 'online_tracker' for p in points)}",
          f"- blocks in a row before the attempt: {sum(p['blocks_before'] > 0 for p in points)}; after a cap "
          f"override: {sum(p['after_cap'] for p in points)}; late (exec_step >= {LATE_STEP} or history over 24,000 "
          f"characters): {sum(p['late'] for p in points)}; fork points (first change in the conversation): "
          f"{sum(p['first_change_in_conversation'] for p in points)}", ""]
    # checks
    names = []
    for p in points:
        for k in p["checks"]:
            if k not in names:
                names.append(k)
    L += ["## Checks (all sample points)", "", "| check | pass | fail |", "|---|---|---|"]
    for k in names:
        ok = sum(1 for p in points if p["checks"].get(k) is True)
        bad = sum(1 for p in points if k in p["checks"] and p["checks"][k] is not True)
        L.append(f"| {k} | {ok} | {bad} |")
    L += ["", f"All checks pass at {sum(p['all_checks_pass'] for p in points)} of {len(points)} points. The user-step "
              f"check is not applicable at {sum('user_step_reproduces_next_reply' not in p['checks'] for p in points)} "
              "points (no executed reply to the user after the attempt: the conversation ends with a tool call).", ""]
    # the points
    L += ["## The sample points", "",
          "| # | run | domain | task | trial | attempt i | step | try | action | kind | A | B | db sha256 | "
          "msgs | exec | user | trace | all ok |", "|" + "---|" * 18]
    for n, p in enumerate(points, 1):
        L.append(f"| {n} | {p['run']} | {p['domain']} | {p['task_index']} | {p['trial']} | {p['attempt_index']} | "
                 f"{p['exec_step']} | {p['attempt']} | {p['action']} | {p['kind']} | {p['decision_a']} | "
                 f"{p['decision_b']} | `{p['db']['sha256'][:12]}` | {p['agent_messages']['count']} | "
                 f"{p['executed']['count']} | {p['user_messages']['count']} | {p['trace']['count']} | "
                 f"{'yes' if p['all_checks_pass'] else 'NO'} |")
    L += [""]
    fails = [p for p in points if not p["all_checks_pass"]]
    if fails:
        L += ["### Failed checks", ""]
        for p in fails:
            bad = [k for k, v in p["checks"].items() if v is not True]
            L.append(f"- {p['run']}/{p['domain']} task {p['task_index']} trial {p['trial']} attempt "
                     f"{p['attempt_index']}: {', '.join(bad)}; continue: {json.dumps(p.get('continue_check'))[:400]}")
        L.append("")
    # fakes self-test
    if selftest:
        L += ["## Replay fakes: self-test", "",
              "Replay from the start with the copied `run_episode` loop, a real τ-bench env (`user_strategy=\"human\"`, "
              "then a real `LLMUserSimulationEnv` without its build call), the source run's real guard (frozen TGR or "
              "TGR + tracker), and the three fakes. Must give the saved conversation exactly.", "",
              "| run | domain | task | trial | guard | attempts | steps | blocks | cap overrides | reward | "
              "agent / user / judge calls answered | exact |", "|" + "---|" * 12]
        for r in selftest["results"]:
            f = (r.get("fakes") or {}).get("calls", {})
            L.append(f"| {r['run']} | {r['domain']} | {r['task_index']} | {r['trial']} | {r['guard']} | {r['attempts']} | "
                     f"{r['n_exec_steps']} | {r['n_blocks']} | {r['n_cap_overrides']} | {r['reward']} | "
                     f"{f.get('agent', 0)} / {f.get('user', 0)} / {f.get('judge', 0)} | "
                     f"{'yes' if (r.get('compare') or {}).get('all_equal') else 'NO'} |")
        neg = selftest["negative_tests"]
        L += ["", f"Exact: {sum(bool((r.get('compare') or {}).get('all_equal')) for r in selftest['results'])} of "
                  f"{len(selftest['results'])} (messages, executed, every attempt field and guard record field, "
                  "reward, done, reward_info). Negative tests (each must raise `ReplayMiss`): "
                  + ", ".join(f"{k} {'ok' if str(v).startswith('raised') else v}" for k, v in neg.items()
                              if k not in ("all_raised",)) + f". All raised: {neg['all_raised']}.", "",
              "The end-to-end check of every sample point above (`continue_reproduces_saved_conversation`) is the "
              "same fakes used from the middle of a conversation: the loop starts at the fork attempt from the "
              "rebuilt state, and the fakes answer from there on.", ""]
    if all_points:
        L += all_section(all_points)
    L += NOTES_TEXT
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


HOW_TEXT = [
    "## How each point is computed", "",
    "For one saved conversation `ep` and attempt `i` (`a = ep[\"attempts\"][i]`):", "",
    "| part | how (own code) | checked against |", "|---|---|---|",
    "| executed history | `messages[:2]` + the two messages of every attempt `j < i` that was not blocked "
    "(cap overrides count as executed) | saved `executed[:a.executed_prefix_len]` |",
    "| executed steps, blocks in a row | count of executed attempts before `i`; blocked attempts right before `i` at "
    "the same step | `a.exec_step`, `a.attempt - 1`, `a.executed_prefix_len = 2 + 2 n`, the cap-override rule |",
    "| agent messages, pending | `messages[:2 + 2i]`, `messages[2 + 2i]` (arguments parsed from the message) | the "
    "attempt pairs (action, feedback / observation), `a.kwargs` |",
    "| database | venv τ-bench `data_load_func()`, then every executed tool call `tools_map[name].invoke(data, "
    "**json.loads(arguments))`, errors as `\"Error: <e>\"` (as `Env.step`) | every replayed output = the saved "
    "output; sha256 (canonical JSON) and τ-bench's `consistent_hash` given |",
    "| env actions | `message_to_action` of every executed agent message (replies included) | count = executed steps |",
    "| user simulator | real `build_system_prompt(instruction)`, \"Hi! ...\", its first message, then (agent text as "
    "\"user\", reply as \"assistant\" with `tool_calls: None`) per executed reply | the real "
    "`LLMUserSimulationEnv.step` with the replay fake gives the next saved reply, and its list then equals the "
    "next rebuilt list |",
    "| guard trace | `trace_position` of every executed attempt before `i` | length = `trace_len_before` = "
    "`step_index`; every position recomputed from the rule set (action predicates + the values used) |",
    "| decision again | copied `repro_runtime.mln.decide` on the rebuilt trace with the saved values | saved "
    "`action_allowed` and `margin` |",
    "| decisions A and B | the real frozen TGR guard (`repro_online.guards.TGRGuard`, frozen rules) and the real "
    "TGR + tracker guard (`guard/tgr_tracker.py`) at the attempt, on the rebuilt history, trace and pending message, "
    "with the replay fake judge (the saved judge answer for that prompt) | the source guard gives the saved "
    "decision, values, trace position and block message; the other guard gives the candidate's other decision |",
    "| end to end | the copied loop of `run_episode` continued from the rebuilt state (env data, env actions, user "
    "list, trace, counters) with the source guard and the replay fakes | the whole saved conversation: messages, "
    "executed, attempts from `i`, reward, done, reward_info |", "",
    "Candidates: source 1 = `output/p8_changes.jsonl` rows with a version-b change (the partner's frozen TGR runs "
    "`luna_train_v5`, `nano_train`); source 2 = attempts of `p10_luna_train`, `p10_nano_train`, `p10_luna_val` "
    "where `tracker.changed` is not empty and the decision with `tracker.judge_values` (same past trace) differs "
    "from the used one. Episodes: the last line without an error per (task, trial). The sample is fork-like "
    "attempts, not only fork points (the special cases need retries and late attempts).", "",
    "Hash: sha256 of `json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(\",\", \":\"))` (UTF-8). The "
    "user list hash is given with `\"tool_calls\": None` in its assistant entries (as `model_dump` makes them) and "
    "without keys whose value is None (`sha256_without_none_keys`).", ""]

NOTES_TEXT = [
    "## Notes for the Part 4 auditor (surprises and traps)", "",
    "1. **Judge evidence at source-2 forks.** TGR + tracker records keep only the judge's values "
    "(`tracker.judge_values`); for a value the tracker changed, the judge's evidence is not in the record. Frozen "
    "TGR's block message prints the evidence of every predicate of the violated rules. So where branch A (frozen TGR) "
    "blocks at a source-2 fork (\"block removed\"), its block message is exact only with the judge's full answer. It "
    "is in the run's judge cache, `output/_llmcache/<tag>/structured/` (same key as `policy_pipeline/llm.py` "
    "`LLM.call`; read only), and was found for every judged check (see above). `feedback_a` here is made with it. "
    "Without the cache the replay fake gives a placeholder evidence (then `feedback_a` differs in that line only).",
    "2. **Fork points at a retry.** Some fork points are at try 2 or 3: both guards blocked the earlier tries of the "
    "same step. There blocks in a row is 1 or 2 at the fork, and the cap (3) continues from that count. A branch "
    "runner that starts the count at 0 is wrong.",
    "3. **Cap overrides.** 13 changed records of source 1 are cap overrides (try 4: blocked, but run anyway). None is "
    "a fork point. If one ever is, both branches run the same call; only the trace entry (values) differs.",
    "4. **The past trace never changes a decision.** The frozen rules use only IMPLIES, NOT, OR, AND (no temporal "
    "operator), and the decision with an empty past trace equals the one with the rebuilt trace everywhere. So it "
    "does not matter that, at a source-2 fork, the trace holds the tracker's values (not the judge's) for branch A. "
    "The trace length still matters (`trace_len_before` is checked by the guard records).",
    "5. **User-simulator list format.** Its assistant entries carry `\"tool_calls\": None` (as `model_dump` makes "
    "them). A list without that key behaves the same with the real model call (`chat_to_responses_input` drops it), "
    "but its sha256 differs: then compare with `sha256_without_none_keys`. The replay fakes compare exactly by "
    "default, so they need the `None` key; `ReplayFakes(..., loose=True)` drops None-valued keys before comparing.",
    "6. **The env-build probe.** The user fake refuses the user-simulator call with no instruction (part1.md 5.7 "
    "trap 2). So a branch runner that builds an `LLMUserSimulationEnv` the normal way is caught "
    "(`allow_build_probe=True` lets it pass, if wanted).",
    "7. **Judge fake key.** The judge fake finds a check by its exact prompt (sha256 of system + user). The judge "
    "sees only the last 24,000 characters of the history, so the judge fake alone cannot see a wrong early history; "
    "the agent fake compares the full message list and catches it.",
    "8. **Reward needs `env.actions`.** τ-bench scores from the final data hash and the reply texts in "
    "`env.actions`. A branch must rebuild `env.actions` (replies included), not only the data. The end-to-end check "
    "here does this, and gives the saved reward and `reward_info` everywhere.",
    "9. **Other branch, other guard.** To check a branch runner with the fakes, run it with the saved decision and "
    "the source run's guard: it must give the saved conversation. With the other decision, the agent fake raises "
    "`ReplayMiss` at the next agent call (expected: the conversation leaves the saved one).",
    "10. **No format surprise.** Every index rule of part1.md 5.2 holds at every point; every replayed output equals "
    "the saved one; the pending `kwargs` equal the message arguments everywhere here (the aliasing case of part1.md "
    "5.7 is an airline `luna_val` conversation, not a candidate).", ""]


def run_points(R: Runner, runs, sample: List[dict], splits: dict, tag: str) -> List[dict]:
    points = []
    for n, s in enumerate(sample, 1):
        ep = runs[(s["run"], s["domain"])][(s["task_index"], s["trial"])][1]
        try:
            p = rebuild_point(R, s, ep, splits)
        except Exception as e:  # noqa: BLE001 - recorded
            p = dict({k: s[k] for k in ("run", "domain", "task_index", "trial", "attempt_index", "kind")},
                     error=f"{type(e).__name__}: {e}", traceback=traceback.format_exc()[-3000:], checks={"ran": False},
                     all_checks_pass=False)
        points.append(p)
        bad = [k for k, v in p["checks"].items() if v is not True]
        print(f"[r2-ref] {tag} {n}/{len(sample)} {s['run']}/{s['domain']} task {s['task_index']} trial {s['trial']} "
              f"attempt {s['attempt_index']}: all ok {p['all_checks_pass']} {bad} {p.get('error', '')} "
              f"({p.get('seconds')} s)", flush=True)
    return points


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates-only", action="store_true")
    ap.add_argument("--all", action="store_true", help="also rebuild every candidate: ref_rebuild_all.jsonl")
    a = ap.parse_args(argv)
    from guard import write_guard
    write_guard.install([os.path.join(PC_DIR, "output")])
    RF.block_network()
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    R = Runner()
    runs = load_runs()
    cands = candidates(R, runs)
    sample = select(cands)
    os.makedirs(REF_DIR, exist_ok=True)
    with open(OUT_CAND, "w", encoding="utf-8") as f:
        json.dump({"n_candidates": len(cands), "seed": SEED, "candidates": cands,
                   "sample": [{k: s[k] for k in ("run", "domain", "task_index", "trial", "attempt_index", "kind",
                                                 "selected_for")} for s in sample]}, f, indent=1, ensure_ascii=False)
    cc = collections.Counter((c["run"], c["domain"], c["kind"]) for c in cands)
    print("[r2-ref] candidates:", len(cands), dict(cc), flush=True)
    for flag in ("blocks_before", "after_cap", "late", "first_change_in_conversation"):
        print(f"[r2-ref] candidates with {flag}: {sum(bool(c[flag]) for c in cands)}; in sample: "
              f"{sum(bool(s[flag]) for s in sample)}", flush=True)
    print("[r2-ref] sample:", len(sample), flush=True)
    for s in sample:
        print("   ", s["run"], s["domain"], s["task_index"], s["trial"], s["attempt_index"], s["kind"],
              "step", s["exec_step"], "try", s["attempt"], s["action"], s["selected_for"], flush=True)
    if a.candidates_only:
        return 0
    with open(SPLITS, encoding="utf-8") as f:
        splits = json.load(f)
    points = run_points(R, runs, sample, splits, "sample")
    with open(OUT_JSONL, "w", encoding="utf-8") as f:
        for p in points:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    all_points = None
    if a.all:
        all_points = run_points(R, runs, [dict(c, selected_for="all candidates") for c in cands], splits, "all")
        with open(OUT_ALL, "w", encoding="utf-8") as f:
            for p in all_points:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
    st_path = os.path.join(REF_DIR, "ref_rebuild_fakes_selftest.json")
    selftest = json.load(open(st_path, encoding="utf-8")) if os.path.exists(st_path) else None
    if all("error" not in p for p in points + (all_points or [])):
        write_md(points, cands, selftest, all_points)
    print(f"[r2-ref] sample: all checks pass at {sum(p['all_checks_pass'] for p in points)} of {len(points)} points"
          + (f"; all candidates: {sum(p['all_checks_pass'] for p in all_points)} of {len(all_points)}"
             if all_points else "") + f"; refused writes {len(write_guard.REFUSED)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
