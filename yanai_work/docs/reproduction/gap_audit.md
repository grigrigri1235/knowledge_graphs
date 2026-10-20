# Deliverable B: gap audit (v1 pipeline and runtime code vs the paper)

Date: 2026-10-15. Component numbers refer to `spec.md`. Decisions: **keep**, **modify**, **remove**, **add**.

## 1. Offline pipeline `policy_pipeline/` v1 (tag `auto-pipeline-v1`)

| Stage | Paper component | Matches | Extra (not in paper) | Missing | Decision |
|---|---|---|---|---|---|
| **S0** tool classification (read/write/utility; k = 3 vote) | none | — | The whole stage. Tool schemas are not an input of the paper's extraction (Fig. 1 "Policy Input"). | — | **remove.** Tool schemas go only to runtime EXTRACT (spec Q2, D11). |
| **S1** clause segmentation (verbatim quotes, sentence-coverage validator, ≤ 2 repairs, fact/normative kind) | 4 policy extraction | Reads the document section by section | Clause unit instead of policy blocks; fact/normative classification; coverage validator + repair loop | The 4 elements (definition, scope, policy_description, reference); the App. H prompt | **modify** into E1 with the App. H prompt verbatim. Keep the verbatim-span check as a **diagnostic only** (it implements App. H's "copy the exact descriptions"; it logs, never repairs). Drop the fact/normative split (App. H asks only for actionable policies). |
| **S2** rule writing: NL rules + `related_tools` + `modality`; critic (low effort) + revise ≤ 2 rounds; pick the version with the fewest failed checks | 5 LTL rule extraction (partly) | One call per source unit; rules are atomic agent obligations | Natural-language-first rules; `related_tools`; `modality`; **critic/revise loop**; the "fewest failed checks" selection | Predicates with keywords; LTL formula in the same call; rule type (action/physical) | **modify** into E2: App. H LTL prompt → `{predicates [name, desc, keywords], logic (LTLf), description, type}`. **Remove** critic/revise (the paper's refinement is VR, component 6). |
| **S3** rule dedupe (embedding clusters ≥ 0.88 + LLM decide) | 8 RP (partly) | Embedding clustering + LLM merge | Runs once, outside any loop; works on NL rules; own prompt | Predicate-level merge inside the Alg. 2 loop; App. H RP prompt | **modify:** fold into RP (E4) with the App. H prompt, inside the Alg. 2 loop. |
| **S3b** tool attribution (3 samples + S2 vote, ≥ 2 of 4) | none | — | The whole stage | — | **remove.** Circuits come from Alg. 3 (component 11). |
| **S4** NL → propositional logic (single top-level IMPLIES, `this_action` placeholder, ≤ 2 repairs; validator via `aspm_tool.validate_rule_consistency`) | 5 LTL rule extraction (logic part) | Predicate/logic output; syntax validation | Separate NL→logic step; `this_action` placeholder; propositional-only grammar | Temporal operators (App. C.3, App. H) | **remove** as a stage (logic is produced in E2). **Keep and modify** the validator: extend the grammar to LTLf (NEXT, ALWAYS, EVENTUALLY, UNTIL) and drop the single-IMPLIES restriction (that came from the authors' `logic_to_python` bug, not the paper). |
| **S5** vocabulary merge (predicate clusters ≥ 0.85 + LLM rename) | 8 RP (predicate merge) | Predicate merging with LLM | Single pass, own prompt | Inside the Alg. 2 loop; recompute vagueness; push affected rules back to the heap | **modify:** fold into RP (E4). |
| **S6** tree: fixed 3 group nodes (write/read/message), rules attached by `related_tools` | 11 circuits | Produces the authors' runtime format (`action_tree`, `actions.soft_rule_ids`, `rule_list`) | Tool-based fixed tree; attachment by votes; every rule `rule_type: "action"` (`stages.py:518`) | Alg. 3 (spectral clustering of state predicates, merge by co-occurrence, action ↔ rule clusters); physical rules | **modify** into E5 (Alg. 3); keep the output format writer. |
| **S7** predicate specs (`value_source`, judge question/context, k = 3 vote) | none (2 predicate types, as metadata) | Predicate descriptions | `value_source`, judge questions, votes | Keywords (from E2) | **remove.** The runtime planner decides how to verify each predicate (Fig. 15–17). |
| **S8** enforcement block/warn (k = 3 vote) | none | — | The whole stage (the paper decides by weights + ε) | Weights | **remove.** Replaced by learned weights (component 15) and ε (component 14). |
| — | 6 VR loop (Alg. 2 l.5–19) | — | — | Entire | **add** E3: max-heap by V_r, App. H VR prompt, budget N_b, per-lineage cap (logged) |
| — | 7 vagueness (Eq. 3) | — | — | Entire | **add** `vagueness.py` (embedding backend per D1) |
| — | 9 iteration/stopping (Alg. 2) | — | — | Entire | **add** the driver (M_it = 10, stop when nothing changes) |
| — | 15 weight learning | — | — | Entire | **add** `train_weights.py` (runtime phase, after data) |

### Cross-cutting v1 additions (not in the paper)

| Addition | Where | Decision | Reason |
|---|---|---|---|
| Critic/revise loop | S2 (`prompts/s2_critic.md`, `s2_revise.md`) | **remove** | Not in the paper; VR is the paper's refinement |
| k = 3 majority votes | S0, S3, S3b, S5, S7, S8 (`Ctx.k`; S1, S2 and S4 use single samples) | **remove** | The paper uses single calls |
| Addendum (interpretation notes) | `inputs/addendum_interpretations.txt`, `_addendum_block` | **remove** | Not in the paper; also leaked across domains (Step 2b report §4) |
| S0 tool classification | S0 | **remove** | See table |
| Tool attribution (S3b) and enforcement (S8) | S3b, S8 | **remove** | Replaced by Alg. 3 and weights/ε |
| Structured outputs (JSON schema, strict) | `llm.py` | **keep** | Implements the App. H "output in JSON format" requirement reliably; it changes the format, not the content. The prompts keep the paper's "Reasoning / Decision" text, carried as a JSON field. |
| Reasoning-effort settings per stage | `Ctx.effort` | **keep**, but uniform `medium` | A deployment parameter with no paper equivalent; set uniformly to avoid per-stage tuning |
| Disk call cache, usage accounting, manifest | `llm.py`, `run.py` | **keep** | Reproducibility (G1). It does not change decisions. |
| Deterministic tie-break, hash-seed-independent validation messages | `stages._top`, `common.logic_errors` | **keep** | Reproducibility |
| No-gold-leakage test | `tests/policy_pipeline` | **keep**, extended to the new modules | Project rule |
| `eval/` (gold comparison E1–E6) | `eval/` | **keep as a diagnostic only** | Allowed as an extraction-quality diagnostic; never an input |

## 2. Runtime modules (`agent/`, authors' code)

| Module | Paper component | Matches | Extra | Missing / broken | Decision |
|---|---|---|---|---|---|
| `agent/agent.py` (`ShieldAgent.verify_action`, `:332-535`) | 1, 16–20, 25 | The pipeline order: grounding → circuit → solution space → predicate map → planner → certification → output | A second LLM agent for certification (20 turns); deny on any error | Azure client (uses openai-agents SDK with the public key); memory wiring (`:354-361` commented out); `db_path` import bug (`:116-121`); `TODO` error handling (`:393`); only text from step i; the error check at `:470` is a no-op | **modify:** port to Azure Responses tool-calling; replace the certification agent with deterministic Formal Verify + MLN; wire memory; shield every step; return `unknown`-aware results |
| `agent/run_inference.py` | 27 (driver) | — | Web-trajectory loader; only the last step (`:74-76`); drops text observations (`:226`); `allowed` vs `action_allowed` (`:121`) | — | **remove** for τ-bench; **add** a τ-bench offline driver (step replay) |
| `tools/aspm_tool.py`: `load_aspm_json`, `get_action_circuit` | 11, 17 | Format and retrieval | `int(rule_id)` sort; non-empty `actions` entries required | Weights per circuit | **keep**, add a weights field (ignored by the loader, read by `mln.py`) |
| `tools/aspm_tool.py`: `action_grounding` | 16 | LLM extraction of action predicates (≤ 3) | Ancestors from the tree (component 12, omitted) | τ-bench step text; tool schema context | **modify:** prompt input = tool call + agent text + action-predicate descriptions; no tree ancestors |
| `tools/aspm_tool.py`: `formulate_solution_space` | 20 (Fig. 15 relevance filtering and disambiguation) | Filter irrelevant rules; make predicates concrete | Free renaming of predicates (design notes §8.1) | Keeping a mapping back to the canonical predicates (needed for MLN weights) | **modify:** keep the filtering; require each grounded predicate to carry its source predicate name; do not split rules (weights are per source rule) |
| `tools/aspm_tool.py`: `validate_rule_consistency` | 5 (syntax) | — | Strips operators by `str.replace` | Temporal operators | **modify** (shared LTLf parser) |
| `tools/verification.py` (`create_predicate_map`, `get_unverified_predicates`, `update_predicate_values`, …) | 20 (Fig. 15–17 truth table) | Exactly the Fig. 15–17 tools | `verify_rule` (eval, unused) | 3-tuple vs 4-element predicate shapes (design notes §8.4); `unknown` value | **keep**, fix shapes, add `unknown` |
| `tools/certification.py` (`verify_fol_rules`, `verify_llm_rules`, `static_certification`, …) | 13, 14, 24 | Rule-by-rule verification step | `verify_llm_rules` (an LLM judges NL descriptions, not in the paper); ALWAYS/EVENTUALLY deleted (`:66-67`); eval errors reported as violations (`:191-194`); character-iteration bug (`:97-101`); `verified` means satisfied (`:186`); **deny if any violation** (`:209-215`) | MLN (Eq. 4), ε (Eq. 5), weights | **remove** and **replace** with `ltlf.py` (Formal Verify) + `mln.py` (Eq. 4/5) |
| `tools/memory_tool.py` | 18 | Workflow store/retrieve by action | TTL short-term dict (unused); SQL `LIKE` memory search | Wiring; embedding retrieval; the `MEMORY_PATH` handling ignores its value (`:396-406`) | **keep and modify:** wire in; retrieve by action + keyword similarity; freeze flag |
| `tools/content_moderation.py` | 23 Detect | OpenAI moderation (text/image) | Factual-check stubs that always return "consistent" | — | **remove** for τ-bench (Detect omitted; stubs are misleading) |
| `tools/binary_query.py`, `tools/context_search.py` (0-byte files) | 22, 21 | — | — | Entire | **add** (nano Binary-Check and Search) |
| `tools/trajectory_tool` (only a `.pyc`) | 16 | — | Regex heuristics | Source | **remove**; τ-bench steps are already structured |
| `tools/policy_extraction.py` (legacy) | 4 | Prompt nearly verbatim App. H (`:425-471`) | Section-queue exploration | — | **reuse the prompt text** in E1; do not use the server |
| `utility/policy_server.py` | 4, 5 | 4-element blocks (`:615-644`) | NL rules + one "refine & categorize" prompt (`:1316-1528`) with risk categories | LTL extraction | **reuse** the extraction prompt; **remove** refine & categorize (not in the paper; RP replaces it) |
| `agent/policy_construction/rule_extractor.py` (unused LTL extractor) | 5 | G/F/X/U; action/physical | gpt-4o; predicates as bare names | Keywords | **reference only** (E2 uses the App. H prompt) |
| `agent/prompt.py` (unused coordinator prompt) | 20 | Names the paper's operations | — | — | **reference only** |
| `agent/lib/LADR-2009-02A`, empty `stormpy` / `pyModelChecking` / `mcp-logic` gitlinks | 24 | — | — | No binaries, no submodules | **not used** (LTLf evaluator) |
| `agent/predicates/`, `scripts/aspm_src/`, `aspm/`, `policies/curated/`, `policies/predicates/` (ours) | — | — | Gold, hand-written | — | **never an input to the method**; at most a diagnostic |

## 3. Summary of decisions on v1 additions not in the paper

| v1 addition | Decision |
|---|---|
| S0 tool classification | remove |
| S1 clause unit, fact/normative kind, coverage repair loop | remove (replaced by App. H policy blocks); verbatim check kept as a diagnostic |
| S2 critic + revise + "fewest failed checks" selection | remove |
| S2 `related_tools`, `modality` fields | remove |
| S3b tool attribution | remove |
| S4 separate NL→logic step, `this_action` placeholder, single-IMPLIES grammar | remove (grammar extended to LTLf) |
| S6 fixed tool tree and vote-based attachment | remove (Alg. 3) |
| S7 `value_source`, judge specs | remove |
| S8 block/warn enforcement | remove (weights + ε) |
| k = 3 votes everywhere | remove |
| Addendum | remove |
| Structured outputs, call cache, deterministic tie-breaks, manifest, leakage test | keep (implementation, reproducibility) |
| Embedding clustering thresholds (0.88 / 0.85) | replaced by the RP graph threshold τ_RP and Alg. 3's θ (spec components 8, 11) |

## Addendum (2026-10-17): dependency of the reproduction on `policy_pipeline/` and `eval/`
`policy_pipeline/` and `eval/` belong to our pre-reproduction stage 2b. Every import from them in `repro_core/`, `repro_pipeline/`, `repro_runtime/`, `repro_online/` and `scripts/reproduction/` (AST scan, including imports inside functions):

| importer | symbol | what it does | class |
|---|---|---|---|
| `repro_core/llm.py:19` (used by every P1/P2/P6 structured call via `structured_llm`, `repro_runtime/calls.py`) | `policy_pipeline.llm.LLM` | sends the caller's system and user prompts **verbatim** to the Responses API with a strict JSON schema; disk cache keyed by (system, user, params); 5 retries with backoff; usage accounting; per-run raw copies | **infrastructure** (LLM client, caching, IO) |
| `repro_core/llm.py:19` (`run_tool_loop`) | `policy_pipeline.llm._get_client` | returns the Azure client and deployment name from `utility/utils.py` (Managed Identity) | **infrastructure** (LLM client) |
| `repro_core/llm.py:32` | module `policy_pipeline.llm` (sets `_client` timeout 420 s, `max_retries=0`; I2) | client configuration | **infrastructure** |
| `scripts/reproduction/p1_gold_diagnostic.py:8` | `eval.common.gold` | loads gold clauses, curated rules, gold ASPM and registry; locates clause spans in the wiki | **gold loader, diagnostic only** (never imported by the method) |
| `scripts/reproduction/p1_gold_diagnostic.py:8` | `eval.common.aligned` | span-overlap test (≥ 0.5 of the shorter span) | **scoring/parsing, diagnostic only** |
| `scripts/reproduction/p1_gold_diagnostic.py:9` | `policy_pipeline.common.find_span` | whitespace-tolerant substring search | **parsing, diagnostic only** |

**Result: no method logic** (prompts, rule construction, predicate generation, verification, decision) comes from `policy_pipeline/` or `eval/`. All P1 prompts live in `repro_pipeline/prompts/`, all runtime prompts in `repro_runtime/prompts/`, LTLf in `repro_core/ltlf.py`, and the decision logic in `repro_runtime/`. The only shared piece on the method path is the LLM transport (`LLM.call`), which does not alter prompts or outputs beyond JSON-schema structured output; that adaptation is documented in `prompts_provenance.md`. Tests reuse the gold-path and domain-word lists `FORBIDDEN` and `DOMAIN_WORDS` from `tests/policy_pipeline/test_pipeline.py`: test infrastructure, not method code. The faithful-reproduction claim is not affected.
