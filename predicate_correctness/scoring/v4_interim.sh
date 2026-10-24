#!/bin/bash
# Tracker v4: the halfway watcher of one step's live run (code_change_map.md section 1.5 `v4_interim.sh`, the generic
# version of scripts/v3_session/b3_interim.sh; preregistration_v4.md section 11). $0: no LLM call, no network.
# Every V4_INTERIM_EVERY seconds (300) it runs
#     python -B -m scoring.v4_online_interim --write-stop --run-dir <run_dir>
# (the halfway harm check and the state / cost / error stops; that script writes <run_dir>/STOP when a stop fires and
# decides by itself when the halfway mark is reached), and it ends when
#   - the run folder has a STOP file (written by the check or by anyone else): exit 0;
#   - no runner pid of the pids file is alive: exit 0. Alive = `kill -0 <pid>` works AND /proc/<pid>/cmdline has
#     "run_online_v4" (a reused pid or a zombie does not count). Never pgrep -f;
#   - the check failed FAIL_MAX (3) times in a row: it first writes <run_dir>/STOP (one JSON line with the reason,
#     never over an existing STOP; audit P9 #1c: no new group starts while nobody checks), then exit 4 (the main chat
#     must look);
#   - no pids file after V4_INTERIM_PID_WAIT seconds: exit 3; another watcher holds this run's lock: exit 5.
# It never kills or signals a runner, and it writes nothing but its logs and that one STOP file (the other STOP files
# are the check's). A real B2v4 / B3v4 start is refused while this watcher is not live (it holds the watch.lock), so
# the main chat starts it BEFORE the shards (it waits for pids.txt).
# Usage (from anywhere; the runner's start line prints the exact command, also in <run_dir>/watcher_command.txt):
#   bash scoring/v4_interim.sh <run_dir> [<pids_file>]        (default pids file: <run_dir>/pids.txt)
# Logs (nothing to the terminal), in output/logs/:
#   v4_<step>_<run_id>_watch.log          one line per event and per check (UTC time, alive pids, verdict, rc)
#   v4_<step>_<run_id>_interim.log        every check's full output, a header per check (appended)
#   v4_<step>_<run_id>_interim_last.txt   the last check's output; v4_<step>_<run_id>_watch.lock (one watcher)
# Env (for tests): V4_INTERIM_EVERY (seconds, default 300), V4_INTERIM_CMD (the check command instead of the python
#   module; the watcher appends "--write-stop --run-dir <run_dir>"), V4_INTERIM_PY (default miniconda's python3),
#   V4_INTERIM_CMD_MARK (the cmdline mark of a live runner, default run_online_v4; empty: kill -0 only): these four
#   are obeyed ONLY for a run folder under output/eval_v4/dryrun/ (audit P9 #1b); for a real run they are ignored
#   (logged) and the defaults hold. V4_INTERIM_LOGS (log folder, default output/logs), V4_INTERIM_PID_WAIT (seconds,
#   default 900) always.
# Refused (exit 2): a run folder not under output/eval_v4/ (never output/eval_v3/), a folder name that is not
#   <step>_<UTC>_<uuid8> of B1v4 / B2v4 / B3v4 / Hv4 inside <step>/ (DEV20v4 is dropped).
set -u
PC=/home/azureuser/code_projects/predicate_correctness
cd "$PC" || exit 1
RUN_ARG=${1:-}; PIDS=${2:-}
LOGS=${V4_INTERIM_LOGS:-$PC/output/logs}
PID_WAIT=${V4_INTERIM_PID_WAIT:-900}
FAIL_MAX=3
NAP=10                                     # seconds between liveness / STOP looks while waiting for the next check
DEF_EVERY=300; DEF_PY=/home/azureuser/miniconda3/bin/python3; DEF_MARK=run_online_v4

refuse() { echo "v4_interim: refused: $*" >&2; exit 2; }
[ -n "$RUN_ARG" ] || refuse "usage: bash scoring/v4_interim.sh <run_dir> [<pids_file>]"
[[ "$PID_WAIT" =~ ^[0-9]+$ ]] || refuse "V4_INTERIM_PID_WAIT=$PID_WAIT is not a whole number of seconds"
RUN=$(realpath -m -- "$RUN_ARG")
case "$RUN/" in
  "$PC/output/eval_v4/"?*) ;;
  *) refuse "run folder $RUN is not under $PC/output/eval_v4/" ;;
esac
SANDBOX=0
case "$RUN/" in "$PC/output/eval_v4/dryrun/"?*) SANDBOX=1 ;; esac
IGNORED=""
if [ "$SANDBOX" = 1 ]; then               # test overrides: a dry-run folder only (audit P9 #1b)
  EVERY=${V4_INTERIM_EVERY:-$DEF_EVERY}
  PY=${V4_INTERIM_PY:-$DEF_PY}
  MARK=${V4_INTERIM_CMD_MARK-$DEF_MARK}
  OVR_CMD=${V4_INTERIM_CMD:-}
else                                      # a real run: the defaults, whatever the environment says
  EVERY=$DEF_EVERY; PY=$DEF_PY; MARK=$DEF_MARK; OVR_CMD=""
  for v in V4_INTERIM_EVERY V4_INTERIM_CMD V4_INTERIM_PY V4_INTERIM_CMD_MARK; do
    [ -n "${!v+x}" ] && IGNORED="$IGNORED $v"
  done
