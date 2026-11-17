# Tracker v3: brainstorm

Date 2026-10-22. **Thoughts only.** No code, no runs, no money. The plan is in `overview.md` and `p1.md` to `p14.md`. **Section 11 (the chat decisions) replaces anything in sections 1-10 that disagrees with it** (for example "unknown" as the fix, the gold scorer as a second reading, the v3a-min / v3a-db variants, and the old part numbers).

Sections 1 to 9 are my own notes, written before the read-only agent brainstorm. Section 10 holds what the agents
(5 designers, 5 critics, 1 completeness critic) added or refuted, and what I changed because of it. Where section 10
contradicts sections 1-9, section 10 wins.

---

## 1. Where we are, in three lines
- The tracker reads the database right (replay exact, 7,168 of 7,168 outputs; right in 213 of 216 reviewed disagreements).
- Where it changes a decision for the strong agent it helps a lot (+0.52 per changed decision), but that is 3 % of conversations.
- For the weak agent it hurt (−0.040), not through decisions but through the **message**: "not shown yet" was coded as
  **false**, so the agent read "violated, do not repeat" instead of "look it up".

So the method must change in three places: the *value* a fact gets when the information is missing, the *message*
the guard writes, and *who* sets the facts about meaning (35 of 66 facts, 71 % of the values behind blocks).

## 2. The one principle behind part (a)
A fact has three values. The decision formula (`mln.decide`) blocks on **false and on unknown alike** (one rule with
one unknown condition: P(run) = (e+1)/(3e+1) = 0.41, margin −0.19, below −ε = −0.10, so blocked). So the value changes
only the **message**, never the decision, for a required fact.

Rule for the value:
- **true**: the state shows the condition holds;
- **false**: the state holds the information and it **contradicts** the condition (balance $17 < difference $32; order
  shown as "delivered" when "pending" is required; the user said "no");
- **unknown**: the information is **not in the state yet**, and a next step can bring it (the order was never looked
  up; the user has not replied yet; no login worked yet; the gift card was never shown, if we read the fact as "shown").

Then feedback.py's two kinds of advice fit: unknown → "do X first, then try again"; false → "this breaks the rule;
offer an allowed alternative". That is exactly the eval v2 lesson.

## 3. World facts, agent-step facts, events (part a)
Three readings of a code-type fact:
| reading | what decides the value | not available → | example |
|---|---|---|---|
| **world** | the database copy (`db(...)`) | unknown only if the id in the call does not exist | gift card balance covers the difference |
| **agent-step** | what tool outputs showed (`shown(...)`) | unknown ("check first") | order status checked pending |
| **event** | the event log | unknown ("do it first") | user authenticated |
| **argument** | the call's arguments | unknown (malformed call) | cancellation reason allowed |

Which reading for which fact: the **policy sentence** decides. "You should check its status before taking the action"
(retail cancel, modify, return, exchange) is about the agent's step → agent-step. "It must have enough balance" (S17,
S26, S36), "the same product but a different option" (S23, S33), "different from the original payment method" (S16),
"the original payment method or an existing gift card" (S29), and all the airline facts about the reservation (cabin,
insurance, used segments, passenger count, baggage total, route) are about the world → world.

My draft table (to be checked in p2):
- retail world: `gift_card_balance_covers_price_difference`, `gift_card_balance_covers_order_total`,
  `item_replacements_are_available_same_product_different_option`, `payment_method_differs_from_original`,
  `return_refund_method_is_original_or_existing_gift_card`;
- retail agent-step: `order_status_checked_pending`, `order_status_checked_delivered`;
- retail event: `user_authenticated`; retail argument: `cancellation_reason_is_allowed`, `payment_method_is_gift_card`;
- airline world: the 14 "database fact" predicates (membership ×3, payment methods in profile, cabin ×3, insurance,
  no used segments, segments unchanged / changed, route preserved, baggage total, passenger count);
- airline argument: the 7 argument predicates.

