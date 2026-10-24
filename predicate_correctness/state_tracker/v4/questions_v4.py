"""Tracker v4: the tiny questions (docs/planning/tracker_v4/code_change_map.md §1.1 row questions_v4.py;
predicate_table.md §0 D10 unclear, D12 quote check, §3 the questions).

The main idea in plain words: v4 asks the same kind of tiny yes/no questions as v3, with new texts, a second wording
used once when the first answer is unclear, a looser quote check (a quote may be cut at any punctuation mark), and a
per-question rule for "still unclear" (block, or allow and log). Everything v3 already does well is reused from
state_tracker.v3.questions (imported as Q): the exception classes (the SAME class objects, so the v3 guard's
HARD_STOPS still catch them), the stores, the budget, the network block, the normalization and the cache key.

    from state_tracker.v4 import questions_v4 as Q4
    hook = Q4.QuestionsV4(Q4.FakeBackendV4("yes"), ask_log="…/asks_shard1of4.jsonl")
    hook.where = {"run_id": …, "step": …, "domain": …, "task": …, "trial": …, "arm": …, "check": …}   # per thread
    rec = hook.ask("K4", {"message": "Can you check my wife's order?"}, fact=…, part=…)            # wording 1
    rec = hook.ask("K4", {...}, fact=…, part=…, wording=2)                                          # the 2nd wording
    rec["status"]   yes | no | unclear | quote_failed | bad_output   (K17: added | not_added | not_said | …)
    rec["missing"]  the answer's "missing" text (schema of system v2; "" otherwise)

---------------------------------------------------------------------------------------------------------------
The questions file questions_v4.json (built by the main chat's merge script; check_doc_v4 is its validator)
---------------------------------------------------------------------------------------------------------------
Top fields: _about, domain_texts ({name: {domain: text}}), effort ("low"), model ("gpt-6-luna"), price (as v3),
questions, systems. Optional: answer_format, schema_version (the file format; 2).
  The merge layout is accepted too (normalize_doc_v4, done by load_questions_v4 and QuestionsV4): v3's top fields
  (system, schema, schema_name, system_sha256, system_version) give system "1", and A4's block system_v2 =
  {system, system_version, added_line, ...} gives system "2" (schema: v3's + a required string `missing`).
  systems = {"1": {system, schema, schema_name, system_sha256}, "2": {...}}
      "1" must be v3's system byte for byte (system_sha256 == V3_SYSTEM_SHA256, schema {answer, quote});
      every other system's schema has exactly {answer, quote, missing}.
      system_sha256 = Q.system_hash({"system", "system_version": int(key), "schema", "schema_name"}).
  questions[Kn] = v3's fields (id, version, question, inputs, quote_from, facts, text_sha256) plus
      system_version  int, a key of systems (1 only for a question whose text is v3's, unchanged)
      on_unclear      "block" | "allow"     (D10: write and reply checks block; K4, K13, K16 allow + log)
      second          {"id": "<Kn>b", "version": int >= 1, "question": "<the second wording>", "text_sha256"}
                      (D10's <id>b; same inputs; text_sha256 = Q.question_hash(second) when given)
      few_shot        optional list of {"inputs": {message or choice input: value}, "answer", "quote"[, "missing"]}
                      (made up from the v1 policy; rendered for both wordings; not allowed with system 1)
      accepted_answers (or answers) optional, default ["yes", "no", "unclear"];
                      K17: ["added", "not_added", "not_said", "unclear"] (schema enum and answer line follow it)
      quote_needed    optional, the answers that need a quote; default ["yes"], else every answer but unclear /
                      no / not_said (K17: added, not_added)
      text_sha256     Q.question_hash(entry) over every field but itself (a changed text needs a new version)
  A choice input with "follows": {"input": <choice>, "map": {value: value}} is filled by code from that choice
  (K3 verb from items_action; K18 gloss from reason). The other choice input is set by items= or, with
  "from": "call", from the call's argument of that name (K18 reason).
  Input types as v3 (message, messages, text, choice). A text input "from": "call" is rendered by code: name "trip"
  -> Q.trip_text; "render": "action_line", or the name "action" with no render and no focus -> action_line_v4
  (K1v4's {action}: tool phrase + object id + item names / flight numbers); "render": "listing_lines" ->
  Q.render_listing; else Q.render_action(focus). A text "from": "domain" comes from domain_texts. A {placeholder}
  in the question text may name a choice input or a text input (inserted inline, then not shown again).

Keys (cache): sha256(question id, key version, model, effort, normalized input) as v3 (Q.cache_key).
  key_version_v4 = "q<version>.s<system_version>" for wording 1, so a question with system_version 1 and v3's
  version and inputs has exactly v3's key; wording 2 uses the id "<Kn>b" and "q<second.version>b.s<system>".
Render: a system-1 question in wording 1 renders byte-equal to v3's Q.render. Every other render: the header, the
  few-shot block, the inputs, "Question: <text>", the answer line; the system text of its system version.

---------------------------------------------------------------------------------------------------------------
Helpers (registered on import; every name ends in _v4; v3's names are untouched)
---------------------------------------------------------------------------------------------------------------
  ask_v4(qid, m1[, m2], focus=None, items=None, on_unclear=None)                       source question
  ask_first_yes_v4(qid, candidates, focus=None, items=None, limit=None, on_unclear=None) source question
      candidates newest first: a message, or a tuple / list [message A, message B or [messages B]] (K1v4:
      [L, [user messages after L]]; K17: [agent message, reply] or a single user message). True at the first yes.
      items= sets the question's choice input (K3: 'exchanged' / 'modified'; K18: the call's reason).
  offer_kind_v4(reply, kind[, db_kinds])                                                 source question
      kind 'cancelled' | 'delayed'. db_kinds: the kinds the database shows for the named, eligible reservations
      (a list / set of 'cancelled' / 'delayed', or a dict {kind: bool}); one kind only decides; both or none ->
      K12's quote words (cancel / delay); still undecided -> True (the blocking value).
  offer_amount_ok_v4(reply, rate, passenger_counts)                                      source structure (code)
      the dollar amounts of the reply's sentences that hold a compensation noun (certificate, voucher, credit (not
      "credit card"), compensation, gesture, goodwill): True if none, or one = rate x a passenger count, or = rate
      with "per passenger / each / per person" within 40 characters.
  insurance_stated_v4(candidates, value)                                                 source question
      K17 on each candidate, newest first; the first decided answer (added / not_added) must equal
      {'yes': 'added', 'no': 'not_added'}[value]; not_said or still unclear -> the next older candidate; none
      decided -> False.
Unclear (D10; a failed quote and a bad output count as unclear): the helper asks once more with wording=2 (same
input), noted as {"v4": "reask", qid, fact, part, key1, key2, status1, status2}. Still unclear:
  on_unclear=None (the file says "block") -> facts_format_v3.UseBlockingValue(kind="unclear"), counted;
  on_unclear=<bool> (the file must say "allow") -> that value is returned, noted {"v4": "unclear_allowed", ...}.
  A mismatch between the expression and the file raises ValueError (a build error, never a silent value).
The notes go to ctx.note() and to the hook's per-thread event list (QuestionsV4.take_events_v4()).
A hook wrapper (e.g. a counting hook in the v4 guard) must forward ask(..., wording=...) and the attribute doc.

Hook: QuestionsV4(backend, store=None, *, doc=None, keep_log=True, ask_log=None). It writes one ask-log line per
ask, cached or not: {ts, key, qid, wording, fact, part, where, cached, store, status, answer} (ask_log = a JSONL
path, also kept in hook.ask_lines). A new answer record adds wording, missing, where_first. It refuses a writable
v3 answers file always, and a writable v4 dev answers file (V4_ANSWERS_PATH) unless the backend is real.
Stores: MemoryStore / JsonlStore (v3's), ChainStore(v4_store, v3_store): reads v4 then v3 (read-only), writes v4.
Backends: FakeBackendV4 = FakeBackend here (fakes on the v4 file; second= a policy for wording 2; v3's class is
FakeBackendV3), SavedBackend (v3's),
RealBackendV4 (needs approval_flag=True from the main chat plus v3's approval words and budgets; the schema of the
question's system version with the question's answers; refused when the network is blocked).
Standard library only (the real backend imports openai / azure.identity of the venv when it runs).
"""
from __future__ import annotations

import argparse
import collections
import copy
import json
import os
import re
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    __package__ = "state_tracker.v4"

from state_tracker import paths                          # noqa: E402
from state_tracker.v3 import facts_format_v3 as F        # noqa: E402
from state_tracker.v3 import questions as Q              # noqa: E402

