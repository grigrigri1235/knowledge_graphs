# state_tracker: our code

Our code for the state tracking experiment (`docs/planning/state_tracking_exp/`). Standard library only. It reads
the copies in `../from_shieldagent/` and never imports gold code.

| file | part | what it does |
|---|---|---|
| `paths.py` | 1, 2 | folder and file paths that every part uses |
| `tgr_to_aspm.py` | 1 | TGR's `to_aspm` (copied function): a rule set as the input of the decision code |
| `load_steps.py` | 2 | the saved conversations as one record per guarded step; checks and counts |
| `tau_copy.py` | 4 | loads τ-bench's tool code, data files and the policies from the copies (no `litellm`/`pydantic`) |
| `tool_table.json` | 4 | per tool: changes the database or not; the kind and id of the objects in its output |
| `state.py` | 4 | the rolling state: database copy, shown set, event log, today's date (`build_state`) |
| `replay_check.py` | 4 | replays every saved tool call and compares; writes `output/p4_replay_check.md`, `p4_parse_report.md` |
| `lookup_format.py` | 5 | the lookup format: validator (Python's `ast`), evaluator on a `State`, checks of the lookup files |
| `lookups_airline.json`, `lookups_retail.json` | 5 | one lookup per code-type predicate (21 airline, 10 retail); frozen 2026-10-22 (sha256 in `overview.md`) |
| `run_lookups.py` | 5 | runs every lookup on the Part 2 step records; writes `output/p5_smoke.md` |
| `replay.py` | 6 | tracker values next to the judge's values; writes `output/p6_values.jsonl`, `p6_disagreements.jsonl`, `p6_agreement.md` |
| `p7_sample.py` | 7 | the review sample (fixed seed) and the blind review sheet; writes `output/p7_review_sheet.md`, `p7_review_items.json`, `p7_review_conversations.json`, `p7_key.json` |
| `decide_again.py` | 8 | TGR's decision again with the tracker's values (versions a and b); writes `output/p8_decision_changes.md`, `p8_changes.jsonl` |

## The saved runs: `episodes.jsonl`
Path: `from_shieldagent/runs/<run>/<domain>/tgr/episodes.jsonl`. One episode (one conversation) per line.
ShieldAgent wrote them with `repro_online/episode.py::run_episode` and the TGR guard (`repro_online/guards.py`,
`method_tgr/runtime.py`).

### Episode
| field | meaning |
|---|---|
| `task_index` | the τ-bench task |
| `trial` | 0, 1 or 2 |
| `env`, `guard`, `profile`, `models` | domain; `"tgr"`; model profile; models of agent, user and guard |
| `executed` | the messages that really happened: the system message (policy), the first user message, then for each executed step the agent's message (`assistant`, with one tool call or with text) and the answer (`tool` output with the same `tool_call_id`, or the user's reply). Blocked attempts are not in it. |
| `messages` | what the agent saw: `executed` plus the blocked attempts and the guard's feedback. We do not use it. |
| `attempts` | one entry per try of the agent, in order (below) |
| `n_exec_steps`, `n_blocks`, `n_cap_overrides` | counts of executed steps, blocked attempts, cap overrides |
| `reward`, `done`, `reward_info` | the task result. `reward_info.actions` are the benchmark's expected actions (answers): we do not use them. |
| `cost`, `latency`, `calls`, `usage_roles`, `seconds`, `error` | run statistics |

### Attempt (`attempts[i]`)
| field | meaning |
|---|---|
| `exec_step` | number of executed steps before this try |
| `attempt` | 1 = first try at this step; +1 after each block (1 to 4) |
| `action`, `kwargs` | the pending action: tool name and arguments, or `"respond"` and `{"content": text}` |
| `agent_text` | the text of the agent's message |
| `blocked` | true: the guard blocked it, and it did not run |
| `cap_override` | true: the guard blocked it, but it ran, because there were 3 blocks in a row before it |
| `executed_prefix_len` | `len(executed)` when the guard checked. The history is `executed[:executed_prefix_len]`. |
| `observation` | (only if it ran) the tool output or the user's reply |
| `feedback` | (only if blocked) the text the agent got instead |
| `guard` | the guard's record (below) |

