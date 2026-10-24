# Reading notes: how tracker v3 was planned and run, and where the time went

Written 2026-10-23 for the tracker v4 plan. $0, read-only. Sources: `docs/planning/tracker_v3/overview.md`, `p1.md`-`p14.md`,
`brainstorm.md` §11, `next_agent_prompt.md`, `lessons_learned.md` §2-6, `predicate_correctness/output/eval_v3/progress.md`,
`v3_freeze.md`, `p1_freeze.md`, `p13_audit_{A,B,C}.md`, `p13_verify_fixes.md`, `predicate_correctness/output/implementation_log.md`
(v3 part, lines 1581-2652), the v3 session scratchpad scripts (`b2_finish.sh`, `b2_auto.sh`, `b3_interim.sh`,
`run_v3_tests_parallel.sh`, `merge_overlays.py`). Git log is no help: the last commit is 2026-10-20, so all v3 times
below come from the implementation log and progress.md (UTC, 2026-10-22/23).

**The main idea in plain words.** v3 took about 21 h of wall time (approved 23:44, handed over 20:57). Only about
half of it was building. The rest was: API session-limit pauses (about 5 h), waiting for the user at stops (about
2.5 h in all, 1 h 41 min of it for B3), a serial fix loop on one tiny question found late (1 h 46 min), and reports
and docs rewritten many times after the results (about 4 h). The build itself already ran in parallel well. v4 can
be fast by (1) starting the runner/metrics/audit track at minute 0, (2) testing tiny questions with real answers as
soon as they exist, (3) asking for all approvals early with conditions, (4) chaining every after-run step in one
script kept in the repo, and (5) writing reports once, at the end, from generated numbers.

---

## 1. The v3 parts, one by one

Times are wall clock (start of first agent → part declared done). "Crit" = on the critical path.

