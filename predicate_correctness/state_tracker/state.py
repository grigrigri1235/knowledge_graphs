"""Part 4: the rolling state of a conversation, built with code only.

For a step of a conversation, the state before that step has four parts (overview.md, "The rolling state"):
- db:     the database copy. τ-bench's data files, changed by running τ-bench's own tool code (copied, unchanged)
          for each executed tool call, in order;
- shown:  the objects (kind and id) that appeared in tool outputs before the step, newest version;
- events: one entry per executed tool call: step, tool, arguments, worked or failed, output;
- today:  the current time stated in the policy (airline: 2024-05-15 15:00:00 EST; retail: None).

Main API (details in state_tracker/README.md, "State API"):
    from state_tracker.state import build_state, load_db
    st = build_state(rec["history"], rec)          # rec: a Part 2 step record (pending action = rec)
    st.db_get("order", "#W123"), st.db_all("order")             # fact: the database copy
    st.shown_get("order", "#W123"), st.shown_all("order")       # shown: the version the conversation showed, or None
    st.events_where(tool="find_user_id_by_email", ok=True)      # earlier tool calls
    st.today, st.pending["tool"], st.pending["args"]

The replay check (every replayed output equals the saved one) is state_tracker/replay_check.py.

Standard library only. No LLM calls. Never imports gold code.
"""
from __future__ import annotations

import copy
import datetime
import json
import os
import re
import sys
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, Union

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from state_tracker import paths, tau_copy
else:
    from . import paths, tau_copy

TOOL_TABLE_PATH = os.path.join(paths.STATE_TRACKER_DIR, "tool_table.json")

# Fields of an airline flight object other than `dates` (flights.json). In a search output, every other field is
# about the searched date (status, available_seats, prices; and `date` in a one-stop search).
FLIGHT_BASE_FIELDS = ("flight_number", "origin", "destination", "scheduled_departure_time_est",
                      "scheduled_arrival_time_est")

# "The current time is 2024-05-15 15:00:00 EST." (airline policy, line 3)
_TIME_RE = re.compile(r"The current time is (\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}(?::\d{2})?)(?:\s+([A-Z]{2,5}))?")

_MISSING = object()


class ReplayMismatch(Exception):
    """A replayed tool output differs from the saved one (raised only with strict=True)."""


# ----------------------------------------------------------------------------------------------- inputs

_TABLE: Optional[dict] = None
_BASE: Dict[str, dict] = {}                     # domain -> data as loaded from the files (never changed)
_TODAY: Dict[str, Tuple[Optional[datetime.datetime], Optional[str]]] = {}
_POLICY: Dict[str, str] = {}


def tool_table() -> dict:
    """state_tracker/tool_table.json (loaded once)."""
    global _TABLE
    if _TABLE is None:
        with open(TOOL_TABLE_PATH, encoding="utf-8") as f:
            _TABLE = json.load(f)
    return _TABLE


def load_db(domain: str) -> Dict[str, Any]:
    """A fresh copy of τ-bench's data for one conversation. The JSON files are read once (with τ-bench's
    load_data()); each call returns a deep copy, so no conversation sees changes made by another."""
    if domain not in _BASE:
        _BASE[domain] = tau_copy.load_data_fresh(domain)
    return copy.deepcopy(_BASE[domain])


def policy_today(domain: str) -> Tuple[Optional[datetime.datetime], Optional[str]]:
    """(today as a datetime, the text as written) from the copied policy, or (None, None) if the policy states no
    current time. The time zone text (EST) is kept in the text only; the datetime has no time zone."""
    if domain not in _TODAY:
        m = _TIME_RE.search(_policy(domain))
        if m:
            t = m.group(2) if m.group(2).count(":") == 2 else m.group(2) + ":00"
            _TODAY[domain] = (datetime.datetime.fromisoformat(f"{m.group(1)}T{t}"),
                              " ".join(x for x in (m.group(1), m.group(2), m.group(3)) if x))
        else:
            _TODAY[domain] = (None, None)
    return _TODAY[domain]


def _policy(domain: str) -> str:
    if domain not in _POLICY:
        _POLICY[domain] = tau_copy.policy_text(domain)
    return _POLICY[domain]


def parse_date(text: Any) -> Optional[datetime.datetime]:
    """A date or time from τ-bench data as a datetime: 'YYYY-MM-DD', 'YYYY-MM-DDTHH:MM:SS' or
    'YYYY-MM-DD HH:MM:SS'. None if it is not one of these."""
    if isinstance(text, datetime.datetime):
        return text
    if isinstance(text, datetime.date):
        return datetime.datetime(text.year, text.month, text.day)
    if not isinstance(text, str):
        return None
    try:
        return datetime.datetime.fromisoformat(text.strip().replace(" ", "T", 1))
    except ValueError:
        return None


