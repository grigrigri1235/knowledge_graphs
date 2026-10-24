"""Tracker v3 p12 steps 3-5 tooling: tests of scoring/v3_p12_offline.py and scoring/v3_p12_holdout_labels.py.

$0: no LLM call, no network, never a client. The hold-out is NEVER opened here: every hold-out code path runs on a
BUILT conversation (a development conversation of ours.p10_luna_train copied under the hold-out data set name
ours.p10_luna_val, so its keys are hold-out keys), with the real hold-out reader replaced by one that fails the test if
it is called. The tiny answers come from a COPY of the answers store in output/eval_v3/dryrun/p12tool/ (or from
built stores); the real store is never opened here. Test files go to output/eval_v3/dryrun/p12tool/test/.

Run from predicate_correctness/ (the venv Python: the guards need the runner copy):
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v3_p12 -v
"""
from __future__ import annotations

import collections
import copy
import json
import os
import shutil
import subprocess
import sys
import unittest

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from scoring import v3_p12_holdout_labels as HL                  # noqa: E402
from scoring import v3_p12_offline as P                          # noqa: E402

TEST_DIR = os.path.join(PC_DIR, "output", "eval_v3", "dryrun", "p12tool", "test")
STORE_COPY = os.path.join(PC_DIR, "output", "eval_v3", "dryrun", "p12tool", "questions_answers_copy.jsonl")
REAL_STORE = P.STORE


def fresh(name: str) -> str:
    d = os.path.join(TEST_DIR, name)
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d)
    return d


def relock() -> None:
    P._UNLOCKED["holdout"] = False


def no_real_holdout(*_a, **_k):
    raise AssertionError("the real hold-out reader was called in a test")


# ----------------------------------------------------------------------------------------------- the store reader
class TestStoreReader(unittest.TestCase):
    def test_whole_lines_only(self):
        d = fresh("store")
        p = os.path.join(d, "s.jsonl")
        recs = [{"key": "a", "qid": "K1", "status": "yes"}, {"key": "b", "qid": "K2", "status": "no"},
                {"key": "a", "qid": "K1", "status": "no"}]
        with open(p, "w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")
            f.write("not json\n")
            f.write('{"key": "c", "qid": "K3", "sta')             # half written: no newline
        got, info = P.read_store(p)
        self.assertEqual(sorted(got), ["a", "b"])
        self.assertEqual(got["a"]["status"], "yes")             # the first of a key twice is kept
        self.assertEqual((info["partial_last_line"], info["bad_lines"], info["duplicate_keys"]), (1, 1, 1))
        with open(p, "a", encoding="utf-8") as f:
            f.write('tus": "yes"}\n')                           # now finished: read
        got, info = P.read_store(p)
        self.assertIn("c", got)
        self.assertEqual(info["partial_last_line"], 0)

    def test_store_path_is_the_project_store(self):
        from state_tracker.v3 import questions as Q
        self.assertEqual(os.path.abspath(P.STORE), os.path.abspath(Q.ANSWERS_PATH))
        self.assertIn(os.path.abspath(P.STORE), {os.path.abspath(x) for x in P.NEVER_WRITE})


# ----------------------------------------------------------------------------------------------- the hook
class TestStoreOnlyHook(unittest.TestCase):
    def test_saved_answer_is_used_and_missing_is_counted_not_asked(self):
        from state_tracker.v3 import questions as Q
        inputs = Q.sample_inputs("K5")
        probe = Q.Questions(Q.FakeBackend("no"))
        key = probe.key("K5", inputs)
        rec = probe.ask("K5", inputs)                       # a fake answer in memory, made only to have a record
        hook, backend, log = P.make_hook({key: rec})
        self.assertEqual(hook.ask("K5", inputs, fact="f", part="a")["status"], "no")
        self.assertEqual(backend.missing, [])
        other = Q.sample_inputs("K4")
        r = hook.ask("K4", other, fact="g", part="b")
        self.assertEqual(r["status"], "bad_output")
        self.assertEqual([m["qid"] for m in backend.missing], ["K4"])
        with self.assertRaises(Q.F.UseBlockingValue):
            Q.value_of(r)                                   # a missing answer takes the blocking value
        self.assertEqual([x[1] for x in log.take()], ["K5", "K4"])
        self.assertEqual(Q.network_events(), [])
        self.assertFalse(hasattr(backend, "client"))        # never a client


