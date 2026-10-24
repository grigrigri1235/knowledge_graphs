# State Tracking Experiment Plan - Overview

Plan version 2 (2026-10-21): changes from `plan_changes_v2.md` applied.

## Simplifying assumptions
Compared with the real world, this experiment assumes the following.

**About the world:**
| we assume | in the real world |
|---|---|
| The predicates and rules are fixed: the 66 frozen TGR predicates (42 airline, 24 retail). We do not add, change or remove any. | Policies change, and new predicates are needed. |
| The policy text is fixed, one text per domain. | Policies are updated. |
| Every task starts from the same known database: τ-bench's data files. | The starting state is whatever the live database holds. |
| Only the agent's tool calls change the database. | Other people and systems change data during a conversation (for example, an order ships). |
| The guard can read the database. So it also knows facts the agent never looked up. Direct and TGR do not have this access. | A guard may not get database access, or the data may be spread over many systems. |
| Tool outputs are JSON objects with ids, and are complete and correct. | Outputs can be plain text, partial, split over pages, or wrong. |
| We know what each tool returns and changes, because we run τ-bench's own tool code. | APIs can be undocumented, or change between versions. |
| Today's date is fixed and stated in the policy. | The clock moves. |
| One user per conversation, and one tool call at a time. | Several users, and calls in parallel. |
| The user is simulated by an LLM. | Real users are less predictable. |

**About our measurement:**
- **Offline replay (Parts 1–9):** we check saved steps. If a decision changes, we do not know how the conversation
  would have continued. Part 10 runs new conversations to measure that.
- **Exact database copy:** running τ-bench's tool code on our copy gives the same results as the real run. Part 4
  checks this on every executed call.
- **One sample:** the saved judge values come from one run. Another run could give different values.
- **Correct answers:** a person's review counts as the correct answer. People can also be wrong or disagree.
- **Few tasks:** Part 10 has 20 / 46 train tasks and 10 / 23 val tasks, with 3 trials each. Changes smaller than
  about 0.08 in pass^1 are hard to tell from noise.

## How predicate values are set in this plan
For each pending action in a conversation:
1. **Action → rules:** the action is the tool name. We take the rules TGR wrote for that tool. A tool with no rules
   is allowed.
2. **Rules → predicates:** we list the predicates in those rules.
3. **Predicate → type:** we look up the predicate's type (Part 3).
4. **Value:**
   - **code types** (argument, database fact, event): we run the predicate's lookup on the state (Parts 4–5). The
     state is the database copy plus what the conversation has shown. The result is true, false or unknown;
   - **conversation and mixed types:** the LLM judge's value. In Parts 6–8 that is the saved value; in Part 10 the
     judge is called as in TGR.
5. **Decision:** all values go into TGR's decision formula, unchanged. The result is allow or block.

```text
pending action → tool name → TGR rules for that tool → predicates → type?
   code types (argument, database fact, event)  → state + lookup → value
   conversation, mixed                           → judge's value
all values → TGR decision formula (LTL rules, unchanged) → allow or block
```

The rules stay LTL. The lookups only replace the judge in computing some predicate values. How a predicate gets its
value was never part of LTL.

## How we decide what is a predicate
- **We do not choose the predicates.** Before any conversation, TGR's rule-writing step (one LLM call) reads the
  policy and writes each rule as "tool X is allowed only if <condition>". In the condition, it names and describes
  every predicate, and lists where its evidence comes from. We use these 66 predicates as they are.
- **We decide each predicate's type** (Part 3, reviewed by a person). Questions, in this order:
  1. Does the value need the meaning of a user or agent message?
     - Only that: **conversation**.
     - That plus something code can check: **mixed**.
  2. Does it need objects from the database (an order's status, a gift card's balance)? **Database fact.** The
     lookup may also compare dates and amounts.
  3. Does it need only which tool calls ran before, and whether they worked? **Event.**
  4. Does it need only the pending call's arguments? **Argument.**
- **Examples** (draft; Part 3 decides):
  | type | example predicate |
  |---|---|
  | argument | `cancellation_reason_is_allowed` |
  | database fact | `order_status_checked_pending`, `gift_card_balance_covers_order_total` |
  | event | `user_authenticated` |
  | conversation | `user_explicitly_confirmed_pending_action` |
  | mixed | `user_chose_pending_payment_method` (the user's message and the call's arguments) |

## The rolling state ("database") for the predicates
**What it is.** A Python structure in memory, one per conversation, with four parts:
- **Database copy:** τ-bench's data, kept up to date with the executed tool calls.
- **Shown set:** the objects (kind and id) that appeared in tool outputs before the step, with the version that was
  shown.
