"""Part 2: the saved TGR conversations as one record per guarded step (an attempt where the judge was called).

Input:  the copies from_shieldagent/runs/<run>/<domain>/tgr/episodes.jsonl (file format: state_tracker/README.md).
Output: output/steps_<run>_<domain>.jsonl (one record per line) and output/p2_counts.md.

Use from other parts (run from predicate_correctness/, or put it on sys.path):
    from state_tracker.load_steps import read_steps
    for rec in read_steps("nano_train", "retail"):   # saved records; history and past_trace are added back
        rec["history"], rec["action"], rec["kwargs"], rec["judge"], rec["circuit"], rec["action_allowed"], ...

    iter_steps(run, domain) gives the same records, built directly from the copied episodes.

Run as a script, from predicate_correctness/:
    python3 -m state_tracker.load_steps > output/logs/p2_load_steps.log 2>&1
    (python3 state_tracker/load_steps.py works too)

The saved files hold the history as a reference (episode_line, history_len) into the checked copy, not the messages
themselves: inline, the histories would add about 80 MB. read_steps() adds `history` and `past_trace` back.

Standard library only. No LLM calls. Reads only the copies in from_shieldagent/. Never imports gold code.
"""
from __future__ import annotations

import collections
import datetime
import hashlib
import json
import os
import random
import sys
from typing import Dict, Iterator, List, Optional, Tuple

if __package__ in (None, ""):                       # run as a file: python3 state_tracker/load_steps.py
    _pc = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path[0] = _pc                               # predicate_correctness/ instead of state_tracker/
    from state_tracker import paths
else:
    from . import paths

paths.add_code_path()
from repro_core.taubench_steps import render_history  # noqa: E402  (copy in from_shieldagent/code/)

# The judge saw render_history(history, max_chars=24000): only the last 24,000 characters of the history.
# Source: TGRConfig.history_chars in ~/ShieldAgent/method_tgr/runtime.py (last changed in commit e32ba95,
# 2026-10-20 11:31, before all four runs).
JUDGE_HISTORY_CHARS = 24000

# Fields that read_steps() / iter_steps() add in memory but that are not saved.
IN_MEMORY = ("history", "past_trace")

# Expected counts (brainstorm sections 2.3 and 2.4; split per domain by the earlier analysis).
# judge values = predicate entries in the judge dicts; blocked = guard checks with action_allowed == false.
EXPECTED = {
    ("luna_train_v5", "airline"): {"judge_values": 2224, "blocked": 12},
    ("luna_train_v5", "retail"): {"judge_values": 5489, "blocked": 54},
    ("nano_train", "airline"): {"judge_values": 3877, "blocked": 94},
    ("nano_train", "retail"): {"judge_values": 8614, "blocked": 416},
}
EXPECTED_TOTALS = {"luna_train_v5": 7713, "nano_train": 12491}     # judge values per agent (brainstorm 2.4)
AGENT_LABEL = {"luna_train_v5": "gpt-6-luna agent", "nano_train": "gpt-5-nano agent"}
NOT_RETURNED = "(not returned by the judge)"   # evidence TGR writes when the judge skipped a predicate


# ----------------------------------------------------------------------------------------------- reading

