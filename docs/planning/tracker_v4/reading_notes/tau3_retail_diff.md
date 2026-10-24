# τ³ retail vs τ-bench v1 retail: what changed (tracker v4 reading notes)

Written 2026-10-23, $0, read-only. τ³ = `third_party/tau2-bench` at commit cc1df47 (not installed, not run).
v1 = `~/opt/tau-bench-59a200c/tau_bench/envs/retail/`. Task map: `retail_task_map.json` (same folder).
Data purity: partner-test tasks were only scored by code for the map (ids + a match score). Their content is not
described here. No banking file, no `web/leaderboard`, no `data/tau2/results` was read.

## 0. The short version

- **The DB did not change.** Same 500 users, 1,000 orders, 50 products, 591 items, 695 payment methods, same ids,
  same values. Only two format changes: each user now also stores `user_id`, and gift card balances are floats
  (`60.0`, v1 `60`). The K2 trap is still there: **0 of 239 credit cards** have a payment id ending in the card's
  last four.
- **The policy text changed in wording, not in rules**, with 3 real additions: "deny requests against this policy",
  a fixed transfer message, and "Other reasons are not acceptable" for cancel. One rule moved out of "Domain basic"
  into a new "Generic action rules" heading ("Exchange or modify order tools can only be called once per order").
- **Tools: one new tool, one gone, some checks changed.** New read tool `get_item_details(item_id)`. `think` is gone.
  Errors are exceptions now; the env shows them as `"Error: <text>"`, and most texts start with a capital letter.
  Address and payment changes now accept status `"pending (item modified)"`. Modify-items refuses new id = old id.
  **New bug:** modify-items writes the *last* new item's price and options onto *every* changed item.
- **Tasks: 114 in τ³ = v1 test 115 minus one exact duplicate** (v1 95 = v1 93 byte for byte). The map is the plain
  order map: τ³ id i -> v1 i for i <= 94, v1 i+1 for i >= 95.
- **All 69 of our retail tasks exist in τ³** (train 46, val 23). **45 τ³ tasks map to the partner's test 66 -> drop.**
  45 + 69 = 114. **Data purity flag: τ³ task 93 (our train) has the same content as partner-test task v1 95.**
- **Reward changed:** v1 = DB hash + every `outputs` string in the agent's replies. τ³ = DB + NL_ASSERTION (an LLM
  judge, paid, model `gpt-5.4-mini-2026-03-17` by default). `communicate_info` is kept but is **not** scored.
  In our 69: 68 use DB + NL_ASSERTION, 1 (v1 33) uses DB only; only 26 have NL assertions (the other 42 pass NL
  for free).
- **Partner's frozen TGR retail rules can run unchanged by name:** all 14 tools + `respond` they gate still exist
  with the same arguments. Gaps: the new `get_item_details` has no rule; the new policy sentences have no rule;
  rule-input facts that read tool outputs must be re-pointed at the new output format.

## 1. Policy diff (v1 `wiki.md` vs τ³ `policy.md`)

τ³ `policy.md` is the same as τ² 2.0 (`git diff 37199f3..HEAD` is empty). S-ids are the partner's rule-set sentence
ids (`from_shieldagent/rules/retail/rule_set.json`).