# ----------------------------------------------------------------------------------------------- the lock
class TestLock(unittest.TestCase):
    def tearDown(self):
        relock()

    def test_unlock_needs_both_flags(self):
        for h, lk in ((False, False), (True, False), (False, True)):
            with self.assertRaises(P.HoldoutLocked):
                P.unlock(h, lk)
        self.assertFalse(P._UNLOCKED["holdout"])
        P.unlock(True, True)
        self.assertTrue(P._UNLOCKED["holdout"])

    def test_holdout_readers_refuse_while_locked(self):
        with self.assertRaises(P.HoldoutLocked):
            next(P.select_conversations("holdout"))
        with self.assertRaises(P.HoldoutLocked):
            P.load_holdout_tool_labels(os.path.join(TEST_DIR, "none.jsonl"))
        with self.assertRaises(P.HoldoutLocked):
            P.require_unlocked()

    def test_main_refuses_without_both_flags_and_reads_nothing(self):
        d = fresh("lock_main")
        for argv in (["--holdout"], [P.LOOK_FLAG], ["--holdout", "--phases", "analyse"]):
            self.assertEqual(P.main(argv + ["--out-dir", d]), 2)
            self.assertEqual(os.listdir(d), [])
            self.assertFalse(P._UNLOCKED["holdout"])

    def test_main_refuses_a_second_holdout_run_and_a_limit(self):
        d = fresh("lock_once")
        out = P.outputs("holdout", d)
        open(out["rows"], "w").close()
        self.assertEqual(P.main(["--holdout", P.LOOK_FLAG, "--out-dir", d]), 2)
        relock()
        self.assertEqual(P.main(["--holdout", P.LOOK_FLAG, "--limit", "3", "--out-dir", fresh("lock_limit")]), 2)

    def test_output_paths(self):
        dev, ho = P.outputs("dev"), P.outputs("holdout")
        self.assertFalse(set(dev.values()) & set(ho.values()))
        never = {os.path.abspath(x) for x in P.NEVER_WRITE}
        self.assertFalse((set(dev.values()) | set(ho.values())) & never)
        for p in list(dev.values()) + list(ho.values()):
            self.assertNotIn("p11_", os.path.basename(p))
        self.assertTrue(all("holdout" in os.path.basename(p) for p in ho.values()))

    def test_labels_script_lock(self):
        d = fresh("lock_labels")
        out, rep = os.path.join(d, "l.jsonl"), os.path.join(d, "r.md")
        for argv in ([], ["--holdout"], [HL.LOOK_FLAG]):
            self.assertEqual(HL.main(argv + ["--out", out, "--report", rep], jobs_fn=no_real_holdout), 2)
        self.assertEqual(os.listdir(d), [])
        for dev in HL.DEV_FILES:
            with self.assertRaises(HL.HoldoutLocked):
                HL.check_outputs(dev, rep)
        open(out, "w").close()
        self.assertEqual(HL.main(["--holdout", HL.LOOK_FLAG, "--out", out, "--report", rep],
                                 jobs_fn=no_real_holdout), 2)          # labelled once

    def test_defaults_are_not_development_files(self):
        self.assertNotEqual(os.path.abspath(HL.HOLDOUT_LABELS), os.path.abspath(HL.P3.LABELS))
        self.assertNotEqual(os.path.abspath(HL.HOLDOUT_REPORT), os.path.abspath(HL.P3.REPORT))
        self.assertEqual(os.path.abspath(HL.HOLDOUT_LABELS), os.path.abspath(P.HOLDOUT_LABELS))


