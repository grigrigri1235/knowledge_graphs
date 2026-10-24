"""Part 8: effect on decisions. Run TGR's decision again with the tracker's values for the code-type predicates.

For every Part 2 step record (a saved guard check with a judge):
  1. Check 1: rebuild TGR's input from the saved guard record and run the copied decision code
     (repro_runtime/mln.py::decide, ε = 0.1, all weights 1, rules from state_tracker/tgr_to_aspm.py). It must give
     the saved allow/block and the saved margin on every step, both with the guard's past trace and with an empty one.
  2. Replace the judge's values of the code-type predicates by the tracker's values (output/p6_values.jsonl) and
     decide again, in two versions that differ only where the tracker gives unknown:
       (a) a tracker unknown stays unknown;
       (b) a tracker unknown is replaced by the judge's value.
  3. Count blocks removed and added per run, domain and predicate.
  4. Part 7: where the reviewed items (output/p7_key.json + output/p7_review_answers.json) cover every disagreeing
     value of a step, decide once more with the reviewer's correct values. That is the reference decision. A change
     fixes an error when the new decision equals the reference, and adds one when the saved decision did.
  5. Choose the version for Part 10 (CHOICE_RULE) and write output/p8_decision_changes.md and output/p8_changes.jsonl.

TGR's input, as in ~/ShieldAgent/method_tgr/runtime.py::_step (read only):
  current = {action: action in matched, for every action of the rule set} + {predicate: judge value};
  per matched action: mln.decide(aspm, circuit, action, current, past, 0.1, 16); allowed iff every action is allowed;
  margin = the smallest margin. `past` is the guard's trace of earlier executed steps.

Run from predicate_correctness/:
    python3 -B -m state_tracker.decide_again > output/logs/p8_decide_again.log 2>&1
Standard library only. No LLM calls. Never imports gold code. Reads the Part 7 key and answers only to score.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time
from typing import Dict, Iterable, List, Optional, Tuple

sys.dont_write_bytecode = True

if __package__ in (None, ""):
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    __package__ = "state_tracker"

from state_tracker import paths                                    # noqa: E402
from state_tracker.load_steps import read_steps                    # noqa: E402
from state_tracker.tgr_to_aspm import load_rule_set, to_aspm       # noqa: E402
from repro_runtime import mln                                      # noqa: E402  (copy; path set by tgr_to_aspm)

EPSILON = 0.1                # TGR's ε (saved in every guard record)
GIBBS_THRESHOLD = 16         # TGR's gibbs_threshold
MARGIN_TOL = 1e-9

VALUES_JSONL = os.path.join(paths.OUTPUT_DIR, "p6_values.jsonl")
KEY_JSON = os.path.join(paths.OUTPUT_DIR, "p7_key.json")
ANSWERS_JSON = os.path.join(paths.OUTPUT_DIR, "p7_review_answers.json")
CHANGES_JSONL = os.path.join(paths.OUTPUT_DIR, "p8_changes.jsonl")
RESULT_MD = os.path.join(paths.OUTPUT_DIR, "p8_decision_changes.md")

VERSIONS = ("a", "b")
VERSION_TEXT = {"a": "(a) tracker unknown stays unknown", "b": "(b) tracker unknown -> judge's value"}
VALUE_NAME = {True: "true", False: "false", None: "unknown"}
ALL_READINGS = "all readings at once"
NAME_VALUE = {"true": True, "false": False, "unknown": None}

# Written before the first run (p8.md: "the version with fewer wrong blocks (using Part 7)").
CHOICE_RULE = ("1. fewer wrong blocks (blocked, but the reference decision allows) on the records whose reference is "
               "known; 2. if tied, fewer wrong decisions in all (wrong blocks + wrong allows); 3. if still tied, "
               "version (b), because it never turns a value the judge gave into unknown (review_before_implementation.md, "
               "H2: more unknowns tend to mean more blocks).")


# ----------------------------------------------------------------------------------------------- decision

def judge_values(rec: dict) -> Dict[str, Optional[bool]]:
    """The judge's value of every predicate of the step (None = unknown)."""
    return {n: v.get("value") for n, v in rec["judge"].items()}


def current_of(aspm, rec: dict, values: Dict[str, Optional[bool]]) -> Dict[str, Optional[bool]]:
    """TGR's `current`: the action predicates (true for the matched action) plus the predicate values."""
    cur = {a: (a in rec["matched"]) for a in aspm.action_predicates}
    cur.update(values)
    return cur


