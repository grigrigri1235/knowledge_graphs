"""Tracker v3, part 12 steps 3-4 (scoring.v3_p12_offline): p11's offline test with NO judge (meaning = tiny), and the
tiny answers vs the judge's saved answers. $0: no LLM call, no network, never a client.

Plan: docs/planning/tracker_v3/p12.md; pass marks P12.1 / P12.2 (= P11.1-P11.3, P11.5 with meaning = tiny) in
output/eval_v3/preregistration.md. p11's code (scoring/v3_offline_eval.py, v3_labels.py) is imported, never edited;
p11's outputs (output/eval_v3/p11_*, gates.md, output/logs/v3_p11_*) are never written.

Two sides
  dev      (default) the development bug check of p12 step 3: the first 50 conversations of each of the 4 strong-agent
           development data sets, chosen exactly as `scoring/v3_p8_dryrun.py --limit-convs 50` chose the
           conversations p12a answered (v3_p8_dryrun.side_conversations: side dev, agent luna, the first N of each data
           set). "Development check, not a result."
  holdout  p12 step 4, the hold-out ONCE: ours.p10_luna_val, partner.luna_val and the Stage B tries forked from them
           (v3_p8_dryrun.HOLDOUT_REAL_DATASETS, agent luna: what p12b answers). LOCKED: runs only with both flags
           --holdout --i-am-the-main-chat-holdout-look; never writes a development file; refuses to run its "run"
           phase again when its rows file exists (the hold-out is opened once). Tool labels: the hold-out labels file
           of scoring/v3_p12_holdout_labels.py (run that first).

The answers: read from the store only (output/eval_v3/questions_answers.jsonl, or --store). read_store() is a
whole-line JSONL reader: a last line without its newline (half written) is skipped and counted; a line that is no JSON
is counted. The guard's answers hook (questions.Questions) gets an in-memory copy of the store and a backend that
makes no call: an answer that is not in the store is counted as MISSING (it takes the blocking value; it must be 0),
never asked. The store file is never written.

What runs per check (worker processes, sharded by conversation; p11's offline base fork/offline_v3.py):
  v3 (tiny)       guard/tgr_tracker_v3.py, facts = v3, meaning = tiny, messages = rule, lazy (as p11's v3 and the
                  online guard). messages = rule: TGR's decision does not depend on the message (P10.6), and the rule
                  message builder then runs on every tiny block, so its fallbacks are counted (P11.1)
  v3 (stand-in)   p11's arm (meaning = saved_judge) on the same check, for the comparison only
  frozen, v2      as p11 (the audit buckets and the LLM share of the hold-out report)
  labels          τ-bench's tool label of each write check (dev: p11's scoring.v3_labels; hold-out: the same label
                  code on the hold-out labels file), and the objective reasons of P11.5 (p7's raw database scan and
                  τ-bench's find tool on the copy, recomputed here with p7's own helpers; dev: checked against p7's
                  saved rows)

Outputs (side dev / side holdout; --out-dir puts all of them in another folder, for tests):
  output/logs/v3_p12_dev_rows.jsonl, v3_p12_dev_run_meta.json        / v3_p12_holdout_rows.jsonl, ..._run_meta.json
  output/eval_v3/p12_devcheck.md, p12_devcheck.json                   / p12_holdout.md, p12_holdout.json
  output/eval_v3/p12_tiny_vs_judge_dev.md, .jsonl                     / p12_tiny_vs_judge_holdout.md, .jsonl
The tiny-vs-judge files list every (check, fact) where the tiny arm's value differs from the judge's saved value, with
the conversation id, check, question, the prompt text, the quote and both answers (the .md: the ones on a blocked
check, for an independent reviewer; the .jsonl: all).

Definitions (counted in the reports)
  answer problems   a store answer used by the tiny arm with status unclear, quote_failed (the quote is not in the
                    message) or bad_output (not the answer format); each takes the fact's blocking value
  missing answer    a key the tiny arm needed that is not in the store (must be 0)
  block only from an unclear answer   a tiny block where every violated rule (rule table rows) would hold if each fact
                    that took its blocking value because of an answer problem had its other value
  two-key disagreement   a fact where the question parts' answers allow (some value of the code parts would give the
                    fact its allowing value) while the code parts block (no answer could): the "two keys" rule of p8
                    (a question's yes needs the code part agreeing). The evaluator runs every code part first and asks
                    a question only while code leaves the fact open, so this is 0 by construction (a bug check)
  tiny vs judge     per (check, fact) the tiny arm asked a question for: the fact's tiny value vs the judge's saved value
                    of the same fact. A disagreement is "from the question" when the stand-in arm (the same code parts
                    with the judge's value as the answer) gives the judge's side, "from code parts" when even the
                    stand-in differs from the judge (code decided against the judge; p11 counted those already)

Run from predicate_correctness/ (the venv Python; the hash seed fixed):
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m scoring.v3_p12_offline \\
        --workers 2 > output/logs/v3_p12_04_devcheck.log 2>&1
main() first calls state_tracker.v3.frozen.check_manifest(); guard/tgr_tracker_v3.py's build() checks its
FROZEN_SHA256 (checked again at the end). Imports only scoring.v3_* from scoring; never the scorer or gold code.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import itertools
import json
import os
import sys
import time
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from state_tracker import paths                                   # noqa: E402
from scoring import v3_audit as A                                 # noqa: E402
from scoring import v3_labels as L                                # noqa: E402
from scoring import v3_offline_eval as E                          # noqa: E402

LOOK_FLAG = "--i-am-the-main-chat-holdout-look"
SIDES = ("dev", "holdout")
OUT_DIR = E.OUT_DIR
LOGS = E.LOGS
STORE = os.path.join(paths.PC_DIR, "output", "eval_v3", "questions_answers.jsonl")
DEV_SETS = ("stage_a.luna.tgr_frozen", "stage_a.luna.tgr_tracker", "ours.p10_luna_train", "partner.luna_train_v5")
HOLDOUT_SETS = ("ours.p10_luna_val", "partner.luna_val", "stage_b")
DEV_LIMIT = 50
AGENT = "luna"
HOLDOUT_LABELS = os.path.join(OUT_DIR, "tool_labels_holdout.jsonl")
TINY, STANDIN = "v3tiny", "v3"
PROBLEM_STATUSES = ("unclear", "quote_failed", "bad_output")
MISSING = "missing"
EVIDENCE_CHARS = 1200
NAMES = {
    "dev": {"rows": ("logs", "v3_p12_dev_rows.jsonl"), "meta": ("logs", "v3_p12_dev_run_meta.json"),
            "md": ("eval", "p12_devcheck.md"), "json": ("eval", "p12_devcheck.json"),
            "cmp_md": ("eval", "p12_tiny_vs_judge_dev.md"), "cmp_jsonl": ("eval", "p12_tiny_vs_judge_dev.jsonl")},
    "holdout": {"rows": ("logs", "v3_p12_holdout_rows.jsonl"), "meta": ("logs", "v3_p12_holdout_run_meta.json"),
                "md": ("eval", "p12_holdout.md"), "json": ("eval", "p12_holdout.json"),
                "cmp_md": ("eval", "p12_tiny_vs_judge_holdout.md"),
                "cmp_jsonl": ("eval", "p12_tiny_vs_judge_holdout.jsonl")},
}
# Files this module never writes (p11's frozen outputs, the development labels, the store, p8's report).
NEVER_WRITE = (E.REPORT, E.JSON_OUT, E.GATES, E.ROWS, E.RUN_META, E.VAR_ROWS, E.VAR_META, A.LABELS, STORE,
               os.path.join(OUT_DIR, "p8_dryrun.md"), os.path.join(OUT_DIR, "p3_tool_labels.md"))
OWN_FILES = ("scoring/v3_p12_offline.py", "scoring/v3_p12_holdout_labels.py", "tests/test_v3_p12.py")


def say(msg: str) -> None:
    print(msg, flush=True)


def sha256_file(path: str) -> str:
    return E.sha256_file(path)


def rel(path: str) -> str:
    return os.path.relpath(os.path.abspath(path), PC_DIR)


# ----------------------------------------------------------------------------------------------- the hold-out lock
class HoldoutLocked(SystemExit):
    """The hold-out lock refused (exit code 2)."""

    def __init__(self, msg: str):
        super().__init__(2)
        self.msg = msg


_UNLOCKED = {"holdout": False}


def unlock(holdout: bool, look: bool) -> None:
    """Both flags open the hold-out for this process; anything else raises HoldoutLocked."""
    if not (holdout is True and look is True):
        raise HoldoutLocked(f"the hold-out is locked: it is opened once, by the main chat, with --holdout {LOOK_FLAG}")
    _UNLOCKED["holdout"] = True


def require_unlocked() -> None:
    if not _UNLOCKED["holdout"]:
        raise HoldoutLocked("hold-out data was asked for, but the hold-out is locked in this process")


def outputs(side: str, out_dir: Optional[str] = None) -> Dict[str, str]:
    """The output paths of a side; never a development file for the hold-out, never a NEVER_WRITE file."""
    if side not in SIDES:
        raise ValueError(f"side must be one of {SIDES}")
    out = {}
    for k, (where, name) in NAMES[side].items():
        base = out_dir if out_dir else (LOGS if where == "logs" else OUT_DIR)
        out[k] = os.path.abspath(os.path.join(base, name))
    bad = {os.path.abspath(p) for p in NEVER_WRITE} & set(out.values())
    if bad:
        raise HoldoutLocked(f"refused: {sorted(rel(p) for p in bad)} must never be written here")
    if side == "holdout":
        dev = set(outputs("dev", out_dir).values())
        if dev & set(out.values()):
            raise HoldoutLocked("refused: a hold-out output path is a development output path")
    return out


# ----------------------------------------------------------------------------------------------- the store
def read_store(path: str) -> Tuple[Dict[str, dict], Dict[str, Any]]:
    """{key: record} of a JSONL answers file, read whole lines only: a last line without its newline (being written)
    is skipped and counted, a line that is no JSON (or has no key) is counted, a key twice keeps the first (as
    questions.JsonlStore). Never writes."""
    with open(path, "rb") as f:
        raw = f.read()
    info: Dict[str, Any] = {"path": rel(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                            "lines": 0, "kept": 0, "partial_last_line": 0, "bad_lines": 0, "duplicate_keys": 0}
    chunks = raw.split(b"\n")
    tail = chunks.pop()                                # b"" when the file ends with a newline
    if tail.strip():
        info["partial_last_line"] = 1
    recs: Dict[str, dict] = {}
    for c in chunks:
        if not c.strip():
            continue
        info["lines"] += 1
        try:
            rec = json.loads(c.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            info["bad_lines"] += 1
            continue
        if not isinstance(rec, dict) or not isinstance(rec.get("key"), str):
            info["bad_lines"] += 1
            continue
        if rec["key"] in recs:
            info["duplicate_keys"] += 1
            continue
        recs[rec["key"]] = rec
    info["kept"] = len(recs)
    info["status"] = dict(sorted(collections.Counter(r.get("status") for r in recs.values()).items(),
                                 key=lambda x: str(x[0])))
    return recs, info


class StoreOnly:
    """The answers backend of the re-run: it never calls anything. A key that is not in the store reaches answer();
    it is recorded as missing and answered as a bad output (the fact takes its blocking value)."""
    name = "store_only"
    exhaustive = False

    def __init__(self):
        self.missing: List[dict] = []
        self.where: Any = None

    def answer(self, *, qid: str, key: str, fact: Optional[str] = None, part: Optional[str] = None, **_: Any) -> dict:
        self.missing.append({"key": key, "qid": qid, "fact": fact, "part": part, "where": self.where})
        return {"answer": "unclear", "quote": "", "bad_output": True}


class AskLog:
    """on_ask hook: every ask of the tiny arm, per check (key, qid, fact, part, from the store)."""

    def __init__(self):
        self.items: List[list] = []

    def __call__(self, key: str, qid: str, fact: Optional[str], part: Optional[str], cached: bool) -> None:
        self.items.append([key, qid, fact, part, bool(cached)])

    def take(self) -> List[list]:
        out, self.items = self.items, []
        return out


def make_hook(recs: Dict[str, dict]) -> Tuple[Any, StoreOnly, AskLog]:
    """questions.Questions over an in-memory copy of the store, with the StoreOnly backend."""
    from state_tracker.v3 import questions as Q
    store = Q.MemoryStore()
    for k, r in recs.items():
        store.put(k, r)
    backend = StoreOnly()
    hook = Q.Questions(backend, store)
    log = AskLog()
    hook.on_ask = log
    return hook, backend, log


# ----------------------------------------------------------------------------------------------- the conversations
def select_conversations(side: str, limit: Optional[int] = None,
                         counts: Optional[collections.Counter] = None) -> Iterator[Any]:
    """dev: the first `limit` (default 50) conversations of each strong-agent development data set, as
    `v3_p8_dryrun.py --limit-convs 50` chose them for p12a. holdout (locked): every strong-agent hold-out conversation,
    as p12b's run (v3_p8_dryrun HOLDOUT_REAL_DATASETS, agent luna)."""
    from scoring import v3_p8_dryrun as P8
    if side == "dev":
        if tuple(P8.PAID_DATASETS) != DEV_SETS:
            raise RuntimeError("v3_p8_dryrun.PAID_DATASETS changed")
        lim = DEV_LIMIT if limit is None else limit
        for conv in P8.side_conversations(DEV_SETS, "dev", limit_convs=lim, counts=counts, agent=AGENT):
            if conv.side != "dev" or L.is_holdout_ckey(conv.conv_key + "|0"):
                raise L.HoldOutData(f"{conv.conv_key}: not development data")
            yield conv
        return
    require_unlocked()
    if tuple(P8.HOLDOUT_REAL_DATASETS) != HOLDOUT_SETS:
        raise RuntimeError("v3_p8_dryrun.HOLDOUT_REAL_DATASETS changed")
    for conv in P8.side_conversations(HOLDOUT_SETS, "holdout", limit_convs=limit, counts=counts, agent=AGENT):
        if conv.side != "holdout":
            raise RuntimeError(f"{conv.conv_key}: not hold-out data")
        yield conv


