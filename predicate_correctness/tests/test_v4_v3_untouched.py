"""Tracker v4: the v3 and eval v2 files are untouched (docs/planning/tracker_v4/code_change_map.md sections 0.1 and 2).

Checks, all read only (file bytes and file times; no conversation is opened, no LLM call, no network):
  1. every file of output/eval_v3/v3_freeze.md has its recorded sha256, and v3_freeze.md itself has the sha256 that
     docs/planning/tracker_v3/overview.md records. Three files were changed once after that freeze, for B3, and
     that change is recorded in the v3 overview ("p14 B3 build" rows): for them the file has the B3-build sha256
     and its saved copy <file>.pre_b3 still has the freeze sha256. The other B3-build files have their recorded sha;
  1b. every v3 file (state_tracker/v3/, guard/*_v3.py, scoring/v3_*.py, the *.pre_b3 backups, v3 tests and audits,
     tests/test_no_gold_import.py, the rule tables) has the sha256 pinned in V3_PINNED (its on-disk sha at the v4
     start, with the record it comes from), and no v3 file exists that is not pinned;
  2. guard/tgr_tracker_v3.check_frozen_v3() passes (the v3 guard's own input table);
  3. state_tracker/v3/frozen.check_manifest() passes (the eval v2 data manifest, 807 files);
  4. no file under output/eval_v3/ or output/eval_v2/, and no v3 code or test file, was changed after the v4 build
     started (V4_START, the user's approval of the v4 plan; file modification times). Not checked: the three scratch
     folders the v3 tests rewrite on every run (V3_TEST_SCRATCH: test_v3_run_online, test_v3_p12, test_v3_p14_report),
     so this check does not fail just because the v3 tests ran first in the same parallel run;
  5. planted checks: a changed byte, a missing file and a wrong pre_b3 copy are each caught.

Run from predicate_correctness/ with the runner Python (check 2 imports the v3 guard):
    ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v4_v3_untouched -v
"""
from __future__ import annotations

import datetime
import glob
import hashlib
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

