"""Tracker v3, part 7: the message view, the text-structure helpers and the screens.

The view (docs/planning/tracker_v3/p7.md, piece 1) is built from the executed history the guard saw, never cut:
    view = build_view(history, pending={"tool": tool, "args": args}, state=state, domain=domain)
Entries, in order (the system message is not an entry); each entry's ref is its index in view.entries:
    role        "user" | "agent" (an assistant message without a tool call) | "tool" (one executed call + its output)
    text        the raw text (a tool entry: the output)
    norm        the normalized text: accents removed, curly quotes straight, markdown removed, spaces collapsed, lower
                case ("#" before an id and "_" inside an id are kept)
    tool, args, ok    tool entries: the tool name, the call's arguments (parsed from the agent's message), worked
    hist_index  the index of the message in the history
view.pending_ref = len(view.entries) is the ref of the pending reply; view.text(ref) / view.norm(ref) / view.role(ref)
work for it. view.prefix(n) gives the view of history[:n] (the entries are shared; used by the offline runs).

The helpers (piece 2; the full list with meanings is output/eval_v3/p7_api.md) are registered on import with
facts_format_v3.register_name(..., source="structure"), so structure and question parts may call them. `me` is
registered with source "event" (the retail login is an event), so a database part may call it too. A helper is a
plain function f(ctx, *args); p8's question helpers may call it from Python with their own ctx.

Rules that every helper follows:
  - value matching is on the normalized text, whole tokens only (no letter, digit or "_" right before or after);
    an order id matches with and without "#"; a 5-digit zip matches inside a ZIP+4; a date YYYY-MM-DD matches six
    forms (ISO, M/D/YYYY, MM/DD/YYYY, DD/MM/YYYY, "Month D, YYYY", "D Month YYYY"; also "-" or "." separators, short
    month names, ordinals and two-digit years);
  - lists of refs are newest first;
  - "before the call" is the whole view: every message of the history before the check, never cut at 24,000
    characters;
  - database reads go through ctx.state (the part's recording state), so they are recorded; a nonexistent object
    raises facts_format_v3.MissingObject (the part takes its if_nonexistent value, default false); a missing argument
    goes through ctx.arg (the fact takes its blocking value);
  - a screen (word list, SCREENS) only decides which messages a tiny question is asked about. It never sets a value
    alone.

Standard library only. No LLM call, no network. Never imports gold code or a scoring module.
"""
from __future__ import annotations

import datetime
import functools
import json
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from state_tracker.v3 import facts_format_v3 as F

SOURCE = "structure"
NO_DATA_TOOLS = ("calculate", "think")                       # their output comes from the agent's own arguments
FIND_TOOLS = ("find_user_id_by_email", "find_user_id_by_name_zip")
CATALOG_TOOLS_RETAIL = ("get_product_details", "list_all_product_types")
RETAIL_ORDER_TOOLS = ("cancel_pending_order", "modify_pending_order_address", "modify_pending_order_items",
                      "modify_pending_order_payment", "return_delivered_order_items",
                      "exchange_delivered_order_items", "get_order_details")
AIRLINE_RES_TOOLS = ("get_reservation_details", "update_reservation_flights", "update_reservation_baggages",
                     "update_reservation_passengers", "cancel_reservation")
AIRLINE_CHANGE_TOOLS = ("update_reservation_flights", "update_reservation_baggages", "update_reservation_passengers",
                        "cancel_reservation")
LISTING_LIMIT = 4                                            # p5: the 4 newest candidates (p8 may change it)


# ----------------------------------------------------------------------------------------------- normalization

