"""Tracker v4, K1 rebuild: the go-ahead helpers (agent A2). $0: no LLM call, no network.

The main idea in plain words. Code finds the agent message that proposed the pending write (the anchor L), takes
every user message after it (B), and decides as much as it can without a model:
  - a strict "no" in B                        -> no go-ahead (no call);
  - a user message in B that clearly names another payment method, item, option value, address or passenger than
    the call                                   -> a clash (no call);
  - the newest message of B is a plain yes ("Yes.", "Please proceed.", "Yes, go ahead") -> go-ahead (no call,
    noted as fast_path);
  - otherwise one K1 question about (L, B) answers it (ask_first_yes_v4 of questions_v4, agent A3).
One answer per (L, B) serves every confirmation fact of the call (no per-fact focus in the question).

Definitions (docs/planning/tracker_v4/predicate_table.md, section 0, the authority):
  D1 writes; D2 action span S; D3 anchor L (newest agent text in S naming a key detail of the call, with a user
  message after it; at most 2, newest first); D4 B = every user message after L up to the call; D7 payment forms and
  clash; D8 fast path (whole-message match against a fixed phrase list, not a word screen); D9 strict no (v3
  `is_strict_no`, unchanged).
Ambiguity rule (DB-only form check, output/eval_v4/form_check.md P5 / P6 / R7): a mention that fits 2+ of the
user's methods (airline: several cards of one brand, several gift cards / certificates; retail mei_johansson_1199:
"4044" is one card's last four and the other card's id ending) is neither a match nor a clash, unless a brand word
next to it picks one. Option values and product names are matched as whole values ("gold" inside "rose gold" is not
"gold").

Helpers (registered on import with facts_format_v3.register_name; every name ends in _v4):
  structure: go_ahead_anchors_v4() (= A1's listing_anchors_v4), go_ahead_candidates_v4(focus=None),
             go_ahead_fast_v4(focus=None), clash_free_v4(), short_go_ahead_v4(x), insurance_candidates_v4()
The K1 question part of a fact is
    go_ahead_fast_v4() or ask_first_yes_v4('K1', go_ahead_candidates_v4(), limit=2)
so the fast path decides first and K1v4 (agent A3's helper, inputs listing / replies / action) is asked only when it
does not hold. A candidate is [L, [b1, b2, ...]] (refs of the message view): K1v4's listing and replies.
Notes (ctx.note) for the guard record: {"fast_path": True, "question": "K1", ...}, {"clash": kind, "named",
"call", "message", "text"}, {"strict_no": ref, ...}.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from state_tracker.v3 import facts_format_v3 as F
from state_tracker.v3 import message_view as MV

try:                                                # agent A1: the D3 anchors (one L for listing and go-ahead)
    from state_tracker.v4 import listing_v4 as _LV
except ImportError:                                 # pragma: no cover - only before A1's file exists
    _LV = None

SOURCE = "structure"
ANCHOR_LIMIT = 2                                    # D3: at most 2 candidates, newest first
INSURANCE_LIMIT = 4

RETAIL_WRITES = ("cancel_pending_order", "modify_pending_order_address", "modify_pending_order_items",
                 "modify_pending_order_payment", "modify_user_address", "return_delivered_order_items",
                 "exchange_delivered_order_items")
AIRLINE_WRITES = ("book_reservation", "update_reservation_flights", "update_reservation_baggages",
                  "update_reservation_passengers", "cancel_reservation", "send_certificate")
WRITE_TOOLS = frozenset(RETAIL_WRITES + AIRLINE_WRITES)
RETAIL_ITEM_TOOLS = ("modify_pending_order_items", "return_delivered_order_items", "exchange_delivered_order_items")
NEW_ITEM_TOOLS = ("modify_pending_order_items", "exchange_delivered_order_items")
ADDRESS_TOOLS = ("modify_pending_order_address", "modify_user_address")
PASSENGER_TOOLS = ("book_reservation", "update_reservation_passengers")

# ----------------------------------------------------------------------------------------------- D8 fast path

FAST_PATH_PHRASES = frozenset((
    "yes", "yes yes", "yeah", "yep", "yup", "sure", "ok", "okay", "correct", "confirm", "confirmed", "i confirm",
    "yes i confirm", "proceed", "yes proceed", "go ahead", "yes go ahead", "go ahead and proceed", "yes do it",
    "do it", "please do", "yes please do", "sounds good", "yes sounds good", "yes that is correct",
    "yes thats correct", "thats correct", "that is correct", "yes that works", "that works", "yes book it",
    "yes cancel it", "yes submit it", "yes go for it",
))
_FILLER = re.compile(r"\b(?:please|thanks|thank you|ok so)\b")
_PUNCT = re.compile(r"[^\w\s]|_")
# the caller's belt-and-braces rule (code_change_map): every phrase above already passes it
_EXCLUDED_WORDS = re.compile(r"\b(?:but|instead|change|not|wait|only)\b")
MAX_FAST_WORDS = 8


def _fast_forms(text: Any) -> List[str]:
    raw = MV.deaccent(text if isinstance(text, str) else "" if text is None else str(text)).lower()
    raw = raw.replace("'", "").replace("’", "")
    no_punct = re.sub(r"\s+", " ", _PUNCT.sub(" ", raw)).strip()
    no_fill = re.sub(r"\s+", " ", _FILLER.sub(" ", no_punct)).strip()
    return [no_punct, no_fill]


def is_short_go_ahead_v4(text: Any) -> bool:
    """D8: the whole message, lower-cased, punctuation removed, "please" / "thanks" / "thank you" / "ok so" removed,
    is one of FAST_PATH_PHRASES. A '?' anywhere, more than 8 words, or but / instead / change / not / wait / only
    never pass. Pure: no LLM call."""
    if not isinstance(text, str) or not text.strip() or "?" in text:
        return False
    forms = _fast_forms(text)
    if len(forms[0].split()) > MAX_FAST_WORDS or _EXCLUDED_WORDS.search(forms[0]):
        return False
    return any(f in FAST_PATH_PHRASES for f in forms if f)


def short_go_ahead_v4(ctx: Any, x: Any) -> bool:
    """short_go_ahead_v4(x): x (a message ref or a text) is a plain yes by D8 (no LLM call)."""
    if isinstance(x, bool):
        raise TypeError("a ref or a text is needed")
    if isinstance(x, int):
        return is_short_go_ahead_v4(MV._view(ctx).text(x))
    if isinstance(x, str):
        return is_short_go_ahead_v4(x)
    raise TypeError(f"a ref or a text is needed, not a {type(x).__name__}")


# ----------------------------------------------------------------------------------------------- D2 / D3 / D4

def _args(ctx: Any) -> Dict[str, Any]:
    a = getattr(ctx, "args", None)
    if isinstance(a, dict) and a:
        return a
    return dict(MV._view(ctx).pending_args or {})


def span_start_v4(ctx: Any) -> int:
    """D2: the ref of the newest worked write before the call that has a user message after it (-1: none, S is the
    whole conversation). S = the messages with a ref above it. A write with no user message after it (a batch
    member) is skipped, so it shares the S of the write before it."""
    v = MV._view(ctx)
    users = v.user_refs()
    last_user = users[-1] if users else -1
    for r in reversed(v.tool_refs()):
        e = v.entries[r]
        if e.ok and e.tool in WRITE_TOOLS and last_user > r:
            return r
    return -1


def _retail_key_values(ctx: Any) -> List[Any]:
    """D3 retail key details: order id, item ids and their product names, address1 / zip, the payment method's
    shown forms (v3 call_details without the cancel reason)."""
    reason = _args(ctx).get("reason")
    return [x for x in MV.call_details(ctx) if not (isinstance(reason, str) and x == reason)]


def _names_key_detail(ctx: Any) -> Callable[[str], bool]:
    tool = MV._tool(ctx)
    if tool in RETAIL_WRITES or tool in MV.RETAIL_ORDER_TOOLS:
        vals = _retail_key_values(ctx)
        return lambda nt: any(MV.text_has_value(nt, x) for x in vals)
    d = MV._change_details(ctx)
    return lambda nt: MV._names_change_detail(nt, d)


def go_ahead_anchors_v4(ctx: Any) -> List[int]:
    """D3: the agent text messages in the action span S that name a key detail of the pending call and have a user
    message after them (before the call); newest first, at most 2. The same anchors as agent A1's
    listing_anchors_v4 (one L for the listing lines and the go-ahead); own copy only when listing_v4 is missing."""
    if _LV is not None:
        return list(_LV.listing_anchors_v4(ctx))
    return own_anchors_v4(ctx)


def own_anchors_v4(ctx: Any) -> List[int]:
    """D3 written here (the fallback of go_ahead_anchors_v4; a test checks it agrees with listing_v4)."""
    v = MV._view(ctx)
    s = span_start_v4(ctx)
    users = v.user_refs()
    last_user = users[-1] if users else -1
    names = _names_key_detail(ctx)
    out: List[int] = []
    for L in reversed(v.agent_refs()):
        if L <= s:
            break
        if L < last_user and names(v.norm(L)):
            out.append(L)
            if len(out) >= ANCHOR_LIMIT:
                break
    return out


def b_messages_v4(ctx: Any, L: int) -> List[int]:
    """D4: every user message after L up to the call, oldest first."""
    return [r for r in MV._view(ctx).user_refs() if r > L]


# ----------------------------------------------------------------------------------------------- D7 payment forms

_ORIGINAL = re.compile(r"\b(?:original (?:payment method|payment|method|card|form of payment|account)|"
                       r"(?:card|method|account) i (?:originally )?(?:paid|used|bought it|ordered|booked)|"
                       r"same (?:card|method|payment method|payment) as (?:before|the order|my order|the booking|"
                       r"the purchase|the reservation|i used)|way i (?:originally )?paid)\b")


def _owner_id(ctx: Any) -> Optional[str]:
    tool, args = MV._tool(ctx), _args(ctx)
    if tool in ("modify_user_address", "book_reservation", "send_certificate"):
        uid = args.get("user_id")
        return uid if isinstance(uid, str) else None
    oid = args.get("order_id")
    if isinstance(oid, str):
        o = MV._db(ctx, "order", oid)
        return o.get("user_id") if o else None
    rid = args.get("reservation_id")
    if isinstance(rid, str):
        r = MV._db(ctx, "reservation", rid)
        return r.get("user_id") if r else None
    return None


def _owner_methods(ctx: Any) -> Dict[str, dict]:
    uid = _owner_id(ctx)
    u = MV._db(ctx, "user", uid) if uid else None
    if not u:
        return {}
    return {mid: dict(m, id=m.get("id", mid)) for mid, m in (u.get("payment_methods") or {}).items()}


def _original_method(ctx: Any) -> Optional[str]:
    args = _args(ctx)
    oid = args.get("order_id")
    if isinstance(oid, str):
        o = MV._db(ctx, "order", oid)
        ph = (o or {}).get("payment_history") or []
        return ph[0].get("payment_method_id") if ph else None
    rid = args.get("reservation_id")
    if isinstance(rid, str) and MV._tool(ctx) != "book_reservation":
        r = MV._db(ctx, "reservation", rid)
        ph = (r or {}).get("payment_history") or []
        return ph[0].get("payment_id") if ph else None
    return None


def call_methods_v4(ctx: Any) -> List[str]:
    """The payment method ids the pending call uses (retail payment_method_id; airline payment_id or each
    payment_methods[].payment_id of a booking)."""
    args = _args(ctx)
    out = []
    for k in ("payment_method_id", "payment_id"):
        if isinstance(args.get(k), str):
            out.append(args[k])
    for p in args.get("payment_methods") or []:
        if isinstance(p, dict) and isinstance(p.get("payment_id"), str):
            out.append(p["payment_id"])
    return list(dict.fromkeys(out))


def _brand_words(brand: Any) -> Tuple[str, ...]:
    b = str(brand or "").lower()
    return MV._BRAND_WORDS.get(b, (b,)) if b else ()


def _digit_forms(mid: str, m: dict) -> List[str]:
    """Number forms of one method: the id number, its 4+ ending digits, a card's last_four."""
    out = []
    num = re.search(r"(\d+)$", MV.normalize(mid))
    if num:
        n = num.group(1)
        out += [n[-k:] for k in range(len(n), 3, -1)]
    lf = m.get("last_four")
    if lf:
        out.append(MV.normalize(lf))
    return list(dict.fromkeys(out))


