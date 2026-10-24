# Part 03: how v4 was built and checked, purity, lessons from v3

*Sections 6 and 7 and Appendix A of the tracker v4 report. Written 2026-10-24 from the planning files, logs and dev
results. No v4 live result and no v3 conversation was opened for this part. Words marked "see Glossary" are defined
in Part 1.*

## 6. How v4 was built and checked

**Main idea.** v4 went through the same steps as v3, in the same order: plan → build at $0 → $0 checks and audits →
a small paid check on development data → fixes → freeze → a 4-conversation smoke test → live runs. The paid check
found two real problems. Fixing them took **two fix rounds, not the one round the pre-registration allowed**; the
second round was the user's decision. Before the live runs v4 had spent about **$0.25** in all.

**Words used here** (more in the Glossary):
- *Development data ("dev")*: data used only to find bugs and too-strict questions, never as a result. Here: 720
  made-up cases and 200 saved v3 development conversations.
- *Made-up case*: a short invented conversation, written from the policy text, with a known right answer. Each
  tiny question got 30 "yes" cases and 30 "hard no" cases (a "no" that looks close to a "yes").
- *Reference* (also "stand-in", see Glossary): the old judge's saved answer for the same fact at the same check. The
  dev check compares v4's blocks with the blocks this reference gives.
- *Fix round*: after a failed dev mark, change only question definitions, then re-ask only the changed questions.
- *Freeze*: the sha256 of every method file goes into one list (the *manifest*). After it, no method change.
- *Smoke test*: 4 live conversations that only check that the live set-up works. Not counted as a result.

The questions named below (full list in section 5): **K3** "did the agent remind the user to include all items?",
**K4** "is the user's message about another person's account or order?", **K13** "is the request outside what the
agent's tools can do?" (a yes allows a hand-over to a human), **K17** the travel-insurance choice.

### 6.1 Timeline (UTC)
| when | step | what happened | paid |
|---|---|---|---|
| 23 Oct, 21:00-21:40 | false start | A first try on τ³-bench. Agents hand-wrote banking rules; the user called it a leak. The work was deleted, the banking task files sealed, the session ended. v4 went back to τ-bench v1 (§7.3, event 0) | $0 |
| 23 Oct, ~21:55 | plan approved | Same benchmark, tasks, rules and predicates as v3. Only how each predicate gets its value changes | $0 |
| 23 Oct ~22:00 → 24 Oct 02:40 | build | 13 build agents at once, each owning its own files, plus 3 "blind" case writers who never saw the questions' examples. An API limit paused 9 agents from 23:15 to 01:35 | $0 |
| 24 Oct, ~05:00-05:45 | merge and $0 checks | Parts merged; full test suite; the whole v4 guard run offline on the 200 dev conversations with reference answers; dry runs with 0 LLM calls | $0 |
| 24 Oct, by ~07:00 | 3 read-only audits, then fixes | 5 purity events found and fixed (§7.3). A planned side test on 20 retail dev tasks was dropped. Safety gates for real runs added | $0 |
| 24 Oct, before the dev check | plan change (user) | The 4 old arms are reused from v3's saved runs. A $0 identity check (in a sandbox copy with fake LLMs and no v3 conversations) showed that none, Direct and frozen give byte-identical records in the v3 and v4 runners | $0 |
| 07:31-07:49 | dev check 1: made-up cases | 12 questions × 60 cases. K3, K4 and K13 fail the mark | $0.054 |
| ~07:55-08:06 | **fix round 1** (allowed by the plan) | New definitions for K3, K4, K13. The case tester now cuts the text window the same way the real guard does. K3 and K4 pass; K13 gets 27 of 30 hard-no cases right (28 needed). The user: "Accept, record, go on" | $0.019 |
| 08:08-08:11 | dev check 2: 200 conversations | **FAIL**: 120 blocks vs 32 for the reference (3.75×; the mark is 1.5×), and 2.1 % unclear answers (the mark is 2 %) | $0.075 |
| ~08:14-08:28 | cause found | A $0 sub-agent found a wiring bug, and that K13 cannot see that the agent already refused under the rules (details below) | $0 |
| 08:38-08:43 | **fix round 2** (user decision, beyond the plan), re-check | Wiring fix and a new K13. Cases: K13 again 27 of 30. 200 conversations: **all 5 marks pass** | $0.048 |
| 08:44:24 | **freeze** | 204 files in the manifest | $0 |
| 08:44:47-~08:47 | smoke test B1v4 | **PASS** | $0.054 |
| ~08:48 | live runs | B2', B3' and H start at the same time (results: section 8) | — |

