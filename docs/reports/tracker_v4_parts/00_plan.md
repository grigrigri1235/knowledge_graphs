# Tracker v4 report: plan (2026-10-24)

Final file: `docs/reports/tracker_v4_report.md`, put together by the main chat from the parts below.
Each part is written by one agent and lives in this folder. Parts do not depend on each other.

## Parts

| file | sections | owner |
|---|---|---|
| `01_motivation_setup.md` | 1 Motivation; 2 Setup (benchmark, task sets, the 6 arms, models, what is reused from v3); 3 The three metrics (exact definitions) | agent A |
| `02_method_questions.md` | 4 How v4 sets each fact (method); 5 The development questions K1-K18 (what, which partner facts, where each came from); Appendix B (full question texts) | agent B |
| `03_build_purity.md` | 6 How v4 was built and checked (timeline, dev checks, fix rounds 1 and 2, results known); 7 Purity and data leakage (honest); Appendix A (lessons from v3 used in v4) | agent C |
| `04_results.md` | 8 Results: skeleton with blanks + reading rules for every cell; spend; stops; limits | agent D |
| `05_generality.md` | 9 Recipe for a new policy (the general processing stage); overfitting check; Appendix C (checklist) | agent E |
| (main chat) | title, short summary, glossary, final numbers filled in | main chat |

## Shared rules for all parts
- Simple, short language. Main idea first in every section. Define every term the first time it appears.
- Style model: `docs/reports/tracker_v3_report.md` (clear structure, tables, defined terms). Do not copy its text. Fix its known
  problems: too many metrics in the main text, terms used before they are defined, numbers without a "so what".
- **Only three metrics per arm** in the main text: **cost of the whole conversation** (all roles: agent, user simulator,
  guard; list price as logged), **task success**, **harmful writes that got through**. Every table shows harm next to success.
  Nothing else in the main text (blocks, LLM share, etc. may go in a short "behaviour" note only if needed to explain).
- Blanks for results not yet in: `⟦TBD: <what>⟧`. Each blank gets a reading rule taken from
  `docs/planning/tracker_v4/preregistration_v4.md` and `reading_guide_v4.md`, written as:
  "If ⟦x⟧ … : bad result, it shows … . Otherwise: good result, it shows … ."
- Do **not** open the v4 live results (`predicate_correctness/output/eval_v4/{B2v4,B3v4,Hv4}/`, `output/logs/v4_{B2v4,B3v4,Hv4}_*`)
  and do not open v3 conversations. The main chat fills the numbers in.
- Arms (names used everywhere): `none` (no guard), `direct` (one LLM checks the policy directly), `direct_facts_v4`
  (Direct + v4's code facts), `tgr_frozen` (the partner's TGR guard, unchanged: one judge LLM sets all facts),
  `tgr_tracker_v3` (v3 tracker), `tgr_tracker_v4` (this work). Short names in tables: none, Direct, D+F v4, frozen, v3, v4.
- Steps: B1v4 (smoke, 4 conv.), B2' = B2v4 (99 tasks × 3 tries), B3' = B3v4 (64 many-step retail tasks × 1),
  H = Hv4 (99 tasks × 1, weak agent gpt-5-nano). Old arms on B2' and on 49 of 64 B3' tasks are **reused from v3 runs**.
