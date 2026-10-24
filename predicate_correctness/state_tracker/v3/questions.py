"""Tracker v3, part 8: the tiny questions (docs/planning/tracker_v3/p8.md).

Where a fact needs the meaning of words, code picks one or two messages (p7's pickers), and one narrow yes/no
question about them decides the question part. The questions K1-K16 are in state_tracker/v3/questions_v3.json.

    from state_tracker.v3 import questions as Q
    hook = Q.Questions(Q.FakeBackend("yes"))                 # the answers hook: evaluate(..., answers=hook)
    rec = hook.ask("K4", {"message": "Can you check my wife's order?"})
    rec["status"]        yes | no | unclear | quote_failed | bad_output
    Q.value_of(rec)      True (yes) / False (no) / raises UseBlockingValue(kind="unclear")

Fixed rules (p8.md):
  - the answer format is {"answer": "yes|no|unclear", "quote": "..."};
  - the quote must be a substring of the message the question names (quote_from), after the view's normalization
    on both sides (p7's message_view.normalize: accents removed, curly quotes straight, markdown removed, spaces
    collapsed, lower case); since the K2 fix (p12) the marks ** and __ and backticks are removed first and every
    whitespace run (line breaks too) is one space (quote_form). The status of a saved answer is derived again from
    the saved answer (its raw model text) each time it is read (saved_status), so a fix of the check applies to
    saved answers without a new call; the answers file is never changed.
    A yes needs a non-empty quote; a no may have an empty quote. Otherwise the answer counts as "unclear"
    (status quote_failed, counted apart);
  - "unclear" takes the fact's blocking value: the helper raises facts_format_v3.UseBlockingValue(kind="unclear");
    the evaluator records it as a problem, and the caller counts it;
  - every answer is saved by sha256(question id, version, model, effort, normalized input), asked once per message
    and question, never repeated. Inputs are never cut by a length limit. Model: gpt-6-luna, low effort (Q3).

The question helpers (registered on import with facts_format_v3.register_name(..., source="question"), so they may be
called only in question parts):
  ask(qid, m1[, m2], focus=None, items=None)                 one question about one or two messages -> True / False
  ask_first_yes(qid, candidates, focus=None, items=None, also=None, limit=None)
                       candidates: messages, or [message, message] pairs (K1: [listing, reply]), newest first. True
                       at the first yes. With also='K2', a pair counts only if K2 is yes on its first message too.
                       limit: at most that many candidates. No yes: an unclear on the way gives the blocking value,
                       else False. No candidate: False.
  offer_kind(reply, kind, cancel_msgs, delay_msgs)           K12's quote decides the offer's kind; else K8 / K9
  offer_amount_ok(reply, rate, passenger_counts)             the dollar amounts in K12's quote (or the reply)
A message is a ref of p7's message view (an int: view.text(ref)), a text (e.g. args['content'], the pending reply),
or a dict with a "text" / "content" / "raw" text. With fewer messages than the question's message inputs, the
optional inputs are left out first (K1 with one message: the reply). A required message that is missing or empty
gives False with no question (no message, no yes). The call's details (K1: render_action; K2 version 2:
render_listing, the input's "render": "listing_lines"), the trip (K15) and the tool list (K13) are rendered by code from
the pending call, the database copy and the domain (render_action, render_listing, trip_text, questions_v3.json
domain_texts). K2 v2 (docs/planning/tracker_v3/k2_fix.md): one line per argument the user can check, each with the
forms that count (product name or item id; new item id or each option that changes; payment kind and last four;
every address field; flight number and date; cabin; passenger name and date of birth; bags total and paid). focus= picks one choice of the call for K1 / K2 ('insurance', 'trip', 'payment');
items= is K3's 'exchanged' or 'modified'.

Answer sources (backends) of the hook Questions(backend, store):
  FakeBackend("yes" | "no" | "unclear" | "bad_quote" | table | function, exhaustive=False)
          deterministic fakes; "yes" quotes the first words of the named message (a valid quote). exhaustive=True
          makes ask_first_yes ask every candidate (the dry run's upper bound).
  RealBackend(approved, max_usd, max_calls)    p12 only, with the user's approval. Refuses to start without the
          approval words, a dollar budget, a call budget, or when this process blocks the network. Stops hard
          (BudgetExceeded) before a call that could pass a budget. List price logged per call. Answers are written to
          output/eval_v3/questions_answers.jsonl (ANSWERS_PATH) only in real mode.
          Threads (p12's --workers): one hook, its store and one budget may be shared by several threads; a key
          is asked once even when two threads need it at the same time (the second waits for the first's answer);
          once the budget stop fires it stays fired, so no new call starts (Budget.stopped).
  SavedBackend()                               reads saved answers only (p12's re-run without the judge); a missing
          answer raises AnswerNotSaved.
StandInAnswers(values) is a separate hook for p9's meaning = saved_judge: the saved judge value of the fact stands in
for every question part of that fact (no question, no quote).

block_network() installs an audit hook (sys.addaudithook) that refuses every network socket (connect, name lookups,
an internet socket, urllib / http.client requests) and counts the attempts (network_events()). Fake modes use it.

CLI (run from predicate_correctness/):
    python -B -m state_tracker.v3.questions --check            check the file, render every question (fake inputs)
    python -B -m state_tracker.v3.questions --show K1          print one rendered question
main() checks the eval v2 manifest first (state_tracker/v3/frozen.py). Standard library only (the real backend
imports openai and azure.identity of the venv when it runs). Imports no scoring module and no gold code.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import socket
import sys
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    __package__ = "state_tracker.v3"

from state_tracker import paths                          # noqa: E402
from state_tracker.v3 import facts_format_v3 as F        # noqa: E402

QUESTIONS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "questions_v3.json")
ANSWERS_REL = "output/eval_v3/questions_answers.jsonl"
ANSWERS_PATH = os.path.join(paths.PC_DIR, *ANSWERS_REL.split("/"))
RUNNER_UTILS = os.path.join(paths.FROM_SA, "runner", "utility", "utils.py")   # read as text only (the endpoint)

ANSWERS = ("yes", "no", "unclear")
STATUSES = ("yes", "no", "unclear", "quote_failed", "bad_output")
FOCUS = (None, "insurance", "trip", "payment")
HARD_CEILING_USD = 95.0          # the plan's total cap (progress.md); a budget above it is refused as a typo
RESERVE_OUTPUT_TOKENS = 4000     # the budget stop reserves this many output tokens for the next call
MAX_OUTPUT_TOKENS = 16000        # as the judge (repro_core/config.json); the answer is never cut short on purpose
REQUEST_TIMEOUT_S = 420
FAKE_QUOTE_WORDS = 8


# ----------------------------------------------------------------------------------------------- errors

class QuestionsFileError(ValueError):
    """questions_v3.json is not well formed (or a text changed without a new version / hash)."""


class NetworkBlocked(RuntimeError):
    """A network socket was refused by the audit hook of block_network()."""


class RealModeRefused(RuntimeError):
    """Real mode cannot start: no approval words, no budget, or the network is blocked in this process."""


class BudgetExceeded(RuntimeError):
    """The next real call could pass the dollar or the call budget: a hard stop (never a fact value)."""


class AnswerNotSaved(RuntimeError):
    """SavedBackend: the answer of this question and input is not in the answers file."""


class RealCallFailed(RuntimeError):
    """A real call failed on every attempt."""


# ----------------------------------------------------------------------------------------------- the questions file

def canonical(x: Any) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def question_hash(q: dict) -> str:
    """sha256 of a question's canonical JSON without its text_sha256 field."""
    return sha256_text(canonical({k: v for k, v in q.items() if k != "text_sha256"}))


def system_hash(doc: dict) -> str:
    return sha256_text(canonical({"system": doc["system"], "system_version": doc["system_version"],
                                  "schema": doc["schema"], "schema_name": doc["schema_name"]}))


INPUT_TYPES = ("message", "messages", "text", "choice")
RENDERS = ("listing_lines",)     # a call text's renderer other than render_action (K2 v2: render_listing)
_QID = re.compile(r"^K[1-9][0-9]*$")


def check_doc(doc: Any) -> List[str]:
    """Problems with a questions file (empty: fine)."""
    p: List[str] = []
    if not isinstance(doc, dict):
        return ["the file is not a JSON object"]
    for f in ("_about", "answer_format", "domain_texts", "effort", "model", "price", "questions", "schema",
              "schema_name", "schema_version", "system", "system_version", "system_sha256"):
        if f not in doc:
            p.append(f"missing top field {f!r}")
    if p:
        return p
    if doc["model"] != "gpt-6-luna" or doc["effort"] != "low":
        p.append("model must be gpt-6-luna with effort low (Q3)")
    if doc["system_sha256"] != system_hash(doc):
        p.append("system_sha256 differs: the system text or schema changed (give a new system_version and hash)")
    if set(doc["schema"].get("properties", {})) != {"answer", "quote"}:
        p.append("the schema must have exactly answer and quote")
    for qid, q in doc["questions"].items():
        pre = f"{qid}:"
        if not _QID.match(qid) or q.get("id") != qid:
            p.append(f"{pre} id must be K<n> and equal its key")
        for f in ("facts", "id", "inputs", "question", "quote_from", "text_sha256", "version"):
            if f not in q:
                p.append(f"{pre} missing field {f!r}")
        if any(f not in q for f in ("inputs", "question", "quote_from", "version", "text_sha256")):
            continue
        if not isinstance(q["version"], int) or q["version"] < 1:
            p.append(f"{pre} version must be an integer >= 1")
        names = [i.get("name") for i in q["inputs"]]
        if len(set(names)) != len(names):
            p.append(f"{pre} an input name is listed twice")
        for i in q["inputs"]:
            if i.get("type") not in INPUT_TYPES:
                p.append(f"{pre} input {i.get('name')!r}: type must be one of {INPUT_TYPES}")
            if not i.get("label"):
                p.append(f"{pre} input {i.get('name')!r}: needs a label")
            if i.get("type") == "choice" and not i.get("values"):
                p.append(f"{pre} input {i.get('name')!r}: a choice needs values")
            if "render" in i and (i.get("render") not in RENDERS or i.get("type") != "text" or i.get("from") != "call"):
                p.append(f"{pre} input {i.get('name')!r}: render must be one of {RENDERS} on a call text")
        msg_inputs = [i["name"] for i in q["inputs"] if i.get("type") in ("message", "messages")]
        if not q["quote_from"] or any(n not in msg_inputs for n in q["quote_from"]):
            p.append(f"{pre} quote_from must name message inputs")
        for name in re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", q["question"]):
            if name not in names:
                p.append(f"{pre} the question text uses {{{name}}}, which is not an input")
        if q["text_sha256"] != question_hash(q):
            p.append(f"{pre} text_sha256 differs: the question changed (give a new version and hash)")
    return p


