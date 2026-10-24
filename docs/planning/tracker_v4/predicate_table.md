# Tracker v4: the predicate table (τ-bench v1 airline + retail)

Written 2026-10-23 by a planning agent. Cost $0: read-only, stdlib Python counts over the v1 database only, no
network, no LLM call. This is a plan input, not an approved plan.

## The main idea in plain words

- v4 is tracker v3 again, on the same τ-bench v1 harness, data, 98 frozen TGR rules and 66 frozen predicates. No
  rule or predicate is added, removed, renamed or reworded. Only **how each predicate gets its value** changes.
- v3's code was right everywhere. What lost tasks was a few tiny yes/no questions that were too strict. So v4:
  1. lets **code** do every string or database check (the old "details listed" question K2 becomes code; the
     "another person" questions K5 and K14 become code; K11 and K15 become code);
  2. keeps the tiny questions only for real meaning ("did the user say go ahead?", "is this a complaint?"), each
     with one meaning, a written window, defaults, defined words and a second wording for "unclear";
  3. accepts every form people really use (card "ending in" the id digits, "the card" when there is one card,
     "the original payment method"), and drops lines the policy never asks for (date of birth, country, "N paid");
  4. makes every block message name the missing detail and its expected value, and gives a way out (after 2 tiny
     blocks on one write, a transfer is allowed).
- Result in numbers (section 4): predicates using a tiny question 28 → 26; tiny question ids 16 → 12 (10 kept,
  1 merged, 5 dropped, 2 new); estimated tiny calls per conversation 11.2 → about 6 (B2-like) and 28.0 → about 9
  (B3-like). These are estimates, to be measured.

Technical names (for the build): `facts_v3_{airline,retail}.json` (the frozen 66), `questions_v3.json`,
`message_view.py`, `code_helpers.py`, `questions.py`, `guard/feedback_v3.py`. v3 files are not touched; v4 gets new
files (`facts_v4_*.json`, `questions_v4.json`, ...). Counts: script
`/tmp/claude-1000/-home-azureuser-code-projects/796f0c59-5ea8-4a72-8aa7-c0248fb5d2c9/scratchpad/v4_pt_counts.py`,
output `predicate_correctness/output/logs/v4_pt_counts.txt` and `v4_pt_usersim.txt`. Lesson ids (L1.x, L2.x) point to
`docs/planning/tracker_v3/lessons_learned.md`.

---

## 0. Shared definitions (the table refers to these)

**D1 Write, worked write.** Retail writes (7): cancel_pending_order, modify_pending_order_address,
modify_pending_order_items, modify_pending_order_payment, modify_user_address, return_delivered_order_items,
exchange_delivered_order_items. Airline writes (6): book_reservation, update_reservation_flights,
update_reservation_baggages, update_reservation_passengers, cancel_reservation, send_certificate. A worked write is one
whose output does not start with "Error". A blocked or refused call is not a worked write.

**D2 Action span S (the window for listings, L1.5).** S = every message after s and before the pending call, where s
= the newest worked write before the call that has at least one user message after it; no such write → the start of
the conversation. A write with no user message since the previous worked write is a **batch member**: it gets the
same S as that write (one listing and one yes can cover a listed batch, L1.6).

**D3 Listing anchor L.** The newest agent text message in S that names at least one key detail of the pending call
and has a user message after it (before the call). Key details: retail: the order id (with or without '#'), the
call's item ids, the product names of those items, the new address1 or zip, a payment form of D7; airline: the
reservation id, the call's flight numbers or flight dates, a passenger's first + last name, the cabin word, the new
bag total, a payment form of D7. At most 2 candidates, newest first. (v3 `listing_candidates` / `change_listings`,
limited to S.)

**D4 Go-ahead window.** Message A = L. Messages B = every user message after L up to the pending call (v3 read only
the first reply). The go-ahead holds when (a) no message of B is a strict no (D9), (b) no clash (D7, last line), and
(c) the fast path (D8) or K1v4 says yes. One K1v4 answer per (L, B) serves every confirmation fact of the call
(shared cache key; no per-fact "focus" any more).

**D5 Listing text T ("the agent messages since the last write + the user's own words for this action").**
T = every agent text message in S, plus L (also when L is older than S because of a batch), plus every user message
in S. A line passes when its value is found in any message of T. The order or reservation id also passes by D6.

**D6 Current object.** The call's order id (retail) or reservation id (airline) passes the object line when it is in
T, or when it is the newest order / reservation id named in any user or agent text before the call (so an id said
one message earlier, or before the last write, still counts when no other object was named since; B3 lost 3 tasks and
had 40 order-id blocks on this, L1.5).

**D7 Payment forms (accepted, any one; checked on the owner's methods in the DB).**
- the full id (`credit_card_3593714`); 4 or more ending digits of the id number ("ending in 3714", "3593714"); the
  card's `last_four`; a brand word next to either. A 4-digit id tail that equals another of the owner's cards'
  last_four names that other card (v3 rule RC11 m3), so for that method 5+ digits are needed.
- the kind word ("credit card", "gift card", "PayPal", "certificate", "travel certificate") when the owner has
  exactly one method of that kind;
- the brand word alone ("my Visa") when the owner has exactly one card of that brand;
- "the card", "my card", "card on file", "same card" when the owner has exactly one card (credit or gift);
- the balance / amount ("the $250 certificate", "gift card with $80") when no other method of the owner has it;
- "the original payment method", "the card I paid with", "same as the order / booking" when the call's method is
  the order's `payment_history[0].payment_method_id` (retail) or the reservation's `payment_history[0].payment_id`
  (airline).
- Negation-aware as v3 (`_methods_mentioned`: "not the Mastercard" is not a choice of it).
- **Clash:** a message of B (D4) that positively names a different method of the owner, or a brand word next to the
  call card's digits that is not the card's brand ("Visa ending 8484" for a Mastercard 8484) → the go-ahead / the
  payment line fails with a clash message naming both.

**D8 Fast path for the go-ahead (code, exact whole-message match, not a word screen; L2.7).** The newest message of
B, lower-cased, punctuation removed, the words "please", "thanks", "thank you", "ok so" removed, is exactly one of:
yes, yes yes, yeah, yep, yup, sure, ok, okay, correct, confirm, confirmed, i confirm, yes i confirm, proceed, yes
proceed, go ahead, yes go ahead, go ahead and proceed, yes do it, do it, please do, yes please do, sounds good, yes
sounds good, yes that is correct, yes thats correct, thats correct, that is correct, yes that works, that works,
yes book it, yes cancel it, yes submit it, yes go for it. → the agreement part is true with no call. Anything else
goes to K1v4.

**D9 Strict no.** v3 `is_strict_no` unchanged (starts with no / not yet / wait / don't / hold on / stop, holds no
yes-word; "no, that's all" and similar are not a no).

**D10 Unclear (L1.7).** A failed quote counts as unclear.
- Question gating a **write**: unclear → ask once more with the second wording (`<id>b`, same input) → still unclear
  → the fact's blocking value; the block message names the reason ("the answer was unclear: ...") and it is counted.
- Question gating a **transfer or a login** (K4v4, K13v4, K16v4): unclear → ask once more → **allow + log**.
- Question gating a **reply** (K12v4): unclear → ask once more → blocking value (the agent rewrites one reply).

**D11 Exit valve (L1.10).** After 2 tiny blocks on the same write (same tool + same order / reservation id; for
book_reservation the same user id), the transfer facts (airline `request_cannot_be_handled_with_available_tools`,
retail `request_cannot_be_handled_within_scope`) are true by code. Counted and shown in the harm table. A "tiny block"
= a block whose deciding fact value rests on a tiny answer or on the go-ahead / listing lines.

**D12 Quote check (L1.8).** Clean-up as v3 (`quote_form`). Split the quote at any punctuation (. , ; : ! ? … — – " '
( ) and line breaks; also "..."); every non-empty piece must be inside one named message. For K1v4 the quote may come
from any message of B.

**D13 Defaults written into every question that reads user messages (L1.11-1.13).**
- "A message that asks for nothing new (it only gives an id, a date, a choice, a thank-you or a yes) is no" (except
  where the question is about agreement, K1v4, where a yes is the point).
- Ownership: "names, emails, ids, orders and addresses count as the user's own unless the message says they belong to
  someone else."
- "Another person" = another customer or account holder (a spouse, friend, relative, colleague, anyone whose account
  or order it is). Not a public person, author, character or company, and not the user themself.

**D14 Block message format (L1.9, L2.5).** "BLOCKED by policy guardrail. Policy: "<sentence>". Not met: <fact in
words>. Missing: <the detail> (expected: <value and the forms that count>). Do: <one step the agent can do in one
turn>." Built from the rule table plus the failing line. Code facts keep v3's evidence lines (they already show the
DB values). Facts with blocking value true get the message when they are true.

**D15 Unchanged machinery.** Code parts run first; lazy evaluation (a question is asked only if a rule still needs
it); an unclear part never hides the other branch of an OR (L2.4); a new allow needs the code key and the yes
(L2.3); answers cached by sha256(question id, version, model, effort, clean input), with the conversation id saved
(L1.18, L3.10). Model gpt-6-luna, low effort, as v3.

---

## 1. The $0 counts used in the table (τ-bench v1 data, `v4_pt_counts.txt`)

