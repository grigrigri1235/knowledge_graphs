"""R1 (Part 4 audit, eval v2): an independent reference list of fork points for sources 1 and 2.

Written by R1 without reading fork/* or its outputs. No LLM call. Standard library only, plus the earlier audited
code: state_tracker (state replay, lookups, types, rule set to ASPM) and the copied decision code repro_runtime.mln.

Definition (docs/planning/tracker_eval_v2/p3.md, HANDOFF.md section 6)
  Per conversation (one line per (task, trial), error lines dropped), the fork is the first attempt, in the order of
  ep["attempts"], where frozen TGR (decision A) and TGR + tracker (decision B) decide differently. This is the first
  try of a retried action when the decisions already differ there, and a later try (attempt > 1) when both guards
  agree on the earlier tries.

  Source 1, saved_tgr (the partner's frozen TGR runs, from_shieldagent/runs/{luna_train_v5,nano_train}):
    A = the saved decision (recomputed from the judge's values; must equal the saved one);
    B = TGR's decision when each code-type predicate (output/predicate_types.json) takes the frozen lookup's value
        where it gives true or false (else the judge's value: Part 8 version b). The lookups run here, on the state
        replayed from executed[:executed_prefix_len], with the arguments of the message's tool call. As in
        guard/tgr_tracker.py: if the replay shows a mismatch, a parse problem or a problem, or a lookup raises, the
        judge's value is kept.
  Source 2, online_tracker (our tgr_tracker runs, output/online/{p10_luna_train,p10_nano_train,p10_luna_val}):
    B = the saved decision (recomputed from the values used; must equal the saved one);
    A = TGR's decision with guard.tracker.judge_values (the judge's own values).
    Extra check: our own lookups on our own replay give the guard's tracker values, and the used values equal the
    judge's values with them put in (version b).

  Decision: as method_tgr/runtime.py::_step: current = {action predicate: in matched} + values; allowed iff every
  matched action passes repro_runtime.mln.decide(aspm, circuit, a, current, past, 0.1, 16). No circuit: allowed with
  no judge (both guards agree).

Outputs (output/eval_v2/checks/ref/):
  ref_forks.jsonl           one line per fork (first differing attempt per conversation)
  ref_forks_changes.jsonl   one line per differing attempt (all of them; for the comparison with p8 / p10)
  ref_forks_rates.json      per run and domain: conversations, forks by kind, fork rate; checks; comparisons
  ref_forks.md              the report

Run from predicate_correctness/:
  PYTHONDONTWRITEBYTECODE=1 /home/azureuser/miniconda3/bin/python3 -B -m tests.audit_v2_ref_forks \
      > output/logs/v2_r1_run.log 2>&1
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

sys.dont_write_bytecode = True

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "tests"

from state_tracker import paths                                            # noqa: E402
from state_tracker import lookup_format as L                               # noqa: E402
from state_tracker.predicate_types import TYPES_JSON, is_code_type, load_types   # noqa: E402
from state_tracker.state import build_state                                # noqa: E402
from state_tracker.tgr_to_aspm import load_rule_set, to_aspm               # noqa: E402  (adds the code path)
from repro_runtime import mln                                              # noqa: E402  (copy)

PC = paths.PC_DIR
OUT_DIR = os.path.join(PC, "output", "eval_v2", "checks", "ref")
OUT_FORKS = os.path.join(OUT_DIR, "ref_forks.jsonl")
OUT_CHANGES = os.path.join(OUT_DIR, "ref_forks_changes.jsonl")
OUT_RATES = os.path.join(OUT_DIR, "ref_forks_rates.json")
OUT_MD = os.path.join(OUT_DIR, "ref_forks.md")

P8_CHANGES = os.path.join(PC, "output", "p8_changes.jsonl")
P10_METRICS = os.path.join(PC, "output", "p10_metrics.json")
PART1_CHECKS = os.path.join(PC, "output", "eval_v2", "checks", "part1_checks.json")

EPSILON = 0.1
GIBBS = 16
CAP = 3
TOL = 1e-9

# Frozen inputs (same values as guard/tgr_tracker.py FROZEN_SHA256; written here so that we do not import the guard).
FROZEN = {
    TYPES_JSON: "20dade34ca42965be3a3ae139749651b385b268de7d6bd4eb07ca12a21ee1889",
    L.lookups_path("airline"): "882ca35ed6a1bbda1ea97d1eed87dd36246b2111cc1d4d47c5645ce12b701dc7",
    L.lookups_path("retail"): "77918b7727831f8c18353f5b5dce89d7e05017aa4db11f31722ee23cc41044a4",
}

SOURCES = [  # (source, run, path template, saved guard name)
    ("saved_tgr", "luna_train_v5", "from_shieldagent/runs/luna_train_v5/{d}/tgr/episodes.jsonl", "tgr"),
    ("saved_tgr", "nano_train", "from_shieldagent/runs/nano_train/{d}/tgr/episodes.jsonl", "tgr"),
    ("online_tracker", "p10_luna_train", "output/online/p10_luna_train/{d}/tgr_tracker/episodes.jsonl", "tgr_tracker"),
    ("online_tracker", "p10_nano_train", "output/online/p10_nano_train/{d}/tgr_tracker/episodes.jsonl", "tgr_tracker"),
    ("online_tracker", "p10_luna_val", "output/online/p10_luna_val/{d}/tgr_tracker/episodes.jsonl", "tgr_tracker"),
]
AGENT = {"gpt-6-luna": "luna", "gpt-5-nano": "nano"}
RUN_AGENT = {"luna_train_v5": "luna", "nano_train": "nano", "p10_luna_train": "luna", "p10_nano_train": "nano",
             "p10_luna_val": "luna"}
DOMAINS = ("airline", "retail")
KINDS = ("block removed", "block added")


def sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def dec_name(allowed: Optional[bool]) -> Optional[str]:
    return None if allowed is None else ("allow" if allowed else "block")


def kind_of(a_allowed: bool, b_allowed: bool) -> Optional[str]:
    if a_allowed == b_allowed:
        return None
    return "block removed" if b_allowed else "block added"


# ----------------------------------------------------------------------------------------------- inputs

def load_conversations(path: str) -> Tuple[List[Tuple[int, dict]], dict]:
    """(line number, episode) for each (task, trial): error lines dropped; if a key repeats, the last good line wins."""
    keep: Dict[Tuple[int, int], Tuple[int, dict]] = {}
    st = collections.Counter()
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            ep = json.loads(line)
            st["lines"] += 1
            if ep.get("error") is not None:
                st["error lines dropped"] += 1
                continue
            if "trial" not in ep:
                raise ValueError(f"{path} line {i}: no trial key")
            key = (ep["task_index"], ep["trial"])
            if key in keep:
                st["repeated (task, trial): earlier line dropped"] += 1
            keep[key] = (i, ep)
    out = [keep[k] for k in sorted(keep)]
    st["conversations"] = len(out)
    return out, dict(st)


def load_splits() -> Dict[str, Dict[int, str]]:
    with open(paths.SPLITS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return {d: {int(k): v for k, v in data[d]["split"].items()} for d in DOMAINS}


def message_call(msg: dict) -> Tuple[str, str, dict, Optional[str]]:
    """(kind, name, arguments, raw arguments) of an agent message, as repro_online/guards.py::make_step reads it."""
    calls = msg.get("tool_calls") or []
    text = msg.get("content") or ""
    if calls and calls[0].get("function") is not None:
        fn = calls[0]["function"]
        raw = fn.get("arguments")
        if isinstance(raw, dict):
            args = raw
        else:
            try:
                out = json.loads(raw) if raw else {}
                args = out if isinstance(out, dict) else {"__value__": out}
            except (json.JSONDecodeError, TypeError):
                args = {"__unparsed__": raw}
        return "tool_call", fn.get("name"), args, raw if not isinstance(raw, dict) else json.dumps(raw)
    return "respond", "respond", {"content": text}, None


# ----------------------------------------------------------------------------------------------- decision

class Ctx:
    def __init__(self):
        self.aspm = {d: to_aspm(load_rule_set(d)) for d in DOMAINS}
        self.lookups = {d: L.load_lookups(d) for d in DOMAINS}
        types = load_types()
        self.code = {d: {n for n, e in types[d].items() if is_code_type(e["type"])} for d in DOMAINS}
        self.splits = load_splits()


def decide(aspm, g: dict, values: Dict[str, Optional[bool]], past: List[dict]) -> Tuple[bool, Optional[float]]:
    matched, circuit = g["matched"], g["circuit"]
    if not circuit:
        return True, None
    cur = {a: (a in matched) for a in aspm.action_predicates}
    cur.update(values)
    per = [mln.decide(aspm, circuit, a, cur, list(past), EPSILON, GIBBS) for a in matched]
    return all(d["allowed"] for d in per), min(d["margin"] for d in per)


def circuit_names(aspm, circuit: List[str]) -> List[str]:
    return sorted({n for r in circuit for n in aspm.rules[r].atoms} - aspm.action_predicates)


def my_tracker_values(ctx: Ctx, domain: str, state, args: dict, names: List[str]
                      ) -> Tuple[Dict[str, Optional[bool]], List[str]]:
    """Our lookup values for the code-type predicates among `names` (None = unknown or not usable)."""
    code = [n for n in names if n in ctx.code[domain]]
    if not code:
        return {}, []
    if isinstance(state, str):                       # the state could not be built, or is not clean
        return {n: None for n in code}, [state]
    out, errors = {}, []
    for n in code:
        lk = ctx.lookups[domain].get(n)
        if lk is None:
            out[n] = None
            errors.append(f"{n}: no lookup")
            continue
        try:
            out[n] = L.evaluate(lk, state, args=args)
        except Exception as e:  # noqa: BLE001 - as the guard: the judge's value is kept
            out[n] = None
            errors.append(f"{n}: {type(e).__name__}: {e}")
    return out, errors


def get_state(domain: str, history: List[dict], name: str, args: dict, cache: Dict[int, Any]):
    """The state before the attempt (cached per history length inside one conversation: retries share it).
    Returns the State, or an error text when the guard would not use it (mismatch, parse problem, problem)."""
    n = len(history)
    if n not in cache:
        try:
            st = build_state(history, {"tool": name, "args": args}, domain=domain)
            bad = []
            if st.mismatches:
                bad.append(f"{len(st.mismatches)} replay mismatch(es)")
            if st.parse_problems:
                bad.append(f"{len(st.parse_problems)} parse problem(s)")
            if st.problems:
                bad.append("; ".join(st.problems[:3]))
            cache[n] = ("state: " + "; ".join(bad)) if bad else st
        except Exception as e:  # noqa: BLE001
            cache[n] = f"state: {type(e).__name__}: {e}"
    return cache[n]


# ----------------------------------------------------------------------------------------------- one conversation

def process_conversation(ctx: Ctx, source: str, run: str, domain: str, line_no: int, ep: dict,
                         checks: collections.Counter, notes: List[str]) -> dict:
    aspm = ctx.aspm[domain]
    key = f"{source}/{run}/{domain}/task{ep['task_index']}/trial{ep['trial']}"

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks[name + (" ok" if ok else " FAILED")] += 1
        if not ok and len(notes) < 200:
            notes.append(f"{key}: {name} FAILED {detail}")

    msgs, executed, attempts = ep["messages"], ep["executed"], ep["attempts"]
    check("len(messages) = 2 + 2 x len(attempts)", len(msgs) == 2 + 2 * len(attempts))
    past: List[dict] = []
    consecutive = 0
    cache: Dict[int, Any] = {}
    diffs: List[dict] = []
    n_judged = 0
    skipped_before: List[int] = []
    first_idx, first_call = 0, None
    for i, att in enumerate(attempts):
        g = att.get("guard")
        msg = msgs[2 + 2 * i]
        kind, name, args, raw = message_call(msg)
        if att["attempt"] == 1:
            first_idx, first_call = i, (name, args)
        check("messages[2+2i] is the attempt's agent message", msg.get("role") == "assistant" and name == att["action"],
              f"attempt {i}: {name} vs {att['action']}")
        check("executed_prefix_len = 2 + 2 x exec_step", att["executed_prefix_len"] == 2 + 2 * att["exec_step"])
        check("attempt = 1 + blocks in a row", att["attempt"] == consecutive + 1, f"attempt {i}")
        if kind == "tool_call":
            checks["kwargs equal the message arguments" if att["kwargs"] == args
                   else "kwargs differ from the message arguments (info)"] += 1
        if not att["blocked"]:
            p = att["executed_prefix_len"]
            check("executed attempt is in executed[prefix:prefix+2]", executed[p] == msg and executed[p + 1] == msgs[3 + 2 * i],
                  f"attempt {i}")
        if g is None:
            checks["attempt without a guard record (info)"] += 1
            blocked_by_guard = False
        else:
            check("trace_len_before = exec_step = past trace length",
                  g["trace_len_before"] == att["exec_step"] == len(past), f"attempt {i}")
            blocked_by_guard = not g["action_allowed"]
        check("cap_override iff guard blocked with 3 blocks in a row",
              att["cap_override"] == (blocked_by_guard and consecutive >= CAP), f"attempt {i}")
        check("blocked = guard blocked and no cap override",
              att["blocked"] == (blocked_by_guard and consecutive < CAP), f"attempt {i}")

        if g is not None and g.get("circuit"):
            n_judged += 1
            names = circuit_names(aspm, g["circuit"])
            check("judge keys = predicates of the circuit's rules", sorted(g.get("judge") or {}) == names, f"attempt {i}")
            saved = g["action_allowed"]
            history = executed[:att["executed_prefix_len"]]
            state = get_state(domain, history, name, args, cache)
            tv, errs = my_tracker_values(ctx, domain, state, args, names)
            if errs:
                checks["attempts where our tracker kept the judge's value because of an error (info)"] += 1
                if len(notes) < 200:
                    notes.append(f"{key} attempt {i}: tracker errors {errs[:2]}")
            judge_saved = {n: (g["judge"].get(n) or {}).get("value") for n in names}
            if source == "saved_tgr":
                a_vals = judge_saved
                b_vals = dict(a_vals)
                for n, t in tv.items():
                    if t is not None:
                        b_vals[n] = t
                a_allowed, a_margin = decide(aspm, g, a_vals, past)
                check("saved decision recomputed (allow/block)", a_allowed == saved, f"attempt {i}")
                check("saved margin recomputed", g["margin"] is not None and abs(a_margin - g["margin"]) <= TOL,
                      f"attempt {i}")
                e_allowed, e_margin = decide(aspm, g, a_vals, [])
                check("empty past trace gives the same decision", e_allowed == a_allowed and e_margin == a_margin)
                b_allowed, b_margin = (decide(aspm, g, b_vals, past) if b_vals != a_vals else (a_allowed, a_margin))
                tracker_rec = None
            else:
                tr = g.get("tracker") or {}
                check("tracker part applied on a judged check", bool(tr.get("applied")), f"attempt {i}")
                b_vals = judge_saved                     # the values used (judge or tracker)
                b_allowed, b_margin = decide(aspm, g, b_vals, past)
                check("saved decision recomputed (allow/block)", b_allowed == saved, f"attempt {i}")
                check("saved margin recomputed", g["margin"] is not None and abs(b_margin - g["margin"]) <= TOL,
                      f"attempt {i}")
                e_allowed, e_margin = decide(aspm, g, b_vals, [])
                check("empty past trace gives the same decision", e_allowed == b_allowed and e_margin == b_margin)
                jv = tr.get("judge_values")
                # our own tracker against the guard's tracker
                gtv = tr.get("tracker_values") or {}
                check("code predicates = guard's code_predicates",
                      sorted(tv) == sorted(tr.get("code_predicates") or []), f"attempt {i}")
                for n, t in tv.items():
                    gv = gtv.get(n) or {}
                    check("our lookup value = guard's tracker value", (gv.get("value") is t) and not gv.get("error"),
                          f"attempt {i} {n}: ours {t} guard {gv}")
                if jv is None:
                    checks["judge skipped: frozen TGR decision unknown"] += 1
                    skipped_before.append(i)
                    a_allowed, a_margin = None, None
                else:
                    expect = dict(jv)
                    for n, t in tv.items():
                        if t is not None:
                            expect[n] = t
                    check("used values = judge values with our tracker values (version b)", expect == b_vals,
                          f"attempt {i}")
                    changed = sorted(n for n in names if b_vals.get(n) is not jv.get(n))
                    check("guard's tracker.changed = predicates where used != judge",
                          sorted(tr.get("changed") or []) == changed, f"attempt {i}")
                    if tr.get("changed"):
                        checks["checks where the tracker changed a value (info)"] += 1
                    a_vals = jv
                    a_allowed, a_margin = decide(aspm, g, a_vals, past)
                tracker_rec = {"changed": tr.get("changed"), "judge_skipped": tr.get("judge_skipped")}
            if a_allowed is not None:
                k = kind_of(a_allowed, b_allowed)
                if k:
                    a_vals_ = a_vals
                    changed = sorted(n for n in names if b_vals.get(n) is not a_vals_.get(n))
                    alone = [n for n in changed
                             if decide(aspm, g, dict(a_vals_, **{n: b_vals.get(n)}), past)[0] != a_allowed]
                    diffs.append({
                        "attempt_index": i, "exec_step": att["exec_step"], "attempt": att["attempt"],
                        "action": att["action"], "action_kind": kind, "arguments": args, "arguments_raw": raw,
                        "kwargs_equal_arguments": (att["kwargs"] == args) if kind == "tool_call" else None,
                        "decision_a": dec_name(a_allowed), "decision_b": dec_name(b_allowed),
                        "margin_a": a_margin, "margin_b": b_margin, "kind": k,
                        "changed_predicates": [{"name": n, "judge": a_vals_.get(n), "tracker": b_vals.get(n)}
                                               for n in changed],
                        "flips_alone": alone,
                        "saved_allowed": saved, "saved_blocked": att["blocked"],
                        "saved_cap_override": att["cap_override"],
                        "no_effect": att["attempt"] > CAP,          # the blocking side runs it anyway (cap override)
                        "step_first_attempt_index": first_idx,      # try 1 of this exec_step
                        "step_first_action": attempts[first_idx]["action"],
                        "same_call_as_step_first_try": (name, args) == first_call,
                        "judge_skipped_before": list(skipped_before),
                        "tracker_record": tracker_rec,
                    })
        # bookkeeping as run_episode
        if not att["blocked"]:
            past.append((g or {}).get("trace_position"))
            consecutive = 0
        else:
            consecutive += 1
    label = ctx.splits[domain].get(ep["task_index"])
    agent = AGENT.get((ep.get("models") or {}).get("agent"))
    return {"key": key, "source": source, "run": run, "domain": domain, "agent": agent, "profile": ep.get("profile"),
            "agent_model": (ep.get("models") or {}).get("agent"), "task_index": ep["task_index"], "trial": ep["trial"],
            "split_label": label, "episode_line": line_no, "n_attempts": len(attempts), "n_judged": n_judged,
            "reward": ep.get("reward"), "diffs": diffs}


# ----------------------------------------------------------------------------------------------- main pass

def run_all(ctx: Ctx) -> Tuple[List[dict], dict, collections.Counter, List[str]]:
    convs: List[dict] = []
    load_stats: dict = {}
    checks: collections.Counter = collections.Counter()
    notes: List[str] = []
    for source, run, tmpl, gname in SOURCES:
        for d in DOMAINS:
            path = os.path.join(PC, tmpl.format(d=d))
            t0 = time.time()
            eps, st = load_conversations(path)
            load_stats[f"{run}/{d}"] = dict(st, path=os.path.relpath(path, PC), sha256=sha256(path))
            for line_no, ep in eps:
                if ep.get("guard") != gname or ep.get("env") != d:
                    raise ValueError(f"{path}: guard {ep.get('guard')} env {ep.get('env')}")
                if ep["task_index"] in ctx.splits[d] and ctx.splits[d][ep["task_index"]] == "test":
                    raise ValueError(f"{path}: task {ep['task_index']} is in the partner's test group")
                c = process_conversation(ctx, source, run, d, line_no, ep, checks, notes)
                if c["agent"] != RUN_AGENT[run]:
                    raise ValueError(f"{c['key']}: agent {c['agent_model']} not {RUN_AGENT[run]}")
                convs.append(c)
            print(f"{run}/{d}: {len(eps)} conversations, {time.time() - t0:.1f} s", flush=True)
    return convs, load_stats, checks, notes


def fork_line(c: dict) -> dict:
    f = c["diffs"][0]
    return {"id": f"{c['key']}/att{f['attempt_index']}", "source": c["source"], "run": c["run"],
            "domain": c["domain"], "agent": c["agent"], "agent_model": c["agent_model"], "profile": c["profile"],
            "task_index": c["task_index"], "trial": c["trial"], "split_label": c["split_label"],
            "episode_line": c["episode_line"], **{k: v for k, v in f.items()},
            "n_attempts": c["n_attempts"], "n_changed_attempts_in_conversation": len(c["diffs"]),
            "kinds_in_conversation": sorted({x["kind"] for x in c["diffs"]}),
            "later_effective_difference": next((x["attempt_index"] for x in c["diffs"] if not x["no_effect"]), None)
            if f["no_effect"] else None,
            "reward": c["reward"]}


def change_line(c: dict, x: dict) -> dict:
    return {"id": f"{c['key']}/att{x['attempt_index']}", "source": c["source"], "run": c["run"],
            "domain": c["domain"], "agent": c["agent"], "task_index": c["task_index"], "trial": c["trial"],
            **{k: x[k] for k in ("attempt_index", "exec_step", "attempt", "action", "decision_a", "decision_b",
                                 "kind", "changed_predicates", "flips_alone", "saved_blocked", "saved_cap_override",
                                 "no_effect")}}


# ----------------------------------------------------------------------------------------------- rates

def rates(convs: List[dict]) -> dict:
    groups: Dict[str, List[dict]] = collections.defaultdict(list)
    for c in convs:
        for k in (f"{c['source']}|{c['run']}|{c['domain']}", f"{c['source']}|{c['run']}|both",
                  f"{c['source']}|agent {c['agent']}|both", f"{c['source']}|all|both",
                  f"all|agent {c['agent']}|both", "all|all|both",
                  f"{c['source']}|agent {c['agent']}|{c['domain']}"):
            groups[k].append(c)
    out = {}
    for k, cs in groups.items():
        n = len(cs)
        withf = [c for c in cs if c["diffs"]]
        by = collections.Counter(c["diffs"][0]["kind"] for c in withf)
        noeff = sum(1 for c in withf if c["diffs"][0]["no_effect"])
        ch = collections.Counter(x["kind"] for c in cs for x in c["diffs"])
        steps = collections.Counter()
        for kind in KINDS:
            steps[kind] = len({(c["key"], x["exec_step"]) for c in cs for x in c["diffs"] if x["kind"] == kind})
        out[k] = {"conversations": n, "conversations_with_fork": len(withf),
                  "fork_block_removed": by["block removed"], "fork_block_added": by["block added"],
                  "fork_rate": round(len(withf) / n, 4) if n else None,
                  "forks_without_effect": noeff,
                  "changed_attempts_block_removed": ch["block removed"], "changed_attempts_block_added": ch["block added"],
                  "changed_steps_block_removed": steps["block removed"], "changed_steps_block_added": steps["block added"],
                  "conversations_with_both_kinds": sum(1 for c in withf if len({x['kind'] for x in c['diffs']}) == 2),
                  "attempts": sum(c["n_attempts"] for c in cs), "judged_attempts": sum(c["n_judged"] for c in cs)}
    return out


# ----------------------------------------------------------------------------------------------- comparisons

def v2name(v: Any) -> str:
    return {True: "true", False: "false", None: "unknown"}.get(v, str(v))


def compare_p8(convs: List[dict]) -> dict:
    """Source 1 against output/p8_changes.jsonl (version b)."""
    p8 = {}
    with open(P8_CHANGES, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            b = r["b"]
            if not b.get("change"):
                continue
            key = (r["run"], r["domain"], r["task"], r["trial"], r["exec_step"], r["attempt"])
            p8[key] = {"kind": b["change"],
                       "values": {n: (x["judge"], x["tracker"]) for n, x in (b.get("values") or {}).items()}}
    mine = {}
    for c in convs:
        if c["source"] != "saved_tgr":
            continue
        for x in c["diffs"]:
            key = (c["run"], c["domain"], c["task_index"], c["trial"], x["exec_step"], x["attempt"])
            mine[key] = {"kind": x["kind"], "values": {p["name"]: (v2name(p["judge"]), v2name(p["tracker"]))
                                                       for p in x["changed_predicates"]}}
    both = sorted(set(p8) & set(mine))
    res = {"p8_changed_records": len(p8), "our_changed_attempts": len(mine), "in_both": len(both),
           "only_p8": [list(k) for k in sorted(set(p8) - set(mine))],
           "only_ours": [list(k) for k in sorted(set(mine) - set(p8))],
           "kind_differs": [list(k) for k in both if p8[k]["kind"] != mine[k]["kind"]],
           "values_differ": [list(k) for k in both if p8[k]["values"] != mine[k]["values"]],
           "p8_by_kind": dict(collections.Counter(v["kind"] for v in p8.values())),
           "ours_by_kind": dict(collections.Counter(v["kind"] for v in mine.values()))}
    for name, src in (("p8", p8), ("ours", mine)):
        res[f"{name}_distinct_steps"] = {k: len({key[:5] for key, v in src.items() if v["kind"] == k}) for k in KINDS}
        res[f"{name}_conversations"] = len({key[:4] for key in src})
    # first change per conversation (attempt order = (exec_step, attempt))
    first_p8: Dict[tuple, tuple] = {}
    for key in sorted(p8):
        first_p8.setdefault(key[:4], (key[4], key[5], p8[key]["kind"]))
    first_mine = {}
    for c in convs:
        if c["source"] == "saved_tgr" and c["diffs"]:
            x = c["diffs"][0]
            first_mine[(c["run"], c["domain"], c["task_index"], c["trial"])] = (x["exec_step"], x["attempt"], x["kind"])
    res["p8_first_change_conversations"] = len(first_p8)
    res["our_fork_conversations"] = len(first_mine)
    res["fork_same_attempt_and_kind"] = sum(1 for k in first_mine if first_p8.get(k) == first_mine[k])
    res["fork_differs"] = [{"conversation": list(k), "p8": first_p8.get(k), "ours": first_mine.get(k)}
                           for k in sorted(set(first_p8) | set(first_mine)) if first_p8.get(k) != first_mine.get(k)]
    return res


def compare_p10(convs: List[dict], checks: collections.Counter) -> dict:
    """Source 2 against output/p10_metrics.json (section 4 of output/p10_metrics.md)."""
    with open(P10_METRICS, encoding="utf-8") as f:
        m = json.load(f)
    tag_of = {exp: v["our_tag"] for exp, v in m["inputs"].items()}
    res = {"per_run_domain": {}, "examples_checked": 0, "examples_missing_in_ours": [], "examples_differ": []}
    ours_by = collections.defaultdict(collections.Counter)
    ours_att = {}
    for c in convs:
        if c["source"] != "online_tracker":
            continue
        for x in c["diffs"]:
            ours_by[(c["run"], c["domain"])][x["kind"]] += 1
            ours_att[(c["run"], c["domain"], c["task_index"], c["trial"], x["attempt_index"])] = x
    tot_p10, tot_ours = collections.Counter(), collections.Counter()
    for exp, r in m["experiments"].items():
        tag = tag_of[exp]
        for d in DOMAINS:
            t = r["tracker"][d]
            cnt = t["counts"]
            p10 = {k: cnt.get(k, 0) for k in KINDS}
            ours = {k: ours_by[(tag, d)][k] for k in KINDS}
            res["per_run_domain"][f"{tag}/{d}"] = {"p10": p10, "ours": ours, "equal": p10 == ours,
                                                   "p10_checks_with_judge": cnt.get("decision with the used values = saved", 0),
                                                   "p10_checks_tracker_changed_a_value":
                                                       cnt.get("checks where the tracker changed a value", 0)}
            tot_p10.update(p10)
            tot_ours.update(ours)
            for ex in t["examples"]:
                res["examples_checked"] += 1
                x = ours_att.get((tag, d, ex["task"], ex["trial"], ex["attempt"]))
                if x is None:
                    res["examples_missing_in_ours"].append([tag, d, ex["task"], ex["trial"], ex["attempt"]])
                    continue
                mine = {"action": x["action"], "change": x["kind"],
                        "predicates": [p["name"] for p in x["changed_predicates"]],
                        "judge": {p["name"]: p["judge"] for p in x["changed_predicates"]},
                        "tracker": {p["name"]: p["tracker"] for p in x["changed_predicates"]}}
                theirs = {k: ex[k] for k in ("action", "change", "predicates", "judge", "tracker")}
                if mine != theirs:
                    res["examples_differ"].append({"key": [tag, d, ex["task"], ex["trial"], ex["attempt"]],
                                                   "p10": theirs, "ours": mine})
    res["total_p10"] = dict(tot_p10)
    res["total_ours"] = dict(tot_ours)
    res["p10_checks_with_judge_total"] = sum(v["p10_checks_with_judge"] for v in res["per_run_domain"].values())
    res["p10_checks_tracker_changed_total"] = sum(v["p10_checks_tracker_changed_a_value"]
                                                  for v in res["per_run_domain"].values())
    return res


def compare_part1(convs: List[dict]) -> dict:
    """Both sources against Part 1's list of 55 known fork points (part1_checks.json, forks.forks)."""
    with open(PART1_CHECKS, encoding="utf-8") as f:
        p1 = json.load(f)["forks"]["forks"]
    theirs = {(x["tag"], x["domain"], x["task"], x["trial"]): (x["attempt_index"], x["kind"]) for x in p1}
    mine = {(c["run"], c["domain"], c["task_index"], c["trial"]): (c["diffs"][0]["attempt_index"], c["diffs"][0]["kind"])
            for c in convs if c["diffs"]}
    return {"part1_forks": len(theirs), "our_forks": len(mine),
            "part1_by_source": dict(collections.Counter(x["source"] for x in p1)),
            "same_attempt_and_kind": sum(1 for k in mine if theirs.get(k) == mine[k]),
            "differ": [{"conversation": list(k), "part1": theirs.get(k), "ours": mine.get(k)}
                       for k in sorted(set(theirs) | set(mine)) if theirs.get(k) != mine.get(k)]}


