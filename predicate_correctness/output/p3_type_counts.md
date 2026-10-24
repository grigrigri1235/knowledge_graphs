# Part 3: counts per predicate type

Written by `state_tracker/type_counts.py` from the Part 2 step records (`output/steps_<run>_<domain>.jsonl`)
and the types in `output/predicate_types.json` (sha256 `20dade34ca42965be3a3ae139749651b385b268de7d6bd4eb07ca12a21ee1889`).
Status of the types: Types reviewed by an independent agent on 2026-10-22; person review pending.

## Summary
- **Main metric:** 195 of 576 blocked steps (33.9 %) involve at least one code-type predicate: luna_train_v5 14 of 66 (21.2 %); nano_train 181 of 510 (35.5 %).
- In 154 blocked steps (26.7 %), every violated rule has a code-type predicate.
- Code types hold 33.1 % of the judge values and 28.7 % of the block-causing values. Conversation predicates hold most of the rest.

## Definitions
- **Code types:** argument, database fact, event (set by code in Parts 4-5). **LLM types:** conversation, mixed.
- **Judge value:** one predicate entry in a step's `judge` dict (true, false or unknown).
- **Blocked step:** a guard check with `action_allowed` = false.
- **Block-causing value:** on a blocked step, a judge value whose predicate appears in the logic of one of the
  step's `violated_rules`. TGR lists there every rule the action breaks in the most likely world, plus every rule
  at risk through an unknown value (`method_tgr/runtime.py`). Allowed steps have no violated rules.
- **Blocked step involves a code type:** at least one of its violated rules has a code-type predicate. Only
  these blocks can change when the tracker replaces code-type values, so the share is an upper limit.
  Two more shares for context:
  - **every violated rule has a code type:** if the conversation and mixed values stay the same, a violated
    rule without a code-type predicate stays violated. So this share is a closer estimate of the blocks the
    tracker could turn into allows;
  - **a code type was judged:** a code-type predicate was among the step's judged predicates at all (wider).

## 1. Predicates per type
| domain | argument | database fact | event | conversation | mixed | code types | total | judged at least once |
|---|---|---|---|---|---|---|---|---|
| airline | 7 | 14 | 0 | 9 | 12 | 21 | 42 | 40 |
| retail | 2 | 7 | 1 | 14 | 0 | 10 | 24 | 24 |
| all | 9 | 21 | 1 | 23 | 12 | 31 | 66 | 64 |

Never judged in the saved runs: `cancelled_flight_certificate_send_conditions_met`, `delayed_flight_certificate_send_conditions_met`.

## 2. Judge values per type
Number of judge values (share of the row).

| run, domain | argument | database fact | event | conversation | mixed | code types | total |
|---|---|---|---|---|---|---|---|
| luna_train_v5 airline | 57 (2.6 %) | 165 (7.4 %) | 0 (0.0 %) | 1,230 (55.3 %) | 772 (34.7 %) | 222 (10.0 %) | 2,224 |
| luna_train_v5 retail | 129 (2.4 %) | 489 (8.9 %) | 1,562 (28.5 %) | 3,309 (60.3 %) | 0 (0.0 %) | 2,180 (39.7 %) | 5,489 |
| nano_train airline | 157 (4.0 %) | 591 (15.2 %) | 0 (0.0 %) | 1,831 (47.2 %) | 1,298 (33.5 %) | 748 (19.3 %) | 3,877 |
| nano_train retail | 318 (3.7 %) | 1,109 (12.9 %) | 2,113 (24.5 %) | 5,074 (58.9 %) | 0 (0.0 %) | 3,540 (41.1 %) | 8,614 |
| **luna_train_v5 (both domains)** | 186 (2.4 %) | 654 (8.5 %) | 1,562 (20.3 %) | 4,539 (58.8 %) | 772 (10.0 %) | 2,402 (31.1 %) | 7,713 |
| **nano_train (both domains)** | 475 (3.8 %) | 1,700 (13.6 %) | 2,113 (16.9 %) | 6,905 (55.3 %) | 1,298 (10.4 %) | 4,288 (34.3 %) | 12,491 |
| **all** | 661 (3.3 %) | 2,354 (11.7 %) | 3,675 (18.2 %) | 11,444 (56.6 %) | 2,070 (10.2 %) | 6,690 (33.1 %) | 20,204 |

