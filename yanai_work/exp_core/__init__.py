"""Shared infrastructure for the post-reproduction experiments (Phase 0+ of the generic-improvements stage).

Kept apart from the frozen reproduction packages (repro_core/, repro_pipeline/ at tag repro-p1-v1): nothing here changes
their code or the gpt-5-nano results. Domain-agnostic; covered by tests/repro/test_repro_pipeline.py::NoGoldLeakage.
  - policy_filter: drop policy sections by heading (rule-building input only).
"""
