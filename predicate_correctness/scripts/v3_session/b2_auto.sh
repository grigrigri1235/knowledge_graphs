#!/bin/bash
# Every 10 min: one "auto:" line in progress.md with B2's lines done, errors, spend. Ends when no B2 process is left.
cd /home/azureuser/code_projects/predicate_correctness
D=output/eval_v3/B2/B2_20261023T155537Z_c842d895
while ps -eo cmd | grep -q '[r]un_online_v3 run --step B2 --run-id B2_20261023T155537Z_c842d895'; do
  sleep 600
  N=$(cat $D/*/episodes_shard*of4.jsonl 2>/dev/null | wc -l)
  E=$(cat $D/*/episodes_shard*of4.jsonl 2>/dev/null | grep -c '"error": "[^"]' )
  S=$(PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -c "from guard import soft_stop_v3 as S; print(round(S.v3_spend()['total_usd'],3))" 2>/dev/null)
  echo "- auto: $(date -u +%H:%M) UTC B2: $N of 1,485 lines, error lines $E, v3 spend \$$S" >> output/eval_v3/progress.md
done
echo "- auto: $(date -u +%H:%M) UTC B2: no B2 process left" >> output/eval_v3/progress.md
