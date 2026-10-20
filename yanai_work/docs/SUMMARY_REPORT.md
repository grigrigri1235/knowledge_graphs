# Guarding tool-using agents with policy rules: ShieldAgent reproduction and a tool-grounded alternative

Summary report, 20 October 2026.

## a. Goal and setup

**ShieldAgent** (Chen et al., ICML 2025) is a "guardrail" for LLM agents. Before an agent's action is executed, the
guardrail checks it against rules extracted from a written policy and blocks it if it would break them. The
pipeline has two halves:
1. **Offline:** an LLM turns the policy document into logical rules (linear temporal logic over the agent's
   actions and facts about the situation), refines and merges them, and groups them into "rule circuits".
2. **Online:** for each agent action, the guard maps the action to the rules' vocabulary, asks an LLM to
   determine the truth of each fact in the relevant rules, and decides with a probabilistic logic model whether the
   action is safe enough to run. If not, it blocks the action and explains why.

**τ-bench** is a benchmark of customer-service conversations: an LLM agent helps a simulated user (another LLM)
in an **airline** or a **retail** domain, using tools such as "cancel reservation" or "modify order", under a written
policy (about 5 kB of rules such as "basic economy flights cannot be modified"). A conversation succeeds if the
final database state matches the expected one.

**What we set out to test:**
1. Can ShieldAgent be reproduced faithfully, and does it help on τ-bench?
2. If not, why not, and can a simpler, tool-grounded rule guard do better than a strong simple baseline?

The baseline that matters is **Direct**: one LLM call per action that receives the whole policy and the
conversation and answers "safe or not".

## b. The reproduction

| | |
|---|---|
| Taken from the paper | the full method: policy → rule extraction prompts (verbatim), verifiability refinement, redundancy pruning, rule circuits, the per-action shielding loop, the probabilistic decision (Markov logic network) and its safety threshold, explanation feedback |
| Implemented by us | every part of the pipeline and runtime the authors' code lacks (rule builder, refinement and pruning, weights, decision model, baselines, metrics), plus an online τ-bench harness |
| Model | gpt-5-nano for every role (agent, user simulator, rule extraction, guard) |
| Main deviations | uniform rule weights (no weight learning) and no workflow memory ("Stage A"); local embeddings at reduced precision; structured JSON prompt formats; at most one format-only repair per unparsable rule; the paper's empty appendices filled by documented decisions |
| Rule | rules are never hand-fixed; a hand-written gold rule set is used only for scoring |

## c. Metrics

| metric | meaning | why it matters |
|---|---|---|
| **pass^1** | share of conversations that succeed (mean over tasks and 3 trials), with a 95 % confidence interval (bootstrap over tasks) | the main utility measure: a guard must not stop the agent from doing its job |
| **Δ pass^1** | difference to another configuration, paired by task, with its confidence interval | the honest comparison; intervals that include 0 mean "no detectable difference" |
| **blocks per conversation** | how often the guard stopped an action | each block costs a turn and may derail the conversation |
| **block precision** | share of blocked state-changing actions that the gold rules mark as real policy violations | are the blocks justified? |
| **repeat after block** | how often the agent's next attempt is the identical action | shows whether the guard's feedback is actionable |
| **violations attempted / blocked / executed** | policy-violating state-changing actions the agent tried / the guard stopped / that went through (gold scorer) | the safety side: what the guard prevents and what it lets through |
| **transfers to a human** | conversations that end with a hand-off | a common way for agents to give up after being blocked |
| **cost** | dollars per conversation at list price (agent + user + guard) | guards are run on every step |

The gold scorer is a set of hand-written, mechanically checkable rules. A second version adds two important
checks the first one missed: cancellation eligibility and explicit user confirmation before changes. It is
conservative: when unsure it does not count a violation.

## d. ShieldAgent results, and why it fails

**With the original weak model (gpt-5-nano, test tasks, 3 trials):**

| domain | no guard | Direct | ShieldAgent | ShieldAgent − Direct |
|---|---|---|---|---|
| airline (20 tasks) | 0.300 | 0.267 | 0.250 | −0.02 [−0.15, +0.12] |
| retail (46 tasks) | 0.348 | 0.391 | **0.145** | **−0.25 [−0.35, −0.15]** |

ShieldAgent blocked 4.47 (airline) and 10.45 (retail) times per conversation, against 1.30 and 0.54 for Direct, and
cost 2–3× more.

**With a strong model (gpt-6-luna for every role, training tasks, 3 trials):**