def decide(aspm, rec: dict, values: Dict[str, Optional[bool]], past: Optional[list] = None) -> dict:
    """TGR's decision for the step with these predicate values."""
    cur = current_of(aspm, rec, values)
    per = [mln.decide(aspm, rec["circuit"], a, cur, list(past or []), EPSILON, GIBBS_THRESHOLD) for a in rec["matched"]]
    if not per:
        return {"allowed": True, "margin": None}
    return {"allowed": all(d["allowed"] for d in per), "margin": min(d["margin"] for d in per)}


def replaced(judge: Dict[str, Optional[bool]], tracker: Dict[str, Optional[bool]], version: str) -> Dict[str, Optional[bool]]:
    """The judge's values with the code-type values replaced by the tracker's. Version (b) keeps the judge's value
    where the tracker gives unknown."""
    if version not in VERSIONS:
        raise ValueError(version)
    out = dict(judge)
    for n, t in tracker.items():
        if t is None and version == "b":
            continue
        out[n] = t
    return out


def differing(old: Dict[str, Optional[bool]], new: Dict[str, Optional[bool]]) -> List[str]:
    """Predicates whose value differs (None, True and False are three different values)."""
    return sorted(n for n in new if new[n] is not old.get(n))


def change_kind(saved_allowed: bool, new_allowed: bool) -> Optional[str]:
    if saved_allowed == new_allowed:
        return None
    return "block removed" if new_allowed else "block added"


def judge_by_reference(old_allowed: bool, new_allowed: bool, ref_allowed: Optional[bool]) -> Optional[str]:
    """For a changed decision: 'fixes an error' (the new decision equals the reference), 'adds an error' (the saved one
    did), or None when the reference is not known."""
    if ref_allowed is None or old_allowed == new_allowed:
        return None
    return "fixes an error" if new_allowed == ref_allowed else "adds an error"


# ----------------------------------------------------------------------------------------------- inputs

def load_tracker(path: str = VALUES_JSONL) -> Dict[str, Dict[str, dict]]:
    """step_id -> predicate -> the Part 6 line (tracker_value, judge_value, type, agreement, group, ...)."""
    out: Dict[str, Dict[str, dict]] = collections.defaultdict(dict)
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            out[r["step_id"]][r["predicate"]] = r
    return dict(out)


def load_review(key_path: str = KEY_JSON, answers_path: str = ANSWERS_JSON) -> Dict[Tuple[str, str], dict]:
    """(step_id, predicate) -> {id, correct, reading, stratum, tracker_ok, judge_ok} from the Part 7 key and answers."""
    with open(key_path, encoding="utf-8") as f:
        key = json.load(f)
    with open(answers_path, encoding="utf-8") as f:
        answers = json.load(f)
    out = {}
    for it in key["items"]:
        ans = answers[it["id"]]
        correct = NAME_VALUE[ans["correct_value"]]
        out[(it["step_id"], it["predicate"])] = {
            "id": it["id"], "correct": correct, "reading": ans.get("reading"), "stratum": it["stratum"],
            "tracker_ok": it["tracker_value"] is correct, "judge_ok": it["judge_value"] is correct}
    return out


# ----------------------------------------------------------------------------------------------- one record

