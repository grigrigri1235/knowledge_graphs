# Tracker v4, session 1: what happened (2026-10-23, about 20:57-21:40 UTC)

This session started the v4 plan and then stopped itself on purpose. Its main chat saw impure
information about how banking predicates could be made, so the user ended it and asked for a fresh
agent. This file records everything, so nothing is lost and nothing impure is reused. Times are UTC,
taken from file times. Paths start at `/home/azureuser/code_projects/`.

## 1. The main idea in one paragraph
v4 is the partner's TGR method on τ³-bench, with **only the predicate VALUE part changed**. TGR's own
pipeline creates the rules and the predicates. v4 then sets each predicate's value by code (database,
tool-code replay, event log, call arguments, exact text) where code can know it, and by a tiny yes/no
LLM question only where words must be understood. In this session the main chat had 7 agents hand-write
banking rules from the knowledge base. **That is predicate creation outside the partner's pipeline**, so
the user called it a leak, had it deleted, and ended the session.

## 2. Timeline
| time | event |
|---|---|
| 20:57 | the prompt `docs/planning/tracker_v4/next_agent_prompt.md` was written (by the v3 agent) |
| ~21:00 | session 1 started; 6 reader agents on the v3 material (all $0, read only) |
| 21:03 | **the user approved the τ³ download** ("i am approving of tau^3 downlowd it"); cloned `sierra-research/tau2-bench` (tag v2.0.0, `cc1df47`) into `third_party/tau2-bench` |
| 21:05 | banking task and result files sealed: sha256 first, then chmod 000 (163, later 167 files) |
| ~21:06 | `uv sync` by the main chat was refused by the auto-mode check; **the user ran the install** (venv `.venv_tau3`, Python 3.12.15, tau2 editable, litellm 1.81.11) |
| ~21:06 | 11 more agents: τ³ harness, airline diff, retail diff, banking tools/DB, and **7 banking KB readers** that hand-extracted rules from all 698 docs |
| ~21:08 | the user asked for data purity: a small calibration set is OK, keep many tasks unseen; all running agents were told |
| ~21:15 | the user's answers: **banking calibration 20 tasks**; **harm cohort yes**; on the old guard: "τ³ policy is the reference … the old guard should adapt a bit, keep its method" |
| ~21:16 | the banking tools reader found that `CHANGELOG.md` names banking task facts; the release-note files were sealed. The harness reader had already read those lines; its notes were scrubbed |
| ~21:17 | **the user: "was it done in accordance with my partner's method? … we improve specifically the predicate part"**. A reader started on TGR's rule builder (`reading_notes/tgr_build_method.md`) |
| ~21:19 | **the user: throw the 7 readers' work away, delete it.** Deleted: `reading_notes/bank_kb_rules_s1..s7.md` and 98 logs (`v4_kb1-7_*`, `v4_bmap_*`); the merge agent was stopped before it wrote anything |
| ~21:20 | the user chose **τ³ = tag v1.0.1** (not v2.0.0), and to **delete the banking tools/DB notes** too. Deleted: `reading_notes/tau3_banking_tools_db.md`, 2 scratch scripts, the `v4_bk_*` logs |
| 21:22 | clone checked out at **v1.0.1 (`fc0055d`)**, re-sealed (218 files, see §5); old seal kept as `*_v2.0.0_superseded*` |
| ~21:25 | **the user: predicate creation must be done only through the partner's pipeline; write a detailed prompt for a fresh agent; parts touched by the leak must be redone.** The hand-made airline/retail predicate-table agent was stopped (it had written no table); its 13 logs were deleted |
| ~21:40 | this file and `next_agent_prompt_v2.md` written |

## 3. The user's decisions (binding for v4)
1. **τ³-bench = tag v1.0.1** of `sierra-research/tau2-bench` (commit `fc0055d`). Not v2.0.0.
2. **Predicates and rules are created only by the partner's TGR pipeline**, in all three domains
   (airline, retail, banking_knowledge), run on the τ³ v1.0.1 policy. Nobody writes, adds, removes or
   rewords a rule or predicate by hand. v4 differs only in **how each predicate gets its value**.
3. **τ³ policy is the reference.** The old guard (TGR = rules + one LLM judge) keeps its method, on the
   rules the partner's pipeline builds from the τ³ policy. v4 uses the same rules.
4. **Data purity first.** Banking calibration set = **20 tasks**, never counted as results; the rest
   stays unseen until the freeze. Airline/retail: dev work on train tasks only; val stays out of dev.
