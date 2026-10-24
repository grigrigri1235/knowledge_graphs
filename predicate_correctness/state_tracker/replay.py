"""Part 6: replay. Tracker values next to the judge's values, for every saved guarded step.

For each Part 2 step record and each code-type predicate (argument, database fact, event; output/predicate_types.json)
in the rules of the step's circuit (rec["circuit"], rules from the frozen rule set):
  1. build the state before the step (state.walk: one pass per conversation; same state as build_state);
  2. run the predicate's frozen lookup (state_tracker/lookups_<domain>.json) with the pending call's arguments;
  3. store the tracker value next to the judge's saved value and evidence, with the objects and events the lookup
     read.

Outputs (in output/):
  p6_values.jsonl         one line per step and predicate
  p6_disagreements.jsonl  the lines where the values differ, with the objects (database copy and shown version) and
                          the events the lookup read, for the review in Part 7
  p6_agreement.md         agreement tables per type and per predicate, blocked steps separately, and per run

Comparison classes (`agreement` field):
  agree_true, agree_false     both give the same known value
  judge_true_tracker_false    disagreement
  judge_false_tracker_true    disagreement
  judge_unknown               the judge gave null, the tracker a value (disagreement)
  tracker_unknown             the tracker gave unknown, the judge a value (disagreement)
  both_unknown                both unknown (not a disagreement)

Run from predicate_correctness/:
    python3 -B -m state_tracker.replay > output/logs/p6_replay.log 2>&1
Standard library only. No LLM calls. Never imports gold code. Does not change the lookups.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import sys
import time
from typing import Any, Dict, Iterable, List, Optional

sys.dont_write_bytecode = True

if __package__ in (None, ""):
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    __package__ = "state_tracker"

from state_tracker import paths                                                   # noqa: E402
from state_tracker import lookup_format as L                                        # noqa: E402
from state_tracker.load_steps import JUDGE_HISTORY_CHARS, read_steps                # noqa: E402
from state_tracker.predicate_types import is_code_type, load_rule_set, load_types   # noqa: E402
from state_tracker.state import walk                                                # noqa: E402
from state_tracker.type_counts import logic_predicates                              # noqa: E402
from repro_core.taubench_steps import render_history                                # noqa: E402  (copy; path set by load_steps)

VALUES_JSONL = os.path.join(paths.OUTPUT_DIR, "p6_values.jsonl")
DISAGREE_JSONL = os.path.join(paths.OUTPUT_DIR, "p6_disagreements.jsonl")
AGREEMENT_MD = os.path.join(paths.OUTPUT_DIR, "p6_agreement.md")

# sha256 of the frozen lookup files (overview.md, Part 5). The replay stops if a file differs, unless --allow-changed.
FROZEN_SHA256 = {
    "airline": "882ca35ed6a1bbda1ea97d1eed87dd36246b2111cc1d4d47c5645ce12b701dc7",
    "retail": "77918b7727831f8c18353f5b5dce89d7e05017aa4db11f31722ee23cc41044a4",
}

CLASSES = ("agree_true", "agree_false", "judge_true_tracker_false", "judge_false_tracker_true",
           "judge_unknown", "tracker_unknown", "both_unknown")
DISAGREE = ("judge_true_tracker_false", "judge_false_tracker_true", "judge_unknown", "tracker_unknown")
VALUE_NAME = {True: "true", False: "false", None: "unknown"}
OUTPUT_CHARS = 3000          # event outputs in the disagreement file are cut to this length


def compare(judge: Optional[bool], tracker: Optional[bool]) -> str:
    """The comparison class of a judge value and a tracker value (True, False or None = unknown)."""
    if judge is None and tracker is None:
        return "both_unknown"
    if judge is None:
        return "judge_unknown"
    if tracker is None:
        return "tracker_unknown"
    if judge == tracker:
        return "agree_true" if judge else "agree_false"
    return "judge_true_tracker_false" if judge else "judge_false_tracker_true"


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


# ----------------------------------------------------------------------------------------------- recording state

class RecordingState:
    """Wraps a State and records what a lookup reads: db / shown objects (kind, id, found), db_all / shown_all
    (kind, count), events (filter and the indices of the events returned). Everything else is passed through.
    The lookups are evaluated unchanged (lookup_format.evaluate_detail) on this wrapper."""

    def __init__(self, state: Any):
        self._st = state
        self.reads: List[dict] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._st, name)

    def _note(self, entry: dict) -> None:
        if entry not in self.reads:
            self.reads.append(entry)

    def db_get(self, kind: str, oid: Any) -> Any:
        obj = self._st.db_get(kind, oid)
        self._note({"read": "db", "kind": kind, "id": oid, "found": obj is not None})
        return obj

    def shown_get(self, kind: str, oid: Any) -> Any:
        obj = self._st.shown_get(kind, oid)
        self._note({"read": "shown", "kind": kind, "id": oid, "found": obj is not None})
        return obj

    def db_all(self, kind: str) -> List[Any]:
        out = self._st.db_all(kind)
        self._note({"read": "db_all", "kind": kind, "n": len(out)})
        return out

    def shown_all(self, kind: str) -> List[Any]:
        out = self._st.shown_all(kind)
        self._note({"read": "shown_all", "kind": kind, "n": len(out)})
        return out

    def events_where(self, tool: Any = None, ok: Optional[bool] = None) -> List[dict]:
        out = self._st.events_where(tool=tool, ok=ok)
        tools = None if tool is None else ([tool] if isinstance(tool, str) else sorted(tool))
        self._note({"read": "events", "tool": tools, "ok": ok, "indices": [e["index"] for e in out]})
        return out


def _cut(x: Any, n: int = OUTPUT_CHARS) -> Any:
    if isinstance(x, str) and len(x) > n:
        return x[:n] + f" ...[{len(x) - n} more characters]"
    return x


def _event_view(e: dict) -> dict:
    return {"index": e["index"], "step": e["step"], "tool": e["tool"], "args": e["args"], "ok": e["ok"],
            "output": _cut(e["output"])}


def judge_view(history: Optional[List[dict]]) -> Dict[str, bool]:
    """tool_call_id -> True if that tool output's line was inside the judge's view. The judge saw
    render_history(history, max_chars=24000): only the last 24,000 characters (Part 2). A line counts as seen if it
    starts inside that window."""
    if not history:
        return {}
    full = len(render_history(history))
    out: Dict[str, bool] = {}
    for i, m in enumerate(history):
        if m.get("role") != "tool":
            continue
        before = len(render_history(history[:i]))
        start = before + 1 if before else 0                 # "\n" between lines
        out[m.get("tool_call_id")] = full - start <= JUDGE_HISTORY_CHARS
    return out


def context(state: Any, reads: List[dict], args: dict, history: Optional[List[dict]] = None) -> dict:
    """What a reviewer needs to see for one lookup run: for each object read, its value in the database copy and its
    shown version (with which call showed it); for each event filter, the events returned and the other events of
    the same tools (also the failed ones); and the pending call's arguments. With the history, each event and each
    shown object also says whether its tool output was inside the judge's view (`in_judge_view`)."""
    view = judge_view(history)
    by_index = {e["index"]: e for e in state.events}

    def seen_by_judge(event_index):
        e = by_index.get(event_index)
        return view.get(e["tool_call_id"]) if (e is not None and view) else None

    objects, seen = [], set()
    for r in reads:
        if r["read"] in ("db", "shown"):
            key = (r["kind"], json.dumps(r["id"], sort_keys=True, default=str))
            if key in seen:
                continue
            seen.add(key)
            kind, oid = r["kind"], r["id"]
            meta = state.shown_meta.get(kind, {}).get(oid) if isinstance(oid, str) else None
            objects.append({"kind": kind, "id": oid,
                            "read_by_lookup": sorted({x["read"] for x in reads if x.get("kind") == kind
                                                      and x.get("id") == oid}),
                            "db": state.db_get(kind, oid), "shown": state.shown_get(kind, oid),
                            "shown_by": meta,
                            "in_judge_view": seen_by_judge(meta["event"]) if meta else None})
    events = []
    for r in reads:
        if r["read"] != "events":
            continue
        related = state.events_where(tool=r["tool"]) if r["tool"] is not None else state.events
        events.append({"filter": {"tool": r["tool"], "ok": r["ok"]}, "returned": r["indices"],
                       "events": [dict(_event_view(e), in_judge_view=seen_by_judge(e["index"])) for e in related]})
    alls = [r for r in reads if r["read"] in ("db_all", "shown_all")]
    return {"args": args, "objects": objects, "events": events, "all_reads": alls}