**The two problems in plain words.**
- *Wiring bug.* Fix round 1 gave K3 one more input: is the action an exchange or a change of items? But the code that
  asks K3 still used v3's helper, which does not know that input. So **every K3 ask crashed**. A crash counts as a
  fact error, and a fact error blocks. That was 76 crashed checks and 64 extra blocks. The fix points K3 to the v4
  helper. It adds no leniency.
- *K13 saw too little.* All 30 K13 blocks were on airline hand-overs. In 24 of them the agent's own summary said a
  rule did not allow the request; in 13 the user had asked for a human. K13 saw only the user's message. The new K13 also reads
  the agent's message just before it: if the agent said the rules do not allow the request for this user, and the
  user still asks for it or for a person, the answer is yes. Requests on the policy's refused list stay no.

### 6.2 Dev check results
**Made-up cases** (pass mark: at least 28 of 30 right on the yes side and on the hard-no side, per question):

| question | first run (yes / hard no) | after fix round 1 | after fix round 2 |
|---|---|---|---|
| K3 | 29 / **24**: fail | 30 / 30: pass | not re-run |
| K4 | **27** / 29: fail | 29 / 30: pass | not re-run |
| K13 | 30 / **26**: fail | 30 / **27**: fail, accepted by the user | 30 / **27**: fail, same acceptance |
| the other 9 questions | all pass | not re-run | not re-run |

**200 dev conversations** (2,164 guard checks):

| check (pass mark) | after fix round 1 | after fix round 2 |
|---|---|---|
| blocks from tiny questions vs the reference, same checks (at most 1.5×) | 120 vs 32 (3.75×): **fail** | 37 vs 32 (1.16×): pass |
| "unclear" answers (at most 2 % of tiny calls) | 2.1 %: **fail** | 4 of 783 (0.5 %): pass |
| two-key conflicts (0): a new allow needs both the question's yes and the code part; a conflict is a check where they disagree | pass | 0: pass |
| state errors, i.e. crashes in the state code (0) | pass | 0: pass |
| block messages that name a detail the agent can fix in one turn (100 %) | pass | 37 of 37: pass |

**So what.** Of the 120 blocks after round 1, the wiring bug alone made 64 at checks where the reference allowed.
After round 2, v4 blocks about as often as the old judge on dev data (1.16×). For comparison, v3 went to its live
test at 122 vs 31 (about 3.9×) on the same check, because v3 had no pass mark there. This is v3's main lesson at
work (Appendix A, L1.16).

### 6.3 What to keep in mind about the dev check
- **Beyond the plan.** The pre-registration allows one fix round; if a mark still fails, "stop and ask the user". We
  stopped and asked; the user chose a second round. It is in the change log with "result seen? yes (dev only)". No
  pass mark was moved.
- **Same data for finding and checking.** Both rounds were checked on the same 200 conversations and the same cases
  that showed the problem. So "all pass" after round 2 shows the fix works on the data that found it. It is not an
  independent test. Dev numbers are bug and strictness checks, never results.
- **K13's case mark was never met** (27 of 30, one short, in both rounds). Every miss was lenient: a hand-over allowed
  that should have been blocked. It is a recorded exception.
- Fix round 1 also changed the case tester (the text window), not the guard.
- **Spend.** The dev ledger shows $0.196 in 1,993 paid calls: cases $0.081, the 200 conversations $0.114. The
  pre-registration's change log says "about $0.21" (it counts by a "larger of two counts" rule). Limit: $2 and 5,100
  calls.

