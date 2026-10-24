"""Shield one agent step (Alg. 1): EXTRACT → RETRIEVE → relevance → planner → VERIFY → MLN (Eq. 4/5) → feedback.

A `Conversation` keeps the per-conversation trace store: position j holds the truth table of the j-th EXECUTED step
(invoked action predicates true, all other action predicates false; condition predicates as assigned, unknown
otherwise), used by temporal rules (p2_design §2). A blocked step is not executed online, so it is NOT recorded
(spec "Trace store"); `Shield.commit` records a step that is executed anyway (cap override). Offline replay of
recorded trajectories, where every step was executed, sets `record_blocked_steps`.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from repro_core.taubench_steps import Step, render_history
from repro_runtime import mln, vocab
from repro_runtime.aspm import ASPM
from repro_runtime.calls import Meter, structured
from repro_runtime.extract import extract
from repro_runtime.plan import planner, relevance
from repro_runtime.prompts import render

EXPLAIN_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["explanation", "feedback"],
                  "properties": {"explanation": {"type": "string"}, "feedback": {"type": "string"}}}


@dataclass
class ShieldConfig:
    aux_effort: str = "low"          # vocabulary, EXTRACT, relevance, Search, Binary-Check, explanation
    planner_effort: str = "medium"
    epsilon: float = 0.1
    max_turns: int = 15
    history_chars: int = 24000
    gibbs_threshold: int = 16
    attempts: int = 3                # re-run a step after a transient API error (cached calls replay)
    record_blocked_steps: bool = False   # True only for offline replay (the recorded agent executed every step)


@dataclass
class Conversation:
    trace: List[Dict[str, Optional[bool]]] = field(default_factory=list)


def action_text(step: Step) -> str:
    if step.kind == "respond":
        return f"respond(content={json.dumps(step.arguments.get('content', ''), ensure_ascii=False)})"
    return f"{step.name}({json.dumps(step.arguments, ensure_ascii=False)})"


def render_feedback(violated: List[dict], explanation: str, feedback: str) -> str:
    rules = "; ".join(f"[{v['rule_id']}] {v['description']}" for v in violated)
    return f"BLOCKED by policy guardrail. Violated rules: {rules} Explanation: {explanation}" + (f" Feedback: {feedback}" if feedback else "")


class Shield:
    def __init__(self, aspm: ASPM, tools: List[dict], config: ShieldConfig = ShieldConfig()):
        self.aspm, self.config = aspm, config
        self.setup_meter = Meter()
        self.vocab = vocab.build(aspm, tools, config.aux_effort, self.setup_meter)
        mapped = set().union(*(v["candidates"] for v in self.vocab.values()))
        aspm.resolve_types(mapped)                                           # P2-3
        for v in self.vocab.values():
            v["candidates"] = [n for n in v["candidates"] if n in aspm.action_predicates]

    def step(self, conv: Conversation, step: Step) -> dict:
        last_err, n0 = None, len(conv.trace)
        for attempt in range(self.config.attempts):
            try:
                rec = self._step(conv, step)
                rec["attempts"] = attempt + 1
                return rec
            except Exception as e:  # noqa: BLE001 - transient API errors; cached calls make the retry cheap
                del conv.trace[n0:]
                last_err = e
                time.sleep(10 * (attempt + 1))
        raise RuntimeError(f"shield step failed after {self.config.attempts} attempts: {last_err}")

    def _step(self, conv: Conversation, step: Step) -> dict:
        cfg, aspm, meter, t0 = self.config, self.aspm, Meter(), time.time()
        history = render_history(step.history, max_chars=cfg.history_chars)
        a_text = action_text(step)
        thought = step.agent_text if step.kind == "tool_call" else ""
        cands = self.vocab.get(step.name, {}).get("candidates", [])
        ex = extract(aspm, a_text, thought, cands, cfg.aux_effort, meter)
        matched = ex["matched"]
        current = {a: (a in matched) for a in aspm.action_predicates}
        rec = {"step_index": step.index, "kind": step.kind, "name": step.name, "action_text": a_text,
               "candidates": cands, "matched": matched, "extract_rejected": ex["rejected"],
               "history_truncated": len(render_history(step.history)) > cfg.history_chars}
        rec["trace_position"] = current
        if not matched:
            conv.trace.append(current)
            return self._finish(rec, meter, t0, allowed=True, reason="unmapped: " + (ex["reason"] or ""), unmapped=True)
        circuit = aspm.circuit(matched)
        rec["circuit"] = circuit
        if not circuit:
            conv.trace.append(current)
            return self._finish(rec, meter, t0, allowed=True, reason="no rules in the circuit of the matched actions")
        rel = relevance(aspm, circuit, history, thought, a_text, matched, cfg.aux_effort, meter)
        kept = rel["kept"]
        rec["relevance"] = {"kept": kept, "dropped": rel["dropped"], "unknown_ids": rel["unknown_ids"]}
        names = sorted({n for r in kept for n in aspm.rules[r].atoms} - aspm.action_predicates)
        descr = {n: rel["grounded"].get(n) or aspm.descriptions.get(n, "") for n in names}
        plan = None
        if names:
            plan = planner(aspm, names, descr, kept, history, a_text, matched, cfg.planner_effort, cfg.aux_effort, meter,
                           max_turns=cfg.max_turns)
            current.update(plan["values"])
        rec["planner"] = None if plan is None else {k: plan[k] for k in (
            "values", "forced_unknown", "turns", "stopped", "completed", "tool_errors", "rejected_assignments",
            "n_search", "n_binary_check", "final_text", "transcript")}
        rec["grounded_descriptions"] = descr
        past = list(conv.trace)
        per_action = [mln.decide(aspm, kept, a, current, past, cfg.epsilon, cfg.gibbs_threshold) for a in matched]
        # counterfactual for the relevance-filter check: all circuit rules, unassigned predicates unknown
        cf = [mln.decide(aspm, circuit, a, current, past, cfg.epsilon, cfg.gibbs_threshold) for a in matched]
        rec["mln"] = per_action
        rec["no_filter"] = {"allowed": all(d["allowed"] for d in cf), "allowed_eps0": all(d["allowed_eps0"] for d in cf),
                            "margin": min(d["margin"] for d in cf),
                            "violated": sorted({r for d in cf for r in d["violated_by_action"]}, key=int)}
        allowed = all(d["allowed"] for d in per_action)
        # V_s: rules violated by the action in the most probable executing world; when the block comes from unknown
        # predicates (no rule false in that world), the rules the action violates with probability > 0 (I-P2-4, B1)
        ids = sorted({r for d in per_action if not d["allowed"]
                      for r in (d["violated_by_action"] or list(d["at_risk"]) or d["false_in_best_world"])}, key=int)
        violated = [{"rule_id": r, "description": aspm.rules[r].description, "logic": aspm.rules[r].logic} for r in ids]
        rec.update({"margin": min(d["margin"] for d in per_action), "allowed_eps0": all(d["allowed_eps0"] for d in per_action),
                    "violated_rules": violated,
                    "unknown_predicates": sorted(n for n in names if current.get(n) is None)})
        if allowed or cfg.record_blocked_steps:
            conv.trace.append(current)
        if not allowed:
            sysmsg, user = render("explain", action=a_text,
                                  rules="\n".join(f"[{v['rule_id']}] {v['description']} (logic: {v['logic']})" for v in violated))
            out = structured(meter, stage="explain", system=sysmsg, user=user, schema=EXPLAIN_SCHEMA, schema_name="explanation",
                             effort=cfg.aux_effort)
            rec.update({"explanation": out["explanation"], "feedback": out["feedback"],
                        "feedback_text": render_feedback(violated, out["explanation"], out["feedback"])})
        return self._finish(rec, meter, t0, allowed=allowed, reason=None)

    def commit(self, conv: Conversation, rec: dict) -> None:
        """Record a blocked step that is executed anyway (cap override) as taken."""
        if not rec["action_allowed"] and not self.config.record_blocked_steps:
            conv.trace.append(rec["trace_position"])

    def _finish(self, rec, meter, t0, allowed, reason, unmapped=False):
        rec.setdefault("margin", None)
        rec.setdefault("allowed_eps0", allowed)
        rec.setdefault("violated_rules", [])
        rec.update({"action_allowed": allowed, "epsilon": self.config.epsilon, "reason": reason, "unmapped": unmapped,
                    "seconds": round(time.time() - t0, 1), "usage": meter.summary(), "calls": meter.calls})
        return rec