fi
[[ "$EVERY" =~ ^[0-9]+$ ]] || refuse "V4_INTERIM_EVERY=$EVERY is not a whole number of seconds"
RUN_ID=$(basename -- "$RUN"); STEP=$(basename -- "$(dirname -- "$RUN")")
if ! [[ "$RUN_ID" =~ ^(B1v4|B2v4|B3v4|Hv4)_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{8}$ ]] || [ "${BASH_REMATCH[1]}" != "$STEP" ]; then
  refuse "$STEP/$RUN_ID is not a v4 run folder <step>/<step>_<UTC>_<uuid8> of B1v4, B2v4, B3v4 or Hv4 (DEV20v4 is dropped)"
fi
[ -n "$PIDS" ] || PIDS=$RUN/pids.txt
if [ -n "$OVR_CMD" ]; then read -r -a CMD <<< "$OVR_CMD"; else CMD=("$PY" -B -m scoring.v4_online_interim); fi
mkdir -p "$LOGS" || exit 1
BASE=$LOGS/v4_${STEP}_${RUN_ID}
WATCH=${BASE}_watch.log; ILOG=${BASE}_interim.log; LAST=${BASE}_interim_last.txt

say() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" >> "$WATCH"; }

exec 9>> "${BASE}_watch.lock"
if ! flock -n 9; then say "another watcher holds ${BASE}_watch.lock: exit 5"; exit 5; fi

alive_pids() {                     # the listed pids that are live runner processes (first field of each line)
  local pid rest out=""
  [ -r "$PIDS" ] || { echo ""; return; }
  while read -r pid rest; do
    [[ "$pid" =~ ^[0-9]+$ ]] || continue
    kill -0 "$pid" 2>/dev/null || continue
    if [ -n "$MARK" ]; then
      tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -qF -- "$MARK" || continue
    fi
    case " $out " in *" $pid "*) ;; *) out="$out $pid" ;; esac
  done < "$PIDS"
  echo "${out# }"
}

stop_present() { [ -e "$RUN/STOP" ]; }

say "start: run $RUN; pids file $PIDS; a check every ${EVERY}s: ${CMD[*]} --write-stop --run-dir $RUN"
[ -n "$IGNORED" ] && say "a real run folder: test overrides ignored:$IGNORED (the defaults hold)"

write_fail_stop() {                # audit P9 #1c: the check keeps failing -> STOP (with the reason), never overwritten
  local line
  line="{\"stop\": [\"watcher_check_failed\"], \"time\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"by\": \"scoring/v4_interim.sh\", \"reason\": \"the halfway / stop check failed $FAIL_MAX times in a row (last rc $1): no new group starts until the main chat looks; logs $ILOG\"}"
  if ( set -o noclobber; printf '%s\n' "$line" > "$RUN/STOP" ) 2>/dev/null; then
    say "wrote $RUN/STOP (the check failed $FAIL_MAX times in a row)"
  elif [ -e "$RUN/STOP" ]; then
    say "STOP already present: not changed"
  else
    say "could not write $RUN/STOP"
  fi
}
waited=0
while [ ! -s "$PIDS" ]; do
  if [ "$waited" -ge "$PID_WAIT" ]; then say "no pids file $PIDS after ${PID_WAIT}s: exit 3"; exit 3; fi
  sleep 5; waited=$((waited + 5))
done

n=0; fails=0
while true; do
  if stop_present; then say "STOP file present ($(head -c 300 "$RUN/STOP" | tr '\n' ' ')): exit"; exit 0; fi
  alive=$(alive_pids)
  if [ -z "$alive" ]; then say "no runner pid of $PIDS is alive: exit (after $n checks)"; exit 0; fi
  n=$((n + 1))
  env PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 "${CMD[@]}" --write-stop --run-dir "$RUN" > "$LAST" 2>&1
  rc=$?
  { echo "=== check $n $(date -u +%Y-%m-%dT%H:%M:%SZ) alive: $alive rc $rc"; cat "$LAST"; } >> "$ILOG"
  verdict=$(grep '^\[v4-interim\]' "$LAST" | tail -1)
  if [ "$rc" -ne 0 ]; then
    fails=$((fails + 1))
    say "check $n FAILED rc $rc ($fails in a row; $(tail -1 "$LAST" | head -c 300))"
    if [ "$fails" -ge "$FAIL_MAX" ]; then
      write_fail_stop "$rc"
      say "the check failed $FAIL_MAX times in a row: exit 4"; exit 4
    fi
  else
    fails=0
    say "check $n: alive $alive; rc 0; ${verdict:-no verdict line}"
  fi
  if stop_present; then say "STOP file present after check $n ($(head -c 300 "$RUN/STOP" | tr '\n' ' ')): exit"; exit 0; fi
  slept=0
  while [ "$slept" -lt "$EVERY" ]; do       # look at STOP and the pids between checks, so the end is seen soon
    nap=$((EVERY - slept)); [ "$nap" -gt "$NAP" ] && nap=$NAP
    sleep "$nap"; slept=$((slept + nap))
    stop_present && break
    [ -z "$(alive_pids)" ] && break
  done
done