FREEZE_MD = "output/eval_v3/v3_freeze.md"
# docs/planning/tracker_v3/overview.md, row "p12 `output/eval_v3/v3_freeze.md` (the v3 freeze)".
FREEZE_MD_SHA256 = "06eed629bd3b5544755d12fe5afe849050705ba58ca86f0da3892f80f86ee55f"
N_FREEZE_FILES = 19
# docs/planning/tracker_v3/overview.md, rows "p14 B3 build ...": the 3 freeze files changed for B3 (their pre-B3
# bytes are kept as <file>.pre_b3), and the other files of the B3 build.
B3_PATCHED = {
    "guard/run_online_v3.py": "0daab01d99c47203f3c5fb1bc7ab24afa1c0ae97f58c7c82ec9a7bc876b60cd7",
    "scoring/v3_online_metrics.py": "daafa873bd8c1a018309cd6ad74ad1bda72ac1981a209cfb54e225c8d1f7da7e",
    "scoring/v3_online_interim.py": "a95d098931536d95b0fb8fb5149d3e88ad12be3c7e303d8f535e46f17b07fa21",
}
B3_BUILD_OTHER = {
    "tests/test_v3_b3.py": "e9bcec2c38be2125d1ab20d7f83efe29c8dba04ab99dcd8770e0e3ecbd285293",
    "output/eval_v3/b3_tasks.json": "0394a99ad08d3c832419f63333bc22b78096b993af5fb39c36c20a47917b33ff",
}
PRE_B3 = ".pre_b3"
# Every v3 file (UNCHANGED_GLOBS below, the v3 freeze files, the rule tables and b3_tasks.json) with its sha256 ON DISK
# at the v4 build start and where that sha is recorded. A change from now on, a missing file or a new v3 file fails.
V3_PINNED = {
    "fork/offline_v3.py": ("7d2eec758bd08be6519a32839638a57bd5b78397dcb4b50fd3f27c35c1120e79",
        "tracker_v3/overview.md sha table"),
    "guard/direct_facts_v3.py": ("3913e60019d098e7dfd9b675c50f18f7938a46be415f7f25c824bc0d0c0f704b",
        "v3_freeze.md"),
    "guard/feedback_v3.py": ("d7c7085eaeb413e7f373e8a4eb5df112b5a191d80ef975174889316d21870f5d",
        "tracker_v3/overview.md sha table"),
    "guard/run_online_v3.py": ("0daab01d99c47203f3c5fb1bc7ab24afa1c0ae97f58c7c82ec9a7bc876b60cd7",
        "tracker_v3/preregistration_online.md change log 2026-10-23 19:08 (B3 build)"),
    "guard/run_online_v3.py.pre_b3": ("45ee28bd8f19c46a302568c835f6f96c6e3b8f0b9746210f4217a8e62eef5fe1",
        "v3_freeze.md (sha of guard/run_online_v3.py at the freeze; B3 backup)"),
    "guard/soft_stop_v3.py": ("f83a04b44c5636af389d28d67169e446566f2800ff25ecd19043bc57d3b9a391",
        "v3_freeze.md"),
    "guard/tgr_tracker_v3.py": ("3afdc3a5c0ab33d63bce874a6b171672f0f47718994bc719c2377ef3b434f377",
        "v3_freeze.md"),
    "output/eval_v3/b3_tasks.json": ("0394a99ad08d3c832419f63333bc22b78096b993af5fb39c36c20a47917b33ff",
        "tracker_v3/preregistration_online.md change log 2026-10-23 19:08 (B3 build)"),
    "output/eval_v3/online_tasks.json": ("5f7b9b71c727531c29cbe1ab8e7189b4bcf67195bb5b78f02437f98d08baf96e",
        "v3_freeze.md"),
    "output/eval_v3/rule_table_airline.json": ("ea2f654a6b5e7d5f1e99bf76e24c08aef4199e4516e1ce2074e5fc27ddbd0c69",
        "tracker_v3/overview.md sha table"),
    "output/eval_v3/rule_table_retail.json": ("1d288c284351337e2316926d6ca0c68b5980fd5af2a6bdb22215202cb817cd3f",
        "tracker_v3/overview.md sha table"),
    "output/eval_v3/v3_freeze.md": ("06eed629bd3b5544755d12fe5afe849050705ba58ca86f0da3892f80f86ee55f",
        "tracker_v3/overview.md sha table"),
    "scoring/v3_audit.py": ("e418902e213b2647a7cda3ad7b5550116242882163c4d9d8e206bcb52838d1d0",
        "tracker_v3/overview.md sha table"),
    "scoring/v3_b1_summary.py": ("a239adcd2f2332f4de26de6c2efd6bb367b03ba1049a4fd98aee8c891a4d47e7",
        "tracker_v3/overview.md sha table"),
    "scoring/v3_harm_metric.py": ("69cf4595874e5fc22948f4619e3db15a08b83100702a7edd4effaa233c148922",
        "tracker_v3/overview.md sha table"),
    "scoring/v3_labels.py": ("060a827a543d4b2be46ff235d806e8b7ecd9793f90c52644636bba49c24964d4",
        "tracker_v3/overview.md sha table"),
    "scoring/v3_message_check.py": ("89a26565d8b8b4568db12cf9861e8e026227dfab7f994148d5360fc8e996a6a6",
        "tracker_v3/overview.md sha table"),
    "scoring/v3_offline_eval.py": ("d9483a7691b1b0c32e4d9902f22a051055006db51a04889cd270daea9b69478b",
        "tracker_v3/overview.md sha table"),
    "scoring/v3_online_interim.py": ("a95d098931536d95b0fb8fb5149d3e88ad12be3c7e303d8f535e46f17b07fa21",
        "tracker_v3/preregistration_online.md change log 2026-10-23 19:08 (B3 build)"),
    "scoring/v3_online_interim.py.pre_b3": ("f30eba6d736a7b1cac4b7a2dee2bd2d76cfc592afdbe225a3a3faf28ba299c84",
        "v3_freeze.md (sha of scoring/v3_online_interim.py at the freeze; B3 backup)"),
    "scoring/v3_online_metrics.py": ("daafa873bd8c1a018309cd6ad74ad1bda72ac1981a209cfb54e225c8d1f7da7e",
        "tracker_v3/preregistration_online.md change log 2026-10-23 19:08 (B3 build)"),
    "scoring/v3_online_metrics.py.pre_b3": ("8f83b1f3934752ba65a333c885d94652f1653ccaf972dac37cd6340d4e81307f",
        "v3_freeze.md (sha of scoring/v3_online_metrics.py at the freeze; B3 backup)"),
    "scoring/v3_p12_holdout_labels.py": ("3b8031c12b0d458b7c72e3632ce720ffc5bd60e4a49931f4d13afd7c28631f5e",
        "on disk at the v4 start (mtime before 21:55 UTC), pinned by A11 at 22:05 UTC"),
    "scoring/v3_p12_offline.py": ("91785624b637a1a8c5e3edcea82a18ae4f59b5d586cf4962d75696410e801875",
        "on disk at the v4 start (mtime before 21:55 UTC), pinned by A11 at 22:05 UTC"),
    "scoring/v3_p12_report.py": ("7f34d947cdae9658f1aa4db3659a36f0b2990ffe931498d37158252b11721628",
        "tracker_v3/overview.md sha table"),
    "scoring/v3_p14_report.py": ("d06280f1cb014248397cd55ad27c540f0932c5bb97bce43a4b4f19b1eccb07a6",
        "tracker_v3/overview.md sha table"),
    "scoring/v3_p1_gate0.py": ("65481afdb781f02852ba601918d29878e1c3fa0e5bde184d6434d3beee90625b",
        "tracker_v3/overview.md sha table"),
    "scoring/v3_p2_rule_table_check.py": ("ada3c1c03c06e4c6c8ca0a3a46d264efcd900e1352bfdd7c913c4c9af5bdefb8",
        "tracker_v3/overview.md sha table"),
    "scoring/v3_p3_labels.py": ("5f6c586f9457e4f3359821f133684d057ef8a8e815cf4941a7da9e588fd4bbbd",
        "tracker_v3/overview.md sha table"),
    "scoring/v3_p6_agreement.py": ("9df0299653d589eb0f0122aefb743f2c36c34a74622ab2c51689fd2e37a0caa3",
        "tracker_v3/overview.md sha table"),
    "scoring/v3_p7_structure.py": ("8930a4d4f752a0168796959caec98f8cbb4d8a79e274f6a66e45f8724536436b",
        "tracker_v3/overview.md sha table"),
    "scoring/v3_p8_dryrun.py": ("aa086928b8d9d1fb0df54b172b765529824f7e8b0842268bb36b9ff05f8cfe96",
        "tracker_v3/overview.md sha table"),
    "scoring/v3_p9_run.py": ("e9f3f458f4a150e12dd7a2cc48574e915f3da59262b18ee5d06ad8fe16ae747c",
        "tracker_v3/overview.md sha table"),
    "state_tracker/v3/__init__.py": ("2c353fcfb3f87d16c5f9e39f4e5561184c197e42e01cde80bf520bdd84e83463",
        "v3_freeze.md"),
    "state_tracker/v3/code_helpers.py": ("53f08edd0675bb3bfc5ca60dcd0c26d3e98f6a903ca2e0203cc3b295789b090d",
        "v3_freeze.md"),
    "state_tracker/v3/facts_format_v3.py": ("c4de3e63502e1ec8532e622f77333deb3faa066891c65c23b6578d75614ce727",
        "v3_freeze.md"),
    "state_tracker/v3/facts_v3_airline.json": ("c49deb8c410247a0dd1b4f5d0a743a5148bf8e899d140595110d7c25f5f16783",
        "v3_freeze.md"),
    "state_tracker/v3/facts_v3_retail.json": ("0122a87da75543f824806612c346edc67d37e63a63464270216d20327a3f3eba",
        "v3_freeze.md"),
    "state_tracker/v3/frozen.py": ("d90e5db71eeba5acfe03717802672659db103ac65a7593a64d969d24bc890315",
        "v3_freeze.md"),
    "state_tracker/v3/info_classes.py": ("ba55362a818d7edbdd4ec2a64ae17461f9dabf5194eebfba1a10c0f72c119ce7",
        "v3_freeze.md"),
    "state_tracker/v3/message_view.py": ("4d302a75b1508403b925b8822b6376cbd447108c85464bbf1b3d24beff0cfad4",
        "v3_freeze.md"),
    "state_tracker/v3/questions.py": ("0d43eb12827237ee147e23d14f6cccb21b191ddcd1c36f104b167a7acd27f4ab",
        "v3_freeze.md"),
    "state_tracker/v3/questions_v3.json": ("892b0ea5ace3084bedb950d9cb28300b5bae3ae6116b597c66456f45e4391ed0",
        "v3_freeze.md"),
    "state_tracker/v3/rule_table.py": ("6593aa658c42641591d0f1b90ca90bc285ac1caae4a91927d82d9c9f311f77c5",
        "v3_freeze.md"),
    "state_tracker/v3/tool_check.py": ("493591328ad4687acb7361607d555f3f0b00527bec81cd3bd84300be58bbe21f",
        "v3_freeze.md"),
    "tests/audit_v3_b3_recompute.py": ("4fd7a006c6804914eb704df66999e2bf2d7a13f5ab525f92e3d0bc0723248f90",
        "tracker_v3/overview.md sha table"),
    "tests/audit_v3_online_recompute.py": ("cac47600730c13962b335380fc634dcdc22c17f7597ec642df5da881f02f48a3",
        "tracker_v3/overview.md sha table"),
    "tests/audit_v3_ref_counts.py": ("05f6a33a4c8802890da4ca78e49bfa8dcb4b62dc9fc3b632e343885916219682",
        "tracker_v3/overview.md sha table"),
    "tests/test_no_gold_import.py": ("b219333693d93ce21d1f6da50ac91d6e0ffb19524f7834b606d58431f306d1ed",
        "tracker_v3/overview.md sha table"),
    "tests/test_v3_audit.py": ("c9d185fb2dded7e6ee01ff249b8e1189092522cc5bf713192d96c7bfc09b2e62",
        "tracker_v3/overview.md sha table"),
    "tests/test_v3_b3.py": ("e9bcec2c38be2125d1ab20d7f83efe29c8dba04ab99dcd8770e0e3ecbd285293",
        "tracker_v3/preregistration_online.md change log 2026-10-23 19:08 (B3 build)"),
    "tests/test_v3_classify.py": ("0f9587a5a34e6dc445719fd3f9977248f4881aa83fe731c7271eb4b2475c7d90",
        "tracker_v3/overview.md sha table"),
    "tests/test_v3_code_facts.py": ("dd93962302941e8f3a38a0352eaf8a8de36606c7362c5fad004030a88b147aec",
        "tracker_v3/overview.md sha table"),
    "tests/test_v3_direct_facts.py": ("0a7ae7aab55fc4816cbca0572cb0f4a6bdaa23e88c1955f433cbfe4ccefd7355",
        "tracker_v3/overview.md sha table"),
    "tests/test_v3_facts_format.py": ("d8375dedc80fa594d7dba45198bda312066390fa31ae465270ae66a6ad29a908",
        "tracker_v3/overview.md sha table"),
    "tests/test_v3_feedback.py": ("bcdb91ace1f4cdd4dbab28e831fd4025800e15865da2226462e95dfc663a439f",
        "tracker_v3/overview.md sha table"),
    "tests/test_v3_frozen.py": ("5f26713d4036075253ad82852492a36ccb0d37ceb119ec314c2d551dff4c89dd",
        "tracker_v3/overview.md sha table"),
    "tests/test_v3_guard.py": ("0d842cd8ce9680418805c4350001e03c3a4835c99b8055217dc1bb6595e0ae66",
        "tracker_v3/overview.md sha table"),
    "tests/test_v3_message_view.py": ("352a66cb95f8346bad6223896d60bf822e0b871995d4323be0bcdcd555387dc1",
        "tracker_v3/overview.md sha table"),
    "tests/test_v3_offline.py": ("ce94a263eb37bd40d91e155084f9ff0d39496607e75381a8760a505e59e78d75",
        "tracker_v3/overview.md sha table"),
    "tests/test_v3_online_metrics.py": ("e485ef158c2ae3cf2cb2ac1497c80877fd2ac27dffe31248ac834e5c412d683e",
        "tracker_v3/overview.md sha table"),
    "tests/test_v3_p12.py": ("b429a9008b8a8a98dd126ce70355e7cec242720cc5950de173ee5c5707dab649",
        "on disk at the v4 start (mtime before 21:55 UTC), pinned by A11 at 22:05 UTC"),
    "tests/test_v3_p14_report.py": ("2723ff2db6c025a947fbb2e0860ede4bf10b9e472797ee729daec425531231c8",
        "tracker_v3/overview.md sha table"),
    "tests/test_v3_questions.py": ("6a89a44e25c611ef905d80a60298354a41186726ac2915d3d884a19b6eb9b51c",
        "tracker_v3/overview.md sha table"),
    "tests/test_v3_rule_table.py": ("cad21e87fd901ae3413b2d9771ac468b41a6b4857ae314709265395dab0fed6d",
        "tracker_v3/overview.md sha table"),
    "tests/test_v3_run_online.py": ("2c49deba444a8a3d38c98a275b37a84ab962bb9d14bb1f51e8a48a47cd0d12d3",
        "tracker_v3/overview.md sha table"),
    "tests/test_v3_soft_stop.py": ("5e917ebd1b1a7bbba3199c5696152d7d4d77808af0b1e20eef936165454f8d1d",
        "tracker_v3/overview.md sha table"),
    "tests/test_v3_structure_facts.py": ("5eae5c8e7497da3b7431c51dbee0eb0b6c2fd16d1d4b4ac009019a74ee325244",
        "tracker_v3/overview.md sha table"),
    "tests/test_v3_tool_check.py": ("bed838aba965cf60ee1bcf447f31dc217dbb07c678ee3f8f0b27eadf89173b13",
        "tracker_v3/overview.md sha table"),
}
# The user approved the v4 plan at about 21:55 UTC (docs/planning/tracker_v4/progress.md); the last v3 write
# (output/eval_v3/progress.md) was at 20:57 UTC.
V4_START = datetime.datetime(2026, 10, 23, 21, 55, 0, tzinfo=datetime.timezone.utc).timestamp()
UNCHANGED_TREES = ("output/eval_v3", "output/eval_v2")
UNCHANGED_GLOBS = ("state_tracker/v3/*", "guard/*_v3.py", "guard/*.pre_b3", "scoring/v3_*.py", "scoring/v3_*.pre_b3",
                   "fork/offline_v3.py", "tests/test_v3_*.py", "tests/audit_v3_*.py", "tests/test_no_gold_import.py")
