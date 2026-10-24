"""Gold code and gold data must never reach the tracker or the guard (overview.md ground rule 5; p7.md subtask 4).

Checks every file under state_tracker/, guard/ and fork/ (the eval v2 fork code, added in eval v2 Part 3b):
  1. No import of gold code: `agent` / `agent.predicates` (ShieldAgent's gold package), `scoring` (the only folder
     that loads gold), or any module whose name contains "gold".
  2. No gold path in the text: the copy from_shieldagent/gold, ShieldAgent's gold folders and scripts, gold files.
  3. No Python string constant that is exactly "gold" (a path part such as os.path.join(FROM_SA, "gold")).
  4. At run time: importing every module of state_tracker/, guard/ and fork/ loads no gold or scoring module and
     opens no gold file (checked with an audit hook in a fresh Python process).

Tracker v3 (docs/planning/tracker_v3/p1.md step 4): every v3 file is checked too. state_tracker/v3/, guard/*_v3.py
and fork/offline_v3.py are inside the folders above (same checks, unchanged). The v3 files outside them,
V3_EXTRA_GLOBS (scoring/v3_*.py, tests/test_v3_*.py, tests/audit_v3_*.py), get checks 1-4 as well, with one
allowance: they may import the v3 scoring modules (`scoring`, `scoring.v3_*`) and name them in text
("scoring/v3_..."). Any other scoring module (the gold loader, p7_results, ...) is refused; relative imports in them
are resolved first. The rest of scoring/ is not scanned (it holds the gold loader). A v3 file that does not exist yet
is covered when it appears.

Run from predicate_correctness/:  python3 -B -m unittest tests.test_no_gold_import -v
Standard library only.
"""
from __future__ import annotations

import ast
import fnmatch
import glob
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_DIRS = ("state_tracker", "guard", "fork")
# v3 files outside SCAN_DIRS (docs/planning/tracker_v3/overview.md, "Reference"), relative to predicate_correctness/.
V3_EXTRA_GLOBS = ("scoring/v3_*.py", "tests/test_v3_*.py", "tests/audit_v3_*.py")
# Every v3 file pattern; the first three are inside SCAN_DIRS.
V3_PATTERNS = ("state_tracker/v3/*", "guard/*_v3.py", "fork/offline_v3.py") + V3_EXTRA_GLOBS
V3_SCORING_TEXT = "scoring/v3_"

# Text that names gold code or gold data. Case-sensitive on purpose: "from_shieldagent/policies" (our policy copy)
# must not match "ShieldAgent/policies" (gold).
GOLD_PATTERNS = (
    "from_shieldagent/gold", "from_shieldagent.gold", "from_shieldagent\\gold",
    "agent/predicates", "agent.predicates",
    "ShieldAgent/aspm", "ShieldAgent/policies", "ShieldAgent/agent",
    "scripts/aspm_src", "aspm_src", "build_aspm", "validate_aspm", "p6_gold_score",
    "gold.jsonl", "gold_v2", "gold_loader", "scoring.p7_results", "scoring/",
)
BANNED_IMPORT_ROOTS = ("agent", "scoring")
TEXT_EXT = (".py", ".json", ".md", ".txt", ".cfg", ".toml", ".yaml", ".yml", ".sh")


def files_to_scan(root: str = PC_DIR):
    for d in SCAN_DIRS:
        base = os.path.join(root, d)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if x != "__pycache__"]
            for f in sorted(filenames):
                yield os.path.join(dirpath, f)
    yield from v3_extra_files(root)


def v3_extra_files(root: str = PC_DIR):
    """The existing v3 files outside SCAN_DIRS (V3_EXTRA_GLOBS), sorted."""
    out = set()
    for g in V3_EXTRA_GLOBS:
        out |= {p for p in glob.glob(os.path.join(root, *g.split("/"))) if os.path.isfile(p)}
    return sorted(out)


def is_v3_extra(path: str, root: str = PC_DIR) -> bool:
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    return any(fnmatch.fnmatchcase(rel, g) for g in V3_EXTRA_GLOBS) and rel.count("/") == 1


def package_of(path: str, root: str = PC_DIR) -> str:
    """The package of a file below root ("scoring" for scoring/v3_x.py), to resolve its relative imports."""
    return os.path.dirname(os.path.relpath(path, root)).replace(os.sep, ".")


