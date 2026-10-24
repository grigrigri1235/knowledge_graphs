# Reading notes: v3 facts, rules and the decision audit (for tracker v4)

Written 2026-10-23 by a read-only planning agent. $0: no code run, no Python, no network, no LLM call.
Everything about τ³-bench in section 6 is **UNVERIFIED** (from memory of τ²-bench; nothing was downloaded).

**Sources read**
- `knowledge_retention.md` sections 3.2-3.7, 4.3-4.5, 6.1, 7 (method, fact model, K2 lessons).
- `predicate_correctness/state_tracker/v3/`: `facts_v3_airline.json` (42 facts), `facts_v3_retail.json` (24 facts),
  `rule_table.py`, `code_helpers.py`, `tool_check.py`, `info_classes.py` (head), `facts_format_v3.py` (head).
- `predicate_correctness/from_shieldagent/rules/{airline,retail}/rules.md` (the frozen TGR rules, their sentences
  and dispositions; the rule table is built from `rule_set.json` next to them).
- `predicate_correctness/output/eval_v3/`: `p2_rule_table.md`, `p3_tool_labels.md`, `p4_audit.md`,
  `p4_audit_recheck.md`, `p5_retail_notes.md`, `p6_tool_agreement.md`, `p7_structure.md`,
  `direct_facts_diagnosis.md`, `B3_diagnosis.md`, plus `tiny_question_audit.md`, `p11_offline.md` (head),
  `p12_report.md` (head).
- v1 policies: `/home/azureuser/refs/tau-bench/tau_bench/envs/airline/wiki.md`, `.../retail/wiki.md`; v1 tool
  signatures in `.../envs/{airline,retail}/tools/*.py`.
- Logs of this reading: `predicate_correctness/output/logs/v4_facts_*.txt`.

**Short words used below**
- *DB* = the database copy at the check, after τ-bench's own tool code replayed every earlier call (so it is the
  real world state). *event* = a tool call that worked (output not "Error..."). *args* = the pending call's
  arguments. *text* = code on message text (exact strings, ids, positions). *Kn* = tiny yes/no question n.
- *block value* = the value of the fact that makes the rule fail.
- "lost" = v3 failed a task the old guard (frozen TGR) passed, and the deciding block came from that item.

---

## 1. The policy rules (frozen TGR rules, 34 airline + 64 retail = 98)

