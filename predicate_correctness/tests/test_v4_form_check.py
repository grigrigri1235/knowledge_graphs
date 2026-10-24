"""Tracker v4: the form check reads the v1 DATABASE and wiki only (scoring/v4_form_check.py).

Purity (docs/planning/tracker_v4/overview.md section 3): the form check must never read a task file, a user
instruction, an expected action, a split file or a conversation. Three checks:
  1. a source scan: no task-file name, no task-field access, no split / partner path, no dynamic import or listing;
  2. the reader refuses every path that is not envs/<domain>/data/<name>.json or envs/<domain>/wiki.md;
  3. a full run with every open() recorded: only the DB json files, the two wiki.md files and the two outputs.
No LLM call, no network.

Run from predicate_correctness/:  ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v4_form_check
"""
from __future__ import annotations

import builtins
import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "scoring", "v4_form_check.py")


def _load():
    spec = importlib.util.spec_from_file_location("v4_form_check_under_test", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FORBIDDEN = [
    r"tasks_", r"tasks\.py", r"\btasks\b\s*[\[=(]", r"[\"']instruction[\"']", r"[\"']actions[\"']",
    r"[\"']outputs[\"']", r"splits", r"from_shieldagent", r"third_party", r"banking", r"\bdev20\b",
    r"\bimport ast\b", r"\bast\.", r"sys\.path", r"importlib", r"__import__", r"\bglob\b", r"listdir", r"os\.walk",
    r"scandir", r"\bexec\(", r"\beval\(", r"trajector", r"conversation[s]?\.json", r"eval_v[23]/",
]


class FormCheckPurity(unittest.TestCase):
    def test_source_has_no_task_access(self):
        with open(SRC) as f:
            src = f.read()
        for pat in FORBIDDEN:
            self.assertIsNone(re.search(pat, src), f"forbidden pattern {pat!r} in scoring/v4_form_check.py")
        # exactly one reader open() plus the two output writes
        self.assertEqual(len(re.findall(r"\bopen\(", src)), 3)

    def test_reader_refuses_other_paths(self):
        m = _load()
        for rel in ("retail/tasks_train.py", "retail/tasks_test.py", "retail/tasks_dev.py", "airline/tasks_test.py",
                    "airline/tasks.py", "retail/data/../tasks_train.py", "retail/data/tasks.json", "../x/data/a.json",
                    "banking/data/users.json", "retail/rules.py", "retail/wiki.py"):
            if rel == "retail/data/tasks.json":
                with self.assertRaises(PermissionError):
                    m.load("retail", "tasks")
                continue
            with self.assertRaises(PermissionError, msg=rel):
                m._read(rel)

    def test_run_opens_only_db_and_wiki(self):
        m = _load()
        opened = []
        real_open = builtins.open

        def rec(path, *a, **k):
            opened.append(os.path.realpath(os.fspath(path)))
            return real_open(path, *a, **k)

        with tempfile.TemporaryDirectory() as tmp:
            m.OUT_DIR, m.OUT_MD, m.OUT_JSON = tmp, os.path.join(tmp, "f.md"), os.path.join(tmp, "f.json")
            with mock.patch("builtins.open", rec), mock.patch("builtins.print"):
                m.main()
            allowed_out = {os.path.realpath(m.OUT_MD), os.path.realpath(m.OUT_JSON)}
            for p in opened:
                if p in allowed_out:
                    continue
                rel = os.path.relpath(p, m.TB)
                self.assertRegex(rel, r"^(retail|airline)/(data/[a-z_]+\.json|wiki\.md)$", p)
            with real_open(m.OUT_JSON) as f:
                data = json.load(f)
            with real_open(m.OUT_MD) as f:
                md = f.read()
        self.assertEqual(sorted(data["inputs_sha256"]), sorted(
            [f"{d}/data/{n}.json" for d, ns in m.DB_FILES.items() for n in ns] + ["retail/wiki.md", "airline/wiki.md"]))
        self.assertIn("## Decisions, DB-only", md)
        self.assertNotIn("simulator:", md)
        for x in data["decisions"]:
            self.assertIn(x["basis_kind"], {"DB", "DB + generic", "generic + DB", "DB + wiki", "wiki",
                                            "wiki + generic", "generic", "comment"}, x["id"])
            self.assertTrue(x["basis"].strip(), x["id"])
        # the DB facts the v4 code relies on (form_check.md P3 / P5 / A1 / R4)
        self.assertEqual(data["retail_cards_id_ends_in_last_four"], 0)
        self.assertEqual(data["airline_cards_id_ends_in_last_four"], 0)
        self.assertEqual([e["user"] for e in data["retail_cross_clash_examples"]], ["mei_johansson_1199"])
        self.assertEqual(data["retail_non_usa"], 0)
        self.assertEqual(data["retail_orders_two_same_product"], 91)


if __name__ == "__main__":
    unittest.main()
