"""Part 2 of the cleanup: which files under predicate_correctness/ does v4 still need?

Start from the v4 entry points. Follow Python imports (ast) and text references
(dotted module names, relative paths, file names) until nothing new is found.
Read only. Writes keep_code.txt and remove_code.txt next to this script.
"""
import ast
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PC = os.path.join(ROOT, "predicate_correctness")
OUT = os.path.dirname(os.path.abspath(__file__))

# Folders always kept whole (partner copies, v4 data). Not candidates.
ALWAYS = ("from_shieldagent/", "output/eval_v4/", "output/logs/v4_", "state_tracker/v4/",
          "tests/fixtures_v4/", "scripts/v4_cases_gen/")
ALWAYS_FILES = {"output/predicate_types.json"}


def rel(p):
    return os.path.relpath(p, PC).replace(os.sep, "/")


def all_files():
    out = []
    for d, _, fs in os.walk(PC):
        for f in fs:
            p = os.path.join(d, f)
            out.append(rel(p))
    return sorted(out)


FILES = all_files()
FILESET = set(FILES)


# Round 2: this test only checks that v3 files did not change during the v4 runs. That job is done, and it names
# every v3 file by text, so it is dropped instead of followed.
DROP_ENTRIES = {"tests/test_v4_v3_untouched.py"}


def is_entry(r):
    b = os.path.basename(r)
    if r in DROP_ENTRIES:
        return False
    if r.startswith(ALWAYS) or r in ALWAYS_FILES:
        return True
    if r.startswith("guard/") and "_v4" in b:
        return True
    if r.startswith("scoring/v4_") or r.startswith("scripts/v4_"):
        return True
    if r.startswith("tests/") and (b.startswith("test_v4_") or b.startswith("audit_v4_")):
        return True
    if r == "scripts/build_questions_A4.py":
        return True
    return False


def module_to_files(mod):
    parts = mod.split(".")
    hits = []
    for i in range(1, len(parts) + 1):  # every package on the way, plus the module
        base = "/".join(parts[:i])
        for cand in (base + ".py", base + "/__init__.py"):
            if cand in FILESET:
                hits.append(cand)
    return hits


def py_imports(r):
    src = open(os.path.join(PC, r), encoding="utf-8", errors="replace").read()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    pkg = os.path.dirname(r).replace("/", ".")
    mods = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            base = n.module or ""
            if n.level:
                up = pkg.split(".") if pkg else []
                up = up[: len(up) - (n.level - 1)] if n.level > 1 else up
                base = ".".join([x for x in up + ([base] if base else []) if x])
            mods.append(base)
            mods += [base + "." + a.name if base else a.name for a in n.names]
    return mods


def text_refs(r, candidates):
    """Candidates named in r's text by dotted module, relative path or file name."""
    try:
        txt = open(os.path.join(PC, r), encoding="utf-8", errors="replace").read()
    except OSError:
        return []
    hits = []
    shell = r.endswith(".sh")
    for c in candidates:
        b = os.path.basename(c)
        keys = [c]
        if c.endswith(".py"):
            # Python code is followed by real imports only. A .py file named in text counts only from a shell
            # script (python path or "-m module").
            if not shell or b == "__init__.py":
                continue
            keys.append(c[:-3].replace("/", "."))
        else:
            keys.append(b)
        for k in keys:
            if re.search(r"(?<![\w.])" + re.escape(k) + r"(?![\w])", txt):
                hits.append(c)
                break
    return hits


def main():
    keep = {f for f in FILES if is_entry(f)}
    why = {f: "entry" for f in keep}
    # The partner's copies are kept whole but never scanned: their text names their own files, not ours.
    todo = [f for f in keep if f.endswith((".py", ".sh")) and not f.startswith("from_shieldagent/")]
    while todo:
        r = todo.pop()
        new = []
        if r.endswith(".py"):
            for m in py_imports(r):
                new += module_to_files(m)
        cands = [f for f in FILES if f not in keep]
        new += text_refs(r, cands)
        for f in new:
            if f not in keep:
                keep.add(f)
                why[f] = "used by " + r
                if f.endswith((".py", ".sh")):
                    todo.append(f)
    # packages of every kept module
    for f in list(keep):
        d = os.path.dirname(f)
        while d:
            i = d + "/__init__.py"
            if i in FILESET and i not in keep:
                keep.add(i)
                why[i] = "package of " + f
            d = os.path.dirname(d)
    remove = [f for f in FILES if f not in keep]
    with open(os.path.join(OUT, "keep_code.txt"), "w") as fh:
        for f in sorted(keep):
            fh.write(f"{f}\t{why[f]}\n")
    with open(os.path.join(OUT, "remove_code.txt"), "w") as fh:
        for f in remove:
            fh.write(f + "\n")
    print(f"files {len(FILES)} keep {len(keep)} remove {len(remove)}")


if __name__ == "__main__":
    sys.exit(main())
