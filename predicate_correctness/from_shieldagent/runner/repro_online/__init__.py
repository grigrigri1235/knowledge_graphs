"""P6: online τ-bench evaluation with a guard in the agent loop (no shield / Direct / ShieldAgent).

The τ-bench ToolCallingAgent loop is re-implemented here with one hook: every agent turn is checked by the guard
before it reaches the environment. τ-bench code (pinned installed copy) supplies the environment, the tools, the
user simulator and the reward; its `litellm.completion` is replaced by the Azure shim of repro_core.taubench_run.
"""
