# Phase 2 log: TGR development (gpt-6-luna, train split)

Approved 2026-10-20. Design and protocol: `phase2_design.md`. No grok-4.7 call in this phase. Every change between
iterations is generic: a prompt or code change with no domain words and no rule edits. Rules are never fixed by hand.

Scripts: `output/tgr/phase2/build.sh <run>` (rule build, both domains), `output/tgr/phase2/dev_run.sh <it> [guard] [rules run]`
(1 trial on train). Logs: `output/tgr/phase2/logs/`.

## Code added (no existing behaviour changed)
- `method_tgr/` (rules, runtime, feedback, prompts), `exp_core/tgr_build.py`.
- Guard registration in the three places of AGENTS.md §4b, plus the two scorer scripts:
  - `repro_online/guards.py` (`TGRGuard`, `build(..., rules_dir)`);
  - `repro_online/run.py` (`--guard` choices);
  - `scripts/reproduction/p6_metrics.py` and `gold_compare.py` (guard tuples).
- `exp_core/run_online.py --rules-dir`.
- Tests: `tests/method_tgr/test_tgr.py`. `method_tgr` was added to the NoGoldLeakage packages and to the
  domain-agnostic packages.

## Iterations

### Iteration 1 (2026-10-20): first rule set and run
- **Build `it1`:**
  - airline: 46 sentences → 38 rules, 44 predicates; rules on 8 actions; dispositions 31 rule / 4 exception /
    6 fact / 5 not enforceable; no repair; $0.006;
  - retail: 38 sentences → 58 rules, 22 predicates; rules on all 17 actions; 1 repair round; $0.011.
- **Run `tgr_dev_it1`** (1 trial, all train tasks). tgr vs the Phase 1 baselines on the same trial:

  | | pass^1 tgr | none | Direct | ShieldAgent | blocks/conv tgr | of them on respond | blocked writes confirmed by gold v2 | transfers tgr vs none |
  |---|---|---|---|---|---|---|---|---|
  | airline | 0.450 | 0.600 | 0.400 | 0.400 | 6.45 | 122 of 129 | 1/7 | 18/20 vs 12/20 |
  | retail | 0.609 | 0.696 | 0.630 | 0.348 | 6.89 | 251 of 317 | 0/16 | 14/46 vs 6/46 |

