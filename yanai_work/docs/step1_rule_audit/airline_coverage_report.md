# Step 1: rule coverage audit, airline domain

| | |
|---|---|
| Ground truth | `output/deep_policy/extraction_20261012_112735/airline_wiki.txt`, byte-identical to `policy_docs/airline_wiki.txt` and to τ-bench `tau_bench/envs/airline/wiki.md` @ `59a200c`. Current time fixed at **2024-05-15 15:00:00 EST**. |
| Audited extraction | Same folder: `TauBench_all_extracted_policies.json` (23), `TauBench_all_extracted_rules.json` (48 raw), `TauBench_risk_categories.json` (7 categories, 49 refined), `TauBench_policy_rule_mapping.json`. Extracted by gpt-5-nano, `target_subject="User"` (CLI default). |
| Deliverables | `policies/curated/airline_clauses.json` (clauses with the per-clause audit), `policies/curated/airline_curated_rules.json` (curated rules), `policies/curated/airline_config.json` (current time), `scripts/validate_curated_rules.py`. These moved from `output/curated/` (git-ignored, now superseded; archived at `archive/step1_gold_standard/data/output_curated/` in the 2026-10-17 cleanup) at Step 1 close-out. |
| Method | Manual, clause-by-clause reading of the wiki, by me. No LLM was used for any judgment. Every clause `text` and every `wiki_quote` fragment is checked by the validator to be verbatim wiki text. Wiki of record: `policy_docs/airline_wiki.txt` (sha256 checked). |

## Headline

- **Before:** 23 of 61 normative clauses were fully covered (37 if subject phrasing is ignored). 31 were partial, **2 incorrect, 5 missing**. **After:** 61 of 61 are covered by 50 atomic, agent-phrased curated rules. The validator passes.
- **Every number survived extraction correctly**: 5 passengers; 1/1/3 payment limits; the 0/1/2, 1/2/3, 2/3/3 bag table; $50; $30; $100 and $50 per passenger; 24 h. The damage is in **conditions, modality, enumerations and subject**, not in numbers.
- The two **incorrect** rules would change shield decisions:
  - R37 narrows "(basic) economy" to basic economy, which **wrongly allows compensation** for regular, uninsured economy passengers.
  - R9 inverts the "don't invent information" rule into a user obligation.
- The five **missing** clauses:
  - "no subjective recommendations";
  - "no tool call and response in the same turn" (both directions);
  - "flights with status delayed / on time / flying cannot be booked". The whole *Domain Basic* section was never extracted.
- **Partial** clauses that matter for the shield:
  - "if and only if" transfer weakened to "if";
  - the cancellation "condition" never grounded to health/weather;
  - cancellation reasons not enumerated;
  - "Basic economy **flights** cannot be modified" broadened to the whole **reservation**, which contradicts the cabin-change permission;
  - complaint triggers for compensation weakened to "experiences a cancelled/delayed flight".

## 1. Summary counts

Clauses: **73** (61 normative, 12 facts). Extracted refined rules: 49. Curated rules: **50**.

| Status (normative clauses) | Before — strict | Before — content only (ignoring subject phrasing) | After curation |
|---|---|---|---|
| covered | 23 | 37 | 61 |
| partial | 31 | 17 | 0 |
| incorrect | 2 | 2 | 0 |
| missing | 5 | 5 | 0 |
| **total** | 61 | 61 | 61 |

Curated rules by origin: extracted 16, modified 27, added 2, interpretation 4, tool_spec 1. Rules needing each data type (a rule can need several): state 29, tool_log 6, structural 2, dialogue 21.

Origin legend: *extracted* = the extracted rule's content is kept and only rephrased as an agent obligation; *modified* = conditions, scope or numbers were changed, or the rule was split or merged; *added* = no extracted rule existed; *interpretation* = a reading the wiki does not force, adopted at Step 1 close-out; *tool_spec* = includes a condition taken from the τ-bench tool description.

## 2. Traceability matrix

`Refined` = rule ids in `*_risk_categories.json`; `Raw` = ids in `*_all_extracted_rules.json`. Issue tags: SUBJ wrong subject (user instead of agent) · COND condition dropped, added, or ungrounded · MODAL weakened modality · SCOPE wrong scope · NUM wrong number/enumeration · INV inverted meaning · HALL invented content · MERGE compound · DUP duplicated · DROP not extracted.

