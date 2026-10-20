Rule form (restriction rules only). Every rule restricts exactly one action and has the form
    <action> IMPLIES <condition>
where <condition> is a boolean formula over condition predicates (AND, OR, NOT, parentheses) that states what must hold at the moment the action is taken for the action to be allowed. Return the action in "action" and the formula in "condition"; the rule is "<action> IMPLIES (<condition>)". No temporal operators and no action names inside a condition.
- A prohibition ("never do X when C") becomes "X IMPLIES NOT c".
- An obligation tied to an action ("before X the agent must do or obtain Y") becomes a precondition on that action: "X IMPLIES y_happened_before", with a predicate stating that Y happened earlier in the conversation.
- A permission or an exception ("X is allowed if E", "unless E", "except when E") is folded into the restriction on the same action as an OR alternative: "X IMPLIES (c OR e)". Never drop an exception and never write a permission as a rule of its own.
- If a requirement applies to several actions, write one rule per action. If an action has several independent requirements, write one rule per requirement.
- Sentences that only describe facts, explain what a tool does, or give background produce no rule.
- Write a rule only if its condition can be decided at the moment of the action from the conversation so far (the user's messages, the agent's messages, earlier tool calls and their outputs) and the arguments of the pending action. If a requirement cannot be checked from these, write no rule for it.
