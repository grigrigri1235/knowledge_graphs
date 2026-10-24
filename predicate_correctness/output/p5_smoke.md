# Part 5: smoke run of the lookups

Written by `state_tracker/run_lookups.py`. It checks that every lookup runs on the saved steps, and counts its
results. It does **not** say whether the values are right: that is the independent check (p5.md subtask 3)
and Part 6. The judge's values and evidence were not read; the predicates of a step come from the rule set
(the action's rules), not from the judge record.

- Records: all Part 2 step records. State: `state.walk` over each conversation, before the step. Arguments: the pending call's.
- A lookup runs on a record if its predicate is in one of the rules of the record's action.
- `missing` = the lookup's `if_missing` value was used (an object or field was missing, or the result was None).
- Time: 27 s.

## Airline

- Records used: 852 (luna_train_v5: 321 of 321, nano_train: 531 of 531), in 120 conversations; 204 have at least one code-type predicate.
- Lookup file check: 0 problems. Evaluation errors: 0. Replay mismatches while walking: 0; parse problems: 0.

| predicate | type | uses | if_missing | runs | true | false | unknown | missing | main missing reasons | errors |
|---|---|---|---|---|---|---|---|---|---|---|
| `booking_has_at_most_five_passengers` | argument | shown | unknown | 13 | 13 | 0 | 0 | 0 |  | 0 |
| `all_booking_passengers_share_flights_and_cabin` | argument | shown | unknown | 13 | 13 | 0 | 0 | 0 |  | 0 |
| `booking_payment_method_counts_within_limits` | argument | shown | unknown | 13 | 12 | 1 | 0 | 0 |  | 0 |
| `booking_payment_methods_found_in_user_profile` | database fact | shown | false | 13 | 13 | 0 | 0 | 0 |  | 0 |
| `booking_user_is_regular_member` | database fact | shown | false | 13 | 0 | 13 | 0 | 0 |  | 0 |
| `regular_member_booking_baggage_counts_correct` | argument | shown | unknown | 13 | 4 | 9 | 0 | 0 |  | 0 |
| `booking_user_is_silver_member` | database fact | shown | false | 13 | 2 | 11 | 0 | 0 |  | 0 |
| `silver_member_booking_baggage_counts_correct` | argument | shown | unknown | 13 | 4 | 9 | 0 | 0 |  | 0 |
| `booking_user_is_gold_member` | database fact | shown | false | 13 | 11 | 2 | 0 | 0 |  | 0 |
| `gold_member_booking_baggage_counts_correct` | argument | shown | unknown | 13 | 13 | 0 | 0 | 0 |  | 0 |
| `pending_flight_update_is_basic_economy` | database fact | shown | false | 136 | 55 | 81 | 0 | 0 |  | 0 |
| `pending_flight_segments_are_unchanged` | database fact | shown | false | 136 | 112 | 24 | 0 | 0 |  | 0 |
| `origin_destination_and_trip_type_preserved` | database fact | shown | false | 136 | 136 | 0 | 0 | 0 |  | 0 |
| `all_pending_flight_segments_have_one_cabin` | argument | shown | unknown | 136 | 136 | 0 | 0 | 0 |  | 0 |
| `pending_baggage_total_not_reduced` | database fact | shown | false | 13 | 13 | 0 | 0 | 0 |  | 0 |
| `pending_passenger_count_unchanged` | database fact | shown | false | 7 | 7 | 0 | 0 | 0 |  | 0 |
| `pending_flight_update_changes_flights` | database fact | shown | false | 136 | 24 | 112 | 0 | 0 |  | 0 |
| `reservation_has_business_cabin` | database fact | shown | false | 35 | 19 | 16 | 0 | 2 | TypeError: object not shown / None (2) | 0 |
| `reservation_has_basic_or_economy_cabin` | database fact | shown | false | 35 | 14 | 21 | 0 | 2 | TypeError: object not shown / None (2) | 0 |
| `reservation_has_travel_insurance` | database fact | shown | false | 35 | 15 | 20 | 0 | 2 | TypeError: object not shown / None (2) | 0 |
| `reservation_has_no_used_flight_segments` | database fact | shown | false | 35 | 30 | 5 | 0 | 2 | TypeError: object not shown / None (2) | 0 |

`uses` = shown, but also reads the database copy (see each reason): `origin_destination_and_trip_type_preserved`.

## Retail

- Records used: 4051 (luna_train_v5: 1729 of 1729, nano_train: 2322 of 2322), in 276 conversations; 3675 have at least one code-type predicate.
- Lookup file check: 0 problems. Evaluation errors: 0. Replay mismatches while walking: 0; parse problems: 0.

| predicate | type | uses | if_missing | runs | true | false | unknown | missing | main missing reasons | errors |
|---|---|---|---|---|---|---|---|---|---|---|
| `user_authenticated` | event | shown | false | 3675 | 3335 | 340 | 0 | 0 |  | 0 |
| `order_status_checked_pending` | database fact | shown | false | 397 | 381 | 16 | 0 | 0 |  | 0 |
| `order_status_checked_delivered` | database fact | shown | false | 273 | 241 | 32 | 0 | 1 | TypeError: object not shown / None (1) | 0 |
| `cancellation_reason_is_allowed` | argument | shown | unknown | 60 | 60 | 0 | 0 | 0 |  | 0 |
| `payment_method_differs_from_original` | database fact | shown | false | 10 | 6 | 4 | 0 | 0 |  | 0 |
| `payment_method_is_gift_card` | argument | shown | unknown | 387 | 49 | 337 | 1 | 1 | KeyError 'payment_method_id' (1) | 0 |
| `gift_card_balance_covers_order_total` | database fact | shown | false | 10 | 0 | 10 | 0 | 10 | KeyError 'balance' (10) | 0 |
| `item_replacements_are_available_same_product_different_option` | database fact | shown | false | 377 | 363 | 14 | 0 | 10 | TypeError: object not shown / None (10) | 0 |
| `gift_card_balance_covers_price_difference` | database fact | shown | false | 377 | 44 | 333 | 0 | 333 | KeyError 'balance' (321); TypeError: object not shown / None (11); KeyError 'payment_method_id' (1) | 0 |
| `return_refund_method_is_original_or_existing_gift_card` | database fact | shown | false | 154 | 153 | 1 | 0 | 0 |  | 0 |

