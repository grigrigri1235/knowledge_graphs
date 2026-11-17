# Tracker Evaluation v2 Plan - Overview (500 extra tasks + fork test)

> **STOP BEFORE REAL MONEY. Urgent rule from the user (2026-10-22, 10:15 UTC). 0 violations allowed.**
> No agent and no command may make a paid LLM call (agent, simulated user or judge; gpt-6-luna or gpt-5-nano) until
> the user gives a new, explicit approval for that exact step in the chat. The earlier approval of the plan's cost
> no longer counts. Work without money may go on: code, tests with fake LLMs, dry runs with the network blocked,
> checks. Stop JUST BEFORE the first paid call, write down what would run (commands, conversations, cost, time), and
> wait. The approval request goes in `docs/planning/tracker_eval_v2/approval_request.md`.


Date 2026-10-22. **Status: STOPPED by the user at 19:25 UTC, during Part 8 (Stage B, 619 of 1,750 tries done), to
improve the method first. Total spend $40.38. Report: `docs/reports/tracker_eval_v2_report.md`.** Parts 1-7 done;
Part 8 stopped; Parts 9-10 replaced by that report. The kickoff message in `HANDOFF.md`
approves the work without money only. **Every paid step needs a new, explicit approval from the user** (see the box
above and "Approval gate" below). This plan replaces `docs/planning/retail500_exp/` and
`docs/planning/fork_test_exp/`, which were merged into it.

**New chat or new agent? Read `HANDOFF.md` first.** It has the context, the commands, the rules, the known problems,
and a kickoff message.

## Objective
Find out how much the tracker changes task success, with two measurements that support each other:
- **Stage A, more tasks:** run frozen TGR and "TGR + tracker" side by side on τ-bench's 500 extra retail tasks.
- **Stage B, fork test:** at every step where the two guards disagree, continue the conversation both ways, several
  times each, and compare the outcomes.

## Why
- In the earlier online test (`docs/reports/state_tracking_final_report.md`, sections 5.3 and 7), we compared two
  separate runs. The agent and the simulated user answer differently every time, so task success moved by up to about
  0.08 by chance.
- The tracker changes a decision in only about 5–8 % of conversations. Where it removes a wrong block, the task gets
  done far more often (30 % with a wrong block against 64 % without, in the saved conversations). Overall, though,
  this is only about +0.02, which is hidden in the noise.
- The two stages attack the noise in two ways:
  - **Stage A:** 10 times more tasks, and both guards run in the same period. The range shrinks from about ±0.08 to
    about ±0.035.
  - **Stage B:** no noise before the decision, because both branches share the same conversation up to the fork. It
    measures the effect of each changed decision directly.
- **They fit together:** Stage A gives Stage B many new fork points. Stage B explains Stage A's number: effect per
  fork × how often forks happen ≈ the overall effect. If the two estimates agree, the result is solid.

```text
Stage A: 500 extra tasks ── frozen TGR ─────────┐
                         └─ TGR + tracker ─────┤──► paired difference in task success (by task)
                                                │
fork points (from saved runs, earlier runs, Stage A)
                                                ▼
Stage B: fork point ─┬─ branch A: TGR decision ──► 5 tries ─┐
                     └─ branch B: tracker decision ─► 5 tries ┴──► effect per fork
                                                                  × fork rate ──► overall effect
```

## Which tasks
- **Stage A:** τ-bench's 500 extra retail tasks, from its own training set (`tasks_train.py`).
  - Neither my partner's work nor ours has used them.
  - They are not the "train" tasks of our earlier reports, which were part of τ-bench's 115 retail test tasks.
  - Same policy, tools and database, so the frozen rules and our lookups apply unchanged.
  - Airline has no extra tasks, so Stage A is retail only.
- **Stage B fork points come from three sources:**
  1. my partner's saved frozen TGR conversations (our train group, both agents);
  2. our earlier "TGR + tracker" conversations (train and validation, both agents);
  3. the Stage A conversations (both guards, both agents).

  My partner's test group is never used.