def process_record(aspm, rec: dict, tracker_lines: Dict[str, dict], review: Dict[Tuple[str, str], dict]) -> dict:
    sid = rec["step_id"]
    saved = rec["action_allowed"]
    jv = judge_values(rec)
    out = {"step_id": sid, "run": rec["run"], "domain": rec["domain"], "task": rec["task"], "trial": rec["trial"],
           "exec_step": rec["exec_step"], "attempt": rec["attempt"], "action": rec["action"],
           "saved_allowed": saved, "saved_margin": rec["margin"], "executed": rec["executed"],
           "cap_override": rec["cap_override"]}

    # Check 1
    cur = current_of(aspm, rec, jv)
    d_past = decide(aspm, rec, jv, rec["past_trace"])
    d_empty = decide(aspm, rec, jv, [])
    out["check"] = {
        "current_equals_trace_position": cur == rec["trace_position"],
        "past_allowed_ok": d_past["allowed"] == saved,
        "past_margin_ok": abs(d_past["margin"] - rec["margin"]) <= MARGIN_TOL,
        "empty_allowed_ok": d_empty["allowed"] == saved,
        "empty_margin_ok": abs(d_empty["margin"] - rec["margin"]) <= MARGIN_TOL,
        "past_equals_empty": d_past["allowed"] == d_empty["allowed"] and d_past["margin"] == d_empty["margin"],
        "judge_matches_p6": all(line["judge_value"] is jv.get(n) for n, line in tracker_lines.items()),
    }

    tv = {n: line["tracker_value"] for n, line in tracker_lines.items()}
    disagree = differing(jv, tv)                       # every code-type value where tracker and judge differ
    out["disagree"] = disagree
    out["tracker_unknown"] = [n for n in disagree if tv[n] is None]
    out["groups"] = {n: tracker_lines[n].get("group") for n in disagree}

    # reference decision from the Part 7 review
    reviewed = [n for n in disagree if (sid, n) in review]
    if not disagree:
        ref, ref_basis = saved, "no disagreement"
    elif len(reviewed) == len(disagree):
        ref_vals = dict(jv)
        for n in disagree:
            ref_vals[n] = review[(sid, n)]["correct"]
        ref, ref_basis = decide(aspm, rec, ref_vals)["allowed"], "reviewed"
    else:
        ref, ref_basis = None, f"{len(disagree) - len(reviewed)} of {len(disagree)} disagreeing values not reviewed"
    out["reference_allowed"], out["reference_basis"] = ref, ref_basis
    out["review_items"] = [{"predicate": n, **{k: review[(sid, n)][k] for k in ("id", "reading")},
                            "correct": VALUE_NAME[review[(sid, n)]["correct"]]} for n in reviewed]
    # the reference if the person took the other reading: the items that rest on that reading take the judge's value
    out["reference_other_reading"] = {}
    if ref_basis == "reviewed":
        present = sorted({review[(sid, n)]["reading"] for n in disagree if review[(sid, n)]["reading"]})
        for scenario in present + ([ALL_READINGS] if present else []):
            alt = dict(jv)
            for n in disagree:
                rd = review[(sid, n)]["reading"]
                use_judge = rd and (scenario == ALL_READINGS or rd == scenario)
                alt[n] = jv[n] if use_judge else review[(sid, n)]["correct"]
            out["reference_other_reading"][scenario] = decide(aspm, rec, alt)["allowed"]

    for v in VERSIONS:
        vals = replaced(jv, tv, v)
        changed = differing(jv, vals)
        d = d_empty if not changed else decide(aspm, rec, vals)
        kind = change_kind(saved, d["allowed"])
        res = {"allowed": d["allowed"], "margin": d["margin"], "changed_values": changed, "change": kind,
               "verdict": judge_by_reference(saved, d["allowed"], ref)}
        if kind:
            # which single replaced value flips the decision on its own
            res["alone_flips"] = [n for n in changed if decide(aspm, rec, dict(jv, **{n: vals[n]}))["allowed"] != saved]
            res["values"] = {n: {"judge": VALUE_NAME[jv[n]], "tracker": VALUE_NAME[vals[n]]} for n in changed}
        out[v] = res
    return out


def run_all(limit: Optional[int] = None) -> List[dict]:
    tracker = load_tracker()
    review = load_review()
    results = []
    for domain in paths.DOMAINS:
        aspm = to_aspm(load_rule_set(domain))
        for run in paths.RUNS:
            t0, n = time.time(), 0
            for rec in read_steps(run, domain):
                results.append(process_record(aspm, rec, tracker.get(rec["step_id"], {}), review))
                n += 1
                if limit and n >= limit:
                    break
            print(f"{run}/{domain}: {n} records in {time.time() - t0:.1f} s", flush=True)
    return results


# ----------------------------------------------------------------------------------------------- counts

