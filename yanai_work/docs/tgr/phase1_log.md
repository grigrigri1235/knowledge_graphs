# Phase 1 log: development baselines (gpt-6-luna, train split)

Approved 2026-10-19 together with decisions M1–M6. All runs use profile `luna-dev`. No grok-4.7 call is made in
this phase.

## Runs (documented as runs, not code changes)

| when | what | command / script | output |
|---|---|---|---|
| 2026-10-19 09:25 | ShieldAgent P1 rebuild, airline then retail: frozen `repro_pipeline` (tag repro-p1-v1), rule-building model gpt-6-luna, Domain-Basic-filtered policy, run id `v1` | `output/tgr/phase1/p1_rebuild_luna.sh` → `python -m exp_core.run_p1 --profile luna-dev --domain <d> --policy policy_docs/<d>_wiki.txt --drop-heading "Domain Basic" --run-id v1` | `output/tgr/aspm_runs/luna-dev/<d>/v1/` |
| after P1 | train runs, 3 trials, none / Direct / ShieldAgent (Stage A: aux low, planner medium, ε 0.1, θ 1, cap 3, 30 executed steps; ASPM = the luna rebuild) | `output/tgr/phase1/train_runs_luna.sh` (3 lanes, ≤ 3 processes, resumable) → `python -m exp_core.run_online --profile luna-dev --env <d> --guard <g> --tasks train --trials 3 --tag luna_train [--aspm-dir …]` | `output/tgr/online/luna_train/<d>/<g>/episodes.jsonl` |
| after runs | metrics: P6 gold scorer + P6 metrics unchanged, plus repeat-after-block and per-role tokens | `python scripts/tgr/metrics.py luna_train` | `output/tgr/online/luna_train/{metrics.json, metrics_tgr.json}` |

## Code added for Phase 1 (no existing code changed)

- `exp_core/run_p1.py`: runs the frozen P1 CLI under a profile, with these differences:
  - filtered policy input;
  - output in `output/tgr/aspm_runs/<profile>/`;
  - embedding cache copied once to `output/tgr/_embcache/` (the nano cache is only read);
  - after the run, the frozen CLI's hard-coded `model: gpt-5-nano` label is corrected in `aspm.json` meta and
    `manifest.json`, and a `tgr` block is added (decision M5).
- `scripts/tgr/metrics.py`: wraps the unchanged P6 scripts and adds the repeat-after-block metric. Definition: the
  next attempt after a non-override block has the same action and arguments. Checked against P6: it reproduces the
  reported 34.7 % / 53.1 % (ShieldAgent) and 1.3 % / 0 % (Direct).

## Events

- **2026-10-19 09:25–21:50, P1 rebuild.** Airline v1 finished 15:47 and retail v1 21:49 (Alg. 2 took 6.3 h and 6.0 h).
  Both loaders succeeded with 57 rules each; no rule was edited. Counts: `p1_report.md` §1.
- **2026-10-19 21:54 to 2026-10-20 02:11, train runs.** All 6 jobs logged DONE (3 lanes, ≤ 3 processes).
- **Disconnect.** The launching session ended without a report. A status check on 2026-10-20 found no Phase 1
  process running and every `episodes.jsonl` complete (airline 60, retail 138 per guard; no duplicates).
- **Content-filter failure (as P6 O7).** Retail / no shield / task 52 trial 1 ended with an Azure `content_filter`
  HTTP 400 on the agent's prompt ("sexual: high", a false positive). On 2026-10-20 07:30 only that unit was resumed,
  with the same configuration (`exp_core.run_online --profile luna-dev --env retail --guard none --tasks train
  --trials 3 --tag luna_train`, `setsid nohup`; the runner skips every unit with a clean result). The earlier file is
  kept as `episodes.before_resume.jsonl`. Result: reward 1, 84 s; all 594 units are now clean.
- **CPU contention.** A stuck `scripts/reproduction/p1_trace.py` process from another session (started 2026-10-18,
  writing only to that session's scratchpad) used the VM's only CPU for 33 h, the whole of Phase 1. It was stopped
  on 2026-10-20. Phase 1 wall times are inflated; results are not affected.
- **Metrics addition.** `scripts/tgr/metrics.py` now also computes the paired Δ pass^1 vs no shield and vs Direct
  (P6 bootstrap: `p6_metrics.boot`, 10k resamples, seed 0), conversations with ≥ 1 block, and max blocks. On the P6
  data it reproduces all four reported Δ values and CIs exactly.
- **2026-10-20, report:** `p1_report.md`.
