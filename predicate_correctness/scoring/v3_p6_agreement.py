"""Tracker v3, part 6 (docs/planning/tracker_v3/p6.md): the database, event and argument parts of the v3 facts,
checked against objective labels on the development data. No LLM call, no network, $0.

The expressions are the p6 overlays output/eval_v3/p6_parts/exprs_<domain>.json, merged in memory into the fact files
(state_tracker/v3/facts_v3_<domain>.json, read only); the helper names are state_tracker/v3/code_helpers.py.

Runs (one pass over every development conversation; preregistration.md, P6.1-P6.4):
  P6.1 agreement   each labelled write attempt (output/eval_v3/tool_labels.jsonl, joined on ckey; Stage B lines with
                   part "prefix" or "fork" are not checks of the try and are dropped): each fact of the label vs the v3
                   value (database facts: the fact; the two status facts: their database part b, because p3's label is
                   the world part only). Counts per fact and tool: agree / disagree / not decided by the tool.
                   Also (not a pass mark): extra parts that a tool check decides (derived from the label's `check` in
                   the tool's own check order), and return's "payment method not found" (p3: None; v3: false).
  P6.2 replay      every development conversation replayed on a fresh database copy: replayed output == saved output.
  P6.3 event log   at every check whose pending call has the key argument: each event part's value vs a raw scan of
                   the saved messages (tool call + tool message that does not start with 'Error').
  P6.4 harm sets   the 420 blocked checks of eval v2's TGR + tracker Stage A runs where a judge "unknown" became the
                   tracker's "false" (eval v2's v2_good_success.py offline(), re-derived here from the saved records), and
                   the 428 checks of output/eval_v2/stage_a_runs.md line 319 (weak agent: gift-card difference, judge
                   unknown -> tracker false, no changed decision; changed decisions from output/logs/v2_c6w_check.json).
                   For each: the fact's v3 value and the tool label.
  sanity           every code fact / part whose rules cover the pending tool, at every development check: values and
                   problems (missing_argument, missing_field, type_error, ...) per fact; evaluation errors.
  P5.4             a call with a nonexistent id (synthetic checks; nonexistent_id_table()): which rules block from the
                   p6 parts alone, and τ-bench's own Error for the calls no rule blocks.

Run from predicate_correctness/ (main() first checks the eval v2 manifest, then blocks the network):
    PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 /home/azureuser/miniconda3/bin/python3 -B -m scoring.v3_p6_agreement \
        > output/logs/v3_p6_<nn>_run.log 2>&1
Writes output/eval_v3/p6_tool_agreement.md and output/eval_v3/p6_parts/p6_run.json. Never imports gold code; never
reads the hold-out (only conversations with side "dev").
"""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
import os
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

sys.dont_write_bytecode = True

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_tracker import paths  # noqa: E402
from state_tracker import state as S  # noqa: E402
from state_tracker import tau_copy  # noqa: E402
from state_tracker.v3 import code_helpers as CH  # noqa: E402,F401  (registers the p6 helper names)
from state_tracker.v3 import facts_format_v3 as F  # noqa: E402
from state_tracker.v3 import tool_check as TC  # noqa: E402

PC = paths.PC_DIR
EVAL_V3 = os.path.join(paths.OUTPUT_DIR, "eval_v3")
P6_DIR = os.path.join(EVAL_V3, "p6_parts")
OVERLAY = os.path.join(P6_DIR, "exprs_{}.json")
LABELS = os.path.join(EVAL_V3, "tool_labels.jsonl")
REPORT = os.path.join(EVAL_V3, "p6_tool_agreement.md")
RUN_JSON = os.path.join(P6_DIR, "p6_run.json")
CHANGED_DECISIONS = os.path.join(paths.OUTPUT_DIR, "logs", "v2_c6w_check.json")
MINE = ("database", "event", "arguments")
GC_DIFF = TC.GC_DIFF
OWN_FILES = ("state_tracker/v3/code_helpers.py", "output/eval_v3/p6_parts/exprs_retail.json",
             "output/eval_v3/p6_parts/exprs_airline.json", "tests/test_v3_code_facts.py", "scoring/v3_p6_agreement.py")

# The event parts: fact -> (the tools whose worked call is the event, the argument that must match or None).
EVENT_SPECS = {
    "retail": {
        "user_authenticated": (("find_user_id_by_email", "find_user_id_by_name_zip"), None),
        "order_status_checked_pending": (("get_order_details",), "order_id"),
        "order_status_checked_delivered": (("get_order_details",), "order_id"),
    },
    "airline": {f: (("get_reservation_details",), "reservation_id") for f in (
        "airline_cancelled_flight_confirmed", "cancellation_is_within_24_hours", "origin_destination_and_trip_type_preserved",
        "pending_flight_segments_are_unchanged", "reservation_has_basic_or_economy_cabin", "reservation_has_business_cabin",
        "reservation_has_travel_insurance")},
}

# Extra parts a tool check decides (not in p3's list; not a pass mark): (fact, part) -> {tool: [deciding checks]}.
EXTRA = {
    ("cancellation_reason_is_allowed", "a"): {"cancel_pending_order": ["invalid_reason"]},
    ("user_chose_pending_payment_method", "d"): {"modify_pending_order_payment": ["payment_method_not_found"]},
    ("user_chose_price_difference_payment_method", "d"): {
        "modify_pending_order_items": ["payment_method_not_found"],
        "exchange_delivered_order_items": ["payment_method_not_found"]},
    ("user_selected_eligible_flight_change_payment_method", "a"): {
        "update_reservation_flights": ["payment_method_not_found", "certificate_not_allowed"]},
    ("cancellation_context_established", "a"): {"cancel_reservation": ["reservation_not_found"]},
    ("modification_user_and_reservation_ids_established", "a"): {
        "update_reservation_flights": ["reservation_not_found"], "update_reservation_baggages": ["reservation_not_found"],
        "update_reservation_passengers": ["reservation_not_found"]},
    ("return_refund_method_is_original_or_existing_gift_card", "*"): {
        "return_delivered_order_items": ["payment_method_not_found", "refund_method_not_allowed"]},
}


# ----------------------------------------------------------------------------------------------- the facts
def load_overlay(domain: str, path: Optional[str] = None) -> dict:
    with open(path or OVERLAY.format(domain), encoding="utf-8") as f:
        ov = json.load(f)
    if ov.get("domain") != domain or ov.get("by") != "p6" or not isinstance(ov.get("exprs"), dict):
        raise ValueError(f"{path or OVERLAY.format(domain)}: not a p6 overlay of {domain}")
    return ov


def merged_facts(domain: str, overlay: Optional[dict] = None) -> dict:
    """A copy of the domain's fact file with the p6 expressions filled in (the fact file is never written)."""
    doc = copy.deepcopy(F.load_facts(domain))
    ov = overlay if overlay is not None else load_overlay(domain)
    for fact, parts in ov["exprs"].items():
        for pid, x in parts.items():
            part = doc["facts"][fact]["parts"][pid]
            if part["source"] not in MINE:
                raise ValueError(f"{fact}.{pid}: source {part['source']!r} is not a p6 source")
            part["expr"] = x["expr"]
            if "if_nonexistent" in x:
                part["if_nonexistent"] = x["if_nonexistent"]
    return doc


