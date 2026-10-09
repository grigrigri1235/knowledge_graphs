# Wiki.md Processing Experiment Plan - Overview

## Objective
Replicate the ShieldAgent extraction pipeline on `/home/azureuser/code_projects/files_given/wiki.md` (Retail agent policy) to extract structured JSON policies and Linear Temporal Logic (LTL) rules and predicates.

## Scope & Omission of Redundant Parts
Compared to `docs/planning/starting_exp/`, the following setup steps are **omitted as redundant**:
- **Environment Setup (`p1.md`):** The Conda environment with Python, `azure-identity`, and `openai` is already created and verified.
- **Pipeline Script Implementation (`p2.md`):** `src/extractor.py` and `src/rule_extractor.py` already exist, support CLI arguments, handle Managed Identity authentication, and include dry-run and formatting capabilities.

## Execution Sequence
- **Part 1 (`p1.md`):** Policy Extraction (`files_given/wiki.md`) [Done]
- **Part 2 (`p2.md`):** Policy Output Schema Validation [Done]
- **Part 3 (`p3.md`):** LTL Rule Extraction [Done]
- **Part 4 (`p4.md`):** LTL Output Schema Validation & Review [Done]
- **Part 5 (`p5.md`):** Quality Review & Retail Domain Analysis [Done]
- **Part 6 (`p6.md`):** Initial Extraction Experiment Reporting & Knowledge Retention [Done]
- **Part 7 (`p7.md`):** Verifiability Refinement (VR) Implementation & Execution [Completed]
- **Part 8 (`p8.md`):** Redundancy Pruning (RP) [Deferred for Comparative Ablation]
- **Part 9 (`p9.md`):** Action-Based Rule Circuit Construction (Baseline Graph from Raw Rules) [Done]
- **Part 10 (`p10_TESTING.md`):** Guardrail Verification & Action Certification Engine (Independent Agent Testing) [Done]
- **Part 11 (`p11.md`):** Full-Fledged Evaluation, Reporting & Knowledge Retention [Done]
