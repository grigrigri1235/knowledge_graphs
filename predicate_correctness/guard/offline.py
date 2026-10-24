"""Part 10: run the guard "TGR + tracker" offline on the saved Part 2 records, with a fake judge (no LLM call).

The fake judge (`FakeJudge`) stands in for the LLM client that the copied TGR code calls
(repro_runtime/calls.py::shared_llm): it answers each judge call with values that the test or the check gives.
`check_records()` runs the real guard (guard/tgr_tracker.py, with the copied TGR runtime, the copied episode-loop
guard interface and our tracker) on each saved step, with the judge's saved values as the fake judge's answers, and
compares with Parts 6 and 8:
  - the guard's tracker values equal the Part 6 tracker values (output/p6_values.jsonl);
  - the decision equals Part 8's version (b): blocks that Part 8 changed (output/p8_changes.jsonl) have Part 8's new
    decision and margin, every other step keeps its saved decision;
  - the margin equals TGR's decision formula (copied mln.decide) on the judge's values with the Part 6 tracker values
    put in as in Part 8 version (b);
  - where the tracker agrees with the judge on every code-type value, the margin is the saved one.

Run from predicate_correctness/ (standard library only; about 5 minutes for all 4,903 records):
    python3 -B -m guard.offline > output/logs/p10_guard_offline.log 2>&1
It writes output/p10_guard_offline_check.md. Never imports gold code; no LLM calls.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time
from typing import Callable, Dict, Iterable, List, Optional

sys.dont_write_bytecode = True

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "guard"

from guard import tgr_tracker                                              # noqa: E402  (sets up the runner path)
from repro_runtime import calls, mln                                       # noqa: E402  (runner copy)
from state_tracker import paths, tau_copy                                  # noqa: E402
from state_tracker.load_steps import read_steps                            # noqa: E402

VALUES_JSONL = os.path.join(paths.OUTPUT_DIR, "p6_values.jsonl")
CHANGES_JSONL = os.path.join(paths.OUTPUT_DIR, "p8_changes.jsonl")
RESULT_MD = os.path.join(paths.OUTPUT_DIR, "p10_guard_offline_check.md")
NAME = {True: "true", False: "false", None: "unknown"}
MARGIN_TOL = 1e-9


class FakeJudge:
    """Stands in for the copied LLM client (policy_pipeline.llm.LLM) behind TGR's judge call.

    `answer(names_in_prompt) -> {predicate: True | False | None | (value, evidence)}` gives the values. The fake
    returns them in TGR's JSON schema. Every call is recorded in `self.calls` (stage, system, user, predicates)."""

    model = "fake-judge"
    max_output_tokens = 16000
    cache_dir = os.path.join(paths.OUTPUT_DIR, "_fake_judge_cache_never_written")

    def __init__(self, answer: Callable[[List[str]], Dict[str, object]]):
        self.answer = answer
        self.calls: List[dict] = []

    @staticmethod
    def predicates_in(user: str) -> List[str]:
        """The predicate names that TGR's judge prompt (method_tgr/prompts/judge.md) lists under
        'Predicates to decide:' (lines '- <name>: <description>')."""
        start = user.rfind("\nPredicates to decide:\n")
        end = user.find("\n\nFor every predicate return", start)
        if start < 0 or end < 0:
            return []
        out = []
        for line in user[start:end].splitlines()[2:]:
            if line.startswith("- ") and ":" in line:
                out.append(line[2:].split(":", 1)[0].strip())
        return out

    def call(self, *, stage, system, user, schema, schema_name, effort="low", sample=0):
        names = self.predicates_in(user)
        vals = self.answer(names)
        preds = []
        for n, v in vals.items():
            value, ev = (v if isinstance(v, tuple) else (v, f"fake evidence for {n}"))
            preds.append({"name": n, "value": NAME[value], "evidence": ev})
        self.calls.append({"stage": stage, "system": system, "user": user, "predicates": names,
                           "schema_name": schema_name, "effort": effort})
        return {"predicates": preds}


def install_fake(judge: FakeJudge) -> None:
    """Make the copied TGR code use the fake judge (calls.shared_llm() returns calls._llm when it is set)."""
    calls._llm = judge


def msg_of(rec: dict) -> dict:
    """The agent's message for a saved step record (what the episode loop passes to guard.check)."""
    if rec["kind"] == "respond":
        return {"role": "assistant", "content": rec["kwargs"].get("content", ""), "tool_calls": None}
    return {"role": "assistant", "content": rec.get("agent_text") or None,
            "tool_calls": [{"id": "call_offline", "type": "function",
                            "function": {"name": rec["action"], "arguments": json.dumps(rec["kwargs"])}}]}


