"""Tracker v3, part 1: the sha256 manifest that freezes eval v2's data and the frozen method files.

The manifest output/eval_v3/manifest_eval_v2_data.sha256 is in `sha256sum` format: one line per file,
`<64 hex>  <path relative to predicate_correctness/>`, sorted by path. It lists (docs/planning/tracker_v3/p1.md, step 1):
  eval_v2      every file under output/eval_v2/;
  online_p10   every file under output/online/p10_*/ (episodes.jsonl and run_*.json);
  sa_runs      every file under from_shieldagent/runs/ (the partner's saved runs: train and val only). A file with a
               task of the partner's test group (from_shieldagent/splits/splits.json) is left out and listed as
               excluded by --build (there is none);
  splits       from_shieldagent/splits/splits.json (it defines train / val / test);
  method       the frozen method files (METHOD_FILES) and every file under from_shieldagent/rules/.

check_manifest() recomputes every listed file. It raises ManifestMissing (no manifest file) or ManifestChanged
(a listed file changed or is missing, a new file appeared in a fully listed folder (CLOSED_FOLDERS), or the manifest
file itself differs from MANIFEST_SHA256). Every v3 script calls it at start and stops on an error.

CLI (run from predicate_correctness/, either Python):
  python -B -m state_tracker.v3.frozen --build    write the manifest once (refused if it exists)
  python -B -m state_tracker.v3.frozen --check    check it; prints file counts, bytes per group and seconds
Standard library only. No side effects on import. Never imports gold code.
"""
from __future__ import annotations

import argparse
import collections
import glob
import hashlib
import json
import os
import re
import sys
import time
from typing import Dict, Iterable, List, Optional, Tuple

PC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # predicate_correctness/
MANIFEST_REL = "output/eval_v3/manifest_eval_v2_data.sha256"
MANIFEST_PATH = os.path.join(PC_DIR, *MANIFEST_REL.split("/"))

# sha256 of the manifest file itself, set once after --build (2026-10-22, 807 lines).
MANIFEST_SHA256: Optional[str] = "5c85c90ca5f27938894b0af8c62647eba45ba068fc2d94800c00bd245c902c18"

EVAL_V2_DIR = "output/eval_v2"
P10_GLOB = "output/online/p10_*"
SA_RUNS_DIR = "from_shieldagent/runs"
SA_RULES_DIR = "from_shieldagent/rules"
SPLITS_REL = "from_shieldagent/splits/splits.json"

# The frozen method files (besides from_shieldagent/rules/), relative to predicate_correctness/.
METHOD_FILES = (
    "state_tracker/lookups_airline.json",
    "state_tracker/lookups_retail.json",
    "state_tracker/lookup_format.py",
    "output/predicate_types.json",
    "guard/tgr_tracker.py",
    "guard/run_online.py",
    "guard/soft_stop.py",
    "fork/points_tgr.py",
    "state_tracker/replay.py",
    "state_tracker/state.py",
    "state_tracker/tau_copy.py",
    "from_shieldagent/runner/method_tgr/feedback.py",
    "from_shieldagent/runner/method_tgr/runtime.py",
    "from_shieldagent/runner/repro_runtime/mln.py",
    "from_shieldagent/runner/method_tgr/prompts/judge.md",
    "from_shieldagent/runner/repro_online/episode.py",
)

# Folders whose every file is listed: a file there that the manifest does not list is a change ("added").
CLOSED_FOLDERS = (EVAL_V2_DIR, P10_GLOB, SA_RUNS_DIR, SA_RULES_DIR)

# Saved partner runs: run name -> the split group its tasks must have in splits.json.
SA_RUN_GROUP = {"luna_train_v5": "train", "nano_train": "train", "luna_val": "val"}

_LINE = re.compile(r"^([0-9a-f]{64})  (\S(?:.*\S)?)$")
_CHUNK = 1 << 22


class FrozenError(RuntimeError):
    """Base class: the frozen eval v2 data cannot be confirmed."""


class ManifestMissing(FrozenError):
    """The manifest file does not exist."""


class ManifestChanged(FrozenError):
    """A listed file changed or is missing, a new file appeared in a closed folder, or the manifest itself changed."""

    def __init__(self, message: str, changed: Iterable[str] = (), missing: Iterable[str] = (),
                 added: Iterable[str] = ()):
        super().__init__(message)
        self.changed = sorted(changed)
        self.missing = sorted(missing)
        self.added = sorted(added)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _rel(path: str, root: str) -> str:
    return os.path.relpath(path, root).replace(os.sep, "/")


def _walk_files(folder: str, root: str) -> List[str]:
    """Every file under root/folder (folder may be a glob), as paths relative to root; sorted."""
    out = []
    for base in sorted(glob.glob(os.path.join(root, *folder.split("/")))):
        if os.path.isfile(base):
            out.append(_rel(base, root))
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames.sort()
            for f in filenames:
                out.append(_rel(os.path.join(dirpath, f), root))
    return sorted(out)