def infer_domain(history: Sequence[dict]) -> str:
    """The domain of a conversation: its system message equals one copied policy; if not, its tool names."""
    if history and history[0].get("role") == "system":
        for d in paths.DOMAINS:
            if history[0].get("content") == _policy(d):
                return d
    names = {tc.get("function", {}).get("name") for m in history if m.get("role") == "assistant"
             for tc in (m.get("tool_calls") or [])}
    hits = [d for d in paths.DOMAINS
            if names & (set(tool_table()["domains"][d]["tools"])
                        - set().union(*(tool_table()["domains"][o]["tools"] for o in paths.DOMAINS if o != d)))]
    if len(hits) == 1:
        return hits[0]
    raise ValueError("cannot tell the domain of this history; pass domain=")


# ----------------------------------------------------------------------------------------------- one call

def is_failure(output: Any) -> bool:
    """A failed call: τ-bench's failed outputs start with 'Error' (an exception in the tool code also becomes
    'Error: ...'); an unknown tool gives 'Unknown action ...'. No text at all (None) also counts as failed."""
    return not isinstance(output, str) or output.startswith("Error") or output.startswith("Unknown action")


def run_tool(domain: str, db: Dict[str, Any], name: str, args: Dict[str, Any]) -> Any:
    """Run one call as τ-bench's Env.step does (envs/base.py): the tool's invoke() on db, which it may change;
    any exception becomes 'Error: <exception>'; an unknown name gives 'Unknown action <name>'."""
    tools = tau_copy.tools(domain)
    if name not in tools:
        return f"Unknown action {name}"
    try:
        return tools[name].invoke(data=db, **args)
    except Exception as e:                       # same as Env.step
        return f"Error: {e}"


def outputs_equal(replayed: Any, saved: Any) -> Tuple[bool, bool]:
    """(exactly the same string, the same JSON value). The replay check uses the exact comparison; the JSON
    comparison is reported too (it is true when the exact one is)."""
    exact = replayed == saved and type(replayed) is type(saved)
    if exact:
        return True, True
    try:
        return False, json.loads(replayed) == json.loads(saved)
    except (TypeError, ValueError):
        return False, False


def parse_output(domain: str, tool: str, args: Dict[str, Any], output: Any
                 ) -> Tuple[List[Tuple[str, str, Any]], Optional[str]]:
    """The objects in one successful output, as (kind, id, version), using tool_table.json.
    Returns (objects, problem); problem is None if the output had the expected form.
    Nested objects (payment methods, variants) are added by State.add_shown, not here."""
    spec = tool_table()["domains"][domain]["tools"].get(tool)
    if spec is None:
        return [], "unknown tool"
    fmt, kind = spec["output"], spec.get("kind")
    if fmt == "text":
        return [], None
    try:
        data = json.loads(output)
    except (TypeError, ValueError):
        return [], f"expected JSON ({fmt}), got text"
    out: List[Tuple[str, str, Any]] = []
    if fmt == "object":
        if not isinstance(data, dict):
            return [], f"expected a JSON object, got {type(data).__name__}"
        src, _, key = spec["id_from"].partition(":")
        oid = data.get(key) if src == "field" else args.get(key)
        if not isinstance(oid, str) or not oid:
            return [], f"no id ({spec['id_from']})"
        out.append((kind, oid, data))
    elif fmt == "flight_list":
        if not isinstance(data, list):
            return [], "expected a list of flights"
        date = args.get("date")
        for f in data:
            if not isinstance(f, dict) or not isinstance(f.get("flight_number"), str) or not isinstance(date, str):
                return [], "a flight without flight_number, or no date argument"
            out.append(("flight", f["flight_number"], _flight_version(f, date)))
    elif fmt == "flight_pair_list":
        if not isinstance(data, list):
            return [], "expected a list of [leg, leg]"
        for pair in data:
            if not isinstance(pair, list) or not pair:
                return [], "expected a list of [leg, leg]"
            for f in pair:
                if not isinstance(f, dict) or not isinstance(f.get("flight_number"), str) or "date" not in f:
                    return [], "a leg without flight_number or date"
                out.append(("flight", f["flight_number"], _flight_version(f, f["date"])))
    elif fmt == "name_to_id":
        if not isinstance(data, dict):
            return [], "expected {name: product_id}"
        for name, pid in data.items():
            out.append((kind, str(pid), {"name": name, "product_id": pid}))
    elif fmt == "code_to_city":
        if not isinstance(data, dict):
            return [], "expected {code: city}"
        for code, city in data.items():
            out.append((kind, code, {"code": code, "city": city}))
    else:
        return [], f"unknown output format {fmt!r} in tool_table.json"
    return out, None


