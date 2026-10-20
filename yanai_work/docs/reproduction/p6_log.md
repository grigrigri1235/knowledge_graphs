# P6 log: online τ-bench evaluation (Stage A)

Started 2026-10-16. Decisions (user, 2026-10-16): trace store records blocked steps as NOT taken (spec P2-6); ShieldAgent runs config A (aux `low`, planner `medium`, ε = 0.1; ε = 0 reported only if it differs); configurations (a) no shield, (b) Direct, (c) ShieldAgent; τ-bench TEST-split tasks of `splits.json` (airline 20, retail 46), 3 trials each; gpt-5-nano agent + gpt-5-nano user simulator (`user_strategy="llm"`), as in P0.

## Implementation (`repro_online/`, leakage test extended to it)
| Piece | Where | Notes |
|---|---|---|
| shielded agent loop | `repro_online/episode.py` | τ-bench `ToolCallingAgent.solve` re-implemented with a guard hook; same message format, first tool call only, `max_num_steps` = 30 executed actions |
| guards | `repro_online/guards.py` | none / Direct (`repro_runtime.direct`, `medium`) / ShieldAgent (`repro_runtime.shield`, config A) |
| runner | `repro_online/run.py` | parallel episodes, resumable `episodes.jsonl` |
| trace store (P2-6) | `repro_runtime/shield.py` | blocked steps not appended; `Shield.commit` for cap overrides; test `TraceStoreOnline` |
| gold scorer (D9, scoring only) | `scripts/reproduction/p6_gold_score.py` | Step-2 firing logic (`scripts/validate_aspm.py` Parser/kleene reused): Python-evaluable gold `block` rules on executed write calls and on blocked write attempts |
| metrics | `scripts/reproduction/p6_metrics.py` | pass^1/pass^3 with bootstrap CIs over tasks (10k resamples), blocks, cap overrides, compliance, precision proxy, rules, cost/latency, failures |

## Online adaptations (documented, not method changes)
- **O1 Blocked respond.** τ-bench has no channel for a note to the agent. The blocked message stays in the agent's context and the feedback follows as a `system` message; the user never sees either. (Checked: the Azure deployment accepts a mid-conversation system message.)
- **O2 Step budget.** `max_num_steps` = 30 counts executed actions (as in τ-bench, where every loop iteration executes one); blocked attempts are bounded by the cap (≤ 3 per executed step).
- **O3 Cap override.** The 4th attempt after 3 consecutive blocks is still shielded (logged), then executed and recorded as taken; `cap_override` = executed although the shield blocked it.
- **O4 Seeds.** The deployment exposes no temperature/seed for gpt-5-nano, so "same seeds" means the same task indices and trial numbers across configurations; sampling differs.
- **O5 Direct feedback.** Direct has no separate feedback field; its block message is `BLOCKED by policy guardrail. Violated rules: [P1] <statement>; … Explanation: <explanation>` (the empty "Feedback:" part is omitted, `render_feedback`).

- **O6 Resources.** The first full-run launch (all 6 domain × guard jobs at once, 8 episode threads each) exhausted the 1.9 GB VM (swap 1.85/2 GB, ~60 % iowait); after 36 min it had finished 51 retail episodes and no airline episode. Stopped and relaunched in two phases of 3 processes (retail × 3 guards with 8 workers, then airline × 3 guards with 6 workers); `episodes.jsonl` is resumable, so finished episodes were kept and only in-flight episodes were redone. Later the airline jobs were started as soon as a slot freed (≤ 3 processes at any time). Not a method change.

- **O7 Disconnect check and resume (2026-10-17).** The session's monitors stopped overnight with the connection; the P6 jobs themselves had been started with `nohup` and all finished (driver log: airline direct ended 18:15, airline shield DONE after 7,293 s). Check: no P6 process running; every `episodes.jsonl` complete (airline 60/60 × 3 guards, retail 138/138 × 3 guards), no corrupt or duplicate lines. One conversation had no final result: retail / ShieldAgent task 65 trial 1 ended with an **Azure content-filter rejection of the agent's prompt** (HTTP 400 `content_filter`, category "sexual: high"; a false positive on a retail conversation), not with a disconnect. Only that conversation was resumed, with the same configuration (`repro_online.run --env retail --guard shield --tasks test --trials 3 --tag full`; the runner skips every (task, trial) with a clean result), launched with `setsid nohup`. The file before the resume is kept as `episodes.before_resume.jsonl`; metrics use the latest record per (task, trial), and the original failure is reported under failures. Result: the resumed conversation finished without error (reward 1, 7 blocks, 2 cap overrides, 367 s); all 594 conversations now have a clean result. Report: `p6_report.md`.

## Bugs (fixed, each listed)
| # | Found | Bug | Fix | Effect on results |
|---|---|---|---|---|
| P6-B1 | retail full run: `retail_none.log` had no per-episode or DONE lines although all 138 episodes were written | `repro_online/run.py` wrapped `get_env` in `contextlib.redirect_stdout` inside the worker threads; `redirect_stdout` swaps `sys.stdout` for the whole process, so concurrent threads swallowed the main thread's progress prints | redirect removed from the worker threads (the airline phase runs the fixed code; the retail processes already running kept the old code, so their completion was tracked by process exit and episode counts) | none: episodes, rewards and records are written by the workers independently of stdout |
