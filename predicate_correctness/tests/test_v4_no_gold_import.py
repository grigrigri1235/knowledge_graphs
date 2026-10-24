"""Tracker v4: gold code and gold data never reach the v4 guard, the v4 tracker or the v4 scoring code.

A copy of the logic of tests/test_no_gold_import.py (v3, unchanged; it keeps running as a regression), for the v4
files (docs/planning/tracker_v4/code_change_map.md sections 0.1 and 2):
  STRICT     every file under guard/ (v2, v3 and v4 guard code) and state_tracker/v4/: no import of gold code
             (`agent`, `agent.predicates`, any module with "gold" in its name) and no import of the scoring folder;
  V4_EXTRA   scoring/v4_*.py|sh, tests/test_v4_*.py, tests/audit_v4_*.py, scripts/v4_*.py|sh: no gold import; they
             may import the v3 and v4 scoring modules (`scoring`, `scoring.v3_*`, `scoring.v4_*`) and nothing else
             of scoring/ (the gold loader, p7_results, ...); relative imports are resolved first.
             This file itself is left out (it names the gold patterns on purpose), as v3's test is.
Checks on every scanned file:
  1. no gold import (AST); in STRICT files also no scoring import;
  2. no gold path in the text (the v3 patterns). One change from v3: a mention of a v3 or v4 scoring file
     ("scoring/v3_...", "scoring/v4_...") is not a hit anywhere (guard/run_online_v4.py names scoring/v4_freeze.py);
  3. no Python string constant that is exactly "gold" used as a path part: a value with a slash, an argument of a
     path call (os.path.join, Path, open, glob, ...), an operand of + or /, or the value of a name / key / keyword
     that names a path (GOLD_DIR = "gold"). v3 flagged every such constant; v4's fact helpers and tests use "gold"
     as data (membership level, product color), which is left alone. The run-time check (5) still catches any
     open of a gold file;
  4. a module name in a string (importlib targets such as "scoring.v4_freeze") is never gold code and, outside
     scoring.v3_* / scoring.v4_*, never a scoring module;
  5. at run time, in a fresh process: importing every STRICT module loads no gold or scoring module and opens no
     gold file; importing every V4_EXTRA module loads no gold module and no scoring module other than v3 / v4 ones.
Planted cases show that each detector fires.

Run from predicate_correctness/ with the runner Python:
    ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v4_no_gold_import -v
Standard library only. No LLM call, no network.
"""
from __future__ import annotations

import ast
import fnmatch
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STRICT_DIRS = ("guard", "state_tracker/v4")
V4_EXTRA_GLOBS = ("scoring/v4_*.py", "scoring/v4_*.sh", "tests/test_v4_*.py", "tests/audit_v4_*.py",
                  "scripts/v4_*.py", "scripts/v4_*.sh")
SELF = "tests/test_v4_no_gold_import.py"
ALLOWED_SCORING_TEXT = ("scoring/v3_", "scoring/v4_")

# As tests/test_no_gold_import.py (case-sensitive on purpose).
GOLD_PATTERNS = (
    "from_shieldagent/gold", "from_shieldagent.gold", "from_shieldagent\\gold",
    "agent/predicates", "agent.predicates",
    "ShieldAgent/aspm", "ShieldAgent/policies", "ShieldAgent/agent",
    "scripts/aspm_src", "aspm_src", "build_aspm", "validate_aspm", "p6_gold_score",
    "gold.jsonl", "gold_v2", "gold_loader", "scoring.p7_results", "scoring/",
)
BANNED_IMPORT_ROOTS = ("agent", "scoring")
TEXT_EXT = (".py", ".json", ".md", ".txt", ".cfg", ".toml", ".yaml", ".yml", ".sh")
PATH_CALL_WORDS = ("join", "Path", "path", "open", "glob", "listdir", "walk", "exists", "isdir", "isfile", "copy",
                   "remove", "makedirs", "mkdir")
_MODULE_STRING = re.compile(r"^(agent|scoring|from_shieldagent)(\.[A-Za-z_][A-Za-z0-9_]*)+$|^[A-Za-z_.]*gold[A-Za-z_.]*$")


