"""Tracker v4 (scoring.v4_dev_check): the pre-registered dev-check pass marks on the 200 development conversations.

Pass marks (preregistration_v4.md §14, overview.md §10), fixed before any answer is read:
  D1 tiny blocks: the main arm's blocks (tiny answers) <= 1.5 x the judge stand-in's blocks, on the same checks
  D2 unclear: unclear answers (unclear, failed quote, bad output: D10) <= 2 % of the tiny calls (distinct keys used)
  D3 two keys: 0 disagreements (the answers allow while a code part blocks; v3 p12's two_keys on the v4 fact files)
  D4 state errors: 0 (main and stand-in arms)
  D5 block messages: 100 % of the main arm's block messages name a line the agent can fix in one turn
     (scoring/v4_message_check.fixable_line_problems by agent A7, run by v4_offline_eval at each block on the
     message builder's plan; a block without that result fails)
Run validity (not a pass mark): 0 missing answers, 0 guard run errors.

Disagreements are read by pattern only, never as single examples: per question (and direction), per fact, per line
kind of the missing records at blocks, per tool of the changed decisions. No conversation text is printed.

Input: the rows of scoring/v4_offline_eval.py (default: --backend saved, the stored real answers; any backend's rows
can be read with --rows). Output: output/eval_v4/dev_check.md and dev_check.json.

Run from predicate_correctness/:
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m scoring.v4_dev_check \\
        > output/logs/v4_dev_check.log 2>&1
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from scoring import v4_offline_eval as OE                          # noqa: E402

OUT_MD = os.path.join(OE.paths.OUTPUT_DIR, "eval_v4", "dev_check.md")
OUT_JSON = os.path.join(OE.paths.OUTPUT_DIR, "eval_v4", "dev_check.json")
TINY_RATIO_MAX = 1.5
UNCLEAR_MAX = 0.02
UNCLEAR = OE.UNCLEAR_STATUSES
MAIN, STANDIN = OE.MAIN, OE.STANDIN


def base_qid(qid: Any) -> str:
    """K1 for K1, K1b, K1v4, K1v4b (the second wording counts with its question)."""
    q = str(qid or "?")
    if q.endswith("b") and len(q) > 2:
        q = q[:-1]
    if q.endswith("v4"):
        q = q[:-2]
    return q


def _qkey(q: str) -> Tuple[int, str]:
    return (int(q[1:]) if q[1:].isdigit() else 999, q)


# ----------------------------------------------------------------------------------------------- marks
def same_checks(rows: Sequence[dict]) -> List[dict]:
    return [r for r in rows if r.get(MAIN) and r.get(STANDIN)]


def mark_tiny_blocks(rows: Sequence[dict]) -> Dict[str, Any]:
    both = same_checks(rows)
    tiny = sum(1 for r in both if r[MAIN]["d"] == "block")
    sj = sum(1 for r in both if r[STANDIN]["d"] == "block")
    ratio = None if sj == 0 else tiny / sj
    ok = tiny <= TINY_RATIO_MAX * sj
    return {"checks": len(both), "tiny_blocks": tiny, "standin_blocks": sj, "ratio": ratio,
            "v4_tiny_block_flag": sum(1 for r in both if r[MAIN]["d"] == "block"
                                      and (r[MAIN].get("v4") or {}).get("tiny_block")),
            "pass": ok, "note": "no check of both arms" if not both else None}


def used_keys(rows: Sequence[dict]) -> Dict[str, Tuple[str, Optional[str]]]:
    """{key: (qid, status)} of every answer the main arm used (each key once: one call)."""
    out: Dict[str, Tuple[str, Optional[str]]] = {}
    for r in rows:
        m = r.get(MAIN) or {}
        st = m.get("status") or {}
        for a in m.get("asks") or []:
            if a and a[0] and a[0] not in out:
                out[a[0]] = (str(a[1]), st.get(a[0]))
    return out


def mark_unclear(rows: Sequence[dict], missing_keys: Sequence[str] = ()) -> Dict[str, Any]:
    keys = used_keys(rows)
    miss = set(missing_keys)
    status: collections.Counter = collections.Counter()
    by_q: Dict[str, collections.Counter] = {}
    for k, (q, st) in keys.items():
        s = "missing" if k in miss or st is None else str(st)
        status[s] += 1
        by_q.setdefault(base_qid(q), collections.Counter())[s] += 1
    n = len(keys)
    unclear = sum(status[s] for s in UNCLEAR)
    return {"tiny_calls": n, "unclear": unclear, "share": (unclear / n) if n else None,
            "status": dict(sorted(status.items())),
            "by_question": {q: dict(sorted(v.items())) for q, v in sorted(by_q.items(), key=lambda x: _qkey(x[0]))},
            "pass": unclear <= UNCLEAR_MAX * n, "note": "no tiny call" if not n else None}


def mark_two_keys(rows: Sequence[dict], docs: Dict[str, dict]) -> Dict[str, Any]:
    from scoring import v3_p12_offline as P12
    res = P12.two_keys(SimpleNamespace(rows=list(rows)), docs)
    n = res["counts"].get("two-key disagreement: the answers allow, a code part blocks", 0)
    by_fact = collections.Counter(it["fact"] for it in res["items"])
    return {"disagreements": n, "counts": res["counts"], "by_fact": dict(by_fact.most_common()), "pass": n == 0}


def mark_state_errors(rows: Sequence[dict]) -> Dict[str, Any]:
    c: collections.Counter = collections.Counter()
    for r in rows:
        for arm in (MAIN, STANDIN):
            for k in ((r.get(arm) or {}).get("serr") or []):
                c[f"{arm}: {k}"] += 1
    n = sum(c.values())
    return {"state_errors": n, "by_kind": dict(sorted(c.items())), "pass": n == 0}


def mark_messages(rows: Sequence[dict]) -> Dict[str, Any]:
    """D5 from the rows: v4_offline_eval ran A7's fixable_line_problems on the message plan of every main-arm block
    (row v3.fix = {ok, problems}). A block without that result is not checked: it fails."""
    blocks = [r for r in rows if (r.get(MAIN) or {}).get("d") == "block"]
    ok = 0
    unchecked = 0
    fails: collections.Counter = collections.Counter()
    for r in blocks:
        fx = r[MAIN].get("fix")
        if not isinstance(fx, dict):
            unchecked += 1
            fails[f"{r['tool']}: not checked"] += 1
            continue
        if fx.get("ok"):
            ok += 1
            continue
        for p in (fx.get("problems") or ["no fixable line"])[:3]:
            fails[f"{r['tool']}: {str(p).split(':')[0][:80]}"] += 1
    return {"blocks": len(blocks), "named": ok, "share": (ok / len(blocks)) if blocks else None,
            "unchecked": unchecked, "fail_patterns": dict(fails.most_common(30)), "pass": ok == len(blocks)}


def validity(meta: Dict[str, Any]) -> Dict[str, Any]:
    counts = meta.get("counts") or {}
    gerr = sum(v for k, v in counts.items() if k.startswith("errors: "))
    miss = len(meta.get("missing") or [])
    return {"missing_answers": miss, "guard_run_errors": gerr, "network_events": meta.get("network_events"),
            "judge_calls": sum((meta.get("judge_calls") or {}).values()), "valid": miss == 0 and gerr == 0}


# ----------------------------------------------------------------------------------------------- patterns
def _blocking(docs: Dict[str, dict], dom: str, fact: str) -> Optional[bool]:
    e = ((docs.get(dom) or {}).get("facts") or {}).get(fact)
    return None if e is None else e.get("blocking_value")


def patterns(rows: Sequence[dict], docs: Dict[str, dict]) -> Dict[str, Any]:
    """Main arm (tiny answers) vs the stand-in on the same checks, grouped: per question x direction, per fact, per
    tool of the changed decisions, and the missing-line kinds at the main arm's blocks (only-tiny blocks apart)."""
    by_q: Dict[str, collections.Counter] = {}
    by_f: Dict[str, collections.Counter] = {}
    dec: Dict[str, collections.Counter] = {}
    deciding: Dict[str, collections.Counter] = {}
    lines_all: collections.Counter = collections.Counter()
    lines_only: collections.Counter = collections.Counter()
    tot: collections.Counter = collections.Counter()
    for r in same_checks(rows):
        m, s = r[MAIN], r[STANDIN]
        asks = m.get("asks") or []
        asked = sorted({a[2] for a in asks if a and a[2]})
        diff_facts = []
        for f in asked:
            tv = (m.get("f") or {}).get(f, [None])[0]
            sv = (s.get("f") or {}).get(f, [None])[0]
            if not isinstance(tv, bool) or not isinstance(sv, bool):
                tot["asked facts without two values"] += 1
                continue
            tot["asked facts"] += 1
            qids = sorted({base_qid(a[1]) for a in asks if a[2] == f}, key=_qkey) or ["?"]
            if tv is sv:
                tot["agree"] += 1
                for q in qids:
                    by_q.setdefault(q, collections.Counter())["agree"] += 1
                continue
            tot["disagree"] += 1
            diff_facts.append((f, qids))
            bv = _blocking(docs, r["dom"], f)
            direction = "tiny blocks" if bv is not None and tv is bv else (
                "tiny allows" if bv is not None else "direction unknown")
            for q in qids:
                by_q.setdefault(q, collections.Counter())[f"disagree: {direction}"] += 1
            by_f.setdefault(f, collections.Counter())[f"disagree: {direction}"] += 1
        md, sd = m["d"], s["d"]
        if md == "block":
            for recs in ((m.get("v4") or {}).get("missing") or {}).values():
                for x in recs or []:
                    lines_all[str((x or {}).get("line"))] += 1
                    if sd == "allow":
                        lines_only[str((x or {}).get("line"))] += 1
        if md != sd:
            what = "tiny block, stand-in allow" if md == "block" else "tiny allow, stand-in block"
            dec.setdefault(what, collections.Counter())[r["tool"]] += 1
            for f, qids in diff_facts or [("(no asked fact differs)", ["-"])]:
                for q in qids:
                    deciding.setdefault(what, collections.Counter())[q] += 1
    return {"totals": dict(tot),
            "by_question": {q: dict(v) for q, v in sorted(by_q.items(), key=lambda x: _qkey(x[0]))},
            "by_fact": {f: dict(v) for f, v in sorted(by_f.items())},
            "decisions_by_tool": {k: dict(v.most_common()) for k, v in dec.items()},
            "decisions_by_question": {k: dict(v.most_common()) for k, v in deciding.items()},
            "missing_lines_at_blocks": dict(lines_all.most_common()),
            "missing_lines_at_tiny_only_blocks": dict(lines_only.most_common())}


