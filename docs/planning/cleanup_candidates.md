# Cleanup candidates (survey only, nothing deleted)

Date: 2026-10-24. Survey of `/home/azureuser/code_projects` for clutter. Read only: nothing was deleted, moved or edited.
A paid v4 run is live, so every protected path from the brief is left out (eval_v4/**, eval_v3/**, logs/v4_*,
_llmcache/v4_*, the 204-path v4 freeze manifest + freeze_list.txt, guard/, state_tracker/, scoring/, scripts/v4*,
tests/, from_shieldagent/, third_party/, docs/planning/tracker_v4/**, docs/reports/**, CLAUDE.md,
knowledge_retention.md, codebase_structure.md, .git, .claude, memory files).
The only freeze path outside those folders is `predicate_correctness/output/predicate_types.json`; it is kept.

"Refs" = grep for the name over the code (guard, state_tracker, scoring, scripts, tests, fork, from_shieldagent/runner,
src) and the docs (docs/, root .md files). Raw grep output: `predicate_correctness/output/logs/cleanup_*.txt`.
Sizes are `du` sizes. Paths are relative to `/home/azureuser/code_projects`. `PC` = `predicate_correctness`.

Git: `PC/output/` is fully untracked. `.venv_tau3/`, `model_call_example/venv/`, `__pycache__/` and
`PC/from_shieldagent/runs/` are ignored. 1043 tracked files under `yanai_work/` show as **deleted** (`D`): the folder is
gone from disk (also not at `~/yanai_work`), but the last commit (78448b8 "Add yanai_work as regular files") still has it.

## Safe (caches, leftovers, empty files) - total about 0.14 MB

| path | size | files | why it is clutter | refs | git |
|---|---|---|---|---|---|
| `PC/fork/__pycache__/` | 16K | 2 | Python byte cache, rebuilt on import | none needed | ignored |
| `src/__pycache__/` | 32K | 3 | Python byte cache of old v1 code | none needed | 1 tracked (`extractor.cpython-310.pyc`), 2 ignored |
| `PC/output/_tmp_test_eval_v2_fork_624626/` | 88K | 3 | leftover temp folder of one test run (pid in name); the test makes a new one each run | `tests/test_eval_v2_fork.py` (builds the name from its pid; never reads this one) | untracked |
| 40 zero-byte non-v4 logs in `PC/output/logs/` (names in the delete command below; includes `v3_p9_48_w1.md.tmp`, `v3_p9_49_w3.md.tmp`, old p10 marker files) | 0 | 40 | empty files, v2/v3/p-era | 2 named in old v2 docs only (`v2_progress_tick.stop`, `v2_c6w_check.err`) | untracked |

Not listed on purpose: `PC/state_tracker/__pycache__` (12K, protected folder), `PC/guard/run_online_v3.py.pre_b3`
(backup, but in protected guard/). Empty dirs: every empty dir found is either protected (eval_v4, eval_v3, _llmcache/v4_*),
inside a venv, or an expected path (`PC/output/eval/output/repro/p6` is the "empty base path" that `scoring/p10_eval.py`
expects), so none is listed alone. No `.ipynb_checkpoints`, `.pytest_cache`, `*.bak`, `*.orig`, `*.swp` outside
protected folders.

## Likely safe (old outputs nothing current reads) - total about 66.7 MB

| path | size | files | why it is clutter | refs | git |
|---|---|---|---|---|---|
| `PC/output/logs/v3_rc11_rerun_0of3.jsonl`, `_1of3`, `_2of3`, `_0of1` | 41.9M | 4 | v3 rerun dumps, v3 is finished | none (no code, no doc names them) | untracked |
| `PC/output/logs/v3_p12prep_effect_0of3.jsonl`, `_1of3`, `_2of3` | 15.3M | 3 | v3 p12 prep dumps | none | untracked |
| `PC/output/logs/v3_p12_dev_rows_run1.jsonl` | 6.2M | 1 | older copy of `v3_p12_dev_rows.jsonl` (that one is referenced and kept) | none | untracked |
| `PC/output/logs/v3_integ_ptests_164657/` | 96K | 23 | v3 test-run scratch folder | none | untracked |
| `PC/output/logs/v2_ra1_rerun_a1/` | 204K | 2 | v2 rerun scratch folder | none | untracked |
| `PC/output/p10_launch_check/` | 24K | 1 | p10 (v1-era) launch check | none | untracked |
| `PC/output/verify/` | 92K | 10 | v1/v2 verify scripts (vf_*.py) | only `docs/planning/state_tracking_exp/overview.md` (old plan) | untracked |
| `PC/output/_llmcache/eval_v2_smoke_stage_b/` | 1.4M | 33 | v2 smoke-test judge cache | none | untracked |
| `PC/output/_llmcache/v2_smoke_stage_a_luna/` | 2.6M | 114 | v2 smoke-test judge cache | only `scoring/v2_p5_smoke_a_check.py` (v2 check, done) | untracked |
| `PC/output/_llmcache/p10_smoke/` | 1.0M | 40 | p10 smoke judge cache | only `scoring/p10_eval.py`, `p10_smoke_check.py` (v1-era) | untracked |
| `git_commit_schemas.log`, `git_push.log`, `output/git_commit_schemas.log`, `output/recent_git_log.txt` | 16K | 4 | stray git logs at the root | none | tracked (removal shows as git delete) |

## Ask the user (may be wanted) - total about 1,567 MB

| path | size | files | why it may be clutter | refs | git |
|---|---|---|---|---|---|
| `PC/output/_llmcache/v2_stage_a_nano/` | 365M | 14480 | v2 judge cache (nano agent); nano is not in the v4 dev sets | v2 scripts only (`scoring/v2_p6_weak_check.py`; `v2_p7a_stage_a_luna.py` forbids it) | untracked |
| `PC/output/_llmcache/v3_B2_20261023T155537Z_c842d895/` | 225M | 10427 | v3 B2 run judge cache; v3 results live in eval_v3 (kept) | v3 runner only; named in `docs/planning/tracker_v4/reading_notes/*` | untracked |
| `PC/output/_llmcache/v3_B3_20261023T190740Z_9bf882c0/` | 76M | 3086 | v3 B3 judge cache | same as above | untracked |
| `PC/output/_llmcache/v3_B1_20261023T153359Z_77ce4c14/` | 2.5M | 93 | v3 B1 judge cache | same as above | untracked |
| `PC/output/_llmcache/eval_v2_stage_b/` | 172M | 3962 | v2 stage B judge cache; stage_b is not in v4 dev sets | `fork/run_branch.py`, `fork/run_all.py`, `fork/offline_v3.py` (stage_b path) | untracked |
| `PC/output/logs/v3_*` (all other v3 logs) | 133M | 2629 | v3 run/debug logs | 57 of them are named in v3 reports or v3 code, e.g. `v3_p11_rows.jsonl` (89M, read by `scoring/v3_offline_eval.py`), `v3_B2_*_metrics.json` (cited in `docs/reports/tracker_v3_*`) | untracked |
| `PC/output/logs/v2_*`, `p[0-9]*`, `verify_*`, `status_*`, `handoff*`, `final_*`, `scout_*`, `qa_*` | 4.9M | 684 | v1/v2-era logs | ~45 named in old plan docs and v2 report | untracked |
| `PC/output/logs/fix2_*`, `v4report_*`, `agentA_*`, `agentE_*`, `c3_*`, `docs_*`, `results_*` | 0.7M | 154 | written today (v4 fix round 2 and report work), not `v4_` prefixed | none, but they belong to the current v4 work: wait until after the run and report | untracked |
| `PC/output/eval_v2/stage_a/luna/{tgr_frozen,tgr_tracker}/episodes_shard0of4.jsonl.before_resume` | 20M | 2 | resume backups | **`tests/test_v4_v3_untouched.py` checks that nothing in eval_v2 changed**: deleting these will fail that v4 test until its manifest is updated | untracked |
| `PC/output/steps_*_train*.jsonl` | 20.3M | 4 | p2 step records (v1-era) | path built in `state_tracker/paths.py` / `load_steps.py` | untracked |
| `PC/output/p[0-9]*_*`, `implementation_log.md`, `predicate_types.md`, `verify_parts_1_9.md`, `verify_parts_1_10.md` | 17.9M | 36 | state-tracking exp (parts 2-10) results | many: `state_tracker/*.py`, `scoring/p7_results.py`, `guard/offline.py`, `fork/*`, `docs/reports/state_tracking_report.md`. Recommend keep | untracked |
| `PC/output/eval/` | 3.5M | 96 | p10 eval tree (symlinks + metrics) | `scoring/p10_eval.py`, `p10_metrics.py`, v2 checks, old docs | untracked |
| `PC/output/archive/` | 1.4M | 6 | tar.gz of v2 logs from an earlier cleanup (on purpose) | `knowledge_retention.md`, `docs/planning/tracker_eval_v2/cleanup_plan.md` | untracked |
| `model_call_example/venv/` | 82M | 6212 | venv for one example script; rebuild from `requirements.txt` | `README.md`, `docs/planning/starting_exp/p2.md` | ignored |
| `handbook/` | 200M | 6691 | nested git repo (gitlink, no `.gitmodules`), v1-era source data | 16 docs (`docs/file_formats/*`, early plans) | tracked as gitlink |
| `.venv_tau3/` | 238M | 9285 | venv for the tau3 clone; v4 does not use it | `docs/planning/tracker_v4/overview.md` says it "stays on disk" | ignored |
| `ShieldAgent_paper.pdf` | 4.9M | 1 | already converted to `docs/paper/ShieldAgent_paper.md` | `docs/planning/shieldagent_paper_digest_plan.md` | tracked |
| `output/` (root, v1 wiki outputs) | 424K | 29 | v1-era outputs | `docs/planning/wiki_processing_exp/*`, wiki reports | tracked |
| `yanai_work/` | 0 on disk | 1043 in git | already gone from disk; git still tracks it (shows `D`) | `knowledge_retention.md` | tracked, deleted in work tree |

For `yanai_work/`: nothing to delete. Pick one: keep it removed (`git rm -r --cached yanai_work` then commit) or bring
it back (`git checkout -- yanai_work`).

## Checked and kept (not candidates)

- `PC/output/online/` (53M): v4 offline dev reads `ours.p10_luna_train` from here (`fork/offline_v3.py`, used by `scoring/v4_offline_eval.py`).
- `PC/output/_llmcache/p10_luna_train`, `p10_luna_val`, `p10_nano_train`, `v2_stage_a_luna` (~387M): default judge caches that `fork/offline_v3.py` reads for the v4 dev sets.
- `PC/output/eval_v2/` (381M, rest of it): hashed by `tests/test_v4_v3_untouched.py`; stage_a.luna is a v4 dev set.
- `PC/fork/`: imported by v4 code (`fork/offline_v3.py`).
- `PC/output/predicate_types.json`: in the v4 freeze.

## After the run only (protected now)

- `PC/output/eval_v4/dryrun/` (39M): maybe, after the run. Note: still named by `guard/soft_stop_v4.py`, `scoring/v4_report.py`, `scripts/v4_dry_all.sh`, so check before removing.
- Also seen in eval_v4, not candidates: `backup_pre_fix2/` (33M, cited in `docs/reports/tracker_v4_report.md`), `v4_freeze.json.superseded_*` (2), `backup_pre_fix2/preregistration_v4.md.bak`.

## Delete commands (NOT run)

Run from anywhere; each block names its paths. No wildcard touches a protected folder (the log globs only match
non-`v4_` names inside `PC/output/logs`).

### Safe

```bash
cd /home/azureuser/code_projects
rm -rf predicate_correctness/fork/__pycache__ src/__pycache__ \
  predicate_correctness/output/_tmp_test_eval_v2_fork_624626
cd /home/azureuser/code_projects/predicate_correctness/output/logs
rm -rf v3_full_cp.txt v3_crit_all_07.log v3_p9_49_w3.md.tmp v3_k2rev_unc_run.txt p10_smoke_marker_before \
  v3_rw_grep_calls.txt v3_main_b3log.log v3_main_dfd.log v3_main_b3stoplog.log v2_progress_tick.stop v3_main_hc.log \
  v2_report_numbers.err v3_k2fix_tests_driver2.log v3_main_prompt_log.log p10_launch_marker v2_progress_tick.log \
  v3_main_b3rep.log v3_main_b3diag.log v3_k2fix_tests_driver.log v3_dry_metrics_stderr.log v3_B2_auto.log \
  p10_audit_marker_before_dry v3_diag_grep92.txt p10_runs_marker_before v3_main_asks.log v3_main_harmlog.log \
  p10_s89_marker_before v2_progress_tick.err v3_main_log5.log v2_c6w_check.err v3_p9_48_w1.md.tmp \
  v3_main_kr_renum.log v2_cleanup_scan.err v3_main_names.log v3_k2rev_k1stats_run.txt verify_pycache.log \
  p10_val_marker_before v3_main_ll.log v3_main_rwf.log p6_edit_view2.log
```

### Likely safe

```bash
cd /home/azureuser/code_projects/predicate_correctness/output
rm -rf logs/v3_rc11_rerun_0of3.jsonl logs/v3_rc11_rerun_1of3.jsonl logs/v3_rc11_rerun_2of3.jsonl \
  logs/v3_rc11_rerun_0of1.jsonl logs/v3_p12prep_effect_0of3.jsonl logs/v3_p12prep_effect_1of3.jsonl \
  logs/v3_p12prep_effect_2of3.jsonl logs/v3_p12_dev_rows_run1.jsonl \
  logs/v3_integ_ptests_164657 logs/v2_ra1_rerun_a1 p10_launch_check verify \
  _llmcache/eval_v2_smoke_stage_b _llmcache/v2_smoke_stage_a_luna _llmcache/p10_smoke
cd /home/azureuser/code_projects
rm -rf git_commit_schemas.log git_push.log output/git_commit_schemas.log output/recent_git_log.txt
```

### Ask the user (one line per item; run only the ones approved, and only after the live run)

```bash
cd /home/azureuser/code_projects/predicate_correctness/output
rm -rf _llmcache/v2_stage_a_nano
rm -rf _llmcache/v3_B2_20261023T155537Z_c842d895 _llmcache/v3_B3_20261023T190740Z_9bf882c0 _llmcache/v3_B1_20261023T153359Z_77ce4c14
rm -rf _llmcache/eval_v2_stage_b
rm -rf logs/v3_*                      # also removes the 57 v3 logs named in v3 reports/code
rm -rf logs/v2_* logs/p[0-9]* logs/verify_* logs/status_* logs/handoff* logs/final_* logs/scout_* logs/qa_*
rm -rf logs/fix2_* logs/v4report_* logs/agentA_* logs/agentE_* logs/c3_* logs/docs_* logs/results_*
rm -rf eval_v2/stage_a/luna/tgr_frozen/episodes_shard0of4.jsonl.before_resume eval_v2/stage_a/luna/tgr_tracker/episodes_shard0of4.jsonl.before_resume
rm -rf steps_luna_train_v5_airline.jsonl steps_luna_train_v5_retail.jsonl steps_nano_train_airline.jsonl steps_nano_train_retail.jsonl
rm -rf p[0-9]*_* implementation_log.md predicate_types.md verify_parts_1_9.md verify_parts_1_10.md   # recommend keep
rm -rf eval archive
cd /home/azureuser/code_projects
rm -rf model_call_example/venv
rm -rf handbook
rm -rf .venv_tau3
rm -rf ShieldAgent_paper.pdf
rm -rf output
```

## Round 2: unused files by count

Survey time: 2026-10-24 10:41:31. Same read-only rules and protected list as above. The Safe and Likely-safe groups
from round 1 are already gone, so they are not counted again.

"Unused" means the file name, or the name without its extension, does not appear in: `docs/reports/**`, the current
code (`PC/guard`, `state_tracker`, `scoring`, `scripts`, `tests`, `fork`), `CLAUDE.md`, `knowledge_retention.md` or
`codebase_structure.md`. For planning files, `docs/planning/tracker_v4/**` also counts as a current doc.
Log names that code builds on the fly are kept too (globs and f-strings in code: `v2_stage_a_{nano,luna}_s*`,
`v2_stage_b_*`, `v2_p7b_dry_stage_b_*`, `v2_r2_*`, `v3_p11_*`, `v3_k2fix_t_test_*`, `v3_wf_result_*`,
`v3_B1_*`, `v3_B2_B2_*`, `v3_B3_B3_*`, `identity_*`). Raw data: `PC/output/logs/cleanup_r2_*.txt`.

### Group 1: `PC/output/logs/`, non-`v4_` files with no reference - 3,297 files (about 24 MB)

3,478 non-`v4_`, non-`cleanup_` entries exist. **181 are kept** because a report or current code names them
(list at the end of this section). The other 3,297:

| group | files | size | reason |
|---|---|---|---|
| 1A `p1_*` ... `p10_*` (state-tracking parts) | 506 | 3.0M | Oct 21-22 work logs of the first experiment; the report cites none of them |
| 1A `v2_*` | 82 | 0.8M | eval_v2 work logs nothing names (the cited ones and the run logs are kept) |
| 1A misc: `verify_*` 29, `status_*` 8, `final_*` 2, `qa_*` 2, `handoff*` 1, `scout_*` 1 | 43 | 0.3M | one-off checks and status notes, Oct 21-22 |
| 1B `v3_p1*`...`v3_p14*` (v3 parts) | 1,128 | 8.2M | v3 part-by-part work logs; the rows/meta files reports use are kept |
| 1B `v3_crit*`, `v3_design*`, `v3_rev*`, `v3_hrev*`, `v3_verfix*` | 349 | 3.1M | critic and design review rounds, done |
| 1B `v3_main_*` | 334 | 0.6M | main-chat scratch output (greps, ls, small checks) |
| 1B `v3_rc*` | 177 | 1.5M | review-cycle logs (rc1, rc4, rc10, rc11), not cited |
| 1B `v3_k2*`, `v3_kr*` | 166 | 2.1M | K2 fix rounds and checks; the test logs read by `run_tests.sh` are kept |
| 1B `v3_b3*`, `v3_B*` (no run id) | 108 | 0.9M | B-run prep and diag notes; the run-id logs and metrics are kept |
| 1B `v3_diag*`, `v3_dfd*` | 76 | 1.4M | diagnosis scratch |
| 1B other v3 (`tqa`, `harm`, `wf`, `rw*`, `ll`, `scout`, `integ`, `recount`, `narr`, ...) | 174 | 1.6M | small one-off v3 checks |
| 1C v4-era, not `v4_` prefixed: `fix2_*` 73, `c3_*` 26, `v4report_*` 25, `agentE_*` 13, `agentA_*` 8, `docs_*` 5, `results_*` 4 | 154 | 0.7M | written today by the v4 fix and report work. **Off by default (G1C=0)**: approve only after the run and report are done |
| **total group 1** | **3,297** | **~24M** | 1A 631, 1B 2,512, 1C 154 |

### Group 2: `docs/planning/`, legacy plans no report or current doc names - 46 files

Kept: `state_tracking_exp/`, `tracker_eval_v2/`, `tracker_v3/` (cited by reports, codebase_structure.md,
knowledge_retention.md and 5-50 code files), `tracker_v4/` (protected) and this file.

| path | files | git | reason |
|---|---|---|---|
| `docs/planning/wiki_processing_exp/` | 12 | tracked | Oct 9 wiki experiment plan; no report or current doc names the folder |
| `docs/planning/fork_test_exp/` | 9 | untracked | Oct 22 fork-test plan, not referenced |
| `docs/planning/starting_exp/` | 8 | tracked | Oct 7 first experiment plan |
| `docs/planning/retail500_exp/` | 8 | untracked | Oct 22 retail-500 plan, not referenced |
| `docs/planning/predicates_correctness/` | 2 | untracked | Oct 21 brainstorm rewrite notes |
| `docs/planning/slide_show_plan.md` | 1 | untracked | slide plan, not referenced |
| `docs/planning/document_processing_experiment_plan.md`, `experimentation_plan.md`, `graph_creation_documentation_plan.md`, `graph_structure_documentation_plan.md`, `shieldagent_paper_digest_plan.md`, `simplify_knowledge_retention_plan.md` | 6 | tracked | early one-file plans (Oct 2-10) |
| **total group 2** | **46** | 26 tracked, 20 untracked | |

### Group 3: other stray files with no reference - 27 files

| path | files | git | reason |
|---|---|---|---|
| root `output/`: `airline_dry_run.txt`, `airline_policies.json`, `expected_ltl_rules_output_review.md`, `expected_policies_output_review.md`, `grep_p7.txt`, `prompt_preview.txt`, `retail_dry_run.txt`, `retail_policies.json`, `steps_p7.jsonl`, `steps_p7_early.jsonl`, `wiki_action_circuits_review.md`, `wiki_guardrail_demo_review.md`, `wiki_ltl_prompt_preview.txt`, `wiki_prompt_preview.txt`, `wiki_vr_predicates_list.txt`, `wiki_vr_prompt_preview.txt`, `wiki_vr_review.md` | 17 | tracked | v1 dry runs, prompt previews and review notes; the 10 root `output/` files the wiki reports cite are kept |
| `files_given/`: `legal_document_classifications.json`, `people-group_document_classifications.json`, `people-policies_document_classification.json`, `security_document_classifications.json`, `task_airline.py`, `tasks_retail.py` | 6 | tracked | given input files nothing reads (the 3 wiki .md files are cited and kept). They came from the user, so confirm first |
| `tests/test_extractor.py` (root) | 1 | tracked | v1 test for `src/extractor.py`; nothing names it |
| `ShieldAgent_paper.pdf` | 1 | tracked | only a legacy plan names it; `docs/paper/ShieldAgent_paper.md` is the converted copy |
| `PC/output/verify_parts_1_9.md`, `verify_parts_1_10.md` | 2 | untracked | v1 verify notes; only the old `state_tracking_exp/overview.md` names them |
| **total group 3** | **27** | 25 tracked, 2 untracked | |

Checked and kept in group 3: `src/*.py`, `README.md`, `environment.yml`, `handbook_files_to_focus.md`,
`PC/initial_brainstorming.md`, `PC/docs/planning/tracker_v4/dev_check_fail_notes.md`, the 3 cited `files_given/*.md`,
all `PC/output/p*_*` files (current state_tracker/scoring code reads them), and `PC/output/steps_*.jsonl` (their path
is built in `state_tracker/paths.py`).

### Round 2 totals

| group | files |
|---|---|
| 1A old logs (p*, v2, misc) | 631 |
| 1B v3 logs | 2,512 |
| 1C v4-era logs (off by default) | 154 |
| 2 legacy planning | 46 |
| 3 strays | 27 |
| **all** | **3,370** (3,216 with 1C left off) |

51 of these files are tracked in git (26 in group 2, 25 in group 3). Deleting them shows up as `D` in
`git status`, which needs a commit later.

### Archive-then-delete command (NOT run)

Set each `G*` switch to 1 (approved) or 0 (skip). The script touches only files older than the survey time and never
a `v4_*` or `cleanup_*` log. It also skips the 181 kept logs, which it reads from the block below. It stops if the
archive already exists, and it deletes the originals only after the archive's file list matches exactly.

```bash
cd /home/azureuser/code_projects && bash -c '
G1A=1; G1B=1; G1C=0; G2=1; G3=1
CUT="2026-10-24 10:41:31"
MD=docs/planning/cleanup_candidates.md
LOGS=predicate_correctness/output/logs
A=predicate_correctness/output/archive/cleanup_round2_$(date +%Y%m%d).tar.gz
[ -e "$A" ] && { echo "archive exists: $A"; exit 1; }
LIST=$(mktemp); KEEP=$(mktemp)
sed -n "/^KEEP_LIST_START$/,/^KEEP_LIST_END$/p" "$MD" | grep -v "^KEEP_LIST_" > "$KEEP"
[ "$(wc -l < "$KEEP")" -eq 181 ] || { echo "keep list not found"; exit 1; }
find "$LOGS" -maxdepth 1 -type f ! -name "v4_*" ! -name "cleanup_*" ! -newermt "$CUT" -printf "%f\n" | sort |
  grep -vxF -f "$KEEP" | while read -r n; do
    case "$n" in
      fix2_*|v4report_*|agentA_*|agentE_*|c3_*|docs_*|results_*) g=$G1C ;;
      v3_*) g=$G1B ;;
      *) g=$G1A ;;
    esac
    if [ "$g" = 1 ]; then echo "$LOGS/$n"; fi
  done >> "$LIST"
PLAN="docs/planning/wiki_processing_exp docs/planning/fork_test_exp docs/planning/starting_exp docs/planning/retail500_exp docs/planning/predicates_correctness docs/planning/slide_show_plan.md docs/planning/document_processing_experiment_plan.md docs/planning/experimentation_plan.md docs/planning/graph_creation_documentation_plan.md docs/planning/graph_structure_documentation_plan.md docs/planning/shieldagent_paper_digest_plan.md docs/planning/simplify_knowledge_retention_plan.md"
if [ "$G2" = 1 ]; then find $PLAN -type f | sort >> "$LIST"; fi
STRAY="output/airline_dry_run.txt output/airline_policies.json output/expected_ltl_rules_output_review.md output/expected_policies_output_review.md output/grep_p7.txt output/prompt_preview.txt output/retail_dry_run.txt output/retail_policies.json output/steps_p7.jsonl output/steps_p7_early.jsonl output/wiki_action_circuits_review.md output/wiki_guardrail_demo_review.md output/wiki_ltl_prompt_preview.txt output/wiki_prompt_preview.txt output/wiki_vr_predicates_list.txt output/wiki_vr_prompt_preview.txt output/wiki_vr_review.md files_given/legal_document_classifications.json files_given/people-group_document_classifications.json files_given/people-policies_document_classification.json files_given/security_document_classifications.json files_given/task_airline.py files_given/tasks_retail.py tests/test_extractor.py ShieldAgent_paper.pdf predicate_correctness/output/verify_parts_1_9.md predicate_correctness/output/verify_parts_1_10.md"
if [ "$G3" = 1 ]; then for f in $STRAY; do [ -f "$f" ] && echo "$f"; done >> "$LIST"; fi
[ -s "$LIST" ] || { echo "nothing selected"; exit 1; }
echo "files selected: $(wc -l < "$LIST")"
tar -czf "$A" -T "$LIST" || exit 1
tar -tzf "$A" | sort > "$LIST.chk"; sort "$LIST" | diff -q - "$LIST.chk" || { echo "archive check failed, nothing deleted"; exit 1; }
xargs -d "\n" rm -f -- < "$LIST"
if [ "$G2" = 1 ]; then for d in $PLAN; do [ -d "$d" ] && find "$d" -depth -type d -empty -delete; done; fi
echo "archived to $A and deleted $(wc -l < "$LIST") files"; rm -f "$LIST" "$LIST.chk" "$KEEP"
'
```

To undo: `cd /home/azureuser/code_projects && tar -xzf predicate_correctness/output/archive/cleanup_round2_<date>.tar.gz`.

### Kept logs (181, read by the command above; do not edit the marker lines)

<details><summary>show the 181 kept log names</summary>

```
KEEP_LIST_START
p10_audit_feedback.log
p10_audit_state.log
p10_guard_offline.log
p10_luna_train_retail.log
p10_metrics.log
p10_nano_train_retail.log
p10_report_extra.log
p2_load_steps.log
p3_type_counts.log
p4_replay_check.log
p6_replay.log
p7_check_answers.log
p7_sample.log
p8_decide_again.log
v2_c6s_check.err
v2_c6s_check.json
v2_c6w_check.json
v2_c6w_extra.err
v2_c6w_extra.json
v2_i1_counts.json
v2_i1_counts.log
v2_i1_examples.log
v2_i1_probes.json
v2_i1_probes.log
v2_p1_checks.log
v2_p1_venv_check.log
v2_p7b_counts.json
v2_p7b_dry_stage_b_1.log
v2_p7b_dry_stage_b_2.log
v2_p7b_dry_stage_b_3.log
v2_p7b_dry_stage_b_4.log
v2_p7b_plan.json
v2_r1_run.log
v2_r1_run2.log
v2_r2_fakes_selftest.log
v2_r2_ref_rebuild.log
v2_report_figures.log
v2_report_numbers.json
v2_smoke_stage_a.log
v2_stage_a_luna_s0.log
v2_stage_a_luna_s0_resume1.log
v2_stage_a_luna_s1.log
v2_stage_a_luna_s2.log
v2_stage_a_luna_s3.log
v2_stage_a_nano_dry.log
v2_stage_a_nano_s0.log
v2_stage_a_nano_s1.log
v2_stage_a_nano_s2.log
v2_stage_a_nano_s3.log
v2_stage_b_1.log
v2_stage_b_2.log
v2_stage_b_3.log
v2_stage_b_4.log
v3_B1_B1_20261023T153359Z_77ce4c14_dryrun.log
v3_B1_B1_20261023T153359Z_77ce4c14_s0.log
v3_B1_B1_20261023T153359Z_77ce4c14_summary.log
v3_B1_launch.txt
v3_B1_new_id.txt
v3_B1_start.txt
v3_B2_B2_20261023T155537Z_c842d895_dryrun_s0.log
v3_B2_B2_20261023T155537Z_c842d895_dryrun_s1.log
v3_B2_B2_20261023T155537Z_c842d895_dryrun_s2.log
v3_B2_B2_20261023T155537Z_c842d895_dryrun_s3.log
v3_B2_B2_20261023T155537Z_c842d895_interim.log
v3_B2_B2_20261023T155537Z_c842d895_metrics.json
v3_B2_B2_20261023T155537Z_c842d895_metrics.log
v3_B2_B2_20261023T155537Z_c842d895_ps.txt
v3_B2_B2_20261023T155537Z_c842d895_report.log
v3_B2_B2_20261023T155537Z_c842d895_s0.log
v3_B2_B2_20261023T155537Z_c842d895_s1.log
v3_B2_B2_20261023T155537Z_c842d895_s2.log
v3_B2_B2_20261023T155537Z_c842d895_s3.log
v3_B3_B3_20261023T190740Z_9bf882c0_dryrun_s0.log
v3_B3_B3_20261023T190740Z_9bf882c0_dryrun_s1.log
v3_B3_B3_20261023T190740Z_9bf882c0_dryrun_s2.log
v3_B3_B3_20261023T190740Z_9bf882c0_dryrun_s3.log
v3_B3_B3_20261023T190740Z_9bf882c0_interim.log
v3_B3_B3_20261023T190740Z_9bf882c0_interim2.log
v3_B3_B3_20261023T190740Z_9bf882c0_metrics.json
v3_B3_B3_20261023T190740Z_9bf882c0_metrics.log
v3_B3_B3_20261023T190740Z_9bf882c0_ps.txt
v3_B3_B3_20261023T190740Z_9bf882c0_s0.log
v3_B3_B3_20261023T190740Z_9bf882c0_s1.log
v3_B3_B3_20261023T190740Z_9bf882c0_s2.log
v3_B3_B3_20261023T190740Z_9bf882c0_s3.log
v3_crit_d_result.md
v3_harm_replay_B2.log
v3_harm_replay_B3.log
v3_harm_report.log
v3_k2fix_t_test_no_gold_import.log
v3_k2fix_t_test_v3_audit.log
v3_k2fix_t_test_v3_classify.log
v3_k2fix_t_test_v3_code_facts.log
v3_k2fix_t_test_v3_direct_facts.log
v3_k2fix_t_test_v3_facts_format.log
v3_k2fix_t_test_v3_feedback.log
v3_k2fix_t_test_v3_frozen.log
v3_k2fix_t_test_v3_guard.log
v3_k2fix_t_test_v3_message_view.log
v3_k2fix_t_test_v3_offline.log
v3_k2fix_t_test_v3_online_metrics.log
v3_k2fix_t_test_v3_p12.log
v3_k2fix_t_test_v3_p14_report.log
v3_k2fix_t_test_v3_questions.log
v3_k2fix_t_test_v3_rule_table.log
v3_k2fix_t_test_v3_run_online.log
v3_k2fix_t_test_v3_soft_stop.log
v3_k2fix_t_test_v3_structure_facts.log
v3_k2fix_t_test_v3_tool_check.log
v3_k2fix_tests_summary.log
v3_ll_card_check.txt
v3_p10_check_details.json
v3_p11_00_ls.log
v3_p11_01_survey.log
v3_p11_02_audit_head.log
v3_p11_03_peek.log
v3_p11_04_i1.log
v3_p11_05_i1json.log
v3_p11_06_readings.log
v3_p11_07_ff.log
v3_p11_08_readfacts.log
v3_p11_09_helpers.log
v3_p11_10_p7api.log
v3_p11_11_events.log
v3_p11_12_p10det.log
v3_p11_13_p6p7.log
v3_p11_14_p7code.log
v3_p11_15_p7det.log
v3_p11_16_p7core.log
v3_p11_17_rules.log
v3_p11_18_v2guard.log
v3_p11_19_overlay.log
v3_p11_20_v2lookups.log
v3_p11_21_mvhelpers.log
v3_p11_22_safety.log
v3_p11_23_foreach.log
v3_p11_24_p4json.log
v3_p11_25_smoke.log
v3_p11_26_smokecheck.log
v3_p11_27_smoke_var.log
v3_p11_28_fullrun.log
v3_p11_29_gates_grep.log
v3_p11_30_gates2.log
v3_p11_31_gates3.log
v3_p11_32_gates4.log
v3_p11_33_palette.log
v3_p11_34_p7rows.log
v3_p11_35_mpl.log
v3_p11_36_progress.log
v3_p11_37_progress.log
v3_p11_38_runend.log
v3_p11_39_status.log
v3_p11_40_analyse.log
v3_p11_41_analyse_tail.log
v3_p11_42_analyse.log
v3_p11_43_tail.log
v3_p11_44_final.log
v3_p11_45_analyse.log
v3_p11_46_final.log
v3_p11_rows.jsonl
v3_p11_run_meta.json
v3_p11_variant_meta.json
v3_p11_variant_rows.jsonl
v3_p12_03_labels_holdout.log
v3_p12_dev_rows.jsonl
v3_p12_dev_run_meta.json
v3_p12_holdout_rows.jsonl
v3_p12_holdout_run_meta.json
v3_p12rep_run.log
v3_p13a_tests.log
v3_p13d_train.json
v3_p13d_train.log
v3_p3_labels.log
v3_p7_run_details.json
v3_p7_screens_set3_before_rule.json
v3_recomp_B2_real.txt
v3_recount_run.log
v3_scout_tool_errors.log
v3_tqa_data.json
v3_wf_result_a.json
v3_wf_result_b.json
KEEP_LIST_END
```

</details>
