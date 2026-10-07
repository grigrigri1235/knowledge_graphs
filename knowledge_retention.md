# Project Knowledge Retention

This document serves as a handover for future agents or team members to understand the context, decisions, and unspoken knowledge of this project.

## 1. The Origin and Role of Target Files
The research managers have specifically assigned a targeted list of files to focus on for the initial Proof of Concept (POC). 
- **Primary Focus:**
  - `record-retention-policy.md`
  - `acceptable-use-policy.md`
  - `change-management-policy.md`
- **Optional Extras:**
  - `gitleaks.md`
  - `data-classification-standard.md`
  - `password-standard.md`

These target files are located in the cloned GitLab handbook repository (under the `handbook/` directory).

## 2. Manager-Provided Ground Truth
The `files_given/legal_document_classifications.json` file is a crucial piece of the experiment. It was provided directly by the research managers and serves as the **ground truth** (target classifications) for testing and verifying our extracted policies.

## 3. Mapping Prompts to Schemas
To replicate the ShieldAgent paper's Action-based Safety Policy Model (ASPM), we extracted the LLM prompts and expected JSON schemas. Here is how they must map together during the experiment:

- **Policy Extraction**
  - **Prompt:** `docs/file_formats/policy_extraction_prompt.md`
  - **Schema:** `docs/file_formats/policy_extraction_format.json`
  - **Role:** Converts raw handbook text into structured actionable policies.

- **Linear Temporal Rule Extraction**
  - **Prompt:** `docs/file_formats/rule_extraction_prompt.md`
  - **Schema:** `docs/file_formats/rule_extraction_format.json`
  - **Role:** Translates structured policies into rigorous Linear Temporal Logic (LTL) rules and predicates.

- **Verifiability Refinement (VR) & Redundancy Pruning (RP)**
  - **Prompts:** `docs/file_formats/vr_prompt.md` and `docs/file_formats/rp_prompt.md`
  - **Schema:** Both output to `docs/file_formats/rule_optimization_format.json`
  - **Role:** Optimizes and merges predicates to ensure they are atomic, unambiguous, and non-redundant.

## 4. Model Architecture & Experiment Setup (POC)
The **Proof of Concept (POC)** is a small-scale, end-to-end test of the ShieldAgent extraction pipeline. It aims to verify that we can programmatically convert raw Markdown handbook text into structured JSON policies, and then into Linear Temporal Logic (LTL) rules, exactly as described in the original paper. 

## 5. POC Learnings & Next Steps
- **Model Usage:** During the initial POC, we successfully used the Azure OpenAI `gpt-5-nano` model (via Managed Identity). The model proved highly capable of adhering to complex nested JSON schemas.
- **Prompt Adjustments:** The zero-shot extraction prompts need few-shot examples to enforce "Atomicity". Currently, the model extracts procedural facts (e.g., human reading a document) rather than discrete, agent-verifiable states. It also tends to group multiple subsections into single policy blocks.
- **Missing Pipeline Components:** The POC proved the Markdown -> Policy JSON -> LTL JSON pipeline works. The immediate next step is to implement the Verifiability Refinement (VR) and Redundancy Pruning (RP) phases which are critical to fix the atomicity drift observed in the raw LTL output.
**FULL REPORT:** docs/reports/poc_report.md