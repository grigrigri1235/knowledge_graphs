# Pre-registration: the paid online test (p14)

**Main idea:** we run the agent live with 5 guards on 99 hard tasks and ask one question: **is v3 (no full judge)
clearly worse than the old guard (frozen TGR)?** The rules below are fixed now, before any paid call. They do not
change after we see a result.

Frozen by sha256 (recorded in `output/eval_v3/preregistration.md` and in the sha table of `overview.md`). Any later
change goes in the change log at the end, with the time, the reason, and whether a result was already seen.

## 1. What runs
- **Agent:** the strong one only, gpt-6-luna for every role (profile `luna-dev`).
- **Tasks:** 99 hard tasks from `output/eval_v3/online_tasks.json`
  (sha256 `5f7b9b71c727531c29cbe1ab8e7189b4bcf67195bb5b78f02437f98d08baf96e`):
  - val 33 (23 retail, 10 airline): unseen, v3 was not designed on them;
  - train 66 (46 retail, 20 airline): seen.
  - Never the partner's test 66. The runner and the metrics refuse it.
- **Tries:** 3 per task.
- **5 arms**, all run on the same (task, try), next to each other:
  1. `none`: no guard;
  2. `direct`: the partner's Direct guard (one LLM call per step with the whole policy);
  3. `direct_facts_v3`: Direct plus a block of facts checked by code;
  4. `tgr_frozen`: the partner's frozen rule guard, run fresh;
  5. `tgr_tracker_v3`: v3 (code facts + tiny yes/no questions, no full judge).
- **Size:** B2 = 99 × 3 × 5 = 1,485 conversations. B1 (the smoke test, 10 conversations) is separate and not counted.

## 2. What we measure
- **Task success** = τ-bench's own reward in the episode line. No gold scorer.
- **Per task:** the average over its tries.
- **Only complete (task, try) groups count:** all 5 arms must have a line without error. A unit that fails is re-run
  once. If it fails again, its group is dropped from all arms. A task with no complete group leaves the test; the
  report gives how many.
- **The 95 % range:** bootstrap by task, stratified by domain (each resample draws the same number of airline and
  retail tasks), 10,000 resamples, seed 20261023, percentile range.
- Code: `scoring/v3_online_metrics.py` (sha256 `da44c1cbaf8547cb523661ab39d7d64e12691f1055b0cd349e21f7e3f2744a58`).

