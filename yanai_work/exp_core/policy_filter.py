"""Generic policy preprocessing: remove Markdown sections by heading, for the RULE-BUILDING input only.

A section is a heading line (`#`… `######`) plus everything up to the next heading of the same or a higher level
(fewer or equal `#`), so its subsections go with it. Headings are compared after case folding and whitespace
normalisation; the heading list comes from the caller (run configuration), never from this module. Every other byte
of the document is kept unchanged. The agent's system prompt and the Direct guard keep reading the original document.

python -m exp_core.policy_filter --policy IN.txt --drop-heading "Some Heading" --out OUT.txt
  → OUT.txt (filtered document) and OUT.txt.filter.json (input/output SHA-256, removed sections verbatim).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from typing import Dict, List, Sequence, Tuple

HEADING = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t#]*$")


def _norm(s: str) -> str:
    return " ".join(s.split()).casefold()


def drop_sections(text: str, headings: Sequence[str]) -> Tuple[str, List[Dict]]:
    """Return (filtered text, removed sections). Each removed section: heading, level, 1-based start/end line, text."""
    wanted = {_norm(h) for h in headings}
    lines = text.splitlines(keepends=True)
    keep, removed, cur = [], [], None          # cur: the section being removed
    for i, line in enumerate(lines, 1):
        m = HEADING.match(line.rstrip("\r\n"))
        if m and cur is not None and len(m.group(1)) <= cur["level"]:
            removed.append(cur)
            cur = None
        if cur is None and m and _norm(m.group(2)) in wanted:
            cur = {"heading": m.group(2), "level": len(m.group(1)), "start_line": i, "lines": []}
        if cur is not None:
            cur["lines"].append(line)
            cur["end_line"] = i
        else:
            keep.append(line)
    if cur is not None:
        removed.append(cur)
    for r in removed:
        r["text"] = "".join(r.pop("lines"))
    return "".join(keep), removed


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--policy", required=True)
    ap.add_argument("--drop-heading", action="append", required=True, help="repeatable; matched case-insensitively")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    text = open(a.policy, encoding="utf-8").read()
    out, removed = drop_sections(text, a.drop_heading)
    unmatched = [h for h in a.drop_heading if _norm(h) not in {_norm(r["heading"]) for r in removed}]
    if unmatched:
        raise SystemExit(f"no section with heading {unmatched} in {a.policy}")
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(out)
    meta = {"input": [a.policy, sha256(text)], "output": [a.out, sha256(out)], "drop_headings": a.drop_heading,
            "removed": removed, "chars": {"input": len(text), "output": len(out),
                                          "removed": sum(len(r["text"]) for r in removed)}}
    with open(a.out + ".filter.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1, ensure_ascii=False)
    print(json.dumps({k: meta[k] for k in ("input", "output", "chars")}, ensure_ascii=False))
    for r in removed:
        print(f"--- removed: {'#' * r['level']} {r['heading']} (lines {r['start_line']}-{r['end_line']})\n{r['text']}")


if __name__ == "__main__":
    main()
