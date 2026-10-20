# Deliverable D: implementation plan (faithful ShieldAgent on τ-bench, gpt-5-nano)

Date: 2026-10-15. Builds on `spec.md` (components 1–28, Q1–Q9), `gap_audit.md` and `data_feasibility.md`. Nothing here is implemented yet.

## Cost assumptions
- **Prices:** gpt-5-nano at list price, about **$0.05 / M input** and **$0.40 / M output** tokens (reasoning tokens bill as output). **Check against your Azure rate card.** All $ figures below scale linearly with it.
- **Shield cost per step.** Measured unit costs from Step 2b: S2–S8 calls average about 1.2 k input / 1.2 k output tokens. A shielded step is estimated at 8–14 nano calls: EXTRACT 1, relevance/grounding 1, planner 4–8 turns, Binary-Check 1–3, Search 0–2, explanation 0–1. At about 6–10 k input tokens per call (history + rules), that is roughly **100 k input + 20 k output ≈ $0.013 per shielded step**.
- **Trajectory length** (recorded τ-bench runs): about 12 agent steps (airline) and 14 (retail).
- **Latency.** Nano calls take about 5–15 s each with reasoning. Wall time is dominated by latency, so phases run 16 parallel workers. The VM's single CPU is not the bottleneck: the work is I/O-bound, except the offline truth tables.

## Stage A scope (2026-10-15)

Stage A = **P0, P1, P2, P6**, with uniform weights (θ = 1), fixed ε (0.1, with ε = 0 as a variant; the sign convention is an open question, see spec "Stage A scope"), and no workflow memory. P3, P4 and P5 move to Stage B. Decisions D1–D4, D8–D11 are final (spec "Stage A scope"); D5, D6, D7 and D12 are deferred.

### Revised cost estimate (Stage A, gpt-5-nano list price, see "Cost assumptions")

| Phase | Measured / estimated | Calls | Cost |
|---|---|---|---|
| P0 infrastructure | measured: tool-loop test (3 calls), two 1-task τ-bench smoke runs (39 + 21 calls) | ≈ 65 | **$0.04** |
| P1 extraction, airline + retail | measured: see `p1_log.md` (filled in after the runs) | ≈ 1–3 k | ≈ $2–4 |
| P2 runtime pilot | 20 train steps per domain | ≈ 500 | ≈ $0.5 |
| P6 online | 165 test tasks × 3 trials ≈ 500 conversations × (≈ 13 shielded steps × ≈ 11 calls + ≈ 20 agent/user calls); unshielded ≈ $10; Direct ≈ $15; ShieldAgent ≈ $90 | ≈ 100 k | ≈ $115 |
| **Stage A total** | | **≈ 0.1 M** | **≈ $120** |

The smoke runs measured **$0.016–0.022 per unshielded conversation** (airline task 0, 21–39 nano calls, 300–500 s). The unshielded P6 condition at 500 conversations is therefore ≈ $10, as estimated. Wall time: 300–500 s per unshielded conversation (sequential calls), so P6 needs ≥ 16 parallel conversations; the shielded condition will be several times slower per conversation.

## Phases

### P0. Infrastructure (no LLM cost)
- **Deliverables:**
  - `ltlf.py`: Kleene LTLf evaluator (spec Q1) with a `flloat` oracle test;
  - embedding backend (D1);
  - Azure Responses tool-calling loop (replaces the openai-agents SDK, which is not wired to Azure);
  - τ-bench step adapter (trajectory → steps);
  - a pinned, *installed* τ-bench copy for online runs (never the read-only reference clone; D6).
- **Validation:**
  - ≥ 10 k random formulas × traces agree with `flloat` on two-valued cases;
  - Kleene unit tests;
  - the embedding backend reproduces cosine values across runs.
- **Cost:** none (embedding model download only).

