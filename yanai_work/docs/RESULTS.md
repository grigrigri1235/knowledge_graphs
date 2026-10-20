# RESULTS: consolidated record of all experiments

Last updated 2026-10-20. This file collects every experiment so far in one place; the detailed reports remain the
source of truth (linked per experiment). τ-bench v1, domains airline and retail. Splits are task-level
(`output/reproduction/labels/splits.json`): airline train 20 / val 10 / test 20 tasks; retail train 46 / val 23 /
test 46. All configurations use the same harness (`repro_online/episode.py`): blocked tool calls get the guard's
feedback as tool output, blocked replies are not sent and the agent receives the feedback as a system note; after
3 consecutive blocks at one step the 4th attempt is executed (cap override); at most 30 executed actions per
conversation.

**Metrics** (all scripts run without LLM calls):
- **pass^1** mean reward over tasks × trials; **pass^3** probability that 3 trials all succeed; 95 % CIs by
  bootstrap over tasks (10,000 resamples); **Δ** = paired by task (`scripts/tgr/metrics.py`, same bootstrap as P6).
- **blocks / conv.** blocked attempts per conversation; **cap** cap overrides.
- **block precision** share of blocked *write* calls that the gold scorer marks as a policy violation (scoring only;
  v1 = Step-2 Python rules, v2 = v1 + confirmation and cancellation-eligibility checks; `policies/gold_v2/`).
- **violations attempted / blocked / executed (gold v2)**: violating write calls the agent executed plus violating
  write attempts a guard blocked / the blocked part / the executed part (API-accepted in brackets where reported).
- **transfers** conversations whose last executed action is a transfer to a human agent.
- **cost** list price per conversation (agent + user + guard), without cached-input discount.

Configurations: **none** (no guard); **Direct** (one LLM call per step with the complete policy); **ShieldAgent**
(faithful Stage A: uniform θ = 1, ε = 0.1); **TGR** (our method: A tool-grounded rules, B restriction-only rule
writing, C actionable feedback; `method_tgr/`).

---

## 1. P6: faithful ShieldAgent reproduction, gpt-5-nano, test split (2026-10-17)

- **Goal.** Measure the reproduced ShieldAgent online against no guard and the Direct baseline.
- **Setup.** Every role gpt-5-nano (agent, user simulator, rule extraction, guards). Test split, 3 trials,
  594 conversations. ASPMs `aspm_repro/` (airline v4: 58 rules; retail v1: 43 rules), extracted by the frozen P1
  pipeline (tag `repro-p1-v1`).
- **Cost.** $20.81 (+ smoke $1.28, resume $0.07). The user-simulator cost is under-counted (τ-bench keeps only the
  last call); true total ≈ $23.5 at most (`p6_report.md` §7 note).

| domain | config | pass^1 [95 % CI] | pass^3 | Δ vs none | Δ vs Direct | blocks / conv. | cap | block precision v1 → v2 (n) | violations v2 att. / blocked / exec. (acc.) | transfers | $ / conv. |
|---|---|---|---|---|---|---|---|---|---|---|---|
| airline | none | 0.300 [0.150, 0.467] | 0.100 | – | +0.033 | – | – | – | 109 / 0 / 109 (79) | 34/60 | 0.015 |
| airline | Direct | 0.267 [0.100, 0.450] | 0.200 | −0.033 [−0.167, +0.117] | – | 1.30 | 3 | 0.52 → 0.79 (33) | 85 / 26 / 59 (42) | 44/60 | 0.029 |
| airline | ShieldAgent | 0.250 [0.133, 0.383] | 0.000 | −0.050 [−0.183, +0.083] | −0.017 [−0.150, +0.117] | 4.47 | 29 | 0.13 → 0.66 (89) | 139 / 59 / 80 (67) | 41/60 | 0.055 |
| retail | none | 0.348 [0.246, 0.457] | 0.109 | – | −0.043 | – | – | – | 83 / 0 / 83 (28) | 66/138 | 0.013 |
| retail | Direct | 0.391 [0.290, 0.493] | 0.130 | +0.043 [−0.036, +0.123] | – | 0.54 | 3 | 0.59 → 0.63 (46) | 76 / 29 / 47 (23) | 54/138 | 0.024 |
| retail | ShieldAgent | **0.145** [0.080, 0.217] | 0.022 | **−0.203 [−0.312, −0.101]** | **−0.246 [−0.348, −0.152]** | 10.45 | 301 | 0.24 → 0.35 (181) | 95 / 63 / 32 (11) | 101/138 | 0.071 |

