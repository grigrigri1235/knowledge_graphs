"""Direct baseline (paper §5.1 "Direct prompt"): one call with the complete policy and the step (p2_design §7)."""
from __future__ import annotations

import time

from repro_core.taubench_steps import Step, render_history
from repro_runtime.calls import Meter, structured
from repro_runtime.prompts import render
from repro_runtime.shield import action_text, render_feedback

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["safe", "violated_policy_statements", "explanation"],
          "properties": {"safe": {"type": "boolean"}, "violated_policy_statements": {"type": "array", "items": {"type": "string"}},
                         "explanation": {"type": "string"}}}


def direct(policy: str, step: Step, effort: str, history_chars: int = 24000) -> dict:
    meter, t0 = Meter(), time.time()
    sysmsg, user = render("direct", policy=policy, history=render_history(step.history, max_chars=history_chars),
                          action=action_text(step))
    out = structured(meter, stage="direct", system=sysmsg, user=user, schema=SCHEMA, schema_name="direct_decision", effort=effort)
    violated = [{"rule_id": f"P{i + 1}", "description": s} for i, s in enumerate(out["violated_policy_statements"])]
    rec = {"step_index": step.index, "action_allowed": bool(out["safe"]), "violated_rules": violated,
           "explanation": out["explanation"], "seconds": round(time.time() - t0, 1), "usage": meter.summary()}
    if not out["safe"]:
        rec["feedback_text"] = render_feedback(violated, out["explanation"], "")
    return rec
