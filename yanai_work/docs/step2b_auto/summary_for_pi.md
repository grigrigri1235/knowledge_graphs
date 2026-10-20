# Step 2b in one page: can the policy rules be written automatically?

*2026-10-15. Full report: `docs/step2b_auto/report.md`.*

## What we built
ShieldAgent checks every action an AI customer-service agent wants to take against a set of formal rules, and blocks the action if a rule is broken. In Steps 1–2 we wrote those rules **by hand** for two τ-bench policies (an airline and a retail shop). In Step 2b we built a pipeline that writes the rules **automatically** from the policy text, using a small, cheap model (gpt-5-nano). We tuned it on the airline policy. We then froze it and ran it once on the retail policy, which it had never seen, as an honest test.

## What works
- **It finds almost all the policy's requirements.** On the unseen retail policy, 36 of 46 requirements are captured correctly (78 %), 8 partly, 1 wrongly, and only 1 is missed. The earlier automatic tool scored 27 correct and 6 missed. On the airline policy used for tuning, it scored 49 of 61 (80 %), against 23 before.
- **It held up on unseen data.** Retail (78 %) is close to airline (80 %), so the tuning did not simply memorise the airline policy.
- **It is cheap and quick.** One policy takes about 20–25 minutes and about 1,600 model calls.
- **Checks pass.** We verified that the retail test used exactly the frozen code, that the pipeline never reads the hand-written answers, and that its output loads into the existing ShieldAgent code.

## What doesn't
- **Its rule sets are too big and too strict to use as a shield yet.** It writes 2–5 times as many rules per action as the hand-written version. Some rules are wrong in a way that blocks correct behaviour every time. Three causes stand out:
  - Descriptions of *what happens after* an action became requirements. For example, "the order status will change to 'return requested'" became a rule that the status must already be 'return requested' before the return is made.
  - Statements of what the agent *may* do became the only thing it is allowed to do.
  - Some rules were attached to the wrong actions.
- On our reading, the retail rules would block **every** cancel, modify, return and exchange, and the airline rules every cancellation, compensation and flight change. Our coverage score did not reveal this, because it asks whether each requirement is present, not whether extra rules do damage.
- **The automatic quality checker is not trustworthy.** An AI judge that grades the rules agrees with careful manual grading only slightly better than chance (agreement statistic κ ≈ 0.1 on a 0–1 scale). Manual grading remains necessary.
- **Extra "interpretation notes" did not help.** One of five notes was applied correctly. One meant for the retail shop leaked into the airline rules and created a rule that can never be satisfied.

## Key numbers
| | Hand-written (gold) | Automatic, retail (unseen) | Automatic, airline (tuned) |
|---|---|---|---|
| Requirements captured correctly | 100 % (by definition) | **78 %** (earlier tool: 59 %) | **80 %** (earlier tool: 38 %) |
| Rules checked per action (average) | ≈ 11 | ≈ 33 | ≈ 33 |
| Questions the AI judge must answer per action | ≈ 3 | **≈ 45–50** | ≈ 50 |
| Actions that would be blocked even when correct | none known | 6 of 7 action types | 3 of 6 action types |

## What happens next
1. **Step 3 (runtime) starts with the hand-written rules.** They are reliable, so any problem we see will be in the runtime machinery, not in the rules.
2. The automatic rules then become the comparison condition. We will run them unchanged, plus a "warn only" variant, to measure how often they would have wrongly blocked.
3. **Decision needed:** whether to fix the pipeline first. The fixes are mostly simple automatic checks: drop after-the-fact rules, keep permissions from becoming restrictions, and test that each action can still pass. A fixed version would need a new unseen policy to test it fairly, because the retail test has now been used.
