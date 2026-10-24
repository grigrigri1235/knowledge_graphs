"""Check the v4 made-up cases against the few-shots of their question (a case equal to a few-shot inflates the pass
mark). $0, no network, reads only questions_v4.json and output/eval_v4/cases/*.jsonl.

For each case: the message texts (agent text + user text, in input order) are compared with each few-shot's
message texts. A message input that holds a list (K1 replies, K13/K16 user_messages) is asked one message at a time
by the guard, so each single list element is also compared as its own view.
Flag: exact (raw message texts equal), near (normalized text equal, or difflib ratio >= 0.9).
The second wording (`<id>b`) has no few-shots of its own in questions_v4.json; it shares the first wording's, which
are checked here. Exit 1 if anything is flagged.

Run from predicate_correctness/:
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 python -B scripts/v4_cases_gen/check_fewshot_overlap.py > LOG 2>&1
"""
import difflib
import glob
import json
import os
import re
import sys

PC = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
QFILE = os.path.join(PC, "state_tracker", "v4", "questions_v4.json")
CASES = os.path.join(PC, "output", "eval_v4", "cases")
NEAR = 0.9


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9$ ]+", " ", s.lower())).strip()


def msg_specs(q):
    return [s for s in q["inputs"] if s.get("type") in ("message", "messages")]


def case_msgs(case, q):
    """List of message values (str or list) in input order, the way scoring.v4_cases fills them."""
    specs = msg_specs(q)
    fill = [x for x in (case.get("A"), case.get("B")) if x is not None]
    if not fill and case.get("user_messages") is not None:
        fill = [case["user_messages"]]
    out, pos = [], 0
    for s in specs:
        if s["name"] in case:
            v = case[s["name"]]
        else:
            v = fill[pos] if pos < len(fill) else None
            pos += 1
        if v is None and len(specs) == 1 and case.get("user_messages") is not None:
            v = case["user_messages"]
        out.append(v)
    return out


def views(vals):
    """Text views: everything joined, plus one view per single element of a list-valued input."""
    def j(v):
        if v is None:
            return ""
        return " || ".join(v) if isinstance(v, list) else v
    vs = [" ## ".join(j(v) for v in vals)]
    for i, v in enumerate(vals):
        if isinstance(v, list) and len(v) > 1:
            for el in v:
                vs.append(" ## ".join(j(el if k == i else w) for k, w in enumerate(vals)))
    return vs


def main():
    doc = json.load(open(QFILE, encoding="utf-8"))
    qs = doc["questions"]
    flagged, total, best = [], 0, {}
    for p in sorted(glob.glob(os.path.join(CASES, "K*.jsonl"))):
        qid = os.path.basename(p).split(".")[0]
        q = qs[qid]
        fss = list(q.get("few_shot") or []) + list((q.get("second") or {}).get("few_shot") or [])
        fs_views = []
        for n, fs in enumerate(fss, 1):
            vals = [fs["inputs"].get(s["name"]) for s in msg_specs(q)]
            fs_views.append((n, fs.get("answer"), views(vals)))
        best[qid] = (0.0, None)
        for ln, line in enumerate(open(p, encoding="utf-8"), 1):
            if not line.strip():
                continue
            total += 1
            c = json.loads(line)
            cv = views(case_msgs(c, q))
            for n, ans, fv in fs_views:
                for a in cv:
                    for b in fv:
                        r = difflib.SequenceMatcher(None, a, b).ratio()
                        if r > best[qid][0]:
                            best[qid] = (r, f"line {ln} vs few-shot {n}")
                        kind = None
                        if a == b:
                            kind = "exact"
                        elif norm(a) == norm(b) or r >= NEAR:
                            kind = "near"
                        if kind:
                            flagged.append((qid, ln, c.get("id"), c.get("expect"), c.get("kind"), n, ans,
                                            kind, round(r, 3), a))
    print(f"cases checked: {total}; few-shots per question: "
          + ", ".join(f"{k}={len(v.get('few_shot') or [])}" for k, v in qs.items()))
    print("highest ratio per set: " + "; ".join(f"{k} {v[0]:.3f} ({v[1]})" for k, v in best.items()))
    seen = set()
    for f in flagged:
        key = f[:3]
        if key in seen:
            continue
        seen.add(key)
        print("FLAG", json.dumps({"set": f[0], "line": f[1], "id": f[2], "expect": f[3], "kind": f[4],
                                  "few_shot": f[5], "few_shot_answer": f[6], "match": f[7], "ratio": f[8],
                                  "text": f[9]}, ensure_ascii=False))
    print(f"flagged cases: {len(seen)}")
    return 1 if seen else 0


if __name__ == "__main__":
    sys.exit(main())