| what | retail | airline |
|---|---|---|
| sizes | 500 users, 1,000 orders, 50 products, 591 items | 500 users, 2,000 reservations, 300 flights |
| payment methods | credit 239, gift 234, PayPal 222 (id numbers all 7 digits) | credit 503, gift 516, certificate 467 (all 7 digits) |
| **card id ends in its last_four** | **0 of 239** | **0 of 503** |
| users with 2+ credit cards / 2+ of one brand | 23 / **0** | 130 / **85** |
| users with exactly 1 credit card (of all card holders) | 193 of 216 | 201 of 331 |
| users with 2+ gift cards / 2+ PayPal / 2+ certificates | 0 / 0 / - | 129 / - / 117 (49 with two certificates of one amount; 1 with two gift cards of one amount) |
| a method's 4-digit id tail = another card's last_four | 1 method | 0 |
| address country | users 500/500, orders 1,000/1,000 "USA" | users 500/500 "USA" |
| address2 | "Suite N" in 500/500 users, 1,000/1,000 orders | - |
| state / zip | 2-letter 500/500; 5 digits 500/500 | - |
| orders shipped to the user's default address | 800 of 1,000 | - |
| object id forms | order `#W`+7 digits 1,000/1,000; item 10 digits 591/591 | reservation 6 upper-case letters/digits 2,000/2,000; flight `HAT`+3 digits 300/300, the 3 digits unique 300/300 |
| statuses | pending 423, delivered 373, processed 102, cancelled 102 | flight-dates: available 4,500, landed 3,982, cancelled 373 (05-01..05-14), on time 57, flying 47, delayed 41 (all on 2024-05-15) |
| several items of one product in one order | 91 orders; 7 with a duplicate item id | - |
| product-name word shared with another product of the order | 40 of 2,885 (order, product) pairs | - |
| option values ≤2 characters / used under 2+ option names | 26 / 30 (of 279); plus 23 of exactly 3 characters (e.g. "red", "USB", "XXL"), which are whole words and need no option name. Corrected 2026-10-24: this row said "≤3 characters: 49"; the code and the database check always used ≤ 2 (`output/eval_v4/form_check.md` R8) | - |
| variant pairs (same product) differing in 1/2/3/4/5 options | 1,706 / 3,244 / 2,196 / 252 / 34 | - |
| order items with no other available variant | 0 of 2,978 | - |
| pending orders not exactly one payment | 0 of 423 | - |
| (pending order, own gift card) pairs where the balance covers the total | 1 of 200 | - |
| login values | emails unique (0 duplicates); name+zip unique (0); user id contains first+last name 500/500 | - |
| reservation passengers that are the user or a saved passenger (DOB in DB) | - | 2,425 of 3,593 |
| reservations with 2+ flights on one date | - | 1,260 of 2,000 |
| bags in DB | - | total 0-8; nonfree 0 in 2,000/2,000 |
| cancelled / flown / both / delayed flight in a reservation | - | 111 / 714 / 88 / 23 |
| compensation-prohibited reservations (regular, no insurance, not business) | - | 218 of 2,000; eligible with a cancelled flight 99, with a delayed one 22 |
| created within 24 h of 2024-05-15 15:00 | - | 41 |
| cabins / insurance / trip type / membership | - | business 675, economy 676, basic 649 / yes 1,005, no 995 / one way 1,046, round trip 954 / gold 175, silver 182, regular 143 |
| airports | - | 20 codes + 20 city names from `list_all_airports` code; all 2,000 reservations use them; 614 touch JFK/LGA/EWR |
| user simulator prompt (`tau_bench/envs/user.py`) | "use your own words", no rule to type "yes" | same |

The user simulator is told to use its own words, so a literal "yes" is not guaranteed: K1v4 must accept any go-ahead.

---

## 2. THE PREDICATE TABLE

Short words: **DB** = the database copy at the check after replaying the conversation's tool calls; **event** = a
worked tool call; **args** = the pending call's arguments; **text** = code on message text; "unchanged expr" = the v3
`expr` of `facts_v3_*.json`, kept byte-equal. "n/a (code)" = no LLM, so no unclear; a missing argument or type error
takes the blocking value and is counted, as in v3. "How sure" for code rows rests on v3's code record: 0 mismatches
in 23,138 replayed calls, 0 disagreements in 14,335 DB checks (428/428 hold-out) and 69,756 event checks (KR 4.2-4.3).

### 2.1 Airline (42)

