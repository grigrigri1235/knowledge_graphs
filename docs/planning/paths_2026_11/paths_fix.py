"""Path move: original machine -> this machine (plan: plan.md).

Usage: python3 -B paths_fix.py dry|apply   (run from repo root)
Exact byte-string replacement, rules applied in order. Line endings untouched.
"""
import os
import subprocess
import sys

RULES = [
    ("A", b"/home/azureuser/code_projects", b"/home/grigrigri1235/knowledge_graphs"),
    ("A2", b"~/code_projects", b"~/knowledge_graphs"),
    ("B", b"/home/azureuser/miniconda3", b"/home/grigrigri1235/miniconda3"),
    ("C", b"/home/azureuser", b"/home/grigrigri1235"),
]
EXCLUDE = (
    "predicate_correctness/from_shieldagent/",
    "predicate_correctness/output/",
    "docs/planning/cleanup_2026_11/",
    "docs/planning/paths_2026_11/",
)
SPECIAL_FILE = "codebase_structure.md"
SPECIAL_OLD = b"The original machine path was `/home/grigrigri1235/knowledge_graphs`; docs and code still name it."
SPECIAL_NEW = (b"Paths were moved from the original machine (`/home/azureuser/code_projects`) to this one on "
               b"2026-11-17 (`docs/planning/paths_2026_11/`).")


def file_set():
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout
    skipped = []
    files = []
    for p in out.decode().split("\0"):
        if not p or p.startswith(EXCLUDE):
            continue
        if os.path.islink(p) or not os.path.isfile(p):
            skipped.append((p, "link/missing"))
            continue
        with open(p, "rb") as f:
            data = f.read()
        if b"\0" in data[:8192]:
            skipped.append((p, "binary"))
            continue
        files.append(p)
    return files, skipped


def main(mode):
    files, skipped = file_set()
    totals = {r[0]: 0 for r in RULES}
    rows = []
    for p in files:
        with open(p, "rb") as f:
            data = f.read()
        new = data
        hits = {}
        for name, old, rep in RULES:
            hits[name] = new.count(old)
            new = new.replace(old, rep)
        special = 0
        if p == SPECIAL_FILE:
            special = new.count(SPECIAL_OLD)
            new = new.replace(SPECIAL_OLD, SPECIAL_NEW)
        if new != data:
            for k, v in hits.items():
                totals[k] += v
            rows.append((p, hits, special))
            if mode == "apply":
                with open(p, "wb") as f:
                    f.write(new)
    lines = ["# file\tA\tA2\tB\tC" + ("\tspecial" if mode else "")]
    for p, h, s in rows:
        lines.append(f"{p}\t{h['A']}\t{h['A2']}\t{h['B']}\t{h['C']}" + (f"\tspecial={s}" if s else ""))
    lines.append(f"TOTAL files={len(rows)}\tA={totals['A']}\tA2={totals['A2']}\tB={totals['B']}\tC={totals['C']}"
                 f"\tfiles_in_set={len(files)}\tskipped={len(skipped)}")
    lines.append("# skipped (binary / symlink / missing):")
    lines += [f"#   {p}\t{why}" for p, why in skipped]
    print("\n".join(lines))


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("dry", "apply"):
        sys.exit(__doc__)
    main(sys.argv[1])
