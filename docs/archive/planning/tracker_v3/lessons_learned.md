# Tracker v3: lessons learned (for the next build on τ³-bench airline + retail)

Written 2026-10-23, after v3 was finished. It costs nothing to read and changes nothing in v3. Every number below comes
from the file named next to it. These lessons come from v3's own test runs (B2, B3). On new, unseen tasks they are
"policy reasons", written before any new data, which is what `next_steps_leak.md` asks for.

**The main idea in plain words.** v3 replaced a big LLM judge with code plus tiny yes/no LLM questions. The code part
was right everywhere: 0 errors, 0 database disagreements, 0 unsafe allows live. What cost us tasks was **a few
tiny questions that were too strict**. They asked for details in forms people never use, read too little text, said
"unclear" too often (and unclear blocks), and the block message did not say what was missing. So the agent looped.
On many-step tasks this added up to a clear loss. Build the questions as carefully as the code, and test them before
any real conversation.

**v3 in four numbers** (KR §1). Main test B2, 99 tasks: v3 − old guard −0.024 [−0.088, +0.040], pass. Unseen val 33:
−0.131, "possible leak". Many-step B3: −0.245 [−0.408, −0.061]. Cost per conversation $0.0089 vs $0.0116.

**File key** (all paths from `/home/azureuser/code_projects/`)
| short | file |
|---|---|
| KR | `knowledge_retention.md` |
| IL | `predicate_correctness/output/implementation_log.md` (times = its entries, 2026-10-23 UTC unless said) |
| OV, K2, PRE, RG, LEAK, AR | `docs/planning/tracker_v3/` `overview.md`, `k2_fix.md`, `preregistration_online.md`, `b2_reading_guide.md`, `next_steps_leak.md`, `approval_request.md` |
| P12R, DEV, K2F, OQR | `predicate_correctness/output/eval_v3/` `p12_report.md`, `p12_devcheck.md`, `p12_k2fix.md`, `p12_other_questions_review.md` |
| B2V, B3D, TQA, DFD, HM | `predicate_correctness/output/eval_v3/` `B2_val_diagnosis.md`, `B3_diagnosis.md`, `tiny_question_audit.md`, `direct_facts_diagnosis.md`, `harm_metric.md` |
| FR | `docs/reports/tracker_v3_full_report.md` |
| Q | `predicate_correctness/state_tracker/v3/questions.py` and `questions_v3.json` |
| CARD | `predicate_correctness/output/logs/v3_ll_card_check.txt` (a $0 recount made for this file) |

---

## 1. How to build a tiny (clarifying) question

**How v3's questions work** (Q). Code picks one or two messages and renders a fixed question (K1-K16) with them.
gpt-6-luna, low effort, answers JSON `{"answer": "yes|no|unclear", "quote": "..."}`. A yes needs a quote that is
really in the named message (after clean-up). "Unclear" or a failed quote takes the fact's blocking value. Each answer
is saved by sha256 of (question id, version, model, effort, clean input) and asked once. A changed question text
needs a new version (`text_sha256` check). Cost: about $0.000046 per call ($0.1253 for 2,726 calls, AR cost log).

**1.1 If code can compute it from the database, the tool code or the event log, never ask an LLM.**
- Evidence: 66 facts: 38 by code alone, 28 with code + a tiny question (IL Part 5). The code side was exact: 0
  mismatches on 23,138 replayed calls and 0 disagreements on 14,335 values (dev), 428 of 428 on the hold-out, 0 unsafe
  allows live (0 of 324 in B2, 0 of 127 in B3) (KR 4.2, 4.3, §1). Most tiny-question losses were things code could
  check: card digits, order ids, address fields, ownership (TQA §4, "code first, K2 second").
- Next time: for every line a question checks, ask "is this a string match or a database value?" If yes, code does
  it. The model only reads meaning: a yes, a reason in words, the kind of request.

