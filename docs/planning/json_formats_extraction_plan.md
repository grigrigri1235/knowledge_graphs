# Plan: Extract JSON Formats from ShieldAgent Paper

## Goal
Identify all JSON structures/schemas mentioned in `ShieldAgent_paper.md` and document each in its own file under `docs/file_formats/`.

---

## Micro-Steps for Sequential Execution

1. **Part 1:** Search `ShieldAgent_paper.md` for JSON code blocks, formats, or structural descriptions.
2. **Part 2:** In the `docs/file_formats/` directory, write there each unique JSON schema to its own appropriately named file (e.g., `<json_schema_name>.json`).
3. **Part 3:** Update `codebase_structure.md` to include the new `docs/file_formats/` directory and report the extracted files.