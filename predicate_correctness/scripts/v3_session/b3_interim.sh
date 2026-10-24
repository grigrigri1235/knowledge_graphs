#!/bin/bash
cd /home/azureuser/code_projects/predicate_correctness || exit 1
RUN_ID=B3_20261023T190740Z_9bf882c0; RUN=output/eval_v3/B3/$RUN_ID
until [ "$(cat $RUN/*/episodes_shard*of4.jsonl 2>/dev/null | wc -l)" -ge 170 ]; do
  if ! (kill -0 1011287 || kill -0 1011288 || kill -0 1011290 || kill -0 1011291) 2>/dev/null; then echo "processes ended before 170"; break; fi
  sleep 15
done
echo "lines $(cat $RUN/*/episodes_shard*of4.jsonl | wc -l) at $(date -u +%H:%M:%S)"
PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 /home/azureuser/miniconda3/bin/python3 -B -m scoring.v3_online_interim --run-dir $RUN > output/logs/v3_B3_${RUN_ID}_interim.log 2>&1
echo "interim exit $?"; tail -1 output/logs/v3_B3_${RUN_ID}_interim.log
