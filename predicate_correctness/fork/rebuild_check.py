"""Eval v2 Part 3 (fork/rebuild_check.py): check every fork point's rebuild against its saved conversation. No LLM.

Checks per fork point (a fork point that fails one is dropped, with the reason written down):
  episode         the line is the fork point's conversation; attempt i has the fork point's exec_step, attempt and
                  action; the arguments are the message's (tool_calls[0].function.arguments)
  replay          the replayed database gives the saved tool output for every executed call before the fork
  agent_messages  the agent's view rebuilt from `executed` plus the blocked attempts (agent message + the saved block
                  message, as the episode loop adds them) equals the saved messages[:2 + 2i]; pending = messages[2 + 2i]
  user_messages   the rebuilt user-simulator list matches the user turns: its system prompt holds the task's
                  instruction, then the greeting, then each executed user message as its own ("assistant") message
                  and each executed agent reply before it as "user"
  decision        the source guard's saved decision comes out again offline from the saved judge values (frozen TGR:
                  the saved judge; TGR + tracker: tracker.judge_values, with the tracker run again on the rebuilt
                  history), with the same margin, rules and block message; the other guard gives the fork point's
                  decision and block message
  trace           the rebuilt guard trace has trace_len_before entries (= executed steps before = n_exec);
                  consecutive blocks = attempt - 1 <= cap
  env             (venv Python only) make_env(state) builds a τ-bench env with no LLM call: replayed outputs, data,
                  actions and τ-bench's own user system prompt all equal the rebuilt state
  continuation    (venv Python only) the rest of the saved conversation, stepped on that env (tool calls through
                  env.step, the saved user replies put into env.user), gives the saved tool outputs and, for a
                  finished conversation, the saved reward and reward_info
The two venv checks are skipped (and said so) when tau_bench cannot be imported (standard library Python).

CLI: python -B -m fork.rebuild_check --points <jsonl> [--md <md>]   (checks a points file; writes only the md)
fork/find_points.py runs the same checks before it writes its points file.
Never imports gold code.
"""
from __future__ import annotations

import argparse
import collections
import copy
import json
import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional

sys.dont_write_bytecode = True

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "fork"

from fork import points_tgr as PT                                     # noqa: E402
from fork import rebuild_tasks                                        # noqa: E402
from fork.rebuild import (RebuildError, _jnorm, action_of, make_env, read_episode, rebuild,   # noqa: E402
                          user_sim_messages)
from fork.schema import ForkPoint                                     # noqa: E402
from state_tracker import paths                                       # noqa: E402

MARGIN_TOL = 1e-9
CHECKS = ("episode", "replay", "agent_messages", "user_messages", "decision", "trace", "env", "continuation")
CHECK_TEXT = {
    "episode": "the line is the conversation; attempt fields and arguments (from the message) match",
    "replay": "replayed database gives the saved tool outputs before the fork",
    "agent_messages": "agent view rebuilt from executed + blocked attempts = saved messages up to the fork",
    "user_messages": "rebuilt user-simulator messages match the user turns (and the task instruction)",
    "decision": "source guard's saved decision, margin, rules and block message come out again offline; the other "
                "guard gives the fork point's decision and message",
    "trace": "guard trace length = trace_len_before = executed steps; blocks in a row = attempt - 1",
    "env": "venv: τ-bench env built with no LLM call; outputs, data, actions, user prompt equal",
    "continuation": "venv: the rest of the saved conversation on that env gives the saved outputs and reward",
}

_VENV: Optional[bool] = None
NETWORK_ATTEMPTS: List[str] = []


def say(msg: str) -> None:
    print(msg, flush=True)


# ----------------------------------------------------------------------------------------------- safety
def _no_network(event, args):
    if event in ("socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.create_connection"):
        NETWORK_ATTEMPTS.append(event)
        raise RuntimeError(f"network blocked in the fork checks ({event})")


class _NoLLM:
    """Put in place of the runner's shared judge client: any judge call fails loudly."""
    model, max_output_tokens = "no-llm", 16000
    cache_dir = os.path.join(paths.OUTPUT_DIR, "_no_llm_never_written")

    def call(self, **_):
        raise RuntimeError("an LLM judge call was attempted in the fork checks")


