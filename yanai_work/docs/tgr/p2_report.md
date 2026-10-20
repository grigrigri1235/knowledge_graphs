# Phase 2 report: TGR (tool-grounded restriction rules) on the train split, gpt-6-luna

Date 2026-10-20.
- Design: `phase2_design.md`. Iterations: `phase2_log.md`.
- Final rule sets: `tgr_rules/<domain>/{full,nob}/`; tables in the appendix `p2_rules_appendix.md`.
- Scorer: gold v1 and gold v2 (`scorer_v2_report.md`).
- Data: `output/tgr/online/luna_train/<domain>/<guard>/`, next to the Phase 1 baselines.
- Recompute: `python scripts/tgr/metrics.py luna_train` and `python scripts/reproduction/gold_compare.py ../../tgr/online/luna_train`
  (no LLM calls).

**Setup.**
- gpt-6-luna in every role; no grok-4.7 call.
- Train split: airline 20 tasks, retail 46; **3 trials**; the same harness as Phase 1 and P6 (cap 3, 30 executed
  steps).
- Configurations:
  - `tgr`: A tool grounding + B restriction-only rules + C actionable feedback;
  - `tgr_nob`: A + C, rules written as general LTLf (not B);
  - `tgr_noc`: A + B, with ShieldAgent's explanation feedback (not C);
  - Phase 1 baselines: none, Direct, ShieldAgent (luna rules).
- Eq. 4–5 with θ = 1, ε = 0.1 in every TGR configuration.
- **Development and this measurement use the same train tasks**, so these numbers are optimistic for TGR. The
  unbiased comparison is Phase 3b (test split).

## 1. Final rule sets
| | airline (A+B) | retail (A+B) | airline (not B) | retail (not B) |
|---|---|---|---|---|
| policy sentences | 46 | 38 | 46 | 38 |
| rules / predicates | 35 / 40 | 61 / 26 | 20 / 45 | 23 / 27 |
| actions with rules | 7 (the 6 write tools + transfer) | 15 (writes, reads, respond, transfer) | 7 | 14 |
| dispositions: rule / exception / fact / not enforceable | 31 / 1 / 7 / 7 | 27 / 0 / 8 / 3 | – | – |
| background facts for the judge | 20 (incl. the current time) | 25 | 29 | 29 |
| repair rounds / invalid dropped / duplicates | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| cost (one call, effort high) | $0.011 | $0.010 | $0.009 | $0.007 |

- **Covered as restrictions:**
  - explicit confirmation of listed details before every write;
  - status preconditions: pending / delivered; no flown segment;
  - cancellation eligibility, with all four exceptions folded in as OR (airline rule 30);
  - the basic-economy restriction with its cabin-change exception folded in (airline rule 21);
  - payment-method limits, baggage allowance, passenger count, the once-only item modification, the gift-card
    balance check;
  - compensation conditions; authentication before reads and before disclosing user information.
- **Not enforceable** (with reasons in the appendix):
  - general message quality (grounding, subjectivity) and refusal of requests;
  - one tool call per turn / no text with a call;
  - the cabin price difference (no tool exposes it);
  - "cannot add insurance after booking" (no tool does this).
- The full rule and disposition tables are in `p2_rules_appendix.md`.

