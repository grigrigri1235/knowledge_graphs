#!/bin/bash
# Run every v3 test module in its own process, 8 at a time. Output: one log per module + a summary.
cd /home/azureuser/code_projects/predicate_correctness
OUT=output/logs/v3_ptests_$(date -u +%H%M%S)
mkdir -p "$OUT"
ls tests/test_v3_*.py tests/test_no_gold_import.py | sed 's#/#.#; s#\.py$##' | \
  xargs -P 8 -I{} sh -c 'PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m unittest {} > '"$OUT"'/{}.log 2>&1; echo "{} exit $?" >> '"$OUT"'/summary.txt'
grep -h "^Ran \|^OK\|^FAILED" "$OUT"/*.log | sort | uniq -c > "$OUT"/totals.txt
echo "$OUT"
