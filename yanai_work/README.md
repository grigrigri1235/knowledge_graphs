# ShieldAgent on τ-bench: a faithful reproduction, and TGR, a tool-grounded rule guard

> **Start here:** [docs/SUMMARY_REPORT.md](docs/SUMMARY_REPORT.md) (the whole story, for readers new to the project) and
> [docs/RESULTS.md](docs/RESULTS.md) (every experiment: setup, tables with CIs, costs, links). Coding agents: `AGENTS.md`.

## Current status (2026-10-20)
1. **Reproduction (done, 2026-10-17).** Faithful ShieldAgent, Stage A, gpt-5-nano for every role; P6 online
   evaluation on the test split (details below).
2. **TGR stage (method frozen; final evaluation pending).** Our method TGR = A tool-grounded rules + B restriction-only
   rule writing + C actionable feedback (`method_tgr/`), developed on train with gpt-6-luna and frozen at git tag
   `tgr-frozen-v1`; checked on the val split; weak-agent experiment with gpt-5-nano agent and gpt-6-luna guards.
   The final evaluation with grok-4.7 on the test split has **not been run** (needs approval and budget).

Headline pass^1 (mean reward over tasks × 3 trials; CIs and all other metrics in `docs/RESULTS.md`):

| experiment (split; agent / guards) | domain | no guard | Direct | ShieldAgent | TGR (frozen) |
|---|---|---|---|---|---|
| P6 reproduction (test; gpt-5-nano / gpt-5-nano) | airline | 0.300 | 0.267 | 0.250 | – |
| | retail | 0.348 | 0.391 | 0.145 | – |
| development (train; gpt-6-luna / gpt-6-luna) | airline | 0.533 | 0.467 | 0.383 | 0.500 |
| | retail | 0.761 | 0.681 | 0.362 | 0.710 |
| validation (val; gpt-6-luna / gpt-6-luna) | airline | 0.633 | 0.567 | 0.400 | 0.633 |
| | retail | 0.667 | 0.609 | 0.362 | **0.710** |
README_STEP5_ROW

## The reproduction (Stage A)

**Goal.** Reproduce *ShieldAgent* (Chen et al., ICML 2025, arXiv 2503.22738v2; copy in `docs/paper/shieldagent.pdf`) as faithfully as possible:
1. policy document → verifiable LTLf rules (ASPM);
2. runtime enforcement with probabilistic rule circuits;
3. evaluation on τ-bench v1 (airline, retail).

