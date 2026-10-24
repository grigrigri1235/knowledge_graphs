# Provenance of the copies

Copied on 2026-10-21, in Part 1 of `docs/planning/state_tracking_exp/` (`p1.md`). The gold code in `gold/` was copied on
2026-10-22, in Part 7, subtask 4 (`p7.md`). The runner code in `runner/` was copied on 2026-10-22, in Part 10, subtask 2
(`p10.md`). The baseline runs (no guard, Direct, frozen TGR) and the metric and gold scorer scripts in `scoring/` were
copied on 2026-10-22, in Part 10, subtasks 8 and 9 (see "Baselines (Part 10)" and "Scoring scripts (Part 10)").

## Rules
- **Never edit a copy.** If a copy needs another path or import setup, write a small wrapper or loader in
  `../state_tracker/`.
- Every copy has its sha256 in `SHA256SUMS` (the checksum of the source at copy time).
- Check the copies: `python3 tests/check_copies.py` (run in `predicate_correctness/`). With `--sources`, it also
  checks that the sources have not changed since the copy.
- Gold code is copied only in Part 7, subtask 4, into `gold/`, and is used only for scoring (done 2026-10-22; see
  "Gold code" below).

## Sources
| source | commit | state of the copied files |
|---|---|---|
| `~/ShieldAgent` | `1bacdb0` (`1bacdb07037bf0f00dbea8982f5bdcc8ae75c506`) | Tracked files: the same as the commit. Run outputs (`output/...`): not in git; taken from the working tree. |
| `~/opt/tau-bench-59a200c` | `59a200c` (`59a200c6d575d595120f1cb70fea53cef0632f6b`) | The same as the commit. |

- The `~/ShieldAgent` working tree has partner changes (`AGENTS.md`, `README.md`, `docs/STRUCTURE.md`,
  `docs/RESULTS.md`, `docs/SUMMARY_REPORT.md`, `scripts/reproduction/p1_trace.py`). None of them is copied.
- The runs used τ-bench from the venv `~/venvs/tau-bench`. That venv has a normal (not editable) install from
  `~/opt/tau-bench-59a200c`, and its `tau_bench` package has no differences from the source (checked with
  `diff -r`). So the copied tool code is the code the runs used.

## Licenses
- `LICENSE`: `~/ShieldAgent`, MIT License, Copyright (c) 2024 Zhaorun Chen.
- `tau_bench/LICENSE`: τ-bench, MIT License, Copyright (c) 2024 Sierra.

## What is where
| folder | content | source |
|---|---|---|
| `code/` | `repro_core/` (`ltlf.py`, `taubench_steps.py`), `repro_runtime/` (`aspm.py`, `verify.py`, `mln.py`) | `~/ShieldAgent` |
| `tau_bench/` | τ-bench's repository root: `LICENSE` and the package `tau_bench/` (only the parts listed below) | `~/opt/tau-bench-59a200c` |
| `rules/<domain>/` | frozen TGR rule set: `rule_set.json`, `manifest.json`, `rules.md` | `~/ShieldAgent/tgr_rules/<domain>/frozen/` |
| `policies/` | `airline_wiki.txt`, `retail_wiki.txt` | `~/ShieldAgent/policy_docs/` |
| `runs/<run>/<domain>/<guard>/` | `episodes.jsonl` and the run's `run_*.json` (guard `tgr` for `luna_train_v5` and `nano_train` in Part 1; `none`, `direct` and all of `luna_val` in Part 10) | `~/ShieldAgent/output/tgr/online/<run>/<domain>/<guard>/` |
| `scoring/` | the partner's metric and gold scorer scripts and their input files, folder layout kept (Part 10; scoring only) | `~/ShieldAgent` |
| `splits/` | `splits.json` | `~/ShieldAgent/output/reproduction/labels/` |
| `runner/` | conversation runner and TGR code, package layout kept: `exp_core/` (`run_online.py`, `models.py`, `model_profiles.json`), `repro_online/`, `method_tgr/` (with `prompts/`), `repro_core/` (`llm.py`, `taubench_run.py`, `taubench_steps.py`, `ltlf.py`, `config.json`), `repro_runtime/` (with `prompts/`), `policy_pipeline/llm.py`, `utility/utils.py` (Part 10; see "Runner code" below) | `~/ShieldAgent` |
| `gold/` | gold predicate code: `__init__.py`, `context.py`, `airline.py`, `retail.py` (Part 7, scoring only) | `~/ShieldAgent/agent/predicates/` |

## How to use the copies
- **`code/`:** put `from_shieldagent/code` on `sys.path` (done by `state_tracker/paths.py::add_code_path`). Then
  `repro_core.ltlf`, `repro_runtime.aspm`, `repro_runtime.verify` and `repro_runtime.mln` import with the standard
  library only.
  - Do not call `repro_runtime.aspm.load()`. It imports `agent.tools.aspm_tool`, which is not copied. TGR does not
    use it.
  - `to_aspm` (from `method_tgr/rules.py`) is in `state_tracker/tgr_to_aspm.py`. That file has the details.
- **`tau_bench/`:** the folder mirrors τ-bench's repository root, so `from_shieldagent/tau_bench` is the folder to
  put on the path. Do not put `from_shieldagent/` itself on `sys.path`: the folder `code/` would hide Python's
  module `code`.

## τ-bench: tool interface (for Part 4)
- **Tools:** each tool is a class in `tau_bench/envs/<domain>/tools/<name>.py`, based on `tau_bench.envs.tool.Tool`,
  with two static methods:
  - `invoke(data, **kwargs) -> str`: runs on the database `data` (a dict). Write tools change `data` in place.
    The result is a string: usually `json.dumps` of the object (order, user, reservation), sometimes plain text
    (for example `calculate`, `transfer_to_human_agents`, `think` returns `""`). Failures return a text that
    starts with `"Error"`.
  - `get_info() -> dict`: the function schema the agent sees. `get_info()["function"]["name"]` is the tool name in
    the conversation.
- **Tool lists:** `tools/__init__.py` has `ALL_TOOLS`: 14 airline tools, 16 retail tools.
- **Data:** `data/__init__.py::load_data()` reads the JSON files and returns a new dict:
  - retail: `orders` (1,000), `products` (50), `users` (500);
  - airline: `flights` (300), `reservations` (2,000), `users` (500).

  τ-bench calls `load_data()` again for every task (`Env.reset`), so every task starts from these files.
- **How τ-bench runs one call** (`tau_bench/envs/base.py::Env.step`, copied for reference only):
  `observation = tools_map[name].invoke(data=self.data, **kwargs)`. Any exception becomes the text
  `f"Error: {e}"` (for example, a missing key or a wrong argument). An unknown tool name gives
  `f"Unknown action {name}"`. `transfer_to_human_agents` ends the conversation (`terminate_tools` in `env.py`).
- **How the saved runs called it:** ShieldAgent's runner (`exp_core/run_online.py`, which reuses
  `repro_online/episode.py::run_episode`) calls `env.step(action)` only for executed attempts. It saves the result
  as `attempt["observation"]` and as the tool message in `executed`. A blocked attempt does not run. An attempt with
  `cap_override: true` was blocked by the guard but ran anyway (the block limit was reached).
- **Heavy imports, and the loader Part 4 must write:**
  - `tau_bench/__init__.py` imports `tau_bench.envs.base` and `tau_bench.agents.base`.
  - `tau_bench/envs/__init__.py` imports `tau_bench.envs.base` and `tau_bench.envs.user`.
  - `base.py` imports `tau_bench.envs.user` (needs `litellm`) and `tau_bench.types` (needs `pydantic`).
  - `envs/<domain>/__init__.py` imports `env.py`, which is not copied.

  So a plain `import tau_bench.envs.retail.tools` would fail, or would load `litellm`. Part 4 must load the tools
  through a loader in `state_tracker/` that does not run these `__init__.py` files. For example: put empty package
  modules for `tau_bench`, `tau_bench.envs` and `tau_bench.envs.<domain>` into `sys.modules`, each with `__path__`
  set to the copied folder, then import `tau_bench.envs.<domain>.tools` and `tau_bench.envs.<domain>.data`. The tools
  import only `tau_bench.envs.tool`, `json`, `typing` and `copy`.
- **Checked on 2026-10-21** (`output/logs/p1_smoke.log`): with this loader, the tools and the data load from the
  copy with the standard library only, and neither `litellm` nor `pydantic` is loaded. `get_info()` of
  `ALL_TOOLS` gives the `tools_sha256` written in both rule-set manifests (sha256 of
  `json.dumps(tools, sort_keys=True)`). So the rules were built for these exact tool schemas.