### Guard record (`attempts[i].guard`)
| field | meaning |
|---|---|
| `step_index`, `trace_len_before` | the step number, and the length of the guard's trace before it (= executed steps before) |
| `kind`, `name`, `action_text` | `tool_call` or `respond`; tool name or `respond`; the action as text, as the judge saw it |
| `matched` | `[name]` if the rule set knows the action, else `[]` |
| `circuit` | the ids of the rules for the matched action. Empty: allowed, with no judge call (`reason` = "no rules for this action"). |
| `judge` | `{predicate: {value: true, false or null, evidence}}`. Only when `circuit` is not empty. null = unknown. |
| `trace_position` | `{action: true or false}` for every action, plus the judge values. It is the step's entry in the guard's trace. |
| `mln` | per matched action, details of `repro_runtime.mln.decide`: `group_rules`, `group_unknowns`, `method`, `p_execute`, `margin`, `violated_by_action`, `at_risk`, `false_in_best_world` |
| `margin`, `epsilon`, `action_allowed`, `allowed_eps0` | P(run) − P(not run); 0.1; the decision (allowed iff margin ≥ −0.1); the decision with ε = 0 |
| `violated_rules`, `unknown_predicates`, `feedback_text` | the rules behind a block (`rule_id`, `description`, `logic`); predicates with value null; the feedback text |
| `usage`, `calls`, `seconds`, `attempts` | LLM use (`cost_usd`, `cache_hits`, …) and API retries |

### Relations (checked on all 4,903 judged attempts in Part 2)
- History length = `executed_prefix_len` = 2 + 2 × `trace_len_before`, and `exec_step` = `step_index` = `trace_len_before`.
- For an attempt that ran: `executed[executed_prefix_len]` is its message and `executed[executed_prefix_len + 1]`
  is its output.
- The guard's trace (`past` in `mln.decide`) is the `trace_position` of each earlier attempt that ran.
- The judge saw `render_history(history, max_chars=24000)`: without the system message, and only the last 24,000
  characters.

## Step records (Part 2): `output/steps_<run>_<domain>.jsonl`
One record per attempt whose guard record has a non-empty `judge`. One JSON object per line.

| field | meaning |
|---|---|
| `step_id` | `<run>/<domain>/task<T>/trial<R>/step<S>/attempt<A>` (unique) |
| `run`, `domain`, `task`, `trial`, `split` | where it comes from; `split` is from `splits.json` (always `train` here) |
| `exec_step`, `attempt`, `episode_line` | step and try number; line of the episode in the copied `episodes.jsonl` (from 0) |
| `agent_model`, `guard_model` | the models |
| `kind`, `action`, `kwargs`, `action_text`, `agent_text` | the pending action |
| `history_len`, `trace_len_before` | length of the history (messages) and of the guard's trace (executed steps) |
| `judge_history_chars`, `judge_history_cut` | length of the history as text for the judge; true if the judge saw only the last 24,000 characters |
| `matched`, `circuit`, `judge`, `trace_position`, `action_allowed`, `margin`, `allowed_eps0`, `epsilon`, `violated_rules`, `unknown_predicates`, `mln` | the guard's record, unchanged |
| `judge_usage` | `n_llm_calls`, `cache_hits`, `cost_usd` of the judge call |
| `executed`, `cap_override` | whether the call ran; whether it ran through the cap override |
| `observation`, `api_error` | the output (if it ran); true if a tool output starts with "Error" |

Added in memory by `read_steps()` and `iter_steps()`, not saved:
- `history`: `executed[:history_len]` (the messages; saved files hold only the length, to keep them small);
- `past_trace`: the guard's trace before the step (for `mln.decide`).

## How to load
```python
# from predicate_correctness/
from state_tracker import paths
from state_tracker.load_steps import read_steps

for run, domain in paths.RUN_DOMAINS:
    for rec in read_steps(run, domain):          # with_history=False skips history and past_trace
        rec["history"], rec["action"], rec["kwargs"], rec["judge"], rec["circuit"], rec["action_allowed"]
```

Write the files again: `python3 -m state_tracker.load_steps > output/logs/p2_load_steps.log 2>&1` (also writes
`output/p2_counts.md`). Tests: `python3 -B -m unittest discover -s tests -t .`

## State API (Part 4): `state.py`
The state before a step, built with code only (overview.md, "The rolling state"). Notes on the tools:
`output/p4_tool_notes.md`. Replay check: `output/p4_replay_check.md`.