def form_map_v4(methods: Dict[str, dict]) -> Dict[str, Set[str]]:
    """form -> the method ids it fits (D7). A form with 2+ ids is ambiguous."""
    fm: Dict[str, Set[str]] = {}

    def add(form: str, mid: str) -> None:
        if form:
            fm.setdefault(form, set()).add(mid)
    for mid, m in methods.items():
        add(MV.normalize(mid), mid)
        for f in _digit_forms(mid, m):
            add(f, mid)
    for mid, words in MV._unique_word_forms(methods).items():
        for w in words:
            add(MV.normalize(w), mid)
    return fm


def _outer_spans(spans: List[Tuple[int, int, Any]]) -> List[Tuple[int, int, Any]]:
    """Whole-value matching: a span inside a longer span is dropped ("gold" in "rose gold")."""
    out = []
    for s, e, x in spans:
        if any((s2 <= s and e <= e2) and (e2 - s2) > (e - s) for s2, e2, _ in spans):
            continue
        out.append((s, e, x))
    return out


def _negated_before(nt: str, s: int) -> bool:
    return bool(MV._NEG_BEFORE.search(nt[max(0, s - 30):s]))


def methods_named_v4(nt: str, methods: Dict[str, dict], original: Optional[str] = None) -> Set[str]:
    """The methods a normalized text names positively and without ambiguity (D7): exact forms, 4+ ending digits of
    the id, last_four, kind / brand / balance words that fit one method, 'the card' when there is one card, 'the
    original payment method' (the order's / reservation's first payment). A form that fits 2+ methods counts only
    when a brand word within 30 characters picks exactly one of them; otherwise it is ignored (neither a match nor
    a clash). A mention right after not / instead of / rather than ... is not a choice."""
    if not methods or not nt:
        return set()
    fm = form_map_v4(methods)
    spans = [(s, e, f) for f in fm for s, e in MV.form_spans(nt, f)]
    named: Set[str] = set()
    for s, e, f in _outer_spans(spans):
        if _negated_before(nt, s):
            continue
        mids = fm[f]
        if len(mids) > 1:
            near = nt[max(0, s - 30):e + 15]
            mids = {mid for mid in mids
                    if any(MV.has_form(near, w) for w in _brand_words(methods[mid].get("brand")))}
            if len(mids) != 1:
                continue
        named |= mids
    if original in methods:
        for mo in _ORIGINAL.finditer(nt):
            if not _negated_before(nt, mo.start()):
                named.add(original)
                break
    return named