def load_splits() -> Dict[str, Dict[int, str]]:
    """{domain: {task_index: "train" | "val" | "test"}} from splits.json (key `split`, task index as a string)."""
    with open(paths.SPLITS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return {d: {int(k): v for k, v in data[d]["split"].items()} for d in paths.DOMAINS}


def iter_episodes(run: str, domain: str) -> Iterator[Tuple[int, dict]]:
    """(line number from 0, episode) for each line of the copied episodes.jsonl."""
    with open(paths.episodes_path(run, domain), encoding="utf-8") as f:
        for line_no, line in enumerate(f):
            yield line_no, json.loads(line)


def episode_trial(ep: dict, seen: collections.Counter) -> int:
    """The episode's `trial` key. If it is missing: the number of earlier episodes of the same task in the file
    (0, 1, 2, ...). `seen` counts episodes per task and must be shared over one file, read in file order."""
    n = seen[ep["task_index"]]
    seen[ep["task_index"]] += 1
    return ep["trial"] if "trial" in ep else n


def step_id(run: str, domain: str, task: int, trial: int, exec_step: int, attempt: int) -> str:
    return f"{run}/{domain}/task{task}/trial{trial}/step{exec_step}/attempt{attempt}"


# ----------------------------------------------------------------------------------------------- records

def _record(run: str, domain: str, line_no: int, ep: dict, trial: int, split: Optional[str], att: dict,
            history: List[dict], past: List[dict]) -> dict:
    g = att["guard"]
    ran = not att["blocked"]                       # allowed, or blocked but run through the cap override
    obs = att.get("observation") if ran else None
    rendered = render_history(history)             # the judge's view before the cut
    usage = g.get("usage") or {}
    return {
        "step_id": step_id(run, domain, ep["task_index"], trial, att["exec_step"], att["attempt"]),
        "run": run, "domain": domain, "task": ep["task_index"], "trial": trial, "split": split,
        "exec_step": att["exec_step"], "attempt": att["attempt"], "episode_line": line_no,
        "agent_model": (ep.get("models") or {}).get("agent"), "guard_model": (ep.get("models") or {}).get("guard"),
        # the pending action
        "kind": g["kind"], "action": att["action"], "kwargs": att["kwargs"], "action_text": g["action_text"],
        "agent_text": att["agent_text"],
        # the history (saved as a length; the messages are added in memory)
        "history_len": att["executed_prefix_len"], "trace_len_before": g["trace_len_before"],
        "judge_history_chars": len(rendered), "judge_history_cut": len(rendered) > JUDGE_HISTORY_CHARS,
        # the guard's saved record
        "matched": g["matched"], "circuit": g["circuit"], "judge": g["judge"], "trace_position": g["trace_position"],
        "action_allowed": g["action_allowed"], "margin": g["margin"], "allowed_eps0": g.get("allowed_eps0"),
        "epsilon": g["epsilon"], "violated_rules": g["violated_rules"],
        "unknown_predicates": g.get("unknown_predicates", []), "mln": g.get("mln"),
        "judge_usage": {k: usage.get(k) for k in ("n_llm_calls", "cache_hits", "cost_usd")},
        # what happened
        "executed": ran, "cap_override": att["cap_override"], "observation": obs,
        "api_error": bool(ran and g["kind"] == "tool_call" and isinstance(obs, str) and obs.startswith("Error")),
        # in memory only
        "history": history, "past_trace": list(past),
    }


def episode_records(run: str, domain: str, line_no: int, ep: dict, trial: int,
                    split: Optional[str] = None) -> List[dict]:
    """The records of one episode: one per attempt whose guard record has a non-empty judge dict.

    history    = executed[:executed_prefix_len]: the executed messages before the attempt. Blocked attempts never
                 enter `executed`, as in the guard.
    past_trace = trace_position of each earlier executed attempt: the guard's trace (method_tgr Conversation.trace),
                 the `past` argument of repro_runtime.mln.decide.
    """
    executed = ep["executed"]
    past: List[dict] = []
    out = []
    for att in ep["attempts"]:
        g = att.get("guard")
        if g and g.get("judge"):
            out.append(_record(run, domain, line_no, ep, trial, split, att,
                               executed[:att["executed_prefix_len"]], past))
        if not att["blocked"]:
            past.append((g or {}).get("trace_position"))
    return out


def iter_steps(run: str, domain: str, splits: Optional[Dict[str, Dict[int, str]]] = None) -> Iterator[dict]:
    """All records of one run and domain, built from the copied episodes (with history and past_trace)."""
    splits = splits if splits is not None else load_splits()
    seen: collections.Counter = collections.Counter()
    for line_no, ep in iter_episodes(run, domain):
        trial = episode_trial(ep, seen)
        yield from episode_records(run, domain, line_no, ep, trial, splits[domain].get(ep["task_index"]))


def to_saved(rec: dict) -> dict:
    """The record without the in-memory fields (what the steps files hold)."""
    return {k: v for k, v in rec.items() if k not in IN_MEMORY}


def read_steps(run: str, domain: str, with_history: bool = True) -> Iterator[dict]:
    """The saved records of output/steps_<run>_<domain>.jsonl. With with_history, `history` and `past_trace` are
    added back from the copied episodes (episode_line, history_len), as iter_steps() gives them."""
    episodes: Optional[List[dict]] = None
    with open(paths.steps_path(run, domain), encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if with_history:
                if episodes is None:
                    episodes = [ep for _, ep in iter_episodes(run, domain)]
                ep = episodes[rec["episode_line"]]
                if ep["task_index"] != rec["task"] or ep.get("trial", rec["trial"]) != rec["trial"]:
                    raise ValueError(f"{rec['step_id']}: episode line {rec['episode_line']} is another episode")
                rec["history"] = ep["executed"][:rec["history_len"]]
                rec["past_trace"] = [a["guard"]["trace_position"] for a in ep["attempts"]
                                     if not a["blocked"] and a["exec_step"] < rec["exec_step"]]
            yield rec


# ----------------------------------------------------------------------------------------------- checks

def _same_call(msg: Optional[dict], rec: dict) -> bool:
    """Is `msg` (an executed assistant message) the record's pending action?"""
    if msg is None or msg.get("role") != "assistant":
        return False
    calls = msg.get("tool_calls") or []
    if rec["kind"] == "respond":
        return not calls and (msg.get("content") or "") == rec["kwargs"].get("content")
    if not calls:
        return False
    fn = calls[0].get("function") or {}
    try:
        args = json.loads(fn.get("arguments") or "{}")
    except json.JSONDecodeError:
        return False
    return fn.get("name") == rec["action"] and args == rec["kwargs"]


def check_episode(ep: dict, recs: List[dict]) -> collections.Counter:
    """Problems found in one episode and its records (an empty Counter means all checks passed)."""
    bad: collections.Counter = collections.Counter()
    executed = ep["executed"]
    n_ran = sum(1 for a in ep["attempts"] if not a["blocked"])
    if n_ran != ep["n_exec_steps"]:
        bad["executed attempts != n_exec_steps"] += 1
    if len(executed) != 2 + 2 * ep["n_exec_steps"]:
        bad["len(executed) != 2 + 2 * n_exec_steps"] += 1
    keys = [(a["exec_step"], a["attempt"]) for a in ep["attempts"]]
    if len(keys) != len(set(keys)):
        bad["(exec_step, attempt) not unique"] += 1
    for a in ep["attempts"]:
        g = a.get("guard") or {}
        if a["blocked"] != (g.get("action_allowed") is False and not a["cap_override"]):
            bad["blocked flag != guard decision"] += 1
        if a["cap_override"] and g.get("action_allowed") is not False:
            bad["cap override of an allowed action"] += 1
    for r in recs:
        n_agent = sum(1 for m in r["history"] if m.get("role") == "assistant")
        if r["history_len"] != 2 + 2 * r["trace_len_before"]:
            bad["history_len != 2 + 2 * trace_len_before"] += 1
        if n_agent != r["trace_len_before"]:
            bad["agent messages in history != trace_len_before"] += 1
        if len(r["past_trace"]) != r["trace_len_before"]:
            bad["past_trace length != trace_len_before"] += 1
        if r["exec_step"] != r["trace_len_before"]:
            bad["exec_step != trace_len_before"] += 1
        if r["history"] and r["history"][0].get("role") != "system":
            bad["history does not start with the system message"] += 1
        if r["action"] != (r["matched"][0] if r["matched"] else None):
            bad["matched action != pending action"] += 1
        if r["executed"]:
            h = r["history_len"]
            if not _same_call(executed[h] if h < len(executed) else None, r):
                bad["executed[history_len] is not the pending action"] += 1
            nxt = executed[h + 1] if h + 1 < len(executed) else None
            role = "user" if r["kind"] == "respond" else "tool"
            if nxt is None or nxt.get("role") != role or nxt.get("content") != r["observation"]:
                bad["executed[history_len + 1] is not the saved output"] += 1
    return bad


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def recorded_sha256() -> Dict[str, str]:
    """{path inside from_shieldagent/: sha256} from SHA256SUMS (Part 1)."""
    out = {}
    with open(paths.SHA256SUMS, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                digest, rel = line.rstrip("\n").split("  ", 1)
                out[rel] = digest
    return out


# ----------------------------------------------------------------------------------------------- one run

def process(run: str, domain: str, splits: Dict[str, Dict[int, str]], write: bool = True) -> dict:
    """Read one run and domain, check it, write its steps file, and return its counts."""
    c: Dict[str, object] = collections.defaultdict(int)
    bad: collections.Counter = collections.Counter()
    no_judge_tools: collections.Counter = collections.Counter()
    kinds: collections.Counter = collections.Counter()
    preds: set = set()
    tasks: Dict[int, List[int]] = collections.defaultdict(list)
    not_train: List[Tuple[int, Optional[str]]] = []
    examples: List[dict] = []
    seen: collections.Counter = collections.Counter()
    trial_from_key = 0
    out_path = paths.steps_path(run, domain)
    tmp = out_path + ".tmp"
    f = open(tmp, "w", encoding="utf-8") if write else None
    try:
        for line_no, ep in iter_episodes(run, domain):
            trial_from_key += "trial" in ep
            trial = episode_trial(ep, seen)
            split = splits[domain].get(ep["task_index"])
            tasks[ep["task_index"]].append(trial)
            if split != "train":
                not_train.append((ep["task_index"], split))
            recs = episode_records(run, domain, line_no, ep, trial, split)
            bad.update(check_episode(ep, recs))
            c["episodes"] += 1
            for a in ep["attempts"]:
                c["attempts"] += 1
                g = a.get("guard")
                if g is None:
                    continue
                c["guard_checks"] += 1
                if g.get("action_allowed") is False:
                    c["blocked"] += 1
                    c["blocked_not_run"] += a["blocked"]
                    c["blocked_cap_override"] += a["cap_override"]
                if not g.get("judge"):
                    no_judge_tools[g.get("name")] += 1
            for r in recs:
                c["records"] += 1
                kinds[r["kind"]] += 1
                c["records_blocked"] += r["action_allowed"] is False
                c["records_executed"] += r["executed"]
                c["judge_history_cut"] += r["judge_history_cut"]
                for name, v in r["judge"].items():
                    preds.add(name)
                    c["judge_values"] += 1
                    c["value_true"] += v.get("value") is True
                    c["value_false"] += v.get("value") is False
                    c["value_unknown"] += v.get("value") is None
                    c["not_returned"] += v.get("evidence") == NOT_RETURNED
                examples.append({k: r[k] for k in ("step_id", "history_len", "trace_len_before")}
                                | {"agent_msgs": sum(1 for m in r["history"] if m.get("role") == "assistant"),
                                   "past": len(r["past_trace"])})
                if f is not None:
                    f.write(json.dumps(to_saved(r), ensure_ascii=False) + "\n")
    finally:
        if f is not None:
            f.close()
    if write and not not_train:
        os.replace(tmp, out_path)
    elif write:
        os.remove(tmp)                                   # stop: a task is not a train task (p2.md subtask 4)
    with open(paths.rule_set_path(domain), encoding="utf-8") as rf:
        missing = sorted(set(json.load(rf)["predicates"]) - preds)   # frozen predicates never judged in this run
    c = dict(c)
    c.update({"run": run, "domain": domain, "bad": dict(bad), "no_judge_tools": dict(no_judge_tools),
              "missing_predicates": missing,
              "kinds": dict(kinds), "n_predicates": len(preds), "tasks": {t: sorted(v) for t, v in tasks.items()},
              "not_train": not_train, "trial_from_key": trial_from_key, "examples": examples,
              "train_tasks": sorted(t for t, s in splits[domain].items() if s == "train"),
              "out_path": out_path if write and not not_train else None})
    return c


# ----------------------------------------------------------------------------------------------- report

def _n(x) -> str:
    return f"{x:,}"


def write_counts(results: List[dict], path: str, sums: Dict[str, str]) -> None:
    today = datetime.date.today().isoformat()
    L: List[str] = []
    w = L.append
    w("# Part 2: Step Records and Counts")
    w("")
    w(f"Made by `python3 -m state_tracker.load_steps` (run in `predicate_correctness/`) on {today}.")
    w("Log: `output/logs/p2_load_steps.log`. Code: `state_tracker/load_steps.py`. File formats: `state_tracker/README.md`.")
    w("")
    w("## What a record is")
    w("- One record per attempt where the TGR judge was called (its guard record has a non-empty `judge`).")
    w("- Each record has: run, domain, task, trial, step and attempt; the pending action (tool name and arguments);")
    w("  the history before the step; the judge's value and evidence for each predicate; the step's rules")
    w("  (`circuit`), the decision (`action_allowed`, `margin`) and the violated rules.")
    w("- Files: `output/steps_<run>_<domain>.jsonl`, one record per line.")
    w("")
    w("## Counts")
    w("- **guard checks:** attempts the guard checked (every attempt).")
    w("- **records:** guard checks where the judge was called. The other checks were for actions without rules.")
    w("- **judge values:** one per predicate per record (true, false or unknown).")
    w("- **blocked:** guard checks with `action_allowed` = false. Most of these calls did not run. After 3 blocks in a")
    w("  row at the same step, the 4th attempt runs even if the guard blocks it (\"cap override\").")
    w("")
    w("| run | domain | episodes | guard checks | records | judge values | true / false / unknown | blocked | not run / cap override |")
    w("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        w(f"| `{r['run']}` | {r['domain']} | {r['episodes']} | {_n(r['guard_checks'])} | {_n(r['records'])} | "
          f"{_n(r['judge_values'])} | {_n(r['value_true'])} / {_n(r['value_false'])} / {_n(r['value_unknown'])} | "
          f"{r['blocked']} | {r['blocked_not_run']} / {r['blocked_cap_override']} |")
    tot = collections.defaultdict(lambda: collections.Counter())
    for r in results:
        tot[r["run"]].update({k: r[k] for k in ("records", "judge_values", "blocked")})
    w("")
    w("## Compared with the expected numbers")
    w("Expected: brainstorm sections 2.3 (blocks) and 2.4 (judge values), split per domain by the earlier analysis.")
    w("")
    w("| run | domain | judge values: expected / found | blocked: expected / found | same? |")
    w("|---|---|---|---|---|")
    all_same = True
    for r in results:
        e = EXPECTED.get((r["run"], r["domain"]), {})
        same = e.get("judge_values") == r["judge_values"] and e.get("blocked") == r["blocked"]
        all_same &= same
        w(f"| `{r['run']}` | {r['domain']} | {_n(e.get('judge_values', 0))} / {_n(r['judge_values'])} | "
          f"{e.get('blocked')} / {r['blocked']} | {'yes' if same else 'NO'} |")
    for run, label in AGENT_LABEL.items():
        if run in tot:
            same = EXPECTED_TOTALS[run] == tot[run]["judge_values"]
            all_same &= same
            w(f"| `{run}` | both ({label}) | {_n(EXPECTED_TOTALS[run])} / {_n(tot[run]['judge_values'])} | "
              f"{sum(EXPECTED[(run, d)]['blocked'] for d in paths.DOMAINS)} / {tot[run]['blocked']} | "
              f"{'yes' if same else 'NO'} |")
    w("")
    if all_same:
        w("All counts are the same as expected. There is no difference to explain.")
    else:
        w("**Some counts differ from the expected ones.** See the notes below.")
    w("")
    w("## Check: the history is right")
    w("- **Rule.** The history of a step is `executed[:executed_prefix_len]`: the system message, the first user")
    w("  message, then 2 messages per executed step (the agent's message, and the tool output or the user's reply).")
    w("  The guard's trace has one entry per executed step. So: history length = 2 + 2 × trace length.")
    w("- **Checked on every record** (not only on 5), with 4 more rules: the number of agent messages in the history,")
    w("  the number of earlier executed attempts (`past_trace`) and the step number all equal the guard's trace length;")
    w("  the history starts with the system message.")
    n_bad = sum(sum(r["bad"].values()) for r in results)
    n_rec = sum(r["records"] for r in results)
    w(f"- **Result:** {_n(n_rec)} records, {n_bad} problems." if n_bad == 0 else
      f"- **Result:** {_n(n_rec)} records, **{n_bad} problems**: "
      + "; ".join(f"`{r['run']}/{r['domain']}`: {r['bad']}" for r in results if r["bad"]))
    w("")
    w("5 example steps (random, seed 0):")
    w("")
    w("| step | history (messages) | agent messages in history | earlier executed steps | guard's trace length | same? |")
    w("|---|---|---|---|---|---|")
    pool = sorted((x for r in results for x in r["examples"]), key=lambda x: x["step_id"])
    for x in random.Random(0).sample(pool, min(5, len(pool))):
        ok = x["history_len"] == 2 + 2 * x["trace_len_before"] and x["agent_msgs"] == x["past"] == x["trace_len_before"]
        w(f"| `{x['step_id']}` | {x['history_len']} | {x['agent_msgs']} | {x['past']} | {x['trace_len_before']} | "
          f"{'yes' if ok else 'NO'} |")
    w("")
    w("## Check: the tasks")
    w("`splits.json` maps each task index (as a string) to train, val or test, per domain: "
      "`splits[domain][\"split\"][str(task_index)]`.")
    w("")
    w("| run | domain | tasks | train tasks in splits.json | trials per task | not train |")
    w("|---|---|---|---|---|---|")
    for r in results:
        trials = sorted({tuple(v) for v in r["tasks"].values()})
        same_set = sorted(r["tasks"]) == r["train_tasks"]
        w(f"| `{r['run']}` | {r['domain']} | {len(r['tasks'])} | {len(r['train_tasks'])} "
          f"({'same set' if same_set else 'DIFFERENT set'}) | {', '.join(str(list(t)) for t in trials)} | "
          f"{len(r['not_train'])} |")
    n_nt = sum(len(r["not_train"]) for r in results)
    w("")
    w("Every episode is a train task, and every train task has 3 trials." if n_nt == 0 else
      f"**{n_nt} episodes are not train tasks. Stopped: no steps file was written for those runs.**")
    w("")
    w("## Check: the pending action")
    n_ran = sum(r["records_executed"] for r in results)
    n_call_bad = sum(v for r in results for k, v in r["bad"].items() if k.startswith("executed[history_len"))
    w("For each record whose call ran, `executed[history_len]` must be the same call (tool name and arguments, or")
    w("the same reply text), and `executed[history_len + 1]` must be the saved output. Part 4 relies on this.")
    n_match_bad = sum(r["bad"].get("matched action != pending action", 0) for r in results)
    w(f"Result: {_n(n_ran)} records checked, {n_call_bad} problems.")
    w(f"Also, in all {_n(n_rec)} records the guard's matched action should be the pending action: {n_match_bad} problems.")
    w("")
    w("## Inputs")
    w("| file | sha256 | same as `SHA256SUMS` (Part 1)? |")
    w("|---|---|---|")
    for r in results:
        rel = os.path.relpath(paths.episodes_path(r["run"], r["domain"]), paths.FROM_SA)
        d = sha256(paths.episodes_path(r["run"], r["domain"]))
        w(f"| `from_shieldagent/{rel}` | `{d[:16]}…` | {'yes' if sums.get(rel) == d else 'NO'} |")
    d = sha256(paths.SPLITS_FILE)
    w(f"| `from_shieldagent/splits/splits.json` | `{d[:16]}…` | "
      f"{'yes' if sums.get('splits/splits.json') == d else 'NO'} |")
    w("")
    w("## Other facts for later parts")
    w("- **The judge saw only the last 24,000 characters of the history** (`render_history(history, max_chars=24000)`")
    w("  in `method_tgr/runtime.py`). So in long conversations the login and the first look-ups can be missing from")
    w("  the judge's view. Records where this cut happened (`judge_history_cut` = true):")
    w("")
    w("  | run | domain | records | with a cut | share |")
    w("  |---|---|---|---|---|")
    for r in results:
        share = 100.0 * r["judge_history_cut"] / r["records"] if r["records"] else 0.0
        w(f"  | `{r['run']}` | {r['domain']} | {_n(r['records'])} | {r['judge_history_cut']} | {share:.1f} % |")
    w("")
    w("  Example: in `nano_train/retail/task23/trial0/step21` the history has 28,011 characters. The login (step 1)")
    w("  was cut from the judge's view. The 3 attempts whose rules use `user_authenticated` got the value false")
    w("  (\"No earlier successful email or name-and-zip lookup appears\"), and all 3 were blocked.")
    w("  Brainstorm section 2.2 said that TGR's cut was not counted. These are the counts.")
    w("")
    nr = sum(r["not_returned"] for r in results)
    w(f"- **Values the judge did not return:** {nr}. TGR sets them to unknown with the evidence "
      f"\"{NOT_RETURNED}\".")
    w("- **Records per kind:** " + "; ".join(
        f"`{r['run']}/{r['domain']}` tool call {r['kinds'].get('tool_call', 0)}, reply {r['kinds'].get('respond', 0)}"
        for r in results) + ".")
    w("- **Guard checks without a judge call** (the action has no rules, so it is allowed without the judge): "
      + "; ".join(f"`{r['run']}/{r['domain']}` {sum(r['no_judge_tools'].values())} "
                  f"({', '.join(f'{k} {v}' for k, v in sorted(r['no_judge_tools'].items(), key=lambda kv: -kv[1]))})"
                  for r in results) + ".")
    w("- **Predicates seen in the records:** " + "; ".join(
        f"`{r['run']}/{r['domain']}` {r['n_predicates']}" for r in results)
      + " (of 42 airline and 24 retail). Never judged: " + "; ".join(
        f"`{r['run']}/{r['domain']}` " + (", ".join(f"`{p}`" for p in r["missing_predicates"]) or "none")
        for r in results) + ".")
    w("")
    w("## Format choices")
    n_key = sum(r["trial_from_key"] for r in results)
    n_ep = sum(r["episodes"] for r in results)
    w(f"- **Trial:** from the episode's `trial` key ({n_key} of {n_ep} episodes have it). If it were missing, the")
    w("  trial would be the number of earlier episodes of the same task in the file (0, 1, 2).")
    w("- **History:** the saved records hold `history_len` and `episode_line` (line in the copied `episodes.jsonl`,")
    w("  from 0), not the messages. Inline, the histories would add about 80 MB, because each step repeats the steps")
    w("  before it. `read_steps()` in `load_steps.py` adds `history` and `past_trace` back from the checked copy.")
    w("- **Step id:** `<run>/<domain>/task<T>/trial<R>/step<S>/attempt<A>`. `step` is the number of executed steps")
    w("  before the attempt; `attempt` counts the tries at that step (1 = first try; 2-4 come after blocks).")
    w("- **Blocked vs executed:** `action_allowed` is the guard's decision. `executed` says whether the call ran.")
    w("  They differ only for cap overrides (blocked, but run).")
    w("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


# ----------------------------------------------------------------------------------------------- main

def main(argv: Optional[List[str]] = None) -> int:
    splits = load_splits()
    sums = recorded_sha256()
    results = []
    for run, domain in paths.RUN_DOMAINS:
        r = process(run, domain, splits)
        results.append(r)
        print(f"{run}/{domain}: episodes {r['episodes']}, guard checks {r['guard_checks']}, records {r['records']}, "
              f"judge values {r['judge_values']} (true {r['value_true']}, false {r['value_false']}, unknown "
              f"{r['value_unknown']}), blocked {r['blocked']} (not run {r['blocked_not_run']}, cap override "
              f"{r['blocked_cap_override']}), judge history cut {r['judge_history_cut']}, problems {r['bad'] or 0}, "
              f"not train {len(r['not_train'])}, written {r['out_path']}")
    counts_path = os.path.join(paths.OUTPUT_DIR, "p2_counts.md")
    write_counts(results, counts_path, sums)
    print(f"wrote {counts_path}")
    failed = any(r["not_train"] or r["bad"] for r in results)
    for r in results:
        e = EXPECTED[(r["run"], r["domain"])]
        print(f"{r['run']}/{r['domain']}: judge values expected {e['judge_values']} found {r['judge_values']}; "
              f"blocked expected {e['blocked']} found {r['blocked']}")
    print("RESULT:", "problems found (see p2_counts.md)" if failed else "all checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