| v1 sentence (S-id) | τ³ | kind | rules citing it |
|---|---|---|---|
| S1 "As a retail agent, you can help users cancel or modify pending orders, return or exchange..." | same 4 items, now a bullet list | format only | fact |
| S2+S3 authenticate via email or name+zip, even if user gives user id | same words | same | 1-14 |
| S4 after auth you can give order/product/profile info | same | same | 3 |
| S5 one user per conversation, deny other users | same | same | 15-28 |
| S6 "Before taking **consequential actions** that update the database (...), you **have to** list the action **detail**..." | "Before taking **any action** that updates the database (...), you **must** list the action **details**..." | wording, same meaning | 30-43 |
| S7 don't make things up | "provided **by** the user" (v1 "from") | wording | not enforceable |
| S8+S9 one tool call at a time; "If you respond to the user, you should not make a tool call." | "...should not make a tool call **at the same time**." | wording | not enforceable |
| — | **NEW:** "You should deny user requests that are against this policy." | **added rule sentence** | none |
| S10 transfer iff request out of scope | same, **plus NEW:** "To transfer, first make a tool call to transfer_to_human_agents, and then send the message 'YOU ARE BEING TRANSFERRED TO A HUMAN AGENT. PLEASE HOLD ON.' to the user." | **added procedure** | 29 (old part only) |
| Domain basic: EST times | same | same | dropped by partner filter |
| Domain basic: user profile (email, address, user id, payment methods; 3 kinds) | rewritten as lists under "### User"; "unique user id" | format | dropped |
| Domain basic: 50 product types, variants, 't shirt' example | lists under "### Product"; adds product attributes (id, name, variants) and item attributes (id, options, **availability**, price) | added facts | dropped |
| Domain basic: product id vs item id not related | "Note: Product ID and Item ID have no relations and should not be confused!" | same | dropped |
| Domain basic: order status 'pending', 'processed', 'delivered', 'cancelled'. "Generally, you can only take action on pending or delivered orders." | status list under "### Order" with **new order attribute list** (id, user id, address, items, status, "fullfilments info", payment history) + "Orders can have other optional attributes (cancellation reason, ... exchange price difference etc)". The "Generally..." sentence moved to **"## Generic action rules"** | moved + added facts | dropped in v1 build; would now be **kept** by the partner's filter (it only drops "Domain basic") |
| Domain basic: "Exchange or modify order tools can only be called once." | "...can only be called once **per order**." under **"## Generic action rules"** | clarified + moved | dropped in v1 build |
| S11 cancel only if pending, check status | same | same | 44 |
| S12 confirm order id and reason (2 reasons) | same **+ "Other reasons are not acceptable."** | added sentence | 30, 45, 46 |
| S13 cancel result + refund timing | same | same | fact |
| S14 modify only if pending | same | same | 47-49 |
| S15 only address, payment, item options | same | same | fact |
| S16 single payment method, different from original | same | same | 50, 51 |
| S17 gift card must cover total | same (same typo "wants the modify") | same | 52 |
| S18 status kept 'pending' | "kept **as** 'pending'" | wording | fact |
| S19 refund timing | "otherwise **it will be refunded within** 5 to 7 business days" | wording | fact |
| S20 modify items once, status 'pending (items modifed)', no more modify/cancel | split into 2 sentences, same content, same typo | wording | not enforceable |
| S21 "So confirm all the details are right and be cautious" | "So **you must** confirm all the details are **correct**..." | wording | 36, 37 |
| S22 remind customer to confirm all items | "...provided all **the items they want to modify**." | wording | 53 |
| S23, S24 same product, other option; no type change | same | same | 54 |
| S25, S26 payment method for price difference; gift card must cover | same | same | 55, 56 |
| S27 return only if delivered | same | same | 57 |
| S28 "confirm the order id, the list of items to be returned, and a payment method to receive the refund" | split: "...confirm the order id and the list of items to be returned." + "The user needs to **provide** a payment method to receive the refund." | split, same meaning | 42, 58 |
| S29 refund to original method or existing gift card | same | same | 59 |
| S30 'return requested' + email | same | same | fact |
| S31-S38 exchange section | same words | same | 60-64, facts |

Net: no v1 rule sentence lost or reversed. New rule-like text without a frozen rule: "deny requests against this
policy", the fixed transfer message, "Other reasons are not acceptable" (already covered by rule 45), and the
"Generic action rules" heading (once per order; act only on pending/delivered).

## 2. Tools diff

τ³: one class `RetailTools` (`src/tau2/domains/retail/tools.py`), `@is_tool` methods. The schema comes from type
hints + docstring (`Args:` lines become the argument descriptions; `Raises:` is not shown to the agent).

### 2.1 Names and arguments