GROUPS = (
    "login output outside the judge's view (history cut)",
    "cabin from an earlier successful flight update (Part 5 reading)",
    "order last shown by a write tool, with another status",
    "order last shown by get_order_details, with another status",
    "payment method is not a gift card (the rule does not need the value)",
    "refund: the new items cost less than the old ones",
    "an object the lookup used was shown outside the judge's view (history cut)",
    "an object the lookup needs was not shown (if_missing)",
    "judge unknown, and the judge saw a cut history",
    "other",
)


def disagreement_group(row: dict, ctx: dict) -> str:
    """A short, factual label for a disagreement, to sort them for the review. It says what the data shows, not who
    is right. The first label that fits is used (order of GROUPS)."""
    p, args = row["predicate"], ctx["args"] or {}
    objs = {(o["kind"], json.dumps(o["id"], default=str)): o for o in ctx["objects"]}

    def shown(kind, oid):
        o = objs.get((kind, json.dumps(oid, default=str)))
        return o["shown"] if o else None

    if p == "user_authenticated" and row["tracker_value"] is True and ctx["events"] and all(
            ev["in_judge_view"] is False for e in ctx["events"] for ev in e["events"] if ev["index"] in e["returned"]):
        return GROUPS[0]
    if any(e["filter"]["tool"] == ["update_reservation_flights"] and e["returned"] for e in ctx["events"]):
        return GROUPS[1]
    if p.startswith("order_status_checked"):
        o = objs.get(("order", json.dumps(args.get("order_id"), default=str)))
        if o and o["shown"] is not None:
            return GROUPS[2] if (o["shown_by"] or {}).get("tool") != "get_order_details" else GROUPS[3]
    if p == "gift_card_balance_covers_price_difference":
        if "gift_card" not in str(args.get("payment_method_id")):
            return GROUPS[4]
        order = shown("order", args.get("order_id"))
        try:
            old = sum([it["price"] for it in order["items"] if it["item_id"] == i][0] for i in args["item_ids"])
            new = sum(shown("variant", n)["price"] for n in args["new_item_ids"])
            if new < old:
                return GROUPS[5]
        except (KeyError, IndexError, TypeError):
            pass
    if any(o["shown"] is not None and o["in_judge_view"] is False for o in ctx["objects"]):
        return GROUPS[6]
    if any(r["read"] == "shown" and not r["found"] for r in row["used"]):
        return GROUPS[7]
    if row["judge_value"] is None and row["judge_history_cut"]:
        return GROUPS[8]
    return GROUPS[9]


