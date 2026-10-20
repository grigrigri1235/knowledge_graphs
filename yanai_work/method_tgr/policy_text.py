"""Sentence numbering of a policy document (the unit of the coverage check)."""
from __future__ import annotations

import re
from typing import List, Tuple

_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"“(])")


def number_sentences(text: str) -> Tuple[str, List[dict]]:
    """Markdown policy -> (text with [S<n>] before every sentence, [{id, text, heading}]). Heading lines are kept
    unnumbered; bullet markers are kept."""
    out, sents, heading = [], [], ""
    for line in text.splitlines():
        s = line.strip()
        if not s:
            out.append("")
            continue
        if s.startswith("#"):
            heading = s.lstrip("#").strip()
            out.append(s)
            continue
        bullet = ""
        m = re.match(r"^([-*]|\d+[.)])\s+", s)
        if m:
            bullet, s = m.group(0), s[m.end():]
        parts = []
        for piece in _SPLIT.split(s):
            piece = piece.strip()
            if not piece:
                continue
            sid = f"S{len(sents) + 1}"
            sents.append({"id": sid, "text": piece, "heading": heading})
            parts.append(f"[{sid}] {piece}")
        out.append(bullet + " ".join(parts))
    return "\n".join(out), sents