# Folders the v3 tests themselves rewrite on every run (fake runs, no LLM call); left out of the file-time check only.
V3_TEST_SCRATCH = ("output/eval_v3/dryrun/equality_check_test",   # tests/test_v3_run_online.py TestEqualityCheck
                   "output/eval_v3/dryrun/p12tool/test",          # tests/test_v3_p12.py TEST_DIR
                   "output/eval_v3/dryrun/p14report")             # tests/test_v3_p14_report.py OUT

_ROW = re.compile(r"^\| `([^`]+)` \| `([0-9a-f]{64})` \|\s*$")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_freeze_table(path: str) -> dict:
    """{relpath: sha256} from the table rows of v3_freeze.md."""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = _ROW.match(line.rstrip("\n"))
            if m:
                out[m.group(1)] = m.group(2)
    return out


def freeze_problems(table: dict, root: str = PC_DIR, patched: dict = B3_PATCHED) -> list:
    """Problems of the freeze table against the files under root (empty: fine)."""
    bad = []
    for rel, want in sorted(table.items()):
        p = os.path.join(root, *rel.split("/"))
        if not os.path.isfile(p):
            bad.append(f"{rel}: missing")
            continue
        got = sha256_file(p)
        if rel in patched:
            if got != patched[rel]:
                bad.append(f"{rel}: sha256 {got} is neither the B3-build sha {patched[rel]}")
            pre = p + PRE_B3
            if not os.path.isfile(pre):
                bad.append(f"{rel}{PRE_B3}: missing (the freeze-time copy)")
            elif sha256_file(pre) != want:
                bad.append(f"{rel}{PRE_B3}: sha256 {sha256_file(pre)} != freeze {want}")
        elif got != want:
            bad.append(f"{rel}: sha256 {got} != freeze {want}")
    return bad


