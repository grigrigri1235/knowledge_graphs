# ShieldAgent POC Implementation

## Project Overview
This repository contains our effort to replicate the Action-based Safety Policy Model (ASPM) from the ShieldAgent paper.

## What We Have Done So Far
- Extracted JSON schemas and LLM prompts directly from the ShieldAgent paper into `docs/file_formats/`.
- Cloned the target GitLab handbook repository to use as our real-world dataset.
- Created an experimentation plan to secure GPU resources (`docs/planning/experimentation_plan.md`).

## Experiment Plan Basics
Our POC focuses on extracting and verifying safety policies from three primary files in the GitLab handbook:
1. `record-retention-policy.md`
2. `acceptable-use-policy.md`
3. `change-management-policy.md`

We will use open-source Large Language Models (LLMs) to perform policy extraction, verifiability refinement (VR), and redundancy pruning (RP). This avoids the privacy risks and high costs associated with using closed-source APIs for internal company data.

## Resources Needed
- **Hardware**: We require a compute node with at least **4x A100 (80GB)** or **8x A100 (40GB)** GPUs.
- **Justification**: This large compute capacity is necessary to load a 70B parameter open-source model locally (requiring ~140GB VRAM) for intensive logic reasoning. Additionally, GPUs are needed to fine-tune a small vision-language model (InternVL2-2B) required for evaluating agent trajectories visually, just as done in the paper.
