# Part 8: effect on decisions

Written by `state_tracker/decide_again.py` (Part 8). Standard library only, no LLM calls.

We run TGR's decision again on each saved guarded step (4,903 records, Part 2). The judge's values of the code-type predicates are replaced by the tracker's values (Part 6). Everything else stays as TGR had it: the conversation and mixed values from the judge, the frozen rules, ε = 0.1, all weights 1.

A record is one guard check (one attempt). A step that was blocked several times has several records.

**Limit.** We count only the decision at each saved step. After a changed decision the real conversation would have gone on differently. Part 10 measures that with new conversations.

## 1. Check: the copied decision code gives the saved decisions

For each record we rebuild TGR's input from the saved guard record: `current` = every action predicate (true for the matched action) plus the judge's values, and run `repro_runtime/mln.py::decide` with the rules from `state_tracker/tgr_to_aspm.py`.

| check | records ok | failed |
|---|---|---|
| rebuilt `current` equals the saved `trace_position` | 4,903 | 0 |
| same allow/block as saved (with the guard's past trace) | 4,903 | 0 |
| same margin as saved, within 1e-9 (with the past trace) | 4,903 | 0 |
| same allow/block as saved (with an empty past trace) | 4,903 | 0 |
| same margin as saved, within 1e-9 (empty past trace) | 4,903 | 0 |
| past trace and empty past trace give exactly the same result | 4,903 | 0 |
| the judge values in Part 6's file equal the guard record | 4,903 | 0 |

No TGR rule has a temporal operator (`tests/test_tgr_to_aspm.py`), so `verify.rule_value` reads only the current position and the past trace cannot change the result. The table shows this on every record. The decisions below use an empty past trace.

## 2. Blocks removed and added

The two versions differ only where the tracker gives unknown:
- **(a)** a tracker unknown stays unknown;
- **(b)** a tracker unknown is replaced by the judge's value.

### Version (a) tracker unknown stays unknown

| run, domain | records | blocked before | blocked after | blocks removed | blocks added | net change |
|---|---|---|---|---|---|---|
| luna_train_v5 airline | 321 | 12 | 13 | 0 | 1 | +1 |
| luna_train_v5 retail | 1,729 | 54 | 51 | 5 | 2 | -3 |
| nano_train airline | 531 | 94 | 89 | 5 | 0 | -5 |
| nano_train retail | 2,322 | 416 | 384 | 57 | 25 | -32 |
| **all** | 4,903 | 576 | 537 | 67 | 28 | -39 |

Distinct steps (task, trial, step; attempts merged): blocks removed 30, blocks added 28.

### Version (b) tracker unknown -> judge's value

| run, domain | records | blocked before | blocked after | blocks removed | blocks added | net change |
|---|---|---|---|---|---|---|
| luna_train_v5 airline | 321 | 12 | 13 | 0 | 1 | +1 |
| luna_train_v5 retail | 1,729 | 54 | 51 | 5 | 2 | -3 |
| nano_train airline | 531 | 94 | 89 | 5 | 0 | -5 |
| nano_train retail | 2,322 | 416 | 384 | 57 | 25 | -32 |
| **all** | 4,903 | 576 | 537 | 67 | 28 | -39 |

Distinct steps (task, trial, step; attempts merged): blocks removed 30, blocks added 28.

Records where (a) and (b) decide differently: 0.

The tracker gives unknown where the judge gave a value in 1 value(s): `payment_method_is_gift_card` at `nano_train/retail/task41/trial2/step8/attempt1`. This is the only place where (a) and (b) differ.

Of the 67 removed blocks, 13 were blocked records that still ran through the cap override. Removed blocks count each blocked attempt: in the real run, attempts 2 to 4 of a step would not have happened once attempt 1 was allowed.

## 3. Per predicate

A changed record can have more than one replaced value, so a record can count under more than one predicate. "alone" = replacing only this predicate's value (all others stay the judge's) already changes the decision.

### Version (a) tracker unknown stays unknown

| domain | predicate | blocks removed | of these, alone | blocks added | of these, alone |
|---|---|---|---|---|---|
| retail | `user_authenticated` | 56 | 56 | 0 | 0 |
| retail | `order_status_checked_delivered` | 0 | 0 | 19 | 19 |
| retail | `order_status_checked_pending` | 1 | 1 | 8 | 8 |
| retail | `gift_card_balance_covers_price_difference` | 5 | 5 | 1 | 0 |
| airline | `reservation_has_no_used_flight_segments` | 3 | 3 | 1 | 1 |
| airline | `pending_flight_update_is_basic_economy` | 2 | 1 | 0 | 0 |
| airline | `origin_destination_and_trip_type_preserved` | 1 | 0 | 0 | 0 |
| airline | `pending_flight_segments_are_unchanged` | 1 | 0 | 0 | 0 |
| airline | `pending_flight_update_changes_flights` | 1 | 0 | 0 | 0 |

