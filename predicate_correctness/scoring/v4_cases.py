"""Tracker v4 (scoring.v4_cases): the made-up case sets through each tiny question, scored against their labels.

Pass mark (preregistration_v4.md §14, overview §10): per question, at least 28 of 30 right on the yes side and at
least 28 of 30 right on the hard-no side. A side with fewer than 30 cases fails (said in the report). A case that
cannot be asked (its fields do not fit the question's inputs) counts as wrong.

Case files: output/eval_v4/cases/<qid>.jsonl, written by the blind writers from the v1 policy (one JSON object per
line). Fields read: `expect` (the label: yes / no; K17 added / not_added / not_said), `A`, `B`, `user_messages`,
`domain`, and any field named like a question input (`action`, `items_action`, `verb`, `reason`, `gloss`, ...); `id`
and `kind` for the report. Inputs: a field with the input's name wins; else the question's message inputs in order
take A, then B (K13 / K16: `user_messages`). A message input given a list is asked the way the guard asks it: each
message newest first, the first yes wins (ask_first_yes). An input `from: domain` takes the questions file's
domain_texts. A K3 case with `conversation` + `order_id` is asked on the guard's own window
(message_view.reminder_candidates, see window_candidates): no candidate -> "no" with no call, as the guard. The side: `side` if given; else expect yes -> the yes side, expect no -> the hard-no side; K17 (three
answers): the hard side is the hard kinds of cases_spec.md (K17_HARD_KINDS), the rest the plain side.
Unclear (D10): an unclear first answer (unclear, failed quote, bad output) is asked once more with the second
wording; the second answer counts. Both are reported.

Backends:
  fake   questions_v4.FakeBackendV4, in memory, $0 (--policy yes | no | unclear | expect: `expect` answers each case's
         label, so the scoring path must give 100 %): shape checks only
  real   main chat only: --i-am-the-main-chat --approved "<the user's words>" --max-usd (<= $2, inside the dev limit)
         --max-calls (<= 5,100); questions_v4.RealBackendV4 (approval_flag=True), store
         output/eval_v4/cases/answers.jsonl. The limits are shared by all v4 dev runs (v4_offline_eval's dev ledger:
         this run gets min(asked, what is left); every call is written there before it starts). Refused otherwise.
Outputs: output/eval_v4/cases_check_<backend>.md, .json and _results.jsonl (one line per case).

Run from predicate_correctness/:
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m scoring.v4_cases \\
        --backend fake --policy expect > output/logs/v4_cases_fake.log 2>&1
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from scoring import v4_offline_eval as OE                          # noqa: E402

CASES_DIR = os.path.join(OE.paths.OUTPUT_DIR, "eval_v4", "cases")
OUT_BASE = os.path.join(OE.paths.OUTPUT_DIR, "eval_v4")
PASS_RIGHT, PASS_OF = 28, 30
SIDES = ("yes", "hard_no")
K17_HARD_KINDS = ("question_no_reply", "price_question_only", "yes_but_without_insurance",
                  "listing_insurance_user_removes", "window_edge_other_booking")
POLICIES = ("yes", "no", "unclear", "expect")
YES_WORDS = ("yes", "added", "not_added")
_QFILE = re.compile(r"^(K[1-9][0-9]*)(?:v4)?\.jsonl$")


def base_qid(q: Any) -> str:
    s = str(q or "")
    m = re.match(r"^(K[1-9][0-9]*)(?:v4)?b?$", s)
    return m.group(1) if m else s


# ----------------------------------------------------------------------------------------------- the cases
def load_cases(cases_dir: str = CASES_DIR, qids: Optional[Sequence[str]] = None) -> Tuple[Dict[str, List[dict]],
                                                                                            List[str]]:
    """{qid: [case, ...]} of every <qid>.jsonl in the folder (file order), and the problems (bad lines)."""
    out: Dict[str, List[dict]] = {}
    problems: List[str] = []
    for p in sorted(glob.glob(os.path.join(cases_dir, "*.jsonl"))):
        m = _QFILE.match(os.path.basename(p))
        if not m:
            continue
        qid = m.group(1)
        if qids and qid not in qids:
            continue
        with open(p, encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    c = json.loads(line)
                except ValueError:
                    problems.append(f"{os.path.basename(p)}:{n}: not JSON")
                    continue
                if not isinstance(c, dict):
                    problems.append(f"{os.path.basename(p)}:{n}: not an object")
                    continue
                c = dict(c)
                c.setdefault("id", f"{qid}-{n:03d}")
                c["_qid"] = qid
                c["_line"] = n
                out.setdefault(qid, []).append(c)
    return out, problems


def side_of(case: dict) -> str:
    s = str(case.get("side") or "").lower()
    if s in ("yes", "easy", "plain", "positive"):
        return "yes"
    if s in ("no", "hard_no", "hard", "negative"):
        return "hard_no"
    exp = str(case.get("expect") or "").lower()
    if case.get("_qid") == "K17":
        return "hard_no" if case.get("kind") in K17_HARD_KINDS else "yes"
    return "yes" if exp == "yes" else "hard_no"


def case_inputs(case: dict, q: dict, doc: dict) -> Tuple[Dict[str, Any], Optional[str]]:
    """(inputs, the name of the message input that holds a candidate list or None). Raises ValueError when the case
    does not fit the question."""
    specs = list(q.get("inputs") or [])
    msg_specs = [s for s in specs if s.get("type") in ("message", "messages")]
    fill = [x for x in (case.get("A"), case.get("B")) if x is not None]
    if not fill and case.get("user_messages") is not None:
        fill = [case["user_messages"]]
    inputs: Dict[str, Any] = {}
    many: Optional[str] = None
    pos = 0
    for s in specs:
        name, typ = s.get("name"), s.get("type")
        if name in case:
            v = case[name]
        elif typ in ("message", "messages"):
            v = fill[pos] if pos < len(fill) else None
            pos += 1
            if v is None and len(msg_specs) == 1 and case.get("user_messages") is not None:
                v = case["user_messages"]
        elif s.get("from") == "domain":
            dom = case.get("domain")
            v = ((doc.get("domain_texts") or {}).get(name) or {}).get(dom)
            if v is None:
                raise ValueError(f"input {name!r} needs the case's domain (got {dom!r})")
        else:
            v = None
        if typ == "messages" and isinstance(v, str):
            v = [v]
        if typ == "message" and isinstance(v, (list, tuple)):
            vals = [x for x in v if isinstance(x, str) and x.strip()]
            if len(vals) == 1:
                v = vals[0]
            elif vals:
                if many is not None:
                    raise ValueError("two message inputs hold several messages")
                many, v = name, vals
            else:
                v = None
        if v is None or (isinstance(v, str) and not v.strip()):
            if not s.get("optional"):
                raise ValueError(f"no value for the required input {name!r}")
            continue
        inputs[name] = v
    return inputs, many


# ----------------------------------------------------------------------------------------------- the guard's window
# A question whose candidate messages the guard picks by code from the conversation is asked here on exactly those
# messages, with the guard's own window function (imported, not copied). Today only K3 cases carry a conversation:
# the guard asks ask_first_yes_v4('K3', reminder_candidates(args['order_id']), items=...) (facts_v4_retail.json; fix
# round 2: v3's ask_first_yes could not fill K3's `verb` input), and with no candidate it is False -> "no", no call.
# K1 (listing, replies), K13 / K16 (user_messages: every user message, newest first, first yes) and K17 (A, B) cases
# give the guard's inputs directly, so they need no window here.
K3_TOOL = {"exchanged": "exchange_delivered_order_items", "modified": "modify_pending_order_items"}


class _WindowCtx:
    """The smallest ctx message_view's helpers read (need_view, args, domain)."""

    def __init__(self, view: Any, args: dict, domain: str):
        self.view, self.args, self.domain, self.state = view, args, domain, None
        self.notes: List[str] = []

    def need_view(self) -> Any:
        return self.view


