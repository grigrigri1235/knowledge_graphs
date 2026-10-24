=== SYSTEM ===
You map an agent's tools to the abstract actions named in a safety policy model.
=== USER ===
Agent tool (JSON schema): {tool}

Abstract action predicates of the policy model (name: description):
{action_predicates}

List every action predicate that an invocation of this tool can be an instance of, including generic ones (e.g. "making a tool call", "updating a booking"). Return [] if none.
Output: {"action_predicates": [names]}
