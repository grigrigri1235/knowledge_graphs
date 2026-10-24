# v4 runner (P1e): short notes

Files (owner P1e): `guard/run_online_v4.py` (copy of `run_online_v3.py`), `guard/soft_stop_v4.py` (copy of
`soft_stop_v3.py`), `scoring/v4_interim.sh` (the halfway watcher), `scripts/v4_dry_all.sh`, `tests/test_v4_run_online.py`. v3 files unchanged (sha checked by the test). No `h_tasks.json`:
Hv4 uses `output/eval_v3/online_tasks.json`.

## Arm plan (P10, user decision): live runs no longer run every arm
Arms the runner knows: none, direct, tgr_frozen, tgr_tracker_v3, direct_facts_v4, tgr_tracker_v4. A group = the live
arms of one (domain, task, try).

| step | live arms | tasks | tries | units | baseline (not run) | limit | shards |
|---|---|---|---|---|---|---|---|
| B1v4 | direct_facts_v4, tgr_tracker_v4 | retail:4, airline:4 | 1 | 4 | none | $1 | 1 |
| B2v4 | direct_facts_v4, tgr_tracker_v4 | `eval_v3/online_tasks.json` (99) | 3 | 594 | v3 `B2/B2_20261023T155537Z_c842d895` (none, direct, tgr_frozen, tgr_tracker_v3; 297 lines each) | $10 | 1-6 |
| B3v4 | the two v4 arms on all 64; none, direct, tgr_frozen, tgr_tracker_v3 on the 15 fill tasks | `eval_v3/b3_tasks.json` (64) | 1 | 128 + 60 = 188 | v3 `B3/B3_20261023T190740Z_9bf882c0` (same 4 arms, 49 tasks each) | $6 | 1-6 |
| Hv4 | all 6 (nano agent) | the same 99 | 1 | 594 | none | $8 | 1-6 |

