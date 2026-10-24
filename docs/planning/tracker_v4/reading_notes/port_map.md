# Port map: v3 guard pipeline (τ-bench v1) -> tracker v4 (τ³-bench, package `tau2`)

Status: reading notes, $0. No code changed, no network, no LLM call. Paths to v3 code are relative to
`predicate_correctness/`. Line numbers are as of 2026-10-23.

**τ³ claims:** checked against the clone `/home/azureuser/code_projects/third_party/tau2-bench` at commit
**cc1df47** (2026-10-22, package `tau2` version 2.0.0). `T2/` below means
`third_party/tau2-bench/src/tau2/`.
- **[VERIFIED file:line]** = read in that code.
- **[UNVERIFIED]** = still from memory, or a plan idea not tested.

**Data purity (what this check read):** only code under `T2/` (never the banking domain code), `pyproject.toml`, and
a file listing of `data/tau2/domains/{retail,airline,telecom}/`. From the retail and airline `split_tasks.json` I read
only the top-level key names (`train`, `test`, `base`), with grep. I never opened a `tasks*.json`, `db.json`,
`policy.md`, any banking path from `banking_seal_paths.txt`, `data/tau2/results`, or `web/leaderboard`.

---------------------------------------------------------------------------------------------------------------------

## 0. The main idea in plain words

v3 does not run τ-bench's own agent loop. It runs a **copy of the partner's loop**
(`from_shieldagent/runner/repro_online/episode.py::run_episode`):
- The loop calls the agent LLM.
- It asks the guard `check()` about each agent turn.
- It then either sends the call to `env.step(action)`, or puts the block message back into the agent's message list.

The guards (frozen TGR, v3 tracker, Direct, Direct + facts) only see **OpenAI-style chat dicts** (`role`, `content`,
`tool_calls[].function.{name,arguments}`, `tool_call_id`). They build their own copy of the database by **replaying
the executed tool calls with τ-bench v1's tool code** on a deep copy of the v1 data files (`state_tracker/state.py`).

So the port has three layers:
1. **Loop and harness glue** (runner, episode loop, task files, user simulator, reward, model routing). This must be
   rewritten for tau2, and it is the biggest part. tau2 owns the loop (`Orchestrator.step`), so the guard has to sit
   in a wrapper agent, or in an Orchestrator subclass (section 2.4).
2. **State replay** (`state.py`, `tau_copy.py`, `tool_table.json`, `tool_check.py`). This must be rebuilt on tau2's
   toolkits and pydantic DB. tau2 already has a replay (`Environment.set_state`), which helps (section 4).
3. **Guard logic** (fact evaluator, rule table, TGR decision, message builder, soft stop, pool, metrics math). This is
   mostly harness-independent. It can be reused if layer 1 gives it the same chat-dict history and layer 2 gives it
   the same `State` API (`db_get`, `db_all`, `shown_get`, `shown_all`, `events_where`, `today`, `pending`).

The domain content (fact files, rule sets, code helpers, question texts, Error-text tables) is tied to the v1 tool
code. It must be re-checked against tau2's retail and airline tools. tau2's tool texts and behaviour do differ
(section 6, T18). Nothing exists yet for telecom, banking_knowledge or intake.

---------------------------------------------------------------------------------------------------------------------

## 1. Environment, Python, launching, resume

