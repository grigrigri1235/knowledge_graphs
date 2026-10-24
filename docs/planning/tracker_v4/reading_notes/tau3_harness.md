# τ³ harness map (for porting our guard runner)

Read-only study of `/home/azureuser/code_projects/third_party/tau2-bench` at commit `cc1df47`.
No Python run, no tau2 run, no network, $0. All paths below are relative to `src/tau2/` unless they start with `data/`, `docs/` or a top-level file name.

## 0. Main points first

- **This checkout is τ-bench 2.0.0, not τ³ v1.0.** `pyproject.toml:7` says `version = "2.0.0"` (released 2026-10-19). τ³ (v1.0.0) is the "previous release" (README.md:110-119). 2.0 changed scoring: communication checks are now judged by an LLM, the NL judge is `gpt-5.4-mini-2026-03-17`, and English retail and telecom use 50 replaced tasks each (CHANGELOG.md:56-90). 2.0 scores are not comparable with 1.x. If we want τ³ numbers, we need tag `v1.0.1`. This is a decision for the main chat.
- **Best place to put the guard:** subclass `Orchestrator` and override `_execute_tool_calls` (`orchestrator/orchestrator.py:327-343`). Every half-duplex tool call (agent and user) goes through this one function before the DB changes.
- **To block a call, return** `ToolMessage(id=call.id, role="tool", requestor=call.requestor, content=<block text>, error=True, execution_status="rejected")`. The agent gets this text back as the tool result. The `"rejected"` flag matters a lot: when the evaluator replays the run, it skips rejected calls (`environment/environment.py:373-378`). Without the flag, the replay would run the blocked write anyway, or raise on content mismatch, and the runner would re-run the whole paid episode up to 3 times.
- **Paid calls hide in the evaluator**, not just in the agent and the user. Airline grading calls a `gpt-5.5` judge for each `communicate_info` item. Retail grading calls a `gpt-5.4-mini` judge (112 of 114 tasks have NL_ASSERTION in their basis). The default banking setup (`alltools`) calls OpenAI embeddings while it builds the env, and again for every dense search the agent makes. Section 2.4 lists every site.
- **Banking seal:** importing tau2 and building the registry does not open task files. But the normal runner path (`build_text_orchestrator`, `run_simulation`, `get_info`) loads the language binding again and again. For banking, that binding globs **every** `data/tau2/domains/banking_knowledge/tasks/task_*.json`, even when you ask for one task id. No code under `src/` reads banking `tasks.json`. Section 4.3 has the safe one-file recipe.

---

## 1. Messages, loop, tool execution, guard hook

### 1.1 Message and tool-call types (`data_model/message.py`)
| Type | Where | Key fields |
|---|---|---|
| `ToolCall` | :61-142 | `id`, `name`, `arguments: dict`, `requestor: "assistant"\|"user"` |
| `ParticipantMessageBase` | :192-379 | `content`, `tool_calls`, `cost`, `usage` (dict), `raw_data` (full provider response, **saved** to results), `generation_time_seconds`, `turn_idx`, `timestamp` |
| `AssistantMessage` / `UserMessage` | :382 / :468 | role literal; `.text(...)` factory |
| `ToolMessage` | :554-608 | `id` (= call id), `content`, `requestor`, `error: bool`, **`execution_status: "executed"\|"rejected"`** (:567-571); validator: rejected needs `error=True` (:579-584) |
| `MultiToolMessage` | :611-617 | wraps several `ToolMessage`s when one assistant turn has several calls |
| `Tick` | :649+ | full-duplex (voice) only |

### 1.2 The loop (half-duplex text): `orchestrator/orchestrator.py`
- `BaseOrchestrator.run()` :274-305: `initialize()`, then `while not done: step(); _check_termination()`, then `_finalize()`.
- `initialize()` :500-687: replays the task's `initial_state` into the env (`set_state`). It sets seeds on the agent and user (:543-545). With no history, the first message is a fixed agent greeting "Hi! How can I help you today?" (:48-50, :646-659; the pack text greeting is the same), or `task.agent_opener`.
- `step()` :840-949 routes one message:
  - AGENT/ENV → USER (:857-874): `user.generate_next_message`. If the reply holds `###STOP###`, `###TRANSFER###` or `###OUT-OF-SCOPE###`, the run ends with USER_STOP (`user/user_simulator.py:141-155`, tokens at `user/user_simulator_base.py:51-53`).
  - USER/ENV → AGENT (:876-922): `agent.generate_next_message`. A message with tool calls goes to ENV, a text message goes to USER.
  - AGENT/USER → ENV (:924-941): **`tool_results = self._execute_tool_calls(self.message.tool_calls)`** (:931). The results go into the trajectory (:935). Then `self.message = _wrap_tool_results(...)` (:936), and the results go back to whoever made the call (:937).
- `_execute_tool_calls` :327-343: loops `environment.get_response(tool_call)` and does `num_errors += 1` when `error` is true.
- `Environment.get_response` (`environment/environment.py:473-498`) → `make_tool_call` (:158-185) → `toolkit.use_tool`. An exception becomes `"Error: ..."` with `error=True`. Note: many banking tools *return* `"Error: ..."` strings instead of raising, so those come back with `error=False` (e.g. `domains/banking_knowledge/tools.py:660-684`).
- How the agent sees tool results: `agent/llm_agent.py:133-137` appends the ToolMessage(s) to its state. `utils/llm_utils.py:256-263` sends them as `{"role":"tool","content":..., "tool_call_id": id}`. So **the block text reaches the agent as the tool result**.
- Precedent in the code: the orchestrator already rejects calls itself, for a bundled terminating tool (:892-914). It builds the same `ToolMessage(error=True, execution_status="rejected")` we need.

### 1.3 Hook options (ranked)
1. **Orchestrator subclass (recommended).** Override `_execute_tool_calls(self, tool_calls)`. For each call: if `requestor=="assistant"`, ask the guard first. The guard can read the live state through `self.environment.tools.db`, the trajectory so far through `self.trajectory`, the policy through `self.environment.get_policy()`, and the task through `self.task`. On allow, call `self.environment.get_response(call)`. On block, build the rejected ToolMessage. Count blocks in our own counter, not in `num_errors` (see 1.4). To use it, build the orchestrator yourself (`runner/build.py:570-662` shows how), or build with `build_text_orchestrator` and then swap `orchestrator.__class__`.
2. Wrapping the env (`Environment.get_response`). This works only if it also sets `execution_status="rejected"`. Downsides: `set_state` also calls `get_response` during the initial-state replay (`environment.py:398`). The evaluator builds *fresh* envs from the registry, so a wrapper on our instance does not reach grading. Both points are fine, but the logic is less clear.
3. Wrapping the agent (`generate_next_message`). This does not work well, because the orchestrator still executes whatever calls come out. We would have to rewrite the message or fake tool results.
- Full-duplex (voice) executes calls in a different place (`orchestrator/full_duplex_orchestrator.py:479`). Out of scope for us.

