# Review of the plan before implementation

Date 2026-10-21. Status: answered. The resulting changes are in `plan_changes_v2.md`, and are applied to the plan.

## Verdict
- The plan fits our discussion:
  - it changes nothing in `~/ShieldAgent`, and copies what it needs into a separate folder;
  - the state comes from tool outputs only;
  - code computes the values it can, and the LLM is not trusted without a person's review;
  - it makes no LLM calls.
- It is almost ready. Five holes should be fixed first (section 1).
- Three limits should be written down, so nobody expects more than the plan can show (section 2).

## 1. Holes (suggested fixes)
| # | hole | why it matters | fix |
|---|---|---|---|
| H1 | **"Not seen" can mean false or unknown.** Many TGR predicates say "Earlier tool output establishes X". If no tool showed X, this predicate is **false**, not unknown. The plan always says unknown. | An unknown value blocks, so the tracker could add wrong blocks. | Part 5: for each lookup, state what "not seen" gives (false or unknown), following the predicate's description. |
| H2 | **Unknown from the tracker.** Part 8 keeps a tracker "unknown" as unknown, even when the judge had a value. | Same: more unknowns mean more blocks. | Part 8: report two versions: (a) tracker unknown stays unknown; (b) tracker unknown → use the judge's value. |
| H3 | **The one-line format may be too small.** Some predicates need sums over items (price difference, order total) or values nested inside objects (a gift card's balance inside the user's payment methods). | Lookups that cannot be written fall back to the judge, and coverage drops. | Part 5: also allow `sum`, simple list comprehensions, and `[...]` indexing on dicts and lists. Still checked by the validator. |
| H4 | **The review of the lookups needs Python reading.** You said you did not look at the Python details. | A review that skips the Python does not protect us from my mistakes. | Part 5: next to each lookup, a plain-language line ("true if the order in the call has status pending"), plus 2–3 saved steps where it gives true, false and unknown. You check those, not the code. |
| H5 | **No early stop.** If code-type predicates cause few blocks, Parts 4–8 cost effort for little gain. | We know this risk already (section 2, L1). | After Part 3: a go / no-go point. Count how many blocks involve a code-type predicate. If fewer than about 20 % in both runs, stop or change direction. |

## 2. Limits to state clearly
- **L1: Most TGR blocks come from conversation predicates.**
  - The most frequent causes are "agent reminded the user to include all items", "user explicitly confirmed" and
    "details listed".
  - The tracker does not compute these. Mixed predicates (for example "user selected the payment method", or "tool
    output **or user message** establishes …") also stay with the judge.
  - So the share of decisions the tracker can change is limited. Examples it can change: `user_authenticated`
    (106 blocks in the gpt-5-nano retail run), gift card balance, basic economy, segments unchanged.
- **L2: τ-bench already rejects some wrong actions.** For example, cancelling an order that is not pending fails in
  the tool itself. The gain from code is larger for rules the tools do not check (airline: cancellation within 24
  hours, no flown segments, baggage counts, basic economy).
- **L3: The plan cannot show a gain in task success.** It measures values and single decisions on saved steps.
  - To claim "better than TGR", we need new conversations with a guard that uses the tracker, compared with frozen
    TGR and Direct.
  - That is listed under "not in this plan", and needs a copy of the conversation code (harness) in our folder,
    plus LLM costs.

## 3. Will it improve on TGR?
My honest expectation:
- **Likely:**
  - code-type values become exact and the same on every run;
  - fewer LLM decisions are needed;
  - each value has a clear reason (the object or event it used).

  If all predicates of a tool are code types, that tool needs no judge call at all, which saves cost and time.
- **Possible:** fewer wrong blocks, and some caught violations, on the airline rules the tools do not check. This is
  most visible with the gpt-5-nano agent.
- **Unlikely in this plan alone:** a measurable gain in task success. Too few of TGR's blocks come from code-type
  predicates (L1), and the gpt-6-luna agent is blocked only 0.1–0.4 times per conversation.
- **Bigger gains** would need the next steps too:
  - narrow LLM questions for the conversation predicates;
  - splitting mixed predicates (A2).

Part 8 tells us how much of the gain is real before we spend money on new conversations.

## 4. Smaller notes
- **Part 1:** check that the `nano_train` TGR runs used the frozen rule set. The plan already says to check which
  rule set each run used.
- **Part 7:** both the tracker and the judge can be wrong in the same way. The 50 agreements in the sample check
  this.
- **Part 2:** the saved guard record has `trace_position` and `judge`, so Part 8 can run the decision again without
  rebuilding anything else.
