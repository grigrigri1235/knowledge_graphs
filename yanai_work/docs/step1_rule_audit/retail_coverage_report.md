# Step 1: rule coverage audit, retail domain

| | |
|---|---|
| Ground truth | `output/deep_policy/extraction_20261012_120408/retail_wiki.txt`, byte-identical to `policy_docs/retail_wiki.txt` and to τ-bench `tau_bench/envs/retail/wiki.md` @ `59a200c`. |
| Audited extraction | Same folder: `TauBench_Retail_all_extracted_policies.json` (18), `…_all_extracted_rules.json` (26 raw), `…_risk_categories.json` (5 categories, **104 refined, 57 unique texts**), `…_policy_rule_mapping.json`. Extracted by gpt-5-nano, `target_subject="User"` (CLI default). |
| Deliverables | `policies/curated/retail_clauses.json`, `policies/curated/retail_curated_rules.json`, `policies/curated/retail_config.json`, `scripts/validate_curated_rules.py`. These moved from `output/curated/` (git-ignored, now superseded; archived at `archive/step1_gold_standard/data/output_curated/` in the 2026-10-17 cleanup) at Step 1 close-out. |
| Method | Manual, clause-by-clause reading of the wiki, by me. No LLM was used for any judgment. Clause texts and quotes are checked by the validator to be verbatim wiki text. Wiki of record: `policy_docs/retail_wiki.txt` (sha256 checked). |

## Headline

- **Before:** 27 of 46 normative clauses were fully covered (30 if subject phrasing is ignored). 11 were partial, **2 incorrect, 6 missing**. **After:** 46 of 46 are covered by 31 curated rules. The validator passes.
- The refined set is **heavily duplicated**:
  - 104 rules, but only 57 distinct texts;
  - category "Identity, Access Control, and Conversation Scope" holds 55 rules, including returns and exchanges;
  - "Order Modifications…" repeats 40 of them verbatim;
  - "Timezone…" and "Confirmation…" repeat others.
- The two **incorrect** rules:
  - **Return refund destination** (R44/R45): "original payment method **or** an existing gift card" became two unconditional statements, which no longer restrict anything.
  - **No subjective recommendations** (R64): inverted into "do not *accept* subjective guidance".
- The six **missing** clauses:
  - authentication "even when the user already provides the user id";
  - "product ids and item ids … should not be confused";
  - "check its status before taking the action" for **modify, return and exchange** (kept only for cancel);
  - "remind the customer to confirm they have provided all items" for **modify items**.
- **Invented content:**
  - six rules (R11–R13 and duplicates R56–R58) turn the database-timezone *fact* into display requirements ("times presented to the user must be in EST / 24-hour format");
  - R10/R62 add "Otherwise continue with automated handling".
- Numbers and enumerations are mostly right: cancellation reasons, pending/delivered, gift-card balance thresholds. One exception: the status string `'pending (items modifed)'` was silently "corrected" to `'pending (items modified)'`, which matches neither the wiki nor the τ-bench API (`'pending (item modified)'`).

## 1. Summary counts

Clauses: **58** (46 normative, 12 facts). Extracted refined rules: 104. Curated rules: **31**.

| Status (normative clauses) | Before — strict | Before — content only (ignoring subject phrasing) | After curation |
|---|---|---|---|
| covered | 27 | 30 | 46 |
| partial | 11 | 8 | 0 |
| incorrect | 2 | 2 | 0 |
| missing | 6 | 6 | 0 |
| **total** | 46 | 46 | 46 |

Curated rules by origin: extracted 12, modified 16, added 2, interpretation 0, tool_spec 1. Rules needing each data type (a rule can need several): state 12, tool_log 5, structural 2, dialogue 14.

Origin legend: *extracted* = the extracted rule's content is kept and only rephrased as an agent obligation; *modified* = conditions, scope or numbers were changed, or the rule was split or merged; *added* = no extracted rule existed; *interpretation* = a reading the wiki does not force, adopted at Step 1 close-out; *tool_spec* = includes a condition taken from the τ-bench tool description.

## 2. Traceability matrix

`Refined` = rule ids in `*_risk_categories.json`; `Raw` = ids in `*_all_extracted_rules.json`. Issue tags: SUBJ wrong subject (user instead of agent) · COND condition dropped, added, or ungrounded · MODAL weakened modality · SCOPE wrong scope · NUM wrong number/enumeration · INV inverted meaning · HALL invented content · MERGE compound · DUP duplicated · DROP not extracted.

