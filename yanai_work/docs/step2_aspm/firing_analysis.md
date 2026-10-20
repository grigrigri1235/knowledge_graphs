# Step 2: offline firing analysis of the Python-evaluable ASPM rules

**Data:** τ-bench `historical_trajectories` @ `59a200c`:
- airline: `gpt-4o` 200 runs and `sonnet-35-new` 400 runs;
- retail: `gpt-4o` 460 runs and `sonnet-35-new` 920 runs.

**Method:** `python scripts/validate_aspm.py --firing`. No LLM calls are made.
- For every **write-tool** call (`writes_db` in `policies/tau_bench/*_tools.json`), the script evaluates every ASPM rule in that tool's circuit (own rules plus upstream nodes) whose condition predicates are all `state`, `tool_log` or `structural`.
- The trajectory prefix *before* the agent turn is the context. The turn itself is passed for the structural predicates.
- `None` predicates use Kleene logic: a rule counts as "not evaluable" only when the `None` leaves its value undetermined.
- A **firing** is a rule that evaluates to False, i.e. is violated. Firings are split by run reward (1 / 0) and by whether the τ-bench API itself rejected the call.
- Raw output goes to `output/step2_firing/` (git-ignored): `firing_tables.md` and `{domain}_firing.json` with up to 12 examples per rule.

## Headline

| | Write calls (r1 / r0) | Python-evaluable rules | Accepted calls a `block` rule would stop: reward-1 runs | … reward-0 runs |
|---|---|---|---|---|
| airline | 213 / 531 | 42 of 64 | **18 of 181** (10%) | **123 of 415** (30%) |
| retail | 1269 / 749 | 38 of 55 | **3 of 1175** (0.3%) | **0 of 634** |

Calls the API rejected are excluded above. A block rule fired on 10 of 32 airline and 62 of 94 retail API-rejected calls in reward-1 runs. Those are true positives the agent later recovered from.

- **Airline.** The Python layer separates the classes well: blocks are 3× more frequent in failed runs. **All 18 reward-1 blocks were investigated.** Each is either a genuine wiki violation that τ-bench's reward does not penalise (reward only compares the final DB), or a τ-bench ground-truth conflict (below).
- **Retail.** Failed runs fail through *wrong choices*: wrong item, wrong order, wrong option. Only `dialogue` predicates could judge these, against what the user asked. The deterministic rules mostly duplicate API guards: 62 of 94 rejected calls in reward-1 runs would have been blocked before execution.
- The text-with-tool-call rules (AIR-R006 / RET-R009, `warn`) fire on 68–73% of write calls of **both** models. They are noisy, but harmless as warnings.

## Investigation of reward-1 firings (accepted calls, `block` rules)

