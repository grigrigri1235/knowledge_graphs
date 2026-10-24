"""EXTRACT (Alg. 1 l.1, §3b): which candidate action predicates the concrete step instantiates (at most 3)."""
from __future__ import annotations

from typing import List

from repro_runtime.aspm import ASPM
from repro_runtime.calls import Meter, structured
from repro_runtime.prompts import render
from repro_runtime.vocab import SCHEMA

MAX_ACTIONS = 3


def extract(aspm: ASPM, action_text: str, agent_text: str, candidates: List[str], effort: str, meter: Meter) -> dict:
    if not candidates:
        return {"matched": [], "rejected": [], "reason": "no candidate action predicate for this tool"}
    cand = "\n".join(f"- {n}: {aspm.descriptions.get(n, '')}" for n in candidates)
    sysmsg, user = render("extract", action=action_text, text=agent_text or "(none)", candidates=cand)
    out = structured(meter, stage="extract", system=sysmsg, user=user, schema=SCHEMA, schema_name="matched_actions", effort=effort)
    names = list(dict.fromkeys(out["action_predicates"]))
    ok = [n for n in names if n in candidates]
    return {"matched": ok[:MAX_ACTIONS], "rejected": [n for n in names if n not in candidates] + ok[MAX_ACTIONS:],
            "reason": None if ok else "EXTRACT returned no candidate"}
