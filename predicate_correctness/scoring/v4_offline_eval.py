"""Tracker v4 (scoring.v4_offline_eval): the v4 guard, offline, on the 200 v3 development conversations (the p12a set).

Plan: docs/planning/tracker_v4/overview.md §10 (P1b offline run, P2 dev check), code_change_map.md §1.3 and §3.
Copied in spirit from scoring/v3_p12_offline.py and scoring/v3_offline_eval.py (both imported, never edited).

The conversations: exactly the set p12a answered (scoring/v3_p12_offline.select_conversations("dev")): the first 50
conversations of each of the 4 strong-agent development data sets (stage_a.luna.tgr_frozen, stage_a.luna.tgr_tracker,
ours.p10_luna_train, partner.luna_train_v5), agent luna. Development data only: a hold-out key raises HoldOutData, and
no B2 / B3 / hold-out file is ever opened.

The guard: guard/tgr_tracker_v4.py (agent A6), messages = rule (the v4 block messages), lazy, built through its
build(). Per conversation each arm keeps its own list of v4 blocks on the TGR Conversation (`conv.v4_blocks`), so the
transfer escape (code_change_map §0.2 item 3) is rebuilt offline exactly as online.

The answer backend (--backend):
  fake      fake answers (--policy yes | no | unclear | bad_quote), in memory: the code paths, $0
  standin   the judge stand-in only (meaning = saved_judge: the judge's saved value of the fact stands in for the
            answer), $0
  saved     the stored answers only (output/eval_v4/questions_answers_v4.jsonl first, then v3's store read-only
            where the v4 key equals the v3 key); a key not stored is counted as missing, never asked. $0
  count     as fake, with the stored answers preloaded (v4 store, then v3's): every key not stored is one call a real
            run would make (scoring/v4_dev_answers.py reads these rows). $0
  real      real answers (main chat only): --i-am-the-main-chat, --approved "<the user's words>", --max-usd (<= $2, the
            dev limit) and --max-calls (<= 5,100); questions_v4.RealBackendV4 over ChainStore(v4 store, v3 store
            read-only, dev keys only). Refused otherwise (state_tracker.v3.questions.RealModeRefused). Threads in one
            process (one budget). The $2 / 5,100-call limits are for ALL v4 dev runs together (cases, this run, any
            re-ask): the shared dev ledger (DEV_LEDGER) is read first and this run gets min(asked, what is left);
            every call is written to the ledger before it starts.
v3's answers file is never loaded whole (it also holds non-dev answers): DevOnlyStore keeps only the dev keys.
Every backend but standin also runs the stand-in arm on the same check (row key "v3sj"), for the dev check's ratio.

Rows (one per check; the layout of v3 p11/p12 rows, so v3's analysis code reads them):
  "v3"    the main arm (the v4 guard's rec["v3"] summary; backend standin: the stand-in arm), plus "v4" (rec["v4"]),
          "asks" ([key, qid, fact, part, cached, wording]), "status" ({key: stored status}), "msg" (the block message)
  "v3sj"  the stand-in arm (None for backend standin)
  "fz"    frozen TGR on the saved judge values (process pool only)
Outputs: output/eval_v4/dev/offline_<tag>_rows.jsonl, _meta.json, _report.md (tag = backend, or backend_policy).

Run from predicate_correctness/ (venv Python, hash seed fixed; output to a log file):
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m scoring.v4_offline_eval \\
        --backend standin --workers 8 > output/logs/v4_offline_standin.log 2>&1
"""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import importlib
import inspect
import json
import os
import sys
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from state_tracker import paths                                   # noqa: E402

OUT_DIR = os.path.join(paths.OUTPUT_DIR, "eval_v4", "dev")
LOGS = os.path.join(paths.OUTPUT_DIR, "logs")
V3_STORE = os.path.join(paths.OUTPUT_DIR, "eval_v3", "questions_answers.jsonl")
V4_STORE = os.path.join(paths.OUTPUT_DIR, "eval_v4", "questions_answers_v4.jsonl")
CASES_STORE = os.path.join(paths.OUTPUT_DIR, "eval_v4", "cases", "answers.jsonl")
V3_OUT = os.path.join(paths.OUTPUT_DIR, "eval_v3")
DEV_SETS = ("stage_a.luna.tgr_frozen", "stage_a.luna.tgr_tracker", "ours.p10_luna_train", "partner.luna_train_v5")
DEV_LIMIT = 50
BACKENDS = ("fake", "standin", "saved", "count", "real")
FAKE_POLICIES = ("yes", "no", "unclear", "bad_quote")
MAIN, STANDIN, FROZEN = "v3", "v3sj", "fz"
DEV_LIMIT_USD = 2.0                       # overview §9: the dev check's money limit (all v4 dev runs together)
DEV_LIMIT_CALLS = 5100                    # the approved call limit (dev_answers_count.md request), all dev runs together
# The shared dev ledger: one line per paid call, written BEFORE the call (reserve, the worst-case cost) and after it
# (spend, the real cost). Every real dev run (cases, the 200 conversations, any re-ask) reads it at start, so the dev
# limits hold across runs. The .lock file is held (flock) for the whole run: one real dev run at a time.
DEV_LEDGER = os.path.join(OUT_DIR, "dev_spend_ledger.jsonl")
MAIN_CHAT_FLAG = "--i-am-the-main-chat"
MAX_WORKERS = 8
FAKE_QUOTE_WORDS = 8
ALT_WORDS = {"K17": {"yes": "added", "no": "not_added", "unclear": "unclear"}}   # K17v4 answers (cases_spec)
UNCLEAR_STATUSES = ("unclear", "quote_failed", "bad_output")                     # D10: a failed quote is unclear
OWN_FILES = ("scoring/v4_offline_eval.py", "scoring/v4_dev_answers.py", "scoring/v4_dev_check.py",
             "scoring/v4_cases.py", "tests/test_v4_devcheck.py")


def say(msg: str) -> None:
    print(msg, flush=True)


def rel(path: str) -> str:
    return os.path.relpath(os.path.abspath(path), PC_DIR)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def utc() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _Q():
    from state_tracker.v3 import questions as Q
    return Q


def hard_stops() -> Tuple[type, ...]:
    """v3's exception classes (v4 reuses them): a hard stop always passes through, never counted as an error."""
    Q = _Q()
    return (Q.BudgetExceeded, Q.NetworkBlocked, Q.RealModeRefused, Q.AnswerNotSaved, Q.RealCallFailed)


# ----------------------------------------------------------------------------------------------- the dev ledger
_HELD_LOCKS: Dict[str, Any] = {}            # lock path -> open file holding the flock (this process)
PARTIAL_LINE_USD = 0.01                     # a cut ledger line (crash while writing) counts one call at this cost