| item | v3 fact | ref |
|---|---|---|
| Python for runs | `~/venvs/tau-bench/bin/python -B` (Python **3.12.15**; the venv was made with `--system-site-packages` from `/home/azureuser/miniconda3`) | `~/venvs/tau-bench/pyvenv.cfg`; run_online_v3.py:88 |
| Packages in that venv | `tau_bench 0.1.0`, `litellm 1.57.8`, `openai 1.69.0`, `pydantic 2.10.4`, `pydantic_settings 2.16.0` (azure-identity comes from miniconda's site-packages) | venv site-packages listing |
| τ-bench source | the installed `tau_bench` in the venv (used by `get_env`), plus a read-only copy `from_shieldagent/tau_bench/` of commit `59a200c` (used by the state replay, loaded with stdlib only) | from_shieldagent/PROVENANCE.md:21; state_tracker/tau_copy.py:39 |
| Python for analysis | `/home/azureuser/miniconda3/bin/python3 -B` (metrics, report) | v3_online_metrics.py:68; v3_p14_report.py:280 |
| Env vars | `PYTHONDONTWRITEBYTECODE=1`, `PYTHONHASHSEED=0` (analysis); `LITELLM_LOCAL_MODEL_COST_MAP=True` is set in code | run_online_v3.py:119 |
| Runner copy on sys.path | `guard/runner_path.py::setup()` puts `from_shieldagent/runner/` first, and checks the sha256 of the shared packages `repro_core` and `repro_runtime` against `from_shieldagent/code/` | runner_path.py:32-59 |
| How runs start | no Slurm. Background processes: `setsid nohup ... > output/logs/<log> 2>&1 &`. One process per shard, at most 4 shards ("the VM: at most 4 heavy processes"), `--workers` <= 8 threads per shard | run_online.py:79-81, 134; run_online_v3.py:162-165 |
| stdout rule | a real run refuses to start unless stdout is the log file `output/logs/v3_<step>_<run_id>_s<i>.log` | run_online_v3.py:1364-1367, 513 |
| Run folder | `output/eval_v3/<step>/<run_id>/` holds: `run.json` (made once with an atomic `os.link`; later shards must match the plan and the input sha256), `pids.txt`, `<arm>/episodes_shard<i>of<n>.jsonl` (append only), `dropped_groups_*.jsonl`, `questions/answers_*.jsonl`, `live/shard*.json`, `STOP` | run_online_v3.py:39-52, 1298-1324, 1515-1526 |
| One process per shard | `fcntl.flock` on `<step_dir>/locks/shard<i>of<n>.lock` | run_online_v3.py:1190-1231 |
| Resume | run the same command again. A unit with a line without error is done. A unit with 2 error lines drops its (task, try) group. A group with any line is "open" and finishes, even under a stop. Before a resume, the main chat **copies** (`cp`, never `mv`) the shard files to `*.jsonl.before_resume`. The run refuses if a backup has no live file of at least the same size with the same first bytes. The spend of a backup counts as max(backup, live) | run_online_v3.py:59-64, 1475-1485; soft_stop_v3.py:235-287 |
| Re-run / drop | a failed unit is re-run once, at once (`UNIT_ATTEMPTS = 2`); a second failure drops the group from all 5 arms | run_online_v3.py:163, 1028-1059 |
| Stops | STOP file, per-step hard limit, v3 cap, reserve (p90 cost x units), arm mean cost, one conversation > $0.25, error share / errors in a row, 3rd v3 state error | soft_stop_v3.py:51-76; run_online_v3.py:1575-1582 |
| Safety | `write_guard.install([output/])` audit hook (no write outside `output/`, nothing under `~/ShieldAgent`). The sandbox under `output/eval_v3/dryrun/` blocks the network and uses fake answers. A real run needs approval words | write_guard.py:1-17, 155-170; run_online_v3.py:1353-1367, 1100-1127 |

**tau2 side:**
- Python `>=3.12,<3.14` **[VERIFIED pyproject.toml:11]**. 3.12 matches the current machine Python.
- Dependencies include `litellm>=1.80.15,<1.82.7`, `loguru`, `typer`, `pandas`, `fastapi`, `deepdiff`, `addict`,
  `docstring-parser`, `toml`, `tenacity`, `numpy`, `httpx` **[VERIFIED pyproject.toml:17-37]**. The litellm pin clashes
  with the current venv's 1.57.8. So v4 needs a **separate venv without `--system-site-packages`**. Creating it
  needs approval (outside this agent's write paths).
- The optional extras `voice`, `live`, `knowledge`, `gym` are not needed for text retail / airline
  **[VERIFIED pyproject.toml:39-81]**.
- Data dir: `TAU2_DATA_DIR`, else `<repo>/data` **[VERIFIED T2/utils/utils.py:17-31]**. Domain files sit at
  `DATA_DIR/tau2/domains/<d>/{db.json,policy.md,tasks.json,split_tasks.json}`
  **[VERIFIED T2/domains/retail/utils.py:3-6, airline/utils.py:3-6]**.
- Default batch results go to `DATA_DIR / "simulations" / run_name` **[VERIFIED T2/runner/batch.py:1226]**, which is
  inside the clone. v4 must pass its own `save_to` under `predicate_correctness/output/`, or not use tau2's batch
  runner. Changing `TAU2_DATA_DIR` would also move where the domain data is read from.
- tau2's own resume: `run_tasks(..., save_to, auto_resume=False)` asks "resume? (y/n)" on the console unless
  `auto_resume=True` **[VERIFIED T2/run.py:167-194; T2/runner/checkpoint.py:34-90]**. In a `nohup` run this prompt
  would block, so v4 keeps its own pool / resume (reused from v3).

---------------------------------------------------------------------------------------------------------------------

## 2. How the guard hooks into the agent loop

### 2.1 v3: `from_shieldagent/runner/repro_online/episode.py::run_episode` (copied, unchanged)

Signature: `run_episode(env, agent_completion, tools_info, wiki, guard, task_index, max_num_steps=30, cap=3)`
(episode.py:51-52). It is called by `run_online_v3.py:1540-1544` inside `with router.use(arm)`.

| step | what happens | ref |
|---|---|---|
| reset | `env.reset(task_index=...)` gives the first user message `reset.observation`; `messages = [system: wiki, user: obs]`; `executed = list(messages)` | episode.py:57-60 |
| new episode | `state = guard.new_episode()` (TGR: a `Conversation(trace=[])`; Direct / none: `None`) | episode.py:61; guards.py:27, 97-99 |
| agent call | `agent_completion(messages=..., model="gpt-5-nano", custom_llm_provider="azure", tools=tools_info, temperature=0.0)`. `make_completion` **ignores** `model` and `temperature` (it routes by role) | episode.py:68-69; exp_core/models.py:244-252 |
| parse | `msg = res.choices[0].message.model_dump()`; `action = message_to_action(msg)` (τ-bench v1 gives `Action(name, kwargs)`; a text reply becomes `name="respond", kwargs={"content": ...}`). **Only the first tool call is kept** (`msg["tool_calls"][:1]`) | episode.py:73-76 |
| guard check | `rec = guard.check(state, executed, msg, n_exec)` returns a dict, or `None` (none arm). Inside, `make_step(executed, msg, index)` builds `Step(index, message_index=len(executed), kind, name, arguments, agent_text, None, False, tool_call_id, history=list(executed))` | episode.py:77; guards.py:13-21; taubench_steps.py:19-30 |
| cost | `gcost += rec["usage"]["cost_usd"]`, `rec["usage"]["n_llm_calls"]`, `rec["seconds"]` | episode.py:78-82 |
| block | `blocked = not rec["action_allowed"]`; `override = blocked and consecutive >= cap` (cap 3) | episode.py:83-84 |
| block message to the agent | a blocked tool call: append `msg` plus a **fake tool message** `{"role": "tool", "tool_call_id": tc["id"], "name": ..., "content": feedback}`. A blocked reply: append `msg` plus `{"role": "system", "content": feedback}`. `feedback = rec["feedback_text"]`, or `"BLOCKED by policy guardrail."`. The env is not called and `executed` does not change; the loop runs again | episode.py:88-98 |
| cap override | `guard.commit(state, rec)` (TGR adds the trace position), then the call is executed | episode.py:99-101; runtime.py:146-148 |
| execute | `env_response = env.step(action)`; `reward = env_response.reward`; `info` is merged; the observation is stored on the attempt. A tool call adds a tool message; a reply adds the next user message. Both lists get the 2 new messages; `n_exec += 1`; stop on `env_response.done` | episode.py:102-117 |
| return | `{task_index, reward, done, n_exec_steps, n_blocks, n_cap_overrides, seconds, cost{agent,user,guard}, latency, calls, attempts, messages, executed, reward_info}` | episode.py:119-126 |

There are two message lists: `messages` (what the agent saw, including blocked attempts and feedback) and `executed`
(what really happened; this is the guard's history). Later code relies on this invariant:
`len(messages) == 2 + 2 * len(attempts)` (v3_harm_metric.py:134).

### 2.2 The v3 guard interface (duck-typed, 3 methods)

`new_episode() -> state`, `check(state, executed, msg, index) -> rec | None`, `commit(state, rec) -> None`
(guards.py:24-108). The record must have `action_allowed`, `usage.{cost_usd,n_llm_calls}`, `seconds`, and
`feedback_text` when it blocks.

| arm | class | what check() does | ref |
|---|---|---|---|
| none | `repro_online.guards.NoGuard` | returns `None` | guards.py:24-34 |
| direct | the copy's `DirectGuard`, built by `direct_facts_v3.direct_guard()` (a policy loader, because the copy's `__init__` opens a missing `policy_docs/`) | `repro_runtime.direct.direct(policy, step, effort)`: 1 structured LLM call | guards.py:37-52; direct_facts_v3.py:188-194 |
| direct_facts_v3 | `DirectFactsGuard` | a facts block (code only) plus the same Direct call with the block inserted | direct_facts_v3.py:461-527 |
| tgr_frozen | the copy's `TGRGuard`, via `guard/run_online.py::build_guard("tgr_frozen")` -> `exp_core/run_online.py::build_guard("tgr", ...)` | `TGR.step(conv, step)`: circuit, 1 judge call, MLN decide, feedback C | run_online.py:461-481; runtime.py:65-119 |
| tgr_tracker_v3 | `OnlineTGRv3Guard(TGRGuard)` wrapping `tgr_tracker_v3.build(domain, tools, answers, facts="v3", meaning="tiny", messages="rule")` | `self.tgr.step(state, make_step(...))`, then `finish_v3_check` adds the tiny-question cost; raises `TinyQuestionCallFailed` when a real call fails | run_online_v3.py:729-754, 640-657 |

`TGR.step` retries `_step` 3 times on an exception (`TGRConfig.attempts = 3`, sleeping 10 / 20 s), and cuts the trace
back each time (runtime.py:65-76). Note that two different things are called "attempts": the TGR retry count, and the
episode's `attempts` list (one entry per agent turn).

### 2.3 How tau2's loop works [VERIFIED]

- The `Orchestrator.__init__` signature is `(domain, agent, user, environment, task, max_steps=100, max_errors=10,
  seed=None, solo_mode=False, simulation_id=None, validate_communication=False, timeout=None, call_context=None)`
  **[T2/orchestrator/orchestrator.py:408-418]**.
- `initialize()` calls `environment.set_state(initialization_data, initialization_actions, message_history)` from
  `task.initial_state` **[orchestrator.py:500-540, 307-325]**.
- With no history, the trajectory starts with an **agent** message: `DEFAULT_FIRST_AGENT_MESSAGE = "Hi! How can I help
  you today?"` (or `task.agent_opener`), and the user goes next **[orchestrator.py:48-50, 643-659]**. v1 started with
  the user's message.
- `step()` routes one message at a time **[orchestrator.py:840-949]**:
  - USER/ENV -> AGENT: `agent.generate_next_message(self.message, self.agent_state)` returns
    `(AssistantMessage, state)`; the message is appended to the trajectory; if it is a tool call, it goes to ENV,
    else to USER **[879-918]**.
  - AGENT/USER -> ENV: `_execute_tool_calls(message.tool_calls)` calls `environment.get_response(tool_call)` for
    **every** call (parallel calls are allowed), counts `num_errors` on `ToolMessage.error`, and wraps several
    results in a `MultiToolMessage` **[924-941, 327-357]**.
  - `step_count += 1` for every routed message **[948]**.
  - Termination: `step_count >= max_steps` -> MAX_STEPS; `num_errors >= max_errors` -> TOO_MANY_ERRORS
    **[755-771]**.
- Text **and** tool calls in one message are refused only when `validate_communication=True` (default False)
  **[orchestrator.py:420, 685-686, 738-746]**. The agent prompt says "You cannot do both at the same time"
  **[T2/agent/llm_agent.py:24-32]**.
- The orchestrator already has a "rejected call" concept: `ToolMessage(execution_status="rejected", error=True,
  content=...)`, which is used for bundled terminating calls **[orchestrator.py:892-914;
  T2/data_model/message.py:566-584]**. `set_state` skips rejected calls during replay
  **[T2/environment/environment.py:374-378]**.
- `LLMAgent`:
  - `__init__(tools, domain_policy, llm, llm_args=None, additional_stop_tool_names=frozenset())`
    **[llm_agent.py:61-79]**;
  - state `LLMAgentState(system_messages, messages)` **[44-48]**;
  - `generate_next_message(message, state)` = `_generate_next_message` (append the input to `state.messages`, call
    `generate(model=self.llm, tools=self.tools, messages=system+messages, **llm_args)`) then append the reply
    **[115-145]**;
  - the system prompt is `<instructions>AGENT_INSTRUCTION</instructions><policy>{policy}</policy>` **[24-41]**, not
    v1's plain wiki.
- Registry:
  - `registry.register_agent_factory(factory, name, task_filter=None, metadata=None)`, with factory signature
    `factory(tools, domain_policy, **kwargs)` **[T2/registry.py:112-140]**;
  - `llm_agent` is registered from `create_llm_agent` **[registry.py:302]**;
  - `build_agent` calls the factory with `tools, domain_policy, llm, llm_args, task, audio_native_config,
    audio_taps_dir` **[T2/runner/build.py:100-177]**.
- The domains registered are mock, airline, retail, telecom, telecom-workflow, banking_knowledge and intake
  **[registry.py:318-360]**. retail and airline have task splits **[322-333]**.

### 2.4 The v4 hook: two options (design [UNVERIFIED], building blocks [VERIFIED])

**A. Wrapper agent (recommended).** `GuardedLLMAgent(LLMAgent)` overrides `generate_next_message(message, state)`:
1. generate a message;
2. turn `state.messages` (executed messages only) plus the new message into v1 chat dicts;
3. call the v3 guard's `check()`;
4. on a block, add the attempt and a feedback message to a **private** copy of the messages that the LLM sees (the
   same as v3: a tool message with the same id, or a system note), and generate again (cap 3, then override);
5. return only the allowed message, and keep `state.messages` free of blocked attempts. The orchestrator trajectory
   then equals v3's `executed`, and the attempt log is ours.

Register it with `register_agent_factory`. The orchestrator never sees a blocked call, so `max_errors` and the
evaluator's `set_state` replay are not affected. Parallel calls need a rule: check each call in order and block the
whole message if any call is blocked, or cut to the first call as v3 does. The LLM-visible feedback must be a
`SystemMessage` or a `ToolMessage` placed after the assistant message; `to_litellm_messages` has to accept that
order **[UNVERIFIED: check T2/utils/llm_utils.py:207-268 and validate_message_history 296-302]**.

**B. Orchestrator subclass.** Intercept AGENT -> ENV and answer blocked calls with
`ToolMessage(execution_status="rejected", error=True, content=feedback)` inside the trajectory. This is native to
tau2's replay, but blocked calls then sit in the official trajectory (the communicate judge and the ACTION checks
see them), and blocked replies cannot be handled this way. Not recommended as the main design.

---------------------------------------------------------------------------------------------------------------------

## 3. LLM clients, models, cost

| role | client | model / effort | how cost is counted | ref |
|---|---|---|---|---|
| agent | `exp_core.models.make_completion("agent")`: the OpenAI SDK client from `utility/utils.py` (Azure AI Foundry endpoint `https://aif-poc-sdc-tiit-trust01.services.ai.azure.com/openai/v1`, `ManagedIdentityCredential`), `client.responses.create` (api "responses") or `chat.completions.create` (api "chat"), 5 tries, `max_output_tokens=16000` | profile `luna-dev`: `gpt-6-luna`, api responses, effort medium | `cost(model, input, output)` at the list price from `exp_core/model_profiles.json` (gpt-6-luna: $0.10 input / $0.50 output per 1M tokens; the cached-input discount is NOT used; reasoning tokens bill as output); per-thread `episode_usage()["agent"]`; returned as `_hidden_params.response_cost` | models.py:60-70, 244-305; model_profiles.json; utils.py:9-30 |
| user simulator | the same `make_completion("user")`, put into τ-bench by **monkeypatch**: `tau_bench.envs.user.completion = timed_user_completion(counter.wrap("user", ...))` | gpt-6-luna, responses, effort medium | the same; `usage_roles.user`; it overwrites the episode line's `cost.user` | run_online_v3.py:1431-1436, 1556-1558; episode.py:29-38 |
| guard judge (Direct, Direct + facts, frozen TGR) | `repro_runtime.calls.structured(meter, ...)` -> `policy_pipeline.llm.LLM.call`, cached on disk by the sha256 of system + user + params. `exp_core.models.activate(PROFILE, "guard")` re-points the client and the model. `JudgeRouter` gives each arm its own LLM object and cache folder `output/_llmcache/v3_<run_id>/<arm>/structured` | gpt-6-luna, effort medium (TGR `judge_effort`, DirectGuard `effort`) | `Meter.add` per call, from the cache record's usage; `Meter.summary()["cost_usd"]` at `calls.PRICE` (set to the role model's price by `activate`). **Cache hits are counted at their first price** ("fresh-equivalent"). For error lines, `JudgeMeter` wraps `Meter.add` so the judge cost of failed conversations is kept | calls.py:36-76; models.py:81-110; run_online.py:484-538; run_online_v3.py:660-707 |
| v3 tiny questions | `state_tracker/v3/questions.py::RealBackend` with its own OpenAI client (`make_client`: the same endpoint, read as text from the runner copy; Managed Identity; `max_retries=0`), `responses.create` with a strict JSON schema | `gpt-6-luna`, effort **low** (checked from `questions_v3.json`) | `Budget` at the price in `questions_v3.json`; a failed attempt is charged as if its input was billed. `TinyMeter` wraps `backend.answer` and `budget.spend` per thread. `finish_v3_check` adds the calls and USD to `rec["usage"]`, so the cost is counted once, in the episode line's guard cost | questions.py:636-808; run_online_v3.py:557-657, 710-726 |

