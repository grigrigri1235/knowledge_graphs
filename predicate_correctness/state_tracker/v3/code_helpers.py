"""Tracker v3, part 6: the helper names for the database, event and argument parts of the v3 facts.

The v3 fact expressions (state_tracker/v3/facts_v3_<domain>.json; the p6 overlay
output/eval_v3/p6_parts/exprs_<domain>.json) are written in the frozen v2 lookup format (state_tracker/lookup_format.py:
args, db, db_all, shown, shown_all, events, today, date, len, sum, any, all; no arithmetic, no method calls but .get).
Some parts need a little more: arithmetic (a price difference, a bag count, "24 hours before now"), the pending call's
tool name, or a read that needs a whole table with its ids. This module adds exactly those as NEW names, registered
with facts_format_v3.register_name() when the module is imported:

    import state_tracker.v3.code_helpers     # registers the names below (once; importing again changes nothing)

Every helper is called as func(ctx, ...) by the evaluator (facts_format_v3.Context: ctx.state is the part's recording
state, so the helper's reads are recorded). The source says which parts may call it (HELPER_USE: any part).

  name                     source     what it gives
  looked_up(tool, key, v)  event      True when an earlier call of `tool` worked (its output is no 'Error...') and had
                                      argument `key` equal to v (the "agent looked object X up" event)
  first_login_user()       event      the user id the first worked find_user_id_by_email / find_user_id_by_name_zip
                                      returned (retail `me`), or None before any worked login
  pending_tool()           arguments  the pending call's tool name (state.pending); no pending call -> blocking value,
                                      problem "no_pending_call"
  owner_of(kind, id)       database   the user record that owns the order / reservation `id` at the check; None when
                                      the object does not exist; an object without user_id, or whose user is not in the
                                      users table, is a missing field (a bug, counted)
  user_id_by_email(e)      database   the user id τ-bench's find_user_id_by_email would return (emails compared in
                                      lower case), or None
  user_id_by_name_zip(f, l, z)  database  the same for find_user_id_by_name_zip (names in lower case, exact zip)
  price_difference(order_id, item_ids, new_item_ids, tool)
                           database   the SIGNED price difference sum(new variant price - old item price) over the
                                      pairs in call order, summed as the tool sums it (the old item is the order's
                                      first item with that id; the new item is a variant of the old item's product);
                                      rounded to cents (round(x, 2)) for exchange_delivered_order_items, not rounded
                                      for modify_pending_order_items (each tool's own rounding); None when the order
                                      does not exist, the lists differ in length, or a pair cannot be priced; another
                                      tool -> blocking value, problem "not_this_tool"; a list argument that is not a
                                      list -> type_error
  cabin_now(reservation_id)
                           database   the reservation's cabin: the cabin argument of the newest worked
                                      update_reservation_flights call on it (τ-bench never updates the cabin field),
                                      else the reservation's cabin field at the check; None when it does not exist
  flight_on_date(number, date)
                           database   the flights-table entry of a flight on a date ({status, ...}); a flight or date
                                      that is not in the table is a missing field (used only for an existing
                                      reservation's own segments, so it is a bug, counted)
  today_minus_hours(h)     database   the policy's current time (state.today) minus h hours; no current time ->
                                      blocking value, problem "no_current_time"
  pairs(a, b)              arguments  [[a0, b0], [a1, b1], ...]: τ-bench's zip (stops at the shorter list)
  distinct(xs)             arguments  xs without repeats (first one kept; compared with ==)
  starts_with(x, prefix)   arguments  x is a text that starts with prefix (False for a non-text)
  list_arg(x)              arguments  x itself when it is a list; else blocking value, problem "type_error"
  bags_right(total, nonfree, cabin, passengers, allowance)
                           arguments  nonfree == max(0, total - len(passengers) * per-passenger allowance of the cabin),
                                      allowance = [[cabin, bags per passenger], ...] (written in the expression).
                                      A count that is not a whole number >= 0 -> problem "bad_count"; a cabin not in
                                      the allowance -> problem "unknown_cabin"; passengers not a list -> "type_error"

Standard library only. No LLM call, no network. Never imports gold code or any scoring module.
"""
from __future__ import annotations

import datetime
from typing import Any, List, Optional

from state_tracker.v3 import facts_format_v3 as F

FIND_USER_TOOLS = ("find_user_id_by_email", "find_user_id_by_name_zip")
EXCHANGE = "exchange_delivered_order_items"
MODIFY_ITEMS = "modify_pending_order_items"
FLIGHT_UPDATE = "update_reservation_flights"


def _blocking(kind: str, detail: str) -> F.UseBlockingValue:
    return F.UseBlockingValue(detail, kind=kind)


# ----------------------------------------------------------------------------------------------- event helpers

