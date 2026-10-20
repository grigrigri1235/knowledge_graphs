"""Component C: actionable feedback for a blocked step (deterministic text, no LLM call).

For every violated rule it names the requirement and lists each of its condition predicates with its value
(true / false / not established) and the judge's evidence. Then it says what to do: establish what is missing (the
predicate's evidence source decides how: ask the user, look it up, tell the user, change the arguments), or, for a
rule that is violated as things stand, not to repeat the same action and to tell the user which requirement
prevents it.
"""
from __future__ import annotations

from typing import Dict, List, Optional

HOW = {
    "user_messages": "ask the user and wait for the answer",
    "agent_messages": "first tell the user in a message",
    "tool_outputs": "look it up with a read-only tool",
    "call_arguments": "change the arguments of the call",
}


def _state(v: Optional[bool]) -> str:
    return "not established" if v is None else ("true" if v else "false")


def actionable(kind: str, name: str, violated: List[dict], aspm, current: Dict[str, Optional[bool]],
               judged: Dict[str, dict], predicates: Dict[str, dict]) -> str:
    what = "Your message was NOT sent to the user" if kind == "respond" else f"The {name} call was NOT executed"
    lines = [f"BLOCKED by policy guardrail. {what}, because these requirements are not met:"]
    missing, false = {}, []
    for v in violated:
        lines.append(f"- [{v['rule_id']}] {v['description']} (rule: {v['logic']})")
        names = sorted(aspm.rules[v["rule_id"]].atoms - aspm.action_predicates)
        for n in names:
            val = current.get(n)
            ev = judged.get(n, {}).get("evidence", "")
            lines.append(f"    {n} = {_state(val)}: {aspm.descriptions.get(n, '')}" + (f" (evidence: {ev})" if ev else ""))
            if val is None:
                for src in predicates.get(n, {}).get("source") or ["user_messages"]:
                    missing.setdefault(HOW.get(src, "find out"), []).append(n)
        if all(current.get(n) is not None for n in names):
            false.append(v["rule_id"])
    lines.append("What to do:")
    for how, ns in missing.items():
        lines.append(f"- Not established yet ({', '.join(sorted(set(ns)))}): {how}; then try again.")
    if false:
        again = "send the same message" if kind == "respond" else "repeat the same call"
        lines.append(f"- Rule(s) {', '.join(false)} are violated as things stand: do not {again}. Proceed only if the "
                     "requirement becomes satisfied (for example, after the user confirms or provides what is needed); "
                     "otherwise tell the user which requirement prevents this action and offer an allowed alternative.")
    return "\n".join(lines)
