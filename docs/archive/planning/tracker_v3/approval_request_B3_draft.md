# DRAFT, NOT APPROVED: p14 B3, the optional extra run

> **NOT APPROVED. It needs the user's new, explicit approval for B3, given in the chat.** Approval of B1, B2, p14 or
> this plan does not count. First written 2026-10-23 for $0 while B2 was ending; **updated 17:25 UTC after B2**, with
> B2's costs and the finished $0 build. The build is ready but **not applied**: it is a tested patch in
> `predicate_correctness/output/eval_v3/b3_prep/` (`README.md` there). Applying it edits 3 frozen files (the runner,
> the metrics, the interim check; not the v3 guard), so it needs your OK too.

## What it does, and why
B3 is a small extra test. It was planned only for an unclear B2 (overview Q15); **the user changed that at 16:52 UTC,
before B2's result: B3 runs after B2 whatever B2 shows** (logged in the `preregistration_online.md` change log,
16:54). B2 then passed its main claim, with a "possible leak" warning.

It runs **64 easy-set (Stage A) retail tasks** that need **3 or more expected actions** (the hardest of the easy set)
× **1 try** × **5 arms** (no guard, Direct, Direct + facts, frozen TGR, v3) = **320 live conversations**, paired by
task. Same strong agent (gpt-6-luna for every role), same arms, same v3 (no change).

Why these tasks: each one needs several writes (cancel, change items, return, exchange), so the agent must list and
confirm several actions. That is where v3's extra blocks (p12: 2.4× the old guard's) should hurt most if they hurt.

Checked ($0, read from τ-bench's `retail/tasks_train.py`, no import): 500 tasks; by number of expected actions
1: 334, 2: 102, 3: 40, 4: 14, 5: 7, 6: 2, 7: 1. So **64** tasks have 3 or more, and all of their actions are writes.
They come from τ-bench's **train** file, not its test file, so none is in the partner's test 66 (the partner's split
covers only the test file's 165 tasks). **Never the partner's test group.**

## Starts only when
1. B2 is finished, and its metrics, report and independent recompute are done. **Done** (16:55 UTC).
2. The $0 build below is done, its tests pass, and the sandbox dry run of the exact B3 commands makes 0 calls.
   **Done in the sandbox** (595 tests pass, 1 skipped; dry run 0 calls in all 4 shards; a fake-LLM run of 2 tasks ×
   5 arms made 0 real calls; B1/B2/B2v outputs byte-identical with and without the patch). After applying it in the
   repo: the tests and the 4-shard dry run again.
3. B3's reading rule (below) is written into the change log of `preregistration_online.md` **before** B3 starts.
4. v3 is unchanged: the same guard input sha256s as in B2's `run.json`, **leaving out 3 keys** (the runner's own
   sha, which the patch changes, and the 2 new B3-only keys: `b3_tasks.json` and τ-bench `tasks_train.py`).
5. The spend so far plus B3's $20 limit stays under the $95 cap (the runner checks this too).
6. **Your new, explicit approval for B3**, in the chat.

## The $0 build needed first (needs your OK too; it edits code, so not done in this draft)
The runner says: "B3 is not built here (it needs its own task list)". It only runs τ-bench's test file and the 99
tasks of `online_tasks.json`. To run B3:
1. **Task list:** a new file `output/eval_v3/b3_tasks.json`: the 64 retail train tasks with 3 or more expected
   actions, each with its task sha256; its own sha256 recorded.
2. **Runner** (`guard/run_online_v3.py`): add step `B3` (1 try, first try 0, 64 tasks, 1-4 shards, a tiny-question
   call limit of about 10,000), allow `B3_...` run ids, load the train file (`task_split="train"`) for B3 only, and
   keep the refusal of any partner test task. The hard limit $20 is already in `guard/soft_stop_v3.py`
   (`STEP_LIMITS_USD["B3"]`), so the cap stays $95.
3. **Metrics and the interim check** (`scoring/v3_online_metrics.py`, `scoring/v3_online_interim.py`): a B3 mode for
   64 retail tasks × 1 try (no val / train split, no airline). Halfway = 160 conversations.
4. Tests for each piece, then a sandbox dry run ($0, fake answers, network blocked).
5. New sha256s logged in `overview.md` and in the change log of `preregistration_online.md` (no rule for B2 changes).

Time: about 1-2 h of agent work (my estimate).

## B3's reading rule (to freeze before B3 runs)
- **Number:** v3 − frozen TGR, task success, paired by task, mean over the 64 tasks; 95 % range by bootstrap over
  tasks (10,000 resamples, seed 20261023).
- **Shown as a side result only.** It is never pooled with B2 and never replaces B2's verdict (pre-registration
  section 11: "no new task subset as the headline"). An unclear B2 stays "unclear" in the report.