_DOC: Dict[str, dict] = {}


def load_questions(path: Optional[str] = None) -> dict:
    """The questions file (checked; loaded once per path). Raises QuestionsFileError."""
    path = path or QUESTIONS_PATH
    if path not in _DOC:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        problems = check_doc(doc)
        if problems:
            raise QuestionsFileError(f"{path}: " + "; ".join(problems))
        _DOC[path] = doc
    return _DOC[path]


def question(qid: str, doc: Optional[dict] = None) -> dict:
    doc = doc or load_questions()
    if qid not in doc["questions"]:
        raise KeyError(f"unknown question {qid!r} (known: {sorted(doc['questions'], key=_qkey)})")
    return doc["questions"][qid]


def _qkey(qid: str) -> int:
    return int(qid[1:]) if qid[1:].isdigit() else 0


def question_ids(doc: Optional[dict] = None) -> List[str]:
    return sorted((doc or load_questions())["questions"], key=_qkey)


# ----------------------------------------------------------------------------------------------- normalization

_MV: Dict[str, Any] = {}


def _view_normalize() -> Callable[[Any], str]:
    """p7's message_view.normalize, imported when first needed (importing the view registers p7's helpers; this
    module's own import does not)."""
    if "normalize" not in _MV:
        from state_tracker.v3 import message_view as MV
        _MV["normalize"] = MV.normalize
    return _MV["normalize"]


def normalize_text(text: Any) -> str:
    """The view's own normalization (p7: message_view.normalize): accents removed, curly quotes and dashes
    straight, markdown removed, spaces collapsed, lower case. None gives ""."""
    if text is None:
        return ""
    return _view_normalize()(text)


def squash(s: str) -> str:
    return " ".join(s.split())


_QUOTE_EDGES = "\"'“”‘’ \t\n"


def clean_quote(quote: Any) -> str:
    """The quote as checked: surrounding quote marks, spaces and '...' removed."""
    q = str(quote or "").strip(_QUOTE_EDGES)
    for edge in ("...", "…"):
        while q.startswith(edge):
            q = q[len(edge):].strip(_QUOTE_EDGES)
        while q.endswith(edge):
            q = q[: -len(edge)].strip(_QUOTE_EDGES)
    return q


_QUOTE_MARKS = re.compile(r"\*\*|__|`")


def quote_form(text: Any) -> str:
    """A text as the quote check compares it (p12 K2 fix): the markdown marks ** and __ and every backtick removed,
    then the view's normalization, then all whitespace (line breaks too) collapsed to one space."""
    if text is None:
        return ""
    return squash(normalize_text(_QUOTE_MARKS.sub("", str(text))))


_QUOTE_SPLIT = re.compile(r";|\u2026|\.\.\.|\r\n|\r|\n")


def quote_pieces(quote: Any) -> List[str]:
    """The pieces of a quote (p12 round 2): split at ';', '\u2026', '...' and line breaks, each piece cleaned
    (clean_quote) and put in quote_form(); empty pieces dropped. A quote without those marks is one piece."""
    out = []
    for piece in _QUOTE_SPLIT.split(str(quote or "")):
        q = quote_form(clean_quote(piece))
        if q:
            out.append(q)
    return out


def quote_in(quote: Any, texts: Iterable[Any]) -> bool:
    """True when the quote has at least one non-empty piece (quote_pieces) and every piece is a substring of the
    same text, both in quote_form() (markdown marks and whitespace ignored). A K2 answer about several lines may
    join pieces of message A with ';', '...' or line breaks."""
    pieces = quote_pieces(quote)
    if not pieces:
        return False
    for t in texts:
        if t:
            f = quote_form(t)
            if all(p in f for p in pieces):
                return True
    return False


def answer_status(answer: Any, quote: Any, bad_output: bool, sources: Sequence[Any]) -> str:
    """The status of one answer: bad_output | unclear | yes | no | quote_failed (a yes needs its quote in a source;
    a no may have an empty quote, else its quote must be in a source too)."""
    if answer not in ANSWERS or bad_output:
        return "bad_output"
    if answer == "unclear":
        return "unclear"
    if answer == "yes":
        return "yes" if quote_in(quote, sources) else "quote_failed"
    return "no" if not clean_quote(quote) or quote_in(quote, sources) else "quote_failed"


def saved_answer(rec: dict) -> Tuple[Any, str, bool]:
    """(answer, quote, bad_output) of a saved record, from its raw model text when it has one (real answers), else
    from its answer and quote fields (fake answers)."""
    if isinstance(rec.get("raw"), str) or ("raw" in rec and rec.get("source") == "real"):
        parsed = parse_answer(rec.get("raw"))
        if parsed is None:
            return None, "", True
        return parsed["answer"], parsed["quote"], False
    ans = rec.get("answer")
    return ans, rec.get("quote") or "", ans not in ANSWERS or bool(rec.get("bad_output"))


def saved_status(rec: dict, sources: Optional[Sequence[Any]] = None, doc: Optional[dict] = None) -> str:
    """The status of a saved answer, derived again at read time with the current quote check (the stored status is
    not trusted: a fix of the check then applies to saved answers without a new call). sources: the quote's source
    texts; by default the record's own normalized input (its quote_from inputs)."""
    if sources is None:
        q = question(str(rec.get("qid")), doc)
        inp = rec.get("input") or {}
        sources = []
        for n in q["quote_from"]:
            v = inp.get(n)
            sources += [x for x in v if x] if isinstance(v, list) else ([v] if v else [])
    ans, quote, bad = saved_answer(rec)
    return answer_status(ans, quote, bad, sources)


# ----------------------------------------------------------------------------------------------- the network block

_NET: Dict[str, Any] = {"installed": False, "events": []}
_NET_LOCK = threading.Lock()
NET_EVENTS = frozenset({"socket.connect", "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr",
                        "socket.getnameinfo", "socket.sendto", "socket.sendmsg", "urllib.Request",
                        "http.client.connect", "http.client.send"})
_INET = {-1, int(socket.AF_INET), int(getattr(socket, "AF_INET6", socket.AF_INET))}


def _net_hook(event: str, args: tuple) -> None:
    hit = event in NET_EVENTS
    if not hit and event == "socket.__new__" and len(args) >= 2:
        try:
            hit = int(args[1]) in _INET
        except (TypeError, ValueError):
            hit = True
    if hit:
        with _NET_LOCK:
            _NET["events"].append(event)
        raise NetworkBlocked(f"network refused by the v3 question block (audit event {event})")


def block_network() -> None:
    """Install the audit hook that refuses every network socket (once per process; it cannot be removed)."""
    with _NET_LOCK:
        if _NET["installed"]:
            return
        _NET["installed"] = True
    sys.addaudithook(_net_hook)


def network_blocked() -> bool:
    return bool(_NET["installed"])


def network_events() -> List[str]:
    """The refused network attempts so far (the dry run must report 0)."""
    with _NET_LOCK:
        return list(_NET["events"])


# ----------------------------------------------------------------------------------------------- inputs and prompts

def message_text(m: Any, view: Any = None) -> Optional[str]:
    """The text of a message: a text, a ref (an int: view.text(ref), p7's message view), or a dict with a text
    field. None when there is none."""
    if m is None or isinstance(m, bool):
        return None
    if isinstance(m, str):
        return m
    if isinstance(m, int):
        if view is None:
            raise F.MissingInput(f"message ref {m}: the message view is needed (view=...)")
        t = view.text(m)
        return t if isinstance(t, str) else None
    if isinstance(m, dict):
        for k in ("text", "content", "raw"):
            v = m.get(k)
            if isinstance(v, str):
                return v
        return None
    return None


def normalized_inputs(qid: str, inputs: Dict[str, Any], doc: Optional[dict] = None) -> Dict[str, Any]:
    """The inputs as they enter the cache key: every text normalized; a list of messages as a list."""
    q = question(qid, doc)
    out: Dict[str, Any] = {}
    for spec in q["inputs"]:
        name = spec["name"]
        v = inputs.get(name)
        if spec["type"] == "messages":
            out[name] = [normalize_text(message_text(x)) for x in (v or [])]
        else:
            out[name] = normalize_text(message_text(v) if spec["type"] == "message" else v)
    return out


