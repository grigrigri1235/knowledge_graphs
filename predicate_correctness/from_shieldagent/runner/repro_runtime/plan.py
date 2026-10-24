"""Relevance filtering (Fig. 15, §4a) and the planner loop with Search / Binary-Check (Alg. 1 l.6–12, §4b)."""
from __future__ import annotations

import json
from typing import Dict, List, Optional

from repro_core.llm import run_tool_loop
from repro_runtime.aspm import ASPM
from repro_runtime.calls import Meter, structured, tool_loop_cache_dir
from repro_runtime.prompts import render

REL_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["relevant_rule_ids", "predicates"],
              "properties": {"relevant_rule_ids": {"type": "array", "items": {"type": "string"}},
                             "predicates": {"type": "array", "items": {
                                 "type": "object", "additionalProperties": False, "required": ["name", "grounded_description"],
                                 "properties": {"name": {"type": "string"}, "grounded_description": {"type": "string"}}}}}}
SEARCH_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["items"],
                 "properties": {"items": {"type": "array", "items": {
                     "type": "object", "additionalProperties": False, "required": ["value", "turn", "evidence"],
                     "properties": {"value": {"type": "string"}, "turn": {"type": "string"}, "evidence": {"type": "string"}}}}}}
BINARY_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["answers"],
                 "properties": {"answers": {"type": "array", "items": {
                     "type": "object", "additionalProperties": False, "required": ["id", "flag", "explanation"],
                     "properties": {"id": {"type": "string"}, "flag": {"type": "string", "enum": ["yes", "no", "unknown"]},
                                    "explanation": {"type": "string"}}}}}}
MAX_BINARY = 10


def rules_text(aspm: ASPM, rule_ids: List[str], header: str = "Available Rules to Ground:") -> str:
    """The authors' rule rendering (aspm_tool.formulate_solution_space), with P2-3-resolved predicate types."""
    out = header + "\n"
    for rid in rule_ids:
        r = aspm.rules[rid]
        out += f"\nRule id: {rid}\nRule type: {r.rule_type} rule\nDescription: {r.description}\nPredicates:\n"
        for p in r.predicates:
            kind = "action predicate" if p[0] in aspm.action_predicates else "state predicate"
            out += f"- {p[0]}: {p[1]} (Type: {kind})\n"
        out += f"Logic: {r.logic}\n" + "-" * 50 + "\n"
    return out


def relevance(aspm: ASPM, rule_ids: List[str], history: str, thought: str, action_text: str, actions: List[str],
              effort: str, meter: Meter) -> dict:
    sysmsg, user = render("relevance", history=history, thought=thought or "(none)", action=action_text,
                          action_predicates=json.dumps(actions), rules=rules_text(aspm, rule_ids))
    out = structured(meter, stage="relevance", system=sysmsg, user=user, schema=REL_SCHEMA, schema_name="relevant_rules",
                     effort=effort)
    keep = [rid for rid in rule_ids if rid in set(map(str, out["relevant_rule_ids"]))]
    names = set().union(*(aspm.rules[r].atoms for r in keep)) if keep else set()
    grounded = {p["name"]: p["grounded_description"] for p in out["predicates"] if p["name"] in names}
    return {"kept": keep, "dropped": [r for r in rule_ids if r not in keep],
            "unknown_ids": sorted(set(map(str, out["relevant_rule_ids"])) - set(rule_ids)), "grounded": grounded}


VALUE = {"true": True, "false": False, "unknown": None}


