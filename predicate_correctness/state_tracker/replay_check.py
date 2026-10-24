"""Part 4, subtasks 3 and 5: replay every executed tool call of every saved conversation and compare.

For each conversation of the 4 saved runs (Part 2 data), one pass over its full `executed` list:
- each tool call is replayed with τ-bench's tool code on a fresh database copy (state.Tracker);
- the replayed output is compared with the saved tool message (exact string; JSON-equal is counted too);
- the database is fingerprinted after each call, to check which calls changed it (against tool_table.json);
- the objects in each output go into the shown set; outputs that cannot be parsed are listed.
Then, for every Part 2 step record, build_state(rec["history"], rec) is compared with the one-pass state at the same
point (events, shown set, database).

Outputs: output/p4_replay_check.md, output/p4_parse_report.md.
Run from predicate_correctness/:
    python3 -B -m state_tracker.replay_check > output/logs/p4_replay_check.log 2>&1

Standard library only. No LLM calls. Never imports gold code.
"""
from __future__ import annotations

import collections
import datetime
import hashlib
import json
import os
import sys
import time
from typing import Dict, List, Optional

if __package__ in (None, ""):
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    from state_tracker import paths
    from state_tracker import state as S
    from state_tracker.load_steps import iter_episodes, read_steps
else:
    from . import paths
    from . import state as S
    from .load_steps import iter_episodes, read_steps


def db_hash(db: dict) -> str:
    return hashlib.sha256(json.dumps(db).encode()).hexdigest()


def shown_hash(st: S.State) -> str:
    return hashlib.sha256(json.dumps([st.shown, st.shown_meta], sort_keys=True).encode()).hexdigest()


def _same_values(st: S.State, ev: dict) -> str:
    """Why a write call that worked left the database the same: are its new values the old ones?"""
    a = ev["args"]
    earlier = any(e["ok"] and e["tool"] == ev["tool"] and e["args"] == a for e in st.events[:ev["index"]])
    out = f"an earlier call with the same arguments worked: {'yes' if earlier else 'no'}"
    if ev["tool"] == "update_reservation_flights":
        r = st.db_get("reservation", a.get("reservation_id")) or {}
        same_f = [(f.get("flight_number"), f.get("date")) for f in a.get("flights", [])] == \
                 [(f["flight_number"], f["date"]) for f in r.get("flights", [])]
        return (f"{out}; same flights as the reservation: {'yes' if same_f else 'no'}; cabin argument "
                f"{a.get('cabin')}, reservation's cabin field {r.get('cabin')}")
    if ev["tool"] == "modify_pending_order_address":
        o = st.db_get("order", a.get("order_id")) or {}
        new = {k: a.get(k) for k in ("address1", "address2", "city", "state", "country", "zip")}
        return f"{out}; new address equals the order's address: {'yes' if new == o.get('address') else 'no'}"
    return f"{out}; args {_short(a, 120)}"


def _short(x, n=160) -> str:
    s = x if isinstance(x, str) else json.dumps(x)
    return s if len(s) <= n else s[:n] + "…"


