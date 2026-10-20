# Reproduction spec: faithful ShieldAgent on τ-bench (gpt-5-nano only)

Date: 2026-10-15. Status: **spec only, nothing implemented.** Companion documents: `gap_audit.md` (v1 vs paper), `data_feasibility.md` (labels), `plan.md` (phases, cost, decisions).

## Sources

| Source | Where | Note |
|---|---|---|
| Paper | `docs/paper/shieldagent.pdf`, arXiv 2503.22738**v2** (27 Nov 2025), 32 pages | Copied from `~/code_projects/ShieldAgent_paper.pdf`; the spec's path did not exist before. All "§/Eq./Alg./Fig./App." references below are to this version. |
| Authors' code | `agent/`, `utility/`, `policy_extractor_async.py` (commit `7f02c71` and earlier; local Azure edits only swap LLM clients) | Surveyed read-only. Full notes: session scratch `original_code_survey.md`; key facts are reproduced here with file:line references. |
| τ-bench | `~/refs/tau-bench` @ `59a200c` (read-only) | Tool schemas, `envs/base.py` reward, tasks, `historical_trajectories/` |
| Our state | `docs/step2b_auto/report.md`, `policy_pipeline/` v1, `aspm/` (gold, diagnostic only) | |

### Facts about the sources that shape the whole spec
1. **Parts of the paper are empty.** App. C.5 ("Training ASPM") and App. D ("ShieldAgent Framework") are headings with no content, although the main text refers to them for details (§3.2.4, §3.3). Several hyper-parameters are therefore **unspecified**: k in Eq. 3, the clustering algorithm C in Alg. 2, θ and k in Alg. 3, the optimiser, learning rate, epochs and ε. Each is listed as a reproduction decision below.
2. **The authors' code implements only part of the paper** (code survey §7):
   - Missing: Verifiability Refinement, Redundancy Pruning, the vagueness score, embeddings, spectral clustering, circuit formation, weights, weight learning, MLN inference and ε. No builder turns rules into an ASPM, and no ASPM file is shipped.
   - **Runtime decision:** `static_certification` denies if any rule is violated (`agent/tools/certification.py:198-228`, `allowable_violations = 0`).
   - **Formal verification:** Python `eval` after string rewriting, with ALWAYS/EVENTUALLY **deleted** (`certification.py:51-69`). Alternatively an LLM judges rule descriptions (`verify_llm_rules`, `:247-330`).
   - **Shielding operations:** Search and Binary-Check are empty files (`agent/tools/binary_query.py`, `context_search.py`); factual checks are constant stubs; the memory store exists but is not wired in (`agent/agent.py:116-139, 354-361`).
   - **Models:** Claude 3.7 Sonnet and GPT-4o. There is no fine-tuned model.
   
   Consequence: "follow the paper" cannot mean "run the authors' code". The code is useful for formats, prompt wording and the runtime skeleton.
3. **The paper is internally inconsistent in places:**
   - Formal verification: the main text names Stormpy (§3.3 Tool Library), but Fig. 14/18 use Prover9.
   - Rule logic: the paper says "LTL" (§3.2.1), the appendix defines **LTLf over finite traces** (App. C.3, Eq. 7), and every example rule is propositional (Fig. 8–19).
   - Fig. 6 measures vagueness with "GPT-4o as a judge", whereas Eq. 3 is an embedding measure.
   - Fig. 19 reports P(execute) = 0.25 and P(not execute) = 0.97. These do not sum to 1, so they do not come from a normalisation over the two worlds of Eq. 4. The margin is printed as −0.82 in Fig. 19 and −0.72 in Fig. 14.
   - A static L1/L2/L3 **action tree** appears in Fig. 14/15 and in the code (`aspm_tool.py`, `ActionTree`) but nowhere in the method text.

### Global deviations (apply to every component)

| Deviation | Paper | Here | Class |
|---|---|---|---|
| G1. Model | GPT-4o for extraction, refinement, planning and baselines (§3.2.2, §3.2.3, §5.1); fine-tuned InternVL2-2B for Search / Binary-Check (§3.3) | gpt-5-nano (existing Azure deployment) for every role. No temperature or seed control (deployment rejects `temperature`), so reproducibility comes from the call cache. | adapted |
| G2. Modality | Web agents: screenshots + AX-tree (App. A.1) | τ-bench is text-only: conversation messages, tool calls and tool outputs | adapted (not applicable) |
| G3. Benchmark | ShieldAgent-Bench (§4), with attacks generating unsafe trajectories | τ-bench airline/retail recorded trajectories, labelled from expected actions (Deliverable C), later plus gpt-5-nano trajectories | adapted |
| G4. Transport | MCP servers (§3.3, Fig. 14) | In-process Python tools with the same names and signatures. MCP does not affect decisions, and in-process tools keep caching and accounting simple. The authors' MCP servers stay usable as reference. | adapted |
| G5. No hand-written domain content | The paper allows "human experts may review the optimized rules and make corrections" (§3.2.3) | **No human review or corrections.** Gold artefacts are never inputs. | omitted (by project rule) |

---

## Stage A scope (decisions of 2026-10-15)

The reproduction proceeds in two stages.
- **Stage A (MVP, now):** end-to-end structure: policy → ASPM (P1) → runtime shield (P2) → online τ-bench (P6).
- **Stage B (later):** weight learning (P3–P4), offline evaluation (P5), workflow memory.

Final Stage A decisions:

| ID | Decision |
|---|---|
| D1 | Embeddings (final, 2026-10-16): local **`BAAI/bge-large-en-v1.5` @ `d4aa6901…` in bfloat16** (**adapted**: there is no Azure embedding deployment, and precision is reduced). The backend is a config switch (`repro_core/config.json → embedding.backend` `azure`/`local`, `embedding.local.dtype`). fp32 was used for airline runs v1/v2 only. |
| D2 | Online, the shield processes every step. There is no offline training in Stage A. |
| D3 | The action tree is omitted. |
| D4 | Respond messages are actions and are shielded. |
| D8 | GuardAgent is omitted. |
| D9 | Online compliance is scored by the gold Python rules, as a **scoring-only judge**, plus a manual audit of a stratified sample. Gold never feeds the method; the leakage test covers `repro_core/` and `repro_pipeline/`. |
| D10 | Detect is omitted. |
| D11 | The policy text is the only extraction input; tool schemas are used only by runtime EXTRACT (taken from the τ-bench environment, not from our files). |
| ε | Fixed a priori at 0.1 (the paper's Fig. 19 example); ε = 0 is reported as a variant. No tuning. |
| Memory | Disabled. |
| Deferred to Stage B | D5 (label cleaning), D6 (nano trajectories), D7 (violated-rule ground truth), D12 (memory updates) |

### Stage A deviations (in addition to G1–G5)

| Deviation | Paper | Stage A | Class |
|---|---|---|---|
| A1. Rule weights | Learned per circuit by the hinge loss (Eq. 6, Alg. 3 l.26–37) | **Uniform θ_r = 1** for every rule in every circuit (`weights.json`) | omitted (Stage A) |
| A2. ε | User-adjustable (§3.2.4); 0.1 in Fig. 19 | **Fixed at 0.1**; ε = 0 as a variant; never tuned | adapted |
| A3. Long-term workflow memory | Few-shot workflows (§3.3, Alg. 1 l.5) | **Disabled** | omitted (Stage A) |
| A4. Embeddings | text-embedding-3-large (§3.2.3) | local bge-large-en-v1.5, pinned, **bfloat16** (reduced numeric precision: the 1.9 GB VM cannot hold the fp32 weights without paging), CLS pooling (upcast to fp32) + L2 normalisation, one text per forward pass (deterministic). A one-time bf16 copy of the pinned weights is stored in `output/repro/_models/` (with `PROVENANCE.json`). Measured effect: cosine(fp32, bf16) ≥ 0.9999 on 381 predicate texts. | adapted |
| A5. Format repair | — | At most one format-only repair per rule whose logic does not parse (`repro_pipeline/prompts/format_repair.md`); rate reported | implementation aid |
| A6. τ-bench harness | τ-bench uses litellm with each provider | τ-bench's own `ToolCallingAgent` and `LLMUserSimulationEnv`, unchanged, with `litellm.completion` replaced by an Azure Chat Completions call (`repro_core/taubench_run.py`). `temperature` is dropped (the deployment rejects it); the user simulator is also gpt-5-nano. | adapted |
| A7. Prompt format | App. H text formats | Structured-output JSON objects, input slots, and the predicate type / rule description / rule type fields required by §3.2.2 (`docs/reproduction/prompts_provenance.md`) | adapted (format only) |

**ε sign (decided 2026-10-16, see the decision below).** With uniform weights and all predicates assigned, Eq. 4 over the two worlds gives margin P(µ=1) − P(µ=0) = tanh((S₁ − S₀)/2), where S₁ − S₀ = −(number of rules the action violates) + (number of rules only the action satisfies).
- The typical rule has the form "action → condition", which is trivially satisfied when the action is not taken. So S₁ ≤ S₀, and the margin is 0 for a compliant action and ≈ −0.46 for one violation.
- **Read literally (margin ≥ +0.1), Eq. 5 therefore blocks every action** whose circuit has no rule that the action itself satisfies.
- The paper's prose describes the condition as "allowing executing a_i only when the safety likelihood increases **or remains within a tolerable region bounded by |ϵ|**" (§3.2.4), i.e. margin ≥ −|ε|. With ε = 0.1 that reading blocks iff at least one rule is net-violated. ε = 0 (margin ≥ 0) gives the same decisions with uniform weights and fully assigned predicates, which equals the authors' code behaviour of denying on any violation.
- **Proposal:** implement l_s = 1 iff margin ≥ −|ε|, with ε = 0.1 as the primary setting and ε = 0 as the variant, and record the literal reading as rejected because it makes every compliant action unsafe. 
- **Decision (2026-10-16, approved; an interpretation of Eq. 5):** an action is allowed iff **P(µ_a=1) − P(µ_a=0) ≥ −ε**, i.e. it does not lower the safety probability by more than ε. ε = 0.1 primary, ε = 0 variant. Reason: the literal reading (≥ +ε) requires every safe action to *raise* the safety likelihood by ε; with θ = 1 the margin of a compliant action is ≤ 0 whenever no rule is satisfied only by the action, so every compliant action would be blocked. The −ε reading matches the paper's prose ("increases or remains within a tolerable region bounded by |ϵ|", §3.2.4).
- Uniform-weight decisions differ from "deny on any violation" only when predicates are unknown (marginalised, fractional margins). Stage B's learned weights are what separate the method from that baseline.

### Implementation choices fixed during P1

**I8. Refinement depth of RP-produced rules (Alg. 2).** Alg. 2 pushes rules changed by RP back into the VR heap (l.27) but says nothing about the per-lineage refinement counter, which is our own safeguard (spec component 6). Up to airline v3, an RP-produced rule inherited the **maximum** depth of the rules it replaced. Since most rules reach the cap of 3 during iteration 1, this kept RP output out of VR, so after iteration 1 VR made 0–2 calls and "convergence" was largely an artefact: the VR↔RP alternation of Alg. 2 was effectively disabled. **From v4, an RP-produced rule starts at the minimum depth of its parents.** The per-lineage cap still applies to VR refinements. This is an implementation choice, not a paper parameter.

**LTLf on an incomplete trajectory (decided 2026-10-16, for P2; the evaluator is unchanged until P2).** The shield evaluates rules on a prefix of the conversation whose continuation is unknown. App. C.3 gives finite-trace semantics for a *complete* trace; using them on a prefix would treat "the conversation ends now" as a fact (e.g. `NEXT φ` false at the last step, an unsatisfied `EVENTUALLY φ` false). **Decision: three-valued prefix semantics. Anything that depends on steps after the current one evaluates to `unknown`.** On a prefix π = π₀ … πₙ (πₙ = the current step):

| Formula | true | false | otherwise |
|---|---|---|---|
| `NEXT φ` at i < n | φ true at i+1 | φ false at i+1 | unknown |
| `NEXT φ` at i = n | — | — | **unknown** |
| `EVENTUALLY φ` at i | φ true at some j ∈ [i, n] | never (the future may satisfy it) | unknown |
| `ALWAYS φ` at i | never (the future may violate it) | φ false at some j ∈ [i, n] | unknown |
| `φ UNTIL ψ` at i | ψ true at some j ≤ n with φ true on [i, j) | φ false at some k ≤ n before any ψ | unknown |
| `NOT`, `AND`, `OR`, `IMPLIES` | Kleene, as now | | |

Unassigned predicates stay `unknown`, as before. A rule blocks only if it evaluates to **false**.

**Consequence to settle in P2 (flagged, not decided):** under this semantics `ALWAYS φ` is never `true` on a prefix. A satisfied `ALWAYS (a IMPLIES b)` evaluates to `unknown`, so in Eq. 4 the indicator 𝟙[µ ∼ r] of such rules is never 1 until the conversation ends. Most extracted rules are wrapped in `ALWAYS` (airline v3: 30/66 rules), so the MLN would see them as uncertain rather than satisfied, and the margin would be driven by marginalising them. The standard alternative is **RV-LTL** (Bauer, Leucker & Schallhart 2010), whose four values add "presumably true" / "presumably false" for prefixes that satisfy / violate a property so far. P2 must choose how `unknown` rule values enter Eq. 4: marginalise, treat as satisfied, or use RV-LTL.

### P2 decisions (2026-10-16)

| # | Decision | Class | Notes |
|---|---|---|---|
| **P2-1** | **MLN computation (Eq. 4/5).** Worlds vary only (i) the invoked action predicate(s) and (ii) the unknown predicates of the **connected group of rules** that touch the invoked action through shared *unknown* predicates. Action predicates that were not invoked are **observed false**. If the group has more than 16 unknowns, Gibbs sampling is used instead of enumeration (logged). | faithful formula; exact decomposition | **The decomposition is exact.** Any rule outside the group depends only on observed predicates or on unknowns outside the group, so its factor Σ exp(θ_r 𝟙[·]) multiplies the numerator P(µ_a = v) and Z identically and cancels in Eq. 4, hence in the margin of Eq. 5. Test: `tests/repro/test_mln_decomposition.py` (400 random circuits, equal to full enumeration to 12 decimals). Worst-case group sizes (all conditions unknown): airline v4 max 21 unknowns, 3 groups > 16 (Gibbs); retail v1 max 4, none > 16. |
| **P2-2** | **Unknown rule values.** In 𝟙[µ ∼ r], a rule counts as **violated only if its prefix value is definitely false**; true and unknown both count as "not violated" (satisfied in Eq. 4). Standard runtime-monitor semantics. | adapted | Resolves the consequence flagged under "LTLf on an incomplete trajectory": a satisfied-so-far `ALWAYS` (prefix value unknown) is not a violation. Unknown predicates are still marginalised by P2-1; rule values are three-valued only through the future. |
| **P2-3** | **Predicates typed inconsistently** (action in one rule, condition in another). Resolved once per domain, deterministically: **action iff it can be matched to an agent tool call or message**, otherwise condition. The match comes from the runtime action-vocabulary mapping (p2_design.md §3): a predicate that no τ-bench tool and no `respond` maps to is a condition. Built once per domain, cached, and logged. | adapted | Counts: airline v4: 1 (`payment_for_reservation_completed_successfully`); retail v1: 0. |
| **P2-4** | **Evaluation position.** Every rule is treated as an **invariant checked at the current step**. A rule whose root operator is not temporal (not ALWAYS / EVENTUALLY / NEXT / UNTIL) is evaluated **at the current step** n. A temporal-rooted rule is evaluated at position 0 over the prefix π₀…πₙ with the three-valued prefix semantics. | adapted | Under plain LTLf (App. C.3) a non-temporal formula is checked only at position 0, i.e. at the first step of the conversation, which makes it vacuous later. Note: "evaluate at the current step" is not identical to wrapping in ALWAYS. On a prefix, ALWAYS would also re-detect violations at earlier steps, and those were already shielded when they happened; the current-step reading is used. Effect (`scripts/reproduction/p1_runtime_semantics.py`, 2-step prefixes): airline v4, 44 rule–action pairs: never blocks 13, can block 29, blocks every step 2; retail v1, 26 pairs: 6 / 20 / 0. |
| **P2-5** | **Operator precedence.** Unchanged: IMPLIES has the lowest precedence and is right-associative (spec Q1). | finding only | `A IMPLIES B AND B IMPLIES A` parses as A → ((B ∧ B) → A), a tautology. Airline v4 rule 44 is such a case, and its description says "equivalence". Counts (`scripts/reproduction/p1_precedence_check.py`): airline v4 1 rule chains IMPLIES (rule 44, parse ≠ description); retail v1 2 rules (rule 39 parse ≠ description: it loses "modify only if pending"; rule 29 is parenthesised). The rules are not changed (method output). |
| **P2-6** | **Trace store for blocked steps (decided 2026-10-16, after the P2 pilot).** Online, a blocked step is **not executed**, so it is **not taken**: it is not appended to the trace store, and neither the blocked message nor its feedback appears in the history H the shield sees for later steps. A step executed through the cap override (4th attempt after 3 consecutive blocks) is recorded as taken. Offline replay of recorded trajectories (P2 pilot) keeps every step, because the recorded agent executed it (`ShieldConfig.record_blocked_steps`). | adapted (the paper does not specify it) | Found in the pilot (finding F5): if blocked steps entered the trace, an ALWAYS rule broken by a blocked attempt would stay false in both worlds and stop discriminating. Implemented in `repro_runtime/shield.py` (`Shield.step` appends only executed steps; `Shield.commit` for cap overrides); test `tests/repro/test_runtime.py::TraceStoreOnline`. The agent itself still sees its blocked message and the feedback (§ online feedback). |
| ε | Fixed at **0.1**, ε = 0 as a variant. **Sign convention decided (interpretation):** l_s = 1 iff P(µ=1) − P(µ=0) ≥ −ε (the "tolerable region bounded by \|ε\|" reading, see "ε sign"); read literally (≥ +ε), Eq. 5 blocks every compliant action. | adapted (interpretation) | With θ = 1 and fully observed predicates, both ε = 0.1 and ε = 0 (under the proposed reading) block iff at least one rule is violated by the action (margin tanh(−k/2) ≤ −0.46 for k ≥ 1). |

**Structural property found while checking P2-4 (paper design, not an implementation issue).** Circuits are keyed by action predicates (Alg. 3), so a rule is evaluated only when one of its action predicates is invoked. An **obligation** "condition IMPLIES action" (e.g. airline v4 rules 5, 18, 19, 27, 44) is satisfied whenever that action is taken, and its violation (*not* taking the action) is never evaluated, because its circuit is retrieved only when the action occurs. Such rules can never block.

## Components

Each block covers: **Paper** · **Original code** · **τ-bench mapping** · **Class** · **Justification** · **Current coverage** · **Work needed** · **Risk**.

### 1. Problem formulation
- **Paper:** (l_s, V_s, T_s) = A_s(a_i | o_i, H_<i, G_ASPM) (Eq. 1). The output is a binary safety flag, rule-violation flags and a textual explanation, per invoked action a_i, given the history and current observation (§3.1, App. A.1).
- **Original code:** `ShieldAgent.verify_action(context)` (`agent/agent.py:332-535`) returns `{action_allowed, violated_rules[{rule_id, explanation, feedback}], explanation}`. `run_inference.py:74-76` verifies only the **last** step of a trajectory.
- **τ-bench mapping:**
  - a_i = one agent output: a tool call `(name, arguments)` or a `respond` message;
  - o_i = the tool output or user message preceding it;
  - H_<i = all prior messages, tool calls and outputs.
  
  Every agent step is shielded, not just the last.
- **Class:** faithful. **Current coverage:** the runtime skeleton in `agent/agent.py`. **Work needed:** a τ-bench step adapter: trajectory → (a_i, o_i, H_<i).
- **Risk:** low.

### 2. Predicate types (action vs state)
- **Paper:** P = {P_a, P_s}. Action predicates name the target action; state predicates describe system/environment conditions (Eq. 2, §3.2.1, App. A.2). Each predicate has a name, a description and keywords (App. H, LTL prompt).
- **Original code:** predicate entries `[name, description, "", "action"|"condition"]` (`aspm_tool.py:384-389`); keywords are never read.
- **τ-bench mapping:**
  - Action predicates are **abstract actions named in the policy**, as produced by the LTL extraction (e.g. `cancel_reservation`, `modify_order_items`, `send_message`). They are not forced to equal tool names; see Q2.
  - State predicates are whatever the extraction produces, refined by VR/RP.
- **Class:** faithful. **Current coverage:** v1 has both types, but its action predicates are tool names (forced by S3b/S6). **Work needed:** keep `[name, description, keywords, type]`.
- **Risk:** low.

### 3. Rule types (action vs physical)
- **Paper:** R = {R_a, R_p} (Eq. 2). An action rule involves at least one action predicate. A physical rule constrains system variables only (e.g. `is_private → is_red_data`) and "serves as knowledge … to enhance the robustness" (App. A.2). Rules are r = [P_r, T_r, φ_r, t_r] (§3.2.2).
- **Original code:** `rule_type ∈ {action, physical}` is passed to the grounding prompt (`aspm_tool.py:347-530`) but plays no role in certification (survey §7.11). The unused `agent/policy_construction/rule_extractor.py` emits both types.
- **τ-bench mapping:** keep both. Physical rules have an effect only through the MLN (component 13), and only when some state predicates are not observed (latent).
- **Class:** faithful. **Current coverage:** v1 emits only action rules (`stages.py:518`, `rule_type: "action"`). **Work needed:** the extraction prompt must allow physical rules; S6 replacement keeps them.
- **Risk:** τ-bench wikis contain few "physical" facts, so physical rules may be rare or useless. Report their count.

### 4. Policy extraction (policy blocks)
- **Paper:** GPT-4o extracts individual actionable policies, each with four elements: term definition, application scope, policy description, reference (§3.2.2, App. C.2.1). The prompt is in App. H ("Prompt Template for Policy Extraction"): exhaust all actionable policies, copy the exact descriptions, one policy per block, JSON list.
- **Original code:** `utility/policy_server.py:615-644` uses the same four elements. The legacy `agent/tools/policy_extraction.py:425-471` is nearly verbatim App. H. Long documents are explored through an LLM-prioritised section queue (budget 20); there is no chunking, only truncation at 150k characters.
- **τ-bench mapping:** input is `policy_docs/{airline,retail}_wiki.txt`, byte-identical to τ-bench `wiki.md`. The wikis are short (~5–6 k characters), so run **one extraction call per markdown section** with the App. H prompt verbatim, filling `{organization}` with "an airline customer-service agent" / "a retail customer-service agent". Output: list of blocks `{definition[], scope, policy_description, reference[]}`.
- **Class:** faithful (with G1).
- **Justification for sectioning:** the paper reads documents "section by section" (App. H step 1); a section is the τ-bench equivalent of a handbook page.
- **Current coverage:** v1 S1 segments into verbatim *clauses*: a different unit, with a coverage validator and repair loop that are not in the paper.
- **Work needed:** new stage E1 using the App. H prompt. Keep v1's verbatim-span check **as a diagnostic only** (log, never repair); see the gap audit.
- **Risk:**
  - Policy blocks are coarser than clauses, so more compound rules reach VR. That is the intended path in the paper (VR decomposes).
  - Nano may summarise despite "copy exact descriptions". The diagnostic shows it.

### 5. LTL rule extraction
- **Paper:** each policy block → rules r = [P_r, T_r, φ_r, t_r] (§3.2.2), via the App. H "Linear Temporal Rule Extraction" prompt:
  - atomic, verifiable, snake_case predicates, each `[name, description, [keywords]]`;
  - prefer positive predicates and action-centred rules;
  - symbols ALWAYS / EVENTUALLY / NEXT / UNTIL / NOT / AND / OR / IMPLIES;
  - output `[{predicates, logic}]`.
- **Original code:** the main pipeline produces only natural-language rules (`policy_server.py`, `extract_rules_from_policies`). The LTL extractor `rule_extractor.py` is unused. The runtime expects keyword logic with at most one effective IMPLIES (`certification.py:51-69`).
- **τ-bench mapping:**
  - Use the App. H prompt verbatim, one call per policy block. Add the description T_r (natural-language constraint) and type t_r (action/physical) as fields, because §3.2.2 lists them in r although the App. H output format omits them. **The formula φ_r is LTLf** (Q1).
  - Output validation (deterministic, no LLM): parseable LTLf; every name in `logic` is in `predicates`; snake_case; every action rule has ≥ 1 action predicate (App. A.2). On failure, one re-ask with the parser error.
- **Class:** faithful. **Justification for the validator:** it enforces the prompt's own output requirements, and the paper's VR also fixes "incorrect LTL representations" (§3.2.3).
- **Current coverage:**
  - v1 S2 writes natural-language rules (plus `related_tools`, `modality`, critic/revise loop) and S4 translates them to single-IMPLIES propositional logic with `this_action`;
  - the two-step NL → logic design and the critic are not in the paper;
  - the v1 grammar validator (`policy_pipeline/common.py`, `scripts/validate_aspm.py` `Parser`) is reusable after it is extended with temporal operators.
- **Work needed:** new stage E2 replacing S2 + S4 (gap audit).
- **Risk:** nano writes logic directly from policy text. v1 split this into two steps because of quality problems (iteration log), so expect more VR work.

### 6. Verifiability Refinement (VR)
- **Paper:** refine rules to be **accurate** (fix LTL vs the original definition), **verifiable** (observable predicates that can be assigned a boolean) and **atomic** (decompose compound rules) (§3.2.3).
  - Traverse each rule, or prioritise vague rules under a budget, via a max-heap on rule vagueness V_r (Alg. 2 l.1–19).
  - `LLM_verifiable(r)` decides; if false, `LLM_refine(r, P_r)` replaces r with r_new (possibly several rules, Fig. 11), predicates are updated, V is recomputed and the rule is pushed back.
  - Prompt in App. H ("Verifiability Refinement"): per-predicate criteria Verifiable / Concrete / Accurate / Atomic / Necessary / Unambiguous; output "Decision: Yes/No" + JSON `{rules: [{predicates, logic}]}`; few-shot examples (not given in the paper).
- **Original code:** absent (survey §3).
- **τ-bench mapping:**
  - Alg. 2 l.5–19 implemented as written. The App. H VR prompt plays both `LLM_verifiable` (its Decision) and `LLM_refine` (its JSON), so there is one call per popped rule.
  - Few-shot examples: the paper's own Fig. 11 (decomposition) and Fig. 12 (vague → specific) as given, which are GitLab/Reddit, not τ-bench. No τ-bench examples, to avoid domain leakage.
  - "Observable" means: decidable from the conversation, tool calls and tool outputs.
- **Class:** faithful.
- **Current coverage:** none. v1's S2 critic/revise loop is the closest analogue, but it judges fidelity to the source clause, not verifiability, and is not in the paper.
- **Work needed:** new stage E3 (VR loop).
- **Risk:**
  - The budget N_b is unspecified. Proposal: N_b = 3 × #rules after E2. Record actual refinements per iteration (cf. paper Fig. 4–6).
  - Nano may keep rewriting; Alg. 2 has no per-rule cap. Proposal: also cap each rule lineage at 3 refinements, and report how often the cap is hit (adapted safeguard).

### 7. Vagueness measure (Eq. 3)
- **Paper:**
  - V_i = (1/k) Σ_{m=1..k} S_α(m), with S_α = desc{e_i · e_j | j ≤ |P_i|}. This is the mean of the top-k cosine similarities between predicate i and all other predicates **of the same type** (action or state), with normalised embeddings from "a SOTA embedding model (e.g. OpenAI's text-embedding-3-large)".
  - V_r = max over the rule's predicates (§3.2.3).
  - The equation's summation bounds are garbled ("Σ^k_{i=m}"); read as m = 1..k. k is unspecified.
- **Original code:** absent.
- **τ-bench mapping:**
  - Embed the text `"{name}: {description}. Keywords: {keywords}"` per predicate; exclude j = i; k = 5 (proposed); compute per type.
  - **Embedding model:** the Azure resource has **no embedding deployment** (probed 2026-10-15: `text-embedding-3-large`, `-3-small` and `ada-002` all return `DeploymentNotFound`).
  - Local options: `minishlab/potion-base-8M` (static model2vec, cached, used by v1), or a transformer encoder via the installed `transformers 4.33` / `torch 2.5` (e.g. `BAAI/bge-large-en-v1.5`).
  - **Recommendation:** ask for a `text-embedding-3-large` deployment (faithful; your decision, since the Azure configuration is yours to change). Otherwise use `bge-large-en-v1.5` locally, pinned by revision (adapted).
- **Class:** faithful (with Azure embeddings) / adapted (local encoder).
- **Current coverage:** v1 `policy_pipeline/embed.py` (potion, used only for clustering).
- **Work needed:** `vagueness.py`, plus an embedding backend switch.
- **Risk:**
  - Static embeddings are weaker, which changes which rules are popped first, not whether they are refined (with a large N_b every rule is visited).
  - Eq. 3 rewards distinctiveness, not concreteness. That is the paper's design; keep it.

### 8. Redundancy Pruning (RP)
- **Paper:**
  - Cluster predicates with semantically similar meaning: K ← C(G), over a predicate graph G = (P, E) "with initial edge weights E" (Alg. 2 inputs; l.20).
  - Per cluster, `LLM_merge(C, R)` merges redundant predicates and rules; G and R are updated, V is recomputed and affected rules are pushed back to the heap (l.21–30).
  - Prompt in App. H ("Redundancy Pruning"): merge redundant predicates and unify identical rule semantics, keeping consistency and completeness; "Decision: Yes/No" + JSON rules.
  - Example in Fig. 13. C, E and the cluster granularity are unspecified.
- **Original code:** absent. A single "refine & categorize" prompt (`policy_server.py:1316-1528`) merges natural-language rules.
- **τ-bench mapping:**
  - G: nodes = predicates (per type); edge weight = cosine similarity of the embeddings (component 7), with edges kept above τ_RP.
  - C = connected components after thresholding, with clusters capped at 12 predicates (larger components split by agglomerative clustering).
  - τ_RP = 0.80 (proposed; tune only by cluster-size statistics, never on labels).
  - One App. H RP call per cluster of size ≥ 2.
- **Class:** faithful in procedure, adapted parameters. **Justification:** C and E are left open by the paper; similarity edges follow "clustering rules with semantically similar predicates" (§3.2.3).
- **Current coverage:** v1 S3 (rule dedupe, threshold 0.88 + LLM) and S5 (predicate vocabulary, threshold 0.85 + LLM) do parts of this outside any loop.
- **Work needed:** merge S3/S5 into the Alg. 2 RP step with the App. H prompt.
- **Risk:**
  - Over-merging distinct predicates (e.g. "pending" vs "pending (item modified)"). The completeness requirement is in the prompt; report merges.
  - v1 showed under-merging at 0.88 (duplicates survived, report P2).

### 9. Iteration and stopping
- **Paper:** alternate VR and RP for m = 1..M_it, and stop early when an iteration changes nothing (Alg. 2 l.5, l.31–33). M_it = 10 in all environments (Table 8). Output: an "ASPM with optimized structure and randomized weights" (l.35).
- **Original code:** absent.
- **τ-bench mapping:** M_it = 10; N_b as in component 6; stop when nothing changes. Log per-iteration #rules, #predicates and mean/min/max V_r (as Table 8, Fig. 4–6).
- **Class:** faithful. **Current coverage:** none. **Work needed:** driver for E3–E4.
- **Risk:** cost (plan: about 1–3 k calls per domain).

### 10. Human expert review
- **Paper:** "human experts may review the optimized rules and make corrections when necessary" (§3.2.3).
- **τ-bench mapping:** none.
- **Class:** omitted. **Justification:** project rule (G5): the baseline must be automatic, with no hand-written domain content. It is optional in the paper ("may").
- **Risk:** the paper's numbers may include human corrections. Our reproduction is a lower bound in that respect. State it.

### 11. ASPM structure and circuit formation (Alg. 3, l.1–25)
- **Paper:** the rules are organised into action-based rule circuits π_θ = {C^{p_a}_{θ_a}} (§3.2.4), with spectral clustering (Von Luxburg 2007) of state predicates. Alg. 3:
  1. adjacency A_ij = 1 if two state predicates co-occur in any rule **or** cos-sim ≥ θ;
  2. `SpectralClustering(A, k)`;
  3. merge clusters that contain co-occurring predicates;
  4. group rules by the state predicates in a cluster;
  5. each action predicate p_a gets every rule cluster that contains a rule mentioning p_a.
  
  θ and k are unspecified.
- **Original code:** absent. The runtime reads `action_tree` (L1/L2/L3) + `actions{name: {soft_rule_ids}}` + `rule_list` (`aspm_tool.py:155-186`). No code builds them.
- **τ-bench mapping:**
  - Alg. 3 implemented as written with `sklearn.cluster.SpectralClustering(affinity="precomputed")` on A (installed, scikit-learn 1.6).
  - θ = 0.80 (same embedding as component 7). k chosen by the eigengap heuristic on A's normalised Laplacian (Von Luxburg 2007, §8.3). Both are documented.
  - Output in the authors' runtime format: one node per action predicate in `actions`, `soft_rule_ids` = the rules of its circuit, `action_tree` flat (all action predicates as L1 nodes; see component 12).
  - Physical rules join a circuit through their state predicates' cluster (step 4).
- **Class:** faithful (parameters adapted).
- **Current coverage:** v1 S6 builds a fixed tool-based tree and attaches rules by S3b votes. Not in the paper.
- **Work needed:** new stage E5 (`circuits.py`), plus an adapter for `aspm_tool.load_aspm_json`.
- **Risk:**
  - **Step 3 can collapse clusters.** Co-occurring predicates are already adjacent in A, and merging every cluster pair linked by a co-occurrence tends to produce the connected components of the co-occurrence graph. If one predicate (e.g. "user confirmed") appears in many rules, most rules end up in one cluster, and every action's circuit becomes nearly the whole ASPM.
  - Report circuit sizes and the cluster count before and after step 3. This is a faithful-reproduction finding either way; do not "fix" it silently.

### 12. Hierarchical action tree (L1/L2/L3)
- **Paper:** only in Fig. 14/15: "matches all higher-level action nodes within the action tree", "matched via a static action tree". Its construction is not described anywhere.
- **Original code:** `ActionTree.from_dict`, `get_upstream_actions`; `agent.py:379-385` adds ancestors of grounded actions.
- **τ-bench mapping:** none by default. Every action predicate is an L1 node, and circuit retrieval uses the extracted action predicates only.
- **Class:** omitted (unspecified).
- **Justification:** building a hierarchy would require an unspecified design; v1's tree was our own invention.
- **Risk:** low. Possible ablation: "LLM-built two-level tree" if you want it (decision D3).

### 13. Probabilistic inference (MLN, Eq. 4)
- **Paper:** in circuit C^{p_a}, P_θ(µ_{p_a}=1 | {µ_{p_s}=v_s}) = (1/Z) exp Σ_{r∈R_{p_a}} θ_r 𝟙[µ ∼ r] (Eq. 4), a Markov Logic Network (Richardson & Domingos 2006). P_θ(µ_{p_a}=0) is the same with the action reversed (§3.2.4).
- **Original code:** absent. Deny if any rule is violated (`certification.py:209-215`).
- **τ-bench mapping (exact enumeration):**
  1. Worlds vary the **invoked action predicates** of the circuit, plus any **state predicates the planner left `unknown`**. Unknowns are treated as latent and marginalised, which is where physical rules contribute (App. A.2: "predicates can sometimes be inaccurately assigned, ϕ_p can serve as knowledge").
  2. Z sums over all these worlds.
  3. 𝟙[µ ∼ r] is evaluated by the LTLf evaluator on the trajectory trace, with the current step's assignment set to the world µ (Q1).
  4. Circuits have at most about 15 latent predicates, so 2^15 worlds is fine. Beyond that, cap with Gibbs sampling, logged.
- **Class:** faithful formula; adapted treatment of latent predicates. **Justification:** the paper fixes all state predicates; it does not say what happens if one cannot be assigned. Marginalisation is the standard MLN answer, and it gives physical rules the role App. A.2 describes.
- **Note on Fig. 19:** its probabilities (0.25 / 0.97) are incompatible with a two-world Z. We follow Eq. 4, not the figure.
- **Current coverage:** none. **Work needed:** `certification.py` replacement `mln.py`.
- **Risk:** with all predicates observed, P(1) − P(0) = tanh((S₁ − S₀)/2). Only rules whose satisfaction changes with the action matter, so physical rules contribute nothing in that case. This is a property of the paper's model; report it.

### 14. Safety condition with ε (Eq. 5)
- **Paper:** l_s(a_i) = 1 iff P_θ(µ_{p_a}=1) − P_θ(µ_{p_a}=0) ≥ ε (Eq. 5), inspired by control barrier certificates. ε is user-adjustable; the Fig. 19 example uses 0.1.
- **Original code:** absent.
- **τ-bench mapping:**
  - ε is selected **on the validation split only**: the value maximising balanced accuracy on cleaned labels. Also report results at ε = 0.1 (paper example) and ε = 0.
  - If several actions are extracted for one step: the step is safe iff every action's condition holds. The paper does not say; this follows "binary flag indicating whether action a_i is safe" (Eq. 1).
- **Class:** faithful (ε selection adapted). **Current coverage:** none. **Work needed:** part of `mln.py` plus the `eval/` threshold sweep.
- **Risk:** ε tuned on noisy labels (Deliverable C).

### 15. Weight learning (Eq. 6, Alg. 3 l.26–37)
- **Paper:** per circuit, random init of θ_r (Alg. 3 l.28); then for max_epochs, for each sample, compute P(µ=1), P(µ=0) (Eq. 4), the guardrail hinge loss L_g = E max(0, −y (P_θ(µ=1) − P_θ(µ=0))) (Eq. 6) with y = +1 safe / −1 unsafe, and gradient descent (Alg. 3 l.30–35). Data: "real-world safety-labeled data or simulated pseudo-learning (Kang & Li, 2024)" (§3.2.4). Optimiser, learning rate, epochs, initialisation range and constraints are unspecified (App. C.5 empty).
- **Original code:** absent.
- **τ-bench mapping:**
  - Samples: labelled write calls (and other shielded actions, if labels exist) from the **train** split (Deliverable C).
  - Predicate values per sample come from running the runtime's assignment (components 16–22) once, cached. Training then runs offline with no LLM calls.
  - θ_r ~ U(0, 1) (Fig. 14 shows weights in (0, 1)); plain gradient descent via autograd (torch installed); lr = 0.1; max 200 epochs; early stopping on validation hinge loss; θ clipped at ≥ 0 (a negative weight would invert a rule). All are documented as choices.
  - A rule in several circuits has a separate weight per circuit (θ_a is per circuit).
  - Pseudo-learning (simulated data) is not used unless real labels prove too few (decision D5).
- **Class:** faithful loss and procedure; adapted data and hyper-parameters.
- **Current coverage:** none. **Work needed:** `train_weights.py`.
- **Risk:**
  - Hinge on a margin in [−1, 1] gives zero gradient once the sign is right, so learning stops early; this is the paper's loss, keep it.
  - **Label noise:** about 60 % of raw "unsafe" labels are not policy violations (Deliverable C).
  - Small airline train set (20 tasks, about 270 labelled calls).

### 16. Action extraction (Alg. 1 l.1)
- **Paper:** p_a ← EXTRACT(a_i): "extracts action predicates from the agent output" (§3.2.4, ASPM Inference); Fig. 14 step 1 is an LLM tool `extract_step_action`.
- **Original code:** `action_grounding` (`aspm_tool.py:235-312`) is one LLM call that matches the action to at most 3 tree nodes, plus their ancestors.
- **τ-bench mapping:** one nano call. It is given the agent step (tool name, arguments, the agent's accompanying text) and the ASPM's action-predicate list with descriptions, and returns the matching action predicates (0..3). Results are cached.
- **Class:** faithful (recommended). The alternative, deterministic tool → action-predicate mapping, would be adapted (Q2).
- **Current coverage:** the authors' `action_grounding`. v1 bypassed it because its action predicates were tool names.
- **Work needed:** an adapter from τ-bench steps to the extraction prompt.
- **Risk:** missed extractions mean no circuit, so the action is allowed. Log the "no action predicate" rate.

### 17. Circuit retrieval (Alg. 1 l.2)
- **Paper:** C^{p_a}_{θ_a} ← RETRIEVE(p_a, G_ASPM).
- **Original code:** `get_action_circuit` (`aspm_tool.py:209-233`, working tree).
- **τ-bench mapping:** union of the circuits of the extracted action predicates.
- **Class:** faithful. **Coverage:** the authors' code. **Work:** none beyond format. **Risk:** low.

### 18. Long-term workflow memory (Alg. 1 l.5)
- **Paper:** W_r ← RETRIEVEWORKFLOW(r, p_a). The memory stores "successful verification workflows for diverse action circuits as permanent memory … continually updated" and uses them as few-shot examples for the plan (§3.3, Memory Modules). Fig. 14 queries `{target_action, keywords}` and returns a stepwise workflow. **Initial content is not specified.**
- **Original code:** SQLite `store_workflow` / `get_workflow` (top 5 by `use_count` per action; `agent/tools/memory_tool.py`). Never called (`agent.py:354-361` commented out; memory server attached to no agent).
- **τ-bench mapping:**
  - Memory starts **empty**.
  - It is filled by running the shield on the **train** split. A workflow (the plan's operation sequence, with predicate→operation choices) is stored when the shield's decision matches the cleaned label.
  - Key: action predicate; retrieval: same action predicate, ranked by embedding similarity of the predicate keywords; top-2 as few-shot.
  - **Frozen before validation/test** (no test-time writes offline). In the online run, freezing is the default, and "continually updated" is an ablation.
- **Class:** faithful mechanism; adapted seeding and freezing. **Justification:** freezing prevents test leakage; the seeding source is unspecified in the paper.
- **Coverage:** the authors' `memory_tool.py` (unused). **Work:** wire it in; fix the `db_path` bug (`agent.py:116-121`).
- **Risk:** the first training passes run without memory. Order effects: fix the train-sample order by seed.

### 19. Short-term memory (interaction history)
- **Paper:** history stored "as KV-cache, minimizing redundant computations"; discarded once the action sequence is verified (§3.3).
- **τ-bench mapping:** the full text history is passed in each prompt. No KV cache over the Azure API; the call cache plays the efficiency role.
- **Class:** adapted. **Justification:** a KV cache is an inference-engine detail unavailable through the API, and it does not change decisions. **Risk:** cost and latency only.

### 20. Shielding plan (Alg. 1 l.6–12; Fig. 15–17)
- **Paper:**
  - While some predicate in P_r is unassigned: A_s ← PLAN(W_r, r, P_r) produces an action plan of shielding operations; EXECUTE each step on (H_<i, o_i); PARSE results into truth values.
  - Fig. 15–17 show the planner: (i) filters irrelevant rules and disambiguates predicates, creating a predicate truth table (`create_predicate_map`); (ii) assigns directly inferable predicates; (iii) calls tools for the others; (iv) uses `binary_check.general_query` for the remaining ones; (v) `check_unassigned`.
- **Original code:**
  - `formulate_solution_space` (one LLM call: filter and ground rules) (`aspm_tool.py:347-530`);
  - a planning agent (Agents SDK, GPT-4o, max 30 turns) with the predicate-map tools (`verification.py`) and moderation (`agent.py:204-258`);
  - instructions: direct inference first, then tools, "make sure all the predicates are assigned even if you are unsure".
- **τ-bench mapping:** keep this structure with nano:
  1. a relevance/grounding call (Fig. 15; the authors' `formulate_solution_space` prompt);
  2. a tool-calling planner loop, max 15 turns, with tools `create_predicate_map`, `assign_predicate_values`, `check_unassigned`, `search` and `binary_check` (components 21–22), with retrieved workflows as few-shot.
  
  Deviation from the authors' code: the planner may assign `unknown`. Unknowns become latent in the MLN (component 13) instead of being forced to a "best guess".
- **Class:** faithful (with G1).
- **Justification for `unknown`:** Alg. 1 loops until all predicates are assigned. With a turn cap, the remaining ones need a defined value; marginalising is the probabilistic reading, and the authors' "best guess" is not in the paper.
- **Coverage:** the authors' planner skeleton (`agent.py`), which uses the openai-agents SDK with the public OpenAI key (not Azure; orientation summary).
- **Work:**
  - port the planner to the Azure client (Responses API with tools), replacing the Agents SDK;
  - fix the predicate-tuple shape bug (`verification.create_predicate_map` 3-tuples vs 4-element lists; design notes §8.4).
- **Risk:** nano tool-calling reliability over many turns; cost per action (plan: about 6–12 calls).

### 21. Search operation
- **Paper:** "Retrieves relevant information from past history H_≤i and enumerates queried items" (§3.3). It is backed by a **fine-tuned InternVL2-2B** model (§3.3, Tool Library).
- **Original code:** `agent/tools/context_search.py` is an empty file.
- **τ-bench mapping:** `search(query, history)` is one nano call over the text history. It returns the enumerated items with turn indices (e.g. "all order ids the user confirmed").
- **Class:** adapted. **Justification:** G1 (no fine-tuned model; nano everywhere by project rule).
- **Risk:** nano extraction errors; long histories (airline up to about 30 turns, which fits in context).

### 22. Binary-Check operation
- **Paper:** "Assigns a binary label to the input query" (§3.3), backed by fine-tuned InternVL2-2B. Fig. 17 shows `binary_check.general_query(query=[...], observation=history+action)` → flags + explanations.
- **Original code:** `agent/tools/binary_query.py` is empty.
- **τ-bench mapping:** `binary_check(queries[], history, action)` is one nano call per batch of up to 10 queries, returning `{flag: true|false|unknown, explanation}` per query.
- **Class:** adapted (G1). **Risk:** batching vs accuracy (plan: pilot 1 vs 10 per call).

### 23. Detect operation
- **Paper:** "Calls moderation APIs to analyze target content and produce guardrail labels for different risk categories" (§3.3), plus moderation tools for images, video and audio.
- **Original code:** `moderate_text` / `moderate_image` via OpenAI `omni-moderation-latest` (`content_moderation.py`); factual checks are stubs.
- **τ-bench mapping:** none.
- **Class:** omitted.
- **Justification:**
  - No airline or retail policy clause concerns harmful or toxic content; the closest ("no subjective recommendations", "do not make up information") is a dialogue judgement that Binary-Check covers.
  - No moderation endpoint is configured on the Azure resource, and adding one would change the Azure configuration.
- **Risk:** none for τ-bench decisions; it should be stated in the paper-comparison table.

### 24. Formal Verify (Alg. 1 l.13)
- **Paper:** l_r ← VERIFY(r, V_s): "run model-checking algorithms to formally verify target rules" (§3.3). The Tool Library names Stormpy; Fig. 18 generates Prover9 code with assignments as assumptions.
- **Original code:** Python `eval` of string-rewritten logic; temporal operators deleted (`certification.py:51-69, 121-196`). LADR/Prover9 sources are vendored but there is no binary (`agent/lib/LADR-2009-02A`, link-order issue `provers.src/Makefile:66`). The Stormpy and pyModelChecking directories are empty gitlinks.
- **τ-bench mapping:** an **LTLf evaluator** over the finite trace (Q1), with Kleene three-valued semantics for `unknown`. It is cross-checked against `flloat` (installs, pure Python) on two-valued cases, plus a property test on random formulas and traces.
- **Class:** adapted.
- **Justification:** for fully assigned predicates, checking r against an assignment is formula evaluation. Prover9 (Fig. 18) and model checking reduce to the same truth value. Stormpy targets probabilistic models (DTMC/MDP) and would be a mismatch for checking a single trace. The App. C.3 semantics (LTLf, Eq. 7) is implemented exactly.
- **Coverage:** v1's `Parser` + `kleene` in `scripts/validate_aspm.py` (propositional), to be extended with temporal operators.
- **Risk:** low.

### 25. Output and explanation
- **Paper:** (l_s, V_s, T_s) (Eq. 1). Fig. 19 shows `report_guardrail{action_allowed, violated_rules, explanation, feedback}`, with per-rule explanation and remediation from `verify_rule` (Fig. 18).
- **Original code:** `{action_allowed, violated_rules[{rule_id, explanation, feedback}], explanation}` (`agent.py:486-516`).
- **τ-bench mapping:** the same JSON, plus `prob_execute`, `prob_non_execute`, `margin`, `epsilon`, `rules_evaluated`, `predicates`, `n_llm_calls`, `seconds` for evaluation.
  - V_s is the set of rules evaluated false at µ_{p_a}=1 that are satisfied at µ_{p_a}=0 (i.e. violated *by the action*).
  - T_s and feedback come from one nano call over the violated rules (Fig. 19 last turn).
- **Class:** faithful. **Risk:** low.

### 26. Online / feedback setting
- **Paper:** "integrate each guardrail method as a post-verification module that copilots with the agent. These guardrails verify the agent's actions step-by-step and provide interactive feedback to help it adjust behavior" (§5.2, Online Guardrail). Metric: policy compliance rate conditioned on task success (Table 4).
- **Original code:** none (offline driver only).
- **τ-bench mapping:**
  - The shield wraps the agent's action execution.
  - Allowed actions run normally.
  - A **blocked tool call is not executed.** The agent instead receives, as that call's tool response, `BLOCKED by policy guardrail. Violated: <rule descriptions>. Explanation: <T_s>. Feedback: <feedback>`. This keeps the tool-call/response pairing valid.
  - A blocked `respond` message is not sent to the user; the agent receives the same text as a system/tool note and must produce another turn.
  - Cap: 3 consecutive blocks on the same step, then let the agent continue. The cap is logged; the paper does not specify one.
- **Class:** adapted (τ-bench interface). **Justification:** τ-bench's action interface has no other feedback channel; the tool response is the natural one.
- **Coverage:** none. **Work:** shielded agent wrapper (in a separately installed τ-bench copy).
- **Risk:** feedback text may itself steer the agent (intended by the paper); latency.

### 27. Evaluation metrics
- **Paper (§5.1):**
  - ACC@G and FPR@G on the overall safety label;
  - ARR@R, the average recall of violated rules from the reported list;
  - NoQ, closed-source API queries per sample;
  - Time, seconds per sample;
  - online: compliance rate conditioned on task success (Table 4).
- **τ-bench mapping:** see Q9. **Class:** adapted; ARR omitted unless annotated (decision D7). **Risk:** label noise.

### 28. Baselines
- **Paper (§5.1):**
  - Direct prompt: GPT-4o with the complete policy outputs a label + violated rules;
  - Rule traverse: prompt for each rule; unsafe if any is violated;
  - GuardAgent (Xiang et al. 2024).
  
  All receive the same policy and output (i) a binary flag and (ii) violated rules.
- **Original code:** none.
- **τ-bench mapping:** see Q8. **Class:** Direct and Rule traverse faithful (G1); GuardAgent decision D8.

---

## Answers to the nine questions

### Q1. Temporal logic: **recommend LTLf over the finite trajectory, with our own small evaluator (flloat as test oracle).**
- **Why LTLf is the faithful choice.** The paper's appendix defines the logic as LTLf over finite traces (App. C.3, Eq. 7), and its extraction prompt allows ALWAYS/EVENTUALLY/NEXT/UNTIL (App. H). v1's single top-level IMPLIES with no temporal operators is a restriction we introduced, inherited from the authors' `logic_to_python` limitations (`certification.py:51-69`).
- **Trace.** One position per agent step (each tool call or respond message), in order.
  - At each position, a predicate's value is the one the shield assigned when it shielded that step. Online, the shield runs on every step, so the trace builds incrementally; offline, the trajectory is replayed step by step.
  - Predicates never assigned at a position are `unknown`.
  - The current position takes the world µ (action executed or not, component 13). Evaluation happens at position 0, so formulas range over the trace so far plus the current step.
- **Evaluator.** About 150 lines: recursive Kleene LTLf semantics with NOT, AND, OR, IMPLIES, NEXT (strong next: false at the last position), ALWAYS, EVENTUALLY, UNTIL.
  - Tested against `flloat` 0.3.0, which installs and evaluates LTLf traces in about 0.1 ms, on random two-valued cases.
  - **Why not flloat directly:** it is two-valued, and we need `unknown`.
- **Packages checked** (scratch venv, 2026-10-15):

| Package | Installs | Fit |
|---|---|---|
| `flloat` 0.3.0 | yes | LTLf truth on finite traces; correct in smoke tests; two-valued only → test oracle |
| `stormpy` 1.14.0 | yes (wheel) | Probabilistic model checking of DTMC/MDP; checking one trace against LTL would need an artificial Markov chain → unsuitable |
| `pyModelChecking` 1.3.4 | yes | LTL/CTL on Kripke structures, infinite-path semantics → finite traces need a self-loop encoding; semantic mismatch with LTLf |
| `ltlf2dfa` 2.0.0 | installs, fails at runtime | Needs the MONA binary (absent) |
| `pylogics` 0.2.1 | yes | No LTL semantics module in this version |
| Prover9 (LADR, vendored) | not built | First-order prover; Fig. 18 only uses it for propositional evaluation |

- **Trade-offs.**
  - Temporal rules need predicate values at *earlier* steps. In practice nano will mostly write past-oriented rules ("must have confirmed before cancelling") as either a temporal formula or a history predicate ("confirmation_obtained"). Both are legal; we do not force either.
  - A rule whose past values were never assigned evaluates to `unknown` and is marginalised (component 13), which weakens it. Report the fraction of temporal rules and of unknown evaluations.

### Q2. Action predicates and circuits: **recommend faithful: abstract action predicates from extraction, LLM EXTRACT at runtime, circuits by Alg. 3.**
- In the paper, action predicates are produced by rule extraction from policy text (App. H; Fig. 8: `delete_data`, `publish_data`), not taken from an environment's action space. EXTRACT maps the concrete action to them (Alg. 1 l.1; Fig. 14).
- τ-bench tool calls are structured, but mapping a tool call to policy-level action predicates is still non-trivial. For example, `update_reservation_flights` is both "change flights" and "change cabin", and `respond` can be "disclose information" or "deny a request". So LLM extraction remains meaningful. It costs one nano call per step.
- **Tool-name mapping (v1) would be adapted, not faithful.** It requires the extraction to use tool names, which means giving tool schemas to the extractor and deterministic attachment. v1 did this and needed S0/S3b/S6, none of which are in the paper.
- **Circuits** follow Alg. 3 exactly (component 11). The collapse risk of its merge step is a reproduction finding to report, not to fix.
- **Tool schemas as extraction input:** the paper's "solution space" input (Fig. 1: logical variables, descriptions, keywords) is not the environment's tool list. **Default: policy text only** (faithful). Tool schemas are given only to EXTRACT at runtime (decision D11).

### Q3. Vagueness measure: **recommend Eq. 3 as written (same-type top-k mean cosine, k = 5, V_r = max), with `text-embedding-3-large` if you add the deployment, otherwise local `bge-large-en-v1.5`.**
- The Azure resource has no embedding deployment (probed).
- Local options: `potion-base-8M` (cached, static, weak) or a transformer encoder (`transformers` 4.33 + `torch` 2.5 installed; model download from the Hugging Face hub works).
- The choice affects only the order in which VR pops rules. With N_b ≥ #rules, every rule is visited, so the effect on the final ASPM is small. Document the model and revision.

### Q4. Shielding operations
- **Search and Binary-Check:** nano instead of fine-tuned InternVL2-2B (adapted, G1). Binary-Check batched up to 10 queries per call, to be validated in a pilot.
- **Detect:** omitted (component 23). No content-moderation clause in either policy, and no moderation endpoint configured.
- **Formal Verify:** the LTLf evaluator (Q1).
- **Planner:** kept as described (Alg. 1 l.6–12, Fig. 15–17): a relevance/grounding step, then a tool-calling loop with workflow few-shot.
  - Two changes from the authors' code: `unknown` is allowed (instead of forced guesses), and turns are capped at 15.
  - The authors' second LLM agent for certification is replaced by deterministic code: Formal Verify plus the MLN. The paper describes certification as tool calls (Fig. 18/19), not as an LLM judgement, and the authors' `verify_llm_rules`, which judges natural-language descriptions, is not in the paper.

### Q5. Memory
- **Long-term:** workflows stored per action predicate after verifications on the **train** split whose decision matched the cleaned label. Retrieved by action predicate + keyword-embedding similarity, top-2 few-shot. Starts empty, frozen for validation/test (component 18).
- **Short-term:** history in the prompt (component 19).

### Q6. MLN and weight learning
- **Inference:** Eq. 4 by exact enumeration over the invoked action predicates and `unknown` state predicates, with Z over those worlds (component 13).
- **Decision:** Eq. 5 (component 14).
- **Training:** Eq. 6 hinge per circuit, θ ~ U(0, 1), plain gradient descent (lr 0.1, ≤ 200 epochs, early stop on validation loss), θ ≥ 0. Predicate values are cached from one runtime pass over train samples (component 15).
- **ε:** maximise balanced accuracy on **validation** (cleaned labels). Also report ε = 0.1 (Fig. 19) and ε = 0. Never tuned on test.

### Q7. Output and feedback
- **Output:** the JSON of component 25.
- **Online:** a blocked tool call is not executed and its tool response is the guardrail report (violated rules, explanation, feedback). A blocked `respond` is withheld and the agent gets the report. At most 3 consecutive blocks per step (component 26).

### Q8. Baselines (all gpt-5-nano, same inputs as ShieldAgent, same output schema `{safe: bool, violated_rules: [...]}`)

| Baseline | Implementation | Class |
|---|---|---|
| **Direct** | One call per shielded step: system = complete policy wiki; user = history + current action; "Is this action safe under the policy? List violated policy statements." | faithful (G1) |
| **Rule traverse** | One call per rule of the **same extracted ASPM** (all rules, not circuits, as in the paper's "traverse each rule"): history + action + rule → violated yes/no; unsafe if any. Cost ≈ #rules calls per step (≈ 100–200). Optimisation, if needed: the step's extracted-action circuits only, reported as a variant. | faithful (G1) |
| **GuardAgent** | Xiang et al. 2024: task-plan + code-generation guard with memory. Not in this repo; needs their public code adapted to τ-bench and nano. | decision D8 (recommend: include only if their code runs with modest adaptation; otherwise omit and say so) |
| No guard | The unshielded agent (online only) | reference |

### Q9. Metrics

| Paper | τ-bench equivalent | Computable? |
|---|---|---|
| ACC@G, FPR@G | Per shielded write call: predicted unsafe vs label. Also per trajectory: unsafe if any call is flagged vs any unsafe label. Report both, on cleaned labels (Deliverable C §6), and on raw expected-action labels as "agreement with expected actions". | yes (label noise caveat) |
| ARR@R | Recall of ground-truth violated rules among reported ones | **No ground truth.** Expected actions give no rule identity. Needs annotation (D7). |
| NoQ | gpt-5-nano calls per shielded step (no closed-source model besides nano) | yes |
| Time | Wall seconds per shielded step and per trajectory (with the call cache disabled for timing runs) | yes |
| Online compliance (Table 4) | Among reward-1 episodes, the fraction with no policy violation | needs a violation judge (D9): expected-action deviation proxy, manual audit sample, or (diagnostic only, if you allow) the gold Python rules |
| (added) pass^1 | Mean τ-bench reward over tasks × trials (τ-bench's pass^k with k = 1) | yes |
| (added) block rate on compliant actions | Fraction of matched-and-reward-1 calls blocked online | yes |

---

## Component classification summary

| Class | Components |
|---|---|
| **faithful** (12) | 1 formulation · 2 predicate types · 3 rule types · 4 policy extraction · 5 LTL rule extraction · 6 VR · 9 iteration/stopping · 13 MLN (formula) · 16 action extraction · 17 circuit retrieval · 20 shielding plan · 25 output |
| **faithful, parameters/data adapted** (6) | 7 vagueness (embedding model) · 8 RP (clustering C, edges) · 11 circuits (θ, k) · 14 ε (selected on validation) · 15 weight learning (data, optimiser hyper-parameters) · 18 workflow memory (seeding, freezing) |
| **adapted** (9) | 19 short-term memory · 21 Search · 22 Binary-Check · 24 Formal Verify (LTLf evaluator) · 26 online feedback · 27 metrics · G1 model · G2 modality · G4 transport (+ G3 benchmark) |
| **omitted** (4) | 10 human review · 12 action tree (unspecified) · 23 Detect · ARR@R unless annotated |
| **open** | 28 GuardAgent baseline (D8) |