# ----------------------------------------------------------------------------------------------- report

def pct(x: Optional[float]) -> str:
    return "-" if x is None else f"{100 * x:.1f} %"


def write_md(res: dict, forks: List[dict]) -> None:
    R = res["rates"]
    L_: List[str] = []
    w = L_.append
    w("# R1 reference: fork points for sources 1 and 2 (Part 4 audit)")
    w("")
    w(f"Written by `tests/audit_v2_ref_forks.py` (R1, independent of `fork/`; no LLM). Date {res['date']}. "
      f"Run time {res['seconds']:.0f} s.")
    w("")
    w("## What")
    w("- **Fork** = per conversation, the first attempt (order of `ep[\"attempts\"]`) where frozen TGR (A) and "
      "TGR + tracker (B) decide differently. One line per (task, trial); error lines dropped (there were none).")
    w("- **Source 1, saved_tgr** (partner frozen TGR): A = saved decision; B = TGR's formula with the code-type values "
      "from our own run of the frozen lookups, where they give true/false (Part 8 version b). State = replay of "
      "`executed[:executed_prefix_len]`; arguments from the message's tool call.")
    w("- **Source 2, online_tracker** (our tgr_tracker runs): B = saved decision; A = TGR's formula with "
      "`guard.tracker.judge_values`.")
    w("- **kind**: \"block removed\" = A blocks, B allows; \"block added\" = A allows, B blocks.")
    w("- **no effect**: the fork attempt is attempt 4 (3 blocks in a row before). The side that blocks runs the "
      "action anyway (cap override), so both branches do the same thing.")
    w("")
    w("## Checks (all on every attempt)")
    w("")
    w("| check | ok | failed |")
    w("|---|---|---|")
    names = sorted({k.rsplit(" ", 1)[0] for k in res["checks"] if k.endswith(" ok") or k.endswith(" FAILED")})
    for n in names:
        w(f"| {n} | {res['checks'].get(n + ' ok', 0):,} | {res['checks'].get(n + ' FAILED', 0):,} |")
    info = {k: v for k, v in res["checks"].items() if not (k.endswith(" ok") or k.endswith(" FAILED"))}
    w("")
    w("Info counts: " + "; ".join(f"{k}: {v:,}" for k, v in sorted(info.items())) + ".")
    w("")
    w("Frozen inputs: sha256 of the types and lookup files equal the frozen values: "
      f"{'yes' if res['frozen_ok'] else 'NO'}. Test-group tasks: 0 (the script stops on one).")
    w("")
    w("## Fork counts and rates")
    w("")
    w("| source | run | domain | conversations | with a fork | block removed | block added | fork rate | "
      "no effect |")
    w("|---|---|---|---|---|---|---|---|---|")
    order = []
    for source, run, _, _ in SOURCES:
        for d in (*DOMAINS, "both"):
            order.append(f"{source}|{run}|{d}")
    for source in ("saved_tgr", "online_tracker"):
        for a in ("luna", "nano"):
            for d in (*DOMAINS, "both"):
                order.append(f"{source}|agent {a}|{d}")
        order.append(f"{source}|all|both")
    for a in ("luna", "nano"):
        order.append(f"all|agent {a}|both")
    order.append("all|all|both")
    for k in order:
        if k not in R:
            continue
        r = R[k]
        s, run, d = k.split("|")
        bold = "**" if run in ("all",) or run.startswith("agent") else ""
        w(f"| {s} | {bold}{run}{bold} | {d} | {r['conversations']} | {r['conversations_with_fork']} | "
          f"{r['fork_block_removed']} | {r['fork_block_added']} | {pct(r['fork_rate'])} | {r['forks_without_effect']} |")
    w("")
    w("All changed attempts (not only the first per conversation):")
    w("")
    w("| source | run | domain | changed attempts: removed / added | distinct steps: removed / added | "
      "conversations with both kinds |")
    w("|---|---|---|---|---|---|")
    for source, run, _, _ in SOURCES:
        for d in (*DOMAINS, "both"):
            r = R.get(f"{source}|{run}|{d}")
            if r:
                w(f"| {source} | {run} | {d} | {r['changed_attempts_block_removed']} / {r['changed_attempts_block_added']} | "
                  f"{r['changed_steps_block_removed']} / {r['changed_steps_block_added']} | "
                  f"{r['conversations_with_both_kinds']} |")
    w("")
    # p8
    p = res["compare_p8"]
    w("## Comparison with `output/p8_changes.jsonl` (source 1)")
    w("")
    w(f"- Changed records: p8 {p['p8_changed_records']} ({p['p8_by_kind']}), ours {p['our_changed_attempts']} "
      f"({p['ours_by_kind']}); in both {p['in_both']}; only p8 {len(p['only_p8'])}; only ours {len(p['only_ours'])}; "
      f"kind differs {len(p['kind_differs'])}; changed values differ {len(p['values_differ'])}.")
    w(f"- Distinct steps (task, trial, step): p8 {p['p8_distinct_steps']}, ours {p['ours_distinct_steps']}.")
    w(f"- Conversations with a change: p8 {p['p8_conversations']}, ours {p['ours_conversations']}.")
    w(f"- Fork (first change per conversation): same attempt and kind in {p['fork_same_attempt_and_kind']} of "
      f"{p['our_fork_conversations']} (p8 gives {p['p8_first_change_conversations']}); differences "
      f"{len(p['fork_differs'])}.")
    for x in p["only_p8"] + p["only_ours"] + p["kind_differs"] + p["values_differ"]:
        w(f"  - difference: {x}")
    for x in p["fork_differs"]:
        w(f"  - fork difference: {x}")
    w("")
    # p10
    q = res["compare_p10"]
    w("## Comparison with `scoring/p10_metrics.py` section 4 (source 2)")
    w("")
    w("| run / domain | p10: removed / added | ours: removed / added | equal | p10 checks with a judge call | "
      "p10 checks where the tracker changed a value |")
    w("|---|---|---|---|---|---|")
    for k, v in q["per_run_domain"].items():
        w(f"| {k} | {v['p10']['block removed']} / {v['p10']['block added']} | {v['ours']['block removed']} / "
          f"{v['ours']['block added']} | {'yes' if v['equal'] else 'NO'} | {v['p10_checks_with_judge']:,} | "
          f"{v['p10_checks_tracker_changed_a_value']} |")
    w(f"| **all** | {q['total_p10'].get('block removed', 0)} / {q['total_p10'].get('block added', 0)} | "
      f"{q['total_ours'].get('block removed', 0)} / {q['total_ours'].get('block added', 0)} | "
      f"{'yes' if q['total_p10'] == q['total_ours'] else 'NO'} | {q['p10_checks_with_judge_total']:,} | "
      f"{q['p10_checks_tracker_changed_total']} |")
    w("")
    w(f"Ours: judged checks in source 2 {res['source2_judged']:,}; checks where the guard's tracker changed a value "
      f"{res['checks'].get('checks where the tracker changed a value (info)', 0)}.")
    w("")
    w(f"p10's saved examples (the first 40 per run/domain, with task, trial, attempt index, predicates and values): "
      f"{q['examples_checked']} checked, {len(q['examples_missing_in_ours'])} missing in ours, "
      f"{len(q['examples_differ'])} differ.")
    for x in q["examples_missing_in_ours"] + q["examples_differ"]:
        w(f"  - {x}")
    w("")
    # part 1
    c1 = res["compare_part1"]
    w("## Comparison with Part 1's list of known forks (`part1_checks.json`, forks)")
    w("")
    w(f"Part 1 {c1['part1_forks']} forks, ours {c1['our_forks']}; same attempt and kind {c1['same_attempt_and_kind']}; "
      f"differences {len(c1['differ'])}.")
    for x in c1["differ"]:
        w(f"  - {x}")
    w("")
    w("## Explanation of the differences")
    w("")
    for line in res["explanations"]:
        w(f"- {line}")
    w("")
    w("## Edge cases and how R1 decided them")
    w("")
    for line in res["edge_cases"]:
        w(f"- {line}")
    w("")
    w("## The forks")
    w("")
    w("`att` = index into `ep[\"attempts\"]`; `step/try` = exec_step / attempt; A = frozen TGR, B = TGR + tracker; "
      "saved = what the saved run did (blocked, cap override, or ran). Predicates: judge -> tracker (null = unknown).")
    w("")
    w("| source | run | domain | task | trial | att | step/try | action | A | B | kind | changed predicates | saved | "
      "no effect |")
    w("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for f in forks:
        cp = ", ".join(f"`{p['name']}` {v2name(p['judge'])}->{v2name(p['tracker'])}" for p in f["changed_predicates"])
        saved = "blocked" if f["saved_blocked"] else ("cap override" if f["saved_cap_override"] else "ran")
        w(f"| {f['source']} | {f['run']} | {f['domain']} | {f['task_index']} | {f['trial']} | {f['attempt_index']} | "
          f"{f['exec_step']}/{f['attempt']} | `{f['action']}` | {f['decision_a']} | {f['decision_b']} | {f['kind']} | "
          f"{cp} | {saved} | {'yes' if f['no_effect'] else ''} |")
    w("")
    w("## Files")
    w("- `output/eval_v2/checks/ref/ref_forks.jsonl`: one line per fork (fields above, plus arguments, margins, "
      "`flips_alone`, `n_changed_attempts_in_conversation`, `split_label`, `episode_line`).")
    w("- `output/eval_v2/checks/ref/ref_forks_changes.jsonl`: every attempt where A and B differ.")
    w("- `output/eval_v2/checks/ref/ref_forks_rates.json`: rates, checks, comparisons, input sha256.")
    w("- Code: `tests/audit_v2_ref_forks.py`. Logs: `output/logs/v2_r1_run2.log` (this run), "
      "`output/logs/v2_r1_run.log` (first run, same numbers; it stopped at a typo in the report code).")
    w("")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L_))


