# Part 2: Step Records and Counts

Made by `python3 -m state_tracker.load_steps` (run in `predicate_correctness/`) on 2026-10-21.
Log: `output/logs/p2_load_steps.log`. Code: `state_tracker/load_steps.py`. File formats: `state_tracker/README.md`.

## What a record is
- One record per attempt where the TGR judge was called (its guard record has a non-empty `judge`).
- Each record has: run, domain, task, trial, step and attempt; the pending action (tool name and arguments);
  the history before the step; the judge's value and evidence for each predicate; the step's rules
  (`circuit`), the decision (`action_allowed`, `margin`) and the violated rules.
- Files: `output/steps_<run>_<domain>.jsonl`, one record per line.

## Counts
- **guard checks:** attempts the guard checked (every attempt).
- **records:** guard checks where the judge was called. The other checks were for actions without rules.
- **judge values:** one per predicate per record (true, false or unknown).
- **blocked:** guard checks with `action_allowed` = false. Most of these calls did not run. After 3 blocks in a
  row at the same step, the 4th attempt runs even if the guard blocks it ("cap override").

| run | domain | episodes | guard checks | records | judge values | true / false / unknown | blocked | not run / cap override |
|---|---|---|---|---|---|---|---|---|
| `luna_train_v5` | airline | 60 | 611 | 321 | 2,224 | 344 / 1,864 / 16 | 12 | 12 / 0 |
| `luna_train_v5` | retail | 138 | 1,738 | 1,729 | 5,489 | 3,237 / 2,236 / 16 | 54 | 54 / 0 |
| `nano_train` | airline | 60 | 825 | 531 | 3,877 | 996 / 2,775 / 106 | 94 | 91 / 3 |
| `nano_train` | retail | 138 | 2,323 | 2,322 | 8,614 | 5,039 / 3,510 / 65 | 416 | 375 / 41 |

## Compared with the expected numbers
Expected: brainstorm sections 2.3 (blocks) and 2.4 (judge values), split per domain by the earlier analysis.

| run | domain | judge values: expected / found | blocked: expected / found | same? |
|---|---|---|---|---|
| `luna_train_v5` | airline | 2,224 / 2,224 | 12 / 12 | yes |
| `luna_train_v5` | retail | 5,489 / 5,489 | 54 / 54 | yes |
| `nano_train` | airline | 3,877 / 3,877 | 94 / 94 | yes |
| `nano_train` | retail | 8,614 / 8,614 | 416 / 416 | yes |
| `luna_train_v5` | both (gpt-6-luna agent) | 7,713 / 7,713 | 66 / 66 | yes |
| `nano_train` | both (gpt-5-nano agent) | 12,491 / 12,491 | 510 / 510 | yes |

All counts are the same as expected. There is no difference to explain.

## Check: the history is right
- **Rule.** The history of a step is `executed[:executed_prefix_len]`: the system message, the first user
  message, then 2 messages per executed step (the agent's message, and the tool output or the user's reply).
  The guard's trace has one entry per executed step. So: history length = 2 + 2 × trace length.
- **Checked on every record** (not only on 5), with 4 more rules: the number of agent messages in the history,
  the number of earlier executed attempts (`past_trace`) and the step number all equal the guard's trace length;
  the history starts with the system message.
- **Result:** 4,903 records, 0 problems.

5 example steps (random, seed 0):

| step | history (messages) | agent messages in history | earlier executed steps | guard's trace length | same? |
|---|---|---|---|---|---|
| `nano_train/retail/task2/trial0/step4/attempt1` | 10 | 4 | 4 | 4 | yes |
| `nano_train/retail/task27/trial2/step11/attempt1` | 24 | 11 | 11 | 11 | yes |
| `luna_train_v5/retail/task101/trial0/step2/attempt1` | 6 | 2 | 2 | 2 | yes |
| `nano_train/airline/task14/trial1/step16/attempt1` | 34 | 16 | 16 | 16 | yes |
| `nano_train/retail/task63/trial0/step12/attempt2` | 26 | 12 | 12 | 12 | yes |

## Check: the tasks
`splits.json` maps each task index (as a string) to train, val or test, per domain: `splits[domain]["split"][str(task_index)]`.

| run | domain | tasks | train tasks in splits.json | trials per task | not train |
|---|---|---|---|---|---|
| `luna_train_v5` | airline | 20 | 20 (same set) | [0, 1, 2] | 0 |
| `luna_train_v5` | retail | 46 | 46 (same set) | [0, 1, 2] | 0 |
| `nano_train` | airline | 20 | 20 (same set) | [0, 1, 2] | 0 |
| `nano_train` | retail | 46 | 46 (same set) | [0, 1, 2] | 0 |