| Clause | L | Kind | Verbatim wiki text | Refined | Raw | Before | Issues | Curated rules (after) |
|---|---|---|---|---|---|---|---|---|
| RET-CTX-01 | 3 | F | As a retail agent, you can help users cancel or modify pending orders, return or exchange delivered orders, modify their default user address, or provide information about their own profile, orders, and related products. | — | — | n/a (fact) | — | RET-R002, RET-R010, RET-R011 |
| RET-GEN-01a | 5 | N | At the beginning of the conversation, you have to authenticate the user identity by locating their user id via email, or via name + zip code. | 1 | 1 | partial | SUBJ SCOPE | RET-R001 |
| RET-GEN-01b | 5 | N | This has to be done even when the user already provides the user id. | — | — | missing | DROP | RET-R001 |
| RET-GEN-02 | 7 | N | Once the user has been authenticated, you can provide the user with information about order, product, profile information, e.g. help the user look up order id. | 2, 3, 4 | 2 | partial (content: covered) | SUBJ | RET-R001 |
| RET-GEN-03a | 9 | N | You can only help one user per conversation (but you can handle multiple requests from the same user) | 5 | 3 | covered | — | RET-R002 |
| RET-GEN-03b | 9 | N | and must deny any requests for tasks related to any other user. | 5, 6 | 3 | covered | DUP | RET-R003 |
| RET-GEN-04a | 11 | N | Before taking consequential actions that update the database (cancel, modify, return, exchange), you have to list the action detail | 59 | 4 | covered | — | RET-R004 |
| RET-GEN-04b | 11 | N | obtain explicit user confirmation (yes) to proceed. | 60 | 4 | covered | — | RET-R005 |
| RET-GEN-05a | 13 | N | You should not make up any information or knowledge or procedures not provided from the user or the tools | 63 | 5 | partial | MODAL | RET-R006 |
| RET-GEN-05b | 13 | N | or give subjective recommendations or comments. | 64 | 5 | incorrect | INV | RET-R007 |
| RET-GEN-06a | 15 | N | You should at most make one tool call at a time | 7 | 6 | partial (content: covered) | SUBJ | RET-R008 |
| RET-GEN-06b | 15 | N | if you take a tool call, you should not respond to the user at the same time. | 8 | 6 | covered | — | RET-R009 |
| RET-GEN-06c | 15 | N | If you respond to the user, you should not make a tool call. | 8 | 6 | covered | — | RET-R009 |
| RET-GEN-07a | 17 | N | You should transfer the user to a human agent if and only if the request cannot be handled within the scope of your actions. | 9, 61 | 7 | covered | DUP | RET-R010 |
| RET-GEN-07b | 17 | N | You should transfer the user to a human agent if and only if the request cannot be handled within the scope of your actions. | 9, 10 | 7 | partial | MODAL HALL | RET-R011 |
| RET-DOM-01 | 21 | F | All times in the database are EST and 24 hour based. For example "02:30:00" means 2:30 AM EST. | 11, 12, 13, 56, 57, 58 | 8 | n/a (fact) | — | — |
| RET-DOM-02 | 23 | F | Each user has a profile of its email, default address, user id, and payment methods. Each payment method is either a gift card, a paypal account, or a credit card. | — | — | n/a (fact) | — | — |
| RET-DOM-03 | 25 | F | Our retail store has 50 types of products. For each type of product, there are variant items of different options. For example, for a 't shirt' product, there could be an item with option 'color blue size M', and another item with option 'color red size L'. | — | — | n/a (fact) | — | — |
| RET-DOM-04a | 27 | F | Each product has an unique product id, and each item has an unique item id. | — | — | n/a (fact) | — | RET-R012 |
| RET-DOM-04b | 27 | N | They have no relations and should not be confused. | — | — | missing | DROP | RET-R012 |
| RET-DOM-05a | 29 | F | Each order can be in status 'pending', 'processed', 'delivered', or 'cancelled'. | — | 9 | n/a (fact) | — | — |
| RET-DOM-05b | 29 | N | Generally, you can only take action on pending or delivered orders. | 14, 15, 65, 66 | 9 | covered | DUP | RET-R013, RET-R014 |
| RET-DOM-06a | 31 | N | Exchange or modify order tools can only be called once. | 17, 33, 82 | 10, 18 | partial | SCOPE | RET-R016, RET-R017 |
| RET-DOM-06b | 31 | N | Be sure that all items to be changed are collected into a list before making the tool call!!! | 16 | 10 | covered | — | RET-R018 |
| RET-CAN-01a | 35 | N | An order can only be cancelled if its status is 'pending' | 18, 67 | 11 | covered | DUP | RET-R013 |
| RET-CAN-01b | 35 | N | and you should check its status before taking the action. | 19, 68 | 11 | covered | DUP | RET-R015 |
| RET-CAN-02a | 37 | N | The user needs to confirm the order id and the reason | 20, 69 | 12 | partial | MODAL | RET-R020 |
| RET-CAN-02b | 37 | N | (either 'no longer needed' or 'ordered by mistake') for cancellation. | 21, 70 | 12 | covered | DUP | RET-R021 |
| RET-CAN-03 | 39 | F | After user confirmation, the order status will be changed to 'cancelled', and the total will be refunded via the original payment method immediately if it is gift card, otherwise in 5 to 7 business days. | 22, 23, 24, 71, 72, 73 | 13 | n/a (fact) | — | — |
| RET-MOD-01a | 43 | N | An order can only be modified if its status is 'pending' | 25, 74 | 14 | covered | DUP | RET-R013 |
| RET-MOD-01b | 43 | N | and you should check its status before taking the action. | — | 14 | missing | DROP | RET-R015 |
| RET-MOD-02 | 45 | N | For a pending order, you can take actions to modify its shipping address, payment method, or product item options, but nothing else. | 26, 27, 75, 76 | 14 | covered | DUP | RET-R022 |
| RET-MPAY-01 | 49 | N | The user can only choose a single payment method different from the original payment method. | 28, 77 | 15 | partial | COND | RET-R023 |
| RET-MPAY-02 | 51 | N | If the user wants the modify the payment method to gift card, it must have enough balance to cover the total amount. | 29, 78 | 15 | covered | DUP | RET-R024 |
| RET-MPAY-03 | 53 | F | After user confirmation, the order status will be kept 'pending'. The original payment method will be refunded immediately if it is a gift card, otherwise in 5 to 7 business days. | 30, 31, 32, 79, 80, 81 | 16, 17 | n/a (fact) | — | — |
| RET-MITEM-01a | 57 | N | This action can only be called once | 33, 82 | 18 | covered | DUP | RET-R016 |
| RET-MITEM-01b | 57 | F | will change the order status to 'pending (items modifed)' | 35, 84 | 18 | n/a (fact) | — | — |
| RET-MITEM-01c | 57 | N | the agent will not be able to modify or cancel the order anymore | 36, 85 | 18 | covered | DUP | RET-R013 |
| RET-MITEM-01d | 57 | N | So confirm all the details are right and be cautious before taking this action. | 34, 83 | 18 | partial (content: covered) | SUBJ | RET-R005 |
| RET-MITEM-01e | 57 | N | In particular, remember to remind the customer to confirm they have provided all items to be modified. | — | — | missing | DROP | RET-R019 |
| RET-MITEM-02a | 59 | N | For a pending order, each item can be modified to an available new item of the same product but of different product option. | 37, 86 | 19 | covered | DUP | RET-R025, RET-R026, RET-R027 |
| RET-MITEM-02b | 59 | N | There cannot be any change of product types, e.g. modify shirt to shoe. | 38, 87 | 19 | covered | DUP | RET-R025 |
| RET-MITEM-03a | 61 | N | The user must provide a payment method to pay or receive refund of the price difference. | 39, 88 | 20 | partial | COND | RET-R028 |
| RET-MITEM-03b | 61 | N | If the user provides a gift card, it must have enough balance to cover the price difference. | 40, 89 | 20 | covered | DUP | RET-R029 |
| RET-RTN-01a | 65 | N | An order can only be returned if its status is 'delivered' | 41, 90 | 21 | covered | DUP | RET-R014 |
| RET-RTN-01b | 65 | N | and you should check its status before taking the action. | — | 21 | missing | DROP | RET-R015 |
| RET-RTN-02 | 67 | N | The user needs to confirm the order id, the list of items to be returned, and a payment method to receive the refund. | 42, 43, 91, 92 | 21 | covered | DUP | RET-R030 |
| RET-RTN-03 | 69 | N | The refund must either go to the original payment method, or an existing gift card. | 44, 45, 93, 94 | 22 | incorrect | INV MERGE | RET-R031 |
| RET-RTN-04 | 71 | F | After user confirmation, the order status will be changed to 'return requested', and the user will receive an email regarding how to return items. | 46, 47, 95, 96 | 23 | n/a (fact) | — | — |
| RET-EXC-01a | 75 | N | An order can only be exchanged if its status is 'delivered' | 48, 97 | 24 | covered | DUP | RET-R014 |
| RET-EXC-01b | 75 | N | and you should check its status before taking the action. | — | 24 | missing | DROP | RET-R015 |
| RET-EXC-01c | 75 | N | In particular, remember to remind the customer to confirm they have provided all items to be exchanged. | 49, 98 | 24 | partial | SUBJ MODAL | RET-R019 |
| RET-EXC-02a | 77 | N | For a delivered order, each item can be exchanged to an available new item of the same product but of different product option. | 50, 99 | 24 | covered | DUP MERGE | RET-R025, RET-R026, RET-R027 |
| RET-EXC-02b | 77 | N | There cannot be any change of product types, e.g. modify shirt to shoe. | 50, 99 | 24 | covered | DUP | RET-R025 |
| RET-EXC-03a | 79 | N | The user must provide a payment method to pay or receive refund of the price difference. | 51, 100 | 25 | covered | DUP | RET-R028 |
| RET-EXC-03b | 79 | N | If the user provides a gift card, it must have enough balance to cover the price difference. | 52, 101 | 25 | covered | DUP | RET-R029 |
| RET-EXC-04a | 81 | F | After user confirmation, the order status will be changed to 'exchange requested', and the user will receive an email regarding how to return items. | 53, 54, 102, 103 | 26 | n/a (fact) | — | — |
| RET-EXC-04b | 81 | F | There is no need to place a new order. | 55, 104 | 26 | n/a (fact) | — | — |

