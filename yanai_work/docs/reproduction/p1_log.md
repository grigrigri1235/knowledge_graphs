# P0 + P1 log (Stage A)

Date: 2026-10-15. Covers infrastructure (P0) and extraction to spec (P1, `repro_pipeline/`). Every change made after a run is logged here, with its reason and whether it is an implementation fix or a method choice. Method choices are not changed after seeing results.

## Environment
- **Reproduction venv:** `~/venvs/tau-bench`, created with `--system-site-packages` (it inherits the main miniconda environment and shadows only what it pins). Frozen list: `docs/reproduction/venv_freeze.txt`.
  - Pinned packages: `tau_bench` (installed from a separate clone `~/opt/tau-bench-59a200c`; the read-only reference clone is untouched), `litellm 1.57.8`, `openai 1.69.0`, `pydantic 2.10.4`, `torch 2.5.1+cpu`, `transformers 4.57.6`, `tokenizers 0.22.2`.
  - Why a venv:
    - the main environment's CUDA torch does not import (two NCCL builds installed, no GPU: `undefined symbol: ncclCommRegister`);
    - τ-bench's dependencies (litellm) would otherwise change the main environment's `openai` / `pydantic`;
    - the newest litellm needs pydantic ≥ 2.12, which breaks the authors' `fastmcp 0.4.1`, so litellm is pinned to a release compatible with pydantic 2.10.
  - **The main environment is unchanged**, apart from `flloat 0.3.0` (+ `pythomata`, `graphviz`), installed as the LTLf test oracle.
- **Run everything for the reproduction** with `~/venvs/tau-bench/bin/python`, e.g. `~/venvs/tau-bench/bin/python -m unittest discover -s tests/repro -t .`.

## P0 results

| Deliverable | Where | Test result |
|---|---|---|
| Kleene LTLf evaluator | `repro_core/ltlf.py` | `tests/repro/test_ltlf.py`, 8 tests OK: **10,000 random formula/trace pairs agree with flloat** on two-valued traces (depth ≤ 4, length 1–6, all 8 operators); Kleene unit tests for `unknown`; soundness against every completion of the unknowns on 2,000 random cases; parser precedence/errors; 3,000 canonical-printer round trips. Kleene evaluation is sound but not complete (`p IMPLIES p` with p unknown → unknown), so MLN enumeration must enumerate unknowns rather than rely on Kleene values. |
| Embedding backend | `repro_core/embed.py`, `repro_core/config.json` | D1 check: no Azure embedding deployment (`DeploymentNotFound` for `text-embedding-3-large`, `-3-small`, `ada-002`). Local `BAAI/bge-large-en-v1.5` @ `d4aa6901…`, CLS pooling + L2 normalisation, one text per forward pass, single thread, SQLite cache. Determinism test: **byte-identical vectors in two separate processes**, unit norm, dim 1024. Backend switch: `embedding.backend` (`local`/`azure`) or env `REPRO_EMBEDDING_BACKEND`; the azure backend raises if the deployment is missing (no silent fallback). |
| Azure Responses tool-calling loop | `repro_core/llm.py` (`run_tool_loop`) | Live test with a trivial `add` tool: 2 chained tool calls, correct answer, 3 calls, 1.2 k in / 0.5 k out tokens; a second run replays **3/3 from the cache**. Offline tests with a fake client: tool outputs are sent back as `function_call_output`; tool errors are returned to the model; `max_turns` stops the loop. |
| τ-bench step adapter | `repro_core/taubench_steps.py` | On all 1,980 recorded trajectories: 26,260 steps (14,285 tool calls, 11,975 responds); every assistant tool call and text-only message maps to exactly one step; **0 tool calls without an observation**; history equals the messages before the step. |
| Pinned τ-bench + nano harness | `~/opt/tau-bench-59a200c`, `repro_core/taubench_run.py` | τ-bench's own `ToolCallingAgent` and `LLMUserSimulationEnv` run unchanged, with `litellm.completion` replaced by an Azure Chat Completions call (`temperature` dropped: the deployment rejects 0.0). |
| **1-task unshielded smoke run** | `output/repro/smoke/airline_test_0.json` | **Works end to end** (airline test task 0, gpt-5-nano agent and user simulator): reward 0.0, 11 agent + 10 user calls, 77 k in / 27 k out tokens, **$0.016**, 502 s. An earlier run on the not-yet-pinned venv (openai 2.54) had reward 0.0, 39 calls, $0.022, 301 s. Both failures are genuine agent failures (wrong year in the flight search in run 1; incomplete booking in run 2). In both runs the nano **user simulator sometimes speaks like the agent** ("Passenger 1 details: first name, last name, DOB …"), a risk for P6. |

