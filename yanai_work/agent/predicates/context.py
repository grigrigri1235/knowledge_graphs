"""Shared trajectory helpers for deterministic ShieldAgent predicates (τ-bench v1).

Data model
----------
trajectory : list of OpenAI-style chat messages **before** the current agent turn, as in τ-bench
    `historical_trajectories` / the τ-bench tool-calling agent:
      {"role": "system"|"user", "content": str}
      {"role": "assistant", "content": str|None, "tool_calls": [{"id", "type", "function": {"name", "arguments"}}]}
      {"role": "tool", "tool_call_id": str, "name": str, "content": str}
tool_call : the call being checked: {"name": str, "arguments": dict|str, "turn": <assistant message>|None}.
    `turn` (the assistant message that contains this call) is needed only by structural predicates.
config : the domain config (policies/curated/{domain}_config.json).

Predicates return True / False, or None when the trajectory does not contain enough information.
They never guess and never read the τ-bench DB directly; they only see what the agent saw.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterator, Optional


@dataclass
class ToolEvent:
    """One executed tool call paired with its result."""
    index: int            # position of the tool-result message in the trajectory
    name: str
    args: dict
    output: str           # raw tool output (string)
    data: Any             # parsed JSON output, or None if not JSON
    ok: bool              # False if the output is an "Error: ..." string


def parse_args(arguments: Any) -> dict:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            value = json.loads(arguments)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def call_name(tool_call: dict) -> str:
    return tool_call.get("name") or tool_call.get("function", {}).get("name", "")


def call_args(tool_call: dict) -> dict:
    if "arguments" in tool_call:
        return parse_args(tool_call["arguments"])
    return parse_args(tool_call.get("function", {}).get("arguments"))


def _parse_output(content: Any) -> tuple[str, Any, bool]:
    text = content if isinstance(content, str) else ("" if content is None else json.dumps(content))
    ok = not text.startswith("Error")
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        data = None
    return text, data, ok


def tool_events(trajectory: list) -> Iterator[ToolEvent]:
    """Yield executed tool calls in order, pairing assistant tool_calls with tool messages by id.

    Falls back to order-of-appearance pairing (by name) for tool messages without a usable id.
    """
    pending: dict[str, tuple[str, dict]] = {}
    unmatched: list[tuple[str, str, dict]] = []
    for i, msg in enumerate(trajectory):
        role = msg.get("role")
        if role == "assistant":
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function", {})
                entry = (fn.get("name", ""), parse_args(fn.get("arguments")))
                if tc.get("id"):
                    pending[tc["id"]] = entry
                else:
                    unmatched.append((None, *entry))
        elif role == "tool":
            tcid = msg.get("tool_call_id")
            if tcid in pending:
                name, args = pending.pop(tcid)
            else:
                pos = next((k for k, u in enumerate(unmatched) if u[1] == msg.get("name")), None)
                if pos is None:
                    continue
                _, name, args = unmatched.pop(pos)
            text, data, ok = _parse_output(msg.get("content"))
            yield ToolEvent(i, name, args, text, data, ok)


def successful_calls(trajectory: list, name: Optional[str] = None) -> list[ToolEvent]:
    return [e for e in tool_events(trajectory) if e.ok and (name is None or e.name == name)]


# ---------------------------------------------------------------------------------------------
# Latest DB objects seen by the agent
# ---------------------------------------------------------------------------------------------
_USER_TOOLS = {"get_user_details", "modify_user_address"}   # output = user record WITHOUT a user_id key


def _objects_in_event(e: ToolEvent, kind: str) -> list[tuple[str, dict]]:
    """(id, object) pairs of `kind` contained in one successful tool output."""
    d = e.data
    if not e.ok or d is None:
        return []
    if kind == "user":
        if e.name in _USER_TOOLS and isinstance(d, dict) and "user_id" in e.args:
            return [(e.args["user_id"], d)]
        return []
    key = {"reservation": "reservation_id", "order": "order_id", "product": "product_id"}[kind]
    if isinstance(d, dict) and key in d:
        return [(d[key], d)]
    return []


def latest_object(trajectory: list, kind: str, obj_id: Any) -> Optional[dict]:
    """Most recent `kind` object ('reservation' | 'order' | 'user' | 'product') with this id seen in ANY
    successful tool output, read or write (e.g. modify_pending_order_items returns the modified order).
    Returns a deep copy, or None if the agent has not seen it."""
    if obj_id is None:
        return None
    found = None
    for e in tool_events(trajectory):
        for oid, obj in _objects_in_event(e, kind):
            if oid == obj_id:
                found = obj
    return copy.deepcopy(found) if found is not None else None


def all_latest_objects(trajectory: list, kind: str) -> dict[Any, dict]:
    out: dict[Any, dict] = {}
    for e in tool_events(trajectory):
        for oid, obj in _objects_in_event(e, kind):
            out[oid] = obj
    return copy.deepcopy(out)


# ---------------------------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------------------------
_AUTH_TOOLS = ("find_user_id_by_email", "find_user_id_by_name_zip")


def authenticated_user_ids(trajectory: list, domain: str) -> list[str]:
    """Distinct user ids, in order of first appearance, established per the domain's rules.

    retail : the string returned by a successful find_user_id_by_email / find_user_id_by_name_zip call.
    airline: the wiki has no authentication step; the user id is 'obtained' when a get_user_details call
             with that user_id succeeds.
    """
    ids: list[str] = []
    for e in tool_events(trajectory):
        if not e.ok:
            continue
        if domain == "retail" and e.name in _AUTH_TOOLS:
            uid = e.output.strip().strip('"')
        elif domain == "airline" and e.name == "get_user_details":
            uid = e.args.get("user_id")
        else:
            continue
        if uid and uid not in ids:
            ids.append(uid)
    return ids


def authenticated_user_id(trajectory: list, domain: str) -> Optional[str]:
    """The FIRST authenticated user id (one user per conversation), or None."""
    ids = authenticated_user_ids(trajectory, domain)
    return ids[0] if ids else None


def with_effective_cabin(trajectory: list, reservation: Optional[dict]) -> Optional[dict]:
    """τ-bench v1 quirk: update_reservation_flights re-prices segments for the new cabin but never writes
    reservation['cabin'] (update_reservation_flights.py:76-86), so every later reservation object shows the old
    cabin. The effective cabin is the `cabin` argument of the latest SUCCESSFUL update_reservation_flights call
    on this reservation, else the stored value. Returns a copy with 'cabin' replaced ('stored_cabin' keeps the original)."""
    if reservation is None:
        return None
    res = copy.deepcopy(reservation)
    rid = res.get("reservation_id")
    for e in tool_events(trajectory):
        if e.ok and e.name == "update_reservation_flights" and e.args.get("reservation_id") == rid and e.args.get("cabin"):
            res.setdefault("stored_cabin", reservation.get("cabin"))
            res["cabin"] = e.args["cabin"]
    return res


def user_mentioned_id(trajectory: list, user_id: Optional[str]) -> bool:
    """True iff `user_id` appears verbatim (as a whole token) in some USER message. Deterministic string match."""
    if not user_id:
        return False
    pat = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(user_id) + r"(?![A-Za-z0-9_])")
    return any(m.get("role") == "user" and isinstance(m.get("content"), str) and pat.search(m["content"]) for m in trajectory)


def reservation_in_focus(trajectory: list, user_id: Optional[str]) -> Optional[dict]:
    """Heuristic for send_certificate (which has no reservation argument): the reservation of `user_id`
    that appeared MOST RECENTLY in any successful tool output (get_reservation_details or a write tool).

    Limits: if the agent looked at several reservations, the last one wins, even if the complaint was about
    another; if it looked at none, the result is None (rules depending on it become not evaluable).
    """
    if user_id is None:
        return None
    focus = None
    for e in tool_events(trajectory):
        for _, obj in _objects_in_event(e, "reservation"):
            if obj.get("user_id") == user_id:
                focus = obj
    return with_effective_cabin(trajectory, focus)


# ---------------------------------------------------------------------------------------------
# Airline flights (search outputs are the only place flight status/prices/endpoints appear)
# ---------------------------------------------------------------------------------------------
def flight_date_info(trajectory: list, flight_number: str, date: str) -> Optional[dict]:
    """Latest search result for (flight_number, date): flight fields + that date's status/seats/prices.
    search_direct_flight items carry no date key (taken from the call args); one-stop legs carry 'date'."""
    found = None
    for e in tool_events(trajectory):
        if not e.ok or not isinstance(e.data, list):
            continue
        if e.name == "search_direct_flight":
            for f in e.data:
                if isinstance(f, dict) and f.get("flight_number") == flight_number and e.args.get("date") == date:
                    found = f
        elif e.name == "search_onestop_flight":
            for pair in e.data:
                for leg in pair if isinstance(pair, list) else []:
                    if isinstance(leg, dict) and leg.get("flight_number") == flight_number and leg.get("date") == date:
                        found = leg
    return copy.deepcopy(found) if found is not None else None


def flight_endpoints(trajectory: list, flight_number: str) -> Optional[tuple[str, str]]:
    """(origin, destination) of a flight number from any search result or reservation flight list."""
    ends = None
    for e in tool_events(trajectory):
        if not e.ok:
            continue
        d = e.data
        candidates = []
        if isinstance(d, dict) and isinstance(d.get("flights"), list):
            candidates = d["flights"]
        elif isinstance(d, list):
            for x in d:
                candidates.extend(x if isinstance(x, list) else [x])
        for f in candidates:
            if isinstance(f, dict) and f.get("flight_number") == flight_number and f.get("origin") and f.get("destination"):
                ends = (f["origin"], f["destination"])
    return ends


# ---------------------------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------------------------
def config_now(config: dict) -> Optional[datetime]:
    t = (config or {}).get("current_time")
    return datetime.fromisoformat(t) if t else None


def parse_timestamp(value: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------------------------
# Payment ids
# ---------------------------------------------------------------------------------------------
def payment_source(payment_id: str, user: Optional[dict] = None) -> Optional[str]:
    """Payment source ('credit_card' | 'gift_card' | 'certificate' | 'paypal'): from the user's profile if
    known, else from the id prefix (in τ-bench data the prefix always equals the source)."""
    if user and payment_id in (user.get("payment_methods") or {}):
        return user["payment_methods"][payment_id].get("source")
    for src in ("credit_card", "gift_card", "certificate", "paypal"):
        if isinstance(payment_id, str) and payment_id.startswith(src + "_"):
            return src
    return None


# ---------------------------------------------------------------------------------------------
# Structural (current turn)
# ---------------------------------------------------------------------------------------------
def single_tool_call_in_turn(tool_call: dict, trajectory: list, config: dict) -> Optional[bool]:
    """True iff the current assistant turn contains exactly one tool call."""
    turn = tool_call.get("turn")
    if not isinstance(turn, dict):
        return None
    return len(turn.get("tool_calls") or []) == 1


def text_with_tool_call(tool_call: dict, trajectory: list, config: dict) -> Optional[bool]:
    """True iff the current assistant turn has non-empty user-facing text AND at least one tool call."""
    turn = tool_call.get("turn")
    if not isinstance(turn, dict):
        return None
    content = turn.get("content")
    has_text = isinstance(content, str) and content.strip() != ""
    return has_text and bool(turn.get("tool_calls"))
