"""Tracker v4: tests of the question-text overlay of agent A4 (output/eval_v4/overlays/questions_A4.json).

The authority is docs/planning/tracker_v4/predicate_table.md: section 3 (texts, second wordings, windows, few-shot,
answers), section 0 D10 (unclear policy) and section 2 (which predicates use which question). The test parses that
file, so a text typed wrong in the overlay fails here. It also runs v3's own validator (state_tracker.v3.questions
.check_doc) on the v3 file with its questions replaced by the overlay's, and checks that no few-shot example uses a
real id of the v1 data. No LLM call, no network; the v3 files are only read.

Run from predicate_correctness/:
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v4_question_texts -v
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys
import unittest

PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from state_tracker import paths                                    # noqa: E402
from state_tracker.v3 import questions as Q                        # noqa: E402

OVERLAY = os.path.join(PC_DIR, "output", "eval_v4", "overlays", "questions_A4.json")
TABLE = os.path.join(os.path.dirname(PC_DIR), "docs", "planning", "tracker_v4", "predicate_table.md")
V3_FILE = os.path.join(PC_DIR, "state_tracker", "v3", "questions_v3.json")
ENVS = os.path.join(paths.TAU_DIR, "tau_bench", "envs")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


# --------------------------------------------------------------------------------------------- the table, parsed

def _table_text() -> str:
    with open(TABLE, encoding="utf-8") as f:
        return f.read()


def _section(text: str, start: str, end: str) -> str:
    i = text.index(start)
    j = text.index(end, i)
    return text[i:j]


def _bullets(block: str):
    """[(bullet text, [sub-bullet texts])] of one question block; wrapped lines joined with one space."""
    out = []
    for line in block.splitlines():
        if line.startswith("- "):
            out.append([line[2:], []])
        elif line.startswith("  - ") and out:
            out[-1][1].append(line[4:])
        elif line.startswith("    ") and out and out[-1][1]:
            out[-1][1][-1] += " " + line.strip()
        elif line.startswith("  ") and out:
            out[-1][0] += " " + line.strip()
    return [(_squash(b), [_squash(s) for s in subs]) for b, subs in out]


def parse_section3(text: str) -> dict:
    sec = _section(text, "## 3. The kept tiny questions", "## 4. Counts")
    res = {}
    for block in sec.split("\n### ")[1:]:
        head = block.splitlines()[0]
        m = re.match(r"K(\d+)v4\b", head)
        assert m, head
        qid = "K" + m.group(1)
        item = {"few_shot": None}
        for b, subs in _bullets(block):
            if b.startswith("**Text:** "):
                item["text"] = re.match(r'\*\*Text:\*\* "([^"]*)"', b).group(1)
            elif b.startswith("**Second wording "):
                mm = re.match(r'\*\*Second wording (K\d+)v4b:\*\* "([^"]*)"', b)
                assert mm.group(1) == qid, b
                item["second"] = mm.group(2)
            elif b.startswith("**Window:** "):
                item["window"] = re.match(r"\*\*Window:\*\* (.*?)(?: \*\*|$)", b).group(1)
            elif b.startswith("**Few-shot: "):
                kind = re.match(r"\*\*Few-shot: (none|yes \(1 \+ 1\))\.\*\*", b).group(1)
                exs = []
                for s in subs:
                    mm = re.match(r"(yes|no|added|not_added|not_said)(?: \([^)]*\))?: (.*)$", s)
                    assert mm, s
                    before, after = mm.group(2).split("→", 1)
                    q = re.search(r'quote "([^"]*)"', after)
                    exs.append({"label": mm.group(1), "strings": re.findall(r'"([^"]*)"', before),
                                "answer": re.match(r"\s*(\w+)", after).group(1),
                                "quote": q.group(1) if q else None})
                item["few_shot"] = {"kind": kind, "examples": exs}
            elif b.startswith("**Defaults:** ") or b.startswith("**Accepted answers:** "):
                mm = re.search(r"Defaults?:(?:\*\*)? (.*)$", b)
                if mm:
                    item["defaults_line"] = mm.group(1)
        res[qid] = item
    return res


def parse_intro(text: str) -> dict:
    intro = _squash(_section(text, "## 3. The kept tiny questions", "### K1v4"))
    sec0 = _squash(_section(text, "## 0. Shared definitions", "## 1. "))
    allow = re.search(r"\*\*transfer or a login\*\* \(([^)]*)\)", sec0).group(1)
    return {
        "added_line": re.search(r'with one added line: "([^"]*)"', intro).group(1),
        "answers": re.search(r'Answer JSON `\{"answer": "([^"]*)"', intro).group(1).split("|"),
        "answers_k17": re.search(r"K17v4: `([^`]*)`", intro).group(1).split("|"),
        "allow": {"K" + n for n in re.findall(r"K(\d+)v4", allow)},
    }


def parse_facts(text: str) -> dict:
    """qid -> {domain: sorted predicates whose 'v4 source' cell names K<n>v4} (section 2 tables)."""
    sec = _section(text, "## 2. THE PREDICATE TABLE", "### 2.3")
    out: dict = {}
    for line in sec.splitlines():
        if not line.startswith("| "):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6 or cells[1] not in ("airline", "retail"):
            continue
        for n in sorted(set(re.findall(r"K(\d+)v4", cells[4]))):
            out.setdefault("K" + n, {}).setdefault(cells[1], set()).add(cells[0])
    return {q: {d: sorted(v) for d, v in ds.items()} for q, ds in out.items()}


def parse_counts(text: str) -> dict:
    sec = _squash(_section(text, "### 4.2 Tiny questions", "### 4.3"))
    dropped = re.search(r"\| dropped \(code\) \| (.*?) \|", sec).group(1)
    merged = re.search(r"\| merged \| (.*?) \|", sec).group(1)
    fs = re.search(r"Few-shot: (\d+) with 1 \+ 1 made-up examples \(([^)]*)\), (\d+) without \(([^)]*)\)", sec)
    return {"removed": set(re.findall(r"\bK\d+\b", dropped)) | {re.match(r"(K\d+)", merged).group(1)},
            "with": {x.strip() for x in fs.group(2).split(",")}, "without": {x.strip() for x in fs.group(4).split(",")},
            "n_with": int(fs.group(1)), "n_without": int(fs.group(3))}


# ------------------------------------------------------------------------------------------------------ helpers

def _msg_strings(q: dict, ex_inputs: dict) -> list:
    out = []
    for spec in q["inputs"]:
        if spec["type"] not in ("message", "messages") or spec["name"] not in ex_inputs:
            continue
        v = ex_inputs[spec["name"]]
        out += list(v) if isinstance(v, list) else [v]
    return out


def _v1_ids():
    """Every id-like value of the v1 data: user ids, emails, payment ids, order / item / product ids, reservation
    ids, flight numbers, saved-passenger names are not ids and are not used."""
    ids = set()
    id_key = re.compile(r"(^|_)id$|^email$|^flight_number$|^payment_id$|^item_id$|^product_id$")

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if isinstance(v, str) and id_key.search(k):
                    ids.add(v)
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    for d, files in (("airline", ("users", "reservations", "flights")), ("retail", ("users", "orders", "products"))):
        for name in files:
            data = _load(os.path.join(ENVS, d, "data", name + ".json"))
            ids.update(data.keys())                               # user ids, reservation ids, flight numbers, ...
            for v in data.values():
                walk(v)
                if isinstance(v, dict):
                    for sub in ("payment_methods", "variants"):
                        if isinstance(v.get(sub), dict):
                            ids.update(v[sub].keys())
    return {i for i in ids if i}


# ---------------------------------------------------------------------------------------------------------- tests

class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = _load(OVERLAY)
        cls.v3 = _load(V3_FILE)
        t = _table_text()
        cls.table = parse_section3(t)
        cls.intro = parse_intro(t)
        cls.facts = parse_facts(t)
        cls.counts = parse_counts(t)
        cls.kept = {k: v for k, v in cls.doc["questions"].items() if v is not None}


class TestShape(Base):
    def test_overlay_format(self):
        self.assertEqual(self.doc["by"], "A4")
        self.assertIn("questions", self.doc)
        self.assertEqual(set(self.doc["domain_texts"]), {"tools"})
        self.assertEqual(set(self.doc["domain_texts"]["tools"]), {"airline", "retail"})

    def test_question_set_is_the_table(self):
        self.assertEqual(len(self.table), 12)
        self.assertEqual(set(self.kept), set(self.table))

    def test_removed(self):
        self.assertEqual(self.counts["removed"], {"K2", "K5", "K9", "K11", "K14", "K15"})
        removed = {k for k, v in self.doc["questions"].items() if v is None}
        self.assertEqual(removed, self.counts["removed"])
        self.assertEqual(set(self.doc["removed"]), removed)
        self.assertTrue(removed <= set(self.v3["questions"]))
        self.assertEqual(set(self.v3["questions"]), removed | (set(self.kept) - {"K17", "K18"}))

    def test_v3_validator_accepts_the_merged_questions(self):
        doc = copy.deepcopy(self.v3)
        doc["questions"] = copy.deepcopy(self.kept)
        doc["domain_texts"] = copy.deepcopy(self.doc["domain_texts"])
        self.assertEqual(Q.check_doc(doc), [])
        for qid, q in self.kept.items():
            self.assertRegex(qid, r"^K[1-9][0-9]*$")
            self.assertEqual(q["text_sha256"], Q.question_hash(q), qid)

    def test_second_wording_validates(self):
        for qid, q in self.kept.items():
            s = q["second"]
            self.assertEqual(s["id"], qid + "b")
            self.assertIsInstance(s["version"], int)
            self.assertGreaterEqual(s["version"], 1)
            self.assertEqual(s["text_sha256"], Q.question_hash(s), qid)
            names = {i["name"] for i in q["inputs"]}
            for name in re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", s["question"]):
                self.assertIn(name, names, f"{qid}b uses {{{name}}}")
            self.assertNotEqual(s["question"], q["question"])

    def test_versions_are_new(self):
        for qid, q in self.kept.items():
            if qid in self.v3["questions"]:
                self.assertGreater(q["version"], self.v3["questions"][qid]["version"], qid)
                self.assertNotEqual(q["question"], self.v3["questions"][qid]["question"], qid)
            else:
                self.assertEqual(q["version"], 1, qid)


class TestTexts(Base):
    def test_text_exact(self):
        for qid, t in self.table.items():
            self.assertEqual(self.kept[qid]["question"], t["text"], qid)

    def test_second_exact(self):
        for qid, t in self.table.items():
            self.assertEqual(self.kept[qid]["second"]["question"], t["second"], qid)

    def test_window_exact(self):
        for qid, t in self.table.items():
            self.assertEqual(self.kept[qid]["window"], t["window"], qid)

    def test_accepted_answers(self):
        self.assertEqual(self.intro["answers"], ["yes", "no", "unclear"])
        for qid, q in self.kept.items():
            want = self.intro["answers_k17"] if qid == "K17" else self.intro["answers"]
            self.assertEqual(q["accepted_answers"], want, qid)
        self.assertEqual(self.kept["K17"]["accepted_answers"], ["added", "not_added", "not_said", "unclear"])

    def test_defaults_are_in_the_text(self):
        for qid, q in self.kept.items():
            self.assertTrue(q["defaults"], qid)
            line = self.table[qid].get("defaults_line")
            for d in q["defaults"]:
                if line is not None:
                    self.assertIn(d, line, qid)
                else:
                    self.assertIn(d, q["question"], qid)
        self.assertIn("No default to \"yes\" on silence.", self.kept["K1"]["defaults"])

    def test_d13_nothing_new_default(self):
        """D13: every question that reads user messages, except agreement (K1) and the reason questions whose own
        text names what is no (K7, K17, K18), says a message asking for nothing new is no."""
        for qid in ("K4", "K6", "K8", "K10", "K13", "K16"):
            self.assertIn("asks for nothing new", self.kept[qid]["question"], qid)

    def test_system_version_2(self):
        sv = self.doc["system_v2"]
        self.assertEqual(sv["added_line"], self.intro["added_line"])
        self.assertEqual(sv["system"], self.v3["system"] + " " + self.intro["added_line"])
        self.assertEqual(sv["system_version"], 2)
        self.assertEqual(sv["based_on_v3_system_sha256"], Q.sha256_text(self.v3["system"]))
        for qid, q in self.kept.items():
            self.assertEqual(q["system_version"], 2, qid)

    def test_on_unclear(self):
        self.assertEqual(self.intro["allow"], {"K4", "K13", "K16"})
        for qid, q in self.kept.items():
            self.assertEqual(q["on_unclear"], "allow" if qid in self.intro["allow"] else "block", qid)
            self.assertTrue(q["on_unclear_note"], qid)

    def test_facts_match_section2(self):
        self.assertEqual(set(self.facts), set(self.kept))
        frozen = {d: set(_load(os.path.join(PC_DIR, "state_tracker", "v3", f"facts_v3_{d}.json"))["facts"])
                  for d in ("airline", "retail")}
        for qid, q in self.kept.items():
            self.assertEqual({d: sorted(v) for d, v in q["facts"].items()}, self.facts[qid], qid)
            for d, names in q["facts"].items():
                self.assertTrue(set(names) <= frozen[d], (qid, set(names) - frozen[d]))

    def test_inputs(self):
        for qid, q in self.kept.items():
            names = {i["name"] for i in q["inputs"]}
            for spec in q["inputs"]:
                f = spec.get("follows")
                if f:
                    self.assertIn(f["input"], names)
                    src = next(i for i in q["inputs"] if i["name"] == f["input"])
                    self.assertEqual(set(f["map"]), set(src["values"]), qid)
                    self.assertEqual(set(f["map"].values()), set(spec["values"]), qid)
        self.assertEqual([i["name"] for i in self.kept["K1"]["inputs"]], ["listing", "replies", "action"])
        self.assertEqual(self.kept["K1"]["quote_from"], ["replies"])
        self.assertEqual(self.kept["K13"]["inputs"][1]["from"], "domain")


class TestFewShot(Base):
    def test_where_the_table_says(self):
        self.assertEqual(self.counts["n_with"], len(self.counts["with"]))
        self.assertEqual(self.counts["n_without"], len(self.counts["without"]))
        for qid, t in self.table.items():
            fs = self.kept[qid]["few_shot"]
            self.assertIsNotNone(t["few_shot"], qid)
            if t["few_shot"]["kind"] == "none":
                self.assertEqual(fs, [], qid)
                self.assertIn(qid, self.counts["without"])
            else:
                self.assertEqual(len(fs), 2, qid)
                self.assertIn(qid, self.counts["with"])
            self.assertTrue(self.kept[qid]["few_shot_why"], qid)

    def test_examples_exact(self):
        for qid, t in self.table.items():
            q = self.kept[qid]
            for ex, want in zip(q["few_shot"], t["few_shot"]["examples"]):
                self.assertEqual(ex["answer"], want["answer"], qid)
                self.assertEqual(ex["answer"], want["label"], qid)
                self.assertEqual(_msg_strings(q, ex["inputs"]), want["strings"], qid)
                if want["quote"] is not None:
                    self.assertEqual(ex["quote"], want["quote"], qid)
                    self.assertTrue(ex["quote_in_table"], qid)
                elif ex["answer"] in ("no", "not_said"):
                    self.assertEqual(ex["quote"], "", qid)
                else:
                    self.assertFalse(ex["quote_in_table"], qid)

    def test_quotes_pass_the_quote_check(self):
        for qid, q in self.kept.items():
            for ex in q["few_shot"]:
                if not ex["quote"]:
                    continue
                srcs = [ex["inputs"][n] for n in q["quote_from"] if n in ex["inputs"]]
                srcs = [x for s in srcs for x in (s if isinstance(s, list) else [s])]
                self.assertTrue(Q.quote_in(ex["quote"], srcs), (qid, ex["quote"]))
                self.assertTrue(any(ex["quote"] in s for s in srcs), (qid, ex["quote"]))

    def test_example_inputs_are_known(self):
        for qid, q in self.kept.items():
            specs = {i["name"]: i for i in q["inputs"]}
            for ex in q["few_shot"]:
                self.assertTrue(set(ex["inputs"]) <= set(specs), qid)
                for name, v in ex["inputs"].items():
                    if specs[name]["type"] == "choice":
                        self.assertIn(v, specs[name]["values"], qid)
                    f = specs[name].get("follows")
                    if f:
                        self.assertEqual(v, f["map"][ex["inputs"][f["input"]]], qid)
                filled = dict(ex["inputs"])
                for name, spec in specs.items():       # call / domain texts (K1 action, K13 tools) come at ask time
                    if spec["type"] == "text":
                        filled.setdefault(name, "given at ask time")
                Q.check_inputs(qid, filled, {"questions": {qid: q}})

    def test_no_real_v1_id(self):
        ids = _v1_ids()
        self.assertGreater(len(ids), 5000)                 # the data was read
        for probe in ("mia_li_3668", "HAT170"):
            self.assertIn(probe, ids)
        lower = {i.lower() for i in ids}
        texts = []
        for q in self.kept.values():
            for ex in q["few_shot"]:
                texts += [v for v in ex["inputs"].values() for v in (v if isinstance(v, list) else [v])]
                texts.append(ex["quote"])
        texts += list(self.doc["domain_texts"]["tools"].values())
        for t in texts:
            for tok in re.findall(r"[#\w@.\-]+", t):
                tok = tok.strip(".-")
                if not tok:
                    continue
                self.assertNotIn(tok, ids, t)
                self.assertNotIn(tok.lower(), lower, t)
                self.assertNotIn("#" + tok, ids, t)
            self.assertIsNone(re.search(r"\d{4,}", t), t)  # no id-like digit run at all


class TestDomainTexts(Base):
    def test_airline_refused_items_cite_sentences(self):
        text = self.doc["domain_texts"]["tools"]["airline"]
        refused = text.split("Requests the policy refuses", 1)[1]
        cited = re.findall(r"\((S\d+)(?:-(S\d+))?\)", refused)
        ids = set()
        for a, b in cited:
            lo, hi = int(a[1:]), int((b or a)[1:])
            ids |= {f"S{i}" for i in range(lo, hi + 1)}
        self.assertEqual(ids, {"S29", "S30", "S31", "S32"})       # the table: S29, S30, S31-S32
        self.assertEqual(len(cited), 3)
        sents = {s["id"]: s["text"] for s in _load(os.path.join(paths.RULES_DIR, "airline", "rule_set.json"))
                 ["sentences"]}
        self.assertIn("not remove checked bags", sents["S29"])
        self.assertIn("cannot add insurance after initial booking", sents["S30"])
        self.assertIn("cannot modify the number of passengers", sents["S31"])
        self.assertIn("even a human agent cannot assist", sents["S32"])
        self.assertIn("removing checked bags (S29)", refused)
        self.assertIn("adding travel insurance after booking (S30)", refused)
        self.assertIn("changing the number of passengers (S31-S32)", refused)

    def test_every_v1_tool_is_described(self):
        phrases = {
            "airline": {"book_reservation": "Book a new reservation", "calculate": "Calculate",
                        "cancel_reservation": "Cancel a whole reservation",
                        "get_reservation_details": "a reservation's details", "get_user_details": "profile",
                        "list_all_airports": "the airports", "search_direct_flight": "direct",
                        "search_onestop_flight": "one-stop", "send_certificate": "Send a certificate",
                        "update_reservation_baggages": "Add checked bags",
                        "update_reservation_flights": "Change the flights",
                        "update_reservation_passengers": "passenger details"},
            "retail": {"calculate": "Calculate", "cancel_pending_order": "Cancel a pending order",
                       "exchange_delivered_order_items": "exchange items of a delivered order",
                       "find_user_id_by_email": "by email", "find_user_id_by_name_zip": "last name and zip code",
                       "get_order_details": "orders", "get_product_details": "the products",
                       "get_user_details": "profile", "list_all_product_types": "types",
                       "modify_pending_order_address": "shipping address",
                       "modify_pending_order_items": "options of its items",
                       "modify_pending_order_payment": "its payment method",
                       "modify_user_address": "default address",
                       "return_delivered_order_items": "Return"},
        }
        for d, want in phrases.items():
            files = sorted(f[:-3] for f in os.listdir(os.path.join(ENVS, d, "tools"))
                           if f.endswith(".py") and f != "__init__.py")
            self.assertEqual(len(files), {"airline": 14, "retail": 16}[d], d)
            self.assertEqual(set(files) - {"think", "transfer_to_human_agents"}, set(want), d)
            text = self.doc["domain_texts"]["tools"][d]
            for tool, phrase in want.items():
                self.assertIn(phrase, text, (d, tool))

    def test_retail_keeps_nothing_else(self):
        self.assertIn("but nothing else", self.doc["domain_texts"]["tools"]["retail"])


if __name__ == "__main__":
    unittest.main()
