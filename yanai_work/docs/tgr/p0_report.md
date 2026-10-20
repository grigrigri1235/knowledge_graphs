# Phase 0 report: models and setup (2026-10-19)

Stage: generic improvements over the ShieldAgent baseline. Phase 0, approved 2026-10-19 (plan: `plan.md`;
limitations: `known_limitations.md`).
Data: `output/tgr/p0/` (git-ignored). Scripts: `scripts/tgr/p0_*.py`. New code: `exp_core/`.

## 1. How each model is reached (read from code, the endpoint and ARM; nothing guessed)

| | gpt-6-luna | grok-4.7 |
|---|---|---|
| endpoint | `https://aif-poc-sdc-tiit-trust01.services.ai.azure.com/openai/v1` (the existing resource, `utility/utils.py`) | same |
| deployment name | `gpt-6-luna` (model gpt-6-luna, version 2026-09-22, format OpenAI) | `grok-4.7` (model grok-4.7, version 1, format xAI) |
| SKU / region | GlobalStandard, capacity 7500; Sweden Central | GlobalStandard, capacity 7500; Sweden Central |
| auth | Managed Identity (`ManagedIdentityCredential`, scope `https://ai.azure.com/.default`), same as gpt-5-nano | same |
| API version | OpenAI v1 surface (`/openai/v1`, no `api-version` parameter), Responses and Chat Completions | same |
| rate limits (response headers) | 7.5 M tokens/min, 7,500 requests/min | same |