def brand_mismatch_v4(nt: str, m: dict, mid: str) -> Optional[str]:
    """A brand word next to the call card's digits that is not the card's brand ("Visa ending 8484" for a
    Mastercard 8484): the wrong brand word, else None."""
    own = set(_brand_words(m.get("brand")))
    if not own:
        return None
    others = {w for ws in MV._BRAND_WORDS.values() for w in ws} - own
    for f in _digit_forms(mid, m):
        for s, e in MV.form_spans(nt, f):
            near = nt[max(0, s - 30):s] + " " + nt[e:e + 10]
            if any(MV.has_form(near, w) for w in own):
                continue
            for w in sorted(others):
                if MV.has_form(near, w):
                    return w
    return None


def _payment_clash(ctx: Any, nt: str) -> Optional[dict]:
    calls = call_methods_v4(ctx)
    if not calls:
        return None
    methods = _owner_methods(ctx)
    if not methods:
        return None
    named = methods_named_v4(nt, methods, _original_method(ctx))
    other = named - set(calls)
    if other and not (named & set(calls)):
        return {"clash": "payment", "named": sorted(other), "call": calls}
    for mid in calls:
        if mid in methods:
            w = brand_mismatch_v4(nt, methods[mid], mid)
            if w:
                return {"clash": "payment", "named": [w], "call": [mid],
                        "why": f"'{w}' next to the digits of {mid} ({methods[mid].get('brand')})"}
    return None