Judge values by value, all runs:

| type | true | false | unknown | total |
|---|---|---|---|---|
| argument | 304 | 357 | 0 | 661 |
| database fact | 1,694 | 561 | 99 | 2,354 |
| event | 3,272 | 396 | 7 | 3,675 |
| conversation | 4,062 | 7,374 | 8 | 11,444 |
| mixed | 284 | 1,697 | 89 | 2,070 |

## 3. Block-causing values per type
Number of block-causing values (share of the row).

| run, domain | argument | database fact | event | conversation | mixed | code types | total |
|---|---|---|---|---|---|---|---|
| luna_train_v5 airline | 0 (0.0 %) | 0 (0.0 %) | 0 (0.0 %) | 11 (84.6 %) | 2 (15.4 %) | 0 (0.0 %) | 13 |
| luna_train_v5 retail | 7 (8.9 %) | 7 (8.9 %) | 7 (8.9 %) | 58 (73.4 %) | 0 (0.0 %) | 21 (26.6 %) | 79 |
| nano_train airline | 1 (0.4 %) | 94 (38.4 %) | 0 (0.0 %) | 88 (35.9 %) | 62 (25.3 %) | 95 (38.8 %) | 245 |
| nano_train retail | 11 (1.8 %) | 35 (5.6 %) | 113 (18.2 %) | 461 (74.4 %) | 0 (0.0 %) | 159 (25.6 %) | 620 |
| **luna_train_v5 (both domains)** | 7 (7.6 %) | 7 (7.6 %) | 7 (7.6 %) | 69 (75.0 %) | 2 (2.2 %) | 21 (22.8 %) | 92 |
| **nano_train (both domains)** | 12 (1.4 %) | 129 (14.9 %) | 113 (13.1 %) | 549 (63.5 %) | 62 (7.2 %) | 254 (29.4 %) | 865 |
| **all** | 19 (2.0 %) | 136 (14.2 %) | 120 (12.5 %) | 618 (64.6 %) | 64 (6.7 %) | 275 (28.7 %) | 957 |

Block-causing values by value, all runs:

| type | true | false | unknown | total |
|---|---|---|---|---|
| argument | 18 | 1 | 0 | 19 |
| database fact | 39 | 62 | 35 | 136 |
| event | 0 | 113 | 7 | 120 |
| conversation | 138 | 472 | 8 | 618 |
| mixed | 0 | 51 | 13 | 64 |

## 4. Blocked steps that involve a code-type predicate
Share of blocked steps. "still ran": blocked steps that ran anyway through the cap override.

| run, domain | blocked steps | still ran | involve a code type (main metric) | every violated rule has a code type | a code type was judged |
|---|---|---|---|---|---|
| luna_train_v5 airline | 12 | 0 | 0 (0.0 %) | 0 (0.0 %) | 6 (50.0 %) |
| luna_train_v5 retail | 54 | 0 | 14 (25.9 %) | 12 (22.2 %) | 52 (96.3 %) |
| nano_train airline | 94 | 3 | 39 (41.5 %) | 31 (33.0 %) | 62 (66.0 %) |
| nano_train retail | 416 | 41 | 142 (34.1 %) | 111 (26.7 %) | 376 (90.4 %) |
| **luna_train_v5 (both domains)** | 66 | 0 | 14 (21.2 %) | 12 (18.2 %) | 58 (87.9 %) |
| **nano_train (both domains)** | 510 | 44 | 181 (35.5 %) | 142 (27.8 %) | 438 (85.9 %) |
| **all** | 576 | 44 | 195 (33.9 %) | 154 (26.7 %) | 496 (86.1 %) |

