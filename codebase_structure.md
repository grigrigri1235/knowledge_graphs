# Codebase Structure

Last updated: 2026-11-17 (after the cleanup, `docs/planning/cleanup_2026_11/`).
The original machine path was `/home/azureuser/code_projects`; docs and code still name it.

```text
knowledge_graphs/
├── CLAUDE.md, README.md, codebase_structure.md, knowledge_retention.md, environment.yml
├── final_presentation.md            slide flow of the v4 talk
├── files_given/                     airline_wiki.md, retail_wiki.md (the policy texts)
├── docs/
│   ├── reports/                     tracker_v4_report.md (THE final report) + figures/ (v4_*.png, make_v4_figures.py)
│   ├── paper/                       ShieldAgent_paper.md
│   ├── planning/
│   │   ├── tracker_v4/              v4 plan, pre-registration, reading guide, reading notes
│   │   ├── rules_determinism/       brainstorm: a deterministic rule build (next step)
│   │   └── cleanup_2026_11/         this cleanup: plan, scripts, keep/remove lists, logs
│   └── archive/                     finished work, kept for the record
│       ├── planning/                state_tracking_exp/, tracker_eval_v2/, tracker_v3/
│       └── reports/                 state tracking, eval v2, v3 reports, criticism.md, their figures
└── predicate_correctness/
    ├── from_shieldagent/            the partner's code and data, copied, never edited (PROVENANCE.md, SHA256SUMS)
    ├── guard/                       the guards: *_v4.py (current), *_v3.py and older (v4 imports them)
    ├── state_tracker/               database replay, state, lookups; v3/ (facts, questions, message view); v4/
    ├── fork/                        offline replay base (offline_v3.py) that v4's offline check uses
    ├── scoring/                     v4_* (current) and the v3 offline scorers v4 imports
    ├── scripts/                     v4_* run helpers, v4_cases_gen/, v3_session/ (only the parts v4 calls)
    ├── tests/                       test_v4_*, fixtures_v4/, audit_v4_*, test_no_gold_import, check_copies
    └── output/
        ├── eval_v4/                 v4 cases, dev check, fix rounds, overlays, freeze (v4_freeze.json)
        ├── logs/v4_*                final metrics and diagnosis of B2', B3', H
        ├── eval/                    saved TGR conversations (episodes, gold) read by the offline dev sets
        └── p*_*, predicate_types.*  state-tracking outputs still read by state_tracker code
```

## Notes
- Every file kept under `predicate_correctness/` is v4, imported by v4, or listed in the v4 freeze
  (`output/eval_v4/v4_freeze.json`, 204 files). The list with reasons: `docs/planning/cleanup_2026_11/keep_code.txt`.
- The four frozen v4 plan docs (`predicate_table.md`, `cases_spec.md`, `preregistration_v4.md`,
  `reading_guide_v4.md`) still cite old paths such as `docs/planning/tracker_v3/`; they were not edited.
- Code docstrings still cite old plan paths like `docs/planning/tracker_v3/p9.md`. Those files now live under
  `docs/archive/planning/`. The code was not edited, so the v4 freeze still holds.
- Not in this copy: live run folders (`output/eval_v4/{B2v4,B3v4,Hv4}/`), `output/eval_v3/`, `output/eval_v2/`,
  `output/_llmcache/`. Live and offline runs need them and the tau-bench venv of the original machine.
- Everything removed in the cleanup is in git: commit `9ecc20d` ("Snapshot before cleanup", branch `cleanup`).

## Run the tests
From `predicate_correctness/`: `python3 -B -m unittest tests.test_v4_<name>`. Full set:
`bash scripts/v4_run_tests_parallel.sh 'tests/test_v4_*.py'`. Send output to a log file.
