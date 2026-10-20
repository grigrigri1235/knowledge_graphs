"""Prompt templates of the method (method_tgr/prompts/*.md); {field} placeholders, other braces left alone."""
from __future__ import annotations

import hashlib
import os
from functools import lru_cache

PROMPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")


@lru_cache(maxsize=None)
def load(name: str) -> str:
    with open(os.path.join(PROMPT_DIR, f"{name}.md"), encoding="utf-8") as f:
        return f.read().strip()


def fill(text: str, **fields) -> str:
    for k, v in fields.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def render(name: str, **fields):
    """(system, user) of a template with === SYSTEM === / === USER === parts."""
    text = load(name)
    sysmsg, user = text.split("=== USER ===", 1)
    return fill(sysmsg.replace("=== SYSTEM ===", "").strip(), **fields), fill(user.strip(), **fields)


def hashes() -> dict:
    out = {}
    for f in sorted(os.listdir(PROMPT_DIR)):
        if f.endswith(".md"):
            with open(os.path.join(PROMPT_DIR, f), "rb") as fh:
                out[f[:-3]] = hashlib.sha256(fh.read()).hexdigest()[:16]
    return out
