# Prompt provenance (paper App. H) and format-only adaptations

Source: ShieldAgent paper, arXiv 2503.22738v2, App. H (pages 29–32), transcribed from `docs/paper/shieldagent.pdf`. The instruction text is verbatim. Every difference is listed here and is format-only: it changes how input is supplied or output is serialised, never what is asked.

Common to all prompts:
- **F0. Restored underscores.** PDF text extraction turned `_` into spaces in identifiers (e.g. "store data" → `store_data`, "is data stored" → `is_data_stored`, "create project" / "click create project" → `create_project` / `click_create_project`, Eq. (8) `is_authorized ∧ has_legitimate_need ⇒ access_personal_data`). They are restored, since App. H requires snake_case names.
- **F1. Object-shaped JSON output.** Outputs are requested and enforced through Azure structured outputs (JSON schema, strict). The output-format blocks are therefore written as the object the schema enforces.
  - E1: `{"policies": [...]}` instead of a bare list.
  - E2: `{"rules": [...]}`, with each predicate as an object `{name, description, keywords, type}` instead of the list `[name, description, [keywords]]`.
  - VR/RP: `{"reasoning", "decision", "rules"}` instead of free text "Reasoning: … Decision: Yes/No … Output JSON: …". The paper's text format is kept above the JSON block, and one line states how the three parts are returned.
- **F2. Input slots.** The App. H templates do not show where the input goes. Each prompt appends one: the document section (E1), the policy block (E2), the rule plus its source policy (VR), the cluster plus its rules (RP).

Per prompt:

| File | App. H template | Adaptations |
|---|---|---|
| `e1_policy_extraction.md` | Prompt Template for Policy Extraction | F1, F2. `{organization (e.g. GitLab)}` → `{organization}`, filled with the document's own H1 title (input-derived, not hand-written). The section's heading path is given as `source`. |
| `e2_ltl_extraction.md` | Prompt Template for Linear Temporal Rule Extraction | F0, F1, F2. **Added fields** that §3.2.2 defines for a rule (r = [P_r, T_r, φ_r, t_r]) and Fig. 8–13 show for predicates, but the App. H output block omits: predicate `type` (action / condition), rule `description` (T_r) and `rule_type` (t_r, action / physical). One bullet ("Type: …") is added under "Predicate Formatting" to define the predicate type. |
| `e3_verifiability_refinement.md` | Prompt Template for Verifiability Refinement (VR) | F1, F2, and the same added fields as E2 in the output JSON. `{Few-shot Examples}` → `fewshot_vr.md` (below). |
| `e4_redundancy_pruning.md` | Prompt Template for Redundancy Pruning (RP) | F1, F2, and the same added fields. The returned rules replace the listed rules (the meaning of App. H's "Updated rules with the new merged predicates"; stated in one line). `Few-shot Examples` → `fewshot_rp.md`. |
| `fewshot_vr.md` | — (not printed in App. H) | The paper's own VR examples: **Fig. 11** (compound `process_content` → `publish_content` / `download_content` / `create_content`) and **Fig. 12** (`comply_with_laws` → GDPR-specific). Figure contents are used as given; keywords are empty (the figures show none); the short reasoning paraphrases the figure captions. Fig. 12's refined logic still says `comply_with_laws` (a typo in the figure) and is written with the refined name; `comply_with_GDPR_laws` is lower-cased to satisfy snake_case. |
| `fewshot_rp.md` | — (not printed in App. H) | The paper's own RP example, **Fig. 13** (`disclose_personal_data` merged into `publish_personal_data`). The original second rule's logic uses `publish_personal_data` although its predicate is `disclose_personal_data` (a typo in the figure); it is written with the declared predicate. |
| `format_repair.md` | — (not in the paper) | **Implementation aid, not a method component.** It is called at most once per rule whose `logic` fails the LTLf grammar. It returns only a rewritten `logic` with the same predicates and meaning (symbol → keyword, parentheses). The repair rate is reported in the manifest (`validation`) and `docs/reproduction/p1_log.md`. |

The few-shot examples come from GitLab/Reddit policies in the paper, so they contain no τ-bench content.

**F3 (added after airline v1, see `p1_log.md` I4). Few-shot delimiting.** The few-shot blocks are wrapped in `<<<BEGIN FEW-SHOT EXAMPLES … They are NOT part of your input. Never copy their predicates or rules into your output.>>>` … `<<<END FEW-SHOT EXAMPLES>>>`, and the input section of VR/RP starts with "YOUR INPUT (the only rule / cluster to process; base your output on it alone):". Without the delimiters, gpt-5-nano copied the example rules into most VR/RP outputs.