- **Event log:** one entry per executed tool call: step, tool, arguments, worked or failed, and the output.
- **Fixed facts from the policy:** today's date, when the policy states it (the airline policy does).

**Where the starting state comes from.**
- The database copy starts from τ-bench's data files:
  - retail: users, orders, products;
  - airline: users, reservations, flights.

  τ-bench reloads these files for every task, so every task starts from the same data. We copy the files, and
  τ-bench's tool code, into `from_shieldagent/tau_bench/` (source: `~/opt/tau-bench-59a200c`).
- The shown set and the event log start empty.

**How it is updated.** For each executed tool call in the conversation, in order:
1. Run τ-bench's tool code for that call on our database copy.
2. **Check:** our output must equal the output saved in the conversation. If every output matches, our copy is
   exactly the state of the real run. A mismatch is reported (Part 4).
3. Log the call in the event log, as worked or failed (failed outputs start with "Error").
4. Add the objects in the output to the shown set. A newer version replaces an older one.

Blocked calls did not run, so we skip them, the same as the guard.

**Two values per predicate, and the description decides which one counts:**
- **fact:** what the database says. For example, the order's status really is "pending".
- **shown:** what the conversation showed before the step.

For example, "Earlier tool output establishes that the order status is pending" uses *shown*: if no tool output
showed the order, the value is **false** (not unknown). A predicate about the fact itself uses *fact*. Each lookup
states which one it uses (Part 5).

**Example (retail):**
| step | tool call | state after it |
|---|---|---|
| 1 | `find_user_id_by_email` → `"yusuf_rossi_9620"` | event: the user lookup worked |
| 2 | `get_order_details("#W123")` → order JSON | shown: order `#W123`, status "pending" |
| 3 | pending: `cancel_pending_order("#W123", reason "no longer needed")` | the lookups run on this state |

Lookups for step 3:
- `user_authenticated` (event): a user lookup worked earlier, so **true**.
- `order_status_checked_pending` (shown): order `#W123` was shown with status "pending", so **true**. Without step 2,
  the value would be **false**, even though the database says the order is pending.
- `cancellation_reason_is_allowed` (argument): the reason is "no longer needed" or "ordered by mistake", so **true**.

## Objective
- **Parts 1–9:** on saved TGR conversations,
  1. compute predicate values with code from the rolling state;
  2. compare them with the LLM judge's values;
  3. count how many guard decisions would change.
- **Part 10:** run new conversations with "TGR + tracker", and compare task success, blocks, violations and cost
  with frozen TGR and Direct.

## Background
- **The idea and the reasons for it:** `predicate_correctness/initial_brainstorming.md` (section 4),
  `docs/planning/predicates_correctness/section4_feedback_and_state_tracking.md`, `review_before_implementation.md`
  and `plan_changes_v2.md` (this folder).
- **Base:** the advanced POC in `~/ShieldAgent` (commit `1bacdb0`; TGR rules frozen at tag `tgr-frozen-v1`).