### 1.4 Limits and how a run ends
- `max_steps`: CLI default 200 (`config.py:4`, `cli.py:141-146`). The constructor default is 100 (`orchestrator.py:415`). Each routed message counts as one step (:948). The check is skipped while waiting for the env (:762-763) → `MAX_STEPS`.
- `max_errors`: default 10 (`config.py:5`). The count is **total tool errors** (`num_errors`, :340), not "in a row" as the CLI help says. When reached → `TOO_MANY_ERRORS` (:768-770). **Guard trap:** if blocked calls count as errors, 10 blocks end the episode, and the reward becomes 0.
- `timeout` (seconds, default none) → `TIMEOUT` (:238-250).
- Reward is forced to 0 unless the run ended with `AGENT_STOP` or `USER_STOP` (`evaluator/evaluator.py:123-133`).
- The normal `LLMAgent` never stops the run by itself. `is_stop` is true only for domain-configured stop tools (`agent/llm_agent.py:81-86`; only `intake` uses `end_call`, `runner/build.py:155-156`). In practice the user simulator ends the run.
- `TerminationReason` enum: `data_model/simulation.py:1070-1081` (also INFRASTRUCTURE_ERROR, CONTEXT_WINDOW_EXCEEDED, …).
- **transfer_to_human_agents** is an ordinary tool: `ToolType.GENERIC`, `mutates_state=False`. It is not replayed and does not end the run (airline `domains/airline/tools.py:603`, retail :777, banking `domains/banking_knowledge/tools.py:366-380` with a `reason` enum). The run ends only when the user simulator, after the agent says it is transferring, emits `###TRANSFER###` (`user/guidelines.py:108,190`). Only the solo agent treats it specially (`agent/llm_agent.py:340`).
- Retries: if `run_fn` raises, the **whole simulation is re-run** up to `max_retries` (default 3) times, then saved as INFRASTRUCTURE_ERROR (`runner/progress.py:20-110`, `runner/batch.py:654-666`). Every retry is paid again.

### 1.5 Banking-specific tool shape (the guard must look inside the arguments)
- Writes mostly go through `call_discoverable_agent_tool(agent_tool_name, arguments: JSON string)` (WRITE, `tools.py:643-700`). The real tool name and arguments sit inside the call's arguments. 49 discoverable tools; 34 of them are WRITE.
- `unlock_discoverable_agent_tool` (:602-641) and `give_discoverable_user_tool` (:532) are GENERIC but `mutates_state=True`, so they are replayed.
- A call to a READ discoverable tool is written to the DB-hashed table `agent_discoverable_tools` only when the tool is in the task's golden trajectory (`read_log_allowlist`, :686-698). That allowlist is built **from the task's expected actions** (`runner/build.py:508-532, 565-566`). So the env built for a banking task depends on its evaluation criteria. The agent cannot see this, but our runner must pass the same `env_kwargs` to grading.
- The banking policy is the retrieval-variant prompt with KB text (`domains/banking_knowledge/retrieval.py:791-813`), not a `policy.md`.

---

## 2. LLM layer and every paid or network call

### 2.1 How a model call is made
- Everything goes through `utils/llm_utils.py::generate` (:516-585) → `_generate_once` (:588-737) → `litellm.completion(model=api_model, messages, tools, tool_choice, **kwargs)` (:677-683).
- litellm is pinned to `>=1.80.15,<1.82.7` (`pyproject.toml:25`); `uv.lock` has 1.81.11. Python must be `>=3.12,<3.14`; `.python-version` = 3.12.
- Model names are litellm strings (`--agent-llm`, `--user-llm`). Extra args go through `--agent-llm-args` / `--user-llm-args` as JSON. They become `llm_args` and are passed unchanged as completion kwargs (`agent/llm_agent.py:138-144`, `user/user_simulator.py:194-200`). `litellm.drop_params = True` (:72).
- **Custom OpenAI-compatible endpoint:** model `"openai/<served-name>"` plus llm_args `{"api_base": "http://host:port/v1", "api_key": "..."}`. **Trap:** if the *last path part* of the model name starts with `gpt-5`, it is forced through the OpenAI **Responses** API bridge (`openai/responses/...`, :442-451, :637-641). A local server that only speaks chat-completions would then fail. Serve under a name that does not start with `gpt-5`, or patch this rule.
- Defaults: agent and user `gpt-4.1-2025-04-14`, `temperature 0.0` (`config.py:26-31`; CLI `cli.py:85-115`). Released benchmark runs use user `openai/gpt-5.5`, `reasoning_effort: low` (`config.py:316-317`).
- Seed: the run seed defaults to 300 (`config.py:6`). Per-trial seeds come from `random.seed(config.seed)` then `randint(0, 1e6)` per trial (`runner/batch.py:879-880`). The orchestrator puts the seed into both `llm_args["seed"]` (`agent/base/llm_config.py:41-48`, `orchestrator.py:543-545`), so the provider receives a `seed` parameter.
- Retries inside litellm: `num_retries = DEFAULT_MAX_RETRIES = 3` unless set (`llm_utils.py:612-613`, `config.py:64`). This stacks with the simulation-level retries in 1.4.
- Cost: `get_response_cost` (:126-158). GPT-5.5 is priced by hand. Everything else uses `litellm.completion_cost`. An **unknown model logs an error and returns 0.0**, so a custom endpoint reports $0 unless we register a price (e.g. `litellm.register_model`) or count tokens ourselves.
- Tokens: `usage` keeps only `prompt_tokens` and `completion_tokens` (:161-168). Cached and reasoning tokens are only in `raw_data` (the full response dict, saved per message).
- Per role: `get_cost(messages)` sums `AssistantMessage.cost` → `agent_cost` and `UserMessage.cost` → `user_cost` (:740-766). This is stored on `SimulationRun.agent_cost/user_cost` (`orchestrator.py:811`, `data_model/simulation.py:1117-1122`). **Judge calls in the evaluator are not counted anywhere.** NL and communicate evaluators drop the returned cost (no `cost` in `evaluator/evaluator_nl_assertions.py` or `evaluator/evaluator_communicate.py`).
- Logging of LLM calls to files happens only with `--verbose-logs` (`llm_utils.py:370-430`). There is a Redis/local cache, off by default (`config.py:71`), and Langfuse, off (`config.py:83`).