| domain | no guard | Direct | ShieldAgent | ShieldAgent − Direct |
|---|---|---|---|---|
| airline | 0.533 | 0.467 | 0.383 | −0.08 [−0.27, +0.08] |
| retail | 0.761 | 0.681 | **0.362** | **−0.32 [−0.46, −0.18]** |

The strong agent almost never violates the policy on its own (0–7 violating actions in 60–138 conversations), so
guards have little to catch and mostly cost tasks.

**Why ShieldAgent fails: six causes, each with an example from our runs**

| cause | example |
|---|---|
| 1. Missing or unenforceable rule content | the extracted retail rules contain no "return or exchange only if delivered" rule, and the airline rules no cancellation-eligibility rule, so such violations cannot be blocked at all |
| 2. Defective extracted rules | "no tool call after the first order tool call" (retail) blocked 333 ordinary actions in one run |
| 3. Abstract action mapping | the agent's read of order details was mapped to "respond to user" and blocked by "a tool call and a reply cannot happen in the same step" |
| 4. Wrong fact values | a flight change was blocked because the guard judged "HAT023 is not a valid flight number" |
| 5. Structural limits of the decision rule | 23 of 58 airline rules mention no agent action; with circuits keyed by action they can never block anything |
| 6. Non-actionable feedback | after a block, the weak agent repeated the identical call 35–53 % of the time; the 3-blocks cap then let the call through (301 times in retail). The strong agent instead handed the user to a human (79 of 138 retail conversations, vs 15 without a guard) |

## e. Our method: TGR (tool-grounded restriction rules)

| component | what it does | failure cause it addresses |
|---|---|---|
| **A. Tool grounding** | rules are written directly over the agent's tools ("cancel reservation", "respond"); each fact names where its evidence comes from (the action's arguments, earlier tool outputs, the user's messages). No LLM mapping of actions; tools without rules are allowed for free | 3 (mapping), and fewer wrong values (4) |
| **B. Restriction-only rule writing** | one LLM call writes every rule as "this tool is allowed only if <condition>"; exceptions are folded in ("… or the booking was made within 24 hours"); obligations become preconditions; for every policy sentence the model also states what happened to it (rule / exception / fact / not enforceable + reason), which is our coverage check | 1, 2 and 5 (every rule restricts a tool and can block it; nothing is silently dropped) |
| **C. Actionable feedback** | the block message lists each unmet condition with its value and evidence, and says what to do: ask the user, look it up, change the arguments, or stop repeating the call and explain | 6 |

The decision step is ShieldAgent's own probabilistic rule, unchanged (same uniform weights and threshold): only
the rules, the fact-finding and the feedback differ.

**How it was developed.**
- Training tasks only, with gpt-6-luna.
- Five logged iterations, each a generic change to prompts or code (no domain words, no hand-edited rules). For
  example: "conditions must be decidable before the action", "a user's choice counts if the user agreed to the
  agent's proposal", "give the fact checker the policy's background facts such as the current date".
- The method was then **frozen**, before any validation or test task was used.

## f. TGR results

**Training tasks (gpt-6-luna, 3 trials).** Frozen version; earlier version and ablations from iteration 4:

| domain | no guard | Direct | ShieldAgent | **TGR frozen** | TGR − Direct |
|---|---|---|---|---|---|
| airline | 0.533 | 0.467 | 0.383 | **0.500** | +0.03 [−0.08, +0.15] |
| retail | 0.761 | 0.681 | 0.362 | **0.710** | +0.03 [−0.06, +0.12] |

| ablation (iteration 4, train) | airline | retail |
|---|---|---|
| TGR (A + B + C) | 0.533 | 0.667 |
| without B (general temporal-logic rules) | 0.550 | 0.674 |
| without C (ShieldAgent-style explanation) | 0.533 | 0.652 |

Neither B nor C changes pass^1 measurably on train. B halves the number of blocks in retail; C changes what the
agent does after a block.

**Validation tasks** (never used in development; gpt-6-luna, 3 trials):

| domain | no guard | Direct | ShieldAgent | **TGR frozen** | TGR − Direct |
|---|---|---|---|---|---|
| airline (10 tasks) | 0.633 | 0.567 | 0.400 | **0.633** | +0.07 [−0.17, +0.33] |
| retail (23 tasks) | 0.667 | 0.609 | 0.362 | **0.710** | **+0.10 [0.00, +0.22]** |