def changed_after(paths, since: float) -> list:
    return sorted(p for p in paths if os.path.getmtime(p) > since)


def unchanged_files(root: str = PC_DIR) -> list:
    out = set()
    for tree in UNCHANGED_TREES:
        for dirpath, dirnames, filenames in os.walk(os.path.join(root, *tree.split("/"))):
            out |= {os.path.join(dirpath, f) for f in filenames}
    for g in UNCHANGED_GLOBS:
        out |= {p for p in glob.glob(os.path.join(root, *g.split("/"))) if os.path.isfile(p)}
    return sorted(p for p in out if "__pycache__" not in p)


def in_v3_test_scratch(path: str, root: str = PC_DIR) -> bool:
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    return any(rel == d or rel.startswith(d + "/") for d in V3_TEST_SCRATCH)


class TestFreezeTable(unittest.TestCase):

    def test_freeze_md_itself(self):
        self.assertEqual(sha256_file(os.path.join(PC_DIR, *FREEZE_MD.split("/"))), FREEZE_MD_SHA256)

    def test_table_has_19_files(self):
        t = read_freeze_table(os.path.join(PC_DIR, *FREEZE_MD.split("/")))
        self.assertEqual(len(t), N_FREEZE_FILES, sorted(t))
        self.assertTrue(set(B3_PATCHED) <= set(t))

    def test_every_freeze_file_matches(self):
        t = read_freeze_table(os.path.join(PC_DIR, *FREEZE_MD.split("/")))
        self.assertEqual(freeze_problems(t), [])

    def test_b3_build_files(self):
        bad = {rel: sha256_file(os.path.join(PC_DIR, *rel.split("/")))
               for rel in B3_BUILD_OTHER
               if sha256_file(os.path.join(PC_DIR, *rel.split("/"))) != B3_BUILD_OTHER[rel]}
        self.assertEqual(bad, {})