def load_holdout_tool_labels(path: str = HOLDOUT_LABELS) -> Dict[str, dict]:
    """As v3_labels.load_tool_labels, for the hold-out labels file: every key must be a hold-out key."""
    require_unlocked()
    out: Dict[str, dict] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            if d.get("part") in L.DROP_PARTS:
                continue
            ck = d["ckey"]
            if not L.is_holdout_ckey(ck):
                raise ValueError(f"{ck}: a development key in the hold-out labels file")
            if ck in out:
                raise ValueError(f"{ck}: two tool labels")
            out[ck] = {"accepted": d["accepted"], "check": d["check"], "facts": d.get("facts") or {},
                       "first_error": d.get("first_error"), "part": d.get("part")}
    return out


def index_line(ch: Any) -> Dict[str, Any]:
    """The index fields of a check computed directly (the hold-out; p1's rule: fork/offline_v3 length_bin)."""
    from fork import offline_v3 as O
    n = ch.history_len()
    return {"saved_decision": ch.saved_decision, "history_len": n, "bin": O.length_bin(n)}


def holdout_conversation_labels(conv: Any, tool_labels: Dict[str, dict], call_of: Callable[[dict], Tuple[str, Any]]
                                ) -> Tuple[Dict[str, dict], List[str]]:
    """v3_labels.conversation_labels for a hold-out conversation (same label code: write_label, task_actions,
    executed_calls, tool_label_for), with the index fields computed from the check."""
    require_unlocked()
    if conv.side != "holdout":
        raise RuntimeError(f"{conv.conv_key}: not hold-out data")
    from state_tracker.v3 import tool_check as TC
    acts = L.task_actions(conv.domain, conv.split, conv.task_id)
    problems: List[str] = []
    ep = conv.ep
    ri = (ep.get("reward_info") or {}).get("actions")
    if isinstance(ri, list) and L.canon([[a.get("name"), a.get("kwargs")] for a in ri]) != L.canon(
            [[n, k] for n, k in acts]):
        problems.append(f"{conv.conv_key}: task actions differ from the episode's reward_info actions")
    expected = [(n, k) for n, k in acts if TC.is_write_tool(conv.domain, n)]
    calls = L.executed_calls(ep["executed"], call_of)
    out: Dict[str, dict] = {}
    for ch in conv.checks():
        tool, args = ch.tool, ch.args
        if not L.is_write(conv.domain, tool):
            continue
        try:
            lab = L.tool_label_for(tool_labels, ch.ckey)
        except (KeyError, ValueError) as e:            # counted and reported (the check then has no outcome label)
            problems.append(f"{ch.ckey}: no usable tool label ({e})")
            continue
        prefix = ch.attempt["executed_prefix_len"]
        if not ch.blocked and not any(p == prefix and t == tool and a == L.canon(args) for p, t, a, _ in calls):
            problems.append(f"{ch.ckey}: the call ran but executed[{prefix}] is another call")
        r = L.write_label(ckey=ch.ckey, dataset=conv.dataset, agent=conv.agent, domain=conv.domain, split=conv.split,
                          task_id=conv.task_id, trial=conv.trial, src=conv.source_guard, tool=tool, args=args,
                          saved_decision=ch.saved_decision, blocked=ch.blocked, cap_override=ch.cap_override,
                          prefix=prefix, expected=expected, calls=calls, tool_label=lab, reward=ep.get("reward"),
                          index_line=index_line(ch))
        false_facts = sorted(f for f, v in (lab.get("facts") or {}).items() if v is False)
        if false_facts != sorted(r["mapped_facts"]):
            problems.append(f"{ch.ckey}: the label's false facts {false_facts} differ from the p3 map "
                            f"{r['mapped_facts']}")
        out[ch.ckey] = r
    return out, problems


# ----------------------------------------------------------------------------------------------- P11.5's reasons
def objective_reasons(conv: Any, tasks: Dict[str, List[dict]], raw_base: Dict[str, Any]) -> Dict[str, dict]:
    """p7's objective reasons for the core structure facts (scoring/v3_p7_structure.py run(), the same steps and
    helpers): retail find_user_id_* checks -> τ-bench's find tool on the copy (gives the task's user?); retail replies
    before login -> the raw database scan (hits). {ckey: {"ident": {...}} or {"disc": {...}}}."""
    from fork import offline_v3 as O
    from scoring import v3_p7_structure as P7
    from state_tracker import state as S
    from state_tracker.v3 import message_view as MV
    out: Dict[str, dict] = {}
    if conv.domain != "retail":
        return out
    dom, ex = conv.domain, conv.ep["executed"]
    task = P7.task_of(tasks, conv)
    checks = list(conv.checks())
    by_prefix: Dict[int, list] = collections.defaultdict(list)
    for chk in checks:
        by_prefix[chk.attempt["executed_prefix_len"]].append(chk)
    if not any(O.call_of(c.msg)[0] in MV.FIND_TOOLS or O.call_of(c.msg)[0] == "respond" for c in checks):
        return out
    full = MV.build_view(ex, domain=dom)
    raw = raw_base[dom]
    raw_extra: Dict[str, set] = {}
    raw_extra_done = 0
    typed_cache: Dict[int, List[str]] = {}
    for n, st in S.walk(ex, dom, sorted(by_prefix)):
        for chk in by_prefix[n]:
            tool, args = O.call_of(chk.msg)
            st.pending = S.normalize_action({"tool": tool, "args": args})
            if tool in MV.FIND_TOOLS:
                o = S.run_tool(dom, st.db, tool, dict(args))
                out[chk.ckey] = {"ident": {"tool_output": o, "task_user": task.get("user_id"),
                                           "gives_task_user": o == task.get("user_id")}}
            if tool != "respond":
                continue
            logged_in = bool(st.events_where(tool=list(MV.FIND_TOOLS), ok=True))
            if n not in typed_cache:
                view = full.prefix(n, {"tool": tool, "args": args}, st)
                typed_cache[n] = [P7._rnorm(e.text) for e in view.entries if e.role == "user"]
            if raw_extra_done < len(st.events):
                for ev in st.events[raw_extra_done:]:
                    if ev["ok"] and ev.get("changes_db"):
                        oid = ev["args"].get("order_id")
                        o = st.db["orders"].get(oid) if isinstance(oid, str) else None
                        if o:
                            P7.add_record(raw_extra, o["user_id"], o)
                        uid = ev["args"].get("user_id")
                        if isinstance(uid, str) and uid in st.db["users"]:
                            P7.add_record(raw_extra, uid, st.db["users"][uid])
                raw_extra_done = len(st.events)
            if not logged_in:
                hits = raw.hits(args.get("content") or "", typed_cache[n], raw_extra)
                out[chk.ckey] = {"disc": {"raw_hits": len(hits), "hit_values": [h["value"] for h in hits][:5]}}
    return out