The rules are TGR's, written by an LLM from the v1 policy. v3 never changed them. 82 of 98 have one fact; the
largest (airline 25) has 6. All are "action IMPLIES condition". Sentence ids (S..) point into the v1 policy (the
rule set's own numbering, one id per sentence of `wiki.md`). Rule table: 0 temporal rules, 0 rules that cannot hold.

### 1.1 Airline (34 rules)
| id | rule (short) | gates (tool) | facts it needs | sentences |
|---|---|---|---|---|
| 1 | list details + explicit yes before booking | book_reservation | pending_database_change_details_listed_and_explicitly_confirmed | S3 |
| 2 | same, before a flight change | update_reservation_flights | same | S3 |
| 3 | same, before a bag change | update_reservation_baggages | same | S3 |
| 4 | same, before a passenger change | update_reservation_passengers | same | S3 |
| 5 | user id, trip type, origin, destination obtained | book_reservation | booking_required_information_established | S9 |
| 6 | at most 5 passengers | book_reservation | booking_has_at_most_five_passengers | S10 |
| 7 | first name, last name, DOB per passenger | book_reservation | passenger_identity_details_established | S11 |
| 8 | all passengers same flights and cabin | book_reservation | all_booking_passengers_share_flights_and_cabin | S12 |
| 9 | ≤1 certificate, ≤1 credit card, ≤3 gift cards | book_reservation | booking_payment_method_counts_within_limits | S13 |
| 10 | payment methods in profile | book_reservation | booking_payment_methods_found_in_user_profile | S15 |
| 11 | regular member → regular bag allowance | book_reservation | booking_user_is_regular_member (NOT), regular_member_booking_baggage_counts_correct | S16 |
| 12 | silver → silver allowance | book_reservation | booking_user_is_silver_member (NOT), silver_member_booking_baggage_counts_correct | S17 |
| 13 | gold → gold allowance | book_reservation | booking_user_is_gold_member (NOT), gold_member_booking_baggage_counts_correct | S18 |
| 14 | insurance asked and matched | book_reservation | booking_insurance_decision_established_and_matched | S20 |
| 15 | user id + reservation id obtained | update_reservation_flights | modification_user_and_reservation_ids_established | S21 |
| 16 | same | update_reservation_baggages | same | S21 |
| 17 | same | update_reservation_passengers | same | S21 |
| 18 | basic economy: flights may not change (cabin-only change OK) | update_reservation_flights | pending_flight_update_is_basic_economy (NOT), pending_flight_segments_are_unchanged | S22, S26 (S26 = exception) |
| 19 | keep origin, destination, trip type | update_reservation_flights | origin_destination_and_trip_type_preserved | S23, S25 |
| 20 | one cabin for all segments | update_reservation_flights | all_pending_flight_segments_have_one_cabin | S28 |
| 21 | bags may not be removed | update_reservation_baggages | pending_baggage_total_not_reduced | S29 |
| 22 | passenger count unchanged | update_reservation_passengers | pending_passenger_count_unchanged | S31 |
| 23 | flights changed → user picked a gift card / credit card | update_reservation_flights | pending_flight_update_changes_flights (NOT), user_selected_eligible_flight_change_payment_method | S33, S34 |
| 24 | user id, reservation id, reason obtained | cancel_reservation | cancellation_context_established | S35 |
| 25 | within 24 h OR airline cancelled OR business OR ((basic) economy AND insurance AND health/weather reason) | cancel_reservation | cancellation_is_within_24_hours, airline_cancelled_flight_confirmed, reservation_has_business_cabin, reservation_has_basic_or_economy_cabin, reservation_has_travel_insurance, insured_cancellation_condition_met | S36-S39 (S36 = exception) |
| 26 | no used segment | cancel_reservation | reservation_has_no_used_flight_segments | S40, S41 |
| 27 | transfer only if tools cannot do it | transfer_to_human_agents | request_cannot_be_handled_with_available_tools | S8 |
| 28 | certificate only for an eligible cancelled-flight or delayed-flight case, right amount | send_certificate | cancelled_flight_certificate_send_conditions_met OR delayed_flight_certificate_send_conditions_met | S43, S44 |
| 29 | certificate only after complaint + explicit ask | send_certificate | user_complained_about_relevant_flight_situation, user_explicitly_requested_compensation | S45 |
| 30 | no certificate for regular + no insurance + (basic) economy | send_certificate | compensation_is_prohibited_for_relevant_reservation (NOT) | S46 |
| 31 | reply offering a cancelled-flight certificate → eligible + right amount | respond | pending_response_offers_cancelled_flight_certificate (NOT), cancelled_flight_certificate_response_conditions_and_amount_met | S43 |
| 32 | reply offering a delayed-flight certificate → eligible + change/cancel done + right amount | respond | pending_response_offers_delayed_flight_certificate (NOT), delayed_flight_certificate_response_conditions_and_amount_met | S44 |
| 33 | reply offering compensation → complaint + explicit ask | respond | pending_response_offers_any_compensation_certificate (NOT), user_complained_about_relevant_flight_situation, user_explicitly_requested_compensation | S45 |
| 34 | reply offering compensation → not the prohibited case | respond | pending_response_offers_any_compensation_certificate (NOT), compensation_is_prohibited_for_relevant_reservation (NOT) | S46 |

Airline gates 7 tools (6 writes + transfer) and `respond`. No airline rule gates a read tool. 42 facts in 51
(rule, fact) pairs; 11 pairs block with true, 40 with false.

### 1.2 Retail (64 rules)
| id(s) | rule (short) | gates (tool) | facts it needs | sentences |
|---|---|---|---|---|
| 1 | email lookup uses an email the user typed | find_user_id_by_email | email_identity_provided_by_user | S2, S3 |
| 2 | name+zip lookup uses values the user typed | find_user_id_by_name_zip | name_and_zip_identity_provided_by_user | S2, S3 |
| 3 | no user data in a reply before login | respond | user_specific_information_disclosed (NOT), user_authenticated | S2-S4 |
| 4-14 | login first (one rule per tool) | 4 get_user_details, 5 get_order_details, 6 get_product_details, 7 list_all_product_types, 8 cancel_pending_order, 9 modify_pending_order_address, 10 modify_pending_order_items, 11 modify_pending_order_payment, 12 modify_user_address, 13 return_delivered_order_items, 14 exchange_delivered_order_items | user_authenticated | S2, S3 |
| 15-27 | not for another user (one rule per tool) | 15 find_user_id_by_email, 16 find_user_id_by_name_zip, 17 get_user_details, 18 get_order_details, 19 get_product_details, 20 list_all_product_types, 21 cancel_pending_order, 22 exchange, 23 modify address, 24 modify items, 25 modify payment, 26 modify_user_address, 27 return | request_is_for_another_user (NOT) | S5 |
| 28 | reply does no task for another user | respond | response_performs_task_for_another_user (NOT) | S5 |
| 29 | transfer only if out of scope | transfer_to_human_agents | request_cannot_be_handled_within_scope | S10 |
| 30, 32, 34, 36, 38, 40, 42 | details listed before the write | 30 cancel, 32 exchange, 34 modify address, 36 modify items, 38 modify payment, 40 modify_user_address, 42 return | consequential_action_details_listed | S6 (+S12, S21, S28) |
| 31, 33, 35, 37, 39, 41, 43 | explicit yes to the listing | same tools, in the same order | user_explicitly_confirmed_pending_action | S6 (+S21) |
| 44 | order pending and checked | cancel_pending_order | order_status_checked_pending | S11 |
| 45 | reason is 'no longer needed' / 'ordered by mistake' | cancel_pending_order | cancellation_reason_is_allowed | S12 |
| 46 | user confirmed order id + reason | cancel_pending_order | user_confirmed_cancellation_order_and_reason | S12 |
| 47, 48, 49 | order pending and checked | modify address / items / payment | order_status_checked_pending | S14 |
| 50 | user chose the one new payment method | modify_pending_order_payment | user_chose_pending_payment_method | S16 |
| 51 | new method differs from the original | modify_pending_order_payment | payment_method_differs_from_original | S16 |
| 52 | gift card covers the order total | modify_pending_order_payment | payment_method_is_gift_card (NOT), gift_card_balance_covers_order_total | S17 |
| 53 | reminded to include all items (modify) | modify_pending_order_items | agent_reminded_user_to_include_all_items_for_modification | S22 |
| 54 | new item available, same product, other option | modify_pending_order_items | item_replacements_are_available_same_product_different_option | S23, S24 |
| 55 | user gave the price-difference payment method | modify_pending_order_items | user_chose_price_difference_payment_method | S25 |
| 56 | gift card covers the price difference | modify_pending_order_items | payment_method_is_gift_card (NOT), gift_card_balance_covers_price_difference | S26 |
| 57 | order delivered and checked | return_delivered_order_items | order_status_checked_delivered | S27 |
| 58 | user confirmed order id, items, refund method | return_delivered_order_items | user_confirmed_return_order_items_and_method | S28 |
| 59 | refund to original method or an existing gift card | return_delivered_order_items | return_refund_method_is_original_or_existing_gift_card | S29 |
| 60 | order delivered and checked | exchange_delivered_order_items | order_status_checked_delivered | S31 |
| 61 | reminded to include all items (exchange) | exchange_delivered_order_items | agent_reminded_user_to_include_all_items_for_exchange | S32 |
| 62 | new item available, same product, other option | exchange_delivered_order_items | item_replacements_are_available_same_product_different_option | S33, S34 |
| 63 | user gave the price-difference payment method | exchange_delivered_order_items | user_chose_price_difference_payment_method | S35 |
| 64 | gift card covers the price difference | exchange_delivered_order_items | payment_method_is_gift_card (NOT), gift_card_balance_covers_price_difference | S36 |

Retail gates all 14 non-trivial tools (7 writes, 5 reads, 2 logins) plus transfer and `respond`. 24 facts in 68
pairs; 18 block with true, 50 with false. Writes and their rule count: cancel 6 (8, 21, 30, 31, 44, 45, 46),
modify address 5, modify items 9, modify payment 8, modify_user_address 4, return 7, exchange 8.

---

## 2. The facts (66: 38 code only, 28 code + a tiny question)

Every fact has two values, starts false, and takes its block value on a problem (missing argument, type error,
"unclear", failed quote). Parts combine with AND / OR; code parts run first; an unclear part in one OR branch does
not hide the other branch (fixed after L2.4). The `expr` column is the exact v3 rule in short (full text in the JSON
files). Numbers: dev = development data (3,403 conversations, 40,942 checks); live = B2 + B3 v3 arm.

**Code-level checks that hold for all DB / event / argument parts** (p3, p6, p12): replay 23,138 calls, 0 output
differences; DB facts vs τ-bench's own tool on a scratch copy 14,335 agree, **0 disagree** (hold-out 428 / 0);
event parts vs a raw message scan 69,756 agree, 0 disagree; 0 missing fields in the data; live 0 fact failures in
4,675 Direct + facts checks. So the known problems are almost all in the text and question parts.

### 2.1 Retail (24 facts)
| fact | rules | block | source | code rule (short) | known bugs / misses (numbers) |
|---|---|---|---|---|---|
| user_authenticated | 3-14 | false | event | a worked `find_user_id_by_email` / `find_user_id_by_name_zip` call exists | v3: event = raw scan 38,011 / 38,011. v2 judge said false after a working login: 31 too-strict blocks (retail:10 27). Flag: a login made with values the user never typed still counts |
| email_identity_provided_by_user | 1 | false | text | `user_typed(args.email)`: email is a whole token in a user message (lower case, accents removed, whole conversation) | judge-era: 6 train blocks from the 24k-char cut view. p7: code true / judge false 70 checks; 0 logins to another user |
| name_and_zip_identity_provided_by_user | 2 | false | text | `user_typed` for first name, last name, zip (ZIP+4 matches; a name inside a typed user id counts) | judge-era 17 cut-view blocks. p7: 1 added block (with reason); 3 tasks (54, 67, 107) where the typed values match nobody |
| request_is_for_another_user | 15-27 | true | DB OR (text AND K4) | a: the call's object (user id / the order's user_id / the user an email or name+zip finds) is not `me` (first logged-in user). b: a user message to ask about (first login always; catalog reads only on an other-person word screen). c: K4 | part a false at 19,708 / 19,708 dev checks; p7: 0 calls on another user's object. K4 asked 302 times live, 0 yes. Judge (v2) said true 0 times in ~24,000 checks. Gap: no code key at the first login |
| response_performs_task_for_another_user | 28 | true | text OR (text AND K5) | a: the reply holds a DB value of a user other than `me` that no user message holds (info classes). b: always true (screen removed). c: K5 on the reply | **K5 asked 1,678 times live, 11 yes, all 11 wrong** (poets, the user's own name); lost retail/62/t2. p7 raw scan: 2 replies with another user's value where part a was false ("suite 641") |
| user_specific_information_disclosed | 3 | true | text OR (text AND K14) | a: reply holds an id-like value or amount that a worked user-data tool output showed and no user message holds (info classes). b: a data output exists. c: K14 | K14 asked 0 times live. p7: 0 leaks let through by code (3,670 replies). v2 judge counted the user's own words as leaks: 56 train + 507 Stage A wrong blocks |
| order_status_checked_pending | 44, 47-49 | false | event AND DB | a: a worked `get_order_details` for this order_id. b: `order.status == 'pending'` | v3 0 disagree (DB part); judge-era: judge true / tool false 61 (main+B). Direct + facts arm: 1 correct cited block (status "pending (item modified)") |
| order_status_checked_delivered | 57, 60 | false | event AND DB | a: as above. b: `order.status == 'delivered'` | judge-era: judge true / tool false 111 |
| cancellation_reason_is_allowed | 45 | false | args | `args.reason in ['no longer needed','ordered by mistake']` (exact, like the tool) | tool agrees 878 / 0 |
| payment_method_is_gift_card | 52, 56, 64 | true | args | `'gift_card' in args.payment_method_id` (id prefix = DB source for all 695 retail methods) | right; it is a tipping fact on the OR side in 214 judge-era too-strict blocks (the balance fact was the real cause) |
| gift_card_balance_covers_order_total | 52 | false | DB | the method is the order user's gift card and `balance >= order.payment_history[0].amount` | v2 "never shown" bug 2; v3 0 disagree |
| gift_card_balance_covers_price_difference | 56, 64 | false | DB | gift card of the order's user; `balance >= diff` or `diff <= 0`; diff = Σ(new variant price − old item price), rounded to cents only for exchange (each tool's own sum) | **the eval v2 harm fact**: v2 "never shown" read as false, 218 main + 3 Stage B wrong values; fixing it removes 61 too-strict blocks, adds 0. v3: 0 disagree; 8 missing-argument problems |
| item_replacements_are_available_same_product_different_option | 54, 62 | false | DB | order exists; non-empty equal-length lists; each old item in the order (with duplicates); each new id is an available variant of the old item's product and differs from it (pairs by position, as the tool's zip) | v2 bugs 7 never-shown + 1 shown-differs (main), 7 (B); v3 0 disagree. Reading: empty list = false (τ-bench accepts it) |
| payment_method_differs_from_original | 51 | false | DB | `args.payment_method_id != order.payment_history[0].payment_method_id` | v2 bug 1; v3 0 disagree. **Gap:** the tool also refuses "exactly one payment" (2nd payment change); no fact |
| return_refund_method_is_original_or_existing_gift_card | 59 | false | DB | method is in the order user's profile AND (it is the original method OR 'gift_card' in id) | v2 bug 4 (shown, differs); v3 0 disagree. **Gap:** the tool's "some item not found" (items not in the order) has no fact |
| consequential_action_details_listed | 30, 32, 34, 36, 38, 40, 42 | false | text AND K2 | a: up to 4 newest agent messages naming one call detail (order id, item ids / names, payment forms, reason, new address1 / zip). b: K2 v2: one message states every checkable line (code renders lines with allowed forms) | **The main v3 failure.** K2 live: 206 blocks (165 alone) on B2+B3; **B3: 11 of 17 lost tasks** (8 card line, 3 order id), = the whole −0.245; B2 val 4 lost, train 5. Card line can never match: payment-id digits ≠ last_four for 0 of 239 retail cards. Order id must be in the same message (33+7 B3 blocks). Quote check failed on good listings (28 of 29 failures had every line). ~40 of 415 "no" had every line. Block message names no line → 29 calls blocked 3+ times, 4 recovered. Hold-out: K2 79 of 177 tiny-vs-judge disagreements; dev run 1: 121 of 211 |
| user_explicitly_confirmed_pending_action | 31, 33, 35, 37, 39, 41, 43 | false | text AND K1 | a: listing candidate L, user's next reply r before the call, r not a strict "no" and no later strict no. b: K1 "agrees to exactly this action" | K1 live 42 blocks (21 alone) both domains; wrong patterns: one yes for 2 orders (retail/92 ×3 lost), card named by id digits, "Yes." misread. Stale yes counts (flag) |
| user_confirmed_cancellation_order_and_reason | 46 | false | text AND K1 | same pair as above; K1 with "cancel this order for this reason" | p7 4 added blocks (all tool-accepted, expected). Reason restated by the user, not the agent: 3 K2 too-strict cases |
| user_confirmed_return_order_items_and_method | 58 | false | text AND K1 | same pair; K1 with "return exactly these items with refund to this method" | p7 2 added. K1 says no when the user names the card by id digits (222, 255, 345 B3) |
| user_chose_pending_payment_method | 50 | false | DB AND (text OR (text AND K1)) | d: method in the order user's profile. a: the user's latest payment message names exactly this method (id, id number or its last 4, last_four, unique kind/brand/balance word; negation-aware). b+c: a listing/reply pair naming it + K1 | part d = tool 140 / 0. p7 2 added blocks. Note: part a already accepts id digits; K2 does not |
| user_chose_price_difference_payment_method | 55, 63 | false | DB AND (text OR (text AND K1)) | same as above, for modify items / exchange | part d = tool 4,660 / 0. **p7: structure alone added 44 blocks (33 tool-accepted, 29 expected actions, 38 also blocked by the saved guard)**. 8 missing-argument problems |
| agent_reminded_user_to_include_all_items_for_modification | 53 | false | text AND K3 | a: agent messages after the order id first appears, with a user reply after them. b: K3 | **judge-era: 703 of 1,029 too-strict blocks** (with exchange: 918). v3 K3 live: 55 blocks, 16 of 18 read were right, misses "is this the only item?"; 52 of 55 blocked calls ran later |
| agent_reminded_user_to_include_all_items_for_exchange | 61 | false | text AND K3 | same, items "exchanged" | judge-era 215 too-strict |
| request_cannot_be_handled_within_scope | 29 | false | text AND K13 | a: the newest 2 user messages. b: K13 with the list of what retail tools can do | K13 live (both domains): 90 blocks, 19 of 22 read were right, but 45 of 90 come after a wrong K1/K2 block (dead end); unclear = 28 block causes. Policy "iff" vs the tool text "or the user asks for a human" (flag) |