# ----------------------------------------------------------------------------------------------- other clashes

_NEG_ITEM = re.compile(r"\b(?:not|no|never|except|other than|without|keep|keeping|rather than|instead of|but not|"
                       r"don'?t (?:return|exchange|change|want to return)|do not)\s+(?:[a-z0-9'$.-]+\s+){0,3}$")


def _mentions(nt: str, groups: Dict[Any, List[str]]) -> Set[Any]:
    """The keys of `groups` (key -> forms) whose forms appear positively as whole values (outer spans only, no
    negation word right before)."""
    spans = [(s, e, k) for k, forms in groups.items() for f in forms if f for s, e in MV.form_spans(nt, f)]
    return {k for s, e, k in _outer_spans(spans) if not _NEG_ITEM.search(nt[max(0, s - 30):s])}


def _order(ctx: Any) -> Optional[dict]:
    oid = _args(ctx).get("order_id")
    return MV._db(ctx, "order", oid) if isinstance(oid, str) else None


def _item_clash(ctx: Any, nt: str) -> Optional[dict]:
    if MV._tool(ctx) not in RETAIL_ITEM_TOOLS:
        return None
    o = _order(ctx)
    ids = [i for i in (_args(ctx).get("item_ids") or []) if isinstance(i, str)]
    if not o or not ids:
        return None
    items = o.get("items") or []
    call_names = {MV.normalize(i.get("name", "")) for i in items if i.get("item_id") in ids}
    groups: Dict[Any, List[str]] = {}
    for i in items:
        iid, name = i.get("item_id"), MV.normalize(i.get("name", ""))
        if iid in ids:
            groups[("call", iid)] = [MV.normalize(iid), name]
        else:
            groups[("other", iid)] = [MV.normalize(iid)] + ([name] if name not in call_names else [])
    hit = _mentions(nt, groups)
    others = sorted(k[1] for k in hit if k[0] == "other")
    if others and not any(k[0] == "call" for k in hit):
        return {"clash": "item", "named": others, "call": ids}
    return None


