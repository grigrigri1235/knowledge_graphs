# Tracker v4 P1 build: the common brief for every build agent (binding)

The user APPROVED `overview.md` (2026-10-23 ~21:55 UTC). Every build agent follows this file, plus:
- `overview.md`;
- `code_change_map.md`: §0 (ground rules), §0.2 (interfaces), §0.3 (overlays), and the rows of the files you own;
- `predicate_table.md`: the authority for every predicate's value definition, once it exists. Until then, follow
  `code_change_map.md` §1.1 and `reading_notes/tiny_questions.md`.

Where this file and `code_change_map.md` differ, **this file wins**.

## Hard rules
1. **$0 only.** No paid LLM call, no network call. Tests use fake backends. Never build a τ-bench env with
   `user_strategy="llm"`. The real backends must refuse to run without the main chat's approval flag.
2. **Never edit a v2 or v3 file.** That includes v3 tests and `questions_v3.json`. Copy to new v4 files. Never
   write under `~/ShieldAgent`, `~/opt`, `~/venvs`. Nothing under `third_party/` is used.
3. **Purity.**
   - Never open v3's B2, B3 or hold-out conversations, their tiny-answer logs, or `questions_answers.jsonl`
     (the dev-check agent A16 may read it, and only for the 200 dev conversations).
   - Never the partner's test 66.
   - Few-shot examples and made-up cases are written from the v1 policy text only.
   - (Added 2026-10-24) A script that counts forms reads only the 6 database json files and the 2 `wiki.md`
     files, never task instructions or expected actions. The message check reads only the 200 dev conversations
     (4 dev sets × 50). See `session1_process_log.md` §9.
4. **Rules and predicates are frozen.** The same 98 rules and 66 predicate names. Only parts, sources,
   questions and messages change.
5. **Bash output** to `predicate_correctness/output/logs/v4_<your agent id>_*.txt`, read with Read.
6. **Python:** `-B`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONHASHSEED=0`.
   - Runner and guard code: `~/venvs/tau-bench/bin/python`.
   - Analysis: `/home/azureuser/miniconda3/bin/python3` (stdlib).
   - Run from `predicate_correctness/` as modules.
7. **Own only your files.** For a shared fact or question file, write an **overlay** (`code_change_map.md` §0.3);
   the main chat merges.
8. Every v4 helper name ends in `_v4`. Reuse v3's exception classes.
9. When done, your final reply gives: your files, your test results, and the interface you depend on or
   publish.

## Name decisions (override `code_change_map.md`)
| thing | name |
|---|---|
| steps | `B1v4` → `B2v4` (99 × 3) + `B3v4` (64 × 1) + `Hv4` (weak agent, 99 × 1). `DEV20v4` was **dropped** on 2026-10-24 (seen by the build). **Live arms (2026-10-24):** B1v4 and B2v4 run only `direct_facts_v4` + `tgr_tracker_v4` (old arms `none`, `direct`, `tgr_frozen`, `tgr_tracker_v3` reused from v3 run `B2_20261023T155537Z_c842d895`); B3v4 runs the 2 new arms on 64 tasks + the 4 old arms on the 15 tasks missing from v3 run `B3_20261023T190740Z_9bf882c0`; Hv4 runs all 6 arms live |
| freeze script | `scoring/v4_freeze.py`, manifest `output/eval_v4/v4_freeze.json` (owned by agent P1b) |
| after-run chain | `scoring/v4_after_run.sh` (P1b) |
| halfway check | `scoring/v4_online_interim.py` (P1b) |
| metrics | `scoring/v4_online_metrics.py` (P1b) |
| runner and soft stop | `guard/run_online_v4.py`, `guard/soft_stop_v4.py` (P1e) |
| Direct + facts | `guard/direct_facts_v4.py`: **done**, a COPY with `FACTS_SOURCE` switch / `register_facts_provider("v4", factory)` |
| pre-registration and reading guide | `docs/planning/tracker_v4/preregistration_v4.md`, `reading_guide_v4.md` (**done**) |
| form check | `scoring/v4_form_check.py`, `output/eval_v4/form_check.md` (P1c) |
| K1 go-ahead helpers | `state_tracker/v4/helpers_go_ahead_v4.py` (A2) |
| other code-fact helpers (ownership, K15, K12 kind) | `state_tracker/v4/helpers_v4.py` (A5) |
| v4 guard record | must save `blocking_facts`, the facts a block rests on (the diagnosis needs it), plus `rec["v4"]` per `code_change_map.md` §0.2 item 6 |
