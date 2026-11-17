# DRAFT, NOT APPROVED: Request 3, p14 B2, the main paid run

> **DRAFT. Not approved. Not part of `approval_request.md` yet.** Written before B1 ran ($0 prep); the cost lines
> were updated after B1 passed (2026-10-23 15:47 UTC). It is copied into `approval_request.md` as Request 3 when you
> decide. **Nothing here runs without your new, explicit
> approval for B2**, given in the chat. Approval of B1 or of this plan does not count.

## What it does
The main test. The strong agent (gpt-6-luna for every role) runs the 99 hard tasks (val 33 + train 66) × 3 tries ×
5 arms (no guard, Direct, Direct + facts, frozen TGR, v3) = **1,485 live conversations**, paired by task. It answers
the pre-registered question: is v3 clearly worse than frozen TGR? (`preregistration_online.md`; the rules do not
change.)

## Starts only when
1. B1 passed its pre-registered pass mark (`b1-check` and `scoring/v3_b1_summary.py` say PASS), and its cost-log row
   is written;
2. no code under the pre-registration changed since B1 (same sha256s as in B1's `run.json`);
3. the spend so far plus B2's hard limit stays under the $95 cap (the runner checks this too).

## Numbers
| item | value |
|---|---|
| conversations | 1,485 (99 × 3 × 5), 4 shards, 6 workers each |
| cost (estimate) | **about $16-22**: p14.md's point $16.4; B1's measured costs project **$22.06** (no guard $2.43, Direct $6.38, Direct + facts $4.69, frozen TGR $5.33, v3 $3.23; rough: 2 conversations per arm) |
| hard limit | **$45** (`guard/soft_stop_v3.py`; a new group starts only if spend + reserve stays under it) |
| v3 cap | **$95**, counting p12 and every p14 step |
| spent so far (cost log) | p12a $0.1253; fix re-asks $0.0687 + $0.0053; p12b $0.1364; B1 $0.1486; total **$0.484**. The live check ($0, 15:47 UTC) gives the same: $0.4843 (questions $0.3357, episodes $0.1486, backups $0). With B2's $45 limit: at most $45.48, under the $95 cap |
| time | about **1.5-2.5 h** |
| the real bill | about 0.55× the logged list price |

Live spend check ($0, before you approve; output to a file):
```
cd /home/azureuser/code_projects/predicate_correctness
PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -c "from guard import soft_stop_v3 as S; r=S.v3_spend(); print({k: r[k] for k in ('total_usd','questions_usd','episodes_usd','backups_extra_usd','dryrun_usd_not_counted')})" > output/logs/v3_B2_spend_before.txt 2>&1
```

## Stops (pre-registered, `preregistration_online.md` section 9; lenient on purpose)
A stop starts no new (task, try) group; open groups finish all 5 arms, so pairs stay complete.
- **Harm at halfway:** at 742 conversations in complete groups, v3 − frozen TGR ≤ −0.15 (the main chat runs the
  interim check below).
- **State errors:** the 3rd v3 check with an exception in the fact code (the runner stops itself).
- **Cost:** an arm's mean cost per conversation, after 50 of its conversations, over 3 × its high estimate (none
  $0.023, Direct $0.044, Direct + facts $0.049, frozen TGR $0.041, v3 $0.061); or one conversation over $0.25.
- **Errors:** 10 or more error lines that are also over 5 % of lines, or 5 error lines in a row.
- **Money:** the $45 hard limit and the $95 cap.
- **Manual:** the file `STOP` in the run folder.

## Commands (from `predicate_correctness/`; `<words>` = your approval words, copied exactly)
Run id (output to a file):
```
~/venvs/tau-bench/bin/python -B -m guard.run_online_v3 new-id --step B2 > output/logs/v3_B2_new_id.txt 2>&1
RUN_ID=$(cat output/logs/v3_B2_new_id.txt)
```
Dry run first ($0, no call; one per shard, each to its own log):
```
for i in 0 1 2 3; do PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 ~/venvs/tau-bench/bin/python -B \
  -m guard.run_online_v3 run --step B2 --run-id $RUN_ID --shard $i/4 --workers 6 \
  --approval "<words>" --dry-run > output/logs/v3_B2_${RUN_ID}_dryrun_s$i.log 2>&1; done
```
The paid run (4 processes, one process group each):
```
for i in 0 1 2 3; do PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 setsid nohup ~/venvs/tau-bench/bin/python -B \
  -m guard.run_online_v3 run --step B2 --run-id $RUN_ID --shard $i/4 --workers 6 \
  --approval "<words>" > output/logs/v3_B2_${RUN_ID}_s$i.log 2>&1 & done
```
- Run folder: `output/eval_v3/B2/$RUN_ID/`. Run id: **`<RUN_ID, filled in at start>`**.
- Approval words: **"`<your approval words for B2>`"**.

## During the run
- Find the processes: `ps -eo pid,pgid,etimes,cmd | grep '[r]un_online_v3' > output/logs/v3_B2_${RUN_ID}_ps.txt 2>&1`
  (never a bare `pgrep -f`).
- `output/eval_v3/progress.md` gets an "auto:" line every 10 minutes.
- **Halfway interim check** ($0, main chat; run it when about 742 conversations are done, and again later):
  ```
  PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 /home/azureuser/miniconda3/bin/python3 -B -m scoring.v3_online_interim \
    --run-dir output/eval_v3/B2/$RUN_ID > output/logs/v3_B2_${RUN_ID}_interim.log 2>&1
  ```
  Its last line says `STOP` or `go on`. On `STOP`: write the STOP file (below) and tell you.

## How to stop and resume
- **Pause:** `kill -STOP <pid>` (resume a pause with `kill -CONT <pid>`).
- **Stop (normal):** `touch output/eval_v3/B2/$RUN_ID/STOP`. No new group starts; open groups finish all 5 arms.
- **Emergency only:** `kill -TERM -<pgid>`. It loses the cost lines of running conversations.
- **Resume:** first **copy** (`cp`, never `mv`) each shard file to `*.jsonl.before_resume`; the live file must stay,
  because its lines are the spend so far (the runner refuses a moved backup). Then run the same paid command again
  with the same `$RUN_ID`. Only one process per shard (a lock file); never start a second one on a paused shard.
  ```
  for f in output/eval_v3/B2/$RUN_ID/*/episodes_shard*of4.jsonl; do cp -p "$f" "$f.before_resume"; done
  ```

## After B2 ($0)
1. Metrics and the report:
   ```
   PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 /home/azureuser/miniconda3/bin/python3 -B -m scoring.v3_online_metrics \
     run --run-dir output/eval_v3/B2/$RUN_ID --out output/logs/v3_B2_${RUN_ID}_metrics.json \
     > output/logs/v3_B2_${RUN_ID}_metrics.log 2>&1
   PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 /home/azureuser/miniconda3/bin/python3 -B -m scoring.v3_p14_report \
     --metrics-json output/logs/v3_B2_${RUN_ID}_metrics.json > output/logs/v3_B2_${RUN_ID}_report.log 2>&1
   ```
   This writes `docs/reports/tracker_v3_report.md` and `docs/reports/figures/v3_online_{success,paired}.png`.
2. A cost-log row in `approval_request.md`.
3. The numbers recomputed by an independent agent.
4. Then **stop**. B3 (optional, only if B2 is unclear) needs its own approval.

## How to approve
Say it in the chat, for example: "approve B2". Your exact words go into `--approval`.

**DRAFT, NOT APPROVED.**
