# Part 4: Tool Notes

Notes for `state_tracker/tool_table.json`. Written from the copied τ-bench tool code only
(`from_shieldagent/tau_bench/tau_bench/envs/<domain>/tools/*.py`), never from gold code. The replay check
(`output/p4_replay_check.md`) then tested the "changes the database" column on all 2,891 saved calls.

## How τ-bench runs a call
- Each tool has `invoke(data, **args) -> str`. `data` is the whole database (a dict of tables). Write tools change it
  in place.
- `Env.step` (`envs/base.py`) runs `invoke`. Any exception becomes the text `Error: <exception>`. An unknown tool
  name gives `Unknown action <name>`. We run calls the same way (`state.run_tool`).
- A failed call returns a text that starts with `Error`. In every tool, the checks come before the changes, so a
  failed call changes nothing. (Only an exception in the middle of the changes could leave a partial change, and
  that needs data that does not fit together, for example a payment id missing from its user.) The replay check
  confirms this on the data: 0 failed calls changed the database.
- `transfer_to_human_agents` ends the conversation (`terminate_tools` in `env.py`). Its code only returns
  "Transfer successful", so we run it like any other tool.

## Retail (16 tools)
| tool | changes the database | output | objects in the output (kind, id) |
|---|---|---|---|
| `calculate` | no | the result as text | none |
| `cancel_pending_order` | yes: order status, cancel reason, refunds; gift card balance | order | order, `order_id` |
| `exchange_delivered_order_items` | yes: order status "exchange requested" and the exchange fields | order | order, `order_id` |
| `find_user_id_by_email` | no | the user id as text | none (event log only) |
| `find_user_id_by_name_zip` | no | the user id as text | none (event log only) |
| `get_order_details` | no | order | order, `order_id` |
| `get_product_details` | no | product | product, `product_id`; each variant, item id |
| `get_user_details` | no | user | user, the `user_id` argument; each payment method, its id |
| `list_all_product_types` | no | {name: product id} | product_type, product id |
| `modify_pending_order_address` | yes: order address | order | order, `order_id` |
| `modify_pending_order_items` | yes: order items, payment entry, status "pending (item modified)"; gift card balance | order | order, `order_id` |
| `modify_pending_order_payment` | yes: payment and refund entries; gift card balances | order | order, `order_id` |
| `modify_user_address` | yes: the user's default address | user | user, the `user_id` argument; payment methods |
| `return_delivered_order_items` | yes: order status "return requested" and the return fields | order | order, `order_id` |
| `think` | no | "" | none |
| `transfer_to_human_agents` | no | "Transfer successful" | none |

## Airline (14 tools)
| tool | changes the database | output | objects in the output (kind, id) |
|---|---|---|---|
| `book_reservation` | yes: new reservation; user's reservation list; gift card amount; a used certificate is removed | reservation | reservation, `reservation_id` |
| `calculate` | no | the result as text | none |
| `cancel_reservation` | yes: status "cancelled", negative payment entries | reservation | reservation, `reservation_id` |
| `get_reservation_details` | no | reservation | reservation, `reservation_id` |
| `get_user_details` | no | user | user, the `user_id` argument; each payment method, its id |
| `list_all_airports` | no | {code: city} | airport, code |
| `search_direct_flight` | no | list of flights on the date | flight, `flight_number` (date: the `date` argument) |
| `search_onestop_flight` | no | list of [leg, leg] | flight, `flight_number` (date: the leg's `date` field) |
| `send_certificate` | yes: a certificate payment method for the user | text | none (event log only) |
| `think` | no | "" | none |
| `transfer_to_human_agents` | no | "Transfer successful" | none |
| `update_reservation_baggages` | yes: bag counts, payment entry; gift card amount | reservation | reservation, `reservation_id` |
| `update_reservation_flights` | yes: flights, payment entry; gift card amount | reservation | reservation, `reservation_id` |
| `update_reservation_passengers` | yes: passengers | reservation | reservation, `reservation_id` |

## Kinds of objects
| domain | kind | where in the database | id |
|---|---|---|---|
| both | `user` | `users` | the dict key (the user object has no id field) |
| both | `payment_method` | inside a user: `payment_methods` | its `id` (unique over all users; checked) |
| retail | `order` | `orders` | `order_id` |
| retail | `product` | `products` | `product_id` |
| retail | `variant` | inside a product: `variants` | its `item_id` (unique over all products; checked) |
| retail | `product_type` | built from `products`: `{name, product_id}` | `product_id` |
| airline | `reservation` | `reservations` | `reservation_id` |
| airline | `flight` | `flights` | `flight_number`; per-date data under `dates` |
| airline | `airport` | not in the data: a constant list in `list_all_airports` | the 3-letter code |

Nested kinds (`payment_method`, `variant`) are given as a copy of the nested object with the parent's id added
(`user_id`, `product_id`), both in the shown set and from `db_get`.

## Facts found in the code that matter for lookups
- **Retail gift cards** keep their money in `balance`; **airline gift cards and certificates** keep it in `amount`.
- **Airline `cancel_reservation`** does not check the status and does not refund any balance. It only adds negative
  payment entries and sets `status` to "cancelled". Reservations in the data files have no `status` field; only a
  cancelled one has it.
- **Airline `update_reservation_flights`** does not change the reservation's `cabin` field, and no airline tool
  changes flight seats. `book_reservation` does not change seats either.
- **Airline `book_reservation`** gives the ids HATHAT, HATHAU, HATHAV in that order, and `created_at` is always
  2024-05-15T15:00:00. It stores the `payment_methods` argument list itself as `payment_history`; later calls append
  to it. Our replay gives each tool a copy of the arguments, so the event log keeps the arguments as sent.
- **Airline `get_reservation_details`** gives "Error: user not found" for an unknown reservation (τ-bench's text).
- **Airline `search_direct_flight`** returns only flights with status "available" on that date. The output has no
  `date` field; the date is the call's argument.
- **Airline `search_onestop_flight`**: the second leg's status, seats and prices come from the first leg's date, even
  when the second leg is on the next day (its `date` field is right). The shown set keeps what was shown, under the
  leg's `date`.
- **Airline `send_certificate`** returns nothing (None) if the user already has all 3 certificate ids. This never
  happened in the saved runs.
- **Retail `find_user_id_*`** return only the user id as text. A user lookup that worked is in the event log
  (`events_where(tool=..., ok=True)`), not in the shown set.
- **Retail `modify_pending_order_items`** sets the status to "pending (item modified)", so a second item change on
  the same order fails ("non-pending order cannot be modified").
- **Retail `exchange_delivered_order_items` and `return_delivered_order_items`** set the status to "exchange
  requested" or "return requested". No money moves yet.

## Today's date
- Airline: "The current time is 2024-05-15 15:00:00 EST." (policy line 3). `state.today` =
  `datetime(2024, 5, 15, 15, 0, 0)`; `state.today_text` = "2024-05-15 15:00:00 EST".
- Retail: the policy states no current time, so `state.today` is None.
