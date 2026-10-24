# Part 10: paths of the copied runner, and where our runs write

Written 2026-10-22 (p10.md subtask 3). Code: `guard/run_online.py` (wrapper), `guard/write_guard.py`,
`guard/runner_path.py`. The copies in `from_shieldagent/runner/` are not edited.

## The short version
- Every copied module finds its files through `ROOT` = the folder above its own file. In our copy that is
  `from_shieldagent/runner/`, never `~/ShieldAgent`.
- We do not call the copy's `main()`. Our wrapper repeats it line by line with our paths (list of differences at the
  top of `guard/run_online.py`).
- All writes go to `predicate_correctness/output/`:
  - conversations: `output/online/<tag>/<env>/tgr_tracker/episodes.jsonl` and `run_<time>.json`;
  - judge cache: `output/_llmcache/<tag>/structured/` (new and empty for each tag);
  - logs: `output/logs/p10_*.log` (the runner prints to stdout; we redirect it).
- A write guard (a Python audit hook) refuses, in the run's process, every write outside `output/` and every access
  (also reading) to `~/ShieldAgent`. Tested in `tests/test_guard.py::TestWriteGuard`.

## What the copied code reads
| path in the copy | read by | in our runs |
|---|---|---|
| `runner/exp_core/model_profiles.json` | `exp_core/models.py` (profiles, prices) | our copy |
| `runner/repro_core/config.json` | `repro_core/llm.py::llm_config`, `repro_runtime/calls.py` (price, replaced by the profile's price in `activate`) | our copy |
| `runner/method_tgr/prompts/*.md`, `runner/repro_runtime/prompts/*.md` | prompt templates (the judge prompt: `method_tgr/prompts/judge.md`) | our copies |
| `ROOT/output/reproduction/labels/splits.json` | the copy's `main()` (task list) | **changed:** our copy `from_shieldagent/splits/splits.json` |
| `ROOT/tgr_rules/<env>/<variant>/rule_set.json` | `repro_online/guards.py::build` (default rules); the partner passed `--rules-dir tgr_rules/<env>/frozen` | **changed:** `from_shieldagent/rules/<env>/rule_set.json` (frozen TGR); `manifest.json` next to it for the tool-schema check |
| `ROOT/policy_docs/<env>_wiki.txt` | `DirectGuard` only | not used (our wrapper runs only `tgr_tracker`) |
| `ROOT/aspm_repro/`, `ROOT/output/repro/aspm_runs/` | `ShieldGuard` only | not used, not copied |
| τ-bench tasks, data, tools, the agent's policy text (`env.wiki`) | `tau_bench` in `~/venvs/tau-bench` (read only) | the same as the partner's runs |
| Azure endpoint and Managed Identity | `runner/utility/utils.py` | network only; no file |

Our tracker also reads `state_tracker/tool_table.json`, `state_tracker/lookups_<env>.json`,
`output/predicate_types.json` (all three checked against the frozen sha256 when the guard starts), and the τ-bench copy
and policy texts in `from_shieldagent/`.

**τ-bench's `task_split="test"`.** The copy's `main()` (and ours) calls `get_env(..., task_split="test")`. This is
τ-bench's task file, from which the partner's `splits.json` draws its train, val and test tasks. It is not the
`splits.json` label "test". Our wrapper takes only tasks that `splits.json` labels train or val, and refuses others.

## What the copied code writes, and where it lands
| what | the copy alone (ROOT = `runner/`) | our wrapper |
|---|---|---|
| conversations (`episodes.jsonl`, `run_<time>.json`) | `ROOT/output/tgr/online/<tag>/<env>/<guard>/` | `output/online/<tag>/<env>/tgr_tracker/` (or `--out-root`, which must be under `output/`) |
| judge cache (structured calls) | `exp_core/models.py::CACHE_ROOT` = `ROOT/output/tgr/_llmcache/structured` | `output/_llmcache/<tag>/structured`: the wrapper sets `models.CACHE_ROOT` before `activate()`; the copy reads it when the first call is made |
| tool-loop cache | `CACHE_ROOT/tool_loop` (ShieldAgent's planner only) | not used by TGR; it would land in `output/_llmcache/<tag>/tool_loop` |
| gpt-5-nano reproduction cache | `repro_core/llm.py::structured_llm` → `ROOT/output/repro/_llmcache` | never called: `activate()` replaces it before the first call; the write guard would refuse it |
| default cache of `policy_pipeline/llm.py` | `ROOT/output/auto_aspm/_cache` (default argument only) | never used: `activate()` passes its own cache folder |
| raw copies of responses | `raw_dir` (None) | none |
| embedding cache | `output/repro/_embcache/embeddings.sqlite` (in `config.json`; used by `repro_core/embed.py`) | not used: `embed.py` is not copied and nothing imports it |
| other runners (`repro_online/run.py`, `repro_core/taubench_run.py`) | `ROOT/output/repro/...` | not used |
| `__pycache__` | next to the copied files | none: the wrapper sets `sys.dont_write_bytecode`, and we run Python with `-B` |

## Caching: our runs make fresh calls
- **Agent and user simulator:** `exp_core/models.py::make_completion` has no cache. Every call goes to Azure, as in
  the partner's runs. τ-bench's user simulator uses it through `tau_bench.envs.user.completion`, which the wrapper
  points at `make_completion("user")` (in memory, as the copy does).
- **Judge:** `policy_pipeline/llm.py::LLM.call` caches each answer on disk, keyed by the prompt and the model. Our
  cache folder is new and separate for each tag, so we never replay the partner's cache. Within one tag, an identical
  judge prompt (rare) is answered from our cache, as it was in the partner's runs. A cache hit still counts its
  original tokens in the cost (the copy's metering).
- For reference, the partner's saved TGR runs had few cache hits: 1 of 321, 6 of 1,729, 9 of 531 and 99 of 2,322 judge
  calls (luna airline, luna retail, nano airline, nano retail; `output/logs/p10_s2_cachehits.log`).

## Safety rules in the wrapper
- Profiles `luna-dev` and `nano-agent-luna` only (argparse choices); every role's model must be `gpt-6-luna` or
  `gpt-5-nano`. `grok-eval` is refused before anything runs.
- Tasks: only splits.json labels train and val; `--task-ids` with a test task is refused.
- Output and cache folders must be under `output/`; the tag may use letters, digits, `_`, `.`, `-` only.
- The tool schemas τ-bench gives must have the `tools_sha256` written in the rule set's manifest.
- The guard checks the frozen sha256 of `predicate_types.json` and both lookup files when it starts.

## Checks done (no LLM call)
- Import check of the copy (venv, `-B`): 33 modules load from `runner/`, none from `~/ShieldAgent`, no file under
  `~/ShieldAgent` opened (`output/logs/p10_import_check.log`).
- `--dry-run` for luna-dev train (airline 60 and retail 138 conversations), nano-agent-luna train (60, 138) and
  luna-dev val (30, 69): every path is under `output/`; models as expected (`output/logs/p10_dryrun.log`).
- A start with 0 trials wrote only `output/p10_launch_check/p10_launch_check/retail/tgr_tracker/run_<time>.json`; no
  LLM cache folder was made; nothing outside `output/` changed; no `__pycache__`; the write guard refused 0 writes
  (`output/logs/p10_launch_check.log`).
- Our train task lists equal the task lists of the partner's `luna_train_v5` and `nano_train` runs.
