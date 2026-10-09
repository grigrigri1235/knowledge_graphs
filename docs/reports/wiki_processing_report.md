# Experiment Report: Retail Policy Extraction & LTL Translation (`wiki.md`)

## 1. Experiment Overview
- **Document Tested:** `files_given/wiki.md` (Retail Agent Policy)
- **Model Used:** Azure OpenAI `gpt-5-nano` (accessed via Managed Identity)
- **Pipeline Scripts Executed:**
  - `src/extractor.py`: Extracted 32 structured policies
  - `src/rule_extractor.py`: Translated policies into 25 LTL rules and 53 unique predicates
- **Prompts Applied:**
  - `docs/file_formats/policy_extraction_prompt.md`
  - `docs/file_formats/rule_extraction_prompt.md`
- **Schemas Enforced:**
  - `docs/file_formats/policy_extraction_format.json`
  - `docs/file_formats/rule_extraction_format.json`
- **Generated Outputs:**
  - Policy Output: `output/wiki_extracted_policies.json`
  - Policy Review: `output/wiki_policy_review.md`
  - LTL Rules Output: `output/wiki_extracted_ltl_rules.json`
  - LTL Review: `output/wiki_ltl_review.md`
  - Domain & Quality Review: `output/wiki_quality_and_domain_review.md`

---

## 2. Quantitative Results
| Stage | Input Items | Output Items | Schema Pass Rate | Unique Predicates |
| :--- | :--- | :--- | :--- | :--- |
| **Policy Extraction** | 82 Markdown lines | 32 Policy objects | 100% | N/A |
| **LTL Translation** | 32 Policy objects | 25 LTL rules | 100% | 53 predicates |

---

## 3. Qualitative Analysis & Notable Successes
1. **Granularity & Lack of Grouping Drift:**
   Unlike the initial POC on `record-retention-policy.md` (which grouped multiple sub-sections into massive blocks), extraction on `wiki.md` achieved fine granularity. Individual bullet points were isolated into 32 distinct, actionable policy specifications.
2. **High API Verifiability (Minimal Atomicity Drift):**
   The retail policy predicates map directly onto agent API parameters, observable states, and database fields:
   - Status verifications: `order_status_pending`, `order_status_delivered`, `order_status_cancelled`
   - Explicit confirmation check: `user_confirmed_yes`, `action_details_listed`
   - Agent concurrency constraints: `tool_call_active`, `user_response_sent`
   This is a marked improvement over corporate handbook policies where human manual activities (e.g., reading or printing documents) leaked into predicates.
3. **Complex Temporal Reasoning:**
   The model effectively synthesized temporal dependencies using `ALWAYS`, `EVENTUALLY`, and `NEXT`:
   - Concurrency barrier: `ALWAYS (tool_call_active IMPLIES NEXT NOT tool_call_active) AND ALWAYS (tool_call_active IMPLIES NOT user_response_sent) AND ALWAYS (user_response_sent IMPLIES NOT tool_call_active)`
   - Sequential confirmation gating: `ALWAYS ((action_details_listed AND user_confirmed_yes) IMPLIES NEXT db_action_executed)`

---

## 4. Observed Flaws & Edge Cases
1. **Operator Notation Drift:**
   Rules 00–11 utilized `IMPLIES`, while Rules 12–24 switched to arrow notation `->`. While logically equivalent, strict syntactic uniformity requires standardizing on textual operators.
2. **Extraction of Domain Invariants as Action Rules:**
   Rule 07 generated `ALWAYS time_in_est`. This describes a database configuration fact rather than an actionable constraint governing agent execution.
3. **Disjunction Splitting in Authentication:**
   The policy permits authentication via email OR name + zip code. The model extracted two separate rules (`locate_user_id_email` and `locate_user_id_name_zip`) instead of combining them into a single disjunctive requirement `(locate_user_id_email OR locate_user_id_name_zip)`.

---

## 5. ASPM Graph Integration
The extracted 53 predicates and 25 rules directly populate the ShieldAgent knowledge graph $G_{\text{ASPM}} = \langle P_a \cup P_s, R_a \cup R_p, \pi_\theta \rangle$:
- **Action Predicates ($P_a$):** Tool calls and database mutations (`locate_user_id_email`, `modify_shipping_address`, `transfer_to_human`, etc.).
- **State Predicates ($P_s$):** Dialogue flags and order statuses (`user_confirmed_yes`, `order_status_pending`, `gift_card_balance_sufficient`, etc.).
- **Action Rules ($R_a$):** Operational guards conditioning actions on states.
- **Physical Rules ($R_p$):** System integrity constraints across status values.

---

## 6. Conclusion
The experiment is a **complete success**. The end-to-end pipeline (`wiki.md` $\rightarrow$ Policies JSON $\rightarrow$ LTL JSON) executed with 100% schema compliance and demonstrated the pipeline's capability on interactive dialogue-based agent policies.
