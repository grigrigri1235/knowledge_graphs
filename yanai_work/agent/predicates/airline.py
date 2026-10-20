"""Deterministic predicates (state / tool_log / structural) for the τ-bench v1 airline ASPM.

Specs: policies/predicates/airline_predicates.json. Signature of every predicate:
    (tool_call: dict, trajectory: list, config: dict) -> bool | None
None means the trajectory does not contain enough information to decide.
"""
from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Optional

from agent.predicates.context import (
    authenticated_user_ids, call_args, call_name, config_now, flight_date_info, flight_endpoints,
    latest_object, parse_timestamp, payment_source, reservation_in_focus, single_tool_call_in_turn,
    successful_calls, text_with_tool_call, tool_events, user_mentioned_id, with_effective_cabin,
)

DOMAIN = "airline"
FREE_BAGS = {  # wiki AIR-BOOK-04a..c: per passenger, by tier of the BOOKING user and cabin
    "regular": {"basic_economy": 0, "economy": 1, "business": 2},
    "silver": {"basic_economy": 1, "economy": 2, "business": 3},
    "gold": {"basic_economy": 2, "economy": 3, "business": 3},
}
EXTRA_BAG_FEE = 50          # AIR-BOOK-04d
INSURANCE_FEE = 30          # AIR-BOOK-05b


# ---------------------------------------------------------------------------------------------- helpers
def _args(tc):
    return call_args(tc)


def _reservation(tc, traj) -> Optional[dict]:
    """Latest reservation object for args.reservation_id, with the effective cabin (see context.with_effective_cabin)."""
    return with_effective_cabin(traj, latest_object(traj, "reservation", _args(tc).get("reservation_id")))


def _booking_user(tc, traj) -> Optional[dict]:
    """User record of the booking user: args.user_id (book / send_certificate) or the reservation owner."""
    a = _args(tc)
    uid = a.get("user_id")
    if uid is None:
        res = _reservation(tc, traj)
        uid = res.get("user_id") if res else None
    return latest_object(traj, "user", uid) if uid else None


def _segments(flights) -> Counter:
    return Counter((f.get("flight_number"), f.get("date")) for f in flights or [] if isinstance(f, dict))


def _new_segments(tc, traj):
    """Segments of the call that are newly booked: all for book_reservation; for update_reservation_flights
    those not already in the current reservation. None if the reservation is unknown."""
    a = _args(tc)
    flights = [f for f in a.get("flights") or [] if isinstance(f, dict)]
    if call_name(tc) == "book_reservation":
        return flights
    res = _reservation(tc, traj)
    if res is None:
        return None
    old = _segments(res.get("flights"))
    out = []
    for f in flights:
        key = (f.get("flight_number"), f.get("date"))
        if old[key] > 0:
            old[key] -= 1
        else:
            out.append(f)
    return out


def _tier_is(tc, traj, tier) -> Optional[bool]:
    user = _booking_user(tc, traj)
    if user is None or "membership" not in user:
        return None
    return user["membership"] == tier


def _ordered_endpoints(tc, traj):
    """[(origin, destination)] of the call's flights sorted by date; None if any endpoint is unknown."""
    flights = sorted((f for f in _args(tc).get("flights") or [] if isinstance(f, dict)), key=lambda f: f.get("date") or "")
    ends = []
    for f in flights:
        e = flight_endpoints(traj, f.get("flight_number"))
        if e is None:
            return None
        ends.append(e)
    return ends


# ---------------------------------------------------------------------------------------------- book
def all_new_flights_available(tc, traj, config):
    """AIR-R010: every newly booked (flight_number, date) was seen in a search result with status 'available'."""
    segs = _new_segments(tc, traj)
    if segs is None:
        return None
    for f in segs:
        info = flight_date_info(traj, f.get("flight_number"), f.get("date"))
        if info is None:
            return None
        if info.get("status") != "available":
            return False
    return True


def passenger_count_at_most_five(tc, traj, config):
    p = _args(tc).get("passengers")
    return None if not isinstance(p, list) else len(p) <= 5


