# ShieldAgent POC Implementation

## Project Overview
This repository contains our effort to replicate the Action-based Safety Policy Model (ASPM) from the ShieldAgent paper. 

## What We Have Done So Far
- Extracted JSON schemas and LLM prompts directly from the ShieldAgent paper into `docs/file_formats/`.
- Cloned the target GitLab handbook repository to use as our real-world dataset.
- Successfully implemented the core extraction pipeline (`src/extractor.py`, `src/rule_extractor.py`).
- Extracted structured JSON policies and translated them to Linear Temporal Logic (LTL) using the Azure OpenAI API.
- Identified prompt weaknesses regarding "Atomicity" drift and missing Verifiability Refinement (VR) / Redundancy Pruning (RP) steps.
- Compiled our findings into a final report (`docs/reports/poc_report.md`) and updated our `knowledge_retention.md`.

## Experiment Plan Basics
Our POC focuses on extracting and verifying safety policies from three primary files in the GitLab handbook:
1. `record-retention-policy.md`
2. `acceptable-use-policy.md`
3. `change-management-policy.md`

For this initial Proof of Concept (POC), we have utilized the Azure OpenAI API to validate the core extraction logic.

## Resources & Architecture
- **Current POC Architecture**: We are using an **Azure OpenAI API** endpoint targeting a closed-source model (`gpt-5-nano`). This is securely accessed via Managed Identity, allowing us to rapidly test the Markdown -> Policy JSON -> LTL JSON pipeline.

**Research managers said:**
I’ve placed a sample file inside the machine that queries a GPT model. Use this file to understand how to query the model.
The file is located in a folder named: model_call_example
Please note that you can only query the model from within the virtual machine.
