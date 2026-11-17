# Cheaper, steadier predicate values for the TGR guard

An AI agent serves airline and retail customers on τ-bench. A guard checks each tool call before it runs. We start
from TGR, the partner's guard (`~/ShieldAgent`): 98 rules over 66 true/false facts, all set by one big LLM judge.

Our method, v4, keeps TGR's rules and facts and changes only how each fact gets its value:
- 40 facts are set by code (the call, the database replay, the tool log, message structure).
- 26 facts use code plus one tiny yes/no LLM question on one or two messages picked by code.

Result: the guard costs about 1/10 of TGR's, with at least the same task success, and no more harm got through.

## Where to start
- Final report: [docs/reports/tracker_v4_report.md](docs/reports/tracker_v4_report.md)
- Talk: [final_presentation.md](final_presentation.md)
- Map of the repo: [codebase_structure.md](codebase_structure.md)
- Handover and lessons: [knowledge_retention.md](knowledge_retention.md)
- Next step under study: a deterministic rule build, [docs/planning/rules_determinism/](docs/planning/rules_determinism/)

## History
1. ASPM reproduction of the ShieldAgent paper (removed in the 2026-11 cleanup; in git history).
2. State tracking experiment: code vs the judge on fact values (`docs/archive/`).
3. Tracker eval v2, then tracker v3: first build without the judge (`docs/archive/`).
4. Tracker v4: the current method (`docs/reports/tracker_v4_report.md`).