For clauses whose verbatim text is shared (e.g. one 'if and only if' sentence split into two directions), the atomic reading is in `atomic_reading` in the clauses JSON.

## 3. Issues found, before → after

Every normative clause that was not `covered` before curation:

| Clause | Before | Problem in extracted rule(s) | After (curated) |
|---|---|---|---|
| RET-GEN-01a | partial | R1 'User must provide identifying information … before any consequential actions' — user subject, and 'at the beginning of the conversation' narrowed to 'before consequential actions' (information disclosure no longer gated). | **RET-R001**: The agent must authenticate the user by locating their user id via email (find_user_id_by_email) or via name and zip code (find_user_id_by_name_zip) before any other tool call or any disclosure of profile, order, or product information, even if the user has already provided a user id. |
| RET-GEN-01b | missing | Dropped at raw-rule level. | **RET-R001**: The agent must authenticate the user by locating their user id via email (find_user_id_by_email) or via name and zip code (find_user_id_by_name_zip) before any other tool call or any disclosure of profile, order, or product information, even if the user has already provided a user id. |
| RET-GEN-02 | partial | Recast as 'User may request …' and split into three rules R2–R4. | **RET-R001**: The agent must authenticate the user by locating their user id via email (find_user_id_by_email) or via name and zip code (find_user_id_by_name_zip) before any other tool call or any disclosure of profile, order, or product information, even if the user has already provided a user id. |
| RET-GEN-05a | partial | R63 'Do not rely on information…' — 'make up' (agent output) became 'rely on' (agent input); raw r5 also has the user as subject. | **RET-R006**: The agent must not make up information, knowledge, or procedures that were not provided by the user or by the tools. |
| RET-GEN-05b | incorrect | R64 'Do not request or accept fabricated or subjective guidance' — direction inverted (accepting instead of giving). | **RET-R007**: The agent must not give subjective recommendations or comments. |
| RET-GEN-06a | partial | R7 'The user must wait for the tool result…'. | **RET-R008**: The agent must make at most one tool call per turn. |
| RET-GEN-07b | partial | 'if and only if' weakened to 'only if'; R10/R62 'Otherwise continue with automated handling' is invented filler. | **RET-R011**: The agent must transfer the user to a human agent when the request cannot be handled within the scope of the agent's actions. |
| RET-DOM-04b | missing | Lumped into P8, then dropped. | **RET-R012**: The agent must not confuse product ids with item ids: item ids passed to order tools must be item ids, and get_product_details must be called with a product id. |
| RET-DOM-06a | partial | R17 'Only one tool call is allowed per order action' is garbled; the exchange-once constraint is not captured (modify-items-once is, via R33). | **RET-R016**: The agent must call modify_pending_order_items at most once per order.<br>**RET-R017**: The agent must call exchange_delivered_order_items at most once per order. |
| RET-CAN-02a | partial | R20 'To cancel a pending order, provide the order id' — user confirmation of id and reason lost. | **RET-R020**: Before cancelling an order, the agent must have the user confirm the order id and the cancellation reason. |
| RET-MOD-01b | missing | Status-check obligation only kept for cancellation. | **RET-R015**: The agent must look up the order's current status (get_order_details) before cancelling, modifying, returning, or exchanging it. |
| RET-MPAY-01 | partial | R28 'may choose a single new payment method' — 'different from the original' dropped (raw r15 still had it). | **RET-R023**: When modifying the payment of a pending order, the agent must switch to a single payment method that is different from the original payment method. |
| RET-MITEM-01d | partial | R34 'User must confirm all details…'. | **RET-R005**: The agent must obtain an explicit 'yes' from the user, given after the action details were listed, before calling any tool that updates the database. |
| RET-MITEM-01e | missing |  | **RET-R019**: Before modifying items of a pending order or exchanging items of a delivered order, the agent must remind the user to confirm that they have provided all items to be modified or exchanged. |
| RET-MITEM-03a | partial | R39 adds the condition 'If item modifications create a price difference' (the tool always requires one). | **RET-R028**: When modifying or exchanging items, the agent must use a payment method provided by the user to pay or receive the price difference. |
| RET-RTN-01b | missing |  | **RET-R015**: The agent must look up the order's current status (get_order_details) before cancelling, modifying, returning, or exchanging it. |
| RET-RTN-03 | incorrect | The 'either … or' restriction was split into two unconditional statements ('…will be issued to the original payment method' AND '…to an existing gift card'): as separate rules they contradict each other and no longer restrict anything. | **RET-R031**: When returning items, the agent must send the refund either to the order's original payment method or to an existing gift card of the user. |
| RET-EXC-01b | missing |  | **RET-R015**: The agent must look up the order's current status (get_order_details) before cancelling, modifying, returning, or exchanging it. |
| RET-EXC-01c | partial | R49 'User must confirm all items to be exchanged' — the agent's reminder obligation is lost. | **RET-R019**: Before modifying items of a pending order or exchanging items of a delivered order, the agent must remind the user to confirm that they have provided all items to be modified or exchanged. |

## 4. Reverse check of the extracted refined rules

Every refined rule, its flags, and where it went in the curated set.

