"""Tracker v4 (scoring.v4_dev_answers): how many tiny-question calls a real dev run on the 200 development
conversations would make, and what they cost. $0: fake answers, no call, no network.

How (code_change_map §1.3, §3 "p8 dry run"): scoring/v4_offline_eval.py runs the v4 guard with the `count` backend:
the stored answers are preloaded (output/eval_v4/questions_answers_v4.jsonl, then v3's store read-only: ChainStore's
read order), so a key whose v4 key equals the v3 key (unchanged questions, system v1) is reused, not called. Every
other key the guard asks is one call. The calls depend on the answers (lazy rules, first yes, re-ask on unclear), so
three fake passes run: yes (every candidate asked), no, unclear (every first wording unclear: the second wordings).
  point estimate   the largest single pass
  upper bound      the union of the three passes' new keys (what any answers could reach)
Price: $0.000046 per call (v3 p12a: 2,726 calls, $0.1253), +25 % for a question with few-shot examples
(questions_v4.json `few_shot`; fallback K1, K3, K4, K13 as overview §6).

Output: output/eval_v4/dev/dev_answers_count.md and .json; the call count and the cost estimate are printed (for the
approval request). Run from predicate_correctness/:
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m scoring.v4_dev_answers \\
        --count-only > output/logs/v4_dev_answers.log 2>&1
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import os
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from scoring import v4_offline_eval as OE                          # noqa: E402

PRICE_PER_CALL = 0.000046
FEW_SHOT_FACTOR = 1.25
FEW_SHOT_FALLBACK = ("K1", "K3", "K4", "K13")
PASSES = ("yes", "no", "unclear")
OUT_MD = os.path.join(OE.OUT_DIR, "dev_answers_count.md")
OUT_JSON = os.path.join(OE.OUT_DIR, "dev_answers_count.json")


def base_qid(q: Any) -> str:
    from scoring.v4_dev_check import base_qid as b
    return b(q)


def few_shot_qids(doc: Optional[dict]) -> Set[str]:
    """Questions with few-shot examples in questions_v4.json; the overview's list when the file is not there."""
    if not doc or not isinstance(doc.get("questions"), dict):
        return set(FEW_SHOT_FALLBACK)
    return {base_qid(q) for q, e in doc["questions"].items() if isinstance(e, dict) and e.get("few_shot")}


def price(calls_by_q: Dict[str, int], few: Set[str], per_call: float = PRICE_PER_CALL) -> Dict[str, Any]:
    by = {q: round(n * per_call * (FEW_SHOT_FACTOR if base_qid(q) in few else 1.0), 6) for q, n in calls_by_q.items()}
    return {"usd": round(sum(by.values()), 6), "by_question": by, "per_call": per_call,
            "few_shot_factor": FEW_SHOT_FACTOR, "few_shot": sorted(few)}


def asked_keys(rows: Iterable[dict]) -> Dict[str, str]:
    """{key: qid} of every ask of the main arm."""
    out: Dict[str, str] = {}
    for r in rows:
        for a in ((r.get(OE.MAIN) or {}).get("asks") or []):
            if a and a[0]:
                out.setdefault(a[0], str(a[1]))
    return out


def count_pass(rows: Sequence[dict], stored: Any) -> Dict[str, Any]:
    """One pass: keys asked, keys reused from the stores, new keys (calls) per question and per conversation."""
    keys = asked_keys(rows)
    new = {k: q for k, q in keys.items() if k not in stored}
    by_q = collections.Counter(base_qid(q) for q in new.values())
    reused = collections.Counter(base_qid(q) for k, q in keys.items() if k in stored)
    per_conv: Dict[str, Set[str]] = collections.defaultdict(set)
    for r in rows:
        for a in ((r.get(OE.MAIN) or {}).get("asks") or []):
            if a and a[0] in new:
                per_conv[r["conv"]].add(a[0])
    convs = {r["conv"] for r in rows}
    sizes = sorted(len(per_conv.get(c, ())) for c in convs)
    return {"asked_keys": len(keys), "reused_keys": len(keys) - len(new), "new_keys": len(new),
            "new_by_question": dict(sorted(by_q.items())), "reused_by_question": dict(sorted(reused.items())),
            "conversations": len(convs), "max_per_conversation": sizes[-1] if sizes else 0,
            "mean_per_conversation": round(sum(sizes) / len(sizes), 2) if sizes else 0.0, "_new": new}


def combine(passes: Dict[str, Dict[str, Any]], few: Set[str]) -> Dict[str, Any]:
    union: Dict[str, str] = {}
    for p in passes.values():
        union.update(p["_new"])
    by_q = collections.Counter(base_qid(q) for q in union.values())
    point_name = max(passes, key=lambda n: passes[n]["new_keys"]) if passes else None
    point = passes[point_name] if point_name else {"new_keys": 0, "new_by_question": {}}
    up_cost = price(dict(by_q), few)
    pt_cost = price(dict(point["new_by_question"]), few)
    # the request: 2x the upper bound (a re-ask round included), rounded up; never above the dev limit
    max_calls = min(int(math.ceil(max(1, 2 * len(union)) / 100.0) * 100), OE.DEV_LIMIT_CALLS)
    return {"point": {"pass": point_name, "calls": point["new_keys"], "cost": pt_cost},
            "upper": {"calls": len(union), "by_question": dict(sorted(by_q.items())), "cost": up_cost},
            "request": {"max_calls": max_calls, "max_usd": OE.DEV_LIMIT_USD,
                        "estimate_usd": up_cost["usd"], "fits_limit": 2 * up_cost["usd"] <= OE.DEV_LIMIT_USD}}