(Violations, transfers and the ShieldAgent-vs-Direct Δ were computed from the P6 episodes on 2026-10-20 with the
gold v2 scorer; they are not in `p6_report.md`.)

- **Findings.** ShieldAgent costs 20 points of pass^1 in retail; Direct is at least as good on every metric.
  Blocks are driven by over-general timing / mutual-exclusion rules, abstract action mapping (reads mapped to
  "respond"), and wrong predicate values; the agent repeats the identical blocked call 35–53 % of the time, so the
  cap turns the shield into a delay (301 retail cap overrides).
- **Caveats.** Weak agent (pass^1 0.30 / 0.35 without a guard); the nano user simulator speaks like the agent in
  ~30 % of conversations; gold v1 missed many violations (see §3).
- **Details.** `docs/reproduction/p6_report.md`, `p6_log.md`; raw `output/repro/p6/full/`.

## 2. Phase 1: baselines with gpt-6-luna, train split (2026-10-19/20)

- **Goal.** Baselines with a stronger model for developing new methods.
- **Setup.** Every role gpt-6-luna (profile `luna-dev`; agent and user via the Responses API, effort medium).
  ShieldAgent's P1 rebuilt with luna by the frozen pipeline from the policy **without its Domain Basic section**
  (airline 57 rules, retail 57; `output/tgr/aspm_runs/luna-dev/`). Train split, 3 trials, 594 conversations.
- **Cost.** ≈ $11.9 (P1 rebuild $0.67, runs $11.25).

| domain | config | pass^1 [95 % CI] | pass^3 | Δ vs none | Δ vs Direct | blocks / conv. | cap | block precision v1 → v2 (n) | violations v2 att. / blocked / exec. | transfers | $ / conv. |
|---|---|---|---|---|---|---|---|---|---|---|---|
| airline | none | 0.533 [0.35, 0.72] | 0.350 | – | +0.067 [−0.033, +0.167] | – | – | – | 1 / 0 / 1 | 40/60 | 0.0060 |
| airline | Direct | 0.467 [0.28, 0.65] | 0.350 | −0.067 [−0.167, +0.033] | – | 1.10 | 2 | 0.00 → 0.00 (4) | 3 / 0 / 3 | 44/60 | 0.0125 |
| airline | ShieldAgent | 0.383 [0.18, 0.60] | 0.350 | −0.150 [−0.367, +0.067] | −0.083 [−0.267, +0.083] | 3.37 | 12 | 0.00 → 0.00 (5) | 0 / 0 / 0 | 55/60 | 0.0092 |
| retail | none | 0.761 [0.67, 0.86] | 0.565 | – | +0.080 [0.000, +0.167] | – | – | – | 7 / 0 / 7 | 15/138 | 0.0068 |
| retail | Direct | 0.681 [0.58, 0.78] | 0.457 | −0.080 [−0.167, 0.000] | – | 1.10 | 1 | 0.07 → 0.21 (14) | 3 / 3 / 0 | 30/138 | 0.0128 |
| retail | ShieldAgent | **0.362** [0.24, 0.49] | 0.283 | **−0.399 [−0.522, −0.275]** | **−0.319 [−0.457, −0.181]** | 5.93 | 47 | 0.00 → 0.07 (152) | 12 / 11 / 1 | 79/138 | 0.0499 |

- **Findings.** The luna agent is strong and almost never violates the policy on its own, so both guards mainly cost
  tasks. ShieldAgent's defect classes persist with a stronger model (timing rules, "grounded information" rules on
  replies); with luna the agent rarely repeats a blocked call but hands the user to a human instead (79/138 vs 15).
