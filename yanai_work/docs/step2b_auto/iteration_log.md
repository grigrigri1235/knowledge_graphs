# Step 2b: iteration log (development on airline only)

Rules for iterating:
- Prompts and validators change only to fix **failure patterns** that are visible across several clauses or rules.
- Gold rule text is never pasted into prompts.
- No change targets an individual gold rule.

Metrics during development:
- **E1:** automatic.
- **E2 proxy:** the gpt-5-nano judge in `eval/e2_rules.py proxy`.
- **Validator pass rates:** per stage, from the run manifest.
- **Critic statistics.**

Manual E2/E3 labels are produced only for the final airline runs (with and without addendum) and for the retail held-out run.

Iterations come in pairs: changes made after run *i* are what run *i+1* tests.

---

## Iteration 0 (run `dev_it0`): baseline

Configuration:
- prompts as first written;
- reasoning effort: S1, S2 and S4 `medium`; the rest `low`;
- k = 3;
- thresholds: sentence coverage 0.5, S3 0.88, S5 0.85.

**S1 findings:**

| Section | Attempts | Problems |
|---|---|---|
| Airline Agent Policy | 2 | 2 uncovered sentences on attempt 0 (current time, scope sentence); fixed by repair |
| Domain Basic | 2 | 1 non-verbatim quote ("an reservation" → "a reservation": nano corrected the source's grammar); fixed |
| Book flight | 3 | 7 non-verbatim quotes on attempt 0. **All had a leading list marker `- `**. After 2 repairs, 1 still failed and was dropped. |
| Modify flight | 1 | — |
| Cancel flight | 2 | 4 quotes with a leading `- `; fixed |
| Refund | 3 | 1 quote with a leading `- `, never fixed; clause dropped |

E1: normative recall 57/61, precision 41/44, kind accuracy 0.95. Missed gold clauses:
- AIR-BOOK-02b and AIR-COMP-03b were **dropped because of the list marker**;
- AIR-DOM-04c and AIR-DOM-04e ("…, cannot be booked") were segmented, but labelled `fact`, because the sentence mixes a fact with a constraint.

**Changes made for iteration 1** (patterns, not individual rules):
1. **S1 validator:** strip leading list markers (`- `, `* `, `• `, `1.`/`1)`) from quotes before the verbatim check (`stages.LIST_MARKER`). This is deterministic and fixes a whole class of rejections.
2. **S1 prompt**, two generic rules:
   - "If one sentence both describes a fact and states what can or cannot be done, emit a fact clause and a separate normative clause; they may share the quote."
   - "Do not include list markers in quotes."

**Findings in S2–S8 (iteration 0):**

| Stage | Observation (pattern) | Evidence |
|---|---|---|
| S0 | `think` voted `write` (2/3) because its description says "append the thought to the log". `transfer_to_human_agents` was `write` because the first prompt's definition included "transfers something". | `stage0_tools.json` votes |
| S2 critic | **Noisy and destructive.** Required transformations were flagged as defects: "you should" → "must" as a modality loss, rewriting to the agent subject as "added content". The critic also demanded verbatim wording. Revisions often made rules *worse*: drift and invented phrasing. Only 12/44 clauses passed first time, 20/44 at the end, and 24 used all 3 rounds. | Failed checks: modality 51, conditions 46, added content 34, coverage 33. Example clauses: S0-C07, S4-C05. |
| S2 cost | The critic produced 631k of 1.2M output tokens. The stage took 23 min. | manifest |
| S2 rules | **Wrong `related_tools`.** Rules were attached to the tool that *obtains* information, or to `respond_to_user`, instead of the action whose invocation violates the rule. Examples: "payment methods must be in the profile" → `get_user_details`; "first obtain the user id" → read tools + `respond_to_user`. Tool names also leaked into descriptions ("must respond_to_user to …"). | `stage2_rules.json` |
| S3 | Works: 114 → 95 rules, 27 clusters checked, coverage unchanged, plausible merges. | `stage3_pruned.json` |
| S4 | All 95 valid; 17 needed repair (undefined predicates, function-call names `x(reservation_id)`, action renamed). Semantic problems: action restated as a trigger (`this_action AND is_update_action`), and "rule satisfied" predicates (`unconditional_rules_satisfied`). | `stage4_logic.json` |
| S5 | 170 → 148 predicates; merges correct (tier synonyms, "obtained before" variants). | |
| S6 | 180 ASPM rules, mostly replication through over-broad `related_tools`. Validator: **PASS**. | `validate_aspm.py --auto` |
| S7 | `value_source` was all three sources for 132/148 predicates, so it carried no information. | `predicates.json` |
| S8 | 165 block / 15 warn. Message-only rules were judged by their content ("a refund would change state") and blocked. | `stage8_enforcement.json` |
| Cost | 1,276 calls, 1.21M input / 2.27M output tokens (2.04M reasoning), ~56 min wall. | manifest |

**Changes made for iteration 1** (all generic):
1. **S2 extract / revise prompts:**
   - `related_tools` = the actions at which a violation would happen. For "first do X / only if C" rules these are the tools that perform the task, not those that obtain information. `respond_to_user` only for rules about what the agent says.
   - No tool names in descriptions.
   - "You should / have to / need to" (to the agent) = must.
2. **S2 critic prompt:**
   - an explicit list of ALLOWED transformations (agent subject, should→must, resolved references, splitting, "cannot" → "must not");
   - judge meaning, not wording;
   - never ask for verbatim copying.

   The revise prompt ignores findings that would undo allowed transformations.
3. **S2 code:** the final rule set is the reviewed version with the **fewest failed checks** (ties → earliest), so the loop cannot degrade rules. The critic runs at **low** effort (cost).
4. **S0 prompt:** write = "changes state that the environment stores and that persists". The agent's own notes and conversation hand-offs do not count.
5. **S4 prompt:**
   - do not restate the action as a condition;
   - no "rule is satisfied" predicates;
   - plain identifiers.
6. **S7 prompt:** `value_source` = the MINIMAL set of sources needed, with a definition per source.
7. **S8 prompt:** "if none of the constrained actions is a write tool, a violation cannot change persistent state → warn". This follows directly from the block criterion.
8. **Runtime:** 16 workers instead of 8.

**Dev metrics, iteration 0:** E1 normative recall 57/61, precision 41/44, kind accuracy 0.95. **E2 proxy:** covered 34 / partial 23 / incorrect 0 / missing 4. Cost: 1,276 calls, 2.27M output tokens, ~56 min.

---

## Iteration 1 (run `dev_it1`)

Results:
- **S1:** all sections valid; 4/6 sections needed no repair, against 1/6 before.
- **E1:**
  - normative recall **57 → 60/61** (61/61 ignoring kind);
  - precision 41/44 → 45/48;
  - kind accuracy 0.95 → 0.87 (the fact/normative split of mixed sentences creates more pairs whose best match has the other kind).
- **S2:**
  - critic first-pass 12/44 → **25/48**; final 20/44 → **38/48**;
  - selected round 0 for 31 clauses, round 1 for 14, round 2 for 3;
  - critic output tokens 631k → **88k**;
  - stage time 23 → **7 min**.
- **`related_tools`:** much better, but 15 rules still list `get_reservation_details` and 12 list `get_user_details`.
- **S7:** `value_source` became informative. 47 predicates are tool_outputs-only, 29 call_args-only, 20 dialogue-only, 33 call_args+tool_outputs; only 5 list all three (before: 132/148).
- **S8:** 134 block / 77 warn (before: 165/15).
- **Totals:** 1,287 calls, 1.73M output tokens, **26 min**. Validator: PASS.
- **E2 proxy:** covered **40** / partial 19 / incorrect 0 / missing 2 (iteration 0: 34 / 23 / 0 / 4).

New patterns seen in S2:
1. **Instruction leakage.** The output-format instruction "describe actions in words, no tool names" came back as policy rules ("The agent must not name tools when describing actions to the user").
2. **Permission → obligation.** "Business flights can always be cancelled" became "The agent must cancel business flights"; "the user can modify passengers" became "The agent must allow modifying passengers".
3. **Context spill-over.** The extraction for one clause also emits rules for its neighbours (one preamble clause produced 8 rules), feeding S3 clusters of 9–10 rules.
4. **Unresolved meta-references.** "The API does not check these…" became "The agent must make sure the rules apply before calling the API" (8 occurrences).
5. **S0 inconsistency at low effort.** For `think` the rationale says "without changing external state" but the vote is `write` (2/3). `transfer_to_human_agents` was also `write` (2/3).

**Changes made for iteration 2:**
1. **S2 extract prompt:**
   - a permission never becomes an obligation;
   - write rules for the TARGET clause only;
   - resolve meta-references into the concrete requirements;
   - output-format notes are explicitly marked as "not policy content".
2. **S2 revise and critic prompts:** the same three points as critic checks (self-containment, scope, permission → obligation counts as a modality failure).
3. **S0** reasoning effort low → medium (42 cheap calls).

---

## Iteration 2 (run `dev_it2`)

Results:
- **S0:** `think` → utility (2/3). `transfer_to_human_agents` stays write (3/3) even at medium effort. That is a defensible reading (an escalation changes the conversation state), so it is **left as is** rather than tuned towards the gold label.
- **S1:** identical to iteration 1 (cache hit; prompt unchanged).
- **S2:**
  - 129 → **94 rules**; critic first-pass 25 → **32/48**, final 38 → **43/48**;
  - instruction leakage: **0** (was 2);
  - meta "rules apply" rules: 8 → 5;
  - permission → obligation: mostly gone ("must not block cancellation for business flights"); 2 cases remain ("must allow cabin changes …").
- **Later stages:** S3 94 → 85 rules (17 s); 174 ASPM rules; 137 predicates; 140 block / 34 warn.
- **Totals:** 1,109 calls, 1.28M output tokens. Validator: PASS.

Remaining dominant pattern:
- **Prerequisite rules attached to the wrong action.** "List the details / get confirmation before acting", "first obtain the user id", "collect the first name for each passenger" still go to `respond_to_user` or to lookup tools, and some to `calculate` ("charge 50 dollars per extra bag" → calculate). Such rules then do not sit in the circuits of the write tools they protect.

**Change made for iteration 3** (S2 extract / revise / critic prompts, generic):
- for "ask / list / collect / obtain / confirm X before (or for) a task" rules, the constrained tools are the ones that PERFORM the task;
- never `respond_to_user`, never lookup tools;
- read and utility tools are constrained only by rules about looking up or computing itself.

**Dev metrics, iteration 2:** E2 proxy covered 40 / partial 18 / incorrect 2 / missing 1 (flat against iteration 1). Rule count and noise went down; coverage did not change.

---

## Iteration 3 (run `dev_it3`)

Results:
- **S2:** 120 rules (iteration 2: 94; the variance between runs is large because the deployment allows no seed); critic first-pass **37/48**, final **45/48**.
- **`related_tools` did not improve.** Rules list `get_reservation_details` 22× (iteration 2: 9×), `get_user_details` 10×, `calculate` 7×. Prompt guidance for tool attribution inside the rule-writing call **plateaued**: nano does too many things in one call.
- Validator: PASS. 193 ASPM rules; 114 block / 79 warn.

**Change made for iteration 4: new stage S3b, tool attribution as its own small call** (the brief's "many small calls + k=3 vote" pattern):
- After S3, every rule gets a focused call: "at which actions would a violation of this rule occur?". The prompt covers prerequisite rules, argument limits, message rules and all-action rules. It is generic and has no domain words (the test checks).
- **Voting:** the 3 S3b samples plus the S2 attribution (written with the full clause context) form 4 voters. A tool is kept if ≥ 2 of 4 name it; `*` needs 2 of 3 S3b samples.
- **Trial on iteration 3's S3 rules:**
  - S3b alone changed 68/107 attributions. Prerequisite rules moved to the write tools that perform the task ("obtain the reason before cancelling" → the cancellation tool; payment limits → the booking tool; "$50 per extra bag" no longer on `calculate`).
  - S3b alone also over-included read tools for "as the first step" rules, and moved 3 compensation rules to `respond_to_user` only.
  - With 4 voters, the compensation rules keep the write tool plus `respond_to_user`. Over-inclusion is limited to a few "first step" rules, which only adds them to read circuits.

**Dev metrics, iteration 3:** E2 proxy covered 39 / partial 20 / incorrect 1 / missing 1.

---

## Iteration 4 (run `dev_it4`): S3b added

Results:
- **S0–S3:** identical to iteration 3 (cache).
- **S3b + S4–S8:** 277 ASPM rules (circuits are larger because prerequisite rules now sit on every write tool they protect); 162 predicates; 217 block / 60 warn. Validator: **PASS**.
- **E2 proxy:** covered **41** / partial 17 / incorrect 2 / missing 1.
- **E4 circuit recall, using the proxy's matched rules as the match set** (a proxy for E4):

| | iteration 2 | iteration 3 | iteration 4 (S3b) |
|---|---|---|---|
| micro recall over the 6 gold write tools | 0.731 | 0.731 | **0.940** |
| `book_reservation` | 11/20 | 11/20 | 17/20 |
| `update_reservation_flights` | 8/13 | 9/13 | 12/13 |
| `update_reservation_passengers` | 7/7 | 5/7 | 7/7 |
| auto circuit size, `book_reservation` | 15 | 20 | 41 |

---

## Summary of development (E2 proxy, airline)

| Iteration | covered | partial | incorrect | missing | output tokens | wall time |
|---|---|---|---|---|---|---|
| original extraction (Step 1, manual audit) | 23 | 31 | 2 | 5 | — | — |
| 0 | 34 | 23 | 0 | 4 | 2.27M | 56 min |
| 1 | 40 | 19 | 0 | 2 | 1.73M | 26 min |
| 2 | 40 | 18 | 2 | 1 | 1.28M | ~25 min |
| 3 | 39 | 20 | 1 | 1 | 1.45M | ~10 min (S0/S1 cached) |
| 4 | 41 | 17 | 2 | 1 | +0.75M (S3b–S8) | — |

## Freeze decision
- Rule content (E2 proxy) has been flat for three iterations, at about 40/61 covered.
- The remaining gains came from attachment (E4: 0.73 → 0.94).
- Remaining failures are model-level (see the report).

**The pipeline as run in iteration 4 is frozen as `auto-pipeline-v1`.**

### Post-freeze reproducibility fix (before any held-out run)

The first frozen airline run (`v1`) did not reproduce `dev_it4` exactly. 4 of 1,602 calls missed the cache. A rerun with a fully warm cache still changed one predicate's `value_source`. There were two causes, both **non-determinism in Python, not in the model**:
1. `aspm_tool.validate_rule_consistency` (runtime code, not modifiable) formats its error messages from Python *sets*. Their order depends on hash randomisation, and the messages go into S4 repair prompts, so prompts and cache keys varied between processes. Fix: `common.logic_errors` re-derives the check with sorted names. A new test runs it under 4 `PYTHONHASHSEED` values and requires identical output.
2. Vote fallbacks used `Counter.most_common(1)` on counters filled by iterating sets, so ties were broken arbitrarily. Fix: `stages._top`, a deterministic tie-break (highest count, then name).

These fixes change no prompt and no decision rule. The tag `auto-pipeline-v1` (local, never pushed, created minutes earlier and not yet used for any held-out run) was **re-created** on the fixed code.

Verification: `v1`, `v1_repro` (`PYTHONHASHSEED=22`) and `v1_repro2` (`PYTHONHASHSEED=33`) produce byte-identical `aspm.json` and `predicates.json`; the repro runs are 1,605/1,605 cache hits. `v1` is published to `aspm_auto/airline/`.
