# Proposed plan changes (v2), from your answers on the review

Date 2026-10-21. Status: approved and applied to the plan (`overview.md`, `p1.md`, `p3.md`, `p4.md`, `p5.md`,
`p7.md`, `p8.md`, `p9.md`, new `p10.md`).

## Your answers, and what they change
| point | your answer | change |
|---|---|---|
| H1 | Use the base database for code predicates. For the other types, decide true, false or unknown from the predicate's description, using database entries if needed. | The state now starts from τ-bench's database, not from an empty table (option B instead of A). See section 1. |
| H2 | Good fix | Part 8 reports two versions (tracker unknown stays unknown / falls back to the judge). |
| H3 | Fine | Larger lookup format (`sum`, simple list comprehensions, indexing). See section 2 on LTL. |
| H4 | You trust my Python | No Python review by you. Instead, an independent agent checks the lookups, as in `wiki_processing_exp/p10_TESTING.md`. Each lookup keeps a plain-language line, for the report. |
| H5 | Track the metrics, no stop | No go / no-go point. Part 3 reports the share of blocks that involve a code-type predicate as a metric. |
| L3 | Why can we not claim a gain? | We can, if we also run new conversations. New Part 10. See section 3. |

## 1. H1: the state starts from the database
**How it works:**
1. **Starting state:** τ-bench's data files (retail: users, orders, products; airline: users, reservations,
   flights). Every task starts from the same data, because τ-bench reloads the data for each task. We copy the files
   and τ-bench's tool code into `from_shieldagent/tau_bench/` (source: `~/opt/tau-bench-59a200c`, not
   `~/ShieldAgent`).
2. **Updates:** for each executed tool call in the saved conversation, in order, we run τ-bench's own tool code on
   our copy of the data. Blocked calls did not run, so we skip them.
3. **Check:** our replayed output must equal the saved tool output for every executed call. If all are equal, our
   state is exactly the state of the real run. This is a strong test of the tracker.
4. **Two values per predicate:**
   - **fact:** what the database says (for example, the order's status really is pending);
   - **shown:** whether a tool output in the conversation showed it before the step.
5. **The predicate's description decides which value counts.** "Earlier tool output establishes the status is
   pending" uses *shown*; if it was not shown, the value is **false**. A predicate about the fact itself uses
   *fact*. Each lookup states which one it uses, and why.

**What this changes:**
- **Assumptions table:** the guard can read the company's database (realistic in practice, since the company owns
  the database). But the guard now knows facts the agent never looked up, and Direct and TGR do not get this access.
  The report must say so.
- **Label definition (Part 7):** for *fact* predicates, the correct value is the database value. For *shown*
  predicates, it is what the conversation showed.
- **Rolling state section** in `overview.md`: rewritten for the steps above.
- **Part 1:** also copy the τ-bench data files, tool code and license.
- **Part 4:** state = database copy + event log + the set of objects shown so far; with the replay check from step 3.

## 2. H3: does this leave LTL?
No, the rules stay LTL.
- An LTL rule is built from predicates, and the logic only combines their true/false values.
- How a predicate gets its value was never part of LTL: the LLM judge did it, outside the logic.
- The lookups replace the judge for some predicates. They compute the values that go into the same LTL rules, and
  the rules and the decision formula do not change.

## 3. L3: claiming a gain over TGR
- **Why the current plan cannot show it:** it checks saved steps. If one decision changes, the rest of the real
  conversation would change too: the agent gets a different reply and does something else. Task success can only be
  measured by running the conversations again.
- **New Part 10: new conversations with "TGR + tracker":**
  - **The guard:** frozen TGR, with one change. Before the decision, the code-type values are replaced by the tracker
    values. If every predicate of a tool is a code type, the judge is not called at all.
  - **Code:** copy the needed `~/ShieldAgent` code into `from_shieldagent/` and add our guard in our folder:
    - the conversation runner (`repro_online/`, `exp_core/run_online.py`, `exp_core/models.py`,
      `exp_core/model_profiles.json`);
    - TGR's runtime (`method_tgr/`);
    - the LLM callers (`repro_core/llm.py`, `repro_runtime/calls.py`, `policy_pipeline/llm.py`,
      `utility/utils.py`).

    Results are written to our `output/`, never to `~/ShieldAgent/output/`.
  - **Runs** (3 trials each):
    1. train tasks, gpt-6-luna agent;
    2. train tasks, gpt-5-nano agent with gpt-6-luna guard;
    3. after that, val tasks with gpt-6-luna.

    No grok-4.7, and no test tasks.
  - **Baselines:** the saved runs of no guard, Direct and frozen TGR on the same tasks, with the same settings.
  - **Metrics:**
    - task success (pass^1) with paired confidence intervals;
    - blocks per conversation;
    - violations (gold scorer, scoring only);
    - cost.
  - **Cost:** about $0.01–0.015 per conversation. Train runs are 2 × 198 conversations, and val is 99, so about
    $8–12 in total.
- **Limits:**
  - with 20 / 46 train tasks and 3 trials, changes smaller than about 0.08 in pass^1 cannot be told apart from
    noise;
  - most TGR blocks come from conversation predicates, which the tracker does not change, so the gain may be small.
    Part 10 measures it instead of guessing.
- **Ground rules in `overview.md`:** "no LLM calls" becomes "no LLM calls in Parts 1–9; Part 10 calls gpt-6-luna and
  gpt-5-nano, after your approval of its cost".

## 4. Parts after the change
1. Folder setup and copies (now also τ-bench data and tool code, and later the runner code for Part 10)
2. Load the saved steps
3. Predicate types (+ the share of blocks per type, as a metric)
4. State tracker: database copy, replay with the output check, event log, objects shown so far
5. Lookups (larger format; fact or shown; plain-language line; independent agent check)
6. Replay: tracker values vs judge values
7. Manual check of the disagreements
8. Effect on decisions (two versions for unknown)
9. Report and knowledge retention (for Parts 1–8)
10. New conversations with "TGR + tracker", and the final report update
