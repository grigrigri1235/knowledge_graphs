#!/usr/bin/env bash
# Tracker v4: the after-run chain of one live step (docs/planning/tracker_v4/overview.md section 10, P5). $0: no LLM
# call, no network. Run it in the background from the main chat right after the step's shard processes start:
#
#   cd /home/azureuser/code_projects/predicate_correctness
#   nohup bash scoring/v4_after_run.sh --step B2v4 --pids "1234 1235 1236" \
#       --run-dir output/eval_v4/B2v4/<run_id> > output/logs/v4_after_run_B2v4_launch.txt 2>&1 &
#
# 1. Waits until every given PID has ended. Explicit PIDs only (never pgrep -f: it matches its own shell). A PID
#    counts as ended when /proc/<pid> is gone or its command line differs from the one seen at start (PID reuse).
# 2. Freeze check (if output/eval_v4/v4_freeze.json exists): scoring/v4_freeze.py --check
#    -> output/logs/v4_<step>_<tag>_freeze_check.txt; a failed check is a progress line (the chain goes on).
#    Then metrics: scoring/v4_online_metrics.py run [--baseline <run.json baseline>] -> output/logs/v4_<step>_<tag>_metrics.{json,md,log}.
# 3. Independent recompute, if tests/audit_v4_online_recompute.py exists (another agent writes it):
#      python -B tests/audit_v4_online_recompute.py --run-dir <dir> [...] --out <json>
#    -> output/logs/v4_<step>_<tag>_recompute.{json,log}; then the point estimates are compared
#    (v4_online_metrics.py compare-points) -> output/logs/v4_<step>_<tag>_points.{json,log}.
# 4. Diagnosis, if scoring/v4_diagnosis.py exists:
#      python -B -m scoring.v4_diagnosis --run-dir <dir> [...] --metrics <metrics json> --out <json>
#    -> output/logs/v4_<step>_<tag>_diagnosis.{json,log}.
# 5. Appends short lines to docs/planning/tracker_v4/progress.md (--progress to change it, e.g. in tests). That file
#    is outside predicate_correctness/ on purpose (the user's planning docs live there). APPEND ONLY: the chain only
#    ever adds lines with `>>` (the progress() function below); it never creates it anew, truncates, rewrites or
#    deletes it. Do not add any other write to it.
# Every step's output goes to files under output/ (--out-dir, default output/logs, must be under output/). A failed
# step is logged and the chain goes on. The chain's own log: <out-dir>/v4_after_run_<step>_<tag>.txt.
# Options: --step (B1v4|B2v4|B3v4|Hv4; build_brief.md names; DEV20v4 is dropped, user decision), --pids "<pid> ...", --run-dir (repeat), --tag (default: the first run
# folder's name), --out-dir, --progress, --poll <seconds> (default 30).
set -u

PC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(dirname "$PC_DIR")"
PY=/home/azureuser/miniconda3/bin/python3
export PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0

STEP="" PIDS="" TAG="" OUT_DIR="$PC_DIR/output/logs" PROGRESS="$REPO/docs/planning/tracker_v4/progress.md" POLL=30
RUN_DIRS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --step) STEP="$2"; shift 2 ;;
    --pids) PIDS="$2"; shift 2 ;;
    --run-dir) RUN_DIRS+=("$2"); shift 2 ;;
    --tag) TAG="$2"; shift 2 ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --progress) PROGRESS="$2"; shift 2 ;;
    --poll) POLL="$2"; shift 2 ;;
    *) echo "v4_after_run: unknown option $1" >&2; exit 2 ;;
  esac
done

case "$STEP" in
  B1v4|B2v4|B3v4|Hv4) ;;
  DEV20v4) echo "v4_after_run: DEV20v4 is dropped (user decision): no after-run chain for it" >&2; exit 2 ;;
  *) echo "v4_after_run: --step must be B1v4, B2v4, B3v4 or Hv4" >&2; exit 2 ;;
