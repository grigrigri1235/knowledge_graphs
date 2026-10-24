"""Load τ-bench's tool code, data files and the policy texts from our copies (from_shieldagent/), with the standard
library only.

Why a loader: importing the copied package normally runs `tau_bench/__init__.py`, `envs/__init__.py` and
`envs/<domain>/__init__.py`. They import `litellm`, `pydantic` and `env.py` (not copied). See
`from_shieldagent/PROVENANCE.md`, "τ-bench: tool interface".

How it works:
- The tool modules and `data/__init__.py` are loaded from the copied files under private module names
  (`_pc_tau_copy_<domain>_tools`, `_pc_tau_copy_<domain>_data`). The relative imports in `tools/__init__.py` work,
  because that file is loaded as a package.
- Each tool file does `from tau_bench.envs.tool import Tool`. If `tau_bench` is not imported yet, we put empty
  package modules for `tau_bench` and `tau_bench.envs` into `sys.modules` (their `__path__` is the copied folder),
  load the tools, and then remove the empty modules again. So a later `import tau_bench` (Part 10, in the venv) gets
  the real package. If the real `tau_bench` is already imported, its `tau_bench.envs.tool` is used (same file).
- No copy is edited.
- Thread-safe (eval v2 audit A2, fix F1 item 1): one module lock (_LOAD_LOCK) covers every load and the
  registration of its result. A module must be in sys.modules while it runs (its relative imports need it), so
  without the lock a second thread could get the half-loaded module ("no attribute 'ALL_TOOLS'"). Now no thread
  sees a module or a tool table before it is complete. The empty tau_bench packages are added and removed under the
  same lock. Runners still call preload() in the main thread before their workers start.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import threading
import types
from typing import Any, Dict, List, Optional

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from state_tracker import paths
else:
    from . import paths

PKG_DIR = os.path.join(paths.TAU_DIR, "tau_bench")          # the copied package tau_bench/
ENVS_DIR = os.path.join(PKG_DIR, "envs")

_TOOLS: Dict[str, Dict[str, type]] = {}                    # domain -> {tool name: Tool class}; set only when complete
_DATA_MODULES: Dict[str, types.ModuleType] = {}            # domain -> data module; set only after it has run
_LOAD_LOCK = threading.RLock()                             # every load + registration (re-entrant: tools() -> load)
_LOADED: set = set()                                       # names of modules that _load_module ran to the end


def _load_module(name: str, path: str, package_dir: Optional[str] = None) -> types.ModuleType:
    """Load one file as module `name` (as a package if package_dir is given). Holds _LOAD_LOCK, so another thread
    waits until the module has run; it never gets a half-loaded one."""
    with _LOAD_LOCK:
        if name in _LOADED and name in sys.modules:
            return sys.modules[name]
        kw = {"submodule_search_locations": [package_dir]} if package_dir else {}
        spec = importlib.util.spec_from_file_location(name, path, **kw)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod                     # needed while it runs (relative imports); other loaders wait
        old = sys.dont_write_bytecode
        sys.dont_write_bytecode = True              # never write __pycache__ into the copies
        try:
            spec.loader.exec_module(mod)
        except BaseException:
            del sys.modules[name]
            raise
        finally:
            sys.dont_write_bytecode = old
        _LOADED.add(name)
        return mod


def _with_tool_base(fn):
    """Run fn() while `tau_bench.envs.tool` can be imported. Adds empty packages only if tau_bench is not imported,
    and removes them afterwards (under _LOAD_LOCK, so two loads never add and remove them in between)."""
    with _LOAD_LOCK:
        added: List[str] = []
        if "tau_bench" not in sys.modules:
            for name, folder in (("tau_bench", PKG_DIR), ("tau_bench.envs", ENVS_DIR)):
                m = types.ModuleType(name)
                m.__path__ = [folder]
                m.__file__ = None
                sys.modules[name] = m
                added.append(name)
            added.append("tau_bench.envs.tool")      # imported by the tools from the copy; removed below too
        try:
            return fn()
        finally:
            for name in added:
                sys.modules.pop(name, None)


def tools(domain: str) -> Dict[str, type]:
    """{tool name as the agent calls it: Tool class} for one domain, from the copied tools/__init__.py ALL_TOOLS.
    Thread-safe: the table is built under _LOAD_LOCK and published only when complete."""
    got = _TOOLS.get(domain)
    if got is not None:
        return got
    with _LOAD_LOCK:
        if domain not in _TOOLS:
            folder = os.path.join(ENVS_DIR, domain, "tools")

            def load():
                return _load_module(f"_pc_tau_copy_{domain}_tools", os.path.join(folder, "__init__.py"), folder)

            mod = _with_tool_base(load)
            _TOOLS[domain] = {t.get_info()["function"]["name"]: t for t in mod.ALL_TOOLS}
        return _TOOLS[domain]


def tools_info(domain: str) -> List[dict]:
    """The tool schemas the agent saw (get_info() of ALL_TOOLS, in that order)."""
    return [t.get_info() for t in tools(domain).values()]


def _data_module(domain: str) -> types.ModuleType:
    """The copied data/__init__.py module of one domain (loaded once, thread-safe)."""
    got = _DATA_MODULES.get(domain)
    if got is not None:
        return got
    with _LOAD_LOCK:
        if domain not in _DATA_MODULES:
            folder = os.path.join(ENVS_DIR, domain, "data")
            _DATA_MODULES[domain] = _load_module(f"_pc_tau_copy_{domain}_data", os.path.join(folder, "__init__.py"),
                                                 folder)
        return _DATA_MODULES[domain]


def load_data_fresh(domain: str) -> Dict[str, Any]:
    """τ-bench's own data/__init__.py load_data() on the copied JSON files: a new dict on every call (slow)."""
    return _data_module(domain).load_data()


def preload(domain: str) -> Dict[str, Any]:
    """Load the tool module and the data module of one domain now (call it in the main thread, before worker
    threads start). Reads no data file. Returns what is loaded (for the run's plan)."""
    t = tools(domain)
    _data_module(domain)
    return {"domain": domain, "tools": len(t), "tools_module": f"_pc_tau_copy_{domain}_tools",
            "data_module": f"_pc_tau_copy_{domain}_data"}


def policy_path(domain: str) -> str:
    return os.path.join(paths.POLICIES_DIR, f"{domain}_wiki.txt")


def policy_text(domain: str) -> str:
    with open(policy_path(domain), encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":                         # smoke test: python3 state_tracker/tau_copy.py
    for d in paths.DOMAINS:
        t = tools(d)
        data = load_data_fresh(d)
        print(d, len(t), "tools:", ", ".join(t), "| data:", {k: len(v) for k, v in data.items()})
    print("tau_bench in sys.modules after loading:", "tau_bench" in sys.modules)
    print("litellm loaded:", "litellm" in sys.modules, "| pydantic loaded:", "pydantic" in sys.modules)
    print(json.dumps(tools_info("retail")[0])[:120])
