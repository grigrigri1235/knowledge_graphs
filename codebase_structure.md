# Codebase Structure

Last updated: 2026-10-07

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
  - `docs/file_formats/`: Extracted JSON schemas and formats.
  - `docs/paper/`: Research papers and converted markdown digests.
  - `docs/planning/`: Execution plans and design documents.
  - `docs/reports/`: Experiment analysis and POC outcome reports.
- `files_given/`: Input data and target classification files from the managers.
- `handbook/`: Cloned GitLab handbook repository containing target policies.
- `output/`: Generated pipeline outputs (extracted policies, LTL rules, reviews).
- `src/`: Core extraction pipeline scripts (`extractor.py`, `rule_extractor.py`).
- `tests/`: Test suite and validation scripts.
- `README.md`: Project overview, setup instructions, and experiment summary.
- `knowledge_retention.md`: Technical handover, architectural decisions, and identified pipeline gaps.
- `handbook_files_to_focus.md`: Target list of files in the handbook to extract policies from.
