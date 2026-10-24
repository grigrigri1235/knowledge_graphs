# 9. A recipe for a new policy (generality)

**Main idea.** The v4 guard is made in two halves.
- **Half 1 makes the rules and the facts they need.** A *fact* (TGR calls it a *predicate*) is one yes/no statement,
  such as "the order is pending". The partner's TGR builder writes all rules and facts from the policy text and the
  tool list, with one LLM call per domain. No person edits a rule.
- **Half 2 is ours. It decides how each fact gets its value.** Code sets it where code can know it. Where words must be
  understood, a *tiny question* sets it: one short yes/no LLM question about one or two messages that code picks.

The **steps** of both halves are general, and they cost little API money. Most of the **content** made in half 2 was
written for τ-bench airline and retail: fact code, helpers, question texts and examples. A new policy needs it written
again. We do not know yet whether v4's tuned content works beyond the tasks it was built around. Every v4 result is on
*known tasks*. Only two slices were never seen by v4's checks: the weak agent (H) and 15 of the B3' tasks.

Words used in this section:
- **code fact**: a fact that code sets from the database copy, the event log (tool calls that worked), the pending
  call's arguments, or exact text checks.
- **window**: the messages a fact or question may read. It is written into the definition.
- **made-up cases**: short test conversations written from the policy by an agent that has not seen the question's
  examples. Each question gets 30 "yes" cases and 30 "hard no" cases.
- **dev check**: real tiny answers on development data, with pass marks fixed in advance. It checks for bugs and for
  over-strict blocking. It never gives results.
- **fix round**: one change to the question definitions (never to single examples) after a failed dev check. Then only
  the changed questions are asked again.
- **freeze**: a sha256 list of every method file, taken before any live run. After it, the method does not change.
- **overfitting**: the content fits the tasks, conversations or agent it was tuned on, and works worse elsewhere.
- **two-key disagreement**: a tiny answer says "allow" while the code part of the same fact says "block" (must be 0).
- **state error**: the guard's replay of the tool calls does not match what really happened.

Other terms (TGR, frozen TGR, B2', B3', H, arms, K1-K18, judge stand-in, val 33 / train 66, known tasks): see Glossary.

## 9.1 The recipe, step by step

**Inputs.**

| input | what it is | v4 example |
|---|---|---|
| policy text | one document, small enough for one LLM call. TGR's builder cannot split a long policy into parts | τ-bench v1 policy: airline 46 sentences, retail 38 (about 5-6 kB each) |
| tool schemas | tool names, arguments, descriptions | τ-bench v1 tool list |
| tool code and a database copy | to replay the conversation's tool calls and read the real state | τ-bench v1 tool code and its data files |
| development conversations | a few hundred saved runs of the agent in this domain, on tasks that will not be the test | v3's 200 (4 strong-agent sets × 50) |
| a reference reading | a second guard's answers on the same checks, used to measure strictness | the frozen TGR judge's saved answers on the same checks (the "judge stand-in", see Glossary) |
| a harness | the agent loop with a guard hook, a user simulator, a task score | τ-bench v1 plus the partner's loop |

**Steps.** "Person" means a human decision is needed. Costs are logged list prices.

