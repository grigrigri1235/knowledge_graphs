# ShieldAgent - Project Structure

This document shows the layout of the project and what each part does.

> `.git/` is not shown. `output/`, `lib/` and `agent/lib/` are shown collapsed.

## 1. Directory Tree

```text
ShieldAgent/
├── .gitignore
├── LICENSE
├── README.md
├── requirements.txt
├── app.py
├── policy_extractor_async.py
├── visualize_policy_graph.py
├── retail_policy_graph.html
├── shield -> agent                  (symlink)
├── lib/                             (JS libraries for the HTML graph)
│   ├── bindings/
│   ├── tom-select/
│   └── vis-9.1.2/
├── output/                          (extraction results)
│   └── deep_policy/
│       ├── extraction_20261012_112151/
│       ├── extraction_20261012_112735/
│       └── extraction_20261012_120408/
├── policy_docs/                     (input policy documents)
│   ├── airline_wiki.txt
│   ├── retail_wiki.txt
│   ├── eu_ai_act_art_5.txt
│   ├── eu_ai_act_art5.pdf
│   ├── aba-formal-opinion-512.pdf
│   └── nais2023.pdf
├── utility/                         (MCP server + helpers for extraction)
│   ├── policy_server.py
│   └── utils.py
├── agent/                           (ShieldAgent runtime verifier)
│   ├── agent.py
│   ├── prompt.py
│   ├── run_inference.py
│   ├── debug_utils.py
│   ├── utils.py
│   ├── lib/                         (third-party logic tools)
│   │   ├── LADR-2009-02A/
│   │   ├── mcp-logic/
│   │   ├── pyModelChecking/
│   │   └── stormpy/
│   ├── policy_construction/         (older / alternative extractors)
│   │   ├── policy_extractor_async.py
│   │   ├── policy_extractor_async_non_mcp.py
│   │   ├── policy_extractor_non_async.py
│   │   ├── rule_extractor.py
│   │   └── utility.py
│   └── tools/                       (MCP tools used by the agent)
│       ├── __init__.py
│       ├── aspm_tool.py
│       ├── binary_query.py
│       ├── certification.py
│       ├── content_moderation.py
│       ├── context_search.py
│       ├── memory_tool.py
│       ├── policy_extraction.py
│       └── verification.py
└── docs/
    └── planning/                    (plans and run logs)
        ├── azure_openai_refactor_plan.md
        ├── project_cleanup_plan.md
        ├── cleanup_run.log
        └── new_tree.txt
```

## 2. Big Picture

The project has two jobs:

1. **Policy extraction (offline).** Read a policy document, then produce policies, rules and risk categories.
   This is `policy_extractor_async.py` + `utility/`.
2. **Action verification (runtime).** Check an AI agent's actions against the extracted rules.
   This is the `agent/` folder.

```text
policy_docs/ --> policy_extractor_async.py --> utility/policy_server.py (MCP) --> output/
                                                                              |
                                              visualize_policy_graph.py <-----+--> HTML graph
                                                                              |
                                                       agent/ (ShieldAgent) <-+  uses the rules
```

## 3. Root Files

| File | Responsibility |
|---|---|
| `policy_extractor_async.py` | Main command-line tool. Loads a document (pdf, html or txt), extracts policies, then rules, then risk categories. Calls the MCP server in `utility/policy_server.py`. Supports parallel section processing. |
| `visualize_policy_graph.py` | Builds an HTML policy graph from extraction output. Default output name is `policy_graph_interactive.html`. |
| `retail_policy_graph.html` | A generated graph for the retail policy. It loads the scripts in `lib/`. |
| `app.py` | Gradio web interface for running the extraction from a browser. |
| `requirements.txt` | Python dependencies (includes `azure-identity`). |
| `README.md` | Project overview. |
| `LICENSE` | License terms. |
| `.gitignore` | Ignores `output/`, `__pycache__/`, `results/`, `.gradio/` and `temp_uploads/`. |
| `shield` | Symlink to `agent/`. The code in `agent/` imports `shield.*`, so it needs this link. |

## 4. Folders

### `policy_docs/` - inputs
Source policy documents.