### 2.2 Airline (42 facts)
| fact | rules | block | source | code rule (short) | known bugs / misses (numbers) |
|---|---|---|---|---|---|
| pending_database_change_details_listed_and_explicitly_confirmed | 1-4 | false | text AND text AND K2 AND K1 | a: latest agent message naming a call detail (flight no., date, passenger name, cabin, bag count next to "bag", reservation id, payment form) with a user reply. b: reply not a strict no. c: K2 v2 lines (reservation id, each flight no.+date, cabin, each passenger first+last+DOB, payment kind+last four, total + paid bags, insurance, certificate amount). d: K1 | K2 too strict: DOB (airline/8/t0, 5/t1 lost), "N paid" bags (4/t2, 5/t0, 5/t2 lost), card last four 0 of 503 airline cards match id digits; model said no to full listings (airline/6/t0, 7/t2). K1: insurance "Yes." unclear lost airline/0/t1. K2 airline blocks: book 16, bags 8, flights 4, passengers 4 |
| booking_required_information_established | 5 | false | text AND ((text AND K15) OR (text AND K1)) | a: `obtained(args.user_id)` (user typed it or a worked tool output showed it). b: origin / destination as upper-case IATA code or the airport table's city in a user message. c: K15 (trip type + direction). d: agent message naming origin+destination with a reply. e: K1 focus trip | code b misses "NY", "LA", "San Fran", "the Big Apple", "Hawaii" (3 blind-set misses); then path d/e. K15 asked 14 live |
| booking_has_at_most_five_passengers | 6 | false | args | `len(passengers) <= 5` | 26 / 26 true dev |
| passenger_identity_details_established | 7 | false | text OR DB (per passenger) | a: first, last, DOB each typed by the user (6 date forms). b: (first, last, dob) equals the booking user or a `saved_passengers` entry in DB | dev: part a false 26 / 26, part b true 26 / 26 (the DB path does the work). Exact, case-sensitive |
| all_booking_passengers_share_flights_and_cabin | 8 | false | args | no passenger has its own cabin / flight list that differs | always true for a well-formed call (the tool takes one cabin) |
| booking_payment_method_counts_within_limits | 9 | false | args | distinct ids: ≤1 `certificate_`, ≤1 `credit_card_`, ≤3 `gift_card_` (prefix = DB source for all 1,486 airline methods) | 3 false of 26 dev |
| booking_payment_methods_found_in_user_profile | 10 | false | DB | user exists and every payment_id is a key of `user.payment_methods` | v2 "never shown" bug; v3 tool 23 / 0 |
| booking_user_is_regular_member / _silver_ / _gold_ | 11 / 12 / 13 | true | DB | `user.membership == 'regular' / 'silver' / 'gold'` | v2 never-shown made all three false, so bag rules always held. v3: right values. In the Direct + facts loop the agent "corrected" itself to regular after the display bug of `compensation_is_prohibited...`, then these facts said gold and blocked again |
| regular / silver / gold_member_booking_baggage_counts_correct | 11 / 12 / 13 | false | args | `nonfree == max(0, total − n_passengers × allowance[cabin])`; allowances regular 0/1/2, silver 1/2/3, gold 2/3/3 (basic, economy, business) | regular 8 / 26 true, silver 8 / 26, gold 26 / 26 dev. Problems unknown_cabin, bad_count |
| booking_insurance_decision_established_and_matched | 14 | false | text AND K1 | a: code picks the user's insurance message (latest agent message with "insurance" + reply, or a later user message naming insurance); `args.insurance in [yes, no]`. b: K1 focus insurance | K1 picked the newest pair, not the earlier yes (airline/25/t2); insurance "Yes." wrong 3 of 8 dev; "Yes, I authorize this booking" to a "no insurance" listing read as no (8/t1, 8/t2) |
| modification_user_and_reservation_ids_established | 15-17 | false | DB AND text AND text | a: reservation exists. b: its owner id obtained (typed or in a worked output). c: reservation id obtained | code only. Dev 329 / 329 true; 0 obtained ids from another user |
| pending_flight_update_is_basic_economy | 18 | true | DB + event | `cabin_now(res) == 'basic_economy'`: cabin of the newest worked flight update, else the DB cabin field | needed because v1 `update_reservation_flights` never writes the cabin field (tool bug; re-check in τ³) |
| pending_flight_segments_are_unchanged | 18 | false | event AND DB | a: worked `get_reservation_details`. b: call flights = DB flights as a multiset of (number, date) | 230 / 271 true dev |
| origin_destination_and_trip_type_preserved | 19 | false | event AND DB | a: looked up. b: order-free route test of the new flight numbers vs the reservation's origin, destination, flight_type | 1 type_error. Legs connecting is not checked |
| all_pending_flight_segments_have_one_cabin | 20 | false | args | no flight entry has its own cabin different from `args.cabin` | always true for a well-formed call; 1 type_error |
| pending_baggage_total_not_reduced | 21 | false | DB | `args.total_baggages >= reservation.total_baggages` (the tool does not check this) | 43 / 43 true dev |
| pending_passenger_count_unchanged | 22 | false | DB | `len(args.passengers) == len(reservation.passengers)` | tool 15 / 0 |
| pending_flight_update_changes_flights | 23 | true | DB | NOT the multiset test above | 41 / 271 true dev |
| user_selected_eligible_flight_change_payment_method | 23 | false | DB AND (text OR (text AND K1)) | a: payment_id is the owner's method with source gift_card / credit_card. b: user's latest payment message names exactly it (id, id number, its last 4, last_four). c+d: listing/reply + K1 | part a = tool 246 / 0. p7: 7 added blocks (2 tool-accepted) |
| cancellation_context_established | 24 | false | DB AND text AND text AND K7 | a: reservation exists. b: owner id obtained. c: reservation id obtained. d: K7 (any reason given) | K7 asked 27 live, 10 yes / 11 no; no blocks seen |
| cancellation_is_within_24_hours | 25 | false | event AND DB | a: looked up. b: `created_at >= 2024-05-14T15:00:00` (policy time − 24 h; created_at read as EST) | 41 of 2,000 reservations inside; judge-era flip "kept" but refuted by DB (0 of 25 blocks were inside 24 h) |
| airline_cancelled_flight_confirmed | 25 | false | event AND DB | a: looked up. b: some reservation flight has status 'cancelled' on its date | v1 has no tool that shows flight status, so only DB can know (τ² may add one, section 6) |
| reservation_has_business_cabin | 25 | false | event AND DB | a: looked up. b: `cabin_now == 'business'` | judge-era tipping fact in 25 too-strict blocks; all right by DB |
| reservation_has_basic_or_economy_cabin | 25 | false | event AND DB | a: looked up. b: `cabin_now in [basic_economy, economy]` | |
| reservation_has_travel_insurance | 25 | false | event AND DB | a: looked up. b: `insurance == 'yes'` (1,005 yes / 995 no) | |
| insured_cancellation_condition_met | 25 | false | text AND K6 | a: health/weather word screen on user messages (kept: 0 blind misses). b: K6 | K6 asked 3 live. judge-era: 13 insured blocks open only on this fact |
| reservation_has_no_used_flight_segments | 26 | false | DB | every flight's status on its date in [available, on time, delayed, cancelled] | v2 bug (critic a): past cancelled flights counted as flown; v3 reads status |
| request_cannot_be_handled_with_available_tools | 27 | false | K13 OR (text AND K16) | a: K13 with the 14 tools and hard limits (passenger count, insurance after booking, removing bags are denials). b: a named reservation of an obtained user has a 'flying' / 'landed' flight (S41). c: K16 (asks to cancel) | K13 refused one gold transfer (airline/36/t2 lost). K16: 12 blocks, always with K13 |
| cancelled_flight_certificate_send_conditions_met | 28 | false | text ×5 AND K8 | a: `obtained(args.user_id)`; b: a reservation of that user named in the chat; c: one had a 'cancelled' flight; d: eligible (silver/gold, insurance yes, or business via cabin_now); e: `amount == 100 × passengers`; f: K8 | never judged in v2 train data; rare in live (K8 9+6 asks) |
| delayed_flight_certificate_send_conditions_met | 28 | false | text ×6 AND K9 AND K11 | as above with 'delayed', plus e: a worked update / cancel on that reservation; amount 50 × passengers; g: K9; h: K11 | 'delayed' exists only on today's flights (41 flight-dates, 23 reservations) |
| cancelled_flight_certificate_response_conditions_and_amount_met | 31 | false | text ×4 AND K12-quote AND K8 | as send, for any obtained user; amount read by code from K12's quote; an offer with no amount passes (flag) | parts c, d true 0 of 1,112 dev |
| delayed_flight_certificate_response_conditions_and_amount_met | 32 | false | text ×5 AND K12-quote AND K9 AND K11 | as send, for a reply | part e true 0 of 1,112 dev |
| user_complained_about_relevant_flight_situation | 29, 33 | false | text AND (K8 OR K9) | a: any user message (screens removed after blind set 3). b: K8 cancelled. c: K9 delayed | screens missed "cxld", "calls off", "dumped", "dleayed" on blind set 3 |
| user_explicitly_requested_compensation | 29, 33 | false | text AND K10 | a: compensation word screen (kept). b: K10 | K10 asked 2 live |
| compensation_is_prohibited_for_relevant_reservation | 30, 34 | true | text (reads DB) | a: an obtained / call user is 'regular'. b: their named reservations (only the cancelled/delayed ones if any) have no insurance and no business cabin | 218 forbidden / 1,782 eligible reservations split exactly. Display bug above (15 wrong Direct + facts decisions) |
| pending_response_offers_any_compensation_certificate | 33, 34 | true | text AND K12 | a: wide `offer` word screen on the reply. b: K12 | K12 asked 820 live, 2 yes, 2 blocks (with code). Screen hits most replies with "$" or "sorry"; a "no offer" allow has no second key when the screen does not hit (flag) |
| pending_response_offers_cancelled_flight_certificate | 31 | true | text AND K12 AND kind | as above; c: kind from K12's quote words, else the user's K8/K9 complaints; undecided = yes | |
| pending_response_offers_delayed_flight_certificate | 32 | true | text AND K12 AND kind | same, kind 'delayed' | |