| tool | v1 | τ³ |
|---|---|---|
| calculate(expression) | yes | same |
| cancel_pending_order(order_id, reason) | `reason` has a JSON **enum** of the 2 reasons | `reason: str`, **no enum** in schema (the docstring still names the 2) |
| exchange_delivered_order_items(order_id, item_ids, new_item_ids, payment_method_id) | yes | same args, same text |
| find_user_id_by_email(email) | yes | same |
| find_user_id_by_name_zip(first_name, last_name, zip) | yes | same |
| get_order_details(order_id) | yes | same |
| get_product_details(product_id) | yes | same |
| **get_item_details(item_id)** | — | **NEW** (READ). "Get the inventory details of an item." Returns the variant: item_id, options, available, price (not the product id or name) |
| get_user_details(user_id) | yes | same |
| list_all_product_types() | yes | same |
| modify_pending_order_address(order_id, address1, address2, city, state, country, zip) | yes | same |
| modify_pending_order_items(order_id, item_ids, new_item_ids, payment_method_id) | yes | same |
| modify_pending_order_payment(order_id, payment_method_id) | yes | same |
| modify_user_address(user_id, address1, ..., zip) | yes | same |
| return_delivered_order_items(order_id, item_ids, payment_method_id) | yes | same |
| **think**(thought) | yes | **removed** (commented out) |
| transfer_to_human_agents(summary) | "Only transfer if the user explicitly asks for a human agent, or if the user's issue cannot be resolved..." | same idea as 2 bullets: "the user explicitly asks for a human agent" / "given the policy and the available tools, you cannot solve the user's issue." Returns "Transfer successful". In the normal text run it does **not** end the episode (v1: terminate tool) |

Tool descriptions (the long text) are word for word the same for all other tools. Only when a multilingual
"regional settings" object is passed do the address argument descriptions change (not the default).

### 2.2 Checks, errors, side effects

General: v1 returns `"Error: ..."` strings; τ³ raises `ValueError`, and `Environment.get_response` turns it into
`"Error: <message>"` with `error=True`. So the prefix stays, the message text changes (mostly a capital first
letter). Check order is the same as v1 in every tool.

| tool | v1 error text | τ³ error text | logic change |
|---|---|---|---|
| any order lookup | `order not found` | `Order not found` | — |
| any user lookup | `user not found` | `User not found` | — |
| get_product_details | `product not found` | `Product not found` | — |
| get_item_details | — | `Item not found` | new |
| find_user_id_by_email / _name_zip | `user not found` | `User not found`; **new** `User lookup is ambiguous` | match is now accent- and case-folded (`fold_for_match`: NFD, drop accents, casefold, strip); v1 took the first match, τ³ refuses 2+ matches. In this DB: all ASCII, no duplicate emails or name+zip, so same answers |
| cancel_pending_order | `non-pending order cannot be cancelled`; `invalid reason` | `Non-pending order cannot be cancelled`; `Invalid reason` | status must be exactly `pending` (same). Gift-card refund test: v1 `'gift_card' in payment_id`, τ³ `isinstance(GiftCard)` (same on this data) |
| exchange_delivered_order_items | `non-delivered order cannot be exchanged`; `{id} not found`; `the number of items to be exchanged should match`; `new item {id} not found or available`; `payment method not found`; `insufficient gift card balance to pay for the price difference` | `Non-delivered order cannot be exchanged`; **`Number of {id} not found.`**; `The number of items to be exchanged should match.`; **two texts now**: `Variant not found` (new id is not a variant of that product) or `New item {id} not found or available` (variant exists but not available); `Payment method not found`; `Insufficient gift card balance to pay for the price difference` | still **no** check that new id differs from old id (v1 tasks 91 and 108 used that hole; τ³ fixed the tasks, not the tool). Diff rounded to cents (same) |
| modify_pending_order_items | `non-pending order cannot be modified`; `{id} not found`; `the number of items to be exchanged should match`; `new item ... not found or available`; `payment method not found`; `insufficient gift card balance to pay for the new item` | capitalized versions; `{id} not found` same; `Variant not found` / `New item ... not found or available` split as above; **new** `The new item id should be different from the old item id` | status must be exactly `pending` (same). **New bug:** the write loop sets `item.price = variant.price` and `item.options = variant.options` using the *last* `variant` from the check loop, so with 2+ changed items every changed item gets the last new item's price and options (the `item_id` is right). The payment / refund amount and gift card balance are still right (sum of true differences). Diff not rounded (same as v1). New status `pending (item modified)` (same) |
| modify_pending_order_payment | `non-pending order cannot be modified`; `payment method not found`; `there should be exactly one payment for a pending order`; `the new payment method should be different from the current one`; `insufficient gift card balance to pay for the order` | capitalized versions | status test is now **`'pending' in status`** (accepts `pending (item modified)`), but such an order has 2+ payment rows, so it still fails, now with `There should be exactly one payment for a pending order`. One-payment test `len != 1` (v1 `> 1`; same on data, 0 pending orders have 2+ payments) |
| modify_pending_order_address | `non-pending order cannot be modified` | `Non-pending order cannot be modified` | **status test loosened to `'pending' in status`: an address change after an item change is now accepted** (v1 refused) |
| modify_user_address | `user not found` | `User not found` | — |
| return_delivered_order_items | `non-delivered order cannot be returned`; `payment method not found`; `payment method should be either the original payment method or a gift card`; `some item not found` | `Non-delivered order cannot be returned`; `Payment method not found`; **`Payment method should be the original payment method`** (shorter, drops "or a gift card"); `Some item not found` | gift card test by type, not id text (same on data) |
| calculate | `invalid characters in expression` | `Invalid characters in expression` | — |