Every LLM role uses **gpt-5-nano on Azure**. The result is the **baseline** that later methods (master's research) are compared against. Deviations from the paper are documented, rules are never hand-fixed, and the hand-written gold rules are used only to score.

### Status of the reproduction (2026-10-17)
**Stage A is finished**: uniform rule weights θ = 1, ε = 0.1, no weight learning, no workflow memory. It covers P0 infrastructure, P1 rule extraction, P2 runtime shield, and P6 online evaluation (594 conversations: τ-bench TEST split of `splits.json`, 3 trials per task, gpt-5-nano agent and user simulator). Stage B (weight learning, offline evaluation, memory) has not been started.

Headline result (pass^1 = mean reward; source: `docs/reproduction/p6_report.md`):
| domain | no shield | Direct guard (one LLM call with the full policy) | ShieldAgent |
|---|---|---|---|
| airline (20 tasks) | 0.300 | 0.267 | 0.250 |
| retail (46 tasks) | 0.348 | 0.391 | **0.145** |

ShieldAgent does not help:
- **Task success:** in retail it costs 20 points of pass^1 (paired 95 % CI −0.31 to −0.10).
- **Blocks:** it blocks about 10 times per retail conversation, mostly through defective rules and abstract action mapping.
- **Precision:** its blocks of write calls are less precise than Direct's (0.13 / 0.24 vs 0.52 / 0.59 against the gold scorer).
- **Cost:** it is 2–3× more expensive than Direct.

Direct is at least as good on every metric.

## Requirements
- An Azure VM with a **Managed Identity** that can call the Azure OpenAI deployment `gpt-5-nano`. The endpoint and deployment are set in `utility/utils.py`. No API key or `.env` is used. The TGR stage also uses the deployments `gpt-6-luna` and `grok-4.7` on the same endpoint (GlobalStandard; names in `exp_core/model_profiles.json`).
- Python venv `~/venvs/tau-bench` (pinned packages: `docs/reproduction/venv_freeze.txt`; τ-bench installed from `~/opt/tau-bench-59a200c`). The read-only τ-bench reference clone `~/refs/tau-bench` supplies the recorded trajectories (data only; its code is never run).
- Optional environment variable: `REPRO_EMBEDDING_BACKEND` (`local` by default; see `repro_core/config.json`).
- The VM has 1.9 GB RAM and 1 CPU. Run **at most 3 heavy processes at once**, and start long jobs with `setsid nohup … &` (all runners are resumable).

Use `PY=~/venvs/tau-bench/bin/python` in the commands below; run from the repository root.

> **Do not overwrite results.** The existing run ids and tags (`output/repro/aspm_runs/airline/v4`, `output/repro/aspm_runs/retail/v1`, p2_pilot tags `A`, `A2`, `A2_rerun`, `B`, `direct`, p6 tag `full`) are the reported results. Use a new `--run-id` / `--tag` for new runs. `p2_pilot.py` truncates the `steps.jsonl` of its tag; `repro_online.run` only appends (it skips finished conversations).

## How to run each stage
**P1: build an ASPM from a policy** (≈ 1 h and ≈ $1 per domain; replays from `output/repro/_llmcache/` when the prompts are unchanged):
```bash
setsid nohup $PY -m repro_pipeline.run --policy policy_docs/airline_wiki.txt --domain airline --run-id v5 \
  > output/repro/p1_airline_v5.log 2>&1 &
# outputs: output/repro/aspm_runs/airline/v5/{e1_policies,e2_rules,alg2,e5_circuits,aspm,weights,manifest,log}.json
# --publish aspm_repro/airline copies aspm.json, weights.json, manifest.json (the published ASPMs are already in aspm_repro/)
```

**P2: offline pilot on recorded steps** (optional; ≈ $1 per configuration):
```bash
# targets: output/repro/p2_pilot/targets.json (seeded; already present, re-running p2_select_pilot.py rewrites it identically)
$PY scripts/reproduction/p2_pilot.py --domain airline --tag A_new               # config A: aux calls low, planner medium
$PY scripts/reproduction/p2_pilot.py --domain airline --tag direct_new --direct
$PY scripts/reproduction/p2_pilot_summary.py airline --a A2 --fresh A --rerun A2_rerun   # summary of the reported pilot
```

**P6: online τ-bench evaluation** (≈ $21 and ≈ 5.5 h for all 594 conversations; resumable, finished (task, trial) pairs are skipped):
```bash
mkdir -p output/repro/p6/new/logs
for g in none direct shield; do
  setsid nohup $PY -u -m repro_online.run --env retail --guard $g --tasks test --trials 3 --tag new --workers 8 \
    >> output/repro/p6/new/logs/retail_$g.log 2>&1 &
done          # then the same for --env airline (≤ 3 processes at a time)
# output: output/repro/p6/<tag>/<domain>/<guard>/episodes.jsonl (the reported run is tag `full`)
```

**Metrics** (no LLM calls):
```bash
$PY scripts/reproduction/p6_gold_score.py full    # D9 gold scorer → .../gold.jsonl (scoring only; deterministic)
$PY scripts/reproduction/p6_metrics.py full       # → output/repro/p6/full/metrics.json (deterministic; recomputed byte-identically in the cleanup)
$PY scripts/reproduction/p6_show_episode.py full retail shield 10 0   # render one conversation
```

### TGR stage: how to run (profiles in `exp_core/model_profiles.json`; see `AGENTS.md` §4d)
```bash
# TGR rule build (one call per domain; cached) → output/tgr/tgr_rules/<profile>/<domain>/<run>/; frozen sets: tgr_rules/<domain>/frozen/
$PY -m exp_core.tgr_build --profile luna-dev --env retail --run-id myrun --effort high            # --no-b: ablation
# ShieldAgent P1 rebuilt with a profile (frozen pipeline, Domain Basic removed from the input)
$PY -m exp_core.run_p1 --profile luna-dev --domain retail --policy policy_docs/retail_wiki.txt --drop-heading "Domain Basic" --run-id v1
# online runs (resumable) → output/tgr/online/<tag>/<env>/<guard>/episodes.jsonl
setsid nohup $PY -u -m exp_core.run_online --profile luna-dev --env retail --guard tgr --tasks val --trials 3 --tag mytag \
  --workers 8 --rules-dir tgr_rules/retail/frozen >> mytag_retail_tgr.log 2>&1 &
#   --guard none | direct | shield (--aspm-dir output/tgr/aspm_runs/luna-dev/retail/v1) | tgr | tgr_nob | tgr_noc
#   --profile nano-agent-luna: gpt-5-nano agent, gpt-6-luna user simulator and guards; grok-eval: final evaluation only, after approval
# metrics (no LLM calls): gold v1 + v2, paired Δ, violations attempted/blocked/executed, transfers
$PY scripts/tgr/metrics.py mytag --guards none,direct,shield,tgr
$PY scripts/reproduction/gold_compare.py ../../tgr/online/mytag
```

**Tests** (include the leakage test that keeps gold data out of the method code):
```bash
$PY -m unittest discover -s tests -t .
```

## Backup & restore
`output/` (results and LLM caches) and `archive/**/data/` are **not in git**.

**Latest backup (2026-10-20; includes the TGR stage: Phase 1–2 runs with gpt-6-luna, gold v2 scores, `output/tgr/` caches):**
- **File:** `~/backups/shieldagent_output_20261020.tar.gz` (471 MB compressed, 87,378 files; same exclusion as below).
- **Checksum:** SHA-256 `dd5eaeaba8fdb79d0bd3910e2db7f9205e059fd2eae02a315692cd7cf33b3e20` (`.sha256` next to it).
- **Verified:** test extraction (identical `splits.json`, P6 and Phase 1 `metrics.json`, a Phase 2 `episodes.jsonl`) and
  a download check from the release (SHA-256 OK).
- **Off-VM copy:** <https://github.com/yanai-1701/ShieldAgent_Taubench/releases/tag/results-backup-2026-10-20> (tag on
  commit `e32ba95`; assets `shieldagent_output_20261020.tar.gz` (493,766,541 bytes) and `.sha256`). Download and restore
  as below, with the date `20261020` and the tag `results-backup-2026-10-20`.