Blocked steps with at least one block-causing value of each type (a step can count for several types):

| run, domain | blocked steps | argument | database fact | event | conversation | mixed |
|---|---|---|---|---|---|---|
| luna_train_v5 airline | 12 | 0 (0.0 %) | 0 (0.0 %) | 0 (0.0 %) | 11 (91.7 %) | 2 (16.7 %) |
| luna_train_v5 retail | 54 | 7 (13.0 %) | 7 (13.0 %) | 7 (13.0 %) | 49 (90.7 %) | 0 (0.0 %) |
| nano_train airline | 94 | 1 (1.1 %) | 38 (40.4 %) | 0 (0.0 %) | 70 (74.5 %) | 41 (43.6 %) |
| nano_train retail | 416 | 11 (2.6 %) | 30 (7.2 %) | 113 (27.2 %) | 404 (97.1 %) | 0 (0.0 %) |
| **all** | 576 | 19 (3.3 %) | 75 (13.0 %) | 120 (20.8 %) | 534 (92.7 %) | 43 (7.5 %) |

## 5. Code-type predicates with block-causing values
All runs. Columns: luna airline, luna retail, nano airline, nano retail.

| domain | predicate | type | luna airline | luna retail | nano airline | nano retail | total |
|---|---|---|---|---|---|---|---|
| airline | `booking_payment_method_counts_within_limits` | argument | 0 | 0 | 1 | 0 | 1 |
| airline | `pending_flight_update_is_basic_economy` | database fact | 0 | 0 | 19 | 0 | 19 |
| airline | `pending_flight_segments_are_unchanged` | database fact | 0 | 0 | 19 | 0 | 19 |
| airline | `origin_destination_and_trip_type_preserved` | database fact | 0 | 0 | 6 | 0 | 6 |
| airline | `pending_flight_update_changes_flights` | database fact | 0 | 0 | 13 | 0 | 13 |
| airline | `reservation_has_business_cabin` | database fact | 0 | 0 | 10 | 0 | 10 |
| airline | `reservation_has_basic_or_economy_cabin` | database fact | 0 | 0 | 10 | 0 | 10 |
| airline | `reservation_has_travel_insurance` | database fact | 0 | 0 | 10 | 0 | 10 |
| airline | `reservation_has_no_used_flight_segments` | database fact | 0 | 0 | 7 | 0 | 7 |
| retail | `user_authenticated` | event | 0 | 7 | 0 | 113 | 120 |
| retail | `order_status_checked_pending` | database fact | 0 | 0 | 0 | 2 | 2 |
| retail | `order_status_checked_delivered` | database fact | 0 | 0 | 0 | 5 | 5 |
| retail | `payment_method_differs_from_original` | database fact | 0 | 0 | 0 | 4 | 4 |
| retail | `payment_method_is_gift_card` | argument | 0 | 7 | 0 | 11 | 18 |
| retail | `item_replacements_are_available_same_product_different_option` | database fact | 0 | 0 | 0 | 12 | 12 |
| retail | `gift_card_balance_covers_price_difference` | database fact | 0 | 7 | 0 | 11 | 18 |
| retail | `return_refund_method_is_original_or_existing_gift_card` | database fact | 0 | 0 | 0 | 1 | 1 |

## 6. Checks

| run, domain | steps | judge values (expected) | blocked (expected) | problems |
|---|---|---|---|---|
| luna_train_v5 airline | 321 | 2,224 (2,224) | 12 (12) | 0 |
| luna_train_v5 retail | 1,729 | 5,489 (5,489) | 54 (54) | 0 |
| nano_train airline | 531 | 3,877 (3,877) | 94 (94) | 0 |
| nano_train retail | 2,322 | 8,614 (8,614) | 416 (416) | 0 |

Models in the step records: luna_train_v5 (gpt-6-luna agent): agent gpt-6-luna, guard gpt-6-luna; nano_train (gpt-5-nano agent): agent gpt-5-nano, guard gpt-6-luna.