---

## 3. The decision audit (p4, $0, development data, judge-era guards)

**What it measured.** Each write check got a class from outcomes only: the saved guard decision, the task's
expected actions, τ-bench's tool on a scratch copy, and what ran. "Too strict" = blocked, equals an expected call
exactly, the tool accepts it, and it never ran.

| class | main (Stage A + ours + partner) | Stage B |
|---|---|---|
| write checks | 7,025 | 659 |
| **too strict (wrong blocks)** | **827** (11.8 per 100) | **202** (30.7) |
| delayed (blocked, ran later) | 1,681 | 71 |
| unclear (repeat, near, other) | 1,129 | 132 |
| block, tool refuses (right) | 245 | 71 |
| right allow | 2,991 | 174 |
| allowed but unwanted (reported) | 85 | 1 |
| allow, tool refuses | 67 (37 on a mapped fact = wrong allows) | 8 (6) |

- By agent: weak (nano) 787 + 193 too strict, strong (luna) 40 + 9. Grows with length: nano 8.9 % (<12k chars),
  23.9 % (12-24k), 31.1 % (>24k). By domain: retail 801, airline 26 (main).
- **What was wrong (rules behind the 1,029 too-strict blocks):** retail:53 703 and retail:61 215 (the two judge-set
  reminder facts: 918 of 1,029); retail:56 123 and retail:64 90 (gift-card balance "never shown"); retail:36 33,
  retail:37 27, retail:32 18, retail:33 17 (list / yes); retail:10 27 (login, judge error); retail:54 26
  (replacements); airline:25 25; retail:48 11 (status).