- The same words as B2: "not clearly worse" if the lower end is above −0.10, else "not shown".

## Numbers
| item | value |
|---|---|
| conversations | 320 (64 × 1 × 5), 4 shards × 8 workers (as B2 ran) |
| cost (estimate) | **about $3.4-7, point about $4**. From B2: 320 × **$0.0106** (B2's mean over all arms) = **$3.40**; these tasks are longer, so up to about 2×. Earlier estimates: p14.md: about $7 ($6.6-9.7; these tasks cost about 2.2× the Stage A mean). B1's measured costs project **$4.76** (64 × per conversation: no guard $0.0082 → $0.52, Direct $0.0215 → $1.38, Direct + facts $0.0158 → $1.01, frozen TGR $0.0180 → $1.15, v3 $0.0109 → $0.70; rough: 2 conversations per arm, and on hard test tasks, not Stage A, so it may be low). |
| hard limit | **$20** (`guard/soft_stop_v3.py`; a new group starts only if spend + reserve stays under it) |
| v3 cap | **$95**, counting p12 and every p14 step |
| spent so far (cost log) | $0.484 before B2, plus B2's $15.76 = **$16.24**. With B3's $20 limit: at most $36.24, under the $95 cap |
| time | about **15-40 min** (p14.md: 30-40 min; B2 ran about 27 conversations a minute with 4 × 8 workers), plus the $0 build first |
| the real bill | about 0.55× the logged list price |

Live spend check ($0, before you approve; output to a file):
```
cd /home/azureuser/code_projects/predicate_correctness
PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -c "from guard import soft_stop_v3 as S; r=S.v3_spend(); print({k: r[k] for k in ('total_usd','questions_usd','episodes_usd','backups_extra_usd','dryrun_usd_not_counted')})" > output/logs/v3_B3_spend_before.txt 2>&1
```

## Stops (the same rules as B2, `preregistration_online.md` section 9; lenient on purpose)
A stop starts no new (task, try) group; open groups finish all 5 arms, so pairs stay complete.
- **Harm at halfway:** at 160 conversations in complete groups, v3 − frozen TGR ≤ −0.15 (the main chat runs the
  interim check below).
- **State errors:** the 3rd v3 check with an exception in the fact code (the runner stops itself).
- **Cost:** an arm's mean cost per conversation, after 50 of its conversations, over 3 × its high estimate (none
  $0.023, Direct $0.044, Direct + facts $0.049, frozen TGR $0.041, v3 $0.061); or one conversation over $0.25.
  Watch Direct: it was $0.0215 per conversation in B1, and these tasks are longer.
- **Errors:** 10 or more error lines that are also over 5 % of lines, or 5 error lines in a row.
- **Money:** the $20 hard limit and the $95 cap.
- **Manual:** the file `STOP` in the run folder.

## Commands (from `predicate_correctness/`; `<words>` = your approval words, copied exactly)
They work only after the $0 build is applied (from `predicate_correctness/`; backups by copy, every output to a file):
```
B3=output/eval_v3/b3_prep
for f in guard/run_online_v3.py scoring/v3_online_metrics.py scoring/v3_online_interim.py; do cp -p $f $f.pre_b3; done
patch -p1 --dry-run < $B3/b3.patch > output/logs/v3_B3_patch_dry.txt 2>&1 && patch -p1 < $B3/b3.patch > output/logs/v3_B3_patch.txt 2>&1
PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m guard.run_online_v3 b3-tasks-file --check > output/logs/v3_B3_tasks_check.txt 2>&1
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v3_b3 tests.test_v3_run_online tests.test_v3_online_metrics tests.test_v3_soft_stop tests.test_no_gold_import > output/logs/v3_B3_unittests.log 2>&1
```
Patch sha256 `e93c3645…`; undo with `patch -p1 -R` or the `*.pre_b3` copies.