### 2.3 Tool output format (what the agent and the guard see)

- Outputs are `json.dumps(model.model_dump())`. Orders now always carry the 7 optional keys
  (`cancel_reason`, `exchange_items`, `exchange_new_items`, `exchange_payment_method_id`,
  `exchange_price_difference`, `return_items`, `return_payment_method_id`) as `null` when unset (v1: absent).
- `get_user_details` adds `"user_id"` first; key order is `user_id, name, address, email, payment_methods, orders`.
- Credit card key order `source, id, brand, last_four` (v1 file: `source, brand, last_four, id`).
- Gift card `balance` prints as float (`60.0`; v1 `60`). Prices and amounts were floats already.
- `list_all_product_types` is the same sorted name -> id JSON. Lookups return the bare user id string (same).

## 3. DB diff (v1 `data/*.json` vs τ³ `db.json`)

| | v1 | τ³ | same ids? |
|---|---|---|---|
| users | 500 | 500 | yes, all 500; only change: `user_id` field added |
| orders | 1,000 | 1,000 | yes, 0 records differ |
| products | 50 | 50 | yes, 0 differ |
| items (variants) | 591 (379 available, 212 not) | 591 (379 / 212) | yes |
| payment methods | 695: credit_card 239, gift_card 234, paypal 222 | same | yes; id prefix = `source` for all 695 |
| card brands | mastercard 133, visa 106 | same | |
| order status | pending 423, delivered 373, processed 102, cancelled 102 | same | |

- **K2 trap recheck: 0 of 239 credit cards have an id ending in their `last_four` in τ³ (same as v1).** Ids are
  `credit_card_` + 7 digits; only 1 card has its last four anywhere inside the 7 digits.
- Addresses: all `country "USA"`, 5-digit zip, `address2` always set (e.g. "Suite 259"), state as 2 letters.
  Field order in the model: address1, address2, city, country, state, zip.
- Item and product ids: 10 digits each. Order ids `#W` + 7 digits. Options: dict of option name -> value, e.g.
  `{'color': 'blue', 'size': 'M', 'material': 'cotton', 'style': 'crew neck'}`.
- Other data facts v3 used, rechecked on τ³: 0 pending orders with 2+ payments; 0 products with two variants of the
  same options; emails and name+zip unique; all order items exist in the catalog; user -> order links consistent.
- `db.json` is byte-identical to τ² 2.0 (commit 37199f3).

## 4. Task map (τ³ 114 -> v1 test 115)

Method: for every τ³ task, score each v1 test task by 0.5 × sequence match of expected actions (name + args) + 0.3 ×
sequence match of the instruction text (τ³ known_info + reason_for_call + unknown_info + task_instructions) + 0.2 ×
same user id (taken from the order ids in the actions, or the lookup args). The best match equals the plain order
map for 113 of 114 tasks. The one tie is t3 93 (see below). Margins are small only for v1 twin tasks that share
the same action list (24/57, 36/37, 41/42, 71/72, 83/84, 97/98); the order map settles them.

**Map rule:** τ³ id i -> v1 test i for i = 0..94; τ³ i -> v1 i+1 for i = 95..113. v1 95 has no τ³ twin.

