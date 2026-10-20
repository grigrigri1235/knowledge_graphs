# Step 2: ASPM design notes (τ-bench v1 airline and retail)

Date: 2026-10-14. Inputs: the curated rules in `policies/curated/` (Step 1, closed out in Step 2 Part A).

## Artefacts

| Path | What it is |
|---|---|
| `aspm/{airline,retail}_aspm.json` | The ASPMs, in the format `agent/tools/aspm_tool.py` loads. Generated; do not edit by hand. |
| `scripts/aspm_src/{airline,retail}.py`, `common.py` | **Hand-written source** of each ASPM: tree, rules (logic, enforcement, api_enforced) and the predicate registry. |
| `scripts/build_aspm.py` | Builds the two JSON artefacts per domain from the sources and the curated rules. |
| `policies/predicates/{domain}_predicates.json` | Predicate registry: type, inputs, computation spec (Python) or judge question/context (dialogue), `used_by_rules`, `implementation`. |
| `agent/predicates/{context,airline,retail}.py` | Pure-Python predicate implementations: `(tool_call, trajectory, config) -> bool \| None`. |
| `policies/tau_bench/{domain}_tools.json`, `{domain}_data_notes.md` | τ-bench tool specs with `api_checks` (from `scripts/extract_tau_tools.py`, AST only) and the data formats predicates rely on. |
| `scripts/validate_aspm.py` | ASPM validation, logic check, and `--firing` offline analysis. |
| `tests/predicates/` | Unit tests on real τ-bench records (`fixtures/tau_records.json`, built by `build_fixtures.py`). |
| `docs/step2_aspm/firing_analysis.md` | Offline firing analysis on τ-bench recorded trajectories. |

Rebuild and check:
```
python scripts/build_aspm.py
python scripts/validate_aspm.py --firing
python -m unittest discover -s tests -t .
python scripts/validate_curated_rules.py
```

## 1. What the runtime code requires (verified in `agent/tools/*.py`)

| Constraint | Where in the code | Consequence for the ASPM |
|---|---|---|
| Rule ids sort with `int(rule_id)` | `aspm_tool.formulate_solution_space` l.375 | `rule_id` is `"1"`…`"N"`. The curated id is kept in `curated_rule_id`. |
| Predicates are read as `pred[0]`, `pred[1]`, `pred[3]` | `formulate_solution_space` l.384-389 | Entries are `[name, description, "", "action"\|"condition"]`. |
| `get_action_circuit` errors if `not aspm_actions.get(name)` | l.217 | **Every tree node needs a non-empty dict** in `actions`; an empty `{}` fails as well. Each entry carries `soft_rule_ids`, `level` and `description`. |
| `agent.py` adds the upstream nodes of every grounded action before calling `get_action_circuit` | `agent.py` l.380-385 | Family rules sit on the L1/L2 group node and are inherited, never duplicated. The validator replays this for every tool. |
| `validate_rule_consistency` strips `IMPLIES/AND/OR/NOT/ALWAYS/EVENTUALLY/UNTIL/(/)` by plain `str.replace` | l.316-343 | Predicate names are lower-case `snake_case`, so no operator substring can occur. |
| `logic_to_python` rewrites `AND/OR/NOT` by string replacement, then applies one non-greedy regex to the **first** `IMPLIES` | `certification.py` l.51-69 | Exactly one top-level `IMPLIES`. No nesting, no temporal operators. The action predicate, or a conjunction containing it, goes on the left. |
| `get_rules_info` returns only `predicates, logic, description, rule_type` | `aspm_tool.py` l.189-205 | `curated_rule_id`, `enforcement`, `api_enforced`, `verification_types`, `attached_to` and `notes` are **ignored by the loader**, so they are safe to add. They also **never reach** the runtime pipeline, so Step 3 must read them from the JSON itself. |
| `load_aspm_json` reads only `action_tree`, `actions`, `rule_list`, `condition_clusters` | l.155-186 | A top-level `meta` block is safe. `condition_clusters` is stored but used nowhere; it holds the predicate names grouped by type. |
| The `L3_children` of a dict child get layer + 1 | `ActionTree.from_dict` | Three-level trees work; `get_upstream_actions` returns both ancestors. |

## 2. Action trees

### Airline (22 nodes, 64 rules)
```
booking_db_write (L1)  confirmation (AIR-R001/R002), turn format
├── book_reservation
├── cancel_reservation
└── modify_reservation (L2)  user id + reservation id obtained (AIR-R026/R027)
    ├── update_reservation_flights
    ├── update_reservation_baggages
    └── update_reservation_passengers
compensation (L1) ── send_certificate
escalation (L1) ── transfer_to_human_agents
messaging (L1) ── respond_to_user          (pseudo-action)
read_only_lookup (L1) ── get_user_details, get_reservation_details, search_direct_flight, search_onestop_flight, list_all_airports
utility (L1) ── calculate, think
```
- `booking_db_write` matches the wiki's own scope for confirmation ("any actions that update the booking database"), including the *interpretation* that cancellation belongs to it. Ablating that interpretation means moving `cancel_reservation` out from under this node.
- `send_certificate` gets its own L1 node because the confirmation rules deliberately exclude it.
- `modify_reservation` exists because AIR-MOD-01 ("first obtain the user id and the reservation id") is one clause covering the three update tools. Cancellation has its own copy of that clause (AIR-CAN-01) and its own curated rules, attached to `cancel_reservation`.
- Read and utility tools are in the tree so that the global turn-format rules have somewhere to attach, and so that a later ablation can shield them. They are **not** shielded in the Step 4 default.

