"""Tracker v3, part 4 (scoring.v3_audit): the decision audit on the eval v2 development data. $0: no LLM call, no
network (docs/planning/tracker_v3/p4.md; the blame rule is P4.0 in output/eval_v3/preregistration.md).

Only the development data is read (preregistration.md "Data split"): Stage A (2,000), our and the partner's train
runs, and the Stage B tries whose fork id does not contain "luna_val". The hold-out data sets are never opened.

What it does
1. Every development write check (a database write tool; Stage B: only the checks after the fork) gets one class,
   from the guard's saved decision, τ-bench's expected actions of the task, τ-bench's tool label (p3) and what ran in
   the conversation (CLASSES, decision_class). "block" is the guard's decision (a cap override is a block that ran).
   Matching: canonical JSON of the arguments (sorted keys, integral floats as ints); "near" = same tool and same main
   object id (MAIN_ID_KEYS), other arguments.
2. Facts vs the tool label, at labelled write checks where the tool decides the fact: code bugs (v2 sources: the
   tracker's value; split "never shown" = the v2 lookup's object was missing, vs "shown, value differs") and judge
   fact errors (the judge's own value; frozen and v2 sources).
3. Locate: for each blocked write check, the saved violated rules; per rule, the rule-table row (p2) from the values
   the source guard used (a saved unknown is looked up as its blocking value and counted as "unknown-tipped"); the
   tipping facts with value and source (judge, tracker, judge-unknown, tracker-unknown).
4. Blame by pattern on the too-strict blocks: per fact (rules, data sets, sources) and per rule (distinct tipping
   facts). Suspect fact: 2 or more rules; suspect rule: 2 or more facts. Top facts and rules too.
5. Blame tests (P4.0): one variant per tested item, written to output/eval_v3/p4_variants/ (sha256 in the report);
   the development checks where the item is asked are re-decided with TGR's own code (fork/offline_v3.py `frozen`
   guard, given the full set of values the source guard used; for a rule, a TGR built from the variant rule set).
     code fact   (a fact with a τ-bench tool label): the label's value where the tool decides, else the saved value
     judge flip  (no tool label): the allowing value (the rule table's non-blocking value) wherever it is asked
     rule        the rule set without the rule (a finding only; the frozen rule set stays)
   removed = too-strict blocks that become allows; added = new blocks on an exact expected call the tool accepts,
   plus new allows the tool refuses on a mapped fact. Kept = removed >= 1 and added = 0. All changed checks, and the
   first divergence per conversation only.
   First the base: the `frozen` guard on the unchanged values must reproduce every saved decision, margin and
   violated rule (v2 sources too), and a TGR built from an unchanged copy of each rule set must change nothing.
6. Splits by data set, agent, domain, rule, fact and length bin; Stage B apart from the rest.

Outputs (output/eval_v3/): p4_audit.md, p4_audit.json, p4_wrong.jsonl, p4_variants/; figures
docs/reports/figures/v3_audit_*.png (../docs from predicate_correctness/).

Run from predicate_correctness/ (the hash seed must be fixed: an unknown value can make TGR's decision sample):
    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m scoring.v3_audit \\
        > output/logs/v3_p4_<nn>_audit.log 2>&1
Standard library for the analysis (matplotlib only for the figures; without it, simple SVG files). Never imports a
scoring module other than scoring.v3_*, never the scorer.
"""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
import os
import re
import sys
import time
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

sys.dont_write_bytecode = True

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "scoring"

from state_tracker import paths                                   # noqa: E402
from state_tracker.v3 import tool_check as TC                     # noqa: E402

PC = paths.PC_DIR
OUT_DIR = os.path.join(paths.OUTPUT_DIR, "eval_v3")
REPORT = os.path.join(OUT_DIR, "p4_audit.md")
JSON_OUT = os.path.join(OUT_DIR, "p4_audit.json")
WRONG_OUT = os.path.join(OUT_DIR, "p4_wrong.jsonl")
VARIANTS_DIR = os.path.join(OUT_DIR, "p4_variants")
INDEX = os.path.join(OUT_DIR, "p1_check_index.jsonl")
LABELS = os.path.join(OUT_DIR, "tool_labels.jsonl")
TABLE = os.path.join(OUT_DIR, "rule_table_{}.json")
FIG_DIR = os.path.normpath(os.path.join(PC, "..", "docs", "reports", "figures"))
OWN_FILES = ("scoring/v3_audit.py", "tests/test_v3_audit.py")

DEV_EPISODE_SETS = ("stage_a.luna.tgr_frozen", "stage_a.luna.tgr_tracker", "stage_a.nano.tgr_frozen",
                    "stage_a.nano.tgr_tracker", "ours.p10_luna_train", "ours.p10_nano_train",
                    "partner.luna_train_v5", "partner.nano_train")
STAGE_B = "stage_b"
DEV_DATASETS = DEV_EPISODE_SETS + (STAGE_B,)
HOLDOUT_FORK_MARK = "luna_val"          # a Stage B fork id with it was forked from a val conversation (hold-out)
PARTS = ("main", "stage_b")             # main = Stage A + ours + partner; Stage B apart
BINS = ("<12k", "12-24k", ">24k")
AGENTS = ("luna", "nano")
DOMAINS = ("retail", "airline")
MAIN_ID_KEYS = ("order_id", "reservation_id", "user_id")

CLASSES = ("too_strict", "delayed", "unclear_done_before", "unclear_near_block", "unclear_other_block",
           "block_tool_refuses", "right_allow", "unclear_near_allow", "allowed_unwanted", "allow_tool_refuses")
WRONG_LINE_CLASSES = ("too_strict", "delayed", "unclear_done_before", "unclear_near_block", "unclear_other_block",
                      "unclear_near_allow")
CLASS_TEXT = {
    "too_strict": "**too strict** (the wrong decision): blocked (message sent), the call equals an expected action "
                  "of the task (same tool, same arguments), the tool accepts it, and the same call never runs in the "
                  "conversation (not later, not before)",
    "delayed": "**delayed** (reported): as too strict, but the same call runs later (a later allow, or this check's "
               "own cap override)",
    "unclear_done_before": "unclear: a block on an exact expected call the tool accepts, but the same call already "
                           "ran earlier (a repeat)",
    "unclear_near_block": "unclear: a block on a near call (same tool, same main object id, other arguments) that "
                          "the tool accepts",
    "unclear_other_block": "unclear: a block on a call that is no expected action, that the tool accepts (the "
                           "block may be right: no confirmation, or not wanted)",
    "block_tool_refuses": "a block on a call the tool refuses (the guard agrees with the tool)",
    "right_allow": "an allow of an exact expected call the tool accepts",
    "unclear_near_allow": "unclear: an allow of a near call the tool accepts",
    "allowed_unwanted": "**allowed but unwanted** (reported, never blamed on the guard): an allow of a call that is "
                        "no expected action (not exact, not near) and that the tool accepts",
    "allow_tool_refuses": "an allow of a call the tool refuses (reported; on a mapped fact it is a wrong allow)",
}
CEILING_SETS = (("luna", "stage_a.luna.tgr_frozen"), ("nano", "stage_a.nano.tgr_frozen"))
CEILING_OVERVIEW = {"no_block": (382, 126), "wanted_never_done": (22, 71), "unwanted": (63, 94),
                    "missed": (122, 176)}
FACT_KINDS = ("code_fact", "v2_lookup", "judge_flip")
TOP_N = 10                              # top facts and rules (by too-strict count) tested besides the suspects
EXAMPLES = 3


def say(msg: str) -> None:
    print(msg, flush=True)