| count | value |
|---|---|
| τ³ retail tasks | 114 (`retail_114.json` = all 114, split "base") |
| v1 test tasks | 115 |
| v1 test dropped by τ² | 1: v1 95 (byte-identical to v1 93: instruction, actions, outputs) |
| our retail tasks (val + train from `online_tasks.json`) | 69, **all 69 present** (train 46, val 23) |
| τ³ tasks mapping to the partner's test 66 (retail part: 46) | **45 -> drop** (the 46th, v1 95, has no τ³ twin) |
| ambiguous | **t3 93**: equal to v1 93 (our train) and v1 95 (partner test). Order map says v1 93. **Same content as a partner-test task: decide keep or drop.** If dropped, our retail train is 45 |
| user id fix | v1 64's `user_id` label is wrong (`harper_moore_6183`); the task is James Sanchez 60623 = `james_sanchez_3954`. `online_tasks.json` copies the wrong id |

τ³'s own splits mix groups: τ³ "train" 74 = ours 46 (train 30, val 16) + partner test 28; τ³ "test" 40 = ours 23
(train 16, val 7) + partner test 17; `retail_50` = ours 33 (train 23, val 10) + partner test 17. **Do not use τ³'s
splits or `retail_50` as-is: they contain partner-test tasks.**

### 4.1 Expected writes per our task (effective = writes that succeed)

