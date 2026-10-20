# Published TGR rule sets (method output; NOT gold)

Made by `exp_core/tgr_build.py` (`method_tgr`) with gpt-6-luna from the Domain-Basic-filtered policy and the
environment's tool schemas. No rule was edited. Phase 2 (`docs/tgr/phase2_log.md`, `phase2_design.md`).

| folder | flags | source run | used by guard |
|---|---|---|---|
| `<domain>/full/` | A + B (restriction-only, dispositions); Phase 2 report version (iteration 4) | `output/tgr/tgr_rules/luna-dev/<domain>/it4/` (effort high) | `tgr`, `tgr_noc` |
| `<domain>/frozen/` | A + B, **frozen method** (tag `tgr-frozen-v1`; iteration 5) | `output/tgr/tgr_rules/luna-dev/<domain>/it5/` (effort high) | `tgr` in the validation check and later experiments (`--rules-dir tgr_rules/<domain>/frozen`) |
| `<domain>/nob/` | A, not B (general LTLf rules) | `output/tgr/tgr_rules/luna-dev/<domain>/final_nob/` (effort high) | `tgr_nob` |

Each folder contains `rule_set.json` (what the guard loads), `rules.md` (rules, predicates, background facts,
dispositions, validation), `manifest.json` (input hashes, model, prompt hashes, cost) and `raw.json` (the model's
output).