def all_passengers_have_name_and_dob(tc, traj, config):
    p = _args(tc).get("passengers")
    if not isinstance(p, list):
        return None
    return all(isinstance(x, dict) and all(isinstance(x.get(k), str) and x.get(k).strip() for k in ("first_name", "last_name", "dob")) for x in p)


def passengers_share_flights_and_cabin(tc, traj, config):
    """AIR-R015: the call has one cabin and one flight list for all passengers (guaranteed by the schema)."""
    a = _args(tc)
    return isinstance(a.get("cabin"), str) and isinstance(a.get("flights"), list)


def _count_source(tc, traj, source):
    user = latest_object(traj, "user", _args(tc).get("user_id"))
    pms = _args(tc).get("payment_methods")
    if not isinstance(pms, list):
        return None
    srcs = [payment_source(p.get("payment_id"), user) for p in pms if isinstance(p, dict)]
    if any(s is None for s in srcs):
        return None
    return srcs.count(source)


def certificate_count_at_most_one(tc, traj, config):
    n = _count_source(tc, traj, "certificate")
    return None if n is None else n <= 1


def credit_card_count_at_most_one(tc, traj, config):
    n = _count_source(tc, traj, "credit_card")
    return None if n is None else n <= 1


def gift_card_count_at_most_three(tc, traj, config):
    n = _count_source(tc, traj, "gift_card")
    return None if n is None else n <= 3


def payment_methods_in_user_profile(tc, traj, config):
    user = latest_object(traj, "user", _args(tc).get("user_id"))
    pms = _args(tc).get("payment_methods")
    if user is None or not isinstance(pms, list):
        return None
    return all(isinstance(p, dict) and p.get("payment_id") in (user.get("payment_methods") or {}) for p in pms)


def booking_user_is_regular(tc, traj, config):
    return _tier_is(tc, traj, "regular")


def booking_user_is_silver(tc, traj, config):
    return _tier_is(tc, traj, "silver")


def booking_user_is_gold(tc, traj, config):
    return _tier_is(tc, traj, "gold")


def nonfree_baggages_match_tier_allowance(tc, traj, config):
    """AIR-R020..R022: nonfree_baggages == max(0, total_baggages - n_passengers x allowance(tier, cabin)).
    book_reservation: cabin and passengers from the args; update_reservation_baggages: from the reservation."""
    a = _args(tc)
    user = _booking_user(tc, traj)
    if user is None or user.get("membership") not in FREE_BAGS:
        return None
    if call_name(tc) == "book_reservation":
        cabin, n = a.get("cabin"), len(a.get("passengers") or [])
    else:
        res = _reservation(tc, traj)
        if res is None:
            return None
        cabin, n = res.get("cabin"), len(res.get("passengers") or [])
    total, nonfree = a.get("total_baggages"), a.get("nonfree_baggages")
    if cabin not in FREE_BAGS["regular"] or not isinstance(total, int) or not isinstance(nonfree, int):
        return None
    return nonfree == max(0, total - n * FREE_BAGS[user["membership"]][cabin])


def insurance_purchased(tc, traj, config):
    ins = _args(tc).get("insurance")
    return None if ins not in ("yes", "no") else ins == "yes"


def payment_total_matches_price(tc, traj, config):
    """AIR-R023/R025: sum of payment amounts == sum(segment price for cabin) x n + 30 x n (insured) + 50 x nonfree.
    Segment prices come from the latest search result for (flight_number, date)."""
    a = _args(tc)
    cabin, pax, pms = a.get("cabin"), a.get("passengers"), a.get("payment_methods")
    if not isinstance(pax, list) or not isinstance(pms, list) or a.get("insurance") not in ("yes", "no"):
        return None
    n = len(pax)
    total = 0.0
    for f in a.get("flights") or []:
        info = flight_date_info(traj, f.get("flight_number"), f.get("date"))
        price = (info or {}).get("prices", {}).get(cabin)
        if price is None:
            return None
        total += price * n
    total += INSURANCE_FEE * n if a["insurance"] == "yes" else 0
    total += EXTRA_BAG_FEE * (a.get("nonfree_baggages") or 0)
    paid = sum(p.get("amount", 0) for p in pms if isinstance(p, dict))
    return abs(paid - total) < 0.01