def counts(results: List[dict]) -> dict:
    c: dict = {"check": collections.Counter(), "n": len(results)}
    for r in results:
        for k, ok in r["check"].items():
            c["check"][k + (" ok" if ok else " FAILED")] += 1
    for v in VERSIONS:
        per_rd = collections.defaultdict(collections.Counter)
        per_pred = collections.defaultdict(collections.Counter)
        verdict = collections.Counter()
        wrong = collections.Counter()
        readings = collections.Counter()
        distinct = collections.defaultdict(set)
        for r in results:
            rd = (r["run"], r["domain"])
            res = r[v]
            for key in (rd, ("all", "all")):
                per_rd[key]["records"] += 1
                per_rd[key]["blocked before"] += not r["saved_allowed"]
                per_rd[key]["blocked after"] += not res["allowed"]
                if res["change"]:
                    per_rd[key][res["change"]] += 1
            if res["change"]:
                distinct[res["change"]].add((r["run"], r["domain"], r["task"], r["trial"], r["exec_step"]))
                for n in res["changed_values"]:
                    per_pred[(r["domain"], n)][res["change"]] += 1
                for n in res["alone_flips"]:
                    per_pred[(r["domain"], n)][res["change"] + ", alone"] += 1
                verdict[(res["change"], res["verdict"] or "not covered")] += 1
                if res["verdict"] == "fixes an error":
                    for it in r["review_items"]:
                        if it["reading"]:
                            readings[it["reading"]] += 1
            # wrong decisions against the reference (where it is known)
            ref = r["reference_allowed"]
            if ref is not None:
                for name, allowed in (("saved", r["saved_allowed"]), (v, res["allowed"])):
                    wrong[(name, "known")] += 1
                    if not allowed and ref:
                        wrong[(name, "wrong block")] += 1
                    if allowed and not ref:
                        wrong[(name, "wrong allow")] += 1
        c[v] = {"per_rd": per_rd, "per_pred": per_pred, "verdict": verdict, "wrong": wrong,
                "readings": readings, "distinct": {k: len(s) for k, s in distinct.items()}}
    # the other reading (sensitivity): wrong decisions when the items of a reading take the judge's value
    scenarios = sorted({s for r in results for s in r["reference_other_reading"]}, key=lambda s: (s == ALL_READINGS, s))
    sens = {}
    for s in scenarios:
        x = collections.Counter()
        for r in results:
            ref = r["reference_other_reading"].get(s, r["reference_allowed"])
            if ref is None:
                continue
            for name, allowed in [("saved", r["saved_allowed"])] + [(v, r[v]["allowed"]) for v in VERSIONS]:
                x[(name, "wrong block")] += (not allowed) and ref
                x[(name, "wrong allow")] += allowed and not ref
            x["records with another reference"] += ref != r["reference_allowed"]
        sens[s] = x
    c["sensitivity"] = sens
    c["removed_cap_override"] = sum(1 for r in results if r["a"]["change"] == "block removed" and r["cap_override"])
    c["reference"] = collections.Counter(
        "no disagreement" if r["reference_basis"] == "no disagreement" else
        ("reviewed" if r["reference_basis"] == "reviewed" else "not covered") for r in results)
    c["reference_blocked"] = collections.Counter(
        r["reference_basis"] if r["reference_basis"] in ("no disagreement", "reviewed") else "not covered"
        for r in results if not r["saved_allowed"])
    return c


def choose(c: dict) -> Tuple[str, str]:
    """The version for Part 10, by CHOICE_RULE, and the reason."""
    wb = {v: c[v]["wrong"][(v, "wrong block")] for v in VERSIONS}
    wa = {v: c[v]["wrong"][(v, "wrong allow")] for v in VERSIONS}
    if wb["a"] != wb["b"]:
        v = min(VERSIONS, key=lambda x: wb[x])
        return v, f"rule 1: wrong blocks (a) {wb['a']}, (b) {wb['b']}"
    if wb["a"] + wa["a"] != wb["b"] + wa["b"]:
        v = min(VERSIONS, key=lambda x: wb[x] + wa[x])
        return v, (f"rule 2: wrong blocks tie at {wb['a']}; wrong decisions in all (a) {wb['a'] + wa['a']}, "
                   f"(b) {wb['b'] + wa['b']}")
    return "b", f"rule 3: tie on wrong blocks ({wb['a']}) and on wrong decisions in all ({wb['a'] + wa['a']})"


# ----------------------------------------------------------------------------------------------- report

def _pct(a: int, b: int) -> str:
    return f"{100.0 * a / b:.1f} %" if b else "-"


