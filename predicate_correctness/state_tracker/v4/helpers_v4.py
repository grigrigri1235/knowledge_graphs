"""Tracker v4: the code-fact helpers of build agent A5.

The idea in plain words: where v3 asked a tiny question about something code can know, v4 lets code decide.
  - Ownership: does the agent's reply name another database user (full name or email)? (Kept as a tool, but
    NOT used by any v4 fact: the main chat decided, per predicate_table.md, that
    response_performs_task_for_another_user is v3's part a alone.)
  - K4's gate: ask K4 at a login or a catalog read only when code sees a reason (a relation word, or login values
    the user did not type).
  - K15 as code: did the user (or the listing L) name the airports and the trip type, does L name every flight,
    and do the booked flights fit the trip (type, origin, destination)?
  - The K12 offer kind from the database: did the user's named reservations have a cancelled or a delayed flight?
    (offer_db_kinds_v4 gives questions_v4.offer_kind_v4 its db_kinds.)
  - The two code paths of the transfer facts: the retail user cannot be found; the airline user already tried to
    cancel a reservation with a used flight.
  - K13's window (fix round 2): each user message with the agent's text message just before it.

Every helper is a plain function f(ctx, *args) and is registered on import with facts_format_v3.register_name(...,
source="structure"), so structure and question parts may call it. Every name ends in "_v4" (the helper registry is
shared with v3). The K1 go-ahead helpers are in helpers_go_ahead_v4.py (agent A2), not here.

Rules (as v3's message_view): value matching on the normalized text, whole tokens; database reads through ctx.state
(recorded), or through the start-of-conversation database copy for fields no tool changes (user names and emails);
a missing argument goes through ctx.arg (the fact takes its blocking value); a nonexistent object raises
facts_format_v3.MissingObject (the part takes its if_nonexistent value, default false). Evidence notes never hold
another user's value (only its kind).

Standard library only. No LLM call, no network. Never imports gold code or a scoring module.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from state_tracker.v3 import facts_format_v3 as F
from state_tracker.v3 import info_classes as IC
from state_tracker.v3 import message_view as MV

SOURCE = "structure"
TRANSFER_TOOL = "transfer_to_human_agents"
OTHER_PERSON_SCREEN = "other_person"          # v3's word list; 0 misses in its blind sets (K4 kept its screen)
MIN_FAILED_LOGINS = 2                          # retail "user not found": at least this many failed find calls


# ----------------------------------------------------------------------------------------------- ownership (K5)

_USER_FORMS: Dict[str, List[Tuple[str, str, str]]] = {}


def _user_forms(domain: str) -> List[Tuple[str, str, str]]:
    """(user id, normalized full name "first last", normalized email) of every user at the start of a conversation.
    Names and emails are never changed by a tool in either domain, so the start copy is the database at any check."""
    if domain not in _USER_FORMS:
        out = []
        for uid, u in (MV._initial_db(domain).get("users") or {}).items():
            if not isinstance(u, dict):
                continue
            name = u.get("name") or {}
            full = MV.normalize(f"{name.get('first_name') or ''} {name.get('last_name') or ''}")
            email = MV.normalize(u.get("email") or "")
            out.append((uid, full if " " in full else "", email))
        _USER_FORMS[domain] = out
    return _USER_FORMS[domain]


def _own_output_norms(v: MV.MessageView, who: str) -> List[str]:
    """The normalized texts of worked data tool outputs that belong to `who` (what the agent read about this user)."""
    out = []
    for r in v.data_tool_refs():
        e = v.entries[r]
        try:
            data = json.loads(e.text)
        except (TypeError, ValueError):
            data = None
        if IC._output_owner(e, data) == who:
            out.append(e.norm)
    return out


def reply_names_other_db_user_v4(ctx: Any) -> bool:
    """The pending reply holds the full name ("first last") or the email of a database user other than the logged-in
    user me() that no user message holds (replaces K5).

    Not counted: the logged-in user's own full name or email (and any user who shares that full name: the retail data
    has many repeated names), a value that a user message holds (the user said it first), a value that a worked tool
    output about me() showed, a first or a last name alone. False while me() is None (before the login) and when the
    pending call is not a reply. The evidence note gives only the kind ("name" / "email"), never the value."""
    v = MV._view(ctx)
    if v.pending_tool != "respond":
        return False
    who = MV.me(ctx)
    if who is None:
        return False
    domain = MV._domain(ctx) or "retail"
    forms = _user_forms(domain)
    mine = next(((n, e) for uid, n, e in forms if uid == who), ("", ""))
    reply = v.norm(v.pending_ref)
    users = [v.norm(r) for r in v.user_refs()]
    own = None
    kinds: List[str] = []
    for uid, full, email in forms:
        if uid == who:
            continue
        for kind, form in (("name", full), ("email", email)):
            if not form or form in mine or not MV.has_form(reply, form):
                continue
            if any(MV.has_form(u, form) for u in users):
                continue
            if own is None:
                own = _own_output_norms(v, who)
            if any(MV.has_form(o, form) for o in own):
                continue
            kinds.append(kind)
    if kinds:
        ctx.note({"other_db_user": [{"kind": k} for k in sorted(set(kinds))]})
    return bool(kinds)


# ----------------------------------------------------------------------------------------------- K4's gate

def _identity_values(ctx: Any, tool: str) -> List[Any]:
    if tool == "find_user_id_by_email":
        return [ctx.arg("email")]
    return [ctx.arg("first_name"), ctx.arg("last_name"), ctx.arg("zip")]


def other_person_precondition_v4(ctx: Any) -> bool:
    """K4's gate (retail request_is_for_another_user part b): code says there is a reason to ask whether the user is
    acting for another person. True only in these two cases:

      1. First login: the pending call is find_user_id_by_email / find_user_id_by_name_zip and me() is not set yet,
         and (a) at least one of the call's identity values (the email; or the first name, the last name, the zip) is
         in no user message before the call (user_typed false: the values came from somewhere else), or (b) a user
         message before the call hits the 'other_person' word list (a relation or a third person: wife, husband,
         son, mom, friend, colleague, "for my", "on behalf", his / her, "not my account", ...; v3's list, 0 misses
         in its blind sets).
      2. Catalog read: the pending call is get_product_details / list_all_product_types and the latest user message
         hits the 'other_person' word list (v3's rule).

    Every other call: false (the database owner, part a, decides every call with an object; a login after me() is
    set is part a's case too). A missing identity argument: the fact's blocking value (ctx.arg). The word list only
    decides whether K4 is asked; K4 (part c, on another_user_pick()) decides the value. When only 1(a) fires and no
    user message holds any identity value, part c has no message and is false; rules 1-2 (the identity was given by
    the user) still block such a login."""
    v = MV._view(ctx)
    tool = MV._tool(ctx)
    if tool in MV.FIND_TOOLS:
        if MV.me(ctx) is not None:
            return False
        vals = _identity_values(ctx, tool)
        untyped = [x for x in vals if x is None or not MV.user_typed(ctx, x)]
        relation = [r for r in v.user_refs() if MV._ref_hit(ctx, OTHER_PERSON_SCREEN, r)]
        if untyped or relation:
            ctx.note({"k4_gate": "login", "untyped_values": len(untyped), "relation_messages": len(relation)})
        return bool(untyped or relation)
    if tool in MV.CATALOG_TOOLS_RETAIL:
        us = v.user_refs()
        hit = bool(us) and MV._ref_hit(ctx, OTHER_PERSON_SCREEN, us[-1])
        if hit:
            ctx.note({"k4_gate": "catalog read", "relation_messages": 1})
        return hit
    return False


# ----------------------------------------------------------------------------------------------- K15 as code

# Metro names (predicate_table.md, booking_required_information_established): short names in upper case are matched
# case-sensitively on the plain text (so "la" or "ny" inside a sentence do not count); the others case-insensitively.
METRO_UPPER: Dict[str, Tuple[str, ...]] = {
    "NYC": ("JFK", "LGA", "EWR"), "NY": ("JFK", "LGA", "EWR"), "LA": ("LAX",), "SF": ("SFO",),
}
METRO_WORDS: Dict[str, Tuple[str, ...]] = {
    "new york": ("JFK", "LGA", "EWR"), "new york city": ("JFK", "LGA", "EWR"), "nyc": ("JFK", "LGA", "EWR"),
    "la guardia": ("LGA",),
    "san fran": ("SFO",), "vegas": ("LAS",), "philly": ("PHL",), "chi-town": ("ORD",), "chitown": ("ORD",),
    "twin cities": ("MSP",),
}


def airport_forms_v4(code: str) -> Tuple[List[str], List[str]]:
    """(case-sensitive forms, normalized forms) that name the airport `code`: the IATA code in upper case, the
    city of list_all_airports, and the metro names above."""
    c = code.strip().upper()
    upper = [c] + [k for k, codes in METRO_UPPER.items() if c in codes]
    words = []
    city = MV._airports(None).get(c)
    if city:
        words.append(MV.normalize(city))
    words += [k for k, codes in METRO_WORDS.items() if c in codes]
    return upper, list(dict.fromkeys(words))


def _names_airport_v4(v: MV.MessageView, ref: int, code: Any) -> bool:
    if not isinstance(code, str) or not code.strip():
        return False
    upper, words = airport_forms_v4(code)
    plain = v.plain(ref)
    if any(MV._form_re(u, case=True).search(plain) for u in upper):
        return True
    nt = v.norm(ref)
    return any(MV.has_form(nt, w) for w in words)


def user_named_airport_v4(ctx: Any, code: Any) -> bool:
    """A user message before the call names the airport `code`: its IATA code written in upper case ("JFK"), its city
    from list_all_airports (any case: "dallas"), or a metro name (NYC / NY / New York for JFK, LGA and EWR; LA for LAX;
    SF / San Fran for SFO; Vegas for LAS; Philly for PHL; Chi-town for ORD; Twin Cities for MSP; La Guardia for LGA).
    A code that is not a text: false."""
    v = MV._view(ctx)
    return any(_names_airport_v4(v, r, code) for r in v.user_refs())


def _anchor_refs(anchors: Any) -> List[int]:
    if anchors is None:
        return []
    if not isinstance(anchors, (list, tuple)) or not all(isinstance(r, int) and not isinstance(r, bool)
                                                          for r in anchors):
        raise TypeError("anchors must be a list of message refs")
    return list(anchors)


def anchor_names_route_v4(ctx: Any, anchors: Any) -> bool:
    """One of the listing anchors L (message refs, e.g. go_ahead_anchors_v4(): D3, newest first, at most 2) names
    both the call's origin and its destination, in the forms of user_named_airport_v4 (upper-case code, city, metro
    name)."""
    v = MV._view(ctx)
    o, d = ctx.arg("origin"), ctx.arg("destination")
    return any(_names_airport_v4(v, r, o) and _names_airport_v4(v, r, d) for r in _anchor_refs(anchors))


TRIP_PHRASES = {
    "one_way": re.compile(r"(?<![a-z0-9])one[\s-]?way(?![a-z0-9])"),
    "round_trip": re.compile(r"(?<![a-z0-9])(?:round[\s-]?trip|return (?:trip|flight))(?![a-z0-9])"),
}


def trip_type_stated_v4(ctx: Any, anchors: Any) -> bool:
    """A phrase of the call's flight_type is in a user message before the call or in one of the anchors L:
    one_way: "one way", "one-way", "oneway"; round_trip: "round trip", "round-trip", "roundtrip", "return trip",
    "return flight" (any case). Another flight_type: false."""
    rx = TRIP_PHRASES.get(ctx.arg("flight_type"))
    if rx is None:
        return False
    v = MV._view(ctx)
    return any(rx.search(v.norm(r)) for r in v.user_refs() + _anchor_refs(anchors))


def anchor_names_flights_v4(ctx: Any, anchors: Any) -> bool:
    """One of the anchors L names every flight of the call: each flight number ("HAT170", "HAT 170", "flight 170")
    with its date (any format, the year may be left out) in that one message (listing_v4's flight line check). A call
    with no flights: false."""
    from state_tracker.v4 import listing_v4 as LV          # agent A1's line check (imported when first needed)
    v = MV._view(ctx)
    flights = ctx.arg("flights")
    if not isinstance(flights, list) or not flights:
        return False
    specs = [LV._flight_line(f) for f in flights]
    return any(all(LV.line_present_v4(s, [v.text(r)]) for s in specs) for r in _anchor_refs(anchors))


def _chain(legs: Sequence[dict], start: str, end: str) -> bool:
    if not legs or legs[0]["origin"] != start or legs[-1]["destination"] != end:
        return False
    return all(a["destination"] == b["origin"] for a, b in zip(legs, legs[1:]))


def trip_fits_v4(ctx: Any) -> bool:
    """The pending book_reservation's flights fit its flight_type, origin and destination in the flights table.

    The legs are the call's flights (each flight number's origin and destination in the database), in travel order
    (by date, then scheduled departure time). one_way: the legs form one chain origin -> ... -> destination (each leg
    leaves where the one before arrived). round_trip: the legs split into an outbound chain origin -> destination and
    a return chain destination -> origin. Any other flight_type, or no flights: false. A flight number that is not in
    the database: the part's if_nonexistent value (false). A flight entry that is not an object with a flight number
    and a date: a type error (the fact's blocking value)."""
    origin, dest, ftype = ctx.arg("origin"), ctx.arg("destination"), ctx.arg("flight_type")
    flights = ctx.arg("flights")
    if not isinstance(flights, list):
        raise TypeError("flights is not a list")
    legs = []
    for f in flights:
        if not isinstance(f, dict) or not isinstance(f.get("flight_number"), str) or not isinstance(f.get("date"), str):
            raise TypeError("a flight entry needs a flight_number and a date")
        row = MV._must(MV._db(ctx, "flight", f["flight_number"]), f"flight {f['flight_number']!r}")
        legs.append({"origin": row["origin"], "destination": row["destination"],
                     "key": (f["date"], str(row.get("scheduled_departure_time_est") or ""))})
    legs.sort(key=lambda x: x["key"])
    if not legs or ftype not in ("one_way", "round_trip"):
        ok = False
    elif ftype == "one_way":
        ok = _chain(legs, origin, dest)
    else:
        ok = any(_chain(legs[:k], origin, dest) and _chain(legs[k:], dest, origin) for k in range(1, len(legs)))
    if not ok:
        ctx.note({"trip_fits": False, "flight_type": ftype, "origin": origin, "destination": dest,
                  "legs": [[x["origin"], x["destination"]] for x in legs]})
    return ok


# ----------------------------------------------------------------------------------------------- the K12 offer kind

KINDS = ("cancelled", "delayed")


def offer_db_kinds_v4(ctx: Any) -> List[str]:
    """The kinds of flight problem the database shows for the user's named reservations (K12v4's offer kind, given
    to questions_v4.offer_kind_v4 as db_kinds): the reservations named in the conversation of the obtained user ids
    (named_reservations(obtained_user_ids())), first only the eligible ones (silver / gold owner, insurance 'yes', or
    business cabin: eligible_for_compensation), and when none of those had a cancelled or a delayed flight, all of
    them. Returns the sorted kinds among 'cancelled' and 'delayed' that had_flight_status finds (a flight that was
    replaced later still counts): ['cancelled'], ['delayed'], both, or []. With both or none, offer_kind_v4 falls
    back to K12's quote words."""
    res = MV.named_reservations(ctx, MV.obtained_user_ids(ctx))
    kinds: List[str] = []
    for group in (MV.eligible_for_compensation(ctx, res, ["silver", "gold"]), res):
        kinds = [k for k in KINDS if MV.had_flight_status(ctx, group, k)]
        if kinds:
            break
    ctx.note({"offer_db_kinds": kinds, "named_reservations": len(res)})
    return kinds


# ----------------------------------------------------------------------------------------------- transfer code paths

def user_not_found_v4(ctx: Any) -> bool:
    """Retail: the user cannot be found, so no request is within scope. At least MIN_FAILED_LOGINS (2)
    find_user_id_by_email / find_user_id_by_name_zip calls ran before the check, every one failed (its output starts
    with 'Error'), and none worked. Guard-blocked calls are not in the executed history and do not count."""
    v = MV._view(ctx)
    finds = [v.entries[r] for r in v.tool_refs() if v.entries[r].tool in MV.FIND_TOOLS]
    hit = len(finds) >= MIN_FAILED_LOGINS and not any(e.ok for e in finds)
    if hit:
        ctx.note({"user_not_found": len(finds)})
    return hit


def cancel_attempted_v4(ctx: Any, res_ids: Any) -> bool:
    """Airline S41's case, code part: a cancel_reservation call on one of `res_ids` ran before the check, worked or
    failed (the user asked to cancel and the agent tried). Guard-blocked calls are not in the executed history and do
    not count (the guard's transfer escape covers repeated blocks)."""
    ids = set(MV._id_list(res_ids))
    v = MV._view(ctx)
    hit = any(v.entries[r].tool == "cancel_reservation" and v.entries[r].args.get("reservation_id") in ids
              for r in v.tool_refs())
    if hit:
        ctx.note({"cancel_attempted": True})
    return hit


def user_messages_with_agent_before_v4(ctx: Any) -> List[Any]:
    """K13 v5's window (fix round 2): every user message, newest first, each with the agent's text message just
    before it. A candidate is [user ref, agent ref] when an agent text message lies between the previous user message
    (or the start) and this one (the newest such message), else the user ref alone. Same user messages and order
    as v3's user_messages(); the agent message is context only (K13 quotes from the user message)."""
    v = MV._view(ctx)
    users = list(v.user_refs())
    agents = list(v.agent_refs())
    out: List[Any] = []
    for i, u in enumerate(users):
        lo = users[i - 1] if i > 0 else -1
        before = [a for a in agents if lo < a < u and (v.text(a) or "").strip()]
        out.append([u, before[-1]] if before else u)
    return list(reversed(out))


# ----------------------------------------------------------------------------------------------- registration

# name -> (function, min positional, max positional, keywords, source)
HELPERS_V4: Dict[str, tuple] = {
    "reply_names_other_db_user_v4": (reply_names_other_db_user_v4, 0, 0, (), SOURCE),
    "other_person_precondition_v4": (other_person_precondition_v4, 0, 0, (), SOURCE),
    "user_named_airport_v4": (user_named_airport_v4, 1, 1, (), SOURCE),
    "trip_fits_v4": (trip_fits_v4, 0, 0, (), SOURCE),
    "anchor_names_route_v4": (anchor_names_route_v4, 1, 1, (), SOURCE),
    "trip_type_stated_v4": (trip_type_stated_v4, 1, 1, (), SOURCE),
    "anchor_names_flights_v4": (anchor_names_flights_v4, 1, 1, (), SOURCE),
    "offer_db_kinds_v4": (offer_db_kinds_v4, 0, 0, (), SOURCE),
    "user_not_found_v4": (user_not_found_v4, 0, 0, (), SOURCE),
    "cancel_attempted_v4": (cancel_attempted_v4, 1, 1, (), SOURCE),
    "user_messages_with_agent_before_v4": (user_messages_with_agent_before_v4, 0, 0, (), SOURCE),
}


def register_helpers_v4() -> List[str]:
    """Register every helper of this module (idempotent: the same helper twice changes nothing)."""
    for name, (func, lo, hi, kws, src) in HELPERS_V4.items():
        F.register_name(name, func, lo, hi, kws, source=src, doc=(func.__doc__ or "").strip().split("\n")[0])
    return list(HELPERS_V4)


register_helpers_v4()
