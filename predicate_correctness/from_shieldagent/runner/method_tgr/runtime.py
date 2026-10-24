"""TGR runtime: one guarded agent step.

  action predicate  = the tool name ("respond" for a message) under A; under not-A, ShieldAgent's vocabulary table +
                      EXTRACT map the step to the rule set's free action predicates (repro_runtime.vocab / extract);
  circuit           = the rules of that action (no rules: allowed without any LLM call);
  predicate values  = one judge call over the conversation so far and the pending action;
  decision          = Eq. 4-5 (repro_runtime.mln.decide), θ = 1, allowed iff P(µ=1) − P(µ=0) ≥ −ε;
  feedback          = C: actionable text (method_tgr.feedback); not-C: ShieldAgent's explanation call.
A per-conversation trace of executed steps (as repro_runtime.shield.Conversation) serves temporal rules (not-B);
blocked steps are not recorded (P2-6); `commit` records a step executed through the cap override.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from repro_core.taubench_steps import Step, render_history
from repro_runtime import mln
from repro_runtime.calls import Meter, structured as aux_structured
from repro_runtime.prompts import render as shield_render
from repro_runtime.shield import EXPLAIN_SCHEMA, action_text, render_feedback

from method_tgr import feedback as fb
from method_tgr import llm, prompts
from method_tgr.rules import RESPOND, to_aspm

JUDGE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["predicates"],
                "properties": {"predicates": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["name", "value", "evidence"],
                    "properties": {"name": {"type": "string"}, "value": {"type": "string", "enum": ["true", "false", "unknown"]},
                                   "evidence": {"type": "string"}}}}}}
VALUE = {"true": True, "false": False, "unknown": None}


@dataclass
class TGRConfig:
    actionable_feedback: bool = True     # component C
    judge_effort: str = "medium"
    aux_effort: str = "low"              # not-A vocabulary / EXTRACT, not-C explanation
    epsilon: float = 0.1
    history_chars: int = 24000
    gibbs_threshold: int = 16
    attempts: int = 3


@dataclass
class Conversation:
    trace: List[Dict[str, Optional[bool]]] = field(default_factory=list)


class TGR:
    def __init__(self, rule_set: dict, tools: List[dict], config: TGRConfig = TGRConfig()):
        self.rule_set, self.config = rule_set, config
        self.grounded = rule_set["flags"]["a"]
        self.aspm = to_aspm(rule_set)
        self.predicates = rule_set["predicates"]
        self.setup_meter = Meter()
        self.vocab = None
        if not self.grounded:
            from repro_runtime import vocab
            self.vocab = vocab.build(self.aspm, tools, config.aux_effort, self.setup_meter)

    def step(self, conv: Conversation, step: Step) -> dict:
        last, n0 = None, len(conv.trace)
        for attempt in range(self.config.attempts):
            try:
                rec = self._step(conv, step)
                rec["attempts"] = attempt + 1
                return rec
            except Exception as e:  # noqa: BLE001 - transient API errors; cached calls replay
                del conv.trace[n0:]
                last = e
                time.sleep(10 * (attempt + 1))
        raise RuntimeError(f"TGR step failed after {self.config.attempts} attempts: {last}")

    def _actions(self, step: Step, a_text: str, meter: Meter) -> List[str]:
        if self.grounded:
            name = RESPOND if step.kind == "respond" else step.name
            return [name] if name in self.aspm.action_predicates else []
        from repro_runtime.extract import extract
        cands = self.vocab.get(step.name, {}).get("candidates", [])
        thought = step.agent_text if step.kind == "tool_call" else ""
        return extract(self.aspm, a_text, thought, cands, self.config.aux_effort, meter)["matched"]

    def _step(self, conv: Conversation, step: Step) -> dict:
        cfg, aspm, meter, t0 = self.config, self.aspm, Meter(), time.time()
        a_text = action_text(step)
        matched = self._actions(step, a_text, meter)
        current = {a: (a in matched) for a in aspm.action_predicates}
        rec = {"step_index": step.index, "kind": step.kind, "name": step.name, "action_text": a_text, "matched": matched,
               "trace_position": current}
        circuit = aspm.circuit(matched)
        rec["circuit"] = circuit
        if not circuit:
            conv.trace.append(current)
            return self._finish(rec, meter, t0, True, "no rules for this action")
        names = sorted({n for r in circuit for n in aspm.rules[r].atoms} - aspm.action_predicates)
        judged = self._judge(step, a_text, circuit, names, meter) if names else {}
        current.update({n: judged.get(n, {}).get("value") for n in names})
        rec["judge"] = judged
        past = list(conv.trace)
        per_action = [mln.decide(aspm, circuit, a, current, past, cfg.epsilon, cfg.gibbs_threshold) for a in matched]
        rec["mln"] = [{k: d[k] for k in ("action", "group_rules", "group_unknowns", "method", "p_execute", "margin",
                                          "violated_by_action", "at_risk", "false_in_best_world")} for d in per_action]
        allowed = all(d["allowed"] for d in per_action)
        # V_s: every rule the action breaks in the most probable world or with probability > 0 (unknowns), so the
        # feedback names all requirements to establish at once (ShieldAgent names the first non-empty of these sets)
        ids = sorted({r for d in per_action if not d["allowed"]
                      for r in (set(d["violated_by_action"]) | set(d["at_risk"]) or d["false_in_best_world"])}, key=int)
        violated = [{"rule_id": r, "description": aspm.rules[r].description, "logic": aspm.rules[r].logic} for r in ids]
        rec.update({"margin": min(d["margin"] for d in per_action), "allowed_eps0": all(d["allowed_eps0"] for d in per_action),
                    "violated_rules": violated, "unknown_predicates": [n for n in names if current.get(n) is None]})
        if allowed:
            conv.trace.append(current)
        else:
            rec["feedback_text"] = self._feedback(step, a_text, violated, current, judged, meter, rec)
        return self._finish(rec, meter, t0, allowed, None)

    def _judge(self, step: Step, a_text: str, circuit: List[str], names: List[str], meter: Meter) -> Dict[str, dict]:
        rules = "\n".join(f"[{r}] {self.aspm.rules[r].description}\n    logic: {self.aspm.rules[r].logic}" for r in circuit)
        preds = "\n".join(f"- {n}: {self.aspm.descriptions.get(n, '')}"
                          + (f" (evidence from: {', '.join(self.predicates[n]['source'])})"
                             if self.grounded and self.predicates.get(n, {}).get("source") else "") for n in names)
        facts = "\n".join(f"- {b['text']}" for b in self.rule_set.get("background", [])) or "(none)"
        sysmsg, user = prompts.render("judge", history=render_history(step.history, max_chars=self.config.history_chars),
                                      action=a_text, rules=rules, facts=facts, predicates=preds)
        out = llm.structured(meter, stage="tgr_judge", system=sysmsg, user=user, schema=JUDGE_SCHEMA,
                             schema_name="predicate_values", effort=self.config.judge_effort)
        got = {p["name"]: {"value": VALUE[p["value"]], "evidence": p["evidence"]} for p in out["predicates"] if p["name"] in names}
        for n in names:
            got.setdefault(n, {"value": None, "evidence": "(not returned by the judge)"})
        return got

    def _feedback(self, step, a_text, violated, current, judged, meter, rec) -> str:
        if self.config.actionable_feedback:
            return fb.actionable(step.kind, step.name, violated, self.aspm, current, judged, self.predicates)
        sysmsg, user = shield_render("explain", action=a_text, rules="\n".join(
            f"[{v['rule_id']}] {v['description']} (logic: {v['logic']})" for v in violated))
        out = aux_structured(meter, stage="explain", system=sysmsg, user=user, schema=EXPLAIN_SCHEMA,
                             schema_name="explanation", effort=self.config.aux_effort)
        rec.update({"explanation": out["explanation"], "feedback": out["feedback"]})
        return render_feedback(violated, out["explanation"], out["feedback"])

    def commit(self, conv: Conversation, rec: dict) -> None:
        if not rec["action_allowed"]:
            conv.trace.append(rec["trace_position"])

    def _finish(self, rec, meter, t0, allowed, reason):
        rec.setdefault("margin", None)
        rec.setdefault("violated_rules", [])
        rec.update({"action_allowed": allowed, "epsilon": self.config.epsilon, "reason": reason,
                    "seconds": round(time.time() - t0, 1), "usage": meter.summary(), "calls": meter.calls})
        return rec


def load_rule_set(path: str) -> dict:
    return json.load(open(path, encoding="utf-8"))