## 2. Task success (pass^k; bootstrap 95 % CIs over tasks, 10k resamples; Δ paired by task)
| domain | configuration | pass^1 | 95 % CI | pass^3 | Δ pass^1 vs no shield | **Δ pass^1 vs Direct** |
|---|---|---|---|---|---|---|
| airline | no shield | 0.533 | 0.35–0.72 | 0.350 | – | +0.067 [−0.033, +0.167] |
| airline | Direct | 0.467 | 0.28–0.65 | 0.350 | −0.067 [−0.167, +0.033] | – |
| airline | ShieldAgent | 0.383 | 0.18–0.60 | 0.350 | −0.150 [−0.367, +0.067] | −0.083 [−0.267, +0.083] |
| airline | **TGR** | **0.533** | 0.33–0.73 | **0.450** | +0.000 [−0.133, +0.117] | **+0.067 [−0.050, +0.200]** |
| airline | TGR − B | 0.550 | 0.35–0.75 | 0.450 | +0.017 [−0.117, +0.167] | +0.083 [−0.067, +0.233] |
| airline | TGR − C | 0.533 | 0.33–0.73 | 0.450 | +0.000 [−0.150, +0.133] | +0.067 [−0.050, +0.200] |
| retail | no shield | 0.761 | 0.67–0.86 | 0.565 | – | +0.080 [0.000, +0.167] |
| retail | Direct | 0.681 | 0.58–0.78 | 0.457 | −0.080 [−0.167, 0.000] | – |
| retail | ShieldAgent | 0.362 | 0.24–0.49 | 0.283 | −0.399 [−0.522, −0.275] | −0.319 [−0.457, −0.181] |
| retail | **TGR** | **0.667** | 0.56–0.78 | **0.478** | **−0.094 [−0.181, −0.007]** | **−0.014 [−0.101, +0.072]** |
| retail | TGR − B | 0.674 | 0.57–0.78 | 0.457 | −0.087 [−0.167, −0.007] | −0.007 [−0.087, +0.080] |
| retail | TGR − C | 0.652 | 0.55–0.75 | 0.370 | −0.109 [−0.188, −0.029] | −0.029 [−0.109, +0.051] |

- **Airline:** TGR matches no shield and is +0.067 above Direct (CI includes 0). Its pass^3 (0.45) is the highest of
  all configurations.
- **Retail:** TGR is level with Direct (−0.014, CI includes 0) and 0.094 below no shield (CI excludes 0). The single
  development trial of iteration 4 (0.761) was optimistic; across 3 trials TGR scores 0.674 / 0.674 / 0.652.
- **Against ShieldAgent (Phase 1, same rules model):** retail +0.31 pass^1, airline +0.15.

## 3. Blocks, cap overrides, transfers and the response to a block
| | blocks / conv. | conv. with ≥ 1 block | max | cap overrides | blocked: read / respond / write / transfer | next attempt after a block: repeat / reply / other | conv. ending in a transfer |
|---|---|---|---|---|---|---|---|
| airline Direct | 1.10 | 36/60 | 4 | 2 | 8 / 40 / 4 / 14 | 2 % / 73 % / 26 % | 44/60 |
| airline ShieldAgent | 3.37 | 57/60 | 11 | 12 | 194 / 0 / 5 / 3 | 42 % / 30 % / 28 % | 55/60 |
| airline **TGR** | **0.38** | 18/60 | 5 | **0** | 0 / 0 / 16 / 7 | **0 %** / 74 % / 26 % | **39/60** (no shield 40) |
| airline TGR − B | 0.50 | 25/60 | 3 | 0 | 0 / 0 / 22 / 8 | 0 % / 73 % / 27 % | 45/60 |
| airline TGR − C | 0.32 | 12/60 | 3 | 0 | 0 / 0 / 14 / 5 | 5 % / 37 % / 58 % | 40/60 |
| retail Direct | 1.10 | 91/138 | 7 | 1 | 5 / 128 / 14 / 5 | 0 % / 84 % / 16 % | 30/138 |
| retail ShieldAgent | 5.93 | 138/138 | 14 | 47 | 22 / 643 / 152 / 2 | 2 % / 82 % / 16 % | 79/138 |
| retail **TGR** | **0.97** | 81/138 | 4 | **0** | 66 / 4 / 64 / 0 | 4 % / 58 % / 37 % | **29/138** (no shield 15) |
| retail TGR − B | 1.99 | 130/138 | 8 | 1 | 200 / 10 / 61 / 3 | 4 % / 69 % / 27 % | 23/138 |
| retail TGR − C | 1.26 | 96/138 | 6 | 0 | 90 / 10 / 71 / 3 | 2 % / 66 % / 32 % | 24/138 |

- TGR blocks almost only write calls and transfers (airline), and writes plus the order look-up precondition
  (retail). There are no cap overrides, and the agent almost never repeats a blocked call.