- **Not copied from τ-bench:**
  - `tasks*.py`: each task's expected actions and outputs, that is, the benchmark's answers. The state does not need
    them, and leaving them out avoids leakage.
  - `user.py`, `types.py`, `env.py`, `rules.py`, `wiki.md`, `wiki.py`, `agents/`, `model_utils/`, `run.py`: they
    are not needed to run the tools.

## Which rule set each saved run used
All four runs used the frozen rule set.

| run | domain | `--rules-dir` in `run_*.json` | same as `tgr_rules/<domain>/frozen/`? |
|---|---|---|---|
| `luna_train_v5` | airline | `output/tgr/tgr_rules/luna-dev/airline/it5` | yes: all 4 files byte-identical (`rule_set.json` sha256 `27e2eafa…`) |
| `luna_train_v5` | retail | `output/tgr/tgr_rules/luna-dev/retail/it5` | yes: all 4 files byte-identical (`rule_set.json` sha256 `9e395e2f…`) |
| `nano_train` | airline | `tgr_rules/airline/frozen` | yes: the folder itself |
| `nano_train` | retail | `tgr_rules/retail/frozen` | yes: the folder itself |

- `tgr_rules/README.md` in `~/ShieldAgent` also says that `frozen/` is iteration 5 (`it5`), tag `tgr-frozen-v1`.
- The `it5` files were written at 12:14 and 12:22 on 2026-10-20, before the `luna_train_v5` run started (12:23).
- **Check on the saved steps** (`output/logs/p1_frozen_circuits.log`, `p1_smoke.log`):
  - In all 5,497 saved guard records, the matched action, the rule ids (circuit) and the judged predicate names are
    the ones the frozen set gives for that tool.
  - We ran the decision again (`to_aspm` + `mln.decide`) on all 4,903 records that have judge values. Each one gives
    the saved margin and the saved allow or block.

## Policies
- `retail_wiki.txt` is byte-identical to `code_projects/files_given/wiki.md` (sha256 `d539fd2a…`) and to τ-bench's
  `envs/retail/wiki.md`.
- `airline_wiki.txt` is byte-identical to τ-bench's `envs/airline/wiki.md`.
- Both checksums equal the `filter.input` hashes in the rule-set manifests.
- The airline policy states "The current time is 2024-05-15 15:00:00 EST." (line 3). The retail policy states no
  current time.

## Runs
| run | domain | episodes | tasks × trials | guard records | judge values | blocked checks |
|---|---|---|---|---|---|---|
| `luna_train_v5` (gpt-6-luna agent and guard) | airline | 60 | 20 × 3 | 611 | 2,224 | 12 |
| `luna_train_v5` | retail | 138 | 46 × 3 | 1,738 | 5,489 | 54 |
| `nano_train` (gpt-5-nano agent, gpt-6-luna guard) | airline | 60 | 20 × 3 | 825 | 3,877 | 94 |
| `nano_train` | retail | 138 | 46 × 3 | 2,323 | 8,614 | 416 |

- Each episode has `task_index` and `trial` (0, 1, 2). The task indices are exactly the train tasks of
  `splits.json`.
- The `run_*.json` files are copied too (not listed in `p1.md`): they hold the rules folder and the task list.
- `gold.jsonl` and `gold_v2.jsonl` next to the `luna_train_v5` episodes are gold scores. They are not copied.

## Splits
`splits.json` has, per domain: `seed`, `fractions`, `split` (task index → train, val or test) and `counts` (sizes
of an earlier label set). We use only `split`.

## Gold code (Part 7)
- **What:** `~/ShieldAgent/agent/predicates/` (`__init__.py`, `context.py`, `airline.py`, `retail.py`), the partner's
  hand-written predicate code. Each predicate has the form `f(tool_call, trajectory, config) -> True | False | None`;
  None means the history does not decide the value. The files equal commit `1bacdb0`. The folder's `__pycache__` was
  not copied.
- **When:** 2026-10-22, after the lookups were frozen (Part 5) and after the review (Part 7, subtask 3).
- **Use:** scoring only. Only `../scoring/gold_loader.py` loads it. The gold files import
  `agent.predicates.context`, so the loader registers two empty package modules (`agent`, `agent.predicates`, the
  second pointing at `gold/`), imports the modules, and removes the stubs again. No bytecode is written into `gold/`.
- **Config:** gold reads only `current_time` (airline). `scoring/gold_loader.py` sets it to `2024-05-15T15:00:00`, the
  value in `~/ShieldAgent/policies/curated/airline_config.json` and the time in the airline policy. The config files
  are not copied.
- **Never in the tracker or the guard:** `../tests/test_no_gold_import.py` fails if anything under `state_tracker/`
  or `guard/` imports or names gold code, `scoring/` or the gold paths in `~/ShieldAgent`, or opens a gold file when
  imported.
- **Not copied:** the gold specs and rules (`~/ShieldAgent/policies/`, `aspm/`, `scripts/aspm_src/`) and the gold
  score files (`gold.jsonl`, `gold_v2.jsonl`). Part 7 needs only the predicate code.

## Runner code (Part 10)
- **What:** 59 files from `~/ShieldAgent` (commit `1bacdb0`; every file equals the commit): the files p10.md lists,
  plus every module they import. The import list comes from an import check on the copy (venv Python, `-B`;
  `output/logs/p10_import_check.log`): all 33 modules load from `runner/`, none from `~/ShieldAgent`, and nothing
  under `~/ShieldAgent` was opened. τ-bench itself comes from the venv (`~/venvs/tau-bench`), as in the partner's runs.
- **Not copied:** `agent/tools/aspm_tool.py` (only `repro_runtime/aspm.py::load` imports it, for ShieldAgent's own
  guard; TGR does not use it), `repro_core/embed.py` and the embedding model (only ShieldAgent's rule building uses
  them), `exp_core/tgr_build.py`, `run_p1.py`, `policy_filter.py` (rule building), `policy_docs/` (already in
  `policies/`).
- **Same files as `code/`:** `repro_core/ltlf.py`, `taubench_steps.py`, `repro_runtime/aspm.py`, `mln.py`, `verify.py`
  and the two `__init__.py` files have the same sha256 in `code/` and in `runner/`.
- **Use:** only through our wrapper `../guard/run_online.py` (it puts `runner/` on `sys.path` and sets every output
  path to `../output/`; details in `../output/p10_paths.md`). The copies keep their own path logic (`ROOT` = `runner/`),
  so run them only through the wrapper. Run Python with `-B`, so no `__pycache__` is written into the copy.