B3v4 fill tasks (missing from v3's B3): retail 368, 380, 393, 415, 416, 427, 431, 433, 434, 445, 451, 462, 464, 474, 497.
`tgr_tracker_v3` runs only in B3v4 and Hv4, built by v3's runner (`make_answers_hook`, `build_arm`, unchanged), with
its own tiny-question store `questions/answers_v3_shard<i>of<n>.jsonl`; the two tiny backends share the shard's budget
half and half. `direct_facts_v3` is never an arm.

Baseline: `run.json` has `"baseline": {run_dir, run_id, arms, task_file_sha256, ...}`. A real B2v4 / B3v4 start reads
counts and keys only (never conversation content) and refuses if the baseline's `tasks_file_sha256` differs, if a B2
arm has not exactly 297 lines, or if a B3 arm's task keys are not exactly the 64 tasks minus the 15 fill tasks.
Sandbox and dry runs never read v3's runs (their `baseline.check` says "real runs only"). $0 check for the main chat:
`python -B -m guard.run_online_v4 baseline-check --step B2v4` (and `B3v4`). Not run by P1e (rule: no v3 B2/B3 reads).

Money (soft_stop_v4.STEP_LIMITS_USD): dev $2, B1v4 $1, B2v4 $10, B3v4 $6, Hv4 $8; total cap $30 (was $80). B1 mean cost
gate unchanged: <= $0.032 per conversation (now 4 conversations). Cost stop thresholds: preregistration_v4.md §11
(tgr_tracker_v3 takes the "another arm" value: $0.044, B3 $0.086).

DEV20v4 (the retail-dev-20 side check) is **dropped** (user decision): refused with that reason.

## Run (real, from predicate_correctness/; stdout must be the log file)
```
~/venvs/tau-bench/bin/python -B -m guard.run_online_v4 new-id --step B2v4
# B2v4 / B3v4: start the watcher FIRST (background; it waits up to 900 s for pids.txt), then the shards
bash scoring/v4_interim.sh output/eval_v4/B2v4/<id> output/eval_v4/B2v4/<id>/pids.txt \
    > output/logs/v4_B2v4_<id>_watcher_stdout.txt 2>&1 &
~/venvs/tau-bench/bin/python -B -m guard.run_online_v4 run --step B2v4 --run-id <id> --shard 0/6 --workers 8 \
    --approved "<the user's words>" --i-am-the-main-chat > output/logs/v4_B2v4_<id>_s0.log 2>&1
```
A real run refuses without: `--i-am-the-main-chat`, the approval words, a passing `scoring/v4_freeze.py` check whose
manifest lists every `freeze_required_files()` path with its current sha256 (guard inputs, this runner,
`soft_stop_v4.py`, facts / questions files, `b3_tasks.json`, and now `scoring/v4_b1_summary.py`,
`v4_online_metrics.py`, `v4_diagnosis.py`, `v4_online_interim.py`, `scoring/v4_interim.sh`), the log file as stdout,
a passing real B1v4 (B2v4, B3v4, Hv4). New (audit P9):
- B2v4 / B3v4: refused unless the halfway watcher of that run is live (it holds
  `output/logs/v4_<step>_<run_id>_watch.lock`). Chosen over "the runner starts it": simpler, the runner never spawns.
- refused when the approval words are already in another step's `run.json` (one approval, one step).
- any start (not a dry run) is refused while another run id of the same step has a live runner (shard lock files
  name their run id; a pid counts only if its command line names that run id).
- `--arms` (sandbox only: the identity check), `--tries`, `--task-ids`: refused outside the sandbox.

Shards: the step flock (`<step>/locks/group_start.flock`) is held around each new group's check AND (P9) around every
unit check of an open group and every re-run check. A unit's check counts the units in flight in all shards at p90;
near the limit (what is left < 2 x p90 x shards) each unit in flight counts $0.25. Unit ledger as before.
v4 total: the dev part is max(dev spend ledger `output/eval_v4/dev/dev_spend_ledger.jsonl` (read only, at call time,
no lock), the dev answers files). Dry run: add `--dry-run --out-root output/eval_v4/dryrun/<name>`.

## Halfway (preregistration_v4.md §11)
Mark (P10): B2v4 the first 149 complete groups of the v4 arms, B3v4 32 groups of the 64 v4 tasks
(`HALFWAY_GROUPS`; `HALFWAY_CONVERSATIONS` = 298 / 64). The decision (tgr_tracker_v4 vs v3's tgr_frozen baseline) is
`scoring/v4_online_interim.py`'s, saved once in `<run>/halfway.json`; soft_stop_v4 only reports the mark.
Two places apply it, both with that one saved decision:
1. the watcher `scoring/v4_interim.sh` (every 300 s: `v4_online_interim --write-stop`);
2. backup (P9): the runner itself, before each new group (`halfway_backup`): reads `halfway.json` (or asks
   `harm_check` to compute and save it once the run has the mark's units done, at most once a minute); a fire writes
   STOP and stops new groups; a check that raises fails closed (STOP with the reason).

Watcher rules: it ends on STOP (exit 0), when no pid of `pids.txt` is alive (`kill -0` + `run_online_v4` in
`/proc/<pid>/cmdline`; exit 0), after 3 failed checks in a row (P9: it writes STOP with the reason first, never over
an existing one; exit 4), with no pids file after 900 s (exit 3). One watcher per run (flock; exit 5). Test overrides
`V4_INTERIM_EVERY`, `_CMD`, `_PY`, `_CMD_MARK` are obeyed only for a run folder under `output/eval_v4/dryrun/` (P9);
for a real folder they are ignored and logged. `V4_INTERIM_LOGS`, `V4_INTERIM_PID_WAIT` always.

## Records
- Episode line: v3's fields plus `conversation_id` = `<run_id>:<arm>:<domain>:<task>:<trial>:a<attempt>`.
- Tiny answers: `questions/answers_shard<i>of<n>.jsonl` (v4, with `conversation_id` and `where`),
  `questions/answers_v3_shard<i>of<n>.jsonl` (v3's tracker, v3's records), asks in `questions/asks_shard<i>of<n>.jsonl`.
- `run.json`: `v4_manifest_sha256`, the freeze result, `live_arms`, `baseline`.

## Interface the other v4 modules must meet
- `guard/tgr_tracker_v4.py`: `build(domain, tools, *, answers, **ONLINE_SWITCHES[, require_freeze])`; record keeps
  `rec["v3"]` (`state_errors`, `fact_errors`), `rec["v4"]` merged too; a failed real tiny call is a fact error
  `RealCallFailed`.
- `guard/direct_facts_v4.py`: `build(domain)`; `rec["direct_facts"]["facts_failure"]` (B1v4 check).
- `state_tracker/v4/questions_v4.py`: `load_questions_v4()`, `QuestionsV4(...)`, `RealBackendV4(...)`.
- `scoring/v4_freeze.py`: `check(...)` (both APIs handled).
- `scoring/v4_online_interim.py`: `read_halfway`, `harm_check(run_dirs, lines, step, save=)`, `raw_lines` (the runner's
  backup uses them). Its owner is moving it to the P10 plan (v4 vs v3's frozen baseline; marks 149 / 32 groups).
- `scoring/v4_b1_summary.py`: still expects 10 conversations x 5 arms; until its owner moves it to 4 conversations x 2
  arms the B1 gate's section 13 check fails, so B2v4 / B3v4 / Hv4 cannot start (the test of it is skipped with that
  reason).

## Choices to review
- The watcher must be live for a real B2v4 / B3v4 start (not started by the runner).
- The runner's halfway backup fails closed (STOP) on any error of the interim check.
- The baseline check reads counts and keys only, on the real path only; P1e never ran it on the real v3 folders.
- `--arms` exists for the identity check only (sandbox); the identity check compares none, direct, tgr_frozen.