Every episode is a train task, and every train task has 3 trials.

## Check: the pending action
For each record whose call ran, `executed[history_len]` must be the same call (tool name and arguments, or
the same reply text), and `executed[history_len + 1]` must be the saved output. Part 4 relies on this.
Result: 4,371 records checked, 0 problems.
Also, in all 4,903 records the guard's matched action should be the pending action: 0 problems.

## Inputs
| file | sha256 | same as `SHA256SUMS` (Part 1)? |
|---|---|---|
| `from_shieldagent/runs/luna_train_v5/airline/tgr/episodes.jsonl` | `3dd77c9334cc9565…` | yes |
| `from_shieldagent/runs/luna_train_v5/retail/tgr/episodes.jsonl` | `8dc1396da20917bd…` | yes |
| `from_shieldagent/runs/nano_train/airline/tgr/episodes.jsonl` | `81e3cb1330d82829…` | yes |
| `from_shieldagent/runs/nano_train/retail/tgr/episodes.jsonl` | `1f3e825586217951…` | yes |
| `from_shieldagent/splits/splits.json` | `a3ab3471c67dad9a…` | yes |

## Other facts for later parts
- **The judge saw only the last 24,000 characters of the history** (`render_history(history, max_chars=24000)`
  in `method_tgr/runtime.py`). So in long conversations the login and the first look-ups can be missing from
  the judge's view. Records where this cut happened (`judge_history_cut` = true):

  | run | domain | records | with a cut | share |
  |---|---|---|---|---|
  | `luna_train_v5` | airline | 321 | 6 | 1.9 % |
  | `luna_train_v5` | retail | 1,729 | 0 | 0.0 % |
  | `nano_train` | airline | 531 | 109 | 20.5 % |
  | `nano_train` | retail | 2,322 | 189 | 8.1 % |

  Example: in `nano_train/retail/task23/trial0/step21` the history has 28,011 characters. The login (step 1)
  was cut from the judge's view. The 3 attempts whose rules use `user_authenticated` got the value false
  ("No earlier successful email or name-and-zip lookup appears"), and all 3 were blocked.
  Brainstorm section 2.2 said that TGR's cut was not counted. These are the counts.

- **Values the judge did not return:** 0. TGR sets them to unknown with the evidence "(not returned by the judge)".
- **Records per kind:** `luna_train_v5/airline` tool call 95, reply 226; `luna_train_v5/retail` tool call 1057, reply 672; `nano_train/airline` tool call 208, reply 323; `nano_train/retail` tool call 1365, reply 957.
- **Guard checks without a judge call** (the action has no rules, so it is allowed without the judge): `luna_train_v5/airline` 290 (get_reservation_details 162, search_direct_flight 58, get_user_details 51, search_onestop_flight 14, list_all_airports 4, calculate 1); `luna_train_v5/retail` 9 (calculate 9); `nano_train/airline` 294 (get_reservation_details 147, search_direct_flight 81, get_user_details 49, search_onestop_flight 17); `nano_train/retail` 1 (calculate 1).
- **Predicates seen in the records:** `luna_train_v5/airline` 40; `luna_train_v5/retail` 24; `nano_train/airline` 40; `nano_train/retail` 24 (of 42 airline and 24 retail). Never judged: `luna_train_v5/airline` `cancelled_flight_certificate_send_conditions_met`, `delayed_flight_certificate_send_conditions_met`; `luna_train_v5/retail` none; `nano_train/airline` `cancelled_flight_certificate_send_conditions_met`, `delayed_flight_certificate_send_conditions_met`; `nano_train/retail` none.

## Format choices
- **Trial:** from the episode's `trial` key (396 of 396 episodes have it). If it were missing, the
  trial would be the number of earlier episodes of the same task in the file (0, 1, 2).
- **History:** the saved records hold `history_len` and `episode_line` (line in the copied `episodes.jsonl`,
  from 0), not the messages. Inline, the histories would add about 80 MB, because each step repeats the steps
  before it. `read_steps()` in `load_steps.py` adds `history` and `past_trace` back from the checked copy.
- **Step id:** `<run>/<domain>/task<T>/trial<R>/step<S>/attempt<A>`. `step` is the number of executed steps
  before the attempt; `attempt` counts the tries at that step (1 = first try; 2-4 come after blocks).
- **Blocked vs executed:** `action_allowed` is the guard's decision. `executed` says whether the call ran.
  They differ only for cap overrides (blocked, but run).