def my_parts(entry: dict) -> List[str]:
    return [pid for pid, p in entry["parts"].items() if p["source"] in MINE]


def code_only(entry: dict) -> bool:
    return all(p["source"] in MINE for p in entry["parts"].values())


def part_entry(entry: dict, pid: str) -> dict:
    """The fact reduced to one of its parts (combine = that part), for a part of a mixed fact."""
    out = dict(entry)
    out["parts"] = {pid: entry["parts"][pid]}
    out["combine"] = pid
    out["sources"] = [entry["parts"][pid]["source"]]
    return out


def evaluate_code(doc: dict, fact: str, state: Any, args: Optional[dict] = None, part: Optional[str] = None) -> dict:
    """F.evaluate of a code-only fact (part None), or of one p6 part of any fact (part = its id)."""
    entry = doc["facts"][fact]
    if part is None:
        if not code_only(entry):
            raise ValueError(f"{fact} has parts that p6 does not write; give part=")
        return F.evaluate(entry, state, args, name=fact)
    return F.evaluate(part_entry(entry, part), state, args, name=f"{fact}.{part}")


def code_units(doc: dict) -> List[Tuple[str, Optional[str]]]:
    """(fact, None) for a code-only fact, (fact, part id) for each p6 part of a mixed fact."""
    out: List[Tuple[str, Optional[str]]] = []
    for fact, e in doc["facts"].items():
        if code_only(e):
            out.append((fact, None))
        else:
            out += [(fact, pid) for pid in my_parts(e)]
    return out


def rule_table(domain: str) -> dict:
    with open(F.rule_table_path(domain), encoding="utf-8") as f:
        return json.load(f)


def fact_tools(domain: str) -> Dict[str, set]:
    """fact -> the actions of the rules it is in."""
    out: Dict[str, set] = collections.defaultdict(set)
    for r in rule_table(domain)["rules"]:
        for f in r["facts"]:
            out[f].update(r["actions"])
    return dict(out)


