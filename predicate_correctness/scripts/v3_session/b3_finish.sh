#!/bin/bash
cd /home/azureuser/code_projects/predicate_correctness || exit 1
RUN_ID=B3_20261023T190740Z_9bf882c0; RUN=output/eval_v3/B3/$RUN_ID
while (kill -0 1011287 || kill -0 1011288 || kill -0 1011290 || kill -0 1011291) 2>/dev/null; do
  N=$(cat $RUN/*/episodes_shard*of4.jsonl 2>/dev/null | wc -l)
  M=$(date -u +%M); if [ $((10#$M % 10)) -eq 0 ] && [ "$LAST" != "$M" ]; then LAST=$M; echo "- auto: $(date -u +%H:%M) UTC B3: $N of 320 lines" >> output/eval_v3/progress.md; fi
  sleep 15
done
echo "B3 processes ended $(date -u +%H:%M:%S); lines $(cat $RUN/*/episodes_shard*of4.jsonl | wc -l)"
for i in 0 1 2 3; do tail -1 output/logs/v3_B3_${RUN_ID}_s$i.log; done
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 /home/azureuser/miniconda3/bin/python3 -B -m scoring.v3_online_metrics run --run-dir $RUN --out output/logs/v3_B3_${RUN_ID}_metrics.json > output/logs/v3_B3_${RUN_ID}_metrics.log 2>&1
echo "metrics exit $?"; tail -5 output/logs/v3_B3_${RUN_ID}_metrics.log