# ----------------------------------------------------------------------------------------------- reused from v3
# The SAME objects (not copies): the v3 guard re-raises only its HARD_STOPS (v3 classes).
QuestionsFileError = Q.QuestionsFileError
NetworkBlocked = Q.NetworkBlocked
RealModeRefused = Q.RealModeRefused
BudgetExceeded = Q.BudgetExceeded
AnswerNotSaved = Q.AnswerNotSaved
RealCallFailed = Q.RealCallFailed
MemoryStore = Q.MemoryStore
JsonlStore = Q.JsonlStore
FakeBackendV3 = Q.FakeBackend          # v3's fakes read v3's file; v4 code uses FakeBackend (= FakeBackendV4, below)
SavedBackend = Q.SavedBackend
Budget = Q.Budget
Stats = Q.Stats
StandInAnswers = Q.StandInAnswers
check_real_mode = Q.check_real_mode
block_network = Q.block_network
network_blocked = Q.network_blocked
network_events = Q.network_events
normalize_text = Q.normalize_text
message_text = Q.message_text
cache_key = Q.cache_key
clean_quote = Q.clean_quote
quote_form = Q.quote_form

QUESTIONS_V4_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "questions_v4.json")
V4_ANSWERS_REL = "output/eval_v4/questions_answers_v4.jsonl"
V4_ANSWERS_PATH = os.path.join(paths.PC_DIR, *V4_ANSWERS_REL.split("/"))
V3_ANSWERS_PATH = Q.ANSWERS_PATH
V3_SYSTEM_SHA256 = "9db089322f02f7cefcd23b6d0d198116e48d1b1117d6e04df2ffa2eb3cf223b7"   # questions_v3.json system 1

YES_NO = ("yes", "no", "unclear")
K17_ANSWERS = ("added", "not_added", "not_said", "unclear")
UNRESOLVED = ("unclear", "quote_failed", "bad_output")
ON_UNCLEAR = ("block", "allow")
RENDERS_V4 = ("listing_lines", "action_line")
WHERE_KEYS = ("run_id", "step", "domain", "task", "trial", "arm", "check")
MIN_PIECE = 2
MISSING_LINE = ('Also give "missing": for a no, a few words on what is missing; otherwise an empty text.')
_QID = re.compile(r"^K[1-9][0-9]*$")
_PLACE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

_DEFAULT = {"path": QUESTIONS_V4_PATH}
_DOC: Dict[str, dict] = {}
_DOC_LOCK = threading.Lock()


# ----------------------------------------------------------------------------------------------- the questions file

def system_hash_v4(sv: Any, entry: dict) -> str:
    """sha256 of one system entry, computed as v3's system_hash (so system 1 hashes to V3_SYSTEM_SHA256)."""
    return Q.system_hash({"system": entry.get("system"), "system_version": int(sv), "schema": entry.get("schema"),
                          "schema_name": entry.get("schema_name")})


def answers_of(q: dict) -> Tuple[str, ...]:
    """The question's answer values: `accepted_answers` (A4's overlay field) or `answers`; default yes/no/unclear."""
    return tuple(q.get("accepted_answers") or q.get("answers") or YES_NO)


V2_SCHEMA_NAME = "tiny_answer_v2"


def v2_schema_from(schema1: dict) -> dict:
    """v3's schema plus a required string `missing` (code_change_map.md §0.2 item 5)."""
    s = copy.deepcopy(schema1)
    s.setdefault("properties", {})["missing"] = {"type": "string"}
    s["required"] = list(s.get("required") or ["answer", "quote"]) + ["missing"]
    return s


def normalize_doc_v4(doc: Any) -> Any:
    """A file in the merge layout (v3's top fields system / schema / schema_name / system_sha256 / system_version,
    plus A4's `system_v2` block {system, system_version, added_line, ...}) gets a `systems` object: "1" from the
    v3 top fields (when present), "<n>" from system_v2 (schema: v3's + `missing`, unless the block gives one;
    system_sha256 computed when the block has none). A file that already has `systems` is returned as is."""
    if not isinstance(doc, dict) or "systems" in doc:
        return doc
    doc = dict(doc)
    systems: Dict[str, dict] = {}
    base = doc.get("schema")
    if all(k in doc for k in ("system", "schema", "schema_name", "system_sha256")):
        systems[str(doc.get("system_version", 1))] = {"system": doc["system"], "schema": doc["schema"],
                                                      "schema_name": doc["schema_name"],
                                                      "system_sha256": doc["system_sha256"]}
    for k, blk in sorted(doc.items()):
        m = re.match(r"^system_v([0-9]+)$", k)
        if not m or not isinstance(blk, dict):
            continue
        sv = str(blk.get("system_version", m.group(1)))
        schema = blk.get("schema") or (v2_schema_from(base) if isinstance(base, dict) else None)
        e = {"system": blk.get("system"), "schema": schema,
             "schema_name": blk.get("schema_name") or V2_SCHEMA_NAME}
        e["system_sha256"] = blk.get("system_sha256") or system_hash_v4(sv, e)
        systems[sv] = e
    doc["systems"] = systems
    return doc


def quote_needed_of(q: dict) -> Tuple[str, ...]:
    if q.get("quote_needed") is not None:
        return tuple(q["quote_needed"])
    ans = answers_of(q)
    return ("yes",) if "yes" in ans else tuple(a for a in ans if a not in ("unclear", "no", "not_said"))


def _placeholders(text: Any) -> List[str]:
    return _PLACE.findall(text) if isinstance(text, str) else []