def write_md(results: List[dict], c: dict, path: str = RESULT_MD) -> str:
    choice, reason = choose(c)
    L: List[str] = []
    w = L.append
    rds = [(r, d) for r, d in paths.RUN_DOMAINS] + [("all", "all")]
    w("# Part 8: effect on decisions")
    w("")
    w("Written by `state_tracker/decide_again.py` (Part 8). Standard library only, no LLM calls.")
    w("")
    w("We run TGR's decision again on each saved guarded step (4,903 records, Part 2). The judge's values of the "
      "code-type predicates are replaced by the tracker's values (Part 6). Everything else stays as TGR had it: the "
      "conversation and mixed values from the judge, the frozen rules, ε = 0.1, all weights 1.")
    w("")
    w("A record is one guard check (one attempt). A step that was blocked several times has several records.")
    w("")
    w("**Limit.** We count only the decision at each saved step. After a changed decision the real conversation "
      "would have gone on differently. Part 10 measures that with new conversations.")
    w("")

    # check 1
    w("## 1. Check: the copied decision code gives the saved decisions")
    w("")
    w("For each record we rebuild TGR's input from the saved guard record: `current` = every action predicate "
      "(true for the matched action) plus the judge's values, and run `repro_runtime/mln.py::decide` with the rules "
      "from `state_tracker/tgr_to_aspm.py`.")
    w("")
    w("| check | records ok | failed |")
    w("|---|---|---|")
    labels = {
        "current_equals_trace_position": "rebuilt `current` equals the saved `trace_position`",
        "past_allowed_ok": "same allow/block as saved (with the guard's past trace)",
        "past_margin_ok": "same margin as saved, within 1e-9 (with the past trace)",
        "empty_allowed_ok": "same allow/block as saved (with an empty past trace)",
        "empty_margin_ok": "same margin as saved, within 1e-9 (empty past trace)",
        "past_equals_empty": "past trace and empty past trace give exactly the same result",
        "judge_matches_p6": "the judge values in Part 6's file equal the guard record",
    }
    for k, lab in labels.items():
        w(f"| {lab} | {c['check'][k + ' ok']:,} | {c['check'][k + ' FAILED']:,} |")
    w("")
    w("No TGR rule has a temporal operator (`tests/test_tgr_to_aspm.py`), so `verify.rule_value` reads only the "
      "current position and the past trace cannot change the result. The table shows this on every record. The "
      "decisions below use an empty past trace.")
    w("")

    # main counts
    w("## 2. Blocks removed and added")
    w("")
    w("The two versions differ only where the tracker gives unknown:")
    w("- **(a)** a tracker unknown stays unknown;")
    w("- **(b)** a tracker unknown is replaced by the judge's value.")
    w("")
    for v in VERSIONS:
        w(f"### Version {VERSION_TEXT[v]}")
        w("")
        w("| run, domain | records | blocked before | blocked after | blocks removed | blocks added | net change |")
        w("|---|---|---|---|---|---|---|")
        for rd in rds:
            p = c[v]["per_rd"][rd]
            name = "**all**" if rd == ("all", "all") else f"{rd[0]} {rd[1]}"
            net = p["blocked after"] - p["blocked before"]
            w(f"| {name} | {p['records']:,} | {p['blocked before']:,} | {p['blocked after']:,} | "
              f"{p['block removed']:,} | {p['block added']:,} | {net:+,} |")
        w("")
        dist = c[v]["distinct"]
        w(f"Distinct steps (task, trial, step; attempts merged): blocks removed {dist.get('block removed', 0):,}, "
          f"blocks added {dist.get('block added', 0):,}.")
        w("")
    diff = [r for r in results if r["a"]["allowed"] != r["b"]["allowed"]]
    w(f"Records where (a) and (b) decide differently: {len(diff)}"
      + (": " + ", ".join(f"`{r['step_id']}`" for r in diff) if diff else "") + ".")
    w("")
    tu = [(r["step_id"], n) for r in results for n in r["tracker_unknown"]]
    w(f"The tracker gives unknown where the judge gave a value in {len(tu)} value(s)"
      + (": " + ", ".join(f"`{n}` at `{s}`" for s, n in tu) if tu else "")
      + ". This is the only place where (a) and (b) differ.")
    w("")
    w(f"Of the {c['a']['per_rd'][('all', 'all')]['block removed']} removed blocks, "
      f"{c['removed_cap_override']} were blocked records that still ran through the cap override. Removed blocks "
      "count each blocked attempt: in the real run, attempts 2 to 4 of a step would not have happened once attempt 1 "
      "was allowed.")
    w("")

    # per predicate
    w("## 3. Per predicate")
    w("")
    w("A changed record can have more than one replaced value, so a record can count under more than one predicate. "
      "\"alone\" = replacing only this predicate's value (all others stay the judge's) already changes the decision.")
    w("")
    for v in VERSIONS:
        w(f"### Version {VERSION_TEXT[v]}")
        w("")
        pp = c[v]["per_pred"]
        if not pp:
            w("No changed decisions.")
            w("")
            continue
        w("| domain | predicate | blocks removed | of these, alone | blocks added | of these, alone |")
        w("|---|---|---|---|---|---|")
        for (d, n), x in sorted(pp.items(), key=lambda kv: (-(kv[1]["block removed"] + kv[1]["block added"]), kv[0])):
            w(f"| {d} | `{n}` | {x['block removed']} | {x['block removed, alone']} | {x['block added']} | "
              f"{x['block added, alone']} |")
        w("")

    # Part 7
    w("## 4. Does a change fix an error or add one? (Part 7)")
    w("")
    w("Reference decision: TGR's decision when every disagreeing code-type value of the record takes the value the "
      "Part 7 reviewer gave as correct (an independent agent; the person review is pending). Agreeing values are "
      "taken as right (Part 7: 50 of 50 sampled agreements were right). A record is **covered** when every "
      "disagreeing value in it was reviewed. A record with no disagreement keeps its saved decision as reference.")
    w("")
    rc, rb = c["reference"], c["reference_blocked"]
    w(f"- All records: no disagreement {rc['no disagreement']:,}, covered {rc['reviewed']:,}, not covered "
      f"{rc['not covered']:,}.")
    w(f"- Blocked records: no disagreement {rb['no disagreement']:,}, covered {rb['reviewed']:,}, not covered "
      f"{rb['not covered']:,}. (Part 7 reviewed every disagreement on a blocked step.)")
    w("")
    for v in VERSIONS:
        vd = c[v]["verdict"]
        w(f"### Version {VERSION_TEXT[v]}")
        w("")
        w("| change | fixes an error | adds an error | not covered | total |")
        w("|---|---|---|---|---|")
        for kind in ("block removed", "block added"):
            f_, a_, n_ = vd[(kind, "fixes an error")], vd[(kind, "adds an error")], vd[(kind, "not covered")]
            w(f"| {kind} | {f_} | {a_} | {n_} | {f_ + a_ + n_} |")
        w("")
        wr = c[v]["wrong"]
        w(f"Wrong decisions on the {wr[('saved', 'known')]:,} records whose reference is known:")
        w("")
        w("| decisions | wrong blocks | wrong allows |")
        w("|---|---|---|")
        w(f"| saved (TGR, judge values) | {wr[('saved', 'wrong block')]} | {wr[('saved', 'wrong allow')]} |")
        w(f"| version {v} | {wr[(v, 'wrong block')]} | {wr[(v, 'wrong allow')]} |")
        w("")
        if c[v]["readings"]:
            w("Fixes that rest on one of the reviewer's readings (Part 7; a fix can rest on more than one item): "
              + "; ".join(f"{k} {n}" for k, n in c[v]["readings"].most_common()) + ".")
            w("")
    # uncovered changes
    unc = [r for r in results for v in ("a",) if r[v]["change"] and r[v]["verdict"] is None]
    if unc:
        w("Changed records that Part 7 does not cover (version a), with the values that were not reviewed:")
        w("")
        w("| record | change | replaced values (judge -> tracker) | Part 6 group (a description, not a verdict) |")
        w("|---|---|---|---|")
        for r in unc:
            vals = ", ".join(f"`{n}` {x['judge']} -> {x['tracker']}" for n, x in r["a"]["values"].items())
            groups = "; ".join(sorted({g for g in r["groups"].values() if g}))
            w(f"| `{r['step_id']}` | {r['a']['change']} | {vals} | {groups} |")
        w("")
        other = [x for x in load_review().values() if x["stratum"] == "disagreement, other"]
        ok = sum(x["tracker_ok"] for x in other)
        w(f"For these, Part 7's sample of other disagreements (not on blocked steps) is the best guide: the tracker "
          f"was right in {ok} of {len(other)} reviewed items. Almost all of them are an order whose status a later "
          f"output showed as something else, so they follow the \"superseded status\" reading: under the reviewer's "
          f"reading the added blocks are right, under the other reading they are wrong.")
        w("")

    # sensitivity
    w("### If the person takes the other reading")
    w("")
    w("Part 7's reviewer chose five readings (stale cabin field, superseded order status, signed price difference, "
      "no gift card in the call, same-item exchange). In each of these items the reviewer sided with the tracker, or, "
      "for the same-item exchange, with neither. Here the items of one reading take the judge's value instead, and "
      "the reference decision is computed again.")
    w("")
    w("| reading taken the other way | records with another reference | saved: wrong blocks / allows | "
      "(a): wrong blocks / allows | (b): wrong blocks / allows |")
    w("|---|---|---|---|---|")
    w(f"| none (as reviewed) | 0 | {c['a']['wrong'][('saved', 'wrong block')]} / "
      f"{c['a']['wrong'][('saved', 'wrong allow')]} | {c['a']['wrong'][('a', 'wrong block')]} / "
      f"{c['a']['wrong'][('a', 'wrong allow')]} | {c['b']['wrong'][('b', 'wrong block')]} / "
      f"{c['b']['wrong'][('b', 'wrong allow')]} |")
    for s, x in c["sensitivity"].items():
        w(f"| {s} | {x['records with another reference']} | {x[('saved', 'wrong block')]} / "
          f"{x[('saved', 'wrong allow')]} | {x[('a', 'wrong block')]} / {x[('a', 'wrong allow')]} | "
          f"{x[('b', 'wrong block')]} / {x[('b', 'wrong allow')]} |")
    w("")
    w("The reference is not independent of the tracker: Part 7's reviewer gave the tracker's value in 263 of 266 "
      "items, and the frozen lookups already follow the readings above. So \"0 wrong decisions after the change\" "
      "mostly says that the tracker and the reviewer agree; the table above shows how much rests on the readings.")
    w("")

    # choice
    w("## 5. The version for Part 10")
    w("")
    w(f"Rule (written before the full run): {CHOICE_RULE}")
    w("")
    w(f"**Chosen: version {VERSION_TEXT[choice]}.** Reason: {reason}.")
    w("")
    if not diff:
        w("On the saved steps the two versions give the same decision on every record, because the tracker gives "
          "unknown in only " + str(len(tu)) + " value(s) and no decision depends on it. So the saved data cannot "
          "tell them apart, and the tie rule decides. In new conversations (Part 10) the tracker may give unknown "
          "more often, for example when the agent calls a tool with a missing argument.")
        w("")
    if choice == "b":
        w("What this means for Part 10: when a lookup gives unknown, the guard uses the judge's value for that "
          "predicate. So the judge must also be able to give a value for a code-type predicate whose lookup gave "
          "unknown (for example, by adding that predicate to the judge's question only in that case).")
        w("")
    w("## Files")
    w("- `output/p8_changes.jsonl`: one line per record whose decision changes in (a) or (b), with the replaced "
      "values, the values that flip the decision alone, the reference decision and the review items.")
    w("- Log: `output/logs/p8_decide_again.log`.")
    w("")
    text = "\n".join(L)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return text


