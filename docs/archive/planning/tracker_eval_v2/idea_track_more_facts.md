# Idea: track more of the judge's facts with code (proposal for the approvers)

Date 2026-10-22. Author: agent I1. **A proposal only.** It changes no code of the guard, runs nothing paid, and is not
part of the approved work. All numbers come from the saved data (sources at the end); estimates say "(estimate)".

## 1. Summary
The tracker sets 31 of the 66 TGR predicates with code. The other **35 predicates (23 conversation, 12 mixed)** still
come from the LLM judge. In the 4,903 saved train checks of frozen TGR they hold **13,514 of 20,204 judge values
(66.9 %)** and **682 of 957 values behind blocks (71.3 %)**: 64.6 % conversation, 6.7 % mixed. With the tracker's
values, 537 checks are blocked (371 steps in 162 of 396 conversations). **In 408 of them (76.0 %), one judge value of
these 35 predicates decides the block alone; 453 (84.4 %) would be allowed if all of them took the allowing value. Only
84 blocks come from code values alone.** One family dominates: "the agent reminded the user to include all items"
decides **234 blocked checks (43.6 %), in 79 conversations (20 %)**. Our own online train runs show the same pattern
(reminders decide 248 of 477 blocked checks). **How often the judge is wrong on these 35 predicates was never
measured** by a review (Part 7 checked only code types). Three proxies:
- the partner's regex confirmation check (gold v2) agrees with the judge in 94.1 % (retail) and 80.5 % (airline) of
  the write checks where both decide;
- in 23 identity checks the judge said no or unknown only because its 24,000-character view was cut; the user's
  message holds the exact email or name and zip;
- all 56 blocks from "the reply discloses user data" came before any tool output had shown user data.

**Main idea:** split the "meaning" facts into small pieces.
1. Use **code from structure** where the fact is string, number or order matching: arguments named in the agent's
   listing, identity strings, amounts, dates, facts in the database. Cost: $0.
2. Ask **one narrow, cached, checkable yes/no question per message** where meaning is needed: "is this a reminder?",
   "is this reply a yes?", "does this ask about another person?".
3. **Keep the judge** only for transfer and scope (2 predicates), and as a fallback.

A new "allow" from the new values needs two keys, so a false "yes" stays unlikely.

