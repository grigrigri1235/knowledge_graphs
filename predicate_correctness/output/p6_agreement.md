# Part 6: tracker values vs judge values

Written by `state_tracker/replay.py`. For every Part 2 step record (4,903) and every code-type predicate
(argument, database fact, event) in the rules of the step's circuit, the frozen lookup ran on the state before
the step, and its value is compared with the judge's saved value. Conversation and mixed predicates are not
compared. No LLM calls; the judge values are the saved ones.

- **Values:** true, false, unknown (judge: null; tracker: `if_missing` = unknown, or an error).
- **Blocked step:** `guard.action_allowed == false` (576 steps; 44 of them still ran through the cap override).
- **Disagreement:** the two values differ, including one known and one unknown. Both unknown is not a
  disagreement. Every disagreement is in `output/p6_disagreements.jsonl`, with the objects and events the lookup
  read.
- **Agreement when both known:** both agree / (both agree + judge true, tracker false + judge false, tracker true).
- Lookup files (frozen, unchanged): airline sha256 `882ca35ed6a1bbda1ea97d1eed87dd36246b2111cc1d4d47c5645ce12b701dc7`, retail `77918b7727831f8c18353f5b5dce89d7e05017aa4db11f31722ee23cc41044a4`.
- Time: 28 s.

## Per run and domain

| run, domain | steps | steps with a code-type predicate | judge values | judge values replaced by the tracker | replaced with a different value | tracker unknown | tracker true / false | errors | replay mismatches |
|---|---|---|---|---|---|---|---|---|---|
| luna_train_v5 airline | 321 | 48 | 2,224 | 222 (10.0 %) | 5 (2.3 %) | 0 (0.0 %) | 150 / 72 | 0 | 0 |
| luna_train_v5 retail | 1,729 | 1,562 | 5,489 | 2,180 (39.7 %) | 25 (1.1 %) | 0 (0.0 %) | 1,849 / 331 | 0 | 0 |
| nano_train airline | 531 | 156 | 3,877 | 748 (19.3 %) | 62 (8.3 %) | 0 (0.0 %) | 496 / 252 | 0 | 0 |
| nano_train retail | 2,322 | 2,113 | 8,614 | 3,540 (41.1 %) | 170 (4.8 %) | 1 (0.0 %) | 2,783 / 756 | 0 | 0 |
| **all** | 4,903 | 3,879 | 20,204 | 6,690 (33.1 %) | 262 (3.9 %) | 1 (0.0 %) | 5,278 / 1,411 | 0 | 0 |

"Replaced" = the code-type values: in "TGR + tracker" the tracker sets them instead of the judge. "With a different value" counts all disagreements, including one side unknown.

**Per run and domain: agreement**

| run, domain | values | both agree (true / false) | judge true, tracker false | judge false, tracker true | either unknown (judge only / tracker only / both) | agreement when both known |
|---|---|---|---|---|---|---|
| luna_train_v5 airline | 222 | 217 (150 / 67) | 5 | 0 | 0 (0 / 0 / 0) | 97.7 % |
| luna_train_v5 retail | 2180 | 2155 (1842 / 313) | 3 | 7 | 15 (15 / 0 / 0) | 99.5 % |
| nano_train airline | 748 | 686 (481 / 205) | 33 | 0 | 29 (29 / 0 / 0) | 95.4 % |
| nano_train retail | 3540 | 3370 (2712 / 658) | 44 | 63 | 63 (62 / 1 / 0) | 96.9 % |
| **all** | 6690 | 6428 (5185 / 1243) | 85 | 70 | 107 (106 / 1 / 0) | 97.6 % |

**Per agent run, blocked steps only**

| run, domain | values | both agree (true / false) | judge true, tracker false | judge false, tracker true | either unknown (judge only / tracker only / both) | agreement when both known |
|---|---|---|---|---|---|---|
| luna_train_v5 airline | 27 | 27 (21 / 6) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| luna_train_v5 retail | 212 | 199 (142 / 57) | 1 | 7 | 5 (5 / 0 / 0) | 96.1 % |
| nano_train airline | 305 | 272 (194 / 78) | 4 | 0 | 29 (29 / 0 / 0) | 98.6 % |
| nano_train retail | 1372 | 1232 (784 / 448) | 18 | 63 | 59 (58 / 1 / 0) | 93.8 % |
| **all** | 1916 | 1730 (1141 / 589) | 23 | 70 | 93 (92 / 1 / 0) | 94.9 % |

## Per type

**All steps**