## Baselines (Part 10, subtask 8)
- **What:** the partner's saved runs with the same tasks, trials (3) and models as our Part 10 runs: `none`, `direct`
  and `tgr` (frozen TGR) for `luna_train_v5` (train, luna-dev), `nano_train` (train, nano-agent-luna) and `luna_val`
  (val, luna-dev), both domains. 30 new files (18 `episodes.jsonl`, 12 `run_*.json`); the 8 files of Part 1
  (`luna_train_v5` and `nano_train` `tgr`) were already there and were skipped (still equal to their sources).
  The partner's `shield` runs are not copied (p10.md does not ask for them), nor are the gold and metric files next to
  the episodes (we score again; the result equals the partner's files, see `../output/p10_metrics.md`).
- **When:** 2026-10-22, with `~/ShieldAgent` at HEAD `7e6575b` (git status clean). The run files are not in git; the
  "commit" column below names our reference commit `1bacdb0`. HEAD and the git status were the same before and after
  the copy (`../output/logs/p10_s89_10_copy.log`).
- **Settings, from each `run_*.json`:** luna-dev = gpt-6-luna for agent, user and guard; nano-agent-luna = gpt-5-nano
  agent (chat), gpt-6-luna user and guard. TGR used `tgr_rules/<domain>/frozen` (`nano_train`, `luna_val`) or the
  byte-identical `it5` folder (`luna_train_v5`, see above). Task lists equal `splits.json` train / val.
- **`luna_train_v5` none and direct** have no `run_*.json`: they are copies of the partner's Phase 1 baseline episodes
  (`~/ShieldAgent/docs/STRUCTURE.md`). Every episode records gpt-6-luna for all roles. `luna_train_v5/retail/none`
  has 139 lines: one (task, trial) failed with an error and was run again; the scripts keep the latest line.
- **Size:** `runs/` is now 120 MB (> 50 MB), so `predicate_correctness/from_shieldagent/runs/` is in the repository's
  `.gitignore`. The files stay on disk with their sha256 in `SHA256SUMS`.

## Scoring scripts (Part 10, subtask 9)
- **What:** 16 files from `~/ShieldAgent`, folder layout kept, all equal to commit `1bacdb0` (and unchanged at
  `7e6575b`): `scripts/tgr/metrics.py`, `scripts/reproduction/p6_metrics.py`, `p6_gold_score.py`, `gold_compare.py`,
  `scripts/validate_aspm.py` (imported by `p6_gold_score.py` for its Parser / kleene / tree_nodes),
  `policies/gold_v2/checks.py` and `README.md`, and the inputs that `p6_gold_score.py` reads:
  `aspm/<domain>_aspm.json`, `policies/predicates/<domain>_predicates.json`, `policies/curated/<domain>_config.json`,
  `policies/tau_bench/<domain>_tools.json`; `metrics.py` reads `exp_core/model_profiles.json` (same sha256 as
  `runner/exp_core/model_profiles.json`).
- **Gold predicate code:** not copied again. The scripts import `agent.predicates.<domain>`, which is the Part 7 copy
  in `gold/` (still equal to `~/ShieldAgent/agent/predicates/`).
- **Use:** scoring only, only through `../scoring/p10_eval.py`. It builds `../output/eval/` with symlinks to these
  folders, so the scripts' ROOT is `output/eval/` and every output lands there; each script runs with `-B` under our
  write guard. Never imported by `state_tracker/` or `guard/` (`../tests/test_no_gold_import.py`).
- **Not copied:** `policies/curated/*_curated_rules.json` and `*_clauses.json`, `scripts/aspm_src/` (only other
  functions of `validate_aspm.py` read them).

## Files
Size in bytes. "same as commit": the file equals the version in the commit. "not in git": the file is a run output
that git does not track.

| copy (in from_shieldagent/) | source | commit | size | sha256 |
|---|---|---|---|---|
| `LICENSE` | `~/ShieldAgent/LICENSE` | `1bacdb0` (same as commit) | 1,068 | `e06aeee4f5d46ec87d52c95b100628f936890ceaa2252e26c0521178f9b3322f` |
| `code/repro_core/__init__.py` | `~/ShieldAgent/repro_core/__init__.py` | `1bacdb0` (same as commit) | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `code/repro_core/ltlf.py` | `~/ShieldAgent/repro_core/ltlf.py` | `1bacdb0` (same as commit) | 10,042 | `a766c1732442368173a3e370a86d46eb630405e36168786cd5275cf5730d2d57` |
| `code/repro_core/taubench_steps.py` | `~/ShieldAgent/repro_core/taubench_steps.py` | `1bacdb0` (same as commit) | 4,005 | `07f8e8034f5098663deb86d6e183b5425516d16ea54ebe018aef48a8182104e9` |
| `code/repro_runtime/__init__.py` | `~/ShieldAgent/repro_runtime/__init__.py` | `1bacdb0` (same as commit) | 290 | `04dc15bc039cba2e6e04afe6707172de121f878d99461d46eed3120e81034c93` |
| `code/repro_runtime/aspm.py` | `~/ShieldAgent/repro_runtime/aspm.py` | `1bacdb0` (same as commit) | 5,032 | `2afef6749a29880e2892b277afab76a6cd28d383b908b772658322636a517a4a` |
| `code/repro_runtime/mln.py` | `~/ShieldAgent/repro_runtime/mln.py` | `1bacdb0` (same as commit) | 5,788 | `6873ce704dab26664e103f680da9c2b9b4ab8ee6862e20548bc8778ca0340c37` |
| `code/repro_runtime/verify.py` | `~/ShieldAgent/repro_runtime/verify.py` | `1bacdb0` (same as commit) | 2,512 | `6151003c9ddd99c644e1c8e1b7a662559ab57c08cba49985cf9d4dc1a32a3d4b` |
| `gold/__init__.py` | `~/ShieldAgent/agent/predicates/__init__.py` | `1bacdb0` (same as commit) | 91 | `ed20efe0964daddd804765f55222609f0a7f570941f6fec526c87358c0451d67` |
| `gold/airline.py` | `~/ShieldAgent/agent/predicates/airline.py` | `1bacdb0` (same as commit) | 16,425 | `dce62a32b03f3d551795b8930018d14c2c501f02c0abdb445510880c0fd66e8c` |
| `gold/context.py` | `~/ShieldAgent/agent/predicates/context.py` | `1bacdb0` (same as commit) | 13,739 | `a5b5e346eeecf8bc6fc9a0a7a91ad89c82e4e39d3485971c99474e6d0388c367` |
| `gold/retail.py` | `~/ShieldAgent/agent/predicates/retail.py` | `1bacdb0` (same as commit) | 12,092 | `0adca05423a02be5de0c5f76778c09a087ba77f7d1a4eb576bd1d1e8d361699b` |
| `policies/airline_wiki.txt` | `~/ShieldAgent/policy_docs/airline_wiki.txt` | `1bacdb0` (same as commit) | 6,155 | `56c335801c16e26b54f600f9db99eb04d31db477e86eb160341d5c66b796c5c8` |
| `policies/retail_wiki.txt` | `~/ShieldAgent/policy_docs/retail_wiki.txt` | `1bacdb0` (same as commit) | 5,718 | `d539fd2a46a8b8dd2e934ff9ed92f43e9f6b56bc7a718db8d2803ba8ad8f6bf7` |
| `rules/airline/manifest.json` | `~/ShieldAgent/tgr_rules/airline/frozen/manifest.json` | `1bacdb0` (same as commit) | 2,922 | `4ee12f830d23b9e6dd32cebbf5dc8e10e6efbfdf8fdda7e08f4deebfac38c674` |
| `rules/airline/rule_set.json` | `~/ShieldAgent/tgr_rules/airline/frozen/rule_set.json` | `1bacdb0` (same as commit) | 60,938 | `27e2eafa05fd919d41083e8d4dfeb7c4a6d9a789fa2ad7c5da645584d05bc5a4` |
| `rules/airline/rules.md` | `~/ShieldAgent/tgr_rules/airline/frozen/rules.md` | `1bacdb0` (same as commit) | 31,365 | `90bf18bb94b19d3889b763ecf7c12126a80422d16c4d20c56234dcfcb719bbf5` |
| `rules/retail/manifest.json` | `~/ShieldAgent/tgr_rules/retail/frozen/manifest.json` | `1bacdb0` (same as commit) | 3,119 | `845f6d9a40ab05d83242b74ce9b8d35c71d880162c2394b67885c8a279fa602d` |
| `rules/retail/rule_set.json` | `~/ShieldAgent/tgr_rules/retail/frozen/rule_set.json` | `1bacdb0` (same as commit) | 60,517 | `9e395e2fc259cdf228612c4cd078a5bb3836bad4fe42af4493ffc9359fb63d7b` |
| `rules/retail/rules.md` | `~/ShieldAgent/tgr_rules/retail/frozen/rules.md` | `1bacdb0` (same as commit) | 28,714 | `1832588a90c94b7d661390d1ef43fbf61be1e2ee9dee66f6b51fb70d66e13428` |
| `runner/exp_core/__init__.py` | `~/ShieldAgent/exp_core/__init__.py` | `1bacdb0` (same as commit) | 431 | `1dae2f991c254a2d44c79a37cc4132e6012355095642d43ede655cb5ffded599` |
| `runner/exp_core/model_profiles.json` | `~/ShieldAgent/exp_core/model_profiles.json` | `1bacdb0` (same as commit) | 2,610 | `03c46ecfbc813e1be2a2cefec865a68b21dc8266ef42c1aaf9e2997b006a2b7e` |
| `runner/exp_core/models.py` | `~/ShieldAgent/exp_core/models.py` | `1bacdb0` (same as commit) | 15,130 | `0cb9c4e5f3f7ec9febd0365efa6955226e62ba7c27f2fe9487803998ae9d2717` |
| `runner/exp_core/run_online.py` | `~/ShieldAgent/exp_core/run_online.py` | `1bacdb0` (same as commit) | 7,691 | `10f04247593d183ffef7d58b5b79c086ab9e0213292cedc24b2e10f090ba86bd` |
| `runner/method_tgr/__init__.py` | `~/ShieldAgent/method_tgr/__init__.py` | `1bacdb0` (same as commit) | 862 | `1b11a4724553d7decaefa1dee773878118d1a9f64eed0dcc1b568b90c6525b0f` |
| `runner/method_tgr/feedback.py` | `~/ShieldAgent/method_tgr/feedback.py` | `1bacdb0` (same as commit) | 2,778 | `6e9bb5c83fbe1c11f8ee40ba26e7c21a6ae5fcaed25aff10690af8b7a892c3d8` |
| `runner/method_tgr/llm.py` | `~/ShieldAgent/method_tgr/llm.py` | `1bacdb0` (same as commit) | 2,016 | `567f49cb22c0c5e06be69f606b7cac30a354d00c163ad5676228fae1707b775c` |
| `runner/method_tgr/policy_text.py` | `~/ShieldAgent/method_tgr/policy_text.py` | `1bacdb0` (same as commit) | 1,220 | `6e2416bb9907eb2c6ede388556173e960b2800f3223ecb1a3730723094c8c742` |
| `runner/method_tgr/prompts.py` | `~/ShieldAgent/method_tgr/prompts.py` | `1bacdb0` (same as commit) | 1,143 | `27b4da24c80ffa657cb6bbae97eb2ce8ee7ff2466d4c6a2668331d2080da55fe` |
| `runner/method_tgr/prompts/actions_free.md` | `~/ShieldAgent/method_tgr/prompts/actions_free.md` | `1bacdb0` (same as commit) | 215 | `afa381adcb6c1f8b2720112efde9417e8c18c1405bc591c677d83d3ed447293e` |
| `runner/method_tgr/prompts/actions_tools.md` | `~/ShieldAgent/method_tgr/prompts/actions_tools.md` | `1bacdb0` (same as commit) | 230 | `062f4d76f84e290cc0824917e804f05ab45b1fb0688032b39d0768284654830f` |
| `runner/method_tgr/prompts/dispositions.md` | `~/ShieldAgent/method_tgr/prompts/dispositions.md` | `1bacdb0` (same as commit) | 621 | `94ae3489c99456bd8dc8ce83556b46e2f8223d4b1950ac0eeda8bf980d5f4c9d` |
| `runner/method_tgr/prompts/example_general.md` | `~/ShieldAgent/method_tgr/prompts/example_general.md` | `1bacdb0` (same as commit) | 404 | `cf9801403e312668c1693e2a5cb1cd50c3f2d7701b406971f5e1c1b6801d768b` |
| `runner/method_tgr/prompts/example_restriction.md` | `~/ShieldAgent/method_tgr/prompts/example_restriction.md` | `1bacdb0` (same as commit) | 780 | `ff23a600589c1fcf9f8d98346cdde536c6246702e129c6bb81abd0afc4945020` |
| `runner/method_tgr/prompts/form_general.md` | `~/ShieldAgent/method_tgr/prompts/form_general.md` | `1bacdb0` (same as commit) | 555 | `21d47105f2020558f045c2268f5a7ace76addb9074ab78a2a00c2f69902b554f` |
| `runner/method_tgr/prompts/form_restriction.md` | `~/ShieldAgent/method_tgr/prompts/form_restriction.md` | `1bacdb0` (same as commit) | 1,571 | `8b9c21ea09fd68b63d40be0f6c5dcf08c0eb9eede4956cd37b75ea0a926dd50f` |
| `runner/method_tgr/prompts/judge.md` | `~/ShieldAgent/method_tgr/prompts/judge.md` | `1bacdb0` (same as commit) | 2,393 | `c3acbd4c26240473656085a950fafdbf8bac6ddf404f52c944d7e117363332a2` |
| `runner/method_tgr/prompts/no_dispositions.md` | `~/ShieldAgent/method_tgr/prompts/no_dispositions.md` | `1bacdb0` (same as commit) | 37 | `ab626a5b8d6a53d80e7f869ff35385ba4aae468ed52c4d90174acc0c3f8232eb` |
| `runner/method_tgr/prompts/predicates_grounded.md` | `~/ShieldAgent/method_tgr/prompts/predicates_grounded.md` | `1bacdb0` (same as commit) | 836 | `ea16ee627f4498d5c2cab44ea9d7d6d69f6b8bfe4c96f7b74e77bc71be1e14b7` |
| `runner/method_tgr/prompts/predicates_plain.md` | `~/ShieldAgent/method_tgr/prompts/predicates_plain.md` | `1bacdb0` (same as commit) | 503 | `0de622b60074d66499b39d2f7b68dd7942b647ec86997a82bd072f897fe334ef` |
| `runner/method_tgr/prompts/repair.md` | `~/ShieldAgent/method_tgr/prompts/repair.md` | `1bacdb0` (same as commit) | 491 | `f099786338a41f8924922380c86ddf8c6a1297e7357035ca01548f9fbdbe02f1` |
| `runner/method_tgr/prompts/rules_system.md` | `~/ShieldAgent/method_tgr/prompts/rules_system.md` | `1bacdb0` (same as commit) | 230 | `a9b6172907b3086766dceab3aefd2a3834e3f9d385b410b9d4c60c561a56b226` |
| `runner/method_tgr/prompts/rules_user.md` | `~/ShieldAgent/method_tgr/prompts/rules_user.md` | `1bacdb0` (same as commit) | 210 | `af2d72bb054d67a4e1d3c2f7fb07c17906e8c3611e915a6324bf5c5c790799b2` |
| `runner/method_tgr/prompts/scope.md` | `~/ShieldAgent/method_tgr/prompts/scope.md` | `1bacdb0` (same as commit) | 2,452 | `a58521fd27fea7b47ec797e08cb96faa35197b69a81ae69c19df593cbb11d6f9` |
| `runner/method_tgr/rules.py` | `~/ShieldAgent/method_tgr/rules.py` | `1bacdb0` (same as commit) | 14,286 | `1d9c3a8b59d31a2a06fc1e349e92fe6868326fb6cefb24dee460999e215ba178` |
| `runner/method_tgr/runtime.py` | `~/ShieldAgent/method_tgr/runtime.py` | `1bacdb0` (same as commit) | 9,136 | `895659215ab45db55b0ded2f5ff0caaba45864fd84e5d2fa946f8a5f0b5d5fb8` |
| `runner/policy_pipeline/__init__.py` | `~/ShieldAgent/policy_pipeline/__init__.py` | `1bacdb0` (same as commit) | 86 | `b846dba80622479cf95cf053eaf29309e392c22b97f3ef74388ace9fd89ffb72` |
| `runner/policy_pipeline/llm.py` | `~/ShieldAgent/policy_pipeline/llm.py` | `1bacdb0` (same as commit) | 6,004 | `5786a5d1fd3b5578fce217e97a01b30796203717612db1b3f3ae1eabd34c4564` |
| `runner/repro_core/__init__.py` | `~/ShieldAgent/repro_core/__init__.py` | `1bacdb0` (same as commit) | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `runner/repro_core/config.json` | `~/ShieldAgent/repro_core/config.json` | `1bacdb0` (same as commit) | 1,095 | `30fe454353ae2e1cf2f068be932a38638b4db55f78029b146db4618ae6f7b738` |
| `runner/repro_core/llm.py` | `~/ShieldAgent/repro_core/llm.py` | `1bacdb0` (same as commit) | 5,632 | `3d1862175438e66bbcbef6d39c34648980c6af4c2cfb936a13a0e282416a19d6` |
| `runner/repro_core/ltlf.py` | `~/ShieldAgent/repro_core/ltlf.py` | `1bacdb0` (same as commit) | 10,042 | `a766c1732442368173a3e370a86d46eb630405e36168786cd5275cf5730d2d57` |
| `runner/repro_core/taubench_run.py` | `~/ShieldAgent/repro_core/taubench_run.py` | `1bacdb0` (same as commit) | 5,550 | `abe667a346ca894c3e2b7104094151c179f11836a951bc7ded4e103f20812a47` |
| `runner/repro_core/taubench_steps.py` | `~/ShieldAgent/repro_core/taubench_steps.py` | `1bacdb0` (same as commit) | 4,005 | `07f8e8034f5098663deb86d6e183b5425516d16ea54ebe018aef48a8182104e9` |
| `runner/repro_online/__init__.py` | `~/ShieldAgent/repro_online/__init__.py` | `1bacdb0` (same as commit) | 448 | `73e271c55ff74083b1008f9867530db20911cc87b44b57b7409b3106616c5b30` |
| `runner/repro_online/episode.py` | `~/ShieldAgent/repro_online/episode.py` | `1bacdb0` (same as commit) | 6,180 | `a2b19ad1aecf44d311d9b9247910c45e21f4fb892ae96a8d84106da250cfdb7d` |
| `runner/repro_online/guards.py` | `~/ShieldAgent/repro_online/guards.py` | `1bacdb0` (same as commit) | 4,866 | `72c7cced7a8ec8b67445a18e61d8cd4e640737f9515975f4e3c6b540ebc69320` |
| `runner/repro_online/run.py` | `~/ShieldAgent/repro_online/run.py` | `1bacdb0` (same as commit) | 4,651 | `2f787d7d42870e3d628cb1d6913110f92bab1dc8d9de82d83d4030020147c427` |
| `runner/repro_runtime/__init__.py` | `~/ShieldAgent/repro_runtime/__init__.py` | `1bacdb0` (same as commit) | 290 | `04dc15bc039cba2e6e04afe6707172de121f878d99461d46eed3120e81034c93` |
| `runner/repro_runtime/aspm.py` | `~/ShieldAgent/repro_runtime/aspm.py` | `1bacdb0` (same as commit) | 5,032 | `2afef6749a29880e2892b277afab76a6cd28d383b908b772658322636a517a4a` |
| `runner/repro_runtime/calls.py` | `~/ShieldAgent/repro_runtime/calls.py` | `1bacdb0` (same as commit) | 3,332 | `449e0fe389db4029c399dda0b7408eb24bec5c0f11c9764d9dc401e43161ec59` |
| `runner/repro_runtime/direct.py` | `~/ShieldAgent/repro_runtime/direct.py` | `1bacdb0` (same as commit) | 1,570 | `cccb281aa1d98c51ca79d00c927e5eff4e3e9a3bee9e091aff736400510d95c7` |
| `runner/repro_runtime/extract.py` | `~/ShieldAgent/repro_runtime/extract.py` | `1bacdb0` (same as commit) | 1,212 | `d982c4fbf38af5e120b7e0c8a0d7e98e5989d66911c0de139001b2754e1ac66e` |
| `runner/repro_runtime/mln.py` | `~/ShieldAgent/repro_runtime/mln.py` | `1bacdb0` (same as commit) | 5,788 | `6873ce704dab26664e103f680da9c2b9b4ab8ee6862e20548bc8778ca0340c37` |
| `runner/repro_runtime/plan.py` | `~/ShieldAgent/repro_runtime/plan.py` | `1bacdb0` (same as commit) | 8,599 | `5aa045616965e06ac0a55d825b02ffdc37f5f0ab58311a4e29167acac64cb1b4` |
| `runner/repro_runtime/prompts.py` | `~/ShieldAgent/repro_runtime/prompts.py` | `1bacdb0` (same as commit) | 1,171 | `885b09f36c27d6efb1172b260d7405000e98c29b9ffbfb239400ce2bc995b5d2` |
| `runner/repro_runtime/prompts/binary_check.md` | `~/ShieldAgent/repro_runtime/prompts/binary_check.md` | `1bacdb0` (same as commit) | 362 | `7642b54ca03a3b221d2a48cf793fbbe39d64abc599bf3a9ea91283f4400cd246` |
| `runner/repro_runtime/prompts/direct.md` | `~/ShieldAgent/repro_runtime/prompts/direct.md` | `1bacdb0` (same as commit) | 352 | `c80f90ae0457380d992fb50566adc6d2ec3b30b114c40aec7b40ff8861fdcc17` |
| `runner/repro_runtime/prompts/explain.md` | `~/ShieldAgent/repro_runtime/prompts/explain.md` | `1bacdb0` (same as commit) | 426 | `c7b01b4f7e6abc5020c09fd35bfa1c4ce99c2b08eac4cb2fdb10c8515ac9d243` |
| `runner/repro_runtime/prompts/extract.md` | `~/ShieldAgent/repro_runtime/prompts/extract.md` | `1bacdb0` (same as commit) | 452 | `905df7e53c9113af1c668dd74e267c5d03890d4284376f6a124132657700074b` |
| `runner/repro_runtime/prompts/planner_system.md` | `~/ShieldAgent/repro_runtime/prompts/planner_system.md` | `1bacdb0` (same as commit) | 3,020 | `4742e4d05a266aabcfff9aee3f874330b68f65df845f835eb782d2a9630c534a` |
| `runner/repro_runtime/prompts/planner_user.md` | `~/ShieldAgent/repro_runtime/prompts/planner_user.md` | `1bacdb0` (same as commit) | 456 | `b3bfa0b7caacaa6ebd5934bb2a04272f5afd4333de371af95df93ef0aa0f2e1f` |
| `runner/repro_runtime/prompts/relevance.md` | `~/ShieldAgent/repro_runtime/prompts/relevance.md` | `1bacdb0` (same as commit) | 1,437 | `d321d5c2567098793c6eff31893f1dae33e26b474435fdcdcb6dec580bb859cc` |
| `runner/repro_runtime/prompts/search.md` | `~/ShieldAgent/repro_runtime/prompts/search.md` | `1bacdb0` (same as commit) | 290 | `b63d9a401dffa0069e0f09c7198f6687772cca80d9fccb24c4ab06485062a800` |
| `runner/repro_runtime/prompts/vocab.md` | `~/ShieldAgent/repro_runtime/prompts/vocab.md` | `1bacdb0` (same as commit) | 447 | `122e2f6dd2f345304019b7e8eac570e2e584f9bf8ceaa4f99cd22d09f0856280` |
| `runner/repro_runtime/shield.py` | `~/ShieldAgent/repro_runtime/shield.py` | `1bacdb0` (same as commit) | 9,003 | `b800205f40b4100f35e68bdbdddca06012cafdb628891105982b1803b3fc2c90` |
| `runner/repro_runtime/verify.py` | `~/ShieldAgent/repro_runtime/verify.py` | `1bacdb0` (same as commit) | 2,512 | `6151003c9ddd99c644e1c8e1b7a662559ab57c08cba49985cf9d4dc1a32a3d4b` |
| `runner/repro_runtime/vocab.py` | `~/ShieldAgent/repro_runtime/vocab.py` | `1bacdb0` (same as commit) | 1,919 | `090816f49446955abb766cf3a3cd569195cd7d46c880656da4c558a4da06f355` |
| `runner/utility/utils.py` | `~/ShieldAgent/utility/utils.py` | `1bacdb0` (same as commit) | 5,962 | `d40b80152f18de43027a1387949e36691bf3d0b23f74341137edde86d2c5f8bc` |
| `runs/luna_train_v5/airline/direct/episodes.jsonl` | `~/ShieldAgent/output/tgr/online/luna_train_v5/airline/direct/episodes.jsonl` | `1bacdb0` (not in git) | 3,323,475 | `c3a055d7e523ae2d783ad5369e6ffb9f62f88861b0c39b071ef44573415e5dd0` |
| `runs/luna_train_v5/airline/none/episodes.jsonl` | `~/ShieldAgent/output/tgr/online/luna_train_v5/airline/none/episodes.jsonl` | `1bacdb0` (not in git) | 2,674,490 | `c933794ee64d59f5a9df8677028e3b3821201d27b86b294388f950b8e38c74a5` |
| `runs/luna_train_v5/airline/tgr/episodes.jsonl` | `~/ShieldAgent/output/tgr/online/luna_train_v5/airline/tgr/episodes.jsonl` | `1bacdb0` (not in git) | 4,218,488 | `3dd77c9334cc9565cc3992048fa215c3a695c8d50b8fe25b612ae4afd44321f0` |
| `runs/luna_train_v5/airline/tgr/run_20261020_122327.json` | `~/ShieldAgent/output/tgr/online/luna_train_v5/airline/tgr/run_20261020_122327.json` | `1bacdb0` (not in git) | 885 | `fbdc2a1375887a61df7b2833b1125c89a7183669dc75c597db174db3ab313b95` |
| `runs/luna_train_v5/retail/direct/episodes.jsonl` | `~/ShieldAgent/output/tgr/online/luna_train_v5/retail/direct/episodes.jsonl` | `1bacdb0` (not in git) | 8,495,233 | `247857131e6693609b82f240fa7f0d9e8f19aa6634bb19547ca0fcef44a9c2c4` |
| `runs/luna_train_v5/retail/none/episodes.jsonl` | `~/ShieldAgent/output/tgr/online/luna_train_v5/retail/none/episodes.jsonl` | `1bacdb0` (not in git) | 7,268,610 | `18ff786037013b4d2eed33fbb266818362ae3a8e151840c6bfe771b66c43a29d` |
| `runs/luna_train_v5/retail/tgr/episodes.jsonl` | `~/ShieldAgent/output/tgr/online/luna_train_v5/retail/tgr/episodes.jsonl` | `1bacdb0` (not in git) | 11,627,181 | `8dc1396da20917bd779a86c6e1494beae37e8cd2933cb1b62ca73cf03688d1fc` |
| `runs/luna_train_v5/retail/tgr/run_20261020_122327.json` | `~/ShieldAgent/output/tgr/online/luna_train_v5/retail/tgr/run_20261020_122327.json` | `1bacdb0` (not in git) | 1,045 | `2792c1921c7e078f7bf7d1b346990a6d942d2de06897881abc3cb356ecc4fb18` |
| `runs/luna_val/airline/direct/episodes.jsonl` | `~/ShieldAgent/output/tgr/online/luna_val/airline/direct/episodes.jsonl` | `1bacdb0` (not in git) | 1,577,019 | `bce3de384c895e8de299cf4e9b43c5509ba44a1ef30da8165e66c823277e07a3` |
| `runs/luna_val/airline/direct/run_20261020_132446.json` | `~/ShieldAgent/output/tgr/online/luna_val/airline/direct/run_20261020_132446.json` | `1bacdb0` (not in git) | 758 | `657d85ccd3dcffd591dee0dec699f7b671f761bfcfadba136473714daf0ab202` |
| `runs/luna_val/airline/none/episodes.jsonl` | `~/ShieldAgent/output/tgr/online/luna_val/airline/none/episodes.jsonl` | `1bacdb0` (not in git) | 1,560,087 | `d5c618bce8dd92982bc25bf5e3a06211c87cc147735954ad20b0379058516430` |
| `runs/luna_val/airline/none/run_20261020_142909.json` | `~/ShieldAgent/output/tgr/online/luna_val/airline/none/run_20261020_142909.json` | `1bacdb0` (not in git) | 756 | `b5966119eed1d06dfcc8ecb8ab2df0165f5f8576d293d3c4a212fa045f628ecf` |
| `runs/luna_val/airline/tgr/episodes.jsonl` | `~/ShieldAgent/output/tgr/online/luna_val/airline/tgr/episodes.jsonl` | `1bacdb0` (not in git) | 2,388,251 | `260c2035d6d8bb4c3a3a6538a5561c2fc939bcfa6270e8afae144c4f2baccd2c` |
| `runs/luna_val/airline/tgr/run_20261020_133048.json` | `~/ShieldAgent/output/tgr/online/luna_val/airline/tgr/run_20261020_133048.json` | `1bacdb0` (not in git) | 802 | `e51ecc703dc0489619e42df846d2335b5135d644e5c19dc4b80d52af377d77d9` |
| `runs/luna_val/retail/direct/episodes.jsonl` | `~/ShieldAgent/output/tgr/online/luna_val/retail/direct/episodes.jsonl` | `1bacdb0` (not in git) | 4,477,430 | `a9e94d6b617fa2e21f7210bf9578b8fba371dd47589c2804db32756ef55f9978` |
| `runs/luna_val/retail/direct/run_20261020_125556.json` | `~/ShieldAgent/output/tgr/online/luna_val/retail/direct/run_20261020_125556.json` | `1bacdb0` (not in git) | 839 | `fffa54de0d4229fa8795a88448896479701cb4674af268ad9b4427de216835ea` |
| `runs/luna_val/retail/none/episodes.jsonl` | `~/ShieldAgent/output/tgr/online/luna_val/retail/none/episodes.jsonl` | `1bacdb0` (not in git) | 3,774,147 | `d7977d493de2f65d4cff2ea4bef39ae7be3aca351bb097ef71a201bb1417f893` |
| `runs/luna_val/retail/none/run_20261020_131531.json` | `~/ShieldAgent/output/tgr/online/luna_val/retail/none/run_20261020_131531.json` | `1bacdb0` (not in git) | 837 | `ce6fc233a08923574de1969284b6cfe8df01ee9944bb117057e1b0764e7f68c2` |
| `runs/luna_val/retail/tgr/episodes.jsonl` | `~/ShieldAgent/output/tgr/online/luna_val/retail/tgr/episodes.jsonl` | `1bacdb0` (not in git) | 6,092,268 | `07446ae051e2ccd3d2f835d11907f747466cf18658cf12fb50d92850ff215e8a` |
| `runs/luna_val/retail/tgr/run_20261020_125556.json` | `~/ShieldAgent/output/tgr/online/luna_val/retail/tgr/run_20261020_125556.json` | `1bacdb0` (not in git) | 882 | `1542f287f7e0b41e4c10450bef08882868c17d7243570c7a1621c49ad333fe89` |
| `runs/nano_train/airline/direct/episodes.jsonl` | `~/ShieldAgent/output/tgr/online/nano_train/airline/direct/episodes.jsonl` | `1bacdb0` (not in git) | 9,854,428 | `bdff1d126cc956b55203070d25989657d7d734198ba6cc8fb187048e02a1dbaa` |
| `runs/nano_train/airline/direct/run_20261020_183929.json` | `~/ShieldAgent/output/tgr/online/nano_train/airline/direct/run_20261020_183929.json` | `1bacdb0` (not in git) | 1,036 | `f7211456d1712eb89a42e063de6a65bdb7d8043d9a071461d60474a6eea89343` |
| `runs/nano_train/airline/none/episodes.jsonl` | `~/ShieldAgent/output/tgr/online/nano_train/airline/none/episodes.jsonl` | `1bacdb0` (not in git) | 4,290,562 | `c78d142fe3947a1b76372fc21e6bebd997f601e792ba03585a8bb85d4d35b486` |
| `runs/nano_train/airline/none/run_20261020_210453.json` | `~/ShieldAgent/output/tgr/online/nano_train/airline/none/run_20261020_210453.json` | `1bacdb0` (not in git) | 1,034 | `45464757841433e1bbbdb42ac24c4e6c1816599984874500df92802396d81641` |
| `runs/nano_train/airline/tgr/episodes.jsonl` | `~/ShieldAgent/output/tgr/online/nano_train/airline/tgr/episodes.jsonl` | `1bacdb0` (not in git) | 8,185,831 | `81e3cb1330d82829ceb92d667266c5095b379aed71d0c9e478628363387e6b1e` |
| `runs/nano_train/airline/tgr/run_20261020_210326.json` | `~/ShieldAgent/output/tgr/online/nano_train/airline/tgr/run_20261020_210326.json` | `1bacdb0` (not in git) | 1,080 | `a8580d3e3c3b8bc8bcdaa25e5f57269a3f17388d6ef58e1361a4b9150d4dfd41` |
| `runs/nano_train/retail/direct/episodes.jsonl` | `~/ShieldAgent/output/tgr/online/nano_train/retail/direct/episodes.jsonl` | `1bacdb0` (not in git) | 16,878,482 | `8653be77950008cdb35e311f16eb996c810bce46dc517d0a23ae4b199e2d1396` |
| `runs/nano_train/retail/direct/run_20261020_160307.json` | `~/ShieldAgent/output/tgr/online/nano_train/retail/direct/run_20261020_160307.json` | `1bacdb0` (not in git) | 1,197 | `dac5ac9b53c3490d8b41c37e0cc46d22da9123e17bc2d7812936d80e25bc198b` |
| `runs/nano_train/retail/none/episodes.jsonl` | `~/ShieldAgent/output/tgr/online/nano_train/retail/none/episodes.jsonl` | `1bacdb0` (not in git) | 9,709,458 | `769226b6ceee3fa80095bf6096cd1bbe837b912cb0f1d6598412392515c99f1d` |
| `runs/nano_train/retail/none/run_20261020_173457.json` | `~/ShieldAgent/output/tgr/online/nano_train/retail/none/run_20261020_173457.json` | `1bacdb0` (not in git) | 1,195 | `8e7652ec4a6ff419135d41d2031c1062bc6a5b6ebc0bfa76d7fef51c717d46ed` |
| `runs/nano_train/retail/tgr/episodes.jsonl` | `~/ShieldAgent/output/tgr/online/nano_train/retail/tgr/episodes.jsonl` | `1bacdb0` (not in git) | 18,933,226 | `1f3e8255862179513f5cb14aae529e4f1dc69d705a3effd97706a32059e27c36` |
| `runs/nano_train/retail/tgr/run_20261020_160307.json` | `~/ShieldAgent/output/tgr/online/nano_train/retail/tgr/run_20261020_160307.json` | `1bacdb0` (not in git) | 1,240 | `af560d7e113a96b491fd1e25d0df05c4ad8932fb6c10887058d02e76c110a363` |
| `scoring/aspm/airline_aspm.json` | `~/ShieldAgent/aspm/airline_aspm.json` | `1bacdb0` (same as commit) | 72,937 | `c2749199d9355459f4f00a3a16509588b3219f3f7d281ea561952846e97b0a81` |
| `scoring/aspm/retail_aspm.json` | `~/ShieldAgent/aspm/retail_aspm.json` | `1bacdb0` (same as commit) | 62,516 | `1d66d45869ecb19d808f18d05ef5e02fbe01b9fc35a9a789e1b676b94c43d036` |
| `scoring/exp_core/model_profiles.json` | `~/ShieldAgent/exp_core/model_profiles.json` | `1bacdb0` (same as commit) | 2,610 | `03c46ecfbc813e1be2a2cefec865a68b21dc8266ef42c1aaf9e2997b006a2b7e` |
| `scoring/policies/curated/airline_config.json` | `~/ShieldAgent/policies/curated/airline_config.json` | `1bacdb0` (same as commit) | 311 | `443e3e8f1b7d690eceed2e63097dfe6f7e1cf7a86880f3477b94e4aaa2263a39` |
| `scoring/policies/curated/retail_config.json` | `~/ShieldAgent/policies/curated/retail_config.json` | `1bacdb0` (same as commit) | 184 | `caff7f3e53ba778b154eacbe4af1f96da7b5f3cf08691ec0215264e094c63fba` |
| `scoring/policies/gold_v2/README.md` | `~/ShieldAgent/policies/gold_v2/README.md` | `1bacdb0` (same as commit) | 7,918 | `91761cf5d3dc24a49f27876f07e02c3679205fa7b767c47a50293fb681f20f8a` |
| `scoring/policies/gold_v2/checks.py` | `~/ShieldAgent/policies/gold_v2/checks.py` | `1bacdb0` (same as commit) | 8,400 | `e4341733638ecf81fc6674f0363ee38fd8ceb6683f13e90d659e4f0ba511ea1a` |
| `scoring/policies/predicates/airline_predicates.json` | `~/ShieldAgent/policies/predicates/airline_predicates.json` | `1bacdb0` (same as commit) | 44,144 | `d89157860882ffa061d9e706572bc6c20039e81ec9bf27a130bd68f17e6d144c` |
| `scoring/policies/predicates/retail_predicates.json` | `~/ShieldAgent/policies/predicates/retail_predicates.json` | `1bacdb0` (same as commit) | 26,081 | `b6ab4cf071b78cabce78c70dc6e471f5215a99f2b0c26977ed46193d88ee028b` |
| `scoring/policies/tau_bench/airline_tools.json` | `~/ShieldAgent/policies/tau_bench/airline_tools.json` | `1bacdb0` (same as commit) | 23,372 | `625018425fea8251f55dd2a060a0cb6e5a7f56cdf7ebfcd082e763d1ac76c13e` |
| `scoring/policies/tau_bench/retail_tools.json` | `~/ShieldAgent/policies/tau_bench/retail_tools.json` | `1bacdb0` (same as commit) | 26,536 | `fd9fd3ac470b4b26c4719fd031f54cf9413665a467fe47fa3eeb2e32d07bb6ef` |
| `scoring/scripts/reproduction/gold_compare.py` | `~/ShieldAgent/scripts/reproduction/gold_compare.py` | `1bacdb0` (same as commit) | 5,600 | `9ab7bb2599b890006ab1e2d65ff92d0bdfe90b8d407129cbc52f159ecab336fd` |
| `scoring/scripts/reproduction/p6_gold_score.py` | `~/ShieldAgent/scripts/reproduction/p6_gold_score.py` | `1bacdb0` (same as commit) | 6,969 | `dfc40dbf4178c7de5cec4c2f7b51990508c116e3e7c6b36bbb6e19322e9cc4e5` |
| `scoring/scripts/reproduction/p6_metrics.py` | `~/ShieldAgent/scripts/reproduction/p6_metrics.py` | `1bacdb0` (same as commit) | 6,512 | `02474548487daea7690df7881190d8086c11150d3f4ff6873027e7f078f76a92` |
| `scoring/scripts/tgr/metrics.py` | `~/ShieldAgent/scripts/tgr/metrics.py` | `1bacdb0` (same as commit) | 8,175 | `0c4b7c10b570a3a3258c1ca42c819caa9f54ea4136c0bbf54a03d341c7132352` |
| `scoring/scripts/validate_aspm.py` | `~/ShieldAgent/scripts/validate_aspm.py` | `1bacdb0` (same as commit) | 23,029 | `cc5f33bb9b451d847401d6413cf985e65508feec1b4c44e356d086d627800b5d` |
| `splits/splits.json` | `~/ShieldAgent/output/reproduction/labels/splits.json` | `1bacdb0` (not in git) | 3,812 | `a3ab3471c67dad9ae3c4d8e252b13282317ad65d648e5a008e1d934568f4abb5` |
| `tau_bench/LICENSE` | `~/opt/tau-bench-59a200c/LICENSE` | `59a200c` (same as commit) | 1,063 | `243d23d45b80122b5ac575586ccef352fdc9c45e6d7d2605449aca8a17478b42` |
| `tau_bench/tau_bench/__init__.py` | `~/opt/tau-bench-59a200c/tau_bench/__init__.py` | `59a200c` (same as commit) | 112 | `be00bb8ea6d5a3bf99b20ae7cc35dd9839acf837e8577f1a8c8cbfd67e45edf9` |
| `tau_bench/tau_bench/envs/__init__.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/__init__.py` | `59a200c` (same as commit) | 1,073 | `a11d9a4de44b931c111ca32042278bdbbda0902364b2a85386f20e30499d6ffe` |
| `tau_bench/tau_bench/envs/airline/__init__.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/airline/__init__.py` | `59a200c` (same as commit) | 104 | `05a6a8b66b8bb5e8494ea7deedb08fe5427323e788102bb77c676db89a88a5af` |
| `tau_bench/tau_bench/envs/airline/data/__init__.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/airline/data/__init__.py` | `59a200c` (same as commit) | 564 | `eca21174cec321e2c3e0438e9bf67035dbb3a8551dc2a1d3a793b4395d8192c1` |
| `tau_bench/tau_bench/envs/airline/data/flights.json` | `~/opt/tau-bench-59a200c/tau_bench/envs/airline/data/flights.json` | `59a200c` (same as commit) | 2,114,218 | `444d7565c68434a3e3fb72efd717f9f9cd5c56dce227f6f56e078f1cb0ed233a` |
| `tau_bench/tau_bench/envs/airline/data/reservations.json` | `~/opt/tau-bench-59a200c/tau_bench/envs/airline/data/reservations.json` | `59a200c` (same as commit) | 2,325,594 | `1cf0bbc58ad984be9de7c24dba6dd27393f94cdbd482d8524f6a54db1f561a8c` |
| `tau_bench/tau_bench/envs/airline/data/users.json` | `~/opt/tau-bench-59a200c/tau_bench/envs/airline/data/users.json` | `59a200c` (same as commit) | 595,947 | `bd264e2a31e0fa35cdfef8987e70a0dd3776828b582fe90e7a44823a12eb4cea` |
| `tau_bench/tau_bench/envs/airline/tools/__init__.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/airline/tools/__init__.py` | `59a200c` (same as commit) | 1,088 | `98cbafc429cf917a088112b652ec6ef8641b509f0981c04047875f90ec4967f3` |
| `tau_bench/tau_bench/envs/airline/tools/book_reservation.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/airline/tools/book_reservation.py` | `59a200c` (same as commit) | 10,282 | `927ca66e6bf289d27582c939d7300ee028ed0a237e2592afed160265f9953304` |
| `tau_bench/tau_bench/envs/airline/tools/calculate.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/airline/tools/calculate.py` | `59a200c` (same as commit) | 1,266 | `3be497428304817e4dae17222dc9d1d41a27d28bf0abc2a613687a6e890d70fe` |
| `tau_bench/tau_bench/envs/airline/tools/cancel_reservation.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/airline/tools/cancel_reservation.py` | `59a200c` (same as commit) | 1,528 | `5dd83916f9dce20a4bac6ecf45c2f4555ae28f0981339c7d237d3f98af2e6b98` |
| `tau_bench/tau_bench/envs/airline/tools/get_reservation_details.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/airline/tools/get_reservation_details.py` | `59a200c` (same as commit) | 1,082 | `3c45957d9489e4226000de99f015c67ca5cc920f867c5a5739edba20cd920b6b` |
| `tau_bench/tau_bench/envs/airline/tools/get_user_details.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/airline/tools/get_user_details.py` | `59a200c` (same as commit) | 1,028 | `50cd80bee1fa2da99852ebd37289964f0b5f34994d9f34104f7d6953216fa7c4` |
| `tau_bench/tau_bench/envs/airline/tools/list_all_airports.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/airline/tools/list_all_airports.py` | `59a200c` (same as commit) | 1,633 | `8c6921b793ce6e93bfa18024e40fa1136f8c4e8204f8fa6f0248beaf674651ba` |
| `tau_bench/tau_bench/envs/airline/tools/search_direct_flight.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/airline/tools/search_direct_flight.py` | `59a200c` (same as commit) | 2,014 | `ca64bab422da436c0ab9e3a77135f786ca934e8cb917d502f0dbab2847716c78` |
| `tau_bench/tau_bench/envs/airline/tools/search_onestop_flight.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/airline/tools/search_onestop_flight.py` | `59a200c` (same as commit) | 3,240 | `205b32a28de70bff29f8846c875964af78c6d6d94685bf79579861b3308efa3d` |
| `tau_bench/tau_bench/envs/airline/tools/send_certificate.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/airline/tools/send_certificate.py` | `59a200c` (same as commit) | 1,765 | `d067a526d0a3579cd4a814fa14d231a62da4854520124ff2af8969f16715a773` |
| `tau_bench/tau_bench/envs/airline/tools/think.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/airline/tools/think.py` | `59a200c` (same as commit) | 980 | `ff2b17409d3d6fade8657e2ada46b0b50e33c6570502cba4ec0202652c51ffa5` |
| `tau_bench/tau_bench/envs/airline/tools/transfer_to_human_agents.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/airline/tools/transfer_to_human_agents.py` | `59a200c` (same as commit) | 1,144 | `d3f105f8a8efc11e8dbb039b12e9e1d86d7c1f1ae16a26bd2bbf41cde2b21db6` |
| `tau_bench/tau_bench/envs/airline/tools/update_reservation_baggages.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/airline/tools/update_reservation_baggages.py` | `59a200c` (same as commit) | 3,268 | `5b72dc0fcd0a2ae21bb116ddc0a76dcc5d2fc2c71dec1fae75942f24f5d6eafd` |
| `tau_bench/tau_bench/envs/airline/tools/update_reservation_flights.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/airline/tools/update_reservation_flights.py` | `59a200c` (same as commit) | 6,070 | `58ef41d20d5ba53782dce1bbcbd514aaa6fcb0670980f54070d8263ab9f8b985` |
| `tau_bench/tau_bench/envs/airline/tools/update_reservation_passengers.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/airline/tools/update_reservation_passengers.py` | `59a200c` (same as commit) | 2,712 | `6ed46b57dc3c6c487219720a10f116774686046f11868c747493ae9a703d2957` |
| `tau_bench/tau_bench/envs/base.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/base.py` | `59a200c` (same as commit) | 5,688 | `1ad0402073f0ac9ca6b527efa0706e2aa8836dd2e5c1d453ed414ecb768c6d21` |
| `tau_bench/tau_bench/envs/retail/__init__.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/__init__.py` | `59a200c` (same as commit) | 101 | `39a98c9311d0713c4464a0c17630c373fb74b4a24379f24dfd9f7cec5f130c0f` |
| `tau_bench/tau_bench/envs/retail/data/__init__.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/data/__init__.py` | `59a200c` (same as commit) | 544 | `aaa0bc456497d79438c5c7602194444d2774f6d225ece1e9d3ad91e03bc1d288` |
| `tau_bench/tau_bench/envs/retail/data/orders.json` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/data/orders.json` | `59a200c` (same as commit) | 1,810,945 | `2598a12586d28f2d6bd16bc86f4c800029b6af18e0abb5c475ef5c869c11ced1` |
| `tau_bench/tau_bench/envs/retail/data/products.json` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/data/products.json` | `59a200c` (same as commit) | 172,258 | `a9eabcc1a9742c5f5288c2779acce52b9308423383ed24706bbaf0889f762a0f` |
| `tau_bench/tau_bench/envs/retail/data/readme.md` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/data/readme.md` | `59a200c` (same as commit) | 1,420 | `448640f4b5e104f15e4476e2aa10f3b6616181135dc38262a86e71ed1b30737d` |
| `tau_bench/tau_bench/envs/retail/data/users.json` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/data/users.json` | `59a200c` (same as commit) | 322,932 | `6f4fd104cc5e80b92166c4035315c31532c6cea52a90dcdf18425ee7f87c2b82` |
| `tau_bench/tau_bench/envs/retail/tools/__init__.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/tools/__init__.py` | `59a200c` (same as commit) | 1,302 | `db8f1252a01eaa333ee409d78858d5dcf5cdc2f27c24bc6d941615ccd2ac54df` |
| `tau_bench/tau_bench/envs/retail/tools/calculate.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/tools/calculate.py` | `59a200c` (same as commit) | 1,324 | `2c3380802673493843ef6d7f3e569e2aed52265ca0b9f7ac248346828d0c75f7` |
| `tau_bench/tau_bench/envs/retail/tools/cancel_pending_order.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/tools/cancel_pending_order.py` | `59a200c` (same as commit) | 3,320 | `c33151a896b62ac87ed1bcbcbd62dabcd47c8c1eaf47bbb5e2f15f8b6283b19d` |
| `tau_bench/tau_bench/envs/retail/tools/exchange_delivered_order_items.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/tools/exchange_delivered_order_items.py` | `59a200c` (same as commit) | 5,370 | `d547d44b28e97513d4a15714d4bd2bbca13f76827bfe06b71e1b51a742f44489` |
| `tau_bench/tau_bench/envs/retail/tools/find_user_id_by_email.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/tools/find_user_id_by_email.py` | `59a200c` (same as commit) | 1,132 | `a289f00eb689146f102d97951d6e7b29c9c639314c203efbfcd888f893d91560` |
| `tau_bench/tau_bench/envs/retail/tools/find_user_id_by_name_zip.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/tools/find_user_id_by_name_zip.py` | `59a200c` (same as commit) | 2,013 | `22c176ffc285b25db573e0e38d82d678e2641298c6d1318f69d2582d52eb7433` |
| `tau_bench/tau_bench/envs/retail/tools/get_order_details.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/tools/get_order_details.py` | `59a200c` (same as commit) | 1,087 | `ca6c23cc89c1e981251b9adb1e6d705e364ff942aee986b12335b36e94281056` |
| `tau_bench/tau_bench/envs/retail/tools/get_product_details.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/tools/get_product_details.py` | `59a200c` (same as commit) | 1,104 | `9578fb31b5e092361a5d0e5d4a8e2afe4b8fb4a96d279d031b01266d9b5c768d` |
| `tau_bench/tau_bench/envs/retail/tools/get_user_details.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/tools/get_user_details.py` | `59a200c` (same as commit) | 1,021 | `f22b59126c2a2aaa102f39dea778653a9298d1902477dd5246509d019318e8d3` |
| `tau_bench/tau_bench/envs/retail/tools/list_all_product_types.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/tools/list_all_product_types.py` | `59a200c` (same as commit) | 1,035 | `63b9f562f893bab36fc6fb91da92978ba9c106f2d6fad88aee3ca20801e4a2e3` |
| `tau_bench/tau_bench/envs/retail/tools/modify_pending_order_address.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/tools/modify_pending_order_address.py` | `59a200c` (same as commit) | 3,212 | `8f23d24511078ca10818fac8501db358ad699584952233d696a695e78993d001` |
| `tau_bench/tau_bench/envs/retail/tools/modify_pending_order_items.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/tools/modify_pending_order_items.py` | `59a200c` (same as commit) | 5,707 | `f1a39d42e42c162dc961afa7f1b4d29c73c5a3710a3b9dff318a076213b6c858` |
| `tau_bench/tau_bench/envs/retail/tools/modify_pending_order_payment.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/tools/modify_pending_order_payment.py` | `59a200c` (same as commit) | 4,364 | `6c2d4c329fae0d66d50bd48cb6ae9520167137f8b20d3385fa407aa5b03d2fe5` |
| `tau_bench/tau_bench/envs/retail/tools/modify_user_address.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/tools/modify_user_address.py` | `59a200c` (same as commit) | 2,920 | `b1f8ac2141056ccee668824d6ab124ce659ea3574e7b186b39af3f558c07ac61` |
| `tau_bench/tau_bench/envs/retail/tools/return_delivered_order_items.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/tools/return_delivered_order_items.py` | `59a200c` (same as commit) | 3,632 | `7d92e8962c17e5fa9c8e3240d21e31fc1adf5e68100c92bb0f67e0a67ea5b7bf` |
| `tau_bench/tau_bench/envs/retail/tools/think.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/tools/think.py` | `59a200c` (same as commit) | 1,160 | `9d9423922fcdc98578c1d6544f35d28ff155e9a5a172355b662db326ef7eb1fc` |
| `tau_bench/tau_bench/envs/retail/tools/transfer_to_human_agents.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/retail/tools/transfer_to_human_agents.py` | `59a200c` (same as commit) | 1,200 | `2b6d4685da53f72709b28b60e14e1897947ac366bc7ecee6d2b7c7169a3d95a6` |
| `tau_bench/tau_bench/envs/tool.py` | `~/opt/tau-bench-59a200c/tau_bench/envs/tool.py` | `59a200c` (same as commit) | 233 | `0a158be298092fc64862ae8843f35f57cfba139aa02c2ee8fbe87b1e4a1de0fc` |
