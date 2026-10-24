"""Eval v2 Part 3b (fork/guards_build.py): the two branch guards of Stage B, built as the runner builds them.

  - Branch A, "tgr_frozen": frozen TGR, the copied runner's guard unchanged: repro_online.guards.TGRGuard("tgr",
    from_shieldagent/rules/<domain>, tools_info) with its defaults (judge effort medium, epsilon 0.1, actionable
    feedback C), built by the copied exp_core/run_online.py build_guard("tgr", domain, tools_info, None, rules_dir),
    the same call as guard/run_online.py makes for tgr_frozen in Stage A.
  - Branch B, "tgr_tracker": guard/tgr_tracker.py build("tgr_tracker", domain, tools_info), as guard/run_online.py
    builds it (it also checks its frozen types and lookups).

Checks before a guard is built (no LLM call):
  - the rule set files have their frozen sha256 (the same values as from_shieldagent/SHA256SUMS);
  - the tool schemas give the tools_sha256 of the rule set's manifest (the rules were built for them).

The runner copy is imported lazily (inside the functions), so fork/run_all.py can install the write guard first.
Never imports gold code.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional

from fork.schema import BRANCH_GUARD
from state_tracker import paths

# sha256 of the frozen rule sets (from_shieldagent/SHA256SUMS, lines rules/<domain>/...)
FROZEN_RULES_SHA256 = {
    "airline": {"rule_set.json": "27e2eafa05fd919d41083e8d4dfeb7c4a6d9a789fa2ad7c5da645584d05bc5a4",
                "manifest.json": "4ee12f830d23b9e6dd32cebbf5dc8e10e6efbfdf8fdda7e08f4deebfac38c674"},
    "retail": {"rule_set.json": "9e395e2fc259cdf228612c4cd078a5bb3836bad4fe42af4493ffc9359fb63d7b",
               "manifest.json": "845f6d9a40ab05d83242b74ce9b8d35c71d880162c2394b67885c8a279fa602d"},
}
FROZEN_TGR_NAME = "tgr"          # the copied runner's variant name for A+B+C (repro_online.guards.TGRGuard.VARIANTS)


class GuardRefused(SystemExit):
    """A frozen input or the tool schemas do not match: the branch guards are not built."""


def sha256_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def tools_sha256(tools_info: List[dict]) -> str:
    """As guard/run_online.py tools_sha256 (sha256 of the sorted-key JSON of the tool schemas)."""
    return hashlib.sha256(json.dumps(tools_info, sort_keys=True).encode()).hexdigest()


def rules_dir(domain: str) -> str:
    return os.path.join(paths.RULES_DIR, domain)


def check_rules(domain: str, tools_info: List[dict]) -> Dict[str, str]:
    """sha256 of the frozen rule set files and of the tool schemas; raises GuardRefused if one differs."""
    if domain not in FROZEN_RULES_SHA256:
        raise GuardRefused(f"unknown domain {domain!r}")
    got = {}
    for name, want in FROZEN_RULES_SHA256[domain].items():
        h = sha256_file(os.path.join(rules_dir(domain), name))
        got[name] = h
        if h != want:
            raise GuardRefused(f"{domain}/{name}: sha256 {h} != frozen {want}")
    with open(os.path.join(rules_dir(domain), "manifest.json"), encoding="utf-8") as f:
        want_tools = json.load(f)["input"]["tools_sha256"]
    t = tools_sha256(tools_info)
    if t != want_tools:
        raise GuardRefused(f"{domain}: tool schemas {t} differ from the rule set's tools_sha256 {want_tools}")
    got["tools_sha256"] = t
    return got


def build_frozen(domain: str, tools_info: List[dict]):
    """Branch A guard: the copied frozen TGR guard (repro_online.guards.TGRGuard), unchanged, on our frozen rules,
    built by the copied runner's own builder exp_core/run_online.py build_guard("tgr", domain, tools_info, None,
    rules_dir) (the same call as guard/run_online.py's tgr_frozen for Stage A)."""
    from guard import runner_path
    runner_path.setup()
    from exp_core.run_online import build_guard as copied_build_guard   # runner copy
    from repro_online.guards import TGRGuard                             # runner copy
    g = copied_build_guard(FROZEN_TGR_NAME, domain, tools_info, None, rules_dir(domain))
    cfg = g.config
    if type(g) is not TGRGuard or g.name != FROZEN_TGR_NAME or \
            (cfg.judge_effort, cfg.epsilon, cfg.actionable_feedback) != ("medium", 0.1, True):
        raise GuardRefused(f"the copied builder gave {type(g).__name__} {g.name} {cfg}, not frozen TGR (A+B+C)")
    return g


def build_tracker(domain: str, tools_info: List[dict]):
    """Branch B guard: TGR + tracker, as guard/run_online.py builds it."""
    from guard import tgr_tracker
    return tgr_tracker.build("tgr_tracker", domain, tools_info, rules_dir(domain))


def guard_info(branch: str, guard: Any, domain: str, sums: Dict[str, str]) -> Dict[str, Any]:
    if branch == "B":
        info = dict(getattr(guard, "info", {}))
    else:
        cfg = guard.config
        info = {"guard": BRANCH_GUARD["A"], "class": "repro_online.guards.TGRGuard", "variant": FROZEN_TGR_NAME,
                "built_by": "exp_core/run_online.py build_guard('tgr', domain, tools_info, None, rules_dir) (copy)",
                "domain": domain, "rules_dir": rules_dir(domain), "judge_effort": cfg.judge_effort,
                "epsilon": cfg.epsilon, "actionable_feedback": cfg.actionable_feedback,
                "history_chars": cfg.history_chars}
    info["branch_guard"] = BRANCH_GUARD[branch]
    info["frozen_rules_sha256"] = {k: v for k, v in sums.items() if k != "tools_sha256"}
    info["tools_sha256"] = sums["tools_sha256"]
    return info


def build_branch_guards(domain: str, tools_info: List[dict], branches=("A", "B")) -> Dict[str, Dict[str, Any]]:
    """{branch: {"guard": guard object, "info": dict}} for one domain. Checks the frozen rules and the tool schemas
    first. No LLM call."""
    sums = check_rules(domain, tools_info)
    out = {}
    for b in branches:
        if b not in BRANCH_GUARD:
            raise GuardRefused(f"unknown branch {b!r}")
        g = build_frozen(domain, tools_info) if b == "A" else build_tracker(domain, tools_info)
        out[b] = {"guard": g, "info": guard_info(b, g, domain, sums)}
    return out


def is_tracker_guard(guard: Optional[Any]) -> bool:
    return type(guard).__name__ == "TGRTrackerGuard"
