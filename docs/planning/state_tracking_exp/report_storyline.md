# Storyline for sections 4+ of the final report

Date 2026-10-22. Why: in the first version, "Where it still failed" and "Verdict" seemed to contradict each other, the
task splits were not explained, and some terms had no explanation.

## The problem
- The verdict said "accuracy: yes, safety: yes", and the failures section said "no gain". Both were true, but they
  answer different questions. The report never said which question each number answers.
- "Train", "validation" and "test" were used without saying what they are, or why the train result does not count
  as proof.
- These terms were used without being explained: pass^1, CI, paired Δ, gold v2, block precision, cap override,
  "readings", "scorable", Part numbers.

## The thread: three questions, answered in order
1. **Are the predicate values more accurate?** Offline test on saved conversations. **Yes**, clearly.
2. **Are the guard's decisions better?** Both tests. **Yes, where the tracker acts**, but it acts on only 1.3 % of
   the checks.
3. **Do more tasks get done?** Online test. **Not proven.** It is up on train, but train was used to study the
   tracker, and validation shows no gain.

**The verdict follows from 1–3:** the tracker is correct, but it changes too few decisions to move task success by
an amount we can measure.

Then "why the gain is small" explains the gap between 2 and 3: few decisions change, most blocks are about message
meaning, and much of the effect comes from the judge's cut-off view.

## New order (sections 4+)
4. How we tested: the two tests, the three task groups, the two agents, and the measures (each explained once)
5. Results:
   - 5.1 values;
   - 5.2 decisions;
   - 5.3 task success;
   - 5.4 examples
6. Verdict (the three answers in one table)
7. Why the gain is small, and what still fails
8. Limits of the measurement
9. Next steps

## Rules
- Each number appears once, with what it measures. The old "Key numbers" table is dropped, because it repeated
  section 5.
- No term without an explanation. Terms that are not needed (pass^3, block precision, cap override) are dropped.
- "Train result" is always said together with "validation result".