_SHORT_VALUE = re.compile(r"^(?:\d+|.{1,2}|yes|no|none)$")


def _option_clash(ctx: Any, nt: str) -> Optional[dict]:
    """New item tools: the message names another value of a changed option (whole value; short or number-only
    values only next to the option name) and not the call's new value."""
    if MV._tool(ctx) not in NEW_ITEM_TOOLS:
        return None
    args = _args(ctx)
    old_ids, new_ids = args.get("item_ids") or [], args.get("new_item_ids") or []
    st = MV._state(ctx)
    if st is None:
        return None
    for old, new in zip(old_ids, new_ids):
        vo, vn = st.db_get("variant", old), st.db_get("variant", new)
        if not vo or not vn:
            continue
        prod = st.db_get("product", vn.get("product_id"))
        if not prod:
            continue
        oo, no = vo.get("options") or {}, vn.get("options") or {}
        for opt, nval in no.items():
            if oo.get(opt) == nval:
                continue
            values = {str(var.get("options", {}).get(opt)) for var in (prod.get("variants") or {}).values()
                      if var.get("options", {}).get(opt) is not None}
            groups = {}
            for val in values:
                f = MV.normalize(val)
                if _SHORT_VALUE.match(f) and not MV.has_form(nt, MV.normalize(opt)):
                    continue
                groups[val] = [f]
            hit = _mentions(nt, groups)
            if str(nval) in hit:
                continue
            other = sorted(x for x in hit if x != str(nval) and x != str(oo.get(opt)))
            if other:
                return {"clash": "option", "option": opt, "named": other, "call": str(nval), "item": new}
    return None


_ZIP = re.compile(r"(?<![0-9])(\d{5})(?:-\d{4})?(?![0-9])")


def _address_clash(ctx: Any, nt: str) -> Optional[dict]:
    if MV._tool(ctx) not in ADDRESS_TOOLS:
        return None
    z = _args(ctx).get("zip")
    if not isinstance(z, str) or not z:
        return None
    zips = set(_ZIP.findall(nt))
    if zips and z not in zips:
        return {"clash": "address", "named": sorted(zips), "call": z}
    return None


def _person_forms(p: Any) -> Optional[Tuple[str, str]]:
    if isinstance(p, dict) and p.get("first_name") and p.get("last_name"):
        return MV.normalize(p["first_name"]), MV.normalize(p["last_name"])
    return None