def check_doc_v4(doc: Any) -> List[str]:
    """Problems with a v4 questions file (empty: fine)."""
    p: List[str] = []
    if not isinstance(doc, dict):
        return ["the file is not a JSON object"]
    doc = normalize_doc_v4(doc)
    for f in ("_about", "domain_texts", "effort", "model", "price", "questions", "systems"):
        if f not in doc:
            p.append(f"missing top field {f!r}")
    if p:
        return p
    if doc["model"] != "gpt-6-luna" or doc["effort"] != "low":
        p.append("model must be gpt-6-luna with effort low (Q3)")
    if not isinstance(doc["price"], dict) or not {"input_per_m", "output_per_m"} <= set(doc["price"]):
        p.append("price needs input_per_m and output_per_m")
    systems = doc["systems"]
    if not isinstance(systems, dict) or not systems:
        return p + ["systems must be a non-empty object"]
    for sv, s in systems.items():
        pre = f"system {sv}:"
        if not str(sv).isdigit() or int(sv) < 1:
            p.append(f"{pre} the key must be an integer >= 1")
            continue
        if not isinstance(s, dict) or any(k not in s for k in ("system", "schema", "schema_name", "system_sha256")):
            p.append(f"{pre} needs system, schema, schema_name, system_sha256")
            continue
        if s["system_sha256"] != system_hash_v4(sv, s):
            p.append(f"{pre} system_sha256 differs: the system text or schema changed (new version and hash)")
        props = set((s["schema"] or {}).get("properties", {}))
        want = {"answer", "quote"} if int(sv) == 1 else {"answer", "quote", "missing"}
        if props != want:
            p.append(f"{pre} the schema must have exactly {sorted(want)}")
        if int(sv) == 1 and s["system_sha256"] != V3_SYSTEM_SHA256:
            p.append(f"{pre} system 1 must be v3's system byte for byte")
    for qid, q in doc["questions"].items():
        pre = f"{qid}:"
        if not _QID.match(qid) or not isinstance(q, dict) or q.get("id") != qid:
            p.append(f"{pre} id must be K<n> and equal its key")
            continue
        need = ("facts", "id", "inputs", "question", "quote_from", "text_sha256", "version", "system_version",
                "on_unclear", "second")
        miss = [f for f in need if f not in q]
        if miss:
            p.append(f"{pre} missing fields {miss}")
            continue
        if not isinstance(q["version"], int) or isinstance(q["version"], bool) or q["version"] < 1:
            p.append(f"{pre} version must be an integer >= 1")
        sv = q["system_version"]
        if str(sv) not in systems:
            p.append(f"{pre} system_version {sv!r} is not in systems")
        if q["on_unclear"] not in ON_UNCLEAR:
            p.append(f"{pre} on_unclear must be one of {ON_UNCLEAR}")
        sec = q["second"]
        if not isinstance(sec, dict) or not isinstance(sec.get("question"), str) or not sec.get("question") \
                or not isinstance(sec.get("version"), int) or isinstance(sec.get("version"), bool) \
                or sec["version"] < 1:
            p.append(f"{pre} second must be {{version: int >= 1, question: text}}")
            sec = {"question": ""}
        else:
            if "id" in sec and sec["id"] != qid + "b":
                p.append(f"{pre} second id must be {qid}b")
            if "text_sha256" in sec and sec["text_sha256"] != Q.question_hash(sec):
                p.append(f"{pre} second text_sha256 differs: the second wording changed (new version and hash)")
        ans = answers_of(q)
        if "unclear" not in ans or len(set(ans)) != len(ans) or len(ans) < 3:
            p.append(f"{pre} answers must list at least 3 distinct answers, unclear among them")
        if any(a not in ans or a == "unclear" for a in quote_needed_of(q)) or not quote_needed_of(q):
            p.append(f"{pre} quote_needed must be answers other than unclear")
        names = [i.get("name") for i in q["inputs"]]
        specs = {i.get("name"): i for i in q["inputs"]}
        if len(set(names)) != len(names):
            p.append(f"{pre} an input name is listed twice")
        for i in q["inputs"]:
            if i.get("type") not in Q.INPUT_TYPES:
                p.append(f"{pre} input {i.get('name')!r}: type must be one of {Q.INPUT_TYPES}")
            if not i.get("label"):
                p.append(f"{pre} input {i.get('name')!r}: needs a label")
            if i.get("type") == "choice" and not i.get("values"):
                p.append(f"{pre} input {i.get('name')!r}: a choice needs values")
            if "render" in i and (i.get("render") not in RENDERS_V4 or i.get("type") != "text"
                                  or i.get("from") != "call"):
                p.append(f"{pre} input {i.get('name')!r}: render must be one of {RENDERS_V4} on a call text")
            if i.get("type") == "text" and i.get("from") == "domain":
                dt = doc["domain_texts"].get(i.get("name"))
                if not isinstance(dt, dict) or not dt:
                    p.append(f"{pre} input {i.get('name')!r}: domain_texts has no {i.get('name')!r}")
        msg_inputs = [i["name"] for i in q["inputs"] if i.get("type") in ("message", "messages")]
        if not q["quote_from"] or any(n not in msg_inputs for n in q["quote_from"]):
            p.append(f"{pre} quote_from must name message inputs")
        for i in q["inputs"]:
            fl = i.get("follows")
            if fl is None:
                continue
            src = specs.get(fl.get("input")) if isinstance(fl, dict) else None
            if i.get("type") != "choice" or src is None or src.get("type") != "choice" or src.get("follows") \
                    or not isinstance(fl.get("map"), dict) or set(fl["map"]) != set(src.get("values") or []) \
                    or any(v not in (i.get("values") or []) for v in fl["map"].values()):
                p.append(f"{pre} input {i.get('name')!r}: follows needs input=<a plain choice input> and a map from "
                         f"all its values to this input's values")
        if len([i for i in q["inputs"] if i.get("type") == "choice" and not i.get("follows")]) > 1:
            p.append(f"{pre} at most one choice input without follows (items= sets it)")
        allowed = set(n for n in names if specs[n].get("type") in ("choice", "text"))
        for where, text in (("question", q["question"]), ("second", sec.get("question"))):
            for name in _placeholders(text):
                if name not in allowed:
                    p.append(f"{pre} the {where} text uses {{{name}}}, which is not a choice or text input")
        shots = q.get("few_shot") or []
        if not isinstance(shots, list):
            p.append(f"{pre} few_shot must be a list")
            shots = []
        for n, ex in enumerate(shots, 1):
            if not isinstance(ex, dict) or not isinstance(ex.get("inputs"), dict) or ex.get("answer") not in ans:
                p.append(f"{pre} few_shot {n}: needs inputs and one of the answers")
                continue
            if any(k not in names or specs[k].get("type") == "text" for k in ex["inputs"]):
                p.append(f"{pre} few_shot {n}: inputs must be message or choice inputs")
            if not any(k in msg_inputs for k in ex["inputs"]):
                p.append(f"{pre} few_shot {n}: needs a message input")
            if ex["answer"] in quote_needed_of(q):
                texts = []
                for k in q["quote_from"]:
                    v = ex["inputs"].get(k)
                    texts += list(v) if isinstance(v, list) else ([v] if v else [])
                if not quote_in_v4(ex.get("quote"), texts):
                    p.append(f"{pre} few_shot {n}: the quote is not in the example's message")
        if str(sv) == "1" and (shots or ans != YES_NO or any(i.get("follows") for i in q["inputs"])):
            p.append(f"{pre} a system 1 question (v3's text) takes no few_shot, follows or other answers")
        if q["text_sha256"] != Q.question_hash(q):
            p.append(f"{pre} text_sha256 differs: the question changed (give a new version and hash)")
    return p


def v3_identity_problems_v4(doc: dict, v3doc: dict) -> List[str]:
    """A system-1 question must be v3's question unchanged (same version, text, inputs, quote_from), else its key
    would equal a v3 key for another question text. Empty: fine."""
    p = []
    for qid, q in doc["questions"].items():
        if str(q.get("system_version")) != "1":
            continue
        v3q = v3doc["questions"].get(qid)
        if v3q is None:
            p.append(f"{qid}: system 1 but v3 has no {qid}")
            continue
        for f in ("version", "question", "inputs", "quote_from"):
            if q.get(f) != v3q.get(f):
                p.append(f"{qid}: system 1 but {f} differs from v3 (give system 2)")
    return p


def set_questions_path_v4(path: Optional[str]) -> str:
    """Change the default file of load_questions_v4() (tests: the fixture). None: back to QUESTIONS_V4_PATH."""
    _DEFAULT["path"] = os.path.abspath(path) if path else QUESTIONS_V4_PATH
    return _DEFAULT["path"]


def load_questions_v4(path: Optional[str] = None) -> dict:
    """The v4 questions file (checked; loaded once per path). Default: state_tracker/v4/questions_v4.json (or the
    path set by set_questions_path_v4). Never v3's file. Raises QuestionsFileError."""
    path = os.path.abspath(path or _DEFAULT["path"])
    with _DOC_LOCK:
        if path not in _DOC:
            with open(path, encoding="utf-8") as f:
                doc = normalize_doc_v4(json.load(f))
            problems = check_doc_v4(doc)
            if problems:
                raise QuestionsFileError(f"{path}: " + "; ".join(problems))
            _DOC[path] = doc
        return _DOC[path]


def question_v4(qid: str, doc: Optional[dict] = None) -> dict:
    doc = doc or load_questions_v4()
    if qid not in doc["questions"]:
        raise KeyError(f"unknown v4 question {qid!r} (known: {question_ids_v4(doc)})")
    return doc["questions"][qid]


def question_ids_v4(doc: Optional[dict] = None) -> List[str]:
    return sorted((doc or load_questions_v4())["questions"], key=Q._qkey)


def _check_wording(wording: Any) -> int:
    if wording not in (1, 2) or isinstance(wording, bool):
        raise ValueError(f"wording must be 1 or 2, not {wording!r}")
    return wording


def key_version_v4(qid: str, doc: Optional[dict] = None, wording: int = 1) -> str:
    """'q<version>.s<system_version>' (wording 1; equals v3's key_version for a system-1 question) or
    'q<second version>b.s<system_version>' (wording 2)."""
    q = question_v4(qid, doc)
    if _check_wording(wording) == 1:
        return f"q{q['version']}.s{q['system_version']}"
    return f"q{q['second']['version']}b.s{q['system_version']}"


def key_id_v4(qid: str, wording: int = 1) -> str:
    """The question id inside the cache key and the stats: 'K4' or 'K4b'."""
    return qid if _check_wording(wording) == 1 else qid + "b"


def key_v4(qid: str, inputs: Dict[str, Any], doc: Optional[dict] = None, wording: int = 1) -> str:
    doc = doc or load_questions_v4()
    return Q.cache_key(key_id_v4(qid, wording), key_version_v4(qid, doc, wording), doc["model"], doc["effort"],
                       Q.normalized_inputs(qid, inputs, doc))


def schema_v4(qid: str, doc: Optional[dict] = None) -> Tuple[dict, str]:
    """(the JSON schema, its name) for one question: its system's schema with the answer enum of the question."""
    doc = normalize_doc_v4(doc or load_questions_v4())
    q = question_v4(qid, doc)
    s = doc["systems"][str(q["system_version"])]
    schema = copy.deepcopy(s["schema"])
    schema.setdefault("properties", {}).setdefault("answer", {"type": "string"})["enum"] = list(answers_of(q))
    return schema, s["schema_name"]


# ----------------------------------------------------------------------------------------------- render

def _v3_shim(doc: dict, q: dict) -> dict:
    return {"system": doc["systems"]["1"]["system"], "questions": {q["id"]: q}}


def _fill(text: str, q: dict, inputs: Dict[str, Any]) -> Tuple[str, set]:
    """The text with its placeholders filled (choice values, follows choices, text inputs); and the text inputs
    used inline."""
    specs = {s["name"]: s for s in q["inputs"]}
    inputs = complete_inputs_v4(q, inputs)
    used = set()

    def one(m: "re.Match") -> str:
        name = m.group(1)
        if name in specs and specs[name]["type"] in ("choice", "text"):
            if specs[name]["type"] == "text":
                used.add(name)
            v = inputs.get(name)
            return m.group(0) if v is None else str(v)
        return m.group(0)
    return _PLACE.sub(one, text), used