- **Transfers:**
  - airline 39 vs ShieldAgent's 55 and Direct's 44;
  - retail 29 vs ShieldAgent's 79, about the same as Direct (30), but above no shield (15).
- In retail, most TGR blocks are on reads: 66 `get_order_details` blocks under "the order belongs to the
  authenticated user" (§5).
- **Without B,** the general LTLf rules attach to many tools at once. Blocks double in retail, including 109 blocks
  on the user look-up `find_user_id_by_name_zip`.

## 4. Policy compliance and block precision (gold scorer, scoring only)
| | violating executed calls / conv. v1 → **v2** | success and no violation v2 | scorable write blocks | **block precision v2** (v1) | violations caught by blocks (v2) |
|---|---|---|---|---|---|
| airline no shield | 0.000 → 0.017 | 32/32 | – | – | – |
| airline Direct | 0.017 → 0.050 | 27/28 | 4 | 0.00 (0.00) | 0 |
| airline **TGR** | 0.000 → 0.083 | 31/32 | 16 | **0.12** (0.06) | 2 |
| airline TGR − B | 0.017 → 0.017 | 32/33 | 22 | 0.00 (0.00) | 0 |
| airline TGR − C | 0.017 → 0.033 | 32/32 | 14 | 0.29 (0.21) | 4 |
| retail no shield | 0.043 → 0.051 | 102/105 | – | – | – |
| retail Direct | 0.000 → 0.000 | 94/94 | 14 | **0.21** (0.07) | 3 |
| retail **TGR** | 0.007 → 0.029 | 88/92 | 64 | **0.03** (0.02) | 2 |
| retail TGR − B | 0.000 → 0.029 | 90/93 | 61 | 0.07 (0.05) | 4 |
| retail TGR − C | 0.000 → 0.036 | 87/90 | 71 | 0.08 (0.04) | 6 |

- The luna agent is almost compliant on its own (no shield: 0.017 / 0.051 violating calls per conversation under v2).
  No guard has many real violations to catch, and "violations caught" stays at 0–6 blocks per configuration.
- **TGR's executed v2 violations come from TGR's own blocks** (airline 5, retail 4; all confirmation, AIR-R002 /
  RET-R005):
  - a block asks for a missing detail (the payment or refund method; the exact change);
  - the user supplies it ("Use my Mastercard ending in 1531.");
  - the agent executes without a further "yes".

  gold v2 reads this as an unconfirmed final detail. TGR's judge accepts the user's own explicit choice. This is a
  policy-reading difference; neither side is changed (`phase2_log.md`, iteration 4).

**Manual audit of TGR blocks** (final `tgr` runs; policy text versus judge values):

