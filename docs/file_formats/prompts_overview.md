# ShieldAgent Prompts Overview

This document explains the roles and variables of the four primary LLM prompts used in the ShieldAgent pipeline, extracted from the paper.

## 1. Policy Extraction Prompt (`policy_extraction_prompt.md`)
- **Role**: This prompt processes raw, natural language organizational safety guidelines (e.g., from a company handbook) and structures them into actionable policies. It is the first step in building the Action-based Safety Policy Model (ASPM).
- **Variables**: `{organization}` - The name of the organization whose policies are being processed (e.g., GitLab).
- **Output Schema**: Maps to `policy_extraction_format.json`.

## 2. Linear Temporal Rule Extraction Prompt (`rule_extraction_prompt.md`)
- **Role**: Takes the structured, natural language policies produced by the extraction prompt and converts them into rigorous Linear Temporal Logic (LTL) rules and verifiable atomic predicates.
- **Variables**: None explicitly in the prompt text, but it expects the structured policy output (Definition, Scope, Policy Description) from the previous step as context.
- **Output Schema**: Maps to `rule_extraction_format.json`.

## 3. Verifiability Refinement Prompt (`vr_prompt.md`)
- **Role**: Evaluates the atomic predicates derived from the rule extraction phase to ensure they are verifiable, concrete, accurate, and truly atomic. Refines or removes them if they are redundant or vague.
- **Variables**: Expects an extracted LTL rule and its associated predicates as context.
- **Output Schema**: Maps to `rule_optimization_format.json`.

## 4. Redundancy Pruning Prompt (`rp_prompt.md`)
- **Role**: The final phase of ASPM optimization. It analyzes a cluster of similar predicates across multiple rules to detect and merge redundancies. It simplifies the logical representation of rules globally.
- **Variables**: Expects a cluster of similar predicates and their associated rules as context.
- **Output Schema**: Maps to `rule_optimization_format.json`.
