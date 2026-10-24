"""Deterministic predicates (state / tool_log / structural) for the τ-bench v1 retail ASPM.

Specs: policies/predicates/retail_predicates.json. Signature of every predicate:
    (tool_call: dict, trajectory: list, config: dict) -> bool | None
None means the trajectory does not contain enough information to decide.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional

from agent.predicates.context import (
    all_latest_objects, authenticated_user_id, call_args, call_name, latest_object, payment_source,
    single_tool_call_in_turn, successful_calls, text_with_tool_call, tool_events,
)

DOMAIN = "retail"
CANCEL_REASONS = ("no longer needed", "ordered by mistake")   # RET-CAN-02b


# ---------------------------------------------------------------------------------------------- helpers
def _args(tc):
    return call_args(tc)


def _order(tc, traj) -> Optional[dict]:
    return latest_object(traj, "order", _args(tc).get("order_id"))


def _order_user(tc, traj) -> Optional[dict]:
    o = _order(tc, traj)
    return latest_object(traj, "user", o.get("user_id")) if o else None


def _pairs(tc):
    a = _args(tc)
    old, new = a.get("item_ids"), a.get("new_item_ids")
    if not isinstance(old, list) or not isinstance(new, list) or len(old) != len(new):
        return None
    return list(zip(old, new))


def _variant_for_pair(tc, traj, old_id, new_id):
    """(found_in_same_product, variant) for one replacement pair; None if product details are not known."""
    order = _order(tc, traj)
    if order is None:
        return None
    item = next((i for i in order.get("items") or [] if i.get("item_id") == old_id), None)
    if item is None:
        return None
    product = latest_object(traj, "product", item.get("product_id"))
    if product is None:
        return None
    variant = (product.get("variants") or {}).get(new_id)
    return (variant is not None, variant)


def _price_difference(tc, traj) -> Optional[float]:
    pairs, order = _pairs(tc), _order(tc, traj)
    if pairs is None or order is None:
        return None
    diff = 0.0
    for old_id, new_id in pairs:
        item = next((i for i in order.get("items") or [] if i.get("item_id") == old_id), None)
        got = _variant_for_pair(tc, traj, old_id, new_id)
        if item is None or got is None or not got[0]:
            return None
        diff += got[1]["price"] - item["price"]
    return round(diff, 2)


def _known_ids(traj):
    """(product ids, item ids) seen in tool outputs (orders' items, product records, product type list)."""
    products, items = set(), set()
    for e in tool_events(traj):
        d = e.data
        if not e.ok or d is None:
            continue
        if e.name == "list_all_product_types" and isinstance(d, dict):
            products.update(v for v in d.values() if isinstance(v, str))
        if isinstance(d, dict) and "variants" in d and "product_id" in d:
            products.add(d["product_id"])
            items.update((d.get("variants") or {}).keys())
        if isinstance(d, dict) and isinstance(d.get("items"), list):
            for it in d["items"]:
                if isinstance(it, dict):
                    products.add(it.get("product_id"))
                    items.add(it.get("item_id"))
    return products, items


# ---------------------------------------------------------------------------------------------- identity
def user_authenticated(tc, traj, config):
    """RET-R001: a find_user_id_by_email / find_user_id_by_name_zip call has succeeded."""
    return authenticated_user_id(traj, DOMAIN) is not None


def all_referenced_entities_owned(tc, traj, config):
    """RET-R002: every user_id / order_id in the args belongs to the authenticated user.
    Order ownership from the latest order object, else from the user's order list. None if undecidable."""
    uid = authenticated_user_id(traj, DOMAIN)
    if uid is None:
        return None
    a = _args(tc)
    if "user_id" in a and a["user_id"] != uid:
        return False
    if "order_id" in a:
        o = _order(tc, traj)
        if o is not None:
            return o.get("user_id") == uid
        user = latest_object(traj, "user", uid)
        if user is None:
            return None
        return a["order_id"] in (user.get("orders") or [])
    return True


def auth_lookup_targets_other_user(tc, traj, config):
    """RET-R002 (authentication tools): a user is already authenticated and this lookup's identity
    (email, or name + zip) differs from that user's profile. False if nobody is authenticated yet."""
    uid = authenticated_user_id(traj, DOMAIN)
    if uid is None:
        return False
    user = latest_object(traj, "user", uid)
    if user is None:
        return None
    a = _args(tc)
    if call_name(tc) == "find_user_id_by_email":
        return (a.get("email") or "").lower() != (user.get("email") or "").lower()
    name, addr = user.get("name") or {}, user.get("address") or {}
    same = (a.get("first_name") == name.get("first_name") and a.get("last_name") == name.get("last_name")
            and a.get("zip") == addr.get("zip"))
    return not same


# ---------------------------------------------------------------------------------------------- order status
def order_status_is_pending(tc, traj, config):
    """RET-R013: status of the LATEST order object is exactly 'pending' ('pending (item modified)' is not)."""
    o = _order(tc, traj)
    return None if o is None or "status" not in o else o["status"] == "pending"


def order_status_is_delivered(tc, traj, config):
    o = _order(tc, traj)
    return None if o is None or "status" not in o else o["status"] == "delivered"


def order_status_checked(tc, traj, config):
    """RET-R015: get_order_details succeeded earlier for args.order_id."""
    oid = _args(tc).get("order_id")
    return any(e.args.get("order_id") == oid for e in successful_calls(traj, "get_order_details"))


def items_modified_before_for_order(tc, traj, config):
    """RET-R016: a successful modify_pending_order_items on this order already happened."""
    oid = _args(tc).get("order_id")
    return any(e.args.get("order_id") == oid for e in successful_calls(traj, "modify_pending_order_items"))


def exchange_done_before_for_order(tc, traj, config):
    """RET-R017: a successful exchange_delivered_order_items on this order already happened."""
    oid = _args(tc).get("order_id")
    return any(e.args.get("order_id") == oid for e in successful_calls(traj, "exchange_delivered_order_items"))


# ---------------------------------------------------------------------------------------------- cancel / payment
def cancel_reason_is_valid(tc, traj, config):
    r = _args(tc).get("reason")
    return None if r is None else r in CANCEL_REASONS


def payment_differs_from_original(tc, traj, config):
    """RET-R023: args.payment_method_id != the order's original payment method (payment_history[0])."""
    o = _order(tc, traj)
    if o is None or not o.get("payment_history"):
        return None
    return _args(tc).get("payment_method_id") != o["payment_history"][0].get("payment_method_id")


def new_payment_is_gift_card(tc, traj, config):
    src = payment_source(_args(tc).get("payment_method_id"), _order_user(tc, traj))
    return None if src is None else src == "gift_card"


def gift_card_covers_order_total(tc, traj, config):
    """RET-R024: the gift card's balance >= the order's paid amount (payment_history[0].amount)."""
    o, user = _order(tc, traj), _order_user(tc, traj)
    pid = _args(tc).get("payment_method_id")
    if o is None or user is None or not o.get("payment_history"):
        return None
    pm = (user.get("payment_methods") or {}).get(pid)
    if pm is None or "balance" not in pm:
        return None
    return pm["balance"] >= o["payment_history"][0]["amount"]


# ---------------------------------------------------------------------------------------------- item changes
def replacement_items_same_product(tc, traj, config):
    """RET-R025: every new item is a variant of the replaced item's product (from get_product_details)."""
    pairs = _pairs(tc)
    if pairs is None:
        return None
    for old_id, new_id in pairs:
        got = _variant_for_pair(tc, traj, old_id, new_id)
        if got is None:
            return None
        if not got[0]:
            return False
    return True


def replacement_items_available(tc, traj, config):
    """RET-R026: every new item's variant has available == True (latest product record)."""
    pairs = _pairs(tc)
    if pairs is None:
        return None
    for old_id, new_id in pairs:
        got = _variant_for_pair(tc, traj, old_id, new_id)
        if got is None or not got[0]:
            return None
        if not got[1].get("available"):
            return False
    return True


def replacement_items_differ(tc, traj, config):
    """RET-R027: new_item_id != item_id for every pair (a different option)."""
    pairs = _pairs(tc)
    return None if pairs is None else all(o != n for o, n in pairs)


def gift_card_covers_price_difference(tc, traj, config):
    """RET-R029: if paying by gift card, its balance >= the total price difference (new - old prices)."""
    user = _order_user(tc, traj)
    pid = _args(tc).get("payment_method_id")
    diff = _price_difference(tc, traj)
    if user is None or diff is None:
        return None
    pm = (user.get("payment_methods") or {}).get(pid)
    if pm is None or "balance" not in pm:
        return None
    return pm["balance"] >= diff


def item_ids_are_order_items(tc, traj, config):
    """RET-R012: item_ids are item ids of this order (with multiplicity) and none is a known product id."""
    o, ids = _order(tc, traj), _args(tc).get("item_ids")
    if o is None or not isinstance(ids, list):
        return None
    products, _ = _known_ids(traj)
    have = Counter(i.get("item_id") for i in o.get("items") or [])
    need = Counter(ids)
    return all(have[k] >= v for k, v in need.items()) and not (set(ids) & products)


def new_item_ids_are_item_ids(tc, traj, config):
    """RET-R012: new_item_ids are item (variant) ids, not product ids. None if no product record was seen."""
    ids = _args(tc).get("new_item_ids")
    if not isinstance(ids, list):
        return None
    products, items = _known_ids(traj)
    if set(ids) & products:
        return False
    if all(i in items for i in ids):
        return True
    return None


def product_id_arg_is_known_item_id(tc, traj, config):
    """RET-R012 (get_product_details): the product_id argument is an id the agent has seen as an item id."""
    pid = _args(tc).get("product_id")
    products, items = _known_ids(traj)
    if pid in products:
        return False
    return pid in items


def refund_to_original_or_gift_card(tc, traj, config):
    """RET-R031: refund method is the order's original payment method or a gift card in the user's profile."""
    o, pid = _order(tc, traj), _args(tc).get("payment_method_id")
    if o is None or not o.get("payment_history"):
        return None
    if pid == o["payment_history"][0].get("payment_method_id"):
        return True
    user = _order_user(tc, traj)
    if payment_source(pid, user) != "gift_card":
        return False if payment_source(pid, user) is not None else None
    if user is None:
        return None
    return pid in (user.get("payment_methods") or {})


PREDICATES = {f.__name__: f for f in [
    single_tool_call_in_turn, text_with_tool_call,
    user_authenticated, all_referenced_entities_owned, auth_lookup_targets_other_user,
    order_status_is_pending, order_status_is_delivered, order_status_checked, items_modified_before_for_order,
    exchange_done_before_for_order, cancel_reason_is_valid, payment_differs_from_original, new_payment_is_gift_card,
    gift_card_covers_order_total, replacement_items_same_product, replacement_items_available,
    replacement_items_differ, gift_card_covers_price_difference, item_ids_are_order_items, new_item_ids_are_item_ids,
    product_id_arg_is_known_item_id, refund_to_original_or_gift_card,
]}