def group_of(rel: str) -> str:
    """The manifest group of a listed path (for reports)."""
    if rel.startswith(EVAL_V2_DIR + "/"):
        return "eval_v2"
    if rel.startswith("output/online/p10_"):
        return "online_p10"
    if rel.startswith(SA_RUNS_DIR + "/"):
        return "sa_runs"
    if rel == SPLITS_REL:
        return "splits"
    return "method"


# ------------------------------------------------------------------------------------------------ manifest file
def read_manifest(path: str = MANIFEST_PATH) -> Dict[str, str]:
    """{relpath: sha256} from a manifest file. Raises ManifestMissing, or ManifestChanged on a bad line."""
    if not os.path.isfile(path):
        raise ManifestMissing(f"no manifest file: {path}")
    out: Dict[str, str] = {}
    order: List[str] = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\n")
            m = _LINE.match(line)
            rel = m.group(2) if m else ""
            if not m or rel.startswith("/") or ".." in rel.split("/") or "\\" in rel:
                raise ManifestChanged(f"{path}: line {n} is not '<sha256>  <relative path>': {line[:200]!r}")
            if rel in out:
                raise ManifestChanged(f"{path}: line {n} lists {rel} twice")
            out[rel] = m.group(1)
            order.append(rel)
    if order != sorted(order):
        raise ManifestChanged(f"{path}: lines are not sorted by path")
    if not out:
        raise ManifestChanged(f"{path}: empty manifest")
    return out


def format_manifest(entries: Dict[str, str]) -> str:
    return "".join(f"{entries[rel]}  {rel}\n" for rel in sorted(entries))


def write_manifest(entries: Dict[str, str], path: str = MANIFEST_PATH) -> str:
    """Write the manifest once (refused if the file exists); returns the manifest's own sha256."""
    if os.path.exists(path):
        raise FileExistsError(f"manifest exists, not rewritten: {path}")
    text = format_manifest(entries)
    with open(path, "x", encoding="utf-8") as f:
        f.write(text)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------------------------------------ check
_DEFAULT = object()


def check_manifest(manifest_path: Optional[str] = None, root: Optional[str] = None,
                   expected_sha256=_DEFAULT) -> Dict[str, str]:
    """Recompute every file listed in the manifest; returns {relpath: sha256}.

    Raises ManifestMissing (no manifest) or ManifestChanged (a changed or missing listed file, a file in a closed
    folder that is not listed, or a manifest file whose sha256 is not MANIFEST_SHA256). manifest_path and root
    default to the real manifest and predicate_correctness/; expected_sha256 defaults to MANIFEST_SHA256 for the real
    manifest and to None (not checked) for another one."""
    path = manifest_path or MANIFEST_PATH
    root = root or PC_DIR
    if expected_sha256 is _DEFAULT:
        expected_sha256 = MANIFEST_SHA256 if os.path.abspath(path) == os.path.abspath(MANIFEST_PATH) else None
    entries = read_manifest(path)
    if expected_sha256 is not None:
        got = sha256_file(path)
        if got != expected_sha256:
            raise ManifestChanged(f"the manifest file itself changed: {path} sha256 {got} != pinned {expected_sha256}")
    changed, missing = [], []
    for rel, want in entries.items():
        p = os.path.join(root, *rel.split("/"))
        if not os.path.isfile(p):
            missing.append(rel)
        elif sha256_file(p) != want:
            changed.append(rel)
    added = [rel for folder in CLOSED_FOLDERS for rel in _walk_files(folder, root) if rel not in entries]
    if changed or missing or added:
        parts = []
        for name, items in (("changed", changed), ("missing", missing), ("added (not in the manifest)", added)):
            if items:
                shown = ", ".join(sorted(items)[:50]) + (f", ... ({len(items) - 50} more)" if len(items) > 50 else "")
                parts.append(f"{len(items)} {name}: {shown}")
        raise ManifestChanged(f"eval v2 frozen data changed ({path}): " + "; ".join(parts),
                              changed=changed, missing=missing, added=added)
    return dict(entries)


# ------------------------------------------------------------------------------------------------ build
def load_splits(root: Optional[str] = None) -> Dict[str, Dict[str, str]]:
    """{domain: {task index (str): 'train' | 'val' | 'test'}} from splits.json."""
    with open(os.path.join(root or PC_DIR, *SPLITS_REL.split("/")), encoding="utf-8") as f:
        data = json.load(f)
    return {d: dict(v["split"]) for d, v in data.items()}