The line cost used by every stop and metric is `soft_stop.line_cost(rec)`: the sum of the `rec["cost"]` values (agent
+ user + guard). For an error line it is the costs in `rec["usage_roles"]` (agent, user, plus the `guard_judge` /
`v3_tiny_questions` added for error lines) (soft_stop.py:51-62; run_online_v3.py:1549-1556).

There is also one thrown-away user-simulator call per conversation at `get_env(user_strategy="llm")`. It is kept on
purpose and counted in `usage_roles.user` (run_online.py:48-49, 818-819).

**tau2 side [VERIFIED]:**
- Every LLM call goes through `tau2.utils.llm_utils.generate` -> `_generate_once` -> `litellm.completion(model=...,
  messages=to_litellm_messages(...), tools=[tool.openai_schema], tool_choice="auto", num_retries=3, **kwargs)`
  **[T2/utils/llm_utils.py:15, 516-737]**. This covers the agent **[llm_agent.py:138-144]**, the user simulator
  **[T2/user/user_simulator.py:194]**, and the communicate judge **[T2/evaluator/evaluator_communicate.py:139]**.
  `litellm.drop_params = True` **[llm_utils.py:72]**.
- Tool call arguments are parsed with `json.loads` into dicts **[llm_utils.py:704-711]**.
- Model names starting with `gpt-5` are bridged to `openai/responses/...` **[637-641]**.
- Cost:
  - `get_response_cost` = `litellm.completion_cost(response)`, with a hand-coded special case only for gpt-5.5. On
    any exception it logs and returns **0.0** **[llm_utils.py:126-158]**. So `gpt-6-luna`, which is not in
    litellm's map, would silently cost $0.
  - The cost is stored per message (`AssistantMessage.cost`, `.usage`) **[714-722]** and summed by
    `get_cost(messages)` into `SimulationRun.agent_cost` / `user_cost` **[740-766; orchestrator.py:811, 823-833]**.
- Seam for v4: one monkeypatch of `tau2.utils.llm_utils.completion` (the module global used at line 677), with an
  adapter that returns a litellm `ModelResponse`. It routes the agent, the user simulator and every tau2 judge, so the
  adapter must refuse or route judge calls on purpose. Or register a custom `litellm` provider. Either way, v4 must
  compute cost itself (our list prices) and not trust `message.cost` **[design UNVERIFIED]**.
