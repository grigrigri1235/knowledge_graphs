# Cheaper, steadier predicate values for TGR: v4

Slide flow for the project supervisors. About 12 minutes, 13 slides.
The audience knows the TGR pipeline in ~/ShieldAgent (rules, predicates, the guard on each tool call). They do not
know what we changed in how predicate values are set.

Each slide has two parts. "On the slide" is what the audience sees. "Say, in order" is the talk track: one short
point per bullet, in speaking order. The last bullet of each slide leads into the next one.
Figures are in `docs/reports/figures/`. The full write-up is `docs/reports/tracker_v4_report.md`.

---

## Slide 1. Title (0:20)

On the slide:
- Cheaper, steadier predicate values for TGR
- Same rules, same predicates. A new way to set their values.
- τ-bench airline and retail, October 2026

Say, in order:
- We kept TGR's rules and predicates exactly as they are.
- We changed one thing: how each predicate gets its true/false value.
- The result: cheaper, at least as good at finishing tasks, and no more harm.
- Let me first remind you how TGR sets those values today.

---

## Slide 2. Where we start: TGR on τ-bench (0:50)

On the slide:
- The agent wants to make a tool call that changes data (cancel, book, return).
- TGR is the partner's guard for τ-bench, in ~/ShieldAgent. It finds the rules for that action: 98 rules over 66
  predicates.
- One judge LLM reads the conversation and sets every predicate of those rules.
- The rules then decide: allow or block.
- Our change is only in the third line.

Say, in order:
- Picture the agent in the middle of a conversation. It wants to cancel an order.
- Step 1: TGR looks up the rules for "cancel". For example: the user must confirm first.
- Step 2: each rule rests on predicates, simple true/false facts such as "the user confirmed".
- Step 3: to fill them in, TGR sends the conversation to one judge LLM. The judge sets all of them at once.
- Step 4: the rules decide. Allow, or block with a message back to the agent.
- We kept steps 1, 2 and 4. We only replaced step 3, the judge.
- Here is why step 3 is the weak spot.

---

## Slide 3. The problem with one big judge call (1:00)

On the slide:
- Cost: every guarded tool call sends the last 24,000 characters of the conversation to the judge.
- That is about 10 judge calls per conversation on the main test, and about 21 on long tasks.
- Not deterministic: the model has no temperature or seed setting, so the same check is a new random draw each time.
- Errors: in an earlier offline study, code and the judge disagreed on 262 of 6,690 values. A review found the code
  right in 213 of 216 of those.
- Most rules hang on one predicate (82 of 98). One wrong value flips the decision.

Say, in order:
- The judge step has three problems.
- It is expensive. Every time the agent wants to write, up to 24,000 characters go to the judge. About 10 times per
  conversation, and 21 on long tasks.
- It is not steady. We cannot fix a temperature or a seed, so asking twice can give two answers.
- It makes mistakes. Where code and the judge disagreed, the code was right 213 times out of 216.
- And one wrong value is enough. 82 of the 98 rules rest on a single predicate.
- Yet many predicates do not need an LLM at all. "Is the order pending?" is written in the database.
- That observation is our whole idea.

---

## Slide 4. Our idea: code first, tiny questions for the rest (1:00)

On the slide:
- If code can know a value, code sets it. From the call's arguments, the database, or the log of tool calls.
- 40 of 66 predicates are now pure code. Same input, same answer, no LLM call.
- The other 26 need reading for meaning, like "did the user say go ahead?".
- For those, the guard asks an LLM one tiny yes/no question. Automatic, inside the check. The user and the agent
  never see it.
- Code picks what the LLM reads: only the one or two messages that matter, e.g. the agent's proposal and the user's
  reply after it.
- 12 tiny questions in total, asked to the same model at low effort. No judge.
- On the main test, 3 of 4 guard checks made no LLM call at all.