def _flight_version(item: dict, date: str) -> dict:
    """A flight from a search output, in the shape of flights.json: base fields plus dates {date: {...}}."""
    base = {k: item[k] for k in FLIGHT_BASE_FIELDS if k in item}
    day = {k: v for k, v in item.items() if k not in FLIGHT_BASE_FIELDS and k != "date"}
    base["dates"] = {date: day}
    return base


# ----------------------------------------------------------------------------------------------- the state

class State:
    """The state of one conversation before a step. Read it; do not change it.

    domain   'airline' or 'retail'
    db       the database copy: τ-bench's data dict ({table: {id: object}}), after the executed calls
    shown    {kind: {id: newest version shown}}; same shape as the database objects
    shown_meta {kind: {id: {"event", "step", "tool"}}}: which event showed the newest version (flights: also
             "dates": {date: event index})
    events   [event]: one dict per executed tool call, in order (fields in Tracker.apply_call)
    today, today_text   the policy's current time (datetime, text) or None
    pending  the pending action {"tool", "args", "kind"} or None
    n_steps  executed steps seen (agent messages in the history)
    mismatches, parse_problems, problems   lists of what went wrong (see replay_check.py)
    """

    def __init__(self, domain: str, db: Dict[str, Any]):
        self.domain = domain
        self.db = db
        self.shown: Dict[str, Dict[str, Any]] = {}
        self.shown_meta: Dict[str, Dict[str, dict]] = {}
        self.events: List[dict] = []
        self.today, self.today_text = policy_today(domain)
        self.pending: Optional[dict] = None
        self.n_steps = 0
        self.mismatches: List[dict] = []
        self.parse_problems: List[dict] = []
        self.problems: List[str] = []
        self._kinds = tool_table()["domains"][domain]["kinds"]

    # ---- fact: the database copy
    def db_get(self, kind: str, oid: Any) -> Any:
        """The object in the database copy, or None. Nested kinds (payment_method, variant) are copies with the
        parent's id added (user_id, product_id)."""
        k = self._kind(kind)
        if "table" in k:
            return self.db[k["table"]].get(oid) if isinstance(oid, str) else None
        if "nested_in" in k:
            parent, field = k["nested_in"]
            for pid, p in self.db[self._kinds[parent]["table"]].items():
                sub = p.get(field) or {}
                if oid in sub:
                    return dict(sub[oid], **{k["parent_id_as"]: pid})
            return None
        return next((o for o in self.db_all(kind) if o.get(k["id_field"]) == oid), None)

    def db_all(self, kind: str) -> List[Any]:
        """All objects of a kind in the database copy (a list)."""
        k = self._kind(kind)
        if "table" in k:
            return list(self.db[k["table"]].values())
        if "nested_in" in k:
            parent, field = k["nested_in"]
            return [dict(o, **{k["parent_id_as"]: pid})
                    for pid, p in self.db[self._kinds[parent]["table"]].items() for o in (p.get(field) or {}).values()]
        if kind == "product_type":
            return [{"name": p["name"], "product_id": p["product_id"]} for p in self.db["products"].values()]
        if kind == "airport":
            out = run_tool(self.domain, self.db, "list_all_airports", {})
            return [{"code": c, "city": city} for c, city in json.loads(out).items()]
        raise KeyError(kind)

    # ---- shown: what the conversation showed
    def shown_get(self, kind: str, oid: Any) -> Any:
        """The newest version of the object shown in an earlier tool output, or None if none showed it."""
        self._kind(kind)
        return self.shown.get(kind, {}).get(oid) if isinstance(oid, str) else None

    def shown_all(self, kind: str) -> List[Any]:
        """All shown objects of a kind (newest versions, a list)."""
        self._kind(kind)
        return list(self.shown.get(kind, {}).values())

    # ---- events
    def events_where(self, tool: Union[None, str, Iterable[str]] = None, ok: Optional[bool] = None) -> List[dict]:
        """Earlier executed tool calls, filtered by tool name (a name or a list of names) and by worked / failed."""
        names = None if tool is None else ({tool} if isinstance(tool, str) else set(tool))
        return [e for e in self.events if (names is None or e["tool"] in names) and (ok is None or e["ok"] is ok)]

    # ---- helpers
    def _kind(self, kind: str) -> dict:
        if kind not in self._kinds:
            raise KeyError(f"unknown kind {kind!r} for {self.domain}; known: {sorted(self._kinds)}")
        return self._kinds[kind]

    def add_shown(self, kind: str, oid: str, version: Any, event: dict) -> None:
        """Put one shown object in the shown set (newer replaces older), with its nested objects."""
        meta = {"event": event["index"], "step": event["step"], "tool": event["tool"]}
        bucket = self.shown.setdefault(kind, {})
        if kind == "flight":                       # merge by date: a newer date entry replaces the older one
            old = bucket.get(oid)
            new_dates = version["dates"]
            dates = {**(old["dates"] if old else {}), **new_dates}
            version = {**{k: v for k, v in version.items() if k != "dates"}, "dates": dates}
            old_meta = self.shown_meta.get(kind, {}).get(oid, {})
            meta["dates"] = {**old_meta.get("dates", {}), **{d: event["index"] for d in new_dates}}
        bucket[oid] = version
        self.shown_meta.setdefault(kind, {})[oid] = meta
        for nkind, nk in self._kinds.items():          # nested kinds: payment methods of a user, variants of a product
            if nk.get("nested_in", [None])[0] == kind:
                field = nk["nested_in"][1]
                for nid, nobj in ((version.get(field) or {}) if isinstance(version, dict) else {}).items():
                    if isinstance(nobj, dict):
                        self.add_shown(nkind, nid, dict(nobj, **{nk["parent_id_as"]: oid}), event)

    def summary(self) -> dict:
        return {"domain": self.domain, "n_steps": self.n_steps, "events": len(self.events),
                "failed_events": sum(1 for e in self.events if not e["ok"]),
                "shown": {k: len(v) for k, v in self.shown.items()}, "today": self.today_text,
                "pending": self.pending, "mismatches": len(self.mismatches),
                "parse_problems": len(self.parse_problems), "problems": len(self.problems)}


