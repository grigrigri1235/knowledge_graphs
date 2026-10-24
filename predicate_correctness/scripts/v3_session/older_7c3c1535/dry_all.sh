#!/bin/bash
set -u
cd /home/azureuser/code_projects/predicate_correctness
touch /tmp/claude-1000/-home-azureuser-code-projects/7c3c1535-bd0d-4a16-af35-122f073a1f9e/scratchpad/dry_marker
sleep 1
echo "start k=1 $(date -u +%T)"
PYTHONDONTWRITEBYTECODE=1 /home/azureuser/venvs/tau-bench/bin/python -B -m fork.run_all output/eval_v2/fork_points.jsonl --profile luna-dev --ids "$(paste -sd, output/eval_v2/stage_b_ids_1.txt)" --branches A,B --tries 5 --workers 8 --later-left-usd 21 --dry-run > output/logs/v2_p7b_dry_stage_b_1.log 2>&1
echo "k=1 rc=$? $(date -u +%T)"
echo "start k=2 $(date -u +%T)"
PYTHONDONTWRITEBYTECODE=1 /home/azureuser/venvs/tau-bench/bin/python -B -m fork.run_all output/eval_v2/fork_points.jsonl --profile nano-agent-luna --ids "$(paste -sd, output/eval_v2/stage_b_ids_2.txt)" --branches A,B --tries 5 --workers 8 --later-left-usd 16 --dry-run > output/logs/v2_p7b_dry_stage_b_2.log 2>&1
echo "k=2 rc=$? $(date -u +%T)"
echo "start k=3 $(date -u +%T)"
PYTHONDONTWRITEBYTECODE=1 /home/azureuser/venvs/tau-bench/bin/python -B -m fork.run_all output/eval_v2/fork_points.jsonl --profile nano-agent-luna --ids "$(paste -sd, output/eval_v2/stage_b_ids_3.txt)" --branches A,B --tries 5 --workers 8 --later-left-usd 16 --dry-run > output/logs/v2_p7b_dry_stage_b_3.log 2>&1
echo "k=3 rc=$? $(date -u +%T)"
echo "start k=4 $(date -u +%T)"
PYTHONDONTWRITEBYTECODE=1 /home/azureuser/venvs/tau-bench/bin/python -B -m fork.run_all output/eval_v2/fork_points.jsonl --profile nano-agent-luna --ids "$(paste -sd, output/eval_v2/stage_b_ids_4.txt)" --branches A,B --tries 5 --workers 8 --later-left-usd 16 --dry-run > output/logs/v2_p7b_dry_stage_b_4.log 2>&1
echo "k=4 rc=$? $(date -u +%T)"
