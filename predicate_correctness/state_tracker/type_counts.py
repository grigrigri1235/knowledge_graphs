"""Part 3, subtask 3: counts per predicate type, from the Part 2 step records.

For each run and domain it counts:
  - predicates per type (from output/predicate_types.json);
  - judge values per type (one value = one predicate entry in a step's judge dict), split into true / false / unknown;
  - block-causing values per type: on a blocked step (action_allowed == false), a judge value whose predicate appears
    in the logic of one of the step's violated_rules;
  - the share of blocked steps that involve at least one code-type predicate (argument, database fact, event), that
    is, a code-type predicate in at least one violated rule. This is the upper limit on how many blocks the tracker
    can change. Two more shares are given for context: every violated rule has a code-type predicate (tighter), and a
    code-type predicate was judged at the step at all (wider).

Writes output/p3_type_counts.md. Standard library only. No LLM calls. Never imports gold code.

Run from predicate_correctness/:  python3 -B -m state_tracker.type_counts > output/logs/p3_type_counts.log 2>&1
"""
from __future__ import annotations

import collections
import hashlib
import os
import sys
from typing import Dict, Iterable, List, Set

sys.dont_write_bytecode = True                      # never write __pycache__ next to the copies

if __package__ in (None, ""):                       # run as a file: python3 state_tracker/type_counts.py
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    __package__ = "state_tracker"

from state_tracker import paths                                         # noqa: E402
from state_tracker.load_steps import AGENT_LABEL, EXPECTED, read_steps  # noqa: E402
from state_tracker.predicate_types import (CODE_TYPES, TYPES, TYPES_JSON, load_meta,  # noqa: E402
                                           load_types)

COUNTS_MD = os.path.join(paths.OUTPUT_DIR, "p3_type_counts.md")
VALUES = (True, False, None)
VALUE_NAME = {True: "true", False: "false", None: "unknown"}


def logic_predicates(logic: str, names: Iterable[str]) -> Set[str]:
    """The predicates (from `names`) that occur in a rule's logic text (token match, as in predicate_types)."""
    tokens = set(logic.replace("(", " ").replace(")", " ").split())
    return tokens & set(names)


def step_info(rec: dict, types_dom: Dict[str, dict]) -> dict:
    """Per-step facts used by the counts."""
    rules = [logic_predicates(r["logic"], types_dom) for r in rec.get("violated_rules") or []]
    causing = set().union(*rules) if rules else set()
    code = {n for n, e in types_dom.items() if e["type"] in CODE_TYPES}
    return {
        "blocked": rec["action_allowed"] is False,
        "rules": rules,
        "causing": causing,
        "any_code": bool(causing & code),
        "all_rules_code": bool(rules) and all(r & code for r in rules),
        "judged_code": bool(set(rec["judge"]) & code),
    }


def count_run(recs: Iterable[dict], types_dom: Dict[str, dict]) -> dict:
    """All counts for one run and domain."""
    c = {
        "steps": 0, "blocked": 0, "blocked_ran": 0,
        "values": collections.Counter(),          # (type, value name) -> judge values
        "causing": collections.Counter(),         # (type, value name) -> block-causing values
        "causing_pred": collections.Counter(),    # predicate -> block-causing values
        "blocked_type": collections.Counter(),    # type -> blocked steps with >= 1 block-causing value of that type
        "any_code": 0, "all_rules_code": 0, "judged_code": 0,
        "problems": collections.Counter(),
    }
    for rec in recs:
        c["steps"] += 1
        info = step_info(rec, types_dom)
        for name, entry in rec["judge"].items():
            if name not in types_dom:
                c["problems"]["judged predicate has no type"] += 1
                continue
            c["values"][(types_dom[name]["type"], VALUE_NAME[entry.get("value")])] += 1
        if not info["blocked"]:
            if info["rules"]:
                c["problems"]["allowed step with violated rules"] += 1
            continue
        c["blocked"] += 1
        c["blocked_ran"] += bool(rec.get("executed"))
        if not info["rules"]:
            c["problems"]["blocked step without violated rules"] += 1
        for name in info["causing"]:
            if name not in rec["judge"]:
                c["problems"]["block-causing predicate not judged"] += 1
                continue
            t = types_dom[name]["type"]
            c["causing"][(t, VALUE_NAME[rec["judge"][name].get("value")])] += 1
            c["causing_pred"][name] += 1
        for t in {types_dom[n]["type"] for n in info["causing"]}:
            c["blocked_type"][t] += 1
        c["any_code"] += info["any_code"]
        c["all_rules_code"] += info["all_rules_code"]
        c["judged_code"] += info["judged_code"]
    return c