| part | what it did | main inputs | main outputs (new files) | time | stop? | parallel? |
|---|---|---|---|---|---|---|
| plan check | 2 read-only reviewers (consistency R-cons; paid benchmark R-bench) | plan files | `output/logs/v3_rev_{cons,bench}_result.md`; 44 + 53 plan edits | 23:48-00:14 (26 min) | no | ran with p1-p3 |
| p1a freeze | sha256 manifest of eval v2 data + method files; ShieldAgent check; no-gold test | eval v2 files | `state_tracker/v3/frozen.py`, `output/eval_v3/manifest_eval_v2_data.sha256` (807 files), `tests/test_v3_frozen.py`, `test_no_gold_import.py` ext., `p1_freeze.md` | 23:48-00:08 (20 min) | no | yes (with p1b, p2, p3) |
| p1b offline base + Gate 0 | rebuild every saved decision exactly; length bins; dev/hold-out split; pre-reg part 1 | saved runs | `fork/offline_v3.py`, `scoring/v3_p1_gate0.py`, `p1_check_index.jsonl` (43,410), `split.json`, `p1_reproduction.md`, `preregistration.md` | 23:48-00:42 (54 min; Gate 0 run 1,543 s) | no | yes |
| p1 re-check RC1 | independent re-decide of all 43,410 checks | p1 outputs | `output/logs/v3_rc1_result.md` | 00:45-01:19 (34 min) | no | yes (with p4, p5) |
| p2 rule table | for every rule × true/false combination, the smallest flip sets | frozen `rule_set.json` | `state_tracker/v3/rule_table.py`, `rule_table_{retail,airline}.json`, `scoring/v3_p2_rule_table_check.py`, tests | 23:48-00:05 (17 min) | no | yes |
| p3 tool check | τ-bench's own write tool on a DB copy as a label | saved writes | `state_tracker/v3/tool_check.py`, `scoring/v3_p3_labels.py`, `tool_labels.jsonl` (10,427) | 23:48-00:37 (49 min) | no | yes |
| p4 decision audit | wrong decisions by outcome, located by rule table, blame tested by variants | p1-p3 | `scoring/v3_audit.py`, `p4_audit.{md,json}`, `p4_wrong.jsonl`, `p4_variants/` | 00:44-01:39 (55 min) + RC4 01:41-02:01 | planned STOP, skipped ("don't stop for me") | yes (with p5) |
| p5 fact definitions | 66 facts: source, start value, who, policy sentence; one evaluator | rule set, policy | `facts_v3_{retail,airline}.json` (via `p5_parts/` overlays), `facts_format_v3.py`, tests | 00:47-01:22 (35 min; 4 agents: retail, airline A, airline B, evaluator) | no | yes, split by domain |
| p6 code facts | database / event / argument expressions; agreement with tool | p5 | `code_helpers.py`, `p6_parts/exprs_*.json`, `scoring/v3_p6_agreement.py`, `p6_tool_agreement.md` | 01:25-05:58 (about 1 h work + 3.5 h API pause) | no | yes (p6∥p7∥p8) |
| p7 text structure | message view, helpers, info classes, structure facts, word screens; 3 blind screen sets by separate agents | p5 | `message_view.py`, `info_classes.py`, `p7_parts/`, `p7_api.md`, `p7_structure.md`, `p7_screen_sets/set{1,2,3}` | 01:25-07:00 (about 2 h work + pause) | P7.2 left for the user | yes |
| merge | main chat merges the 3 overlays into the fact files | p6-p8 overlays | fact files (0 conflicts) | 06:21 (1 min) | no | — |
| p8 tiny questions | K1-K16, cache, quote check, fake mode, network hook, budgeted real mode; dry-run call count and cost | p5, p7 | `questions_v3.json`, `questions.py`, `scoring/v3_p8_dryrun.py`, `p8_dryrun.md` | built 01:25-02:05; dry run 06:21-06:45, again 07:01-07:16 | no | yes |
| p9 guard | `TrackerTGRv3`, no judge, switches, `FROZEN_SHA256` | p6-p8 | `guard/tgr_tracker_v3.py`, `scoring/v3_p9_run.py`, `p9_guard.md` | 06:21-08:24 (2 h; run 2,786 s) | no | yes (p9∥p10) — crit |
| p10 block messages | messages from the rule table, 8 automatic checks | p2, p5, p9 interface | `guard/feedback_v3.py`, `scoring/v3_message_check.py` (1,215 s, 1 process), `p10_message_check.md` | 06:21-07:26 + RC10 07:27-08:35 | no | yes |
| p11 offline test | re-decide all dev checks with v3 (judge answers as stand-in), classes, audit again | p1-p10 | `scoring/v3_labels.py` (07:18-07:45, early), `scoring/v3_offline_eval.py`, `p11_offline.{md,json}`, `gates.md`, figures | 08:27-10:34 (about 40 min work + 1.5 h API pause) + RC11 10:36-11:22 | **STOP** 11:22 → user 11:25-11:50 | labels ∥ p9; run waits for p9 — crit |
| p12 real tiny answers | step 0 prep ($0: workers, hold-out mode); p12a dev sample (200 conv.); dev bug check; K2 fix loop (2 rounds, 3 re-asks); **freeze**; p12b hold-out once; independent recount; review; report | p8, p11 | `questions_answers.jsonl`, `scoring/v3_p12_{offline,holdout_labels,report}.py`, `p12_*.md`, `k2_fix.md`, `v3_freeze.md`, `tests/audit_v3_ref_counts.py` | 11:46-15:57 (4 h 11 min); K2 loop 13:47-15:33 | **paid; STOP** before; asked user 3× inside | p13 ran in parallel; K2 loop serial — crit |
| p13 paid-run prep | Direct + facts guard; soft stop; runner; metrics; online pre-reg; 3 audits; fixes; verify; dry runs | v2 runner, copy of partner runner | `guard/{direct_facts_v3,soft_stop_v3,run_online_v3}.py`, `scoring/v3_online_{metrics,interim}.py`, `online_tasks.json`, `preregistration_online.md`, `p13_audit_*.md`, `p13_verify_fixes.md` | 11:51-13:52 (2 h; 4 agents, then 3 auditors, 1 fixer, 1 verifier) | STOP (merged into p12 flow) | yes, fully ∥ p12. **Could have started at 23:48**: it does not depend on facts |
| p14 B1 smoke | 2 tasks × 5 arms | freeze | B1 run folder, `B1_*_summary.md` | approved 13:16; ran 15:34:50-15:39 (5 min) | paid | waited for the freeze |
| p14 B2 main | 99 tasks × 3 tries × 5 arms = 1,485 conv., 4 shards × 8 workers | freeze, B1 | `output/eval_v3/B2/<run_id>/`, metrics json, recompute, `tracker_v3_report.md` | approved 15:55; 15:56-16:54:53 (59 min); after-run chain 16:55:09 (16 s) | paid | — |
| p14 B3 extra | 64 Stage A many-write tasks × 1 try × 5 arms; needed a $0 runner build first | B2 | B3 run, `b3_prep/b3.patch`, `b3_tasks.json`, `tests/audit_v3_b3_recompute.py` | build ready 17:19, request 17:25, **approved 19:06**, run 19:08-19:24:47 (17 min; harm stop fired) | paid | — |
| after-results | val, B3, Direct+facts diagnoses; tiny-question audit; harm metric; report and KR rewrites; lessons; v4 prompt | runs | `B2_val_diagnosis.md`, `B3_diagnosis.md`, `direct_facts_diagnosis.md`, `tiny_question_audit.md`, `harm_metric.md`, `scoring/v3_harm_metric.py`, `docs/reports/tracker_v3_full_report.md`, `lessons_learned.md` | 16:58-20:57 (about 4 h, mixed with the B3 wait) | no | 3-4 agents at a time |