| Rule | Firings before → after fixes | Finding | Action |
|---|---|---|---|
| AIR-R020–R022 on `update_reservation_baggages` | 10 → 0 | **Predicate bug caused by a τ-bench quirk.** `update_reservation_flights` never writes `reservation.cabin`. After a basic-economy→economy upgrade, the stored cabin stayed `basic_economy`, so the gold allowance was computed as 2 instead of 3 (airline task 5, reservation FQ8APE). | Added `context.with_effective_cabin`, used by every cabin predicate. Regression test `test_effective_cabin_after_upgrade` plus the bag test "update after cabin upgrade". Documented in `airline_data_notes.md`. |
| AIR-R026 / AIR-R039 ("owner identified") | 23 / 9 → 8 / 3 | **Predicate too strict.** It required a `get_user_details` call, but agents often get the user id from the user's message (e.g. task 26). | The predicate now also accepts a **verbatim, whole-token mention of the owner's id in a user message**. This is deterministic; no LLM is needed. |
| AIR-R026 / AIR-R039 (remaining 11) | — | **True positives under the wiki.** In sonnet tasks 10 and 43 the agent acted on a reservation id alone and never obtained the user id. The wiki requires it ("must first obtain the user id and the reservation id"). The DB outcome was correct, so reward = 1. | Kept. The cost at runtime is one extra question to the user. |
| AIR-R043 ("trip not flown") | 5 | **τ-bench ground-truth conflict.** Tasks 26/27 expect `cancel_reservation(NQNU5R)`. Both segments of NQNU5R are dated 2024-05-13/14 with status `landed`, so the trip is entirely flown. The task instruction calls it "upcoming". | Kept as the wiki says. **Open question** for the user. |
| AIR-R028 (no flight change in basic economy) | 5 (2 accepted) | **True positive.** In sonnet task 9 (trials 1–2) the agent replaced a segment of basic-economy reservation K1NW8N while upgrading it. The policy-compliant ground truth is cancel and rebook. | Kept. |
| AIR-R016 (≤ 1 certificate) | 1 | **True positive.** The agent booked with three certificates (sonnet task 9). The API does not check counts. The ground truth uses three separate bookings. | Kept. |
| RET-R001 (authenticated) | 3 | **True positive.** In sonnet tasks 35 and 58, `find_user_id_by_email` failed, and the agent then used the user-supplied id directly. The wiki forbids exactly this. | Kept. |
| RET-R027 (new item ≠ old item) | 17 + 26 (32 accepted) | **τ-bench ground-truth conflict.** Tasks 18 and 108 *require* exchanging an item for the **same** item ("exchange for the same item", "same specs"); the wiki says "different product option". The other firings are harmless no-op pairs (an item mapped to itself inside a larger modification, task 36). | **Enforcement downgraded `block` → `warn`** (B4: a false positive would block a correct action). The curated rule stays literal. **Open question.** |

Reward-0 spot checks found **no predicate bugs**. Examples:
- AIR-R029/R030 caught real destination changes (ATL→PHL became ATL→EWR; DTW→LGA became DTW→JFK) and round trips collapsed to one segment.
- AIR-R043 caught a flown trip cancelled when the ground truth does not cancel it (I6M8JQ).
- AIR-R045 caught certificates sent to regular / economy / uninsured users (tasks 37, 40).

## Full tables (after fixes)

`r1`/`r0` = runs with reward 1 / 0; `eval` = rule in the circuit of the call; `n/e` = not evaluable.

### airline

Write-tool calls analysed: 213 in reward-1 runs, 531 in reward-0 runs. Python-evaluable rules: 42 of 64. Kleene logic: a rule is 'not evaluable' (n/e) only if a None predicate leaves its value undetermined.

Calls a `block` rule would stop: reward-1 runs: 18 of 181 API-accepted (+10 of 32 API-rejected); reward-0 runs: 123 of 415 API-accepted (+57 of 116 API-rejected).