# ------------------------------------------------------------------------------------------------ file sets
def strict_files(root: str = PC_DIR):
    out = []
    for d in STRICT_DIRS:
        for dirpath, dirnames, filenames in os.walk(os.path.join(root, *d.split("/"))):
            dirnames[:] = sorted(x for x in dirnames if x != "__pycache__")
            out += [os.path.join(dirpath, f) for f in sorted(filenames)]
    return out


def extra_files(root: str = PC_DIR):
    out = set()
    for g in V4_EXTRA_GLOBS:
        out |= {p for p in glob.glob(os.path.join(root, *g.split("/"))) if os.path.isfile(p)}
    return sorted(p for p in out if _rel(p, root) != SELF)


def files_to_scan(root: str = PC_DIR):
    return strict_files(root) + extra_files(root)


def _rel(path: str, root: str = PC_DIR) -> str:
    return os.path.relpath(path, root).replace(os.sep, "/")


def is_extra(path: str, root: str = PC_DIR) -> bool:
    rel = _rel(path, root)
    return any(fnmatch.fnmatchcase(rel, g) for g in V4_EXTRA_GLOBS) and rel.count("/") == 1


def package_of(path: str, root: str = PC_DIR) -> str:
    return os.path.dirname(os.path.relpath(path, root)).replace(os.sep, ".")


def _read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


# ------------------------------------------------------------------------------------------------ detectors
def text_hits(text: str):
    for allowed in ALLOWED_SCORING_TEXT:
        text = text.replace(allowed, "\0")
    return [p for p in GOLD_PATTERNS if p in text]


def allowed_scoring_module(name: str) -> bool:
    return (name == "scoring" or name.startswith("scoring.v3_") or name.startswith("scoring.v4_")) \
        and "gold" not in name.lower()


def import_hits(source: str, allow_scoring: bool = False, package: str = ""):
    """Imported module names that are gold code, contain 'gold', or (unless allowed) are of the scoring folder."""
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
            if allow_scoring and allowed_scoring_module(n):
                continue
            if n.split(".")[0] in BANNED_IMPORT_ROOTS or "gold" in n.lower():
                hits.append(n)
    return hits


PATH_NAME_WORDS = ("dir", "path", "root", "folder", "file")


def _names_path(text: str) -> bool:
    return any(w in text.lower() for w in PATH_NAME_WORDS)


def _is_path_context(node: ast.Constant, parents: dict) -> bool:
    """Is a "gold" constant used as a path part? A value with a slash ("gold/", "/gold") always is. Otherwise: an
    argument of a call that builds or opens a path (os.path.join, Path, open, glob, ...), an operand of + or /
    (BASE + "/" + "gold"), or the value given to a name, key or keyword that names a path (GOLD_DIR = "gold",
    {"dir": "gold"}). Everything else is a data value (a membership level, a product color in a test fixture)."""
    if any(c in node.value for c in "/\\"):
        return True
    parent = parents.get(node)
    if isinstance(parent, ast.Starred):
        parent = parents.get(parent)
    if isinstance(parent, (ast.Tuple, ast.List)) and isinstance(parents.get(parent), ast.Starred):
        parent = parents.get(parents.get(parent))
    if isinstance(parent, ast.Call):
        in_args = any(x is node or (isinstance(x, ast.Starred) and any(y is node for y in ast.walk(x)))
                      for x in parent.args)
        return in_args and any(w in ast.unparse(parent.func) for w in PATH_CALL_WORDS) or (
            isinstance(parent.func, ast.Attribute) and parent.func.attr == "joinpath")
    if isinstance(parent, ast.BinOp):
        return isinstance(parent.op, (ast.Add, ast.Div))
    if isinstance(parent, (ast.Assign, ast.AnnAssign)):
        targets = parent.targets if isinstance(parent, ast.Assign) else [parent.target]
        return any(_names_path(ast.unparse(t)) for t in targets)
    if isinstance(parent, ast.Dict):
        return any(v is node and isinstance(k, ast.Constant) and isinstance(k.value, str) and _names_path(k.value)
                   for k, v in zip(parent.keys, parent.values))
    if isinstance(parent, ast.keyword):
        return bool(parent.arg) and _names_path(parent.arg)
    return False


def gold_constants(source: str):
    """String constants that are exactly a gold path part ("gold", "gold/") used as a path (_is_path_context)."""
    tree = ast.parse(source)
    parents = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and node.value.strip("/\\").lower() == "gold" and _is_path_context(node, parents)]


