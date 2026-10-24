# How the partner's TGR builds its rules (and how to re-run it on τ³)

Reading notes, tracker v4 planning ($0, read only). Written 2026-10-23 by a subagent.
`SA/` = `~/ShieldAgent` (working tree = git tag `tgr-frozen-v1` for every method file: `git diff --stat tgr-frozen-v1`
on `method_tgr exp_core tgr_rules policy_pipeline/llm.py` is empty; prompt-file hashes now equal the frozen manifests'
`prompt_hashes`). `FSA/` = `predicate_correctness/from_shieldagent/` (our copy; `FSA/rules/*` = `SA/tgr_rules/*/frozen/*`
by sha256). `T3/` = `third_party/tau2-bench` **at tag v1.0.1, commit `fc0055d`** (re-checked after the switch; the
airline/retail `policy.md` shas are the same as in v2.0.0). Logs: `predicate_correctness/output/logs/v4_tgrb_*.txt`.

**Purity note.** I opened no banking task, result, leaderboard or CHANGELOG file. Before the coordinator's message I
had opened the old banking reading note (since deleted). Nothing in this file uses it: every banking number in §4.2
was measured again by me on v1.0.1 from the prompt files, the KB documents and the tool code only. I ran no Python and
no build, made no network or LLM calls, and wrote nothing under `~/ShieldAgent`, `~/opt` or `~/venvs`. I used only
read-only git there (`GIT_OPTIONAL_LOCKS=0`).

## 0. Main idea in plain words

- TGR's rule build is **one LLM call per domain**. The model reads the policy text and the tool list, and writes all
  the rules, all the facts (predicates) and a label for every policy sentence, in one JSON answer.
- Code then checks the answer. If something is wrong, the same model gets up to **2 repair calls**. Rules that are
  still broken are dropped. Exact duplicates are dropped. Rules are grouped by tool. **No human edits anything.**
- Inputs are only: the policy (with its "Domain Basic" section cut out) and the tool schemas. **No task, no
  conversation, no gold label goes into the build.**
- But the **prompts** were tuned in 5 rounds by watching TGR run on the v1 **train** tasks (and their gold scores).
  So the method has "seen" v1 train behaviour. It never saw val/test before freezing, and it never saw banking.
- Cost was about **1-2 cents per domain**. A re-run on new policy text is a **new random sample**: no temperature,
  no seed. Only the disk cache makes a re-run repeat itself.
- The build is made for a **small** policy (about 5 kB). It cannot take the banking knowledge base in one call.

## 1. The build pipeline, step by step