| Rule | Curated | Enf. | API | Logic | r1 eval | r1 fired | r1 n/e | r0 eval | r0 fired | r0 n/e | fired & API-rejected (r1/r0) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 3 | AIR-R005 | block | no | `booking_db_write IMPLIES single_tool_call_in_turn` | 202 | 0 | 0 | 512 | 0 | 0 | 0/0 |
| 4 | AIR-R005 | block | no | `compensation IMPLIES single_tool_call_in_turn` | 11 | 0 | 0 | 19 | 0 | 0 | 0/0 |
| 8 | AIR-R006 | warn | no | `booking_db_write IMPLIES NOT text_with_tool_call` | 202 | 153 | 0 | 512 | 334 | 0 | 19/64 |
| 9 | AIR-R006 | warn | no | `compensation IMPLIES NOT text_with_tool_call` | 11 | 6 | 0 | 19 | 16 | 0 | 0/0 |
| 14 | AIR-R010 | block | yes | `book_reservation IMPLIES all_new_flights_available` | 18 | 0 | 6 | 131 | 0 | 22 | 0/0 |
| 17 | AIR-R013 | block | no | `book_reservation IMPLIES passenger_count_at_most_five` | 18 | 0 | 0 | 131 | 0 | 0 | 0/0 |
| 18 | AIR-R014 | block | no | `book_reservation IMPLIES all_passengers_have_name_and_dob` | 18 | 0 | 0 | 131 | 0 | 0 | 0/0 |
| 19 | AIR-R015 | block | yes | `book_reservation IMPLIES passengers_share_flights_and_cabin` | 18 | 0 | 0 | 131 | 0 | 0 | 0/0 |
| 20 | AIR-R016 | block | no | `book_reservation IMPLIES certificate_count_at_most_one` | 18 | 1 | 0 | 131 | 25 | 0 | 0/11 |
| 21 | AIR-R017 | block | no | `book_reservation IMPLIES credit_card_count_at_most_one` | 18 | 0 | 0 | 131 | 1 | 0 | 0/0 |
| 22 | AIR-R018 | block | no | `book_reservation IMPLIES gift_card_count_at_most_three` | 18 | 0 | 0 | 131 | 1 | 0 | 0/0 |
| 23 | AIR-R019 | block | yes | `book_reservation IMPLIES payment_methods_in_user_profile` | 18 | 0 | 0 | 131 | 0 | 2 | 0/0 |
| 24 | AIR-R020 | block | no | `(book_reservation AND booking_user_is_regular) IMPLIES nonfree_baggages_match_tier_allowance` | 18 | 0 | 0 | 131 | 3 | 2 | 0/1 |
| 25 | AIR-R021 | block | no | `(book_reservation AND booking_user_is_silver) IMPLIES nonfree_baggages_match_tier_allowance` | 18 | 0 | 0 | 131 | 1 | 2 | 0/0 |
| 26 | AIR-R022 | block | no | `(book_reservation AND booking_user_is_gold) IMPLIES nonfree_baggages_match_tier_allowance` | 18 | 0 | 0 | 131 | 13 | 2 | 0/7 |
| 27 | AIR-R023 | block | yes | `book_reservation IMPLIES payment_total_matches_price` | 18 | 0 | 6 | 131 | 23 | 22 | 0/16 |
| 29 | AIR-R025 | block | yes | `(book_reservation AND insurance_purchased) IMPLIES payment_total_matches_price` | 18 | 0 | 0 | 131 | 0 | 0 | 0/0 |
| 30 | AIR-R039 | block | no | `cancel_reservation IMPLIES reservation_owner_identified` | 48 | 3 | 0 | 140 | 8 | 1 | 0/0 |
| 31 | AIR-R040 | block | no | `cancel_reservation IMPLIES reservation_details_retrieved` | 48 | 0 | 0 | 140 | 4 | 0 | 0/0 |
| 34 | AIR-R043 | block | no | `cancel_reservation IMPLIES NOT any_segment_departed` | 48 | 5 | 0 | 140 | 27 | 2 | 0/0 |
| 35 | AIR-R026 | block | no | `modify_reservation IMPLIES reservation_owner_identified` | 136 | 9 | 0 | 241 | 14 | 0 | 1/3 |
| 36 | AIR-R027 | block | no | `modify_reservation IMPLIES reservation_details_retrieved` | 136 | 0 | 0 | 241 | 2 | 0 | 0/0 |
| 37 | AIR-R010 | block | yes | `update_reservation_flights IMPLIES all_new_flights_available` | 101 | 0 | 0 | 186 | 0 | 0 | 0/0 |
| 38 | AIR-R028 | block | no | `(update_reservation_flights AND reservation_is_basic_economy) IMPLIES flights_unchanged` | 101 | 5 | 0 | 186 | 25 | 0 | 3/12 |
| 39 | AIR-R029 | block | no | `update_reservation_flights IMPLIES itinerary_endpoints_preserved` | 101 | 0 | 0 | 186 | 20 | 0 | 0/3 |
| 40 | AIR-R030 | block | no | `update_reservation_flights IMPLIES trip_type_preserved` | 101 | 1 | 0 | 186 | 17 | 0 | 1/8 |
| 41 | AIR-R032 | block | yes | `update_reservation_flights IMPLIES single_cabin_for_all_flights` | 101 | 0 | 0 | 186 | 0 | 0 | 0/0 |
| 42 | AIR-R037 | block | yes | `(update_reservation_flights AND flights_changed) IMPLIES payment_is_gift_card_or_credit_card` | 101 | 6 | 8 | 186 | 11 | 20 | 6/11 |
| 44 | AIR-R020 | block | no | `(update_reservation_baggages AND booking_user_is_regular) IMPLIES nonfree_baggages_match_tier_allowance` | 16 | 0 | 0 | 50 | 2 | 8 | 0/0 |
| 45 | AIR-R021 | block | no | `(update_reservation_baggages AND booking_user_is_silver) IMPLIES nonfree_baggages_match_tier_allowance` | 16 | 0 | 0 | 50 | 13 | 8 | 0/6 |
| 46 | AIR-R022 | block | no | `(update_reservation_baggages AND booking_user_is_gold) IMPLIES nonfree_baggages_match_tier_allowance` | 16 | 0 | 0 | 50 | 7 | 8 | 0/0 |
| 47 | AIR-R033 | block | no | `update_reservation_baggages IMPLIES total_baggages_not_decreased` | 16 | 0 | 0 | 50 | 0 | 0 | 0/0 |
| 48 | AIR-R035 | block | yes | `update_reservation_passengers IMPLIES passenger_count_unchanged` | 19 | 0 | 0 | 5 | 0 | 0 | 0/0 |
| 49 | AIR-R045 | block | no | `send_certificate IMPLIES (user_is_silver_or_gold OR focus_reservation_has_insurance OR focus_reservation_is_business)` | 11 | 0 | 0 | 19 | 8 | 0 | 0/0 |
| 51 | AIR-R047 | block | no | `send_certificate IMPLIES reservation_facts_checked` | 11 | 0 | 0 | 19 | 0 | 0 | 0/0 |