# ----------------------------------------------------------------------------------------------- the run (workers)
_W: Dict[str, Any] = {}


def worker_init(side: str, store_path: str, holdout: bool = False, look: bool = False) -> None:
    """Once per process: p11's safety and guards, the store, the tiny guard (meaning = tiny, messages = rule)."""
    key = (side, os.path.abspath(store_path))
    if _W.get("key") == key:
        return
    if side == "holdout":
        unlock(holdout, look)
    E.setup_process()                                    # network refused, judge refused, writes only under output/
    from fork import offline_v3 as O
    from guard import tgr_tracker_v3 as G
    from scoring import v3_p7_structure as P7
    from state_tracker.v3 import message_view as MV
    recs, info = read_store(store_path)
    hook, backend, log = make_hook(recs)
    G.register_tiny(TINY, hook, messages="rule", lazy=True)       # replaces an earlier one (and its built guards)
    for d in E.DOMAINS:
        O.guard_for(TINY, d)
    if "tasks" not in _W:
        _W.update(tasks=P7.load_tasks(), raw_base={d: P7.RawScan(d, MV._initial_db(d)) for d in paths.DOMAINS})
    _W.update(key=key, side=side, recs=recs, store_info=info, hook=hook, backend=backend, log=log)


def _short3(res: Optional[dict], docs: Dict[str, dict], dom: str, write: bool, asks: Optional[List[list]] = None
            ) -> Optional[dict]:
    if res is None:
        return None
    rec = res["record"]
    v = rec.get("v3") or {}
    facts = v.get("facts") or {}
    out = {"d": res["decision"], "viol": A._rule_ids(rec.get("violated_rules")),
           "f": {nm: [x.get("value"), x.get("source")] for nm, x in facts.items()},
           "probs": {nm: x["problems"] for nm, x in facts.items() if x.get("problems")},
           "serr": [e.get("kind") for e in v.get("state_errors") or []],
           "ferr": [e.get("fact") for e in v.get("fact_errors") or []],
           "fb": bool((v.get("message") or {}).get("fallback")),
           "unknown": len(v.get("unknown") or []), "switches": v.get("switches")}
    if asks is not None:
        asked = sorted({a[2] for a in asks if a[2]})
        out["asks"] = asks
        out["parts"] = {nm: {pid: [p.get("value"), p.get("source"), p.get("how")] for pid, p in
                             (facts[nm].get("parts") or {}).items()} for nm in asked if nm in facts}
        if write and facts:
            out["world"] = L.world_values(dom, facts, docs[dom])
    return out


def conv_rows(conv: Any, pos: int, labels_src: Dict[str, Any], docs: Dict[str, dict], verify_every: int,
              counts: collections.Counter, walk: collections.Counter, errors: List[dict],
              problems: List[str]) -> List[dict]:
    """The rows of one conversation (p11's row fields; "v3" = the tiny arm; plus "v3sj", "judge", "obj")."""
    from fork import offline_v3 as O
    from scoring import v3_p9_run as P9
    side = _W["side"]
    if side == "dev":
        labs, probs = L.conversation_labels(conv, labels_src["index"], labels_src["tool_labels"], call_of=O.call_of)
    else:
        labs, probs = holdout_conversation_labels(conv, labels_src["tool_labels"], O.call_of)
    problems += probs
    obj = objective_reasons(conv, _W["tasks"], _W["raw_base"])
    gt, gs = O.guard_for(TINY, conv.domain), O.guard_for(STANDIN, conv.domain)
    gt.state_source = P9.WalkStates(conv, walk, verify_every)
    gs.state_source = P9.WalkStates(conv, collections.Counter(), 0)
    backend, log = _W["backend"], _W["log"]
    rows = []
    ep = conv.ep
    try:
        for ch in conv.checks():
            counts["checks"] += 1
            judged = ch.saved_judge()
            if judged is None:
                counts["judge skipped in the source run (given {})"] += 1
                judged = {}
            ix = labels_src["index"][ch.ckey] if side == "dev" else index_line(ch)
            saved = ch.saved
            log.take()
            backend.where = ch.ckey
            rt = E._decide(O, ch, TINY, judged, errors, counts)
            asks = log.take()
            rs = E._decide(O, ch, STANDIN, judged, errors, counts)
            rf = E._decide(O, ch, "frozen", judged, errors, counts)
            rv2 = E._decide(O, ch, "v2", judged, errors, counts) if conv.source_guard == "frozen" else None
            lab = labs.get(ch.ckey)
            asked = sorted({a[2] for a in asks if a[2]})
            row: Dict[str, Any] = {
                "ck": ch.ckey, "conv": conv.conv_key, "pos": pos, "i": ch.check_idx, "ds": conv.dataset,
                "part": A.part_of(conv.dataset), "agent": conv.agent, "dom": conv.domain,
                "src": conv.source_guard, "tool": ch.tool, "write": lab is not None,
                "bin": ix["bin"], "hl": ix["history_len"],
                "task": L.task_key(conv.domain, conv.split, conv.task_id), "reward": ep.get("reward"),
                "saved": {"d": ch.saved_decision, "blocked": ch.blocked, "cap": ch.cap_override,
                          "judged": ch.judged, "viol": A._rule_ids(saved.get("violated_rules")),
                          "vals": E._vals(saved.get("judge")), "setter": E._setters(saved.get("judge")),
                          "judge_skipped": bool((saved.get("tracker") or {}).get("judge_skipped")),
                          "asked_judge": bool(saved.get("judge"))},
                "fz": E._short(rf), "v2": E._short(rv2), "label": lab,
                "v3": _short3(rt, docs, conv.domain, lab is not None, asks),
                "v3sj": _short3(rs, docs, conv.domain, False),
                "judge": {f: [(judged.get(f) or {}).get("value"),
                              str((judged.get(f) or {}).get("evidence") or "")[:EVIDENCE_CHARS]]
                          for f in asked if f in judged},
                "obj": obj.get(ch.ckey)}
            rows.append(row)
    finally:
        gt.state_source = None
        gs.state_source = None
    return rows


def run_shard(task: Tuple[Any, ...]) -> Dict[str, Any]:
    """One shard: the selected conversations with (index in the selection) % n == k."""
    side, k, n, limit, labels_path, verify_every, store_path, holdout, look = task
    worker_init(side, store_path, holdout, look)
    from scoring import v3_p9_run as P9
    from state_tracker.v3 import facts_format_v3 as F
    from state_tracker.v3 import questions as Q
    t0 = time.time()
    c0, n0 = dict(P9.COUNT), len(Q.network_events())
    m0 = len(_W["backend"].missing)
    docs = {d: F.load_facts(d) for d in E.DOMAINS}
    if side == "dev":
        labels_src = {"index": L.load_index(), "tool_labels": L.load_tool_labels()}
    else:
        labels_src = {"index": None, "tool_labels": load_holdout_tool_labels(labels_path)}
    counts: collections.Counter = collections.Counter()
    walk: collections.Counter = collections.Counter()
    sel: collections.Counter = collections.Counter()
    errors: List[dict] = []
    problems: List[str] = []
    rows: List[dict] = []
    for j, conv in enumerate(select_conversations(side, limit, sel)):
        if j % n != k:
            continue
        counts["conversations"] += 1
        rows += conv_rows(conv, conv.ordinal, labels_src, docs, verify_every, counts, walk, errors, problems)
        if counts["conversations"] % 25 == 0:
            say(f"[{side} {k}/{n}] {counts['conversations']} conversations, {counts['checks']} checks, "
                f"{time.time() - t0:.0f} s")
    return {"rows": rows, "counts": dict(counts), "walk": dict(walk), "selection": dict(sel), "errors": errors,
            "problems": problems, "missing": _W["backend"].missing[m0:],
            "judge_calls": {key: P9.COUNT[key] - c0.get(key, 0) for key in P9.COUNT},
            "network_events": len(Q.network_events()) - n0, "seconds": round(time.time() - t0, 1),
            "store": _W["store_info"], "k": k, "n": n}


def order_key(r: dict) -> Tuple[int, int, int]:
    sets = DEV_SETS if r["ds"] in DEV_SETS else HOLDOUT_SETS
    return (sets.index(r["ds"]), r["pos"], r["i"])


