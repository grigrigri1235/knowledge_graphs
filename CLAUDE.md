# Agent Policy
UNLESS STATED OTHERWISE, FOLLOW THIS STRICTLY. NOT FOLLOWING THIS ENTIRE FILE STRICTLY, IS A SERIOUS VAIOLATION. READ THIS ENTIRE FILE AND FOLLOW ALL THE RULES:
# General notes
1. after creating a plan, divide it into many tiny parts to implament sequentially, and after completing each part say (and only this) done with part i where i is the part number
(like done with part 1, done with part 2, ....).
DO NOT TERMINATE AFTER EACH PART, just report you finished it, and continue until you finish everything
2. in brainstorming phase, write your thoughts and plan in a seperate file, not in the chat
3. do not edit code not EXCUTE stuff without manually approving the plan. really wait for EXCPLICIT premmission to do ANYTHING.
4. unless directly stated otherwise, use short simple language when talking to me and in reports
5. remember after each micro step, deploy the change, and say done
6. use pymupdf4llm to convert givern pdf's to .md formats
like that i can track progression
7. DO NOT CREATE ARTIFACTS i cant edit them
8. When you run bash commands, output is NEVER at terminal, always output to a file
9. starting at the first msessage of the chat, EVERY message starts with what you understood from this global context file. do not skip a rule. tell me about common way you may not adhere to rules, and what would you do to prevent it from happening
> **WARNING TO ALL FUTURE AGENTS:** This is your primary directive file. You **MUST** adhere to this lifecycle when operating in this repository to prevent code clashing, GPU bottlenecks, and loss of intermediate experimental results.
>
> ### THE 100% COMPLIANCE & QUALITY RULE
> Every phase in this document is MANDATORY. Do not proceed until you have explicitly verified that the current phase (planning, implementation, demo, scribe, execution, reporting) is completed.
> **QUALITY MANDATE:** Artifacts (notebooks, reports) must be high-density. A lackluster summary with only text is considered a failure. Reports must include data-driven evidence, code for reproducibility, and professional-grade visualizations.
**RUNTIME MANDATE:** Every notebook created must be **verified to run start-to-finish** without error. Use  to confirm execution before finalization.
**PRE-EXECUTION MANDATE:** Delivered notebooks MUST be in a **fully executed state**. All code cells must show output cells (values, tables, and images) so the user can inspect results without re-running code.

## Phase 1: Ideation & Mapped Planning
3. **Mapped .md Planning:** Once a solution is agreed upon, you **must write a detailed execution plan** in the  directory (e.g. ). This allows all future agents and humans to understand what is being built.


### MANDATORY STOP: Await Approval
**After writing the plan, you MUST STOP. Present the plan to the user and wait for explicit confirmation (e.g., Proceed with the plan) before taking any further actions in implementation or execution.**

## Phase 2: Full Execution & Slurm Concurrency
Do not use generic names like .
2. **Dynamic Slurm Utilities:** Use  to programmatically spawn jobs with unique UUIDs and separated  outputs

## Phase 3: Post-Experiment & Reporting
1. **Analyze (Code-Driven):** Parse your results JSON and calculate the metrics defined in your planning document