### Retail (25 nodes, 55 rules)
```
authentication (L1) ── find_user_id_by_email, find_user_id_by_name_zip
information_access (L1)  authenticated + ownership (RET-R001/R002)
    ── get_user_details, get_order_details, get_product_details, list_all_product_types
db_write (L1)  authenticated, ownership, confirmation (RET-R001/R002/R004/R005), turn format
├── modify_user_address
├── pending_order_write (L2)  status exactly 'pending' (RET-R013), status looked up (RET-R015)
│   └── cancel_pending_order, modify_pending_order_address, modify_pending_order_payment, modify_pending_order_items
└── delivered_order_write (L2)  status exactly 'delivered' (RET-R014), status looked up (RET-R015)
    └── return_delivered_order_items, exchange_delivered_order_items
escalation (L1) ── transfer_to_human_agents
messaging (L1) ── respond_to_user
utility (L1) ── calculate, think
```
- The tree groups by **order status**, because status preconditions are the main block-critical family.
- The item-change rules (RET-R012, R018, R019, R025–R029) apply to both `modify_pending_order_items` and `exchange_delivered_order_items`, which sit in different status groups. Each therefore appears twice, once per tool. A node can have only one parent, so the tree cannot express both groupings at once.
- `authentication` is separate from `information_access` so that RET-R001 ("authenticate first") does not gate the authentication tools themselves.

### Rules at L1 vs L2 vs L3

| | L1 (family-wide) | L2 | L3 |
|---|---|---|---|
| airline | 13: confirmation ×2, turn-format replicas ×11 | 39: tool-specific plus `modify_reservation` (2) | 12: the update tools |
| retail | 18: auth/ownership/confirmation on `db_write` and `information_access`; turn-format replicas ×11; second-user lookup | 12: status rules on the two order groups, `get_product_details`, transfer, messaging | 25: pending/delivered order tools |

**Global (`*`) rules.** The turn-format rules AIR-R005/R006 and RET-R008/R009 have no single node to live on, because every action has exactly one parent. They are replicated **once per L1 node** (5 L1 nodes for R005/R008, 6 for R006/R009), each with that L1 node as its action predicate. This is replication across siblings, not duplication on children.

Effective circuit size (own rules plus inherited) per tool:
- **airline:** `book_reservation` 20, `update_reservation_flights` 13, `update_reservation_baggages` 10, `cancel_reservation` 9, `respond_to_user` 9, `send_certificate` 8, `update_reservation_passengers` 7, `transfer_to_human_agents` 4, read/utility tools 2;
- **retail:** `modify_pending_order_items` 17, `exchange_delivered_order_items` 17, `return_delivered_order_items` 11, `cancel_pending_order` 10, `modify_pending_order_payment` 10, `modify_pending_order_address` 8, `respond_to_user` 7, `modify_user_address` 6, `get_product_details` 5, other reads 4, authentication 3, transfer 3, utility 2.

## 3. Predicate vocabulary

- **Names.** Lower-case `snake_case`, one vocabulary per domain. Names are shared across domains where the meaning is the same (`action_details_listed`, `explicit_user_confirmation`, `request_out_of_scope`, `user_explicitly_requested_human`, `message_contains_*`, `single_tool_call_in_turn`, `text_with_tool_call`).
- **Action predicates** are exact τ-bench tool names, `respond_to_user`, or group-node names.
- **Condition predicates** are named for the fact they assert: `booked_within_24h`, `order_status_is_pending`, `replacement_items_differ`.
- **Negation.** Predicates are phrased positively and negated in the logic, e.g. `NOT any_segment_departed` and `NOT text_with_tool_call`.

| Domain | `state` | `tool_log` | `structural` | `dialogue` | Total condition predicates | Rules fully evaluable in Python |
|---|---|---|---|---|---|---|
| airline | 32 | 4 | 2 | 26 | 64 | 42 of 64 |
| retail | 16 | 4 | 2 | 15 | 37 | 38 of 55 |

Implementation conventions (`agent/predicates/context.py`):
- **`latest_object(traj, kind, id)`.** "Current state" is the latest object for that id in any successful tool output, *including the agent's own writes*. RET-R013 depends on this: after `modify_pending_order_items` the tool returns the order with status `pending (item modified)`, and every later cancel or modify fails `order_status_is_pending`. The unit test `test_ret_r013_blocks_second_modify_after_items_modified` evaluates this through the real rule logic and `logic_to_python`. A mutation test (switching to a `startswith("pending")` match) makes 5 assertions fail.
- **User records have no `user_id` key.** They are associated with the call argument of `get_user_details` / `modify_user_address`.
- **Effective cabin.** τ-bench `update_reservation_flights` never writes `reservation.cabin`. The cabin is therefore taken from the latest successful upgrade call (`with_effective_cabin`). The firing analysis surfaced this.
- **`None`, never a guess.** Examples: an unseen reservation, a fare that was never searched, a segment dated today.
- **`authenticated_user_id`.** Retail: the first successful `find_user_id_*` result. Airline: the first successful `get_user_details`.

## 4. How the temporal clauses became predicates

No temporal operators are used. Every ordering clause became a history predicate.