def write_changes(results: List[dict], path: str = CHANGES_JSONL) -> int:
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        for r in results:
            if r["a"]["change"] or r["b"]["change"]:
                f.write(json.dumps({k: v for k, v in r.items() if k != "check"}, ensure_ascii=False) + "\n")
                n += 1
    return n


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=None, help="records per run and domain (for a quick try; no files)")
    args = ap.parse_args(list(argv) if argv is not None else None)
    t0 = time.time()
    results = run_all(args.limit)
    c = counts(results)
    print(f"records: {len(results)}  ({time.time() - t0:.1f} s)")
    for k, n in sorted(c["check"].items()):
        print(f"  check {k}: {n}")
    failed = sum(n for k, n in c["check"].items() if k.endswith("FAILED"))
    if failed:
        print("CHECK 1 FAILED: stop (p8.md subtask 1).")
        return 1
    for v in VERSIONS:
        p = c[v]["per_rd"][("all", "all")]
        print(f"version {v}: blocked before {p['blocked before']}, after {p['blocked after']}, removed "
              f"{p['block removed']}, added {p['block added']}; verdicts {dict(c[v]['verdict'])}; "
              f"wrong {dict(c[v]['wrong'])}")
    print("choice:", choose(c))
    if args.limit:
        return 0
    print("changed records written:", write_changes(results))
    write_md(results, c)
    print("wrote", RESULT_MD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