def task_groups(rel: str, root: str, splits: Dict[str, Dict[str, str]]) -> collections.Counter:
    """Counter of split groups of the tasks in one saved run file (episodes.jsonl lines or run_*.json "tasks").

    The domain comes from the path (<run>/<domain>/<guard>/<file>) and, for episode lines, must equal the line's env.
    Unknown task ids count as 'unknown'."""
    parts = rel.split("/")
    domain = parts[-3]
    groups: collections.Counter = collections.Counter()
    path = os.path.join(root, *parts)
    if parts[-1].endswith(".jsonl"):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                if rec.get("env") != domain:
                    groups["wrong_env"] += 1
                    continue
                groups[splits.get(domain, {}).get(str(rec.get("task_index")), "unknown")] += 1
    elif parts[-1].endswith(".json"):
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
        for t in rec.get("tasks") or []:
            groups[splits.get(domain, {}).get(str(t), "unknown")] += 1
    return groups


def run_file_ok(rel: str, groups: collections.Counter) -> bool:
    """A saved run file may be used: only tasks of its run's group (train or val), none of the test group."""
    run = rel.split("/")[2] if rel.startswith(SA_RUNS_DIR + "/") else None
    want = SA_RUN_GROUP.get(run) if run else None
    allowed = {want} if want else {"train", "val"}
    return bool(groups) and set(groups) <= allowed


def build_entries(root: Optional[str] = None) -> Tuple[Dict[str, str], List[str], Dict[str, dict]]:
    """(entries {relpath: sha256}, excluded relpaths, task-group report {relpath: counts}) for the manifest."""
    root = root or PC_DIR
    splits = load_splits(root)
    files = _walk_files(EVAL_V2_DIR, root) + _walk_files(P10_GLOB, root) + _walk_files(SA_RULES_DIR, root)
    files += [SPLITS_REL] + list(METHOD_FILES)
    excluded, report = [], {}
    for rel in _walk_files(SA_RUNS_DIR, root):
        groups = task_groups(rel, root, splits)
        report[rel] = dict(groups)
        if run_file_ok(rel, groups):
            files.append(rel)
        else:
            excluded.append(rel)
    for rel in _walk_files(P10_GLOB, root):
        if rel.endswith(".jsonl"):
            report[rel] = dict(task_groups(rel, root, splits))
    missing = [rel for rel in files if not os.path.isfile(os.path.join(root, *rel.split("/")))]
    if missing:
        raise FileNotFoundError(f"files to freeze are missing: {missing}")
    if len(set(files)) != len(files):
        raise ValueError("a file is listed twice")
    entries = {rel: sha256_file(os.path.join(root, *rel.split("/"))) for rel in sorted(files)}
    return entries, excluded, report


def group_stats(entries: Dict[str, str], root: Optional[str] = None) -> Dict[str, Tuple[int, int]]:
    """{group: (files, bytes)}."""
    root = root or PC_DIR
    out: Dict[str, List[int]] = collections.defaultdict(lambda: [0, 0])
    for rel in entries:
        g = out[group_of(rel)]
        g[0] += 1
        g[1] += os.path.getsize(os.path.join(root, *rel.split("/")))
    return {g: (n, b) for g, (n, b) in sorted(out.items())}


def _print_stats(entries: Dict[str, str]) -> None:
    stats = group_stats(entries)
    for g, (n, b) in stats.items():
        print(f"  {g:<11} {n:>5} files {b:>13,} bytes")
    print(f"  {'total':<11} {sum(n for n, _ in stats.values()):>5} files "
          f"{sum(b for _, b in stats.values()):>13,} bytes")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -B -m state_tracker.v3.frozen", description=__doc__.split("\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build", action="store_true", help="write the manifest once (refused if it exists)")
    mode.add_argument("--check", action="store_true", help="recompute every listed file")
    a = ap.parse_args(argv)
    if a.build:
        if os.path.exists(MANIFEST_PATH):
            print(f"REFUSED: the manifest exists: {MANIFEST_PATH}", file=sys.stderr)
            return 2
        t0 = time.time()
        entries, excluded, report = build_entries()
        print("task groups per saved run file (splits.json):")
        for rel, groups in sorted(report.items()):
            print(f"  {rel}: {json.dumps(groups, sort_keys=True)}")
        print(f"excluded (partner's test group or no task): {len(excluded)}")
        for rel in excluded:
            print(f"  EXCLUDED {rel}")
        own = write_manifest(entries)
        print(f"wrote {MANIFEST_PATH}: {len(entries)} lines, own sha256 {own}, {time.time() - t0:.2f} s")
        _print_stats(entries)
        return 0
    t0 = time.time()
    try:
        entries = check_manifest()
    except FrozenError as e:
        print(f"FAIL: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(f"OK: {len(entries)} files equal the manifest ({time.time() - t0:.2f} s); manifest sha256 "
          f"{sha256_file(MANIFEST_PATH)}, pinned {MANIFEST_SHA256}")
    _print_stats(entries)
    return 0


if __name__ == "__main__":
    sys.exit(main())
