"""The ASPM as the runtime sees it: rules (parsed LTLf), weights, predicate registry, action circuits.

Loaded from the published files (aspm.json in the authors' format, weights.json). The authors' loader
(`agent/tools/aspm_tool.load_aspm_json`) is run once as a format check; retrieval follows the authors'
`get_action_circuit`: the circuit of action predicate a is the rule set `actions[a]["soft_rule_ids"]`.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Set

from repro_core import ltlf


@dataclass
class Rule:
    rule_id: str
    description: str
    logic: str
    rule_type: str
    predicates: List[list]            # [name, description, keywords, type] as in aspm.json
    formula: ltlf.Formula = field(repr=False, default=None)

    @property
    def atoms(self) -> Set[str]:
        return set(self.formula.atoms)

    @property
    def temporal_root(self) -> bool:
        return self.formula.tree[0] in ltlf.TEMPORAL


@dataclass
class ASPM:
    rules: Dict[str, Rule]
    weights: Dict[str, Dict[str, float]]                # weights.json: action -> rule id -> θ (Stage A: all 1.0)
    circuits: Dict[str, List[str]]                       # action predicate -> rule ids
    descriptions: Dict[str, str]                         # predicate -> description (first declaration)
    declared_types: Dict[str, Set[str]]                  # predicate -> types used across rules
    action_predicates: Set[str] = field(default_factory=set)    # after P2-3 resolution
    type_resolution: Dict[str, str] = field(default_factory=dict)

    @property
    def conflicting(self) -> List[str]:
        return sorted(n for n, t in self.declared_types.items() if len(t) > 1)

    def candidate_actions(self) -> List[str]:
        """Predicates typed `action` in at least one rule (input to the vocabulary table, §3a)."""
        return sorted(n for n, t in self.declared_types.items() if "action" in t)

    def resolve_types(self, mapped: Iterable[str]) -> None:
        """P2-3: a predicate is an action iff it is consistently typed `action`, or it is inconsistently typed and
        some tool / respond maps to it (vocabulary table); otherwise it is a condition."""
        mapped = set(mapped)
        self.action_predicates, self.type_resolution = set(), {}
        for n, t in self.declared_types.items():
            if t == {"action"}:
                self.action_predicates.add(n)
            elif len(t) > 1:
                res = "action" if n in mapped else "condition"
                self.type_resolution[n] = res
                if res == "action":
                    self.action_predicates.add(n)

    def weight(self, action: str, rule_id: str) -> float:
        """θ of a rule in the circuit of `action`; a rule outside that circuit takes its θ from any circuit (1.0 if none)."""
        if rule_id in self.weights.get(action, {}):
            return self.weights[action][rule_id]
        for w in self.weights.values():
            if rule_id in w:
                return w[rule_id]
        return 1.0

    def circuit(self, actions: Iterable[str]) -> List[str]:
        ids = set()
        for a in actions:
            ids.update(self.circuits.get(a, []))
        return sorted(ids, key=int)


def load(aspm_dir: str, type_conflicts: Iterable[str] = (), check_with_authors_loader: bool = True) -> ASPM:
    """`type_conflicts`: predicates typed inconsistently during extraction (the run's alg2.json `type_conflicts`).
    aspm.json carries only the registry type (an action use wins), so P2-3 needs this list to re-resolve them."""
    path = os.path.join(aspm_dir, "aspm.json")
    if check_with_authors_loader:
        from agent.tools import aspm_tool
        with contextlib.redirect_stdout(io.StringIO()):
            status = aspm_tool.load_aspm_json(path)
        if status.get("status") != "success":
            raise ValueError(f"authors' loader rejected {path}: {status}")
    data = json.load(open(path, encoding="utf-8"))
    wpath = os.path.join(aspm_dir, "weights.json")
    weights_raw = json.load(open(wpath)) if os.path.exists(wpath) else {}
    weights = {a: {str(k): float(v) for k, v in w.items()} for a, w in weights_raw.get("circuits", {}).items()}
    rules, descriptions, types = {}, {}, {}
    for r in data["rule_list"]:
        rid = str(r["rule_id"])
        rules[rid] = Rule(rid, r.get("description", ""), r["logic"], r.get("rule_type", ""), r["predicates"],
                          ltlf.parse(r["logic"]))
        for p in r["predicates"]:
            descriptions.setdefault(p[0], p[1])
            types.setdefault(p[0], set()).add(p[3])
    circuits = {a: [str(x) for x in v.get("soft_rule_ids", [])] for a, v in data["actions"].items()}
    for n in type_conflicts:
        if n in types:
            types[n] = {"action", "condition"}
    aspm = ASPM(rules, weights, circuits, descriptions, types)
    aspm.resolve_types([])
    return aspm
