# Prompt for the next agent: implement tracker v3 (written 2026-10-22)

Copy everything in the code block into a fresh chat. Before you paste it, fill in the line "MY ANSWERS" (or leave
"defaults"). It replaces the planning prompt that was here before; the planning is done.

```
Read /home/azureuser/code_projects/knowledge_retention.md fully, then CLAUDE.md, then the tracker v3 plan:
docs/planning/tracker_v3/overview.md, docs/planning/tracker_v3/brainstorm.md section 11 (my decisions; it wins over
sections 1-10), and every part file docs/planning/tracker_v3/p1.md ... p14.md (short files). Also read
predicate_correctness/output/eval_v3/progress.md (the live status file you keep up to date).
Start every message with what you understood from CLAUDE.md, as it asks (rule 9).

CONTEXT
- Tracker evaluation v2 was stopped on purpose (docs/reports/tracker_eval_v2_report.md). The tracker read the
  database correctly, but all 31 of its lookups read "what earlier tool output showed" (the framing of TGR's rule
  writer, written for a judge that only reads the chat), and 22 answered false when nothing was shown. So "is the gift
  card balance enough?" became "was the balance shown?", and the guard told the agent "violated, do not repeat".
  Most other blocks come from the full LLM judge, which sets 71 % of the values behind blocks.
- Tracker v3 (the plan) has one main idea: NO FULL LLM JUDGE. Every fact is a two-valued state set by code (database,
  event log, call arguments, text structure). Where meaning is needed, one tiny saved yes/no question about one or
  two messages that code picks. Block messages are built from the rule itself (no hand-written text per fact). A
  decision audit (p4) finds wrong decisions by outcome first. The gold scorer is not used at all.
- Paid runs use only the strong agent (gpt-6-luna for every role), on the 99 hard tau-bench tasks we may use (the partner's val 33
  + train 66, both domains; never their test 66) x 3 tries, with five arms: no guard, Direct, Direct + facts (an ablation: Direct prompting plus the facts v3's code tracked),
  frozen TGR, v3.

APPROVAL
- I approve the $0 parts p1-p11 and p13, with the default answers to Q1-Q15 in overview.md.
- MY ANSWERS (changes to the defaults): defaults
- NOT approved: any paid step (p12, and every step of p14). For each, stop just before it, write the approval request
  (commands, cost, hard limit, time) in docs/planning/tracker_v3/approval_request.md, and wait for my new, explicit
  approval for that exact step. Paid runs are started from the main chat only.

YOUR TASK
Implement the plan, part by part, p1 -> p14, in order.
- After each part: say only "done with part i" (CLAUDE.md), add a section to
  predicate_correctness/output/implementation_log.md, update progress.md (status, time, result), fill in the sha256
  table at the end of overview.md for the files the part froze, and go on.
- STOP and wait for me:
  - after p4: I read the audit and pick the order of p5-p10;
  - after p11: I read the offline report;
  - before and after p12 (paid);
  - after p13;
  - before every paid step of p14.
- If a pass mark fails: fix it on the development data, log the change in the pre-registration change log (p1),
  and re-run. Never on the hold-out. Never move a pass mark. If you cannot fix it, stop and tell me.
- Report numbers only from code that you or an independent agent can re-run. Mark estimates "(estimate)".

RULES (from knowledge_retention.md section 7 and CLAUDE.md; all of them, strictly)
- Never write under ~/ShieldAgent, ~/opt or ~/venvs. Use GIT_OPTIONAL_LOCKS=0 for any read-only git command in
  ~/ShieldAgent.
- Never the partner's test group. No gold scorer anywhere in v3 (tests/test_no_gold_import.py covers every new file).
- The frozen eval v2 method and data stay byte-identical (the sha256 manifest of p1 is checked by every v3 script).
  New code only in the new files the part files name.
- Bash output always to a file under predicate_correctness/output/logs/ (prefix v3_), then read it with the Read
  tool. Never to the terminal.
- Python:
  - runner and tau-bench: ~/venvs/tau-bench/bin/python;
  - analysis: /home/azureuser/miniconda3/bin/python3 (standard library only);
  - always -B and PYTHONDONTWRITEBYTECODE=1; run from predicate_correctness/ as modules.
- Tests: python3 -B -m unittest discover -s tests -t . from predicate_correctness/ (288 pass before v3). Every part
  keeps them passing.
- Traps:
  - never put from_shieldagent/ on sys.path (its code/ hides Python's code); load tau-bench copies with
    state_tracker/tau_copy.py;
  - building a tau-bench env with user_strategy="llm" makes one paid user call; use "human" or a scripted user for
    dry runs and tests;
  - take tool arguments from the message, not from attempts[i].kwargs;
  - pgrep -f <name> also matches your own shell; pause or kill by explicit process id or process group;
  - name backups *.jsonl.before_resume: anything named episodes*.jsonl counts as spend in the soft stop.
- Short, simple language in chat and in reports. No Artifacts. Reports have numbers, the code to recompute them, and
  figures.

HOW TO WORK
- Many subagents can run in parallel here (I have run 13 at once). Use the Agent tool, and send ALL independent Agent
  calls in ONE message. Do NOT use the Workflow tool for fan-out: it ran only 2 agents at a time here. The part table in
  progress.md says which parts can run together (p2 and p3 with p1; p6, p7 and p8 together; p5 by domain).
- Put the money rule word for word in every subagent prompt: "STOP BEFORE REAL MONEY: no paid LLM call (agent,
  simulated user, judge, tiny questions; gpt-6-luna or gpt-5-nano), no network call. Your step has no money in it."
- Subagents may now write code, but only the new files their part names. They may run tests and offline scripts
  with fake LLMs and the network blocked. Their bash output goes to predicate_correctness/output/logs/v3_*.log. They
  never edit frozen files, plan files or progress.md: the main chat does that.
- Give every subagent the part file path, the exact files it owns, the pass marks it must reach, and what to return.
  Brief it like a peer: it knows only what you write.
- After p1, p4, p10 and p11, have one independent read-only agent re-check the part's "How we know it is right"
  section with its own script, before you say "done". In eval v2, independent auditors found 1 real bug and 1
  unfairness before any money was spent.
- Paid runs: a subagent prepares and dry-runs them; only the main chat starts them, after my approval (a subagent
  cannot show my approval to the permission check).
- Keep progress.md current: a line in "Events" at every event, and an "auto:" line every 10 minutes during paid runs.

WORK ALREADY DONE (do not redo it)
1. The plan: docs/planning/tracker_v3/overview.md, p1.md-p14.md, brainstorm.md (section 11 = my decisions).
2. Designs and reviews behind the plan, under predicate_correctness/output/logs/. They are useful for detail (file
   lines, tool check orders, counts), but parts of them are replaced by the plan; when they disagree, the plan wins:
   - v3_wf_result_a.json: reading table T2, the tool check order and Error texts T3;
   - v3_wf_result_b.json: message ideas, the information-safety whitelist;
   - v3_design_c_result.md: structure code, the question ideas;
   - v3_design_d_result.md: data sizes, offline harness;
   - v3_design_e_result.md: prices, power, run mechanics;
   - v3_crit_{a,b,c,d,e,all}_result.md and v3_crit_plan2_result.md: the critics' findings (already applied to the
     plan).
3. Scouting logs: v3_scout_*.log, including v3_scout_tool_errors.log (every tau-bench tool check and Error text, in
   code order).
4. Facts checked on 2026-10-22:
   - ~/ShieldAgent has 3 commits after our copy (1bacdb0): docs and scripts/reproduction/p1_trace.py only;
   - the rules: 98 rules, 82 with one fact, the largest (airline rule 25) with 6;
   - saved data: 2,990 conversations, 38,579 judged checks, 4,885 blocks (+415 cap overrides), 3,260 judged Stage B
     checks; our 495 and the partner's 495 are the same (task, trial) pairs; val = 198 conversations;
   - the eval v2 harm set: 420 checks; 356 of them are also blocked by another rule.

FIRST STEPS
1. make sure the v3 plan and its benchmarking process (including the direct+facts ablation) is consistent, and well planned
2. Write progress.md's "Now" (started), then start p1, p2 and p3 together (3 Agent calls in one message). You keep the
   logs and the progress file.
3. Then p4 (the audit) on the eval v2 data, its independent re-check, and STOP for me.
```
