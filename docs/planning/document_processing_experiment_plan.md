# Plan: Document Processing Experiment (Building Blocks)

## Objective
Take a target document from the GitLab handbook, process it using the LLM (Azure OpenAI) with our extraction prompts, and evaluate the output against the provided ground truth to create structured policy "building blocks".

## Phase 1: Preparation
- **Part 1:** Set up the environment using Conda. We will create an `environment.yml` file detailing the required dependencies (`openai`, `azure-identity`) to ensure it is easily transferable, and then create the conda environment from it.
- **Part 2:** Create the main Python pipeline script (e.g., `src/extractor.py`). This script will read a target markdown file, inject its content into the `docs/file_formats/policy_extraction_prompt.md` template, query the `gpt-5-nano` model, and parse the response.

## Phase 2: Single Document Extraction POC
- **Part 3:** Run the extraction script on the first focus file: `handbook/content/handbook/legal/record-retention-policy.md`.
- **Part 4:** Save the output and validate that it matches the schema defined in `docs/file_formats/policy_extraction_format.json`.
- **Part 5:** Feed the structured policy into the LTL rule extraction prompt (`rule_extraction_prompt.md`) to generate the final building block schema (`rule_extraction_format.json`).

## Phase 3: Evaluation & Validation
- **Part 6:** Manually review the extracted JSON outputs to ensure the policy definitions and LTL rules are logically sound, atomic, and adhere to the schemas.
- **Part 7:** Write a brief report analyzing the quality of the extraction and identifying any adjustments needed to our prompts or parsing logic. *(Note: The `files_given/` dataset will be used in future pipelines as a pre-filter to identify exactly which files across the entire repo contain actual rules and should be sent through this extraction pipeline).*