- **Failure classes, from reading the blocked steps:**
  1. Message-quality rules on `respond` ("responses must be grounded and non-subjective"; "deny requests that
     violate the policy") produced 117 + 22 airline and 250 retail blocks of ordinary replies, and with them the
     extra transfers.
  2. A circular precondition: "get_order_details IMPLIES the order belongs to the authenticated user" can only be
     decided from the call's own result. It is always unknown and blocks every first look-up (42 retail blocks).
  3. Conditional requirements written unconditionally: "book IMPLIES uses the regular-member allowance", judged
     false for a gold member. The situation was hidden in the predicate's description.
  4. Over-literal judging: "asked for origin" is false although the user volunteered it; passenger details are "not
     supplied" because they came from a tool output.
  5. **Correct blocks by the policy's wording** (kept): a cancellation after "please cancel X" without a yes to
     listed details (gold v2 flags this as well); a missing reminder to confirm all items before an item
     modification or exchange.
- **Changes for iteration 2** (generic; prompts only):
  - New `prompts/scope.md` ("What a rule can check"), shared by the B and not-B rule-writing prompts. It says:
    - conditions must be decidable before the action, never from the action's own result;
    - situational requirements are written as `X IMPLIES (NOT situation OR requirement)`, and predicate
      descriptions contain no "if";
    - `respond` rules only for specific restrictions on what one message may do; no rules on the general quality of
      messages or on which requests to refuse;
    - no rules on how actions are combined within one turn.
  - `prompts/judge.md`: information that must have been obtained counts as obtained if the user provided it or a
    tool returned it, whether or not the agent asked, unless the predicate names one source.

### Iteration 2 (2026-10-20): scope rules for rule writing; source-agnostic "obtained"
- **Build `it2`:**
  - airline: 31 rules on 7 actions, none on `respond` or reads; message-quality and turn-format sentences are
    `not_enforceable`, with reasons;
  - retail: 42 rules on 12 actions; one `respond` rule (no customer information before authentication); the
    per-tool "no unanswered tool call" rules are gone;
  - cost $0.010 + $0.009, 1 repair round each.
- **Run `tgr_dev_it2`:**

  | | pass^1 tgr | none | Direct | blocks/conv (read, respond, write) | cap | blocked writes confirmed by gold v2 | transfers tgr vs none | guard $/conv |
  |---|---|---|---|---|---|---|---|---|
  | airline | 0.500 | 0.600 | 0.400 | 0.50 (3, 0, 7) | 0 | 1/7 | 16/20 vs 12/20 | 0.0011 |
  | retail | **0.739** | 0.696 | 0.630 | 0.74 (3, 2, 29) | 0 | 1/29 | 9/46 vs 6/46 | 0.0042 |

- **Findings:**
  - Respond blocks fell from 373 to 2. Retail TGR passes more tasks than no shield on this trial.
  - Almost every retail write block enforces a literal requirement that gold v2 does not score: the user must
    provide the payment method for a price difference; the user must confirm the order id, items and refund method.
    The agent then asks, and the task mostly succeeds (reward 1 in 22 of 29). Gold-v2 block precision is therefore
    low, although the policy's text supports the blocks.
  - The 4 gold-v2 "executed violations" in retail are writes made after a block. TGR asked for the payment method,
    the user replied "Use PayPal.", and the agent executed without a new "yes". The scorer reads this as an
    unconfirmed final detail. The judge had counted the earlier "yes".
  - Airline losses against no shield (tasks 0, 1, 5, 30):
    - task 0: an ordering precondition ("user id obtained before the trip questions") cannot be repaired at action
      time;
    - tasks 1 and 30: "no flown segments" is unknown because the judge does not know the current date. It is a
      policy sentence (disposition "fact"), but the judge sees only the conversation;
    - task 5: a transfer was blocked because "the issue cannot be resolved with the available tools" was judged
      unknown.
- **Changes for iteration 3** (generic):
  1. Rule writing returns `background_sentences`: ids of policy sentences that state facts needed to decide the
     predicates (for example, the current date). The judge receives their text as "Background facts from the
     policy". This is in both the B and not-B prompts (`predicates_*.md`, schema, `runtime._judge`).
  2. `scope.md`: a precondition may require that something happened before the action, but not an order among
     earlier steps.
  3. `judge.md`: a confirmation counts only for details stated to the user before it was given.
  4. `judge.md`: predicates that need a judgment about the situation (not a fact to look up) are decided true or
     false; unknown is for missing facts.

### Iteration 3 (2026-10-20): background facts, no ordering preconditions, stricter confirmation, decided judgments
- **Build `it3`:** airline 34 rules on 8 actions; retail 42 rules on 15 actions; 1 repair round each. The model's
  `background_sentences` were empty for airline and listed restriction sentences for retail. The current time (a
  disposition-"fact" sentence) therefore did not reach the judge.
- **Run `tgr_dev_it3`:**

  | | pass^1 tgr | none | Direct | blocks/conv | gold-confirmed write blocks | executed violations/conv v2 | transfers tgr vs none |
  |---|---|---|---|---|---|---|---|
  | airline | 0.350 | 0.600 | 0.400 | 0.95 | 3/17 | 0.100 (1 accepted, 1 rejected) | 18/20 vs 12/20 |
  | retail | 0.739 | 0.696 | 0.630 | 0.43 | 1/14 | **0.000** | **4/46** vs 6/46 |

- **Findings:**
  - Retail is stable: the same pass^1 as it2, half the blocks, no executed violations (the confirmation change
    worked), and fewer transfers than no shield.
  - Airline is worse, and the causes are in the rule set:
    - this sample did not fold two exceptions. The cabin-change permission became a separate restriction for every
      reservation (`NOT cabin_is_changed OR flights_are_unchanged`, which blocked business-class flight changes in
      tasks 7 and 15), and "basic economy cannot be modified" lost its cabin exception. it2 had folded both
      correctly, so rule writing varies between samples;
    - "no flown segments" is still unknown without the date (tasks 1, 30);
    - "obtain information" became "asked for" or "provided by the user" ("trip details requested before booking",
      "passenger details provided by user"), which is false when the user volunteered the information or chose
      their profile.
- **Changes for iteration 4** (generic):
  1. The judge's background facts are the sentences the model lists **plus, under B, every sentence with disposition
     "fact"** (`rules.build_rules`). Under not-B only the model's list exists; this is part of what B provides.
  2. `scope.md`: a requirement to obtain information means "the information is known from the conversation (user or
     tool)", not "a particular question was asked" or "the user stated it". Requirements to inform, offer, remind
     or ask for a decision are unchanged.
  3. Rule writing runs at effort `high` (was `medium`), to reduce defects that vary between samples. The cost is a
     one-off of about $0.02 per domain. ShieldAgent's P1 used `medium`; P1 is a different, many-call pipeline.
- **Operational note (it4 build):** at effort `high`, one rule-writing call takes longer than the 420 s client
  timeout, so it timed out and retried. The first attempt was stopped after 20 min (`build_it4.aborted.log`).
  `exp_core/tgr_build.py` now uses a 1,800 s request timeout for the build process only (`--timeout`). This is a
  harness setting and changes no prompt.

### Iteration 4 (2026-10-20): fact background, "information known", rule writing at effort high — final
- **Build `it4`** (effort high, 1 call each, no repair):
  - airline: 35 rules on 7 write and transfer actions; the basic-economy cabin exception and every cancellation
    exception are folded in as OR; 20 background sentences, including the current time;
  - retail: 61 rules on 15 actions; $0.01 each.
