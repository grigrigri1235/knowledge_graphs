"""Eval v2 Part 6, weak run: a few extra raw facts for stage_a_runs.md (standard library only, no LLM call).

Reads output/logs/v2_c6w_check.json (from scoring/v2_p6_weak_check.py) and the weak run's episode files (read only).
1. Same start in both guards: tasks where the first user message and the first agent message are the same text in
   both guards (this is when the two guards can ask the judge the very same first prompt, so share a cache name).
2. Paired raw counts split by "the tracker changed a decision in this task" (yes / no).
3. For each changed decision on user_authenticated: characters of conversation text between the end of the first
   successful find_user_id_* result and the attempt (a rough view of whether the login was outside the judge's last
   24,000 characters; the judge's own text format differs a little, so this is only a rough count).
4. Tracker conversations where a value changed but no decision did (the guard's feedback text can still differ).

Run from predicate_correctness/:
  PYTHONDONTWRITEBYTECODE=1 nice -n 10 /home/azureuser/miniconda3/bin/python3 -B -m scoring.v2_p6_weak_extra \
      > output/logs/v2_c6w_extra.json 2> output/logs/v2_c6w_extra.err
"""
from __future__ import annotations

import collections
import glob
import json
import os
import sys

sys.dont_write_bytecode = True

from state_tracker import paths                                     # noqa: E402

AGENT_DIR = os.path.join(paths.OUTPUT_DIR, "eval_v2", "stage_a", "nano")
CHECK = os.path.join(paths.OUTPUT_DIR, "logs", "v2_c6w_check.json")
GUARDS = ("tgr_frozen", "tgr_tracker")
VIEW = 24000


def good_lines(g):
    out = {}
    for p in sorted(glob.glob(os.path.join(AGENT_DIR, g, "episodes*.jsonl"))):
        with open(p, encoding="utf-8") as f:
            for raw in f:
                if not raw.strip():
                    continue
                r = json.loads(raw)
                if r.get("error") is None and r["task_index"] not in out:
                    out[r["task_index"]] = r
    return out


def text_len(m):
    n = len(str(m.get("content") or ""))
    if m.get("tool_calls"):
        n += len(json.dumps(m["tool_calls"]))
    return n


def first_agent_text(r):
    a = (r.get("attempts") or [{}])[0]
    return json.dumps([a.get("action"), a.get("kwargs"), a.get("agent_text")], sort_keys=True)


