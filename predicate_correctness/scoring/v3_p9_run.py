"""Tracker v3, part 9: the offline runs of the v3 guard (guard/tgr_tracker_v3.py). $0: no LLM call, no network.

Development data only (fork/offline_v3.py side "dev"; hold-out conversations are skipped before any check is read).
Every judge call is set to fail (fork/rebuild_check.py safety_setup), TGR's own LLM judge method is replaced by a
counter that raises, the network is refused (questions.block_network()), and writes go only under output/.

  (a) P9.5 (Gate 0 style): the guard with facts = v2, meaning = saved_judge ("v3_v2facts") on every saved check of
      the development data whose source guard is eval v2's (TGR + tracker): decision, margin (exact), violated rules,
      block-message bytes and the tracker part (fork/offline_v3.py compare_with_saved), the past-trace length
      (trace_len_before) and every other record field (all fields but timing, token usage and the "v3" part) equal
      the saved record. Pass: 100 %. Also P9.4 on a sample (every 5th v2-source conversation): eval v2's own guard
      ("v2") in this process (v3 loaded and registered) gives the same record, field by field; and on every 10th
      frozen-source conversation the v2-facts guard equals eval v2's guard.
  (b) the guard with facts = v3, meaning = saved_judge, messages = frozen ("v3", lazy) on all development data:
      counts only (decisions, blocks, unknowns per check, state errors, problems, fact sources, the questions lazy
      evaluation would ask, by question id, and the facts it skips). p11 does the analysis.
  (c) meaning = tiny with fake answers (all "unclear", all "yes", and a mixed yes / no / unclear fake fixed by the
      question key) on a sample (every --tiny-every th development conversation): lazy and full evaluation, with
      their decisions compared and the questions counted; 0 network events asserted.

States: in (b) and (c) the guard gets its states from one walk over each conversation (state.Tracker, the same code
build_state runs), installed as the guard's offline `state_source`; every --verify-every th check is compared with
build_state (db, shown, events, problems, today, pending) and a difference is counted (pass: 0; that check then
uses build_state). (a) runs eval v2's frozen tracker code, which builds its own state.

Shards (--workers up to 3; --shards per part, default 2 x workers): each part is split by conversation (ordinal % n
== k of every data set, as fork/offline_v3.py iter_conversations), run in worker processes (spawn, PYTHONHASHSEED=0),
and merged: counts add, example lists are sorted by the one-process check order, distinct question keys are counted
over all shards, and which walked states are verified depends only on the conversation. So the numbers equal a
one-process run.

Run from predicate_correctness/ (the venv Python, the hash seed fixed):
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m scoring.v3_p9_run --workers 3 \\
        > output/logs/v3_p9_<nn>_run.log 2>&1
main() first calls state_tracker.v3.frozen.check_manifest(). Writes output/eval_v3/p9_run.json and
output/eval_v3/p9_guard.md. Imports no other scoring module and no gold code.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import sys
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from fork import offline_v3 as O                                          # noqa: E402  (sets up the runner path)
from state_tracker import paths                                           # noqa: E402
from state_tracker import state as S                                      # noqa: E402

OUT_DIR = os.path.join(paths.OUTPUT_DIR, "eval_v3")
OUT_JSON = os.path.join(OUT_DIR, "p9_run.json")
OUT_MD = os.path.join(OUT_DIR, "p9_guard.md")
DEV_DATASETS = tuple(d for d in O.DATASETS if d not in ("ours.p10_luna_val", "partner.luna_val"))
VOLATILE = ("seconds", "usage", "calls", "attempts", "v3")
OWN_FILES = ("guard/tgr_tracker_v3.py", "tests/test_v3_guard.py", "scoring/v3_p9_run.py")
FAKES = ("unclear", "yes", "mixed")
COUNT: collections.Counter = collections.Counter()          # judge / LLM calls seen (P9.1: 0)


def say(msg: str) -> None:
    print(msg, flush=True)


def sha256_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ----------------------------------------------------------------------------------------------- safety
def install_judge_counters() -> None:
    """TGR's own LLM judge and the runner's structured LLM call: counted, then refused (P9.1)."""
    from method_tgr import llm as tgr_llm                                 # runner copy
    from method_tgr import runtime as RT

    def judge(self, *a, **k):
        COUNT["TGR._judge (LLM judge) calls"] += 1
        raise AssertionError("TGR's LLM judge was called")

    def structured(*a, **k):
        COUNT["method_tgr.llm.structured calls"] += 1
        raise AssertionError("an LLM call was attempted")

    RT.TGR._judge = judge
    tgr_llm.structured = structured
    RT.llm.structured = structured


# ----------------------------------------------------------------------------------------------- states
def same_state(a: Any, b: Any) -> bool:
    return (a.db == b.db and a.shown == b.shown and a.shown_meta == b.shown_meta and a.events == b.events
            and a.mismatches == b.mismatches and a.parse_problems == b.parse_problems and a.problems == b.problems
            and a.n_steps == b.n_steps and a.today == b.today and a.today_text == b.today_text
            and a.pending == b.pending and a.domain == b.domain)


class WalkStates:
    """The guard's offline state_source for one conversation: one Tracker fed along the executed messages. Falls
    back to build_state when the history is not a prefix of this conversation, goes back, or ends inside a call."""

    def __init__(self, conv: O.SavedConversation, counts: collections.Counter, verify_every: int):
        self.executed = conv.ep["executed"]
        self.domain = conv.domain
        self.tr = S.Tracker(conv.domain)
        self.i = 0
        self.n = 0                                   # states given so far (the verified ones: fixed per conversation)
        self.ordinal = conv.ordinal
        self.counts = counts
        self.verify_every = max(0, int(verify_every))

    def __call__(self, history: List[dict], tool: str, args: Dict[str, Any]) -> Any:
        c = self.counts
        n = len(history)
        prefix = (n >= self.i and n <= len(self.executed)
                  and all(history[k] is self.executed[k] for k in range(n)))
        if not prefix:
            c["walk: fallback to build_state (not a prefix)"] += 1
            return S.build_state(history, {"tool": tool, "args": args}, domain=self.domain)
        while self.i < n:
            self.tr.feed_message(self.executed[self.i])
            self.i += 1
        if self.tr._open:
            c["walk: fallback to build_state (open call)"] += 1
            return S.build_state(history, {"tool": tool, "args": args}, domain=self.domain)
        st = self.tr.state
        st.pending = S.normalize_action({"tool": tool, "args": args})
        c["walk: states"] += 1
        self.n += 1
        if self.verify_every and (self.ordinal + self.n - 1) % self.verify_every == 0:
            ref = S.build_state(history, {"tool": tool, "args": args}, domain=self.domain)
            c["walk: verified with build_state"] += 1
            if not same_state(st, ref):
                c["walk: DIFFERS from build_state"] += 1
                return ref
        return st


# ----------------------------------------------------------------------------------------------- records
def comparable(rec: dict) -> str:
    """A guard record without timing, token usage, TGR.step's attempt count and the v3 part, as canonical JSON."""
    r = {k: v for k, v in rec.items() if k not in VOLATILE}
    tr = r.get("tracker")
    if isinstance(tr, dict):
        tr = {k: v for k, v in tr.items() if k != "seconds"}
        if isinstance(tr.get("state"), dict):
            tr["state"] = {k: v for k, v in tr["state"].items() if k != "seconds"}
        r["tracker"] = tr
    return json.dumps(O._jn(r), sort_keys=True, ensure_ascii=False)


