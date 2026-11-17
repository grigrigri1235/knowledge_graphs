# Plan: original-machine paths to this machine (2026-11-17)

Status: plan only. Survey done (read only): `logs/s1_survey.log`, `logs/s2_files.log`. Waits for the user's "go".

## 1. What the survey found
- 75 files name `/home/azureuser/...`. About 40 are code or scripts, the rest are docs and run records.
- Many more use `~/...` forms (`~/ShieldAgent` 45 files, `~/venvs/tau-bench` 59, `~/opt/tau-bench-59a200c` 16).
  A `~` path already means "home on this machine", so its text needs no change.
- On this machine: `~/knowledge_graphs` (the repo) and `~/miniconda3` (Python 3.13) exist.
  `~/ShieldAgent`, `~/venvs/tau-bench`, `~/opt/tau-bench-59a200c`, `~/refs` do not exist.
- `from_shieldagent/` has no `/home/azureuser` paths (only one `~/venvs` mention in a docstring). Not touched.

## 2. The rules (applied in this order)
| # | from | to | target exists here? |
|---|---|---|---|
| A | `/home/azureuser/code_projects` | `/home/grigrigri1235/knowledge_graphs` | yes |
| A2 | `~/code_projects` | `~/knowledge_graphs` | yes |
| B | `/home/azureuser/miniconda3` | `/home/grigrigri1235/miniconda3` | yes (Python 3.13 here) |
| C | any other `/home/azureuser` (ShieldAgent, venvs, opt, refs) | `/home/grigrigri1235` | **no** |

Rule C keeps the absolute and `~` forms in step. The targets are still missing, so code that needs them fails, as
it does today. Setting them up (a `~/venvs/tau-bench` venv, a ShieldAgent clone) is a separate task.

## 3. Which files
- **Change:** code and scripts under `predicate_correctness/` (except `from_shieldagent/`), `README.md`,
  `codebase_structure.md`, `knowledge_retention.md`, `docs/reports/`, `docs/planning/tracker_v4/`, `docs/archive/`.
  This includes frozen files: you said that is fine. The freeze already fails in this copy.
- **Keep as is (records of what ran):** `predicate_correctness/output/` (run metrics, logs, `v4_freeze.json`,
  check outputs), and the logs and check files in `docs/planning/cleanup_2026_11/` and `paths_2026_11/`.
  They record what happened on that machine. Changing them would change the record.

## 4. Parts
| part | what | cost |
|---|---|---|
| 1 | Dry run: per file and per rule, count the hits. Write `planned_changes.txt`. | $0 |
| 2 | Apply rules A, A2, B, C to the file set (sed, exact strings only). | $0 |
| 3 | Check: no `/home/azureuser` left in the file set; every `.py` compiles; `bash -n` on every `.sh`; import check before vs after (reuse `cleanup_2026_11/check_tree.py`). | $0 |
| 4 | Commit on branch `cleanup`. Short report. | $0 |

## 5. Choices for you
1. Rule C: also change ShieldAgent, venvs, opt and refs paths to `/home/grigrigri1235/...`, even though they
   don't exist here? (my pick: yes, for consistency)
2. Run records in `output/`: keep as is (my pick), or change them too?
3. Do you want the missing targets set up later (a tau-bench venv here)? Not part of this plan.