def evaluate(rows: Sequence[dict], meta: Dict[str, Any], docs: Dict[str, dict]) -> Dict[str, Any]:
    missing = [m.get("key") for m in meta.get("missing") or []]
    marks = {"D1": mark_tiny_blocks(rows), "D2": mark_unclear(rows, missing), "D3": mark_two_keys(rows, docs),
             "D4": mark_state_errors(rows), "D5": mark_messages(rows)}
    val = validity(meta)
    return {"marks": marks, "validity": val, "all_pass": all(m["pass"] for m in marks.values()) and val["valid"],
            "patterns": patterns(rows, docs), "backend": meta.get("backend"), "run_id": meta.get("run_id"),
            "rows": len(rows), "conversations": len({r["conv"] for r in rows})}


# ----------------------------------------------------------------------------------------------- report
def _tbl(head: List[str], rows: List[List[Any]]) -> List[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return out


def _pf(x: dict) -> str:
    return "PASS" if x["pass"] else "**FAIL**"


def _pct(x: Optional[float]) -> str:
    return "-" if x is None else f"{100 * x:.1f} %"


def render(res: Dict[str, Any], rows_path: str) -> str:
    m, v, p = res["marks"], res["validity"], res["patterns"]
    w: List[str] = []
    w.append("# Tracker v4: dev check on the 200 development conversations (pass marks, by pattern)")
    w.append("")
    w.append("> **Development check, not a result.** In-sample data (the p12a set). Disagreements are shown by pattern "
             "only, never as single examples.")
    w.append("")
    w.append(f"Written by `scoring/v4_dev_check.py` on {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} from "
             f"`{OE.rel(rows_path)}` (backend {res['backend']}, run `{res['run_id']}`): {res['conversations']} "
             f"conversations, {res['rows']:,} checks.")
    w.append("")
    w.append(f"## Overall: **{'PASS' if res['all_pass'] else 'FAIL'}**")
    w.append("")
    d1, d2, d3, d4, d5 = m["D1"], m["D2"], m["D3"], m["D4"], m["D5"]
    ratio = "-" if d1["ratio"] is None else f"{d1['ratio']:.2f}x"
    d5txt = (f"{d5['named']} of {d5['blocks']} block messages name a fixable line ({_pct(d5.get('share'))}); not "
             f"checked {d5['unchecked']}")
    w += _tbl(["id", "pass mark", "result", "pass"], [
        ["D1", "tiny blocks <= 1.5 x the stand-in's blocks (same checks)",
         f"tiny {d1['tiny_blocks']} vs stand-in {d1['standin_blocks']} on {d1['checks']:,} checks ({ratio})", _pf(d1)],
        ["D2", "unclear answers <= 2 % of tiny calls",
         f"{d2['unclear']} of {d2['tiny_calls']:,} calls ({_pct(d2['share'])}); statuses {json.dumps(d2['status'])}",
         _pf(d2)],
        ["D3", "two-key disagreements: 0", f"{d3['disagreements']}", _pf(d3)],
        ["D4", "state errors: 0", f"{d4['state_errors']} {json.dumps(d4['by_kind']) if d4['by_kind'] else ''}",
         _pf(d4)],
        ["D5", "100 % of block messages name a line the agent can fix in one turn", d5txt, _pf(d5)],
    ])
    w.append("")
    w.append(f"Run validity (not a pass mark): missing answers {v['missing_answers']}, guard run errors "
             f"{v['guard_run_errors']}, judge calls {v['judge_calls']}, network events {v['network_events']}: "
             f"**{'valid' if v['valid'] else 'NOT VALID'}**. D5 uses `scoring/v4_message_check.fixable_line_problems` "
             "(A7) on the message plan of each block, run inside the offline run.")
    w.append("")
    w.append("## Unclear answers by question")
    w.append("")
    sts = sorted({s for x in d2["by_question"].values() for s in x})
    w += _tbl(["question"] + sts, [[q] + [x.get(s, 0) for s in sts] for q, x in d2["by_question"].items()])
    w.append("")
    w.append("## Tiny answers vs the stand-in, per question (asked facts on the same checks)")
    w.append("")
    t = p["totals"]
    w.append(f"Asked facts {t.get('asked facts', 0):,}: agree {t.get('agree', 0):,}, disagree {t.get('disagree', 0):,}.")
    w.append("")
    cols = ["agree", "disagree: tiny blocks", "disagree: tiny allows", "disagree: direction unknown"]
    w += _tbl(["question"] + cols, [[q] + [x.get(c, 0) for c in cols] for q, x in p["by_question"].items()])
    w.append("")
    w.append("## Disagreements per fact")
    w.append("")
    w += _tbl(["fact"] + cols[1:], [[f"`{f}`"] + [x.get(c, 0) for c in cols[1:]] for f, x in p["by_fact"].items()])
    w.append("")
    w.append("## Changed decisions (tiny vs stand-in): by tool and by the question whose answer differed")
    w.append("")
    for what in sorted(set(p["decisions_by_tool"]) | set(p["decisions_by_question"])):
        w.append(f"- **{what}**: by tool " + ", ".join(f"{k} {n}" for k, n in p["decisions_by_tool"].get(what, {}).items())
                 + "; by question " + ", ".join(f"{k} {n}" for k, n in p["decisions_by_question"].get(what, {}).items()))
    w.append("")
    w.append("## Missing lines named at the tiny arm's blocks (per line kind)")
    w.append("")
    kinds = sorted(set(p["missing_lines_at_blocks"]) | set(p["missing_lines_at_tiny_only_blocks"]))
    w += _tbl(["line kind", "at all blocks", "at blocks the stand-in allows"],
              [[k, p["missing_lines_at_blocks"].get(k, 0), p["missing_lines_at_tiny_only_blocks"].get(k, 0)]
               for k in kinds])
    w.append("")
    if d5.get("fail_patterns"):
        w.append("## Block messages without a fixable line (per tool and reason)")
        w.append("")
        w += _tbl(["pattern", "n"], [[k, n] for k, n in d5["fail_patterns"].items()])
        w.append("")
    if d3["by_fact"]:
        w.append("Two-key disagreements per fact: " + ", ".join(f"`{k}` {n}" for k, n in d3["by_fact"].items()))
        w.append("")
    return "\n".join(w) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -B -m scoring.v4_dev_check", description=__doc__.split("\n")[0])
    ap.add_argument("--rows", default=None, help="rows file of v4_offline_eval (default: the saved backend's)")
    ap.add_argument("--out-md", default=OUT_MD)
    ap.add_argument("--out-json", default=OUT_JSON)
    a = ap.parse_args(argv)
    out = OE.outputs("saved")
    rows_path = a.rows or out["rows"]
    meta_path = rows_path.replace("_rows.jsonl", "_meta.json")
    rows = OE.read_jsonl(rows_path)
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    from scoring import v3_labels as L
    if any(L.is_holdout_ckey(r["ck"]) for r in rows):
        raise L.HoldOutData("a hold-out check in the rows: refused")
    docs = OE.load_v4_docs()
    res = evaluate(rows, meta, docs)
    OE.write_json(a.out_json, res)
    with open(a.out_md, "w", encoding="utf-8") as f:
        f.write(render(res, rows_path))
    OE.say(f"[dev check] {'PASS' if res['all_pass'] else 'FAIL'}: " + ", ".join(
        f"{k} {'PASS' if x['pass'] else 'FAIL'}" for k, x in res["marks"].items()) + f"; wrote {OE.rel(a.out_md)}")
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.exit(main())