| Clause | L | Kind | Verbatim wiki text | Refined | Raw | Before | Issues | Curated rules (after) |
|---|---|---|---|---|---|---|---|---|
| AIR-CTX-01 | 3 | F | The current time is 2024-05-15 15:00:00 EST. | — | — | n/a (fact) | — | AIR-R042 |
| AIR-CTX-02 | 5 | F | As an airline agent, you can help users book, modify, or cancel flight reservations. | — | — | n/a (fact) | — | AIR-R008, AIR-R009 |
| AIR-GEN-01a | 7 | N | Before taking any actions that update the booking database (booking, modifying flights, editing baggage, upgrading cabin class, or updating passenger information), you must list the action details | 1 | 1 | partial | SUBJ MERGE SCOPE | AIR-R001 |
| AIR-GEN-01b | 7 | N | obtain explicit user confirmation (yes) to proceed. | 1 | 1 | partial (content: covered) | SUBJ MERGE | AIR-R002 |
| AIR-GEN-02a | 9 | N | You should not provide any information, knowledge, or procedures not provided by the user or available tools | 9 | 2 | incorrect | SUBJ INV HALL | AIR-R003 |
| AIR-GEN-02b | 9 | N | or give subjective recommendations or comments. | — | — | missing | DROP | AIR-R004 |
| AIR-GEN-03a | 11 | N | You should only make one tool call at a time | 47 | 3 | partial (content: covered) | SUBJ | AIR-R005 |
| AIR-GEN-03b | 11 | N | if you make a tool call, you should not respond to the user simultaneously. | — | 3 | missing | DROP | AIR-R006 |
| AIR-GEN-03c | 11 | N | If you respond to the user, you should not make a tool call at the same time. | — | — | missing | DROP | AIR-R006 |
| AIR-GEN-04 | 13 | N | You should deny user requests that are against this policy. | 48 | 4 | partial (content: covered) | SUBJ | AIR-R007 |
| AIR-GEN-05a | 15 | N | You should transfer the user to a human agent if and only if the request cannot be handled within the scope of your actions. | 49 | 5 | partial | MODAL SUBJ | AIR-R008 |
| AIR-GEN-05b | 15 | N | You should transfer the user to a human agent if and only if the request cannot be handled within the scope of your actions. | 49 | 5 | partial (content: covered) | SUBJ | AIR-R009 |
| AIR-DOM-01 | 19 | F | Each user has a profile containing user id, email, addresses, date of birth, payment methods, reservation numbers, and membership tier. | — | — | n/a (fact) | — | — |
| AIR-DOM-02 | 21 | F | Each reservation has an reservation id, user id, trip type (one way, round trip), flights, passengers, payment methods, created time, baggages, and travel insurance information. | — | — | n/a (fact) | — | AIR-R030 |
| AIR-DOM-03 | 23 | F | Each flight has a flight number, an origin, destination, scheduled departure and arrival time (local time), and for each date: | — | — | n/a (fact) | — | — |
| AIR-DOM-04a | 24 | F | If the status is "available", the flight has not taken off, available seats and prices are listed. | — | — | n/a (fact) | — | — |
| AIR-DOM-04b | 25 | F | If the status is "delayed" or "on time", the flight has not taken off, cannot be booked. | — | — | n/a (fact) | — | AIR-R010 |
| AIR-DOM-04c | 25 | N | If the status is "delayed" or "on time", the flight has not taken off, cannot be booked. | — | — | missing | DROP | AIR-R010 |
| AIR-DOM-04d | 26 | F | If the status is "flying", the flight has taken off but not landed, cannot be booked. | — | — | n/a (fact) | — | AIR-R010 |
| AIR-DOM-04e | 26 | N | If the status is "flying", the flight has taken off but not landed, cannot be booked. | — | — | missing | DROP | AIR-R010 |
| AIR-BOOK-01a | 30 | N | The agent must first obtain the user id | 2 | 6 | partial (content: covered) | SUBJ MERGE | AIR-R011 |
| AIR-BOOK-01b | 30 | N | then ask for the trip type, origin, destination. | 2 | 6 | partial | SUBJ COND | AIR-R012 |
| AIR-BOOK-02a | 32 | N | Passengers: Each reservation can have at most five passengers. | 3 | 7 | partial (content: covered) | SUBJ | AIR-R013 |
| AIR-BOOK-02b | 32 | N | The agent needs to collect the first name, last name, and date of birth for each passenger. | 4 | 8 | partial (content: covered) | SUBJ | AIR-R014 |
| AIR-BOOK-02c | 32 | N | All passengers must fly the same flights in the same cabin. | 5 | 9 | covered | — | AIR-R015 |
| AIR-BOOK-03a | 34 | N | Payment: each reservation can use at most one travel certificate | 29 | 10 | partial (content: covered) | SUBJ | AIR-R016 |
| AIR-BOOK-03b | 34 | N | at most one credit card | 30 | 11 | partial (content: covered) | SUBJ | AIR-R017 |
| AIR-BOOK-03c | 34 | N | and at most three gift cards. | 31 | 12 | partial (content: covered) | SUBJ | AIR-R018 |
| AIR-BOOK-03d | 34 | F | The remaining amount of a travel certificate is not refundable. | 32 | 13 | n/a (fact) | — | — |
| AIR-BOOK-03e | 34 | N | All payment methods must already be in user profile for safety reasons. | 33 | 14 | covered | — | AIR-R019 |
| AIR-BOOK-04a | 36 | N | If the booking user is a regular member, 0 free checked bag for each basic economy passenger, 1 free checked bag for each economy passenger, and 2 free checked bags for each business passenger. | 22 | 15 | partial | SCOPE | AIR-R020 |
| AIR-BOOK-04b | 36 | N | If the booking user is a silver member, 1 free checked bag for each basic economy passenger, 2 free checked bag for each economy passenger, and 3 free checked bags for each business passenger. | 23 | 16 | partial | SCOPE | AIR-R021 |
| AIR-BOOK-04c | 36 | N | If the booking user is a gold member, 2 free checked bag for each basic economy passenger, 3 free checked bag for each economy passenger, and 3 free checked bags for each business passenger. | 24 | 17 | partial | SCOPE | AIR-R022 |
| AIR-BOOK-04d | 36 | N | Each extra baggage is 50 dollars. | 25 | 18 | covered | — | AIR-R023 |
| AIR-BOOK-05a | 38 | N | Travel insurance: the agent should ask if the user wants to buy the travel insurance | 27 | 19 | partial | MODAL MERGE | AIR-R024 |
| AIR-BOOK-05b | 38 | N | which is 30 dollars per passenger | 27 | 19 | covered | MERGE | AIR-R025 |
| AIR-BOOK-05c | 38 | F | and enables full refund if the user needs to cancel the flight given health or weather reasons. | 27 | 19 | n/a (fact) | — | AIR-R042 |
| AIR-MOD-01a | 42 | N | The agent must first obtain the user id and the reservation id. | 10 | 20 | partial (content: covered) | SUBJ | AIR-R026 |
| AIR-MOD-01b | 42 | N | The agent must first obtain the user id and the reservation id. | 10 | 20 | partial (content: covered) | SUBJ | AIR-R027 |
| AIR-MOD-02a | 44 | N | Change flights: Basic economy flights cannot be modified. | 11 | 21 | partial | SCOPE SUBJ | AIR-R028 |
| AIR-MOD-02b | 44 | N | Other reservations can be modified without changing the origin, destination, and trip type. | 12 | 22 | partial (content: covered) | SUBJ MERGE | AIR-R029, AIR-R030 |
| AIR-MOD-02c | 44 | F | Some flight segments can be kept, but their prices will not be updated based on the current price. | 13 | 23 | n/a (fact) | — | — |
| AIR-MOD-02d | 44 | N | The API does not check these for the agent, so the agent must make sure the rules apply before calling the API! | 6 | 24 | partial | SUBJ SCOPE | AIR-R028, AIR-R029, AIR-R030 |
| AIR-MOD-03a | 46 | N | Change cabin: all reservations, including basic economy, can change cabin without changing the flights. | 14 | 25 | partial (content: covered) | SUBJ | AIR-R028 |
| AIR-MOD-03b | 46 | N | Cabin changes require the user to pay for the difference between their current cabin and the new cabin class. | 15 | 26 | covered | — | AIR-R031 |
| AIR-MOD-03c | 46 | N | Cabin class must be the same across all the flights in the same reservation | 16 | 27 | covered | — | AIR-R032 |
| AIR-MOD-03d | 46 | N | changing cabin for just one flight segment is not possible. | 17, 16 | 28 | covered | DUP | AIR-R032 |
| AIR-MOD-04a | 48 | N | Change baggage and insurance: The user can add but not remove checked bags. | 26 | 29 | covered | — | AIR-R033 |
| AIR-MOD-04b | 48 | N | The user cannot add insurance after initial booking. | 28 | 30 | covered | — | AIR-R034 |
| AIR-MOD-05a | 50 | N | Change passengers: The user can modify passengers but cannot modify the number of passengers. | 18 | 31 | covered | — | AIR-R035 |
| AIR-MOD-05b | 50 | N | This is something that even a human agent cannot assist with. | 19 | 32 | partial | SCOPE | AIR-R036 |
| AIR-MOD-06a | 52 | N | Payment: If the flights are changed, the user needs to provide one gift card or credit card for payment or refund method. | 20, 35 | 33 | covered | DUP | AIR-R037 |
| AIR-MOD-06b | 52 | N | The agent should ask for the payment or refund method instead. | 21 | 34 | partial | COND | AIR-R038 |
| AIR-CAN-01a | 56 | N | The agent must first obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons) | 7 | 35 | partial | SUBJ SCOPE | AIR-R039 |
| AIR-CAN-01b | 56 | N | The agent must first obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons) | 8 | 36 | partial | SUBJ SCOPE | AIR-R040 |
| AIR-CAN-01c | 56 | N | The agent must first obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons) | 38 | 37 | partial | SUBJ NUM | AIR-R041 |
| AIR-CAN-02a | 58 | N | All reservations can be cancelled within 24 hours of booking, or if the airline cancelled the flight. | 39 | 38 | covered | — | AIR-R042 |
| AIR-CAN-02b | 58 | N | All reservations can be cancelled within 24 hours of booking, or if the airline cancelled the flight. | 39 | 38 | covered | — | AIR-R042 |
| AIR-CAN-02c | 58 | N | Otherwise, basic economy or economy flights can be cancelled only if travel insurance is bought and the condition is met | 40 | 39 | partial | COND | AIR-R042 |
| AIR-CAN-02d | 58 | N | and business flights can always be cancelled. | 41 | 40 | covered | — | AIR-R042 |
| AIR-CAN-02e | 58 | N | The rules are strict regardless of the membership status. | 42 | 41 | covered | MERGE | AIR-R042 |
| AIR-CAN-02f | 58 | N | The API does not check these for the agent, so the agent must make sure the rules apply before calling the API! | 42 | 41 | covered | MERGE | AIR-R042 |
| AIR-CAN-03a | 60 | N | The agent can only cancel the whole trip that is not flown. | 43 | 42 | covered | MERGE | AIR-R043 |
| AIR-CAN-03b | 60 | N | If any of the segments are already used, the agent cannot help and transfer is needed. | 43, 44 | 42, 43 | covered | DUP | AIR-R044 |
| AIR-CAN-04 | 62 | F | The refund will go to original payment methods in 5 to 7 business days. | 34 | 44 | n/a (fact) | — | — |
| AIR-COMP-01a | 66 | N | If the user is silver/gold member or has travel insurance or flies business, and complains about cancelled flights in a reservation, the agent can offer a certificate as a gesture | 45 | 45 | partial | COND | AIR-R045, AIR-R046, AIR-R048 |
| AIR-COMP-01b | 66 | N | after confirming the facts | 45 | 45 | covered | — | AIR-R047 |
| AIR-COMP-01c | 66 | N | with the amount being $100 times the number of passengers. | 45 | 45 | covered | — | AIR-R048 |
| AIR-COMP-02a | 68 | N | If the user is silver/gold member or has travel insurance or flies business, and complains about delayed flights in a reservation and wants to change or cancel the reservation, the agent can offer a certificate as a gesture | 46 | 46 | partial | COND | AIR-R045, AIR-R046, AIR-R049, AIR-R050 |
| AIR-COMP-02b | 68 | N | after confirming the facts and changing or cancelling the reservation | 46 | 46 | covered | — | AIR-R047, AIR-R049 |
| AIR-COMP-02c | 68 | N | with the amount being $50 times the number of passengers. | 46 | 46 | covered | — | AIR-R050 |
| AIR-COMP-03a | 70 | N | Do not proactively offer these unless the user complains about the situation and explicitly asks for some compensation. | 36 | 47 | covered | — | AIR-R046 |
| AIR-COMP-03b | 70 | N | Do not compensate if the user is regular member and has no travel insurance and flies (basic) economy. | 37 | 48 | incorrect | NUM | AIR-R045 |

