> **Note (2026-10-17 cleanup):** items mentioned below were moved: `README.md` (authors') → `archive/authors_code/README_authors.md`; `project_structure.md` → `archive/early_setup/`; `visualize_policy_graph.py`, `retail_policy_graph.html` and `lib/` → `archive/autopolicy_early/visualization/`; `output/curated/` → `archive/step1_gold_standard/data/output_curated/`. See `docs/cleanup/cleanup_log.md`.

# Azure OpenAI Managed Identity Migration Plan

## Context & Objectives
Refactor the `ShieldAgent` codebase to replace standard OpenAI API client initializations with Azure OpenAI using Managed Identity authentication (`ManagedIdentityCredential` and `get_bearer_token_provider`). Update model references from OpenAI models (such as `"gpt-4"`, `"gpt-4o"`) to the Azure deployment `"gpt-5-nano"`, and update API call structures and response parsing from `chat.completions.create` / `response.choices[0].message.content` to `responses.create` / `response.output_text`.

Azure Configuration:
- Endpoint: `https://aif-poc-sdc-tiit-trust01.services.ai.azure.com/openai/v1`
- Deployment name: `gpt-5-nano`
- Token scope: `https://ai.azure.com/.default`

---

## Detailed Step-by-Step Implementation Breakdown

### Part 1: Update `utility/utils.py`
- Add imports: `from azure.identity import ManagedIdentityCredential, get_bearer_token_provider`.
- Define Azure deployment variables (`endpoint`, `deployment_name`, `credential`, `token_provider`, default client).
- Refactor `chat_text`:
  - When model is `"gpt-5-nano"` or `"openai"` / `"gpt"`:
    - Invoke `client.responses.create(model=deployment_name, input=...)`.
    - Extract result via `response.output_text`.

### Part 2: Update `agent/utils.py`
- Mirror changes from `utility/utils.py`:
  - Add imports and Azure Managed Identity configuration.
  - Refactor `chat_text` to use `responses.create` and parse `response.output_text`.

### Part 3: Update `utility/policy_server.py`
- Add imports: `from azure.identity import ManagedIdentityCredential, get_bearer_token_provider`.
- Configure Azure credentials and token provider.
- Replace `openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))` around line 1507 with Managed Identity initialization.
- Safely initialize `anthropic_client` (only if `ANTHROPIC_API_KEY` is present in the environment) to avoid initialization crashes.
- Update tools (`analyze_document_section`, `extract_policies_from_file`, `extract_rules_from_policies`, `refine_and_categorize_rules`) to default to `deployment_name` (`"gpt-5-nano"`) and `openai_client`.

### Part 4: Update `policy_extractor_async.py` (Root)
- Add Azure Managed Identity imports and configuration.
- Replace `self.openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))` (line 123) with Managed Identity initialization.
- Safely initialize `self.anthropic_client`.
- Update `--model` CLI argument help string and default model configurations to use `"gpt-5-nano"`.

### Part 5: Update `agent/policy_construction/rule_extractor.py`
- Replace direct `openai` module usage with `from openai import OpenAI` and Azure Managed Identity.
- Replace `model="gpt-4o"` with `deployment_name = "gpt-5-nano"`.
- In `query_openai`: Replace `openai.chat.completions.create(...)` and `response.choices[0].message.content` with `client.responses.create(model=deployment_name, input=messages)` and `return response.output_text`.

### Part 6: Update `agent/tools/policy_extraction.py`
- Add Azure Managed Identity imports.
- Replace `openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))` (line 1208) with Managed Identity initialization.
- Safely initialize `anthropic_client`.
- Ensure tool calls route to `openai_client` with `gpt-5-nano` when appropriate.

### Part 7: Update `agent/tools/certification.py`
- Add Azure Managed Identity imports.
- Replace `openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))` (line 316) with Managed Identity initialization.
- Safely initialize `anthropic_client`.

### Part 8: Update `agent/tools/content_moderation.py`
- Add Azure Managed Identity imports.
- Replace `openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))` (line 193) with Managed Identity initialization.
- Safely initialize `anthropic_client`.

### Part 9: Update `agent/tools/aspm_tool.py`
- Add Azure Managed Identity imports.
- Replace `openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))` (line 516) with Managed Identity initialization.
- Safely initialize `anthropic_client`.

### Part 10: Update `agent/policy_construction/utility.py`
- Add Azure Managed Identity imports.
- Replace `openai_client = OpenAI(...)` at line 43 and line 700 with Managed Identity initialization.
- Safely initialize `anthropic_client`.

### Part 11: Update `agent/policy_construction/policy_extractor_async.py` & `policy_extractor_non_async.py`
- Add Azure Managed Identity imports and replace `self.openai_client` initialization in `__init__`.
- Update CLI argument `--model` help text referencing `"gpt-4o"` to `"gpt-5-nano"`.

### Part 12: Update `agent/agent.py`, `agent/run_inference.py`, and `app.py`
- In `agent/agent.py`: update default `model: str = "gpt-5-nano"`.
- In `agent/run_inference.py`: update `model="gpt-5-nano"`.
- In `app.py`: update `MODELS` list to replace `"gpt-4o"` with `"gpt-5-nano"`.

### Part 13: Verification & Execution Testing
- Run test command with output redirected to a file:
  `python policy_extractor_async.py -d ./policy_docs/airline_wiki.txt -t txt -org "TauBench" -er > test_run.log 2>&1`
- Verify that `policy_server.py` and `policy_extractor_async.py` start and authenticate successfully without `OpenAIError`.