def field_diffs(a: dict, b: dict) -> List[str]:
    ja, jb = json.loads(comparable(a)), json.loads(comparable(b))
    return sorted(k for k in set(ja) | set(jb) if ja.get(k) != jb.get(k))


def judged_of(ch: O.SavedCheck, c: collections.Counter) -> Dict[str, dict]:
    """The saved judge values of a check; {} when the judge was skipped in the source run (counted)."""
    j = ch.saved_judge()
    if j is None:
        c["judge skipped in the source run (given {})"] += 1
        return {}
    return j


def dev_conversations(datasets: Iterable[str], c: collections.Counter, limit: Optional[int] = None,
                      part: Optional[Tuple[int, int]] = None) -> Iterable[O.SavedConversation]:
    """The development conversations (part = (k, n): only those with ordinal % n == k, as fork/offline_v3.py)."""
    n_by: collections.Counter = collections.Counter()
    for conv in O.iter_conversations(list(datasets), part=part):
        if conv.side != O.DEV:
            c["hold-out conversations skipped (not read)"] += 1
            continue
        n_by[conv.dataset] += 1
        if limit is not None and n_by[conv.dataset] > limit:
            continue
        yield conv


# ----------------------------------------------------------------------------------------------- (a) P9.5, P9.4
def order_of(ch: O.SavedCheck) -> List[int]:
    """The one-process order of a check (data set, conversation, check): lists of examples are sorted by it."""
    return [O.DATASETS.index(ch.dataset), ch.conv.ordinal, ch.check_idx]


