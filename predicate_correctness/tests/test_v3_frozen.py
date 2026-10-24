"""Tracker v3, part 1: the eval v2 sha256 manifest (state_tracker/v3/frozen.py).

  - the real manifest passes check_manifest(), is in sha256sum format, and lists what p1.md step 1 asks for;
  - no listed saved run file holds a task of the partner's test group (from_shieldagent/splits/splits.json);
  - on a temporary copy (never the real files): a changed byte, a missing file, a new file in a closed folder, a
    missing manifest, a changed manifest and a bad manifest line are each detected.

Run from predicate_correctness/:  python3 -B -m unittest tests.test_v3_frozen -v
Standard library only.
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import io
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.dont_write_bytecode = True

from state_tracker.v3 import frozen as F  # noqa: E402

STDLIB = set(sys.stdlib_module_names)


class TestRealManifest(unittest.TestCase):

    def test_check_passes_on_real_files(self):
        t0 = time.time()
        got = F.check_manifest()
        seconds = time.time() - t0
        self.assertEqual(got, F.read_manifest())
        self.assertGreater(len(got), 700)
        print(f"\n  check_manifest: {len(got)} files in {seconds:.2f} s", file=sys.stderr)

    def test_manifest_is_pinned_and_sha256sum_format(self):
        self.assertTrue(os.path.isfile(F.MANIFEST_PATH))
        self.assertEqual(F.sha256_file(F.MANIFEST_PATH), F.MANIFEST_SHA256)
        with open(F.MANIFEST_PATH, encoding="utf-8") as f:
            lines = f.read().splitlines()
        rels = []
        for line in lines:
            digest, rel = line.split("  ", 1)
            self.assertEqual(len(digest), 64)
            int(digest, 16)
            self.assertFalse(rel.startswith("/"))
            self.assertTrue(os.path.isfile(os.path.join(F.PC_DIR, rel)), rel)
            rels.append(rel)
        self.assertEqual(rels, sorted(rels))
        self.assertEqual(len(rels), len(set(rels)))

    def test_manifest_lists_what_p1_asks_for(self):
        entries = F.read_manifest()
        for rel in F.METHOD_FILES + (F.SPLITS_REL,):
            self.assertIn(rel, entries)
        for folder in F.CLOSED_FOLDERS:
            files = F._walk_files(folder, F.PC_DIR)
            self.assertTrue(files, folder)
            self.assertEqual([r for r in files if r not in entries], [], folder)
        groups = {F.group_of(r) for r in entries}
        self.assertEqual(groups, {"eval_v2", "online_p10", "sa_runs", "splits", "method"})
        self.assertTrue(any(r.startswith("from_shieldagent/rules/") for r in entries))
        self.assertTrue(any(r.endswith("/tgr/episodes.jsonl") and F.group_of(r) == "sa_runs" for r in entries))

    def test_no_partner_test_group_task_in_listed_runs(self):
        splits = F.load_splits()
        entries = F.read_manifest()
        runs = [r for r in entries if F.group_of(r) == "sa_runs"]
        self.assertTrue(runs)
        for rel in runs:
            groups = F.task_groups(rel, F.PC_DIR, splits)
            self.assertTrue(F.run_file_ok(rel, groups), f"{rel}: {dict(groups)}")
            self.assertNotIn("test", groups, rel)
        for rel in entries:
            if F.group_of(rel) == "online_p10" and rel.endswith(".jsonl"):
                groups = F.task_groups(rel, F.PC_DIR, splits)
                self.assertTrue(set(groups) <= {"train", "val"}, f"{rel}: {dict(groups)}")

    def test_build_is_refused_when_the_manifest_exists(self):
        self.assertTrue(os.path.isfile(F.MANIFEST_PATH))
        before = F.sha256_file(F.MANIFEST_PATH)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = F.main(["--build"])
        self.assertEqual(rc, 2)
        self.assertIn("REFUSED", err.getvalue())
        self.assertEqual(F.sha256_file(F.MANIFEST_PATH), before)

    def test_frozen_module_uses_standard_library_only(self):
        with open(F.__file__, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                roots.add((node.module or "").split(".")[0])
        self.assertEqual(roots - STDLIB, set())


class TestOnTemporaryCopy(unittest.TestCase):
    """A small copy of real listed files in a temporary folder; the real files are only read."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="v3_frozen_test_")
        self.root = self._tmp.name
        real = F.read_manifest()
        self.rels = sorted(r for r in real if F.group_of(r) in ("method", "splits"))
        self.assertTrue(self.rels)
        for rel in self.rels:
            dst = os.path.join(self.root, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(F.PC_DIR, rel), dst)
        self.manifest = os.path.join(self.root, "manifest.sha256")
        self.entries = {r: real[r] for r in self.rels}
        F.write_manifest(self.entries, self.manifest)

    def tearDown(self):
        self._tmp.cleanup()

    def _path(self, rel: str) -> str:
        p = os.path.join(self.root, rel)
        self.assertTrue(os.path.realpath(p).startswith(os.path.realpath(self.root) + os.sep))
        return p

    def check(self, **kw):
        return F.check_manifest(manifest_path=self.manifest, root=self.root, **kw)

    def test_copy_passes(self):
        self.assertEqual(self.check(), self.entries)

    def test_changed_byte(self):
        rel = "from_shieldagent/rules/retail/rule_set.json"
        p = self._path(rel)
        with open(p, "r+b") as f:
            f.seek(100)
            b = f.read(1)
            f.seek(100)
            f.write(bytes([b[0] ^ 1]))
        with self.assertRaises(F.ManifestChanged) as cm:
            self.check()
        self.assertEqual(cm.exception.changed, [rel])
        self.assertEqual(cm.exception.missing, [])
        self.assertIn(rel, str(cm.exception))

    def test_missing_file(self):
        rel = "guard/tgr_tracker.py"
        os.remove(self._path(rel))
        with self.assertRaises(F.ManifestChanged) as cm:
            self.check()
        self.assertEqual(cm.exception.missing, [rel])
        self.assertEqual(cm.exception.changed, [])
        self.assertIn(rel, str(cm.exception))

    def test_new_file_in_closed_folder(self):
        rel = "from_shieldagent/rules/airline/extra.json"
        with open(self._path(rel), "w", encoding="utf-8") as f:
            f.write("{}")
        with self.assertRaises(F.ManifestChanged) as cm:
            self.check()
        self.assertEqual(cm.exception.added, [rel])

    def test_missing_manifest(self):
        os.remove(self.manifest)
        with self.assertRaises(F.ManifestMissing):
            self.check()

    def test_manifest_itself_changed(self):
        good = F.sha256_file(self.manifest)
        self.assertEqual(self.check(expected_sha256=good), self.entries)
        with self.assertRaises(F.ManifestChanged):
            self.check(expected_sha256=hashlib.sha256(b"other").hexdigest())

    def test_bad_manifest_line(self):
        with open(self.manifest, "a", encoding="utf-8") as f:
            f.write("not a line\n")
        with self.assertRaises(F.ManifestChanged):
            self.check()

    def test_unsorted_manifest(self):
        with open(self.manifest, encoding="utf-8") as f:
            lines = f.read().splitlines()
        with open(self.manifest, "w", encoding="utf-8") as f:
            f.write("\n".join(reversed(lines)) + "\n")
        with self.assertRaises(F.ManifestChanged):
            self.check()

    def test_write_manifest_refuses_existing(self):
        with self.assertRaises(FileExistsError):
            F.write_manifest(self.entries, self.manifest)


if __name__ == "__main__":
    unittest.main()