### retail

Write-tool calls analysed: 1269 in reward-1 runs, 749 in reward-0 runs. Python-evaluable rules: 38 of 55. Kleene logic: a rule is 'not evaluable' (n/e) only if a None predicate leaves its value undetermined.

Calls a `block` rule would stop: reward-1 runs: 3 of 1175 API-accepted (+62 of 94 API-rejected); reward-0 runs: 0 of 634 API-accepted (+98 of 115 API-rejected).

| Rule | Curated | Enf. | API | Logic | r1 eval | r1 fired | r1 n/e | r0 eval | r0 fired | r0 n/e | fired & API-rejected (r1/r0) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 3 | RET-R008 | block | no | `db_write IMPLIES single_tool_call_in_turn` | 1269 | 0 | 0 | 749 | 0 | 0 | 0/0 |
| 8 | RET-R009 | warn | no | `db_write IMPLIES NOT text_with_tool_call` | 1269 | 915 | 0 | 749 | 462 | 0 | 59/55 |
| 16 | RET-R001 | block | no | `db_write IMPLIES user_authenticated` | 1269 | 3 | 0 | 749 | 0 | 0 | 0/0 |
| 17 | RET-R002 | block | no | `db_write IMPLIES all_referenced_entities_owned` | 1269 | 0 | 3 | 749 | 0 | 0 | 0/0 |
| 20 | RET-R013 | block | yes | `pending_order_write IMPLIES order_status_is_pending` | 632 | 2 | 0 | 362 | 25 | 0 | 2/25 |
| 21 | RET-R015 | block | no | `pending_order_write IMPLIES order_status_checked` | 632 | 0 | 0 | 362 | 0 | 0 | 0/0 |
| 22 | RET-R014 | block | yes | `delivered_order_write IMPLIES order_status_is_delivered` | 578 | 18 | 0 | 327 | 56 | 0 | 18/56 |
| 23 | RET-R015 | block | no | `delivered_order_write IMPLIES order_status_checked` | 578 | 0 | 0 | 327 | 0 | 0 | 0/0 |
| 25 | RET-R021 | block | yes | `cancel_pending_order IMPLIES cancel_reason_is_valid` | 208 | 0 | 0 | 83 | 0 | 0 | 0/0 |
| 26 | RET-R023 | block | yes | `modify_pending_order_payment IMPLIES payment_differs_from_original` | 16 | 0 | 0 | 2 | 0 | 0 | 0/0 |
| 27 | RET-R024 | block | yes | `(modify_pending_order_payment AND new_payment_is_gift_card) IMPLIES gift_card_covers_order_total` | 16 | 4 | 0 | 2 | 0 | 0 | 4/0 |
| 28 | RET-R016 | block | yes | `modify_pending_order_items IMPLIES NOT items_modified_before_for_order` | 276 | 0 | 0 | 182 | 0 | 0 | 0/0 |
| 31 | RET-R025 | block | yes | `modify_pending_order_items IMPLIES replacement_items_same_product` | 276 | 1 | 31 | 182 | 0 | 21 | 1/0 |
| 32 | RET-R026 | block | yes | `modify_pending_order_items IMPLIES replacement_items_available` | 276 | 8 | 32 | 182 | 0 | 21 | 8/0 |
| 33 | RET-R027 | warn | no | `modify_pending_order_items IMPLIES replacement_items_differ` | 276 | 17 | 23 | 182 | 5 | 6 | 7/1 |
| 35 | RET-R029 | block | yes | `(modify_pending_order_items AND new_payment_is_gift_card) IMPLIES gift_card_covers_price_difference` | 276 | 0 | 12 | 182 | 0 | 8 | 0/0 |
| 36 | RET-R012 | block | yes | `modify_pending_order_items IMPLIES (item_ids_are_order_items AND new_item_ids_are_item_ids)` | 276 | 0 | 3 | 182 | 0 | 4 | 0/0 |
| 37 | RET-R017 | block | yes | `exchange_delivered_order_items IMPLIES NOT exchange_done_before_for_order` | 266 | 0 | 0 | 150 | 5 | 0 | 0/5 |
| 40 | RET-R025 | block | yes | `exchange_delivered_order_items IMPLIES replacement_items_same_product` | 266 | 0 | 20 | 150 | 1 | 12 | 0/1 |
| 41 | RET-R026 | block | yes | `exchange_delivered_order_items IMPLIES replacement_items_available` | 266 | 0 | 20 | 150 | 1 | 13 | 0/1 |
| 42 | RET-R027 | warn | no | `exchange_delivered_order_items IMPLIES replacement_items_differ` | 266 | 26 | 0 | 150 | 8 | 0 | 4/3 |
| 44 | RET-R029 | block | yes | `(exchange_delivered_order_items AND new_payment_is_gift_card) IMPLIES gift_card_covers_price_difference` | 266 | 4 | 10 | 150 | 2 | 3 | 4/2 |
| 45 | RET-R012 | block | yes | `exchange_delivered_order_items IMPLIES (item_ids_are_order_items AND new_item_ids_are_item_ids)` | 266 | 0 | 0 | 150 | 9 | 1 | 0/9 |
| 47 | RET-R031 | block | yes | `return_delivered_order_items IMPLIES refund_to_original_or_gift_card` | 312 | 25 | 0 | 177 | 5 | 0 | 25/5 |
| 48 | RET-R012 | block | yes | `return_delivered_order_items IMPLIES item_ids_are_order_items` | 312 | 0 | 0 | 177 | 3 | 0 | 0/3 |