All repro tests: `Ran 17 tests … OK` (`tests/repro/`).

## P1 runs
(filled in below per domain)

## Implementation changes during P1 (not method changes)

| # | When | Change | Reason | Effect on results |
|---|---|---|---|---|
| I1 | airline v1, during Alg. 2 iteration 1 | **VR scheduling.** Waves of 16 parallel calls with a barrier were replaced by a rolling pool: 16 calls stay running, each popped from the vagueness max-heap and applied when it returns. Validation and format repair moved into the worker (task-local logs, merged by the main thread). Progress lines and "VR done" / "RP done" lines per iteration were added. | First attempt (`output/repro/p1_airline_v1.attempt1.log`): 72 VR calls in 80 min. Each wave waited for its slowest call (VR median 45 s, max 362 s), and between waves sequential repair calls and silent retries left the pool idle for 10–20 min. The process was alive and idle (0 % CPU, 4 threads, requests pending). At that rate iteration 1 alone would take > 4 h. | None on prompts or decision rules. Order of application = completion order instead of pop order; the heap and budget logic are as in Alg. 2. The run was resumed from the cache, so all 161 completed calls replayed without new API calls. |
| I2 | same | **Request timeout.** v1's shared client gets `timeout = 420 s`, `max_retries = 0` (`repro_core/config.json → llm.request_timeout_s`); v1's `LLM.call` keeps its own 5 retries with backoff. | The openai default (600 s × 3 attempts) let one stalled request block a wave for up to 30 min. 420 s exceeds the slowest legitimate call seen (362 s). | None. |
| I3 | test | Progress text "in flight" → "running". | The domain-word leakage test (whole-word match) flagged "flight". | None. |
| I4 | airline v1 finished → **v1 invalid**, rerun as v2 | **Few-shot contamination fix.** (a) The VR/RP few-shot blocks are delimited explicitly ("<<<BEGIN FEW-SHOT EXAMPLES … NOT part of your input. Never copy their predicates or rules into your output.>>> … <<<END FEW-SHOT EXAMPLES>>>"), and the actual input is labelled "YOUR INPUT (the only rule to check …)". (b) A deterministic, domain-free guard drops any VR/RP output rule using a predicate name that occurs only in the few-shot examples and not in the actual input; it is counted as `fewshot_copy_*` in the validation stats. | In v1, **192/294 VR outputs and 55/70 RP outputs contained the paper's example predicates** (`publish_personal_data`, `store_personal_data`, `is_illegal_content`, …), and **37/71 final rules were copies of the examples**. Cause: the example blocks used the same labels as the real input ("Rule to check:", "Cluster of similar predicates:"), so the model treated them as input. Consequence: v1's VR "explosion" (105 → 1,024 rules) and "RP merges everything" were largely this bug, not method behaviour. Probe of the fixed prompt on 10 real E2 rules: 0/10 copies; refinements are 1–2 rules each. | Format-only prompt change (documented in `docs/reproduction/prompts_provenance.md`), plus an implementation guard. E1/E2 unchanged (replayed from the cache); Alg. 2 and E5 rerun as `v2`. |