Two variants to evaluate apart, because they differ in what they change:
- **v3a-min**: keep "shown", but "not shown" → unknown. Changes only messages (same decisions as frozen TGR where the
  judge said unknown).
- **v3a-db**: world facts from the database. Changes decisions too: a balance that was never shown but is enough →
  true → allow. The policy allows it (S36 says the card must have enough balance; it does not say the agent must look).
  The guard then knows something the agent never looked up; the message must not leak data before authentication.

Why the database is safe here: τ-bench's own write tools check the same facts (status, item availability, payment
method existence, gift card balance, refund method, passenger count, flight availability; see
`output/logs/v3_scout_tool_errors.log`). A world fact that is false by our lookup is a call that τ-bench refuses.

**The tool oracle (objective label for world facts, $0).** At any check, run τ-bench's own tool for the pending call
on a *scratch copy* of the state and read the result. Its `Error: ...` text names the failed check. Map each world
fact to its check: "insufficient gift card balance" ↔ covers; "non-pending order" ↔ status pending; "new item ... not
found or available" ↔ replacements; "payment method should be either the original ..." ↔ refund method;
"number of passengers does not match" ↔ passenger count. The checks run in a fixed order, so if an earlier check fails
the later facts are undetermined by the oracle (report them as "not decided by the oracle"). This label does not
depend on the judge, the gold scorer or a person. It also works on blocked calls, which never ran.

Limits of the oracle: the tools do not check everything (no check for "reminded", "confirmed", membership for the
baggage rules, 24 hours, insurance reasons). Those stay with the other labels.

## 4. Exact messages (part b)
Today's message (feedback.py) prints each predicate with its value and the judge's evidence, then a generic "What to
do". For tracker-set facts we know the exact numbers, so the message can say them and name the next step.

Idea: every v3 lookup carries `facts` (named sub-expressions: balance, difference, status, order id) and a `message`
template for each value (false / unknown), filled from the recorded reads. The "What to do" line then is specific:
- unknown, agent-step: "Order #W123 has not been looked up in this conversation. Call get_order_details(order_id='#W123') first, then try again."
- false, world: "Gift card gift_card_123 has a balance of $17.00; the price difference is $32.00 (new items $80.00, old items $48.00). Ask the user for another payment method from their profile, or a gift card with enough balance."
- false, agent-step: "Order #W123 was last shown with status 'delivered' (get_order_details, step 4). Only pending orders can be modified. Tell the user."
- unknown, event: "No successful login yet. Call find_user_id_by_email(email=...) or find_user_id_by_name_zip(first_name=..., last_name=..., zip=...) first; ask the user for these if you do not have them."
- judge-set facts keep the judge's evidence text unchanged (frozen TGR's words), but get the same "do X first" or
  "contradiction" advice kind (section 5).

Information safety: before a login worked, the message names only what the user typed or what a tool already showed;
it never prints profile or order data from the database.

How to know a message is right without a person: every number, id and status in a message is re-derived from the state
by a checker (an "all quoted facts exist in the state" test on every saved check); the named next tool call must be a
real tool with valid arguments; and the behaviour effect is measured only online (part e), with the offline count of
"same decision, different message" as the $0 proxy.