No configuration file or environment variable mentions either model. The deployments were found via the endpoint's
model list and confirmed by ARM (`Microsoft.CognitiveServices/accounts/aif-poc-sdc-tiit-trust01/deployments`, read with
the VM's managed identity).

## 2. Smoke tests (`scripts/tgr/p0_smoke_models.py`, `p0_probe_extra.py` → `output/tgr/p0/`)

| feature | gpt-6-luna | grok-4.7 |
|---|---|---|
| plain completion (Responses, Chat) | OK, OK | OK, OK |
| JSON-schema structured output, strict (Responses `text.format`, Chat `response_format`) | OK, OK | OK, OK |
| function calling, round trip with tool output (Responses), used by the planner | OK | OK |
| function calling (Chat Completions), used by the τ-bench agent in P6 | **400 unless `reasoning_effort="none"`** ("Function tools with reasoning_effort are not supported … use /v1/responses or set reasoning_effort to 'none'") | OK |
| reasoning effort values | none, low, medium, high, xhigh, max (no `minimal`) | low, medium, high, xhigh (no `minimal`, no `none`) |
| default effort | reasons (≈ low/medium) | reasons heavily: 337 reasoning tokens at `low` for a one-line arithmetic question |
| temperature | rejected on Responses; Chat accepts only the default 1 | accepted (0 and 1) |
| seed | Responses: unknown parameter; Chat: accepted | Responses: unknown parameter; Chat: accepted but **not honoured** (3 calls, seed 7, three different outputs) |
| usage accounting | consistent | Chat `completion_tokens` **excludes** reasoning tokens (1 vs 340); Responses `output_tokens` includes them |

No model is unreachable and no needed feature is missing. Tool calling with reasoning works on both via the Responses
API.

## 3. Prices (Azure Retail Prices API, Sweden Central, GlobalStandard, short-context meters; USD per 1M tokens)

| model | input | cached input | output (incl. reasoning) | long-context meters |
|---|---|---|---|---|
| gpt-6-luna | 0.10 | 0.01 | 0.50 | 0.20 / 0.02 / 0.75 |
| grok-4.7 | 2.00 | 0.50 | 6.00 | 4.00 / 1.00 / 12.00 |
| (gpt-5-nano, P1–P6) | 0.05 | – | 0.40 | |

Grok is 20× luna on input and 12× on output. Our prompts stay far below the long-context thresholds. Azure prompt
caching is automatic: 79–94 % of agent input tokens were cached in the pilot (§6).

## 4. Domain Basic filter

`exp_core/policy_filter.py::drop_sections(text, headings)`. It removes a Markdown section by heading, together with its
subsections, up to the next heading of the same or a higher level. Headings are matched case-insensitively with
whitespace normalised. The heading comes from the caller, never from the code, and every other byte stays unchanged.
Tests are in `tests/exp_core/test_policy_filter.py`. Command used (the outputs are the rule-building inputs for every
method from Phase 1 on; the agent prompt and the Direct guard keep `policy_docs/<domain>_wiki.txt`):

```
python -m exp_core.policy_filter --policy policy_docs/<d>_wiki.txt --drop-heading "Domain Basic" \
       --out output/tgr/policy_input/<d>_wiki.rulebuild.txt      (+ .filter.json: SHA-256 in/out, removed text)
```

**Airline**: `## Domain Basic`, lines 17–27, 753 of 6,155 characters removed (output SHA-256 10233fba…):
> - Each user has a profile containing user id, email, addresses, date of birth, payment methods, reservation numbers, and membership tier.
> - Each reservation has an reservation id, user id, trip type (one way, round trip), flights, passengers, payment methods, created time, baggages, and travel insurance information.
> - Each flight has a flight number, an origin, destination, scheduled departure and arrival time (local time), and for each date:
>   - If the status is "available", the flight has not taken off, available seats and prices are listed.
>   - If the status is "delayed" or "on time", the flight has not taken off, cannot be booked.
>   - If the status is "flying", the flight has taken off but not landed, cannot be booked.

**Retail**: `## Domain basic` (lower-case b, hence the case-insensitive match), lines 19–32, 978 of 5,718 characters removed (output SHA-256 be74a78d…):
> - All times in the database are EST and 24 hour based. For example "02:30:00" means 2:30 AM EST.
> - Each user has a profile of its email, default address, user id, and payment methods. Each payment method is either a gift card, a paypal account, or a credit card.
> - Our retail store has 50 types of products. For each type of product, there are variant items of different options. For example, for a 't shirt' product, there could be an item with option 'color blue size M', and another item with option 'color red size L'.
> - Each product has an unique product id, and each item has an unique item id. They have no relations and should not be confused.
> - Each order can be in status 'pending', 'processed', 'delivered', or 'cancelled'. Generally, you can only take action on pending or delivered orders.
> - Exchange or modify order tools can only be called once. Be sure that all items to be changed are collected into a list before making the tool call!!!

Consequences (reported, not acted on). Three removed sentences are constraints, not descriptions:
- airline: "delayed / on time / flying flights cannot be booked" appears nowhere else in the policy, so rule building no
  longer sees it;
- retail: the order-status constraint is restated per action ("can only be cancelled/modified/returned/exchanged if
  its status is …"), and the modify-once constraint is restated under "Modify items". **"Exchange … can only be called
  once"** survives only as the weaker "remind the customer to confirm they have provided all items to be exchanged";
- this section was also the source of the defective P1 retail rule 32 ("no tool call after the first order tool
  call").

## 5. Per-role model configuration (setup for Phase 1; no existing code edited)

- `exp_core/model_profiles.json`: profiles `luna-dev` and `grok-eval`, each with one entry per role (`rulebuild`,
  `guard`, `agent`, `user`), plus the price table. No model name is hard-coded in code.
- `exp_core/models.py::activate(profile, structured_role)` re-points the three LLM seams of the existing code for one
  process, without editing them:
  1. structured calls: the shared client and deployment, and `LLM.model`, which is part of `LLM.call`'s cache key;
  2. the planner tool loop: a copy of `repro_core.llm.run_tool_loop` with the model as a parameter and in the cache
     key;
  3. τ-bench agent and user simulator: a `litellm.completion` drop-in routed by role.

  The new caches are in `output/tgr/_llmcache/`, apart from the gpt-5-nano caches.
- `exp_core/run_online.py`: the P6 runner with `--profile`, `--aspm-dir` and output in
  `output/tgr/online/<tag>/`. It reuses `repro_online.episode.run_episode` and the existing guards unchanged.
- Tests: `tests/exp_core/test_models.py`. `NoGoldLeakage` now also covers `exp_core/`, and the domain-word check
  covers the filter, as for `repro_core`; `exp_core` otherwise holds the benchmark harness.
- Frozen code check: all 21 files of `repro_core/` and `repro_pipeline/` match tag `repro-p1-v1` (`git hash-object`).
  No P1–P6 result or cache file was touched.

## 6. Cost and runtime estimate: one full train run per model

Method: a measured pilot on train tasks with the real runner. It is cost-only: nothing was tuned, and the grok
outcomes were not inspected.
- luna: 2 tasks per domain × {none, Direct, ShieldAgent};
- grok: 1 task per domain;
- ShieldAgent used the published gpt-5-nano ASPM as a size proxy, because the per-model ASPMs come in Phase 1.

A replay of 11 real P1 calls (same prompts, schema, effort) scales P1:
- luna: same input, 0.25× nano output, 0.28× latency;
- grok: 1.08× input, 0.56× output, about 1× latency.

Per conversation (list price, no cached-input discount, as in P6):

| | luna none | luna Direct | luna Shield | grok none | grok Direct | grok Shield |
|---|---|---|---|---|---|---|
| airline $ | 0.011 | 0.009 | 0.021 | 0.124 | 0.225 | 1.229 |
| retail $ | 0.008 | 0.014 | 0.067 | 0.205 | 0.356 | 0.787 |
| airline s | 145 | 135 | 347 | 82 | 305 | 2,102 |
| retail s | 96 | 271 | 738 | 136 | 375 | 859 |

Full train run = (20 airline + 46 retail tasks) × 3 trials × 3 configurations = 594 conversations:

| | gpt-6-luna | grok-4.7 |
|---|---|---|
| online, list price | **≈ $15** (none $1.8, Direct $2.5, Shield $10.5) | **≈ $280** (none $36, Direct $63, Shield $182) |
| online, with cached-input billing (agent/user only) | ≈ $10 | ≈ $210 |
| P1 rebuild, both domains | ≈ $1 | ≈ $22 |
| wall time (≤ 3 processes, 6–8 workers) | ≈ 4 h (bounded by retail Shield ≈ 3.5 h) | ≈ 6 h (bounded by airline Shield: 35 min per conversation) |
| P1 rebuild wall time | ≈ 20 min per domain | ≈ 1 h per domain |

Uncertainty: with 1–2 pilot conversations per cell, read these as ±50 %. ShieldAgent cost also depends on the size of
the rebuilt ASPM.

**Early warning for Phase 3.** The test split has the same task counts as train (20 + 46), so the three grok
baselines cost about $280 on their own. The three TGR configurations would add about $190–550, depending on whether
TGR's guard costs like Direct or like ShieldAgent. With the rule rebuilds, that totals **≈ $500–850**.

Phase 0 spend: ≈ $3.5. Of this, $3.0 was the grok pilot and $0.3 the luna pilot; the smoke tests and replays were
below $0.3.

## 7. Decisions taken (confirmed by the user 2026-10-19)

| id | decision | reason |
|---|---|---|
| M1 | Agent and user simulator call **the Responses API** for both models (adapter in `exp_core/models.py`); the planner already used it | luna cannot use Chat Completions tools while reasoning. Chat with `effort="none"` would make the dev agent a non-reasoning model, unlike the reasoning eval agent. One API for both models also avoids grok's Chat usage quirk. |
| M2 | Agent and user effort **medium**; guard efforts unchanged (Stage A: aux low, planner medium; Direct medium); rule building as in `repro_core/config.json` (medium) | medium mirrors gpt-5-nano's default in P6, and both models accept it |
| M3 | **No temperature and no seed** for either model | luna rejects any temperature but 1; grok ignores seed. Same settings for dev and eval; reproducibility via caches, as before. |
| M4 | Cost metric = list price without the cached-input discount (as P6); cached tokens are recorded separately | keeps the metric comparable with P6 |
| M5 | The frozen P1 CLI writes the literal `"model": "gpt-5-nano"` into the ASPM `meta` and manifest; the Phase-1 wrapper will correct that label after the run and record the profile | the frozen code cannot be edited |
| M6 | grok-4.7 was used on 2 **train** tasks for this cost pilot only | measured costs instead of guesses; no test task, no tuning |

## 8. Findings

- **P6 user-simulator cost is under-counted.** τ-bench's `LLMUserSimulationEnv` assigns `total_cost` from each call
  instead of adding to it, so P6's per-conversation user cost is the last call's cost. Recorded: $0.33 over 594
  conversations. Estimated with calls × last-call cost: about $2–3, so the P6 total of $20.81 is understated by about
  10–14 %. The guard costs and the Direct vs ShieldAgent comparisons are unaffected. The new runner meters every
  agent and user call itself (`rec["usage_roles"]`). P6 data were not changed; a dated note was added to `p6_report.md` §7.
- grok-4.7's guard is slow: one airline ShieldAgent conversation took 35 min (137 guard LLM calls). The 30-step
  budget and the cap are unchanged, so this is a cost and time issue, not a correctness one.