```python
# from predicate_correctness/
from state_tracker.state import build_state, load_db, walk, parse_date
from state_tracker.load_steps import read_steps

for rec in read_steps("nano_train", "retail"):
    st = build_state(rec["history"], rec)      # replays the tool calls in the history; rec = the pending action
    st.pending                                  # {"tool": "cancel_pending_order", "args": {...}, "kind": "tool_call"}
    st.db_get("order", rec["kwargs"].get("order_id"))      # fact: the object in the database copy, or None
    st.shown_get("order", rec["kwargs"].get("order_id"))   # shown: the newest version shown before the step, or None
    st.events_where(tool="find_user_id_by_email", ok=True) # earlier calls of that tool that worked
    st.today                                    # datetime(2024, 5, 15, 15, 0) for airline, None for retail
```

### Functions
| name | what it does |
|---|---|
| `load_db(domain)` | a fresh deep copy of τ-bench's data. The files are read once with τ-bench's `load_data()`. |
| `build_state(history, action=None, domain=None, strict=False)` | the state before a step: a fresh copy, then the tool calls of `history` replayed in order. `action` (the pending action) is stored, not run. `domain` is taken from the system message (the policy) if not given. `strict=True` raises `ReplayMismatch` at the first replayed output that differs from the saved one. |
| `walk(executed, domain=None, stops=None)` | one pass over a whole conversation; yields `(n, state)` for the state after `executed[:n]`, for each `n` in `stops`. The same object is yielded each time, so use it before the next step. Faster than `build_state` per step (no copy per step). |
| `Tracker(domain)` | the step-by-step builder behind both: `feed(messages)`, `feed_message(msg)`, `apply_call(tool, args, saved_output)`, `finish()`. |
| `run_tool(domain, db, name, args)` | one call as τ-bench's `Env.step` runs it (exception → `Error: ...`). |
| `parse_date(text)` | 'YYYY-MM-DD', 'YYYY-MM-DDTHH:MM:SS' or 'YYYY-MM-DD HH:MM:SS' → `datetime`, else None. |
| `is_failure(output)` | true if the output starts with `Error` or `Unknown action` (or is not text). |

### The State object (read only; do not change it)
| field / method | meaning |
|---|---|
| `domain` | `airline` or `retail` |
| `db` | the database copy: τ-bench's data dict `{table: {id: object}}` after the replayed calls |
| `db_get(kind, id)`, `db_all(kind)` | **fact**: one object (or None), or a list of all objects of a kind |
| `shown`, `shown_get(kind, id)`, `shown_all(kind)` | **shown**: `{kind: {id: newest version shown}}`; one object (or None); a list |
| `shown_meta[kind][id]` | `{"event", "step", "tool"}` of the call that showed the newest version; flights also have `"dates": {date: event}` |
| `events`, `events_where(tool=None, ok=None)` | the event log; filter by tool name (a name or a list) and worked/failed |
| `today`, `today_text` | the policy's current time (`datetime`, text) or None |
| `pending` | the pending action `{"tool", "args", "kind"}`; a reply has tool `respond` and args `{"content": ...}` |
| `n_steps` | executed steps in the history (agent messages) |
| `mismatches`, `parse_problems`, `problems` | replayed outputs that differ from the saved ones; outputs that could not be parsed; tool messages without a call |

