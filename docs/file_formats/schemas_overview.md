# ShieldAgent JSON Schemas Overview

This document explains the JSON formats used in the ShieldAgent pipeline to turn policy documents into executable safety rules.

---

## 1. Policy Extraction Schema (`policy_extraction_format.json`)

**Role:**  
Takes raw text from a handbook or policy document and breaks it down into clear, structured pieces.

**Fields Explained in Simple Terms:**

- **`policy_description` (String) — *What is the actual rule?***
  - This is **literally copied from the document**. It details the restriction or guideline telling people or systems what they must or must not do.
  - *Example:* `"All records should be promptly destroyed pursuant to GitLab Records Retention Schedule."`

- **`definition` (Array of Strings) — *What do the terms mean?***
  - A mini-dictionary for words used in the rule. It defines terms so there is no ambiguity. It does not enforce actions by itself. If no terms are defined in the text, this is `None`.
  - *Example:* `["Record Owner: The individual or department that maintains the official version of a record."]`

- **`scope` (String) — *Where and when does the rule apply?***
  - Describes who the rule applies to, under what conditions, or in which systems. If it applies everywhere unconditionally, this can be `None` or broad.
  - *Example:* `"Records under the control of a specific department until transferred to an archive."`

- **`reference` (Array of Strings) — *Where did this text come from?***
  - The exact file path, URL, or section heading in the source document so anyone can verify the original context.
  - *Example:* `["/handbook/security/policies_and_standards/records-retention-deletion"]`

### Quick Field Summary
| Field | Plain English Meaning | Example |
| :--- | :--- | :--- |
| **`policy_description`** | The literal rule copied from text | *"Record Owner must delete records after 3 years."* |
| **`definition`** | Explains what words mean | *"Record Owner means the manager holding the file."* |
| **`scope`** | Conditions/groups it applies to | *"Applies only to financial records stored digitally."* |
| **`reference`** | Where the rule was found | *"/handbook/finance/records_policy.md"* |

---

## 2. Rule Extraction Schema (`rule_extraction_format.json`)

**Role:**  
Converts the extracted English policy rules into formal logic (Linear Temporal Logic, or LTL) so a computer agent can test and enforce them.

**Fields:**
- **`predicates` (Array of Arrays) — *The building blocks/states:***
  - Defines the conditions, states, or actions used in the rule logic. Each item has:
    - `predicate_name`: Short snake_case name (e.g., `retention_period_expired`).
    - `description`: Plain English explanation of what this condition represents.
    - `keywords`: Helpful search words for clustering related rules.
- **`logic` (String) — *The formal rule expression:***
  - The exact mathematical formula using LTL operators like `ALWAYS`, `AND`, `OR`, `NOT`, and `IMPLIES`.
  - *Example:* `ALWAYS ((retention_period_expired AND NOT litigation_hold_active) IMPLIES destroy_record)`

---

## 3. Rule Optimization Schema (`rule_optimization_format.json`)

**Role:**  
Cleans up the extracted logic rules. It removes duplicate rules (Redundancy Pruning) and makes sure all predicates can actually be checked by a software system (Verifiability Refinement).

**Fields:**
- **`rules` (Array of Objects):** The cleaned list of final rules.
  - Each rule has the refined `predicates` and the cleaned `logic` expression ensuring rules are concrete, testable, and not repetitive.