| File | Content |
|---|---|
| `airline_wiki.txt` | Airline policy text (used for the TauBench run). |
| `retail_wiki.txt` | Retail policy text. |
| `eu_ai_act_art_5.txt`, `eu_ai_act_art5.pdf` | EU AI Act, Article 5. |
| `aba-formal-opinion-512.pdf` | ABA formal opinion 512. |
| `nais2023.pdf` | NAIS 2023 document. |

### `output/` - results
One timestamped folder per run, under `output/deep_policy/extraction_<date>_<time>/`.
Each run holds the extracted policies, rules, risk categories, a policy-to-rule mapping and a document tree (JSON).

### `utility/` - extraction backend
| File | Responsibility |
|---|---|
| `policy_server.py` | MCP server called by `policy_extractor_async.py`. Tools: `analyze_document_section`, `extract_policies_from_file`, `extract_rules_from_policies`, `refine_and_categorize_rules`. Uses the Azure `gpt-5-nano` deployment through Managed Identity. |
| `utils.py` | Shared helpers: `chat_text` (LLM call), JSON extraction from text, image encoding, document-tree plotting. |

### `agent/` - ShieldAgent runtime
| File / folder | Responsibility |
|---|---|
| `agent.py` | The `ShieldAgent` class. Plans checks and verifies agent actions against rules. |
| `run_inference.py` | Runs `ShieldAgent` over saved trajectories. |
| `prompt.py` | Prompt text for the agent. |
| `debug_utils.py` | Debug logging helpers. |
| `utils.py` | LLM call helper (`chat_text`) and other helpers for the agent. |
| `lib/` | Third-party logic and model-checking tools: LADR, mcp-logic, pyModelChecking, stormpy. |

### `agent/tools/` - MCP tools for the agent
| File | Responsibility |
|---|---|
| `aspm_tool.py` | Access to ASPM data and rule circuits. |
| `binary_query.py` | Yes/no style checks. |
| `certification.py` | Final rule verification and safety decision. |
| `content_moderation.py` | Text and image moderation checks. |
| `context_search.py` | Context lookup. |
| `memory_tool.py` | Memory of past verification workflows. |
| `policy_extraction.py` | Policy extraction tool (older copy of the logic in `utility/policy_server.py`). |
| `verification.py` | Predicate and rule verification tools. |
| `__init__.py` | Package setup. |

### `agent/policy_construction/` - older extractors
Earlier or alternative versions of the extraction pipeline.

| File | Responsibility |
|---|---|
| `policy_extractor_async.py` | Async extractor (older version of the root script). |
| `policy_extractor_async_non_mcp.py` | Async extractor that does not use MCP. |
| `policy_extractor_non_async.py` | Sequential extractor. |
| `rule_extractor.py` | Extracts LTL rules from structured policies. |
| `utility.py` | Helpers shared by these extractors. |

### `lib/` - graph front-end libraries
JavaScript used by the generated HTML graphs: `vis-9.1.2`, `tom-select` and `bindings`.
`retail_policy_graph.html` loads `lib/bindings/utils.js`, so keep this folder while you keep the HTML graph.

### `docs/planning/` - plans and logs
Plans and run logs kept as required by the agent policy.

| File | Content |
|---|---|
| `azure_openai_refactor_plan.md` | Plan for the Azure OpenAI Managed Identity migration. |
| `project_cleanup_plan.md` | Plan for the cleanup. |
| `cleanup_run.log` | Log of the cleanup commands. |
| `new_tree.txt` | Raw directory listing taken after cleanup. |

## 5. Notes

- **LLM backend.** All OpenAI-style calls use Azure `gpt-5-nano` with Managed Identity and `client.responses.create(...)` / `response.output_text`.
- **Anthropic.** The Anthropic client is created only if `ANTHROPIC_API_KEY` is set.
- **Imports in `agent/`.** Files there import `shield.*`. That works only because of the `shield -> agent` symlink at the project root.
- **Missing files.** `run.sh` and `visualize_policy_graph_full.py` are not on the system yet. They are not listed above.
- **Python cache.** `__pycache__/` folders were removed. They return when you run Python and are ignored by git.
