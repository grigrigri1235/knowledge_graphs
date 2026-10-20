# Repository structure

State on 2026-10-20 (after the 2026-10-17 cleanup, plus the TGR stage: `exp_core/`, `method_tgr/`, `scripts/tgr/`, `policies/gold_v2/`, `tgr_rules/`, `docs/tgr/`, `output/tgr/`). Excluded: `.git/`, the τ-bench internals (installed package in `~/venvs/tau-bench`, source `~/opt/tau-bench-59a200c`, read-only reference clone `~/refs/tau-bench`), `__pycache__/`, `_to_delete/` (awaiting deletion by the owner), and the inside of cache folders.

**Tags:**
- **[in]** input;
- **[code]** source;
- **[out]** generated output or results;
- **[rep]** report or documentation;
- **[gold]** gold standard, scoring only (never read by the method; enforced by the leakage test);
- **[cache]** cache whose loss forces re-computation (paid if LLM);
- **[arch]** archived history;
- **[up]** the paper authors' original code (upstream, adapted to Azure in Stage 0).

`output/` and `archive/**/data/` are **git-ignored** (local data).

```text
ShieldAgent/
├── README.md                        [rep]  human entry point: goal, status, headline table, how to run
├── AGENTS.md                        [rep]  onboarding for coding agents (rules, paper→code map, history, bugs, gotchas)
├── CLAUDE.md -> AGENTS.md          [rep]  symlink (cannot drift from AGENTS.md)
├── LICENSE                          [up]   MIT license of the authors' repository
├── .gitignore                       [code] ignores output/, caches, _to_delete/, archive/**/data/
├── requirements.txt                 [up]   authors' requirements (the reproduction venv: docs/reproduction/venv_freeze.txt)
├── app.py                           [up]   authors' Gradio demo (policy extraction + shielding)
├── policy_extractor_async.py        [up]   authors' AutoPolicy extraction script (wrote output/deep_policy/)
├── shield -> agent                  [up]   symlink; authors' code imports `shield.*`
│
├── policy_docs/                     [in]
│   ├── airline_wiki.txt                    τ-bench airline policy (byte-identical to τ-bench wiki.md); P1 and Direct input
│   ├── retail_wiki.txt                     τ-bench retail policy; P1 and Direct input
│   ├── aba-formal-opinion-512.pdf   [up]   authors' sample policy document
│   ├── eu_ai_act_art5.pdf           [up]   authors' sample policy document
│   ├── eu_ai_act_art_5.txt          [up]   text version of the EU AI Act Art. 5 sample
│   └── nais2023.pdf                 [up]   authors' sample policy document
│
├── repro_core/                      [code] P0 infrastructure (frozen at tag repro-p1-v1)
│   ├── __init__.py
│   ├── config.json                         embedding backend/model/dtype (bf16), LLM effort/timeout/cache dir, pricing
│   ├── embed.py                            local bge-large-en-v1.5 embeddings (bf16 copy, SQLite cache)
│   ├── llm.py                              structured_llm() wrapper; run_tool_loop() function-calling loop (cached per turn)
│   ├── ltlf.py                             LTLf parser, Kleene evaluator, syntax checks, flloat export
│   ├── taubench_run.py                     Azure Chat-Completions shim for τ-bench (make_completion); 1-task runner
│   └── taubench_steps.py                   τ-bench trajectory → shielded steps (Step, steps_from_messages, render_history)
├── repro_pipeline/                  [code] P1 extraction (frozen at tag repro-p1-v1)
│   ├── __init__.py
│   ├── run.py                              CLI: policy → ASPM run directory (+ --publish)
│   ├── stages.py                           E1 policies, E2 rules, Alg. 2 (VR/RP), Alg. 3 circuits, ASPM assembly
│   ├── rules.py                            rule schemas, normalisation, validate_or_repair, predicate registry
│   ├── vagueness.py                        Eq. 3 vagueness, similarity matrix
│   ├── prompts.py                          prompt loader, prompt hashes
│   └── prompts/
│       ├── e1_policy_extraction.md         App. H policy-extraction prompt (+ documented format adaptations)
│       ├── e2_ltl_extraction.md            App. H LTLf rule-extraction prompt
│       ├── e3_verifiability_refinement.md  App. H VR prompt
│       ├── e4_redundancy_pruning.md        App. H RP prompt
│       ├── fewshot_vr.md                   paper Fig. 11/12 few-shot examples (delimited, I4)
│       ├── fewshot_rp.md                   paper Fig. 13 few-shot example
│       ├── format_repair.md                [new] format-only syntax repair
│       └── format_declare.md               [new] declaration repair for undeclared predicates (I7)
├── repro_runtime/                   [code] P2 runtime shield (Alg. 1), domain-agnostic
│   ├── __init__.py
│   ├── aspm.py                             ASPM loader, circuits, θ, P2-3 type resolution
│   ├── calls.py                            metered cached gpt-5-nano calls (fresh-equivalent accounting)
│   ├── vocab.py                            tool/respond → candidate action predicates (vocabulary table)
│   ├── extract.py                          EXTRACT: step → ≤ 3 action predicates
│   ├── plan.py                             relevance filter, predicate map, planner loop with Search/Binary-Check
│   ├── verify.py                           three-valued prefix LTLf evaluation (P2-2, P2-4)
│   ├── mln.py                              Eq. 4 MLN (exact connected group / Gibbs) and Eq. 5 decision, V_s
│   ├── shield.py                           Shield.step orchestration, trace store (P2-6), feedback rendering
│   ├── direct.py                           Direct baseline guard
│   ├── prompts.py                          prompt loader
│   └── prompts/                            vocab, extract, relevance, planner_system, planner_user, search,
│                                           binary_check, explain, direct (.md); provenance in docs/reproduction/p2_log.md
├── repro_online/                    [code] P6 online τ-bench harness
│   ├── __init__.py
│   ├── episode.py                          shielded ToolCallingAgent loop (blocking, feedback, cap override)
│   ├── guards.py                           none / Direct / ShieldAgent / TGR guards (TGRGuard: tgr, tgr_nob, tgr_noc, tgr_noa)
│   └── run.py                              CLI (gpt-5-nano only): parallel, resumable episodes → episodes.jsonl
├── exp_core/                        [code] TGR stage infrastructure: models per role, filtered policy input, runners
│   ├── __init__.py
│   ├── model_profiles.json          [in]   profiles luna-dev, nano-agent-luna, grok-eval (model/api/effort per role) + list prices
│   ├── models.py                           activate(profile, role): re-points the LLM seams; Responses-API agent/user adapter; per-episode metering
│   ├── policy_filter.py                    removes named headings (Domain Basic) from the rule-building input
│   ├── run_p1.py                           CLI: frozen ShieldAgent P1 with a profile → output/tgr/aspm_runs/<profile>/<domain>/<run>/
│   ├── run_online.py                       CLI: online episodes with a profile (--aspm-dir, --rules-dir) → output/tgr/online/<tag>/
│   └── tgr_build.py                        CLI: TGR rule build with a profile → output/tgr/tgr_rules/<profile>/<domain>/<run>/
├── method_tgr/                      [code] TGR method (domain-agnostic, no gold access; frozen at tag tgr-frozen-v1)
│   ├── __init__.py                         components A / B / C overview
│   ├── policy_text.py                      numbers policy sentences ([S<n>], the coverage unit)
│   ├── rules.py                            B (+A vocabulary): one-call rule writing, validation, repair, exact duplicates, circuits, → ASPM
│   ├── runtime.py                          TGR.step: action = tool, circuit, judge call, Eq. 4–5 (repro_runtime.mln), trace store
│   ├── feedback.py                         C: actionable feedback text (deterministic)
│   ├── llm.py                              metered structured calls with a per-call output budget
│   ├── prompts.py                          prompt loader and hashes
│   └── prompts/                            rules_system, rules_user, actions_{tools,free}, form_{restriction,general}, scope,
│                                           predicates_{grounded,plain}, dispositions, no_dispositions, example_{restriction,general},
│                                           repair, judge (.md)
│
├── scripts/
│   ├── build_aspm.py                [gold] builds aspm/*.json from scripts/aspm_src/
│   ├── aspm_src/{airline,retail,common}.py [gold] hand-written gold ASPM sources
│   ├── validate_aspm.py             [gold] gold ASPM validator + offline firing analysis (Parser/kleene reused by the D9 scorer)
│   ├── validate_curated_rules.py    [gold] validator of policies/curated/
│   ├── extract_tau_tools.py         [code] τ-bench tool list → policies/tau_bench/*_tools.json
│   ├── freeze_pipeline_tag.sh       [code] creates tag auto-pipeline-v1 (stage 2b)
│   ├── freeze_repro_tag.sh          [code] creates tag repro-p1-v1 with a temporary index
│   └── reproduction/                [code] analysis and evaluation scripts
│       ├── label_write_actions.py          write-call safe/unsafe labels from expected actions → output/reproduction/labels/
│       ├── sample_unsafe.py                sample of unsafe labels for the manual noise check
│       ├── make_splits.py                  task-level train/val/test splits → splits.json
│       ├── p1_summary.py                   per-iteration table, repairs, circuits of a P1 run
│       ├── p1_circuits_premerge.py         circuit sizes before/after the co-occurrence merge
│       ├── p1_gold_diagnostic.py           [gold] E1 coverage vs gold clauses (diagnostic only)
│       ├── p1_rule_diagnostics.py          rule semantics diagnostics (complete-trace vs prefix)
│       ├── p1_precedence_check.py          IMPLIES-chaining / precedence check (P2-5)
│       ├── p1_runtime_semantics.py         never-block / can-block / every-step table (P2-2 + P2-4)
│       ├── p2_select_pilot.py              P2 pilot target selection (train split, seeded)
│       ├── p2_pilot.py                     P2 offline pilot runner (configs, Direct)
│       ├── p2_pilot_summary.py             P2 pilot summary tables
│       ├── p2_worked_example.py            P2 worked-example renderer
│       ├── p6_gold_score.py                [gold] D9 compliance scorer (scoring only); --gold v1 (default) | v2 → gold.jsonl | gold_v2.jsonl
│       ├── gold_compare.py                 [gold] v1 vs v2 scores of one run → gold_compare.json (missed violations, precision)
│       ├── p6_metrics.py                   P6 metrics (pass^k + bootstrap CIs, blocks, compliance, precision, cost); --gold v2
│       ├── p6_show_episode.py              renders one P6 conversation
│       ├── p6_audit_view.py                compact write-call view for the D9 manual audit
│       └── p6_user_sim_check.py            user-simulator "speaks like the agent" sample
│   └── tgr/                         [code] TGR-stage scripts
│       ├── metrics.py                      metrics for output/tgr/online/<tag>: P6 metrics (gold v1+v2), paired Δ, repeat-after-block,
│       │                                   violations attempted/blocked/executed, transfers → metrics.json, metrics_gold_v2.json, metrics_tgr.json
│       ├── dev_summary.py                  per-iteration development summary vs Phase 1 baselines (no LLM calls)
│       └── p0_smoke_models.py, p0_probe_extra.py, p0_replay_p1.py, p0_estimate.py   Phase 0 probes and cost estimate
│
├── aspm_repro/                      [out]  FINAL P1 ASPMs (708K)
│   ├── airline/{aspm.json, weights.json, manifest.json, rules.md}   airline v4 (58 rules)
│   └── retail/{aspm.json, weights.json, manifest.json, rules.md}    retail v1 (43 rules)
├── tgr_rules/                       [out]  published TGR rule sets (method output, NOT gold; README.md)
│   └── {airline,retail}/{full,nob,frozen}/{rule_set.json, rules.md, manifest.json, raw.json}
│                                           full = Phase 2 report version (it4), nob = −B ablation, frozen = tag tgr-frozen-v1 (it5)
├── aspm/                            [gold] gold ASPMs {airline,retail}_aspm.json (140K)
├── policies/                        [gold] (332K)
│   ├── curated/                            {domain}_clauses.json, {domain}_curated_rules.json, {domain}_config.json (Step 1)
│   ├── predicates/                         {domain}_predicates.json gold predicate registries (Step 2)
│   ├── tau_bench/                          {domain}_tools.json (tools + write flags), {domain}_data_notes.md
│   └── gold_v2/                            checks.py (confirmation + cancellation-eligibility dialogue predicates), README.md
├── agent/                           [up]   the authors' ShieldAgent code; never modified by the reproduction
│   ├── agent.py, prompt.py, run_inference.py, utils.py, debug_utils.py   authors' agent (planner prompt cited in p2_design)
│   ├── tools/                              authors' MCP tools; aspm_tool.load_aspm_json is used as a format check
│   │   └── __init__.py, aspm_tool.py, binary_query.py, certification.py, content_moderation.py,
│   │       context_search.py, memory_tool.py, policy_extraction.py, verification.py
│   ├── policy_construction/                authors' AutoPolicy extraction (policy_extractor_*.py, rule_extractor.py, utility.py)
│   ├── predicates/                  [gold] deterministic gold predicates: context.py (trajectory helpers), airline.py, retail.py
│   └── lib/                         [up]   vendored LADR/Prover9 sources (14M); mcp-logic, pyModelChecking, stormpy are empty
├── utility/                         [up]
│   ├── utils.py                            Azure OpenAI client (Managed Identity; endpoint + gpt-5-nano deployment)
│   └── policy_server.py                    authors' policy MCP server
├── policy_pipeline/                 [code] stage 2b automatic pipeline (tag auto-pipeline-v1); llm.py is the shared cached caller
│   ├── llm.py, common.py, embed.py, schemas.py, stages.py, run.py, __init__.py
│   ├── prompts/                            s0_tool_class … s8_enforce (.md), stage 2b prompts
│   └── inputs/                             addendum_interpretations.txt, airline_config.json, {airline,retail}_tools_raw.json,
│                                           extract_tau_tools_raw.py
├── aspm_auto/                       [out]  stage 2b published ASPMs: {airline,retail}/{aspm,manifest,predicates}.json (1.2M)
├── eval/                            [code] stage 2b evaluation (E1–E6) against gold
│   ├── common.py, collect.py, e1_clauses.py, e2_rules.py, e3_e6.py, e3_worksheet.py, runtime_load.py, __init__.py
│   ├── labels/                      [out]  manual labels and worksheets (JSON/MD/TXT, 476K)
│   └── results/                     [out]  evaluation results (JSON, 356K)
├── tests/                           [code] unit tests: python -m unittest discover -s tests -t .  (87 tests)
│   ├── policy_pipeline/test_pipeline.py    stage 2b tests (+ shared FORBIDDEN gold paths and DOMAIN_WORDS lists)
│   ├── predicates/                         gold predicate tests: test_airline.py, test_retail.py, test_context.py,
│   │                                       helpers.py, build_fixtures.py, fixtures/tau_records.json (164K)
│   └── repro/                              test_ltlf.py (vs flloat), test_infra.py, test_repro_pipeline.py (leakage, domain
│                                           words, prompts, fake-LLM end-to-end), test_mln_decomposition.py, test_runtime.py
│   ├── exp_core/                           test_models.py (profiles, routing, adapters), test_policy_filter.py
│   ├── method_tgr/                         test_tgr.py (sentences, validation, duplicates, runtime decision, feedback; fake LLM)
│   └── gold_v2/                     [gold] test_checks.py (hand-checked confirmation / eligibility cases)
│
├── docs/                            [rep]
│   ├── STRUCTURE.md                        this file
│   ├── RESULTS.md                          consolidated technical record of every experiment (tables with CIs, costs, links)
│   ├── SUMMARY_REPORT.md                   plain-language summary report for advisors
│   ├── paper/shieldagent.pdf        [in]   the paper (arXiv 2503.22738v2, 4.9M)
│   ├── orientation_summary.md              Stage 0 orientation of the authors' repo
│   ├── planning/                           Stage 0 plans: azure_openai_refactor_plan.md, project_cleanup_plan.md,
│   │                                       cleanup_run.log, new_tree.txt
│   ├── step1_rule_audit/                   {airline,retail}_coverage_report.md (gold clause audit)
│   ├── step2_aspm/                         design_notes.md, firing_analysis.md (gold ASPM)
│   ├── step2b_auto/                        report.md, summary_for_pi.md, iteration_log.md (stage 2b pipeline)
│   ├── reproduction/
│   │   ├── spec.md                         reproduction spec: components, deviations A1–A7, decisions D1–D13, P2-1…P2-6, ε sign
│   │   ├── gap_audit.md                    what the authors' code has / lacks
│   │   ├── data_feasibility.md             labels, label noise, splits
│   │   ├── plan.md                         phases P0–P6, Stage A/B, costs
│   │   ├── prompts_provenance.md           P1 prompt provenance and format adaptations
│   │   ├── venv_freeze.txt                 pinned packages of ~/venvs/tau-bench
│   │   ├── p1_log.md, p1_report.md         P0/P1 log (I1–I8, runs v1–v4, findings) and report
│   │   ├── airline_v4_rules.md, retail_v1_rules.md   final rule tables
│   │   ├── p2_design.md, p2_log.md         runtime design and implementation log (B1)
│   │   ├── p2_pilot_report.md              offline pilot (40 target steps)
│   │   ├── p6_log.md                       online evaluation log (O1–O7, P6-B1)
│   │   └── p6_report.md                    online evaluation report (source of truth for numbers)
│   ├── cleanup/                            cleanup_log.md, inventory.md, test_run.log (2026-10-17)
│   └── tgr/                                TGR stage
│       ├── plan.md                         phases 0–3, decisions, component B (revised), status
│       ├── p0_report.md                    Phase 0: models, smoke tests, prices, filter, cost estimate (M1–M6)
│       ├── known_limitations.md            L1 Domain Basic removal
│       ├── phase1_log.md, p1_report.md     Phase 1 (luna baselines, train)
│       ├── scorer_v2_report.md             gold v2 re-scoring of P6 and Phase 1
│       ├── phase2_design.md                TGR design, flags, decisions T1–T8, development protocol
│       ├── phase2_log.md                   iterations 1–5, final runs, freeze
│       ├── p2_report.md, p2_rules_appendix.md   Phase 2 report (iteration 4 + ablations); rules and dispositions
│       ├── val_report.md                   validation check (val split)
│       └── nano_agent_report.md            weak agent (gpt-5-nano) + strong guards (gpt-6-luna)
│
├── archive/                         [arch]
│   ├── authors_code/README_authors.md      the authors' original README
│   ├── early_setup/project_structure.md    Stage 0 structure doc
│   ├── autopolicy_early/visualization/     visualize_policy_graph.py, retail_policy_graph.html, lib/ (JS assets), 796K
│   ├── step1_gold_standard/data/output_curated/   first copy of the Step 1 curated files (SUPERSEDED.md inside), 168K
│   └── p1_superseded_runs/data/airline_v1, airline_v2, airline_v3   superseded P1 runs (I4 / fp32 / I7), 12.3M
│
└── output/                          [out]  git-ignored local results and caches (≈ 1.6G)
    ├── deep_policy/                        authors' AutoPolicy runs with gpt-5-nano (3 extraction_* folders; cited by gold JSON), 244K
    ├── step2_firing/                       gold firing analysis: {domain}_firing.json, firing_tables.md, 200K
    ├── auto_aspm/                          stage 2b runs ({airline,retail}/, *.log), 84M
    │   └── _cache/                  [cache] stage 2b LLM cache (JSON per call), 214M
    ├── reproduction/labels/         [in]   {domain}.jsonl write-call labels, {domain}_transfer.jsonl, counts.json,
    │                                       refusal_tasks.json, **splits.json** (task-level splits), 1.8M
    └── repro/
        ├── _llmcache/               [cache] P1/P2/P6 LLM cache (structured calls + tool_loop/ turns, JSON), 503M
        ├── _embcache/               [cache] embedding cache (embeddings.sqlite), 13M
        ├── _models/                 [cache] bf16 copy of BAAI/bge-large-en-v1.5 @ d4aa6901 (+ PROVENANCE.json), 641M
        ├── aspm_runs/airline/v4/, retail/v1/   P1 run dirs: e1_policies, e2_rules, alg2, e5_circuits, aspm, weights,
        │                                       manifest, log (.json), raw/ (per-call responses); 4.8M / 3.2M
        ├── p1_*.log                        P1 run logs (airline v1 attempt 1, v1–v4; retail v1)
        ├── smoke/                          P0 smoke runs airline_test_0.json, airline_test_0.openai254.json
        ├── p2_pilot/                       targets.json; {domain}/{A,A2,A2_rerun,B,direct,smoke}/{setup.json,steps.jsonl};
        │                                   {domain}/summary.{md,json}; run.log (9.7M)
        └── p6/
            ├── smoke/                      5 tasks × 1 trial × 3 guards per domain (episodes.jsonl, gold.jsonl), 4.9M
            └── full/                       594 conversations, 122M:
                ├── {airline,retail}/{none,direct,shield}/episodes.jsonl   one JSON line per conversation (attempts, guard
                │                                                         records, agent/executed messages, cost, latency)
                ├── {…}/gold.jsonl                                        D9 gold scores per conversation
                ├── retail/shield/episodes.before_resume.jsonl            state before the O7 single-conversation rerun
                ├── metrics.json, metrics.md                              P6 metrics (p6_metrics.py)
                └── logs/                                                 per-job run logs, driver.log
    └── tgr/                                TGR stage (≈ 1.1G)
        ├── _llmcache/               [cache] LLM cache of every profile (structured/ and tool_loop/), 839M
        ├── _embcache/               [cache] copy of the embedding cache used by the luna P1 rebuild, 22M
        ├── policy_input/            [in]   {domain}_wiki.rulebuild.txt (Domain Basic removed) + .filter.json (hashes, removed text)
        ├── p0/                             Phase 0 probes, smoke results, estimate.json, logs/
        ├── aspm_runs/luna-dev/{airline,retail}/v1/   ShieldAgent P1 rebuilt with gpt-6-luna (as output/repro/aspm_runs)
        ├── tgr_rules/luna-dev/{airline,retail}/{it1..it5,final_nob}/   every TGR rule build (rule_set, raw, rules.md, manifest)
        ├── online/                         episodes.jsonl (+ gold.jsonl, gold_v2.jsonl, metrics*.json, gold_compare.json) per tag:
        │   ├── p0_check/, p0_pilot_luna/, p0_pilot_grok/   Phase 0 smoke and cost pilots
        │   ├── luna_train/                 Phase 1 baselines + Phase 2 tgr / tgr_nob / tgr_noc (train, 3 trials)
        │   ├── tgr_dev_it1/ … tgr_dev_it4/ Phase 2 development runs (1 trial)
        │   ├── luna_train_v5/              frozen TGR (iteration 5), train, 3 trials (+ copies of the Phase 1 baseline episodes)
        │   ├── luna_val/                   validation check (val split)
        │   ├── nano_pilot/                 weak-agent cost pilot (16 conversations)
        │   └── nano_train/                 weak agent + strong guard (train, 3 trials)
        ├── phase1/, phase2/, phase_val/, phase_nano/   run scripts (*.sh) and logs/ of each phase
        └── (backups of output/: ~/backups/shieldagent_output_<date>.tar.gz + GitHub releases results-backup-<date>)
```