- **Caveats.** Train split (not comparable with P6's test split); wall times inflated by a stuck process on the
  1-CPU VM; Domain Basic removal confounds a P1-luna vs P1-nano rule comparison.
- **Details.** `docs/tgr/p1_report.md`, `phase1_log.md`; raw `output/tgr/online/luna_train/{none,direct,shield}`.

## 3. Gold scorer v2: re-scoring P6 and Phase 1 (2026-10-20)

- **Goal.** Close the two documented scorer gaps (cancellation eligibility; explicit user confirmation before writes).
- **Setup.** Deterministic dialogue checks for three gold predicates (AIR-R042, AIR-R002, RET-R005), written from
  the policy text and hand-checked on ~60 calls; v1 unchanged and byte-identical on re-score. No LLM calls; cost $0.

| write calls the v1 scorer missed (API-accepted) | none | Direct | ShieldAgent |
|---|---|---|---|
| P6 airline (nano) | 62 (53) | 31 (22) | 42 (37) |
| P6 retail (nano) | 25 (22) | 23 (23) | 11 (10) |
| Phase 1 airline (luna) | 1 (1) | 2 (2) | 0 |
| Phase 1 retail (luna) | 1 (1) | 0 | 0 |

- **Findings.** v1 under-counted nano's violations about 2× (mostly blanket "yes, proceed" given before details
  were listed); P6's "no accepted violation in successful conversations" no longer holds (5 of 6 configs, 5–15 % of
  successes); P6 block precision rises (ShieldAgent airline 0.13 → 0.66). The luna agent remains almost compliant.
- **Caveats.** Regular expressions over the dialogue: conservative ("unknown" is not a violation), so recall is
  still limited; the F5 rule is a strict reading of "list the details, then confirm".
- **Details.** `docs/tgr/scorer_v2_report.md`, `policies/gold_v2/README.md`; outputs `gold_v2.jsonl`,
  `metrics_gold_v2.json`, `gold_compare.json` next to each run.

## 4. Phase 2: TGR development, ablations and freeze, train split, gpt-6-luna (2026-10-20)

- **Goal.** Build TGR (A + B + C, each behind a flag) and develop it with generic changes only.
- **Setup.** gpt-6-luna for every role (`luna-dev`); rules written in one call per domain from the Domain-Basic-
  filtered policy and the environment's tool schemas; decision = ShieldAgent's Eq. 4–5 unchanged (θ = 1, ε = 0.1).
  Iterations 1–4 evaluated with 1 trial on train, iteration 4 and the ablations with 3 trials; iteration 5 (after
  the Phase 2 report) with 3 trials, then **frozen** (git tag `tgr-frozen-v1`, rules `tgr_rules/<domain>/frozen/`:
  airline 34 rules, retail 64).
- **Cost.** ≈ $11.2 (iterations 1–4 and final runs) + $2.33 (iteration 5).

**Iterations** (generic prompt/code changes only; pass^1 on train):

| iteration | main change | trials | airline | retail |
|---|---|---|---|---|
| 1 | first rule set | 1 | 0.450 | 0.609 |
| 2 | scope rules: decidable before the action, no message-quality rules, situations in the condition | 1 | 0.500 | 0.739 |
| 3 | background facts for the judge; no ordering preconditions; confirmation covers prior details | 1 | 0.350 | 0.739 |
| 4 | facts = "fact" sentences; "information known" instead of "asked"; rule writing at effort high | 1 / **3** | 0.500 / **0.533** | 0.761 / **0.667** |
| 5 (frozen) | user choices incl. agreeing to a proposal; date facts used; prohibitions not proof obligations | **3** | **0.500** | **0.710** |

**Final configurations, 3 trials:**

