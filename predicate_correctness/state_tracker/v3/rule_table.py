"""Tracker v3, part 2: the rule table (docs/planning/tracker_v3/p2.md).

For every rule of a TGR rule set and every true/false combination of its facts: does the rule hold? If not, every
smallest set of facts that, flipped, makes it hold. The table is read by the decision audit (p4: "these facts made
the guard block") and by the block messages (p10: "this fact is not met; this makes it true").

Generic: only the rule set's own fields are read (rules, action_names, predicates, circuits, sentences,
dispositions), so the same code runs on any TGR rule set. No tool, fact or domain name appears in this file.

TGR's own code, from the runner copy (made importable by guard/runner_path.py; nothing in the copy is edited):
  - the rule set as TGR's runtime sees it: method_tgr.rules.to_aspm (parsed logic, action predicates, circuits);
  - the facts of a rule: its atoms minus the action predicates, i.e. the names the judge sets
    (method_tgr.runtime.TGR._step: names = atoms of the circuit's rules - aspm.action_predicates);
  - the actions a rule applies to: the circuits that list it (TGR._step: circuit = aspm.circuit(matched));
  - whether a rule holds: repro_runtime.verify.rule_value at the decision step, with the pending action true and every
    other action predicate false (TGR._step: current = {a: a in matched}); a rule is broken only if its value is
    False, as in repro_runtime.mln.
One pending action at a time, as TGR with tool grounding (flag a). A rule with a temporal operator depends on earlier
steps, so it is not tabled; it is listed under "skipped".

Each tabled rule:
  id, rule (all its fields as the rule set gives them), facts, n_facts, actions, n_combinations (2 ** n_facts, per
  action), n_rows;
  cited_sentences: the sentence records the rule cites (copied from the rule set's "sentences"; p10 quotes them),
  missing_sentence_ids, dispositions (the sentences whose disposition names this rule);
  polarity per fact (from the parse tree: an odd number of NOTs and IMPLIES left sides above it is "negative"):
  "positive" / "negative" / "both";
  blocking_values per fact: the values with which the fact can make the rule fail, i.e. the values it has in some
  failing combination where it is in a smallest flip set ([] if it never matters);
  cannot_hold: the actions for which no combination makes the rule hold (only the action itself is forbidden);
  rows: one per action and combination, in a fixed order (actions sorted; combinations with the first fact as the
  most significant bit, all-false first): action, values, holds, flip_sets (every smallest set, ordered by size, then
  by names; [] when the rule holds), tipping_facts (the union of the flip sets).

The table also has "counts" (rules by fact count, rows, failing rows, flip sets, the blocking-value findings, rules
that cannot hold, sentence and disposition gaps) and "source" (the rule set's path and sha256).

Output (deterministic: sorted keys, stable order): output/eval_v3/rule_table_<name>.json, one per
<rules dir>/<name>/rule_set.json. main() first checks the eval v2 manifest (state_tracker/v3/frozen.py).

Standard library only. Run from predicate_correctness/:
    python3 -B -m state_tracker.v3.rule_table > output/logs/<log> 2>&1
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import sys
from typing import Callable, Dict, Iterable, List, Sequence

sys.dont_write_bytecode = True

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    __package__ = "state_tracker.v3"

from guard import runner_path                                   # noqa: E402

runner_path.setup()

from method_tgr.rules import to_aspm                            # noqa: E402  (runner copy)
from repro_runtime.verify import rule_value                     # noqa: E402  (runner copy)

from state_tracker import paths                                 # noqa: E402

VERSION = 1
OUT_DIR = os.path.join(paths.OUTPUT_DIR, "eval_v3")
TABLE_FILE = "rule_table_{}.json"
RULE_SET_FILE = "rule_set.json"
POLARITY = {frozenset({1}): "positive", frozenset({-1}): "negative", frozenset({1, -1}): "both"}
ROW_ORDER = ("actions sorted; per action every combination of the facts (sorted names), the first fact as the most "
             "significant bit, all-false first")


# ---------------------------------------------------------------- logic

def polarity(tree) -> Dict[str, set]:
    """Atom -> signs it occurs with (+1 / -1): NOT and the left side of IMPLIES flip the sign."""
    out: Dict[str, set] = {}

    def walk(n, sign):
        op = n[0]
        if op == "atom":
            out.setdefault(n[1], set()).add(sign)
        elif op == "const":
            return
        elif op == "NOT":
            walk(n[1], -sign)
        elif op == "IMPLIES":
            walk(n[1], -sign)
            walk(n[2], sign)
        else:
            for child in n[1:]:
                walk(child, sign)

    walk(tree, 1)
    return out


def holds(formula, action_predicates: Iterable[str], action: str, values: Dict[str, bool]) -> bool:
    """The rule's value at the decision step (TGR's own evaluation), counted as broken only if False."""
    current = {a: a == action for a in action_predicates}
    current.update(values)
    return rule_value(formula, [current]) is not False


def flip(values: Dict[str, bool], names: Iterable[str]) -> Dict[str, bool]:
    out = dict(values)
    for n in names:
        out[n] = not out[n]
    return out


def smallest_flip_sets(test: Callable[[Dict[str, bool]], bool], facts: Sequence[str],
                       values: Dict[str, bool]) -> List[List[str]]:
    """Every smallest set of facts that, flipped, makes `test` true (sizes 1..n; a set that contains a smaller found
    set is not smallest). Ordered by size, then by names."""
    found: List[set] = []
    for size in range(1, len(facts) + 1):
        for subset in itertools.combinations(sorted(facts), size):
            s = set(subset)
            if any(f <= s for f in found):
                continue
            if test(flip(values, subset)):
                found.append(s)
    return [sorted(s) for s in found]


def combinations(facts: Sequence[str]) -> List[Dict[str, bool]]:
    return [dict(zip(facts, bits)) for bits in itertools.product((False, True), repeat=len(facts))]


# ---------------------------------------------------------------- the table

def _id_key(rule_id: str):
    return (0, int(rule_id), "") if str(rule_id).isdigit() else (1, 0, str(rule_id))


def rule_entry(rule: dict, aspm, sentences: Dict[str, dict], dispositions: Sequence[dict]) -> dict:
    rid = rule["id"]
    r = aspm.rules[rid]
    facts = sorted(r.atoms - aspm.action_predicates)
    actions = sorted(a for a, ids in aspm.circuits.items() if rid in ids)
    signs = polarity(r.formula.tree)
    blocking = {f: set() for f in facts}
    rows, cannot_hold = [], []
    for a in actions:
        def test(v, a=a):
            return holds(r.formula, aspm.action_predicates, a, v)
        any_holds = False
        for values in combinations(facts):
            ok = test(values)
            any_holds |= ok
            sets = [] if ok else smallest_flip_sets(test, facts, values)
            for s in sets:
                for f in s:
                    blocking[f].add(values[f])
            rows.append({"action": a, "values": values, "holds": ok, "flip_sets": sets,
                         "tipping_facts": sorted({f for s in sets for f in s})})
        if not any_holds:
            cannot_hold.append(a)
    cited = [s for s in rule.get("sentences", []) if s in sentences]
    return {
        "id": rid,
        "rule": rule,
        "facts": facts,
        "n_facts": len(facts),
        "actions": actions,
        "n_combinations": 2 ** len(facts),
        "n_rows": len(rows),
        "cited_sentences": [sentences[s] for s in cited],
        "missing_sentence_ids": [s for s in rule.get("sentences", []) if s not in sentences],
        "dispositions": [{"sentence": d.get("sentence"), "disposition": d.get("disposition")}
                         for d in dispositions if rid in d.get("rule_ids", [])],
        "polarity": {f: POLARITY[frozenset(signs[f])] for f in facts},
        "blocking_values": {f: sorted(blocking[f]) for f in facts},
        "cannot_hold": cannot_hold,
        "rows": rows,
    }


def counts(rules: Sequence[dict], skipped: Sequence[dict]) -> dict:
    by_n: Dict[str, int] = {}
    sizes: Dict[str, int] = {}
    fact_signs: Dict[str, set] = {}
    fact_blocking: Dict[str, set] = {}
    rows = failing = flip_sets = 0
    two_values, both_polarity, never_matters = [], [], []
    for e in rules:
        by_n[str(e["n_facts"])] = by_n.get(str(e["n_facts"]), 0) + 1
        rows += len(e["rows"])
        for row in e["rows"]:
            if not row["holds"]:
                failing += 1
                flip_sets += len(row["flip_sets"])
                for s in row["flip_sets"]:
                    sizes[str(len(s))] = sizes.get(str(len(s)), 0) + 1
        for f in e["facts"]:
            fact_signs.setdefault(f, set()).add(e["polarity"][f])
            fact_blocking.setdefault(f, set()).update(e["blocking_values"][f])
            if len(e["blocking_values"][f]) > 1:
                two_values.append([e["id"], f])
            if e["polarity"][f] == "both":
                both_polarity.append([e["id"], f])
            if not e["blocking_values"][f]:
                never_matters.append([e["id"], f])
    return {
        "rules": len(rules),
        "skipped_rules": len(skipped),
        "rules_by_fact_count": by_n,
        "rows": rows,
        "failing_rows": failing,
        "flip_sets": flip_sets,
        "flip_sets_by_size": sizes,
        "cannot_hold_rules": [e["id"] for e in rules if e["cannot_hold"]],
        "rules_in_no_circuit": [e["id"] for e in rules if not e["actions"]],
        "rules_without_cited_sentences": [e["id"] for e in rules if not e["cited_sentences"]],
        "rules_with_missing_sentence_ids": [e["id"] for e in rules if e["missing_sentence_ids"]],
        "rules_without_dispositions": [e["id"] for e in rules if not e["dispositions"]],
        "rules_with_an_exception_disposition": [e["id"] for e in rules
                                                if any(d["disposition"] == "exception" for d in e["dispositions"])],
        "facts": len(fact_signs),
        "fact_rule_pairs": sum(e["n_facts"] for e in rules),
        "pairs_with_two_blocking_values": two_values,
        "pairs_with_both_polarities": both_polarity,
        "pairs_that_never_block": never_matters,
        "facts_negated_in_one_rule_and_not_in_another": sorted(f for f, s in fact_signs.items() if len(s) > 1),
        "facts_with_different_blocking_values_across_rules": sorted(f for f, s in fact_blocking.items() if len(s) > 1),
    }


def build_table(rule_set: dict) -> dict:
    aspm = to_aspm(rule_set)
    sentences = {s["id"]: s for s in rule_set.get("sentences", [])}
    dispositions = rule_set.get("dispositions", [])
    rules, skipped = [], []
    for rule in sorted(rule_set["rules"], key=lambda x: _id_key(x["id"])):
        if aspm.rules[rule["id"]].formula.has_temporal:
            skipped.append({"id": rule["id"], "reason": "temporal operator: the value depends on earlier steps"})
            continue
        rules.append(rule_entry(rule, aspm, sentences, dispositions))
    return {"version": VERSION, "row_order": ROW_ORDER, "rules": rules, "skipped": skipped,
            "counts": counts(rules, skipped)}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    with open(path, "rb") as f:
        return sha256_bytes(f.read())


def build_for_path(rule_set_path: str) -> dict:
    with open(rule_set_path, encoding="utf-8") as f:
        rule_set = json.load(f)
    table = build_table(rule_set)
    table["source"] = {"path": os.path.relpath(rule_set_path, paths.PC_DIR), "sha256": sha256_file(rule_set_path)}
    return table


def render(table: dict) -> str:
    return json.dumps(table, sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def rule_set_paths(rules_dir: str = paths.RULES_DIR) -> Dict[str, str]:
    """name -> <rules_dir>/<name>/rule_set.json, for every sub-folder that has one."""
    out = {}
    for name in sorted(os.listdir(rules_dir)):
        p = os.path.join(rules_dir, name, RULE_SET_FILE)
        if os.path.isfile(p):
            out[name] = p
    return out


def table_path(name: str, out_dir: str = OUT_DIR) -> str:
    return os.path.join(out_dir, TABLE_FILE.format(name))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Write the rule table of every TGR rule set.")
    ap.add_argument("--rules-dir", default=paths.RULES_DIR)
    ap.add_argument("--out-dir", default=OUT_DIR)
    args = ap.parse_args(argv)
    from state_tracker.v3.frozen import check_manifest
    check_manifest()
    os.makedirs(args.out_dir, exist_ok=True)
    for name, path in rule_set_paths(args.rules_dir).items():
        text = render(build_for_path(path))
        out = table_path(name, args.out_dir)
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        c = json.loads(text)["counts"]
        print(json.dumps({"rule_set": name, "table": os.path.relpath(out, paths.PC_DIR),
                          "sha256": sha256_bytes(text.encode("utf-8")), "rules": c["rules"],
                          "rules_by_fact_count": c["rules_by_fact_count"], "rows": c["rows"],
                          "failing_rows": c["failing_rows"], "flip_sets": c["flip_sets"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
