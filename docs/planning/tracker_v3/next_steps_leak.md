# After p14: fixing K2 without a data leak (brainstorm, 2026-10-23)

Written at the user's request ("fixing K2 based on that feedback is a data leak"). Nothing here is approved.

## The problem
- The K1/K2/K5/K13 fixes come from reading B2 and B3 conversations, our test data.
- If we fix v3 and test again on the same tasks, the test is no longer clean. We would have tuned on the test.
- This holds even for fixes that look general ("accept the payment id's digits"). We chose them because we saw them fail
  on the test.

## What stays as it is
- **v3's results stay final as reported** (B2: main claim PASS, possible leak; B3: v3 clearly worse on many-step
  tasks). The pre-registration does not change. No v3 change, no re-run of B2 or B3 as a "fixed" result.
- The diagnoses (B2 val, B3, tiny-question audit, Direct + facts) are labelled EXPLORATORY: they explain, they are not
  results.

## Options for a fixed version (v4)
| option | clean? | what it tests | cost / work |
|---|---|---|---|
| A. Leave it. Report v3 as is; the fixes go to "future work" | yes | nothing new | $0 |
| B. v4 with the fixes, tested on fresh tries of the same 99 tasks | **no**: the tasks were seen in the diagnosis | only "do the fixes help here" | about $16, small build |
| C. v4 tested on the partner's test 66 | yes, once | the same domains, unseen tasks | breaks the standing rule "never the partner's test group": only if the user lifts it and the partner agrees; it uses up their final test |
| D. v4 tested on a **new domain**: τ²-bench telecom (114 tasks) or τ³-bench banking | **yes** | the method on a new policy document (overview section 7, KR section 7) | big: a new build (facts, rules, questions) and a new harness; paid |
| E. τ²-bench retail / airline | **no**: mostly the same tasks as τ-bench v1 (with fixes) | — | — |

## How to keep any v4 honest
1. Write the fix list from **policy reasons**, before any new data: for example "a detail the system can check in the
   database is checked by code, not asked of the user"; "one confirmation may cover a listed batch"; "the block message
   names the missing detail".
2. Freeze v4 and its pass marks before the new test, as we did for v3.
3. Report v4 next to v3, never in place of it, and say the fixes were found on v3's test data.
4. Test only on data no one has looked at (option C or D).

## Recommendation
- Now: **option A**. v3 is done; its report says what failed and why.
- Next project step: **option D** (a new domain) is the real test of the method and has no leak. Option C only if the
  partner agrees.
