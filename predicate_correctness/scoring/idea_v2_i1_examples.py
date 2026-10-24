"""I1 proposal: print a few judge evidences for the predicates that decide most blocks (read only, stdlib, no LLM,
no network). For reading only; it decides nothing.

Run from predicate_correctness/:
    python3 -B scoring/idea_v2_i1_examples.py > output/logs/v2_i1_examples.log 2>&1
"""
from __future__ import annotations

import collections
import json
import os
import random
import sys

sys.dont_write_bytecode = True


def _no_network(event, args):
    if event in ("socket.connect", "socket.getaddrinfo", "socket.sendto", "socket.sendmsg"):
        raise RuntimeError(f"network refused ({event})")


sys.addaudithook(_no_network)
PC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC not in sys.path:
    sys.path.insert(0, PC)

from state_tracker import paths                                     # noqa: E402
from state_tracker.load_steps import read_steps                     # noqa: E402
from state_tracker.tgr_to_aspm import load_rule_set, to_aspm        # noqa: E402
from state_tracker.decide_again import decide, judge_values, replaced  # noqa: E402

WANT = {"retail": ["user_specific_information_disclosed", "agent_reminded_user_to_include_all_items_for_modification",
                   "agent_reminded_user_to_include_all_items_for_exchange"],
        "airline": ["pending_database_change_details_listed_and_explicitly_confirmed",
                    "request_cannot_be_handled_with_available_tools"]}


def main():
    tracker = collections.defaultdict(dict)
    with open(os.path.join(paths.OUTPUT_DIR, "p6_values.jsonl"), encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            tracker[r["step_id"]][r["predicate"]] = r["tracker_value"]
    pool = collections.defaultdict(list)
    shown_before = collections.Counter()
    for domain in paths.DOMAINS:
        aspm = to_aspm(load_rule_set(domain))
        for run in paths.RUNS:
            for rec in read_steps(run, domain, with_history=True):
                jv = judge_values(rec)
                tv = replaced(jv, tracker.get(rec["step_id"], {}), "b")
                if decide(aspm, rec, tv)["allowed"]:
                    continue
                for p in WANT[domain]:
                    if p not in jv:
                        continue
                    alt = dict(tv, **{p: not jv[p]}) if jv[p] is not None else None
                    if alt is None or not decide(aspm, rec, alt)["allowed"]:
                        continue
                    if p == "user_specific_information_disclosed":
                        ok_tools = [m for m in rec["history"] if m.get("role") == "tool"
                                    and not str(m.get("content", "")).startswith("Error")]
                        shown_before["any_ok_tool_output" if ok_tools else "no_ok_tool_output"] += 1
                    pool[p].append({"step_id": rec["step_id"], "value": jv[p], "cut": rec["judge_history_cut"],
                                    "evidence": str(rec["judge"][p].get("evidence"))[:300],
                                    "action_text": str(rec.get("action_text"))[:300]})
    rnd = random.Random(20261022)
    for p, xs in pool.items():
        print(f"=== {p}: {len(xs)} pivotal blocked checks; 4 random examples")
        for x in rnd.sample(xs, min(4, len(xs))):
            print(json.dumps(x, ensure_ascii=False))
    print("user_specific_information_disclosed pivotal blocks, successful tool output before:", dict(shown_before))
    return 0


if __name__ == "__main__":
    sys.exit(main())