def phase_run(a: argparse.Namespace, out: Dict[str, str]) -> Dict[str, Any]:
    t0 = time.time()
    tasks = [(a.side, k, a.shards, a.limit, a.labels, a.verify_every, a.store, a.holdout, a.look)
             for k in range(a.shards)]
    results: List[Dict[str, Any]] = []
    if a.workers == 1:
        for t in tasks:
            results.append(run_shard(t))
    else:
        import multiprocessing
        ctx = multiprocessing.get_context("spawn")
        with ctx.Pool(a.workers) as pool:
            for r in pool.imap_unordered(run_shard, tasks):
                results.append(r)
                say(f"[run] shard {r['k']}/{r['n']} back ({len(results)} of {len(tasks)}), {time.time() - t0:.0f} s")
    rows = sorted((r for res in results for r in res["rows"]), key=order_key)
    if len({r["ck"] for r in rows}) != len(rows):
        raise RuntimeError("a check key twice in the rows")
    if a.side == "dev" and any(L.is_holdout_ckey(r["ck"]) for r in rows):
        raise L.HoldOutData("a hold-out check in the development rows")
    if a.side == "holdout" and not all(L.is_holdout_ckey(r["ck"]) for r in rows):
        raise RuntimeError("a development check in the hold-out rows")
    E.write_jsonl(out["rows"], rows)
    stores = {json.dumps(r["store"], sort_keys=True) for r in results}
    meta = {"side": a.side, "counts": E._merge_counts(results, "counts"), "walk": E._merge_counts(results, "walk"),
            "selection": results[0]["selection"] if results else {},
            "judge_calls": E._merge_counts(results, "judge_calls"),
            "network_events": sum(r["network_events"] for r in results),
            "problems": sorted(p for r in results for p in r["problems"]),
            "errors": sorted((e for r in results for e in r["errors"]), key=lambda e: (e["ckey"], e["guard"]))[:50],
            "missing": sorted((m for r in results for m in r["missing"]), key=lambda m: (str(m["where"]), m["key"])),
            "store": json.loads(sorted(stores)[0]) if stores else None, "stores_differ": len(stores) > 1,
            "worker_seconds": round(sum(r["seconds"] for r in results), 1), "seconds": round(time.time() - t0, 1),
            "shards": a.shards, "workers": a.workers, "limit": a.limit, "verify_every": a.verify_every,
            "rows": len(rows), "rows_sha256": sha256_file(out["rows"]),
            "when": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}
    E.write_json(out["meta"], meta)
    say(f"[run] {len(rows)} rows, {meta['seconds']} s; counts {json.dumps(meta['counts'])[:1200]}")
    return meta


# ======================================================================================================= analysis
def asked_facts(r: dict) -> List[str]:
    return sorted({a[2] for a in ((r.get("v3") or {}).get("asks") or []) if a[2]})


def asks_of(r: dict, fact: Optional[str] = None, unique: bool = False) -> List[list]:
    """The tiny arm's asks of a row (of one fact); unique: each key once (a fact can ask one key twice)."""
    out, seen = [], set()
    for a in ((r.get("v3") or {}).get("asks") or []):
        if fact is not None and a[2] != fact:
            continue
        if unique and (a[0], a[2]) in seen:
            continue
        seen.add((a[0], a[2]))
        out.append(a)
    return out


def status_of(key: str, recs: Dict[str, dict], missing: set) -> str:
    if key in missing:
        return MISSING
    rec = recs.get(key)
    return MISSING if rec is None else str(rec.get("status"))


def answer_problems(rows: List[dict], recs: Dict[str, dict], missing: set) -> Dict[str, Any]:
    """Statuses of the distinct answers the tiny arm used, per question; and of the whole store."""
    used: Dict[str, str] = {}
    for r in rows:
        for a in asks_of(r):
            used.setdefault(a[0], a[1])
    by_q: Dict[str, collections.Counter] = {}
    tot: collections.Counter = collections.Counter()
    for k, q in used.items():
        st = status_of(k, recs, missing)
        by_q.setdefault(q, collections.Counter())[st] += 1
        tot[st] += 1
    store_by_q: Dict[str, collections.Counter] = {}
    for rec in recs.values():
        store_by_q.setdefault(str(rec.get("qid")), collections.Counter())[str(rec.get("status"))] += 1
    qk = lambda q: int(q[1:]) if q[1:].isdigit() else 0      # noqa: E731
    return {"used_keys": len(used), "used_status": dict(sorted(tot.items())),
            "used_by_question": {q: dict(sorted(by_q[q].items())) for q in sorted(by_q, key=qk)},
            "store_answers": len(recs),
            "store_status": dict(sorted(collections.Counter(str(r.get("status")) for r in recs.values()).items())),
            "store_by_question": {q: dict(sorted(store_by_q[q].items())) for q in sorted(store_by_q, key=qk)},
            "asks": sum(len(asks_of(r)) for r in rows),
            "checks_with_asks": sum(1 for r in rows if asks_of(r))}


def problem_facts(r: dict, recs: Dict[str, dict], missing: set) -> Dict[str, List[dict]]:
    """{fact: [its asks with a problem status]} for the facts of the tiny arm that took their blocking value because
    of an answer problem (problem kind "unclear": unclear, quote_failed, bad_output) or a missing answer."""
    out: Dict[str, List[dict]] = {}
    probs = (r.get("v3") or {}).get("probs") or {}
    for f, kinds in probs.items():
        if "unclear" not in kinds:
            continue
        bad = []
        for a in asks_of(r, f, unique=True):
            st = status_of(a[0], recs, missing)
            if st in PROBLEM_STATUSES or st == MISSING:
                bad.append({"key": a[0], "qid": a[1], "part": a[3], "status": st})
        out[f] = bad
    return out


def _row_holds(tables: Dict[str, dict], dom: str, rid: str, tool: str, vals: Dict[str, Any]) -> Optional[bool]:
    t = tables[dom]
    e = t["rules"].get(str(rid))
    if e is None:
        return None
    key = tuple(vals.get(f) for f in e["facts"])
    if any(v is None for v in key):
        return None
    row = t["rows"].get((e["id"], tool, key)) or t["rows"].get((e["id"], None, key))
    return None if row is None else bool(row["holds"])


def unclear_blocks(an: Any, recs: Dict[str, dict], missing: set) -> Dict[str, Any]:
    """Tiny blocks with a fact at its blocking value from an answer problem; "only" = every violated rule would hold
    with those facts flipped (rule table rows)."""
    c: collections.Counter = collections.Counter()
    items: List[dict] = []
    for r in an.rows:
        if an.dec(r, "v3") != "block":
            continue
        pf = problem_facts(r, recs, missing)
        if not pf:
            continue
        c["tiny blocks with a fact set by an answer problem"] += 1
        vals = {f: x[0] for f, x in r["v3"]["f"].items()}
        flipped = dict(vals)
        for f in pf:
            if isinstance(flipped.get(f), bool):
                flipped[f] = not flipped[f]
        viol = an.viol(r, "v3")
        holds = [_row_holds(an.tables, r["dom"], rid, r["tool"], flipped) for rid in viol]
        only = bool(viol) and all(h is True for h in holds)
        kind = "only from an answer problem" if only else (
            "other rules block too" if all(h is not None for h in holds) else "not decidable from the rule table")
        c[kind] += 1
        if any(b["status"] == MISSING for v in pf.values() for b in v):
            c["... with a missing answer"] += 1
        items.append({"ck": r["ck"], "tool": r["tool"], "saved": r["saved"]["d"], "rules": viol,
                      "facts": {f: [vals.get(f), v] for f, v in pf.items()}, "only": only, "kind": kind,
                      "role": r.get("_role")})
    return {"counts": dict(c), "items": items}


def _exists(tree: Any, fixed: Dict[str, bool], free: Sequence[str], want: bool) -> bool:
    from state_tracker.v3 import facts_format_v3 as F
    for bits in itertools.product((True, False), repeat=len(free)):
        if F.combine_value(tree, dict(fixed, **dict(zip(free, bits)))) is want:
            return True
    return False


def two_keys(an: Any, docs: Dict[str, dict]) -> Dict[str, Any]:
    """Per asked fact: do the question parts allow while the code parts block (the two keys disagree)? Also counted:
    facts the question alone closed (code open, the answers block) and facts both keys open."""
    from state_tracker.v3 import facts_format_v3 as F
    c: collections.Counter = collections.Counter()
    items: List[dict] = []
    for r in an.rows:
        for f, parts in ((r.get("v3") or {}).get("parts") or {}).items():
            e = docs[r["dom"]]["facts"].get(f)
            if e is None:
                continue
            tree = F.parse_combine(e["combine"])
            ids = F.combine_ids(tree)
            allow = not e["blocking_value"]
            qv = {p: v[0] for p, v in parts.items() if e["parts"].get(p, {}).get("source") == "question"
                  and isinstance(v[0], bool)}
            cv = {p: v[0] for p, v in parts.items() if e["parts"].get(p, {}).get("source") != "question"
                  and isinstance(v[0], bool)}
            if not qv:
                c["asked facts with no answered question part (a problem or not needed)"] += 1
                continue
            c["asked facts with an answered question part"] += 1
            q_allow = _exists(tree, qv, [p for p in ids if p not in qv], allow)
            c_allow = _exists(tree, cv, [p for p in ids if p not in cv], allow)
            if q_allow and not c_allow:
                c["two-key disagreement: the answers allow, a code part blocks"] += 1
                items.append({"ck": r["ck"], "fact": f, "parts": parts})
            elif c_allow and not q_allow:
                c["the answers block, code open (a question decided the block)"] += 1
            elif c_allow and q_allow:
                c["both keys open"] += 1
            else:
                c["both keys block"] += 1
    return {"counts": dict(c), "items": items[:200]}