### 2.2 Things that happen at import time
- `import tau2...` → `tau2/utils/utils.py:10-14` runs **`load_dotenv()`**. It searches for a `.env` up the directory tree, so any `.env` above the code can put API keys into the process. Today `/home/azureuser/code_projects/` has no `.env`, but we should pin this (e.g. `dotenv` override, or run with an empty env).
- `import litellm` (`llm_utils.py:14`): litellm normally **downloads its model price map from GitHub at import**, unless `LITELLM_LOCAL_MODEL_COST_MAP=True`. This is known litellm behaviour, not seen in this repo; check after install. It is a network call, not a paid one. Our v3 runner already sets this variable.
- `llm_utils.py:53-55` creates httpx clients. This makes no network call.
- `registry.py` (:284-364) imports every domain module and registers *functions*. It reads no data. Banking package modules have no load calls at module level (only constants: `domains/banking_knowledge/utils.py:11,38-43`).
- The CLI (`cli.py:63`, `get_options()`) builds the registry to fill argparse `choices`. The custom-run path calls `extension_for_domain` (`cli.py:806-815`), which globs `data/tau2/multilingual_extensions/*/<lang>/extension.json`. With the seal (chmod 000) this listing fails silently. It never opens task files.
- `get_commit_hash()` runs `git rev-parse HEAD` in the current directory (`utils/utils.py:88-100`). This is local only.

### 2.3 Calls outside the agent and the user (evaluator, env, runner)
See the table in 2.4. Key ones:
- **Communicate judge** (semantic by default since 2.0): one `generate` call **per `communicate_info` item** with judge `gpt-5.5`, `reasoning_effort: low` (`evaluator/evaluator_communicate.py:125-163`; defaults `config.py:53-54`, `data_model/semantic_communication.py:14-87`). An empty or null `communicate_info` makes no call (docs/evaluation.md:80-81). This runs only when COMMUNICATE is in `reward_basis` (`evaluator/evaluator.py:217-223`). Switch it off with `--communicate-scorer substring`, or `CommunicateScoring(scorer="substring")` (`multilingual/cli.py:20-66`).
- **NL-assertion judge:** `gpt-5.4-mini-2026-03-17`, **hard-coded** (`evaluator/evaluator_nl_assertions.py:117-121`, `config.py:45-46`). No CLI override. It runs when NL_ASSERTION is in the basis or `evaluation_type=ALL_WITH_NL_ASSERTIONS*` (`evaluator.py:224-230`). The batch runner default is `ALL` (`runner/batch.py:369,855,1016`). The docs claim the CLI uses ALL_WITH_NL_ASSERTIONS (docs/evaluation.md:171); the code does not show that. To avoid paid calls, monkeypatch the constant, or grade with `EvaluationType.ENV` + `ACTION` and judge NL later.
- **Banking retrieval:** with retrieval config `alltools` (the **default** for banking, `data_model/simulation.py:174-178`, `config.py:37`), every env construction builds a BM25 pipeline, a **dense pipeline with OpenAI `text-embedding-3-large`** (`domains/banking_knowledge/retrieval.py:157-195, 588-592, 755-759`) and a **sandbox** (`srt` + `rg`/`bwrap`/`socat`, `knowledge/sandbox_manager.py:84,118`). The embeddings for 698 docs are computed once and cached on disk under `data/.embeddings_cache` (relative to the current directory; `knowledge/embeddings_cache.py:68-76, 514-563`). A cache miss means a paid embeddings job. **Each `KB_search_dense` tool call by the agent embeds the query** (paid, network; `knowledge/input_preprocessors/embedding_encoder.py:102,129`; in-memory cache only). The env is built about 4–5 times per simulation (orchestrator, `get_info`, evaluator tool-types, predicted env, gold env: `runner/helpers.py:254`, `evaluator/evaluator.py:162`, `evaluator/evaluator_env.py:85,97`).
- `*_reranker` configs: a pointwise LLM reranker (`gpt-5.2`, `knowledge/postprocessors/pointwise_llm_reranker.py:37`). BGE and Qwen rerankers POST to Sierra Baseten URLs (`bge_reranker.py:12`, `qwen_reranker.py:30-31`).
- `$0` offline banking configs: `bm25`, `bm25_grep`, `grep_only`, `no_knowledge`, `full_kb`, `golden_retrieval` (AGENTS.md:264). Note that `golden_retrieval` puts the task's `required_documents` in the prompt (`retrieval.py:349-378`), so it reads task data.
- Optional extras, off by default: `--auto-review` (LLM review, `claude-opus-4-5`, `config.py:56`, `cli.py:488-506`). Hallucination check (full-duplex only, `runner/batch.py:669-670`). Auth classifier (`evaluator/auth_classifier.py:138,182`). `environment/utils/interface_agent.py:66,79` (only the env CLI).

