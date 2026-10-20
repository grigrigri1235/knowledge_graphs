# Phase 1 report: ShieldAgent baselines with gpt-6-luna (train split)

Date 2026-10-20. Plan: `plan.md`. Run log: `phase1_log.md`. Data: `output/tgr/aspm_runs/luna-dev/<domain>/v1/` (P1
rebuild) and `output/tgr/online/luna_train/<domain>/<guard>/{episodes,gold}.jsonl`, `metrics.json` (P6 metrics, unchanged
script), `metrics_tgr.json` (additions). Recompute with `python scripts/tgr/metrics.py luna_train` (no LLM calls).

**Setup.**
- **Model:** gpt-6-luna in every role: rule building, guard, agent and user simulator. Profile `luna-dev`; agent and
  user use the Responses API with effort `medium` (decisions M1–M6, `p0_report.md`). No grok-4.7 call was made.
- **Rule-building input:** the policy without its Domain Basic section (`exp_core/policy_filter.py`; limitation L1,
  `known_limitations.md`). The agent and the Direct guard see the full wiki.
- **P1 rebuild:** the frozen `repro_pipeline` (tag `repro-p1-v1`), run through `exp_core/run_p1.py` with the same
  parameters as the gpt-5-nano P1. No rule was edited.
- **Configurations:** (a) no shield; (b) Direct; (c) ShieldAgent Stage A (θ = 1, ε = 0.1, auxiliary calls `low`,
  planner `medium`, cap 3, 30 executed steps). Guard code and settings are the same as in P6; only the model and the
  ASPM differ.
- **Tasks:** the TRAIN split of `splits.json` (airline 20 tasks, retail 46), 3 trials each, 594 conversations.
- **Not comparable with P6 without care.** P6 ran on the TEST split with gpt-5-nano. The P6 columns below are context,
  not a paired comparison (§9).

## 1. P1 rebuild with gpt-6-luna
| | airline luna | airline nano (P6) | retail luna | retail nano (P6) |
|---|---|---|---|---|
| policy sections / blocks (E1) | 5 / 52 | 6 / 43 | 7 / 50 | 8 / 34 |
| rules after E2 (dropped) | 79 (0) | 105 (0) | 82 (0) | 74 (9) |
| final rules / predicates | **57** / 105 | 58 / 103 | **57** / 73 | 43 / 56 |
| rules with temporal operators / physical rules | 55 / 10 | 38 / 23 | 52 / 6 | 26 / 19 |
| format repairs attempted / failed | 11 / 0 | 105 / 23 | 28 / 1 | 45 / 17 |
| action predicates / distinct circuits / largest circuit | 49 / 31 / 16 | 34 / 27 / 26 | 36 / 26 / 27 | 15 / 12 / 5 |
| loader check | success | success | success | success |
| wall time (Alg. 2) | 6.3 h | 1.0 h | 6.0 h | 1.0 h |
| cost (list price) | $0.32 | – | $0.34 | – |

The counts are in a sane range, and luna needs far fewer format repairs. One fewer section per domain is the removed
Domain Basic section. Retail luna has 3.6× nano's action predicates, and its largest circuit holds 27 predicates
(collapse flag set). The long Alg. 2 wall time is partly CPU contention: a stuck diagnostic process from another
session (`p1_trace.py`) used the VM's only CPU for the whole of Phase 1 (§8).

## 2. Task success (pass^k; bootstrap 95 % CIs over tasks, 10k resamples)
| domain | configuration | pass^1 | 95 % CI | pass^3 | 95 % CI | Δ pass^1 vs no shield (paired) | Δ pass^1 vs Direct (paired) |
|---|---|---|---|---|---|---|---|
| airline | no shield | **0.533** | 0.350–0.717 | 0.350 | 0.150–0.550 | – | +0.067 [−0.033, +0.167] |
| airline | Direct | 0.467 | 0.283–0.650 | 0.350 | 0.150–0.550 | −0.067 [−0.167, +0.033] | – |
| airline | ShieldAgent | 0.383 | 0.183–0.600 | 0.350 | 0.150–0.550 | −0.150 [−0.367, +0.067] | −0.083 [−0.267, +0.083] |
| retail | no shield | **0.761** | 0.667–0.855 | 0.565 | 0.413–0.717 | – | +0.080 [0.000, +0.167] |
| retail | Direct | 0.681 | 0.580–0.783 | 0.457 | 0.326–0.587 | −0.080 [−0.167, 0.000] | – |
| retail | ShieldAgent | **0.362** | 0.239–0.493 | 0.283 | 0.152–0.413 | **−0.399 [−0.522, −0.275]** | **−0.319 [−0.457, −0.181]** |