## 5. Advice kind for judge-set facts (parts b and c)
The judge says "false" for "the agent did not remind the user" (its prompt: a fact that something happened earlier is
false if it did not happen). Under section 2 that would be unknown (the reminder can still be given). I do not want to
change the judge's values (frozen prompt, comparability). So I split the two things:
- the **value** stays the judge's (true/false/unknown) for the decision;
- the **advice kind** is a fixed attribute of the predicate: *do-first* (reminder, listing, ask the user, look it up,
  log in) or *contradiction* (balance too low, status wrong, user said no, another user's data). The "What to do"
  section uses the advice kind, not the value.

For tracker-set facts the value and the advice kind agree by construction (section 2). This way parts a, b and c tell
the agent the same kind of thing for the same kind of fact.

## 6. Fewer judge facts (part c), in three steps
**c1, structure code, $0.** Code over a "message view" (user messages, agent text messages, tool outputs, in order,
plus the pending call and the shown objects): `user_typed(value)`, `agent_listed(args)` (every id-like argument, or
its shown form: item id → product name and options), `reply_after(listing)`, `reply_is_no_or_question`, phrase screens.
Safety rule (from the idea file): a new **allow** needs two keys. Code alone may set an allowing value only for exact
string facts (identity strings, ids in the listing, "nothing shown yet so nothing disclosed", "the call's object
belongs to the logged-in user"). Code alone may set a *blocking* value only on clear structure (no user message after
the listing; the listing lacks the order id). Everything else stays unknown → the judge's value (as version b today).
Expected on the saved train data (idea file): about 79 of 537 blocked checks removed (56 disclosure blocks before any
tool output, 23 identity blocks with a cut view).

**c2, one tiny saved question per message, small money.** About 8 yes/no questions (reminder? explicit yes to this
listing? about another person? health or weather reason? complaint about a cancelled/delayed flight? asks for
compensation? reply offers a certificate? reply does a task for another person?). Input: one message (plus the
listing for the "yes" question). Output: yes / no / unclear + a quote that code checks as a substring. Cached by
(message text, question). Never cut by a 24,000-character view. It is the second key next to c1. When every fact of a
check is set by code + labels, the judge call is skipped (up to 72 % of checks: 2,178 reply checks and 1,344 retail read
checks). Labels cost money even on saved data, so they go to part (e) as the cheapest paid step.

**c3, confirmations as fixed events, paid.** The agent gets a `confirm_action(action, arguments)` step: the loop sends
the listing to the simulated user as a message and records a structured event; the user's reply is parsed by c1 + c2.
The rules then read an event, not meaning. This changes the agent's tools and prompt, so it is a **new agent variant**:
it cannot be tested on saved conversations, only with fake LLMs ($0) and then in new runs (part e).

Reading questions for the person (few, with my defaults): repeating the user's own words is not disclosure (default:
yes); a "yes" must follow a listing that names the order id and every changed id (default: yes, strict); one reminder
covers later item changes in the same order (default: yes).

## 7. Offline evaluation, $0 (part d)
Data: Stage A 2,000 (retail, both guards, both agents), our 495 (TGR + tracker, airline + retail, train + val), the
partner's 495 (frozen TGR, train + val). Never the partner's test group.