## Airline runs so far

| Run | Embeddings | Prompts | Status | Use |
|---|---|---|---|---|
| v1 | bge-large fp32 | before I4 (no few-shot delimiting) | finished; **invalid**: 37/71 final rules were copies of the few-shot examples | evidence for I4 only; not published |
| v2 | bge-large **fp32** | after I4 | finished 2026-10-15 20:39; converged at iteration 6 (no refinement, no merge); 57 final rules, 96 predicates, 30 distinct circuits, max 13 predicates per circuit; Alg. 2 took 6,995 s with heavy paging | diagnostic only; not published (superseded by v3 because D1 changed to bf16) |
| v3 | bge-large **bfloat16** | after I4 | finished 2026-10-16; converged at iteration 6; 66 final rules. **Affected by defect I7** (28 meaning-changing repairs) | diagnostic only; not published |
| v4 | bge-large bfloat16 | after I4, I7, I8 | finished 2026-10-16; converged at iteration 8; 58 final rules | under review; not published |

| # | When | Change | Reason | Effect |
|---|---|---|---|---|
| I5 | before v3 | **bf16 embeddings (D1).** The embedding dtype is a config field and part of the cache key (fp32 vectors stay valid under their old keys). A one-time bf16 copy of the pinned weights is saved to `output/repro/_models/…-bfloat16` and loaded directly, so the fp32 weights are never resident alongside it. | v1/v2 paged heavily: 1.9 GB VM, about 1 GB free next to the IDE server, and 1.3 GB of fp32 weights. | Warm-up (150 new texts): peak RSS 851 MB (fp32: 1.1 GB), 0.90 s/text (fp32 under paging: 1.8 s), cosine(fp32, bf16) ≥ 0.99991. **Not fully swap-free:** 279 MB of process swap and high IO pressure. torch + transformers take about 380 MB anonymous memory, and the 639 MB of bf16 weights are memory-mapped file pages, so the total is about 1 GB against about 1.0–1.15 GB available. The CPU (Xeon 8171M) has no native bf16, so bf16 compute is emulated. |
| I6 | before v3 | **Embeddings computed inside the VR/RP worker tasks.** New rules' predicate texts are embedded in the worker (cached), so the main thread's vagueness recomputation (Alg. 2 l.13/l.26) hits the cache and the pool keeps running. | In v1/v2 the main thread embedded new predicates while the pool waited; under paging that throttled VR to 1–4 effective workers. | No semantic change: same vectors, same order of operations in the main thread. |

| I7 | found in v3, **fixed in code, not yet rerun** | **Format repair could change meaning.** It is now split in two. (a) Undeclared-predicate errors (the logic parses but uses a name missing from `predicates`) get a **declaration repair** (`prompts/format_declare.md`): the LLM returns declarations for exactly the missing names, and the logic is never changed; declarations for other names are rejected. (b) Syntax errors keep the logic rewrite, accepted only if the repaired formula uses exactly the same predicates as the original text and introduces no `TRUE`/`FALSE`. Unit tests: `tests/repro/test_repro_pipeline.py::FormatRepair`. | In v3, **28 of 45 "successful" repairs changed meaning**, all 28 of them undeclared-predicate cases, where the logic-only repair deleted or replaced the undeclared action. Examples: `within_24h_of_booking IMPLIES cancel_reservation` → `… IMPLIES FALSE`; `NOT user_confirmed_before_booking_update IMPLIES NOT update_passenger_info_action` → `FALSE`; `airline_cancelled IMPLIES cancel_reservation` → `airline_cancelled IMPLIES airline_cancelled`. | Rules that needed a repair change (E2: 14 rules; VR/RP: 50). Their downstream VR/RP calls are re-issued; everything else replays from the cache. |

## Airline v3 results (bf16, before I7)