| Clause (curated rule) | Predicate | Type |
|---|---|---|
| List details, then explicit "yes", before a write (AIR-R001/R002, RET-R004/R005) | `action_details_listed`, `explicit_user_confirmation` | dialogue |
| One tool call per turn; no text with a tool call (AIR-R005/R006, RET-R008/R009) | `single_tool_call_in_turn`, `text_with_tool_call` | structural |
| First user id, then trip details (AIR-R011/R012) | `user_id_obtained_before_trip_details`, `trip_details_collected` | dialogue |
| Ask about insurance before booking (AIR-R024) | `insurance_offered` | dialogue |
| First obtain user id and reservation id (AIR-R026/R027/R039/R040) | `reservation_owner_identified` (successful `get_user_details` **or** verbatim id in a user message), `reservation_details_retrieved` | tool_log |
| Obtain the cancellation reason first (AIR-R041) | `cancellation_reason_obtained` | dialogue |
| Ask the user for the payment method of a flight change (AIR-R038) | `payment_method_chosen_by_user` | dialogue |
| Certificate only after confirming the facts (AIR-R047) | `reservation_facts_checked` | tool_log |
| Delayed-flight certificate only after the change/cancellation (AIR-R049) | `focus_reservation_changed_or_cancelled` | tool_log |
| Compensation only after a complaint and an explicit request (AIR-R046) | `user_complained`, `user_explicitly_requested_compensation` | dialogue |
| Within 24 h of booking (AIR-R042) | `booked_within_24h` (config `current_time`) | state |
| Authenticate at the beginning (RET-R001) | `user_authenticated` | tool_log |
| Check the status before acting (RET-R015) | `order_status_checked` | tool_log |
| Modify items / exchange only once (RET-R016/R017) | `items_modified_before_for_order`, `exchange_done_before_for_order` (also implied by the latest status) | tool_log |
| Remind the user to confirm all items (RET-R019) | `user_reminded_to_confirm_all_items` | dialogue |
| User confirms id and reason / return details (RET-R020/R030) | `user_confirmed_order_id_and_reason`, `user_confirmed_return_details` | dialogue |
| User provides the payment method for the price difference (RET-R028) | `payment_method_provided_by_user` | dialogue |

## 5. Enforcement and API overlap

| | block | warn | api_enforced = true | api_enforced = false |
|---|---|---|---|---|
| airline | 45 | 19 | 9 | 55 |
| retail | 32 | 23 | 18 | 37 |

**`block`** covers consent before writes, eligibility, limits, statuses, ownership, once-per-order, transfers, and compensation. **`warn`** covers:
- dialogue ordering (AIR-R011/R012/R024/R041/R038, RET-R018/R019/R020/R028/R030);
- every `respond_to_user` rule;
- the text-with-tool-call rules.

Borderline cases:
- **Turn format.** AIR-R005/RET-R008 (one call per turn) is `block`: it is exact, and parallel calls could chain writes without a confirmation in between. AIR-R006/RET-R009 (text with a tool call) is `warn`: it is pure format, and it fires on 68–73% of write calls of both recorded models.
- **Dialogue-judged but `block`.**
  - AIR-R001/R002 and RET-R004/R005 (consent).
  - AIR-R046 (compensation without a request): money leaves the system.
  - AIR-R008/R036 and RET-R010 (transfers): a wrong transfer ends the τ-bench episode.

  These depend on an LLM judge, so Step 3 must handle judge uncertainty (`unknown` → `None`).
- **RET-R027 (new item ≠ old item)** was **downgraded to `warn`** after the firing analysis. τ-bench ground truth requires same-item exchanges (tasks 18 and 108).
- **RET-R002 on the authentication tools** (a lookup targets a second identity) is `warn`. A lookup is read-only, and a user may legitimately mistype their email.

**`api_enforced`** is true iff a guard in the tool implementation rejects the violating call (`policies/tau_bench/*_tools.json → api_checks`). Two kinds also count as enforced:
- **schema-unrepresentable** violations: AIR-R015/R032, one cabin per call;
- **API-computed prices**: AIR-R023/R025, where the payment total must equal the API's own total.

**The wiki's claim is confirmed in the source:**
- `cancel_reservation` has no guard besides "reservation not found";
- `update_reservation_flights` checks only flight existence, availability, seats and payment, so basic economy, origin/destination and trip type go unchecked.

So AIR-R028–R030, R042 and R043 are `api_enforced: false`. Other notable gaps:
- the airline API checks neither the passenger count (≤ 5) nor the payment-method counts;
- `send_certificate` checks nothing;
- the retail API checks neither ownership, nor authentication, nor "new item ≠ old item".

## 6. Curated rules that could not be expressed cleanly

