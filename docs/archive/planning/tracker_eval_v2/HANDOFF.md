# HANDOFF: start here (for a new chat or a new agent)

> **STATUS (2026-10-22, 19:40 UTC): this plan is STOPPED.** The user stopped it during Stage B to improve the method
> first. Do not resume it unless the user asks. **A new agent should start with `knowledge_retention.md`** (repo
> root): its last section has the prompt for the next step. Results: `docs/reports/tracker_eval_v2_report.md`. The text
> below is the plan as it was written and run.

> **STOP BEFORE REAL MONEY. Urgent rule from the user (2026-10-22, 10:15 UTC). 0 violations allowed.**
> No agent and no command may make a paid LLM call (agent, simulated user or judge; gpt-6-luna or gpt-5-nano) until
> the user gives a new, explicit approval for that exact step in the chat. The earlier approval of the plan's cost
> no longer counts. Work without money may go on: code, tests with fake LLMs, dry runs with the network blocked,
> checks. Stop JUST BEFORE the first paid call, write down what would run (commands, conversations, cost, time), and
> wait. The approval request goes in `docs/planning/tracker_eval_v2/approval_request.md`.


Date 2026-10-22. This file has everything a new chat needs to implement this plan without the earlier conversation.
Read it fully, then `overview.md`, then `p1.md` … `p10.md`.

## 1. The one-paragraph story
`~/ShieldAgent` (my partner's code; never change it) tests guards for LLM agents on τ-bench (customer-service
conversations, airline and retail). TGR is my partner's guard: an LLM writes rules over predicates once per policy,
and at every action an LLM "judge" sets the predicate values. We built a **tracker** that sets 31 of the 66 predicate
values with code instead: it replays the tool calls on a copy of τ-bench's database, and runs a one-line lookup per
predicate. The tracker is more accurate than the judge (right in 213 of 216 reviewed disagreements). But in new
conversations, its effect on task success was too small to measure, because the noise between separate runs is larger
than the effect. This plan measures it properly:
- **Stage A:** both guards side by side on 500 unused retail tasks;
- **Stage B:** a fork test at every step where the two guards disagree.

## 2. Read these first (in this order)
1. `docs/reports/state_tracking_final_report.md`: the idea, the assumptions and the results so far (short).
2. `docs/planning/state_tracking_exp/overview.md`: the earlier plan. It defines the rolling state, fact/shown, the
   types and the lookups.
3. `predicate_correctness/state_tracker/README.md`:
   - the saved-run format;
   - the step records;
   - the State API;
   - the lookup format;
   - replay, decide again.
4. `predicate_correctness/guard/run_online.py` (docstring) and `guard/tgr_tracker.py` (docstring): the wrapper and
   the guard used in the online test.
5. `predicate_correctness/output/p10_paths.md`: every path the copied runner reads or writes.
6. `predicate_correctness/output/implementation_log.md`: what every earlier part did, with its open issues (long;
   search it as needed).

## 3. Rules (from `CLAUDE.md` and the earlier work)
- **STOP BEFORE REAL MONEY (urgent, 2026-10-22 10:15 UTC, 0 violations).** The kickoff message (section 8) approves
  only the work without money. **No paid LLM call (agent, simulated user, judge) may run until the user gives a new,
  explicit approval for that exact step in the chat.** Stop just before the first paid call, write
  `docs/planning/tracker_eval_v2/approval_request.md`, and wait. Tell every subagent this rule, word for word, and
  that its own step has no money in it unless the user's new approval names that step.
- **Approval received 2026-10-22 13:47 UTC** for the paid steps Part 5, Part 6 (strong, then weak) and Part 8, inside
  the $100 soft stop (`approval_request.md`). Nothing else paid is approved.
- Inside what the user approves, the cost limit is a $100 soft stop: at $100, finish only if $30 or less is left.
  Tell subagents which part is theirs (`CLAUDE.md` rule 3).
- **Never write anything under `~/ShieldAgent`,** `~/opt/tau-bench-59a200c` or `~/venvs`.
  - Use `GIT_OPTIONAL_LOCKS=0` for any git command in `~/ShieldAgent`.
  - Our copies are from commit `1bacdb0`. My partner has committed since (HEAD `7e6575b`). That is fine: we use our
    copies.