- The luna agent alone is strong (0.53 / 0.76).
- In retail, ShieldAgent costs 40 points of pass^1 against no shield and 32 points against Direct; both CIs exclude 0.
- Direct costs about 7–8 points in both domains. In retail the CI's upper end is 0.
- In airline, no difference is detectable (20 tasks, wide CIs).
- Step limit: 1 conversation hit the 30-executed-step limit (airline, no shield), against 8–27 per configuration in P6.

## 3. Blocks, cap overrides and the response to a block
| | blocks / conversation | conversations with ≥ 1 block | max blocks | cap overrides | blocks on read tools / respond / write tools / transfer | guard checks / conversation |
|---|---|---|---|---|---|---|
| airline Direct | 1.10 | 36/60 | 4 | 2 | 8 / 40 / 4 / 14 | 11.3 |
| airline ShieldAgent | 3.37 | 57/60 | 11 | 12 | **194** / 0 / 5 / 3 | 7.8 |
| retail Direct | 1.10 | 91/138 | 7 | 1 | 5 / 128 / 14 / 5 | 12.8 |
| retail ShieldAgent | 5.93 | **138/138** | 14 | 47 | 22 / **643** / 152 / 2 | 18.0 |

**Next attempt after a block** (`scripts/tgr/metrics.py`, same definition as P6 §3):

| | identical call repeated | reply to the user | other action |
|---|---|---|---|
| airline Direct | 2 % | 73 % | 26 % |
| airline ShieldAgent | **42 %** | 30 % | 28 % |
| retail Direct | 0 % | 84 % | 16 % |
| retail ShieldAgent | 2 % | 82 % | 16 % |

- In airline, luna repeats a blocked call about as often as nano did (42 % vs 35 %). Most of these are reads that
  rule 2 blocks (§6).
