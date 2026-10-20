# AGENTS.md: onboarding for coding agents

Read this file first. `CLAUDE.md` is a symlink to this file. Numbers below come from the detailed reports: `docs/reproduction/p6_report.md` for the reproduction, `docs/tgr/*_report.md` for the post-reproduction (TGR) stage; `docs/RESULTS.md` collects every experiment in one place, and `docs/SUMMARY_REPORT.md` is the plain-language summary for advisors.

## 1. Research goal and rules of the game
This is a master's research project in two stages: (1) a **faithful reproduction of ShieldAgent** (ICML 2025, arXiv 2503.22738v2, `docs/paper/shieldagent.pdf`) on **τ-bench v1 (airline, retail)** with gpt-5-nano (P0–P6, done); (2) **TGR**, our tool-grounded rule guard developed against that baseline (`docs/tgr/`; method frozen, final evaluation pending). Rules:
- **Faithful.** Follow the paper; use App. H prompts verbatim. Any change, even format-only, is documented as a deviation or interpretation (`docs/reproduction/spec.md`, `docs/reproduction/prompts_provenance.md`, and the stage logs). The paper leaves gaps (App. C.5 and D are empty); each gap-filling choice is a numbered decision in `spec.md`.
- **Never hand-fix rules.** Method-produced problems are reported as findings. Never edit `aspm_repro/` or any result file.
- **Gold is for scoring only.** The hand-written gold standard must never feed a method. It consists of `aspm/`, `policies/curated/`, `policies/predicates/`, `policies/tau_bench/`, `policies/gold_v2/`, `agent/predicates/`, and `scripts/aspm_src/`. `tests/repro/test_repro_pipeline.py::NoGoldLeakage` enforces this for `repro_core/`, `repro_pipeline/`, `repro_runtime/`, `repro_online/`, `exp_core/` and `method_tgr/`, and keeps the method packages (`repro_pipeline/`, `repro_runtime/`, `method_tgr/`, `exp_core/policy_filter.py`) free of domain words. Extend it when you add a package.
- **Models.** The reproduction (P0–P6) uses **gpt-5-nano only** for every role. The TGR stage chooses models per role through **profiles** (`exp_core/model_profiles.json`, §4d): `gpt-6-luna` for development (train and val only), `grok-4.7` reserved for the final test evaluation. **Make no grok-4.7 call until the owner explicitly approves the final evaluation and its budget.**
- **Long jobs survive disconnects.** Use `setsid nohup … &`, write results incrementally, and make runs resumable (every existing runner is). Wait on process exit or explicit "DONE"/"stage done" log lines, never on guessed file counts.
- **Frozen method (TGR).** `method_tgr/` and the rule sets `tgr_rules/<domain>/frozen/` are frozen at git tag **`tgr-frozen-v1`** (iteration 5). No method change after seeing validation, weak-agent or test results.
- **Frozen code.** `repro_core/` and `repro_pipeline/` are frozen at git tag **`repro-p1-v1`**. Check with `git hash-object <file>` vs `git rev-parse repro-p1-v1:<file>`; the directories were untracked when tagged, so `git diff` is misleading. Retail P1 ran on exactly this code.
- Do not modify the authors' code (`agent/`, `utility/`, `app.py`).
- **τ-bench: two copies.** `~/refs/tau-bench` is a **read-only reference clone**: its recorded `historical_trajectories/` are read as data, and its code is never executed. **All runs** (P0 smoke, P6) use the τ-bench package **installed in `~/venvs/tau-bench`** (from `~/opt/tau-bench-59a200c`, pinned commit 59a200c).
- **Policy input.** P1 (and the Direct guard) read **`policy_docs/airline_wiki.txt`** and **`policy_docs/retail_wiki.txt`**. Both are byte-identical to τ-bench's own `tau_bench/envs/<domain>/wiki.md`: the SHA-256 was checked on 2026-10-17 against the installed package and the reference clone, and is recorded in `aspm_repro/<domain>/manifest.json` → `input`. Nothing under `policies/` (gold, curated, tool lists) is ever a method input.
- **Data splits.** New methods are developed and tuned **only on train-split tasks**. The test split is run **once**, for final numbers, exactly as P2 (offline pilot on train tasks) vs P6 (online, test tasks). Splits are task-level and live in **`output/reproduction/labels/splits.json`** (git-ignored, in the backup; made by `scripts/reproduction/make_splits.py`, seeded). Task counts (τ-bench test-set task indices): **airline train 20 / val 10 / test 20; retail train 46 / val 23 / test 46.**
- **Git.** `origin` = the owner's private repo (`https://github.com/yanai-1701/ShieldAgent_Taubench.git`); `upstream` = the paper authors' repo (`BillChan226/ShieldAgent`, push URL set to `DISABLED`). Commit and push **only when asked**, and push **only to `origin`**; never push to `upstream`.
- Stop and report after each requested step; do not start the next stage unasked.