- **Every shell command writes its output to a file** under `predicate_correctness/output/logs/` (prefix `v2_`), and
  is then read with the Read tool (`CLAUDE.md` rule 8).
- **Only gpt-6-luna and gpt-5-nano,** with profiles `luna-dev` and `nano-agent-luna`. Never grok-4.7. Never my
  partner's **test** group (`from_shieldagent/splits/splits.json`, label "test").
- **Gold code** (`from_shieldagent/gold/`, `from_shieldagent/scoring/`, `predicate_correctness/scoring/`) is for
  scoring only. `guard/`, `state_tracker/` and the new `fork/` must never import it; `tests/test_no_gold_import.py`
  checks this, so extend it to `fork/`.
- **Frozen inputs, do not change:**
  - lookups: `state_tracker/lookups_airline.json` and `lookups_retail.json`;
  - types: `output/predicate_types.json`;
  - rules: `from_shieldagent/rules/`.

  Their sha256 are in `guard/tgr_tracker.py` (`FROZEN_SHA256`), and the guard refuses to start if one differs.
- **Copies in `from_shieldagent/` are never edited.** Wrappers go in our own folders.
- **Simple, short language** in every document and report (`CLAUDE.md` rule 4).
- **No git commit or push:** what "deploy" means in `CLAUDE.md` rule 5 is still unknown.
- **After each part:** update `overview.md`, append a section to `predicate_correctness/output/implementation_log.md`,
  and say "done with part i".

## 4. How to run things
- **Working folder:** `predicate_correctness/`. Run as modules, for example `python -B -m guard.run_online`.
- **Two Pythons:**
  - `~/venvs/tau-bench/bin/python` (runner, LLM calls, τ-bench);
  - `/home/azureuser/miniconda3/bin/python3` (analysis; standard library only).

  Always use `-B` and `PYTHONDONTWRITEBYTECODE=1`.
- **The earlier online runs,** for reference (`output/p10_runs.md`):
  ```
  ~/venvs/tau-bench/bin/python -B -m guard.run_online --profile luna-dev --env retail --tasks train --trials 3 --tag p10_luna_train --workers 8
  ```
  Add `--dry-run` to plan without LLM calls. Outputs go to `output/online/<tag>/<env>/<guard>/episodes.jsonl`. Each tag
  gets a fresh judge cache (`output/_llmcache/<tag>/`); agent and user calls are never cached.
- **Long runs:**
  - start with `setsid nohup … &`, logs to `output/logs/`;
  - the runner is resumable;
  - wait with bash loops of under 10 minutes each;
  - each job ends with a line `[p10-online] <env>/<guard> DONE: ...`.
- **The VM:** 4 CPUs and 16 GB RAM. At most 4 heavy processes at once, each with 8 workers (peak memory was about
  3.4 GB). In a workflow, only 2 subagents run at once.
- **Tests:** `python3 -B -m unittest discover -s tests -t .` from `predicate_correctness/` (153 tests passed on
  2026-10-22).
- **Cost per conversation** (from `output/p10_metrics.md`): about $0.012 with the strong agent, and about $0.022 with
  the weak agent.

## 5. Things that bit us before (keep them in mind)
1. **τ-bench imports:** do not import the copied τ-bench package the normal way. Its `__init__` files pull in heavy
   packages. Use the loader `state_tracker/tau_copy.py` (it registers empty package modules).
2. **`from_shieldagent/` must never go on `sys.path`.** Its folder `code/` would hide Python's module `code`.
3. **Saved step records** (`output/steps_*.jsonl`) store the history as a reference. Load them with
   `state_tracker/load_steps.py` (`read_steps` / `iter_steps`), not by reading the JSONL alone.
4. **Blocked steps that still ran:** an attempt with `cap_override: true` was blocked, but still ran (after 3 blocks in
   a row, the 4th try runs). The replay must run it; the `executed` field tells you.
5. **Guard records of `tgr_tracker`:** `judge` holds the values that were used, each with `source` judge or tracker.
   The judge's own values are in `tracker.judge_values`.