def explanations(res: dict, convs: List[dict]) -> Tuple[List[str], List[str]]:
    p, q, c1 = res["compare_p8"], res["compare_p10"], res["compare_part1"]
    ex: List[str] = []
    if not (p["only_p8"] or p["only_ours"] or p["kind_differs"] or p["values_differ"]):
        ex.append(f"p8: every changed record is the same in both lists ({p['in_both']} records, same kind and same "
                  "changed values).")
    if not p["fork_differs"]:
        ex.append(f"p8: the first change per conversation is our fork in all {p['our_fork_conversations']} "
                  "conversations.")
    if q["total_p10"] == q["total_ours"] and all(v["equal"] for v in q["per_run_domain"].values()):
        ex.append(f"p10: the counts of changed decisions are equal in every run and domain "
                  f"({sum(q['total_ours'].values())} in all).")
    if not (q["examples_missing_in_ours"] or q["examples_differ"]):
        ex.append(f"p10: all {q['examples_checked']} saved examples are in our list with the same action, kind, "
                  "predicates and values.")
    n_forks2 = res["rates"]["online_tracker|all|both"]["conversations_with_fork"]
    n_ch2 = sum(q["total_ours"].values())
    ex.append(f"Why the numbers are smaller than \"77 changed decisions\" / \"30 + 28 steps\": a fork is one per "
              f"conversation. Source 2 has {n_ch2} changed attempts in {n_forks2} conversations; retries of the same "
              "step and later steps of the same conversation are not forks.")
    n1 = res["rates"]["saved_tgr|all|both"]
    ex.append(f"Source 1 has {n1['changed_attempts_block_removed'] + n1['changed_attempts_block_added']} changed "
              f"attempts ({n1['changed_attempts_block_removed']} removed, {n1['changed_attempts_block_added']} added), "
              f"{n1['changed_steps_block_removed']} + {n1['changed_steps_block_added']} distinct steps, in "
              f"{n1['conversations_with_fork']} conversations (the plan says \"about 33\"; Part 1 counted "
              f"{c1['part1_by_source'].get('partner frozen TGR', 0)} for source 1 and "
              f"{c1['part1_by_source'].get('our TGR + tracker', 0)} for source 2).")
    if c1["differ"]:
        ex.append("Part 1: see the differences listed above.")
    else:
        ex.append(f"Part 1: all {c1['part1_forks']} forks equal ours (attempt index and kind).")
    edge: List[str] = []
    noeff = [c for c in convs if c["diffs"] and c["diffs"][0]["no_effect"]]
    edge.append(f"Fork at attempt 4 (cap override; no effect on the conversation): {len(noeff)} conversation(s)"
                + (": " + ", ".join(f"`{c['key']}` att {c['diffs'][0]['attempt_index']}" for c in noeff) if noeff else "")
                + ". Kept in the list by the strict definition, with `no_effect: true` and the next difference with an "
                  "effect in `later_effective_difference`.")
    both_kinds = [c for c in convs if c["diffs"] and len({x["kind"] for x in c["diffs"]}) == 2]
    edge.append(f"Conversations with both kinds of change: {len(both_kinds)}. The fork's kind is the kind of the first "
                "difference.")
    later_try = [c for c in convs if c["diffs"] and c["diffs"][0]["attempt"] > 1]
    edge.append(f"Forks at a later try (attempt > 1, both guards blocked the earlier tries): {len(later_try)}"
                + (": " + ", ".join(f"`{c['key']}` att {c['diffs'][0]['attempt_index']} (try "
                                    f"{c['diffs'][0]['attempt']}, `{c['diffs'][0]['action']}`; try 1 at att "
                                    f"{c['diffs'][0]['step_first_attempt_index']} was "
                                    f"`{c['diffs'][0]['step_first_action']}`"
                                    f"{', same call' if c['diffs'][0]['same_call_as_step_first_try'] else ''})"
                                    for c in later_try) if later_try else "") + ".")
    n_other = sum(1 for c in later_try if not c["diffs"][0]["same_call_as_step_first_try"])
    edge.append(f"Of these {len(later_try)}, {n_other} are a different call from try 1 of the step: `attempt` counts "
                "blocks in a row at an exec_step, not tries of the same call. The agent changed its action after a "
                "block that both guards made. Moving such a fork back to try 1 would put it where A and B agree. "
                "R1 keeps the first attempt that really differs.")
    retried = [c for c in convs if c["diffs"] and any(x["exec_step"] == c["diffs"][0]["exec_step"]
                                                       for x in c["diffs"][1:])]
    edge.append(f"Forks whose step has more differing tries after the fork (a retried blocked action; the fork is "
                f"the first try that differs): {len(retried)}.")
    respond = [c for c in convs if c["diffs"] and c["diffs"][0]["action"] == "respond"]
    edge.append(f"Forks on a reply to the user (action `respond`; arguments = {{\"content\": text}}): {len(respond)}.")
    kw = [c for c in convs if c["diffs"] and c["diffs"][0]["kwargs_equal_arguments"] is False]
    edge.append(f"Forks where `attempts[i].kwargs` differs from the message arguments: {len(kw)} (arguments are taken "
                "from the message).")
    unk = [c for c in convs for x in c["diffs"][:1] for pp in x["changed_predicates"]
           if pp["judge"] is None or pp["tracker"] is None]
    edge.append(f"Forks where a changed value is unknown on one side (judge unknown -> tracker true/false): {len(unk)}. "
                "A tracker unknown never replaces a judge value (version b), so the tracker side is never unknown "
                "unless the judge's was.")
    multi = [c for c in convs if c["diffs"] and len(c["diffs"][0]["changed_predicates"]) > 1]
    edge.append(f"Forks with more than one changed predicate: {len(multi)}"
                + (": " + ", ".join(f"`{c['key']}` (alone flips: {c['diffs'][0]['flips_alone'] or 'none; only together'})"
                                    for c in multi) if multi else "") + ". All changed predicates are listed.")
    sk = res["checks"].get("judge skipped: frozen TGR decision unknown", 0)
    edge.append(f"Source 2 checks where the judge was skipped (frozen TGR's decision cannot be known): {sk}.")
    edge.append("Past trace: the decision uses the trace of executed attempts (cap overrides included). TGR's rules "
                "have no temporal operator; the check \"empty past trace gives the same decision\" holds on every "
                "judged attempt, so the mixed trace in source 2 (B's values) does not matter for A.")
    edge.append("Retried steps after the fork are not counted as forks; they are in `ref_forks_changes.jsonl`.")
    return ex, edge


