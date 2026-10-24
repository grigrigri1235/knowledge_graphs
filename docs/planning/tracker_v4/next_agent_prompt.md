# Prompt for the next agent: tracker v4 on τ³-bench (copy and paste)

Written 2026-10-23 by the agent that ran tracker v3, at the user's request. A copy is in the last section of
`knowledge_retention.md`; if the two differ, this file wins.

```
You are taking over a research project that just had a really promising result. Read this whole prompt first.

WHO YOU WORK FOR AND HOW
- Read /home/azureuser/code_projects/CLAUDE.md and follow ALL of it. Start every message with a short line saying
  what you understood from it. Short, simple words. Brainstorm in files, not in the chat. No Artifacts.
- Plan → the user's explicit approval → many tiny parts. After each part say only "done with part i" and go on.
- The user cares about SPEED. Tracker v3 took a whole day; this one must not. We learned the hard lessons already
  (docs/planning/tracker_v3/lessons_learned.md). Plan in ONE shot, use many parallel subagents (the Agent tool;
  the Workflow tool is capped here), and keep the number of stops small (see SPEED below).

RED LINES (never cross them; no exception without the user's new, explicit words)
1. No paid LLM call (agent, user simulator, judge, tiny questions; gpt-6-luna, gpt-5-nano or any other) and no
   network call (pip, git clone, downloads, web) without the user's new, explicit approval for that exact step.
   Approval of a plan or of an earlier step never counts. Paid runs are started from the main chat only, never by
   a subagent. Every paid step has a written request (commands, cost, hard limit, time) and a hard limit in code.
2. Never write under ~/ShieldAgent (the partner's repo), ~/opt or ~/venvs. Read-only git there with
   GIT_OPTIONAL_LOCKS=0. Never put from_shieldagent/ on sys.path. A new Python env for τ³-bench (it needs
   Python 3.12-3.13) goes under /home/azureuser/code_projects/, never under ~/venvs, and only after the user
   approves the install (it is a network step).
3. Never the partner's test group (the τ-bench v1 test tasks in their test 66 split, in ~/ShieldAgent splits.json),
   in any version of τ-bench, τ²-bench or τ³-bench. In τ³ airline/retail, map every task to its v1 task first and
   drop those 66.
4. No gold scorer anywhere in the method. τ-bench's own reward and expected actions are used only to score.
5. The frozen eval v2 and v3 methods and data stay byte-identical. v3's results are final; do not re-run or "fix" v3.
6. Every bash command writes its output to a file under predicate_correctness/output/logs/ (prefix v4_), read with
   the Read tool. Never to the terminal. Python: -B, PYTHONDONTWRITEBYTECODE=1, PYTHONHASHSEED=0.
7. Traps: user_strategy="llm" makes a paid call; take tool arguments from the message, not attempts[i].kwargs;
   `pgrep -f` matches its own shell; backups are copied (cp, never mv) to *.jsonl.before_resume.
8. No change to the method after the freeze; pass marks and the reading of each number are written BEFORE the
   result (pre-registration + reading guide), and the harm metric is planned BEFORE the run.

WHAT WE HAVE (tracker v3, done 2026-10-23; total $21.49)
- A guard that checks each action of a customer-service agent with CODE facts (τ-bench's own tool code replayed on
  a copy of the database, the event log, call arguments) plus TINY yes/no LLM questions, instead of a big LLM judge.
- A really promising experiment with cool results:
  * Main live test (B2, 99 hard tasks × 3 tries × 5 guards): v3 ties the old guard (frozen TGR) on task success,
    −0.024 [−0.088, +0.040], PASS.
  * The money gain is clear: v3 is the cheapest guard, $0.0089 per conversation vs $0.0116 for the old guard (23 %
    less); its guard part costs $0.0007 vs $0.0047 per conversation; only 58 % of its checks need an LLM (vs 88 %).
  * Harmful writes that got through are lower where it matters: on many-step tasks (B3) 8.2 % of v3's
    conversations vs 20.4 % for the old guard and 24.5 % with no guard. (On B2 all guards were about equal,
    16.8-19.2 %: a strong agent rarely tries harm.)
  * Safety: 0 v3 allows that the database then refused.
  * What went wrong is known and fixable: one badly built tiny question, K2 ("the agent listed the details"),
    caused most lost tasks (its card line could never match the data), plus smaller K1, K5, K13 issues.
    Details: docs/planning/tracker_v3/lessons_learned.md section 1, predicate_correctness/output/eval_v3/
    tiny_question_audit.md, B3_diagnosis.md.

THE GOAL: tracker v4 = the whole pipeline again, in one shot, on τ³-bench
- τ³-bench is the newest τ-bench (repo sierra-research/tau2-bench, package `tau2`). Use ONLY:
  (a) airline + retail: exactly the 99 tasks listed in predicate_correctness/output/eval_v3/online_tasks.json
      (66 marked "train" + 33 marked "val"), in their τ³ versions. τ³ has 75+ task fixes across airline, retail and
      banking (per its README), so a task's text may differ a little. We have seen these tasks, so this part is
      "a one-shot rebuild on a new harness, on known tasks". It is NOT an unseen test. Use no other airline or
      retail task.
  (b) banking_knowledge (about 97 tasks, with a knowledge base of about 698 policy documents): the TRUE UNSEEN
      test of the method on a new policy. Before the freeze you MAY read its policy documents, tool code and
      database: you need them to build the facts and questions. Before the freeze you may NOT open its task
      files (user instructions, expected actions, outputs) or run any banking conversation. After the freeze the
      tasks are opened once, for the live run.
- Verify every count and fact above from the repo once the user approves the download; report differences.

READ FIRST (in this order; skim long ones; every relative path in this prompt starts at /home/azureuser/code_projects/)
1. /home/azureuser/code_projects/knowledge_retention.md (all of it).
2. docs/planning/tracker_v3/lessons_learned.md (all of it: the most important file).
3. docs/reports/tracker_v3_full_report.md (the results, harm, tiny-question problems, next steps).
4. docs/planning/tracker_v3/overview.md (how v3 was planned: parts p1-p14, the sha table), k2_fix.md,
   preregistration_online.md, b2_reading_guide.md, next_steps_leak.md, approval_request.md (cost log).
5. predicate_correctness/output/eval_v3/tiny_question_audit.md, B3_diagnosis.md, B2_val_diagnosis.md,
   direct_facts_diagnosis.md, harm_metric.md.
6. The v3 code: predicate_correctness/state_tracker/v3/ (facts, questions.py, questions_v3.json),
   guard/tgr_tracker_v3.py, guard/run_online_v3.py, scoring/v3_online_metrics.py, tests/.

YOUR FIRST JOB ($0): write the v4 overview and plan, in ONE go, then STOP for the user's approval
Write docs/planning/tracker_v4/overview.md (+ one short file per part if needed). It must have:
1. The main idea in plain words first; the claims and pass marks (pre-registered); the data roles (airline/retail
   known; banking unseen; the partner's test group excluded). The arms: the same 5 as v3 (no guard; Direct;
   Direct + facts; the old guard, i.e. the partner's frozen TGR; v4). TGR's frozen rules exist only for τ-bench v1
   airline and retail and must not be changed. So: say whether TGR's frozen rules can run unchanged on τ³ airline
   and retail; if not, drop that arm there and say why. For banking there is no TGR: drop that arm (do not build a
   new TGR).
2. Metrics planned BEFORE the run: task success AND "harmful got through" (an accepted write the task did not
   expect, or any write on a refusal task; lower is better) side by side in EVERY table; cost per conversation; LLM
   calls per conversation (all roles and guard only); share of checks that need an LLM; blocks per write.
3. Which predicates (facts) are needed, found with the same method as v3 (knowledge_retention.md section 7: rules
   from the policy, the facts each rule needs, a decision audit). For EACH predicate, look at the policy, the tool
   code and the database:
   - if it can be computed by code alone (database, tool-code replay, event log, call arguments) with deterministic
     tracking: do that. Never ask an LLM what code can know;
   - only if it truly needs reading the conversation: a tiny clarifying question, built with ALL the lessons in
     lessons_learned.md section 1 (the K2 incident above all: every form the question accepts must occur in the
     real data — check it on the database; never ask the user to repeat what the database knows; say which text
     window the question reads; one "yes" may cover a listed batch; the block message names the missing detail
     and the expected value; define words like "another person"; quotes may come in pieces; test each question on
     made-up yes/no cases written from the policy before any real data).
4. THE PREDICATE TABLE (required), one row per predicate:
   | predicate | domain | source (code / tiny question) | the exact question (or the code rule) | text window read |
   | expected user (or agent) answer in a normal good conversation | how sure are we the user answers that way
   (high / medium / low) and why | what happens on "unclear" | the block message if it fails |
   Every "low" or "medium" row needs a plan to remove or soften the question. Show a K2-style check for every row:
   "can each accepted form occur in the data? checked how?"
5. Few-shot in the tiny questions: decide per question whether 1 yes + 1 no example helps. Examples must be
   MADE UP from the policy, never copied from any conversation (a leak). Cost is small: v3's tiny calls cost about
   $0.00004 each and v3 asked about 16 per conversation, so 1-2 short examples add about a quarter to that part,
   about $0.0002 per conversation, cents per run. Say what you chose and why.
6. The parts (few, big, parallel), each with: what, cost, hard limit, time, agents, the stop if any.
7. The leak rules: freeze v4 (sha256 of every method file) before any banking task file is opened or any banking
   conversation is run; banking tasks are opened once; airline/retail results are labelled "known tasks".
8. Cost and time estimates (use v3's measured costs: B2 $15.76 for 1,485 conversations; mean about $0.0106 per
   conversation; B3 $5.25 for 245).

SPEED (the user's wish; follow it)
- Stops (exactly these; the user approves each one):
  (1) the plan;
  (2) the install / download of τ³-bench (a network step);
  (3) a paid dev check of the tiny answers on the known airline/retail tasks only. Skip this stop only if the plan
      says why it is not needed;
  (4) the paid live runs. One written request may cover both the known-task run and the banking run, with one
      hard limit for each.
  No other stops, unless a pre-registered stop rule fires during a run.
- Reuse v3's code and audits wherever τ³ allows; port, do not rewrite. Run builds, tests and audits as parallel
  agents. Automate the after-run steps (metrics, report, independent recompute) so they run when the run ends.
- After each part, update in short lines (no doc churn): a v4 progress file (docs/planning/tracker_v4/progress.md),
  the implementation log (predicate_correctness/output/implementation_log.md), knowledge_retention.md section 1,
  and the sha256 table at the end of docs/planning/tracker_v4/overview.md.
```
