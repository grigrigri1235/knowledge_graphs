# Tracker v3: approval requests for paid steps

Written by the main chat. **Nothing here runs without your new, explicit approval for that exact step**, given in the
chat. Paid runs are started from the main chat only. Spent: **$21.49** in all for v3 (B2 $15.76, B3 $5.25; see the cost log at the end).

## Request 1: p12, tiny questions on saved conversations (2026-10-23, 11:30 UTC)

**What it does.** v3 asks its small yes/no questions on saved strong-agent conversations, with real answers (no
judge), in two runs:
- **p12a, development data:** a bug check only, not a result;
- **p12b, hold-out, once:** the offline result.

The hold-out run waits until the bug check passes. After p12b, v3 is frozen for p14.

### Step 0, $0 preparation (also needs your OK; p12 is outside the $0 parts you approved)
One agent, about 45-75 min, tests with fake answers only, no network:
1. **Parallel calls.** Today's script asks one question at a time. At about 1-2 s per call (estimate), 22,070 calls
   would take about 6-12 h. Add `--workers 8`: one shared answer store and one shared budget, each question still asked
   once. Then p12a takes about 1-2 h (estimate). A test checks that the answers and the budget stop are the same as
   with 1 worker, on fake answers.
2. **Hold-out in real mode.** Today the script refuses real answers on the hold-out (`--side holdout`). Allow it, with
   its own budget and approval words.
3. **Output path.** Every real run writes its report to a new file (`--out output/eval_v3/p12_answers_<side>.md`), so
   p8's frozen `p8_dryrun.md` is never overwritten.
4. **Optional, your choice: the 2 bugs RC11 found** (fixed on development data, logged in the change log):
   - payment naming: "card ending in 2222" is matched to the card's id ending, not its last four digits (4466); add
     "don't have" to the negation list;
   - the disclosure fact's part a fires without any data output (the example ZIP 19104 case).

   These must go in **before** p12a (after p12b nothing in v3 may change). If they change the call count, I re-count
   ($0) and tell you before any paid call.
5. The fake dry run is run again and must give the same counts (or the new counts, if step 4 changed them).

### p12a: development data (paid)

