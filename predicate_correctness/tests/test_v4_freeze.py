"""Tests for the v4 freeze manifest (scoring/v4_freeze.py). Made-up files in temporary folders; the real manifest
(output/eval_v4/v4_freeze.json) is never written or read. No LLM, no network.

TestRunnerFiles writes temp manifests with the runner's real files (guard/run_online_v4.py freeze_required_files();
audit P7 #3): --write adds them all, --check and the runner refuse a manifest that leaves one out.

Run from predicate_correctness/:
    /home/azureuser/miniconda3/bin/python3 -B -m unittest tests.test_v4_freeze -v
"""
from __future__ import annotations

import contextlib
import glob
import io
import json
import os
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from scoring import v4_freeze as Z     # noqa: E402

THIS = os.path.abspath(__file__)


def load(path):
    with open(path) as f:
        return json.load(f)


def dump(doc, path):
    with open(path, "w") as f:
        json.dump(doc, f)


def run(argv, runner_files=False):
    """Z.main; made-up files only unless runner_files (then --write adds and --check needs the runner's files)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = Z.main(list(argv) + ([] if runner_files else ["--no-runner-files"]))
    return code, buf.getvalue()


class TestFreeze(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.d = self.tmp.name
        self.files = []
        for i in range(3):
            p = os.path.join(d, f"method_{i}.py")
            with open(p, "w") as f:
                f.write(f"x = {i}\n")
            self.files.append(p)
        self.prereg, self.guide = os.path.join(d, "prereg.md"), os.path.join(d, "guide.md")
        for p in (self.prereg, self.guide):
            with open(p, "w") as f:
                f.write("text\n")
        self.man = os.path.join(d, "out", "v4_freeze.json")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, extra=()):
        return run(["--write", "--files", *self.files, *extra, "--prereg", self.prereg, "--guide", self.guide,
                    "--manifest", self.man])

    def test_write_then_check(self):
        code, out = self.write([THIS])
        self.assertEqual(code, 0, out)
        self.assertIn("6 files (4 method, 1 pre-registration, 1 reading guide)", out)
        with open(self.man) as f:
            doc = json.load(f)
        self.assertEqual(doc["counts"], {"method": 4, "preregistration": 1, "reading_guide": 1, "total": 6,
                                         "bytes": sum(os.path.getsize(p) for p in self.files + [THIS, self.prereg,
                                                                                              self.guide])})
        paths = [e["path"] for e in doc["files"]]
        self.assertIn("predicate_correctness/tests/test_v4_freeze.py", paths)   # stored relative to the repo
        self.assertIn(os.path.abspath(self.files[0]), paths)                     # outside the repo: absolute
        code, out = run(["--check", "--manifest", self.man])
        self.assertEqual(code, 0, out)
        self.assertIn("6 files listed, 6 same, 0 changed, 0 missing, 0 runner files not listed, 0 manifest problems -> OK", out)

    def test_change_and_missing_fail(self):
        self.assertEqual(self.write()[0], 0)
        with open(self.files[1], "a") as f:
            f.write("# changed\n")
        code, out = run(["--check", "--manifest", self.man])
        self.assertEqual(code, 1)
        self.assertIn("CHANGED", out)
        self.assertIn("1 changed, 0 missing", out)
        os.remove(self.guide)
        res = Z.check(self.man)
        self.assertFalse(res["ok"])
        self.assertEqual((len(res["changed"]), len(res["missing"])), (1, 1))

    def test_bad_manifests(self):
        self.assertFalse(Z.check(os.path.join(self.d, "nope.json"))["ok"])
        self.assertEqual(self.write()[0], 0)
        with open(self.man) as f:
            doc = json.load(f)
        doc["counts"]["method"] = 99                                   # a hand-typed count
        with open(self.man, "w") as f:
            json.dump(doc, f)
        res = Z.check(self.man)
        self.assertFalse(res["ok"])
        self.assertTrue(any("counts" in p for p in res["problems"]))
        doc = load(self.man)
        doc["files"].append(dict(doc["files"][0]))                    # a duplicate path
        doc["counts"] = Z.counts_of(doc["files"])
        dump(doc, self.man)
        self.assertTrue(any("twice" in p for p in Z.check(self.man)["problems"]))
        with open(self.man, "w") as f:
            f.write("{not json")
        self.assertFalse(Z.check(self.man)["ok"])

    def test_write_refusals(self):
        self.assertEqual(self.write()[0], 0)
        with self.assertRaises(SystemExit):                            # written once
            self.write()
        code, out = run(["--write", "--files", *self.files, "--prereg", self.prereg, "--guide", self.guide,
                         "--manifest", self.man, "--replace"])
        self.assertEqual(code, 0)
        self.assertEqual(len(glob.glob(self.man + ".superseded_*")), 1)  # the old one is copied, never moved
        self.assertIn("old manifest copied", out)
        other = os.path.join(self.d, "m2.json")
        for argv in (["--files", os.path.join(self.d, "missing.py")],      # a missing file
                     ["--files", self.d],                                  # a folder
                     ["--files", self.files[0], self.files[0]],            # a file given twice
                     ["--files", self.prereg],                             # the pre-registration again
                     ["--files"]):                                         # no method file
            with self.assertRaises(SystemExit):
                run(["--write", *argv, "--prereg", self.prereg, "--guide", self.guide, "--manifest", other])
        self.assertFalse(os.path.exists(other))
        with self.assertRaises(SystemExit):                            # --prereg and --guide are needed
            run(["--write", "--files", self.files[0], "--manifest", other])
        self.assertTrue(Z._forbidden(os.path.join(Z.HOME, "venvs", "x.json")))
        self.assertTrue(Z._forbidden(os.path.join(Z.HOME, "ShieldAgent", "x.json")))
        self.assertTrue(Z._forbidden(os.path.join(Z.HOME, "opt", "a", "b.json")))
        self.assertFalse(Z._forbidden(Z.DEFAULT_MANIFEST))

    def test_files_from_list(self):
        lst = os.path.join(self.d, "list.txt")
        with open(lst, "w") as f:
            f.write("# v4 method files\n\n" + "\n".join(self.files[:2]) + "\n")
        code, out = run(["--write", "--files-from", lst, "--files", self.files[2], "--prereg", self.prereg,
                         "--guide", self.guide, "--manifest", self.man])
        self.assertEqual(code, 0, out)
        self.assertEqual(load(self.man)["counts"]["method"], 3)

    def test_default_manifest_path(self):
        self.assertEqual(Z.DEFAULT_MANIFEST, os.path.join(PC_DIR, "output", "eval_v4", "v4_freeze.json"))


class TestRunnerFiles(unittest.TestCase):
    """audit P7 #3: every file the v4 runner needs is written into the manifest and checked."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.prereg, self.guide = os.path.join(d, "prereg.md"), os.path.join(d, "guide.md")
        for p in (self.prereg, self.guide):
            with open(p, "w") as f:
                f.write("text\n")
        self.man = os.path.join(d, "out", "v4_freeze.json")
        from guard import run_online_v4 as R
        self.R = R

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_adds_every_runner_file_and_the_runner_accepts_it(self):
        own = os.path.join(PC_DIR, "guard", "run_online_v4.py")              # given by hand too: added once
        code, out = run(["--write", "--files", own, "--prereg", self.prereg, "--guide", self.guide,
                         "--manifest", self.man], runner_files=True)
        self.assertEqual(code, 0, out)
        doc = load(self.man)
        paths = {e["path"] for e in doc["files"]}
        want = {"predicate_correctness/" + rel for rel in self.R.freeze_required_files()}
        self.assertTrue(want <= paths, sorted(want - paths)[:5])
        for rel in ("guard/run_online_v4.py", "guard/soft_stop_v4.py", "state_tracker/v4/questions_v4.json",
                    "state_tracker/v4/facts_v4_retail.json", "state_tracker/v4/facts_v4_airline.json",
                    # audit P9 #4: the B1 gate's summary, the metrics, the diagnosis, the halfway check and watcher
                    "scoring/v4_b1_summary.py", "scoring/v4_online_metrics.py", "scoring/v4_diagnosis.py",
                    "scoring/v4_online_interim.py", "scoring/v4_interim.sh"):
            self.assertIn("predicate_correctness/" + rel, paths)
        self.assertEqual(len(paths), len(doc["files"]))                         # no path twice
        res = Z.check(self.man, Z.runner_required_files())
        self.assertTrue(res["ok"], res["unlisted"][:5])
        self.assertEqual(res["unlisted"], [])
        code, out = run(["--check", "--manifest", self.man], runner_files=True)
        self.assertEqual(code, 0, out)
        self.assertIn("0 runner files not listed", out)
        self.assertTrue(self.R.freeze_coverage(self.man)["ok"])
        got = self.R.freeze_check(require=True, manifest=self.man)          # the runner's check, the real script
        self.assertTrue(got["ok"], got["detail"])
        self.assertEqual(got["manifest_sha256"], Z.sha256_file(self.man))

    def test_a_manifest_without_a_runner_file_is_refused(self):
        code, out = run(["--write", "--prereg", self.prereg, "--guide", self.guide, "--manifest", self.man],
                        runner_files=True)                                    # only the runner's files: enough
        self.assertEqual(code, 0, out)
        doc = load(self.man)
        drop = "predicate_correctness/guard/soft_stop_v4.py"
        doc["files"] = [e for e in doc["files"] if e["path"] != drop]
        doc["counts"] = Z.counts_of(doc["files"])
        dump(doc, self.man)
        self.assertTrue(Z.check(self.man)["ok"])                               # holds together by itself ...
        res = Z.check(self.man, Z.runner_required_files())
        self.assertFalse(res["ok"])                                            # ... but leaves a runner file out
        self.assertEqual(res["unlisted"], [drop])
        code, out = run(["--check", "--manifest", self.man], runner_files=True)
        self.assertEqual(code, 1)
        self.assertIn("NOT LISTED (the runner needs it): " + drop, out)
        self.assertFalse(self.R.freeze_coverage(self.man)["ok"])
        with self.assertRaises(self.R.RunRefused) as cm:
            self.R.freeze_check(require=True, manifest=self.man)
        self.assertIn("guard/soft_stop_v4.py", str(cm.exception))

    def test_p9_scoring_files_required_and_docstring_names(self):
        """audit P9 #4: the scoring files the gate, the metrics and the halfway stop use are frozen too; the usage text
        names the real pre-registration and reading guide files (preregistration_v4.md, reading_guide_v4.md)."""
        req = {os.path.relpath(p, PC_DIR).replace(os.sep, "/") for p in Z.runner_required_files()}
        for rel in ("scoring/v4_b1_summary.py", "scoring/v4_online_metrics.py", "scoring/v4_diagnosis.py",
                    "scoring/v4_online_interim.py", "scoring/v4_interim.sh"):
            self.assertIn(rel, req)
            self.assertIn(rel, self.R.FREEZE_REQUIRED_EXTRA)
            self.assertTrue(os.path.isfile(os.path.join(PC_DIR, *rel.split("/"))), rel)
        doc = Z.__doc__
        self.assertIn("tracker_v4/preregistration_v4.md", doc)
        self.assertIn("tracker_v4/reading_guide_v4.md", doc)
        self.assertNotIn("tracker_v4/preregistration.md", doc)
        self.assertNotIn("tracker_v4/reading_guide.md", doc)
        docs_dir = os.path.join(os.path.dirname(PC_DIR), "docs", "planning", "tracker_v4")
        for name in ("preregistration_v4.md", "reading_guide_v4.md"):
            self.assertTrue(os.path.isfile(os.path.join(docs_dir, name)), name)


if __name__ == "__main__":
    unittest.main()