- In retail, luna almost never repeats a blocked call (2 % vs nano's 53 %). It writes a new reply or **hands the user
  to a human**: the last executed action is `transfer_to_human_agents` in 79/138 ShieldAgent conversations, against
  15/138 with no shield (airline 55/60 vs 40/60). The failure mode moves from "delay until the cap" (P6) to "give up
  and transfer". Cap overrides fall from 301 (P6 retail) to 47.
- **ε:** 6 of 2,488 retail ShieldAgent checks had a margin in (−0.1, 0), so ε = 0.1 allowed actions that ε = 0 would
  have blocked. P6 had none. Airline had none.
- **Trace store:** for every check, the trace length before the step equals the number of executed steps
  (0 mismatches in 2,953 checks).

## 4. Policy compliance (D9 gold scorer; scoring only)
| | successful episodes | success and no gold violation | success and no API-accepted violation | violating write calls / episode | violated gold rules |
|---|---|---|---|---|---|
| airline no shield | 32 | 32/32 (1.00) | 1.00 | **0.00** | – |
| airline Direct | 28 | 27/28 (0.96) | 0.96 | 0.02 | AIR-R022 ×1 |
| airline ShieldAgent | 23 | 23/23 (1.00) | 1.00 | 0.00 | – |
| retail no shield | 105 | 102/105 (0.97) | 1.00 | **0.04** | RET-R013 ×3, RET-R031 ×2, RET-R014 ×1 |
| retail Direct | 94 | 94/94 (1.00) | 1.00 | 0.00 | – |
| retail ShieldAgent | 50 | 50/50 (1.00) | 1.00 | 0.01 | RET-R013 ×1 |

- **The unguarded luna agent almost never makes a write call that the scorer flags as a violation:** 0 in 60 airline
  conversations and 6 in 138 retail ones. nano made 0.78 / 0.42 per conversation in P6.
- On train, a guard therefore has almost no scorer-visible violation to prevent.
- The D9 limits still hold (`p6_report.md` §4). Cancellation eligibility (AIR-R042), explicit confirmation and
  unrequested actions are not scored, so these numbers are upper bounds. No manual audit was done in Phase 1.
- One Direct conversation (airline) executed an API-accepted violation, AIR-R022, in a successful episode.

## 5. Block precision proxy
| | blocks | scorable blocks (write calls) | precision, all blocks | precision, scorable blocks |
|---|---|---|---|---|
| airline Direct | 66 | 4 | 0.00 | 0.00 (0/4) |
| airline ShieldAgent | 202 | 5 | 0.00 | 0.00 (0/5) |
| retail Direct | 152 | 14 | 0.01 | 0.07 (1/14) |
| retail ShieldAgent | 819 | 152 | 0.00 | **0.00 (0/152)** |

Under the gold scorer, almost every block by either guard is a false positive. Direct's small denominators (4, 14)
make its precision uninformative here. ShieldAgent's 0 of 152 blocked write calls in retail is a clear result.
Because gold recall is limited (§4), true precision may be slightly higher for both guards.

## 6. Rules most often responsible for ShieldAgent blocks
| airline rule | block citations | content | defect class (AGENTS.md §7) |
|---|---|---|---|
| 2 | 196 of 202 blocks | `ALWAYS (make_tool_call IMPLIES (NOT make_tool_call UNTIL tool_call_completes))`: "no tool call until the current one completes" | 2, over-general timing rule (the same kind as nano airline rule 4); it blocks ordinary reads (`get_user_details` 122, `get_reservation_details` 51) |
| 25 | 5 | flight change only after the agent "consulted the applicable flight-change rules" | 2/4, unverifiable meta-condition |
| 35 | 1 | transfer only if the request is outside scope | 4, predicate value |

| retail rule | block citations | content | defect class |
|---|---|---|---|
| 25 | 353 | no procedural guidance unless grounded in user or tool input | 2/4: blocks ordinary replies, for example "please provide your email … so I can locate your order" |
| 26 | 275 | the same, for procedural steps about the user's own orders | 2/4 |
| 24 | 137 | no factual information unless grounded in user or tool input | 4, predicate value |
| 27 | 87 | modify items only after an action "reviewing the pending-order record" | 3/4: an action predicate as a precondition, rarely grounded |
| 45, 52 | 86, 48 | a price difference needs a payment method (modify / exchange) | 4: blocked writes, none confirmed by gold |
| 15 | 29 | no tool call while another is in progress | 2, timing rule |
| 13 | 16 | remind the customer to confirm all items before modifying | obligation turned into a precondition (the only one among the top rules) |

The nano P1 defects "no tool call after the first order tool call" (retail rule 32) and the respond/tool-call mutual
exclusion (rules 3/4/29) do not recur. The once-only sentence that produced rule 32 is in the removed Domain Basic
section, so this is confounded with limitation L1. Grounding rules on replies took their place as the main source of
blocks.

**Direct's most cited policy statements** (first violated statement per block):
- airline: "do not provide information … not provided by the user or available tools" (26), "transfer … if and only
  if" (20), obtain user id / trip details first (8);
- retail: "the user must provide a payment method for the price difference" (34), "do not make up information"
  (41), "modify items can only be called once" (18), "transfer … if and only if" (15), explicit confirmation (9).

## 7. Cost and latency (means per conversation; list price, as in P6)
| | agent | user | guard | **total** | wall time | guard latency / check | guard cost / check | agent calls |
|---|---|---|---|---|---|---|---|---|
| airline no shield | $0.0053 | $0.0007 | – | $0.0060 | 332 s | – | – | 10.0 |
| airline Direct | $0.0063 | $0.0007 | $0.0055 | $0.0125 | 249 s | 5.9 s | $0.0005 | 11.3 |
| airline ShieldAgent | $0.0033 | $0.0004 | $0.0055 | $0.0092 | 422 s | 25.8 s | $0.0007 | 7.8 |
| retail no shield | $0.0062 | $0.0006 | – | $0.0068 | 326 s | – | – | 12.2 |
| retail Direct | $0.0069 | $0.0006 | $0.0054 | $0.0128 | 382 s | 7.3 s | $0.0004 | 12.8 |
| retail ShieldAgent | $0.0109 | $0.0006 | $0.0383 | **$0.0499** | 848 s | 31.7 s | $0.0021 | 18.0 |

- **Totals (list price):** no shield $1.30, Direct $2.52, ShieldAgent $7.43; online $11.25 including the failed
  attempt. Add $0.67 for the P1 rebuild: **Phase 1 ≈ $11.9**, against the Phase 0 estimate of ≈ $16 (≈ $15 online
  + ≈ $1 P1). With cached-input billing for agent and user, the online part would be ≈ $8.2.
- Unlike P6, the user cost is metered per call (`exp_core/run_online.py`).
- Airline ShieldAgent is cheaper than no shield because its conversations end early: 7.8 agent calls against 10.0,
  mostly ending in a transfer (§3).
- In retail, ShieldAgent costs about 4× Direct per conversation and is about 2.2× slower.
- Absolute times include CPU contention (§8).

## 8. Failures and operations
- **Crashes:** none in the harness or the guards. One conversation failed: retail / no shield / task 52 trial 1. Azure's
  content filter rejected the agent's prompt (HTTP 400 `content_filter`, "sexual: high"), a false positive like P6's
  O7. On 2026-10-20 that conversation alone was resumed with the same configuration; it finished with reward 1 in 84 s.
  The file before the resume is kept as `episodes.before_resume.jsonl`; metrics use the latest record per
  (task, trial). All 594 conversations now have a clean result, with no missing or duplicate units.
- **Disconnect:** the session that launched Phase 1 ended without a report (the user's computer was closed). The jobs
  ran under `setsid nohup` and all logged DONE (`output/tgr/phase1/logs/`). Timeline: P1 rebuild 2026-10-19
  09:25–21:50; online runs 21:54 to 02:11 on 2026-10-20 (retail ShieldAgent 4.25 h).
- **CPU contention:** a diagnostic process from an earlier session (`scripts/reproduction/p1_trace.py`, started
  2026-10-18) was stuck and used the only CPU for 33 h, including all of Phase 1. It was stopped on 2026-10-20. Wall
  times and latencies in this report are therefore inflated. Costs and decisions are not affected.

## 9. Context: gpt-5-nano P6 numbers (**different split: train vs test, not directly comparable**)
| | luna pass^1 (train) | nano pass^1 (test) | luna blocks / conv. | nano blocks / conv. | luna prec. (scorable) | nano prec. (scorable) | luna repeat | nano repeat | luna $ / conv. | nano $ / conv.* |
|---|---|---|---|---|---|---|---|---|---|---|
| airline no shield | 0.533 | 0.300 | – | – | – | – | – | – | 0.006 | 0.015 |
| airline Direct | 0.467 | 0.267 | 1.10 | 1.30 | 0.00 (n=4) | 0.52 | 2 % | 1 % | 0.013 | 0.029 |
| airline ShieldAgent | 0.383 | 0.250 | 3.37 | 4.47 | 0.00 (n=5) | 0.13 | 42 % | 35 % | 0.009 | 0.055 |
| retail no shield | 0.761 | 0.348 | – | – | – | – | – | – | 0.007 | 0.013 |
| retail Direct | 0.681 | 0.391 | 1.10 | 0.54 | 0.07 (n=14) | 0.59 | 0 % | 0 % | 0.013 | 0.024 |
| retail ShieldAgent | 0.362 | 0.145 | 5.93 | 10.45 | 0.00 (n=152) | 0.24 | 2 % | 53 % | 0.050 | 0.071 |

\* The nano user cost is under-counted (`p6_report.md` §7 note).

The models, splits and rule sets all differ, so only qualitative patterns carry over: the ranking (no shield ≥ Direct
> ShieldAgent) and the large retail ShieldAgent loss hold in both.

## 10. User-simulator check (heuristic only)
`p6_user_sim_check.py`'s agent-like-wording heuristic flags 12 of 594 conversations (0–5 per configuration). For the
nano user the same heuristic flagged 3 conversations where a manual read found 6 in 20. No manual read was done for
luna, so the role-swap rate is not established. The heuristic suggests it is lower than nano's.

## 11. Findings
1. **With a strong agent, a guard is mostly a cost.** The unguarded luna agent makes almost no scorer-visible
   violations on train (0.00 / 0.04 per conversation), so both guards' blocks are almost all false positives under
   the gold scorer, and both lower pass^1.
2. **ShieldAgent (luna rules) loses 40 points of pass^1 in retail** (−0.32 vs Direct, CI excludes 0). It blocks in
   every retail conversation, mainly replies (643 blocks) and write calls (152 blocks, none gold-confirmed).
3. **Defect classes 2 and 4 persist with a stronger model.** Over-general timing rules (airline rule 2: 196 of 202
   blocks) and grounding rules judged on ordinary replies (retail 24–26) are the main sources of blocks. A better
   rule-building model removes the nano-specific defects (rule 32, the mutual exclusion) but writes other non-tool
   rules in their place. This supports tool-grounded, restriction-only rules (Phase 2, components A and B).
4. **The response to non-actionable feedback changes with the model.** luna rarely retries a blocked retail call
   (2 %); it replies or transfers to a human instead (transfers 15 → 79 of 138). The cap is reached less often, but
   tasks are abandoned. This supports component C (actionable feedback).
5. **Direct is the baseline to beat on train as well.** It costs 7–8 points of pass^1 at about $0.0055 guard cost per
   conversation; ShieldAgent costs 15–40 points at $0.0055–0.038.
6. **Caveats:** train split only (the same tasks that Phase 2 will develop on); D9 compliance numbers are upper
   bounds; 20 airline tasks give wide CIs; no manual audit or user-simulator read in this phase.