# ---------------------------------------------------------------------------------------------- existing reservation
def reservation_owner_identified(tc, traj, config):
    """AIR-R026/R039: the reservation owner's user id was obtained: a get_user_details call for it succeeded,
    or the user wrote that exact user id in a message."""
    res = _reservation(tc, traj)
    if res is None:
        return None
    uid = res.get("user_id")
    return uid in authenticated_user_ids(traj, DOMAIN) or user_mentioned_id(traj, uid)


def reservation_details_retrieved(tc, traj, config):
    """AIR-R027/R040: get_reservation_details succeeded earlier for args.reservation_id."""
    rid = _args(tc).get("reservation_id")
    return any(e.args.get("reservation_id") == rid for e in successful_calls(traj, "get_reservation_details"))


def cabin_is_business(tc, traj, config):
    res = _reservation(tc, traj)
    return None if res is None or "cabin" not in res else res["cabin"] == "business"


def booked_within_24h(tc, traj, config):
    """AIR-R042: 0 <= now - created_at <= 24h, with now = config.current_time (inclusive boundary)."""
    res = _reservation(tc, traj)
    now = config_now(config)
    created = parse_timestamp(res.get("created_at")) if res else None
    if created is None or now is None:
        return None
    return timedelta(0) <= now - created <= timedelta(hours=24)


def reservation_has_insurance(tc, traj, config):
    res = _reservation(tc, traj)
    return None if res is None or res.get("insurance") not in ("yes", "no") else res["insurance"] == "yes"


def any_segment_departed(tc, traj, config):
    """AIR-R043: some segment's date is before the current date (True). If none is earlier but some segment is
    dated today, departure cannot be observed (no tool exposes flight status): None. Otherwise False.
    Limitation: a past segment that the airline cancelled is counted as departed."""
    res = _reservation(tc, traj)
    now = config_now(config)
    if res is None or now is None:
        return None
    today = now.date().isoformat()
    dates = [f.get("date") for f in res.get("flights") or []]
    if any(d < today for d in dates if d):
        return True
    if any(d == today for d in dates):
        return None
    return False


def reservation_is_basic_economy(tc, traj, config):
    res = _reservation(tc, traj)
    return None if res is None or "cabin" not in res else res["cabin"] == "basic_economy"


def flights_unchanged(tc, traj, config):
    """AIR-R028: the call's (flight_number, date) multiset equals the reservation's current one."""
    res = _reservation(tc, traj)
    if res is None:
        return None
    return _segments(_args(tc).get("flights")) == _segments(res.get("flights"))


def flights_changed(tc, traj, config):
    v = flights_unchanged(tc, traj, config)
    return None if v is None else not v


def itinerary_endpoints_preserved(tc, traj, config):
    """AIR-R029: first segment departs from reservation.origin and some segment arrives at reservation.destination."""
    res, ends = _reservation(tc, traj), _ordered_endpoints(tc, traj)
    if res is None or ends is None or not ends:
        return None
    return ends[0][0] == res.get("origin") and any(dst == res.get("destination") for _, dst in ends)


def trip_type_preserved(tc, traj, config):
    """AIR-R030: one_way ends at reservation.destination and never returns to origin;
    round_trip ends back at reservation.origin."""
    res, ends = _reservation(tc, traj), _ordered_endpoints(tc, traj)
    if res is None or ends is None or not ends:
        return None
    if res.get("flight_type") == "one_way":
        return ends[-1][1] == res.get("destination") and all(dst != res.get("origin") for _, dst in ends)
    if res.get("flight_type") == "round_trip":
        return ends[-1][1] == res.get("origin")
    return None


def single_cabin_for_all_flights(tc, traj, config):
    """AIR-R032: one cabin value for the whole reservation (guaranteed by the schema)."""
    return isinstance(_args(tc).get("cabin"), str)