### Event (one per executed tool call, in order)
| field | meaning |
|---|---|
| `index` | 0, 1, 2, … in this conversation |
| `step` | executed steps before the call (agent messages before it; replies to the user count too) |
| `tool`, `args` | the tool name and the arguments as sent (from the agent's message) |
| `ok` | worked: the output does not start with `Error` (or `Unknown action`) |
| `output` | the saved output (the tool message); the replayed one if the history has none |
| `match`, `json_match` | the replayed output equals the saved one (exact string; same JSON). None if nothing was saved |
| `changes_db` | the tool can change the database (`tool_table.json`) |
| `tool_call_id` | links the call to its tool message |

### Kinds and the shown set
| domain | kind | from which outputs | id | version kept |
|---|---|---|---|---|
| both | `user` | `get_user_details`, `modify_user_address` (retail) | the `user_id` argument | the user object as shown |
| both | `payment_method` | inside each shown user (`payment_methods`) | its `id` | the method plus `user_id` |
| retail | `order` | `get_order_details` and the 6 order write tools | `order_id` | the order as shown |
| retail | `product` | `get_product_details` | `product_id` | the product with all variants |
| retail | `variant` | inside each shown product (`variants`) | `item_id` | the variant plus `product_id` |
| retail | `product_type` | `list_all_product_types` | product id | `{name, product_id}` |
| airline | `reservation` | `get_reservation_details` and the 5 reservation write tools | `reservation_id` | the reservation as shown |
| airline | `flight` | `search_direct_flight`, `search_onestop_flight` | `flight_number` | the shape of `flights.json`: base fields plus `dates` with only the shown dates. A newer output for a date replaces that date only |
| airline | `airport` | `list_all_airports` | the code | `{code, city}` |

- Only outputs of calls that worked are parsed. A newer version of an object replaces the older one.
- The shown set holds the **saved** output (what the conversation showed). The replay check showed that it equals the
  replayed output for every saved call.
- Text outputs add no objects: `find_user_id_by_*` (the user id), `send_certificate`, `calculate`, `think`,
  `transfer_to_human_agents`. The event log keeps them.
- `db_get` and `db_all` use the same kinds. `product_type` is built from `products`; `airport` from the constant list
  in `list_all_airports`. Nested kinds come with the parent's id added, as in the shown set.

### Speed
`load_db` costs about 0.04 s (retail) and 0.12 s (airline) per copy. For all 4,903 step records, `build_state` takes
a few minutes; `walk` over each conversation once is faster.

Run the replay check again: `python3 -B -m state_tracker.replay_check > output/logs/p4_replay_check.log 2>&1`.

## Lookups (Part 5): `lookup_format.py`, `lookups_<domain>.json`
A lookup computes one code-type predicate (argument, database fact, event) from the state and the pending call's
arguments. It is one Python expression. The format is in p5.md and at the top of `lookup_format.py`.

```python
# from predicate_correctness/
from state_tracker import lookup_format as L
lookups = L.load_lookups("retail")               # predicate -> {expr, uses, if_missing, plain, reason}
L.evaluate(lookups["order_status_checked_pending"], st, args=rec["kwargs"])   # True, False or None (unknown)
L.evaluate_detail(lookup, st, args)              # also: raw value, and why if_missing was used
L.check_lookups("retail")                        # [] if the file is complete and every expression is valid
```

| name in a lookup | bound to | meaning |
|---|---|---|
| `args` | the `args=` given (default: `st.pending["args"]`) | the pending call's arguments |
| `db(kind, id)`, `db_all(kind)` | `st.db_get`, `st.db_all` | **fact**: the database copy |
| `shown(kind, id)`, `shown_all(kind)` | `st.shown_get`, `st.shown_all` | **shown**: newest version shown, or None |
| `events(tool=..., ok=...)` | `st.events_where` | earlier executed calls |
| `today`, `date(text)` | `st.today`, `parse_date` | the policy's current time (airline; None for retail) |

- Also allowed: comparisons, `and`/`or`/`not`, `len`/`sum`/`any`/`all`, list comprehensions and generator
  expressions, `x[key]`, `x[0]`, `x[-1]`, `x.get(field[, default])`, constants, list and tuple displays. Nothing else:
  no arithmetic (add with `sum([a, b])`), no slices, no other names, functions or attributes.
- A one-element loop names a value: `all(... for r in [shown('reservation', args['reservation_id'])])`.
- **if_missing:** a missing object or field (KeyError, IndexError, TypeError such as `None['x']`) or a result of None
  gives the lookup's `if_missing` value (`false` or `unknown`). Any other non-bool result, or an unknown kind, raises
  `LookupEvalError`.
- Check the files: `python3 -B -m state_tracker.lookup_format > output/logs/p5_check_lookups.log 2>&1`.
- Smoke run on all step records (about 30 s): `python3 -B -m state_tracker.run_lookups > output/logs/p5_run_lookups.log 2>&1`.
- **Frozen** on 2026-10-22, after the independent check (`output/p5_independent_check.md`) and the answers to it (`output/p5_audit_responses.md`). After the freeze a lookup changes only to fix a clear bug, logged in `output/p5_lookup_fixes.md` with the case that showed it (p5.md).

## Replay (Part 6): `replay.py`
For each Part 2 step record and each code-type predicate in the rules of the step's circuit, the frozen lookup runs on
the state before the step (`state.walk`), with the pending call's arguments. The value is stored next to the judge's
saved value. About 30 s for all records.

```bash
# from predicate_correctness/
python3 -B -m state_tracker.replay > output/logs/p6_replay.log 2>&1
```

- It stops if a lookup file differs from the frozen sha256. After a logged fix (`output/p5_lookup_fixes.md`), run it
  with `--allow-changed --suffix _v2`, so the first version's files stay for the report.
- `RecordingState` wraps a `State` and records what a lookup reads (`db`, `shown`, `events`). The lookups run
  unchanged on it.

| file | one line per | main fields |
|---|---|---|
| `output/p6_values.jsonl` | step and code-type predicate (6,690) | `step_id`, run, domain, task, trial, step, attempt, `episode_line`, `history_len`, action, predicate, type, `uses`, `if_missing`, `judge_value`, `judge_evidence`, `tracker_value`, `tracker_missing` (why `if_missing` was used), `unknown_reason`, `used` (the objects and events read), `agreement`, `blocked`, `executed`, `cap_override`, `in_violated_rule`, `judge_history_cut` |
| `output/p6_disagreements.jsonl` | disagreement (values differ, including one side unknown) | the same fields, plus `description`, `plain`, `expr`, `action_text`, `circuit`, `violated_rules`, `margin`, `group` (a short label of what the data shows) and `context` |

`context` holds, for the review in Part 7:
- `args`: the pending call's arguments;
- `objects`: each object the lookup read, with its value in the database copy (`db`), its shown version (`shown`), the
  call that showed it (`shown_by`) and whether that output was inside the judge's view (`in_judge_view`; the judge saw
  only the last 24,000 characters);
