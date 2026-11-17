# Tracker v3 Plan: Overview

> **STOP BEFORE REAL MONEY.** No paid LLM call and no network call until the user approves that exact step in the
> chat. Approving this plan approves no paid step. Paid runs start from the main chat only.

Date 2026-10-22. Status: **the $0 parts p1-p11 and p13 approved (2026-10-22 23:44 UTC, default answers); no paid
step approved.** The decision audit is in
p4. Live status, cost and time: `predicate_correctness/output/eval_v3/progress.md`.
Parts: `p1.md`-`p14.md`. Chat decisions: `brainstorm.md` section 11.

## The main idea
**No full LLM judge.** Every fact the guard uses is set by code, from the database and from what happened in the
conversation. Where a fact needs the meaning of words, **one tiny yes/no question about one or two messages**
decides it. Each question is asked once and saved. When the guard blocks, it says which fact of the rule is not met,
and what makes it true.

## The experiment in short (2026-10-23)
**What v3 learns, and what it does not**
- **What a tool does to the data is not learned.** v3 runs τ-bench's own tool code on a copy of the database, so it is
  exact on any task, seen or unseen (0 mismatches on 23,138 replayed calls; 0 disagreements on 14,335 database values).
- **Only the text-reading part is tuned:** hand-written rules and tiny yes/no questions that read the conversation
  (did the user say yes, which card the user meant, was private data shown). We tuned them while reading development
  conversations, so only this part can overfit.

**The data**
| role | data |
|---|---|
| build and fix ("train") | easy retail 500 (Stage A, 2,000 conversations) + hard train 66 (needed: airline exists only in the hard tasks) |
| check once, offline ("validation") | the val conversations (the hold-out, 206), opened once in p12 |
| final test | new live conversations in p14: **main claim on all 99 tasks**; val 33 shown alone as the leak check |
| never used | the partner's test 66 |

Numbers on the build data are **bug checks, not results**.

**The stages**
- **p1-p11 (done, $0): build v3 and check for bugs.** Freeze the old guard; write the 66 facts; database facts by
  τ-bench's code; the tiny questions; block messages. Aim: the code is right (0 errors; agrees with τ-bench's tools).
- **p12 (next; paid, about $2.4; needs approval): real answers to the tiny questions.** p12a: on the development
  conversations, a last bug check. Then v3 is frozen. p12b: once on the hold-out. Aim: does v3 work on conversations
  nobody looked at? The first real result.
- **p13 ($0): get the live run ready.** The 5th arm (Direct + facts), spend limits, runner, metrics, pass marks fixed
  before any data, dry runs with fake LLMs. Aim: the paid run cannot break or overspend.
- **p14 (paid, about $16; one approval per step): the live test.** New conversations: 99 hard tasks × 3 tries × 5 arms
  (no guard, Direct, Direct + facts, frozen TGR, v3). Aim: is v3 at least as good as frozen TGR on task success, with
  fewer LLM decisions? Do code facts help an LLM guard (Direct vs Direct + facts)?

**The goal in one line:** a guard that decides by τ-bench's code and tiny yes/no questions, with no big LLM judge, and
works as well on tasks it never saw.

**Honest expectations:** offline, the changes were small but clean (on build data, so not a result). The main test on all 99
tasks passes 90-98 % of the time if v3 equals frozen TGR (val 33 alone: only 47-66 %, so val is the leak check, not
the main test). A tie with frozen TGR, with fewer LLM decisions, is a good result.

## Why: what went wrong in eval v2
- The tracker read the database correctly. Where it changed a decision, the strong agent did much better.
- But the weak agent did worse (−0.040). The cause is one framing that we copied:
  - TGR's rule writer wrote every fact for a judge that **only reads the conversation**. So "the gift card has enough
    balance" became "*an earlier tool output shows* that the gift card has enough balance".
  - Our tracker followed that wording. All 31 lookups read "what was shown", and 22 answer **false** when nothing was
    shown.
  - So "is the balance enough?" turned into "was the balance shown?". The answer was false, and TGR told the agent
    "violated, do not repeat".
- The rest comes from the full judge: one long LLM call at every check, which reads only the last 24,000 characters.
  It sets 71 % of the values behind blocks.

## Which agent, and what we compare with
- **Online, only the strong agent (gpt-6-luna).** Companies that guard agents do not run cheap models, and it halves
  the cost. Every LLM role is gpt-6-luna: the agent, the simulated user, the LLM guards, and the tiny questions.
- **Offline ($0), all saved data, weak agent included.** With the strong agent, violations are rare: in the
  partner's runs, about 1 in 138 retail conversations without a guard. The saved weak-agent conversations hold most
  of the violation attempts, so they test whether v3 still **blocks** what it should.
