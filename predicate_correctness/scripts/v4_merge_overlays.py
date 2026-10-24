"""Tracker v4: build the v4 fact files and the v4 questions file from the v3 files plus the agents' overlays.

From the v3 session's merge_overlays.py (scripts/v3_session/merge_overlays.py). Plan: docs/planning/tracker_v4/
code_change_map.md section 0.3. Run from predicate_correctness/ with the runner Python (it imports the helper
modules so that facts_format_v3.validate knows every helper name):

    ~/venvs/tau-bench/bin/python -B -m scripts.v4_merge_overlays            # report only (writes nothing but the log)
    ~/venvs/tau-bench/bin/python -B -m scripts.v4_merge_overlays --check    # also: built files equal what is on disk
    ~/venvs/tau-bench/bin/python -B -m scripts.v4_merge_overlays --write    # MAIN CHAT ONLY: write the three files

Inputs (read only):
  state_tracker/v3/facts_v3_<domain>.json, state_tracker/v3/questions_v3.json      (the v3 base, never written)
  output/eval_v4/overlays/facts_<agent>_<domain>.json
      {"domain", "by", "facts": {fact: {"combine"?, "sources"?, <other fact field>?, "parts"?: {pid: part | null}}}}
      a part value replaces the whole part (or adds it); null removes it.
  output/eval_v4/overlays/questions_<agent>.json
      {"by"?, "questions": {qid: entry | null}, "domain_texts"?: {key: {domain: text}}, "top"?: {field: value | null},
       "system_v<n>"?: {system, system_version, ...}, "removed"?: {qid: why (notes; the entry must be null)}}
      an entry replaces the whole v3 question (or adds a new one, e.g. K17); null removes it (e.g. K2).
      "top" sets a top field of the questions file; a system_v<n> block is a top field too, turned into `systems` by
      questions_v4.normalize_doc_v4 before the check (the written file is the normalized one).
Outputs (only with --write): state_tracker/v4/facts_v4_retail.json, facts_v4_airline.json, questions_v4.json.
Always: a JSON report output/logs/v4_merge_overlays_<UTC>.json; one summary line on stdout.

Refused (exit 1, nothing written):
  - one fact field, one part, one question, one domain text or one top field set by two overlays ("owned twice");
  - an overlay whose "by" differs from the agent in its file name, or whose "domain" differs from the file name;
  - an unknown fact (not in the v3 file), a removed part that does not exist, a frozen fact field
    (rules, blocking_value, policy, who: the rules and predicates are frozen);
  - any problem of facts_format_v3.validate on a built fact file, or of the questions validator on the built
    questions file (questions_v4.check_doc_v4 when it exists, else v3's questions.check_doc);
  - a helper module of state_tracker/v4 that fails to import;
  - a fact expression that names a question id ('K<n>') the built questions file does not have.
Facts and questions that no overlay names stay equal to their v3 entries. No LLM call, no network, no gold code.
"""
from __future__ import annotations

import argparse
import copy
import datetime
import glob
import hashlib
import importlib
import json
import os
import re
import sys
import traceback

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

DOMAINS = ("retail", "airline")
V3_FACTS = "state_tracker/v3/facts_v3_{}.json"
V3_QUESTIONS = "state_tracker/v3/questions_v3.json"
V4_DIR = "state_tracker/v4"
V4_FACTS = V4_DIR + "/facts_v4_{}.json"
V4_QUESTIONS = V4_DIR + "/questions_v4.json"
OVERLAY_DIR = "output/eval_v4/overlays"
LOG_DIR = "output/logs"
FROZEN_FACT_FIELDS = ("rules", "blocking_value", "policy", "who")
# v3 modules that register the helper names of the v3 expressions (as guard/tgr_tracker_v3.py imports them).
V3_HELPER_MODULES = ("state_tracker.v3.code_helpers", "state_tracker.v3.message_view",
                     "state_tracker.v3.info_classes", "state_tracker.v3.questions")
FACT_OVERLAY_RE = re.compile(r"^facts_(?P<by>[A-Za-z0-9]+)_(?P<domain>[a-z]+)\.json$")
QUESTION_OVERLAY_RE = re.compile(r"^questions_(?P<by>[A-Za-z0-9]+)\.json$")
QID_IN_EXPR = re.compile(r"['\"](K[1-9][0-9]*)['\"]")      # a question id literal in an expression
V4_ABOUT = ("Tracker v4 (docs/planning/tracker_v4/overview.md): built by scripts/v4_merge_overlays.py from the v3 "
            "file plus the overlays {overlays}. Facts and questions that no overlay names equal their v3 entries. "
            "v3 text follows. | ")


def _p(rel: str, root: str) -> str:
    return os.path.join(root, *rel.split("/"))