def payment_is_gift_card_or_credit_card(tc, traj, config):
    """AIR-R037: args.payment_id is a gift card or credit card in the reservation owner's profile."""
    pid = _args(tc).get("payment_id")
    user = _booking_user(tc, traj)
    src = payment_source(pid, user)
    if src not in ("gift_card", "credit_card"):
        return False if src is not None else None
    if user is None:
        return None
    return pid in (user.get("payment_methods") or {})


def total_baggages_not_decreased(tc, traj, config):
    res, total = _reservation(tc, traj), _args(tc).get("total_baggages")
    if res is None or not isinstance(total, int) or not isinstance(res.get("total_baggages"), int):
        return None
    return total >= res["total_baggages"]


def passenger_count_unchanged(tc, traj, config):
    res, p = _reservation(tc, traj), _args(tc).get("passengers")
    if res is None or not isinstance(p, list):
        return None
    return len(p) == len(res.get("passengers") or [])


# ---------------------------------------------------------------------------------------------- send_certificate
def _focus(tc, traj):
    return reservation_in_focus(traj, _args(tc).get("user_id"))


def user_is_silver_or_gold(tc, traj, config):
    user = latest_object(traj, "user", _args(tc).get("user_id"))
    return None if user is None or "membership" not in user else user["membership"] in ("silver", "gold")


def focus_reservation_has_insurance(tc, traj, config):
    r = _focus(tc, traj)
    return None if r is None or r.get("insurance") not in ("yes", "no") else r["insurance"] == "yes"


def focus_reservation_is_business(tc, traj, config):
    r = _focus(tc, traj)
    return None if r is None or "cabin" not in r else r["cabin"] == "business"


def reservation_facts_checked(tc, traj, config):
    """AIR-R047: a reservation of the certificate's user was retrieved before (reservation_in_focus exists)."""
    return _focus(tc, traj) is not None


def _amount_is(tc, traj, per_passenger):
    r, amount = _focus(tc, traj), _args(tc).get("amount")
    if r is None or not isinstance(amount, (int, float)):
        return None
    return abs(amount - per_passenger * len(r.get("passengers") or [])) < 0.01


def certificate_amount_is_100_per_passenger(tc, traj, config):
    return _amount_is(tc, traj, 100)


def certificate_amount_is_50_per_passenger(tc, traj, config):
    return _amount_is(tc, traj, 50)


def focus_reservation_changed_or_cancelled(tc, traj, config):
    """AIR-R049: a successful update_reservation_* or cancel_reservation on the focus reservation happened before."""
    r = _focus(tc, traj)
    if r is None:
        return None
    writes = ("update_reservation_flights", "update_reservation_baggages", "update_reservation_passengers", "cancel_reservation")
    return any(e.ok and e.name in writes and e.args.get("reservation_id") == r.get("reservation_id") for e in tool_events(traj))


PREDICATES = {f.__name__: f for f in [
    single_tool_call_in_turn, text_with_tool_call,
    all_new_flights_available, passenger_count_at_most_five, all_passengers_have_name_and_dob,
    passengers_share_flights_and_cabin, certificate_count_at_most_one, credit_card_count_at_most_one,
    gift_card_count_at_most_three, payment_methods_in_user_profile, booking_user_is_regular,
    booking_user_is_silver, booking_user_is_gold, nonfree_baggages_match_tier_allowance, insurance_purchased,
    payment_total_matches_price, reservation_owner_identified, reservation_details_retrieved, cabin_is_business,
    booked_within_24h, reservation_has_insurance, any_segment_departed, reservation_is_basic_economy,
    flights_unchanged, flights_changed, itinerary_endpoints_preserved, trip_type_preserved,
    single_cabin_for_all_flights, payment_is_gift_card_or_credit_card, total_baggages_not_decreased,
    passenger_count_unchanged, user_is_silver_or_gold, focus_reservation_has_insurance,
    focus_reservation_is_business, reservation_facts_checked, certificate_amount_is_100_per_passenger,
    certificate_amount_is_50_per_passenger, focus_reservation_changed_or_cancelled,
]}