def check_run(run: str, domain: str, verify_records: bool = True) -> dict:
    spec = S.tool_table()["domains"][domain]["tools"]
    c = collections.Counter()
    per_tool: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    shown_kinds = collections.Counter()
    mismatches: List[dict] = []
    parse_problems: List[dict] = []
    problems: List[str] = []
    unknown_tools = collections.Counter()
    error_texts: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    write_no_change: List[str] = []
    db_change_bad: List[str] = []
    kwargs_diff: List[str] = []
    snapshots: Dict[tuple, tuple] = {}                 # (episode line, history_len) -> (events, shown hash, db hash)
    needed = collections.defaultdict(set)
    if verify_records:
        for rec in read_steps(run, domain, with_history=False):
            needed[rec["episode_line"]].add(rec["history_len"])
    for line_no, ep in iter_episodes(run, domain):
        c["conversations"] += 1
        executed = ep["executed"]
        if S.infer_domain(executed) != domain:
            problems.append(f"line {line_no}: domain from the history != {domain}")
        c["system_is_policy"] += executed[0].get("content") == S.tau_copy.policy_text(domain)
        tr = S.Tracker(domain)
        st = tr.state
        h_prev = db_hash(st.db)
        cid = f"{run}/{domain}/task{ep['task_index']}/trial{ep.get('trial')}"
        # arguments in the executed message vs the attempt's saved kwargs (the replay uses the message)
        ran = [a for a in ep["attempts"] if not a["blocked"] and a["action"] != "respond"]
        msgs = [m for m in executed if m.get("role") == "assistant" and m.get("tool_calls")]
        for a, m in zip(ran, msgs):
            if json.loads(m["tool_calls"][0]["function"]["arguments"]) != a["kwargs"]:
                kwargs_diff.append(f"{cid}/step{a['exec_step']} {a['action']}")
        if len(ran) != len(msgs):
            problems.append(f"{cid}: {len(ran)} executed tool attempts but {len(msgs)} tool-call messages")
        for i, msg in enumerate(executed):
            if i in needed.get(line_no, ()):
                snapshots[(line_no, i)] = (len(st.events), shown_hash(st), h_prev)
            n_before = len(st.events)
            n_mis, n_parse = len(st.mismatches), len(st.parse_problems)
            tr.feed_message(msg)
            if len(st.events) == n_before:
                continue
            ev = st.events[-1]
            h = db_hash(st.db)
            changed = h != h_prev
            h_prev = h
            t = ev["tool"]
            pt = per_tool[t]
            c["calls"] += 1
            pt["calls"] += 1
            pt["ok" if ev["ok"] else "failed"] += 1
            c["exact"] += bool(ev["match"])
            c["json_equal"] += bool(ev["json_match"])
            pt["exact"] += bool(ev["match"])
            if t not in spec:
                unknown_tools[t] += 1
            if not ev["ok"]:
                error_texts[t][_short(ev["output"], 90)] += 1
            if changed:
                pt["db_changed"] += 1
                if not spec.get(t, {}).get("changes_db"):
                    db_change_bad.append(f"{cid}/step{ev['step']} {t}: read-only tool changed the database")
                if not ev["ok"]:
                    db_change_bad.append(f"{cid}/step{ev['step']} {t}: failed call changed the database")
            elif ev["ok"] and spec.get(t, {}).get("changes_db"):
                write_no_change.append(f"{cid}/step{ev['step']} {t}: {_same_values(st, ev)}")
            for mm in st.mismatches[n_mis:]:
                mismatches.append({"conv": cid, **mm})
            for pp in st.parse_problems[n_parse:]:
                parse_problems.append({"conv": cid, **pp})
            if ev["ok"] and spec.get(t, {}).get("output") == "text":
                pt["text_ok"] += 1
        if len(executed) in needed.get(line_no, ()):
            snapshots[(line_no, len(executed))] = (len(st.events), shown_hash(st), h_prev)
        tr.finish()
        problems.extend(f"{cid}: {p}" for p in st.problems)
        for kind, objs in st.shown.items():
            shown_kinds[kind] += len(objs)
        c["shown_objects"] += sum(len(v) for v in st.shown.values())
        c["calls_per_conv_max"] = max(c["calls_per_conv_max"], len(st.events))
    # build_state per step record == the one-pass state at the same point
    rec_bad: List[str] = []
    if verify_records:
        t0 = time.time()
        for rec in read_steps(run, domain):
            st = S.build_state(rec["history"], rec)
            c["records"] += 1
            want = snapshots.get((rec["episode_line"], rec["history_len"]))
            got = (len(st.events), shown_hash(st), db_hash(st.db))
            n_calls = sum(len(m.get("tool_calls") or []) for m in rec["history"] if m.get("role") == "assistant")
            ok = (want == got and len(st.events) == n_calls and st.domain == domain and not st.mismatches
                  and st.pending == {"tool": rec["action"], "args": rec["kwargs"], "kind": rec["kind"]}
                  and (st.today is not None) == (domain == "airline"))
            c["records_same"] += ok
            if not ok and len(rec_bad) < 20:
                rec_bad.append(rec["step_id"])
        c["records_seconds"] = round(time.time() - t0)
    return {"run": run, "domain": domain, "c": dict(c), "per_tool": {k: dict(v) for k, v in per_tool.items()},
            "shown_kinds": dict(shown_kinds), "mismatches": mismatches, "parse_problems": parse_problems,
            "problems": problems, "unknown_tools": dict(unknown_tools),
            "error_texts": {k: dict(v) for k, v in error_texts.items()}, "write_no_change": write_no_change,
            "db_change_bad": db_change_bad, "kwargs_diff": kwargs_diff, "rec_bad": rec_bad}


