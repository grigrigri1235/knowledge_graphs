"""Part 7, subtasks 1 and 2: the sample of tracker and judge values, and the blind review sheet.

Sample (fixed seed SEED), from output/p6_values.jsonl:
  - every disagreement on a blocked step (guard action_allowed == false);
  - a random sample of N_OTHER of the other disagreements;
  - N_AGREE random agreements, as a control.
"Disagreement" is as in Part 6: the two values differ, including one known and one unknown.

The items are shuffled. Each item shows the two values as "value A" and "value B", in random order per item. The
sheet does not say which value came from which source, or whether the item is a disagreement. The key is in
output/p7_key.json, which the reviewer must not read.

Outputs (in output/):
  p7_review_sheet.md            the sheet the reviewer reads and fills in (one "Answer" line per item)
  p7_review_items.json          the same items as data (for scoring; `answer` and `note` stay empty here)
  p7_review_conversations.json  the conversations of the sampled items, without the policy (system) message
  p7_key.json                   which value is which, the sample group and the Part 6 fields (NOT for the reviewer)

For every item the state before the step is built again (state.build_state) and the frozen lookup is run again. The
value must equal the one in p6_values.jsonl; the script fails if not.

Run from predicate_correctness/:
    python3 -B -m state_tracker.p7_sample > output/logs/p7_sample.log 2>&1
    python3 -B -m state_tracker.p7_sample --check-answers > output/logs/p7_check_answers.log 2>&1
The first command refuses to overwrite a sheet that already has answers (use --force).
Standard library only. No LLM calls. Never imports gold code. Does not change the lookups.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import random
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.dont_write_bytecode = True

if __package__ in (None, ""):
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    __package__ = "state_tracker"

from state_tracker import paths                                                   # noqa: E402
from state_tracker import lookup_format as L                                        # noqa: E402
from state_tracker.load_steps import read_steps                                     # noqa: E402
from state_tracker.predicate_types import load_rule_set                             # noqa: E402
from state_tracker.replay import DISAGREE, FROZEN_SHA256, RecordingState, context, sha256   # noqa: E402
from state_tracker.state import build_state                                         # noqa: E402

SEED = 20261022          # the date of the sample; written into the sheet and the key
N_OTHER = 30             # random disagreements on steps that were not blocked
N_AGREE = 50             # random agreements (control)

VALUES_JSONL = os.path.join(paths.OUTPUT_DIR, "p6_values.jsonl")
SHEET_MD = os.path.join(paths.OUTPUT_DIR, "p7_review_sheet.md")
ITEMS_JSON = os.path.join(paths.OUTPUT_DIR, "p7_review_items.json")
CONV_JSON = os.path.join(paths.OUTPUT_DIR, "p7_review_conversations.json")
KEY_JSON = os.path.join(paths.OUTPUT_DIR, "p7_key.json")

ANSWERS = ("A right", "B right", "both wrong", "both right", "predicate unclear")
STRATA = ("disagreement, blocked step", "disagreement, other", "agreement")
VALUE_TEXT = {True: "true", False: "false", None: "unknown"}

# Conversation excerpt
LAST_N = 4               # the last messages before the step are always shown
TOOL_CHARS = 1500        # outputs that showed an object or call that matters are cut to this length (the objects
                         # themselves are given in full below the excerpt)
OTHER_TOOL_CHARS = 400   # other tool outputs in the excerpt
TEXT_CHARS = 1500        # user and agent texts are cut to this length: the first user message and the last LAST_N
OTHER_TEXT_CHARS = 700   # other user and agent texts in the excerpt (picked because they mention an id)
EVENT_CHARS = 400        # outputs in the list of earlier calls
BIG_JSON = 1200          # JSON longer than this goes into a <details> block
# Argument names whose values are ids; messages that mention one of these values are put in the excerpt.
ID_KEYS = {"order_id", "item_ids", "new_item_ids", "reservation_id", "payment_id", "payment_method_id", "user_id",
           "flight_number", "product_id", "item_id"}


# ----------------------------------------------------------------------------------------------- sample

def load_values(path: str = VALUES_JSONL) -> List[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def row_key(r: dict) -> Tuple[str, str]:
    return (r["step_id"], r["predicate"])


def draw_sample(rows: List[dict], seed: int = SEED, n_other: int = N_OTHER, n_agree: int = N_AGREE
                ) -> List[Tuple[dict, str]]:
    """(row, stratum) pairs: every disagreement on a blocked step, n_other random other disagreements, n_agree random
    agreements. Rows are sorted first, so the same seed always gives the same sample. Not shuffled."""
    rng = random.Random(seed)
    rows = sorted(rows, key=row_key)
    dis_blocked = [r for r in rows if r["agreement"] in DISAGREE and r["blocked"]]
    dis_other = [r for r in rows if r["agreement"] in DISAGREE and not r["blocked"]]
    agree = [r for r in rows if r["agreement"] in ("agree_true", "agree_false")]
    out = [(r, STRATA[0]) for r in dis_blocked]
    out += [(r, STRATA[1]) for r in rng.sample(dis_other, min(n_other, len(dis_other)))]
    out += [(r, STRATA[2]) for r in rng.sample(agree, min(n_agree, len(agree)))]
    return out


def shuffle_and_blind(sample: List[Tuple[dict, str]], seed: int = SEED) -> List[dict]:
    """Shuffle the items, give them ids P7-001 ..., and put the two values in random order (A, B) per item.
    Returns key entries: id, the row, the stratum, and which source is A."""
    rng = random.Random(seed + 1)
    items = list(sample)
    rng.shuffle(items)
    out = []
    for i, (row, stratum) in enumerate(items, 1):
        a = "tracker" if rng.random() < 0.5 else "judge"
        out.append({"id": f"P7-{i:03d}", "row": row, "stratum": stratum, "A": a,
                    "B": "judge" if a == "tracker" else "tracker"})
    return out


# ----------------------------------------------------------------------------------------------- excerpt

def _ids_in(x: Any, key: Optional[str] = None, out: Optional[set] = None) -> set:
    """String values of id arguments (ID_KEYS), also inside lists and nested dicts (flights, payment_methods)."""
    out = set() if out is None else out
    if isinstance(x, dict):
        for k, v in x.items():
            _ids_in(v, k, out)
    elif isinstance(x, list):
        for v in x:
            _ids_in(v, key, out)
    elif isinstance(x, (str, int)) and key in ID_KEYS and str(x).strip():
        out.add(str(x))
    return out


def _msg_text(m: dict) -> str:
    """Everything in a message that can mention an id: its text and its tool calls (name and arguments)."""
    parts = [m.get("content") or ""]
    for tc in m.get("tool_calls") or []:
        fn = tc.get("function") or {}
        parts.append(f"{fn.get('name')} {fn.get('arguments')}")
    return "\n".join(str(p) for p in parts)


def _cut(text: str, n: int) -> str:
    text = str(text)
    return text if len(text) <= n else text[:n] + f" ...[{len(text) - n} more characters]"


def select_messages(history: List[dict], ids: set, must: set, last_n: int = LAST_N) -> List[int]:
    """Indices of the history messages for the excerpt (index 0 = the policy, never shown):
    the first user message, the last `last_n` messages, every message that mentions one of `ids`, the messages in
    `must`, and for every tool call or output picked, its partner (the call and its output go together)."""
    n = len(history)
    pick = set(i for i in must if 0 < i < n)
    if n > 1:
        pick.add(1)
    pick.update(range(max(1, n - last_n), n))
    for i in range(1, n):
        text = _msg_text(history[i])
        if any(x in text for x in ids):
            pick.add(i)
    # calls and outputs together
    call_of: Dict[str, int] = {}
    out_of: Dict[str, int] = {}
    for i, m in enumerate(history):
        for tc in m.get("tool_calls") or []:
            call_of[tc.get("id")] = i
        if m.get("role") == "tool":
            out_of[m.get("tool_call_id")] = i
    for i in list(pick):
        m = history[i]
        if m.get("role") == "tool" and m.get("tool_call_id") in call_of:
            pick.add(call_of[m["tool_call_id"]])
        for tc in m.get("tool_calls") or []:
            if tc.get("id") in out_of:
                pick.add(out_of[tc["id"]])
    return sorted(pick)


def message_view(i: int, m: dict, tool_chars: int = TOOL_CHARS, text_chars: int = TEXT_CHARS) -> dict:
    role = m.get("role")
    if role == "tool":
        return {"n": i, "role": "tool output", "tool": m.get("name"), "text": _cut(m.get("content") or "", tool_chars)}
    calls = []
    for tc in m.get("tool_calls") or []:
        fn = tc.get("function") or {}
        calls.append(f"{fn.get('name')}({fn.get('arguments')})")
    return {"n": i, "role": "agent" if role == "assistant" else role,
            "text": _cut(m.get("content") or "", text_chars), "calls": calls}


def render_excerpt(msgs: List[dict], n_total: int) -> str:
    lines, prev = [], 0
    for m in msgs:
        if m["n"] > prev + 1:
            lines.append(f"[messages #{prev + 1}-#{m['n'] - 1} left out]" if m["n"] - 1 > prev + 1
                         else f"[message #{prev + 1} left out]")
        if m["role"] == "tool output":
            lines.append(f"#{m['n']} output of {m['tool']}: {m['text']}")
        else:
            text = m["text"]
            if m.get("calls"):
                text = (text + "\n   " if text else "") + "calls: " + "; ".join(m["calls"])
            lines.append(f"#{m['n']} {m['role']}: {text}")
        prev = m["n"]
    if prev < n_total - 1:
        lines.append(f"[messages #{prev + 1}-#{n_total - 1} left out]")
    return "\n".join(lines).replace("````", "` ` ` `")


# ----------------------------------------------------------------------------------------------- objects

def _diff_fields(kind: str, db: Any, shown: Any) -> List[str]:
    """Top-level fields where the shown version differs from the database value. For a flight, only the dates that
    were shown are compared."""
    if not isinstance(db, dict) or not isinstance(shown, dict):
        return [] if db == shown else ["(whole value)"]
    out = []
    for k in sorted(set(db) | set(shown)):
        if kind == "flight" and k == "dates":
            sd, dd = shown.get("dates") or {}, db.get("dates") or {}
            out += [f"dates.{d}" for d in sorted(sd) if sd.get(d) != dd.get(d)]
        elif db.get(k) != shown.get(k):
            out.append(k)
    return out


def _dates_in(x: Any) -> set:
    """Every 'YYYY-MM-DD' text in the arguments (flight dates)."""
    return set(re.findall(r"\d{4}-\d{2}-\d{2}", json.dumps(x)))


def _trim_flight(db: Any, shown: Any, dates: set) -> Any:
    """A flight's database value with only the dates that were shown or that the pending call names (a flight has
    a status and prices for every date; the others do not matter for the value)."""
    if not isinstance(db, dict) or not isinstance(db.get("dates"), dict):
        return db
    keep = set(dates) | set((shown or {}).get("dates") or {})
    kept = {d: v for d, v in db["dates"].items() if d in keep}
    out = dict(db, dates=kept)
    if len(kept) < len(db["dates"]):
        out["dates_left_out"] = f"{len(db['dates']) - len(kept)} other dates"
    return out


def object_view(o: dict, msg_of_event: Dict[int, int], dates: Optional[set] = None) -> dict:
    meta = o.get("shown_by")
    shown_text = "not shown before this step"
    if o.get("shown") is not None and meta:
        k = msg_of_event.get(meta.get("event"))
        where = f"message #{k}" if k is not None else f"call {meta.get('event')}"
        diff = _diff_fields(o["kind"], o.get("db"), o.get("shown"))
        if o.get("db") is None:
            same = "the database has no such object"
        elif diff:
            same = "the shown version differs from the database value in: " + ", ".join(diff)
        else:
            same = "the shown version equals the database value" + (
                " (for the dates shown)" if o["kind"] == "flight" else "")
        shown_text = f"shown by {meta.get('tool')} (newest version in {where}); {same}"
    db = _trim_flight(o.get("db"), o.get("shown"), dates or set()) if o["kind"] == "flight" else o.get("db")
    return {"kind": o["kind"], "id": o["id"], "db": db, "shown": o.get("shown"), "shown_text": shown_text}


def event_view(ctx_events: List[dict], msg_of_event: Dict[int, int]) -> List[dict]:
    """The earlier calls of the tools that matter for the value (also the failed ones), once each."""
    seen, out = set(), []
    for f in ctx_events:
        for e in f["events"]:
            if e["index"] in seen:
                continue
            seen.add(e["index"])
            out.append({"message": msg_of_event.get(e["index"]), "tool": e["tool"], "args": e["args"],
                        "worked": e["ok"], "output": _cut(e["output"], EVENT_CHARS)})
    return sorted(out, key=lambda e: (e["message"] is None, e["message"] or 0))


def tracker_explanation(row: dict, lookup: dict, objs: List[dict], ctx: dict, msg_of_event: Dict[int, int]) -> str:
    parts = [lookup["plain"]]
    used = []
    for o in ctx["objects"]:
        src = " and ".join("database value" if r == "db" else "shown version" for r in o["read_by_lookup"])
        found = "found" if (o["shown"] if "shown" in o["read_by_lookup"] else o["db"]) is not None else "not found"
        used.append(f"{o['kind']} {o['id']} ({src}; {found})")
    for f in ctx["events"]:
        msgs = [f"#{msg_of_event[i]}" for i in f["returned"] if i in msg_of_event]
        tools = ", ".join(f["filter"]["tool"] or ["any tool"])
        cond = {True: "that worked", False: "that failed", None: ""}[f["filter"]["ok"]]
        used.append(f"earlier calls of {tools} {cond}: " + (", ".join(msgs) if msgs else "none").strip())
    for a in ctx.get("all_reads") or []:
        used.append(f"all {a['kind']} objects ({'database' if a['read'] == 'db_all' else 'shown'}; {a['n']})")
    if used:
        parts.append("Based on: " + "; ".join(used) + ".")
    else:
        parts.append("Based on: the pending call's arguments.")
    if row["tracker_missing"]:
        miss = row["tracker_missing"]
        m = re.match(r"KeyError: '(.+)'", miss)
        what = (f"the field or argument '{m.group(1)}' is missing" if m else
                "an object it needs was not found" if "NoneType" in miss else miss)
        parts.append(f"Missing: {what}, so the value is {lookup['if_missing']}.")
    return " ".join(parts)


def judge_explanation(row: dict) -> str:
    ev = (row.get("judge_evidence") or "").strip()
    return ev if ev else "(no explanation given)"


def correct_means(ptype: str, uses: str) -> str:
    if ptype == "argument":
        return ("argument: the pending call's arguments decide (with the description; also read the conversation if "
                "the description refers to it).")
    if uses == "fact":
        return "fact: the value in the database copy at this step (the database value below), as the description says."
    return ("shown: what the conversation had shown before this step (tool outputs and messages before the pending "
            "action), as the description says. If the description asks for something an earlier tool output "
            "established, and no output before the step showed it, the value is false.")


# ----------------------------------------------------------------------------------------------- build

def build_items(entries: List[dict]) -> Tuple[List[dict], Dict[str, List[dict]], List[str]]:
    """For each key entry: the review item (blind), plus the conversations, plus check problems."""
    need: Dict[Tuple[str, str], set] = collections.defaultdict(set)
    for e in entries:
        need[(e["row"]["run"], e["row"]["domain"])].add(e["row"]["step_id"])
    recs: Dict[str, dict] = {}
    longest: Dict[str, Tuple[int, List[dict]]] = {}
    for (run, domain), ids in need.items():
        for rec in read_steps(run, domain):
            if rec["step_id"] in ids:
                recs[rec["step_id"]] = rec
    lookups = {d: L.load_lookups(d) for d in paths.DOMAINS}
    rule_sets = {d: load_rule_set(d) for d in paths.DOMAINS}
    states: Dict[str, Any] = {}
    items, problems = [], []
    for e in entries:
        row = e["row"]
        rec = recs[row["step_id"]]
        d = row["domain"]
        lk = lookups[d][row["predicate"]]
        if rec["step_id"] not in states:
            states[rec["step_id"]] = build_state(rec["history"], rec, domain=d)
        st = states[rec["step_id"]]
        rs = RecordingState(st)
        det = L.evaluate_detail(lk, rs, args=rec["kwargs"])
        if det["value"] != row["tracker_value"] or det["missing"] != row["tracker_missing"] or rs.reads != row["used"]:
            problems.append(f"{e['id']} {row['step_id']} {row['predicate']}: recomputed value differs from Part 6")
        if (rec["judge"].get(row["predicate"]) or {}).get("value") != row["judge_value"]:
            problems.append(f"{e['id']}: judge value differs from the step record")
        ctx = context(st, rs.reads, rec["kwargs"], rec["history"])
        hist = rec["history"]
        msg_of_tcid = {m.get("tool_call_id"): i for i, m in enumerate(hist) if m.get("role") == "tool"}
        msg_of_event = {ev["index"]: msg_of_tcid[ev["tool_call_id"]] for ev in st.events
                        if ev.get("tool_call_id") in msg_of_tcid}
        objs = [object_view(o, msg_of_event, _dates_in(rec["kwargs"])) for o in ctx["objects"]]
        ids = _ids_in(rec["kwargs"]) | {str(o["id"]) for o in ctx["objects"]}
        for o in ctx["objects"]:
            for v in (o.get("db"), o.get("shown")):
                if isinstance(v, dict) and v.get("user_id"):
                    ids.add(str(v["user_id"]))
        must = {msg_of_event[ev["index"]] for f in ctx["events"] for ev in f["events"] if ev["index"] in msg_of_event}
        for o in ctx["objects"]:                    # the output that showed the newest version of each object
            ev_index = (o.get("shown_by") or {}).get("event")
            if ev_index in msg_of_event:
                must.add(msg_of_event[ev_index])
        idx = select_messages(hist, {x for x in ids if len(x) >= 3}, must)
        near = {1} | set(range(max(1, len(hist) - LAST_N), len(hist)))
        excerpt = [message_view(i, hist[i], TOOL_CHARS if i in must else OTHER_TOOL_CHARS,
                                TEXT_CHARS if i in near else OTHER_TEXT_CHARS) for i in idx]
        expl = {"tracker": tracker_explanation(row, lk, objs, ctx, msg_of_event), "judge": judge_explanation(row)}
        vals = {"tracker": row["tracker_value"], "judge": row["judge_value"]}
        conv = f"{row['run']}/{d}/task{row['task']}/trial{row['trial']}"
        prev = longest.get(conv)
        if prev is None or len(hist) > prev[0]:
            longest[conv] = (len(hist), hist)
        items.append({
            "id": e["id"], "step": row["step_id"], "conversation": conv, "messages_before_step": len(hist),
            "domain": d, "predicate": row["predicate"], "type": row["type"],
            "description": rule_sets[d]["predicates"][row["predicate"]]["description"],
            "correct_means": correct_means(row["type"], row["uses"]),
            "pending_action": {"tool": rec["action"], "args": rec["kwargs"], "agent_text": rec.get("agent_text") or "",
                               "action_text": rec.get("action_text")},
            "today": st.today_text,
            "excerpt": excerpt, "excerpt_text": render_excerpt(excerpt, len(hist)),
            "objects": objs, "earlier_calls": event_view(ctx["events"], msg_of_event),
            "value_A": {"value": VALUE_TEXT[vals[e["A"]]], "explanation": expl[e["A"]]},
            "value_B": {"value": VALUE_TEXT[vals[e["B"]]], "explanation": expl[e["B"]]},
            "answer": None, "note": "",
        })
    convs = {}
    for conv, (_, hist) in sorted(longest.items()):
        d = conv.split("/")[1]
        convs[conv] = [{"role": "system", "content": f"(the policy: from_shieldagent/policies/{d}_wiki.txt)"}] + \
            [dict(m) for m in hist[1:]]
    return items, convs, problems


# ----------------------------------------------------------------------------------------------- sheet

def _json_block(x: Any) -> str:
    text = json.dumps(x, ensure_ascii=False)
    if len(text) > BIG_JSON:
        return f"<details><summary>JSON ({len(text):,} characters)</summary>\n\n```json\n{text}\n```\n\n</details>"
    return f"```json\n{text}\n```"


def render_sheet(items: List[dict], counts: Dict[str, int]) -> str:
    out: List[str] = []
    w = out.append
    w("# Part 7: review sheet")
    w("")
    w(f"Written by `state_tracker/p7_sample.py` on 2026-10-22. Seed: {SEED}. Items: {len(items)}.")
    w("")
    w("## What to do")
    w("Each item is one predicate value at one saved step of a τ-bench conversation, just before the pending action.")
    w("Two sources gave a value: **value A** and **value B**. One source is an LLM, the other is code. The sheet does")
    w("not say which is which; the order is random for each item. The two values can be equal or different.")
    w("")
    w("For each item, decide the correct value and fill in the **Answer** line with one of:")
    w("- `A right`: value A is correct and value B is not;")
    w("- `B right`: value B is correct and value A is not;")
    w("- `both right`: both values are correct;")
    w("- `both wrong`: neither value is correct;")
    w("- `predicate unclear`: the description does not settle the value. Say why in the note.")
    w("")
    w("Write a short reason in the **Note** line, for every item that is not `both right`.")
    w("")
    w("## What counts as correct")
    w("- For a predicate whose item says *fact*: the value in the database copy at that step.")
    w("- For a predicate whose item says *shown*: what the conversation had shown before the step.")
    w("- For an *argument* predicate: the pending call's arguments.")
    w("- In every case the predicate's description decides. If the description is unclear, mark `predicate unclear`.")
    w("- `unknown` is correct only if the correct value cannot be decided from the description, the conversation")
    w("  before the step and the database at that step.")
    w("- Judge the value only. Whether the action should be allowed is not part of the question.")
    w("")
    w("## What you may read")
    w("- This sheet, `output/p7_review_items.json` (the same items as data) and `output/p7_review_conversations.json`")
    w("  (the full conversations; message #k of an item is element k of its conversation, and only messages before")
    w("  `messages before step` count).")
    w("- The policies (`from_shieldagent/policies/`), the rule sets (`from_shieldagent/rules/`), and τ-bench's data and")
    w("  tool code (`from_shieldagent/tau_bench/`).")
    w("")
    w("Do **not** read `output/p7_key.json`, `output/p6_*`, `output/p5_*`, `output/steps_*.jsonl`,")
    w("`output/implementation_log.md`, `state_tracker/lookups_*.json`, the saved runs in `from_shieldagent/runs/`, or")
    w("anything in `~/ShieldAgent`. They show which value is which.")
    w("")
    w("## How each item is laid out")
    w("- **Step:** where it is (run/domain/task/trial/step/attempt) and how many messages came before it. Message #0")
    w("  is the policy and is not shown.")
    w("- **Conversation excerpt:** the first user message, the last 4 messages, every message that mentions an id in")
    w("  the pending call or in the objects below, and each tool call with its output. Long texts are cut; the full")
    w("  conversation is in `p7_review_conversations.json`.")
    w("- **Objects:** each database object that matters: its value in the database copy at this step, and whether")
    w("  (and by which message) the conversation had shown it.")
    w("- **Earlier calls:** earlier calls of the tools that matter, also the failed ones.")
    w("")
    w("## Index")
    w("")
    w("| id | domain | predicate | type |")
    w("|---|---|---|---|")
    for it in items:
        w(f"| [{it['id']}](#{it['id'].lower()}) | {it['domain']} | `{it['predicate']}` | {it['type']} |")
    w("")
    w("## Items")
    w("")
    for it in items:
        w(f"### {it['id']}")
        w("")
        w(f"- **Domain, predicate (type):** {it['domain']}, `{it['predicate']}` ({it['type']})")
        w(f"- **Description:** {it['description']}")
        w(f"- **What counts as correct:** {it['correct_means']}")
        w(f"- **Step:** `{it['step']}`; {it['messages_before_step']} messages before the step (#0-#"
          f"{it['messages_before_step'] - 1})" + (f"; the policy's current time: {it['today']}" if it["today"] else ""))
        pa = it["pending_action"]
        w(f"- **Pending action:** `{pa['tool']}` with arguments `{json.dumps(pa['args'], ensure_ascii=False)}`")
        if pa["agent_text"].strip():
            w(f"  - Agent's text with it: {_cut(pa['agent_text'], TEXT_CHARS)!r}")
        w("")
        w("**Conversation excerpt**")
        w("")
        w("````text")
        w(it["excerpt_text"])
        w("````")
        w("")
        w("**Objects**")
        w("")
        if not it["objects"]:
            w("No database object is read for this value.")
        for o in it["objects"]:
            w(f"- `{o['kind']}` `{o['id']}`: {o['shown_text']}.")
            w("")
            w("  Database value at this step:")
            w("")
            w(_indent(_json_block(o["db"]) if o["db"] is not None else "(none: not in the database)"))
            if o["shown"] is not None and "differs" in o["shown_text"]:
                w("")
                w("  Shown version:")
                w("")
                w(_indent(_json_block(o["shown"])))
            w("")
        if it["earlier_calls"]:
            w("**Earlier calls of the tools that matter**")
            w("")
            for c in it["earlier_calls"]:
                where = f"#{c['message']}" if c["message"] is not None else "(no message)"
                w(f"- {where} `{c['tool']}` `{json.dumps(c['args'], ensure_ascii=False)}`: "
                  f"{'worked' if c['worked'] else 'failed'}; output: {c['output']!r}")
            w("")
        for k in ("A", "B"):
            v = it[f"value_{k}"]
            w(f"**Value {k}: {v['value']}.** Explanation: {v['explanation']}")
            w("")
        w(f"**Answer** ({' / '.join(ANSWERS)}): ")
        w("")
        w("**Note:** ")
        w("")
        w("---")
        w("")
    return "\n".join(out) + "\n"


def _indent(text: str, n: int = 2) -> str:
    return "\n".join((" " * n + line) if line else line for line in text.split("\n"))


# ----------------------------------------------------------------------------------------------- answers

_ITEM_RE = re.compile(r"^### (P7-\d{3})\s*$", re.M)
_ANSWER_RE = re.compile(r"^\*\*Answer\*\* \([^)]*\):[ \t]*(.*)$", re.M)
_NOTE_RE = re.compile(r"^\*\*Note:\*\*[ \t]*(.*)$", re.M)


def normalize_answer(text: str) -> Optional[str]:
    """One of ANSWERS, None if empty; raises ValueError if it is something else."""
    t = re.sub(r"[`*\[\]_]", "", text or "").strip().lower().rstrip(".")
    if not t:
        return None
    for a in ANSWERS:
        if t == a.lower():
            return a
    raise ValueError(f"not an answer: {text!r}")


def read_answers(md_text: str) -> Dict[str, dict]:
    """id -> {"answer": one of ANSWERS or None, "note": text, "error": None or text}, from a filled-in sheet."""
    out: Dict[str, dict] = {}
    marks = list(_ITEM_RE.finditer(md_text))
    for i, m in enumerate(marks):
        body = md_text[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(md_text)]
        a = _ANSWER_RE.search(body)
        n = _NOTE_RE.search(body)
        entry = {"answer": None, "note": (n.group(1).strip() if n else ""), "error": None}
        if a is None:
            entry["error"] = "no Answer line"
        else:
            try:
                entry["answer"] = normalize_answer(a.group(1))
            except ValueError as e:
                entry["error"] = str(e)
        out[m.group(1)] = entry
    return out


def check_answers(path: str = SHEET_MD) -> int:
    with open(path, encoding="utf-8") as f:
        ans = read_answers(f.read())
    c = collections.Counter(v["answer"] for v in ans.values())
    bad = {k: v["error"] for k, v in ans.items() if v["error"]}
    print(f"items {len(ans)}; answered {sum(v for k, v in c.items() if k)}; empty {c[None] - len(bad)}; "
          f"invalid {len(bad)}")
    for a in ANSWERS:
        print(f"  {a}: {c[a]}")
    for k, e in sorted(bad.items()):
        print(f"  {k}: {e}")
    return 1 if bad else 0


# ----------------------------------------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true", help="overwrite a sheet that already has answers")
    ap.add_argument("--check-answers", action="store_true", help="only read the answers in the sheet and count them")
    a = ap.parse_args(argv)
    if a.check_answers:
        return check_answers()
    if os.path.exists(SHEET_MD) and not a.force:
        with open(SHEET_MD, encoding="utf-8") as f:
            filled = [k for k, v in read_answers(f.read()).items() if v["answer"] or v["note"]]
        if filled:
            print(f"{SHEET_MD} already has {len(filled)} answers or notes; not overwritten (use --force).")
            return 2
    shas = {d: sha256(L.lookups_path(d)) for d in paths.DOMAINS}
    if shas != FROZEN_SHA256:
        print(f"lookup files differ from the frozen ones: {shas}")
        return 2
    rows = load_values()
    sample = draw_sample(rows)
    entries = shuffle_and_blind(sample)
    items, convs, problems = build_items(entries)
    pop = collections.Counter()
    for r in rows:
        if r["agreement"] in DISAGREE:
            pop[STRATA[0] if r["blocked"] else STRATA[1]] += 1
        elif r["agreement"] in ("agree_true", "agree_false"):
            pop[STRATA[2]] += 1
    drawn = collections.Counter(e["stratum"] for e in entries)
    key = {
        "about": "Part 7 key: which value is the tracker's and which is the judge's. NOT for the reviewer.",
        "seed": SEED, "date": "2026-10-22", "n_other": N_OTHER, "n_agree": N_AGREE,
        "population": dict(pop), "sampled": dict(drawn),
        "lookup_sha256": shas,
        "items": [{"id": e["id"], "A": e["A"], "B": e["B"], "stratum": e["stratum"],
                   "step_id": e["row"]["step_id"], "predicate": e["row"]["predicate"], "type": e["row"]["type"],
                   "uses": e["row"]["uses"], "agreement": e["row"]["agreement"],
                   "tracker_value": e["row"]["tracker_value"], "judge_value": e["row"]["judge_value"],
                   "blocked": e["row"]["blocked"], "in_violated_rule": e["row"]["in_violated_rule"],
                   "judge_history_cut": e["row"]["judge_history_cut"], "group": e["row"]["group"]}
                  for e in entries],
    }
    with open(KEY_JSON, "w", encoding="utf-8") as f:
        json.dump(key, f, ensure_ascii=False, indent=1)
    with open(ITEMS_JSON, "w", encoding="utf-8") as f:
        json.dump({"about": "Part 7 review items (blind). Fill in the answers in output/p7_review_sheet.md.",
                   "seed": SEED, "answers": list(ANSWERS),
                   "items": [{k: v for k, v in it.items() if k != "excerpt_text"} for it in items]},
                  f, ensure_ascii=False, indent=1)
    with open(CONV_JSON, "w", encoding="utf-8") as f:
        json.dump(convs, f, ensure_ascii=False)
    with open(SHEET_MD, "w", encoding="utf-8") as f:
        f.write(render_sheet(items, dict(drawn)))
    print(f"population: {dict(pop)}")
    print(f"sampled: {dict(drawn)}; items {len(items)}; conversations {len(convs)}")
    print(f"A is the tracker in {sum(e['A'] == 'tracker' for e in entries)} items")
    print("by agreement:", dict(collections.Counter(e["row"]["agreement"] for e in entries)))
    print("by predicate:", dict(collections.Counter(e["row"]["predicate"] for e in entries).most_common()))
    print(f"problems: {len(problems)}")
    for p in problems[:20]:
        print("  ", p)
    for p in (SHEET_MD, ITEMS_JSON, CONV_JSON, KEY_JSON):
        print(f"wrote {p} ({os.path.getsize(p):,} bytes)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