## 2. Every predicate the judge still sets
Columns, all from the 4,903 saved train checks of frozen TGR, unless noted:
- **checked:** judge values, true/false/unknown;
- **decides blocks:** blocked checks (with the tracker's values) that one other true/false value of this predicate
  alone would allow, with distinct steps in brackets. One check can count for several predicates;
- **online:** the same in our TGR + tracker online train runs (4,729 judged checks, 477 blocked);
- **allows on it:** allowed checks that the other value would block. A wrong value here lets a violation through;
- **way:** (a) code from structure, (b) one narrow LLM question per message, (c) keep the judge.

**Retail (14, all conversation)**

| predicate: meaning | checked (T/F/U) | decides blocks (steps) | online | allows on it | way | how to set it |
|---|---|---|---|---|---|---|
| `agent_reminded_..._for_modification`: an earlier agent message told the user to list all items to change | 258 (65/193/0) | **180 (130)** | 190 | 60 | b | One question per agent message ("does it ask the user to make sure all items to modify are listed?"), with a quote that code checks. Kept for the whole conversation (no 24,000 cut). A crude phrase probe finds a reminder-like phrase before 81 of the 193 "false" values; 22 of the 193 had a cut view. |
| `user_specific_information_disclosed`: the pending reply holds the user's profile, order or product data | 1,629 (1,330/299/0) | **56 (34)** | 68 | 283 | a | True only if the reply holds a value from a worked tool output (ids, names, addresses, amounts) that the user did not type. Nothing shown yet means false. All 56 blocks came before any worked tool output (the agent repeated the user's own words). It matters only before login (rule 3 has "OR user_authenticated"). |
| `agent_reminded_..._for_exchange` | 119 (51/68/0) | **54 (34)** | 58 | 50 | b | As above, for exchange. The probe finds a phrase before 3 of the 68 "false" values. |
| `name_and_zip_identity_provided_by_user`: the lookup's name and zip are the ones the user gave | 242 (223/15/4) | 19 (11) | 1 | 223 | a | The first name, last name and zip of the arguments appear in a user message. 17 of the 19 blocks had a cut view; in 17 of the 19 "false" or "unknown" values, the user's message holds all three. |
| `request_cannot_be_handled_within_scope` (transfer) | 55 (43/12/0) | 12 (12) | 6 | 43 | c | Needs the whole request; there is no fixed fact. Keep the judge. |
| `email_identity_provided_by_user` | 79 (68/11/0) | 11 (8) | 0 | 68 | a | The email argument appears in a user message. All 11 blocks had a cut view: in 6 the user typed the email; in 5 it is in no user message (block likely right). |
| `user_explicitly_confirmed_pending_action`: after the listing, the user said yes | 702 (652/50/0) | 2 (2); with the listing family 65 (47) | 2 | **366** | a + b | Code finds the last listing and the user's next message. A clear "no" in code: no user message after it, a question, or a refusal. "Is this an explicit yes to the listing?" is a narrow question (b). Gold v2 and the judge: 619 of 658 agree; 33 judge no / gold yes (all on blocked checks), 6 judge yes / gold no. |
| `user_chose_price_difference_payment_method` | 377 (373/4/0) | 1 (1) | 0 | 110 | a | The payment id, or its shown form ("gift card", "PayPal", card ending), is in a user message, or in a listing the user said yes to. |
| `response_performs_task_for_another_user` (every reply) | 1,629 (0/1,629/0) | 0 | 0 | **1,573** | b | One question on the pending reply. Never true in 1,629 + 1,566 values. Main gain: no full judge call on reply checks. |
| `request_is_for_another_user` (13 tools) | 2,367 (0/2,367/0) | 0 | 0 | **2,000** | a + b | Code: true if the call's user or order belongs to someone other than the logged-in user (database). (b): one question per user message, cached. Main gain: no judge call on the 1,344 read checks. |
| `consequential_action_details_listed`: an agent message listed the call's details | 702 (658/44/0) | 0 alone (family above) | 1 | 366 | a | Every id-like argument (order, items, payment, address fields, reason) is in the last agent message(s) before the user's reply, as written or in its shown form (item id → product name and options from shown objects). |
| `user_confirmed_return_order_items_and_method` | 154 (146/8/0) | 0 | 0 | 116 | a + b | Order id, every item and the refund method in the listing (a), then a yes (b). |
| `user_chose_pending_payment_method` | 10 (8/2/0) | 0 | 0 | 6 | a | As for the price-difference method. |
| `user_confirmed_cancellation_order_and_reason` | 60 (58/2/0) | 0 | 1 | 56 | a + b | Order id and reason words in the listing or the user's message (a), then a yes (b). |

**Airline (9 conversation, 12 mixed: the mixed ones accept tool outputs or user messages as evidence)**