| Refined | Category | Extracted text | Flags | Comment | Disposition |
|---|---|---|---|---|---|
| R1 | Identity, Access Control, and Conversation Scope | User must provide identifying information (email or name and zip code) at the start of the conversation to locate their account and enable authentication before any consequential actions. | SUBJ SCOPE | 'before any consequential actions' instead of 'at the beginning'; misses user-id clause. | → RET-R001 |
| R2 | Identity, Access Control, and Conversation Scope | User may request information about orders after authentication. | SUBJ OVERSPLIT | Permission recast as user permissions, split in three. | folded into RET-R001 |
| R3 | Identity, Access Control, and Conversation Scope | User may request information about products after authentication. | SUBJ OVERSPLIT | Permission recast as user permissions, split in three. | folded into RET-R001 |
| R4 | Identity, Access Control, and Conversation Scope | User may request profile information after authentication. | SUBJ OVERSPLIT | Permission recast as user permissions, split in three. | folded into RET-R001 |
| R5 | Identity, Access Control, and Conversation Scope | Each conversation must assist only one user; requests for another user must be denied. | COMPOUND |  | split → RET-R002, RET-R003 |
| R6 | Identity, Access Control, and Conversation Scope | Requests concerning other users must be refused. | REDUNDANT | = second half of R5. | merged into RET-R003 |
| R7 | Identity, Access Control, and Conversation Scope | The user must wait for the tool result before triggering a new tool call in the same turn. | SUBJ |  | → RET-R008 |
| R8 | Identity, Access Control, and Conversation Scope | The system must not respond with a tool call and a user response simultaneously. | ok |  | → RET-R009 |
| R9 | Identity, Access Control, and Conversation Scope | Transfer to a human agent should occur only if the request cannot be handled within the system's scope. | ok |  | → RET-R010 |
| R10 | Identity, Access Control, and Conversation Scope | Otherwise continue with automated handling. | UNSUPPORTED REDUNDANT | 'Otherwise continue with automated handling' — not in wiki. | dropped (RET-R011 added instead) |
| R11 | Identity, Access Control, and Conversation Scope | All time-related data presented to the user must be in EST. | HALLUCINATED REDUNDANT | Display-format requirements invented from a database fact; R56–R58 duplicate R11–R13. | dropped (clause RET-DOM-01 kept as fact) |
| R12 | Identity, Access Control, and Conversation Scope | Times must be displayed using 24-hour format. | HALLUCINATED REDUNDANT | Display-format requirements invented from a database fact; R56–R58 duplicate R11–R13. | dropped (clause RET-DOM-01 kept as fact) |
| R13 | Identity, Access Control, and Conversation Scope | The system should interpret and display times as EST in all actions. | HALLUCINATED REDUNDANT | Display-format requirements invented from a database fact; R56–R58 duplicate R11–R13. | dropped (clause RET-DOM-01 kept as fact) |
| R14 | Identity, Access Control, and Conversation Scope | Actions on an order are not permitted if the order status is not 'pending' or 'delivered'. | REDUNDANT | Four copies of one clause (two are negations of each other). | merged into RET-R013/RET-R014 |
| R15 | Identity, Access Control, and Conversation Scope | An order action is allowed only when the order status is 'pending' or 'delivered'. | REDUNDANT | Four copies of one clause (two are negations of each other). | merged into RET-R013/RET-R014 |
| R16 | Identity, Access Control, and Conversation Scope | When modifying or exchanging items, provide all items to be changed in a single list before the tool call. | ok |  | → RET-R018 |
| R17 | Identity, Access Control, and Conversation Scope | Only one tool call is allowed per order action. | GARBLED | 'Only one tool call is allowed per order action'. | → RET-R016, RET-R017 |
| R18 | Identity, Access Control, and Conversation Scope | Canceling an order is allowed only if the order status is 'pending'. | ok |  | → RET-R013 |
| R19 | Identity, Access Control, and Conversation Scope | Always verify the order status before requesting cancellation. | ok |  | → RET-R015 (extended to all order actions) |
| R20 | Identity, Access Control, and Conversation Scope | To cancel a pending order, provide the order id. | MODALITY | Confirmation lost. | → RET-R020 |
| R21 | Identity, Access Control, and Conversation Scope | Cancellation reason must be either 'no longer needed' or 'ordered by mistake'. | ok |  | → RET-R021 |
| R22 | Identity, Access Control, and Conversation Scope | Refund after cancellation is issued to the original payment method. | FACT REDUNDANT |  | dropped (clause RET-CAN-03 kept as fact) |
| R23 | Identity, Access Control, and Conversation Scope | If the original payment method was a gift card, the refund is issued immediately. | FACT REDUNDANT |  | dropped (clause RET-CAN-03 kept as fact) |
| R24 | Identity, Access Control, and Conversation Scope | If the original payment method was not a gift card, the refund takes 5 to 7 business days. | FACT REDUNDANT |  | dropped (clause RET-CAN-03 kept as fact) |
| R25 | Identity, Access Control, and Conversation Scope | A pending order may be modified only if its status is 'pending'. | ok |  | → RET-R013 |
| R26 | Identity, Access Control, and Conversation Scope | Allowed modifications are the shipping address, the payment method, or product item options. | REDUNDANT |  | → RET-R022 |
| R27 | Identity, Access Control, and Conversation Scope | No other changes are allowed. | REDUNDANT |  | → RET-R022 |
| R28 | Identity, Access Control, and Conversation Scope | When modifying the payment for a pending order, the user may choose a single new payment method. | MISSING-CONDITION | 'different from the original' dropped. | → RET-R023 |
| R29 | Identity, Access Control, and Conversation Scope | If changing to a gift card, the gift card must have enough balance to cover the total. | ok |  | → RET-R024 |
| R30 | Identity, Access Control, and Conversation Scope | Order status remains 'pending' after confirming a payment modification. | FACT REDUNDANT |  | dropped (clause RET-MPAY-03 kept as fact) |
| R31 | Identity, Access Control, and Conversation Scope | If the original payment method was a gift card, the refund is issued immediately. | FACT REDUNDANT |  | dropped (clause RET-MPAY-03 kept as fact) |
| R32 | Identity, Access Control, and Conversation Scope | If the original payment method was not a gift card, the refund takes 5 to 7 business days. | FACT REDUNDANT |  | dropped (clause RET-MPAY-03 kept as fact) |
| R33 | Identity, Access Control, and Conversation Scope | This modification action can be performed only once per order. | ok |  | → RET-R016 |
| R34 | Identity, Access Control, and Conversation Scope | User must confirm all details before executing the modification of items in a pending order. | SUBJ |  | → RET-R005 |
| R35 | Identity, Access Control, and Conversation Scope | After execution, the order status becomes 'pending (items modified)'. | FACT ALTERED-VALUE | Status string normalised to 'pending (items modified)' — neither wiki nor API spelling. | dropped (clause RET-MITEM-01b kept as fact) |
| R36 | Identity, Access Control, and Conversation Scope | The agent cannot modify or cancel the order further after modification. | ok |  | → RET-R013 |
| R37 | Identity, Access Control, and Conversation Scope | Each modified item must be changed to an available new item of the same product with a different option. | COMPOUND |  | split → RET-R025–R027 |
| R38 | Identity, Access Control, and Conversation Scope | Changing the product type is not allowed. | ok |  | → RET-R025 |
| R39 | Identity, Access Control, and Conversation Scope | If item modifications create a price difference, the user must provide a payment method to pay or receive a refund. | ADDED-CONDITION | 'If … a price difference arises'. | → RET-R028 |
| R40 | Identity, Access Control, and Conversation Scope | If a gift card is used, the balance must cover the price difference. | ok |  | → RET-R029 |
| R41 | Identity, Access Control, and Conversation Scope | Return is allowed only for orders with status 'delivered'. | ok |  | → RET-R014 |
| R42 | Identity, Access Control, and Conversation Scope | User must confirm the order id and the list of items to be returned. | ok |  | → RET-R030 |
| R43 | Identity, Access Control, and Conversation Scope | User must provide a payment method to receive the refund. | ok |  | → RET-R030 |
| R44 | Identity, Access Control, and Conversation Scope | Refund for returns will be issued to the original payment method. | INCORRECT | Disjunction split into two unconditional statements. | → RET-R031 |
| R45 | Identity, Access Control, and Conversation Scope | Refund for returns will be issued to an existing gift card. | INCORRECT | Disjunction split into two unconditional statements. | → RET-R031 |
| R46 | Identity, Access Control, and Conversation Scope | After user confirmation, the order status changes to 'return requested'. | FACT REDUNDANT |  | dropped (clause RET-RTN-04 kept as fact) |
| R47 | Identity, Access Control, and Conversation Scope | The user will receive an email with return instructions. | FACT REDUNDANT |  | dropped (clause RET-RTN-04 kept as fact) |
| R48 | Identity, Access Control, and Conversation Scope | Exchange is allowed only for orders with status 'delivered'. | ok |  | → RET-R014 |
| R49 | Identity, Access Control, and Conversation Scope | User must confirm all items to be exchanged. | SUBJ | Reminder obligation lost. | → RET-R019 |
| R50 | Identity, Access Control, and Conversation Scope | Each item must be exchangeable to an available new item of the same product with a different option and not changing the product type. | COMPOUND |  | split → RET-R025–R027 |
| R51 | Identity, Access Control, and Conversation Scope | For an exchange, provide a payment method to pay or receive a refund for the price difference. | ok |  | → RET-R028 |
| R52 | Identity, Access Control, and Conversation Scope | If using a gift card, the balance must cover the price difference. | ok |  | → RET-R029 |
| R53 | Identity, Access Control, and Conversation Scope | After user confirmation, the order status changes to 'exchange requested'. | FACT REDUNDANT |  | dropped (clauses RET-EXC-04a/b kept as facts) |
| R54 | Identity, Access Control, and Conversation Scope | The user will receive an email about the exchange. | FACT REDUNDANT |  | dropped (clauses RET-EXC-04a/b kept as facts) |
| R55 | Identity, Access Control, and Conversation Scope | There is no need to place a new order. | FACT REDUNDANT |  | dropped (clauses RET-EXC-04a/b kept as facts) |
| R56 | Timezone, Time Formatting, and Localization | All time-related data presented to the user must be in EST. | HALLUCINATED REDUNDANT | Display-format requirements invented from a database fact; R56–R58 duplicate R11–R13. | dropped (clause RET-DOM-01 kept as fact) |
| R57 | Timezone, Time Formatting, and Localization | Times must be displayed using 24-hour format. | HALLUCINATED REDUNDANT | Display-format requirements invented from a database fact; R56–R58 duplicate R11–R13. | dropped (clause RET-DOM-01 kept as fact) |
| R58 | Timezone, Time Formatting, and Localization | The system should interpret and display times as EST in all actions. | HALLUCINATED REDUNDANT | Display-format requirements invented from a database fact; R56–R58 duplicate R11–R13. | dropped (clause RET-DOM-01 kept as fact) |
| R59 | Confirmation, Consent, and System Guidance | Show action details before performing any consequential action that updates the database. | ok |  | → RET-R004 |
| R60 | Confirmation, Consent, and System Guidance | Require explicit confirmation by the user replying 'yes' to proceed with the action. | ok |  | → RET-R005 |
| R61 | Confirmation, Consent, and System Guidance | Transfer to a human agent should occur only if the request cannot be handled within the system's scope. | REDUNDANT | = R9. | merged into RET-R010 |
| R62 | Confirmation, Consent, and System Guidance | Otherwise continue with automated handling. | UNSUPPORTED REDUNDANT | 'Otherwise continue with automated handling' — not in wiki. | dropped (RET-R011 added instead) |
| R63 | Information Reliability and Guidance | Do not rely on information or procedures that are not provided by the user or by the tools. | MODALITY | 'rely on' ≠ 'make up'. | → RET-R006 |
| R64 | Information Reliability and Guidance | Do not request or accept fabricated or subjective guidance. | INVERTED | 'accept' instead of 'give'. | → RET-R007 |
| R65 | Order Modifications, Cancellations, Returns, and Exchanges | Actions on an order are not permitted if the order status is not 'pending' or 'delivered'. | REDUNDANT | Four copies of one clause (two are negations of each other). | merged into RET-R013/RET-R014 |
| R66 | Order Modifications, Cancellations, Returns, and Exchanges | An order action is allowed only when the order status is 'pending' or 'delivered'. | REDUNDANT | Four copies of one clause (two are negations of each other). | merged into RET-R013/RET-R014 |
| R67 | Order Modifications, Cancellations, Returns, and Exchanges | Canceling an order is allowed only if the order status is 'pending'. | ok |  | → RET-R013 |
| R68 | Order Modifications, Cancellations, Returns, and Exchanges | Always verify the order status before requesting cancellation. | ok |  | → RET-R015 (extended to all order actions) |
| R69 | Order Modifications, Cancellations, Returns, and Exchanges | To cancel a pending order, provide the order id. | MODALITY | Confirmation lost. | → RET-R020 |
| R70 | Order Modifications, Cancellations, Returns, and Exchanges | Cancellation reason must be either 'no longer needed' or 'ordered by mistake'. | ok |  | → RET-R021 |
| R71 | Order Modifications, Cancellations, Returns, and Exchanges | Refund after cancellation is issued to the original payment method. | FACT REDUNDANT |  | dropped (clause RET-CAN-03 kept as fact) |
| R72 | Order Modifications, Cancellations, Returns, and Exchanges | If the original payment method was a gift card, the refund is issued immediately. | FACT REDUNDANT |  | dropped (clause RET-CAN-03 kept as fact) |
| R73 | Order Modifications, Cancellations, Returns, and Exchanges | If the original payment method was not a gift card, the refund takes 5 to 7 business days. | FACT REDUNDANT |  | dropped (clause RET-CAN-03 kept as fact) |
| R74 | Order Modifications, Cancellations, Returns, and Exchanges | A pending order may be modified only if its status is 'pending'. | ok |  | → RET-R013 |
| R75 | Order Modifications, Cancellations, Returns, and Exchanges | Allowed modifications are the shipping address, the payment method, or product item options. | REDUNDANT |  | → RET-R022 |
| R76 | Order Modifications, Cancellations, Returns, and Exchanges | No other changes are allowed. | REDUNDANT |  | → RET-R022 |
| R77 | Order Modifications, Cancellations, Returns, and Exchanges | When modifying the payment for a pending order, the user may choose a single new payment method. | MISSING-CONDITION | 'different from the original' dropped. | → RET-R023 |
| R78 | Order Modifications, Cancellations, Returns, and Exchanges | If changing to a gift card, the gift card must have enough balance to cover the total. | ok |  | → RET-R024 |
| R79 | Order Modifications, Cancellations, Returns, and Exchanges | Order status remains 'pending' after confirming a payment modification. | FACT REDUNDANT |  | dropped (clause RET-MPAY-03 kept as fact) |
| R80 | Order Modifications, Cancellations, Returns, and Exchanges | If the original payment method was a gift card, the refund is issued immediately. | FACT REDUNDANT |  | dropped (clause RET-MPAY-03 kept as fact) |
| R81 | Order Modifications, Cancellations, Returns, and Exchanges | If the original payment method was not a gift card, the refund takes 5 to 7 business days. | FACT REDUNDANT |  | dropped (clause RET-MPAY-03 kept as fact) |
| R82 | Order Modifications, Cancellations, Returns, and Exchanges | This modification action can be performed only once per order. | ok |  | → RET-R016 |
| R83 | Order Modifications, Cancellations, Returns, and Exchanges | User must confirm all details before executing the modification of items in a pending order. | SUBJ |  | → RET-R005 |
| R84 | Order Modifications, Cancellations, Returns, and Exchanges | After execution, the order status becomes 'pending (items modified)'. | FACT ALTERED-VALUE | Status string normalised to 'pending (items modified)' — neither wiki nor API spelling. | dropped (clause RET-MITEM-01b kept as fact) |
| R85 | Order Modifications, Cancellations, Returns, and Exchanges | The agent cannot modify or cancel the order further after modification. | ok |  | → RET-R013 |
| R86 | Order Modifications, Cancellations, Returns, and Exchanges | Each modified item must be changed to an available new item of the same product with a different option. | COMPOUND |  | split → RET-R025–R027 |
| R87 | Order Modifications, Cancellations, Returns, and Exchanges | Changing the product type is not allowed. | ok |  | → RET-R025 |
| R88 | Order Modifications, Cancellations, Returns, and Exchanges | If item modifications create a price difference, the user must provide a payment method to pay or receive a refund. | ADDED-CONDITION | 'If … a price difference arises'. | → RET-R028 |
| R89 | Order Modifications, Cancellations, Returns, and Exchanges | If a gift card is used, the balance must cover the price difference. | ok |  | → RET-R029 |
| R90 | Order Modifications, Cancellations, Returns, and Exchanges | Return is allowed only for orders with status 'delivered'. | ok |  | → RET-R014 |
| R91 | Order Modifications, Cancellations, Returns, and Exchanges | User must confirm the order id and the list of items to be returned. | ok |  | → RET-R030 |
| R92 | Order Modifications, Cancellations, Returns, and Exchanges | User must provide a payment method to receive the refund. | ok |  | → RET-R030 |
| R93 | Order Modifications, Cancellations, Returns, and Exchanges | Refund for returns will be issued to the original payment method. | INCORRECT | Disjunction split into two unconditional statements. | → RET-R031 |
| R94 | Order Modifications, Cancellations, Returns, and Exchanges | Refund for returns will be issued to an existing gift card. | INCORRECT | Disjunction split into two unconditional statements. | → RET-R031 |
| R95 | Order Modifications, Cancellations, Returns, and Exchanges | After user confirmation, the order status changes to 'return requested'. | FACT REDUNDANT |  | dropped (clause RET-RTN-04 kept as fact) |
| R96 | Order Modifications, Cancellations, Returns, and Exchanges | The user will receive an email with return instructions. | FACT REDUNDANT |  | dropped (clause RET-RTN-04 kept as fact) |
| R97 | Order Modifications, Cancellations, Returns, and Exchanges | Exchange is allowed only for orders with status 'delivered'. | ok |  | → RET-R014 |
| R98 | Order Modifications, Cancellations, Returns, and Exchanges | User must confirm all items to be exchanged. | SUBJ | Reminder obligation lost. | → RET-R019 |
| R99 | Order Modifications, Cancellations, Returns, and Exchanges | Each item must be exchangeable to an available new item of the same product with a different option and not changing the product type. | COMPOUND |  | split → RET-R025–R027 |
| R100 | Order Modifications, Cancellations, Returns, and Exchanges | For an exchange, provide a payment method to pay or receive a refund for the price difference. | ok |  | → RET-R028 |
| R101 | Order Modifications, Cancellations, Returns, and Exchanges | If using a gift card, the balance must cover the price difference. | ok |  | → RET-R029 |
| R102 | Order Modifications, Cancellations, Returns, and Exchanges | After user confirmation, the order status changes to 'exchange requested'. | FACT REDUNDANT |  | dropped (clauses RET-EXC-04a/b kept as facts) |
| R103 | Order Modifications, Cancellations, Returns, and Exchanges | The user will receive an email about the exchange. | FACT REDUNDANT |  | dropped (clauses RET-EXC-04a/b kept as facts) |
| R104 | Order Modifications, Cancellations, Returns, and Exchanges | There is no need to place a new order. | FACT REDUNDANT |  | dropped (clauses RET-EXC-04a/b kept as facts) |

