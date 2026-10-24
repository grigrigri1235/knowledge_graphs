"""Tracker v4: the "details listed" check (v3 tiny question K2) as code.

The main idea in plain words: before a write, the agent must list the action's details. v3 asked a tiny LLM
question (K2) about one agent message. v4 checks each detail ("line") by string match over a written window: the
agent's messages since the last write that had a user reply, plus the user's own words. Each line accepts every
form the v1 DB / wiki backs (DB-only check: output/eval_v4/form_check.md). A missing line is reported with its
expected value, so the block message can name it.

Definitions (docs/planning/tracker_v4/predicate_table.md section 0, the authority):
  D1 write / worked write   the 7 retail and 6 airline write tools; worked = the output does not start with "Error".
  D2 span S                 every message after s, where s = the newest worked write that has a user message after
                            it (else the start). A write with no user message after it is a batch member: it shares
                            the span of the write before it.
  D3 anchor L               the newest agent text message in S that names a key detail of the call and has a user
                            message after it; at most 2, newest first (listing_anchors_v4).
  D5 listing text T         every agent text message in S, plus L, plus every user message in S
                            (listing_window_v4). A line passes when it is found in one message of T.
  D6 current object         the order / reservation id also passes when it is the newest order / reservation id
                            named in any user or agent text before the call.
  D7 payment forms          full id; 4+ ending digits of the id number; a card's last four (brand optional); the kind
                            word / brand word / "the card" / the balance when it fits only one method of the owner;
                            "the original payment method" when the call's method is payment_history[0]. A 4-digit
                            number that is a 4-digit form of two of the owner's methods names neither. Negation aware
                            ("not the Mastercard"); a brand word next to the digits that is not the card's brand does
                            not count (a clash).

Lines per tool (code_change_map.md "K2 code lines", predicate_table.md rows of the two facts):
  retail   order id (D6); cancel reason (exact phrase; else the tiny question K18 decides: listing_reason_ok_v4 and
           listing_reason_candidates_v4); each changed address field (country dropped; "your default address" when
           the call's address is the user's default); payment method (D7); each old item (product name, a word of it
           that names no other product of the order, or the item id; the item id or an option value only it has when
           the order has 2+ items of that product and the call does not take all of them); each new item (its id, or
           every changed option value, whole value; short / number / yes-no / shared values only next to the option
           name); return: each item or "all the items" when every item is returned.
  airline  reservation id (D6); flight number + date (changed flights only; "HAT170", "HAT 170", "flight 170"; any
           date form, year optional); cabin (book; flight change only when it differs); passenger first + last name
           (changed passengers only; the date of birth only when it is the changed field); payment method(s) (D7),
           with the amount when 2+; bags: the total when > 0 (book), the new total or the number added (bag change);
           the paid number when > 0 (book); the payment method of a bag change only when it costs money;
           certificate amount. Insurance (book) is decided by the tiny question K17 (fact
           booking_insurance_decision_established_and_matched); its line is listed with decided_by "K17" and skipped
           here.

Missing record (code_change_map.md section 0.2 item 5): {"line", "expected", "forms", "fact", "part"}. The helpers
note {"missing": [records]} with ctx.note when a line is missing.

Registered helpers (source "structure"): listing_window_v4(), listing_anchors_v4(), listing_ok_v4(),
listing_missing_count_v4(), listing_reason_ok_v4(), listing_reason_candidates_v4().
Python API: span_refs_v4, listing_window_v4, listing_anchors_v4, line_specs_v4, line_present_v4,
listing_missing_v4, reason_phrase_in_v4, payment_named_v4.

Standard library only. No LLM call, no network. Never imports gold code or a scoring module.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from state_tracker.v3 import facts_format_v3 as F
from state_tracker.v3 import message_view as MV
from state_tracker.v3 import questions as Q

SOURCE = "structure"
RETAIL_WRITES = ("cancel_pending_order", "modify_pending_order_address", "modify_pending_order_items",
                 "modify_pending_order_payment", "modify_user_address", "return_delivered_order_items",
                 "exchange_delivered_order_items")
AIRLINE_WRITES = ("book_reservation", "update_reservation_flights", "update_reservation_baggages",
                  "update_reservation_passengers", "cancel_reservation", "send_certificate")
WRITES = {"retail": RETAIL_WRITES, "airline": AIRLINE_WRITES}
ANCHOR_LIMIT = 2                       # D3: at most 2 anchor candidates
REASON_LIMIT = 4                       # K18 window: messages of T, newest first, at most 4
BAG_FEE = 50                           # airline policy: each extra (non-free) bag costs $50
ADDRESS_FIELDS = ("address1", "address2", "city", "state", "zip")      # country dropped (form check: USA 1500/1500)
ADDRESS_LABELS = {"address1": "street (line 1)", "address2": "line 2", "city": "city", "state": "state",
                  "zip": "zip"}


# ----------------------------------------------------------------------------------------------- text matching

def _texts(texts: Iterable[Any]) -> List[Tuple[str, str]]:
    """(normalized lower-case text, normalized case-kept text) of each message text."""
    out = []
    for t in texts:
        if isinstance(t, tuple) and len(t) == 2:
            out.append(t)
        else:
            out.append((MV.normalize(t), MV.plain(t)))
    return out


def _flex_body(value_norm: str) -> str:
    """A regex body for a normalized value: letter / digit chunks, joined by optional spaces or hyphens
    ("10-inch" = "10 inch" = "10inch"; "t-shirt" = "t shirt"; "wi-fi + cellular")."""
    chunks = re.findall(r"[a-z]+|\d+(?:\.\d+)?|[^a-z0-9\s-]", value_norm)
    return r"[\s-]*".join(re.escape(c) for c in chunks)


_FLEX_CACHE: Dict[str, "re.Pattern[str]"] = {}


def _flex_re(value: Any) -> Optional["re.Pattern[str]"]:
    v = MV.normalize(str(value))
    if not v:
        return None
    if v not in _FLEX_CACHE:
        _FLEX_CACHE[v] = re.compile(rf"(?<![a-z0-9_]){_flex_body(v)}(?![a-z0-9_])")
    return _FLEX_CACHE[v]


def _spans(norm: str, value: Any) -> List[Tuple[int, int]]:
    rx = _flex_re(value)
    return [m.span() for m in rx.finditer(norm)] if rx is not None else []


def _whole_spans(norm: str, value: Any, longer: Sequence[Any] = ()) -> List[Tuple[int, int]]:
    """Spans of the value that are not inside a longer value of the same option ("gold" inside "rose gold",
    "polarized" inside "non-polarized", "wi-fi" inside "wi-fi + cellular")."""
    out = _spans(norm, value)
    if not out or not longer:
        return out
    big = [sp for x in longer for sp in _spans(norm, x)]
    return [(s, e) for s, e in out if not any(bs <= s and e <= be for bs, be in big)]


def _num_ok(norm: str, s: int, e: int) -> bool:
    """A digit match is not part of another number: not a price ("$3714"), not a date / time / decimal piece
    ("2024-05-15", "12:30", "3714.50", "77034-3714")."""
    if s > 0 and norm[s - 1] == "$":
        return False
    if s >= 2 and norm[s - 1] in ".,/:-" and norm[s - 2].isdigit():
        return False
    if e + 1 < len(norm) and norm[e] in ".,/:-" and norm[e + 1].isdigit():
        return False
    return True


def _digit_spans(norm: str, digits: str) -> List[Tuple[int, int]]:
    return [(s, e) for s, e in MV.form_spans(norm, digits) if _num_ok(norm, s, e)]


def _negated(norm: str, s: int) -> bool:
    return bool(MV._NEG_BEFORE.search(norm[max(0, s - 30):s]))


def _near_words(norm: str, s: int, e: int, names: Sequence[str], words: int = 3) -> bool:
    """One of the option names is within `words` words before or after the span."""
    for n in names:
        body = _flex_body(MV.normalize(n))
        if not body:
            continue
        body = rf"(?:{body})(?:e?s)?"                     # "lens" / "lenses", "size" / "sizes"
        if re.search(rf"(?<![a-z0-9_]){body}(?:\W+[\w'-]+){{0,{words}}}\W*$", norm[:s]):
            return True
        if re.search(rf"^\W*(?:[\w'-]+\W+){{0,{words}}}{body}(?![a-z0-9_])", norm[e:]):
            return True
    return False


def _amount_re(amount: Any) -> Optional["re.Pattern[str]"]:
    a = MV._amount_text(amount)
    if a is None:
        return None
    ip, _, dp = a.partition(".")
    if len(ip) > 3:
        groups = []
        head = len(ip) % 3 or 3
        groups.append(ip[:head])
        groups += [ip[i:i + 3] for i in range(head, len(ip), 3)]
        ip_re = ",?".join(groups)
    else:
        ip_re = ip
    dec = rf"\.{dp}0*" if dp else r"(?:\.0+)?"
    return re.compile(rf"(?<![0-9.,]){ip_re}{dec}(?![0-9]|\.[0-9])")


def _amount_in(norm: str, amount: Any) -> bool:
    rx = _amount_re(amount)
    return rx is not None and rx.search(norm) is not None


# ----------------------------------------------------------------------------------------------- payment (D7)

_ORIGINAL = re.compile(
    r"\boriginal (?:form of )?(?:payment(?: method)?|method(?: of payment)?|card|credit card|gift card|paypal|"
    r"account|source)\b|\b(?:card|method|account) (?:i|you|they|we) (?:originally )?(?:paid|used|purchased|bought)"
    r"(?: with)?\b|\bsame (?:payment )?(?:method|card|account) (?:as|i|you|that|used)\b|\bsame as (?:the |my |your )?"
    r"(?:order|booking|reservation|original|purchase|before)\b|\b(?:refund(?:ed)?|back|credited) to (?:the |your |"
    r"my )?original\b")
_BRANDS_ALL = sorted({w for ws in MV._BRAND_WORDS.values() for w in ws}, key=len, reverse=True)


def _owner_methods(state: Any, user_id: Any) -> Dict[str, dict]:
    u = state.db_get("user", user_id) if isinstance(user_id, str) and state is not None else None
    if not isinstance(u, dict):
        return {}
    return {mid: dict(m, id=m.get("id", mid)) for mid, m in (u.get("payment_methods") or {}).items()}


def _four_forms(m: dict) -> List[str]:
    num = re.search(r"(\d+)$", MV.normalize(m.get("id", "")))
    out = [num.group(1)[-4:]] if num else []
    if m.get("last_four"):
        out.append(MV.normalize(m["last_four"]))
    return out


def payment_check_v4(state: Any, pid: Any, owner: Any, original: Optional[str] = None) -> dict:
    """The check data of one payment method (D7): exact forms, loose forms, original, brand."""
    pid = str(pid)
    methods = _owner_methods(state, owner)
    m = methods.get(pid)
    if m is None:
        pm = state.db_get("payment_method", pid) if state is not None else None
        m = dict(pm, id=pid) if isinstance(pm, dict) else {"id": pid}
        methods = dict(methods, **{pid: m})
    exact = list(MV.exact_payment_forms(m))
    num = re.search(r"(\d+)$", MV.normalize(pid))
    if num:
        n = num.group(1)
        exact += [n[-k:] for k in range(5, len(n))]              # 4+ ending digits: 5 and 6 as well
    four_other = {f for mid, x in methods.items() if mid != pid for f in _four_forms(x)}
    exact = [f for f in dict.fromkeys(exact) if f and not (len(f) == 4 and f.isdigit() and f in four_other)]
    loose = list(MV._unique_word_forms(methods).get(pid, []))
    brand = str(m.get("brand") or "").lower() or None
    own_brand = set(MV._BRAND_WORDS.get(brand, (brand,))) if brand else set()
    return {"kind": "payment", "id": pid, "exact": exact, "loose": loose, "original": original == pid,
            "brand": brand, "other_brands": [b for b in _BRANDS_ALL if b not in own_brand],
            "source": MV._method_kind(m), "last_four": m.get("last_four")}


def _payment_hit(norm: str, chk: dict) -> bool:
    for f in chk["exact"]:
        digits = f.isdigit()
        spans = _digit_spans(norm, f) if digits else MV.form_spans(norm, f)
        for s, e in spans:
            if _negated(norm, s):
                continue
            if digits and chk.get("brand"):
                before = norm[max(0, s - 25):s]
                if any(MV.has_form(before, b) for b in chk["other_brands"]) and not any(
                        MV.has_form(before, b) for b in MV._BRAND_WORDS.get(chk["brand"], (chk["brand"],))):
                    continue                                      # "Visa ending 8484" for a Mastercard: a clash
            return True
    for f in chk["loose"]:
        for s, e in MV.form_spans(norm, f):
            if not _negated(norm, s):
                return True
    if chk.get("original"):
        for mo in _ORIGINAL.finditer(norm):
            if not _negated(norm, mo.start()):
                return True
    return False


def payment_named_v4(text: Any, chk: dict) -> bool:
    """One message text names the payment method of `chk` (payment_check_v4) in a D7 form."""
    return _payment_hit(MV.normalize(text), chk)


def _payment_forms(chk: dict) -> List[str]:
    out = [chk["id"]]
    num = re.search(r"(\d+)$", chk["id"])
    if num:
        out.append(f"4 or more ending digits of the id ('ending in {num.group(1)[-4:]}')")
    if chk.get("last_four"):
        out.append(f"the card's last four {chk['last_four']}" + (f" ({chk['brand']} optional)" if chk.get("brand")
                                                                  else ""))
    out += [f"'{w}'" for w in chk["loose"]]
    if chk.get("original"):
        out.append("'the original payment method'")
    return out


def _payment_expected(chk: dict) -> str:
    src = chk.get("source")
    if src == "credit_card":
        b = f"{chk['brand'].title()}, " if chk.get("brand") else ""
        return f"{chk['id']} ({b}last four {chk.get('last_four')})"
    return chk["id"]


# ----------------------------------------------------------------------------------------------- retail pieces

_STOP = {"the", "and", "for", "with", "set", "kit", "of", "a", "an", "smart", "electric", "digital"}
_ALL_ITEMS = re.compile(r"\b(?:all (?:of )?(?:the |your |my |these |those )?(?:\w+ )?(?:items|products|things)|"
                        r"(?:the |your |my )?(?:whole|entire|full|complete) order|everything(?: in (?:the|your|my) "
                        r"order)?|all of (?:them|it))\b")
_DEFAULT_ADDR = re.compile(r"\b(?:default|profile|primary|usual|saved) (?:shipping |home )?address\b|"
                           r"\baddress (?:on|in|from) (?:your|my|the) (?:profile|account|file)\b|\baddress on file\b")
_SUFFIX = [("avenue", "ave"), ("street", "st"), ("road", "rd"), ("drive", "dr"), ("lane", "ln"),
           ("boulevard", "blvd"), ("court", "ct"), ("place", "pl"), ("terrace", "ter"), ("circle", "cir"),
           ("parkway", "pkwy"), ("highway", "hwy"), ("square", "sq")]
_SUFFIX_ALT = {w: g for g in _SUFFIX for w in g}
_UNIT_WORDS = r"(?:suite|ste\.?|apt\.?|apartment|unit|no\.?|number|#)"
US_STATES = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas", "CA": "california", "CO": "colorado",
    "CT": "connecticut", "DE": "delaware", "DC": "district of columbia", "FL": "florida", "GA": "georgia",
    "HI": "hawaii", "ID": "idaho", "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas",
    "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland", "MA": "massachusetts", "MI": "michigan",
    "MN": "minnesota", "MS": "mississippi", "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada",
    "NH": "new hampshire", "NJ": "new jersey", "NM": "new mexico", "NY": "new york", "NC": "north carolina",
    "ND": "north dakota", "OH": "ohio", "OK": "oklahoma", "OR": "oregon", "PA": "pennsylvania",
    "RI": "rhode island", "SC": "south carolina", "SD": "south dakota", "TN": "tennessee", "TX": "texas",
    "UT": "utah", "VT": "vermont", "VA": "virginia", "WA": "washington", "WV": "west virginia",
    "WI": "wisconsin", "WY": "wyoming"}
REASON_PHRASES = {"no longer needed": re.compile(r"\bno longer need(?:ed|s)?\b"),
                  "ordered by mistake": re.compile(r"\bordered (?:it |them |this |that |these |those )?by mistake\b")}


def reason_phrase_in_v4(text: Any, reason: Any) -> bool:
    """The exact cancel-reason phrase ("no longer need(ed)", "ordered (it) by mistake"; any case) is in the text.
    Other words for the same reason are left to the tiny question K18."""
    norm = MV.normalize(text)
    r = MV.normalize(str(reason or ""))
    rx = REASON_PHRASES.get(r)
    return (rx.search(norm) is not None) if rx is not None else (bool(r) and MV.has_form(norm, r))


def _address1_re(value: str) -> Optional["re.Pattern[str]"]:
    toks = re.findall(r"[a-z0-9]+", MV.normalize(value))
    if not toks:
        return None
    parts = []
    for t in toks:
        g = _SUFFIX_ALT.get(t)
        parts.append(("(?:" + "|".join(g) + r")\.?") if g else re.escape(t))
    return re.compile(r"(?<![a-z0-9_])" + r"[\s,.]+".join(parts) + r"(?![a-z0-9_])")


def _addr_hit(norm: str, plain: str, chk: dict) -> bool:
    f, v = chk["field"], chk["value"]
    if f == "address1":
        rx = _address1_re(v)
        return rx is not None and rx.search(norm) is not None
    if f == "address2":
        num = re.search(r"([a-z]?\d+[a-z]?)\s*$", MV.normalize(v))
        if num is None:
            return MV.has_form(norm, MV.normalize(v))
        n = re.escape(num.group(1))
        if re.search(rf"(?<![a-z0-9_]){_UNIT_WORDS}\s*#?\s*{n}(?![a-z0-9_])", norm):
            return True
        rx1 = _address1_re(chk.get("address1") or "")
        if rx1 is not None:
            for mo in rx1.finditer(norm):
                if re.match(rf"[\s,]+#?\s*{n}(?![a-z0-9_])", norm[mo.end():]):
                    return True
        return False
    if f == "city":
        return MV.has_form(norm, MV.normalize(v))
    if f == "state":
        code = str(v).strip().upper()
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(code)}(?![A-Za-z0-9_])", plain):
            return True
        name = US_STATES.get(code) or MV.normalize(v)
        return MV.has_form(norm, name)
    if f == "zip":
        return bool(_digit_spans(norm, MV.normalize(v))) or MV.has_form(norm, MV.normalize(v))
    return False


def _value_spec(opt: str, value: Any, product: Optional[dict]) -> dict:
    """The check of one option value: whole value; the option name next to it when the value is short (<= 2
    characters), a number, a yes / no word, or used under 2+ option names of the product."""
    vn = MV.normalize(str(value))
    names_with: set = set()
    longer: set = set()
    names = set()
    for var in ((product or {}).get("variants") or {}).values():
        for k, x in (var.get("options") or {}).items():
            names.add(k)
            xn = MV.normalize(str(x))
            if xn == vn:
                names_with.add(k)
            elif k == opt and xn != vn and _spans(xn, vn):
                longer.add(x)
    need = (len(vn) <= 2 or re.fullmatch(r"[\d.]+", vn) is not None or vn in ("yes", "no", "none")
            or len(names_with) >= 2)
    own_words = [w for w in re.findall(r"[a-z]+", MV.normalize(opt)) if len(w) >= 3]
    rivals = (names_with - {opt}) if len(names_with) >= 2 else set()   # other option names that use this value
    other_words = {w for k in rivals for w in re.findall(r"[a-z]+", MV.normalize(k))}
    name_forms = [opt] + [w for w in own_words if w not in other_words and w != MV.normalize(opt)]
    return {"option": opt, "value": str(value), "need_name": bool(need), "names": name_forms,
            "longer": sorted(longer)}


def _value_hit(norm: str, vs: dict) -> bool:
    for s, e in _whole_spans(norm, vs["value"], vs["longer"]):
        if not vs["need_name"] or _near_words(norm, s, e, vs["names"]):
            return True
    return False


def _value_form(vs: dict) -> str:
    return f"{vs['option']} {vs['value']}" if vs["need_name"] else vs["value"]


# ----------------------------------------------------------------------------------------------- line specs

def _need(args: Dict[str, Any], key: str) -> Any:
    if not isinstance(args, dict) or key not in args:
        raise F.MissingArgument(f"the call has no argument [{key!r}]")
    return args[key]


def _get(state: Any, kind: str, oid: Any) -> Optional[dict]:
    if state is None or not isinstance(oid, str):
        return None
    x = state.db_get(kind, oid)
    return x if isinstance(x, dict) else None


def _spec(line: str, expected: str, forms: List[str], chk: dict, **extra: Any) -> dict:
    d = {"line": line, "expected": expected, "forms": forms, "check": chk}
    d.update(extra)
    return d


def _order_line(oid: Any) -> dict:
    s = str(oid)
    bare = s.lstrip("#")
    return _spec("order id", s, [f"#{bare}", bare], {"kind": "order_id", "id": s})


def _reservation_line(rid: Any) -> dict:
    return _spec("reservation id", str(rid), [str(rid)], {"kind": "reservation_id", "id": str(rid)})


def _pay_line(state: Any, label: str, pid: Any, owner: Any, original: Optional[str] = None,
              amount: Any = None) -> dict:
    if not isinstance(pid, str):
        raise TypeError("a payment id is a text")
    chk = payment_check_v4(state, pid, owner, original)
    forms = _payment_forms(chk)
    exp = _payment_expected(chk)
    if amount is not None:
        chk["amount"] = amount
        a = MV._amount_text(amount)
        forms = forms + [f"and the amount ${a}"]
        exp += f", ${a}"
    return _spec(label, exp, forms, chk)


def _order_products(order: Optional[dict]) -> List[dict]:
    return [it for it in (order or {}).get("items") or [] if isinstance(it, dict)]


def _old_item_line(state: Any, iid: Any, order: Optional[dict], call_ids: Sequence[Any], label: str,
                   all_ok: bool = False) -> dict:
    name, opts = Q.item_options(state, iid, order)
    items = _order_products(order)
    mine = next((it for it in items if it.get("item_id") == iid), None)
    pid = mine.get("product_id") if mine else None
    same = [it for it in items if pid is not None and it.get("product_id") == pid]
    taken = sum(1 for x in call_ids if any(it.get("item_id") == x for it in same))
    distinct_needed = len(same) >= 2 and taken < len(same)
    chk: Dict[str, Any] = {"kind": "item_old", "item_id": str(iid), "names": [], "words": [], "distinct": [],
                           "need_distinct": distinct_needed, "all_items": all_ok}
    forms = [f"item {iid}"]
    if distinct_needed:
        prod = _get(state, "product", pid)
        others = [it for it in same if it is not mine]
        for k, v in (opts or {}).items():
            if all((it.get("options") or {}).get(k) != v for it in others):
                vs = _value_spec(k, v, prod)
                chk["distinct"].append(vs)
                forms.append(_value_form(vs) + " (an option only this one has)")
    elif name:
        chk["names"] = [name]
        forms.insert(0, name)
        other_words = {w for it in items if it.get("product_id") != pid
                       for w in re.findall(r"[a-z0-9]+", MV.normalize(it.get("name") or ""))}
        for w in re.findall(r"[a-z0-9]+", MV.normalize(name)):
            if len(w) >= 3 and w not in _STOP and w not in other_words and w != MV.normalize(name):
                chk["words"].append(w)
                forms.append(f"'{w}'")
    if all_ok:
        forms.append("'all the items' (the call returns every item)")
    exp = f"{name} (item {iid})" if name else f"item {iid}"
    return _spec(label, exp, forms, chk)


def _new_item_line(state: Any, old_id: Any, new_id: Any, order: Optional[dict]) -> Optional[dict]:
    oname, oopts = Q.item_options(state, old_id, order)
    var = _get(state, "variant", new_id)
    prod = _get(state, "product", var.get("product_id")) if var else None
    nname = prod.get("name") if prod else None
    nopts = dict(var.get("options") or {}) if var else {}
    chk: Dict[str, Any] = {"kind": "item_new", "item_id": str(new_id), "values": [], "clash": []}
    forms = [f"item {new_id}"]
    exp = f"item {new_id}"
    if var is not None and oname is not None and nname == oname:
        diffs = [(k, a, b) for k, a, b in Q.changed_options(oopts, nopts) if b is not None]
        if not diffs:
            return None                                     # nothing changes: no line
        for k, a, b in diffs:
            vs = _value_spec(k, b, prod)
            chk["values"].append(vs)
            others = {str(x) for v2 in (prod.get("variants") or {}).values()
                      for kk, x in (v2.get("options") or {}).items() if kk == k} - {str(a), str(b)}
            chk["clash"] += [_value_spec(k, x, prod) for x in sorted(others)]
        ch = "; ".join(f"{k} {a} → {b}" for k, a, b in diffs)
        exp = f"the new {oname}: {ch} (or item {new_id})"
        forms.append("every changed option: " + ", ".join(_value_form(v) for v in chk["values"]))
    return _spec(f"new item for {oname or 'item ' + str(old_id)}", exp, forms, chk)


def _address_lines(args: Dict[str, Any], current: Optional[dict], default: Optional[dict]) -> List[dict]:
    new = {k: _need(args, k) for k in ADDRESS_FIELDS}
    cur = current or {}
    same_default = default is not None and all(
        MV.normalize(str(new[k] or "")) == MV.normalize(str(default.get(k) or "")) for k in ADDRESS_FIELDS)
    out = []
    for k in ADDRESS_FIELDS:
        v = new[k]
        if v in (None, ""):
            continue
        if MV.normalize(str(v)) == MV.normalize(str(cur.get(k) or "")):
            continue                                        # this field does not change
        forms = [str(v)]
        if k == "address2":
            forms.append("Suite / Ste / Apt / Unit / # + the number, or the number right after line 1")
        if k == "state":
            forms.append(US_STATES.get(str(v).upper(), str(v)).title())
        if same_default:
            forms.append("'your default address' (the new address is the user's default)")
        out.append(_spec(f"{ADDRESS_LABELS[k]} of the new address", str(v), forms,
                         {"kind": "address", "field": k, "value": str(v), "address1": str(new["address1"]),
                          "default": same_default}))
    return out


def _retail_specs(state: Any, tool: str, args: Dict[str, Any]) -> List[dict]:
    out: List[dict] = []
    if tool == "modify_user_address":
        uid = _need(args, "user_id")
        u = _get(state, "user", uid)
        addr = (u or {}).get("address")
        return _address_lines(args, addr, addr)
    oid = _need(args, "order_id")
    order = _get(state, "order", oid)
    owner = (order or {}).get("user_id")
    hist = (order or {}).get("payment_history") or []
    original = hist[0].get("payment_method_id") if hist and isinstance(hist[0], dict) else None
    out.append(_order_line(oid))
    if tool == "cancel_pending_order":
        reason = _need(args, "reason")
        out.append(_spec("cancel reason", str(reason), [f"'{reason}'", "or the same meaning (tiny question K18)"],
                         {"kind": "reason", "reason": str(reason)}, decided_by="K18"))
    elif tool == "modify_pending_order_address":
        u = _get(state, "user", owner)
        out += _address_lines(args, (order or {}).get("address"), (u or {}).get("address"))
    elif tool == "modify_pending_order_payment":
        out.append(_pay_line(state, "new payment method", _need(args, "payment_method_id"), owner))
    elif tool in ("modify_pending_order_items", "exchange_delivered_order_items"):
        olds, news = list(_need(args, "item_ids") or []), list(_need(args, "new_item_ids") or [])
        pid = _need(args, "payment_method_id")
        for i in range(max(len(olds), len(news))):
            o = olds[i] if i < len(olds) else None
            n = news[i] if i < len(news) else None
            if o is not None:
                out.append(_old_item_line(state, o, order, olds, "item"))
            if n is not None:
                nl = _new_item_line(state, o, n, order)
                if nl is not None:
                    out.append(nl)
        out.append(_pay_line(state, "payment method for the price difference", pid, owner, original))
    elif tool == "return_delivered_order_items":
        ids = list(_need(args, "item_ids") or [])
        pid = _need(args, "payment_method_id")
        every = sorted(str(it.get("item_id")) for it in _order_products(order))
        all_ok = bool(every) and sorted(str(x) for x in ids) == every
        for it in ids:
            out.append(_old_item_line(state, it, order, ids, "returned item", all_ok=all_ok))
        out.append(_pay_line(state, "refund method", pid, owner, original))
    return out


def _flight_line(fl: Any) -> dict:
    if not isinstance(fl, dict):
        raise TypeError("a flight is an object")
    num, date = str(fl.get("flight_number") or ""), str(fl.get("date") or "")
    digits = re.sub(r"^[A-Za-z]+", "", num)
    prefix = num[:len(num) - len(digits)]
    forms = [num] + ([f"{prefix} {digits}", f"flight {digits}"] if digits and prefix else [])
    return _spec("flight", f"{num} on {date}",
                 forms + [f"and its date {date} (any format, the year may be left out)"],
                 {"kind": "flight", "number": num, "date": date})


def _cabin_line(cabin: Any) -> dict:
    c = str(cabin)
    return _spec("cabin", c.replace("_", " "), [c.replace("_", " ")], {"kind": "cabin", "cabin": c})


def _passenger_line(p: Any, with_dob: bool = False) -> dict:
    if not isinstance(p, dict):
        raise TypeError("a passenger is an object")
    first, last, dob = str(p.get("first_name") or ""), str(p.get("last_name") or ""), p.get("dob")
    forms = [f"{first} {last} (first and last name)"]
    exp = f"{first} {last}"
    if with_dob:
        forms.append(f"and the new date of birth {dob} (any format)")
        exp += f", date of birth {dob}"
    return _spec("passenger", exp, forms, {"kind": "passenger", "first": first, "last": last,
                                           "dob": dob if with_dob else None})


def _int(x: Any, what: str) -> int:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise TypeError(f"{what} is not a number")
    return int(x)


def _airline_specs(state: Any, tool: str, args: Dict[str, Any]) -> List[dict]:
    out: List[dict] = []
    if tool == "book_reservation":
        uid = _need(args, "user_id")
        for fl in _need(args, "flights") or []:
            out.append(_flight_line(fl))
        out.append(_cabin_line(_need(args, "cabin")))
        for p in _need(args, "passengers") or []:
            out.append(_passenger_line(p))
        pms = [pm for pm in (_need(args, "payment_methods") or []) if isinstance(pm, dict)]
        for pm in pms:
            out.append(_pay_line(state, "payment method", pm.get("payment_id"), uid,
                                 amount=pm.get("amount") if len(pms) > 1 else None))
        total = _int(_need(args, "total_baggages"), "total_baggages")
        paid = _int(_need(args, "nonfree_baggages"), "nonfree_baggages")
        if total > 0:
            out.append(_spec("checked bags", f"{total} in total", [f"{total} bags"],
                             {"kind": "bags", "values": [total]}))
        if paid > 0:
            out.append(_spec("paid bags", f"{paid} paid (${BAG_FEE * paid})",
                             [f"{paid} paid / extra bags", f"${BAG_FEE * paid}"],
                             {"kind": "paid_bags", "n": paid, "amount": BAG_FEE * paid}))
        ins = args.get("insurance")
        out.append(_spec("travel insurance", {"yes": "added", "no": "not added"}.get(ins, str(ins)),
                         ["the tiny question K17"], {"kind": "question", "qid": "K17"}, decided_by="K17"))
        return out
    if tool == "send_certificate":
        amt = _need(args, "amount")
        a = MV._amount_text(amt)
        out.append(_spec("certificate amount", f"${a}", [f"${a}"], {"kind": "amount", "amount": amt}))
        return out
    rid = _need(args, "reservation_id")
    res = _get(state, "reservation", rid)
    owner = (res or {}).get("user_id")
    hist = (res or {}).get("payment_history") or []
    original = hist[0].get("payment_id") if hist and isinstance(hist[0], dict) else None
    out.append(_reservation_line(rid))
    if tool == "update_reservation_flights":
        cabin = _need(args, "cabin")
        for fl in Q.changed_flights(state, rid, _need(args, "flights")):
            out.append(_flight_line(fl))
        if res is None or cabin != res.get("cabin"):
            out.append(_cabin_line(cabin))
        out.append(_pay_line(state, "payment method", _need(args, "payment_id"), owner, original))
    elif tool == "update_reservation_baggages":
        total = _int(_need(args, "total_baggages"), "total_baggages")
        paid = _int(_need(args, "nonfree_baggages"), "nonfree_baggages")
        db_total = _int((res or {}).get("total_baggages", 0), "total_baggages")
        db_paid = _int((res or {}).get("nonfree_baggages", 0), "nonfree_baggages")
        vals = [total] + ([total - db_total] if total - db_total > 0 else [])
        out.append(_spec("checked bags", f"{total} in total" + (f" ({total - db_total} added)"
                                                                 if total - db_total > 0 else ""),
                         [f"{v} bags" for v in vals], {"kind": "bags", "values": vals}))
        if BAG_FEE * max(0, paid - db_paid) > 0:
            out.append(_pay_line(state, "payment method", _need(args, "payment_id"), owner, original))
    elif tool == "update_reservation_passengers":
        now = [(p.get("first_name"), p.get("last_name")) for p in (res or {}).get("passengers") or []
               if isinstance(p, dict)]
        for p in Q.changed_passengers(state, rid, _need(args, "passengers")):
            same_name = isinstance(p, dict) and (p.get("first_name"), p.get("last_name")) in now
            out.append(_passenger_line(p, with_dob=same_name))
    return out


def line_specs_v4(state: Any, domain: Optional[str], tool: Optional[str], args: Dict[str, Any]) -> List[dict]:
    """One spec per line of the call: {"line", "expected", "forms", "check"} (+ "decided_by" for a line that a
    tiny question decides: the retail cancel reason K18, the airline booking insurance K17). The DB is the state at
    the check. A missing argument raises facts_format_v3.MissingArgument (the fact takes its blocking value)."""
    args = args if isinstance(args, dict) else {}
    if domain == "retail" and tool in RETAIL_WRITES:
        return _retail_specs(state, tool, args)
    if domain == "airline" and tool in AIRLINE_WRITES:
        return _airline_specs(state, tool, args)
    return []


# ----------------------------------------------------------------------------------------------- line check

_ECON = re.compile(r"(?<![a-z0-9_])(?<!basic )(?<!basic-)(?<!basic_)economy(?![a-z0-9_])")
_CABIN_RE = {"basic_economy": re.compile(r"(?<![a-z0-9])basic[\s_-]*economy(?![a-z0-9])"),
             "business": re.compile(r"(?<![a-z0-9_])business(?![a-z0-9_])")}
_PAID_WORDS = re.compile(r"\b(?:paid|extra|non-?free|additional|charged?|fee)\b")


def _flight_hit(norm: str, chk: dict) -> bool:
    num = chk["number"].lower()
    mo = re.match(r"([a-z]+)(\d+)$", num)
    if mo:
        p, d = re.escape(mo.group(1)), re.escape(mo.group(2))
        rx = re.compile(rf"(?<![a-z0-9_]){p}[\s-]?{d}(?![0-9])|\bflight(?:\s+(?:number|no\.?|num\.?))?\s*#?\s*{d}"
                        rf"(?![0-9])")
    else:
        rx = re.compile(rf"(?<![a-z0-9_]){re.escape(num)}(?![a-z0-9_])")
    return rx.search(norm) is not None and MV.text_names_date(norm, chk["date"], without_year=True)


def _cabin_hit(norm: str, cabin: str) -> bool:
    if cabin == "economy":
        return _ECON.search(norm) is not None
    rx = _CABIN_RE.get(cabin)
    if rx is None:
        return MV.has_form(norm, MV.normalize(cabin.replace("_", " ")))
    return rx.search(norm) is not None


def _item_old_hit(norm: str, chk: dict) -> bool:
    if MV.has_form(norm, chk["item_id"]):
        return True
    if chk.get("all_items") and _ALL_ITEMS.search(norm):
        return True
    if chk["need_distinct"]:
        return any(_value_hit(norm, vs) for vs in chk["distinct"])
    for n in chk["names"]:
        body = _flex_body(MV.normalize(n))
        if body and re.search(rf"(?<![a-z0-9_]){body}(?:e?s)?(?![a-z0-9_])", norm):   # "Backpack(s)"
            return True
    for w in chk["words"]:
        if re.search(rf"(?<![a-z0-9_]){re.escape(w)}(?:e?s)?(?![a-z0-9_])", norm) or (
                w.endswith("s") and MV.has_form(norm, w[:-1])):
            return True
    return False


def _check_one(chk: dict, norm: str, plain: str) -> bool:
    k = chk["kind"]
    if k == "order_id":
        return MV.text_has_value(norm, chk["id"])
    if k == "reservation_id":
        return MV.has_form(norm, chk["id"].lower())
    if k == "reason":
        return reason_phrase_in_v4(norm, chk["reason"])
    if k == "address":
        return _addr_hit(norm, plain, chk) or bool(chk.get("default") and _DEFAULT_ADDR.search(norm))
    if k == "payment":
        return _payment_hit(norm, chk)
    if k == "item_old":
        return _item_old_hit(norm, chk)
    if k == "flight":
        return _flight_hit(norm, chk)
    if k == "cabin":
        return _cabin_hit(norm, chk["cabin"])
    if k == "passenger":
        ok = MV.has_form(norm, MV.normalize(chk["first"])) and MV.has_form(norm, MV.normalize(chk["last"]))
        return ok and (chk.get("dob") is None or MV.text_names_date(norm, chk["dob"]))
    if k == "bags":
        return bool(set(chk["values"]) & MV._bag_counts(norm))
    if k == "paid_bags":
        if _amount_in(norm, chk["amount"]) and "$" in norm:
            return True
        return chk["n"] in MV._bag_counts(norm) and _PAID_WORDS.search(norm) is not None
    if k == "amount":
        return _amount_in(norm, chk["amount"])
    return False


def line_present_v4(spec: dict, texts: Iterable[Any]) -> bool:
    """The line is stated in the texts (raw message texts, or (norm, plain) pairs). A single-message line (flight
    number + date, first + last name, a card form) must be in one message; a new item passes on its id in one message,
    or on every changed option value, each found in some message; a payment with an amount needs the method in one
    message and the amount in some message. A line decided by a tiny question (decided_by) is never present here."""
    if spec.get("decided_by"):
        return False
    chk = spec["check"]
    tx = _texts(texts)
    if chk["kind"] == "item_new":
        if any(MV.has_form(n, chk["item_id"]) for n, _ in tx):
            return True
        vals = chk["values"]
        return bool(vals) and all(any(_value_hit(n, vs) for n, _ in tx) for vs in vals)
    hit = any(_check_one(chk, n, p) for n, p in tx)
    if hit and chk["kind"] == "payment" and chk.get("amount") is not None:
        return any(_amount_in(n, chk["amount"]) for n, _ in tx)
    return hit


def option_clashes_v4(spec: dict, texts: Iterable[Any]) -> List[str]:
    """Values of a changed option that are neither the old nor the new value and appear in the texts (log only in
    v4, predicate_table.md: "Clash (log only, not a block)")."""
    chk = spec.get("check") or {}
    if chk.get("kind") != "item_new":
        return []
    tx = _texts(texts)
    return [vs["value"] for vs in chk.get("clash") or [] if any(_value_hit(n, vs) for n, _ in tx)]


# ----------------------------------------------------------------------------------------------- the window

def _view(ctx: Any) -> Any:
    return ctx.need_view()


def _domain(ctx: Any) -> Optional[str]:
    return MV._domain(ctx)


def _state(ctx: Any) -> Any:
    return MV._state(ctx)


def _pending(ctx: Any) -> Tuple[Optional[str], Dict[str, Any]]:
    v = _view(ctx)
    args = getattr(ctx, "args", None)
    return MV._tool(ctx), (args if isinstance(args, dict) else dict(v.pending_args or {}))


def span_refs_v4(ctx: Any) -> List[int]:
    """D2: the refs of the action span S (oldest first)."""
    v = _view(ctx)
    writes = set(WRITES.get(_domain(ctx) or "", ()))
    users = v.user_refs()
    start = -1
    for r in reversed(v.tool_refs()):
        e = v.entries[r]
        if e.ok and e.tool in writes and any(u > r for u in users):
            start = r
            break
    return [e.ref for e in v.entries if e.ref > start]


def _key_detail_hit(ctx: Any, norm: str, tool: str, args: Dict[str, Any]) -> bool:
    """D3: the message names at least one key detail of the call."""
    st = _state(ctx)
    dom = _domain(ctx)
    if dom == "retail":
        if isinstance(args.get("order_id"), str) and MV.text_has_value(norm, args["order_id"]):
            return True
        for k in ("item_ids", "new_item_ids"):
            for iid in args.get(k) or []:
                if not isinstance(iid, str):
                    continue
                if MV.has_form(norm, iid):
                    return True
                var = _get(st, "variant", iid)
                prod = _get(st, "product", var.get("product_id")) if var else None
                if prod and prod.get("name") and _spans(norm, prod["name"]):
                    return True
        for k in ("address1", "zip"):
            if isinstance(args.get(k), str) and args[k] and MV.has_form(norm, MV.normalize(args[k])):
                return True
        pid = args.get("payment_method_id")
        if isinstance(pid, str):
            order = _get(st, "order", args.get("order_id"))
            owner = (order or {}).get("user_id") or args.get("user_id")
            hist = (order or {}).get("payment_history") or []
            orig = hist[0].get("payment_method_id") if hist and isinstance(hist[0], dict) else None
            if _payment_hit(norm, payment_check_v4(st, pid, owner, orig)):
                return True
        return False
    rid = args.get("reservation_id")
    if isinstance(rid, str) and MV.has_form(norm, rid.lower()):
        return True
    for fl in args.get("flights") or []:
        if isinstance(fl, dict):
            if fl.get("flight_number") and MV.has_form(norm, MV.normalize(fl["flight_number"])):
                return True
            if fl.get("date") and MV.text_names_date(norm, fl["date"], without_year=True):
                return True
    for p in args.get("passengers") or []:
        if isinstance(p, dict) and p.get("first_name") and p.get("last_name") and MV.has_form(
                norm, MV.normalize(p["first_name"])) and MV.has_form(norm, MV.normalize(p["last_name"])):
            return True
    if isinstance(args.get("cabin"), str) and _cabin_hit(norm, args["cabin"]):
        return True
    if tool == "update_reservation_baggages" and isinstance(args.get("total_baggages"), int):
        if args["total_baggages"] in MV._bag_counts(norm):
            return True
    res = _get(st, "reservation", rid)
    owner = args.get("user_id") if tool == "book_reservation" else (res or {}).get("user_id")
    pids = ([pm.get("payment_id") for pm in args.get("payment_methods") or [] if isinstance(pm, dict)]
            if tool == "book_reservation" else [args.get("payment_id")])
    for pid in pids:
        if isinstance(pid, str) and _payment_hit(norm, payment_check_v4(st, pid, owner)):
            return True
    return False


def listing_anchors_v4(ctx: Any) -> List[int]:
    """D3: the agent text messages of S that name a key detail of the call and have a user message after them,
    newest first, at most 2."""
    v = _view(ctx)
    tool, args = _pending(ctx)
    span = span_refs_v4(ctx)
    users = [r for r in v.user_refs()]
    out = []
    for r in reversed(span):
        if v.role(r) != "agent" or not any(u > r for u in users):
            continue
        if _key_detail_hit(ctx, v.norm(r), tool, args):
            out.append(r)
            if len(out) >= ANCHOR_LIMIT:
                break
    return out


def listing_window_v4(ctx: Any) -> List[int]:
    """D5: the listing text T = every agent text message in S, plus the anchor L, plus every user message in S;
    refs newest first."""
    v = _view(ctx)
    span = span_refs_v4(ctx)
    refs = {r for r in span if v.role(r) in ("agent", "user")}
    refs |= set(listing_anchors_v4(ctx)[:1])
    return sorted(refs, reverse=True)


_ORDER_TOKEN = re.compile(r"(?<![a-z0-9_])#?w\d{7}(?![a-z0-9_])")


def _newest_named_object(ctx: Any) -> Optional[str]:
    """D6: the newest order id (retail) or reservation id (airline) named in a user or agent text message: the last
    one named in the newest message that names any (a reservation id only if it is in the database)."""
    v = _view(ctx)
    st = _state(ctx)
    dom = _domain(ctx)
    for r in reversed([e.ref for e in v.entries if e.role in ("user", "agent")]):
        norm = v.norm(r)
        if dom == "retail":
            ids = ["#" + x.lstrip("#").upper() for x in _ORDER_TOKEN.findall(norm)]
        else:
            ids = [t.upper() for t in MV._RES6.findall(norm) if _get(st, "reservation", t.upper()) is not None]
        if ids:
            return ids[-1]
    return None


def _object_passes_d6(ctx: Any, spec: dict) -> bool:
    k = spec["check"]["kind"]
    if k not in ("order_id", "reservation_id"):
        return False
    want = spec["check"]["id"]
    got = _newest_named_object(ctx)
    if got is None:
        return False
    if k == "order_id":
        return got.lstrip("#").upper() == want.lstrip("#").upper()
    return got.upper() == want.upper()


def _record(ctx: Any, spec: dict) -> dict:
    return {"line": spec["line"], "expected": spec["expected"], "forms": list(spec["forms"]),
            "fact": getattr(ctx, "fact", None), "part": getattr(ctx, "part_id", None)}


def _specs_of(ctx: Any) -> List[dict]:
    tool, args = _pending(ctx)
    return line_specs_v4(_state(ctx), _domain(ctx), tool, args)


def _window_texts(ctx: Any) -> List[Tuple[str, str]]:
    v = _view(ctx)
    return [(v.norm(r), v.plain(r)) for r in listing_window_v4(ctx)]


def listing_missing_v4(ctx: Any, note: bool = True) -> List[dict]:
    """The missing records of the call's code lines (lines decided by a tiny question are left out), checked over
    T (D5); the object line also passes by D6. Noted as {"missing": [records]} when some line is missing; an option
    clash of a new item is noted as {"option_clash": ...} (log only)."""
    specs = _specs_of(ctx)
    tx = _window_texts(ctx)
    missing = []
    clashes = []
    for sp in specs:
        if sp.get("decided_by"):
            continue
        if line_present_v4(sp, tx) or _object_passes_d6(ctx, sp):
            ok = True
        else:
            ok = False
            missing.append(_record(ctx, sp))
        if ok:
            c = option_clashes_v4(sp, tx)
            if c:
                clashes.append({"line": sp["line"], "expected": sp["expected"], "also_named": c})
    if note and missing:
        ctx.note({"missing": missing})
    if note and clashes:
        ctx.note({"option_clash": clashes})
    return missing


# ----------------------------------------------------------------------------------------------- helpers

def h_listing_window_v4(ctx: Any) -> List[int]:
    """D5 listing text T (refs, newest first)."""
    return listing_window_v4(ctx)


def h_listing_anchors_v4(ctx: Any) -> List[int]:
    """D3 anchor candidates L (refs, newest first, at most 2)."""
    return listing_anchors_v4(ctx)


def h_listing_ok_v4(ctx: Any) -> bool:
    """Every code line of the pending call is stated in T (D5) (the object also by D6)."""
    return not listing_missing_v4(ctx)


def h_listing_missing_count_v4(ctx: Any) -> int:
    """How many code lines of the pending call are missing from T."""
    return len(listing_missing_v4(ctx))


def h_listing_reason_ok_v4(ctx: Any) -> bool:
    """retail cancel_pending_order: the exact reason phrase is in a message of T (true for every other call). When it
    is not, the missing reason is noted and the tiny question K18 decides (listing_reason_candidates_v4)."""
    tool, args = _pending(ctx)
    if _domain(ctx) != "retail" or tool != "cancel_pending_order":
        return True
    reason = _need(args, "reason")
    v = _view(ctx)
    if any(reason_phrase_in_v4(v.norm(r), reason) for r in listing_window_v4(ctx)):
        return True
    sp = next(s for s in _specs_of(ctx) if s["check"]["kind"] == "reason")
    ctx.note({"missing": [_record(ctx, sp)]})
    return False


def h_listing_reason_candidates_v4(ctx: Any) -> List[int]:
    """K18's messages: the messages of T (agent and user), newest first, at most 4 ([] for a call that is not a
    retail cancel)."""
    tool, _ = _pending(ctx)
    if _domain(ctx) != "retail" or tool != "cancel_pending_order":
        return []
    return listing_window_v4(ctx)[:REASON_LIMIT]


HELPERS: Dict[str, tuple] = {
    "listing_window_v4": (h_listing_window_v4, 0, 0, ()),
    "listing_anchors_v4": (h_listing_anchors_v4, 0, 0, ()),
    "listing_ok_v4": (h_listing_ok_v4, 0, 0, ()),
    "listing_missing_count_v4": (h_listing_missing_count_v4, 0, 0, ()),
    "listing_reason_ok_v4": (h_listing_reason_ok_v4, 0, 0, ()),
    "listing_reason_candidates_v4": (h_listing_reason_candidates_v4, 0, 0, ()),
}


def register_helpers_v4() -> List[str]:
    """Register the listing helpers (idempotent)."""
    for name, (func, lo, hi, kws) in HELPERS.items():
        F.register_name(name, func, lo, hi, kws, source=SOURCE, doc=(func.__doc__ or "").strip().split("\n")[0])
    return sorted(HELPERS)


register_helpers_v4()
