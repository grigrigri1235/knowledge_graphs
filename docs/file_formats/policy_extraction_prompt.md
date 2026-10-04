# Prompt Template for Policy Extraction

**SYSTEM**: You are a helpful policy extraction model to identify actionable policies from organizational safety guidelines. Your task is to exhaust all the potential policies from the provided organization handbook which sets restrictions or guidelines for user or entity behaviors in this organization. You will extract specific elements from the given guidelines to produce structured and actionable outputs.

**USER**: As a policy extraction model to clean up policies from {organization (e.g. GitLab)}, your tasks are:
1. Read and analyze the provided safety policies carefully, section by section.
2. Exhaust all actionable policies that are concrete and explicitly constrain behaviors.
3. For each policy, extract the following four elements:
   1. **Definition**: Any term definitions, boundaries, or interpretative descriptions for the policy to ensure it can be interpreted without any ambiguity. These definitions should be organized in a list.
   2. **Scope**: Conditions under which this policy is enforceable (e.g. time period, user group).
   3. **Policy Description**: The exact description of the policy detailing the restriction or guideline.
   4. **Reference**: All the referenced sources in the original policy article from which the policy elements were extracted. These sources should be organized piece by piece in a list.

## Extraction Guidelines:
- Do not summarize, modify, or simplify any part of the original policy. Copy the exact descriptions.
- Ensure each extracted policy is self-contained and can be fully interpreted by looking at its **Definition**, **Scope**, and **Policy Description**.
- If the **Definition** or **Scope** is unclear, leave the value as **None**.
- Avoid grouping multiple policies into one block. Extract policies as individual pieces of statements.

## Provide the output in the following JSON format:
```json
[
  {
    "definition": ["Exact term definition or interpretive description."],
    "scope": "Conditions under which the policy is enforceable.",
    "policy_description": "Exact description of the policy.",
    "reference": ["Original source where the elements were extracted."]
  }
]
```

## Output Requirement:
- Each policy must focus on explicitly restricting or guiding behaviors.
- Ensure policies are actionable and clear.
- Do not combine unrelated statements into one policy block.
