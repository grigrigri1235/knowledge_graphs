"""Rule writing (component B, with A's tool vocabulary), validation, duplicate removal and circuits.

One rule-writing call per policy (plus at most `max_repairs` format/consistency repair calls when the validator finds
problems). Flags:
  a: the actions are the agent's tools (+ "respond") and predicates carry an evidence source; otherwise the model
     names free action predicates, which are mapped to tools at runtime (ShieldAgent's vocabulary table + EXTRACT);
  b: restriction-only rules "<action> IMPLIES (<condition>)" with a disposition per sentence; otherwise general LTLf
     rules and no dispositions.
No rule is ever edited by hand or by code: invalid rules left after the repairs are dropped and reported.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from repro_core import ltlf
from repro_runtime.aspm import ASPM, Rule
from repro_runtime.calls import Meter

from method_tgr import llm, prompts
from method_tgr.policy_text import number_sentences

RESPOND = "respond"
SOURCES = ["call_arguments", "tool_outputs", "user_messages", "agent_messages"]
DISPOSITIONS = ["rule", "exception", "fact", "not_enforceable"]
NAME_RE = re.compile(r"[a-z][a-z0-9_]*\Z")


@dataclass(frozen=True)
class Flags:
    a: bool = True
    b: bool = True

    @property
    def label(self) -> str:
        return ("A" if self.a else "noA") + "+" + ("B" if self.b else "noB")


def schema(flags: Flags) -> dict:
    pred = {"type": "object", "additionalProperties": False, "required": ["name", "description", "source"],
            "properties": {"name": {"type": "string"}, "description": {"type": "string"},
                           "source": {"type": "array", "items": {"type": "string", "enum": SOURCES}}}}
    if flags.b:
        rule = {"type": "object", "additionalProperties": False,
                "required": ["id", "action", "condition", "description", "sentences"],
                "properties": {"id": {"type": "string"}, "action": {"type": "string"}, "condition": {"type": "string"},
                               "description": {"type": "string"}, "sentences": {"type": "array", "items": {"type": "string"}}}}
    else:
        rule = {"type": "object", "additionalProperties": False, "required": ["id", "logic", "description", "sentences"],
                "properties": {"id": {"type": "string"}, "logic": {"type": "string"}, "description": {"type": "string"},
                               "sentences": {"type": "array", "items": {"type": "string"}}}}
    disp = {"type": "object", "additionalProperties": False, "required": ["sentence", "disposition", "rule_ids", "reason"],
            "properties": {"sentence": {"type": "string"}, "disposition": {"type": "string", "enum": DISPOSITIONS},
                           "rule_ids": {"type": "array", "items": {"type": "string"}}, "reason": {"type": "string"}}}
    act = {"type": "object", "additionalProperties": False, "required": ["name", "description"],
           "properties": {"name": {"type": "string"}, "description": {"type": "string"}}}
    return {"type": "object", "additionalProperties": False,
            "required": ["actions", "predicates", "rules", "dispositions", "background_sentences"],
            "properties": {"actions": {"type": "array", "items": act}, "predicates": {"type": "array", "items": pred},
                           "rules": {"type": "array", "items": rule}, "dispositions": {"type": "array", "items": disp},
                           "background_sentences": {"type": "array", "items": {"type": "string"}}}}


def tool_list(tools: Sequence[dict]) -> str:
    lines = []
    for t in tools:
        f = t["function"]
        params = f.get("parameters", {}).get("properties", {})
        args = ", ".join(f"{k}: {v.get('description', v.get('type', ''))}".strip() for k, v in params.items())
        lines.append(f"- {f['name']}({args}): {f.get('description', '')}")
    lines.append(f"- {RESPOND}(content): send a message to the user.")
    return "\n".join(lines)


def instructions(flags: Flags) -> str:
    parts = [prompts.load("form_restriction" if flags.b else "form_general"), prompts.load("scope"),
             prompts.load("predicates_grounded" if flags.a else "predicates_plain"),
             prompts.load("dispositions" if flags.b else "no_dispositions")]
    if flags.a:
        parts.append('Set "actions" to an empty list.')
    return "\n\n".join(parts)


def render(policy_numbered: str, tools: Sequence[dict], flags: Flags):
    actions = prompts.fill(prompts.load("actions_tools"), tools=tool_list(tools)) if flags.a else prompts.load("actions_free")
    if flags.a:
        actions += '\nSet "actions" to an empty list.'
    user = prompts.fill(prompts.load("rules_user"), policy=policy_numbered, actions_section=actions,
                        form_section=prompts.load("form_restriction" if flags.b else "form_general"),
                        scope_section=prompts.load("scope"),
                        predicates_section=prompts.load("predicates_grounded" if flags.a else "predicates_plain"),
                        dispositions_section=prompts.load("dispositions" if flags.b else "no_dispositions"),
                        example=prompts.load("example_restriction" if flags.b else "example_general"))
    return prompts.load("rules_system"), user


# ---------------------------------------------------------------- validation

def logic_of(rule: dict, flags: Flags) -> str:
    return f"{rule['action']} IMPLIES ({rule['condition']})" if flags.b else rule["logic"]


def validate(out: dict, action_names: Optional[set], sentence_ids: List[str], flags: Flags) -> dict:
    """Returns {"rules": valid rules (with "logic", "actions"), "errors": [..], "invalid": {rule id: [errors]},
    "global_errors": [...]}. action_names: tool names (+ respond) under A; None under not-A (taken from out["actions"])."""
    errors, invalid, glob = [], {}, []
    if action_names is None:
        action_names = set()
        for a in out["actions"]:
            if not NAME_RE.match(a["name"]):
                glob.append(f"action name {a['name']!r} is not snake_case")
            action_names.add(a["name"])
    preds = {}
    for p in out["predicates"]:
        if not NAME_RE.match(p["name"]):
            glob.append(f"predicate name {p['name']!r} is not snake_case")
        elif p["name"] in action_names:
            glob.append(f"predicate {p['name']!r} has the name of an action")
        elif p["name"] in preds:
            glob.append(f"predicate {p['name']!r} is declared twice")
        else:
            preds[p["name"]] = p
    seen_ids, valid = set(), []
    for r in out["rules"]:
        errs = []
        if r["id"] in seen_ids:
            errs.append(f"rule id {r['id']} is used twice")
        seen_ids.add(r["id"])
        if flags.b and r["action"] not in action_names:
            errs.append(f"action {r['action']!r} is not one of the allowed actions")
        text = logic_of(r, flags)
        try:
            f = ltlf.parse(text)
        except ltlf.LTLfSyntaxError as e:
            errs.append(f"syntax error in {text!r}: {e}")
            f = None
        if f is not None:
            atoms = set(f.atoms)
            undeclared = sorted(atoms - set(preds) - action_names)
            if undeclared:
                errs.append(f"undeclared predicates {undeclared}")
            acts = atoms & action_names
            if flags.b:
                cond = ltlf.parse(f"({r['condition']})")
                if cond.has_temporal:
                    errs.append("temporal operator in a restriction condition")
                if set(cond.atoms) & action_names:
                    errs.append(f"action names inside the condition: {sorted(set(cond.atoms) & action_names)}")
            elif not acts:
                errs.append("the rule mentions no action")
        if errs:
            invalid[r["id"]] = errs
            errors += [f"rule {r['id']}: {e}" for e in errs]
        else:
            valid.append(dict(r, logic=ltlf.parse(text).canonical(), actions=sorted(set(ltlf.parse(text).atoms) & action_names)))
    if flags.b:
        disp_ids = [d["sentence"] for d in out["dispositions"]]
        missing = [s for s in sentence_ids if s not in disp_ids]
        dup = sorted({s for s in disp_ids if disp_ids.count(s) > 1})
        unknown = sorted(set(disp_ids) - set(sentence_ids))
        if missing:
            glob.append(f"sentences without a disposition: {missing}")
        if dup:
            glob.append(f"sentences with more than one disposition: {dup}")
        if unknown:
            glob.append(f"dispositions for unknown sentence ids: {unknown}")
        rule_ids = {r["id"] for r in out["rules"]}
        for d in out["dispositions"]:
            if d["disposition"] in ("rule", "exception"):
                bad = [x for x in d["rule_ids"] if x not in rule_ids]
                if not d["rule_ids"]:
                    glob.append(f"{d['sentence']}: disposition {d['disposition']} without rule ids")
                elif bad:
                    glob.append(f"{d['sentence']}: unknown rule ids {bad}")
    return {"rules": valid, "invalid": invalid, "global_errors": glob, "errors": errors + glob,
            "predicates": preds, "action_names": sorted(action_names)}


def dedupe(rules: List[dict]) -> (List[dict], List[dict]):
    """Exact duplicates only: same canonical logic."""
    seen, keep, dropped = {}, [], []
    for r in rules:
        if r["logic"] in seen:
            dropped.append({"rule": r["id"], "duplicate_of": seen[r["logic"]]})
        else:
            seen[r["logic"]] = r["id"]
            keep.append(r)
    return keep, dropped


def circuits(rules: List[dict]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for r in rules:
        for a in r["actions"]:
            out.setdefault(a, []).append(r["id"])
    return out


# ---------------------------------------------------------------- the build step

def build_rules(policy: str, tools: Sequence[dict], flags: Flags, effort: str = "medium", max_repairs: int = 2,
                max_output_tokens: int = 32000) -> dict:
    meter = Meter()
    numbered, sentences = number_sentences(policy)
    sysmsg, user = render(numbered, tools, flags)
    sch = schema(flags)
    action_names = ({t["function"]["name"] for t in tools} | {RESPOND}) if flags.a else None
    out = llm.structured(meter, stage="tgr_rules", system=sysmsg, user=user, schema=sch, schema_name="rule_set",
                         effort=effort, max_output_tokens=max_output_tokens)
    raw = [out]
    v = validate(out, action_names, [s["id"] for s in sentences], flags)
    repairs = []
    for _ in range(max_repairs):
        if not v["errors"]:
            break
        rs, ru = prompts.render("repair", errors="\n".join(f"- {e}" for e in v["errors"]), instructions=instructions(flags),
                                rules_json=json.dumps(out, ensure_ascii=False, indent=1))
        out = llm.structured(meter, stage="tgr_repair", system=rs, user=ru, schema=sch, schema_name="rule_set",
                             effort=effort, max_output_tokens=max_output_tokens)
        raw.append(out)
        repairs.append({"errors": v["errors"]})
        v = validate(out, action_names, [s["id"] for s in sentences], flags)
    rules, dups = dedupe(v["rules"])
    # numeric ids (the runtime orders rule ids numerically); the model's id is kept as "model_id"
    id_map = {r["id"]: str(i + 1) for i, r in enumerate(rules)}
    for d in dups:
        id_map.setdefault(d["rule"], id_map.get(d["duplicate_of"]))
    rules = [dict(r, model_id=r["id"], id=id_map[r["id"]]) for r in rules]
    dispositions = [dict(d, rule_ids=[id_map.get(x, f"dropped:{x}") for x in d["rule_ids"]], model_rule_ids=d["rule_ids"])
                    for d in out["dispositions"]] if flags.b else []
    used = set().union(*(ltlf.parse(r["logic"]).atoms for r in rules)) if rules else set()
    preds = {n: p for n, p in v["predicates"].items() if n in used}
    actions = {a["name"]: a["description"] for a in out["actions"]} if not flags.a else {}
    sent = {s["id"]: s["text"] for s in sentences}
    # facts the judge receives: the sentences the model lists, and under B also every sentence with disposition "fact"
    bg_ids = list(out.get("background_sentences", [])) + [d["sentence"] for d in dispositions if d["disposition"] == "fact"]
    background = [{"id": i, "text": sent[i]} for i in dict.fromkeys(bg_ids) if i in sent]
    return {"flags": {"a": flags.a, "b": flags.b, "label": flags.label}, "sentences": sentences, "policy_numbered": numbered,
            "rules": rules, "predicates": preds, "actions": actions, "action_names": v["action_names"],
            "circuits": circuits(rules), "dispositions": dispositions, "background": background,
            "validation": {"remaining_errors": v["errors"], "invalid_rules_dropped": v["invalid"],
                           "duplicates_dropped": dups, "repair_rounds": repairs,
                           "unused_predicates": sorted(set(v["predicates"]) - used)},
            "raw": raw, "usage": meter.summary(), "prompt_hashes": prompts.hashes()}


# ---------------------------------------------------------------- runtime structure

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