## Simplifying assumptions
| we assume | why this is acceptable |
|---|---|
| τ-bench's extra tasks are of similar quality to its test tasks. | Same benchmark, policy and data. Part 1 looks at a sample. |
| Our gold scorer works on the extra tasks. | Its checks are policy rules on actions, not on a task. Part 1 checks it on a sample. |
| 1 try per task in Stage A. | We use 500 tasks instead of more tries. Stage B adds 5 tries where it matters. |
| The simulated user's next reply depends only on the messages it has seen. | That is how τ-bench's simulated user works: its only state is its message list. |
| We can rebuild the database at a fork point by replaying the executed tool calls. | Shown in the earlier plan: the replay was exact for 2,891 of 2,891 calls. |
| A fork at the first differing step of a conversation is enough. | Later differences happen inside each branch on their own, because each branch keeps its own guard. |

## Cost
- **Stage A:** about $35 in total.
  - strong agent: 1,000 conversations, about $12.5;
  - weak agent: 1,000 conversations, about $22.
- **Stage B:** about $15–25, for an estimated 200–300 fork points × 2 branches × 5 tries. A branch continues only part
  of a conversation.
- **No money is spent without a new, explicit approval from the user for that step** (urgent rule, 10:15 UTC). The
  numbers here are estimates for the approval request, not an approval.
- **Total limit: $100, as a soft stop** (inside what the user approves).
  - When the total spend reaches $100, we estimate the cost of the work that is left.
  - If that is $30 or less (close to finishing), we finish, and write down the final total.
  - If it is more, we stop and report what was done.
- **Before Stage B starts:** if the Stage B projection plus the spend so far is above $100, we take a fixed-seed sample
  of the fork points, spread over kinds and agents, and write down what was left out.

## Ground rules
- Nothing in `~/ShieldAgent` is changed. We use our copies and wrapper in `predicate_correctness/`.
- All output goes under `predicate_correctness/output/eval_v2/`. Command output goes to
  `predicate_correctness/output/logs/` (prefix `v2_`).
- Only gpt-6-luna and gpt-5-nano, with the profiles `luna-dev` and `nano-agent-luna`. No grok-4.7. Never my partner's
  test group.
- **STOP BEFORE REAL MONEY: no paid LLM call without a new, explicit approval from the user for that exact step.**
  Stop just before the first paid call, write `approval_request.md` (what runs, how many conversations, cost, time,
  commands), and wait. A dry run counts as paid unless the network is blocked and 0 calls are counted.
- An independent agent audits all new code before any money is spent (Part 4), and checks everything at the end
  (Part 10).
- After each part: update this file and say "done with part i".

## Folder layout
```text
predicate_correctness/
├── guard/                      wrapper (extended: extra tasks, frozen TGR side by side, cost limit)
├── fork/                       fork code: find points, rebuild, run a branch
├── tests/                      test_eval_v2_*.py
└── output/eval_v2/
    ├── checks/                 Part 1 checks
    ├── stage_a/<agent>/<guard>/episodes.jsonl
    ├── fork_points.jsonl       Part 7
    ├── stage_b/<fork id>/<branch>/<try>.json
    └── metrics.md / metrics.json
```

## Execution sequence
- **Part 1 (`p1.md`):** Checks: the 500 tasks, the scorer, the runner, the conversation formats (no LLM) [Done]
  Result: 500 tasks (index 0–499), 0 overlap with the test tasks, gold scorer v2 0 errors, formats checked on 990
  saved conversations (replay 7,168 of 7,168, reward 976 of 976). The extra tasks are templated and easier. Estimate:
  Stage A $35, Stage B $27 (about 233 forks). Details: `predicate_correctness/output/eval_v2/checks/part1.md`.