def module_string_hits(source: str):
    """String constants that name a gold module or (other than scoring.v3_* / v4_*) a scoring module."""
    hits = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and _MODULE_STRING.match(node.value):
            v = node.value
            if allowed_scoring_module(v) or v.strip("/\\").lower() == "gold":   # a plain "gold": gold_constants
                continue
            if False:
                continue
            if v.split(".")[0] in ("agent", "scoring") or "gold" in v.lower() or v.startswith("from_shieldagent.gold"):
                hits.append(v)
    return hits


# The run-time check (fresh process; prints one JSON line). argv: pc, comma list of folders, comma list of globs,
# "1" = allow scoring / scoring.v3_* / scoring.v4_*, comma list of relative paths to leave out.
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
skip = set(x for x in sys.argv[5].split(",") if x) if len(sys.argv) > 5 else set()
mods, errors = [], {}
for d in [x for x in sys.argv[2].split(",") if x]:
    base = os.path.join(pc, *d.split("/"))
    if not os.path.isdir(base):
        continue
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(x for x in dirnames if x != "__pycache__")
        for f in sorted(filenames):
            if f.endswith(".py"):
                rel = os.path.relpath(os.path.join(dirpath, f), pc)[:-3].replace(os.sep, ".")
                if rel.endswith(".__init__"):
                    rel = rel[: -len(".__init__")]
                mods.append(rel)
globs = [x for x in sys.argv[3].split(",") if x] if len(sys.argv) > 3 else []
allow = len(sys.argv) > 4 and sys.argv[4] == "1"
for g in globs:
    for p in sorted(glob.glob(os.path.join(pc, *g.split("/")))):
        rel = os.path.relpath(p, pc).replace(os.sep, "/")
        if os.path.isfile(p) and p.endswith(".py") and rel not in skip:
            mods.append(rel[:-3].replace("/", "."))
for m in mods:
    try:
        importlib.import_module(m)
    except Exception as e:
        errors[m] = repr(e)
gold_dir = os.path.join(pc, "from_shieldagent", "gold")
def allowed_scoring(n):
    return allow and (n == "scoring" or n.startswith("scoring.v3_") or n.startswith("scoring.v4_")) \
        and "gold" not in n.lower()
bad_mods = sorted(n for n, mod in list(sys.modules.items())
                  if n == "agent" or n.startswith("agent.") or "gold" in n.lower()
                  or ((n == "scoring" or n.startswith("scoring.")) and not allowed_scoring(n))
                  or os.path.abspath(str(getattr(mod, "__file__", "") or "")).startswith(gold_dir))
bad_open = sorted({p for p in opened if os.path.abspath(p).startswith(gold_dir)
                   or "/ShieldAgent/aspm" in p or "/ShieldAgent/policies" in p
                   or "/ShieldAgent/agent/predicates" in p or "gold" in os.path.basename(p).lower()})
