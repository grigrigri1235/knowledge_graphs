#!/bin/bash
# Tracker v4 identity check ($0, 0 real LLM calls). From scripts/v3_session/b3/tools/identity_check.sh.
# Question: do none / direct / tgr_frozen give the same episode records and judge-cache records under the v4 runner
# (guard/run_online_v4.py, step B1v4) as under the v3 runner (guard/run_online_v3.py, step B1)?
# How: a SANDBOX COPY of predicate_correctness (never the real tree; the copy has no gold folder, no v3
# conversations: of output/eval_v3/ only the task files, rule tables and the eval v2 manifest), then
# scripts/v4_identity_driver.py runs each runner in its own process inside the copy (network blocked, sandbox write
# guard, fake Azure client, scripted user: no LLM user env is built), then compares.
# Usage (from anywhere):  scripts/v4_identity_check.sh        (KEEP_TREE=1 keeps the copy for reading)
# Output: output/eval_v4/dryrun/identity_<UTC>/{v3,v4}/ (run folders, driver_result.json), summary.json,
#         driver logs; one line in output/logs/v4_identity_<UTC>.txt. Exit 1 if anything differs.
set -u
PC=/home/azureuser/code_projects/predicate_correctness
cd "$PC" || exit 1
PY="env PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 LITELLM_LOCAL_MODEL_COST_MAP=True $HOME/venvs/tau-bench/bin/python -B -W ignore"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT=$PC/output/eval_v4/dryrun/identity_$STAMP
TREE=$OUT/tree/predicate_correctness
LOG=$PC/output/logs/v4_identity_$STAMP.txt
mkdir -p "$TREE" output/logs
G=gold   # the partner's gold folder name, kept out of the copy (spelled apart: tests/test_v4_no_gold_import.py scans the text)
(
  echo "identity check $STAMP: copy to $TREE"
  rsync -a \
    --exclude='__pycache__/' --exclude="/from_shieldagent/$G/" --exclude='/scripts/v3_session/' \
    --exclude='/output/_llmcache/' --exclude='/output/logs/' --exclude='/output/_tmp*' \
    --exclude='/output/eval_v4/dryrun/' --exclude='/output/eval_v4/cases/' --exclude='/output/eval_v4/dev/' \
    --include='/output/eval_v3/' \
    --include='/output/eval_v3/online_tasks.json' --include='/output/eval_v3/b3_tasks.json' \
    --include='/output/eval_v3/rule_table_retail.json' --include='/output/eval_v3/rule_table_airline.json' \
    --include='/output/eval_v3/manifest_eval_v2_data.sha256' \
    --exclude='/output/eval_v3/*' \
    "$PC/" "$TREE/"
  echo "rsync exit $?"
  [ -e "$TREE/from_shieldagent/$G" ] && { echo "REFUSED: gold in the copy"; exit 1; }
  mkdir -p "$TREE/output/eval_v3/dryrun/identity" "$TREE/output/eval_v4/dryrun/identity"
  ( cd "$TREE" && $PY scripts/v4_identity_driver.py run v3 "$TREE" "$TREE/output/eval_v3/dryrun/identity" ) \
      > "$OUT/driver_v3.txt" 2>&1
  echo "driver v3 exit $?"
  ( cd "$TREE" && $PY scripts/v4_identity_driver.py run v4 "$TREE" "$TREE/output/eval_v4/dryrun/identity" ) \
      > "$OUT/driver_v4.txt" 2>&1
  echo "driver v4 exit $?"
  cp -a "$TREE/output/eval_v3/dryrun/identity" "$OUT/v3"
  cp -a "$TREE/output/eval_v4/dryrun/identity" "$OUT/v4"
  /home/azureuser/miniconda3/bin/python3 -B "$PC/scripts/v4_identity_driver.py" compare "$OUT/v3" "$OUT/v4" \
      "$OUT/summary.json"
  RC=$?
  echo "compare exit $RC"
  [ "${KEEP_TREE:-0}" = "1" ] || rm -rf "$OUT/tree"
  exit $RC
) > "$LOG" 2>&1
RC=$?
echo "$LOG"
exit $RC
