# Output Review: Baseline Action-Based Rule Circuits (`wiki.md`)

## 1. Graph Overview
- **Source Input:** `output/wiki_extracted_ltl_rules.json` (25 raw rules, 53 predicates).
- **Graph Type:** Baseline Action-Based Safety Policy Model (ASPM) Graph (built directly from raw rules without Verifiability Refinement or Redundancy Pruning).
- **Node Partitioning:**
  - **State Nodes ($P_s$):** 27 atomic environmental and contextual conditions.
  - **Action Nodes ($P_a$):** 26 operational and agent action predicates.
- **State Adjacency Matrix ($A$):** Shape $27 \times 27$ with 73 non-zero edges, capturing co-occurrences and semantic similarity ($\ge 0.50$).
- **Clustering:** Spectral clustering unified into 5 distinct state topic clusters under rule co-occurrence constraints.
- **Assembled Circuits:** 8 dedicated action circuits stored in `output/wiki_action_circuits.json`.

---

## 2. Action Circuit Verification Overhead Statistics

| Target Action ($p_a$) | Description | Circuit Rules ($|R_{p_a}|$) | Total Rules | Overhead Reduction (%) | Relevant States |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `cancel_order` | Cancel active or pending order | **7** | 25 | **72.0%** | 4 |
| `authenticate_user` | Locate user ID via email / name+zip | **15** | 25 | **40.0%** | 19 |
| `provide_information` | Disclose order, product, or profile info | **15** | 25 | **40.0%** | 19 |
| `send_response` | User response concurrency check | **15** | 25 | **40.0%** | 19 |
| `transfer_to_human` | Escalate unhandled requests | **15** | 25 | **40.0%** | 19 |
| `return_order` | Return delivered items & email slip | **22** | 25 | **12.0%** | 23 |
| `modify_order` | Modify order items, address, or payment | **23** | 25 | **8.0%** | 23 |
| `exchange_order` | Process item exchange & balance | **23** | 25 | **8.0%** | 25 |

---

## 3. Key Empirical Finding: The Need for VR & RP
By building this **baseline graph first**, we revealed a critical structural property:

1. **Clean Isolation for Independent Actions:**
   - Actions like `cancel_order` achieve immediate **72.0% overhead reduction**, isolating down to just 7 rules out of 25.
2. **Entangled Circuits from Compound Rules:**
   - In the raw rules, compound rules like Rule 5:
     `ALWAYS ((cancel_request OR modify_request OR return_request OR exchange_request) IMPLIES (action_details_listed AND user_confirmed_yes))`
     group four distinct actions into one single constraint.
   - Because all four actions share `action_details_listed` and `user_confirmed_yes`, their state clusters merge, entangling `modify_order`, `return_order`, and `exchange_order` into large 22–23 rule circuits (only 8–12% reduction).
3. **The Value of Verifiability Refinement (VR):**
   - In Part 7, VR decomposed Rule 5 into atomic rules for each action. When we construct the graph with VR later, each action will be completely disentangled, allowing `modify_order` and `exchange_order` to achieve the same high isolation rates (>70%) seen in `cancel_order`.
