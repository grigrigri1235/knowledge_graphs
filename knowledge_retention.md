# Project Knowledge Retention

This file explains the project in plain and simple terms so anyone joining the team can quickly understand what was done, why, and what comes next.

---

## 1. Main Target Files
The research managers gave us a specific list of files to test:
- **Primary files to focus on:**
  - `record-retention-policy.md`
  - `acceptable-use-policy.md`
  - `change-management-policy.md`
- **Extra optional files:**
  - `gitleaks.md`
  - `data-classification-standard.md`
  - `password-standard.md`

All these files come from the GitLab handbook repository and live in the `handbook/` folder.

---

## 2. Target Answers (Ground Truth)
The file `files_given/legal_document_classifications.json` was provided directly by the research managers. It acts as our **answer key** to check whether our extracted rules are accurate.

---

## 3. How Prompts Map to JSON Formats
To build the safety model from the ShieldAgent paper, we use prompts and JSON templates in three steps:

1. **Policy Extraction:**
   - **Prompt:** `docs/file_formats/policy_extraction_prompt.md`
   - **JSON Format:** `docs/file_formats/policy_extraction_format.json`
   - **Job:** Reads handbook text and pulls out clean, structured policy statements.

2. **Rule Extraction (LTL):**
   - **Prompt:** `docs/file_formats/rule_extraction_prompt.md`
   - **JSON Format:** `docs/file_formats/rule_extraction_format.json`
   - **Job:** Turns each policy into formal logic rules (Linear Temporal Logic) and simple true/false checks (predicates).

3. **Rule Cleanup & Optimization:**
   - **Prompts:** `docs/file_formats/vr_prompt.md` (Verifiability Refinement) and `docs/file_formats/rp_prompt.md` (Redundancy Pruning)
   - **JSON Format:** `docs/file_formats/rule_optimization_format.json`
   - **Job:** Cleans up vague words, splits compound rules, and removes duplicates.

---

## 4. First Test Setup (POC)
The **Proof of Concept (POC)** was a small test of our extraction pipeline. Its goal was to make sure our code can take raw text, turn it into structured policy JSON, and then turn it into logic rules (LTL) using the Azure OpenAI model `gpt-5-nano`.

---

## 5. What We Learned from the First Test
- **Good news:** The model followed the JSON formats without errors.
- **Problem 1 (Grouping):** The model grouped multiple subsections into one big block instead of making separate rules.
- **Problem 2 (Human Actions vs. System Checks):** The model made rules about things humans do (like "read a guide" or "print a paper"). A software agent cannot easily check these. Rules must describe things software can verify directly (like database flags or API calls).
- **Next steps:** Add examples to the prompts to stop grouping, and build the cleanup steps (VR and RP).
- **Full Report:** `docs/reports/poc_report.md`

---

## 6. How the Safety Policy Graph is Built

The ShieldAgent paper represents safety rules as a knowledge graph ($G_{\text{ASPM}}$). In simple terms, this graph is a network of **nodes** (the basic facts and actions) connected by **edges** (the relationships and rules).

### Vertices (Nodes)
The nodes in the graph are **Predicates** (statements that can be True or False). They are split into two groups:

1. **Action Nodes ($P_a$):**
   - Things the agent tries to do (for example: `delete_data`, `cancel_order`, `send_to_user`).
   - Grouped into a simple 3-level tree:
     - **Level 1 (Broad Area):** High-level category (e.g., `Content Access`).
     - **Level 2 (Group):** Group of actions (e.g., `Publish Data`).
     - **Level 3 (Specific Action):** The exact action taken (e.g., `Update Bio`).

2. **State Nodes ($P_s$):**
   - Conditions or facts about the environment (for example: `user_is_authorized`, `data_is_private`, `order_status_pending`).

Connecting these nodes are two types of **Rules**:
- **Action Rules ($R_a$):** Rules that allow or block an action based on conditions (e.g., *"If user is NOT authorized, then DO NOT delete data"*).
- **Knowledge Rules ($R_p$):** Basic system facts connecting states (e.g., *"If data is private, then it is red data"*).

### Edges (Links between Nodes)
The graph connects nodes in four ways:

1. **Similarity Links:** Connect state nodes that appear in the same rule or mean similar things (used to group related checks together).
2. **Action-to-Rule Links:** Connect each action to the group of safety rules that protect it.
3. **Logic Circuit Links:** Inside each rule group, links show which conditions must be checked to decide if the action is safe.
4. **Action Tree Links:** Define hierarchical structures and execution order between nodes.


---

## 7. What We Learned from the Retail Policy (`wiki.md`)
- **Code worked smoothly:** The same scripts (`src/extractor.py` and `src/rule_extractor.py`) processed `files_given/wiki.md` without code crashes.
- **Surface granularity vs. True atomicity:** The model generated 32 items, which looked much better than the earlier handbook POC. However, deeper manual inspection revealed that individual bullet points still lumped multiple distinct rules together.
- **Easy for software to check:** The model extracted 25 logic rules and 53 predicates. Most predicates describe digital actions and states (like `user_confirmed_yes`, `order_status_pending`, `tool_call_active`), making them much easier to verify than human actions.
- **Full Report:** `docs/reports/wiki_processing_report.md`