| type | values | both agree (true / false) | judge true, tracker false | judge false, tracker true | either unknown (judge only / tracker only / both) | agreement when both known |
|---|---|---|---|---|---|---|
| argument | 661 | 660 (304 / 356) | 0 | 0 | 1 (0 / 1 / 0) | 100.0 % |
| database fact | 2354 | 2156 (1609 / 547) | 85 | 14 | 99 (99 / 0 / 0) | 95.6 % |
| event | 3675 | 3612 (3272 / 340) | 0 | 56 | 7 (7 / 0 / 0) | 98.5 % |
| **all** | 6690 | 6428 (5185 / 1243) | 85 | 70 | 107 (106 / 1 / 0) | 97.6 % |

**Allowed steps**

| type | values | both agree (true / false) | judge true, tracker false | judge false, tracker true | either unknown (judge only / tracker only / both) | agreement when both known |
|---|---|---|---|---|---|---|
| argument | 315 | 315 (202 / 113) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| database fact | 1212 | 1136 (878 / 258) | 62 | 0 | 14 (14 / 0 / 0) | 94.8 % |
| event | 3247 | 3247 (2964 / 283) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| **all** | 4774 | 4698 (4044 / 654) | 62 | 0 | 14 (14 / 0 / 0) | 98.7 % |

**Blocked steps**

| type | values | both agree (true / false) | judge true, tracker false | judge false, tracker true | either unknown (judge only / tracker only / both) | agreement when both known |
|---|---|---|---|---|---|---|
| argument | 346 | 345 (102 / 243) | 0 | 0 | 1 (0 / 1 / 0) | 100.0 % |
| database fact | 1142 | 1020 (731 / 289) | 23 | 14 | 85 (85 / 0 / 0) | 96.5 % |
| event | 428 | 365 (308 / 57) | 0 | 56 | 7 (7 / 0 / 0) | 86.7 % |
| **all** | 1916 | 1730 (1141 / 589) | 23 | 70 | 93 (92 / 1 / 0) | 94.9 % |

**Blocked steps, predicate in a violated rule (block-causing)**

| type | values | both agree (true / false) | judge true, tracker false | judge false, tracker true | either unknown (judge only / tracker only / both) | agreement when both known |
|---|---|---|---|---|---|---|
| argument | 19 | 19 (18 / 1) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| database fact | 136 | 84 (36 / 48) | 3 | 14 | 35 (35 / 0 / 0) | 83.2 % |
| event | 120 | 57 (0 / 57) | 0 | 56 | 7 (7 / 0 / 0) | 50.4 % |
| **all** | 275 | 160 (54 / 106) | 3 | 70 | 42 (42 / 0 / 0) | 68.7 % |

**By `uses` of the lookup (all steps; for argument lookups `uses` is a placeholder)**

| type, uses | values | both agree (true / false) | judge true, tracker false | judge false, tracker true | either unknown (judge only / tracker only / both) | agreement when both known |
|---|---|---|---|---|---|---|
| argument, shown | 661 | 660 (304 / 356) | 0 | 0 | 1 (0 / 1 / 0) | 100.0 % |
| database fact, shown | 2354 | 2156 (1609 / 547) | 85 | 14 | 99 (99 / 0 / 0) | 95.6 % |
| event, shown | 3675 | 3612 (3272 / 340) | 0 | 56 | 7 (7 / 0 / 0) | 98.5 % |
| **all** | 6690 | 6428 (5185 / 1243) | 85 | 70 | 107 (106 / 1 / 0) | 97.6 % |

## Per predicate: airline

**All steps**