### 6.4 Freeze and smoke test
- **Freeze** at 08:44:24 UTC: 204 files = 202 method files (the v4 code, the question and fact files, the 720 cases,
  the partner's rules and runner, the v3 code v4 uses, the tests, the task lists) + the pre-registration + the
  reading guide. Manifest sha256 `10bbfb4e5ce637f66905a5815f12a6d6d18278eb4bdd28043826403b74908e68`. Checked for
  this report: the pre-registration's sha today equals its frozen sha.
- **Gates in the code.** A paid run needs a flag only the main chat uses. B2', B3' and H refuse to start without a
  passing B1 on the same manifest. B1's run record names the same manifest sha.
- **Smoke test B1v4: PASS.** Approved by the user ("can you also run the full scale experiment as we planned? …
  lets go"). 2 tasks × the 2 new arms = 4 conversations, $0.054 in all, mean $0.013 per conversation (limit $0.032),
  0 error lines, 0 fact failures in D+F v4, 0 state errors in v4. Total v4 spend at the end of B1: $0.249.
- **Small gaps found while checking.** (1) The pre-registration's file table still says "TBD at freeze", and the
  plan's sha table is empty; the manifest is the only record. (2) The plan wanted one sha per reused v3 run file in
  the manifest; they are not there. Instead the scoring code refuses a v3 run whose run id or task-list sha differs.
  (3) The last full test run before the freeze (08:27): 39 of 41 test modules pass; the 2 that fail are frozen v3
  tests with known, test-only causes (logged before v4).

*Sources:* `docs/planning/tracker_v4/preregistration_v4.md` (§12-14, change log); `progress.md`;
`dev_check_fail_notes.md`; `fix_round2_plan.md`; `predicate_correctness/output/eval_v4/{cases_check_real.md,
fix1/,fix2/,dev_check.md,v4_freeze.json,dev/dev_spend_ledger.jsonl}`; `output/logs/v4_B1_state.txt`; B1v4
`run.json`; `output/logs/v4_tests_20261024T082706Z_*`; `knowledge_retention.md` §8; `implementation_log.md` (end).

---

## 7. Purity and data leakage

**Main idea.** Every v4 result is labelled **"known tasks"**: v4 runs on tasks whose v3 results we studied. The parts
of the process that are easy to check are clean: the rules were not touched, the method was frozen before any live
call, no gold scorer was used, and the build scripts read only the database and the policy text. The leak is the
*knowledge* that came from v3's test conversations on the same tasks, second-hand, through v3's reports, plus two
fix rounds on dev data from the same task pools. **The leak is small, but it is not zero.**

**Words used here.** A *leak* is any way the test answers can shape the method before the test. *Seen* tasks are
tasks whose conversations or results the builders could learn from. The *gold scorer* is τ-bench code that knows the
right actions; the method may never use it (task success is τ-bench's own reward). A *few-shot example* is a worked
example inside a question's prompt. The *form check* is a $0 script that counts how things like cards and ids are
written in the data.

### 7.1 What is known about the test tasks
| set | tasks | seen before? | what the build knew about them |
|---|---|---|---|
| B2' | the same 99 tasks as v3's B2 (66 train + 33 val) | yes. v3 ran 297 conversations per arm on them; v3's results, diagnoses and lessons were read. Val 33 is no longer "unseen" | which tasks v3 lost and why: mostly by pattern, some by task id and quoted user lines |
| B3' | the same 64 many-write retail tasks as v3's B3 | yes. v3 ran 49 of them. They are "Stage A" tasks (easy retail tasks from τ-bench's retail train file), and Stage A conversations were v3's build data | v3's B3 diagnosis (11 of 17 losses came from one too-strict v3 question) |
| B3', the 15 "fill" tasks | the tasks v3's B3 never reached (its halfway stop fired) | never in a B3 run. As Stage A tasks they may be in v3's build data (not checked) | nothing task-specific from B3 |
| H | the same 99 tasks as B2', weak agent | the tasks, yes. The agent is new: no conversation with it existed | the same as B2' |
| dev data | 200 saved v3 conversations: the first 50 of 4 sets, 2 on Stage A tasks and 2 on hard train tasks | used for both fix rounds | they come from the same task pools as B3' and B2' train. The exact overlap with the 163 test tasks was not counted |

### 7.2 Checking the claim
The user's claim: *"we basically ran the pipeline from the start, with only general lessons learned from v3."*

| part of the claim | holds? | why |
|---|---|---|
| the same steps in the same order, from plan to live run | **yes** | timeline in 6.1. The pre-registration and reading guide were written before any paid v4 call; the freeze came before the first live call; the smoke test came before the main runs |
| nothing was fitted to the right answers | **yes** | the partner's 98 rules and 66 predicates are unchanged (read-only, sha-checked). No gold scorer. The build scripts read only the database and the policy text. No lesson says which action is right in a task |
| "from the start" | **partly** | v4 is not a new build. It keeps v3's code, harness and code facts and changes only how values are set. 4 of the 6 arms are v3's saved runs on B2' and on 49 B3' tasks, not new runs |
| "only general lessons" | **partly** | the lessons are general in form, but (a) they were found on these same tasks; (b) the build's inputs name lost tasks (9 task ids in v3's lessons file, about 20 in the per-question notes) and quote user lines from v3's test conversations, e.g. "please submit the returns for all four items" and "I can't reply 'yes'"; (c) some few-shot examples were picked to target those loss types; (d) some fixes are about this benchmark's data (cards are named by payment-id digits) or drop lines that lost these tasks (date of birth, country, "paid" bags) |
| one planned fix on dev data | **no** | two fix rounds, both checked on dev data from the same task pools; the second by user decision |

### 7.3 Purity events: the full list
None of these changed a v4 decision that we know of. All were found and fixed before any live v4 run.

| # | what happened | fix | effect |
|---|---|---|---|
| 0 | **False start (23 Oct).** On τ³-bench, 7 agents hand-wrote banking rules (rule making outside the partner's method), and one reader read release notes that name 4 banking tasks | user decision: all of it deleted; the banking task files, results and release notes sealed; session ended; v4 moved back to τ-bench v1 | none on v4's tasks (banking is not used). The 4 named banking tasks count as seen for any later banking test |
| 1 | **Form check read test text.** The form-check script read the user instructions and gold expected actions of the retail train file (holds B3'), the test tasks (= B2') and the 20 retail dev tasks, to count how users name things | user decision: rebuilt to read only the 6 database files and the 2 policy files; a test enforces it; all 40 form decisions re-based on the database, the policy or a generic reason | 0 decisions changed; the offline rows are byte-identical. The 20 retail dev tasks are now seen, so that side test was dropped |
| 2 | **Message check read more than dev data.** An early run of the block-message check used its old default of 9 data sets, including saved conversations forked from v3's hold-out (the conversations v3 kept apart for its one offline test), and weak-agent sets | now only the 200 dev conversations are allowed; any other set is refused | code read the files and logged only counts; no person or model read the content |
| 3 | **Few-shot wording too strong.** The plan said the few-shot writers "never saw any conversation" | reworded: the examples are made up from the policy, but some were picked to target loss types known from v3's reports | wording only; it is part of the leak in 7.2 |
| 4 | **K17 cases too close to K17's example.** 3 made-up cases equalled or nearly equalled the K17 few-shot example | replaced; the closest case now has a text ratio of 0.817 to any example (the limit is 0.9) | the K17 case score is not inflated by copies |
| 5 | **v3's answer store.** The dev check and offline run read v3's saved tiny answers | now they keep only the rows of the 200 dev conversations, enforced in code | rule made exact in code |

### 7.4 Possible leaks: what we did, what is left
| possible leak | what we did | what is left |
|---|---|---|
| v3's fixes were found on the same test tasks | label "known tasks"; no "unseen" claim anywhere; lessons written before any v4 data; v4 shown next to v3, never in its place | the build read task ids, loss stories and quoted user lines from those tasks (7.2) |
| rules fitted to the tasks | the partner's rules and predicates unchanged, read-only, sha-checked | the partner tuned its rule-building prompts on v1 train conversations (the same for every TGR arm) |
| build reads test task text or gold actions | the form check reads only database and policy files; a test checks the source, refuses other paths, and records every file a full run opens | the first version did read them (event 1); 0 decisions changed |
| a gold scorer inside the method | a test scans all v4 guard, scoring, test and script files (imports, text, path strings) and imports them in a fresh process | none known |
| v3's test conversations opened while building | a written rule in the build brief, plan and pre-registration; 3 read-only audits; the message check limited to dev data; the identity check ran on a copy with no v3 conversations | event 2 (counts only). The rule is a process rule; no test can prove it |
| dev data overlaps the test pools | dev = 200 v3 dev conversations and made-up cases; never v3's hold-out, B2 or B3 logs | the dev sets are Stage A and train conversations, the same pools as B3' and B2' train; both fix rounds used them; the overlap was not counted |
| fixes after seeing data | one planned round; every change in the change log with "result seen?" | round 2 went beyond the plan and was checked on the same data |
| a method change after the live results | freeze of 204 files before B1; the gates check the manifest sha; the pre-registration's sha is unchanged | the reused v3 run files have no per-file sha in the manifest (6.4) |
| the reused old arms | read only after the freeze, by scoring code, never changed; same API model; byte-identical records in the $0 identity check | the time between runs (old arms 23 Oct, new arms 24 Oct); B3' old-arm data is mixed (49 v3 + 15 new) |
| the partner's test 66 | never used; the runner and the metrics refuse it | the only truly unseen hard data stays unused |
| τ³-bench banking | 218 files sealed (sha256 first, then no read access; still sealed today); no v4 code uses the τ³ copy | does not protect v4's tasks; it only keeps a later banking test clean |

### 7.5 Verdict
The process claim holds. v4 ran the full pipeline again in v3's order: a plan, a pre-registration and a reading
guide before any paid call, a freeze before any live call, a smoke test, gates in the code, and no gold scorer. The
build scripts read only the database and the policy, and the rules were never touched. The claim "only general
lessons from v3" holds only in part. The lessons are general rules, and none of them says which action is right.
But they were found on these same tasks, and the build read reports that name the lost tasks and quote user lines
from them. Some few-shot examples aim at those losses. Two fix rounds, not one, were tuned on dev data from the same
task pools. So **"known tasks, small leak"** is the honest label, and v4's numbers on B2' and B3' may be a little
better than v4 would get on new tasks of the same kind. H has the weakest link to v3 (new agent, all arms live), but
its tasks are known too. Only a run on unseen tasks (for example the partner's test 66, which needs the user's and
the partner's OK) could remove this doubt.

### 7.6 Why we accepted the small leak, and why it stays small
**There was little we could do about it.** τ-bench v1 has few tasks of each kind. The partner's split leaves 165
test-file tasks: v3 already used 99 of them (B2), and the other 66 are the partner's own final test, which we keep
unused. The many-write retail tasks (B3') are a small pool too. So there was no fresh set of the same kind to build
or test v4 on. Any v4 had to run on tasks v3 had already seen.

**The leak cannot help the cost claim.** v3 already showed that the tracker is cheaper than frozen TGR (B2 $0.0089
vs $0.0116 per conversation; B3 $0.0185 vs $0.0244). Cost comes from how many LLM calls a guard makes, not from
knowing which action is right, so knowing the tasks does not make v4 look cheaper.

**v4 was worth the asterisk.** v3's report showed problems in how the tiny questions were made: some were too strict
(one question caused 11 of v3's 17 B3 losses), and the block messages were often vague. These looked like easy
fixes with a large effect. We chose to make them, knowing the result would carry a "known tasks" mark.

**Why the leak stays small:**
- The rules and facts are the partner's and were never changed. v4 only changes how a fact gets its value.
- No gold scorer, and no right answer of any task, is used anywhere in the method.
- The lessons are about how to word a question and how to treat an unclear answer. None of them says what to do in
  a given task.
- No text from a test conversation is in any prompt. The few-shot examples and test cases are made up from the
  policy, and a check refuses near-copies.
- The dev pass marks never looked at task success. Both fix rounds were judged on blocks compared with the judge
  stand-in, on unclear answers and on errors, so they could not tune v4 toward winning tasks. Fix round 2 was mostly
  a crash fix (a code bug), which no amount of task knowledge would change.
- The pass marks, the reading rules and all the code were written down and frozen before any live run.
- H uses a weak agent that never ran before, and 15 of the B3' tasks never ran in any B3 test.

### 7.7 For the future
If time allows, run the v4 pipeline once more **purely from the start**: build it without v3's task-level notes,
then test it on tasks nobody has seen (for example the partner's test 66, with the partner's OK). This would only
reassure fairness. It would not change the method. It is also cheap: the whole v4 dev check cost about $0.21, and all
live steps together about ⟦TBD: spend.total⟧. On the data so far the method works well: it passes both success
claims (B2' and B3') at a lower cost than frozen TGR (H: ⟦TBD: H1.label⟧).

*Sources:* `preregistration_v4.md` §0, §15, §18 and change log; `docs/planning/tracker_v4/build_brief.md` rule 3;
`session1_process_log.md` §2-5, §9; `overview.md` §3, §12; `banking_seal_paths.txt`, `banking_seal.sha256`
(file permissions checked today); `predicate_correctness/tests/test_v4_no_gold_import.py`, `test_v4_form_check.py`;
`scripts/v4_identity_check.sh`; `scoring/v4_message_check.py`, `scoring/v4_offline_eval.py` (dev sets);
`scoring/v4_online_metrics.py` (reuse checks); `docs/reports/tracker_v3_full_report.md` §4.1, §4.7;
`docs/planning/tracker_v3/lessons_learned.md`; `reading_notes/tiny_questions.md` (task-id count by grep);
`state_tracker/v4/questions_v4.json` (`few_shot_why`).

---

## Appendix A. Lessons from v3 used in v4

**Main idea.** v4 used about 30 lessons from v3. Almost all are **general**: they would help on any policy. A few
carry **task-specific** detail: they were found on, and partly name, the tasks v4 runs again. "L" numbers are the
lesson numbers of v3's lessons file (the same numbers as v3 full report §9).

| # | lesson (one line) | used in v4 as | from | general or specific |
|---|---|---|---|---|
| L1.1 | if code can know it (database, tool code, event log), do not ask an LLM | 5 of v3's tiny questions became code, among them "the agent listed the details" | lessons §1.1; v3 full report §6.1 | general |
| L1.2 | before paying, check that each accepted form really occurs in the data | the form check; cards accepted by payment-id digits (0 of 239 retail and 0 of 503 airline ids end in the card's last four) | lessons §1.2; full report §6.2 | general method; the card finding is specific to τ-bench's data |
| L1.3 | do not ask for what the policy does not ask for, or what the database knows | dropped date of birth, country and "N paid" bags from the listing check | lessons §1.3 | general idea; the dropped lines were found on lost test tasks: **specific** |
| L1.4 | one question asks one thing about one short text | rule 1 for every question | lessons §1.4 | general |
| L1.5 | write the text window into the definition | windows in every definition; the listing reads all agent messages since the last write; the new K13 reads the agent's message before | lessons §1.5 | general |
| L1.6 | one go-ahead can cover a listed batch; test it | the go-ahead question accepts one yes for a batch | lessons §1.6 (found on one lost test task) | general rule, found on a test task |
| L1.7 | "unclear" should not block at once | one more ask with a second wording; hand-over and login questions allow and log on unclear | lessons §1.7 | general |
| L1.8 | quotes come in pieces | the quote check splits at any punctuation | lessons §1.8 | general |
| L1.9 | a block message must name the missing detail and its value | "Not stated: …" in every v4 block message; a pass mark on dev | lessons §1.9 | general |
| L1.10 | plan a way out of a chain of wrong blocks | a hand-over is allowed after 2 tiny-question blocks on the same write | lessons §1.10 | general |
| L1.11 | define every open word | "another person" = another customer, not a public figure, not the user | lessons §1.11 | general; its examples come from test conversations |
| L1.12 | ownership comes from the database; give the question a default | ownership by code; "the user's own unless the message says otherwise" | lessons §1.12 | general |
| L1.13 | a message that asks for nothing new is "no" | in every question that reads user messages | lessons §1.13 | general |
| L1.14 | write down the answer you expect from agent and user | a short "yes" decided by code; the insurance "Yes." case | lessons §1.14; per-question notes | general method; the "Yes." case was found on a lost test task: **specific** |
| L1.15 | test each question on made-up cases before real data | 720 blind cases, a pass mark per question | lessons §1.15 | general |
| L1.16 | a strictness check needs a pass mark | at most 1.5× the reference's blocks on dev | lessons §1.16 | general |
| L1.17 | many-step tasks multiply each question's errors | B3' pre-registered as its own claim | lessons §1.17, §3.8 | general |
| L1.18 | version every question, cache answers by hash | kept; fix rounds re-asked only changed questions | lessons §1.18 | general |
| L2.3, L2.4 | a new allow needs two keys; an unclear part must not hide the other branch of an "or" | kept, and checked on dev (0 conflicts) | lessons §2.3-2.4 | general |
| L2.6 | show code facts to an LLM as final values with their sign | the D+F v4 arm ("user is a regular member: NO (membership gold)") | lessons §2.6; full report §6.6 | general |
| L3.1 | pre-register claims, marks, stops and the reading of every result | the pre-registration and reading guide, every cell, before any paid call | lessons §3.1 | general |
| L3.3 | plan the harm metric; show it next to success | harm next to success in every table | lessons §3.3; full report §5.9 | general |
| L3.5 | a real harm test needs a weak agent | H with gpt-5-nano | lessons §3.5; full report §7 | general |
| L3.6 | size the test first | power stated in the pre-registration | lessons §3.6 | general |
| L3.7 | fixes found on test conversations make those tasks seen | the "known tasks" label (section 7) | lessons §3.7; full report §4.1 | general |
| L3.10 | plan the diagnosis; save the conversation id with each answer | loss classes and script written before the run; ids saved | lessons §3.10 | general |
| L4.1-L4.5 | own approval per paid step; paid runs from the main chat; lenient stops; dry runs, audits, smoke test; finish script and an independent recount ready | the same order and tools in v4 | lessons §4.1-4.5 | general |
| L4.7 | claim dollars and the LLM share, not "fewer calls" | the pre-registration forbids a "fewer calls" claim unless shown | lessons §4.7 | general |
| L4.8 | known traps (tool arguments from the message; no LLM user in dry runs) | rules in the plan and the code | lessons §4.8; knowledge file §8 | specific to this harness |
| L5.2, L5.6, L5.7 | form check and cases before money; many agents owning their files; plan in one shot | the v4 build order and agent set-up | lessons §5 | general |
| — | one meaning per item, an exact scope (the user's manual audit of extracted policies) | supports rule 1; rules were not changed | `criticism.md` | general |

**Count.** Of the 31 rows, 27 are general, 1 is specific to this harness, and 3 carry task-specific detail (L1.3's
dropped lines, L1.6 found on one task, L1.14's "Yes." case). "General" means the rule would apply to any policy,
not that it was found on other data: v3's lessons file says that nearly all its evidence comes from v3's own test
runs on these tasks. That is why the label is "known tasks" (section 7).

*Sources:* `docs/planning/tracker_v3/lessons_learned.md` §1-6; `docs/reports/tracker_v3_full_report.md` §4.1, §5.9,
§6, §9; `docs/planning/tracker_v4/overview.md` §3, §6, §12; `build_brief.md`; `brainstorm.md` (event list only; its
design notes are not used); `reading_notes/tiny_questions.md`; `knowledge_retention.md` §5-8; `docs/reports/criticism.md`.