def _read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def text_hits(text: str, allow_v3_scoring: bool = False):
    """The gold patterns that occur in a text. allow_v3_scoring (v3 files outside SCAN_DIRS only): a mention of a v3
    scoring file ("scoring/v3_...") is not a hit; every other pattern still is."""
    if allow_v3_scoring:
        text = text.replace(V3_SCORING_TEXT, "\0")
    return [p for p in GOLD_PATTERNS if p in text]


def _v3_scoring_module(name: str) -> bool:
    return name == "scoring" or name.startswith("scoring.v3_")


def import_hits(source: str, allow_v3_scoring: bool = False, package: str = ""):
    """Imported module names that are gold code, the scoring folder, or contain 'gold'.

    allow_v3_scoring and package are for the v3 files outside SCAN_DIRS only: there, `scoring` and `scoring.v3_*`
    may be imported, and relative imports are first resolved against package. Without them (SCAN_DIRS files), the
    check is the original one."""
    hits = []
    for node in ast.walk(ast.parse(source)):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if package and node.level:
                parts = package.split(".")
                base = parts[:len(parts) - (node.level - 1)] if node.level - 1 < len(parts) else []
                mod = ".".join(base + ([mod] if mod else []))
            names = [mod] + [f"{mod}.{a.name}" if mod else a.name for a in node.names]
        for n in names:
            root = n.split(".")[0]
            if allow_v3_scoring and _v3_scoring_module(n) and "gold" not in n.lower():
                continue
            if root in BANNED_IMPORT_ROOTS or "gold" in n.lower():
                hits.append(n)
    return hits


def gold_constants(source: str):
    """String constants that are exactly a gold path part ("gold", "gold/")."""
    return [node.value for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and node.value.strip("/\\").lower() == "gold"]


# The run-time check: runs in a fresh process, prints a JSON report.
# argv: pc, comma list of folders, [comma list of globs (V3_EXTRA_GLOBS), "1" = allow scoring / scoring.v3_*].
_RUNTIME = r"""
import glob, importlib, json, os, sys
sys.dont_write_bytecode = True
pc = sys.argv[1]
sys.path.insert(0, pc)
opened = []
def hook(event, args):
    if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
        opened.append(os.fsdecode(args[0]))
sys.addaudithook(hook)
mods, errors = [], {}
for d in [x for x in sys.argv[2].split(",") if x]:
    base = os.path.join(pc, d)
    if not os.path.isdir(base):
        continue
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [x for x in dirnames if x != "__pycache__"]
        for f in sorted(filenames):
            if f.endswith(".py"):
                rel = os.path.relpath(os.path.join(dirpath, f), pc)[:-3].replace(os.sep, ".")
                if rel.endswith(".__init__"):
                    rel = rel[: -len(".__init__")]
                mods.append(rel)
globs = [x for x in sys.argv[3].split(",") if x] if len(sys.argv) > 3 else []
allow_v3 = len(sys.argv) > 4 and sys.argv[4] == "1"
for g in globs:
    for p in sorted(glob.glob(os.path.join(pc, *g.split("/")))):
        if os.path.isfile(p) and p.endswith(".py"):
            mods.append(os.path.relpath(p, pc)[:-3].replace(os.sep, "."))
for m in mods:
    try:
        importlib.import_module(m)
    except Exception as e:
        errors[m] = repr(e)
gold_dir = os.path.join(pc, "from_shieldagent", "gold")
def allowed_scoring(n):
    return allow_v3 and (n == "scoring" or n.startswith("scoring.v3_")) and "gold" not in n.lower()
bad_mods = sorted(n for n, mod in list(sys.modules.items())
                  if n == "agent" or n.startswith("agent.")
                  or ((n == "scoring" or n.startswith("scoring.")) and not allowed_scoring(n))
                  or os.path.abspath(str(getattr(mod, "__file__", "") or "")).startswith(gold_dir))
bad_open = sorted({p for p in opened if os.path.abspath(p).startswith(gold_dir)
                   or "/ShieldAgent/aspm" in p or "/ShieldAgent/policies" in p
                   or "/ShieldAgent/agent/predicates" in p or "gold" in os.path.basename(p).lower()})
print(json.dumps({"modules": mods, "errors": errors, "bad_modules": bad_mods, "bad_open": bad_open}))
"""