def _no_user(*_, **__):
    raise RuntimeError("a user-simulator LLM call was attempted in the fork checks")


def safety_setup() -> None:
    """For the CLIs only (never at import): block the network, refuse writes outside output/, and make every judge
    or user-simulator call fail."""
    sys.addaudithook(_no_network)
    from guard import write_guard
    write_guard.install([paths.OUTPUT_DIR])
    from repro_runtime import calls                     # runner copy (path set by fork.points_tgr)
    calls._llm = _NoLLM()
    if venv_available():
        import tau_bench.envs.user as user_mod
        user_mod.completion = _no_user


def venv_available() -> bool:
    """True when the real tau_bench can be imported (the venv Python)."""
    global _VENV
    if _VENV is None:
        os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
        try:
            import tau_bench.envs  # noqa: F401
            _VENV = True
        except Exception:  # noqa: BLE001 - standard library Python
            _VENV = False
    return _VENV


# ----------------------------------------------------------------------------------------------- one fork point
def _agent_view(ep: dict, i: int) -> List[dict]:
    """messages[:2 + 2i] rebuilt from `executed` and the blocked attempts (repro_online/episode.py's rules)."""
    exe, msgs, atts = ep["executed"], ep["messages"], ep["attempts"]
    view = copy.deepcopy(exe[:2])
    for j in range(i):
        aj, mj = atts[j], msgs[2 + 2 * j]
        if aj["blocked"]:
            fb = aj.get("feedback")
            if aj["action"] == "respond":
                ans = {"role": "system", "content": fb}
            else:
                tc = mj["tool_calls"][0]
                ans = {"role": "tool", "tool_call_id": tc["id"], "name": tc["function"]["name"], "content": fb}
            view += [mj, ans]
        else:
            k = 2 + 2 * aj["exec_step"]
            view += copy.deepcopy(exe[k:k + 2])
    return view


def _check(ok: bool, detail: str = "") -> Dict[str, Any]:
    return {"ok": bool(ok), "detail": detail}


