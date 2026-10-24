# Part 4: Replay Check

Made by `python3 -B -m state_tracker.replay_check` (run in `predicate_correctness/`) on 2026-10-22.
Log: `output/logs/p4_replay_check.log`. Code: `state_tracker/state.py`, `state_tracker/replay_check.py`.

## What was checked
- **All executed tool calls of all saved conversations** (the 4 runs of Part 2, 396 conversations). Each
  conversation is replayed once, from a fresh copy of τ-bench's data, over its full `executed` list. Calls that
  ran through the cap override are in `executed`, so they are replayed too. Blocked calls are not.
- **How the call is run:** τ-bench's own tool code (the copy, unchanged), the same way as `Env.step`: an
  exception becomes `Error: <exception>`. The arguments are read from the agent's message (`tool_calls`), and
  the output is matched to its tool message by `tool_call_id`.
- **Comparison:** the replayed output must be exactly the same string as the saved tool message. We also count
  outputs that are the same JSON value (for example, the same object with other spacing). With exact equality,
  the JSON count can only be the same or higher.

## Result
| run | domain | conversations | calls checked | exact match | JSON-equal | mismatches |
|---|---|---|---|---|---|---|
| `luna_train_v5` | airline | 60 | 374 | 374 | 374 | 0 |
| `luna_train_v5` | retail | 138 | 1,019 | 1,019 | 1,019 | 0 |
| `nano_train` | airline | 60 | 426 | 426 | 426 | 0 |
| `nano_train` | retail | 138 | 1,072 | 1,072 | 1,072 | 0 |
| all | | 396 | 2,891 | 2,891 | 2,891 | 0 |

**Every replayed output equals the saved one (2,891 of 2,891, exact string).** So the database copy is the database of the real run at every step, and there is no mismatch to explain.

## Which calls changed the database
The database was fingerprinted (sha256 of its JSON) after every call.

| run | domain | read-only tool changed it | failed call changed it | write call that worked but changed nothing |
|---|---|---|---|---|
| `luna_train_v5` | airline | 0 | 0 | 7 |
| `luna_train_v5` | retail | 0 | 0 | 0 |
| `nano_train` | airline | 0 | 0 | 50 |
| `nano_train` | retail | 0 | 0 | 3 |

- So the `changes_db` column of `tool_table.json` holds on the data: only write tools changed the database, and
  a failed call never did.
- 60 write calls worked but left the database the same. In 60 of them, the same call (same
  arguments) had already worked earlier in the conversation, so the new values were already there. Example:
  `update_reservation_flights` to change the cabin. The first call sets the new prices and adds a payment;
  a repeated call finds the same prices, so the price difference is 0 and nothing changes. τ-bench never
  updates the reservation's `cabin` field, so the agent may see the old cabin and try again.
  None of this is a replay problem: τ-bench's code gives the same result. All cases:
  - `luna_train_v5/airline/task7/trial0/step17 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field business`
  - `luna_train_v5/airline/task7/trial1/step15 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field business`
  - `luna_train_v5/airline/task34/trial1/step12 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `luna_train_v5/airline/task7/trial2/step15 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field business`
  - `luna_train_v5/airline/task5/trial2/step9 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `luna_train_v5/airline/task5/trial2/step12 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `luna_train_v5/airline/task5/trial2/step15 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `nano_train/airline/task5/trial0/step15 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `nano_train/airline/task5/trial0/step23 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `nano_train/airline/task5/trial0/step24 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `nano_train/airline/task5/trial0/step25 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `nano_train/airline/task5/trial0/step26 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `nano_train/airline/task5/trial0/step27 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `nano_train/airline/task5/trial0/step28 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `nano_train/airline/task5/trial0/step29 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `nano_train/airline/task34/trial0/step7 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `nano_train/airline/task33/trial0/step20 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field basic_economy`
  - `nano_train/airline/task33/trial0/step22 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field basic_economy`
  - `nano_train/airline/task33/trial0/step23 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field basic_economy`
  - `nano_train/airline/task33/trial0/step24 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field basic_economy`
  - `nano_train/airline/task33/trial0/step25 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field basic_economy`
  - `nano_train/airline/task33/trial0/step26 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field basic_economy`
  - `nano_train/airline/task33/trial0/step27 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field basic_economy`
  - `nano_train/airline/task33/trial0/step28 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field basic_economy`
  - `nano_train/airline/task33/trial0/step29 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field basic_economy`
  - `nano_train/airline/task5/trial1/step14 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `nano_train/airline/task5/trial1/step16 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `nano_train/airline/task5/trial1/step17 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `nano_train/airline/task5/trial1/step19 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `nano_train/airline/task5/trial1/step21 update_reservation_baggages: an earlier call with the same arguments worked: yes; args {"reservation_id": "FQ8APE", "total_baggages": 3, "nonfree_baggages": 1, "payment_id": "gift_card_8190333"}`
  - `nano_train/airline/task5/trial1/step22 update_reservation_passengers: an earlier call with the same arguments worked: yes; args {"reservation_id": "FQ8APE", "passengers": [{"first_name": "Omar", "last_name": "Rossi", "dob": "1970-06-06"}]}`
  - `nano_train/airline/task5/trial1/step23 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `nano_train/airline/task5/trial1/step24 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `nano_train/airline/task5/trial1/step25 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `nano_train/airline/task5/trial1/step26 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `nano_train/airline/task5/trial1/step28 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `nano_train/airline/task5/trial1/step29 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `nano_train/airline/task34/trial1/step7 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument economy, reservation's cabin field basic_economy`
  - `nano_train/airline/task14/trial1/step7 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field economy`
  - `nano_train/airline/task14/trial1/step8 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field economy`
  - `nano_train/airline/task14/trial1/step9 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field economy`
  - `nano_train/airline/task14/trial1/step11 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field economy`
  - `nano_train/airline/task14/trial1/step12 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field economy`
  - `nano_train/airline/task14/trial1/step13 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field economy`
  - `nano_train/airline/task14/trial1/step15 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field economy`
  - `nano_train/airline/task14/trial1/step16 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field economy`
  - `nano_train/airline/task14/trial1/step17 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field economy`
  - `nano_train/airline/task14/trial1/step18 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field economy`
  - `nano_train/airline/task14/trial1/step19 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field economy`
  - `nano_train/airline/task14/trial1/step20 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field economy`
  - `nano_train/airline/task14/trial1/step21 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field economy`
  - `nano_train/airline/task14/trial1/step22 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field economy`
  - `nano_train/airline/task14/trial1/step23 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field economy`
  - `nano_train/airline/task14/trial1/step25 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field economy`
  - `nano_train/airline/task14/trial1/step26 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field economy`
  - `nano_train/airline/task14/trial1/step27 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field economy`
  - `nano_train/airline/task14/trial1/step28 update_reservation_flights: an earlier call with the same arguments worked: yes; same flights as the reservation: yes; cabin argument business, reservation's cabin field economy`
  - `nano_train/retail/task41/trial0/step24 modify_pending_order_address: an earlier call with the same arguments worked: yes; new address equals the order's address: yes`
  - `nano_train/retail/task111/trial2/step9 modify_pending_order_address: an earlier call with the same arguments worked: yes; new address equals the order's address: yes`
  - `nano_train/retail/task111/trial2/step11 modify_pending_order_address: an earlier call with the same arguments worked: yes; new address equals the order's address: yes`

