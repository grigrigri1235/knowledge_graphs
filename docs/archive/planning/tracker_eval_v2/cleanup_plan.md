# Cleanup plan (eval v2 clutter)

**Done 2026-10-22 19:36-19:45 UTC, approved by the user ("archive then remove").** Real counts: 1,033 logs and 40
other files archived (34 one-off scripts, not 38 as first counted, + 6 leftovers). Log: `predicate_correctness/output/archive/cleanup_log.txt`.

Date 2026-10-22, 19:55 UTC. Asked by the user: "remove unneeded files, organise the rest while making sure nothing
breaks; update knowledge_retention.md; add a prompt for the next agent". `predicate_correctness/` is not in git, so a
deleted file cannot be brought back. That is why everything removed goes into 2 archive files first.

## What is clutter (scan: `predicate_correctness/scoring/v2_cleanup_scan.py`)
| what | count | why it is not needed | what happens |
|---|---|---|---|
| eval v2 command-output logs named by no doc, script or report | 1,033 of 1,161 | raw shell output (CLAUDE.md rule 8); the numbers are in the reports | packed into `output/archive/eval_v2_logs_20261022.tar.gz`, then removed |
| one-off audit and re-audit scripts in `tests/` (`audit_v2_a1..a5_*`, `audit_v2_ra1_*`, `audit_v2_ra2_*`) | 38 | used once; the results are in `checks/audit*.md` | packed into `output/archive/eval_v2_audit_scripts_20261022.tar.gz`, then removed; a note in `audit.md` says where they are |
| copied log sections `checks/log_part*.md`; markers `checks/smoke_marker`, `checks/smoke_before.txt` | 5 | the log sections are already in `implementation_log.md`; the markers were only for one check | into the scripts archive, then removed |
| one-off helpers of the main chat (`scoring/v2_cleanup_scan.py`; `output/logs/v2_main_banner.py`) | 2 | used once | into the archives, then removed |

## What stays, and how it is organised
- **Kept as is (code that works and is tested):** `guard/`, `fork/`, `state_tracker/`, `tests/test_eval_v2_*.py`.
- **Kept as reusable audit tools:** `tests/audit_v2_ref_*.py` (independent references) and
  `tests/audit_v2_replay_fakes.py` (replays a saved conversation with fake LLMs). They are useful for the next audit.
- **Moved:** `tests/idea_v2_i1_*.py` (3 analysis scripts, not tests) → `scoring/`. They are at the same folder
  depth, so their paths still work. The references in `idea_track_more_facts.md` are updated.
- **Kept in place:** the 128 logs that a report names (evidence), all run data (`stage_a/`, `stage_b/`, `smoke/`),
  the fork point files, and the judge caches (`output/_llmcache/`, 921 MB). Stage B seeds read the caches if Stage B
  is ever resumed.
- **New index:** `output/eval_v2/README.md`, with one line per file or folder.
- **`HANDOFF.md`:** a top note says the plan is stopped and points to `knowledge_retention.md` and the report.

## Checks that nothing broke
1. Every archive lists exactly the files it should, before any file is removed.
2. The full test suite passes (288 tests).
3. Every kept `.py` file still compiles. The 3 moved scripts run their `--help` (or import) without errors.
4. A new scan of the kept docs and code for names of removed files: each remaining mention points to the archive.

## Then
- Rewrite `knowledge_retention.md`: the current state, short legacy history, a file map, the working rules, and a
  last section with a prompt for the next agent.
