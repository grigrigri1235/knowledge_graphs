**UNUSED — DEV20v4 dropped 2026-10-24 (seen by the build).** The v4 form check read these tasks while building v4, so they are not unseen. Kept as a record only. See `docs/planning/tracker_v4/preregistration_v4.md` §15.

# Tracker v4 P1: is τ-bench v1's retail dev split (20 tasks) unused?

**Verdict: UNUSED.** It can be the small unseen side check (plan §4). Nobody ran it, neither we nor the partner.
It does not copy any train-500 task. Two flags below. They do not change the verdict, but the report should
state them.

## 1. Was it used? Evidence says never
| check | result |
|---|---|
| Dev task text in any saved file. I took one 45-char string from each dev instruction, unique against train 500 and test 69, and searched every text file under `predicate_correctness/` (2.4 GB, incl. `output/`, `_llmcache/`, run folders), `~/ShieldAgent/` (3.4 GB, incl. `output/`, `docs/`) and `docs/` | **0 files** (only this check's own logs) |
| Positive control, our tree: a train-500 instruction (train 80) | found in 5 files (`eval_v2/stage_b/...train80...`), so saved runs keep the instruction text |
| Positive control, partner tree: a test-split instruction from the partner's train group (retail test 2) | found in 1,946 files under `~/ShieldAgent/output` (runs and `_llmcache`) |
| Run metadata with `"task_split": "dev"` (our outputs and partner outputs) | 0 |
| Partner runner `exp_core/run_online.py` | always `get_env(..., task_split="test", ...)`. `--tasks train/val/test` is a `splits.json` label over the τ-bench **test** file. "luna-dev" is a model profile name and `tgr_dev_it*` are dev runs on the partner's train group, not the dev split |
| Partner docs | `docs/reproduction/data_feasibility.md` only lists `tasks_dev.py (20)` and proposes it as possible future training data (l.162-164). `RESULTS.md` and `docs/tgr/*report*.md` only say "luna-dev" (the profile) |
| Our code | `scoring/v2_task_files.py`, `fork/rebuild_tasks.py`, `tests/audit_v2_ref_stage_a.py`: file lists or sha checks only. `tests/test_eval_v2_fork.py:1064`: the v2 runner **refuses** `task_split="dev"`. `guard/run_online_v4.py` (being built) has it as the optional DEV20v4 step |
| Our docs | `knowledge_retention.md` l.114 names it ("dev 20 follow one easy template"). No result anywhere |

## 2. Does it repeat train-500 tasks?
Numbers come from `scoring/v4_form_check.py` (table in `form_check.md`, last section; raw data in `form_check.json` under `dev20`).

| measure | dev 20 | baseline |
|---|---|---|
| same instruction text as a train-500 task (normalised) | **0** | - |
| same instruction as a test-69 task (test minus the partner's 66) | 0 | - |
| same full action list as a train-500 task | **0** | - |
| closest text match to train (difflib ratio) | median about 0.42, max 0.70 (dev 14 vs train 292) | test-69 vs train: median 0.32, max 0.70 |
| user also in some train-500 task | 14 of 20 (70 %) | test-69: 34 of 41 users (83 %); train 500 uses 271 of the 500 users. All splits share one database |
| same write tool on the same order as a train task | 6 tasks: dev 9 (train 312), 11 (332), 12 (80, 119, 221, 298), 13 (363, 428), 16 (193), 19 (188) | - |

The dev tasks are written like test tasks ("you realize that the color of the mouse doesn't go well...").
Two of them (12, 14) use the train template text. Sharing a user or an order is normal, because there is only
one database. In each of the 6 tasks above, the target differs from the train task (another new item, another
reason, another set of items). Only these two are partial repeats:

- **dev 12** (olivia_ito_3591, 6 writes): one write is the same as in **train 80**: `modify_pending_order_payment #W3657213 →
  credit_card_9753331`. A second write changes the same Patio Umbrella to the same new item 2001307871, but train 80
  also changes the Hiking Boots in that call. **Train 80 is in B3** (v3's known tasks).
- **dev 13** (aarav_sanchez_6636): returns all 3 items (Portable Charger, Bookshelf, Cycling Helmet) of #W9552705
  to gift_card_8922351. Train 363 returns 2 of them to the same gift card, and train 428 returns the other pair.
  It is a different call, but the same order and refund card. Neither train task is in B3.

## 3. Flags for the report
1. **Easier tasks.** Dev uses the same database as train 500, and some dev tasks use its template. Call it
   "unseen tasks", not "unseen data". It is an easy-template check, like B3, not a hard test.
2. **dev 12 and dev 13 partly repeat train writes** (dev 12 with B3 task train 80). Suggestion: show the result
   with all 20 and without these 2. There is no pass mark either way (plan §4).
3. **Not checked: overlap with the partner's test 66.** Purity rule: I never read those tasks. Indirect sign:
   partner run files keep task text (1,946 hits for one test-split task), yet no partner file holds any dev
   string.
4. dev 17 (juan_smith_9901) expects no write (a refusal or no-action task). dev 12 expects 6 writes.

## How to rerun
```
cd /home/azureuser/code_projects/predicate_correctness && PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 /home/azureuser/miniconda3/bin/python3 -B scoring/v4_form_check.py
```
The search for dev strings and the positive controls are in `output/logs/v4_p1c_15.txt` (the strings),
`v4_p1c_16_devtext_hits.txt`, `v4_p1c_21.txt` and `v4_p1c_23.txt` (positive controls), and `v4_p1c_22.txt` (docs and runner).