| predicate: meaning | type | checked (T/F/U) | decides blocks (steps) | online | allows on it | way | how to set it |
|---|---|---|---|---|---|---|---|
| `pending_database_change_details_listed_and_explicitly_confirmed` | conv. | 169 (136/33/0) | **29 (21)** | 28 | 119 | a + b | As retail: flight numbers, dates, cabin, payment id, passengers and bags in the listing (a); the yes (b). Gold v2 and the judge: 107 of 133 agree; 21 judge no / gold yes (all blocked), 5 judge yes / gold no. The judge's "no" often names an argument the user did not approve (another payment method, flights never listed). Code can check exactly that. |
| `request_cannot_be_handled_with_available_tools` (transfer) | conv. | 99 (79/16/4) | 20 (19) | 7 | 79 | c | Keep the judge (judgment about the whole request). |
| `delayed_flight_certificate_response_conditions_and_amount_met` | mixed | 549 (0/549/0) | 10 (6) | 14 | 0 | a + b | Split it. Code checks the amount in the reply (= $50 × passengers of the shown reservation), the eligibility (membership, insurance, cabin) and the finished change. (b) asks about the complaint and the wish. |
| `pending_response_offers_delayed_flight_certificate` | conv. | 549 (18/531/0) | 10 (6) | 14 | **531** | a + b | A wide word screen (certificate, voucher, credit, compensation, $): no such word means false. If a word is found, ask one question on the reply. |
| `airline_cancelled_flight_confirmed` | mixed | 35 (0/35/0) | 9 (9) | 10 | 0 | a | Fact: the flight status in the flight data. No flight was cancelled in any of the 35 checks, and the judge said false: the same value, so no block changes. Whether a user's claim alone counts is a reading (Q2). |
| `cancellation_is_within_24_hours` | mixed | 35 (1/33/1) | 9 (9) | 10 | 0 | a | `created_at` of the shown reservation vs the policy time. Gold v1 agrees with the judge in 33 of 33. |
| `insured_cancellation_condition_met`: health or weather reason | conv. | 35 (5/30/0) | 4 (4) | 4 | 5 | b | One question per user message. The judge equals gold v2's regex in 35 of 35. |
| `modification_user_and_reservation_ids_established` | mixed | 156 (151/3/2) | 2 (2) | 1 | 110 | a | The ids are in a user message, or a worked profile or reservation lookup shows them. |
| `user_selected_eligible_flight_change_payment_method` | mixed | 136 (69/30/37) | 2 (2) | 1 | 7 | a | Gift card or credit card, stored in the profile (code). "Chosen": the id or its shown form is in a user message or a confirmed listing. |
| `booking_required_information_established` | mixed | 13 (12/0/1) | 1 (1) | 0 | 9 | a | User id shown; origin and destination as codes or city names (airport list) in user messages; trip-type words. |
| `cancelled_flight_certificate_response_conditions_and_amount_met` | mixed | 549 (0/549/0) | 0 | 0 | 0 | a + b | Split as the delayed one ($100 × passengers). |
| `compensation_is_prohibited_for_relevant_reservation` | mixed | 549 (3/498/48) | 0 | 0 | 0 | a, else c | Membership by code. Insurance and cabin by code if all shown reservations of the user agree; else the judge. |
| `pending_response_offers_any_compensation_certificate` | conv. | 549 (18/531/0) | 0 | 0 | 505 | a + b | Word screen, then one question. |
| `pending_response_offers_cancelled_flight_certificate` | conv. | 549 (4/545/0) | 0 | 0 | 531 | a + b | Word screen, then one question. |
| `user_complained_about_relevant_flight_situation` | conv. | 549 (73/476/0) | 0 | 0 | 0 | b | One question per user message. |
| `user_explicitly_requested_compensation` | conv. | 549 (41/508/0) | 0 | 0 | 0 | b | One question per user message. |
| `booking_insurance_decision_established_and_matched` | conv. | 13 (13/0/0) | 0 | 0 | 9 | a + b | The user's answer to the insurance question (b), compared with the `insurance` argument (a). |
| `passenger_identity_details_established` | mixed | 13 (13/0/0) | 0 | 0 | 9 | a | Names and birth dates are in user messages or saved passengers (normalize date formats). |
| `cancellation_context_established` | mixed | 35 (35/0/0) | 0 | 1 | 21 | a + b | Ids by code; the reason (change of plan, airline cancelled, other) by one question. |
| `cancelled_flight_certificate_send_conditions_met` | mixed | never judged | - | - | - | a + b | As the response version. |
| `delayed_flight_certificate_send_conditions_met` | mixed | never judged | - | - | - | a + b | As the response version. |

Totals by way: (a) 13 predicates, (a + b) 14, (b) 6, (c) 2.

## 3. Three designs, from cheapest to strongest
**The safe side, for all three.** A false "yes" on a confirmation lets an unconfirmed change through, which is the
real risk. A false "no" only costs a block. So every new value is merged with the judge's value like this:

| predicate kind | value that allows | new code or label may set it alone | needs two keys |
|---|---|---|---|
| required (confirmed, listed, reminded, identity given, chose) | true | **false**, on clear structure only | **true**: code and label agree (D2, D3). D1 sets true alone only for exact string facts (identity, ids) and "nothing shown yet, so nothing disclosed". |
| forbidden (another user, disclosed, offers a certificate) | false | **true** | **false**: code and label agree, or a wide word screen finds no trigger word |
| any, when the new value is unknown | | the judge's value (as version b today) | |

Gate before any online use: in the offline review, **0 cases of "new allow, the reference says block"**. With n
reviewed new allows and 0 errors, the 95 % upper bound on the error rate is about 3/n (rule of three).

