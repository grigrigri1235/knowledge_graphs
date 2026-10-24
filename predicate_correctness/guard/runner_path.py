"""Make the copied runner code (from_shieldagent/runner/) importable, without editing it.

- Puts from_shieldagent/runner/ first on sys.path and turns off bytecode writing, so no __pycache__ lands in the copy.
- The Part 1 copy from_shieldagent/code/ also has packages named repro_core and repro_runtime (a subset, same files).
  If one of them is already imported from code/ (for example by state_tracker/tgr_to_aspm.py in a test process), its
  package path gets the runner folder added, so the missing modules (calls.py, shield.py, llm.py, ...) load from the
  runner copy. Before that, every module already loaded from code/ must have the same sha256 as its runner copy.
- Never imports anything from ~/ShieldAgent.

Standard library only.
"""
from __future__ import annotations

import hashlib
import os
import sys

PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # predicate_correctness/
RUNNER_DIR = os.path.join(PC_DIR, "from_shieldagent", "runner")
SHARED_PACKAGES = ("repro_core", "repro_runtime")      # also in from_shieldagent/code/ (Part 1)


class RunnerPathError(RuntimeError):
    """A module already imported from another copy differs from the runner copy."""


def _sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def setup() -> str:
    """Put the runner copy on sys.path (once). Returns the runner folder."""
    sys.dont_write_bytecode = True
    if RUNNER_DIR not in sys.path:
        sys.path.insert(0, RUNNER_DIR)
    if PC_DIR not in sys.path:
        sys.path.append(PC_DIR)
    for pkg in SHARED_PACKAGES:
        mod = sys.modules.get(pkg)
        if mod is None:
            continue
        rdir = os.path.join(RUNNER_DIR, pkg)
        pkg_path = getattr(mod, "__path__", None)
        if pkg_path is None or rdir in list(pkg_path):
            continue
        for name, sub in list(sys.modules.items()):
            if name != pkg and not name.startswith(pkg + "."):
                continue
            f = getattr(sub, "__file__", None)
            if not f or os.path.abspath(f).startswith(RUNNER_DIR):
                continue
            parts = name.split(".")
            mine = (os.path.join(RUNNER_DIR, *parts, "__init__.py") if name == pkg
                    else os.path.join(RUNNER_DIR, *parts) + ".py")
            if not os.path.exists(mine) or _sha256(f) != _sha256(mine):
                raise RunnerPathError(f"{name} is already imported from {f}, which differs from the runner copy")
        pkg_path.append(rdir)
    return RUNNER_DIR