### 1.1 Entry point and inputs
| step | what | where |
|---|---|---|
| CLI | `python -m exp_core.tgr_build --profile luna-dev --env <d> --run-id <r> [--effort high] [--no-a] [--no-b] [--timeout 1800]` | `SA/exp_core/tgr_build.py:9, 61-70`; wrapper `SA/output/tgr/phase2/build.sh:5-8` (venv `~/venvs/tau-bench/bin/python`, both domains in a row) |
| input 1: policy | `output/tgr/policy_input/<env>_wiki.rulebuild.txt` = v1 `policy_docs/<d>_wiki.txt` (byte-equal to τ-bench v1 `wiki.md`, `SA/AGENTS.md:16`) with the "Domain Basic" section cut out | `tgr_build.py:77-79`; filter `SA/exp_core/policy_filter.py:26-47`; decision `SA/docs/tgr/plan.md:11-12`, `known_limitations.md` L1 (advisors' decision) |
| filter details | drops a Markdown heading + everything to the next heading of the same or higher level; case-insensitive heading match; heading list comes from the caller; **fails if the heading is missing** (`SystemExit`); writes `.filter.json` with in/out sha256 and the removed text. Airline removed 753 of 6,155 chars, retail 978 of 5,718 | `policy_filter.py:19-47, 62-71`; `SA/output/tgr/policy_input/*.filter.json` |
| input 2: tools | `env.tools_info` of τ-bench v1 (`get_env(env, user_strategy="human", user_model="none", task_split="test", task_index=0)`): the agent's own OpenAI-style tool schemas. This loads a v1 env object, but only `tools_info` is used | `tgr_build.py:28-32, 80` |
| no gold / no tasks | docstring "Never a gold file"; `method_tgr` is in the `NoGoldLeakage` and domain-agnostic test lists | `tgr_build.py:3-4`; `SA/AGENTS.md:9`; `SA/docs/tgr/phase2_design.md:3-5, 10-11` |
| model routing | profile `luna-dev`, role `rulebuild` → `gpt-6-luna` (Azure AI Foundry, managed identity, `utility/utils.py`) | `tgr_build.py:71-75`; `SA/exp_core/model_profiles.json:4-9`; `SA/exp_core/models.py:81-110` |

### 1.2 Preparing the prompt
1. **Sentence numbering.** Every non-heading line is split into sentences, and each one gets an id `[S<n>]`. Headings
   stay unnumbered (they are context). Bullets are kept. The split rule is `(?<=[.!?])\s+(?=[A-Z"“(])`. So each bullet
   line is at least one sentence. → airline v1 46 sentences, retail 38. (`SA/method_tgr/policy_text.py:7-33`)
2. **Tool list.** One line per tool: `- name(arg: description, ...): description`, plus `- respond(content): send a
   message to the user.` (`SA/method_tgr/rules.py:66-74`)
3. **User prompt** = `prompts/rules_user.md` filled with: the numbered policy; `actions_tools.md` (+ `Set "actions" to
   an empty list.`); `form_restriction.md`; `scope.md`; `predicates_grounded.md`; `dispositions.md`;
   `example_restriction.md` (a made-up library domain). **System prompt** = `prompts/rules_system.md`.
   (`rules.py:86-96`; prompt files `SA/method_tgr/prompts/*.md`; the fill function is `prompts.py:17-20`)

### 1.3 The LLM calls
| call | prompt | model / effort | output format | budget | count |
|---|---|---|---|---|---|
| rule writing (`stage="tgr_rules"`) | `rules_system.md` + filled `rules_user.md` | gpt-6-luna; CLI default effort `medium` (`tgr_build.py:68`), **all final builds used `high`** (manifests `"effort": "high"`; reason in `phase2_log.md:126-127`) | strict JSON schema `rule_set` (`rules.py:41-63`): `actions`, `predicates` [{name, description, source ∈ call_arguments/tool_outputs/user_messages/agent_messages}], `rules` [{id, action, condition, description, sentences}], `dispositions` [{sentence, disposition ∈ rule/exception/fact/not_enforceable, rule_ids, reason}], `background_sentences` [ids] | `max_output_tokens=32000` (`rules.py:204`), request timeout 1,800 s (`tgr_build.py:69, 75`) | exactly 1 (`rules.py:210-211`) |
| repair (`stage="tgr_repair"`) | `prompts/repair.md`: the validator's error list + the instruction parts (`instructions()`, `rules.py:77-83`) + the full rule JSON; "change only what is needed" | same | same schema | same | 0-2 (`max_repairs=2`, `rules.py:203, 214-224`), only while errors remain |

- **Temperature / seed: none.** gpt-6-luna rejects temperature on the Responses API, and seed is not a Responses
  parameter (`SA/docs/tgr/p0_report.md` §2 table, decision M3; `SA/policy_pipeline/llm.py:1-9`).
- **Transport.** `client.responses.create(model, input=[system, user], reasoning={"effort"}, max_output_tokens,
  text={"format": {"type": "json_schema", "strict": true}})`. Up to **5 attempts** on any exception, including a
  timeout or truncated/invalid JSON, with 2/4/8/16/32 s back-off (`SA/policy_pipeline/llm.py:90-128`).
- **Cache.** The key is sha256 of (system, user, model, effort, max_output_tokens, schema, `sample=0`). The cache lives in
  `<ROOT>/output/tgr/_llmcache/structured`. A re-run with the same inputs replays the stored answer
  (`SA/method_tgr/llm.py:31-46`; `SA/exp_core/models.py:30, 91-94`). `sample` is fixed to 0 in `method_tgr/llm.py:35`,
  so the code cannot draw a second sample of the same prompt.
- **Cost metering.** `Meter`, list price from `model_profiles.json` (`SA/repro_runtime/calls.py:43-59`;
  `models.py:104-105`). **Failed attempts are not metered** (only the successful record is read back).

### 1.4 Code steps after the call (no LLM)
| step | what | where |
|---|---|---|
| validation | each rule parses as LTLf `<action> IMPLIES (<condition>)`; the action is a tool name or `respond`; the condition has no temporal operator and no action name; every atom is declared; no duplicate rule id; predicate names are snake_case, unique, and not action names; **every sentence has exactly one disposition**; rule/exception dispositions point to existing rule ids | `rules.py:105-178` |
| repair loop | errors → repair call (≤ 2) | `rules.py:214-224` |
| drop invalid | rules still invalid after the repairs are **dropped and reported**. Global errors (for example a missing disposition) are only reported; they drop nothing | `rules.py:157, 225, 243-245`; `rules.py:9` "No rule is ever edited by hand or by code" |
| dedupe | **exact duplicates only** (same canonical LTLf); no other merging | `rules.py:181-190`; `phase2_design.md:22` |
| renumber | rule ids → "1".."n" (the runtime sorts numerically); the model's id is kept as `model_id`; dispositions are remapped | `rules.py:226-232`; decision T7 `phase2_design.md:60` |
| prune predicates | only predicates used by a kept rule stay; unused ones are listed in `validation.unused_predicates` | `rules.py:233-234, 245` |
| background facts (S-ids for the judge) | the model's `background_sentences` **plus every sentence with disposition "fact"** (under B), as {id, text} | `rules.py:237-239`; added in iteration 4 (`phase2_log.md:121-122`) |
| circuits | rules grouped by action (tool) | `rules.py:193-198` |

### 1.5 Outputs
- `output/tgr/tgr_rules/<profile>/<env>/<run_id>/` (`tgr_build.py:82-104`):
  - `rule_set.json`: what the guard loads. It holds flags, sentences, numbered policy, rules, predicates (with
    description and source), action names, circuits, dispositions, background, validation, usage and prompt hashes;
  - `raw.json`: every model answer;
  - `rules.md`: readable tables (`tgr_build.py:35-58`);
  - `manifest.json`: profile, model, effort, the policy path + sha256, the filter record, **`tools_sha256` =
    sha256(`json.dumps(tools, sort_keys=True)`)**, the prompt hashes (16-hex sha256 prefix of **every** prompt file,
    the judge's included; `prompts.py:30-36`), usage, wall seconds and counts.
- **`tools_sha256` is only recorded.** No method code checks it (grep: the only hit is `tgr_build.py:94`). Our v3
  runner used it as a safety gate (`reading_notes/tgr_portability.md` §1). It is not part of TGR.
- **`judge.md` is not a build output.** It is a fixed method prompt read at run time (`SA/method_tgr/runtime.py:121-134`).
  Its hash is only recorded in the manifest.
- **Publishing** was a manual copy into `SA/tgr_rules/<d>/{full,nob,frozen}/` (README `SA/tgr_rules/README.md:6-14`).
  Frozen = run `it5` (`SA/docs/tgr/phase2_log.md:205-207`). The copy did not edit any content: our sha256 check
  gives equal bytes.

### 1.6 Human / manual steps (complete list)
1. Choosing the heading to drop ("Domain Basic"): an advisors' decision, passed as a CLI argument (`known_limitations.md`
   L1; `p0_report.md` §4).
2. Choosing effort `high` and the 1,800 s timeout (harness settings, `phase2_log.md:126-131`).
3. **Editing the generic prompts between iterations** (section 2). No rule was ever edited.
4. Copying the final run folder to `tgr_rules/<d>/frozen/`.

## 2. Was anything tuned on train/val conversations?

**Rules: no.** There is no pruning or selection of rules by outcomes. Each published set is the single build of the
final prompt state: "There was no selection among samples: it4 is the only build of the final prompt state"
(`phase2_log.md:155-156`), and `it5` was likewise built once (`phase2_log.md:187-190`).

**Prompts and code: yes, on v1 train.** Development protocol `phase2_design.md:63-75`:
- each iteration = rebuild the rules, run TGR for 1 trial on **all train tasks of both domains** (66 conversations),
  compare with the baselines on the **gold v2 block precision** and pass^1, read the blocked steps, then change only
  generic prompts or code (no domain words, no rule edits);
- the changes, in order (`phase2_log.md`):
  - it1→2: new `scope.md`; `judge.md` "obtained" rule (`:46-55`);
  - it2→3: `background_sentences`, ordering ban, stricter confirmation, decided judgments (`:87-95`);
  - it3→4: fact sentences → background, "information known", effort high (`:120-127`);
  - it4→5: user choices, date facts, prohibitions (`:170-186`). This round was evaluated with 3 trials on train (tag
    `luna_train_v5`, `:193`).
- **Data used:** τ-bench v1 **train** split of `SA/output/reproduction/labels/splits.json` (airline 20 tasks,
  retail 46; seed 0, fractions 0.4/0.2/0.4), gpt-6-luna for every role, gold v1/v2 scores as signals.
  - **Val** (airline 10 / retail 23) was used only **after** freezing (`SA/docs/tgr/val_report.md:1-5`).
  - **Test** was never used.
- **What this means for leaks:**
  - The prompts carry no task text, but they were fitted to how TGR behaved on v1 train conversations.
  - τ³ airline/retail tasks are largely the same tasks as v1, reordered (`tgr_portability.md` §5).
  - So any τ³ task that maps to v1 **train** is "development-seen" by the method. Val-mapped tasks are clean, and
    test-mapped tasks must be dropped (we already do this).
  - Banking was never seen.
  - The rule **build itself** reads no task data on τ³ either.

## 3. Cost and time of the original builds

From `SA/tgr_rules/<d>/<v>/manifest.json` and `SA/output/tgr/phase2/logs/build_*.log`:

| build | calls | input tok | output tok (incl. reasoning) | reasoning | $ (list) | API s | wall s |
|---|---|---|---|---|---|---|---|
| **airline frozen (it5)** | 2 (1 + 1 repair) | 14,037 | 31,721 | 15,629 | **0.0173** | 349 | 1,224 |
| **retail frozen (it5)** | 1 | 4,518 | 20,206 | 12,866 | **0.0106** | 202 | 491 |
| airline full (it4) | 1 | 3,745 | 20,657 | 13,663 | 0.0107 | 263 | 263 |
| retail full (it4) | 1 | 4,379 | 21,187 | 13,854 | 0.0110 | 280 | 569 |
| airline nob | 1 | 3,272 | 16,597 | 11,967 | 0.0086 | 166 | 166 |
| retail nob | 1 | 3,906 | 13,736 | 9,831 | 0.0073 | 137 | 137 |

- All builds it1-it5 + nob ≈ **$0.12**. The partner's report says $0.09, which covers the builds before it5
  (`phase2_log.md:168`; `p2_report.md:142-144`, which also says the aborted first effort-high build "may add a
  little unrecorded cost").
- **Wall time is much larger than API time** for airline it5 (1,224 vs 349 s) and for retail it4/it5. My reading: the
  gap is failed attempts (timeouts or truncated JSON) plus back-off, which the meter does not count (§1.3). So the
  true spend is somewhat higher than the manifests show. Each lost attempt costs up to about $0.017 at the 32k cap.
- Rule counts move between builds (airline rules 38/31/34/35/34 for it1-it5, retail 58/42/42/61/64). Part of this is
  the prompt changes, and part is sampling: it2 and it3 differ on folding the same exceptions
  (`phase2_log.md:112-115`).

## 4. Policy size limits, and banking_knowledge

### 4.1 What the build can take
- It takes **one policy text** and makes **one call over the whole of it**. This is a deliberate choice: "exceptions
  can sit in another section from their restriction; the policy is small (4.7-5.4 kB)" (decision T8,
  `phase2_design.md:61`). There is no chunking or merge code anywhere in `method_tgr`.
- No size check exists. The real limits are implicit:
  1. **output cap 32,000 tokens per call, reasoning included** (`rules.py:204`). v1 already used 16-32k. Above the
     cap the JSON is cut off, `json.loads` fails, the call is retried 5 times, and the build crashes with a
     RuntimeError (`policy_pipeline/llm.py:103-128`);
  2. **one disposition per sentence** in that same output (`rules.py:158-168`). The output therefore grows with the
     policy length, not only with the number of rules;
  3. 1,800 s request timeout (`tgr_build.py:69`);
  4. the model's context window. Its size for gpt-6-luna is not documented in `SA/`. `p0_report.md` §3 only says
     long-context meters exist: $0.20 / $0.75 per 1M tokens.
- At run time, **every background fact goes into every judge prompt** (`runtime.py:126`). Under B, every "fact"
  sentence becomes background (`rules.py:237-239`). A long policy therefore also makes every judge call long.

### 4.2 Banking sizes (τ³ v1.0.1 `fc0055d`; measured by me, logs `v4_tgrb_18_bank.txt`, `v4_tgrb_19_env.txt`)
- **Agent prompt** (default variant `alltools`, `T3/src/tau2/domains/banking_knowledge/retrieval.py:59`):
  - `prompts/all_tools.md` = `policy_header.md` (1,779 chars) + a "Knowledge base search tools" section
    (search-tool how-to + `shell_instructions.md`, 1,468 chars) + `additional_instructions.md` (3,816 chars);
  - about **7.5k chars ≈ 1.9k tokens**. The policy parts alone (header + additional) are about 5.6k chars ≈ 1.4k
    tokens and 43 non-blank lines, so the size of v1's wiki.
  - It is assembled by `build_policy(variant, kb, task)` (`retrieval.py:798-820`). `get_environment(task=None)` works
    for every variant except `golden_retrieval`, which pastes the task's required documents into the prompt
    (`retrieval.py:356-384, 445`). **Never use `golden_retrieval` / `required_docs.md` for a build (it reads the
    task).**
- **KB**: `data/tau2/domains/banking_knowledge/documents/`:
  - **698 JSON docs, 932,122 bytes** (≈ 210-230k tokens), about 14.4k lines, **71 categories** by file-name prefix.
    The largest category is `bank_accounts_(general)` with 47 docs; the largest doc is 8,148 bytes;
  - **44 docs name a `_NNNN`-style tool** (the discoverable-tool naming): 110,712 bytes ≈ 28k tokens, 1,787 lines.
- **Tools**: the agent's always-visible tools (`@is_tool`) are about 20: lookups, `change_user_email`,
  `log_verification`, `give_discoverable_user_tool`, `unlock_discoverable_agent_tool`, `call_discoverable_agent_tool`,
  `transfer_to_human_agents` and the search tools of the variant. **48 more tools are `@is_discoverable_tool`**
  (`tools.py`). The agent reaches them only through `unlock_…` + `call_discoverable_agent_tool(name, arguments)`, as
  the prompt itself says (`additional_instructions.md`, "Unlocking and Using Agent Discoverable Tools").

### 4.3 Options for banking
| option | what goes in | calls | fits the partner's code as is? | est. $ (luna list) |
|---|---|---|---|---|
| **A. prompt only** | the assembled agent prompt (the variant we will run) + the visible tools | 1 (+≤2 repairs) | **yes**; only the input changes, as for airline/retail | ≈ $0.01-0.02; worst ≈ $0.05 |
| B. prompt + the 44 tool-naming docs, one call | ≈ 35k input tokens, roughly 1.2-2k sentence ids | 1 | **no**: dispositions alone ≈ 40-80k output tokens > 32k cap → truncated JSON → 5 failed attempts → crash (≈ $0.10 lost). It needs a larger `max_output_tokens` (a change to `rules.py:204`) | ≈ $0.05-0.10 per call if the cap were raised |
| C. one call per tool-naming doc (prompt + 1 doc) | 44 chunks, ≈ 7-8k input tokens each | 44 (+repairs) | the calls are; the **merge is new code** (predicate-name clashes between chunks, prompt sentences labelled 44 times, renumbering, union of circuits; dedupe would reuse `rules.dedupe`) | ≈ $0.25-0.60; ≤ ≈ $1 with repairs |
| D. one call per category (all 698 docs) | 71 chunks | 71 (+repairs) | as C; the biggest categories may still overflow 32k | ≈ $0.8-1.5; ≤ ≈ $3 |
| E. whole KB, one call | ≈ 220k input tokens, roughly 10k+ sentence ids | 1 | **impossible** (several hundred thousand output tokens needed; long-context input price) | – |

Two more things matter for C and D:
- **Component A has a gap.** Under A the actions are the agent's tools, and the runtime keys circuits on the tool
  name (`runtime.py:78-81`).
  - The faithful choice: visible tools only. Every KB rule then becomes a rule on `call_discoverable_agent_tool` with
    a call-argument predicate ("the pending call's agent_tool_name is X"). The form allows this (`scope.md`:
    "X IMPLIES (NOT situation OR requirement)"). But all KB rules then land in **one circuit**, so every discoverable
    call gets one judge call over all of them.
  - The other choice: list the 48 discoverable tools as actions. This needs a runtime adapter that renames the step
    to the inner tool, which is a harness deviation.
- **The background grows.** Every KB "fact" sentence would go into every judge prompt (§4.1). With 44 docs that
  could be hundreds of sentences.

**Most faithful: option A.** In v1 the build input was exactly the policy the agent had in its system prompt
(`wiki.md`, `AGENTS.md:16`). In banking the system prompt is the assembled variant prompt. The KB is data the agent
fetches with tools, like DB rows, and the partner never built rules from tool outputs. Option A runs the partner's
code with no change except the input.
- Its cost is coverage: the per-product rules in the KB (confirmations, ownership, fees) will not be rules. Report
  this as a known gap.
- If KB rules are wanted, run **option C as a separately named extension** ("TGR + KB chunks, our merge"). It breaks
  decision T8, so it is not "the partner's method".
- **Filter choice (pre-register it):** banking has no "Domain Basic" heading. `policy_filter.py` exits when the
  heading is missing (`:62-64`), and `tgr_build.py:78` requires a `.filter.json`. So either:
  - no filter, and the wrapper writes a record with an empty drop list (my default: fewest choices); or
  - drop the descriptive "Knowledge base search tools" section, as the advisors did with "Domain Basic".

## 5. Re-running the build on τ³ airline and retail (v1.0.1)

### 5.1 Inputs (τ³ v1.0.1, commit `fc0055d`; log `v4_tgrb_17_v101.txt`)
| | v1 (frozen build) | τ³ v1.0.1 `policy.md` |
|---|---|---|
| airline file | 6,155 chars | 7,676 chars, sha `10dc0525…` |
| airline "Domain Basic" | `## Domain Basic`, 753 chars | `## Domain Basic` with `### User/Flight/Reservation` (lines 17-62, ≈ 1.3k chars); the filter drops it with its subsections → ≈ 6.4k chars left, about 75 non-blank lines (v1: 46 sentences) |
| retail file | 5,718 chars | 6,699 chars, sha `2c9652af…` |
| retail "Domain basic" | lines 19-32, 978 chars, **including "Exchange or modify order tools can only be called once"** | `## Domain basic` lines 26-79, ≈ 1.4k chars → ≈ 5.3k chars left. **"Generally, you can only take action on pending or delivered orders" and "…can only be called once per order" now sit under a separate `## Generic action rules` heading (line 80), so they reach the build.** This removes retail's part of limitation L1. Airline's "delayed / on time / flying … cannot be booked" is still inside Domain Basic, so it is still dropped |
| tools | `tools_info` of v1 (`tools_sha256` 67ceb47e… / b6540819…) | `[t.openai_schema for t in env.get_tools()]` (`openai_schema` is a property, `T3/src/tau2/environment/tool.py:139-149`). Its format matches what `rules.tool_list` reads (`function.name`, `description`, `parameters.properties.*.description`). The docstrings are longer, so the sha will differ |

### 5.2 Commands that WOULD be run (not run; each is a separate approval step)
Rules for all of them:
- Nothing is written under `~/ShieldAgent`, `~/opt` or `~/venvs`.
- A τ³ venv is needed only to dump the tool schemas. It is not installed yet. Put it in a project path such as
  `/home/azureuser/code_projects/.venvs/tau3-v1.0.1`, never under `~/venvs`.
- Every command's output goes to a log file.

```bash
P=/home/azureuser/code_projects/predicate_correctness
T=/home/azureuser/code_projects/third_party/tau2-bench
OUT=$P/output/tgr_build_t3          # new folder; nothing under ~/ShieldAgent
# 0. ($0) copy the two missing build files byte-identically from the tag, check sha
GIT_OPTIONAL_LOCKS=0 git -C ~/ShieldAgent show tgr-frozen-v1:exp_core/tgr_build.py    > $P/from_shieldagent/runner/exp_core/tgr_build.py
GIT_OPTIONAL_LOCKS=0 git -C ~/ShieldAgent show tgr-frozen-v1:exp_core/policy_filter.py > $P/from_shieldagent/runner/exp_core/policy_filter.py
# 1. ($0, stdlib only) the partner's filter, unchanged
for d in airline retail; do H="Domain Basic"
  ~/venvs/tau-bench/bin/python -I -B $P/from_shieldagent/runner/exp_core/policy_filter.py \
    --policy $T/data/tau2/domains/$d/policy.md --drop-heading "$H" \
    --out $OUT/policy_input/${d}_policy.rulebuild.txt > $P/output/logs/v4_tgrb_run_filter_$d.txt 2>&1; done
# steps 2-3: run once for each d in airline retail ($TAU3 = the new τ³ v1.0.1 venv)
# 2. ($0, no network) dump the τ³ agent tool schemas once
$TAU3/bin/python -I -B -c "import json,sys; from tau2.domains.$d.environment import get_environment as g; \
  json.dump([t.openai_schema for t in g().get_tools()], open(sys.argv[1],'w'), sort_keys=True, indent=1)" \
  $OUT/tools/${d}_tools_t3.json > $P/output/logs/v4_tgrb_run_tools_$d.txt 2>&1
# 3. (PAID: 1 call + ≤2 repairs per domain) a thin new wrapper = tgr_build.main with only paths/tools swapped
~/venvs/tau-bench/bin/python -B -u $P/guard/tgr_build_t3.py --profile luna-dev --env $d --run-id t3v101_s1 \
  --policy $OUT/policy_input/${d}_policy.rulebuild.txt --tools $OUT/tools/${d}_tools_t3.json \
  --effort high --timeout 1800 --out $OUT/tgr_rules > $P/output/logs/v4_tgrb_run_build_$d.txt 2>&1
```
- The wrapper `guard/tgr_build_t3.py` is new harness code. It must:
  - import `method_tgr.rules.build_rules` / `Flags` and `exp_core.models` from `FSA/runner/` unchanged;
  - read the policy and tools from files (in place of `tgr_build.py:28-32, 77-80`);
  - set `ROOT`/cache/output to `$P/output/` (the way `guard/run_online.py` does for the runner, `PROVENANCE.md:175`);
  - write the same four files and the same manifest fields (reuse `tgr_build.rules_md`), and add
    `tools_sha256` of the τ³ list plus the τ³ commit.
- Python: `~/venvs/tau-bench` already has openai + azure-identity for `utility/utils.py`. No `tau_bench` import is
  needed once the tools come from the JSON file.

### 5.3 Estimated calls and cost (gpt-6-luna $0.10 / 1M in, $0.50 / 1M out, reasoning billed as output)
Per call: input ≈ 5-8k tokens (policy 1.3-1.6k + prompts ≈ 1.5k + longer τ³ tool docstrings), output ≈ 20-32k (v1:
14-32k) → **≈ $0.011-0.017 per call**. A repair call has more input (the full rule JSON, ≈ 15-25k) → ≈ $0.012-0.019.
| domain | expected | likely range | hard ceiling (3 calls × 5 attempts, unmetered failures included) |
|---|---|---|---|
| **(a) airline** | 1-2 calls | **$0.01-0.035** | ≈ $0.27 |
| **(b) retail** | 1 call (v1 it4/it5 needed no repair) | **$0.01-0.035** | ≈ $0.27 |
| **(c) banking, option A** | 1-2 calls | **$0.01-0.04** | ≈ $0.27 |
| (c') banking, option C (44 chunks) | 44-60 calls | $0.25-0.60 | ≈ $1 realistic, more if many retries |
Wall time: about 5-20 min per domain (v1: 137-1,224 s). Run the domains one after another, as `build.sh` did.

### 5.4 Deterministic or not?
- **Not deterministic across fresh runs.** There is no temperature and no seed (§1.3), and the τ³ policy text and
  tool schemas differ from v1, so the cache key is new and every build is a fresh sample.
  - v1 evidence: it2 folded two exceptions and it3 did not (`phase2_log.md:112-115`). Effort `high` was chosen to
    reduce such sample defects (`:126-127`), but they remain.
- **Deterministic on replay.** The same inputs give the cached answer (cache key `policy_pipeline/llm.py:78-81`).
  Keep the cache with the run.
- Protocol to stay faithful (the partner's own): **one build per domain, used as is, with no selection among
  samples** (`phase2_log.md:155-156`). Pre-register "sample 1 is the rule set" and publish its sha before any τ³
  conversation runs.
  - A variance report (extra builds) is optional. It needs a separate cache directory per sample, because
    `sample=0` is fixed (`method_tgr/llm.py:35`).
  - Extra samples may be **reported but never chosen** by outcome.
- **Compared with the frozen v1 rules** (`tgr_portability.md`):
  - Running the frozen rules unchanged is fully deterministic and byte-identical to the partner's artifact. But they
    encode the **v1** policy: one conflict (gold business bags 3 → 4, rule 13 / S18) and missing τ³ rules.
  - **Hand-adapting** those rules is not the partner's method. AGENTS.md:8 says "Never hand-fix rules", and
    `rules.py:9` says "No rule is ever edited by hand or by code". It would also be our edit, not the method's.
  - **Rebuilding by the frozen method** is what the partner planned for a new setting: Phase 3b "frozen TGR (rules
    rebuilt with grok by the frozen method)", `AGENTS.md:267`. It is faithful to the method and current with τ³'s
    policy, at the price of one random sample.
  - Suggestion: run both arms ("frozen-v1 rules" and "rebuilt on τ³") if the budget allows. The rebuild costs cents.

## 6. v1-specific parts vs parts that must stay byte-identical

**Must stay byte-identical (this is "the partner's method"):**
- `method_tgr/rules.py`, with its constants: `max_repairs=2`, `max_output_tokens=32000`, the schema, validation,
  exact dedupe, renumbering, background rule and circuits;
- `method_tgr/policy_text.py`, `prompts.py` and `llm.py`;
- the 15 prompt files `method_tgr/prompts/*.md`, with the hashes in the frozen manifests (`rules_system a9b6172907b30867`,
  `rules_user af2d72bb054d67a4`, `scope a58521fd27fea7b4`, `form_restriction 8b9c21ea09fd68b6`,
  `predicates_grounded ea16ee627f4498d5`, `dispositions 94ae3489c99456bd`, `example_restriction ff23a600589c1fcf`,
  `actions_tools 062f4d76f84e290c`, `repair f099786338a41f89`, `judge c3acbd4c26240473`, …);
- `repro_core/ltlf.py` (parse/canonical);
- the transport `policy_pipeline/llm.py` (strict JSON schema, 5 attempts) and `repro_runtime/calls.py`;
- `exp_core/policy_filter.py::drop_sections`;
- the settings: flags A+B, model gpt-6-luna (profile luna-dev), effort **high**, timeout 1,800 s;
- the rule that **one build = the result**: no selection among samples and no rule edits.

The TGR copy in `FSA/runner/` already has `method_tgr/*` (prompt shas listed in `FSA/PROVENANCE.md:242-263`, equal to
the above). **It does not have `exp_core/tgr_build.py` or `policy_filter.py`** (`PROVENANCE.md:169`). They would have
to be copied byte-identically from tag `tgr-frozen-v1` first.

**v1-specific (harness; must be adapted, and the change documented):**
| item | v1 assumption | where |
|---|---|---|
| tools source | `tau_bench.envs.get_env(...).tools_info` (v1 package) | `tgr_build.py:28-32` |
| policy path | `output/tgr/policy_input/<env>_wiki.rulebuild.txt` + a **required** `.filter.json` | `tgr_build.py:77-79` |
| output + cache paths | under `ROOT` = the code folder; run inside `~/ShieldAgent`, it would write there (forbidden for us) | `tgr_build.py:82`; `models.py:30` |
| drop heading | "Domain Basic" (CLI value, not code) | `p0_report.md` §4 |
| `tools_sha256` value | changes with any schema text; only recorded | `tgr_build.py:94` |
| venv | `~/venvs/tau-bench` (has v1 `tau_bench`, openai, azure-identity) | `build.sh:6` |
| `--env` choices | `airline`/`retail` only through `get_env` | `tgr_build.py:29-31` |

There are no domain words in `method_tgr` (a test enforces it, `AGENTS.md:9`), so no tool name or wiki path inside the
method itself needs to change.
