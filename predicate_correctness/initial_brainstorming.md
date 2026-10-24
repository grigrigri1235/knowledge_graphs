# Predicate correctness: initial brainstorm

Draft, 2026-10-21. File paths are inside `~/ShieldAgent/` unless written otherwise.

## The idea
A guard decides if an agent's action is allowed by checking rules. Rules are built from predicates: yes/no
statements such as "the order status is pending" or "the user confirmed the action". At every step, an LLM decides if
each predicate is true, false or unknown. Nothing checks these answers. One wrong answer can make the guard block a
correct action or allow a wrong one.

We want these answers to be more accurate. Two limits:
- The predicates are not a fixed list. The LLM writes new ones for each policy.
- We already use an LLM for this step.

## Words used in this document
| word | meaning |
|---|---|
| agent | the LLM that serves the customer and calls tools |
| action | one tool call (for example `cancel_reservation`) or one message to the user |
| guard | the program that checks each action before it runs, and can block it |
| rule | a condition on an action, for example "`cancel_reservation` is allowed only if the user confirmed" |
| predicate | a yes/no statement used in rules, for example `user_confirmed` |
| value | the answer for a predicate at one step: true, false or unknown |
| block | the guard stops the action and sends the agent a message that says why |
| gold | hand-written rules and checks that we use only to score results, never as input to a method |
| pass^1 | share of conversations in which the agent completed the task |
| Direct | the simplest guard: one LLM call per action reads the whole policy and answers "allowed or not" |

---

## 0. The advanced POC: `~/ShieldAgent`

### What it is
`~/ShieldAgent` (GitHub: `yanai-1701/ShieldAgent_Taubench`) is the advanced POC. It continues the first POC in this
repository, on the same retail policy (`files_given/wiki.md`, the τ-bench retail policy), plus the τ-bench airline
policy.

It tests guards inside τ-bench conversations. In each conversation:
1. A simulated user (an LLM) asks for something, for example to cancel an order.
2. The agent (another LLM) talks to the user and calls tools.
3. Before each action, the guard checks it. A blocked action does not run; the agent gets the guard's message
   instead.
4. At the end, τ-bench checks if the database is in the expected state. This is task success.

There are three guards:
- **Direct** (see the table above).
- **ShieldAgent:** our copy of the paper's method, as close to the paper as we could make it. Before the
  conversations, an LLM turns the policy into rules, improves them in several rounds, and groups them by action.
- **TGR:** our own method. Before the conversations, one LLM call writes rules of the form "tool X is allowed only
  if <condition>", using the agent's real tool names.

Section 1.2 shows how ShieldAgent and TGR check one action.

### Results so far
- ShieldAgent completes fewer tasks than Direct. In retail, pass^1 is 0.25 lower with gpt-5-nano (test tasks) and
  0.32 lower with gpt-6-luna (train tasks).
- On the validation tasks, TGR completes the most tasks of the three guards. In retail, its pass^1 is 0.10 higher
  than Direct's.
- The final run on the test tasks has not been done yet.

Details: `docs/SUMMARY_REPORT.md`. All numbers: `docs/RESULTS.md`.

### What the advanced POC added to the first POC
| | first POC (`code_projects/src/`) | advanced POC (`~/ShieldAgent`) |
|---|---|---|
| policy | handbook files, then `wiki.md` | the same `wiki.md`, plus the airline policy |
| tests | 12 hand-written cases | full τ-bench conversations (594 in one full run) |
| which action is checked | written in each test case | taken from the conversation |
| predicate values | written in each test case | set by an LLM during the conversation |
| rule building | extraction once, plus one cleanup pass | all the paper's steps, repeated until the rules stop changing |
| rules about earlier steps | not checked | checked |
| guards | one | three: Direct, ShieldAgent, TGR |

This brainstorm is about setting predicate values. The first POC does not have that step, so we study the advanced
POC.

Full comparison: `knowledge_retention.md`, section 2 (this repository).

---

## 1. How predicate values are set

### 1.1 In the paper
For each action, the paper's guard:
1. Finds the rules for the action.
2. Runs a planner LLM. The planner sets easy values itself. For the others it calls tools:
   - Search finds items in the conversation;
   - Binary-Check answers a yes/no question about the conversation.
