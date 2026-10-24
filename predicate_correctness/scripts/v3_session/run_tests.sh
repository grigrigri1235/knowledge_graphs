#!/bin/bash
cd /home/azureuser/code_projects/predicate_correctness
export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1
pids=()
for f in tests/test_v3_*.py tests/test_no_gold_import.py; do
  m=$(basename $f .py)
  ( timeout 3000 ~/venvs/tau-bench/bin/python -B -m unittest tests.$m > output/logs/v3_k2fix_t_$m.log 2>&1; echo "exit $?" >> output/logs/v3_k2fix_t_$m.log ) &
done
wait
for f in output/logs/v3_k2fix_t_test_*.log; do echo "$f: $(grep -E '^Ran ' $f) $(tail -1 $f) $(grep -E '^(OK|FAILED)' $f)"; done > output/logs/v3_k2fix_tests_summary.log