def load_p6(path: str = VALUES_JSONL) -> Dict[str, Dict[str, Optional[bool]]]:
    out: Dict[str, Dict[str, Optional[bool]]] = collections.defaultdict(dict)
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            out[r["step_id"]][r["predicate"]] = r["tracker_value"]
    return dict(out)


def load_p8(path: str = CHANGES_JSONL) -> Dict[str, dict]:
    with open(path, encoding="utf-8") as f:
        return {r["step_id"]: r for r in map(json.loads, f)}


def part8_b_margin(guard, rec: dict, tracker: Dict[str, Optional[bool]]) -> Optional[float]:
    """Part 8 version (b), computed again: judge values, tracker values put in where known, copied mln.decide."""
    aspm = guard.tgr.aspm
    vals = {n: v.get("value") for n, v in rec["judge"].items()}
    vals.update({n: t for n, t in tracker.items() if t is not None})
    cur = {a: (a in rec["matched"]) for a in aspm.action_predicates}
    cur.update(vals)
    per = [mln.decide(aspm, rec["circuit"], a, cur, [], tgr_tracker.EPSILON, 16) for a in rec["matched"]]
    return min(d["margin"] for d in per) if per else None


def check_records(run: str, domain: str, limit: Optional[int] = None, p6: Optional[dict] = None,
                  p8: Optional[dict] = None, guard=None) -> dict:
    """Run the guard on the saved records of one run and domain; return counts and the first problems."""
    p6 = load_p6() if p6 is None else p6
    p8 = load_p8() if p8 is None else p8
    guard = guard or tgr_tracker.TGRTrackerGuard(domain, tau_copy.tools_info(domain))
    current = {}
    judge = FakeJudge(lambda names: current["answer"])
    install_fake(judge)
    c = collections.Counter()
    problems: List[str] = []

    def bad(kind: str, rec: dict, detail: str) -> None:
        c["problem: " + kind] += 1
        if len(problems) < 20:
            problems.append(f"{kind}: {rec['step_id']}: {detail}")

    for rec in read_steps(run, domain):
        if limit and c["records"] >= limit:
            break
        c["records"] += 1
        sid = rec["step_id"]
        current["answer"] = {n: (v.get("value"), v.get("evidence", "")) for n, v in rec["judge"].items()}
        n_calls = len(judge.calls)
        conv = guard.new_episode()
        conv.trace = list(rec.get("past_trace") or [])
        out = guard.check(conv, rec["history"], msg_of(rec), rec["exec_step"])
        tr = out["tracker"]
        c["judge skipped"] += bool(tr.get("judge_skipped"))
        c["lookup errors"] += len(tr.get("lookup_errors") or [])
        c["values replaced"] += len(tr.get("replaced") or [])
        c["values changed"] += len(tr.get("changed") or [])
        called = len(judge.calls) - n_calls
        if out["action_text"] != rec["action_text"]:
            bad("action text differs", rec, out["action_text"][:80])
        if out["circuit"] != rec["circuit"]:
            bad("circuit differs", rec, f"{out['circuit']} vs {rec['circuit']}")
        if tr.get("judge_skipped"):
            if called:
                bad("judge called although skipped", rec, "")
        else:
            if called != 1:
                bad("judge not called exactly once", rec, str(called))
            elif sorted(judge.calls[-1]["predicates"]) != sorted(rec["judge"]):
                bad("judge asked other predicates", rec, str(judge.calls[-1]["predicates"]))
        # 1. tracker values = Part 6
        want_t = p6.get(sid, {})
        got_t = {n: v.get("value") for n, v in (tr.get("tracker_values") or {}).items()}
        if got_t != want_t:
            bad("tracker values differ from Part 6", rec, f"{got_t} vs {want_t}")
        # 2. decision = Part 8 version (b)
        ch = p8.get(sid)
        want_allowed = ch["b"]["allowed"] if ch else rec["action_allowed"]
        c["part 8 changed records"] += bool(ch)
        c["blocked (saved)"] += not rec["action_allowed"]
        c["blocked (guard)"] += not out["action_allowed"]
        if out["action_allowed"] != want_allowed:
            bad("decision differs from Part 8 (b)", rec, f"{out['action_allowed']} vs {want_allowed}")
        else:
            c["decision = Part 8 (b)"] += 1
        if ch and abs(out["margin"] - ch["b"]["margin"]) > MARGIN_TOL:
            bad("margin differs from Part 8 (b)", rec, f"{out['margin']} vs {ch['b']['margin']}")
        # 3. margin = Part 8 (b) computed again
        m = part8_b_margin(guard, rec, want_t)
        if m is None or abs(out["margin"] - m) > MARGIN_TOL:
            bad("margin differs from recomputed (b)", rec, f"{out['margin']} vs {m}")
        else:
            c["margin = recomputed (b)"] += 1
        # 4. tracker agrees with the judge on every value -> saved decision and margin
        jv = {n: v.get("value") for n, v in rec["judge"].items()}
        if all(t is None or jv.get(n) is t for n, t in want_t.items()):
            c["records where the tracker agrees (or is unknown)"] += 1
            if out["action_allowed"] != rec["action_allowed"] or abs(out["margin"] - rec["margin"]) > MARGIN_TOL:
                bad("decision changed although the tracker agrees", rec, "")
            else:
                c["agreeing records with the saved decision and margin"] += 1
    return {"run": run, "domain": domain, "counts": dict(c), "problems": problems}