class Tracker:
    """Builds a State by feeding the conversation's messages in order (chat format: system / user / assistant with
    tool_calls / tool). Each tool message is matched to its call by tool_call_id; then the call is replayed on the
    database copy, checked against the saved output, logged, and its objects are added to the shown set.

    The tracker can be fed further: the same State object then changes. Use build_state() for a separate state.
    """

    def __init__(self, domain: str, strict: bool = False, db: Optional[Dict[str, Any]] = None):
        self.domain = domain
        self.strict = strict
        self.state = State(domain, load_db(domain) if db is None else db)
        self._spec = tool_table()["domains"][domain]["tools"]
        self._open: Dict[str, dict] = {}           # tool_call_id -> call waiting for its tool message
        self.n_messages = 0

    def feed(self, messages: Iterable[dict]) -> "Tracker":
        for m in messages:
            self.feed_message(m)
        return self

    def feed_message(self, msg: dict) -> None:
        role = msg.get("role")
        if role == "assistant":
            step = self.state.n_steps
            self.state.n_steps += 1
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function") or {}
                raw = fn.get("arguments")
                args, err = raw, None
                if not isinstance(raw, dict):
                    try:
                        args = json.loads(raw or "{}")
                    except (TypeError, ValueError) as e:
                        args, err = {}, f"arguments are not JSON: {e}"
                self._open[tc.get("id")] = {"tool": fn.get("name"), "args": args, "step": step,
                                            "tool_call_id": tc.get("id"), "args_error": err}
        elif role == "tool":
            call = self._open.pop(msg.get("tool_call_id"), None)
            if call is None:
                self.state.problems.append(f"message {self.n_messages}: tool output without a matching call "
                                           f"(tool_call_id {msg.get('tool_call_id')!r})")
            else:
                self.apply_call(call["tool"], call["args"], msg.get("content"), step=call["step"],
                                tool_call_id=call["tool_call_id"], args_error=call["args_error"])
        self.n_messages += 1

    def finish(self) -> State:
        """Replay the calls whose output is not in the messages (the history ended right after the call).
        They ran, so they change the state; their event has match None."""
        for call in list(self._open.values()):
            self.state.problems.append(f"call {call['tool']} (tool_call_id {call['tool_call_id']!r}) has no output "
                                       f"in the history; replayed without a check")
            self.apply_call(call["tool"], call["args"], _MISSING, step=call["step"],
                            tool_call_id=call["tool_call_id"], args_error=call["args_error"])
        self._open.clear()
        return self.state

    def apply_call(self, tool: str, args: Dict[str, Any], saved: Any = _MISSING, step: Optional[int] = None,
                   tool_call_id: Optional[str] = None, args_error: Optional[str] = None) -> dict:
        """Replay one executed call and update the state. Returns its event:
        index (0, 1, ... in this conversation), step (executed steps before the call), tool, args, ok (worked),
        output (the saved output; the replayed one if there is none), match (replayed == saved; None if nothing
        was saved), json_match, changes_db (the tool can change the database, from tool_table.json),
        tool_call_id."""
        st = self.state
        # A copy of the arguments goes to the tool: some tools store argument lists in the database (book_reservation
        # stores `payment_methods` as the reservation's payment_history), and later calls append to them. Without
        # the copy, those changes would show up in this event's args.
        replayed = (f"Error: {args_error}" if args_error
                    else run_tool(self.domain, st.db, tool, copy.deepcopy(args)))
        has_saved = saved is not _MISSING
        exact, json_eq = outputs_equal(replayed, saved) if has_saved else (None, None)
        output = saved if has_saved else replayed
        ev = {"index": len(st.events), "step": step if step is not None else st.n_steps, "tool": tool,
              "args": args, "ok": not is_failure(output), "output": output, "match": exact, "json_match": json_eq,
              "changes_db": bool(self._spec.get(tool, {}).get("changes_db", False)), "tool_call_id": tool_call_id}
        if has_saved and not exact:
            st.mismatches.append({"event": ev["index"], "step": ev["step"], "tool": tool, "args": args,
                                  "saved": saved, "replayed": replayed, "json_equal": json_eq})
            if self.strict:
                raise ReplayMismatch(f"event {ev['index']} ({tool}): replayed output differs from the saved one")
        if ev["ok"]:
            objs, problem = parse_output(self.domain, tool, args, output)
            if problem:
                st.parse_problems.append({"event": ev["index"], "step": ev["step"], "tool": tool,
                                          "problem": problem, "output": str(output)[:300]})
            for kind, oid, version in objs:
                st.add_shown(kind, oid, version, ev)
        st.events.append(ev)
        return ev


