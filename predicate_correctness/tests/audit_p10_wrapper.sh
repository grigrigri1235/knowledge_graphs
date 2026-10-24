#!/bin/bash
# Part 10 audit: the wrapper's safety rules (dry runs only; no LLM call). Run from anywhere; output to stdout.
cd /home/azureuser/code_projects/predicate_correctness || exit 1
PY=/home/azureuser/venvs/tau-bench/bin/python
run() {
  echo "=== $*"
  $PY -B -m guard.run_online "$@" --dry-run > /tmp/claude-1000/p10_audit_one.log 2>&1
  rc=$?
  grep -E "RunRefused|refused|error:|DRY RUN DONE|Traceback|\"agent\"|\"user\"|\"guard\"|units_to_run|tasks_label|PermissionError" /tmp/claude-1000/p10_audit_one.log | head -12
  echo "exit $rc"
}
mkdir -p /tmp/claude-1000
# must be refused
run --profile grok-eval --env retail --tasks train --tag audit_x
run --profile luna-dev --env retail --tasks test --tag audit_x
run --profile luna-dev --env airline --task-ids 2 --tag audit_x
run --profile luna-dev --env retail --task-ids 0,1 --tag audit_x
run --profile luna-dev --env retail --tasks dev --tag audit_x
run --profile luna-dev --env retail --tasks train --tag audit_x --out-root /tmp/claude-1000/x
run --profile luna-dev --env retail --tasks train --tag audit_x --cache-root /home/azureuser/ShieldAgent/output/tgr/_llmcache
run --profile luna-dev --env retail --tasks train --tag ../../x
run --profile luna-dev --env retail --tasks train --tag audit_x --rules-dir /home/azureuser/ShieldAgent/tgr_rules/retail/frozen
run --profile luna-dev --env retail --guard tgr --tasks train --tag audit_x
# must work (the documented runs)
run --profile luna-dev --env airline --tasks train --trials 3 --tag audit_dry
run --profile luna-dev --env retail --tasks train --trials 3 --tag audit_dry
run --profile nano-agent-luna --env airline --tasks train --trials 3 --tag audit_dry
run --profile nano-agent-luna --env retail --tasks train --trials 3 --tag audit_dry
run --profile luna-dev --env airline --tasks val --trials 3 --tag audit_dry
run --profile luna-dev --env retail --tasks val --trials 3 --tag audit_dry
echo "ALL DONE"
