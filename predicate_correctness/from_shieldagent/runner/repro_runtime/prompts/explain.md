=== SYSTEM ===
You explain the decisions of a policy guardrail for an agent.
=== USER ===
Agent's action: {action}

Violated rules:
{rules}

Given the agent's action and the violated rules, write (1) a one-sentence explanation of why the action violates them and (2) one sentence of feedback on what the agent should do instead. Do not invent policy content beyond the rules.
Output: {"explanation": "...", "feedback": "..."}