print(json.dumps({"modules": mods, "errors": errors, "bad_modules": bad_mods, "bad_open": bad_open}))
"""


def run_runtime(root: str, dirs, globs, allow: bool, skip=()):
    r = subprocess.run([sys.executable, "-B", "-c", _RUNTIME, root, ",".join(dirs), ",".join(globs),
                        "1" if allow else "0", ",".join(skip)],
                       capture_output=True, text=True, cwd=root, timeout=900,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0"))
    return r


# ------------------------------------------------------------------------------------------------ tests
class TestDetectors(unittest.TestCase):
    """Each check must catch a planted violation, so a pass below means something."""

    def test_text_hits(self):
        self.assertTrue(text_hits("p = os.path.join(PC, 'from_shieldagent/gold/retail.py')"))
        self.assertTrue(text_hits("x = '~/ShieldAgent/policies/gold_v2/x.json'"))
        self.assertTrue(text_hits("see scoring/gold_loader.py"))
        self.assertTrue(text_hits("see scoring/p7_results.py"))
        self.assertEqual(text_hits("see scoring/v4_freeze.py and scoring/v3_online_metrics.py"), [])
        self.assertFalse(text_hits("membership == 'gold'  # gold member"))

    def test_import_hits(self):
        self.assertEqual(import_hits("from agent.predicates import retail"),
                         ["agent.predicates", "agent.predicates.retail"])
        self.assertTrue(import_hits("import scoring.gold_loader"))
        self.assertTrue(import_hits("from scoring import v4_freeze"))          # strict: no scoring at all
        self.assertTrue(import_hits("import gold_tools"))
        self.assertFalse(import_hits("from state_tracker.v3 import questions as Q\nimport json"))
        allow = dict(allow_scoring=True)
        self.assertEqual(import_hits("from scoring import v4_online_metrics\nimport scoring.v3_online_metrics",
                                     **allow), [])
        self.assertTrue(import_hits("from scoring import p7_results", **allow))
        self.assertTrue(import_hits("import scoring.gold_loader", **allow))
        self.assertTrue(import_hits("from scoring.v4_x import gold_values", **allow))
        self.assertTrue(import_hits("from . import p7_results", package="scoring", **allow))
        self.assertEqual(import_hits("from . import v4_online_metrics", package="scoring", **allow), [])
        self.assertTrue(import_hits("from .gold_loader import x", package="scoring", **allow))

    def test_gold_constants(self):
        self.assertEqual(gold_constants("p = os.path.join(FROM_SA, 'gold')"), ["gold"])
        self.assertEqual(gold_constants("p = FROM_SA + '/' + 'gold/'"), ["gold/"])
        self.assertEqual(gold_constants("t = 'gold member'"), [])
        # membership levels are not a gold path
        self.assertEqual(gold_constants("ok = user['membership'] == 'gold'"), [])
        self.assertEqual(gold_constants("ok = m in ('silver', 'gold')"), [])
        self.assertEqual(gold_constants("u = {'membership': 'gold', 'name': 'x'}"), [])
        self.assertEqual(gold_constants("u = make_user(membership='gold')"), [])
        self.assertEqual(gold_constants("x = {'dir': 'gold'}"), ["gold"])
        self.assertEqual(gold_constants("c = airline_compensation('gold')"), [])
        self.assertEqual(gold_constants("x = [i for i, v in vs.items() if v['options']['color'] == 'gold']"), [])
        self.assertEqual(gold_constants("self.miss('retail', s, 'x', a, [('new item for Smartphone', 'gold')])"), [])
        self.assertEqual(gold_constants("GOLD_DIR = 'gold'"), ["gold"])
        self.assertEqual(gold_constants("p = BASE / 'gold'"), ["gold"])
        self.assertEqual(gold_constants("p = os.path.join(*(SA, 'gold'))"), ["gold"])
        self.assertEqual(gold_constants("p = f'{SA}/gold'"), ["/gold"])
        self.assertEqual(gold_constants("p = pathlib.Path(BASE, 'gold')"), ["gold"])
        self.assertEqual(gold_constants("f = open(os.path.join(SA, 'gold', 'retail.py'))"), ["gold"])

    def test_module_string_hits(self):
        self.assertEqual(module_string_hits("FREEZE_MODULE = 'scoring.v4_freeze'"), [])
        self.assertEqual(module_string_hits("M = 'scoring.gold_loader'"), ["scoring.gold_loader"])
        self.assertEqual(module_string_hits("M = 'scoring.p7_results'"), ["scoring.p7_results"])
        self.assertEqual(module_string_hits("M = 'agent.predicates.retail'"), ["agent.predicates.retail"])
        self.assertEqual(module_string_hits("M = 'gold_tools'"), ["gold_tools"])
        self.assertEqual(module_string_hits("t = 'a gold member'"), [])
        self.assertEqual(module_string_hits("m = ['silver', 'gold']"), [])

    def test_planted_tree_scan_sets(self):
        files = ["guard/x_v4.py", "guard/tgr_tracker_v3.py", "state_tracker/v4/listing_v4.py",
                 "scoring/v4_metrics.py", "scoring/v4_after.sh", "tests/test_v4_x.py", "tests/audit_v4_y.py",
                 "scripts/v4_merge.py", "scripts/v4_dry.sh", SELF]
        other = ["scoring/gold_loader.py", "scoring/v3_x.py", "state_tracker/v3/questions.py", "tests/test_v3_x.py",
                 "scripts/v3_session/tqa_dump.py"]
        with tempfile.TemporaryDirectory(prefix="v4_no_gold_") as root:
            for rel in files + other:
                p = os.path.join(root, *rel.split("/"))
                os.makedirs(os.path.dirname(p), exist_ok=True)
                open(p, "w").close()
            scanned = {_rel(p, root) for p in files_to_scan(root)}
        self.assertEqual(scanned, set(files) - {SELF})

    def test_runtime_catches_planted_imports(self):
        files = {"scoring/__init__.py": "", "scoring/p7_results.py": "X = 1\n",
                 "scoring/v4_ok.py": "import json\n", "scoring/v4_bad.py": "from scoring import p7_results\n",
                 "guard/__init__.py": "", "guard/g_v4.py": "from scoring import v4_ok\n"}
        with tempfile.TemporaryDirectory(prefix="v4_no_gold_rt_") as root:
            for rel, text in files.items():
                p = os.path.join(root, *rel.split("/"))
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(text)
            r = run_runtime(root, ["guard"], [], allow=False)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            strict = json.loads(r.stdout.strip().splitlines()[-1])
            r = run_runtime(root, [], ["scoring/v4_*.py"], allow=True)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            extra = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(strict["bad_modules"], ["scoring", "scoring.v4_ok"])     # strict: no scoring module
        self.assertEqual(sorted(extra["modules"]), ["scoring.v4_bad", "scoring.v4_ok"])
        self.assertEqual(extra["bad_modules"], ["scoring.p7_results"])


class TestNoGoldInV4(unittest.TestCase):

    def test_scan_sets_are_not_empty(self):
        rels = {_rel(p) for p in files_to_scan()}
        self.assertIn("guard/tgr_tracker_v3.py", rels)
        self.assertIn("guard/run_online_v4.py", rels)
        self.assertIn("tests/test_v4_v3_untouched.py", rels)
        self.assertIn("scripts/v4_merge_overlays.py", rels)
        self.assertNotIn(SELF, rels)
        self.assertNotIn("scoring/gold_loader.py", rels)

    def test_no_gold_imports(self):
        bad = {}
        for path in files_to_scan():
            if path.endswith(".py"):
                src = _read(path)
                hits = (import_hits(src, allow_scoring=True, package=package_of(path)) if is_extra(path)
                        else import_hits(src))
                if hits:
                    bad[_rel(path)] = hits
        self.assertEqual(bad, {})

    def test_no_gold_paths_in_text(self):
        bad = {}
        for path in files_to_scan():
            if path.endswith(TEXT_EXT):
                hits = text_hits(_read(path))
                if hits:
                    bad[_rel(path)] = hits
        self.assertEqual(bad, {})

    def test_no_gold_path_parts(self):
        bad = {}
        for path in files_to_scan():
            if path.endswith(".py"):
                hits = gold_constants(_read(path))
                if hits:
                    bad[_rel(path)] = hits
        self.assertEqual(bad, {})

    def test_no_gold_module_strings(self):
        bad = {}
        for path in files_to_scan():
            if path.endswith(".py"):
                hits = module_string_hits(_read(path))
                if hits:
                    bad[_rel(path)] = hits
        self.assertEqual(bad, {})

    def test_runtime_strict(self):
        """Importing every module of guard/ and state_tracker/v4/ loads no gold or scoring module, opens no gold
        file."""
        r = run_runtime(PC_DIR, STRICT_DIRS, [], allow=False)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        rep = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertIn("guard.run_online_v4", rep["modules"])
        self.assertEqual(rep["errors"], {})
        self.assertEqual(rep["bad_modules"], [])
        self.assertEqual(rep["bad_open"], [])

    def test_runtime_v4_extra(self):
        """Importing every v4 Python module outside guard/ and state_tracker/v4/ loads no gold module and no scoring
        module other than scoring.v3_* / scoring.v4_*, and opens no gold file."""
        r = run_runtime(PC_DIR, [], [g for g in V4_EXTRA_GLOBS if g.endswith(".py")], allow=True, skip=[SELF])
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        rep = json.loads(r.stdout.strip().splitlines()[-1])
        want = sorted(_rel(p)[:-3].replace("/", ".") for p in extra_files() if p.endswith(".py"))
        self.assertEqual(sorted(rep["modules"]), want)
        self.assertIn("tests.test_v4_v3_untouched", rep["modules"])
        self.assertEqual(rep["errors"], {})
        self.assertEqual(rep["bad_modules"], [])
        self.assertEqual(rep["bad_open"], [])


if __name__ == "__main__":
    unittest.main()