Method: for every judged check, run frozen TGR and each v3 variant offline (`OfflineGuards` style: the guards' own
code, the judge's saved values for the facts v3 does not set). First the check: the offline guard reproduces every
saved decision (100 %, as `decide_again` check 1). Variants: v3a-min, v3a-db, v3b, v3c1, and all together. Count
**changed decisions** (blocks removed / added) **and changed messages** (same decision, different message; classify:
unknown ↔ false advice, exact facts added, next step named).

Labels:
1. **τ-bench's expected actions**: a write check whose call equals an expected action (same tool, same arguments) is a
   *wanted* write. Block removed on a wanted write that ran later anyway: good. Block added on a wanted write: suspect
   (right only if a confirmation was really missing: check with the gold v2 regex as a second reading). An executed
   unwanted write that v3 would block: good. An executed write with a gold v2 violation that v3 would allow (it was
   allowed before too): unchanged.
2. **The tool oracle** on every world fact (section 3).
3. **GOOD task success** of the saved conversations, split by "v3 changes at least one decision / message in it" vs
   not. Descriptive only: the conversation is fixed, so this tells where the changes land, not what they cause.
4. **Reuse of the 619 paid Stage B tries**: at the 175 forks, v3's offline decision equals branch A or branch B. Where
   it equals B, the measured B − A effect is v3's effect at that fork, for free. Expected overall effect = effect per
   fork × v3's fork rate (strong agent only: the weak agent has about 1 try per side).
5. Gold v2 as a second reading on write checks.
6. Judge calls that v3 would skip → cost per conversation.

Split by conversation length: history characters at the check; bins under 12,000 / 12,000–24,000 / over 24,000
(cut). All counts per bin.

Pre-registered gates before any paid step (numbers to fix in p9): 0 new allows on an executed write that the tool
oracle or gold v2 flags; v3a-min turns ≥ 90 % of the eval v2 "unknown → false" message changes back to "do X first";
every message passes the facts-exist checker; the offline guard reproduces 100 % of saved decisions.

Verification of the evaluation itself: an independent agent recomputes the main counts with its own script; the
method code never imports gold (`tests/test_no_gold_import.py`, extended to the new folders).

## 8. Optional paid run (part e)
Candidates, each with its own approval, started from the main chat, dry run first:
- e1: tiny-question labels on the 396 saved train conversations: 2,470 user messages + 2,074 agent messages + pending
  replies, about 8 questions where they apply, at the judge's price ($0.00056 per call) → about $2–4 (estimate).
- e2: Stage B between frozen TGR and v3 at **decision forks and message-only forks**, 5 tries per side: price per try
  from eval v2 (luna $0.0048, nano $0.013–0.015). Number of forks unknown until part d; 200 forks → about $25.
- e3: a smaller Stage A on the same 500 retail tasks, v3 vs frozen TGR, weak agent first: about $21.5 (weak), $11.3
  (strong).
- e4: the confirm-event agent variant (c3): new runs only; after e2/e3.
Recommended order: e1 (cheap, unlocks c2 offline), then e2 (direct message test), then e3, then e4.

## 9. What stays frozen, what is new
Frozen and byte-identical (a test checks the sha256): `state_tracker/lookups_*.json`, `output/predicate_types.json`,
`from_shieldagent/rules/`, `guard/tgr_tracker.py`, all of `output/eval_v2/`.
New: `state_tracker/v3/` (lookups_v3_<domain>.json with reading / if_missing / facts / message, structure_v3_<domain>.json
for c1, questions_v3.json for c2, the evaluator extensions), `guard/tgr_tracker_v3.py` (guard name `tgr_tracker_v3`,
own `FROZEN_SHA256`), `scoring/v3_*.py`, `tests/test_v3_*.py`, `output/eval_v3/`. Logs: `output/logs/v3_*`.

## 10. What the agents added, and what I changed because of it
Agents: 5 designers (a, b: earlier run; c, d, e: this run) and 6 critics (a, b, c, d, e, completeness). All
read-only, $0. Their results: `predicate_correctness/output/logs/v3_wf_result_{a,b}.json`,
`v3_design_{c,d,e}_result.md`, `v3_crit_{a,b,c,d,e,all}_result.md`, with their logs `v3_design_*`, `v3_crit_*`.

### 10.1 Corrections to my own sections 1-9
| my earlier idea | what the agents found | now in the plan |
|---|---|---|
| §2: unknown whenever the information is missing | `user_authenticated` before a login is *known*: the event log is complete. Unknown would open a two-unknown allow on rule 3 (margin −0.086). | false before login; the advice still says "log in first", because the advice comes from the kind (p2, p6) |
| §3: nonexistent id → unknown | no look-up can make it exist; unknown would loop until the cap | false, with an explicit test that every circuit still blocks it (p2) |
| §3: all airline reservation facts are world facts | airline lines 44 and 58 ("the agent must make sure ...") give the same duty to check as retail's "check its status before" | default agent-step for A11-A21; the db reading is an extra offline column (p2, p3, Q2) |
| §3: run the tool oracle at runtime for the balance facts | after an earlier failed check the oracle is undecided → an unknown no look-up fixes | exact expressions with each tool's rounding; the oracle is a test only (p3, p4) |
| §6 / design a: merge c asks the judge only the non-code facts | that changes the judge's prompt, so the saved judge values no longer apply and the cache misses; and "skip when only code facts" never happens (0 of 38,579 checks) | judge prompt unchanged, code-fact answers ignored (p5). No assumption about the judge is needed offline |
| design a: A21 "a past segment = flown" | 22 reservations have only *cancelled* past segments, which were never flown (v2 has the same bug) | cancelled past segment = not flown (p3) |
| design b: "tell / ask facts are never violated" | a user's clear "no", and a call that differs from what the user gave or confirmed, are real contradictions | new kind `match`; a strict "no" forbids the same call (p6) |
| design b: closing line chosen by a general rule | scope false and the airline compensation preconditions would end with "call transfer again" | an explicit `same_call_forbidden` per (kind, value) (p6) |
| design b: `me` = the call's user id (airline) | the agent can type any id, so the ownership check always passes | airline `me` = a user id the user typed (c1); retail `me` = the first login (p7) |
| designs a + b: two guards under one name, two evaluators | the b guard would have run v2 values; numbers could differ (rounding) | one class `TrackerTGRv3` with flags, three hooks; one evaluator (p5, p6, p7) |
| design b: one exception in the message code | `TGR.step` retries the whole step 3 times, then raises: the episode crashes | try/except → TGR's own message, counted; gate 0 fallbacks (p7) |
| design b: V1 "re-derive every number" | circular: same expressions, same state | a separate database-field reader + the oracle (p8) |
| §6: c1 may block on listing / yes structure | strict listing rules contradicted a judge "true" in 37-101 checks; the judge was right in the samples (earlier listing; one yes for several actions) | c1 blocks only on whole-conversation absence or a strict "no"; screens never block (p9) |
| §7: Stage B forks at message points in the core | with v3 messages almost every block is a "message fork"; that would wipe out the decision evidence, and e2 detects only about +0.09 per fork for nano | decisions measured with `messages=frozen`; message changes counted per block; message forks moved to "later" (p12, p15) |
| §7: our 495 and the partner's 495 as two data sets | they are the same 495 (task, trial) pairs | one paired set; bootstrap by task (p1, p12) |
| §8: e2 / e3 order, $57-68 | the smallest step that answers the weak agent's question is a paired 500-task run; the strong-agent "enriched" subset misses new blocks; the point-estimate rule cut the power from 0.79 to 0.65; logged prices skip the cached discount | core = smoke + weak + strong ≈ $32.5, cap $50; non-inferiority; prices called upper bounds (p14, p15) |
| git as the freeze check | the frozen code and data are untracked in git, so `git diff` proves nothing | a sha256 manifest checked against eval v2's recorded hashes (p1) |

### 10.2 New facts from the agents' $0 counts
- **Saved data:** 2,990 conversations, 38,579 judged checks, 4,885 blocks (+ 415 cap overrides). Length bins of the
  judged checks: 31,168 / 5,779 / 1,632. Only 599 different tasks. Test group: 0 lines (critic d recount).
- **Stage A messages:** 1,859 of 1,861 tracker-guard block messages end with "violated, do not repeat". 229 name
  the gift card false only because it was never shown. 1,122 name a reminder as false (critic b recount).
- **The weak agent's real gap after reminder blocks:** its next reply held reminder words in only 126 of 800 cases,
  and in 156 cases the call then ran through the cap override. So the missing *content* matters, not only the word
  "violated" (critic b). This is why the v3 tell step gives the exact reminder content.
- **c1 offline:** train blocks 537 → 454 (−83), 0 added. Stage A nano tracker −574, all disclosure before login. 0 of
  the removed replies holds a database-only token (design c; critic c to confirm).
- **Judge skip:** with c1, the whole judge call can be skipped in about 73 % of train checks (design c), because no
  remaining judge fact can change the decision. This needs no prompt change.
- **Prices:** luna $0.01115 and nano $0.02193 per conversation (logged list prices). The real bill is about 0.6× /
  0.8× of that (cached input; critic e).
- **Power:** a paired 500-task weak run with the pooled frozen arm can rule out −0.040 with probability about 0.60
  when v3 equals frozen. A 2nd v3 try raises it to about 0.79 (critic e).

### 10.3 Ideas I kept out of the plan, and why
- **A shorter judge prompt** (ask only the needed facts): saves money, but changes the judge. Offline it would need
  an untestable assumption. Kept for later, as its own option, with a small paid check.
- **A new rule set** that splits the 12 mixed predicates: needs the user's approval of a new method. Mixed facts are
  split inside the value layer instead, and the rules stay frozen.
- **A bigger or "keep the start" judge view:** not a general fix (knowledge_retention §5.6). c1 reads the whole
  conversation instead.
- **Stage B message forks, c2 labels and the confirm variant at runtime:** moved to "later" in p15. They answer
  "which message helps", not "is v3 better".

### 10.4 Part c critic and completeness critic
**Part c critic** (`v3_crit_c_result.md`):
- the c1 core reproduces with independent code: Stage A nano tracker 1,876 → 1,302, with 0 real leaks in the 574
  removed replies, and every identity value equal to the task's own user (23 / 23 train, 91 / 91 Stage A);
- but **"0 added" held only for the whole-conversation rule.** The saved helper used the window since the last
  write, which adds 101 blocks. p10 now fixes the scope, and the replay must come from saved project code;
- the counts included cap overrides. The headline is now without them: nano tracker 1,745 → 1,238;
- the screens are not proven (11 of 19 and 5 of 8 constructed phrasings missed). A screen may allow only together
  with a code key, and is tested on ≥ 60 constructed positives written by a separate agent;
- "payment chosen" matched generic words. It is now only the id or last four digits in the latest payment message
  (Q11);
- two keys were only on paper for reminders and the yes. p11 now names the real second key;
- the judge skip is sound (0 changed decisions by brute force). The shorter "subset" prompt is dropped;
- c3: the guard's history must show the listing and the reply, never render a wrong call, and the later run needs a
  third arm.

**Completeness critic** (`v3_crit_all_result.md`), what it changed:
- p6 is new: the message view, helpers, info classes and `me` were needed by the message builder before part c built
  them. The old p10 and p11 (c2 and c3) are merged into one part. The total stays at 15 parts;
- one naming scheme (M, D, D+c1; flags; K1-K8 for questions, Q1-Q11 for user decisions);
- fact counts under the default reading (10 world, 12 agent-step, 1 event, 9 argument). The oracle always compares
  with `expr_db`. A13 stays a world fact;
- **val is a clean hold-out:** used only in Gate 0 and once in p13, after everything is frozen;
- **gold only flags,** through one module, never as a gate or a stop that decides;
- p12 gains three class rows (removed reply blocks, blocks added on executed unwanted writes, non-write checks), a
  definition of exact / near / unwanted, the judge's remaining share (goal c), the skip share, and a length bin per
  conversation;
- no escape that needs a person: Gate 0 misses have fixed classes and a hard cap of 0.5 %; every fix gets a line in
  a pre-registration change log; gate thresholds never change;
- the paid part: gold only flags; the joint pass chance is stated; the paired unit finishes on a stop; the main chat
  runs the interim check; all output goes to log files.

## 11. Decisions from the chat with the user (2026-10-22, after section 10)
These replace parts of sections 1-10. The plan (`overview.md`, `p1.md`-`p14.md`) follows this section.
1. **Main idea: no full LLM judge.** Every fact is set by code from the database and from what happened in the
   conversation. Where meaning is needed, one tiny yes/no question about one or two messages (code picks them).
   No judge at run time, not even as a fallback.
2. **Why eval v2 went wrong:** all 31 lookups read "what was shown" (22 answer false when nothing was shown), because
   TGR's rule writer phrased every fact for a judge that only reads the chat ("an earlier tool output shows ...").
   "Unknown" was never the missing piece: the framing was.
3. **Facts are states, two values:** a source (database, event, arguments, text structure, tiny question), a start
   value and an update rule. A "looked it up first" event part only where the policy says to check first.
4. **Messages are built from the rule, not hand-written per fact** (hand-written text would be fitted to τ-bench).
   The rules are small (82 of 98 have one fact; max 6), so a table per rule set lists which facts tip each
   decision. The simplest version (TGR's message without "violated, do not repeat") is the comparison.
5. **The confirm button** is no longer needed for the main goal; later option only.
6. **The gold scorer is dropped.** It is regex-based and tuned on about 50 hand-read calls. Our facts and rules are its
   better replacement; "rule broken" from them is reported, never a pass mark (v3 enforces the same rules).
7. **Expectations:** the saved data caps what better facts can add to task success (strong at most about +0.04, weak
   at most about +0.14, loose). Most failures are agent mistakes no rule covers. The gain is more correct, cheaper
   decisions.
8. **The decision audit is the heart:** for every wrong decision, was it the fact, the rule, or the agent? It runs
   first (p4), on the eval v2 data, for $0. How to tell a rule problem from a fact problem: p4 step 3 (blame by pattern, kept only if the fix improves
   outcomes).
9. **Paid runs: the strong agent only** (gpt-6-luna for every role). Companies that guard agents do not use cheap
   models, and it halves the cost. The saved weak-agent conversations stay in the $0 offline test, because they hold
   most of the violation attempts (the strong agent rarely violates the policy).
10. **Compare with no guard too.** The partner's results (`~/ShieldAgent/docs/RESULTS.md`) show that with the strong
    agent, no guard has the best task success; every guard mostly costs tasks. So the main paid run has three arms
    (v3, a fresh frozen TGR, no guard); Direct is optional [replaced by item 13 and overview Q13: five arms, with Direct]; ShieldAgent is not re-run (far below the others in the
    partner's results).
11. **The partner's repo** has 3 commits after our copy (`1bacdb0`): docs and one reproduction script only. p1
    re-checks this read-only.
12. **Cost and time (estimates):** core about $13-22 (cap $40) [replaced by item 16 and the overview]; about 2-3 working days. Live status:
    `predicate_correctness/output/eval_v3/progress.md`.
13. **An ablation arm, "Direct + facts":** Direct prompting (one LLM call per step with the whole policy), plus the
    facts v3's code tracked, given as checked facts. With Direct and v3 next to it, it shows whether reliable facts
    help an LLM guard, and whether rules beat an LLM once the facts are the same. Online only (it needs LLM calls).
14. **Fewer, harder online tasks:** the 500 Stage A tasks follow one easy template. The paid run uses 53 unseen tasks
    (val 33 in both domains, with 6 refusal tasks; τ-bench's retail dev 20) × 3 tries. With 53 tasks, only differences
    of about 0.07 or more show, so the pass mark is "not clearly worse" (lower end above −0.10), and the five arms
    are compared with ranges. Core cost about $10-17, cap $30 [replaced by items 16 and 17].
15. **Future work, added:** an intent check (does the call match what the user asked?), for the agent's own mistakes
    that no policy rule covers.
16. **Correction to item 14:** τ-bench has only 685 tasks. Retail train 500 and retail dev 20 follow one easy template
    (only 1-2 write actions expected). The hard ones are its 165 test-set tasks (115 retail, 50 airline), split by the
    partner into train 66 / val 33 / test 66 (never used). The paid run therefore uses all 99 hard tasks we may use
    (val 33 clean, train 66 seen), × 3 tries, with val and train also reported apart. Core cost about $17-26
    [replaced by item 17].
17. **Lenient money caps (user, 2026-10-23):** "give really lenient money caps to estimates so we won't interrupt it
    when we actually could have gone on." Every paid step has a hard limit of about 2× its high estimate (p12 $26,
    smoke $2, main run $45, option $20); the v3 total cap is their sum, $95. The cost and error stops catch only a
    broken run (3× an arm's high cost per conversation; 10 or more error lines and over 5 %). Measured costs and
    power: `predicate_correctness/output/logs/v3_rev_bench_result.md`. Items 10, 12 and 14 are replaced by items 13,
    16 and this one.
