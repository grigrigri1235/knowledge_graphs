Example from an unrelated domain (a library); do not copy its content.
Policy: [S1] Loans last 21 days. [S2] A loan can be renewed at most twice. [S3] Overdue loans cannot be renewed unless the member pays the late fee first. [S4] Before renewing, the agent must tell the member the new due date.
Tools: renew_loan(loan_id), pay_fee(member_id, amount), get_loan(loan_id)
Rules:
- R1: action renew_loan, condition "loan_renewed_fewer_than_two_times" (source tool_outputs)
- R2: action renew_loan, condition "NOT loan_is_overdue OR late_fee_paid" (sources tool_outputs; tool_outputs)
- R3: action renew_loan, condition "new_due_date_told_to_member" (source agent_messages)
Dispositions: S1 fact; S2 rule [R1]; S3 rule [R2] (its "unless" clause is the OR alternative); S4 rule [R3].