## 3. The main claim (all 99 tasks)
- **Number:** v3 − frozen TGR, task success, paired by task, mean over the 99 tasks.
- **Pass:** the lower end of the 95 % range is above **−0.10**. Then we say "v3 is not clearly worse than frozen TGR".
- **Fail:** otherwise. We report it as it is.
- Power (from the partner's saved train runs): if v3 equals frozen TGR, this passes 90-98 % of the time.

## 4. The leak check (val 33 vs train 66)
- The same test, on val 33 alone and on train 66 alone, shown side by side.
- If val's upper end is below train's point estimate, the report says **"possible leak"**.
- It is weak on purpose (val alone passes only 47-66 % of the time if v3 equals frozen TGR). It is a warning sign, not
  a pass mark.
- v3 does not change after p12's hold-out look. If it does, val is reported as seen.

## 5. Two secondary claims (all 99 tasks, the same bootstrap)
Val 33 and train 66 are also shown apart. There are two claims and no multiple-testing correction; the report says
so.
- **S1, do code facts help an LLM guard?** Direct + facts − Direct.
  - "facts help" if the lower end is above 0;
  - "facts hurt" if the upper end is below 0;
  - else "no clear difference".
- **S2, rules vs an LLM with the same facts:** v3 − Direct + facts.
  - "rules better" if the lower end is above 0;
  - "rules worse" if the upper end is below 0;
  - else "no clear difference".

## 6. Safety (pass mark)
- **0** v3 allows that τ-bench's own tool then refuses, at a check that maps to a v3 fact.

## 7. Reported, with 95 % ranges, no pass mark
- v3 vs no guard, and each guard's cost.
- Each arm's success.
- The 18 refusal tasks (no write expected; 6 val, 12 train): per arm, success, any write sent, any write accepted.

## 8. Reported only
Expected actions done, unwanted writes, "rule broken" (from v3's own facts and rules), the share of checks decided by
an LLM, cost per conversation, hand-overs, cap overrides, and whether the agent followed the advice of a block.

## 9. Stops during the run
They are lenient on purpose: they catch a broken run, not a normal one. A stop starts no new (task, try) group; open
groups finish all 5 arms, so the pairs stay complete.
- **Harm at halfway:** at 742 conversations (complete groups only), if v3 − frozen TGR ≤ −0.15. The main chat runs
  `scoring/v3_online_interim.py` (sha256 `acc21065ed202ef8ff3e02721adce219090657f7002d2cde39799a58863e2b1f`). At a true
  difference of 0 this fires with a chance under 0.001.
- **State errors:** the 3rd v3 check with an exception in the fact code. One or two are logged and reviewed after.
- **Cost:** an arm's mean cost per conversation, after 50 or more of its conversations, over its threshold (3 × its
  high estimate): none $0.023, Direct $0.044, Direct + facts $0.049, frozen TGR $0.041, v3 $0.061. Or one conversation
  over $0.25.
- **Errors:** 10 or more error lines that are also over 5 % of the lines, or 5 error lines in a row.
- **Money:** hard limits B1 $2, B2 $45 (B3 $20, only if approved). The v3 total cap is $95, counting p12 and every p14
  step. A new group starts only if the spend so far plus a reserve stays under the step limit. Code:
  `guard/soft_stop_v3.py` (sha256 `388552ddb483e803e000dbc0c4ea7461caa6c0a6cfc6496b42a13846a7feb29e`).
- **Manual:** the file `STOP` in the run folder, written by the main chat.

## 10. The smoke test (B1) passes when
- 2 tasks (1 retail, 1 airline) × 5 arms = 10 conversations, in their own folder;
- 0 error lines (1 content-filter error allowed);
- the mean cost is at most 3 × the point estimate.

## 11. What we will not do
- No v3 change between p12's hold-out look and the end of p14.
- No new pass mark, no new task subset as the headline, no new arm after a result is seen.
- B2v (more val tries) is not planned. B3 runs only if B2 is unclear, and only with its own approval.

## Code under this pre-registration
| file | sha256 |
|---|---|
| `guard/run_online_v3.py` | `a6834ea950366ae60bdffd5672f0754739b6c119a66181d11203209a98bea64c` |
| `guard/direct_facts_v3.py` | `2ffcf20494b9dd2b2b73f611adf589d8e5adea9a5eb654075d438fe72f90f61d` |
| `guard/soft_stop_v3.py` | `388552ddb483e803e000dbc0c4ea7461caa6c0a6cfc6496b42a13846a7feb29e` |
| `scoring/v3_online_metrics.py` | `da44c1cbaf8547cb523661ab39d7d64e12691f1055b0cd349e21f7e3f2744a58` |
| `scoring/v3_online_interim.py` | `acc21065ed202ef8ff3e02721adce219090657f7002d2cde39799a58863e2b1f` |
| `output/eval_v3/online_tasks.json` | `5f7b9b71c727531c29cbe1ab8e7189b4bcf67195bb5b78f02437f98d08baf96e` |

These shas can still change for bug fixes found by the p13 audit (step 6) or the dry runs (step 7), before B1. Each
such change is logged below, with the new sha. The rules in sections 1-11 do not change.

## Change log
| time (UTC) | change | why | result seen? |
|---|---|---|---|
| 2026-10-23 | first version, frozen | p13 step 5 | no (no paid online call yet) |
| 2026-10-23 12:46 | code shas only: `scoring/v3_online_metrics.py` da44c1cb… → 8f83b1f3…, `scoring/v3_online_interim.py` acc21065… → f30eba6d…; no rule in sections 1-11 changed | p13 audit A fixes: the saved-val lock by source path (also on `run` and the interim check); a missing arm is an error, not a silent drop; safety counted on every v3 line; interim state errors counted like the runner; warnings for mixed runs and under 99 tasks; a 95 % range for each arm's cost (section 7 asked for it) | no (no paid online call yet) |
| 2026-10-23 13:35 | code shas only: `guard/run_online_v3.py` a6834ea9… → 45ee28bd…, `guard/soft_stop_v3.py` 388552dd… → f83a04b4…, `guard/direct_facts_v3.py` 2ffcf204… → 3913e600… (version v3.p13.2); no rule in sections 1-11 changed. Section 10 gets one stricter B1 check (audit C): Direct + facts `facts_failure` = 0 and v3 state errors = 0 | p13 audits B and C: moved backups refused and counted; a failed tiny-question call becomes an error line (re-run, then dropped), not a v3 block or a state error; one process per shard (flock); judge cost on error lines; B1 fixed to retail:4 + airline:4, try 1; workers 1-8; the hard limit checked before each unit; the facts block text saved | no (no paid online call yet) |
| 2026-10-23 16:03 | new `docs/planning/tracker_v3/b2_reading_guide.md` (sha256 `8c55bd3eb7db6a80a8681a28690d7e54489d676f95ca68f0aabbb08f2b894620`): what each B2 number means (good / bad / unclear), written at the user's request | the user asked to define good and bad signs before the result | **no** (only line and error counts read: 148 of 1,485 lines, 0 errors); no pass mark changed |
| 2026-10-23 16:54 | section 11 ("B3 runs only if B2 is unclear") changed by the user: **B3 runs after B2 whatever B2 shows**, still only with its own paid approval. B3 is reported apart, as "many-step Stage A tasks, seen" (v3 was built on Stage A), and adds no pass mark and nothing to the main claim, the leak check, S1 or S2 | the user, 16:52 UTC ("i think we should do B3 after that"; view: on Stage A, v3 was tuned mainly to see the answers' form) | **no** final B2 result seen; only the pre-registered halfway check (16:29: go on) and line counts; no pass mark changed |
| 2026-10-23 19:08 | B3 build applied (user approval: "Approve build + B3 run (Recommended)"). Code shas: `guard/run_online_v3.py` 45ee28bd… → 0daab01d…, `scoring/v3_online_metrics.py` 8f83b1f3… → daafa873…, `scoring/v3_online_interim.py` f30eba6d… → a95d0989…; new `tests/test_v3_b3.py` e9bcec2c…, `output/eval_v3/b3_tasks.json` 0394a99a… (64 Stage A retail train tasks with 3+ expected actions). B1/B2 behaviour byte-identical (sandbox check). **B3 reading rule** (fixed before B3 starts): v3 − frozen TGR, task success, paired by task, mean over the 64 tasks, 1 try; 95 % range by bootstrap over tasks, 10,000 resamples, seed 20261023; "not clearly worse" if the lower end is above −0.10, else "not shown". A side result only: tasks seen in the build ("many-step Stage A tasks, seen"), never pooled with B2, never changes B2's verdict; S1, S2 and v3 − none reported only. Stops as B2 (section 9), halfway at 160 conversations; limit $20, cap $95. Check after the run: B3's guard input shas equal B2's, leaving out the runner sha and the 2 B3-only keys | the user, 17:25-19:06 UTC; B2 finished and scored first | B2 result seen (16:55); **no B3 outcome** exists yet; no B2 pass mark changed |
