=== SYSTEM ===
You search a conversation between a customer-service agent, a user and tools. Return only items that literally occur in it.
=== USER ===
Conversation: {history}
Current action: {action}
Query: {query}
Return {"items": [{"value", "turn", "evidence"}]}; [] if nothing matches.