Say, in order:
- Our rule is simple. If code can know a value, code sets it.
- Code reads three things: the call's arguments, the database, and the tool calls made so far.
- That covers 40 of the 66 predicates. Same input, same answer, and free.
- The other 26 need reading for meaning. For example: did the user really say go ahead?
- For those, the guard itself asks an LLM. This happens automatically, inside the check, before the tool call runs.
  We never ask the user or the agent anything. They do not see it.
- First, code picks what the LLM may read. Each question has a fixed rule for this. For "go ahead", it is the
  agent's message that proposed the action, plus the user's replies after it.
- Then the LLM gets one narrow question about just those messages: "Did the user say yes to this exact action?"
- It answers yes, no or unclear. That answer becomes the predicate's value. Slide 6 shows one check end to end.
- Often code settles the rule before any question is needed. On the main test, 3 of 4 checks made no LLM call.
- The obvious next question: how do we know these values are right?

---

## Slide 5. How do we know the values are right? (1:20)

On the slide:
- 66 predicates give 2^66 true/false combinations. Nobody can test all of them.
- But a tool call only touches its own rules: at most 14 predicates, usually 10 or fewer.
- And rules are tiny: the largest has 6 predicates, so at most 64 combinations.
- We listed every combination of every rule, and ran TGR's own decision code on each. 100 % matched.
- So we can test each value source on its own, not the combinations:

| layer | what we checked | how big |
|---|---|---|
| code predicates | replayed against the real tool outputs | 2,891 of 2,891 exact |
| each tiny question | 30 made-up "yes" and 30 hard "no" cases, mark 28 of 30 | 720 cases |
| whole checks | 200 real saved conversations, compared with the old judge | 2,164 tool-call checks |
| end to end | live runs, task success and harm | 1,375 conversations |

Say, in order:
- The worry: 66 predicates means 2^66 combinations. We cannot test that.
- We do not need to. One tool call only looks at its own rules, so at most 14 predicates.
- Each rule is even smaller: at most 6 predicates, so at most 64 combinations.
- So we wrote out every combination of every rule, and ran TGR's own decision code on each. All matched.
- Now we know exactly which predicate flips which decision. That lets us test each value on its own.
- We tested in layers, from cheap to expensive. Code against real tool outputs. Each question on 60 made-up cases.
  Whole checks on 200 saved conversations. Then live runs.
- Only the live runs count as results. The other layers catch bugs early, for cents.
- Next: how the tiny questions are written. This is where v3 and v4 differ.

---

## Slide 6. Writing the tiny questions: what v3 set up (0:50)

On the slide (v3, our first version):
- One question, one meaning. Words are defined, and the default is stated.
- Code picks the messages. The question never sees the whole conversation.
- A "yes" must quote the message it relies on. A bad quote counts as unclear.
- Two keys: a new allow needs both the code part and the question's yes.
- An unclear answer blocks.
- Every answer is cached, so the same input never costs twice.
- Example panel: one check, from proposal to allow.

Say, in order (walk through the example on the left):
- Here is one check, from start to end. The agent wants to cancel order W2378156.
- First, code checks its own part of the rule. The order exists and is still pending. That is key one.
- One predicate needs meaning: did the user say go ahead?
- Code picks just two messages: the agent's proposal and the user's reply. Nothing else is sent.
- The question is narrow, and its default is stated: "no, unless the user clearly said yes to this exact action".
- The model answers yes, and quotes "Yes, please do."
- Code checks that the quote really is in the user's message. It is. That is key two.
- Both keys are there, so the write is allowed.
- If the answer had been unclear, or the quote wrong, the write would have been blocked.
- The answer is cached. The same two messages never cost a second call.
- This worked well on short tasks. On long tasks it blocked far too often. That is what v4 fixed.

---

## Slide 7. What we learned from v3, and what v4 changed (1:00)