def _short_reads(reads: List[dict]) -> List[dict]:
    """The reads, as stored in p6_values.jsonl (no objects; events as indices)."""
    return [dict(r) for r in reads]


# ----------------------------------------------------------------------------------------------- the replay

def circuit_predicates(rec: dict, rules: Dict[str, dict], names: Iterable[str]) -> List[str]:
    """The predicates in the rules of the step's circuit, in rule order, without repeats."""
    out: List[str] = []
    for rid in rec["circuit"]:
        for p in sorted(logic_predicates(rules[rid]["logic"], names)):
            if p not in out:
                out.append(p)
    return out


def violated_predicates(rec: dict, names: Iterable[str]) -> set:
    rules = [logic_predicates(r["logic"], names) for r in rec.get("violated_rules") or []]
    return set().union(*rules) if rules else set()


def replay_domain(domain: str, write_values, write_disagree, stats: dict) -> None:
    lookups = L.load_lookups(domain)
    types = load_types()[domain]
    rule_set = load_rule_set(domain)
    names = list(rule_set["predicates"])
    rules = {r["id"]: r for r in rule_set["rules"]}
    for run in paths.RUNS:
        key = (run, domain)
        s = stats.setdefault(key, new_run_stat())
        recs = list(read_steps(run, domain))
        groups: Dict[int, List[dict]] = collections.defaultdict(list)
        for r in recs:
            groups[r["episode_line"]].append(r)
        for line, group in sorted(groups.items()):
            longest = max(group, key=lambda r: r["history_len"])["history"]
            at: Dict[int, List[dict]] = collections.defaultdict(list)
            for r in group:
                at[r["history_len"]].append(r)
            last = None
            for n, st in walk(longest, domain=domain, stops=sorted(at)):
                last = st
                for rec in at[n]:
                    s["steps"] += 1
                    s["judge_values"] += len(rec["judge"])
                    preds = circuit_predicates(rec, rules, names)
                    if set(preds) != set(rec["judge"]):
                        s["problems"]["circuit predicates differ from judged predicates"] += 1
                    code = [p for p in preds if is_code_type(types[p]["type"])]
                    if code:
                        s["steps_with_code"] += 1
                    blocked = rec["action_allowed"] is False
                    viol = violated_predicates(rec, names)
                    for p in code:
                        row, dis = one_value(rec, p, types[p]["type"], lookups[p], st, blocked, p in viol,
                                             rule_set["predicates"][p]["description"])
                        s["code_values"] += 1
                        s["classes"][row["agreement"]] += 1
                        s["tracker"][VALUE_NAME[row["tracker_value"]]] += 1
                        if row["error"]:
                            s["errors"].append(f"{rec['step_id']} {p}: {row['error']}")
                        if row["judge_present"] is False:
                            s["problems"]["code-type predicate not in the judge record"] += 1
                        write_values(row)
                        if dis is not None:
                            write_disagree(dis)
                        stats.setdefault("_rows", []).append(_slim(row))
            if last is not None:
                s["mismatches"] += len(last.mismatches)
                s["parse_problems"] += len(last.parse_problems)


