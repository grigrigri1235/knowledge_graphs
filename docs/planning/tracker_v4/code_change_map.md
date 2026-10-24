# Tracker v4: code change map (file by file)

Written 2026-10-23 for part P1 of `overview.md`. $0, read-only planning. Paths are under
`/home/azureuser/code_projects/predicate_correctness/` unless they start with `docs/`.

**The main idea in plain words.** v4 is v3 with better ways to give predicates their values. Every v3 file stays
byte-identical. v4 adds new files only. Where a v3 module is harness glue (runner, metrics, block messages), v4
**copies** it to a `_v4` file and edits it, so an audit can read one diff. Where a v3 module is a clean library
(evaluator, message view, rule table, soft stop, tool check), v4 **imports it unchanged**. The guard itself is a
small **subclass** of the v3 guard. Four things need care: new helper names must not clash with v3's in the one
shared helper registry; v4 must reuse v3's exception classes; block messages must not leak database values; and
the "transfer escape" needs a per-conversation memory of blocks.

Inputs read for this map: `reading_notes/v3_structure.md`, `port_map.md` (v3 parts only), `metrics_costs.md`,
`tiny_questions.md`, `tracker_v3/lessons_learned.md` §1-2, `tracker_v3/overview.md`, `preregistration_online.md`,
`b2_reading_guide.md`, `approval_request.md`, `tracker_v4/overview.md` (approved 21:55), and the v3 code listed
in the task. Logs of this read: `output/logs/v4_cm_*.txt`.

---

## 0. Ground rules for every P1 agent

### 0.1 How v4 sits next to v3
| rule | why (what breaks otherwise) |
|---|---|
| Never edit a v3 file, a v3 test or a v2 file. `tests/test_no_gold_import.py` too: v4 gets its own copy. | v3 is frozen (`output/eval_v3/v3_freeze.md`, 19 files); `test_v4_v3_untouched.py` checks it |
| New code lives in `state_tracker/v4/`, `guard/*_v4.py`, `scoring/v4_*.py`, `tests/test_v4_*.py`, `tests/audit_v4_*.py`, `scripts/`. Outputs in `output/eval_v4/`. Logs `output/logs/v4_*`. | one place per version |
| **Helper names are global.** `facts_format_v3.register_name` keeps one process-wide registry and refuses a name that is taken by another function. v3's `questions.py` registers `ask`, `ask_first_yes`, `offer_kind`, `offer_amount_ok`, and it is always imported (by `tgr_tracker_v3`). **Every v4 helper name ends in `_v4`.** | a clash raises at import; v3 cost minutes on "helper registry import order" |
| **Reuse v3's exception classes**: `questions_v4.py` imports `BudgetExceeded, NetworkBlocked, RealModeRefused, AnswerNotSaved, RealCallFailed` from `state_tracker.v3.questions`, never defines its own. | `TrackerTGRv3._run` re-raises only `HARD_STOPS` (v3 classes). A new class would be caught as a fact error: a **silent block** (the v3 audit B major) |
| A v4 question helper always calls `hook.ask(...)` on the hook it is given, and finds its question file with `hook.doc`, falling back to the **v4** file (never `load_questions()` of v3). | the lazy probe (`_Probe`) stops at the first `ask`; `_Probe` has no `doc`, so v3's fallback would load the v3 file |
| The v4 guard keeps writing `rec["v3"]` (same layout, `version` = v4) and adds `rec["v4"]` for new fields. | metrics, harm, offline and message-check code read `rec["v3"]` |
| Shared output roots: v4 never writes under `output/eval_v3/`. It reads `output/eval_v3/online_tasks.json`, `b3_tasks.json`, `rule_table_*.json` and (dev check only) `questions_answers.jsonl` read-only. | same data, no change to v3 records |
| Purity (overview §12): no v4 agent opens B2, B3 or hold-out conversations or their tiny-answer logs. So the dossier's "replay every saved v3 K2 block through the new code" is **not done**. | known-task leak stays small |

### 0.2 Interfaces fixed before the agents start (main chat writes these 7 lines into each brief)
1. **Write key** (one "write" for blocks per write and for the escape): `(tool, object id)`. Object id = `order_id`
   (retail order tools), `reservation_id` (airline update / cancel), `user_id` (`modify_user_address`,
   `book_reservation`, `send_certificate`). Write tools = `tool_table.json` `changes_db`.
2. **Tiny block**: a v4 block of a write call where at least one unmet fact of a violated rule is a **text fact**
   (a fact with a question part, or with a part that calls a `listing_*_v4` / `go_ahead_*_v4` helper). The list
   of text facts is computed from the v4 fact files at build time (`tgr_tracker_v4.TEXT_FACTS`).
3. **Escape**: on a `transfer_to_human_agents` check, if one write key has **2 or more tiny blocks** in this
   conversation and no later executed attempt of that key, the transfer fact (retail
   `request_cannot_be_handled_within_scope`, airline `request_cannot_be_handled_with_available_tools`) is set
   true with source `escape`. Counted in `rec["v4"]["escape"]` and in the metrics.
4. **Unclear policy** (per question, in `questions_v4.json` and in the helper call): write checks → ask once more
   with the second wording → still unclear → blocking value (counted). K4, K13, K16 → ask once more → **allow +
   log** (`on_unclear=` keyword in the expression; the value that allows is written in the expression).
5. **`missing` record** (every code line check and every v2-schema answer): `{"line": "order id", "expected":
   "#W2806889", "forms": [...], "fact": ..., "part": ...}`; the answer schema v2 adds `"missing": "<short text>"`.
6. **`rec["v4"]`**: `{version, manifest_sha256, frozen (bool), write_key, tiny_block, escape, reasks: [{qid,
   key1, key2, status1, status2}], unclear_allowed: [{fact, qid}], missing: {fact: [missing records]},
   fast_path: [fact], ask_keys: {fact: [key16]}}`.
7. **`where`** (conversation id on every tiny answer): `{run_id, step, domain, task, trial, arm, check}`; set per
   unit and per check by the runner, kept per thread by the hook.

### 0.3 Overlay files (so many agents can edit one fact file without clashes)
- Fact overlays: `output/eval_v4/overlays/facts_<agent>_<domain>.json` = `{"domain", "by", "facts": {fact: {"combine"?,
  "sources"?, "parts": {pid: part | null}}}}` (null removes a part). One fact belongs to one agent (table in §1.1).
