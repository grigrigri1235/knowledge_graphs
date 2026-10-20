# Phase 2 design: TGR (tool-grounded restriction rules)

Date 2026-10-20. Approved scope: `plan.md` (Phase 2, component B as revised). Code: `method_tgr/` (method, domain-agnostic,
no gold access; enforced by `tests/repro/test_repro_pipeline.py`), `exp_core/tgr_build.py` (rule-build CLI),
`repro_online/guards.py::TGRGuard` (online guard). Tests: `tests/method_tgr/`. Iterations: `phase2_log.md`.

## Pipeline

**Rule building (offline, once per domain).**
- Input: the Domain-Basic-filtered policy (`output/tgr/policy_input/<d>_wiki.rulebuild.txt`, as in Phase 1) and the
  environment's tool schemas (the agent's own tool interface). No gold file is read.
- `method_tgr.policy_text` numbers every policy sentence (`[S<n>]`). Headings are context; bullets are kept.
- **One rule-writing call** (`method_tgr/prompts/rules_*.md`, effort `medium`, output budget 32k tokens) returns
  three things:
  - the condition predicates (name, description, evidence source);
  - the rules;
  - a disposition for every sentence.
- **Validation** (code): every rule parses as LTLf. Its action is a tool (or `respond`). Its condition is purely
  boolean and contains no actions. All predicates are declared, and every sentence has exactly one disposition.
  - If anything fails: at most 2 repair calls, each given the validator's error list and told to change only what
    the errors require. Rules still invalid after that are dropped and reported. No rule is edited by hand or by code.
- **Exact duplicates** (same canonical logic) are removed. No other merging.
- **Circuits** = the rules grouped by action.
- Output: `output/tgr/tgr_rules/<profile>/<d>/<run>/{rule_set.json, raw.json, rules.md, manifest.json}`. Final
  rule sets are published to `tgr_rules/<d>/{full,nob}/`.

**Runtime (one agent step, `method_tgr/runtime.py`).**
1. Action = the tool name, or `respond` (A). If the action has no rules, the step is allowed **without any LLM call**.
2. Predicate values: **one judge call** (effort `medium`, `prompts/judge.md`) over the executed conversation (P2-6,
   tail-truncated at 24,000 characters) and the pending action. It returns true / false / unknown with evidence.
   "Something happened earlier" predicates are false if it did not happen. Unknown is reserved for information that
   is missing from the conversation.
3. Decision: **Eq. 4–5 unchanged** (`repro_runtime.mln.decide`), θ = 1 for every rule, allowed iff
   P(µ=1) − P(µ=0) ≥ −ε with ε = 0.1. The per-conversation trace store follows ShieldAgent's rules: blocked steps are
   not recorded, and the cap override commits the step.
4. Feedback: C on → `method_tgr/feedback.py`; C off → ShieldAgent's explanation call (`repro_runtime` `explain`
   prompt and `render_feedback`).

## Components and flags

| component | on | off (ablation) |
|---|---|---|
| **A** tool grounding (build flag `--no-a`; guard `tgr_noa`) | actions = the env's tools + `respond`; every predicate declares its evidence source (call arguments, tool outputs, user messages, agent messages); no runtime mapping | free action predicates named by the model, mapped at runtime by ShieldAgent's vocabulary table + EXTRACT (`repro_runtime.vocab` / `extract`); predicates without source |
| **B** restriction-only rule writing (build flag `--no-b`; guard `tgr_nob`) | `<action> IMPLIES (<condition>)` only; prohibitions as `NOT`; action-tied obligations become preconditions; permissions and exceptions folded in as OR; facts give no rule; a disposition per sentence (rule / exception / fact / not_enforceable + reason) saved as the coverage check | general LTLf rules (any operator; obligations, prohibitions and permissions as separate rules); no dispositions; same validation, duplicate removal and grouping by every action the rule mentions |
| **C** actionable feedback (guard `tgr_noc`) | deterministic text: for each violated rule, every condition predicate with its value (true / false / not established) and the judge's evidence; then what to do: for each missing value, how to establish it (ask the user / look it up / tell the user / change the arguments); for a rule violated as things stand, "do not repeat the same call", proceed only once the requirement holds, otherwise tell the user which requirement prevents it | ShieldAgent's explanation call: "BLOCKED by policy guardrail. Violated rules: … Explanation: … Feedback: …" |

Ablations run on train with gpt-6-luna (plan change 2026-10-19): `tgr` (A+B+C), `tgr_nob` (A+C, rules built with
`--no-b`), `tgr_noc` (A+B, the `tgr` rule set).

## Decisions (TGR-specific)

| id | decision | why |
|---|---|---|
| T1 | Restriction rules are evaluated at the current step only (no temporal operators). History-dependent requirements are predicates such as "the user confirmed X earlier" | B: obligations tied to an action become preconditions; the judge reads the history |
| T2 | One judge call per checked step, replacing ShieldAgent's relevance filter, planner loop and EXTRACT | circuits keyed by tool are small and all relevant to the invoked tool; P6 showed the planner almost never used Search / Binary-Check |
| T3 | Under A, steps whose tool has no rules cost nothing and are always allowed | the P1-luna blocks came mostly from non-tool rules applied to reads and replies |
| T4 | V_s (rules named in the feedback) = rules violated in the most probable world ∪ rules violated with probability > 0. ShieldAgent uses the first non-empty one of these sets (B1) | the feedback must name every requirement to establish, or the agent fixes one and is blocked again by the next |
| T5 | An unknown precondition blocks (Eq. 5 with θ = 1: margin = (e+1−2e)/(3e+1) ≈ −0.19 < −0.1). This is kept; C turns it into "establish it first" | it is a structural property of Eq. 4–5, which the plan fixes; it is not tuned away |
| T6 | `respond` is an action like any tool. The model decides, under B's "checkable at action time" constraint, whether any rule restricts messages | generic; the development loop shows its effect |
| T7 | Rule ids are renumbered 1..n after validation; the model's id is kept as `model_id` | the runtime orders rule ids numerically |
| T8 | Rule writing uses one call over the whole policy, not one call per section | exceptions can sit in another section from their restriction; the policy is small (4.7–5.4 kB) |

## Development protocol (fixed before the first run)
- Train split only, gpt-6-luna for every role, no grok-4.7 call.
- **Iteration k:**
  1. rebuild rules (`build.sh it<k>`);
  2. run `tgr` with 1 trial on all train tasks, both domains (66 conversations, tag `tgr_dev_it<k>`);
  3. compare with the Phase 1 baselines on the same tasks: blocks, transfers, block precision (gold v2), pass^1 as a
     rough signal;
  4. read blocked steps and the rules behind them;
  5. change only generic prompts or code (no domain words, no rule edits), and log the change in `phase2_log.md`.
- At most about 5 iterations. Then the final runs: `tgr`, `tgr_nob` and `tgr_noc` with 3 trials on train (tag
  `luna_train`, next to the Phase 1 baselines), and the report.
- **Caveat:** development and final measurement use the same train tasks, so the train numbers are optimistic for
  TGR. The unbiased comparison is Phase 3b (grok-4.7, test split, once).