def new_run_stat() -> dict:
    return {"steps": 0, "steps_with_code": 0, "judge_values": 0, "code_values": 0, "classes": collections.Counter(),
            "tracker": collections.Counter(), "errors": [], "problems": collections.Counter(), "mismatches": 0,
            "parse_problems": 0}


def one_value(rec: dict, pred: str, ptype: str, lookup: dict, state: Any, blocked: bool, in_violated: bool,
              description: str) -> tuple:
    """Run one lookup on one step. Returns (values row, disagreement row or None)."""
    rs = RecordingState(state)
    judge = rec["judge"].get(pred)
    jval = judge.get("value") if judge else None
    error = None
    try:
        d = L.evaluate_detail(lookup, rs, args=rec["kwargs"])
        tval, missing = d["value"], d["missing"]
    except Exception as e:                       # an error in a lookup: unknown, with the error as the reason
        tval, missing, error = None, None, f"{type(e).__name__}: {e}"
    if tval is None:
        unknown_reason = (f"error: {error}" if error else f"if_missing=unknown: {missing}" if missing
                          else "the lookup gave unknown")
    else:
        unknown_reason = None
    cls = compare(jval, tval)
    row = {
        "step_id": rec["step_id"], "run": rec["run"], "domain": rec["domain"], "task": rec["task"],
        "trial": rec["trial"], "step": rec["exec_step"], "attempt": rec["attempt"],
        "episode_line": rec["episode_line"], "history_len": rec["history_len"],
        "action": rec["action"], "predicate": pred, "type": ptype, "uses": lookup["uses"],
        "if_missing": lookup["if_missing"],
        "judge_present": judge is not None, "judge_value": jval, "judge_evidence": (judge or {}).get("evidence"),
        "tracker_value": tval, "tracker_missing": missing, "unknown_reason": unknown_reason, "error": error,
        "used": _short_reads(rs.reads),
        "agreement": cls, "blocked": blocked, "executed": rec.get("executed"), "cap_override": rec.get("cap_override"),
        "in_violated_rule": in_violated, "judge_history_cut": rec.get("judge_history_cut"),
        "group": None,
    }
    dis = None
    if cls in DISAGREE:
        dis = dict(row)
        dis.update({"description": description, "plain": lookup["plain"], "expr": lookup["expr"],
                    "action_text": rec.get("action_text"), "circuit": rec["circuit"],
                    "violated_rules": [r.get("rule_id") for r in rec.get("violated_rules") or []],
                    "margin": rec.get("margin"),
                    "context": context(state, rs.reads, rec["kwargs"], rec.get("history"))})
        dis["group"] = disagreement_group(row, dis["context"])
        row["group"] = dis["group"]
    return row, dis


def _slim(row: dict) -> dict:
    out = {k: row[k] for k in ("run", "domain", "predicate", "type", "uses", "agreement", "blocked",
                               "in_violated_rule", "tracker_value", "judge_value", "judge_history_cut")}
    out["group"] = row.get("group")
    return out


# ----------------------------------------------------------------------------------------------- tables

def _pct(a: int, b: int) -> str:
    return f"{100.0 * a / b:.1f} %" if b else "-"


