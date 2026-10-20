# P2 log: ShieldAgent runtime (Stage A) and pilot

Started 2026-10-16. Design: `p2_design.md`; decisions P2-1…P2-5 and the ε sign: `spec.md`. ASPMs: `aspm_repro/{airline,retail}/` (tag `repro-p1-v1`). Env: `~/venvs/tau-bench/bin/python`.

## Decisions taken before implementation (user, 2026-10-16)
1. ε sign: allowed iff P(µ_a=1) − P(µ_a=0) ≥ −ε; ε = 0.1, variant ε = 0 (spec "ε sign", documented as an interpretation).
2. Reasoning effort: auxiliary calls (vocabulary, EXTRACT, relevance, Search, Binary-Check, explanation) `low`; planner `medium` (config **A**). The pilot reruns every shielded step with all calls at `medium` (config **B**).
3. No-circuit rules (airline 7, retail 18) stay unevaluated (Alg. 3); reported as a finding.
4. Retail v1 published to `aspm_repro/retail/` (aspm.json, weights.json, manifest.json, rules.md).

## Implementation map (`repro_runtime/`, domain-agnostic; leakage + domain-word tests extended to it)
| Alg. 1 / design § | Module | Notes |
|---|---|---|
| ASPM, RETRIEVE (l.2) | `aspm.py` | authors' `load_aspm_json` run once as a format check; circuit of a = `actions[a].soft_rule_ids` (authors' `get_action_circuit` semantics); θ from `weights.json` (per circuit; all 1.0) |
| §3a vocabulary + P2-3 | `vocab.py`, `aspm.resolve_types` | one call per tool + `respond`, cached |
| EXTRACT (l.1), §3b | `extract.py` | ≤ 3 predicates, must be among the tool's candidates |
| relevance (Fig. 15), §4a | `plan.relevance` | kept ids ⊆ circuit; predicates never renamed |
| planner (l.6–12), §4b | `plan.planner` | `repro_core.llm.run_tool_loop`, ≤ 15 turns; tools check_unassigned / assign_predicate_values / search / binary_check |
| VERIFY (l.13) | `verify.py` | three-valued prefix semantics, P2-2, P2-4 |
| Eq. 4/5 (l.15–20) | `mln.py` | P2-1 connected group, exact ≤ 16 unknowns, Gibbs above (10k samples, 1k burn-in, seed 0) |
| output + feedback, §6 | `shield.py` | per-conversation trace store; explanation call only when blocked |
| Direct baseline, §7 | `direct.py` | one call, complete wiki |
| pilot | `scripts/reproduction/p2_select_pilot.py`, `p2_pilot.py`, `p2_pilot_summary.py` | |

## Prompt provenance (`repro_runtime/prompts/`)
| Prompt | Mark | Source / change |
|---|---|---|
| `vocab.md` | [new] | p2_design §3a, verbatim |
| `extract.md` | [authors] | system text from `aspm_tool.action_grounding` ("…most critical actions that require safety verification (maximum 3 actions)"); user text p2_design §3b |
| `relevance.md` | [authors] | system text verbatim from `aspm_tool.formulate_solution_space` (non-reasoning variant minus its output-format sentence, replaced by structured output); rule rendering verbatim (`plan.rules_text`); context block (Agent Thought / Agent Action / Matched Action Predicates) verbatim. Changed: one rule is not grounded into several, predicates are not renamed and logic is not changed (keeps weights attached, p2_design §4a); the interaction history is added |
| `planner_system.md` | [authors] | `agent/agent.py:204-246` verbatim except (i) "make sure all the predicates are assigned even if you are unsure … best guess" → "Assign `unknown` when the history does not determine the value"; (ii) the "default-based predicates are always true" guideline removed; (iii) only the tools that exist are listed (Content Moderation and Detect omitted, D10); (iv) tool names `get_unverified_predicates` / `update_predicate_values` → `check_unassigned` / `assign_predicate_values` (p2_design §4b); `get_predicate_info` dropped (redundant with check_unassigned) |
| `planner_user.md` | [new] | history, current action, invoked action predicates, rules under verification, and "the predicates describe the situation at the moment the current action is about to be executed" |
| `search.md`, `binary_check.md` | [new] | p2_design §4b, verbatim |
| `explain.md` | [new] | p2_design §6, verbatim (Fig. 19 fields) |
| `direct.md` | [new] | p2_design §7, verbatim |
| respond pseudo-tool schema (`vocab.RESPOND_TOOL`) | [new] | "Send a text message to the user (the agent's reply in the conversation)" |