# ----------------------------------------------------------------------------------------------- small helpers
def _norm(x: Any) -> Any:
    """Canonical values for matching: dict keys as text, integral floats as ints (1.0 == 1)."""
    if isinstance(x, bool) or x is None:
        return x
    if isinstance(x, float) and x.is_integer():
        return int(x)
    if isinstance(x, dict):
        return {str(k): _norm(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_norm(v) for v in x]
    return x


def canon(x: Any) -> str:
    """Canonical JSON (sorted keys, no spaces, integral floats as ints)."""
    return json.dumps(_norm(x), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(path: str) -> str:
    return os.path.relpath(os.path.abspath(path), PC)


def part_of(dataset: str) -> str:
    return "stage_b" if dataset == STAGE_B else "main"


def short_args(args_canon: str, n: int = 90) -> str:
    return args_canon if len(args_canon) <= n else args_canon[:n - 3] + "..."


def main_id(args: Any) -> Optional[Tuple[str, Any]]:
    """(key, value) of the call's main object id: the first of order_id, reservation_id, user_id it has."""
    if isinstance(args, dict):
        for k in MAIN_ID_KEYS:
            if k in args:
                return k, _norm(args[k])
    return None


def match_expected(tool: str, args: Any, expected: Sequence[Tuple[str, Any]]) -> str:
    """'exact' (an expected action with the same tool and canonical arguments), 'near' (same tool and same main
    object id, other arguments) or 'none'. expected = [(name, kwargs)]."""
    c = canon(args)
    if any(n == tool and canon(kw) == c for n, kw in expected):
        return "exact"
    mid = main_id(args)
    if mid is not None and any(n == tool and main_id(kw) == mid for n, kw in expected):
        return "near"
    return "none"


def executed_calls(executed: Sequence[dict], call_of: Callable[[dict], Tuple[str, Any]]
                   ) -> List[Tuple[int, str, str]]:
    """(position in `executed`, tool, canonical arguments) of every executed tool call."""
    out = []
    for pos, m in enumerate(executed):
        if isinstance(m, dict) and m.get("role") == "assistant" and m.get("tool_calls"):
            tool, args = call_of(m)
            out.append((pos, tool, canon(args)))
    return out


def ran_later(calls: Sequence[Tuple[int, str, str]], tool: str, args_canon: str, prefix: int,
              ran_here: bool) -> bool:
    """The same call runs after the check. prefix = the check's executed_prefix_len. When the check's call ran
    (allow or cap override), executed[prefix] is that call itself, so later runs are at positions > prefix; when it
    was blocked, executed[prefix] is already the next executed step, so >= prefix."""
    start = prefix + 1 if ran_here else prefix
    return any(p >= start and t == tool and a == args_canon for p, t, a in calls)


def ran_before(calls: Sequence[Tuple[int, str, str]], tool: str, args_canon: str, prefix: int) -> bool:
    return any(p < prefix and t == tool and a == args_canon for p, t, a in calls)


def decision_class(decision: str, cap: bool, match: str, accepted: bool, done_later: bool,
                   done_before: bool) -> str:
    """The class of one write check (CLASSES; CLASS_TEXT has the definitions). decision = the guard's decision
    ('allow' / 'block'; a cap override is a block that ran)."""
    if decision == "block":
        if not accepted:
            return "block_tool_refuses"
        if match == "exact":
            if done_before:
                return "unclear_done_before"
            if cap or done_later:
                return "delayed"
            return "too_strict"
        return "unclear_near_block" if match == "near" else "unclear_other_block"
    if not accepted:
        return "allow_tool_refuses"
    if match == "exact":
        return "right_allow"
    return "unclear_near_allow" if match == "near" else "allowed_unwanted"


def refused_on_mapped_fact(label: Optional[dict]) -> bool:
    """The tool refuses the call at a check that decides a mapped fact (some label fact is False)."""
    return bool(label) and not label["accepted"] and any(v is False for v in (label.get("facts") or {}).values())


# ----------------------------------------------------------------------------------------------- rule tables
def load_tables(domains: Iterable[str] = DOMAINS) -> Dict[str, dict]:
    """{domain: {"rules": {id: entry}, "rows": {(id, action, values tuple): row}, "sha256"}} of the p2 tables."""
    out = {}
    for d in domains:
        path = TABLE.format(d)
        with open(path, encoding="utf-8") as f:
            t = json.load(f)
        out[d] = index_table(t)
        out[d]["sha256"] = sha256_file(path)
        out[d]["path"] = rel(path)
    return out


def index_table(t: dict) -> dict:
    rules, rows = {}, {}
    for e in t["rules"]:
        rules[e["id"]] = e
        for r in e["rows"]:
            rows[(e["id"], r["action"], tuple(r["values"][f] for f in e["facts"]))] = r
    return {"rules": rules, "rows": rows}


def blocking_value(entry: dict, fact: str) -> bool:
    vals = entry["blocking_values"].get(fact) or []
    if len(vals) != 1:
        raise ValueError(f"rule {entry['id']}: fact {fact} has blocking values {vals} (one expected)")
    return bool(vals[0])


def allowing_value(tables: Dict[str, dict], fact: str) -> Optional[bool]:
    """The non-blocking value of a fact (the same in every rule that has it; None if no rule has it)."""
    seen = set()
    for t in tables.values():
        for e in t["rules"].values():
            if fact in e["facts"]:
                seen.add(blocking_value(e, fact))
    if not seen:
        return None
    if len(seen) > 1:
        raise ValueError(f"{fact}: different blocking values across rules")
    return not seen.pop()


def locate(table: dict, domain: str, action: str, violated: Sequence[str],
           values: Dict[str, Tuple[Optional[bool], str]]) -> List[dict]:
    """Per violated rule: the rule-table row from the values used (unknown -> blocking value) and its tipping facts.
    values = {fact: (value or None, source 'judge' | 'tracker')}."""
    out = []
    for rid in violated:
        e = table["rules"].get(rid)
        item = {"rule": f"{domain}:{rid}", "row": None, "holds": None, "tipping": [], "not_asked": []}
        if e is None:
            item["problem"] = "rule not in the table"
            out.append(item)
            continue
        vals, unknown = {}, set()
        for f in e["facts"]:
            v = values.get(f)
            if v is None:
                item["not_asked"].append(f)
                vals[f] = blocking_value(e, f)
                unknown.add(f)
            elif v[0] is None:
                vals[f] = blocking_value(e, f)
                unknown.add(f)
            else:
                vals[f] = bool(v[0])
        row = table["rows"].get((rid, action, tuple(vals[f] for f in e["facts"])))
        if row is None:
            item["problem"] = f"no row for action {action}"
            out.append(item)
            continue
        item["row"] = {"values": row["values"], "flip_sets": row["flip_sets"]}
        item["holds"] = row["holds"]
        for f in row["tipping_facts"]:
            src = (values.get(f) or (None, "not asked"))[1]
            item["tipping"].append({"fact": f, "value": vals[f], "unknown": f in unknown,
                                    "source": f"{src}-unknown" if f in unknown else src})
        out.append(item)
    return out


# ----------------------------------------------------------------------------------------------- blame by pattern
def blame_patterns(wrong: Sequence[dict]) -> Dict[str, Any]:
    """Per fact and per rule, over wrong decisions [{ckey, dataset, agent, located: [locate items]}].
    Suspect fact: behind wrong decisions in 2 or more rules. Suspect rule: wrong with 2 or more distinct facts."""
    facts: Dict[str, dict] = {}
    rules: Dict[str, dict] = {}
    for w in wrong:
        fseen = set()
        for it in w["located"]:
            R = rules.setdefault(it["rule"], {"wrong": set(), "facts": collections.Counter(),
                                              "datasets": collections.Counter(), "unknown_tipped": 0})
            if w["ckey"] not in R["wrong"]:
                R["wrong"].add(w["ckey"])
                R["datasets"][w["dataset"]] += 1
            unk = False
            for t in it["tipping"]:
                R["facts"][t["fact"]] += 1
                unk |= t["unknown"]
                F = facts.setdefault(t["fact"], {"wrong": set(), "rules": collections.Counter(),
                                                 "datasets": collections.Counter(), "sources": collections.Counter(),
                                                 "unknown_tipped": 0})
                F["rules"][it["rule"]] += 1
                F["sources"][t["source"]] += 1
                F["unknown_tipped"] += int(t["unknown"])
                if t["fact"] not in fseen:
                    fseen.add(t["fact"])
                    F["wrong"].add(w["ckey"])
                    F["datasets"][w["dataset"]] += 1
            R["unknown_tipped"] += int(unk)
    fact_rows = sorted(({"fact": f, "wrong": len(v["wrong"]), "rules": dict(v["rules"]),
                         "n_rules": len(v["rules"]), "datasets": dict(v["datasets"]), "sources": dict(v["sources"]),
                         "unknown_tipped": v["unknown_tipped"], "suspect": len(v["rules"]) >= 2}
                        for f, v in facts.items()), key=lambda r: (-r["wrong"], r["fact"]))
    rule_rows = sorted(({"rule": r, "wrong": len(v["wrong"]), "facts": dict(v["facts"]), "n_facts": len(v["facts"]),
                         "datasets": dict(v["datasets"]), "unknown_tipped": v["unknown_tipped"],
                         "suspect": len(v["facts"]) >= 2}
                        for r, v in rules.items()), key=lambda r: (-r["wrong"], r["rule"]))
    return {"facts": fact_rows, "rules": rule_rows,
            "suspect_facts": [r["fact"] for r in fact_rows if r["suspect"]],
            "suspect_rules": [r["rule"] for r in rule_rows if r["suspect"]]}


# ----------------------------------------------------------------------------------------------- variants
def fact_variant_value(kind: str, old: Optional[bool], label_value: Optional[bool],
                       allowing: Optional[bool], world_part_only: bool = False) -> Optional[bool]:
    """The variant's value of a fact at one check: code fact -> the tool label where the tool decides, else the saved
    value; judge flip -> the allowing value. A label that holds only the database part of a fact (the two order
    status facts: "looked it up" AND the status) can only make it false: a false label gives False, a true label
    keeps the saved value."""
    if kind == "code_fact":
        if label_value is None:
            return old
        if world_part_only and label_value is True:
            return old
        return label_value
    if kind == "judge_flip":
        return allowing
    raise ValueError(kind)


def alone_fixable(located: List[dict], item: str) -> bool:
    """A too-strict block that this one item can fix alone: a fact that is a whole flip set of every violated rule,
    or a rule that is the only violated rule. item = "fact:<name>" or "rule:<domain>:<id>"."""
    kind, name = item.split(":", 1)
    if kind == "rule":
        return [it["rule"] for it in located] == [name]
    return bool(located) and all([name] in ((it.get("row") or {}).get("flip_sets") or []) for it in located)


def tally_changes(changes: Sequence[Tuple[str, str, str]], rows: Dict[str, dict]) -> collections.Counter:
    """Counts of the changed decisions [(ckey, before, after)] of a variant (P4.0 terms)."""
    c: collections.Counter = collections.Counter()
    for ck, before, after in changes:
        r = rows[ck]
        c["changed"] += 1
        if before == "block" and after == "allow":
            c["block_to_allow"] += 1
            cls = r.get("cls")
            if cls == "too_strict":
                c["removed"] += 1
            elif cls == "delayed":
                c["removed_delayed"] += 1
            if r["write"]:
                lab = r["label"]
                if not lab["accepted"]:
                    c["new_allow_tool_refuses"] += 1
                    if refused_on_mapped_fact(lab):
                        c["added_allow_mapped"] += 1
                elif r["match"] == "none":
                    c["new_allow_not_expected"] += 1
                elif r["match"] == "near":
                    c["new_allow_near"] += 1
                else:
                    c["new_allow_exact"] += 1
            else:
                c["new_allow_not_write"] += 1
        elif before == "allow" and after == "block":
            c["allow_to_block"] += 1
            if r["write"] and r["match"] == "exact" and r["label"]["accepted"]:
                c["added_block"] += 1
            else:
                c["new_block_other"] += 1
    c["added"] = c["added_block"] + c["added_allow_mapped"]
    return c


def first_divergence(changes: Sequence[Tuple[str, str, str]], rows: Dict[str, dict]) -> List[Tuple[str, str, str]]:
    """Only the first changed check of each conversation."""
    best: Dict[str, Tuple[int, Tuple[str, str, str]]] = {}
    for ch in changes:
        r = rows[ch[0]]
        if r["conv"] not in best or r["idx"] < best[r["conv"]][0]:
            best[r["conv"]] = (r["idx"], ch)
    return [v[1] for v in best.values()]


def kept(c: collections.Counter) -> bool:
    """P4.0: the change removes outcome-wrong decisions and adds none."""
    return c["removed"] >= 1 and c["added"] == 0


def rule_set_without(rule_set: dict, rule_id: str) -> dict:
    """A copy of a TGR rule set without one rule (rules, circuits and disposition links)."""
    rs = copy.deepcopy(rule_set)
    if not any(r["id"] == rule_id for r in rs["rules"]):
        raise ValueError(f"no rule {rule_id}")
    rs["rules"] = [r for r in rs["rules"] if r["id"] != rule_id]
    rs["circuits"] = {a: [x for x in ids if x != rule_id] for a, ids in rs["circuits"].items()}
    for d in rs.get("dispositions", []):
        if "rule_ids" in d:
            d["rule_ids"] = [x for x in d["rule_ids"] if x != rule_id]
    return rs


# ----------------------------------------------------------------------------------------------- reading (dev only)
def iter_dev_conversations(datasets: Sequence[str] = DEV_DATASETS) -> Iterator[Any]:
    """The development conversations, in fork/offline_v3.py's order. Stage B: the try files of forks without
    "luna_val" in their id only (the hold-out tries are never opened). Every conversation is asserted to be "dev"."""
    from fork import offline_v3 as O
    for name in datasets:
        if name in ("ours.p10_luna_val", "partner.luna_val"):
            raise ValueError(f"{name} is hold-out data")
        if name == STAGE_B:
            yield from _stage_b_dev(O)
            continue
        for conv in O.iter_conversations([name]):
            if conv.side != O.DEV:
                raise RuntimeError(f"{conv.conv_key} is not development data")
            yield conv


def _stage_b_dev(O) -> Iterator[Any]:
    spec = O.dataset_spec(STAGE_B)
    items = []
    for fid in sorted(os.listdir(O.STAGE_B_DIR)):
        fdir = os.path.join(O.STAGE_B_DIR, fid)
        if not os.path.isdir(fdir) or HOLDOUT_FORK_MARK in fid:
            continue
        for br in sorted(os.listdir(fdir)):
            bdir = os.path.join(fdir, br)
            if br not in O.BRANCH_GUARD or not os.path.isdir(bdir):
                continue
            for name in os.listdir(bdir):
                m = O._TRY_RE.match(name)
                if m:
                    items.append((fid, br, int(m.group(1)), os.path.join(bdir, name)))
    labels = O.splits()
    for ordinal, (fid, br, t, path) in enumerate(sorted(items)):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("error") is not None:
            continue
        if (d.get("fork_id"), d.get("branch"), d.get("try"), d.get("guard")) != (fid, br, t, O.BRANCH_GUARD[br]):
            raise RuntimeError(f"{rel(path)}: fork id / branch / try / guard do not match the path")
        conv = O._conversation(spec, ordinal, path, None, d, d.get("env"), labels)
        if conv.side != O.DEV:
            raise RuntimeError(f"{conv.conv_key} is not development data")
        yield conv


def load_index() -> Dict[str, dict]:
    """ckey -> {bin, history_len} of the development checks (hold-out lines are skipped unread)."""
    out = {}
    with open(INDEX, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d["side"] == "dev":
                out[d["ckey"]] = {"bin": d["bin"], "history_len": d["history_len"]}
    return out


def load_labels() -> Dict[str, dict]:
    out = {}
    with open(LABELS, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            out[d["ckey"]] = {"accepted": d["accepted"], "check": d["check"], "facts": d["facts"],
                              "part": d.get("part")}
    return out


def given_of(saved: dict) -> Dict[str, dict]:
    """The full set of values the source guard used ({name: {value, evidence}}, tracker-set ones included)."""
    return {n: {"value": v.get("value"), "evidence": v.get("evidence", "")} for n, v in (saved.get("judge") or {}).items()}


def _rule_ids(rules: Any) -> List[str]:
    return [str(r.get("rule_id")) for r in (rules or [])]


# ----------------------------------------------------------------------------------------------- pass 1
def collect(log=say) -> Dict[str, Any]:
    """Every development check (compact rows), the conversations, and the base re-decide."""
    from fork import offline_v3 as O
    from fork import rebuild_tasks as RT
    t0 = time.time()
    index, labels = load_index(), load_labels()
    rows: Dict[str, dict] = {}
    convs: Dict[str, dict] = {}
    base = collections.Counter()
    base_misses: List[str] = []
    problems: List[str] = []
    for conv in iter_dev_conversations():
        ep = conv.ep
        tsplit = "train" if conv.split == "tau_train" else "test"
        task = RT.task(conv.domain, tsplit, conv.task_id)
        acts = [(a["name"], a.get("kwargs") or {}) for a in task["actions"]]
        ri = (ep.get("reward_info") or {}).get("actions")
        if isinstance(ri, list) and canon([[a.get("name"), a.get("kwargs")] for a in ri]) != canon(
                [[n, k] for n, k in acts]):
            problems.append(f"{conv.conv_key}: task actions differ from the episode's reward_info actions")
        expected = [(n, k) for n, k in acts if TC.is_write_tool(conv.domain, n)]
        calls = executed_calls(ep["executed"], O.call_of)
        cr = {"conv": conv.conv_key, "dataset": conv.dataset, "part": part_of(conv.dataset), "agent": conv.agent,
              "domain": conv.domain, "split": conv.split, "task_id": conv.task_id, "trial": conv.trial,
              "src": conv.source_guard, "reward": ep.get("reward"),
              "expected": [[n, canon(k)] for n, k in expected],
              "executed_writes": [[p, t, a] for p, t, a in calls if TC.is_write_tool(conv.domain, t)],
              "n_blocked": sum(1 for a in ep["attempts"] if a.get("blocked")),
              "n_cap": sum(1 for a in ep["attempts"] if a.get("cap_override")),
              "checks": []}
        if conv.dataset == STAGE_B:
            cr["n_blocked"] = sum(1 for a in ep["attempts"] if a.get("blocked") and a.get("fork_part") == "after")
            cr["n_cap"] = sum(1 for a in ep["attempts"] if a.get("cap_override") and a.get("fork_part") == "after")
        for ch in conv.checks():
            tool, args = ch.tool, ch.args
            saved = ch.saved
            ac = canon(args)
            write = tool in TC.TOOL_CHECKS and TC.is_write_tool(conv.domain, tool)
            ix = index.get(ch.ckey)
            if ix is None:
                raise RuntimeError(f"{ch.ckey}: not in the check index")
            tr = saved.get("tracker") or {}
            values = {n: [v.get("value"), v.get("source", "judge")] for n, v in (saved.get("judge") or {}).items()}
            if conv.saved_guard == "tgr_tracker":
                jv = tr.get("judge_values")
                judge_own = dict(jv) if isinstance(jv, dict) else None
            else:
                judge_own = {n: v[0] for n, v in values.items()}
            prefix = ch.attempt["executed_prefix_len"]
            r = {"ckey": ch.ckey, "conv": conv.conv_key, "idx": ch.check_idx, "dataset": conv.dataset,
                 "part": cr["part"], "agent": conv.agent, "domain": conv.domain, "src": conv.source_guard,
                 "tool": tool, "args": ac, "write": write, "decision": ch.saved_decision, "blocked": ch.blocked,
                 "cap": ch.cap_override, "judged": ch.judged, "values": values, "judge_own": judge_own,
                 "tracker": {n: [v.get("value"), v.get("missing")] for n, v in (tr.get("tracker_values") or {}).items()},
                 "violated": _rule_ids(saved.get("violated_rules")),
                 "matched": list(saved.get("matched") or []), "circuit": [str(x) for x in saved.get("circuit") or []],
                 "unknown": list(saved.get("unknown_predicates") or []), "bin": ix["bin"],
                 "history_len": ix["history_len"], "prefix": prefix}
            if ch.judged:
                res = O.decide(ch, "frozen", given_of(saved))
                ok = (res["decision"] == ch.saved_decision and res["margin"] == saved.get("margin")
                      and _rule_ids(res["violated_rules"]) == r["violated"])
                base["re-decided"] += 1
                base[f"re-decided {conv.source_guard}"] += 1
                base["equal"] += ok
                base[f"equal {conv.source_guard}"] += ok
                if not ok:
                    base_misses.append(ch.ckey)
                r["base"] = res["decision"]
            else:
                base["not judged (allow, no rule asked)"] += 1
                r["base"] = ch.saved_decision
            if write:
                lab = labels.get(ch.ckey)
                if lab is None:
                    raise RuntimeError(f"{ch.ckey}: write check without a tool label")
                if conv.dataset == STAGE_B and lab.get("part") != "after":
                    raise RuntimeError(f"{ch.ckey}: Stage B check labelled as part {lab.get('part')!r}")
                r["label"] = lab
                if not ch.blocked and not any(p == prefix and t == tool and a == ac for p, t, a in calls):
                    problems.append(f"{ch.ckey}: the call ran but executed[{prefix}] is another call")
                r["match"] = match_expected(tool, args, expected)
                r["done_later"] = ran_later(calls, tool, ac, prefix, ran_here=not ch.blocked)
                r["done_before"] = ran_before(calls, tool, ac, prefix)
                r["cls"] = decision_class(ch.saved_decision, ch.cap_override, r["match"], lab["accepted"],
                                          r["done_later"], r["done_before"])
            else:
                r["label"] = None
            rows[ch.ckey] = r
            cr["checks"].append(ch.ckey)
        convs[conv.conv_key] = cr
    log(f"[audit] pass 1: {len(convs)} conversations, {len(rows)} checks, base {dict(base)}, "
        f"{time.time() - t0:.0f} s")
    return {"rows": rows, "convs": convs, "base": dict(base), "base_misses": base_misses, "problems": problems,
            "seconds": round(time.time() - t0, 1)}


# ----------------------------------------------------------------------------------------------- analysis
def facts_vs_tool(rows: Dict[str, dict]) -> Dict[str, Any]:
    """Code bugs (v2 sources: tracker value vs label) and judge fact errors (judge's own value vs label), at write
    checks where the tool decides the fact (label value not None)."""
    code = collections.defaultdict(collections.Counter)
    judge = collections.defaultdict(collections.Counter)
    used = collections.defaultdict(collections.Counter)
    ex_code: Dict[str, List[dict]] = collections.defaultdict(list)
    ex_judge: Dict[str, List[dict]] = collections.defaultdict(list)
    for r in rows.values():
        if not r["write"]:
            continue
        for f, L in (r["label"].get("facts") or {}).items():
            if L is None:
                continue
            key = (r["part"], f)
            if r["src"] == "v2" and f in r["tracker"]:
                T, missing = r["tracker"][f]
                if T is None:
                    code[key]["tracker unknown"] += 1
                elif T == L:
                    code[key]["agree"] += 1
                else:
                    kind = "never shown" if missing else "shown, value differs"
                    code[key][kind] += 1
                    code[key][f"{kind}: tracker {T}"] += 1
                    if len(ex_code[f"{f}|{kind}"]) < EXAMPLES:
                        ex_code[f"{f}|{kind}"].append({"ckey": r["ckey"], "tool": r["tool"], "tracker": T,
                                                       "label": L, "missing": missing, "args": short_args(r["args"])})
            J = (r["judge_own"] or {}).get(f, "absent") if r["judge_own"] is not None else "absent"
            if J != "absent" and f in r["values"]:
                if J is None:
                    judge[key]["judge unknown"] += 1
                elif J == L:
                    judge[key]["agree"] += 1
                else:
                    judge[key]["differs"] += 1
                    judge[key][f"judge {J}, tool {L}"] += 1
                    if len(ex_judge[f]) < EXAMPLES:
                        ex_judge[f].append({"ckey": r["ckey"], "tool": r["tool"], "judge": J, "label": L,
                                            "src": r["src"], "args": short_args(r["args"])})
            if f in r["values"]:
                V, s = r["values"][f]
                used[key]["unknown" if V is None else ("agree" if V == L else f"differs ({s})")] += 1
    def flat(d):
        return {f"{p}|{f}": dict(c) for (p, f), c in sorted(d.items())}
    return {"code": flat(code), "judge": flat(judge), "used": flat(used), "examples_code": dict(ex_code),
            "examples_judge": dict(ex_judge)}


def ceiling(convs: Dict[str, dict], rows: Dict[str, dict]) -> Dict[str, Any]:
    """The overview's ceiling table (eval v2 Stage A, frozen TGR), recomputed with several unit choices."""
    out = {}
    for agent, ds in CEILING_SETS:
        cs = [c for c in convs.values() if c["dataset"] == ds]
        c = collections.Counter()
        c["conversations"] = len(cs)
        for cv in cs:
            c["no block (no blocked attempt)"] += cv["n_blocked"] == 0
            c["no block and no cap override"] += cv["n_blocked"] == 0 and cv["n_cap"] == 0
            exp = {(n, k) for n, k in cv["expected"]}
            ran = {(t, a) for _, t, a in cv["executed_writes"]}
            ran_pos = cv["executed_writes"]
            c["missed: an expected write never ran (exact)"] += any(e not in ran for e in exp)
            c["missed: reward < 1"] += (cv["reward"] or 0) < 1
            unwanted = [(t, a) for t, a in ran if (t, a) not in exp]
            c["unwanted: a write ran that is not exact expected"] += bool(unwanted)
            unw_far = [x for x in unwanted
                       if match_expected(x[0], json.loads(x[1]), [(n, json.loads(k)) for n, k in exp]) == "none"]
            c["unwanted: ... and not near"] += bool(unw_far)
            first_block: Dict[Tuple[str, str], int] = {}
            first_block_acc: Dict[Tuple[str, str], int] = {}
            for ck in cv["checks"]:
                r = rows[ck]
                if not r["write"] or r["decision"] != "block" or r["match"] != "exact":
                    continue
                key = (r["tool"], r["args"])
                prefix = r["prefix"]
                first_block.setdefault(key, prefix)
                if r["label"]["accepted"]:
                    first_block_acc.setdefault(key, prefix)
                c["checks: blocks on an exact expected call"] += 1
                c["checks: ... never run later"] += not r["done_later"] and not r["cap"]
            for key, p in first_block.items():
                c["wanted actions blocked (distinct calls)"] += 1
                later = any(pos >= p and (t, a) == key for pos, t, a in ran_pos)
                c["... run after the first block"] += later
                c["wanted actions blocked and never run after the first block"] += not later
            for key, p in first_block_acc.items():
                later = any(pos >= p and (t, a) == key for pos, t, a in ran_pos)
                c["... same, tool accepts"] += not later
            c["too-strict checks (this audit)"] += sum(1 for ck in cv["checks"] if rows[ck].get("cls") == "too_strict")
            c["conversations with a too-strict block (this audit)"] += any(
                rows[ck].get("cls") == "too_strict" for ck in cv["checks"])
            c["allowed_unwanted checks (this audit)"] += sum(1 for ck in cv["checks"]
                                                             if rows[ck].get("cls") == "allowed_unwanted")
            c["conversations with an allowed-but-unwanted write (this audit)"] += any(
                rows[ck].get("cls") == "allowed_unwanted" for ck in cv["checks"])
        out[agent] = dict(c)
    return out


def predicate_sources() -> Dict[str, List[str]]:
    """{fact: the rule set's evidence sources} (call_arguments, tool_outputs, agent_messages, user_messages)."""
    out: Dict[str, List[str]] = {}
    for d in DOMAINS:
        with open(os.path.join(paths.RULES_DIR, d, "rule_set.json"), encoding="utf-8") as f:
            for n, p in json.load(f)["predicates"].items():
                out[n] = sorted(p.get("source") or [])
    return out


def fix_kind(located: List[dict], sources: Dict[str, List[str]]) -> str:
    """'agent step' when every violated rule has a flip set whose facts all read the agent's own messages (the agent
    can make the rule hold by a step: list, remind, ask), else 'data or user'."""
    for it in located:
        sets = (it.get("row") or {}).get("flip_sets") or []
        if not any(all("agent_messages" in sources.get(f, []) for f in s) for s in sets):
            return "data or user"
    return "agent step"


def analyse(data: Dict[str, Any], tables: Dict[str, dict],
            sources: Optional[Dict[str, List[str]]] = None) -> Dict[str, Any]:
    rows, convs = data["rows"], data["convs"]
    sources = sources if sources is not None else {}
    writes = [r for r in rows.values() if r["write"]]
    # class counts and splits
    split_keys = ("part", "dataset", "agent", "domain", "bin", "src")
    by: Dict[str, Dict[str, collections.Counter]] = {k: collections.defaultdict(collections.Counter) for k in split_keys}
    by_part_bin_agent: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for r in writes:
        for k in split_keys:
            g = r[k] if k in ("part", "dataset") else f"{r['part']}|{r[k]}"      # Stage B apart from the rest
            by[k][g][r["cls"]] += 1
            by[k][g]["write checks"] += 1
            if r["cls"] == "delayed" and r["cap"]:
                by[k][g]["delayed: by the cap override"] += 1
            if r["cls"] == "allow_tool_refuses" and refused_on_mapped_fact(r["label"]):
                by[k][g]["allow_tool_refuses: on a mapped fact"] += 1
        kk = f"{r['part']}|{r['agent']}|{r['bin']}"
        by_part_bin_agent[kk][r["cls"]] += 1
        by_part_bin_agent[kk]["write checks"] += 1
    nonwrite = collections.Counter()
    for r in rows.values():
        if not r["write"]:
            kind = "respond" if r["tool"] == "respond" else ("transfer" if r["tool"] == "transfer_to_human_agents"
                                                             else "read or other")
            nonwrite[f"{r['part']}|{kind}|checks"] += 1
            nonwrite[f"{r['part']}|{kind}|blocks"] += r["decision"] == "block"
    # locate every blocked write check
    located: Dict[str, List[dict]] = {}
    loc_problems = collections.Counter()
    for r in writes:
        if r["decision"] != "block":
            continue
        action = r["matched"][0] if len(r["matched"]) == 1 else r["tool"]
        vals = {f: (v[0], v[1]) for f, v in r["values"].items()}
        items = locate(tables[r["domain"]], r["domain"], action, r["violated"], vals)
        for it in items:
            if it.get("problem"):
                loc_problems[it["problem"]] += 1
            elif it["holds"]:
                loc_problems["row holds (the saved values satisfy a violated rule)"] += 1
            if it["not_asked"]:
                loc_problems["a fact of a violated rule was not asked"] += 1
        if not r["violated"]:
            loc_problems["block without a violated rule"] += 1
        located[r["ckey"]] = items
    # blame patterns on the too-strict blocks
    def wrong_list(part=None):
        return [{"ckey": r["ckey"], "dataset": r["dataset"], "agent": r["agent"], "located": located[r["ckey"]]}
                for r in writes if r["cls"] == "too_strict" and (part is None or r["part"] == part)]
    blame = {"all": blame_patterns(wrong_list()), "main": blame_patterns(wrong_list("main")),
             "stage_b": blame_patterns(wrong_list("stage_b"))}
    # per-fact and per-rule detail with the tool label and splits
    detail_f: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    detail_r: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    ex_f: Dict[str, List[dict]] = collections.defaultdict(list)
    ex_r: Dict[str, List[dict]] = collections.defaultdict(list)
    unknown_tipped = collections.Counter()
    ex_by: Dict[str, List[dict]] = collections.defaultdict(list)
    distinct = collections.Counter()
    fixable = collections.Counter()
    seen_calls = set()
    for r in writes:
        if r["cls"] != "too_strict":
            continue
        for k in ("dataset", "agent", "bin", "domain"):
            if len(ex_by[f"{k}={r[k]}"]) < (EXAMPLES if k == "dataset" else 1):
                ex_by[f"{k}={r[k]}"].append(_example(r, located[r["ckey"]]))
        if (r["conv"], r["tool"], r["args"]) not in seen_calls:
            seen_calls.add((r["conv"], r["tool"], r["args"]))
            distinct[f"{r['part']}|{r['agent']}"] += 1
        fixable[f"{r['part']}|{fix_kind(located[r['ckey']], sources)}"] += 1
        any_unk = False
        fseen = set()
        for it in located[r["ckey"]]:
            rr = detail_r[it["rule"]]
            for k in ("part", "agent", "bin", "dataset", "src"):
                rr[f"{k}={r[k]}"] += 1
            if len(ex_r[it["rule"]]) < EXAMPLES:
                ex_r[it["rule"]].append(_example(r, located[r["ckey"]]))
            for t in it["tipping"]:
                any_unk |= t["unknown"]
                if t["fact"] in fseen:
                    continue
                fseen.add(t["fact"])
                ff = detail_f[t["fact"]]
                for k in ("part", "agent", "bin", "dataset", "src"):
                    ff[f"{k}={r[k]}"] += 1
                ff[f"source={t['source']}"] += 1
                L = (r["label"].get("facts") or {}).get(t["fact"], "no label")
                ff["tool label: " + ("no label" if L == "no label" else ("not decided" if L is None else
                                                                         ("agrees" if L == t["value"] else
                                                                          "says otherwise")))] += 1
                if len(ex_f[t["fact"]]) < EXAMPLES:
                    ex_f[t["fact"]].append(_example(r, located[r["ckey"]]))
        unknown_tipped[r["part"]] += any_unk
    # conversations and tasks
    conv_counts = collections.defaultdict(collections.Counter)
    for cv in convs.values():
        cc = [rows[ck] for ck in cv["checks"]]
        g = f"{cv['part']}|{cv['agent']}"
        conv_counts[g]["conversations"] += 1
        conv_counts[g]["with a too-strict block"] += any(r.get("cls") == "too_strict" for r in cc)
        conv_counts[g]["with an allowed-but-unwanted write"] += any(r.get("cls") == "allowed_unwanted" for r in cc)
        ts = any(r.get("cls") == "too_strict" for r in cc)
        conv_counts[g]["reward 1"] += (cv["reward"] or 0) >= 1
        conv_counts[g]["reward 1, with a too-strict block"] += ts and (cv["reward"] or 0) >= 1
    return {"by": {k: {g: dict(c) for g, c in sorted(v.items())} for k, v in by.items()},
            "by_part_agent_bin": {k: dict(v) for k, v in sorted(by_part_bin_agent.items())},
            "nonwrite": dict(nonwrite), "located": located, "locate_problems": dict(loc_problems),
            "blame": blame, "fact_detail": {k: dict(v) for k, v in detail_f.items()},
            "rule_detail": {k: dict(v) for k, v in detail_r.items()},
            "fact_examples": dict(ex_f), "rule_examples": dict(ex_r), "unknown_tipped": dict(unknown_tipped),
            "examples": dict(ex_by), "distinct_too_strict_calls": dict(distinct), "fix_kind": dict(fixable),
            "sources": {f: sources.get(f, []) for f in detail_f},
            "facts_vs_tool": facts_vs_tool(rows), "ceiling": ceiling(convs, rows),
            "conversations": {k: dict(v) for k, v in sorted(conv_counts.items())}}


def _example(r: dict, located: List[dict]) -> dict:
    return {"ckey": r["ckey"], "tool": r["tool"], "args": short_args(r["args"]),
            "rules": [it["rule"] for it in located],
            "tipping": [f"{t['fact']}={t['value']} ({t['source']})" for it in located for t in it["tipping"]]}


# ----------------------------------------------------------------------------------------------- pass 2: variants
def choose_items(blame_all: Dict[str, Any], n: int = TOP_N) -> Tuple[List[str], List[str]]:
    facts = list(dict.fromkeys(blame_all["suspect_facts"] + [r["fact"] for r in blame_all["facts"][:n]]))
    rules = list(dict.fromkeys(blame_all["suspect_rules"] + [r["rule"] for r in blame_all["rules"][:n]]))
    return facts, rules


def load_lookups() -> Dict[str, Dict[str, dict]]:
    """The frozen v2 lookups per domain (state_tracker/lookups_<domain>.json)."""
    from state_tracker import lookup_format as L
    return {d: L.load_lookups(d) for d in DOMAINS}


def fact_kind(fact: str, lookups: Dict[str, Dict[str, dict]]) -> str:
    """code_fact (τ-bench's tool labels it), v2_lookup (a v2 code definition, no tool label) or judge_flip."""
    if fact in TC.ALL_FACTS:
        return "code_fact"
    if any(fact in lookups.get(d, {}) for d in DOMAINS):
        return "v2_lookup"
    return "judge_flip"


def v2_lookup_values(facts: Sequence[str], data: Dict[str, Any], lookups: Dict[str, Dict[str, dict]],
                     log=say) -> Dict[str, Dict[str, List[Any]]]:
    """For v2-lookup facts: {fact: {ckey: [saved value, lookup value]}} at the frozen-TGR source checks where the
    fact is asked and the lookup gives a value (the v2 sources already use the lookup, except where it was unknown;
    an unknown lookup value keeps the saved value). The state before a check: state_tracker/state.py walk over
    executed[:executed_prefix_len], the history the guard saw."""
    from state_tracker import lookup_format as L
    from state_tracker import state as S
    t0 = time.time()
    out: Dict[str, Dict[str, List[Any]]] = {f: {} for f in facts}
    rows, convs = data["rows"], data["convs"]
    n = 0
    if not facts:
        return out
    sample = collections.Counter()
    for i, conv in enumerate(iter_dev_conversations()):
        check_v2 = conv.source_guard == "v2" and i % 10 == 0     # a sample: the walk state gives the tracker's value
        if conv.source_guard != "frozen" and not check_v2:
            continue
        todo: Dict[int, List[Tuple[str, Any, List[str]]]] = collections.defaultdict(list)
        for ch in conv.checks(judged_only=True):
            r = rows[ch.ckey]
            fs = [f for f in facts if f in r["values"] and f in lookups[conv.domain]
                  and (not check_v2 or f in r["tracker"])]
            if fs:
                todo[r["prefix"]].append((ch.ckey, ch.args, fs))
        if not todo:
            continue
        for k, st in S.walk(conv.ep["executed"], domain=conv.domain, stops=sorted(todo)):
            for ck, args, fs in todo.get(k, []):
                for f in fs:
                    v = L.evaluate_detail(lookups[conv.domain][f], st, args)["value"]
                    if check_v2:
                        sample["v2 sample: equal to the saved tracker value"] += v == rows[ck]["tracker"][f][0]
                        sample["v2 sample: checked"] += 1
                        continue
                    n += 1
                    old = rows[ck]["values"][f][0]
                    if v is not None and v != old:
                        out[f][ck] = [old, v]
    data["v2_lookup_sample"] = dict(sample)
    log(f"[audit] v2 lookups: {n} values at frozen-source checks; {dict(sample)}; {time.time() - t0:.0f} s")
    return out


def fact_changes(f: str, kind: str, rows: Dict[str, dict], allow: Optional[bool],
                 v2vals: Dict[str, Dict[str, List[Any]]]) -> Tuple[Dict[str, List[Any]], int]:
    """({ckey: [saved value, variant value]} where they differ, checks where the fact is asked)."""
    changed, asked = {}, 0
    for ck, r in rows.items():
        if f not in r["values"]:
            continue
        asked += 1
        old = r["values"][f][0]
        if kind == "v2_lookup":
            if ck in v2vals.get(f, {}):
                changed[ck] = list(v2vals[f][ck])
            continue
        lab = (r["label"].get("facts") or {}).get(f) if r["write"] else None
        new = fact_variant_value(kind, old, lab, allow, f in TC.WORLD_PART_ONLY)
        if new != old:
            changed[ck] = [old, new]
    return changed, asked


def choose_combos(blame_all: Dict[str, Any], lookups: Dict[str, Dict[str, dict]]) -> List[Tuple[str, List[Tuple[str, str]]]]:
    """Extra tests (not blames): combo:db_facts = the database facts by τ-bench's tool label all at once (what p6
    can give); combo:db_facts+top2 = the same plus the facts of the two rules with the most too-strict blocks (one-fact
    rules), each by its own kind."""
    db = [(f, "code_fact") for f in TC.ALL_FACTS]
    top = [next(iter(r["facts"])) for r in blame_all["rules"][:2] if r["n_facts"] == 1]
    out = [("combo:db_facts", db)]
    if top:
        out.append(("combo:db_facts+top2", db + [(f, fact_kind(f, lookups)) for f in top]))
    return out


def build_variants(facts: Sequence[str], rules: Sequence[str], rows: Dict[str, dict], tables: Dict[str, dict],
                   lookups: Dict[str, Dict[str, dict]], v2vals: Dict[str, Dict[str, List[Any]]],
                   combos: Sequence[Tuple[str, List[Tuple[str, str]]]] = (),
                   out_dir: str = VARIANTS_DIR) -> List[dict]:
    """Write one variant file per tested item and return the variant specs (with sha256)."""
    os.makedirs(out_dir, exist_ok=True)
    out = []
    for f in facts:
        kind = fact_kind(f, lookups)
        allow = allowing_value(tables, f)
        changed, asked = fact_changes(f, kind, rows, allow, v2vals)
        if kind == "code_fact":
            definition = ("the tool label's value where τ-bench's tool decides the fact "
                          "(output/eval_v3/tool_labels.jsonl), else the saved value")
        elif kind == "v2_lookup":
            definition = ("the v2 lookup (state_tracker/lookups_<domain>.json) on the state before the check, at the "
                          "frozen-TGR source checks (v2 sources already use it); an unknown lookup value keeps the "
                          "saved value")
        else:
            definition = f"the allowing value {allow} (the rule table's non-blocking value) wherever the fact is asked"
        if f in TC.WORLD_PART_ONLY:
            definition += (" (the label is the database part only, so it can only make the fact false: a false "
                           "label gives false, a true label keeps the saved value)")
        doc = {"kind": kind, "fact": f, "definition": definition, "allowing_value": allow,
               "checks_asked": asked, "values_changed": len(changed), "changed": dict(sorted(changed.items())),
               "inputs": {"tool_labels": rel(LABELS), "rule_tables": {d: t["sha256"] for d, t in tables.items()}}}
        if kind == "v2_lookup":
            doc["lookups"] = {d: lookups[d][f]["expr"] for d in DOMAINS if f in lookups[d]}
        path = os.path.join(out_dir, f"fact_{kind}_{f}.json")
        _write_json(path, doc)
        out.append({"id": f"fact:{f}", "kind": kind, "fact": f, "allowing": allow, "path": path,
                    "sha256": sha256_file(path), "asked": asked, "values_changed": len(changed)})
    for cid, comps in combos:
        changed: Dict[str, Dict[str, List[Any]]] = {}
        for f, kind in comps:
            ch_f, _ = fact_changes(f, kind, rows, allowing_value(tables, f), v2vals)
            for ck, ov in ch_f.items():
                changed.setdefault(ck, {})[f] = ov
        doc = {"kind": "combo", "id": cid, "components": [{"fact": f, "kind": k} for f, k in comps],
               "definition": "each component as in its own variant, all at once", "values_changed": len(changed),
               "changed": dict(sorted(changed.items()))}
        path = os.path.join(out_dir, f"combo_{cid.split(':', 1)[1].replace('+', '_and_')}.json")
        _write_json(path, doc)
        out.append({"id": cid, "kind": "combo", "components": [list(c) for c in comps], "path": path,
                    "sha256": sha256_file(path), "asked": sum(1 for r in rows.values()
                                                              if any(f in r["values"] for f, _ in comps)),
                    "values_changed": len(changed)})
    for rr in rules:
        domain, rid = rr.split(":", 1)
        src = os.path.join(paths.RULES_DIR, domain, "rule_set.json")
        with open(src, encoding="utf-8") as fh:
            rs = json.load(fh)
        path = os.path.join(out_dir, f"rule_set_{domain}_without_rule_{rid}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(rule_set_without(rs, rid), fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        asked = sum(1 for r in rows.values() if r["domain"] == domain and rid in r["circuit"])
        out.append({"id": f"rule:{rr}", "kind": "rule", "rule": rr, "domain": domain, "rule_id": rid, "path": path,
                    "sha256": sha256_file(path), "asked": asked, "source_sha256": sha256_file(src)})
    for domain in DOMAINS:                  # control: an unchanged copy of the rule set must change nothing
        src = os.path.join(paths.RULES_DIR, domain, "rule_set.json")
        with open(src, encoding="utf-8") as fh:
            rs = json.load(fh)
        path = os.path.join(out_dir, f"control_rule_set_{domain}_unchanged.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(rs, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        out.append({"id": f"control:{domain}", "kind": "control", "domain": domain, "rule_id": None, "path": path,
                    "sha256": sha256_file(path), "asked": sum(1 for r in rows.values() if r["domain"] == domain
                                                              and r["judged"])})
    return out


def _write_json(path: str, doc: Any) -> None:
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(doc, f, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    os.replace(path + ".tmp", path)


def _rule_guard(path: str):
    from fork import points_tgr as PT
    from guard import tgr_tracker
    from method_tgr.runtime import TGRConfig, load_rule_set
    config = TGRConfig(actionable_feedback=True, judge_effort=tgr_tracker.JUDGE_EFFORT, epsilon=tgr_tracker.EPSILON)
    return PT.GivenJudgeTGR(load_rule_set(path), [], config)


def run_variants(variants: List[dict], rows: Dict[str, dict], log=say) -> Dict[str, List[Tuple[str, str, str]]]:
    """Re-decide every development check where a variant's item is asked. Returns {variant id: [(ckey, before,
    after)] of the changed decisions} (before = the saved decision, equal to the base re-decide)."""
    from fork import offline_v3 as O
    t0 = time.time()
    guards = {v["id"]: _rule_guard(v["path"]) for v in variants if v["kind"] in ("rule", "control")}
    changes: Dict[str, List[Tuple[str, str, str]]] = {v["id"]: [] for v in variants}
    decided = collections.Counter()
    fact_maps: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for v in variants:
        if v["kind"] in FACT_KINDS or v["kind"] == "combo":
            with open(v["path"], encoding="utf-8") as f:
                ch = json.load(f)["changed"]
            fact_maps[v["id"]] = ({ck: {v["fact"]: ov[1]} for ck, ov in ch.items()} if v["kind"] != "combo" else
                                  {ck: {f: ov[1] for f, ov in m.items()} for ck, m in ch.items()})
    for conv in iter_dev_conversations():
        for ch in conv.checks(judged_only=True):
            r = rows[ch.ckey]
            given = given_of(ch.saved)
            for v in variants:
                if v["id"] in fact_maps:
                    cm = fact_maps[v["id"]].get(ch.ckey)
                    if cm is None:
                        continue
                    g2 = dict(given)
                    for f, val in cm.items():
                        g2[f] = {"value": val, "evidence": given[f]["evidence"]}
                    res = O.decide(ch, "frozen", g2)
                else:
                    if r["domain"] != v["domain"] or (v["rule_id"] is not None and v["rule_id"] not in r["circuit"]):
                        continue
                    rec = O.run_guard(guards[v["id"]], ch.history, ch.msg, ch.n_exec, ch.past, given)
                    res = O.result_of(rec, v["id"])
                decided[v["id"]] += 1
                if res["decision"] != r["decision"]:
                    changes[v["id"]].append((ch.ckey, r["decision"], res["decision"]))
    log(f"[audit] pass 2: {sum(decided.values())} re-decides for {len(variants)} variants, {time.time() - t0:.0f} s")
    for v in variants:
        v["re_decided"] = decided[v["id"]]
    return changes


def variant_results(variants: List[dict], changes: Dict[str, List[Tuple[str, str, str]]],
                    rows: Dict[str, dict], located: Optional[Dict[str, List[dict]]] = None) -> List[dict]:
    located = located or {}
    ts = [ck for ck, r in rows.items() if r.get("cls") == "too_strict"]
    out = []
    for v in variants:
        ch = changes[v["id"]]
        res = dict(v)
        res["path"] = rel(v["path"])
        if v["kind"] in FACT_KINDS or v["kind"] == "rule":
            item = v["id"]
            name = item.split(":", 1)[1]
            res["too_strict_with_item"] = sum(
                1 for ck in ts if any((it["rule"] == name) if v["kind"] == "rule" else
                                      any(t["fact"] == name for t in it["tipping"]) for it in located.get(ck, [])))
            res["too_strict_alone"] = sum(1 for ck in ts if alone_fixable(located.get(ck, []), item))
        added_checks = collections.Counter(rows[c[0]]["label"]["check"] for c in ch
                                           if c[1] == "block" and c[2] == "allow" and rows[c[0]]["write"]
                                           and refused_on_mapped_fact(rows[c[0]]["label"]))
        res["added_allow_checks"] = dict(added_checks)
        res["all"] = dict(tally_changes(ch, rows))
        for p in PARTS:
            res[p] = dict(tally_changes([c for c in ch if rows[c[0]]["part"] == p], rows))
        for s in ("frozen", "v2"):
            res[f"src_{s}"] = dict(tally_changes([c for c in ch if rows[c[0]]["src"] == s], rows))
        fd = first_divergence(ch, rows)
        res["first"] = dict(tally_changes(fd, rows))
        res["kept"] = kept(collections.Counter(res["all"]))
        res["kept_first"] = kept(collections.Counter(res["first"]))
        res["examples_removed"] = [c[0] for c in ch if rows[c[0]].get("cls") == "too_strict"][:EXAMPLES]
        res["examples_added"] = [c[0] for c in ch if _is_added(c, rows)][:EXAMPLES]
        out.append(res)
    return out


def _is_added(c: Tuple[str, str, str], rows: Dict[str, dict]) -> bool:
    r = rows[c[0]]
    if c[1] == "allow" and c[2] == "block":
        return r["write"] and r["match"] == "exact" and r["label"]["accepted"]
    return c[1] == "block" and c[2] == "allow" and r["write"] and refused_on_mapped_fact(r["label"])


def cancel_checks(data: Dict[str, Any], log=say) -> Dict[str, Any]:
    """The database at each too-strict block of cancel_reservation (the state before the check, state.py walk): was
    the reservation booked within 24 hours of the policy's current time, was a flight cancelled by the airline, is
    the cabin business, does it have travel insurance. These are the conditions of the cancellation rule; it shows
    whether the facts behind those blocks were right."""
    from state_tracker import state as S
    import datetime
    rows = data["rows"]
    want = collections.defaultdict(list)
    for ck, r in rows.items():
        if r.get("cls") == "too_strict" and r["tool"] == "cancel_reservation":
            want[r["conv"]].append(ck)
    c = collections.Counter()
    by_rule: Dict[str, collections.Counter] = {}
    res_by_rule: Dict[str, set] = {}
    per_res: Dict[str, dict] = {}
    if not want:
        return {"counts": {}, "reservations": {}, "by_rule": {}}
    for conv in iter_dev_conversations():
        if conv.conv_key not in want:
            continue
        stops = sorted({rows[ck]["prefix"] for ck in want[conv.conv_key]})
        for k, st in S.walk(conv.ep["executed"], domain=conv.domain, stops=stops):
            for ck in want[conv.conv_key]:
                if rows[ck]["prefix"] != k:
                    continue
                rid = json.loads(rows[ck]["args"]).get("reservation_id")
                res = (st.db.get("reservations") or {}).get(rid) or {}
                created = res.get("created_at")
                within = None
                if created and st.today is not None:
                    within = (st.today - datetime.datetime.fromisoformat(created)) <= datetime.timedelta(hours=24)
                cancelled = any(((st.db.get("flights") or {}).get(f.get("flight_number"), {}).get("dates") or {})
                                .get(f.get("date"), {}).get("status") == "cancelled" for f in res.get("flights", []))
                key = (f"within 24 h {within}, airline cancelled {cancelled}, business {res.get('cabin') == 'business'}"
                       f", insurance {res.get('insurance')}")
                rules = "+".join(rows[ck]["violated"])
                c[f"rules {rules} | {key}"] += 1
                for rule in rows[ck]["violated"]:
                    g = by_rule.setdefault(f"{conv.domain}:{rule}", collections.Counter())
                    g["blocks"] += 1
                    g["an allowing condition true (within 24 h, airline cancelled or business)"] += bool(
                        within or cancelled or res.get("cabin") == "business")
                    g[f"insurance {res.get('insurance')}"] += 1
                    res_by_rule.setdefault(f"{conv.domain}:{rule}", set()).add(rid)
                per_res.setdefault(rid, {"checks": 0, "conditions": key})["checks"] += 1
    log(f"[audit] cancellation database check: {dict(c)}")
    for k, v in res_by_rule.items():
        by_rule[k]["reservations"] = len(v)
    return {"counts": dict(c), "reservations": per_res, "by_rule": {k: dict(v) for k, v in sorted(by_rule.items())}}


# ----------------------------------------------------------------------------------------------- outputs
def wrong_lines(rows: Dict[str, dict], located: Dict[str, List[dict]]) -> List[dict]:
    """One compact line per wrong or unclear decision (WRONG_LINE_CLASSES)."""
    out = []
    for r in rows.values():
        if r.get("cls") not in WRONG_LINE_CLASSES:
            continue
        items = located.get(r["ckey"], [])
        line = {"ckey": r["ckey"], "class": r["cls"], "dataset": r["dataset"], "agent": r["agent"],
                "domain": r["domain"], "bin": r["bin"], "src": r["src"], "tool": r["tool"],
                "args": short_args(r["args"], 160), "cap": r["cap"],
                "rules": [it["rule"] for it in items],
                "tipping": [{"rule": it["rule"], "fact": t["fact"], "value": t["value"], "source": t["source"],
                             "label": (r["label"].get("facts") or {}).get(t["fact"], "no label")}
                            for it in items for t in it["tipping"]]}
        out.append(line)
    order = {d: i for i, d in enumerate(DEV_DATASETS)}
    out.sort(key=lambda x: (order[x["dataset"]], x["ckey"].rsplit("|", 1)[0], int(x["ckey"].rsplit("|", 1)[1])))
    return out


def _f(n: Any) -> str:
    return f"{n:,}" if isinstance(n, int) else str(n)


def _pct(a: int, b: int) -> str:
    return f"{100.0 * a / b:.1f} %" if b else "-"


def _import_matplotlib():
    """matplotlib.pyplot with the Agg backend, imported before the write guard (its font cache), or None."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        return plt
    except Exception:  # noqa: BLE001 - no matplotlib: simple SVG figures
        return None


INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")          # blue, orange, aqua (the first three validate all-pairs)


def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#c3c2b7")
    ax.tick_params(colors=INK2, labelsize=8)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _hbars(plt, path: str, labels: List[str], series: List[Tuple[str, List[float]]], title: str, xlabel: str,
           stacked: bool) -> str:
    """Horizontal bars (stacked or grouped), one row per label, top row first."""
    n = len(labels)
    fig, ax = plt.subplots(figsize=(9.5, 0.42 * n + 1.6), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    ys = list(range(n))[::-1]
    k = len(series)
    h = 0.62 if stacked else 0.7 / k
    left = [0.0] * n
    for j, (name, vals) in enumerate(series):
        if stacked:
            ax.barh(ys, vals, left=left, height=h, color=SERIES[j], edgecolor=SURFACE, linewidth=1.2, label=name)
            left = [a + b for a, b in zip(left, vals)]
        else:
            off = (k - 1) / 2.0 - j
            ax.barh([y + off * h for y in ys], vals, height=h * 0.92, color=SERIES[j], edgecolor=SURFACE,
                    linewidth=1.0, label=name)
            for y, v in zip(ys, vals):
                ax.text(v, y + off * h, f" {int(v):,}", va="center", ha="left", fontsize=7, color=INK2)
    if stacked:
        for y, v in zip(ys, left):
            ax.text(v, y, f" {int(v):,}", va="center", ha="left", fontsize=7, color=INK2)
    ax.set_yticks(ys)
    ax.set_yticklabels(labels, fontsize=7.5, color=INK)
    ax.set_xlabel(xlabel, fontsize=8, color=INK2)
    ax.set_title(title, fontsize=10, color=INK, loc="left")
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


def _svg_hbars(path: str, labels: List[str], series: List[Tuple[str, List[float]]], title: str) -> str:
    """The SVG fallback (standard library): grouped horizontal bars with values."""
    path = os.path.splitext(path)[0] + ".svg"
    top = max([max(v) for _, v in series if v] + [1])
    w, row = 900, 18 * max(1, len(series)) + 8
    hgt = 60 + row * len(labels)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{hgt}" font-family="sans-serif" '
           f'font-size="11"><rect width="100%" height="100%" fill="{SURFACE}"/>',
           f'<text x="10" y="20" font-size="14" fill="{INK}">{_xml(title)}</text>']
    for i, lab in enumerate(labels):
        y0 = 40 + i * row
        out.append(f'<text x="10" y="{y0 + 12}" fill="{INK}">{_xml(lab[:60])}</text>')
        for j, (name, vals) in enumerate(series):
            bw = 380.0 * vals[i] / top
            y = y0 + j * 18
            out.append(f'<rect x="420" y="{y}" width="{bw:.1f}" height="14" fill="{SERIES[j % 3]}"/>')
            out.append(f'<text x="{424 + bw:.1f}" y="{y + 11}" fill="{INK2}">{_xml(name)} {int(vals[i]):,}</text>')
    out.append("</svg>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    return path


def _xml(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def figures(plt, an: Dict[str, Any], results: List[dict], out_dir: str = FIG_DIR) -> List[str]:
    os.makedirs(out_dir, exist_ok=True)
    made = []
    # 1. too-strict blocks by tipping fact and value source
    facts = an["blame"]["all"]["facts"][:14]
    labels = [r["fact"] for r in facts]
    def src(r, keys):
        return [float(sum(v for k, v in x["sources"].items() if k in keys)) for x in r]
    ser = [("judge", src(facts, ("judge",))), ("tracker (v2 code)", src(facts, ("tracker",))),
           ("unknown, looked up as the blocking value", src(facts, ("judge-unknown", "tracker-unknown")))]
    p = os.path.join(out_dir, "v3_audit_facts.png")
    made.append(_hbars(plt, p, labels, ser, "Too-strict blocks by tipping fact and who set its value "
                       "(development data, all sets)", "too-strict blocks (a block counts once per tipping fact)",
                       True) if plt else _svg_hbars(p, labels, ser, "Too-strict blocks by tipping fact and source"))
    # 2. by length bin and agent (main data): too-strict per 100 write checks
    labels, ser = [], [("luna", []), ("nano", [])]
    for b in BINS:
        labels.append(f"history {b}")
        for j, a in enumerate(AGENTS):
            c = an["by_part_agent_bin"].get(f"main|{a}|{b}", {})
            ser[j][1].append(100.0 * c.get("too_strict", 0) / c["write checks"] if c.get("write checks") else 0.0)
    p = os.path.join(out_dir, "v3_audit_bins.png")
    if plt:
        fig, ax = plt.subplots(figsize=(7.5, 3.4), dpi=150)
        fig.patch.set_facecolor(SURFACE)
        _style(ax)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.grid(axis="x", visible=False)
        xs = list(range(len(labels)))
        for j, (name, vals) in enumerate(ser):
            off = -0.17 if j == 0 else 0.17
            ax.bar([x + off for x in xs], vals, width=0.32, color=SERIES[j], edgecolor=SURFACE, linewidth=1.0,
                   label=name)
            for x, v, b in zip(xs, vals, BINS):
                n = an["by_part_agent_bin"].get(f"main|{name}|{b}", {}).get("write checks", 0)
                ax.text(x + off, v, f"{v:.1f}\nn={n:,}", ha="center", va="bottom", fontsize=6.5, color=INK2)
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, fontsize=8, color=INK)
        ax.set_ylabel("too-strict blocks per 100 write checks", fontsize=8, color=INK2)
        ax.set_title("Too-strict blocks by history length (Stage A + ours + partner)", fontsize=10, color=INK,
                     loc="left")
        ax.legend(fontsize=8, frameon=False)
        ax.margins(y=0.25)
        fig.tight_layout()
        fig.savefig(p, facecolor=SURFACE)
        plt.close(fig)
        made.append(p)
    else:
        made.append(_svg_hbars(p, labels, ser, "Too-strict blocks per 100 write checks by length bin"))
    # 3. blame tests: removed vs added
    res = [r for r in results if r["kind"] != "control" and r["all"].get("changed")]
    def short(x: str) -> str:
        return x if len(x) <= 58 else x[:55] + "..."
    labels = [f"{short(r['id'])} ({r['kind']}){' - kept' if r['kept'] else ''}" for r in res]
    ser = [("too-strict blocks removed", [float(r["all"].get("removed", 0)) for r in res]),
           ("wrong decisions added (P4.0)", [float(r["all"].get("added", 0)) for r in res])]
    p = os.path.join(out_dir, "v3_audit_blame.png")
    made.append(_hbars(plt, p, labels, ser, "Blame tests (P4.0): too-strict blocks removed, wrong decisions added",
                       "checks (all changed checks; variants that changed no decision are left out)", False)
                if plt else _svg_hbars(p, labels, ser, "Blame tests"))
    return made


# ----------------------------------------------------------------------------------------------- the report
def _cls_row(c: Dict[str, int]) -> List[int]:
    unclear = sum(c.get(k, 0) for k in ("unclear_done_before", "unclear_near_block", "unclear_other_block",
                                        "unclear_near_allow"))
    return [c.get("write checks", 0), c.get("too_strict", 0), c.get("delayed", 0), unclear,
            c.get("block_tool_refuses", 0), c.get("right_allow", 0), c.get("allowed_unwanted", 0),
            c.get("allow_tool_refuses", 0)]


CLS_HEAD = ("| {} | write checks | too strict | per 100 | delayed | unclear | block, tool refuses | right allow "
            "| allowed but unwanted | allow, tool refuses |")
CLS_SEP = "|---|---|---|---|---|---|---|---|---|---|"


def _cls_line(name: str, c: Dict[str, int]) -> str:
    v = _cls_row(c)
    rate = f"{100.0 * v[1] / v[0]:.1f}" if v[0] else "-"
    return (f"| {name} | {_f(v[0])} | **{_f(v[1])}** | {rate} | {_f(v[2])} | {_f(v[3])} | {_f(v[4])} | {_f(v[5])} "
            f"| {_f(v[6])} | {_f(v[7])} |")


def _ex(e: dict) -> str:
    return (f"`{e['ckey']}` {e['tool']} `{e['args']}`; rules {', '.join(e['rules']) or '-'}; tipping "
            f"{'; '.join(e['tipping']) or '-'}")


def _variant_line(r: dict) -> str:
    a, fst = r["all"], r["first"]
    alone = f"{_f(r['too_strict_with_item'])} / {_f(r['too_strict_alone'])}" if "too_strict_alone" in r else "-"
    return (f"| `{r['id']}` | {r['kind']} | {_f(r['asked'])} | {_f(r.get('values_changed', '-'))} | {alone} | "
            f"{_f(a.get('changed', 0))} | **{_f(a.get('removed', 0))}** | {_f(a.get('added_block', 0))} / "
            f"{_f(a.get('added_allow_mapped', 0))} | **{'yes' if r['kept'] else 'no'}** | "
            f"{_f(fst.get('removed', 0))} / {_f(fst.get('added', 0))} / {'yes' if r['kept_first'] else 'no'} | "
            f"{_f(a.get('removed_delayed', 0))} | {_f(a.get('new_allow_not_expected', 0))} / "
            f"{_f(a.get('new_allow_near', 0))} / {_f(a.get('new_allow_tool_refuses', 0))} / "
            f"{_f(a.get('new_allow_not_write', 0))} |")


VARIANT_HEAD = ("| variant | kind | checks asked | values changed | too-strict blocks with it / it alone can fix | "
                "changed decisions | **removed** | added: new blocks / new allows refused on a mapped fact | "
                "**kept** | first divergence: removed / added / kept | reported: delayed removed | reported: new "
                "allows not expected / near / tool refuses (any) / not a write |")
VARIANT_SEP = "|---|---|---|---|---|---|---|---|---|---|---|---|"


def write_report(path: str, ctx: Dict[str, Any]) -> None:
    an, data, results = ctx["an"], ctx["data"], ctx["results"]
    by = an["by"]
    L: List[str] = []
    w = L.append
    main_c, sb_c = by["part"].get("main", {}), by["part"].get("stage_b", {})
    ba = an["blame"]["all"]
    singles = [r for r in results if r["kind"] in FACT_KINDS or r["kind"] == "rule"]
    combos = [r for r in results if r["kind"] == "combo"]
    controls = [r for r in results if r["kind"] == "control"]
    n_ts = sum(1 for r in data["rows"].values() if r.get("cls") == "too_strict")
    w("# Tracker v3, part 4: the decision audit on the eval v2 development data")
    w("")
    w(f"Written by `scoring/v3_audit.py` on {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. $0: no LLM call, "
      "no network (blocked). Development data only: Stage A (2,000), our and the partner's train runs, and the Stage B "
      "tries forked from them; the hold-out sets and the Stage B val forks are never opened. The eval v2 manifest was "
      f"checked first ({ctx['manifest_files']} files). The blame rule is P4.0 (`output/eval_v3/preregistration.md`). "
      "Per-check lines: `output/eval_v3/p4_wrong.jsonl`; all counts: `output/eval_v3/p4_audit.json`.")
    w("")
    # ---- summary
    kept_list = [r for r in singles if r["kept"]]
    w("## In short")
    w(f"- **Too strict** (a block on an exact expected call that τ-bench's tool accepts and that never runs): "
      f"**{_f(main_c.get('too_strict', 0))}** of {_f(main_c.get('write checks', 0))} write checks in Stage A + ours + "
      f"partner, **{_f(sb_c.get('too_strict', 0))}** of {_f(sb_c.get('write checks', 0))} in Stage B. Weak agent "
      + " + ".join(_f(by['agent'].get(f'{p}|nano', {}).get('too_strict', 0)) for p in PARTS) + ", strong agent "
      + " + ".join(_f(by['agent'].get(f'{p}|luna', {}).get('too_strict', 0)) for p in PARTS)
      + " (main + Stage B). For the weak agent they grow with the history length (section 2).")
    top_r = ba["rules"][:2]
    if top_r:
        w("- **Two reminder rules hold most of them:** " + ", ".join(
            f"`{r['rule']}` ({_f(r['wrong'])}, fact `{next(iter(r['facts']))}`)" for r in top_r)
          + f": {_f(sum(r['wrong'] for r in top_r))} of {_f(n_ts)}. Both facts are judge facts that read the agent's "
          "own messages: one agent step (remind the user to list all items) makes them true, but the call never ran.")
    fk = an["fix_kind"]
    w(f"- One agent step (list, remind, ask) could fix {_f(fk.get('main|agent step', 0) + fk.get('stage_b|agent step', 0))}"
      f" of {_f(n_ts)} too-strict blocks (by the rule set's evidence sources); the rest need data or the user.")
    gc = an["facts_vs_tool"]["code"].get("main|gift_card_balance_covers_price_difference", {})
    w(f"- **Code bugs** (v2 tracker vs τ-bench's tool): the known harm, the gift-card balance fact false because the "
      f"balance was never shown: {_f(gc.get('never shown', 0))} checks; other \"never shown\": "
      f"{_f(sum(v.get('never shown', 0) for k, v in an['facts_vs_tool']['code'].items()) - gc.get('never shown', 0))};"
      f" shown but different (real bugs): "
      f"{_f(sum(v.get('shown, value differs', 0) for v in an['facts_vs_tool']['code'].values()))}.")
    w(f"- Suspect facts (wrong in 2+ rules): {', '.join(f'`{x}`' for x in ba['suspect_facts']) or 'none'}. Suspect "
      f"rules (wrong with 2+ facts): {', '.join(f'`{x}`' for x in ba['suspect_rules']) or 'none'}.")
    w(f"- **Blame tests (P4.0):** {len(kept_list)} of {len(singles)} kept: "
      + (", ".join(f"`{r['id']}` (-{_f(r['all'].get('removed', 0))})" for r in kept_list) or "none")
      + ". The airline ones are refuted by the database (section 6): τ-bench expected cancellations that the written "
      "policy does not allow.")
    for r in combos:
        extra = [f for f, k in r["components"] if k != "code_fact"]
        w(f"- Extra test `{r['id']}` (the {sum(1 for _, k in r['components'] if k == 'code_fact')} database facts by "
          "τ-bench's tool label" + (" + " + ", ".join(f"`{f}`" for f in extra) + " set to their allowing value"
                                    if extra else "") + f"): removes **{_f(r['all'].get('removed', 0))}** of "
          f"{_f(n_ts)} too-strict blocks, adds **{_f(r['all'].get('added', 0))}**.")
    b = data["base"]
    w(f"- Base check: the `frozen` guard, given the full set of values the source guard used, reproduces "
      f"{_f(b.get('equal', 0))} of {_f(b.get('re-decided', 0))} saved decisions, margins and violated rules "
      f"(v2 sources {_f(b.get('equal v2', 0))} / {_f(b.get('re-decided v2', 0))}). TGR built from an unchanged copy "
      "of each rule set changes " + ", ".join(f"{r['domain']} {_f(r['all'].get('changed', 0))}" for r in controls)
      + " decisions. The ceiling table is reproduced (section 7).")
    w("")
    # ---- classes
    w("## 1. The classes")
    w("Each development write check (a τ-bench tool that writes to the database; Stage B: only the checks after the "
      "fork) gets one class, from: the guard's decision (a cap override is a block that then ran); the task's "
      "expected actions (τ-bench's task file via `fork/rebuild_tasks.py`; equal to each episode's `reward_info` "
      "actions); τ-bench's tool label (p3); what ran (`executed`). **Exact** = same tool, same arguments as "
      "canonical JSON (sorted keys, 1.0 = 1). **Near** = same tool, same main object id (`order_id`, "
      "`reservation_id` or `user_id`), other arguments.")
    w("")
    w("| class | definition | Stage A + ours + partner | Stage B |")
    w("|---|---|---|---|")
    for k in CLASSES:
        w(f"| `{k}` | {CLASS_TEXT[k]} | {_f(main_c.get(k, 0))} | {_f(sb_c.get(k, 0))} |")
    w("")
    w(f"Delayed by this check's own cap override: {_f(main_c.get('delayed: by the cap override', 0))} / "
      f"{_f(sb_c.get('delayed: by the cap override', 0))}. Allows the tool refuses on a mapped fact (wrong allows): "
      f"{_f(main_c.get('allow_tool_refuses: on a mapped fact', 0))} / "
      f"{_f(sb_c.get('allow_tool_refuses: on a mapped fact', 0))}. Per fact (section 3): **code bug** = v2 sources, "
      "the tracker's value differs from the tool label where the tool decides (\"never shown\": the v2 lookup's "
      "object was in no earlier tool output, so `if_missing` gave the value; \"shown, value differs\": a real bug); "
      "**judge fact error** = the judge's own value differs (frozen and v2 sources).")
    nw = an["nonwrite"]
    w("")
    w("Not classed (no outcome label), blocks / checks, main and Stage B: replies " + ", ".join(
        f"{_f(nw.get(f'{p}|respond|blocks', 0))} / {_f(nw.get(f'{p}|respond|checks', 0))}" for p in PARTS)
      + "; read tools " + ", ".join(
        f"{_f(nw.get(f'{p}|read or other|blocks', 0))} / {_f(nw.get(f'{p}|read or other|checks', 0))}" for p in PARTS)
      + "; transfers " + ", ".join(
        f"{_f(nw.get(f'{p}|transfer|blocks', 0))} / {_f(nw.get(f'{p}|transfer|checks', 0))}" for p in PARTS) + ".")
    w("")
    # ---- splits
    w("## 2. Wrong decisions by data set, agent, domain, source guard and length")
    w("Unclear = done before + near block + other block + near allow. Per 100 = too strict per 100 write checks. "
      "Main = Stage A + ours + partner; Stage B apart (its tries repeat the source conversation up to the fork).")
    w("")
    w(CLS_HEAD.format("group"))
    w(CLS_SEP)
    for ds in DEV_DATASETS:
        if ds in by["dataset"]:
            w(_cls_line(f"`{ds}`", by["dataset"][ds]))
    w(_cls_line("**Stage A + ours + partner**", main_c))
    for k, keys in (("agent", AGENTS), ("domain", DOMAINS), ("src", ("frozen", "v2")), ("bin", BINS)):
        for part in PARTS:
            for g in keys:
                if f"{part}|{g}" in by[k]:
                    w(_cls_line(f"{ {'src': 'source guard', 'bin': 'length'}.get(k, k)} {g}, "
                                f"{'main' if part == 'main' else 'Stage B'}", by[k][f"{part}|{g}"]))
    w("")
    w("Too strict / write checks by length bin and agent (Stage A + ours + partner):")
    w("")
    w("| agent | " + " | ".join(BINS) + " |")
    w("|---|---|---|---|")
    for a in AGENTS:
        cells = []
        for bn in BINS:
            c = an["by_part_agent_bin"].get(f"main|{a}|{bn}", {})
            cells.append(f"{_f(c.get('too_strict', 0))} / {_f(c.get('write checks', 0))} "
                         f"({_pct(c.get('too_strict', 0), c.get('write checks', 0))})")
        w(f"| {a} | " + " | ".join(cells) + " |")
    w("")
    w("| conversations (part, agent) | all | with a too-strict block | distinct too-strict calls | with an "
      "allowed-but-unwanted write | reward 1 | reward 1 and a too-strict block |")
    w("|---|---|---|---|---|---|---|")
    for g, c in an["conversations"].items():
        w(f"| {g.replace('|', ', ')} | {_f(c['conversations'])} | {_f(c['with a too-strict block'])} | "
          f"{_f(an['distinct_too_strict_calls'].get(g, 0))} | {_f(c['with an allowed-but-unwanted write'])} | "
          f"{_f(c['reward 1'])} | {_f(c['reward 1, with a too-strict block'])} |")
    w("")
    w("Examples (one per data set; ckey, tool, arguments, violated rules, tipping facts = value (source)):")
    w("")
    for ds in DEV_DATASETS:
        for e in an["examples"].get(f"dataset={ds}", [])[:1]:
            w(f"- {_ex(e)}")
    w("")
    # ---- facts vs tool
    fv = an["facts_vs_tool"]
    w("## 3. Facts against τ-bench's tool label")
    w("At labelled write checks where the tool decides the fact. The order-status labels hold the database part only, "
      "so a false value with a true label can be right (the order was not looked up). Facts with full agreement are "
      "left out: " + ", ".join(sorted({k for k, c in fv["code"].items() if set(c) <= {"agree"}})) + " (code); "
      + ", ".join(sorted({k for k, c in fv["judge"].items() if set(c) <= {"agree"}})) + " (judge).")
    w("")
    w("| part, fact | code (v2): agree / never shown / shown, differs / unknown | judge: agree / false, tool true / "
      "true, tool false / unknown |")
    w("|---|---|---|")
    for k in sorted(set(fv["code"]) | set(fv["judge"])):
        c, j = fv["code"].get(k, {}), fv["judge"].get(k, {})
        if set(c) <= {"agree"} and set(j) <= {"agree"}:
            continue
        w(f"| {k.replace('|', ', ')} | {_f(c.get('agree', 0))} / {_f(c.get('never shown', 0))} / "
          f"{_f(c.get('shown, value differs', 0))} / {_f(c.get('tracker unknown', 0))} | {_f(j.get('agree', 0))} / "
          f"{_f(j.get('judge False, tool True', 0))} / {_f(j.get('judge True, tool False', 0))} / "
          f"{_f(j.get('judge unknown', 0))} |")
    w("")
    w("Examples:")
    w("")
    for k, exs in fv["examples_code"].items():
        if "shown, value differs" in k or k.startswith("gift_card_balance_covers_price_difference"):
            e = exs[0]
            w(f"- code, {k.replace('|', ', ')}: `{e['ckey']}` {e['tool']} tracker {e['tracker']}, tool {e['label']}; "
              f"`{e['args']}`")
    for k, exs in fv["examples_judge"].items():
        e = exs[0]
        w(f"- judge, {k}: `{e['ckey']}` ({e['src']}) {e['tool']} judge {e['judge']}, tool {e['label']}")
    w("")
    # ---- locate
    w("## 4. Locate: the rules and facts behind the too-strict blocks")
    w("Per too-strict block: the saved violated rules; per rule, the rule-table row (p2) from the values the source "
      "guard used (judge or tracker; an unknown is looked up as its blocking value); its tipping facts (the union of "
      "the smallest flip sets). Problems: " + (", ".join(f"{k} {v}" for k, v in an["locate_problems"].items())
                                               or "none") + ". Blocks with an unknown-tipped fact: "
      f"{_f(an['unknown_tipped'].get('main', 0))} (main), {_f(an['unknown_tipped'].get('stage_b', 0))} (Stage B).")
    w("")
    w("| rule | too strict | main / Stage B | luna / nano | tipping facts (count) | unknown-tipped | example |")
    w("|---|---|---|---|---|---|---|")
    for r in ba["rules"][:12]:
        d = an["rule_detail"].get(r["rule"], {})
        ex = an["rule_examples"].get(r["rule"], [{}])[0]
        w(f"| `{r['rule']}` | **{_f(r['wrong'])}** | {_f(d.get('part=main', 0))} / {_f(d.get('part=stage_b', 0))} | "
          f"{_f(d.get('agent=luna', 0))} / {_f(d.get('agent=nano', 0))} | "
          + ", ".join(f"{f} ({n})" for f, n in r["facts"].items())
          + f" | {_f(r['unknown_tipped'])} | `{ex.get('ckey', '-')}` |")
    w("")
    w("| fact | too strict | rules | value set by | tool label: agrees / says otherwise / not decided / no label | "
      "rule-set evidence | example |")
    w("|---|---|---|---|---|---|---|")
    for r in ba["facts"][:12]:
        d = an["fact_detail"].get(r["fact"], {})
        ex = an["fact_examples"].get(r["fact"], [{}])[0]
        w(f"| `{r['fact']}` | **{_f(r['wrong'])}** | " + ", ".join(f"{k} ({v})" for k, v in r["rules"].items())
          + " | " + ", ".join(f"{k} {v}" for k, v in sorted(r["sources"].items()))
          + f" | {_f(d.get('tool label: agrees', 0))} / {_f(d.get('tool label: says otherwise', 0))} / "
          f"{_f(d.get('tool label: not decided', 0))} / {_f(d.get('tool label: no label', 0))} | "
          f"{', '.join(an['sources'].get(r['fact'], []))} | `{ex.get('ckey', '-')}` |")
    w("")
    # ---- suspects
    w("## 5. Blame by pattern: the suspects")
    for part, title in (("all", "all development data"), ("main", "Stage A + ours + partner"), ("stage_b", "Stage B")):
        bp = an["blame"][part]
        w(f"- {title}: facts {', '.join(f'`{x}`' for x in bp['suspect_facts']) or 'none'}; rules "
          f"{', '.join(f'`{x}`' for x in bp['suspect_rules']) or 'none'}.")
    w("- A fact on the other side of an OR is a tipping fact even when its value is right (flipping it would also make "
      "the rule hold): `payment_method_is_gift_card` in rules 56 and 64 is such a case (the payment is a gift card; "
      "the balance is in doubt). The tests sort this out.")
    w(f"- Tested: the suspects, the top {TOP_N} facts and the top {TOP_N} rules by count, and two extra tests "
      "(several facts at once; not blames).")
    w("")
    # ---- blame tests
    w("## 6. Blame tests (P4.0)")
    w("Each variant changes one item. Every development check where the item is asked is re-decided with TGR's own "
      "code: the offline base's `frozen` guard, given all values the source guard used, only the variant's values "
      "changed; for a rule, TGR built from the variant rule set. **removed** = too-strict blocks that become allows. "
      "**added** = new blocks on an exact expected call the tool accepts + new allows the tool refuses on a mapped "
      "fact. **Kept** = removed >= 1 and added = 0. **First divergence** = only the first changed check per "
      "conversation (later checks are descriptive: the conversation would have gone differently).")
    w("")
    w("Kinds: **code_fact** = the tool label where the tool decides, else the saved value (the order-status labels can "
      "only make the fact false); **v2_lookup** = a fact with a v2 code definition and no tool label: the v2 lookup's "
      "value at the frozen-TGR source checks (v2 sources use it already); **judge_flip** = the allowing value "
      "wherever asked. A flip cannot add a block and outcome labels cannot see a wrong allow: **a kept judge flip is "
      "a suspect for p5-p8, not a proof.** **rule** = the rule set without the rule: a finding only, the frozen rule "
      "set stays. A one-fact rule's removal equals its fact's flip.")
    w("")
    w(VARIANT_HEAD)
    w(VARIANT_SEP)
    for r in singles + combos:
        w(_variant_line(r))
    w("")
    w("| variant | main: removed / added | Stage B: removed / added | frozen sources: removed / added | v2 sources: "
      "removed / added | added allows: the tool's failing check |")
    w("|---|---|---|---|---|---|")
    for r in singles + combos:
        if not r["all"].get("changed"):
            continue
        w(f"| `{r['id']}` | {_f(r['main'].get('removed', 0))} / {_f(r['main'].get('added', 0))} | "
          f"{_f(r['stage_b'].get('removed', 0))} / {_f(r['stage_b'].get('added', 0))} | "
          f"{_f(r['src_frozen'].get('removed', 0))} / {_f(r['src_frozen'].get('added', 0))} | "
          f"{_f(r['src_v2'].get('removed', 0))} / {_f(r['src_v2'].get('added', 0))} | "
          + (", ".join(f"{k} {v}" for k, v in sorted(r["added_allow_checks"].items())) or "-") + " |")
    w("")
    cc = an.get("cancel_checks", {})
    if cc.get("by_rule", {}).get("airline:25"):
        g = cc["by_rule"]["airline:25"]
        w(f"**The database behind the too-strict cancellations that break `airline:25`** (the state before each block):"
          f" {_f(g.get('blocks', 0))} blocks on {_f(g.get('reservations', 0))} reservations; within 24 hours, a flight "
          "cancelled by the airline or business cabin: "
          f"{_f(g.get('an allowing condition true (within 24 h, airline cancelled or business)', 0))}; insurance yes / "
          f"no: {_f(g.get('insurance yes', 0))} / {_f(g.get('insurance no', 0))}. (Other cancellation blocks: "
          + ", ".join(f"`{k}` {_f(v.get('blocks', 0))}" for k, v in cc["by_rule"].items() if k != "airline:25")
          + ".)")
        g25 = cc["by_rule"].get("airline:25", {})
        if g25 and not g25.get("an allowing condition true (within 24 h, airline cancelled or business)", 0):
            w("")
            w(f"So at the `airline:25` blocks the flipped airline facts were right: none was within 24 hours, by a "
              f"cancelled flight or in business. Without insurance ({_f(g25.get('insurance no', 0))} blocks) nothing in "
              "the written policy allows the cancellation, so τ-bench's expected action breaks the policy (label "
              f"noise); with insurance ({_f(g25.get('insurance yes', 0))}) only the user's reason "
              "(`insured_cancellation_condition_met`, a user-message fact) is open. The kept airline flips and the kept "
              "removal of `airline:25` are not blames: P4.0 passes them only because outcome labels cannot see wrong "
              "allows.")
        w("")
    w("Examples (removed; added):")
    w("")
    for r in singles + combos:
        if r["examples_removed"] or r["examples_added"]:
            w(f"- `{r['id']}`: removed " + (", ".join(f"`{x}`" for x in r["examples_removed"][:2]) or "-")
              + "; added " + (", ".join(f"`{x}`" for x in r["examples_added"][:2]) or "-"))
    w("")
    w("Variant files (`output/eval_v3/p4_variants/`):")
    w("")
    w("| variant | file | sha256 |")
    w("|---|---|---|")
    for r in results:
        w(f"| `{r['id']}` | `{os.path.basename(r['path'])}` | `{r['sha256']}` |")
    w("")
    # ---- ceiling
    w("## 7. The overview's ceiling table, recomputed (eval v2 Stage A, frozen TGR)")
    ce = an["ceiling"]
    lu, na = ce.get("luna", {}), ce.get("nano", {})
    rows_ce = [
        ("conversations with no block at all", "no block (no blocked attempt)", "no_block"),
        ("wanted actions blocked and never done later (distinct calls, never run after the first block)",
         "wanted actions blocked and never run after the first block", "wanted_never_done"),
        ("tasks with a write the task did not want (a write ran that is not an exact expected action)",
         "unwanted: a write ran that is not exact expected", "unwanted"),
        ("tasks with a missed expected action (an expected write never ran exactly)",
         "missed: an expected write never ran (exact)", "missed")]
    w("")
    w("| row | overview strong / weak | recomputed strong / weak | equal |")
    w("|---|---|---|---|")
    for name, key, ok in rows_ce:
        ov = CEILING_OVERVIEW[ok]
        got = (lu.get(key, 0), na.get(key, 0))
        w(f"| {name} | {ov[0]} / {ov[1]} | {got[0]} / {got[1]} | {'yes' if tuple(got) == ov else 'no'} |")
    w("")
    w(f"- Wanted actions blocked: {lu.get('wanted actions blocked (distinct calls)', 0)} / "
      f"{na.get('wanted actions blocked (distinct calls)', 0)} distinct calls, run after the first block "
      f"{lu.get('... run after the first block', 0)} / {na.get('... run after the first block', 0)} (the plan check: "
      "101 - 79 and 276 - 205, the same 22 and 71). Adding \"the tool accepts\": "
      f"{lu.get('... same, tool accepts', 0)} / {na.get('... same, tool accepts', 0)}. This audit counts checks: "
      f"{lu.get('too-strict checks (this audit)', 0)} / {na.get('too-strict checks (this audit)', 0)} too-strict "
      f"checks in {lu.get('conversations with a too-strict block (this audit)', 0)} / "
      f"{na.get('conversations with a too-strict block (this audit)', 0)} conversations.")
    w(f"- Unwanted, weak agent: {na.get('unwanted: a write ran that is not exact expected', 0)}, not 94. The overview's "
      "exact rule is not written down; counting transfers or attempted writes gives far more, so the 3 tasks are a "
      "unit detail (estimate). Not exact and not near (this audit's allowed-but-unwanted): "
      f"{lu.get('unwanted: ... and not near', 0)} / {na.get('unwanted: ... and not near', 0)}: in Stage A almost "
      "every unwanted write is a near call (right order, other items or payment), the agent's own mistake.")
    w(f"- Missed by reward (< 1) instead: {lu.get('missed: reward < 1', 0)} / {na.get('missed: reward < 1', 0)}.")
    w("")
    # ---- figures
    w("## 8. Figures")
    w("")
    for p, alt in zip(ctx["figures"], ("too-strict blocks by fact and source", "too-strict blocks by length bin",
                                       "blame tests: removed and added")):
        w(f"![{alt}](../../../docs/reports/figures/{os.path.basename(p)})")
        w("")
    # ---- questions
    w("## 9. Questions for the order of p5-p10")
    w("")
    for q in ctx["questions"]:
        w(q)
    w("")
    # ---- run
    w("## 10. Recompute; files")
    w("```")
    w("cd predicate_correctness")
    w("PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 ~/venvs/tau-bench/bin/python -B -m scoring.v3_audit "
      "> output/logs/v3_p4_<nn>_audit.log 2>&1")
    w("/home/azureuser/miniconda3/bin/python3 -B -m unittest tests.test_v3_audit > output/logs/v3_p4_<nn>_tests.log 2>&1")
    w("```")
    smp = data.get("v2_lookup_sample", {})
    w(f"Run time {ctx['seconds']:.0f} s (pass 1 {data['seconds']:.0f} s). v2-lookup state check (a sample of v2 "
      f"sources): {_f(smp.get('v2 sample: equal to the saved tracker value', 0))} of "
      f"{_f(smp.get('v2 sample: checked', 0))} values equal the saved tracker value. Problems: "
      + ("; ".join(data["problems"][:10]) if data["problems"] else "none") + ".")
    w("")
    w("| file | sha256 |")
    w("|---|---|")
    for k, v in ctx["sha256"].items():
        if not k.startswith("output/eval_v3/p4_variants/"):
            w(f"| `{k}` | `{v}` |")
    w("")
    w("(Variant files: section 6. The sha256 of this report and of `p4_audit.json` are in the run log.)")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    os.replace(path + ".tmp", path)


# Suggested readings for p5 (the audit's view; p5 writes the definitions). (reading, part)
READINGS = {
    "agent_reminded_user_to_include_all_items_for_modification": (
        "an earlier agent message asks the user to make sure every item to modify is listed (any wording; once per "
        "order, Q7); structure fact or one tiny question on the agent's own text", "p7/p8"),
    "agent_reminded_user_to_include_all_items_for_exchange": (
        "the same for an exchange", "p7/p8"),
    "gift_card_balance_covers_price_difference": (
        "the database at the check: the gift card's balance covers the new items' price minus the old items' price; "
        "never \"was it shown\"", "p6"),
    "payment_method_is_gift_card": (
        "argument fact as in v2 (the payment id is a gift card); the audit finds it right, no change", "p6"),
    "consequential_action_details_listed": (
        "an earlier agent message names the call's details (order id, items, new items, payment): code matches the "
        "ids in the text with the arguments", "p7"),
    "user_explicitly_confirmed_pending_action": (
        "the user's reply after that list is an explicit yes (tiny question, two keys)", "p8"),
    "item_replacements_are_available_same_product_different_option": (
        "the database at the check: each new item exists, is available, same product, other option", "p6"),
    "user_authenticated": (
        "event: an earlier find_user_id_by_email / find_user_id_by_name_zip call worked (the v2 code); the judge "
        "said false after a working login in many reply checks", "p6"),
    "user_chose_price_difference_payment_method": (
        "the user named the payment method for the price difference (tiny question)", "p8"),
    "airline_cancelled_flight_confirmed": ("the database: a flight of the reservation has status cancelled", "p6"),
    "cancellation_is_within_24_hours": (
        "the database: created_at within 24 hours of the policy's current time", "p6"),
    "insured_cancellation_condition_met": (
        "insurance yes (database) and the user's stated reason is covered (tiny question)", "p6 + p8"),
    "reservation_has_business_cabin": ("the database (after earlier flight updates)", "p6"),
    "reservation_has_travel_insurance": ("the database", "p6"),
    "order_status_checked_pending": (
        "looked up (event) AND the database status at the check is pending; not the newest shown status (the judge "
        "said true where the tool says false in section 3)", "p6"),
    "order_status_checked_delivered": (
        "looked up (event) AND the database status at the check is delivered (the judge said true where the tool "
        "says false: an order already exchanged or returned)", "p6"),
    "reservation_has_no_used_flight_segments": ("the database: no flight of the reservation has flown yet", "p6"),
}


def questions(an: Dict[str, Any], results: List[dict]) -> List[str]:
    """Section 9 as markdown lines: the suggested order of p5-p10, the suspect facts with their readings (for the p5
    definition agents), and the questions for the user. Numbers come from this run; the readings are suggestions."""
    L: List[str] = []
    ba = an["blame"]["all"]
    res = {r["id"]: r for r in results}
    fk = an["fix_kind"]
    agent_fix = fk.get("main|agent step", 0) + fk.get("stage_b|agent step", 0)
    n_ts = agent_fix + fk.get("main|data or user", 0) + fk.get("stage_b|data or user", 0)
    db, db2 = res.get("combo:db_facts"), res.get("combo:db_facts+top2")
    top = ba["rules"][:2]
    top_n = sum(r["wrong"] for r in top)
    fv = an["facts_vs_tool"]["judge"]
    st_pend = sum(fv.get(f"{p}|order_status_checked_pending", {}).get("judge True, tool False", 0) for p in PARTS)
    st_del = sum(fv.get(f"{p}|order_status_checked_delivered", {}).get("judge True, tool False", 0) for p in PARTS)
    rem = [res.get(f"fact:{next(iter(r['facts']))}") for r in top]
    rem_added = sum(r["all"].get("added", 0) for r in rem if r)
    rem_checks = collections.Counter()
    for r in rem:
        if r:
            rem_checks.update(r.get("added_allow_checks", {}))
    L.append("Suggested order (the audit's reading; you decide):")
    L.append("")
    L.append(f"1. **p5, then p6 (database facts) as planned.** All database facts by τ-bench's tool label at once "
             f"(`combo:db_facts`) remove {_f(db['all'].get('removed', 0)) if db else '-'} too-strict blocks and add "
             f"{_f(db['all'].get('added', 0)) if db else '-'}. It also fixes the judge's status errors (judge true, tool "
             f"false: `order_status_checked_pending` {_f(st_pend)}, `order_status_checked_delivered` {_f(st_del)}), "
             f"which are why the reminder flips alone add wrong allows ({_f(rem_added)}: "
             + ", ".join(f"{k} {v}" for k, v in sorted(rem_checks.items())) + ").")
    if top:
        L.append(f"2. **Then the two reminder facts (p7 structure or p8 tiny question), before the other meaning "
                 f"facts.** " + ", ".join(f"`{r['rule']}` ({_f(r['wrong'])})" for r in top)
                 + f" hold {_f(top_n)} of {_f(n_ts)} too-strict blocks. With the database facts in place "
                 f"(`combo:db_facts+top2`) the reminder facts set to true remove "
                 f"{_f(db2['all'].get('removed', 0)) if db2 else '-'} and add {_f(db2['all'].get('added', 0)) if db2 else '-'}"
                 f" (first divergence only: {_f(db2['first'].get('removed', 0)) if db2 else '-'} / "
                 f"{_f(db2['first'].get('added', 0)) if db2 else '-'}). A flip is a suspect, not a proof: p7/p8 must "
                 "show the agent really reminded the user where the judge said no.")
    L.append(f"3. **p10 (block messages) right after, before the rest of p7-p8.** {_f(agent_fix)} of {_f(n_ts)} "
             "too-strict blocks need only one agent step (remind, list, ask), and the call never ran: the weak agent "
             "gives up after \"violated, do not repeat\". Offline numbers cannot show this; the online run can.")
    L.append("4. Then the confirmation facts (`consequential_action_details_listed`, "
             "`user_explicitly_confirmed_pending_action`), p9, the rest of p10.")
    L.append("")
    L.append("Suspect and top facts, with what the audit shows and a reading for p5 (too strict = blocks where the "
             "fact tipped a violated rule; test = removed / added by its own variant; alone = blocks it can fix by "
             "itself):")
    L.append("")
    L.append("| fact | rules (too strict) | value set by | test: removed / added; alone | reading for p5 | part |")
    L.append("|---|---|---|---|---|---|")
    shown = list(dict.fromkeys(ba["suspect_facts"] + [r["fact"] for r in ba["facts"][:15]]
                               + ["order_status_checked_delivered"]))
    rows_f = {r["fact"]: r for r in ba["facts"]}
    for f in shown:
        r = rows_f.get(f, {"wrong": 0, "rules": {}, "sources": {}})
        v = res.get(f"fact:{f}")
        test = (f"{_f(v['all'].get('removed', 0))} / {_f(v['all'].get('added', 0))}; {_f(v.get('too_strict_alone', 0))}"
                f" ({v['kind']})") if v else "not tested alone"
        reading, part = READINGS.get(f, ("-", "-"))
        L.append(f"| `{f}` | " + (", ".join(f"{k} ({_f(n)})" for k, n in r["rules"].items()) or "-")
                 + " | " + (", ".join(f"{k} {_f(n)}" for k, n in sorted(r["sources"].items())) or "-")
                 + f" | {test} | {reading} | {part} |")
    L.append("")
    cb = an["facts_vs_tool"]["code"]
    L.append(f"Code bugs to fix in p6 (v2 tracker): \"never shown\" read as false: "
             + ", ".join(f"`{k.split('|')[1]}` {_f(c.get('never shown', 0))} ({k.split('|')[0]})"
                         for k, c in sorted(cb.items()) if c.get("never shown")) + "; shown but different: "
             + (", ".join(f"`{k.split('|')[1]}` {_f(c.get('shown, value differs', 0))}" for k, c in sorted(cb.items())
                          if c.get("shown, value differs")) or "none") + " (examples in section 3).")
    L.append("")
    L.append("Questions for you:")
    L.append("")
    L.append("- Keep the frozen rule set (default)? No rule blame passes both P4.0 and the database check: the rule "
             "removals that remove too-strict blocks either add wrong allows (`retail:53`, `retail:61`, `retail:56`, "
             "`retail:64`, `retail:52`) or allow cancellations the policy forbids (`airline:25`).")
    g25 = an.get("cancel_checks", {}).get("by_rule", {}).get("airline:25", {})
    L.append(f"- Treat the `airline:25` too-strict blocks without insurance ({_f(g25.get('insurance no', 0))} of "
             f"{_f(g25.get('blocks', 0))} checks, {_f(g25.get('reservations', 0))} reservations in all) as τ-bench "
             "label noise in later counts?")
    L.append("- Order: p5 → p6 → the two reminder facts → p10 → the other p7-p8 facts → p9 (suggested), or the plan's "
             "p5-p10 order?")
    return L


# ----------------------------------------------------------------------------------------------- main
def safety() -> None:
    """Block the network, allow writes only under output/ and the figure folder, make every judge call fail."""
    from fork import points_tgr  # noqa: F401  (sets up the runner path)
    from fork import rebuild_check as RC
    from guard import write_guard
    sys.addaudithook(RC._no_network)
    os.makedirs(FIG_DIR, exist_ok=True)
    write_guard.install([paths.OUTPUT_DIR, FIG_DIR])
    from repro_runtime import calls                     # runner copy
    calls._llm = RC._NoLLM()


def json_doc(ctx: Dict[str, Any]) -> Dict[str, Any]:
    an = dict(ctx["an"])
    an.pop("located", None)
    return {"written_by": "scoring.v3_audit (tracker v3 part 4)", "base": ctx["data"]["base"],
            "base_misses": ctx["data"]["base_misses"], "problems": ctx["data"]["problems"],
            "classes": list(CLASSES), "class_text": CLASS_TEXT, "analysis": an,
            "variants": [{k: v for k, v in r.items()} for r in ctx["results"]],
            "tested_items": ctx["items"], "files": ctx["sha256"], "seconds": ctx["seconds"],
            "counts": {"conversations": len(ctx["data"]["convs"]), "checks": len(ctx["data"]["rows"]),
                       "write checks": sum(1 for r in ctx["data"]["rows"].values() if r["write"])}}


def main(argv: Optional[List[str]] = None) -> int:
    from state_tracker.v3.frozen import check_manifest
    manifest = check_manifest()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--top", type=int, default=TOP_N, help="top facts and rules tested besides the suspects")
    a = ap.parse_args(argv)
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise SystemExit("set PYTHONHASHSEED=0 (an unknown value can make TGR's decision sample)")
    t0 = time.time()
    plt = _import_matplotlib()
    safety()
    say(f"[audit] manifest ok ({len(manifest)} files); matplotlib {'yes' if plt else 'no (SVG figures)'}")
    tables = load_tables()
    data = collect()
    an = analyse(data, tables, predicate_sources())
    facts, rules = choose_items(an["blame"]["all"], a.top)
    lookups = load_lookups()
    v2facts = [f for f in facts if fact_kind(f, lookups) == "v2_lookup"]
    v2vals = v2_lookup_values(v2facts, data, lookups)
    an["cancel_checks"] = cancel_checks(data)
    combos = choose_combos(an["blame"]["all"], lookups)
    variants = build_variants(facts, rules, data["rows"], tables, lookups, v2vals, combos)
    say(f"[audit] variants: {[v['id'] for v in variants]}")
    changes = run_variants(variants, data["rows"])
    results = variant_results(variants, changes, data["rows"], an["located"])
    for r in results:
        say(f"[audit] {r['id']} ({r['kind']}): changed {r['all'].get('changed', 0)}, removed "
            f"{r['all'].get('removed', 0)}, added {r['all'].get('added', 0)}, kept {r['kept']}")
    os.makedirs(OUT_DIR, exist_ok=True)
    lines = wrong_lines(data["rows"], an["located"])
    with open(WRONG_OUT + ".tmp", "w", encoding="utf-8") as f:
        for ln in lines:
            f.write(json.dumps(ln, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(WRONG_OUT + ".tmp", WRONG_OUT)
    figs = figures(plt, an, results)
    shas = {f: sha256_file(os.path.join(PC, f)) for f in OWN_FILES if os.path.exists(os.path.join(PC, f))}
    shas[rel(WRONG_OUT)] = sha256_file(WRONG_OUT)
    for p in figs:
        shas[os.path.relpath(p, os.path.dirname(PC))] = sha256_file(p)
    for r in results:
        shas[r["path"]] = r["sha256"]
    for d, t in tables.items():
        shas[t["path"] + " (input)"] = t["sha256"]
    shas[rel(LABELS) + " (input)"] = sha256_file(LABELS)
    shas[rel(INDEX) + " (input)"] = sha256_file(INDEX)
    ctx = {"an": an, "data": data, "results": results, "figures": figs, "questions": questions(an, results),
           "sha256": shas, "seconds": time.time() - t0, "manifest_files": len(manifest),
           "items": {"facts": facts, "rules": rules}}
    _write_json(JSON_OUT, json_doc(ctx))
    write_report(REPORT, ctx)
    say(f"[audit] wrote {rel(REPORT)} sha256 {sha256_file(REPORT)}")
    say(f"[audit] wrote {rel(JSON_OUT)} sha256 {sha256_file(JSON_OUT)}")
    say(f"[audit] wrote {rel(WRONG_OUT)} ({len(lines)} lines) sha256 {shas[rel(WRONG_OUT)]}")
    say(f"[audit] done in {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