def check_point(fp: ForkPoint, off_for: Callable[[str], PT.OfflineGuards], venv: Optional[bool] = None) -> dict:
    """All checks of one fork point: {fork_id, ok, checks: {name: {ok, detail}}, reasons: [...]}."""
    venv = venv_available() if venv is None else venv
    checks: Dict[str, Dict[str, Any]] = {}
    out = {"fork_id": fp.fork_id, "source": fp.source, "run": fp.run, "domain": fp.domain, "kind": fp.kind,
           "checks": checks}
    try:
        ep = read_episode(fp)
        st = rebuild(fp, ep)
    except Exception as e:  # noqa: BLE001
        checks["episode"] = _check(False, f"rebuild failed: {type(e).__name__}: {e}")
        return _finish(out)
    i = fp.attempt_index
    a = ep["attempts"][i]
    g = a.get("guard") or {}
    name, args = action_of(st.pending)
    bad = [k for k, want, got in (("exec_step", fp.exec_step, a["exec_step"]), ("attempt", fp.attempt, a["attempt"]),
                                  ("action", fp.action, a["action"]), ("message action", fp.action, name),
                                  ("arguments", fp.arguments, args)) if want != got]
    checks["episode"] = _check(not bad, "differs: " + ", ".join(bad) if bad else f"attempt {i} of {len(ep['attempts'])}")

    rp = st.extra["replay"]
    checks["replay"] = _check(not rp["mismatches"] and not rp["problems"],
                              f"{rp['tool_calls']} tool calls, {len(rp['mismatches'])} mismatches, "
                              f"{len(rp['problems'])} problems")

    view = _agent_view(ep, i)
    exe_ok = st.executed == ep["executed"][:a["executed_prefix_len"]]
    checks["agent_messages"] = _check(view == st.messages and st.messages == ep["messages"][:2 + 2 * i] and exe_ok
                                      and st.pending == ep["messages"][2 + 2 * i],
                                      f"{len(st.messages)} messages, {len(st.executed)} executed")

    um = st.user_messages
    exe = st.executed
    sim_said = [exe[1].get("content")] + [exe[k + 1].get("content") for k in range(2, len(exe) - 1, 2)
                                          if exe[k + 1].get("role") == "user"]
    agent_said = [exe[k].get("content") for k in range(2, len(exe) - 1, 2) if exe[k + 1].get("role") == "user"]
    instr = st.extra["instruction"]
    ok_um = (um[0] == {"role": "system", "content": rebuild_tasks.user_system_prompt(instr)}
             and ("Instruction: " + instr) in um[0]["content"]
             and um[1] == {"role": "user", "content": rebuild_tasks.GREETING}
             and [m["content"] for m in um[2::2]] == sim_said and all(m["role"] == "assistant" for m in um[2::2])
             and [m["content"] for m in um[3::2]] == agent_said and all(m["role"] == "user" for m in um[3::2])
             and len(um) == 2 + len(sim_said) + len(agent_said))
    checks["user_messages"] = _check(ok_um, f"{len(um)} messages, {len(agent_said)} executed replies")

    checks["decision"] = _check_decision(fp, ep, st, a, g, off_for(fp.domain))

    n_tr = len(st.trace)
    ok_tr = (n_tr == g.get("trace_len_before") == st.n_exec == g.get("step_index") and
             st.consecutive_blocks == a["attempt"] - 1 and 0 <= st.consecutive_blocks <= st.cap)
    checks["trace"] = _check(ok_tr, f"trace {n_tr}, trace_len_before {g.get('trace_len_before')}, n_exec "
                                    f"{st.n_exec}, blocks in a row {st.consecutive_blocks}")

    if venv:
        try:
            env = make_env(st, user_model=(ep.get("models") or {}).get("user"))
            checks["env"] = _check(True, f"task {env.task_index} ({st.task_split}), {len(env.actions)} actions")
        except Exception as e:  # noqa: BLE001
            checks["env"] = _check(False, f"{type(e).__name__}: {e}")
            env = None
        try:
            checks["continuation"] = (_check_continuation(ep, st, env) if env is not None
                                      else _check(False, "no env"))
        except Exception as e:  # noqa: BLE001
            checks["continuation"] = _check(False, f"{type(e).__name__}: {e}")
    else:
        checks["env"] = {"ok": None, "detail": "skipped: tau_bench not importable (standard library Python)"}
        checks["continuation"] = {"ok": None, "detail": "skipped: tau_bench not importable"}
    return _finish(out)


def _finish(out: dict) -> dict:
    reasons = [f"{k}: {v['detail']}" for k, v in out["checks"].items() if v["ok"] is False]
    out["reasons"] = reasons
    out["ok"] = not reasons and all(out["checks"].get(k, {}).get("ok") is not False for k in CHECKS)
    return out


def _same_rec(rec: dict, saved: dict) -> List[str]:
    """What differs between an offline guard record and the saved one (decision, margin, rules, block message)."""
    bad = []
    if bool(rec["action_allowed"]) != bool(saved["action_allowed"]):
        bad.append("decision")
    m1, m2 = rec.get("margin"), saved.get("margin")
    if (m1 is None) != (m2 is None) or (m1 is not None and abs(m1 - m2) > MARGIN_TOL):
        bad.append("margin")
    if [v["rule_id"] for v in rec.get("violated_rules") or []] != [v["rule_id"] for v in saved.get("violated_rules") or []]:
        bad.append("violated rules")
    if PT.feedback_of(rec) != PT.feedback_of(saved):
        bad.append("block message")
    return bad