def window_candidates(qid: str, case: dict) -> Optional[List[str]]:
    """The candidate message texts the guard would ask, oldest first; None when the case has no conversation (asked
    as given). K3: message_view.reminder_candidates on the case's conversation and order_id."""
    conv = case.get("conversation")
    if qid != "K3" or not conv:
        return None
    from state_tracker.v3 import message_view as MV
    hist: List[dict] = [{"role": "system", "content": "policy"}]
    for m in conv:
        role = {"agent": "assistant", "assistant": "assistant", "user": "user"}.get(str(m.get("role")))
        if role is None:
            raise ValueError(f"conversation role {m.get('role')!r} is not user / agent")
        hist.append({"role": role, "content": m.get("text") or m.get("content") or ""})
        if role == "assistant":
            hist[-1]["tool_calls"] = None
    oid = case.get("order_id")
    if not oid:
        raise ValueError("a K3 conversation case needs order_id (the call's order)")
    args = {"order_id": oid}
    view = MV.build_view(hist, pending={"tool": K3_TOOL.get(str(case.get("items_action")), K3_TOOL["modified"]),
                                        "args": args}, domain="retail")
    refs = MV.reminder_candidates(_WindowCtx(view, args, "retail"), oid)       # newest first
    texts = {e.ref: e.text for e in view.entries}
    return [texts[r] for r in reversed(refs)]


