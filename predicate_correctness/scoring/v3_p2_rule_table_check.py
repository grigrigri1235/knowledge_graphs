"""Tracker v3, part 2: checks of the rule table (docs/planning/tracker_v3/p2.md; pass marks P2.1-P2.4 in
output/eval_v3/preregistration.md). $0: no LLM call, no network.

  P2.1 every row is checked by TGR's own decision code, repro_runtime.mln.decide (runner copy), with TGR's ε and
       weights (method_tgr.runtime.TGRConfig: ε = 0.1, Gibbs threshold 16; method_tgr.rules.to_aspm: θ = 1), on a
       check whose only rule is this one (rule_ids = [rule id]): the pending action true, every other action
       predicate false, the facts as in the row, no earlier steps. A failing combination must block; the combination
       with each listed flip set applied must allow. (Also: a holding combination must allow.)
  P2.2 brute force, with mln.decide as the judge of "satisfies": for every failing combination, every set of facts
       (all 2^n) is flipped and decided. A set that is not listed must either not allow, or contain a listed smaller
       set. Listed sets must be smallest: no proper subset of a listed set allows.
  P2.3 generic code: no tool, fact or domain name of any rule set (nor "tau_bench" / "tau-bench" / "τ-bench") in
       state_tracker/v3/rule_table.py.
  P2.4 the unit tests tests/test_v3_rule_table.py, run in this process.
Also: each table on disk equals a fresh build byte for byte; the blocking values agree with the flip sets and with
the polarity; rules per fact count against the plan; rows, flip sets; rules that cannot hold by flipping facts.

Output: output/eval_v3/p2_rule_table.md (short report; every number comes from this script) and a JSON summary on
stdout. Run from predicate_correctness/ (stdlib Python):
    python3 -B -m scoring.v3_p2_rule_table_check > output/logs/<log> 2>&1
"""
from __future__ import annotations

import io
import itertools
import json
import os
import re
import sys
import time
import unittest
from typing import Dict, List

sys.dont_write_bytecode = True

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "scoring"

from state_tracker.v3 import rule_table as RT                         # noqa: E402  (also sets up the runner path)
from method_tgr.rules import to_aspm                                  # noqa: E402  (runner copy)
from method_tgr.runtime import TGRConfig                              # noqa: E402  (runner copy)
from repro_runtime import mln                                         # noqa: E402  (runner copy)

from state_tracker import paths                                       # noqa: E402

CFG = TGRConfig()                                   # TGR's defaults: epsilon 0.1, gibbs_threshold 16
REPORT = os.path.join(RT.OUT_DIR, "p2_rule_table.md")
RULE_TABLE_PY = os.path.join(paths.STATE_TRACKER_DIR, "v3", "rule_table.py")
EXTRA_NAMES = ("tau_bench", "tau-bench", "τ-bench", "taubench")
# the plan's expected rule counts by fact count (p2.md, "Why it is easy")
EXPECTED_BY_FACTS = {"retail": {"1": 60, "2": 4}, "airline": {"1": 22, "2": 10, "3": 1, "6": 1}}


def decide_allows(aspm, rule_id: str, action: str, values: Dict[str, bool]) -> bool:
    """TGR's decision (method_tgr.runtime.TGR._step) for one pending action, with this rule as the only rule."""
    current = {a: a == action for a in aspm.action_predicates}
    current.update(values)
    d = mln.decide(aspm, [rule_id], action, current, [], CFG.epsilon, CFG.gibbs_threshold)
    if d["group_unknowns"]:
        raise AssertionError(f"rule {rule_id}: unknown predicates {d['group_unknowns']} in a fully set check")
    return bool(d["allowed"])


