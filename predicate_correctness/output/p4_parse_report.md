# Part 4: Shown-Set Parse Report

Made by `python3 -B -m state_tracker.replay_check` on 2026-10-22. How outputs are parsed: `state_tracker/README.md`
("Shown set") and `state_tracker/tool_table.json`.

## Rules
- Only outputs of calls that worked are parsed. A failed call (`Error…`) adds nothing.
- A tool whose `output` is `text` in the tool table has no objects by design (`calculate`, `think`,
  `transfer_to_human_agents`, `find_user_id_by_*`, `send_certificate`). These are not parse failures; the event
  log keeps their output.
- A parse failure is an output of a call that worked that does not have the form the tool table gives (for
  example, not JSON, or no id).

## Result
- **Parse failures: 0.**
- **Unknown tools (not in the tool table): 0.**

## Calls per tool
| run | domain | tool | calls | worked | failed | text output (no objects) | changed the database |
|---|---|---|---|---|---|---|---|
| `luna_train_v5` | airline | `book_reservation` | 4 | 4 | 0 | 0 | 4 |
| `luna_train_v5` | airline | `calculate` | 1 | 1 | 0 | 1 | 0 |
| `luna_train_v5` | airline | `cancel_reservation` | 7 | 7 | 0 | 0 | 7 |
| `luna_train_v5` | airline | `get_reservation_details` | 162 | 162 | 0 | 0 | 0 |
| `luna_train_v5` | airline | `get_user_details` | 51 | 49 | 2 | 0 | 0 |
| `luna_train_v5` | airline | `list_all_airports` | 4 | 4 | 0 | 0 | 0 |
| `luna_train_v5` | airline | `search_direct_flight` | 58 | 58 | 0 | 0 | 0 |
| `luna_train_v5` | airline | `search_onestop_flight` | 14 | 14 | 0 | 0 | 0 |
| `luna_train_v5` | airline | `transfer_to_human_agents` | 42 | 42 | 0 | 42 | 0 |
| `luna_train_v5` | airline | `update_reservation_baggages` | 4 | 4 | 0 | 0 | 4 |
| `luna_train_v5` | airline | `update_reservation_flights` | 24 | 21 | 3 | 0 | 14 |
| `luna_train_v5` | airline | `update_reservation_passengers` | 3 | 3 | 0 | 0 | 3 |
| `luna_train_v5` | retail | `calculate` | 9 | 9 | 0 | 9 | 0 |
| `luna_train_v5` | retail | `cancel_pending_order` | 26 | 26 | 0 | 0 | 26 |
| `luna_train_v5` | retail | `exchange_delivered_order_items` | 24 | 24 | 0 | 0 | 24 |
| `luna_train_v5` | retail | `find_user_id_by_email` | 34 | 30 | 4 | 30 | 0 |
| `luna_train_v5` | retail | `find_user_id_by_name_zip` | 109 | 106 | 3 | 106 | 0 |
| `luna_train_v5` | retail | `get_order_details` | 409 | 408 | 1 | 0 | 0 |
| `luna_train_v5` | retail | `get_product_details` | 103 | 103 | 0 | 0 | 0 |
| `luna_train_v5` | retail | `get_user_details` | 131 | 131 | 0 | 0 | 0 |
| `luna_train_v5` | retail | `list_all_product_types` | 10 | 10 | 0 | 0 | 0 |
| `luna_train_v5` | retail | `modify_pending_order_address` | 30 | 29 | 1 | 0 | 29 |
| `luna_train_v5` | retail | `modify_pending_order_items` | 38 | 38 | 0 | 0 | 38 |
| `luna_train_v5` | retail | `modify_pending_order_payment` | 3 | 3 | 0 | 0 | 3 |
| `luna_train_v5` | retail | `modify_user_address` | 13 | 13 | 0 | 0 | 13 |
| `luna_train_v5` | retail | `return_delivered_order_items` | 58 | 57 | 1 | 0 | 57 |
| `luna_train_v5` | retail | `transfer_to_human_agents` | 22 | 22 | 0 | 22 | 0 |
| `nano_train` | airline | `book_reservation` | 5 | 4 | 1 | 0 | 4 |
| `nano_train` | airline | `cancel_reservation` | 12 | 12 | 0 | 0 | 12 |
| `nano_train` | airline | `get_reservation_details` | 147 | 147 | 0 | 0 | 0 |
| `nano_train` | airline | `get_user_details` | 49 | 49 | 0 | 0 | 0 |
| `nano_train` | airline | `search_direct_flight` | 81 | 81 | 0 | 0 | 0 |
| `nano_train` | airline | `search_onestop_flight` | 17 | 17 | 0 | 0 | 0 |
| `nano_train` | airline | `transfer_to_human_agents` | 37 | 37 | 0 | 37 | 0 |
| `nano_train` | airline | `update_reservation_baggages` | 6 | 6 | 0 | 0 | 5 |
| `nano_train` | airline | `update_reservation_flights` | 68 | 58 | 10 | 0 | 10 |
| `nano_train` | airline | `update_reservation_passengers` | 4 | 4 | 0 | 0 | 3 |
| `nano_train` | retail | `calculate` | 1 | 1 | 0 | 1 | 0 |
| `nano_train` | retail | `cancel_pending_order` | 32 | 30 | 2 | 0 | 30 |
| `nano_train` | retail | `exchange_delivered_order_items` | 26 | 25 | 1 | 0 | 25 |
| `nano_train` | retail | `find_user_id_by_email` | 38 | 35 | 3 | 35 | 0 |
| `nano_train` | retail | `find_user_id_by_name_zip` | 118 | 114 | 4 | 114 | 0 |
| `nano_train` | retail | `get_order_details` | 429 | 423 | 6 | 0 | 0 |
| `nano_train` | retail | `get_product_details` | 107 | 107 | 0 | 0 | 0 |
| `nano_train` | retail | `get_user_details` | 136 | 136 | 0 | 0 | 0 |
| `nano_train` | retail | `list_all_product_types` | 12 | 12 | 0 | 0 | 0 |
| `nano_train` | retail | `modify_pending_order_address` | 28 | 23 | 5 | 0 | 20 |
| `nano_train` | retail | `modify_pending_order_items` | 30 | 29 | 1 | 0 | 29 |
| `nano_train` | retail | `modify_pending_order_payment` | 3 | 3 | 0 | 0 | 3 |
| `nano_train` | retail | `modify_user_address` | 13 | 13 | 0 | 0 | 13 |
| `nano_train` | retail | `return_delivered_order_items` | 77 | 60 | 17 | 0 | 60 |
| `nano_train` | retail | `transfer_to_human_agents` | 22 | 21 | 1 | 21 | 0 |