### 2.4 Every place that can make a PAID (P) or NETWORK (N) call
| # | Where | When | P/N | Default on? |
|---|---|---|---|---|
| 1 | `agent/llm_agent.py:138` (`LLMAgent`) | each agent turn | P,N | yes |
| 2 | `user/user_simulator.py:194` | each user turn | P,N | yes |
| 3 | `agent/llm_agent.py:262,479` (GT / solo agents) | if chosen | P,N | no |
| 4 | `evaluator/evaluator_communicate.py:139` (`gpt-5.5`) | grading, per communicate item, COMMUNICATE in basis (airline: all 50) | P,N | **yes** |
| 5 | `evaluator/evaluator_nl_assertions.py:117` (`gpt-5.4-mini`) | grading, NL_ASSERTION in basis (retail 112/114) or ALL_WITH_NL | P,N | **yes for retail** |
| 6 | `knowledge/embedders/openai_embedder.py:27` / `openrouter_embedder.py:116` via `embedding_indexer` | **banking env construction** on cache miss; `prepare_batch` → `warm_kb_cache` (`runner/batch.py:895-918`) | P,N | **yes (alltools)** |
| 7 | `knowledge/input_preprocessors/embedding_encoder.py:102,129` | each agent `KB_search_dense` / embedding `KB_search` call | P,N | **yes (alltools)** |
| 8 | `knowledge/postprocessors/pointwise_llm_reranker.py` (`gpt-5.2`) | `*_reranker` configs, per search | P,N | no |
| 9 | `knowledge/postprocessors/bge_reranker.py:12`, `qwen_reranker.py:30` (Baseten) | those configs | N (P?) | no |
| 10 | `evaluator/review_llm_judge*.py`, `auth_classifier.py` | `--auto-review` | P,N | no |
| 11 | `evaluator/hallucination_reviewer.py:230` | voice only | P,N | no (text) |
| 12 | `user/user_simulator_streaming.py:187,257,1309`, all `voice/**` | voice only | P,N | no (text) |
| 13 | `environment/utils/interface_agent.py:66,79` | `make env-cli` only | P,N | no |
| 14 | litellm import (price map download) | import | N | likely yes (set `LITELLM_LOCAL_MODEL_COST_MAP=True`) |
| 15 | `utils/utils.py:14` `load_dotenv()` | import | — (loads keys) | yes |
| 16 | `knowledge/sandbox_manager.py` (`srt` subprocess) | banking `alltools`/`terminal_use*` env build | local; srt settings include a `network` block (:531) | yes (alltools) |
| 17 | `judges/**`, `multilingual/factory/**`, `scripts/leaderboard/**` | separate commands | P,N | no |
| 18 | `runner/batch.py:654` `run_with_retry` | repeats 1–7 on any exception, up to 3× | P | yes |

### 2.5 Design facts for a $0 setup (asked by the main chat)
- **Banking needs an offline retrieval variant.** The default `alltools` = BM25 search (`KB_search_bm25`) + dense OpenAI-embedding search (`KB_search_dense`, paid) + read-only shell sandbox (`retrieval.py:401-420, 588-592`). There is no registered "alltools without dense" variant: `build_tools` uses the AllTools toolkit only when all three parts exist (`retrieval.py:750-759`).
  - **Closest offline variant: `bm25_grep`.** It has BM25 `KB_search` plus a `grep` tool (exact pattern search, close to what the shell is used for). No API key, no sandbox. Prompt `classic_rag_bm25.md`, `top_k` 10 (`retrieval.py:493-500, 291-307`).
  - `bm25` = BM25 only (:555-561). `grep_only` = grep only (:569-575). `terminal_use` = shell only. It is offline, but it needs the `srt` sandbox install (:576-581).
  - Tool names and prompt differ from `alltools`, so scores are not comparable with official banking (`alltools`) numbers.
  - How to select it: CLI `--retrieval-config bm25_grep` (`cli.py:458-471`), optional `--retrieval-config-kwargs '{"top_k": 10, "grep_top_k": 10}'`. In Python: `TextRunConfig(domain="banking_knowledge", retrieval_config="bm25_grep", ...)`. The default fill-in only happens when it is None (`data_model/simulation.py:174-178`). Our runner must pass the same `retrieval_variant` in `env_kwargs` to grading. `_build_env_kwargs` already does this (`runner/build.py:558-566`). Note that `prepare_batch` then warms no embeddings, because `bm25_grep` is not in `CONFIG_EMBEDDERS` (`knowledge/embeddings_cache.py:609-627`).
- **Substring communicate scoring:**
  - CLI: `--communicate-scorer substring` (`multilingual/cli.py:81-87, 112-126`).
  - Python: `from tau2.data_model.semantic_communication import CommunicateScoring, CommunicateScorer`, then `TextRunConfig(..., communicate_scoring=CommunicateScoring(scorer=CommunicateScorer.SUBSTRING))`. A plain dict `{"scorer": "substring"}` also works. You must **not** pass `judge` with substring; the validator raises (`semantic_communication.py:68-73`). The help text says substring is for "custom runs only". `run_simulation` raises if a passed `communicate_scoring` differs from the orchestrator's call context (`runner/simulation.py:108-112`), so set it on the config, not only at grading.
  - The other option is to keep the semantic judge but point it at our own endpoint: `--communicate-judge '{"model": "openai/<name>", "model_args": {"api_base": "...", "api_key": "..."}}'` (`multilingual/cli.py:88-94, 127-129`). This is not comparable with the pinned `gpt-5.5` judge.
- **NL-assertion judge:** model `gpt-5.4-mini-2026-03-17`, args `{"reasoning_effort": "low"}` (`config.py:45-46`). It is hard-coded in `evaluator/evaluator_nl_assertions.py:117-121`: no CLI flag, no config field, and the cost is not recorded. It runs only when NL_ASSERTION is in the task's `reward_basis` (retail: 112/114), or with `ALL_WITH_NL_ASSERTIONS*`. For $0, we can (a) grade retail with `EvaluationType.ENV` and score NL later in an approved paid step, or (b) monkeypatch `tau2.evaluator.evaluator_nl_assertions.DEFAULT_LLM_NL_ASSERTIONS` / `_ARGS` (module-level imports, so patch that module, not `tau2.config`). Option (b) is not comparable with official scores.

This matches the trap we hit in v1. In 2.0 the trap is not in user setup; it is in **grading** (rows 4-5) and in **banking env construction** (row 6). Constructing a `UserSimulator` makes no call. Its first call is the first `generate_next_message`.

---

## 3. Evaluator

- Entry point: `evaluator/evaluator.py::evaluate_simulation` (:89-371). Under `ALL` (:202-293) it always computes ENV and ACTION. It adds COMMUNICATE and NL only when they are in the basis. The **final reward is the product of the components in `task.evaluation_criteria.reward_basis`** (:233-268). If the basis names a component that was not evaluated, it raises (:245-250).
- `RewardType` = `DB`, `ENV_ASSERTION`, `NL_ASSERTION`, `ACTION`, `COMMUNICATE` (`data_model/tasks.py:237-267`). The schema default basis is `[DB, COMMUNICATE]` (:427-435).
- Which domains use which (counted from task files; banking not opened):
  - airline: 50 × `[DB, COMMUNICATE]`
  - retail: 112 × `[DB, NL_ASSERTION]`, 2 × `[DB]` (the 50 English replacements are also `[DB, NL_ASSERTION]`)
  - telecom: `[ENV_ASSERTION]` (most), 32 × `[ENV_ASSERTION, ACTION]` in the full generated set
  - banking: per docs, ACTION is in the basis for "about 9 out of ~100" tasks (docs/evaluation.md:22,197-201). Other bases not checked (sealed).