def _check_decision(fp: ForkPoint, ep: dict, st, a: dict, g: dict, off: PT.OfflineGuards) -> Dict[str, Any]:
    want_a, want_b = fp.decision_a == "allow", fp.decision_b == "allow"
    expected_kind = "block removed" if (not want_a and want_b) else ("block added" if (want_a and not want_b) else None)
    problems = []
    if expected_kind != fp.kind:
        problems.append(f"kind {fp.kind!r} does not follow the decisions")
    if fp.source_guard in ("tgr", "tgr_frozen"):
        saved_judged = PT.saved_judge_answer(g)
        rec_a = off.check("A", st.executed, st.pending, st.n_exec, st.trace, saved_judged)
        problems += [f"frozen TGR again: {x}" for x in _same_rec(rec_a, g)]
        if bool(g["action_allowed"]) != want_a:
            problems.append("decision_a is not the saved decision")
        if PT.feedback_of(g) != fp.feedback_a:
            problems.append("feedback_a is not the saved block message")
        rec_b = off.check("B", st.executed, st.pending, st.n_exec, st.trace, saved_judged)
        if bool(rec_b["action_allowed"]) != want_b:
            problems.append("TGR + tracker offline does not give decision_b")
        if PT.feedback_of(rec_b) != fp.feedback_b:
            problems.append("TGR + tracker offline does not give feedback_b")
        detail = f"saved {fp.decision_a}, tracker {fp.decision_b}"
    else:
        judged, info = PT.own_judge_answer(off.frozen, g, st.executed, _cache_dir(fp),
                                           (ep.get("models") or {}).get("guard"))
        rec_b = off.check("B", st.executed, st.pending, st.n_exec, st.trace, judged)
        problems += [f"TGR + tracker again: {x}" for x in _same_rec(rec_b, g)]
        if sorted((rec_b.get("tracker") or {}).get("changed") or []) != sorted((g.get("tracker") or {}).get("changed") or []):
            problems.append("TGR + tracker again: other changed values")
        if bool(g["action_allowed"]) != want_b:
            problems.append("decision_b is not the saved decision")
        if PT.feedback_of(g) != fp.feedback_b:
            problems.append("feedback_b is not the saved block message")
        rec_a = off.check("A", st.executed, st.pending, st.n_exec, st.trace, judged)
        if bool(rec_a["action_allowed"]) != want_a:
            problems.append("frozen TGR with the judge's own values does not give decision_a")
        if PT.feedback_of(rec_a) != fp.feedback_a:
            problems.append("frozen TGR with the judge's own values does not give feedback_a")
        if info["evidence"] != fp.judge_evidence_from:
            problems.append("judge_evidence_from differs from the evidence found again")
        missing = sorted(n for n, s in info["evidence"].items() if s == "missing")
        if missing and not want_a:
            problems.append(f"frozen TGR's block message has no judge evidence for {', '.join(missing)} (the run's "
                            f"judge cache: {info['cache']}; {_cache_dir(fp)})")
        if info["problems"]:
            problems.append("judge evidence: " + "; ".join(info["problems"]))
        detail = (f"saved {fp.decision_b}, judge's own values {fp.decision_a}; judge evidence "
                  f"{dict(collections.Counter(info['evidence'].values()))} (cache: {info['cache']})")
    return _check(not problems, "; ".join(problems) if problems else detail)


_CACHE_DIRS: Dict[tuple, Optional[str]] = {}


def _cache_dir(fp: ForkPoint) -> Optional[str]:
    """The judge cache of the fork point's run and source guard (only tgr_tracker runs need it): the one the run
    files of its folder name for fp.source_guard (find_points._find_cache_dir; audit A3 W1)."""
    folder = os.path.dirname(os.path.join(paths.PC_DIR, fp.episodes_path))
    key = (folder, fp.source_guard)
    if key not in _CACHE_DIRS:
        from fork.find_points import LLMCACHE_DIR, _find_cache_dir
        default = os.path.join(LLMCACHE_DIR, fp.run, "structured") if fp.source == "online_tracker" else None
        _CACHE_DIRS[key] = _find_cache_dir(folder, fp.source_guard, default)
    return _CACHE_DIRS[key]