class TestPinnedV3Files(unittest.TestCase):

    def test_every_pinned_file_matches(self):
        bad = {}
        for rel, (want, _src) in sorted(V3_PINNED.items()):
            p = os.path.join(PC_DIR, *rel.split("/"))
            got = sha256_file(p) if os.path.isfile(p) else "missing"
            if got != want:
                bad[rel] = got
        self.assertEqual(bad, {})

    def test_no_unpinned_v3_file(self):
        rels = set()
        for g in UNCHANGED_GLOBS:
            rels |= {os.path.relpath(p, PC_DIR).replace(os.sep, "/") for p in glob.glob(os.path.join(PC_DIR, *g.split("/")))
                     if os.path.isfile(p) and "__pycache__" not in p}
        self.assertEqual(sorted(rels - set(V3_PINNED)), [])

    def test_pins_agree_with_the_records(self):
        freeze = read_freeze_table(os.path.join(PC_DIR, *FREEZE_MD.split("/")))
        for rel, want in freeze.items():
            pin = V3_PINNED[rel][0]
            self.assertEqual(pin, B3_PATCHED.get(rel, want), rel)
            if rel in B3_PATCHED:
                self.assertEqual(V3_PINNED[rel + PRE_B3][0], want, rel)
        for rel, want in B3_BUILD_OTHER.items():
            self.assertEqual(V3_PINNED[rel][0], want, rel)
        self.assertEqual(V3_PINNED[FREEZE_MD][0], FREEZE_MD_SHA256)
        self.assertTrue(all(src for _, src in V3_PINNED.values()))