def _status(rec: dict) -> str:
    return str(rec.get("status") or "unclear")


def ask_case(hook: Any, qid: str, inputs: Dict[str, Any], many: Optional[str]) -> Dict[str, Any]:
    """Ask one case the way the guard asks: per candidate message (newest first, first yes wins), wording 1, and the
    second wording on an unclear first answer."""
    cands = [inputs] if many is None else [dict(inputs, **{many: m}) for m in reversed(inputs[many])]
    asks: List[dict] = []
    final1: Optional[str] = None
    final: Optional[str] = None
    unresolved = set(OE.UNCLEAR_STATUSES)
    st1s, st2s = [], []
    for inp in cands:
        r1 = hook.ask(qid, inp, fact=None, part="case", wording=1)
        s1 = _status(r1)
        s2 = s1
        if s1 in unresolved:
            r2 = hook.ask(qid, inp, fact=None, part="case", wording=2)
            s2 = _status(r2)
        asks.append({"status1": s1, "status2": s2 if s1 in unresolved else None})
        st1s.append(s1)
        st2s.append(s2)
        if s2 in YES_WORDS and qid != "K17":
            break
        if qid == "K17":
            break
    final1 = _combine(st1s, qid)
    final = _combine(st2s, qid)
    return {"final": final, "first_wording": final1, "asks": asks}


def _combine(statuses: List[str], qid: str) -> str:
    if not statuses:
        return "unclear"
    if qid == "K17" or len(statuses) == 1:
        return statuses[0]
    if "yes" in statuses:
        return "yes"
    if all(s == "no" for s in statuses):
        return "no"
    return "unclear"


def score(results: Sequence[dict]) -> Dict[str, Any]:
    """Per question and side: n, right, wrong, unclear, right with the first wording only, pass (>= 28 of 30)."""
    by: Dict[str, Dict[str, collections.Counter]] = {}
    kinds: Dict[str, collections.Counter] = {}
    for r in results:
        c = by.setdefault(r["qid"], {s: collections.Counter() for s in SIDES})[r["side"]]
        c["n"] += 1
        c["right"] += int(r["right"])
        c["right_first_wording"] += int(r.get("right_first") or False)
        c["unclear"] += int(r.get("final") in OE.UNCLEAR_STATUSES)
        c["not_asked"] += int(r.get("error") is not None)
        if not r["right"]:
            kinds.setdefault(r["qid"], collections.Counter())[f"{r['side']}: {r.get('kind') or '-'}"] += 1
    out: Dict[str, Any] = {}
    for q, sides in sorted(by.items(), key=lambda x: (int(x[0][1:]) if x[0][1:].isdigit() else 99)):
        out[q] = {}
        for s, c in sides.items():
            n, right = c["n"], c["right"]
            ok = n >= PASS_OF and right * PASS_OF >= PASS_RIGHT * n
            base = {k: 0 for k in ("n", "right", "right_first_wording", "unclear", "not_asked")}
            base.update(c)
            out[q][s] = dict(base, pass_=ok, note=None if n >= PASS_OF else f"only {n} cases (< {PASS_OF})")
        out[q]["pass"] = all(out[q][s]["pass_"] for s in SIDES)
        out[q]["wrong_by_kind"] = dict((kinds.get(q) or collections.Counter()).most_common())
    return {"by_question": out, "all_pass": bool(out) and all(v["pass"] for v in out.values())}