| Curated | Issue | How it is represented |
|---|---|---|
| AIR-R005/R006, RET-R008/R009 | Global (`*`); no single node | Replicated per L1 node (§2). |
| AIR-R007 (deny requests against policy) | Meta-rule | Its action part is realised by all the other rules. Message part: `respond_to_user IMPLIES NOT message_accepts_policy_violating_request`. Its precedence over the explicit-request transfer permission is encoded in AIR-R008 (`AND NOT request_violates_policy`). |
| AIR-R009, RET-R011, AIR-R044 (must transfer) | Liveness obligations: the violation is the *absence* of a transfer | Message-level proxies (`message_refuses_out_of_scope_request_without_transfer`, `message_announces_transfer`), `warn`. |
| AIR-R031 (pay the fare difference), AIR-R034 (no insurance after booking), RET-R022 (nothing else modifiable) | No tool can violate them | Tool part: API-computed or impossible. Message-level rules, `warn`. |
| AIR-R023 on `update_reservation_baggages` | The API charges 50 × added non-free bags itself | No rule on that tool (noted on rule 27). |
| AIR-R015, AIR-R032 | The schema makes them unviolable | Trivial schema predicates (`passengers_share_flights_and_cabin`, `single_cabin_for_all_flights`). |
| AIR-R042 | "Airline cancelled a flight" is **not observable**: no v1 tool returns a non-`available` status. "Reason is health/weather" is the user's statement. | Both are `dialogue` predicates; the rest is `state`. In the data, cancelled flights exist only on past dates. |
| AIR-R043 | "Flown" is not observable | Date-based: a past-dated segment counts as departed; a same-day segment gives `None`. Limitation: a past segment the airline cancelled also counts as departed. |
| AIR-R047 ("after confirming the facts") | Only the reservation lookup is observable, not the flight's cancellation/delay | `reservation_facts_checked` (tool_log). |
| AIR-R020–R022 | The wiki's allowance is per passenger; the tool takes totals | Pooled allowance, exact equality (A2.7); tier and cabin as rule antecedents. |
| AIR-R023 vs AIR-R025 | Both are checked by the same total-price predicate | Two ASPM rules with the same consequent; AIR-R025 is redundant given AIR-R023 but kept for 1:1 coverage. |
| RET-R001 (no disclosure before authentication) | The disclosure is in messages | `respond_to_user IMPLIES (user_authenticated OR NOT message_discloses_account_information)` mixes tool_log and dialogue. |
| RET-R012 | Ids the agent has never seen cannot be classified | `new_item_ids_are_item_ids` returns `None` if an id is neither a known product id nor a known item id. |

## 7. `reservation_in_focus` (send_certificate)

`send_certificate(user_id, amount)` names no reservation, yet AIR-R045/R048/R050 need the reservation's insurance, cabin and passenger count. The heuristic is: **the reservation of `user_id` that appeared most recently in any successful tool output** (a lookup or a write), with the effective cabin.

**Limits:**
1. If the agent looked at several reservations after the complaint, the last one wins, even if the complaint concerned another. The amount check (×100 / ×50 per passenger) can then be wrong.
2. If no reservation of that user was seen, the result is `None` and the eligibility and amount rules become not evaluable. AIR-R047 (`reservation_facts_checked`) then fires, which is the intended behaviour.
3. Passengers are counted on the current reservation object. After a cancellation the record still lists them, which is fine.
4. Which flight was complained about, and whether it was cancelled or delayed, is decided only by the dialogue predicates `complaint_is_cancelled_flight` / `complaint_is_delayed_flight`.

**Recommendation for Step 3:** let the dialogue judge also name the reservation id the complaint is about, and prefer that over the heuristic when present.

## 8. ⚠ Flags for Step 3 (runtime)

1. **`formulate_solution_space` breaks the link to the Python predicates.** It asks an LLM to filter, rename and re-ground every predicate per context ("create concrete versions of the predicates"; "submit_data can be grounded to post_data_1 and post_data_2"). The grounded names no longer match `agent/predicates/*.PREDICATES`, and a deterministic predicate would end up valued by the planning LLM. **Proposed Step 3 design:**
   1. **Action grounding without an LLM** for tool calls. The tool name is known, so the grounded actions are {tool} ∪ ancestors from `ActionTree.get_upstream_actions`. `respond_to_user` likewise. Keep `action_grounding` only for free-form actions, which τ-bench does not have.
   2. `get_action_circuit` as is.
   3. **Skip `formulate_solution_space`** for rules whose condition predicates are all Python-typed. Evaluate them with canonical names via `agent/predicates/{domain}.PREDICATES` (and `with_effective_cabin` etc.).
   4. For rules with `dialogue` predicates, send **only those predicates** to the LLM judge, using the registry's `judge.question` / `judge.context`. Keep canonical names and use no free-form grounding.
   5. Only then run certification.