For clauses whose verbatim text is shared (e.g. one 'if and only if' sentence split into two directions), the atomic reading is in `atomic_reading` in the clauses JSON.

## 3. Issues found, before → after

Every normative clause that was not `covered` before curation:

| Clause | Before | Problem in extracted rule(s) | After (curated) |
|---|---|---|---|
| AIR-GEN-01a | partial | Refined R1 'User must be shown action details…' — passive/user subject, merged with the confirmation clause, and 'booking database' narrowed to 'booking update actions'. | **AIR-R001**: The agent must list the action details to the user before calling any tool that updates the booking database (booking, cancelling, changing flights or cabin, editing baggage, or updating passengers). |
| AIR-GEN-01b | partial | Content present in R1 but phrased as a user obligation and merged with AIR-GEN-01a. | **AIR-R002**: The agent must obtain an explicit 'yes' from the user, given after the action details were listed, before calling any tool that updates the booking database. |
| AIR-GEN-02a | incorrect | R9 'User must rely only on information … provided by TauBench or available tools; do not request information not provided' — obligation moved to the user, 'the user' replaced by 'TauBench', and an invented 'do not request' clause. | **AIR-R003**: The agent must not provide information, knowledge, or procedures that were not provided by the user or by the available tools. |
| AIR-GEN-02b | missing | Dropped already at raw-rule level (raw r2 omits it). | **AIR-R004**: The agent must not give subjective recommendations or comments. |
| AIR-GEN-03a | partial | R47 'the user must not trigger more than one external tool call at a time' — the user never makes tool calls. | **AIR-R005**: The agent must make at most one tool call per turn. |
| AIR-GEN-03b | missing | R47/r3 only say 'wait for the tool result'; the no-simultaneous-response constraint is lost. | **AIR-R006**: The agent must not respond to the user and make a tool call in the same turn. |
| AIR-GEN-03c | missing | Not captured. | **AIR-R006**: The agent must not respond to the user and make a tool call in the same turn. |
| AIR-GEN-04 | partial | R48 'The user must not submit requests that violate any policy; such requests will be denied' — obligation moved to the user. | **AIR-R007**: The agent must deny (refuse to carry out) user requests that are against this policy. |
| AIR-GEN-05a | partial | 'if and only if' weakened to 'if' in R49; the prohibition on unnecessary transfers is lost. | **AIR-R008**: The agent must not transfer the user to a human agent unless the request cannot be handled within the scope of the agent's actions or the user explicitly asks for a human agent. |
| AIR-GEN-05b | partial | R49 'the user will be transferred' — passive, user-centred. | **AIR-R009**: The agent must transfer the user to a human agent when the request cannot be handled within the scope of the agent's actions. |
| AIR-DOM-04c | missing | No policy was extracted from Domain Basic. | **AIR-R010**: The agent must not book a flight, or add a new flight to an existing reservation, unless the flight's status on that date is 'available'. |
| AIR-DOM-04e | missing | No policy was extracted from Domain Basic. | **AIR-R010**: The agent must not book a flight, or add a new flight to an existing reservation, unless the flight's status on that date is 'available'. |
| AIR-BOOK-01a | partial | R2 'User must supply user id, then …' — agent obligation recast as user obligation. | **AIR-R011**: When booking a flight, the agent must obtain the user id first, before collecting the trip type, origin, and destination. |
| AIR-BOOK-01b | partial | R2 imposes a strict order 'trip type, then origin, then destination' that the wiki does not state. | **AIR-R012**: The agent must ask the user for the trip type, origin, and destination before booking a flight. |
| AIR-BOOK-02a | partial | R3 'User must ensure…'. Number 5 correct. | **AIR-R013**: The agent must not book a reservation with more than five passengers. |
| AIR-BOOK-02b | partial | R4 'User must provide for each passenger…' — agent obligation recast. | **AIR-R014**: The agent must collect the first name, last name, and date of birth of every passenger before booking. |
| AIR-BOOK-03a | partial | R29 'the user must not apply…'. Number correct. | **AIR-R016**: The agent must not use more than one travel certificate as payment for a reservation. |
| AIR-BOOK-03b | partial | Number correct. | **AIR-R017**: The agent must not use more than one credit card as payment for a reservation. |
| AIR-BOOK-03c | partial | Number correct. | **AIR-R018**: The agent must not use more than three gift cards as payment for a reservation. |
| AIR-BOOK-04a | partial | Numbers correct, but 'booking user' dropped ('Regular members get…'), so it is ambiguous whose tier applies (passengers have no tier). | **AIR-R020**: When the booking user is a regular member, the agent must set nonfree_baggages to exactly the number of checked bags in excess of the pooled free allowance (number of passengers x per-passenger allowance), with a per-passenger allowance of 0 bags in basic economy, 1 in economy and 2 in business. |
| AIR-BOOK-04b | partial | Numbers correct; 'booking user' dropped. | **AIR-R021**: When the booking user is a silver member, the agent must set nonfree_baggages to exactly the number of checked bags in excess of the pooled free allowance (number of passengers x per-passenger allowance), with a per-passenger allowance of 1 bag in basic economy, 2 in economy and 3 in business. |
| AIR-BOOK-04c | partial | Numbers correct; 'booking user' dropped. | **AIR-R022**: When the booking user is a gold member, the agent must set nonfree_baggages to exactly the number of checked bags in excess of the pooled free allowance (number of passengers x per-passenger allowance), with a per-passenger allowance of 2 bags in basic economy, 3 in economy and 3 in business. |
| AIR-BOOK-05a | partial | R27 'User may opt to purchase travel insurance…' — the agent's obligation to ask is lost (raw r19 still had 'will be asked'); compound with price and coverage. | **AIR-R024**: The agent must ask the user whether they want to buy travel insurance before booking. |
| AIR-MOD-01a | partial | R10 'User must provide user id and reservation id…'. | **AIR-R026**: The agent must obtain the user id before modifying a reservation (flights, cabin, baggage, or passengers). |
| AIR-MOD-01b | partial | Same rule R10. | **AIR-R027**: The agent must obtain the reservation id before modifying a reservation (flights, cabin, baggage, or passengers). |
| AIR-MOD-02a | partial | R11 'User must not modify Basic Economy reservations' — broadened from flights to the whole reservation, contradicting AIR-MOD-03a (BE cabin change allowed) and R14. | **AIR-R028**: The agent must not change the flights of a basic economy reservation; for a basic economy reservation it may only change the cabin while keeping exactly the same flights (flight numbers and dates). |
| AIR-MOD-02b | partial | R12 'User may modify…'. | **AIR-R029**: When changing flights, the agent must keep the reservation's origin and destination unchanged.<br>**AIR-R030**: When changing flights, the agent must keep the reservation's trip type (one way or round trip) unchanged. |
| AIR-MOD-02d | partial | R6 'User must verify all safety rules before making any API call' — wrong subject and over-generalised to all rules / any API call; filed under 'Booking Setup'. | **AIR-R028**: The agent must not change the flights of a basic economy reservation; for a basic economy reservation it may only change the cabin while keeping exactly the same flights (flight numbers and dates).<br>**AIR-R029**: When changing flights, the agent must keep the reservation's origin and destination unchanged.<br>**AIR-R030**: When changing flights, the agent must keep the reservation's trip type (one way or round trip) unchanged. |
| AIR-MOD-03a | partial | R14 'User may apply cabin changes…'. | **AIR-R028**: The agent must not change the flights of a basic economy reservation; for a basic economy reservation it may only change the cabin while keeping exactly the same flights (flight numbers and dates). |
| AIR-MOD-05b | partial | R19 'cannot be modified by anyone' keeps the fact but loses the operational consequence (no transfer), which is an exception to AIR-GEN-05b. | **AIR-R036**: The agent must not transfer the user to a human agent for a request to change the number of passengers. |
| AIR-MOD-06b | partial | R21 'Agent must ask for the payment or refund method' — trigger 'if the flights are changed' dropped. | **AIR-R038**: When changing flights, the agent must ask the user which payment or refund method to use rather than choosing a method itself. |
| AIR-CAN-01a | partial | R7 'User must provide their user id for operations' — cancellation context lost; filed under 'Booking Setup'. | **AIR-R039**: The agent must obtain the user id before cancelling a reservation. |
| AIR-CAN-01b | partial | R8, same problems as R7. | **AIR-R040**: The agent must obtain the reservation id before cancelling a reservation. |
| AIR-CAN-01c | partial | R38 'User must provide the reason' — the reason enumeration is dropped. | **AIR-R041**: The agent must obtain the user's reason for cancellation (change of plan, airline cancelled flight, or other reasons) before cancelling a reservation. |
| AIR-CAN-02c | partial | 'the condition is met' left ungrounded; never linked to the insurance coverage (health or weather, AIR-BOOK-05c). | **AIR-R042**: The agent must not cancel a basic economy or economy reservation unless it was created within the 24 hours before the current time, the airline cancelled a flight in the reservation, or travel insurance was bought and the cancellation reason is covered by it (health or weather). |
| AIR-COMP-01a | partial | Refined R45 'experiences a cancelled flight' drops the complaint trigger; raw r45 additionally invents 'and wants to change or cancel' (copied from the delayed-flight clause). | **AIR-R045**: The agent must not send a certificate to a user who is a regular member, has no travel insurance on the reservation, and flies basic economy or economy in it.<br>**AIR-R046**: The agent must not offer or send compensation unless the user has complained about the situation and explicitly asked for compensation.<br>**AIR-R048**: For a complaint about a cancelled flight, the agent must set the certificate amount to exactly 100 dollars times the number of passengers in the reservation. |
| AIR-COMP-02a | partial | R46 'experiences a delayed flight' drops the complaint trigger and the explicit 'wants to change or cancel' condition. | **AIR-R045**: The agent must not send a certificate to a user who is a regular member, has no travel insurance on the reservation, and flies basic economy or economy in it.<br>**AIR-R046**: The agent must not offer or send compensation unless the user has complained about the situation and explicitly asked for compensation.<br>**AIR-R049**: For a complaint about a delayed flight, the agent must send a certificate only if the user wanted to change or cancel the reservation and only after that change or cancellation has been completed.<br>**AIR-R050**: For a complaint about a delayed flight, the agent must set the certificate amount to exactly 50 dollars times the number of passengers in the reservation. |
| AIR-COMP-03b | incorrect | R37 '…flies basic economy' — '(basic) economy' narrowed to basic economy only; a regular, uninsured economy passenger would wrongly be eligible. | **AIR-R045**: The agent must not send a certificate to a user who is a regular member, has no travel insurance on the reservation, and flies basic economy or economy in it. |

