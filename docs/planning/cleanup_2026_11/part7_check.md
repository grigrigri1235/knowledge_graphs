# Part 7: before vs after

- compile errors: before 0 of 298, after 0 of 203
- imports: before 23 fail of 208, after 8 fail of 113
- **imports broken by the cleanup: 0**

- v4 test files: 21 after (before 21; test_v4_v3_untouched was removed, then restored because it is frozen)
- Note: the "before" tree held only `predicate_correctness/` at first, without `docs/`. So the two tests that read
  `docs/` (test_v4_question_texts, test_v4_freeze) look better "after". That is the setup, not the cleanup.
- v4 freeze (`scoring.v4_freeze --check`): before 2 same / 198 changed / 4 missing; after the same.
  The 198 differ already in this copy (the files have CRLF line ends here); the 4 missing are `output/eval_v3/`,
  never in this copy.
- **v4 tests broken by the cleanup: 0**

## New compile errors
(none)

## Imports broken by the cleanup
(none)

## Tests broken by the cleanup
(none)

## Already failing before the cleanup (same here and in the snapshot)

| file | before | after |
|---|---|---|
| import scripts/build_questions_A4.py | fail (1): FileNotFoundError: [Errno 2] No such file or directory: '/home/azureuser/code_pr | fail (1): FileNotFoundError: [Errno 2] No such file or directory: '/home/azureuser/code_pr |
| import scripts/v4_cases_gen/gen_a17.py | fail (1): FileNotFoundError: [Errno 2] No such file or directory: '/home/azureuser/code_pr | fail (1): FileNotFoundError: [Errno 2] No such file or directory: '/home/azureuser/code_pr |
| import scripts/v4_cases_gen/gen_k1.py | fail (1): IndexError: list index out of range | fail (1): IndexError: list index out of range |
| import scripts/v4_cases_gen/gen_k3.py | fail (1): IndexError: list index out of range | fail (1): IndexError: list index out of range |
| import scripts/v4_cases_gen/gen_k4k6.py | fail (1): IndexError: list index out of range | fail (1): IndexError: list index out of range |
| import scripts/v4_cases_gen/make_v4_A15.py | fail (1): PermissionError: [Errno 13] Permission denied: '/home/azureuser' | fail (1): PermissionError: [Errno 13] Permission denied: '/home/azureuser' |
| import tests/test_v4_feedback.py | fail (1): FileNotFoundError: [Errno 2] No such file or directory: '/home/grigrigri1235/.ca | fail (1): FileNotFoundError: [Errno 2] No such file or directory: '/home/grigrigri1235/kno |
| import tests/test_v4_recompute.py | fail (1): FileNotFoundError: [Errno 2] No such file or directory: '/home/grigrigri1235/.ca | fail (1): FileNotFoundError: [Errno 2] No such file or directory: '/home/grigrigri1235/kno |
| test tests/test_v4_code_facts.py | FAILED (errors=2) | FAILED (errors=2) |
| test tests/test_v4_direct_facts.py | FAILED (errors=8) | FAILED (errors=8) |
| test tests/test_v4_feedback.py | FileNotFoundError: [Errno 2] No such file or directory: '/home/grigrigri1235/.cache/kg_cle | FileNotFoundError: [Errno 2] No such file or directory: '/home/grigrigri1235/knowledge_gra |
| test tests/test_v4_form_check.py | FAILED (errors=1) | FAILED (errors=1) |
| test tests/test_v4_freeze.py | FAILED (failures=1, errors=2) | FAILED (errors=2) |
| test tests/test_v4_guard.py | FAILED (failures=1, errors=35) | FAILED (failures=1, errors=35) |
| test tests/test_v4_metrics.py | FAILED (failures=1) | FAILED (failures=1) |
| test tests/test_v4_no_gold_import.py | FAILED (failures=1) | FAILED (failures=1) |
| test tests/test_v4_question_texts.py | FAILED (errors=4) | OK |
| test tests/test_v4_recompute.py | FileNotFoundError: [Errno 2] No such file or directory: '/home/grigrigri1235/.cache/kg_cle | FileNotFoundError: [Errno 2] No such file or directory: '/home/grigrigri1235/knowledge_gra |
| test tests/test_v4_report.py | FAILED (failures=2) | FAILED (failures=2) |
| test tests/test_v4_run_online.py | FAILED (failures=10, errors=6, skipped=4) | FAILED (failures=10, errors=6, skipped=4) |
| test tests/test_v4_v3_untouched.py | FAILED (failures=3, errors=7) | FAILED (failures=3, errors=7) |
