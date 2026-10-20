# τ-bench v1 retail: data formats that predicates depend on

Source: `sierra-research/tau-bench` @ `59a200c` (read-only clone at `~/refs/tau-bench`), files `tau_bench/envs/retail/data/{users,orders,products}.json` and `tools/*.py`. Counts come from the data files. See also `retail_tools.json`.

## What the agent can see

| Tool | Output | Contains |
|---|---|---|
| `find_user_id_by_email(email)`, `find_user_id_by_name_zip(first_name, last_name, zip)` | Plain string user id (e.g. `noah_brown_6181`), or `"Error: user not found"` | The successful result **is** the authentication event. |
| `get_user_details(user_id)` | JSON user record | **No `user_id` key**: associate it with the call argument. |
| `modify_user_address(user_id, …)` | JSON user record after the write | Same; associate it with the argument. |
| `get_order_details(order_id)` | JSON order record | Has `order_id` and `user_id`. |
| `cancel_pending_order`, `modify_pending_order_*`, `return_delivered_order_items`, `exchange_delivered_order_items` | JSON order record **after** the write | The latest status. |
| `get_product_details(product_id)` | JSON product `{name, product_id, variants{item_id→variant}}` | |
| `list_all_product_types()` | JSON `{product name: product_id}` (50 entries) | |
| `transfer_to_human_agents` | `"Transfer successful"` | |
| `think` | `""` | |
| Any tool on failure | A string starting with `"Error: "` | No state change. |

There are no timestamps in orders. All database times are EST, 24 h (wiki), and no retail rule depends on time.

## Order object
Keys: `order_id`, `user_id`, `address{address1,address2,city,country,state,zip}`, `items[]`, `fulfillments[]`, `status`, `payment_history[]`.
- `order_id`: `#W` followed by 7 digits (e.g. `#W2611340`). Note the leading `#`.
- `items[]`: `{name, product_id, item_id, price, options{…}}`. The same `item_id` can occur twice; the tools count duplicates.
- `payment_history[]`: `{transaction_type ∈ {payment, refund}, amount, payment_method_id}`. Every `pending` order has **exactly one** entry, a `payment`. The **original payment method** is `payment_history[0].payment_method_id`.
- After an exchange or return, the tools add `exchange_items`, `exchange_new_items`, `exchange_payment_method_id`, `exchange_price_difference` / `return_items`, `return_payment_method_id`.

### Status strings (exact)

| Status | Where it comes from |
|---|---|
| `pending` (423), `processed` (102), `delivered` (373), `cancelled` (102) | initial data |
| `cancelled` | `cancel_pending_order.py:41` |
| **`pending (item modified)`** | `modify_pending_order_items.py:84`. The wiki writes `'pending (items modifed)'`; the code string is singular `item` and spelled correctly. |
| `return requested` | `return_delivered_order_items.py:38` |
| `exchange requested` | `exchange_delivered_order_items.py:67` |
| `pending` (unchanged) | `modify_pending_order_address` and `modify_pending_order_payment` |

All status guards in the tools are **exact string comparisons** (`!= "pending"`, `!= "delivered"`). An order in `pending (item modified)` therefore cannot be cancelled or modified again.

## User object
Keys: `name{first_name,last_name}`, `address{…zip}`, `email`, `payment_methods{id→method}`, `orders[]`. There is no membership tier. Authentication by name + zip matches `name.first_name`, `name.last_name` and `address.zip`.

## Payment methods
- Ids are `<source>_<7 digits>` with `source ∈ {credit_card, gift_card, paypal}`. The prefix always equals `source` (credit_card 239, gift_card 234, paypal 222).
- `gift_card`: `{source, balance, id}`. **The balance field is `balance`** (airline uses `amount`).
- `credit_card`: `{source, brand, last_four, id}`. `paypal`: `{source, id}`.
- Return refunds: the API accepts the original method or **any** id containing `gift_card` that belongs to the order's user (`return_delivered_order_items.py:25-29`).

## Products and items
- 50 products. `product_id` and `item_id` are **both 10-digit strings** (591 items). They come from separate id spaces, but look identical, so the wiki's "should not be confused" is a real risk.
- Variant: `{item_id, options{…}, available: bool, price}`. 379 variants are available and 212 are not.
- The item-replacement guard (`modify_pending_order_items.py:40-44`, `exchange_delivered_order_items.py:41-45`) requires `new_item_id ∈ products[old item's product_id].variants` (same product) **and** `available`. It does **not** require `new_item_id != item_id` (different option).

## Recorded trajectories (B0.4)
`historical_trajectories/gpt-4o-retail.json` (460 runs, 115 tasks × 4 trials, reward 1: 278) and `sonnet-35-new-retail.json` (920 runs, 115 tasks × 8 trials, reward 1: 637). The format is the same as in airline (OpenAI-style messages).
