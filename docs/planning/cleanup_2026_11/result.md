# Cleanup result (2026-11-17)

Branch `cleanup`. Snapshot before: commit `9ecc20d`. Undo any file: `git checkout 9ecc20d -- <path>`.

## Numbers
| | before | after |
|---|---|---|
| files in git | 800 | 588 |
| size | about 50 MB | about 33 MB |

| change | files |
|---|---|
| removed | 245 |
| moved to `docs/archive/` | 73 |
| edited | 12 (README, codebase_structure, path fixes in docs, merged dev-check note) |
| added | 33 (this folder: plan, scripts, lists, logs) |

Removed, by place: `predicate_correctness/output` 78, `tests` 44, `scoring` 35, `docs/reports` 22 (13 drafts, 6 parts,
3 v1 reports), `scripts` 18, root `output/` 10, `docs/file_formats` 9, `files_given` 7, `src` 6, `fork` 6, others 10.

## Checks (part 7, `part7_check.md`)
- Imports broken by the cleanup: 0. v4 tests broken by the cleanup: 0.
- The v4 freeze gives the same result as before (2 same, 198 changed, 4 missing). The 198 already differ in this copy
  (CRLF line ends); the 4 missing were never here.

## What went wrong, and the fix
- Part 2's freeze check read `freeze_list.txt` (90 files, CRLF line ends) and missed the real manifest
  `v4_freeze.json` (204 files). So part 6 removed 8 frozen files, and part 5 edited 4 frozen v4 plan docs.
- Found in part 7 by a test that got worse. All 12 were restored byte-equal from the snapshot.
- Cost: 8 old files stay that v4 does not import (`guard/offline.py`, 5 in `state_tracker/`,
  `state_tracker/v3/rule_table.py`, `tests/test_v4_v3_untouched.py`), and the 4 frozen docs keep old paths.

## Left as is
- Code docstrings and the 4 frozen docs cite `docs/planning/tracker_v3/...`; those plans now live in
  `docs/archive/planning/`.
- `knowledge_retention.md` lines 1114-1115 name 3 removed v1 reports (history).
- Many v4 tests already failed before the cleanup in this copy: they need `/home/azureuser/...` paths, the
  tau-bench venv, or `output/eval_v3/`. Listed in `part7_check.md`.
