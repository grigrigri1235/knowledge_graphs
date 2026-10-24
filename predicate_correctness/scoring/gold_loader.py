"""Load the copied gold predicate code (from_shieldagent/gold/) for scoring only.

The gold modules import `agent.predicates.context`, their place in ~/ShieldAgent. We do not edit the copies. Instead
we register two empty package modules, `agent` and `agent.predicates` (the second with `__path__` set to the copied
folder), import the modules, and then remove every `agent*` entry from sys.modules again, so no stub stays behind.
No bytecode is written into the copy.

Standard library only. No LLM calls.
"""
from __future__ import annotations

import importlib
import os
import sys
import types
from typing import Dict

PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # predicate_correctness/
GOLD_DIR = os.path.join(PC_DIR, "from_shieldagent", "gold")
GOLD_FILES = ("__init__.py", "context.py", "airline.py", "retail.py")

# Gold config: only `current_time` is read (airline). Value of ~/ShieldAgent/policies/curated/airline_config.json,
# which equals the airline policy line "The current time is 2024-05-15 15:00:00 EST." The retail config has none.
GOLD_CONFIG = {
    "airline": {"current_time": "2024-05-15T15:00:00"},
    "retail": {},
}


def load_gold(domain: str) -> Dict[str, object]:
    """The gold PREDICATES dict of one domain: name -> f(tool_call, trajectory, config) -> True | False | None."""
    if domain not in ("airline", "retail"):
        raise ValueError(f"unknown domain {domain!r}")
    clash = [m for m in sys.modules if m == "agent" or m.startswith("agent.")]
    if clash:
        raise RuntimeError(f"modules named agent.* are already loaded: {clash}")
    old_flag = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        pkg = types.ModuleType("agent")
        pkg.__path__ = []                                   # nothing else under agent/ can be imported
        sub = types.ModuleType("agent.predicates")
        sub.__path__ = [GOLD_DIR]
        pkg.predicates = sub
        sys.modules["agent"] = pkg
        sys.modules["agent.predicates"] = sub
        mod = importlib.import_module(f"agent.predicates.{domain}")
        return dict(mod.PREDICATES)
    finally:
        for m in [m for m in sys.modules if m == "agent" or m.startswith("agent.")]:
            del sys.modules[m]
        sys.dont_write_bytecode = old_flag


def gold_call(name: str, arguments: dict, turn: dict = None) -> dict:
    """The tool_call argument the gold predicates expect."""
    return {"name": name, "arguments": arguments, "turn": turn}
