# Tracker v4: brainstorm (working notes, not the plan)

Started 2026-10-23 ~21:00 UTC. The plan is `overview.md`. Reader notes are in `reading_notes/`.

## Events so far
- 21:03: the user approved the τ³ download ("i am approving of tau^3 downlowd it"). Cloned
  `sierra-research/tau2-bench` at `cc1df47` (2026-10-22) into `third_party/tau2-bench`.
- 21:05: banking task and result files sealed: sha256 of 163 files in `banking_seal.sha256` was taken first,
  then they were set to chmod 000. Paths are in `banking_seal_paths.txt`. Nobody has read them.
- `uv sync` (install) was **refused by the auto-mode permission check**. It is not installed yet. The user
  has to allow it or run it.
- The user's mid-run wishes: more subagents and speed; data purity and no leaks. A small dedicated
  calibration set is OK (maybe in banking), but keep many tasks unseen.

- The user: v4 improves ONLY the predicate part of the partner's TGR method. Rules must come from the partner's
  own rule builder, not from us.
- 7 banking KB reader agents wrote rule notes by hand-reading all 698 docs. **The user ordered them thrown away
  for purity.** Done: the 7 files (bank_kb_rules_s1-7.md) and 98 logs (v4_kb1-7_*, v4_bmap_*) were deleted,
  and the merge agent was stopped before writing. They must not be used. Banking predicate work must be done
  by fresh agents that never saw them. (The main chat saw their short summaries; it will not use them.)
- Leak note: one harness reader read CHANGELOG.md lines naming banking task facts before the seal. Its notes
  were scrubbed. The banking task ids named in CHANGELOG / RELEASE_NOTES / github-release-body (task_053,
  task_074, task_085; plus a "task 102") count as **seen**: never in the unseen test set.
- Version: the clone is tag v2.0.0 ("τ-bench 2.0", i18n). τ³-bench is the earlier tag **v1.0.x** (v1.0.1
  fixed banking grading). Which one to use is the user's choice.

- The user chose τ³ = v1.0.1. The clone was switched to v1.0.1 (fc0055d); the old seal is kept as
  `*_v2.0.0_superseded`. New seal: 218 files (banking tasks.json, tasks_voice.json, tasks/ with 97 files,
  banking task tests, test_retrieval_e2e.py, all data/tau2/results, all web/leaderboard submissions, the
  release notes). Contents not read.
- The user deleted the banking tools/DB notes too (purity). Done.
- Seen banking ids (named in the release notes): task_053, task_074, task_085, task_102. They are never in
  the unseen test set.
- The venv was installed from v2.0.0's lock. The editable tau2 now points at v1.0.1 code. v1.0.1's deps may
  differ; check at build time, and if needed the user re-runs `uv sync --frozen` (network).

## Facts from the repo (names and counts only)
- Domains: airline, retail, telecom, banking_knowledge, intake, mock.
- Task subsets: airline_50, retail_114, retail_50, banking_knowledge_97.
- Banking KB: 698 documents, 0.93 MB (~230k tokens), in 71 product categories.
- Python 3.12-3.13.

## Design thoughts
1. **Data roles**
   - Known airline/retail: the 99 tasks. The dev check uses train 66 × 1 try only. Val 33 stays out of the
     dev check (it is the "least seen" part).
   - Banking: calibration set C, ~15 tasks, picked by sha256(seed + file name) with no content read. These
     files are unsealed before the freeze and used for the dev check only. The test set T, ~82 tasks, is
     opened at the freeze. Results come from T only.
2. **Banking rules.** No TGR exists there, so we write rules from the KB plus the system prompt, each rule
   citing its doc and sentence. 7 slice readers are extracting them. An independent completeness critic
   checks them after.
3. **Direct for banking.** The guard gets the agent's own policy text plus the docs retrieved in the
   conversation. The whole KB is too big for one prompt.
4. **Confirmations**
   - "Details listed" (the old K2) becomes CODE: string checks over a window (agent messages since the last
     write plus the user's words), with forms counted from the DB.
   - "User agreed" (K1') stays a tiny question. One yes covers a listed batch, and any wording counts.
5. **Unclear answers.** Ask once more with a second wording before an unclear answer blocks a write. After
   2 tiny blocks on one write, allow the transfer.
6. **Dev check = smoke test.** Train 66 × 1 try (v4 + frozen TGR if it runs) plus banking C × 1 try (v4 +
   Direct), plus made-up cases. Pass marks are written in advance. Up to 2 fix rounds go inside the same
   approval only if the user names them.
7. **Harm cohort.** A weak agent (gpt-5-nano) on banking T × 1 try × 4 arms. Optional, default yes.
8. **Watch:** paid or network calls in τ³ (NL-assertion judge, embeddings for retrieval, the user simulator
   at construction). The harness reader will list them.