Critical path in v3: p5 → (p6 ∥ p7 ∥ p8) → merge → (p9 ∥ p10) → p11 → RC11 → **stop** → p12 prep → p12a → dev check →
K2 loop → freeze → (p12b ∥ B1) → B2 → B3 request → **wait** → B3.

---

## 2. The freeze mechanism, and how it was checked

v3 had **four** sha256 layers. They worked, but the bookkeeping drifted (see the end of this section).

**Layer 1: the old method and data (eval v2), `state_tracker/v3/frozen.py`** (standard library only, no import side
effects).
- Manifest file `output/eval_v3/manifest_eval_v2_data.sha256`, `sha256sum` format, one line per file:
  `<sha256>  <path from predicate_correctness/>`, sorted by path, 807 lines (eval_v2 736, online p10 16, partner runs
  32, splits 1, method files + rules 22).
- The manifest's own sha256 is pinned in `frozen.py` as `MANIFEST_SHA256`.
- API: `MANIFEST_PATH`, `check_manifest() -> {relpath: sha256}`; raises `ManifestMissing` / `ManifestChanged` (with
  `.changed`, `.missing`, `.added`). It also fails when a **new** file appears in a closed folder (`output/eval_v2/`,
  `output/online/p10_*/`, `from_shieldagent/runs/`, `from_shieldagent/rules/`). CLI: `python -B -m
  state_tracker.v3.frozen --build | --check` (`--build` refuses if the manifest exists). Takes 0.6 s.
- **Every v3 script calls `check_manifest()` first.** Test `tests/test_v3_frozen.py` (15 tests) plants a changed byte,
  a missing file, a new file, a changed manifest, a bad line and unsorted lines on a temp copy.
- `tests/test_no_gold_import.py` was extended to every v3 file pattern (static + run-time import check).