- 43 policy blocks → 105 E2 rules → **66 final rules**, 96 predicates (38 action / 58 condition), 17 physical rules, **40/66 (61 %) with temporal operators**.
- Alg. 2 stopped by **convergence at iteration 6** (no refinement, no merge). The budget was not binding (222/315). VR was effectively inactive after iteration 1: 182 refinements hit the per-lineage cap (3), and RP outputs inherit the maximum depth of the merged rules, so they are not re-queued (iteration 2: 2 VR calls; later: 0).
- Parse repairs: 69/810 validations (8.5 %); 24 failed (rule dropped); see I7 for the 28 meaning-changing ones. The few-shot copy guard fired once (2 rules).
- Circuits: 32 spectral clusters (k by eigengap) → 28 after the co-occurrence merge; 47 → 43 rule clusters; 31 distinct circuits; circuit sizes unchanged by the merge: **max 20 predicates** (`modify_flight`: 18 rules, 7 action + 13 condition), median 3 predicates / 2 rules. No collapse.
- Cost: fresh-equivalent 488 distinct calls, 0.85 M in / 2.17 M out tokens ≈ $0.91 (this run itself: 74 new calls, $0.18, 35 min wall, mostly cache).

| I8 | before v4 (decided by the user) | **RP output depth = MIN of the parents' depths** (was MAX). The per-lineage cap still applies to VR refinements. Documented in spec.md ("Implementation choices fixed during P1"). | With MAX, RP output inherited the capped depth and was never re-checked by VR: v3 made 2 VR calls after iteration 1, and its "convergence" was largely an artefact. | v4 iteration 2: 155 VR calls, 94 refinements. The refinement budget (315) was then exhausted, so VR made 0 calls in iterations 3–8. |

## Airline v4 results (bf16, I7 + I8)

- 43 policy blocks → 105 E2 rules → **58 final rules**, 103 predicates (34 action / 69 condition), 23 physical rules, 38/58 (66 %) with temporal operators, 1 predicate type conflict (`payment_for_reservation_completed_successfully`).
- Alg. 2: VR iteration 1: 315 calls / 222 refined; iteration 2: 155 calls / 94 refined / 9 budget-skipped → **budget exhausted (316/315)**. Iterations 3–8 were RP only (21, 20, 20, 15, 12, 11 calls; 10, 5, 4, 4, 1, 0 merges). **Stopped by convergence at iteration 8** (budget exhausted + no merge), before M_it = 10.
- Repairs (I7): 105/1,155 validations (9.1 %). Declaration repairs 70 (67 accepted, 3 rejected); syntax repairs 35 (15 accepted, 20 rejected, mostly still unparsable); 23 rules dropped. **0 accepted repairs changed predicates or added TRUE/FALSE.** The few-shot guard never fired.
- Circuits: spectral k = 34 → **24 clusters after the co-occurrence merge** (41 → 31 rule clusters). The merge enlarges circuits: max 22 → **26 predicates**, median 4. **3 circuits > 20 predicates** (collapse flag set): `gesture_certificate_offered` (13 rules; 5 action + 21 condition), `entitlement_silver_basic_economy_1` and `full_refund_granted_for_booking` (11 rules, 22 predicates each).
- Cost: fresh-equivalent 661 distinct calls, 1.19 M in / 2.88 M out ≈ $1.21 (VR 399, RP 122, E2 43, repairs 91, E1 6); this run 318 new calls, $0.58, 63 min wall.
- Never-block / always-block (one-step prefix, action taken): complete-trace semantics: 18 vacuous / 3 always-block of 43 pairs; **three-valued prefix semantics: 20 never block / 2 block every step**.

## Airline v4 accepted (2026-10-16)
Published to `aspm_repro/airline/` (aspm.json, weights.json, manifest.json, rules.md). Pipeline frozen as git tag **`repro-p1-v1`** (commit `98d029c`, `scripts/freeze_repro_tag.sh`; no branch moved). From here `repro_pipeline/` is frozen; retail runs on exactly this code and configuration.

