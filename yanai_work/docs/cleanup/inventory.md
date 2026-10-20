# Repository inventory (Phase 1, before cleanup)

Date 2026-10-17. Every candidate for ARCHIVE or DELETE was grepped by name and path across code, configs and `docs/` (the grep evidence is in the "referenced?" column). "Tracked" = under git before the cleanup; most of the reproduction was untracked, and `output/` is git-ignored.

Stage names: **S0** the authors' code adapted to Azure/gpt-5-nano; **S1** gold rule audit; **S2** gold ASPM; **S2b** our automatic pre-reproduction pipeline; **P0–P6** the faithful reproduction.

## Top level
| path | what it is | stage | referenced by current code or docs? | verdict |
|---|---|---|---|---|
| `.gitignore` | ignore list | S0 | – | KEEP (extended in Phase 2) |
| `LICENSE` | MIT license of the authors' repo | upstream | – | KEEP |
| `README.md` | the authors' original README (ShieldAgent demo, deep_policy extraction) | upstream | `docs/planning/project_cleanup_plan.md` (as a file to keep) | ARCHIVE → `archive/authors_code/README_authors.md` (replaced by a new README) |
| `requirements.txt` | the authors' requirements, edited in S0 | upstream/S0 | – | KEEP (the reproduction venv is `docs/reproduction/venv_freeze.txt`) |
| `app.py` | the authors' Gradio demo (policy extraction + shielding), adapted to Azure | upstream/S0 | `docs/orientation_summary.md`, `docs/planning/*` | KEEP (the authors' code audited in `gap_audit.md`) |
| `policy_extractor_async.py` | the authors' AutoPolicy extraction script (produced `output/deep_policy/`) | upstream/S0 | `docs/reproduction/spec.md`, `docs/orientation_summary.md`, `app.py` | KEEP |
| `visualize_policy_graph.py` | pyvis graph of a deep_policy extraction | S0 | only `project_structure.md`, `docs/planning/*` | ARCHIVE → `archive/autopolicy_early/visualization/` |
| `retail_policy_graph.html` | output of the visualiser | S0 | `docs/orientation_summary.md`, `docs/planning/*` | ARCHIVE (with the visualiser; references updated) |
| `lib/` (756K) | JS assets (vis-network, tom-select) loaded by the HTML graph | S0 | `docs/orientation_summary.md` (as support for the HTML graph) | ARCHIVE (with the HTML; it loads them by relative path) |
| `project_structure.md` | structure doc of the S0 repo | S0 | not referenced | ARCHIVE → `archive/early_setup/` (superseded by `docs/STRUCTURE.md`) |
| `shield` → `agent` | symlink | S0 | `agent/**` imports `shield.*` (8 files) | KEEP |
| `agent/` (15M) | the authors' agent: `agent.py`, `tools/` (incl. `aspm_tool.py`), `policy_construction/`, `lib/` (vendored LADR/Prover9, 14M, tracked) | upstream/S0 | `repro_runtime/aspm.py` and `repro_pipeline/run.py` call `agent.tools.aspm_tool.load_aspm_json`; prompts cite `agent/agent.py` and `aspm_tool.py` lines | KEEP (never modified by the reproduction) |
| `agent/predicates/` | **gold** deterministic predicates (`context.py`, `airline.py`, `retail.py`) | S2 | gold scorer `scripts/reproduction/p6_gold_score.py`, `tests/predicates/` | KEEP (gold, scoring only) |
| `utility/` | the authors' utilities; `utils.py` holds the Azure Managed-Identity client | upstream/S0 | `policy_pipeline/llm.py` → used by every repro LLM call | KEEP |
| `policy_docs/` | inputs: `airline_wiki.txt`, `retail_wiki.txt` (byte-identical to τ-bench `wiki.md`) and the authors' sample PDFs | upstream + S0 | wikis: P1/P6; PDFs: `app.py`, authors' README | KEEP |
| `policies/` | **gold**: `curated/` (clauses, curated rules, configs), `predicates/` (registries), `tau_bench/` (tool lists with write flags) | S1/S2 | gold scorer, `scripts/build_aspm.py`, `scripts/reproduction/*` | KEEP (gold, scoring only) |
| `aspm/` | **gold** ASPMs (`{airline,retail}_aspm.json`) built from `scripts/aspm_src/` | S2 | gold scorer, tests | KEEP (gold, scoring only) |
| `aspm_auto/` | S2b automatically built ASPMs | S2b | `policy_pipeline/run.py` (`--publish`), `docs/step2b_auto/*` | KEEP (cited; S2b code stays in place, see below) |
| `aspm_repro/` | **final P1 ASPMs** (airline v4, retail v1) | P1 | P2/P6, all reports | KEEP |
| `policy_pipeline/` | S2b pipeline; `llm.py` is the shared cached gpt-5-nano caller | S2b | imported by frozen `repro_core/llm.py` and `repro_core/taubench_run.py` | KEEP (cannot move without changing frozen P1 code) |
| `eval/` | S2b evaluation code, labels, results | S2b | `scripts/reproduction/p1_gold_diagnostic.py` imports `eval.common`; `docs/step2b_auto/report.md` | KEEP (imported) |
| `repro_core/`, `repro_pipeline/` | P0/P1 code (frozen at tag `repro-p1-v1`) | P0/P1 | – | KEEP |
| `repro_runtime/` | P2 runtime shield | P2 | – | KEEP |
| `repro_online/` | P6 online harness | P6 | – | KEEP |
| `scripts/` | gold builders/validators (`build_aspm.py`, `aspm_src/`, `validate_*`, `extract_tau_tools.py`), tag scripts, `reproduction/` analysis scripts | S1–P6 | reports and logs | KEEP (all; a few P1/P2 analysis scripts are not cited by file name but produced numbers in the reports) |
| `tests/` | unit tests (`policy_pipeline/`, `predicates/`, `repro/`) | S2–P6 | – | KEEP |
| `docs/` | all reports (`reproduction/`, `step1_rule_audit/`, `step2_aspm/`, `step2b_auto/`, `planning/`, `paper/`, `orientation_summary.md`) | all | – | KEEP (every file) |

