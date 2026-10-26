# Report flow fix: sections 2, 3 and 5

Goal: section 2 gives the idea as intuition only. Section 3 gives the method in depth. The v3 story leaves both and
moves to section 5, where v3 already lives. Nothing else changes.

## Part 1. Rewrite section 2 as "The idea, in plain words"
Draft text:

> ## 2. The idea, in plain words
> This section is intuition only. It says what we expect, not what we measured. Section 3 gives the exact method,
> section 4 shows the values are right, and section 7 gives the results.
>
> ### 2.1 Most facts are already written down
> Look at TGR's facts one by one. Most need no reading at all.
> - "The order is pending" is in the database.
> - "At most five passengers" is in the tool call.
> - "The agent looked the reservation up first" is in the list of tool calls so far.
> - "The user typed their email" is a plain search over the user's messages.
>
> A few lines of code can read these. Same input, same answer, no cost.
>
> ### 2.2 The rest needs one small question
> Some facts need meaning: "did the user agree?", "is this a complaint?". Code cannot judge that. But it does not
> need the whole conversation either. Code knows which one or two messages matter. For "did the user agree?", that is
> the agent's proposal and the user's replies after it. So an LLM reads only those messages and answers one yes/no
> question.
>
> ### 2.3 What we expect
> - Cheaper. Many checks are settled by code, with no LLM call. When a question is needed, it reads a few short
>   messages, not 24,000 characters.
> - Steadier. Code facts give the same answer every time. A question is short and narrow, with a stated default, so
>   there is less room for a random answer.
> - Fewer errors. Code reads the real data, so it cannot misread it.
> - Same rules. TGR's rules and decision code stay exactly as they are. Any change in behavior comes from the values
>   alone.
>
> One risk comes with it. A question that is too strict blocks good actions, and the agent can get stuck. Much of
> section 3 deals with that risk.
>
> We built this idea twice: v3 first, then v4. This report is about v4. Section 5 tells what v3 taught us. You do not
> need it to follow section 3.

Removed from section 2: the v3 numbers (old 2.2) and "what v4 had to do" (old 2.3). They move to section 5.

## Part 2. Strip v3 from section 3
- 3.6: new title "The listing check: details found by text matching". Drop "v3 asked an LLM (K2)...". The reason
  becomes: the tool call already holds every detail, so code can search for them.
- 3.11: keep the way-out rule. Drop the v3 numbers (45 of 90). The reason becomes: without it, one wrong block could
  trap the agent in a loop; a transfer changes no data, so allowing it is safe. The v3 numbers stay in section 5,
  lesson 5.
- 3.4 step 8: fix a wrong pointer, (3.8) to (3.9).

## Part 3. Section 5 becomes "v3, and what it taught us"
- 5.1 v3 in short: old 2.2 text, moved as is.
- 5.2 Six main lessons: the existing table and the two refinements.
- 5.3 The card number story: the existing 5.1.
- Fix pointers to 5.1 (now 5.3) in the report.

## Part 4. Regenerate the contents, check every internal pointer, back up the old file as draft6
