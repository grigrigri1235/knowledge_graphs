# Part 5: answers to the independent check

Date 2026-10-22. This file answers every point in `output/p5_independent_check.md` (p5.md subtask 3: "every problem
it finds is fixed or explained"). I decided from the predicate descriptions, the policy, the τ-bench tool code and the
saved conversations. I did not read the judge's values or evidence, or any gold code.

Lookup files before the changes (the ones the checker read): airline `4c354258…ca4b`, retail `8033144d…aae9`.
After the changes, they are frozen (sha256 in `overview.md`).

## Answers, one line per item

| # | predicate | auditor verdict | action taken | reason |
|---|---|---|---|---|
| 1 | `item_replacements_are_available_same_product_different_option` (retail) | wrong | **Fixed.** New and old items are now paired by position (index `k` in `[0..9]`), as the checker suggested. | The description says "its paired original item", and τ-bench pairs by position (`zip`; the tool says "match the item id in the same position"). The old version gave true for crossed pairs and false for X->Y, Y->Z. Calls with more than 10 items give false; an order has at most 5 items, so such a call cannot work. |
| 2 | `pending_flight_update_is_basic_economy` (airline) | unclear | **Changed.** The cabin is the `cabin` argument of the newest successful `update_reservation_flights` on this reservation; only without such a call, the shown `cabin` field. | τ-bench never updates the `cabin` field after a cabin change (a τ-bench bug), so both the shown details and the database copy keep the old cabin. The conversation does show the change: the call worked and its output has the new cabin's prices. In luna task34 trial1 the user even says "The cabin is still basic economy". The policy lets every reservation change cabin, and forbids flight changes only for basic economy. The old reading would block a flight change after a paid upgrade. Both sources are what the conversation showed, so `uses` stays `shown`. |
| 3 | `reservation_has_business_cabin` (airline) | ok (with a stale-cabin note) | **Changed** to the same cabin reading as #2. | One cabin reading for all three cabin lookups. No saved value changes. |
| 4 | `reservation_has_basic_or_economy_cabin` (airline) | ok (with a stale-cabin note) | **Changed** to the same cabin reading as #2. | As #3. No saved value changes. |
| 5 | `origin_destination_and_trip_type_preserved` (airline) | unclear | **Fixed.** The check no longer depends on the order of the flights in the call. A one-way reservation whose origin equals its destination (35 in the data, e.g. Z7GOZK) checks only the origin and the destination. | The description is about origin, destination and trip type, not about the order of the list. The old version gave false for a round trip listed return first. The checker's caution about one-way trips with origin = destination is handled. |
| 6 | `origin_destination_and_trip_type_preserved`: reads the flight schedule (`db`) while `uses` is `shown` | note | **Kept**, explained in the reason. | The call has no origin or destination argument. The route of a flight number comes from the schedule, which no tool changes, so fact and shown give the same route. |
| 7 | `origin_destination_and_trip_type_preserved`: does not check that legs connect | note | **Kept.** | The description does not ask for it, and τ-bench does not check it either. |
| 8 | `booking_payment_methods_found_in_user_profile`: a certificate spent earlier stays "found" until the profile is shown again | ok (edge) | **Kept.** | The description asks whether the method "appears in an earlier tool output showing the user's profile", and it did. This never happens in the saved steps. |
| 9 | `gift_card_balance_covers_order_total`: stale balance; the gift card's owner is not checked | ok (edges) | **Kept.** | The description asks what earlier output "establishes" about the balance, which is the shown balance. Ownership is not in the description; τ-bench rejects a method not in the order user's profile. Neither edge is in the saved steps. |
| 10 | `gift_card_balance_covers_price_difference`: stale balance; rounding at the cent | ok (edges) | **Kept.** | Stale balance: as #9. Rounding: the format has no rounding. Only a difference equal to the balance within one cent can compare either way. No saved step is near that edge (checker). |
| 11 | `reservation_has_no_used_flight_segments`: segment dated today | ok | **No change.** | The checker agreed with the lookup's handling. |
| 12 | `order_status_checked_pending`, `order_status_checked_delivered`: newest shown version, also from write tools | ok | **No change.** | The checker confirmed this reading. In the 15 + 27 runs where it differs from the literal reading, τ-bench rejected every call that ran. |
| 13 | The 9 argument lookups: `uses` is only a placeholder | note | **Kept**; stated in each reason. | The format requires the field. Part 6 must not read anything into `uses` for argument lookups. |
| 14 | Lookups with no true or no false value in the saved steps (e.g. five passengers, one cabin) | note | **Kept.** | The unit tests cover the missing values with hand-made cases (`tests/test_lookup_format.py`). |

## Effect on the saved steps
`state_tracker/run_lookups.py` on all 4,903 step records (`output/p5_smoke.md`, log `output/logs/p5fix_run_lookups.log`):
0 errors, 0 file problems, 0 replay mismatches.

| lookup | runs | before: true / false | after: true / false |
|---|---|---|---|
| `pending_flight_update_is_basic_economy` | 136 | 92 / 44 | 55 / 81 |
| `reservation_has_business_cabin` | 35 | 19 / 16 | 19 / 16 |
| `reservation_has_basic_or_economy_cabin` | 35 | 14 / 21 | 14 / 21 |
| `origin_destination_and_trip_type_preserved` | 136 | 136 / 0 | 136 / 0 |
| `item_replacements_are_available_same_product_different_option` | 377 | 363 / 14 | 363 / 14 |

- Only `pending_flight_update_is_basic_economy` changes. 37 values go from true to false, all after a successful cabin
  change on the same reservation: nano task5 trials 0 and 1, nano task33 trial0, nano task34 trials 0 and 1, luna
  task5 trial2 and luna task34 trial1. The checker found the same 37.
- For rule 18 ("no flight change on basic economy unless the flights stay the same"), only nano task5 trial0 steps 19-21
  change from broken to kept. In the other 34, the flights were unchanged, so the rule holds either way.
- The other 30 lookups are unchanged. Each changed lookup was compared with its old version on every saved step
  (`output/logs/p5fix_compare.log`).

## Tests
- `tests/test_lookup_format.py` has a new class `TestAuditFixes` with 5 tests built from τ-bench's data and tools:
  - crossed pairs give false (τ-bench also rejects the call);
  - X->Y, Y->Z of one product gives true (τ-bench accepts it);
  - the cabin after a successful upgrade, a failed upgrade and an upgrade to business;
  - a round trip in any order, and a different destination;
  - one-way trips: legs in reverse order, an added flight from the destination, and origin = destination.
- With the old lookup files, all 5 new tests fail (`output/logs/p5fix_tests_old_lookups.log`). With the new ones, all
  pass.
- Full suite: 87 of 87 pass (`output/logs/p5fix_tests_all.log`).

## For later parts
- Part 7: the cabin reading (#2) is a choice. If the person reviewing the disagreements prefers the literal reading of
  the stale field, that is a lookup fix after the freeze. It is logged in `output/p5_lookup_fixes.md`, and Part 6 is
  run again.