class DevLedger:
    """The shared spend ledger of every real v4 dev run (see DEV_LEDGER). Only appends; reads whole lines."""

    def __init__(self, path: str = DEV_LEDGER):
        self.path = os.path.abspath(path)
        self._lock = threading.Lock()
        self._n = 0

    def read(self) -> Dict[str, Any]:
        """{calls, usd, open, runs, bad_lines}: calls = reserve lines; usd = per reserve its spend if written, else
        its worst-case cost (a call whose result was never written counts in full). A bad or cut line counts as one
        call at PARTIAL_LINE_USD (never less than nothing)."""
        res: Dict[str, dict] = {}
        spends: Dict[str, float] = {}
        bad = 0
        runs = set()
        if os.path.isfile(self.path):
            with open(self.path, "rb") as f:
                for raw in f:
                    try:
                        if not raw.endswith(b"\n"):
                            raise ValueError("cut line")
                        if not raw.strip():
                            continue
                        rec = json.loads(raw.decode("utf-8"))
                        kind, rid, usd = rec["kind"], str(rec["rid"]), float(rec["usd"])
                    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
                        bad += 1
                        continue
                    runs.add(str(rec.get("run_id")))
                    if kind == "reserve":
                        res.setdefault(rid, {"usd": max(0.0, usd)})
                    elif kind == "spend":
                        spends[rid] = spends.get(rid, 0.0) + max(0.0, usd)
                    else:
                        bad += 1
        usd = sum(spends.get(rid, r["usd"]) for rid, r in res.items())
        usd += sum(v for rid, v in spends.items() if rid not in res) + bad * PARTIAL_LINE_USD
        return {"path": rel(self.path), "calls": len(res) + bad, "usd": round(usd, 8),
                "open": sum(1 for rid in res if rid not in spends), "runs": sorted(runs), "bad_lines": bad}

    def _append(self, rec: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def reserve(self, run_id: str, usd: float) -> str:
        """One call about to start, at its worst-case cost; written (fsync) before the call. Returns its id."""
        with self._lock:
            self._n += 1
            rid = f"{run_id}:{os.getpid()}:{self._n}"
            self._append({"kind": "reserve", "rid": rid, "run_id": run_id, "usd": round(float(usd), 8),
                          "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            return rid

    def spend(self, run_id: str, rid: Optional[str], usd: float) -> None:
        with self._lock:
            self._append({"kind": "spend", "rid": rid or f"{run_id}:unpaired", "run_id": run_id,
                          "usd": round(float(usd), 8), "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})


def lock_ledger(path: str = DEV_LEDGER) -> None:
    """Hold the ledger's lock file (flock, non-blocking) until this process ends; RealModeRefused if another
    process holds it (two real dev runs at once could both spend the same money)."""
    import fcntl
    lp = os.path.abspath(path) + ".lock"
    if lp in _HELD_LOCKS:
        return
    os.makedirs(os.path.dirname(lp), exist_ok=True)
    fh = open(lp, "a+")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        raise _Q().RealModeRefused(f"another real v4 dev run holds {rel(lp)}: one paid dev run at a time") from None
    _HELD_LOCKS[lp] = fh


def unlock_ledger(path: str = DEV_LEDGER) -> None:
    fh = _HELD_LOCKS.pop(os.path.abspath(path) + ".lock", None)
    if fh is not None:
        fh.close()                                   # closing the file releases the flock


def ledger_locked(path: str = DEV_LEDGER) -> bool:
    return os.path.abspath(path) + ".lock" in _HELD_LOCKS


def dev_room(ledger: str = DEV_LEDGER, questions: Optional[Sequence[str]] = None, limit_usd: float = DEV_LIMIT_USD,
             limit_calls: int = DEV_LIMIT_CALLS) -> Dict[str, Any]:
    """What is left of the dev limits: spent = max(the ledger, guard/soft_stop_v4.questions_spend of the dev answers
    files), used = max(ledger calls, answer lines in those files)."""
    from guard import soft_stop_v4 as SS                 # read and call only (owned by another agent)
    led = DevLedger(ledger).read()
    q = SS.questions_spend(tuple(questions) if questions is not None else SS.QUESTIONS_FILES)
    q_lines = sum(int(v.get("lines") or 0) for v in (q.get("by_file") or {}).values())
    spent = max(float(led["usd"]), float(q["usd"]))
    used = max(int(led["calls"]), q_lines)
    return {"ledger": led, "questions_usd": round(float(q["usd"]), 8), "questions_lines": q_lines,
            "spent_usd": round(spent, 8), "used_calls": used, "limit_usd": limit_usd, "limit_calls": limit_calls,
            "left_usd": round(limit_usd - spent, 8), "left_calls": int(limit_calls - used)}


def ledger_budget(base: Any, ledger: DevLedger, run_id: str) -> Any:
    """A questions.Budget that also writes every call to the dev ledger: the reserve line before the call (inside
    reserve(), after the budget's own check), the spend line after it. A ledger write that fails fires the stop."""
    Q = _Q()

    class LedgerBudget(Q.Budget):
        def __init__(self):
            super().__init__(base.max_usd, base.max_calls, {"input_per_m": 0.0, "output_per_m": 0.0})
            self.pin, self.pout = base.pin, base.pout
            self.spent, self.calls, self.stopped = base.spent, base.calls, base.stopped
            self.ledger, self.run_id = ledger, run_id
            self._tl = threading.local()
            self._order = threading.Lock()

        def reserve(self, est_input_tokens: int) -> None:
            with self._order:
                super().reserve(est_input_tokens)               # raises BudgetExceeded: no line, no call
                try:
                    self._tl.rid = self.ledger.reserve(self.run_id, self.worst_next(est_input_tokens))
                except Exception as e:  # noqa: BLE001 - no ledger line: the call must not start
                    self.stop(f"the dev ledger could not be written: {type(e).__name__}: {e}")
                    raise Q.BudgetExceeded(f"the dev ledger could not be written ({e}): no call starts") from None

        def spend(self, usd: float) -> None:
            super().spend(usd)
            rid = getattr(self._tl, "rid", None)
            self._tl.rid = None
            try:
                self.ledger.spend(self.run_id, rid, usd)
            except Exception as e:  # noqa: BLE001 - the reserve line stays (worst case counted); no new call
                self.stop(f"the dev ledger could not be written: {type(e).__name__}: {e}")

    return LedgerBudget()


def install_ledger(backend: Any, ledger_path: str, run_id: str) -> Any:
    """Put the ledger budget on a real backend, before its first call. The ledger lock must be held."""
    if not ledger_locked(ledger_path):
        raise _Q().RealModeRefused("the real backend needs the dev ledger lock (check_real_flags takes it)")
    backend.budget = ledger_budget(backend.budget, DevLedger(ledger_path), run_id)
    return backend


# ----------------------------------------------------------------------------------------------- real mode guard
def check_real_flags(backend: str, *, main_chat: bool, approved: Optional[str], max_usd: Any, max_calls: Any,
                     limit_usd: float = DEV_LIMIT_USD, limit_calls: int = DEV_LIMIT_CALLS,
                     ledger: Optional[str] = None, questions: Optional[Sequence[str]] = None,
                     info: Optional[Dict[str, Any]] = None) -> Optional[Tuple[str, float, int]]:
    """None for a $0 backend. For backend real: the main chat's flag, the user's approval words, a dollar budget
    0 < max_usd <= limit_usd, a call budget 1 <= max_calls <= limit_calls (questions.check_real_mode), the dev ledger
    lock, and room left in the shared dev limits (dev_room): this run's budgets become min(asked, left). Refused
    (RealModeRefused) when nothing is left. `info` gets the room."""
    Q = _Q()
    if backend != "real":
        if approved:
            raise Q.RealModeRefused(f"--approved was given but the backend is {backend!r} ($0): nothing to approve")
        return None
    if main_chat is not True:
        raise Q.RealModeRefused(f"the real backend runs only from the main chat ({MAIN_CHAT_FLAG})")
    try:
        usd = float(max_usd)
    except (TypeError, ValueError):
        raise Q.RealModeRefused("the real backend needs --max-usd") from None
    if not 0 < usd <= limit_usd:
        raise Q.RealModeRefused(f"--max-usd must be > 0 and <= ${limit_usd:.2f} (the dev check's limit), not {max_usd!r}")
    if isinstance(max_calls, int) and not isinstance(max_calls, bool) and max_calls > limit_calls:
        raise Q.RealModeRefused(f"--max-calls must be <= {limit_calls:,} (the dev check's call limit), not {max_calls}")
    words, usd, calls = Q.check_real_mode(approved, usd, max_calls)
    led = ledger or DEV_LEDGER
    lock_ledger(led)
    try:
        room = dev_room(led, questions, limit_usd, limit_calls)
    except Exception as e:  # noqa: BLE001 - no spend known: no paid run
        unlock_ledger(led)
        raise Q.RealModeRefused(f"the dev spend could not be read ({type(e).__name__}: {e}): refused") from None
    if room["left_usd"] <= 1e-9 or room["left_calls"] < 1:
        unlock_ledger(led)
        raise Q.RealModeRefused(f"the dev limits are used up: spent ${room['spent_usd']:.4f} of ${limit_usd:.2f}, "
                                f"{room['used_calls']:,} of {limit_calls:,} calls")
    run_usd, run_calls = min(usd, room["left_usd"]), min(calls, room["left_calls"])
    room.update(asked_usd=usd, asked_calls=calls, run_usd=run_usd, run_calls=run_calls)
    if info is not None:
        info.update(room)
    say(f"[dev ledger] spent ${room['spent_usd']:.4f} of ${limit_usd:.2f}, {room['used_calls']:,} of "
        f"{limit_calls:,} calls; this run: max ${run_usd:.4f}, max {run_calls:,} calls"
        + (" (cut to what is left)" if (run_usd, run_calls) != (usd, calls) else ""))
    return words, run_usd, run_calls


# ----------------------------------------------------------------------------------------------- fake answers
def fake_policy(word: str) -> Callable[[str, Dict[str, Any], Any], str]:
    """A policy function for questions_v4.FakeBackendV4: the same word for every question, K17's words for K17
    (yes -> added, no -> not_added)."""
    if word not in FAKE_POLICIES:
        raise ValueError(f"unknown fake policy {word!r} (one of {FAKE_POLICIES})")

    def pol(qid: str, inputs: Dict[str, Any], norm: Any = None) -> str:
        base = qid[:-1] if qid.endswith("b") and qid[:-1] in ALT_WORDS else qid
        return ALT_WORDS.get(base, {}).get(word, word)
    return pol


def fake_backend(policy: str, exhaustive: bool = False, counting: bool = False) -> Any:
    """questions_v4.FakeBackendV4 with fake_policy(policy); counting=True also keeps every (key, qid) asked."""
    QV4 = _QV4()

    class CountingFakeV4(QV4.FakeBackendV4):
        def __init__(self, *a: Any, **k: Any):
            super().__init__(*a, **k)
            self.asked: List[Tuple[str, str]] = []
            self._lk = threading.Lock()

        def answer(self, *, qid: str, key: Optional[str] = None, **kw: Any) -> dict:
            with self._lk:
                self.asked.append((str(key), qid))
            return super().answer(qid=qid, key=key, **kw)

    cls = CountingFakeV4 if counting else QV4.FakeBackendV4
    return cls(fake_policy(policy), exhaustive=exhaustive)


class StoreOnlyV4:
    """The backend of the saved mode: it never calls anything. A key that is not stored reaches answer(): it is
    counted as missing and answered as a bad output (the fact takes its blocking value; must be 0)."""
    name = "store_only"
    exhaustive = False

    def __init__(self):
        self.missing: List[dict] = []
        self._tl = threading.local()
        self._lock = threading.Lock()

    @property
    def where(self) -> Any:
        return getattr(self._tl, "where", None)

    @where.setter
    def where(self, v: Any) -> None:
        self._tl.where = v

    def answer(self, *, qid: str, key: Optional[str] = None, fact: Optional[str] = None, part: Optional[str] = None,
               **_: Any) -> dict:
        with self._lock:
            self.missing.append({"key": key, "qid": qid, "fact": fact, "part": part, "where": self.where})
        return {"answer": "unclear", "quote": "", "bad_output": True, "missing": ""}


# ----------------------------------------------------------------------------------------------- stores
class DevOnlyStore:
    """v3's answers file, read-only, kept to the dev keys. v3's file also holds answers of non-dev runs (hold-out),
    so it is never loaded whole: it is read once, line by line, keeping only (key -> byte offset, length) of each
    whole line (the parsed line is dropped at once). A record is read from disk only when get(key) asks for it,
    and get() is called only for a key the v4 guard asks on one of the 200 dev conversations: so the records kept
    are exactly the dev keys. keep: an optional set of allowed keys (a key outside it is not even indexed).
    put() is refused; keys() and len() give only the records read so far."""
    path: Optional[str] = None
    writable = False

    def __init__(self, path: str, keep: Optional[Iterable[str]] = None):
        self.path = os.path.abspath(path)
        self._keep = None if keep is None else set(keep)
        self._index: Dict[str, Tuple[int, int]] = {}
        self._recs: Dict[str, dict] = {}
        self._lock = threading.Lock()
        h = hashlib.sha256()
        info: Dict[str, Any] = {"path": rel(self.path), "exists": os.path.isfile(self.path), "bytes": 0,
                                "lines": 0, "indexed": 0, "partial_last_line": 0, "bad_lines": 0,
                                "duplicate_keys": 0, "not_kept": 0, "read": "lazy: dev keys only"}
        if info["exists"]:
            off = 0
            with open(self.path, "rb") as f:
                for raw in f:                                      # line by line
                    h.update(raw)
                    n = len(raw)
                    start, off = off, off + n
                    if not raw.endswith(b"\n"):
                        if raw.strip():
                            info["partial_last_line"] = 1         # being written: skipped (as v3's reader)
                        continue
                    if not raw.strip():
                        continue
                    info["lines"] += 1
                    try:
                        key = json.loads(raw.decode("utf-8")).get("key")
                    except (ValueError, UnicodeDecodeError, AttributeError):
                        key = None
                    if not isinstance(key, str):
                        info["bad_lines"] += 1
                        continue
                    if self._keep is not None and key not in self._keep:
                        info["not_kept"] += 1
                        continue
                    if key in self._index:
                        info["duplicate_keys"] += 1                # the first line wins (as JsonlStore)
                        continue
                    self._index[key] = (start, n)
            info["bytes"] = off
            info["sha256"] = h.hexdigest()
        info["indexed"] = len(self._index)
        self.info = info

    def __contains__(self, key: object) -> bool:
        return key in self._index

    def get(self, key: str) -> Optional[dict]:
        with self._lock:
            if key in self._recs:
                return self._recs[key]
            at = self._index.get(key)
            if at is None:
                return None
            fd = os.open(self.path, os.O_RDONLY)
            try:
                raw = os.pread(fd, at[1], at[0])
            finally:
                os.close(fd)
            rec = json.loads(raw.decode("utf-8"))
            if not isinstance(rec, dict) or rec.get("key") != key:
                raise RuntimeError(f"{rel(self.path)} changed while it was read (key {key[:12]})")
            self._recs[key] = rec
            return rec

    def put(self, key: str, rec: dict) -> None:
        raise RuntimeError(f"{rel(self.path)}: the store is read-only")

    def keys(self) -> List[str]:
        with self._lock:
            return list(self._recs)

    def __len__(self) -> int:
        return len(self._recs)


class StoredKeys:
    """`key in stored` over the v4 records and the dev-only v3 store (scoring/v4_dev_answers.py's reuse test)."""

    def __init__(self, first: Iterable[str], second: DevOnlyStore):
        self.first, self.second = set(first), second

    def __contains__(self, key: object) -> bool:
        return key in self.first or key in self.second


def dev_stores(paths_: Sequence[str] = (V4_STORE, V3_STORE)) -> Tuple[Dict[str, dict], DevOnlyStore,
                                                                         List[Dict[str, Any]]]:
    """(the v4 store's records, v3's store as a DevOnlyStore, infos). The v4 store holds only v4 dev answers (the
    online runs keep theirs in their run folders), so it is read whole; v3's is read lazily (dev keys only)."""
    if len(paths_) != 2:
        raise ValueError("dev_stores needs (the v4 store, v3's store)")
    recs, info4 = read_records(paths_[0])
    s3 = DevOnlyStore(paths_[1])
    return recs, s3, [info4, s3.info]


def read_records(path: str) -> Tuple[Dict[str, dict], Dict[str, Any]]:
    """{key: record} of a JSONL answers file, whole lines only (v3 p12's reader); never writes. Refused for v3's
    answers file (it holds non-dev answers: use DevOnlyStore)."""
    if os.path.abspath(path) == os.path.abspath(V3_STORE):
        raise RuntimeError(f"{rel(path)} holds non-dev answers: it is never loaded whole (use DevOnlyStore)")
    if not os.path.isfile(path):
        return {}, {"path": rel(path), "exists": False, "kept": 0}
    from scoring import v3_p12_offline as P12
    recs, info = P12.read_store(path)
    info["exists"] = True
    return recs, info


def merged_records(paths_: Sequence[str]) -> Tuple[Dict[str, dict], List[Dict[str, Any]], Dict[str, str]]:
    """The records of several stores, the first store winning on a key (ChainStore's read order: v4, then v3).
    Returns (records, infos, {key: the store it came from})."""
    out: Dict[str, dict] = {}
    origin: Dict[str, str] = {}
    infos = []
    for p in paths_:
        recs, info = read_records(p)
        infos.append(info)
        for k, r in recs.items():
            if k not in out:
                out[k] = r
                origin[k] = rel(p)
    return out, infos, origin


def memory_store(recs: Dict[str, dict]) -> Any:
    st = _Q().MemoryStore()
    for k, r in recs.items():
        st.put(k, r)
    return st


def asks_since(hook: Any, start: int, where: Any) -> Tuple[List[list], Dict[str, Any]]:
    """The main arm's asks of one check from the hook's ask lines (questions_v4.QuestionsV4.ask_lines: one line per
    ask, cached or not, with where, wording and the status as read): ([key, qid, fact, part, cached, wording],
    {key: status}). Lines of other threads are left out by `where` (unique per check)."""
    lines = list(getattr(hook, "ask_lines", None) or [])[start:]
    w = _jn(where)
    asks: List[list] = []
    status: Dict[str, Any] = {}
    for ln in lines:
        if ln.get("where") != w:
            continue
        asks.append([ln.get("key"), ln.get("qid"), ln.get("fact"), ln.get("part"), bool(ln.get("cached")),
                     ln.get("wording")])
        status.setdefault(ln.get("key"), ln.get("status"))
    return asks, status


# ----------------------------------------------------------------------------------------------- v4 modules (A3, A6)
def _QV4():
    from state_tracker.v4 import questions_v4 as QV4
    return QV4


def _G4():
    from guard import tgr_tracker_v4 as G4
    return G4


def _accepted(fn: Callable[..., Any], want: Dict[str, Any]) -> Dict[str, Any]:
    """The keyword arguments of `want` that fn accepts (all of them if it takes **kwargs)."""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return dict(want)
    if any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):
        return dict(want)
    return {k: v for k, v in want.items() if k in sig.parameters}


def make_questions_v4(backend: Any, store: Any, **extra: Any) -> Any:
    """questions_v4.QuestionsV4(backend, store, ...) with the extra keywords it accepts."""
    cls = _QV4().QuestionsV4
    return cls(backend, store, **_accepted(cls.__init__, extra))


def make_hook(backend_name: str, *, policy: str = "yes", real: Optional[Dict[str, Any]] = None,
              stores: Sequence[str] = (V4_STORE, V3_STORE), log: Optional[Callable[[str], None]] = None,
              ask_log: Optional[str] = None) -> Tuple[Any, Any, Dict[str, Any]]:
    """(hook, backend, store info) of a backend; (None, None, {}) for standin."""
    if backend_name == "standin":
        return None, None, {}
    info: Dict[str, Any] = {}
    Q = _Q()
    if backend_name == "fake":
        backend = fake_backend(policy, exhaustive=(policy == "yes"))
        store = Q.MemoryStore()
    elif backend_name in ("count", "saved"):
        recs, s3, infos = dev_stores(stores)
        info = {"stores": infos, "v4_records": len(recs), "v4_keys_sha256": hashlib.sha256(
            "\n".join(sorted(recs)).encode()).hexdigest()}
        backend = fake_backend(policy, exhaustive=(policy == "yes"), counting=True) if backend_name == "count" \
            else StoreOnlyV4()
        store = _QV4().ChainStore(memory_store(recs), s3)        # v4 first, then v3's dev keys (read-only)
    elif backend_name == "real":
        if not real or not real.get("ledger") or not real.get("run_id"):
            raise Q.RealModeRefused("the real backend needs the checked real-mode flags and the dev ledger")
        if not ledger_locked(real["ledger"]):
            raise Q.RealModeRefused("the real backend needs the dev ledger lock (check_real_flags takes it)")
        QV4 = _QV4()
        s3 = DevOnlyStore(V3_STORE)
        store = QV4.ChainStore(Q.JsonlStore(V4_STORE, writable=True), s3)
        backend = QV4.RealBackendV4(real["approved"], real["max_usd"], real["max_calls"], approval_flag=True,
                                    log=log)
        install_ledger(backend, real["ledger"], real["run_id"])          # before the first call
        info = {"stores": [rel(V4_STORE) + " (writable)", s3.info], "ledger": rel(real["ledger"]),
                "ask_log": rel(ask_log) if ask_log else None}
    else:
        raise ValueError(f"unknown backend {backend_name!r}")
    hook = make_questions_v4(backend, store, ask_log=ask_log)
    if getattr(backend, "doc", "x") is None:
        backend.doc = getattr(hook, "doc", None)
    return hook, backend, info


def build_guard_v4(domain: str, meaning: str, answers: Any = None) -> Any:
    """The v4 guard of one domain (guard/tgr_tracker_v4.build): messages = rule, lazy, no freeze needed offline."""
    G4 = _G4()
    want: Dict[str, Any] = {"meaning": meaning, "messages": "rule", "lazy": True, "require_freeze": False}
    if meaning == "tiny":
        want["answers"] = answers
    return G4.build(domain, **_accepted(G4.build, want))


def where_of(run_id: str, ch: Any, arm: str) -> Dict[str, Any]:
    """code_change_map §0.2 item 7: {run_id, step, domain, task, trial, arm, check}."""
    c = ch.conv
    return {"run_id": run_id, "step": "DEV", "domain": c.domain, "task": f"{c.dataset}|{c.conv_id}",
            "trial": c.trial, "arm": arm, "check": ch.check_idx}


def run_guard_v4(tgr: Any, ch: Any, judged: Dict[str, dict], blocks: List[dict], *,
                 conv_cls: Any = None, make_step_fn: Any = None) -> Dict[str, Any]:
    """One check through a v4 guard, as fork/offline_v3.run_guard, with the arm's per-conversation block memory
    (conv.v4_blocks) so the transfer escape sees the earlier v4 blocks of this conversation."""
    from fork import offline_v3 as O
    if conv_cls is None:
        from method_tgr.runtime import Conversation as conv_cls          # runner copy (path set by fork.offline_v3)
    if make_step_fn is None:
        from repro_online.guards import make_step as make_step_fn
    tgr.set_given(judged)
    step = make_step_fn(list(ch.history), ch.msg, ch.n_exec)
    conv = conv_cls(trace=list(ch.past))
    conv.v4_blocks = blocks
    rec = tgr._step(conv, step)
    got = getattr(conv, "v4_blocks", blocks)
    if got is not blocks:                                   # the guard replaced the list: keep its content
        blocks[:] = list(got or [])
    rec["trace_len_before"] = len(ch.past)
    return O.result_of(rec, "tgr_tracker_v4")


# ----------------------------------------------------------------------------------------------- D5 at the block
def attach_capture(g: Any) -> Any:
    """Keep, per thread, what the guard's rule message got at a block (as scoring/v4_message_check.py's Capture):
    the violated rules and the check's data (tool, args, results, state, view)."""
    if getattr(g, "_v4cap", None) is not None:
        return g
    orig = g._feedback
    g._v4cap = threading.local()

    def fb(step, a_text, violated, current, judged, meter, rec):
        text = orig(step, a_text, violated, current, judged, meter, rec)
        d = g._v3tls.data
        if d is None:
            try:
                d = g._message_data(step)
            except Exception:  # noqa: BLE001 - no data: the fix check says so
                d = None
        g._v4cap.items = {"violated": copy.deepcopy(violated), "data": d}
        return text
    g._feedback = fb
    return g


def take_capture(g: Any) -> Optional[dict]:
    tl = getattr(g, "_v4cap", None)
    if tl is None:
        return None
    cap = getattr(tl, "items", None)
    tl.items = None
    return cap


def fix_check(g: Any, domain: str, cap: Optional[dict]) -> Dict[str, Any]:
    """D5 for one block: A7's fixable_line_problems on the message builder's plan (guard.feedback_v4.explain on the
    captured inputs). {"ok", "problems"}; any failure is not ok."""
    if cap is None or cap.get("data") is None:
        return {"ok": False, "problems": ["no captured message inputs"]}
    try:
        from scoring import v4_message_check as MC          # agent A7
        FB = importlib.import_module(getattr(_G4(), "FEEDBACK_MODULE", "guard.feedback_v4"))
        d = cap["data"]
        plan = FB.explain(domain, d["tool"], d["args"], cap["violated"], d["results"], d["state"], d["view"],
                          g.rule_table, g.rule_set)
        probs = list(MC.fixable_line_problems(plan, FB))
    except Exception as e:  # noqa: BLE001 - counted as a failed message
        return {"ok": False, "problems": [f"checker error {type(e).__name__}: {e}"[:200]]}
    return {"ok": not probs, "problems": probs[:5]}


# ----------------------------------------------------------------------------------------------- rows
def rule_ids(rules: Any) -> List[str]:
    return [str(r.get("rule_id")) for r in (rules or []) if isinstance(r, dict)]


def _jn(x: Any) -> Any:
    return json.loads(json.dumps(x, default=str))


def short_v4(res: Optional[dict], *, asks: Optional[List[list]] = None, status: Optional[Dict[str, Any]] = None,
             world: Optional[Callable[[Dict[str, Any]], Any]] = None) -> Optional[dict]:
    """The compact row part of one arm's result (v3 p12 _short3 layout, plus rec["v4"], the message, statuses)."""
    if res is None:
        return None
    rec = res["record"]
    v = rec.get("v3") or {}
    facts = v.get("facts") or {}
    out: Dict[str, Any] = {
        "d": res["decision"], "viol": rule_ids(rec.get("violated_rules")),
        "f": {nm: [x.get("value"), x.get("source")] for nm, x in facts.items()},
        "probs": {nm: x["problems"] for nm, x in facts.items() if x.get("problems")},
        "serr": [e.get("kind") for e in v.get("state_errors") or []],
        "ferr": [e.get("fact") for e in v.get("fact_errors") or []],
        "fb": bool((v.get("message") or {}).get("fallback")), "unknown": len(v.get("unknown") or []),
        "switches": v.get("switches"), "v4": _jn(rec.get("v4") or {}),
        "blocking_facts": _jn(rec.get("blocking_facts")) if rec.get("blocking_facts") is not None else None}
    if res["decision"] == "block":
        out["msg"] = res.get("feedback_text")
    if asks is not None:
        asked = sorted({a[2] for a in asks if a[2]})
        out["asks"] = asks
        out["parts"] = {nm: {pid: [p.get("value"), p.get("source"), p.get("how")] for pid, p in
                             (facts[nm].get("parts") or {}).items()} for nm in asked if nm in facts}
        out["status"] = dict(status or {})
    if world is not None and facts:
        try:
            out["world"] = world(facts)
        except Exception:  # noqa: BLE001 - a v4 fact the v3 world reader does not know: no world values
            out["world"] = None
    return out


class Ctx:
    """What a worker needs: backend, hook, guards per thread, labels."""

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.backend_name = cfg["backend"]
        self.hook, self.backend, self.store_info = make_hook(
            cfg["backend"], policy=cfg.get("policy") or "yes", real=cfg.get("real"),
            stores=cfg.get("stores") or (V4_STORE, V3_STORE), log=say, ask_log=cfg.get("ask_log"))
        self.tl = threading.local()
        self.frozen = bool(cfg.get("frozen", True))
        from scoring import v3_labels as L
        self.index, self.tool_labels = L.load_index(), L.load_tool_labels()

    def guard(self, arm: str, domain: str) -> Any:
        g = getattr(self.tl, "guards", None)
        if g is None:
            g = self.tl.guards = {}
        if (arm, domain) not in g:
            if arm == "main" and self.backend_name != "standin":
                g[(arm, domain)] = attach_capture(build_guard_v4(domain, "tiny", self.hook))
            elif arm == "main" or self.backend_name == "standin":
                g[(arm, domain)] = attach_capture(build_guard_v4(domain, "saved_judge"))
            else:
                g[(arm, domain)] = build_guard_v4(domain, "saved_judge")
        return g[(arm, domain)]


def _decide(fn: Callable[[], Dict[str, Any]], arm: str, ckey: str, errors: List[dict],
            counts: collections.Counter) -> Optional[Dict[str, Any]]:
    try:
        return fn()
    except hard_stops():
        raise
    except Exception as e:  # noqa: BLE001 - counted, listed (a guard run error is a pass-mark failure)
        counts[f"errors: {arm}"] += 1
        if len(errors) < 50:
            errors.append({"ckey": ckey, "guard": arm, "error": f"{type(e).__name__}: {e}"[:300]})
        return None


def conv_rows(ctx: Ctx, conv: Any, pos: int, counts: collections.Counter, walk: collections.Counter,
              errors: List[dict], problems: List[str]) -> List[dict]:
    """The rows of one conversation (every check, in order)."""
    from fork import offline_v3 as O
    from scoring import v3_audit as A
    from scoring import v3_labels as L
    from scoring import v3_p9_run as P9
    from scoring import v3_offline_eval as E
    if conv.side != "dev" or L.is_holdout_ckey(conv.conv_key + "|0"):
        raise L.HoldOutData(f"{conv.conv_key}: not development data")
    labs, probs = L.conversation_labels(conv, ctx.index, ctx.tool_labels, call_of=O.call_of)
    problems += probs
    has_main = ctx.backend_name != "standin"
    gm = ctx.guard("main", conv.domain) if has_main else None
    gs = ctx.guard("standin", conv.domain)
    if gm is not None:
        gm.state_source = P9.WalkStates(conv, walk, ctx.cfg.get("verify_every", 10))
    gs.state_source = P9.WalkStates(conv, collections.Counter() if has_main else walk,
                                    0 if has_main else ctx.cfg.get("verify_every", 10))
    blocks: Dict[str, List[dict]] = {"main": [], "standin": []}
    run_id = ctx.cfg["run_id"]
    rows: List[dict] = []
    ep = conv.ep
    try:
        for ch in conv.checks():
            counts["checks"] += 1
            judged = ch.saved_judge()
            if judged is None:
                counts["judge skipped in the source run (given {})"] += 1
                judged = {}
            ix = ctx.index.get(ch.ckey) or {"bin": None, "history_len": None}
            lab = labs.get(ch.ckey)
            write = lab is not None
            world = None
            if write:
                docs = ctx.cfg.get("docs") or {}
                if conv.domain in docs:
                    world = (lambda facts, d=docs[conv.domain], dom=conv.domain: L.world_values(dom, {
                        n: {"value": x.get("value"), "parts": x.get("parts") or {}} for n, x in facts.items()}, d))
            rm = None
            asks: Optional[List[list]] = None
            status: Dict[str, Any] = {}
            cap_m = None
            if gm is not None:
                wh = where_of(run_id, ch, "tgr_tracker_v4")
                start = len(getattr(ctx.hook, "ask_lines", None) or [])
                ctx.hook.where = wh
                if isinstance(ctx.backend, StoreOnlyV4):
                    ctx.backend.where = ch.ckey
                take_capture(gm)
                rm = _decide(lambda: run_guard_v4(gm, ch, judged, blocks["main"]), "v4", ch.ckey, errors, counts)
                asks, status = asks_since(ctx.hook, start, wh)
                cap_m = take_capture(gm)
            take_capture(gs)
            rs = _decide(lambda: run_guard_v4(gs, ch, judged, blocks["standin"]), "v4_standin", ch.ckey, errors,
                         counts)
            cap_s = take_capture(gs)
            rf = None
            if ctx.frozen:
                rf = _decide(lambda: O.decide(ch, "frozen", judged=judged), "frozen", ch.ckey, errors, counts)
            main = short_v4(rm, asks=asks, status=status, world=world) if has_main else \
                short_v4(rs, world=world)
            if main is not None and main["d"] == "block":
                main["fix"] = fix_check(gm if has_main else gs, conv.domain, cap_m if has_main else cap_s)
            saved = ch.saved
            asked = sorted({a[2] for a in (asks or []) if a[2]})
            rows.append({
                "ck": ch.ckey, "conv": conv.conv_key, "pos": pos, "i": ch.check_idx, "ds": conv.dataset,
                "part": A.part_of(conv.dataset), "agent": conv.agent, "dom": conv.domain, "src": conv.source_guard,
                "tool": ch.tool, "write": write, "bin": ix["bin"], "hl": ix["history_len"],
                "task": L.task_key(conv.domain, conv.split, conv.task_id), "reward": ep.get("reward"),
                "saved": {"d": ch.saved_decision, "blocked": ch.blocked, "cap": ch.cap_override, "judged": ch.judged,
                          "viol": A._rule_ids(saved.get("violated_rules")), "vals": E._vals(saved.get("judge")),
                          "setter": E._setters(saved.get("judge")),
                          "judge_skipped": bool((saved.get("tracker") or {}).get("judge_skipped")),
                          "asked_judge": bool(saved.get("judge"))},
                "fz": E._short(rf), "v2": None, "label": lab, MAIN: main,
                STANDIN: short_v4(rs) if has_main else None,
                "judge": {f: (judged.get(f) or {}).get("value") for f in asked if f in judged}})
    finally:
        if gm is not None:
            gm.state_source = None
        gs.state_source = None
    return rows


# ----------------------------------------------------------------------------------------------- safety, workers
_W: Dict[str, Any] = {}


def safety_v4(block_net: bool) -> None:
    """As v3 p11's safety: writes only under output/, every judge / user-simulator / runner LLM call refused, TGR's
    judge counted and refused; the network refused too unless this is the real backend (its client must connect)."""
    from fork import points_tgr  # noqa: F401  (runner path)
    from fork import rebuild_check as RC
    from guard import write_guard
    from scoring import v3_offline_eval as E
    if block_net:
        sys.addaudithook(RC._no_network)
    os.makedirs(E.FIG_DIR, exist_ok=True)
    write_guard.install([paths.OUTPUT_DIR, E.FIG_DIR])
    from repro_runtime import calls                     # runner copy
    calls._llm = RC._NoLLM()
    if RC.venv_available():
        import tau_bench.envs.user as user_mod
        user_mod.completion = RC._no_user
    if block_net:
        _Q().block_network()
    E.install_counters()


def worker_init(cfg: Dict[str, Any]) -> Ctx:
    key = json.dumps({k: v for k, v in cfg.items() if k not in ("real", "docs")}, sort_keys=True, default=str)
    if _W.get("key") == key:
        return _W["ctx"]
    if not _W.get("safe"):
        safety_v4(block_net=cfg["backend"] != "real")
        _W["safe"] = True
    _QV4()                                               # registers the _v4 helper names
    G4 = _G4()
    if hasattr(G4, "register"):
        try:
            G4.register()
        except Exception:  # noqa: BLE001 - registered already in this process
            pass
    if cfg.get("docs") is None:
        try:
            cfg = dict(cfg, docs=load_v4_docs())
        except Exception as e:  # noqa: BLE001 - the guard build reports the same problem; world values are skipped
            say(f"[init] v4 fact files not loaded for the world values: {type(e).__name__}: {e}"[:300])
            cfg = dict(cfg, docs={})
    ctx = Ctx(cfg)
    _W.update(key=key, ctx=ctx)
    return ctx


def load_v4_docs() -> Dict[str, dict]:
    """The v4 fact files (state_tracker/v4/facts_v4_<domain>.json), via the guard's checked loader when there is one."""
    G4 = _G4()
    out = {}
    for d in ("retail", "airline"):
        fn = getattr(G4, "load_checked_facts_v4", None)
        if fn is not None:
            out[d] = fn(d)
        else:
            with open(os.path.join(PC_DIR, "state_tracker", "v4", f"facts_v4_{d}.json"), encoding="utf-8") as f:
                out[d] = json.load(f)
    return out


def select(limit: Optional[int], counts: Optional[collections.Counter] = None) -> Iterable[Any]:
    """The p12a development conversations (v3 p12's selection; asserts development data)."""
    from scoring import v3_p12_offline as P12
    if tuple(P12.DEV_SETS) != DEV_SETS:
        raise RuntimeError("v3_p12_offline.DEV_SETS changed")
    return P12.select_conversations("dev", limit, counts)


def _result(ctx: Ctx, rows: List[dict], counts: collections.Counter, walk: collections.Counter, sel: Any,
            errors: List[dict], problems: List[str], t0: float, extra: Dict[str, Any]) -> Dict[str, Any]:
    from scoring import v3_p9_run as P9
    out = {"rows": rows, "counts": dict(counts), "walk": dict(walk), "selection": dict(sel or {}), "errors": errors,
           "problems": problems, "seconds": round(time.time() - t0, 1), "store": ctx.store_info,
           "judge_calls": dict(P9.COUNT), "network_events": len(_Q().network_events())}
    b = ctx.backend
    out["missing"] = list(getattr(b, "missing", []) or [])
    out["backend_calls"] = int(getattr(b, "calls", 0) or 0)
    out["counted_keys"] = sorted({k for k, _ in getattr(b, "asked", [])})
    out.update(extra)
    return out


def run_shard(task: Tuple[Dict[str, Any], int, int]) -> Dict[str, Any]:
    """One shard of the process pool: the selected conversations with (index in the selection) % n == k."""
    cfg, k, n = task
    ctx = worker_init(cfg)
    t0 = time.time()
    counts: collections.Counter = collections.Counter()
    walk: collections.Counter = collections.Counter()
    sel: collections.Counter = collections.Counter()
    errors: List[dict] = []
    problems: List[str] = []
    rows: List[dict] = []
    for j, conv in enumerate(select(cfg.get("limit"), sel)):
        if j % n != k:
            continue
        counts["conversations"] += 1
        rows += conv_rows(ctx, conv, conv.ordinal, counts, walk, errors, problems)
    return _result(ctx, rows, counts, walk, sel, errors, problems, t0, {"k": k, "n": n})


def run_threads(cfg: Dict[str, Any], workers: int) -> List[Dict[str, Any]]:
    """The real backend: one process, `workers` threads (one guard set per thread, one shared hook and budget); a
    hard stop in one thread fires the budget stop, the others stop before their next conversation."""
    from concurrent.futures import ThreadPoolExecutor
    ctx = worker_init(cfg)
    t0 = time.time()
    stop = threading.Event()
    sel: collections.Counter = collections.Counter()
    convs = list(select(cfg.get("limit"), sel))

    def work(conv: Any) -> Dict[str, Any]:
        if stop.is_set():
            return {"rows": [], "counts": {}, "walk": {}, "errors": [], "problems": [], "skipped": 1}
        c: collections.Counter = collections.Counter(conversations=1)
        w: collections.Counter = collections.Counter()
        errs: List[dict] = []
        probs: List[str] = []
        try:
            rows = conv_rows(ctx, conv, conv.ordinal, c, w, errs, probs)
        except BaseException:
            stop.set()
            b = getattr(ctx.backend, "budget", None)
            if b is not None:
                b.stop("stopped after a hard stop in another worker")
            raise
        return {"rows": rows, "counts": dict(c), "walk": dict(w), "errors": errs, "problems": probs}

    parts: List[Dict[str, Any]] = []
    first: List[BaseException] = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="v4dev") as ex:
        for fut in [ex.submit(work, cv) for cv in convs]:
            try:
                parts.append(fut.result())
            except BaseException as e:  # noqa: BLE001 - kept, raised after the drain
                first.append(e)
    if first:
        hard = [e for e in first if isinstance(e, hard_stops())]
        raise (hard or first)[0]
    counts: collections.Counter = collections.Counter()
    walk: collections.Counter = collections.Counter()
    for p in parts:
        counts.update(p["counts"])
        walk.update(p["walk"])
    rows = [r for p in parts for r in p["rows"]]
    errors = [e for p in parts for e in p["errors"]]
    problems = [x for p in parts for x in p["problems"]]
    res = _result(ctx, rows, counts, walk, sel, errors, problems, t0, {"k": 0, "n": 1})
    b = ctx.backend
    res["spend"] = {"usd": getattr(getattr(b, "budget", None), "spent", None),
                    "calls": getattr(getattr(b, "budget", None), "calls", None),
                    "usage": dict(getattr(b, "usage", {}) or {})}
    return [res]


def order_key(r: dict) -> Tuple[int, int, int]:
    return (DEV_SETS.index(r["ds"]), r["pos"], r["i"])


def tag_of(backend: str, policy: Optional[str]) -> str:
    return f"{backend}_{policy}" if backend in ("fake", "count") else backend


def outputs(tag: str, out_dir: Optional[str] = None) -> Dict[str, str]:
    base = out_dir or OUT_DIR
    out = {"rows": os.path.join(base, f"offline_{tag}_rows.jsonl"), "meta": os.path.join(base, f"offline_{tag}_meta.json"),
           "md": os.path.join(base, f"offline_{tag}_report.md")}
    for p in out.values():
        ap = os.path.abspath(p)
        if ap.startswith(os.path.abspath(V3_OUT) + os.sep) or ap in {os.path.abspath(x) for x in
                                                                    (V3_STORE, V4_STORE, CASES_STORE)}:
            raise RuntimeError(f"refused: {rel(ap)} must never be written by this script")
    return out


def write_jsonl(path: str, rows: Iterable[dict]) -> None:
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")
    os.replace(path + ".tmp", path)


def write_json(path: str, doc: Any) -> None:
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, sort_keys=True, ensure_ascii=False, default=str)
        f.write("\n")
    os.replace(path + ".tmp", path)


def read_jsonl(path: str) -> List[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def merge_counts(results: Iterable[Dict[str, Any]], key: str) -> Dict[str, int]:
    c: collections.Counter = collections.Counter()
    for r in results:
        c.update(r.get(key) or {})
    return dict(sorted(c.items()))


def phase_run(a: argparse.Namespace, out: Dict[str, str]) -> Dict[str, Any]:
    """Run every selected check; write the rows and the run meta."""
    from scoring import v3_labels as L
    t0 = time.time()
    run_id = f"v4dev_{tag_of(a.backend, a.policy)}_{utc()}"
    cfg = {"backend": a.backend, "policy": a.policy, "limit": a.limit, "verify_every": a.verify_every,
           "run_id": run_id, "ask_log": (os.path.join(os.path.dirname(out["rows"]), f"asks_{run_id}.jsonl")
                                         if a.backend == "real" else None), "frozen": a.backend != "real" and not a.no_frozen,
           "real": dict(a.real, run_id=run_id) if a.real else None, "stores": tuple(a.stores)}
    if a.backend == "real":
        results = run_threads(cfg, a.workers)
    elif a.workers == 1:
        results = [run_shard((cfg, k, a.shards)) for k in range(a.shards)]
    else:
        import multiprocessing
        mp = multiprocessing.get_context("spawn")
        results = []
        with mp.Pool(a.workers) as pool:
            for r in pool.imap_unordered(run_shard, [(cfg, k, a.shards) for k in range(a.shards)]):
                results.append(r)
                say(f"[run] shard {r['k']}/{r['n']} back ({len(results)} of {a.shards}), {time.time() - t0:.0f} s")
    rows = sorted((r for res in results for r in res["rows"]), key=order_key)
    if len({r["ck"] for r in rows}) != len(rows):
        raise RuntimeError("a check key twice in the rows")
    if any(L.is_holdout_ckey(r["ck"]) for r in rows):
        raise L.HoldOutData("a hold-out check in the development rows")
    write_jsonl(out["rows"], rows)
    stores = {json.dumps(r.get("store"), sort_keys=True, default=str) for r in results}
    meta = {"backend": a.backend, "policy": a.policy if a.backend in ("fake", "count") else None,
            "run_id": cfg["run_id"], "counts": merge_counts(results, "counts"), "walk": merge_counts(results, "walk"),
            "selection": results[0]["selection"] if results else {},
            "judge_calls": merge_counts(results, "judge_calls"),
            "network_events": sum(r["network_events"] for r in results),
            "problems": sorted(p for r in results for p in r["problems"]),
            "errors": sorted((e for r in results for e in r["errors"]), key=lambda e: (e["ckey"], e["guard"]))[:50],
            "missing": sorted((m for r in results for m in r.get("missing") or []),
                              key=lambda m: (str(m.get("where")), str(m.get("key")))),
            "backend_calls": sum(r.get("backend_calls", 0) for r in results),
            "counted_keys": sorted({k for r in results for k in r.get("counted_keys") or []}),
            "store": json.loads(sorted(stores)[0]) if stores else None, "stores_differ": len(stores) > 1,
            "spend": results[0].get("spend") if a.backend == "real" and results else None,
            "dev_ledger": ({"at_start": (a.real or {}).get("room"), "at_end": DevLedger(a.real["ledger"]).read()}
                           if a.backend == "real" and a.real else None),
            "worker_seconds": round(sum(r["seconds"] for r in results), 1), "seconds": round(time.time() - t0, 1),
            "shards": a.shards if a.backend != "real" else 1, "workers": a.workers, "limit": a.limit,
            "rows": len(rows), "rows_sha256": sha256_file(out["rows"]),
            "when": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}
    write_json(out["meta"], meta)
    say(f"[run] {len(rows)} rows, {meta['seconds']} s; counts {json.dumps(meta['counts'])[:1200]}")
    return meta


# ======================================================================================================= summary
def summarize(rows: List[dict], meta: Dict[str, Any]) -> Dict[str, Any]:
    """The counts of the offline report (code paths, K2 code strictness, escapes, and the decision audit)."""
    c: collections.Counter = collections.Counter()
    lines: collections.Counter = collections.Counter()
    by_tool: Dict[str, collections.Counter] = {}
    for r in rows:
        m, s, f = r.get(MAIN), r.get(STANDIN), r.get(FROZEN)
        c["checks"] += 1
        c["write checks"] += int(bool(r.get("write")))
        c["saved blocks"] += int(r["saved"]["d"] == "block")
        if f:
            c["frozen blocks"] += int(f["d"] == "block")
        if s:
            c["stand-in blocks"] += int(s["d"] == "block")
            c["stand-in state errors"] += len(s.get("serr") or [])
        if not m:
            c["checks with no main decision"] += 1
            continue
        blk = m["d"] == "block"
        c["main blocks"] += int(blk)
        c["main state errors"] += len(m.get("serr") or [])
        c["main fact errors"] += len(m.get("ferr") or [])
        c["main message fallbacks"] += int(bool(m.get("fb")))
        v4 = m.get("v4") or {}
        c["v4 tiny blocks"] += int(blk and bool(v4.get("tiny_block")))
        c["v4 escapes"] += int(bool(v4.get("escape")))
        c["v4 re-asks"] += len(v4.get("reasks") or [])
        c["v4 unclear allowed"] += len(v4.get("unclear_allowed") or [])
        c["v4 fast path (K1 plain yes by code)"] += len(v4.get("fast_path") or [])
        c["asks"] += len(m.get("asks") or [])
        if blk:
            t = by_tool.setdefault(r["tool"], collections.Counter())
            t["main blocks"] += 1
            for recs in (v4.get("missing") or {}).values():
                for x in recs or []:
                    lines[str((x or {}).get("line"))] += 1
        if s and s["d"] != m["d"]:
            c["main vs stand-in decisions differ"] += 1
    out: Dict[str, Any] = {"counts": dict(sorted(c.items())), "missing_lines_at_blocks": dict(lines.most_common()),
                           "blocks_by_tool": {k: dict(v) for k, v in sorted(by_tool.items())}}
    try:
        from scoring import v3_audit as A
        from scoring import v3_offline_eval as E
        an = E.Ana(rows, A.load_tables())
        aud = E.sec_audit(an)
        aud.pop("_p4_check", None)
        out["audit"] = {g: aud.get(g, {}).get("part=main", {}) for g in ("saved", "frozen", "v3")}
        classes, _ = E.sec_classes(an)
        out["classes"] = classes["exact"]["counts"]["all"].get("all", {})
    except Exception as e:  # noqa: BLE001 - reported, the rest of the report stands
        out["audit_error"] = f"{type(e).__name__}: {e}"[:300]
    return out


def render(summary: Dict[str, Any], meta: Dict[str, Any], out: Dict[str, str]) -> str:
    c = summary["counts"]
    w: List[str] = []
    w.append(f"# Tracker v4: the v4 guard offline on the 200 development conversations ({meta.get('backend')}"
             + (f", policy {meta['policy']}" if meta.get("policy") else "") + ")")
    w.append("")
    w.append("> **Development check, not a result.** In-sample: the facts and questions were designed on these "
             "conversations.")
    w.append("")
    w.append(f"Written by `scoring/v4_offline_eval.py` on {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. "
             f"Run `{meta.get('run_id')}`; judge calls refused {sum((meta.get('judge_calls') or {}).values())}; network "
             f"events {meta.get('network_events')}; missing answers {len(meta.get('missing') or [])}; guard errors "
             f"{sum(v for k, v in (meta.get('counts') or {}).items() if k.startswith('errors: '))}.")
    w.append("")
    w.append("| count | n |")
    w.append("|---|---|")
    for k, v in c.items():
        w.append(f"| {k} | {v:,} |")
    w.append("")
    w.append("## Missing lines named at the main arm's blocks (by line kind)")
    w.append("")
    w.append("| line | n |")
    w.append("|---|---|")
    for k, v in summary["missing_lines_at_blocks"].items():
        w.append(f"| {k} | {v} |")
    w.append("")
    w.append("## Blocks by tool (main arm)")
    w.append("")
    w.append("| tool | blocks |")
    w.append("|---|---|")
    for k, v in summary["blocks_by_tool"].items():
        w.append(f"| {k} | {v.get('main blocks', 0)} |")
    w.append("")
    w.append("## Decision audit by outcome (write checks, p4 buckets; τ-bench's labels)")
    w.append("")
    if summary.get("audit"):
        from scoring import v3_offline_eval as E
        w.append("| bucket | saved | frozen | v4 |")
        w.append("|---|---|---|---|")
        for b in E.BUCKETS:
            w.append(f"| {E.BUCKET_SHORT.get(b, b)} | " + " | ".join(
                str(summary["audit"].get(g, {}).get(b, 0)) for g in ("saved", "frozen", "v3")) + " |")
        w.append("")
        w.append("Changed decisions (v4 vs saved) by class: " + ", ".join(
            f"{k} {v}" for k, v in sorted((summary.get("classes") or {}).items()) if "|" not in k and ":" not in k))
    else:
        w.append(f"Not computed: {summary.get('audit_error')}")
    w.append("")
    w.append(f"Rows: `{rel(out['rows'])}` (sha256 `{meta.get('rows_sha256')}`), {meta.get('rows')} rows; "
             f"{meta.get('seconds')} s wall, {meta.get('workers')} workers.")
    return "\n".join(w) + "\n"


# ----------------------------------------------------------------------------------------------- main
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="python -B -m scoring.v4_offline_eval", description=__doc__.split("\n")[0])
    ap.add_argument("--backend", choices=BACKENDS, default="standin")
    ap.add_argument("--policy", choices=FAKE_POLICIES, default="yes", help="fake / count: the fake answer")
    ap.add_argument("--phases", default="run,report", help="comma list of run, report")
    ap.add_argument("--workers", type=int, default=MAX_WORKERS)
    ap.add_argument("--shards", type=int, default=16)
    ap.add_argument("--limit", type=int, default=None, help="conversations per data set (default 50 = p12a's)")
    ap.add_argument("--verify-every", type=int, default=10)
    ap.add_argument("--no-frozen", action="store_true", help="skip the frozen TGR arm")
    ap.add_argument("--out-dir", default=None, help="write the outputs here (tests)")
    ap.add_argument(MAIN_CHAT_FLAG, dest="main_chat", action="store_true", help="real backend: the main chat runs it")
    ap.add_argument("--approved", default=None, help="real backend: the user's own approval words for this step")
    ap.add_argument("--max-usd", default=None)
    ap.add_argument("--max-calls", type=int, default=None)
    a = ap.parse_args(argv)
    if not 1 <= a.workers <= MAX_WORKERS:
        ap.error(f"--workers must be 1 to {MAX_WORKERS}")
    if a.limit is not None and not 1 <= a.limit <= DEV_LIMIT:
        ap.error(f"--limit must be 1 to {DEV_LIMIT} (the p12a set; never more)")
    a.stores = (V4_STORE, V3_STORE)
    return a


def main(argv: Optional[List[str]] = None) -> int:
    a = parse_args(argv)
    Q = _Q()
    room: Dict[str, Any] = {}
    try:
        got = check_real_flags(a.backend, main_chat=a.main_chat, approved=a.approved, max_usd=a.max_usd,
                               max_calls=a.max_calls, info=room)
    except Q.RealModeRefused as e:
        say(f"REFUSED: {e}")
        return 2
    a.real = None if got is None else {"approved": got[0], "max_usd": got[1], "max_calls": got[2],
                                       "ledger": DEV_LEDGER, "room": room}
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise SystemExit("set PYTHONHASHSEED=0 (the hash seed must be fixed before Python starts)")
    from state_tracker.v3.frozen import check_manifest
    check_manifest()
    out = outputs(tag_of(a.backend, a.policy), a.out_dir)
    os.makedirs(os.path.dirname(out["rows"]), exist_ok=True)
    phases = [p for p in a.phases.split(",") if p]
    if "run" in phases:
        meta = phase_run(a, out)
    else:
        with open(out["meta"], encoding="utf-8") as f:
            meta = json.load(f)
    from guard import tgr_tracker_v3 as G3
    G3.check_frozen_v3()                                  # the v3 files are unchanged after the run
    if "report" in phases:
        rows = read_jsonl(out["rows"])
        summary = summarize(rows, meta)
        write_json(out["meta"].replace("_meta.json", "_summary.json"), summary)
        with open(out["md"], "w", encoding="utf-8") as f:
            f.write(render(summary, meta, out))
        say(f"[report] wrote {rel(out['md'])}; counts {json.dumps(summary['counts'])[:1500]}")
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.exit(main())