Flag counts: REDUNDANT 40, FACT 24, SUBJ 9, HALLUCINATED 6, COMPOUND 5, INCORRECT 4, OVERSPLIT 3, MODALITY 3, UNSUPPORTED 2, MISSING-CONDITION 2, ALTERED-VALUE 2, ADDED-CONDITION 2, SCOPE 1, GARBLED 1, INVERTED 1; refined rules with no flag: 35.

## 5. Curated rule set (overview)

The full records, with `wiki_quote`, `notes` and extracted ids, are in the JSON file.

| Rule | Description | Sources | Origin | Tools | Verification types |
|---|---|---|---|---|---|
| RET-R001 | The agent must authenticate the user by locating their user id via email (find_user_id_by_email) or via name and zip code (find_user_id_by_name_zip) before any other tool call or any disclosure of profile, order, or product information, even if the user has already provided a user id. | RET-GEN-01a, RET-GEN-01b, RET-GEN-02 | modified | get_user_details, get_order_details, get_product_details, list_all_product_types, cancel_pending_order, modify_pending_order_address, modify_pending_order_items, modify_pending_order_payment, modify_user_address, return_delivered_order_items, exchange_delivered_order_items, respond_to_user | tool_log, dialogue |
| RET-R002 | The agent must only act on the authenticated user's own account and orders: every user id and order passed to a tool must belong to the user authenticated in this conversation. | RET-GEN-03a, RET-CTX-01 | modified | get_user_details, get_order_details, cancel_pending_order, modify_pending_order_address, modify_pending_order_items, modify_pending_order_payment, modify_user_address, return_delivered_order_items, exchange_delivered_order_items, find_user_id_by_email, find_user_id_by_name_zip | state, tool_log |
| RET-R003 | The agent must deny any request for tasks related to a user other than the authenticated user. | RET-GEN-03b | extracted | respond_to_user | dialogue |
| RET-R004 | The agent must list the action details to the user before calling any tool that updates the database (cancel, modify, return, or exchange). | RET-GEN-04a | extracted | cancel_pending_order, modify_pending_order_address, modify_pending_order_items, modify_pending_order_payment, modify_user_address, return_delivered_order_items, exchange_delivered_order_items | dialogue |
| RET-R005 | The agent must obtain an explicit 'yes' from the user, given after the action details were listed, before calling any tool that updates the database. | RET-GEN-04b, RET-MITEM-01d | extracted | cancel_pending_order, modify_pending_order_address, modify_pending_order_items, modify_pending_order_payment, modify_user_address, return_delivered_order_items, exchange_delivered_order_items | dialogue |
| RET-R006 | The agent must not make up information, knowledge, or procedures that were not provided by the user or by the tools. | RET-GEN-05a | modified | respond_to_user | dialogue |
| RET-R007 | The agent must not give subjective recommendations or comments. | RET-GEN-05b | modified | respond_to_user | dialogue |
| RET-R008 | The agent must make at most one tool call per turn. | RET-GEN-06a | modified | * | structural |
| RET-R009 | The agent must not respond to the user and make a tool call in the same turn. | RET-GEN-06b, RET-GEN-06c | extracted | *, respond_to_user | structural |
| RET-R010 | The agent must not transfer the user to a human agent unless the request cannot be handled within the scope of the agent's actions or the user explicitly asks for a human agent. | RET-GEN-07a, RET-CTX-01 | tool_spec | transfer_to_human_agents | dialogue |
| RET-R011 | The agent must transfer the user to a human agent when the request cannot be handled within the scope of the agent's actions. | RET-GEN-07b, RET-CTX-01 | added | transfer_to_human_agents, respond_to_user | dialogue |
| RET-R012 | The agent must not confuse product ids with item ids: item ids passed to order tools must be item ids, and get_product_details must be called with a product id. | RET-DOM-04b, RET-DOM-04a | added | get_product_details, modify_pending_order_items, exchange_delivered_order_items, return_delivered_order_items | state |
| RET-R013 | The agent must not cancel or modify (address, payment method, or items) an order unless its status is exactly 'pending'. | RET-CAN-01a, RET-MOD-01a, RET-MITEM-01c, RET-DOM-05b | modified | cancel_pending_order, modify_pending_order_address, modify_pending_order_payment, modify_pending_order_items | state |
| RET-R014 | The agent must not return or exchange items of an order unless its status is exactly 'delivered'. | RET-RTN-01a, RET-EXC-01a, RET-DOM-05b | modified | return_delivered_order_items, exchange_delivered_order_items | state |
| RET-R015 | The agent must look up the order's current status (get_order_details) before cancelling, modifying, returning, or exchanging it. | RET-CAN-01b, RET-MOD-01b, RET-RTN-01b, RET-EXC-01b | modified | cancel_pending_order, modify_pending_order_address, modify_pending_order_items, modify_pending_order_payment, return_delivered_order_items, exchange_delivered_order_items | tool_log |
| RET-R016 | The agent must call modify_pending_order_items at most once per order. | RET-MITEM-01a, RET-DOM-06a | extracted | modify_pending_order_items | tool_log |
| RET-R017 | The agent must call exchange_delivered_order_items at most once per order. | RET-DOM-06a | modified | exchange_delivered_order_items | tool_log |
| RET-R018 | The agent must collect every item the user wants to change into the item list of a single modify-items or exchange call. | RET-DOM-06b | extracted | modify_pending_order_items, exchange_delivered_order_items | dialogue |
| RET-R019 | Before modifying items of a pending order or exchanging items of a delivered order, the agent must remind the user to confirm that they have provided all items to be modified or exchanged. | RET-MITEM-01e, RET-EXC-01c | modified | modify_pending_order_items, exchange_delivered_order_items | dialogue |
| RET-R020 | Before cancelling an order, the agent must have the user confirm the order id and the cancellation reason. | RET-CAN-02a | modified | cancel_pending_order | dialogue |
| RET-R021 | The agent must only cancel an order with the reason 'no longer needed' or 'ordered by mistake'. | RET-CAN-02b | extracted | cancel_pending_order | state |
| RET-R022 | The agent must not modify anything of a pending order other than its shipping address, payment method, or item options. | RET-MOD-02 | extracted | modify_pending_order_address, modify_pending_order_payment, modify_pending_order_items, respond_to_user | dialogue |
| RET-R023 | When modifying the payment of a pending order, the agent must switch to a single payment method that is different from the original payment method. | RET-MPAY-01 | modified | modify_pending_order_payment | state |
| RET-R024 | When modifying the payment of a pending order to a gift card, the agent must ensure the gift card balance covers the order's total amount. | RET-MPAY-02 | extracted | modify_pending_order_payment | state |
| RET-R025 | When modifying or exchanging items, the agent must replace each item only with an item of the same product (no change of product type). | RET-MITEM-02a, RET-MITEM-02b, RET-EXC-02a, RET-EXC-02b | extracted | modify_pending_order_items, exchange_delivered_order_items | state |
| RET-R026 | When modifying or exchanging items, the agent must replace each item only with a new item that is available. | RET-MITEM-02a, RET-EXC-02a | modified | modify_pending_order_items, exchange_delivered_order_items | state |
| RET-R027 | When modifying or exchanging items, the agent must replace each item only with a new item of a different product option than the item it replaces. | RET-MITEM-02a, RET-EXC-02a | modified | modify_pending_order_items, exchange_delivered_order_items | state |
| RET-R028 | When modifying or exchanging items, the agent must use a payment method provided by the user to pay or receive the price difference. | RET-MITEM-03a, RET-EXC-03a | modified | modify_pending_order_items, exchange_delivered_order_items | dialogue |
| RET-R029 | When modifying or exchanging items with a gift card as the payment method, the agent must ensure the gift card balance covers the price difference. | RET-MITEM-03b, RET-EXC-03b | extracted | modify_pending_order_items, exchange_delivered_order_items | state |
| RET-R030 | Before returning items, the agent must have the user confirm the order id, the list of items to be returned, and the payment method to receive the refund. | RET-RTN-02 | extracted | return_delivered_order_items | dialogue |
| RET-R031 | When returning items, the agent must send the refund either to the order's original payment method or to an existing gift card of the user. | RET-RTN-03 | modified | return_delivered_order_items | state |