**1.2 Before any paid call, check that every form a question accepts can really occur in the data.**
- Evidence: K2's card line wanted the database `last_four`. Users and agents name a card by the end of its payment id
  (`credit_card_3593714` → "ending in 3714"; the user simulator itself says it). 0 of 239 τ-bench retail cards have
  a payment id ending in the last four (IL 19:37). Recounted for this file: retail 0 of 239, **airline 0 of 503**
  (CARD). It cost 8 of the 11 K2 losses on B3 and 51 of 104 v3 write blocks there (B3D §2, §4).
- Next time: a $0 script per line: how do users and agents name this thing in the data (cards, ids, addresses,
  dates)? Accept every real form (last four, id digits, full id, "the card" when the user has one).

**1.3 Never ask the agent or user to repeat what the policy does not ask for, or what the database already knows.**
- Evidence: the policy never asks for a card's last four, a date of birth, a country or "how many bags are paid"
  (TQA §2). Each line lost tasks: airline/8/t0 (no dates of birth; the blocked booking was exactly the gold call;
  K2 no ×4), airline/4/t2 ("3 checked bags … allowance covers all 3" is not "3 in total, 0 paid"), retail/111/t2 (no
  "USA"; 8 blocks) (B2V §2, TQA §3).
- Next time: take the lines from the policy's own words ("the order id, the items, a payment method" for a return),
  not from every tool argument. Drop a line when the value is in the database and the user did not change it.

**1.4 One question asks one thing about one short text.**
- Evidence: K2 v1 asked for "every detail above" and made 121 of 211 tiny-vs-judge disagreements (K2). K2 v2 still
  asked about all lines at once: about 1 in 10 of its "no" answers had every line present (40 of 415, heuristic), and
  the model glued quote pieces together (TQA §2).
- Next time: code renders and checks the id-type lines; the model gets at most one meaning line per call, or answers
  per line with a `missing` field.

**1.5 Decide on purpose which text a question reads: which messages, how far back, and the user's words too.**
- Evidence: K2 read one agent message. An order id said one message earlier did not count: 3 of 11 B3 losses, 40
  order-id write blocks on B3 (33 + 7) (B3D §2, §3.3); 11 of the 24 "too strict" K2 cases read (TQA §2); retail/110/t1
  had the full address in the message before (B2V §2).