def check_table(table: dict, rule_set: dict) -> dict:
    """P2.1 and P2.2 for every row of one table, plus structure and blocking-value checks."""
    aspm = to_aspm(rule_set)
    c = {"rows": 0, "hold_rows": 0, "hold_allow_pass": 0, "failing_rows": 0, "block_pass": 0,
         "flip_sets": 0, "flip_allow_pass": 0, "bf_subsets": 0, "bf_unlisted": 0, "bf_unlisted_pass": 0,
         "bf_listed_minimal_pass": 0, "structure_errors": [], "failures": [], "blocking_errors": [],
         "polarity_disagreements": []}
    tabled = {e["id"] for e in table["rules"]} | {s["id"] for s in table["skipped"]}
    if tabled != {r["id"] for r in rule_set["rules"]}:
        c["structure_errors"].append("the table does not cover every rule exactly once")
    for e in table["rules"]:
        rid, facts = e["id"], e["facts"]
        r = aspm.rules[rid]
        if facts != sorted(r.atoms - aspm.action_predicates):
            c["structure_errors"].append(f"rule {rid}: facts differ from the judge's names")
        acts = sorted(a for a, ids in aspm.circuits.items() if rid in ids)
        if e["actions"] != acts:
            c["structure_errors"].append(f"rule {rid}: actions differ from the circuits")
        want = [(a, tuple(bits)) for a in acts for bits in itertools.product((False, True), repeat=len(facts))]
        got = [(row["action"], tuple(row["values"][f] for f in facts)) for row in e["rows"]]
        if got != want or any(sorted(row["values"]) != facts for row in e["rows"]):
            c["structure_errors"].append(f"rule {rid}: rows are not every combination once, in order")
        blocking = {f: set() for f in facts}
        for row in e["rows"]:
            c["rows"] += 1
            a, values, listed = row["action"], row["values"], [frozenset(s) for s in row["flip_sets"]]
            allowed = decide_allows(aspm, rid, a, values)
            if row["holds"]:
                c["hold_rows"] += 1
                if allowed and not listed:
                    c["hold_allow_pass"] += 1
                else:
                    c["failures"].append(f"rule {rid} {a} {values}: holds in the table, decide allowed={allowed}")
                continue
            c["failing_rows"] += 1
            if not allowed:
                c["block_pass"] += 1
            else:
                c["failures"].append(f"rule {rid} {a} {values}: fails in the table, but decide allows")
            for s in listed:
                c["flip_sets"] += 1
                for f in s:
                    blocking[f].add(values[f])
                if decide_allows(aspm, rid, a, RT.flip(values, s)):
                    c["flip_allow_pass"] += 1
                else:
                    c["failures"].append(f"rule {rid} {a} {values}: flip set {sorted(s)} does not allow")
            # P2.2: every set of facts, decided by mln.decide
            allows = {}
            for size in range(0, len(facts) + 1):
                for sub in itertools.combinations(facts, size):
                    allows[frozenset(sub)] = decide_allows(aspm, rid, a, RT.flip(values, sub))
                    c["bf_subsets"] += 1
            for s, ok in allows.items():
                if s in listed:
                    continue
                c["bf_unlisted"] += 1
                if not ok or any(t < s for t in listed):
                    c["bf_unlisted_pass"] += 1
                else:
                    c["failures"].append(f"rule {rid} {a} {values}: missing flip set {sorted(s)}")
            for s in listed:
                if not any(allows[t] for t in allows if t < s):
                    c["bf_listed_minimal_pass"] += 1
                else:
                    c["failures"].append(f"rule {rid} {a} {values}: flip set {sorted(s)} is not smallest")
        for f in facts:
            if sorted(blocking[f]) != e["blocking_values"][f]:
                c["blocking_errors"].append(f"rule {rid} {f}: blocking values differ from the flip sets")
            pol = e["polarity"][f]
            allowed_values = {"positive": {False}, "negative": {True}, "both": {False, True}}[pol]
            if not set(e["blocking_values"][f]) <= allowed_values:
                c["polarity_disagreements"].append(f"rule {rid} {f}: polarity {pol}, blocks with {e['blocking_values'][f]}")
    return c


def generic_names(rule_sets: Dict[str, dict]) -> List[str]:
    names = set(rule_sets) | set(EXTRA_NAMES)
    for rs in rule_sets.values():
        names |= set(rs.get("action_names", [])) | set(rs.get("predicates", {})) | set(rs.get("actions", {}))
        names |= {r["action"] for r in rs.get("rules", []) if r.get("action")}
    return sorted(names)


def generic_hits_text(text: str, names: List[str]) -> List[str]:
    """P2.3: the names that occur in a text as a word (case-insensitive), comments and docstrings included."""
    return [n for n in names if re.search(r"(?<![A-Za-z0-9_])" + re.escape(n) + r"(?![A-Za-z0-9_])", text, re.I)]


def generic_hits(code_path: str, names: List[str]) -> List[str]:
    with open(code_path, encoding="utf-8") as f:
        return generic_hits_text(f.read(), names)


def run_unit_tests() -> dict:
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_v3_rule_table")
    res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    return {"run": res.testsRun, "failures": len(res.failures), "errors": len(res.errors),
            "skipped": len(res.skipped), "ok": res.wasSuccessful()}


def pct(a: int, b: int) -> str:
    return f"{100.0 * a / b:.1f} %" if b else "n/a"


