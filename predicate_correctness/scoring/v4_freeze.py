"""Tracker v4: the freeze manifest (docs/planning/tracker_v4/overview.md section 10 P3, section 12 rule 4). One script
writes and checks a sha256 manifest of the v4 method files, the pre-registration and the reading guide.
$0, standard library only, no network. Writes only the manifest (default predicate_correctness/output/eval_v4/
v4_freeze.json).

  --write --files <method files ...> [--files-from <list file>] --prereg <file> --guide <file> [--manifest <path>]
      hashes every file and writes the manifest. Refused: a missing file, a folder, a file given twice, no method file,
      a manifest that already exists (unless --replace: the old one is first COPIED to <manifest>.superseded_<UTC>,
      never moved), a manifest path under ~/ShieldAgent, ~/opt or ~/venvs.
      Every file the v4 runner needs (guard/run_online_v4.py freeze_required_files(): all guard input files, the
      runner, guard/soft_stop_v4.py, the merged state_tracker/v4/facts_v4_*.json, questions_v4.json, b3_tasks.json,
      and (audit P9 #4) scoring/v4_b1_summary.py, v4_online_metrics.py, v4_diagnosis.py, v4_online_interim.py and
      scoring/v4_interim.sh) is added as a method file (once; audit P7 #3).
  --check [--manifest <path>]
      hashes every listed file again; exit 1 on any changed or missing file, a runner file that is not listed, or a
      manifest that does not hold together (counts that disagree with its own file list, a duplicate path, a bad
      sha256). Exit 0 if all agree. The runner makes the same "every file listed" check before a real run.
  --no-runner-files: tests with made-up files only (neither adds nor requires the runner's files).
Both print the counts they computed from the files (no hand-typed counts) and the manifest's own sha256.

Paths are stored relative to the repository root (/home/azureuser/code_projects, the parent of predicate_correctness/)
when under it, else absolute. A list file has one path per line; blank lines and lines starting with # are skipped.

Run from predicate_correctness/:
  /home/azureuser/miniconda3/bin/python3 -B -m scoring.v4_freeze --write --files-from output/eval_v4/freeze_list.txt \\
      --prereg ../docs/planning/tracker_v4/preregistration_v4.md \\
      --guide ../docs/planning/tracker_v4/reading_guide_v4.md \\
      > output/logs/v4_freeze_write.txt 2>&1
  /home/azureuser/miniconda3/bin/python3 -B -m scoring.v4_freeze --check > output/logs/v4_freeze_check.txt 2>&1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from typing import Dict, List, Optional, Sequence

sys.dont_write_bytecode = True

PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(PC_DIR)
DEFAULT_MANIFEST = os.path.join(PC_DIR, "output", "eval_v4", "v4_freeze.json")
HOME = os.path.expanduser("~")
FORBIDDEN = tuple(os.path.join(HOME, x) for x in ("ShieldAgent", "opt", "venvs"))
ROLES = ("method", "preregistration", "reading_guide")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
VERSION = "v4_freeze 2"
RUNNER_MODULE = "guard.run_online_v4"           # its freeze_required_files(): what a real run needs in the manifest


class FreezeError(SystemExit):
    """A refused write or a malformed manifest."""


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stored_path(path: str) -> str:
    ap = os.path.abspath(path)
    return os.path.relpath(ap, REPO) if ap.startswith(REPO + os.sep) else ap


def real_path(stored: str) -> str:
    return stored if os.path.isabs(stored) else os.path.join(REPO, stored)


def _forbidden(path: str) -> bool:
    for p in {os.path.abspath(path), os.path.realpath(path)}:
        if any(p == r or p.startswith(r + os.sep) for r in FORBIDDEN):
            return True
    return False


def read_list(path: str) -> List[str]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s and not s.startswith("#"):
                out.append(s)
    return out


def counts_of(entries: Sequence[dict]) -> Dict[str, int]:
    c = {r: sum(1 for e in entries if e["role"] == r) for r in ROLES}
    c["total"] = len(entries)
    c["bytes"] = sum(int(e["bytes"]) for e in entries)
    return c


def build(files: Sequence[str], prereg: str, guide: str) -> dict:
    items = [(p, "method") for p in files] + [(prereg, "preregistration"), (guide, "reading_guide")]
    if not files:
        raise FreezeError("refused: no method file given")
    entries, seen, problems = [], set(), []
    for p, role in items:
        sp = stored_path(p)
        if sp in seen:
            problems.append(f"given twice: {sp}")
            continue
        seen.add(sp)
        rp = real_path(sp)
        if not os.path.exists(rp):
            problems.append(f"missing: {sp}")
            continue
        if not os.path.isfile(rp):
            problems.append(f"not a file: {sp}")
            continue
        entries.append({"path": sp, "role": role, "sha256": sha256_file(rp), "bytes": os.path.getsize(rp)})
    if problems:
        raise FreezeError("refused: " + "; ".join(problems))
    return {"written_by": "predicate_correctness/scoring/v4_freeze.py", "version": VERSION,
            "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "root": REPO,
            "files": entries, "counts": counts_of(entries)}


def write(manifest: str, doc: dict, replace: bool = False) -> Optional[str]:
    if _forbidden(manifest):
        raise FreezeError(f"refused: {manifest} is under ~/ShieldAgent, ~/opt or ~/venvs")
    backup = None
    if os.path.exists(manifest):
        if not replace:
            raise FreezeError(f"refused: {manifest} exists (the freeze is written once; --replace to supersede it)")
        backup = f"{manifest}.superseded_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
        shutil.copy2(manifest, backup)
    os.makedirs(os.path.dirname(os.path.abspath(manifest)), exist_ok=True)
    tmp = f"{manifest}.tmp_{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, manifest)
    return backup


def runner_required_files() -> List[str]:
    """The files the v4 runner needs in the manifest (guard/run_online_v4.py freeze_required_files(): every guard
    input file, the runner, guard/soft_stop_v4.py, the merged facts_v4_*.json, questions_v4.json, b3_tasks.json, the
    B1 summary, metrics, diagnosis, halfway check and watcher scripts), as absolute paths. Imports the runner module lazily (it imports no scoring module and makes no call)."""
    import importlib
    R = importlib.import_module(RUNNER_MODULE)
    return [os.path.join(PC_DIR, *rel.split("/")) for rel in R.freeze_required_files()]


def check(manifest: str, required: Optional[Sequence[str]] = None) -> dict:
    """Every listed file hashed again. ok = no change, nothing missing, the manifest holds together, and (required: a
    list of paths, e.g. runner_required_files()) every required file is listed ("unlisted" otherwise)."""
    if not os.path.exists(manifest):
        return {"ok": False, "problems": [f"manifest missing: {manifest}"], "checked": 0, "same": 0, "changed": [],
                "missing": [], "unlisted": []}
    try:
        with open(manifest, encoding="utf-8") as f:
            doc = json.load(f)
        entries = list(doc["files"])
    except (OSError, ValueError, KeyError, TypeError) as e:
        return {"ok": False, "problems": [f"manifest unreadable: {type(e).__name__}: {e}"], "checked": 0, "same": 0,
                "changed": [], "missing": [], "unlisted": []}
    problems: List[str] = []
    paths = [e.get("path") for e in entries]
    if len(set(paths)) != len(paths):
        problems.append("a path is listed twice")
    for e in entries:
        if e.get("role") not in ROLES or not isinstance(e.get("path"), str) or not SHA_RE.match(str(e.get("sha256"))):
            problems.append(f"bad entry: {e}")
    try:
        if doc.get("counts") != counts_of(entries):
            problems.append(f"counts {doc.get('counts')} disagree with the file list {counts_of(entries)}")
    except (KeyError, TypeError, ValueError):
        problems.append("counts cannot be computed from the file list")
    for r in ("preregistration", "reading_guide"):
        if sum(1 for e in entries if e.get("role") == r) != 1:
            problems.append(f"the manifest must list exactly one {r}")
    if not any(e.get("role") == "method" for e in entries):
        problems.append("the manifest lists no method file")
    same, changed, missing = 0, [], []
    for e in entries:
        rp = real_path(str(e.get("path")))
        if not os.path.isfile(rp):
            missing.append(e.get("path"))
            continue
        got = sha256_file(rp)
        if got == e.get("sha256"):
            same += 1
        else:
            changed.append({"path": e.get("path"), "want": e.get("sha256"), "got": got})
    unlisted: List[str] = []
    if required is not None:
        listed = {os.path.realpath(real_path(str(e.get("path")))) for e in entries}
        unlisted = sorted(stored_path(p) for p in required if os.path.realpath(p) not in listed)
    return {"ok": not (problems or changed or missing or unlisted), "problems": problems, "checked": len(entries),
            "same": same, "changed": changed, "missing": missing, "unlisted": unlisted,
            "required_checked": None if required is None else len(required),
            "counts_computed": counts_of(entries) if not problems else None, "manifest_sha256": sha256_file(manifest)}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--check", action="store_true")
    ap.add_argument("--files", nargs="*", default=[])
    ap.add_argument("--files-from")
    ap.add_argument("--prereg")
    ap.add_argument("--guide")
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST)
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--no-runner-files", action="store_true",
                    help="tests with made-up files only: do not add / require the runner's files (the runner still "
                         "refuses a manifest without them)")
    a = ap.parse_args(argv)
    required = None if a.no_runner_files else runner_required_files()
    if a.write:
        if not a.prereg or not a.guide:
            raise FreezeError("refused: --write needs --prereg and --guide")
        files = list(a.files) + (read_list(a.files_from) if a.files_from else [])
        n_given = len(files)
        if required is not None:                     # every file the runner needs (audit P7 #3), once
            have = {stored_path(p) for p in files} | {stored_path(a.prereg), stored_path(a.guide)}
            files += [p for p in required if stored_path(p) not in have]
        doc = build(files, a.prereg, a.guide)
        backup = write(a.manifest, doc, a.replace)
        c = doc["counts"]
        print(f"[v4-freeze] wrote {a.manifest}: {c['total']} files ({c['method']} method, {c['preregistration']} "
              f"pre-registration, {c['reading_guide']} reading guide), {c['bytes']} bytes; "
              f"{len(files) - n_given} runner files added; manifest sha256 "
              f"{sha256_file(a.manifest)}" + (f"; old manifest copied to {backup}" if backup else ""))
        res = check(a.manifest, required)
        print(f"[v4-freeze] check right after writing: {'OK' if res['ok'] else 'FAILED'}")
        return 0 if res["ok"] else 1
    res = check(a.manifest, required)
    for p in res["problems"]:
        print(f"[v4-freeze] PROBLEM: {p}")
    for x in res["changed"]:
        print(f"[v4-freeze] CHANGED: {x['path']} (frozen {x['want'][:12]}..., now {x['got'][:12]}...)")
    for x in res["missing"]:
        print(f"[v4-freeze] MISSING: {x}")
    for x in res.get("unlisted") or []:
        print(f"[v4-freeze] NOT LISTED (the runner needs it): {x}")
    print(f"[v4-freeze] check {a.manifest}: {res['checked']} files listed, {res['same']} same, "
          f"{len(res['changed'])} changed, {len(res['missing'])} missing, {len(res.get('unlisted') or [])} runner "
          f"files not listed, {len(res['problems'])} manifest problems -> {'OK' if res['ok'] else 'FAILED'}"
          + (f"; manifest sha256 {res['manifest_sha256']}" if res.get("manifest_sha256") else ""))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
