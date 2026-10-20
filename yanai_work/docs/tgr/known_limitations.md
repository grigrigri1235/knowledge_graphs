# Known limitations of the TGR stage (generic improvements over ShieldAgent)

Dated entries. Limitations are documented, never patched by hand.

## L1. Domain Basic removal drops three constraint sentences from rule building (2026-10-19)

**Decision (advisors).** Every rule-building method, including the ShieldAgent P1 rebuild, reads the policy without
its "Domain Basic" section(s). The removal is generic (`exp_core/policy_filter.py`, heading given by the caller). The
agent's system prompt and the Direct guard still get the full original wiki. The removed text is quoted in
`p0_report.md` §4.

**Limitation.** The section is mostly descriptive, but three of its sentences are constraints that rule building now
never sees:

| domain | removed sentence | stated elsewhere in the policy? |
|---|---|---|
| airline | "If the status is "delayed" or "on time", the flight has not taken off, cannot be booked." | no |
| airline | "If the status is "flying", the flight has taken off but not landed, cannot be booked." | no |
| retail | "Exchange or modify order tools can only be called once." | modify: yes ("Modify items": "This action can only be called once"); exchange: only as the weaker "remind the customer to confirm they have provided all items to be exchanged" |

(Retail's "Generally, you can only take action on pending or delivered orders" is restated per action, so it is not
lost.)

**Consequences for evaluation.**
- A rule-based guard built from the filtered policy cannot block booking a non-available flight, or a second
  exchange call, on the strength of these sentences. Direct sees them, because it reads the full wiki. Comparisons
  between rule-based guards and Direct must keep this in mind.
- In practice the airline constraint matters little: no τ-bench tool exposes a non-available flight status
  (AGENTS.md §6), so search results only list available flights.
- The same section produced the defective P1 retail rule 32 ("no tool call after the first order tool call", from the
  once-only sentence). Its removal may therefore also remove false blocks. This is a confound for any ShieldAgent
  P1(luna) vs P1(nano) comparison.

**Not done.** The sentences are not restored or re-inserted into any rule-building input, and no rule is added for
them by hand.
