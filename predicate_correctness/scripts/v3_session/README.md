# Old v3 session scripts (archive copies, read only)

Byte-identical copies of helper scripts from the tracker v3 session, kept here because their temp folder can vanish.
Copied 2026-10-23 by build agent A11 (tracker v4, P1). Do not edit them. The v4 scripts in `scripts/` are the
generic versions.

- Source: `/tmp/claude-1000/-home-azureuser-code-projects/dbfe7ffd-ee14-4b6f-ab52-d79bdd15e981/scratchpad/<same path>`.
- `older_7c3c1535/dry_all.sh`: from the older session
  `/tmp/claude-1000/-home-azureuser-code-projects/7c3c1535-bd0d-4a16-af35-122f073a1f9e/scratchpad/dry_all.sh`.
- `SHA256SUMS`: the sha256 of every copy (`sha256sum -c SHA256SUMS` from this folder). They were checked against the
  sources at copy time: all equal.

## Do NOT run these during the v4 build (purity)

They read v3's B2 / B3 conversations, tiny-answer logs or run folders, which no v4 agent may open:

| file | what it reads |
|---|---|
| `tqa_build.py`, `tqa_dump.py`, `tqa_k2lines.py`, `tqa_tab.py` | B2 + B3 lines and tiny answers (the tiny-question audit) |
| `blocksum.py` | B2 run folder |
| `b3_finish.sh`, `b3_interim.sh` | B3 run folder |
| `b3/tools/identity_check.sh` | B1 / B2 dry-run folders of the v3 sandbox |
| `b2_finish.sh`, `b2_auto.sh` | B2 run folder |
| `verify.py`, `verify2.py` | B2 tiny answers |
| `b2_dry/compare.py` | B2 metrics / recompute files |

The rest (`merge_overlays.py`, `run_v3_tests_parallel.sh`, `run_tests.sh`, `run_runner_tests.py`, `hash_table.py`,
`ov_sha.py`, `scripts/tiny_fail_probe.py`, `older_7c3c1535/dry_all.sh`) are kept as examples only. They hard-code
v3 run ids, pids and paths: run the v4 versions instead (`scripts/v4_merge_overlays.py`,
`scripts/v4_run_tests_parallel.sh`, `scripts/v4_dry_all.sh`, `scripts/v4_identity_check.sh`).