def looked_up(ctx: F.Context, tool: str, key: str, value: Any) -> bool:
    """True when an earlier executed call of `tool` worked (state.is_failure is False: its output is a text that
    does not start with 'Error' / 'Unknown action') and its argument `key` equals `value`."""
    for e in ctx.state.events_where(tool=tool, ok=True):
        a = e.get("args")
        if isinstance(a, dict) and key in a and a[key] == value:
            return True
    return False


def first_login_user(ctx: F.Context) -> Optional[str]:
    """The output of the first worked find_user_id_by_email / find_user_id_by_name_zip call (a user id, stripped;
    an empty output is skipped), or None. The same reading as p7's retail `me` (message_view.me); a later login
    never switches it."""
    for e in ctx.state.events_where(tool=list(FIND_USER_TOOLS), ok=True):
        out = e.get("output")
        if isinstance(out, str) and out.strip():
            return out.strip()
    return None


# ----------------------------------------------------------------------------------------------- argument helpers

def pending_tool(ctx: F.Context) -> str:
    """The pending call's tool name (state.pending["tool"])."""
    p = getattr(ctx.state, "pending", None)
    if not isinstance(p, dict) or not isinstance(p.get("tool"), str):
        raise _blocking("no_pending_call", "pending_tool(): the state has no pending call")
    return p["tool"]


def pairs(ctx: F.Context, a: Any, b: Any) -> List[list]:
    """[[a[0], b[0]], [a[1], b[1]], ...] as τ-bench's zip(a, b)."""
    return [[x, y] for x, y in zip(a, b)]


def distinct(ctx: F.Context, xs: Any) -> list:
    """The items of xs without repeats, in order (compared with ==, so unhashable items work too)."""
    out: list = []
    for x in xs:
        if x not in out:
            out.append(x)
    return out


def starts_with(ctx: F.Context, x: Any, prefix: str) -> bool:
    return isinstance(x, str) and isinstance(prefix, str) and x.startswith(prefix)


def list_arg(ctx: F.Context, x: Any) -> list:
    """x when it is a list (an argument list); otherwise the fact takes its blocking value (type_error)."""
    if isinstance(x, list):
        return x
    raise _blocking("type_error", f"list_arg(): expected a list, got a {type(x).__name__}")


def _whole(x: Any, name: str) -> int:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or (isinstance(x, float) and not x.is_integer()) \
            or x < 0:
        raise _blocking("bad_count", f"bags_right(): {name} = {x!r} is not a whole number >= 0")
    return int(x)


def bags_right(ctx: F.Context, total: Any, nonfree: Any, cabin: Any, passengers: Any, allowance: Any) -> bool:
    """nonfree == max(0, total - n_passengers * allowance[cabin])."""
    t = _whole(total, "total_baggages")
    n = _whole(nonfree, "nonfree_baggages")
    if not isinstance(passengers, list):
        raise _blocking("type_error", f"bags_right(): passengers is a {type(passengers).__name__}, not a list")
    per = None
    for c, k in allowance:
        if c == cabin:
            per = k
            break
    if per is None:
        raise _blocking("unknown_cabin", f"bags_right(): cabin {cabin!r} has no allowance in {allowance!r}")
    free = len(passengers) * per
    return n == max(0, t - free)


# ----------------------------------------------------------------------------------------------- database helpers

def owner_of(ctx: F.Context, kind: str, oid: Any) -> Optional[dict]:
    """The user record owning the order / reservation `oid` (database at the check), or None if it does not exist."""
    obj = ctx.state.db_get(kind, oid)
    if obj is None:
        return None
    if "user_id" not in obj:
        raise F.MissingField(f"owner_of(): {kind} {oid!r} has no user_id")
    user = ctx.state.db_get("user", obj["user_id"])
    if user is None:
        raise F.MissingField(f"owner_of(): {kind} {oid!r} belongs to user {obj['user_id']!r}, who is not in the "
                             f"users table")
    return user


def _users(ctx: F.Context) -> dict:
    ctx.state.db_all("user")                         # records the read of the whole users table
    return ctx.state.db["users"]


def user_id_by_email(ctx: F.Context, email: Any) -> Optional[str]:
    """τ-bench's find_user_id_by_email matching: profile email == email, both in lower case."""
    if not isinstance(email, str):
        raise TypeError(f"user_id_by_email(): the email is a {type(email).__name__}, not a text")
    for uid, u in _users(ctx).items():
        if u["email"].lower() == email.lower():
            return uid
    return None


def user_id_by_name_zip(ctx: F.Context, first: Any, last: Any, zip_code: Any) -> Optional[str]:
    """τ-bench's find_user_id_by_name_zip matching: first and last name in lower case, the zip exactly."""
    if not isinstance(first, str) or not isinstance(last, str):
        raise TypeError("user_id_by_name_zip(): first and last name must be texts")
    for uid, u in _users(ctx).items():
        if (u["name"]["first_name"].lower() == first.lower() and u["name"]["last_name"].lower() == last.lower()
                and u["address"]["zip"] == zip_code):
            return uid
    return None


