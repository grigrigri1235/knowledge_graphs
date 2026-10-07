# POC Experiment Report: Policy Extraction & LTL Translation

## Experiment Setup
- **Document Tested:** `handbook/content/handbook/legal/record-retention-policy.md`
- **Model Used:** Azure OpenAI `gpt-5-nano`
- **Code Files Executed:** `src/extractor.py` (Policy Extraction) and `src/rule_extractor.py` (LTL Rule Extraction).
- **Prompts Used:** `docs/file_formats/policy_extraction_prompt.md` and `docs/file_formats/rule_extraction_prompt.md`.
- **JSON Schemas:** `docs/file_formats/policy_extraction_format.json` and `docs/file_formats/rule_extraction_format.json`.
- **Results Locations:**
  - Policy JSON: `output/extracted_policies.json`
  - LTL Rules JSON: `output/extracted_ltl_rules.json`

## 1. Summary of Results
### Notable Successes
- **Perfect Schema Adherence:** The model output perfectly matched the highly structured nested JSON schemas without any missing keys, array format deviations, or type errors.
- **Logical Accuracy:** The LTL syntax generated was remarkably robust. The model successfully combined complex contextual conditions, such as: `ALWAYS (((is_original_record AND under_retention_schedule AND retention_period_expired) AND NOT litigation_hold_active) IMPLIES destroy_original_record)`. This shows the LLM easily understands the hierarchical priorities (e.g., a litigation hold overriding an expiration).
- **API Integration:** We successfully bypassed the local GPU constraint for the POC by leveraging an available Azure OpenAI endpoint.

### Flaws & Qualitative Analysis
- **Grouping Too Much Together:** The model often put unrelated rules into one big block instead of splitting them. For example, it combined "8.1 Mergers", "8.2 Consolidations", and "8.3 Team Member Moves" into a single policy block (Policy 9). It also grouped the entire "Personnel File Retention" section into one policy (Policy 10). *What it should have done: It should have created a separate JSON object for each of those sub-sections.*
- **Obvious or Useless Rules:** The model sometimes turned simple descriptions into rules. For example, it created `ALWAYS (team_member_consults_procedures IMPLIES retention_and_destruction_defined)`, which is just a fact, not a strict system rule to enforce. *What it should have done: It should have ignored this descriptive sentence entirely and only extracted rules that tell a system what it must or must not do.*
- **Human Actions instead of System Actions (Atomicity Drift):** We need rules a software agent can actually check. But the model used human actions for some rules, like "team member consults procedure" or "hard copy printed". A software agent cannot easily check if a human read a manual or printed a paper copy. *What it should have done: It should have mapped these concepts to system events (like checking if a digital "consultation_logged" flag exists or an "export_requested" API call happens), or skipped them if they cannot be verified digitally.* 

## 2. Prompt Adjustments Needed
- **Enforce Granularity:** Add a strict negative constraint to the Policy Extraction prompt forbidding the combination of independent list items or headers into single blocks. Add a few-shot example showing a bad grouping vs a good split.
- **Enforce ASPM Verifiability:** Modify the LTL Rule Extraction prompt to emphasize that predicates *must* describe discrete, API-verifiable system states (not manual human actions like printing).

## 3. Parsing Improvements
- Currently, our fallback parsing logic using string finding (`text.find("[")`) and regex works for well-behaved outputs. We should consider enforcing Structured Outputs (JSON mode) directly via the Azure OpenAI API parameters to eliminate regex fragility entirely.

## 4. General Notes & Conclusion
- **Lacking Feature:** We are completely missing the Verifiability Refinement (VR) and Redundancy Pruning (RP) steps. These steps from the paper are explicitly designed to fix the "Atomicity Drift" and redundancy we noticed in this manual review. 
- **Success Criteria:** Is the experiment a success? **Yes.** The core pipeline (Markdown -> Policy JSON -> LTL JSON) operates smoothly start-to-finish. The model proved highly capable of understanding and generating LTL logic. We have a strong baseline to scale from.