# ----------------------------------------------------------------------------------------------- running
class _Expect:
    """fake policy `expect`: answers the label of the case being asked (thread-local)."""

    def __init__(self):
        self.tl = threading.local()

    def __call__(self, qid: str, inputs: Dict[str, Any], norm: Any = None) -> str:
        return str(getattr(self.tl, "expect", "no"))


def make_case_hook(backend: str, policy: str, doc: dict, real: Optional[Dict[str, Any]], store_path: str
                   ) -> Tuple[Any, Any, Optional[_Expect]]:
    QV4 = OE._QV4()
    Q = OE._Q()
    exp = None
    if backend == "fake":
        if policy == "expect":
            exp = _Expect()
            be = QV4.FakeBackendV4(exp, doc=doc)
        else:
            be = QV4.FakeBackendV4(OE.fake_policy(policy), doc=doc)
        store = Q.MemoryStore()
    elif backend == "real":
        if not real:
            raise Q.RealModeRefused("the real backend needs the checked real-mode flags")
        if not real.get("ledger") or not real.get("run_id") or not OE.ledger_locked(real["ledger"]):
            raise Q.RealModeRefused("the real backend needs the dev ledger (lock held, run id)")
        be = QV4.RealBackendV4(real["approved"], real["max_usd"], real["max_calls"], approval_flag=True, doc=doc,
                               log=OE.say)
        OE.install_ledger(be, real["ledger"], real["run_id"])             # before the first call
        store = Q.JsonlStore(store_path, writable=True)
    else:
        raise ValueError(f"unknown backend {backend!r}")
    hook = QV4.QuestionsV4(be, store, doc=doc)
    return hook, be, exp


def run_cases(cases: Dict[str, List[dict]], hook: Any, doc: dict, run_id: str,
              expect_hook: Optional[_Expect] = None) -> List[dict]:
    results: List[dict] = []
    for qid, items in cases.items():
        q = (doc.get("questions") or {}).get(qid)
        for c in items:
            exp = str(c.get("expect") or "").lower()
            side = side_of(c)
            res: Dict[str, Any] = {"qid": qid, "id": c.get("id"), "kind": c.get("kind"), "side": side,
                                   "expect": exp, "domain": c.get("domain"), "error": None}
            try:
                if q is None:
                    raise ValueError(f"{qid} is not in the questions file")
                win = window_candidates(qid, c)
                if win is not None:
                    res["window"] = len(win)
                if win == []:                              # the guard: no candidate -> False, no call
                    res.update(final="no", first="no", asks=[])
                else:
                    cc = c if win is None else dict(c, A=(win[0] if len(win) == 1 else win), B=None)
                    inputs, many = case_inputs(cc, q, doc)
                    hook.where = {"run_id": run_id, "step": "CASES", "domain": c.get("domain"), "task": c.get("id"),
                                  "trial": 0, "arm": "cases", "check": qid}
                    if expect_hook is not None:
                        expect_hook.tl.expect = exp
                    a = ask_case(hook, qid, inputs, many)
                    res.update(final=a["final"], first=a["first_wording"], asks=a["asks"])
            except OE.hard_stops():
                raise
            except Exception as e:  # noqa: BLE001 - a case that cannot be asked counts as wrong
                res.update(final=None, first=None, error=f"{type(e).__name__}: {e}"[:200])
            res["right"] = res.get("final") == exp
            res["right_first"] = res.get("first") == exp
            results.append(res)
    return results


