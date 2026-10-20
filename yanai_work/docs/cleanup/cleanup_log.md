# Cleanup log

Started 2026-10-17. Rules: no rule edits, no result-file changes, no secrets; untracked files are never deleted (moved to `_to_delete/`); tracked deletions are recoverable from tag `pre-cleanup`.

## Phase 0: safety net
- `git status` before: 28 tracked files modified or deleted (the authors' code adapted to Azure/gpt-5-nano in Stage 0, plus stale `.pyc` files). Secrets check of the diff: no keys (authentication is Azure Managed Identity; only the endpoint hostname appears). Committed as `b754141` "pre-cleanup snapshot", tagged **`pre-cleanup`**. Remote `origin` is the paper authors' GitHub repo: nothing is pushed.
- Untracked (not protected by git): agent/__pycache__ (12K), agent/predicates (132K), agent/tools/__pycache__ (88K), aspm/ (140K), aspm_auto/ (1.2M), aspm_repro/ (708K), docs/ (5.4M), eval/ (956K), lib/ (756K), policies/ (332K), policy_docs/{airline,retail}_wiki.txt (8K each), policy_pipeline/ (300K), project_structure.md (12K), repro_core/ (116K), repro_online/ (68K), repro_pipeline/ (188K), repro_runtime/ (200K), retail_policy_graph.html (28K), scripts/ (300K), shield (symlink → agent), tests/ (480K), visualize_policy_graph.py (8K).
- Ignored by .gitignore: output/ (**1.6G**; results and LLM caches), utility/__pycache__ (12K).
- Disk: / 61G total, 49G used, **13G free** (80 %). Repo working tree **1.7G** (of which output/ 1.6G, .git 11M).

## Phase 1: inventory
`docs/cleanup/inventory.md`. Every ARCHIVE/DELETE candidate was grepped by name and path across code, configs and `docs/`. Two candidates were found to be referenced and stayed KEEP:
- `output/deep_policy/`: cited as source by the gold `policies/curated/*.json`.
- `output/repro/smoke/airline_test_0.openai254.json`: the earlier smoke run described by its numbers in `p1_log.md`.

The stage-2b code (`policy_pipeline/`, `eval/`, `aspm_auto/`, `output/auto_aspm/`) stays in place: it is imported by the frozen `repro_core/` and by `scripts/reproduction/p1_gold_diagnostic.py`, and it is the default LLM cache location.

## Phase 2: clean up
**ARCHIVE** (7 items):
| from | to | how | references updated |
|---|---|---|---|
| `README.md` (authors', tracked) | `archive/authors_code/README_authors.md` | `git mv` | note in `docs/planning/project_cleanup_plan.md` |
| `project_structure.md` (untracked) | `archive/early_setup/project_structure.md` | `mv` | none needed (unreferenced) |
| `visualize_policy_graph.py`, `retail_policy_graph.html`, `lib/` (untracked) | `archive/autopolicy_early/visualization/` | `mv` (kept together: the HTML loads `lib/` by relative path) | `docs/orientation_summary.md` (inline + note), `docs/planning/{project_cleanup_plan.md,azure_openai_refactor_plan.md,new_tree.txt}` (note at top) |
| `output/curated/` (git-ignored) | `archive/step1_gold_standard/data/output_curated/` | `mv` | `docs/step1_rule_audit/{airline,retail}_coverage_report.md` (inline), `docs/orientation_summary.md` |
| `output/repro/aspm_runs/airline/v1`, `v2`, `v3` (git-ignored, 12.3M) | `archive/p1_superseded_runs/data/airline_v1`, `_v2`, `_v3` | `mv` | none needed (`p1_log.md` names the runs, not the paths; no code reads them) |

**DELETE**:
- Tracked: none.
- Untracked, moved to `_to_delete/` with relative paths kept: 16 `__pycache__/` directories (912K): `utility/`, `scripts/`, `scripts/reproduction/`, `repro_pipeline/`, `repro_core/`, `repro_online/`, `repro_runtime/`, `policy_pipeline/`, `agent/`, `agent/predicates/`, `agent/tools/`, `eval/`, `tests/`, `tests/policy_pipeline/`, `tests/repro/`, `tests/predicates/`. They are regenerated on import (git-ignored now). **You can delete `_to_delete/` after checking.**

**.gitignore** additions: `__pycache__/`, `*.pyc`, `.pytest_cache/`, `nohup.out`, `_to_delete/`, `archive/**/data/` (archived run outputs remain local data, like `output/`).

Not reorganised: `repro_core/`, `repro_pipeline/`, `repro_runtime/`, `repro_online/`, `scripts/reproduction/`, gold artefacts, `output/` results and caches.

## Phase 3: verification
- **Full test suite** (`~/venvs/tau-bench/bin/python -m unittest discover -s tests -t .`, run detached): **56 tests OK** in 350 s, including `tests/repro/test_repro_pipeline.py::NoGoldLeakage` (gold paths unreachable from `repro_core`, `repro_pipeline`, `repro_runtime` and `repro_online`; no domain words in the method packages). Output: `docs/cleanup/test_run.log`.
- **Imports:** all 27 modules of `repro_core`, `repro_pipeline`, `repro_runtime` and `repro_online` import. All 22 scripts in `scripts/` and `scripts/reproduction/` compile, and every module they import resolves. Scripts are not executed on import, because several run at module level.
- **P6 metrics recompute** (`scripts/reproduction/p6_metrics.py full`, no LLM calls): `output/repro/p6/full/metrics.json` is **byte-identical** to the file before the cleanup (SHA-256 `1bad70fc…f862a` before and after). The headline values match `p6_report.md`:
  - pass^1: airline 0.300 / 0.267 / 0.250, retail 0.348 / 0.391 / 0.145;
  - pass^3: 0.100 / 0.200 / 0.000 and 0.109 / 0.130 / 0.022;
  - blocks per episode 1.30 / 4.47 and 0.54 / 10.45; cap overrides 3 / 29 and 3 / 301;
  - precision on scorable blocks 0.52 / 0.13 and 0.59 / 0.24;
  - cost $0.89 / $1.72 / $3.30 and $1.77 / $3.28 / $9.86.
- **Dry starts without API calls:**
  - `python -m repro_pipeline.run --help` and `python -m repro_online.run --help` work.
  - For both domains, the P1 prompt hashes equal the `aspm_repro/*/manifest.json` hashes, and the policy inputs, run directories, LLM cache and bf16 model copy are present.
  - `repro_runtime.aspm.load` loads both ASPMs (58 / 43 rules).
  - A 0-task online run (`--guard none --tasks no_such_split --tag _dryrun`) starts, finds `splits.json` and τ-bench, and ends with "DONE: 0 episodes". The empty `output/repro/p6/_dryrun/` it created was moved to `_to_delete/output/repro/p6/_dryrun/`.
- **Frozen P1 code** still equals tag `repro-p1-v1` (blob-by-blob, same file set).
- Nothing failed; nothing was restored from `pre-cleanup`.

## Phase 4: documentation
New: `README.md` (humans), `AGENTS.md` + identical `CLAUDE.md` (coding agents), `docs/STRUCTURE.md` (folder and file map). Every backticked path in them was checked to exist. The README commands were made non-destructive: new run ids and tags, with a warning that `p2_pilot.py` truncates its tag's file.

## Sizes
| | before | after |
|---|---|---|
| repo working tree | 1.7G | 1.7G (nothing deleted outright; `_to_delete/` = 1.0M awaiting your deletion) |
| `output/` (git-ignored) | 1.6G | 1.6G (−12.5M moved to `archive/**/data/`) |
| `archive/` | – | 14M (of which 12.5M git-ignored `data/`) |
| `.git` | 11M | 11M before the final commit (the commit adds 221 files, 10.3 MB) |
| free disk | 13G | 13G |

Secret scan of the files added by the final commit: no keys, tokens or private keys found. `output/`, `archive/**/data/`, `_to_delete/` and caches are not committed.

## Follow-ups (2026-10-17, after the cleanup commit)
- **Git remotes:**
  - `origin` (the authors' repo) was renamed to **`upstream`**, and its push URL was set to `DISABLED`, so an accidental push fails.
  - The owner's private repo was added as **`origin`**: `https://github.com/yanai-1701/ShieldAgent_Taubench.git`.
  - Push to `origin` **failed**: no GitHub credentials on the VM (no `gh`, no SSH key registered with GitHub, no token). Nothing was pushed anywhere.
- **Backup:**
  - Archive: `~/backups/shieldagent_output_20261017.tar.gz`, 325 MB (340,583,940 bytes), 55,546 files. It contains `output/` and `archive/`, minus `output/repro/_models/` (the regenerable bf16 model copy, 641 MB).
  - Checksum file: `~/backups/shieldagent_output_20261017.tar.gz.sha256` (SHA-256 `bffbcfb9…908f`).
  - Built by a `setsid nohup` script that writes a `.partial` file and then renames it.
  - Test extraction into `/tmp/backup_check`: 55,546 = 55,546 files; per-folder counts equal; `metrics.json` and `splits.json` byte-identical. The test copy was then removed.
  - README section "Backup & restore" added.
- **Dependency audit** of `policy_pipeline/` and `eval/`: no method logic is used (`docs/reproduction/gap_audit.md` addendum, `AGENTS.md` §4c).
- **Docs:** `CLAUDE.md` replaced by a symlink to `AGENTS.md`. `AGENTS.md` gained the git rule, data-splits rule, Stage-A configuration table, new-guard guide, D9 scorer limitation, and the verified policy-input and τ-bench wording.