Run id (output to a file):
```
~/venvs/tau-bench/bin/python -B -m guard.run_online_v3 new-id --step B3 > output/logs/v3_B3_new_id.txt 2>&1
RUN_ID=$(cat output/logs/v3_B3_new_id.txt)
```
Dry run first ($0, no call; one per shard, each to its own log):
```
for i in 0 1 2 3; do PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 ~/venvs/tau-bench/bin/python -B \
  -m guard.run_online_v3 run --step B3 --run-id $RUN_ID --shard $i/4 --workers 8 \
  --approval "<words>" --dry-run > output/logs/v3_B3_${RUN_ID}_dryrun_s$i.log 2>&1; done
```
The paid run (4 processes, one process group each):
```
for i in 0 1 2 3; do PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 setsid nohup ~/venvs/tau-bench/bin/python -B \
  -m guard.run_online_v3 run --step B3 --run-id $RUN_ID --shard $i/4 --workers 8 \
  --approval "<words>" > output/logs/v3_B3_${RUN_ID}_s$i.log 2>&1 & done
```
- Run folder: `output/eval_v3/B3/$RUN_ID/`. Run id: **`<RUN_ID, filled in at start>`**.
- Approval words: **"`<your approval words for B3>`"**.

## During the run
- Find the processes: `ps -eo pid,pgid,etimes,cmd | grep '[r]un_online_v3' > output/logs/v3_B3_${RUN_ID}_ps.txt 2>&1`
  (never a bare `pgrep -f`).
- `output/eval_v3/progress.md` gets an "auto:" line every 10 minutes.
- **Halfway interim check** ($0, main chat; run it at about 160 conversations, and again later; needs the B3 mode of
  the build):
  ```
  PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 /home/azureuser/miniconda3/bin/python3 -B -m scoring.v3_online_interim \
    --run-dir output/eval_v3/B3/$RUN_ID > output/logs/v3_B3_${RUN_ID}_interim.log 2>&1
  ```
  Its last line says `STOP` or `go on`. On `STOP`: write the STOP file (below) and tell you.

## How to stop and resume
- **Pause:** `kill -STOP <pid>` (resume a pause with `kill -CONT <pid>`).
- **Stop (normal):** `touch output/eval_v3/B3/$RUN_ID/STOP`. No new group starts; open groups finish all 5 arms.
- **Emergency only:** `kill -TERM -<pgid>`. It loses the cost lines of running conversations.
- **Resume:** first **copy** (`cp`, never `mv`) each shard file to `*.jsonl.before_resume`; the live file must stay,
  because its lines are the spend so far (the runner refuses a moved backup). Then run the same paid command again
  with the same `$RUN_ID`. Only one process per shard (a lock file); never start a second one on a paused shard.
  ```
  for f in output/eval_v3/B3/$RUN_ID/*/episodes_shard*of4.jsonl; do cp -p "$f" "$f.before_resume"; done
  ```

## After B3 ($0)
1. Metrics (B3 mode of the build):
   ```
   PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 /home/azureuser/miniconda3/bin/python3 -B -m scoring.v3_online_metrics \
     run --run-dir output/eval_v3/B3/$RUN_ID --out output/logs/v3_B3_${RUN_ID}_metrics.json \
     > output/logs/v3_B3_${RUN_ID}_metrics.log 2>&1
   ```
2. A side section "B3 (optional extra)" in `docs/reports/tracker_v3_report.md`; B2's verdict stays as it is.
3. A cost-log row in `approval_request.md`.
4. The numbers recomputed by an independent agent.
5. Then **stop**.

## What B3 would tell us
- Whether v3 costs tasks on **multi-write** tasks, where it should block most (several listings and confirmations).
- The same five-arm view on a second kind of task: S1 (do facts help Direct?) and S2 (rules vs an LLM with the same
  facts), reported only.
- Live safety on these tasks: v3 allows that τ-bench's tool then refuses (should be 0).
- Cost per conversation of each guard on longer conversations.

## What B3 would NOT tell us
- **It cannot settle an unclear B2 alone.** 64 tasks × 1 try is small: the 95 % range will be about ±0.12-0.15
  (my rough estimate, not computed from saved runs). Even if v3 equals frozen TGR, it often will not pass −0.10.
- **The tasks are seen.** v3 was built and checked on saved Stage A conversations (p11, p12a), so B3 is not a clean,
  unseen test. It says nothing about overfitting (B2's val 33 does that).
- **Retail only.** No airline task.
- **Easy template.** The ids are given in these tasks; they test multi-step writes, not finding the user or the order.
- It is not pooled with B2, and it is not a new headline.

## How to approve
Two things: the build ($0; it edits the 3 frozen files above) and the paid run ($20 limit). You can approve both at
once. Your exact words go into `--approval`.

**DRAFT, NOT APPROVED. Needs the user's new, explicit approval.**
