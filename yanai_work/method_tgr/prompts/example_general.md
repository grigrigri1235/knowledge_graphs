Example from an unrelated domain (a library); do not copy its content.
Policy: [S1] Loans last 21 days. [S2] Overdue loans cannot be renewed unless the member pays the late fee first. [S3] After a renewal the agent must tell the member the new due date.
Rules:
- R1: "ALWAYS ((renew_loan AND loan_is_overdue) IMPLIES late_fee_paid)"
- R2: "ALWAYS (renew_loan IMPLIES EVENTUALLY due_date_told_to_member)"
