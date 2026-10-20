> **Note (2026-10-17 cleanup):** items mentioned below were moved: `README.md` (authors') → `archive/authors_code/README_authors.md`; `project_structure.md` → `archive/early_setup/`; `visualize_policy_graph.py`, `retail_policy_graph.html` and `lib/` → `archive/autopolicy_early/visualization/`; `output/curated/` → `archive/step1_gold_standard/data/output_curated/`. See `docs/cleanup/cleanup_log.md`.

# Project Cleanup Plan

Status: WAITING FOR APPROVAL. Nothing has been deleted.

## Found problems in your request
- `run.sh` does not exist in the project. Cannot keep what is not there.
- `visualize_policy_graph_full.py` does not exist either.
- Only `visualize_policy_graph.py` exists. It will be kept.

## Never touched (your exclusions + core)
- `output/` (all contents)
- `visualize_policy_graph.py`
- `policy_extractor_async.py`
- `policy_docs/` (all 6 files)
- `app.py`, `README.md`, `LICENSE`, `requirements.txt`, `.gitignore`, `.git/`
- `agent/` code (agent.py, prompt.py, run_inference.py, utils.py, debug_utils.py, policy_construction/, tools/)
- `utility/` code (policy_server.py, utils.py)
- `agent/lib/` third-party logic tools (LADR, mcp-logic, pyModelChecking, stormpy)
- `docs/planning/` (required by agent policy)
- `shield` symlink -> `agent` (I made it earlier. The `agent/` code does `import shield.*`. Removing it breaks those imports.)

## A. Safe to delete (temporary / junk)
| Path | Why |
|---|---|
| `test_run.log` | My smoke-test log. Not part of code. |
| `response.txt` | Stray LLM debug dump. Only a commented-out line in `policy_server.py` refers to it. |
| `__pycache__/` (root) | Python cache. Already in .gitignore. |
| `agent/__pycache__/` | Same. |
| `agent/policy_construction/__pycache__/` | Same. |
| `agent/tools/__pycache__/` | Same. |
| `utility/__pycache__/` | Same. |

## B. Generated files - YOUR DECISION
These are made by `visualize_policy_graph.py`. They can be re-created.
| Path | Recommendation |
|---|---|
| `policy_graph_static.png` (985 KB) | Delete. Re-creatable. |
| `policy_graph_interactive.html` | Delete. Re-creatable (it is the script default output name). |
| `retail_policy_graph.html` | KEEP unless you say delete. You have it open. |
| `lib/` (bindings, tom-select, vis-9.1.2) | KEEP if you keep any HTML graph. The HTML loads `lib/bindings/utils.js`. |

## C. Optional - YOUR DECISION
| Path | Note |
|---|---|
| `agent/lib/test.py` | Small scratch demo of pyModelChecking. Not imported anywhere. Recommend delete. |

## Execution parts (after approval)
1. Delete section A files and cache dirs.
2. Apply your decision on section B.
3. Apply your decision on section C.
4. Print new directory tree to a file and show it.
5. Write the folder/file explanation.

All commands will write output to `docs/planning/cleanup_run.log`.