def core_reasons(an: Any) -> Dict[str, Any]:
    """P11.5 as v3_offline_eval.sec_core, with the objective reasons recomputed per row ("obj")."""
    rows_out = []
    c: collections.Counter = collections.Counter()
    for r in an.rows:
        if r["saved"]["d"] != "allow" or an.dec(r, "v3") != "block":
            continue
        hit = []
        for rid in an.viol(r, "v3"):
            for f in an.rule_facts(r["dom"], rid):
                if f in E.CORE_STRUCTURE and f in r["_changed"] and an.v3val(r, f) is an.blocking(r["dom"], rid, f):
                    hit.append((rid, f))
        for rid, f in hit:
            c["added blocks with a core fact"] += 1
            o = r.get("obj") or {}
            reason = None
            if f in E.IDENTITY:
                x = o.get("ident")
                if x is not None and x.get("gives_task_user") is False:
                    reason = f"τ-bench's find tool on the copy gives {x.get('tool_output')!r}, not the task's user"
            else:
                x = o.get("disc")
                if x is not None and (x.get("raw_hits") or 0) > 0:
                    reason = f"p7's raw scan finds database value(s) {x.get('hit_values')} the user did not type"
            c["with an objective reason" if reason else "without an objective reason"] += 1
            rows_out.append({"ck": r["ck"], "rule": f"{r['dom']}:{rid}", "fact": f, "reason": reason,
                             "role": r["_role"]})
    return {"counts": dict(c), "rows": rows_out}


def p7_agreement(rows: List[dict]) -> Dict[str, Any]:
    """Dev only: the recomputed objective reasons vs p7's saved rows (output/logs/v3_p7_run_details.json)."""
    try:
        with open(E.P7_DETAILS, encoding="utf-8") as f:
            p7 = json.load(f)
    except OSError as e:
        return {"error": str(e)}
    ident = {x["ckey"]: x for x in p7.get("ident") or []}
    disc = {x["ckey"]: x for x in p7.get("disc_rows") or []}
    c: collections.Counter = collections.Counter()
    ex: List[str] = []
    for r in rows:
        o = r.get("obj") or {}
        for kind, ref, field in (("ident", ident, "gives_task_user"), ("disc", disc, "raw_hits")):
            mine = o.get(kind)
            theirs = ref.get(r["ck"])
            if mine is None and theirs is None:
                continue
            if mine is None or theirs is None:
                c[f"{kind}: only one side has a row"] += 1
                if len(ex) < 10:
                    ex.append(f"{r['ck']} {kind}: mine {mine is not None}, p7 {theirs is not None}")
                continue
            same = mine[field] == theirs[field]
            c[f"{kind}: {'equal' if same else 'DIFFERENT'}"] += 1
            if not same and len(ex) < 10:
                ex.append(f"{r['ck']} {kind}: mine {mine[field]}, p7 {theirs[field]}")
    return {"counts": dict(sorted(c.items())), "examples": ex}


def llm_share(an: Any) -> Dict[str, Any]:
    """Values behind blocks (facts of every violated rule, one per (check, fact)): set by an LLM or by code. Frozen:
    the judge. v3 (tiny): a tiny question (source "question"), code, a lazy skip or a blocking value."""
    out: Dict[str, Any] = {}
    for g in ("frozen", "v3"):
        c: collections.Counter = collections.Counter()
        for r in an.rows:
            if an.dec(r, g) != "block":
                continue
            c["blocks"] += 1
            cats = []
            for f in an.facts_of(r, an.viol(r, g)):
                if g == "frozen":
                    cats.append("llm" if f in ((r["fz"] or {}).get("vals") or {}) else "missing")
                else:
                    x = (r["v3"] or {}).get("f", {}).get(f)
                    k = None if x is None else x[1]
                    cats.append("missing" if k is None else "llm" if k == "question" else "code" if k == "code"
                                else "not_asked" if k == "lazy_skip" else "blocking_value")
            for x in cats:
                c[x] += 1
                c["values"] += 1
            c["blocks with an LLM-set value"] += int("llm" in cats)
        out[g] = dict(sorted(c.items()))
    return out


def compare(an: Any, recs: Dict[str, dict], missing: set, docs: Optional[Dict[str, dict]] = None) -> Dict[str, Any]:
    """Item 3: per (check, fact the tiny arm asked for): the tiny value vs the judge's saved value. docs (the fact
    files): the direction of a disagreement (does the tiny value block or allow)."""
    from state_tracker.v3 import questions as Q
    qdoc = Q.load_questions()
    c: collections.Counter = collections.Counter()
    by_q: Dict[str, collections.Counter] = {}
    by_f: Dict[str, collections.Counter] = {}
    items: List[dict] = []
    for r in an.rows:
        for f in asked_facts(r):
            tv = (r["v3"]["f"].get(f) or [None, None])
            jv = (r.get("judge") or {}).get(f)
            sv = ((r.get("v3sj") or {}).get("f") or {}).get(f)
            qids = sorted({a[1] for a in asks_of(r, f)}, key=Q._qkey)
            c["asked facts"] += 1
            if jv is None or not isinstance(jv[0], bool):
                k = "judge has no value (unknown or not asked)"
            elif not isinstance(tv[0], bool):
                k = "tiny has no value"
            elif tv[0] is jv[0]:
                k = "agree"
            else:
                k = "disagree"
            c[k] += 1
            for q in qids:
                by_q.setdefault(q, collections.Counter())[k] += 1
            by_f.setdefault(f, collections.Counter())[k] += 1
            if k != "disagree":
                continue
            if sv is None or sv[1] in ("lazy_skip", "state_error", "fact_error") or not isinstance(sv[0], bool):
                why = "stand-in arm did not evaluate the fact"
            elif sv[0] is jv[0]:
                why = "from the question"
            else:
                why = "from code parts (the stand-in differs from the judge too)"
            blocked = r["saved"]["d"] == "block" or an.dec(r, "v3") == "block"
            c[f"disagree, {'blocked check' if blocked else 'allowed check'}, {why}"] += 1
            e = ((docs or {}).get(r["dom"]) or {}).get("facts", {}).get(f)
            direction = None if e is None else (
                "tiny gives the blocking value" if tv[0] is e["blocking_value"] else "tiny gives the allowing value")
            if direction:
                c[f"disagree: {direction}"] += 1
            for q in qids:
                by_q[q][f"disagree: {why}"] += 1
            asks = []
            for a in asks_of(r, f, unique=True):
                rec = recs.get(a[0]) or {}
                asks.append({"qid": a[1], "part": a[3], "status": status_of(a[0], recs, missing),
                             "answer": rec.get("answer"), "quote": rec.get("quote"), "raw": rec.get("raw"),
                             "question": (qdoc["questions"].get(a[1]) or {}).get("question"),
                             "prompt_user": rec.get("prompt_user"), "key": a[0]})
            items.append({"ck": r["ck"], "conv": r["conv"], "check": r["i"], "dataset": r["ds"], "tool": r["tool"],
                          "fact": f, "blocked": blocked, "why": why, "direction": direction,
                          "saved_decision": r["saved"]["d"],
                          "tiny_decision": an.dec(r, "v3"), "standin_decision": (r.get("v3sj") or {}).get("d"),
                          "tiny_value": tv[0], "tiny_source": tv[1], "judge_value": jv[0], "judge_evidence": jv[1],
                          "standin_value": None if sv is None else sv[0],
                          "standin_source": None if sv is None else sv[1], "asks": asks})
    return {"counts": dict(sorted(c.items())), "by_question": {q: dict(sorted(v.items())) for q, v in
                                                                sorted(by_q.items(), key=lambda x: Q._qkey(x[0]))},
            "by_fact": {f: dict(sorted(v.items())) for f, v in sorted(by_f.items())}, "items": items}


def pass_marks(an: Any, meta: dict, p112: dict, classes: dict, core: dict, missing_n: int) -> Dict[str, Any]:
    rows = an.rows
    serr = sum(len((r["v3"] or {}).get("serr") or []) for r in rows)
    ferr = sum(len((r["v3"] or {}).get("ferr") or []) for r in rows)
    fb = sum(int(bool((r["v3"] or {}).get("fb"))) for r in rows)
    blocks = sum(1 for r in rows if an.dec(r, "v3") == "block")
    gerr = sum(v for k, v in (meta.get("counts") or {}).items() if k.startswith("errors: "))
    gerr_tiny = int((meta.get("counts") or {}).get(f"errors: {TINY}", 0))
    no_dec = sum(1 for r in rows if not r["v3"])
    n_checks = sum(1 for r in rows if (r["v3"] or {}).get("f"))
    n_values = sum(len((r["v3"] or {}).get("f") or {}) for r in rows)
    out: Dict[str, Any] = {}
    out["P11.1"] = {"state_errors": serr, "fact_errors": ferr, "message_fallbacks_rule": fb, "tiny_blocks": blocks,
                    "guard_run_errors_all_arms": gerr, "guard_run_errors_tiny": gerr_tiny, "checks_without_tiny": no_dec,
                    "n_checks_with_facts": n_checks, "n_fact_values": n_values,
                    "bound_state": L.three_over_n(n_checks) if n_checks else None,
                    "bound_fact": L.three_over_n(n_values) if n_values else None,
                    "bound_fallback": L.three_over_n(blocks) if blocks else None,
                    "pass": serr == 0 and ferr == 0 and fb == 0 and gerr == 0 and no_dec == 0}
    pc = p112["counts"]
    n2 = pc.get("agree", 0) + pc.get("disagree", 0)
    out["P11.2"] = {"agree": pc.get("agree", 0), "disagree": pc.get("disagree", 0),
                    "not_decided": pc.get("not decided by the tool", 0), "bound": L.three_over_n(n2) if n2 else None,
                    "examples": p112.get("disagree_examples"), "pass": pc.get("disagree", 0) == 0}
    cc = classes["exact"]["counts"]["all"].get("all", {})
    new_allows_write = sum(1 for r in rows if r["write"] and r["saved"]["d"] == "block" and an.dec(r, "v3") == "allow")
    out["P11.3"] = {"bad": cc.get("bad", 0),
                    "bad_order_blind": classes["order_blind"]["counts"]["all"].get("all", {}).get("bad", 0),
                    "new_allows_at_write_checks": new_allows_write,
                    "bound": L.three_over_n(new_allows_write) if new_allows_write else None,
                    "pass": cc.get("bad", 0) == 0}
    co = core["counts"]
    out["P11.5"] = {"added_with_core_fact": co.get("added blocks with a core fact", 0),
                    "with_reason": co.get("with an objective reason", 0),
                    "without_reason": co.get("without an objective reason", 0),
                    "pass": co.get("without an objective reason", 0) == 0}
    out["missing_answers"] = {"missing": missing_n, "pass": missing_n == 0}
    out["all_pass"] = all(x["pass"] for x in out.values())
    return out


