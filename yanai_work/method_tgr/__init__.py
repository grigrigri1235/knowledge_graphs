"""TGR: tool-grounded restriction rules for a policy guardrail (post-reproduction method, docs/tgr/plan.md).

Components, each behind a flag (docs/tgr/phase2_design.md):
  A  tool grounding: the actions of the rules are the agent's tools (+ respond); condition predicates name their
     evidence source; no LLM action mapping at runtime;
  B  restriction-only rule writing in one step ("<tool> IMPLIES <condition>", exceptions folded as OR, a disposition
     per policy sentence); no merging, exact duplicates removed, circuits = rules grouped by action;
  C  actionable feedback: names each unmet requirement, whether it is false or not established, and what to do.
The decision is Eq. 4-5 of ShieldAgent (repro_runtime.mln.decide) with uniform weights.
This package is domain-agnostic and never reads gold artefacts (tests/repro/test_repro_pipeline.py).
"""
