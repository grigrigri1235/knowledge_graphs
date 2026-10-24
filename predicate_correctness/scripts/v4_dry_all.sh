#!/bin/bash
# Tracker v4: 0-call dry runs of every shard of the v4 steps (guard/run_online_v4.py run ... --dry-run with an out
# root under output/eval_v4/dryrun/: network blocked, no LLM client, guards built, nothing written).
# Usage (from anywhere):  scripts/v4_dry_all.sh [STEP:N ...]
#   default: B1v4:1 B2v4:4 B3v4:1 Hv4:1   (N = shard count; DEV20v4 is dropped: a bad spec)
# Every shard i of N of every step gets one dry run, 4 processes at a time, each with 8 workers.
# A shard passes when: exit 0; "DRY RUN DONE"; the line "LLM calls in this dry run: agent 0, user 0, judge 0, tiny 0;
# network attempts blocked 0; refused writes 0"; "shards_cover_every_unit_once": true. A step passes when its shards
# pass and their units add up to the planned size (P10 arm plan: B1v4 4, B2v4 594, B3v4 188, Hv4 594).
# Output: output/logs/v4_dry_<UTC>_<step>_s<i>of<N>.txt per shard, output/logs/v4_dry_<UTC>_summary.txt.
# Prints only the summary path. Exit 1 if anything fails. Never a real run: --dry-run is always given and the out
# root is always under output/eval_v4/dryrun/.
set -u
PC=/home/azureuser/code_projects/predicate_correctness
cd "$PC" || exit 1
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
PRE=output/logs/v4_dry_${STAMP}
OUTROOT=output/eval_v4/dryrun/dry_all_${STAMP}
SUM=${PRE}_summary.txt
mkdir -p output/logs "$OUTROOT"
if [ "$#" -gt 0 ]; then SPECS=("$@"); else SPECS=(B1v4:1 B2v4:4 B3v4:1 Hv4:1); fi
declare -A WANT=([B1v4]=4 [B2v4]=594 [B3v4]=188 [Hv4]=594)
JOBS=()
for spec in "${SPECS[@]}"; do
  step=${spec%%:*}; n=${spec#*:}
  [ "$step" = "$spec" ] && n=1
  if [ -z "${WANT[$step]:-}" ] || ! [[ "$n" =~ ^[1-6]$ ]]; then
    echo "bad spec $spec (STEP:N, STEP in ${!WANT[*]}, N 1-6)" > "$SUM"; echo FAIL >> "$SUM"; echo "$SUM"; exit 1
  fi
  for ((i = 0; i < n; i++)); do JOBS+=("$step $i $n"); done
done
export PRE OUTROOT STAMP
printf '%s\n' "${JOBS[@]}" | xargs -P 4 -L 1 bash -c '
  step=$0; i=$1; n=$2
  log="${PRE}_${step}_s${i}of${n}.txt"
  PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 timeout 1800 "$HOME/venvs/tau-bench/bin/python" -B -W ignore \
    -m guard.run_online_v4 run --step "$step" --run-id "${step}_${STAMP}_00000000" --shard "$i/$n" --workers 8 \
    --out-root "$OUTROOT" --dry-run --approval "dry run, no money" > "$log" 2>&1
  echo "rc $?" >> "$log"'
FAIL=0
{
  for spec in "${SPECS[@]}"; do
    step=${spec%%:*}; n=${spec#*:}; [ "$step" = "$spec" ] && n=1
    total=0
    for ((i = 0; i < n; i++)); do
      log="${PRE}_${step}_s${i}of${n}.txt"
      ok=1
      grep -q "^rc 0$" "$log" || ok=0
      grep -q "DRY RUN DONE" "$log" || ok=0
      grep -q "LLM calls in this dry run: agent 0, user 0, judge 0, tiny 0; network attempts blocked 0; refused writes 0" "$log" || ok=0
      grep -q '"shards_cover_every_unit_once": true' "$log" || ok=0
      units=$(grep -m1 '"units_in_shard":' "$log" | grep -o '[0-9]\+' | head -1)
      units=${units:-0}
      total=$((total + units))
      [ $ok = 1 ] && echo "$step shard $i/$n: ok, $units units" || { echo "$step shard $i/$n: FAIL ($log)"; FAIL=1; }
    done
    if [ "$total" -eq "${WANT[$step]}" ]; then echo "$step: units $total = ${WANT[$step]}"
    else echo "$step: units $total != pre-registered ${WANT[$step]}: FAIL"; FAIL=1; fi
  done
  [ $FAIL = 0 ] && echo PASS || echo FAIL
} > "$SUM"
rmdir "$OUTROOT" 2>/dev/null
echo "$SUM"
[ $FAIL = 0 ]