def _load(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump(doc) -> str:
    """The file text (the v3 layout: indent 2, sorted keys, UTF-8, final newline)."""
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical(x) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


# ------------------------------------------------------------------------------------------------ overlays
def find_overlays(root: str):
    """(fact overlays [(path, by, domain)], question overlays [(path, by)], bad file names [path])."""
    facts, questions, bad = [], [], []
    for path in sorted(glob.glob(os.path.join(_p(OVERLAY_DIR, root), "*.json"))):
        name = os.path.basename(path)
        m = FACT_OVERLAY_RE.match(name)
        if m and m.group("domain") in DOMAINS:
            facts.append((path, m.group("by"), m.group("domain")))
            continue
        m = QUESTION_OVERLAY_RE.match(name)
        if m:
            questions.append((path, m.group("by")))
            continue
        bad.append(path)
    return facts, questions, bad


def merge_facts(base: dict, overlays, problems: list, rel=lambda p: p):
    """Apply fact overlays [(path, by, domain, doc)] of one domain to a deep copy of base. Returns (doc, owners)
    with owners {"fact.field" | "fact.parts.pid": by}. Problems are appended to `problems`."""
    doc = copy.deepcopy(base)
    owners = {}
    for path, by, domain, ov in overlays:
        where = rel(path)
        if not isinstance(ov, dict) or not isinstance(ov.get("facts"), dict):
            problems.append(f"{where}: not an overlay object with a 'facts' object")
            continue
        if ov.get("domain") != domain:
            problems.append(f"{where}: domain field {ov.get('domain')!r} differs from the file name ({domain})")
        if ov.get("by") != by:
            problems.append(f"{where}: by field {ov.get('by')!r} differs from the file name ({by})")
        extra = set(ov) - {"domain", "by", "facts", "_about"}
        if extra:
            problems.append(f"{where}: unknown top fields {sorted(extra)}")
        for fact, change in ov["facts"].items():
            if fact not in doc["facts"]:
                problems.append(f"{where}: unknown fact {fact!r} (not in the v3 file; the 66 names are frozen)")
                continue
            if not isinstance(change, dict):
                problems.append(f"{where}: {fact}: the change must be an object")
                continue
            entry = doc["facts"][fact]
            for field, value in change.items():
                if field == "parts":
                    continue
                key = f"{fact}.{field}"
                if field in FROZEN_FACT_FIELDS:
                    problems.append(f"{where}: {key}: frozen fact field (rules and predicates do not change)")
                    continue
                if key in owners:
                    problems.append(f"{where}: {key} owned twice (also by {owners[key]})")
                    continue
                owners[key] = by
                if value is None:
                    entry.pop(field, None)
                else:
                    entry[field] = copy.deepcopy(value)
            parts = change.get("parts", {})
            if not isinstance(parts, dict):
                problems.append(f"{where}: {fact}.parts must be an object")
                continue
            for pid, part in parts.items():
                key = f"{fact}.parts.{pid}"
                if key in owners:
                    problems.append(f"{where}: {key} owned twice (also by {owners[key]})")
                    continue
                owners[key] = by
                if part is None:
                    if pid not in entry["parts"]:
                        problems.append(f"{where}: {key}: removed part does not exist")
                        continue
                    del entry["parts"][pid]
                elif not isinstance(part, dict):
                    problems.append(f"{where}: {key}: a part must be an object or null")
                else:
                    entry["parts"][pid] = copy.deepcopy(part)
    return doc, owners


def merge_questions(base: dict, overlays, problems: list, rel=lambda p: p):
    """Apply question overlays [(path, by, doc)] to a deep copy of base. Returns (doc, owners)."""
    doc = copy.deepcopy(base)
    owners = {}
    for path, by, ov in overlays:
        where = rel(path)
        if not isinstance(ov, dict):
            problems.append(f"{where}: not a JSON object")
            continue
        if "by" in ov and ov["by"] != by:
            problems.append(f"{where}: by field {ov.get('by')!r} differs from the file name ({by})")
        blocks = {k: v for k, v in ov.items() if re.match(r"^system_v[0-9]+$", k)}
        extra = set(ov) - {"by", "questions", "domain_texts", "top", "_about", "removed"} - set(blocks)
        if extra:
            problems.append(f"{where}: unknown top fields {sorted(extra)}")
        if "removed" in ov:                      # notes only ({qid: why}); the removal itself is the null entry
            notes = ov["removed"] if isinstance(ov["removed"], dict) else {}
            for qid in notes:
                if (ov.get("questions") or {}).get(qid, "absent") is not None:
                    problems.append(f"{where}: removed.{qid}: the question is not set to null in 'questions'")
        for field, value in blocks.items():      # A4's system_v<n> block: a top field (questions_v4 normalizes it)
            key = f"top.{field}"
            if key in owners:
                problems.append(f"{where}: {key} owned twice (also by {owners[key]})")
                continue
            owners[key] = by
            doc[field] = copy.deepcopy(value)
        for qid, entry in (ov.get("questions") or {}).items():
            key = f"questions.{qid}"
            if key in owners:
                problems.append(f"{where}: {key} owned twice (also by {owners[key]})")
                continue
            owners[key] = by
            if entry is None:
                if qid not in doc["questions"]:
                    problems.append(f"{where}: {key}: removed question does not exist")
                    continue
                del doc["questions"][qid]
            elif not isinstance(entry, dict):
                problems.append(f"{where}: {key}: a question must be an object or null")
            else:
                doc["questions"][qid] = copy.deepcopy(entry)
        for tkey, per_domain in (ov.get("domain_texts") or {}).items():
            if not isinstance(per_domain, dict):
                problems.append(f"{where}: domain_texts.{tkey} must be an object {{domain: text}}")
                continue
            for dom, text in per_domain.items():
                key = f"domain_texts.{tkey}.{dom}"
                if key in owners:
                    problems.append(f"{where}: {key} owned twice (also by {owners[key]})")
                    continue
                owners[key] = by
                slot = doc["domain_texts"].setdefault(tkey, {})
                if text is None:
                    slot.pop(dom, None)
                else:
                    slot[dom] = copy.deepcopy(text)
        for field, value in (ov.get("top") or {}).items():
            key = f"top.{field}"
            if field in ("questions", "domain_texts"):
                problems.append(f"{where}: {key}: set questions and domain_texts with their own fields")
                continue
            if key in owners:
                problems.append(f"{where}: {key} owned twice (also by {owners[key]})")
                continue
            owners[key] = by
            if value is None:
                doc.pop(field, None)
            else:
                doc[field] = copy.deepcopy(value)
    return doc, owners


# ------------------------------------------------------------------------------------------------ validation
def import_helpers(root: str, problems: list):
    """Import the v3 helper modules and every module of state_tracker/v4 (they register the helper names).
    Returns the imported v4 module names."""
    for m in V3_HELPER_MODULES:
        importlib.import_module(m)
    done = []
    for path in sorted(glob.glob(os.path.join(_p(V4_DIR, root), "*.py"))):
        name = os.path.basename(path)[:-3]
        mod = "state_tracker.v4" if name == "__init__" else f"state_tracker.v4.{name}"
        try:
            importlib.import_module(mod)
            done.append(mod)
        except Exception as e:  # noqa: BLE001 (reported, never silent)
            problems.append(f"import {mod} failed: {type(e).__name__}: {e} | "
                            + traceback.format_exc(limit=3).replace("\n", " ")[-600:])
    return done


def question_validator():
    """(name, check function, normalize function) of the questions validator: questions_v4.check_doc_v4 (after
    questions_v4.normalize_doc_v4, which turns system_v<n> blocks into `systems`) when it exists, else v3's."""
    try:
        q4 = importlib.import_module("state_tracker.v4.questions_v4")
        if hasattr(q4, "check_doc_v4"):
            norm = getattr(q4, "normalize_doc_v4", lambda d: d)
            return "state_tracker.v4.questions_v4.check_doc_v4", q4.check_doc_v4, norm
    except Exception:  # noqa: BLE001 (the import problem is reported by import_helpers)
        pass
    from state_tracker.v3 import questions as Q
    return "state_tracker.v3.questions.check_doc", Q.check_doc, lambda d: d


def changed_names(base: dict, built: dict) -> list:
    return sorted(k for k in set(base) | set(built) if canonical(base.get(k)) != canonical(built.get(k)))


# ------------------------------------------------------------------------------------------------ main
def build(root: str = PC_DIR, validate: bool = True):
    """Merge everything. Returns (report, outputs {rel path: text}); report["problems"] empty means fine."""
    problems: list = []
    rel = lambda p: os.path.relpath(p, root).replace(os.sep, "/")  # noqa: E731
    fact_ovs, q_ovs, bad_names = find_overlays(root)
    problems += [f"{rel(p)}: file name is neither facts_<agent>_<domain>.json nor questions_<agent>.json"
                 for p in bad_names]
    loaded_f, loaded_q = [], []
    for path, by, domain in fact_ovs:
        try:
            loaded_f.append((path, by, domain, _load(path)))
        except ValueError as e:
            problems.append(f"{rel(path)}: not JSON: {e}")
    for path, by in q_ovs:
        try:
            loaded_q.append((path, by, _load(path)))
        except ValueError as e:
            problems.append(f"{rel(path)}: not JSON: {e}")
    v4_modules = import_helpers(root, problems) if validate else []
    report = {"root": root, "overlays": [rel(p) for p, *_ in fact_ovs] + [rel(p) for p, _ in q_ovs],
              "v4_modules": v4_modules, "domains": {}, "questions": {}}
    outputs = {}
    if validate:
        from state_tracker.v3 import facts_format_v3 as F
    for d in DOMAINS:
        base_path = _p(V3_FACTS.format(d), root)
        base = _load(base_path)
        mine = [x for x in loaded_f if x[2] == d]
        doc, owners = merge_facts(base, mine, problems, rel)
        doc["_about"] = V4_ABOUT.format(overlays=", ".join(rel(x[0]) for x in mine) or "(none)") + base["_about"]
        vp = F.validate(doc, d) if validate else []
        problems += [f"{d}: validate: {x}" for x in vp]
        text = dump(doc)
        out = V4_FACTS.format(d)
        outputs[out] = text
        by_count = {}
        for v in owners.values():
            by_count[v] = by_count.get(v, 0) + 1
        report["domains"][d] = {"v3_sha256": hashlib.sha256(open(base_path, "rb").read()).hexdigest(),
                                "facts": len(doc["facts"]), "parts": sum(len(e["parts"]) for e in doc["facts"].values()),
                                "changed_facts": changed_names(base["facts"], doc["facts"]),
                                "set_by": by_count, "validate_problems": len(vp), "out": out, "out_sha256": sha(text)}
    qbase = _load(_p(V3_QUESTIONS, root))
    qdoc, qowners = merge_questions(qbase, [(p, b, o) for p, b, o in loaded_q], problems, rel)
    if validate:
        vname, vfunc, vnorm = question_validator()
        qdoc = vnorm(qdoc)                       # the written file is the normalized one (load_questions_v4 keeps it)
        qp = list(vfunc(qdoc))
    else:
        vname, qp = "(not run)", []
    problems += [f"questions: {vname}: {x}" for x in qp]
    qids = set(qdoc["questions"])                # every question id an expression names must exist in the v4 file
    for out, text in outputs.items():
        for fact, e in json.loads(text)["facts"].items():
            for pid, part in e["parts"].items():
                for qid in QID_IN_EXPR.findall(part.get("expr") or ""):
                    if qid not in qids:
                        problems.append(f"{out}: {fact}.{pid} asks {qid}, which is not in the v4 questions file")
    qtext = dump(qdoc)
    outputs[V4_QUESTIONS] = qtext
    report["questions"] = {"v3_sha256": hashlib.sha256(open(_p(V3_QUESTIONS, root), "rb").read()).hexdigest(),
                           "ids": sorted(qdoc["questions"], key=lambda q: (len(q), q)),
                           "changed": changed_names(qbase["questions"], qdoc["questions"]),
                           "changed_top": changed_names({k: v for k, v in qbase.items() if k != "questions"},
                                                        {k: v for k, v in qdoc.items() if k != "questions"}),
                           "validator": vname, "validate_problems": len(qp), "out": V4_QUESTIONS,
                           "out_sha256": sha(qtext)}
    report["problems"] = problems
    return report, outputs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -B -m scripts.v4_merge_overlays", description=__doc__.split("\n")[0])
    ap.add_argument("--write", action="store_true", help="write the v4 files (main chat only; refused on a problem)")
    ap.add_argument("--check", action="store_true", help="exit 1 if a built file differs from the file on disk")
    ap.add_argument("--root", default=PC_DIR, help=argparse.SUPPRESS)   # tests: a planted tree
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    report, outputs = build(root)
    if a.check:
        diff = []
        for out, text in outputs.items():
            p = _p(out, root)
            if not os.path.isfile(p) or open(p, encoding="utf-8").read() != text:
                diff.append(out)
        report["check_differs"] = diff
    written = []
    if a.write and not report["problems"]:
        os.makedirs(_p(V4_DIR, root), exist_ok=True)
        for out, text in outputs.items():
            with open(_p(out, root), "w", encoding="utf-8") as f:
                f.write(text)
            written.append(out)
    report["written"] = written
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_dir = _p(LOG_DIR, root)
    os.makedirs(log_dir, exist_ok=True)
    log = os.path.join(log_dir, f"v4_merge_overlays_{stamp}.json")
    with open(log, "w", encoding="utf-8") as f:
        f.write(json.dumps(report, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    bad = bool(report["problems"]) or bool(report.get("check_differs"))
    print(f"v4_merge_overlays: {len(report['problems'])} problems, {len(report['overlays'])} overlays, "
          f"written {len(written)}, check_differs {len(report.get('check_differs', []))}; report {log}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
