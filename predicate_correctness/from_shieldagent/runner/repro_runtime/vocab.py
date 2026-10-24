"""§3a vocabulary table (once per domain, cached): agent tool / respond → candidate ASPM action predicates.

Also the input of the P2-3 type resolution (a predicate is an action iff some tool or respond maps to it).
"""
from __future__ import annotations

import json
from typing import Dict, List

from repro_runtime.aspm import ASPM
from repro_runtime.calls import Meter, structured
from repro_runtime.prompts import render

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["action_predicates"],
          "properties": {"action_predicates": {"type": "array", "items": {"type": "string"}}}}

RESPOND_TOOL = {"type": "function", "function": {
    "name": "respond", "description": "Send a text message to the user (the agent's reply in the conversation).",
    "parameters": {"type": "object", "properties": {"content": {"type": "string", "description": "The message text."}},
                   "required": ["content"]}}}


def action_list(aspm: ASPM) -> str:
    return "\n".join(f"- {n}: {aspm.descriptions.get(n, '')}" for n in aspm.candidate_actions())


def build(aspm: ASPM, tools: List[dict], effort: str, meter: Meter) -> Dict[str, dict]:
    """tools: the environment's tool schemas (OpenAI function format). Returns tool name -> {candidates, rejected}."""
    allowed = set(aspm.candidate_actions())
    table = {}
    for tool in list(tools) + [RESPOND_TOOL]:
        name = tool["function"]["name"]
        sysmsg, user = render("vocab", tool=json.dumps(tool, ensure_ascii=False, sort_keys=True), action_predicates=action_list(aspm))
        out = structured(meter, stage="vocab", system=sysmsg, user=user, schema=SCHEMA, schema_name="vocabulary", effort=effort)
        names = list(dict.fromkeys(out["action_predicates"]))
        table[name] = {"candidates": sorted(n for n in names if n in allowed), "rejected": sorted(n for n in names if n not in allowed)}
    return table
