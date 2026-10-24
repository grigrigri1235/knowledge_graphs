"""Part 10 audit (no LLM call): where the tracker changes no value, the guard's record equals TGR's saved record.

For every attempt with a judge call in the copied episodes, the real guard runs with a fake judge that gives the saved
values. Where tracker.changed is empty, these fields must equal the saved guard record: matched, circuit, judge values,
action_allowed, margin, violated_rules, unknown_predicates, feedback_text (component C text). Where values changed,
only the counts are reported.

Run from predicate_correctness/ with the venv:  python -B -m tests.audit_p10_feedback > output/logs/p10_audit_feedback.log
"""
from __future__ import annotations

import collections
import json
import os
import sys

sys.dont_write_bytecode = True
PC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC not in sys.path:
    sys.path.insert(0, PC)

from guard import offline, tgr_tracker                                    # noqa: E402
from repro_online.guards import make_step                                   # noqa: E402,F401
from state_tracker import paths, tau_copy                                   # noqa: E402
from state_tracker.load_steps import iter_episodes                          # noqa: E402

FIELDS = ("matched", "circuit", "action_allowed", "margin", "violated_rules", "unknown_predicates", "feedback_text")


def main() -> int:
    tot = collections.Counter()
    probs = []
    for domain in paths.DOMAINS:
        guard = tgr_tracker.TGRTrackerGuard(domain, tau_copy.tools_info(domain))
        cur = {}
        offline.install_fake(offline.FakeJudge(lambda names: cur["a"]))
        for run in paths.RUNS:
            for _, ep in iter_episodes(run, domain):
                ex, msgs, atts = ep["executed"], ep["messages"], ep["attempts"]
                for i, att in enumerate(atts):
                    g = att.get("guard") or {}
                    if not g.get("judge"):
                        continue
                    cur["a"] = {n: (v.get("value"), v.get("evidence", "")) for n, v in g["judge"].items()}
                    conv = guard.new_episode()
                    conv.trace = [a["guard"]["trace_position"] for a in atts[:i] if not a["blocked"]]
                    out = guard.check(conv, ex[:att["executed_prefix_len"]], msgs[2 + 2 * i], att["exec_step"])
                    tot["records"] += 1
                    if out["tracker"]["changed"]:
                        tot["records with a changed value"] += 1
                        continue
                    tot["records, no value changed"] += 1
                    if not g["action_allowed"]:
                        tot["blocked, no value changed"] += 1
                    jv = {n: v["value"] for n, v in out["judge"].items()}
                    if jv != {n: v.get("value") for n, v in g["judge"].items()}:
                        tot["problem: judge values"] += 1
                    for f in FIELDS:
                        a, b = out.get(f), g.get(f)
                        if f == "margin" and a is not None and b is not None:
                            same = abs(a - b) <= 1e-9
                        else:
                            same = json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
                        if not same:
                            tot[f"problem: {f}"] += 1
                            if len(probs) < 10:
                                probs.append(f"{run}/{domain} task {ep['task_index']} att {i} {f}: {str(a)[:200]} || "
                                             f"{str(b)[:200]}")
                        elif f == "feedback_text" and b:
                            tot["feedback text equal (blocked)"] += 1
            print(run, domain, dict(tot), flush=True)
    print("TOTAL", json.dumps(dict(tot), sort_keys=True))
    for p in probs:
        print("PROBLEM", p)
    print("DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