## Ground rules
1. We change no file in `~/ShieldAgent` (my partner's directory). We only read it.
2. Everything we need is copied to `predicate_correctness/from_shieldagent/`, with its source path, commit and
   checksum. This includes τ-bench's data and tool code (from `~/opt/tau-bench-59a200c`). Copies are never edited.
   If a copy needs a different path, we write a small wrapper in our own folder.
3. Parts 1–9 use only train-task conversations. Part 10 also uses val tasks. Test tasks are never used.
4. The state starts from τ-bench's database (see "The rolling state").
5. Gold code from `~/ShieldAgent` is copied only in Part 7, after our lookups are frozen, and is used only for
   scoring. Our code never imports it.
6. Every command writes its output to a file in `predicate_correctness/output/logs/`.
7. Parts 1–9 use only the Python standard library. Part 10 uses the existing venv `~/venvs/tau-bench`, without
   installing anything.
8. LLM calls:
   - none in Parts 1–9;
   - Part 10 calls gpt-6-luna and gpt-5-nano, and only after you approve its cost (about $8–12);
   - never grok-4.7.
9. After each part: update this file and say "done with part i".

## Who does what
- **Me:** code, drafts and tables.
- **An independent agent** (not the one that wrote the lookups): checks the lookups (Part 5).
- **You (or your partner):** review the types (Part 3) and the disagreements (Part 7). Approve the cost of Part 10.

## Folder layout
```text
code_projects/
├── docs/planning/state_tracking_exp/   this plan (overview.md, p1.md … p10.md)
├── docs/reports/state_tracking_report.md   final report (Parts 9 and 10)
└── predicate_correctness/
    ├── initial_brainstorming.md
    ├── from_shieldagent/               copies (never edited; PROVENANCE.md)
    │   ├── code/                       repro_core/ltlf.py, taubench_steps.py; repro_runtime/aspm.py, verify.py, mln.py
    │   ├── tau_bench/                  τ-bench data files, tool code and license (from ~/opt/tau-bench-59a200c)
    │   ├── rules/                      frozen TGR rule sets (airline, retail)
    │   ├── policies/                   airline and retail policy texts
    │   ├── runs/                       saved conversations (train in Part 1; baselines on val in Part 10)
    │   ├── splits/                     splits.json
    │   ├── runner/                     conversation runner and TGR code (Part 10)
    │   └── gold/                       gold code, for scoring only (Part 7)
    ├── state_tracker/                  our code: state, lookups, replay
    ├── guard/                          our guard "TGR + tracker" (Part 10)
    ├── tests/                          our tests
    └── output/                         results; logs/ for command output
```

## Execution sequence
- **Part 1 (`p1.md`):** Folder setup, copies (including τ-bench data and tool code), brainstorm update [Done, with notes]
  - Note: also copied `run_*.json` and τ-bench's `envs/base.py` (reference); `runs/` is 43 MB (< 50 MB), so no `.gitignore` change.
- **Part 2 (`p2.md`):** Load the saved steps and check the counts [Done, with notes]
  - Note: all counts match. The step files hold the history as a reference into the checked copy, not inline (about 80 MB less); `read_steps()` adds it back.
- **Part 3 (`p3.md`):** Give each predicate one type, plus the share of blocks per type [Done, with notes: person review pending]
  - Types frozen 2026-10-22 after an independent agent's review (0 changes; `output/p3_review_changes.md`):
    `output/predicate_types.json` sha256 `20dade34ca42965be3a3ae139749651b385b268de7d6bd4eb07ca12a21ee1889`. Person
    review pending; if it changes a type, record the new sha256 here.
  - Note: the agent review stands in for the person review (p3.md asks for yours). 195 of 576 blocked steps (33.9 %)
    involve a code-type predicate (`output/p3_type_counts.md`). The mixed example `user_chose_pending_payment_method`
    above is typed conversation.
- **Part 4 (`p4.md`):** State tracker: database copy, replay check, shown set, event log [Done, with notes]
  - Note: 2,891 of 2,891 replayed outputs equal the saved ones (exact string), 0 parse failures. Added: `walk()` (one pass per conversation), nested kinds (`payment_method`, `variant`), and a check that `build_state` gives the same state for all 4,903 step records.
- **Part 5 (`p5.md`):** Lookups (larger format, fact or shown, independent agent check) [Done, with notes]
  - **Frozen 2026-10-22:** `state_tracker/lookups_airline.json` sha256
    `882ca35ed6a1bbda1ea97d1eed87dd36246b2111cc1d4d47c5645ce12b701dc7`, `state_tracker/lookups_retail.json` sha256
    `77918b7727831f8c18353f5b5dce89d7e05017aa4db11f31722ee23cc41044a4`. From now on a lookup changes only to fix a
    clear bug, logged in `output/p5_lookup_fixes.md`.
  - Note (independent check, 2026-10-22, `output/p5_independent_check.md`): 28 ok, 1 wrong
    (`item_replacements_are_available_same_product_different_option`: no position pairing), 2 unclear
    (`pending_flight_update_is_basic_economy`: stale cabin field; `origin_destination_and_trip_type_preserved`: leg
    order). The checker's own values agree with the lookups in 6,690 of 6,690 saved runs.
  - Note (answers, `output/p5_audit_responses.md`): the wrong lookup and the leg order are fixed. The three cabin
    lookups now take the cabin from the newest successful flight update of the reservation, because τ-bench leaves the
    `cabin` field stale; this changes 37 saved values (true to false) and is a choice Part 7 may revisit. Other points
    are explained.
  - Note: 31 lookups (21 airline, 10 retail). The format is as listed in p5.md; it has no arithmetic, so sums and
    differences are written with `sum([...])`. Smoke run on all 4,903 step records: 0 errors (`output/p5_smoke.md`).
- **Part 6 (`p6.md`):** Replay: tracker values vs judge values [Done, with notes]
  - Note: 6,690 code-type values (33.1 % of 20,204 judge values); 6,428 agree, 262 disagree (85 judge true / tracker
    false, 70 judge false / tracker true, 106 judge unknown, 1 tracker unknown). Frozen lookups unchanged, no fix
    needed. Each disagreement also gets a short `group` label and says whether the judge's cut history hid the tool
    output the lookup used (`output/p6_agreement.md`).
- **Part 7 (`p7.md`):** Manual check of the disagreements [Done, with notes: person review pending]
  - Note: all 186 disagreements on blocked steps are more than the "about 150 in total" in p7.md. All 186 are
    kept, plus 30 random other disagreements (of 76) and 50 random agreements: 266 items, seed `20261022`
    (`state_tracker/p7_sample.py`). The sheet is blind (value A / value B); the key is `output/p7_key.json`. The
    review is done by an independent agent instead of a person.
  - Note (agent review, 2026-10-22; person review pending): all 266 items answered in
    `output/p7_review_sheet_answered.md` and `output/p7_review_answers.json`: A right 102, B right 113, both right 50,
    both wrong 1, predicate unclear 0. Five readings decide 116 answers (stale cabin field, superseded order status,
    signed price difference, no gift card in the call, same-item exchange); the person should confirm them.
  - Note (results and gold check, 2026-10-22; `output/p7_review_results.md`): tracker right in 263 of 266 items,
    judge in 52; on the 216 disagreements the tracker is right in 213, the judge in 2, both wrong in 1. Gold code
    copied to `from_shieldagent/gold/` and used only by `scoring/` (outside `state_tracker/`; checked by
    `tests/test_no_gold_import.py`). Gold decides 189 items and equals the tracker and the reviewer in all 189, the
    judge in 46. In the other 77 gold gives None, which matches the judge's unknown (67 of them) rather than the
    tracker's "not shown → false"; under that convention the tracker is right in 190 and the judge in 113 of 266.
- **Part 8 (`p8.md`):** Effect on decisions (two versions for unknown) [Done, with notes]
  - Note: check 1 passes on all 4,903 records (same allow/block and margin as saved, with or without the past
    trace). With the tracker's values, blocks go from 576 to 537: 67 removed (30 distinct steps; 56 through
    `user_authenticated`), 28 added (27 through the order-status predicates). Against Part 7's reviewed values, all
    67 removals and 10 of the additions fix an error, 0 add one; 18 additions are not covered by the review
    (`output/p8_decision_changes.md`).
  - **Version for Part 10: (b), a tracker unknown is replaced by the judge's value.** Chosen 2026-10-22, before
    Part 10. Reason: (a) and (b) give the same decision on every saved record (the tracker gives unknown in 1 value,
    and no decision depends on it), so both have 0 wrong blocks; the tie rule written before the full run picks (b),
    because it never turns a judge value into unknown. Part 10's judge must give a value for a code-type predicate
    whose lookup gave unknown.
