"""Tracker v3 part 3 (docs/planning/tracker_v3/p3.md): τ-bench's own write tool as an objective label.

    from state_tracker.v3.tool_check import check
    lab = check(state, {"tool": "modify_pending_order_payment", "args": {...}})
    lab == {"tool": ..., "first_error": "Error: ..." or None, "accepted": True | False,
            "check": name of the failed check (TOOL_CHECKS) | None (accepted) | "other" | "ambiguous",
            "facts": {fact: True | False | None}}

How it works:
1. Deep-copy the state's database (and the arguments), and run the pending write call on the copy with τ-bench's own
   tool code (state.run_tool, as Env.step: an exception becomes "Error: <exception>"). The real state is never
   changed.
2. A τ-bench tool returns at its first failing check, so the output is the first "Error: ..." text. It is matched to
   one check of the tool's list (TOOL_CHECKS, in the tool's code order; the variable parts of a text must be values of
   the call's arguments). A text that matches no listed check (an exception in the tool code) is "other"; one that
   matches more than one check is "ambiguous". Both leave every fact None.
3. Each fact a tool checks has its deciding check(s) (TOOL_FACTS). For an error at check k:
     - k decides the fact                      -> False;
     - all deciding checks come before k       -> True (they passed);
     - a deciding check comes after k          -> None ("not decided by the tool": counted apart, never as agreement).
   No error -> every fact of the tool is True. Exceptions (the tool does not check that part):
     - item_replacements_are_available_same_product_different_option: the tool accepts a "replacement" by the same
       item id, which the "different option" part forbids -> None when any new item id equals its old item id;
     - gift_card_balance_covers_order_total / gift_card_balance_covers_price_difference: the tool checks the balance
       only when the payment method's source is "gift_card" (read from the database, as the tool reads it) -> None for
       another source;
     - booking_payment_methods_found_in_user_profile: book_reservation checks "found" and "enough balance" per payment
       method in one loop; a balance error at payment method j leaves the later methods unchecked -> True only when j
       is the last method (and its id occurs once), else None.
4. order_status_checked_pending / order_status_checked_delivered (WORLD_PART_ONLY): only the world part, i.e. the
   order's status in the database is "pending" / "delivered". The facts themselves also need the agent to have checked
   the status; the tool cannot see that.

The facts with a tool check (p3 step 2; names from output/predicate_types.json), and the Error texts that decide them:
  payment_method_differs_from_original          "the new payment method should be different from the current one"
  gift_card_balance_covers_order_total          "insufficient gift card balance to pay for the order"
  item_replacements_are_available_same_product_different_option
                                                "<item> not found", "the number of items to be exchanged should
                                                match", "new item <id> not found or available" (modify items, exchange)
  gift_card_balance_covers_price_difference     "insufficient gift card balance to pay for the new item" (modify
                                                items) / "... for the price difference" (exchange)
  return_refund_method_is_original_or_existing_gift_card
                                                "payment method should be either the original payment method or a
                                                gift card". The earlier "payment method not found" (check 3) is a
                                                separate check: the fact is then None (p3.md lists only check 4).
  booking_payment_methods_found_in_user_profile "payment method <id> not found" (book_reservation)
  pending_passenger_count_unchanged             "number of passengers does not match"
plus the world part of order_status_checked_pending ("non-pending order cannot be ...") and
order_status_checked_delivered ("non-delivered order cannot be ..."). cancel_reservation checks only "reservation not
found". Tools with checks but no fact (update_reservation_flights, update_reservation_baggages, send_certificate,
modify_user_address, book_reservation's flight checks) still get first_error, accepted and check.

Standard library only. No LLM call. Never imports gold code. No side effects on import.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from state_tracker import state as S

# ------------------------------------------------------------------------------------------------ facts
PENDING = "order_status_checked_pending"
DELIVERED = "order_status_checked_delivered"
DIFFERS = "payment_method_differs_from_original"
GC_TOTAL = "gift_card_balance_covers_order_total"
REPLACE = "item_replacements_are_available_same_product_different_option"
GC_DIFF = "gift_card_balance_covers_price_difference"
REFUND = "return_refund_method_is_original_or_existing_gift_card"
BOOK_PM = "booking_payment_methods_found_in_user_profile"
PAX = "pending_passenger_count_unchanged"

WORLD_PART_ONLY = (PENDING, DELIVERED)
TOOL_CHECKED_FACTS = (DIFFERS, GC_TOTAL, REPLACE, GC_DIFF, REFUND, BOOK_PM, PAX)    # the 7 facts of p3 step 2
ALL_FACTS = TOOL_CHECKED_FACTS + WORLD_PART_ONLY
FACT_DOMAIN = {DIFFERS: "retail", GC_TOTAL: "retail", REPLACE: "retail", GC_DIFF: "retail", REFUND: "retail",
               PENDING: "retail", DELIVERED: "retail", BOOK_PM: "airline", PAX: "airline"}

OTHER = "other"            # an Error text that matches no listed check (an exception in the tool code)
AMBIGUOUS = "ambiguous"    # an Error text that matches more than one listed check


# ------------------------------------------------------------------------------------------------ matchers
def _items(x: Any) -> List[Any]:
    """What `for v in x` gives in the tool code (a list, a string's characters, ...); [] if x is not iterable."""
    try:
        return list(x)
    except TypeError:
        return []


def _arg(args: Any, key: str) -> Any:
    return args.get(key) if isinstance(args, dict) else None


def _exact(text: str) -> Callable[[str, Any], bool]:
    return lambda out, args: out == text


def _each(key: str, fmt: str) -> Callable[[str, Any], bool]:
    """fmt.format(v) for a value v of the argument list `key` (as the tool's f-string formats it)."""
    return lambda out, args: any(out == fmt.format(v) for v in _items(_arg(args, key)))


def _each_payment(fmt: str) -> Callable[[str, Any], bool]:
    """fmt.format(payment_id) for a payment of the `payment_methods` argument (book_reservation)."""
    def m(out: str, args: Any) -> bool:
        return any(out == fmt.format(p.get("payment_id")) for p in _items(_arg(args, "payment_methods"))
                   if isinstance(p, dict))
    return m


def _each_flight(fmt: str) -> Callable[[str, Any], bool]:
    """fmt.format(flight_number=..., date=...) for a flight of the `flights` argument."""
    def m(out: str, args: Any) -> bool:
        return any(out == fmt.format(fn=f.get("flight_number"), date=f.get("date"))
                   for f in _items(_arg(args, "flights")) if isinstance(f, dict))
    return m


def _regex(pattern: str) -> Callable[[str, Any], bool]:
    rx = re.compile(pattern, re.S)
    return lambda out, args: rx.fullmatch(out) is not None


# One entry per Error text of the tool, in the tool's code order (output/logs/v3_scout_tool_errors.log):
# (check name, the text as written in the tool's source, matcher(output, args) -> bool).
_ORDER_NOT_FOUND = ("order_not_found", "Error: order not found", _exact("Error: order not found"))
_PM_NOT_FOUND = ("payment_method_not_found", "Error: payment method not found",
                 _exact("Error: payment method not found"))
_ITEM_NOT_FOUND = ("item_not_found", "Error: {item_id} not found", _each("item_ids", "Error: {} not found"))
_COUNT = ("item_count_mismatch", "Error: the number of items to be exchanged should match",
          _exact("Error: the number of items to be exchanged should match"))
_NEW_ITEM = ("new_item_not_found_or_available", "Error: new item {new_item_id} not found or available",
             _each("new_item_ids", "Error: new item {} not found or available"))
_RES_NOT_FOUND = ("reservation_not_found", "Error: reservation not found", _exact("Error: reservation not found"))
_USER_NOT_FOUND = ("user_not_found", "Error: user not found", _exact("Error: user not found"))
_FLIGHT_CHECKS = [
    ("flight_not_found", "Error: flight {flight_number} not found",
     _each_flight("Error: flight {fn} not found")),
    ("flight_not_found_on_date", "Error: flight {flight_number} not found on date {flight['date']}",
     _each_flight("Error: flight {fn} not found on date {date}")),
    ("flight_not_available_on_date", "Error: flight {flight_number} not available on date {flight['date']}",
     _each_flight("Error: flight {fn} not available on date {date}")),
    ("not_enough_seats", "Error: not enough seats on flight {flight_number}",
     _each_flight("Error: not enough seats on flight {fn}")),
]
_CERT = ("certificate_not_allowed", "Error: certificate cannot be used to update reservation",
         _exact("Error: certificate cannot be used to update reservation"))
_GC_NOT_ENOUGH = ("gift_card_balance_not_enough", "Error: gift card balance is not enough",
                  _exact("Error: gift card balance is not enough"))

TOOL_CHECKS: Dict[str, List[Tuple[str, str, Callable[[str, Any], bool]]]] = {
    # retail
    "cancel_pending_order": [
        _ORDER_NOT_FOUND,
        ("non_pending", "Error: non-pending order cannot be cancelled",
         _exact("Error: non-pending order cannot be cancelled")),
        ("invalid_reason", "Error: invalid reason", _exact("Error: invalid reason")),
    ],
    "exchange_delivered_order_items": [
        _ORDER_NOT_FOUND,
        ("non_delivered", "Error: non-delivered order cannot be exchanged",
         _exact("Error: non-delivered order cannot be exchanged")),
        _ITEM_NOT_FOUND, _COUNT, _NEW_ITEM, _PM_NOT_FOUND,
        ("gift_card_insufficient", "Error: insufficient gift card balance to pay for the price difference",
         _exact("Error: insufficient gift card balance to pay for the price difference")),
    ],
    "modify_pending_order_address": [
        _ORDER_NOT_FOUND,
        ("non_pending", "Error: non-pending order cannot be modified",
         _exact("Error: non-pending order cannot be modified")),
    ],
    "modify_pending_order_items": [
        _ORDER_NOT_FOUND,
        ("non_pending", "Error: non-pending order cannot be modified",
         _exact("Error: non-pending order cannot be modified")),
        _ITEM_NOT_FOUND, _COUNT, _NEW_ITEM, _PM_NOT_FOUND,
        ("gift_card_insufficient", "Error: insufficient gift card balance to pay for the new item",
         _exact("Error: insufficient gift card balance to pay for the new item")),
    ],
    "modify_pending_order_payment": [
        _ORDER_NOT_FOUND,
        ("non_pending", "Error: non-pending order cannot be modified",
         _exact("Error: non-pending order cannot be modified")),
        _PM_NOT_FOUND,
        ("not_exactly_one_payment", "Error: there should be exactly one payment for a pending order",
         _exact("Error: there should be exactly one payment for a pending order")),
        ("same_payment_method", "Error: the new payment method should be different from the current one",
         _exact("Error: the new payment method should be different from the current one")),
        ("gift_card_insufficient", "Error: insufficient gift card balance to pay for the order",
         _exact("Error: insufficient gift card balance to pay for the order")),
    ],
    "modify_user_address": [_USER_NOT_FOUND],
    "return_delivered_order_items": [
        _ORDER_NOT_FOUND,
        ("non_delivered", "Error: non-delivered order cannot be returned",
         _exact("Error: non-delivered order cannot be returned")),
        _PM_NOT_FOUND,
        ("refund_method_not_allowed",
         "Error: payment method should be either the original payment method or a gift card",
         _exact("Error: payment method should be either the original payment method or a gift card")),
        ("some_item_not_found", "Error: some item not found", _exact("Error: some item not found")),
    ],
    # airline
    "book_reservation": [
        _USER_NOT_FOUND, *_FLIGHT_CHECKS,
        ("payment_method_not_found", "Error: payment method {payment_id} not found",
         _each_payment("Error: payment method {} not found")),
        ("not_enough_balance", "Error: not enough balance in payment method {payment_id}",
         _each_payment("Error: not enough balance in payment method {}")),
        ("payment_amount_mismatch",
         "Error: payment amount does not add up, total price is {total_price}, but paid "
         "{sum(payment['amount'] for payment in payment_methods)}",
         _regex(r"Error: payment amount does not add up, total price is .+, but paid .+")),
    ],
    "cancel_reservation": [_RES_NOT_FOUND],
    "send_certificate": [_USER_NOT_FOUND],
    "update_reservation_baggages": [_RES_NOT_FOUND, _PM_NOT_FOUND, _CERT, _GC_NOT_ENOUGH],
    "update_reservation_flights": [_RES_NOT_FOUND, *_FLIGHT_CHECKS, _PM_NOT_FOUND, _CERT, _GC_NOT_ENOUGH],
    "update_reservation_passengers": [
        _RES_NOT_FOUND,
        ("passenger_count_mismatch", "Error: number of passengers does not match",
         _exact("Error: number of passengers does not match")),
    ],
}

TOOL_DOMAIN = {t: ("airline" if t in ("book_reservation", "cancel_reservation", "send_certificate",
                                       "update_reservation_baggages", "update_reservation_flights",
                                       "update_reservation_passengers") else "retail") for t in TOOL_CHECKS}

# fact -> the check(s) that decide it, per tool
_REPLACE_CHECKS = ["item_not_found", "item_count_mismatch", "new_item_not_found_or_available"]
TOOL_FACTS: Dict[str, Dict[str, List[str]]] = {
    "cancel_pending_order": {PENDING: ["non_pending"]},
    "modify_pending_order_address": {PENDING: ["non_pending"]},
    "modify_pending_order_items": {PENDING: ["non_pending"], REPLACE: _REPLACE_CHECKS,
                                   GC_DIFF: ["gift_card_insufficient"]},
    "modify_pending_order_payment": {PENDING: ["non_pending"], DIFFERS: ["same_payment_method"],
                                     GC_TOTAL: ["gift_card_insufficient"]},
    "return_delivered_order_items": {DELIVERED: ["non_delivered"], REFUND: ["refund_method_not_allowed"]},
    "exchange_delivered_order_items": {DELIVERED: ["non_delivered"], REPLACE: _REPLACE_CHECKS,
                                       GC_DIFF: ["gift_card_insufficient"]},
    "book_reservation": {BOOK_PM: ["payment_method_not_found"]},
    "update_reservation_passengers": {PAX: ["passenger_count_mismatch"]},
    "cancel_reservation": {},
    "modify_user_address": {},
    "send_certificate": {},
    "update_reservation_baggages": {},
    "update_reservation_flights": {},
}


class NotAWriteTool(ValueError):
    """check() was given a tool that does not write to the database (read tools, transfer_to_human_agents, unknown
    names)."""


# ------------------------------------------------------------------------------------------------ the check
def is_write_tool(domain: str, tool: str) -> bool:
    """A τ-bench tool of this domain that can change the database (state_tracker/tool_table.json changes_db)."""
    spec = S.tool_table()["domains"].get(domain, {}).get("tools", {}).get(tool)
    return bool(spec and spec.get("changes_db"))


def run_on_copy(state: S.State, tool: str, args: Any) -> Any:
    """The tool's output on a deep copy of the state's database (and of the arguments). state.db is not touched."""
    db = copy.deepcopy(state.db)
    return S.run_tool(state.domain, db, tool, copy.deepcopy(args))


def which_check(tool: str, output: Any, args: Any) -> Optional[str]:
    """The name of the failed check for an output of `tool`: None (the call worked), a TOOL_CHECKS name, OTHER or
    AMBIGUOUS."""
    if not S.is_failure(output):
        return None
    if not isinstance(output, str):
        return OTHER
    hits = [name for name, _, m in TOOL_CHECKS[tool] if m(output, args)]
    names = list(dict.fromkeys(hits))
    if not names:
        return OTHER
    return names[0] if len(names) == 1 else AMBIGUOUS


def _payment_source(state: S.State, args: Any) -> Optional[str]:
    """The source of the call's payment method in the order's user's profile (the field the retail tools read before
    their gift-card balance check), or None if it cannot be read."""
    try:
        order = state.db["orders"][args["order_id"]]
        return state.db["users"][order["user_id"]]["payment_methods"][args["payment_method_id"]].get("source")
    except (KeyError, TypeError):
        return None


def _same_item_pair(args: Any) -> bool:
    """Some new item id equals its old item id (pairs as the tool zips them)."""
    return any(a == b for a, b in zip(_items(_arg(args, "item_ids")), _items(_arg(args, "new_item_ids"))))


def _balance_error_at_last_payment(output: str, args: Any) -> bool:
    """book_reservation's balance error names the last payment method, and that id occurs once in the list."""
    pms = [p for p in _items(_arg(args, "payment_methods"))]
    ids = [p.get("payment_id") if isinstance(p, dict) else None for p in pms]
    if not ids:
        return False
    last = ids[-1]
    return output == f"Error: not enough balance in payment method {last}" and ids.count(last) == 1


def label_output(state: S.State, tool: str, args: Any, output: Any) -> dict:
    """The label of one call, from its output on a copy of `state` (see the module docstring). Reads state.db only
    for the gift-card source (R7, R9); never changes it."""
    if tool not in TOOL_CHECKS:
        raise NotAWriteTool(f"{tool!r} is not a τ-bench write tool with a check list")
    failed = which_check(tool, output, args)
    order = [name for name, _, _ in TOOL_CHECKS[tool]]
    facts: Dict[str, Optional[bool]] = {}
    for fact, deciding in TOOL_FACTS[tool].items():
        if failed in (OTHER, AMBIGUOUS):
            v: Optional[bool] = None
        elif failed is None:
            v = True
        elif failed in deciding:
            v = False
        else:
            k = order.index(failed)
            v = True if max(order.index(d) for d in deciding) < k else None
        if v is True:
            if fact == REPLACE and _same_item_pair(args):
                v = None                    # "different option" is not checked by the tool
            elif fact in (GC_TOTAL, GC_DIFF) and _payment_source(state, args) != "gift_card":
                v = None                    # the tool checks the balance of gift cards only
            elif fact == BOOK_PM and failed == "not_enough_balance" and not _balance_error_at_last_payment(
                    output, args):
                v = None                    # later payment methods were not checked
        facts[fact] = v
    return {"tool": tool, "first_error": output if S.is_failure(output) else None,
            "accepted": not S.is_failure(output), "check": failed, "facts": facts}


def _call(state: S.State, call: Any) -> Tuple[str, Any]:
    c = S.normalize_action(call) if call is not None else state.pending
    if c is None:
        raise ValueError("no call given and the state has no pending action")
    return c["tool"], c["args"]


def check(state: S.State, call: Any = None, keep_output: bool = False) -> dict:
    """τ-bench's tool check of one pending write call on a scratch copy of `state` (module docstring).

    call: {"tool", "args"}, (name, kwargs), a step record ("action", "kwargs") or None (state.pending).
    Returns {tool, first_error, accepted, check, facts} (and "output", the full tool output, if keep_output).
    Raises NotAWriteTool for a tool that is not a database write of the state's domain."""
    tool, args = _call(state, call)
    if not is_write_tool(state.domain, tool) or tool not in TOOL_CHECKS:
        raise NotAWriteTool(f"{tool!r} is not a database write tool of {state.domain}")
    output = run_on_copy(state, tool, args)
    lab = label_output(state, tool, args, output)
    if keep_output:
        lab["output"] = output
    return lab