# ----------------------------------------------------------------------------------------------- analysis pieces
class _Stub:
    """The bits of v3_offline_eval.Ana the analysis helpers use."""

    def __init__(self, rows, tables):
        self.rows, self.tables = rows, tables

    @staticmethod
    def dec(r, g):
        return (r.get(g) or {}).get("d") if g != "saved" else r["saved"]["d"]

    @staticmethod
    def viol(r, g):
        return (r.get(g) or {}).get("viol") or []


TABLES = {"retail": {"rules": {"1": {"id": "1", "facts": ["x", "y"]}, "2": {"id": "2", "facts": ["z"]}},
                     "rows": {("1", "t", (True, True)): {"holds": True}, ("1", "t", (False, True)): {"holds": False},
                              ("1", "t", (True, False)): {"holds": False},
                              ("1", "t", (False, False)): {"holds": False},
                              ("2", "t", (True,)): {"holds": True}, ("2", "t", (False,)): {"holds": False}}}}


def row(ck, viol, f, probs, asks, saved="allow"):
    return {"ck": ck, "conv": ck.rsplit("|", 1)[0], "i": 0, "ds": "x", "tool": "t", "dom": "retail",
            "saved": {"d": saved}, "v3": {"d": "block" if viol else "allow", "viol": viol, "f": f, "probs": probs,
                                          "asks": asks}}


class TestAnalysisPieces(unittest.TestCase):
    def test_unclear_only_blocks(self):
        recs = {"k1": {"status": "unclear"}, "k2": {"status": "yes"}, "k3": {"status": "quote_failed"}}
        rows = [row("a|1|0", ["1"], {"x": [False, "blocking_value"], "y": [True, "code"]}, {"x": ["unclear"]},
                    [["k1", "K1", "x", "a", True]]),
                row("a|1|1", ["1", "2"], {"x": [False, "blocking_value"], "y": [True, "code"], "z": [False, "code"]},
                    {"x": ["unclear"]}, [["k3", "K2", "x", "b", True]]),
                row("a|1|2", ["1"], {"x": [False, "question"], "y": [True, "code"]}, {},
                    [["k2", "K1", "x", "a", True]])]
        res = P.unclear_blocks(_Stub(rows, TABLES), recs, set())
        self.assertEqual(res["counts"]["tiny blocks with a fact set by an answer problem"], 2)
        self.assertEqual(res["counts"]["only from an answer problem"], 1)
        self.assertEqual(res["counts"]["other rules block too"], 1)
        self.assertEqual([i["ck"] for i in res["items"] if i["only"]], ["a|1|0"])
        res = P.unclear_blocks(_Stub(rows[:1], TABLES), recs, {"k1"})
        self.assertEqual(res["counts"]["... with a missing answer"], 1)

    def test_two_keys(self):
        docs = {"retail": {"facts": {"f": {"combine": "a AND q", "blocking_value": False,
                                           "parts": {"a": {"source": "database"}, "q": {"source": "question"}}}}}}

        def r(a, q):
            return {"ck": "x|1|0", "dom": "retail", "v3": {"parts": {"f": {"a": [a, "database", "value"],
                                                                         "q": [q, "question", "value"]}}}}
        res = P.two_keys(_Stub([r(False, True), r(True, False), r(True, True), r(False, None)], {}), docs)
        c = res["counts"]
        self.assertEqual(c["two-key disagreement: the answers allow, a code part blocks"], 1)
        self.assertEqual(c["the answers block, code open (a question decided the block)"], 1)
        self.assertEqual(c["both keys open"], 1)
        self.assertEqual(c["asked facts with no answered question part (a problem or not needed)"], 1)

    def test_compare(self):
        recs = {"k": {"status": "no", "answer": "no", "quote": "", "prompt_user": "Question K2 ...", "raw": "{}"}}
        base = row("a|1|0", ["1"], {"x": [False, "question"]}, {}, [["k", "K2", "x", "b", True],
                                                                     ["k", "K2", "x", "b", True]])
        base["judge"] = {"x": [True, "the judge's words"]}
        base["v3sj"] = {"d": "allow", "f": {"x": [True, "saved_judge"]}}
        code = copy.deepcopy(base)
        code["ck"] = "a|1|1"
        code["v3sj"]["f"]["x"] = [False, "saved_judge"]
        same = copy.deepcopy(base)
        same["ck"], same["v3"]["f"]["x"] = "a|1|2", [True, "question"]
        docs = {"retail": {"facts": {"x": {"blocking_value": False}}}}
        res = P.compare(_Stub([base, code, same], {}), recs, set(), docs)
        c = res["counts"]
        self.assertEqual((c["asked facts"], c["agree"], c["disagree"]), (3, 1, 2))
        self.assertEqual(c["disagree, blocked check, from the question"], 1)
        self.assertEqual(c["disagree, blocked check, from code parts (the stand-in differs from the judge too)"], 1)
        self.assertEqual(c["disagree: tiny gives the blocking value"], 2)
        it = res["items"][0]
        self.assertEqual((it["ck"], it["judge_value"], it["tiny_value"], len(it["asks"])), ("a|1|0", True, False, 1))
        self.assertEqual(it["asks"][0]["qid"], "K2")
        self.assertTrue(it["asks"][0]["question"])
        self.assertIn("independent reviewer", P.render_compare({"compare": res}, "dev"))


