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

## 4. Why We Need GPUs (Experiment Justification)
The original paper relies on closed APIs (like GPT-4o). However, for our POC, we are pivoting to open-source Large Language Models (like Llama-3.1-70B or Qwen-2.5-72B) deployed locally because:
- **Cost & Limits:** Evaluating hundreds of rules iteratively via an API is prohibitively expensive and slow for real-time agent guardrailing.
- **Privacy:** Sending internal corporate policies to an external third-party API compromises data security.
- **Visual Guardrails:** We must fine-tune a small vision-language model (InternVL2-2B) locally to run rapid visual checks on agent actions.

**Hardware Request:** We need a compute node with at least **4x A100 (80GB)** or **8x A100 (40GB)** GPUs to load a 70B parameter model (~140GB VRAM) for offline extraction and to fine-tune the 2B guardrail.