_TRANS = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'", "ʼ": "'", "＇": "'",
    "`": "", "´": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"', "«": '"', "»": '"',
    "＂": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", " ": " ", " ": " ", "​": "", "﻿": "",
})
_MD_LINK = re.compile(r"!?\[([^\]\n]*)\]\(([^)\s]*)\)")
_MD_HEAD = re.compile(r"(?m)^[ \t]*#{1,6}[ \t]+")
_MD_QUOTE = re.compile(r"(?m)^[ \t]*>+[ \t]?")
_MD_RULE = re.compile(r"(?m)^[ \t]*([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_SPACES = re.compile(r"\s+")


def _to_text(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if isinstance(x, (dict, list)):
        return json.dumps(x)
    return str(x)


def deaccent(text: Any) -> str:
    """Accents removed (NFKD), curly quotes and dashes straight, odd spaces plain. Case and markdown kept."""
    t = unicodedata.normalize("NFKD", _to_text(text))
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return t.translate(_TRANS)


@functools.lru_cache(maxsize=200000)
def _normalize(text: str, lower: bool) -> str:
    t = deaccent(text)
    t = _MD_LINK.sub(r"\1", t)
    t = _MD_HEAD.sub("", t)
    t = _MD_QUOTE.sub("", t)
    t = _MD_RULE.sub(" ", t)
    t = t.replace("**", "").replace("__", "").replace("~~", "").replace("*", "")
    t = _SPACES.sub(" ", t).strip()
    return t.lower() if lower else t


def normalize(text: Any) -> str:
    """The normalized text: accents removed, curly quotes straight, markdown removed, spaces collapsed, lower case."""
    return _normalize(_to_text(text), True)


def plain(text: Any) -> str:
    """As normalize(), but the case is kept (for upper-case codes such as IATA airport codes)."""
    return _normalize(_to_text(text), False)


# ----------------------------------------------------------------------------------------------- value matching

_TOKCH = "a-z0-9_"


_ALPHA_FORM = re.compile(r"[a-z][a-z' .-]*")


@functools.lru_cache(maxsize=200000)
def _form_re(form: str, case: bool = False) -> "re.Pattern[str]":
    """A whole-token pattern. For a form made of letters only (a name, a word), "_" also separates tokens, so a
    user who types the user id "daiki_johnson_9523" has typed the names Daiki and Johnson."""
    body = re.escape(form).replace(r"\ ", r"\s+")
    if case:
        return re.compile(rf"(?<![A-Za-z0-9_]){body}(?![A-Za-z0-9_])")
    tok = "a-z0-9" if _ALPHA_FORM.fullmatch(form) else _TOKCH
    return re.compile(rf"(?<![{tok}]){body}(?![{tok}])")


def has_form(norm_text: str, form: str) -> bool:
    """`form` (normalized) appears in the normalized text as a whole token."""
    if not form or form not in norm_text:
        return False
    return _form_re(form).search(norm_text) is not None


def form_spans(norm_text: str, form: str) -> List[Tuple[int, int]]:
    if not form or form not in norm_text:
        return []
    return [m.span() for m in _form_re(form).finditer(norm_text)]


_ORDER_ID = re.compile(r"#?w\d{5,}")
_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _scalar(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, (str, int, float)):
        return value
    raise TypeError(f"a text or a number is needed, not a {type(value).__name__}")


@functools.lru_cache(maxsize=100000)
def _value_forms(value: Any) -> Tuple[str, ...]:
    v = normalize(str(value))
    if not v:
        return ()
    forms = [v]
    if _ORDER_ID.fullmatch(v):
        bare = v.lstrip("#")
        forms += ["#" + bare, bare]
    return tuple(dict.fromkeys(forms))


def value_forms(value: Any) -> Tuple[str, ...]:
    """The normalized forms that name a value in a text (section 2 of p7_api.md; dates are matched by dates_in)."""
    value = _scalar(value)
    if value is None or isinstance(value, bool):
        return ()
    return _value_forms(value)


_MONTHS = {"january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "apr": 4, "may": 5,
           "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
           "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12}
_MON = "|".join(sorted(_MONTHS, key=len, reverse=True))
_ORD = r"(?:st|nd|rd|th)?"
_D_ISO = re.compile(r"(?<![0-9])(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?![0-9])")
_D_NUM = re.compile(r"(?<![0-9])(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})(?![0-9])")
_D_MDY = re.compile(rf"(?<![a-z])({_MON})\.?\s+(\d{{1,2}}){_ORD},?\s+(?:of\s+)?(\d{{4}})(?![0-9])")
_D_DMY = re.compile(rf"(?<![0-9])(\d{{1,2}}){_ORD}\s+(?:of\s+)?({_MON})\.?,?\s+(\d{{4}})(?![0-9])")
_D_MD = re.compile(rf"(?<![a-z])({_MON})\.?\s+(\d{{1,2}}){_ORD}(?![0-9])")
_D_DM = re.compile(rf"(?<![0-9])(\d{{1,2}}){_ORD}\s+(?:of\s+)?({_MON})(?![a-z])")
_D_NUM_MD = re.compile(r"(?<![0-9/.-])(\d{1,2})/(\d{1,2})(?![0-9/])")


def _iso(y: int, m: int, d: int) -> Optional[str]:
    try:
        return datetime.date(y, m, d).isoformat()
    except ValueError:
        return None


def _years(y: str) -> List[int]:
    if len(y) == 4:
        return [int(y)]
    return [1900 + int(y), 2000 + int(y)]


@functools.lru_cache(maxsize=100000)
def dates_in(norm_text: str) -> frozenset:
    """Every date (YYYY-MM-DD) a normalized text names in one of the six forms (both readings of a/b/yyyy)."""
    out = set()
    for y, m, d in _D_ISO.findall(norm_text):
        out.add(_iso(int(y), int(m), int(d)))
    for a, b, y in _D_NUM.findall(norm_text):
        for yy in _years(y):
            out.add(_iso(yy, int(a), int(b)))
            out.add(_iso(yy, int(b), int(a)))
    for mon, d, y in _D_MDY.findall(norm_text):
        out.add(_iso(int(y), _MONTHS[mon], int(d)))
    for d, mon, y in _D_DMY.findall(norm_text):
        out.add(_iso(int(y), _MONTHS[mon], int(d)))
    out.discard(None)
    return frozenset(out)


@functools.lru_cache(maxsize=100000)
def month_days_in(norm_text: str) -> frozenset:
    """(month, day) pairs named without a year ('May 20', '20 May', '5/20'): used only to find listing candidates."""
    out = set()
    for mon, d in _D_MD.findall(norm_text):
        out.add((_MONTHS[mon], int(d)))
    for d, mon in _D_DM.findall(norm_text):
        out.add((_MONTHS[mon], int(d)))
    for a, b in _D_NUM_MD.findall(norm_text):
        out.add((int(a), int(b)))
    return frozenset(out)


def text_has_value(norm_text: str, value: Any) -> bool:
    """The normalized text names the value (whole token; order ids with and without '#'; dates in six forms)."""
    forms = value_forms(value)
    if not forms:
        return False
    if any(has_form(norm_text, f) for f in forms):
        return True
    if _ISO.fullmatch(forms[0]) and forms[0] in dates_in(norm_text):
        return True
    return False


def text_names_date(norm_text: str, iso: Any, without_year: bool = False) -> bool:
    if not isinstance(iso, str) or not _ISO.fullmatch(iso):
        return False
    if iso in dates_in(norm_text) or has_form(norm_text, iso):
        return True
    if without_year:
        y, m, d = (int(x) for x in iso.split("-"))
        return (m, d) in month_days_in(norm_text)
    return False


# ----------------------------------------------------------------------------------------------- the view

def _parse_args(raw: Any) -> Tuple[Dict[str, Any], Optional[str]]:
    if isinstance(raw, dict):
        return raw, None
    try:
        x = json.loads(raw or "{}")
    except (TypeError, ValueError) as e:
        return {}, f"arguments are not JSON: {e}"
    return (x, None) if isinstance(x, dict) else ({}, "arguments are not a JSON object")


def is_failure(output: Any) -> bool:
    """As state.is_failure: an output that is not a text, or starts with 'Error' / 'Unknown action'."""
    return not isinstance(output, str) or output.startswith("Error") or output.startswith("Unknown action")


class Entry:
    """One message of the view. norm is computed when first read."""

    def __init__(self, ref: int, role: str, text: str, hist_index: int, tool: Optional[str] = None,
                 args: Optional[dict] = None, ok: Optional[bool] = None, call_id: Optional[str] = None,
                 call_index: Optional[int] = None, call_text: Optional[str] = None):
        self.ref = ref
        self.role = role
        self.text = text
        self.hist_index = hist_index
        self.tool = tool
        self.args = args if args is not None else {}
        self.ok = ok
        self.call_id = call_id
        self.call_index = call_index            # the history index of the agent message that made the call
        self.call_text = call_text              # text of that agent message, if it had any (not shown to the user)
        self._norm: Optional[str] = None
        self._plain: Optional[str] = None

    @property
    def norm(self) -> str:
        if self._norm is None:
            self._norm = normalize(self.text)
        return self._norm

    @property
    def plain(self) -> str:
        if self._plain is None:
            self._plain = plain(self.text)
        return self._plain

    def __repr__(self) -> str:
        return f"Entry({self.ref}, {self.role}, {self.tool or ''} {self.text[:40]!r})"


def _pending_of(pending: Any, state: Any) -> Tuple[Optional[str], Dict[str, Any]]:
    if pending is None and state is not None:
        pending = getattr(state, "pending", None)
    if pending is None:
        return None, {}
    if isinstance(pending, (tuple, list)) and len(pending) == 2:
        return pending[0], dict(pending[1] or {})
    if isinstance(pending, dict):
        tool = pending.get("tool", pending.get("name", pending.get("action")))
        args = pending.get("args", pending.get("kwargs")) or {}
        return tool, dict(args)
    raise TypeError(f"cannot read the pending call from a {type(pending).__name__}")


class MessageView:
    """The message view of one check (see the module text)."""

    def __init__(self, entries: List[Entry], pending: Any = None, state: Any = None, domain: Optional[str] = None,
                 n_history: Optional[int] = None, problems: Optional[List[str]] = None):
        self.entries = entries
        self.state = state
        self.domain = domain or getattr(state, "domain", None)
        self.pending_tool, self.pending_args = _pending_of(pending, state)
        self.pending_text = (_to_text(self.pending_args.get("content")) if self.pending_tool == "respond" else None)
        self.pending_ref = len(entries)
        self.n_history = n_history
        self.problems = list(problems or [])
        self.cache: Dict[Any, Any] = {}
        self._pending_norm: Optional[str] = None

    # --- texts by ref
    def _check(self, ref: Any) -> int:
        if isinstance(ref, bool) or not isinstance(ref, int):
            raise TypeError(f"a message ref is an int, not {ref!r}")
        if ref == self.pending_ref:
            if self.pending_text is None:
                raise IndexError(f"ref {ref} is the pending call, which is not a reply")
            return ref
        if not 0 <= ref < len(self.entries):
            raise IndexError(f"no message with ref {ref}")
        return ref

    def text(self, ref: int) -> str:
        ref = self._check(ref)
        return self.pending_text if ref == self.pending_ref else self.entries[ref].text

    def norm(self, ref: int) -> str:
        ref = self._check(ref)
        if ref == self.pending_ref:
            if self._pending_norm is None:
                self._pending_norm = normalize(self.pending_text)
            return self._pending_norm
        return self.entries[ref].norm

    def plain(self, ref: int) -> str:
        ref = self._check(ref)
        return plain(self.pending_text) if ref == self.pending_ref else self.entries[ref].plain

    def role(self, ref: int) -> str:
        ref = self._check(ref)
        return "agent" if ref == self.pending_ref else self.entries[ref].role

    # --- refs (oldest first)
    def refs(self, role: str) -> List[int]:
        key = ("refs", role)
        if key not in self.cache:
            self.cache[key] = [e.ref for e in self.entries if role == "any" or e.role == role]
        return self.cache[key]

    def user_refs(self) -> List[int]:
        return self.refs("user")

    def agent_refs(self) -> List[int]:
        return self.refs("agent")

    def tool_refs(self) -> List[int]:
        return self.refs("tool")

    def data_tool_refs(self) -> List[int]:
        """Worked tool calls other than calculate / think (their outputs hold data from the tools)."""
        return [r for r in self.tool_refs() if self.entries[r].ok and self.entries[r].tool not in NO_DATA_TOOLS]

    def prefix(self, n_history: int, pending: Any = None, state: Any = None) -> "MessageView":
        """The view of history[:n_history] (entries shared), with its own pending call and state."""
        ents = [e for e in self.entries if e.hist_index < n_history]
        return MessageView(ents, pending, state, self.domain, n_history, self.problems)


def build_view(history: Sequence[dict], pending: Any = None, state: Any = None,
               domain: Optional[str] = None) -> MessageView:
    """The view of an executed history (chat messages: system / user / assistant with or without tool_calls /
    tool). Nothing is cut. pending: {"tool", "args"} (or (tool, args), or None: the state's pending call)."""
    entries: List[Entry] = []
    problems: List[str] = []
    open_calls: Dict[Any, dict] = {}
    for i, m in enumerate(history):
        role = m.get("role")
        if role == "system":
            continue
        if role == "user":
            entries.append(Entry(len(entries), "user", _to_text(m.get("content")), i))
        elif role == "assistant":
            calls = m.get("tool_calls") or []
            if not calls:
                entries.append(Entry(len(entries), "agent", _to_text(m.get("content")), i))
                continue
            text = m.get("content")
            if text:
                problems.append(f"message {i}: an agent message with text and a tool call (text kept as call_text)")
            for tc in calls:
                fn = tc.get("function") or {}
                args, err = _parse_args(fn.get("arguments"))
                if err:
                    problems.append(f"message {i}: {err}")
                open_calls[tc.get("id")] = {"tool": fn.get("name"), "args": args, "index": i,
                                            "text": _to_text(text) if text else None}
        elif role == "tool":
            call = open_calls.pop(m.get("tool_call_id"), None)
            if call is None:
                problems.append(f"message {i}: tool output without a matching call")
                call = {"tool": m.get("name"), "args": {}, "index": None, "text": None}
            out = m.get("content")
            entries.append(Entry(len(entries), "tool", _to_text(out), i, tool=call["tool"], args=call["args"],
                                 ok=not is_failure(out), call_id=m.get("tool_call_id"), call_index=call["index"],
                                 call_text=call["text"]))
        else:
            problems.append(f"message {i}: unknown role {role!r}")
    for cid, call in open_calls.items():
        problems.append(f"call {call['tool']} ({cid}) has no output in the history")
    return MessageView(entries, pending, state, domain or getattr(state, "domain", None), len(history), problems)


def reconstruct(view: MessageView) -> List[dict]:
    """The history messages the view stands for, rebuilt from the entries (for the P7.1 check): user and agent
    entries as {role, content}; a tool entry as {role: "tool", tool, args, content}."""
    out = []
    for e in view.entries:
        if e.role == "tool":
            out.append({"role": "tool", "tool": e.tool, "args": e.args, "content": e.text})
        else:
            out.append({"role": "user" if e.role == "user" else "assistant", "content": e.text})
    return out


# ----------------------------------------------------------------------------------------------- screens

def _alts(*words: str) -> str:
    return "|".join(words)


# Word lists: regular expressions over the normalized text (lower case, accents removed). Wide on purpose: a screen
# only decides whether a tiny question is asked; a hit that is not a case costs one question, a miss can cost a
# wrong decision. Written from the policy and the fact definitions, before any constructed test set was read.
SCREENS: Dict[str, List[str]] = {
    # K4 / K5: another person (retail S5: "must deny any requests for tasks related to any other user")
    "other_person": [
        r"\b(?:wife|husband|spouse|partner|fiance|fiancee|boyfriend|girlfriend|bf|gf|hubby|wifey)s?\b",
        r"\b(?:mom|mum|mommy|mummy|mama|mother|dad|daddy|papa|father|parents?|stepmom|stepmother|stepdad|stepfather)s?\b",
        r"\b(?:son|daughter|kid|kids|child|children|baby|toddler|teen|teenager|boy|girl|stepson|stepdaughter)s?\b",
        r"\b(?:brother|sister|sibling|bro|sis|twin|cousin|aunt|auntie|uncle|nephew|niece|relative|family|in-laws?)s?\b",
        r"\b(?:grandma|grandmother|grandpa|grandfather|grandparents?|grandson|granddaughter|grandchild|grandchildren|"
        r"granny|nana|gran)s?\b",
        r"\b(?:friend|buddy|pal|mate|colleague|coworker|co-worker|boss|manager|supervisor|employee|employer|staff|"
        r"assistant|secretary|client|neighbou?r|roommate|flatmate|housemate|tenant|landlord|landlady|classmate|"
        r"teammate|guest|caregiver|caretaker|patient|student|teacher|acquaintance|associate)s?\b",
        r"\b(?:someone|somebody|anyone else|anybody else|another person|other person|another people|other people|"
        r"another user|other user|another customer|other customer|another account|other account|third party|"
        r"third-party|a stranger|this person|that person|the person|the owner|account holder|account owner|"
        r"cardholder|card holder)\b",
        r"\bon (?:his|her|their|someone'?s|somebody'?s|behalf)\b|\bbehalf\b",
        r"\b(?:he|she|they|him|her|hers|his|them|their|theirs|themselves|himself|herself)\b",
        r"\b(?:he|she|they)'(?:s|re|ve|ll|d)\b",
        r"\b(?:not|isn'?t|aren'?t|wasn'?t) (?:mine|my own|my account|my order|my email|me)\b|\bnot my\b",
        r"\b(?:belongs? to|belonged to|registered to|registered under|under (?:the|his|her|their|a different) name|"
        r"in (?:his|her|their) name|under someone|for someone|for somebody|for a friend|for my)\b",
        r"\b(?:asked me to|told me to|wants me to|wanted me to|asking for|calling for|helping|help out|"
        r"handling (?:this|it) for|doing this for|sent me|gave me (?:his|her|their))\b",
        r"\b(?:mr|mrs|ms|miss|dr)\.? [a-z]+",
        r"\b(?!(?:it|that|what|let|there|here|he|she|who|where|how|when|why|one|today|tomorrow|yesterday|everyone|"
        r"everybody|nobody|somebody|someone|anyone|anybody|this|which|thats|name|order|item|product|company|store|"
        r"world|week|month|year|day|night)'s\b)[a-z]+'s\b",
        r"\b[a-z]+s' (?:order|account|email|address|card|items?|package)\b",
        r"\b(?:his|her|their) (?:order|account|email|address|card|purchase|package|items?|details|info)\b",
    ],
    # K6: a health or weather reason for cancelling (airline S39)
    "health": [
        r"\b(?:sick|sickness|ill|illness|ills|unwell|not well|not feeling well|feel(?:ing)? (?:bad|awful|terrible|"
        r"horrible|poorly|rough|lousy)|under the weather|poorly)\b",
        r"\b(?:health|healthy|medical|medic\w*|medicine|medication|meds|prescription|hospital\w*|surgery|surgeries|"
        r"surgical|operation|operated|doctor|doctors|doc|dr|physician|nurse|clinic|er|emergency room|urgent care|"
        r"ambulance|paramedic\w*|icu|intensive care|ward|admitted)\b",
        r"\b(?:injur\w*|hurt|hurts|broke|broken|fractur\w*|sprain\w*|wound\w*|accident\w*|crash\w*|bruis\w*|"
        r"concussion|stitches|cast|crutches|wheelchair|bed ?rest|bedridden|disab\w*|pain|painful|ache|aching)\b",
        r"\b(?:pregnan\w*|maternity|labou?r|giving birth|gave birth|birth|newborn|miscarr\w*|expecting a baby|"
        r"due date|c-section)\b",
        r"\b(?:covid\w*|corona\w*|flu|influenza|fever|feverish|cold|virus|viral|infection|infected|contagious|"
        r"quarantin\w*|isolat\w*|cough\w*|pneumonia|bronchitis|asthma|allerg\w*|migraine\w*|headache\w*|nause\w*|"
        r"vomit\w*|diarrh\w*|food poisoning|stomach|appendi\w*|tonsil\w*|strep|measles|chickenpox|shingles|rash|"
        r"sinus\w*|ear infection)\b",
        r"\b(?:heart|cardiac|stroke|seizure\w*|epilep\w*|cancer|tumou?r|chemo\w*|radiation|therap\w*|treatment\w*|"
        r"diagnos\w*|disease\w*|condition|symptom\w*|recover\w*|rehab\w*|dialysis|diabet\w*|blood|kidney|liver|"
        r"lung\w*|transplant|biopsy|scan|mri|x-ray|test results|tested positive|positive test|dental|dentist|"
        r"tooth|teeth|toothache|eye|vision)\b",
        r"\b(?:mental|anxiety|anxious|panic|depress\w*|stress\w*|burnout|breakdown|psychiatric|dementia|alzheimer\w*|"
        r"hospice|terminal|dying|died|death|dead|passed away|passing|funeral|bereave\w*|grief|care home|"
        r"nursing home)\b",
        r"\b(?:unable to fly|can'?t fly|cannot fly|not fit to fly|fit to fly|unfit|too weak|weak|exhausted|"
        r"doctor'?s orders|emergency|emergencies|urgent|vet|veterinar\w*)\b",
        r"\b(?:weather|storm\w*|hurricane\w*|typhoon\w*|cyclone\w*|tornado\w*|twister|snow\w*|blizzard\w*|ice|icy|"
        r"sleet|hail\w*|freez\w*|frost\w*|frozen|flood\w*|rain\w*|monsoon\w*|thunder\w*|lightning|wind|winds|windy|"
        r"gale\w*|fog|foggy|heat ?wave|extreme heat|heat|wildfire\w*|fire|fires|smoke|smog|volcan\w*|ash cloud|"
        r"earthquake\w*|quake|tsunami|landslide\w*|mudslide\w*|avalanche\w*|natural disaster|disaster|evacuat\w*|"
        r"state of emergency|severe|forecast\w*|climate|tropical|el nino|road closures?|roads? (?:are )?closed)\b",
    ],
    # K8 / K16: a cancelled flight, or a wish to cancel (airline S41, S43)
    "cancel": [
        r"\bcancel\w*|\bcanx\b|\bcncl\b",
        r"\b(?:call(?:ed|ing)? off|scrap\w*|axe[ds]?|axing|nix\w*|scratch(?:ed)?|kill(?:ed)? (?:the|my|this))\b",
        r"\b(?:drop(?:ped)?|delete[ds]?|deleting|remove[ds]?|removing|void(?:ed)?|terminat\w*|undo|withdraw\w*|"
        r"get rid of|back out|backing out|pull(?:ed)? (?:out|the plug))\b",
        r"\b(?:refund\w*|money back)\b",
        r"\b(?:not going|won'?t be (?:going|traveling|travelling|flying|taking|using|able)|can'?t make it|"
        r"cannot make it|unable to (?:make it|go|travel|fly|attend)|not (?:traveling|travelling|flying|"
        r"taking (?:the|this|my) (?:trip|flight))|no longer (?:need|want|going|traveling|travelling|able|"
        r"operating|running|flying|available|scheduled|happening|on)|don'?t (?:need|want) (?:the|this|my|it)|"
        r"do not (?:need|want) (?:the|this|my|it))\b",
        r"\b(?:didn'?t|did not|never|won'?t|will not|isn'?t|is not|wasn'?t|was not|not) (?:fly|flying|flew|"
        r"operate|operating|operated|depart|departing|departed|leave|leaving|left|take off|took off|happen|"
        r"happening|go|going|run|running|scheduled)\b",
        r"\b(?:grounded|discontinued|suspended|removed from the schedule|taken off the schedule|struck off|"
        r"called it off|out of service)\b",
        r"\b(?:anymore|any more|disappeared|vanished|gone|is off|was off|scrubbed|bumped|got (?:pulled|dropped|"
        r"killed|bumped|scrubbed|binned)|take (?:me|us|it|them|him|her) off|staying home|stay home|change of plans?|"
        r"plans? (?:changed|have changed|fell through)|not (?:do|take|make|use) (?:the|this|my|our) (?:trip|flight|"
        r"reservation|booking)|skip (?:the|this|my|our) (?:trip|flight))\b",
    ],
    # K9: a delayed flight (airline S44)
    "delay": [
        r"\bdelay\w*|\blate\b|\blater\b|\blateness\b|\btardy\b|\boverdue\b",
        r"\b(?:behind schedule|not on time|wasn'?t on time|isn'?t on time|off schedule|on time)\b",
        r"\b(?:still waiting|been waiting|keep waiting|waiting (?:at|for|on|around|here|in)|wait(?:ed|ing)? "
        r"(?:hours|forever|ages|so long)|wait time|hours?|minutes?|mins?)\b",
        r"\b(?:postpon\w*|push(?:ed)? back|pushed|held up|hold up|holding|stuck|stranded|tarmac|gate|"
        r"hasn'?t (?:left|departed|taken off|boarded|arrived)|has not (?:left|departed|taken off|boarded|arrived)|"
        r"never (?:took off|left|departed|arrived)|didn'?t (?:leave|depart|take off|arrive) on time)\b",
        r"\b(?:missed|miss|missing) (?:my|the|our|a)? ?(?:connection|connecting|flight|meeting|event|wedding|"
        r"appointment)\b|\bmissed\b",
        r"\b(?:reschedul\w*|retim\w*|moved (?:to|back)|new departure|estimated departure|taking forever|forever|"
        r"ages|eternity|slow|sitting (?:on|at|in|here))\b",
        r"\bbehind\b|\bschedul\w*|\b(?:took off|left|departed|arrived|landed) (?:way|very|so|really|much)? ?"
        r"(?:after|past)\b|\b(?:still|yet) (?:on the ground|at the gate|not boarding|not boarded|boarding)\b",
    ],
    # K10: an explicit request for compensation (airline S43-S45)
    "compensation_request": [
        r"\bcompensat\w*|\bcertificate\w*|\bvoucher\w*|\bcredit\w*|\brefund\w*|\breimburs\w*|\brepay\w*",
        r"\b(?:money back|cash|pay (?:me|back|for)|paid back|gesture|goodwill|make up for|make it up|"
        r"make (?:it|this|things) right|something for|anything for|do something|do anything|the least you can do|"
        r"what can you (?:do|offer)|what will you do|what are you going to do|what are you gonna do)\b",
        r"\b(?:for (?:the|my|this|our|all the) (?:trouble|inconvenience|hassle|delay|cancell?ation|issue|problem|"
        r"mess)|inconvenience\w*|trouble|hassle|deserve\w*|owed?|owes|entitle\w*|claim\w*|damages)\b",
        r"\b(?:offer\w*|discount\w*|free|upgrade\w*|miles|points|bonus|perk\w*|coupon\w*|gift|reward\w*|rebate\w*|"
        r"waive\w*|fee|fees|apolog\w*|sorry)\b",
        r"\$\s?\d|\b\d+ ?(?:dollars?|usd|bucks)\b|\b(?:dollars?|usd|bucks)\b",
        r"\b(?:cover (?:the|my|our)? ?(?:cost|costs|expenses?|hotel|meals?|taxi|uber|food)|expenses?|hotel|meals?|"
        r"food|taxi|uber|lyft|lounge|accommodation\w*|lodging)\b",
        r"\b(?:i expect|i want something|i'?d like something|give me something|anything you can|any way you can)\b",
    ],
    # K12: the pending reply offers compensation (airline S43-S46). The wide list also catches offers without the
    # word "certificate".
    "offer": [
        r"\bcertificate\w*|\bvoucher\w*|\bcompensat\w*|\bgesture\b|\bgoodwill\b|\bcredit\w*|\bcoupon\w*",
        r"\b(?:as a courtesy|courtesy|make it up|make up for|make amends|make (?:it|this|things) right|"
        r"for the inconvenience|for your trouble|for the trouble|token of)\b",
        r"\$\s?\d|\b\d+ ?(?:dollars?|usd|bucks)\b|\b(?:dollars?|usd|bucks)\b",
        r"\b(?:refund\w*|reimburs\w*|discount\w*|free|complimentary|on us|on the house|waive\w*|upgrade\w*|miles|"
        r"points|bonus|reward\w*|rebate\w*|gift|travel fund\w*|future travel|future (?:flight|booking|trip)|"
        r"towards? (?:a|your|any) (?:future|next)|e-?credit\w*|wallet)\b",
        r"\b(?:apolog\w*|sorry|offer\w*|provide you with|issue you|send you|give you|grant you|eligible for|"
        r"entitled to|lounge|meal|meals|hotel|accommodation\w*)\b",
    ],
}
# Added after blind set 1 (output/eval_v3/p7_screen_sets/set1): typos, idioms and wordings without the key word.
SCREENS["other_person"] += [
    r"\b(?:second|other|another|different|separate) (?:account|profile|user|customer|person|login|member)\b",
    r"\b(?:the|that|this) (?:user|person|customer|account|profile|member|passenger) (?:you'?re|you are|you were|"
    r"you'?ve been) (?:assisting|helping|asking about|calling about|calling for|acting for|working with)\b",
    r"\b(?:you'?re|you are|you were) (?:assisting|helping|calling for|asking for|acting for|acting on behalf)\b",
    r"\b(?:account|profile|user|person|order|reservation) (?:you|that you) (?:asked|inquired|gave|mentioned|"
    r"provided|shared)\b",
    r"\b(?:folks|missus|better half|significant other|old man|old lady|my ex)\b|\bgod(?:mother|father|son|daughter|"
    r"parent)s?\b|\bstep\w+",
    r"\b(?:the|this|that|a) (?:guy|lady|woman|man|gentleman|girl|boy|fellow|gal|dude)\b",
]
SCREENS["health"] += [
    r"\bs+i+c*k+\w*|\bwh?ea?th?er\w*|\bhosp\w*|\bhur+[iy]?c\w*|\btorn[ae]d\w*|\bbliz+\w*|\w*storm\w*|\bstrom\w*|"
    r"\bpreg\w*|\bsurg\w*|\bemer?g\w*|\binj\w*|\bmed\w*|\bdoc\w*|\bill\w*",
    r"\b(?:threw|hurt|injured|pulled|strained|tweaked) (?:out )?(?:my|his|her|their|out)? ?(?:back|neck|knee|ankle|"
    r"shoulder|hip)\b|\bback (?:out|injury|pain|problems?|issues?)\b|\bbad back\b",
    r"\b(?:ankle|knee|leg|arm|wrist|hip|shoulder|neck|spine|foot|feet|hand|chest|throat|ribs?|elbow|head)s?\b",
    r"\b(?:ice[ds]?|icing|iced over|whiteout|nor'?easter|vortex|outage|power out|air quality|degrees)\b|\u00b0",
    r"\b(?:dizzy|dizziness|faint\w*|throwing up|threw up|bedbound|laid up|mourning|grieving|condolences|physio\w*|"
    r"baby|contractions|ob|obgyn|gyno?\w*|chemo\w*|infus\w*|ward)\b",
]
SCREENS["cancel"] += [
    r"\bcan[cx]\w*|\bcanc?l\w*|\bcanned\b|\bkill\w*|\bannul\w*|\brescind\w*|\brevok\w*|\bnullif\w*|\babort\w*",
    r"\b(?:wiped|wipe|erased?|trash\w*|release|free up|give up)\b|\b(?:from|off) the (?:schedule|board|books|system)\b",
    r"\bcall (?:it|this|that|them|the trip|the flight) off\b|\bget (?:me|us) out of\b|"
    r"\bout of (?:this|the|my|our) (?:reservation|booking|trip|flight)\b|\bun-?book\w*|\bun-?reserv\w*",
    r"\bforget (?:the|my|this|about)\b|\bwon'?t need\b|\bno (?:flight|plane)\b|'s off\b|\bhappened\b",
]
SCREENS["delay"] += [
    r"\bd\w{0,2}lay\w*|\bdela\w*",
    r"\b(?:supposed|meant|scheduled|due|planned|set) to\b",
    r"\b(?:moved|pushed|changed|shifted|slipped|bumped|went|jumped|got moved) (?:from|to|back|out)\b|\bslipp\w*",
    r"\b(?:is|was) now (?:a |at |an |)\d|\bnow (?:it'?s|it is|says|shows|leaves|departs|at|reads|listed)\b",
    r"\bestimated\b|\beta\b|\bnew (?:time|departure|arrival|eta)\b|\bgot in (?:at|around|after)\b",
    r"\b(?:lost|missed|missing|blew) (?:my|our|the|a) (?:connection|connecting|transfer|layover)\b|\bconnect\w*",
    r"\b\d{1,2}(?::\d{2})? ?(?:am|pm|a\.m\.|p\.m\.)\b.*\b\d{1,2}(?::\d{2})? ?(?:am|pm|a\.m\.|p\.m\.)\b",
    r"\b(?:on hold|all day|overnight|runway|lagging|haven'?t (?:left|departed|taken off|boarded|moved))\b",
]
# Added after blind set 2 (output/eval_v3/p7_screen_sets/set2).
SCREENS["health"] += [
    r"\b(?:my|his|her|their|a|bad|sore|aching|stiff|hurt|injured) back\b|\bkilling me\b|\b(?:sore|stiff|aching)\b",
    r"\bcan'?t (?:sit|walk|stand|move|breathe|see|hear|bend|lift)\b|\bcannot (?:sit|walk|stand|move|breathe)\b",
    r"\b(?:flare\w*|relapse\w*|attack|attacks|\w*pox|bug|in no shape|not in (?:any )?shape)\b",
    r"\b(?:pour\w*|drizzl\w*|gusts?|gusty|squall\w*|dust|visibility|slippery|roads?|advisor\w*|warnings?|alerts?|"
    r"erupt\w*|tremor\w*|aftershock\w*)\b",
]
SCREENS["delay"] += [
    r"\bon-?time\b|\bpunctual\w*|\btimetable\w*|\bclock\w*|\bmidnight\b|\bnoon\b|\binstead of\b",
    r"\b(?:until|till|til) \d|\bnot until\b|\bdidn'?t (?:leave|depart|take off|arrive|land|board|get in|go) until\b",
    r"\b\d{1,2}:\d{2}\b.*\b\d{1,2}:\d{2}\b",
    r"\bnow (?:departing|leaving|arriving|boarding|scheduled|set|showing|landing|expected)\b",
    r"\bwait\w*|\bboard\w*|\bpast \d|\bstill no\b|\btook forever\b|\bhours? late\b",
]
SCREENS["cancel"] += [r"\b(?:pulled|dead)\b"]
SCREENS["compensation_request"] += [
    r"\bwhat (?:do|will|can|would|should|could) (?:i|we) (?:get|receive|be given)\b|\bmoney\b|\bkomp\w*|"
    r"\bcompen\w*|\bindemn\w*|\brestitution\w*|\brecompense\w*|\bredress\w*|\breparation\w*|\bsettlement\w*|"
    r"\bpay ?out\w*|\bpay up\b|\bmake amends\b|\bgive (?:me|us) back\b|\bwhat are you (?:offering|giving)\b",
]
SCREENS["compensation_request"] += [
    r"\bmake (?:this|it|that|things) up\b|\bmake up\b|\bmake (?:it |this |that )?good\b|\bmake good on\b",
    r"\bcomp\w*|\bcost of\b|\bcover\b|\beligible\b|\bwhat'?s in it for\b",
    r"\b(?:get|receive|give me|give us|offer me|offer us) (?:anything|something|some)\b",
]
SCREENS["complaint"] = SCREENS["cancel"] + SCREENS["delay"]
# Case-sensitive patterns on the text with accents removed (case kept): a named person after a verb or preposition
# ("what did Sarah Lee order", "for Mr. Brown"), which the lower-case lists cannot see.
SCREENS_RAW: Dict[str, List[str]] = {
    "other_person": [
        r"\b(?:for|of|about|what|did|does|check|find|look up|lookup|tell me|help|account|order|orders|ordered|named|"
        r"called|is|was|with|by|whether|if)\s+(?:(?:Mr|Mrs|Ms|Miss|Dr)\.?\s+)?[A-Z][a-z]+\s+[A-Z][a-z]+\b",
        r"\b(?:Mr|Mrs|Ms|Miss|Dr)\.?\s+[A-Z][a-z]+",
    ],
}
SCREEN_FOR_QUESTION = {"K4": "other_person", "K5": "other_person", "K6": "health", "K8": "cancel", "K9": "delay",
                       "K10": "compensation_request", "K12": "offer", "K16": "cancel"}
# Blind set 3 (output/eval_v3/p7_screen_sets/set3), run once with the lists above unchanged, missed positives of K5,
# K8, K9 and K16. The pre-registered rule (preregistration.md change log, 2026-10-23 06:20): a topic with any miss
# loses its word screen, and its tiny question is asked on every candidate message. So the screens "cancel" (K8,
# K16), "delay" (K9) and "complaint" (cancel or delay) always hit, and other_person_screen() (K5, the reply side)
# always holds. K4 (catalog reads), K6, K10 and K12 had 0 misses and keep their screens. The word lists are kept
# unchanged (they still give screen_hits for evidence).
REMOVED_SCREENS = ("cancel", "delay", "complaint")
K5_SCREEN_REMOVED = True
REMOVED_BY_SET3 = {"K5": "other_person (reply side)", "K8": "cancel", "K9": "delay", "K16": "cancel"}


@functools.lru_cache(maxsize=None)
def _screen_re(name: str) -> "re.Pattern[str]":
    if name not in SCREENS:
        raise ValueError(f"unknown screen {name!r}; known: {sorted(SCREENS)}")
    return re.compile("|".join(f"(?:{p})" for p in SCREENS[name]))


@functools.lru_cache(maxsize=None)
def _screen_raw_re(name: str) -> Optional["re.Pattern[str]"]:
    pats = SCREENS_RAW.get(name)
    return re.compile("|".join(f"(?:{p})" for p in pats)) if pats else None


def _screen_hit(name: str, norm_text: str, plain_text: Optional[str]) -> bool:
    if name in REMOVED_SCREENS:                      # screen removed after blind set 3: ask always
        _screen_re(name)
        return True
    if _screen_re(name).search(norm_text):
        return True
    raw = _screen_raw_re(name)
    return raw is not None and plain_text is not None and raw.search(plain_text) is not None


def screen_hits(name: str, text: Any) -> List[str]:
    """The words of screen `name` found in a text (normalized here; the case-sensitive patterns on plain()). For a
    removed screen (REMOVED_SCREENS) these are evidence only: the screen itself always hits."""
    out = [m.group(0) for m in _screen_re(name).finditer(normalize(text))]
    raw = _screen_raw_re(name)
    if raw is not None:
        out += [m.group(0) for m in raw.finditer(plain(text))]
    return out


def screen_text(name: str, text: Any) -> bool:
    """Screen `name` hits the text."""
    return _screen_hit(name, normalize(text), plain(text))


# ----------------------------------------------------------------------------------------------- context access

def _view(ctx: Any) -> MessageView:
    return ctx.need_view()


def _state(ctx: Any) -> Any:
    st = getattr(ctx, "state", None)
    if st is None:
        st = getattr(_view(ctx), "state", None)
    return st


def _domain(ctx: Any) -> Optional[str]:
    v = getattr(ctx, "view", None)
    return getattr(ctx, "domain", None) or getattr(v, "domain", None)


def _tool(ctx: Any) -> Optional[str]:
    v = _view(ctx)
    if v.pending_tool is not None:
        return v.pending_tool
    st = _state(ctx)
    return ((getattr(st, "pending", None) or {}).get("tool")) if st is not None else None


def _db(ctx: Any, kind: str, oid: Any) -> Any:
    st = _state(ctx)
    if st is None:
        raise F.MissingInput("this helper needs the state (database)")
    return st.db_get(kind, oid) if isinstance(oid, str) else None


def _must(obj: Any, what: str) -> Any:
    if obj is None:
        raise F.MissingObject(f"{what} does not exist")
    return obj


def _ref_or_text_norm(ctx: Any, x: Any) -> str:
    if isinstance(x, bool):
        raise TypeError("a ref or a text is needed")
    if isinstance(x, int):
        return _view(ctx).norm(x)
    if isinstance(x, str):
        return normalize(x)
    raise TypeError(f"a ref or a text is needed, not a {type(x).__name__}")


def _id_list(ids: Any) -> List[Any]:
    if isinstance(ids, (list, tuple)):
        return [_scalar(x) for x in ids if x is not None]
    if ids is None:
        return []
    return [_scalar(ids)]


def _newest(refs: Sequence[int]) -> List[int]:
    return list(reversed(refs))


def _limit(n: Any) -> Optional[int]:
    if n is None:
        return None
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise TypeError("a limit is a whole number >= 0")
    return n


# ----------------------------------------------------------------------------------------------- general helpers

def user_typed(ctx: Any, value: Any) -> bool:
    """The value appears in a user message (whole token; order ids with and without '#'; ZIP+4; six date forms)."""
    v = _view(ctx)
    return any(text_has_value(v.norm(r), value) for r in v.user_refs())


def agent_wrote(ctx: Any, value: Any) -> bool:
    """The value appears in an agent text message."""
    v = _view(ctx)
    return any(text_has_value(v.norm(r), value) for r in v.agent_refs())


def tool_output_has(ctx: Any, value: Any) -> bool:
    """The value appears in a worked tool output (not calculate, not think)."""
    v = _view(ctx)
    return any(text_has_value(v.norm(r), value) for r in v.data_tool_refs())


def obtained(ctx: Any, value: Any) -> bool:
    """The value is in the user's words or in a worked tool output (not the call's arguments, not the agent's
    words)."""
    return user_typed(ctx, value) or tool_output_has(ctx, value)


def user_messages(ctx: Any, n: Any = None) -> List[int]:
    """The user messages, newest first (the n newest when n is given)."""
    refs = _newest(_view(ctx).user_refs())
    n = _limit(n)
    return refs if n is None else refs[:n]


def agent_messages(ctx: Any, n: Any = None) -> List[int]:
    """The agent text messages, newest first (the n newest when n is given)."""
    refs = _newest(_view(ctx).agent_refs())
    n = _limit(n)
    return refs if n is None else refs[:n]


def messages_naming(ctx: Any, ids: Any, role: str = "agent", limit: Any = None, shown: bool = False) -> List[int]:
    """The messages of `role` ("agent", "user", "tool", "any") that hold one of `ids` (section 2 forms; with
    shown=True, also its shown forms), newest first, at most `limit`."""
    if role not in ("agent", "user", "tool", "any"):
        raise ValueError(f"role must be agent, user, tool or any, not {role!r}")
    v = _view(ctx)
    vals = _id_list(ids)
    limit = _limit(limit)
    forms = [f for x in vals for f in (shown_forms(ctx, x) if shown else ())]
    out = []
    for r in _newest(v.refs(role)):
        nt = v.norm(r)
        if any(text_has_value(nt, x) for x in vals) or any(has_form(nt, f) for f in forms):
            out.append(r)
            if limit is not None and len(out) >= limit:
                break
    return out


def reply_after(ctx: Any, ref: Any) -> Optional[int]:
    """The first user message after `ref` (before the call), or None."""
    v = _view(ctx)
    if isinstance(ref, bool) or not isinstance(ref, int):
        raise TypeError("reply_after needs a message ref")
    return next((r for r in v.user_refs() if r > ref), None)


_NO_START = re.compile(r"^[\s\"'(\[\-.,!]*(?:no|nope|nah|nay|not yet|not now|not right now|wait|hold on|hold off|"
                       r"stop|don'?t|do not|never mind|nevermind|cancel that|scratch that)\b")
_NO_EXCEPT = re.compile(r"^[\s\"'(\[\-.,!]*(?:no (?:problem|worries|worry|doubt|issue|issues|rush|hurry|need to wait)\b|"
                        r"no,? (?:other|more|additional|further|extra|else)\b|"
                        r"no,? (?:that'?s|that is|this is|it'?s) (?:all|it|everything|correct|right|fine|good)\b|"
                        r"no,? (?:nothing|none) (?:else|more|other)\b|no,? just (?:that|this|those|these|the)\b)")
_YES = re.compile(r"\b(?:yes|yeah|yea|yep|yup|ya|sure|ok|okay|k|confirm\w*|proceed\w*|go ahead|go for it|"
                  r"please do|sounds good|sounds great|that works|that'?s fine|that is fine|alright|all right|"
                  r"absolutely|definitely|of course|perfect)\b")


def is_strict_no(norm_text: str) -> bool:
    """Strict no on a normalized text (p7.md): starts with no / not yet / wait / don't ..., holds no yes-word."""
    if not norm_text or _NO_EXCEPT.match(norm_text):
        return False
    return bool(_NO_START.match(norm_text)) and not _YES.search(norm_text)


def reply_is_no(ctx: Any, x: Any) -> bool:
    """Strict no: x (a ref or a text) starts with no / nope / not yet / wait / don't / do not / hold on / stop, and
    holds no yes-word."""
    return is_strict_no(_ref_or_text_norm(ctx, x))


def no_after(ctx: Any, ref: Any) -> bool:
    """`ref` or a later user message before the call is a strict no."""
    v = _view(ctx)
    if isinstance(ref, bool) or not isinstance(ref, int):
        raise TypeError("no_after needs a message ref")
    return any(is_strict_no(v.norm(r)) for r in v.user_refs() if r >= ref)


# --- payment methods

_KIND_WORDS = {"paypal": ("paypal", "pay pal"), "gift_card": ("gift card", "giftcard", "gift-card", "e-gift card"),
               "credit_card": ("credit card", "creditcard", "credit-card"), "certificate": ("certificate",
                                                                                            "travel certificate")}
_BRAND_WORDS = {"visa": ("visa",), "mastercard": ("mastercard", "master card", "master-card"),
                "amex": ("amex", "american express"), "american express": ("amex", "american express"),
                "discover": ("discover card", "discover")}


def _method_kind(m: dict) -> str:
    src = m.get("source")
    if isinstance(src, str) and src:
        return src
    mid = str(m.get("id", ""))
    return re.sub(r"_\d+$", "", mid)


def exact_payment_forms(m: dict) -> List[str]:
    """Exact forms of a payment method: the id, the number in the id and its last four digits, a card's
    last_four."""
    mid = normalize(m.get("id", ""))
    forms = [mid] if mid else []
    num = re.search(r"(\d+)$", mid)
    if num:
        forms += [num.group(1), num.group(1)[-4:]]
    lf = m.get("last_four")
    if lf:
        forms.append(normalize(lf))
    return list(dict.fromkeys(f for f in forms if f))


def _unique_word_forms(methods: Dict[str, dict]) -> Dict[str, List[str]]:
    """method id -> kind / brand words that name it alone (the user has only one method of that kind / brand)."""
    by_kind: Dict[str, List[str]] = {}
    by_brand: Dict[str, List[str]] = {}
    for mid, m in methods.items():
        by_kind.setdefault(_method_kind(m), []).append(mid)
        b = str(m.get("brand") or "").lower()
        if b:
            by_brand.setdefault(b, []).append(mid)
    out: Dict[str, List[str]] = {mid: [] for mid in methods}
    for k, mids in by_kind.items():
        if len(mids) == 1:
            out[mids[0]] += list(_KIND_WORDS.get(k, (k.replace("_", " "),)))
    for b, mids in by_brand.items():
        if len(mids) == 1:
            out[mids[0]] += list(_BRAND_WORDS.get(b, (b,)))
    by_amount: Dict[str, List[str]] = {}                 # a gift card / certificate named by its balance ("$280")
    for mid, m in methods.items():
        for k in ("balance", "amount"):
            a = _amount_text(m.get(k))
            if a is not None:
                by_amount.setdefault(a, []).append(mid)
    for a, mids in by_amount.items():
        if len(set(mids)) == 1:
            out[mids[0]].append("$" + a)
    cards = [mid for mid, m in methods.items() if _method_kind(m) in ("credit_card", "gift_card")]
    if len(cards) == 1:                                  # "my card", "the card on file": the only card
        out[cards[0]] += ["card on file", "my card", "the card", "same card", "that card"]
    return out


def _amount_text(x: Any) -> Optional[str]:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    f = round(float(x), 2)
    return f"{f:.2f}".rstrip("0").rstrip(".")


# a mention right after one of these words is a negative one ("not the Mastercard", "instead of PayPal")
_NEG_BEFORE = re.compile(r"\b(?:not|no|never|instead of|rather than|except|other than|but not|without|avoid|"
                         r"don'?t (?:use|charge|want|have)|do not (?:use|charge|want|have)|"
                         r"doesn'?t have|does not have|didn'?t have|did not have|haven'?t got|no longer have)"
                         r"\s+(?:[a-z0-9'$.-]+\s+){0,3}$")
# "I don't have a gift card or credit card": a mention joined by "or" / "nor" to a negative mention is negative too
_NEG_JOIN = re.compile(r"^\s*,?\s*(?:or|nor)\s+(?:(?:a|an|the|my|any|your)\s+)?$")


def _mention_spans(norm_text: str, forms: Iterable[str]) -> List[Tuple[int, int]]:
    return [sp for f in forms for sp in form_spans(norm_text, f)]


def _exact_forms_in_context(mid: str, m: dict, methods: Dict[str, dict]) -> List[str]:
    """exact_payment_forms of one method among the user's methods. A 4-digit number that is a card's last_four
    names that card only (RC11 m3): the last four digits of another method's id number are left out when they equal
    a last_four of one of the user's methods (a number the user gives is matched to the card's last_four first)."""
    forms = exact_payment_forms(dict(m, id=m.get("id", mid)))
    own_lf = normalize(m.get("last_four") or "")
    lfs = {normalize(x.get("last_four")) for x in methods.values() if x.get("last_four")}
    mnum = re.search(r"(\d+)$", normalize(m.get("id", mid)))
    tail = mnum.group(1)[-4:] if mnum else None
    if tail and tail != own_lf and tail in lfs and tail != mnum.group(1):
        forms = [f for f in forms if f != tail]
    return forms


def _methods_mentioned(norm_text: str, methods: Dict[str, dict]) -> Tuple[set, set, set]:
    """(methods named positively by an exact form, ... by a unique kind / brand / balance word, methods named only
    in a negative way such as "not the Mastercard", "I don't have a gift card or credit card")."""
    exact, loose, negated = set(), set(), set()
    words = _unique_word_forms(methods)
    spans: List[Tuple[int, int, str, str]] = []                  # (start, end, method id, "ex" | "lo")
    for mid, m in methods.items():
        spans += [(s, e, mid, "ex") for s, e in _mention_spans(norm_text, _exact_forms_in_context(mid, m, methods))]
        spans += [(s, e, mid, "lo") for s, e in _mention_spans(norm_text, words.get(mid, []))]
    spans.sort()
    neg = [bool(_NEG_BEFORE.search(norm_text[max(0, s - 30):s])) for s, _, _, _ in spans]
    changed = True
    while changed:                                               # "not X or Y": Y is negative too
        changed = False
        for i, (s, _, _, _) in enumerate(spans):
            if neg[i]:
                continue
            if any(neg[j] and spans[j][1] <= s and _NEG_JOIN.match(norm_text[spans[j][1]:s])
                   for j in range(len(spans))):
                neg[i] = changed = True
    mentioned: set = set()
    for (s, e, mid, kind), n in zip(spans, neg):
        mentioned.add(mid)
        if not n:
            (exact if kind == "ex" else loose).add(mid)
    negated = {mid for mid in mentioned if mid not in exact and mid not in loose}
    return exact, loose, negated


def _methods_named(norm_text: str, methods: Dict[str, dict]) -> Tuple[set, set]:
    """(methods named positively by an exact form, methods named positively by a unique kind / brand / balance
    word). A method named only in a negative way ("not the Mastercard") is not named."""
    exact, loose, _ = _methods_mentioned(norm_text, methods)
    return exact, loose


_NEGATION = re.compile(r"\b(?:not|no|don'?t|do not|never|instead of|except|other than|rather than|without|"
                       r"neither|nor|isn'?t|aren'?t|won'?t|can'?t|cannot|shouldn'?t|wouldn'?t|but not|avoid)\b")
_NEG_AFTER = re.compile(r"^\W{0,3}(?:is not|isn'?t|was not|wasn'?t|no longer|not that one|is wrong|no\b)")


def _negated_near(norm_text: str, forms: Iterable[str], before: int = 40) -> bool:
    """A negation word in the 40 characters before a match, or a match followed by "is not", "isn't", "no" ..."""
    for f in forms:
        for s, e in form_spans(norm_text, f):
            if _NEGATION.search(norm_text[max(0, s - before):s]) or _NEG_AFTER.search(norm_text[e:e + 25]):
                return True
    return False


def _user_methods(ctx: Any, user_id: Any) -> Dict[str, dict]:
    u = _must(_db(ctx, "user", user_id), f"user {user_id!r}")
    pms = u["payment_methods"]
    return {mid: dict(m, id=m.get("id", mid)) for mid, m in pms.items()}


def payment_named_exactly(ctx: Any, method_id: Any, user_id: Any) -> bool:
    """P = the user's latest message that names one of user_id's methods (exact form, or a kind / brand word or
    balance that fits only one method), positively or negatively. True when P names method_id by an exact form,
    names no other method positively ("not the Mastercard" is not a choice of it), and no negation word is near the
    match."""
    v = _view(ctx)
    methods = _user_methods(ctx, user_id)
    for r in _newest(v.user_refs()):
        nt = v.norm(r)
        exact, loose, negated = _methods_mentioned(nt, methods)
        named = exact | loose
        if not named and not negated:
            continue
        if method_id not in exact or named - {method_id}:
            return False
        return not _negated_near(nt, _exact_forms_in_context(method_id, methods[method_id], methods))
    return False


def payment_confirm_pairs(ctx: Any, method_id: Any, user_id: Any, key_ids: Any = None,
                          limit: Any = LISTING_LIMIT) -> List[List[int]]:
    """[[L, r]], newest first, at most `limit`: L an agent text message (naming one of key_ids when given), r =
    reply_after(L); L or r names method_id by a shown form (exact form, or a kind / brand word or balance that fits
    only one method of the user); no strict no from r to the call; no user message from r on names another method of
    the user."""
    v = _view(ctx)
    methods = _user_methods(ctx, user_id)
    keys = _id_list(key_ids)
    limit = _limit(limit)
    out: List[List[int]] = []
    for L in _newest(v.agent_refs()):
        nt = v.norm(L)
        if keys and not any(text_has_value(nt, k) for k in keys):
            continue
        r = reply_after(ctx, L)
        if r is None or no_after(ctx, r):
            continue
        exact, loose = _methods_named(nt, methods)
        ex_r, lo_r = _methods_named(v.norm(r), methods)
        if method_id not in exact | loose | ex_r | lo_r:
            continue
        other = False
        for u in v.user_refs():
            if u >= r:
                ex, lo = _methods_named(v.norm(u), methods)
                if (ex | lo) - {method_id}:
                    other = True
                    break
        if other:
            continue
        out.append([L, r])
        if limit is not None and len(out) >= limit:
            break
    return out


def shown_forms(ctx: Any, value: Any) -> List[str]:
    """The normalized forms that name a value (p7_api.md section 3)."""
    value = _scalar(value)
    if value is None or isinstance(value, bool):
        return []
    forms = list(value_forms(value))
    sval = str(value)
    st = _state(ctx)
    dom = _domain(ctx)
    if st is not None and isinstance(value, str):
        pm = st.db_get("payment_method", sval)
        if pm is not None:
            owner = st.db_get("user", pm.get("user_id"))
            methods = {mid: dict(m, id=m.get("id", mid)) for mid, m in (owner or {}).get("payment_methods", {}).items()}
            forms += exact_payment_forms(dict(pm, id=pm.get("id", sval)))
            forms += _unique_word_forms(methods).get(sval, []) if methods else []
            if pm.get("brand") and pm.get("last_four"):
                forms.append(normalize(f"{pm['brand']} {pm['last_four']}"))
        elif dom == "retail" and re.fullmatch(r"\d{10}", sval):
            var = st.db_get("variant", sval)
            if var is not None:
                prod = st.db_get("product", var.get("product_id"))
                if prod is not None:
                    forms.append(normalize(prod.get("name", "")))
                forms += [normalize(x) for x in (var.get("options") or {}).values()]
    if isinstance(value, str) and "_" in value and not re.search(r"\d", value):
        forms.append(normalize(value.replace("_", " ")))          # cabin: basic_economy -> basic economy
    return list(dict.fromkeys(f for f in forms if f))


def call_key_ids(ctx: Any) -> List[Any]:
    """The key ids of the pending call (retail order tools: the order id; modify_user_address: the new zip and
    address1; airline reservation tools: the reservation id; book_reservation: the flight numbers)."""
    tool = _tool(ctx)
    if tool in RETAIL_ORDER_TOOLS:
        return [ctx.arg("order_id")]
    if tool == "modify_user_address":
        return [ctx.arg("zip"), ctx.arg("address1")]
    if tool in AIRLINE_RES_TOOLS:
        return [ctx.arg("reservation_id")]
    if tool == "book_reservation":
        fl = ctx.arg("flights")
        if not isinstance(fl, list):
            raise TypeError("flights is not a list")
        return [f.get("flight_number") for f in fl if isinstance(f, dict) and f.get("flight_number")]
    return []


def call_details(ctx: Any) -> List[Any]:
    """Every value that names the pending retail write in a listing: the key ids (call_key_ids), the item ids and
    new item ids, the product names of those items, the payment method's shown forms, the reason, the new address
    line and zip. (An agent's listing often names the items and the payment but not the order id again.)"""
    out: List[Any] = list(call_key_ids(ctx))
    args = _view(ctx).pending_args
    st = _state(ctx)
    for k in ("item_ids", "new_item_ids"):
        for iid in args.get(k) or []:
            if isinstance(iid, str):
                out.append(iid)
                var = st.db_get("variant", iid) if st is not None else None
                prod = st.db_get("product", var.get("product_id")) if var is not None else None
                if prod is not None and prod.get("name"):
                    out.append(prod["name"])
    pid = args.get("payment_method_id")
    if isinstance(pid, str):
        out += shown_forms(ctx, pid)
    for k in ("reason", "address1", "zip"):
        if isinstance(args.get(k), str) and args[k]:
            out.append(args[k])
    return list(dict.fromkeys(x for x in out if x not in (None, "")))


def pending_reply(ctx: Any) -> List[int]:
    """[view.pending_ref] when the pending call is a reply, else []."""
    v = _view(ctx)
    return [v.pending_ref] if v.pending_tool == "respond" else []


def me(ctx: Any) -> Optional[str]:
    """The logged-in user. retail: the user id returned by the FIRST worked find_user_id_by_* call (a later login
    never switches it); airline: the first user id typed by the user that exists in the database. Never the call's
    own arguments."""
    dom = _domain(ctx)
    st = _state(ctx)
    if dom == "retail":
        if st is not None and hasattr(st, "events_where"):
            evs = st.events_where(tool=list(FIND_TOOLS), ok=True)
            for e in evs:
                out = e.get("output")
                if isinstance(out, str) and out.strip():
                    return out.strip()
            return None
        v = _view(ctx)
        for r in v.tool_refs():
            e = v.entries[r]
            if e.tool in FIND_TOOLS and e.ok and e.text.strip():
                return e.text.strip()
        return None
    v = _view(ctx)
    for r in v.user_refs():
        for uid in _UID.findall(v.norm(r)):
            if st is None or st.db_get("user", uid) is not None:
                return uid
    return None


def _ref_hit(ctx: Any, name: str, x: Any) -> bool:
    if isinstance(x, int) and not isinstance(x, bool):
        v = _view(ctx)
        return _screen_hit(name, v.norm(x), v.plain(x))
    if isinstance(x, str):
        return screen_text(name, x)
    raise TypeError(f"a ref or a text is needed, not a {type(x).__name__}")


def screen(ctx: Any, name: str, x: Any) -> bool:
    """The word list `name` hits x (a ref or a text)."""
    return _ref_hit(ctx, name, x)


def screened_user_messages(ctx: Any, name: str) -> List[int]:
    """The user messages that hit screen `name`, newest first."""
    v = _view(ctx)
    _screen_re(name)
    return [r for r in _newest(v.user_refs()) if _ref_hit(ctx, name, r)]


def screen_reply(ctx: Any, name: str) -> bool:
    """The pending reply hits screen `name` (false when the pending call is not a reply)."""
    v = _view(ctx)
    if v.pending_tool != "respond":
        return False
    return _ref_hit(ctx, name, v.pending_ref)


# ----------------------------------------------------------------------------------------------- retail helpers

def reminder_candidates(ctx: Any, order_id: Any) -> List[int]:
    """The agent text messages at or after the first message (user, agent or tool output) that holds the order id,
    each followed by a user message before the call; newest first."""
    v = _view(ctx)
    first = next((e.ref for e in v.entries if text_has_value(e.norm, order_id)), None)
    if first is None:
        return []
    users = v.user_refs()
    last_user = users[-1] if users else -1
    return [r for r in _newest(v.agent_refs()) if r >= first and r < last_user]


def listing_candidates(ctx: Any, ids: Any, limit: Any = LISTING_LIMIT) -> List[int]:
    """The agent text messages that name one of `ids` (order ids with or without '#'), newest first, at most
    `limit`."""
    return messages_naming(ctx, ids, "agent", limit)


def confirm_pairs(ctx: Any, ids: Any, limit: Any = LISTING_LIMIT) -> List[List[int]]:
    """[[L, r]], newest first, at most `limit`: L an agent text message naming one of `ids`; r = reply_after(L)
    exists; r is not a strict no and no later user message before the call is one."""
    limit = _limit(limit)
    out: List[List[int]] = []
    for L in messages_naming(ctx, ids, "agent"):
        r = reply_after(ctx, L)
        if r is None or no_after(ctx, r):
            continue
        out.append([L, r])
        if limit is not None and len(out) >= limit:
            break
    return out


def another_user_pick(ctx: Any) -> List[int]:
    """K4's message (retail request_is_for_another_user part b): for find_user_id_by_* while me() is None, the
    newest user message holding one of the call's identity values; for get_product_details / list_all_product_types,
    the latest user message when it hits 'other_person'; else []."""
    v = _view(ctx)
    tool = _tool(ctx)
    if tool in FIND_TOOLS:
        if me(ctx) is not None:
            return []
        vals = ([ctx.arg("email")] if tool == "find_user_id_by_email"
                else [ctx.arg("first_name"), ctx.arg("last_name"), ctx.arg("zip")])
        for r in _newest(v.user_refs()):
            if any(text_has_value(v.norm(r), x) for x in vals if x is not None):
                return [r]
        return []
    if tool in CATALOG_TOOLS_RETAIL:
        us = _newest(v.user_refs())
        if us and _ref_hit(ctx, "other_person", us[0]):
            return [us[0]]
    return []


def other_person_screen(ctx: Any) -> bool:
    """K5's screen: the pending reply, or the latest user message before it, hits 'other_person'. Removed after
    blind set 3 (K5 missed 2 positives): always true, so K5 is asked on every reply where part a is false."""
    v = _view(ctx)
    if K5_SCREEN_REMOVED:                            # K5's screen removed after blind set 3: K5 is asked always
        return True
    if v.pending_tool == "respond" and _ref_hit(ctx, "other_person", v.pending_ref):
        return True
    us = v.user_refs()
    return bool(us) and _ref_hit(ctx, "other_person", us[-1])


def reply_holds_other_user_data(ctx: Any) -> bool:
    """The pending reply holds a database value of a user other than me() (info classes) that no user message
    holds; false while me() is None or the pending call is not a reply."""
    from state_tracker.v3 import info_classes as IC
    v = _view(ctx)
    if v.pending_tool != "respond":
        return False
    who = me(ctx)
    if who is None:
        return False
    found = IC.user_data_values(v.pending_text, v, _state(ctx), owner_ok=(who,))
    if found:
        ctx.note({"other_user_values": [{"kind": x["kind"]} for x in found]})
    return bool(found)


def reply_discloses_user_data(ctx: Any) -> bool:
    """The pending reply holds an id-like value or an amount that the info classes mark as a database field of a
    user (profile, orders, payment methods), that no user message holds, and that a worked data tool output of this
    conversation showed (the agent can only disclose data it read; RC11 M1: an example ZIP in the first reply, before
    any tool call, is not a disclosure)."""
    from state_tracker.v3 import info_classes as IC
    v = _view(ctx)
    if v.pending_tool != "respond":
        return False
    found = IC.user_data_values(v.pending_text, v, _state(ctx), seen_only=True)
    if found:
        ctx.note({"disclosed_kinds": sorted({x["kind"] for x in found})})
    return bool(found)


def data_output_exists(ctx: Any) -> bool:
    """A worked tool call other than calculate / think ran before the check."""
    return bool(_view(ctx).data_tool_refs())


# ----------------------------------------------------------------------------------------------- airline helpers

_UID = re.compile(r"(?<![a-z0-9_])[a-z]+(?:_[a-z]+)*_\d{3,}(?![a-z0-9_])")
_RES6 = re.compile(r"(?<![a-z0-9_])[a-z0-9]{6}(?![a-z0-9_])")
_INITIAL: Dict[str, dict] = {}


def _initial_db(domain: str) -> dict:
    """τ-bench's data at the start of a conversation (one copy per process, never changed)."""
    if domain not in _INITIAL:
        from state_tracker.state import load_db
        _INITIAL[domain] = load_db(domain)
    return _INITIAL[domain]


def obtained_user_ids(ctx: Any) -> List[str]:
    """The user ids (in the database) that appear in a user message or a worked tool output, in order of first
    appearance."""
    v = _view(ctx)
    out: List[str] = []
    for e in v.entries:
        if e.role == "user" or (e.role == "tool" and e.ok and e.tool not in NO_DATA_TOOLS):
            for uid in _UID.findall(e.norm):
                if uid not in out and _db(ctx, "user", uid) is not None:
                    out.append(uid)
    return out


def _worked(v: MessageView, tools: Iterable[str]) -> List[Entry]:
    names = set(tools)
    return [v.entries[r] for r in v.tool_refs() if v.entries[r].ok and v.entries[r].tool in names]


def _named_reservation_ids(ctx: Any) -> List[str]:
    v = _view(ctx)
    out: List[str] = []
    for e in v.entries:
        cand: List[str] = []
        if e.role == "user":
            cand = [t.upper() for t in _RES6.findall(e.norm)]
        elif e.role == "tool" and e.ok:
            if e.tool in AIRLINE_RES_TOOLS:
                rid = e.args.get("reservation_id")
                cand = [rid] if isinstance(rid, str) else []
            elif e.tool == "book_reservation":
                try:
                    rid = json.loads(e.text).get("reservation_id")
                except (TypeError, ValueError, AttributeError):
                    rid = None
                cand = [rid] if isinstance(rid, str) else []
        for rid in cand:
            if rid not in out and _db(ctx, "reservation", rid) is not None:
                out.append(rid)
    return out


def named_reservations(ctx: Any, user_ids: Any) -> List[str]:
    """Reservations of these users named in the conversation: typed by the user, the id argument of a worked
    get_reservation_details / update_reservation_* / cancel_reservation, or created by a worked book_reservation."""
    users = set(_id_list(user_ids))
    out = []
    for rid in _named_reservation_ids(ctx):
        res = _db(ctx, "reservation", rid)
        if res is not None and res["user_id"] in users:
            out.append(rid)
    return out


def _flight_sets(ctx: Any, rid: str, res: dict, current: bool) -> List[list]:
    sets = [res["flights"]]
    if current:
        return sets
    init = _initial_db(_domain(ctx) or "airline").get("reservations", {}).get(rid)
    if init is not None:
        sets.append(init["flights"])
    v = _view(ctx)
    for e in _worked(v, ("update_reservation_flights", "book_reservation")):
        if e.tool == "update_reservation_flights" and e.args.get("reservation_id") != rid:
            continue
        if e.tool == "book_reservation":
            try:
                if json.loads(e.text).get("reservation_id") != rid:
                    continue
            except (TypeError, ValueError, AttributeError):
                continue
        fl = e.args.get("flights")
        if isinstance(fl, list):
            sets.append([f for f in fl if isinstance(f, dict)])
    return sets


def _status_list(statuses: Any) -> List[str]:
    if isinstance(statuses, str):
        return [statuses]
    if isinstance(statuses, (list, tuple)) and all(isinstance(s, str) for s in statuses):
        return list(statuses)
    raise TypeError("statuses must be a text or a list of texts")


def had_flight_status(ctx: Any, res_ids: Any, statuses: Any, current: bool = False) -> List[str]:
    """The reservations with a flight whose status (flights table) is in `statuses` on its date: the flights at the
    start of the conversation or after any worked update_reservation_flights (current=True: the flights at the
    check only)."""
    want = set(_status_list(statuses))
    out = []
    for rid in _id_list(res_ids):
        res = _db(ctx, "reservation", rid)
        if res is None:
            continue
        hit = False
        for fl in _flight_sets(ctx, rid, res, bool(current)):
            for f in fl:
                fn, date = f.get("flight_number"), f.get("date")
                flight = _db(ctx, "flight", fn)
                if flight is None or not isinstance(date, str):
                    continue
                if (flight["dates"].get(date) or {}).get("status") in want:
                    hit = True
                    break
            if hit:
                break
        if hit:
            out.append(rid)
    return out


def _cabin(ctx: Any, rid: str, res: dict) -> Any:
    ups = [e for e in _worked(_view(ctx), ("update_reservation_flights",)) if e.args.get("reservation_id") == rid]
    if ups and ups[-1].args.get("cabin"):
        return ups[-1].args.get("cabin")
    return res["cabin"]


def eligible_for_compensation(ctx: Any, res_ids: Any, members: Any) -> List[str]:
    """Those whose owner's membership is in `members` (the expression names the levels, from the policy), or with
    insurance 'yes', or with cabin business (the cabin of the newest worked update_reservation_flights on it, else
    the database)."""
    levels = set(_status_list(members))
    out = []
    for rid in _id_list(res_ids):
        res = _db(ctx, "reservation", rid)
        if res is None:
            continue
        owner = _db(ctx, "user", res["user_id"])
        member = owner["membership"] if owner is not None else None
        if member in levels or res["insurance"] == "yes" or _cabin(ctx, rid, res) == "business":
            out.append(rid)
    return out


def changed_or_cancelled(ctx: Any, res_ids: Any) -> List[str]:
    """Those with a worked update_reservation_* or cancel_reservation call before the check."""
    ids = _id_list(res_ids)
    done = {e.args.get("reservation_id") for e in _worked(_view(ctx), AIRLINE_CHANGE_TOOLS)}
    return [r for r in ids if r in done]


def n_passengers(ctx: Any, res_id: Any) -> int:
    """The passengers of the reservation in the database at the check."""
    res = _must(_db(ctx, "reservation", res_id), f"reservation {res_id!r}")
    return len(res["passengers"])


def _number(x: Any) -> float:
    if isinstance(x, bool):
        raise TypeError("an amount is a number")
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        try:
            return float(x.strip().lstrip("$").replace(",", ""))
        except ValueError:
            raise TypeError(f"the amount {x!r} is not a number") from None
    raise TypeError(f"the amount is a {type(x).__name__}, not a number")


def amount_fits(ctx: Any, res_ids: Any, amount: Any, rate: Any) -> bool:
    """amount == rate x the passengers of one of the reservations."""
    a, k = _number(amount), _number(rate)
    for rid in _id_list(res_ids):
        res = _db(ctx, "reservation", rid)
        if res is not None and abs(a - k * len(res["passengers"])) < 1e-9:
            return True
    return False


def compensation_users(ctx: Any) -> List[Any]:
    """send_certificate: the call's user_id; a reply: obtained_user_ids()."""
    if _tool(ctx) == "send_certificate":
        return [ctx.arg("user_id")]
    return obtained_user_ids(ctx)


def prohibited_case(ctx: Any, user_id: Any) -> bool:
    """S46 part b: the user's relevant reservations (named; only those with a cancelled or delayed flight when some
    have one) are at least one, and none has insurance 'yes' or business cabin."""
    rel = named_reservations(ctx, [user_id])
    hit = had_flight_status(ctx, rel, ["cancelled", "delayed"])
    if hit:
        rel = hit
    if not rel:
        return False
    for rid in rel:
        res = _db(ctx, "reservation", rid)
        if res["insurance"] == "yes" or _cabin(ctx, rid, res) == "business":
            return False
    return True


_AIRPORTS: Dict[str, Dict[str, str]] = {}


def _airports(ctx: Any) -> Dict[str, str]:
    if "airline" not in _AIRPORTS:
        from state_tracker.state import run_tool
        _AIRPORTS["airline"] = json.loads(run_tool("airline", {}, "list_all_airports", {}))
    return _AIRPORTS["airline"]


def _names_airport(ctx: Any, ref: int, code: Any) -> bool:
    if not isinstance(code, str) or not code.strip():
        return False
    v = _view(ctx)
    c = code.strip().upper()
    if _form_re(c, case=True).search(v.plain(ref)):
        return True
    city = _airports(ctx).get(c)
    return bool(city) and has_form(v.norm(ref), normalize(city))


def user_named_airport(ctx: Any, code: Any) -> bool:
    """A user message names the airport: its IATA code (upper case in the text) or its city (list_all_airports)."""
    return any(_names_airport(ctx, r, code) for r in _view(ctx).user_refs())


def route_user_messages(ctx: Any, origin: Any, destination: Any) -> List[int]:
    """The latest user message naming origin or destination, plus the latest naming the other when it is a
    different message (newest first, at most two)."""
    v = _view(ctx)
    us = _newest(v.user_refs())
    o = next((r for r in us if _names_airport(ctx, r, origin)), None)
    d = next((r for r in us if _names_airport(ctx, r, destination)), None)
    return sorted({r for r in (o, d) if r is not None}, reverse=True)


def route_listing_pairs(ctx: Any, origin: Any, destination: Any) -> List[List[int]]:
    """[[L, r]], newest first: agent text messages naming both airports (code or city) with a user reply after."""
    out = []
    for L in _newest(_view(ctx).agent_refs()):
        if _names_airport(ctx, L, origin) and _names_airport(ctx, L, destination):
            r = reply_after(ctx, L)
            if r is not None:
                out.append([L, r])
    return out


def insurance_pick(ctx: Any) -> List[int]:
    """[L, r]: the latest agent text naming insurance that has a user reply; or [u]: a later user message naming
    insurance (or, when no agent message names it, the latest user message that does); else []."""
    v = _view(ctx)
    users_ins = [r for r in _newest(v.user_refs()) if has_form(v.norm(r), "insurance")]
    for L in _newest(v.agent_refs()):
        if has_form(v.norm(L), "insurance"):
            r = reply_after(ctx, L)
            if r is None:
                continue
            later = [u for u in users_ins if u > r]
            return [later[0]] if later else [L, r]
    return [users_ins[0]] if users_ins else []


_NUMWORDS = {"zero": 0, "no": 0, "none": 0, "one": 1, "a": 1, "an": 1, "single": 1, "two": 2, "three": 3,
             "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_BAG_W = r"(?:bags?|baggages?|luggages?|suitcases?|checked items?)"
_BAG_BEFORE = re.compile(rf"(?<![a-z0-9])(\d+|{'|'.join(_NUMWORDS)})\s+(?:[a-z-]+\s+){{0,3}}{_BAG_W}\b")
_BAG_AFTER = re.compile(rf"\b{_BAG_W}\s*(?:[:=-]|to|of|count|total|:?\s*total)?\s*(\d+)(?![0-9])")


def _bag_counts(norm_text: str) -> set:
    out = set()
    for w in _BAG_BEFORE.findall(norm_text):
        out.add(int(w) if w.isdigit() else _NUMWORDS[w])
    for w in _BAG_AFTER.findall(norm_text):
        out.add(int(w))
    return out


def _change_details(ctx: Any) -> Dict[str, list]:
    """The details of the pending airline write that a listing may name."""
    v = _view(ctx)
    tool, args = v.pending_tool, v.pending_args
    d: Dict[str, list] = {"ids": [], "dates": [], "names": [], "words": [], "bags": [], "payments": []}
    rid = args.get("reservation_id")
    if isinstance(rid, str) and rid:
        d["ids"].append(rid)
    if tool in ("book_reservation", "update_reservation_flights"):
        for f in args.get("flights") or []:
            if isinstance(f, dict):
                if f.get("flight_number"):
                    d["ids"].append(f["flight_number"])
                if f.get("date"):
                    d["dates"].append(f["date"])
        cab = args.get("cabin")
        if isinstance(cab, str) and cab:
            d["words"].append(normalize(cab.replace("_", " ")))
    if tool in ("book_reservation", "update_reservation_passengers"):
        for p in args.get("passengers") or []:
            if isinstance(p, dict) and p.get("first_name") and p.get("last_name"):
                d["names"].append((normalize(p["first_name"]), normalize(p["last_name"])))
    if tool == "update_reservation_baggages":
        for k in ("total_baggages", "nonfree_baggages"):
            if isinstance(args.get(k), int) and not isinstance(args.get(k), bool):
                d["bags"].append(args[k])
    pays = []
    if tool == "book_reservation":
        pays = [p.get("payment_id") for p in (args.get("payment_methods") or []) if isinstance(p, dict)]
    elif args.get("payment_id"):
        pays = [args.get("payment_id")]
    owner = args.get("user_id") if tool == "book_reservation" else None
    if owner is None and isinstance(rid, str):
        res = _db(ctx, "reservation", rid)
        owner = res["user_id"] if res is not None else None
    for pid in pays:
        if not isinstance(pid, str):
            continue
        forms = [normalize(pid)]
        u = _db(ctx, "user", owner) if isinstance(owner, str) else None
        if u is not None and pid in u["payment_methods"]:
            methods = {mid: dict(m, id=m.get("id", mid)) for mid, m in u["payment_methods"].items()}
            forms += exact_payment_forms(methods[pid]) + _unique_word_forms(methods).get(pid, [])
        d["payments"].append(forms)
    return d


def _names_change_detail(nt: str, d: Dict[str, list]) -> bool:
    if any(text_has_value(nt, x) for x in d["ids"]):
        return True
    if any(text_names_date(nt, x, without_year=True) for x in d["dates"]):
        return True
    if any(has_form(nt, f) and has_form(nt, l) for f, l in d["names"]):
        return True
    if any(has_form(nt, w) for w in d["words"]):
        return True
    if d["bags"] and set(d["bags"]) & _bag_counts(nt):
        return True
    return any(has_form(nt, f) for forms in d["payments"] for f in forms)


def change_listings(ctx: Any) -> List[int]:
    """The agent text messages that name at least one detail of the pending airline write (flight numbers, dates,
    passenger names, cabin, a bag count next to 'bag', the reservation id, the payment form) and have a user reply
    after; newest first."""
    v = _view(ctx)
    d = _change_details(ctx)
    users = v.user_refs()
    last_user = users[-1] if users else -1
    return [L for L in _newest(v.agent_refs()) if L < last_user and _names_change_detail(v.norm(L), d)]


def change_listing_pairs(ctx: Any) -> List[List[int]]:
    """[[L, r]]: L from change_listings(), r = reply_after(L), no strict no from r to the call; newest first."""
    out = []
    for L in change_listings(ctx):
        r = reply_after(ctx, L)
        if r is not None and not no_after(ctx, r):
            out.append([L, r])
    return out


# ----------------------------------------------------------------------------------------------- registration

# name -> (function, min positional, max positional, keywords, source)
HELPERS: Dict[str, tuple] = {
    "user_typed": (user_typed, 1, 1, (), SOURCE),
    "agent_wrote": (agent_wrote, 1, 1, (), SOURCE),
    "tool_output_has": (tool_output_has, 1, 1, (), SOURCE),
    "obtained": (obtained, 1, 1, (), SOURCE),
    "user_messages": (user_messages, 0, 1, (), SOURCE),
    "agent_messages": (agent_messages, 0, 1, (), SOURCE),
    "messages_naming": (messages_naming, 1, 3, ("role", "limit", "shown"), SOURCE),
    "reply_after": (reply_after, 1, 1, (), SOURCE),
    "reply_is_no": (reply_is_no, 1, 1, (), SOURCE),
    "no_after": (no_after, 1, 1, (), SOURCE),
    "shown_forms": (shown_forms, 1, 1, (), SOURCE),
    "call_key_ids": (call_key_ids, 0, 0, (), SOURCE),
    "call_details": (call_details, 0, 0, (), SOURCE),
    "pending_reply": (pending_reply, 0, 0, (), SOURCE),
    "me": (me, 0, 0, (), "event"),
    "screen": (screen, 2, 2, (), SOURCE),
    "screened_user_messages": (screened_user_messages, 1, 1, (), SOURCE),
    "screen_reply": (screen_reply, 1, 1, (), SOURCE),
    "reminder_candidates": (reminder_candidates, 1, 1, (), SOURCE),
    "listing_candidates": (listing_candidates, 1, 2, ("limit",), SOURCE),
    "confirm_pairs": (confirm_pairs, 1, 2, ("limit",), SOURCE),
    "payment_named_exactly": (payment_named_exactly, 2, 2, (), SOURCE),
    "payment_confirm_pairs": (payment_confirm_pairs, 2, 4, ("key_ids", "limit"), SOURCE),
    "another_user_pick": (another_user_pick, 0, 0, (), SOURCE),
    "other_person_screen": (other_person_screen, 0, 0, (), SOURCE),
    "reply_holds_other_user_data": (reply_holds_other_user_data, 0, 0, (), SOURCE),
    "reply_discloses_user_data": (reply_discloses_user_data, 0, 0, (), SOURCE),
    "data_output_exists": (data_output_exists, 0, 0, (), SOURCE),
    "obtained_user_ids": (obtained_user_ids, 0, 0, (), SOURCE),
    "named_reservations": (named_reservations, 1, 1, (), SOURCE),
    "had_flight_status": (had_flight_status, 2, 3, ("current",), SOURCE),
    "eligible_for_compensation": (eligible_for_compensation, 2, 2, (), SOURCE),
    "changed_or_cancelled": (changed_or_cancelled, 1, 1, (), SOURCE),
    "amount_fits": (amount_fits, 3, 3, (), SOURCE),
    "n_passengers": (n_passengers, 1, 1, (), SOURCE),
    "compensation_users": (compensation_users, 0, 0, (), SOURCE),
    "prohibited_case": (prohibited_case, 1, 1, (), SOURCE),
    "user_named_airport": (user_named_airport, 1, 1, (), SOURCE),
    "route_user_messages": (route_user_messages, 2, 2, (), SOURCE),
    "route_listing_pairs": (route_listing_pairs, 2, 2, (), SOURCE),
    "insurance_pick": (insurance_pick, 0, 0, (), SOURCE),
    "change_listings": (change_listings, 0, 0, (), SOURCE),
    "change_listing_pairs": (change_listing_pairs, 0, 0, (), SOURCE),
}


def register_all() -> None:
    """Register every helper (idempotent: the same helper twice changes nothing)."""
    for name, (func, lo, hi, kws, src) in HELPERS.items():
        F.register_name(name, func, lo, hi, kws, source=src, doc=(func.__doc__ or "").strip().split("\n")[0])


register_all()