class TestDetectors(unittest.TestCase):
    """The checks must catch planted violations, so a pass below means something."""

    def test_text_hits(self):
        self.assertTrue(text_hits("p = os.path.join(PC, 'from_shieldagent/gold/retail.py')"))
        self.assertTrue(text_hits("x = '~/ShieldAgent/policies/gold_v2/x.json'"))
        self.assertFalse(text_hits("p = os.path.join(FROM_SA, 'policies', 'retail_wiki.txt')"))
        self.assertFalse(text_hits("membership == 'gold'  # gold member"))

    def test_import_hits(self):
        self.assertEqual(import_hits("from agent.predicates import retail"),
                         ["agent.predicates", "agent.predicates.retail"])
        self.assertTrue(import_hits("import scoring.gold_loader"))
        self.assertTrue(import_hits("from scoring import p7_results"))
        self.assertTrue(import_hits("import gold_tools"))
        self.assertFalse(import_hits("from state_tracker import paths\nimport json"))

    def test_gold_constants(self):
        self.assertEqual(gold_constants("p = os.path.join(FROM_SA, 'gold')"), ["gold"])
        self.assertEqual(gold_constants("t = 'gold member'"), [])

    def test_v3_scoring_allowance(self):
        # SCAN_DIRS files: unchanged, every scoring import and every "scoring/" text is a hit.
        self.assertTrue(import_hits("from scoring import v3_report"))
        self.assertTrue(text_hits("see scoring/v3_report.py"))
        # v3 files outside SCAN_DIRS: scoring.v3_* is allowed, nothing else of scoring/.
        allow = dict(allow_v3_scoring=True)
        self.assertEqual(import_hits("from scoring import v3_report\nimport scoring.v3_common", **allow), [])
        self.assertEqual(import_hits("from scoring.v3_common import f", **allow), [])
        self.assertTrue(import_hits("from scoring import p7_results", **allow))
        self.assertTrue(import_hits("import scoring.gold_loader", **allow))
        self.assertTrue(import_hits("from scoring.v3_common import gold_values", **allow))
        self.assertTrue(import_hits("from agent.predicates import retail", **allow))
        self.assertTrue(import_hits("from . import p7_results", package="scoring", **allow))
        self.assertTrue(import_hits("from .p7_results import x", package="scoring", **allow))
        self.assertEqual(import_hits("from . import v3_common", package="scoring", **allow), [])
        self.assertEqual(import_hits("from .v3_common import f", package="scoring", **allow), [])
        self.assertEqual(text_hits("see scoring/v3_report.py", **allow), [])
        self.assertTrue(text_hits("see scoring/p7_results.py", **allow))
        self.assertTrue(text_hits("x = 'from_shieldagent/gold/retail.py'", **allow))

    def test_v3_patterns_are_scanned(self):
        """In a planted tree, every v3 file pattern is scanned and the rest of scoring/ and tests/ is not."""
        v3 = ["state_tracker/v3/__init__.py", "state_tracker/v3/facts_format_v3.py", "state_tracker/v3/t.json",
              "guard/tgr_tracker_v3.py", "fork/offline_v3.py", "scoring/v3_report.py", "tests/test_v3_x.py",
              "tests/audit_v3_x.py"]
        other = ["scoring/gold_loader.py", "scoring/p7_results.py", "scoring/__init__.py", "tests/test_guard.py",
                 "tests/audit_v2_ref_guards.py", "tests/check_copies.py"]
        with tempfile.TemporaryDirectory(prefix="no_gold_test_") as root:
            for d in SCAN_DIRS:
                os.makedirs(os.path.join(root, d), exist_ok=True)
            for rel in v3 + other:
                p = os.path.join(root, *rel.split("/"))
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    f.write("")
            scanned = {os.path.relpath(p, root).replace(os.sep, "/") for p in files_to_scan(root)}
            self.assertEqual(scanned & set(other), set())
            self.assertEqual(set(v3) - scanned, set())
            self.assertEqual({r for r in scanned if is_v3_extra(os.path.join(root, r), root)},
                             {"scoring/v3_report.py", "tests/test_v3_x.py", "tests/audit_v3_x.py"})

    def test_runtime_v3_extra_catches_planted_import(self):
        """The run-time check of the v3 files outside SCAN_DIRS flags a v3 scoring module that loads another one."""
        files = {"scoring/__init__.py": "", "scoring/p7_results.py": "X = 1\n",
                 "scoring/v3_ok.py": "import json\n", "scoring/v3_bad.py": "from scoring import p7_results\n",
                 "tests/__init__.py": "", "tests/test_v3_ok.py": "from scoring import v3_ok\n"}
        with tempfile.TemporaryDirectory(prefix="no_gold_rt_") as root:
            for rel, text in files.items():
                p = os.path.join(root, *rel.split("/"))
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(text)
            r = subprocess.run([sys.executable, "-B", "-c", _RUNTIME, root, "", ",".join(V3_EXTRA_GLOBS), "1"],
                               capture_output=True, text=True, cwd=root, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            rep = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(sorted(rep["modules"]), ["scoring.v3_bad", "scoring.v3_ok", "tests.test_v3_ok"])
        self.assertEqual(rep["bad_modules"], ["scoring.p7_results"])


class TestNoGoldInTrackerOrGuard(unittest.TestCase):

    def test_scan_dirs_exist(self):
        for d in SCAN_DIRS:
            self.assertTrue(os.path.isdir(os.path.join(PC_DIR, d)), d)
        self.assertTrue(any(f.endswith(".py") for f in files_to_scan()), "nothing to scan")

    def test_every_v3_file_is_scanned(self):
        scanned = {os.path.relpath(p, PC_DIR).replace(os.sep, "/") for p in files_to_scan()}
        v3 = set()
        for pat in V3_PATTERNS:
            v3 |= {os.path.relpath(p, PC_DIR).replace(os.sep, "/")
                   for p in glob.glob(os.path.join(PC_DIR, *pat.split("/"))) if os.path.isfile(p)}
        v3 = {r for r in v3 if "__pycache__" not in r}
        self.assertIn("state_tracker/v3/frozen.py", v3)
        self.assertIn("tests/test_v3_frozen.py", v3)
        self.assertEqual(v3 - scanned, set())
        self.assertNotIn("scoring/gold_loader.py", scanned)

    def test_no_gold_imports(self):
        bad = {}
        for path in files_to_scan():
            if path.endswith(".py"):
                if is_v3_extra(path):
                    hits = import_hits(_read(path), allow_v3_scoring=True, package=package_of(path))
                else:
                    hits = import_hits(_read(path))
                if hits:
                    bad[os.path.relpath(path, PC_DIR)] = hits
        self.assertEqual(bad, {})

    def test_no_gold_paths_in_text(self):
        bad = {}
        for path in files_to_scan():
            if path.endswith(TEXT_EXT):
                hits = text_hits(_read(path), allow_v3_scoring=is_v3_extra(path))
                if hits:
                    bad[os.path.relpath(path, PC_DIR)] = hits
        self.assertEqual(bad, {})

    def test_no_gold_path_parts(self):
        bad = {}
        for path in files_to_scan():
            if path.endswith(".py"):
                hits = gold_constants(_read(path))
                if hits:
                    bad[os.path.relpath(path, PC_DIR)] = hits
        self.assertEqual(bad, {})

    def test_runtime_imports_and_reads(self):
        r = subprocess.run([sys.executable, "-B", "-c", _RUNTIME, PC_DIR, ",".join(SCAN_DIRS)], capture_output=True,
                           text=True, cwd=PC_DIR, timeout=600)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        rep = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertTrue(rep["modules"], "no module imported")
        for d in SCAN_DIRS:
            self.assertTrue(any(m == d or m.startswith(d + ".") for m in rep["modules"]), f"no module of {d}/")
        self.assertIn("fork.run_branch", rep["modules"])
        self.assertIn("fork.run_all", rep["modules"])
        self.assertEqual(rep["errors"], {})
        self.assertEqual(rep["bad_modules"], [])
        self.assertEqual(rep["bad_open"], [])

    def test_runtime_imports_and_reads_v3_extra(self):
        """Importing every v3 module outside SCAN_DIRS loads no gold module and no scoring module other than
        scoring.v3_*, and opens no gold file."""
        r = subprocess.run([sys.executable, "-B", "-c", _RUNTIME, PC_DIR, "", ",".join(V3_EXTRA_GLOBS), "1"],
                           capture_output=True, text=True, cwd=PC_DIR, timeout=600)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        rep = json.loads(r.stdout.strip().splitlines()[-1])
        want = sorted(os.path.relpath(p, PC_DIR)[:-3].replace(os.sep, ".") for p in v3_extra_files()
                      if p.endswith(".py"))
        self.assertEqual(sorted(rep["modules"]), want)
        self.assertIn("tests.test_v3_frozen", rep["modules"])
        self.assertEqual(rep["errors"], {})
        self.assertEqual(rep["bad_modules"], [])
        self.assertEqual(rep["bad_open"], [])


if __name__ == "__main__":
    unittest.main()