def render(sc: Dict[str, Any], meta: Dict[str, Any]) -> str:
    w = [f"# Tracker v4: made-up cases through the tiny questions ({meta['backend']}"
         + (f", policy {meta['policy']}" if meta.get("policy") else "") + ")", "",
         f"Written by `scoring/v4_cases.py` on {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. Pass mark: at "
         f"least {PASS_RIGHT} of {PASS_OF} right on the yes side and on the hard-no side, per question "
         f"(preregistration_v4.md §14). Cases {meta['cases']}; bad lines {len(meta['problems'])}."
         + (" **Fake answers: a shape check, not a result.**" if meta["backend"] == "fake" else ""), "",
         f"## Overall: **{'PASS' if sc['all_pass'] else 'FAIL'}**", "",
         "| question | yes side right | hard-no side right | unclear (yes / no) | not asked | first wording only (yes / no) "
         "| pass |", "|---|---|---|---|---|---|---|"]
    for q, v in sc["by_question"].items():
        y, n = v["yes"], v["hard_no"]
        w.append(f"| {q} | {y['right']} / {y['n']} | {n['right']} / {n['n']} | {y['unclear']} / {n['unclear']} | "
                 f"{y['not_asked'] + n['not_asked']} | {y['right_first_wording']} / {n['right_first_wording']} | "
                 f"{'PASS' if v['pass'] else '**FAIL**'} |")
    w += ["", "## Wrong cases by kind (patterns, not single cases)", ""]
    for q, v in sc["by_question"].items():
        if v["wrong_by_kind"]:
            w.append(f"- {q}: " + ", ".join(f"{k} {n}" for k, n in v["wrong_by_kind"].items()))
    if meta.get("spend"):
        w += ["", f"Spend: {json.dumps(meta['spend'])}"]
    return "\n".join(w) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -B -m scoring.v4_cases", description=__doc__.split("\n")[0])
    ap.add_argument("--backend", choices=("fake", "real"), default="fake")
    ap.add_argument("--policy", choices=POLICIES, default="expect")
    ap.add_argument("--cases-dir", default=CASES_DIR)
    ap.add_argument("--qids", default=None, help="comma list (default: every case file)")
    ap.add_argument("--questions", default=None, help="the v4 questions file (default: questions_v4's)")
    ap.add_argument("--out-dir", default=OUT_BASE)
    ap.add_argument(OE.MAIN_CHAT_FLAG, dest="main_chat", action="store_true")
    ap.add_argument("--approved", default=None)
    ap.add_argument("--max-usd", default=None)
    ap.add_argument("--max-calls", type=int, default=None)
    a = ap.parse_args(argv)
    Q = OE._Q()
    room: Dict[str, Any] = {}
    try:
        got = OE.check_real_flags(a.backend, main_chat=a.main_chat, approved=a.approved, max_usd=a.max_usd,
                                  max_calls=a.max_calls, info=room)
    except Q.RealModeRefused as e:
        OE.say(f"REFUSED: {e}")
        return 2
    if a.backend == "fake":
        Q.block_network()
    run_id = f"v4cases_{a.backend}_{OE.utc()}"
    real = None if got is None else {"approved": got[0], "max_usd": got[1], "max_calls": got[2],
                                     "ledger": OE.DEV_LEDGER, "run_id": run_id}
    QV4 = OE._QV4()
    doc = QV4.load_questions_v4(a.questions) if a.questions else QV4.load_questions_v4()
    qids = [x for x in (a.qids.split(",") if a.qids else []) if x] or None
    cases, problems = load_cases(a.cases_dir, qids)
    hook, be, exp = make_case_hook(a.backend, a.policy, doc, real, OE.CASES_STORE)
    results = run_cases(cases, hook, doc, run_id, exp)
    sc = score(results)
    meta = {"backend": a.backend, "policy": a.policy if a.backend == "fake" else None, "run_id": run_id,
            "cases": len(results), "problems": problems, "network_events": len(Q.network_events()),
            "spend": ({"usd": be.budget.spent, "calls": be.budget.calls} if a.backend == "real" else None),
            "dev_ledger": ({"at_start": room, "at_end": OE.DevLedger(OE.DEV_LEDGER).read()}
                           if a.backend == "real" else None)}
    os.makedirs(a.out_dir, exist_ok=True)
    stem = os.path.join(a.out_dir, f"cases_check_{a.backend}")
    OE.write_jsonl(stem + "_results.jsonl", results)
    OE.write_json(stem + ".json", {"score": sc, "meta": meta})
    with open(stem + ".md", "w", encoding="utf-8") as f:
        f.write(render(sc, meta))
    OE.say(f"[cases] {'PASS' if sc['all_pass'] else 'FAIL'}: " + ", ".join(
        f"{q} {'PASS' if v['pass'] else 'FAIL'}" for q, v in sc["by_question"].items()) + f"; wrote {OE.rel(stem)}.md")
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.exit(main())