- The default task LLMs are `gpt-4.1-2025-04-14`. The defaults with paid side effects: **the communicate judge is
  semantic by default** (`CommunicateScoring.scorer = SEMANTIC`, judge model `gpt-5.5`, effort low; one LLM call per
  `communicate_info` fact; no call when a task has none), and the NL-assertion judge is `gpt-5.4-mini`
  **[T2/config.py:26-27, 45-54; T2/data_model/semantic_communication.py:14-86; evaluator_communicate.py:62-140]**.
  v4 should pass `CommunicateScoring(scorer="substring")`. That is $0 and is the original τ-bench rule.

---------------------------------------------------------------------------------------------------------------------

## 4. Tool-code replay on a database copy

### 4.1 v3

Main file: `state_tracker/state.py` (frozen v2 code; its sha256 is in FROZEN_SHA256 at tgr_tracker_v3.py:153).

| piece | how | ref |
|---|---|---|
| tool code and data | `state_tracker/tau_copy.py` loads the **copied** v1 tool modules (`envs/<domain>/tools/__init__.py`, `ALL_TOOLS`) and `data/__init__.py::load_data()` under private module names, with stdlib only. It puts empty `tau_bench` / `tau_bench.envs` packages in `sys.modules` only while loading. It is thread-safe; `preload()` runs in the main thread before the workers start | tau_copy.py:48-138 |
| fresh DB per check | `load_db(domain)`: the v1 data is read once, with a `copy.deepcopy` per call | state.py:72-77 |
| run one call | `run_tool(domain, db, name, args)`: `tools[name].invoke(data=db, **args)`. An exception gives `"Error: <e>"`; an unknown name gives `"Unknown action <name>"` | state.py:139-148 |
| replay | `Tracker.feed(history)`: each tool call is matched to its tool message by `tool_call_id`, then `apply_call` replays it on the DB copy with `deepcopy(args)`. The replayed output is compared with the saved output (**exact string**; JSON equality is also recorded). An event is recorded, and objects from the output go into the `shown` set, parsed with `state_tracker/tool_table.json` | state.py:342-432, 163-217 |
| entry point | `build_state(history, action, domain)` returns a `State` with `db`, `shown`, `shown_meta`, `events`, `today` (parsed from the policy text "The current time is ..."), `pending`, `mismatches`, `parse_problems`, `problems` | state.py:456-469, 230-339 |
| when used | every guard check of tgr_tracker_v3 and direct_facts_v3 rebuilds the state from scratch | tgr_tracker_v3.py:463-493; direct_facts_v3.py:304 |
| trust check | a mismatch, parse problem, state problem or view error is a "state error": every fact takes its blocking value and it is counted. The 3rd state error stops new groups | tgr_tracker_v3.py:475-493, 590-595; run_online_v3.py:164, 792-801 |
| write tool as a label | `state_tracker/v3/tool_check.py::check(state, call)`: deep-copies the DB, runs the pending **write** call with v1 tool code, and maps the first `Error: ...` text to a check in `TOOL_CHECKS` and to facts in `TOOL_FACTS` | tool_check.py:1-53, 270 |
| other direct uses | `message_view._initial_db` (`load_db`, 1350); airline airports via `run_tool(... "list_all_airports")` (1554); `info_classes` policy constants from `tau_copy.policy_text` + `tools_info` (205-206); `feedback_v3.tool_schemas` from `tau_copy.tools_info` (221); `State.db_all("airport")` (state.py:286-288) | as listed |

v1 assumptions baked in:
- the data is a plain dict of dicts;
- tool outputs are `json.dumps` of those dicts, or plain text;
- errors start with `"Error"`;
- every conversation of a domain starts from the same data;
- the airline "current time" comes from the policy text.

### 4.2 tau2 [VERIFIED]

- **Tools**: methods of a `ToolKitBase` subclass, marked `@is_tool(ToolType.READ|WRITE|GENERIC|THINK,
  mutates_state=None)`. `mutates_state` defaults to `tool_type == WRITE` **[T2/environment/toolkit.py:43-91]**.
  `use_tool(name, **kw)` calls the method; an unknown name raises `ValueError("Tool '<name>' not found.")`
  **[toolkit.py:138-142]**.
- **DB**: `DB(BaseModelNoExtra)`, a pydantic model with `load(path)`, `dump`, `get_hash()` **[T2/environment/db.py:8-35]**.
  The toolkit's `get_db_hash()` is `get_dict_hash(db.model_dump())` and `update_db(update_data)` patches the model
  **[toolkit.py:234-245]**.
- **Retail**: `get_environment(db=None, solo_mode=False, policy=None, regional_settings=None)` loads
  `RetailDB.load(RETAIL_DB_PATH)` (or a deep copy of a given db) plus `RetailTools(db, regional_settings)` and
  `policy.md`. Retail refuses solo mode **[T2/domains/retail/environment.py:65-85]**. Airline is the same shape
  **[T2/domains/airline/environment.py:18-36]**.
- **One call**: `Environment.get_response(ToolCall)` runs `make_tool_call(name, requestor, **arguments)` (user tools
  for `requestor="user"`). An exception becomes `"Error: <e>"` with `error=True`. The result is turned into text by
  `to_json_str` (a pydantic model -> `model_dump()` -> `json.dumps(..., default=str)`, no indent; a str stays a str;
  numbers become str) **[T2/environment/environment.py:473-498, 158-185, 420-449]**.
- **Replay**: `Environment.set_state(initialization_data, initialization_actions, message_history, strict=True)`
  **[environment.py:293-418]**. It:
  - applies the task's `initialization_data` (`update_db`) and `initialization_actions`;
  - pairs each tool call with the tool message that follows it, by id (it raises on a mismatch);
  - **skips rejected calls, unknown tools and every non-mutating tool**;
  - re-runs only the mutating tools, and compares their output with the saved output **by JSON value** (not exact
    string). When `strict` is on, a mismatch raises.

  The evaluator uses the same routine to build the predicted DB and the gold DB **[T2/evaluator/evaluator_env.py:63-120]**.
- **Per-task initial state**: `Task.initial_state = InitialState(initialization_data(agent_data, user_data),
  initialization_actions, message_history)` **[T2/data_model/tasks.py:491-525, 586]**. It is applied by the
  orchestrator at start **[orchestrator.py:507-540]**. Whether retail / airline tasks use it was not checked: the
  task files were not opened.
- **Airline current time**: `AirlineTools._get_datetime()` returns `"2024-05-15T15:00:00"`, or
  `regional_settings.current_datetime` when set **[T2/domains/airline/tools.py:155-160]**. It is a tool fact, not
  only policy text.
- **Tool schemas**: built from the method signatures and docstrings (`docstring_parser`, `Tool.openai_schema`)
  **[T2/environment/tool.py:11, 25, 83-140, 185]**. Retail tools can be re-described by regional settings
  **[T2/domains/retail/tools.py:41-56]**. So `tools_sha256` against the v1 rule-set manifests
  (run_online_v3.py:1438-1448) will fail.