def price_difference(ctx: F.Context, order_id: Any, item_ids: Any, new_item_ids: Any, tool: Any) -> Optional[float]:
    """The signed price difference of the item pairs, with the tool's own sum and rounding (module text)."""
    if tool not in (EXCHANGE, MODIFY_ITEMS):
        raise _blocking("not_this_tool", f"price_difference(): no price-difference rule for tool {tool!r}")
    for name, x in (("item_ids", item_ids), ("new_item_ids", new_item_ids)):
        if not isinstance(x, list):
            raise TypeError(f"price_difference(): {name} is a {type(x).__name__}, not a list")
    order = ctx.state.db_get("order", order_id)
    if order is None or len(item_ids) != len(new_item_ids):
        return None
    diff = 0
    for item_id, new_item_id in zip(item_ids, new_item_ids):
        found = [it for it in order["items"] if it["item_id"] == item_id]
        if not found:
            return None
        item = found[0]
        product = ctx.state.db_get("product", item["product_id"])
        if product is None:
            raise F.MissingField(f"price_difference(): order {order_id!r} has an item of product "
                                 f"{item['product_id']!r}, which is not in the products table")
        variants = product["variants"]
        if not isinstance(new_item_id, str) or new_item_id not in variants:
            return None
        diff += variants[new_item_id]["price"] - item["price"]
    if tool == EXCHANGE:
        diff = round(diff, 2)
    return diff


def cabin_now(ctx: F.Context, reservation_id: Any) -> Optional[str]:
    """The cabin of the newest worked update_reservation_flights on this reservation, else its cabin field."""
    ups = [e for e in ctx.state.events_where(tool=FLIGHT_UPDATE, ok=True)
           if isinstance(e.get("args"), dict) and e["args"].get("reservation_id") == reservation_id]
    res = ctx.state.db_get("reservation", reservation_id)
    if ups:
        return ups[-1]["args"]["cabin"]
    if res is None:
        return None
    return res["cabin"]


def flight_on_date(ctx: F.Context, flight_number: Any, date: Any) -> dict:
    """The flights-table entry of `flight_number` on `date` (for an existing reservation's own segment)."""
    f = ctx.state.db_get("flight", flight_number)
    if f is None:
        raise F.MissingField(f"flight_on_date(): flight {flight_number!r} is not in the flights table")
    day = f["dates"].get(date) if isinstance(date, str) else None
    if day is None:
        raise F.MissingField(f"flight_on_date(): flight {flight_number!r} has no entry for date {date!r}")
    return day


def today_minus_hours(ctx: F.Context, hours: Any) -> datetime.datetime:
    """The policy's current time minus `hours` hours."""
    now = getattr(ctx.state, "today", None)
    if now is None:
        raise _blocking("no_current_time", "today_minus_hours(): the policy states no current time")
    if isinstance(hours, bool) or not isinstance(hours, (int, float)):
        raise TypeError("today_minus_hours(): hours must be a number")
    return now - datetime.timedelta(hours=hours)


# ----------------------------------------------------------------------------------------------- registration

HELPERS = (
    # name, func, min args, max args, source, doc
    ("looked_up", looked_up, 3, 3, "event", "a worked earlier call of tool with argument key == value"),
    ("first_login_user", first_login_user, 0, 0, "event", "the user id of the first worked find_user_id_* call"),
    ("pending_tool", pending_tool, 0, 0, "arguments", "the pending call's tool name"),
    ("pairs", pairs, 2, 2, "arguments", "zip(a, b) as a list of [x, y]"),
    ("distinct", distinct, 1, 1, "arguments", "the list without repeats"),
    ("starts_with", starts_with, 2, 2, "arguments", "x is a text starting with prefix"),
    ("list_arg", list_arg, 1, 1, "arguments", "the argument when it is a list, else the blocking value"),
    ("bags_right", bags_right, 5, 5, "arguments", "nonfree == max(0, total - passengers x allowance[cabin])"),
    ("owner_of", owner_of, 2, 2, "database", "the user record owning an order or reservation"),
    ("user_id_by_email", user_id_by_email, 1, 1, "database", "τ-bench's email matching"),
    ("user_id_by_name_zip", user_id_by_name_zip, 3, 3, "database", "τ-bench's name + zip matching"),
    ("price_difference", price_difference, 4, 4, "database", "signed price difference with the tool's rounding"),
    ("cabin_now", cabin_now, 1, 1, "database", "the cabin after the last worked flight update"),
    ("flight_on_date", flight_on_date, 2, 2, "database", "the flights-table entry of a segment"),
    ("today_minus_hours", today_minus_hours, 1, 1, "database", "the policy's current time minus h hours"),
)
NAMES = tuple(h[0] for h in HELPERS)


def register_all() -> None:
    """Register every helper (registering the very same helper again changes nothing)."""
    for name, func, lo, hi, source, doc in HELPERS:
        F.register_name(name, func, lo, hi, (), source=source, doc=doc)


register_all()