- `events`: for each `events(...)` filter, the indices it returned and all events of those tools (also failed ones),
  with output (cut at 3,000 characters) and `in_judge_view`.

`agreement` classes: `agree_true`, `agree_false`, `judge_true_tracker_false`, `judge_false_tracker_true`,
`judge_unknown`, `tracker_unknown`, `both_unknown`. The first two and `both_unknown` are not disagreements.

## Review sample (Part 7): `p7_sample.py`
Draws the sample for the review from `output/p6_values.jsonl` and writes a blind sheet. Seed `20261022`.

```bash
# from predicate_correctness/
python3 -B -m state_tracker.p7_sample > output/logs/p7_sample.log 2>&1                  # sample and sheet
python3 -B -m state_tracker.p7_sample --check-answers > output/logs/p7_check_answers.log 2>&1   # count the answers
```

- Sample: every disagreement on a blocked step (186), 30 random other disagreements (of 76), 50 random agreements
  (of 6,428). 266 items, shuffled.
- Each item shows "value A" and "value B" in random order. The sheet does not say which value is the tracker's or
  the judge's, or whether the item is a disagreement. The key is in `output/p7_key.json` (not for the reviewer).
- For every item the state is built again and the frozen lookup is run again; the value must equal the Part 6 value.
- The reviewer fills in the `**Answer**` line of each item in `output/p7_review_sheet.md`. `read_answers()` reads
  them. The script does not overwrite a sheet that has answers (unless `--force`).

| file | what it holds |
|---|---|
| `output/p7_review_sheet.md` | per item: description, what counts as correct, the step, the pending action, a conversation excerpt, the objects (database value; shown or not, and by which message), earlier calls, value A and B with their explanations, and the answer line |
| `output/p7_review_items.json` | the same items as data (`answer` and `note` empty) |
| `output/p7_review_conversations.json` | the full conversations of the items, without the policy; message #k = element k |
| `output/p7_key.json` | per item: which value (A or B) is the tracker's, the sample group, the agreement class, blocked, in a violated rule, the judge's cut history and the Part 6 group. Also the seed and the population sizes (for weighting). |

## Review results and gold check (Part 7, subtasks 4–5)
Not in this folder. The code that scores the review and compares with the gold predicate code is in the separate
folder `predicate_correctness/scoring`. This folder never imports it or the gold code;
`tests/test_no_gold_import.py` checks that. Results: `output/p7_review_results.md` and
`output/p7_scored_items.jsonl`.

## Decisions again (Part 8): `decide_again.py`
```bash
# from predicate_correctness/
python3 -B -m state_tracker.decide_again > output/logs/p8_decide_again.log 2>&1
```
- Check 1: for every step record, TGR's input is rebuilt from the guard record (`current` = action predicates plus
  the judge's values; it equals the saved `trace_position`) and `repro_runtime/mln.py::decide` must give the saved
  allow/block and margin. It does on all 4,903 records, with the past trace and with an empty one. The script stops
  if any record fails.
- Then the code-type values are replaced by the tracker's (`output/p6_values.jsonl`), in version (a) (tracker
  unknown stays unknown) and (b) (tracker unknown -> judge's value), and the decision is run again.
- The Part 7 key and answers give a reference decision where every disagreeing value of a record was reviewed.
- Outputs: `output/p8_decision_changes.md` (counts, Part 7 estimate, the other readings, the chosen version) and
  `output/p8_changes.jsonl` (one line per changed record).