### Version (b) tracker unknown -> judge's value

| domain | predicate | blocks removed | of these, alone | blocks added | of these, alone |
|---|---|---|---|---|---|
| retail | `user_authenticated` | 56 | 56 | 0 | 0 |
| retail | `order_status_checked_delivered` | 0 | 0 | 19 | 19 |
| retail | `order_status_checked_pending` | 1 | 1 | 8 | 8 |
| retail | `gift_card_balance_covers_price_difference` | 5 | 5 | 1 | 0 |
| airline | `reservation_has_no_used_flight_segments` | 3 | 3 | 1 | 1 |
| airline | `pending_flight_update_is_basic_economy` | 2 | 1 | 0 | 0 |
| airline | `origin_destination_and_trip_type_preserved` | 1 | 0 | 0 | 0 |
| airline | `pending_flight_segments_are_unchanged` | 1 | 0 | 0 | 0 |
| airline | `pending_flight_update_changes_flights` | 1 | 0 | 0 | 0 |

## 4. Does a change fix an error or add one? (Part 7)

Reference decision: TGR's decision when every disagreeing code-type value of the record takes the value the Part 7 reviewer gave as correct (an independent agent; the person review is pending). Agreeing values are taken as right (Part 7: 50 of 50 sampled agreements were right). A record is **covered** when every disagreeing value in it was reviewed. A record with no disagreement keeps its saved decision as reference.

- All records: no disagreement 4,668, covered 190, not covered 45.
- Blocked records: no disagreement 416, covered 160, not covered 0. (Part 7 reviewed every disagreement on a blocked step.)

### Version (a) tracker unknown stays unknown

| change | fixes an error | adds an error | not covered | total |
|---|---|---|---|---|
| block removed | 67 | 0 | 0 | 67 |
| block added | 10 | 0 | 18 | 28 |

Wrong decisions on the 4,858 records whose reference is known:

| decisions | wrong blocks | wrong allows |
|---|---|---|
| saved (TGR, judge values) | 67 | 10 |
| version a | 0 | 0 |

Fixes that rest on one of the reviewer's readings (Part 7; a fix can rest on more than one item): superseded status 9; signed price difference 5; stale cabin field after a cabin change 1.

### Version (b) tracker unknown -> judge's value

| change | fixes an error | adds an error | not covered | total |
|---|---|---|---|---|
| block removed | 67 | 0 | 0 | 67 |
| block added | 10 | 0 | 18 | 28 |

Wrong decisions on the 4,858 records whose reference is known:

| decisions | wrong blocks | wrong allows |
|---|---|---|
| saved (TGR, judge values) | 67 | 10 |
| version b | 0 | 0 |

Fixes that rest on one of the reviewer's readings (Part 7; a fix can rest on more than one item): superseded status 9; signed price difference 5; stale cabin field after a cabin change 1.

Changed records that Part 7 does not cover (version a), with the values that were not reviewed:

| record | change | replaced values (judge -> tracker) | Part 6 group (a description, not a verdict) |
|---|---|---|---|
| `nano_train/retail/task98/trial0/step8/attempt1` | block added | `order_status_checked_pending` true -> false | order last shown by a write tool, with another status |
| `nano_train/retail/task27/trial1/step13/attempt1` | block added | `gift_card_balance_covers_price_difference` unknown -> false, `order_status_checked_delivered` true -> false | order last shown by a write tool, with another status; payment method is not a gift card (the rule does not need the value) |
| `nano_train/retail/task27/trial1/step14/attempt1` | block added | `order_status_checked_delivered` true -> false | order last shown by a write tool, with another status |
| `nano_train/retail/task41/trial1/step10/attempt1` | block added | `order_status_checked_pending` true -> false | order last shown by a write tool, with another status |
| `nano_train/retail/task54/trial1/step17/attempt1` | block added | `order_status_checked_delivered` true -> false | order last shown by a write tool, with another status |
| `nano_train/retail/task54/trial1/step18/attempt1` | block added | `order_status_checked_delivered` true -> false | order last shown by a write tool, with another status |
| `nano_train/retail/task54/trial1/step20/attempt1` | block added | `order_status_checked_delivered` true -> false | order last shown by a write tool, with another status |
| `nano_train/retail/task54/trial1/step25/attempt1` | block added | `order_status_checked_pending` true -> false | order last shown by a write tool, with another status |
| `nano_train/retail/task54/trial1/step27/attempt1` | block added | `order_status_checked_delivered` true -> false | order last shown by get_order_details, with another status |
| `nano_train/retail/task54/trial1/step29/attempt1` | block added | `order_status_checked_delivered` true -> false | order last shown by get_order_details, with another status |
| `nano_train/retail/task27/trial2/step10/attempt1` | block added | `order_status_checked_delivered` true -> false | order last shown by a write tool, with another status |
| `nano_train/retail/task28/trial2/step14/attempt1` | block added | `order_status_checked_delivered` true -> false | order last shown by a write tool, with another status |
| `nano_train/retail/task28/trial2/step16/attempt1` | block added | `order_status_checked_delivered` true -> false | order last shown by a write tool, with another status |
| `nano_train/retail/task28/trial2/step17/attempt1` | block added | `order_status_checked_delivered` true -> false | order last shown by a write tool, with another status |
| `nano_train/retail/task28/trial2/step18/attempt1` | block added | `order_status_checked_delivered` true -> false | order last shown by a write tool, with another status |
| `nano_train/retail/task28/trial2/step23/attempt1` | block added | `order_status_checked_delivered` true -> false | order last shown by a write tool, with another status |
| `nano_train/retail/task28/trial2/step26/attempt1` | block added | `order_status_checked_delivered` true -> false | order last shown by get_order_details, with another status |
| `nano_train/retail/task98/trial2/step14/attempt1` | block added | `order_status_checked_pending` true -> false | order last shown by a write tool, with another status |

For these, Part 7's sample of other disagreements (not on blocked steps) is the best guide: the tracker was right in 30 of 30 reviewed items. Almost all of them are an order whose status a later output showed as something else, so they follow the "superseded status" reading: under the reviewer's reading the added blocks are right, under the other reading they are wrong.

### If the person takes the other reading

Part 7's reviewer chose five readings (stale cabin field, superseded order status, signed price difference, no gift card in the call, same-item exchange). In each of these items the reviewer sided with the tracker, or, for the same-item exchange, with neither. Here the items of one reading take the judge's value instead, and the reference decision is computed again.

| reading taken the other way | records with another reference | saved: wrong blocks / allows | (a): wrong blocks / allows | (b): wrong blocks / allows |
|---|---|---|---|---|
| none (as reviewed) | 0 | 67 / 10 | 0 / 0 | 0 / 0 |
| no gift card in the call | 0 | 67 / 10 | 0 / 0 | 0 / 0 |
| same-item exchange: difference 0 from the order output | 0 | 67 / 10 | 0 / 0 | 0 / 0 |
| signed price difference | 5 | 62 / 10 | 0 / 5 | 0 / 5 |
| stale cabin field after a cabin change | 1 | 66 / 10 | 0 / 1 | 0 / 1 |
| superseded status | 11 | 69 / 1 | 11 / 0 | 11 / 0 |
| all readings at once | 17 | 63 / 1 | 11 / 6 | 11 / 6 |

The reference is not independent of the tracker: Part 7's reviewer gave the tracker's value in 263 of 266 items, and the frozen lookups already follow the readings above. So "0 wrong decisions after the change" mostly says that the tracker and the reviewer agree; the table above shows how much rests on the readings.

## 5. The version for Part 10

Rule (written before the full run): 1. fewer wrong blocks (blocked, but the reference decision allows) on the records whose reference is known; 2. if tied, fewer wrong decisions in all (wrong blocks + wrong allows); 3. if still tied, version (b), because it never turns a value the judge gave into unknown (review_before_implementation.md, H2: more unknowns tend to mean more blocks).

**Chosen: version (b) tracker unknown -> judge's value.** Reason: rule 3: tie on wrong blocks (0) and on wrong decisions in all (0).

On the saved steps the two versions give the same decision on every record, because the tracker gives unknown in only 1 value(s) and no decision depends on it. So the saved data cannot tell them apart, and the tie rule decides. In new conversations (Part 10) the tracker may give unknown more often, for example when the agent calls a tool with a missing argument.

What this means for Part 10: when a lookup gives unknown, the guard uses the judge's value for that predicate. So the judge must also be able to give a value for a code-type predicate whose lookup gave unknown (for example, by adding that predicate to the judge's question only in that case).

## Files
- `output/p8_changes.jsonl`: one line per record whose decision changes in (a) or (b), with the replaced values, the values that flip the decision alone, the reference decision and the review items.
- Log: `output/logs/p8_decide_again.log`.