def _passenger_clash(ctx: Any, nt: str) -> Optional[dict]:
    tool = MV._tool(ctx)
    if tool not in PASSENGER_TOOLS:
        return None
    args = _args(ctx)
    calls = {fl for fl in (_person_forms(p) for p in args.get("passengers") or []) if fl}
    if not calls:
        return None
    known: Set[Tuple[str, str]] = set()
    uid = _owner_id(ctx)
    u = MV._db(ctx, "user", uid) if uid else None
    if u:
        known |= {fl for fl in (_person_forms(p) for p in (u.get("saved_passengers") or [])) if fl}
        me = _person_forms(u.get("name"))
        if me:
            known.add(me)
    rid = args.get("reservation_id")
    if isinstance(rid, str):
        r = MV._db(ctx, "reservation", rid)
        known |= {fl for fl in (_person_forms(p) for p in ((r or {}).get("passengers") or [])) if fl}
    groups = {("call", fl): [" ".join(fl)] for fl in calls}
    groups.update({("other", fl): [" ".join(fl)] for fl in known - calls})
    hit = _mentions(nt, groups)
    others = sorted(" ".join(k[1]) for k in hit if k[0] == "other")
    if others and not any(k[0] == "call" for k in hit):
        return {"clash": "passenger", "named": others, "call": sorted(" ".join(fl) for fl in calls)}
    return None


CLASH_CHECKS = (_payment_clash, _item_clash, _option_clash, _address_clash, _passenger_clash)


def clash_in_v4(ctx: Any, refs: Iterable[int], kinds: Optional[Sequence[str]] = None) -> Optional[dict]:
    """The first clash in the user messages `refs` (D7, plus item / option / address / passenger), or None."""
    v = MV._view(ctx)
    for r in refs:
        nt = v.norm(r)
        for check in CLASH_CHECKS:
            c = check(ctx, nt)
            if c is not None and (kinds is None or c["clash"] in kinds):
                return dict(c, message=r, text=v.text(r)[:120])
    return None


def clash_free_v4(ctx: Any) -> bool:
    """No user message after the newest anchor L names another payment method, item, option value, address or
    passenger than the call (no anchor: true; the go-ahead parts fail on their own). A clash is noted with both
    values."""
    anchors = go_ahead_anchors_v4(ctx)
    if not anchors:
        return True
    c = clash_in_v4(ctx, b_messages_v4(ctx, anchors[0]))
    if c is not None:
        ctx.note(c)
        return False
    return True


# ----------------------------------------------------------------------------------------------- candidates

FOCUS = (None, "payment")


def go_ahead_candidates_v4(ctx: Any, focus: Optional[str] = None) -> List[list]:
    """[[L, [b...]]], newest L first (at most 2): L an anchor (D3), B every user message after it (D4). A candidate
    whose B holds a strict no (D9) is dropped. focus='payment': only candidates where L or a message of B names the
    call's payment method (D7, no ambiguity) and no message of B names another method (payment clash)."""
    if focus not in FOCUS:
        raise ValueError(f"go_ahead_candidates_v4: focus must be one of {FOCUS}, not {focus!r}")
    v = MV._view(ctx)
    out: List[list] = []
    for L in go_ahead_anchors_v4(ctx):
        B = b_messages_v4(ctx, L)
        if not B:
            continue
        no = next((b for b in B if MV.is_strict_no(v.norm(b))), None)
        if no is not None:
            ctx.note({"strict_no": no, "anchor": L, "text": v.text(no)[:80]})
            continue
        if focus == "payment":
            calls = set(call_methods_v4(ctx))
            methods = _owner_methods(ctx)
            orig = _original_method(ctx)
            if not calls or not any(methods_named_v4(v.norm(x), methods, orig) & calls for x in [L] + B):
                continue
            if clash_in_v4(ctx, B, kinds=("payment",)) is not None:
                continue
        out.append([L, B])
    return out


# ----------------------------------------------------------------------------------------------- the question

_ASK_OVERRIDE: Optional[Callable] = None            # tests put a double here


def _ask_first_yes_impl() -> Callable:
    if _ASK_OVERRIDE is not None:
        return _ASK_OVERRIDE
    h = F.registered_names().get("ask_first_yes_v4")
    if h is None:
        try:
            import state_tracker.v4.questions_v4  # noqa: F401  (agent A3; registers ask_first_yes_v4)
        except ImportError:
            pass
        h = F.registered_names().get("ask_first_yes_v4")
    if h is None:
        raise F.NotDefinedYet("go_ahead_yes_v4 needs ask_first_yes_v4 (state_tracker/v4/questions_v4.py)")
    return h.func