5. **Harm cohort: yes.** A weak agent (gpt-5-nano) on the unseen banking tasks, pre-registered.
6. More subagents, more speed. Keep stops few.

## 4. Files: what is clean, what is not
| file (`docs/planning/tracker_v4/` unless a full path) | made by | status |
|---|---|---|
| `next_agent_prompt.md` | v3 agent, before this session | clean, but **superseded by `next_agent_prompt_v2.md`** |
| `next_agent_prompt_v2.md` | session 1 main chat, written for the user | the prompt for the fresh agent; contains **no banking facts and no predicates** |
| `brainstorm.md` | session 1 main chat | **do not use its design notes** (the main chat was leak-affected); its event list is a record only |
| `banking_seal.sha256`, `banking_seal_paths.txt` | main chat | clean; the v1.0.1 seal (218 files) |
| `banking_seal_*_v2.0.0_superseded*` | main chat | record only |
| `reading_notes/v3_structure.md` | reader (v3 docs only) | clean |
| `reading_notes/metrics_costs.md` | reader (v3 docs only) | clean |
| `reading_notes/facts_rules.md` | reader (v3 facts, v1 policy) | clean; its τ³ parts were written from memory, not from the repo |
| `reading_notes/tiny_questions.md` | reader (v3 questions + τ³ v2.0.0 airline/retail db counts) | clean for the **value-assignment lessons**; its counts are v2.0.0 (the DB is believed to be the same in v1.0.1, so re-check) |
| `reading_notes/port_map.md` | reader (v3 code + τ³ v2.0.0 code) | clean; v2.0.0, see its errata section |
| `reading_notes/tgr_portability.md` | reader (TGR + τ³ v2.0.0 airline/retail) | clean; v2.0.0 |
| `reading_notes/tau3_airline_diff.md`, `airline_task_map.json` | reader (v1 vs τ³ v2.0.0 airline) | clean; v2.0.0, maps redone for v1.0.1 in `airline_task_map_v101.json` |
| `reading_notes/tau3_retail_diff.md`, `retail_task_map.json` | reader (v1 vs τ³ v2.0.0 retail) | clean; v2.0.0, maps redone in `retail_task_map_v101.json` |
| `reading_notes/tau3_harness.md` | reader (τ³ v2.0.0 code) | **leak-touched**: this agent read `CHANGELOG.md` lines that name banking task facts (its notes were scrubbed). Use only its airline/retail and general harness parts; **re-derive every banking part** from the v1.0.1 code |
| `reading_notes/tgr_build_method.md` | reader (ShieldAgent TGR builder, τ³ v1.0.1 policies) | **airline/retail and the pipeline description: clean.** **Banking parts: leak-touched.** Before my message reached it, this agent opened the since-deleted banking tools/DB note; it says it used nothing from it and re-measured banking from the prompt files, KB docs and tool code. Re-decide the banking build input independently |
| `reading_notes/*_v101*` and the errata sections | reader (git diff v1.0.1 vs v2.0.0, airline/retail) | clean |
| deleted, **must not be recreated or used** | the 7 KB readers, the merge agent, the banking tools/DB reader, the airline/retail predicate-table agent | gone |

## 5. The seal (τ³ v1.0.1)
- Sealed (chmod 000, sha256 taken first, contents never read; list in `banking_seal_paths.txt`):
  - banking task files: `data/tau2/domains/banking_knowledge/tasks.json`, `tasks_voice.json`, and `tasks/`
    (97 files, task_001-task_102 with gaps);
  - banking task tests: `tests/test_domains/test_banking_knowledge/tasks/` and `test_retrieval_e2e.py`;
  - all saved results and leaderboard submissions: `data/tau2/results`, `web/leaderboard/public/submissions`;
  - the release notes: `CHANGELOG.md`, `RELEASE_NOTES.md`, `github-release-body.md`, `.release-template.md`.
- **Seen banking ids**, named in the release notes that one reader read: **task_053, task_074, task_085,
  task_102**. They must never be in the unseen test set; put them in the calibration set.
- To unseal later: `chmod -R u+rwX` on those paths, only at the step the plan names.

## 6. What must be redone (because of the leak or the method rule)
1. **All banking predicate work**, from zero, by fresh agents that never saw any session-1 banking output:
   the partner's pipeline makes the rules and predicates; then value assignment.