esac
[ ${#RUN_DIRS[@]} -gt 0 ] || { echo "v4_after_run: at least one --run-dir" >&2; exit 2; }
for p in $PIDS; do
  case "$p" in ''|*[!0-9]*) echo "v4_after_run: bad pid '$p' (numbers only)" >&2; exit 2 ;; esac
done
case "$POLL" in ''|*[!0-9]*) echo "v4_after_run: --poll must be a whole number of seconds" >&2; exit 2 ;; esac
mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"
case "$OUT_DIR/" in "$PC_DIR/output/"*) ;; *) echo "v4_after_run: --out-dir must be under $PC_DIR/output" >&2; exit 2 ;; esac
ABS_RUNS=()
for d in "${RUN_DIRS[@]}"; do
  case "$d" in /*) ABS_RUNS+=("$d") ;; *) ABS_RUNS+=("$PC_DIR/$d") ;; esac
done
[ -n "$TAG" ] || TAG="$(basename "${ABS_RUNS[0]}")"
case "$TAG" in *[!A-Za-z0-9_.-]*) echo "v4_after_run: --tag may hold letters, digits, _ . - only" >&2; exit 2 ;; esac

BASE="$OUT_DIR/v4_${STEP}_${TAG}"
LOG="$OUT_DIR/v4_after_run_${STEP}_${TAG}.txt"
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
say() { echo "$(now) $*" >> "$LOG"; }
progress() { echo "- $(now): $*" >> "$PROGRESS"; }   # append only (>>): the one write to the progress file
RUN_ARGS=()
for d in "${ABS_RUNS[@]}"; do RUN_ARGS+=(--run-dir "$d"); done
# P10 arm plan (user decision): B2v4 / B3v4 take their old arms from v3's saved run that the live run.json names
# ("baseline".run_dir). The chain passes it on (--baseline) to the metrics, the recompute and the diagnosis; each
# refuses it unless it is the run.json one. B1v4 / Hv4 have no baseline.
BASELINE="$("$PY" -B -c 'import json, os, sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    d = {}
b = d.get("baseline") or (d.get("ident") or {}).get("baseline") or {}
r = b.get("run_dir") or ""
print(r if (not r or os.path.isabs(r)) else os.path.join(sys.argv[2], r))' "${ABS_RUNS[0]}/run.json" "$PC_DIR" 2>/dev/null)"
BASE_ARGS=()
[ -n "$BASELINE" ] && BASE_ARGS=(--baseline "$BASELINE")

say "start: step $STEP, tag $TAG, pids [$PIDS], run dirs ${ABS_RUNS[*]}, baseline ${BASELINE:-(none)}"
case "$STEP" in
  B2v4|B3v4) [ -n "$BASELINE" ] || { say "no baseline in run.json: metrics, recompute and diagnosis will refuse";
                                     progress "after-run $STEP ($TAG): no baseline in run.json (the old arms are missing)"; } ;;
esac

# 1. wait for the given PIDs (explicit; the command line seen now guards against PID reuse)
declare -A CMD0
for p in $PIDS; do
  if [ -r "/proc/$p/cmdline" ]; then CMD0[$p]="$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null)"; else CMD0[$p]=""; fi
  say "pid $p: ${CMD0[$p]:-(already ended)}"
done
alive() {
  local p="$1"
  [ -n "${CMD0[$p]}" ] || return 1
  [ -r "/proc/$p/cmdline" ] || return 1
  [ "$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null)" = "${CMD0[$p]}" ]
}
while :; do
  left=""
  for p in $PIDS; do alive "$p" && left="$left $p"; done
  [ -z "$left" ] && break
  sleep "$POLL"
done
say "all pids ended"

cd "$PC_DIR" || exit 1

# 2. freeze check, then metrics
MANIFEST="$PC_DIR/output/eval_v4/v4_freeze.json"
if [ -f "$MANIFEST" ]; then
  if "$PY" -B -m scoring.v4_freeze --check --manifest "$MANIFEST" > "${BASE}_freeze_check.txt" 2>&1; then
    say "freeze check ok"; progress "after-run $STEP ($TAG): freeze check ok"
  else
    say "freeze check FAILED (see ${BASE}_freeze_check.txt)"
    progress "after-run $STEP ($TAG): freeze check FAILED (\`${BASE#$REPO/}_freeze_check.txt\`)"
  fi
else
  say "freeze manifest absent ($MANIFEST)"; progress "after-run $STEP ($TAG): freeze manifest absent"
fi
METRICS_OK=0
if "$PY" -B -m scoring.v4_online_metrics run "${RUN_ARGS[@]}" "${BASE_ARGS[@]}" --out "${BASE}_metrics.json" \
     --out-md "${BASE}_metrics.md" > "${BASE}_metrics.log" 2>&1; then
  METRICS_OK=1
  SUMMARY="$(grep -m1 '^\[v4-online-metrics\] SUMMARY: ' "${BASE}_metrics.log" | sed 's/^\[v4-online-metrics\] SUMMARY: //')"
  say "metrics ok: $SUMMARY"
  progress "after-run $STEP ($TAG): metrics ok: ${SUMMARY} (\`${BASE#$REPO/}_metrics.md\`)"
else
  say "metrics FAILED (see ${BASE}_metrics.log)"
  progress "after-run $STEP ($TAG): metrics FAILED (\`${BASE#$REPO/}_metrics.log\`)"
fi

# 3. independent recompute + point comparison
RECOMP="$PC_DIR/tests/audit_v4_online_recompute.py"
if [ -f "$RECOMP" ]; then
  if "$PY" -B "$RECOMP" "${RUN_ARGS[@]}" "${BASE_ARGS[@]}" --out "${BASE}_recompute.json" > "${BASE}_recompute.log" 2>&1; then
    if [ "$METRICS_OK" = 1 ]; then
      if "$PY" -B -m scoring.v4_online_metrics compare-points --metrics "${BASE}_metrics.json" \
           --recompute "${BASE}_recompute.json" --out "${BASE}_points.json" > "${BASE}_points.log" 2>&1; then
        say "recompute: same points"; progress "after-run $STEP ($TAG): recompute: same point estimates"
      else
        say "recompute: points DIFFER or none shared (see ${BASE}_points.json)"
        progress "after-run $STEP ($TAG): recompute: point estimates DIFFER or none shared (\`${BASE#$REPO/}_points.json\`)"
      fi
    else
      say "recompute ran; no comparison (metrics failed)"; progress "after-run $STEP ($TAG): recompute ran, not compared (metrics failed)"
    fi
  else
    say "recompute FAILED (see ${BASE}_recompute.log)"; progress "after-run $STEP ($TAG): recompute FAILED"
  fi
else
  say "recompute: absent ($RECOMP)"; progress "after-run $STEP ($TAG): recompute script absent"
fi

# 4. diagnosis
if [ -f "$PC_DIR/scoring/v4_diagnosis.py" ]; then
  if "$PY" -B -m scoring.v4_diagnosis "${RUN_ARGS[@]}" "${BASE_ARGS[@]}" --metrics "${BASE}_metrics.json" \
       --out "${BASE}_diagnosis.json" > "${BASE}_diagnosis.log" 2>&1; then
    say "diagnosis done"; progress "after-run $STEP ($TAG): diagnosis done (\`${BASE#$REPO/}_diagnosis.json\`)"
  else
    say "diagnosis FAILED (see ${BASE}_diagnosis.log)"; progress "after-run $STEP ($TAG): diagnosis FAILED"
  fi
else
  say "diagnosis: absent"; progress "after-run $STEP ($TAG): diagnosis script absent"
fi
say "done"
exit 0