> **Cut on 2026-10-23 11:57 UTC (the user: cut bug-check time):** p12a runs on a sample, the first 50 conversations of
> each of the 4 data sets (200 conversations, `--limit-convs 50`). Its calls, cost and limits get smaller (filled in
> from the prep's sample count); the table below is the full-data upper bound, still within the approval.
| item | value |
|---|---|
| data | strong agent, development: Stage A gpt-6-luna (frozen + tracker), our and the partner's train runs; 1,396 conversations |
| calls | at most **22,070** (p8's dry run, upper bound) |
| model | gpt-6-luna, low effort; one call per (question, input), saved in `output/eval_v3/questions_answers.jsonl` |
| cost (estimate) | $1.24 / **$2.13** / $4.11 (low / point / high) |
| hard limit | **$13.24** (2 × count × $0.0003), plus a call limit of 24,287 (count + 10 %), enforced by the budget stop in `questions.py` |
| time | about 1-2 h with 8 workers (estimate; 6-12 h without step 0.1) |

**The sample run (counted by the prep, 12:40 UTC; `output/eval_v3/p12_prep_dryrun_dev_sample.md`):**
| item | value |
|---|---|
| data | the first 50 conversations of each of the 4 data sets: 200 conversations, 2,164 checks |
| calls | at most **3,425** (upper bound) |
| cost (estimate) | $0.19 / **$0.33** / $0.64 (low / point / high; scaled from the full count) |
| hard limit | **$2.06** (2 × count × $0.0003), plus a call limit of **3,768** (count + 10 %). With 8 workers, calls already running when the dollar stop fires still finish: up to about $0.02 over. Far under the approved $13.24 |
| time | about 10-20 min with 8 workers (estimate) |

Command (from `predicate_correctness/`; `<words>` = your approval words, copied):
```
PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m scoring.v3_p8_dryrun --answers real --approved "<words>" --max-usd 2.06 --max-calls 3768 --limit-convs 50 --workers 8 --out output/eval_v3/p12_answers_dev.md --datasets stage_a.luna.tgr_frozen,stage_a.luna.tgr_tracker,ours.p10_luna_train,partner.luna_train_v5 > output/logs/v3_p12_01_answers_dev.log 2>&1
```
(The full-data command, with `--max-usd 13.24 --max-calls 24287` and no `--limit-convs`, is not run.)
Then, $0: the bug check (P12.1 and the answer problems). If something fails, it is fixed on development data and
logged, and I tell you.

### p12b: hold-out, once (paid; it starts only after the bug check passes)
| item | value |
|---|---|
| data | the hold-out: 99 `p10_luna_val` + 99 partner `luna_val` + 8 Stage B tries forked from val; 206 conversations, 2,468 checks |
| calls | at most **3,284** (count from `--side holdout --count-only`, `output/eval_v3/p12_holdout_count.md`; no label or decision of the hold-out was read) |
| cost (estimate) | $0.18 / **$0.31** / $0.61 |
| hard limit | **$1.97** (2 × count × $0.0003), plus a call limit of 3,613 (count + 10 %) |
| time | about 10-20 min with 8 workers (estimate) |

Command:
```
PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m scoring.v3_p8_dryrun --side holdout --answers real --approved "<words>" --max-usd 1.97 --max-calls 3613 --workers 8 --out output/eval_v3/p12_answers_holdout.md > output/logs/v3_p12_02_answers_holdout.log 2>&1
```
Then, $0: p11's test on the hold-out, the tiny-vs-judge review, the independent recount, and the report. **STOP.**

### p12 total
- cost (estimate): about **$2.4** (point), high $4.7;
- hard limit **$15.21** (p12a + p12b), under the plan value of $26 and the v3 cap of $95;
- time: about 2-4 h, including the $0 checks.

### How to approve
You can approve one piece or several in one message. For example:
- "approve p12 step 0 with the 2 fixes" (or "without the fixes");
- "approve p12a";
- "approve p12b" (it still waits until the bug check passes).

Each run copies your words into `--approved`.

## Request 2: p14 B1, the smoke test (paid) — APPROVED 2026-10-23 13:16 UTC ("approve B1 after freeze")

**What:** 2 tasks (the first retail and the first airline task of `online_tasks.json`, try 1) × 5 arms = 10 live
conversations, strong agent (gpt-6-luna for every role), in its own folder. Not part of B2. It checks that the whole
paid pipeline works before the big run.

**Starts only when all of these hold** (checked and logged by the main chat):
1. v3 is frozen: p12b (the hold-out answers) has started, after the dev bug check passed;
2. the audit B and C fixes are in, all v3 tests pass, the equality check is byte-equal, and the sandbox dry run of
   this exact B1 command makes 0 calls (p13 step 7);
3. an independent check of the fixes finds 0 open blockers.

| item | value |
|---|---|
| conversations | 10 |
| cost (estimate) | about **$0.12** (high $0.48) |
| hard limit | **$2** (enforced by `guard/soft_stop_v3.py`), inside the v3 cap of $95 |
| time | about 15 min |
| pass (pre-registered, `preregistration_online.md` section 10) | 0 error lines (1 content-filter error allowed); mean cost ≤ 3 × the point; plus (audit C) Direct + facts' `facts_failure` = 0 and v3's `state_error` = 0 |

Command (from `predicate_correctness/`; the exact form is filled in after the fixes, and logged here before the run):
```
~/venvs/tau-bench/bin/python -B -m guard.run_online_v3 new-id --step B1 > output/logs/v3_B1_new_id.txt 2>&1
RUN_ID=$(cat output/logs/v3_B1_new_id.txt)
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 setsid nohup ~/venvs/tau-bench/bin/python -B -m guard.run_online_v3 run \
  --step B1 --run-id $RUN_ID --shard 0/1 --workers 5 \
  --approval "approve B1 after freeze" > output/logs/v3_B1_${RUN_ID}_s0.log 2>&1 &
```
After B1: a $0 check of spend, errors and the pass mark, a cost-log row, and then **stop**. **B2 is not approved.**

## Cost log
| date (UTC) | step | calls | cost (logged list price) | hard limit | note |
|---|---|---|---|---|---|
| 2026-10-23 11:50 | p12 (step 0, p12a, p12b) | — | — | $13.24 + $1.97 | **approved by the user**: "you can go with the plan runs" (reply to this request). p12b only after p12a's bug check passes. p14 not approved |
| 2026-10-23 12:42:44 | p12a started (sample: 200 conversations) | ≤ 3,768 | — | $2.06 | main chat; `--approved "you can go with the plan runs"`; log `output/logs/v3_p12_01_answers_dev.log` |
| 2026-10-23 12:54 | p12a done (200 dev conversations, 2,164 checks) | 2,726 | $0.1253 | $2.06 | exit 0; 0 errors; 0 network events outside the API; 12 min; 44 unclear answers (K13 16, K5 13, K4 8, K2 3, K1 2, K15 2); report `output/eval_v3/p12_answers_dev.md` |
| 2026-10-23 13:16 | p14 B1 (smoke, 10 conversations) | — | — | $2 | **approved by the user**: "approve B1 after freeze". Starts only after the freeze, the audit fixes and their checks (Request 2). B2 and later steps not approved |
| 2026-10-23 14:58:27 | p12 re-ask started (changed questions K2, K4, K5, K13 + newly reached keys; same 200 dev conversations) | ≤ 2,059 | — | $1.00 | main chat; approved with the fix: "implament the suggested fix, with the modification we disscussed now, lets go!"; inside p12's $13.24; log `output/logs/v3_p12_06_answers_dev_k2v2.log` |
| 2026-10-23 15:02 | p12 re-ask done (changed questions, same 200 dev conversations) | 1,157 | $0.0687 | $1.00 | exit 0; 0 errors; 3.5 min; unclear: K2 35, K13 8, K1 2, K15 2 (K4 and K5 0); report `output/eval_v3/p12_answers_dev_k2v2.md` |
| 2026-10-23 15:29:59 | p12 round-2 re-ask started (K2 lines changed for flight / passenger changes; same 200 dev conversations) | ≤ 873 | — | $0.48 | main chat; approved by the user: "1. Multi-piece quotes, 2. Only changed flights"; with the first re-ask ($0.0687) inside the $1 fix limit; log `output/logs/v3_p12_09_answers_dev_k2v3.log` |
| 2026-10-23 15:30 | p12 round-2 re-ask done | 76 | $0.0053 | $0.48 | exit 0; 0 errors |
| 2026-10-23 15:33:59 | p12b started (hold-out answers, 206 conversations) | ≤ 3,613 | — | $1.97 | main chat; after the freeze; log `output/logs/v3_p12_02_answers_holdout.log` |
| 2026-10-23 15:34:50 | **p14 B1 started** (run B1_20261023T153359Z_77ce4c14; 10 conversations) | — | — | $2 | main chat; `--approval "approve B1 after freeze"`; conditions met: freeze 15:33, audit fixes in, independent check 0 open blockers |
| 2026-10-23 15:40 | p12b done (hold-out answers, 206 conversations) | 2,559 | $0.1364 | $1.97 | exit 0; 0 errors; 7 min; unclear: K2 16, K13 7, K1 2, K8 2; report `output/eval_v3/p12_answers_holdout.md` |
| 2026-10-23 15:39 | **p14 B1 done** (run B1_20261023T153359Z_77ce4c14) | 10 conversations (93 judge calls, 26 tiny) | $0.1486 | $2 | **PASS** (pre-registered mark: 10 conversations, 0 error lines, mean $0.0149 ≤ $0.036, Direct + facts facts_failure 0, v3 state errors 0); summary `output/eval_v3/B1_B1_20261023T153359Z_77ce4c14_summary.md`; v3 total $0.48 of the $95 cap |
| 2026-10-23 15:56:00 | **p14 B2 started** (run B2_20261023T155537Z_c842d895; 1,485 conversations; 4 shards × 8 workers; original pre-registered stops) | — | — | $45 | **approved by the user**: "Yes, start B2 now (Recommended)" (after the stop change was blocked by the permission system); dry runs 0 calls; freeze hashes match; spend before $0.484 |
| 2026-10-23 16:54:53 | **p14 B2 done** (run B2_20261023T155537Z_c842d895; 1,485 conversations) | 1,485 conversations (judge 10,450 calls metered) | $15.7568 | $45 | exit 0; 0 error lines, 0 dropped, no stop; **main claim PASS** (v3 − frozen −0.024 [−0.088, +0.040]); leak check: possible leak; safety 0; v3 total $16.24 of the $95 cap; report `docs/reports/tracker_v3_report.md` |
| 2026-10-23 19:08:09 | **p14 B3 started** (run B3_20261023T190740Z_9bf882c0; 64 Stage A retail tasks × 1 try × 5 arms = 320 conversations; 4 shards × 8 workers; B2's stops, halfway 160) | — | — | $20 | **approved by the user**: "Approve build + B3 run (Recommended)" (build and run, request `approval_request_B3_draft.md`, 17:25); build applied 19:06 (patch e93c3645…), 114 tests pass, tasks file equal to a fresh build, dry run 0 calls in all 4 shards; spend before $16.24 |
| 2026-10-23 19:21:03 | **p14 B3 stopped** by the pre-registered harm rule (halfway check: v3 − frozen −0.243 on 37 complete groups ≤ −0.15); STOP file written by the main chat | — | — | $20 | open groups finish; spend and final lines when the processes end |
| 2026-10-23 19:24:47 | **p14 B3 done** (stopped by the harm rule; run B3_20261023T190740Z_9bf882c0) | 245 lines = 49 complete tasks × 5 arms (15 tasks not started; judge 3,086 calls metered) | $5.2484 | $20 | 0 errors, 0 dropped; v3 − frozen **−0.245 [−0.408, −0.061]: not shown** (side result, seen tasks); S2 rules worse; safety 0 of 127; independent recompute matches; v3 total $21.49 of $95 |
