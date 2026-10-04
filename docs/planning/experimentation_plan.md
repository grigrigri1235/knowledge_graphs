# Experimentation Plan

## Objective
Formulate a concrete experimentation plan to secure GPU resources by leveraging the JSON schemas in `schemas_overview.md` and the provided `files_given`. Replicate the ShieldAgent paper's methods as closely as possible for the initial Proof of Concept (POC) before adapting to our own needs.

## 1. Micro-Steps for Sequential Execution
5. **Part 5:** Present the concrete GPU Proof of Concept (POC) design below to secure computational resources.

---

## 2. GPU Proof of Concept (POC) Experimental Design

To faithfully replicate the Action-based Safety Policy Model (ASPM) from the ShieldAgent paper, we will build a POC targeting specific, high-density files from the GitLab handbook provided by the research managers.

**Primary Focus Files:**
1. `handbook/content/handbook/legal/record-retention-policy.md`
2. `handbook/content/handbook/people-group/acceptable-use-policy.md`
3. `handbook/content/handbook/security/security-and-technology-policies/change-management-policy.md`

*(Optional extensions: `gitleaks.md`, `data-classification-standard.md`, `password-standard.md`)*

### 2.1 The Need for Dedicated GPU Resources
While the paper utilizes closed LLMs (like GPT-4o) via API for policy extraction, relying exclusively on third-party APIs for real-time agent guardrailing and iterative optimization presents severe computational difficulties:

1. **Prohibitive Cost and Rate Limits**: Iterative processes like Redundancy Pruning (RP) and Verifiability Refinement (VR) evaluate hundreds of predicates per document. Sending complete trajectory histories and logic schemas back-and-forth to a closed API is too costly, slow, and rate-limited for a realistic, low-latency agentic shield.
2. **Data Privacy**: Sending internal corporate policies (like change management and record retention) to an external API compromises corporate data security.
3. **Local Guardrail Fine-Tuning**: Replicating the paper explicitly requires fine-tuning a small, fast vision-language guardrail model (e.g., InternVL2-2B) to perform rapid visual search and binary checks directly on agent trajectory screenshots. This cannot be done efficiently without dedicated GPUs.

### 2.2 Concrete Experiment Scale and Requirements
We propose migrating the heavy logic refinement (VR and RP) and inference tasks to open-source, large-parameter LLMs (e.g., Llama-3.1-70B-Instruct or Qwen-2.5-72B) deployed locally. 

- **Experiment Scale**: 
  - **Extraction Volume**: Extracting and refining 100+ LTL rules and predicates from the 3 primary handbook files.
  - **Inference Volume**: Thousands of rule verifications simulated over generated agent trajectories interacting with web environments.
- **Model Sizes & Hardware Needs**:
  - Running a 70B parameter model in FP16 requires ~140GB VRAM strictly for inference.
  - Fine-tuning the InternVL2-2B vision-language model requires high memory bandwidth.
- **Resource Request**: We request a compute node with at least **4x A100 (80GB)** or **8x A100 (40GB)** GPUs to facilitate fast, batched inference for the 70B model and concurrent fine-tuning of the 2B guardrail.

## 3. Pipeline Implementation (Part 5 execution)
1. **Extraction (CPU/API/GPU)**: Run the `policy_extraction_prompt.md` and `rule_extraction_prompt.md` over the 3 focus files.
2. **Refinement (GPU)**: Run the `vr_prompt.md` and `rp_prompt.md` using a locally hosted 70B open model to distill the rules.
3. **Verification**: Run simulated trajectories against the extracted rules using `files_given/legal_document_classifications.json` annotations to benchmark our open-source replica against the paper's reported SOTA metrics.