## 4. Reverse check of the extracted refined rules

Every refined rule, its flags, and where it went in the curated set.

| Refined | Category | Extracted text | Flags | Comment | Disposition |
|---|---|---|---|---|---|
| R1 | Booking Setup and Identity | User must be shown action details and must explicitly confirm with 'yes' before any booking update actions. | SUBJ COMPOUND | User-subject; merges listing + confirmation. | split → AIR-R001, AIR-R002 |
| R2 | Booking Setup and Identity | User must supply user id, then trip type, then origin, then destination when initiating a booking. | SUBJ COMPOUND OVERSTRICT | Adds an order among trip type/origin/destination that the wiki does not give. | split → AIR-R011, AIR-R012 |
| R3 | Booking Setup and Identity | User must ensure the reservation includes no more than five passengers. | SUBJ |  | → AIR-R013 |
| R4 | Booking Setup and Identity | User must provide for each passenger: first name, last name, and date of birth. | SUBJ |  | → AIR-R014 |
| R5 | Booking Setup and Identity | All passengers must fly on the same flights and in the same cabin. | ok |  | → AIR-R015 |
| R6 | Booking Setup and Identity | User must verify all safety rules before making any API call. | SUBJ OVERGENERAL MISCATEGORISED | 'all safety rules / any API call'; placed under Booking Setup. | folded into AIR-R028–R030 (AIR-MOD-02d) |
| R7 | Booking Setup and Identity | User must provide their user id for operations. | SUBJ SCOPE MISCATEGORISED | 'for operations' — cancellation context lost. | → AIR-R039 |
| R8 | Booking Setup and Identity | User must provide the reservation id for operations. | SUBJ SCOPE MISCATEGORISED | Same as R7. | → AIR-R040 |
| R9 | Booking Setup and Identity | User must rely only on information, knowledge, or procedures provided by TauBench or available tools; do not request information not provided. | SUBJ INVERTED HALLUCINATED-PART | 'provided by TauBench'; invented 'do not request information'. | → AIR-R003 (+ AIR-R004 added) |
| R10 | Modification and Cabin Policy | User must provide user id and reservation id before modifying a flight. | SUBJ COMPOUND |  | split → AIR-R026, AIR-R027 |
| R11 | Modification and Cabin Policy | User must not modify Basic Economy reservations. | SUBJ OVERBROAD | Bans all modification of BE reservations; conflicts with R14. | → AIR-R028 |
| R12 | Modification and Cabin Policy | User may modify Non-Basic Economy reservations, but origin, destination, and trip type must remain unchanged. | SUBJ COMPOUND |  | split → AIR-R029, AIR-R030 |
| R13 | Modification and Cabin Policy | When modifying, some segments may be kept, but prices will not be updated to reflect current price. | FACT | Pricing behaviour of the API, not a constraint. | dropped (clause AIR-MOD-02c kept as fact) |
| R14 | Modification and Cabin Policy | User may apply cabin changes across all flights in a reservation, including Basic Economy, without changing the flights. | SUBJ | Permission; exception to R11. | folded into AIR-R028 |
| R15 | Modification and Cabin Policy | User must pay the difference between the current cabin and the new cabin when changing cabin. | ok |  | → AIR-R031 |
| R16 | Modification and Cabin Policy | After a cabin change, all flights in the reservation must have the same cabin. | ok |  | → AIR-R032 |
| R17 | Modification and Cabin Policy | User must not change cabin for only a single flight segment. | REDUNDANT | Same constraint as R16. | merged into AIR-R032 |
| R18 | Modification and Cabin Policy | User may modify passenger details but must not change the number of passengers. | ok |  | → AIR-R035 |
| R19 | Modification and Cabin Policy | The number of passengers cannot be modified by anyone. | FACT-ONLY | Loses the 'do not transfer' consequence. | → AIR-R036 |
| R20 | Modification and Cabin Policy | If flights are changed, the user must provide a payment method using either one gift card or one credit card. | ok |  | → AIR-R037 |
| R21 | Modification and Cabin Policy | Agent must ask for the payment or refund method. | MISSING-CONDITION | Trigger 'if flights are changed' dropped. | → AIR-R038 |
| R22 | Baggage, Passengers, and Seat Allocations | Regular members get 0 free bags for Basic Economy, 1 free bag for Economy, and 2 free bags for Business per passenger. | SCOPE | 'booking user' dropped. | → AIR-R020 |
| R23 | Baggage, Passengers, and Seat Allocations | Silver members get 1 free bag for Basic Economy, 2 free bags for Economy, and 3 free bags for Business per passenger. | SCOPE |  | → AIR-R021 |
| R24 | Baggage, Passengers, and Seat Allocations | Gold members get 2 free bags for Basic Economy, 3 free bags for Economy, and 3 free bags for Business per passenger. | SCOPE |  | → AIR-R022 |
| R25 | Baggage, Passengers, and Seat Allocations | Each extra baggage costs $50. | ok |  | → AIR-R023 |
| R26 | Baggage, Passengers, and Seat Allocations | User may add checked bags but must not remove existing bags. | ok |  | → AIR-R033 |
| R27 | Insurance, Payments, Certificates, and Refunds | User may opt to purchase travel insurance at $30 per passenger; provides full refund if cancellation due to health or weather. | COMPOUND MODALITY | Ask + price + coverage; obligation to ask lost. | split → AIR-R024, AIR-R025 (+ fact AIR-BOOK-05c) |
| R28 | Insurance, Payments, Certificates, and Refunds | User must not add travel insurance after initial booking. | ok |  | → AIR-R034 |
| R29 | Insurance, Payments, Certificates, and Refunds | Per reservation, the user must not apply more than one travel certificate. | SUBJ |  | → AIR-R016 |
| R30 | Insurance, Payments, Certificates, and Refunds | Per reservation, the user must not apply more than one credit card. | SUBJ |  | → AIR-R017 |
| R31 | Insurance, Payments, Certificates, and Refunds | Per reservation, the user must not apply more than three gift cards. | SUBJ |  | → AIR-R018 |
| R32 | Insurance, Payments, Certificates, and Refunds | Any remaining amount of a travel certificate is non-refundable. | FACT |  | dropped (clause AIR-BOOK-03d kept as fact) |
| R33 | Insurance, Payments, Certificates, and Refunds | All payment methods used must already be in the user's profile. | ok |  | → AIR-R019 |
| R34 | Insurance, Payments, Certificates, and Refunds | Refunds will be processed to the original payment method within 5-7 business days. | FACT |  | dropped (clause AIR-CAN-04 kept as fact) |
| R35 | Insurance, Payments, Certificates, and Refunds | If flights change, payments/refunds may be required via a single gift card or single credit card. | REDUNDANT | Duplicate of R20 (same raw rule 33). | merged into AIR-R037 |
| R36 | Insurance, Payments, Certificates, and Refunds | Do not proactively offer compensation unless the user complains and explicitly asks for compensation. | ok |  | → AIR-R046 |
| R37 | Insurance, Payments, Certificates, and Refunds | Do not compensate if the user is a regular member and has no travel insurance and flies basic economy. | INCORRECT | '(basic) economy' narrowed to basic economy. | → AIR-R045 |
| R38 | Cancellation Policy and Enforcement | User must provide the reason for cancellation. | SUBJ MISSING-ENUM |  | → AIR-R041 |
| R39 | Cancellation Policy and Enforcement | Cancellation is allowed within 24 hours of booking or if the airline cancelled. | ok |  | folded into AIR-R042 |
| R40 | Cancellation Policy and Enforcement | Outside 24 hours and not airline cancelled, Basic Economy or Economy cancellations require travel insurance to be bought and the condition met. | UNDEFINED-CONDITION | 'the condition' ungrounded. | folded into AIR-R042 |
| R41 | Cancellation Policy and Enforcement | Business class flights can always be cancelled. | ok |  | folded into AIR-R042 |
| R42 | Cancellation Policy and Enforcement | Cancellation rules apply to all users regardless of membership; agent must enforce them before API calls. | COMPOUND |  | folded into AIR-R042 |
| R43 | Cancellation Policy and Enforcement | The agent can cancel only an entire trip that has not been flown; if any segments have flown, cancellation cannot be performed and transfer is needed. | COMPOUND | Cancellation ban + transfer obligation. | split → AIR-R043, AIR-R044 |
| R44 | Cancellation Policy and Enforcement | If any flight segment has been flown, the user cannot cancel and must be transferred. | REDUNDANT SUBJ | Duplicate of R43. | merged into AIR-R043/R044 |
| R45 | Compensation and Gestures | If the user is a silver or gold member or has travel insurance or flies business and experiences a cancelled flight, the agent can offer a gesture certificate equal to 100 times the number of passengers after confirming facts. | WEAKENED-TRIGGER COMPOUND | 'experiences' instead of 'complains'. | split → AIR-R045–R048 |
| R46 | Compensation and Gestures | If the user is a silver or gold member or has travel insurance or flies business and experiences a delayed flight, the agent can offer a gesture certificate equal to 50 times the number of passengers after confirming facts and making the change or cancellation. | WEAKENED-TRIGGER COMPOUND | 'experiences'; 'wants to change or cancel' only implicit. | split → AIR-R045–R047, AIR-R049, AIR-R050 |
| R47 | Handover, Tools, and Compliance | During interactions, the user must not trigger more than one external tool call at a time and must wait for the tool result before submitting another. | SUBJ PARTIAL | User-subject; simultaneous-response half missing. | → AIR-R005 (+ AIR-R006 added) |
| R48 | Handover, Tools, and Compliance | The user must not submit requests that violate any policy; such requests will be denied. | SUBJ |  | → AIR-R007 |
| R49 | Handover, Tools, and Compliance | If a user request cannot be handled within the defined scope, the user will be transferred to a human agent. | SUBJ MODALITY | 'if and only if' weakened to 'if'. | split → AIR-R008, AIR-R009 |