On the slide (one row per lesson: lesson | what v4 does). Subtitle: "the 6 main lessons, of 31 we recorded":
- If code can check it, do not ask an LLM. | The check "did the agent state the details?" became code. 16 questions became 12.
- Check how the data really says it. Never ask for more than the policy. | Each question passed made-up test cases before any real use.
- Unclear is not the same as no. | Ask once more in other words. Then decide by what a wrong block would cost.
- A block must say how to fix it. | Block messages name what is missing, and the one step that fixes it.
- Always leave a way out. | After 2 question blocks on the same write, the agent may hand the user to a human.
- Measure strictness before going live. | A limit of 1.5 times the old judge's blocks. v4 came in at 1.16 times.

Say, in order:
- v3's problem was simple: it blocked too often. On long tasks, agents got stuck and failed.
- We recorded 31 lessons from v3. Here are the six main ones. v4 is those lessons put into practice.
- One: if code can check it, do not ask an LLM.
- Example: "did the agent state the details before acting?" The tool call already holds every detail.
- So code takes each detail from the call, and looks for it in what the agent told the user.
- It accepts every form people really use, like a card's id or its last four digits. No LLM needed.
- Two: check how the data really says it, and never ask for more than the policy.
- v3's worst question demanded one form of the card number. Nobody in the conversations used that form, and the
  policy never asked for it.
- So it said no almost every time, and caused most of v3's long-task losses.
- Now every question is tested on made-up cases first, so a question like that is caught early.
- Three: unclear is not the same as no. v4 asks once more in other words. If it is still unclear, it looks at what a
  wrong block would cost. A write is blocked. A transfer to a human is let through, because blocking it leaves the
  user with no help at all.
- Four: a block must say how to fix it. Otherwise the agent just tries the same thing again.
- Five: always leave a way out. After two blocks on the same write, the agent can hand over to a human.
- Why it helps: in v3, one wrong block could trap the agent in a loop until the step limit. The user got no help.
- Now a wrong question costs at most two tries. A transfer changes no data, so it is safe.
- On the main and long-task tests, v4 lost no task to a block loop that ran into the step limit.
- Six: measure strictness before going live. On 200 saved conversations, v4 blocked 1.16 times as often as the old
  judge. v3 had been near 4 times.
- That is the method. Next, how we tested it.

---

## Slide 8. How we tested (0:40)

On the slide:
- B2': main test. 99 hard tasks, 3 tries each. Can v4 match TGR without the big judge?
- B3': long-task test. 64 retail tasks with 3 or more writes. This is where v3 failed.
- H: harm test. The same 99 tasks with a weak agent (gpt-5-nano) that tries more forbidden writes.
- Arms: no guard, frozen TGR, v3, v4. Pass marks were written down before any run.

Say, in order:
- Three tests. Each answers one question.
- B2', the main test: does v4 finish as many tasks as TGR?
- B3', long tasks with 3 or more writes. More writes mean more chances to block wrongly. This is where v3 failed.
- H, the harm test. A strong agent rarely tries forbidden writes, so all guards look the same. So we use a weak agent
  that tries more of them.
- The same tasks ran with four setups: no guard, TGR, v3 and v4.
- Every pass mark was written down before the runs.
- We look at three numbers: cost, task success, and harmful writes. First, cost.

---

## Slide 9. Result 1: cost (0:50)

On the slide: figure `docs/reports/figures/v4_cost.png`
- Four bars in every group, in this order: no guard, TGR, v3, v4. US cents per conversation, list price.

| group | no guard | TGR | v3 | v4 |
|---|---|---|---|---|
| B2' · main | 0.66 | 1.16 | 0.89 | 0.78 |
| B3' · long tasks | 1.35 | 2.57 | 1.81 | 1.49 |
| H · weak agent | 1.15 | 3.08 | 1.94 | 1.39 |

- v4 is the cheapest guard in every test.
- It costs 0.67 times TGR on B2', 0.58 times on B3', and 0.45 times on H.
- It is also cheaper than v3.

Say, in order:
- v4 is the cheapest guard in all three tests.
- It costs about two thirds of TGR on the main test, and less than half with the weak agent.
- The longer the conversation, the bigger the saving. TGR pays for a big call at every write. v4 mostly pays nothing.
- v4 is even cheaper than v3.
- Cheap only matters if it still works. So, task success.

