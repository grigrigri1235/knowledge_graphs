# Orchestration notes (main chat)

> **STOP BEFORE REAL MONEY. Urgent rule from the user (2026-10-22, 10:15 UTC). 0 violations allowed.**
> No agent and no command may make a paid LLM call (agent, simulated user or judge; gpt-6-luna or gpt-5-nano) until
> the user gives a new, explicit approval for that exact step in the chat. The earlier approval of the plan's cost
> no longer counts. Work without money may go on: code, tests with fake LLMs, dry runs with the network blocked,
> checks. Stop JUST BEFORE the first paid call, write down what would run (commands, conversations, cost, time), and
> wait. The approval request goes in `docs/planning/tracker_eval_v2/approval_request.md`.


Date 2026-10-22. How the main chat runs the plan. The plan itself is in `overview.md` and `p1.md`–`p10.md`.

## Change (15:40 UTC): the main chat starts every paid run
- In a subagent, the Claude Code permission check refused the paid Stage A start ("Real-World Transactions"): a
  subagent cannot show the user's approval. The user chose: **the main chat starts each approved paid run** (Part 6
  strong, Part 6 weak, Part 8, and any resume of them). Agents do only the no-money work: checks, waiting, reports.
- A no-money loop adds an "auto:" line to `output/eval_v2/progress.md` every 10 minutes
  (`scoring/v2_progress_tick.py`; stop it by creating `output/logs/v2_progress_tick.stop`).

## Change (user request, 10:15 UTC): STOP BEFORE REAL MONEY
- The running workflow (fix-and-smoke) was stopped at 10:16, before its smoke step, with $0.00 spent. It is resumed
  without the paid smoke step: fixes → re-audit → close Part 4 → **prepare** Part 5 (no money) → write
  `approval_request.md` → stop.
- Every agent prompt from now on carries the stop rule word for word. Paid steps (Part 5, Part 6 strong, Part 6 weak,
  Part 8) each wait for the user's own approval in the chat.
- New option for the approvers: track more of the facts that stay with the judge (`idea_track_more_facts.md`).

## Change (user request, 08:2x): 5-6 agents at once
- The Workflow tool runs at most 2 agents at once on this VM (4 CPUs - 2). The user wants at least 5-6, since most
  agent work is reading files and waiting.
- So: Part 1 finishes in workflow 1. Then workflow 1 is stopped, and the main chat starts agents directly with the
  Agent tool, 5-6 at once.

## Wave plan
1. **Part 1:** one agent (already running in workflow 1).
2. **Build wave, 6 at once:**
   - **B1, Part 2:** wrapper, `guard/soft_stop.py`, tests, dry run. Owns `guard/`, `tests/test_eval_v2_wrapper.py`.
   - **B2, Part 3a:** `fork/find_points.py`, `fork/rebuild.py`, the rebuild checks. Owns those files,
     `tests/test_eval_v2_points.py` and `checks/rebuild.md`.
   - **B3, Part 3b:** `fork/run_branch.py`, `fork/run_all.py`, fake-LLM tests. Owns those files,
     `tests/test_eval_v2_fork.py` and `tests/test_no_gold_import.py`.
   - **R1, R2, R3: independent references for the audit.** They wrote none of the code, and read none of the new code.
     Their scripts go in `tests/audit_v2_ref_*.py`, and their outputs in `output/eval_v2/checks/ref/`.
     - R1: their own list of fork points (sources 1 and 2).
     - R2: their own rebuild of a sample of fork points.
     - R3: their own list of Stage A tasks, plus frozen TGR's prompt and decisions on a sample.
   - The interface between B2 and B3 is fixed in `fork/schema.py`, written by the main chat before the wave (not
     `types.py`: that name would hide Python's own `types` module).
3. **Scribe:** updates `overview.md` and the log for Parts 2-3, and runs all tests.
4. **Part 4 audit, 5 clean auditors at once,** each with one lens:
   - Stage A tasks and guards;
   - fork points against R1;
   - rebuild against R2;
   - Stage B fairness;
   - safety, the soft stop and the tests.

   Then a merge step writes `audit.md`. If something blocks: a fixer, then a new re-auditor.
5. **Part 5 smoke:** a Stage A agent and a Stage B agent at once, then one checker.
6. **Runs:** Part 6, then Parts 7-8 (fork points from sources 1-2 can start during Stage A).
7. **Analysis:** Part 9 split three ways (Stage A, Stage B, combined), the Part 10 report, then 5 clean final checkers
   at once.

## Shared choices given to the subagents
- **Soft stop module** `guard/soft_stop.py` (owned by Part 2; Part 3 uses it):
  - spend = all LLM cost recorded under `output/eval_v2/` (Stage A episodes, Stage B tries, smoke);
  - at $100 or more: go on only if the estimated cost left is $30 or less.
- **Stage B try files** have a top-level `cost_usd`, so the soft stop can add them up.
- **Agents running at once never edit the same file.** Only the scribe and the merge steps edit `overview.md` and
  the log.
- **"Done with part i"** is said by the main chat after each part.
- **The $100** counts only the LLM spend of the runs (gpt-6-luna, gpt-5-nano), not the cost of the subagents.
- **The runners' soft stop sees only their own job's "work left"** (audit A2, W1). So before each job (smoke, Stage A
  luna, Stage A nano, Stage B), the main chat checks: spend so far + this job + every later job. If that is above
  $100, apply the overview's rule (sample before Stage B) before starting.
- **Before any spend:** no `output/eval_v2/_audit_*` or `_tmp*` folder may exist (the soft stop would count their fake
  costs; audit A2, W2). Check `guard/soft_stop.spent_report()["by_file"]`.
- **Always `--shard i/4`** for Stage A (a different n could repeat units; A2, W3). Wait loops also check that each
  process is alive (A2, W4).