def merge(cs: List[dict]) -> dict:
    out = {}
    for k, v in cs[0].items():
        if isinstance(v, collections.Counter):
            out[k] = sum((c[k] for c in cs), collections.Counter())
        else:
            out[k] = sum(c[k] for c in cs)
    return out


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:.1f} %" if d else "-"


def _n(x: int) -> str:
    return f"{x:,}"


def by_type(counter: collections.Counter, t: str) -> int:
    return sum(v for (tt, _), v in counter.items() if tt == t)


def render(types: dict, results: Dict[tuple, dict]) -> str:
    rows = list(results)                                           # (run, domain)
    agents = {run: merge([results[(r, d)] for r, d in rows if r == run]) for run in paths.RUNS}
    total = merge(list(results.values()))
    meta = load_meta()
    L: List[str] = [
        "# Part 3: counts per predicate type",
        "",
        "Written by `state_tracker/type_counts.py` from the Part 2 step records (`output/steps_<run>_<domain>.jsonl`)",
        f"and the types in `output/predicate_types.json` (sha256 `{sha256(TYPES_JSON)}`).",
        f"Status of the types: {meta.get('status', 'draft')}",
        "",
        "## Summary",
        f"- **Main metric:** {_n(total['any_code'])} of {_n(total['blocked'])} blocked steps "
        f"({_pct(total['any_code'], total['blocked'])}) involve at least one code-type predicate: "
        + "; ".join(f"{run} {_n(agents[run]['any_code'])} of {_n(agents[run]['blocked'])} "
                    f"({_pct(agents[run]['any_code'], agents[run]['blocked'])})" for run in paths.RUNS) + ".",
        f"- In {_n(total['all_rules_code'])} blocked steps ({_pct(total['all_rules_code'], total['blocked'])}), "
        "every violated rule has a code-type predicate.",
        f"- Code types hold {_pct(sum(by_type(total['values'], t) for t in CODE_TYPES), sum(total['values'].values()))}"
        f" of the judge values and {_pct(sum(by_type(total['causing'], t) for t in CODE_TYPES), sum(total['causing'].values()))}"
        " of the block-causing values. Conversation predicates hold most of the rest.",
        "",
        "## Definitions",
        "- **Code types:** argument, database fact, event (set by code in Parts 4-5). **LLM types:** conversation, mixed.",
        "- **Judge value:** one predicate entry in a step's `judge` dict (true, false or unknown).",
        "- **Blocked step:** a guard check with `action_allowed` = false.",
        "- **Block-causing value:** on a blocked step, a judge value whose predicate appears in the logic of one of the",
        "  step's `violated_rules`. TGR lists there every rule the action breaks in the most likely world, plus every rule",
        "  at risk through an unknown value (`method_tgr/runtime.py`). Allowed steps have no violated rules.",
        "- **Blocked step involves a code type:** at least one of its violated rules has a code-type predicate. Only",
        "  these blocks can change when the tracker replaces code-type values, so the share is an upper limit.",
        "  Two more shares for context:",
        "  - **every violated rule has a code type:** if the conversation and mixed values stay the same, a violated",
        "    rule without a code-type predicate stays violated. So this share is a closer estimate of the blocks the",
        "    tracker could turn into allows;",
        "  - **a code type was judged:** a code-type predicate was among the step's judged predicates at all (wider).",
        "",
        "## 1. Predicates per type",
        "| domain | " + " | ".join(TYPES) + " | code types | total | judged at least once |",
        "|---|" + "---|" * (len(TYPES) + 3),
    ]
    judged_names = {d: set() for d in paths.DOMAINS}
    for (run, dom), c in results.items():
        judged_names[dom] |= set(c["_judged"])
    all_counts = collections.Counter()
    for dom in paths.DOMAINS:
        tc = collections.Counter(e["type"] for e in types[dom].values())
        all_counts += tc
        L.append(f"| {dom} | " + " | ".join(str(tc[t]) for t in TYPES)
                 + f" | {sum(tc[t] for t in CODE_TYPES)} | {sum(tc.values())} | {len(judged_names[dom])} |")
    L.append("| all | " + " | ".join(str(all_counts[t]) for t in TYPES)
             + f" | {sum(all_counts[t] for t in CODE_TYPES)} | {sum(all_counts.values())} |"
             f" {sum(len(v) for v in judged_names.values())} |")
    never = sorted(n for d in paths.DOMAINS for n in types[d] if n not in judged_names[d])
    L += ["", f"Never judged in the saved runs: {', '.join(f'`{n}`' for n in never) or 'none'}.", ""]

    def table(title: str, key: str, note: str) -> None:
        L.extend([title, note, "",
                  "| run, domain | " + " | ".join(TYPES) + " | code types | total |",
                  "|---|" + "---|" * (len(TYPES) + 2)])

        def line(label: str, c: dict) -> str:
            tot = sum(c[key].values())
            cells = [f"{_n(by_type(c[key], t))} ({_pct(by_type(c[key], t), tot)})" for t in TYPES]
            code = sum(by_type(c[key], t) for t in CODE_TYPES)
            return f"| {label} | " + " | ".join(cells) + f" | {_n(code)} ({_pct(code, tot)}) | {_n(tot)} |"
        for (run, dom) in rows:
            L.append(line(f"{run} {dom}", results[(run, dom)]))
        for run in paths.RUNS:
            L.append(line(f"**{run} (both domains)**", agents[run]))
        L.append(line("**all**", total))
        L.append("")

    table("## 2. Judge values per type", "values",
          "Number of judge values (share of the row).")
    L += ["Judge values by value, all runs:", "",
          "| type | true | false | unknown | total |", "|---|---|---|---|---|"]
    for t in TYPES:
        vs = [total["values"][(t, VALUE_NAME[v])] for v in VALUES]
        L.append(f"| {t} | " + " | ".join(_n(x) for x in vs) + f" | {_n(sum(vs))} |")
    L.append("")

    table("## 3. Block-causing values per type", "causing",
          "Number of block-causing values (share of the row).")
    L += ["Block-causing values by value, all runs:", "",
          "| type | true | false | unknown | total |", "|---|---|---|---|---|"]
    for t in TYPES:
        vs = [total["causing"][(t, VALUE_NAME[v])] for v in VALUES]
        L.append(f"| {t} | " + " | ".join(_n(x) for x in vs) + f" | {_n(sum(vs))} |")
    L.append("")

    L += ["## 4. Blocked steps that involve a code-type predicate",
          "Share of blocked steps. \"still ran\": blocked steps that ran anyway through the cap override.", "",
          "| run, domain | blocked steps | still ran | involve a code type (main metric) | every violated rule has a code type"
          " | a code type was judged |",
          "|---|---|---|---|---|---|"]

    def share_line(label: str, c: dict) -> str:
        b = c["blocked"]
        return (f"| {label} | {_n(b)} | {_n(c['blocked_ran'])} | {_n(c['any_code'])} ({_pct(c['any_code'], b)}) | "
                f"{_n(c['all_rules_code'])} ({_pct(c['all_rules_code'], b)}) | "
                f"{_n(c['judged_code'])} ({_pct(c['judged_code'], b)}) |")
    for (run, dom) in rows:
        L.append(share_line(f"{run} {dom}", results[(run, dom)]))
    for run in paths.RUNS:
        L.append(share_line(f"**{run} (both domains)**", agents[run]))
    L.append(share_line("**all**", total))
    L.append("")

    L += ["Blocked steps with at least one block-causing value of each type (a step can count for several types):", "",
          "| run, domain | blocked steps | " + " | ".join(TYPES) + " |", "|---|---|" + "---|" * len(TYPES)]
    for (run, dom) in rows:
        c = results[(run, dom)]
        L.append(f"| {run} {dom} | {_n(c['blocked'])} | "
                 + " | ".join(f"{_n(c['blocked_type'][t])} ({_pct(c['blocked_type'][t], c['blocked'])})" for t in TYPES)
                 + " |")
    L.append(f"| **all** | {_n(total['blocked'])} | "
             + " | ".join(f"{_n(total['blocked_type'][t])} ({_pct(total['blocked_type'][t], total['blocked'])})"
                          for t in TYPES) + " |")
    L.append("")

    L += ["## 5. Code-type predicates with block-causing values",
          "All runs. Columns: luna airline, luna retail, nano airline, nano retail.", "",
          "| domain | predicate | type | " + " | ".join(f"{r.split('_')[0]} {d}" for r, d in rows) + " | total |",
          "|---|---|---|" + "---|" * (len(rows) + 1)]
    for dom in paths.DOMAINS:
        for name, e in types[dom].items():
            if e["type"] not in CODE_TYPES:
                continue
            per = [results[(r, d)]["causing_pred"][name] if d == dom else 0 for r, d in rows]
            if sum(per):
                L.append(f"| {dom} | `{name}` | {e['type']} | " + " | ".join(_n(x) for x in per)
                         + f" | {_n(sum(per))} |")
    L.append("")

    L += ["## 6. Checks", "",
          "| run, domain | steps | judge values (expected) | blocked (expected) | problems |",
          "|---|---|---|---|---|"]
    for (run, dom) in rows:
        c = results[(run, dom)]
        exp = EXPECTED[(run, dom)]
        probs = ", ".join(f"{k}: {v}" for k, v in sorted(c["problems"].items())) or "0"
        L.append(f"| {run} {dom} | {_n(c['steps'])} | {_n(sum(c['values'].values()))} ({_n(exp['judge_values'])}) | "
                 f"{_n(c['blocked'])} ({_n(exp['blocked'])}) | {probs} |")
    models = {run: (sorted(agents[run]["_agent_models"]), sorted(agents[run]["_guard_models"])) for run in paths.RUNS}
    L += ["", "Models in the step records: " + "; ".join(
        f"{run} ({AGENT_LABEL[run]}): agent {', '.join(map(str, a))}, guard {', '.join(map(str, g))}"
        for run, (a, g) in models.items()) + ".", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    types = load_types()
    results = {}
    ok = True
    for run, dom in paths.RUN_DOMAINS:
        recs = list(read_steps(run, dom, with_history=False))
        c = count_run(recs, types[dom])
        c["_judged"] = collections.Counter(n for r in recs for n in r["judge"])
        c["_agent_models"] = collections.Counter(r.get("agent_model") for r in recs)
        c["_guard_models"] = collections.Counter(r.get("guard_model") for r in recs)
        results[(run, dom)] = c
        exp = EXPECTED[(run, dom)]
        nv = sum(c["values"].values())
        good = nv == exp["judge_values"] and c["blocked"] == exp["blocked"] and not c["problems"]
        ok &= good
        print(f"{run} {dom}: steps {c['steps']}, judge values {nv} (exp {exp['judge_values']}), blocked "
              f"{c['blocked']} (exp {exp['blocked']}), involve code {c['any_code']}, all rules code "
              f"{c['all_rules_code']}, judged code {c['judged_code']}, problems {dict(c['problems'])}"
              f" -> {'OK' if good else 'MISMATCH'}")
    text = render(types, results)
    with open(COUNTS_MD, "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote", COUNTS_MD)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