class PredicateMap:
    """Fig. 17 predicate tracking: name -> unassigned (missing) / True / False / None (unknown)."""

    def __init__(self, names: List[str], descriptions: Dict[str, str]):
        self.names = list(names)
        self.descriptions = descriptions
        self.values: Dict[str, Optional[bool]] = {}
        self.rejected: List[dict] = []

    def check_unassigned(self):
        return {"unassigned": [{"name": n, "description": self.descriptions.get(n, ""), "type": "state predicate"}
                               for n in self.names if n not in self.values]}

    def assign_predicate_values(self, assignments=None, **kw):
        assignments = dict(assignments or {}, **kw)
        accepted, rejected = [], {}
        for n, v in assignments.items():
            key = str(v).strip().lower() if not isinstance(v, bool) else ("true" if v else "false")
            if n not in self.names:
                rejected[n] = "not a predicate of the rules under verification"
            elif key not in VALUE:
                rejected[n] = "value must be true, false or unknown"
            else:
                self.values[n] = VALUE[key]
                accepted.append(n)
        if rejected:
            self.rejected.append(rejected)
        return {"accepted": accepted, "rejected": rejected, "remaining": len(self.names) - len(self.values)}


PLANNER_TOOLS = [
    {"name": "check_unassigned", "description": "Get all predicates that have not been assigned yet, with their descriptions and types.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "assign_predicate_values", "description": "Push verified truth values into the predicate map.",
     "parameters": {"type": "object", "properties": {"assignments": {
         "type": "object", "description": "predicate name -> \"true\" | \"false\" | \"unknown\"",
         "additionalProperties": {"type": "string", "enum": ["true", "false", "unknown"]}}}, "required": ["assignments"]}},
    {"name": "search", "description": "Search: retrieves relevant information from the past interaction history and enumerates queried items.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "binary_check", "description": f"Binary Check: assigns a yes/no/unknown label to each query about the history and the current action (at most {MAX_BINARY} queries per call).",
     "parameters": {"type": "object", "properties": {"queries": {"type": "array", "items": {"type": "string"}}}, "required": ["queries"]}},
]


def planner(aspm: ASPM, names: List[str], descriptions: Dict[str, str], rule_ids: List[str], history: str,
            action_text: str, actions: List[str], planner_effort: str, aux_effort: str, meter: Meter,
            max_turns: int = 15) -> dict:
    pm = PredicateMap(names, descriptions)
    counts = {"search": 0, "binary_check": 0}

    def search(query: str = "", **_):
        counts["search"] += 1
        sysmsg, user = render("search", history=history, action=action_text, query=query)
        return structured(meter, stage="search", system=sysmsg, user=user, schema=SEARCH_SCHEMA, schema_name="search_results",
                          effort=aux_effort)

    def binary_check(queries=None, **_):
        qs = [str(q) for q in (queries or [])][:MAX_BINARY]
        counts["binary_check"] += 1
        sysmsg, user = render("binary_check", history=history, action=action_text,
                              questions="\n".join(f"{i + 1}. {q}" for i, q in enumerate(qs)))
        return structured(meter, stage="binary_check", system=sysmsg, user=user, schema=BINARY_SCHEMA,
                          schema_name="binary_answers", effort=aux_effort)

    sysmsg = render("planner_system")[1]
    _, user = render("planner_user", history=history, action=action_text, action_predicates=json.dumps(actions),
                     rules=rules_text(aspm, rule_ids, header=""))
    handlers = {"check_unassigned": pm.check_unassigned, "assign_predicate_values": pm.assign_predicate_values,
                "search": search, "binary_check": binary_check}
    res = run_tool_loop(system=sysmsg, user=user, tools=PLANNER_TOOLS, handlers=handlers, stage="planner",
                        max_turns=max_turns, effort=planner_effort, cache_dir=tool_loop_cache_dir())
    u = res.usage
    meter.add("planner", planner_effort, u.get("cache_hits", 0), u, u.get("api_seconds", 0.0), n=u.get("calls", res.turns))
    forced = [n for n in names if n not in pm.values]
    values = dict(pm.values, **{n: None for n in forced})
    errors = sum(1 for t in res.transcript if "output" in t and t["output"].startswith('{"error"'))
    return {"values": values, "forced_unknown": forced, "turns": res.turns, "stopped": res.stopped,
            "completed": res.stopped == "final_text" and not forced, "tool_errors": errors,
            "rejected_assignments": pm.rejected, "n_search": counts["search"], "n_binary_check": counts["binary_check"],
            "final_text": res.final_text, "transcript": res.transcript}