- **DB check** (`evaluator/evaluator_env.py:22-165`):
  - Predicted env = fresh env + init state + **replay of the whole trajectory** with `set_state` (:85-94). Replay runs only `mutates_state=True` tools, skips `rejected` and unknown tools, and with `strict=True` raises if a replayed output differs from the recorded one (`environment/environment.py:372-418`).
  - Gold env = fresh env + init state + `evaluation_criteria.actions` run one by one (:97-115).
  - It then compares `get_dict_hash(db.model_dump())` for agent and user DBs (:118-129; `environment/toolkit.py:242-244`). A hash match is all-or-nothing.
  - Env assertions run on the predicted env (:134-148).
- **ACTION check** (`evaluator/evaluator_action.py:16-150`): every gold action must match *some* tool call in the trajectory (`Action.compare_with_tool_call`, `data_model/tasks.py:178-196`; `compare_args` limits which arguments are compared). Tool calls come from all Assistant and User messages (:112-129). **Rejected (blocked) calls still count as matches**, because the check reads attempted calls, not executed ones. Keep this in mind for banking ACTION tasks.
- **Expected actions per task:** yes. `task.evaluation_criteria.actions: list[Action]` with `name`, `arguments`, `requestor`, `compare_args` (`data_model/tasks.py:116-196, 377-390`). Writes can be classified with `toolkit.tool_mutates_state(name)` / `tool_type(name)` (`environment/toolkit.py:198-209`). For the harm metric "accepted write the task did not expect", use: executed call (`execution_status=="executed"`) + mutating tool (for banking, a `call_discoverable_agent_tool` whose inner tool is WRITE, plus unlock/give) + no matching gold action. Caveats:
  - (a) docs/evaluation.md:14-20 says `actions` is *one* reference path, not the only correct one. Some "unexpected" writes can still give a matching DB end state.
  - (b) For banking, reading `actions` means opening task files. That is post-freeze only for sealed tasks.
  - (c) `RewardInfo.action_checks` is filled on every run under `ALL` (`evaluator.py:211-215, 274`). `partial_action_reward` splits READ and WRITE (docs/evaluation.md:187-190).
- `RewardInfo` fields: `reward, db_check, env_assertions, action_checks, nl_assertions, communicate_checks, reward_basis, reward_breakdown, info` (`data_model/simulation.py:796+`).

---

## 4. Running

### 4.1 Config and CLI
- `TextRunConfig` = `BaseRunConfig` (`data_model/simulation.py:60-305`: domain, task_set_name, task_split_name, task_ids, num_tasks, language, save_to, benchmark…) + `RunSettings` (`data_model/run_config.py:350-541`: llm_user, llm_args_user, num_trials, max_errors, timeout, max_concurrency=3, workers=0, seed=300, max_retries=3, retrieval_config, communicate_scoring…) + `TextRunSettings` (:543-600: agent, llm_agent, llm_args_agent, user, max_steps, enforce_communication_protocol).
- CLI: `tau2 run` (`cli.py:60-512`, `cli.py:709-895`). Text runs are "custom" unless `--benchmark text`. `--task-split-name` defaults to `base`. Official splits: airline train 30 / test 20 / base 50; retail train 74 / test 40 / base 114 (`data/tau2/domains/*/split_tasks.json`).
- Layers: Layer 1 `runner/simulation.py::run_simulation(orchestrator, evaluation_type, env_kwargs, communicate_scoring)` (:20-160). Layer 2 `runner/build.py` (`build_environment` :55, `build_agent` :100, `build_user` :180, `build_text_orchestrator` :570). Layer 3 `runner/batch.py` (`run_single_task` :364, `run_unit` :584, `prepare_batch` :849, `run_tasks` :1010, `run_domain` :1232).
- Concurrency: a `ThreadPoolExecutor(max_workers=max_concurrency)` of consumer threads (`runner/batch.py:1113-1150`). `--workers N` gives a multi-process controller (`runner/controller.py`, `runner/worker.py`). Resume: an existing `results.json` is resumed by `(trial, task_id, seed)` (`batch.py:934-962`).
- Custom agents: `registry.register_agent_factory(factory, name)` (`registry.py:112-140`). Factory signature `factory(tools, domain_policy, **kwargs)`.

### 4.2 Results JSON
- Text runs: one file, `data/simulations/<save_to>/results.json` (`runner/batch.py:1219-1229`; `DATA_DIR` = `TAU2_DATA_DIR` or the repo `data/`, `utils/utils.py:17-25`).
- `Results` = `{timestamp, info, tasks, simulations, simulation_index}` (`data_model/simulation.py:1230-1258`). **`tasks` embeds the full Task objects, including evaluation criteria.** So any results file for a sealed banking task is itself sealed material.
- `Info` (:942+) holds git_commit, num_trials, max_steps, max_errors, user_info, agent_info (llm, llm_args), environment_info (policy), seed, language_tasks, communicate_scoring, retrieval_config.
- `SimulationRun` (:1083-1190) holds id, task_id, trial, seed, start/end_time, duration, termination_reason, agent_cost, user_cost, reward_info, **messages** (each with cost/usage/raw_data), policy, info.
- Total tokens: `get_token_usage(messages)` (`utils/llm_utils.py:769-782`).

