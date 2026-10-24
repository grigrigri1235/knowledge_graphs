"""A TGR rule set as repro_runtime's ASPM, the input of the decision code (repro_runtime.mln.decide).

Where `to_aspm` comes from:
  ~/ShieldAgent/method_tgr/rules.py, function `to_aspm` (lines 251-267), commit 1bacdb0 (the same file at tag
  tgr-frozen-v1; git blob 4ffa4b5e; file sha256 1d9c3a8b59d31a2a06fc1e349e92fe6868326fb6cefb24dee460999e215ba178).
  The function body is copied without changes (checked on 2026-10-21: same Python syntax tree as the original).
  The rest of rules.py needs LLM code (method_tgr.llm, prompts), so only this function is copied (Part 1, subtask 3).

How TGR uses it (method_tgr/runtime.py, for Parts 8 and 10): aspm = to_aspm(rule_set); for a pending tool call,
matched = [tool] if tool in aspm.action_predicates else []; circuit = aspm.circuit(matched); current =
{a: a in matched for a in aspm.action_predicates} plus the predicate values; then
mln.decide(aspm, circuit, tool, current, past, 0.1, 16); allowed iff margin >= -0.1. TGR rules have no temporal
operator, so only the current position counts and `past` does not change the result.
"""
from __future__ import annotations

import json

from .paths import add_code_path, rule_set_path

add_code_path()

from repro_core import ltlf  # noqa: E402  (copy in from_shieldagent/code/)
from repro_runtime.aspm import ASPM, Rule  # noqa: E402


def to_aspm(rule_set: dict) -> ASPM:
    """The rule set as repro_runtime's ASPM (θ = 1 for every rule: weights left empty, ASPM.weight defaults to 1.0)."""
    action_names = set(rule_set["action_names"])
    rules, descriptions, types = {}, {}, {}
    for n, p in rule_set["predicates"].items():
        descriptions[n] = p["description"]
        types[n] = {"condition"}
    for a in action_names:
        descriptions.setdefault(a, rule_set.get("actions", {}).get(a, a))
        types[a] = {"action"}
    for r in rule_set["rules"]:
        atoms = ltlf.parse(r["logic"]).atoms
        preds = [[n, descriptions.get(n, ""), [], "action" if n in action_names else "condition"] for n in atoms]
        rules[r["id"]] = Rule(r["id"], r["description"], r["logic"], "action", preds, ltlf.parse(r["logic"]))
    aspm = ASPM(rules, {}, {a: list(ids) for a, ids in rule_set["circuits"].items()}, descriptions, types)
    aspm.resolve_types([])
    return aspm


def load_rule_set(domain: str) -> dict:
    """The frozen TGR rule set of a domain ("airline" or "retail"), from the copy."""
    with open(rule_set_path(domain), encoding="utf-8") as f:
        return json.load(f)