def analyse(side: str, rows: List[dict], meta: dict, recs: Dict[str, dict], store_info: dict) -> Dict[str, Any]:
    from state_tracker.v3 import facts_format_v3 as F
    tables = A.load_tables()
    docs = {d: F.load_facts(d) for d in E.DOMAINS}
    an = E.Ana(rows, tables)
    missing = {m["key"] for m in meta.get("missing") or []}
    p112 = E.sec_p112(an)
    classes, detail = E.sec_classes(an)
    core = core_reasons(an)
    num: Dict[str, Any] = {"side": side, "meta": {k: v for k, v in meta.items() if k not in ("missing",)},
                           "missing": meta.get("missing") or [], "store": store_info}
    num["pass_marks"] = pass_marks(an, meta, p112, classes, core, len(missing))
    num["data"] = {"conversations": len(an.convs), "checks": len(rows), "write_checks": sum(r["write"] for r in rows),
                   "by_dataset": dict(collections.Counter(r["ds"] for r in rows)),
                   "conversations_by_dataset": dict(collections.Counter(rows_[0]["ds"] for rows_ in an.convs.values())),
                   "saved_blocks": sum(r["saved"]["d"] == "block" for r in rows),
                   "tiny_blocks": sum(an.dec(r, "v3") == "block" for r in rows),
                   "standin_blocks": sum((r.get("v3sj") or {}).get("d") == "block" for r in rows),
                   "tiny_vs_standin_changed": sum(1 for r in rows if r.get("v3sj") and r["v3"]
                                                  and r["v3sj"]["d"] != r["v3"]["d"]),
                   "asymmetric_fact_names": an.asym}
    num["answers"] = answer_problems(rows, recs, missing)
    num["unclear_blocks"] = unclear_blocks(an, recs, missing)
    num["two_keys"] = two_keys(an, docs)
    num["core"] = core
    num["p112"] = {k: v for k, v in p112.items()}
    num["classes"] = classes
    num["class_detail"] = [d for d in detail if d["cls"] in ("bad", "suspect", "good", "reported_unwanted_allow")]
    num["compare"] = compare(an, recs, missing, docs)
    c: collections.Counter = collections.Counter()
    for r in rows:
        sd, td = r["saved"]["d"], an.dec(r, "v3")
        if td is None or sd == td:
            continue
        what = "added" if td == "block" else "removed"
        c[what] += 1
        if r.get("_role") == "first":
            c[f"{what} (first divergence)"] += 1
        if what == "added":
            c[f"added at {r['tool']}"] += 1
    c["conversations with a divergence"] = sum(1 for r in rows if r.get("_role") == "first")
    num["changes_short"] = dict(sorted(c.items()))
    if side == "dev":
        num["p7_agreement"] = p7_agreement(rows)
    else:
        num["changes"] = E.sec_changes(an)
        aud = E.sec_audit(an)
        aud.pop("_p4_check", None)
        num["audit"] = aud
        num["llm_share"] = llm_share(an)
    return num


# ----------------------------------------------------------------------------------------------- reports
def _tbl(head: List[str], rows: List[List[Any]]) -> List[str]:
    return E._tbl(head, rows)


def _bound(x: Optional[float]) -> str:
    return "-" if x is None else f"{x:.2e}"


def pass_rows(pm: Dict[str, Any]) -> List[List[Any]]:
    p1, p2, p3, p5, pm_ = pm["P11.1"], pm["P11.2"], pm["P11.3"], pm["P11.5"], pm["missing_answers"]
    ok = lambda x: "PASS" if x["pass"] else "**FAIL**"     # noqa: E731
    return [
        ["P11.1", "state errors, fact errors, message fallbacks: 0",
         f"state errors {p1['state_errors']} (3/n = {_bound(p1['bound_state'])}, n = {p1['n_checks_with_facts']:,} "
         f"checks); fact errors {p1['fact_errors']} (3/n = {_bound(p1['bound_fact'])}, n = {p1['n_fact_values']:,} "
         f"values); rule-message fallbacks {p1['message_fallbacks_rule']} (3/n = {_bound(p1['bound_fallback'])}, "
         f"n = {p1['tiny_blocks']:,} tiny blocks); guard run errors {p1['guard_run_errors_all_arms']}; checks with no "
         f"tiny decision {p1['checks_without_tiny']}", ok(p1)],
        ["P11.2", "database facts vs τ-bench's tool: 0 disagreements",
         f"agree {p2['agree']:,}, disagree {p2['disagree']}, not decided by the tool {p2['not_decided']:,} "
         f"(3/n = {_bound(p2['bound'])})", ok(p2)],
        ["P11.3", "new allows the tool refuses on a check mapped to a v3 fact: 0",
         f"class bad {p3['bad']} (order-blind {p3['bad_order_blind']}) of {p3['new_allows_at_write_checks']} new "
         f"allows at write checks (3/n = {_bound(p3['bound'])})", ok(p3)],
        ["P11.5", "core structure facts: added blocks with no objective reason: 0",
         f"added blocks with a core fact {p5['added_with_core_fact']}; with a reason {p5['with_reason']}, without "
         f"{p5['without_reason']}", ok(p5)],
        ["(p12)", "answers missing from the store: 0 (asked of the store only, never of a model)",
         f"{pm_['missing']}", ok(pm_)],
    ]


def answer_section(num: Dict[str, Any]) -> List[str]:
    ans, ub, tk = num["answers"], num["unclear_blocks"], num["two_keys"]
    L_: List[str] = []
    w = L_.append
    us = ans["used_status"]
    w(f"- Answers the tiny arm used: **{ans['used_keys']:,}** distinct (question, input) keys, {ans['asks']:,} asks at "
      f"{ans['checks_with_asks']:,} checks. Status: " + ", ".join(f"{k} {v:,}" for k, v in us.items()) + ".")
    w(f"- Answer problems among them: unclear **{us.get('unclear', 0)}**, failed quotes **{us.get('quote_failed', 0)}**,"
      f" bad outputs **{us.get('bad_output', 0)}**, missing **{us.get(MISSING, 0)}**. Each takes the fact's blocking "
      "value (Q2).")
    w(f"- The whole store ({ans['store_answers']:,} answers): " + ", ".join(
        f"{k} {v:,}" for k, v in ans["store_status"].items()) + ".")
    w("")
    rows = []
    for q in sorted(set(ans["used_by_question"]) | set(ans["store_by_question"]),
                    key=lambda q: int(q[1:]) if q[1:].isdigit() else 0):
        u, s = ans["used_by_question"].get(q, {}), ans["store_by_question"].get(q, {})
        rows.append([q, sum(u.values()), u.get("yes", 0), u.get("no", 0), u.get("unclear", 0), u.get("quote_failed", 0),
                     u.get("bad_output", 0), u.get(MISSING, 0), sum(s.values()),
                     s.get("unclear", 0) + s.get("quote_failed", 0) + s.get("bad_output", 0)])
    L_ += _tbl(["question", "used", "yes", "no", "unclear", "quote failed", "bad output", "missing", "store answers",
                "store problems"], rows)
    w("")
    uc = ub["counts"]
    w(f"- **Blocks only from an unclear answer** (a tiny block where every violated rule would hold if the facts set by "
      f"an answer problem had their other value; rule table rows): **{uc.get('only from an answer problem', 0)}**. "
      f"Tiny blocks with any fact set by an answer problem: {uc.get('tiny blocks with a fact set by an answer problem', 0)}"
      f" (other rules block too: {uc.get('other rules block too', 0)}; not decidable from the rule table: "
      f"{uc.get('not decidable from the rule table', 0)}).")
    if ub["items"]:
        w("")
        rows = []
        for it in ub["items"]:
            fs = "; ".join(f"`{f}` ({', '.join(b['qid'] + ' ' + b['status'] for b in v[1]) or 'no ask'})"
                           for f, v in it["facts"].items())
            rows.append([f"`{it['ck']}`", it["tool"], it["saved"], ", ".join(it["rules"]), fs,
                         "yes" if it["only"] else "no", it.get("role") or "-"])
        L_ += _tbl(["check", "tool", "saved", "violated rules (tiny)", "fact (question status)", "only from it",
                    "role"], rows)
    w("")
    tc = tk["counts"]
    w(f"- **Two-key disagreements** (the answers allow while a code part blocks): "
      f"**{tc.get('two-key disagreement: the answers allow, a code part blocks', 0)}** of "
      f"{tc.get('asked facts with an answered question part', 0):,} asked facts with an answered question part (0 by "
      f"construction: code parts run first). Also: a question decided the block (code open) "
      f"{tc.get('the answers block, code open (a question decided the block)', 0):,}; both keys open "
      f"{tc.get('both keys open', 0):,}; both block {tc.get('both keys block', 0):,}; asked facts with no answered "
      f"question part {tc.get('asked facts with no answered question part (a problem or not needed)', 0):,}.")
    for it in tk["items"][:20]:
        w(f"  - `{it['ck']}` `{it['fact']}`: {json.dumps(it['parts'])}")
    return L_