def write_report(summary: dict) -> None:
    d = summary["domains"]
    names = sorted(d)
    L = ["# Tracker v3, part 2: the rule table", "",
         "Written by `scoring/v3_p2_rule_table_check.py` (every number below comes from it). $0: no LLM call.", "",
         "## Files", "", "| file | sha256 |", "|---|---|"]
    for n in names:
        L.append(f"| `{d[n]['table']}` | `{d[n]['table_sha256']}` |")
    for n in names:
        L.append(f"| `{d[n]['source']}` (input, frozen) | `{d[n]['source_sha256']}` |")
    L.append(f"| `state_tracker/v3/rule_table.py` | `{summary['code_sha256']}` |")
    L += ["", "## The table", "",
          "| | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]

    def row(label, key, fmt=str):
        L.append(f"| {label} | " + " | ".join(fmt(d[n][key]) for n in names) + " |")

    row("rules", "rules")
    row("rules by fact count (facts: rules)", "rules_by_fact_count",
        lambda x: ", ".join(f"{k}: {v}" for k, v in sorted(x.items(), key=lambda kv: int(kv[0]))))
    row("as the plan expects", "by_facts_as_expected", lambda x: "yes" if x else "**no**")
    row("rows (action x combination)", "rows")
    row("failing rows (the guard blocks)", "failing_rows")
    row("flip sets listed", "flip_sets")
    row("flip sets by size (size: count)", "flip_sets_by_size",
        lambda x: ", ".join(f"{k}: {v}" for k, v in sorted(x.items(), key=lambda kv: int(kv[0]))))
    row("rules that cannot hold by flipping facts", "cannot_hold_rules", lambda x: str(len(x)))
    row("skipped rules (temporal)", "skipped_rules")
    row("table on disk = fresh build", "file_matches_build", lambda x: "yes" if x else "**no**")
    L += ["", "## Checks (pre-registered, P2.1-P2.4)", "", "| id | check | result | pass mark | pass |",
          "|---|---|---|---|---|"]
    t = summary["totals"]
    L.append(f"| P2.1 | failing combination blocks (`mln.decide`, only this rule, ε = {CFG.epsilon}, θ = 1) | "
             f"{t['block_pass']} / {t['failing_rows']} = {pct(t['block_pass'], t['failing_rows'])} | 100 % | "
             f"{'yes' if t['block_pass'] == t['failing_rows'] else 'NO'} |")
    L.append(f"| P2.1 | combination + listed flip set allows | {t['flip_allow_pass']} / {t['flip_sets']} = "
             f"{pct(t['flip_allow_pass'], t['flip_sets'])} | 100 % | "
             f"{'yes' if t['flip_allow_pass'] == t['flip_sets'] else 'NO'} |")
    L.append(f"| P2.2 | unlisted flip sets: fail or contain a listed set (brute force, {t['bf_subsets']} decisions) | "
             f"{t['bf_unlisted_pass']} / {t['bf_unlisted']} = {pct(t['bf_unlisted_pass'], t['bf_unlisted'])} | 100 % | "
             f"{'yes' if t['bf_unlisted_pass'] == t['bf_unlisted'] else 'NO'} |")
    L.append(f"| P2.2 | listed flip sets are smallest | {t['bf_listed_minimal_pass']} / {t['flip_sets']} = "
             f"{pct(t['bf_listed_minimal_pass'], t['flip_sets'])} | 100 % | "
             f"{'yes' if t['bf_listed_minimal_pass'] == t['flip_sets'] else 'NO'} |")
    g = summary["generic"]
    L.append(f"| P2.3 | rule-set names in `rule_table.py` ({g['names_checked']} names checked) | {len(g['hits'])} | 0 | "
             f"{'yes' if not g['hits'] else 'NO'} |")
    u = summary["unit_tests"]
    L.append(f"| P2.4 | `tests/test_v3_rule_table.py` | {u['run']} run, {u['failures']} failures, {u['errors']} errors | "
             f"pass | {'yes' if u['ok'] else 'NO'} |")
    L.append(f"| extra | holding combination allows | {t['hold_allow_pass']} / {t['hold_rows']} | 100 % | "
             f"{'yes' if t['hold_allow_pass'] == t['hold_rows'] else 'NO'} |")
    L.append(f"| extra | structure, blocking values, polarity | {t['structure_errors']} / {t['blocking_errors']} / "
             f"{t['polarity_disagreements']} errors | 0 | "
             f"{'yes' if not (t['structure_errors'] or t['blocking_errors'] or t['polarity_disagreements']) else 'NO'} |")
    L += ["", "## Blocking values", ""]
    for n in names:
        x = d[n]
        L.append(f"- {n}: {x['facts']} facts in {x['fact_rule_pairs']} (rule, fact) pairs. Pairs that can block "
                 f"with both values: {len(x['pairs_with_two_blocking_values'])}. Pairs with both polarities: "
                 f"{len(x['pairs_with_both_polarities'])}. Pairs that never block: {len(x['pairs_that_never_block'])}. "
                 f"Facts negated in one rule and not in another: "
                 f"{', '.join(x['facts_negated_in_one_rule_and_not_in_another']) or 'none'}. Pairs that block with "
                 f"true / with false: {x['blocking_true']} / {x['blocking_false']}.")
    L += ["", "## Policy sentences (for the p10 quote)", ""]
    for n in names:
        x = d[n]
        L.append(f"- {n}: rules citing no sentence: {len(x['rules_without_cited_sentences'])}; rules citing a "
                 f"sentence id the rule set does not have: {len(x['rules_with_missing_sentence_ids'])}; rules no "
                 f"disposition names: {len(x['rules_without_dispositions'])}; rules named by an `exception` "
                 f"disposition: {', '.join(x['rules_with_an_exception_disposition']) or 'none'}.")
    n_two = sum(len(d[n]["pairs_with_two_blocking_values"]) for n in names)
    n_never = sum(len(d[n]["pairs_that_never_block"]) for n in names)
    one_value = ("Every (rule, fact) pair has exactly one blocking value in these rule sets."
                 if n_two == 0 and n_never == 0 else
                 f"{n_two} (rule, fact) pairs can block with both values and {n_never} never block: p10 must handle "
                 "them.")
    L += ["", "## Notes for p4 and p10", "",
          "- A row is found by (rule id, action, values of the rule's facts). `flip_sets` are all the smallest ways "
          "to make the rule hold; `tipping_facts` is their union (\"these facts made the guard block\").",
          "- `blocking_values[fact]` is the value that breaks the rule (p10 shows it, for example `true` for a "
          "negated fact). " + one_value,
          "- `cited_sentences` copies the rule set's sentence records (id, text, heading) for the policy quote; "
          "`dispositions` says whether the sentence is a `rule` or an `exception` for this rule.",
          "- The table is two-valued (every fact true or false). With an unknown fact, TGR's decision also depends on "
          "the other rules of the circuit; that case is not in the table.", ""]
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def main(argv=None) -> int:
    from state_tracker.v3.frozen import check_manifest
    check_manifest()
    t0 = time.time()
    summary = {"domains": {}, "epsilon": CFG.epsilon, "gibbs_threshold": CFG.gibbs_threshold,
               "code_sha256": RT.sha256_file(RULE_TABLE_PY)}
    rule_sets = {}
    totals: Dict[str, int] = {}
    for name, path in RT.rule_set_paths().items():
        with open(path, encoding="utf-8") as f:
            rule_set = json.load(f)
        rule_sets[name] = rule_set
        fresh = RT.render(RT.build_for_path(path))
        tpath = RT.table_path(name)
        with open(tpath, encoding="utf-8") as f:
            on_disk = f.read()
        table = json.loads(on_disk)
        c = check_table(table, rule_set)
        tc = table["counts"]
        pairs = [(e["id"], f, e["blocking_values"][f]) for e in table["rules"] for f in e["facts"]]
        summary["domains"][name] = dict(
            tc, table=os.path.relpath(tpath, paths.PC_DIR), table_sha256=RT.sha256_bytes(on_disk.encode("utf-8")),
            source=table["source"]["path"], source_sha256=table["source"]["sha256"],
            file_matches_build=(fresh == on_disk),
            by_facts_as_expected=(tc["rules_by_fact_count"] == EXPECTED_BY_FACTS.get(name, tc["rules_by_fact_count"])),
            blocking_true=sum(1 for p in pairs if p[2] == [True]), blocking_false=sum(1 for p in pairs if p[2] == [False]),
            check={k: (len(v) if isinstance(v, list) else v) for k, v in c.items()},
            check_failures=c["failures"][:20] + c["structure_errors"][:20] + c["blocking_errors"][:20]
            + c["polarity_disagreements"][:20])
        for k, v in c.items():
            totals[k] = totals.get(k, 0) + (len(v) if isinstance(v, list) else v)
    summary["totals"] = totals
    names = generic_names(rule_sets)
    summary["generic"] = {"names_checked": len(names), "hits": generic_hits(RULE_TABLE_PY, names)}
    summary["unit_tests"] = run_unit_tests()
    summary["seconds"] = round(time.time() - t0, 1)
    write_report(summary)
    print(json.dumps(summary, indent=1, sort_keys=True, ensure_ascii=False))
    t = totals
    ok = (t["block_pass"] == t["failing_rows"] and t["flip_allow_pass"] == t["flip_sets"]
          and t["bf_unlisted_pass"] == t["bf_unlisted"] and t["bf_listed_minimal_pass"] == t["flip_sets"]
          and t["hold_allow_pass"] == t["hold_rows"] and not summary["generic"]["hits"] and summary["unit_tests"]["ok"]
          and not (t["structure_errors"] or t["blocking_errors"] or t["polarity_disagreements"])
          and all(x["file_matches_build"] for x in summary["domains"].values()))
    print("ALL CHECKS PASS" if ok else "SOME CHECK FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