# ----------------------------------------------------------------------------------------------- tiny conversations
def conversation(domain: str, calls: Iterable[Tuple[str, dict]], user_text: str = "hi") -> List[dict]:
    """System, user, then per call an assistant tool call and its tool message; each output made by τ-bench's own
    tool code on a separate copy of the data (as tests/test_state.py)."""
    db = S.load_db(domain)
    msgs = [{"role": "system", "content": tau_copy.policy_text(domain)}, {"role": "user", "content": user_text}]
    for i, (name, args) in enumerate(calls):
        out = S.run_tool(domain, db, name, copy.deepcopy(args))
        msgs.append({"role": "assistant", "content": None, "tool_calls": [
            {"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "name": name, "content": out})
    return msgs


def state_for(domain: str, calls: Iterable[Tuple[str, dict]], tool: str, args: dict):
    return S.build_state(conversation(domain, calls), {"tool": tool, "args": args}, domain=domain)


# ----------------------------------------------------------------------------------------------- P5.4: nonexistent ids
NO_ORDER, NO_USER, NO_PRODUCT, NO_ITEM = "#W0000000", "nobody_00000", "0000000000", "0000000001"
NO_GC, NO_CC = "gift_card_0000000", "credit_card_0000000"
NO_RES, NO_FLIGHT = "ZZZZZZ", "HAT000"


def retail_sample() -> dict:
    """A user with a pending order (whose first item has another available variant), a delivered order (same), a
    gift card that is not the pending order's original method, and a method of another kind (data, read only)."""
    db = S.load_db("retail")

    def swap(order):
        it = order["items"][0]
        vs = db["products"][it["product_id"]]["variants"]
        return next((v for v, x in sorted(vs.items()) if v != it["item_id"] and x["available"]), None)

    for uid in sorted(db["users"]):
        u = db["users"][uid]
        orders = [db["orders"][o] for o in u["orders"] if o in db["orders"]]
        pend = next((o for o in orders if o["status"] == "pending" and swap(o)), None)
        deliv = next((o for o in orders if o["status"] == "delivered" and swap(o)), None)
        gcs = sorted(p for p, m in u["payment_methods"].items() if m["source"] == "gift_card")
        others = sorted(p for p, m in u["payment_methods"].items() if m["source"] != "gift_card")
        if not (pend and deliv and gcs and others):
            continue
        gc = next((g for g in gcs if g != pend["payment_history"][0]["payment_method_id"]), None)
        if gc is None:
            continue
        prod = pend["items"][0]["product_id"]
        return {"user": uid, "email": u["email"], "first": u["name"]["first_name"], "last": u["name"]["last_name"],
                "zip": u["address"]["zip"], "pending": pend["order_id"], "p_item": pend["items"][0]["item_id"],
                "p_new": swap(pend), "delivered": deliv["order_id"], "d_item": deliv["items"][0]["item_id"],
                "d_new": swap(deliv), "d_orig": deliv["payment_history"][0]["payment_method_id"], "gc": gc,
                "other": others[0], "product": prod}
    raise RuntimeError("no retail sample user")


def airline_sample() -> dict:
    """A user with a reservation whose flights are all in the schedule, and a credit card."""
    db = S.load_db("airline")
    for uid in sorted(db["users"]):
        u = db["users"][uid]
        cc = sorted(p for p, m in u["payment_methods"].items() if m["source"] == "credit_card")
        for rid in u["reservations"]:
            r = db["reservations"].get(rid)
            if not r or not cc or not r["flights"]:
                continue
            fl = r["flights"]
            if any(f["flight_number"] not in db["flights"] for f in fl):
                continue
            days = db["flights"][fl[0]["flight_number"]]["dates"]
            dates = [d for d in sorted(days) if d != fl[0]["date"] and days[d]["status"] == "available"
                     and days[d]["available_seats"][r["cabin"]] >= len(r["passengers"])]
            if not dates:
                continue
            return {"user": uid, "res": rid, "cc": cc[0], "cabin": r["cabin"],
                    "flights": [{"flight_number": f["flight_number"], "date": f["date"]} for f in fl],
                    "moved": [{"flight_number": f["flight_number"], "date": dates[0] if k == 0 else f["date"]}
                              for k, f in enumerate(fl)],
                    "passengers": [{k: p[k] for k in ("first_name", "last_name", "dob")} for p in r["passengers"]],
                    "origin": r["origin"], "destination": r["destination"], "flight_type": r["flight_type"],
                    "total_bags": r["total_baggages"], "nonfree_bags": r["nonfree_baggages"],
                    "name": u["name"], "dob": u["dob"]}
    raise RuntimeError("no airline sample user")


def nonexistent_cases(domain: str) -> Tuple[List[Tuple[str, dict]], List[Tuple[str, str, dict]]]:
    """(the calls before the check, [(action, variant, args)]): each variant makes one id of a valid call nonexistent."""
    if domain == "retail":
        s = retail_sample()
        before = [("find_user_id_by_email", {"email": s["email"]}), ("get_user_details", {"user_id": s["user"]}),
                  ("get_order_details", {"order_id": s["pending"]}), ("get_order_details", {"order_id": s["delivered"]}),
                  ("get_order_details", {"order_id": NO_ORDER}), ("get_product_details", {"product_id": s["product"]})]
        addr = {"address1": "1 Main St", "address2": "", "city": "Austin", "state": "TX", "country": "USA",
                "zip": "78701"}
        base = {
            "find_user_id_by_email": {"email": s["email"]},
            "find_user_id_by_name_zip": {"first_name": s["first"], "last_name": s["last"], "zip": s["zip"]},
            "get_user_details": {"user_id": s["user"]},
            "get_order_details": {"order_id": s["pending"]},
            "get_product_details": {"product_id": s["product"]},
            "cancel_pending_order": {"order_id": s["pending"], "reason": "no longer needed"},
            "modify_pending_order_address": dict(order_id=s["pending"], **addr),
            "modify_pending_order_items": {"order_id": s["pending"], "item_ids": [s["p_item"]],
                                           "new_item_ids": [s["p_new"]], "payment_method_id": s["gc"]},
            "modify_pending_order_payment": {"order_id": s["pending"], "payment_method_id": s["gc"]},
            "modify_user_address": dict(user_id=s["user"], **addr),
            "return_delivered_order_items": {"order_id": s["delivered"], "item_ids": [s["d_item"]],
                                             "payment_method_id": s["d_orig"]},
            "exchange_delivered_order_items": {"order_id": s["delivered"], "item_ids": [s["d_item"]],
                                               "new_item_ids": [s["d_new"]], "payment_method_id": s["gc"]},
        }
        repl = {"order_id": NO_ORDER, "user_id": NO_USER, "product_id": NO_PRODUCT,
                "email": "nobody.at.all@example.com", "item_ids": [NO_ITEM], "new_item_ids": [NO_ITEM]}
        out = []
        for action, args in base.items():
            for key in args:
                if key in repl:
                    out.append((action, key, dict(args, **{key: repl[key]})))
                if key == "payment_method_id":
                    out.append((action, "payment_method_id (gift card form)", dict(args, payment_method_id=NO_GC)))
                    out.append((action, "payment_method_id (credit card form)", dict(args, payment_method_id=NO_CC)))
            if action == "find_user_id_by_name_zip":
                out.append((action, "first_name, last_name, zip", {"first_name": "Nobody", "last_name": "Atall",
                                                                    "zip": "00000"}))
        return before, out
    s = airline_sample()
    before = [("get_user_details", {"user_id": s["user"]}), ("get_reservation_details", {"reservation_id": s["res"]}),
              ("get_reservation_details", {"reservation_id": NO_RES})]
    pax = [{"first_name": s["name"]["first_name"], "last_name": s["name"]["last_name"], "dob": s["dob"]}]
    base = {
        "book_reservation": {"user_id": s["user"], "origin": s["origin"], "destination": s["destination"],
                             "flight_type": "one_way", "cabin": "economy", "flights": s["flights"][:1],
                             "passengers": pax, "payment_methods": [{"payment_id": s["cc"], "amount": 100}],
                             "total_baggages": 0, "nonfree_baggages": 0, "insurance": "no"},
        "update_reservation_flights": {"reservation_id": s["res"], "cabin": s["cabin"], "flights": s["moved"],
                                       "payment_id": s["cc"]},
        "update_reservation_baggages": {"reservation_id": s["res"], "total_baggages": s["total_bags"] + 1,
                                        "nonfree_baggages": s["nonfree_bags"], "payment_id": s["cc"]},
        "update_reservation_passengers": {"reservation_id": s["res"], "passengers": s["passengers"]},
        "cancel_reservation": {"reservation_id": s["res"]},
        "send_certificate": {"user_id": s["user"], "amount": 100},
    }
    out = []
    for action, args in base.items():
        for key in args:
            if key == "reservation_id":
                out.append((action, key, dict(args, reservation_id=NO_RES)))
            if key == "user_id":
                out.append((action, key, dict(args, user_id=NO_USER)))
            if key == "payment_id":
                out.append((action, key, dict(args, payment_id=NO_CC)))
            if key == "payment_methods":
                out.append((action, "payment_methods[0].payment_id",
                            dict(args, payment_methods=[{"payment_id": NO_CC, "amount": 100}])))
            if key == "flights":
                fl = copy.deepcopy(args["flights"])
                fl[0]["flight_number"] = NO_FLIGHT
                out.append((action, "flights[0].flight_number", dict(args, flights=fl)))
    return before, out


def rule_outcome(rule: dict, values: Dict[str, Optional[bool]]) -> str:
    """'blocks' when every row that agrees with the known values fails, 'allows' when every one holds, else 'depends'
    (a fact p6 does not decide could tip it)."""
    rows = [r for r in rule["rows"] if all(values.get(f) is None or r["values"][f] == values[f] for f in rule["facts"])]
    holds = {r["holds"] for r in rows}
    if holds == {False}:
        return "blocks"
    if holds == {True}:
        return "allows"
    return "depends"


def fact_value_from_parts(doc: dict, fact: str, state: Any, args: dict) -> Tuple[Optional[bool], List[dict]]:
    """The fact's value as far as the p6 parts decide it (None: a part p6 does not write could tip it), and problems."""
    e = doc["facts"][fact]
    if code_only(e):
        r = F.evaluate(e, state, args, name=fact)
        return r["value"], r["problems"]
    mine = my_parts(e)
    if not mine:
        return None, []
    known: Dict[str, Optional[bool]] = {}
    probs: List[dict] = []
    for pid in mine:
        if e.get("for_each"):
            return None, []                              # per-item combine: p6 cannot decide it alone
        r = F.evaluate(part_entry(e, pid), state, args, name=f"{fact}.{pid}")
        if r["problems"]:
            return e["blocking_value"], r["problems"]
        known[pid] = r["value"]
    return F.combine_value(F.parse_combine(e["combine"]), known), probs


def nonexistent_id_table(domain: str, doc: Optional[dict] = None) -> List[dict]:
    """One row per (rule, action, variant) of nonexistent_cases(): the rule's facts as the p6 parts decide them, the
    rule's outcome, and τ-bench's own output for the call (on a copy)."""
    doc = doc or merged_facts(domain)
    before, cases = nonexistent_cases(domain)
    table = rule_table(domain)
    rows = []
    for action, variant, args in cases:
        st = state_for(domain, before, action, args)
        tau = TC.run_on_copy(st, action, args)
        for rule in table["rules"]:
            if action not in rule["actions"]:
                continue
            values, probs = {}, []
            for f in rule["facts"]:
                v, p = fact_value_from_parts(doc, f, st, args)
                values[f] = v
                probs += p
            rows.append({"rule": rule["id"], "action": action, "variant": variant, "values": values,
                         "outcome": rule_outcome(rule, values), "problems": [p["kind"] for p in probs],
                         "tau_output": tau if S.is_failure(tau) else "accepted"})
    return rows


# ----------------------------------------------------------------------------------------------- raw event scan
def raw_worked_calls(history: List[dict]) -> List[Tuple[str, Any]]:
    """(tool name, arguments) of every call in the saved messages whose tool message is a text that does not start
    with 'Error' or 'Unknown action'. Read from the messages only (not from the state's event log)."""
    calls: Dict[Any, Tuple[str, Any]] = {}
    out: List[Tuple[str, Any]] = []
    for m in history:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                raw = fn.get("arguments")
                try:
                    a = raw if isinstance(raw, dict) else json.loads(raw or "{}")
                except (TypeError, ValueError):
                    a = None
                calls[tc.get("id")] = (fn.get("name"), a)
        elif m.get("role") == "tool" and m.get("tool_call_id") in calls:
            c = m.get("content")
            if isinstance(c, str) and not c.startswith("Error") and not c.startswith("Unknown action"):
                out.append(calls[m["tool_call_id"]])
    return out


def raw_event(history: List[dict], tools: Tuple[str, ...], key: Optional[str], value: Any) -> bool:
    return any(name in tools and (key is None or (isinstance(a, dict) and key in a and a[key] == value))
               for name, a in raw_worked_calls(history))


# ----------------------------------------------------------------------------------------------- labels
def derived_label(tool: str, failed: Optional[str], deciding: List[str]) -> Optional[bool]:
    """As tool_check.label_output, for a part p3 does not list: False at a deciding check, True when the tool passed
    every deciding check, None when an earlier (or an unlisted) check failed first."""
    if failed in (TC.OTHER, TC.AMBIGUOUS):
        return None
    if failed is None:
        return True
    if failed in deciding:
        return False
    order = [n for n, _, _ in TC.TOOL_CHECKS[tool]]
    return True if max(order.index(d) for d in deciding) < order.index(failed) else None


def load_labels(path: str = LABELS) -> Dict[str, dict]:
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                ln = json.loads(line)
                if ln.get("part") in ("prefix", "fork"):
                    continue
                out[ln["ckey"]] = ln
    return out


def changed_decisions(path: str = CHANGED_DECISIONS) -> set:
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return {(x["task"], x["attempt_idx"]) for x in d["guards"]["tgr_tracker"]["tracker"]["changed_decisions"]}


def harm_flips(check: Any) -> Tuple[List[str], List[str]]:
    """(flipped facts of the 420 definition, flipped facts of the 428 definition) for one saved check."""
    if not check.dataset.startswith("stage_a.") or not check.dataset.endswith(".tgr_tracker"):
        return [], []
    g = check.saved
    tr = g.get("tracker") or {}
    jv = tr.get("judge_values")
    used = {n: (v or {}).get("value") for n, v in (g.get("judge") or {}).items()}
    src = {n: (v or {}).get("source") for n, v in (g.get("judge") or {}).items()}
    f420: List[str] = []
    if check.blocked and g.get("judge") and jv is not None:
        f420 = sorted(n for n in used if jv.get(n) is None and used[n] is False and src.get(n) == "tracker")
    f428: List[str] = []
    if check.dataset == "stage_a.nano.tgr_tracker" and GC_DIFF in (tr.get("changed") or []):
        if (jv or {}).get(GC_DIFF) is None and used.get(GC_DIFF) is False:
            f428 = [GC_DIFF]
    return f420, f428


# ----------------------------------------------------------------------------------------------- the pass
class Tally:
    def __init__(self):
        self.agree = collections.Counter()           # (fact, tool, class)
        self.disagree_rows: List[dict] = []
        self.extra = collections.Counter()           # (fact, part, tool, class)
        self.extra_rows: List[dict] = []
        self.refund_check3: List[dict] = []
        self.events = collections.Counter()          # (fact, class)
        self.event_rows: List[dict] = []
        self.sanity = collections.Counter()          # (fact, part, what)
        self.problem_examples: Dict[tuple, str] = {}  # (fact, part, kind) -> the first check with that problem
        self.empty_items = collections.Counter()     # (tool, accepted?) for calls with item_ids == []
        self.errors: List[str] = []
        self.replay = collections.Counter()
        self.harm420: List[dict] = []
        self.harm428: List[dict] = []
        self.harm428_changed = 0
        self.v2wrong: List[dict] = []                # v2 tracker value != tool label (p4 section 3)
        self.convs = collections.Counter()
        self.checks = collections.Counter()


def _cls(label: Optional[bool], mine: Optional[bool]) -> str:
    if label is None:
        return "undecided"
    if mine is None:
        return "problem"
    return "agree" if label == mine else "disagree"


def run_pass(limit: Optional[int] = None, datasets: Optional[List[str]] = None, progress: bool = True) -> Tally:
    from fork import offline_v3 as O                  # imported here: the tests only need the helpers above
    labels = load_labels()
    chd = changed_decisions()
    docs = {d: merged_facts(d) for d in paths.DOMAINS}
    units = {d: code_units(docs[d]) for d in paths.DOMAINS}
    ftools = {d: fact_tools(d) for d in paths.DOMAINS}
    T = Tally()
    t0 = time.time()
    n_conv = 0
    if datasets is None:                              # the two val data sets (hold-out) are never opened
        datasets = [d for d in O.DATASETS if O.side_of(d) == O.DEV or d == "stage_b"]
    for conv in O.iter_conversations(datasets):
        if conv.side != "dev":                        # Stage B tries forked from a val conversation
            T.convs["hold-out Stage B tries skipped"] += 1
            continue
        if limit and T.convs[conv.dataset] >= limit:
            continue
        T.convs[conv.dataset] += 1
        n_conv += 1
        domain, doc = conv.domain, docs[conv.domain]
        checks = list(conv.checks())
        by_n: Dict[int, list] = collections.defaultdict(list)
        for ch in checks:
            by_n[len(ch.history)].append(ch)
        executed = conv.ep["executed"]
        stops = sorted(set(by_n) | {len(executed)})
        for n, st in S.walk(executed, domain=domain, stops=stops):
            for ch in by_n.get(n, []):
                try:
                    one_check(ch, st, doc, domain, units[domain], ftools[domain], labels, chd, T)
                except Exception as e:                # noqa: BLE001 - counted, never silent
                    T.errors.append(f"{ch.ckey}: {type(e).__name__}: {e}")
                st.pending = None
            if n == len(executed):
                T.replay["conversations"] += 1
                T.replay["replayed tool calls"] += len(st.events)
                T.replay["mismatches"] += len(st.mismatches)
                T.replay["parse problems"] += len(st.parse_problems)
                T.replay["problems"] += len(st.problems)
        if progress and n_conv % 250 == 0:
            print(f"{n_conv} conversations, {sum(T.checks.values())} checks, {time.time() - t0:.0f} s", flush=True)
    return T


def one_check(ch: Any, st: Any, doc: dict, domain: str, units: list, ftools: dict, labels: dict, chd: set,
              T: Tally) -> None:
    from fork import offline_v3 as O
    tool, args = O.call_of(ch.msg)
    st.pending = S.normalize_action((tool, args))
    T.checks[ch.dataset] += 1
    cache: Dict[Tuple[str, Optional[str]], dict] = {}

    def ev(fact: str, part: Optional[str]) -> dict:
        k = (fact, part)
        if k not in cache:
            cache[k] = evaluate_code(doc, fact, st, args, part)
        return cache[k]

    # sanity: every code unit whose rules cover the pending tool
    for fact, part in units:
        if tool not in ftools.get(fact, ()):
            continue
        r = ev(fact, part)
        key = (fact, part or "*")
        T.sanity[key + ("checks",)] += 1
        T.sanity[key + ("value " + str(r["value"]).lower(),)] += 1
        for p in r["problems"]:
            T.sanity[key + ("problem " + p["kind"],)] += 1
            ex = key + (p["kind"],)
            if ex not in T.problem_examples:
                T.problem_examples[ex] = f"`{ch.ckey}` ({tool}): {str(p['detail'])[:160]}"
    if tool in ("modify_pending_order_items", "exchange_delivered_order_items") and isinstance(args, dict) \
            and args.get("item_ids") == []:
        T.empty_items[(tool, "accepted by the tool" if (labels.get(ch.ckey) or {}).get("accepted") else
                       "refused or not labelled")] += 1
    # P6.3: event parts
    for fact, (tools, key) in EVENT_SPECS[domain].items():
        if key is not None and (not isinstance(args, dict) or key not in args):
            continue
        r = ev(fact, "a")
        mine = r["value"] if not r["problems"] else None
        raw = raw_event(ch.history, tools, key, None if key is None else args[key])
        c = "agree" if mine == raw else ("problem" if mine is None else "disagree")
        T.events[(fact, c)] += 1
        T.events[(fact, "raw true" if raw else "raw false")] += 1
        if c != "agree" and len(T.event_rows) < 50:
            T.event_rows.append({"ckey": ch.ckey, "fact": fact, "mine": mine, "raw": raw, "problems": r["problems"]})
    # P6.1: the tool labels
    lab = labels.get(ch.ckey)
    if lab is not None:
        if lab["tool"] != tool:
            T.errors.append(f"{ch.ckey}: label tool {lab['tool']} != message tool {tool}")
        for fact, lv in lab["facts"].items():
            r = ev(fact, "b") if fact in TC.WORLD_PART_ONLY else ev(fact, None)
            mine = r["value"] if not (fact in TC.WORLD_PART_ONLY and r["problems"]) else None
            c = _cls(lv, mine)
            T.agree[(fact, tool, c)] += 1
            if r["problems"]:
                T.agree[(fact, tool, "with a problem: " + ",".join(sorted({p["kind"] for p in r["problems"]})))] += 1
            if c in ("disagree", "problem"):
                T.disagree_rows.append({"ckey": ch.ckey, "fact": fact, "tool": tool, "label": lv, "mine": mine,
                                        "check": lab["check"], "first_error": lab["first_error"],
                                        "problems": r["problems"]})
            saved = ((ch.saved.get("judge") or {}).get(fact) or {})
            if saved.get("source") == "tracker" and lv is not None and saved.get("value") is not None \
                    and saved.get("value") != lv:
                T.v2wrong.append({"ckey": ch.ckey, "family": "stage_b" if ch.dataset == "stage_b" else "main",
                                  "fact": fact, "tool": tool, "label": lv, "v2": saved.get("value"), "v3": mine})
        for (fact, part), by_tool in EXTRA.items():
            if tool not in by_tool:
                continue
            lv = derived_label(tool, lab["check"], by_tool[tool])
            r = ev(fact, None if part == "*" else part)
            c = _cls(lv, r["value"])
            T.extra[(fact, part, tool, c)] += 1
            if c in ("disagree", "problem") and len(T.extra_rows) < 50:
                T.extra_rows.append({"ckey": ch.ckey, "fact": fact, "part": part, "tool": tool, "derived": lv,
                                     "mine": r["value"], "check": lab["check"], "problems": r["problems"]})
        if tool == "return_delivered_order_items" and lab["check"] == "payment_method_not_found":
            r = ev(TC.REFUND, None)
            T.refund_check3.append({"ckey": ch.ckey, "p3": lab["facts"].get(TC.REFUND), "v3": r["value"],
                                    "check": lab["check"]})
    # P6.4: the harm sets
    f420, f428 = harm_flips(ch)
    for flips, rows, which in ((f420, T.harm420, 420), (f428, T.harm428, 428)):
        if which == 428 and flips and (ch.conv.task_id, ch.check_idx) in chd:
            T.harm428_changed += 1
            continue
        for fact in flips:
            r = ev(fact, None) if code_only(doc["facts"][fact]) else None
            lv = (lab or {}).get("facts", {}).get(fact) if lab else None
            viol = [str(v.get("rule_id")) for v in ch.saved.get("violated_rules") or []]
            rows.append({"ckey": ch.ckey, "dataset": ch.dataset, "task": ch.conv.task_id, "attempt": ch.check_idx,
                         "tool": tool, "fact": fact, "v3": None if r is None else r["value"],
                         "v3_problems": [] if r is None else [p["kind"] for p in r["problems"]],
                         "label": lv, "labelled": lab is not None, "violated_rules": viol,
                         "payment_is_gift_card": isinstance(args, dict)
                         and "gift_card" in str(args.get("payment_method_id"))})


# ----------------------------------------------------------------------------------------------- report
NOTES = """
**Bugs found and fixed in p6's own files** (during development; the agreement run found no disagreement with
τ-bench's tool, so no expression was changed because of P6.1, and p6 needs no pre-registration change-log line):

1. Retail overlay: `request_is_for_another_user` part a used `me` as a loop variable. p7 registers `me` as a helper
   name, so the merged retail file failed the validator (p8's check). Renamed to `u`. `first_login_user()` now strips
   the login output exactly as p7's retail `me()` does; a test checks both give the same user.
2. Test `test_reservation_exists_parts` gave `cancel_reservation` an extra `passengers` argument (τ-bench raised an
   exception, check "other"): a test bug, fixed in the test (the failure the 01:58 audit run saw).
3. The nonexistent-id table first moved the airline sample's flight to a past date, so τ-bench refused the base
   call itself; now an available date is picked, and a test checks that τ-bench accepts each base call.
4. The report text named two eval v2 scripts with their folder prefix, which the no-gold text scan refuses; reworded.

**Notes for the main chat** (no definition was changed):

a. **Import.** The p6 names exist only after `import state_tracker.v3.code_helpers` (facts_format_v3 does not import
   it). The merge / validator step, p9's guard and p10 must import it (with p7's `message_view` and p8's
   `questions`) before validating or evaluating the merged files; otherwise the parts raise NotDefinedYet. Smallest
   fix: one import line where the merged files are used.
b. **The pending tool.** Two parts read the pending call's tool (`state.pending`): the gift-card difference (each
   tool's rounding) and `request_is_for_another_user` part a (which object the call is about). evaluate() needs a
   state built with the pending action (`build_state(history, action)`); without one the fact takes its blocking
   value (problem `no_pending_call`).
c. **`me`.** p6's `first_login_user()` equals p7's retail `me()` (test). After the merge one name could serve both.
d. **Return, check 3** ("payment method not found"): p3's label is None, the v3 definition gives false (see
   section 2). Smallest fix if wanted: map check 3 to False for this fact in p3's tool_check (not needed for P6.1).
e. **Reading choices where the plain text leaves room** (flagged, not changed):
   - gift-card difference: item lists of different length cannot be priced, so false (τ-bench refuses them anyway);
   - item replacements: an empty item list is false (p5's flag; τ-bench accepts it; the count of such calls in
     the development data is in section 6; P6.1 found no disagreement);
   - passenger identity part b: exact, case-sensitive equality ("equals");
   - bag counts: an unknown cabin or a count that is not a whole number >= 0 takes the blocking value (problems
     `unknown_cabin`, `bad_count`);
   - a reservation segment missing from the flights table is a missing field (a bug, counted; 0 in the data).
f. **P5.4: calls with a nonexistent id that no rule blocks from p6's parts** (section 7; τ-bench refuses every one,
   with the Error shown there): retail reads (get_order_details, get_product_details) and find_user_id_* (their other
   rules depend on p7 / p8 parts); a return with an item not in the order (no v3 fact checks it, p5 retail note 6);
   airline book_reservation with an unknown flight and update_reservation_baggages with a payment method not in the
   profile (rule-set gaps, p5 airline part A note 6); send_certificate for a nonexistent user (rules 28-30 depend on
   p7 / p8 parts).
"""


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def _rules_of(domain: str) -> Dict[str, List[str]]:
    """rule id -> its facts."""
    return {r["id"]: r["facts"] for r in rule_table(domain)["rules"]}


def write_report(T: Tally, ne: Dict[str, List[dict]], seconds: float, argv: List[str], manifest_files: int,
                 net_attempts: int, path: str = REPORT) -> dict:
    docs = {d: merged_facts(d) for d in paths.DOMAINS}
    L: List[str] = []
    w = L.append
    w("# Tracker v3 part 6: database, event and argument facts vs τ-bench's tool")
    w("")
    w(f"Written by `scoring/v3_p6_agreement.py` on {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. "
      "No LLM call, no network, $0. Development data only (side \"dev\"); nothing of the hold-out is evaluated.")
    w("")
    w("**In short.** p6 wrote the expressions of every database, event and argument part of the 66 facts (overlays "
      "`output/eval_v3/p6_parts/exprs_<domain>.json`; helper names in `state_tracker/v3/code_helpers.py`). Each part "
      "was then checked against an objective label: τ-bench's own tool check (p3 labels), the replay, and a raw scan "
      "of the saved messages.")
    w("")
    # ---- counts of parts
    w("## 1. What p6 wrote")
    w("")
    w("| domain | facts with a p6 part | of these: only p6 parts | p6 parts: database / event / arguments |")
    w("|---|---|---|---|")
    summary = {}
    for d in paths.DOMAINS:
        doc = docs[d]
        with_p6 = [f for f, e in doc["facts"].items() if my_parts(e)]
        only = [f for f in with_p6 if code_only(doc["facts"][f])]
        src = collections.Counter(doc["facts"][f]["parts"][p]["source"] for f in with_p6
                                  for p in my_parts(doc["facts"][f]))
        summary[d] = {"facts": len(with_p6), "code_only": len(only), "parts": dict(src)}
        w(f"| {d} | {len(with_p6)} | {len(only)} | {src['database']} / {src['event']} / {src['arguments']} |")
    w("")
    w("Helper names (registered at import of `state_tracker.v3.code_helpers`): "
      + ", ".join(f"`{n}` ({s})" for n, _, _, _, s, _ in CH.HELPERS) + ".")
    w("")
    # ---- P6.1
    w("## 2. P6.1: database facts vs τ-bench's tool (p3 labels)")
    w("")
    w("Every labelled development write attempt (`tool_labels.jsonl`, joined on ckey; Stage B `prefix` / `fork` lines "
      "dropped: they are not checks of the try). Label None = not decided by the tool (an earlier check failed, or the "
      "tool does not check that part): counted apart, never as agreement. The status facts are compared on their "
      "database part b (p3's label is the world part only).")
    w("")
    w("| fact | tool | agree | disagree | not decided by the tool | v3 value with a problem |")
    w("|---|---|---|---|---|---|")
    keys = sorted({(f, t) for f, t, _ in T.agree})
    tot = collections.Counter()
    for f, t in keys:
        a, dd, u = T.agree[(f, t, "agree")], T.agree[(f, t, "disagree")] + T.agree[(f, t, "problem")], \
            T.agree[(f, t, "undecided")]
        pr = sum(v for (f2, t2, c), v in T.agree.items() if f2 == f and t2 == t and c.startswith("with a problem"))
        tot.update({"agree": a, "disagree": dd, "undecided": u, "problem": pr})
        w(f"| `{f}` | {t} | {a:,} | {dd:,} | {u:,} | {pr:,} |")
    w(f"| **all** | | **{tot['agree']:,}** | **{tot['disagree']:,}** | {tot['undecided']:,} | {tot['problem']:,} |")
    w("")
    w(f"**P6.1: {tot['disagree']} disagreements** on {tot['agree'] + tot['disagree']:,} fact values the tool decides.")
    if T.disagree_rows:
        w("")
        w("Disagreements (first 30):")
        w("")
        for r in T.disagree_rows[:30]:
            w(f"- `{r['ckey']}` {r['fact']} ({r['tool']}): label {r['label']}, v3 {r['mine']}, check {r['check']}, "
              f"problems {[p['kind'] for p in r['problems']]}")
    probs = sorted({c for (_, _, c) in T.agree if c.startswith("with a problem")})
    if probs:
        w("")
        w("v3 values with a problem (the fact took its blocking value): "
          + "; ".join(f"{c[len('with a problem: '):]} {sum(v for (_, _, c2), v in T.agree.items() if c2 == c)}"
                      for c in probs) + ".")
    w("")
    w("### Extra parts a tool check decides (not a pass mark)")
    w("")
    w("Derived from the label's `check` in the tool's own check order (as `tool_check.label_output`).")
    w("")
    w("| fact (part) | tool | deciding check(s) | agree | disagree | not decided |")
    w("|---|---|---|---|---|---|")
    for (fact, part), by_tool in EXTRA.items():
        for t, dec in by_tool.items():
            a = T.extra[(fact, part, t, "agree")]
            dd = T.extra[(fact, part, t, "disagree")] + T.extra[(fact, part, t, "problem")]
            u = T.extra[(fact, part, t, "undecided")]
            if a + dd + u:
                w(f"| `{fact}` ({'the fact' if part == '*' else 'part ' + part}) | {t} | {', '.join(dec)} | {a:,} | "
                  f"{dd:,} | {u:,} |")
    for r in T.extra_rows[:20]:
        w(f"- extra disagreement `{r['ckey']}` {r['fact']}.{r['part']} ({r['tool']}): derived {r['derived']}, v3 "
          f"{r['mine']}, check {r['check']}")
    w("")
    w("### The v2 tracker's errors (p4 audit, section 3), re-derived")
    w("")
    w("Labelled checks of TGR + tracker sources where the saved tracker value (source \"tracker\") differs from the "
      "tool label the tool decides (v2 read \"never shown\" as false, or a shown version that differs from the "
      "database). The v3 value on the same checks:")
    w("")
    w("| part of the data | fact | checks | v2 false, tool true / v2 true, tool false | v3 = tool label |")
    w("|---|---|---|---|---|")
    vw = collections.defaultdict(collections.Counter)
    for r in T.v2wrong:
        k = (r["family"], r["fact"])
        vw[k]["n"] += 1
        vw[k]["ft" if r["v2"] is False else "tf"] += 1
        vw[k]["v3 ok"] += r["v3"] == r["label"]
    for (fam, fact), c in sorted(vw.items()):
        w(f"| {fam} | `{fact}` | {c['n']} | {c['ft']} / {c['tf']} | {c['v3 ok']} of {c['n']} |")
    w(f"| **all** | | {len(T.v2wrong)} | | **{sum(r['v3'] == r['label'] for r in T.v2wrong)} of "
      f"{len(T.v2wrong)}** |")
    w("")
    w("(p4 counted: main gift-card difference 218, item replacements 7 + 1, status pending 4, payment differs 1, "
      "order total 2, refund method 4; Stage B gift-card difference 3, item replacements 7.)")
    w("")
    n3 = len(T.refund_check3)
    w(f"**Return, \"payment method not found\" (check 3):** {n3} attempt(s). p3's label for "
      f"`return_refund_method_is_original_or_existing_gift_card` is None there (p3 maps only check 4); the v3 "
      f"definition makes the fact false. v3 value: "
      + (", ".join(f"`{r['ckey']}` {r['v3']}" for r in T.refund_check3) if n3 else "none") + ".")
    w("")
    # ---- P6.2
    rp = T.replay
    w("## 3. P6.2: replay")
    w("")
    w(f"Every development conversation replayed on a fresh database copy (`state.walk` over the whole executed "
      f"history): {rp['conversations']:,} conversations, {rp['replayed tool calls']:,} executed tool calls; "
      f"replayed output != saved output: **{rp['mismatches']}**; parse problems {rp['parse problems']}; tool "
      f"messages without a call {rp['problems']}. (p3: 0 mismatches in 23,138 calls.)")
    w("")
    # ---- P6.3
    w("## 4. P6.3: event parts vs a raw scan of the saved messages")
    w("")
    w("At every development check whose pending call has the key argument (user_authenticated: every retail check), "
      "the event part's value vs a raw scan of the messages before the check: a tool call of that tool with that "
      "argument whose tool message is a text that does not start with 'Error' (or 'Unknown action').")
    w("")
    w("| fact (part a) | checks | agree | disagree | problem | raw scan true / false |")
    w("|---|---|---|---|---|---|")
    ev_tot = collections.Counter()
    for d in paths.DOMAINS:
        for fact in EVENT_SPECS[d]:
            a, dd, pr = T.events[(fact, "agree")], T.events[(fact, "disagree")], T.events[(fact, "problem")]
            ev_tot.update({"agree": a, "disagree": dd, "problem": pr})
            w(f"| `{fact}` | {a + dd + pr:,} | {a:,} | {dd:,} | {pr:,} | {T.events[(fact, 'raw true')]:,} / "
              f"{T.events[(fact, 'raw false')]:,} |")
    w(f"| **all** | {sum(ev_tot.values()):,} | {ev_tot['agree']:,} | **{ev_tot['disagree']}** | {ev_tot['problem']} | |")
    for r in T.event_rows[:20]:
        w(f"- `{r['ckey']}` {r['fact']}: v3 {r['mine']}, raw {r['raw']}")
    w("")
    # ---- P6.4
    w("## 5. P6.4: the eval v2 harm sets")
    w("")
    for which, rows in ((420, T.harm420), (428, T.harm428)):
        checks = sorted({r["ckey"] for r in rows})
        c = collections.Counter()
        by_fact = collections.defaultdict(collections.Counter)
        for r in rows:
            k = "undecided" if r["label"] is None else ("agree" if r["v3"] == r["label"] else "disagree")
            c[k] += 1
            by_fact[r["fact"]][k] += 1
            by_fact[r["fact"]]["v3 " + str(r["v3"]).lower()] += 1
        if which == 420:
            w("**The 420 set** (`output/eval_v2/good_success_stage_a.md` lines 209-212; definition of "
              "eval v2's `v2_good_success.py` offline(), re-derived from the saved records): TGR + tracker Stage A, "
              "blocked checks with judge values, where some fact had the judge's value unknown and the tracker's false.")
        else:
            w("**The 428 set** (`output/eval_v2/stage_a_runs.md` line 319; definition of "
              "eval v2's `v2_p6_weak_extra.py` part 4): weak agent, TGR + tracker, every check (blocked or not) where "
              "the tracker changed `gift_card_balance_covers_price_difference` from the judge's unknown to false, and "
              "the decision did not change (changed decisions: `output/logs/v2_c6w_check.json`).")
        w("")
        per_ds = collections.Counter(r["dataset"] for r in {r["ckey"]: r for r in rows}.values())
        w(f"- checks: **{len(checks)}** ({', '.join(f'{k} {v}' for k, v in sorted(per_ds.items()))}); "
          f"fact values: {len(rows)}")
        if which == 428:
            w(f"- left out because the decision changed: {T.harm428_changed}")
        w(f"- v3 value vs the tool label: agree {c['agree']}, disagree **{c['disagree']}**, not decided by the tool "
          f"{c['undecided']}")
        w("")
        w("| fact | values | v3 true / false | agree | disagree | not decided |")
        w("|---|---|---|---|---|---|")
        for f, cc in sorted(by_fact.items()):
            n = cc["agree"] + cc["disagree"] + cc["undecided"]
            w(f"| `{f}` | {n} | {cc['v3 true']} / {cc['v3 false']} | {cc['agree']} | {cc['disagree']} | "
              f"{cc['undecided']} |")
        w("")
        if which == 420:
            rules = _rules_of("retail")
            other = 0
            for ck in checks:
                rs = [r for r in rows if r["ckey"] == ck]
                flipped = {r["fact"] for r in rs}
                viol = rs[0]["violated_rules"]
                if any(not (set(rules.get(v, [])) & flipped) for v in viol):
                    other += 1
            gc_not = sum(1 for r in rows if r["fact"] == GC_DIFF and not r["payment_is_gift_card"])
            w(f"- also blocked by a rule without a flipped fact (saved violated rules): {other} of {len(checks)} "
              f"(the plan says 356 of 420)")
            w(f"- `{GC_DIFF}` values where the call's payment method is not a gift card: {gc_not} (the tool does not "
              "check the balance then: not decided; the v3 value is false and rule 56 / 64 holds by its other branch)")
            w("")
    s420 = {r["ckey"] for r in T.harm420}
    s428 = {r["ckey"] for r in T.harm428}
    s420n = {k for k in s420 if k.startswith("stage_a.nano.")}
    w(f"**420 vs 428.** The 420 are blocked checks of both agents with any flipped fact; the 428 are checks of the weak "
      f"agent only, blocked or not, with the gift-card difference flipped and no changed decision. Overlap: "
      f"{len(s420 & s428)} checks are in both; {len(s428 - s420)} are only in the 428 (weak agent; "
      f"{sum(1 for r in T.harm428 if r['ckey'] in (s428 - s420) and not r['ckey'] in s420)} values); "
      f"{len(s420 - s428)} only in the 420 ({len(s420n - s428)} weak, {len(s420 - s420n - s428)} strong).")
    w("")
    # ---- sanity
    w("## 6. Two values and problems at every development check (P5.3, P9.2 preview)")
    w("")
    w("Every code fact (or p6 part of a mixed fact) at every development check whose pending tool is in one of the "
      "fact's rules. A problem gives the blocking value and is counted: missing_argument (the call lacks an argument), "
      "missing_field (an existing object lacks a field: a bug), type_error, and the helpers' own kinds.")
    w("")
    w("| fact (part) | checks | true | false | problems |")
    w("|---|---|---|---|---|")
    keys = sorted({(f, p) for f, p, _ in T.sanity})
    mf = 0
    for f, p in keys:
        n = T.sanity[(f, p, "checks")]
        pr = {k[2][len("problem "):]: v for k, v in T.sanity.items() if k[0] == f and k[1] == p
              and k[2].startswith("problem ")}
        mf += pr.get("missing_field", 0)
        w(f"| `{f}`{'' if p == '*' else ' (' + p + ')'} | {n:,} | {T.sanity[(f, p, 'value true')]:,} | "
          f"{T.sanity[(f, p, 'value false')]:,} | {', '.join(f'{k} {v}' for k, v in sorted(pr.items())) or '-'} |")
    w("")
    w(f"Missing fields of existing objects (bugs): **{mf}**. Evaluation errors (exceptions): **{len(T.errors)}**.")
    for e in T.errors[:10]:
        w(f"- {e}")
    w("")
    w("Write calls with an empty `item_ids` list (item replacements: false by the p5 definition, τ-bench accepts "
      "them): " + (", ".join(f"{t} {k} {n}" for (t, k), n in sorted(T.empty_items.items())) or "none") + ".")
    w("")
    if T.problem_examples:
        w("The first check with each problem (counted above; the fact took its blocking value):")
        w("")
        for (f, p, kind), txt in sorted(T.problem_examples.items()):
            w(f"- `{f}`{'' if p == '*' else ' (' + p + ')'}, {kind}: {txt}")
        w("")
    # ---- P5.4
    w("## 7. P5.4: a call with a nonexistent id")
    w("")
    w("Synthetic checks (a logged-in user's conversation with real τ-bench outputs; one id of a valid call replaced by "
      "an id that does not exist). For every rule of the call's action: the rule's facts as the p6 parts decide them "
      "(a fact with a part p6 does not write is open), and the outcome: blocks (every completion fails), allows, or "
      "depends (a structure / question part could tip it). For the calls that no rule blocks from the p6 parts, "
      "τ-bench's own output on a copy.")
    w("")
    for d in paths.DOMAINS:
        rows = ne[d]
        w(f"**{d}**")
        w("")
        w("| action | nonexistent | rules that block (p6 parts) | rules that allow | rules that depend | τ-bench |")
        w("|---|---|---|---|---|---|")
        groups: Dict[Tuple[str, str], List[dict]] = collections.defaultdict(list)
        for r in rows:
            groups[(r["action"], r["variant"])].append(r)
        for (a, v), rs in groups.items():
            bl = [r["rule"] for r in rs if r["outcome"] == "blocks"]
            al = [r["rule"] for r in rs if r["outcome"] == "allows"]
            de = [r["rule"] for r in rs if r["outcome"] == "depends"]
            w(f"| {a} | {v} | {', '.join(bl) or '**none**'} | {', '.join(al) or '-'} | {', '.join(de) or '-'} | "
              f"{rs[0]['tau_output']} |")
        w("")
    # ---- notes
    w("## 8. Bugs found and fixed; notes for the main chat")
    w("")
    w(NOTES.strip())
    w("")
    # ---- run
    w("## 9. Run")
    w("")
    skip = "hold-out Stage B tries skipped"
    w(f"- Conversations: {sum(v for k, v in T.convs.items() if k != skip):,} (development); the two val data sets "
      f"(hold-out) are not opened; hold-out Stage B tries skipped before any use: {T.convs[skip]}. Checks: "
      f"{sum(T.checks.values()):,}.")
    w(f"- Manifest check passed first ({manifest_files:,} files); network attempts: {net_attempts}.")
    w(f"- Run time: {seconds:.0f} s.")
    w("- Command (from `predicate_correctness/`): `PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 "
      "/home/azureuser/miniconda3/bin/python3 -B -m scoring.v3_p6_agreement " + " ".join(argv) + "`")
    w("- sha256:")
    for f in OWN_FILES:
        p = os.path.join(PC, f)
        w(f"  - `{f}`: `{sha256_file(p) if os.path.exists(p) else 'missing'}`")
    w("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    return {"summary": summary, "p61": dict(tot), "events": dict(ev_tot), "missing_field": mf}


def main(argv: Optional[List[str]] = None) -> int:
    from state_tracker.v3.frozen import check_manifest
    manifest = check_manifest()
    from fork import rebuild_check as RC                # blocks the network; writes only under output/
    RC.safety_setup()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=None, help="conversations per data set (a test run)")
    ap.add_argument("--report", default=REPORT)
    raw = list(sys.argv[1:] if argv is None else argv)
    a = ap.parse_args(raw)
    t0 = time.time()
    print(f"manifest ok: {len(manifest)} files", flush=True)
    ne = {d: nonexistent_id_table(d) for d in paths.DOMAINS}
    T = run_pass(limit=a.limit)
    secs = time.time() - t0
    out = write_report(T, ne, secs, raw, len(manifest), len(RC.NETWORK_ATTEMPTS), a.report)
    js = {"p61": out["p61"], "events": out["events"], "replay": dict(T.replay), "missing_field": out["missing_field"],
          "errors": T.errors[:50], "n_errors": len(T.errors), "disagreements": T.disagree_rows[:200],
          "harm420": T.harm420, "harm428": T.harm428, "harm428_changed": T.harm428_changed,
          "refund_check3": T.refund_check3, "v2wrong": T.v2wrong,
          "convs": dict(T.convs), "checks": dict(T.checks), "seconds": round(secs)}
    if a.limit is None:
        with open(RUN_JSON, "w", encoding="utf-8") as f:
            json.dump(js, f, indent=1, default=str)
    print(json.dumps({k: js[k] for k in ("p61", "events", "replay", "missing_field", "n_errors", "convs", "checks",
                                         "seconds")}, indent=1), flush=True)
    print(f"420: {len({r['ckey'] for r in T.harm420})} checks; 428: {len({r['ckey'] for r in T.harm428})} checks",
          flush=True)
    print("wrote", os.path.relpath(a.report, PC), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