- **v2 code bugs vs the tool:** 218 gift-card-difference "never shown" (the eval v2 harm), 24 other "never shown",
  5 shown-but-differs.
- **Blame tests (keep only if removes ≥ 1 and adds 0):** kept: gift_card_balance_covers_price_difference (−61),
  user_chose_price_difference_payment_method (−1), airline_cancelled_flight_confirmed (−23),
  cancellation_is_within_24_hours (−23), rule airline:25 (−23). The 3 airline keeps are **refuted by the DB**: at
  all 25 blocks the facts were right; 12 had no insurance, so τ-bench's expected cancellation breaks the written
  policy (label noise); 13 were insured and open only on the user's health/weather reason. Not kept: the reminder
  flips (−552 / +11, −125 / +25) because the judge also had status errors.
- **Combined tests:** all 9 DB facts by the tool label: −62, +0. DB facts + both reminders true: **−897, +0**.
- Recheck (RC4): all 7 items pass. Corrections: 827 / 202 is a lower bound (48 more near blocks differ only by item
  order: use an order-blind matcher); removing airline:25 newly allows 3 cancellations the policy forbids; one
  "too strict" block (retail/111/1) was harmless.
- **No rule removal passes** both the outcome test and the DB check, so the frozen rules were kept.

**What happened after the rebuild (for v4's baseline):**
- p11 offline (dev, judge stand-in for questions): v3 removes 2,299 saved blocks, adds 62; changed decisions bad 0;
  too-strict frozen 864 → v3 773 of 7,025.
- p12 hold-out (real tiny answers): **blocks 153 (6.2 %) vs frozen 65 (2.6 %)**; too-strict write blocks **77
  (26.1 %)** vs 9 (3.1 %); changed decisions: good 7, bad 0, suspect 17, undecided 100. 87.6 % of v3 blocks rest on
  a tiny answer. So v3 was much stricter offline, and the stricter part was K1 / K2.
- Live B3 (many writes): 126 v3 blocks; 71 % from K2; 14 % from unclear / failed quotes; 19 writes (13 %) blocked
  and never run.

---

## 4. Facts v3 asked an LLM about that code could know (move to code in v4)

The rule: never ask an LLM what the DB, the event log, the call or exact text can tell. Ordered by harm seen.

| # | where (fact / question) | what code can decide | why it matters (numbers) |
|---|---|---|---|
| 1 | K2 lines in `consequential_action_details_listed` and `pending_database_change_details_listed_and_explicitly_confirmed` | Every id-type line by string match over a stated window (the agent messages since the last write + the user's own words): order / reservation id, item id or product name, flight number + date, passenger names, cabin word, bag numbers, insurance yes/no, certificate amount, address fields, payment (last_four OR any ≥4 trailing digits of the payment id OR the full id; "gift card" / gift card id; "PayPal"; "the card" if only one). v3 already **rendered** these lines in code and then asked the model to match them | K2: 206 live blocks, all 12 lost B3 tasks, 9 lost B2 conversations. The card form the data uses was never accepted. Only meaning lines (new options in words, a reason in other words) need a model |
| 2 | K1 "exactly this action" | the "same details" half: code compares the reply's ids / digits with the call (card id digits = same card; a listed batch = several calls). Leave to the model only "is this reply an agreement?" | K1 42 blocks; 3 B2 val lost (one yes for two orders); card id digits; insurance "Yes." |
| 3 | K5 (`response_performs_task_for_another_user`) | part a (another user's DB value in the reply) is code. Add a code precondition: ask only when the reply holds account data, or drop K5 | asked 1,678 times, 11 yes, 11 wrong; 1 lost |
| 4 | K4 (`request_is_for_another_user`) | after login, ownership is DB (part a). At the first login, code can check the typed identity values exist and belong to one user; ask only on a screen hit | asked 302 times, 0 yes |
| 5 | K16 (S41 transfer) | an event: the agent tried `cancel_reservation` (or the user's reservation has a flown segment, already DB part b) → the transfer is the policy's case | 12 blocks, always beside K13 |
| 6 | K11 (wants to change / cancel the delayed reservation) | part e already needs a worked change / cancel on that reservation (event). That event shows the wish was acted on | asked 0 live; removes a question for free |
| 7 | K12 offer kind and amount | already code from the quote; the "is there an offer" part could use a stricter code pre-check (a certificate / voucher / $ word AND a compensation verb) to cut asks | 820 asks, 2 yes |
| 8 | K8 / K9 complaints | code precondition: ask only if a named reservation of the user really has a cancelled / delayed flight (DB) | screens removed → asked on every user message |
| 9 | K15 trip | origin / destination by code with an alias table checked on the data (NY, LA, San Fran ...); trip type from a small word set; K1 path stays as fallback | 3 blind misses |
| 10 | K13 (transfer) | known code-decidable cases: the user cannot be found (find_user returned Error), a write blocked 2+ times by a tiny question (dead end), a tool error the agent cannot fix | 45 of 90 K13 blocks were dead ends after wrong K1/K2 blocks |
| 11 | `booking_insurance_decision_established_and_matched` window | code picks the newest **yes** reply to a listing that stated insurance, not the newest pair | airline/25/t2, 0/t1 |
| 12 | display of code facts to an LLM (Direct + facts arm) | print final value with sign ("user is a regular member: NO (gold)"), never part plain text | 15 wrong decisions, 1 lost |

Kept as real meaning questions (no code can know): K3 (reminder), K6 (health / weather reason), K7 (a reason
given), K10 (explicit ask for compensation), the agreement part of K1, the "is there an offer" part of K12, the
scope part of K13, K14 (rarely asked).

---

## 5. Things in the v1 policy NOT covered by a v3 rule

From the rule sets' dispositions (not_enforceable / fact) and v3's own gap notes (L2.9, p5, p6 section 7).

**Airline**
- S4 / S7: no made-up information, no subjective advice; deny requests against the policy (no rule; Direct covers
  some of this).
- S5 / S6: one tool call at a time; no reply together with a call.
- S19 "each extra bag is $50": no rule (the booking tool's own price check covers the total).
- S27 cabin change must be paid: no rule; no rule on the payment method of a cabin-only change (S33 is only for
  changed flights; the tool refuses a certificate).
- S30 no insurance after booking: no tool does it (fine).
- S41 "transfer is needed" after a used segment: the transfer *duty* is not enforced (only "do not cancel").
- Domain Basic flight status lines (no sentence ids): "delayed / on time cannot be booked" – no rule; only the tool
  refuses a non-available flight.
- Rule gaps the tool hides: booking with an unknown or unavailable flight (no rule blocks); bag update paid by a
  certificate or a method not in the profile (no rule; tool refuses); a cabin-only flight update for basic economy
  is allowed by rule 18 (exception S26) — check τ³ text.
- No rule ties the reservation to the user being helped beyond "owner id obtained" (airline has no login).
- No rule limits how many certificates are sent, or a certificate after an earlier one.
- S42 / S14 / S24 refund and price facts: outcomes only.

**Retail**
- S7: no made-up information (Direct blocks this often: about 10 of 43 Direct-style blocks).
- S8 / S9: one tool call at a time.
- S20 / Domain basic "exchange or modify tools can only be called once; collect all items into one list": no rule;
  in effect the status facts cover it (after modify the status is "pending (item modified)", after exchange
  "exchange requested").
- S15 "nothing else" can be modified: the tools limit it.
- Domain basic: product id vs item id confusion: no rule.
- Tool checks with no v3 fact: modify payment "exactly one payment for a pending order"; return "some item not
  found" (items not in the order).
- Transfer: the tool description also allows a transfer when the user asks for a human; the policy says "if and
  only if" out of scope; v3 followed the policy.
- `modify_user_address` / address writes: no check that the new address is the one the user gave (only "listed"
  and "confirmed").

**Both:** the intent check (does the call match what the user asked?) is not a policy rule, but most strong-agent
failures are agent mistakes it would catch (KR 7.5 future work).

---

## 6. τ³ airline / retail: what may change (ALL UNVERIFIED until the download) and the diff checklist

τ³-bench = the newest `sierra-research/tau2-bench` (package `tau2`). τ² ported airline and retail from τ-bench v1.
From memory only, so treat every line as a guess to check:
- **Code layout differs:** tools are methods of one toolkit class per domain (`src/tau2/domains/<d>/tools.py`, an
  `@is_tool` decorator), the DB is a typed model (`data_model.py`), data and policy live under
  `data/tau2/domains/<d>/` (`policy.md`, `tasks.json`, a DB file). v3's `state.run_tool` and `tool_check.py` call
  v1 `invoke(data, ...)` functions: they must be ported.
- **Errors may be exceptions, not "Error: ..." strings**, and their texts may differ. `tool_check.TOOL_CHECKS`
  matches exact v1 texts in v1 order: re-map every check.
- **Airline may have a new tool to read a flight's status** (something like `get_flight_status`). Then
  "no tool shows a flight's status" (the reason for DB-only `airline_cancelled_flight_confirmed`) is no longer true,
  and the "looked it up first" event part may want this tool.
- **The `think` tool may be gone**; tool lists and descriptions may be reworded.
- **The v1 cabin bug** (`update_reservation_flights` never writes the cabin field) may be fixed; then `cabin_now`
  must read the DB field.
- **Policy text may be reworded or extended** (τ² policies are longer, e.g. a fixed message after a transfer). TGR's
  frozen rules cite v1 sentences S1-S46 / S1-S38 by text; any change breaks "the rules are not ours, unchanged".
- Task fixes (75+ across domains per the README) may change expected actions of our 99 tasks.
- The current time (2024-05-15 15:00 EST), membership names, cabin names, status words, payment id formats are
  probably the same — check, do not assume.

**Diff checklist (do right after the approved download, $0, by code where possible)**
1. Tool names, both domains: v1 airline 14 (book_reservation, calculate, cancel_reservation, get_reservation_details,
   get_user_details, list_all_airports, search_direct_flight, search_onestop_flight, send_certificate, think,
   transfer_to_human_agents, update_reservation_baggages, update_reservation_flights,
   update_reservation_passengers); v1 retail 16 (calculate, cancel_pending_order, exchange_delivered_order_items,
   find_user_id_by_email, find_user_id_by_name_zip, get_order_details, get_product_details, get_user_details,
   list_all_product_types, modify_pending_order_address, modify_pending_order_items, modify_pending_order_payment,
   modify_user_address, return_delivered_order_items, think, transfer_to_human_agents). TGR circuits key on these
   names: a renamed or new write tool has no rule.
2. Argument names, types and required lists, per write tool. v1: book_reservation (user_id, origin, destination,
   flight_type, cabin, flights[{flight_number, date}], passengers[{first_name, last_name, dob}],
   payment_methods[{payment_id, amount}], total_baggages, nonfree_baggages, insurance); update_reservation_flights
   (reservation_id, cabin, flights, payment_id); update_reservation_baggages (reservation_id, total_baggages,
   nonfree_baggages, payment_id); update_reservation_passengers (reservation_id, passengers); cancel_reservation
   (reservation_id); send_certificate (user_id, amount); retail cancel (order_id, reason); modify address and
   modify_user_address (order_id / user_id, address1, address2, city, state, country, zip); modify items and
   exchange (order_id, item_ids, new_item_ids, payment_method_id); modify payment (order_id, payment_method_id);
   return (order_id, item_ids, payment_method_id); find by email (email); by name+zip (first_name, last_name, zip).
   Every v3 `expr` reads these keys.
3. Each tool's checks, their order and their texts (re-derive `TOOL_CHECKS` / `TOOL_FACTS`); side effects (cabin
   write, status writes such as 'cancelled', 'pending (item modified)', 'return requested', 'exchange requested';
   gift card balance changes; certificate ids).
4. DB fields v3 reads. Retail: order.status, order.user_id, order.items[].item_id / product_id / price,
   order.payment_history[0].payment_method_id / amount, user.email, user.name.first_name / last_name,
   user.address.zip, user.payment_methods{id: source, balance, last_four, brand}, product.variants{item_id:
   available, price, options}. Airline: reservation.user_id / origin / destination / flight_type / cabin / flights
   [flight_number, date, price] / passengers / insurance / created_at / total_baggages / nonfree_baggages / status,
   user.membership / name / dob / saved_passengers / payment_methods{id: source, amount}, flight.origin /
   destination / dates{date: status, available_seats, prices}.
5. Value sets: order statuses; flight statuses ('available', 'on time', 'delayed', 'flying', 'landed',
   'cancelled'); membership ('regular', 'silver', 'gold'); cabins ('basic_economy', 'economy', 'business');
   flight_type ('one_way', 'round_trip'); insurance ('yes', 'no'); cancel reasons ('no longer needed', 'ordered by
   mistake'); payment id prefixes = `source` (v1: 695 retail, 1,486 airline methods).
6. Data facts v3 relied on (re-count on the τ³ DB): no card's last_four equals its id's last 4 (0 / 239 retail,
   0 / 503 airline); 0 pending orders with 2+ payments; no product with two variants of the same options; emails
   and name+zip unique; created_at near the 24 h edge; 'delayed' only on today's flights; 218 / 1,782 compensation
   split.
7. Policy text: diff `policy.md` sentence by sentence against v1 `wiki.md` (and the rule set's S-ids). For each
   changed sentence: which TGR rule cites it, and does the frozen rule still say the same thing? Decide whether
   the old-guard arm can run unchanged.
8. Tool descriptions (they act as policy too: e.g. transfer "when the user asks for a human", return "explain the
   detail and ask for confirmation").
9. Tasks: map each of our 99 tasks to its τ³ version; diff instructions and expected actions; drop the partner's
   test 66 in every version.
10. Re-run the $0 checks on τ³: replay = saved outputs, DB facts = τ³ tool on a scratch copy (0 disagreements),
    event parts = raw scan, and Gate 0 (rebuild the old guard's decisions) if that arm stays.
