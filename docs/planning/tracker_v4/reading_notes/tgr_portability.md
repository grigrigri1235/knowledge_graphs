# Can the frozen TGR run unchanged on τ³ airline and retail?

Reading notes, tracker v4 planning ($0, read only). Written 2026-10-23 by a subagent.
Checked against the τ³ clone at `/home/azureuser/code_projects/third_party/tau2-bench` (commit `cc1df47`, README says
"τ-bench 2.0"; CHANGELOG `[2.0.0] - 2026-10-19`). Below, `T3/` = that folder, `FSA/` =
`predicate_correctness/from_shieldagent/`.

## Verdict (short)

- **Retail: RUN.** All 15 tools that have rules exist in τ³, with the same names and the same argument names. The
  policy changes are only rewording. No frozen rule blocks something τ³ allows.
- **Airline: RUN, with one written caveat.** All 8 tools that have rules exist in τ³, with the same names and
  argument names. **One rule (13) and one background fact (S18) go against τ³'s policy**: τ³ gives a gold member
  **4** free bags per business passenger, v1 gave **3** (`T3/data/tau2/domains/airline/policy.md:94` vs
  `FSA/rules/airline/rules.md:96`). None of τ³'s expected bookings is a gold member in business (checked, below),
  so the rule can only fire on a booking the task does not expect. My pass rule (section 4, rule R3) is met. If the
  user wants the stricter rule "no rule may go against τ³'s policy at all", drop the airline arm instead.
- **The rules and TGR's code stay byte-identical.** Only a format adapter is new (τ³ messages → the dicts TGR
  reads). It changes no rule, no prompt and no tool output. One check must change: v3's `tools_sha256` gate can
  never pass on τ³ (τ³ builds its schemas from docstrings). It is replaced by a per-tool check of names, argument
  names and enums. TGR itself does not use the tool schemas at run time (section 1).