| predicate (frozen name) | domain | rules using it | v3 source | v4 source (DB / event / args / text-structure / tiny question id) | the exact code rule or the exact question text | text window read | expected user (or agent) answer in a normal good conversation | how sure (high/medium/low) and why | what happens on "unclear" | block message if false (names the missing detail and expected value) | K2-style check: can each accepted form occur in the data? checked how (give the count from v1 data) | changed vs v3? (no / how) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| airline_cancelled_flight_confirmed | airline | 25 | event AND DB | event AND DB | unchanged expr: a `looked_up('get_reservation_details','reservation_id',args['reservation_id'])`; b `any(flight_on_date(f['flight_number'],f['date'])['status']=='cancelled' for f in db('reservation',args['reservation_id'])['flights'])` | none | agent looks the reservation up before cancel_reservation | high: code record | n/a (code) | rule 25 is an OR: shown only when every branch fails: "Not met: the airline cancelled a flight of <rid>: DB shows none cancelled (<flight date status ...>). Do: look it up with get_reservation_details (if not done)." | status 'cancelled' occurs: 373 flight-dates, 111 reservations (counted) | no |
| all_booking_passengers_share_flights_and_cabin | airline | 8 | args | args | unchanged expr: `all(p.get('cabin',c)==c and p.get('flights',fl)==fl for c in [args['cabin']] for fl in [args['flights']] for p in list_arg(args['passengers']))` | none | always true for a well-formed call | high: the tool schema has one cabin and one flight list | n/a (code) | "All passengers must fly the same flights in the same cabin: passenger <name> has <x>, the call has <y>." | n/a (arguments; tool schema read) | no |
| all_pending_flight_segments_have_one_cabin | airline | 20 | args | args | unchanged expr: `all(f.get('cabin',c)==c for c in [args['cabin']] for f in list_arg(args['flights']))` | none | always true | high: one cabin argument | n/a (code) | "Cabin must be the same on all flights: flight <n> has <x>, the call has <y>." | n/a | no |
| booking_has_at_most_five_passengers | airline | 6 | args | args | unchanged expr: `len(list_arg(args['passengers'])) <= 5` | none | true | high | n/a (code) | "At most 5 passengers per reservation; the call has <n>. Deny or split as the user wants." | DB: 1-4 passengers per reservation (920/662/323/95) | no |
| booking_insurance_decision_established_and_matched | airline | 14 | text (insurance_pick) AND K1 (focus insurance) | args + text-structure + **K17v4** | `args['insurance'] in ['yes','no']` AND the first decided K17v4 answer among the candidates, newest first: (1) a user message in S holding the screen `insur/coverage/protection` after the newest such agent message's first reply (asked alone); (2) pairs (agent message in S holding the screen, the first user reply after it). Decided = `added` / `not_added`; true iff it equals `{'yes':'added','no':'not_added'}[args['insurance']]` | booking span S (D2); only messages that hold the screen word, plus each one's first reply | agent: "Would you like travel insurance for $30 per passenger?"; user: "No thanks." or "Yes." | medium: v3 lost airline/0/t1 when "Yes." was read alone; the pair input fixes that, but K17v4 is new and untested | K17v4b once; still unclear → next older candidate; none decided → false (block) | not asked: "Not established: the user's travel-insurance choice. The call says insurance = no. Ask: 'Would you like travel insurance ($30 per passenger, full refund for health or weather cancellations)?'" mismatch: "The user chose added ("<quote>") but the call says insurance = no." | both values occur (yes 1,005 / no 995 reservations); the screen word is in every insurance question by construction; the one-word reply case is in the pair | yes: K1 focus → new K17v4 on (question, reply) pairs; newest decided answer wins, not the newest pair |
| booking_payment_method_counts_within_limits | airline | 9 | args | args | unchanged expr: distinct ids, ≤1 `certificate_`, ≤1 `credit_card_`, ≤3 `gift_card_` | none | true | high: id prefix = DB source for all 1,486 methods | n/a (code) | "At most 1 certificate, 1 credit card and 3 gift cards per booking; the call has <counts>." | prefixes = source 1,486/1,486 | no |
| booking_payment_methods_found_in_user_profile | airline | 10 | DB | DB | unchanged expr: user exists and every `payment_id` is a key of `user['payment_methods']` | none | true | high: code record (tool 23/0) | n/a (code) | "Payment method <id> is not in user <uid>'s profile (methods: <list>)." | DB ids of the owner | no |
| booking_required_information_established | airline | 5 | text AND ((text AND K15) OR (text AND K1 trip)) | text-structure + shared **K1v4** (only on the listing path) | a `obtained(args['user_id'])` AND route AND trip. route: the user named origin and destination (upper-case IATA code, the city of `list_all_airports`, or the metro alias table: NYC/NY/New York → JFK, LGA, EWR; LA → LAX; SF/San Fran → SFO; Vegas → LAS; Philly → PHL; Chi-town → ORD; Twin Cities → MSP) OR (L names both airports AND the go-ahead D4 holds). trip: a phrase of `args['flight_type']` ("one way", "one-way", "oneway" / "round trip", "round-trip", "roundtrip", "return trip", "return flight") in a user message or in L, OR (L names every flight of the call (number + date) AND the go-ahead holds AND the flights fit flight_type by the flight table: round trip iff some flight leaves the destination and some arrives at the origin) | all user messages before the call; L and B (D3, D4) | user: "a one-way trip from New York to Seattle"; or agent lists the flights and the user says go ahead | medium: the alias table is hand-made; the listing path backs it up; v3's K15 was asked 14 times live, 0 blocks | code: none; K1v4 per D10 | "Not established before booking: <the trip type: ask 'one way or round trip?'> / <the origin JFK: the user has not named it; state it in your listing and get a go-ahead>." | 20 codes and 20 cities in the tool code; 2,000/2,000 reservations use them; 614 touch JFK/LGA/EWR ("New York" accepted for all three); flight_type values one_way 1,046 / round_trip 954 | yes: K15 dropped (code); K1 focus trip → shared K1v4; alias table added |
| booking_user_is_gold_member | airline | 13 | DB | DB | unchanged expr: `db('user',args['user_id'])['membership']=='gold'` | none | n/a | high | n/a (code) | (blocks with true, with rule 13): "The booking user is gold: bags must follow the gold allowance (see bag fact)." | gold 175 users | no |
| booking_user_is_regular_member | airline | 11 | DB | DB | unchanged expr: `...['membership']=='regular'` | none | n/a | high | n/a (code) | as above, regular | regular 143 | no |
| booking_user_is_silver_member | airline | 12 | DB | DB | unchanged expr: `...['membership']=='silver'` | none | n/a | high | n/a (code) | as above, silver | silver 182 | no |
| cancellation_context_established | airline | 24 | DB AND text AND text AND K7 | DB + text-structure + **K7v4** | a `db('reservation',rid) is not None`; b `obtained(owner user_id)`; c `obtained(args['reservation_id'])` (unchanged); d `ask_first_yes('K7v4', user_messages())` | all user messages before the call, newest first, first yes | user: "My plans changed." (often when asked) | high: live 10 yes / 11 no, 0 blocks; 0 judge disagreements dev/hold-out | write: K7v4b once → still unclear → false, block | "Not established: the reason for cancelling <rid>. Ask the user why they want to cancel (change of plan, the airline cancelled the flight, or another reason)." id parts: "the user id <uid> was not given by the user or shown by a lookup: ask the user for it." | any reason counts (no form); reservation ids 2,000/2,000 six characters | yes: K7 text gets the D13 default, a second wording and a named block |
| cancellation_is_within_24_hours | airline | 25 | event AND DB | event AND DB | unchanged expr: looked up AND `created_at >= 2024-05-14T15:00:00` | none | DB decides | high | n/a (code) | OR-rule message (see first row): "booked at <created_at>, more than 24 h before 2024-05-15 15:00 EST" | 41 reservations inside 24 h | no |
| cancelled_flight_certificate_response_conditions_and_amount_met | airline | 31 | text×4 AND K12-quote AND K8 | text-structure + DB + code amount + **K8v4** | a-d unchanged (obtained user, named reservation, cancelled flight, eligible); e (new code) `offer_amount_ok_v4(reply,100,counts)`: amounts = dollar amounts in the reply's sentences that hold a compensation noun (certificate, voucher, credit, compensation, gesture, goodwill); true if none, or one = 100 × passengers of a reservation of d, or = 100 with "per passenger / each / per person" within 40 characters; f `ask_first_yes('K8v4', user_messages())` | e: the pending reply; f: all user messages, newest first | user complains "my flight was cancelled and I missed my meeting"; agent offers "$200 certificate (2 passengers)" | medium-high: rare (K8 0 live blocks); amount now code | K8v4: write-like (D10): K8v4b → still unclear → false (user-only fact, counted) | "Do not offer a cancelled-flight certificate now. Missing: <the user has not complained about the cancelled flight in their own words> / <reservation <rid> is not eligible: regular member, no insurance, economy> / <the amount must be $100 × 2 passengers = $200; the reply says $150>." | cancelled-flight reservations 111, eligible 99; passengers 1-4 so amounts $100-$400 | yes: amount by code over the offer sentences (not K12's quote); K8 → merged K8v4 |
| cancelled_flight_certificate_send_conditions_met | airline | 28 | text×5 AND K8 | text-structure + DB + **K8v4** | a-e unchanged (`amount_fits(...,args['amount'],100)`); f `ask_first_yes('K8v4', user_messages())` | user messages | as above, then send_certificate with the right amount | medium-high: rare; amount is an argument | as above | "Do not send this certificate: <missing condition>. Expected amount: $100 × <n> passengers = $<x>; the call says $<y>." | as above | yes: K8 → K8v4 |
| compensation_is_prohibited_for_relevant_reservation | airline | 30, 34 | text (reads DB) | text-structure (reads DB) | unchanged expr: a any obtained / call user is 'regular'; b `prohibited_case(u)` (relevant reservations: no insurance, no business) | none (DB + obtained ids) | n/a | high: split exactly 218 / 1,782 | n/a (code) | (blocks with true): "No compensation: user <uid> is a regular member and reservation <rid> has no insurance and flies <economy> (policy S46)." | 218 of 2,000 reservations | no (the display fix L2.6 is for the Direct + facts arm only) |
| delayed_flight_certificate_response_conditions_and_amount_met | airline | 32 | text×5 AND K12-quote AND K9 AND K11 | text-structure + DB + event + code amount + **K8v4** | a-e unchanged (e = a worked update_reservation_* or cancel_reservation on the eligible delayed reservation, event log); f `offer_amount_ok_v4(reply,50,counts)`; g `ask_first_yes('K8v4', user_messages())`; **h (K11) dropped**: part e already shows the change / cancel the user wanted (policy: "after ... changing or cancelling the reservation") | reply; user messages | user: "my flight is delayed, I want to change it"; agent changes it, then offers $50 × passengers | medium-high: rare (delayed only on 2024-05-15) | K8v4 per D10 (false on still unclear) | "Do not offer a delayed-flight certificate now. Missing: <change or cancel reservation <rid> first> / <the amount must be $50 × 3 = $150>." | delayed 41 flight-dates, 23 reservations, 22 eligible | yes: K9 → K8v4; K11 dropped (event); amount code |
| delayed_flight_certificate_send_conditions_met | airline | 28 | text×6 AND K9 AND K11 | text-structure + DB + event + **K8v4** | a-f unchanged (`amount_fits(...,50)`); g K8v4; h dropped (event e) | user messages | as above | medium-high | as above | as above, send version | as above | yes: K9 → K8v4; K11 dropped |
| gold_member_booking_baggage_counts_correct | airline | 13 | args | args | unchanged expr: `bags_right(total, nonfree, cabin, passengers, [[basic_economy,2],[economy,3],[business,3]])` | none | true | high | n/a (code) | "Bags do not fit the gold allowance: <n> passengers × <3> free (<economy>) = <f> free; total <t> → nonfree must be <max(0,t-f)>, the call says <x>." | allowances from policy S18; DB totals 0-8 | no |
| insured_cancellation_condition_met | airline | 25 | text (screen) AND K6 | text-structure (screen) + **K6v4** | a screen `health` unchanged (0 blind misses); b `ask_first_yes('K6v4', screened_user_messages('health'))` | user messages that hit the screen, newest first | insured economy cancel: "I broke my leg and can't travel" | medium: few live cases (3 asks), task-specific | write: K6v4b → still unclear → false, block | "Reservation <rid> (economy, insured, booked > 24 h ago, no airline cancellation) can be cancelled only for a covered reason: health or weather. Ask the user for the reason; do not suggest one." | screen blind-tested on 2 sets; insured reservations 1,005 | yes: text defines "health" / "weather", D13 default, second wording, named block |
| modification_user_and_reservation_ids_established | airline | 15, 16, 17 | DB AND text AND text | DB + text-structure | unchanged expr: reservation exists AND `obtained(owner)` AND `obtained(rid)` | user messages + worked tool outputs | user gives the user id and the reservation id | high: dev 329/329 true | n/a (code) | "Not established: the user id <uid> (owner of <rid>): ask the user for it." / "...the reservation id: ask for it." | ids: 2,000/2,000 six characters | no |
| origin_destination_and_trip_type_preserved | airline | 19 | event AND DB | event AND DB | unchanged expr (route test of the new flight numbers vs origin, destination, flight_type) | none | true for a correct change | high: 1 type error dev | n/a (code) | "The new flights change the trip: reservation <rid> is <round trip JFK-SEA>; the new flights <...> do not leave JFK / return to JFK." | 35 one-way reservations with origin = destination (the expr handles them) | no |
| passenger_identity_details_established | airline | 7 | text OR DB | text OR DB | unchanged expr: a user typed first, last, dob; b (first, last, dob) is the user or a saved passenger | user messages (a) | the DB path does the work (dev 26/26) | high | n/a (code) | "Not established: <first last>'s date of birth (not typed by the user, not in the profile). Ask the user for it." | 2,425 of 3,593 passengers are in the DB; dob ISO 500/500; 6 date forms in text | no |
| pending_baggage_total_not_reduced | airline | 21 | DB | DB | unchanged expr: `args['total_baggages'] >= reservation['total_baggages']` | none | true | high: 43/43 dev | n/a (code) | "Bags can be added, not removed: <rid> has <3>, the call says <2>. Deny the removal." | DB totals 0-8 | no |
| pending_database_change_details_listed_and_explicitly_confirmed | airline | 1, 2, 3, 4 | text AND text AND K2 AND K1 | text-structure (lines, code) + **K17v4** (insurance line, booking only) + **K1v4** | a: L exists (D3); b: no strict no in B (D9); c: every line of the call found in T (D5): **book**: each flight number ("HAT170", "HAT 170", "flight 170") + its date (any form, year optional); the cabin word; each passenger first + last name; each payment method (D7), with its amount only if 2+ methods; the total bags when > 0; insurance: a K17v4 answer on an agent message in S that holds the insurance screen (with its first reply) equals the call's value. **update_reservation_flights**: the reservation (D6); each changed flight (number + date); the cabin only if it differs from `cabin_now`; the payment method (D7). **update_reservation_baggages**: the reservation (D6); the new total or the number added (total − DB total); the payment method only if the charge 50 × max(0, nonfree − DB nonfree) > 0. **update_reservation_passengers**: the reservation (D6); each changed passenger's first + last name, plus the new date of birth only when the DOB is the changed field. Dropped: booking DOBs, "M paid", unchanged flights / cabin / passengers. d: go-ahead D4 (fast path D8, else K1v4) and no clash (D7) | T (D5) for c; A = L, B = user messages after L for d | agent: "Booking: HAT170 May 22, HAT022 May 26, economy, Ana Ruiz and Leo Ruiz, 2 checked bags, no insurance, Visa ending 7447. Shall I book?" user: "Yes, book it." | **medium**: the lines are now code over DB-derived forms, but they never ran on real agent text; v3 K2 airline blocks: book 16, bags 8, flights 4, passengers 4; 5 lost B2 conversations (DOB, "paid") | lines: no unclear (code); K17v4 per its row; K1v4 per D10 (K1v4b → false) | lines (all missing ones at once): "Not in your listing since the last change: the flight HAT022 on 2024-05-26; the card (the call uses credit_card_4421486, Visa, last four 7447; 'ending in 1486' also counts). List them and ask for a yes." go-ahead: "After your listing ("<first 80 chars>"), the user has not said to go ahead (last reply: "<...>"). Ask: 'Shall I go ahead with <book flights HAT170, HAT022>? Please reply yes or no.'" clash: "The user named <Mastercard ending 3714> but the call uses <credit_card_4421486 (Visa 7447)>. Ask which one." | flights HAT+3 digits 300/300, 3-digit tails unique 300/300; 1,260/2,000 reservations have 2+ flights on one date (so number + date per flight); card id never ends in last_four (0/503): both forms accepted; 85 users with 2+ cards of one brand and 130 with 2+ credit cards (brand / "card" alone only for single ones; 201 of 331 holders have one); 129 users 2+ gift cards, 117 2+ certificates, 49 two certificates of one amount; DB nonfree 0 in 2,000/2,000; DOB in DB for 2,425/3,593 passengers | yes: K2 → code lines over the span (not one message); DOB / "paid" / unchanged values dropped; card id digits accepted; K1 → K1v4 (any words, batch, all replies); block names each line |
| pending_flight_segments_are_unchanged | airline | 18 | event AND DB | event AND DB | unchanged expr: looked up AND call flights = DB flights as a multiset | none | n/a | high: 230/271 true dev | n/a (code) | "Basic economy flights cannot be changed: <rid> is basic economy and the call changes <HAT001 05-20 → HAT003 05-21>. Only the cabin may change." | basic economy 649 reservations | no |
| pending_flight_update_changes_flights | airline | 23 | DB | DB | unchanged expr: NOT the multiset test | none | n/a | high | n/a (code) | (blocks with true, with rule 23): see the payment fact | n/a | no |
| pending_flight_update_is_basic_economy | airline | 18 | DB (+event) | DB + event | unchanged expr: `cabin_now(rid)=='basic_economy'` (newest worked update's cabin, else DB; v1 tool never writes cabin) | none | n/a | high | n/a (code) | (blocks with true, with rule 18): as two rows up | basic economy 649 | no |
| pending_passenger_count_unchanged | airline | 22 | DB | DB | unchanged expr: `len(args['passengers']) == len(reservation['passengers'])` | none | true | high: tool 15/0 | n/a (code) | "The number of passengers cannot change: <rid> has 2, the call has 3. Deny; even a human agent cannot do it." | 1-4 passengers | no |
| pending_response_offers_any_compensation_certificate | airline | 33, 34 | text (screen) AND K12 | text-structure (screen) + **K12v4** | a `screen_reply('offer')` unchanged; b `ask('K12v4', args['content'])` | the pending reply | no offer → no | high: live 2 yes of 271, 0 lost | reply: K12v4b → still unclear → true (blocking), the agent rewrites the reply | (true): "Your reply offers compensation ("<quote>"). Not allowed now: <the user has not asked for it / user <uid> is regular, no insurance, economy>. Remove the offer." | screen blind-tested; no DB form | yes: K12 text (refund / price difference / fees are not compensation), second wording |
| pending_response_offers_cancelled_flight_certificate | airline | 31 | text AND K12 AND kind (quote words, else K8/K9) | text-structure + **K12v4** + DB kind | a, b as above; c (new order): kind = 'cancelled' if a named reservation of an obtained user had a cancelled flight and none had a delayed one (DB `had_flight_status`); 'delayed' the other way; both or neither → K12v4 quote words (cancel / delay); still undecided → true (blocking) | reply + DB | no offer | high | as above | (true): "Your reply offers a certificate for the cancelled flight of <rid>. Missing: <condition>; the amount must be $100 × <n> = $<x>." | 111 reservations with a cancelled flight, 23 with a delayed one | yes: kind from the DB first (not K8/K9) |
| pending_response_offers_delayed_flight_certificate | airline | 32 | text AND K12 AND kind | text-structure + **K12v4** + DB kind | as above with 'delayed' | reply + DB | no offer | high | as above | (true): "... delayed flight of <rid>: change or cancel the reservation first; amount $50 × <n>." | as above | yes: as above |
| regular_member_booking_baggage_counts_correct | airline | 11 | args | args | unchanged expr: allowance [[basic_economy,0],[economy,1],[business,2]] | none | true | high | n/a (code) | as the gold row, regular allowance | policy S16 | no |
| request_cannot_be_handled_with_available_tools | airline | 27 | K13 OR (text AND K16) | **K13v4** OR (text-structure AND (event OR **K16v4**)) OR code exit valve | a `ask_first_yes('K13v4', user_messages())` (unclear → allow + log); b unchanged (a named reservation of an obtained user has a 'flying' / 'landed' flight now); c (new code first) a cancel_reservation call on a reservation of b earlier in the conversation (any outcome, also guard-blocked), else `ask_first_yes('K16v4', user_messages())`; e (new) exit valve D11. Combine: a OR (b AND c) OR e | all user messages, newest first | transfers are rare: a request no tool can do, or a flown trip to cancel | medium: K13 had 90 live blocks, 45 of them dead ends after a wrong K1/K2 block; 1 lost (airline/36, a known conflict with the policy's refused list; recorded, not tuned) | K13v4 / K16v4: ask again → allow + log | "Do not transfer yet: the user's request ("<newest request>") can be done with <tool>. Do it, or deny it if the policy forbids it." | flown reservations 714 (88 also cancelled); refused list cites S29, S30, S31-S32 | yes: unclear → allow; exit valve; code cancel-attempt path before K16; second wordings |
| reservation_has_basic_or_economy_cabin | airline | 25 | event AND DB | event AND DB | unchanged expr: looked up AND `cabin_now in [basic_economy, economy]` | none | n/a | high | n/a (code) | OR-rule message (rule 25) | 1,325 reservations | no |
| reservation_has_business_cabin | airline | 25 | event AND DB | event AND DB | unchanged expr: looked up AND `cabin_now=='business'` | none | n/a | high | n/a (code) | OR-rule message | 675 | no |
| reservation_has_no_used_flight_segments | airline | 26 | DB | DB | unchanged expr: every flight status in [available, on time, delayed, cancelled] | none | n/a | high | n/a (code) | "Reservation <rid> has a flown segment (<HAT001 05-14 landed>): it cannot be cancelled; transfer the user (policy)." | flown 714 | no |
| reservation_has_travel_insurance | airline | 25 | event AND DB | event AND DB | unchanged expr: looked up AND `insurance=='yes'` | none | n/a | high | n/a (code) | OR-rule message | yes 1,005 | no |
| silver_member_booking_baggage_counts_correct | airline | 12 | args | args | unchanged expr: allowance [[basic_economy,1],[economy,2],[business,3]] | none | true | high | n/a (code) | as the gold row, silver allowance | policy S17 | no |
| user_complained_about_relevant_flight_situation | airline | 29, 33 | text AND (K8 OR K9) | text-structure + **K8v4** | a `len(user_messages()) > 0`; b `ask_first_yes('K8v4', user_messages())` | all user messages, newest first | compensation task: "my flight was delayed 5 hours, this is unacceptable" → yes | medium-high: K8/K9 0 live blocks; the merged text is new | K8v4b → still unclear → false (user-only) | "The user has not complained about a delayed or cancelled flight in their own words. Do not offer or send compensation unless they do; do not lead them." | delayed 23 / cancelled 111 reservations in DB | yes: K8 + K9 merged into K8v4 |
| user_explicitly_requested_compensation | airline | 29, 33 | text (screen) AND K10 | text-structure (screen) + **K10v4** | a screen `compensation_request` unchanged; b `ask_first_yes('K10v4', screened_user_messages('compensation_request'))` | user messages that hit the screen | compensation task: "I'd like some compensation for this" | high: 2 live asks, 2 yes, 0 problems | K10v4b → still unclear → false | "The user has not asked for compensation. Policy: do not offer it unless the user explicitly asks." | screen blind-tested | yes: D13 default and second wording only |
| user_selected_eligible_flight_change_payment_method | airline | 23 | DB AND (text OR (text AND K1)) | DB + text-structure + shared **K1v4** | a unchanged (owner's method, source gift_card or credit_card); b `payment_named_exactly` with the D7 forms (the user's latest payment message names exactly it); c: L or a message of B names it (D7) and no clash; d: go-ahead D4 (shared answer). Combine a AND (b OR (c AND d)) | user messages (b); L and B (c, d) | user: "use the gift card ending 0333" / agent "I'll charge your Visa ending 7447, OK?" "Yes." | medium: p7 had 7 added blocks (2 tool-accepted); D7 adds the real forms | K1v4 per D10 | "Not established: the user's choice of payment for the flight change. The call uses <gift_card_8190333 ($280)>. Ask: 'Which gift card or credit card should I use for the difference?'" clash: as D7 | as the listing row (card forms 0/503, 85 same-brand users, 129 / 117 multi gift / certificate users) | yes: D7 forms; shared K1v4 instead of K1 focus payment |

### 2.2 Retail (24)

| predicate (frozen name) | domain | rules using it | v3 source | v4 source (DB / event / args / text-structure / tiny question id) | the exact code rule or the exact question text | text window read | expected user (or agent) answer in a normal good conversation | how sure (high/medium/low) and why | what happens on "unclear" | block message if false (names the missing detail and expected value) | K2-style check: can each accepted form occur in the data? checked how (give the count from v1 data) | changed vs v3? (no / how) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| agent_reminded_user_to_include_all_items_for_exchange | retail | 61 | text AND K3 | text-structure + **K3v4** | a `len(reminder_candidates(args['order_id'])) > 0` unchanged; b `ask_first_yes('K3v4', reminder_candidates(args['order_id']), items='exchanged')` | agent text messages at or after the first message holding the order id, each followed by a user message, newest first; one reminder covers later changes of the same order (Q7) | agent: "Are these all the items you want to exchange?" | medium-high: 16 of 18 read answers right; agents often forget (live 182 yes / 267 no) but fix it in one turn (52 of 55 blocked calls ran later) | write: K3v4b → still unclear → false, block | "Before this exchange, ask the user: 'Are <the boots and the lamp> all the items you want to exchange in order #W1234567? An exchange can be done only once.'" | no DB form (agent phrasing); order ids #W+7 digits 1,000/1,000, so the window start is always found | yes: text names the accepted forms and the hard no; second wording; exact sentence in the block |
| agent_reminded_user_to_include_all_items_for_modification | retail | 53 | text AND K3 | text-structure + **K3v4** | as above, `items='modified'` | as above | "Is the T-Shirt the only item you want to change?" | medium-high, as above | as above | "Before this change, ask the user: 'Are these all the items you want to modify in order <oid>? This can be done only once.'" | as above | yes: as above |
| cancellation_reason_is_allowed | retail | 45 | args | args | unchanged expr: `args['reason'] in ['no longer needed','ordered by mistake']` | none | true | high: tool agrees 878/0 | n/a (code) | "The reason must be exactly 'no longer needed' or 'ordered by mistake'; the call says '<x>'. Ask the user which one applies." | tool enum = these 2 strings | no |
| consequential_action_details_listed | retail | 30, 32, 34, 36, 38, 40, 42 | text AND K2 | text-structure (lines, code) + **K18v4** (cancel reason only, when the exact phrase is absent) | a: L exists (D3); b: every line of the call found in T (D5). Lines: **object** (all order tools): the order (D6). **cancel**: the reason: the exact phrase ("no longer need(ed)", "ordered (it) by mistake", case-insensitive) in T, else K18v4 yes on a message of T. **modify address / modify_user_address**: each field of the new address that differs from the current one (the order's address / the user's default address): address1, address2 ("Suite N", "Ste N", "#N", "Unit N", "Apt N", or N right after address1), city, state (2-letter code or full name), zip (5 digits); country dropped; or "your default address / the address on your profile" when the call's address equals the user's default address in the DB. **modify payment**: the new method (D7). **modify items / exchange**: each old item (product name, a word of it that names no other product of the order, or the item id; when the order has 2+ items of that product and the call does not take all of them: the item id or an option value only that item has) and each new item (new item id, or every changed option's new value as a whole token; a value of ≤2 characters (corrected 2026-10-24 from "≤3": 3-character values such as "red" or "USB" are whole words), number-only, "yes" / "no" / "none", or used by 2+ option names of the product needs its option name within 3 words, e.g. "size 8"); the payment method for the difference (D7). **return**: each returned item (as old items), or "all the items / the whole order" when the call returns every item; the refund method (D7). Clash (log only, not a block in v4): a value of a changed option that is neither the old nor the new value of that item | T (D5) | agent: "To confirm: return the Hiking Boots and the Desk Lamp from order #W1234567, refund to your Visa ending 7447. Shall I proceed?" | **medium**: v3 K2 caused most losses (206 live blocks; 11 of 17 B3 losses; 9 lost B2 conversations); now code over DB-derived forms, but never run on real agent text | code: none; K18v4 per its row (K18v4b → line missing) | per missing line, all at once: "Not in your listing since the last change: the refund method (the call uses credit_card_3593714: Mastercard, last four 3705; 'ending in 3714' also counts)." / "the zip of the new address: 77034" / "the new item for the Water Bottle: capacity 1000ml → 750ml (or item 1234567890)". List them and ask for a yes. | order ids 1,000/1,000; item ids 591/591; country "USA" 500/500 users and 1,000/1,000 orders (line dropped); address2 "Suite N" 500/500 and 1,000/1,000; states 2 letters 500/500; zips 5 digits 500/500; 800/1,000 orders use the default address; card id ends in last_four 0/239; 0 users with 2+ cards of one brand (brand alone names a card), 23 with 2+ credit cards, 0 with 2+ gift cards or PayPal; 1 method needs 5+ digits; 91 orders with 2+ items of one product, 7 with a duplicate item id; 40 of 2,885 (order, product) pairs share a name word; 26 short (≤2 characters) and 30 shared option values; variant pairs differ in 1 option 1,706 / 2: 3,244 / 3: 2,196 / 4: 252 / 5: 34 | yes: K2 → code; window = span + user words; country dropped; id digits, "original", "default address", "all items" forms; per-line block message |
| email_identity_provided_by_user | retail | 1 | text | text-structure | unchanged expr: `user_typed(args['email'])` | all user messages | user types the email | high: p7 0 logins to another user | n/a (code) | "The email <x> was not given by the user. Ask the user for their email (or name and zip)." | emails unique: 0 duplicates in 500 | no |
| gift_card_balance_covers_order_total | retail | 52 | DB | DB | unchanged expr: own gift card AND `balance >= payment_history[0].amount` | none | true when used | high: v3 0 disagree | n/a (code) | "Gift card <id> has $<b>; the order total is $<t>. It cannot pay this order. Ask for another method." | 1 of 200 (pending order, own gift card) pairs covers | no |
| gift_card_balance_covers_price_difference | retail | 56, 64 | DB | DB | unchanged expr: own gift card AND (balance >= diff OR diff <= 0), diff as each tool sums it | none | true when used | high: v3 0 disagree | n/a (code) | "Gift card <id> has $<b>; the price difference is $<d>. Ask for another method." | balances 0-100 (median 57) | no |
| item_replacements_are_available_same_product_different_option | retail | 54, 62 | DB | DB | unchanged expr: same length, old items in the order, each new id an available variant of the old item's product and different | none | true | high | n/a (code) | "New item <id> is not an available variant of <product> (or equals the old item <id>). Available options: <...>." | 379 of 591 variants available; 0 products with two variants of the same options; 0 of 2,978 order items lack an alternative | no |
| name_and_zip_identity_provided_by_user | retail | 2 | text | text-structure | unchanged expr: `user_typed` first name, last name, zip | all user messages | user types name and zip | high | n/a (code) | "Not given by the user: <the zip 76192>. Ask the user for it." | name+zip unique (0 duplicates); user ids contain first+last 500/500 (a name inside a typed user id counts) | no |
| order_status_checked_delivered | retail | 57, 60 | event AND DB | event AND DB | unchanged expr: looked up AND `status=='delivered'` | none | agent looks the order up first | high | n/a (code) | "Look up order <oid> with get_order_details first." / "Order <oid> is <processed>, not delivered: it cannot be returned or exchanged." | delivered 373 | no |
| order_status_checked_pending | retail | 44, 47, 48, 49 | event AND DB | event AND DB | unchanged expr: looked up AND `status=='pending'` | none | as above | high | n/a (code) | as above, "not pending" | pending 423 | no |
| payment_method_differs_from_original | retail | 51 | DB | DB | unchanged expr: `args['payment_method_id'] != payment_history[0].payment_method_id` | none | true | high | n/a (code) | "The new method <id> is the order's current method. Ask the user for a different one." | 0 of 423 pending orders with more than one payment | no |
| payment_method_is_gift_card | retail | 52, 56, 64 | args | args | unchanged expr: `'gift_card' in args['payment_method_id']` | none | n/a | high: prefix = source 695/695 | n/a (code) | (blocks with true, with the balance facts): see them | 695/695 | no |
| request_cannot_be_handled_within_scope | retail | 29 | text AND K13 | text-structure + **K13v4** + code exit valve + code "user not found" | a `len(user_messages()) > 0` (all user messages; v3 newest 2); b `ask_first_yes('K13v4', user_messages())` (unclear → allow + log); c exit valve D11; d (new code) 2+ find_user_id_by_* calls, all failed, and none worked (the user cannot be found, so nothing is in scope). Combine (a AND b) OR c OR d | all user messages, newest first | rare transfers: a request no tool can do | medium: K13 live blocks mostly dead ends after wrong writes; wrong yeses on "escalate" while in scope | ask again → allow + log | "Do not transfer yet: the user's request ("<newest request>") can be done with <tool>. Do it, or deny it if the policy forbids it." | no DB form; v1 `retail/tools/` has 16 tool files, and v3's tools text omits the two find-user tools (v4 adds them; the full text diff is a build step) | yes: window all user messages; unclear → allow; exit valve; user-not-found code; second wording |
| request_is_for_another_user | retail | 15-27 | DB OR (text AND K4) | DB OR (text-structure AND **K4v4**) | a unchanged (the call's object belongs to a user other than `me`, DB); b `another_user_pick()` unchanged (first login: always; catalog reads: only on the `other_person` screen); c `ask_first_yes('K4v4', another_user_pick())` | one user message (the one with the login values, or the latest for catalog reads) | "I'm Lei Anderson, zip 76192" → no | high: 0 yes in 302 live asks, 0 blocks | login / catalog read: ask again → **allow + log** (later writes are still checked by the DB owner, part a) | (true): "The user asks about another person's account ("<quote>"). Policy: help only the user you are talking to; deny this request." | DB part: owners for 1,000/1,000 orders; logins: unique emails and name+zip | yes: unclear → allow + log; "another person" defined (D13) |
| response_performs_task_for_another_user | retail | 28 | text OR (text AND K5) | text-structure only | `reply_holds_other_user_data()` (part a, unchanged); parts b (always-true screen) and c (K5) removed | the pending reply + DB | false | high: K5 had 11 live yeses, all wrong (poets, the user's own name), 1 lost; the real harm (another user's DB data in a reply) is part a | n/a (code) | (true): "Your reply holds data of another user (<kind>), not of the logged-in user <me>. Remove it: you can help only this user." | DB values of all 500 users (info classes) | yes: K5 dropped |
| return_refund_method_is_original_or_existing_gift_card | retail | 59 | DB | DB | unchanged expr: in the owner's profile AND (original OR 'gift_card' in id) | none | true | high | n/a (code) | "The refund must go to the original method (<id>) or an existing gift card; <id> is neither." | originals in profile 1,000/1,000; original kinds gift 337, credit 304, PayPal 359 | no |
| user_authenticated | retail | 3-14 | event | event | unchanged expr: a worked find_user_id_by_email / _by_name_zip | none | agent finds the user first | high: 38,011/38,011 | n/a (code) | "Find the user first: find_user_id_by_email (email) or find_user_id_by_name_zip (first name, last name, zip) with details the user gives." | n/a | no |
| user_chose_pending_payment_method | retail | 50 | DB AND (text OR (text AND K1)) | DB + text-structure + shared **K1v4** | d unchanged (method in the order owner's profile); a `payment_named_exactly` with the D7 forms; b: L or a message of B names it (D7) and no clash; c: go-ahead D4 (shared). Combine d AND (a OR (b AND c)) | user messages (a); L and B (b, c) | user: "switch it to my PayPal" | medium: p7 2 added blocks; D7 adds real forms | K1v4 per D10 | "Not established: the user's choice of the new payment method. The call uses <paypal_5727330>. Ask: 'Which payment method should the order use?'" clash: as D7 | retail D7 counts (0/239, 0 same-brand, 0 multi gift / PayPal, 1 tail clash) | yes: D7 forms; shared K1v4 |
| user_chose_price_difference_payment_method | retail | 55, 63 | DB AND (text OR (text AND K1)) | DB + text-structure + shared **K1v4** | as above, for modify items / exchange | as above | user: "charge the difference to the original card" | **medium-low**: p7 structure alone added 44 blocks (33 tool-accepted, 29 expected actions); the "original payment method" and "the card" forms (D7) and the span should remove most | K1v4 per D10 | "Not established: the method for the price difference ($<d>). The call uses <credit_card_...> (<Visa 7447>; 'the original payment method' also counts if the user says it). Ask: 'Which method should pay or receive the difference?'" | as above; original method still in the profile 1,000/1,000 | yes: D7 forms incl. "original"; shared K1v4 |
| user_confirmed_cancellation_order_and_reason | retail | 46 | text AND K1 | text-structure + **K18v4** (fallback) + **K1v4** | order: D6; reason: the exact phrase in T or in any user message before the call, else K18v4 yes on a message of T; go-ahead D4 | T; L and B | user: "Yes, cancel it, I don't need it anymore." | medium-high: p7 4 added blocks (expected); 3 K2 too-strict cases where the user, not the agent, said the reason (now counted) | K18v4 / K1v4 per D10 | "Not confirmed: <the reason: the call says 'no longer needed'; the user has not given or confirmed it> / <the go-ahead>. Ask: 'Shall I cancel order <oid> because it is no longer needed? Please reply yes or no.'" | 2 reason strings (tool enum); order id forms 1,000/1,000 | yes: reason by code or K18v4 (not one K1 over the whole action); window; shared K1v4 |
| user_confirmed_return_order_items_and_method | retail | 58 | text AND K1 | text-structure (lines) + **K1v4** | order D6; each returned item and the refund method found in T (the same lines as the return listing) or the method named by the user's latest payment message (D7); go-ahead D4 | T; L and B | user: "Yes, refund it to the credit card ending 5124." | medium: v3 K1 said no when the card was named by id digits (B3 222, 255, 345); D7 accepts them | K1v4 per D10 | "Not confirmed: the refund method for the return of <items> (the call uses <credit_card_1565124: Mastercard 2732; 'ending 5124' also counts>)." / go-ahead as D4 | as the listing row | yes: details by code; K1v4 only reads agreement |
| user_explicitly_confirmed_pending_action | retail | 31, 33, 35, 37, 39, 41, 43 | text AND K1 | text-structure + **K1v4** | L exists (D3); no strict no in B (D9); no clash (D7); fast path D8 or K1v4 yes | A = L; B = user messages after L | user: "Yes." / "Please go ahead with both." / "Sounds right, submit the return." | **medium**: K1 lost 4 tasks (one yes for two orders, retail/92 ×3; "Yes." insurance); the batch + any-words text and all replies fix these; the user simulator has no rule to type "yes" | K1v4b → still unclear → false, block (counted) | "Not confirmed: after your listing ("<first 80 chars>"), the user has not said to go ahead (last reply: "<...>"). Ask: 'Shall I go ahead with <return 2 items of #W1234567>? Please reply yes or no.'" | user simulator prompt: "use your own words" (no "yes" rule), so every go-ahead form is a test case | yes: K1 → K1v4 (one meaning: agreement; batch; all replies; fast path) |
| user_specific_information_disclosed | retail | 3 | text OR (text AND K14) | text-structure only | `reply_discloses_user_data()` (part a, unchanged); b and c (K14) removed | the pending reply + worked tool outputs | false | high: K14 was asked 0 times live; after login rule 3 holds by `user_authenticated` | n/a (code) | (true): "Your reply shows user data (<kind>) before the user is identified. Identify the user first." | n/a | yes: K14 dropped |

### 2.3 Plans for every medium / low row (remove or soften)

| row | plan |
|---|---|
| consequential_action_details_listed; pending_database_change_details_listed_and_explicitly_confirmed | (1) $0: 30 yes / 30 hard-no made-up listings per write tool (each line form, D6 one-message-earlier, a batch listing, default address, "all items", card by id digits) before any paid call. (2) $0: run the line code over the v3 dev conversations (the 3,403 dev ones, not B2/B3/hold-out) and count blocks per line; strictness mark pre-registered (tiny + line blocks ≤ 1.5 × the reference). (3) Soften if a line is too strict: a line that fails on dev only because of a form gets the form added (counted in data first, L1.2), never a single-example fix. (4) The exit valve D11 caps the damage. |
| user_explicitly_confirmed_pending_action and the other K1v4 users | made-up set (section 3, K1v4); fast path removes the bare-"yes" calls; if K1v4's dev "no" share on replies that the reference calls agreement is above 5 %, add the failing wording class (not the example) to the text. |
| user_chose_price_difference_payment_method | count on dev how many of v3's 44 structure blocks the D7 forms clear ($0 replay of the code part only); if > 5 remain, add path: "the confirmed listing names the method (D7) and the user did not name another" without a separate payment sentence from the user. |
| booking_insurance_decision_established_and_matched | K17v4 made-up set incl. one-word replies; if it is too strict on dev, fall back to: the confirmed listing states the insurance value (K17v4 on L) and the go-ahead holds. |
| booking_required_information_established | count on dev the bookings where only the listing path passes; extend the alias table only from airport-name forms counted there. |
| request_cannot_be_handled_* | unclear → allow already; the exit valve and user-not-found code remove the dead ends; the refused list stays policy-only (airline/36 conflict recorded, not tuned). |
| insured_cancellation_condition_met | K6v4 made-up set; health screen kept (blind-tested). |
| agent_reminded_* (medium-high) | block message gives the exact sentence, so the cost is one turn; made-up set for the forms "only item", "any other items", "all the items". |

---

## 3. The kept tiny questions (v4)

Common to all: system prompt as v3, with one added line: "If the question names a default or defines a word, use
it." Answer JSON `{"answer": "yes|no|unclear", "quote": "..."}` (K17v4: `added|not_added|not_said|unclear`). Quote
check D12. Unclear D10. Each question has a second wording `<id>b` used only on an unclear answer. All examples below
are **made up from the policy text**; none is copied from a conversation, and none uses a real id from the data.

### K1v4: the user tells the agent to go ahead (replaces K1 v1)
- **Used by:** retail user_explicitly_confirmed_pending_action, user_confirmed_cancellation_order_and_reason,
  user_confirmed_return_order_items_and_method, user_chose_pending_payment_method,
  user_chose_price_difference_payment_method; airline pending_database_change_details_listed_and_explicitly_confirmed,
  booking_required_information_established (listing path), user_selected_eligible_flight_change_payment_method. One
  answer per (L, B) serves all of them.
- **Text:** "Message A is the agent's message. It may propose one action or a list of actions. Messages B are the
  user's messages after it, oldest first. Do the user's messages B tell the agent to go ahead with what message A
  proposes (all of it, or at least this action: {action})? Yes: a clear go-ahead in any words, for example yes,
  confirm, go ahead, proceed, please do it, submit it, I authorize it, that's right please continue, or the user
  restating the action as an instruction. One go-ahead for a whole list of actions counts for each action in the
  list. No: a question, a maybe, 'wait' or 'not yet', a request to change a detail, a choice of a different option,
  or a go-ahead taken back in a later message B. A message B that neither agrees nor asks for a change (only thanks,
  or only an id) does not count as a go-ahead."
- **Second wording K1v4b:** "Message A is the agent's proposal; messages B are the user's answers. Has the user
  agreed that the agent should now carry out {action}? Answer yes if the user agreed in any words, also when the
  user agreed to a list of actions that includes it. Answer no if the user asked something, hesitated, changed a
  detail, chose something else, or took the agreement back."
- **{action}:** one short line: tool phrase + object id (+ item names for retail item tools, flight numbers for
  airline). No other details (details are code).
- **Window:** A = L (D3); B = every user message after L up to the call (D4). Quote from any message of B.
- **Accepted answers:** yes / no / unclear. Code before it: strict no (D9) → false without a call; clash (D7) →
  false without a call; fast path (D8) → true without a call.
- **Defaults:** batch: one go-ahead covers each listed action. No default to "yes" on silence.
- **Few-shot: yes (1 + 1).** Why: the live failures were exactly a batch go-ahead without "yes" and a clear
  go-ahead in other words; one example of each kind of decision teaches both, and costs about +100 tokens on about
  half the old K1 calls.
  - yes: A: "I can cancel the pending order with the electric kettle and also change the shipping address of your
    other order to 12 Elm Street. Shall I do both?" B: "That all sounds right, please take care of both." → yes,
    quote "please take care of both".
  - no: A: "I will exchange the fleece jacket for size L and charge the price difference to your gift card. Do you
    want me to go ahead?" B: "Could you put the difference on my credit card instead?" → no.
- **Test-case spec (30 yes / 30 hard no, separate agent, from the policy):** yes: bare yes words (5, though the
  fast path takes most), go-ahead without a yes word (5), batch go-ahead over 2-4 listed actions in 1-2 objects (5),
  yes + an unrelated remark (3), restated instruction ("Cancel it for that reason.") (3), the go-ahead in the 2nd or
  3rd message of B after a short agent aside (4: the window edge), yes to a list where {action} is the 3rd item (3),
  "I authorize it" style (2). Hard no: a question about the price / refund timing (5), "wait" / "let me check" (4),
  a changed detail (card, size, address) (6), a different choice from the listed options (4), a go-ahead then taken
  back in a later B message (4), a yes to a different listed action only ("only the first one") (4), thanks only (3).
  Pass mark: ≥ 29/30 on each side, 0 unclear on the yes side.

### K3v4: the agent reminded the user to give all items (replaces K3 v1)
- **Used by:** agent_reminded_user_to_include_all_items_for_exchange (items = exchanged, verb = exchange),
  ..._for_modification (modified / modify).
- **Text:** "Does message A ask the user to check that the list of items to be {items_action} is complete? Yes, for
  example: 'Are these all the items you want to {verb}?', 'Is this the only item?', 'Any other items you want to
  {verb}?', 'Please make sure you have listed every item, since this can be done only once.' An invitation to name
  more items or more changes for this order counts too, also when it is said as a statement (for example next to a
  warning that this can be done only once). No: asking only to confirm the change itself ('Shall I proceed?', 'Please
  confirm you want to {verb} both items'), checking which item the user means or that an item is the correct one (that
  checks one item, not that none is missing), asking which options the user wants, or a general 'anything else I can
  help with?' about other help."
- **Second wording K3v4b:** "Message A is from the agent. Before acting, does it ask the user whether there are more
  items to {verb} (or whether the listed items are all of them)? A request to confirm the action, or a question about
  options, is no."
- **Window:** as v3: agent text messages at or after the first message holding the order id, each followed by a
  user message before the call; newest first; first yes wins; one reminder covers later changes of the same order.
- **Accepted answers:** yes / no / unclear. Default: none needed (agent message).
- **Few-shot: yes (1 + 1).** Why: the live misses were the "only item" forms and the one wrong yes was "confirm you
  want to exchange both items"; an example of each pins the boundary.
  - yes: "Got it, the desk lamp in white. Is the desk lamp the only item you'd like to change in this order?" → yes.
  - no: "Please confirm you want me to exchange both the backpack and the water bottle." → no.
- **Test-case spec:** yes: "only item" (5), "any other items" (5), "all the items" (5), "complete list / every item"
  (5), the reminder inside a long listing (5), reminder phrased as a statement + question ("This can only be done
  once, so let me know if there's anything else to add.") (5). Hard no: confirm-the-action questions naming items
  (8), option questions (6), generic "anything else I can help with" (6), reminder about a different order (window
  edge: asked on a message before the order id appears) (5), "Is this the right item?" (5).

### K4v4: the user's message is about another person (replaces K4 v2)
- **Used by:** request_is_for_another_user (first login always; catalog reads on the `other_person` screen).
- **Text:** "Does message A say that the account, order or reservation it is about belongs to another person, or ask
  the agent to act on another person's account? Another person means another customer or account holder (for example a
  spouse, friend, relative or colleague whose account or order it is). Whose it is depends on whose account or profile
  holds it: an order or reservation in the user's own account is the user's own, also when it was bought or booked for
  someone else, is a gift, or is used or flown by someone else. A message that only says the account, order or
  reservation belongs to another person or is under their name, email or profile is yes, even if it asks for nothing
  else. A public person, an author, a character or a company is not another person, and the user is not another
  person. Names, emails, zip codes and ids in message A count as the user's own unless message A says they belong to
  someone else. Any other message that asks for nothing new is no."
- **Second wording K4v4b:** "Is the user in message A asking for help with an account or an order that belongs to
  someone else (not themself)? If message A does not say the details belong to someone else, answer no."
- **Window:** one user message (`another_user_pick`).
- **Unclear:** ask K4v4b → still unclear → allow + log.
- **Few-shot: none.** Why: 0 wrong answers in 302 live asks with v2; it is the most frequent retail question at
  login, and examples would only add cost.
- **Test-case spec:** yes: "my wife's / husband's / mom's order" (8), "for my friend, her email is ..." (6), "I'm
  helping my colleague with his account" (5), "log in as my brother" (5), indirect ("the order is under my
  daughter's name") (6). Hard no: the user's own name, email, zip (8), a product named after a person or brand (5), a
  gift the user bought for someone ("I bought it for my son, I want to return it") (6: the order is the user's own),
  an author / celebrity mention (5), "it's me again" style (6).

### K6v4: a health or weather reason for cancelling (replaces K6 v1)
- **Used by:** insured_cancellation_condition_met (screen `health` decides which messages are asked).
- **Text:** "Does message A give a health reason or a weather reason for cancelling the trip? A health reason is an
  illness, an injury or another medical problem of the user or of a person on the trip. A weather reason is a storm,
  snow, a hurricane or another weather event that affects the trip. A message that only mentions health or weather
  without making it the reason for cancelling is no. A message that asks for nothing new is no."
- **Second wording K6v4b:** "Is the user in message A cancelling because someone on the trip is ill or hurt, or
  because of the weather? Answer yes only if that is given as the reason."
- **Window:** user messages that hit the screen, newest first, first yes.
- **Few-shot: yes (1 + 1).** Why: the screen passes many health / weather words that are not reasons; one hard no
  shows the boundary.
  - yes: "I need to cancel, my son came down with pneumonia and can't fly." → yes.
  - no: "The weather there is lovely this time of year, but I have to cancel because my job changed." → no.
- **Test-case spec:** yes: illness of the user (6), of a passenger (6), injury (5), weather event (8), medical
  appointment / surgery (5). Hard no: weather mentioned but another reason (6), health mentioned but another reason
  (6), a question about the insurance rules (6), a change of plans (6), "asks nothing new" replies ("yes", an id) (6).

### K7v4: a reason for cancelling the reservation (replaces K7 v1)
- **Used by:** cancellation_context_established.
- **Text:** "Does message A give a reason why the user wants to cancel the reservation? Any reason counts, for example
  a change of plans, the airline cancelled the flight, a health problem, the weather or the price. Only saying
  'cancel it', or only giving an id, a date or a yes, is no. When message A answers the agent's question about the
  reason, a short answer such as 'change of plans' counts."
- **Second wording K7v4b:** "Does the user in message A say why they want to cancel? Any reason at all is yes."
- **Window:** all user messages before the call, newest first, first yes.
- **Few-shot: none.** Why: any reason counts; 0 disagreements and 0 blocks in v3.
- **Test-case spec:** yes: each policy reason (change of plan, airline cancelled, other) (12), short answers to
  "why?" (8), reason inside a longer request (10). Hard no: "please cancel it" (8), an id or date only (8), a question
  about refunds (7), "yes" (7).

### K8v4: the user complains about a flight problem (merges K8 v1 and K9 v1)
- **Used by:** user_complained_about_relevant_flight_situation, cancelled_ / delayed_flight_certificate_*_conditions
  facts (4). The kind (delayed / cancelled) comes from the DB, not from this answer.
- **Text:** "Does message A complain about a problem with a flight of the user's trip, such as the flight being
  delayed or cancelled? A complaint is the user saying the flight was or is delayed or cancelled and that this is a
  problem for them. Only asking about a flight's status, or only asking to change or cancel a booking, is no. A
  message that asks for nothing new is no."
- **Second wording K8v4b:** "Is the user in message A unhappy that their flight was delayed or cancelled?"
- **Window:** all user messages before the check, newest first, first yes.
- **Unclear:** K8v4b → still unclear → false (user-only facts that allow compensation).
- **Few-shot: yes (1 + 1).** Why: the merged text is new and the hard no (a status question) is the common case.
  - yes: "My flight this morning was cancelled and I've been stuck at the airport all day. This is really
    frustrating." → yes.
  - no: "Can you check whether my flight tomorrow is on time?" → no.
- **Test-case spec:** yes: cancelled complaints (8), delayed complaints (8), both (3), typos ("dleayed", "cxld") (5),
  complaint + request for compensation (6). Hard no: status questions (8), change / cancel requests without a
  complaint (8), complaints about something else (seat, food, agent) (7), "asks nothing new" replies (7).

### K10v4: the user explicitly asks for compensation (K10 v1 + default)
- **Used by:** user_explicitly_requested_compensation (screen `compensation_request`).
- **Text:** "Does message A explicitly ask for compensation (a certificate, voucher, credit, money or something else
  to make up for a problem)? Asking only to change, cancel or refund a booking is no. A message that asks for nothing
  new is no."
- **Second wording K10v4b:** "Does the user in message A ask to be given something to make up for a problem?"
- **Window:** user messages that hit the screen, newest first.
- **Few-shot: none.** Why: 2 live asks, 2 right; screen-gated, cheap, no failure pattern to teach.
- **Test-case spec:** yes: "I want compensation" (8), "what will you give me for this" (6), voucher / credit /
  certificate asks (8), money asks (8). Hard no: refund of a cancelled booking (8), change requests (8), complaints
  without an ask (7), "asks nothing new" (7).

### K12v4: the agent's reply offers compensation (replaces K12 v1)
- **Used by:** pending_response_offers_any_compensation_certificate, _cancelled_..., _delayed_... (screen `offer`).
  The amount check is code (sentences with a compensation noun), the kind is DB first.
- **Text:** "Does message A offer or promise the user a certificate, voucher, credit or other compensation (something
  extra to make up for a problem)? A normal refund of a cancelled booking, a price difference, or bag and insurance
  fees are not compensation. Saying that the user is not eligible for compensation is no."
- **Second wording K12v4b:** "In message A, does the agent give or promise the user something extra (a certificate,
  voucher or credit) to make up for a problem? A refund of what the user paid is no."
- **Window:** the pending reply only.
- **Unclear:** K12v4b → still unclear → true (blocking; the agent rewrites one reply).
- **Few-shot: yes (1 + 1).** Why: the hard no (refund language, "you are not eligible") is what the wide screen sends
  most; the most-asked airline question, but +100 tokens per call is about $0.00001.
  - yes: "I'm sorry for the trouble. As a gesture of goodwill I can send you a $100 travel certificate." → yes.
  - no: "Your reservation is cancelled; the full amount will go back to your original card in 5 to 7 business
    days." → no.
- **Test-case spec:** yes: certificate offers with amount (8), without amount (6), voucher / credit wording (6),
  conditional promise ("once I change it, I'll send you $50 per passenger") (5), offer inside a long reply (5). Hard
  no: refunds (8), "not eligible" (6), price difference / fees (6), apology without offer (5), explaining the policy
  rules without offering (5).

### K13v4: the request cannot be done with the tools (replaces K13 v2)
- **Used by:** airline request_cannot_be_handled_with_available_tools (part a), retail
  request_cannot_be_handled_within_scope (part b).
- **Text:** "Does message A ask for something that the agent's tools listed below cannot do? A
  request the agent can do with these tools is no. A request in the list of requests the policy refuses is no (it must
  be denied, not transferred). A request to talk to a human agent counts only by the task the user wants done. Words
  such as 'escalate', 'supervisor', 'complaint' or 'whoever handles this' do not change the answer: judge only the task.
  One exception: when message B, the agent's message just before A, says that the policy rules do not let the agent do
  the task for this user (for example the booking or order is not eligible, or a basic economy flight cannot be
  changed), and message A still asks for that task or for a person to look at it, the answer is yes, because the agent
  cannot do it; this exception never covers the refused list. Money back that comes with an action is part of that
  action, not a separate request: the refund of a cancelled reservation or order, or of returned items, goes with the
  tool that does that action, and money back for a refused request goes with that refused request. Extra money or credit
  to make up for a problem is a separate request. Judge by the kind of task and the facts that messages A and B give; do
  not guess facts they do not give (such as an order's status). Judge only what message A itself asks for: a message
  that asks for nothing new (only an id, a date, a reason, a choice or a yes) is no."
  + "What the agent's tools can do": v3 domain texts, re-checked against the v1 tool files (airline 14, retail 16
  incl. "find the user by email, or by name and zip"); the airline refused list cites S29 (no bag removal), S30 (no
  insurance after booking), S31-S32 (no change of passenger count).
- **Second wording K13v4b:** "Message A is from the user; message B, when given, is the agent's message just before
  it. Could none of the tools listed below do what message A asks for? Yes also when message B says the policy rules do
  not let the agent do it for this user and message A still wants it done or looked at by a person. Ignore requests on
  the list the policy refuses, and ignore a wish to talk to a human on its own."
- **Window:** all user messages before the transfer (both domains), newest first, first yes; each asked with message
  B, the agent's text message just before it (after the previous user message), when there is one.
- **Message B (fix round 2, K13 v5):** context only; the quote comes from message A. Why: on the 200 dev
  conversations all 30 K13 blocks the stand-in allowed were airline transfers; in 24 the agent's transfer summary
  names a rule or "not eligible" (basic economy in 24). K13 saw only the user's words, so it judged the tool's kind of
  task (cancel_reservation 14, update_reservation_flights 14, update_reservation_baggages 2) and said no.
- **Unclear:** ask again → allow + log. Exit valve D11 and (retail) user-not-found code run before it.
- **Few-shot: yes (1 + 1).** Why: the wrong yeses were in-scope requests worded as "escalate"; one hard no fixes the
  boundary.
  - yes: "Can you ship me a free replacement and also give me a store credit?" (retail: no tool does either) → yes.
  - no: "Please escalate this, I just need the shipping address on my pending order changed." → no.
- **Test-case spec:** yes: requests no tool does (12 per domain spread), human request + out-of-scope task (6), the
  task stated in an earlier user message (window edge) (6), multi-request with one out of scope (6). Hard no: in-scope
  tasks worded "escalate / supervisor" (8), refused-list requests (6), human request with an in-scope task (6), "asks
  nothing new" (5), option changes of an item (5).

### K16v4: the user asks to cancel a reservation (K16 v1 + default + soften)
- **Used by:** request_cannot_be_handled_with_available_tools part c, only when no cancel_reservation attempt exists
  (code first).
- **Text:** "Does message A ask to cancel a reservation or a trip (all of it or a part of it)? A question about the
  cancellation rules without asking to cancel is no. A message that asks for nothing new is no."
- **Second wording K16v4b:** "Does the user in message A want a booking cancelled?"
- **Window:** all user messages, newest first, first yes. **Unclear:** ask again → allow + log.
- **Few-shot: none.** Why: a plain meaning; 1 disagreement in v3 (tiny right).
- **Test-case spec:** yes: whole-trip cancel (10), part of the trip (6), cancel with reason (8), indirect ("I won't
  be flying, please get rid of it") (6). Hard no: rules questions (8), change requests (8), refund status (7), "asks
  nothing new" (7).

### K17v4 (new): the travel-insurance choice for the booking
- **Used by:** booking_insurance_decision_established_and_matched; the insurance line of
  pending_database_change_details_listed_and_explicitly_confirmed (book).
- **Text:** "Messages A (from the agent, may be empty) and B (from the user, may be empty) are about a new flight
  booking. What do they say together about travel insurance for this booking? Answer added if insurance is included,
  bought or wanted; not_added if it is declined, not included or not wanted; not_said if neither. If A asks whether
  the user wants insurance and B answers yes or no, that answer is the choice. A question about insurance with no
  answer is not_said."
- **Second wording K17v4b:** "Read A and B. Is travel insurance part of this booking? Answer added, not_added, or
  not_said if they do not say."
- **Window:** candidates in the booking span S, newest first: user messages holding the insurance screen after the
  newest agent insurance message's first reply (B alone); then pairs (agent message holding the screen, its first user
  reply). Screen `insur / coverage / protection` decides only which messages are asked.
- **Accepted answers:** added / not_added / not_said / unclear; code compares with `args['insurance']`.
- **Few-shot: yes (1 + 1).** Why: new question; the one-word reply was the v3 loss.
  - added: A: "Would you like to add travel insurance for $30 per passenger?" B: "Yes." → added.
  - not_added: A: "Summary: two passengers, economy, no travel insurance, total $640. Shall I book it?" B: "Go
    ahead." → not_added.
- **Test-case spec:** added: one-word yes to the question (6), "add the insurance" (5), listing says included + go
  ahead (5); not_added: one-word no (5), "no thanks, skip it" (5), listing says no insurance + go ahead (4). Hard
  cases (30): the question with no reply (not_said) (6), user asks the price only (not_said) (6), yes to the booking but
  "without the insurance" (not_added) (6), listing says insurance + user removes it (not_added) (6), insurance asked
  for another booking earlier (window edge) (6).

### K18v4 (new): the retail cancel reason in other words
- **Used by:** consequential_action_details_listed (cancel) and user_confirmed_cancellation_order_and_reason, only
  when the exact phrase is not in T (a word list may not decide a value, L2.7).
- **Text:** "Does message A give this reason for cancelling the order: '{reason}' ({gloss})? The same meaning in other
  words counts. Another reason, or no reason, is no." Glosses: 'no longer needed' = the user does not need or want
  the item any more; 'ordered by mistake' = the order was placed by accident or is not what the user meant to order.
- **Second wording K18v4b:** "Is the reason for cancelling in message A '{reason}' in meaning?"
- **Window:** messages of T (agent and user), newest first, at most 4.
- **Few-shot: yes (1 + 1).** Why: the boundary between the two allowed reasons and other reasons ("too slow") is the
  point.
  - yes ('no longer needed'): "I won't have any use for it now, so please cancel." → yes.
  - no ('no longer needed'): "Please cancel, the delivery is taking too long." → no.
- **Test-case spec:** yes: paraphrases of each reason (12 each), said by the agent in a listing (6). Hard no: other
  reasons (price, delivery time, found cheaper) (12), the other allowed reason (8), no reason (10).

---

## 4. Counts

### 4.1 Predicates by v4 source vs v3 (main source of the value)

| source | v3 airline | v3 retail | v3 total | v4 airline | v4 retail | v4 total |
|---|---|---|---|---|---|---|
| args only | 7 | 2 | 9 | 7 | 2 | 9 |
| DB / event (incl. DB + text ids) | 17 | 8 | 25 | 17 | 8 | 25 |
| text-structure (code on text, may read DB) | 2 | 2 | 4 | 2 | 4 | 6 |
| **code only, total** | 26 | 12 | **38** | 26 | 14 | **40** |
| code + a tiny question | 16 | 12 | **28** | 16 | 10 | **26** |

- Moved to code only: response_performs_task_for_another_user (K5), user_specific_information_disclosed (K14).
- Still "code + tiny" but lighter: booking_required_information_established (K15 gone; only the shared K1v4 on the
  listing path), consequential_action_details_listed (K2 gone; K18v4 only for a paraphrased cancel reason),
  pending_database_change_details_listed_and_explicitly_confirmed (K2 gone; K17v4 only for booking insurance), the
  four certificate condition facts (K11 gone; K12 amount now code).
- Changed predicates: 28 changed (all 26 tiny rows + the 2 moved to code), 38 unchanged ("no" in the last column).

### 4.2 Tiny questions

| status | ids | count |
|---|---|---|
| kept (new version v4, fixed text, second wording) | K1, K3, K4, K6, K7, K8, K10, K12, K13, K16 | 10 |
| merged | K9 → K8v4 | 1 |
| dropped (code) | K2 (lines), K5 (DB owner), K11 (event), K14 (code + login), K15 (airports, trip type, listing) | 5 |
| new | K17v4 (insurance choice), K18v4 (cancel reason in other words) | 2 |
| **v4 question ids** | | **12** (v3: 16) |

Few-shot: 8 with 1 + 1 made-up examples (K1, K3, K6, K8, K12, K13, K17, K18), 4 without (K4, K7, K10, K16).

### 4.3 Estimated tiny calls per conversation (v3 measured: B2 11.2, B3 28.0)

Method: v3's live asks per question (TQA, cached repeats included: B2 val + train 4,819 asks → 3,336 calls, factor
0.69; B3 1,764 asks → 1,373 calls, factor 0.78), with each v4 change applied.

| question | B2 asks v3 | B2 asks v4 (assumption) | B3 asks v3 | B3 asks v4 |
|---|---|---|---|---|
| K2 | 807 | 0 (code) | 460 | 0 |
| K5 | 1,134 | 0 (code) | 544 | 0 |
| K1 | 893 | ~400 (one shared answer per write instead of one per fact focus; fast path takes the bare yeses, assumed half) | 374 | ~170 |
| K3 | 309 | 309 | 266 | 266 |
| K4 | 245 | 245 (asked at login as v3) | 57 | 57 |
| K12 | 820 | 820 (screen unchanged) | 0 | 0 |
| K13 | 486 | ~550 (all user messages read; fewer repeats after the exit valve) | 63 | ~70 |
| K16 | 58 | ~40 (cancel-attempt code first) | 0 | 0 |
| K6, K7, K8+K9, K10 | 53 | 53 | 0 | 0 |
| K15 | 14 | 0 | 0 | 0 |
| K17, K18 (new) | 0 | ~35 | 0 | ~5 |
| **asks** | 4,819 | **~2,450** | 1,764 | **~570** |
| **calls per conversation** | 11.2 | **~5.7** (range 5-7) | 28.0 | **~9.0** (range 8-11) |

The unclear re-asks add < 1 % (v3 unclear share on K1 0.3 %, K13 6 %; the K13 re-ask is the largest, ~+0.1 per
conversation). The fast-path share is the main unknown; measure it on dev before the freeze. Cost: about $0.00005 per
call with few-shot → about $0.0003 (B2-like) and $0.0005 (B3-like) per conversation, vs $0.0007 and $0.0016 in v3.

---

## 5. The 5 riskiest rows (and why)

1. **retail consequential_action_details_listed**: v3's biggest loss source (K2); v4's line code is new and has never
   seen real agent listings; item naming (91 orders with 2+ items of one product, 49 short option values) and
   address forms are where a line can be too strict.
2. **airline pending_database_change_details_listed_and_explicitly_confirmed**: one fact carries listing lines, the
   new K17v4 insurance line and the go-ahead; four write tools depend on it.
3. **retail user_explicitly_confirmed_pending_action (K1v4)**: gates all 7 retail writes; the user simulator never has
   to type "yes", and the batch decision (one go-ahead for several actions) is the exact v3 failure.
4. **retail user_chose_price_difference_payment_method**: v3's structure part alone added 44 blocks; v4 relies on the
   new D7 forms ("original payment method", "the card") to clear them, not yet counted on dev.
5. **airline booking_insurance_decision_established_and_matched (K17v4)**: a new question on the case that lost
   airline/0/t1; three answer values instead of yes/no.

(Next: request_cannot_be_handled_* (K13v4): softened, but the refused list still conflicts with one known task.)

---

## 6. Honest notes

- Every count in section 1 comes from the v1 database and tool code (`v4_pt_counts.txt`, `v4_pt_usersim.txt`); none
  comes from a conversation. How agents and users phrase things (listings, go-aheads, card names) was **not**
  counted here: no conversation was opened (B2 / B3 / hold-out are off limits). The form evidence for "users name a
  card by the id digits" is from v3's lessons (L1.2), not re-checked.
- The fast path D8 and the payment forms D7 decide values by exact strings or DB-derived strings, not by word screens
  (L2.7). The insurance, cancel-reason and health screens only decide whether to ask.
- The window D2 / D5 is wider than v3's one message. It can make a stale listing count for the same object. The risk
  is low (the values must still match the call, and the go-ahead after L is still needed), and it is what the lessons
  ask for; the made-up sets test the edge.
- The "user not found" transfer path (retail) and the cancel-attempt path (airline K16) are policy readings written
  before any data, from the lessons' list of code-decidable transfer cases (facts_rules.md §4 #10).
- The airline cancel_reservation has no confirmation rule in the frozen set (gap, L2.9); v4 does not add one.
- The call estimates in 4.3 rest on stated assumptions (mainly the fast-path share and K1's shared answer); they are
  not measurements.
