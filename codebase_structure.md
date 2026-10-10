# Codebase Structure

Last updated: 2026-10-10

```text
/home/azureuser/code_projects/
├── docs/
│   ├── file_formats/
│   ├── paper/
│   ├── planning/
│   └── reports/
├── files_given/
├── handbook/
├── output/
├── src/
└── tests/
```

### Directory Descriptions
- `docs/`: Project documentation, research papers, plans, and reports.
  - `docs/file_formats/`: JSON schemas (`policy_extraction_format.json`, `rule_extraction_format.json`, etc.) and prompt templates.
  - `docs/paper/`: Research papers and converted markdown digests.
  - `docs/planning/`: Execution plans and design documents.
  - `docs/reports/`: POC evaluations, retail guardrail benchmark reports, and manual audit logs (`criticism.md`).
- `files_given/`: Input data, ground truth classifications, and retail benchmark files (`wiki.md`).
- `handbook/`: Cloned GitLab handbook repository containing target enterprise policies.
- `output/`: Generated pipeline outputs (policy JSONs, LTL rules, action circuits, verification logs, reviews).
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
