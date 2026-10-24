"""τ-bench trajectory → shielded steps (spec component 1: a_i, o_i, H_<i).

A τ-bench trajectory is a list of chat messages (system / user / assistant with optional tool_calls / tool).
Every assistant message yields steps:
  - one `tool_call` step per tool call (the message's text, if any, is the agent's accompanying thought);
  - one `respond` step if the message has text and no tool call (τ-bench's RESPOND action).
The observation o_i is the tool output matched by tool_call_id (or, for respond, the next user message).
History H_<i is every message before the assistant message that produced the step.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

RESPOND = "respond"


@dataclass
class Step:
    index: int                    # position among the trajectory's steps
    message_index: int            # index of the assistant message in the trajectory
    kind: str                     # "tool_call" | "respond"
    name: str                     # tool name, or "respond"
    arguments: Dict[str, Any]     # tool arguments, or {"content": text}
    agent_text: str               # text the agent produced in the same message
    observation: Optional[str]    # tool output / next user message (None if the trajectory ended)
    api_error: bool               # tool output starts with "Error"
    tool_call_id: Optional[str] = None
    history: List[Dict[str, Any]] = field(default_factory=list, repr=False)


def _args(raw) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        out = json.loads(raw) if raw else {}
        return out if isinstance(out, dict) else {"__value__": out}
    except (json.JSONDecodeError, TypeError):
        return {"__unparsed__": raw}


def steps_from_messages(messages: List[Dict[str, Any]], with_history: bool = True) -> List[Step]:
    steps: List[Step] = []
    for i, m in enumerate(messages):
        if m.get("role") != "assistant":
            continue
        text = m.get("content") or ""
        calls = m.get("tool_calls") or []
        history = messages[:i] if with_history else []
        for tc in calls:
            fn = tc.get("function") or {}
            obs = next((x for x in messages[i + 1:] if x.get("role") == "tool" and x.get("tool_call_id") == tc.get("id")), None)
            content = None if obs is None else str(obs.get("content", ""))
            steps.append(Step(len(steps), i, "tool_call", fn.get("name", ""), _args(fn.get("arguments")), text, content,
                              bool(content and content.startswith("Error")), tc.get("id"), history))
        if not calls and text:
            nxt = next((x for x in messages[i + 1:] if x.get("role") in ("user", "assistant")), None)
            obs = nxt.get("content") if nxt is not None and nxt.get("role") == "user" else None
            steps.append(Step(len(steps), i, "respond", RESPOND, {"content": text}, text, obs, False, None, history))
    return steps


def render_history(history: List[Dict[str, Any]], max_chars: Optional[int] = None) -> str:
    """Plain-text rendering of a history (for prompts); the system prompt (policy wiki) is omitted."""
    lines = []
    for m in history:
        role = m.get("role")
        if role == "system":
            continue
        if role == "user":
            lines.append(f"USER: {m.get('content') or ''}")
        elif role == "assistant":
            if m.get("content"):
                lines.append(f"AGENT: {m['content']}")
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function") or {}
                lines.append(f"AGENT TOOL CALL: {fn.get('name')}({json.dumps(_args(fn.get('arguments')), ensure_ascii=False)})")
        elif role == "tool":
            lines.append(f"TOOL RESULT ({m.get('name', '')}): {m.get('content') or ''}")
    text = "\n".join(lines)
    return text if max_chars is None or len(text) <= max_chars else "…" + text[-max_chars:]
