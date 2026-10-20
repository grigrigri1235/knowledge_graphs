> **Note (2026-10-17 cleanup):** items mentioned below were moved: `README.md` (authors') → `archive/authors_code/README_authors.md`; `project_structure.md` → `archive/early_setup/`; `visualize_policy_graph.py`, `retail_policy_graph.html` and `lib/` → `archive/autopolicy_early/visualization/`; `output/curated/` → `archive/step1_gold_standard/data/output_curated/`. See `docs/cleanup/cleanup_log.md`.

# Orientation summary (Step 0)

Date: 2026-10-14. Scope: repo state before Step 1 (rule audit). Read-only. Nothing under `output/deep_policy/` was changed.

## Repository layout

| Path | Role | Status |
|---|---|---|
| `policy_extractor_async.py`, `utility/` | Offline extraction: CLI and MCP server (`policy_server.py`), plus helpers (`utils.py`). | **Live.** This produced the τ-bench outputs. |
| `app.py` | Gradio UI over the extractor. | Live, but still asks for OpenAI/Anthropic keys (`app.py:41-46`), so it is not Azure-aligned. |
| `agent/` | Runtime guardrail (`ShieldAgent`, MCP tools in `agent/tools/`). | **Canonical** runtime code. Skeleton only; see the brief, §2. |
| `shield` | **Symlink → `agent/`**, not a copy. It exists because `agent/*.py` imports `shield.*`. It is untracked in git. | Alias of `agent/`. |
| `agent/policy_construction/` | Older and alternative extractors, plus the unwired LTL `rule_extractor.py`. | Legacy. |
| `agent/lib/` | LADR/Prover9 sources. `mcp-logic/`, `pyModelChecking/` and `stormpy/` are **empty**. | Unused. |
| `lib/` (root; archived at `archive/autopolicy_early/visualization/lib/`) | JS assets (vis-network, tom-select) for `retail_policy_graph.html`. Not logic libraries. | Support for the HTML graph. |
| `policy_docs/` | Inputs. `airline_wiki.txt` and `retail_wiki.txt` are **byte-identical to upstream τ-bench `wiki.md`** (checked against sierra-research/tau-bench @ `59a200c`). | Inputs. |
| `output/deep_policy/` | Extraction runs. **Ignored by git (`.gitignore: output/*`)**. Curated Step 1 artifacts first went to `output/curated/` (now `archive/step1_gold_standard/data/output_curated/`) and now live in the tracked `policies/curated/` (moved at Step 1 close-out). | Data. |
| `docs/planning/` | Refactor/cleanup plans. `cleanup_run.log` is **empty**, so the cleanup actions were not logged. | Docs. |

## LLM configuration (no secrets printed)
- Azure OpenAI v1 endpoint with deployment `gpt-5-nano`, authenticated through **Managed Identity** (`ManagedIdentityCredential` + `get_bearer_token_provider`, scope `https://ai.azure.com/.default`). There is no API key. The endpoint and deployment are **hard-coded** in each module: `utility/utils.py:9-31`, `agent/utils.py`, `utility/policy_server.py:34-51`, `policy_extractor_async.py:32-37`, and the legacy extractors.
- The helper is `chat_text(prompt, system, model, client)` in `utility/utils.py:91` (mirrored in `agent/utils.py`). It calls `client.responses.create(model=deployment_name, input=...)` and returns `response.output_text`. `max_tokens` and `temperature` are **ignored** on the Azure path.
- `policy_server.py:54`: the model can be overridden through the env var `POLICY_MODEL`. Anthropic is used only if `ANTHROPIC_API_KEY` is set.
- **Gap:** `agent/agent.py:21-30` uses the `openai-agents` SDK (`Agent(model="gpt-5-nano")`) with `set_default_openai_key(OPENAI_API_KEY)`. That is the public OpenAI client, not Azure. The runtime planner is therefore **not** wired to Azure (relevant for Step 3).

## Extraction outputs

| | Airline (`extraction_20261012_112735`, org `TauBench`) | Retail (`extraction_20261012_120408`, org `TauBench_Retail`) |
|---|---|---|
| Policies | 23 (ids 0–22, unique) | 18 (ids 0–17, unique) |
| Raw rules | 48 | 26 |
| Risk categories | 7 | 5 |
| Refined rules | 49 (49 unique texts) | **104, but only 57 unique texts.** 47 are verbatim duplicates: one category ("Identity, Access Control…", 55 rules) absorbed nearly everything, and three other categories repeat it. |
| `target_subject` | **`"User"`**. Not recorded in the outputs; inferred from shell history (no `-ts` flag, CLI default `User`). No `-org-desc` was given either. | same |
| Model | `gpt-5-nano`. Not recorded in the outputs; inferred from CLI default and code. | same |

`extraction_20261012_112151` is a **failed airline run**: 0 policies, 0.13 s, only a report and a document tree. It is superseded by 112735 and can be ignored.

**Structural problems**
- `*_policy_rule_mapping.json` maps policy index → **refined** rule ids, not raw ids. Checked: it is fully consistent with the refined `source_policy_ids`. It *looks* broken if you read it as raw ids (e.g. airline maps to "49", but there are only 48 raw rules).
- In every raw rule, `source_policies` is empty. `source_policy_idx` carries the link.
- `*_document_tree.json` has `children: []` and `policies_count: 0`, although the report says 23 and 18 policies were extracted. The tree is not populated.
- Airline: no policy was extracted from "Domain Basic", so the flight-status rule "cannot be booked" is lost. Refined R35 duplicates R20 (both come from raw 33).
- Retail: the policy `reference` fields are wrong (e.g. "Cancel pending order" is tagged `Domain basic`). P8 lumps five Domain-basic bullets together.
- **Systemic subject problem.** The prompts say "Format rules from the perspective of '{target_subject} must/must not…'" (`policy_server.py:1395`). As a result, many rules come out as "User must…" (airline 25 of 49 refined rules; retail 13 of 57 unique rules). A few of these are faithful, because the wiki itself addresses the user, but most are agent obligations moved onto the user. The details are in the Step 1 reports.

## Contradictions with the brief
1. The git remote is `BillChan226/ShieldAgent`, not `AutoPolicy`.
2. The empty logic libraries are at `agent/lib/{stormpy,pyModelChecking,mcp-logic}`, not at the root `lib/`. The root `lib/` holds JS assets.
3. `shield/` is a symlink to `agent/`, not a separate package.
4. The policy→rule mapping is not broken. It is keyed on refined rule ids (see above).
5. τ-bench tool names in the brief are exactly right; I verified them against upstream `tools/__init__.py`. τ-bench is **not** installed locally. I used a read-only clone in a scratch directory.
6. The runtime `agent.py` LLM path is not on Azure (see above). The brief implies the whole repo is.