def main() -> int:
    t0 = time.time()
    os.makedirs(OUT_DIR, exist_ok=True)
    if "--md-only" in sys.argv[1:]:          # write the report again from the saved JSON files (no recompute)
        with open(OUT_RATES, encoding="utf-8") as f:
            res = json.load(f)
        with open(OUT_FORKS, encoding="utf-8") as f:
            forks = [json.loads(line) for line in f]
        write_md(res, forks)
        print(f"wrote {OUT_MD} from {OUT_RATES}")
        return 0
    frozen = {os.path.relpath(p, PC): sha256(p) for p in FROZEN}
    frozen_ok = all(sha256(p) == want for p, want in FROZEN.items())
    if not frozen_ok:
        print("FROZEN INPUT CHANGED:", frozen)
        return 1
    ctx = Ctx()
    convs, load_stats, checks, notes = run_all(ctx)
    failed = {k: v for k, v in checks.items() if k.endswith("FAILED")}
    print("checks:", json.dumps(dict(sorted(checks.items())), indent=1), flush=True)
    for n in notes[:50]:
        print("NOTE", n)
    forks = [fork_line(c) for c in convs if c["diffs"]]
    with open(OUT_FORKS, "w", encoding="utf-8") as f:
        for x in forks:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    with open(OUT_CHANGES, "w", encoding="utf-8") as f:
        for c in convs:
            for x in c["diffs"]:
                f.write(json.dumps(change_line(c, x), ensure_ascii=False) + "\n")
    res = {"date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "frozen_sha256": frozen,
           "frozen_ok": frozen_ok, "rule_set_sha256": {d: sha256(paths.rule_set_path(d)) for d in DOMAINS},
           "inputs": load_stats, "checks": dict(sorted(checks.items())), "checks_failed": failed,
           "notes": notes[:200], "rates": rates(convs),
           "source2_judged": sum(c["n_judged"] for c in convs if c["source"] == "online_tracker")}
    res["compare_p8"] = compare_p8(convs)
    res["compare_p10"] = compare_p10(convs, checks)
    res["compare_part1"] = compare_part1(convs)
    res["explanations"], res["edge_cases"] = explanations(res, convs)
    res["seconds"] = time.time() - t0
    with open(OUT_RATES, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    write_md(res, forks)
    print(f"forks: {len(forks)}; changed attempts: {sum(len(c['diffs']) for c in convs)}; failed checks: {failed}")
    print("p8:", json.dumps({k: v for k, v in res["compare_p8"].items() if not isinstance(v, list)}))
    print("p10:", json.dumps({k: v for k, v in res["compare_p10"].items() if k in ("total_p10", "total_ours")}))
    print("part1:", json.dumps({k: v for k, v in res["compare_part1"].items() if not isinstance(v, list)}))
    print(f"wrote {OUT_FORKS}, {OUT_CHANGES}, {OUT_RATES}, {OUT_MD} in {res['seconds']:.0f} s")
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
