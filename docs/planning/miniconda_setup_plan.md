# Plan: Miniconda3 Installation & Environment Setup

## Goal
Install Miniconda3 in user space (`/home/azureuser/miniconda3`), initialize it, and create a dedicated conda environment for the project.

---

## Micro-Steps for Sequential Execution

1. **Part 1:** Download the latest Miniconda3 installer script for Linux x86_64 to `/home/azureuser/miniconda.sh`.
2. **Part 2:** Execute silent batch installation to `/home/azureuser/miniconda3` and remove the installer script.
3. **Part 3:** Run conda initialization for bash (`/home/azureuser/miniconda3/bin/conda init bash`).
4. **Part 4:** Create a dedicated conda environment named `graph_project_env` with Python 3.12, pymupdf4llm, torch.
5. **Part 5:** Verify environment creation and report completion with instructions for activation.
