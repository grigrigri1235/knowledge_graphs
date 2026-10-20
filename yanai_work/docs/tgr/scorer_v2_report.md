# Gold scorer v2: cancellation eligibility and explicit confirmation (scoring only)

Date 2026-10-20. Requested before Phase 2. **Scoring only: gold v2 never feeds a method** (enforced by
NoGoldLeakage, pattern `gold_v2`). The definition, policy text, decision tables, hand check and limitations are in
`policies/gold_v2/README.md`. This document reports the re-scoring.

## What was done
- Added Python checks for the three gold `dialogue` predicates behind the two documented scorer gaps:
  - cancellation eligibility: AIR-R042;
  - explicit user confirmation before write calls: AIR-R002 (airline) and RET-R005 (retail).
  Rules, tool scopes and all other predicates are unchanged gold v1.
- Recorded them as **gold v2** (`policies/gold_v2/checks.py`). v1 is kept and is still the default.
  - `scripts/reproduction/p6_gold_score.py <tag> --gold v2` writes `gold_v2.jsonl` next to v1's `gold.jsonl`.
  - `p6_metrics.py <tag> --gold v2` writes `metrics_gold_v2.json`.
  - `scripts/reproduction/gold_compare.py <tag>` writes `gold_compare.json`.
  - A v1 re-score is byte-identical to the stored `gold.jsonl` in all 12 P6 and Phase 1 result sets.
- Tested on hand-checked calls from P6 and Phase 1 (README "Hand check"; 13 unit tests in
  `tests/gold_v2/test_checks.py`). The hand check found 6 false positives in the drafts: 2 from "No longer needed"
  read as a refusal, and 3 + 1 from "I'm feeling unwell" (once per affected call). All were fixed by generic changes
  to the checks. No false positive remains in the read sets, and recall is still limited.
- Re-scored P6 (`output/repro/p6/full`) and Phase 1 (`output/tgr/online/luna_train`) with both versions. No LLM
  calls, no episodes re-run, and no stored file overwritten: `gold.jsonl` and `metrics.json` are unchanged.

## Violations the v1 scorer missed (executed write calls; latest record per task and trial)

"Missed by v1" = write calls that v1 scores as compliant and v2 flags. New violations by rule can exceed the number of
calls, because one call can break both rules.

**P6 (gpt-5-nano, test split)**

| config | write calls | violating v1 → v2 | **missed by v1** (API-accepted) | conversations with a missed call | new: confirmation / cancel eligibility | of the confirmation misses, on `cancel_reservation` (interpretation scope) |
|---|---|---|---|---|---|---|
| airline no shield | 156 | 47 → 109 | **62** (53) | 21/60 | 56 / 19 | 0 |
| airline Direct | 106 | 28 → 59 | **31** (22) | 15/60 | 37 / 4 | 0 |
| airline ShieldAgent | 117 | 38 → 80 | **42** (37) | 14/60 | 45 / 6 | 2 |
| retail no shield | 226 | 58 → 83 | **25** (22) | 20/138 | 38 / – | – |
| retail Direct | 204 | 24 → 47 | **23** (23) | 19/138 | 24 / – | – |
| retail ShieldAgent | 78 | 21 → 32 | **11** (10) | 9/138 | 13 / – | – |

**Phase 1 (gpt-6-luna, train split)**

| config | write calls | violating v1 → v2 | **missed by v1** (API-accepted) | conversations with a missed call | new: confirmation / cancel eligibility | of the confirmation misses, on `cancel_reservation` |
|---|---|---|---|---|---|---|
| airline no shield | 37 | 0 → 1 | **1** (1) | 1/60 | 1 / 0 | 1 |
| airline Direct | 34 | 1 → 3 | **2** (2) | 1/60 | 2 / 0 | 2 |
| airline ShieldAgent | 5 | 0 → 0 | **0** | 0/60 | 0 / 0 | – |
| retail no shield | 200 | 6 → 7 | **1** (1) | 1/138 | 1 / – | – |
| retail Direct | 185 | 0 → 0 | **0** | 0/138 | 0 / – | – |
| retail ShieldAgent | 117 | 1 → 1 | **0** | 0/138 | 0 / – | – |

