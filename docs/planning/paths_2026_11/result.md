# Result: paths moved to this machine (2026-11-17)

Commit `5ec6c23` on branch `cleanup` (not pushed). Plan: `plan.md`. Script: `paths_fix.py` (exact byte replacement, line endings kept).

## What changed
- 56 files, 99 lines. Full list with per-file hits: `planned_changes.txt`.
- Hits per rule (applied in order):

| rule | from | to | hits |
|---|---|---|---|
| A | `/home/azureuser/code_projects` | `/home/grigrigri1235/knowledge_graphs` | 48 |
| A2 | `~/code_projects` | `~/knowledge_graphs` | 2 |
| B | `/home/azureuser/miniconda3` | `/home/grigrigri1235/miniconda3` | 39 |
| C | other `/home/azureuser` | `/home/grigrigri1235` | 11 |

- `codebase_structure.md`: the "original machine path" sentence was rewritten by hand, as planned.
- File set: 240 tracked text files; 15 png skipped. Not touched: `predicate_correctness/output/`, `from_shieldagent/`,
  `docs/planning/cleanup_2026_11/`, `docs/planning/paths_2026_11/`.
- The commit holds only: the 56 files, `docs/planning/paths_2026_11/`, `docs/planning/cleanup_2026_11/logs/p9_commit.log`
  (84 files). `environment.yml` and `docs/planning/env_2026_11/` (main session's work) were NOT committed (checked with
  `git diff --cached --name-only`, log `logs/p4_stage.log`).

## Checks (part 3)
| check | result |
|---|---|
| new compile errors | 0 of 203 |
| imports broken | 0 (8 failed before, 5 after) |
| v4 tests broken | 0 (see below) |
| `bash -n` on the 8 changed `.sh` (committed text) | 8 of 8 pass |
| `azureuser` left in the file set | codebase_structure.md sentence + 8 kept temp names (below) |

Details: `part3_check.md`, logs `logs/p3*.log`.

### Tests whose result changed (rerun after the restore below)
| test | before | after | why |
|---|---|---|---|
| `test_v4_fix2` | OK | OK | showed FAILED only while output/ was overwritten |
| `test_v4_question_texts` | FAILED (errors=4) | OK (24 tests) | the snapshot had no `docs/` folder |
| `test_v4_freeze` | FAILED (failures=1, errors=2) | FAILED (errors=2) | same snapshot reason; the 2 errors (missing `output/eval_v3/*.json`) are unchanged |

## Odd things
1. **The check wrote into output/.** The 3 scripts whose import now passes (`scripts/build_questions_A4.py`,
   `scripts/v4_cases_gen/gen_a17.py`, `scripts/v4_cases_gen/make_v4_A15.py`) write files at import time to paths that
   now exist here. `check_tree.py` overwrote 9 tracked files: `output/eval_v4/overlays/questions_A4.json` (content changed)
   and `output/eval_v4/cases/K7,K8,K10,K12,K13,K16,K17,K18.jsonl` (same content). Restored with `git checkout --`;
   output/ is clean (`logs/p3_restore.log`). **Do not run `check_tree.py` on this tree again** (or importing those 3 scripts).
2. **CRLF in the working copy.** WSL git has `core.autocrlf=true`, so checked-out text files have CRLF. 7 of the 8
   changed `.sh` files fail `bash -n` in the working copy (`$'\r'` errors). Same before the edit. The committed text has
   LF and all 8 pass `bash -n` (`logs/p3c_crlf.log`, `logs/p4_verify.log`). Running the scripts from this working copy
   will fail until line endings are fixed (separate task).
3. **Kept temp-folder names.** 8 hits in 7 files of `/tmp/claude-1000/-home-azureuser-code-projects/<session>/scratchpad/...`
   (old Claude scratchpad folders; they exist on neither machine). No rule covers them. Decision: keep as is, no new rule.
   Files: `docs/archive/reports/tracker_v3_full_report.md`, `docs/planning/tracker_v4/code_change_map.md`,
   `docs/planning/tracker_v4/predicate_table.md`, `docs/planning/tracker_v4/reading_notes/tau3_airline_diff.md`,
   `docs/planning/tracker_v4/reading_notes/tau3_retail_diff.md`, `predicate_correctness/scripts/v3_session/README.md` (2),
   `predicate_correctness/scripts/v3_session/b3/tools/identity_check.sh`.
4. Rule C targets (`~/ShieldAgent`, `~/venvs/tau-bench`, `~/opt/tau-bench-59a200c`, `~/refs`) still do not exist here.