| # | step | what is done | automatic or person | v4 example (cost, time) |
|---|---|---|---|---|
| 1 | cut the policy | drop the parts that only describe the world | a person picks the heading; TGR's filter drops it | the "Domain Basic" section: 753 of 6,155 characters (airline), 978 of 5,718 (retail); $0 |
| 2 | build rules and facts | TGR makes one LLM call. It writes the rules, the facts (each with a source label) and a label for every policy sentence (rule / exception / fact / not enforceable). Code checks the answer, allows at most 2 repair calls, and drops broken rules and exact duplicates | automatic. A person only picks the settings. One build is the result: no picking among samples | frozen builds: airline 2 calls, $0.017, 20 min; retail 1 call, $0.011, 8 min. Output: 98 rules, 66 facts |
| 3 | check rules against the policy | list sentences with no rule and those marked "not enforceable"; diff against any older policy version | an agent drafts, a person reads | 11 of 84 sentences are "not enforceable" (airline 7, retail 4). The τ³ diff found 1 conflict and several gaps; $0 |
| 4 | sort each fact: code or tiny question | first sort by TGR's own source label (only arguments or tool outputs → code). For facts that read messages, ask: "is this a string check or a meaning?" | an agent drafts one table row per fact; a person approves the plan (approval 1 of 3) | TGR's label puts 35 of 66 facts on arguments or tool outputs only. v4 sets 40 by code alone and 26 by code plus one tiny question. 12 question kinds, named K1-K18 with gaps (v3 had 16). 1 planning agent, $0 |
| 5 | write the code facts | expressions over the replayed database, the event log and the arguments; helpers; listing checks over a written window | agents, with unit tests | 3 agents at once, 41-66 tests each; $0 |
| 6 | form check | count with code how each value can be named. Read only the database and the policy, never task text | an automatic script. A person sets which files it may read | 0 of 239 retail and 0 of 503 airline card ids end in the card's last four, so ids are accepted; 40 form decisions; $0 |
| 7 | write each tiny question from its policy line | one meaning; the window written in; stated defaults; open words defined; a second wording used when the answer is "unclear"; 1 yes + 1 no made-up example, only where the yes/no line is hard to see | an agent writes; a person reviews the riskiest rows | 12 questions, 8 of them with examples; $0 |
| 8 | block messages | built from the rule table: the policy sentence, the unmet fact, the missing value and the value expected, and one step the agent can take. Plus a way out: a transfer is allowed after 2 tiny blocks on one write | automatic from the table | 1 agent; $0 |
| 9 | make up test cases | 30 yes + 30 hard no per question, from the policy. The writers do not see the examples. No case may nearly copy an example (text ratio under 0.9) | separate agents; code checks for copies | 720 cases by 3 writers; $0 |
| 10 | $0 checks | unit tests; fake answers (these test the code paths only); reference answers on the dev data; dry runs with 0 calls; read-only audits | automatic, plus audit agents | 3 audits found 5 purity slips; all were fixed; $0 |
| 11 | paid dev check | real answers on the cases and the dev data. Pass marks: ≥ 28/30 right per side per question; tiny blocks ≤ 1.5× the reference; unclear ≤ 2 %; 0 two-key disagreements; 0 state errors; 100 % of block messages fixable | the run is automatic; a person approves it (approval 2) | about $0.21 in all (limit $2) |
| 12 | fix rounds | read the failures by pattern; change definitions only; re-ask only the changed keys | a person decides each round | round 1: K3, K4, K13 texts. Round 2: a K3 wiring bug, and K13 now reads the agent's previous message. Blocks went from 120 to 37 (reference: 32). One fail accepted: K13 got 27/30 on hard no |
| 13 | freeze and pre-register | sha256 manifest; write down the claims, the harm metric, a reading rule for every cell, the stops and the loss classes | a script; a person approves | $0 |
| 14 | live test | smoke test, then the main runs; unseen tasks are run once | a person approves (approval 3) | 1,380 live conversations; estimate about $13; cap $30 |

**Time and money.**
- **API money is small.** The rules cost about $0.01-0.02 per domain. Building the values costs $0. The dev check cost
  about $0.21. The live test is the big spend.
- **Wall time is not small.** v4 reused all of v3's code and data. It still took about 10 h from plan approval (21:55)
  to the first real dev check on the 200 conversations (08:08):
  - 13 build agents and 3 case writers ran from 22:25 to 02:40. The plan said 1-1.5 h; this included a 2 h 15 min API
    pause.
  - The merge was at about 05:04. Tests, audits and fix round 1 came after it.
  - For comparison, v3 (the first build on τ-bench) took about 20.5 h.
- **A new domain must also make what v4 got for free:**
  - the harness and the guard hook;
  - the state replay on the new tools;
  - saved dev conversations: 200 at v3's B2 cost of $0.007-0.013 each is about $1.3-2.6 (an estimate);
  - a reference reading on those conversations.
  So expect an effort the size of v3, not of v4.