### Airline findings (method output, not hand-fixed). Rule numbers = `aspm_repro/airline/aspm.json` rule_id (see rules.md)
- **Missing or not enforceable, though critical for τ-bench:**
  - *Cancellation eligibility:* only "can cancel" facts, no prohibition: rule 11 `within_24h_of_booking IMPLIES can_cancel_due_to_time` and rule 37 `is_business_flight IMPLIES can_cancel_business_flight`. **Both are in no circuit**, so they are never evaluated. Nothing forbids cancelling an ineligible (basic) economy reservation. The only cancellation prohibition is rule 23 (no cancelling a partly flown trip); rule 56 is a future refund obligation.
  - *Compensation restrictions:* no ban for regular + uninsured + (basic) economy users and no ban on proactive offers. **Rule 58 even obliges an offer** (`… AND has_cancelled_flight_complaint AND facts_confirmed IMPLIES gesture_certificate_offered`). Rules 18/19 only fix the amount once an offer is made.
  - *Basic-economy flight-change ban:* absent (basic economy appears only in the bag-allowance facts, rules 45/47/51).
  - *Origin, destination and trip type preserved on flight changes:* absent (rules 13/14/16 concern the ordering of booking questions, not preservation).
- **Likely false blocks: rule 4** `ALWAYS NOT (initiate_tool_call AND NEXT initiate_tool_call)` forbids two tool calls on *consecutive steps*. The policy means one tool call *per turn*; consecutive single calls (e.g. a lookup followed by a write) are normal.
- **7 rules in no circuit, never checked:** rules 7, 11, 12, 22, 34, 37, 57. Their Alg. 3 rule clusters contain no rule that mentions an action predicate.
- **Abstract action predicates:** the 34 action predicates are policy-level (`complete_booking`, `ask_origin`, `provide_information`, `gesture_certificate_offered`, …), not τ-bench tool names. At runtime, EXTRACT (an LLM) must map every τ-bench step to them (p2_design.md §3).
- **Operator precedence (P2-5):** 1 of 58 rules chains IMPLIES: **rule 44** parses as `pre → ((upd ∧ upd) → pre)`, a tautology, although its description says "equivalence".
- **Obligations never enforced (structural, P2-4):** rules 5, 18, 19, 27, 44 have the form "condition IMPLIES action". They are satisfied whenever the action is taken, and their circuits are retrieved only then.
- **Inconsistent predicate types (P2-3):** 1 (`payment_for_reservation_completed_successfully`).

## Retail v1 results (frozen code, tag `repro-p1-v1`)

Run `output/repro/aspm_runs/retail/v1` (log `output/repro/p1_retail_v1.log`); **not published**. Freeze check after the run: every file under `repro_core/` and `repro_pipeline/` has the same git blob as in `repro-p1-v1`, with the same file set; manifest `params`, `prompt_template_sha256_16` and `embedding` are identical to airline v4. No implementation bug hit; 6 transient API errors (3 VR, 3 RP), all retried successfully. The few-shot guard never fired.

- 8 sections → 34 policy blocks (30 with a verbatim description) → 74 E2 rules (9 dropped) → **43 final rules**, 56 predicates (15 action / 41 condition), 19 physical, 26/43 (60 %) with temporal operators, **0 predicate type conflicts** (P2-3 count 0).
- Alg. 2 (N_b = 222): VR iteration 1: 154 refined; iteration 2: 69 refined → **budget exhausted (223/222)**. Iterations 3–10 were RP only (12, 9, 8, 7, 7, 7, 7, 6 calls; 6, 1, 2, 1, 1, 1, 1, 0 merges). Stopped at **iteration 10 = M_it**; its RP made no merge, so convergence and the cap coincide.

