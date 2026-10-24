#!/bin/bash
# B1/B2 identity check: the same $0 commands with the ORIGINAL and with the PATCHED runner / metrics / interim in the
# sandbox copy; outputs saved per mode, then compared. Usage: identity_check.sh <orig|patched>
set -u
SP=/tmp/claude-1000/-home-azureuser-code-projects/dbfe7ffd-ee14-4b6f-ab52-d79bdd15e981/scratchpad/b3
S=$SP/sandbox/predicate_correctness
MODE=$1
OUT=$SP/identity/$MODE
rm -rf "$OUT"; mkdir -p "$OUT"
for f in guard/run_online_v3.py scoring/v3_online_metrics.py scoring/v3_online_interim.py; do
  cp -p "$SP/$MODE/$f" "$S/$f"
done
sha256sum "$S/guard/run_online_v3.py" "$S/scoring/v3_online_metrics.py" "$S/scoring/v3_online_interim.py" > "$OUT/sha.txt"
PY="env PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 $HOME/venvs/tau-bench/bin/python -B -W ignore"
MPY="env PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 /home/azureuser/miniconda3/bin/python3 -B"
cd "$S" || exit 1
$PY -m guard.run_online_v3 tasks-file --check > "$OUT/tasks_check.txt" 2>&1
$PY -m guard.run_online_v3 run --step B1 --run-id B1_20261024T000000Z_00000000 --shard 0/1 --workers 5 \
    --approval "identity check, no money" --dry-run > "$OUT/dry_B1.txt" 2>&1
for i in 0 3; do
  $PY -m guard.run_online_v3 run --step B2 --run-id B2_20261024T000000Z_00000000 --shard $i/4 --workers 8 \
      --approval "identity check, no money" --dry-run > "$OUT/dry_B2_s$i.txt" 2>&1
done
$PY -m guard.run_online_v3 run --step B2v --run-id B2v_20261024T000000Z_00000000 --shard 1/4 --workers 8 \
    --b2v-approved --approval "identity check, no money" --dry-run > "$OUT/dry_B2v_s1.txt" 2>&1
B2D=$S/output/eval_v3/dryrun/b2_synth/B2/B2_20261024T000000Z_00000000
B1D=$(ls -d $S/output/eval_v3/dryrun/equality_check_test/v3/B1/B1_* 2>/dev/null | head -1)
$MPY -m scoring.v3_online_metrics run --run-dir "$B2D" --out "$S/output/logs/identity_${MODE}_b2.json" > "$OUT/metrics_b2_stdout.txt" 2>&1
cp "$S/output/logs/identity_${MODE}_b2.json" "$OUT/metrics_b2.json" 2>/dev/null
if [ -n "$B1D" ]; then
  $MPY -m scoring.v3_online_metrics run --run-dir "$B1D" --out "$S/output/logs/identity_${MODE}_b1.json" > "$OUT/metrics_b1_stdout.txt" 2>&1
  cp "$S/output/logs/identity_${MODE}_b1.json" "$OUT/metrics_b1.json" 2>/dev/null
  $MPY -m scoring.v3_online_interim --run-dir "$B1D" > "$OUT/interim_b1.txt" 2>&1
fi
$MPY -m scoring.v3_online_interim --run-dir "$B2D" > "$OUT/interim_b2.txt" 2>&1
$MPY -m scoring.v3_online_metrics partner-train --no-sim --out "$S/output/logs/identity_${MODE}_ptrain.json" > "$OUT/ptrain_stdout.txt" 2>&1
cp "$S/output/logs/identity_${MODE}_ptrain.json" "$OUT/ptrain.json" 2>/dev/null
$PY - > "$OUT/inprocess.json" 2>&1 <<'EOF'
import json, sys
sys.path.insert(0, ".")
from guard import run_online_v3 as R
doc = R.load_tasks_file()
out = {"steps": {k: R.STEPS[k] for k in ("B1", "B2", "B2v")}, "guard_input_files": R.guard_input_files(),
       "tasks_sha": doc["sha256"], "task_split": R.TASK_SPLIT, "version": R.VERSION,
       "guard_inputs_sha256": R.guard_inputs_sha256()}
for s in ("B1", "B2", "B2v"):
    t = R.select_tasks(doc, s, None)
    cfg = R.STEPS[s]
    out[f"select_{s}"] = t
    out[f"units_{s}"] = R.plan_units(t, cfg["tries"], cfg["first_try"])
    out[f"ident_{s}"] = R.plan_identity(s, f"{s}_x", t, cfg["tries"], cfg["first_try"], 4, "w", 95.0, 45.0, doc["sha256"])
ids = ["B1_20261024T000000Z_00000000", "B2_20261024T000000Z_00000000", "B2v_20261024T000000Z_00000000", "B2_bad"]
out["run_id_ok"] = {f"{s}:{i}": bool(R.RUN_ID_RE.match(i) and R.RUN_ID_RE.match(i).group(1) == s) for s in ("B1", "B2", "B2v") for i in ids}
print(json.dumps(out, sort_keys=True, default=str))
EOF
echo "done $MODE"
