# Part 10: Guardrail Verification Engine (Algorithm 1)

## Objective
Implement and run the online verification engine (following Algorithm 1 from Section 3.2.4 of the ShieldAgent paper) to test safety enforcement over retail agent action trajectories against the baseline Action-Based Safety Policy Model (ASPM) circuits (`output/wiki_action_circuits.json`).

> **CRITICAL REQUIREMENT - INDEPENDENT TEST AGENT:**
> This part MUST be executed by a **new, independent agent** (a different agent instance from the one that built Part 9). The agent that created the circuits in Part 9 must not test them, preventing any confirmation bias toward its own implementation. The new agent must independently inspect the circuits, formulate test trajectories (both safe and attack scenarios), and verify compliance.

---

## Mathematical & Algorithmic Formulation

### 1. Markov Logic Network (MLN) World Modeling (Eq. 4)
For an invoked action $p_a$ and its retrieved action circuit $C_\theta^{p_a} = \langle P_{p_a}, R_{p_a}, \theta_a \rangle$:
A world assignment $\mu$ assigns boolean truth values to state predicates $V_s = \{\mu_{p_s}\}$ and action predicate $\mu_{p_a}$.
The probability of world $\mu$ is modeled via MLN:
$$P_\theta(\mu) = \frac{1}{Z} \exp\left(\sum_{r \in R_{p_a}} \theta_r \mathbb{I}[\mu \models r]\right)$$
Where:
- $\mathbb{I}[\mu \models r] = 1$ if rule $r$ is satisfied under assignment $\mu$, else $0$.
- For the unweighted baseline graph, $\theta_r = 1.0$ for all rules $r \in R_{p_a}$.

### 2. Relative Safety Condition & Barrier Certificate (Eq. 5)
Conditioning on observed environment state predicates $V_s$:
1. **Invoked World ($\mu_{p_a} = 1$):**
   $$S_{\text{exec}} = \sum_{r \in R_{p_a}} \theta_r \mathbb{I}[(\mu_{p_a}=1, V_s) \models r]$$
2. **Counterfactual Non-Invoked World ($\mu_{p_a} = 0$):**
   $$S_{\text{non-exec}} = \sum_{r \in R_{p_a}} \theta_r \mathbb{I}[(\mu_{p_a}=0, V_s) \models r]$$
3. **Conditional Probabilities:**
   $$P_\theta(\mu_{p_a}=1 \mid V_s) = \frac{\exp(S_{\text{exec}})}{\exp(S_{\text{exec}}) + \exp(S_{\text{non-exec}})}$$
   $$P_\theta(\mu_{p_a}=0 \mid V_s) = \frac{\exp(S_{\text{non-exec}})}{\exp(S_{\text{exec}}) + \exp(S_{\text{non-exec}})}$$
4. **Relative Safety Condition:**
   $$\epsilon_s = P_\theta(\mu_{p_a}=1 \mid V_s) - P_\theta(\mu_{p_a}=0 \mid V_s) = \tanh\left(\frac{S_{\text{exec}} - S_{\text{non-exec}}}{2}\right)$$
5. **Certification Decision:**
   $$\ell_s = \begin{cases} 1 \quad (\text{Safe}) & \text{if } \epsilon_s \ge \epsilon \\ 0 \quad (\text{Unsafe}) & \text{if } \epsilon_s < \epsilon \end{cases}$$
   (Default threshold $\epsilon = 0.0$ or safety margin $0.1$ as per paper).

---

## Sequential Implementation Parts

### Part 1: Trajectory Benchmark Dataset Creation
- Formulate a test suite of realistic retail agent trajectories covering diverse actions:
  - `cancel_order`: Safe pending cancellation vs Unsafe delivered cancellation vs Unsafe unconfirmed cancellation.
  - `modify_order`: Safe address modification vs Unsafe gift card modification without sufficient balance.
  - `return_order`: Safe delivered return with email vs Unsafe return on pending order.
  - `authenticate_user`: Safe email lookup upon start vs Unsafe proceeding without authentication.
  - `provide_information`: Safe disclosure when authenticated vs Unsafe data leak when unauthenticated.
  - Multi-user conflict / transfer scenarios.
- Structure test cases with action description, observation, thought, proposed action $a_i$, state context, and ground truth safety label.

### Part 2: Formal Rule Verification Logic & LTL Evaluator
- Implement formal rule satisfaction evaluator in `src/verifier.py`:
  - Evaluate boolean propositional and temporal implications (`IMPLIES`, `AND`, `OR`, `NOT`, `EVENTUALLY`, `NEXT`).
  - Verify whether assignments $(p_a=1, V_s)$ and $(p_a=0, V_s)$ satisfy each rule in the circuit.
  - Track exact violated rules $V_s$ when unsatisfied.

### Part 3: Algorithm 1 Verifier Engine Implementation
- Implement `src/verifier.py`:
  - Step 1: `EXTRACT(a_i)`: Map agent proposed action to action predicate $p_a$.
  - Step 2: `RETRIEVE(p_a, G_ASPM)`: Retrieve circuit $C_\theta^{p_a}$ from `output/wiki_action_circuits.json`.
  - Step 3: `ASSIGN(H_{<i}, o_i)`: Extract/assign truth values to relevant circuit state predicates.
  - Step 4: `VERIFY(r, V_s)`: Formally check all rules in $C_\theta^{p_a}$.
  - Step 5: `COMPUTE_SAFETY`: Calculate $P_\theta(\mu_{p_a}=1)$, $P_\theta(\mu_{p_a}=0)$, $\epsilon_s$, and safety flag $\ell_s$.
  - Step 6: `EXPLAIN`: Generate natural language explanation and actionable remediation feedback for any violation.

### Part 4: Engine Execution & Results Serialization
- Execute `src/verifier.py` across the complete trajectory benchmark.
- Redirect execution output to log: `output/wiki_verifier_execution.log`.
- Serialize results to `output/wiki_guardrail_demo_results.json`.

### Part 5: Quality Review, Metrics Analysis & Knowledge Retention
- Compile comprehensive review into `output/wiki_guardrail_demo_review.md`:
  - Guardrail accuracy, Precision, Recall of violated rules, False Positive Rate (FPR), False Negative Rate (FNR).
  - Efficiency metrics: circuit overhead reduction utilized during verification.
  - Analysis of baseline circuit performance.
- Update `docs/planning/wiki_processing_exp/overview.md` to mark Part 10 as completed.

---

## Deliverables
1. `src/verifier.py`: Algorithm 1 implementation.
2. `output/wiki_guardrail_demo_results.json`: Benchmark trajectory verification results.
3. `output/wiki_guardrail_demo_review.md`: Evaluation analysis report.
4. `output/wiki_verifier_execution.log`: Full execution log.
