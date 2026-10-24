#!/bin/bash
# Tracker v4: run every test module in its own process, 8 at a time (from scripts/v3_session/run_v3_tests_parallel.sh).
# Usage (from anywhere):  scripts/v4_run_tests_parallel.sh [test file globs, relative to predicate_correctness/]
#   default globs: tests/test_v4_*.py tests/test_v3_*.py (tests/test_v4_no_gold_import.py is inside the first)
# Output (nothing else is written):
#   output/logs/v4_tests_<UTC>_<module>.txt   one log per module (unittest -v output)
#   output/logs/v4_tests_<UTC>_summary.txt    "<module> exit <code> <seconds>s", one line per module, sorted
#   output/logs/v4_tests_<UTC>_totals.txt     counts of the "Ran / OK / FAILED" lines, then PASS or FAIL
# Each module: runner Python, -B, PYTHONDONTWRITEBYTECODE=1, PYTHONHASHSEED=0, timeout 3000 s (exit 124 = timeout).
# Exit 1 if any module fails or no module matched. Prints only the summary path. No LLM call, no network.
set -u
PC=/home/azureuser/code_projects/predicate_correctness
cd "$PC" || exit 1
PY=${V4_TEST_PY:-$HOME/venvs/tau-bench/bin/python}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
PRE=output/logs/v4_tests_${STAMP}
mkdir -p output/logs
if [ "$#" -gt 0 ]; then GLOBS=("$@"); else GLOBS=(tests/test_v4_*.py tests/test_v3_*.py); fi
MODS=$(for g in "${GLOBS[@]}"; do ls $g 2>/dev/null; done | sort -u | sed 's#/#.#g; s#\.py$##')
if [ -z "$MODS" ]; then
  echo "no test module matched: ${GLOBS[*]}" > "${PRE}_summary.txt"; echo "FAIL" > "${PRE}_totals.txt"
  echo "${PRE}_summary.txt"; exit 1
fi
export PY PRE
echo "$MODS" | xargs -P 8 -I{} bash -c '
  t0=$(date +%s)
  PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 timeout 3000 "$PY" -B -m unittest -v {} > "${PRE}_{}.txt" 2>&1
  rc=$?
  echo "{} exit $rc $(( $(date +%s) - t0 ))s" >> "${PRE}_summary.txt"'
sort -o "${PRE}_summary.txt" "${PRE}_summary.txt"
N=$(echo "$MODS" | wc -l)
NS=$(wc -l < "${PRE}_summary.txt")
NBAD=$(grep -vc " exit 0 " "${PRE}_summary.txt")
{
  grep -h "^Ran \|^OK\|^FAILED" $(echo "$MODS" | sed "s#^#${PRE}_#; s#\$#.txt#") 2>/dev/null | sort | uniq -c
  echo "modules $N, finished $NS, not exit 0: $NBAD"
  if [ "$NBAD" -eq 0 ] && [ "$NS" -eq "$N" ]; then echo PASS; else echo FAIL; fi
} > "${PRE}_totals.txt"
echo "${PRE}_summary.txt"
[ "$NBAD" -eq 0 ] && [ "$NS" -eq "$N" ]