| set | blocks read | supported by the policy text | judge value wrong | rule or predicate stricter than the policy |
|---|---|---|---|---|
| airline, all write blocks | 16 | 4 (change not listed / not confirmed; baggage over the free allowance) | 12: 7 × "agent asked for the payment method" false although the agent proposed one and the user agreed; 5 × "no segment flown" unknown although the dates are after the current time | 0 |
| retail, sample of write blocks | 14 of 64 | 6 (address not listed; no "all items" reminder; confirmation covered fewer items) | 2 (gift-card balance applied to a refund; a reminder not recognised) | 6 × "the user provided the payment method" when the agent proposed it and the user agreed |
| retail, `get_order_details` blocks | 4 of 66 | 0 | 1 (the order was in the user's order list) | 3: ownership proof before a read is not required by the policy text (it requires authentication) |

TGR's blocks are more often justified by the policy text than the gold-v2 precision suggests: airline 4/16, retail
writes 6/14. But many are **wrong predicate values or over-literal predicates**, not wrong rules.

## 5. Cost and latency (means per conversation; list price)
| | agent + user | guard | **total** | guard checks with an LLM call | guard latency / check |
|---|---|---|---|---|---|
| airline Direct | $0.0069 | $0.0055 | $0.0125 | every step | 5.9 s |
| airline ShieldAgent | $0.0037 | $0.0055 | $0.0092 | every step | 25.8 s |
| airline **TGR** | $0.0077 | **$0.0013** | $0.0090 | only steps of the 7 restricted actions | 1.1 s (mean over all checks) |
| retail Direct | $0.0075 | $0.0054 | $0.0128 | every step | 7.3 s |
| retail ShieldAgent | $0.0115 | $0.0383 | $0.0499 | every step | 31.7 s |
| retail **TGR** | $0.0079 | **$0.0057** | $0.0136 | 15 of 17 actions | 4.4 s |

- **Phase 2 spend:** $0.09 for the rule builds, $3.62 for development runs (264 conversations), $7.50 for the final
  runs (594 conversations): **≈ $11.2** in total. The first, aborted effort-high build may add a little unrecorded
  cost (timed-out requests).
- Wall-clock comparisons with Phase 1 are not valid: Phase 1 ran with a stuck process using the only CPU
  (`p1_report.md` §8).

## 6. Success criteria (train, gpt-6-luna)
| criterion | airline | retail |
|---|---|---|
| pass^1 above Direct | **yes**, +0.067 (CI includes 0) | **no**, −0.014 (CI includes 0) |
| as close as possible to no shield | equal (+0.000) | −0.094 (CI excludes 0) |
| block precision above Direct (gold v2) | yes, nominally: 0.12 vs 0.00 (n = 16 vs 4) | **no**: 0.03 vs 0.21 |
| violations caught (gold v2) | 2 (Direct 0) | 2 (Direct 3) |
| fewer transfers than ShieldAgent | **yes**: 39 vs 55 | **yes**: 29 vs 79 |

## 7. Ablations (train, gpt-6-luna)
- **B (restriction-only rules + dispositions):** no measurable effect on pass^1: airline −0.017, retail −0.007 for
  TGR against TGR − B, all within noise. B halves the blocks in retail (0.97 vs 1.99), keeps rules off the user
  look-up tools, and supplies the coverage check and the fact background.
- **C (actionable feedback):** no measurable effect on pass^1: airline 0.000, retail +0.014. With the luna agent the
  repeat rate is already low without C (2–5 %). C changes what the agent does next: airline replies 74 % vs 37 %,
  "other" actions 26 % vs 58 %. pass^3 in retail is higher with C (0.478 vs 0.370).
- **Caveat:** 3 trials on 20 and 46 tasks cannot resolve effects below about ±0.08.

## 8. Findings
1. **Tool grounding plus restriction rules removed ShieldAgent's main failure modes**: blocks on reads and replies,
   cap overrides, repeat loops and mass transfers. It did so at about 1/4 (airline) to 1/7 (retail) of ShieldAgent's guard cost, and the
   guard costs nothing on steps of unrestricted tools.
2. **TGR does not yet beat Direct on train:** better in airline, level in retail, and in neither case
   significantly. The luna agent leaves little to protect against; each unnecessary block costs some tasks.
3. **The remaining errors are mostly in predicate values, not in the rules.** Three generic causes:
   - (a) over-literal "who said it / who asked" predicates;
   - (b) the judge leaves date-derivable facts unknown, even with the current time;
   - (c) a precondition stricter than the policy text (ownership before a read).

   Under Eq. 5 an unknown blocks (T5), so (b) always blocks.
4. **Rule writing varies between samples.** The two medium-effort samples (it2 and it3) differed in whether
   exceptions were folded in. The final rule sets were built at effort high, one sample each.
5. **The gold scorer and TGR read "confirmation" differently** after a block that asks for a missing detail. This
   produces the few executed v2 violations TGR has.

## 9. Possible next steps (not started; Phase 3 needs approval)
- **Generic judge and rule-writing changes on train** before Phase 3b, if wanted:
  - predicates about having information or a choice, not about who stated it;
  - date and time arithmetic against the background facts in the judge;
  - no preconditions on reads beyond what the policy names.

  Each change would be logged as iteration 5 and followed by new 3-trial train runs.
- **Phase 3b** (grok-4.7, test, once; after approval and a cost estimate): no shield, Direct, ShieldAgent, TGR full.
  The ablations stay on train (done here).

Appendix: `p2_rules_appendix.md` (final rules, per-sentence dispositions, background facts).