| predicate (type) | values | both agree (true / false) | judge true, tracker false | judge false, tracker true | either unknown (judge only / tracker only / both) | agreement when both known |
|---|---|---|---|---|---|---|
| `booking_has_at_most_five_passengers` (argument) | 13 | 13 (13 / 0) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `all_booking_passengers_share_flights_and_cabin` (argument) | 13 | 13 (13 / 0) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `booking_payment_method_counts_within_limits` (argument) | 13 | 13 (12 / 1) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `booking_payment_methods_found_in_user_profile` (database fact) | 13 | 13 (13 / 0) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `booking_user_is_regular_member` (database fact) | 13 | 13 (0 / 13) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `regular_member_booking_baggage_counts_correct` (argument) | 13 | 13 (4 / 9) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `booking_user_is_silver_member` (database fact) | 13 | 13 (2 / 11) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `silver_member_booking_baggage_counts_correct` (argument) | 13 | 13 (4 / 9) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `booking_user_is_gold_member` (database fact) | 13 | 13 (11 / 2) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `gold_member_booking_baggage_counts_correct` (argument) | 13 | 13 (13 / 0) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `pending_flight_update_is_basic_economy` (database fact) | 136 | 97 (53 / 44) | 37 | 0 | 2 (2 / 0 / 0) | 72.4 % |
| `pending_flight_segments_are_unchanged` (database fact) | 136 | 132 (109 / 23) | 0 | 0 | 4 (4 / 0 / 0) | 100.0 % |
| `origin_destination_and_trip_type_preserved` (database fact) | 136 | 130 (130 / 0) | 0 | 0 | 6 (6 / 0 / 0) | 100.0 % |
| `all_pending_flight_segments_have_one_cabin` (argument) | 136 | 136 (136 / 0) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `pending_baggage_total_not_reduced` (database fact) | 13 | 13 (13 / 0) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `pending_passenger_count_unchanged` (database fact) | 7 | 7 (7 / 0) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `pending_flight_update_changes_flights` (database fact) | 136 | 132 (23 / 109) | 0 | 0 | 4 (4 / 0 / 0) | 100.0 % |
| `reservation_has_business_cabin` (database fact) | 35 | 33 (19 / 14) | 0 | 0 | 2 (2 / 0 / 0) | 100.0 % |
| `reservation_has_basic_or_economy_cabin` (database fact) | 35 | 33 (14 / 19) | 0 | 0 | 2 (2 / 0 / 0) | 100.0 % |
| `reservation_has_travel_insurance` (database fact) | 35 | 33 (15 / 18) | 0 | 0 | 2 (2 / 0 / 0) | 100.0 % |
| `reservation_has_no_used_flight_segments` (database fact) | 35 | 27 (27 / 0) | 1 | 0 | 7 (7 / 0 / 0) | 96.4 % |
| **all** | 970 | 903 (631 / 272) | 38 | 0 | 29 (29 / 0 / 0) | 96.0 % |

**Blocked steps**

| predicate (type) | values | both agree (true / false) | judge true, tracker false | judge false, tracker true | either unknown (judge only / tracker only / both) | agreement when both known |
|---|---|---|---|---|---|---|
| `booking_has_at_most_five_passengers` (argument) | 4 | 4 (4 / 0) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `all_booking_passengers_share_flights_and_cabin` (argument) | 4 | 4 (4 / 0) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `booking_payment_method_counts_within_limits` (argument) | 4 | 4 (3 / 1) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `booking_payment_methods_found_in_user_profile` (database fact) | 4 | 4 (4 / 0) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `booking_user_is_regular_member` (database fact) | 4 | 4 (0 / 4) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `regular_member_booking_baggage_counts_correct` (argument) | 4 | 4 (2 / 2) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `booking_user_is_silver_member` (database fact) | 4 | 4 (1 / 3) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `silver_member_booking_baggage_counts_correct` (argument) | 4 | 4 (2 / 2) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `booking_user_is_gold_member` (database fact) | 4 | 4 (3 / 1) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `gold_member_booking_baggage_counts_correct` (argument) | 4 | 4 (4 / 0) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `pending_flight_update_is_basic_economy` (database fact) | 45 | 39 (30 / 9) | 4 | 0 | 2 (2 / 0 / 0) | 90.7 % |
| `pending_flight_segments_are_unchanged` (database fact) | 45 | 41 (24 / 17) | 0 | 0 | 4 (4 / 0 / 0) | 100.0 % |
| `origin_destination_and_trip_type_preserved` (database fact) | 45 | 39 (39 / 0) | 0 | 0 | 6 (6 / 0 / 0) | 100.0 % |
| `all_pending_flight_segments_have_one_cabin` (argument) | 45 | 45 (45 / 0) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `pending_baggage_total_not_reduced` (database fact) | 3 | 3 (3 / 0) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `pending_flight_update_changes_flights` (database fact) | 45 | 41 (17 / 24) | 0 | 0 | 4 (4 / 0 / 0) | 100.0 % |
| `reservation_has_business_cabin` (database fact) | 16 | 14 (5 / 9) | 0 | 0 | 2 (2 / 0 / 0) | 100.0 % |
| `reservation_has_basic_or_economy_cabin` (database fact) | 16 | 14 (9 / 5) | 0 | 0 | 2 (2 / 0 / 0) | 100.0 % |
| `reservation_has_travel_insurance` (database fact) | 16 | 14 (7 / 7) | 0 | 0 | 2 (2 / 0 / 0) | 100.0 % |
| `reservation_has_no_used_flight_segments` (database fact) | 16 | 9 (9 / 0) | 0 | 0 | 7 (7 / 0 / 0) | 100.0 % |
| **all** | 332 | 299 (215 / 84) | 4 | 0 | 29 (29 / 0 / 0) | 98.7 % |