Flag counts: SUBJ 20, COMPOUND 9, SCOPE 5, MISCATEGORISED 3, FACT 3, REDUNDANT 3, MODALITY 2, WEAKENED-TRIGGER 2, OVERSTRICT 1, OVERGENERAL 1, INVERTED 1, HALLUCINATED-PART 1, OVERBROAD 1, FACT-ONLY 1, MISSING-CONDITION 1, INCORRECT 1, MISSING-ENUM 1, UNDEFINED-CONDITION 1, PARTIAL 1; refined rules with no flag: 12.

## 5. Curated rule set (overview)

The full records, with `wiki_quote`, `notes` and extracted ids, are in the JSON file.

| Rule | Description | Sources | Origin | Tools | Verification types |
|---|---|---|---|---|---|
| AIR-R001 | The agent must list the action details to the user before calling any tool that updates the booking database (booking, cancelling, changing flights or cabin, editing baggage, or updating passengers). | AIR-GEN-01a | modified | book_reservation, cancel_reservation, update_reservation_flights, update_reservation_baggages, update_reservation_passengers | dialogue |
| AIR-R002 | The agent must obtain an explicit 'yes' from the user, given after the action details were listed, before calling any tool that updates the booking database. | AIR-GEN-01b | modified | book_reservation, cancel_reservation, update_reservation_flights, update_reservation_baggages, update_reservation_passengers | dialogue |
| AIR-R003 | The agent must not provide information, knowledge, or procedures that were not provided by the user or by the available tools. | AIR-GEN-02a | modified | respond_to_user | dialogue |
| AIR-R004 | The agent must not give subjective recommendations or comments. | AIR-GEN-02b | added | respond_to_user | dialogue |
| AIR-R005 | The agent must make at most one tool call per turn. | AIR-GEN-03a | modified | * | structural |
| AIR-R006 | The agent must not respond to the user and make a tool call in the same turn. | AIR-GEN-03b, AIR-GEN-03c | added | *, respond_to_user | structural |
| AIR-R007 | The agent must deny (refuse to carry out) user requests that are against this policy. | AIR-GEN-04 | modified | *, respond_to_user | dialogue |
| AIR-R008 | The agent must not transfer the user to a human agent unless the request cannot be handled within the scope of the agent's actions or the user explicitly asks for a human agent. | AIR-GEN-05a, AIR-CTX-02 | tool_spec | transfer_to_human_agents | dialogue |
| AIR-R009 | The agent must transfer the user to a human agent when the request cannot be handled within the scope of the agent's actions. | AIR-GEN-05b, AIR-CTX-02 | modified | transfer_to_human_agents, respond_to_user | dialogue |
| AIR-R010 | The agent must not book a flight, or add a new flight to an existing reservation, unless the flight's status on that date is 'available'. | AIR-DOM-04c, AIR-DOM-04e, AIR-DOM-04b, AIR-DOM-04d | interpretation | book_reservation, update_reservation_flights | state |
| AIR-R011 | When booking a flight, the agent must obtain the user id first, before collecting the trip type, origin, and destination. | AIR-BOOK-01a | modified | book_reservation | dialogue |
| AIR-R012 | The agent must ask the user for the trip type, origin, and destination before booking a flight. | AIR-BOOK-01b | modified | book_reservation | dialogue |
| AIR-R013 | The agent must not book a reservation with more than five passengers. | AIR-BOOK-02a | extracted | book_reservation | state |
| AIR-R014 | The agent must collect the first name, last name, and date of birth of every passenger before booking. | AIR-BOOK-02b | extracted | book_reservation | state |
| AIR-R015 | The agent must book all passengers of a reservation on the same flights in the same cabin. | AIR-BOOK-02c | extracted | book_reservation | state |
| AIR-R016 | The agent must not use more than one travel certificate as payment for a reservation. | AIR-BOOK-03a | extracted | book_reservation | state |
| AIR-R017 | The agent must not use more than one credit card as payment for a reservation. | AIR-BOOK-03b | extracted | book_reservation | state |
| AIR-R018 | The agent must not use more than three gift cards as payment for a reservation. | AIR-BOOK-03c | extracted | book_reservation | state |
| AIR-R019 | The agent must only use payment methods that already exist in the user's profile when booking. | AIR-BOOK-03e | extracted | book_reservation | state |
| AIR-R020 | When the booking user is a regular member, the agent must set nonfree_baggages to exactly the number of checked bags in excess of the pooled free allowance (number of passengers x per-passenger allowance), with a per-passenger allowance of 0 bags in basic economy, 1 in economy and 2 in business. | AIR-BOOK-04a | interpretation | book_reservation, update_reservation_baggages | state |
| AIR-R021 | When the booking user is a silver member, the agent must set nonfree_baggages to exactly the number of checked bags in excess of the pooled free allowance (number of passengers x per-passenger allowance), with a per-passenger allowance of 1 bag in basic economy, 2 in economy and 3 in business. | AIR-BOOK-04b | interpretation | book_reservation, update_reservation_baggages | state |
| AIR-R022 | When the booking user is a gold member, the agent must set nonfree_baggages to exactly the number of checked bags in excess of the pooled free allowance (number of passengers x per-passenger allowance), with a per-passenger allowance of 2 bags in basic economy, 3 in economy and 3 in business. | AIR-BOOK-04c | interpretation | book_reservation, update_reservation_baggages | state |
| AIR-R023 | The agent must charge 50 dollars for each extra (non-free) checked bag. | AIR-BOOK-04d | extracted | book_reservation, update_reservation_baggages | state |
| AIR-R024 | The agent must ask the user whether they want to buy travel insurance before booking. | AIR-BOOK-05a | modified | book_reservation | dialogue |
| AIR-R025 | The agent must charge travel insurance at 30 dollars per passenger when the user buys it. | AIR-BOOK-05b | modified | book_reservation | state |
| AIR-R026 | The agent must obtain the user id before modifying a reservation (flights, cabin, baggage, or passengers). | AIR-MOD-01a | modified | update_reservation_flights, update_reservation_baggages, update_reservation_passengers | tool_log, state |
| AIR-R027 | The agent must obtain the reservation id before modifying a reservation (flights, cabin, baggage, or passengers). | AIR-MOD-01b | modified | update_reservation_flights, update_reservation_baggages, update_reservation_passengers | tool_log |
| AIR-R028 | The agent must not change the flights of a basic economy reservation; for a basic economy reservation it may only change the cabin while keeping exactly the same flights (flight numbers and dates). | AIR-MOD-02a, AIR-MOD-02d, AIR-MOD-03a | modified | update_reservation_flights | state |
| AIR-R029 | When changing flights, the agent must keep the reservation's origin and destination unchanged. | AIR-MOD-02b, AIR-MOD-02d | modified | update_reservation_flights | state |
| AIR-R030 | When changing flights, the agent must keep the reservation's trip type (one way or round trip) unchanged. | AIR-MOD-02b, AIR-MOD-02d, AIR-DOM-02 | modified | update_reservation_flights | state |
| AIR-R031 | When changing the cabin of a reservation, the agent must charge the user the price difference between the current and the new cabin class and must not waive it. | AIR-MOD-03b | extracted | update_reservation_flights | dialogue |
| AIR-R032 | The agent must apply a cabin change to all flights in the reservation and must not change the cabin of only some flight segments. | AIR-MOD-03c, AIR-MOD-03d | extracted | update_reservation_flights | state |
| AIR-R033 | The agent must not remove checked bags from a reservation: the new total number of checked bags must not be lower than the current total. | AIR-MOD-04a | extracted | update_reservation_baggages | state |
| AIR-R034 | The agent must not add travel insurance to a reservation after it has been booked. | AIR-MOD-04b | extracted | respond_to_user | dialogue |
| AIR-R035 | The agent must not change the number of passengers in a reservation: an updated passenger list must have the same number of passengers as the current list. | AIR-MOD-05a | extracted | update_reservation_passengers | state |
| AIR-R036 | The agent must not transfer the user to a human agent for a request to change the number of passengers. | AIR-MOD-05b | modified | transfer_to_human_agents | dialogue |
| AIR-R037 | When changing flights, the agent must use exactly one payment method, which must be a gift card or a credit card from the user's profile (not a travel certificate). | AIR-MOD-06a | extracted | update_reservation_flights | state |
| AIR-R038 | When changing flights, the agent must ask the user which payment or refund method to use rather than choosing a method itself. | AIR-MOD-06b | modified | update_reservation_flights | state, dialogue |
| AIR-R039 | The agent must obtain the user id before cancelling a reservation. | AIR-CAN-01a | modified | cancel_reservation | tool_log, state |
| AIR-R040 | The agent must obtain the reservation id before cancelling a reservation. | AIR-CAN-01b | modified | cancel_reservation | tool_log |
| AIR-R041 | The agent must obtain the user's reason for cancellation (change of plan, airline cancelled flight, or other reasons) before cancelling a reservation. | AIR-CAN-01c | modified | cancel_reservation | dialogue |
| AIR-R042 | The agent must not cancel a basic economy or economy reservation unless it was created within the 24 hours before the current time, the airline cancelled a flight in the reservation, or travel insurance was bought and the cancellation reason is covered by it (health or weather). | AIR-CAN-02a, AIR-CAN-02b, AIR-CAN-02c, AIR-CAN-02d, AIR-CAN-02e, AIR-CAN-02f, AIR-BOOK-05c, AIR-CTX-01 | modified | cancel_reservation | state, dialogue |
| AIR-R043 | The agent must not cancel a reservation in which any flight segment has already been flown. | AIR-CAN-03a | extracted | cancel_reservation | state |
| AIR-R044 | If the user asks to cancel a reservation in which any flight segment has already been flown, the agent must transfer the user to a human agent. | AIR-CAN-03b | modified | transfer_to_human_agents, respond_to_user | state, dialogue |
| AIR-R045 | The agent must not send a certificate to a user who is a regular member, has no travel insurance on the reservation, and flies basic economy or economy in it. | AIR-COMP-03b, AIR-COMP-01a, AIR-COMP-02a | modified | send_certificate | state |
| AIR-R046 | The agent must not offer or send compensation unless the user has complained about the situation and explicitly asked for compensation. | AIR-COMP-03a, AIR-COMP-01a, AIR-COMP-02a | extracted | respond_to_user, send_certificate | dialogue |
| AIR-R047 | The agent must confirm the facts (that the flight in the user's reservation was actually cancelled or delayed, verified via tool lookups) before offering or sending a certificate. | AIR-COMP-01b, AIR-COMP-02b | modified | send_certificate, respond_to_user | tool_log |
| AIR-R048 | For a complaint about a cancelled flight, the agent must set the certificate amount to exactly 100 dollars times the number of passengers in the reservation. | AIR-COMP-01c, AIR-COMP-01a | modified | send_certificate | state, dialogue |
| AIR-R049 | For a complaint about a delayed flight, the agent must send a certificate only if the user wanted to change or cancel the reservation and only after that change or cancellation has been completed. | AIR-COMP-02a, AIR-COMP-02b | modified | send_certificate | tool_log, dialogue |
| AIR-R050 | For a complaint about a delayed flight, the agent must set the certificate amount to exactly 50 dollars times the number of passengers in the reservation. | AIR-COMP-02c, AIR-COMP-02a | modified | send_certificate | state, dialogue |


## 6. Exact-value check

| Value | Wiki | Extracted (refined) | Curated |
|---|---|---|---|
| Max passengers per reservation | 5 | R3: 5 ✓ | AIR-R013 |
| Travel certificates per reservation | ≤ 1 | R29: ✓ | AIR-R016 |
| Credit cards per reservation | ≤ 1 | R30: ✓ | AIR-R017 |
| Gift cards per reservation | ≤ 3 | R31: ✓ | AIR-R018 |
| Free bags, regular (BE / E / B) | 0 / 1 / 2 | R22: ✓ ("booking user" lost) | AIR-R020 |
| Free bags, silver | 1 / 2 / 3 | R23: ✓ (same) | AIR-R021 |
| Free bags, gold | 2 / 3 / 3 | R24: ✓ (same) | AIR-R022 |
| Extra bag | $50 each | R25: ✓ | AIR-R023 |
| Insurance | $30 per passenger | R27: ✓ | AIR-R025 |
| Insurance coverage | health or weather | R27: ✓, but **not linked** to the cancellation rule (R40 says "the condition") | AIR-R042 |
| Cancellation window | 24 h from booking; now = 2024-05-15 15:00:00 EST | R39: "24 hours" ✓; current time not extracted | AIR-R042: created_at ≥ 2024-05-14 15:00:00 |
| Cancellation reasons | change of plan / airline cancelled flight / other reasons | R38: **enumeration dropped** | AIR-R041 |
| Cancellable without exception | business | R41: ✓ | AIR-R042 (scope) |
| Compensation eligibility | silver/gold OR insurance OR business | R45/R46: ✓ | AIR-R045 |
| Compensation exclusion | regular AND no insurance AND **(basic) economy** | R37: **basic economy only ✗** | AIR-R045 |
| Certificate, cancelled flight | $100 × passengers | R45: "100 times" ✓ (unit dropped) | AIR-R048 |
| Certificate, delayed flight | $50 × passengers | R46: "50 times" ✓ (unit dropped) | AIR-R050 |
| Non-bookable flight statuses | delayed, on time, flying | **not extracted** | AIR-R010 |
| Trip types | one way, round trip | R12: "trip type" ✓ | AIR-R030 |
| Payment for flight change | one gift card or credit card | R20: ✓ | AIR-R037 |
| Refund timing | 5 to 7 business days | R34: ✓ (fact) | fact AIR-CAN-04 |

The validator's only warning is the derived date `2024-05-14` in AIR-R042, which is 24 h before the fixed current time. This is intended.

## 7. Systemic observations

1. **Target subject.** The run used the CLI default `target_subject="User"`. The prompts in `utility/policy_server.py` say "only include constraints on the behaviors of the target subject" (l. 827) and "Format rules from the perspective of '{target_subject} must/must not…'" (l. 1395). The τ-bench wiki addresses **the agent** ("you", "the agent"). This produced three effects:
   - 25 of 49 refined rules read "User must…" or "the user …";
   - agent duties were transferred to the user, e.g. R47 "the user must not trigger more than one external tool call", R2 "User must supply user id…", R6 "User must verify all safety rules before making any API call";
   - agent-only duties with no plausible user reading were **dropped**: no subjective comments, and no response and tool call in the same turn.

   This is a systemic issue, not a one-off. A few wiki sentences genuinely address the user ("The user can add but not remove checked bags", "Cabin changes require the user to pay…"). Those extractions are faithful and are marked `covered`.
2. **Typical gpt-5-nano failure modes seen here.**
   - Modality weakening: "if and only if" became "if" (R49); "the agent should ask" became "User may opt" (R27).
   - Lost qualifiers: "booking user" in the bag table; "if the flights are changed" (R21); the cancellation context in R7/R8.
   - Narrowed enumerations: "(basic) economy" became "basic economy" (R37).
   - Dropped enumerations: cancellation reasons (R38).
   - Ungrounded anaphora: "the condition is met" (R40).
   - Over-broadening: "BE flights" became "BE reservations" (R11).
   - Over-strict ordering: R2.
   - Conditions copied between neighbouring clauses: raw r45 gained "and wants to change or cancel" from the delayed-flight clause.
   - Whole section skipped: *Domain Basic*.
   - Facts emitted as rules: R13, R32, R34.

   **Numbers were never altered.**
3. **Refinement stage.** The single "decompose + merge + categorise" call barely changed the raw rules: 48 raw rules became 49 refined, and only R35 was a new near-duplicate. It did not merge redundancies (R16/R17, R43/R44) and it placed several rules in odd categories (R6–R8 under "Booking Setup and Identity"). The paper's iterative verifiability and redundancy loop is absent (as stated in the brief), and it shows.
4. **Traceability artefacts.** Every raw rule has an empty `source_policies`; the link is carried by `source_policy_idx`. `TauBench_policy_rule_mapping.json` is keyed on *refined* rule ids and is consistent. The document tree is empty (`children: []`) even though 23 policies were extracted.
5. **Compound rules.** Several refined rules bundle 2–3 obligations (R1, R2, R10, R12, R27, R43, R45, R46). The curated set splits them, so that each rule maps to a single implication in Step 2.

## 8. Ambiguities, read literally and recorded in `notes`

The **Decision** lines were added at Step 1 close-out (Step 2 Part A, 2026-10-14). Items without a decision keep the literal reading.

1. **Confirmation scope (AIR-R001/R002).** The parenthetical list omits cancellation. `cancel_reservation` is included because it updates the booking database. `send_certificate` is excluded.
   **Decision (A1.4):** kept as is. The cancellation part is an *interpretation*, so it is an ablation candidate.
2. **Transfer (AIR-R008/R009).** The τ-bench tool description adds "if the user explicitly asks for a human". The wiki does not, so the wiki is followed. Precedence: requests against policy are denied, not transferred (AIR-R007). A passenger-count change is never transferred (AIR-R036). A cancellation with a flown segment is always transferred (AIR-R044).
   **Decision (A1.3):** a transfer is allowed iff the request is out of scope **or** the user explicitly asks for a human. The second disjunct is `origin: tool_spec`. AIR-R007 and AIR-R036 keep precedence over the explicit-request permission.
3. **Flight statuses (AIR-R010).** τ-bench data also uses `landed` and `cancelled`, and the wiki never lists them. The rule follows the literal list. A stricter "only `available`" reading is open.
   **Decision (A1.2):** AIR-R010 now allows booking only when the status is `available` (`origin: interpretation`). The API enforces the same check.
4. **Bag table on later additions (AIR-R020–R023).** The table sits under *Book flight*. Applying it to `update_reservation_baggages` is an interpretation.
   **Decision (A2.7):** AIR-R020–R022 now require **exact equality**: `nonfree_baggages` must equal the bags in excess of the pooled allowance (`origin: interpretation`; pooling across passengers is assumed). The tool source confirms both counts are reservation-level totals.
5. **Basic economy after an upgrade (AIR-R028).** Once the cabin has been upgraded, the reservation is no longer basic economy. The wiki is silent on whether flights may then be changed.
6. **"instead" (AIR-R038).** Read as "instead of the agent choosing the method".
7. **"the condition is met" (AIR-R042).** Read as the insurance condition (health or weather).
8. **24 h boundary (AIR-R042).** Read as inclusive. `created_at` has no timezone and is assumed to be EST.
   **Decision (A2.6):** the hard-coded date was removed from AIR-R042. The current time is `policies/curated/airline_config.json:current_time`, which the validator checks against AIR-CTX-01.
9. **"airline cancelled the flight" (AIR-R042).** Read as a segment whose flight status is `cancelled`.
   **Finding (Step 2 B0):** no τ-bench v1 airline tool exposes a non-`available` flight status, so this fact can come only from the dialogue. See `policies/tau_bench/airline_data_notes.md`.
10. **"flown" (AIR-R043).** Read as status `flying` or `landed`, or a date before today.
11. **Removing bags (AIR-R033).** Only `total_baggages` is constrained. Whether `nonfree_baggages` may decrease is not stated.
12. **Payment rule scope (AIR-R037).** The rule applies "if the flights are changed". A cabin-only change uses the same tool.
   **Decision (A2.9):** the literal scope is kept. The API rejects certificates for *any* `update_reservation_flights` call (`update_reservation_flights.py:68-69`), so the rule is API-enforced.
13. **AIR-R042 verification type.** It is tagged `deterministic`, but its "reason is health or weather" sub-predicate is semantic.
   **Decision (A2.10):** every rule was re-tagged with the four-way scheme. AIR-R042 is `[state, dialogue]`. The turn-format rules AIR-R005/R006 are `structural` (A2.8).

## 9. Recommendations for re-running extraction

A re-run is **not required for Step 2**. The curated set is now the source of truth for the ASPM. A re-run is worth doing only if we want to report how well the *automatic* pipeline does, as a paper-style ablation. In that case:

1. Run with `-ts "Agent"` (or "customer service agent") and with `-org-desc` describing the τ-bench setting: "rules constrain an LLM customer-service agent's tool calls and messages". Note bug #8: `organization_description` is not passed to the agent constructor, so check that it actually reaches the prompts.
2. Record `target_subject`, `model` and `org_desc` in `*_extraction_report.json`. Today they are not stored at all.
3. Use this audit as a regression test: score a new extraction against `policies/curated/airline_clauses.json`, measuring per-clause coverage. A small scorer over `extraction_audit` is enough.
4. Prompt changes worth testing:
   - "preserve modality (only if / if and only if) and enumerations verbatim";
   - "separate domain facts from constraints";
   - "do not drop clauses that constrain the agent";
   - a real dedup pass in the refinement step.
5. Consider a stronger extraction model. The wikis are short, so cost is negligible, and gpt-5-nano's errors here are qualitative, not numeric.

## 10. Validation output

`python scripts/validate_curated_rules.py` (default `--curated-dir policies/curated`; run 2026-10-14 after the Step 1 close-out, both domains):

```text
[airline] clauses=73 normative=61 normative_covered=61/61 rules=50
  => PASS (0 failures, 0 warnings)
[retail] clauses=58 normative=46 normative_covered=46/46 rules=31
  => PASS (0 failures, 0 warnings)
OVERALL: PASS
```

## 11. Step 1 close-out changes (Step 2 Part A, 2026-10-14)

Rules whose description, origin or notes changed in the close-out. The `verification_type` of **every** rule was also re-tagged with the four-way scheme (state / tool_log / structural / dialogue); see §5.

| Rule | Decision | Before | After |
|---|---|---|---|
| AIR-R001 | A1.4 | The agent must list the action details to the user before calling any tool that updates the booking database (booking, cancelling, changing flights or cabin, editing baggage, or updating passengers). *(origin: modified; type: temporal)* | description unchanged; note added *(origin: modified; types: dialogue)* |
| AIR-R002 | A1.4 | The agent must obtain an explicit 'yes' from the user, given after the action details were listed, before calling any tool that updates the booking database. *(origin: modified; type: temporal)* | description unchanged; note added *(origin: modified; types: dialogue)* |
| AIR-R005 | A2.8 | The agent must make at most one tool call per turn. *(origin: modified; type: temporal)* | description unchanged; note added *(origin: modified; types: structural)* |
| AIR-R006 | A2.8 | The agent must not respond to the user and make a tool call in the same turn. *(origin: added; type: temporal)* | description unchanged; note added *(origin: added; types: structural)* |
| AIR-R008 | A1.3 | The agent must not transfer the user to a human agent unless the request cannot be handled within the scope of the agent's actions. *(origin: modified; type: semantic)* | The agent must not transfer the user to a human agent unless the request cannot be handled within the scope of the agent's actions or the user explicitly asks for a human agent. *(origin: tool_spec; types: dialogue)* |
| AIR-R009 | A1.3 | The agent must transfer the user to a human agent when the request cannot be handled within the scope of the agent's actions. *(origin: modified; type: semantic)* | description unchanged; note added *(origin: modified; types: dialogue)* |
| AIR-R010 | A1.2 | The agent must not book a flight on a date whose status is 'delayed', 'on time', or 'flying', including when adding a new flight to an existing reservation. *(origin: added; type: deterministic)* | The agent must not book a flight, or add a new flight to an existing reservation, unless the flight's status on that date is 'available'. *(origin: interpretation; types: state)* |
| AIR-R020 | A2.7 | When the booking user is a regular member, the agent must count 0 free checked bags per basic economy passenger, 1 per economy passenger, and 2 per business passenger, and must treat every additional bag as non-free. *(origin: modified; type: deterministic)* | When the booking user is a regular member, the agent must set nonfree_baggages to exactly the number of checked bags in excess of the pooled free allowance (number of passengers x per-passenger allowance), with a per-passenger allowance of 0 bags in basic economy, 1 in economy and 2 in business. *(origin: interpretation; types: state)* |
| AIR-R021 | A2.7 | When the booking user is a silver member, the agent must count 1 free checked bag per basic economy passenger, 2 per economy passenger, and 3 per business passenger, and must treat every additional bag as non-free. *(origin: modified; type: deterministic)* | When the booking user is a silver member, the agent must set nonfree_baggages to exactly the number of checked bags in excess of the pooled free allowance (number of passengers x per-passenger allowance), with a per-passenger allowance of 1 bag in basic economy, 2 in economy and 3 in business. *(origin: interpretation; types: state)* |
| AIR-R022 | A2.7 | When the booking user is a gold member, the agent must count 2 free checked bags per basic economy passenger, 3 per economy passenger, and 3 per business passenger, and must treat every additional bag as non-free. *(origin: modified; type: deterministic)* | When the booking user is a gold member, the agent must set nonfree_baggages to exactly the number of checked bags in excess of the pooled free allowance (number of passengers x per-passenger allowance), with a per-passenger allowance of 2 bags in basic economy, 3 in economy and 3 in business. *(origin: interpretation; types: state)* |
| AIR-R037 | A2.9 | When changing flights, the agent must use exactly one payment method, which must be a gift card or a credit card from the user's profile (not a travel certificate). *(origin: extracted; type: deterministic)* | description unchanged; note added *(origin: extracted; types: state)* |
| AIR-R042 | A2.6 | The agent must not cancel a basic economy or economy reservation unless it was booked within the last 24 hours (created at or after 2024-05-14 15:00:00 EST), the airline cancelled a flight in the reservation, or travel insurance was bought and the cancellation reason is covered by it (health or weather). *(origin: modified; type: deterministic)* | The agent must not cancel a basic economy or economy reservation unless it was created within the 24 hours before the current time, the airline cancelled a flight in the reservation, or travel insurance was bought and the cancellation reason is covered by it (health or weather). *(origin: modified; types: state, dialogue)* |