def render(res: Dict[str, Any]) -> str:
    w: List[str] = ["# Tracker v4: tiny-question calls of the real dev run (count only, $0)", "",
                    f"Written by `scoring/v4_dev_answers.py` on {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. "
                    "Fake answers, no call, no network. The 200 development conversations of p12a. Stored answers "
                    "preloaded (v4 store, then v3's read-only): a key equal to a stored key is reused, not called.", ""]
    w += ["| pass | keys asked | reused | **new calls** | max per conversation | mean per conversation |",
          "|---|---|---|---|---|---|"]
    for n, p in res["passes"].items():
        w.append(f"| {n} | {p['asked_keys']:,} | {p['reused_keys']:,} | **{p['new_keys']:,}** | "
                 f"{p['max_per_conversation']} | {p['mean_per_conversation']} |")
    c = res["combined"]
    w += ["", f"- **Point estimate** (largest pass, {c['point']['pass']}): **{c['point']['calls']:,} calls, "
              f"${c['point']['cost']['usd']:.4f}**.",
          f"- **Upper bound** (union of the passes): **{c['upper']['calls']:,} calls, ${c['upper']['cost']['usd']:.4f}** "
          f"(${PRICE_PER_CALL} per call, x{FEW_SHOT_FACTOR} for few-shot questions "
          f"{', '.join(c['upper']['cost']['few_shot'])}).",
          f"- Request: max calls {c['request']['max_calls']:,}, max ${c['request']['max_usd']:.2f} (the dev limit); "
          f"2x the upper bound fits the limit: {c['request']['fits_limit']}.", "",
          "| question | new calls (upper) | cost (upper) | reused keys (yes pass) |", "|---|---|---|---|"]
    reused = (res["passes"].get("yes") or {}).get("reused_by_question") or {}
    for q in sorted(set(c["upper"]["by_question"]) | set(reused), key=lambda x: (int(x[1:]) if x[1:].isdigit() else 99)):
        w.append(f"| {q} | {c['upper']['by_question'].get(q, 0):,} | "
                 f"${c['upper']['cost']['by_question'].get(q, 0.0):.4f} | {reused.get(q, 0):,} |")
    w += ["", f"Stores: {json.dumps(res.get('stores'))}"]
    return "\n".join(w) + "\n"


def run_pass(policy: str, a: argparse.Namespace) -> List[dict]:
    """scoring.v4_offline_eval with the count backend and this policy (its own rows file)."""
    argv = ["--backend", "count", "--policy", policy, "--workers", str(a.workers), "--shards", str(a.shards),
            "--phases", "run", "--no-frozen"]
    if a.limit:
        argv += ["--limit", str(a.limit)]
    if a.out_dir:
        argv += ["--out-dir", a.out_dir]
    rc = OE.main(argv)
    if rc != 0:
        raise SystemExit(f"v4_offline_eval {policy} pass failed ({rc})")
    return OE.read_jsonl(OE.outputs(OE.tag_of("count", policy), a.out_dir)["rows"])


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -B -m scoring.v4_dev_answers", description=__doc__.split("\n")[0])
    ap.add_argument("--count-only", action="store_true", default=True, help="the only mode (no real asking here)")
    ap.add_argument("--passes", default=",".join(PASSES))
    ap.add_argument("--workers", type=int, default=OE.MAX_WORKERS)
    ap.add_argument("--shards", type=int, default=16)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--reuse-rows", action="store_true", help="read the passes' rows files, do not run them again")
    a = ap.parse_args(argv)
    recs, s3, infos = OE.dev_stores((OE.V4_STORE, OE.V3_STORE))       # v3's store: dev keys only, never whole
    stored = OE.StoredKeys(recs, s3)
    del recs
    doc = None
    try:
        doc = OE._QV4().load_questions_v4()
    except Exception as e:  # noqa: BLE001 - the fallback few-shot list is used, and said
        OE.say(f"[count] questions_v4 not loaded ({type(e).__name__}: {e}); few-shot fallback {FEW_SHOT_FALLBACK}")
    few = few_shot_qids(doc)
    passes: Dict[str, Dict[str, Any]] = {}
    for pol in [p for p in a.passes.split(",") if p]:
        rows = (OE.read_jsonl(OE.outputs(OE.tag_of("count", pol), a.out_dir)["rows"]) if a.reuse_rows
                else run_pass(pol, a))
        passes[pol] = count_pass(rows, stored)
        OE.say(f"[count] pass {pol}: {passes[pol]['new_keys']} new calls, {passes[pol]['reused_keys']} reused")
    res = {"passes": passes, "combined": combine(passes, few), "stores": infos}
    out_md = os.path.join(a.out_dir, "dev_answers_count.md") if a.out_dir else OUT_MD
    out_json = out_md.replace(".md", ".json")
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    OE.write_json(out_json, {"passes": {k: {kk: vv for kk, vv in v.items() if kk != "_new"} for k, v in passes.items()},
                             "combined": res["combined"], "stores": infos})
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(render(res))
    c = res["combined"]
    OE.say(f"[count] CALLS: point {c['point']['calls']} (${c['point']['cost']['usd']:.4f}), upper "
           f"{c['upper']['calls']} (${c['upper']['cost']['usd']:.4f}); request max calls {c['request']['max_calls']}, "
           f"max ${c['request']['max_usd']:.2f}; wrote {OE.rel(out_md)}")
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.exit(main())