## Per predicate: retail

**All steps**

| predicate (type) | values | both agree (true / false) | judge true, tracker false | judge false, tracker true | either unknown (judge only / tracker only / both) | agreement when both known |
|---|---|---|---|---|---|---|
| `user_authenticated` (event) | 3675 | 3612 (3272 / 340) | 0 | 56 | 7 (7 / 0 / 0) | 98.5 % |
| `order_status_checked_pending` (database fact) | 397 | 381 (380 / 1) | 15 | 0 | 1 (1 / 0 / 0) | 96.2 % |
| `order_status_checked_delivered` (database fact) | 273 | 246 (241 / 5) | 27 | 0 | 0 (0 / 0 / 0) | 90.1 % |
| `cancellation_reason_is_allowed` (argument) | 60 | 60 (60 / 0) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `payment_method_differs_from_original` (database fact) | 10 | 10 (6 / 4) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `payment_method_is_gift_card` (argument) | 387 | 386 (49 / 337) | 0 | 0 | 1 (0 / 1 / 0) | 100.0 % |
| `gift_card_balance_covers_order_total` (database fact) | 10 | 10 (0 / 10) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `item_replacements_are_available_same_product_different_option` (database fact) | 377 | 369 (363 / 6) | 2 | 0 | 6 (6 / 0 / 0) | 99.5 % |
| `gift_card_balance_covers_price_difference` (database fact) | 377 | 297 (30 / 267) | 3 | 14 | 63 (63 / 0 / 0) | 94.6 % |
| `return_refund_method_is_original_or_existing_gift_card` (database fact) | 154 | 154 (153 / 1) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| **all** | 5720 | 5525 (4554 / 971) | 47 | 70 | 78 (77 / 1 / 0) | 97.9 % |

**Blocked steps**

| predicate (type) | values | both agree (true / false) | judge true, tracker false | judge false, tracker true | either unknown (judge only / tracker only / both) | agreement when both known |
|---|---|---|---|---|---|---|
| `user_authenticated` (event) | 428 | 365 (308 / 57) | 0 | 56 | 7 (7 / 0 / 0) | 86.7 % |
| `order_status_checked_pending` (database fact) | 218 | 210 (209 / 1) | 7 | 0 | 1 (1 / 0 / 0) | 96.8 % |
| `order_status_checked_delivered` (database fact) | 91 | 83 (78 / 5) | 8 | 0 | 0 (0 / 0 / 0) | 91.2 % |
| `cancellation_reason_is_allowed` (argument) | 2 | 2 (2 / 0) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `payment_method_differs_from_original` (database fact) | 4 | 4 (0 / 4) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `payment_method_is_gift_card` (argument) | 275 | 274 (36 / 238) | 0 | 0 | 1 (0 / 1 / 0) | 100.0 % |
| `gift_card_balance_covers_order_total` (database fact) | 4 | 4 (0 / 4) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| `item_replacements_are_available_same_product_different_option` (database fact) | 271 | 263 (257 / 6) | 2 | 0 | 6 (6 / 0 / 0) | 99.2 % |
| `gift_card_balance_covers_price_difference` (database fact) | 271 | 206 (17 / 189) | 2 | 14 | 49 (49 / 0 / 0) | 92.8 % |
| `return_refund_method_is_original_or_existing_gift_card` (database fact) | 20 | 20 (19 / 1) | 0 | 0 | 0 (0 / 0 / 0) | 100.0 % |
| **all** | 1584 | 1431 (926 / 505) | 19 | 70 | 64 (63 / 1 / 0) | 94.1 % |

## Disagreements by group

Each disagreement gets one short label that says what the data shows (`group` in `p6_disagreements.jsonl`).
The label does not say who is right: that is the review in Part 7. The first label that fits is used.