def _check_continuation(ep: dict, st, env) -> Dict[str, Any]:
    """Step the rest of the saved conversation on the rebuilt env (no LLM: saved user replies are put in)."""
    from tau_bench.agents.tool_calling_agent import message_to_action
    from tau_bench.types import RESPOND_ACTION_NAME
    rest = ep["executed"][len(st.executed):]
    bad, reward, info, done = [], None, None, False
    for k in range(0, len(rest) - 1, 2):
        m, r = rest[k], rest[k + 1]
        action = message_to_action(m)
        if action.name == RESPOND_ACTION_NAME:
            env.actions.append(action)
            env.user.messages.append({"role": "user", "content": action.kwargs["content"]})
            env.user.messages.append({"role": "assistant", "content": r.get("content"), "tool_calls": None})
            if "###STOP###" in (r.get("content") or ""):
                rr = env.calculate_reward()
                reward, info, done = rr.reward, _jnorm(rr.model_dump()), True
        else:
            resp = env.step(action)
            if resp.observation != r.get("content"):
                bad.append(f"executed[{len(st.executed) + k}] {action.name}: output differs")
            if resp.done:
                reward, done = resp.reward, True
                info = _jnorm(resp.info.reward_info.model_dump()) if resp.info.reward_info else None
        if done:
            break
    if ep.get("done"):
        if not done:
            bad.append("the saved conversation ended, the replay did not")
        elif reward != ep.get("reward") or info != ep.get("reward_info"):
            bad.append(f"reward {reward} / reward_info differ from the saved {ep.get('reward')}")
    elif done:
        bad.append("the replay ended, the saved conversation did not")
    full = user_sim_messages(ep["executed"], st.extra["instruction"])
    if _jnorm(env.user.messages) != _jnorm(full):
        bad.append("user-simulator messages at the end differ from the full rebuilt list")
    return _check(not bad, "; ".join(bad[:3]) if bad else
                  f"{len(rest) // 2} more steps; reward {reward} (saved {ep.get('reward')})")


# ----------------------------------------------------------------------------------------------- many
def check_points(points: List[ForkPoint], off_cache: Optional[Dict[str, PT.OfflineGuards]] = None,
                 log: Callable[[str], None] = say) -> dict:
    cache = off_cache if off_cache is not None else {}

    def off_for(d: str) -> PT.OfflineGuards:
        if d not in cache:
            cache[d] = PT.OfflineGuards(d)
        return cache[d]

    venv = venv_available()
    t0 = time.time()
    results = [check_point(p, off_for, venv) for p in points]
    counts = {k: collections.Counter("passed" if r["checks"].get(k, {}).get("ok") is True else
                                     ("skipped" if r["checks"].get(k, {}).get("ok") is None else "failed")
                                     for r in results) for k in CHECKS}
    log(f"[rebuild_check] {len(results)} fork points, {sum(r['ok'] for r in results)} passed, venv checks "
        f"{'on' if venv else 'off'}; {time.time() - t0:.0f} s")
    for r in results:
        if not r["ok"]:
            log(f"[rebuild_check] DROPPED {r['fork_id']}: {r['reasons']}")
    return {"results": results, "venv": venv, "counts": counts, "network_attempts": len(NETWORK_ATTEMPTS)}