---

## Slide 10. Result 2: task success (0:50)

On the slide: figure `docs/reports/figures/v4_success.png`
- Title: "Task success: as good or better". Subtitle: share of conversations where the task was done right.
- Four bars in every group, in this order: no guard, TGR, v3, v4.

| group | no guard | TGR | v3 | v4 | tag under the group |
|---|---|---|---|---|---|
| B2' · main | 0.667 | 0.657 | 0.633 | 0.673 | not worse |
| B3' · long tasks | 0.719 | 0.719 | 0.469 | 0.750 | not worse · v3's crash gone |
| H · weak agent | 0.561 | 0.480 | 0.480 | 0.622 | clearly better |

- Name the third group "H · weak agent", not "H · harm". This slide is task success; harm is the next slide.

Say, in order:
- Each group has four bars: no guard, TGR, v3 and v4.
- No guard is the ceiling a guard should not fall far below. A guard that blocks wrongly loses tasks.
- Main test: v4 0.67, the same as no guard. TGR 0.66, v3 0.63.
- Long tasks: v4 0.75. TGR and no guard 0.72. v3 crashed to 0.47.
- On both, the gain over TGR is small. So we claim "not worse", the pass mark. Both pass.
- Weak agent: TGR and v3 both fall to 0.48, below no guard's 0.56. They block too much.
- v4 stays at 0.62. Clearly better than TGR, and no task cost compared with no guard.
- Last number: does v4 still stop harmful writes?

---

## Slide 11. Result 3: harmful writes that got through (0:50)

On the slide: figure `docs/reports/figures/v4_harm.png`
- Main chart: the H test only (weak agent), four bars in this order: no guard, TGR, v3, v4.
  % of conversations where a harmful write got through. Lower is better.

| H · weak agent | no guard | TGR | v3 | v4 |
|---|---|---|---|---|
| harm got through | 31.6 % | 24.5 % | 20.4 % | 18.4 % |
| task success (for the note under v3) | 0.561 | 0.480 | 0.480 | 0.622 |

- Tag next to v4: "clearly below no guard · not worse than TGR".
- Small note under the v3 bar: "low harm, but it also blocked right writes: success 0.48".
- Safety box, writes allowed that τ-bench's own tool then refused: v4 0, v3 0, TGR 11.
- Honest note box: even TGR was not clearly below no guard, so H is a weak harm test.
- Optional footnote, strong agent (no clear differences): B2' no guard 17.8, TGR 16.8, v3 17.5, v4 19.2;
  B3' no guard 25.4, TGR 25.4, v3 15.9, v4 23.8.

Say, in order:
- A harmful write is a write the task did not expect.
- Look at H, the weak agent. No guard lets 31.6 % through. TGR 24.5 %. v3 20.4 %. v4 18.4 %.
- So v4 clearly cuts harm compared with no guard, and is not worse than TGR.
- v3 also looks low. But it got there by blocking right writes too: its task success fell to 0.48.
- v4 has the lowest harm of the four, and the highest task success. It cuts harm without losing tasks.
- Safety check: v4 and v3 never allowed a write that τ-bench itself then refused. TGR did, 11 times.
- One honest caveat: TGR itself was not clearly below no guard here. So H is a weak harm test.
- With the strong agent, on B2' and B3', harm differences are small either way.
- A fair question at this point: v3 was already cheap. Why build v4?

---

## Slide 12. For skeptics: why not just keep v3? (0:40)

On the slide:
- v3 was already cheaper than TGR.
- On the main test its task success was only a little lower: 0.633 against 0.657.
- But on long tasks it crashed: 0.469 against 0.719. It blocked too often, and agents got stuck.
- That crash is why we built v4.
- v4 is cheaper than v3 too, and finishes more tasks than v3 in every test.

Chart data (one row per test; show cost next to success, since two cards are about cost):