# ----------------------------------------------------------------------------------------------- entry points

def normalize_action(action: Any) -> Optional[dict]:
    """The pending action as {"tool", "args", "kind"}. Accepts a Part 2 step record ("action", "kwargs"),
    a τ-bench Action-like dict ("name", "kwargs"), {"tool", "args"}, a (name, kwargs) pair, or None.
    A reply to the user has tool "respond" and args {"content": text}."""
    if action is None:
        return None
    if isinstance(action, (tuple, list)) and len(action) == 2:
        name, kwargs = action
    elif isinstance(action, dict) and "action" in action:
        name, kwargs = action["action"], action.get("kwargs") or {}
    elif isinstance(action, dict) and "name" in action:
        name, kwargs = action["name"], action.get("kwargs") or {}
    elif isinstance(action, dict) and "tool" in action:
        name, kwargs = action["tool"], action.get("args") or {}
    else:
        raise TypeError(f"cannot read the pending action from {type(action).__name__}")
    return {"tool": name, "args": kwargs, "kind": "respond" if name == "respond" else "tool_call"}


def build_state(history: Sequence[dict], action: Any = None, domain: Optional[str] = None,
                strict: bool = False) -> State:
    """The state before a step: replays the executed tool calls in `history` (in order) on a fresh database copy.

    history  the executed messages before the step (Part 2: rec["history"]). Blocked calls are not in it, so they
             are not replayed. Calls that ran through the cap override are in it and are replayed.
    action   the pending action (not replayed); see normalize_action(). Stored as state.pending.
    domain   'airline' or 'retail'; if None, taken from the system message (the policy) or the tool names.
    strict   raise ReplayMismatch at the first replayed output that differs from the saved one.
    """
    domain = domain or infer_domain(history)
    st = Tracker(domain, strict=strict).feed(history).finish()
    st.pending = normalize_action(action)
    return st


def walk(executed: Sequence[dict], domain: Optional[str] = None, stops: Optional[Iterable[int]] = None,
         strict: bool = False) -> Iterator[Tuple[int, State]]:
    """One pass over a whole conversation, for many steps at once (faster than build_state per step).
    Yields (n, state) where state is built from executed[:n], for each n in stops (default: every n). The same
    State object is yielded each time and changes after the next iteration, so use it before going on.
    Unlike build_state(), a call whose output comes after the cut n is not applied yet (it is applied when its
    output arrives). Part 2 histories always end after an output, so both give the same state there."""
    domain = domain or infer_domain(executed)
    tr = Tracker(domain, strict=strict)
    wanted = sorted(set(range(len(executed) + 1) if stops is None else stops))
    i = 0
    for n in wanted:
        while i < min(n, len(executed)):
            tr.feed_message(executed[i])
            i += 1
        yield n, tr.state