# ----------------------------------------------------------------------------------------------- reports

def _n(x) -> str:
    return f"{x:,}"


def write_replay_report(results: List[dict], path: str) -> None:
    today = datetime.date.today().isoformat()
    L: List[str] = []
    w = L.append
    tot = collections.Counter()
    for r in results:
        tot.update({k: v for k, v in r["c"].items() if k != "calls_per_conv_max"})
    w("# Part 4: Replay Check")
    w("")
    w(f"Made by `python3 -B -m state_tracker.replay_check` (run in `predicate_correctness/`) on {today}.")
    w("Log: `output/logs/p4_replay_check.log`. Code: `state_tracker/state.py`, `state_tracker/replay_check.py`.")
    w("")
    w("## What was checked")
    w("- **All executed tool calls of all saved conversations** (the 4 runs of Part 2, 396 conversations). Each")
    w("  conversation is replayed once, from a fresh copy of τ-bench's data, over its full `executed` list. Calls that")
    w("  ran through the cap override are in `executed`, so they are replayed too. Blocked calls are not.")
    w("- **How the call is run:** τ-bench's own tool code (the copy, unchanged), the same way as `Env.step`: an")
    w("  exception becomes `Error: <exception>`. The arguments are read from the agent's message (`tool_calls`), and")
    w("  the output is matched to its tool message by `tool_call_id`.")
    w("- **Comparison:** the replayed output must be exactly the same string as the saved tool message. We also count")
    w("  outputs that are the same JSON value (for example, the same object with other spacing). With exact equality,")
    w("  the JSON count can only be the same or higher.")
    w("")
    w("## Result")
    w("| run | domain | conversations | calls checked | exact match | JSON-equal | mismatches |")
    w("|---|---|---|---|---|---|---|")
    for r in results:
        c = r["c"]
        w(f"| `{r['run']}` | {r['domain']} | {c['conversations']} | {_n(c['calls'])} | {_n(c['exact'])} | "
          f"{_n(c['json_equal'])} | {len(r['mismatches'])} |")
    n_mis = sum(len(r["mismatches"]) for r in results)
    w(f"| all | | {tot['conversations']} | {_n(tot['calls'])} | {_n(tot['exact'])} | {_n(tot['json_equal'])} | "
      f"{n_mis} |")
    w("")
    if n_mis == 0:
        w(f"**Every replayed output equals the saved one ({_n(tot['exact'])} of {_n(tot['calls'])}, exact string).** "
          "So the database copy is the database of the real run at every step, and there is no mismatch to explain.")
    else:
        w(f"**{n_mis} mismatches.** Each one is listed below with its cause.")
        w("")
        w("| conversation | step | tool | saved | replayed | JSON-equal |")
        w("|---|---|---|---|---|---|")
        for r in results:
            for m in r["mismatches"]:
                w(f"| `{m['conv']}` | {m['step']} | `{m['tool']}` | `{_short(m['saved'], 80)}` | "
                  f"`{_short(m['replayed'], 80)}` | {m['json_equal']} |")
    w("")
    w("## Which calls changed the database")
    w("The database was fingerprinted (sha256 of its JSON) after every call.")
    w("")
    w("| run | domain | read-only tool changed it | failed call changed it | write call that worked but changed nothing |")
    w("|---|---|---|---|---|")
    for r in results:
        ro = sum(1 for x in r["db_change_bad"] if "read-only" in x)
        fl = sum(1 for x in r["db_change_bad"] if "failed call" in x)
        w(f"| `{r['run']}` | {r['domain']} | {ro} | {fl} | {len(r['write_no_change'])} |")
    w("")
    w("- So the `changes_db` column of `tool_table.json` holds on the data: only write tools changed the database, and")
    w("  a failed call never did." if not any(r["db_change_bad"] for r in results) else
      "- **Some calls disagree with `tool_table.json`:** " + "; ".join(x for r in results for x in r["db_change_bad"][:10]))
    wnc = [x for r in results for x in r["write_no_change"]]
    if wnc:
        n_rep = sum(1 for x in wnc if "same arguments worked: yes" in x)
        w(f"- {len(wnc)} write calls worked but left the database the same. In {n_rep} of them, the same call (same")
        w("  arguments) had already worked earlier in the conversation, so the new values were already there. Example:")
        w("  `update_reservation_flights` to change the cabin. The first call sets the new prices and adds a payment;")
        w("  a repeated call finds the same prices, so the price difference is 0 and nothing changes. τ-bench never")
        w("  updates the reservation's `cabin` field, so the agent may see the old cabin and try again."
          + (" The other cases are listed with their reason." if n_rep < len(wnc) else ""))
        w("  None of this is a replay problem: τ-bench's code gives the same result. All cases:")
        for x in wnc:
            w(f"  - `{x}`")
    w("")
    w("## Each step record gets the same state from `build_state`")
    w("For every Part 2 step record, `build_state(rec[\"history\"], rec)` (fresh copy, replay of the history only) was")
    w("compared with the one-pass state at the same point: number of events, shown set (with which event showed each")
    w("object), and the database fingerprint. Also checked: the events equal the tool calls in the history, the")
    w("domain, the pending action, no mismatch, and today's date (airline only).")
    w("")
    w("| run | domain | records | same | seconds |")
    w("|---|---|---|---|---|")
    for r in results:
        c = r["c"]
        w(f"| `{r['run']}` | {r['domain']} | {_n(c.get('records', 0))} | {_n(c.get('records_same', 0))} | "
          f"{c.get('records_seconds', '-')} |")
    bad = [x for r in results for x in r["rec_bad"]]
    w("")
    w("All records give the same state." if not bad else "**Records that differ:** " + ", ".join(f"`{x}`" for x in bad))
    w("")
    w("## Other checks")
    sp = sum(r["c"].get("system_is_policy", 0) for r in results)
    w(f"- The system message of {sp} of {tot['conversations']} conversations is exactly the copied policy text, so")
    w("  `build_state` can tell the domain from it.")
    probs = [x for r in results for x in r["problems"]]
    w(f"- Tool messages without a matching call, or calls without an output: {len(probs)}."
      + ("" if not probs else " " + "; ".join(probs[:10])))
    kd = [x for r in results for x in r["kwargs_diff"]]
    w("- The arguments in the agent's message equal the attempt's saved `kwargs` for every executed tool call"
      + (" (0 differences)." if not kd else f", except {len(kd)}: " + ", ".join(f"`{x}`" for x in kd[:20])))
    if kd:
        w("  Cause: τ-bench's `book_reservation` stores the `payment_methods` argument list itself as the reservation's")
        w("  `payment_history`. Later calls in the same conversation (`cancel_reservation`, `update_reservation_*`)")
        w("  append to that list, so the attempt's saved `kwargs` changed after the call. The message text did not")
        w("  change, so the replay (which reads the message) is not affected. Our replay gives each tool a copy of the")
        w("  arguments, so our event log keeps the arguments as sent.")
    w("")
    w("## Failed calls (worked = false)")
    w("Calls whose output starts with `Error` (τ-bench's failed outputs). They are in the event log as failed and add")
    w("nothing to the shown set. An output like `Error: X.invoke() got an unexpected keyword argument …` comes from a")
    w("call with a wrong argument name: τ-bench's `Env.step` turns the exception into this text, and the replay gives")
    w("the same text.")
    w("")
    w("| run | domain | tool | output | count |")
    w("|---|---|---|---|---|")
    for r in results:
        for t, texts in sorted(r["error_texts"].items()):
            for txt, k in sorted(texts.items(), key=lambda kv: -kv[1]):
                w(f"| `{r['run']}` | {r['domain']} | `{t}` | `{txt}` | {k} |")
    w("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def write_parse_report(results: List[dict], path: str) -> None:
    today = datetime.date.today().isoformat()
    L: List[str] = []
    w = L.append
    w("# Part 4: Shown-Set Parse Report")
    w("")
    w(f"Made by `python3 -B -m state_tracker.replay_check` on {today}. How outputs are parsed: `state_tracker/README.md`")
    w("(\"Shown set\") and `state_tracker/tool_table.json`.")
    w("")
    w("## Rules")
    w("- Only outputs of calls that worked are parsed. A failed call (`Error…`) adds nothing.")
    w("- A tool whose `output` is `text` in the tool table has no objects by design (`calculate`, `think`,")
    w("  `transfer_to_human_agents`, `find_user_id_by_*`, `send_certificate`). These are not parse failures; the event")
    w("  log keeps their output.")
    w("- A parse failure is an output of a call that worked that does not have the form the tool table gives (for")
    w("  example, not JSON, or no id).")
    w("")
    n_pp = sum(len(r["parse_problems"]) for r in results)
    n_unk = sum(sum(r["unknown_tools"].values()) for r in results)
    w("## Result")
    w(f"- **Parse failures: {n_pp}.**")
    w(f"- **Unknown tools (not in the tool table): {n_unk}.**")
    w("")
    if n_pp:
        w("| conversation | step | tool | problem | output (start) |")
        w("|---|---|---|---|---|")
        for r in results:
            for p in r["parse_problems"]:
                w(f"| `{p['conv']}` | {p['step']} | `{p['tool']}` | {p['problem']} | `{_short(p['output'], 80)}` |")
        w("")
    if n_unk:
        for r in results:
            for t, k in r["unknown_tools"].items():
                w(f"- `{r['run']}/{r['domain']}`: unknown tool `{t}`, {k} calls")
        w("")
    w("## Calls per tool")
    w("| run | domain | tool | calls | worked | failed | text output (no objects) | changed the database |")
    w("|---|---|---|---|---|---|---|---|")
    for r in results:
        for t, pt in sorted(r["per_tool"].items()):
            w(f"| `{r['run']}` | {r['domain']} | `{t}` | {pt.get('calls', 0)} | {pt.get('ok', 0)} | "
              f"{pt.get('failed', 0)} | {pt.get('text_ok', 0)} | {pt.get('db_changed', 0)} |")
    w("")
    w("## Shown objects at the end of the conversations")
    w("Sum over the conversations of the objects in the shown set at the end (one per kind and id).")
    w("")
    w("| run | domain | " + " | ".join(["kind", "objects"]) + " |")
    w("|---|---|---|---|")
    for r in results:
        for k, v in sorted(r["shown_kinds"].items()):
            w(f"| `{r['run']}` | {r['domain']} | `{k}` | {_n(v)} |")
    w("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    verify = "--no-records" not in argv
    results = []
    for run, domain in paths.RUN_DOMAINS:
        t0 = time.time()
        r = check_run(run, domain, verify_records=verify)
        results.append(r)
        c = r["c"]
        print(f"{run}/{domain}: conversations {c['conversations']}, calls {c['calls']}, exact {c['exact']}, "
              f"json_equal {c['json_equal']}, mismatches {len(r['mismatches'])}, parse problems "
              f"{len(r['parse_problems'])}, unknown tools {r['unknown_tools']}, db change problems "
              f"{len(r['db_change_bad'])}, write calls without change {len(r['write_no_change'])}, kwargs diffs "
              f"{len(r['kwargs_diff'])}, problems {len(r['problems'])}, records {c.get('records', 0)} same "
              f"{c.get('records_same', 0)}, seconds {round(time.time() - t0)}", flush=True)
        for m in r["mismatches"][:5]:
            print("  mismatch:", m["conv"], m["step"], m["tool"], "| saved:", _short(m["saved"]), "| replayed:",
                  _short(m["replayed"]))
        for x in r["write_no_change"][:10]:
            print("  write without change:", x)
        for x in r["kwargs_diff"][:10]:
            print("  kwargs diff:", x)
        for x in r["problems"][:10]:
            print("  problem:", x)
    write_replay_report(results, os.path.join(paths.OUTPUT_DIR, "p4_replay_check.md"))
    write_parse_report(results, os.path.join(paths.OUTPUT_DIR, "p4_parse_report.md"))
    print("wrote output/p4_replay_check.md and output/p4_parse_report.md")
    failed = any(r["mismatches"] or r["parse_problems"] or r["unknown_tools"] or r["db_change_bad"] or r["rec_bad"]
                 or r["problems"] for r in results)
    print("RESULT:", "problems found (see the reports)" if failed else "all checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