## `output/` (git-ignored, 1.6G)
| path | what it is | stage | referenced? | verdict |
|---|---|---|---|---|
| `output/deep_policy/` (244K) | the authors' AutoPolicy runs with gpt-5-nano | S0 | cited as source by gold `policies/curated/*.json`; `app.py`, `policy_extractor_async.py` write there | KEEP |
| `output/curated/` (168K) | first copy of the S1 curated artefacts; contains `SUPERSEDED.md` | S1 | `docs/step1_rule_audit/*_coverage_report.md`, `docs/orientation_summary.md` ("moved from output/curated/") | ARCHIVE → `archive/step1_gold_standard/data/output_curated/` (references updated) |
| `output/step2_firing/` (200K) | S2 firing analysis of the gold ASPM | S2 | default output of `scripts/validate_aspm.py --firing`; `docs/step2_aspm/firing_analysis.md` | KEEP |
| `output/auto_aspm/` (298M) | S2b runs + **LLM cache `_cache/` (214M)** + logs | S2b | default cache dir of `policy_pipeline/llm.py`; `eval/runtime_load.py`; `docs/step2b_auto/report.md` | KEEP (cache: loss would force paid re-runs) |
| `output/reproduction/labels/` (1.8M) | write-action labels, **`splits.json`** | P0 | `scripts/reproduction/*`, `repro_online/run.py`, `data_feasibility.md` | KEEP (must keep) |
| `output/repro/_llmcache/` (**503M**) | P1/P2/P6 LLM cache (structured calls + tool-loop turns) | P1–P6 | `repro_core/config.json` | KEEP (loss forces paid re-runs) |
| `output/repro/_embcache/` (13M) | bge-large embedding cache (SQLite) | P1 | `repro_core/config.json` | KEEP (recomputable locally but slow) |
| `output/repro/_models/` (641M) | bf16 copy of bge-large-en-v1.5 @ d4aa6901 (+ PROVENANCE.json) | P1 | `repro_core/embed.py` | KEEP (regenerable by download + conversion, no LLM cost) |
| `output/repro/aspm_runs/airline/v4`, `retail/v1` | the published P1 runs (raw responses, alg2, circuits, manifests) | P1 | `aspm_repro/*/manifest.json` run ids; P2/P6 read `alg2.json` type conflicts | KEEP |
| `output/repro/aspm_runs/airline/v1`, `v2`, `v3` (12.3M) | superseded P1 runs: v1 few-shot copies (I4), v2 fp32 diagnostic, v3 meaning-changing repairs (I7) | P1 | described in `docs/reproduction/p1_log.md` (by name, not path); no code reads them | ARCHIVE → `archive/p1_superseded_runs/data/airline_v{1,2,3}/` |
| `output/repro/p1_*.log` | P1 run logs | P1 | `p1_log.md` | KEEP |
| `output/repro/smoke/` | P0 smoke runs, including `airline_test_0.openai254.json` | P0 | `p1_log.md` (the openai-2.54 run is described by its numbers) | KEEP |
| `output/repro/p2_pilot/` (9.7M) | P2 pilot records (A, A2, A2_rerun, B, direct, smoke) | P2 | `p2_pilot_report.md` | KEEP |
| `output/repro/p6/` (127M) | P6 smoke + full runs: `episodes.jsonl` (+ `episodes.before_resume.jsonl`), `gold.jsonl`, `metrics.json/md`, logs | P6 | `p6_report.md` | KEEP (must keep) |

## Caches and regenerable files
| path | verdict |
|---|---|
| all `__pycache__/` outside `output/` (16 directories) | DELETE (untracked → `_to_delete/`) |
| `agent/lib/LADR-2009-02A/**.bak` | KEEP: vendored third-party sources tracked by the authors' repo; not touched |

## Counts
- KEEP: 35 rows (+ the vendored LADR `.bak` files); ARCHIVE: 7 items (authors' README, `project_structure.md`, visualiser + HTML + `lib/`, `output/curated/`, P1 airline v1–v3); DELETE: 16 `__pycache__` directories (all untracked → `_to_delete/`), 0 tracked files.
- Unsure, left as KEEP: `aspm_auto/`, `eval/`, `policy_pipeline/`, `output/auto_aspm/` (stage 2b; imported or cited, so not archived); the authors' `app.py`, `policy_extractor_async.py`, `agent/policy_construction/` and sample PDFs (upstream code, audited in `gap_audit.md`); `output/repro/_models/` (regenerable but 641M to re-download).