2. **Airline/retail rules and predicates**: rebuilt by the partner's pipeline on the τ³ v1.0.1 policy, not
   hand-adapted. The hand-adapt idea (fix "3 → 4 bags", add new bans by hand) is dropped.
3. **Banking harness facts** (retrieval variant, paid call sites in banking, seal-safe task loading):
   re-derive from v1.0.1 code; do not trust `tau3_harness.md` there.
4. The v4 plan (`overview.md`) was never written. It is the first job of the next agent.

## 7. Agents used in session 1 (all $0, read only unless noted)
- **Clean, kept:** v3 structure, metrics/costs, facts/rules, tiny questions, port map, TGR portability,
  airline diff + map, retail diff + map, TGR rule builder, the v1.0.1 re-check.
- **Leak-touched, partly kept:** the τ³ harness reader (§4).
- **Deleted:** the 7 KB rule readers, the KB merge (stopped), the banking tools/DB reader, the airline/retail
  predicate table (stopped).
- **Rule slips the agents reported:** 3 agents ran a no-op `python3 -c` against the "no Python" brief (no
  effect); one repo-wide `grep -l` printed only file names. No paid or network call by any agent. The only
  network steps were the clone (approved) and the install (run by the user).

## 8. Spend
$0. No LLM API call was made. The network steps were the clone (user-approved) and the user's install.

---

## 9. 2026-10-24: purity events found in the part 7 audits (all $0)
**In plain words.** The read-only audits of part 7 found five places where the build touched data it should not have,
or where a plan sentence was too strong. None changed a v4 decision. All are fixed and written down here and in the
change log of `preregistration_v4.md`. No v4 live run and no paid call had happened.

| # | what happened | fix | effect |
|---|---|---|---|
| 1 | **Form-check leak.** The form-check script read the user instructions and the gold expected actions of retail train 500 (this holds the B3' tasks), retail test 69 + airline test 30 (= the B2' tasks) and retail dev 20, to count how users name things (payment, dates, items). Its decisions fed the listing and go-ahead code. | User decision: rebuild from the database only. The check now reads only the 6 database json files and the 2 `wiki.md` policy files (a test enforces this). All 40 form decisions were re-based on database counts, the wiki, or a generic reason. | 0 decisions changed; the stand-in eval rows are byte-identical (sha `2bc488e9…`). No v4 decision depended on task text, but it is disclosed. |
| 2 | **Message-check read.** An early run of the message-check script used its old default of 9 data sets. These included `stage_b`, whose try files hold forks of hold-out conversations, and nano and other sets beyond the 200 dev conversations. Code read those files; only counts went to the log; no person or model read the content. | The default and the only allowed sets are now the 4 dev sets × 50 = 200 conversations; any other set is refused. | none known; disclosed |
| 3 | **Few-shot origin wording.** `overview.md` §12.2 said the few-shot writers "never saw any conversation". The few-shots are made up from the policy, but some were chosen to target loss types known from v3's reports (for example one-word replies). | §12.2 reworded to say exactly that. Sources: `few_shot_why` of K1, K3, K13, K17 in `questions_v4.json`; `predicate_table.md` lines 184 and 249. | wording only |
| 4 | **K17 cases too close to the K17 few-shot.** 3 made-up K17 cases equalled or nearly equalled the few-shot (1 exact, 2 near). | Replaced by new made-up cases. Now no case has a text ratio ≥ 0.9 to any few-shot (max 0.817). New `K17.jsonl` sha `96699e7e5d6ed189c3d276ebdcefb799f8ae9e6d3df8b8b50df53f57c1839f15`. | the K17 case score is not inflated by copies |
| 5 | **Dev-check reads of v3's answer store.** | The dev check and the offline eval now read only the dev keys of v3's `questions_answers.jsonl`, line by line; non-dev rows are never kept. | purity rule of `build_brief.md` §3 now enforced in code |

**Plan change that follows from #1 (user decision):** the retail dev 20 tasks were read by the build, so they are not
unseen. The DEV20v4 side check is **dropped**. `output/eval_v4/dev20_check.md` is marked unused.

Names: `scoring/v4_form_check.py`, `state_tracker/v4/listing_v4.py`, `state_tracker/v4/helpers_go_ahead_v4.py`,
`scoring/v4_message_check.py`, `scoring/v4_dev_check.py`, `scoring/v4_offline_eval.py`,
`output/eval_v4/cases/K17.jsonl`.