| writes | train | val | all | our v1 ids |
|---|---|---|---|---|
| 0 | 4 | 2 | 6 | 24, 25, 50, 57, 62, 67 (= the partner's retail no-write list minus its test ids 10, 65, 68) |
| 1 | 24 | 10 | 34 | 2, 3, 5, 6, 8, 15, 17, 20, 21, 26, 27, 33, 37, 38, 40, 46, 47, 49, 51, 52, 53, 56, 58, 63, 64*, 66, 82, 84, 85, 89, 90, 93, 94, 107 |
| 2 | 8 | 7 | 15 | 4, 11, 14, 31, 59, 71, 74, 76, 81, 91, 92, 96, 98, 101, 108 |
| 3+ | 10 | 4 | 14 | 16, 22, 23, 28, 32, 41, 54, 78, 102, 103, 104, 110, 111, 112 |

\*64 lists 2 writes; the first (`exchange_delivered_order_items` on a pending order) fails in v1 and τ³.
Write counts are the same as v1 for all 69. 0-write tasks: 25 and 50 end in transfer, 24 and 57 are "change of
mind / not allowed", 62 and 67 are info only.

### 4.2 What changed per our task

Reward basis, all 69: v1 = DB + `outputs` strings. τ³ = DB + NL_ASSERTION for 68, DB only for v1 33.
NL assertions present in 26: v1 2, 3, 4, 16, 21, 24, 28, 37, 38, 40, 46, 47, 54, 59, 62, 63, 67, 76, 89, 96, 104,
107, 108, 110, 111, 112. `communicate_info` equals v1 `outputs` for 67 of 69 (37, 38: `481.5` -> `481.50`).
Tasks with NL but no v1 outputs (new judged demands): 107, 108, 110, 111, 112 (all "Agent should modify / process
..."). Tasks with v1 outputs but no NL (string no longer checked): 31, 32 (tracking number). Instructions are now
split into known_info / unknown_info / reason_for_call / task_instructions; most only moved text. Expected actions
are identical for 58 of 69; write actions identical for 67 of 69.

| v1 id (τ³ id) | group | change |
|---|---|---|
| 2, 3 | train | `list_all_product_types` removed from gold; "exactly how many"; NL: 10 t-shirt options |
| 4 | val | same as 2; "(i.e., your 2 relevant orders)" dropped; **open issue** issue_2b74ee61 (user never asks for a number, so the NL "10" is unfair) |
| 5 | val | **open issue** issue_770466c1 (tools do not enforce login) |
| 15 | val | adds "You prefer PayPal for any payment or refund." |
| 20 | val | instruction rewritten (new variants may differ, only size matters; skip an order that cannot be upgraded; gift card else PayPal). Gold DB differs from v1 because of the modify-items price bug |
| 21 | val | 3 `get_product_details(<item id>)` -> `get_item_details`; clearer item-vs-product id; NL gift card balance $44.08. Gold DB differs (price bug) |
| 22 | train | regret moment pinned (after both address changes are confirmed) |
| 27 | train | "From a recent order"; "if the agent says they can only do one" |
| 28 | train | return order spelled out; cancel only the hose, refuse a whole-order cancel |
| 31 | val | stray ". " at the start of reason_for_call; tracking number no longer scored |
| 32 | train | tracking number no longer scored |
| 33 | train | reward = DB only |
| 37 | val | 6 read actions removed; "Do not end the conversation until your changes have been made."; 2 NL; gold DB differs (price bug) |
| 38 | val | 7 read actions removed; 2 NL |
| 51 | train | `list_all_product_types` removed |
| 54 | train | adds "if NO cheaper boots, keep that order and cancel the other items" |
| 59 | val | `calculate` removed from gold; 2 NL |
| 62 | train | `list_all_product_types` removed; adds "only modify if a speaker under $100 exists"; 2 NL |
| 64 | val | wrong v1 user_id label (see above); failing gold exchange kept |
| 74 | train | adds "pay the modification with your credit card" |
| 76 | train | cancel reasons spelled out; "all the grills bought in previous orders" |
| 78, 84, 92 | | wording only ("when the agent asks for confirmation", "do not say yes immediately") |
| 91 | val | **gold write changed**: exchange new item 9494281769 (= old, a v1 bug) -> 7609274509; fallback "get the 32GB E-Reader" |
| 101 (100) | train | adds "use your credit card" and "if pending orders cannot be exchanged, ask to change the order"; gold DB differs (price bug) |
| 102 (101) | val | adds "this order contains both an air purifier and a speaker" |
| 107 (106) | train | both emails stated; NL "Agent should process the exchange." |
| 108 (107) | val | **gold write changed**: exchange new item 1615379700 (= old) -> 8106223139; fallback size 9 leather waterproof; NL |
| 110 (109), 111 (110), 112 (111) | val, train, train | process NL assertions added (address on order + profile, modify items) |
| 93 | train | **data purity flag** (same content as partner test v1 95) |
| all others | | text moved into the 4 fields only; same actions; same outputs |

Gold write replay on the τ³ DB (my own stdlib re-implementation of the 7 write tools, both semantics): the only
failing gold write is 64's known one. Gold end DB differs from the v1 gold end DB for 20, 21, 37, 101 (price bug)
and 91, 108 (changed gold).

## 5. Can the partner's frozen TGR retail rules run unchanged?

Frozen set: 64 rules, 24 predicates, circuits for 15 actions; `action_names` (17) also lists `calculate` and
`think`. Predicates are judged from messages, call args and tool outputs (an LLM judge in TGR; code facts in v3).

| what the rules use | still in τ³ with the same meaning? |
|---|---|
| tool names in circuits: find_user_id_by_email, find_user_id_by_name_zip, get_user_details, get_order_details, get_product_details, list_all_product_types, cancel_pending_order, modify_pending_order_address, modify_pending_order_items, modify_pending_order_payment, modify_user_address, return_delivered_order_items, exchange_delivered_order_items, transfer_to_human_agents, respond | **yes, all 15**, same argument names |
| `think` (listed, no rule) | gone; harmless |
| `get_item_details` | **new, no rule.** Rules 6/19 gate `get_product_details` (login first, not another user); the same read via `get_item_details` is ungated. Catalog data, low risk, but a gap |
| user_authenticated ("successful email or name-and-zip lookup output") | yes: output is still the bare user id; failure is `Error: User not found` (capital U) or new `Error: User lookup is ambiguous` (never happens on this DB) |
| email_identity_provided_by_user, name_and_zip_identity_provided_by_user | yes; the tool now folds accents, code facts that compare typed text should fold the same way |
| order_status_checked_pending / _delivered | yes: `status` values identical. Note rule 47/49 still require `pending`; τ³'s address tool now accepts `pending (item modified)` -> the rule is stricter than the τ³ tool but matches the policy ("not able to modify or cancel the order anymore") |
| cancellation_reason_is_allowed | yes; the schema lost its enum, so wrong reasons may now reach the tool (it still refuses) |
| payment_method_is_gift_card (id holds "gift_card") | yes, id prefix = source for all 695 |
| gift_card_balance_covers_order_total / _price_difference | yes; balance now prints `60.0` |
| payment_method_differs_from_original | yes (`payment_history[0]`) |
| item_replacements_are_available_same_product_different_option | yes; data same. After a multi-item modify, τ³ order outputs show wrong price/options for changed items (tool bug) |
| return_refund_method_is_original_or_existing_gift_card | yes; the tool's error text no longer says "or a gift card" |
| consequential_action_details_listed / user_explicitly_confirmed_pending_action (S6) | yes, S6 only reworded |
| request_cannot_be_handled_within_scope (S10) | yes for the old part. New fixed transfer message and non-terminal transfer are not in any rule |
| background facts S13, S15, S18, S19, S30, S37, S38 | same meaning |
| sentence ids S1-S38 | all still present in meaning; S6, S8/S9, S12, S18-S22, S28 reworded; S28 split in two |

Verdict: the rule set can run unchanged on τ³ retail by name and meaning. To keep "the rules are not ours,
unchanged", feed it the same frozen file and say plainly that τ³ adds 3 policy sentences and 1 tool it does not
cover. What must change is **our plumbing**, not the rules: v3 `state.run_tool` / `tool_check.py` call v1
`invoke(data, ...)` and match v1 error texts -> port to τ³ and re-map every error text in 2.2; output parsers must
accept `null` optional keys, the `user_id` key, the new card key order and float balances; the modify-items price
bug must be mirrored (or flagged) in any DB fact that reads order item prices after a modify.

## 6. Open points for the plan

1. t3 93: keep (it is our train task) or drop (its content equals a partner-test task)? Safest for "no leaks": drop
   it, or keep it only in train and say so.
2. NL_ASSERTION is an LLM judge (paid, needs approval). Options: run it, or score τ³ with DB only (`--evaluation-type
   env` style) and report NL separately. v1-style string checks on `communicate_info` are free but not τ³'s metric.
3. Fix our `online_tasks.json` user id for v1 64 when building the τ³ task file.
4. The modify-items price bug changes gold DB for 4 of our tasks; both gold and agent use the same tool, so DB
   reward is fair, but displayed prices are wrong.
5. Open τ³ issues on our tasks: 4 (unfair NL "10"), 5 (no login enforcement).

## 7. Files

- Map: `/home/azureuser/code_projects/docs/planning/tracker_v4/reading_notes/retail_task_map.json` (114 rows;
  partner-test rows carry only ids, score and `drop: true`; our 69 carry group, user id, write counts, reward basis,
  NL assertions, communicate_info, gold-replay result, notes).
- Scripts (stdlib, scratchpad): `/tmp/claude-1000/-home-azureuser-code-projects/796f0c59-5ea8-4a72-8aa7-c0248fb5d2c9/scratchpad/v4_ret_load.py`, `v4_ret_map.py`, `v4_ret_pertask.py`,
  `v4_ret_db.py`, `v4_ret_sim.py`, `v4_ret_build.py` (same folder).
- Logs: `/home/azureuser/code_projects/predicate_correctness/output/logs/v4_ret_*.txt`.

---

## Errata for v1.0.1

Checked 2026-10-23, $0, read only. The clone is now at tag **v1.0.1** (commit fc0055d, `pyproject.toml` version 1.0.1). This is τ³-bench, the version we use. The notes above were made at cc1df47. For every retail file, cc1df47 = v2.0.0. Method: `git diff v1.0.1 v2.0.0` plus `git show v1.0.1:<path>`. No tau2 import. Logs: `predicate_correctness/output/logs/v4_v101_*.txt`.

**Main point: the retail world did not change.** These files have the same blob id at v1.0.1, v2.0.0 and cc1df47: `db.json`, `policy.md`, `tasks.json`, `split_tasks.json` and the three `task_issues/*.json`, plus `data_model.py` and `utils.py`. So these still hold: section 1 (policy), section 3 (DB), section 4 (map rule and per-task changes) and section 5 (frozen rules). The write tools are unchanged too, including the modify-items price bug and the `'pending' in status` checks.

New map: `retail_task_map_v101.json`, rebuilt by re-running `v4_ret_map.py`, `v4_ret_sim.py` and `v4_ret_build.py` on the v1.0.1 blobs. The match scores and the gold-replay output are byte-identical to the old run, and all 114 rows match `retail_task_map.json`. One change was made on purpose: **τ³ 93 is now `drop: true`**. This applies the rule "drop any τ³ task whose content equals a partner-test task": v1 93 and partner-test v1 95 are byte-identical. Its row now keeps only ids. A full-equality check over all v1 retail tasks finds no other such pair.

### Statements that change at v1.0.1
| where above | it says | at v1.0.1 |
|---|---|---|
| header | τ³ = cc1df47 | τ³ = v1.0.1 (fc0055d). Same data |
| §0 / §4 "All 69 of our retail tasks exist (train 46, val 23)" | 69 kept | **68 kept: train 45, val 23.** 46 dropped = 45 partner-test + τ³ 93 (content equals partner-test v1 95) |
| §0 "Reward changed … NL_ASSERTION (paid, model `gpt-5.4-mini-2026-03-17`)" | gpt-5.4-mini | NL judge = **`gpt-4.1-2025-04-14`, temperature 0.0** (`config.py` `DEFAULT_LLM_NL_ASSERTIONS`). It makes **one call per task**, with all of the task's assertions in one prompt. The reply is read with a bare `json.loads` (no JSON repair, no validation retry). If the reply is not JSON, grading raises and the runner re-runs the whole simulation (`run_with_retry`, up to `max_retries`=3). A task whose `nl_assertions` list is empty makes no call and gets NL = 1 |
| §2.2 `find_user_id_by_email` / `_by_name_zip` | accent- and case-folded; refuses 2+ matches with "User lookup is ambiguous" | `.lower()` equality only (no accent folding, no strip). It returns the **first** match and never says "ambiguous". The answers on this DB are the same (all ASCII, emails and name+zip are unique) |
| §2.1 last line | regional settings can change the address descriptions | there are no regional settings at v1.0.1. The descriptions are always the default ones |
| §4 τ³ splits | "`retail_50` = ours 33 + partner test 17" | `data/tau2/task_subsets/` (`retail_50`, `retail_114`) **does not exist** at v1.0.1. `split_tasks.json` is identical (train 74 / test 40 / base 114). The warning still holds: τ³'s own splits mix in partner-test tasks |
| §6 point 1 (t3 93 keep or drop) | open | **decided: drop** |
| §6 point 2 | grade "`--evaluation-type env` style" | v1.0.1 `tau2 run` has **no evaluation-type flag**. It always grades with `EvaluationType.ALL`. For DB-only grading, pass `evaluation_type=EvaluationType.ENV` in Python (`run_tasks`, `run_single_task`, `run_simulation` or `evaluate_simulation`) |
| (not stated above) | — | COMMUNICATE is computed under `ALL` by substring ($0), but it is in no retail task's reward basis, so it never affects the retail reward |

Tool line numbers at v1.0.1: `cancel_pending_order` :159, `exchange_delivered_order_items` :208, `find_user_id_by_name_zip` :287, `find_user_id_by_email` :315, `get_item_details` :365, `modify_pending_order_address` :411, `modify_pending_order_items` :455, `modify_pending_order_payment` :545, `modify_user_address` :625, `return_delivered_order_items` :664, `think` (commented out) :716, `transfer_to_human_agents` :732.

### Per-task facts at v1.0.1 (our 68 tasks; from `retail_task_map_v101.json` → `v101`)
Effective writes are the expected writes that succeed in the stdlib replay. The only failing gold write is the known one in v1 64.

| writes | train | val | all | our v1 ids |
|---|---|---|---|---|
| 0 | 4 | 2 | 6 | 24, 25, 50, 57, 62, 67 |
| 1 | 23 | 10 | 33 | 2, 3, 5, 6, 8, 15, 17, 20, 21, 26, 27, 33, 37, 38, 40, 46, 47, 49, 51, 52, 53, 56, 58, 63, 64, 66, 82, 84, 85, 89, 90, 94, 107 |
| 2 | 8 | 7 | 15 | 4, 11, 14, 31, 59, 71, 74, 76, 81, 91, 92, 96, 98, 101, 108 |
| 3+ | 10 | 4 | 14 | 16, 22, 23, 28, 32, 41, 54, 78, 102, 103, 104, 110, 111, 112 |

- Reward basis: `["DB","NL_ASSERTION"]` for 67 tasks; `["DB"]` for 1 (v1 33).
- NL assertions: 26 tasks, 43 assertions in total (v1 2, 3, 4, 16, 21, 24, 28, 37, 38, 40, 46, 47, 54, 59, 62, 63, 67, 76, 89, 96, 104, 107, 108, 110, 111, 112). The other 41 tasks with NL in the basis pass NL for free.
- `communicate_info`: non-empty in 23 tasks. It is never scored for retail.
- Paid judge calls per trial under the default `ALL`: **26** (one gpt-4.1 call for each of those 26 tasks) and 0 for the other 42.