## 6. Exact-value check

| Value | Wiki | Extracted (refined) | Curated |
|---|---|---|---|
| Authentication keys | email, or name + zip code | R1: ✓ | RET-R001 |
| Cancellation reasons | 'no longer needed' / 'ordered by mistake' | R21/R70: ✓ | RET-R021 |
| Order statuses | 'pending', 'processed', 'delivered', 'cancelled' (+ 'pending (items modifed)', 'return requested', 'exchange requested' elsewhere) | R14/R15: ✓ | facts RET-DOM-05a and others |
| Actionable statuses | pending (cancel/modify), delivered (return/exchange) | R18/R25/R41/R48: ✓ | RET-R013, RET-R014 (exact match) |
| Post-modify status | `'pending (items modifed)'` (sic); API: `'pending (item modified)'` | R35: **'pending (items modified)'** (altered) | RET-R013 note: exact match on `'pending'`, never a prefix match |
| Calls per order | modify items once; exchange once | modify ✓ (R33); exchange **✗** (R17 garbled) | RET-R016, RET-R017 |
| Payment-change method | single, **different from original** | R28: "different" **dropped** | RET-R023 |
| Gift-card balance | ≥ order total (payment change); ≥ price difference (items) | R29, R40, R52: ✓ | RET-R024, RET-R029 |
| Return refund destination | original method **or** existing gift card | R44+R45: **split, incorrect** | RET-R031 |
| Modifiable fields | shipping address, payment method, item options, nothing else | R26/R27: ✓ | RET-R022 |
| Payment method types | gift card, paypal, credit card | not extracted (fact) | fact RET-DOM-02 |
| Refund timing | gift card immediately, otherwise 5 to 7 business days | ✓ (as rules, duplicated) | facts RET-CAN-03, RET-MPAY-03 |
| Product types | 50 | not extracted | fact RET-DOM-03 |
| Times | EST, 24 h, **in the database** | R11–R13: **turned into display rules (invented)** | fact RET-DOM-01 |