| validation, guard behaviour | Direct | ShieldAgent | TGR |
|---|---|---|---|
| blocks per conversation (airline / retail) | 0.93 / 1.06 | 3.60 / 7.29 | **0.13 / 0.42** |
| transfers to a human (airline / retail) | 25/30 / 18/69 | 27/30 / 42/69 | 23/30 / **12/69** |
| cost per conversation (airline / retail) | $0.012 / $0.013 | $0.010 / $0.062 | $0.012 / $0.013 |

**Weak agent + strong guard** (gpt-5-nano agent; gpt-6-luna user simulator and guards; training tasks, 3 trials):

STEP5_SUMMARY_TABLE

## g. What we can claim, and what not yet

**We can claim:**
- The faithful ShieldAgent reproduction does not help on τ-bench, with either a weak or a strong model. It loses
  significantly to the simple Direct guard in retail, and we can name the causes with examples.
- TGR removes those failure modes: few blocks, no runaway retries, few hand-offs, cost equal to Direct. On
  validation tasks it is the best of the three guards in both domains, and it is the only guard that does not
  lower the strong agent's success rate.

**We cannot claim yet:**
- That TGR is *significantly* better than Direct. Every interval except retail validation includes 0, and that
  one touches 0. The splits are small (10–46 tasks).
- That TGR prevents more violations. The strong agent attempts so few violations that "caught" and "precision"
  are counts of 0–6. The weak-agent experiment (section f) is the better test of this.
- That the results transfer to another model. The final test-set evaluation with a different model has not been
  run.
- Development and the training numbers use the same tasks. Validation is the only unbiased check so far.

## h. Limitations

- **Domain Basic removal.** For every rule-building method, the policy's descriptive "Domain Basic" section is
  removed (the agent and Direct still see it). Three constraint sentences are lost with it, for example "exchange
  or modify order tools can only be called once".
- **The scorer.** It uses mechanical checks plus regular expressions over the dialogue. It is conservative, so it
  under-counts violations, and its reading of "explicit confirmation" is strict.
- **User-simulator noise.** The weak simulator often speaks like the agent (about 30 % of conversations); the
  strong one less so. The weak-agent experiment therefore uses the strong simulator and is not directly comparable
  with the original reproduction.
- **Models and splits differ** across experiments (weak model on test, strong model on train and validation), so
  only within-experiment comparisons are valid.
- **Single samples.** Each rule set is one LLM sample, and rule writing varies between samples.

## i. Next steps and open decisions

- **Final evaluation (not started; needs approval and budget):**
  - a different, stronger model (grok-4.7) for every role, on the held-out test tasks, once;
  - configurations: no guard, Direct, ShieldAgent (rules rebuilt with that model) and frozen TGR (rules rebuilt
    with that model, same method), 3 trials;
  - success means beating Direct on pass^1 and on block precision;
  - the earlier estimate is about **$300–480**: the three baselines about $280, TGR about $60–180 (it now costs
    about the same as Direct per conversation, so the lower end is likely), and rule rebuilds about $25.
- **Optional before that:** more trials on validation to narrow the intervals, and a manual audit of the
  violations TGR let through (most are policy-reading edge cases of "explicit confirmation").

## Sources

- Detailed record of every experiment, with all numbers: `docs/RESULTS.md`.
- Reproduction: `docs/reproduction/spec.md` (deviations A1–A7, decisions), `p1_report.md`, `p2_pilot_report.md`,
  `p6_report.md` (gpt-5-nano results, failure analysis §3, §6, §10).
- Phase 1 baselines with gpt-6-luna: `docs/tgr/p1_report.md`.
- Scorer v2: `docs/tgr/scorer_v2_report.md`, `policies/gold_v2/README.md`.
- TGR design, iterations and ablations: `docs/tgr/phase2_design.md`, `phase2_log.md`, `p2_report.md`,
  `p2_rules_appendix.md`.
- Validation: `docs/tgr/val_report.md`. Weak agent + strong guard: `docs/tgr/nano_agent_report.md`.
- Limitations: `docs/tgr/known_limitations.md`. Plan and budget: `docs/tgr/plan.md`, `p0_report.md`.
- Failure examples:
  - ShieldAgent retail rule 32 and the read mapped to "respond": `p6_report.md` §1 and §6;
  - "HAT023": airline task 9, `p6_report.md` §1;
  - 23 physical airline rules: `docs/reproduction/p1_report.md` / the `aspm_repro/airline` manifest;
  - transfers 79/138: `docs/tgr/p1_report.md` §3.