**What must be ported:** a v4 `state.py` that gives the same `State` API from tau2. Two ways:
(a) a fresh `get_environment()` plus `set_state(task.initial_state..., executed messages)`, then `db.model_dump()`
into a dict, so the lookup expressions keep using dict access. tau2's replay re-runs only mutating tools, so `shown`
must be parsed from the saved outputs (a new `tool_table.json` for tau2's output shapes), and our exact-replay check
becomes tau2's JSON check (only for writes).
(b) deep-copy the live env's DB at check time. This is cheaper, but there is no replay check.
Way (a) matches v3's "trust check" best **[design UNVERIFIED]**.

---------------------------------------------------------------------------------------------------------------------

## 5. How the event log is built

### 5.1 v3

1. **The guard's event log (inside the state):** `State.events` has one entry per executed tool call in the history:
   `{index, step, tool, args, ok, output, match, json_match, changes_db, tool_call_id}`. `ok = not is_failure(output)`
   (the output starts with "Error" / "Unknown action", or is not a str). `changes_db` comes from `tool_table.json`.
   It is built by `Tracker.apply_call` (state.py:400-432) and read by lookups through `events_where(tool, ok)`
   (state.py:303-306) and by helpers like `looked_up(tool, key, v)` and `first_login_user()` (code_helpers.py:17-20).
   Blocked calls are never in it; cap overrides are.
2. **The episode's attempt log (the record on disk):** `attempts` in `run_episode`, one entry per agent turn:
   `{exec_step, attempt, action, kwargs, agent_text, blocked, cap_override, executed_prefix_len, guard (slim record),
   feedback | observation}` (episode.py:85-106). The runner adds to each line `env, guard, trial, profile, models,
   task_split, arm, task_group, step, run_id, unit_attempt, shard, usage_roles, error` (run_online_v3.py:1556-1562).
   The metrics and the harm replay read `attempts`, `messages`, `executed`, `reward` and `reward_info.actions`.

The v3 guard record adds `rec["v3"] = {version, switches, lazy, facts{name: {value, source, how, sources, parts,
problems, deciding_item}}, unknown, state_errors, fact_errors, questions, standin, message, seconds}` and
`rec["tracker"]` (tgr_tracker_v3.py:645-664, 409-414). Direct + facts adds `rec["direct_facts"]`
(direct_facts_v3.py:505-526).

### 5.2 tau2 [VERIFIED]

- `ToolCall(id, name, arguments: dict, requestor)` **[T2/data_model/message.py:61-72]**.
- `ToolMessage(id, role, content, requestor, error, execution_status, turn_idx, timestamp)` **[554-584]**.
- Assistant and user messages share `content, tool_calls, turn_idx, timestamp, cost, usage, raw_data,
  generation_time_seconds` **[192-218]**. `MultiToolMessage(tool_messages)` **[611-617]**.
- v4's `State.events` can be built from the trajectory directly: `ok = not error` instead of the "Error" prefix, and
  `changes_db` from `toolkit.tool_mutates_state(name)` **[toolkit.py:202-209]**.
- In telecom the **user** also calls tools: the user simulator sets `requestor="user"` on its calls
  **[user_simulator.py:102-113]**, and `Environment.user_tools` exists **[environment.py:39-63, 150-156]**. These calls
  change state the guard never checked. The log must include them, and `events_where` needs a requestor filter.

---------------------------------------------------------------------------------------------------------------------

## 6. Touch points with τ-bench v1 and their tau2 equivalents

| # | v3 touch point | v3 ref | tau2 equivalent | status | port work |
|---|---|---|---|---|---|
| T1 | `get_env(d, user_strategy="llm", ..., task_split, task_index=t)` per unit; probe env with `user_strategy="human"` for `tools_info` and `wiki` | run_online_v3.py:1432, 1439-1444, 1540-1541 | `registry.get_env_constructor(d)()` -> `Environment`; `env.get_policy()`, `env.get_tools()` (Tool objects; `.openai_schema`); tasks via `registry.get_tasks_loader(d)(split)` | VERIFIED registry.py:225-241; environment.py:71-83; tool.py:140 | new builder; tool schemas from tau2; policy from tau2 `policy.md` (not v1 `wiki.md`) |
| T2 | `env.reset(task_index)` -> first user message | episode.py:57-58 | `Orchestrator(...).run()`; the first message is the agent greeting, then the user simulator | VERIFIED orchestrator.py:48-50, 643-659 | the loop moves into tau2; the guard sits in a wrapper agent (2.4) |
| T3 | `env.step(action)` -> observation, reward, done, info | episode.py:102-105 | `environment.get_response(ToolCall)` -> `ToolMessage`; replies go to `UserSimulator.generate_next_message`; reward only at the end via the evaluator | VERIFIED orchestrator.py:327-343, 857-874; environment.py:473-498 | blocked calls must never reach `get_response` |
| T4 | `message_to_action(msg)`, `RESPOND_ACTION_NAME` | episode.py:53-54, 74-76 | `AssistantMessage.is_tool_call()` / `has_text_content()`; both at once is refused only with `validate_communication=True` | VERIFIED message.py:297-317; orchestrator.py:420, 738-746 | a converter from tau2 messages to v1 chat dicts for the guard |
| T5 | only the first tool call per message is kept | episode.py:75-76 | parallel tool calls are generated and all executed (`MultiToolMessage`) | VERIFIED llm_utils.py:703-712; orchestrator.py:931-936, 345-357 | decide: cut to the first call (as v3), or check each call |
| T6 | OpenAI chat dicts; `arguments` is a JSON **string**; tool message `{"role": "tool", "tool_call_id", "name", "content"}` | taubench_steps.py:33-61; state.py:363-387 | pydantic messages; `ToolCall.arguments` is a dict; `ToolMessage.id` = the call id; `requestor` | VERIFIED message.py:61-72, 554-584 | one converter `tau2_to_chat(messages)`; then `Step`, `render_history`, `message_view` and `state` work unchanged |
| T7 | block message: a fake tool message (tool call) or a system message (reply), then the agent is called again | episode.py:88-98 | wrapper `LLMAgent.generate_next_message` regenerates on a private message list; register with `register_agent_factory`. Alternative: `ToolMessage(execution_status="rejected", error=True)` | building blocks VERIFIED llm_agent.py:115-145; registry.py:112-140; message.py:566-584; design UNVERIFIED | new module (the main port); our own attempt log |
| T8 | cap override after 3 blocks in a row | episode.py:84, 99-101 | same logic inside the wrapper | — | port as is |
| T9 | `max_num_steps=30` counts executed env steps only | episode.py:66; run_online_v3.py:161 | `max_steps` counts every routed message (agent, user and env turns); Orchestrator default 100, config default 200; `max_errors` 10 tool errors | VERIFIED orchestrator.py:415-416, 765-770, 948; config.py:4-5 | choose a value; blocked attempts do not reach the orchestrator, so they do not count unless we count them |
| T10 | user simulator: `tau_bench.envs.user.completion` monkeypatched | run_online_v3.py:1431, 1435 | `UserSimulator._generate_next_message` -> `generate(model=self.llm, ...)`; stop tokens STOP / TRANSFER / OUT_OF_SCOPE | VERIFIED user_simulator.py:142-154, 165-226 | patch `tau2.utils.llm_utils.completion` |
| T11 | user cost `env.user.get_total_cost()` | episode.py:118 | `SimulationRun.user_cost` from `get_cost(messages)` | VERIFIED orchestrator.py:811, 831; llm_utils.py:740-766 | compute ourselves (litellm gives 0 for gpt-6-luna) |
| T12 | reward `env_response.reward`; `info["reward_info"]` with `actions`; success = `reward == 1.0` and no error | episode.py:103-104, 126; v3_online_metrics.py:200-202, 490-493 | `evaluate_simulation(simulation, task, evaluation_type, solo_mode, domain, ..., communicate_scoring=...)` -> `RewardInfo(reward, db_check, env_assertions, action_checks, nl_assertions, communicate_checks, reward_basis, reward_breakdown, info)`. **Reward is 0 unless the termination is AGENT_STOP or USER_STOP.** The final reward is the product over `reward_basis`; the default basis is `[DB, COMMUNICATE]`; ACTION is "not used in airline/retail/telecom" | VERIFIED evaluator.py:89-133, 234-283; simulation.py:796-838; tasks.py:237-268 | call the evaluator ourselves, with `CommunicateScoring(scorer="substring")` for $0 |
| T13 | tasks: `tau_bench.envs.<d>.tasks_test.TASKS` / `TASKS_TEST`, `tasks_train.TASKS_TRAIN`; `task.model_dump()`, `task.actions`, `user_id`; tasks by **int index** | run_online_v3.py:230-237, 315-320, 240-269, 323-352 | `Task(id: str, description, user_scenario, ticket, initial_state, evaluation_criteria, issues, required_documents, user_tools, agent_opener)`; `get_tasks(split="base")` from `tasks.json`, split from `split_tasks.json` with keys `train`, `test`, `base` | VERIFIED tasks.py:560-625; retail/environment.py:88-107; airline/environment.py:41-59; key names by grep | new tasks file and new split mapping; the partner's `splits.json` (v1 test indices) does not map to tau2 string ids. The v1-to-tau2 task mapping and the train-66 / val-33 rule need a separate, approved step (data purity) |
| T14 | `kwargs` (v1 `Action.kwargs`) in attempts and expected actions | episode.py:85; v3_online_metrics.py:493, 504, 554 | `Action(action_id, requestor, name, arguments, info, compare_args)`; `compare_with_tool_call` | VERIFIED tasks.py:116-195 | rename in the readers (our own lines may keep `kwargs`) |
| T15 | tool schemas sha vs the rule set manifest `input.tools_sha256` | run_online_v3.py:1444-1448; run_online.py:796-799 | schemas come from docstrings; retail can be re-described by regional settings | VERIFIED tool.py:83-140; retail/tools.py:41-56 | rule sets must be re-checked (or rebuilt in a paid rule-building step) for tau2 tools |
| T16 | policy text equals v1 `wiki.md` (sha checked) | direct_facts_v3.py:102-108, 137-146; run_online_v3.py:1450-1452 | `policy.md` per domain; the agent sees it inside `<policy>` with tau2's AGENT_INSTRUCTION | VERIFIED retail/utils.py:5; llm_agent.py:24-41 | new policy files and hashes; check the airline time (tools.py:155-160) |
| T17 | v1 tool code + data copy for the replay | tau_copy.py; state.py:72-148 | toolkits + pydantic DB; `set_state` replay (writes only, JSON compare) | VERIFIED environment.py:293-418 | rebuild `state.py` (section 4.2) |
| T18 | v1 Error texts (TOOL_CHECKS) and v1 tool behaviour | tool_check.py:77-78, 229-231, 292-309; code_helpers.py:26-56 | tau2 raises `ValueError` with **different texts**: capitalised ("Non-pending order cannot be cancelled", "Insufficient gift card balance to pay for the order"); new checks ("User lookup is ambiguous", "Invalid reason", "There should be exactly one payment for a pending order"); a **changed rule** for returns: "Payment method should be the original payment method" (v1 also allowed a gift card). Airline has a new tool `get_flight_status`; `think` is commented out in both domains | VERIFIED retail/tools.py:210-214, 350, 374, 563, 624, 636, 746, 761, 776; airline/tools.py:587, 790-791 | re-derive TOOL_CHECKS / TOOL_FACTS and re-check every code helper and fact against tau2 code |
| T19 | `transfer_to_human_agents`, the handed-over rule | v3_online_metrics.py:129, 517-520 | the same tool name, a GENERIC tool (not a stop tool for `LLMAgent`; `is_stop` only checks `additional_stop_tool_names`); the user simulator stops on its TRANSFER token | VERIFIED retail/tools.py:776-777; airline/tools.py:602-603; llm_agent.py:81-86; user_simulator.py:142-154 | keep the rule; check how the conversation ends after a transfer |
| T20 | the agent's system prompt = the v1 wiki only | episode.py:59 | `<instructions>` + `<policy>` | VERIFIED llm_agent.py:24-41 | results are not comparable with v1 numbers |
| T21 | the partner's published v1 numbers and saved runs, for reproduction | v3_online_metrics.py:46-59, 941-961 | none for tau2 | — | drop the reproduction block for v4 |
| T22 | (new) unknown tool -> v1 `"Unknown action <name>"` | state.py:144 | `"Error: Tool '<name>' not found."`, `error=True`; the replay skips it as a no-op | VERIFIED toolkit.py:138-142; environment.py:379-392 | update `is_failure` and the event log |

---------------------------------------------------------------------------------------------------------------------

## 7. Module by module

Effort: **S** = small (constants, a converter, hashes), **M** = medium (some functions rewritten, logic kept),
**L** = large (rewrite).

### 7.1 guard/

| module | lines | what it does | τ-bench touch points | LLM / cost | port effort |
|---|---|---|---|---|---|
| `run_online_v3.py` | 1707 | The paid-run wrapper: tasks file, units (task, try, arm), shards, run folder, group pool with re-run / drop, stops, resume, sandbox, B1 check. Builds the 5 arms and calls the copied `run_episode` | T1, T10-T13, T15, T16; `tau_test_tasks` 230-237, `tau_train_tasks` 315-320, `cmd_run` 1431-1452, `run_unit` 1534-1563; reads `attempts[].guard.v3` 792-801 | wires all roles: `models.activate`, `make_completion`, `JudgeRouter`, `JudgeMeter`, `TinyMeter` | **L** for the τ glue (~35 % of the file: tasks, envs, run_unit, model routing). **Reuse as is**: `GroupPool` 921-1092, the shard lock 1190-1231, `write_line` / `write_atomic_json` 881-893, `ensure_run_json` 1298-1324, `plan_units` / `shard_units` / `arm_order` 439-458, `RunFiles` 804-878 (needs the line keys), `install_sandbox` + net recorder 1100-1186, `approval_problem` 547-552, `TinyMeter` 557-619 |
| `tgr_tracker_v3.py` | 785 | The v3 guard `TrackerTGRv3(TrackerTGR, _NoLLMJudge)`: no LLM judge; facts from the one v3 evaluator on the replayed state + message view; lazy tiny questions only where a rule is still undecided; rule-built block messages | indirect only: `build_state` 471, 742; `Step` from `make_step`; `FROZEN_SHA256` lists v1 files 133-160 | none itself; tiny questions go through the answers hook | **S-M**: swap the state builder; regenerate `FROZEN_SHA256` |
| `tgr_tracker.py` | 236 | v2 guard `TrackerTGR(TGR)`: replaces code-type predicate values by v2 lookups; the base class of v3 | `build_state` 160, 225; v1 lookups `lookups_<domain>.json` | judge via TGR (not reached in v3) | **S** if v4 keeps it only as a base class (the `facts="v2"` switch can go); **M** if v2 facts are wanted on tau2 |
| `direct_facts_v3.py` | 552 | Direct + facts: the partner's Direct prompt plus a "Facts checked by code" block (code-only v3 facts; evidence after login) | policy sha = v1 wiki 102-108, 137-146; runner-copy file hashes 110-185; `_state_view` 304 | 1 structured judge call per check (`copy_calls.structured`, stage "direct", effort medium) | **M**: new policy and hashes, state adapter; prompt logic reused |
| `soft_stop_v3.py` | 603 | Spend limits and stop rules, read only: v3 total, step spend, backups, reserve with p90, cost and error stops, STOP file | none (reads episode lines: `cost`, `usage_roles`, `error`, `guard` / `arm`) | counts only | **S**: reuse with new constants (step names, limits, arm names, priors) |
| `feedback_v3.py` | 961 | The block message from the rule table, the fact definitions and the evaluator's results (Not met / What makes it true / closing), with safety rules for database values | `tau_copy.tools_info` for required args 221; fact texts name tools through the fact files | none | **S**: schema source -> tau2 `Tool.openai_schema`; the logic is generic |
| `runner_path.py` | 59 | Makes the copied runner importable without editing it | none | — | **reuse as is** (if the TGR runtime copy is kept) |
| `write_guard.py` | 174 | Audit hook: writes only under `output/`, nothing under `~/ShieldAgent` | none | — | **reuse as is**. tau2 writes LLM logs only when a log dir is set (`set_llm_log_dir`, llm_utils.py:304) and results only to `save_to` / `DATA_DIR/simulations`; both must point under `output/` |
| (runner copy) `repro_online/episode.py` | 126 | the loop of section 2.1 | T2-T9, T11, T12 | agent cost | **replaced** by the tau2 wrapper agent + our attempt log (new code, **L**) |
| (runner copy) `exp_core/models.py` | 305 | role routing to Azure Foundry; cost per role | none (a pure client) | all roles | **reuse**, plus a litellm `ModelResponse` adapter for the `tau2.utils.llm_utils.completion` seam (**M**) |
| (runner copy) `method_tgr/*`, `repro_runtime/{mln,calls,shield,direct,prompts}` | ~700 | TGR decision, MLN, feedback C, Direct | `Step`, `render_history` on chat dicts | judge | **reuse as is** behind the chat-dict converter |

### 7.2 state_tracker/v3/

| module | lines | what it does | τ-bench touch points | port effort |
|---|---|---|---|---|
| `facts_format_v3.py` | 1189 | The one fact evaluator (parts with sources database / event / arguments / structure / question; `combine` AND / OR / NOT; blocking values; problems) and the fact-file validator | none directly; runs on the `State` API through `replay.RecordingState` (758) | **reuse as is** if the State API is kept |
| `code_helpers.py` | 291 | Extra helper names for fact expressions: `looked_up`, `first_login_user`, `owner_of`, `user_id_by_email`, `price_difference`, `cabin_now`, `flight_on_date`, `today_minus_hours`, `bags_right`, ... | 17 v1 tool-name mentions; mirrors v1 tool behaviour (rounding, cabin never updated, email lower case) 26-56 | **M**: re-check each helper against tau2 tool code (tau2 lookups can be "ambiguous": retail/tools.py:350, 374) |
| `questions.py` | 1776 | Tiny yes / no questions (K1-K16): rendering, quote check, cache key, stores, Fake / Saved / Real backends, budget, network block | 54 tool-name mentions (`RETAIL_PHRASE`, `AIRLINE_PHRASE`, `render_action`, `render_listing`, `trip_text`) 1117-1443; domain texts in `questions_v3.json` | **S-M**: client and budget reusable; per-tool rendering re-checked for tau2 argument names (and `get_flight_status`) |
| `info_classes.py` | 467 | For each id / amount in a text: user_typed, call_argument, policy_constant, catalog, db_user (disclosure facts, safe evidence lines) | `tau_copy.policy_text` + `tools_info` 205-206; v1 table names; airline branch 136, 236 | **M** |
| `message_view.py` | 1765 | The view of the executed history (user / agent / tool entries, normalized text), structure helpers, screens | chat-dict history 406-418; `pending["args" / "kwargs"]` 325; `load_db` 1350; `run_tool("list_all_airports")` 1554; retail id regex 1118, 1184 | **S-M** behind the converter. Note that the tau2 trajectory starts with an agent greeting (orchestrator.py:48-50); some structure helpers may assume the first entry is the user |
| `tool_check.py` | 363 | τ-bench's own write tool on a DB copy as an objective label (first Error text -> check -> facts) | `S.run_tool` 270; v1 Error texts and tool order 77-78, 229-231 | **M-L**: rebuild TOOL_CHECKS / TOOL_FACTS from tau2 code (texts differ: T18) |
| `rule_table.py` | 306 | For every TGR rule and fact combination: does it hold?, smallest flip sets, blocking values | none (reads the rule set only; generic by design) | **reuse as is** |
| `frozen.py` | 341 | sha256 manifest of eval v2 data + method files; `check_manifest()` at every v3 start | lists `state_tracker/tau_copy.py` etc. 60 | **S**: reuse the code; v4 needs its own manifest (freeze v3 + v2) |
| data: `facts_v3_<domain>.json`, `questions_v3.json`, `output/eval_v3/rule_table_<domain>.json`, `state_tracker/tool_table.json`, `from_shieldagent/rules/<domain>/rule_set.json` | — | the domain content | all bound to v1 tool names, arguments and data fields | **M-L** per domain: re-validate on tau2 retail / airline. **New** for telecom / banking_knowledge / intake (no rules or facts yet: a paid rule build plus new fact files) |

### 7.3 scoring/

| module | lines | what it does | τ-bench touch points | port effort |
|---|---|---|---|---|
| `v3_online_metrics.py` | 1201 | Pre-registered metrics: paired stratified bootstrap (v3 - frozen TGR, margin -0.10), S1 / S2, refusal tasks, safety (allowed writes refused by a tool check mapped to a fact), expected actions, rule broken, guard metrics, power, partner reproduction | `reward`, `error`, `reward_info.actions[name, kwargs]` 490-493; `attempts[action, kwargs, blocked, cap_override, observation, guard]` 473-569; int task ids + `splits.json` 152-159, 234-249; `tool_check` 482-510; published v1 numbers 941-961 | **M**: the bootstrap, pairing and power code are reusable; the record readers must be rewritten for the v4 line schema and tau2 `RewardInfo`; expected writes come from `task.evaluation_criteria.actions`; drop the partner block |
| `v3_harm_metric.py` | 567 | Harm metric: accepted unwanted writes (outcome view) and writes broken for sure by v3 rules + code facts (rules view, a $0 offline replay of every attempt) | `len(messages) == 2 + 2 * len(attempts)` 134; `fork/offline_v3.run_guard` 141; `executed_prefix_len` 139; `tau_bench.envs.user` patch in safety() 83-84 | **M**: depends on the v4 attempt log layout |
| `v3_p14_report.py` | 687 | The after-run report: markdown + 2 figures, verdicts, spend vs limits, warnings, TEST mode | none directly (works through the metrics); constants for 99 tasks / val 33 / train 66 and arm cost priors 70-72 | **S-M** |

### 7.4 tests/test_v3_*.py (skimmed)

About 800 tests in 20 files. Most build tiny conversations with **v1 tool outputs** (`state.run_tool` on the v1 data
copy): test_v3_code_facts, _message_view, _structure_facts, _feedback, _tool_check, _questions, _guard. These are
v1-bound and need tau2 fixtures. The tests that can move nearly as they are: test_v3_rule_table, test_v3_facts_format
(evaluator / validator parts), test_v3_soft_stop, the pool / shard / stop parts of test_v3_run_online, the bootstrap
parts of test_v3_online_metrics, and test_v3_frozen (as a pattern). Venv-only tests use `skipUnless(HAVE_TAU)`
(test_v3_b3.py:94; test_v3_run_online.py:100, 500, 701); test_v3_run_online.py:907-908 imports `tau_bench.envs`
directly.

---------------------------------------------------------------------------------------------------------------------

## 8. Reusable as is (harness-independent)

- `state_tracker/v3/facts_format_v3.py` (the evaluator), `state_tracker/v3/rule_table.py`,
  `state_tracker/lookup_format.py` (the frozen expression format), `state_tracker/replay.py::RecordingState`.
- The runner copy's TGR core: `method_tgr/runtime.py`, `method_tgr/feedback.py`, `method_tgr/rules.py`,
  `repro_runtime/mln.py`, `repro_runtime/verify.py`, `repro_runtime/calls.py` (Meter, cache),
  `repro_core/taubench_steps.py` (`Step` and `render_history` work on chat dicts), plus `guard/runner_path.py`.
- `guard/write_guard.py`, and `guard/soft_stop.py` + `guard/soft_stop_v3.py` (only the constants change).
- From `guard/run_online_v3.py`: `GroupPool`, the shard lock, the run.json identity check, atomic writes, units /
  shards, the sandbox audit hooks, `TinyMeter`, the approval check.
- `state_tracker/v3/questions.py`: backends, store, budget, network block (the rendering of tool calls needs a check).
- `exp_core/models.py`: role routing and cost (it needs the litellm-shaped adapter).
- From scoring: the bootstrap, pairing, power and report rendering functions.

These hold only if v4 gives them three things:
1. the executed history as v1-style chat dicts;
2. a `State` object with the same API;
3. episode lines with the same keys (`attempts`, `cost`, `usage_roles`, `error`, `guard` / `arm`, `trial`, a task key).

---------------------------------------------------------------------------------------------------------------------

## 9. Effort summary

| area | effort | why |
|---|---|---|
| tau2 wrapper agent (guard hook, block message, cap, attempt log) + the converter from tau2 messages to chat dicts | L | replaces `run_episode`; the core of the port |
| model routing (patch `tau2.utils.llm_utils.completion`), our own cost per role, the gpt-6-luna price; `CommunicateScoring(substring)` | M | tau2 gives $0 for unknown models and calls a gpt-5.5 judge by default |
| runner v4 (tasks file with string ids, split mapping, envs, evaluator call, line schema) on top of the reused pool / stops / resume | M-L | about a third of run_online_v3.py is τ glue |
| state on tau2 (`State` API from the pydantic DB, replay via `set_state` + `shown` parsing, a new tool_table) | M | tau2's replay re-runs only writes and compares JSON |
| domain content re-check for retail + airline (rule sets vs tau2 tools, fact files, code helpers, Error texts, question rendering, info classes, policy / time) | M-L | tau2 changed texts and some rules (T18) |
| telecom / banking_knowledge / intake | L | nothing exists: rules (a paid build), facts, questions; user-side tools; banking is sealed |
| scoring for tau2 `RewardInfo` and the new line schema | M | the readers change, the math stays |
| tests: tau2 fixtures for the v1-bound suites | M-L | most fact tests build v1 tool outputs |
| guard logic, evaluator, rule table, soft stop, write guard | S / reuse | harness-independent |

---------------------------------------------------------------------------------------------------------------------

## 10. Open questions

Answered at cc1df47 (see sections 2.3, 3, 4.2, 5.2 and 6):
- the loop and parallel calls (T5);
- mixed messages (T4);
- the agent hook and the registry (2.3);
- the `set_state` behaviour (4.2);
- tool output serialization and errors (4.2, T22);
- splits (T13; key names only);
- `max_steps` / `max_errors` (T9);
- transfer (T19);
- the results dir and resume (1);
- the litellm cost for unknown models (3);
- the Python and litellm pins (1);
- what τ³ adds: new domains banking_knowledge, intake, mock; voice / full-duplex; multilingual and regional settings
  (`T2/domains/`, `T2/multilingual/`, `T2/orchestrator/full_duplex_orchestrator.py`).

Still open (check when a plan step needs them):
1. Does `to_litellm_messages` / `validate_message_history` accept our private feedback messages (a system note after
   an assistant message; a tool message for a blocked call)? (llm_utils.py:207-302, not read in full)
2. Do retail / airline tasks use `initial_state` or `agent_opener`? This needs opening tasks.json, which belongs to a
   separate, approved, train-only step (data purity).
3. Which retail / airline tasks have COMMUNICATE in `reward_basis`, and is substring scoring the right $0 choice?
   (The same data-purity rule applies.)
4. How is the v1 task index mapped to tau2 task ids, and how is train 66 / val 33 kept apart there?
5. What does `regional_settings` / `localize_db` (config.py:15 `DEFAULT_LOCALIZE_DB = True`) change for English text
   runs? The DB or tool descriptions may change by default; check `T2/runner/build.py:535-570` and
   `T2/environment/regional.py`.
6. How does the tau2 airline / retail DB shape (pydantic field names) compare with the v1 dict layout the fact
   expressions read (`T2/domains/*/data_model.py`, not read yet)?

---

## Errata for v1.0.1

Checked 2026-10-23, $0, read only, at tag **v1.0.1** (fc0055d, `tau2` version 1.0.1, τ³-bench, the version we use). The **[VERIFIED]** marks above refer to cc1df47 (2.0.0). Method: `git diff v1.0.1 v2.0.0` plus `git show v1.0.1:<path>`. Logs: `predicate_correctness/output/logs/v4_v101_*.txt`.

What still holds: section 0, the v3 side of every table, the 3-layer port plan, the wrapper-agent design (§2.4 A), the State-API idea (§4.2 way a), the `set_state` pairing and JSON compare, the tool output serialization (`to_json_str`), `"Error: <e>"` with `error=True`, toolkit/`is_tool`/`mutates_state`, the litellm pin, Python 3.12, `load_dotenv` at import, and the retail/airline data paths. Line numbers in `T2/` differ at v1.0.1.

### Statements that change at v1.0.1
| where | above | at v1.0.1 |
|---|---|---|
| header | cc1df47, version 2.0.0 | v1.0.1, version "1.0.1" (`pyproject.toml:7`) |
| §2.3 / §2.4 B / T7 | the orchestrator has a "rejected call" concept; `set_state` skips rejected calls (`environment.py:374-378`) | **no such concept**: `ToolMessage` has no `execution_status` (`message.py:554-596`), and `set_state` replays every recorded mutating call (`environment.py:369-420`). **Option B is not usable.** Option A (wrapper agent) is the only clean hook |
| §2.3 | `Orchestrator.__init__(…, timeout=None, call_context=None)`; first message may be `task.agent_opener` | no `call_context`, no `agent_opener`; the greeting is always "Hi! How can I help you today?" (`orchestrator.py:47-49, 626-638`) |
| §2.3 | `LLMAgent.__init__(…, additional_stop_tool_names=frozenset())` | `__init__(tools, domain_policy, llm, llm_args=None)` only (`llm_agent.py:61-76`) |
| §2.3 | domains include `intake` | registered domains: mock, airline, retail, telecom (+ workflow / full / small task sets), banking_knowledge (`registry.py:313-348`) |
| §3 tau2 side | `_generate_once`, lines 516-737; gpt-5 → `openai/responses/…` bridge (637-641); GPT-5.5 hand price | one `generate()` at `llm_utils.py:355-470`, `completion(model=model, …)` at :409. **No Responses bridge, no hand price**; `get_response_cost` :119-131 (unknown model → 0.0) |
| §3 tau2 side | "the communicate judge is semantic by default (gpt-5.5) … v4 should pass `CommunicateScoring(scorer="substring")`" | **wrong at v1.0.1**: COMMUNICATE is substring only and $0. `CommunicateScoring` does not exist, so there is nothing to pass |
| §3 tau2 side | NL judge `gpt-5.4-mini` | **`gpt-4.1-2025-04-14`, temperature 0.0**, one call per task (all assertions in one prompt). Only for tasks with non-empty `nl_assertions` when NL_ASSERTION is in the basis (retail) |
| §3 tau2 side | `get_cost` sums per message | returns **None for both sides** if any agent or user message lacks a cost (`llm_utils.py:472-490`). Our own meter must not rely on it |
| §3 seam | patch `tau2.utils.llm_utils.completion` routes agent, user and judges | still true at v1.0.1. The seam is `completion` at :409; the NL judge also goes through it |
| §4.2 | retail tools can be re-described by regional settings (`retail/tools.py:41-56`) | no regional settings at v1.0.1. Tool schemas come only from signatures + docstrings (the tools_sha256 gate still fails) |
| §4.2 | `get_environment(db=None, solo_mode=False, policy=None, regional_settings=None)`; a given db is deep-copied | `get_environment(db=None, solo_mode=False)` only. A passed `db` is used **as is (no deep copy)**. Policy is always read from `policy.md` |
| §4.2 | airline time: `regional_settings.current_datetime` when set | always `"2024-05-15T15:00:00"` |
| T12 | `evaluate_simulation(…, communicate_scoring=…)`; "call the evaluator with CommunicateScoring(substring) for $0" | `evaluate_simulation(simulation, task, evaluation_type, solo_mode, domain, mode, env_kwargs, strict_replay)`. Under `ALL`, airline is $0 by default; retail calls the gpt-4.1 NL judge for tasks with assertions, so use `EvaluationType.ENV` for $0 (see tau3_harness errata) |
| T18 | new check "User lookup is ambiguous" (`retail/tools.py:350, 374`) | not at v1.0.1 (first match wins, `.lower()` compare). The other T18 texts are the same |
| §6 T5 / T9 / T10 / T19 line refs | `orchestrator.py:931-936, 765-770, 948`; `user_simulator.py:142-154` | v1.0.1: tool step :882-892, limits :744-749, `step_count` :899, `UserSimulator.is_stop` :183. Same logic |
| §1 tau2 resume | `run.py:167-194` | `auto_resume` parameter at `run.py:194` (same idea) |
| §10 open 3 | which tasks have COMMUNICATE | answered: airline 50/50 `[DB, COMMUNICATE]` (4 of our 30 have facts); retail none |
| §10 open 2 | `initial_state` / `agent_opener` | `agent_opener` does not exist at v1.0.1. `initial_state` and `persona` are empty in all 50 airline and all 114 retail tasks (count only) |
| §10 open 4 | v1 → tau2 id map | done: `airline_task_map_v101.json` (30 ours: train 20, val 10) and `retail_task_map_v101.json` (68 ours: train 45, val 23; τ³ 93 dropped as a duplicate of partner-test content) |
| §10 open 5 | `regional_settings` / `DEFAULT_LOCALIZE_DB` | moot: neither exists at v1.0.1 |