## 7. Systemic observations

1. **Target subject.** As in airline, the run used `target_subject="User"`. The effect is weaker here: 13 of 57 unique refined rules have the user as subject, and many retail rules came out as bare imperatives ("Show action details…", "Do not rely on…"). Damage still happened:
   - R1 makes authentication a user duty ("User must provide identifying information");
   - R7 "The user must wait for the tool result";
   - R49 "User must confirm all items" replaces the agent's duty to *remind*;
   - R34 "User must confirm all details".

   Agent-only clauses with no user analogue were again the ones dropped: the user-id clause, the product/item-id clause, the reminder for modify-items, and the status checks.
2. **Refinement broke instead of merging.** The "decompose + merge + categorise" call mostly re-emitted the raw rules, often split into fragments. It placed the full list in one category and then copied subsets into others: 47 verbatim duplicates. It also produced fragments that are meaningless on their own: R10/R62 "Otherwise continue with automated handling", R27 "No other changes are allowed", R45 "Refund for returns will be issued to an existing gift card". These are serious for Step 2, because an ASPM built from this file would contain duplicated circuits and self-contradicting rules.
3. **Typical gpt-5-nano failure modes seen here.**
   - Dropped qualifiers: "different from the original"; "even when the user already provides the user id"; status checks for 3 of 4 actions.
   - Added conditions: "if a price difference arises" (R39).
   - Inverted direction: R64.
   - Disjunction split into conjunction of facts: R44/R45.
   - Hallucinated requirements from a fact: R11–R13.
   - Altered string literal: 'pending (items modified)'.
   - Hedge dropped: "Generally" in RET-DOM-05b.
   - "iff" weakened, here to "only if" (airline lost the other half).
   - Many facts emitted as rules (24 of 104).