| test | task success: TGR / v3 / v4 | cost, cents per conversation: TGR / v3 / v4 |
|---|---|---|
| main test, B2' | 0.657 / 0.633 / 0.673 | 1.16 / 0.89 / 0.78 |
| long tasks, B3' | 0.719 / 0.469 / 0.750 | 2.57 / 1.81 / 1.49 |
| weak agent, H | 0.480 / 0.480 / 0.622 | 3.08 / 1.94 / 1.39 |

If asked: v4's lead over v3 is clear on long tasks (+0.28) and on H (+0.14). On the main test (+0.04) it is not clear.

Say, in order:
- v3 was already cheaper than TGR. The cost idea worked from the start.
- On the main test, v3 was only a little behind TGR: 0.63 against 0.66.
- But on long tasks it crashed: 0.47 against 0.72. It blocked so often that agents got stuck.
- That crash is the reason v4 exists.
- With the weak agent, v3 only tied TGR: 0.48 each.
- v4 fixes it without giving the saving back. It is cheaper than v3 in every test, for example 0.78 against 0.89
  cents on the main test.
- And it finishes more tasks than v3 in every test: clearly so on long tasks and with the weak agent.
- One caveat remains, and you should hear it from us: the data leak.

---

## Slide 13. The data leak, and why it is small (1:30)

On the slide:
- The leak: v4 runs on the same tasks as v3. We studied v3's results on them before building v4.
  So every v4 result is on "known tasks".
- 1. The cost result does not depend on it. v3 already showed the saving, in its own pre-registered run. Cost comes
  from how many LLM calls a guard makes, not from knowing the tasks.
- 2. Why it is small:
  - TGR's rules and predicates were never changed.
  - No right answer of any task is used anywhere in the method.
  - The lessons are about how to word a question, not what to do in a task.
  - No test conversation text is in any prompt.
  - The fix rounds were judged on block counts, never on task success.
  - Everything was frozen before the first live run.
  - H uses a new agent, and 15 long tasks never ran before.
- 3. Why we could not avoid it: τ-bench has few tasks of each kind. v3 had already used 99 of the 165 test-file
  tasks. The other 66 are the partner's final test, which we kept unused.

Say, in order:
- The leak: v4 runs on the same tasks as v3, and we studied v3's results before building v4.
- Point one: it cannot touch the cost result. v3 already showed the saving, in its own pre-registered run. And cost
  depends on how many LLM calls a guard makes, not on knowing the tasks.
- Point two: the leak is small. The rules were never touched. No right answer is used anywhere. The lessons are
  about wording, not about what to do in a task.
- Also, our fixes were judged on block counts, never on task success. So they could not tune v4 to win these tasks.
- Point three: we could not avoid it. τ-bench has few tasks. v3 had used 99 of the 165. The other 66 are the
  partner's final test, which we kept unused.
- The clean next step: a fresh build without v3's notes, tested on those 66 tasks. It would only confirm fairness,
  and it costs about $25.

---

## Closing line (0:10)

Same rules, same predicates. Code first, tiny questions for the rest. Cheaper in every test, at least as good at
finishing tasks, and no more harm than TGR.

---

## Backup slides (only if asked)

- B1: smoke test, 4 conversations, passed. Not counted.
- Money: H hit its $8 limit at 307 of 594 conversations. We raised it to $15 before looking at any H result. One
  task was dropped, so H has 98 tasks. Total spend $24.49 of $30.
- Dev check: the first run failed (3.75 times the judge's blocks). The cause was a code bug that made one question
  crash. After the fix: 1.16 times. Two fix rounds were needed. The plan allowed one, and we asked before the second.
- K13 (transfers): 27 of 30 on its hard-no cases, one short of the mark. The misses all let a transfer through,
  which changes no data. Accepted and recorded.
- The 15 long tasks v3 never ran lean slightly the wrong way (1 win, 2 losses). Too few to say much.
- Direct (one LLM checks the policy directly) is also in the report. It is about as safe as v4 on H but costs 2.4
  times as much.
