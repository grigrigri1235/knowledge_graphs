"""Merge the p6 / p7 / p8 expression overlays into the v3 fact files (main chat, 2026-10-23).

Each overlay: {"domain", "by", "exprs": {fact: {part_id: {"expr": str, "if_nonexistent"?: bool}}}}.
Rules: a part gets exactly one expression; the overlay's owner must match the part's source
(p6: database / event / arguments; p7: structure; p8: question); nothing else in the fact files changes.
Writes only with --write; always prints a report. Run from predicate_correctness/.
"""
import hashlib
import json
import sys

OWNER = {"database": "p6", "event": "p6", "arguments": "p6", "structure": "p7", "question": "p8"}
DOMAINS = ("retail", "airline")


def main(write):
    bad, report = [], {}
    for d in DOMAINS:
        path = f"state_tracker/v3/facts_v3_{d}.json"
        doc = json.load(open(path, encoding="utf-8"))
        before = hashlib.sha256(open(path, "rb").read()).hexdigest()
        set_by = {}
        for by in ("p6", "p7", "p8"):
            ov = json.load(open(f"output/eval_v3/{by}_parts/exprs_{d}.json", encoding="utf-8"))
            if ov.get("domain") != d:
                bad.append((d, by, "domain field", ov.get("domain")))
            for fact, parts in ov["exprs"].items():
                if fact not in doc["facts"]:
                    bad.append((d, by, "unknown fact", fact))
                    continue
                for pid, val in parts.items():
                    part = doc["facts"][fact]["parts"].get(pid)
                    if part is None:
                        bad.append((d, by, "unknown part", f"{fact}.{pid}"))
                        continue
                    if OWNER[part["source"]] != by:
                        bad.append((d, by, f"part source {part['source']} belongs to {OWNER[part['source']]}", f"{fact}.{pid}"))
                        continue
                    key = (fact, pid)
                    if key in set_by:
                        bad.append((d, by, f"set twice (also by {set_by[key]})", f"{fact}.{pid}"))
                        continue
                    if part.get("expr") not in (None, val["expr"]):
                        bad.append((d, by, "part already has another expr", f"{fact}.{pid}"))
                        continue
                    set_by[key] = by
                    part["expr"] = val["expr"]
                    if "if_nonexistent" in val:
                        part["if_nonexistent"] = val["if_nonexistent"]
                    extra = set(val) - {"expr", "if_nonexistent"}
                    if extra:
                        bad.append((d, by, "extra overlay fields", f"{fact}.{pid}: {sorted(extra)}"))
        missing = [f"{f}.{p}" for f, e in doc["facts"].items() for p, part in e["parts"].items() if not part.get("expr")]
        by_count = {}
        for v in set_by.values():
            by_count[v] = by_count.get(v, 0) + 1
        txt = json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        report[d] = {"parts": sum(len(e["parts"]) for e in doc["facts"].values()), "set": len(set_by),
                     "by": by_count, "missing": missing, "sha_before": before,
                     "sha_after": hashlib.sha256(txt.encode()).hexdigest()}
        if write and not bad and not missing:
            open(path, "w", encoding="utf-8").write(txt)
            report[d]["written"] = True
    print(json.dumps({"problems": bad, "report": report}, indent=1))
    if bad or any(r["missing"] for r in report.values()):
        sys.exit(1)


main("--write" in sys.argv)