| predicate | group | disagreements | judge true, tracker false | judge false, tracker true | judge unknown | tracker unknown | on blocked steps | in a violated rule | judge saw a cut history |
|---|---|---|---|---|---|---|---|---|---|
| `pending_flight_update_is_basic_economy` (airline) | cabin from an earlier successful flight update (Part 5 reading) | 37 | 37 | 0 | 0 | 0 | 4 | 3 | 26 |
| `reservation_has_no_used_flight_segments` (airline) | an object the lookup needs was not shown (if_missing) | 5 | 1 | 0 | 4 | 0 | 4 | 4 | 0 |
| `origin_destination_and_trip_type_preserved` (airline) | an object the lookup used was shown outside the judge's view (history cut) | 4 | 0 | 0 | 4 | 0 | 4 | 4 | 4 |
| `pending_flight_segments_are_unchanged` (airline) | an object the lookup used was shown outside the judge's view (history cut) | 4 | 0 | 0 | 4 | 0 | 4 | 4 | 4 |
| `pending_flight_update_changes_flights` (airline) | an object the lookup used was shown outside the judge's view (history cut) | 4 | 0 | 0 | 4 | 0 | 4 | 4 | 4 |
| `reservation_has_no_used_flight_segments` (airline) | other | 3 | 0 | 0 | 3 | 0 | 3 | 3 | 0 |
| `origin_destination_and_trip_type_preserved` (airline) | other | 2 | 0 | 0 | 2 | 0 | 2 | 2 | 0 |
| `pending_flight_update_is_basic_economy` (airline) | an object the lookup used was shown outside the judge's view (history cut) | 2 | 0 | 0 | 2 | 0 | 2 | 2 | 2 |
| `reservation_has_basic_or_economy_cabin` (airline) | an object the lookup needs was not shown (if_missing) | 2 | 0 | 0 | 2 | 0 | 2 | 1 | 0 |
| `reservation_has_business_cabin` (airline) | an object the lookup needs was not shown (if_missing) | 2 | 0 | 0 | 2 | 0 | 2 | 1 | 0 |
| `reservation_has_travel_insurance` (airline) | an object the lookup needs was not shown (if_missing) | 2 | 0 | 0 | 2 | 0 | 2 | 1 | 0 |
| `gift_card_balance_covers_price_difference` (retail) | payment method is not a gift card (the rule does not need the value) | 63 | 2 | 0 | 61 | 0 | 48 | 0 | 2 |
| `user_authenticated` (retail) | login output outside the judge's view (history cut) | 63 | 0 | 56 | 7 | 0 | 63 | 63 | 63 |
| `order_status_checked_delivered` (retail) | order last shown by a write tool, with another status | 21 | 21 | 0 | 0 | 0 | 6 | 0 | 1 |
| `gift_card_balance_covers_price_difference` (retail) | refund: the new items cost less than the old ones | 14 | 0 | 14 | 0 | 0 | 14 | 14 | 2 |
| `order_status_checked_pending` (retail) | order last shown by a write tool, with another status | 11 | 10 | 0 | 1 | 0 | 4 | 1 | 3 |
| `item_replacements_are_available_same_product_different_option` (retail) | an object the lookup needs was not shown (if_missing) | 7 | 2 | 0 | 5 | 0 | 7 | 5 | 1 |
| `order_status_checked_delivered` (retail) | order last shown by get_order_details, with another status | 6 | 6 | 0 | 0 | 0 | 2 | 0 | 6 |
| `order_status_checked_pending` (retail) | order last shown by get_order_details, with another status | 5 | 5 | 0 | 0 | 0 | 4 | 0 | 0 |
| `gift_card_balance_covers_price_difference` (retail) | an object the lookup needs was not shown (if_missing) | 3 | 1 | 0 | 2 | 0 | 3 | 2 | 0 |
| `item_replacements_are_available_same_product_different_option` (retail) | other | 1 | 0 | 0 | 1 | 0 | 1 | 1 | 0 |
| `payment_method_is_gift_card` (retail) | other | 1 | 0 | 0 | 0 | 1 | 1 | 0 | 0 |
| **all** | | 262 | | | | | 186 | 115 | 118 |

Per group: login output outside the judge's view (history cut): 63; cabin from an earlier successful flight update (Part 5 reading): 37; order last shown by a write tool, with another status: 32; order last shown by get_order_details, with another status: 11; payment method is not a gift card (the rule does not need the value): 63; refund: the new items cost less than the old ones: 14; an object the lookup used was shown outside the judge's view (history cut): 14; an object the lookup needs was not shown (if_missing): 21; other: 7.

## Tracker unknowns and their reasons

Every code-type value has a tracker value (true or false) or is unknown with a reason. The reasons:

| predicate | reason | values |
|---|---|---|
| `payment_method_is_gift_card` | missing argument or field: 'payment_method_id' | 1 |

## Checks

- Evaluation errors: 0. Replay mismatches while walking: 0.
- Steps whose circuit predicates differ from the judged predicates: 0.
- Code-type predicates in the circuit but missing from the judge record: 0.
- Values where the judge saw a cut history (last 24,000 characters only): 561, of which disagreements: 118.

