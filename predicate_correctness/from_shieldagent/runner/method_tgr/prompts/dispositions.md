Coverage check. In "dispositions", give every sentence id of the policy exactly one disposition:
- "rule": the sentence is encoded by the listed rule(s);
- "exception": the sentence is a permission or exception folded into the listed rule(s) as an OR alternative;
- "fact": the sentence is descriptive and needs no rule;
- "not_enforceable": the sentence states a requirement that cannot be checked at the moment of an action (see "What a rule can check"), or is not about the agent's actions; give the reason.
"rule_ids" lists the rules for "rule" and "exception" and is empty otherwise; "reason" is one short sentence.
