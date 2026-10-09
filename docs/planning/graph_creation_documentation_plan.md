# Plan: Document Graph Creation Process & JSON Mapping in knowledge_retention.md

## Goal
Add a clear, simple section to `/home/azureuser/code_projects/knowledge_retention.md` detailing:
1. The step-by-step Graph Creation Process from the ShieldAgent paper (from raw text to optimized action circuits).
2. How all graph building blocks (vertices and edges) come to life directly through our pipeline's JSON files.

---

## Micro-Steps for Sequential Execution

1. **Part 1:** Draft the content in plain language:
   - The 4-step creation lifecycle from the paper (Extraction -> Bi-stage Optimization VR/RP -> Circuit Construction Algorithm 3 -> Weight Learning).
   - The exact JSON-to-Graph mapping: how `"predicates"` and `"logic"` in our JSON files become the vertices, factor edges, co-occurrence links, and action circuits.
2. **Part 2:** Edit `/home/azureuser/code_projects/knowledge_retention.md` to insert this new section.
3. **Part 3:** Verify the updated file to ensure simple language and complete alignment with the paper and schemas.