## Each step record gets the same state from `build_state`
For every Part 2 step record, `build_state(rec["history"], rec)` (fresh copy, replay of the history only) was
compared with the one-pass state at the same point: number of events, shown set (with which event showed each
object), and the database fingerprint. Also checked: the events equal the tool calls in the history, the
domain, the pending action, no mismatch, and today's date (airline only).

| run | domain | records | same | seconds |
|---|---|---|---|---|
| `luna_train_v5` | airline | 321 | 321 | 46 |
| `luna_train_v5` | retail | 1,729 | 1,729 | 104 |
| `nano_train` | airline | 531 | 531 | 80 |
| `nano_train` | retail | 2,322 | 2,322 | 142 |

All records give the same state.

## Other checks
- The system message of 396 of 396 conversations is exactly the copied policy text, so
  `build_state` can tell the domain from it.
- Tool messages without a matching call, or calls without an output: 0.
- The arguments in the agent's message equal the attempt's saved `kwargs` for every executed tool call (0 differences).

## Failed calls (worked = false)
Calls whose output starts with `Error` (τ-bench's failed outputs). They are in the event log as failed and add
nothing to the shown set. An output like `Error: X.invoke() got an unexpected keyword argument …` comes from a
call with a wrong argument name: τ-bench's `Env.step` turns the exception into this text, and the replay gives
the same text.

| run | domain | tool | output | count |
|---|---|---|---|---|
| `luna_train_v5` | airline | `get_user_details` | `Error: user not found` | 2 |
| `luna_train_v5` | airline | `update_reservation_flights` | `Error: not enough seats on flight HAT290` | 3 |
| `luna_train_v5` | retail | `find_user_id_by_email` | `Error: user not found` | 4 |
| `luna_train_v5` | retail | `find_user_id_by_name_zip` | `Error: user not found` | 3 |
| `luna_train_v5` | retail | `get_order_details` | `Error: order not found` | 1 |
| `luna_train_v5` | retail | `modify_pending_order_address` | `Error: non-pending order cannot be modified` | 1 |
| `luna_train_v5` | retail | `return_delivered_order_items` | `Error: non-delivered order cannot be returned` | 1 |
| `nano_train` | airline | `book_reservation` | `Error: not enough seats on flight HAT213` | 1 |
| `nano_train` | airline | `update_reservation_flights` | `Error: gift card balance is not enough` | 5 |
| `nano_train` | airline | `update_reservation_flights` | `Error: not enough seats on flight HAT290` | 2 |
| `nano_train` | airline | `update_reservation_flights` | `Error: flight HAT238 not available on date 2024-05-14` | 2 |
| `nano_train` | airline | `update_reservation_flights` | `Error: payment method not found` | 1 |
| `nano_train` | retail | `cancel_pending_order` | `Error: non-pending order cannot be cancelled` | 2 |
| `nano_train` | retail | `exchange_delivered_order_items` | `Error: non-delivered order cannot be exchanged` | 1 |
| `nano_train` | retail | `find_user_id_by_email` | `Error: user not found` | 3 |
| `nano_train` | retail | `find_user_id_by_name_zip` | `Error: user not found` | 4 |
| `nano_train` | retail | `get_order_details` | `Error: order not found` | 6 |
| `nano_train` | retail | `modify_pending_order_address` | `Error: non-pending order cannot be modified` | 5 |
| `nano_train` | retail | `modify_pending_order_items` | `Error: non-pending order cannot be modified` | 1 |
| `nano_train` | retail | `return_delivered_order_items` | `Error: non-delivered order cannot be returned` | 17 |
| `nano_train` | retail | `transfer_to_human_agents` | `Error: TransferToHumanAgents.invoke() got an unexpected keyword argument 'Yes, modify skat…` | 1 |