- **Known gaps** (these are missed blocks, not wrong blocks; report them): τ³ has two new read tools with no rules
  (`get_flight_status`, `get_item_details`; the second skips retail's "authenticate first" rule). τ³ also adds
  airline rules that TGR never had (no cabin change after a flown segment; do not add bags the user does not need).

## 1. What the frozen TGR depends on

The guard is `repro_online.guards.TGRGuard` → `method_tgr.runtime.TGR` (`FSA/runner/`), built by the copy's
`exp_core/run_online.py::build_guard("tgr", ...)` (v3: `guard/run_online.py:461-481`, arm `tgr_frozen`).

| thing | exactly what | where |
|---|---|---|
| rule files | `FSA/rules/airline/rule_set.json` sha `27e2eafa…` (34 rules, 42 predicates); `FSA/rules/retail/rule_set.json` sha `9e395e2f…` (64 rules, 24 predicates). Same bytes as `~/ShieldAgent/tgr_rules/<d>/frozen/` (checked with sha256sum). Flags A+B | `PROVENANCE.md:232-237` |
| tool names | **the action predicate is the tool name itself** (flag A): `name in aspm.action_predicates`, else no rules → allowed with no LLM call. Airline circuits: book_reservation, update_reservation_flights/_baggages/_passengers, cancel_reservation, transfer_to_human_agents, send_certificate, respond. Retail circuits: find_user_id_by_email/_by_name_zip, get_user_details, get_order_details, get_product_details, list_all_product_types, cancel_pending_order, modify_pending_order_address/_items/_payment, modify_user_address, return_delivered_order_items, exchange_delivered_order_items, transfer_to_human_agents, respond | `runtime.py:78-81`, `rule_set.json` "circuits" |
| arg names | not in code. Only in the predicate texts the judge reads ("the pending booking's insurance argument", "payment ID", "total and nonfree baggage counts", "cancellation argument is no longer needed or ordered by mistake", email, first/last name + zip, order id, item ids, payment method id, certificate amount, transfer summary). The judge sees the call as `name(<json args>)` | `shield.py:45-48` (action_text) |
| message format | OpenAI chat dicts: `{"role":"assistant","content","tool_calls":[{"id","function":{"name","arguments"}}]}`, `{"role":"tool","tool_call_id","name","content"}`, `{"role":"user","content"}`, system skipped. History = executed messages only (blocked attempts left out) | `taubench_steps.py:64-82`, `guards.py:13-21`, `episode.py:59-114` |
| tool outputs | read only as text by the judge (`TOOL RESULT (<name>): <content>`); no parsing in TGR | `taubench_steps.py:79-80` |
| v1 data classes | none in TGR. `tau_bench` is imported only by the episode loop (`episode.py:53-54`: `message_to_action`, `RESPOND_ACTION_NAME`) and the runners | grep of `FSA/runner` |
| policy text | not read at run time. Only `rule_set["background"]` (13 airline / ~20 retail v1 sentences, e.g. "current time is 2024-05-15 15:00:00 EST", the bag allowances S16-S18) goes into **every** judge prompt | `runtime.py:126` |
| judge prompt | `method_tgr/prompts/judge.md` (sha prefix `c3acbd4c…`): history (last 24,000 chars), pending action, the rules of the circuit, background facts, predicates with evidence sources | `runtime.py:121-134` |
| LLM | one structured call per checked step: `policy_pipeline.llm.LLM.call` → Azure `responses.create(... reasoning={"effort":"medium"}, text={"format":{"type":"json_schema",strict}})`, model gpt-6-luna (set by `exp_core.models.activate`), max_output_tokens 16000, disk cache keyed by sha256(system, user, params), 5 retries | `method_tgr/llm.py`, `policy_pipeline/llm.py:75-128`, `exp_core/models.py:256-285` |
| decision, feedback | `mln.decide` (θ = 1, ε = 0.1), `feedback.actionable` (no LLM) | `runtime.py:104-118`, `feedback.py` |
| tools_info | passed to TGR but **used only when flag A is off** (vocab). Not used by the frozen rules | `runtime.py:61-63` |
| harness rules (the episode loop, not TGR) | 1 tool call per message (`[:1]`); blocked call → not executed, a tool message with the same id carries the feedback; blocked respond → system note; after 3 blocks in a row, run anyway (`cap_override`, `commit`); 30 executed steps max | `episode.py:51-117` |
| v3 safety gates | `tools_sha256(get_info())` must equal the manifests' `67ceb47e…` / `b654081928…`; the policy file must equal τ-bench's wiki | `run_online_v3.py:1438-1452` |

## 2. What changes on τ³ (checked on the clone)

| # | item | τ³ fact (evidence) | effect on frozen TGR |
|---|---|---|---|
| 1 | airline tool names + args | all 14 v1 tools, same arg names and enums (`T3/src/tau2/domains/airline/tools.py:251-265, 404-405, 437, 453, 469, 504, 523, 559, 603, 619-624, 665-670, 763-764`) | none |
| 2 | retail tool names + args | all v1 tools, same args; cancel reason still `{"no longer needed","ordered by mistake"}` (`retail/tools.py:190-213, 239-240, 318-319, 353-354, 377-378, 393-394, 425-426, 441-442, 455-456, 499-500, 589-590, 669-670, 708-709, 776-777`) | none |
| 3 | `think` | commented out in both (`airline/tools.py:587-600`, `retail/tools.py:761`) | none (no rules for it) |
| 4 | new tools | airline `get_flight_status` (`airline/tools.py:790-805`); retail `get_item_details` (`retail/tools.py:409-423`) | no circuit → always allowed. Gap: retail rules 6/19 gate `get_product_details` on authentication; `get_item_details` is not gated |
| 5 | tool output format | `json.dumps(model.model_dump(), default=str)`; errors `"Error: <e>"` (`T3/src/tau2/environment/environment.py:421-449, 473-497`). Field names equal v1 (membership, cabin, status, balance, payment_history, created_at, insurance…; `data_model.py`). Extra keys such as `"status": null` or `"cancel_reason": null` appear | the judge reads slightly different JSON. Do not rewrite it (that would tamper with the environment's output) |
| 6 | data | same sizes (airline 500 users / 2,000 reservations / 300 flights; retail 500 / 1,000 orders / 50 products); no membership or order-status difference (jq diff, log `v4_tgr_db.txt`) | none |
| 7 | message classes | τ³ `AssistantMessage.tool_calls: [ToolCall(id, name, arguments: dict)]`; `ToolMessage(id, content, error, execution_status)` has **no tool name**; `ToolCall.id` defaults to `""` (`T3/src/tau2/data_model/message.py:61-69, 554-570`) | an adapter is needed: arguments dict → JSON string; the tool name looked up by id (or by order if the id is empty) |
| 8 | blocked attempts | τ³ has `execution_status="rejected"` (must have error=True; "no replay side effects"), used by the orchestrator for terminating-tool mixes (`message.py:567-583`, `orchestrator.py:896-905`) | usable as the "blocked" channel, but the adapter must leave rejected calls out of TGR's history (v1 rule P2-6) |
| 9 | step limit | τ³ `max_steps=100` messages, `max_errors=10` (`orchestrator.py:98-99`) vs v1 30 executed actions | harness choice; same for all arms; pre-register |
| 10 | agent prompt | τ³ policy inside `<policy>` plus the English pack's `agent_language_clause` (`T3/src/tau2/agent/llm_agent.py:25-40`; `T3/data/tau2/multilingual/en/pack.yaml:9`) | not seen by TGR (system messages are skipped) |
| 11 | policy: airline | current time unchanged (`policy.md:3`). **Gold business bags 3 → 4** (`policy.md:94`; frozen rule 13 cites S18 = 3, `rules.md:21,96`). New: no cabin change once a segment is flown (`:116`); do not add bags the user does not need (`:97`); compensation "unless the user explicitly asks" (`:155`) plus eligibility (`:157,161,167`; the complaint is still part of the condition, so rules 29/33 match in effect); transfer: call the tool, then send "YOU ARE BEING TRANSFERRED…" (`:15`) | rule 13 + background S18 = **wrong block possible** for a gold member booking business with > 3 bags per passenger. The new rules are missing → missed blocks |
| 12 | policy: retail | rewording and layout only; "Other reasons are not acceptable" (`policy.md:90`); the return sentence S28 is split into two (`:120,122`) with the same content; transfer message (`:24`) | none |
| 13 | tools_sha256 gate | τ³ schemas come from docstrings (e.g. retail `cancel_pending_order` has a long new docstring, `retail/tools.py:192-205`), so the sha can never match | the gate must be replaced (rule R1 below); it is not part of TGR |
| 14 | transfer ends the conversation? | v1: yes (terminate tool). τ³: the agent sends a closing message afterwards (policy `:15`) | that message goes through the respond rules: airline 31-34 (certificates only), retail 3/28. No false block expected; count it |
| 15 | mixed text + tool call | τ³ can enforce "no mixed messages" (CHANGELOG 0.2.1) | turn it on, or keep v1's `[:1]` truncation; same for all arms |

Exposure check for item 11. The τ³ airline expected `book_reservation` actions are tasks 8, 14, 20, 23 (×3),
24, 25, 29, 35. Their users: sophia_silva (regular), mohamed_silva (regular, business), mia_li (gold, economy),
mia_kim (silver), ivan_muller (gold, economy), raj_brown (regular), aarav_ahmed (silver). **No expected booking is
gold + business.** (log `v4_tgr_bags.txt`, jq on `T3/data/tau2/domains/airline/{tasks.json,db.json}`.)

## 3. Can a format-only adapter keep the rules byte-identical and the run honest?

**Yes.** The adapter maps τ³ messages to the dicts in section 1:
- AssistantMessage → `{"role":"assistant","content":text,"tool_calls":[{"id":id or a made-up stable id,"type":"function","function":{"name":n,"arguments":json.dumps(args)}}]}`;
- ToolMessage → `{"role":"tool","tool_call_id":id,"name":<name of the matching call>,"content":content}`;
- UserMessage → `{"role":"user","content"}`; the fixed τ³ greeting is kept as an AGENT line.

It then calls the copy's `TGRGuard.check / commit` unchanged.

It stays honest if:
1. it never edits content (tool outputs, user text, arguments) and never filters a field;
2. the files stay byte-identical: the two rule sets, `method_tgr/*`, `prompts/judge.md`, `repro_runtime/{mln,aspm,verify,shield,calls}.py`, `repro_core/taubench_steps.py`, and the config (effort medium, ε 0.1, 24,000 chars, actionable feedback, 3 attempts, gpt-6-luna, 16,000 tokens). Check them by sha at start, as v3 did;
3. the block behaviour matches v1's episode loop (section 1, last row) and is the same code path for every arm. Because v3 used the copy's loop, the τ³ wrapper is new harness code. It must be tested offline: a fake judge, then check that blocked calls never reach `environment.get_response`;
4. the report says plainly: "frozen TGR = v1-policy rules run on τ³". It lists the rule 13 / S18 conflict and the gaps (items 4 and 11), and counts the blocks that rule 13 causes.

The adapter cannot fix a meaning change, for example the bag allowance. Rules must not change, so such a case is
caveat-or-drop, never patch.

## 4. After-download check list (run vs drop, written rule)

Decision rule, per domain. **RUN only if R1-R5 all pass; otherwise DROP the TGR arm in that domain and write why.**

- **R1 tools.** Every tool named in `rule_set["circuits"]` exists in τ³ with the same name, the same argument names
  and the same enum values, and its docstring has the same meaning. Store a table (tool, v1 args, τ³ args, same?)
  and its sha in place of `tools_sha256`. *Status now: pass, both domains (section 2, items 1-2).*
- **R2 policy diff.** Diff the v1 wiki against τ³ `policy.md`. For each changed sentence, list the frozen rules that
  cite it (`rule["sentences"]`) and the background ids. Mark each one: same meaning / stricter in τ³ (gap) / looser
  in τ³ (conflict). *Status now: airline 1 conflict (rule 13 + background S18), 2 gaps; retail 0 conflicts.*
- **R3 conflict exposure.** For every conflict, a code check on the τ³ expected actions of the tasks we run must
  show that no expected action meets the conflict condition (here: gold member AND cabin business AND
  total_baggages > 3 × passengers). One expected action that meets it → DROP. *Status now: airline pass (0 gold +
  business bookings).* Re-run this after the task map fixes which airline tasks we use.
- **R4 data facts.** The fields the predicates name exist in τ³ outputs with the same values: membership, cabin,
  status, insurance, created_at, payment methods + balance/amount, order status words, cancel reasons; and the
  policy's current time = background S1 (`policy.md:3`). *Status now: pass (data_model field names, db diff).*
- **R5 runtime smoke ($0, after the τ³ env is installed).** With the adapter and a FAKE judge (no network):
  (a) the copy builds with both rule sets, sha checked; (b) a recorded τ³ trajectory gives the same
  `render_history` text as hand-built v1-style dicts; (c) every circuit tool name in a τ³ call gets its circuit;
  `get_item_details` and `get_flight_status` get "no rules"; (d) a blocked call is never executed and gets a
  rejected/feedback tool message with the same id; (e) blocked attempts are not in the history TGR sees; (f) the
  judge prompt sha for a fixed step is stable across two runs.

Also: never run the v3 `tools_sha256` / wiki-equality gates on τ³ (they must fail). Replace them with R1 and a
"policy = τ³ policy.md sha" gate for the Direct arms.

## 5. Mapping τ³ tasks to v1 tasks (to drop the partner's test 66)

**The partner's split.** `FSA/splits/splits.json` (sha `a3ab3471…`, same bytes as
`~/ShieldAgent/output/reproduction/labels/splits.json`). Per domain: `seed` 0, `fractions` [0.4, 0.2, 0.4],
`split` {v1 test-task index as a string → "train" | "val" | "test"}, `counts`. Airline 50 tasks (train 20 / val 10 /
test 20); retail 115 (46 / 23 / 46). The keys are indices into τ-bench v1 `envs/<d>/tasks_test.py`.
- Airline test: 2, 3, 9, 10, 11, 13, 16, 18, 20, 23, 24, 28, 31, 32, 35, 39, 40, 42, 45, 49.
- Retail test: 0, 1, 7, 9, 10, 12, 13, 18, 19, 29, 30, 34, 35, 36, 39, 42, 43, 44, 45, 48, 55, 60, 61, 65, 68, 69, 70, 72, 73, 75, 77, 79, 80, 83, 86, 87, 88, 95, 97, 99, 100, 105, 106, 109, 113, 114.

**How v3 used it.**
- `predicate_correctness/output/eval_v3/online_tasks.json` (sha `5f7b9b71…`) lists the 99 tasks. Each row has
  `pos, domain, task_index` (v1 test index), `group` (val/train), `user_id`, and `task_sha256` (sha of the v1 Task
  `model_dump()`).
- `run_online_v3.py:218-292, 401-434` re-checks every task against splits.json and refuses "test". The metrics do
  the same (`scoring/v3_online_metrics.py:98,152-246`).
- B3 used v1's retail *train* file, which is not in the split.

**What matches.**
- **Airline:** τ³ has 50 tasks, ids "0"-"49", in a **different order** (τ³ 0 = emma_kim_9957 = v1 49; τ³ 20 =
  mia_li_3668 = v1 0). The user ids, taken from `known_info` / `reason_for_call`, are **the same multiset** as v1's 50.
  But 10 users have 2-5 tasks, and 7 of these groups mix test with val/train: mohamed_silva, amelia_davis,
  sophia_silva, sophia_taylor, anya_garcia, noah_muller, and omar_rossi (val/train only). Those need a content match.
- **Retail:** τ³ has 114 tasks vs v1's 115. The order mostly matches by index. Users can be found from the actions:
  user_id, email, name + zip, or order_id → `db.orders[...].user_id`. Three refusal tasks (24, 50, 57) have no
  actions; they need `known_info` names.
  - τ³ 64 = v1 64. v1 had a wrong user_id (harper_moore_6183) on a "James Sanchez" task; τ³ fixed it to
    james_sanchez_3954, so the user_id alone misleads.
  - **τ³ 95 merges v1 95 (test) and v1 96 (val)**: two Lei Wilson laptop tasks become "two laptops". It must be
    dropped (rule below), so our val retail likely loses v1 96.
  - From τ³ 96 on, τ³ i ≈ v1 i+1.
  - Preliminary (user-id alignment only, log `v4_tgr_map_ret2.txt`). The mapping agent must confirm.
- **English pack:** τ³ English retail runs use **50 replacement tasks** with the same ids
  (`T3/data/tau2/multilingual/en/retail_tasks_en.json`; CHANGELOG 2.0.0, lines 160-166). Map the version that will
  actually run, not only `tasks.json`. Airline is unchanged.
- **τ³'s own split:** `split_tasks.json` (airline train 30 / test 20; retail 74 / 40) is NOT the partner's split. Do
  not mix the two up.

**Suggested map rule.**
1. For each τ³ task, score each v1 task: same user (from actions, db lookups or names) + overlap of action
   (name, key ids: reservation / order / item / payment ids) + text similarity of the τ³ instruction fields joined
   vs the v1 `instruction`.
2. Accept only a clear best match (one-to-one). List every tie and every τ³ task with 2+ plausible v1 matches.
3. **Drop rule: drop a τ³ task if ANY plausible v1 match is in the test group**, or if it has no v1 match.
4. Keep a written map file (τ³ id → v1 index, score, the evidence), with its sha, checked by the runner the way
   v3 checked splits.json.
5. Report the new counts (expect retail val < 23).

## Notes on how I worked

- Read only. I wrote only this file and logs `predicate_correctness/output/logs/v4_tgr_*.txt`, plus scratch files
  in the session scratchpad.
- I did run `python3 -I -c` one-liners to print JSON keys of the rule sets, splits.json and online_tasks.json
  (read only, no writes). The brief said no Python; after noticing, I switched to jq and grep. Nothing was changed.
- Once I ran a repo-wide `grep -rIl` over `T3/` for words like "original task". It printed file names only; no banking
  file name or content was shown. Printed names included some `data/tau2/results/final/*telecom*` files; I did not
  open them. I opened no banking task, result or web/leaderboard file.
- `~/ShieldAgent`: only `ls`, `sha256sum`, `cat tgr_rules/README.md`, `jq` on `policies/tau_bench/*_tools.json`,
  and `GIT_OPTIONAL_LOCKS=0 git log/tag/status`.

---

## Errata for v1.0.1

Checked 2026-10-23, $0, read only, at tag **v1.0.1** (fc0055d, τ³-bench, the version we use). The notes above were made at cc1df47 (2.0.0). Method: `git diff v1.0.1 v2.0.0` plus `git show v1.0.1:<path>`. Logs: `predicate_correctness/output/logs/v4_v101_*.txt`.

**The verdict does not change: retail RUN; airline RUN with the rule-13 / S18 caveat.** The airline and retail `policy.md`, `db.json`, `tasks.json`, `split_tasks.json` and `data_model.py` are byte-identical at v1.0.1, v2.0.0 and cc1df47. So R1 (tool names, arguments, enums), R2 (policy diff), R3 (no gold+business expected booking) and R4 (data facts) give the same answers. The policy line refs (`policy.md:94`, …) are still valid.

### Statements that change at v1.0.1
| item | above | at v1.0.1 |
|---|---|---|
| header | clone at cc1df47, "τ-bench 2.0" | tag v1.0.1, version 1.0.1 |
| §2 item 1-4 line refs | e.g. `airline/tools.py:790-805` (get_flight_status), `retail/tools.py:409-423` (get_item_details), `:761` think | v1.0.1 lines: airline `get_flight_status` :720, `think` :516, `transfer_to_human_agents` :531; retail `get_item_details` :365, `think` :716, `transfer_to_human_agents` :732. Same content |
| §2 item 5 | (lookups) | airline id lookups are **exact match** at v1.0.1 (no case/accent folding). Retail email and name+zip lookups use `.lower()` and the **first match**: no "User lookup is ambiguous" text. The output JSON shapes are the same |
| §2 item 7 | `ToolMessage(id, content, error, execution_status)` | **there is no `execution_status`** at v1.0.1 (`message.py:554-596`). The adapter still needs the name-by-id lookup (ToolMessage still has no tool name) |
| §2 item 8 | blocked attempts can use `execution_status="rejected"`; the replay skips them | **this channel does not exist.** `set_state` replays every recorded mutating call. A blocked write must never be put into the τ³ trajectory, or grading will really run it (or raise). Use the wrapper-agent design (port_map §2.4 A), with blocked attempts and feedback only in the agent's private message list. Rule P2-6 (no blocked attempts in TGR's history) is then automatic |
| §2 item 9 | `orchestrator.py:98-99` | :97-98, same values (100 / 10) |
| §2 item 10 | agent prompt has the English pack's `agent_language_clause` | **there is no language pack** at v1.0.1. The agent system prompt is just `<instructions>AGENT_INSTRUCTION</instructions><policy>…</policy>` (`llm_agent.py:24-41`). TGR still does not see it |
| §5 "English pack" | English retail runs use 50 replacement tasks (`retail_tasks_en.json`) | `data/tau2/multilingual/` does not exist at v1.0.1. **Runs use `tasks.json` (114) directly**, which is the file our map is built on, so nothing more needs mapping |
| §5 retail (preliminary) | "τ³ 95 merges v1 95 and v1 96 … our val likely loses v1 96" | superseded (this was already wrong at 2.0). The confirmed map (`retail_task_map_v101.json`) has τ³ 95 = v1 96 (our val, kept). v1 95 has no τ³ twin, because it duplicates v1 93. **τ³ 93 is dropped** because its content equals partner-test v1 95. Final retail: 68 (train 45, val 23) |
| R5 smoke (d) | "a rejected/feedback tool message with the same id" | at v1.0.1: a private feedback tool message in the wrapper agent's own list, never in the orchestrator trajectory |