### 4.3 Task loading and the banking seal (asked by the main chat)
- **Import / registry:** reads no task file (`registry.py:352-353` only registers `get_tasks`).
- **Banking loader:** `domains/banking_knowledge/environment.py:97-125`. `sorted(Path(KNOWLEDGE_TASK_SET_PATH).glob("task_*.json"))` reads **every file** in `data/tau2/domains/banking_knowledge/tasks/` (`utils.py:40`). It ignores the split name. It does **not** read `banking_knowledge/tasks.json`. Under `src/`, only `scripts/recombine_rewards.py:146` and `scripts/view_simulations.py:778` read a `<domain>/tasks.json`, and only when those commands are used.
- **Banking env construction** (`get_environment`, :36-94) reads `db.json` and `documents/` only. It reads a task only if one is passed in (golden_retrieval prompt; allowlist from `_build_env_kwargs`).
- **But the run path reloads the whole population many times:**
  - `pin_language_artifacts` → `load_run_language` → `load_language` → `_binding_tasks` → `_registry_tasks` → `registry.get_tasks_loader("banking_knowledge")()` (`multilingual/runtime.py:274-347, 350-403, 514-531, 680-691`).
  - It is called from `_load_run_tasks` (`runner/batch.py:1191-1201`), `get_info` (`runner/helpers.py:236`), `task_context` (`runtime.py:708`, inside `build_text_orchestrator`), `_build_env_kwargs` (`runner/build.py:548`), and `run_simulation` → `reload_recorded_call` (`runner/simulation.py:78`).
  - Task ids are filtered only *after* the load (`runner/helpers.py:83-105`). So `--task-ids task_NNN` still globs all banking task files.
  - English binds banking through `default_binding` (registry source, no metadata file; `data/tau2/multilingual/en/pack.yaml:175-177`). Registry bindings are "open": a task given by the caller is accepted with default metadata (`runtime.py:592-594`).
- **With today's seal (tasks dir chmod 000):** `tasks_dir.exists()` is true, the glob gets PermissionError, and pathlib swallows it, so the loader returns `[]`. Then `load_language` raises "language binding has empty or duplicate task IDs" (`runtime.py:464-466`). So the seal holds: a banking run fails loudly before any provider work. (Inferred from the code. Check after install.)
- **How to load ONE banking task, or a fixed id subset, without touching the others.** Pick one:
  - (a) **Stage the files:** the main chat copies only the calibration files (e.g. `task_NNN.json`) into a separate dir. Before any tau2 run code, our runner sets `tau2.domains.banking_knowledge.environment.KNOWLEDGE_TASK_SET_PATH = <staging dir>`. `get_tasks` reads this module-level name at call time (:111); the registry holds the function, not the path. Then every reload sees only the staged files.
  - (b) **Replace the loader:** `registry._tasks["banking_knowledge"] = lambda task_split_name=None, **kw: [Task.model_validate(json.load(open(p))) for p in ALLOWED_PATHS]`. Direct dict write, because `register_tasks` refuses duplicates (`registry.py:209-211`).
  - (c) Do not use any `multilingual` or runner layer: build `get_environment(retrieval_variant=..., task=task, read_log_allowlist=_derive_read_log_allowlist(task))`, then `LLMAgent`, `UserSimulator`, `Orchestrator` with `call_context=None`, then `evaluate_simulation(...)` directly. This loses the 2.0 persona/greeting binding, so it is not input-identical to official runs.
  - For (a) and (b), the directory permission can stay "x without r" (open by exact name works, listing fails). Option (a) does not need even that if the main chat copies the files.
  - Also: do not run `tau2 run --domain banking_knowledge` without (a) or (b). Do not run `scripts/evaluate_trajectories.py --fresh-tasks` (it loads all tasks, `:88`) or `task_subsets` on banking.
- `tau2 run ... --dry-run` (custom run) only validates and prints the config (`cli.py:891-894`). It loads no tasks and makes no LLM call.

---

## 5. Install, network needs, dry run
- Python `>=3.12,<3.14` (`pyproject.toml:10`), `.python-version` = 3.12. Install with `uv sync` (core) and `uv sync --extra knowledge` for banking (`rank-bm25`, `openai`; `pyproject.toml:68-71`). Set `UV_FROZEN=1` (AGENTS.md:260). Note: `/home/azureuser/code_projects/.venv_tau3` **already exists**, although the brief says no venv yet. Someone should check what is in it.
- Runtime network needs: provider APIs for the agent, the user and the judges; OpenAI embeddings for `alltools`/`openai_*`; OpenRouter for `qwen_*`; Baseten for BGE/Qwen rerankers; the litellm price map at import (unless set local). `alltools` also needs the npm `@anthropic-ai/sandbox-runtime@0.0.23` plus `ripgrep bubblewrap socat` (AGENTS.md:264), or env construction raises.
- **No built-in no-LLM dry run of an episode.** `DummyUser` is solo-only and raises on `generate_next_message` (`user/user_simulator.py:228-248`). There is no dummy agent. For a $0 end-to-end smoke test:
  - (1) Write scripted `HalfDuplexAgent` / `HalfDuplexUser` subclasses (or pass litellm `mock_response` through `llm_args`; this is litellm behaviour, check after install).
  - (2) Grade with `EvaluationType.ENV` (or `ACTION`), `CommunicateScoring(scorer="substring")`, and no NL judge.
  - (3) Use banking `retrieval_config=bm25` (or `bm25_grep`).
  - (4) Set `LITELLM_LOCAL_MODEL_COST_MAP=True`, unset API keys, block the network like our v3 dry runs.
- Interactive options exist: `tau2 play` and the Gym env (`gym/gym_agent.py`; CHANGELOG 0.2.1). They are not needed.

---

## 6. Compared with our v1 runner (`predicate_correctness/guard/run_online_v3.py`)
- v1 wrapped the `repro_online/episode.py::run_episode` loop with guard arms. In τ³, the same seam is `Orchestrator._execute_tool_calls`, and the block result must be the rejected `ToolMessage`.
- Things to port as they are: network block + `LITELLM_LOCAL_MODEL_COST_MAP` in dry runs, the write guard, soft stops, per-role cost meters. Add a judge-cost meter, because τ³ does not record judge cost (2.1).
- New: grading itself is paid (2.3). The runner must pick an evaluation type and communicate scorer on purpose, and count their cost.

## 7. Seal report (paths only; no banking task facts are recorded here)
- `CHANGELOG.md`: I read the whole file before the alert. Lines 246-247 and 330-376 name banking task facts. Nothing from them is written in these notes.
- `RELEASE_NOTES.md`: I saw only headings and grep hit lines in its 1.0.1 section (lines 57-177). I did not read the body.
- `github-release-body.md`: not opened.
- `docs/evaluation.md`: mentions banking only as a count (lines 22, 198).
- `src/tau2/domains/banking_knowledge/tools.py`: I read only lines 360-380 (transfer tool), 600-704 (discoverable wrappers) and grep lines of decorators. Not lines 1255-1363.
- No sealed path was opened. The tool's working directory was `data/tau2/domains/banking_knowledge/documents` (KB documents, which the agent can see, not sealed). Nothing was read from it.

---

## Errata for v1.0.1