def _row(label: str, c: collections.Counter) -> str:
    n = sum(c.values())
    agree = c["agree_true"] + c["agree_false"]
    known = agree + c["judge_true_tracker_false"] + c["judge_false_tracker_true"]
    either = c["judge_unknown"] + c["tracker_unknown"] + c["both_unknown"]
    return (f"| {label} | {n} | {agree} ({c['agree_true']} / {c['agree_false']}) | {c['judge_true_tracker_false']} | "
            f"{c['judge_false_tracker_true']} | {either} ({c['judge_unknown']} / {c['tracker_unknown']} / "
            f"{c['both_unknown']}) | {_pct(agree, known)} |")


HEAD = ("| {0} | values | both agree (true / false) | judge true, tracker false | judge false, tracker true | "
        "either unknown (judge only / tracker only / both) | agreement when both known |")
SEP = "|---|---|---|---|---|---|---|"


def table(w, title: str, rows: List[dict], key, label_name: str, order: Optional[List] = None,
          fmt=lambda k: str(k)) -> None:
    by: Dict[Any, collections.Counter] = collections.defaultdict(collections.Counter)
    for r in rows:
        by[key(r)][r["agreement"]] += 1
    keys = order if order is not None else sorted(by)
    w(f"**{title}**")
    w("")
    w(HEAD.format(label_name))
    w(SEP)
    for k in keys:
        if k in by:
            w(_row(fmt(k), by[k]))
    total = collections.Counter()
    for c in by.values():
        total.update(c)
    w(_row("**all**", total))
    w("")