| iter | phase | rules | predicates (act/cond) | V mean | refined | merges / RP calls | budget |
|---|---|---|---|---|---|---|---|
| 0 | initial | 74 | 114 (47/67) | 0.802 | | | |
| 1 | VR | 177 | 201 (75/126) | 0.845 | 154 | | 154/222 |
| 1 | RP | 77 | 96 (37/59) | 0.770 | | 33 / 38 | |
| 2 | VR | 98 | 118 (44/74) | 0.832 | 69 | | 223/222 |
| 2 | RP | 62 | 71 (22/49) | 0.744 | | 14 / 19 | |
| 3 | RP | 55 | 64 (18/46) | 0.717 | | 6 / 12 | |
| 4 | RP | 53 | 60 (17/43) | 0.712 | | 1 / 9 | |
| 5 | RP | 52 | 60 (17/43) | 0.708 | | 2 / 8 | |
| 6 | RP | 50 | 60 (17/43) | 0.705 | | 1 / 7 | |
| 7 | RP | 48 | 60 (17/43) | 0.702 | | 1 / 7 | |
| 8 | RP | 47 | 60 (17/43) | 0.701 | | 1 / 7 | |
| 9 | RP | 43 | 56 (15/41) | 0.688 | | 1 / 7 | |
| 10 | RP | 43 | 56 (15/41) | 0.688 | | 0 / 6 | |

- Repairs (I7): 45/728 validations (6.2 %). Declaration repairs 19 (19 accepted); syntax repairs 26 (9 accepted, 17 rejected); 17 rules dropped. **0 accepted repairs changed predicates or added TRUE/FALSE.** The 9 accepted syntax repairs are token substitutions (`∧`/`⇒`/`->`/`G` → AND/IMPLIES/ALWAYS, `IFF` → two IMPLIES, predicate arguments stripped).
- Circuits: spectral k = 23 (eigengap) → **22 clusters after the co-occurrence merge** (25 → 24 rule clusters; 2 rules without state predicates). The merge changes no circuit size: **max 5 predicates**, median 4; 12 distinct circuits over 15 action predicates; no collapse. sklearn warned "graph is not fully connected" (as in airline v4).
- MLN feasibility under P2-1 (worst case: every condition predicate unknown, non-invoked actions observed false): largest connected group **4 unknowns** (`payment_method_provided`), median 2, **0 groups > 16**, so exact enumeration always. (Airline v4 for comparison: max 21, median 1; 3 groups > 16 need Gibbs: `gesture_certificate_offered` 21, `entitlement_silver_basic_economy_1` 19, `full_refund_granted_for_booking` 19.)
- Operator precedence (P2-5): **2 of 43** rules contain ≥ 2 IMPLIES. Rule 29 is fully parenthesised, so its parse matches the description. **Rule 39's parse differs from its description**: `pending IMPLIES m AND m IMPLIES pending AND m IMPLIES not_modified` parses as pending → (m → ((pending ∧ m) → not_modified)), i.e. (pending ∧ m) → not_modified. The "only once" part survives; "modify only if pending" (m → pending) is lost. Not a tautology. Related: rules 25 and 27 (`ALWAYS a AND b`) parse as (ALWAYS a) ∧ b. Both are in no circuit, so this has no runtime effect. Airline v4 has no such case.
- Never block / can block / block every step (`p1_runtime_semantics.py`, 26 rule–action pairs): 1 step: plain LTLf 8 / 17 / 1, runtime (P2-2 + P2-4) 9 / 17 / 0; **2 steps: plain LTLf 1 / 24 / 1, runtime 6 / 20 / 0**. The 6 never-block pairs are all obligations "condition IMPLIES action": rules 5, 9, 18, 19, 20, 37.
- Cost: 558 API calls (493 distinct prompts; 59 cache hits within the run), 0.89 M in / 2.19 M out tokens (1.95 M reasoning) ≈ **$0.92** billed; distinct-prompt (fresh-equivalent) $0.91. Wall **66.1 min** (E1 37 s, E2 3.2 min, Alg. 2 62.3 min, circuits 1 s).
- E1 gold diagnostic (diagnostic only; span overlap): 37/46 gold normative clauses covered by a block. The 9 "missed" (RET-GEN-05/06/07 and RET-EXC-03) are paraphrased blocks, not missing content. Rules 2, 3/4/29 and 9/10 cover GEN-05/06/07, so span alignment undercounts.

