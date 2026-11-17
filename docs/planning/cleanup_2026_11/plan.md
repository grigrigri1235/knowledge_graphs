# Cleanup plan (2026-11-17)

Status: plan only. Nothing deleted, moved or edited. Waits for the user's "go".
Survey: read only, file list in the session scratchpad. 755 files, about 50 MB (git folder not counted).

## 0. Two facts that shape the plan

1. **Nothing is in git.** `git status` shows every top folder as untracked, and there are no commits. A delete
   today cannot be undone. So part 1 is a snapshot commit. After that, git history keeps every removed file.
2. **This repo is a copy.** The docs name `/home/azureuser/code_projects`. The big run folders and LLM caches are
   not here (no `output/eval_v4/B2v4/...`, no `_llmcache/`). So nothing here can re-run a live test anyway.
   That makes old code easier to remove: what matters is the v4 code, the v4 numbers and the reports.

## 1. What stays (the "keep" set)

- The final work: `docs/reports/tracker_v4_report.md`, its figures (`v4_*.png`, `make_v4_figures.py`),
  `final_presentation.md`.
- v4 code: `guard/*_v4.py`, `state_tracker/v4/`, `scoring/v4_*`, `scripts/v4_*`, `tests/test_v4_*`,
  `tests/fixtures_v4/`, plus **every older module v4 imports** (found in part 2, not guessed).
- v4 data: `output/eval_v4/`, `output/logs/v4_*` (the final metrics), `output/predicate_types.json` (in the freeze).
- The partner's copies: `from_shieldagent/` (all of it; v4 runs on it).
- Project files: `CLAUDE.md`, `knowledge_retention.md`, `README.md`, `codebase_structure.md` (both rewritten in
  part 8), `environment.yml`, `docs/paper/`, `docs/planning/tracker_v4/`, `docs/planning/rules_determinism/`.
- The policy texts: `files_given/airline_wiki.md`, `retail_wiki.md`.

## 2. What goes, by group

### Group A: plain clutter (27 files) - remove
| path | files | why |
|---|---|---|
| `docs/reports/tracker_v4_report.draft1.md` ... `draft13.md` | 13 | drafts of the final report |
| `docs/reports/tracker_v4_parts/` | 6 | parts merged into the final report |
| `final_presentation.before_rewrite.md` | 1 | old version of the presentation |
| `guard/run_online_v3.py.pre_b3`, `scoring/v3_online_interim.py.pre_b3`, `scoring/v3_online_metrics.py.pre_b3` | 3 | backups |
| `predicate_correctness/docs/planning/tracker_v4/dev_check_fail_notes.md` | 1 | copy of `docs/planning/tracker_v4/dev_check_fail_notes.md` (removed only if byte-equal) |
| `docs/planning/cleanup_candidates.md` | 1 | old survey of the other machine |
| `docs/planning/tracker_v4/banking_seal_*superseded*` | 2 | replaced seals |

### Group B: the first project, the ASPM pipeline before TGR (about 40 files) - remove or archive
| path | files | why |
|---|---|---|
| `src/` | 6 | v1 pipeline code (extractor, verifier, ...) |
| `output/` (root) | 10 | v1 pipeline outputs |
| `docs/file_formats/` | 9 | v1 prompts and schemas |
| `docs/reports/poc_report.md`, `wiki_processing_report.md`, `wiki_full_fledged_aspm_report.md` | 3 | v1 reports |
| `files_given/*classification*.json`, `task_airline.py`, `tasks_retail.py`, `wiki.md` | 7 | v1 inputs (`wiki.md` likely equals `retail_wiki.md`: same size; checked first) |
| `handbook_files_to_focus.md`, `model_call_example/` | 3 | v1 handbook list, an example script |

`files_given/` came from you. Confirm before it goes.

### Group C: old experiment plans (56 files) - move to `docs/archive/planning/`
`docs/planning/state_tracking_exp/` (16), `tracker_eval_v2/` (15), `tracker_v3/` (25).
Reports cite them, so move instead of delete.
The old reports (`state_tracking_*`, `tracker_eval_v2_report`, `tracker_v3_*`, `criticism.md`) and their figures
move to `docs/archive/reports/`. The v4 report cites some of them, so its source lines get the new path.

### Group D: old code and old outputs (about 300 files) - remove what v4 does not need
Pre-v4 code: `scoring/v2_*`, `idea_v2_*`, `p10_*`, `p7_results`, `v3_*`; `guard/` v1-v3 files; `fork/`;
top-level `state_tracker/*.py`; `state_tracker/v3/`; `scripts/v3_session/`; `tests/` v1-v3 and `audit_*`.
Old outputs: `output/eval/` (96), `output/p*_*` (35), `implementation_log.md`, `predicate_types.md`.

**Not decided by name.** v4 is built on v3, so some of this is still imported (for example
`fork/offline_v3.py`, the v3 rule table). Part 2 builds the real import list. Only files outside it are removed.
`tests/test_v4_v3_untouched.py` checks old v2/v3 outputs. That test is removed or cut down with them, and the
plan says which.

## 3. Parts (tiny, in order; parts 3-6 can run in parallel after part 2)

| part | what | cost | undo |
|---|---|---|---|
| 1 | Snapshot: `git add -A` + one commit "snapshot before cleanup" on a new branch `cleanup`. Check `.gitignore` first so no venv or cache goes in. | $0 | n/a |
| 2 | Import graph: from every v4 entry point (`guard/run_online_v4.py`, `scoring/v4_*`, `scripts/v4_*`, `tests/test_v4_*`), follow imports and file paths. Output: `keep_code.txt` + a short md. | $0 | read only |
| 3 | Remove group A. | $0 | git |
| 4 | Remove group B (after your yes on `files_given`). | $0 | git |
| 5 | Move group C to `docs/archive/`; fix the paths cited in the v4 report. | $0 | git |
| 6 | Remove group D files not in `keep_code.txt`. | $0 | git |
| 7 | Check: compile every kept `.py` and import every kept module. Run the v4 tests that need no outside venv. Tests that need `/home/azureuser/...` are listed, not counted as fails. | $0 | n/a |
| 8 | Rewrite `codebase_structure.md` and `README.md` for the new tree. | $0 | git |
| 9 | Second commit "cleanup". Report: file count before and after, size before and after, and the list of what went. | $0 | git |

Every command's output goes to a log file, per CLAUDE.md. A progress file is updated during the parts.

## 4. Choices for you
1. Remove group B, or move it to `docs/archive/v1_aspm/`? (my pick: remove; git keeps it)
2. Can `files_given/` inputs go (except the two policy texts)?
3. Old plans and reports: archive folder (my pick) or remove?
4. OK to make the snapshot commit on a new branch `cleanup`?