3. Checks each rule with a logic prover, then computes the decision.

The paper trained two small models (InternVL2-2B) for Search and Binary-Check. These models get a question in plain
language, not a predicate name, so they do not need a fixed list of predicates. The authors did not publish them.

### 1.2 Our two guards, step by step
Example: the agent calls `cancel_pending_order` for order `#W123`.

| step | ShieldAgent (our copy of the paper) | TGR (our method) |
|---|---|---|
| 1. Name the action | An LLM picks up to 3 action names from the rules, for example `modify_order` | The tool name: `cancel_pending_order` |
| 2. Find the rules | All rules that use these action names | The rules written for `cancel_pending_order`. No rules: the action is allowed |
| 3. Set the values | A planner LLM, in up to 15 rounds. It can ask a helper LLM to search the conversation or to answer yes/no questions | One LLM call (the "judge") for all predicates at once |
| The LLM sees | The last 24,000 characters of the conversation, the action, the rules | The same, plus facts from the policy (for example today's date) and, for each predicate, where to look: call arguments, tool results, user messages, agent messages |
| The LLM returns | true, false or unknown for each predicate | true, false or unknown for each predicate, plus a short evidence text |
| 4. Decide | The paper's formula | The same formula |

Extra details:
- **ShieldAgent:**
  - before step 3, another LLM call drops rules that do not apply and rewrites the predicate descriptions;
  - values from earlier steps are stored and reused; they are never checked again.
- **TGR:** the evidence text is shown to the agent after a block. Nothing checks it.

Code:
- ShieldAgent: `repro_runtime/extract.py` (step 1), `plan.py` (step 3), `mln.py` (step 4);
- TGR: `method_tgr/runtime.py`.

### 1.3 Why one wrong value changes the decision
All rule weights are 1. For a rule "the action is allowed only if <condition>", the formula gives:
- condition true: allow;
- condition false: block;
- condition unknown: block.

So the decision follows the values. In our runs, the threshold setting (ε) never changed a decision. The paper says
extra "knowledge" rules protect the guard from wrong values. In our runs these rules cannot change a decision.

A wrong value has one of two results:
- **Wrong block:** a required fact is set to false or unknown, or a forbidden fact is set to true. The agent loses a
  turn, and often the task.
- **Missed violation:** a required fact is set to true, or a forbidden fact is set to false. A wrong action runs.

---

## 2. What goes wrong today

### 2.1 Errors in how a predicate is written (when rules are built)
| error | example | source |
|---|---|---|
| The predicate adds a requirement that the policy does not have | `flight_id_is_iata_flight_number`: the LLM said "HAT005 is not an IATA flight number" and blocked a correct flight change. This rule caused 83 airline blocks. | `docs/reproduction/p2_pilot_report.md`, `docs/reproduction/p6_report.md` |
| The predicate asks who said something, not whether the fact is known | "The agent asked for the payment method" was false when the agent suggested a method and the user agreed: 7 of 16 airline blocks. "The user provided the payment method": 6 of 14 retail blocks. | `docs/tgr/p2_report.md` |
| The predicate can only be known after the action runs | "The order belongs to this user", checked before the call that looks up the order: 42 retail blocks | `docs/tgr/phase2_log.md` |
| One predicate holds several facts | `booking_required_information_established` = user id, trip type, origin and destination, all matching the call | `tgr_rules/airline/frozen/rule_set.json` |
| A word in the policy is unclear | Does "Cancel both orders" count as explicit confirmation? Does "Use PayPal" after a block? TGR's judge says yes; our gold scorer says no. | `docs/tgr/val_report.md` |

Later TGR versions changed their prompts to reduce the second and third errors.

### 2.2 Errors in the value (during the conversation)
| error | example | source |
|---|---|---|
| Date not computed | "No flight segment has been flown" set to unknown, although all flight dates were after today's date: 5 of 16 airline blocks | `docs/tgr/p2_report.md` |
| Invented knowledge | the IATA example above | `docs/reproduction/p6_report.md` |
| Wrong item | a gift card balance used for a refund instead of a payment | `docs/tgr/p2_report.md` |
| Start of the conversation missing | The LLM sees only the last 24,000 characters, so the login and the first look-ups can be cut. Share of ShieldAgent checks with a cut: 12.2 % (airline, gpt-5-nano); 3–7 % (gpt-5-nano agent, gpt-6-luna guard); under 0.3 % (gpt-6-luna). TGR cuts the same way; we have not counted it. We have not measured the effect on values. | our logs, counted 2026-10-21 |
| Tools not used | ShieldAgent's planner called Search or Binary-Check 3 times in 321 runs. It set almost all values without them. | `docs/reproduction/p2_pilot_report.md` |
| Different answers on repeat | The same steps, run again with another effort level, got the same decision in 79–80 % of cases. | `docs/reproduction/p2_pilot_report.md` |

### 2.3 Where this matters
- In ShieldAgent, most blocks come from bad rules and from actions mapped to the wrong predicates. Better values
  would not fix it.
- TGR fixed these two problems. The TGR report says that most of its remaining errors are predicate values. So we
  study TGR.

Values that caused TGR blocks. In all rows the guard is gpt-6-luna.

| run | domain | blocks | most frequent cause (count) |
|---|---|---|---|
| train, gpt-6-luna agent | airline | 12 | "details listed and confirmed" = false (5) |
| train, gpt-6-luna agent | retail | 54 | "agent reminded the user to include all items" = false (26) |
| val, gpt-6-luna agent | airline | 4 | "request cannot be handled" = unknown or false (2) |
| val, gpt-6-luna agent | retail | 29 | "agent reminded the user to include all items" = false (19) |
| train, gpt-5-nano agent | airline | 94 | "details listed and confirmed" = false (28) |
| train, gpt-5-nano agent | retail | 416 | "agent reminded the user to include all items" = false (167); "user logged in" = false (106) |

What this shows:
- Most blocks come from predicates about the conversation: did the agent remind or list, did the user confirm. Code
  cannot compute these; they need an LLM.
- We do not know yet how many of these values are wrong. An earlier manual check found that many "reminder" blocks
  were correct according to the policy text.
- The gpt-5-nano agent makes more mistakes, so the guard has more to decide. Better values can show an effect there.

### 2.4 Data we already have
Every guarded step is saved with the conversation, the action and the values. TGR also saves the judge's evidence
text.

| run | ShieldAgent values | TGR values |
|---|---|---|
| train, gpt-6-luna agent | 7,327 | 7,713 |
| val, gpt-6-luna agent | 4,287 | 4,081 |
| train, gpt-5-nano agent | 10,174 | 12,491 |

No value has a "correct" or "wrong" label yet.

---

## 3. The predicates are not a fixed list: does that stop us?
A normal classifier learns a fixed list of classes, but our predicates change with each policy. Four points:
1. **For one policy, the list is fixed.** After the rules are built, the predicates do not change: TGR has 42 airline
   and 24 retail predicates. We can write code, tests or train a model for each predicate right after the rules are
   built, before the guard runs.
2. **A model can read the predicate's description.** The input is the description, the evidence and the action. The
   output is true, false or unknown. The outputs are the same for every policy. The paper's Binary-Check model works
   this way.
3. **Code can compute some predicates.** When the rules are built, the LLM can also write a short function for each
   predicate.
   - The function reads the tool call's arguments, earlier tool results and today's date.
   - During the conversation the code runs, and the LLM handles only what the code cannot decide.
   - In TGR, 25 of 42 airline and 10 of 24 retail predicates use only tool arguments and tool results.
   - Our gold checks (`agent/predicates/*.py`) compute similar facts in 5–15 lines each, for example
     `order_status_is_pending`. We may use the gold code only for scoring, not as an example for the LLM.
4. **The LLM keeps a role.** When the rules are built, it writes the predicates, the code and the tests. During the
   conversation, it answers only the predicates about the conversation, and checks again the values that cause a
   block.

---

## 4. Ideas

### A. Write better predicates (when the rules are built)
- **A1. One fact per predicate.** Split predicates that hold several facts.
- **A2. Predicate type.** Give each predicate a type: tool-argument check, database fact, date or number calculation,
  or conversation fact (listed, confirmed, reminded, chose). The type decides who sets the value: code or the LLM.
  - Every predicate gets exactly one type.
  - A predicate that needs two types (for example a database fact and a user message) holds several facts, so it
    must be split into one predicate per fact. So A2 also covers A1 and the fourth error in section 2.1 ("one
    predicate holds several facts").
  - Example: `booking_required_information_established` uses user messages, tool results and call arguments. It
    would be split into one predicate per fact.
- **A3. Predicate check.** A second step checks each predicate:
  - Can it be known before the action?
  - Does it add a requirement that the policy does not have?
  - Does it ask who said something, when the policy does not care?
- **A4. Tests whose expected answer does not come from an LLM.** Tests written by the same LLM share its mistakes,
  so they cannot check it. The expected value comes from somewhere else:
  - **hand-written:** a few cases per predicate type (not per predicate), so the number stays small;
  - **edits of saved conversations:** change "pending" to "delivered", remove the user's "yes", move a date. The
    expected value comes from the edit, not from an LLM.

  They include the hard cases from section 2. We use them to test the judge and the code before any run.

### B. Compute values with code
- **B1. Code per predicate.** The LLM writes a function for each predicate that uses tool arguments, tool results or
  dates.
  - The function returns true, false or "cannot tell". "Cannot tell" goes to the LLM judge.
  - We test the code on saved steps and review every case where it disagrees with the judge.
- **B2. Table of facts.** A parser turns tool results into a table: orders, reservations and payment methods, with
  status, dates and balances, plus today's date. The code and the judge both read it.
- **B3. Rolling state.** One state per conversation, kept up to date by code, with no LLM. It extends B2.
  - **Start:** the database at the start of the task. In τ-bench these are its data files, which τ-bench loads
    again for every task.
  - **Update:** after each executed tool call, run the tool's own code on our copy of the database. Blocked calls
    did not run, so we skip them. Check: our output must equal the output saved in the conversation.
  - **Also kept:** the objects that tool outputs showed so far (with the version shown), and a log of the executed
    calls (tool, arguments, worked or failed).
  - **Two values per predicate:**
    - fact: what the database says (the order really is pending);
    - shown: what the conversation showed before the step.

    The predicate's description decides which one counts. "Earlier tool output establishes that the order is
    pending" uses shown: if no tool output showed the order, the value is false, not unknown.
  - **What it can set:** database facts become lookups (order status, gift card balance, cabin, flight dates
    compared with today's date). Events ("user authenticated", "order already modified once") come from the log.
    Conversation predicates ("user confirmed", "agent listed the details") stay with the LLM.
  - **Lookups:** written in a small fixed format that code checks, each with a plain-language sentence.
  - **Limit:** the guard now knows facts that the agent never looked up. Direct and TGR do not have this access, so
    a report must say so.
  - Plan: `code_projects/docs/planning/state_tracking_exp/`.
  - Report (Parts 1–8 on saved steps, Part 10 in new conversations): `code_projects/docs/reports/state_tracking_report.md`.
    Part 10 result: the tracker fixes judge errors (77 changed decisions, all scorable ones right), but its effect on
    pass^1 is too small to measure (train luna +0.076 [+0.03, +0.13], mostly noise; val −0.020 [−0.10, +0.05]).

Risks: a bug in the code repeats every time, and the code must run in a sandbox.

### C. Ask the LLM better (no training)
- **C1. Check the quote.** The judge must quote the text that decides each value. Code checks that the quote is in
  the conversation or in the arguments. If it is not, the value becomes unknown, or is checked again.
- **C2. One question per predicate.** Ask about each predicate (or each rule) separately, instead of all in one
  answer. This costs more calls.
- **C3. Ask several times.** Ask k times and take the majority. If the answers differ, treat the value as uncertain.
  This costs k times more on the checked steps.
- **C4. Keep the start of the conversation.** When the conversation is too long, keep its first part (login, first
  look-ups) as well.
- **C5. One definition per conversation word.** Write one definition each for "listed", "confirmed", "reminded" and
  "chose". Use it when the rules are built, in the judge, and in our labels.

### D. Use uncertainty in the decision
- **D1. Probabilities instead of true or false.** Give each value a probability, for example from C3. The paper's
  formula can use probabilities if we add them as weighted facts; today it gets only true, false or unknown.
- **D2. Ask instead of block.** If a block depends on an uncertain value, the message asks the agent to check the
  fact first.

### E. Check again only what matters
- **E1. Before a block.** Find the values that cause the block, and check only those again with a stronger method:
  code, C3, or a stronger model. TGR blocks 0.1–0.4 times per conversation with gpt-6-luna, so this adds little cost.
  It reduces wrong blocks.
- **E2. Before a database change is allowed.** Check again the values that would cause a block if they were
  different, for example an instruction counted as a confirmation (val, retail task 16). It reduces missed
  violations.

### F. Train a model (only if A–E are not enough)
- **F1. A small model that reads the predicate's description.** The input is the description, the evidence and the
  action; the output is true, false or unknown. Training data:
  - answers from a stronger LLM on our saved steps;
  - edited conversations with a known answer: change "pending" to "delivered", remove the user's "yes", move a date;
  - the test cases from A4;
  - the values from the code in B1.
- Limits:
  - our VM (1 CPU, 1.9 GB RAM) cannot train or run the model, so we would need a GPU machine;
  - the model may not work on a new policy.

**Suggested order:** first C4, C1, B1 with B2, E1 and A2. They are cheap, and each one tests one idea. Then D1. F1
only if the others leave a clear gap.

---

## 5. How to measure

### 5.1 What we label
- **One item:** one guarded step and one predicate. It contains the conversation up to that step, the action, the
  predicate description, the value and the evidence.
- **The correct value** is what a careful reader would answer from the conversation. If the conversation does not
  show a fact, the correct value is unknown, even if the database knows it.
- **Where labels come from:**
  1. **Gold code.** Some of our predicates mean the same as a gold check, for example `order_status_checked_pending`
     and `order_status_is_pending`. We match them by hand and use the gold result as the label. This is free, but it
     covers mostly database facts.
  2. **Manual labels.** About 300–400 items, chosen to cover each predicate type, each value, and values that caused
     a block. Two people label part of them, to check that they agree. The labeling guide also gives the definitions
     for C5.
  3. **Labels from a stronger LLM**, checked against the manual labels. Not grok-4.7: it is kept for the final run.
  4. **The τ-bench database.** Only to see the best possible result, because it knows facts that the conversation did
     not show.
- **Tasks:** labels come from train-task conversations only. Val and test tasks are kept for the final check.

### 5.2 What we count
- The share of correct values, per predicate type. Wrong blocks and missed violations are counted apart.
- The wrong values that change the decision. We compute this without new LLM calls: we run the decision again
  (`repro_runtime/mln.py::decide`) with the corrected value.
- How often the same question gets the same answer.
- Later, in full conversations:
  - pass^1, compared with Direct and with the current TGR;
  - blocks per conversation, and the share of blocks that were correct;
  - violations caught and missed;
  - cost.

### 5.3 First check how much there is to gain
Before we build anything:
1. Take the saved steps.
2. Put in the corrected values.
3. Run the decision again.
4. Count how many blocks go away and how many violations would be caught.

If few decisions change, predicate values are not TGR's main problem.

---

## 6. First steps
1. Compare against the current TGR (git tag `tgr-frozen-v1`). Any change becomes a new version, developed on train
   tasks only.
2. Build the label set (5.1) from saved TGR steps: train tasks, with the gpt-6-luna agent and with the gpt-5-nano
   agent.
3. Measure the current accuracy and the possible gain (5.3).
4. Test the cheap ideas on the same saved steps, without new conversations: C4, C1, B1 with B2, E1, C3.
5. Run only the ideas that help in full conversations: train tasks first, then val. Compare with Direct and with the
   current TGR.

Steps 2–4 for idea B3 (the rolling state) are done on saved steps, and step 5 in new conversations (train, then val):
`code_projects/docs/reports/state_tracking_report.md`.

## 7. Open questions
1. Do we improve TGR, ShieldAgent, or both? Suggestion: TGR (section 2.3).
2. Do we fix how predicates are written, how values are set, or both? They need different fixes (section 2).
3. Who decides the correct meaning of "confirmed", "chose" and "reminded": the policy text, our gold scorer, or the
   judge?
4. Is a GPU machine available, in case we want F1?
5. Which LLM may produce labels?
6. What matters more: fewer wrong blocks, or fewer missed violations?