- **The online tasks: every hard task we may use.** τ-bench is small: 685 tasks in all.
  - **500 retail "train" tasks** (Stage A) and **20 retail "dev" tasks** follow one easy template: the ids are given,
    and only 1-2 write actions are expected (334 of the 500 expect a single write).
  - **The hard ones are τ-bench's test set:** 115 retail + 50 airline tasks, with reads, several steps, refusal tasks
    and up to 20 expected actions (reads included; at most 4-5 writes). The partner split them into train 66 / val 33 / test 66, and **their test 66 is
    never used**.

  So the paid run uses **the 99 hard tasks we may use, × 3 tries**:
  - **val, 33 tasks** (23 retail, 10 airline; 6 refusal tasks). Clean: nobody tuned anything on it. Unseen. Shown alone as **the leak check** (the user, 2026-10-23);
  - **train, 66 tasks** (46 retail, 20 airline; 12 refusal tasks). Seen: the partner developed TGR on these, and our
    offline test uses their saved conversations. Still run: **the main claim is on all 99 tasks** (the user, 2026-10-23,
    after p13's power numbers). The leak can only touch the text-reading parts, not the database part.

  The 2,000 saved Stage A conversations stay in the $0 offline test. With 99 tasks × 3 tries, the run shows differences
  of about 0.06-0.09 with 80 % power (val alone about 0.11-0.16, train alone about 0.08-0.10; from the partner's
  saved runs on the same tasks). p13's power numbers (from the train runs): the main rule passes 90-98 % of the time on all 99 if v3 equals frozen
  TGR, but only 47-66 % on val 33 alone; so all 99 is the main test and val 33 the leak check.
- **Five arms, the same tasks, the same period** (an ablation):

  | arm | what it is | what it shows |
  |---|---|---|
  | **no guard** | the agent alone | in the partner's Phase 1 (train) runs no guard has the best task success with the strong agent; on val, frozen TGR is above it in retail (0.710 vs 0.667) and ties in airline (0.633) (`~/ShieldAgent/docs/RESULTS.md`); it shows each guard's cost |
  | **Direct** | one LLM call per step with the whole policy (the partner's baseline) | an LLM guard alone |
  | **Direct + facts** | Direct, plus the facts v3's code tracked, given to the LLM as checked facts | do reliable facts help an LLM guard? |
  | **frozen TGR** | rules + the full LLM judge | the bar to beat |
  | **v3** | rules + facts by code + tiny questions, no judge | our method |

  Direct + facts vs v3 answers the question: once the facts are reliable, are rules better than an LLM deciding?
  ShieldAgent is not re-run: the partner's results already show it far below the others (retail, val, strong agent:
  ShieldAgent 0.362 task success vs Direct 0.609).
- **The partner's repo:** we work from a copy at commit `1bacdb0`. Its 3 newer commits change only docs and one
  reproduction script, not the guards or rules. p1 re-checks this, read-only.

## The three changes
**1. Every fact is a state with a start value and an update rule.** Each fact has one source and two values, true or
false. A fact is false until its update rule makes it true.

| source | how it is set | example |
|---|---|---|
| database | read from the database copy at the check | the gift card balance covers the price difference |
| event | false until the event happened (a tool call that worked) | the user logged in; the agent looked order #W1 up |
| call arguments | read from the pending call | the cancellation reason is allowed |
| text structure | code on the text: exact strings, ids, positions | the user typed this email |
| tiny question | a saved yes/no answer about one or two messages, picked by code | this reply agrees to exactly this action |

A fact gets a "the agent looked it up first" part only where the policy says to check first: retail order status
("check its status before"), and airline modify / cancel ("the agent must make sure").

**2. The judge is replaced, not reduced.** Each of the 35 facts the judge sets today is split into a code part (which
message, which ids, which database values) and, where needed, one tiny question about the meaning of words. Sixteen
yes/no question types (K1-K16) cover all of them (p8). Rules for every question:
- the answer must quote words that are really in the message;
- "unclear" takes the blocking value;
- every new allow needs two keys: the question's yes, and the code part agreeing.

**3. Block messages are built from the rule itself.** No hand-written text per fact: that would be fitted to
τ-bench. The rules are small (82 of 98 rules have one fact; the largest has 6). So a table, made once per rule set,
lists for every rule and every true/false combination which facts must change to satisfy it. The message quotes the
policy sentence, names the unmet facts with their evidence, and says what makes them true. The advice depends on who
can make the fact true: the agent (do this step), the user when the policy says to ask (ask), only the user (do not
lead them), or nobody (not possible with these arguments). The simplest version (TGR's own message without "violated,
do not repeat") is built too, for comparison. The paid runs use the rule-built messages.

## Questions about a call: check lines built from the call (the K2 fix, 2026-10-23)
**What went wrong.** K2 asks "did the agent list the action's details before asking for a yes?" (policy S6: "list the
action detail and obtain explicit user confirmation"). Version 1 (p8) showed the model every option of every item and
asked for "every detail above". With real answers (p12a, 200 development conversations), K2 said no to good listings:
the agent named the items but not their options. The tiny guard blocked 207 times, the judge stand-in 31; K2 made 121
of the 211 disagreements with the judge. Fake answers (p8) and the stand-in (p11) could not show this: a question's
wording can only be tested with real answers.

**The fix (K2 version 2; definition `k2_fix.md`, code and tests `output/eval_v3/p12_k2fix.md`).** One rule: *the
message must state every argument of the call that the user can check, each in a form the user knows.* Code builds
one line per argument from the call and the database, and each line says which forms count (an item by its name or
id; a new item by its id or the options that change; a card by its kind and last four; an address by every non-empty
field; a flight by number and date). The question only asks whether each line is stated. The same batch fixed K4 and
K5 (data counts as the user's own unless the message says otherwise), K13 (a message that asks for nothing new is
no), the OR evaluator (an unclear part no longer hides the other branch) and the quote check (`**` marks and line
breaks ignored). After the batch, on the same 200 conversations: tiny blocks 155, stand-in 31 (a development bug
check, not a result). **Round 2** (approved 15:11 UTC, done 15:29; re-asked; then 122 blocks): quotes may come in pieces, and for a whole-list
argument (τ-bench's flight change takes every flight; the passenger change every passenger) the lines cover only what differs from the database. Kept
strict: a detail the user said themselves must still be in the agent's listing. Fixed on development data, before the
hold-out; the hold-out and p14 stay unseen.

**The general method for a new policy document** is written once, as a step-by-step recipe with the numbers behind
each step and a worked example (retail `return_delivered_order_items`), in `knowledge_retention.md` section 7. In
short:
1. Find the "state before acting" sentences of the policy.
2. Take the lines from the tool schemas' arguments, not from examples.
3. Fix the allowed forms once per argument kind.
4. For a whole-list argument, check only the difference with the database.
5. Code renders the lines; the model only matches text.
6. Give each question what it needs, or a stated default; code checks what code can know.
7. An unclear part must not hide another branch of an OR.
8. Let a quote come in pieces when a question has several lines.
9. Test the wording with real answers on a small development sample early; fix definitions, never single examples;
   then the hold-out, once.

## The decision audit (p4)
Checking a fact against the database is circular, because that is what the tracker does. So the audit uses outcomes:
1. find wrong decisions by τ-bench's labels: a block on an expected action that the database accepts and that never
   gets done;
2. locate the rule and facts that tipped each one (the rule table);
3. blame a fact definition or a rule by pattern, and keep a blame only if fixing it removes wrong decisions and adds
   none.

It costs $0 and runs **first**, on the eval v2 data, then again after v3. Wrong allows that did not hurt the task,
and missing rules, are future work.

## What we measure: is v3 better than the LLM judge?
Each is compared for frozen TGR (the judge), v2, and v3, on the same conversations. **Pass** = a pre-registered pass
mark; the rest is reported.

| group | metric | goal |
|---|---|---|
| **better decisions** (offline) | too-strict blocks: blocks on an expected action that the database accepts and that never gets done | down |
| | new allows that τ-bench's tool refuses on a check mapped to a v3 fact | 0 (pass) |
| | new allows on actions the task did not want (can be the agent's own mistake) | reported, by changed fact |
| | database facts that disagree with τ-bench's tool | 0 (pass) |
| | the 420 eval v2 harm checks: the changed fact equals τ-bench's tool label | 100 % (pass) |
| | wrong decisions by cause, from the audit (fact definition, rule) | down |
| **less LLM** | checks that need any LLM call | today 100 %; down to a small share |
| | values behind blocks set by an LLM | today 71 %; down |
| | LLM calls, tokens and dollars per conversation | whole conversation vs frozen TGR: from about −40 % to about +70 %, point about −13 % (estimate; the judge has 23-27 meaning-fact slots per conversation on these tasks; p8's dry run gives the real question count) |
| **no length problem** | all of the above, split by conversation length (< 12,000 / 12,000-24,000 / > 24,000 characters; the judge sees only the last 24,000) | v3 flat across lengths |
| **better advice** | blocks whose message says "do not repeat" although a step could fix it | 0 (pass) |
| | message checks: true values, valid next step, no leak before login | 100 % (pass) |
| | online: the agent does what the message asks (looks up, asks the user) | up |
| | online: the agent gives up or hands over after a block; blocks that end in the cap override | down |
| **the end result** (online, paid, strong agent, 99 hard tasks × 3 tries) | task success, paired by task, v3 vs frozen TGR | **main claim on all 99 tasks**: not clearly worse, the lower end of the 95 % range above −0.10 (pass); the val 33 result is also shown alone, as the **leak check**: if v3 − frozen TGR on val is clearly worse than on train (val's upper end below train's point estimate), the report says "possible leak" |
| | task success vs no guard, Direct, Direct + facts | **pre-registered secondary claims** (the user, 2026-10-23): S1 do code facts help an LLM guard (Direct + facts − Direct); S2 rules vs an LLM with the same facts (v3 − Direct + facts); each "better" / "worse" / "no clear difference" by its 95 % range. v3 vs no guard reported (each guard's cost) |
| | the 18 refusal tasks (no write is expected; mostly the user asks for something forbidden, 3 expect a transfer) | reported per arm: τ-bench success, and whether any write ran |
| | expected actions done; unwanted writes | up; not up |
| | "rule broken" by v3's own facts and rules | reported only (v3 enforces these rules) |

## What better facts can and cannot fix (eval v2, Stage A, frozen TGR)
| | strong agent | weak agent |
|---|---|---|
| conversations with no block at all | 382 of 500 | 126 of 500 |
| wanted actions blocked and never done later | 22 | 71 |
| tasks with a write the task did not want | 63 | 94 |
| tasks with a missed expected action | 122 | 176 |

Removing wrong blocks can add at most about +0.04 task success for the strong agent (eval v2 already got +0.026),
and at most about +0.14 for the weak one (a very loose upper bound). Most failures are the agent's own mistakes
(wrong item, a missed action) that no policy rule covers. So the expected gain is **more correct and much cheaper
decisions**, not a large jump in task success.

## How we know it is right, without a person
The objective labels come from τ-bench itself:
- **its tools:** would the database accept this call? (run on a scratch copy);
- **its expected actions** for each task;
- **task success.**

| what | checked by | pass |
|---|---|---|
| database facts | τ-bench's tool on a scratch copy | 100 % agree |
| event and structure facts | the saved conversation, and τ-bench's tools (an identity from the text must find the right user) | 100 % |
| tiny questions | the quote must be in the message; the two keys; disagreements with the old judge reviewed by an agent as a second opinion | 0 new allows that the tool refuses on a v3 fact |
| messages | every value re-checked against the database; every suggested step a valid call; no database value before login | 100 % |
| all counts | an independent agent recomputes them | equal |

**The gold scorer is not used.** It is regex-based, it was tuned on about 50 hand-read calls, and no one checked it
on the full data. Our facts and rules are its better replacement. "Rule broken" counts come from v3's own facts and
rules. Because v3's guard enforces those same rules, they are reported but never decide a pass.

## Frozen
Nothing in eval v2 changes. Its code and data are checked by a sha256 manifest. New facts, tables and code go in new
files, each with its own sha256. The frozen rule set is not changed: the new facts feed the same rules.

## Parts
| part | what | $ |
|---|---|---|
| p1 | freeze eval v2; rebuild every saved decision exactly; set the hold-out aside | $0 |
| p2 | the rule table: for every rule and true/false combination, which facts tip the decision | $0 |
| p3 | the τ-bench tool check, as a label | $0 |
| p4 | **decision audit** on the eval v2 data: wrong decisions by outcome, located by the rule table | $0 |
| p5 | the definition of all 66 facts: source, start value, update rule | $0 |
| p6 | database, event and argument facts in code; agreement with the tool check | $0 |
| p7 | text structure: message view, helpers, info classes, structure facts | $0 |
| p8 | the tiny questions: code part, question, two keys; fake answers only | $0 |
| p9 | the v3 guard, with no judge | $0 |
| p10 | block messages from the rule table, the simplest version, and automatic message checks | $0 |
| p11 | offline test on the saved data (a development check: the code is right; not a result); audit again — **STOP** | $0 |
| p12 | tiny-question answers on the saved strong-agent data (development: a bug check only, on a 200-conversation sample; it found K2 too strict, fixed on development data as K2 version 2, see "Questions about a call"); the hold-out once, the offline result; recount on the hold-out — **STOP** | about $0.3-13 (point $3.5); so far $0.13 |
| p13 | prepare the paid runs: the Direct + facts guard, spend limits, runner, dry runs, approval request — **STOP** | $0 |
| p14 | paid runs, strong agent only, one approved step at a time: smoke, then 99 hard tasks × 3 tries × 5 arms | about $15-22 (point $16.4), the p14 core |

Order: p1 → p14. p4 ends with a **STOP**: its result may change the order of p5-p10, and the user decides that.

## Money and time
Logged list-price dollars (the real bill is lower, about 0.55× here: 0.33× without a guard, 0.6× with one, because of cached input). Times are
wall-clock with several agents at once. Full table: `predicate_correctness/output/eval_v3/progress.md`.

| step | cost (estimate) | time (estimate) |
|---|---|---|
| p1-p11, $0 build and offline test | $0 | about 9-17 h of agent work, about 1.5-2 working days with the stops |
| p12: tiny questions on about 1,600 saved strong-agent conversations | $0.3-13, point $3.5 (2-27 questions per conversation at $0.00008-0.0003 each); hard limit $26 | 1-4 h (the development part is a bug check only) |
| p13: preparation (incl. the Direct + facts guard), audit, dry runs | $0 | 2-3 h |
| p14 smoke: 2 tasks × 5 arms | about $0.12 (high $0.48); hard limit $2 | 15 min |
| p14 main: 99 hard tasks × 3 tries × 5 arms (1,485 conversations) | $15-22, point $16.4; hard limit $45 | about 1.5-2.5 h |
| optional: 64 Stage A tasks with 3 or more expected actions (the hardest of the easy set) × 1 try × 5 arms | about $7 ($6.6-9.7; these tasks cost 2.2× the Stage A mean); hard limit $20 | +30-40 min |
| report | $0 | 1-1.5 h |

**v3 core total (p12 + smoke + main run) about $15-35 (point $20), everything about $22-45 (point $27). Proposed
cap $95: the hard limits $26 + $2 + $45 + $20 sum to $93, rounded up**, so the cap never stops a step that stays under its own
limit (eval v2 spent $40.38 with both agents and a judge). The limits are lenient on purpose: about 2× each step's
high estimate, so a normal run is never cut. Each paid step has its own approval and hard limit. **All in all, about 2-3 working days**, plus the time you
take at the stops.

Later, outside this plan: an **intent check** (does the call match what the user asked? It targets the agent's own
mistakes, which no policy rule covers; it can be sized for $0 with τ-bench's expected actions), the confirm button
for the agent (a new tool), and message forks.

## Decisions for you (my default on the right)
| # | question | default |
|---|---|---|
| Q1 | No full judge at run time, not even as a fallback? | yes |
| Q2 | "Unclear" tiny answers take the blocking value? | yes |
| Q3 | Model for the tiny questions | gpt-6-luna only |
| Q4 | A "looked it up first" part only where the policy says to check first (retail order status, airline modify / cancel)? | yes |
| Q5 | Messages built from the rule, with the simplest version as the comparison? | yes |
| Q6 | If the agent repeats the user's own words before login, is that *not* a data leak? | not a leak |
| Q7 | Can one "yes" cover several listed actions? Can one reminder cover later item changes in the same order? | yes, and yes |
| Q8 | The confirm button: later only? | later |
| Q9 | Paid part: strong agent only; cap $95 (the step limits sum to $93, rounded up); the test "v3 is not clearly worse than frozen TGR" (the lower end of the 95 % range above −0.10), on all 99 tasks, with val 33 alone as the leak check (the user, 2026-10-23, after p13's power numbers). p13 computes the real pass chance from the partner's saved runs on the same tasks (from the saved runs: about 0.90-0.99 if v3 equals frozen, 0.63-0.88 if it is 0.03 worse, 0.37-0.61 if 0.05 worse) | yes |
| Q10 | No gold scorer; "rule broken" from v3's own facts and rules, reported only | yes |
| Q11 | The paid runs use the rule-built messages (frozen messages would say "violated, do not repeat" on "not logged in yet", the eval v2 harm) | yes |
| Q12 | Online tasks: the 99 hard tasks we may use (val 33 + train 66, both domains), 3 tries each, main claim on all 99, val 33 alone as the leak check? | yes (the user, 2026-10-23) |
| Q13 | Five arms: no guard, Direct, Direct + facts, frozen TGR, v3? | yes |
| Q14 | Direct + facts gets the facts set by code alone (database, events, arguments, text structure), not the tiny-question answers: a fact with a tiny-question part is left out, its code part too, and the LLM reads meaning itself. Before login, it gets only true / false, no database values | yes |
| Q15 | The 64 hardest Stage A tasks (3 or more expected actions), 1 try, as an optional extra (about $7)? | no, only if the main run is unclear |

## Rules while working
- After each part: say only "done with part i", log it in `predicate_correctness/output/implementation_log.md`, and
  go on. **Stop** after p4 (the user picks the order of p5-p10), after p11, p12 and p13, and before every paid step.
- If a check fails: fix it on the development data and log the change. Never touch the hold-out; never move a pass
  mark.
- **Development data is for bug checks, not results** (the user, 2026-10-23): numbers on development data are not
  validated further or claimed. Results come only from the hold-out (p12) and the new conversations of p14 (main claim:
  all 99 tasks; val 33 alone as the leak check).
- Never write under `~/ShieldAgent`, `~/opt` or `~/venvs`. Never the partner's test group. Bash output always to
  `predicate_correctness/output/logs/v3_*.log`.

## Reference (for implementers)
- **Guard:** one new guard `TrackerTGRv3` (`guard/tgr_tracker_v3.py`), with three switches:
  - `facts`: v2 = eval v2's tracker; v3 = the new facts;
  - `meaning`: saved_judge = the judge's saved answers, offline only (strong-agent data until p12, weak-agent data
    always); tiny = the tiny questions;
  - `messages`: frozen = TGR's own; rule = built from the rule table; simple = TGR's own without the closing line.
- **Files:** one evaluator `state_tracker/v3/facts_format_v3.py`; new code under `state_tracker/v3/`,
  `guard/*_v3.py`, `fork/offline_v3.py`, `scoring/v3_*.py`, `tests/test_v3_*.py`; results in `output/eval_v3/`; figures `docs/reports/figures/v3_*.png`; approval requests and
  the online pre-registration in `docs/planning/tracker_v3/`; the final report `docs/reports/tracker_v3_report.md`.
- **Frozen** (sha256 manifest, p1): the v2 lookups, `predicate_types.json`, the rules, the runner copy,
  `guard/tgr_tracker.py`, `guard/run_online.py`, `guard/soft_stop.py`, `fork/points_tgr.py`, `state_tracker/replay.py`,
  `state.py`, `tau_copy.py`, `lookup_format.py`, all eval v2 and earlier run data (full list: p1 step 1).
- **Earlier designs and reviews** (some parts of them are replaced by this plan):
  `predicate_correctness/output/logs/v3_wf_result_{a,b}.json`, `v3_design_{c,d,e}_result.md`,
  `v3_crit_{a,b,c,d,e,all,plan2}_result.md`, and the plan check of 2026-10-23 (`v3_rev_cons_result.md`,
  `v3_rev_bench_result.md`).

| new file | sha256 |
|---|---|
| (filled in by each part) | |
| p1 `state_tracker/v3/frozen.py` | `d90e5db71eeba5acfe03717802672659db103ac65a7593a64d969d24bc890315` |
| p1 `output/eval_v3/manifest_eval_v2_data.sha256` | `5c85c90ca5f27938894b0af8c62647eba45ba068fc2d94800c00bd245c902c18` |
| p1 `tests/test_v3_frozen.py` | `5f26713d4036075253ad82852492a36ccb0d37ceb119ec314c2d551dff4c89dd` |
| p1 `tests/test_no_gold_import.py` (extended) | `b219333693d93ce21d1f6da50ac91d6e0ffb19524f7834b606d58431f306d1ed` |
| p1 `fork/offline_v3.py` | `7d2eec758bd08be6519a32839638a57bd5b78397dcb4b50fd3f27c35c1120e79` |
| p1 `tests/test_v3_offline.py` | `ce94a263eb37bd40d91e155084f9ff0d39496607e75381a8760a505e59e78d75` |
| p1 `scoring/v3_p1_gate0.py` | `65481afdb781f02852ba601918d29878e1c3fa0e5bde184d6434d3beee90625b` |
| p1 `output/eval_v3/p1_check_index.jsonl` | `59beac55ea66c341aabbb5df5b73637ea52a7ad1d5f89688ec65470ff97174f9` |
| p1 `output/eval_v3/split.json` | `f6996d5e3bc2ca05cd7b2f8651c7ce9d338ab2683d61b2aae3bc12482022ad09` |
| p1 `output/eval_v3/preregistration.md` (parts 1-2) | `efdf2d333415f1a3df0e365ba3ae10941490aadc9fe905afb8d07ace3ead34ed` |
| p2 `state_tracker/v3/rule_table.py` | `6593aa658c42641591d0f1b90ca90bc285ac1caae4a91927d82d9c9f311f77c5` |
| p2 `output/eval_v3/rule_table_retail.json` | `1d288c284351337e2316926d6ca0c68b5980fd5af2a6bdb22215202cb817cd3f` |
| p2 `output/eval_v3/rule_table_airline.json` | `ea2f654a6b5e7d5f1e99bf76e24c08aef4199e4516e1ce2074e5fc27ddbd0c69` |
| p2 `scoring/v3_p2_rule_table_check.py` | `ada3c1c03c06e4c6c8ca0a3a46d264efcd900e1352bfdd7c913c4c9af5bdefb8` |
| p2 `tests/test_v3_rule_table.py` | `cad21e87fd901ae3413b2d9771ac468b41a6b4857ae314709265395dab0fed6d` |
| p4 `scoring/v3_audit.py` | `e418902e213b2647a7cda3ad7b5550116242882163c4d9d8e206bcb52838d1d0` |
| p4 `tests/test_v3_audit.py` | `c9d185fb2dded7e6ee01ff249b8e1189092522cc5bf713192d96c7bfc09b2e62` |
| p4 `output/eval_v3/p4_audit.json` | `73361e3d7ae9432e3c8c9579b5a9aede952f3344e4090111cb18d040fa08d2f1` |
| p4 `output/eval_v3/p4_wrong.jsonl` | `609b6a74af5e3ee1414089fbf4bb7d7a7fb95d416d1de630c2adc1a02926f31e` |
| p5 `state_tracker/v3/facts_format_v3.py` | `8f67faa63525b093de3c19000ec6efc2d33a0aed25126acdaf501d3be7e3a36c` |
| p5 `tests/test_v3_facts_format.py` (isolated, 05:47) | `d8375dedc80fa594d7dba45198bda312066390fa31ae465270ae66a6ad29a908` |
| p5-p8 `state_tracker/v3/facts_v3_retail.json` (all expressions, after p8) | `d9cf7ebe0274b0b3a87c23275b308e892c7710ffb2bf47afc5aae05a31911247` |
| p5-p8 `state_tracker/v3/facts_v3_airline.json` (all expressions, after p8) | `0dea908f5c72a12fe37c3fc0869723682fddddfb3c5086395e709d6cf7f204b2` |
| p7 `state_tracker/v3/message_view.py` (after blind set 3) | `82cfe62555c2745514354c98daa61a41be9d12488e0633639e29fb6238cf8d89` |
| p7 `state_tracker/v3/info_classes.py` | `802233b28deec1d0496ec2cc7510db505b8c06faa61dd264bbffb0649db407ee` |
| p7 `tests/test_v3_message_view.py` | `3cd85a5a64c0ed84fb9ce9d566b8611c35387dccbf91d91df1d296247c0cad1b` |
| p7 `tests/test_v3_structure_facts.py` | `6057cf3b054fe206a8d03f1abce7ddd14c73f49e82a05f75653a7029be53bb0c` |
| p7 `scoring/v3_p7_structure.py` | `8930a4d4f752a0168796959caec98f8cbb4d8a79e274f6a66e45f8724536436b` |
| p8 `state_tracker/v3/questions_v3.json` | `ad585bc5fcf8aff914b13442e3722ede58fa6b6b12108200d540100caad60769` |
| p8 `state_tracker/v3/questions.py` | `7ef97fd25cb034fbe1514836841c5fa40497bc21ad7be3c11721fc623afec9ed` |
| p8 `tests/test_v3_questions.py` | `8d13823f58faf0cd7a4d9bccad2787f8322834abb1601328f61ec83c0ed37aa3` |
| p8 `scoring/v3_p8_dryrun.py` | `5b90f28d054c9c9be119a6150b927a6722a1850d125331ad10edfdaf2ff8aad9` |
| p6 `state_tracker/v3/code_helpers.py` | `53f08edd0675bb3bfc5ca60dcd0c26d3e98f6a903ca2e0203cc3b295789b090d` |
| p6 `tests/test_v3_code_facts.py` | `dd93962302941e8f3a38a0352eaf8a8de36606c7362c5fad004030a88b147aec` |
| p6 `scoring/v3_p6_agreement.py` | `9df0299653d589eb0f0122aefb743f2c36c34a74622ab2c51689fd2e37a0caa3` |
| p9 `guard/tgr_tracker_v3.py` | `645e060c48cf81706ced376fe7d37f2c2a1dfd333ff465e7ef84953f373003ea` |
| p9 `tests/test_v3_guard.py` | `0d842cd8ce9680418805c4350001e03c3a4835c99b8055217dc1bb6595e0ae66` |
| p9 `scoring/v3_p9_run.py` | `e9f3f458f4a150e12dd7a2cc48574e915f3da59262b18ee5d06ad8fe16ae747c` |
| p10 `guard/feedback_v3.py` | `d7c7085eaeb413e7f373e8a4eb5df112b5a191d80ef975174889316d21870f5d` |
| p10 `tests/test_v3_feedback.py` | `bcdb91ace1f4cdd4dbab28e831fd4025800e15865da2226462e95dfc663a439f` |
| p10 `scoring/v3_message_check.py` | `89a26565d8b8b4568db12cf9861e8e026227dfab7f994148d5360fc8e996a6a6` |
| p11 `scoring/v3_labels.py` | `060a827a543d4b2be46ff235d806e8b7ecd9793f90c52644636bba49c24964d4` |
| p11 `tests/test_v3_classify.py` | `0f9587a5a34e6dc445719fd3f9977248f4881aa83fe731c7271eb4b2475c7d90` |
| p11 `scoring/v3_offline_eval.py` | `d9483a7691b1b0c32e4d9902f22a051055006db51a04889cd270daea9b69478b` |
| p11 `output/eval_v3/p11_offline.md` | `5b66dd3a1401b2524a441ba6b5a38932516525411b7da3c5e9462d9c67eb93de` |
| p11 `output/eval_v3/p11_offline.json` | `98f6c59f2985088abe7ab3c2274fadb56ab0bcc69ff6c61e86e11e00825f8a29` |
| p11 `output/eval_v3/gates.md` (after the user's P7.2 decision and the label, 2026-10-23) | `7614169adde8b8b8b48e0e04768e685b05b3ec989c350f4f841689df822a8ba5` |
| p12 `output/eval_v3/p12_holdout_count.md` (count only) | `1c9e98f1d3191b188c748499c44f20924beb1035b980b8a2c8de18b659d1594b` |
| p13 `guard/soft_stop_v3.py` | `388552ddb483e803e000dbc0c4ea7461caa6c0a6cfc6496b42a13846a7feb29e` |
| p13 `tests/test_v3_soft_stop.py` | `518cd5234c45294d879e40f438d404b32eec17d60ebeb2d736b9be7149e43259` |
| p13 `scoring/v3_online_metrics.py` | `da44c1cbaf8547cb523661ab39d7d64e12691f1055b0cd349e21f7e3f2744a58` (after dropped groups, the all-99 main claim, S1 / S2) |
| p13 `scoring/v3_online_interim.py` | `acc21065ed202ef8ff3e02721adce219090657f7002d2cde39799a58863e2b1f` |
| p13 `tests/test_v3_online_metrics.py` | `8afa18e12878c44ac887d2a175804a83435ab6fef8f3487e8595dd9d15b4edee` |
| p13 `guard/direct_facts_v3.py` | `2ffcf20494b9dd2b2b73f611adf589d8e5adea9a5eb654075d438fe72f90f61d` |
| p13 `tests/test_v3_direct_facts.py` | `c84cc36a3ab81e85b2c9313a31ad8549aae35031c205786cc2388670200f0e0c` |
| p13 `guard/run_online_v3.py` | `a6834ea950366ae60bdffd5672f0754739b6c119a66181d11203209a98bea64c` |
| p13 `tests/test_v3_run_online.py` | `47790a311bc6c5db105a31a507a8ef60ce694032e2e4c684a278927d368ddaca` |
| p13 `output/eval_v3/online_tasks.json` | `5f7b9b71c727531c29cbe1ab8e7189b4bcf67195bb5b78f02437f98d08baf96e` |
| p11 `docs/reports/figures/v3_offline_changes_by_bin.png` | `11e2a67ebad715b00839993ba768db5c5c49d78445175b05a6f88111b1b2186c` |
| p11 `docs/reports/figures/v3_offline_llm_share.png` | `a7895f30e31f7b4a7b0f8b9e7cfb5d485d6ffb878b23af7dcd9584614ac5b6ef` |
| p11 `docs/reports/figures/v3_offline_audit_buckets.png` | `1bb537771f3be6cb692618fecc0fbe45ef957105fa0f46b80f9e954e9afa45cb` |
| p11 `output/eval_v3/p11_variants/` (8 files) | listed in `p11_offline.md` section 10 |
| p3 `state_tracker/v3/tool_check.py` | `493591328ad4687acb7361607d555f3f0b00527bec81cd3bd84300be58bbe21f` |
| p3 `tests/test_v3_tool_check.py` | `bed838aba965cf60ee1bcf447f31dc217dbb07c678ee3f8f0b27eadf89173b13` |
| p3 `scoring/v3_p3_labels.py` | `5f6c586f9457e4f3359821f133684d057ef8a8e815cf4941a7da9e588fd4bbbd` |
| p3 `output/eval_v3/tool_labels.jsonl` | `50673b1e2f21aaab2a63ace46b8a4c50802c4c81fb4d1f8d29a6a07753160134` |
| p13 `docs/planning/tracker_v3/preregistration_online.md` (frozen) | `9b385a58bf2b54ca2886066264c252967b5e40030d0e9c6c4bfc524608cae8cd` |
| p13 `scoring/v3_online_metrics.py` (after audit A) | `8f83b1f3934752ba65a333c885d94652f1653ccaf972dac37cd6340d4e81307f` |
| p13 `scoring/v3_online_interim.py` (after audit A) | `f30eba6d736a7b1cac4b7a2dee2bd2d76cfc592afdbe225a3a3faf28ba299c84` |
| p13 `tests/test_v3_online_metrics.py` (after audit A) | `e485ef158c2ae3cf2cb2ac1497c80877fd2ac27dffe31248ac834e5c412d683e` |
| p13 `guard/run_online_v3.py` (after audits B, C) | `45ee28bd8f19c46a302568c835f6f96c6e3b8f0b9746210f4217a8e62eef5fe1` |
| p13 `guard/soft_stop_v3.py` (after audits B, C) | `f83a04b44c5636af389d28d67169e446566f2800ff25ecd19043bc57d3b9a391` |
| p13 `guard/direct_facts_v3.py` (after audits B, C) | `3913e60019d098e7dfd9b675c50f18f7938a46be415f7f25c824bc0d0c0f704b` |
| p13 `tests/test_v3_run_online.py` (after audits B, C) | `2c49deba444a8a3d38c98a275b37a84ab962bb9d14bb1f51e8a48a47cd0d12d3` |
| p13 `tests/test_v3_soft_stop.py` (after audits B, C) | `5e917ebd1b1a7bbba3199c5696152d7d4d77808af0b1e20eef936165454f8d1d` |
| p13 `tests/test_v3_direct_facts.py` (after audits B, C) | `0a7ae7aab55fc4816cbca0572cb0f4a6bdaa23e88c1955f433cbfe4ccefd7355` |
| p12 `tests/audit_v3_ref_counts.py` (independent recount) | `05f6a33a4c8802890da4ca78e49bfa8dcb4b62dc9fc3b632e343885916219682` |
| p12 `scoring/v3_p12_report.py` (report builder) | `7f34d947cdae9658f1aa4db3659a36f0b2990ffe931498d37158252b11721628` |
| p14 `scoring/v3_p14_report.py` | `d06280f1cb014248397cd55ad27c540f0932c5bb97bce43a4b4f19b1eccb07a6` |
| p14 `scoring/v3_b1_summary.py` | `a239adcd2f2332f4de26de6c2efd6bb367b03ba1049a4fd98aee8c891a4d47e7` |
| p14 `tests/test_v3_p14_report.py` | `2723ff2db6c025a947fbb2e0860ede4bf10b9e472797ee729daec425531231c8` |
| p12 K2 batch `state_tracker/v3/questions.py` | `9be468138424e13608615dc608544c9c29eb03a623da83b6910eb96cc5a39094` |
| p12 K2 batch `state_tracker/v3/questions_v3.json` | `892b0ea5ace3084bedb950d9cb28300b5bae3ae6116b597c66456f45e4391ed0` |
| p12 K2 batch `state_tracker/v3/facts_v3_retail.json` | `0122a87da75543f824806612c346edc67d37e63a63464270216d20327a3f3eba` |
| p12 K2 batch `state_tracker/v3/facts_v3_airline.json` | `c49deb8c410247a0dd1b4f5d0a743a5148bf8e899d140595110d7c25f5f16783` |
| p12 K2 batch `state_tracker/v3/facts_format_v3.py` | `c4de3e63502e1ec8532e622f77333deb3faa066891c65c23b6578d75614ce727` |
| p12 K2 batch `guard/tgr_tracker_v3.py` | `ae4c7a938c1473138e415eac244a9c064c18d77f63a789e643e56a0779c103ff` |
| p12 K2 round 2 `state_tracker/v3/questions.py` | `0d43eb12827237ee147e23d14f6cccb21b191ddcd1c36f104b167a7acd27f4ab` |
| p12 K2 round 2 `guard/tgr_tracker_v3.py` | `3afdc3a5c0ab33d63bce874a6b171672f0f47718994bc719c2377ef3b434f377` |
| p12 K2 round 2 `tests/test_v3_questions.py` | `6a89a44e25c611ef905d80a60298354a41186726ac2915d3d884a19b6eb9b51c` |
| p12 `output/eval_v3/v3_freeze.md` (the v3 freeze) | `06eed629bd3b5544755d12fe5afe849050705ba58ca86f0da3892f80f86ee55f` |
| p12 `output/eval_v3/p12_report.md` (the p12 report) | `308d40f28d895572e04b5c943408c2d733d5c4116978305a91f74074e44830d5` |
| p12 `output/eval_v3/p12_recount_holdout.md` (P12.3) | `c190d30478cb239db0cc3bf92ec28f72f1d14aaa88020a4f47aa0cfca5fec304` |
| p14 `tests/audit_v3_online_recompute.py` (independent recompute) | `cac47600730c13962b335380fc634dcdc22c17f7597ec642df5da881f02f48a3` |
| p14 `docs/planning/tracker_v3/b2_reading_guide.md` (frozen) | `8c55bd3eb7db6a80a8681a28690d7e54489d676f95ca68f0aabbb08f2b894620` |
| p14 `docs/planning/tracker_v3/preregistration_online.md` (the frozen text plus change-log rows to 16:03 UTC; the pass marks are unchanged) | `75be03e75b2172a2e231cd14f06dc052cc308526c72ee3b32e997c27c90587ca` |
| current (16:52 UTC check) `tests/test_v3_message_view.py` (changed 12:01, the p12 helper fixes) | `352a66cb95f8346bad6223896d60bf822e0b871995d4323be0bcdcd555387dc1` |
| current (16:52 UTC check) `tests/test_v3_structure_facts.py` (changed 12:01) | `5eae5c8e7497da3b7431c51dbee0eb0b6c2fd16d1d4b4ac009019a74ee325244` |
| current (16:52 UTC check) `scoring/v3_p8_dryrun.py` (changed 12:00) | `aa086928b8d9d1fb0df54b172b765529824f7e8b0842268bb36b9ff05f8cfe96` |
| current (16:52 UTC check) `output/eval_v3/preregistration.md` (change-log rows to 15:36) | `2b6bc05e81a635ff9d498dec95944d4a61d0054848ef05aa994f36c5775f3e66` |
| p14 `docs/planning/tracker_v3/preregistration_online.md` (change-log row 16:54: B3 runs whatever B2 shows; pass marks unchanged) | `f7cf2ee19ca7223cce2a7eb69197e9296503ec0498019bd48268312d620355ac` |
| p14 B2 `docs/reports/tracker_v3_report.md` | `74abac003623689b029b21c907cf4712f57348a62ead2216f7926fe5e2a799d0` |
| p14 B2 `predicate_correctness/output/logs/v3_B2_B2_20261023T155537Z_c842d895_metrics.json` | `d8eff3564caccaf58b2323999b90176234af363ecc225c7d01b689fa6ba74423` |
| p14 B2 `predicate_correctness/output/eval_v3/B2/recompute_B2_20261023T155537Z_c842d895.json` | `21cc06d5736f43f2bd4d9cb5abcf3d851077ed1ba7b3722eac8fddefebc66edf` |
| p14 B2 `predicate_correctness/output/eval_v3/B2/recompute_B2_20261023T155537Z_c842d895.md` | `49394374b35c6ee9b2ea267989f0d1c91c687638b0928a59f5c8d07b46a5fb72` |
| p14 B2 `docs/reports/tracker_v3_full_report.md` (full report, B3 placeholders open) | `b2b7f92d54dedada6b5ee44dc708a3f5b90fdd1c21748f0117a18b722dd7e3e8` |
| p14 B2 `predicate_correctness/output/eval_v3/B2_val_diagnosis.md` (exploratory diagnosis / full report with it) | `aecca7ec772e178e4b37e2fd08e66a9f1baa2d45b95bd60ee7d977c984886975` |
| p14 B2 `docs/reports/tracker_v3_full_report.md` (exploratory diagnosis / full report with it) | `47e103ce97eb1bf2442bc043357c83490112ddf6bbbf51c0741a1fe48a76fd46` |
| p14 B3 prep `predicate_correctness/output/eval_v3/b3_prep/b3.patch` (not applied) | `e93c3645778e9b5a6c4d5f437cd49442f954df93e15ca8caa435d7b56ee72394` |
| p14 B3 `docs/planning/tracker_v3/approval_request_B3_draft.md` (final request, 17:25) | `b49fd1056653e32497a2bf2df0d7e14ef9db6bb1d45c522fda6fa4e5306354b4` |
| p14 B3 `docs/planning/tracker_v3/preregistration_online.md` (change-log row 19:08: B3 build and reading rule) | `6191455cd348f760232498066312af688efb07573d8df4ee6b5a454b5f516667` |
| p14 B3 build `guard/run_online_v3.py` | `0daab01d99c47203f3c5fb1bc7ab24afa1c0ae97f58c7c82ec9a7bc876b60cd7` |
| p14 B3 build `scoring/v3_online_metrics.py` | `daafa873bd8c1a018309cd6ad74ad1bda72ac1981a209cfb54e225c8d1f7da7e` |
| p14 B3 build `scoring/v3_online_interim.py` | `a95d098931536d95b0fb8fb5149d3e88ad12be3c7e303d8f535e46f17b07fa21` |
| p14 B3 build `tests/test_v3_b3.py` | `e9bcec2c38be2125d1ab20d7f83efe29c8dba04ab99dcd8770e0e3ecbd285293` |
| p14 B3 build `output/eval_v3/b3_tasks.json` | `0394a99ad08d3c832419f63333bc22b78096b993af5fb39c36c20a47917b33ff` |
| p14 B3 `predicate_correctness/tests/audit_v3_b3_recompute.py` (independent recompute) | `4fd7a006c6804914eb704df66999e2bf2d7a13f5ab525f92e3d0bc0723248f90` |
| p14 B2 `docs/reports/tracker_v3_full_report.md` (rewritten for easy reading) | `be6a01bb5b64d0ef36fe01be472399e40f29cd06eefe0cd51fb83b29e7fbfda7` |
| p14 B3 `predicate_correctness/output/logs/v3_B3_B3_20261023T190740Z_9bf882c0_metrics.json` | `1228419992ee1833b674b977927fca69e47c679ff886d1bac1ea7cab147c7f20` |
| p14 B3 `predicate_correctness/output/eval_v3/B3/recompute_B3_20261023T190740Z_9bf882c0.json` | `1afcbaab0cc27445b4cd3987195aac09c622d1f8e0ace858c91268be8d50f331` |
| p14 B3 `predicate_correctness/output/eval_v3/B3/recompute_B3_20261023T190740Z_9bf882c0.md` | `4c7faa57896deb94f4ef0312d00ff1ed6a15dcf520113ca5421f9ac9ac8040d3` |
| p14 B3 `docs/reports/tracker_v3_full_report.md` (with B3) | `01a63b88f8330d358ebec835f77173226e70d90fe22935c150c990aca8529a39` |
| p14 after-results (exploratory) `predicate_correctness/scoring/v3_harm_metric.py` | `69cf4595874e5fc22948f4619e3db15a08b83100702a7edd4effaa233c148922` |
| p14 after-results (exploratory) `predicate_correctness/output/eval_v3/harm_metric.md` | `a6e42dc850393851548620b96ddcdff0a3a9b246d9e5c6c8f5af9209440e6dee` |
| p14 after-results (exploratory) `predicate_correctness/output/eval_v3/tiny_question_audit.md` | `8c8fbd510cce934707f4f4b5a7b5c35e44caf82002a8e5c990173e5b36d12e22` |
| p14 after-results (exploratory) `predicate_correctness/output/eval_v3/B3_diagnosis.md` | `97ca73e135e7fedc78749817ed02216d21f4a0b4e186db6165bd3c253fac7c0b` |
| p14 after-results (exploratory) `predicate_correctness/output/eval_v3/direct_facts_diagnosis.md` | `15262d99bb09f357fe055764ea0ff1b7b39ebb54aa727dbe2d069d60c4e8d414` |
| p14 after-results (exploratory) `docs/planning/tracker_v3/next_steps_leak.md` | `bc886633e5145258e8d4041172a88355edafdb1a563a59600310d1fe27aa553e` |
| p14 `docs/reports/tracker_v3_full_report.md` (with the after-results findings) | `db686ce93591ce111f9b1d85e996281386e34d1cd2b1f89dd02ccdac69efdd19` |
| p14 `knowledge_retention.md` (after-results findings) | `1749660154e12c21ee6abb4e78ec0a564d72e1fcf14a78eec7956a498ff59dd0` |
| p14 `docs/reports/tracker_v3_full_report.md` (harm column in every arm table) | `51fe0d636ac1074aa819503a2baf29fa8080236856df6517be5c2a7f3b04f556` |
| p14 `knowledge_retention.md` (harm rows in the B2/B3 tables) | `6e59190a5affd4faa6473278dee91a90d458a51c309c06d30f8a9de7f236a825` |
| after p14 `docs/planning/tracker_v3/lessons_learned.md` | `1a254ae07827204bc9bdf0e625ac6324ecf3cf396b20abcabf7ef078464d92ce` |
| after p14 `docs/planning/tracker_v4/next_agent_prompt.md` | `36f6b640b8cb023b71dfb7de6af706d7666d8e7e0a487430fa1c604b5c4937fd` |
| after p14 `docs/planning/tracker_v4/next_agent_prompt.md` (unambiguous wording) | `6d603e4175ff299858572ff3270d154e1f437871153b1172c2bb8f23a2b9d213` |
| after p14 `docs/reports/tracker_v3_full_report.md` (reorganised / links fixed) | `de94d32e87c2d11fbb69cb2614b087b173831fbd92c91c21dac78885f9ba9dbd` |
| after p14 `docs/planning/tracker_v3/lessons_learned.md` (reorganised / links fixed) | `089c054decb4f19219a0e8ecc5cea2e1cee7b04789663752f7373328b3cd4568` |
| after p14 `knowledge_retention.md` (final) | `8eb172a654e4913f563ecd5b381b0e55302fc734f8739c8b30345b5688047be3` |
| after p14 `docs/planning/tracker_v4/next_agent_prompt.md` (final) | `eeb12654681e6b5d9c92a2426b793a6dc52effa2029b0ce50452ea771843eb84` |
