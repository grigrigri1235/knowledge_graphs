# Approval: paid steps of tracker eval v2

## Approval received
- **When:** 2026-10-22, 13:47 UTC, in the chat. The user wrote: "continue with the plan, we have got it approved the
  part with money use".
- **What it covers:** the paid steps of this plan, inside the $100 soft stop (at $100, finish only if $30 or less is
  left):
  - Part 5, the smoke test;
  - Part 6, Stage A: strong agent, then weak agent;
  - Part 8, Stage B.
- **What it does not cover:** anything outside these three parts. In particular, the "track more facts with code"
  proposal (`idea_track_more_facts.md`, parts M1-M6) is not approved and does not start.
- **The stop rule stays** for anything outside this scope (box at the top of every plan file).

## Money before the approval
$0.00. No paid LLM call ran before 13:47 UTC.

## Estimated cost (from `predicate_correctness/output/eval_v2/checks/part1.md`, section 6)
| step | what runs | est. cost |
|---|---|---|
| Part 5 smoke | 5 tasks × 2 guards; 3 fork points × 2 branches × 1 try | about $0.1-1 |
| Part 6 strong | 500 tasks × 2 guards × 1 try, luna-dev | about $12.5 |
| Part 6 weak | 500 tasks × 2 guards × 1 try, nano-agent-luna | about $22.8 |
| Part 8 | about 233 fork points × 2 branches × 5 tries | about $27 |
| **total** | | **about $63** |

The smoke test (Part 5) measures the real cost per conversation. Before each later paid step, the main chat checks:
spend so far + that step + all later steps. If that is above $100, it applies the plan's rule (sample the fork points
before Stage B) and writes it down here.

## Check before each paid step
| step | spend before | projected total | started (UTC) | note |
|---|---|---|---|---|
| Part 5 smoke | $0.00 | about $63 | 14:35 | done: cost $0.1624 (Stage A $0.1010, Stage B $0.0614); `predicate_correctness/output/eval_v2/checks/smoke.md` |
| Part 6 strong | $0.1624 (15:07, `soft_stop.spent_report()`, agent R6S; by_file: only the smoke files) | $0.16 + $10.1 (cautious $12.5) + weak $18.4 ($22.8) + Part 8 $24.7 ($28.7) = about $53 (cautious $64), under $100 | **15:42:47** (by the main chat) | **done (16:29:49; resume of 1 unit 16:31:37-16:32:35): 500 tasks x 2 guards, all finished; run cost $11.27 ($0.01127 per conversation); spend after $11.43 (`soft_stop.spent_report()`, without the weak run); 1 error (task 440, `tgr_tracker`, Azure content filter on a judge prompt), resumed once, OK; check by agent C6S (no LLM call): `predicate_correctness/output/eval_v2/stage_a_runs.md`.** Before: **blocked 15:09 UTC in a subagent:** the Claude Code permission check refused the start command (reason "Real-World Transactions"); 0 processes started, 0 spent. **15:40 UTC: the user chose "the main chat starts each paid run"**; the main chat started it at 15:42:47 (spend before $0.1624, no runner alive, `stage_a/` new). Plan: 4 processes x 8 workers, about 50 min; passed `--later-left-usd 51` (cautious later cost, as the task said); preflight: no `_audit_*`/`_tmp*` folder, no runner alive, disk 11 GB free, `stage_a/luna/` new |
| Part 6 weak | $11.43 ($11.4326 in each run file's soft-stop reading at start; without the weak run) | $11.43 + weak about $20.5 (cautious $22.8) + Part 8 $24.7 ($28.7) = about $57 (cautious $63), under $100 | **16:34:10** (by the main chat, after a dry run with the network blocked and 0 LLM calls, `output/logs/v2_stage_a_nano_dry.log`) | **done (18:13:00): 500 tasks x 2 guards, all finished, 0 errors, no resume; run cost $21.50 ($0.0215 per conversation); spend after $32.93 (`soft_stop.spent_report()`, 18:18 UTC); 4 processes x 8 workers, 99 min; `--later-left-usd 29`; check by agent C6W (no LLM call): `predicate_correctness/output/eval_v2/stage_a_runs.md`.** Projection now: $32.93 + Part 8 $24.7 (cautious $28.7) = about $58 (cautious $62), under $100 |
| Part 8 | $32.93 (18:32 UTC, `soft_stop.spent_report()`, agent P7B; 26 files: smoke 10, Stage A luna 8, Stage A nano 8; no `_audit_*`/`_tmp*` files) | $32.93 + Part 8 $19.08 (175 forks x 2 branches x 5 tries = 1,750 tries: luna 440 x $0.00478 = $2.10, nano 1,310 x $0.01296 = $16.98; cautious nano $0.0154: $22.28) = **about $52.0 (cautious $55.2), under $100: no sampling** | **to be started by the main chat** | prepared by agent P7B (no LLM call): 175 fork points (`predicate_correctness/output/eval_v2/fork_points.jsonl`), all pass the rebuild checks; plan: 4 processes x 8 workers (1 luna, 3 nano; disjoint `--ids` lists; `--later-left-usd` 21 / 16 / 16 / 16), about 2.3 h; dry runs of the 4 exact commands: all forks OK, 0 problems, network attempts 0, nothing written. Commands and checks before the start: `predicate_correctness/output/eval_v2/stage_b_launch.md`  **Started 18:41:04 by the main chat; paused 19:02 (user); stopped 19:25 (user): 619 of 1,750 tries, cost $7.45; total spend $40.38.** |
