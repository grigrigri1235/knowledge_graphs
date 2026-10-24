"""Runtime prompt templates (provenance marks in docs/reproduction/p2_design.md and p2_log.md)."""
from __future__ import annotations

import hashlib
import os
from functools import lru_cache

PROMPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")


@lru_cache(maxsize=None)
def _load(name: str):
    text = open(os.path.join(PROMPT_DIR, f"{name}.md"), encoding="utf-8").read()
    if "=== SYSTEM ===" in text:
        sysmsg, user = text.split("=== USER ===", 1)
        return sysmsg.replace("=== SYSTEM ===", "").strip(), user.strip()
    return None, text.strip()


def _fill(text, fields):
    for k, v in fields.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def render(name: str, **fields):
    """(system, user) with {field} placeholders filled in both parts; other braces are left alone."""
    sysmsg, user = _load(name)
    return (_fill(sysmsg, fields) if sysmsg else sysmsg), _fill(user, fields)


def prompt_hashes() -> dict:
    return {f[:-3]: hashlib.sha256(open(os.path.join(PROMPT_DIR, f), "rb").read()).hexdigest()[:16]
            for f in sorted(os.listdir(PROMPT_DIR)) if f.endswith(".md")}
