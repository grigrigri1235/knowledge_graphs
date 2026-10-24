"""Tracker v3, part 7: info classes. For each id-like value or amount in a text, where it comes from.

docs/planning/tracker_v3/p7.md, piece 3. One definition, used by the disclosure facts (message_view helpers
reply_discloses_user_data, reply_holds_other_user_data) and by the block messages (p10). The leak CHECKS do not use
it: they use a separate raw scan of the database, so they do not check themselves.

    IC.classify_text(text, view, state, me=None)   -> [{"value", "kind", "classes", "users"}]
    IC.user_data_values(text, view, state, owner_ok=())   -> the values that count as user data

The values looked at (the token filter of the disclosure fact): user ids, emails, street lines (address1), zips,
payment method ids, card last four digits, gift card / certificate balances, order ids, item ids, tracking ids,
reservation ids, dates of birth, and amounts written with "$" or two decimals. Status words and small numbers do not
count alone. A 4-digit number inside a date (a year) is part of the date, not a separate value.

Classes (a value may have several):
  user_typed       a user message holds the value (order ids with and without "#"; dates in six forms)
  call_argument    the pending call's arguments hold it (not for a reply: its argument is the text itself)
  policy_constant  the policy text or the tool schemas hold it (e.g. the example ids "#W0000000", "1008292230")
  catalog          a field of a catalog object: product (id, name), variant (item id, price), flight (number, price),
                   airport (code, city)
  db_user          a field of a user, order, payment method or reservation; "users" lists the owners. Built from
                   τ-bench's data at the start of the conversation, plus the objects in this conversation's worked
                   tool outputs (so a changed address or a new reservation is known too)

user_data_values: a value counts when it is db_user, not user_typed, not call_argument, not policy_constant, and not
owned by a user in owner_ok. A value that is also catalog (an item id, a price) counts only when a worked user-data
tool output of this conversation showed it and no worked catalog output did.

Standard library only. No LLM call, no network. Never imports gold code or a scoring module.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from state_tracker.v3 import message_view as MV

CATALOG_OUTPUT_TOOLS = ("get_product_details", "list_all_product_types", "search_direct_flight",
                        "search_onestop_flight", "list_all_airports")
USER_DATA_OUTPUT_TOOLS = ("find_user_id_by_email", "find_user_id_by_name_zip", "get_user_details",
                          "get_order_details", "cancel_pending_order", "modify_pending_order_address",
                          "modify_pending_order_items", "modify_pending_order_payment", "modify_user_address",
                          "return_delivered_order_items", "exchange_delivered_order_items", "get_reservation_details",
                          "book_reservation", "cancel_reservation", "update_reservation_flights",
                          "update_reservation_baggages", "update_reservation_passengers", "send_certificate")


def canon_amount(x: Any) -> Optional[str]:
    """An amount as a text: 54.04 -> '54.04', 69.0 -> '69', 54.4 -> '54.4'."""
    if isinstance(x, bool):
        return None
    try:
        f = round(float(x), 2)
    except (TypeError, ValueError):
        return None
    s = f"{f:.2f}".rstrip("0").rstrip(".")
    return s or "0"


# ----------------------------------------------------------------------------------------------- candidates

_C_EMAIL = re.compile(r"(?<![a-z0-9._%+-])[a-z0-9][a-z0-9._%+-]*@[a-z0-9-]+(?:\.[a-z0-9-]+)+")
_C_PAY = re.compile(r"(?<![a-z0-9_])(?:gift_card|credit_card|paypal|certificate)_\d+(?![a-z0-9_])")
_C_UID = re.compile(r"(?<![a-z0-9_])[a-z]+(?:_[a-z]+)*_\d{3,}(?![a-z0-9_])")
_C_ORDER = re.compile(r"(?<![a-z0-9_])#?w\d{7}(?![a-z0-9_])")
_C_AMOUNT = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?(?![\d])"
                       r"|(?<![\d.,$])(\d{1,3}(?:,\d{3})+|\d+)\.(\d{2})(?![\d])")
_C_NUM = re.compile(r"(?<![a-z0-9_.,$#])\d{4,}(?![a-z0-9_]|[.,]\d)")
_C_RES = re.compile(r"(?<![a-z0-9_])[a-z0-9]{6}(?![a-z0-9_])")
_DATE_SPANS = (MV._D_ISO, MV._D_NUM, MV._D_MDY, MV._D_DMY)


def _blank_spans(text: str, patterns: Iterable["re.Pattern[str]"]) -> str:
    out = list(text)
    for p in patterns:
        for m in p.finditer(text):
            for i in range(m.start(), m.end()):
                out[i] = " "
    return "".join(out)


def candidates(norm: str) -> List[Tuple[str, str]]:
    """(kind, value) of every id-like value or amount in a normalized text (values in the index's form)."""
    out: List[Tuple[str, str]] = []
    for m in _C_EMAIL.findall(norm):
        out.append(("email", m.rstrip(".")))
    pays = set(_C_PAY.findall(norm))
    out += [("payment_id", p) for p in sorted(pays)]
    out += [("user_id", u) for u in _C_UID.findall(norm) if u not in pays]
    out += [("order_id", "#" + o.lstrip("#")) for o in _C_ORDER.findall(norm)]
    for a, b, c, d in _C_AMOUNT.findall(norm):
        whole, dec = (a, b) if a else (c, d)
        out.append(("amount", canon_amount(whole.replace(",", "") + ("." + dec if dec else ""))))
    for iso in sorted(MV.dates_in(norm)):
        out.append(("date", iso))
    rest = _blank_spans(norm, _DATE_SPANS + (_C_AMOUNT, _C_EMAIL, _C_PAY, _C_UID, _C_ORDER))
    out += [("number", n) for n in _C_NUM.findall(rest)]
    out += [("code6", r) for r in _C_RES.findall(rest)]
    return list(dict.fromkeys(out))


# ----------------------------------------------------------------------------------------------- the index

class Index:
    """value -> {"kinds": set, "users": set} for user data; catalog values; street lines; policy constants."""

    def __init__(self, domain: str):
        self.domain = domain
        self.values: Dict[str, Dict[str, set]] = {}
        self.streets: Dict[str, Set[str]] = {}
        self.catalog: Set[str] = set()
        self.policy: Set[str] = set()

    def add(self, value: Any, kind: str, user: Any) -> None:
        if value is None or isinstance(value, bool):
            return
        v = canon_amount(value) if kind in ("amount", "price") else MV.normalize(str(value))
        if not v:
            return
        e = self.values.setdefault(v, {"kinds": set(), "users": set()})
        e["kinds"].add(kind)
        if isinstance(user, str):
            e["users"].add(user)
        if kind == "street":
            self.streets.setdefault(v, set()).update([user] if isinstance(user, str) else [])

    def add_user(self, uid: str, u: dict) -> None:
        if not isinstance(u, dict):
            return
        self.add(uid, "user_id", uid)
        self.add(u.get("email"), "email", uid)
        addr = u.get("address") or {}
        self.add(addr.get("address1"), "street", uid)
        self.add(addr.get("zip"), "zip", uid)
        if self.domain == "airline":
            self.add(u.get("dob"), "dob", uid)
            for p in u.get("saved_passengers") or []:
                if isinstance(p, dict):
                    self.add(p.get("dob"), "dob", uid)
        for mid, m in (u.get("payment_methods") or {}).items():
            if not isinstance(m, dict):
                continue
            self.add(m.get("id", mid), "payment_id", uid)
            self.add(m.get("last_four"), "last_four", uid)
            num = re.search(r"(\d+)$", str(m.get("id", mid)))
            if num:                                 # users name a gift card by the number in its id, or its tail
                self.add(num.group(1), "shown_number", uid)
                self.add(num.group(1)[-4:], "shown_number", uid)
            for k in ("balance", "amount"):
                if k in m:
                    self.add(m[k], "amount", uid)
        for oid in u.get("orders") or []:
            self.add(oid, "order_id", uid)
        for rid in u.get("reservations") or []:
            self.add(rid, "reservation_id", uid)

    def add_order(self, o: dict) -> None:
        if not isinstance(o, dict):
            return
        uid = o.get("user_id")
        self.add(o.get("order_id"), "order_id", uid)
        addr = o.get("address") or {}
        self.add(addr.get("address1"), "street", uid)
        self.add(addr.get("zip"), "zip", uid)
        for it in o.get("items") or []:
            if isinstance(it, dict):
                self.add(it.get("item_id"), "item_id", uid)
                self.add(it.get("price"), "price", uid)
        for f in o.get("fulfillments") or []:
            if isinstance(f, dict):
                for t in f.get("tracking_id") or []:
                    self.add(t, "tracking_id", uid)
        for p in o.get("payment_history") or []:
            if isinstance(p, dict):
                self.add(p.get("payment_method_id"), "payment_id", uid)
                self.add(p.get("amount"), "price", uid)

    def add_reservation(self, r: dict) -> None:
        if not isinstance(r, dict):
            return
        uid = r.get("user_id")
        self.add(r.get("reservation_id"), "reservation_id", uid)
        for p in r.get("passengers") or []:
            if isinstance(p, dict):
                self.add(p.get("dob"), "dob", uid)
        for p in r.get("payment_history") or []:
            if isinstance(p, dict):
                self.add(p.get("payment_id"), "payment_id", uid)
                self.add(p.get("amount"), "price", uid)
        for f in r.get("flights") or []:
            if isinstance(f, dict):
                self.add(f.get("price"), "price", uid)

    def lookup(self, kind: str, value: str) -> Optional[Dict[str, set]]:
        if kind == "code6":
            return self.values.get(value)
        return self.values.get(value)


_BASE: Dict[str, Index] = {}


def _policy_texts(domain: str) -> List[str]:
    from state_tracker import tau_copy
    return [tau_copy.policy_text(domain), json.dumps(tau_copy.tools_info(domain))]


def base_index(domain: str) -> Index:
    """The index of τ-bench's data at the start of a conversation (built once per process)."""
    if domain in _BASE:
        return _BASE[domain]
    db = MV._initial_db(domain)
    ix = Index(domain)
    for uid, u in (db.get("users") or {}).items():
        ix.add_user(uid, u)
    for o in (db.get("orders") or {}).values():
        ix.add_order(o)
    for r in (db.get("reservations") or {}).values():
        ix.add_reservation(r)
    for p in (db.get("products") or {}).values():
        ix.catalog.add(MV.normalize(p.get("product_id", "")))
        ix.catalog.add(MV.normalize(p.get("name", "")))
        for iid, var in (p.get("variants") or {}).items():
            ix.catalog.add(MV.normalize(var.get("item_id", iid)))
            a = canon_amount(var.get("price"))
            if a:
                ix.catalog.add(a)
    for fn, f in (db.get("flights") or {}).items():
        ix.catalog.add(MV.normalize(fn))
        for day in (f.get("dates") or {}).values():
            for price in ((day or {}).get("prices") or {}).values():
                a = canon_amount(price)
                if a:
                    ix.catalog.add(a)
    if domain == "airline":
        for code, city in MV._airports(None).items():
            ix.catalog.add(MV.normalize(code))
            ix.catalog.add(MV.normalize(city))
    ix.catalog.discard("")
    for t in _policy_texts(domain):
        nt = MV.normalize(t)
        ix.policy.update(v for _, v in candidates(nt))
    _BASE[domain] = ix
    return ix


def conversation_index(view: Any, state: Any) -> Tuple[Index, Dict[str, set]]:
    """(the base index plus the objects in this conversation's worked tool outputs, {value: tools that showed it});
    cached on the view."""
    key = ("ic_index", len(view.entries))
    if key in view.cache:
        return view.cache[key]
    domain = view.domain or getattr(state, "domain", None)
    base = base_index(domain)
    extra = Index(domain)
    shown_by: Dict[str, set] = {}
    for r in view.data_tool_refs():
        e = view.entries[r]
        cands = candidates(e.norm)
        for _, val in cands:
            shown_by.setdefault(val, set()).add(e.tool)
        try:
            data = json.loads(e.text)
        except (TypeError, ValueError):
            data = None
        nums = _numbers(data)
        for num in nums:
            shown_by.setdefault(num, set()).add(e.tool)
        owner = _output_owner(e, data)
        if owner is not None and e.tool in USER_DATA_OUTPUT_TOOLS:
            # every value a user-data output showed is data of the user it belongs to
            for kind, val in cands:
                if kind in _OUTPUT_KIND:
                    extra.add(val, _OUTPUT_KIND[kind], owner)
            for num in nums:
                extra.add(num, "amount", owner)
        if not isinstance(data, dict):
            continue
        if "order_id" in data and "items" in data:
            extra.add_order(data)
        elif "reservation_id" in data and "flights" in data:
            extra.add_reservation(data)
        elif "payment_methods" in data and isinstance(e.args.get("user_id"), str):
            extra.add_user(e.args["user_id"], data)
    view.cache[key] = (_Merged(base, extra), shown_by)
    return view.cache[key]


def _numbers(x: Any) -> List[str]:
    """Every number in a parsed JSON output, as canon_amount texts."""
    out: List[str] = []
    if isinstance(x, dict):
        for v in x.values():
            out += _numbers(v)
    elif isinstance(x, list):
        for v in x:
            out += _numbers(v)
    elif isinstance(x, (int, float)) and not isinstance(x, bool):
        a = canon_amount(x)
        if a:
            out.append(a)
    return out


_OUTPUT_KIND = {"email": "email", "payment_id": "payment_id", "user_id": "user_id", "order_id": "order_id",
                "amount": "amount", "date": "dob", "number": "shown_number"}


def _output_owner(e: Any, data: Any) -> Optional[str]:
    """The user a worked tool output belongs to: an order's or a reservation's user_id, the user_id argument of a
    user read or write, the user id a find tool returned."""
    if isinstance(data, dict) and isinstance(data.get("user_id"), str):
        return data["user_id"]
    if e.tool in ("get_user_details", "modify_user_address") and isinstance(e.args.get("user_id"), str):
        return e.args["user_id"]
    if e.tool in ("find_user_id_by_email", "find_user_id_by_name_zip") and e.text.strip():
        return e.text.strip()
    return None


class _Merged:
    """The base index with the conversation's additions."""

    def __init__(self, base: Index, extra: Index):
        self.base, self.extra = base, extra
        self.catalog, self.policy, self.domain = base.catalog, base.policy, base.domain

    def lookup(self, kind: str, value: str) -> Optional[Dict[str, set]]:
        a, b = self.base.values.get(value), self.extra.values.get(value)
        if a is None and b is None:
            return None
        return {"kinds": (a or {}).get("kinds", set()) | (b or {}).get("kinds", set()),
                "users": (a or {}).get("users", set()) | (b or {}).get("users", set())}

    def streets(self) -> Dict[str, set]:
        out = {k: set(v) for k, v in self.base.streets.items()}
        for k, v in self.extra.streets.items():
            out.setdefault(k, set()).update(v)
        return out


# ----------------------------------------------------------------------------------------------- classes

# which index kinds a candidate of each text kind may stand for
_KIND_FITS = {
    "email": {"email"}, "payment_id": {"payment_id"}, "user_id": {"user_id"}, "order_id": {"order_id"},
    "amount": {"amount", "price"}, "date": {"dob"}, "street": {"street"},
    "number": {"zip", "last_four", "item_id", "tracking_id", "shown_number"}, "code6": {"reservation_id"},
}


def _typed_sets(view: Any) -> Tuple[List[str], set, set]:
    key = ("ic_typed", len(view.entries))
    if key not in view.cache:
        norms = [view.norm(r) for r in view.user_refs()]
        amounts, dates = set(), set()
        for nt in norms:
            for k, v in candidates(nt):
                if k == "amount":
                    amounts.add(v)
            dates |= set(MV.dates_in(nt))
        view.cache[key] = (norms, amounts, dates)
    return view.cache[key]


def _arg_values(view: Any) -> set:
    if view.pending_tool in (None, "respond"):
        return set()
    out: set = set()

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for y in x.values():
                walk(y)
        elif isinstance(x, list):
            for y in x:
                walk(y)
        elif isinstance(x, (int, float)) and not isinstance(x, bool):
            out.add(canon_amount(x))
            out.add(MV.normalize(str(x)))
        elif isinstance(x, str):
            v = MV.normalize(x)
            out.add(v)
            if MV._ORDER_ID.fullmatch(v):
                out.add("#" + v.lstrip("#"))
    walk(view.pending_args)
    return out


def _is_typed(view: Any, kind: str, value: str) -> bool:
    norms, amounts, dates = _typed_sets(view)
    if kind == "amount":
        return value in amounts
    if kind == "date":
        return value in dates
    return any(MV.text_has_value(nt, value) for nt in norms)


def classify_text(text: Any, view: Any, state: Any = None, me: Optional[str] = None) -> List[dict]:
    """One {"value", "kind", "classes", "users"} per id-like value or amount in the text (see the module text).
    me is only reported ("mine": the value is a field of me's records)."""
    ix, shown_by = conversation_index(view, state)
    nt = MV.normalize(text)
    args = _arg_values(view)
    out = []
    found = []
    for kind, val in candidates(nt):
        found.append((kind, val))
    for street, users in ix.streets().items():
        if MV.has_form(nt, street):
            found.append(("street", street))
    for kind, val in found:
        classes = []
        if _is_typed(view, kind, val):
            classes.append("user_typed")
        if val in args:
            classes.append("call_argument")
        if val in ix.policy:
            classes.append("policy_constant")
        if val in ix.catalog:
            classes.append("catalog")
        hit = ix.lookup(kind, val)
        users: set = set()
        if hit is not None and hit["kinds"] & _KIND_FITS[kind]:
            classes.append("db_user")
            users = set(hit["users"])
        out.append({"value": val, "kind": (sorted(hit["kinds"])[0] if hit and "db_user" in classes else kind),
                    "text_kind": kind, "classes": classes, "users": sorted(users), "mine": bool(me and me in users),
                    "shown_by": sorted(shown_by.get(val, ())), "seen": _seen(ix, shown_by, val)})
    return out


def _seen(ix: Any, shown_by: Dict[str, set], val: str) -> bool:
    """A worked data tool output of this conversation (before the check) showed the value: it is a value of such an
    output's text, or of a record such an output held (its user, order, reservation or payment fields, a payment id's
    number and its last four digits, a street line). Database data the agent could have seen."""
    if shown_by.get(val):
        return True
    extra = getattr(ix, "extra", None)
    return extra is not None and (val in extra.values or val in extra.streets)


def user_data_values(text: Any, view: Any, state: Any = None, owner_ok: Iterable[Any] = (),
                     seen_only: bool = False) -> List[dict]:
    """The values of the text that count as user data (see the module text). seen_only=True (the disclosure fact's
    part a, RC11 M1): only values that a worked data tool output of this conversation showed (_seen); a value that
    no output showed cannot come from the database the agent read (e.g. an example ZIP in the first reply that
    happens to be some user's ZIP)."""
    ok = {u for u in owner_ok if isinstance(u, str)}
    out = []
    for c in classify_text(text, view, state):
        cl = c["classes"]
        if "db_user" not in cl or {"user_typed", "call_argument", "policy_constant"} & set(cl):
            continue
        if ok & set(c["users"]):
            continue
        if seen_only and not c["seen"]:
            continue
        by = set(c["shown_by"])
        if "catalog" in cl or c["kind"] in ("amount", "price") or c.get("text_kind") == "amount":
            # a catalog value or an amount is user data only when a user-data tool output showed it (amounts repeat
            # across many records, so an amount alone says nothing about where it came from)
            if not (by & set(USER_DATA_OUTPUT_TOOLS)) or (by & set(CATALOG_OUTPUT_TOOLS)):
                continue
        out.append(c)
    return out