def compare_section(num: Dict[str, Any], cmp_md: str) -> List[str]:
    cm = num["compare"]
    c = cm["counts"]
    L_ = [f"Per (check, fact the tiny arm asked a question for): the fact's tiny value vs the judge's saved value. "
          f"Asked facts {c.get('asked facts', 0):,}: agree {c.get('agree', 0):,}, **disagree {c.get('disagree', 0):,}**, "
          f"the judge has no value {c.get('judge has no value (unknown or not asked)', 0):,}, tiny has no value "
          f"{c.get('tiny has no value', 0):,}.", ""]
    rows = [[k.replace("disagree, ", "").replace("disagree: ", "direction: "), v] for k, v in c.items()
            if k.startswith("disagree, ") or k.startswith("disagree: ")]
    L_ += _tbl(["disagreements by place and cause", "n"], rows) + [""]
    rows = []
    for q, v in cm["by_question"].items():
        rows.append([q, v.get("agree", 0), v.get("disagree", 0), v.get("disagree: from the question", 0),
                     v.get("judge has no value (unknown or not asked)", 0)])
    L_ += _tbl(["question", "agree", "disagree", "... from the question", "judge: no value"], rows)
    L_ += ["", f"Every disagreement on a blocked check (saved or tiny block) is listed for the independent reviewer in "
               f"`{rel(cmp_md)}`; all disagreements are in the `.jsonl` next to it."]
    return L_


def file_rows(paths_: Iterable[str]) -> List[List[str]]:
    out = []
    for p in paths_:
        ap = p if os.path.isabs(p) else os.path.join(PC_DIR, p)
        out.append([f"`{rel(ap)}`", f"`{sha256_file(ap)}`" if os.path.exists(ap) else "missing"])
    return out


def render_dev(num: Dict[str, Any], out: Dict[str, str]) -> str:
    pm, d, m, st = num["pass_marks"], num["data"], num["meta"], num["store"]
    L_: List[str] = []
    w = L_.append
    w("# Tracker v3 p12 step 3: the development bug check with tiny answers (development check, not a result)")
    w("")
    w("> **Development check, not a result.** The facts and the tiny questions were designed on these conversations "
      "(the user, 2026-10-23). This shows the code does what it says; its counts are in-sample. The result of p12 is "
      "the hold-out.")
    w("")
    w(f"Written by `scoring/v3_p12_offline.py` on {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. $0: no LLM "
      f"call, no network (judge calls refused: {sum((m.get('judge_calls') or {}).values())}; network events: "
      f"{m.get('network_events')}). The tiny answers are read from the store only (`{st['path']}`, sha256 "
      f"`{st['sha256'][:16]}…`, {st['kept']:,} answers; partial last line {st['partial_last_line']}, bad lines "
      f"{st['bad_lines']}, duplicate keys {st['duplicate_keys']}); an answer not in the store is counted, never asked.")
    w("")
    w(f"Data: the first 50 conversations of each strong-agent development data set, as p12a chose them "
      f"(`v3_p8_dryrun.py --limit-convs 50`): {d['conversations']} conversations, {d['checks']:,} checks "
      f"({d['write_checks']} write checks). Per data set: " + ", ".join(
        f"{k} {d['conversations_by_dataset'].get(k, 0)} / {v:,} checks" for k, v in d["by_dataset"].items()) + ".")
    w(f"Guard: v3, facts = v3, meaning = **tiny**, messages = rule, lazy. Blocks: saved {d['saved_blocks']}, tiny "
      f"{d['tiny_blocks']}, stand-in (meaning = saved_judge) {d['standin_blocks']}; tiny vs stand-in decisions differ at "
      f"{d['tiny_vs_standin_changed']} checks.")
    w("")
    w(f"## P12.1: **{'PASS' if pm['all_pass'] else 'FAIL'}**")
    w("p11's zero-count marks with meaning = tiny (P11.1-P11.3, P11.5), and 0 missing answers. Zero counts with the "
      "3/n upper bound.")
    w("")
    L_ += _tbl(["id", "pass mark", "result", "pass"], pass_rows(pm))
    w("")
    if num["pass_marks"]["P11.5"]["added_with_core_fact"]:
        for x in num["core"]["rows"]:
            w(f"- P11.5 row: `{x['ck']}` {x['rule']} `{x['fact']}`: {x['reason'] or '**no objective reason**'}")
        w("")
    pa = num.get("p7_agreement") or {}
    w(f"- P11.5's objective reasons are recomputed with p7's helpers; vs p7's saved rows on these checks: "
      f"{json.dumps(pa.get('counts'))}" + (f"; examples {pa.get('examples')}" if pa.get("examples") else "") + ".")
    if num["missing"]:
        w(f"- **Missing answers ({len(num['missing'])})**: " + "; ".join(
            f"{x['where']} {x['qid']} {x['fact']}" for x in num["missing"][:20]))
    cs = num["changes_short"]
    top = sorted(((k[len("added at "):], v) for k, v in cs.items() if k.startswith("added at ")), key=lambda x: -x[1])
    w(f"- **For reading only (in-sample, not a result; not a pass mark): the tiny guard is much stricter than the saved "
      f"guard here.** Blocks added (saved allow, tiny block) {cs.get('added', 0)} (first divergence "
      f"{cs.get('added (first divergence)', 0)}), removed {cs.get('removed', 0)} (first divergence "
      f"{cs.get('removed (first divergence)', 0)}); conversations with a divergence "
      f"{cs.get('conversations with a divergence', 0)} of {d['conversations']}. Added blocks by tool: "
      + ", ".join(f"{t} {n}" for t, n in top) + ". Most come from tiny answers that differ from the judge (next "
      "sections; K2 and K13 lead).")
    cls = num["classes"]["exact"]["counts"]["all"].get("all", {})
    w(f"- For reading P11.3 only (in-sample, not a result): changed decisions vs the saved guard by class (exact "
      f"matcher): " + ", ".join(f"{k} {cls.get(k, 0)}" for k in L.CHANGED_CLASSES) + ".")
    w("")
    w("## Answer problems")
    L_ += answer_section(num)
    w("")
    w("## Tiny answers vs the judge's saved answers")
    L_ += compare_section(num, out["cmp_md"])
    w("")
    w("## Run, commands, files")
    w(f"- Run: {m.get('seconds')} s wall ({m.get('worker_seconds')} worker s, {m.get('workers')} workers, "
      f"{m.get('shards')} shards). Walk: {json.dumps(m.get('walk'))}. Label problems: {len(m.get('problems') or [])}"
      + (f" (e.g. {m['problems'][:3]})" if m.get("problems") else "") + f". Guard errors: {m.get('errors')[:3] if m.get('errors') else 'none'}.")
    w(f"- Conversations skipped by the selection (other side or agent): {json.dumps(m.get('selection'))}.")
    w("- Command (from `predicate_correctness/`): `PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python "
      "-B -m scoring.v3_p12_offline --workers 2 > output/logs/v3_p12_04_devcheck.log 2>&1`")
    w("")
    L_ += _tbl(["file", "sha256"], file_rows([out["rows"], out["cmp_jsonl"], *OWN_FILES,
                                              "scoring/v3_offline_eval.py", "scoring/v3_labels.py"]))
    return "\n".join(L_) + "\n"