def check_inputs(qid: str, inputs: Dict[str, Any], doc: Optional[dict] = None) -> None:
    """ValueError when an input is unknown, a required one is missing, or a choice is not one of its values."""
    q = question(qid, doc)
    specs = {s["name"]: s for s in q["inputs"]}
    for k in inputs:
        if k not in specs:
            raise ValueError(f"{qid}: unknown input {k!r} (inputs: {list(specs)})")
    for name, s in specs.items():
        v = inputs.get(name)
        empty = v is None or (s["type"] == "messages" and not v) or (s["type"] != "messages"
                                                                      and not (message_text(v) or "").strip())
        if empty and not s.get("optional"):
            raise ValueError(f"{qid}: input {name!r} is required")
        if s["type"] == "choice" and v not in s["values"]:
            raise ValueError(f"{qid}: input {name!r} must be one of {s['values']}, not {v!r}")


def cache_key(qid: str, version: Any, model: str, effort: str, norm_inputs: Dict[str, Any]) -> str:
    """sha256(question id, version, model, effort, normalized input)."""
    return sha256_text(canonical({"q": qid, "v": version, "model": model, "effort": effort, "input": norm_inputs}))


def key_version(qid: str, doc: Optional[dict] = None) -> str:
    """The version in the cache key: the question's version and the system prompt's version."""
    doc = doc or load_questions()
    return f"q{question(qid, doc)['version']}.s{doc['system_version']}"


def render(qid: str, inputs: Dict[str, Any], doc: Optional[dict] = None) -> Dict[str, str]:
    """The prompt {"system", "user"} of one question. Message texts are shown as written (never cut); the cache key
    uses their normalized form."""
    doc = doc or load_questions()
    q = question(qid, doc)
    lines = [f"Question {qid} (version {q['version']}).", ""]
    values: Dict[str, str] = {}
    for spec in q["inputs"]:
        name, typ = spec["name"], spec["type"]
        v = inputs.get(name)
        if typ == "choice":
            values[name] = str(v)
            continue
        if typ == "message":
            t = message_text(v)
            if t is None or not t.strip():
                continue                                   # an optional message that is not there
            lines += [spec["label"] + ":", "<<<", t, ">>>", ""]
        elif typ == "messages":
            items = [message_text(x) or "" for x in (v or [])]
            if not items:
                continue
            lines += [spec["label"] + ":", "<<<", "\n---\n".join(items), ">>>", ""]
        else:
            lines += [spec["label"] + ":", str(v), ""]
    text = q["question"]
    for name, val in values.items():
        text = text.replace("{" + name + "}", val)
    labels = {s["name"]: s["label"].split(",")[0] for s in q["inputs"]}
    src = " or ".join(labels[n] for n in q["quote_from"] if message_text(inputs.get(n)) or
                      (isinstance(inputs.get(n), list) and inputs.get(n)))
    lines += ["Question: " + text,
              f"Answer yes, no or unclear. For yes, the quote is copied exactly from {src or 'the message'}."]
    return {"system": doc["system"], "user": "\n".join(lines)}


def quote_sources(qid: str, inputs: Dict[str, Any], doc: Optional[dict] = None) -> List[str]:
    """The texts the quote must come from (raw; the check normalizes)."""
    q = question(qid, doc)
    spec = {s["name"]: s for s in q["inputs"]}
    out: List[str] = []
    for n in q["quote_from"]:
        v = inputs.get(n)
        if spec[n]["type"] == "messages":
            out += [message_text(x) or "" for x in (v or [])]
        else:
            t = message_text(v)
            if t:
                out.append(t)
    return out


def estimate_tokens(text: str) -> int:
    """Characters / 4 (an estimate; no tokenizer of the model is available offline)."""
    return (len(text) + 3) // 4


# ----------------------------------------------------------------------------------------------- answers: the store

class MemoryStore:
    """Saved answers in memory (fake modes and tests)."""
    path: Optional[str] = None
    writable = True

    def __init__(self):
        self._d: Dict[str, dict] = {}

    def get(self, key: str) -> Optional[dict]:
        return self._d.get(key)

    def put(self, key: str, rec: dict) -> None:
        if key in self._d:
            raise RuntimeError(f"answer {key[:12]} is already saved (an answer is never repeated)")
        self._d[key] = rec

    def __len__(self) -> int:
        return len(self._d)

    def keys(self) -> List[str]:
        return list(self._d)


class JsonlStore(MemoryStore):
    """Saved answers in a JSONL file: one line per answer, appended and flushed at once; read at start. The answers
    file of the project (ANSWERS_PATH) is written only by a hook whose backend is real (Questions checks it)."""

    def __init__(self, path: str, writable: bool = True):
        super().__init__()
        self.path = os.path.abspath(path)
        self.writable = writable
        self.bad_lines = 0
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        self.bad_lines += 1           # a line cut by a crash: the answer is asked again
                        continue
                    if isinstance(rec, dict) and isinstance(rec.get("key"), str):
                        self._d.setdefault(rec["key"], rec)

    def put(self, key: str, rec: dict) -> None:
        if not self.writable:
            raise RuntimeError(f"{self.path}: the store is read-only")
        super().put(key, rec)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())


# ----------------------------------------------------------------------------------------------- answers: backends

def _first_words(text: str, n: int = FAKE_QUOTE_WORDS) -> str:
    return " ".join(normalize_text(text).split()[:n])


class FakeBackend:
    """Deterministic fake answers. policy: "yes" (with a valid quote: the first words of the named message), "no",
    "unclear", "bad_quote" (yes with a quote that is in no message), a dict {cache key or (qid, normalized first quote
    source): answer dict or answer word} with `default` for the rest, or a function(qid, inputs, norm) -> answer dict
    or word. exhaustive=True: ask_first_yes asks every candidate (for the dry run's upper bound)."""
    name = "fake"

    def __init__(self, policy: Any = "yes", default: str = "no", exhaustive: bool = False):
        if isinstance(policy, str) and policy not in ("yes", "no", "unclear", "bad_quote"):
            raise ValueError(f"unknown fake policy {policy!r}")
        self.policy = policy
        self.default = default
        self.exhaustive = exhaustive
        self.calls = 0

    def _word(self, word: str, qid: str, inputs: Dict[str, Any]) -> dict:
        if word == "yes":
            src = quote_sources(qid, inputs)
            return {"answer": "yes", "quote": _first_words(src[0]) if src else ""}
        if word == "bad_quote":
            return {"answer": "yes", "quote": "zz this quote is in no message zz"}
        if word in ("no", "unclear"):
            return {"answer": word, "quote": ""}
        raise ValueError(f"unknown fake answer {word!r}")

    def answer(self, *, qid: str, inputs: Dict[str, Any], norm: Dict[str, Any], key: str, **_: Any) -> dict:
        self.calls += 1
        p = self.policy
        if callable(p):
            out = p(qid, inputs, norm)
        elif isinstance(p, dict):
            src = quote_sources(qid, inputs)
            out = p.get(key, p.get((qid, normalize_text(src[0]) if src else ""), self.default))
        else:
            out = p
        return self._word(out, qid, inputs) if isinstance(out, str) else dict(out)


class SavedBackend:
    """Answers from the store only (p12's re-run with meaning = tiny). A missing answer raises AnswerNotSaved."""
    name = "saved"
    exhaustive = False

    def answer(self, *, qid: str, key: str, **_: Any) -> dict:
        raise AnswerNotSaved(f"{qid}: answer {key[:16]}... is not saved")


def check_real_mode(approved: Any, max_usd: Any, max_calls: Any) -> Tuple[str, float, int]:
    """The guards of real mode. Raises RealModeRefused unless: the user's approval words are given (a real text, not
    a placeholder), a dollar budget 0 < max_usd <= HARD_CEILING_USD, a call budget max_calls >= 1, and this process
    does not block the network."""
    if not isinstance(approved, str) or len(approved.strip()) < 8 or re.search(r"[<>]", approved) \
            or approved.strip().lower() in ("yes", "approved", "ok", "proceed", "go ahead"):
        raise RealModeRefused("real mode needs --approved \"<the user's own approval words for this paid step>\" "
                              "(at least 8 characters, not a placeholder)")
    try:
        usd = float(max_usd)
    except (TypeError, ValueError):
        raise RealModeRefused("real mode needs a dollar budget (--max-usd)") from None
    if not 0 < usd <= HARD_CEILING_USD or usd != usd:
        raise RealModeRefused(f"the dollar budget must be > 0 and <= {HARD_CEILING_USD} (got {max_usd!r})")
    if isinstance(max_calls, bool) or not isinstance(max_calls, int) or max_calls < 1:
        raise RealModeRefused(f"real mode needs a call budget (--max-calls, an integer >= 1; got {max_calls!r})")
    if network_blocked():
        raise RealModeRefused("this process blocks the network (block_network() ran): real mode cannot start here")
    return approved.strip(), usd, max_calls


class Budget:
    """The hard stop of real mode: a dollar and a call budget at the logged list price."""

    def __init__(self, max_usd: float, max_calls: int, price: Dict[str, float]):
        self.max_usd = float(max_usd)
        self.max_calls = int(max_calls)
        self.pin = price["input_per_m"] / 1e6
        self.pout = price["output_per_m"] / 1e6
        self.spent = 0.0
        self.calls = 0
        self.stopped: Optional[str] = None       # set once the stop fired: no later call starts (thread-safe)
        self._lock = threading.Lock()

    def worst_next(self, est_input_tokens: int) -> float:
        return est_input_tokens * self.pin + RESERVE_OUTPUT_TOKENS * self.pout

    def stop(self, reason: str) -> None:
        """Fire the stop by hand (e.g. another worker stopped): every later reserve() raises BudgetExceeded."""
        with self._lock:
            self.stopped = self.stopped or reason

    def reserve(self, est_input_tokens: int) -> None:
        """Count one call, or raise BudgetExceeded if it could pass a budget. Once the stop fired, it stays: no new
        call starts afterwards, even a smaller one that would still fit (several threads share one budget)."""
        with self._lock:
            if self.stopped:
                raise BudgetExceeded(f"the budget stop already fired: {self.stopped}")
            if self.calls + 1 > self.max_calls:
                self.stopped = f"call budget reached: {self.calls} of {self.max_calls} calls made"
                raise BudgetExceeded(self.stopped)
            nxt = self.worst_next(est_input_tokens)
            if self.spent + nxt > self.max_usd:
                self.stopped = (f"dollar budget: spent ${self.spent:.4f}, the next call could cost up to "
                                f"${nxt:.4f}, budget ${self.max_usd:.2f}")
                raise BudgetExceeded(self.stopped)
            self.calls += 1

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return input_tokens * self.pin + output_tokens * self.pout

    def spend(self, usd: float) -> None:
        with self._lock:
            self.spent += usd