**Layer 2: the new method, frozen once before the hold-out and the live runs.**
- `output/eval_v3/v3_freeze.md`: a markdown table `| file | sha256 |`, 19 rows (state_tracker/v3/* incl. the fact and
  question JSON, `guard/tgr_tracker_v3.py`, `direct_facts_v3.py`, `run_online_v3.py`, `soft_stop_v3.py`,
  `scoring/v3_online_metrics.py`, `v3_online_interim.py`, `online_tasks.json`). Written by the main chat at 15:33:34
  right after the last dev check; its own sha is logged in the overview table.
- The guard checks itself: `FROZEN_SHA256` (24 files) in `guard/tgr_tracker_v3.py`, checked at start and end of a
  run. Every fix before the freeze had to "re-record FROZEN_SHA256" (p10, p12 prep, K2 batch, round 2): a recurring
  small step.
- The runner writes `run.json` with the command, the approval quote and the sha256 of every guard input; later shards
  with other inputs are refused.

**Layer 3: the online pre-registration** `docs/planning/tracker_v3/preregistration_online.md`, frozen by sha before
any paid call (12:30). It lists the shas of 5 code files + the task list. Later code-sha changes (audit fixes, B3
build) go in its change log: `| time (UTC) | change | why | result seen? |`. The dev pre-registration
`output/eval_v3/preregistration.md` had the same change-log pattern (parts 1-2 logged before p4 / p5 outputs).

**Layer 4: the overview sha table**, at the end of `overview.md`: `| new file | sha256 |`, rows like
``| p13 `guard/run_online_v3.py` (after audits B, C) | `45ee…` |``. Append-only: about 140 rows by the end, including
stale rows for files changed later, report rewrites and KR versions.

**How it was checked.**
- Before B2 the main chat re-hashed the freeze files ("all 21 match"; there are 19).
- During B2 an integrity agent (no edits) found: freeze OK (19/19); 4 files with no current overview row; 2 stale
  rows; freeze size logged as 21 instead of 19; 3 test-only failures (helper registry import order; a stale store copy).
- B3 check: B3's guard input shas equal B2's except the runner and 2 B3-only keys.

**Drift to avoid in v4:** four places, written by hand, with hand-typed counts. v4: one script `v4_freeze.py --write
| --check` that writes one machine-readable manifest of every method file (the same sha256sum format as layer 1), and
one generated markdown table from it; the guard and runner read that manifest instead of a hand-kept
`FROZEN_SHA256`; the overview table points to the manifest, it does not copy it.

---

## 3. The biggest time sinks and their causes

| # | sink | time lost (about) | cause | v4 fix |
|---|---|---|---|---|
| 1 | API session-limit pauses | 5 h (02:05-05:38; ~09:00-10:30) | many agents plus long runs hit the account's session limit; agents were resumed by message | plan the heavy fan-out in bursts; resume briefs ready; keep agents' logs out of context; no redundant re-check agents on non-critical parts |
| 2 | User waits at stops / approvals | ~2.5 h: B3 request 17:25 → approval 19:06 (1 h 41 min); p11 stop 11:22 → 11:50; K2 questions 13:47 → 14:02, 14:09 → 14:18; B2 15:46 → 15:55 | one approval per paid step, asked only when the step was ready; design questions came up mid-run | ask all paid approvals in one request with conditions ("smoke, then main if smoke passes; banking after known"); put the user's likely choices (main claim set, secondary claims, harm, extra runs) into the first plan |
| 3 | Real tiny answers tested late → serial K2 loop | 1 h 46 min loop (13:47-15:33) + about 5.5 h latency (question code ready 07:16, first real answer 12:42) | fake answers and the judge stand-in hid K2's strictness; real answers only after the full offline test, the p11 stop and the p12 approval | $0 form check + made-up cases first; a small paid pilot of real answers right after the question code (v4 stop 3), before the big offline test |
| 4 | Long offline runs on the critical path, one process | p9 run 46 min, p10 check 20 min, p11 28 min (3 workers), Gate 0 26 min, p6 8 min, p7 7 min | single-process scripts; the full test suite 9.5 min in one process until 15:29 | workers by default in every script; the parallel test runner from day 1 |
| 5 | Independent re-checks on the critical path | RC10 68 min, RC11 46 min (RC1 34, RC4 20 off path) | one re-check per part, each from scratch | one combined audit wave at the end of the build, in parallel with the paid pilot; recompute scripts written once and reused |
| 6 | Blind screen sets, 3 rounds | 01:25-06:58 off the main path, but ended in removing 4 screens anyway (K5 then asked at almost every reply: 715 → 6,008 calls) | word lists as a gate for asking | prefer code preconditions; no screen sets |
| 7 | After-results work and doc churn | ~4 h (16:58-20:57) | harm metric invented after the results (19:29), then added to every table (20:13-20:16); full report rewritten 5× (16:58, 19:19, 20:05, 20:16, 20:52); KR rewritten 15:16-15:27, fact-checked 15:41 (found an error), cleaned 16:37, updated 20:07, reorganised 20:57 | pre-register harm + diagnosis classes; reports generated once from numbers files; one checker |
| 8 | Mid-run plan changes | each cost doc + code + pre-reg edits: main claim on 99 (12:12), S1/S2 (12:14), B3 whatever (16:52), harm (19:29) | not in the first plan | decide them in the plan |
| 9 | Missing runner feature found late | B3 needed a $0 build (16:49-17:19) | the runner supported only the 99-task steps | build every planned step (incl. options) into the runner before the freeze |
| 10 | Cross-agent small breakages | minutes each: "gold" constant vs no-gold test, helper registry import order, test isolation, `me` loop variable, stale `FROZEN_SHA256` | shared registries and constants written by several agents | one owner per module; tests isolate registries; frozen hashes generated |
| 11 | Plan check edits | 26 min, 97 edits | the plan had gaps (p12 limit had no code; p4 details) | keep, but run it on the v4 plan before the user stop |

What already worked for speed (keep): p1a/p1b/p2/p3 at once; p4 ∥ p5; p6 ∥ p7 ∥ p8 with owned overlay files merged by
`merge_overlays.py` (0 conflicts); p9 ∥ p10 with a fixed interface; p13 ∥ p12; 4 shards × 8 workers (B2 1,485 conv.
in 59 min); `--workers 8` for tiny questions (2,726 calls in 12 min); the auto-finish script (B2 metrics + report +
recompute 16 s after the last process).

---

## 4. The audit pattern, and how to automate it

**What v3 did.**
- **Per-part independent re-checks** (RC1, RC4, RC10, RC11): a fresh read-only agent re-checks the part's "How we
  know it is right" with its own script, plants errors to show its checks bite (e.g. RC10 caught 124/124 changed
  values, 98/98 planted other-user values), and writes `output/logs/v3_rcN_result.md` (blocker / major / minor).
- **p13: three lens audits in parallel** (12:33-12:47), each given the code and the rules, not our conclusions:
  - A: metrics code vs the frozen pre-registration (bootstrap, leak rule, S1/S2, complete groups, val lock);
  - B: runner and money (overspend, pairing, wrong tasks, calls without approval) — found the 1 blocker (backup
    moved, not copied, hides spend) and 2 majors (failed tiny call became a silent v3 block; two processes per shard);
  - C: fairness of the arms (prompt equality Direct vs Direct + facts via judge-cache records, policy sha, models).
  - Format: `| # | severity | file:line | what is wrong | failing case |` + verdict "0 blockers (x major, y minor)".
  - Then one fix agent for all findings (not allowed to touch frozen v3 files), then one **verify-fixes** agent:
    `| # | was | now | severity left | where | the case I tried |` → "0 open blockers".
- **Independent recomputes** (written by a separate agent from the plan/pre-reg text and the raw lines, never from the
  project's analysis code):
  - `tests/audit_v3_ref_counts.py` (P12.3, hold-out counts; matched except one class split, because "confirmation
    facts" was never defined);
  - `tests/audit_v3_online_recompute.py` (B2; ~3 s; point estimates must match, ranges may differ in the 3rd
    decimal); dry-run on a partial copy before the end (42/42 match, outcomes not read);
  - `tests/audit_v3_b3_recompute.py` (B3).

**How v4 can automate it.**
1. Write the independent recompute **before** the run (independence comes from who writes it and what it reads, not
   from when it runs). Then running it is a script step.
2. One after-run chain in the repo (not in a session scratchpad, where v3's `b2_finish.sh` lived):
   `scripts/v4_after_run.sh <run_dir>` = wait for the pids in `pids.txt` → line and error counts → metrics →
   harm metric → independent recompute → **compare** point estimates (exit 1 and a "MISMATCH" progress line if any
   differs by > 1e-9) → diagnosis classes (pre-written classifier: wrong/too-strict block by question, agent
   mistake, noise, other) → report builder → append progress + implementation-log lines → append sha rows.
3. Halfway interim by script, including writing the `STOP` file when the pre-registered harm rule fires (writing STOP
   only stops spending, so it is safe to automate; v3's main chat did it by hand at 19:21).
4. Progress "auto:" lines by the same script every 10 min (`b2_auto.sh` pattern).
5. Lens audits A/B/C stay agent work (they read code), but run once, at the end of the build, in parallel with the
   paid pilot, with the v3 findings list as a checklist (each v3 finding has a test now, so most become unit tests).
6. Integrity check (freeze hashes, sha table, full test suite) as a script run before every paid start and by the
   after-run chain.

---

## 5. Proposal: v4 in 6 big parts with parallel tracks

The v4 prompt fixes the stops: (1) the plan, (2) the τ³ install/download, (3) a paid dev check of tiny answers on the
known tasks, (4) the paid live runs. The parts below fit those stops. Three tracks run side by side:
**M** = method (facts, questions, guard), **H** = harness (runner, money, metrics, recompute, after-run chain),
**R** = rules of the experiment (pre-registration, reading guide, harm, diagnosis classes).

| part | what (merges v3 parts) | tracks / agents | stop | time (estimate) |
|---|---|---|---|---|
| **P0 plan** | overview + predicate table + pre-reg draft + reading guide draft + harm + diagnosis classes + all approvals asked as conditional ones; plan check by 2 reviewers before the stop | main + 2 reviewers | **stop 1** | done before the stop |
| **A install + map + freeze base** (v3 p1, p3) | install τ³ (main chat, network); map τ³ tasks to v1 and drop test 66; policy diff v1 ↔ τ³; extend the frozen manifest (v2 + v3 + τ³ source); port the tool replay and tool-check label to τ³ tool code; Gate 0 on τ³ (old guard rebuild if it runs); read banking policy/tools/DB (not task files) | M: replay/tool-check; H: env, map, manifest; R: banking reading | **stop 2** is the install at the start | 1-1.5 h |
| **B facts + rules** (v3 p2, p4, p5, p6, p7) | rule tables (TGR frozen rules for airline/retail if they run; banking rules written from policy, same schema); fact definitions by domain; code parts; structure parts; agreement with the tool; owned overlays merged by script | M: 3-5 agents (retail, airline, banking A/B, evaluator port); H in parallel: runner port + soft stop + metrics port (v3 p13 steps 1-4) | none | 2-3 h |
| **C questions + guard + messages + offline check** (v3 p8, p9, p10, p11) | tiny questions with the $0 form check and made-up cases; guard v4; block messages naming the missing line; Direct + facts with the fixed wording; offline check on saved known-task conversations ($0); dry-run call counts | M: 3-4 agents; H: recompute scripts, after-run chain, dry runs; R: freeze the pre-reg + reading guide | none | 2-3 h (overlaps B's end) |
| **D paid pilot + fix + freeze** (v3 p12a + p13 audits) | real tiny answers on a small known-task sample; fix definitions (not examples), re-ask; then **freeze v4** (generated manifest); in parallel: audit wave A/B/C + verify + integrity check + shard dry runs | main chat runs the pilot; 3 auditors + 1 fixer + 1 verifier | **stop 3** (paid pilot) | 1-1.5 h |
| **E live runs** (v3 p14) | smoke → known-task run (99 × 3 × arms) → banking run (~97 × 3 × arms), one written request, one hard limit each, conditional chaining; auto interim + auto STOP + auto progress lines | main chat; scripts | **stop 4** (paid runs) | ~2-3 h (B2 did 1,485 conv. in 59 min) |
| **F after-run + report** | after-run chain runs by itself; pre-written diagnosis; reports written once from the numbers files; KR §1 + lessons updated once | 2-3 agents | none | ~1 h |

Rough total, no API pause and quick approvals: about 9-12 h wall clock (v3: 21 h).

**What can start at minute 0 (after stop 2):** the whole H track (v3's p13 had no dependency on facts but started at
11:51) and the whole R track. Only the M track is serial (facts → questions → pilot → freeze).

**Existing scripts to reuse (port, do not rewrite).** All under `predicate_correctness/` unless noted.
| v3 file | v4 use | change needed (expected; τ³ API not yet checked, no network) |
|---|---|---|
| `state_tracker/v3/frozen.py` | manifest pattern | new manifest file + closed folders; make it generic (`--manifest`) |
| `state_tracker/v3/rule_table.py` | rule tables | none for TGR-schema rules; banking rules must use the same schema |
| `state_tracker/v3/tool_check.py` | tool label | port to τ³ tool code and error texts |
| `state_tracker/v3/facts_format_v3.py` | the one evaluator (OR fix included) | domain list; registry isolation |
| `state_tracker/v3/code_helpers.py`, `message_view.py`, `info_classes.py` | helpers | τ³ message/record format |
| `state_tracker/v3/questions.py` (+ `questions_v3.json`) | cache, quote check (multi-piece), budgets, fake mode, network hook, `--workers` | new questions; save the conversation id with every answer (TQA §5) |
| `guard/feedback_v3.py` | rule-built messages | add the failing line and expected value |
| `guard/tgr_tracker_v3.py` | guard skeleton | read the generated manifest instead of a hand-kept `FROZEN_SHA256` |
| `guard/direct_facts_v3.py` | Direct + facts arm | print final value with sign; only facts the action's rules use |
| `guard/soft_stop_v3.py` | limits, cap, reserve, backup check | step names |
| `guard/run_online_v3.py` | runner (shards, locks, STOP file, approval words, dry-run sandbox, run.json) | biggest port: τ³ orchestrator; build every planned step in |
| `scoring/v3_online_metrics.py`, `v3_online_interim.py` | metrics, interim | arms per domain (no TGR on banking); harm as a pre-registered metric |
| `scoring/v3_harm_metric.py` | harm (outcome view) | make it part of metrics, not a separate after-step |
| `scoring/v3_p14_report.py`, `v3_b1_summary.py` | report, smoke summary | sections for known vs banking |
| `scoring/v3_labels.py`, `v3_audit.py`, `fork/offline_v3.py`, `scoring/v3_p8_dryrun.py`, `v3_message_check.py` | offline check, classes, decision audit, call counts, message checks | input format |
| `tests/audit_v3_online_recompute.py`, `audit_v3_b3_recompute.py`, `audit_v3_ref_counts.py` | independent recompute templates | written fresh by a separate agent from the v4 pre-reg (keep independence) |
| scratchpad (session `dbfe7ffd…`): `b2_finish.sh`, `b2_auto.sh`, `b3_interim.sh`, `run_v3_tests_parallel.sh`, `merge_overlays.py` | after-run chain, progress lines, interim, parallel tests, overlay merge | **copy into the repo first** (`scripts/`): they live in a temporary session folder and hard-code pids and run ids |

**After-run steps that can be chained automatically:** wait for pids → counts → metrics (incl. harm, cost, LLM calls,
LLM share, blocks per write) → independent recompute → compare → diagnosis classes → report → progress /
implementation-log lines → sha rows → integrity check. Halfway interim + STOP file also by script. Only the reading
of the result and the lessons stay with the main chat.

---

## 6. Formats used in v3 (copy them for v4)

**`progress.md`** (`predicate_correctness/output/eval_v3/progress.md`; v4: `docs/planning/tracker_v4/progress.md`)
1. Title, then one line: open in VS Code Markdown preview; updated by the main chat at every event, and by run
   agents at least every 10 min during long runs.
2. A blockquote **money rule** listing exactly what is approved so far (with the user's words and times) and money
   spent.
3. "The experiment in short" block (what is learned / not; data roles table; stages; goal in one line; honest
   expectations).
4. `## Now`: bullets with UTC times, newest state first.
5. `## Spend`: table `| | $ |`.
6. `## Parts`: table `| part | what | money | status | est. time | agents | result |` (status like **done** (01:19)).
   Then totals and "where the times come from".
7. `## Agents running now`: `| agent | part | started (UTC) | owns |`.
8. `## Events (newest last)`: bullets `- 2026-10-23 HH:MM UTC: **key fact**: text`. Run lines by script:
   `- auto: HH:MM UTC B2: N of 1,485 lines, error lines E, v3 spend $S`.

**`implementation_log.md`** entries (append-only, one `##` section per event)
- Header, two styles were used: early `## Tracker v3 Part N: title (agent pN, HH:MM - HH:MM UTC) — part N done`;
  later `## 2026-10-23 HH:MM UTC: event (who, $0 / paid)`. v4: pick the second style always.
- Bullets: **Files:** (paths, sha prefix `e418902e…`), the run command and its run time, **Pass marks:** `P6.1: …`
  with exact counts, **Main chat re-check (HH:MM):** command + log path, notes for later parts, main chat decisions,
  rule slips (e.g. "one edit result printed to the terminal").
- Corrections are new entries that point to the old one ("Correction (this entry): the 15:11 entry … overstates it").

**`knowledge_retention.md` section 1** ("The project in one page")
- File header: "Last updated <date>, after <event> (HH:MM UTC)" and where newer events live.
- §1 blocks in order: **In one line**; **The goal**; **What we built** (bullets per version); **Headline results**
  (bullets with numbers and the source file); an **arm table** `| arm | B2 task success | B2 harmful got through |
  B3 task success | B3 harmful got through | B2 cost per conversation |` with a note under it (harm next to success
  in every table, the user's rule); **What "no gain" means**; **Status** (frozen time, "results are final", spend of
  cap, "Nothing paid is approved. No network step is approved."); **The next step** (data-role table, arms, stops).
- During v3, §1 was updated at each big event (16:35 B2 status; 17:08 val diagnosis; 19:19; 20:07; 20:57 reorg), plus
  §4.3, §6.3 rows, §9, §10, §11 (prompt copy). v4 prompt asks: short-line updates of §1 after each part, no
  rewrites.

**Overview sha table** (end of `overview.md`): `| new file | sha256 |`, rows ``| <part> `path` (note) | `sha256` |``.
v4: generated from the freeze manifest, not hand-typed.

**Pre-registration change log:** `| time (UTC) | change | why | result seen? |`.

**Cost log** (end of `approval_request.md`): `| date (UTC) | step | calls | cost (logged list price) | hard limit |
note |`, one row for each approval, start and end, with the user's approval words quoted.

**Audit report:** `| # | severity | file:line | what is wrong | failing case |` + "Checked and right" table + "What I
ran" + verdict line. **Verify-fixes:** `| # | was | now | severity left | where | the case I tried |`.