## 2. Paper → code map
| paper component | file :: function |
|---|---|
| §3.2.1 policy extraction (App. H prompt 1) | `repro_pipeline/stages.py::e1_policies`, `repro_pipeline/prompts/e1_policy_extraction.md` |
| §3.2.2 LTLf rule extraction (App. H prompt 2) | `stages.py::e2_rules`, `repro_pipeline/prompts/e2_ltl_extraction.md`; format-only repair `repro_pipeline/rules.py::validate_or_repair` |
| LTLf syntax and semantics | `repro_core/ltlf.py::parse`, `evaluate` (Kleene), `syntax_errors`; tests vs flloat in `tests/repro/test_ltlf.py` |
| §3.2.3 vagueness (Eq. 3) | `repro_pipeline/vagueness.py::vagueness`, `rule_vagueness`, `similarity_matrix`; embeddings `repro_core/embed.py::embed` (bge-large-en-v1.5, bf16) |
| Alg. 2: Verifiability Refinement + Redundancy Pruning | `stages.py::alg2` (`vr_task`, `_rp_clusters`), prompts `repro_pipeline/prompts/{e3_verifiability_refinement,e4_redundancy_pruning,fewshot_vr,fewshot_rp}.md` |
| Alg. 3: rule circuits (spectral clustering, merge) | `stages.py::e5_circuits`; ASPM assembly (authors' JSON format) `stages.py::assemble` |
| rule weights θ | `weights.json` (Stage A: all 1.0); `repro_runtime/aspm.py::ASPM.weight` |
| P1 CLI | `repro_pipeline/run.py` (`python -m repro_pipeline.run --help`) |
| Alg. 1: shielding one step | `repro_runtime/shield.py::Shield.step` (`_step`), per-conversation trace store `Conversation` |
| action grounding (EXTRACT) | vocabulary table `repro_runtime/vocab.py::build`; per step `repro_runtime/extract.py::extract` |
| RETRIEVE circuit | `repro_runtime/aspm.py::ASPM.circuit` (authors' `get_action_circuit` semantics); loader `aspm.py::load` |
| relevance / solution-space formulation (Fig. 15) | `repro_runtime/plan.py::relevance` |
| planner with Search / Binary-Check (Fig. 16–17) | `repro_runtime/plan.py::planner` (function-calling loop `repro_core/llm.py::run_tool_loop`) |
| VERIFY (formal verification) | `repro_runtime/verify.py::rule_value`, `prefix_eval` (three-valued prefix semantics) |
| Eq. 4 (MLN) and Eq. 5 (safety condition with ε) | `repro_runtime/mln.py::decide`, `connected_group` |
| feedback / explanation (Fig. 19) | `repro_runtime/shield.py::render_feedback`, prompt `repro_runtime/prompts/explain.md` |
| Direct baseline (§5.1) | `repro_runtime/direct.py::direct` |
| online integration in τ-bench | `repro_online/episode.py::run_episode`, `repro_online/guards.py`, CLI `repro_online/run.py` |
| τ-bench adapters | trajectory → steps `repro_core/taubench_steps.py`; Azure shim for τ-bench `repro_core/taubench_run.py::make_completion` |
| Eq. 6 weight learning, workflow memory, GuardAgent, Detect tool | **not implemented** (Stage B / omitted; `spec.md` "Stage A scope") |
| D9 compliance scorer (gold, scoring only) | `scripts/reproduction/p6_gold_score.py` (reuses `scripts/validate_aspm.py` Parser/kleene) |
| metrics | `scripts/reproduction/p6_metrics.py`; P2 pilot `scripts/reproduction/p2_pilot_summary.py` |

### TGR (post-reproduction method) → code map
| component | file :: function |
|---|---|
| per-role model routing (agent, user, guard, rule building) | `exp_core/models.py::activate`, `make_completion`, `run_tool_loop`; profiles `exp_core/model_profiles.json` |
| Domain Basic filter (rule-building input only) | `exp_core/policy_filter.py` (limitation L1, `docs/tgr/known_limitations.md`) |
| ShieldAgent P1 rebuild with a profile (frozen code) | `exp_core/run_p1.py` |
| online runner with profiles | `exp_core/run_online.py` (`--profile`, `--aspm-dir`, `--rules-dir`) → `output/tgr/online/<tag>/` |
| policy sentence numbering (coverage unit) | `method_tgr/policy_text.py::number_sentences` |
| B: restriction-only rule writing (one call), validation, repair, exact duplicates, circuits by tool | `method_tgr/rules.py::build_rules`, `validate`, `dedupe`, `circuits`; prompts `method_tgr/prompts/rules_*.md`, `form_restriction.md`, `scope.md`, `dispositions.md` |
| A: tool grounding (actions = tools + respond; evidence sources) | `method_tgr/rules.py::tool_list`, `prompts/actions_tools.md`, `predicates_grounded.md`; runtime `method_tgr/runtime.py::TGR._actions` |
| judge (one call per restricted step) | `method_tgr/runtime.py::TGR._judge`, prompt `method_tgr/prompts/judge.md` |
| decision (Eq. 4–5, unchanged) | `repro_runtime/mln.py::decide` via `method_tgr/rules.py::to_aspm` |
| C: actionable feedback | `method_tgr/feedback.py::actionable` (not-C: ShieldAgent's `explain`) |
| rule-build CLI | `exp_core/tgr_build.py` → `output/tgr/tgr_rules/<profile>/<domain>/<run>/`; published `tgr_rules/<domain>/{full,nob,frozen}/` |
| guard registration | `repro_online/guards.py::TGRGuard` (`tgr`, `tgr_nob`, `tgr_noc`, `tgr_noa`) |
| gold scorer v2 (scoring only) | `policies/gold_v2/checks.py`; `scripts/reproduction/p6_gold_score.py --gold v2`, `p6_metrics.py --gold v2`, `gold_compare.py` |
| TGR-stage metrics | `scripts/tgr/metrics.py <tag>` (P6 metrics v1 + v2, paired Δ, repeat-after-block, violations attempted/blocked/executed, transfers); `scripts/tgr/dev_summary.py <tag>` |

## 3. Deviations and interpretations
- `docs/reproduction/spec.md` is the master list:
  - component-by-component faithful / adapted / new classes;
  - deviations **A1–A7**;
  - decisions D1–D13 (**D1**: bf16 embeddings);
  - "Implementation choices fixed during P1" (I8 depth rule, three-valued prefix semantics);
  - **P2-1…P2-6**:
    - P2-1: exact connected-group MLN;
    - P2-2: only definitely false rules are violated;
    - P2-3: predicate type resolution;
    - P2-4: evaluation position;
    - P2-5: precedence (finding only);
    - P2-6: blocked steps are not taken;
  - the **ε sign** interpretation: allowed iff P(µ=1) − P(µ=0) ≥ −ε.
- `docs/reproduction/gap_audit.md`: what the authors' code has and lacks (no ASPM builder, VR/RP, weights, MLN, baselines or metrics).
- `docs/reproduction/prompts_provenance.md`: prompt-by-prompt provenance. Runtime prompts are marked [paper] / [authors] / [new] in `docs/reproduction/p2_log.md`.
- Online adaptations O1–O7 (blocked respond as a system note, step budget, cap override, no seeds, …) are in `docs/reproduction/p6_log.md`.

## 4. Project history (in order)
1. **Orientation and authors' code** (2026-10-12…14): Azure/Managed-Identity refactor of the authors' repo, and AutoPolicy runs with gpt-5-nano (`output/deep_policy/`). Docs: `docs/orientation_summary.md`, `docs/planning/`.
2. **Step 1, gold rule audit:** curated clauses and rules for τ-bench airline/retail. Docs: `docs/step1_rule_audit/`; data: `policies/curated/`.
3. **Step 2, gold ASPM:** hand-written ASPMs and deterministic predicates. Docs: `docs/step2_aspm/design_notes.md`, `firing_analysis.md`; data: `aspm/`, `agent/predicates/`, `scripts/aspm_src/`.
4. **Step 2b, our automatic pipeline** (pre-reproduction; tag `auto-pipeline-v1`): Docs: `docs/step2b_auto/report.md`, `summary_for_pi.md`; code: `policy_pipeline/` (its `llm.py` is still the shared LLM caller), `eval/`, `aspm_auto/`.
5. **Goal change to a faithful reproduction** (2026-10-15): `docs/reproduction/spec.md`, `gap_audit.md`, `data_feasibility.md` (labels, splits), `plan.md`.
6. **P0 infrastructure + P1 extraction:** `docs/reproduction/p1_log.md`, `p1_report.md`, `airline_v4_rules.md`, `retail_v1_rules.md`; ASPMs published to `aspm_repro/`.
7. **P2 runtime + offline pilot:** `docs/reproduction/p2_design.md`, `p2_log.md`, `p2_pilot_report.md`.
8. **P6 online evaluation** (594 conversations): `docs/reproduction/p6_log.md`, `p6_report.md`.
9. **Cleanup and docs** (2026-10-17): `docs/cleanup/`, `docs/STRUCTURE.md`, this file.
10. **TGR Phase 0** (2026-10-19): model access (gpt-6-luna, grok-4.7), per-role profiles, Domain Basic filter, cost pilot; decisions M1–M6. `docs/tgr/p0_report.md`, `plan.md`.
11. **Phase 1:** ShieldAgent P1 rebuilt with luna; train baselines none / Direct / ShieldAgent (594 conversations). `docs/tgr/p1_report.md`, `phase1_log.md`.
12. **Gold scorer v2** (2026-10-20): confirmation + cancellation-eligibility checks; P6 and Phase 1 re-scored. `docs/tgr/scorer_v2_report.md`.
13. **Phase 2:** TGR built (`method_tgr/`), iterations 1–4, ablations (−B, −C) on train; iteration 5, then frozen (tag `tgr-frozen-v1`). `docs/tgr/phase2_design.md`, `phase2_log.md`, `p2_report.md`.
14. **Validation check** (val split, luna): frozen TGR vs baselines. `docs/tgr/val_report.md`.
15. **Weak agent + strong guard** (gpt-5-nano agent, luna user and guards, train). `docs/tgr/nano_agent_report.md`.
16. **Consolidated docs** (2026-10-20): `docs/RESULTS.md`, `docs/SUMMARY_REPORT.md`.

## 4a. ShieldAgent Stage-A configuration (as evaluated in P6)
| setting | value | where it is set |
|---|---|---|
| rule weights θ | 1.0 for every rule (no weight learning) | `aspm_repro/<domain>/weights.json` (written by `repro_pipeline/stages.py::assemble`); read by `repro_runtime/aspm.py::ASPM.weight` |
| ε and its sign | ε = 0.1; allowed iff P(µ=1) − P(µ=0) **≥ −ε** (interpretation of Eq. 5; spec "ε sign"); ε = 0 never gave a different decision | `repro_runtime/shield.py::ShieldConfig.epsilon` (default 0.1), `repro_online/guards.py::ShieldGuard(epsilon=0.1)`; test in `repro_runtime/mln.py::decide` |
| config A (reasoning effort) | auxiliary calls (vocabulary, EXTRACT, relevance, Search, Binary-Check, explanation) `low`; planner `medium` | `ShieldConfig.aux_effort` / `.planner_effort`, `ShieldGuard` defaults |
| planner turns, history length | ≤ 15 tool-loop turns; history tail-truncated at 24,000 characters | `ShieldConfig.max_turns`, `ShieldConfig.history_chars` |
| MLN inference | exact over the connected group of unknowns (P2-1); Gibbs above 16 unknowns (never needed) | `ShieldConfig.gibbs_threshold`, `repro_runtime/mln.py` |
| block cap and cap override | after 3 consecutive blocks at the same step, the 4th attempt is executed (`cap_override`), still shielded for the log and recorded as taken (P2-6) | `repro_online/episode.py::run_episode(cap=3)` |
| step budget | max 30 **executed** actions per conversation (blocked attempts do not count) | `run_episode(max_num_steps=30)`, `repro_online/run.py --max-steps 30` |
| Direct guard | one call with the complete wiki, effort `medium` | `repro_online/guards.py::DirectGuard(effort="medium")`, `repro_runtime/direct.py` |

## 4b. Adding and evaluating a new guard
**Interface** (`repro_online/guards.py`; see `NoGuard`, `DirectGuard`, `ShieldGuard`, `TGRGuard`). For runs with other models use `exp_core.run_online` (§4d) instead of `repro_online.run` (gpt-5-nano only):
```python
class MyGuard:
    name = "myguard"
    def new_episode(self):                       # → per-conversation state (or None)
        ...
    def check(self, state, executed, msg, index):
        # executed: list of chat messages actually executed so far (system wiki, user/agent/tool turns; blocked
        #           attempts and feedback are NOT in it, P2-6). Build a step with guards.make_step(executed, msg, index).
        # msg: the agent's next assistant message (dict; at most one tool call, already truncated); index: executed-step count.
        # return None (not checked) or a dict with at least:
        #   {"action_allowed": bool, "feedback_text": str (when blocked), "seconds": float,
        #    "usage": {"cost_usd": float, "n_llm_calls": int},
        #    "violated_rules": [{"rule_id": str, "description": str}, ...]}   # used for the top-blocking-rules table
    def commit(self, state, rec):                # called when a blocked attempt is executed through the cap override
        ...
```
**How a block is delivered** (`repro_online/episode.py::run_episode`):
- a blocked tool call is not executed, and `feedback_text` is returned as its tool response (same `tool_call_id`);
- a blocked respond is not sent to the user, and the agent receives `feedback_text` as a `system` message;
- after 3 consecutive blocks the next attempt is executed (`cap_override`) and `commit` is called.

`shield.render_feedback(violated, explanation, feedback)` gives the standard text ("BLOCKED by policy guardrail. Violated rules: …").

**Register it** in three places (code change):
- `guards.build`;
- the `--guard` `choices` in `repro_online/run.py`;
- the guard tuple `("none", "direct", "shield")` in `scripts/reproduction/p6_metrics.py`. `p6_gold_score.py` already scans every guard folder.

**Develop on train tasks only**, for example:
```bash
$PY -m repro_online.run --env retail --guard myguard --tasks train --trials 1 --tag dev --workers 6
```
**Final run on the test split, 3 trials** (≤ 3 processes at once; resumable):
```bash
setsid nohup $PY -u -m repro_online.run --env airline --guard myguard --tasks test --trials 3 --tag full --workers 6 \
  >> output/repro/p6/full/logs/airline_myguard.log 2>&1 &
setsid nohup $PY -u -m repro_online.run --env retail  --guard myguard --tasks test --trials 3 --tag full --workers 8 \
  >> output/repro/p6/full/logs/retail_myguard.log 2>&1 &
```
Using tag `full` puts the new guard next to the reported baselines. The existing guards' files are not touched: the runner only appends to its own `<domain>/<guard>/episodes.jsonl`.

**Metrics and gold compliance** (no LLM calls):
```bash
$PY scripts/reproduction/p6_gold_score.py full      # D9 gold scorer (scoring only) → <domain>/<guard>/gold.jsonl
$PY scripts/reproduction/p6_gold_score.py full --gold v2   # gold v2 (adds confirmation + cancel eligibility) → gold_v2.jsonl
$PY scripts/reproduction/p6_metrics.py full         # pass^1/pass^3 + bootstrap CIs, blocks, cap overrides,
                                                    # compliance, block precision, top rules, cost, latency
```

**Expected cost and runtime.** P6 cost **$20.81** and about **5.5 h** for all 594 conversations (66 test tasks × 3 trials × 3 configurations, at most 3 processes on the 1.9 GB VM). Per configuration, airline + retail (198 conversations):
- no shield: $2.66, 217–262 s per conversation;
- Direct: $5.00, 352–415 s;
- ShieldAgent: $13.16, 676–823 s; wall time per job with 6–8 workers: airline about 2 h, retail about 3.5–4 h.

A new guard costs roughly the no-shield cost ($0.013–0.015 per conversation) plus its own cost per check times about 16–22 checks per conversation (observed for Direct and ShieldAgent, blocked attempts included).

**The baseline to beat is Direct**, not "no shield". Direct is ahead of ShieldAgent on pass^1, block precision and cost (`p6_report.md` §2, §5, §7). A new method should report its paired pass^1 difference against Direct, its block precision, and its cost.

## 4c. Dependency on `policy_pipeline/` and `eval/` (audit 2026-10-17)
| importer | symbol | class |
|---|---|---|
| `repro_core/llm.py` (all structured calls; `run_tool_loop`) | `policy_pipeline.llm.LLM`, `_get_client`, module config (timeout) | infrastructure: LLM client, disk cache, retries, usage; prompts are sent verbatim |
| `scripts/reproduction/p1_gold_diagnostic.py` | `eval.common.gold`, `eval.common.aligned`, `policy_pipeline.common.find_span` | gold loader / span parsing, **diagnostic only** |

**No method logic** (prompts, rule construction, predicate generation, verification, decision) comes from these packages. Details: `docs/reproduction/gap_audit.md` (addendum).

## 4d. Model profiles: running each role/model combination
Profiles in `exp_core/model_profiles.json` name a model per role (`rulebuild`, `guard`, `agent`, `user`; agent/user also `api` and `effort`). One process serves one structured role (`exp_core.models.activate(profile, role)`); caches are in `output/tgr/_llmcache/`, apart from the nano caches; cost uses the list prices in the same file.

| profile | agent | user simulator | guards | rule building | use |
|---|---|---|---|---|---|
| `luna-dev` | gpt-6-luna (Responses, medium) | gpt-6-luna (Responses, medium) | gpt-6-luna | gpt-6-luna | development on train, validation |
| `nano-agent-luna` | gpt-5-nano (Chat, P6 settings) | gpt-6-luna | gpt-6-luna | gpt-6-luna | weak agent + strong guard |
| `grok-eval` | grok-4.7 | grok-4.7 | grok-4.7 | grok-4.7 | **final test evaluation only, after approval** |

```bash
PY=~/venvs/tau-bench/bin/python
# online runs (resumable; output/tgr/online/<tag>/<env>/<guard>/episodes.jsonl)
$PY -m exp_core.run_online --profile luna-dev --env retail --guard none   --tasks train --trials 3 --tag mytag --workers 8
$PY -m exp_core.run_online --profile luna-dev --env retail --guard direct --tasks train --trials 3 --tag mytag --workers 8
$PY -m exp_core.run_online --profile luna-dev --env retail --guard shield --tasks train --trials 3 --tag mytag --workers 8 \
    --aspm-dir output/tgr/aspm_runs/luna-dev/retail/v1          # ShieldAgent with the luna-rebuilt ASPM
$PY -m exp_core.run_online --profile luna-dev --env retail --guard tgr    --tasks train --trials 3 --tag mytag --workers 8 \
    --rules-dir tgr_rules/retail/frozen                         # frozen TGR
# rebuild ShieldAgent P1 / TGR rules with a profile (LLM calls cached)
$PY -m exp_core.run_p1 --profile luna-dev --domain retail --policy policy_docs/retail_wiki.txt --drop-heading "Domain Basic" --run-id v1
$PY -m exp_core.tgr_build --profile luna-dev --env retail --run-id myrun --effort high      # --no-b for the ablation
# metrics (no LLM calls)
$PY scripts/tgr/metrics.py mytag --guards none,direct,shield,tgr
```

## 5. Bugs and incidents (one line each)
| id | what | where logged |
|---|---|---|
| I1 | VR wave barrier → rolling worker pool | `p1_log.md` |
| I2 | stalled requests → client timeout 420 s, no hidden retries | `p1_log.md` |
| I3 | domain-word test flagged "in flight" → wording change | `p1_log.md` |
| I4 | few-shot examples copied into rules (airline v1 invalid) → delimited few-shot + copy guard | `p1_log.md`, `prompts_provenance.md` |
| I5 | memory thrash → bf16 embeddings (D1), converted model copy | `p1_log.md` |
| I6 | embeddings moved into worker tasks | `p1_log.md` |
| I7 | format repair changed meaning (28 cases in v3) → declaration repair + checked syntax repair | `p1_log.md` |
| I8 | RP output depth = MIN of parents (was MAX: artificial convergence) | `p1_log.md`, `spec.md` |
| B1 | blocks caused only by unknown predicates named no rule → `at_risk` rules used for V_s | `p2_log.md` |
| P6-B1 | `redirect_stdout` in worker threads swallowed progress lines (logging only) | `p6_log.md` |
| O6 | 6 parallel P6 jobs thrashed the 1.9 GB VM → ≤ 3 processes, resumed | `p6_log.md` |
| O7 | Azure content-filter false positive (retail ShieldAgent task 65 trial 1) → only that conversation rerun | `p6_log.md` |
| T-1 | Phase 1: the same content-filter false positive with luna (retail none task 52 trial 1) → only that unit resumed | `docs/tgr/phase1_log.md` |
| T-2 | a diagnostic process (`scripts/reproduction/p1_trace.py`) hung for 33 h on the only CPU during Phase 1 → stopped; Phase 1 wall times inflated | `docs/tgr/phase1_log.md` |
| T-3 | rule writing at effort high exceeded the 420 s client timeout → `exp_core/tgr_build.py --timeout 1800` for the build process | `docs/tgr/phase2_log.md` (it4) |
| T-4 | `pkill -f <pattern>` / `pgrep -f` matched the calling shell's own command line (killed or never ended the caller) → kill by PID | this file |

## 6. Environment gotchas
- **VM:** 1.9 GB RAM, 1 CPU. At most **3** heavy Python processes at once: each P6 job is about 350 MB, and the IDE server also uses memory. The main conda env has a broken torch, so always use `~/venvs/tau-bench/bin/python`.
- **Embeddings:** local bge-large-en-v1.5 in **bfloat16** (`output/repro/_models/`, D1). No Azure embedding deployment exists. Airline v1/v2 used fp32.
- **gpt-5-nano on this deployment accepts no temperature and no seed.** Reproducibility comes from the disk caches (`output/repro/_llmcache/`, `output/auto_aspm/_cache/`; prompt-keyed). "Same seeds" across configurations means the same task and trial indices.
- **Azure content filter** gives false positives (for example "sexual: high" on a retail conversation), with gpt-5-nano and gpt-6-luna alike. They surface as an HTTP 400 `content_filter` error recorded in `episodes.jsonl`. Rerun only the affected unit (the runners skip finished units; keep the old file as `episodes.before_resume.jsonl`).
- **gpt-6-luna tool calls only via the Responses API.** luna cannot use Chat-Completions tools while reasoning, and accepts no temperature other than 1 (decisions M1, M3). `exp_core/models.py::make_completion` adapts τ-bench's chat messages to the Responses API; gpt-5-nano in `nano-agent-luna` keeps P6's Chat-Completions path.
- **Hung processes.** Check `ps` for leftovers before long runs (incident T-2): one stuck process on the 1-CPU VM slows every job. Never match processes with `pkill -f` patterns that also occur in your own command line (T-4).
- **τ-bench user-simulator cost** is under-counted by τ-bench itself (it keeps only the last call); `exp_core/run_online.py` meters every call. P6 user costs are too low (`p6_report.md` §7 note).
- **τ-bench quirks:**
  - `update_reservation_flights` never writes `reservation.cabin` (`docs/step2_aspm/design_notes.md`);
  - no tool exposes a non-available flight status;
  - ground-truth conflicts: airline tasks 26/27 cancel the fully flown NQNU5R; retail 18/108 exchange an item for an identical one (`docs/step2_aspm/firing_analysis.md`, `docs/reproduction/data_feasibility.md`).
- **Expected-action labels are noisy:** "unsafe" means a policy violation in only ≈ 35–40 % of cases (`data_feasibility.md` §4).
- **The nano user simulator speaks like the agent** in about 30 % of conversations (`p6_report.md` §9).
- `output/` is **git-ignored** (results and caches). Backups are tar.gz archives in `~/backups/` with a `.sha256`, each also uploaded as a GitHub release `results-backup-<date>` (list and restore steps in `README.md` → "Backup & restore"). Re-run the backup after new results.

## 7. Main findings
- **Headline (pass^1; Δ vs no shield paired by task):**
  - airline: no shield 0.300, Direct 0.267, ShieldAgent 0.250 (Δ −0.05, CI includes 0);
  - retail: no shield 0.348, Direct 0.391, ShieldAgent **0.145** (Δ −0.20, CI −0.31 to −0.10).
- **Blocks:** ShieldAgent averages 4.5 (airline) and 10.4 (retail) blocks per conversation, with 301 cap overrides in retail.
- **Precision:** on blocked write calls the gold scorer confirms 0.13 / 0.24 for ShieldAgent vs 0.52 / 0.59 for Direct.
- **Cost:** $0.055–0.071 per conversation vs $0.024–0.029 for Direct.
- **D9 scorer limitation:** the gold scorer evaluates only Python-evaluable gold `block` rules. It **misses cancellation-eligibility violations** (AIR-R042 needs dialogue predicates) and **user-confirmation / unrequested-action violations**. The manual audit found 3 missed calls in 20 episodes and no false positives. Compliance numbers are therefore **upper bounds** (`p6_report.md` §4). **Gold v2** (2026-10-20, `policies/gold_v2/`, `docs/tgr/scorer_v2_report.md`) adds dialogue checks for cancellation eligibility and explicit confirmation; run the scorer and metrics with `--gold v2` (outputs `gold_v2.jsonl`, `metrics_gold_v2.json`) and compare with `scripts/reproduction/gold_compare.py <tag>`. v1 stays the default and is what `p6_report.md` reports.

- **TGR stage (all numbers in `docs/RESULTS.md`):**
  - with gpt-6-luna, ShieldAgent still loses to Direct (retail train −0.32, CI −0.46 to −0.18);
  - frozen TGR is the best guard on train and on val (val pass^1 airline 0.633, retail 0.710 vs Direct 0.567 / 0.609; retail Δ +0.10, CI 0.00 to +0.22), with 0.1–0.4 blocks per conversation, no cap overrides, few transfers and Direct-level cost;
  - ablations: neither B nor C changes pass^1 measurably on train;
  - the strong luna agent attempts very few violations, so precision and violations caught are small-number statistics; the weak-agent experiment (`docs/tgr/nano_agent_report.md`) tests the safety side.

**Six failure causes** (grouped from `p6_report.md` §3/§6/§10 and `p2_pilot_report.md` findings F1–F11):
1. **Missing or unenforceable rule content.** Examples: cancellation eligibility, certificate rules, "return/exchange only if delivered", explicit confirmation. Such violations cannot be blocked at all.
2. **Defective extracted rules.** Over-general timing and mutual-exclusion rules (airline 3/4; retail 3/4/29–32) block ordinary reads and replies. Retail rule 32 ("no tool call after the first order tool call") is one example.
3. **Abstract action mapping (EXTRACT, ≤ 3 predicates).** Reads get mapped to `respond_to_user`, returns and exchanges to `modify_order`, and specific predicates such as `cancel_entire_trip` are rarely chosen (1 in 9).
4. **Wrong or unknown predicate values.** The planner relies on direct inference and almost never uses Search or Binary-Check. Examples: "HAT005 is not an IATA flight number"; unknowns marginalised into a block.
5. **Structural limits of Eq. 5 with circuits keyed by action.** Physical rules (no action predicate) and obligations ("C IMPLIES action") can never block. Only restrictions on the invoked action can.
6. **Non-actionable feedback.** After a ShieldAgent block the agent repeats the identical call 35–53 % of the time, so the cap turns the shield into a delay. After a Direct block the agent almost never repeats it (0–1 %).

## 8. Open next steps
- **Final evaluation (Phase 3b): NOT started; needs the owner's explicit approval and budget.** grok-4.7 for every role, test split, once, 3 trials: no shield, Direct, ShieldAgent (P1 rebuilt with grok) and frozen TGR (rules rebuilt with grok by the frozen method). Estimate ≈ $300–480 (`docs/tgr/plan.md`). Cost estimate and approval first.
- **Optional before Phase 3b:** more val trials (narrower CIs); manual audit of the violations TGR let through.
- **Stage B (optional):** weight learning (Eq. 6, decisions D5–D7), offline evaluation (P5), workflow memory; plan in `docs/reproduction/plan.md` (P3–P5).
- **Further generic improvements** (not started), always evaluated against **Direct**: automatic rule verification (round-trip checks, satisfiability); code-computed predicates from tool outputs instead of LLM-judged values. (Tool grounding, restriction-only rules and actionable feedback are implemented in TGR.)

## 9. Where to look first
| task | start here |
|---|---|
| the whole story / all numbers | `docs/SUMMARY_REPORT.md` (advisors), `docs/RESULTS.md` (technical record) |
| understand a number in a report | `docs/reproduction/p6_report.md`, then `output/repro/p6/full/metrics.json`, `scripts/reproduction/p6_metrics.py`; TGR stage: `docs/tgr/*_report.md`, `output/tgr/online/<tag>/metrics*.json` |
| inspect one online conversation | `scripts/reproduction/p6_show_episode.py full <env> <guard> <task> <trial>`; audit view `scripts/reproduction/p6_audit_view.py` |
| see the extracted rules | `aspm_repro/<domain>/rules.md`, `aspm.json`; history `docs/reproduction/p1_log.md` |
| change or debug the runtime shield | `repro_runtime/shield.py` (flow), `mln.py`, `verify.py`, `plan.py`; tests `tests/repro/test_runtime.py`, `test_mln_decomposition.py` |
| change the online harness | `repro_online/episode.py`, `guards.py`, `run.py` |
| re-score compliance | `scripts/reproduction/p6_gold_score.py` (gold, scoring only; `--gold v2` adds confirmation + cancellation eligibility, `policies/gold_v2/README.md`) |
| post-reproduction stage (TGR) | plan `docs/tgr/plan.md`; models `exp_core/` (`model_profiles.json`, `run_online.py`); method `method_tgr/` (design `docs/tgr/phase2_design.md`, iterations `docs/tgr/phase2_log.md`); rule build `exp_core/tgr_build.py`; published rule sets `tgr_rules/`; metrics `scripts/tgr/metrics.py <tag>` |
| why a design choice was made | `docs/reproduction/spec.md` (decisions table), `p2_design.md` |
| folder and file map | `docs/STRUCTURE.md` |
| run things | `README.md` |
