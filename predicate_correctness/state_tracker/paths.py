"""Paths to the copies in predicate_correctness/from_shieldagent/ (see from_shieldagent/PROVENANCE.md)."""
from __future__ import annotations

import os
import sys

PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # predicate_correctness/
FROM_SA = os.path.join(PC_DIR, "from_shieldagent")
CODE_DIR = os.path.join(FROM_SA, "code")                # repro_core/, repro_runtime/
TAU_DIR = os.path.join(FROM_SA, "tau_bench")            # τ-bench repository root (LICENSE, tau_bench/)
RULES_DIR = os.path.join(FROM_SA, "rules")              # <domain>/rule_set.json
POLICIES_DIR = os.path.join(FROM_SA, "policies")
RUNS_DIR = os.path.join(FROM_SA, "runs")                # <run>/<domain>/tgr/episodes.jsonl
SPLITS_FILE = os.path.join(FROM_SA, "splits", "splits.json")
SHA256SUMS = os.path.join(FROM_SA, "SHA256SUMS")         # checksums of the copies (Part 1)
STATE_TRACKER_DIR = os.path.join(PC_DIR, "state_tracker")
TESTS_DIR = os.path.join(PC_DIR, "tests")
OUTPUT_DIR = os.path.join(PC_DIR, "output")
LOGS_DIR = os.path.join(OUTPUT_DIR, "logs")              # output of every command

DOMAINS = ("airline", "retail")
RUNS = ("luna_train_v5", "nano_train")
RUN_DOMAINS = tuple((r, d) for r in RUNS for d in DOMAINS)   # the 4 saved train runs


def add_code_path() -> None:
    """Make the copied packages repro_core and repro_runtime importable (no copy is edited)."""
    if CODE_DIR not in sys.path:
        sys.path.insert(0, CODE_DIR)


def rule_set_path(domain: str) -> str:
    return os.path.join(RULES_DIR, domain, "rule_set.json")


def episodes_path(run: str, domain: str) -> str:
    return os.path.join(RUNS_DIR, run, domain, "tgr", "episodes.jsonl")


def steps_path(run: str, domain: str) -> str:
    """Step records of one run and domain (Part 2, state_tracker/load_steps.py)."""
    return os.path.join(OUTPUT_DIR, f"steps_{run}_{domain}.jsonl")
