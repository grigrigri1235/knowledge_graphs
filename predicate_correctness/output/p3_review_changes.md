# Part 3: review of the predicate types

Types reviewed by an independent agent on 2026-10-22; person review pending.

## Who and how
- The reviewer is an agent that did not write the draft (`output/predicate_types.json`, 2026-10-21).
- For each of the 66 predicates, it checked the draft type against:
  - the predicate's description and declared sources in the frozen rule set;
  - the type table in `p3.md`;
  - the questions in `overview.md`, "How we decide what is a predicate".
- It paid most attention to four groups:
  - descriptions that mention user or agent messages (conversation or mixed);
  - "earlier tool output establishes" (database fact, *shown*);
  - comparisons of dates and amounts (database fact);
  - "a lookup worked earlier" (event).
- It checked the facts that some types rest on, in the copied τ-bench tool code and data. It did not look at judge
  values or gold data.
- Verdict per predicate: `output/p3_agent_review.json`. It is also the column "agent review" in
  `output/predicate_types.md`.

## Changes
**None.** The review agrees with all 66 draft types: airline 7 argument, 14 database fact, 0 event, 9 conversation,
12 mixed; retail 2 argument, 7 database fact, 1 event, 14 conversation, 0 mixed. That gives 31 code types and 35 LLM
types.

The only edits are:
- `predicate_types.json` gets a `_review` key with the status line. `load_types()` leaves it out.
- `predicate_types.md` is rebuilt with the status and the "agent review" column.

## Checks behind the verdicts
| check | result | used for |
|---|---|---|
| Payment-method id prefix vs `source` in `users.json` | prefix = source for all 1,486 airline and 695 retail methods (0 mismatches) | `payment_method_is_gift_card` and `booking_payment_method_counts_within_limits` stay **argument** |
| `book_reservation` / `update_reservation_flights` signatures | one `cabin` and one `flights` list per call | `all_booking_passengers_share_flights_and_cabin`, `all_pending_flight_segments_have_one_cabin`: **argument**, true for every well-formed call |
| Can a tool output show that a reservation's flight was cancelled? | No. Reservation flights have no `status` field, and the search tools list only flights with status "available". In the 120 saved airline conversations, all 658 flight statuses shown are "available". | `airline_cancelled_flight_confirmed` (see below) |
| Does `update_reservation_flights` update the reservation's `cabin`? | No (it changes `flights` and payments only) | note for Part 5 on the cabin predicates |

## Verdicts on the draft's borderline cases
| predicate | draft | verdict | reason |
|---|---|---|---|
| `cancellation_is_within_24_hours` | mixed | agree | The description accepts user messages ("tool outputs or user messages establish"), and we use the predicates as written. When the reservation was shown, its `created_at` decides, and a user message cannot overrule it. First candidate for an A2 split into a database fact. |
| `airline_cancelled_flight_confirmed` | mixed | agree, with a note | No tool output can show it (check above). Its *shown* part is always false. The only code part is the *fact* value in the flight data, which the guard can read (B3). If only *shown* evidence should count, it would be conversation, like `insured_cancellation_condition_met`. Either way the LLM sets it in this plan. |
| `compensation_is_prohibited_for_relevant_reservation` | mixed | agree | Neither `send_certificate` nor `respond` names a reservation. So it is not a database fact in the sense of `p3.md` ("the arguments say which object"). Membership alone is a separate code fact: silver or gold gives false for every reservation. |
| `regular/silver/gold_member_booking_baggage_counts_correct` | argument | agree | The predicate name fixes the membership level. The free allowance is the policy table (S16–S18). Passenger count, cabin and bag counts are arguments. |
| `all_booking_passengers_share_flights_and_cabin`, `all_pending_flight_segments_have_one_cabin` | argument | agree | Both are true for every well-formed call. |
| `insured_cancellation_condition_met` | conversation | agree | No tool output and no database field holds a health or weather reason. |
| `request_cannot_be_handled_with_available_tools`, `request_cannot_be_handled_within_scope` | conversation | agree | They need what the user asks and whether it is in scope. Tool outputs are context, and no fixed fact can be checked by code alone. |
| `user_chose_pending_payment_method` | conversation | agree | The description holds no fact that code can check alone. The argument only says what the user's words must match. The mixed example in `overview.md` ("How we decide what is a predicate") is out of date; the person may update it. |
| `payment_method_is_gift_card` | argument | agree | The prefix check gives the same answer as `source` for all 695 retail methods. |

## Other points looked at (no change)
- **Mixed predicates with "user messages or tool outputs"** (`booking_required_information_established`,
  `passenger_identity_details_established`, `modification_user_and_reservation_ids_established`,
  `cancellation_context_established`): mixed. The code part can show the ids. Trip type, origin, destination, names
  and the cancellation reason may come only from messages, and a false value needs them.
- **`user_authenticated`** (event): agree. The event does not check that the found user is "the user for this
  conversation"; `request_is_for_another_user` covers that.
- **"Earlier tool output establishes ..." database facts** (order status, gift card balance, payment method, item
  replacement, refund method, membership, reservation cabin and insurance): all agree, all *shown*.
- **Date comparisons** (`reservation_has_no_used_flight_segments`): database fact, agree. A segment dated
  2024-05-15 needs the departure time or the flight status from the flight data.

## Notes for later parts
- **Part 5:** `pending_flight_update_is_basic_economy`, `reservation_has_business_cabin` and
  `reservation_has_basic_or_economy_cabin` read the reservation's `cabin`. τ-bench never updates that field after
  `update_reservation_flights`, so after an earlier cabin change in the same conversation, the value can be stale.
- **Part 5:** `airline_cancelled_flight_confirmed` is not a code type. If it is split later (A2), only a *fact*
  lookup can make its code part useful.
- **Person review:** the cases above are where a person's view matters most, mainly
  `cancellation_is_within_24_hours` (it moves 1 predicate from LLM to code if changed). If the person changes a
  type: edit `predicate_types.json` and the verdict in `p3_agent_review.json`. Then run
  `python3 -B -m state_tracker.predicate_types --write-md --force`, `python3 -B -m state_tracker.type_counts`
  and the tests, and record the new sha256 in `overview.md`.

## Freeze (agent review)
- Date: 2026-10-22. Person review pending.
- `output/predicate_types.json` sha256 `20dade34ca42965be3a3ae139749651b385b268de7d6bd4eb07ca12a21ee1889`.
- `output/p3_agent_review.json` sha256 `1e9b810934392eb0dca9b5ba9ac5e7c8502146937d34bfc77897364d84112474`.