def write_md(results: List[dict], seconds: float, path: str = RESULT_MD) -> None:
    keys = ["records", "decision = Part 8 (b)", "margin = recomputed (b)", "part 8 changed records",
            "blocked (saved)", "blocked (guard)", "judge skipped", "values replaced", "values changed",
            "records where the tracker agrees (or is unknown)", "agreeing records with the saved decision and margin",
            "lookup errors"]
    L = ["# Part 10: the guard offline on the saved steps", "",
         "Written by `guard/offline.py`. No LLM call: a fake judge answers each judge call with the judge's saved "
         "values. The real guard (`guard/tgr_tracker.py` with the copied TGR runtime) runs on every Part 2 record "
         "and builds the state from the saved history.", "",
         "| " + " | ".join(["run, domain"] + keys) + " |", "|" + "---|" * (len(keys) + 1)]
    tot = collections.Counter()
    for r in results:
        L.append("| " + " | ".join([f"{r['run']} {r['domain']}"] + [f"{r['counts'].get(k, 0):,}" for k in keys]) + " |")
        tot.update(r["counts"])
    L.append("| " + " | ".join(["**all**"] + [f"{tot.get(k, 0):,}" for k in keys]) + " |")
    probs = {k: v for k, v in tot.items() if k.startswith("problem: ")}
    L += ["", f"Problems: {sum(probs.values())}" + (": " + ", ".join(f"{k[9:]} {v}" for k, v in probs.items())
                                                     if probs else "."), ""]
    for r in results:
        for p in r["problems"]:
            L.append(f"- {p}")
    L += ["", "Checks:", "- the decision equals Part 8 version (b) (`output/p8_changes.jsonl`; other steps keep the "
          "saved decision);", "- the margin equals TGR's formula on the judge's values with Part 6's tracker values "
          "put in (version b);", "- the tracker values equal Part 6 (`output/p6_values.jsonl`);",
          "- where the tracker agrees with the judge (or gives unknown), the decision and the margin are the saved "
          "ones;", "- the judge is called once with the same predicates as the saved judge call, or not at all "
          "when every predicate is a code type with a known value.", "", f"Time: {seconds:.0f} s.", ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=None, help="records per run and domain (no file written)")
    a = ap.parse_args(list(argv) if argv is not None else None)
    t0 = time.time()
    p6, p8 = load_p6(), load_p8()
    results = []
    for domain in paths.DOMAINS:
        guard = tgr_tracker.TGRTrackerGuard(domain, tau_copy.tools_info(domain))
        for run in paths.RUNS:
            t1 = time.time()
            r = check_records(run, domain, a.limit, p6, p8, guard)
            results.append(r)
            print(f"{run}/{domain}: {json.dumps(r['counts'], sort_keys=True)} ({time.time() - t1:.0f} s)", flush=True)
            for p in r["problems"]:
                print("  PROBLEM", p, flush=True)
    n_prob = sum(v for r in results for k, v in r["counts"].items() if k.startswith("problem: "))
    if not a.limit:
        write_md(results, time.time() - t0)
        print("wrote", RESULT_MD)
    print(f"problems: {n_prob}")
    return 1 if n_prob else 0


if __name__ == "__main__":
    sys.exit(main())