- **Run `tgr_dev_it4`:**

  | | pass^1 tgr | none | Direct | blocks/conv (read, respond, write) | gold-confirmed write blocks | executed violations/conv v2 | transfers tgr / none / Direct | guard $/conv |
  |---|---|---|---|---|---|---|---|---|
  | airline | 0.500 | 0.600 | 0.400 | 0.25 (3, 0, 2) | 0/2 | **0.000** | 14 / 12 / 15 | 0.0011 |
  | retail | **0.761** | 0.696 | 0.630 | 1.22 (25, 5, 26) | 1/26 | 0.065 | 6 / 6 / 11 | 0.0059 |

- **Findings:**
  - With the date known, cancellations of unflown trips pass.
  - Retail's most frequent block (25) is "get_order_details IMPLIES the order belongs to the authenticated user"
    before the user's details were retrieved. The feedback says to look it up, and the agent calls
    get_user_details first. This costs turns but is policy-consistent (authentication), and pass^1 is not hurt.
  - 2 of the 3 retail "executed violations" are writes after a TGR block that asked for the payment method. The user
    named the method ("Use my Mastercard ending in 1531.") and the agent executed without a further "yes". gold v2
    counts this as unconfirmed. Whether a user's own explicit choice needs a separate "yes" is a reading of the
    policy; it is left as is and reported. The third was rejected by the API.
- **Decision:** development stops here; this is the 4th iteration and the protocol allows about 5. The final rule
  sets are the it4 builds, made by the final prompts and code. There was no selection among samples: it4 is the
  only build of the final prompt state. The not-B ablation rule sets are built once with the same prompts, effort
  `high` and `--no-b` (run id `final_nob`).

## Final runs (2026-10-20)
- Rule sets published:
  - `tgr_rules/<d>/full/` = `it4` (A+B);
  - `tgr_rules/<d>/nob/` = `final_nob` (A, not B; effort high; 1 call each, no repair).
- `output/tgr/phase2/final_runs.sh`: tgr, tgr_nob and tgr_noc, 3 trials on train, tag `luna_train`, 3 lanes. All
  594 conversations finished, with no errors and no content-filter failures. Wall time: retail about 40 min per
  configuration, airline about 15 min.
- Metrics: `scripts/tgr/metrics.py luna_train` (gold v1 and v2), `gold_compare.py`. Report: `p2_report.md`; rules
  and dispositions: `p2_rules_appendix.md`.
- Phase 2 spend ≈ $11.2: rule builds $0.09, development runs $3.62 (264 conversations), final runs $7.50.

### Iteration 5 (2026-10-20, after the Phase 2 report; requested by the user): the three judge problems — FROZEN
- **Changes** (generic; prompts only):
  1. **Over-literal choices.**
     - `scope.md`: a requirement that the user provide, choose or decide something is met when the user stated it
       or agreed to an option the agent presented. Rules must not require that the user typed the value or that
       the agent used particular wording.
     - `judge.md`: the same for judging. A requirement that the agent ask for something is met if the agent
       presented options or a proposal and the user answered.
  2. **Date-dependent predicates.** `judge.md`: the background facts (current date and time) are known; use them
     together with the conversation, for example by comparing dates in tool outputs with the current date. "unknown"
     only if a fact neither is in the conversation nor follows from the background facts.
  3. **Precondition stricter than the policy.**
     - `scope.md`: a prohibition becomes `X IMPLIES NOT forbidden_situation`, with a predicate that is true when the
       conversation shows the forbidden situation. It is not turned into a proof obligation unless the policy
       requires that check before the action.
     - `judge.md`: a predicate describing a forbidden or conflicting situation is true only if the conversation shows
       it, and false if nothing indicates it.
- **Build `it5`** (effort high):
  - airline: 34 rules on 8 actions (now including certificate-offer restrictions on `respond`), 1 repair round,
    13 background facts including the current time, $0.017;
  - retail: 64 rules on 15 actions, no repair, $0.011.
  - Retail ownership is now `NOT request_is_for_another_user`, and payment requirements are "user chose …"
    predicates.
- **Evaluation: 3 trials on train** (tag `luna_train_v5`, with copies of the Phase 1 baseline episodes for the
  paired comparison):

  | | pass^1 it5 | it4 (`p2_report`) | none | Direct | Δ vs Direct (paired) | blocks/conv it5 / it4 | executed violations/conv v2 it5 / it4 | transfers it5 / it4 |
  |---|---|---|---|---|---|---|---|---|
  | airline | 0.500 | 0.533 | 0.533 | 0.467 | +0.033 [−0.083, +0.150] | 0.20 / 0.38 | 0.050 / 0.083 | 42 / 39 |
  | retail | **0.710** | 0.667 | 0.761 | 0.681 | **+0.029** [−0.058, +0.123] | 0.39 / 0.97 | 0.014 / 0.029 | 22 / 29 |

  - Retail improves: half as many blocks, fewer transfers, and now above Direct (CI includes 0).
  - Airline moves within noise.
  - The remaining blocks are mostly literal policy requirements: the reminder to include all items before an item
    change or exchange, confirmation of listed details, and authentication before disclosure.
- **Frozen:** this state is the frozen method (git tag `tgr-frozen-v1`). Rule sets are published to
  `tgr_rules/<d>/frozen/`. No method changes after this point: the validation check and the weak-agent experiment
  use it as is.
