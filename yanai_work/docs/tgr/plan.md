# TGR stage plan: generic improvements over the ShieldAgent baseline

All AGENTS.md rules apply: no hand-fixed rules, gold for scoring only, develop on train, test once, long jobs resumable
under `setsid nohup`, at most 3 heavy processes on the VM, every decision documented. Each phase ends with a report,
and the next phase starts only after the user approves it. The gpt-5-nano code and results stay untouched.

Models (exact deployment names): `gpt-6-luna` is the development model for every LLM role, on train tasks only.
`grok-4.7` is the evaluation model for every role, on test tasks, once. **No grok-4.7 call is made before the user
explicitly approves Phase 3.** Profiles: `exp_core/model_profiles.json` (`luna-dev`, `grok-eval`).

Rule-building input for every method: the policy without its Domain Basic section(s) (`exp_core/policy_filter.py`;
limitation L1 in `known_limitations.md`). The agent and the Direct guard keep the full wiki.

| phase | content | model / split | status |
|---|---|---|---|
| 0 | model access, smoke tests, prices, Domain Basic filter, per-role model config, cost estimate | luna + grok probes; 2 train tasks for the cost pilot | **done**, approved 2026-10-19 (`p0_report.md`; decisions M1–M6 confirmed) |
| 1 | rebuild ShieldAgent P1 (frozen code, model via profile, filtered policy) into a new output folder; train runs with 3 trials: no shield, Direct, ShieldAgent (Stage A); same metrics as P6 | gpt-6-luna, train | **done**, approved 2026-10-20 (`p1_report.md`) |
| 2 | new package `method_tgr/` + guard `tgr` (registered in the 3 places of AGENTS.md §4b). Components A tool grounding, B restriction-only rule writing with per-sentence dispositions, C actionable feedback, each behind a flag. Eq. 4–5 with θ = 1, ε = 0.1. Development loop on train with logged iterations. Report: final rules, train metrics vs Phase 1 | gpt-6-luna, train | **done** 2026-10-20 (`p2_report.md`), awaiting review |
| 3a | **ablations on train**: TGR full, TGR without B, TGR without C (3 trials) | **gpt-6-luna, train** | **done** as part of Phase 2 (`p2_report.md` §7) |
| 3b | final evaluation, once, only after explicit approval: cost estimate first; rebuild ShieldAgent P1 and TGR rules with grok-4.7; test runs with 3 trials: **no shield, Direct, ShieldAgent, TGR full**; report with bootstrap CIs as in `p6_report.md`. Success = beating Direct on pass^1 and on block precision | **grok-4.7, test** | not started |

**Component B, revised (user; recorded 2026-10-20). Restriction-only rule writing, in a single step.** This replaces
the shorter description of B in the Phase 2 row:
- The prompt makes the model write rules only in the form `tool_name IMPLIES condition`.
- Permissions and exceptions are folded into the matching restriction as an OR alternative; they are never dropped.
- Obligations tied to an action become preconditions on that tool. Facts produce no rule.
- In the same call, the model returns a disposition for every policy sentence: `rule <id>`, `exception in rule <id>`,
  `no rule: fact`, or `no rule: not enforceable` with a reason. The dispositions are saved as the coverage check.
- No RP merging; only exact duplicates are removed. Circuits are the rules grouped by tool.

**Plan change 2026-10-19 (user).** The ablations (TGR without B, without C) run on train with gpt-6-luna only. grok-4.7
on test runs only no shield, Direct, ShieldAgent and TGR full. This cuts the Phase-0 projection for Phase 3 from
≈ $500–850 to ≈ $300–480: the three grok baselines at ≈ $280, plus one TGR configuration at ≈ $60–180, plus about $25
for the rule rebuilds.