# ----------------------------------------------------------------------------------------------- the pipeline
# The pipeline runs in a CHILD process: p11's safety (scoring.v3_offline_eval.setup_process) turns on a process-wide
# write guard and the network block, which must not reach the other test modules of the same unittest run.
def built_holdout_copy(conv):
    """A development conversation under a hold-out data set name (keys "ours.p10_luna_val|..."): a BUILT hold-out
    conversation; no hold-out file is read."""
    from fork import offline_v3 as O
    c = O.SavedConversation("ours.p10_luna_val", conv.conv_id, conv.ordinal, conv.domain, conv.split, conv.task_id,
                            conv.trial, conv.agent, conv.saved_guard, copy.deepcopy(conv.ep), dict(conv.meta))
    assert c.side == "holdout"
    return c


def child_dev(d: str) -> dict:
    from scoring import v3_p8_dryrun as P8
    rc = P.main(["--workers", "1", "--shards", "1", "--limit", "1", "--store", STORE_COPY, "--out-dir", d])
    rows = P.E.read_jsonl(P.outputs("dev", d)["rows"])
    with open(P.outputs("dev", d)["json"], encoding="utf-8") as f:
        num = json.load(f)
    mine = [c.conv_key for c in P.select_conversations("dev", 3)]
    ref = [c.conv_key for c in P8.side_conversations(P8.PAID_DATASETS, "dev", limit_convs=3, agent="luna")]
    return {"rc": rc, "pass_marks": num["pass_marks"], "convs": len({r["conv"] for r in rows}),
            "tiny": all(r["v3"]["switches"]["meaning"] == "tiny" for r in rows),
            "standin": all(r["v3sj"]["switches"]["meaning"] == "saved_judge" for r in rows),
            "asks": any(r["v3"]["asks"] for r in rows), "network_events": num["meta"]["network_events"],
            "judge_calls": sum(num["meta"]["judge_calls"].values()),
            "md": os.path.isfile(P.outputs("dev", d)["md"]), "selection": [mine, ref]}


