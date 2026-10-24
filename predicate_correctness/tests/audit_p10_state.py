"""Part 10 audit (independent check, no LLM call): the guard's online path on the saved conversations.

For every attempt in the copied episodes (from_shieldagent/runs/<run>/<domain>/tgr/episodes.jsonl):
  1. online state = offline state: the guard builds the state as the live loop would (repro_online.guards.make_step on
     executed[:executed_prefix_len] and the real agent message from `messages`, then state.build_state with the step's
     tool and arguments). It must equal the Part 4-6 state (state.walk over `executed`, as run_lookups.py uses), field
     by field (db, shown, shown_meta, events, n_steps, mismatches, parse problems, problems), and the pending action
     must equal the saved one;
  2. the history holds no blocked attempt: its agent messages = the executed attempts before this one;
  3. the guard's tracker values (guard.check with a fake judge giving the saved values) equal Part 6
     (output/p6_values.jsonl);
  4. the judge prompt is TGR's own: the cache key of the prompt the guard sends (same key formula as
     policy_pipeline/llm.py, model gpt-6-luna) exists in the partner's judge cache
     (~/ShieldAgent/output/tgr/_llmcache/structured; only os.path.exists, read only);
  5. thread safety: tracker values from 8 threads equal the sequential ones (a sample).

Run from predicate_correctness/ with the venv:  python -B -m tests.audit_p10_state > output/logs/p10_audit_state.log 2>&1
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.dont_write_bytecode = True
PC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC not in sys.path:
    sys.path.insert(0, PC)

from guard import offline, tgr_tracker                                    # noqa: E402
from repro_online.guards import make_step                                   # noqa: E402  (runner copy)
from repro_core.llm import llm_config                                       # noqa: E402  (runner copy)
from method_tgr.runtime import JUDGE_SCHEMA                                 # noqa: E402
from state_tracker import paths, tau_copy                                   # noqa: E402
from state_tracker.state import build_state, normalize_action, walk         # noqa: E402
from state_tracker.load_steps import episode_trial, iter_episodes, step_id  # noqa: E402

PARTNER_CACHE = os.path.expanduser("~/ShieldAgent/output/tgr/_llmcache/structured")
SITE = "/home/azureuser/venvs/tau-bench/lib/python3.12/site-packages/tau_bench/envs"


def fp(st) -> str:
    d = {"db": st.db, "shown": st.shown, "shown_meta": st.shown_meta, "events": st.events, "n_steps": st.n_steps,
         "mismatches": st.mismatches, "parse_problems": st.parse_problems, "problems": st.problems,
         "today": st.today_text}
    return hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()


def judge_key(call: dict) -> str:
    params = {"model": "gpt-6-luna", "effort": call["effort"], "max_output_tokens": llm_config()["max_output_tokens"],
              "schema_name": call["schema_name"], "schema": JUDGE_SCHEMA, "sample": 0}
    return hashlib.sha256(json.dumps({"system": call["system"], "user": call["user"], "params": params},
                                     sort_keys=True).encode()).hexdigest()


def main() -> int:
    t0 = time.time()
    for d in paths.DOMAINS:
        same = tau_copy.policy_text(d) == open(os.path.join(SITE, d, "wiki.md"), encoding="utf-8").read()
        print(f"policy text {d}: copy == venv wiki.md: {same}", flush=True)
    p6 = offline.load_p6()
    tot = collections.Counter()
    problems = []
    sample_steps = []

    def bad(kind, sid, detail=""):
        tot["problem: " + kind] += 1
        if len(problems) < 40:
            problems.append(f"{kind}: {sid}: {detail}"[:400])

    for domain in paths.DOMAINS:
        guard = tgr_tracker.TGRTrackerGuard(domain, tau_copy.tools_info(domain))
        current = {}
        judge = offline.FakeJudge(lambda names: current["answer"])
        offline.install_fake(judge)
        for run in paths.RUNS:
            c = collections.Counter()
            seen = collections.Counter()
            t1 = time.time()
            for line_no, ep in iter_episodes(run, domain):
                trial = episode_trial(ep, seen)
                executed, messages, attempts = ep["executed"], ep["messages"], ep["attempts"]
                stops = sorted({a["executed_prefix_len"] for a in attempts})
                offline_fp = {n: fp(st) for n, st in walk(executed, domain=domain, stops=stops)}
                n_ran = 0
                for i, att in enumerate(attempts):
                    c["attempts"] += 1
                    sid = step_id(run, domain, ep["task_index"], trial, att["exec_step"], att["attempt"])
                    msg = messages[2 + 2 * i]
                    calls = msg.get("tool_calls") or []
                    if msg.get("role") != "assistant" or (att["action"] != "respond" and
                                                         (not calls or calls[0]["function"]["name"] != att["action"])):
                        bad("message alignment", sid)
                        continue
                    hist = executed[:att["executed_prefix_len"]]
                    step = make_step(hist, msg, att["exec_step"])
                    # 2. no blocked attempt in the history
                    if sum(1 for m in step.history if m.get("role") == "assistant") != n_ran:
                        bad("history has blocked attempts", sid)
                    # 1. online state = offline state
                    st = build_state(step.history, {"tool": step.name, "args": step.arguments}, domain=domain)
                    if fp(st) != offline_fp[att["executed_prefix_len"]]:
                        bad("online state != offline state", sid)
                    else:
                        c["state equal"] += 1
                    if st.pending != normalize_action({"action": att["action"], "kwargs": att["kwargs"]}):
                        bad("pending differs", sid, f"{st.pending} vs {att['action']} {att['kwargs']}")
                    c["mismatches"] += len(st.mismatches)
                    c["parse_problems"] += len(st.parse_problems)
                    c["state_problems"] += len(st.problems)
                    if not att["blocked"]:
                        n_ran += 1
                    g = att.get("guard") or {}
                    if not g.get("judge"):
                        continue
                    # 3. tracker values and 4. judge prompt, through the real guard
                    c["records"] += 1
                    current["answer"] = {n: (v.get("value"), v.get("evidence", "")) for n, v in g["judge"].items()}
                    k0 = len(judge.calls)
                    conv = guard.new_episode()
                    conv.trace = [a["guard"]["trace_position"] for a in attempts[:i] if not a["blocked"]]
                    out = guard.check(conv, list(hist), msg, att["exec_step"])
                    tv = {n: v.get("value") for n, v in (out["tracker"].get("tracker_values") or {}).items()}
                    if tv != p6.get(sid, {}):
                        bad("tracker values != Part 6", sid, f"{tv} vs {p6.get(sid)}")
                    else:
                        c["tracker = Part 6"] += 1
                    c["lookup errors"] += len(out["tracker"].get("lookup_errors") or [])
                    if len(judge.calls) - k0 != 1:
                        bad("judge calls != 1", sid, str(len(judge.calls) - k0))
                        continue
                    key = judge_key(judge.calls[-1])
                    if os.path.exists(os.path.join(PARTNER_CACHE, key[:2], key + ".json")):
                        c["judge prompt in partner cache"] += 1
                    else:
                        c["judge prompt NOT in partner cache"] += 1
                        if c["judge prompt NOT in partner cache"] <= 3:
                            print(f"  not in cache: {sid}", flush=True)
                    if len(sample_steps) < 600 and c["records"] % 7 == 0:
                        code = [n for n in g["judge"] if n in guard.tgr.code_types]
                        if code:
                            sample_steps.append((guard, step, sorted(code), tv))
            print(f"{run}/{domain}: {dict(c)} ({time.time() - t1:.0f} s)", flush=True)
            tot.update({f"{k}": v for k, v in c.items()})

    # 5. thread safety on a sample (no judge needed: tracker_values only)
    def one(item):
        g, step, code, want = item
        got, _, _ = g.tgr.tracker_values(step, code)
        return {n: v.get("value") for n, v in got.items()} == {n: want.get(n) for n in code}
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(one, sample_steps * 2))
    print(f"threads: {sum(res)} of {len(res)} tracker results equal the sequential ones", flush=True)
    tot["thread sample"] = len(res)
    tot["thread sample equal"] = sum(res)
    print("TOTAL", json.dumps(dict(tot), sort_keys=True))
    for p in problems:
        print("PROBLEM", p)
    print(f"DONE in {time.time() - t0:.0f} s; problems {sum(v for k, v in tot.items() if k.startswith('problem: '))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
