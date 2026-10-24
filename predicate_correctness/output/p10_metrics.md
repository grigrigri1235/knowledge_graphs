# Part 10: metrics of "TGR + tracker"

Written by `scoring/p10_metrics.py` (no LLM call). The partner's metric and gold scorer scripts (copies in `from_shieldagent/scoring/`) ran on our runs and on the partner's baselines through `scoring/p10_eval.py`. Details and checks: `output/p10_metrics.json`.

- **TGR + tracker**: our new runs (`output/online/<tag>/<domain>/tgr_tracker/`).
- **frozen TGR, Direct, no guard**: the partner's saved runs with the same tasks, trials and models (`from_shieldagent/runs/`). They ran earlier, with no sampling seed.
- pass^1: the mean over tasks of the share of successful trials, with a 95 % bootstrap CI over tasks. Paired Δ: the per-task difference, with a 95 % bootstrap CI over tasks (10,000 resamples, seed 0, the partner's method). A CI that contains 0 means no clear difference.
- Violations use gold v2 (scoring only). *attempted* = executed violating write calls + blocked violating write attempts; *blocked* = the second part; *executed* = the first part.
- Block precision (gold v2): the share of blocked write calls that break a gold rule. Blocks of messages and reads cannot be scored.

## Main results

- **train, luna-dev:** pass^1 TGR + tracker − frozen TGR = +0.076 [+0.03, +0.13] over both domains (66 tasks); − Direct = +0.106 [+0.04, +0.17]. Blocks per conversation (ours vs frozen TGR): airline 0.20 vs 0.20, retail 0.33 vs 0.39. Executed gold v2 violations: airline 3 vs 3, retail 0 vs 2.
- **train, nano-agent-luna:** pass^1 TGR + tracker − frozen TGR = +0.020 [-0.05, +0.09] over both domains (66 tasks); − Direct = +0.015 [-0.06, +0.09]. Blocks per conversation (ours vs frozen TGR): airline 1.10 vs 1.52, retail 2.36 vs 2.72. Executed gold v2 violations: airline 3 vs 6, retail 1 vs 28.
- **val, luna-dev:** pass^1 TGR + tracker − frozen TGR = -0.020 [-0.10, +0.05] over both domains (33 tasks); − Direct = +0.071 [-0.02, +0.16]. Blocks per conversation (ours vs frozen TGR): airline 0.07 vs 0.13, retail 0.32 vs 0.42. Executed gold v2 violations: airline 1 vs 3, retail 4 vs 4.
- **Per step:** in 5,774 guard checks with a judge call, the tracker's values changed the decision 77 times: 68 blocks removed, 9 added. Gold v2: removed blocks 18 without a violation, 0 with one, 50 not scorable (messages and reads); added blocks 9 with a violation, 0 without.
- **Tracker:** judge skipped 0 times, values replaced 7,750, changed 307, tracker unknowns 2 (judge's value kept), lookup errors 0, replay mismatches 0.
- Only CIs that exclude 0 show a clear difference. With 9 comparisons per column, one such CI can appear by chance.

## 1. Paired Δ pass^1

| experiment | domain | tasks | TGR + tracker − frozen TGR | TGR + tracker − Direct | frozen TGR − Direct | TGR + tracker − no guard |
|---|---|---|---|---|---|---|
| train, luna-dev | airline | 20 | +0.050 [-0.02, +0.12] | +0.083 [-0.03, +0.22] | +0.033 [-0.08, +0.15] | +0.017 [-0.05, +0.10] |
| train, luna-dev | retail | 46 | +0.087 [+0.02, +0.16] | +0.116 [+0.04, +0.20] | +0.029 [-0.06, +0.12] | +0.036 [-0.03, +0.10] |
| train, luna-dev | both | 66 | +0.076 [+0.03, +0.13] | +0.106 [+0.04, +0.17] | +0.030 [-0.04, +0.11] | +0.030 [-0.02, +0.09] |
| train, nano-agent-luna | airline | 20 | +0.050 [-0.03, +0.15] | +0.067 [-0.02, +0.17] | +0.017 [-0.08, +0.12] | +0.033 [-0.13, +0.17] |
| train, nano-agent-luna | retail | 46 | +0.007 [-0.07, +0.09] | -0.007 [-0.10, +0.09] | -0.014 [-0.12, +0.09] | +0.022 [-0.04, +0.09] |
| train, nano-agent-luna | both | 66 | +0.020 [-0.05, +0.09] | +0.015 [-0.06, +0.09] | -0.005 [-0.08, +0.07] | +0.025 [-0.04, +0.09] |
| val, luna-dev | airline | 10 | +0.033 [-0.07, +0.13] | +0.100 [-0.07, +0.27] | +0.067 [-0.17, +0.33] | +0.033 [-0.07, +0.13] |
| val, luna-dev | retail | 23 | -0.043 [-0.14, +0.04] | +0.058 [-0.04, +0.17] | +0.101 [+0.00, +0.22] | -0.000 [-0.10, +0.10] |
| val, luna-dev | both | 33 | -0.020 [-0.10, +0.05] | +0.071 [-0.02, +0.16] | +0.091 [-0.01, +0.20] | +0.010 [-0.07, +0.08] |

## 2. All metrics per guard

| experiment | domain | guard | conv. | pass^1 [95% CI] | pass^3 | blocks/conv. | cap overrides | block precision v2 (n) | violations attempted / blocked / executed (v2) | transfers | $ / conv. (guard $) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| train, luna-dev | airline | no guard | 60 | 0.533 [0.35, 0.72] | 0.350 | 0.00 | 0 | – (0) | 1 / 0 / 1 | 40 | 0.0060 (0.0000) |
| train, luna-dev | airline | Direct | 60 | 0.467 [0.28, 0.65] | 0.350 | 1.10 | 2 | 0.00 (4) | 3 / 0 / 3 | 44 | 0.0125 (0.0055) |
| train, luna-dev | airline | frozen TGR | 60 | 0.500 [0.32, 0.68] | 0.300 | 0.20 | 0 | 0.17 (6) | 4 / 1 / 3 | 42 | 0.0097 (0.0035) |
| train, luna-dev | airline | **TGR + tracker** | 60 | 0.550 [0.35, 0.73] | 0.400 | 0.20 | 0 | 0.40 (5) | 5 / 2 / 3 | 40 | 0.0103 (0.0036) |
| train, luna-dev | retail | no guard | 138 | 0.761 [0.67, 0.86] | 0.565 | 0.00 | 0 | – (0) | 7 / 0 / 7 | 15 | 0.0068 (0.0000) |
| train, luna-dev | retail | Direct | 138 | 0.681 [0.58, 0.78] | 0.457 | 1.10 | 1 | 0.21 (14) | 3 / 3 / 0 | 30 | 0.0128 (0.0054) |
| train, luna-dev | retail | frozen TGR | 138 | 0.710 [0.60, 0.81] | 0.565 | 0.39 | 0 | 0.04 (45) | 4 / 2 / 2 | 22 | 0.0125 (0.0052) |
| train, luna-dev | retail | **TGR + tracker** | 138 | 0.797 [0.71, 0.88] | 0.630 | 0.33 | 0 | 0.08 (38) | 3 / 3 / 0 | 16 | 0.0125 (0.0053) |
| train, nano-agent-luna | airline | no guard | 60 | 0.400 [0.23, 0.57] | 0.200 | 0.00 | 0 | – (0) | 50 / 0 / 50 | 26 | 0.0123 (0.0000) |
| train, nano-agent-luna | airline | Direct | 60 | 0.367 [0.18, 0.55] | 0.250 | 11.08 | 102 | 0.34 (96) | 40 / 33 / 7 | 45 | 0.0503 (0.0197) |
| train, nano-agent-luna | airline | frozen TGR | 60 | 0.383 [0.18, 0.58] | 0.300 | 1.52 | 3 | 0.59 (61) | 42 / 36 / 6 | 37 | 0.0240 (0.0079) |
| train, nano-agent-luna | airline | **TGR + tracker** | 60 | 0.433 [0.25, 0.62] | 0.300 | 1.10 | 4 | 0.75 (52) | 42 / 39 / 3 | 35 | 0.0216 (0.0068) |
| train, nano-agent-luna | retail | no guard | 138 | 0.652 [0.55, 0.75] | 0.435 | 0.00 | 0 | – (0) | 39 / 0 / 39 | 24 | 0.0097 (0.0000) |
| train, nano-agent-luna | retail | Direct | 138 | 0.681 [0.57, 0.78] | 0.500 | 6.64 | 104 | 0.26 (68) | 20 / 18 / 2 | 34 | 0.0303 (0.0124) |
| train, nano-agent-luna | retail | frozen TGR | 138 | 0.667 [0.56, 0.78] | 0.457 | 2.72 | 41 | 0.14 (256) | 64 / 36 / 28 | 22 | 0.0239 (0.0097) |
| train, nano-agent-luna | retail | **TGR + tracker** | 138 | 0.674 [0.57, 0.78] | 0.500 | 2.36 | 24 | 0.14 (266) | 37 / 36 / 1 | 20 | 0.0217 (0.0089) |
| val, luna-dev | airline | no guard | 30 | 0.633 [0.37, 0.87] | 0.500 | 0.00 | 0 | – (0) | 2 / 0 / 2 | 21 | 0.0078 (0.0000) |
| val, luna-dev | airline | Direct | 30 | 0.567 [0.27, 0.83] | 0.500 | 0.93 | 0 | 0.00 (5) | 1 / 0 / 1 | 25 | 0.0116 (0.0053) |
| val, luna-dev | airline | frozen TGR | 30 | 0.633 [0.40, 0.87] | 0.400 | 0.13 | 0 | 0.00 (2) | 3 / 0 / 3 | 23 | 0.0116 (0.0041) |
| val, luna-dev | airline | **TGR + tracker** | 30 | 0.667 [0.43, 0.87] | 0.400 | 0.07 | 0 | – (0) | 1 / 0 / 1 | 20 | 0.0115 (0.0041) |
| val, luna-dev | retail | no guard | 69 | 0.667 [0.49, 0.83] | 0.522 | 0.00 | 0 | – (0) | 1 / 0 / 1 | 14 | 0.0069 (0.0000) |
| val, luna-dev | retail | Direct | 69 | 0.609 [0.43, 0.77] | 0.478 | 1.06 | 2 | 0.00 (4) | 2 / 0 / 2 | 18 | 0.0133 (0.0056) |
| val, luna-dev | retail | frozen TGR | 69 | 0.710 [0.54, 0.87] | 0.609 | 0.42 | 0 | 0.08 (26) | 6 / 2 / 4 | 12 | 0.0131 (0.0055) |
| val, luna-dev | retail | **TGR + tracker** | 69 | 0.667 [0.51, 0.83] | 0.478 | 0.32 | 0 | 0.05 (20) | 5 / 1 / 4 | 10 | 0.0125 (0.0053) |

## 3. The tracker inside the guard (our runs)

| experiment | domain | conv. | guard checks | judge calls | judge skipped | values replaced | values changed | tracker unknowns | lookup errors | replay mismatches |
|---|---|---|---|---|---|---|---|---|---|---|
| train, luna-dev | airline | 60 | 637 | 315 | 0 | 204 | 4 | 0 | 0 | 0 |
| train, luna-dev | retail | 138 | 1,754 | 1,744 | 0 | 2,205 | 24 | 0 | 0 | 0 |
| train, nano-agent-luna | airline | 60 | 745 | 487 | 0 | 643 | 68 | 1 | 0 | 0 |
| train, nano-agent-luna | retail | 138 | 2,184 | 2,183 | 0 | 3,477 | 199 | 1 | 0 | 0 |
| val, luna-dev | airline | 30 | 340 | 186 | 0 | 111 | 3 | 0 | 0 | 0 |
| val, luna-dev | retail | 69 | 863 | 859 | 0 | 1,110 | 9 | 0 | 0 | 0 |

## 4. Per step: did the tracker's values change the decision?

For every guard check with a judge call, TGR's decision formula ran again on the same past trace, once with the values the guard used and once with the judge's own values. With the used values it gives the saved decision in every check (see the checks below). *Block removed*: the judge's values would block and the guard allowed. *Block added*: the judge's values would allow and the guard blocked.

| experiment | domain | checks with a judge call | checks where the tracker changed a value | block removed | block added | removed: gold v2 violation / no violation / not scorable | added: gold v2 violation / no violation / not scorable |
|---|---|---|---|---|---|---|---|
| train, luna-dev | airline | 315 | 2 | 0 | 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| train, luna-dev | retail | 1,744 | 24 | 8 | 2 | 0 / 8 / 0 | 2 / 0 / 0 |
| train, nano-agent-luna | airline | 487 | 47 | 1 | 0 | 0 / 1 / 0 | 0 / 0 / 0 |
| train, nano-agent-luna | retail | 2,183 | 174 | 58 | 7 | 0 / 8 / 50 | 7 / 0 / 0 |
| val, luna-dev | airline | 186 | 2 | 1 | 0 | 0 / 1 / 0 | 0 / 0 / 0 |
| val, luna-dev | retail | 859 | 9 | 0 | 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| **all** | | 5,774 | 258 | 68 | 9 | | |

Predicates behind the changed decisions (all experiments):

- block removed: `user_authenticated` 58, `gift_card_balance_covers_price_difference` 8, `origin_destination_and_trip_type_preserved` 1, `pending_flight_update_is_basic_economy` 1, `order_status_checked_pending` 1, `reservation_has_no_used_flight_segments` 1
- block added: `order_status_checked_pending` 8, `order_status_checked_delivered` 1

## 5. Checks

- none and Direct give the same numbers in our tag and in the baseline tag: 24 of 24.
- Baseline numbers against the partner's saved metric files (read only): 72 of 72 entries equal in every common value; 0 values differ (details in the JSON).
- Decision again with the used values = saved decision: 5,774 of 5,774 checks.
- Past trace length = the saved trace_len_before in every check: yes.

## 6. Limits

- 20 / 46 train tasks and 10 / 23 val tasks, 3 trials each: pass^1 changes below about 0.08 are hard to tell from noise.
- The baselines ran earlier (2026-10-20) and sampling has no seed, so part of every gap is noise.
- The guard reads the database; frozen TGR and Direct do not.
- In `output/eval/`, the folder named `tgr` of our tags holds the tgr_tracker runs (the copied scripts know only fixed guard names).