**D1: structure checks in code (cost per run $0).**
- **What changes:** a new lookup file per domain over a "message view": the user and agent messages in order, the
  pending call, and the shown objects (to turn ids into names). New helpers:
  - `user_said(value)`;
  - `agent_listed(args)`: every id-like argument in the last listing;
  - `reply_after(listing)`;
  - `reply_is_question_or_no`.

  The frozen lookups, types and rules stay. The new files get their own sha256.
- **Covers:** identity strings (2), disclosure before login (1), ids given (4), payment chosen (3), the listing part of
  all confirmations, the fact parts of the airline mixed predicates (24 hours, cancelled flight, eligibility, amounts),
  and the word screen on airline replies.
- **Expected effect (saved train data):**
  - removes **79 of 537 blocked checks (14.7 %)**: 56 disclosure blocks (all before any tool output) and 23
    identity blocks (cut view, exact string in the user's message);
  - adds blocks where an argument was never listed. The number is unknown until it is built. Gold v2 hints at 6 + 5
    write checks with judge yes / gold no;
  - the 14 blocked cancellation checks do not change: code equals the judge wherever code decides (24 hours: 33 of
    33; cancelled flight: 35 of 35);
  - (estimate) the judge is no longer needed on most airline reply checks (549), where no compensation word appears.
- **Risks:** paraphrases (an item named by its options, dates in other formats), and the simulated user sometimes
  speaks like the agent. Also two readings for the person: is repeating the user's own words disclosure? Must a yes
  follow a listing of every argument?
- **Offline test ($0, like the earlier Parts 6–8):**
  1. run the new lookups on the 4,903 saved train checks;
  2. compare them with the judge;
  3. a blind review (independent agent or person, no gpt call) of every disagreement on a blocked check, 30 random
     others and 50 controls;
  4. decide again (as `decide_again.py`), and count the blocks removed and added, each with its review verdict.

  Then repeat once on the validation runs and the Stage A logs (no new runs). **Gold v2 is only a second check**: a
  code confirmation check like ours agrees with its regexes by construction. D1 must be written from the policy text,
  not from gold v2.

**D2: one narrow question per message (small LLM cost).**
- **What changes:** each new message, and each pending reply, gets a few yes/no labels with a quoted span. Each label
  is cached by (message text, question) and asked once, then reused at every later check. Labels never fall out of a
  24,000-character view. Predicates become code over labels, for example "an agent message after the last item list
  and before the call has reminder = yes". Code checks that the quote exists in the message, and that a yes follows a
  listing that holds the call's arguments (D1). Otherwise the label is ignored.
- **The questions (about 8):**
  - reminder of all items;
  - explicit yes to this listing;
  - asks about another person;
  - health or weather reason;
  - complaint about a cancelled or delayed flight;
  - asks for compensation;
  - the reply offers a certificate;
  - the reply does a task for another person.
- **Covers:** reminders (2), the yes of every confirmation (as the second key), another user (2), compensation and
  certificates (7 judged ones), cancellation reasons (2).
- **Expected effect:**
  - reminders decide 234 blocked checks (164 steps, 79 conversations). The gain is the judge's error rate on them
    × 234. That rate is unknown; the crude probe gives only an upper hint (84 of 261 "false" values);
  - (estimate) once every judge predicate of a tool is covered, the full judge call can be skipped. This is possible
    on up to 3,522 of 4,903 checks (72 %): 2,178 reply checks and 1,344 retail read checks. Today it is skipped in
    0 checks.
- **Risks:** a label is still an LLM answer. Keep it narrow (one message, one question), quoted and checked, and use
  it only as one of two keys for a new allow.
- **Offline test:** the labels need real LLM calls, so this is **not free**.
  - $0 first: tests with a fake LLM, and a dry run with the network blocked that counts the exact questions.
  - Then label the 396 saved train conversations: 2,470 user messages, 2,074 agent text messages, plus the pending
    replies. Cost about $2–4 (estimate; the judge cost $0.00056 per call on average). **Needs its own explicit
    approval.**
  - Then score the labels against the D1 review sample.

**D3: code + labels as a third guard, the judge only for the rest (strongest).**
- **What changes:** D1 + D2 replace the judge for every predicate they cover. The judge stays for the 2 transfer
  predicates, and as the fallback for unknowns. Its view keeps the start of the conversation (final report, next
  step 1). Optional: split the 12 mixed predicates into a code part AND a message part (idea A1/A2). That makes a
  new rule set, so a new method with new approval, because the rules are frozen.
- **Covers:** 33 of the 35 predicates.
- **Expected effect:** the covered predicates decide up to 421 of 537 blocked checks (453 minus the 32 transfer
  checks; estimate, an upper bound). The real gain depends on the error rates from the review.
- **Risks:** as D1 + D2. The biggest change of the three, so it is measured as its own guard, never mixed into the
  Stage A guards.
- **Test:** offline as D1 + D2. Then, with approval, as a third branch at Stage B fork points where it decides
  differently, or in a small separate run.

## 4. A short plan the approvers could approve
| part | what | money | fits where |
|---|---|---|---|
| M1 | **Blind review of the judge values that decide blocks** (as the earlier Part 7): the 311 (step, predicate) pairs from section 2, plus 50 controls. Gives the judge's error rate per family: the missing number. | $0 (agent or person) | Now, in parallel with Part 4 and Stage A. It touches no file of `guard/` or `fork/`. |
| M2 | D1 as new lookup files, with tests, an offline replay on train, a review of the disagreements, and decide again | $0 | After M1, or in parallel. Only new files; frozen inputs unchanged. |
| M3 | D1 offline on the validation runs and the Stage A conversations (both guards) | $0 | After Stage A. Gives D1's effect on about 2,000 new conversations without new runs, and the fork points for a third branch. |
| M4 | D2 dry run with a fake LLM, an exact question count, and an approval request | $0 | Any time after M1. |
| M5 | D2 labels on the saved train conversations | about $2–4 (estimate); **own approval** | After M4. |
| M6 | D3 as a third branch in Stage B forks, where it differs (or a small separate run) | similar to Stage B ($15–25, estimate; exact after M3); **own approval** | Only if M2/M3/M5 pass the safety gate. Inside the $100 soft stop. |

**Recommendation:**
- approve M1 now: it costs nothing, and it tells whether the 35 predicates are worth the work;
- then M2;
- decide M4–M6 after their numbers.

Stage A stays as planned. It measures the tracker as frozen, and M1–M3 do not change it.

## 5. Open questions for the approvers
1. May a guard make extra small LLM calls at run time (D2)? If yes, with which model: gpt-6-luna, or the cheaper
   gpt-5-nano for one-message questions?
2. **Readings, for a person:**
   - is repeating the user's own words disclosure?
   - does a user's claim count for "within 24 hours" or "airline cancelled", when the shown reservation says
     otherwise?
   - does one reminder cover later item changes?
   - must the yes follow a listing of every argument (strict, like gold v2 F5), or may the user delegate ("use my
     saved card")?
3. Who does the M1 review: a person, or an independent agent with a person checking a sample?
4. What is the go/no-go threshold for a family? For example: build it only if the judge is wrong in at least 10 % of
   its block-deciding values.
5. Should this go into the current plan (M1–M3 in parallel, M6 as a third Stage B branch), or into a separate
   follow-up plan after this plan's report? The follow-up is cleaner for the measurement.
6. May the frozen rule set be changed, to split the 12 mixed predicates (D3, optional)?
7. Should the 24,000-character cut be fixed first (keep the conversation start) as the baseline? It explains 23
   identity blocks, and 22 of 193 "false" reminder values.

## Sources and how to recompute (no LLM, no network; output under `predicate_correctness/output/logs/`)
- `predicate_correctness/scoring/idea_v2_i1_counts.py` → `v2_i1_counts.json`, `v2_i1_counts2.log`: values, blocks
  decided (decision code re-run with one value changed), families, online train runs. Validation runs are not read.
- `predicate_correctness/scoring/idea_v2_i1_probes.py` → `v2_i1_probes.json`, `v2_i1_probes.log`: the judge vs gold v2
  and gold v1, the database fact for cancelled flights, and the identity and reminder probes. It loads gold code
  only to measure the judge (scoring use, as `scoring/`), never as a method input.
- `predicate_correctness/scoring/idea_v2_i1_examples.py` → `v2_i1_examples.log`: sample judge evidences.
- Also used: `output/p3_type_counts.md`, `output/p6_agreement.md`, `output/p7_review_results.md`,
  `output/p10_metrics.md`, `output/predicate_types.md`, `from_shieldagent/rules/*/rule_set.json`, the policies, and
  `from_shieldagent/scoring/policies/gold_v2/README.md`.
