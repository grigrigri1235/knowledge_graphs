# Tracker v4: dev check on the 200 development conversations (pass marks, by pattern)

> **Development check, not a result.** In-sample data (the p12a set). Disagreements are shown by pattern only, never as single examples.

Written by `scoring/v4_dev_check.py` on 2026-10-24 08:43 UTC from `output/eval_v4/dev/offline_real_rows.jsonl` (backend real, run `v4dev_real_20261024T084043Z`): 200 conversations, 2,164 checks.

## Overall: **PASS**

| id | pass mark | result | pass |
|---|---|---|---|
| D1 | tiny blocks <= 1.5 x the stand-in's blocks (same checks) | tiny 37 vs stand-in 32 on 2,164 checks (1.16x) | PASS |
| D2 | unclear answers <= 2 % of tiny calls | 4 of 783 calls (0.5 %); statuses {"no": 437, "not_added": 8, "quote_failed": 1, "unclear": 3, "yes": 334} | PASS |
| D3 | two-key disagreements: 0 | 0 | PASS |
| D4 | state errors: 0 | 0  | PASS |
| D5 | 100 % of block messages name a line the agent can fix in one turn | 37 of 37 block messages name a fixable line (100.0 %); not checked 0 | PASS |

Run validity (not a pass mark): missing answers 0, guard run errors 0, judge calls 0, network events 0: **valid**. D5 uses `scoring/v4_message_check.fixable_line_problems` (A7) on the message plan of each block, run inside the offline run.

## Unclear answers by question

| question | no | not_added | quote_failed | unclear | yes |
|---|---|---|---|---|---|
| K1 | 12 | 0 | 1 | 0 | 170 |
| K3 | 51 | 0 | 0 | 0 | 66 |
| K4 | 15 | 0 | 0 | 0 | 0 |
| K6 | 0 | 0 | 0 | 0 | 4 |
| K7 | 14 | 0 | 0 | 0 | 9 |
| K8 | 1 | 0 | 0 | 0 | 2 |
| K10 | 0 | 0 | 0 | 0 | 2 |
| K12 | 222 | 0 | 0 | 0 | 3 |
| K13 | 101 | 0 | 0 | 3 | 60 |
| K16 | 14 | 0 | 0 | 0 | 9 |
| K17 | 0 | 8 | 0 | 0 | 0 |
| K18 | 7 | 0 | 0 | 0 | 9 |

## Tiny answers vs the stand-in, per question (asked facts on the same checks)

Asked facts 1,168: agree 1,128, disagree 40.

| question | agree | disagree: tiny blocks | disagree: tiny allows | disagree: direction unknown |
|---|---|---|---|---|
| K1 | 255 | 6 | 6 | 0 |
| K3 | 75 | 0 | 1 | 0 |
| K4 | 22 | 0 | 0 | 0 |
| K6 | 4 | 0 | 0 | 0 |
| K7 | 11 | 0 | 0 | 0 |
| K8 | 2 | 0 | 1 | 0 |
| K10 | 2 | 0 | 1 | 0 |
| K12 | 674 | 4 | 0 | 0 |
| K13 | 66 | 14 | 7 | 0 |
| K16 | 8 | 5 | 1 | 0 |
| K17 | 8 | 0 | 0 | 0 |
| K18 | 9 | 0 | 0 | 0 |

## Disagreements per fact

| fact | disagree: tiny blocks | disagree: tiny allows | disagree: direction unknown |
|---|---|---|---|
| `agent_reminded_user_to_include_all_items_for_exchange` | 0 | 1 | 0 |
| `pending_database_change_details_listed_and_explicitly_confirmed` | 3 | 3 | 0 |
| `pending_response_offers_any_compensation_certificate` | 1 | 0 | 0 |
| `pending_response_offers_cancelled_flight_certificate` | 2 | 0 | 0 |
| `pending_response_offers_delayed_flight_certificate` | 1 | 0 | 0 |
| `request_cannot_be_handled_with_available_tools` | 14 | 7 | 0 |
| `user_chose_pending_payment_method` | 1 | 0 | 0 |
| `user_complained_about_relevant_flight_situation` | 0 | 1 | 0 |
| `user_explicitly_confirmed_pending_action` | 2 | 2 | 0 |
| `user_explicitly_requested_compensation` | 0 | 1 | 0 |
| `user_selected_eligible_flight_change_payment_method` | 0 | 1 | 0 |

## Changed decisions (tiny vs stand-in): by tool and by the question whose answer differed

- **tiny allow, stand-in block**: by tool transfer_to_human_agents 8, update_reservation_flights 3, exchange_delivered_order_items 1, modify_pending_order_items 1, update_reservation_baggages 1; by question K13 7, K1 5, K3 1, K16 1, - 1
- **tiny block, stand-in allow**: by tool transfer_to_human_agents 14, update_reservation_flights 2, modify_pending_order_payment 1, respond 1, update_reservation_passengers 1; by question K13 14, K1 5, K16 5, K12 3, K8 1, K10 1

## Missing lines named at the tiny arm's blocks (per line kind)

| line kind | at all blocks | at blocks the stand-in allows |
|---|---|---|
| checked bags | 1 | 0 |
| payment method | 3 | 0 |
| payment method for the price difference | 1 | 0 |

