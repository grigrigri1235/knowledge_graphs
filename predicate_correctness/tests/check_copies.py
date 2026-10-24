"""Check the copies in predicate_correctness/from_shieldagent/ (Part 1, subtask 10).

Standard library only. Never writes outside from_shieldagent/.

Modes:
  python3 check_copies.py            check every copy listed in from_shieldagent/SHA256SUMS against its checksum,
                                     and list files that are not in SHA256SUMS
  python3 check_copies.py --sources  also check that each source file still has the same checksum (read only)
  python3 check_copies.py --write    compute SHA256SUMS from the source files, check copy == source, and print one
                                     markdown table row per file (for PROVENANCE.md)

Git facts are read without git commands that could write: the blob id of the file is computed here and compared
with `git rev-parse <commit>:<path>`.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FROM_SA = os.path.normpath(os.path.join(HERE, "..", "from_shieldagent"))
SUMS = os.path.join(FROM_SA, "SHA256SUMS")
NOT_COPIES = {"PROVENANCE.md", "SHA256SUMS"}

SA = "/home/azureuser/ShieldAgent"
TB = "/home/azureuser/opt/tau-bench-59a200c"
SA_COMMIT = "1bacdb07037bf0f00dbea8982f5bdcc8ae75c506"
TB_COMMIT = "59a200c6d575d595120f1cb70fea53cef0632f6b"

# copy prefix (inside from_shieldagent/) -> (source prefix, git repo, commit). Longest prefix wins.
SOURCES = {
    "LICENSE": (f"{SA}/LICENSE", SA, SA_COMMIT),
    "code/": (f"{SA}/", SA, SA_COMMIT),
    "policies/": (f"{SA}/policy_docs/", SA, SA_COMMIT),
    "splits/splits.json": (f"{SA}/output/reproduction/labels/splits.json", SA, SA_COMMIT),
    "runs/": (f"{SA}/output/tgr/online/", SA, SA_COMMIT),
    "tau_bench/": (f"{TB}/", TB, TB_COMMIT),
    "gold/": (f"{SA}/agent/predicates/", SA, SA_COMMIT),     # Part 7, subtask 4: gold code, scoring only
    "runner/": (f"{SA}/", SA, SA_COMMIT),                    # Part 10: conversation runner and TGR code
    "scoring/": (f"{SA}/", SA, SA_COMMIT),                   # Part 10, subtask 9: metric and gold scorer scripts (scoring only)
}
RULES_PREFIX = "rules/"          # rules/<domain>/<file> -> tgr_rules/<domain>/frozen/<file>


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob_id(path: str) -> str:
    data = open(path, "rb").read()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def source_of(rel: str):
    if rel.startswith(RULES_PREFIX):
        domain, name = rel[len(RULES_PREFIX):].split("/", 1)
        return f"{SA}/tgr_rules/{domain}/frozen/{name}", SA, SA_COMMIT
    best = max((p for p in SOURCES if rel == p or (p.endswith("/") and rel.startswith(p))), key=len, default=None)
    if best is None:
        return None
    src, repo, commit = SOURCES[best]
    if best.endswith("/"):
        src = src + rel[len(best):]
    return src, repo, commit


def git_state(src: str, repo: str, commit: str) -> str:
    rel = os.path.relpath(src, repo)
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    r = subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "--quiet", f"{commit}:{rel}"],
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        return "not in git"
    return "same as commit" if r.stdout.strip() == git_blob_id(src) else "CHANGED since commit"


def copies() -> list:
    out = []
    for root, dirs, files in os.walk(FROM_SA):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), FROM_SA)
            if rel not in NOT_COPIES:
                out.append(rel)
    return sorted(out)


def read_sums() -> dict:
    sums = {}
    for line in open(SUMS, encoding="utf-8"):
        line = line.rstrip("\n")
        if line:
            digest, rel = line.split("  ", 1)
            sums[rel] = digest
    return sums


def write() -> int:
    bad, rows, lines = 0, [], []
    for rel in copies():
        s = source_of(rel)
        if s is None:
            print(f"NO SOURCE MAPPING: {rel}", file=sys.stderr)
            bad += 1
            continue
        src, repo, commit = s
        d_src, d_copy = sha256(src), sha256(os.path.join(FROM_SA, rel))
        if d_src != d_copy:
            print(f"COPY DIFFERS FROM SOURCE: {rel}", file=sys.stderr)
            bad += 1
        lines.append(f"{d_src}  {rel}")
        size = os.path.getsize(src)
        rows.append(f"| `{rel}` | `{src.replace('/home/azureuser/', '~/')}` | `{commit[:7]}` "
                    f"({git_state(src, repo, commit)}) | {size:,} | `{d_src}` |")
    with open(SUMS, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(rows))
    print(f"files: {len(lines)}, problems: {bad}", file=sys.stderr)
    return 1 if bad else 0


def check(with_sources: bool) -> int:
    sums, bad = read_sums(), 0
    present = set(copies())
    for rel, digest in sums.items():
        path = os.path.join(FROM_SA, rel)
        if not os.path.exists(path):
            print(f"MISSING: {rel}")
            bad += 1
            continue
        if sha256(path) != digest:
            print(f"CHECKSUM MISMATCH (copy): {rel}")
            bad += 1
        if with_sources:
            s = source_of(rel)
            if s is None or not os.path.exists(s[0]):
                print(f"SOURCE NOT FOUND: {rel}")
                bad += 1
            elif sha256(s[0]) != digest:
                print(f"SOURCE CHANGED SINCE COPY: {rel}")
                bad += 1
    for rel in sorted(present - set(sums)):
        print(f"NOT IN SHA256SUMS: {rel}")
        bad += 1
    print(f"checked {len(sums)} copies{' and their sources' if with_sources else ''}: "
          f"{'OK' if not bad else f'{bad} problem(s)'}")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--write" in sys.argv:
        sys.exit(write())
    sys.exit(check("--sources" in sys.argv))