6. **Run files:** when a run resumes, failed lines stay in `episodes.jsonl`. Drop lines with an error, and keep one
   line per (task, try).
7. **Metrics:** the copied partner scripts know only fixed guard names. `scoring/p10_eval.py` builds
   `output/eval/<tag>/<domain>/<guard>/`, where the folder named `tgr` holds our `tgr_tracker` runs. Skip the tag
   `p10_smoke`.
8. **The wrapper today** allows only the guard `tgr_tracker`, and only tasks labelled train or val in `splits.json`.
   Stage A needs a new task source and a `tgr_frozen` guard (Part 2). Keep the write guard (`guard/write_guard.py`).
9. **τ-bench quirks:**
   - the reservation's `cabin` field is never updated after `update_reservation_flights`;
   - an airline reservation has a `status` only after it is cancelled;
   - `search_onestop_flight` shows the second leg's status from the first leg's date;
   - plain-text outputs (`find_user_id_*`, `send_certificate`) are only in the event log.
10. **The judge's 24,000-character view:** the judge sees only the last 24,000 characters of the conversation. This
    caused most of the wrong blocks the tracker removes (a missed login).
11. **Person reviews** of the types (earlier Part 3) and the review readings (earlier Part 7) are still pending. Do not
    wait for them.

## 6. Where the fork points come from (for Part 3 and Part 7)
- **My partner's saved frozen TGR conversations:** `from_shieldagent/runs/{luna_train_v5,nano_train}/<domain>/tgr/`.
  - The changed decisions are already listed in `output/p8_changes.jsonl`: one line per attempt where the decision
    changes. The field `b.change` is "block removed" or "block added".
  - The first changed attempt of each conversation is its fork point.
  - There are 30 removed-block steps and 28 added-block steps, in about 33 conversations.
- **Our earlier TGR + tracker conversations:** `output/online/{p10_luna_train,p10_nano_train,p10_luna_val}/`.
  - A decision changed where `tracker.changed` is not empty and the decision with `tracker.judge_values` differs.
  - `scoring/p10_metrics.py` already recomputes this (section 4 of `output/p10_metrics.md`: 77 changed decisions).
- **The Stage A conversations,** both guards: compute the other guard's decision offline, the same way.
- **What a fork needs** (Part 1 must confirm the formats):
  - the agent's messages, including blocked attempts and the guard's messages (likely the episode's `messages`
    field);
  - τ-bench's user-simulator messages (`tau_bench/envs/user.py`; the runner's model adapter is
    `from_shieldagent/runner/exp_core/models.py`);
  - the database at the fork (`state_tracker/state.py` replay);
  - the guard's counters;
  - the task, so τ-bench can score the result.

## 7. Suggested orchestration (with ultracode)
Run it as three workflows. Read the results between them.
1. **Build** (no LLM calls):
   - Part 1 (checks);
   - then Part 2 (wrapper) and Part 3 (fork code) in parallel. They touch different files: `guard/` vs `fork/`;
   - then Part 4: a **clean, independent auditor** that wrote none of Parts 1–3;
   - then Part 5 (smoke test).
2. **Runs:** Part 6 (Stage A, strong agent, then weak agent), Part 7 (fork points), Part 8 (Stage B). Long; wait on
   the DONE lines.
3. **Analysis:** Part 9 (metrics), Part 10 (report), then a **clean, independent final check** that recomputes the
   numbers.

Each subagent prompt should:
- name its part file;
- say the user approved it;
- repeat the rules in section 3;
- ask for a structured result (status, summary, key numbers, files, issues).

## 8. Kickoff message for the new chat (copy and paste)
**Changed at 10:15 UTC:** the cost in this message is no longer approved. Paid steps need a new approval (section 3).
```
ultracode. Implement the plan in docs/planning/tracker_eval_v2/. Start by reading
docs/planning/tracker_eval_v2/HANDOFF.md, then overview.md and p1.md–p10.md. I approve the plan and its cost
($100 soft stop: at $100, finish only if $30 or less is left). Use subagents; give the audit (Part 4) and the
final check (Part 10) to clean, independent subagents. When done, give me a final report that starts with the key
numbers and whether it was a success.
```