def complete_inputs_v4(q: dict, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """The inputs with each `follows` choice filled from its source choice (when not given)."""
    out = dict(inputs or {})
    for s in q["inputs"]:
        fl = s.get("follows")
        if fl and out.get(s["name"]) is None and out.get(fl.get("input")) is not None:
            out[s["name"]] = fl["map"].get(out[fl["input"]])
    return out


def _input_lines(q: dict, inputs: Dict[str, Any], skip: set, example: bool = False) -> List[str]:
    """The input blocks. In an example (few-shot): message inputs and the choices it gives ("label: value")."""
    lines: List[str] = []
    for spec in q["inputs"]:
        name, typ = spec["name"], spec["type"]
        if example and typ == "choice" and inputs.get(name) is not None:
            lines += [f"{spec['label']}: {inputs[name]}"]
            continue
        if name in skip or typ == "choice" or (example and typ not in ("message", "messages")):
            continue
        v = inputs.get(name)
        if typ == "message":
            t = message_text(v)
            if t is None or not t.strip():
                continue
            lines += [spec["label"] + ":", "<<<", t, ">>>", ""]
        elif typ == "messages":
            items = [message_text(x) or "" for x in (v if isinstance(v, (list, tuple)) else ([v] if v else []))]
            if not items:
                continue
            lines += [spec["label"] + ":", "<<<", "\n---\n".join(items), ">>>", ""]
        else:
            if v is None:
                continue
            lines += [spec["label"] + ":", str(v), ""]
    return lines


def _answer_json(q: dict, sv: Any, ans: str, quote: str, missing: str = "") -> str:
    d: Dict[str, Any] = {"answer": ans, "quote": quote}
    if str(sv) != "1":
        d["missing"] = missing
    return json.dumps(d, ensure_ascii=False)


def render_v4(qid: str, inputs: Dict[str, Any], doc: Optional[dict] = None, wording: int = 1) -> Dict[str, str]:
    """The prompt {"system", "user"} of one question in wording 1 or 2. A system-1 question in wording 1 is exactly
    v3's Q.render. Message texts are shown as written (never cut)."""
    doc = normalize_doc_v4(doc or load_questions_v4())
    q = question_v4(qid, doc)
    sv = str(q["system_version"])
    inputs = complete_inputs_v4(q, inputs)
    if _check_wording(wording) == 1 and sv == "1":
        return Q.render(qid, inputs, _v3_shim(doc, q))
    if wording == 1:
        lines = [f"Question {qid} (version {q['version']}).", ""]
        raw_text = q["question"]
    else:
        lines = [f"Question {qid}b (version {q['second']['version']}).", ""]
        raw_text = q["second"]["question"]
    text, inline = _fill(raw_text, q, inputs)
    shots = q.get("few_shot") or []
    if shots:
        lines += ["Made-up examples (not from this conversation):", ""]
        for n, ex in enumerate(shots, 1):
            lines += [f"Example {n}:"]
            lines += _input_lines(q, ex["inputs"], set(), example=True)
            lines += ["Answer: " + _answer_json(q, sv, ex["answer"], ex.get("quote") or "", ex.get("missing") or ""),
                      ""]
        lines += ["The messages to judge:", ""]
    lines += _input_lines(q, inputs, inline)
    labels = {s["name"]: s["label"].split(",")[0] for s in q["inputs"]}
    src = " or ".join(labels[n] for n in q["quote_from"] if message_text(inputs.get(n)) or
                      (isinstance(inputs.get(n), list) and inputs.get(n)))
    ans = answers_of(q)
    if ans == YES_NO:
        how = f"Answer yes, no or unclear. For yes, the quote is copied exactly from {src or 'the message'}."
    else:
        main = [a for a in ans if a != "unclear"]
        how = (f"Answer {', '.join(main)} or unclear (these words replace yes / no in the answer field). For "
               f"{' or '.join(quote_needed_of(q))}, the quote is copied exactly from {src or 'the message'}.")
    lines += ["Question: " + text, how]
    if "missing" in (doc["systems"][sv].get("schema") or {}).get("properties", {}):
        lines.append(MISSING_LINE)
    return {"system": doc["systems"][sv]["system"], "user": "\n".join(lines)}


# ----------------------------------------------------------------------------------------------- the quote check (D12)

_SPLIT_V4 = re.compile(r"\.\.\.|[.,;:!?…—–\-\"'“”‘’«»()\[\]{}\r\n]")


def quote_pieces_v4(quote: Any) -> List[str]:
    """The pieces of a quote: split at any punctuation (. , ; : ! ? … — – - quotes, brackets, line breaks, '...'),
    each cleaned (v3 clean_quote) and in v3 quote_form; pieces shorter than 2 characters are dropped."""
    out = []
    for piece in _SPLIT_V4.split(str(quote or "")):
        q = quote_form(clean_quote(piece))
        if len(q) >= MIN_PIECE:
            out.append(q)
    return out


def quote_in_v4(quote: Any, texts: Sequence[Any]) -> bool:
    """True when the quote has at least one piece and every piece is a substring of the SAME text (quote_form)."""
    pieces = quote_pieces_v4(quote)
    if not pieces:
        return False
    for t in texts or []:
        if t:
            f = quote_form(t)
            if all(p in f for p in pieces):
                return True
    return False


def parse_answer_v4(text: Any, answers: Sequence[str] = YES_NO) -> Optional[dict]:
    """{"answer", "quote", "missing"} from the model's JSON text, or None when it is not that. "missing" is kept
    ("" when the answer has none)."""
    try:
        d = json.loads(text) if isinstance(text, str) else None
    except ValueError:
        return None
    if not isinstance(d, dict) or d.get("answer") not in tuple(answers) or not isinstance(d.get("quote", ""), str) \
            or not isinstance(d.get("missing", ""), str):
        return None
    return {"answer": d["answer"], "quote": d.get("quote", ""), "missing": d.get("missing", "")}


def answer_status_v4(answer: Any, quote: Any, bad_output: bool, sources: Sequence[Any],
                     q: Optional[dict] = None) -> str:
    """bad_output | unclear | <answer> | quote_failed. An answer of quote_needed (yes; K17 added / not_added) needs
    its quote in a source; another answer may have an empty quote, else its quote must be in a source too."""
    q = q or {}
    if answer not in answers_of(q) or bad_output:
        return "bad_output"
    if answer == "unclear":
        return "unclear"
    if answer in quote_needed_of(q):
        return answer if quote_in_v4(quote, sources) else "quote_failed"
    return answer if not clean_quote(quote) or quote_in_v4(quote, sources) else "quote_failed"


def saved_answer_v4(rec: dict, q: Optional[dict] = None) -> Tuple[Any, str, bool]:
    """(answer, quote, bad_output) of a saved record (v4 or v3): from its raw model text when it has one."""
    if isinstance(rec.get("raw"), str) or ("raw" in rec and rec.get("source") == "real"):
        parsed = parse_answer_v4(rec.get("raw"), answers_of(q or {}))
        if parsed is None:
            return None, "", True
        return parsed["answer"], parsed["quote"], False
    ans = rec.get("answer")
    return ans, rec.get("quote") or "", ans not in answers_of(q or {}) or bool(rec.get("bad_output"))


def saved_status_v4(rec: dict, sources: Optional[Sequence[Any]] = None, doc: Optional[dict] = None) -> str:
    """The status of a saved answer derived again with the v4 quote check (the stored status is not trusted)."""
    q = question_v4(str(rec.get("qid")), doc)
    if sources is None:
        inp = rec.get("input") or {}
        sources = []
        for n in q["quote_from"]:
            v = inp.get(n)
            sources += [x for x in v if x] if isinstance(v, list) else ([v] if v else [])
    ans, quote, bad = saved_answer_v4(rec, q)
    return answer_status_v4(ans, quote, bad, sources, q)


# ----------------------------------------------------------------------------------------------- stores

class ChainStore:
    """Read the v4 store first, then the v3 store (read-only: never written); write the v4 store only. So a question
    whose key equals v3's is answered from v3's saved answer, and only changed keys are asked."""

    def __init__(self, v4_store: Any, v3_store: Any):
        self.first = v4_store
        self.second = v3_store
        self.path = getattr(v4_store, "path", None)
        self.writable = getattr(v4_store, "writable", True)

    def get(self, key: str) -> Optional[dict]:
        rec = self.first.get(key)
        return rec if rec is not None else self.second.get(key)

    def store_of(self, key: str) -> Optional[str]:
        if self.first.get(key) is not None:
            return "v4"
        return "v3" if self.second.get(key) is not None else None

    def put(self, key: str, rec: dict) -> None:
        if self.second.get(key) is not None:
            raise RuntimeError(f"answer {key[:12]} is already saved in the v3 store (an answer is never repeated)")
        self.first.put(key, rec)

    def __len__(self) -> int:
        return len(set(self.first.keys()) | set(self.second.keys()))

    def keys(self) -> List[str]:
        return list(dict.fromkeys(list(self.first.keys()) + list(self.second.keys())))


def _stores(store: Any) -> List[Tuple[Any, bool]]:
    """(store, may be written) of a store and, for a ChainStore, of its parts."""
    if isinstance(store, ChainStore):
        return _stores(store.first) + [(s, False) for s, _ in _stores(store.second)]
    return [(store, True)]


# ----------------------------------------------------------------------------------------------- backends

class FakeBackendV4(Q.FakeBackend):
    """v3's fakes on the v4 file. policy: "yes" / "added" / "not_added" (with a valid quote: the first words of the
    first quote source), "no", "unclear", "not_said", "bad_quote", a dict, or a function(qid, inputs, norm) -> word or
    answer dict (as v3). second: the policy for wording 2 (default: the same policy). missing: the "missing" text."""
    QUOTED = ("yes", "added", "not_added")
    WORDS = ("yes", "no", "unclear", "bad_quote", "added", "not_added", "not_said")

    def __init__(self, policy: Any = "yes", default: str = "no", exhaustive: bool = False, second: Any = None,
                 missing: str = "", doc: Optional[dict] = None):
        for p in (policy, second):
            if isinstance(p, str) and p not in self.WORDS:
                raise ValueError(f"unknown fake policy {p!r}")
        self.policy = policy
        self.second = second
        self.default = default
        self.exhaustive = exhaustive
        self.missing = missing
        self.doc = doc
        self.calls = 0
        self.wordings: collections.Counter = collections.Counter()

    def _src(self, qid: str, inputs: Dict[str, Any], doc: Optional[dict]) -> List[str]:
        return [s for s in Q.quote_sources(qid, inputs, doc or self.doc or load_questions_v4()) if s]

    def _word_v4(self, word: str, qid: str, inputs: Dict[str, Any], doc: Optional[dict]) -> dict:
        if word in self.QUOTED:
            src = self._src(qid, inputs, doc)
            return {"answer": word, "quote": Q._first_words(src[0]) if src else "", "missing": ""}
        if word == "bad_quote":
            return {"answer": "yes", "quote": "zz this quote is in no message zz", "missing": ""}
        if word in ("no", "unclear", "not_said"):
            return {"answer": word, "quote": "", "missing": self.missing if word == "no" else ""}
        raise ValueError(f"unknown fake answer {word!r}")

    def answer(self, *, qid: str, inputs: Dict[str, Any], norm: Dict[str, Any], key: str, wording: int = 1,
               doc: Optional[dict] = None, **_: Any) -> dict:
        self.calls += 1
        self.wordings[wording] += 1
        p = self.second if (wording == 2 and self.second is not None) else self.policy
        if callable(p):
            out = p(qid, inputs, norm)
        elif isinstance(p, dict):
            src = self._src(qid, inputs, doc)
            out = p.get(key, p.get((qid, normalize_text(src[0]) if src else ""), self.default))
        else:
            out = p
        return self._word_v4(out, qid, inputs, doc) if isinstance(out, str) else dict(out)


FakeBackend = FakeBackendV4             # the runner takes getattr(module, "FakeBackend"): the v4-aware fakes


class RealBackendV4(Q.RealBackend):
    """Real answers (paid). Refuses unless approval_flag is True (set by the main chat after the user's approval of
    that exact step) and v3's check_real_mode passes (approval words, dollar and call budgets, network not
    blocked). Only answer() differs from v3: the schema of the question's system version and answers."""

    def __init__(self, approved: str, max_usd: float, max_calls: int, *, approval_flag: bool = False,
                 client: Any = None, doc: Optional[dict] = None, log: Any = None, attempts: int = 3,
                 sleep: Any = time.sleep):
        if approval_flag is not True:
            raise RealModeRefused("v4 real mode needs the main chat's approval flag (approval_flag=True), given "
                                  "only after the user's explicit approval of this paid step")
        super().__init__(approved, max_usd, max_calls, client=client, doc=doc or load_questions_v4(), log=log,
                         attempts=attempts, sleep=sleep)

    def answer(self, *, qid: str, prompt: Dict[str, str], schema: Optional[dict] = None,
               schema_name: Optional[str] = None, answers: Optional[Sequence[str]] = None, **_: Any) -> dict:
        if schema is None or schema_name is None:
            schema, schema_name = schema_v4(qid, self.doc)
        allowed = tuple(answers or schema.get("properties", {}).get("answer", {}).get("enum") or YES_NO)
        est = Q.estimate_tokens(prompt["system"] + prompt["user"]) + 80
        last: Optional[BaseException] = None
        for attempt in range(self.attempts):
            self.budget.reserve(est)                                           # raises BudgetExceeded
            t0 = time.time()
            try:
                resp = self.client().responses.create(
                    model=self.doc["model"],
                    input=[{"role": "system", "content": prompt["system"]},
                           {"role": "user", "content": prompt["user"]}],
                    reasoning={"effort": self.doc["effort"]},
                    max_output_tokens=Q.MAX_OUTPUT_TOKENS,
                    text={"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}})
            except Exception as e:                       # noqa: BLE001 - transient API errors: retried, counted
                last = e
                self.budget.spend(est * self.budget.pin)
                self.usage["failed_attempts"] += 1
                self.log(f"{qid}: attempt {attempt + 1} failed: {type(e).__name__}: {e}")
                self.sleep(min(30.0, 2.0 * 2 ** attempt))
                continue
            u = getattr(resp, "usage", None)
            tin = int(getattr(u, "input_tokens", 0) or 0)
            tout = int(getattr(u, "output_tokens", 0) or 0)
            reasoning = int(getattr(getattr(u, "output_tokens_details", None), "reasoning_tokens", 0) or 0)
            cached = int(getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0)
            cost = self.budget.cost(tin, tout)
            self.budget.spend(cost)
            for k, v in (("calls", 1), ("input_tokens", tin), ("output_tokens", tout),
                         ("reasoning_tokens", reasoning), ("cached_tokens", cached)):
                self.usage[k] += v
            text = getattr(resp, "output_text", None)
            parsed = parse_answer_v4(text, allowed)
            out = dict(parsed or {"answer": "unclear", "quote": "", "missing": ""})
            out.update(raw=text, bad_output=parsed is None, api_status=getattr(resp, "status", None),
                       usage={"input_tokens": tin, "output_tokens": tout, "reasoning_tokens": reasoning,
                              "cached_tokens": cached},
                       cost_usd=round(cost, 8), spent_usd=round(self.budget.spent, 8),
                       seconds=round(time.time() - t0, 3), model=self.doc["model"], effort=self.doc["effort"])
            self.log(f"{qid}: {out['answer']} (${cost:.6f}; spent ${self.budget.spent:.4f} of "
                     f"${self.budget.max_usd:.2f}; calls {self.budget.calls} of {self.budget.max_calls})")
            return out
        raise RealCallFailed(f"{qid}: {self.attempts} attempts failed: {last}")


# ----------------------------------------------------------------------------------------------- the hook

class StatsV4(Q.Stats):
    """v3's counts plus re-asks and unclear answers allowed (per question id)."""

    def __init__(self):
        super().__init__()
        self.reasks = collections.Counter()
        self.unclear_allowed = collections.Counter()

    def as_dict(self) -> dict:
        out = super().as_dict()
        for q in set(self.reasks) | set(self.unclear_allowed):
            out.setdefault(q, {"asks": 0, "cache_hits": 0, "calls": 0, "status": {}, "unclear_values": 0,
                               "no_message": 0})
        for q, d in out.items():
            d["reasks"] = self.reasks[q]
            d["unclear_allowed"] = self.unclear_allowed[q]
        return out


def _jsonable(x: Any) -> Any:
    try:
        return json.loads(json.dumps(x, sort_keys=True, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return str(x)


class QuestionsV4(Q.Questions):
    """The v4 answers hook (evaluate(..., answers=hook)). Asks each (question, wording, input) once."""
    supports_wording_v4 = True

    def __init__(self, backend: Any, store: Any = None, *, doc: Optional[dict] = None, keep_log: bool = True,
                 ask_log: Optional[str] = None):
        doc = normalize_doc_v4(doc or load_questions_v4())
        store = store if store is not None else MemoryStore()
        real = getattr(backend, "name", "") == "real"
        for s, may_write in _stores(store):
            p = getattr(s, "path", None)
            writes = may_write and getattr(s, "writable", True)
            if p and os.path.abspath(p) == V3_ANSWERS_PATH and writes:
                raise RealModeRefused(f"{Q.ANSWERS_REL} is v3's answers file: v4 never writes it (open it "
                                      f"read-only, as the second store of a ChainStore)")
            if p and os.path.abspath(p) == V4_ANSWERS_PATH and writes and not real:
                raise RealModeRefused(f"{V4_ANSWERS_REL} is written only in real mode (backend {backend!r})")
        super().__init__(backend, store, doc=doc, keep_log=keep_log)
        self.stats = StatsV4()
        self.ask_log_path = os.path.abspath(ask_log) if ask_log else None
        self.ask_lines: List[dict] = []
        self._ask_log_lock = threading.Lock()
        self._ev = threading.local()

    # ---- per-thread v4 events (re-asks, unclear allowed): the guard drains them per check
    def push_event_v4(self, ev: dict) -> None:
        if not hasattr(self._ev, "items"):
            self._ev.items = []
        self._ev.items.append(ev)

    def take_events_v4(self) -> List[dict]:
        items = list(getattr(self._ev, "items", []))
        self._ev.items = []
        return items

    def key(self, qid: str, inputs: Dict[str, Any], wording: int = 1) -> str:
        return key_v4(qid, inputs, self.doc, wording)

    def _log_ask(self, key: str, qid: str, wording: int, fact: Optional[str], part: Optional[str], cached: bool,
                 rec: dict) -> None:
        store_of = getattr(self.store, "store_of", None)
        line = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "key": key, "qid": qid,
                "wording": wording, "fact": fact, "part": part, "where": _jsonable(self.where), "cached": cached,
                "store": store_of(key) if callable(store_of) else None, "status": rec.get("status"),
                "answer": rec.get("answer")}
        with self._ask_log_lock:
            self.ask_lines.append(line)
            if self.ask_log_path:
                os.makedirs(os.path.dirname(self.ask_log_path), exist_ok=True)
                with open(self.ask_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(line, sort_keys=True, ensure_ascii=False) + "\n")
                    f.flush()

    def ask(self, qid: str, inputs: Dict[str, Any], *, fact: Optional[str] = None, part: Optional[str] = None,
            wording: int = 1) -> dict:
        """The saved answer of one question (wording 1 or 2) about these inputs; asked now if not saved yet. One
        ask-log line per ask, cached or not."""
        _check_wording(wording)
        inputs = complete_inputs_v4(question_v4(qid, self.doc), inputs)
        check_inputs_v4(qid, inputs, self.doc)
        norm = Q.normalized_inputs(qid, inputs, self.doc)
        sid = key_id_v4(qid, wording)
        key = Q.cache_key(sid, key_version_v4(qid, self.doc, wording), self.model, self.effort, norm)
        while True:
            with self._lock:
                self.stats.asks[sid] += 1
                rec = self.store.get(key)
                if rec is not None:
                    self.stats.hits[sid] += 1
                    if self.on_ask is not None:
                        self.on_ask(key, qid, fact, part, True)
                    out = self._as_read(qid, inputs, rec)
                    break
                ev = self._inflight.get(key)
                if ev is None:
                    ev = self._inflight[key] = threading.Event()
                    out = None
                    break
                self.stats.asks[sid] -= 1
            ev.wait()
        if out is not None:
            self._log_ask(key, qid, wording, fact, part, True, out)
            return out
        try:
            prompt = render_v4(qid, inputs, self.doc, wording)
            schema, schema_name = schema_v4(qid, self.doc)
            raw = self.backend.answer(qid=qid, inputs=inputs, norm=norm, key=key, prompt=prompt, fact=fact,
                                      part=part, wording=wording, schema=schema, schema_name=schema_name,
                                      answers=answers_of(question_v4(qid, self.doc)), doc=self.doc)
            rec = self._finish(qid, key, norm, inputs, prompt, raw, wording)
            with self._lock:
                self.store.put(key, rec)
                self.stats.calls[sid] += 1
                self.stats.status[sid][rec["status"]] += 1
                if self.keep_log:
                    self.log.append({"key": key, "qid": qid, "wording": wording, "fact": fact, "part": part,
                                     "where": self.where, "chars": len(prompt["system"]) + len(prompt["user"]),
                                     "chars_user": len(prompt["user"]), "status": rec["status"]})
                if self.on_ask is not None:
                    self.on_ask(key, qid, fact, part, False)
            self._log_ask(key, qid, wording, fact, part, False, rec)
            return rec
        finally:
            with self._lock:
                self._inflight.pop(key, None)
            ev.set()

    def _as_read(self, qid: str, inputs: Dict[str, Any], rec: dict) -> dict:
        """A saved answer (v4 or v3 store) with its status derived again with the v4 quote check; a copy when it
        changed (status_saved keeps the stored one). The store is never changed."""
        st = saved_status_v4(dict(rec, qid=qid), Q.quote_sources(qid, inputs, self.doc), self.doc)
        if st == rec.get("status"):
            return rec
        return dict(rec, status=st, status_saved=rec.get("status"))

    def _finish(self, qid: str, key: str, norm: Dict[str, Any], inputs: Dict[str, Any], prompt: Dict[str, str],
                raw: dict, wording: int = 1) -> dict:
        q = question_v4(qid, self.doc)
        ans = raw.get("answer")
        quote = raw.get("quote") or ""
        missing = raw.get("missing")
        status = answer_status_v4(ans, quote, bool(raw.get("bad_output")), Q.quote_sources(qid, inputs, self.doc),
                                  q)
        rec = {"key": key, "qid": qid, "qid_asked": key_id_v4(qid, wording), "wording": wording,
               "version": key_version_v4(qid, self.doc, wording), "model": self.model, "effort": self.effort,
               "input": norm, "answer": ans if ans in answers_of(q) else None, "quote": quote,
               "missing": missing if isinstance(missing, str) else "", "status": status,
               "source": getattr(self.backend, "name", "?"), "where_first": _jsonable(self.where),
               "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        if raw.get("bad_output"):
            rec["bad_output"] = True
        if getattr(self.backend, "name", "") == "real":
            rec.update(prompt_user=prompt["user"],
                       prompt_sha256=Q.sha256_text(prompt["system"] + "\n" + prompt["user"]),
                       **{k: raw[k] for k in ("raw", "usage", "cost_usd", "spent_usd", "seconds", "api_status")
                          if k in raw})
        return rec


def check_inputs_v4(qid: str, inputs: Dict[str, Any], doc: Optional[dict] = None) -> None:
    """v3's input check on the v4 file, plus: at least one message input is given."""
    doc = doc or load_questions_v4()
    Q.check_inputs(qid, inputs, doc)
    q = question_v4(qid, doc)
    if not any(message_text(inputs.get(s["name"])) or (isinstance(inputs.get(s["name"]), list)
                                                        and inputs.get(s["name"]))
               for s in q["inputs"] if s["type"] in ("message", "messages")):
        raise ValueError(f"{qid}: no message input is given")


# ----------------------------------------------------------------------------------------------- rendering the action

def action_line_v4(state: Any, tool: Optional[str], args: Dict[str, Any]) -> str:
    """K1v4's {action}: one short line: the tool phrase and the object id (+ item names for retail item tools,
    flight numbers for airline flight tools). No other details (they are code)."""
    args = dict(args or {})
    domain = getattr(state, "domain", None)
    tool = tool or "the pending call"
    phrase = (Q.RETAIL_PHRASE if domain == "retail" else Q.AIRLINE_PHRASE).get(tool, f"call {tool}")
    bits = [phrase]
    if domain == "retail":
        oid = args.get("order_id")
        if oid is not None:
            bits.append(str(oid))
        if tool in ("modify_pending_order_items", "exchange_delivered_order_items", "return_delivered_order_items"):
            order = Q._safe(lambda: state.db_get("order", oid)) if oid is not None else None
            names = []
            for it in args.get("item_ids") or []:
                name, _ = Q._safe(lambda: Q.item_options(state, it, order), (None, {}))
                names.append(name or f"item {it}")
            if names:
                bits.append("(" + ", ".join(names) + ")")
    else:
        rid = args.get("reservation_id")
        if rid is not None:
            bits.append(str(rid))
        if tool in ("book_reservation", "update_reservation_flights"):
            nums = [str(f.get("flight_number")) for f in args.get("flights") or [] if isinstance(f, dict)]
            if nums:
                bits.append("(flights " + ", ".join(nums) + ")")
    return " ".join(bits)


# ----------------------------------------------------------------------------------------------- the helpers

def _doc_of_v4(hook: Any) -> dict:
    d = getattr(hook, "doc", None)
    return d if isinstance(d, dict) and "systems" in d else load_questions_v4()


def _bump(hook: Any, counter: str, qid: str) -> None:
    st = getattr(hook, "stats", None)
    if st is not None and isinstance(getattr(st, counter, None), collections.Counter):
        st.bump(counter, qid)


def _event(ctx: Any, hook: Any, ev: dict) -> None:
    ctx.note(ev)
    push = getattr(hook, "push_event_v4", None)
    if callable(push):
        push(ev)


def _build_inputs_v4(ctx: Any, qid: str, messages: Sequence[Any], focus: Optional[str], items: Optional[str],
                     doc: dict) -> Optional[Dict[str, Any]]:
    """The question's inputs (v3's _build_inputs on the v4 file, with render action_line). None when a required
    message is missing or empty, or no message input is given at all (no message, no yes)."""
    q = question_v4(qid, doc)
    msg_specs = [s for s in q["inputs"] if s["type"] in ("message", "messages")]
    if len(messages) > len(msg_specs):
        raise ValueError(f"{qid} takes at most {len(msg_specs)} messages, got {len(messages)}")
    if focus is not None and not any(s["type"] == "text" and s.get("from") == "call" for s in q["inputs"]):
        raise ValueError(f"{qid} has no call text, so focus= does not apply")
    drop = len(msg_specs) - len(messages)
    specs = []
    for s in msg_specs:
        if drop > 0 and s.get("optional"):
            drop -= 1
            continue
        specs.append(s)
    view = getattr(ctx, "view", None)
    inputs: Dict[str, Any] = {}
    for s, m in zip(specs, list(messages) + [None] * (len(specs) - len(messages))):
        if s["type"] == "messages":
            xs = list(m) if isinstance(m, (list, tuple)) else ([] if m is None else [m])
            if xs and all(isinstance(x, int) and not isinstance(x, bool) for x in xs):
                xs = sorted(xs)
            texts = [t for t in (message_text(x, view) for x in xs) if t and t.strip()]
            if texts:
                inputs[s["name"]] = texts
            elif not s.get("optional"):
                return None
        else:
            t = message_text(m, view)
            if t and t.strip():
                inputs[s["name"]] = t
            elif not s.get("optional"):
                return None
    if not inputs:
        return None
    tool = Q._pending_tool(ctx)
    for s in q["inputs"]:
        if s["type"] == "text" and s.get("from") == "call":
            if s["name"] == "trip":
                inputs[s["name"]] = Q.trip_text(ctx.state, ctx.args or {})
            elif s.get("render") == "action_line" or (s["name"] == "action" and "render" not in s
                                                       and focus is None):
                inputs[s["name"]] = action_line_v4(ctx.state, tool, ctx.args or {})
            elif s.get("render") == Q.LISTING_RENDER and focus is None:
                inputs[s["name"]] = Q.render_listing(ctx.state, tool, ctx.args or {})
            else:
                inputs[s["name"]] = Q.render_action(ctx.state, tool, ctx.args or {}, focus)
        elif s["type"] == "text" and s.get("from") == "domain":
            inputs[s["name"]] = doc["domain_texts"][s["name"]][ctx.domain]
        elif s["type"] == "choice" and not s.get("follows"):
            v = items
            if v is None and s.get("from") == "call":
                v = (ctx.args or {}).get(s["name"])
            if v not in s["values"]:
                raise ValueError(f"{qid}: items= (or the call's {s['name']!r}) must be one of {s['values']}, "
                                 f"not {v!r}")
            inputs[s["name"]] = v
    if items is not None and not any(s["type"] == "choice" and not s.get("follows") for s in q["inputs"]):
        raise ValueError(f"{qid} has no choice input, so items= does not apply")
    return complete_inputs_v4(q, inputs)


def _ask_rec_v4(ctx: Any, hook: Any, qid: str, inputs: Dict[str, Any], wording: int) -> dict:
    if wording == 1:
        rec = hook.ask(qid, inputs, fact=ctx.fact, part=ctx.part_id)
    else:
        rec = hook.ask(qid, inputs, fact=ctx.fact, part=ctx.part_id, wording=2)
    ctx.note({"question": key_id_v4(qid, wording), "key": (rec.get("key") or "")[:16], "status": rec.get("status"),
              "quote": rec.get("quote"), "missing": rec.get("missing")})
    return rec


def _ask_with_reask(ctx: Any, hook: Any, qid: str, messages: Sequence[Any], focus: Optional[str] = None,
                    items: Optional[str] = None) -> Optional[dict]:
    """Wording 1; on unclear / failed quote / bad output, wording 2 on the same input (noted). None: no message."""
    doc = _doc_of_v4(hook)
    inputs = _build_inputs_v4(ctx, qid, messages, focus, items, doc)
    if inputs is None:
        _bump(hook, "no_message", qid)
        ctx.note({"question": qid, "answer": None, "why": "no message to ask about"})
        return None
    rec = _ask_rec_v4(ctx, hook, qid, inputs, 1)
    if rec.get("status") in UNRESOLVED and not getattr(hook, "standin", False):
        rec2 = _ask_rec_v4(ctx, hook, qid, inputs, 2)
        _bump(hook, "reasks", qid)
        _event(ctx, hook, {"v4": "reask", "qid": qid, "fact": ctx.fact, "part": ctx.part_id,
                           "key1": rec.get("key"), "key2": rec2.get("key"),
                           "status1": rec.get("status"), "status2": rec2.get("status")})
        return rec2
    return rec


def _yes_no_only(qid: str, doc: dict) -> None:
    if answers_of(question_v4(qid, doc)) != YES_NO:
        raise ValueError(f"{qid} is not a yes/no question (answers {answers_of(question_v4(qid, doc))})")


def _still_unclear(ctx: Any, hook: Any, qid: str, on_unclear: Any, detail: str) -> bool:
    """D10 after the second wording: block (raise UseBlockingValue, counted) or allow (return on_unclear, logged)."""
    mode = question_v4(qid, _doc_of_v4(hook))["on_unclear"]
    if on_unclear is None:
        if mode == "allow":
            raise ValueError(f"{qid}: questions_v4.json says on_unclear 'allow', so the expression must give "
                             f"on_unclear=<the value that allows>")
        _bump(hook, "blocking", qid)
        raise F.UseBlockingValue(detail, kind="unclear")
    if not isinstance(on_unclear, bool):
        raise TypeError(f"{qid}: on_unclear must be True or False, not {on_unclear!r}")
    if mode != "allow":
        raise ValueError(f"{qid}: questions_v4.json says on_unclear 'block', but the expression gives "
                         f"on_unclear={on_unclear!r}")
    _bump(hook, "unclear_allowed", qid)
    _event(ctx, hook, {"v4": "unclear_allowed", "fact": ctx.fact, "qid": qid, "part": ctx.part_id,
                       "value": on_unclear, "detail": detail})
    return on_unclear


def h_ask_v4(ctx: Any, qid: str, *messages: Any, focus: Optional[str] = None, items: Optional[str] = None,
             on_unclear: Optional[bool] = None) -> bool:
    """ask_v4(qid, m1[, m2], focus=None, items=None, on_unclear=None): one yes/no question, re-asked once with the
    second wording when unclear; still unclear: the question's policy (D10)."""
    hook = Q._hook(ctx)
    _yes_no_only(qid, _doc_of_v4(hook))
    rec = _ask_with_reask(ctx, hook, qid, messages, focus, items)
    if rec is None:
        return False
    st = rec.get("status")
    if st in ("yes", "no"):
        return st == "yes"
    return _still_unclear(ctx, hook, qid, on_unclear,
                          f"{qid}: {st} after the second wording (answer {rec.get('answer')!r}, "
                          f"quote {rec.get('quote')!r})")


def h_ask_first_yes_v4(ctx: Any, qid: str, candidates: Any, focus: Optional[str] = None,
                       items: Optional[str] = None, limit: Optional[int] = None,
                       on_unclear: Optional[bool] = None) -> bool:
    """ask_first_yes_v4(qid, candidates, focus=None, items=None, limit=None, on_unclear=None): newest candidate
    first; True at the first yes (each candidate re-asked once when unclear). No yes and a still-unclear candidate:
    the question's policy (D10). No yes otherwise (or no candidate): False."""
    hook = Q._hook(ctx)
    _yes_no_only(qid, _doc_of_v4(hook))
    if candidates is None:
        candidates = []
    if not isinstance(candidates, (list, tuple)):
        raise TypeError(f"ask_first_yes_v4: candidates must be a list, not {type(candidates).__name__}")
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError(f"ask_first_yes_v4: limit must be an integer >= 1, not {limit!r}")
        candidates = list(candidates)[:limit]
    unclear: Optional[str] = None
    found = False
    for c in candidates:
        rec = _ask_with_reask(ctx, hook, qid, Q._as_messages(c), focus, items)
        if rec is None:
            continue
        st = rec.get("status")
        if st == "yes":
            found = True
            if not hook.exhaustive:
                return True
        elif st != "no":
            unclear = unclear or f"{qid}: {st} after the second wording (quote {rec.get('quote')!r})"
    if found:
        return True
    if unclear is not None:
        return _still_unclear(ctx, hook, qid, on_unclear, f"no yes, and an unclear answer on the way: {unclear}")
    return False


def _kinds(db_kinds: Any) -> set:
    if db_kinds is None:
        return set()
    if isinstance(db_kinds, dict):
        return {k for k, v in db_kinds.items() if v}
    if isinstance(db_kinds, str):
        return {db_kinds}
    return {k for k in db_kinds if isinstance(k, str)}


_CANCEL_WORD = re.compile(r"\bcancel")
_DELAY_WORD = re.compile(r"\bdelay")


def h_offer_kind_v4(ctx: Any, reply: Any, kind: str, db_kinds: Any = None) -> bool:
    """offer_kind_v4(reply, kind[, db_kinds]): the reply's offer is about a `kind` flight. The database decides when
    exactly one kind is in db_kinds; else K12's quote words (cancel / delay; K12 asked with the re-ask); still
    undecided: True (the blocking value of both offer facts)."""
    if kind not in ("cancelled", "delayed"):
        raise ValueError(f"offer_kind_v4: kind must be 'cancelled' or 'delayed', not {kind!r}")
    hook = Q._hook(ctx)
    if getattr(hook, "standin", False):
        return Q._standin_value(ctx, hook)
    ks = _kinds(db_kinds)
    c, d = "cancelled" in ks, "delayed" in ks
    if c != d:
        ctx.note({"offer_kind": kind, "decided_by": "database", "db_kinds": sorted(ks)})
        return c if kind == "cancelled" else d
    rec = _ask_with_reask(ctx, hook, "K12", (reply,))
    if rec is None:
        return False
    st = rec.get("status")
    if st not in ("yes", "no"):
        _still_unclear(ctx, hook, "K12", None, f"K12: {st} after the second wording")
    if st == "no":
        return False
    qt = normalize_text(clean_quote(rec.get("quote")))
    cw, dw = bool(_CANCEL_WORD.search(qt)), bool(_DELAY_WORD.search(qt))
    if cw != dw:
        ctx.note({"offer_kind": kind, "decided_by": "quote words", "db_kinds": sorted(ks)})
        return cw if kind == "cancelled" else dw
    ctx.note({"offer_kind": kind, "decided_by": "undecided: blocking value", "db_kinds": sorted(ks)})
    return True


_COMP_NOUN = re.compile(r"\b(?:certificates?|vouchers?|credit(?!\s*cards?)|credits|compensation|gesture|goodwill)\b")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")


def offer_amounts_v4(text: Any) -> List[Tuple[float, str, int, int]]:
    """(amount, sentence, start, end) of every dollar amount in a sentence of the text that holds a compensation
    noun (normalized text)."""
    s = normalize_text(text)
    out = []
    for sent in _SENTENCE_END.split(s):
        if sent and _COMP_NOUN.search(sent):
            for amount, a, b in Q.amounts_in(sent):
                out.append((amount, sent, a, b))
    return out


def h_offer_amount_ok_v4(ctx: Any, reply: Any, rate: Any, passenger_counts: Any) -> bool:
    """offer_amount_ok_v4(reply, rate, passenger_counts): code only (no question). True when no offer sentence
    names an amount, or one amount = rate x a passenger count, or = rate with 'per passenger / each / per person'
    within 40 characters."""
    text = message_text(reply, getattr(ctx, "view", None)) or ""
    found = offer_amounts_v4(text)
    if not found:
        ctx.note({"offer_amount": "no dollar amount in an offer sentence"})
        return True
    rate = float(rate)
    counts = [int(n) for n in (passenger_counts or []) if isinstance(n, (int, float)) and not isinstance(n, bool)]
    for amount, sent, start, end in found:
        if any(abs(amount - rate * n) < 0.005 for n in counts):
            return True
        if abs(amount - rate) < 0.005 and Q._PER_PERSON.search(sent[max(0, start - 40): end + 40]):
            return True
    ctx.note({"offer_amount": [a for a, _, _, _ in found], "rate": rate, "passenger_counts": counts})
    return False


INSURANCE_WORD = {"yes": "added", "no": "not_added"}


def h_insurance_stated_v4(ctx: Any, candidates: Any, value: Any) -> bool:
    """insurance_stated_v4(candidates, value): K17 on each candidate, newest first (a user message, or a pair
    [agent message, reply]); the first decided answer (added / not_added) must equal the call's value ('yes' ->
    added, 'no' -> not_added). not_said or still unclear -> the next older candidate. None decided -> False."""
    hook = Q._hook(ctx)
    if getattr(hook, "standin", False):
        return Q._standin_value(ctx, hook)
    want = INSURANCE_WORD.get(value)
    if want is None:
        ctx.note({"insurance": None, "why": f"the call's insurance is {value!r}"})
        return False
    if candidates is None:
        candidates = []
    if not isinstance(candidates, (list, tuple)):
        raise TypeError(f"insurance_stated_v4: candidates must be a list, not {type(candidates).__name__}")
    unclear = False
    for c in candidates:
        rec = _ask_with_reask(ctx, hook, "K17", Q._as_messages(c))
        if rec is None:
            continue
        st = rec.get("status")
        if st in ("added", "not_added"):
            ctx.note({"insurance": st, "expected": want, "quote": rec.get("quote")})
            return st == want
        unclear = unclear or st in UNRESOLVED
    if unclear:
        _bump(hook, "blocking", "K17")
    ctx.note({"insurance": "not decided", "expected": want, "unclear_on_the_way": unclear})
    return False


HELPERS_V4 = (
    ("ask_v4", h_ask_v4, 2, 3, ("focus", "items", "on_unclear"), "question",
     "one v4 tiny yes/no question about one or two messages, re-asked once when unclear"),
    ("ask_first_yes_v4", h_ask_first_yes_v4, 2, 2, ("focus", "items", "limit", "on_unclear"), "question",
     "the first yes among candidates, newest first, each re-asked once when unclear"),
    ("offer_kind_v4", h_offer_kind_v4, 2, 3, (), "question",
     "the kind of the offer: the database's kinds first, else K12's quote words"),
    ("offer_amount_ok_v4", h_offer_amount_ok_v4, 3, 3, (), "structure",
     "the dollar amounts of the reply's offer sentences (code)"),
    ("insurance_stated_v4", h_insurance_stated_v4, 2, 2, (), "question",
     "K17: the first decided insurance answer equals the call's insurance"),
)


def register_helpers_v4() -> List[str]:
    """Register the v4 question helpers; registering again changes nothing."""
    for name, func, lo, hi, kws, source, doc in HELPERS_V4:
        F.register_name(name, func, lo, hi, kws, source=source, doc=doc)
    return [h[0] for h in HELPERS_V4]


register_helpers_v4()


# ----------------------------------------------------------------------------------------------- CLI

def sample_inputs_v4(qid: str, doc: Optional[dict] = None) -> Dict[str, Any]:
    doc = doc or load_questions_v4()
    q = question_v4(qid, doc)
    out: Dict[str, Any] = {}
    for s in q["inputs"]:
        if s["type"] == "message":
            out[s["name"]] = f"sample {s.get('who', 'user')} message for {s['name']}: yes, please go ahead."
        elif s["type"] == "messages":
            out[s["name"]] = ["sample user message one", "sample user message two"]
        elif s["type"] == "choice":
            out[s["name"]] = s["values"][0]
        elif s.get("from") == "domain":
            dt = doc["domain_texts"][s["name"]]
            out[s["name"]] = dt.get("retail") or next(iter(dt.values()))
        else:
            out[s["name"]] = "sample action text"
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -B -m state_tracker.v4.questions_v4",
                                 description="Check the v4 tiny questions file and render the questions (no LLM call).")
    ap.add_argument("--path", default=None, help="the questions file (default state_tracker/v4/questions_v4.json)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="check the file and render every question in both wordings")
    g.add_argument("--show", metavar="K", help="print one rendered question (both wordings) with made-up inputs")
    a = ap.parse_args(argv)
    block_network()
    doc = load_questions_v4(a.path)
    if a.show:
        for w in (1, 2):
            p = render_v4(a.show, sample_inputs_v4(a.show, doc), doc, w)
            print(f"=== wording {w}\nSYSTEM:\n" + p["system"] + "\n\nUSER:\n" + p["user"] + "\n")
        return 0
    for qid in question_ids_v4(doc):
        q = question_v4(qid, doc)
        inputs = sample_inputs_v4(qid, doc)
        h = QuestionsV4(FakeBackendV4("yes" if answers_of(q) == YES_NO else "added", doc=doc), doc=doc)
        rec = h.ask(qid, inputs)
        n = [len(render_v4(qid, inputs, doc, w)["user"]) for w in (1, 2)]
        print(f"{qid} v{q['version']} s{q['system_version']} on_unclear={q['on_unclear']} "
              f"few_shot={len(q.get('few_shot') or [])}: prompt chars {n}; fake -> {rec['status']}; "
              f"key version {key_version_v4(qid, doc)}")
    print(f"questions: {len(doc['questions'])}; systems {sorted(doc['systems'])}; network events "
          f"{len(network_events())}")
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.exit(main())
