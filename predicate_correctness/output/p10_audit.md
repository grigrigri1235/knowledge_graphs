# Part 10: independent audit of the guard and the wrapper (before any LLM spend)

Date 2026-10-22. The auditor did not write the guard or the wrapper. No LLM calls were made, and $0 was spent.
Nothing in `~/ShieldAgent` was changed: it was only read, and every git command there used `GIT_OPTIONAL_LOCKS=0`.

**Verdict: PASS. No problem blocks the runs, and no code was fixed: no clear bug was found.**

## Result table
| # | check | result | evidence |
|---|---|---|---|
| 1a | Same TGR judge prompt | **pass** | For all 4,903 saved records, the prompt our guard sends (copied TGR, model gpt-6-luna, effort medium, same schema) gives a cache key that exists in the partner's judge cache. So the prompts are byte-identical to the partner's runs (`p10_audit_state.log`). |
| 1b | Same decision and feedback | **pass** | 4,669 records where the tracker changes no value: matched, circuit, values, decision, margin, violated rules, unknown predicates and feedback text are all the same as TGR's saved record, with 0 differences. This includes all 417 blocked records, whose feedback text is identical (`p10_audit_feedback.log`). |
| 1c | Only code-type values are replaced | **pass** | Code reading: `merge()` replaces only names in `code_types` (argument, database fact, event) that have a true or false lookup value. Offline check: 6,689 values replaced, all code types. |
| 1d | Version (b) fallback | **pass** | A lookup that gives unknown, fails, has no entry, or runs on a bad state (replay mismatch, parse problem, output without a call) keeps the judge's value. Unit tests cover each case. |
| 1e | Judge skip rule | **pass** | Skip only if `names` is not empty, every name is a code type, and every lookup gave true or false. Otherwise the judge is called once, with all circuit predicates. With the frozen rules the judge is never skipped: 0 of 4,903 records. |
| 1f | Lookup errors are handled safely | **pass** | `build_state` and `evaluate_detail` are wrapped in try/except, so an error falls back to the judge and is logged. One line, `tracker_evidence`, is outside the try (`lk["plain"]`, `d["missing"]`). It cannot fail: `check_lookups` passes and `evaluate_detail` always returns `missing`. |
| 1g | Blocked attempts stay out of the history | **pass** | The copied episode loop adds a blocked attempt only to `messages`, never to `executed`, and `make_step` passes `list(executed)`. On all 5,497 saved attempts, the agent messages in the history equal the executed attempts before the step. |
| 2 | Online state = offline state | **pass** | All 5,497 attempts: the state built as the live loop builds it (`make_step` on `executed[:prefix]` with the real agent message, then `build_state`) equals the Part 4-6 state (`walk`). Checked fields: database, shown objects, shown metadata, events, step count, problems and pending action. Replay mismatches 0, parse problems 0. Tracker values equal Part 6 in 4,903 of 4,903 records, with 0 lookup errors. |
| 2b | Thread safety (8 workers share one guard) | **pass** | 1,116 of 1,116 tracker results from 8 threads equal the results from one thread. The info is thread-local, and each check gets its own deep copy of the database. |
| 2c | τ-bench copy = τ-bench the runs use | **pass** | The tools and data of both domains, and `base.py`, are identical between the venv's site-packages and our copy. The policy texts are identical too (`p10_audit_taudiff2.log`). |
| 3 | All writes go under `predicate_correctness/output/` | **pass** | Code reading: the wrapper installs the write guard (an audit hook) first; episodes, run JSON and the LLM cache go under `output/`; `models.CACHE_ROOT` is set before `activate()`. Dry runs: 6 documented commands plus 10 refusal cases. Afterwards, `output/online` and `output/_llmcache` do not exist, and there is no `__pycache__`. The only new files outside `output/` are the 3 audit scripts in `tests/`. In `~/ShieldAgent`, HEAD (1bacdb0) and the hash of `git status` are the same before and after, and 0 files changed in the last 90 minutes. |
| 4 | No grok-4.7 and no test split | **pass** | `--profile grok-eval` is refused by argparse. `--tasks test` / `dev` are refused. `--task-ids 2` (airline test) and `--task-ids 0,1` (retail test) are refused. `--guard tgr` is refused. Every role's model is checked against {gpt-6-luna, gpt-5-nano}. |
| 5 | Profiles match the partner's baselines | **pass** | `model_profiles.json` sha256 is the same as the partner's (03c46ecf…). Every partner run JSON (tgr/none/direct for luna_train_v5 tgr, nano_train, luna_val) records the same roles as ours: luna-dev = gpt-6-luna for all roles, with responses API and effort medium for the agent and user. nano-agent-luna = gpt-5-nano agent (chat API, default effort) with gpt-6-luna user and guard. The rule sets equal the partner's (`it5` = `frozen`, same sha256), and `splits.json` is the same. |
| 6 | Tests pass | **pass** | 153 of 153 (`p10_audit_tests.log`). |

## Problems found (none blocks the runs)
1. **The judge is never skipped** with the frozen rules: every tool's rules have a conversation or mixed predicate.
   So `tgr_tracker` saves no judge cost (this was already known). The skip path is tested only with a reduced rule set.
2. **`--rules-dir` accepts any A+B rule set outside `~/ShieldAgent`.** The guard records the sha256 of the rule set
   it uses, but it does not refuse a rule set that differs from the frozen one. The documented commands do not pass
   `--rules-dir`. **Rule for the runs:** do not pass `--rules-dir`.
3. **The wrapper has no spending cap.** Projection from the partner's TGR runs with the same tasks and profiles:
   $0.58 + $1.72 (luna train), $1.44 + $3.29 (nano train), $0.35 + $0.90 (luna val), so about **$8.3 in total**
   (`p10_audit_cost.log`). That is well under $25. The smoke test should confirm the cost per conversation before
   the full runs.
4. **Failed episodes stay in `episodes.jsonl`.** When a run resumes, the failed (task, trial) runs again and a new
   line is added; this is the same as in the partner's runner. The metrics step must drop lines with `error` and keep
   one line per (task, trial).
5. **The partner's luna_train_v5 TGR run started (12:23) before the commit of iteration 5 (b2ec28c, 12:55).** This
   is not a problem: all of its judge prompts are in the partner's cache exactly as our copy renders them, and its
   decisions and feedback are reproduced. So the code that matters was the same.
6. **Feedback text differs from TGR's only where a tracker value differs from the judge's.** There, the evidence
   is the lookup's plain sentence. This is by design, and it is documented.
7. **This audit covers only saved histories, which have 0 replay mismatches.** In new conversations, a mismatch
   makes the guard use the judge's values for that check. That is safe, but the smoke test should count
   `tracker.state.mismatches` and `tracker.lookup_errors`.

## Fixes
None. No clear bug was found, so no code was changed.

## Files
- Audit scripts: `tests/audit_p10_state.py` (checks 1g, 2, 2b, 1a), `tests/audit_p10_feedback.py` (check 1b) and
  `tests/audit_p10_wrapper.sh` (checks 3 and 4). The scripts are not unit tests and are not collected by
  `unittest discover`. None of them calls an LLM.
- Logs (`output/logs/`): `p10_audit_state.log`, `p10_audit_feedback.log`, `p10_audit_wrapper.log`,
  `p10_audit_wrapper2.log`, `p10_audit_tests.log`, `p10_audit_baselines.log`, `p10_audit_codeversions.log`,
  `p10_audit_taudiff2.log`, `p10_audit_cost.log`, `p10_audit_shield_before.log`, `p10_audit_shield_after.log`.