## Shown objects at the end of the conversations
Sum over the conversations of the objects in the shown set at the end (one per kind and id).

| run | domain | kind | objects |
|---|---|---|---|
| `luna_train_v5` | airline | `airport` | 80 |
| `luna_train_v5` | airline | `flight` | 167 |
| `luna_train_v5` | airline | `payment_method` | 166 |
| `luna_train_v5` | airline | `reservation` | 154 |
| `luna_train_v5` | airline | `user` | 48 |
| `luna_train_v5` | retail | `order` | 400 |
| `luna_train_v5` | retail | `payment_method` | 205 |
| `luna_train_v5` | retail | `product` | 101 |
| `luna_train_v5` | retail | `product_type` | 500 |
| `luna_train_v5` | retail | `user` | 133 |
| `luna_train_v5` | retail | `variant` | 1,456 |
| `nano_train` | airline | `flight` | 184 |
| `nano_train` | airline | `payment_method` | 162 |
| `nano_train` | airline | `reservation` | 130 |
| `nano_train` | airline | `user` | 46 |
| `nano_train` | retail | `order` | 394 |
| `nano_train` | retail | `payment_method` | 197 |
| `nano_train` | retail | `product` | 106 |
| `nano_train` | retail | `product_type` | 600 |
| `nano_train` | retail | `user` | 129 |
| `nano_train` | retail | `variant` | 1,504 |