class TestV3GuardAndV2Manifest(unittest.TestCase):

    def test_check_frozen_v3(self):
        from guard import tgr_tracker_v3 as V3
        r = V3.check_frozen_v3()
        self.assertEqual(r["unrecorded"], [])
        self.assertEqual(len(r["sha256"]), len(V3.FROZEN_SHA256))

    def test_eval_v2_manifest(self):
        from state_tracker.v3 import frozen
        entries = frozen.check_manifest()
        self.assertGreater(len(entries), 800)
        self.assertEqual(frozen.sha256_file(frozen.MANIFEST_PATH), frozen.MANIFEST_SHA256)


class TestNothingChangedSinceV4Start(unittest.TestCase):

    def test_no_v3_or_v2_file_newer_than_v4_start(self):
        files = [p for p in unchanged_files() if not in_v3_test_scratch(p)]
        self.assertGreater(len(files), 1000)   # eval_v3 (~660) + eval_v2 + code
        self.assertEqual([os.path.relpath(p, PC_DIR) for p in changed_after(files, V4_START)], [])

    def test_scratch_skip_is_narrow(self):
        j = lambda rel: os.path.join(PC_DIR, *rel.split("/"))
        for rel in ("output/eval_v3/dryrun/p14report/a.md", "output/eval_v3/dryrun/p12tool/test/s/x.jsonl",
                    "output/eval_v3/dryrun/equality_check_test/summary.json"):
            self.assertTrue(in_v3_test_scratch(j(rel)), rel)
        for rel in ("output/eval_v3/dryrun/equality_check/summary.json", "output/eval_v3/dryrun/p14report_x/a.md",
                    "output/eval_v3/dryrun/p12tool/questions_answers_copy.jsonl", "output/eval_v3/v3_freeze.md",
                    "guard/tgr_tracker_v3.py"):
            self.assertFalse(in_v3_test_scratch(j(rel)), rel)

    def test_globs_cover_the_v3_code(self):
        rels = {os.path.relpath(p, PC_DIR).replace(os.sep, "/") for p in unchanged_files()}
        for rel in ("state_tracker/v3/questions.py", "guard/tgr_tracker_v3.py", "guard/run_online_v3.py.pre_b3",
                    "scoring/v3_online_metrics.py", "tests/test_v3_questions.py", "tests/test_no_gold_import.py",
                    "fork/offline_v3.py", "output/eval_v3/v3_freeze.md"):
            self.assertIn(rel, rels)