def main():
    chk = json.load(open(CHECK, encoding="utf-8"))
    eps = {g: good_lines(g) for g in GUARDS}
    a = {t: r["reward"] for t, r in eps["tgr_frozen"].items()}
    b = {t: r["reward"] for t, r in eps["tgr_tracker"].items()}
    out = {}
    # 0. layout check: messages = 2 + 2 x attempts, and message 2 + 2j is the agent message of attempt j
    lay = collections.Counter()
    for g in GUARDS:
        for r in eps[g].values():
            ms, at = r["messages"], r.get("attempts") or []
            lay["ok length" if len(ms) == 2 + 2 * len(at) else "other length"] += 1
            lay["agent message at 2+2j" if all(ms[2 + 2 * j].get("role") == "assistant" for j in range(len(at))
                                               if 2 + 2 * j < len(ms)) else "not agent at 2+2j"] += 1
    out["layout"] = dict(lay)
    # 1. same start
    same_user = same_both = 0
    for t in range(500):
        f, k = eps["tgr_frozen"][t], eps["tgr_tracker"][t]
        if f["messages"][1] == k["messages"][1]:
            same_user += 1
            if first_agent_text(f) == first_agent_text(k):
                same_both += 1
    out["same_first_user_message"] = same_user
    out["same_first_user_message_and_first_agent_attempt"] = same_both
    # 2. paired split
    ch = set(chk["guards"]["tgr_tracker"]["tracker"]["tasks_with_a_changed_decision"])
    for label, ts in (("changed", sorted(ch)), ("not_changed", sorted(set(range(500)) - ch))):
        out[f"paired_{label}"] = {
            "tasks": len(ts),
            "both_success": sum(1 for t in ts if a[t] == 1.0 and b[t] == 1.0),
            "only_tracker_success": sum(1 for t in ts if a[t] != 1.0 and b[t] == 1.0),
            "only_frozen_success": sum(1 for t in ts if a[t] == 1.0 and b[t] != 1.0),
            "both_fail": sum(1 for t in ts if a[t] != 1.0 and b[t] != 1.0),
            "tracker_success": sum(1 for t in ts if b[t] == 1.0),
            "frozen_success": sum(1 for t in ts if a[t] == 1.0)}
    # 3. distance from the login to the changed user_authenticated decisions
    dist = []
    no_login = 0
    for x in chk["guards"]["tgr_tracker"]["tracker"]["changed_decisions"]:
        if "user_authenticated" not in x["predicates"]:
            continue
        r = eps["tgr_tracker"][x["task"]]
        msgs = r["messages"]
        atts = r["attempts"]
        login_end = None
        for j, at in enumerate(atts):
            if j >= x["attempt_idx"]:
                break
            if str(at.get("action") or "").startswith("find_user_id") and not at.get("blocked"):
                res = msgs[2 + 2 * j + 1] if 2 + 2 * j + 1 < len(msgs) else {}
                if not str(res.get("content") or "").lower().startswith("error"):
                    login_end = 2 + 2 * j + 2
                    break
        upto = 2 + 2 * x["attempt_idx"] + 1          # include the agent message of the attempt
        if login_end is None:
            no_login += 1
            continue
        dist.append({"task": x["task"], "attempt_idx": x["attempt_idx"], "change": x["change"],
                     "chars_after_login": sum(text_len(m) for m in msgs[login_end:upto]),
                     "chars_total_before": sum(text_len(m) for m in msgs[1:upto])})
    out["user_authenticated_changed"] = {
        "n": len(dist) + no_login, "no_successful_login_before": no_login,
        "chars_after_login_over_24000": sum(1 for d in dist if d["chars_after_login"] > VIEW),
        "chars_after_login_at_most_24000": sum(1 for d in dist if d["chars_after_login"] <= VIEW),
        "kinds": dict(collections.Counter(d["change"] for d in dist)),
        "min_chars_after_login": min((d["chars_after_login"] for d in dist), default=None),
        "median_chars_after_login": sorted(d["chars_after_login"] for d in dist)[len(dist) // 2] if dist else None,
        "under_view_examples": [d for d in dist if d["chars_after_login"] <= VIEW][:10]}
    # 4. value changed, no decision changed
    chd = {(x["task"], x["attempt_idx"]) for x in chk["guards"]["tgr_tracker"]["tracker"]["changed_decisions"]}
    vc = set()
    flips = collections.Counter()
    for t, r in eps["tgr_tracker"].items():
        for i, at in enumerate(r.get("attempts") or []):
            rec = at.get("guard") or {}
            tr = rec.get("tracker") or {}
            if tr.get("changed"):
                vc.add(t)
                if (t, i) not in chd:
                    jv = tr.get("judge_values") or {}
                    used = {k: (v or {}).get("value") for k, v in (rec.get("judge") or {}).items()}
                    for nm in tr["changed"]:
                        flips[f"{nm}: judge {jv.get(nm)} -> used {used.get(nm)}"] += 1
    out["changed_values_without_a_changed_decision"] = dict(flips.most_common())
    only_value = sorted(vc - ch)
    out["tracker_conversations_with_a_changed_value"] = len(vc)
    out["with_a_changed_value_but_no_changed_decision"] = {
        "tasks": len(only_value),
        "only_tracker_success": sum(1 for t in only_value if a[t] != 1.0 and b[t] == 1.0),
        "only_frozen_success": sum(1 for t in only_value if a[t] == 1.0 and b[t] != 1.0)}
    rest = sorted(set(range(500)) - vc)
    out["no_changed_value_at_all"] = {
        "tasks": len(rest),
        "only_tracker_success": sum(1 for t in rest if a[t] != 1.0 and b[t] == 1.0),
        "only_frozen_success": sum(1 for t in rest if a[t] == 1.0 and b[t] != 1.0)}
    # 5. rule-56 blocks with a gift card: the judge's "not established" (frozen) vs the tracker's false.
    #    What the agent does at the next attempt, and the raw outcome of the tasks that have such a block.
    gc = "gift_card_balance_covers_price_difference"
    five = {}
    for g in GUARDS:
        nxt = collections.Counter()
        tasks = set()
        kinds = collections.Counter()
        for t, r in eps[g].items():
            atts = r.get("attempts") or []
            for i, at in enumerate(atts):
                rec = at.get("guard") or {}
                if not at.get("blocked") or at.get("action") != "modify_pending_order_items":
                    continue
                used = {k: (v or {}).get("value") for k, v in (rec.get("judge") or {}).items()}
                if used.get("payment_method_is_gift_card") is not True or gc not in used:
                    continue
                tr = rec.get("tracker") or {}
                jv = tr.get("judge_values") or {}
                if g == "tgr_frozen" and used[gc] is None:
                    kind = "judge: not established"
                elif g == "tgr_tracker" and used[gc] is False and gc in (tr.get("changed") or []) and jv.get(gc) is None:
                    kind = "judge: not established, tracker: false"
                else:
                    continue
                kinds[kind] += 1
                tasks.add(t)
                fb = str(at.get("feedback") or "")
                todo = [ln for ln in fb.split("\n") if ln.startswith("- Rule(s)")]
                kinds["feedback says: look it up with a read-only tool"] += "look it up with a read-only tool" in fb
                kinds["feedback says: Rule(s) ... 56 ... violated"] += any("56" in ln and "violated" in ln for ln in todo)
                kinds[f"feedback shows: {gc} = false"] += f"{gc} = false" in fb
                kinds[f"feedback shows: {gc} = not established"] += f"{gc} = not established" in fb
                if i + 1 < len(atts):
                    na = str(atts[i + 1].get("action"))
                    nxt["read-only lookup (get_*)" if na.startswith("get_") else
                        "same call again" if na == "modify_pending_order_items" else
                        "respond" if na == "respond" else "other: " + na] += 1
                else:
                    nxt["end of conversation"] += 1
        ts = sorted(tasks)
        five[g] = {"blocks": dict(kinds), "next_attempt": dict(nxt.most_common()), "tasks": len(ts),
                   "this_guard_success": sum(1 for t in ts if eps[g][t]["reward"] == 1.0),
                   "other_guard_success_same_tasks": sum(
                       1 for t in ts if eps["tgr_tracker" if g == "tgr_frozen" else "tgr_frozen"][t]["reward"] == 1.0)}
    out["rule56_gift_card_not_established"] = five
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
