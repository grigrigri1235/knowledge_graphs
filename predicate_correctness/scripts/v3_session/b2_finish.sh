#!/bin/bash
# Waits for the 4 B2 processes to exit, then runs the $0 after-B2 steps (metrics, report, independent recompute).
cd /home/azureuser/code_projects/predicate_correctness || exit 1
RUN_ID=B2_20261023T155537Z_c842d895
RUN=output/eval_v3/B2/$RUN_ID
while kill -0 944600 2>/dev/null || kill -0 944601 2>/dev/null || kill -0 944602 2>/dev/null || kill -0 944603 2>/dev/null; do
  sleep 15
done
echo "B2 processes ended $(date -u +%H:%M:%S)"
echo "lines $(cat $RUN/*/episodes_shard*of4.jsonl | wc -l)"
export PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0
PY=/home/azureuser/miniconda3/bin/python3
$PY -B -m scoring.v3_online_metrics run --run-dir $RUN --out output/logs/v3_B2_${RUN_ID}_metrics.json > output/logs/v3_B2_${RUN_ID}_metrics.log 2>&1
echo "metrics exit $?"
$PY -B -m scoring.v3_p14_report --metrics-json output/logs/v3_B2_${RUN_ID}_metrics.json > output/logs/v3_B2_${RUN_ID}_report.log 2>&1
echo "report exit $?"
$PY -B tests/audit_v3_online_recompute.py --run-dir $RUN --out output/eval_v3/B2/recompute_${RUN_ID} > output/logs/v3_recomp_B2_real.txt 2>&1
echo "recompute exit $?"
echo "done $(date -u +%H:%M:%S)"