class TestDetectorsCatchPlantedChanges(unittest.TestCase):
    """The checks above must fail on a planted change, so a pass means something."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="v4_untouched_")
        self.table = {"a/x.py": None, "guard/run_online_v3.py": None}
        for rel in self.table:
            p = os.path.join(self.root, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(f"frozen {rel}\n")
            self.table[rel] = sha256_file(p)
        p = os.path.join(self.root, "guard", "run_online_v3.py")
        shutil.copy(p, p + PRE_B3)
        with open(p, "a", encoding="utf-8") as f:
            f.write("# b3 build\n")
        self.patched = {"guard/run_online_v3.py": sha256_file(p)}

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_clean_tree_passes(self):
        self.assertEqual(freeze_problems(self.table, self.root, self.patched), [])

    def test_changed_byte(self):
        with open(os.path.join(self.root, "a", "x.py"), "a", encoding="utf-8") as f:
            f.write(" ")
        self.assertEqual(len(freeze_problems(self.table, self.root, self.patched)), 1)

    def test_missing_file(self):
        os.remove(os.path.join(self.root, "a", "x.py"))
        self.assertEqual(freeze_problems(self.table, self.root, self.patched), ["a/x.py: missing"])

    def test_wrong_pre_b3_copy(self):
        with open(os.path.join(self.root, "guard", "run_online_v3.py" + PRE_B3), "a", encoding="utf-8") as f:
            f.write("x")
        self.assertEqual(len(freeze_problems(self.table, self.root, self.patched)), 1)

    def test_patched_file_changed_again(self):
        with open(os.path.join(self.root, "guard", "run_online_v3.py"), "a", encoding="utf-8") as f:
            f.write("x")
        self.assertEqual(len(freeze_problems(self.table, self.root, self.patched)), 1)

    def test_newer_file_is_caught(self):
        p = os.path.join(self.root, "a", "x.py")
        os.utime(p, (V4_START + 60, V4_START + 60))
        self.assertEqual(changed_after([p], V4_START), [p])
        os.utime(p, (V4_START - 60, V4_START - 60))
        self.assertEqual(changed_after([p], V4_START), [])

    def test_table_parser(self):
        p = os.path.join(self.root, "f.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("| file | sha256 |\n|---|---|\n| `a/x.py` | `" + "0" * 64 + "` |\n| not a row |\n")
        self.assertEqual(read_freeze_table(p), {"a/x.py": "0" * 64})


if __name__ == "__main__":
    unittest.main()