def run_a(datasets: Iterable[str], limit: Optional[int] = None, p94_every: int = 5, frozen_every: int = 10,
          log: Callable[[str], None] = say, part: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
    t0 = time.time()
    tot: collections.Counter = collections.Counter()
    by: Dict[str, collections.Counter] = collections.OrderedDict()
    misses: List[Dict[str, Any]] = []
    for conv in dev_conversations(datasets, tot, limit, part):
        c = by.setdefault(conv.dataset, collections.Counter())
        v2src = conv.saved_guard == "tgr_tracker"
        p94 = v2src and conv.ordinal % p94_every == 0
        fz = (not v2src) and conv.ordinal % frozen_every == 0
        if not (v2src or fz):
            continue
        c["conversations"] += 1
        for ch in conv.checks():
            judged = judged_of(ch, c)
            try:
                res = O.decide(ch, "v3_v2facts", judged=judged)
            except Exception as e:  # noqa: BLE001 - counted as a miss
                c["errors"] += 1
                if len(misses) < 20:
                    misses.append({"ckey": ch.ckey, "error": f"{type(e).__name__}: {e}"[:300], "_order": order_of(ch)})
                continue
            rec = res["record"]
            c["records with the three switches"] += rec.get("v3", {}).get("switches") == {
                "facts": "v2", "meaning": "saved_judge", "messages": "frozen"}
            if v2src:
                c["checks (v2 source)"] += 1
                c["judged (v2 source)"] += ch.judged
                cmp = O.compare_with_saved(ch, res)
                tlb = rec.get("trace_len_before") == ch.saved.get("trace_len_before")
                same_all = comparable(rec) == comparable(ch.saved)
                ok = cmp["pass"] and tlb and same_all
                c["P9.5 reproduced"] += ok
                c["decision equal"] += cmp["main"]["decision"]
                for k, v in cmp["main"].items():
                    c[f"main field equal: {k}"] += v
                c["trace_len_before equal"] += tlb
                c["all record fields equal"] += same_all
                if ch.cap_override:
                    c["cap overrides"] += 1
                    c["cap override decision equal"] += cmp["main"]["decision"]
                if not ok and len(misses) < 20:
                    misses.append({"ckey": ch.ckey, "differs": cmp["differs"], "trace_len_before": tlb,
                                   "fields": field_diffs(rec, ch.saved)[:10], "cap_override": ch.cap_override,
                                   "_order": order_of(ch)})
                if p94:
                    r2 = O.decide(ch, "v2", judged=judged)["record"]
                    c["P9.4 checks"] += 1
                    c["P9.4 eval v2 guard = saved record (all fields)"] += comparable(r2) == comparable(ch.saved)
                    c["P9.4 eval v2 guard = v2-facts guard (all fields)"] += comparable(r2) == comparable(rec)
                    c["P9.4 eval v2 guard trace_len_before = saved"] += (r2.get("trace_len_before")
                                                                       == ch.saved.get("trace_len_before"))
            else:
                r2 = O.decide(ch, "v2", judged=judged)["record"]
                c["frozen-source sample checks"] += 1
                c["frozen-source sample: v2-facts guard = eval v2 guard (all fields)"] += (comparable(r2)
                                                                                          == comparable(rec))
        tot["conversations done"] += 1
        if tot["conversations done"] % 200 == 0:
            log(f"[a] {tot['conversations done']} conversations, {time.time() - t0:.0f} s")
    for c in by.values():
        tot.update(c)
    return {"by_dataset": {d: dict(c) for d, c in by.items()}, "total": dict(tot), "misses": misses,
            "seconds": round(time.time() - t0, 1)}


# ----------------------------------------------------------------------------------------------- (b) v3 counts
def _hist(c: collections.Counter, prefix: str, n: int) -> None:
    c[f"{prefix} {n if n < 5 else '5+'}"] += 1


def run_b(datasets: Iterable[str], limit: Optional[int] = None, verify_every: int = 10,
          log: Callable[[str], None] = say, part: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
    from guard.tgr_tracker_v3 import KINDS
    t0 = time.time()
    tot: collections.Counter = collections.Counter()
    by: Dict[str, collections.Counter] = collections.OrderedDict()
    walk: collections.Counter = collections.Counter()
    sources: collections.Counter = collections.Counter()
    problems: collections.Counter = collections.Counter()
    state_errors: collections.Counter = collections.Counter()
    fact_errors: collections.Counter = collections.Counter()
    asked: collections.Counter = collections.Counter()
    asked_facts: collections.Counter = collections.Counter()
    skipped_facts: collections.Counter = collections.Counter()
    skipped_q: collections.Counter = collections.Counter()
    pending_q: collections.Counter = collections.Counter()
    unknown_facts: collections.Counter = collections.Counter()
    changed: collections.Counter = collections.Counter()
    errors: List[Dict[str, Any]] = []
    fb0 = sum(O.guard_for("v3", d).counters["message_fallbacks"] for d in paths.DOMAINS)
    for conv in dev_conversations(datasets, tot, limit, part):
        c = by.setdefault(conv.dataset, collections.Counter())
        c["conversations"] += 1
        g = O.guard_for("v3", conv.domain)
        g.state_source = WalkStates(conv, walk, verify_every)
        try:
            for ch in conv.checks():
                judged = judged_of(ch, c)
                c["checks"] += 1
                try:
                    res = O.decide(ch, "v3", judged=judged)
                except Exception as e:  # noqa: BLE001 - counted
                    c["errors"] += 1
                    if len(errors) < 20:
                        errors.append({"ckey": ch.ckey, "error": f"{type(e).__name__}: {e}"[:300],
                                       "_order": order_of(ch)})
                    continue
                rec = res["record"]
                v = rec["v3"]
                c["records with the three switches"] += v.get("switches") == {
                    "facts": "v3", "meaning": "saved_judge", "messages": "frozen"}
                c[f"decision {res['decision']}"] += 1
                c[f"saved {ch.saved_decision}"] += 1
                if res["decision"] != ch.saved_decision:
                    c[f"decision changed: saved {ch.saved_decision} -> v3 {res['decision']}"] += 1
                if ch.cap_override:
                    c["cap overrides (saved)"] += 1
                if v["facts"] is None:
                    c["checks without facts (no rule, or a rule on the action alone)"] += 1
                    continue
                c["checks with facts"] += 1
                c["facts evaluated"] += len(v["facts"])
                nu = len(v["unknown"])
                c["unknown values"] += nu
                c["checks with an unknown value"] += nu > 0
                _hist(c, "unknowns per check:", nu)
                for n in v["unknown"]:
                    unknown_facts[n] += 1
                for n, f in v["facts"].items():
                    sources[f["source"]] += 1
                    c["facts with a value and a source"] += f["source"] in KINDS and (
                        isinstance(f["value"], bool) or (f["value"] is None and f["source"] == "saved_unknown"))
                    for k in f["problems"]:
                        problems[(n, k)] += 1
                for e in v["state_errors"]:
                    state_errors[e["kind"]] += 1
                c["checks with a state error"] += bool(v["state_errors"])
                for e in v["fact_errors"]:
                    fact_errors[(e["fact"], e["error"])] += 1
                q = v["questions"]
                asked.update(q["asked"])
                asked_facts.update(q["asked_facts"])
                skipped_facts.update(q["skipped_facts"])
                skipped_q.update(q["skipped_first_question"])
                c["question facts (code did not decide)"] += q["pending_facts"]
                c["question facts answered"] += len(q["asked_facts"])
                c["question facts skipped (lazy)"] += len(q["skipped_facts"])
                c["checks asking a question"] += bool(q["asked_facts"])
                for n in v["facts"]:
                    if "first_question" in v["facts"][n]:
                        pending_q[v["facts"][n]["first_question"]] += 1
                changed.update(v.get("changed_vs_saved_judge") or [])
                if (v.get("message") or {}).get("fallback"):
                    c["message fallbacks"] += 1
        finally:
            g.state_source = None
        tot["conversations done"] += 1
        if tot["conversations done"] % 200 == 0:
            log(f"[b] {tot['conversations done']} conversations, {time.time() - t0:.0f} s, walk {dict(walk)}")
    for c in by.values():
        tot.update(c)
    fb = sum(O.guard_for("v3", d).counters["message_fallbacks"] for d in paths.DOMAINS) - fb0

    def pairs(cn: collections.Counter) -> Dict[str, int]:
        return {f"{a}: {b}": n for (a, b), n in sorted(cn.items())}

    return {"by_dataset": {d: dict(c) for d, c in by.items()}, "total": dict(tot), "walk": dict(walk),
            "fact_sources": dict(sorted(sources.items())), "problems": pairs(problems),
            "state_errors": dict(state_errors), "fact_errors": pairs(fact_errors),
            "questions_asked_by_id": dict(sorted(asked.items())),
            "question_facts_answered": dict(sorted(asked_facts.items())),
            "question_facts_skipped": dict(sorted(skipped_facts.items())),
            "skipped_by_first_question": dict(sorted(skipped_q.items())),
            "question_facts_by_first_question": dict(sorted(pending_q.items())),
            "unknown_by_fact": dict(sorted(unknown_facts.items())),
            "changed_vs_saved_judge_by_fact": dict(sorted(changed.items())),
            "message_fallbacks_counter": fb, "errors": errors, "seconds": round(time.time() - t0, 1)}


# ----------------------------------------------------------------------------------------------- (c) tiny, fakes
def mixed_policy(qid: str, inputs: Dict[str, Any], norm: Dict[str, Any]) -> str:
    """A fixed mixed fake: yes / no / unclear from the sha256 of the question and its normalized input."""
    h = int(hashlib.sha256((qid + json.dumps(norm, sort_keys=True)).encode("utf-8")).hexdigest()[:8], 16) % 20
    return "unclear" if h < 2 else ("yes" if h < 11 else "no")


def fake_backend(name: str):
    from state_tracker.v3 import questions as Q
    return Q.FakeBackend(mixed_policy if name == "mixed" else name)


def prepare_c() -> Tuple[Dict[Tuple[str, bool], Any], Dict[Tuple[str, str, bool], Any]]:
    """The fake answers hooks and the meaning = tiny guards of (c) (built at the start: frozen inputs checked once)."""
    from guard import tgr_tracker_v3 as G
    from state_tracker.v3 import questions as Q
    hooks = {(f, lazy): Q.Questions(fake_backend(f)) for f in FAKES for lazy in (True, False)}
    guards = {(d, f, lazy): G.build(d, facts="v3", meaning="tiny", messages="frozen", lazy=lazy,
                                   answers=hooks[(f, lazy)])
              for d in paths.DOMAINS for f in FAKES for lazy in (True, False)}
    return hooks, guards


def run_c(datasets: Iterable[str], every: int = 40, limit: Optional[int] = None, verify_every: int = 10,
          log: Callable[[str], None] = say, prepared: Optional[tuple] = None,
          part: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
    from guard import tgr_tracker_v3 as G
    from state_tracker.v3 import questions as Q
    t0 = time.time()
    tot: collections.Counter = collections.Counter()
    walk: collections.Counter = collections.Counter()
    hooks, guards = prepared or prepare_c()
    per: Dict[str, collections.Counter] = {f: collections.Counter() for f in FAKES}
    diffs: List[Dict[str, Any]] = []
    for conv in dev_conversations(datasets, tot, limit, part):
        if conv.ordinal % every != 0:
            continue
        tot["conversations"] += 1
        ws = WalkStates(conv, walk, verify_every)
        for g in (guards[(conv.domain, f, lz)] for f in FAKES for lz in (True, False)):
            g.state_source = ws
        try:
            for ch in conv.checks():
                tot["checks"] += 1
                for f in FAKES:
                    pc = per[f]
                    out = {}
                    for lazy in (True, False):
                        rec = O.run_guard(guards[(conv.domain, f, lazy)], ch.history, ch.msg, ch.n_exec, ch.past, {})
                        out[lazy] = rec
                        v = rec["v3"]
                        tag = "lazy" if lazy else "full"
                        if v["facts"] is not None:
                            for n, x in v["facts"].items():
                                pc[f"{tag}: facts"] += 1
                                pc[f"{tag}: facts with a true / false value"] += isinstance(x["value"], bool)
                                pc[f"{tag}: facts with a source"] += x["source"] in G.KINDS
                                pc[f"{tag}: source {x['source']}"] += 1
                                pc[f"{tag}: unclear problems"] += x["problems"].count("unclear")
                            pc[f"{tag}: question asks"] += sum(v["questions"]["asked"].values())
                            pc[f"{tag}: question facts answered"] += len(v["questions"]["asked_facts"])
                            pc[f"{tag}: question facts skipped"] += len(v["questions"]["skipped_facts"])
                            pc[f"{tag}: state errors"] += len(v["state_errors"])
                            pc[f"{tag}: fact errors"] += len(v["fact_errors"])
                        pc[f"{tag}: blocks"] += not rec.get("action_allowed", True)
                    a, b = out[True], out[False]
                    same = (bool(a.get("action_allowed", True)) == bool(b.get("action_allowed", True))
                            and [r["rule_id"] for r in a.get("violated_rules") or []]
                            == [r["rule_id"] for r in b.get("violated_rules") or []])
                    pc["checks"] += 1
                    pc["lazy = full: decision and violated rules"] += same
                    pc["lazy = full: margin exactly"] += a.get("margin") == b.get("margin")
                    if not same and len(diffs) < 20:
                        diffs.append({"ckey": ch.ckey, "fake": f, "_order": order_of(ch)})
        finally:
            for g in guards.values():
                g.state_source = None
        if tot["conversations"] % 25 == 0:
            log(f"[c] {tot['conversations']} conversations, {tot['checks']} checks, {time.time() - t0:.0f} s")
    keys = {}
    for f in FAKES:
        per[f]["asks by id, lazy"] = dict(sorted(hooks[(f, True)].stats.asks.items()))
        per[f]["asks by id, full"] = dict(sorted(hooks[(f, False)].stats.asks.items()))
        for lazy in (True, False):                       # distinct question keys: counted after the merge
            keys[f"{f}|{'lazy' if lazy else 'full'}"] = sorted({e["key"] for e in hooks[(f, lazy)].log})
    net = Q.network_events()
    return {"total": dict(tot), "walk": dict(walk), "per_fake": {f: dict(c) for f, c in per.items()},
            "lazy_full_differences": diffs, "network_events": len(net), "every": every, "_keys": keys,
            "seconds": round(time.time() - t0, 1)}


# ----------------------------------------------------------------------------------------------- the report
def _f(n: Any) -> str:
    return f"{n:,}" if isinstance(n, int) and not isinstance(n, bool) else str(n)


def tests_summary(path: Optional[str]) -> Optional[str]:
    if not path or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    ran = [ln for ln in text.splitlines() if ln.startswith("Ran ")]
    status = [ln for ln in text.splitlines() if ln.startswith("OK") or ln.startswith("FAILED")]
    return f"{ran[-1] if ran else '?'}; {status[-1] if status else '?'} (`{os.path.relpath(path, PC_DIR)}`)"


def render_md(num: Dict[str, Any], meta: Dict[str, Any]) -> str:
    L: List[str] = []
    w = L.append
    a, b, c = num.get("a"), num.get("b"), num.get("c")
    w("# Tracker v3, part 9: the v3 guard, with no judge ($0)")
    w("")
    w(f"Written by `scoring/v3_p9_run.py` on {meta['when']}. No LLM call, no network: judge calls set to fail, TGR's "
      f"LLM judge replaced by a counter, network refused (events: {meta['network_events']}). Development data only "
      f"(hold-out conversations skipped unread). Manifest: {meta['manifest']}. Run time {meta['seconds']} s with {meta['workers']} worker process(es), {meta['shards']} shards per part.")
    w("")
    w("## Pass marks")
    calls = num["judge_calls"]
    w(f"- **P9.1 judge calls: {'PASS' if sum(calls.values()) == 0 else 'FAIL'}.** "
      + "; ".join(f"{k}: {v}" for k, v in calls.items()) + ". The tests assert 0 too.")
    if c:
        pf = c["per_fake"]
        ok2 = all(x.get("lazy: facts", 0) == x.get("lazy: facts with a true / false value", -1)
                  == x.get("lazy: facts with a source", -2) for x in pf.values())
        w(f"- **P9.2 every fact has a value and a source: {'PASS' if ok2 else 'FAIL'}** (meaning = tiny, fake answers, "
          f"run c): " + "; ".join(f"{f}: {x.get('lazy: facts with a true / false value', 0)} of "
                                  f"{x.get('lazy: facts', 0)} true/false, with a source "
                                  f"{x.get('lazy: facts with a source', 0)}" for f, x in pf.items())
          + ". With meaning = saved_judge a saved unknown can stay unknown (counted in b)"
          + (f"; run b: {_f(b['total'].get('facts with a value and a source', 0))} of "
             f"{_f(b['total'].get('facts evaluated', 0))} facts have true / false, or None as saved_unknown, and a "
             f"source." if b else "."))
    w("- **P9.3 state errors take the blocking value, counted:** by test (`tests/test_v3_guard.py`). "
      + (f"Run b: {_f(sum(b['state_errors'].values()))} state errors, {_f(sum(int(v) for v in b['fact_errors'].values()))} fact "
         f"errors on the development data." if b else ""))
    if a:
        t = a["total"]
        w(f"- **P9.4 eval v2's guard byte-identical: {'PASS' if t.get('P9.4 checks') and t.get('P9.4 checks') == t.get('P9.4 eval v2 guard = saved record (all fields)') == t.get('P9.4 eval v2 guard = v2-facts guard (all fields)') else 'FAIL'}** "
          f"(sample, v3 loaded): {_f(t.get('P9.4 eval v2 guard = saved record (all fields)', 0))} of "
          f"{_f(t.get('P9.4 checks', 0))} checks equal the saved record in every field; "
          f"{_f(t.get('P9.4 eval v2 guard = v2-facts guard (all fields)', 0))} equal the v2-facts guard; "
          f"trace_len_before {_f(t.get('P9.4 eval v2 guard trace_len_before = saved', 0))}.")
        n95 = t.get("checks (v2 source)", 0)
        w(f"- **P9.5 stand-in reproduces eval v2: {'PASS' if n95 and t.get('P9.5 reproduced') == n95 and not t.get('errors') else 'FAIL'}.** "
          f"{_f(t.get('P9.5 reproduced', 0))} of {_f(n95)} v2-source development checks "
          f"({_f(t.get('judged (v2 source)', 0))} judged; {_f(t.get('cap overrides', 0))} cap overrides, held to "
          f"every field too): decision {_f(t.get('decision equal', 0))}, margin "
          f"{_f(t.get('main field equal: margin', 0))}, "
          f"violated rules {_f(t.get('main field equal: violated_rules', 0))}, message bytes "
          f"{_f(t.get('main field equal: message', 0))}, tracker part {_f(t.get('main field equal: tracker', 0))}, "
          f"trace_len_before {_f(t.get('trace_len_before equal', 0))}, all record fields "
          f"{_f(t.get('all record fields equal', 0))}. Errors {t.get('errors', 0)}.")
    w("")
    if a:
        w("## (a) facts = v2, meaning = saved_judge")
        w("| data set | conv. | checks (v2 source) | reproduced | trace_len_before | all fields | P9.4 sample | "
          "frozen-source sample = eval v2 guard |")
        w("|---|---|---|---|---|---|---|---|")
        for d, x in a["by_dataset"].items():
            w(f"| {d} | {_f(x.get('conversations', 0))} | {_f(x.get('checks (v2 source)', 0))} | "
              f"{_f(x.get('P9.5 reproduced', 0))} | {_f(x.get('trace_len_before equal', 0))} | "
              f"{_f(x.get('all record fields equal', 0))} | "
              f"{_f(x.get('P9.4 eval v2 guard = saved record (all fields)', 0))} / {_f(x.get('P9.4 checks', 0))} | "
              f"{_f(x.get('frozen-source sample: v2-facts guard = eval v2 guard (all fields)', 0))} / "
              f"{_f(x.get('frozen-source sample checks', 0))} |")
        w(f"Misses: {a['misses'] or 'none'}. Worker seconds: {a['worker_seconds']} ({a['shards']} shards).")
        w("")
    if b:
        t = b["total"]
        w("## (b) facts = v3, meaning = saved_judge, messages = frozen, lazy: counts")
        w(f"- Checks {_f(t.get('checks', 0))} ({_f(t.get('checks with facts', 0))} with facts); decisions: allow "
          f"{_f(t.get('decision allow', 0))}, block {_f(t.get('decision block', 0))} (saved: allow "
          f"{_f(t.get('saved allow', 0))}, block {_f(t.get('saved block', 0))}); changed: saved block -> v3 allow "
          f"{_f(t.get('decision changed: saved block -> v3 allow', 0))}, saved allow -> v3 block "
          f"{_f(t.get('decision changed: saved allow -> v3 block', 0))}. Errors {t.get('errors', 0)}.")
        w(f"- Unknown values {_f(t.get('unknown values', 0))} in {_f(t.get('checks with an unknown value', 0))} checks; "
          "per check: " + ", ".join(f"{k.split(':')[1].strip()}: {_f(v)}" for k, v in sorted(t.items())
                                    if k.startswith("unknowns per check:")) + ".")
        w(f"- Fact sources: {b['fact_sources']}.")
        w(f"- State errors: {b['state_errors'] or 0}; fact errors: {b['fact_errors'] or 0}; message fallbacks "
          f"{t.get('message fallbacks', 0)} (counter {b['message_fallbacks_counter']}).")
        w(f"- Problems (fact: kind): {b['problems'] or 'none'}.")
        w(f"- Question facts (code did not decide): {_f(t.get('question facts (code did not decide)', 0))}; answered "
          f"{_f(t.get('question facts answered', 0))}; skipped by lazy evaluation "
          f"{_f(t.get('question facts skipped (lazy)', 0))}; checks asking a question "
          f"{_f(t.get('checks asking a question', 0))}.")
        w(f"- Stand-in asks by question id (the questions lazy evaluation would ask with these answers): "
          f"{b['questions_asked_by_id']}.")
        w(f"- Question facts by their first question: {b['question_facts_by_first_question']}; skipped by first "
          f"question: {b['skipped_by_first_question']}.")
        w(f"- Answered facts: {b['question_facts_answered']}.")
        w(f"- Skipped facts: {b['question_facts_skipped']}.")
        w(f"- Unknown by fact: {b['unknown_by_fact'] or 'none'}.")
        w(f"- Walked states: {b['walk']}.")
        w("")
        w("| data set | conv. | checks | allow | block | saved block | block -> allow | allow -> block | unknown values |"
          " state errors |")
        w("|---|---|---|---|---|---|---|---|---|---|")
        for d, x in b["by_dataset"].items():
            w(f"| {d} | {_f(x.get('conversations', 0))} | {_f(x.get('checks', 0))} | {_f(x.get('decision allow', 0))} | "
              f"{_f(x.get('decision block', 0))} | {_f(x.get('saved block', 0))} | "
              f"{_f(x.get('decision changed: saved block -> v3 allow', 0))} | "
              f"{_f(x.get('decision changed: saved allow -> v3 block', 0))} | {_f(x.get('unknown values', 0))} | "
              f"{_f(x.get('checks with a state error', 0))} |")
        w(f"Worker seconds: {b['worker_seconds']} ({b['shards']} shards).")
        w("")
    if c:
        w(f"## (c) meaning = tiny, fake answers, every {c['every']}th development conversation")
        w(f"- {_f(c['total'].get('conversations', 0))} conversations, {_f(c['total'].get('checks', 0))} checks. "
          f"Network events: **{c['network_events']}**. Walked states: {c['walk']}.")
        w("| fake | checks | lazy = full (decision, violated rules) | margin equal | blocks lazy / full | question asks "
          "lazy / full | facts answered lazy / full | skipped (lazy) | new calls lazy / full | unclear problems lazy |")
        w("|---|---|---|---|---|---|---|---|---|---|")
        for f, x in c["per_fake"].items():
            w(f"| {f} | {_f(x.get('checks', 0))} | {_f(x.get('lazy = full: decision and violated rules', 0))} | "
              f"{_f(x.get('lazy = full: margin exactly', 0))} | {_f(x.get('lazy: blocks', 0))} / "
              f"{_f(x.get('full: blocks', 0))} | {_f(x.get('lazy: question asks', 0))} / "
              f"{_f(x.get('full: question asks', 0))} | {_f(x.get('lazy: question facts answered', 0))} / "
              f"{_f(x.get('full: question facts answered', 0))} | {_f(x.get('lazy: question facts skipped', 0))} | "
              f"{_f(x.get('new question calls (distinct keys), lazy', 0))} / "
              f"{_f(x.get('new question calls (distinct keys), full', 0))} | {_f(x.get('lazy: unclear problems', 0))} |")
        w(f"Lazy / full differences: {c['lazy_full_differences'] or 'none'}. Worker seconds: {c['worker_seconds']} ({c['shards']} shards).")
        w("")
    w("## Tests")
    w(f"- `tests/test_v3_guard.py`: {meta.get('tests') or 'not given (--tests-log)'}")
    w("")
    w("## Files")
    w("| file | sha256 |")
    w("|---|---|")
    for k, v in meta["sha256"].items():
        w(f"| `{k}` | `{v}` |")
    fs, fe = num.get("frozen_v3_start") or {}, num.get("frozen_v3_end") or {}
    if fs:
        w("")
        w(f"Inputs of the guard (`FROZEN_SHA256`): {len(fs['sha256'])} files checked at the start; not recorded yet: "
          f"{fs['unrecorded'] or 'none'}; at the end: "
          f"{'unchanged' if fe.get('sha256') == fs['sha256'] else 'CHANGED: ' + str(fe)[:300]}.")
        w("")
        w("| input | sha256 at the start |")
        w("|---|---|")
        for k, v in fs["sha256"].items():
            w(f"| `{k}` | `{v}` |")
    w("")
    w("## Commands")
    w("```")
    w("cd predicate_correctness")
    w("PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m unittest tests.test_v3_guard -v "
      "> output/logs/v3_p9_<nn>_tests.log 2>&1")
    w("PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m scoring.v3_p9_run --workers 3 "
      "--tests-log output/logs/v3_p9_<nn>_tests.log > output/logs/v3_p9_<nn>_run.log 2>&1")
    w("```")
    w(f"This run: `{' '.join(meta['argv'])}`.")
    return "\n".join(L) + "\n"


# ----------------------------------------------------------------------------------------------- shards
def setup_process() -> None:
    """Safety, counters and the guards of one process (the main one, or a worker): network refused, judge calls
    refused and counted, writes only under output/, every guard built (the frozen inputs checked)."""
    from fork import rebuild_check as RC
    RC.safety_setup()
    from state_tracker.v3 import questions as Q
    Q.block_network()
    install_judge_counters()
    from guard import tgr_tracker_v3 as G
    G.register()
    for d in paths.DOMAINS:
        for name in ("v3_v2facts", "v2", "v3"):
            O.guard_for(name, d)


def work(task: Tuple[str, List[str], int, int, Optional[int], int, int]) -> Dict[str, Any]:
    """One shard of one part: the conversations with ordinal % n == k of every data set."""
    from state_tracker.v3 import questions as Q
    letter, datasets, k, n, limit, tiny_every, verify_every = task
    c0, n0 = dict(COUNT), len(Q.network_events())
    tag = f"[{letter} {k}/{n}]"
    log = (lambda m: say(f"{tag} {m}"))
    if letter == "a":
        res = run_a(datasets, limit, log=log, part=(k, n))
    elif letter == "b":
        res = run_b(datasets, limit, verify_every, log=log, part=(k, n))
    else:
        res = run_c(datasets, tiny_every, limit, verify_every, log=log, part=(k, n))
    calls = {key: COUNT[key] - c0.get(key, 0) for key in COUNT}
    say(f"{tag} done in {res['seconds']} s")
    return {"part": letter, "k": k, "n": n, "res": res, "judge_calls": calls,
            "network_events": len(Q.network_events()) - n0}


def merge_values(a: Any, b: Any) -> Any:
    """Counters of two shards: numbers add, dicts merge key by key, lists join."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for key, v in b.items():
            out[key] = merge_values(out[key], v) if key in out else v
        return out
    if isinstance(a, list) and isinstance(b, list):
        return a + b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return a + b
    return a


def _ordered(d: Dict[str, Any]) -> Dict[str, Any]:
    order = {x: i for i, x in enumerate(O.DATASETS)}
    return {key: d[key] for key in sorted(d, key=lambda x: order.get(x, len(order)))}


def _sorted_dict(d: Any) -> Any:
    return {key: d[key] for key in sorted(d)} if isinstance(d, dict) else d


def finish_part(letter: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The merged result of a part, in the one-process form: example lists sorted by the check order (first 20),
    data sets in DATASETS order, distinct question keys counted over all shards."""
    res: Dict[str, Any] = {}
    for r in sorted(results, key=lambda x: x["k"]):
        res = merge_values(res, r["res"]) if res else r["res"]
    for key in ("misses", "errors", "lazy_full_differences"):
        if key in res:
            res[key] = [{k: v for k, v in x.items() if k != "_order"}
                        for x in sorted(res[key], key=lambda x: x.get("_order") or [])][:20]
    if "by_dataset" in res:
        res["by_dataset"] = _ordered(res["by_dataset"])
    for key, v in list(res.items()):
        if key not in ("by_dataset", "per_fake", "_keys", "misses", "errors", "lazy_full_differences") \
                and isinstance(v, dict):
            res[key] = _sorted_dict(v)
    if letter == "c":
        res["every"] = results[0]["res"]["every"]
        keys = res.pop("_keys")
        for f in FAKES:
            pf = res["per_fake"][f]
            pf["new question calls (distinct keys), lazy"] = len(set(keys[f"{f}|lazy"]))
            pf["new question calls (distinct keys), full"] = len(set(keys[f"{f}|full"]))
            for tag in ("lazy", "full"):
                pf[f"asks by id, {tag}"] = _sorted_dict(pf[f"asks by id, {tag}"])
            res["per_fake"][f] = _sorted_dict(pf)
        res["network_events"] = sum(r["network_events"] for r in results)
    res["worker_seconds"] = round(sum(r["res"]["seconds"] for r in results), 1)
    res["shards"] = len(results)
    res.pop("seconds", None)
    return res


# ----------------------------------------------------------------------------------------------- main
def main(argv: Optional[List[str]] = None) -> int:
    from state_tracker.v3.frozen import check_manifest
    manifest = check_manifest()
    ap = argparse.ArgumentParser(prog="python -B -m scoring.v3_p9_run", description=__doc__.split("\n")[0])
    ap.add_argument("--parts", default="a,b,c", help="comma list of a, b, c")
    ap.add_argument("--datasets", default=None, help="comma list (default: every development data set)")
    ap.add_argument("--limit", type=int, default=None, help="at most this many conversations per data set (smoke)")
    ap.add_argument("--tiny-every", type=int, default=10, help="(c): every n-th development conversation")
    ap.add_argument("--verify-every", type=int, default=10, help="compare every n-th walked state with build_state")
    ap.add_argument("--workers", type=int, default=1, help="worker processes (at most 3 on this machine)")
    ap.add_argument("--shards", type=int, default=None, help="shards per part (default: 2 x workers)")
    ap.add_argument("--tests-log", default=None, help="the unittest log of tests.test_v3_guard (for the report)")
    ap.add_argument("--out-json", default=OUT_JSON)
    ap.add_argument("--out-md", default=OUT_MD)
    a = ap.parse_args(argv)
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise SystemExit("set PYTHONHASHSEED=0 (the hash seed must be fixed before Python starts)")
    if not 1 <= a.workers <= 3:
        raise SystemExit("--workers must be 1, 2 or 3 on this machine")
    setup_process()
    from guard import tgr_tracker_v3 as G
    from state_tracker.v3 import questions as Q
    t0 = time.time()
    datasets = [d for d in (a.datasets.split(",") if a.datasets else DEV_DATASETS) if d]
    bad = [d for d in datasets if d not in DEV_DATASETS]
    if bad:
        raise SystemExit(f"not development data sets: {bad}")
    parts = [p for p in a.parts.split(",") if p]
    n = a.shards or (1 if a.workers == 1 else 2 * a.workers)
    frozen_start = G.check_frozen_v3()
    say(f"[p9] manifest ok ({len(manifest)} entries); data sets {datasets}; parts {parts}; workers {a.workers}, "
        f"shards {n}; v3 inputs {len(frozen_start['sha256'])} files (unrecorded {frozen_start['unrecorded']})")
    tasks = [(p, datasets, k, n, a.limit, a.tiny_every, a.verify_every) for p in parts for k in range(n)]
    results: List[Dict[str, Any]] = []
    if a.workers == 1:
        results = [work(t) for t in tasks]
    else:
        import multiprocessing
        ctx = multiprocessing.get_context("spawn")
        with ctx.Pool(a.workers, initializer=setup_process) as pool:
            for r in pool.imap_unordered(work, tasks):
                results.append(r)
                say(f"[p9] shard {r['part']} {r['k']}/{r['n']} back ({len(results)} of {len(tasks)}), "
                    f"{time.time() - t0:.0f} s")
    num: Dict[str, Any] = {}
    for p in parts:
        num[p] = finish_part(p, [r for r in results if r["part"] == p])
        say(f"[p9] ({p}) merged: {json.dumps(num[p].get('total'), sort_keys=True)[:2000]}")
    calls: collections.Counter = collections.Counter(dict(COUNT))
    for r in results:
        calls.update(r["judge_calls"])
    num["judge_calls"] = {"TGR._judge (LLM judge) calls": calls["TGR._judge (LLM judge) calls"],
                          "method_tgr.llm.structured calls": calls["method_tgr.llm.structured calls"]}
    num["frozen_v3_start"] = frozen_start
    try:
        num["frozen_v3_end"] = G.check_frozen_v3()
    except G.FrozenInputChangedV3 as e:                   # a file changed during the run: reported
        num["frozen_v3_end"] = {"changed": str(e)}
    n_net = len(Q.network_events()) + sum(r["network_events"] for r in results)
    shas = {f: sha256_file(os.path.join(PC_DIR, f)) for f in OWN_FILES if os.path.exists(os.path.join(PC_DIR, f))}
    meta = {"when": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "manifest": f"ok ({len(manifest)} entries)",
            "seconds": round(time.time() - t0, 1), "network_events": n_net, "sha256": shas,
            "workers": a.workers, "shards": n, "tests": tests_summary(a.tests_log),
            "argv": [os.path.basename(sys.executable), "-m", "scoring.v3_p9_run"] + list(
                argv if argv is not None else sys.argv[1:])}
    num["meta"] = meta
    os.makedirs(os.path.dirname(os.path.abspath(a.out_json)), exist_ok=True)
    with open(a.out_json + ".tmp", "w", encoding="utf-8") as f:
        json.dump(num, f, indent=1, sort_keys=True, default=str)
        f.write("\n")
    os.replace(a.out_json + ".tmp", a.out_json)
    with open(a.out_md + ".tmp", "w", encoding="utf-8") as f:
        f.write(render_md(num, meta))
    os.replace(a.out_md + ".tmp", a.out_md)
    say(f"[p9] judge calls {num['judge_calls']}; network events {n_net}; {meta['seconds']} s")
    ok = sum(num["judge_calls"].values()) == 0 and not n_net
    if "c" in num:
        ok = ok and num["c"]["network_events"] == 0 and not num["c"]["lazy_full_differences"]
    if "a" in num:
        t = num["a"]["total"]
        ok = ok and t.get("P9.5 reproduced") == t.get("checks (v2 source)") and not t.get("errors")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