## Implementation choices (not method changes)
- **I-P2-1 Predicate type conflicts (P2-3) input.** `aspm.json` stores only the registry type (an action use wins, `repro_pipeline/stages.assemble`), so the published file shows no conflict. The runtime takes the conflict list from the run's `alg2.json` (`type_conflicts`, located via `aspm_repro/<domain>/manifest.json` run_id) and re-resolves it with the vocabulary table. Airline: 1 (`payment_for_reservation_completed_successfully`); retail: 0.
- **I-P2-2 Several invoked action predicates.** For the margin of invoked predicate a, the other invoked predicates of the same step are observed **true**, non-invoked ones false (P2-1). The step is allowed iff every invoked predicate passes (spec component 14).
- **I-P2-3 Trace store.** Position j: invoked action predicates of step j true, every other action predicate false; condition predicates as assigned at step j (unknown, or never assigned → unknown). Unmapped steps hold only the all-false action predicates.
- **I-P2-4 V_s.** Rules false in the most probable world with µ_a = 1 and not false in the same world with µ_a = 0. If that set is empty while the step is blocked (the block comes from unknown predicates), V_s = the rules the action violates with probability > 0 given µ_a = 1 (`at_risk`, P(r false at (1, u) and not false at (0, u) | µ_a = 1)), sorted by that probability (fix B1).
- **I-P2-5 Relevance-filter counterfactual.** Each mapped step also gets the decision over the **whole circuit** with the same predicate values; predicates of dropped rules are unassigned, so they are unknown and marginalised (P2-1). No extra LLM calls. A filter-caused miss = filtered decision allow, counterfactual block.
- **I-P2-6 Transient API errors.** A failed step is re-run (≤ 3 attempts, trace rolled back); cached calls replay, so a retry repeats only the failed call.
- **I-P2-7 Accounting.** Structured calls report tokens and API seconds from their cache record (fresh-equivalent even on cache hits). Planner turns come from `run_tool_loop`, which counts tokens only for fresh turns; config A/B runs are fresh, the warm rerun reports 0 planner tokens.
- **I-P2-8 Direct effort.** Direct is a decision-making call (the counterpart of the planner), so it runs at `medium` in both configurations; it is run once.
- **I-P2-9 Inputs.** The shield never sees the step's observation (tool output / next user message); H_<i excludes the wiki system prompt; tail truncation at 24k characters is flagged per step.

## Bugs found during the pilot (fixed, each listed)
| # | Found | Bug | Fix | Effect on results |
|---|---|---|---|---|
| B1 | airline config A: 4 of 33 blocks (targets: task 37 trial 0 step 7, sonnet task 37 trial 5 step 7; prefix: sonnet task 30 trial 0 step 0, sonnet task 5 trial 3 step 9); retail: 2 prefix steps, no target | A step blocked only through unknown predicates (margin < −ε, but no rule false in the most probable executing world) returned an **empty violated-rule list**, so the feedback named no rule (§6 requires the violated rules). | `mln.decide` also returns `at_risk` (per-rule probability of being violated by the action given µ_a = 1); `shield` uses it for V_s when the best-world set is empty. Unit test added. | Decisions and margins unchanged (V_s is computed after Eq. 5). The violated-rule list and explanation of those steps change. Config A was replayed from cache with the fix (tag `A2`, new explanation calls only): decisions and margins identical to `A` on 196/196 airline and 216/216 retail steps. A2 is the reported config A; cost and latency are taken from the fresh run `A`. |

## Pilot (2026-10-16)
Run inventory, per-domain checks, the 40-step target table with causes, worked examples, feedback messages, A vs B and exit criteria: **`p2_pilot_report.md`**. Raw records `output/repro/p2_pilot/<domain>/<tag>/steps.jsonl` (tags A, A2, A2_rerun, B, direct); summaries `output/repro/p2_pilot/<domain>/summary.md` (`scripts/reproduction/p2_pilot_summary.py <domain> --a A2 --fresh A --rerun A2_rerun`).
Sequence: smoke test (airline gpt-4o 41·0, 5 steps) → config A both domains (fresh) → B1 found while reading airline A → driver stopped before config B, fix + unit test → A2 (cache replay with the fix) → B → Direct → A2_rerun. No crash in any run.