Checked 2026-10-23, $0, read only. The clone is now at tag **v1.0.1** (commit fc0055d, `pyproject.toml` version "1.0.1"). This is τ³-bench, the version we use. Everything above was read at cc1df47 (2.0.0 plus leaderboard and voice commits). Method: `git diff v1.0.1 v2.0.0 --stat` and per-file diffs, plus `git show v1.0.1:<path>`. Airline, retail and core code only. No banking file was opened, so **every banking statement above (sections 0, 1.5, 2.3 rows 6-9, 2.5 first bullet, 4.3) is NOT re-checked for v1.0.1**. Logs: `predicate_correctness/output/logs/v4_v101_*.txt`.

### Big changes (these flip a design choice)
1. **There is no "rejected" tool message at v1.0.1.** `ToolMessage` (`data_model/message.py:554-596`) has only `id, role, content, requestor, error, turn_idx, timestamp`. There is no `execution_status` and no validator. `Environment.set_state` (`environment/environment.py:293-420`) replays **every** call whose tool exists and mutates state, and with `strict=True` it raises when the replayed output differs from the recorded one. The orchestrator has no rejected-call precedent (the bundled-terminating-tool code is 2.0-only). Effect: hook option 1 in §1.3 (orchestrator subclass that writes a blocked call plus a fake ToolMessage into the trajectory) is **broken**. In grading, the blocked write would really run in the predicted env and then raise on the content mismatch, and the runner would re-run the whole paid episode up to 3 times. With `strict_replay=False` it would not raise, but the blocked write would land in the predicted DB. **Use the wrapper-agent design (port_map §2.4 option A): blocked attempts never enter the trajectory.**
2. **The communicate judge does not exist.** `evaluator_communicate.py` at v1.0.1 is substring only: the fact, lowercased, must appear in an agent text message, lowercased with commas removed. There is no `CommunicateScoring`, no `semantic_communication.py`, no `--communicate-scorer` / `--communicate-judge`, and no `gpt-5.5` default. COMMUNICATE costs **$0**.
3. **The NL judge is `gpt-4.1-2025-04-14`, temperature 0.0** (`config.py` `DEFAULT_LLM_NL_ASSERTIONS` / `_ARGS`), not gpt-5.4-mini. It makes **one call per task**, with all of the task's assertions in one prompt (`evaluator_nl_assertions.py:121-127`). The reply goes through a bare `json.loads(content)`: no JSON extraction, no response-validation retries. An empty `nl_assertions` list means no call.
4. **No multilingual layer.** These do not exist at v1.0.1: `src/tau2/multilingual/`, `data/tau2/multilingual/` (no English pack, no `retail_tasks_en.json`, no pack personas, no `agent_language_clause`), `data/tau2/multilingual_extensions/`, `data/tau2/task_subsets/` and `src/tau2/task_subsets/`. Also missing: `src/tau2/judges/`, `environment/regional.py`, `domains/*/region.py`, `utils/text_match.py`, `user/guidelines.py` and the `intake` domain. **English retail runs use `tasks.json` (114) directly.** The "50 replaced tasks" statement in §0 is 2.0-only.
5. **No GPT-5 Responses-API bridge.** `generate()` (`utils/llm_utils.py:355-470`) passes the model name unchanged to `litellm.completion` (:409). The §2.1 trap ("a model name starting with gpt-5 is forced through `openai/responses/`") does not exist at v1.0.1. Also gone: xhigh handling, Anthropic adaptive thinking, `response_model` retries and the hand-coded GPT-5.5 price.