- **Part 9 (`p9.md`):** Report and knowledge retention for Parts 1–8 [Done, with notes: your reading of the report is pending]
  - Note: report `docs/reports/state_tracking_report.md` (Parts 1–8, 5 examples, limits, next steps, empty Part 10
    section). Also updated: `knowledge_retention.md` (section 6), `codebase_structure.md`, brainstorm sections 4 and
    6. The report says that the reviews in Parts 3, 5 and 7 were done by independent agents and the person reviews are
    pending. "Last updated" dates are 2026-10-22 (the day of the work).
- **Final check of Parts 1–9** (independent agent, 2026-10-22) [Done]
  - Note: all 7 checks pass (`predicate_correctness/output/verify_parts_1_9.md`). Only the person reviews of Parts 3,
    7 and 9 are open.
- **Part 10 (`p10.md`):** New conversations with "TGR + tracker", and the report update [Done, with notes: your reading of the report and the person reviews of Parts 3 and 7 are pending]
  - Subtask 1: the user approved the whole plan, LLM cost included ("complete the plan", 2026-10-22).
  - Subtasks 2-5 (2026-10-22, no LLM call): 59 runner files copied to `from_shieldagent/runner/` (all equal commit
    `1bacdb0`; `~/ShieldAgent` unchanged); every output path moved to `output/` by our wrapper
    `guard/run_online.py` (`output/p10_paths.md`); our guard `guard/tgr_tracker.py` (version b); 19 new tests, 153 of
    153 pass. Offline, on all 4,903 saved records with the judge's saved values, the guard gives Part 8's version (b)
    decision in every record (`output/p10_guard_offline_check.md`). With the frozen rules the judge is never skipped
    (every tool's rules have a conversation or mixed predicate).
  - Independent audit (2026-10-22, no LLM call): every check passes, and nothing needed a fix
    (`predicate_correctness/output/p10_audit.md`). On all 5,497 saved attempts, the online state equals the offline
    state. The judge prompts are byte-identical to the partner's. Where the tracker agrees, TGR's decisions and
    feedback are reproduced. The profiles, rules and splits equal the baselines. grok-4.7 and the test split are
    refused, and no file is written outside `output/`. Projected spend for the runs: about $8.3.
  - Subtask 6, smoke test (2026-10-22, $0.047): 4 train conversations (luna-dev), 0 errors, 2 blocks with TGR's
    feedback, 0 lookup errors, 0 replay mismatches, 2 judge values corrected by the tracker; nothing written outside
    `output/` (`predicate_correctness/output/p10_smoke.md`). Projected cost of the runs: about $7.2 ($12.4 with a
    1.5x margin).
  - Subtask 7, runs 1-2 (2026-10-22, $6.63): train, 3 trials, guard `tgr_tracker`, profiles luna-dev
    (`p10_luna_train`) and nano-agent-luna (`p10_nano_train`). All 396 conversations (60 + 138 per profile) finished,
    with 0 errors and no rerun. 0 lookup errors and 0 replay mismatches. Part 10 spend so far $6.67, projected total
    $7.95 (`predicate_correctness/output/p10_runs.md`). `~/ShieldAgent` got 3 partner commits during the runs (HEAD
    `7e6575b`). They were not ours, and all 136 copies still match.
  - Subtask 7, run 3 (2026-10-22, $1.21): val, 3 trials, guard `tgr_tracker`, profile luna-dev (`p10_luna_val`).
    All 99 conversations (30 + 69) finished, with 0 errors and no rerun. 0 lookup errors, 0 replay mismatches.
    `~/ShieldAgent` unchanged during the run. **Part 10 LLM spend in total: $7.885** (no LLM run is left)
    (`predicate_correctness/output/p10_runs.md`, section "Run 3").
  - Subtasks 8-9, baselines and metrics (2026-10-22, no LLM call): 30 baseline files (none, direct, frozen TGR) copied
    to `from_shieldagent/runs/` (now 120 MB, so in `.gitignore`); the partner's metric and gold scorer scripts copied to
    `from_shieldagent/scoring/` and run unchanged through `scoring/p10_eval.py` (`output/eval/`). Their baseline numbers
    equal the partner's saved files (0 of 2,074 values differ). Paired Δ pass^1, TGR + tracker − frozen TGR, both
    domains: train luna-dev +0.076 [+0.03, +0.13], train nano-agent-luna +0.020 [−0.05, +0.09], val luna-dev −0.020
    [−0.10, +0.05]. Blocks per conversation the same or lower everywhere. Per step, the tracker changed 77 of 5,774
    judged decisions (68 blocks removed, 9 added); under gold v2 every scorable change was right (18 + 9)
    (`predicate_correctness/output/p10_metrics.md`).
  - Subtask 10, report (2026-10-22, no LLM call): the "Part 10: new conversations" section and a "Key numbers and
    verdict" block at the top of `docs/reports/state_tracking_report.md`; `knowledge_retention.md` (section 6) and
    brainstorm sections 4 and 6 updated. Verdict: partly a success. The tracker works and its scorable changes are all
    right, but the pass^1 effect is too small to measure: on train luna-dev, 63 of 66 tasks had no changed decision and
    still show +0.058 of the +0.076 (noise check `scoring/p10_report_extra.py`, `output/p10_report_extra.json`).
  - Final independent check of Parts 1–10 (2026-10-22, no LLM call): all 8 checks pass, 0 differences in the
    recomputed numbers (copies 176 of 176, tests 153 of 153, Part 10 pass^1 and Δ, 77 changed decisions, $7.885;
    no grok-4.7, no test task). `~/ShieldAgent` changed only through the partner's own commits (HEAD `7e6575b`)
    (`predicate_correctness/output/verify_parts_1_10.md`).
  - **Open (person):** read the report; review the types (Part 3), the five readings and the false-vs-unknown question
    (Part 7). If a review changes a type or a lookup, Parts 6–8 must be run again, and the Part 10
    runs no longer match the frozen inputs.

## Not in this plan (possible next steps)
- The LLM writes the lookups in the same format; compare them with ours.
- Narrow LLM questions for the conversation predicates ("Is this message a yes to these details?").
- Split mixed predicates while the rules are written (ideas A1 and A2).
- The test split, or grok-4.7. Both need your partner's agreement, because they are reserved for the final
  evaluation.

## Open question
- What does "deploy" mean in `CLAUDE.md` rule 5?