def child_holdout(d: str) -> dict:
    from scoring import v3_p8_dryrun as P8
    convs = list(P8.side_conversations(P8.PAID_DATASETS, "dev", limit_convs=50, agent="luna"))
    writes = lambda c: sum(1 for ch in c.checks() if P.L.is_write(c.domain, ch.tool))   # noqa: E731
    src = [c for c in convs if c.domain == "retail" and writes(c)][:1] + \
        [c for c in convs if c.domain == "airline" and writes(c)][:1]
    built = [built_holdout_copy(c) for c in src]
    to_src = {b.conv_key: s.conv_key for b, s in zip(built, src)}
    back = {v: k for k, v in to_src.items()}

    def key(ck, m):
        conv, i = ck.rsplit("|", 1)
        return f"{m[conv]}|{i}"
    out: dict = {"n_built": len(built)}
    labels, rep = os.path.join(d, "tool_labels_holdout.jsonl"), os.path.join(d, "p3_holdout.md")

    def jobs(splits, counts):
        for c in built:
            counts.setdefault(c.dataset, collections.Counter())["built"] += 1
            yield (c.dataset, c.conv_id, c.domain, c.ep, None)
    out["labels_rc"] = HL.main(["--holdout", HL.LOOK_FLAG, "--out", labels, "--report", rep], jobs_fn=jobs)
    with open(labels, encoding="utf-8") as f:
        lines = [json.loads(x) for x in f]
    out["labels_all_holdout"] = bool(lines) and all(HL.is_holdout_line(x) for x in lines)
    dev = {}
    with open(HL.P3.LABELS, encoding="utf-8") as f:
        for x in f:
            y = json.loads(x)
            if any(y["ckey"].startswith(c.conv_key + "|") for c in src):
                dev[key(y["ckey"], back)] = y
    out["labels_equal_p3"] = ({x["ckey"]: [x["accepted"], x["check"], x["facts"]] for x in lines}
                              == {k: [y["accepted"], y["check"], y["facts"]] for k, y in dev.items()})
    orig = P.select_conversations

    def sel(side, limit=None, counts=None):
        if side != "holdout":
            return orig(side, limit, counts)
        P.require_unlocked()
        return iter(built)
    P.select_conversations = sel
    out_dir = os.path.join(d, "out")
    try:
        out["rc"] = P.main(["--holdout", P.LOOK_FLAG, "--workers", "1", "--shards", "1", "--store", STORE_COPY,
                            "--labels", labels, "--out-dir", out_dir])
    finally:
        P.select_conversations = orig
    o = P.outputs("holdout", out_dir)
    rows = P.E.read_jsonl(o["rows"])
    with open(o["json"], encoding="utf-8") as f:
        num = json.load(f)
    with open(o["md"], encoding="utf-8") as f:
        md = f.read()
    out.update(rows_all_holdout=bool(rows) and all(P.L.is_holdout_ckey(r["ck"]) for r in rows),
               pass_marks=num["pass_marks"], sections=sorted(num), md_has_p122="P12.2" in md,
               cmp_files=os.path.isfile(o["cmp_md"]) and os.path.isfile(o["cmp_jsonl"]))
    got = {key(r["ck"], to_src): [r["v3"]["d"], r["v3"]["viol"], r["v3"]["f"], r["label"] is not None] for r in rows}
    P.select_conversations = lambda side, limit=None, counts=None: iter(src)
    try:
        od = os.path.join(d, "dev_same")
        out["dev_same_rc"] = P.main(["--workers", "1", "--shards", "1", "--store", STORE_COPY, "--out-dir", od])
    finally:
        P.select_conversations = orig
    ref = {r["ck"]: [r["v3"]["d"], r["v3"]["viol"], r["v3"]["f"], r["label"] is not None]
           for r in P.E.read_jsonl(P.outputs("dev", od)["rows"])}
    out["any_labelled_write"] = any(v[3] for v in got.values())
    out["same_as_dev"] = got == ref
    relock()
    out["second_run_rc"] = P.main(["--holdout", P.LOOK_FLAG, "--store", STORE_COPY, "--labels", labels,
                                   "--out-dir", out_dir])
    relock()
    out["analyse_again_rc"] = P.main(["--holdout", P.LOOK_FLAG, "--store", STORE_COPY, "--labels", labels,
                                      "--out-dir", out_dir, "--phases", "analyse"])
    return out


