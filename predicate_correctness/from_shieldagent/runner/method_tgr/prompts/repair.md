=== SYSTEM ===
You fix the format and consistency of a rule set for a policy guardrail without changing what the rules mean.
=== USER ===
The rule set below (JSON) was written from a policy, but a validator found these problems:
{errors}

Instructions that the rule set must follow:
{instructions}

Rule set:
{rules_json}

Return the complete corrected rule set (same schema). Change only what is needed to fix the listed problems; keep every other rule, predicate and disposition as it is.