def runner_endpoint(path: str = RUNNER_UTILS) -> str:
    """The Azure endpoint of the runner copy's client (read as text; the copy is never imported)."""
    with open(path, encoding="utf-8") as f:
        m = re.search(r'^endpoint\s*=\s*"([^"]+)"', f.read(), re.M)
    if not m:
        raise RealModeRefused(f"no endpoint in {path}")
    return m.group(1)


def make_client(timeout: float = REQUEST_TIMEOUT_S):
    """The Azure AI Foundry client, built like the runner copy's (utility/utils.py: endpoint + Managed Identity),
    with a timeout and no hidden retries. Needs the venv (openai, azure.identity). Only RealBackend calls it."""
    from azure.identity import ManagedIdentityCredential, get_bearer_token_provider   # venv only
    from openai import OpenAI                                                          # venv only
    provider = get_bearer_token_provider(ManagedIdentityCredential(), "https://ai.azure.com/.default")

    class _Token:
        def __call__(self):
            return provider()

        def __str__(self):
            return provider()

    return OpenAI(base_url=runner_endpoint(), api_key=_Token(), timeout=timeout, max_retries=0)


def parse_answer(text: Any) -> Optional[dict]:
    """{"answer", "quote"} from the model's JSON text, or None when it is not that."""
    try:
        d = json.loads(text) if isinstance(text, str) else None
    except ValueError:
        return None
    if not isinstance(d, dict) or d.get("answer") not in ANSWERS or not isinstance(d.get("quote", ""), str):
        return None
    return {"answer": d["answer"], "quote": d.get("quote", "")}


class RealBackend:
    """Real answers (p12 only, never run by p8). See check_real_mode() for the guards and Budget for the stop."""
    name = "real"
    exhaustive = False

    def __init__(self, approved: str, max_usd: float, max_calls: int, *, client: Any = None,
                 doc: Optional[dict] = None, log: Optional[Callable[[str], None]] = None, attempts: int = 3,
                 sleep: Callable[[float], None] = time.sleep):
        self.approved, usd, calls = check_real_mode(approved, max_usd, max_calls)
        self.doc = doc or load_questions()
        self.price = {"input_per_m": self.doc["price"]["input_per_m"],
                      "output_per_m": self.doc["price"]["output_per_m"]}
        self.budget = Budget(usd, calls, self.price)
        self._client = client
        self._client_lock = threading.Lock()
        self.log = log or (lambda s: None)
        self.attempts = attempts
        self.sleep = sleep
        self.usage = collections.Counter()

    def client(self):
        with self._client_lock:
            if self._client is None:
                self._client = make_client()
            return self._client

    def answer(self, *, qid: str, prompt: Dict[str, str], **_: Any) -> dict:
        est = estimate_tokens(prompt["system"] + prompt["user"]) + 60          # + the schema
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
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                    text={"format": {"type": "json_schema", "name": self.doc["schema_name"],
                                     "schema": self.doc["schema"], "strict": True}})
            except Exception as e:                       # noqa: BLE001 - transient API errors: retried, counted
                last = e
                self.budget.spend(est * self.budget.pin)          # counted as if the input was billed
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
            parsed = parse_answer(text)
            out = dict(parsed or {"answer": "unclear", "quote": ""})
            out.update(raw=text, bad_output=parsed is None, api_status=getattr(resp, "status", None),
                       usage={"input_tokens": tin, "output_tokens": tout, "reasoning_tokens": reasoning,
                              "cached_tokens": cached},
                       cost_usd=round(cost, 8), spent_usd=round(self.budget.spent, 8),
                       seconds=round(time.time() - t0, 3), model=self.doc["model"], effort=self.doc["effort"])
            self.log(f"{qid}: {out['answer']} (${cost:.6f}; spent ${self.budget.spent:.4f} of "
                     f"${self.budget.max_usd:.2f}; calls {self.budget.calls} of {self.budget.max_calls})")
            return out
        raise RealCallFailed(f"{qid}: {self.attempts} attempts failed: {last}")


# ----------------------------------------------------------------------------------------------- answers: the hook

class Stats:
    """Counts of the hook: asks (with cache hits), new calls, outcomes, unclear values raised by the helpers."""

    def __init__(self):
        self.asks = collections.Counter()
        self.hits = collections.Counter()
        self.calls = collections.Counter()
        self.status = collections.defaultdict(collections.Counter)      # qid -> status -> new calls
        self.blocking = collections.Counter()                           # qid -> unclear values raised
        self.no_message = collections.Counter()                         # qid -> asked with no message (False)
        self._lock = threading.Lock()

    def bump(self, counter: str, qid: str, n: int = 1) -> None:
        """counter[qid] += n under a lock (the helpers run in several threads with --workers)."""
        with self._lock:
            getattr(self, counter)[qid] += n

    def as_dict(self) -> dict:
        qs = sorted(set(self.asks) | set(self.calls) | set(self.blocking) | set(self.no_message), key=_qkey)
        return {q: {"asks": self.asks[q], "cache_hits": self.hits[q], "calls": self.calls[q],
                    "status": dict(self.status[q]), "unclear_values": self.blocking[q],
                    "no_message": self.no_message[q]} for q in qs}