4. **Policy granularity and references.** P8 lumps five *Domain basic* bullets; P13–P17 each merge a whole section. The `reference` fields are wrong: "Cancel pending order" and others are tagged `Domain basic`. The policy→rule mapping is consistent (refined ids), but raw `source_policies` is always empty and the document tree is empty.
5. **What the extraction got right.** Every status and every enumerated value (except the typo-string), the item-replacement constraints, and the gift-card thresholds.

## 8. Ambiguities, read literally and recorded in `notes`

The **Decision** lines were added at Step 1 close-out (Step 2 Part A, 2026-10-14). Items without a decision keep the literal reading.

1. **"Exchange or modify order tools can only be called once" (RET-R016/R017).** Read literally, this could also cover the address and payment modify tools. The surrounding text ("all items to be changed") and the separate "Modify items: This action can only be called once" suggest item tools only, so the narrower reading is used.
   **Decision (A1.1):** the narrow reading is confirmed. RET-R013 (exact `'pending'`) blocks any modify or cancel after `modify_pending_order_items`, *provided* "current status" means the latest order object seen in any tool output (`agent/predicates/context.py:latest_object`). The dependency is recorded in RET-R013's notes and covered by a unit test.
2. **Authentication gating (RET-R001).** Read literally, product information (`get_product_details`, `list_all_product_types`) also comes after authentication, which may over-block. Whether a transfer is allowed before authentication is unspecified, so the transfer tool is not gated.
   **Decision (A1.5):** the literal rule is kept. Read tools will not be shielded at runtime, so the product-lookup gating causes no blocking.
3. **"Generally, you can only take action on pending or delivered orders."** The hedge is ignored, because the action-specific clauses are unhedged.
4. **Status string.** The wiki says `'pending (items modifed)'` and the API says `'pending (item modified)'`. The rule uses an exact match on `'pending'`, which makes the spelling irrelevant.
5. **Confirmation for `modify_user_address` (RET-R004/R005).** It is included under "modify … update the database". The tool description agrees.
6. **Transfer (RET-R010/R011).** As in airline, the tool description's "explicitly asks for a human" is not in the wiki.
   **Decision (A1.3):** the disjunct is now part of RET-R010 (`origin: tool_spec`). The retail wiki has no precedence exceptions.
7. **Status-check recency (RET-R015).** The rule requires the status lookup to happen before the action. Whether it must be the latest lookup is left to Step 2.
8. **Status list.** The wiki's status enumeration (RET-DOM-05a) is incomplete relative to its own later sections and to the API.

## 9. Recommendations for re-running extraction

Same as the airline report, §9: a re-run is not needed for Step 2, and if done, use `-ts "Agent"`, record the parameters, and score against `policies/curated/retail_clauses.json`. Retail-specific additions:

1. The refinement step must **deduplicate**: hash-based exact dedup at minimum, embedding-based ideally, as in the paper. It must also assign each rule to exactly one category. Today the retail `risk_categories.json` cannot be used as an ASPM input as-is.
2. Instruct the extractor to keep string literals verbatim (statuses, reasons). Domain facts belong in a separate "context" output, not in rules.

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
| RET-R001 | A1.5 | The agent must authenticate the user by locating their user id via email (find_user_id_by_email) or via name and zip code (find_user_id_by_name_zip) before any other tool call or any disclosure of profile, order, or product information, even if the user has already provided a user id. *(origin: modified; type: temporal)* | description unchanged; note added *(origin: modified; types: tool_log, dialogue)* |
| RET-R008 | A2.8 | The agent must make at most one tool call per turn. *(origin: modified; type: temporal)* | description unchanged; note added *(origin: modified; types: structural)* |
| RET-R009 | A2.8 | The agent must not respond to the user and make a tool call in the same turn. *(origin: extracted; type: temporal)* | description unchanged; note added *(origin: extracted; types: structural)* |
| RET-R010 | A1.3 | The agent must not transfer the user to a human agent unless the request cannot be handled within the scope of the agent's actions. *(origin: extracted; type: semantic)* | The agent must not transfer the user to a human agent unless the request cannot be handled within the scope of the agent's actions or the user explicitly asks for a human agent. *(origin: tool_spec; types: dialogue)* |
| RET-R011 | A1.3 | The agent must transfer the user to a human agent when the request cannot be handled within the scope of the agent's actions. *(origin: added; type: semantic)* | description unchanged; note added *(origin: added; types: dialogue)* |
| RET-R013 | A1.1 | The agent must not cancel or modify (address, payment method, or items) an order unless its status is exactly 'pending'. *(origin: modified; type: deterministic)* | description unchanged; note added *(origin: modified; types: state)* |
| RET-R016 | A1.1 | The agent must call modify_pending_order_items at most once per order. *(origin: extracted; type: temporal)* | description unchanged; note added *(origin: extracted; types: tool_log)* |
| RET-R017 | A1.1 | The agent must call exchange_delivered_order_items at most once per order. *(origin: modified; type: temporal)* | description unchanged; note added *(origin: modified; types: tool_log)* |