- **People are needed at six points:**
  1. the policy cut;
  2. the rule check;
  3. the sorting table;
  4. each paid step;
  5. each fix round;
  6. the purity wall (who may read which files).

*Sources: `reading_notes/tgr_build_method.md` §0-§3; `predicate_table.md` §0, §4; `overview.md` §6, §10-§11;
`progress.md`; `preregistration_v4.md` §12, §14 and change log; `session1_process_log.md` §9; `knowledge_retention.md`
§7.2; frozen `rule_set.json` source labels and sentence labels (counted at $0).*

## 9.2 What is general and what is specific to τ-bench

Labels:
- **general**: reuse as is.
- **rewrite**: the idea carries over, but the content is written again for each domain.
- **specific**: made for τ-bench airline and retail; drop it or redo it.

| v4 piece | label | why (with evidence from the τ³ port study) |
|---|---|---|
| rule and fact builder (TGR) | general, with a size limit | No domain words in the method (a test enforces it). It reads only the policy and the tool schemas. But it is one call over the whole policy: a 32k output cap, one label per sentence, made for about 5 kB. Its prompts were tuned on v1 train. A rebuild is a new random sample (airline rule counts across builds: 38/31/34/35/34) |
| "if code can know it, code decides"; the 5 sources (database, event, arguments, text structure, tiny question) | general | It needs the tools' code and a database copy |
| guard engine: rule table, fact evaluator, two keys for a new allow, "an unclear part must not hide the other branch of an OR" | general | The port study marks these "reuse as is" |
| state replay (the tool's own code on a database copy) | general idea, ported per harness | τ³'s own replay re-runs only writes and compares JSON. Port effort: medium |
| code facts (40 expressions) | rewrite, even for a new version of the same domain | They name v1 tools, arguments and fields. τ³ (same worlds) changed error texts and the shape of tool outputs, and its flight-change tool now updates the cabin |
| helpers (owner, flight on date, cabin now, bag rules, metro-airport alias table) | specific | They mirror v1 tool quirks: v1 never updates the cabin, and τ³ fixed that, so "cabin now" would be wrong there. The alias table was made by hand for 20 airports |
| window cuts (the span since the last worked write, the listing anchor, the go-ahead window, the current object) | rewrite | The idea fits any "list, confirm, act" policy. The key details for each tool (order id, items; reservation id, flights) are domain lists |
| forms table and form check (payment forms, ids, addresses) | rewrite | Rows per argument kind can be reused. The counts must be redone on the new data: the card-id trap is a property of τ-bench's data |
| fast path for a plain "yes"; strict-no list | general for English chat | exact whole-message matches; tied to the language |
| question-writing rules (one meaning, window, defaults, defined words, second wording, unclear handling) | general | the v3 lessons L1.x, not tied to a domain |
| K1 (the user said go ahead), K4 (another person's account) | mostly general | Any confirmation or ownership policy needs them. Small edits |
| K3, K6-K8, K10, K12, K16-K18 | specific | They name τ-bench things: "can be done only once", health or weather reasons, certificates, the two retail cancel reasons |
| K13 (the request is outside the tools) | rewrite, plus one specific part | The text form is general; the tool list and the refused list are per domain. The fix-round-2 exception is **specific and tuned on dev data**: "the agent said the rules do not allow it, and the user still asks" came from 30 airline transfer blocks, 24 of them on basic economy |
| way out (transfer after 2 tiny blocks on one write) | general, if the domain has a hand-over tool | |
| few-shot examples | rewrite | made up from the policy, but chosen with v3's loss types in mind |
| block message format (policy sentence / not met / missing + expected value / one step) | general | built from the rule table. The fact wording comes with each domain |
| Direct + facts (code facts shown as final values with their sign) | general | |
| dev check, pass marks, fix-round rules, freeze, pre-registration, harm next to success | general | |
| purity rule: build scripts read only the database and the policy, and a test enforces it | general | |
| agent loop and guard hook | specific to τ-bench v1 | On τ³ a blocked call must never enter the trajectory, because grading replays it. The guard has to sit in a wrapper agent. Port effort: large |

**What the τ³ study shows.** τ³ airline and retail are the same worlds as v1: the same users, orders, tools and
argument names. A port still breaks content:
- **Policy.** Gold members' free business bags went from 3 to 4. New lines have no rule: no cabin change after a flown
  segment; do not add bags the user does not need. So frozen rule 13 can block wrongly, and the new lines are missed.
- **Tools.** Error texts changed. A v1 cabin bug was fixed. A new retail price bug appeared.
- **Harness.** The guard hook has to move into the agent.

So even "same domain, new version" needs three things: the fact code re-checked, the error-text map rebuilt, and the
policy diffed. The guard engine moves as it is. An earlier pipeline in this repo (gpt-5-nano) read the same retail policy
and got 25 rules over 53 predicates; TGR got 64 over 24. So the rules depend on the builder. It also scored 100 % on
12 hand-made trajectories, which is far weaker evidence than v4's 720 blind cases plus dev data.

**Short verdict.**
- The process and the guard engine are general.
- For the content, only the writing rules carry over. The content itself is written again for each domain.
- A few pieces are tuned to τ-bench: the helpers, K13's exception, and the choice of examples.

*Sources: `reading_notes/port_map.md` §0, §4, §6-§9 and v1.0.1 errata; `tgr_portability.md` verdict, §2;
`tau3_airline_diff.md` §1-§2; `tau3_retail_diff.md` §0, §2, §5; `tgr_build_method.md` §3-§6; `predicate_table.md` §0,
§3; `fix_round2_plan.md`; `docs/reports/wiki_processing_report.md`, `wiki_full_fledged_aspm_report.md`.*

## 9.3 Have we overfitted?

**Main idea.** We cannot say yet.
- **The rules cannot be fitted to the tasks.** Their build reads no task, conversation or score, and v4 did not touch
  them.
- **The values were tuned, partly on data close to the test.** The table below shows on what.
- Nothing in v4 runs a new policy, so generality to a new policy is not tested at all.

**What was tuned, and on what data.**

| what | data it used | could it fit the test? |
|---|---|---|
| TGR's rule-writing prompts | 5 rounds on v1 train (66 conversations each, scored by the partner's rule checker) | partly: train 66 is in B2'. This is the same for every TGR arm, so no comparison changes |
| v4's lessons (windows, forms, defaults) | v3's losses on B2, B3 and the hold-out: the same 99 tasks and 49 of the B3' tasks | yes, in kind. Hence the "known tasks" label. They are general rules of asking, written before any v4 data, and they say nothing about which action is right |
| few-shot examples | made up from the policy, but 4 were chosen to target v3 loss types (K1, K3, K13, K17) | mild |
| form check | first read the instructions and expected actions of the B2' and B3' tasks. Then rebuilt on the database and policy only: 0 decisions changed | low after the fix, but the builders saw the counts |
| fix round 1 (the K3, K4, K13 texts) | 720 made-up cases | low for the tasks. It fits the case writers' reading of the policy |
| fix round 2 (K13 reads the agent's previous message; a K3 bug fix) | 200 dev conversations: 100 on easy retail tasks ("Stage A", eval v2's runs) and 100 on the hard **train** tasks; strong agent only | **medium**. The K13 change was read off 30 airline transfer blocks on train tasks that B2' runs again. Val 33 was not in the dev data |
| number of fix rounds | the pre-registration allowed one. Two were used, plus one accepted fail (user decisions) | a disclosed change to the agreed process |

**What v4's build and checks never saw.**
- **H's weak agent** (gpt-5-nano). All 4 dev sets are strong-agent runs. But H uses the same 99 tasks, so it tests a
  change of agent, not of task or policy. v3's own design data did hold weak-agent runs; v4 took only v3's lessons.
- **The 15 B3' tasks v3 never ran.** No v3 conversation exists for them, so no v3 loss lesson came from them. Caveats:
  - they come from the same Stage A pool as part of the dev data, so some may be in the dev sample (not checked here;
    a $0 check by task index can settle it);
  - the early form check read their instructions (later rebuilt);
  - they are not a random sample: they are the tail of v3's run order (pre-registration §17).
- **The partner's test 66, and any new policy:** never used.

**The "known tasks" label** (pre-registration §0). Every v4 number carries it, and no "unseen" claim is made (§18).
The 15 fresh tasks are **not reported apart** in the pre-registration: §5 has one B3' number on 64 tasks, and §18 bans
a new subset as a headline. So a 15-task number is a **reported-only split**. Its range is about 2× wider than the
64-task range (√(64/15) ≈ 2.1, so about ±0.3).

⟦TBD: v4 − frozen task success on H (reported only) and the H1 harm verdict, next to v4 − frozen on B2'⟧

⟦TBD: v4 − frozen task success on the 15 fresh B3' tasks vs the 49 tasks from v3's run (reported-only split)⟧

⟦TBD: v4 − frozen on val 33 vs train 66 on B2' (shown only, pre-registration §4)⟧

**Reading rules.**
- **H and the 15 fresh tasks.**
  - If v4 holds on H and on the 15 fresh B3' tasks as on B2': good sign it is not overfit. "Holds" means each point is
    within 0.10 of its B2' or 49-task point, and H1 (harm, v4 − frozen) reads "less harm" or "not more harm". It is a good sign because the
    weak agent lists, names and agrees in other words than the strong-agent dev conversations that shaped the windows,
    forms and examples, and because the 15 tasks gave v4 no lesson.
  - If it drops there (a point more than 0.10 lower, or H1 "not shown"): sign of overfitting. On H, to the strong
    agent's way of talking. On the 15 tasks, to the loss types of the 49 B3 tasks v3 lost.
  - Read it with care. The 15 tasks are few, have 1 try each and are not random, so treat them as weak evidence. If H is
    weak (no-guard harm at or below 17.8 %, reading guide §3.3), H says little.
  - The 0.10 band is borrowed from the guide's val / train rule. For H and the 15 tasks it is this report's reading,
    not pre-registered.
- **Val 33 vs train 66.**
  - If val's point is more than 0.10 below train's (the guide's "v4 does worse on the val tasks"): bad sign. It points
    to fitting to the train-task dev conversations of fix round 2, and it would repeat v3's pattern (val −0.131, train
    +0.030).
  - Otherwise: good sign. The dev fixes did not fit the train tasks.
- **Even good readings have a limit.** They show "not fitted to the strong agent, or to v3's B3 losses". They do not
  show "works on a new policy".

**Our view, without results.**
- Overfitting **to tasks** is probably small: no rule or action choice was fitted.
- Overfitting **to τ-bench** is real: the helpers, K13's exception, the few-shot picks, the forms counted on τ-bench
  data. This is the bigger risk for a new policy.

*Sources: `preregistration_v4.md` §0, §4-§6, §14, §17-§18 and change log; `reading_guide_v4.md` §3.3, §9;
`overview.md` §3, §12; `session1_process_log.md` §9; `tgr_build_method.md` §2; `knowledge_retention.md` §2;
`docs/reports/tracker_v3_report.md` (val / train); dev set names from `scoring/v4_offline_eval.py`.*

## 9.4 Open risks for a new policy

- **Vague policy lines.** Lines like "explicit confirmation (yes)", "another person" and "cannot be handled within the
  scope of your actions" each needed a defined word. A person must choose the reading.
  - The policy and the tool texts can disagree. For transfers, "the user explicitly asks for a human" is only in the
    tool's description; v4 followed the policy.
  - TGR itself marks 11 of 84 sentences "not enforceable".
- **Facts no code can see.** Some lines leave no trace in a tool or the database. An earlier pipeline in this repo, run
  on a record-retention handbook, turned actions like "reading or printing documents" into facts. Such facts fall back
  to tiny questions or to nothing.
- **No tool code or database copy.** v4's 40 code facts rest on replaying τ-bench's own tool code: 0 mismatches in
  23,138 replayed calls. With a closed API, code sees only tool outputs. Reading world facts as "was it shown?" caused
  eval v2's harm (lesson E3).
- **Long or many-document policies.** The builder makes one call, has a 32k output cap and gives one label per sentence.
  A policy of hundreds of documents (`overview.md` §1) needs new merge code, and then it is no longer the partner's
  method.
- **Policy versions.** A changed number (3 → 4 bags) makes a frozen rule block wrongly. New lines go unguarded. A
  rebuild is a new random sample, because the builder has no seed.
- **Question drift.** Tiny answers depend on the model (gpt-6-luna, low effort). A new model or effort level needs a new
  dev check. Some unclear answers are still not explained: 14 of 15 were K13 first-wording unclears on long messages.
- **Strictness.** One too-strict line can lose many tasks: v3's K2 cost the B3 loss (−0.245). v4's 1.5× mark caught a
  3.75× case. On a new domain, that mark needs a reference reading, which must be made first.
- **People's time and purity.** The API spend is cents; the human part is not. v4 needed:
  - 3 approvals;
  - 2 fix-round decisions;
  - 1 accepted fail;
  - fixes for 5 purity slips that audits found, made even with written rules.
  On a new policy, fix the dev / test split before any agent reads a task, and enforce the read limits in code.
- **Scope.** One benchmark, two domains, a simulated user, English, one strong agent for building. The forms table
  covers only τ-bench's argument kinds.

*Sources: `dev_check_fail_notes.md`; `fix_round2_plan.md`; `tgr_build_method.md` §3-§5; `tgr_portability.md` §2;
`knowledge_retention.md` §1, §6.5, §7.5; `predicate_table.md` §2; `docs/reports/wiki_processing_report.md` §3;
`overview.md` §1.*

---

## Appendix C: checklist for a new policy (one page)

**Before you start**
- [ ] One policy document, small enough for one LLM call. Note any part that only describes the world.
- [ ] Tool schemas, the tools' own code, and a database copy. If there is no code: plan for output-only facts.
- [ ] A harness with a guard hook. Blocked calls never reach the real tools.
- [ ] A written data wall: dev tasks, test tasks, and tasks never used. Code enforces who may read what.
- [ ] Saved dev conversations (about 200, including 3+ write tasks) and a reference reading on them.

**Rules (half 1)**
- [ ] Run TGR once per domain at the fixed settings. One build is the result: no picking, no rule edits.
- [ ] List sentences with no rule and those marked "not enforceable". Diff against any older policy.

**Values (half 2)**
- [ ] One row per fact: source, exact rule, window, expected answer, how sure, unclear handling, block message.
- [ ] Code decides everything code can know (database, events, arguments, string checks).
- [ ] Form check by code on the database and the policy only. Accept every real form.
- [ ] Each tiny question: one meaning, a written window, defaults, defined words, a second wording.
- [ ] Unclear on a write: ask again, then block. On a transfer or login: ask again, then allow and log.
- [ ] Examples (1 yes + 1 no) only where the boundary is subtle, made up from the policy.
- [ ] Block messages from the rule table, naming the missing value. A way out after 2 tiny blocks.

**Tests before money ($0)**
- [ ] 30 yes / 30 hard no made-up cases per question, by blind writers; check for near copies.
- [ ] Unit tests, fake-answer run, reference-answer run, 0-call dry runs, read-only audits.

**Dev check (paid, small, approved)**
- [ ] Pass marks fixed first: ≥ 28/30 per side; tiny blocks ≤ 1.5× the reference; unclear ≤ 2 %; 0 two-key
      disagreements; 0 state errors; 100 % fixable block messages.
- [ ] On a fail: read the failures by pattern and fix definitions only. Fix the number of rounds in advance; any extra
      round is a written change.

**Freeze and test**
- [ ] sha256 manifest of every method file. Pre-register claims, harm next to success, a reading rule for every cell,
      stops, and loss classes.
- [ ] Smoke test, then the live runs, each approved. Unseen tasks are run once.

**Report**
- [ ] Label the data honestly (known / seen / unseen). Report results next to the old guard, never in its place.
- [ ] Report less-seen slices (new agent, fresh tasks, val) apart, as overfitting checks.
