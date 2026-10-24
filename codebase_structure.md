# Codebase Structure

Last updated: 2026-10-22

```text
/home/azureuser/code_projects/
├── docs/
│   ├── file_formats/
│   ├── paper/
│   ├── planning/
│   │   └── state_tracking_exp/
│   └── reports/
├── files_given/
├── handbook/
├── output/
├── predicate_correctness/
│   ├── from_shieldagent/
│   │   ├── code/
│   │   ├── tau_bench/
│   │   ├── rules/
│   │   ├── policies/
│   │   ├── runs/
│   │   ├── splits/
│   │   ├── runner/
│   │   └── gold/
│   ├── state_tracker/
│   ├── scoring/
│   ├── guard/
│   ├── tests/
│   └── output/
│       └── logs/
├── src/
└── tests/
```

### Directory Descriptions
- `docs/`: Project documentation, research papers, plans, and reports.
  - `docs/file_formats/`: JSON schemas (`policy_extraction_format.json`, `rule_extraction_format.json`, etc.) and prompt templates.
  - `docs/paper/`: Research papers and converted markdown digests.
  - `docs/planning/`: Execution plans and design documents.
    - `docs/planning/state_tracking_exp/`: plan of the state tracking experiment (`overview.md`, `p1.md` … `p10.md`).
    - `docs/planning/tracker_eval_v2/`: plan of tracker evaluation v2 (stopped on 2026-10-22; report in `docs/reports/tracker_eval_v2_report.md`).
    - `docs/planning/tracker_v3/`: plan of tracker v3 (no full LLM judge): `overview.md`, `p1.md` … `p14.md`, `brainstorm.md` (section 11 = the user's decisions), `next_agent_prompt.md` (the prompt to implement it). Live status: `predicate_correctness/output/eval_v3/progress.md`.
  - `docs/reports/`: POC evaluations, retail guardrail benchmark reports, and manual audit logs (`criticism.md`). `state_tracking_report.md` is the report of the state tracking experiment.
- `files_given/`: Input data, ground truth classifications, and retail benchmark files (`wiki.md`).
- `handbook/`: Cloned GitLab handbook repository containing target enterprise policies.
- `output/`: Generated pipeline outputs (policy JSONs, LTL rules, action circuits, verification logs, reviews).
- `predicate_correctness/`: Work on predicate values (brainstorm `initial_brainstorming.md`, and the state tracking experiment). Standard-library Python; run the tests here with `python3 -B -m unittest discover -s tests -t .`.
  - `from_shieldagent/`: Copies, never edited, with `PROVENANCE.md` (source, commit) and `SHA256SUMS`:
    - `code/`: ShieldAgent's LTL and decision code (`repro_core/`, `repro_runtime/`).
    - `tau_bench/`: τ-bench's data files, tool code and license (from `~/opt/tau-bench-59a200c`).
    - `rules/`: the frozen TGR rule sets (airline, retail).
    - `policies/`: the airline and retail policy texts.
    - `runs/`: saved TGR conversations on train tasks (`luna_train_v5`, `nano_train`).
    - `splits/`: `splits.json` (train, val, test tasks).
    - `runner/`: conversation runner and TGR code (Part 10; empty until then).
    - `gold/`: the partner's gold predicate code, used only by `scoring/`.
  - `state_tracker/`: our code: step loader, rolling state (database copy, shown set, event log), lookup format and lookups, replay, decisions again. `README.md` explains it.
  - `scoring/`: review scoring and the gold loader (Part 7). The tracker code never imports it.
  - `guard/`: our guard "TGR + tracker" (Part 10; empty until then).
  - `tests/`: unit tests and `check_copies.py`.
  - `output/`: results (`*.md` tables, `*.jsonl` data), `implementation_log.md`, and `logs/` with every command's output. `eval_v2/`: tracker evaluation v2 (frozen). `eval_v3/`: tracker v3 (from its part 1 on; `progress.md` is the live status).
- `src/`: End-to-end ASPM pipeline and guardrail implementation:
  - `extractor.py`: Extracts initial policies from text into structured JSON.
  - `rule_extractor.py`: Translates extracted policies into LTL formulas and predicates.
  - `refiner_vr.py`: Verifiability Refinement (VR) module for enforcing verifiable predicates.
  - `circuit_builder.py`: Builds action-specific rule circuits to reduce guardrail evaluation overhead.
  - `verifier.py`: Runtime safety guardrail engine that computes safety scores ($\epsilon_s$) and blocks unsafe actions.
  - `test_trajectories.py`: Test suite evaluating the guardrail across safe and adversarial customer scenarios.
- `tests/`: Automated test suite and validation scripts.
- `README.md`: Project overview, workflow setup, and usage instructions.
- `knowledge_retention.md`: Comprehensive technical handover, core architecture, and lessons learned.
- `handbook_files_to_focus.md`: Target list of GitLab handbook files for enterprise extraction.