- **Part 2 (`p2.md`):** Extend the wrapper for Stage A (no LLM) [Done] Wrapper runs the 500 extra tasks with both guards side by side, 4 shards, own judge cache per guard, soft stop; 251 tests pass; dry runs 0 LLM calls.
- **Part 3 (`p3.md`):** Fork code: find points, rebuild, run a branch (no LLM; fake-LLM tests) [Done] 55 fork points from saved runs, all pass the rebuild checks; branch runner with fake-LLM tests; dry run on 55 forks OK.
- **Part 4 (`p4.md`):** Independent audit of Parts 2–3 before spending [Done] 5 independent auditors + 3 independent
  reference builders; 1 blocker (thread race) and 1 fairness fix (judge cache seeded at the fork) and about 16 small
  issues found and fixed; re-audit passed. Details: `predicate_correctness/output/eval_v2/checks/audit.md`.
- **APPROVAL RECEIVED (13:47 UTC):** the user approved the paid steps of this plan (Parts 5, 6 and 8) inside the $100
  soft stop. See `approval_request.md` for the exact scope. The "track more facts" idea is not approved.
- **APPROVAL GATE (no money before it):** after Part 4, all paid steps are prepared without money (commands, dry runs
  with the network blocked, cost, time) and written to `approval_request.md`. **Everything stops there** until the user
  approves. Each later paid step (Part 5, Part 6 strong, Part 6 weak, Part 8) also waits for its own approval, unless
  the user's approval names it.
- **Part 5 (`p5.md`):** Smoke test for both stages [Done] 10 of 10 Stage A conversations and 6 of 6 Stage B tries
  finished and scored, 0 errors, nothing written outside; spend $0.16; projected total about $53 (cautious $64), under
  $100, so no fork sampling. Details: `predicate_correctness/output/eval_v2/checks/smoke.md`.
- **Part 6 (`p6.md`):** Stage A runs (strong agent, then weak agent) [Done] both runs 1,000 of 1,000 finished (strong: 1
  error resumed; weak: 0 errors); raw success frozen/tracker: strong 419/432, weak 376/356 of 500; cost $11.27 + $21.50;
  spend $32.93. Details: `predicate_correctness/output/eval_v2/stage_a_runs.md`.
- **Part 7 (`p7.md`):** Fork points from all sources [Done] 175 fork points (saved 55, Stage A luna 28, Stage A nano
  92; luna 44, nano 131; block removed 143, added 32), all pass the rebuild checks, 0 dropped; fork rate Stage A luna
  2.8 % per guard, nano 8.6 % / 9.8 % (frozen / tracker runs); judge's view cut at the fork in 107; Stage B projected
  $19.1 (cautious $22.3), total about $52 (cautious $55), no sampling; dry runs OK (0 calls). Launch plan for the main
  chat (4 processes): `predicate_correctness/output/eval_v2/stage_b_launch.md`. Details:
  `predicate_correctness/output/eval_v2/fork_points.md`.
- **Part 8 (`p8.md`):** Stage B runs [**Stopped** by the user at 19:25 UTC: 619 of 1,750 tries, $7.45; started by the
  main chat at 18:41, paused at 19:02, stopped at 19:25. The runner can resume these tries later.]
- **Part 9 (`p9.md`):** Metrics for both stages, and the combined estimate [Not started]. Added on the user's request
  (no money): the effect **by conversation length** (p9.md items 11-14). A fixed view always cuts something in a long
  conversation, while the tracker's state does not depend on length, so its gain should grow with length.
- **Part 10 (`p10.md`):** Report and final independent check [Replaced: the user stopped the experiment and asked for
  a report: `docs/reports/tracker_eval_v2_report.md`. No independent final check was run.]

## Open questions
- What does "deploy" mean in `CLAUDE.md` rule 5?
- **For the approvers: track more facts with code?** The tracker sets 31 of the 66 predicates with code, which hold
  about 1/3 of the values the judge gives. The other 2/3 stay with the judge: mostly facts about what messages mean
  ("the user confirmed", "the agent listed the details"). They give about 65 % of the values behind blocks. Should
  this plan also find a way to set some of them with code (or with narrow, checkable questions), before or after the
  paid runs? A first proposal, with no code and no money, is in `idea_track_more_facts.md`. It is an option for the
  approvers, not part of the approved work.