def go_ahead_fast_v4(ctx: Any, focus: Optional[str] = None) -> bool:
    """go_ahead_fast_v4(focus=None): D8 on the go-ahead candidates: there is a candidate and the newest message of
    its B (the newest user message before the call) is a plain yes. True is noted {"fast_path": True, "question":
    "K1", ...}; no LLM call. Used as `go_ahead_fast_v4() or ask_first_yes_v4('K1', go_ahead_candidates_v4(),
    limit=2)`, so K1v4 is asked only when the fast path does not hold."""
    cands = go_ahead_candidates_v4(ctx, focus)
    if not cands:
        return False
    newest = cands[0][1][-1]
    text = MV._view(ctx).text(newest)
    if is_short_go_ahead_v4(text):
        ctx.note({"fast_path": True, "question": "K1", "message": newest, "anchor": cands[0][0], "text": text[:80]})
        return True
    return False


def go_ahead_yes_v4(ctx: Any, focus: Optional[str] = None) -> bool:
    """The whole go-ahead (D4) as one Python call (what the fact expressions do with `or`): the fast path, else
    ask_first_yes_v4('K1', candidates, limit=2). No candidate: false. Not a registered helper."""
    if go_ahead_fast_v4(ctx, focus):
        return True
    cands = go_ahead_candidates_v4(ctx, focus)
    if not cands:
        return False
    return _ask_first_yes_impl()(ctx, "K1", cands, limit=ANCHOR_LIMIT)


# ----------------------------------------------------------------------------------------------- insurance (K17)

_INSURANCE = re.compile(r"\b(?:insur\w*|coverage|protection)\b")


def insurance_candidates_v4(ctx: Any) -> List[list]:
    """K17v4's window (predicate_table, booking_insurance row), newest first, at most 4: (1) [u] for each user message
    in S holding insur* / coverage / protection after the first reply to the newest such agent message (all such
    user messages in S when no agent message holds the words); (2) [A, r] for each agent message in S holding the
    words and its first user reply."""
    v = MV._view(ctx)
    s = span_start_v4(ctx)
    agents = [a for a in reversed(v.agent_refs()) if a > s and _INSURANCE.search(v.norm(a))]
    pairs = []
    for a in agents:
        r = MV.reply_after(ctx, a)
        if r is not None:
            pairs.append([a, r])
    after = pairs[0][1] if pairs else s
    alone = [[u] for u in reversed(v.user_refs()) if u > after and _INSURANCE.search(v.norm(u))]
    return (alone + pairs)[:INSURANCE_LIMIT]


# ----------------------------------------------------------------------------------------------- registration

HELPERS = (
    ("go_ahead_anchors_v4", go_ahead_anchors_v4, 0, 0, (), SOURCE, "D3: the listing anchors L, newest first, at most 2"),
    ("go_ahead_candidates_v4", go_ahead_candidates_v4, 0, 0, ("focus",), SOURCE,
     "D3 + D4: [[L, [user messages after L]]] without a strict no (focus='payment': names the call's method)"),
    ("clash_free_v4", clash_free_v4, 0, 0, (), SOURCE,
     "D7: no user message after L names another payment method, item, option, address or passenger"),
    ("short_go_ahead_v4", short_go_ahead_v4, 1, 1, (), SOURCE, "D8: a plain yes, by a whole-message match"),
    ("insurance_candidates_v4", insurance_candidates_v4, 0, 0, (), SOURCE, "K17v4's messages in the booking span"),
    ("go_ahead_fast_v4", go_ahead_fast_v4, 0, 0, ("focus",), SOURCE,
     "D8 on the go-ahead candidates: the newest user message is a plain yes (no LLM call)"),
)
NAMES = tuple(h[0] for h in HELPERS)


def register_helpers_v4() -> List[str]:
    """Register the helpers (registering again changes nothing)."""
    for name, func, lo, hi, kws, src, doc in HELPERS:
        F.register_name(name, func, lo, hi, kws, source=src, doc=doc)
    return list(NAMES)


register_helpers_v4()