### P1. Extraction to spec (E1–E5)
- **Deliverables:** `repro_pipeline/` (new package; `policy_pipeline/` v1 stays frozen):
  - E1 policy blocks (App. H);
  - E2 LTLf rules (App. H);
  - E3 VR loop + E4 RP inside Alg. 2 (M_it = 10, N_b = 3 × #rules, vagueness Eq. 3);
  - E5 circuits (Alg. 3);
  - ASPM JSON in the authors' runtime format, plus a weights file.
- **Validation:**
  - 100 % grammar validity;
  - no-gold-leakage test extended to the new package;
  - per-iteration statistics as Table 8 / Fig. 4–6 (#predicates, #rules, vagueness);
  - circuit sizes, and the cluster count before and after the Alg. 3 merge step;
  - optional diagnostic only: Step 2b's E1–E2 comparison against the gold clauses.
- **Cost:** about 0.5–1.5 k calls and 1–3 M output tokens per domain, **≈ $1–2 per domain**. v1 used 1.6 k calls and 1.8 M output tokens per domain.

### P2. Runtime
- **Deliverables:**
  - EXTRACT (`action_grounding`, modified);
  - circuit retrieval;
  - relevance/grounding (`formulate_solution_space`, modified to keep the source predicate);
  - planner loop with `create_predicate_map` / `assign` / `check_unassigned` / `search` / `binary_check`;
  - Formal Verify (LTLf);
  - MLN (Eq. 4/5) with exact enumeration over action + unknown predicates;
  - output/explanation (Fig. 19);
  - workflow memory (empty, freezable).
- **Validation:**
  - an end-to-end run on 20 **train** steps per domain;
  - tool-call parse rate ≥ 98 %;
  - share of steps with no extracted action predicate;
  - share of `unknown` predicates;
  - identical decisions on a cache-warm rerun;
  - a timing run with the cache off.
- **Cost:** pilot about 40 steps ≈ $0.5.

### P3. Data
- **Deliverables:**
  - cleaned labels per D5 (`data_feasibility.md` §6) for train / val / test;
  - optionally, gpt-5-nano trajectories on the retail **train/dev** tasks and the airline **train/val** tasks (D6), labelled with `label_write_actions.py`.
- **Validation:**
  - for the labels: inter-pass agreement on a 50-call re-label;
  - for D6: task-level split integrity (no task in two splits); pass^1 of the unshielded nano agent as a sanity value.
- **Cost:**
  - manual relabelling: no LLM cost (labeller time; about 950 unsafe-labelled calls in all splits);
  - nano trajectories (D6): retail train 500 tasks × 4 trials plus dev 20 × 4 ≈ 2,080 conversations × about 40 calls (agent + user simulator) ≈ 80 k calls, **≈ $60–100**.

### P4. Training
- **Deliverables:**
  1. one runtime pass over the train samples (predicate values cached);
  2. workflow memory seeded from correct decisions, then frozen;
  3. Eq. 6 hinge training per circuit (θ ~ U(0, 1), gradient descent, lr 0.1, ≤ 200 epochs, early stop on validation);
  4. ε selected on validation (balanced accuracy).
- **Validation:**
  - training loss decreases;
  - validation balanced accuracy vs two reference points: uniform weights (θ = 1) and the authors' "deny if any rule is violated";
  - learned weights reported per circuit.
- **Cost:**
  - **D2-a, labelled write steps only:** train ≈ 270 (airline) + 830 (retail) recorded steps ≈ 1.1 k steps ≈ 13 k calls, **≈ $15**;
  - **D2-b, every step of the trajectories:** about 8× more, **≈ $120**;
  - add D6 data if generated (retail train ≈ 2,000 conversations ≈ 3–4 k write steps ≈ $50 on D2-a).

### P5. Offline evaluation (test split)
- **Deliverables:**
  - ShieldAgent, Direct and Rule traverse (+ GuardAgent per D8) on the test split;
  - ACC / FPR per action and per trajectory, on cleaned labels and on raw expected-action labels;
  - NoQ and time;
  - ablations: uniform weights; no memory; deny-on-any-violation; ε ∈ {0, 0.1, selected}; action predicates by tool name (spec Q2 adapted variant).
- **Validation:** the shield never saw test tasks (memory frozen, ε from validation); bootstrap 95 % CIs over tasks.
- **Cost (D2-a):** ShieldAgent about 1.1 k test steps ≈ $15; Direct about $1; Rule traverse about 1.1 k × #rules (≈ 100–200) ≈ 150 k calls ≈ **$40**; ablations reuse cached predicate values (no new LLM cost, except the tool-name variant ≈ $15).

### P6. Online evaluation (τ-bench)
- **Deliverables:** τ-bench runs with the gpt-5-nano agent and user simulator: unshielded, + ShieldAgent, + Direct (+ Rule traverse, circuit variant only, if approved). Airline 50 + retail 115 test tasks × 3 trials.
- **Metrics:** pass^1, compliance conditioned on success (D9), block rate on compliant actions, NoQ, time.
- **Validation:** a 5-task smoke run per configuration; feedback loop cap hits logged.
- **Cost:**
  - ShieldAgent shields every step (faithful): about 500 conversations × about 13 steps × about 11 calls + agent/user calls ≈ 100 k calls, **≈ $90**;
  - unshielded ≈ $10; Direct ≈ $15;
  - Rule traverse online, circuit variant: ≈ $100+, so it is optional.

### Totals (list prices, D2-a, without GuardAgent)
| | Calls | Cost |
|---|---|---|
| Without D6 | ≈ 0.4 M | **≈ $200** |
| With D6 | ≈ 0.5 M | **≈ $300** |

Wall time is several days of mostly unattended API time at 16 workers.

## Main risks
1. **Label noise.** About 60 % of raw "unsafe" labels are task deviations, not policy violations (`data_feasibility.md` §4). Training and accuracy on raw labels would measure the wrong thing. Mitigation: D5 cleaning, and reporting both label sets.
2. **Circuit collapse in Alg. 3.** Merging clusters by co-occurrence may make every circuit nearly the whole ASPM (spec component 11). It is faithful to report, but it raises cost and dilutes weights.
3. **Nano capability.** Three things depend on it: direct LTL writing (v1 needed a separate NL step), a multi-turn tool planner, and batched Binary-Check. Mitigation: pilots in P1/P2, with failure rates reported. The model stays nano (project rule).
4. **Unspecified paper details** (empty App. C.5/D): k, θ, C, N_b, the optimiser and ε are our choices. All are documented, fixed before test, and never tuned on test.
5. **Small airline data:** 50 tasks in total, about 270 labelled train calls. Weights may be underdetermined; report learned vs uniform weights.
6. **Temporal rules with unassigned past steps** evaluate to unknown (D2-a), which weakens them. Report the fraction affected; D2-b removes this at about 8× cost.
7. **Online feedback loops:** the agent may loop on blocks. A cap of 3 is logged.
8. **Cost and latency of Rule traverse** (≈ 100–200 calls per step). Offline only by default.

## Decisions needed from you
| ID | Decision | Options (recommendation first) |
|---|---|---|
| **D1** | Embedding model for vagueness (Eq. 3) and clustering | (a) **add an Azure `text-embedding-3-large` deployment** (faithful; your config change); (b) local `BAAI/bge-large-en-v1.5`, pinned (adapted); (c) keep `potion-base-8M` |
| **D2** | Which steps the shield processes | Online: **every step** (faithful). Offline/training: (a) **labelled write steps only** (≈ $15 per split; past-step temporal values unknown); (b) every step (≈ 8×) |
| **D3** | Hierarchical action tree (Fig. 14 only) | (a) **omit** (unspecified); (b) add an LLM-built two-level tree as an ablation |
| **D4** | Respond messages as actions | (a) **shield them** (faithful: every action); (b) tool calls only |
| **D5** | Label definition for training/evaluation | (a) **3 classes: unsafe-policy / safe / deviation, with a manual relabel of the about 950 unsafe-labelled calls** (by me, written criteria, 50-call re-check); (b) automatic proxy: refusal-task writes + policy-reason API rejections as unsafe; (c) raw expected-action labels |
| **D6** | Generate gpt-5-nano trajectories (installed τ-bench copy) | (a) **yes, retail train/dev + airline train/val tasks, k = 4** (≈ $60–100), keeping retail's 115 test tasks test-only; (b) recorded trajectories only |
| **D7** | Ground truth for ARR@R (violated-rule recall) | (a) **manually annotate violated *policy statements* for test unsafe-policy calls**, then map them to extracted rules; (b) skip ARR. Separately: may the gold curated rules serve as an *annotation aid* for this evaluation label? |
| **D8** | GuardAgent baseline | (a) **include only if their public code runs on τ-bench with modest adaptation**, else omit and state it; (b) omit |
| **D9** | Online compliance judge | (a) **manual audit of a stratified sample of successful episodes**; (b) expected-action deviation proxy; (c) gold Python rules as a diagnostic judge (needs your OK, since gold must not feed the method; it would only score) |
| **D10** | Detect (moderation) omitted for τ-bench | **confirm** |
| **D11** | Tool schemas as extraction input | (a) **no: policy text only** (faithful); schemas only for runtime EXTRACT; (b) yes (adapted, closer to v1) |
| **D12** | Workflow memory at test time | (a) **frozen** (no leakage); (b) continually updated, as an online ablation |
| **D13** | Budget | Approve about $200 (without D6) or about $300 (with D6) at list price |
