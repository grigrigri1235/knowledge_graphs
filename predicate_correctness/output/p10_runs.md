# Part 10 runs 1 and 2: "TGR + tracker" on the train tasks

Date 2026-10-22 (p10.md subtask 7, runs 1 and 2). Guard `tgr_tracker` (frozen TGR + tracker values, version b),
3 trials, train tasks, through our wrapper `guard/run_online.py`. Status script: `scoring/p10_runs_check.py` (stdlib,
no LLM). Run 3 (val) is a later step.

**Result: success.** All 4 jobs finished. Every planned conversation is there, with 0 errors, so no rerun was needed.
Spend was $6.63 for these runs ($6.67 for Part 10 so far). The projected Part 10 total is $7.95, under the $25 cap.

## Commands
Run from `predicate_correctness/`, all 4 started at the same time with `setsid nohup`, venv Python with `-B` and
`PYTHONDONTWRITEBYTECODE=1`, 8 workers each (as in the partner's runs):
```
python -B -m guard.run_online --profile luna-dev        --env airline --tasks train --trials 3 --tag p10_luna_train --workers 8
python -B -m guard.run_online --profile luna-dev        --env retail  --tasks train --trials 3 --tag p10_luna_train --workers 8
python -B -m guard.run_online --profile nano-agent-luna --env airline --tasks train --trials 3 --tag p10_nano_train --workers 8
python -B -m guard.run_online --profile nano-agent-luna --env retail  --tasks train --trials 3 --tag p10_nano_train --workers 8
```
No `--rules-dir` (so the frozen rule sets are used), as the audit advised. Before the start, a dry run of each job
planned 60 / 138 units, with 0 already done and the right models (`logs/p10_runs_02_dry.log`).

Logs: `output/logs/p10_luna_train_{airline,retail}.log`, `output/logs/p10_nano_train_{airline,retail}.log`. Each one
ends with `DONE: ... ; refused writes 0`.

## Times
| run | domain | start | end | minutes |
|---|---|---|---|---|
| 1 luna-dev | airline | 05:32:20 | 05:42:20 | 10 |
| 1 luna-dev | retail | 05:32:19 | 05:59:26 | 27 |
| 2 nano-agent-luna | airline | 05:32:18 | 06:04:00 | 32 |
| 2 nano-agent-luna | retail | 05:32:19 | 06:38:15 | 66 |

All times are UTC on 2026-10-22. End time = start + the seconds in the DONE line. 4 processes ran at once (the
step's limit is 4; p10.md said 3, because of memory). Memory use stayed at 3.4 GB or less, out of 16 GB.

## Conversations, errors and reruns
| run | domain | expected | lines | good units | error lines | duplicate units | trials 0/1/2 |
|---|---|---|---|---|---|---|---|
| 1 luna-dev | airline | 60 | 60 | 60 | 0 | 0 | 20/20/20 |
| 1 luna-dev | retail | 138 | 138 | 138 | 0 | 0 | 46/46/46 |
| 2 nano-agent-luna | airline | 60 | 60 | 60 | 0 | 0 | 20/20/20 |
| 2 nano-agent-luna | retail | 138 | 138 | 138 | 0 | 0 | 46/46/46 |

- **Reruns: none.** There were no failed units, so no `episodes.before_resume.jsonl` was made.
- Models in every record: luna-dev = gpt-6-luna for agent, user and guard; nano-agent-luna = gpt-5-nano agent and
  gpt-6-luna user and guard. No grok-4.7, and no test tasks.
- Outputs: `output/online/p10_luna_train/<env>/tgr_tracker/` and `output/online/p10_nano_train/<env>/tgr_tracker/`
  (`episodes.jsonl` and one `run_*.json` each). Judge caches: `output/_llmcache/p10_luna_train/` (2,057 files) and
  `output/_llmcache/p10_nano_train/` (2,574 files).

## Guard records (checks on every good unit)
| run | domain | guard checks | judge calls | judge skipped | values replaced | values changed | tracker unknown | lookup errors | replay mismatches | cap overrides |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | airline | 637 | 315 | 0 | 204 | 4 | 0 | 0 | 0 | 0 |
| 1 | retail | 1,754 | 1,744 | 0 | 2,205 | 24 | 0 | 0 | 0 | 0 |
| 2 | airline | 745 | 487 | 0 | 643 | 68 | 1 | 0 | 0 | 4 |
| 2 | retail | 2,184 | 2,183 | 0 | 3,477 | 199 | 1 | 0 | 0 | 24 |

- Every check with a judge has a tracker part. 0 predicates that are not a code type were replaced.
- For the 2 tracker unknowns, the judge's value was kept (version b).
- "Values changed" means the tracker value differs from the judge's value. It does not mean the decision changed.
  Subtask 9 measures decisions and their effects.
- Cap overrides come from the copied runner (the block cap is reached and the call is let through). They appear only
  with the nano agent.

## Cost
| run | domain | cost $ | per conversation $ | partner TGR per conversation $ | agent / user / judge $ | seconds per conversation |
|---|---|---|---|---|---|---|
| 1 luna-dev | airline | 0.617 | 0.0103 | 0.0097 | 0.361 / 0.041 / 0.215 | 74 |
| 1 luna-dev | retail | 1.728 | 0.0125 | 0.0125 | 0.913 / 0.088 / 0.726 | 86 |
| 2 nano-agent-luna | airline | 1.294 | 0.0216 | 0.0240 | 0.784 / 0.102 / 0.408 | 229 |
| 2 nano-agent-luna | retail | 2.988 | 0.0217 | 0.0239 | 1.574 / 0.192 / 1.223 | 207 |
| **runs 1-2** | | **6.627** | | | | |

- Part 10 spend so far: **$6.674** (runs 1-2 plus the $0.047 smoke test).
- Our cost / partner TGR's cost on luna train, same tasks: 1.02.
- Projection for run 3 (val, luna-dev): partner luna_val TGR $1.249 x 1.02 = $1.27.
- **Projected Part 10 total: $7.95**, under the $25 cap (`logs/p10_runs_09_final.log`).

## First look (raw means, no confidence intervals; subtask 9 does the real comparison)
| run | domain | reward ours | TGR | Direct | no guard | blocks/conv ours | TGR |
|---|---|---|---|---|---|---|---|
| 1 luna-dev | airline | 0.550 | 0.500 | 0.467 | 0.533 | 0.20 | 0.20 |
| 1 luna-dev | retail | 0.797 | 0.710 | 0.681 | 0.761 | 0.33 | 0.39 |
| 2 nano-agent-luna | airline | 0.433 | 0.383 | 0.367 | 0.400 | 1.10 | 1.52 |
| 2 nano-agent-luna | retail | 0.674 | 0.667 | 0.681 | 0.652 | 2.36 | 2.72 |

The baselines are the partner's saved runs (`luna_train_v5`, `nano_train`), read only. Sampling has no seed, so part
of any gap is noise (p10.md: changes under about 0.08 are hard to tell from noise).

## Nothing written outside our folder
Logs: `logs/p10_runs_01_before.log`, `logs/p10_runs_10_after.log` and `logs/p10_runs_11_partner_commit.log`.
- `~/opt/tau-bench-59a200c` and `~/venvs`: 0 files newer than the start marker. No `__pycache__` in our folder.
- `code_projects`, outside `predicate_correctness/output/`: only the new script `scoring/p10_runs_check.py`.
- `~/ShieldAgent` changed during the runs, **but not because of us**. HEAD moved from `1bacdb0` to `7e6575b`: 3
  commits by the partner's user, made 06:05-06:16, on docs and `scripts/reproduction/p1_trace.py`. New metric and gold
  files (`gold*.jsonl`, `metrics*.json`) appeared in the partner's `output/tgr/online/nano_train/`, and the git
  status is now clean. Our wrapper never runs git, its write guard refuses any access to `~/ShieldAgent`, and it
  refused 0 writes. No baseline `episodes.jsonl` changed.
  - The copies in `from_shieldagent/` were made from `1bacdb0`. The new commits do not touch any copied file:
    `tests/check_copies.py --sources` still gives 136 of 136 OK after the runs (`logs/p10_runs_13_copies.log`).

## Run 3: val tasks, luna-dev (tag `p10_luna_val`)
Date 2026-10-22 (p10.md subtask 7, run 3). Started only after the checks above showed runs 1-2 were clean.

**Result: success.** Both jobs finished. All 99 planned conversations are there, with 0 errors, so no rerun was
needed. Run 3 cost $1.21. **Part 10 spend so far is $7.885**, under the $25 cap (no LLM run is left in Part 10).

**Commands** (from `predicate_correctness/`, both started at 06:41 UTC with `setsid nohup`, venv Python with `-B` and
`PYTHONDONTWRITEBYTECODE=1`, 8 workers each, no `--rules-dir`):
```
python -B -m guard.run_online --profile luna-dev --env airline --tasks val --trials 3 --tag p10_luna_val --workers 8
python -B -m guard.run_online --profile luna-dev --env retail  --tasks val --trials 3 --tag p10_luna_val --workers 8
```
A dry run first planned 30 / 69 units, 0 already done, gpt-6-luna for every role, frozen rules
(`logs/p10_val_02_dry.log`). Logs: `logs/p10_luna_val_{airline,retail}.log`; both end with `DONE: ... ; refused
writes 0`. Only 2 processes ran at once.

| domain | start | end | minutes | expected | lines | good units | error lines | duplicate units | trials 0/1/2 |
|---|---|---|---|---|---|---|---|---|---|
| airline | 06:41 | 06:48 | 7 | 30 | 30 | 30 | 0 | 0 | 10/10/10 |
| retail | 06:41 | 06:56 | 15 | 69 | 69 | 69 | 0 | 0 | 23/23/23 |

- The task lists equal the partner's `luna_val` runs (airline 10 tasks, retail 23 tasks).
- Outputs: `output/online/p10_luna_val/<env>/tgr_tracker/` (`episodes.jsonl` and one `run_*.json` each). Judge cache:
  `output/_llmcache/p10_luna_val/` (1,045 files).

**Guard records**
| domain | guard checks | judge calls | judge skipped | values replaced | values changed | tracker unknown | lookup errors | replay mismatches | cap overrides |
|---|---|---|---|---|---|---|---|---|---|
| airline | 340 | 186 | 0 | 111 | 3 | 0 | 0 | 0 | 0 |
| retail | 863 | 859 | 0 | 1,110 | 9 | 0 | 0 | 0 | 0 |

Every check with a judge has a tracker part, and 0 non-code predicates were replaced.

**Cost**
| domain | cost $ | per conversation $ | partner TGR per conversation $ | agent / user / judge $ | seconds per conversation |
|---|---|---|---|---|---|
| airline | 0.346 | 0.0115 | 0.0116 | 0.197 / 0.026 / 0.123 | 97 |
| retail | 0.866 | 0.0125 | 0.0131 | 0.453 / 0.046 / 0.367 | 96 |
| **run 3** | **1.212** | | | | |

- Part 10 spend: smoke $0.047 + runs 1-2 $6.627 + run 3 $1.212 = **$7.885** (`logs/p10_val_06_check.log`). The
  "projected total" line in that log ($9.16) counts the val run twice, because the script adds a val projection even
  when the val run is done. The real total is $7.885.

**First look (raw means, no confidence intervals; subtask 9 does the real comparison)**
| domain | reward ours | TGR | Direct | no guard | blocks/conv ours | TGR | Direct |
|---|---|---|---|---|---|---|---|
| airline | 0.667 | 0.633 | 0.567 | 0.633 | 0.07 | 0.13 | 0.93 |
| retail | 0.667 | 0.710 | 0.609 | 0.667 | 0.32 | 0.42 | 1.06 |

Baselines: the partner's saved `luna_val` runs, read only (`logs/p10_val_08_summary.log`). With 30 / 69 conversations
these gaps are within noise.

**Nothing written outside our folder** (`logs/p10_val_01_before.log`, `logs/p10_val_09_after.log`,
`logs/p10_val_10_copies.log`, marker `logs/p10_val_marker_before`)
- `~/ShieldAgent`: same HEAD (`7e6575b`) and same git status hash before and after, 0 files newer than the marker
  (by change time or modify time). Its file count is the same as after runs 1-2 (127,580 files).
- `~/opt/tau-bench-59a200c`, `~/venvs` and `code_projects` outside `predicate_correctness/output/`: 0 files newer than
  the marker. No `__pycache__`.
- `tests/check_copies.py --sources`: 136 of 136 OK.