class Questions:
    """The answers hook given to facts_format_v3.evaluate(..., answers=hook). Asks each (question, input) once."""
    standin = False

    def __init__(self, backend: Any, store: Any = None, *, doc: Optional[dict] = None, keep_log: bool = True):
        self.doc = doc or load_questions()
        self.backend = backend
        self.store = store if store is not None else MemoryStore()
        if getattr(self.store, "path", None) and os.path.abspath(self.store.path) == ANSWERS_PATH \
                and getattr(self.store, "writable", True) and getattr(backend, "name", "") != "real":
            raise RealModeRefused(f"{ANSWERS_REL} is written only in real mode (backend {backend!r})")
        self.model = self.doc["model"]
        self.effort = self.doc["effort"]
        self.stats = Stats()
        self.log: List[dict] = []                  # one entry per new call (the dry run counts them)
        self._tl = threading.local()               # `where` is per thread (one hook, several worker threads)
        self.on_ask: Optional[Callable[[str, str, Optional[str], Optional[str], bool], None]] = None
        #                                           on_ask(key, qid, fact, part, cached): every ask (the dry run)
        self.keep_log = keep_log
        self._lock = threading.Lock()
        self._inflight: Dict[str, threading.Event] = {}

    @property
    def where(self) -> Any:
        """Set by the caller (e.g. the conversation key); one value per thread."""
        return getattr(self._tl, "where", None)

    @where.setter
    def where(self, value: Any) -> None:
        self._tl.where = value

    @property
    def exhaustive(self) -> bool:
        return bool(getattr(self.backend, "exhaustive", False))

    def key(self, qid: str, inputs: Dict[str, Any]) -> str:
        return cache_key(qid, key_version(qid, self.doc), self.model, self.effort,
                         normalized_inputs(qid, inputs, self.doc))

    def ask(self, qid: str, inputs: Dict[str, Any], *, fact: Optional[str] = None, part: Optional[str] = None
            ) -> dict:
        """The saved answer of one question about these inputs; asked now if it is not saved yet."""
        check_inputs(qid, inputs, self.doc)
        norm = normalized_inputs(qid, inputs, self.doc)
        key = cache_key(qid, key_version(qid, self.doc), self.model, self.effort, norm)
        while True:
            with self._lock:
                self.stats.asks[qid] += 1
                rec = self.store.get(key)
                if rec is not None:
                    self.stats.hits[qid] += 1
                    if self.on_ask is not None:
                        self.on_ask(key, qid, fact, part, True)
                    return self._as_read(qid, inputs, rec)
                ev = self._inflight.get(key)
                if ev is None:
                    ev = self._inflight[key] = threading.Event()
                    break
                self.stats.asks[qid] -= 1               # counted again when the other thread's answer is read
            ev.wait()
        try:
            prompt = render(qid, inputs, self.doc)
            raw = self.backend.answer(qid=qid, inputs=inputs, norm=norm, key=key, prompt=prompt, fact=fact,
                                      part=part)
            rec = self._finish(qid, key, norm, inputs, prompt, raw)
            with self._lock:
                self.store.put(key, rec)
                self.stats.calls[qid] += 1
                self.stats.status[qid][rec["status"]] += 1
                if self.keep_log:
                    self.log.append({"key": key, "qid": qid, "fact": fact, "part": part, "where": self.where,
                                     "chars": len(prompt["system"]) + len(prompt["user"]),
                                     "chars_user": len(prompt["user"]), "status": rec["status"]})
                if self.on_ask is not None:
                    self.on_ask(key, qid, fact, part, False)
            return rec
        finally:
            with self._lock:
                self._inflight.pop(key, None)
            ev.set()

    def _as_read(self, qid: str, inputs: Dict[str, Any], rec: dict) -> dict:
        """A saved answer as read: its status derived again from the saved answer (the raw model text when there is
        one) with the current quote check. The same record when the status is unchanged; else a copy with the new
        status and the stored one as status_saved (the store itself is never changed)."""
        st = saved_status(rec, quote_sources(qid, inputs, self.doc), self.doc)
        if st == rec.get("status"):
            return rec
        return dict(rec, status=st, status_saved=rec.get("status"))

    def _finish(self, qid: str, key: str, norm: Dict[str, Any], inputs: Dict[str, Any], prompt: Dict[str, str],
                raw: dict) -> dict:
        ans = raw.get("answer")
        quote = raw.get("quote") or ""
        status = answer_status(ans, quote, bool(raw.get("bad_output")), quote_sources(qid, inputs, self.doc))
        rec = {"key": key, "qid": qid, "version": key_version(qid, self.doc), "model": self.model,
               "effort": self.effort, "input": norm, "answer": ans if ans in ANSWERS else None, "quote": quote,
               "status": status, "source": getattr(self.backend, "name", "?"),
               "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        if raw.get("bad_output"):
            rec["bad_output"] = True                     # kept, so the status read again stays bad_output
        if getattr(self.backend, "name", "") == "real":
            rec.update(prompt_user=prompt["user"], prompt_sha256=sha256_text(prompt["system"] + "\n" + prompt["user"]),
                       **{k: raw[k] for k in ("raw", "usage", "cost_usd", "spent_usd", "seconds", "api_status")
                          if k in raw})
        return rec


def value_of(rec: dict) -> bool:
    """yes -> True, no -> False; unclear, a failed quote or a bad output -> UseBlockingValue(kind='unclear')."""
    st = rec.get("status")
    if st == "yes":
        return True
    if st == "no":
        return False
    raise F.UseBlockingValue(f"{rec.get('qid')}: {st} (answer {rec.get('answer')!r}, quote {rec.get('quote')!r})",
                             kind="unclear")


class StandInAnswers:
    """p9's meaning = saved_judge: the saved judge value of a fact stands in for the answers of its question parts.
    values: {fact: True | False | None}; None (the judge said unknown) or a missing fact gives an unclear answer.
    No question is asked and no quote is checked."""
    standin = True
    exhaustive = False

    def __init__(self, values: Dict[str, Optional[bool]]):
        self.values = dict(values)
        self.stats = Stats()
        self.where: Any = None

    def value_for(self, fact: Optional[str]) -> Optional[bool]:
        v = self.values.get(fact)
        return v if isinstance(v, bool) else None

    def ask(self, qid: str, inputs: Dict[str, Any], *, fact: Optional[str] = None, part: Optional[str] = None
            ) -> dict:
        self.stats.asks[qid] += 1
        v = self.value_for(fact)
        st = "unclear" if v is None else ("yes" if v else "no")
        return {"key": None, "qid": qid, "answer": st, "quote": "", "status": st, "source": "standin"}


# ----------------------------------------------------------------------------------------------- rendering the call

RETAIL_PHRASE = {
    "cancel_pending_order": "cancel the pending order",
    "modify_pending_order_address": "change the shipping address of the pending order",
    "modify_pending_order_payment": "change the payment method of the pending order",
    "modify_pending_order_items": "change items of the pending order to other options",
    "exchange_delivered_order_items": "exchange items of the delivered order for other options",
    "return_delivered_order_items": "return items of the delivered order",
    "modify_user_address": "change the user's default address",
    "transfer_to_human_agents": "transfer the user to a human agent",
}
AIRLINE_PHRASE = {
    "book_reservation": "book a new reservation",
    "update_reservation_flights": "change the flights of the reservation",
    "update_reservation_baggages": "change the checked bags of the reservation",
    "update_reservation_passengers": "change the passengers of the reservation",
    "cancel_reservation": "cancel the reservation",
    "send_certificate": "send a certificate to the user",
    "transfer_to_human_agents": "transfer the user to a human agent",
}
ADDRESS_KEYS = ("address1", "address2", "city", "state", "country", "zip")


def _safe(f: Callable[[], Any], default: Any = None) -> Any:
    try:
        return f()
    except (KeyError, IndexError, TypeError, AttributeError, ValueError):
        return default


def _options(opts: Any) -> str:
    if isinstance(opts, dict) and opts:
        return " (" + ", ".join(f"{k}: {v}" for k, v in opts.items()) + ")"
    return ""


def _payment_text(state: Any, pid: Any) -> str:
    pm = _safe(lambda: state.db_get("payment_method", pid))
    if not isinstance(pm, dict):
        return f"payment method {pid}"
    src = pm.get("source")
    if src == "credit_card":
        brand = pm.get("brand") or ""
        return f"credit card {brand} ending in {pm.get('last_four')} ({pid})".replace("  ", " ")
    if src == "gift_card":
        return f"gift card ({pid})"
    if src == "paypal":
        return f"PayPal ({pid})"
    if src == "certificate":
        return f"certificate ({pid})"
    return f"{src or 'payment method'} ({pid})"


def _retail_item(state: Any, item_id: Any, order: Any = None) -> str:
    if isinstance(order, dict):
        for it in order.get("items") or []:
            if isinstance(it, dict) and it.get("item_id") == item_id:
                return f"{it.get('name')}{_options(it.get('options'))} [item {item_id}]"
    v = _safe(lambda: state.db_get("variant", item_id))
    if isinstance(v, dict):
        prod = _safe(lambda: state.db_get("product", v.get("product_id")))
        name = prod.get("name") if isinstance(prod, dict) else "product"
        return f"{name}{_options(v.get('options'))} [item {item_id}]"
    return f"item {item_id}"


def _address(args: Dict[str, Any]) -> str:
    return ", ".join(str(args[k]) for k in ADDRESS_KEYS if args.get(k) not in (None, ""))


def _airports(state: Any) -> Dict[str, str]:
    rows = _safe(lambda: state.db_all("airport"), []) or []
    return {r.get("code"): r.get("city") for r in rows if isinstance(r, dict)}


def _place(code: Any, airports: Dict[str, str]) -> str:
    city = airports.get(code)
    return f"{city} ({code})" if city else str(code)


def trip_text(state: Any, args: Dict[str, Any]) -> str:
    """The booking's trip in plain words (K15, K1 with focus='trip')."""
    airports = _airports(state)
    kind = {"one_way": "one way", "round_trip": "round trip"}.get(args.get("flight_type"), str(args.get("flight_type")))
    return f"a {kind} trip from {_place(args.get('origin'), airports)} to {_place(args.get('destination'), airports)}"


def _flights(state: Any, flights: Any) -> List[str]:
    out = []
    for fl in flights or []:
        if not isinstance(fl, dict):
            out.append(str(fl))
            continue
        num, date = fl.get("flight_number"), fl.get("date")
        base = _safe(lambda: state.db_get("flight", num))
        route = f" ({base.get('origin')} to {base.get('destination')})" if isinstance(base, dict) else ""
        out.append(f"{num} on {date}{route}")
    return out


def _passengers(ps: Any) -> List[str]:
    out = []
    for p in ps or []:
        if isinstance(p, dict):
            out.append(f"{p.get('first_name')} {p.get('last_name')} (date of birth {p.get('dob')})")
        else:
            out.append(str(p))
    return out


def _generic(args: Dict[str, Any]) -> List[str]:
    return [f"- {k}: {json.dumps(v, ensure_ascii=False, sort_keys=True) if not isinstance(v, str) else v}"
            for k, v in sorted(args.items())]


def render_action(state: Any, tool: Optional[str], args: Dict[str, Any], focus: Optional[str] = None) -> str:
    """The pending call in plain words, with the forms the user sees (product names and options, payment kinds and
    last four digits, flight numbers and dates, cities). focus: None (the whole call), 'insurance', 'trip' or
    'payment' (only that choice). Deterministic: the same call on the same database gives the same text."""
    if focus not in FOCUS:
        raise ValueError(f"focus must be one of {FOCUS}, not {focus!r}")
    args = dict(args or {})
    domain = getattr(state, "domain", None)
    tool = tool or "the pending call"
    if focus == "insurance":
        ins = args.get("insurance")
        word = {"yes": "yes (the user buys travel insurance)", "no": "no (the user does not buy travel insurance)"}
        return f"travel insurance for this booking: {word.get(ins, str(ins))}"
    if focus == "trip":
        return trip_text(state, args)
    if focus == "payment":
        pid = args.get("payment_id", args.get("payment_method_id"))
        what = {"update_reservation_flights": f"the flight change of reservation {args.get('reservation_id')}",
                "update_reservation_baggages": f"the bag change of reservation {args.get('reservation_id')}",
                }.get(tool, f"this {tool} call")
        return f"pay for (or be refunded for) {what} with {_payment_text(state, pid)}"
    phrase = (RETAIL_PHRASE if domain == "retail" else AIRLINE_PHRASE).get(tool, f"call {tool}")
    lines = [f"{phrase} (tool {tool})"]
    try:
        lines += _detail_lines(state, domain, tool, args)
    except (KeyError, IndexError, TypeError, AttributeError, ValueError):
        lines += _generic(args)
    return "\n".join(lines)


def _detail_lines(state: Any, domain: Optional[str], tool: str, args: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    if domain == "retail":
        oid = args.get("order_id")
        order = _safe(lambda: state.db_get("order", oid)) if oid is not None else None
        if oid is not None:
            out.append(f"- order: {oid}")
        if tool == "cancel_pending_order":
            out.append(f"- reason: {args.get('reason')}")
        elif tool in ("modify_pending_order_address", "modify_user_address"):
            if tool == "modify_user_address":
                out.append(f"- user: {args.get('user_id')}")
            out.append(f"- new address: {_address(args)}")
        elif tool == "modify_pending_order_payment":
            out.append(f"- new payment method: {_payment_text(state, args.get('payment_method_id'))}")
        elif tool in ("modify_pending_order_items", "exchange_delivered_order_items"):
            olds, news = list(args.get("item_ids") or []), list(args.get("new_item_ids") or [])
            for i in range(max(len(olds), len(news))):
                a = _retail_item(state, olds[i], order) if i < len(olds) else "(none)"
                b = _retail_item(state, news[i]) if i < len(news) else "(none)"
                out.append(f"- item: {a} -> {b}")
            out.append(f"- price difference paid or refunded with: "
                       f"{_payment_text(state, args.get('payment_method_id'))}")
        elif tool == "return_delivered_order_items":
            for it in args.get("item_ids") or []:
                out.append(f"- return item: {_retail_item(state, it, order)}")
            out.append(f"- refund to: {_payment_text(state, args.get('payment_method_id'))}")
        else:
            out += _generic({k: v for k, v in args.items() if k != "order_id"})
        return out
    if tool == "book_reservation":
        out.append(f"- trip: {trip_text(state, args)}")
        out.append(f"- cabin: {args.get('cabin')}")
        out += [f"- flight: {x}" for x in _flights(state, args.get("flights"))]
        out += [f"- passenger: {x}" for x in _passengers(args.get("passengers"))]
        for pm in args.get("payment_methods") or []:
            if isinstance(pm, dict):
                out.append(f"- payment: {_payment_text(state, pm.get('payment_id'))}, amount {pm.get('amount')}")
        out.append(f"- checked bags: {args.get('total_baggages')} in total, {args.get('nonfree_baggages')} not free")
        out.append(f"- travel insurance: {args.get('insurance')}")
        return out
    rid = args.get("reservation_id")
    if rid is not None:
        out.append(f"- reservation: {rid}")
    if tool == "update_reservation_flights":
        out.append(f"- cabin: {args.get('cabin')}")
        out += [f"- flight: {x}" for x in _flights(state, args.get("flights"))]
        out.append(f"- payment: {_payment_text(state, args.get('payment_id'))}")
    elif tool == "update_reservation_baggages":
        out.append(f"- checked bags: {args.get('total_baggages')} in total, {args.get('nonfree_baggages')} not free")
        out.append(f"- payment: {_payment_text(state, args.get('payment_id'))}")
    elif tool == "update_reservation_passengers":
        out += [f"- passenger: {x}" for x in _passengers(args.get("passengers"))]
    elif tool == "send_certificate":
        out.append(f"- user: {args.get('user_id')}")
        out.append(f"- amount: {args.get('amount')}")
    elif tool != "cancel_reservation":
        out += _generic({k: v for k, v in args.items() if k != "reservation_id"})
    return out


# ----------------------------------------------------------------------------------------------- K2 v2: the lines to state

# K2 version 2 (docs/planning/tracker_v3/k2_fix.md): message A must state every argument of the call that the user can
# check, each in a form the user knows. Code renders one line per argument (the per-tool list), each with the value(s)
# from the call and the forms that count. Never listed: the user's own id, amounts that are not arguments (prices),
# the options that stay the same, the internal payment id of a card or PayPal.
LISTING_RENDER = "listing_lines"                  # the input field "render" of K2 v2's details input
ADDRESS_NAMES = (("address1", "street line 1"), ("address2", "line 2"), ("city", "city"), ("state", "state"),
                 ("zip", "zip"), ("country", "country"))
ARROW = "→"
DASH = "—"


def _given(v: Any) -> bool:
    return v not in (None, "")


def payment_line(state: Any, pid: Any, amount: Any = None) -> Tuple[str, str]:
    """(the method in plain words, the forms that count) of one payment method: a card by its kind and last four
    digits (the brand may be left out), a gift card by 'gift card' or its id, PayPal by 'PayPal', a certificate by
    'certificate' or its id. With amount (several methods in one call): the amount paid with it too."""
    pm = _safe(lambda: state.db_get("payment_method", pid))
    src = pm.get("source") if isinstance(pm, dict) else None
    if src == "credit_card":
        brand = (pm.get("brand") or "").strip()
        four = pm.get("last_four")
        what = f"credit card{' ' + brand if brand else ''} ending in {four}"
        forms = f"the message names a credit card (any brand word or none) with the last four digits {four}"
    elif src == "gift_card":
        what = f"gift card ({pid})"
        forms = f"the message says gift card, or gives the gift card id ({pid})"
    elif src == "paypal":
        what = "PayPal"
        forms = "the message says PayPal"
    elif src == "certificate":
        what = f"certificate ({pid})"
        forms = f"the message says certificate, or gives the certificate id ({pid})"
    else:
        what = f"payment method {pid}"
        forms = f"the message names this payment method ({pid})"
    if amount is not None:
        what += f", amount {amount}"
        forms += f", and the amount paid with it ({amount})"
    return what, forms


def _line(label: str, value: str, forms: str) -> str:
    return f"- {label}: {value} {DASH} counts if {forms}"


def _pay_line(state: Any, label: str, pid: Any) -> str:
    what, forms = payment_line(state, pid)
    return _line(label, what, forms)


def address_line(args: Dict[str, Any], label: str = "new address") -> str:
    """Every non-empty field of the address, each named."""
    parts = [(name, str(args[k])) for k, name in ADDRESS_NAMES if _given(args.get(k))]
    value = ", ".join(v for _, v in parts) or "(no field given)"
    forms = "the message gives every field: " + "; ".join(f"{n} ({v})" for n, v in parts)
    return _line(label, value, forms)


def item_options(state: Any, item_id: Any, order: Any = None) -> Tuple[Optional[str], Dict[str, Any]]:
    """(product name, options) of an item: from the order's own item list first (the old item), else the product
    catalogue's variant. (None, {}) when the item is not found."""
    if isinstance(order, dict):
        for it in order.get("items") or []:
            if isinstance(it, dict) and it.get("item_id") == item_id:
                return it.get("name"), dict(it.get("options") or {})
    v = _safe(lambda: state.db_get("variant", item_id))
    if isinstance(v, dict):
        prod = _safe(lambda: state.db_get("product", v.get("product_id")))
        return (prod.get("name") if isinstance(prod, dict) else None), dict(v.get("options") or {})
    return None, {}


def changed_options(old: Dict[str, Any], new: Dict[str, Any]) -> List[Tuple[str, Any, Any]]:
    """(option, old value, new value) for each option whose value differs, in the old item's option order, then
    options only the new item has (None: the item has no such option)."""
    keys = list(old) + [k for k in new if k not in old]
    return [(k, old.get(k), new.get(k)) for k in keys if old.get(k) != new.get(k)]


def _item_name(name: Optional[str], item_id: Any) -> str:
    return f"{name} [item {item_id}]" if name else f"item {item_id}"


def _old_item_forms(name: Optional[str], item_id: Any) -> str:
    return f"the message names the product ({name}) or the item id" if name else \
        f"the message gives the item id ({item_id})"


def changed_item_line(state: Any, old_id: Any, new_id: Any, order: Any = None) -> str:
    """One old item and its new item: the old one by product name or item id; the new one by its item id, or each
    option that changes (computed from the two items' options in the database)."""
    oname, oopts = item_options(state, old_id, order)
    nname, nopts = item_options(state, new_id)
    old_txt = _item_name(oname, old_id)
    if not _given(new_id):
        return _line("changed item", f"{old_txt} {ARROW} (no new item)", _old_item_forms(oname, old_id))
    both = oname is not None and nname is not None
    diffs = changed_options(oopts, nopts) if both else []
    old_forms = (f"the message names the product ({oname}) or the old item id" if oname else
                 f"the message gives the old item id ({old_id})")
    if both and nname == oname and diffs:
        ch = "; ".join(f"{k} {'(none)' if a is None else a} {ARROW} {'(none)' if b is None else b}"
                       for k, a, b in diffs)
        new_forms = f"gives the new item id, or each option that changes: {ch}"
    elif both and nname != oname:
        new_forms = f"gives the new item id (the new item is a {nname})"
    elif both:
        new_forms = "gives the new item id (no option changes)"
    else:
        new_forms = "gives the new item id"
    return _line(f"new item for {old_txt}", f"item {new_id}", f"{old_forms}, and {new_forms}")


def flight_line(fl: Any) -> str:
    if not isinstance(fl, dict):
        return _line("flight", str(fl), "the message names this flight")
    num, date = fl.get("flight_number"), fl.get("date")
    return _line("flight", f"{num} on {date}",
                 f"the message gives the flight number ({num}) and the date ({date}; any date format, the year may "
                 f"be left out)")


def passenger_line(p: Any) -> str:
    if not isinstance(p, dict):
        return _line("passenger", str(p), "the message names this passenger")
    first, last, dob = p.get("first_name"), p.get("last_name"), p.get("dob")
    return _line("passenger", f"{first} {last}, date of birth {dob}",
                 f"the message gives the first and last name ({first} {last}) and the date of birth ({dob}; any "
                 f"date format)")


def bags_line(args: Dict[str, Any]) -> str:
    total, paid = args.get("total_baggages"), args.get("nonfree_baggages")
    return _line("checked bags", f"{total} in total, {paid} paid",
                 f"the message gives the total number of checked bags ({total}) and how many are paid ({paid})")


def _paid_bags(args: Dict[str, Any]) -> bool:
    try:
        return int(args.get("nonfree_baggages") or 0) > 0
    except (TypeError, ValueError):
        return True


def _reservation(state: Any, rid: Any) -> Optional[dict]:
    r = _safe(lambda: state.db_get("reservation", rid)) if rid is not None else None
    return r if isinstance(r, dict) else None


def changed_flights(state: Any, rid: Any, flights: Any) -> List[Any]:
    """The call's flights whose flight number or date differs from every current flight of the reservation (the
    database at the check). tau-bench's update_reservation_flights takes all flights of the trip, so the unchanged
    ones are not lines (like the options that stay the same). Reservation not found: every flight."""
    flights = list(flights or [])
    res = _reservation(state, rid)
    if res is None:
        return flights
    now = {(f.get("flight_number"), f.get("date")) for f in res.get("flights") or [] if isinstance(f, dict)}
    return [f for f in flights if not isinstance(f, dict) or (f.get("flight_number"), f.get("date")) not in now]


def changed_passengers(state: Any, rid: Any, passengers: Any) -> List[Any]:
    """The call's passengers whose first name, last name or date of birth differs from every current passenger of
    the reservation (tau-bench's update_reservation_passengers takes all passengers). Reservation not found: all."""
    ps = list(passengers or [])
    res = _reservation(state, rid)
    if res is None:
        return ps
    now = {(p.get("first_name"), p.get("last_name"), p.get("dob")) for p in res.get("passengers") or []
           if isinstance(p, dict)}
    return [p for p in ps if not isinstance(p, dict) or (p.get("first_name"), p.get("last_name"), p.get("dob"))
            not in now]


def listing_lines(state: Any, domain: Optional[str], tool: str, args: Dict[str, Any]) -> List[str]:
    """K2 v2's lines for one call (k2_fix.md, the per-tool list)."""
    out: List[str] = []
    if domain == "retail":
        oid = args.get("order_id")
        order = _safe(lambda: state.db_get("order", oid)) if oid is not None else None
        if tool != "modify_user_address":
            out.append(_line("order", str(oid), "the message gives the order id (with or without #)"))
        if tool == "cancel_pending_order":
            reason = args.get("reason")
            out.append(_line("reason", str(reason),
                             f"the message gives this reason ({reason}), in these words or the same meaning"))
        elif tool in ("modify_pending_order_address", "modify_user_address"):
            out.append(address_line(args, "new address" if tool == "modify_pending_order_address"
                                    else "new default address"))
        elif tool == "modify_pending_order_payment":
            out.append(_pay_line(state, "new payment method", args.get("payment_method_id")))
        elif tool in ("modify_pending_order_items", "exchange_delivered_order_items"):
            olds, news = list(args.get("item_ids") or []), list(args.get("new_item_ids") or [])
            for i in range(max(len(olds), len(news))):
                o = olds[i] if i < len(olds) else None
                n = news[i] if i < len(news) else None
                if o is None:
                    out.append(_line("new item", f"item {n} (no old item)", f"the message gives the item id ({n})"))
                else:
                    out.append(changed_item_line(state, o, n, order))
            out.append(_pay_line(state, "payment method for the price difference", args.get("payment_method_id")))
        elif tool == "return_delivered_order_items":
            for it in args.get("item_ids") or []:
                name, _ = item_options(state, it, order)
                out.append(_line("returned item", _item_name(name, it), _old_item_forms(name, it)))
            out.append(_pay_line(state, "refund method", args.get("payment_method_id")))
        else:
            out += _generic({k: v for k, v in args.items() if k not in ("order_id", "user_id")})
        return out
    cabin_forms = "the message names this cabin ({})"
    if tool == "book_reservation":
        out += [flight_line(f) for f in args.get("flights") or []]
        out.append(_line("cabin", str(args.get("cabin")), cabin_forms.format(args.get("cabin"))))
        out += [passenger_line(p) for p in args.get("passengers") or []]
        pms = [pm for pm in args.get("payment_methods") or [] if isinstance(pm, dict)]
        for pm in pms:
            what, forms = payment_line(state, pm.get("payment_id"), pm.get("amount") if len(pms) > 1 else None)
            out.append(_line("payment method", what, forms))
        out.append(bags_line(args))
        ins = args.get("insurance")
        word = {"yes": "added", "no": "not added"}.get(ins, str(ins))
        out.append(_line("travel insurance", word,
                         f"the message says whether travel insurance is added (here: {word})"))
        return out
    rid = args.get("reservation_id")
    if tool != "send_certificate":
        out.append(_line("reservation", str(rid), "the message gives the reservation id"))
    if tool == "update_reservation_flights":
        out += [flight_line(f) for f in changed_flights(state, rid, args.get("flights"))]
        out.append(_line("cabin", str(args.get("cabin")), cabin_forms.format(args.get("cabin"))))
        out.append(_pay_line(state, "payment method", args.get("payment_id")))
    elif tool == "update_reservation_baggages":
        out.append(bags_line(args))
        if _paid_bags(args):
            out.append(_pay_line(state, "payment method", args.get("payment_id")))
    elif tool == "update_reservation_passengers":
        out += [passenger_line(p) for p in changed_passengers(state, rid, args.get("passengers"))]
    elif tool == "send_certificate":
        amt = args.get("amount")
        out.append(_line("certificate amount", str(amt), f"the message gives the amount ({amt})"))
    elif tool != "cancel_reservation":
        out += _generic({k: v for k, v in args.items() if k not in ("reservation_id", "user_id")})
    return out


def render_listing(state: Any, tool: Optional[str], args: Dict[str, Any]) -> str:
    """K2 v2's details text: the action, then one line per argument the user can check, each with the forms that
    count. Deterministic. K1 keeps render_action (its input is unchanged)."""
    args = dict(args or {})
    domain = getattr(state, "domain", None)
    tool = tool or "the pending call"
    phrase = (RETAIL_PHRASE if domain == "retail" else AIRLINE_PHRASE).get(tool, f"call {tool}")
    lines = [f"{phrase} (tool {tool}). The lines:"]
    try:
        lines += listing_lines(state, domain, tool, args)
    except (KeyError, IndexError, TypeError, AttributeError, ValueError):
        lines += _generic({k: v for k, v in args.items() if k != "user_id"})
    return "\n".join(lines)


# ----------------------------------------------------------------------------------------------- the helpers

def _hook(ctx: Any) -> Any:
    a = ctx.need_answers()                           # MissingInput when evaluate() got no answers hook
    if not callable(getattr(a, "ask", None)):
        raise F.MissingInput(f"{ctx.fact}: the answers hook has no ask()")
    return a


def _pending_tool(ctx: Any) -> Optional[str]:
    p = getattr(ctx.state, "pending", None)
    return p.get("tool") if isinstance(p, dict) else None


def _build_inputs(ctx: Any, qid: str, messages: Sequence[Any], focus: Optional[str], items: Optional[str],
                  doc: dict) -> Optional[Dict[str, Any]]:
    """The question's inputs: the messages in the order of its message inputs, and the texts code renders. A message
    is a text or a ref of the view (p7). With fewer messages than message inputs, the optional inputs are left out
    first (K1 with one message: the reply; K15: message; K14: reply). None when a required message is missing or
    empty (the helper then gives False: no message, no yes)."""
    q = question(qid, doc)
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
                xs = sorted(xs)                              # refs: in conversation order
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
    for s in q["inputs"]:
        if s["type"] == "text" and s.get("from") == "call":
            if s["name"] == "trip":
                inputs[s["name"]] = trip_text(ctx.state, ctx.args or {})
            elif s.get("render") == LISTING_RENDER and focus is None:
                inputs[s["name"]] = render_listing(ctx.state, _pending_tool(ctx), ctx.args or {})   # K2 v2
            else:
                inputs[s["name"]] = render_action(ctx.state, _pending_tool(ctx), ctx.args or {}, focus)
        elif s["type"] == "text" and s.get("from") == "domain":
            inputs[s["name"]] = doc["domain_texts"][s["name"]][ctx.domain]
        elif s["type"] == "choice":
            if items not in s["values"]:
                raise ValueError(f"{qid}: items= must be one of {s['values']}, not {items!r}")
            inputs[s["name"]] = items
    if items is not None and not any(s["type"] == "choice" for s in q["inputs"]):
        raise ValueError(f"{qid} has no choice input, so items= does not apply")
    return inputs


def _doc_of(hook: Any) -> dict:
    return getattr(hook, "doc", None) or load_questions()


def _ask_rec(ctx: Any, hook: Any, qid: str, messages: Sequence[Any], focus: Optional[str] = None,
             items: Optional[str] = None) -> Optional[dict]:
    """The answer record, or None when a required message is missing."""
    inputs = _build_inputs(ctx, qid, messages, focus, items, _doc_of(hook))
    if inputs is None:
        hook.stats.bump("no_message", qid)
        ctx.note({"question": qid, "answer": None, "why": "no message to ask about"})
        return None
    rec = hook.ask(qid, inputs, fact=ctx.fact, part=ctx.part_id)
    ctx.note({"question": qid, "key": (rec.get("key") or "")[:16], "status": rec.get("status"),
              "quote": rec.get("quote")})
    return rec


def _value(hook: Any, qid: str, rec: dict) -> bool:
    try:
        return value_of(rec)
    except F.UseBlockingValue:
        hook.stats.bump("blocking", qid)
        raise


def h_ask(ctx: Any, qid: str, *messages: Any, focus: Optional[str] = None, items: Optional[str] = None) -> bool:
    """ask(qid, m1[, m2], focus=None, items=None): one question about one or two messages."""
    hook = _hook(ctx)
    rec = _ask_rec(ctx, hook, qid, messages, focus, items)
    if rec is None:
        return False
    return _value(hook, qid, rec)


def _as_messages(c: Any) -> Tuple[Any, ...]:
    if isinstance(c, (list, tuple)):
        return tuple(c)
    return (c,)


def h_ask_first_yes(ctx: Any, qid: str, candidates: Any, focus: Optional[str] = None, items: Optional[str] = None,
                    also: Optional[str] = None, limit: Optional[int] = None) -> bool:
    """ask_first_yes(qid, candidates, focus=None, items=None, also=None, limit=None): newest candidate first; True
    at the first yes. also='K2': a candidate counts only if that question is yes on its first message too (asked
    first). limit: at most that many candidates. No yes and an unclear on the way: the blocking value. No yes and no
    unclear (or no candidate): False."""
    hook = _hook(ctx)
    if candidates is None:
        candidates = []
    if not isinstance(candidates, (list, tuple)):
        raise TypeError(f"ask_first_yes: candidates must be a list, not {type(candidates).__name__}")
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError(f"ask_first_yes: limit must be an integer >= 1, not {limit!r}")
        candidates = list(candidates)[:limit]
    unclear: Optional[F.UseBlockingValue] = None
    found = False
    for c in candidates:
        msgs = _as_messages(c)
        if also is not None:
            arec = _ask_rec(ctx, hook, also, msgs[:1], None, None)
            if arec is None:
                continue
            try:
                if not value_of(arec):
                    continue
            except F.UseBlockingValue as e:
                unclear = unclear or e
                continue
        rec = _ask_rec(ctx, hook, qid, msgs, focus, items)
        if rec is None:
            continue
        try:
            if value_of(rec):
                found = True
                if not hook.exhaustive:
                    return True
        except F.UseBlockingValue as e:
            unclear = unclear or e
    if found:
        return True
    if unclear is not None:
        hook.stats.bump("blocking", qid)
        raise F.UseBlockingValue(f"no yes, and an unclear answer on the way: {unclear.detail}", kind="unclear")
    return False


_CANCEL_WORD = re.compile(r"\bcancel")
_DELAY_WORD = re.compile(r"\bdelay")
_AMOUNT = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s?(?:dollars|usd)\b")
_PER_PERSON = re.compile(r"per passenger|per person|each|a passenger|a person|per traveler|per traveller")


def amounts_in(text: Any) -> List[Tuple[float, int, int]]:
    """(amount, start, end) of every dollar amount ('$100', '100 dollars', '100 USD') in the normalized text."""
    s = normalize_text(text)
    out = []
    for m in _AMOUNT.finditer(s):
        num = (m.group(1) or m.group(2)).replace(",", "")
        try:
            out.append((float(num), m.start(), m.end()))
        except ValueError:
            continue
    return out


def _standin_value(ctx: Any, hook: Any) -> bool:
    v = hook.value_for(ctx.fact)
    if v is None:
        raise F.UseBlockingValue(f"{ctx.fact}: the saved judge value is unknown", kind="unclear")
    return v


def _first_yes_soft(ctx: Any, hook: Any, qid: str, msgs: Any) -> Optional[bool]:
    """ask_first_yes, with an unclear result as None (offer_kind decides undecided cases itself)."""
    try:
        return h_ask_first_yes(ctx, qid, list(msgs or []))
    except F.UseBlockingValue:
        return None


def h_offer_kind(ctx: Any, reply: Any, kind: str, cancel_msgs: Any = None, delay_msgs: Any = None) -> bool:
    """offer_kind(reply, kind, cancel_msgs, delay_msgs): the offer in the reply is about a `kind` ('cancelled' or
    'delayed') flight. K12's quote: a word of this kind and none of the other gives True; of the other kind only gives
    False. Otherwise the user's complaints decide: K8 on cancel_msgs, K9 on delay_msgs (first yes); only this kind
    complained of gives True, only the other kind gives False. Still undecided: True (the blocking value of both
    offer facts)."""
    if kind not in ("cancelled", "delayed"):
        raise ValueError(f"offer_kind: kind must be 'cancelled' or 'delayed', not {kind!r}")
    hook = _hook(ctx)
    if getattr(hook, "standin", False):
        return _standin_value(ctx, hook)
    rec = _ask_rec(ctx, hook, "K12", (reply,))
    if rec is None:
        return False                                    # no reply text: no offer
    offered = _value(hook, "K12", rec)
    if not offered:
        return False
    q = normalize_text(clean_quote(rec.get("quote")))
    c, d = bool(_CANCEL_WORD.search(q)), bool(_DELAY_WORD.search(q))
    if c != d:
        return c if kind == "cancelled" else d
    k8 = _first_yes_soft(ctx, hook, "K8", cancel_msgs)
    k9 = _first_yes_soft(ctx, hook, "K9", delay_msgs)
    if k8 is not None and k9 is not None and k8 != k9:
        return k8 if kind == "cancelled" else k9
    ctx.note({"offer_kind": kind, "decided_by": "undecided: blocking value", "k8": k8, "k9": k9})
    return True


def h_offer_amount_ok(ctx: Any, reply: Any, rate: Any, passenger_counts: Any) -> bool:
    """offer_amount_ok(reply, rate, passenger_counts): the dollar amounts of the offer are right. Amounts are read
    from K12's quote, or from the reply when the quote has none. True when no amount is named, when one equals
    rate x the passengers of a reservation (passenger_counts), or when one equals the rate with 'per passenger',
    'each' or 'per person' near it. A reply with no dollar amount at all is True without a question (the quote is
    part of the reply, so it has none either)."""
    hook = _hook(ctx)
    if getattr(hook, "standin", False):
        return _standin_value(ctx, hook)
    text = message_text(reply, getattr(ctx, "view", None)) or ""
    if not amounts_in(text):
        ctx.note({"offer_amount": "no dollar amount in the reply"})
        return True
    rec = _ask_rec(ctx, hook, "K12", (reply,))
    if rec is None:
        return True
    offered = _value(hook, "K12", rec)
    quote = normalize_text(clean_quote(rec.get("quote"))) if offered else ""
    source = quote if amounts_in(quote) else normalize_text(text)
    found = amounts_in(source)
    if not found:
        return True
    rate = float(rate)
    counts = [int(n) for n in (passenger_counts or []) if isinstance(n, (int, float)) and not isinstance(n, bool)]
    for amount, start, end in found:
        if any(abs(amount - rate * n) < 0.005 for n in counts):
            return True
        if abs(amount - rate) < 0.005 and _PER_PERSON.search(source[max(0, start - 40): end + 40]):
            return True
    ctx.note({"offer_amount": [a for a, _, _ in found], "rate": rate, "passenger_counts": counts})
    return False


HELPERS = (
    ("ask", h_ask, 2, 3, ("focus", "items"), "one tiny question about one or two messages (p8)"),
    ("ask_first_yes", h_ask_first_yes, 2, 2, ("focus", "items", "also", "limit"),
     "the first yes among candidate messages or pairs, newest first (p8)"),
    ("offer_kind", h_offer_kind, 2, 4, (), "the kind of the offer in a reply: K12's quote, else K8 / K9 (p8)"),
    ("offer_amount_ok", h_offer_amount_ok, 3, 3, (), "the dollar amounts of the offer in a reply (p8)"),
)


def register_helpers() -> List[str]:
    """Register the question helpers (source 'question'); registering again changes nothing."""
    for name, func, lo, hi, kws, doc in HELPERS:
        F.register_name(name, func, lo, hi, kws, source="question", doc=doc)
    return [h[0] for h in HELPERS]


register_helpers()


# ----------------------------------------------------------------------------------------------- CLI

def sample_inputs(qid: str, doc: Optional[dict] = None) -> Dict[str, Any]:
    """Made-up inputs for a question (the --check rendering and the tests)."""
    q = question(qid, doc)
    out: Dict[str, Any] = {}
    for s in q["inputs"]:
        if s["type"] == "message":
            out[s["name"]] = f"sample {s.get('who', 'user')} message for {s['name']}: yes, please go ahead."
        elif s["type"] == "messages":
            out[s["name"]] = ["sample user message one", "sample user message two"]
        elif s["type"] == "choice":
            out[s["name"]] = s["values"][0]
        elif s.get("from") == "domain":
            out[s["name"]] = (doc or load_questions())["domain_texts"][s["name"]]["retail"]
        else:
            out[s["name"]] = "sample action text"
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -B -m state_tracker.v3.questions",
                                 description="Check the tiny questions file and render the questions (no LLM call).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="check questions_v3.json and render every question")
    g.add_argument("--show", metavar="K", help="print one rendered question with made-up inputs")
    a = ap.parse_args(argv)
    from state_tracker.v3.frozen import check_manifest
    check_manifest()
    block_network()
    doc = load_questions()
    if a.show:
        p = render(a.show, sample_inputs(a.show, doc), doc)
        print("SYSTEM:\n" + p["system"] + "\n\nUSER:\n" + p["user"])
        return 0
    for qid in question_ids(doc):
        q = question(qid, doc)
        inputs = sample_inputs(qid, doc)
        p = render(qid, inputs, doc)
        h = Questions(FakeBackend("yes"), doc=doc)
        rec = h.ask(qid, inputs)
        print(f"{qid} v{q['version']}: inputs {[i['name'] for i in q['inputs']]}; quote from {q['quote_from']}; "
              f"prompt {len(p['system']) + len(p['user'])} chars; fake yes -> {rec['status']}; "
              f"text_sha256 {q['text_sha256'][:16]}")
    print(f"questions: {len(doc['questions'])}; system_sha256 {doc['system_sha256'][:16]}; model {doc['model']} "
          f"({doc['effort']}); helpers {[h[0] for h in HELPERS]}; network events {len(network_events())}")
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.exit(main())
