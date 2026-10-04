# ShieldAgent JSON Schemas Overview

This document explains the roles and fields of the JSON schemas used in the ShieldAgent pipeline for safety policy extraction and rule reasoning.

## 1. Policy Extraction Schema (`policy_extraction_format.json`)

**Role:** 
This schema is used in the first stage of the Action-based Safety Policy Model (ASPM) pipeline. It formats raw natural language policies (e.g., from government regulations or corporate handbooks) into structured independent components.

**Fields:**
- `definition` (Array of Strings): Contains the exact term definition or interpretive description of the policy constraints.
- `scope` (String): Describes the specific conditions or environments under which the policy is enforceable.
- `policy_description` (String): Provides the exact, unabridged description of the policy directly from the source.
- `reference` (Array of Strings): Cites the original source (document, section, or page) where the elements were extracted from to allow backtracking and verification.

## 2. Rule Extraction Schema (`rule_extraction_format.json`)

**Role:** 
This schema is used to translate the formatted natural language policies into manageable linear temporal logic (LTL) rules. These structured logical rules make formal verification possible.

**Fields:**
- `predicates` (Array of Arrays): Defines the variables or states used in the logic expression. Each inner array defines a single predicate and contains:
  - `predicate_name` (String): The unique identifier for the predicate (e.g., `create_project`).
  - `description` (String): A natural language description of what the predicate represents.
  - `keywords` (Array of Strings): A list of keywords related to the predicate used for semantic matching and clustering.
- `logic` (String): The formal representation of the rule using Linear Temporal Logic (LTL) that involves the defined predicate names.

## 3. Rule Optimization Schema (`rule_optimization_format.json`)

**Role:** 
This schema is used during the iterative ASPM Structure Optimization phase, which consists of Verifiability Refinement (VR) and Redundancy Pruning (RP). It represents the refined, atomic, and concrete versions of rules, or the result of merging redundant rules together.

**Fields:**
- `rules` (Array of Objects): A list of optimized or merged rules. Each object contains:
  - `predicates` (Array of Arrays): Contains the updated or refined predicates, utilizing the same structure as the rule extraction schema (name, description, keywords).
  - `logic` (String): The refined LTL logic expression that uses the optimized predicates, ensuring the rule is accurate, atomic, and verifiable without ambiguity.