## Effect on the reported metrics

| | success and no gold violation, v1 → v2 | success and no **API-accepted** violation, v1 → v2 | violating calls / conversation, v1 → v2 | block precision on scorable write blocks, v1 → v2 |
|---|---|---|---|---|
| P6 airline no shield | 0.89 → 0.83 | 1.00 → **0.94** | 0.78 → 1.82 | – |
| P6 airline Direct | 1.00 → 0.94 | 1.00 → **0.94** | 0.47 → 0.98 | 0.52 → **0.79** (17 → 26 of 33) |
| P6 airline ShieldAgent | 1.00 → 0.93 | 1.00 → 1.00 | 0.63 → 1.33 | 0.13 → **0.66** (12 → 59 of 89) |
| P6 retail no shield | 0.81 → 0.75 | 1.00 → **0.92** | 0.42 → 0.60 | – |
| P6 retail Direct | 0.96 → 0.85 | 1.00 → **0.89** | 0.17 → 0.34 | 0.59 → 0.63 (27 → 29 of 46) |
| P6 retail ShieldAgent | 0.95 → 0.80 | 1.00 → **0.85** | 0.15 → 0.23 | 0.24 → 0.35 (43 → 63 of 181) |
| P1-luna airline Direct | 0.96 → 0.96 | 0.96 → 0.96 | 0.02 → 0.05 | 0.00 → 0.00 (of 4) |
| P1-luna retail Direct | 1.00 → 1.00 | 1.00 → 1.00 | 0.00 → 0.00 | 0.07 → 0.21 (1 → 3 of 14) |
| P1-luna retail ShieldAgent | 1.00 → 1.00 | 1.00 → 1.00 | 0.01 → 0.01 | 0.00 → 0.07 (0 → 11 of 152) |

(The P1-luna rows not shown are unchanged: 1.00 / 1.00, and 0.00–0.05 violating calls per conversation.)

## Findings
1. **v1 under-counted nano's violations by about 2× in airline and 1.4–2× in retail.** Most of the misses are
   confirmation violations, and in airline most of those are blanket "yes, proceed" confirmations given before the
   details were listed (rule F5). Cancellation eligibility adds 19 / 4 / 6 calls in airline. These include the 3
   calls that the P6 manual audit found missed in airline no shield task 28 trial 2.
2. **The P6 claim "no API-accepted violation in successful episodes" (p6_report §4) does not survive v2.** 5 of 6
   configurations have successful conversations with an executed confirmation or eligibility violation (5–15 % of
   successes). τ-bench rewards these conversations as successes.
3. **ShieldAgent's P6 block precision was understated by v1** (airline 0.13 → 0.66, retail 0.24 → 0.35), because
   many of its blocked writes came after blanket confirmations. Direct still leads in retail (0.63 vs 0.35). In
   airline the two are now close (0.79 vs 0.66). P6's ranking on pass^1 and cost is unaffected.
4. **The luna agent is almost fully compliant on train, even under v2:** 0–2 missed calls per configuration. The
   3 airline misses are all `cancel_reservation` calls (the interpretation scope) after a direct instruction ("please
   cancel SE9KEL and PUNERT"). For Phase 2 this means "violations caught" on train can only be a small number. Block
   precision and pass^1 will carry most of the signal.

## Reproduce
```bash
PY=~/venvs/tau-bench/bin/python
for t in full ../../tgr/online/luna_train; do
  $PY scripts/reproduction/p6_gold_score.py $t --gold v2
  $PY scripts/reproduction/p6_metrics.py $t --gold v2
  $PY scripts/reproduction/gold_compare.py $t
done
$PY -m unittest tests.gold_v2.test_checks
```