---

## 8. The Full-Fledged Safety Policy Graph & Guardrail Engine

We built and verified the complete end-to-end safety guardrail system on the retail policy:

### 1. What Are Action Circuits? (`src/circuit_builder.py`)
Instead of making the guardrail check all 25 rules every single turn, we divide the rules into **8 small circuits** based on what action the agent wants to do.
- When an agent wants to `cancel_order`, it only checks **7 rules** (a **72% reduction** in work).
- When an agent wants to `authenticate_user`, it only checks **15 rules** (a **40% reduction**).

### 2. How the Guardrail Engine Protects Actions (`src/verifier.py`)
Before the agent is allowed to execute an action (like calling a database tool or answering a user):
1. **Extracts Action:** Identifies what the agent wants to do (e.g. `cancel_order`).
2. **Retrieves Circuit:** Pulls up only the safety rules protecting that action.
3. **Checks Facts:** Checks the environment (e.g. Is the order delivered? Did the customer say yes?).
4. **Calculates Safety Score ($\epsilon_s$):** Compares the safety probability of running the action versus doing nothing.
   - If $\epsilon_s \ge 0.0$, the action is **Certified Safe**.
   - If $\epsilon_s < 0.0$, the action is **Blocked** and the agent receives explanation feedback on what rule it broke.

### 3. Test Results (100% Accuracy)
We tested the guardrail on **12 realistic customer service scenarios** (`src/test_trajectories.py`):
- **All 6 safe customer requests** (e.g., normal cancellations on pending orders, address updates) were correctly approved (**0% false alarms**).
- **All 6 attack and violation scenarios** (e.g., trying to cancel a delivered order, leaking customer data without authentication, running actions without user confirmation) were immediately blocked (**0% breaches**).
- **Full Report & Verification Guide:** `docs/reports/wiki_full_fledged_aspm_report.md`

---

## 9. Critical Lessons from Manual Audits (Systematic Extractor Bugs)

A deep manual audit of the extraction JSON (`docs/reports/criticism.md`) exposed 4 major systematic bugs that automated schema checks completely missed:

### 1. The Scoping Systematic Bug (Detailed Breakdown)
The extractor handled the `scope` field very poorly in four distinct ways:
- **`null` vs. `always` collapse:** Global safety rules that must be obeyed at all times (e.g. *"Do not hallucinate / make up info"*, *"At most one tool call at a time"*) were given `scope: null` instead of `always` (or `all conversations`). The model failed to identify global invariants.
- **Ignoring In-Sentence Triggers:** When a sentence explicitly defined the trigger condition, the extractor still set `scope: null`. For example:
  - *"Transfer to human agent if and only if the request cannot be handled..."* $\rightarrow$ Model set `scope: null` despite the clear `if and only if` condition.
  - *"Be sure items are collected before making the tool call"* $\rightarrow$ Model set `scope: null` despite the clear `before making tool call` condition.
- **Lazy Header Copying:** When it did populate scope, it lazily copied the Markdown section heading (e.g., `"Modification of a pending order"` or `"Cancellation of a pending order"`) instead of the exact operational trigger (e.g., `"before modifying an order"` or `"after user confirmation of cancellation"`).
- **Trigger Smearing:** Because the trigger condition was missed or made vague in `scope`, the conditional phrase was left stuck inside `policy_description` (e.g., *"Before taking consequential actions... you have to list action details..."*), preventing clean separation between the rule's precondition and its action.

### 2. Inline Definition Blindness
- The model set `"definition": null` whenever definitions appeared inside normal sentences or parentheses:
  - Consequential actions were defined as `(cancel, modify, return, exchange)`.
  - Explicit user confirmation was defined as `(yes)`.
  - Cancellation reasons were defined as `('no longer needed' or 'ordered by mistake')`.
  - Profile fields and payment methods were explicitly enumerated.
- The extractor only recognized definitions if they were formatted like dictionary glossaries with colons (`Term: Definition`).

### 3. Confusing Static Data Models & Non-Policies for Rules
- The extractor treated passive database schemas and store catalogs as safety policies:
  - User profile attributes (email, default address, user ID).
  - Store inventory facts (50 types of products, color/size options) including illustrative examples (*"for example 't shirt'..."*).
  - Database timestamp conventions (24h EST).
- It also extracted vague non-rules that cannot be formally verified (*"Generally, you can only take action on pending or delivered orders"*). Policies cannot contain fuzzy words like "Generally".

### 4. Over-Grouping within Single Sentences
- The model packed multiple independent behavioral rules into single JSON objects:
  - Lumping database status update (`order status changed to 'cancelled'`) together with the financial refund process (`refunded via original payment method in 5 to 7 days`).
  - Lumping tool call limits (`at most one tool call at a time`) with messaging exclusivity (`do not respond to user when calling a tool`).
- Each of these has different triggers and enforces different actions; they must be separated into atomic policies.

---

### Key Takeaway for Future Pipelines
- **Syntactic validity $\ne$ semantic accuracy:** 0 schema errors does not mean the extraction is correct.
- **Prompts need targeted guidance:** Prompts must explicitly instruct models to identify inline definitions in parentheses, separate compound rules, distinguish `always` from `null`, and ignore non-behavioral data models.