2. **Use a correct evaluator.** `logic_to_python` is correct for this grammar (648 assignments verified), but it breaks with nested IMPLIES (bug #1). Prefer the parser in `scripts/validate_aspm.py` (`Parser` + `kleene`) as the certifier. It also gives Kleene semantics for `None`.
3. **`None` / missing values.** `verify_fol_rules` reports a rule as **Violated** when any predicate value is missing (l.155-164), and the sanity check in `initialize_verification_state` is broken (bug #2). Step 3 needs an explicit policy: evaluate with Kleene logic, then for an undetermined `block` rule either ask the judge or allow and log. Do not deny silently.
4. **Predicate tuple shapes differ.** `verification.create_predicate_map` unpacks grounded predicates as 3-tuples `(name, description, type)` (l.61), while ASPM predicates are 4-element lists. Convert explicitly if those tools are reused.
5. **Enforcement metadata is stripped.** `get_rules_info` drops `enforcement` / `api_enforced`, so the decision step must read them from the ASPM JSON. Proposed decision: deny iff a `block` rule is violated; feed `warn` violations back as advisory text; report the curated rule ids and descriptions.
6. **`api_enforced` rules** can be skipped for latency, or kept to catch the violation *before* the API error. The firing analysis shows they would pre-empt 62 of 94 rejected retail calls in reward-1 runs.
7. **The runtime agent is not on Azure.** `agent/agent.py` uses the openai-agents SDK with `OPENAI_API_KEY` (orientation summary). Fix this before any LLM-judge calls.

## 9. Circuits to shield in the initial Step 4 run

- **Default (write tools only):**
  - airline: `book_reservation`, `cancel_reservation`, `update_reservation_flights`, `update_reservation_baggages`, `update_reservation_passengers`, `send_certificate`;
  - retail: `cancel_pending_order`, `modify_pending_order_address`, `modify_pending_order_payment`, `modify_pending_order_items`, `modify_user_address`, `return_delivered_order_items`, `exchange_delivered_order_items`.
- **Later ablations:**
  1. `transfer_to_human_agents`: not a DB write, but it ends the episode;
  2. the `respond_to_user` circuit (message-level rules, all `warn`);
  3. read tools (RET-R001 gating);
  4. `cancel_reservation` outside the airline confirmation scope (A1.4 interpretation);
  5. RET-R027 as `block`.
- **Expected effect (Python layer only, from the firing analysis):** on correct-outcome airline runs the shield would block 18 of 181 accepted write calls. Of these:
  - 11 are "obtain the user id first" (AIR-R026/R039): the agent should recover by asking for the id;
  - 5 are the NQNU5R ground-truth conflict: τ-bench tasks 26/27 would lose reward by design;
  - 2 are genuine basic-economy and certificate violations.

## 10. Open questions
1. **AIR-R043 vs τ-bench tasks 26/27.** The ground truth cancels NQNU5R, a fully flown trip. Keep the wiki rule (and accept the lost reward), or treat it as a benchmark label error?
2. **RET-R027 vs τ-bench tasks 18/108.** The ground truth exchanges an item for the identical item. Keep `warn`, or reinterpret "different product option"?
3. **"Airline cancelled the flight."** It is unobservable, so the dialogue predicate trusts the user's statement. In the data no future flight is cancelled. Should a user's claim that a *future* flight was cancelled be treated as false (a data-specific shortcut)?
4. **AIR-R026/R039 strictness.** Keep `block` (the agent must ask for the user id), or downgrade to `warn`, given that the outcome is unaffected?
5. **`None` policy** for `block` rules at runtime (§8.3).

## Appendix: all ASPM rules

Generated from `aspm/*_aspm.json`. **needs** = the data types of the condition predicates.

### Airline ASPM rules

| id | curated | attached to | logic | enf. | API | needs |
|---|---|---|---|---|---|---|
| 1 | AIR-R001 | booking_db_write (L1) | `booking_db_write IMPLIES action_details_listed` | block | no | dialogue |
| 2 | AIR-R002 | booking_db_write (L1) | `booking_db_write IMPLIES explicit_user_confirmation` | block | no | dialogue |
| 3 | AIR-R005 | booking_db_write (L1) | `booking_db_write IMPLIES single_tool_call_in_turn` | block | no | structural |
| 4 | AIR-R005 | compensation (L1) | `compensation IMPLIES single_tool_call_in_turn` | block | no | structural |
| 5 | AIR-R005 | escalation (L1) | `escalation IMPLIES single_tool_call_in_turn` | block | no | structural |
| 6 | AIR-R005 | read_only_lookup (L1) | `read_only_lookup IMPLIES single_tool_call_in_turn` | block | no | structural |
| 7 | AIR-R005 | utility (L1) | `utility IMPLIES single_tool_call_in_turn` | block | no | structural |
| 8 | AIR-R006 | booking_db_write (L1) | `booking_db_write IMPLIES NOT text_with_tool_call` | warn | no | structural |
| 9 | AIR-R006 | compensation (L1) | `compensation IMPLIES NOT text_with_tool_call` | warn | no | structural |
| 10 | AIR-R006 | escalation (L1) | `escalation IMPLIES NOT text_with_tool_call` | warn | no | structural |
| 11 | AIR-R006 | read_only_lookup (L1) | `read_only_lookup IMPLIES NOT text_with_tool_call` | warn | no | structural |
| 12 | AIR-R006 | utility (L1) | `utility IMPLIES NOT text_with_tool_call` | warn | no | structural |
| 13 | AIR-R006 | messaging (L1) | `messaging IMPLIES NOT text_with_tool_call` | warn | no | structural |
| 14 | AIR-R010 | book_reservation (L2) | `book_reservation IMPLIES all_new_flights_available` | block | yes | state |
| 15 | AIR-R011 | book_reservation (L2) | `book_reservation IMPLIES user_id_obtained_before_trip_details` | warn | no | dialogue |
| 16 | AIR-R012 | book_reservation (L2) | `book_reservation IMPLIES trip_details_collected` | warn | no | dialogue |
| 17 | AIR-R013 | book_reservation (L2) | `book_reservation IMPLIES passenger_count_at_most_five` | block | no | state |
| 18 | AIR-R014 | book_reservation (L2) | `book_reservation IMPLIES all_passengers_have_name_and_dob` | block | no | state |
| 19 | AIR-R015 | book_reservation (L2) | `book_reservation IMPLIES passengers_share_flights_and_cabin` | block | yes | state |
| 20 | AIR-R016 | book_reservation (L2) | `book_reservation IMPLIES certificate_count_at_most_one` | block | no | state |
| 21 | AIR-R017 | book_reservation (L2) | `book_reservation IMPLIES credit_card_count_at_most_one` | block | no | state |
| 22 | AIR-R018 | book_reservation (L2) | `book_reservation IMPLIES gift_card_count_at_most_three` | block | no | state |
| 23 | AIR-R019 | book_reservation (L2) | `book_reservation IMPLIES payment_methods_in_user_profile` | block | yes | state |
| 24 | AIR-R020 | book_reservation (L2) | `(book_reservation AND booking_user_is_regular) IMPLIES nonfree_baggages_match_tier_allowance` | block | no | state |
| 25 | AIR-R021 | book_reservation (L2) | `(book_reservation AND booking_user_is_silver) IMPLIES nonfree_baggages_match_tier_allowance` | block | no | state |
| 26 | AIR-R022 | book_reservation (L2) | `(book_reservation AND booking_user_is_gold) IMPLIES nonfree_baggages_match_tier_allowance` | block | no | state |
| 27 | AIR-R023 | book_reservation (L2) | `book_reservation IMPLIES payment_total_matches_price` | block | yes | state |
| 28 | AIR-R024 | book_reservation (L2) | `book_reservation IMPLIES insurance_offered` | warn | no | dialogue |
| 29 | AIR-R025 | book_reservation (L2) | `(book_reservation AND insurance_purchased) IMPLIES payment_total_matches_price` | block | yes | state |
| 30 | AIR-R039 | cancel_reservation (L2) | `cancel_reservation IMPLIES reservation_owner_identified` | block | no | tool_log |
| 31 | AIR-R040 | cancel_reservation (L2) | `cancel_reservation IMPLIES reservation_details_retrieved` | block | no | tool_log |
| 32 | AIR-R041 | cancel_reservation (L2) | `cancel_reservation IMPLIES cancellation_reason_obtained` | warn | no | dialogue |
| 33 | AIR-R042 | cancel_reservation (L2) | `cancel_reservation IMPLIES (cabin_is_business OR booked_within_24h OR airline_cancelled_flight OR (reservation_has_insurance AND cancellation_reason_is_health_or_weather))` | block | no | dialogue, state |
| 34 | AIR-R043 | cancel_reservation (L2) | `cancel_reservation IMPLIES NOT any_segment_departed` | block | no | state |
| 35 | AIR-R026 | modify_reservation (L2) | `modify_reservation IMPLIES reservation_owner_identified` | block | no | tool_log |
| 36 | AIR-R027 | modify_reservation (L2) | `modify_reservation IMPLIES reservation_details_retrieved` | block | no | tool_log |
| 37 | AIR-R010 | update_reservation_flights (L3) | `update_reservation_flights IMPLIES all_new_flights_available` | block | yes | state |
| 38 | AIR-R028 | update_reservation_flights (L3) | `(update_reservation_flights AND reservation_is_basic_economy) IMPLIES flights_unchanged` | block | no | state |
| 39 | AIR-R029 | update_reservation_flights (L3) | `update_reservation_flights IMPLIES itinerary_endpoints_preserved` | block | no | state |
| 40 | AIR-R030 | update_reservation_flights (L3) | `update_reservation_flights IMPLIES trip_type_preserved` | block | no | state |
| 41 | AIR-R032 | update_reservation_flights (L3) | `update_reservation_flights IMPLIES single_cabin_for_all_flights` | block | yes | state |
| 42 | AIR-R037 | update_reservation_flights (L3) | `(update_reservation_flights AND flights_changed) IMPLIES payment_is_gift_card_or_credit_card` | block | yes | state |
| 43 | AIR-R038 | update_reservation_flights (L3) | `(update_reservation_flights AND flights_changed) IMPLIES payment_method_chosen_by_user` | warn | no | dialogue, state |
| 44 | AIR-R020 | update_reservation_baggages (L3) | `(update_reservation_baggages AND booking_user_is_regular) IMPLIES nonfree_baggages_match_tier_allowance` | block | no | state |
| 45 | AIR-R021 | update_reservation_baggages (L3) | `(update_reservation_baggages AND booking_user_is_silver) IMPLIES nonfree_baggages_match_tier_allowance` | block | no | state |
| 46 | AIR-R022 | update_reservation_baggages (L3) | `(update_reservation_baggages AND booking_user_is_gold) IMPLIES nonfree_baggages_match_tier_allowance` | block | no | state |
| 47 | AIR-R033 | update_reservation_baggages (L3) | `update_reservation_baggages IMPLIES total_baggages_not_decreased` | block | no | state |
| 48 | AIR-R035 | update_reservation_passengers (L3) | `update_reservation_passengers IMPLIES passenger_count_unchanged` | block | yes | state |
| 49 | AIR-R045 | send_certificate (L2) | `send_certificate IMPLIES (user_is_silver_or_gold OR focus_reservation_has_insurance OR focus_reservation_is_business)` | block | no | state |
| 50 | AIR-R046 | send_certificate (L2) | `send_certificate IMPLIES (user_complained AND user_explicitly_requested_compensation)` | block | no | dialogue |
| 51 | AIR-R047 | send_certificate (L2) | `send_certificate IMPLIES reservation_facts_checked` | block | no | tool_log |
| 52 | AIR-R048 | send_certificate (L2) | `(send_certificate AND complaint_is_cancelled_flight) IMPLIES certificate_amount_is_100_per_passenger` | block | no | dialogue, state |
| 53 | AIR-R049 | send_certificate (L2) | `(send_certificate AND complaint_is_delayed_flight) IMPLIES focus_reservation_changed_or_cancelled` | block | no | dialogue, tool_log |
| 54 | AIR-R050 | send_certificate (L2) | `(send_certificate AND complaint_is_delayed_flight) IMPLIES certificate_amount_is_50_per_passenger` | block | no | dialogue, state |
| 55 | AIR-R008 | transfer_to_human_agents (L2) | `transfer_to_human_agents IMPLIES (request_out_of_scope OR (user_explicitly_requested_human AND NOT request_violates_policy))` | block | no | dialogue |
| 56 | AIR-R036 | transfer_to_human_agents (L2) | `transfer_to_human_agents IMPLIES NOT request_is_passenger_count_change` | block | no | dialogue |
| 57 | AIR-R003 | respond_to_user (L2) | `respond_to_user IMPLIES NOT message_contains_unsupported_information` | warn | no | dialogue |
| 58 | AIR-R004 | respond_to_user (L2) | `respond_to_user IMPLIES NOT message_contains_subjective_recommendation` | warn | no | dialogue |
| 59 | AIR-R007 | respond_to_user (L2) | `respond_to_user IMPLIES NOT message_accepts_policy_violating_request` | warn | no | dialogue |
| 60 | AIR-R009 | respond_to_user (L2) | `respond_to_user IMPLIES NOT message_refuses_out_of_scope_request_without_transfer` | warn | no | dialogue |
| 61 | AIR-R031 | respond_to_user (L2) | `respond_to_user IMPLIES NOT message_waives_cabin_fare_difference` | warn | no | dialogue |
| 62 | AIR-R034 | respond_to_user (L2) | `respond_to_user IMPLIES NOT message_offers_insurance_after_booking` | warn | no | dialogue |
| 63 | AIR-R044 | respond_to_user (L2) | `(respond_to_user AND user_requests_cancellation_of_flown_reservation) IMPLIES message_announces_transfer` | warn | no | dialogue |
| 64 | AIR-R046 | respond_to_user (L2) | `respond_to_user IMPLIES NOT message_offers_unrequested_compensation` | warn | no | dialogue |

### Retail ASPM rules

| id | curated | attached to | logic | enf. | API | needs |
|---|---|---|---|---|---|---|
| 1 | RET-R008 | authentication (L1) | `authentication IMPLIES single_tool_call_in_turn` | block | no | structural |
| 2 | RET-R008 | information_access (L1) | `information_access IMPLIES single_tool_call_in_turn` | block | no | structural |
| 3 | RET-R008 | db_write (L1) | `db_write IMPLIES single_tool_call_in_turn` | block | no | structural |
| 4 | RET-R008 | escalation (L1) | `escalation IMPLIES single_tool_call_in_turn` | block | no | structural |
| 5 | RET-R008 | utility (L1) | `utility IMPLIES single_tool_call_in_turn` | block | no | structural |
| 6 | RET-R009 | authentication (L1) | `authentication IMPLIES NOT text_with_tool_call` | warn | no | structural |
| 7 | RET-R009 | information_access (L1) | `information_access IMPLIES NOT text_with_tool_call` | warn | no | structural |
| 8 | RET-R009 | db_write (L1) | `db_write IMPLIES NOT text_with_tool_call` | warn | no | structural |
| 9 | RET-R009 | escalation (L1) | `escalation IMPLIES NOT text_with_tool_call` | warn | no | structural |
| 10 | RET-R009 | utility (L1) | `utility IMPLIES NOT text_with_tool_call` | warn | no | structural |
| 11 | RET-R009 | messaging (L1) | `messaging IMPLIES NOT text_with_tool_call` | warn | no | structural |
| 12 | RET-R002 | authentication (L1) | `authentication IMPLIES NOT auth_lookup_targets_other_user` | warn | no | state |
| 13 | RET-R001 | information_access (L1) | `information_access IMPLIES user_authenticated` | block | no | tool_log |
| 14 | RET-R002 | information_access (L1) | `information_access IMPLIES all_referenced_entities_owned` | block | no | state |
| 15 | RET-R012 | get_product_details (L2) | `get_product_details IMPLIES NOT product_id_arg_is_known_item_id` | block | yes | state |
| 16 | RET-R001 | db_write (L1) | `db_write IMPLIES user_authenticated` | block | no | tool_log |
| 17 | RET-R002 | db_write (L1) | `db_write IMPLIES all_referenced_entities_owned` | block | no | state |
| 18 | RET-R004 | db_write (L1) | `db_write IMPLIES action_details_listed` | block | no | dialogue |
| 19 | RET-R005 | db_write (L1) | `db_write IMPLIES explicit_user_confirmation` | block | no | dialogue |
| 20 | RET-R013 | pending_order_write (L2) | `pending_order_write IMPLIES order_status_is_pending` | block | yes | state |
| 21 | RET-R015 | pending_order_write (L2) | `pending_order_write IMPLIES order_status_checked` | block | no | tool_log |
| 22 | RET-R014 | delivered_order_write (L2) | `delivered_order_write IMPLIES order_status_is_delivered` | block | yes | state |
| 23 | RET-R015 | delivered_order_write (L2) | `delivered_order_write IMPLIES order_status_checked` | block | no | tool_log |
| 24 | RET-R020 | cancel_pending_order (L3) | `cancel_pending_order IMPLIES user_confirmed_order_id_and_reason` | warn | no | dialogue |
| 25 | RET-R021 | cancel_pending_order (L3) | `cancel_pending_order IMPLIES cancel_reason_is_valid` | block | yes | state |
| 26 | RET-R023 | modify_pending_order_payment (L3) | `modify_pending_order_payment IMPLIES payment_differs_from_original` | block | yes | state |
| 27 | RET-R024 | modify_pending_order_payment (L3) | `(modify_pending_order_payment AND new_payment_is_gift_card) IMPLIES gift_card_covers_order_total` | block | yes | state |
| 28 | RET-R016 | modify_pending_order_items (L3) | `modify_pending_order_items IMPLIES NOT items_modified_before_for_order` | block | yes | tool_log |
| 29 | RET-R018 | modify_pending_order_items (L3) | `modify_pending_order_items IMPLIES all_requested_items_included` | warn | no | dialogue |
| 30 | RET-R019 | modify_pending_order_items (L3) | `modify_pending_order_items IMPLIES user_reminded_to_confirm_all_items` | warn | no | dialogue |
| 31 | RET-R025 | modify_pending_order_items (L3) | `modify_pending_order_items IMPLIES replacement_items_same_product` | block | yes | state |
| 32 | RET-R026 | modify_pending_order_items (L3) | `modify_pending_order_items IMPLIES replacement_items_available` | block | yes | state |
| 33 | RET-R027 | modify_pending_order_items (L3) | `modify_pending_order_items IMPLIES replacement_items_differ` | warn | no | state |
| 34 | RET-R028 | modify_pending_order_items (L3) | `modify_pending_order_items IMPLIES payment_method_provided_by_user` | warn | no | dialogue |
| 35 | RET-R029 | modify_pending_order_items (L3) | `(modify_pending_order_items AND new_payment_is_gift_card) IMPLIES gift_card_covers_price_difference` | block | yes | state |
| 36 | RET-R012 | modify_pending_order_items (L3) | `modify_pending_order_items IMPLIES (item_ids_are_order_items AND new_item_ids_are_item_ids)` | block | yes | state |
| 37 | RET-R017 | exchange_delivered_order_items (L3) | `exchange_delivered_order_items IMPLIES NOT exchange_done_before_for_order` | block | yes | tool_log |
| 38 | RET-R018 | exchange_delivered_order_items (L3) | `exchange_delivered_order_items IMPLIES all_requested_items_included` | warn | no | dialogue |
| 39 | RET-R019 | exchange_delivered_order_items (L3) | `exchange_delivered_order_items IMPLIES user_reminded_to_confirm_all_items` | warn | no | dialogue |
| 40 | RET-R025 | exchange_delivered_order_items (L3) | `exchange_delivered_order_items IMPLIES replacement_items_same_product` | block | yes | state |
| 41 | RET-R026 | exchange_delivered_order_items (L3) | `exchange_delivered_order_items IMPLIES replacement_items_available` | block | yes | state |
| 42 | RET-R027 | exchange_delivered_order_items (L3) | `exchange_delivered_order_items IMPLIES replacement_items_differ` | warn | no | state |
| 43 | RET-R028 | exchange_delivered_order_items (L3) | `exchange_delivered_order_items IMPLIES payment_method_provided_by_user` | warn | no | dialogue |
| 44 | RET-R029 | exchange_delivered_order_items (L3) | `(exchange_delivered_order_items AND new_payment_is_gift_card) IMPLIES gift_card_covers_price_difference` | block | yes | state |
| 45 | RET-R012 | exchange_delivered_order_items (L3) | `exchange_delivered_order_items IMPLIES (item_ids_are_order_items AND new_item_ids_are_item_ids)` | block | yes | state |
| 46 | RET-R030 | return_delivered_order_items (L3) | `return_delivered_order_items IMPLIES user_confirmed_return_details` | warn | no | dialogue |
| 47 | RET-R031 | return_delivered_order_items (L3) | `return_delivered_order_items IMPLIES refund_to_original_or_gift_card` | block | yes | state |
| 48 | RET-R012 | return_delivered_order_items (L3) | `return_delivered_order_items IMPLIES item_ids_are_order_items` | block | yes | state |
| 49 | RET-R010 | transfer_to_human_agents (L2) | `transfer_to_human_agents IMPLIES (request_out_of_scope OR user_explicitly_requested_human)` | block | no | dialogue |
| 50 | RET-R001 | respond_to_user (L2) | `respond_to_user IMPLIES (user_authenticated OR NOT message_discloses_account_information)` | warn | no | dialogue, tool_log |
| 51 | RET-R003 | respond_to_user (L2) | `respond_to_user IMPLIES NOT message_assists_with_other_user_task` | warn | no | dialogue |
| 52 | RET-R006 | respond_to_user (L2) | `respond_to_user IMPLIES NOT message_contains_unsupported_information` | warn | no | dialogue |
| 53 | RET-R007 | respond_to_user (L2) | `respond_to_user IMPLIES NOT message_contains_subjective_recommendation` | warn | no | dialogue |
| 54 | RET-R011 | respond_to_user (L2) | `respond_to_user IMPLIES NOT message_refuses_out_of_scope_request_without_transfer` | warn | no | dialogue |
| 55 | RET-R022 | respond_to_user (L2) | `respond_to_user IMPLIES NOT message_offers_unsupported_order_modification` | warn | no | dialogue |