def render_holdout(num: Dict[str, Any], out: Dict[str, str]) -> str:
    pm, d, m, st = num["pass_marks"], num["data"], num["meta"], num["store"]
    L_: List[str] = []
    w = L_.append
    w("# Tracker v3 p12 step 4: the hold-out, once (the offline result, meaning = tiny)")
    w("")
    w(f"Written by `scoring/v3_p12_offline.py --holdout` on {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. $0: "
      f"no LLM call, no network (judge calls refused: {sum((m.get('judge_calls') or {}).values())}; network events: "
      f"{m.get('network_events')}). Answers from the store only (`{st['path']}`, sha256 `{st['sha256'][:16]}…`, "
      f"{st['kept']:,} answers; partial last line {st['partial_last_line']}). **Nothing is fixed on the hold-out.**")
    w("")
    w(f"Data: the strong agent's val conversations and the Stage B tries forked from them: {d['conversations']} "
      f"conversations, {d['checks']:,} checks ({d['write_checks']} write checks). Per data set: " + ", ".join(
        f"{k} {d['conversations_by_dataset'].get(k, 0)} / {v:,} checks" for k, v in d["by_dataset"].items()) + ".")
    w(f"Blocks: saved {d['saved_blocks']}, v3 tiny {d['tiny_blocks']}, v3 stand-in {d['standin_blocks']}.")
    w("")
    w(f"## P12.2: **{'PASS' if pm['all_pass'] else 'FAIL'}**")
    w("The zero-count marks (P11.1-P11.3, P11.5) with meaning = tiny, and 0 missing answers. Zero counts with the "
      "3/n upper bound.")
    w("")
    L_ += _tbl(["id", "pass mark", "result", "pass"], pass_rows(pm))
    w("")
    for x in num["core"]["rows"]:
        w(f"- P11.5 row: `{x['ck']}` {x['rule']} `{x['fact']}`: {x['reason'] or '**no objective reason**'}")
    if num["missing"]:
        w(f"- **Missing answers ({len(num['missing'])})**: " + "; ".join(
            f"{x['where']} {x['qid']} {x['fact']}" for x in num["missing"][:20]))
    w("")
    w("## Changed decisions (v3 tiny vs the saved guard)")
    ch = num["changes"]["counts"]
    rows = []
    for g in sorted(ch["all"], key=lambda g: (g != "all", g)):
        a, f = ch["all"][g], ch["first"].get(g, {})
        rows.append([g, a.get("checks", 0), a.get("removed", 0), a.get("added", 0), f.get("removed", 0),
                     f.get("added", 0)])
    L_ += _tbl(["group", "checks", "removed", "added", "removed (first div.)", "added (first div.)"], rows)
    w("")
    w("## Classes of the changed decisions (τ-bench's labels only)")
    rows = []
    for mode in ("exact", "order_blind"):
        cc = num["classes"][mode]["counts"]
        for g in ("all", "part=main", "part=stage_b"):
            x = cc["all"].get(g, {})
            if x or g == "all":
                rows.append([g, mode] + [x.get(k, 0) for k in L.CHANGED_CLASSES])
    L_ += _tbl(["group", "matcher", *L.CHANGED_CLASSES], rows)
    for dd in num["class_detail"][:40]:
        w(f"- {dd['cls']}: `{dd['ck']}` {dd['tool']} ({', '.join(dd['changed']) or '-'}; tool accepts: {dd['accepted']})")
    w("")
    w("## Audit buckets (p4's definitions; write checks)")
    au = num["audit"]
    rows = []
    for b in E.BUCKETS:
        rows.append([E.BUCKET_SHORT[b]] + [au[g].get("part=main", {}).get(b, 0) for g in ("saved", "frozen", "v2", "v3")]
                    + [au[g].get("part=stage_b", {}).get(b, 0) for g in ("saved", "v3")])
    L_ += _tbl(["bucket", "main: saved", "frozen", "v2", "v3 tiny", "stage_b: saved", "v3 tiny"], rows)
    w("")
    w("## Length split")
    rows = []
    for g in ("bin=<12k", "bin=12-24k", "bin=>24k"):
        a = ch["all"].get(g, {})
        rows.append([g, a.get("checks", 0), a.get("removed", 0), a.get("added", 0)])
    L_ += _tbl(["bin", "checks", "removed", "added"], rows)
    w("")
    w("## Values behind blocks: set by an LLM")
    ls = num["llm_share"]
    for g in ("frozen", "v3"):
        x = ls[g]
        w(f"- {g}: LLM-set {x.get('llm', 0)} of {x.get('values', 0)} values behind {x.get('blocks', 0)} blocks "
          f"(code {x.get('code', 0)}, not asked {x.get('not_asked', 0)}, blocking value {x.get('blocking_value', 0)}).")
    w("")
    w("## Answer problems")
    L_ += answer_section(num)
    w("")
    w("## Tiny answers vs the judge's saved answers")
    L_ += compare_section(num, out["cmp_md"])
    w("")
    w(f"Run: {m.get('seconds')} s wall ({m.get('worker_seconds')} worker s). Label problems: "
      f"{len(m.get('problems') or [])}" + (f" (e.g. {m['problems'][:3]})" if m.get("problems") else "")
      + f". Errors: {m.get('errors')[:3] if m.get('errors') else 'none'}.")
    w("")
    L_ += _tbl(["file", "sha256"], file_rows([out["rows"], out["cmp_jsonl"], *OWN_FILES]))
    return "\n".join(L_) + "\n"


def render_compare(num: Dict[str, Any], side: str) -> str:
    items = [x for x in num["compare"]["items"] if x["blocked"]]
    L_ = [f"# Tracker v3 p12: tiny answers vs the judge's saved answers, disagreements on blocked checks ({side})", "",
          ("> **Development check, not a result.**" if side == "dev" else "> Hold-out (p12 step 4)."), "",
          "For an independent reviewer (a second opinion against the policy text; there is no objective label for "
          "\"is this a yes\"). One entry per (check, fact) where the fact's value from the tiny questions differs from "
          "the judge's saved value, on a check the saved guard or the tiny guard blocks. \"why\": \"from the question\" "
          "= the same code parts with the judge's value as the answer give the judge's side; \"from code parts\" = the "
          "stand-in differs from the judge too (code decided against the judge, not the question).", "",
          f"Entries: {len(items)}.", ""]
    for n, x in enumerate(items, 1):
        L_ += [f"## {n}. `{x['ck']}` — `{x['fact']}`", "",
               f"- conversation `{x['conv']}`, check {x['check']}, tool `{x['tool']}`; decisions: saved "
               f"{x['saved_decision']}, tiny {x['tiny_decision']}, stand-in {x['standin_decision']}; "
               f"{x.get('direction') or ''}",
               f"- fact value: tiny **{x['tiny_value']}** ({x['tiny_source']}); judge **{x['judge_value']}**; stand-in "
               f"{x['standin_value']} ({x['standin_source']}); why: {x['why']}",
               f"- judge's evidence: {json.dumps(x['judge_evidence'], ensure_ascii=False)}"]
        for a in x["asks"]:
            L_ += [f"- **{a['qid']}** (part {a['part']}): answer **{a['answer']}**, status {a['status']}, quote "
                   f"{json.dumps(a['quote'], ensure_ascii=False)}", f"  - question: {a['question']}", "",
                   "```text", (a["prompt_user"] or "(no prompt saved)").replace("```", "'''"), "```"]
        L_.append("")
    return "\n".join(L_) + "\n"


def phase_analyse(a: argparse.Namespace, out: Dict[str, str]) -> Dict[str, Any]:
    rows = E.read_jsonl(out["rows"])
    with open(out["meta"], encoding="utf-8") as f:
        meta = json.load(f)
    if a.side == "holdout":
        require_unlocked()
    recs, info = read_store(a.store)
    if meta.get("store") and meta["store"].get("sha256") != info["sha256"]:
        raise RuntimeError("the store changed between the run and the analysis")
    num = analyse(a.side, rows, meta, recs, info)
    E.write_json(out["json"], {k: v for k, v in num.items() if k != "compare"} | {
        "compare": {k: v for k, v in num["compare"].items() if k != "items"}})
    E.write_jsonl(out["cmp_jsonl"], num["compare"]["items"])
    with open(out["cmp_md"], "w", encoding="utf-8") as f:
        f.write(render_compare(num, a.side))
    with open(out["md"], "w", encoding="utf-8") as f:
        f.write(render_dev(num, out) if a.side == "dev" else render_holdout(num, out))
    pm = num["pass_marks"]
    say(f"[analyse] {a.side}: pass marks " + ", ".join(f"{k} {'PASS' if v['pass'] else 'FAIL'}" for k, v in pm.items()
                                                     if isinstance(v, dict)) + f"; all {pm['all_pass']}")
    say(f"[analyse] answers {json.dumps(num['answers']['used_status'])}; unclear blocks "
        f"{json.dumps(num['unclear_blocks']['counts'])}; two keys {json.dumps(num['two_keys']['counts'])}; compare "
        f"{json.dumps(num['compare']['counts'])}")
    say(f"[analyse] wrote {rel(out['md'])}, {rel(out['json'])}, {rel(out['cmp_md'])}, {rel(out['cmp_jsonl'])}")
    return num


# ----------------------------------------------------------------------------------------------- main
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="python -B -m scoring.v3_p12_offline", description=__doc__.split("\n")[0])
    ap.add_argument("--holdout", action="store_true", help="the hold-out (needs the second flag too)")
    ap.add_argument(LOOK_FLAG, dest="look", action="store_true", help="the main chat's one hold-out look")
    ap.add_argument("--phases", default="run,analyse", help="comma list of run, analyse")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--shards", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None, help="dev: conversations per data set (default 50 = p12a's); "
                                                            "a smaller number is a smoke test")
    ap.add_argument("--verify-every", type=int, default=10)
    ap.add_argument("--store", default=STORE, help="the answers file (read only)")
    ap.add_argument("--labels", default=HOLDOUT_LABELS, help="hold-out: the hold-out tool labels file")
    ap.add_argument("--out-dir", default=None, help="write every output here (tests)")
    a = ap.parse_args(argv)
    a.side = "holdout" if (a.holdout or a.look) else "dev"
    if not 1 <= a.workers <= 3:
        ap.error("--workers must be 1, 2 or 3 on this machine")
    if a.shards < 1:
        ap.error("--shards must be >= 1")
    return a


def main(argv: Optional[List[str]] = None) -> int:
    a = parse_args(argv)
    try:
        if a.side == "holdout":
            unlock(a.holdout, a.look)                 # both flags, or refused before anything is read
            if a.limit is not None:
                raise HoldoutLocked("--limit is not allowed on the hold-out (all of it, once)")
        out = outputs(a.side, a.out_dir)
        phases = [p for p in a.phases.split(",") if p]
        if not phases or set(phases) - {"run", "analyse"}:
            raise HoldoutLocked(f"unknown phases {phases}")
        if a.side == "holdout" and "run" in phases and os.path.exists(out["rows"]):
            raise HoldoutLocked(f"{rel(out['rows'])} exists: the hold-out run is made once (analyse from it with "
                                f"--phases analyse, or move it away by hand)")
    except HoldoutLocked as e:
        say(f"REFUSED: {e.msg}")
        return 2
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise SystemExit("set PYTHONHASHSEED=0 (the hash seed must be fixed before Python starts)")
    from state_tracker.v3.frozen import check_manifest
    manifest = check_manifest()
    if not os.path.isfile(a.store):
        raise SystemExit(f"no answers file {a.store}")
    for p in out.values():
        os.makedirs(os.path.dirname(p), exist_ok=True)
    worker_init(a.side, a.store, a.holdout, a.look)    # this process: safety, guards (FROZEN_SHA256 checked)
    from guard import tgr_tracker_v3 as G
    frozen_start = G.check_frozen_v3()
    say(f"[p12] side {a.side}; manifest ok ({len(manifest)} entries); v3 guard inputs {len(frozen_start['sha256'])} "
        f"files; store {rel(a.store)} ({_W['store_info']['kept']} answers, partial last line "
        f"{_W['store_info']['partial_last_line']}); phases {phases}")
    t0 = time.time()
    if "run" in phases:
        phase_run(a, out)
    G.check_frozen_v3()
    check_manifest()
    if "analyse" in phases:
        phase_analyse(a, out)
    say(f"[p12] done in {time.time() - t0:.0f} s; the eval v2 manifest and the v3 guard inputs are unchanged")
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.exit(main())
