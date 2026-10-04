# Plan: GPU Availability Check

## Goal
Determine if an NVIDIA GPU is physically present and accessible to Python in this VM.

---

## Micro-Steps for Sequential Execution

1. **Part 1:** Run system check (`nvidia-smi` or `lspci`) to verify GPU hardware presence and driver status.
2. **Part 2:** Execute a quick Python check (`torch.cuda.is_available()` or checking `/dev/nvidia*`) to verify Python accessibility.
3. **Part 3:** Report GPU status, model, and memory back to user.