def render(stats: dict, rows: List[dict], seconds: float, shas: Dict[str, str]) -> str:
    out: List[str] = []
    w = out.append
    types_all = load_types()
    w("# Part 6: tracker values vs judge values")
    w("")
    w("Written by `state_tracker/replay.py`. For every Part 2 step record (4,903) and every code-type predicate")
    w("(argument, database fact, event) in the rules of the step's circuit, the frozen lookup ran on the state before")
    w("the step, and its value is compared with the judge's saved value. Conversation and mixed predicates are not")
    w("compared. No LLM calls; the judge values are the saved ones.")
    w("")
    w("- **Values:** true, false, unknown (judge: null; tracker: `if_missing` = unknown, or an error).")
    w("- **Blocked step:** `guard.action_allowed == false` (576 steps; 44 of them still ran through the cap override).")
    w("- **Disagreement:** the two values differ, including one known and one unknown. Both unknown is not a")
    w("  disagreement. Every disagreement is in `output/p6_disagreements.jsonl`, with the objects and events the lookup")
    w("  read.")
    w("- **Agreement when both known:** both agree / (both agree + judge true, tracker false + judge false, tracker true).")
    w(f"- Lookup files (frozen, unchanged): airline sha256 `{shas['airline']}`, retail `{shas['retail']}`.")
    w(f"- Time: {seconds:.0f} s.")
    w("")

    # ---- per run and domain
    w("## Per run and domain")
    w("")
    w("| run, domain | steps | steps with a code-type predicate | judge values | judge values replaced by the tracker "
      "| replaced with a different value | tracker unknown | tracker true / false | errors | replay mismatches |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    tot = new_run_stat()
    for run, domain in paths.RUN_DOMAINS:
        s = stats[(run, domain)]
        diff = sum(s["classes"][c] for c in DISAGREE)
        w(f"| {run} {domain} | {s['steps']:,} | {s['steps_with_code']:,} | {s['judge_values']:,} | "
          f"{s['code_values']:,} ({_pct(s['code_values'], s['judge_values'])}) | {diff:,} "
          f"({_pct(diff, s['code_values'])}) | {s['tracker']['unknown']:,} ({_pct(s['tracker']['unknown'], s['code_values'])}) | "
          f"{s['tracker']['true']:,} / {s['tracker']['false']:,} | {len(s['errors'])} | {s['mismatches']} |")
        for k in ("steps", "steps_with_code", "judge_values", "code_values", "mismatches"):
            tot[k] += s[k]
        tot["classes"].update(s["classes"])
        tot["tracker"].update(s["tracker"])
        tot["errors"] += s["errors"]
    diff = sum(tot["classes"][c] for c in DISAGREE)
    w(f"| **all** | {tot['steps']:,} | {tot['steps_with_code']:,} | {tot['judge_values']:,} | "
      f"{tot['code_values']:,} ({_pct(tot['code_values'], tot['judge_values'])}) | {diff:,} "
      f"({_pct(diff, tot['code_values'])}) | {tot['tracker']['unknown']:,} ({_pct(tot['tracker']['unknown'], tot['code_values'])}) | "
      f"{tot['tracker']['true']:,} / {tot['tracker']['false']:,} | {len(tot['errors'])} | {tot['mismatches']} |")
    w("")
    w("\"Replaced\" = the code-type values: in \"TGR + tracker\" the tracker sets them instead of the judge. "
      "\"With a different value\" counts all disagreements, including one side unknown.")
    w("")
    table(w, "Per run and domain: agreement", rows, lambda r: (r["run"], r["domain"]), "run, domain",
          order=list(paths.RUN_DOMAINS), fmt=lambda k: f"{k[0]} {k[1]}")
    table(w, "Per agent run, blocked steps only", [r for r in rows if r["blocked"]],
          lambda r: (r["run"], r["domain"]), "run, domain", order=list(paths.RUN_DOMAINS),
          fmt=lambda k: f"{k[0]} {k[1]}")

    # ---- per type
    w("## Per type")
    w("")
    order = ["argument", "database fact", "event"]
    tkey = lambda r: r["type"]
    table(w, "All steps", rows, tkey, "type", order=order)
    table(w, "Allowed steps", [r for r in rows if not r["blocked"]], tkey, "type", order=order)
    table(w, "Blocked steps", [r for r in rows if r["blocked"]], tkey, "type", order=order)
    table(w, "Blocked steps, predicate in a violated rule (block-causing)",
          [r for r in rows if r["blocked"] and r["in_violated_rule"]], tkey, "type", order=order)
    table(w, "By `uses` of the lookup (all steps; for argument lookups `uses` is a placeholder)", rows,
          lambda r: (r["type"], r["uses"]), "type, uses", fmt=lambda k: f"{k[0]}, {k[1]}")

    # ---- per predicate
    for domain in paths.DOMAINS:
        drows = [r for r in rows if r["domain"] == domain]
        lk = L.load_lookups(domain)
        porder = list(lk)
        fmt = lambda p, d=domain: f"`{p}` ({types_all[d][p]['type']})"
        w(f"## Per predicate: {domain}")
        w("")
        table(w, "All steps", drows, lambda r: r["predicate"], "predicate (type)", order=porder, fmt=fmt)
        table(w, "Blocked steps", [r for r in drows if r["blocked"]], lambda r: r["predicate"], "predicate (type)",
              order=porder, fmt=fmt)
        never = [p for p in porder if not any(r["predicate"] == p for r in drows)]
        if never:
            w(f"Never in a guarded step's rules: {', '.join(f'`{p}`' for p in never)}.")
            w("")

    # ---- disagreement groups
    dis = [r for r in rows if r["agreement"] in DISAGREE]
    w("## Disagreements by group")
    w("")
    w("Each disagreement gets one short label that says what the data shows (`group` in `p6_disagreements.jsonl`).")
    w("The label does not say who is right: that is the review in Part 7. The first label that fits is used.")
    w("")
    w("| predicate | group | disagreements | judge true, tracker false | judge false, tracker true | judge unknown "
      "| tracker unknown | on blocked steps | in a violated rule | judge saw a cut history |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    by: Dict[tuple, List[dict]] = collections.defaultdict(list)
    for r in dis:
        by[(r["domain"], r["predicate"], r["group"])].append(r)
    for (d, p, g), rs in sorted(by.items(), key=lambda kv: (kv[0][0], -len(kv[1]), kv[0][1], kv[0][2])):
        c = collections.Counter(r["agreement"] for r in rs)
        w(f"| `{p}` ({d}) | {g} | {len(rs)} | {c['judge_true_tracker_false']} | {c['judge_false_tracker_true']} | "
          f"{c['judge_unknown']} | {c['tracker_unknown']} | {sum(r['blocked'] for r in rs)} | "
          f"{sum(r['in_violated_rule'] for r in rs)} | {sum(bool(r['judge_history_cut']) for r in rs)} |")
    gc = collections.Counter(r["group"] for r in dis)
    w(f"| **all** | | {len(dis)} | | | | | {sum(r['blocked'] for r in dis)} | "
      f"{sum(r['in_violated_rule'] for r in dis)} | {sum(bool(r['judge_history_cut']) for r in dis)} |")
    w("")
    w("Per group: " + "; ".join(f"{g}: {gc[g]}" for g in GROUPS if gc[g]) + ".")
    w("")

    # ---- unknowns and reasons
    w("## Tracker unknowns and their reasons")
    w("")
    w("Every code-type value has a tracker value (true or false) or is unknown with a reason. The reasons:")
    w("")
    reasons = stats.get("_unknown_reasons", collections.Counter())
    if reasons:
        w("| predicate | reason | values |")
        w("|---|---|---|")
        for (p, r), c in reasons.most_common():
            w(f"| `{p}` | {r} | {c} |")
    else:
        w("None.")
    w("")
    probs = collections.Counter()
    for k, s in stats.items():
        if isinstance(k, tuple):
            probs.update(s["problems"])
    w("## Checks")
    w("")
    w(f"- Evaluation errors: {len(tot['errors'])}. Replay mismatches while walking: {tot['mismatches']}.")
    w(f"- Steps whose circuit predicates differ from the judged predicates: "
      f"{probs['circuit predicates differ from judged predicates']}.")
    w(f"- Code-type predicates in the circuit but missing from the judge record: "
      f"{probs['code-type predicate not in the judge record']}.")
    w(f"- Values where the judge saw a cut history (last 24,000 characters only): "
      f"{sum(1 for r in rows if r['judge_history_cut'])}, of which disagreements: "
      f"{sum(1 for r in rows if r['judge_history_cut'] and r['agreement'] in DISAGREE)}.")
    w("")
    return "\n".join(out) + "\n"


def _unknown_class(reason: str) -> str:
    """A short class of an unknown reason (for the table)."""
    if reason.startswith("error"):
        return reason[:100]
    if "KeyError" in reason:
        return "missing argument or field: " + reason.split("KeyError:", 1)[-1].strip()[:60]
    if "TypeError" in reason:
        return "malformed or missing value (TypeError)"
    return reason[:100]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--allow-changed", action="store_true", help="run even if a lookup file differs from the frozen one")
    ap.add_argument("--suffix", default="", help="written to p6_values<suffix>.jsonl etc. (for a rerun after a fix)")
    a = ap.parse_args(argv)
    shas = {d: sha256(L.lookups_path(d)) for d in paths.DOMAINS}
    changed = [d for d in paths.DOMAINS if shas[d] != FROZEN_SHA256[d]]
    if changed and not a.allow_changed:
        print(f"lookup files differ from the frozen ones: {changed}. Use --allow-changed after logging the fix in "
              f"output/p5_lookup_fixes.md.")
        return 2
    vpath, dpath, mpath = (p.replace(ext, f"{a.suffix}{ext}") for p, ext in
                           ((VALUES_JSONL, ".jsonl"), (DISAGREE_JSONL, ".jsonl"), (AGREEMENT_MD, ".md")))
    t0 = time.time()
    stats: dict = {}
    n_dis = 0
    with open(vpath, "w", encoding="utf-8") as fv, open(dpath, "w", encoding="utf-8") as fd:
        def wv(row):
            fv.write(json.dumps(row, ensure_ascii=False, sort_keys=False, default=str) + "\n")
            if row["tracker_value"] is None:
                stats.setdefault("_unknown_reasons", collections.Counter())[
                    (row["predicate"], _unknown_class(row["unknown_reason"]))] += 1

        def wd(row):
            nonlocal n_dis
            n_dis += 1
            fd.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

        for d in paths.DOMAINS:
            replay_domain(d, wv, wd, stats)
    rows = stats.pop("_rows", [])
    seconds = time.time() - t0
    with open(mpath, "w", encoding="utf-8") as f:
        f.write(render(stats, rows, seconds, shas))
    bad = 0
    for run, domain in paths.RUN_DOMAINS:
        s = stats[(run, domain)]
        bad += len(s["errors"]) + s["mismatches"] + sum(s["problems"].values())
        print(f"{run} {domain}: steps {s['steps']}, with code {s['steps_with_code']}, judge values {s['judge_values']}, "
              f"code values {s['code_values']}, classes {dict(s['classes'])}, tracker {dict(s['tracker'])}, "
              f"errors {len(s['errors'])}, problems {dict(s['problems'])}, mismatches {s['mismatches']}")
        for e in s["errors"][:5]:
            print("   ERROR", e)
    print(f"values {len(rows)}, disagreements {n_dis}")
    print(f"wrote {vpath}, {dpath}, {mpath} in {seconds:.0f} s")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
