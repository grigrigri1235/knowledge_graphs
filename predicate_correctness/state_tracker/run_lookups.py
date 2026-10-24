"""Part 5: smoke run of the lookups on the Part 2 step records. Writes output/p5_smoke.md.

For each step record, the action's rules (frozen rule set: circuits) give the predicates; for each code-type
predicate among them (output/predicate_types.json), its lookup runs on the state before the step (state.walk, one
pass per conversation) with the pending call's arguments (rec["kwargs"]). It counts true / false / unknown per lookup,
how often if_missing was applied and why, and every evaluation error.

It does not read the judge's values or evidence: the predicates come from the rule set, not from rec["judge"]. It
only checks that the lookups run; whether their values are right is the independent check (p5.md subtask 3) and
Part 6.

Run from predicate_correctness/:
    python3 -B -m state_tracker.run_lookups > output/logs/p5_run_lookups.log 2>&1          (all records)
    python3 -B -m state_tracker.run_lookups --sample 200 > ...                              (200 per run and domain)
Standard library only. No LLM calls. Never imports gold code.
"""
from __future__ import annotations

import argparse
import collections
import os
import random
import sys
import time
from typing import Dict, List, Optional

sys.dont_write_bytecode = True

if __package__ in (None, ""):
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    __package__ = "state_tracker"

from state_tracker import paths                                                   # noqa: E402
from state_tracker import lookup_format as L                                        # noqa: E402
from state_tracker.load_steps import read_steps                                     # noqa: E402
from state_tracker.predicate_types import is_code_type, load_rule_set, load_types   # noqa: E402
from state_tracker.state import walk                                                # noqa: E402
from state_tracker.type_counts import logic_predicates                              # noqa: E402

SMOKE_MD = os.path.join(paths.OUTPUT_DIR, "p5_smoke.md")
VALUE_NAME = {True: "true", False: "false", None: "unknown"}


def action_predicates(rule_set: dict) -> Dict[str, List[str]]:
    """action -> predicates in its rules (circuits), in rule order, without repeats."""
    names = rule_set["predicates"]
    rules = {r["id"]: r for r in rule_set["rules"]}
    out: Dict[str, List[str]] = {}
    for action, ids in rule_set["circuits"].items():
        seen: List[str] = []
        for rid in ids:
            for p in sorted(logic_predicates(rules[rid]["logic"], names)):
                if p not in seen:
                    seen.append(p)
        out[action] = seen
    return out


def new_stat() -> dict:
    return {"n": 0, "true": 0, "false": 0, "unknown": 0, "missing": 0, "reasons": collections.Counter(),
            "errors": [], "actions": collections.Counter(), "runs": collections.Counter()}


def run_domain(domain: str, sample: Optional[int], seed: int) -> dict:
    lookups = L.load_lookups(domain)
    problems = L.check_lookups(domain, lookups)
    types = load_types()[domain]
    by_action = action_predicates(load_rule_set(domain))
    stats = {n: new_stat() for n in lookups}
    info = {"records": 0, "records_with_lookup": 0, "episodes": 0, "mismatches": 0, "parse_problems": 0,
            "problems": problems, "per_run": {}}
    for run in paths.RUNS:
        recs = list(read_steps(run, domain))
        total = len(recs)
        if sample is not None and sample < len(recs):
            rng = random.Random(f"{seed}/{run}/{domain}")
            recs = sorted(rng.sample(recs, sample), key=lambda r: (r["episode_line"], r["history_len"]))
        info["per_run"][run] = {"records": total, "used": len(recs)}
        groups: Dict[int, List[dict]] = collections.defaultdict(list)
        for r in recs:
            groups[r["episode_line"]].append(r)
        for line, group in sorted(groups.items()):
            info["episodes"] += 1
            longest = max(group, key=lambda r: r["history_len"])["history"]
            at: Dict[int, List[dict]] = collections.defaultdict(list)
            for r in group:
                at[r["history_len"]].append(r)
            last_state = None
            for n, st in walk(longest, domain=domain, stops=sorted(at)):
                last_state = st
                for rec in at[n]:
                    info["records"] += 1
                    preds = [p for p in by_action.get(rec["action"], []) if is_code_type(types[p]["type"])]
                    if preds:
                        info["records_with_lookup"] += 1
                    for p in preds:
                        s = stats[p]
                        s["n"] += 1
                        s["actions"][rec["action"]] += 1
                        s["runs"][run] += 1
                        try:
                            d = L.evaluate_detail(lookups[p], st, args=rec["kwargs"])
                        except (L.LookupFormatError, L.LookupEvalError, Exception) as e:   # report every error
                            s["errors"].append(f"{rec['step_id']}: {type(e).__name__}: {e}")
                            continue
                        s[VALUE_NAME[d["value"]]] += 1
                        if d["missing"] is not None:
                            s["missing"] += 1
                            s["reasons"][_reason(d["missing"])] += 1
            if last_state is not None:
                info["mismatches"] += len(last_state.mismatches)
                info["parse_problems"] += len(last_state.parse_problems)
    return {"stats": stats, "info": info, "lookups": lookups, "types": types}