- Question overlays: `output/eval_v4/overlays/questions_<agent>.json` = `{"questions": {qid: entry}, "domain_texts"?}`.
- `scripts/v4_merge_overlays.py` (from the v3 session's `merge_overlays.py`) builds `state_tracker/v4/facts_v4_<domain>.json`
  and `questions_v4.json` from the v3 files plus the overlays, refuses a fact or question owned twice, then runs
  `facts_format_v3.validate`. Only the main chat runs it with `--write`.

---

## 1. File by file

Legend: **COPY** = new file made from the v3 file, then edited (diff is the audit object). **SUB** = new file that
imports the v3 module and overrides a few functions. **NEW** = written fresh. **SHARED** = v3/v2 file used as is.

### 1.1 `state_tracker/v4/` (the predicate values)

| new file | from | what changes (function level) |
|---|---|---|
| `__init__.py` | NEW | empty |
| `facts_v4_retail.json`, `facts_v4_airline.json` | COPY of `state_tracker/v3/facts_v3_<d>.json` (built by the merge script) | Same 24 / 42 fact names, same `rules`, `blocking_value`, `policy`, `who`. Only `parts`, `combine`, `sources`, `plain`, `evidence` of the 28 facts that had a question part change. List below. The authority for each definition is `predicate_table.md`. |
| `questions_v4.json` | COPY of `questions_v3.json` (merge script) | New versions; K2, K5, K9, K11, K14, K15 removed; **K17** = the insurance line (the validator only accepts ids `K<n>`, so not "K-INS"); per question: `second` (second wording, its own version), `few_shot` (made-up yes / no, from the policy), `on_unclear` (`block` / `allow`), `system_version` (1 for unchanged K4, K10, K12; 2 for the rest), `schema` per system version (v2 adds `missing`). `domain_texts.tools` for K13 rewritten from the **v1** wiki sentences (each refused item cites its S id). |
| `questions_v4.py` | NEW (imports v3 `questions` as `Q`) | Reused from Q unchanged: exceptions, `MemoryStore`, `JsonlStore`, `FakeBackend`, `SavedBackend`, `Budget`, `check_real_mode`, `block_network`, `network_events`, `normalize_text`, `message_text`, `cache_key`, `Stats`, `StandInAnswers`. New: `load_questions_v4`, `check_doc_v4`, `question_v4`, `key_version_v4` (**equals v3's `q<v>.s1` for unchanged questions**, so their keys equal v3 keys), `render_v4` (few-shot block; second wording; for system v1 questions the text must be **byte-equal** to v3's `render`), `quote_pieces_v4` (split at **any** punctuation: `, . ; : ! ? … — – -` quotes, brackets, line breaks; each piece ≥ 2 characters must be in the same source), `quote_in_v4`, `parse_answer_v4` (keeps `missing`), `answer_status_v4`, `saved_status_v4`, `ChainStore` (read v4 store, then v3 store read-only; write v4 only), `RealBackendV4(Q.RealBackend)` (only `answer` overridden: schema by the question's `system_version`), `QuestionsV4(Q.Questions)` (overrides `__init__` (refuses the v3 answers file and the v4 dev file unless real), `key`, `ask(qid, inputs, *, fact, part, wording=1)` (also appends one **ask-log line** per ask, cached or not, with `where`), `_as_read`, `_finish` (adds `where_first`, `wording`, `missing`)). Helpers (source `question`): `ask_v4`, `ask_first_yes_v4(qid, candidates, focus=, items=, limit=, on_unclear=)` (re-ask with `wording=2` on unclear / failed quote / bad output; then the policy), `offer_kind_v4` (kind from the **database**: which named, eligible reservations had a delayed or a cancelled flight; quote words only when both kinds exist), `offer_amount_ok_v4` (amounts from **every** `$` amount of the reply, not the quote), `insurance_stated_v4(candidates, value)` (K17 → included / not included / not said vs the call's `insurance`). `register_helpers_v4()` at import. |
| `listing_v4.py` | NEW (imports v3 `message_view` as `MV`, v3 `questions` for `item_options`, `changed_options`, `changed_flights`, `changed_passengers`) | **K2 → code.** `listing_window_v4(ctx)` = the 2 newest agent text messages before the user's go-ahead message + every user message since the last worked write (or the start). `line_specs_v4(state, domain, tool, args)` = one spec per line `{line, expected, forms}` (table below). `line_present_v4(spec, texts)`. `listing_missing_v4(ctx)` → missing records (noted with `ctx.note`). Helpers (source `structure`): `listing_ok_v4()`, `listing_missing_count_v4()`. Uses `MV.has_form`, `MV.value_forms`, `MV.text_names_date`, `MV.exact_payment_forms`, `MV._methods_named` (already accepts id digits). |
| `helpers_v4.py` | NEW | K1 v4 code parts: `go_ahead_candidates_v4(focus=None)` (L = newest agent message where `listing_ok_v4` holds for this call; B = every user message after L up to the call; drops L when `MV.no_after`), `short_go_ahead_v4(text)` (≤ 8 words, starts with a yes word, no `?`, no but / instead / change / not / wait / only: true with **no LLM call**, noted as `fast_path`), `clash_free_v4()` (no user message after L names another payment method, item, address or passenger than the call; message names both values). Ownership: `reply_names_other_db_user_v4()` (the reply holds the full name or email of a database user other than `me` that no user message holds; replaces K5), `other_person_precondition_v4()` (K4's gate at login and catalog reads; definition in `predicate_table.md`). K15 → code: `user_named_airport_v4(code)` (IATA code or city name from the v1 `list_all_airports` output), `trip_fits_v4()` (the call's flights match `flight_type`, origin and destination in the flights table). All `structure` or `database` source as their reads require. |
| `freeze_v4.py` | NEW (uses `state_tracker/v3/frozen.py` functions `sha256_file`, `format_manifest`, `read_manifest`) | One manifest for everything v4 runs on: `output/eval_v4/v4_freeze.sha256` (sha256sum format, sorted). Lists: every v4 method file (`state_tracker/v4/*`, `guard/*_v4.py`, `scoring/v4_online_metrics.py`, `v4_online_interim.py`, `tests/audit_v4_online_recompute.py`, `scripts/v4_after_run.sh`, `scripts/v4_compare_recompute.py`, `docs/planning/tracker_v4/preregistration.md`, `reading_guide.md`) **and** every shared file the v4 runner reads (the same walk as `run_online_v3.guard_input_files()`: `state_tracker/**`, `guard/**`, `from_shieldagent/runner|rules|policies`, rule tables, `online_tasks.json`, `b3_tasks.json`, `splits.json`, `SHA256SUMS`). CLI: `--write` (refuses if the file exists, unless `--replace --why "<text>"` before the freeze, logged), `--check` (exit 1 with changed / missing / new files), `--table` (writes `output/eval_v4/v4_freeze.md` from the manifest; the overview sha table only points to it). API: `check(require=True) -> {"manifest_sha256", "n_files"}`. The manifest never lists itself. |

**Fact-file change list** (28 facts; the rest stay byte-equal to v3, checked by a test). "ask*" = `ask_first_yes_v4`.

| domain | fact | v3 question part(s) | v4 parts (owner agent) |
|---|---|---|---|
| retail | `consequential_action_details_listed` | b K2 | b → structure `listing_ok_v4()`; a → `len(listing_window_v4()) > 0`; sources drop `question` (A1) |
| retail | `user_explicitly_confirmed_pending_action`, `user_confirmed_cancellation_order_and_reason`, `user_confirmed_return_order_items_and_method` | b K1 | a → `len(go_ahead_candidates_v4()) > 0`; new c `clash_free_v4()`; b → `ask*('K1', go_ahead_candidates_v4())` (fast path inside) (A2) |
| retail | `user_chose_pending_payment_method`, `user_chose_price_difference_payment_method` | c K1 | c → `ask*('K1', go_ahead_candidates_v4(focus='payment'))`; a, d unchanged (A2) |
| retail | `agent_reminded_user_to_include_all_items_for_exchange` / `_for_modification` | b K3 | b → `ask*('K3', reminder_candidates(...), items=...)` K3 v2 (A4 text, A3 helper) |
| retail | `request_cannot_be_handled_within_scope` | b K13 | b → `ask*('K13', user_messages(), on_unclear=True)`; window all user messages; escape at guard level (A5) |
| retail | `request_is_for_another_user` | c K4 | b → `other_person_precondition_v4()`; c → `ask*('K4', another_user_pick(), on_unclear=False)` (A5) |
| retail | `response_performs_task_for_another_user` | c K5 | `a OR b`, b → `reply_names_other_db_user_v4()`; K5 gone (A5) |
| retail | `user_specific_information_disclosed` | c K14 | combine `a` (code part a only; R3 still has `user_authenticated`) (A5) |
| airline | `pending_database_change_details_listed_and_explicitly_confirmed` | c K2, d K1 (also K2) | a/b → go-ahead candidates; c → `listing_ok_v4()`; d → `ask*('K1', go_ahead_candidates_v4())` (A1 c, A2 a/b/d) |
| airline | `booking_insurance_decision_established_and_matched` | b K1 focus insurance | b → `insurance_stated_v4(listing_window_v4(), args['insurance'])` (K17); c → go-ahead (A2) |
| airline | `booking_required_information_established` | c K15, e K1 trip | `a AND f AND (b OR d)`: b `user_named_airport_v4` ×2, d `listing_ok_v4()`, f `trip_fits_v4()`; c, e gone (A5) |
| airline | `user_selected_eligible_flight_change_payment_method` | d K1 focus payment | d → `ask*('K1', go_ahead_candidates_v4(focus='payment'))` (A2) |
| airline | `cancellation_context_established` | d K7 | K7 v2 (A4) |
| airline | `insured_cancellation_condition_met` | b K6 | K6 v2 (A4) |
| airline | `user_complained_about_relevant_flight_situation` | b K8, c K9 | `a AND b`, b → K8 v2 (merged complaint); c gone (A5) |
| airline | `cancelled_flight_certificate_send_conditions_met` | f K8 | f → K8 v2 (A5) |
| airline | `delayed_flight_certificate_send_conditions_met` | g K9, h K11 | g → K8 v2 (the delayed kind is already part c, database); h gone (part e is the event) (A5) |
| airline | `cancelled_flight_certificate_response_conditions_and_amount_met` | e K12 amount, f K8 | e → `offer_amount_ok_v4`; f → K8 v2 (A5) |
| airline | `delayed_flight_certificate_response_conditions_and_amount_met` | f K12 amount, g K9, h K11 | f → `offer_amount_ok_v4`; g → K8 v2; h gone (A5) |
| airline | `pending_response_offers_cancelled_flight_certificate` / `_delayed_flight_certificate` | b K12, c offer_kind | b → `ask_v4('K12', ...)` (K12 unchanged); c → `offer_kind_v4` (DB kind) (A5) |
| airline | `pending_response_offers_any_compensation_certificate` | b K12 | `ask_v4('K12', ...)` (helper rename only) (A5) |
| airline | `request_cannot_be_handled_with_available_tools` | a K13, c K16 | a → `ask*('K13', user_messages(), on_unclear=True)`; c → `ask*('K16', user_messages(), on_unclear=True)`; escape (A5) |
| airline | `user_explicitly_requested_compensation` | b K10 | `ask*('K10', ...)` (K10 unchanged) (A5) |

**K2 code lines** (`listing_v4.line_specs_v4`; forms from the dossier, re-counted on the **v1** database by
`scoring/v4_form_check.py`; the τ³ counts in the dossier are the same data but must be re-checked on v1):

| line | accepted (any one) | dropped vs v3 |
|---|---|---|
| order id | `#W1234567` or `W1234567`, any case | — |
| reservation id | the 6 characters, any case | — |
| item (old) | product name, a word of it unique among the order's items, or the item id | — |
| new item | new item id, or each changed option value (short values like "8", "M" only next to the option name); **and no other value of the same option** in the window | — |
| card | last four (brand optional), **4+ trailing digits of the payment id**, the full id, "the original card / payment method" when it is `payment_history[0]`; retail: the brand alone (0 users with 2 cards of one brand) | "real last four only" |
| gift card / PayPal / certificate | the kind word (retail: unique per user), the id, id digits; "original payment method" if original | — |
| several methods | each method and its amount | — |
| address | line 1, line 2 (Suite / Ste / Apt / Unit / #), city, state (code or name), zip | **country** |
| cancel reason | the phrase or a synonym, said by the agent **or the user** | agent-only |
| flight (changed only) | number + date (any format, year optional) | — |
| cabin | basic economy / economy / business | — |
| passenger (changed only) | first + last name | **date of birth** |
| bags | total; the paid number only when > 0 | "M paid" when 0 |
| certificate amount | the amount | — |
| insurance (booking) | K17 (meaning) | — |

### 1.2 `guard/`

| new file | from | what changes (function level) |
|---|---|---|
| `tgr_tracker_v4.py` | SUB of `guard/tgr_tracker_v3.py` (`class TrackerTGRv4(V3.TrackerTGRv3)`) | Imports `state_tracker.v4.{questions_v4, listing_v4, helpers_v4}` (registers the `_v4` names). Constants `NAME = "tgr_tracker_v4"`, `VERSION = "v4.p1.1"`, `FEEDBACK_MODULE = "guard.feedback_v4"`, `TEXT_FACTS` (from the fact files). Overrides: `_step(conv, step)` (reads `conv.v4_blocks`, a list kept on the episode's `Conversation`; after the record exists, appends `{write_key, tiny}` when the check blocked; puts `rec["v4"]`); `_v3_values(step, names, circuit)` (calls super, then applies the **escape** on a transfer check: the transfer fact → true, source `escape`); `_feedback(...)` (same as v3 but imports `guard.feedback_v4`); `_v3_part(...)` (adds `version` v4). New `build(domain, tools, *, meaning, messages, lazy, answers, require_freeze)`: as `V3.build` (rule set flags, `T.check_frozen()`, **`V3.check_frozen_v3()` still runs**: proves v3 files unchanged) plus `freeze_v4.check(require=require_freeze)`, `load_checked_facts_v4(domain)` (the v4 file through `F.load_facts(domain, path=...)` + `F.validate`). `register()` adds offline variants `v4`, `v4_rule`, `v4_full` to `fork/offline_v3.py`'s registry. Unchanged from v3: the probe, lazy evaluation, two keys, OR branch rule, state-error handling. |
| `feedback_v4.py` | COPY of `guard/feedback_v3.py` | `fact_definitions(domain)` loads the **v4** fact file (v3's loads v3 files through a module cache, so it cannot be reused). `fact_evidence()` adds one evidence line per missing record: "Not stated in your listing: the order id #W2806889." / "Not stated: the card. The call uses credit_card_3593714 (Mastercard, last four 3705; the user may call it 'ending in 3714')." / "Your listing says 'black' but the new item 1586641416 is silver." Every expected value passes the same safety rule as database lines: nothing before login, only records of `me` (`record_owner`, `_payment_owner`, `IC.user_data_values`). `fact_advice()`: K1 not confirmed → "Ask: 'Shall I go ahead with <action>? Please reply yes or no.'"; clash → name both values; K3 → the exact sentence; K6 / K7 → "ask the user why"; K13 no → "Your tools can do this: <tool>. Do it, or deny it if the policy forbids it." `VERSION = 2`. `render()` unchanged. |
| `direct_facts_v4.py` | SUB of `guard/direct_facts_v3.py` (`FactsBlockV4(DF.FactsBlock)`, `DirectFactsGuardV4(DF.DirectFactsGuard)`) | Arm `direct_facts_v4` (overview §5). `render()` / `_fact_lines()`: final value with its sign and the deciding value, "user is a regular member: NO (membership gold)"; part lines only for parts that decided; only facts of the pending action's rules (as v3). Facts from the **v4** fact file (its code-only facts; K2 is now code, so the listing fact enters the block). `NAME`, `VERSION`, `build()`. Policy loader, input-sha check, prompt placement and the Direct call are reused unchanged. *Decision for the main chat: if the user prefers an exact repeat of v3's 4 other arms, keep `direct_facts_v3` instead (one constant in the runner).* |
| `run_online_v4.py` | COPY of `guard/run_online_v3.py` | Constants: `ARMS = ("none", "direct", "direct_facts_v4", "tgr_frozen", "tgr_tracker_v4")`, `LLM_ARMS` with `direct_facts_v4`, `V4_ARM`, `V4_ROOT = output/eval_v4`, `DRYRUN_ROOT = output/eval_v4/dryrun`, cache `output/_llmcache/v4_<run_id>`, logs `v4_<step>_<run_id>_s<i>.log`. `STEPS`: `B1` (retail:4 + airline:4, 1 try), `B2p` (99 × 3), `B3p` (64 Stage A, 1 try, train file), `H` (99 × 1, **profile `nano-agent-luna`**), optional `R20` (20 retail dev tasks × 1, only if the $0 check says unused). Each step has its own `profile` and `allowed_models` (H: agent gpt-5-nano, user and guard gpt-6-luna; every other step gpt-6-luna only). `RUN_ID_RE` with these step names. Task loaders reuse v3's files and shas read-only (`load_tasks_file`, `load_b3_tasks_file` logic copied with the same pinned shas). `build_v4_guard()` (was `build_v3_guard`): `OnlineTGRv4Guard.new_episode()` returns a `Conversation` with `v4_blocks = []`; `check()` sets `answers.where` (with the check index) before `tgr.step`. `make_answers_hook()` → `QuestionsV4` + `RealBackendV4`, store `questions/answers_shard<i>of<n>.jsonl`, ask log `questions/asks_shard<i>of<n>.jsonl`. `run_unit()` sets `where` per unit. `guard_input_files()` adds `state_tracker/v4`, v4 tasks; `run.json` gets `v4_manifest_sha256`. The real run refuses without a passing `freeze_v4.check()`. Soft stop: **`soft_stop_v3.SoftStopV3` reused unchanged**, called with `root=V4_ROOT`, `questions=(output/eval_v4/questions_answers_v4.jsonl, output/eval_v4/cases/answers.jsonl)`, `hard_limit_usd=V4_STEP_LIMITS[step]`, `cap_usd=V4_CAP` (dev $2, B1 $2, B2p $40, B3p $20, H $15, cap $80; R20 needs a limit and cap room, see §6). `b1_check()` with v4 arm names. `v4_state_error_checks()` reads `rec["v3"]` of the v4 arm. Unchanged logic: `GroupPool`, shard locks, `RunFiles` (arm names only), sandbox, net recorder, `TinyMeter`, `JudgeMeter`, approval words, backups rule. |

**Shared and untouched** (imported as they are): `guard/tgr_tracker_v3.py`, `guard/tgr_tracker.py`,
`guard/direct_facts_v3.py`, `guard/feedback_v3.py` (D+F still uses its pure helpers), `guard/soft_stop_v3.py`,
`guard/soft_stop.py`, `guard/run_online.py` (frozen TGR builder, `JudgeRouter`, `tools_sha256`), `guard/runner_path.py`,
`guard/write_guard.py`, `state_tracker/v3/{facts_format_v3, code_helpers, message_view, info_classes, questions,
rule_table, tool_check, frozen}.py`, `questions_v3.json` (v4 never reads it except to verify reuse keys),
`output/eval_v3/rule_table_*.json`, `state_tracker/{state, replay, tau_copy, lookup_format, tool_table.json}`,
`fork/offline_v3.py`, the runner copy and the rules under `from_shieldagent/`.

### 1.3 `scoring/`

| new file | from | what changes |
|---|---|---|
| `v4_online_metrics.py` | COPY of `v3_online_metrics.py` | Constants: `ARMS`, labels, `V4`, `MAIN = (V4, FROZEN)`, `SECONDARY = {S1: (direct_facts_v4, direct), S2: (V4, direct_facts_v4)}`, `REPORTED = ((V4, none), (FROZEN, none))`, `SEEN` all true ("known tasks", val no longer "unseen"; the val/train split is still shown). Steps `B1`, `B2p` (main), `B3p` (`report_b3p`: never pooled), `H` (`report_h`: never pooled), `R20`. **New, pre-registered in this script:** `task_expected()`, `unwanted_flags()`, `conv_harm()` (the outcome view moved here from `v3_harm_metric.py`: expected writes per task from any conversation with `reward_info.actions`; each expected write matched once; refusal task → every accepted write), `harm_rate()` with its 95 % range, `compare_harm(a, b)` (paired by task; H verdicts "less harm" upper < 0, "not more harm" upper < +0.05, else "not shown"), `llm_calls()` per conversation (all roles = `usage_roles.agent.calls` + `usage_roles.user.calls` + Σ checks `guard.usage.n_llm_calls`; guard only = the last term; cache hits apart), `blocks_per_write()` (write checks blocked ÷ write checks, cap overrides count as blocked; different writes by write key: share blocked at least once, share blocked and never run), `by_writes()` (tasks grouped by expected writes 0 / 1 / 2 / 3+), `strictness_warning` (v4 blocks per write > 2 × frozen), `escapes`, `unclear_allowed`, `reasks`, `fast_path` counts, `safety()` for **every** arm. Every arm table row carries success and harm side by side. Partner-reproduction block: dropped (not needed). Power: kept. |
| `v4_online_interim.py` | COPY of `v3_online_interim.py` | Arms; `HALF` per step (B2p 742 conversations, B3p 160; H: no success stop, health and cost stops only); `--write-stop` writes `<run_dir>/STOP` when the harm rule fires (pre-registered; it only stops spending). |
| `v4_report.py` | COPY of `v3_p14_report.py` | Sections B2p / B3p / H / R20; harm and calls columns; v3's B2/B3 numbers read from the saved v3 metrics JSON as a **description only** (different tries, no test); cost priors from v3's measured costs; written once from the numbers files. |
| `v4_b1_summary.py` | COPY of `v3_b1_summary.py` | arm names, v4 state errors, D+F v4 facts failures |
| `v4_diagnosis.py` | NEW (classes from `B3_diagnosis.md` / `B2_val_diagnosis.md` method, written before the run) | per lost (task, try): wrong or too-strict block (by question / code line) / agent mistake / noise / step limit / other; reads only the new run folder |
| `v4_form_check.py` | NEW | $0 counts on the v1 database (`tau_copy.load_db`): every accepted form of §1.1 can occur; card-id endings vs last four (0 / 239, 0 / 503 to re-confirm on v1), 2+ cards of one brand, country values, address2 forms, items of one product per order, short option values, airport city names. Also the **retail dev-20 check**: does τ-bench v1's retail dev split appear in our or the partner's data. |
| `v4_cases.py` | NEW | the made-up cases: reads `output/eval_v4/cases/<qid>.jsonl` (written by the blind writers), asks real answers through `QuestionsV4` (budget, approval words), scores against the labels, pass mark ≥ 28 / 30 per side per question; fake mode for $0 shape checks |
| `v4_dev_answers.py` | COPY of `v3_p8_dryrun.py` (the asking driver) | v4 guard and questions; store = `ChainStore(v4 store, v3 store read-only)`, so **only changed questions' new keys are asked**; `--count-only` gives the call count for the request; dev side only (no hold-out mode at all) |
| `v4_dev_check.py` | COPY of `v3_p12_offline.py` | dev side only; pass marks of overview §10 (tiny blocks ≤ 1.5 × the judge stand-in on the same checks, unclear ≤ 2 % of calls, 0 two-key disagreements, 0 state errors, 100 % of block messages name a fixable line), read by pattern |
| `v4_offline_eval.py` | COPY of `v3_offline_eval.py` | p11-style $0 run on the dev data with the judge stand-in for meaning; **the K2 code lines now run for real**, so this already measures their strictness at $0; the decision audit by outcome included |
| `v4_message_check.py` | COPY of `v3_message_check.py` | targets `feedback_v4`; the 8 v3 checks plus: every missing line names a value the agent can state in one turn; no expected value before login or of another user |

**Shared and untouched:** `v3_harm_metric.py` (its rules view is not part of v4's claims), `v3_labels.py`,
`v3_audit.py`, `v3_p6_agreement.py`, `v3_p7_structure.py`, `v3_p12_report.py`, all other v3 scoring files.

### 1.4 `tests/` (see §2 for the list) and the independent recompute
- `tests/audit_v4_online_recompute.py`: NEW, written by a **separate agent from the pre-registration text and the
  raw lines only** (never from `v4_online_metrics.py`): main claim, S1, S2, harm (outcome view, paired), LLM calls,
  blocks per write, for B2p, B3p and H. v3's `audit_v3_*recompute.py` may be read as a format example only.

### 1.5 `scripts/` (new folder `predicate_correctness/scripts/`)

**Copies of the old session scripts** (they still exist in
`/tmp/claude-1000/-home-azureuser-code-projects/dbfe7ffd-ee14-4b6f-ab52-d79bdd15e981/scratchpad/`; a temp folder can
vanish). Copy **byte-identical** into `scripts/v3_session/` plus `scripts/v3_session/SOURCES.sha256` (sha256 and
original path of each):
`b2_finish.sh`, `b2_auto.sh`, `b3_finish.sh`, `b3_interim.sh`, `run_v3_tests_parallel.sh`, `run_tests.sh`,
`merge_overlays.py`, `b2_dry/compare.py`, `b3/tools/identity_check.sh`, `ov_sha.py`, `hash_table.py`,
`blocksum.py`, `run_runner_tests.py`, `verify.py`, `verify2.py`, `scripts/tiny_fail_probe.py`, `tqa_build.py`,
`tqa_dump.py`, `tqa_k2lines.py`, `tqa_tab.py`. (Optional, older: `dry_all.sh` in session `7c3c1535…`.)
**Do not run** `tqa_*.py`, `blocksum.py` or `b3_*` during the v4 build: they read B2/B3 conversations (purity).
They hard-code pids, run ids and paths; the v4 scripts below are the generic versions.

**New v4 scripts** (each writes only to `output/logs/` and the run folder; nothing to the terminal):
| script | from | what it does |
|---|---|---|
| `run_tests_parallel.sh [globs]` | `run_v3_tests_parallel.sh` | every test module in its own process, 8 at a time, timeout 3000 s; default globs `tests/test_v4_*.py tests/test_v3_*.py tests/test_v4_no_gold_import.py`; logs `output/logs/v4_ptests_<UTC>/`; `summary.txt`, `totals.txt`; exit 1 if any module fails |
| `v4_after_run.sh <run_dir>` | `b2_finish.sh` + `b3_finish.sh` | the after-run chain (below) |
| `v4_progress_tick.sh <run_dir> <n_lines>` | `b2_auto.sh` | every 10 min one `- auto: HH:MM UTC <step>: N of M lines, error lines E, step spend $S` line in `docs/planning/tracker_v4/progress.md`; stops when no pid of `pids.txt` is alive (`kill -0` by explicit pid, never `pgrep -f`) |
| `v4_interim.sh <run_dir> <half>` | `b3_interim.sh` | waits for `half` lines in complete groups, runs `v4_online_interim --write-stop`, writes a progress line |
| `v4_compare_recompute.py <metrics> <recompute>` | `b2_dry/compare.py` | every point estimate and count; exit 1 and a `MISMATCH` progress line if any differs by > 1e-9 |
| `v4_dry_all.sh <step>` | v3's dry-run pattern | sandbox dry run of every shard of a step; asserts 0 calls, 0 network attempts |
| `v4_identity_check.sh` | `b3/tools/identity_check.sh` | none / direct / tgr_frozen arms of the v4 runner give byte-equal records and judge-cache records to the v3 runner on the fake-LLM sandbox |
| `v4_merge_overlays.py` | `merge_overlays.py` | §0.3 |

**The after-run chain** (`v4_after_run.sh`, started by the main chat right after it launches a step):
wait for the pids → line, error and dropped-group counts → `freeze_v4 --check` → `v4_online_metrics run` →
`audit_v4_online_recompute.py` → `v4_compare_recompute.py` (MISMATCH stops the chain's "done" line) →
`v4_diagnosis.py` → `v4_report.py` (B1: `v4_b1_summary.py`) → progress and implementation-log lines → `freeze_v4
--table`. Analysis Python: `/home/azureuser/miniconda3/bin/python3 -B`; runner Python: `~/venvs/tau-bench/bin/python
-B`; always `PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0`.

### 1.6 Docs and outputs
- `docs/planning/tracker_v4/preregistration.md` (claims, pass marks, stops, harm, diagnosis classes, change log with
  "result seen?"), `reading_guide.md` (every cell, overview §7), `approval_request.md` (dev check; then B1 → B2p +
  B3p + H, each with its limit), `predicate_table.md` (separate deliverable).
- `output/eval_v4/`: `overlays/`, `cases/`, `dev/`, `v4_freeze.sha256`, `v4_freeze.md`, `questions_answers_v4.jsonl`
  (dev and cases answers only), `B1/ B2p/ B3p/ H/ R20/<run_id>/`, `dryrun/`.

---

## 2. Tests

**New** (each owned by the agent that owns the code; all in the parallel runner):
| test file | what it pins |
|---|---|
| `test_v4_v3_untouched.py` | every file of `v3_freeze.md` has its recorded sha; `V3.check_frozen_v3()` passes; `frozen.check_manifest()` passes; no file under `output/eval_v3/` newer than the v3 handover |
| `test_v4_freeze.py` | write / check / table on a temp copy; planted changed byte, missing file, new file; the guard refuses `require_freeze=True` without a passing manifest |
| `test_v4_facts.py` | both v4 fact files validate with 0 problems; same fact names as the rule set; every fact **not** in the §1.1 list equals its v3 entry byte for byte (canonical JSON); no v4 expression calls a v3 question helper |
| `test_v4_listing.py` | every accepted and dropped form of the K2 table; the window edges (detail one message earlier counts; detail before the last worked write does not; the user's own words count); "black vs silver"; missing records with expected values |
| `test_v4_go_ahead.py` | K1 v4: fast path yes / not-yes (`?`, but, wait); a batch go-ahead covers each listed action; all user messages after L; clash; strict no; K17 insurance |
| `test_v4_code_facts.py` | ownership (another user's payment method / order; reply names another DB user; a public name does not count), K11 by event, K15 airports by code and city, trip fit, K12 kind from DB and amounts from every `$` |
| `test_v4_questions.py` | doc check, versions, `text_sha256`; **unchanged K4 / K10 / K12 keys and prompts equal v3's**; changed keys differ; few-shot render; second wording; quote pieces at any punctuation; `missing` parsing; re-derived saved status; ask log with `where`; threads (port of the v3 thread tests); v3 exception classes |
| `test_v4_unclear.py` | write check: unclear → re-ask → block; K4 / K13 / K16: unclear → re-ask → allow + log; an unclear part does not hide the other OR branch (L2.4) |
| `test_v4_guard.py` | build, lazy questions, `rec["v3"]` + `rec["v4"]`; **escape**: fires after 2 tiny blocks on one write key, not after 2 database-only blocks, not after the write ran, not across episodes or threads |
| `test_v4_feedback.py` | missing line + expected value; hidden before login; another user's value hidden; port of the 8 v3 message tests |
| `test_v4_direct_facts.py` | "NO (…)" wording; only circuit facts; prompt byte-equal to Direct with no fact; v4 fact file |
| `test_v4_run_online.py` | arms; steps and their profiles (nano only for H); run ids; tasks and shas; shards cover every unit once; store, ask log, `where`; soft stop root and limits (v3 spend not counted); sandbox and dry run make 0 calls; no `tgr_tracker_v3` arm |
| `test_v4_online_metrics.py` | port of the bootstrap / pairing / complete-group tests; harm outcome view on fixtures (early-ended conversation, refusal task); paired harm verdicts; LLM calls; blocks per write on a fixture with known counts; by-writes groups; B3p / H never pooled; test group refused |
| `test_v4_interim.py`, `test_v4_report.py`, `test_v4_diagnosis.py`, `test_v4_cases.py`, `test_v4_no_gold_import.py` | as named |

**Adapted** (copied from the v3 test, then edited): `test_v3_questions` → `test_v4_questions`; `test_v3_guard` →
`test_v4_guard`; `test_v3_feedback` → `test_v4_feedback`; `test_v3_direct_facts` → `test_v4_direct_facts`;
`test_v3_run_online` + the runner parts of `test_v3_b3` → `test_v4_run_online`; `test_v3_online_metrics` + the
metrics parts of `test_v3_b3` → `test_v4_online_metrics`; `test_v3_p14_report` → `test_v4_report`.

**Run unchanged as regression:** all 20 `test_v3_*.py` (they prove that importing v4 next to v3 breaks nothing),
incl. `test_v3_soft_stop.py` and `test_v3_frozen.py` (shared modules).

**The parallel runner:** `scripts/run_tests_parallel.sh` (§1.5). v3's suite took 9.5 min in one process; the
parallel runner fixed that (its time was not logged). v4 + v3 together: a few minutes (estimate; the slowest
module sets the time).

---

## 3. Which v3 $0 checks run again for v4

| v3 check | for v4 | why |
|---|---|---|
| Gate 0 (rebuild every saved old-guard decision) | **no** | frozen TGR code, rules and data are byte-identical (manifest + `test_v4_v3_untouched`). Replaced by `v4_identity_check.sh` (the 3 unchanged arms are byte-equal to the v3 runner on fake LLMs) |
| p2 rule table, p3 tool labels | no | unchanged, sha-checked |
| p4 decision audit | yes, inside `v4_offline_eval.py` on dev data | the new code facts can make new wrong blocks |
| p6 code vs tool agreement | **only the new database / event parts** (ownership, trip fit, K12 kind) | the rest is unchanged code |
| p7 blind screen sets | no | v4 adds no word screen; made-up cases test the questions instead |
| p8 dry run (fake answers, call counts) | yes: `v4_dev_answers.py --count-only` | the call count and limit of the dev-check request |
| p9 guard run, p11 offline (judge stand-in) | yes: `v4_offline_eval.py`, 8 workers | code paths; K2 code strictness for $0 |
| p10 message checks | yes: `v4_message_check.py` (+ the 2 new marks) | messages changed |
| p12a dev check, real answers | yes, **changed questions only**, on the same 200 dev conversations (P2) | unchanged K4 / K10 / K12 keys are read from v3's store |
| p12b hold-out | **no** | overview: v3's hold-out is not opened again |
| p13 audits A / B / C + fix + verify | yes, once, at the end of P1 | metrics vs pre-reg; runner and money; arm fairness |
| shard dry runs (0 calls), B1 check, independent recompute | yes | as v3 |

---

## 4. Parts, agents, times, money

Times are wall clock, many agents at once, no API pause. Each agent owns the files named; nobody else edits them.

| part | what | agents (owned files) | time | stop |
|---|---|---|---|---|
| **P1a build** | all code, docs and case sets at once | **A1** `listing_v4.py`, `v4_form_check.py`, `test_v4_listing.py`, fact overlay for listing parts · **A2** `helpers_v4.py` (go-ahead part), `test_v4_go_ahead.py`, K1 / K17 overlays · **A3** `questions_v4.py`, `test_v4_questions.py`, `test_v4_unclear.py` (critical: start first; publishes its helper signatures in 10 min) · **A4** question-text overlay (K3, K6, K7, K8, K10, K12, K13, K16, K17 texts, second wordings, few-shot made up from the v1 policy) · **A5** `helpers_v4.py` (ownership, K15, K12 kind part), overlays for K4 / K5 / K8 / K11 / K13 / K14 / K15 / K16 facts, `test_v4_code_facts.py` · **A6** `tgr_tracker_v4.py`, `test_v4_guard.py` · **A7** `feedback_v4.py`, `v4_message_check.py`, `test_v4_feedback.py` · **A8** `direct_facts_v4.py`, its test · **A9** `run_online_v4.py`, `v4_dry_all.sh`, `v4_identity_check.sh`, `test_v4_run_online.py` · **A10** `v4_online_metrics.py`, `v4_online_interim.py`, `v4_report.py`, `v4_b1_summary.py`, `v4_diagnosis.py`, their tests · **A11** `freeze_v4.py`, all other `scripts/`, the v3-session copies, `test_v4_freeze.py`, `test_v4_v3_untouched.py`, `test_v4_no_gold_import.py` · **A12** `preregistration.md`, `reading_guide.md`, `approval_request.md` · **A13** `audit_v4_online_recompute.py` (from A12's text only) · **A14, A15** blind case writers (`cases/*.jsonl`; they never see questions_v4's few-shot) · **A16** `v4_dev_answers.py`, `v4_dev_check.py`, `v4_offline_eval.py`, `v4_cases.py` | **75-90 min** (A3 → A2 / A5 / A6 is the critical chain) | — |
| **P1b integrate + check** | main chat merges overlays; parallel tests; `v4_offline_eval` + message check ($0, 8 workers); dev call count; dry runs of every shard (0 calls); identity check; 3 audits (A metrics vs pre-reg, B runner and money, C arm fairness) → 1 fixer → 1 verifier | main chat + 5 | **35-45 min** | — |
| **P2 dev check** (paid) | real answers on the made-up cases → changed keys on the 200 dev conversations → pass marks → at most one fix round (definitions only) and a re-ask of changed keys | main chat runs; 2 readers by pattern | **25-35 min** | STOP 2 (approve with the plan, conditional on P1b) |
| **P3 freeze + B1** (paid) | `freeze_v4 --write`, `--table`, pre-reg sha; B1 10 conversations; `b1-check` | main chat | **15 min** | STOP 3 (one request: B1 → B2p + B3p + H) |
| **P4 live** (paid) | B2p 4 shards, B3p 1 shard, H 1 shard at once (6 processes × 8 workers); `v4_progress_tick.sh`, `v4_interim.sh`, `v4_after_run.sh` per step | main chat launches | **~1.5 h** (B3p on 1 shard is the long pole: v3 did 0.45 conversations / min / worker on B3 → 320 in ~90 min; B2p ~60 min, H ~80 min) | — |
| **P5 after run** | the chain ran by itself; read the numbers; report written once; KR §1 short lines | 2 | **20-30 min** | — |

**Total: about 4-4.5 h** plus the approval waits (overview says 3-3.5 h; the gap is P1b audits and B3p on one
shard). Faster: give B3p and H 2 shards each (8 processes; v3 said "at most 4 heavy processes" on this VM, so test
the load in the dry run first), and skip the fix round if P2 passes.

**Paid steps, cost from v3's measured numbers** (logged list price; the real bill is about 0.55×):
| step | size | estimate | basis | limit |
|---|---|---|---|---|
| made-up cases | ~12 questions × 60 cases, + second wordings, up to 2 rounds ≈ 1,500 calls | $0.05-0.10 | $0.000046 per call (p12a), +25 % for few-shot | inside the dev $2 |
| dev check | ~1,200-2,000 new keys on 200 dev conversations, + one re-ask round | $0.08-0.20 | p12a 2,726 calls $0.1253; re-asks $0.0687, $0.0053 | dev $2 |
| B1 smoke | 10 conversations | $0.15 | v3 B1 $0.1486 | $2 |
| B2p | 1,485 conversations | $15-17 | v3 B2 $15.76 ($0.0106 / conversation) | $40 |
| B3p | 320 conversations | $6.5-8 | v3 B3 $0.0214 / conversation (245 ran) | $20 |
| H (weak agent) | 495 conversations | $3-6 (**not measured**: nano agent, luna user and guards; pin it at $0 from eval v2's nano lines before the request) | — | $15 |
| R20 (optional) | 100 conversations | ~$1 | B2 mean | needs its own limit; the cap $80 leaves $1 |
| **total** | | **about $26-31** | | cap $80 |

---

## 5. The riskiest code changes

1. **K2 as code** (`listing_v4.py`). Too strict again if a real form is missing (cards, addresses, short option
   values); too loose if a stray number or word counts as a match. A wrong "listed" is a new allow only together
   with K1's go-ahead (two keys), but it is the biggest behaviour change. Guard: the form check on v1 data, the
   window-edge tests, made-up listing cases, and the $0 stand-in run on dev data before any money.
2. **The K1 rebuild**: the short-yes fast path (no LLM) and "all user messages after the listing" can turn a yes to
   something else into an allow. Guard: the clash check, the strict-no rule, `?` / but / wait exclusions, and the
   batch cases in the made-up set.
3. **The shared helper registry and exceptions**: a v4 name equal to a v3 name raises at import; a new exception
   class turns a budget or network stop into a silent block; a helper that skips `hook.ask` breaks the lazy probe;
   a `doc` fallback to v3 asks the wrong question. Guard: the `_v4` naming rule, `test_v4_questions` (exception
   identity), `test_v4_guard` (probe and lazy counts).
4. **The transfer escape**: it needs a per-conversation block memory on the TGR `Conversation` (a plain dataclass,
   so the attribute works), must survive `TGR.step` retries and cap overrides, and must be rebuilt by the offline
   driver. It creates new allows on transfers, so it is counted and shown next to harm.
5. **Missing lines in block messages**: they print expected values (card ids, last four, zip, item options). A
   value before login or of another user is a data leak. Guard: the feedback safety rule on every missing value,
   and the 2 new message checks.
6. **The runner copy**: 5 steps with different profiles (nano only for H), 6 processes at once, a new spend root
   and cap, and `where` on every tiny answer. Guard: `test_v4_run_online`, 0-call dry runs of every shard, the
   identity check of the 3 unchanged arms, and audit B.
7. **Answer reuse for unchanged questions**: v3 answers may be reused only if the v4 key and prompt equal v3's byte
   for byte (system v1, same text). If that gets fiddly, use system v2 for all questions and re-ask everything on
   dev (about $0.03 more); the dev check still reads only changed behaviour.

---

## 6. Open decisions for the main chat (defaults in brackets)
1. Direct + facts arm: `direct_facts_v4` with the wording fix and the v4 fact file, as overview §5 [yes]; or keep
   `direct_facts_v3` for an exact repeat of v3's 4 other arms.
2. K4's code precondition at login (`other_person_precondition_v4`): write it in `predicate_table.md` [the lookup
   values were not typed by the user, or the user message names a relation (wife, friend, ...) tested on made-up
   cases].
3. **Decided 2026-10-24: R20 / DEV20v4 dropped** (the build read the dev 20 tasks; see `preregistration_v4.md`
   change log). Old text: R20 side check: only if `v4_form_check.py` finds the 20 retail dev tasks unused; needs its own limit and $1-3 more
   cap [decide after the $0 check].
4. B3p and H shards: 1 each (6 processes, ~1.5 h) [yes], or 2 each (8 processes, ~1 h) after a load test.
5. H halfway stop: none on success; health and cost stops only [yes].

**Rule slip in this planning step (honest note):** to read two JSON files I ran three short `python3 -c` reads
(output to `output/logs/v4_cm_questions.txt` and `v4_cm_facts.txt`), against "no running code". They only read
files; nothing was written except those logs and this file.