**Earlier backup (2026-10-17):**
- **File:** `~/backups/shieldagent_output_20261017.tar.gz` (325 MB compressed, 55,546 files; about 973 MB unpacked).
- **Checksum:** `~/backups/shieldagent_output_20261017.tar.gz.sha256` (SHA-256 `bffbcfb98af93216e1f05f12585f274c1674fdb12a2205b4a3f64cf3a872908f`).
- **Verified** by a test extraction: identical file counts, and identical `metrics.json` and `splits.json`.

**Backed up:** all of `output/` and `archive/`. That includes:
- the P6 episodes, gold scores and metrics;
- P2 pilot records and P1 run directories;
- `splits.json` and labels;
- the paid LLM caches `output/repro/_llmcache/` (503 MB) and `output/auto_aspm/_cache/` (214 MB);
- the embedding cache;
- the authors' AutoPolicy runs;
- the archived superseded runs.

**Excluded (regenerable without paid calls):** the bf16 copy of the embedding model, `output/repro/_models/BAAI--bge-large-en-v1.5@d4aa6901d3a4-bfloat16/` (641 MB). It is re-created automatically the first time a new text is embedded. To create it explicitly (downloads the pinned snapshot `BAAI/bge-large-en-v1.5` @ `d4aa6901d3a41ba39fb536a557fa166f842b0e09` from the Hugging Face Hub into `~/.cache/huggingface`, then converts it to bfloat16):
```bash
$PY -c "from repro_core import embed; embed._local_model(embed.config()['local'])"
```
Embeddings already computed are in the backed-up cache `output/repro/_embcache/embeddings.sqlite`, so reruns of P1 do not need the model unless they embed new texts.

**Off-VM copy (GitHub Release):** <https://github.com/yanai-1701/ShieldAgent_Taubench/releases/tag/results-backup-2026-10-17>. It has two assets: `shieldagent_output_20261017.tar.gz` (340,583,940 bytes) and its `.sha256`. The tag points at commit `521b0c4`. Download check on 2026-10-17: SHA-256 OK. The repository is private, so downloads need a token with read access:
```bash
mkdir -p ~/backups && cd ~/backups
# GH_TOKEN must hold a GitHub token with read access to the private repo (never commit or log it)
for f in shieldagent_output_20261017.tar.gz shieldagent_output_20261017.tar.gz.sha256; do
  id=$(curl -s -H "Authorization: Bearer $GH_TOKEN" \
        https://api.github.com/repos/yanai-1701/ShieldAgent_Taubench/releases/tags/results-backup-2026-10-17 \
        | python3 -c "import sys,json; print([a['id'] for a in json.load(sys.stdin)['assets'] if a['name']=='$f'][0])")
  curl -sL -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/octet-stream" -o "$f" \
       https://api.github.com/repos/yanai-1701/ShieldAgent_Taubench/releases/assets/$id
done
# or, with the GitHub CLI: gh release download results-backup-2026-10-17 -R yanai-1701/ShieldAgent_Taubench
```

**Restore** (from the repository root, after the download; the repository itself comes from `git clone https://github.com/yanai-1701/ShieldAgent_Taubench.git`):
```bash
cd ~/backups && sha256sum -c shieldagent_output_20261017.tar.gz.sha256
cd ~/ShieldAgent && tar -xzf ~/backups/shieldagent_output_20261017.tar.gz      # recreates output/ and archive/
$PY scripts/reproduction/p6_metrics.py full                                   # optional check: no LLM calls
```
Copy the backup off the VM (for example `scp ~/backups/shieldagent_output_20261017.tar.gz* <host>:`): a backup on the same disk does not survive the loss of the VM.

## Where things are
- `AGENTS.md`: onboarding for coding agents (rules, paper → code map, history, bugs, gotchas, next steps).
- `docs/STRUCTURE.md`: every folder and file.
- `docs/reproduction/`: specification, logs and reports.
- `archive/`: historical material (the authors' original README, early AutoPolicy visualisation, superseded runs).
- License: MIT (`LICENSE`, from the authors' repository).