- Next time: write the window into the definition (for example: all agent messages since the last write, plus the
  user's own words for this action). Test a case where the detail sits one message earlier.

**1.6 One confirmation can cover a listed batch of actions. Put it in the question text, and test it.**
- Evidence: design decision Q7 said "one yes covers several listed actions" (OV Q7), but K1's text says "exactly
  this action". K1 said no to "please submit the returns for all four items" (two orders): retail/92, v3 0 of 3 vs
  frozen 2 of 3 (B2V §1-2). The hold-out review, done as B2 started, had already found 21 such wrong blocks
  (IL 15:56).
- Next time: every design decision becomes a made-up test case for the question (1.15) before any paid call.

**1.7 "Unclear → blocking value" turns every wording flaw into a block.**
- Evidence: live, 60 block causes were unclear answers or failed quotes (K2 32, K13 28) (TQA). On dev, blocks only from
  an answer problem were 41 before the fixes and 13 after (P12R §2). 28 of 29 live K2 quote failures had every line
  present (heuristic, TQA §2).
- Next time: on a write check, ask once more (same input, or a second wording) before blocking. Count unclear answers
  as a pass-mark item of the dev check.

**1.8 Quotes come in pieces. The quote check must allow it.**
- Evidence: K2 v2 had 31 quote failures on dev. Allowing pieces split at ";", "…" and line breaks made 24 of them
  correct yeses with no new call; 7 stayed (the model changed words) (K2F R2.2). The markdown and line-break fix alone
  changed 0 of 2,726 answers (K2F §5). Live, the model still joined pieces with "—" or "," (retail/103/t0, TQA §2).
- Next time: split at any punctuation and match each piece; for many-line questions let code check that each value
  is present and skip the quote.

**1.9 The block message must name the missing detail and its expected value, or the agent loops and transfers.**
- Evidence: every K2 block said only "consequential action details listed: false … Do this step first". The agent
  re-listed the same text 3-6 times (retail/277: 6 listings) (TQA §2, B3D §3.5). A call blocked once by K2 ran later in
  59 of 65 cases; blocked 3+ times, in only 4 of 29 (TQA §1). The old guard names the field and gets fixed in one step
  (B3 task 76, B3D §4). Agents follow block advice 97.6 % of the time (KR §1), so the advice must be exact.
- Next time: the answer carries a `missing` field and the message says "Not stated: the order id #W2806889". $0 check
  on saved blocks: does every message name a line the agent can fix in one turn?

**1.10 Plan the way out. A question that fires after another wrong block makes the error worse.**
- Evidence: 45 of K13's 90 live blocks came after a K1/K2 block in the same conversation, and blocked the agent's
  transfer: a dead end (TQA). On B3, 22 transfer calls were blocked in 13 conversations; in 10 of the 11 lost (a)
  conversations K13 blocked at least one transfer (B3D §3.1, §3.5).
- Next time: after 2 tiny-question blocks on the same write, allow the transfer (count it). Test chains of questions,
  not each question alone.

**1.11 Define every open word ("another person", "outside the tools", "reminded") with what counts and what does not.**
- Evidence: K5 "names another person" caught poets ("Shakespeare's Sonnet 18") and the user's own name: all 11 live K5
  blocks were wrong, 1 lost conversation; it was asked 1,678 times for those 11 yeses (TQA §1, §2). K13's hand-written
  list called "adding travel insurance after booking" a refused request, but the gold action for airline/36 was a
  transfer (B2V §2). K3 missed "is this the only item?" (TQA).
- Next time: "another person" = another customer or account holder, not a public person, not the user. Skip a question
  by code when its precondition is absent (no account data shown → no K5).

**1.12 Say whose data it is. Code knows ownership from the database; the question gets a stated default.**
- Evidence: K4 and K5 saw one message and could not know the owner: K5 gave 13 unclear-driven disagreements, K4 8 (all
  the user's own login) (OQR). With "the user's own unless the message says otherwise", both had 0 unclear answers
  (AR cost log 15:02).
- Next time: ownership by code; the question text carries the default.

**1.13 A message that asks for nothing new is "no".**
- Evidence: K13 v1 had 20 unclear answers on short follow-ups ("Yes.", a date). One sentence ("a message that asks
  for nothing new … is no") left 8 (OQR; KR 7.2 step 7).
- Next time: put this default into every question that reads user messages.

**1.14 Write down, for each question, the answer you expect from the agent and the user, and how sure you are.**
- Evidence: v3 never did this, and the surprises came live: the user simulator would not type "yes" ("I can't reply
  'yes'", retail/92, B2V §2); it names cards by id digits (B3D). K1 read "Yes." to the insurance line wrongly in 3 of 8
  dev cases; this was logged as a watch item (OQR), went live unfixed, and lost airline/0/t1 (TQA §3).
- Next time: one row per question: policy sentence | what the agent should say | what the user will likely say
  (counted in saved conversations) | how sure (the share) | what happens if not. Fix every watch item before the
  freeze.

**1.15 Test each question on made-up yes/no cases written from the policy, before any real conversation.**
- Evidence: fake answers (p8) and the judge stand-in (p11) only test code paths; they hid K2's strictness (KR 5.10).
  Blind sets did work for the word screens: 3 sets (818, 810 and 777 positives, about 400 hard negatives each) were
  written by agents that never saw the screens, and set 3 removed 4 screens (K5, K8, K9, K16) (IL Part 7). The
  questions themselves never got such a set, and Q7 (1.6) failed live.
- Next time: a separate agent writes 30 yes and 30 hard-no cases per question from the policy: each accepted form,
  each design decision, the window edge, the default case. Real answers on them cost cents (about 1,000 calls ×
  $0.000046 ≈ $0.05, estimate). Pass mark per question, fixed before the run.

**1.16 A dev check of blocks against a reference catches strictness, but it needs a pass mark.**
- Evidence: on 200 dev conversations tiny blocks went 207 → 155 → 122 against 31 for the judge stand-in (P12R §2).
  The check passed every time, because strictness was "for reading only … not a pass mark" (DEV). The rest went live:
  hold-out 153 blocks vs 64 for the saved guard, too strict on 26.1 % of write checks vs 3.1 % for the old guard
  (P12R §1); B2 0.848 vs 0.286 blocks per
  conversation; val −0.131 (KR §1). The dev review called K1's 22 disagreements "noise, no change" (OQR); on the
  hold-out K1 had 74, with the judge right in 60 (P12R §1).
- Next time: pre-register a strictness mark on dev (for example tiny blocks at most 1.5× the reference; choose the
  number before data). Read disagreements by pattern ("one yes for two orders"), never as "noise".

**1.17 Many-step tasks multiply each question's error rate.**
- Evidence: a write was blocked at least once at the same rate on B2 retail and B3 (0.32), but B3 has 2.98 writes per
  conversation vs 1.39, so 13 % of writes never ran vs 6 % (B3D §3.2). Blocks per write: v3 0.71, old guard 0.14
  (B3D §3.1). K2 was asked 9.4 times per B3 conversation vs about 3 on B2 (TQA). B3 success: v3 0.469, old guard 0.714
  (KR §1).
- Next time: a task with n writes passes all checks with chance (1 − p)^n, so include 3+ write tasks in the dev check
  and in the main test (3.8).

**1.18 Version every question and cache answers by hash; then fixes are cheap.**
- Evidence: re-asking only the changed keys cost $0.0687 (1,157 calls) and $0.0053 (76 calls) (AR). A saved answer's
  status is derived again from its raw text, so the quote fix turned 24 failures into yeses for $0 (K2F §1, R2.2).
- Next time: keep this design (Q).

---

## 2. Facts, rules and code

**2.1 World facts come from the database through the tool's own code, never from "was it shown".**
- Evidence: eval v2 copied the wording "an earlier tool output shows …"; 22 of 31 lookups were false when nothing was
  shown, and the weak agent lost 0.040 (OV "Why"; KR 5.3-5.4). v3's replay: 0 mismatches, 0 disagreements (1.1).
- Next time: replay the conversation's tool calls on a database copy; check each fact against the real tool on a
  scratch copy ($0).

**2.2 Event facts are false until a tool call that worked. Add "looked it up first" only where the policy says so.**
- Evidence: event parts vs a raw scan of the messages: 69,756 checks, 0 disagreements (IL Part 6). Retail "check its
  status before", airline "the agent must make sure" (KR 7.2 step 3). No "and looked up" on a fact where false allows,
  or "not looked up" becomes an allow (IL Part 5, airline A).
- Next time: the same; read the database part at the check, so a later change is seen.

**2.3 A new allow needs two keys: the question's yes and the code part.**
- Evidence: 0 two-key disagreements on 2,016 dev facts and on the hold-out; 0 bad of 10 new allows (DEV, P12R).
- Next time: keep it; run code parts first.

**2.4 An unclear part must not hide the other branch of an OR.**
- Evidence: one unclear K13 answer stopped the other path (a used flight + K16) in 2 dev cases (OQR); fixed in the
  evaluator (K2F §1).
- Next time: evaluate each branch; block only if the value rests on the unclear part. Test it with a made-up case.

**2.5 Build block messages from a rule table, and pass the question's failing line into them.**
- Evidence: 82 of 98 rules have one fact; rule-built messages are 37 % shorter and pass all 8 message checks on 3,978
  blocks (KR 4.2). But the table knows only "fact false", not which K2 line failed (1.9).
- Next time: advice by who can make the fact true (agent, ask the user, only the user, nobody), plus the missing line.

**2.6 Show code facts to an LLM as final values with their sign, never as a part's plain text.**
- Evidence: the Direct + facts block printed "- message structure (false): The user U is a regular member …"; the LLM
  read it as true: 15 wrong decisions in B2 (13 blocks, 2 cap overrides), 4 of the 8 cap overrides, 1 lost
  conversation. The values were right (0 failures in 4,675 checks). Its small loss to Direct is chance (36 vs 33
  matched wins, p = 0.81) (DFD).
- Next time: "user is a regular member: NO (membership gold)"; leave out facts that no rule of the pending action uses.

**2.7 Word lists ("screens") may only decide whether to ask, and they need blind tests.**
- Evidence: 4 screens failed blind set 3 and were removed (IL Part 7). Then K5 was asked at almost every retail reply:
  the upper bound went from 715 to 6,008 calls (IL Part 8). Lazy evaluation (only facts a rule still needs) saved 5-9 %
  of questions with the same decisions (IL Part 9).
- Next time: prefer a code precondition (1.11) to a word list; keep lazy evaluation.

**2.8 First rebuild the old guard's saved decisions exactly (Gate 0), so every comparison is fair.**
- Evidence: 38,579 of 38,579 judged checks and 4,885 block messages rebuilt, 0 misses (KR 4.2); the none / Direct /
  old-guard arms were byte-equal to the copied code in dry runs (IL p13 runner).
- Next time: the same on τ³-bench before any new fact.

**2.9 Check the rules you inherit; their gaps become your gaps.**
- Evidence: v3 kept TGR's 98 rules. No rule blocks a booking with an unknown flight, a cabin-only change or a bag
  update paid by certificate (the tool refuses them anyway) (IL Part 5, airline A); the tool's check "the items are in
  the order" has no v3 fact (KR 7.3).
- Next time: each rule cites its policy sentence; diff τ³'s policy text against τ-bench's before reusing rules.

---

## 3. Experiment design

**3.1 Pre-register claims, pass marks, stops and the reading before any paid call; log every change with "result seen?".**
- Evidence: the online pre-registration was frozen at 12:30 (sha `9b385a58…`), before the first paid call; its change
  log has 6 rows, each saying whether a result was seen (PRE). The reading guide was frozen at 16:03 with only 148 of
  1,485 lines counted (RG); gaps were found before the result (no label for "pass with a point below −0.05") (IL 16:50).
- Next time: write the reading guide with the pre-registration, and cover every cell (pass / fail × point sign).

**3.2 Freeze, then open the hold-out once. Development numbers are bug checks, not results.**
- Evidence: v3 was frozen at 15:33 (19 files) and never changed; the hold-out passed its zero-count marks (0 errors,
  428 of 428, 0 of 10 bad allows). The independent recount matched every main count but one class split (suspect 17 vs
  6), because "confirmation facts" was never defined (P12R §1).
- Next time: define every word a count uses; add the strictness mark (1.16) to the hold-out too.

**3.3 Plan the harm metric before the run, and show it next to task success in every table.**
- Evidence: harm was added after the results (asked 19:29, counted 20:02, put in every table 20:13-20:16, IL). Success alone rewards
  no guard: it had the best success in B2 (0.667) and B3 (0.755) (KR §1). Outcome harm in B2: every arm 16.8-19.2 %; in
  B3 v3 8.2 % vs old guard 20.4 % (HM). The existing "unwanted writes" count treated every write as unwanted when a
  conversation ended early; taking the expected writes per task changed B3 v3 from 16.3 % to 8.2 % (HM, last table).
- Next time: pre-register harm (outcome view, expected writes per task, 95 % range) as a claim, shown next to success.

**3.4 With a strong agent, no guard wins on task success. Claim "not worse, cheaper, less harm", not "better".**
- Evidence: partner's train retail: no guard 0.761, TGR 0.710 (FR §7). Removing every wrong block could add at most
  about +0.04 for the strong agent (OV). In the partner's runs, the strong agent with no guard breaks a rule in
  about 1 of 138 retail conversations (FR §8).
- Next time: main claim = not clearly worse on success; also report new guard − no guard (B2 v3 −0.034, KR §1).

**3.5 A real harm test needs a weak agent or simulated users who push for forbidden actions.**
- Evidence: partner's weak-agent runs: accepted rule breaks fell from 38 (airline) / 16 (retail) with no guard to 7 / 2
  with Direct and 4 / 2 with TGR (FR §7). In our B2, refusal tasks had only 2-4 conversations with an accepted write
  per arm, out of 54 (HM).
- Next time: add a pre-registered harm cohort (weak agent, or user instructions written from the policy's forbidden
  actions).

**3.6 Size the test first. Val 33 alone is close to a coin flip.**
- Evidence: if v3 equals the old guard, the test passes 0.89-0.98 of the time on all 99 tasks but only 0.41-0.60 on
  val 33 (0.53-0.80 with 6 tries) (IL 15:37). One val task flipping 3 of 3 moves the mean by 0.09 (B2V §4). B3's 49
  tasks gave a range of about ±0.17 (FR §5.6).
- Next time: compute power from saved runs before choosing the split; put the main claim on the largest clean set.

**3.7 Leak rules: a fix found by reading test conversations makes those tasks seen.**
- Evidence: v3's results stay final; a "fixed" v3 on the same tasks would be a leak; τ²-bench retail / airline are
  mostly the same tasks as τ-bench (LEAK).
- Next time: ($0, first step) measure how many τ³-bench airline / retail tasks repeat τ-bench tasks (v3's lessons came
  from those). Call repeated tasks "seen". Freeze the new build and its pass marks before the test; report it next to
  v3, never in its place.

**3.8 Put many-write tasks and refusal tasks into the main test, not into an optional extra.**
- Evidence: B3 (3+ writes) was optional (OV Q15, default "no") and on seen tasks, yet it showed the biggest problem
  (−0.245) (FR §4.7). The 30-step limit scores 0: v3 did all 5 gold writes of task 248 and still got 0, partly because
  blocks use steps (B3D §2).
- Next time: split the main test by number of writes, with a reading per group fixed in advance.

**3.9 Keep the five-arm comparison.**
- Evidence: S1 (Direct + facts − Direct) −0.010 and S2 (v3 − Direct + facts) +0.024 on B2, both no clear difference;
  on B3 S2 −0.224, "rules worse" (KR §1). It told us the facts are fine and the questions are the problem.
- Next time: no guard, Direct, Direct + facts, old guard, new guard, on the same (task, try), side by side.

**3.10 Plan the diagnosis too.**
- Evidence: the same 4 loss classes (wrong block, agent mistake, noise, other) explained B2 val (8 of 22 from wrong
  blocks) and B3 (11 of 17) within about 15 minutes of each result (B2V, B3D; IL 17:08, 19:37). Answers had no
  conversation id, so they were matched by text (TQA §5).
- Next time: write the classes and the script before the run; save the conversation id with every tiny answer.

---

## 4. Running paid steps

**4.1 Every paid step needs its own new, explicit approval, with a written request.**
- Evidence: 7 approvals, each with commands, cost, limit and time, and the user's words copied into `--approved`
  (AR, KR §1). Asking for B1 as "approve B1 after freeze" saved about 1-1.5 h (IL 13:16).
- Next time: ask for the expected approvals early, as conditional ones ("B2 after B1 passes"), each with its limit.

**4.2 Paid runs start from the main chat.**
- Evidence: a subagent's change to B2's stops was blocked by the permission system; it was not worked around (IL 15:56;
  KR 5.11).
- Next time: subagents prepare and dry-run; the main chat launches (`setsid nohup`, one process group per shard).

**4.3 Lenient stops, fixed in advance, worked.**
- Evidence: B2 halfway: v3 − old guard +0.010, go on (IL 16:29). B3 halfway: −0.243 ≤ −0.15 on 37 complete groups, so
  the main chat wrote the STOP file at 19:21:03; open groups finished, 0 dropped, $5.25 of $20 (IL 19:25). Stops:
  harm at halfway, 3rd state error, cost 3× the high estimate, error lines, money limits, a manual STOP file (PRE §9).
- Next time: keep them; run the halfway check by script (B3 had one at 170 lines, IL 19:08).

**4.4 Dry runs, a smoke test and independent audits before money.**
- Evidence: sandbox dry runs of every shard made 0 calls (B2 375 / 375 / 375 / 360 units; B3 320) (IL 15:56, 19:08).
  Three read-only audits found 1 blocker (a backup moved instead of copied hides spend) and a major (a failed tiny-
  question API call became a silent v3 block) (IL 12:47). B1, 10 conversations, $0.149, passed (AR).
- Next time: same order: dry run → audits → smoke → main run.

**4.5 Have the finish script and an independent recompute ready before the run.**
- Evidence: B2 ended 16:54:53; metrics, report and recompute ran by themselves at 16:55:09 (IL 16:55). The recompute,
  written from the pre-registration text and raw lines only, gave the same point estimates for B2 (−0.0236) and B3
  (IL 16:55, 19:25). A dry run on a partial copy matched 42 of 42 estimates without reading outcomes (IL 16:35).
- Next time: the same.

**4.6 Run in parallel: shards × workers, and parallel question calls.**
- Evidence: B2's 1,485 conversations took 59 min with 4 shards × 8 workers; B3's 245 took 17 min (AR). Asking the
  tiny questions one at a time would have taken 6-12 h for 22,070 calls; with 8 workers p12a's 2,726 calls took 12 min
  (AR step 0, cost log).
- Next time: one process per shard (lock file); before a resume, copy (never move) each run file (KR §8).

**4.7 Costs, per conversation (logged list price; the real bill is about 0.55× of it).**
| arm | B2 | B3 (3+ writes) |
|---|---|---|
| no guard | $0.0066 | $0.0134 |
| Direct | $0.0131 | $0.0254 |
| Direct + facts | $0.0128 | $0.0254 |
| old guard (frozen TGR) | $0.0116 | $0.0244 |
| v3 (guard part) | $0.0089 ($0.0007) | $0.0185 ($0.0016) |
- Evidence: FR §2, §10.2. All of v3 cost $21.49 (cap $95; eval v2 $40.38) (KR §1). The B2 estimate was close
  (point $16.4, actual $15.76). v3 made more LLM calls than the old guard (32.0 vs 28.9 per conversation; B3 64.4 vs
  52.5), but they were tiny (FR §2, §10.2).
- Next time: claim dollars and the share of checks that use an LLM, not "fewer calls"; set limits at about 2× the high
  estimate.

**4.8 Known traps** (KR §8).
- `pgrep -f` matches your own shell; act by explicit process id. A τ-bench env with `user_strategy="llm"` makes a paid
  call even in a dry run. Take tool arguments from the message, not `attempts[i].kwargs`. Any file named
  `episodes*.jsonl` counts as spend. Never put `from_shieldagent/` on `sys.path`.

---

## 5. Working fast

**5.1 Where the time went.** v3 took about 20.5 h wall time (approved 2026-10-22 23:44, last edit 2026-10-23 20:16),
with two API-limit pauses of about 3.5 h (02:05-05:38) and 1.5 h (09:00-10:30) (IL). The plan said 2-3 working days
(OV).

**5.2 The K2 rounds were the slow part, and avoidable at $0.**
- Evidence: the dev check found K2 at 13:47; fixes, three paid re-asks and two dev checks ran until the freeze at 15:33,
  about 1 h 45 min on a path that cannot be split (fix → re-ask → check → freeze → hold-out) (IL 14:29). The question
  code was ready at 07:16 (p8), but real answers came only after the full offline test (p11, 11:22) and the approval
  (11:50).
- Next time: the $0 form check (1.2) and made-up cases (1.15) first; then a small real-answer pilot as soon as the
  question code exists.

**5.3 Waiting on the user.** The B3 request was final at 17:25 and approved at 19:06 (FR §4.7). Ask for all likely
approvals in one message, with conditions (4.1).

**5.4 Slow loops.** The full test suite took 9.5 min in one process; a parallel runner (each module in its own
process, 8 at a time) fixed it (IL 15:29). Questions in parallel: 4.6.

**5.5 Doc churn.** `knowledge_retention.md` was rewritten (15:16-15:27) and then fact-checked (15:41: "31 correct
yeses" was really 24 of 31); docs were cleaned again at 16:37; the full report was rewritten at 19:19 and got harm
columns at 20:13-20:16. An integrity check found the freeze size logged as 21 files instead of 19, and 4 missing sha
rows (IL). Next time: one live status file plus one log; numbers only in generated files; write the reports once, at
the end, from those files, with one checker.

**5.6 Many agents in parallel.** 13 agents at once worked; the Workflow tool ran only 2 at a time here (KR §8). Each
agent owned its own files (overlays merged by the main chat, 0 conflicts, IL 06:21). Brief auditors with the code
and the rules, not with your conclusions (IL 12:33).

**5.7 Plan in one shot.** All 15 design questions were answered at once with defaults (OV Q1-Q15, 23:44), so p1-p11 ran
without a stop. The later changes each cost doc and code edits: main claim on all 99 (12:12), secondary claims
(12:14), B3 whatever B2 shows (16:52), harm next to success (19:29, 20:13) (IL). Put these choices into the first
plan (section 6).

---

## 6. Checklist for the next build (τ³-bench airline + retail)

1. ($0) Count τ³ tasks that repeat τ-bench tasks; mark them "seen". Compute power from any saved runs; pick the split.
2. Get rules that cite policy sentences; diff τ³'s policy text against τ-bench's; list the rule gaps.
3. Sort every fact part: database / event / call argument / text structure / meaning. Code for all but meaning.
   Replay tool calls; 0 mismatches against the real tool on a scratch copy. Rebuild the old guard exactly.
4. Per question, write: one meaning; the text window; the default for the empty case ("the user's own", "asks
   nothing new" = no); every open word defined; the expected agent and user answer, counted in data, with how sure.
5. ($0) Form check: for each accepted form, count how users and agents name it in the database and saved
   conversations (card ids vs last four: 0 of 239 retail, 0 of 503 airline in τ-bench). Accept every real form; drop
   lines the policy does not ask for or the database knows.
6. Made-up cases per question (30 yes / 30 hard no, from the policy, by a separate agent, including every design
   decision such as "one yes covers a batch"); real answers for cents; a pass mark per question.
7. The block message names the missing line and its value; after 2 tiny blocks on one write, allow the transfer;
   ask once more before an "unclear" blocks a write.
8. Facts shown to an LLM: final value with its sign, only facts the pending action's rules use.
9. Pre-register: main claim (not clearly worse), harm (outcome view) next to success in every table, a strictness mark
   on dev and hold-out, stops, a reading guide for every cell, the diagnosis classes.
10. The test set holds many-write tasks and refusal tasks; add a harm cohort (weak agent or pushy users).
11. Dev check with real answers early, read by pattern; fix definitions, never single examples; re-ask changed keys.
12. Freeze (sha manifest) → hold-out once → smoke → main run, each paid step with its own approval (ask early, with
    conditions).
13. Before money: shard dry runs with 0 calls, 3 read-only audits, the finish script and the independent recompute.
14. Run from the main chat: 4 shards × 8 workers, STOP file, copy-not-move backups, a progress line every 10 min.
15. Many parallel agents with owned files; one status file; reports written once at the end from generated numbers.