def run_child(kind: str) -> dict:
    d = fresh(f"pipe_{kind}")
    res = os.path.join(d, "result.json")
    env = dict(os.environ, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1")
    log = os.path.join(TEST_DIR, f"child_{kind}.log")
    with open(log, "w", encoding="utf-8") as f:
        p = subprocess.run([sys.executable, "-B", "-m", "tests.test_v3_p12", "--child", kind, d, res], cwd=PC_DIR,
                           env=env, stdout=f, stderr=subprocess.STDOUT, timeout=1500)
    if p.returncode != 0:
        raise AssertionError(f"child {kind} failed (exit {p.returncode}); see {log}")
    with open(res, encoding="utf-8") as f:
        return json.load(f)


class TestPipeline(unittest.TestCase):
    """The dev path on 1 conversation per data set and the hold-out path on built conversations, with the store copy
    (each in a child process)."""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(STORE_COPY):
            raise unittest.SkipTest(f"no store copy at {STORE_COPY} (copy output/eval_v3/questions_answers.jsonl)")
        cls.dev = run_child("dev")
        cls.ho = run_child("holdout")

    def test_dev_selection_is_p12a_s(self):
        mine, ref = self.dev["selection"]
        self.assertEqual(mine, ref)
        self.assertEqual(len(mine), 12)

    def test_dev_run(self):
        x = self.dev
        self.assertEqual(x["rc"], 0)
        self.assertTrue(x["pass_marks"]["all_pass"], x["pass_marks"])
        self.assertEqual(x["pass_marks"]["missing_answers"]["missing"], 0)
        self.assertEqual(x["convs"], 4)
        self.assertTrue(x["tiny"] and x["standin"] and x["asks"] and x["md"])
        self.assertEqual((x["network_events"], x["judge_calls"]), (0, 0))

    def test_holdout_path_on_built_conversations(self):
        x = self.ho
        self.assertEqual(x["n_built"], 2)
        self.assertEqual(x["labels_rc"], 0)
        self.assertTrue(x["labels_all_holdout"])
        self.assertTrue(x["labels_equal_p3"])             # p3's label code, unchanged, on the built copies
        self.assertEqual(x["rc"], 0)
        self.assertTrue(x["rows_all_holdout"])
        self.assertTrue(x["pass_marks"]["all_pass"], x["pass_marks"])
        self.assertEqual(x["pass_marks"]["missing_answers"]["missing"], 0)
        for k in ("changes", "audit", "llm_share", "compare", "answers", "two_keys", "unclear_blocks"):
            self.assertIn(k, x["sections"])
        self.assertTrue(x["md_has_p122"] and x["cmp_files"])
        self.assertEqual(x["dev_same_rc"], 0)
        self.assertTrue(x["any_labelled_write"])
        self.assertTrue(x["same_as_dev"])                 # the hold-out path decides as the dev path
        self.assertEqual(x["second_run_rc"], 2)           # the hold-out run is made once
        self.assertEqual(x["analyse_again_rc"], 0)        # the analysis alone may be redone


class TestNoGoldCoverage(unittest.TestCase):
    def test_new_files_are_scanned(self):
        # the patterns of tests/test_no_gold_import.py V3_EXTRA_GLOBS (read as text; that module is not imported)
        import fnmatch
        with open(os.path.join(PC_DIR, "tests", "test_no_gold_import.py"), encoding="utf-8") as f:
            text = f.read()
        for g in ("scoring/v3_*.py", "tests/test_v3_*.py"):
            self.assertIn(f'"{g}"', text)
        for f in P.OWN_FILES:
            self.assertTrue(any(fnmatch.fnmatchcase(f, g) for g in ("scoring/v3_*.py", "tests/test_v3_*.py")), f)


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "--child":
        kind, d, res = sys.argv[2], sys.argv[3], sys.argv[4]
        out = child_dev(d) if kind == "dev" else child_holdout(d)
        with open(res, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1, default=str)
        sys.exit(0)
    unittest.main()
