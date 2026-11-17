# Part 2: what v4 still needs

Script: `import_graph.py`. Output: `keep_code.txt` (file + why), `remove_code.txt`. Logs: `logs/p2_*.log`.

## Method
- Start: v4 entry points (`guard/*_v4.py`, `state_tracker/v4/`, `scoring/v4_*`, `scripts/v4_*`,
  `scripts/v4_cases_gen/`, `scripts/build_questions_A4.py`, `tests/test_v4_*`, `tests/audit_v4_*`,
  `tests/fixtures_v4/`), plus v4 data (`output/eval_v4/`, `output/logs/v4_*`, `output/predicate_types.json`)
  and `from_shieldagent/` (kept whole).
- Follow real Python imports (ast). Data files and shell scripts are followed by name.
- Round 1 also followed .py names found in any text. It kept almost everything (539 of 612), because some tests
  list every v3 file by name. Round 2 follows .py files by import only (or from a shell script).
- `tests/test_v4_v3_untouched.py` is dropped, not followed. Its only job was to prove v3 files did not change
  during the v4 runs. That is done.
- `importlib` constants checked by hand (`logs/p2_modconst.log`): all point to kept modules.

## Result
| | files |
|---|---|
| under `predicate_correctness/` | 612 |
| keep | 419, plus `tests/check_copies.py` (checks the partner copies) = 420 |
| remove | 192 |
| in the v4 freeze list and in the remove list | 0 |

v4 really sits on v3: it keeps `guard/tgr_tracker_v3.py`, `run_online_v3.py`, `state_tracker/v3/` (minus
`rule_table.py`), most top-level `state_tracker/`, part of `fork/`, and the v3 offline scorers.

Removed groups: v1/v2/p10 scorers, v3 report and label scripts, most of `scripts/v3_session/`, the v1-v3 tests,
the `gold_v2` and metrics files in `output/eval/`, old `output/p*` notes no kept code reads.

## Found along the way
- `predicate_correctness/docs/planning/tracker_v4/dev_check_fail_notes.md` is not a copy. It is the first half of
  the note (the fail), and `docs/planning/tracker_v4/dev_check_fail_notes.md` is the second half (fix round 2).
  They get merged into the docs one.
- `files_given/wiki.md` is byte-equal to `files_given/retail_wiki.md`.

## Limit
Paths built at run time from pieces (f-strings) are not seen. Part 7 checks imports, not every data path.
