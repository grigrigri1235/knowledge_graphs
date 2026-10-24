=== SYSTEM ===
You answer yes/no questions about a conversation and the agent's current action, using only the conversation and tool outputs shown. Answer unknown when they do not determine the answer.
=== USER ===
Conversation: {history}
Current action: {action}
Questions:
{questions}
Return {"answers": [{"id", "flag": "yes"|"no"|"unknown", "explanation"}]}.