| domain | config | pass^1 [95 % CI] | pass^3 | Δ vs none | Δ vs Direct | blocks / conv. | cap | block precision v2 (n) | violations v2 att. / blocked / exec. | transfers | $ / conv. |
|---|---|---|---|---|---|---|---|---|---|---|---|
| airline | TGR it4 | 0.533 [0.33, 0.73] | 0.450 | +0.000 [−0.133, +0.117] | +0.067 [−0.050, +0.200] | 0.38 | 0 | 0.12 (16) | 7 / 2 / 5 | 39/60 | 0.0090 |
| airline | TGR it4 − B | 0.550 [0.35, 0.75] | 0.450 | +0.017 [−0.117, +0.167] | +0.083 [−0.067, +0.233] | 0.50 | 0 | 0.00 (22) | 1 / 0 / 1 | 45/60 | 0.0086 |
| airline | TGR it4 − C | 0.533 [0.33, 0.73] | 0.450 | +0.000 [−0.150, +0.133] | +0.067 [−0.050, +0.200] | 0.32 | 0 | 0.29 (14) | 6 / 4 / 2 | 40/60 | 0.0078 |
| airline | **TGR frozen (it5)** | 0.500 [0.32, 0.68] | 0.300 | −0.033 [−0.133, +0.050] | +0.033 [−0.083, +0.150] | 0.20 | 0 | 0.17 (6) | 4 / 1 / 3 | 42/60 | 0.0097 |
| retail | TGR it4 | 0.667 [0.56, 0.78] | 0.478 | −0.094 [−0.181, −0.007] | −0.014 [−0.101, +0.072] | 0.97 | 0 | 0.03 (64) | 6 / 2 / 4 | 29/138 | 0.0136 |
| retail | TGR it4 − B | 0.674 [0.57, 0.78] | 0.457 | −0.087 [−0.167, −0.007] | −0.007 [−0.087, +0.080] | 1.99 | 1 | 0.07 (61) | 8 / 4 / 4 | 23/138 | 0.0158 |
| retail | TGR it4 − C | 0.652 [0.55, 0.75] | 0.370 | −0.109 [−0.188, −0.029] | −0.029 [−0.109, +0.051] | 1.26 | 0 | 0.08 (71) | 11 / 6 / 5 | 24/138 | 0.0140 |
| retail | **TGR frozen (it5)** | **0.710** [0.60, 0.81] | **0.565** | −0.051 [−0.123, +0.022] | **+0.029 [−0.058, +0.123]** | 0.39 | 0 | 0.04 (45) | 4 / 2 / 2 | 22/138 | 0.0125 |

(Baselines for these rows: §2.)

