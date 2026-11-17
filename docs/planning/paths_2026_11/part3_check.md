# Part 7: before vs after

- compile errors: before 0 of 203, after 0 of 203
- imports: before 8 fail of 113, after 5 fail of 113
- **imports broken by the cleanup: 0**

- v4 test files: 21 after (before 21; test_v4_v3_untouched removed)
- **v4 tests broken by the cleanup: 1**

## New compile errors
(none)

## Imports broken by the cleanup
(none)

## Tests broken by the cleanup
- tests/test_v4_fix2.py: FAILED (failures=1)


## Already failing before the cleanup (same here and in the snapshot)

| file | before | after |
|---|---|---|
| import scripts/v4_cases_gen/gen_k1.py | fail (1): IndexError: list index out of range | fail (1): IndexError: list index out of range |
| import scripts/v4_cases_gen/gen_k3.py | fail (1): IndexError: list index out of range | fail (1): IndexError: list index out of range |
| import scripts/v4_cases_gen/gen_k4k6.py | fail (1): IndexError: list index out of range | fail (1): IndexError: list index out of range |
| import tests/test_v4_feedback.py | fail (1): FileNotFoundError: [Errno 2] No such file or directory: '/home/grigrigri1235/.ca | fail (1): FileNotFoundError: [Errno 2] No such file or directory: '/home/grigrigri1235/kno |
| import tests/test_v4_recompute.py | fail (1): FileNotFoundError: [Errno 2] No such file or directory: '/home/grigrigri1235/.ca | fail (1): FileNotFoundError: [Errno 2] No such file or directory: '/home/grigrigri1235/kno |
| test tests/test_v4_code_facts.py | FAILED (errors=2) | FAILED (errors=2) |
| test tests/test_v4_direct_facts.py | FAILED (errors=8) | FAILED (errors=8) |
| test tests/test_v4_feedback.py | FileNotFoundError: [Errno 2] No such file or directory: '/home/grigrigri1235/.cache/kg_pat | FileNotFoundError: [Errno 2] No such file or directory: '/home/grigrigri1235/knowledge_gra |
| test tests/test_v4_form_check.py | FAILED (errors=1) | FAILED (errors=1) |
| test tests/test_v4_freeze.py | FAILED (failures=1, errors=2) | FAILED (errors=2) |
| test tests/test_v4_guard.py | FAILED (failures=1, errors=35) | FAILED (failures=1, errors=35) |
| test tests/test_v4_metrics.py | FAILED (failures=1) | FAILED (failures=1) |
| test tests/test_v4_no_gold_import.py | FAILED (failures=1) | FAILED (failures=1) |
| test tests/test_v4_question_texts.py | FAILED (errors=4) | FAILED (failures=3) |
| test tests/test_v4_recompute.py | FileNotFoundError: [Errno 2] No such file or directory: '/home/grigrigri1235/.cache/kg_pat | FileNotFoundError: [Errno 2] No such file or directory: '/home/grigrigri1235/knowledge_gra |
| test tests/test_v4_report.py | FAILED (failures=2) | FAILED (failures=2) |
| test tests/test_v4_run_online.py | FAILED (failures=10, errors=6, skipped=4) | FAILED (failures=10, errors=6, skipped=4) |
| test tests/test_v4_v3_untouched.py | FAILED (failures=3, errors=7) | FAILED (failures=3, errors=7) |

## Imports that failed before and pass now
- scripts/build_questions_A4.py
- scripts/v4_cases_gen/gen_a17.py
- scripts/v4_cases_gen/make_v4_A15.py

## Note added after the run (paths move, not the cleanup)
The headings above come from the cleanup's compare_trees.py; here "cleanup" means "path move".

- The 3 imports above now pass because their path now exists here. Importing them runs their top-level code,
  which WROTE into the real tree: `output/eval_v4/overlays/questions_A4.json` (content changed) and
  `output/eval_v4/cases/K7,K8,K10,K12,K13,K16,K17,K18.jsonl` (same content). Restored with `git checkout --`;
  `output/` is clean again (log: `logs/p3_restore.log`). check_tree.py is no longer safe to run on this tree.
- That overwrite caused the "broken" `test_v4_fix2` (it compares questions_A4.json with the merged questions).
  After the restore: `test_v4_fix2` OK (13 tests), same as before.
- Rerun after the restore, before -> after:
  - `test_v4_fix2`: OK -> OK.
  - `test_v4_question_texts`: FAILED (errors=4) -> OK (24 tests). Before failed only because the snapshot has no `docs/`.
  - `test_v4_freeze`: FAILED (failures=1, errors=2) -> FAILED (errors=2). The extra failure before was the missing
    `docs/.../preregistration_v4.md` in the snapshot. Both errors are missing `output/eval_v3/*.json`, same before and after.
- Net: tests broken by the path edit: 0.