### Retail findings (method output, not hand-fixed). Rule numbers = `aspm.json` rule_id (see `docs/reproduction/retail_v1_rules.md`)
**Three typical problems**
1. **Unenforceable database/schema facts and unpruned duplicates.** **18 of 43 rules are in no circuit** (rules 7, 11–16, 22–28, 35, 38, 41, 42; all physical), so they are never evaluated. Examples: rule 13 `ALWAYS id_unique`; rules 14/15/24–28 restate "timestamps are EST, 24 h" six times. RP left **exact-logic duplicates**: 14 ≡ 15, 24 ≡ 26 ≡ 28, 25 ≡ 27, and 33 ≡ 34 (the last pair is in the `tool_call_in_session_initiated` circuit and is double-counted in Eq. 4 with θ = 1).
2. **Over-generalisation, likely false blocks.** Rule 32 `ALWAYS (first_order_tool_call_happened_in_session IMPLIES NOT EVENTUALLY tool_call_in_session_initiated)` turns "exchange or modify tools can only be called once" into "no tool call at all after the first order tool call". Rule 30 forbids tool calls on consecutive steps (same misreading as airline rule 4). Rule 31 requires `change_items_list_ready` for *every* tool call. Rule 16 turns the wiki's illustrative example ("blue M", "red L" variants) into a requirement for every product type.
3. **Abstract or obligation-only action predicates.** Action predicates such as `tool_call_in_session_initiated`, `deliver_response`, `provide_help`, `payment_method_provided`, `refund_initiated_immediately` and `new_order_placed` are policy-level, not τ-bench tools (mapping needed, p2_design §3). `payment_method_provided` is a user act typed as an agent action. 8 rules (1, 5, 8, 9, 18, 19, 20, 37) are obligations "C IMPLIES action" (structural finding in spec P2-4). 6 of them never block (table above). The ALWAYS-rooted rules 1 and 8 can be false only through an *earlier* step, so they would block the current action for a past omission.

**Critical-content check**
| Content | Status | Rules |
|---|---|---|
| Authentication before acting | **partial**: only information disclosure requires authentication (`provide_information IMPLIES is_authenticated`); the authentication step is an obligation that never blocks. **Nothing requires authentication before a write action** (cancel/modify/return/exchange). | 21, 20 |
| Order-status preconditions | **partial**: modify requires pending (rule 36; rule 39 lost its pending part, see P2-5). **Cancel requires pending: absent. Return/exchange require delivered: absent** (rule 37 is a reminder obligation; rule 38 is an allowed-status fact with no circuit). | 36, 39, 37, 38 |
| Modify/exchange items only once | **partial**: rule 39 keeps "(pending ∧ modify items) → not modified before". Exchange-once has no dedicated rule, only the over-general rule 32 (blocks every later tool call). | 39, 32 |
| Refund destination for returns | **wrong scope**: rule 17 `refund_initiated_immediately IMPLIES refund_destination_is_original_payment_method` comes from the cancel/modify refund sentences. The return rule ("original payment method **or an existing gift card**") is absent; if rule 17 were mapped to returns, it would block a valid gift-card refund. | 17 |
| Cancellation reasons ('no longer needed' / 'ordered by mistake') | **absent**: no cancellation rule survives at all. | — |
| Gift-card balance | **present for price differences** (modify items / exchange): rule 40, in the `payment_method_provided` circuit only. **Payment-method change to a gift card ("enough balance to cover the total"): absent.** | 40 |
| (also) Explicit confirmation before write actions | **absent** as a precondition; only rule 43 uses `exchange_confirmation_received`, as a trigger of an obligation. | 43 |