- **Findings.** Tool grounding + restriction rules removed ShieldAgent's main failure modes (blocks on reads and
  replies, cap overrides, repeat loops, mass transfers) at ¼–1/7 of its guard cost. Ablations: neither B nor C has a
  measurable pass^1 effect on train (B halves retail blocks; C changes the agent's next action). A manual audit of
  iteration-4 blocks showed most remaining false blocks were wrong or over-literal predicate values, which
  iteration 5 addressed.
- **Caveats.** Development and these measurements use the same train tasks (optimistic for TGR); 20 / 46 tasks
  with 3 trials cannot resolve effects below about ±0.08; rule writing varies between samples (one sample per build).
- **Details.** `docs/tgr/p2_report.md` (iteration 4 + ablations), `phase2_log.md` (all iterations incl. 5),
  `phase2_design.md`, `p2_rules_appendix.md`; raw `output/tgr/online/{tgr_dev_it1..4, luna_train, luna_train_v5}`.

## 5. Validation check: frozen TGR on the val split, gpt-6-luna (2026-10-20)

- **Goal.** Check the frozen method on tasks never used in development.
- **Setup.** `luna-dev`; val split (airline 10 tasks, retail 23), 3 trials, 396 conversations; none, Direct,
  ShieldAgent (luna-dev P1 rules), frozen TGR. No change after seeing val.
- **Cost.** $7.83.

| domain | config | pass^1 [95 % CI] | pass^3 | Δ vs none | Δ vs Direct | blocks / conv. | cap | block precision v2 (n) | violations v2 att. / blocked / exec. (acc.) | transfers | $ / conv. |
|---|---|---|---|---|---|---|---|---|---|---|---|
| airline | none | 0.633 [0.37, 0.87] | 0.500 | – | +0.067 [0.000, +0.167] | – | – | – | 2 / 0 / 2 (2) | 21/30 | 0.0078 |
| airline | Direct | 0.567 [0.27, 0.83] | 0.500 | −0.067 [−0.167, 0.000] | – | 0.93 | 0 | 0.00 (5) | 1 / 0 / 1 (1) | 25/30 | 0.0116 |
| airline | ShieldAgent | 0.400 [0.10, 0.70] | 0.400 | −0.233 [−0.467, −0.033] | −0.167 [−0.400, 0.000] | 3.60 | 5 | 0.00 (1) | 0 / 0 / 0 | 27/30 | 0.0103 |
| airline | **TGR frozen** | **0.633** [0.40, 0.87] | 0.400 | 0.000 [−0.200, +0.200] | +0.067 [−0.167, +0.333] | 0.13 | 0 | 0.00 (2) | 3 / 0 / 3 (3) | 23/30 | 0.0116 |
| retail | none | 0.667 [0.49, 0.83] | 0.522 | – | +0.058 [−0.072, +0.203] | – | – | – | 1 / 0 / 1 (0) | 14/69 | 0.0069 |
| retail | Direct | 0.609 [0.43, 0.77] | 0.478 | −0.058 [−0.203, +0.072] | – | 1.06 | 2 | 0.00 (4) | 2 / 0 / 2 (2) | 18/69 | 0.0133 |
| retail | ShieldAgent | 0.362 [0.17, 0.55] | 0.304 | −0.304 [−0.478, −0.145] | −0.246 [−0.478, −0.014] | 7.29 | 25 | 0.06 (98) | 6 / 6 / 0 | 42/69 | 0.0623 |
| retail | **TGR frozen** | **0.710** [0.54, 0.87] | **0.609** | +0.043 [−0.043, +0.130] | **+0.101 [0.000, +0.217]** | 0.42 | 0 | 0.08 (26) | 6 / 2 / 4 (4) | 12/69 | 0.0131 |

- **Findings.** The train ranking holds: TGR is the best guard in both domains and matches (airline) or exceeds
  (retail) no shield; retail transfers are the lowest of all configs. ShieldAgent again loses 0.17–0.25 vs Direct.
- **Caveats.** Small split (10 / 23 tasks), wide CIs; the luna agent attempts few violations, so precision and
  violations-caught are small-number statistics; TGR's executed violations are policy-reading edge cases
  (instructions accepted as confirmation), not forced-through blocks.
- **Details.** `docs/tgr/val_report.md`; raw `output/tgr/online/luna_val/`.

## 6. Weak agent + strong guard: gpt-5-nano agent, gpt-6-luna user and guards, train split (2026-10-20)

STEP5_PLACEHOLDER

---

## Overall summary: pass^1 by configuration and experiment

| experiment (split; agent / guards) | domain | none | Direct | ShieldAgent | TGR |
|---|---|---|---|---|---|
| P6 (test; nano / nano) | airline | 0.300 | 0.267 | 0.250 | – |
| P6 (test; nano / nano) | retail | 0.348 | 0.391 | 0.145 | – |
| Phase 1 + 2 (train; luna / luna), TGR it4 | airline | 0.533 | 0.467 | 0.383 | 0.533 |
| Phase 1 + 2 (train; luna / luna), TGR it4 | retail | 0.761 | 0.681 | 0.362 | 0.667 |
| Phase 2 (train; luna / luna), TGR frozen | airline | 0.533 | 0.467 | 0.383 | 0.500 |
| Phase 2 (train; luna / luna), TGR frozen | retail | 0.761 | 0.681 | 0.362 | 0.710 |
| Validation (val; luna / luna), TGR frozen | airline | 0.633 | 0.567 | 0.400 | 0.633 |
| Validation (val; luna / luna), TGR frozen | retail | 0.667 | 0.609 | 0.362 | 0.710 |
STEP5_SUMMARY_ROWS

**Total spend to date** (list price): P6 ≈ $22.2; Phase 0 ≈ $3.5; Phase 1 ≈ $11.9; scorer v2 $0; Phase 2 ≈ $13.5
(incl. iteration 5); validation $7.83; step 5 STEP5_COST (incl. its $0.50 pilot).