def _reason(text: str) -> str:
    """A short class of a missing-value reason: the exception type and the first words of its message."""
    head, _, msg = text.partition(": ")
    if head == "KeyError":
        return f"KeyError {msg}"                     # the missing key
    if head == "TypeError":
        if "NoneType" in msg and "subscriptable" in msg:
            return "TypeError: object not shown / None"
        return "TypeError: " + msg[:70]
    return text[:80]


def _cell(x) -> str:
    return str(x).replace("|", "\\|").replace("\n", " ")


def render(results: Dict[str, dict], sample: Optional[int], seconds: float) -> str:
    out: List[str] = []
    w = out.append
    w("# Part 5: smoke run of the lookups")
    w("")
    w("Written by `state_tracker/run_lookups.py`. It checks that every lookup runs on the saved steps, and counts its")
    w("results. It does **not** say whether the values are right: that is the independent check (p5.md subtask 3)")
    w("and Part 6. The judge's values and evidence were not read; the predicates of a step come from the rule set")
    w("(the action's rules), not from the judge record.")
    w("")
    scope = "all Part 2 step records" if sample is None else f"a random sample of {sample} records per run and domain (seed 0)"
    w(f"- Records: {scope}. State: `state.walk` over each conversation, before the step. Arguments: the pending call's.")
    w(f"- A lookup runs on a record if its predicate is in one of the rules of the record's action.")
    w(f"- `missing` = the lookup's `if_missing` value was used (an object or field was missing, or the result was None).")
    w(f"- Time: {seconds:.0f} s.")
    w("")
    for domain, res in results.items():
        info, stats, lookups, types = res["info"], res["stats"], res["lookups"], res["types"]
        n_err = sum(len(s["errors"]) for s in stats.values())
        w(f"## {domain.capitalize()}")
        w("")
        runs = ", ".join(f"{r}: {v['used']} of {v['records']}" for r, v in info["per_run"].items())
        w(f"- Records used: {info['records']} ({runs}), in {info['episodes']} conversations; "
          f"{info['records_with_lookup']} have at least one code-type predicate.")
        w(f"- Lookup file check: {len(info['problems'])} problems. Evaluation errors: {n_err}. "
          f"Replay mismatches while walking: {info['mismatches']}; parse problems: {info['parse_problems']}.")
        w("")
        w("| predicate | type | uses | if_missing | runs | true | false | unknown | missing | main missing reasons | errors |")
        w("|---|---|---|---|---|---|---|---|---|---|---|")
        for name in lookups:
            s, lk = stats[name], lookups[name]
            reasons = "; ".join(f"{r} ({c})" for r, c in s["reasons"].most_common(3))
            w(f"| `{name}` | {types[name]['type']} | {lk['uses']} | {lk['if_missing']} | {s['n']} | {s['true']} | "
              f"{s['false']} | {s['unknown']} | {s['missing']} | {_cell(reasons)} | {len(s['errors'])} |")
        never = [n for n in lookups if stats[n]["n"] == 0]
        if never:
            w("")
            w(f"Never run (no record of an action that uses them): {', '.join(f'`{n}`' for n in never)}.")
        reads_db = [n for n, lk in lookups.items() if lk["uses"] == "shown" and {"db", "db_all"} & set(L.validate(lk["expr"])["calls"])]
        if reads_db:
            w("")
            w(f"`uses` = shown, but also reads the database copy (see each reason): {', '.join(f'`{n}`' for n in reads_db)}.")
        if info["problems"] or n_err:
            w("")
            w("### Problems and errors")
            for p in info["problems"]:
                w(f"- {_cell(p)}")
            for name, s in stats.items():
                for e in s["errors"][:10]:
                    w(f"- `{name}`: {_cell(e)[:300]}")
                if len(s["errors"]) > 10:
                    w(f"- `{name}`: ... {len(s['errors']) - 10} more")
        w("")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sample", type=int, default=None, help="records per run and domain (default: all)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=SMOKE_MD)
    a = ap.parse_args(argv)
    t0 = time.time()
    results = {d: run_domain(d, a.sample, a.seed) for d in paths.DOMAINS}
    seconds = time.time() - t0
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(render(results, a.sample, seconds))
    bad = 0
    for d, res in results.items():
        n_err = sum(len(s["errors"]) for s in res["stats"].values())
        bad += n_err + len(res["info"]["problems"]) + res["info"]["mismatches"]
        print(f"{d}: records {res['info']['records']}, with lookups {res['info']['records_with_lookup']}, "
              f"errors {n_err}, file problems {len(res['info']['problems'])}, mismatches {res['info']['mismatches']}")
        for name, s in res["stats"].items():
            print(f"   {name}: n={s['n']} true={s['true']} false={s['false']} unknown={s['unknown']} "
                  f"missing={s['missing']} errors={len(s['errors'])}")
    print(f"wrote {a.out} in {seconds:.0f} s")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
