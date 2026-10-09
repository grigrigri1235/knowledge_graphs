# Output Review: Retail Policy Extraction (`wiki.md`)

## 1. Schema Validation
- **Structure:** The output successfully parsed into a valid JSON array containing **32 policy objects**.
- **Keys:** Every object strictly contains all four required keys:
  - `definition`
  - `scope`
  - `policy_description`
  - `reference`
- **Field Types:**
  - `definition`: `null` across entries (conforming to the prompt instruction: *"If the Definition or Scope is unclear, leave the value as None"* since `wiki.md` specifies rules as direct operational constraints rather than explicit glossary definitions).
  - `scope`: `string` (when situational conditions exist, e.g., *"At the beginning of the conversation"*, *"Before taking consequential actions..."*) or `null` (for global constraints).
  - `policy_description`: `string` containing verbatim actionable policy statements.
  - `reference`: Array of strings, pointing to source sections (e.g., `["Retail agent policy"]`, `["Cancel pending order"]`, `["Modify pending order"]`).
- **Completeness:** No missing keys, no malformed syntax, and all required fields are present.

## 2. Content Quality & Granularity Comparison
- **High Granularity:** Unlike the earlier POC on `record-retention-policy.md` (which exhibited heavy grouping drift), the model here avoided grouping and broke individual bullet points into dedicated policy entries (32 total).
- **Behavioral Restrictions Captured:**
  1. Mandatory authentication before service lookup.
  2. Single user per conversation restriction.
  3. Strict requirement for listing action details and receiving explicit confirmation ("yes") prior to state-changing operations.
  4. Tool call vs. user response exclusivity (at most one tool call at a time; no simultaneous response + tool call).
  5. One-time tool execution limits for order modification and exchange.
  6. Precondition checks on order status (`pending` for cancel/modify, `delivered` for return/exchange).
  7. Payment refund and balance coverage rules (e.g. gift card vs. paypal/credit card timelines, gift card balance requirements for price difference).

## 3. Evaluation for Subsequent LTL Extraction
The extracted policies in `output/wiki_extracted_policies.json` are atomic, clear, and actionable. They serve as a clean, granular input for translation into Linear Temporal Logic (LTL) rules and predicates in Part 3.