### Line-by-line errata
| § | above | at v1.0.1 |
|---|---|---|
| 0, bullet 1 | "This checkout is 2.0.0 … we need tag v1.0.1" | now on v1.0.1. Scores are τ³ 1.x scores: substring COMMUNICATE, gpt-4.1 NL judge, retail = 114 `tasks.json` tasks |
| 0, bullet 2 / 1.3 | `_execute_tool_calls` at `orchestrator.py:327-343` | at `:313-329`, same body (no rejected path) |
| 0, bullet 3 | block = `ToolMessage(..., execution_status="rejected")`; replay skips it (`environment.py:373-378`) | not possible (big change 1) |
| 0, bullet 4 / 2.4 row 4 | airline grading calls a `gpt-5.5` judge per communicate item | airline grading is **$0** (substring) |
| 0, bullet 4 / 2.4 row 5 | retail calls `gpt-5.4-mini`, 112/114 tasks | retail calls **gpt-4.1-2025-04-14**, one call per task, **only when the task's `nl_assertions` is non-empty**. NL_ASSERTION is in the basis for 112/114, but for our 68 tasks only 26 make a call |
| 1.1 | `ToolMessage` :554-608 with `execution_status`; validator :579-584 | :554-596, no such field (big change 1) |
| 1.2 | greeting at :48-50 or `task.agent_opener`; `initialize()` :500-687; `step()` :840-949; precedent :892-914 | greeting `DEFAULT_FIRST_AGENT_MESSAGE` at :47-49, always "Hi! How can I help you today?" (`Task` has no `agent_opener`, there is no `call_context`). `initialize()` :483-665. `step()` :823-900. No precedent |
| 1.3 option 2 | env wrapper works if it sets "rejected" | same problem as option 1: a recorded blocked write is replayed in grading |
| 1.4 | `is_stop` true only for domain-configured stop tools (`llm_agent.py:81-86`, intake `end_call`) | `LLMAgent` has no `is_stop` override, and the base `participant.py:91` returns False. Same effect: the agent never ends the run. There is no `additional_stop_tool_names` and no intake |
| 1.4 | the TRANSFER token comes from `user/guidelines.py:108,190` | it comes from `data/tau2/user_simulator/simulation_guidelines.md` (and `_tools.md`). Tokens are the same: `###STOP###`, `###TRANSFER###`, `###OUT-OF-SCOPE###` (`user_simulator_base.py:51-53`); `UserSimulator.is_stop` is at :183 |
| 1.4 | retries in `runner/progress.py:20-110`, `runner/batch.py:654-666` | same logic: `run_with_retry` (`progress.py:19`) is called at `batch.py:676`, `max_retries` defaults to 3. Grading runs inside it, so **an NL-judge JSON error or a strict-replay mismatch re-runs the whole paid simulation** |
| 2.1 | the gpt-5 Responses trap | gone (big change 5). A custom endpoint `openai/<name>` works with any name |
| 2.1 | released runs use user `openai/gpt-5.5` (`config.py:316-317`) | not in the v1.0.1 config. The defaults are agent and user `gpt-4.1-2025-04-14`, temperature 0.0 |
| 2.1 cost | GPT-5.5 priced by hand; an unknown model costs 0.0 | no hand pricing. An unknown model still logs an error and gives 0.0 (`get_response_cost` :119-131). **New:** `get_cost` (:472-490) returns `None` for both sides if any agent or user message has no cost, so `agent_cost` and `user_cost` become None (2.0 counts the sides separately) |
| 2.1 seed | `runner/batch.py:879-880` | `batch.py:517-518`, same scheme (`random.seed(config.seed)`, `randint` per trial) |
| 2.2 | CLI `extension_for_domain` globs `multilingual_extensions` | does not exist |
| 2.3 | communicate judge, `--communicate-scorer substring`, `multilingual/cli.py` | does not exist; substring is the only scorer |
| 2.3 | NL judge hard-coded, no CLI flag | still true. Monkeypatch `tau2.evaluator.evaluator_nl_assertions.DEFAULT_LLM_NL_ASSERTIONS` and `DEFAULT_LLM_NL_ASSERTIONS_ARGS`; they are module-level names imported from `tau2.config` (:9) |
| 2.3 / 3 | "batch runner default is ALL" | `tau2 run` has **no evaluation-type flag** at all. `run_domain` / `run_tasks` / `run_single_task` / `run_simulation` / `evaluate_trajectories` all default to `EvaluationType.ALL` and take `evaluation_type` only from Python |
| 2.4 rows 11, 12, 17 | hallucination reviewer, voice, `judges/**`, `multilingual/factory/**` | the hallucination reviewer exists (full-duplex only, off for text). `judges/` and `multilingual/` do not exist |
| 2.5 | substring via `CommunicateScoring(scorer=SUBSTRING)`; `run_simulation` checks `communicate_scoring` | not needed, does not exist. `run_simulation(orchestrator, *, evaluation_type, env_kwargs)` (`runner/simulation.py:20-24`) |
| 3 | under `ALL`, COMMUNICATE is evaluated only when in the basis | at v1.0.1 `ALL` **always** computes ENV, ACTION and COMMUNICATE (substring, $0), and NL only if NL_ASSERTION is in the basis or the type is `ALL_WITH_NL_ASSERTIONS`. Only basis components enter the product (`evaluator.py:196-275`). Termination gate (AGENT_STOP / USER_STOP only) at :119-129 |
| 3 | retail "the 50 English replacements are also [DB, NL_ASSERTION]" | there are no replacements at v1.0.1 |
| 3 ACTION | "rejected (blocked) calls still count as matches" | there are no rejected calls. With the wrapper agent, blocked attempts are not in the trajectory and cannot match |
| 4.1 | `TextRunConfig` in `data_model/run_config.py`; `runner/controller.py`, `worker.py`, `--workers`, `--benchmark text`, `--dry-run` | `TextRunConfig` is in `data_model/simulation.py:514`. Runner files: `batch, build, checkpoint, helpers, progress, simulation` only. No `--workers`, no `--benchmark`, no `--language`, no `--dry-run`. `--retrieval-config` exists (cli :374). Official splits are the same (identical `split_tasks.json`) |
| 4.2 | `Info` holds `language_tasks`, `communicate_scoring` | not at v1.0.1 (`Info` :1199; `retrieval_config` is there) |
| 4.3 | the banking reload chain via `multilingual/runtime.py` | that module does not exist. **Banking task loading at v1.0.1 was not re-read** (sealed area); re-check before any banking step |
| 5 | `uv sync`; Python and litellm pins | same pins (`requires-python >=3.12,<3.14`, `litellm>=1.80.15,<1.82.7`). There is no `--dry-run`; a $0 smoke test needs a scripted agent and user, as written |

### Paid call sites in grading at v1.0.1 (airline, retail, text)
| # | where | when | cost |
|---|---|---|---|
| G1 | `evaluator_nl_assertions.py:121-127` `generate(model=gpt-4.1-2025-04-14, temperature 0)` | NL_ASSERTION in the basis **and** non-empty `nl_assertions` (retail: 26 of our 68), or `ALL_WITH_NL_ASSERTIONS*` / `NL_ASSERTIONS` | 1 paid call per task per trial. Cost is not recorded anywhere |
| G2 | `runner/progress.py` `run_with_retry` | any exception in run + grading (bad NL JSON, strict replay mismatch, provider error) | re-runs agent + user + judge, up to 3 more times |
| G3 | `--auto-review` (review judge `claude-opus-4-5`, `DEFAULT_LLM_EVAL_USER_SIMULATOR`; auth classifier) | only if set | off by default |
| — | COMMUNICATE | always under `ALL` | **$0** (substring) |
| — | DB check (fresh env + replay, hash) | always | $0 (airline and retail env builds make no network call) |

### How to grade at $0, or with our own model, at v1.0.1
- **Airline:** default `EvaluationType.ALL` is already $0 (DB + substring COMMUNICATE; NL is not in the basis). Never pick `ALL_WITH_NL_ASSERTIONS*` or `NL_ASSERTIONS`.
- **Retail, $0:** call the Python layer with `evaluation_type=EvaluationType.ENV`. This scores the DB part only, which is all of the reward for the 42 of our 68 tasks with no assertions. Report NL later in a separately approved step. `tau2 run` cannot do this, because it always uses `ALL`.
- **Retail with our own judge model:** before grading, set `tau2.evaluator.evaluator_nl_assertions.DEFAULT_LLM_NL_ASSERTIONS = "openai/<served-name>"` and `DEFAULT_LLM_NL_ASSERTIONS_ARGS = {"api_base": ..., "api_key": ..., "temperature": 0.0}`. The args go as kwargs to `litellm.completion`. Or patch the one seam `tau2.utils.llm_utils.completion`. This is not comparable with the official gpt-4.1 judge. litellm returns cost 0.0 for an unknown model, so count tokens ourselves. Our model must return plain JSON (`{"results":[...]}`), because a non-JSON reply raises and triggers G2.
- **Re-grade saved runs:** `evaluate_simulation(simulation, task, evaluation_type, solo_mode, domain, ...)` takes no scoring arguments at v1.0.1. `scripts/evaluate_trajectories.py` defaults to `ALL`, so for retail it calls G1.