# ----------------------------------------------------------------------------------------------- report
def write_md(path: str, points: List[ForkPoint], checked: dict, rate_rows: Optional[List[dict]] = None,
             cross: Optional[dict] = None, sources: Optional[List[str]] = None) -> None:
    res = checked["results"]
    by_id = {p.fork_id: p for p in points}
    n_ok = sum(r["ok"] for r in res)
    L: List[str] = []
    w = L.append
    w("# Eval v2, Part 3: fork points and rebuild checks")
    w("")
    w(f"Date {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. Written by `fork/find_points.py` with "
      f"`fork/rebuild_check.py` (no LLM call; network blocked; writes only under `output/`). Sources: "
      f"{', '.join(sources or sorted({p.source for p in points}))}.")
    w("")
    w("## Short version")
    w(f"- **{len(points)} fork points found; {n_ok} pass every check; {len(res) - n_ok} dropped.**")
    kinds = collections.Counter((p.source, p.kind) for p in points)
    for s in sorted({p.source for p in points}):
        w(f"- {s}: {sum(v for (src, _), v in kinds.items() if src == s)} "
          f"(block removed {kinds[(s, 'block removed')]}, block added {kinds[(s, 'block added')]}).")
    w(f"- τ-bench env checks (venv): {'run' if checked['venv'] else 'not run (standard library Python)'}. "
      f"Network attempts blocked: {checked.get('network_attempts', 0)}.")
    if cross:
        for k, v in cross.items():
            w(f"- Cross-check `{k}`: {'same' if v.get('same') else ('NOT the same' if v.get('same') is False else 'not run')}.")
    w("")
    if rate_rows:
        w("## 1. Fork points per run (before the checks)")
        w("")
        w("A conversation has at most one fork point (its first differing attempt). Changed attempts: every attempt "
          "where the two guards differ (a blocked step tried again counts each try).")
        w("")
        w("| source | run | agent | domain | conversations | with a fork | block removed | block added | fork rate "
          "| changed attempts (removed / added) | checks not comparable | fork at a later try | kept |")
        w("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in rate_rows:
            kept = sum(1 for x in res if x["ok"] and (x["source"], x["run"], x["domain"]) == (r["source"], r["run"], r["domain"]))
            fr = "-" if r.get("fork_rate") is None else f"{100 * r['fork_rate']:.1f} %"
            w(f"| {r['source']} | {r['run']} | {r['agent']} | {r['domain']} | {r.get('conversations', 0)} "
              f"| {r.get('with fork', 0)} | {r.get('block removed', 0)} | {r.get('block added', 0)} | {fr} "
              f"| {r.get('changed attempts: block removed', 0)} / {r.get('changed attempts: block added', 0)} "
              f"| {r.get('checks not comparable', 0)} | {r.get('fork at a later try (attempt > 1)', 0)} | {kept} |")
        w("")
        skipped = {k: sum(r.get(k, 0) for r in rate_rows) for k in ("error lines", "later duplicate lines (first kept)",
                                                                       "skipped: models not gpt-6-luna / gpt-5-nano",
                                                                       "skipped: test group or no label",
                                                                       "skipped: other profile", "offline errors")}
        w("Lines left out: " + ", ".join(f"{k} {v}" for k, v in skipped.items()) + ".")
        w("")
        ne = sum(r.get("differences skipped: cap override, no effect", 0) for r in rate_rows)
        only = sum(r.get("conversations with only no-effect differences", 0) for r in rate_rows)
        miss = sum(r.get("frozen block message without judge evidence", 0) for r in rate_rows)
        w(f"Differences skipped because they have no effect (at a cap override, 4th try: both branches run the "
          f"action): {ne} (conversations with only such differences: {only}). Frozen TGR block messages without the "
          f"judge's evidence (fails the decision check): {miss}.")
        w("")
    w("## 2. Checks")
    w("")
    w("| check | what it compares | passed | failed | skipped |")
    w("|---|---|---|---|---|")
    for k in CHECKS:
        c = checked["counts"][k]
        w(f"| {k} | {CHECK_TEXT[k]} | {c['passed']} | {c['failed']} | {c['skipped']} |")
    w("")
    w("## 3. Dropped fork points")
    w("")
    dropped = [r for r in res if not r["ok"]]
    if not dropped:
        w("None: every fork point passed every check.")
    else:
        w("| fork id | reasons |")
        w("|---|---|")
        for r in dropped:
            w(f"| `{r['fork_id']}` | {'; '.join(r['reasons'])} |")
    w("")
    if cross:
        w("## 4. Cross-checks with the earlier parts")
        w("")
        p8 = cross.get("p8_changes_version_b")
        if p8:
            w(f"- **Part 8, version (b)** (`output/p8_changes.jsonl`): changed attempts in the partner's runs: ours "
              f"{p8['ours']}, Part 8 {p8['p8']}, in both {p8['common']}; only ours {len(p8['only_ours'])}, only Part 8 "
              f"{len(p8['only_p8'])}; other kind {len(p8['kind_differs'])}; other changed values "
              f"{len(p8['changed_values_differ'])}. Part 8's first changed attempt per conversation: "
              f"{p8['p8_conversations']} conversations ({', '.join(f'{k} {v}' for k, v in p8['p8_first_changes'].items())}).")
            for k in ("only_ours", "only_p8", "kind_differs", "changed_values_differ"):
                if p8[k]:
                    w(f"  - {k}: " + ", ".join(f"`{s}`" for s in p8[k][:20]))
        p10 = cross.get("p10_metrics_section_4")
        if p10 and p10.get("rows"):
            w(f"- **p10_metrics section 4** (`output/p10_metrics.json`): changed decisions in our p10 runs, ours "
              f"{p10['ours_total']}; same in every row: {p10['same']}.")
            w("")
            w("| tag | domain | p10_metrics removed / added | ours removed / added |")
            w("|---|---|---|---|")
            for r in p10["rows"]:
                w(f"| {r['tag']} | {r['domain']} | {r['p10_metrics']['block removed']} / {r['p10_metrics']['block added']} "
                  f"| {r['ours']['block removed']} / {r['ours']['block added']} |")
        w("")
    w("## 5. Notes on the fork points")
    w("")
    later = [p for p in points if p.attempt > 1]
    capf = [p for p in points if p.cap_override_at_fork]
    w(f"- Fork at a later try (attempt > 1: both guards blocked the earlier tries): {len(later)}"
      + (": " + ", ".join(f"`{p.fork_id}` (attempt {p.attempt})" for p in later) if later else "") + ".")
    w(f"- Fork at a 4th try (a block runs anyway through the cap override, so both branches run the action): "
      f"{len(capf)}" + (": " + ", ".join(f"`{p.fork_id}`" for p in capf) if capf else "") + ".")
    srcs = collections.Counter((p.feedback_a_source, p.feedback_b_source) for p in points)
    w("- Block messages (A, B): " + ", ".join(f"{a} / {b}: {n}" for (a, b), n in sorted(srcs.items(), key=str)) + ".")
    ev_missing = [p for p in points if p.feedback_a is not None and "missing" in p.judge_evidence_from.values()]
    ev_cache = [p for p in points if p.feedback_a is not None and "cache" in p.judge_evidence_from.values()]
    rebuilt_a = [p for p in points if p.feedback_a_source == "rebuilt"]
    w(f"- Rebuilt frozen-TGR block messages (tgr_tracker sources, A blocks): {len(rebuilt_a)}. The judge's own "
      f"evidence of the values the tracker changed is not in the guard record, so it is read from the run's judge "
      f"cache (the judge's full answer to the same prompt; read only): found for {len(ev_cache)}, missing for "
      f"{len(ev_missing)}" + (": " + ", ".join(f"`{p.fork_id}`" for p in ev_missing) if ev_missing else "") + ".")
    verd = collections.Counter(p.reviewer_verdict or "none" for p in points)
    w("- Reviewer verdict (Part 7 through Part 8, partner runs only): " + ", ".join(f"{k} {v}" for k, v in verd.items()) + ".")
    preds = collections.Counter(c["name"] for p in points for c in p.changed_predicates)
    w("- Changed predicates at the fork: " + ", ".join(f"`{k}` {v}" for k, v in preds.most_common()) + ".")
    w("")
    w("## Files")
    w("- Fork points (passing only): the `--out` file of `fork/find_points.py`; fork rates and the dropped list: the "
      "`--rates` file.")
    w("- Code: `fork/find_points.py`, `fork/points_tgr.py`, `fork/rebuild.py`, `fork/rebuild_tasks.py`, "
      "`fork/rebuild_check.py`; tests `tests/test_eval_v2_points.py`.")
    w("")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    _ = by_id


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--points", required=True)
    ap.add_argument("--md", default=None, help="write a report here (default: no report)")
    a = ap.parse_args(argv)
    safety_setup()
    from fork.find_points import read_points
    pts = read_points(a.points)
    checked = check_points(pts)
    if a.md:
        write_md(a.md, pts, checked)
        print("wrote", a.md)
    return 0 if all(r["ok"] for r in checked["results"]) else 1


if __name__ == "__main__":
    sys.exit(main())
