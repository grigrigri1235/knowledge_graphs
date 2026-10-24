"""I1 proposal 'track more facts with code' (docs/planning/tracker_eval_v2/idea_track_more_facts.md): counts per
predicate that is NOT a code type today (conversation, mixed).

Read only. Standard library only. No LLM call, no network (an audit hook refuses every socket connection).
Reads: output/steps_<run>_<domain>.jsonl (frozen TGR, train, 4,903 judged checks), output/p6_values.jsonl (tracker
values), output/predicate_types.json, the frozen rule sets, and the online train runs of TGR + tracker
(output/online/p10_{luna,nano}_train/<domain>/tgr_tracker/episodes.jsonl). Validation runs are NOT read, so they stay
clean for a later honest test.
Writes only: output/logs/v2_i1_counts.json (and the log the caller redirects to).

Run from predicate_correctness/:
    python3 -B scoring/idea_v2_i1_counts.py > output/logs/v2_i1_counts.log 2>&1

Measures per predicate:
  values           judge values (true / false / unknown) in the 4,903 offline checks
  block_causing    frozen TGR blocked checks where the predicate is in a violated rule (as in p3_type_counts.md)
  pivot_block_frz  frozen TGR blocked checks that one other value (true or false) of this predicate alone would allow
  pivot_block_trk  the same with the tracker's code-type values (version b, the current guard 'TGR + tracker')
  allow_rests      allowed checks (with tracker values) that the other true/false value of this predicate would block
  cut              of pivot_block_trk: checks where the judge saw a cut history (last 24,000 characters only)
Family counterfactual: blocked checks (tracker values) that become allowed if every predicate of a family takes the
value that allows (true for required predicates, false for those under NOT).
"""
from __future__ import annotations

import collections
import json
import os
import sys
import time

sys.dont_write_bytecode = True


def _no_network(event, args):
    if event in ("socket.connect", "socket.getaddrinfo", "socket.sendto", "socket.sendmsg"):
        raise RuntimeError(f"network refused by idea_v2_i1_counts.py ({event})")


sys.addaudithook(_no_network)

PC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC not in sys.path:
    sys.path.insert(0, PC)

from state_tracker import paths                                     # noqa: E402
from state_tracker.load_steps import read_steps                     # noqa: E402
from state_tracker.tgr_to_aspm import load_rule_set, to_aspm        # noqa: E402
from state_tracker.decide_again import decide, judge_values, replaced  # noqa: E402

OUT_JSON = os.path.join(paths.LOGS_DIR, "v2_i1_counts.json")
CODE_TYPES = {"argument", "database fact", "event"}
LLM_TYPES = {"conversation", "mixed"}
ONLINE_TAGS = ("p10_luna_train", "p10_nano_train")      # train only; validation is not read

FAMILIES = {
    "listed_confirmed": [
        "consequential_action_details_listed", "user_explicitly_confirmed_pending_action",
        "user_confirmed_cancellation_order_and_reason", "user_confirmed_return_order_items_and_method",
        "user_chose_pending_payment_method", "user_chose_price_difference_payment_method",
        "pending_database_change_details_listed_and_explicitly_confirmed",
        "user_selected_eligible_flight_change_payment_method", "booking_insurance_decision_established_and_matched"],
    "reminder": ["agent_reminded_user_to_include_all_items_for_modification",
                 "agent_reminded_user_to_include_all_items_for_exchange"],
    "ids_given": ["email_identity_provided_by_user", "name_and_zip_identity_provided_by_user",
                  "booking_required_information_established", "passenger_identity_details_established",
                  "modification_user_and_reservation_ids_established", "cancellation_context_established"],
    "other_user": ["request_is_for_another_user", "response_performs_task_for_another_user",
                   "user_specific_information_disclosed"],
    "fact_with_message_fallback": ["cancellation_is_within_24_hours", "airline_cancelled_flight_confirmed",
                                   "compensation_is_prohibited_for_relevant_reservation",
                                   "insured_cancellation_condition_met"],
    "compensation_talk": ["user_explicitly_requested_compensation", "user_complained_about_relevant_flight_situation",
                          "pending_response_offers_cancelled_flight_certificate",
                          "pending_response_offers_delayed_flight_certificate",
                          "pending_response_offers_any_compensation_certificate",
                          "cancelled_flight_certificate_response_conditions_and_amount_met",
                          "delayed_flight_certificate_response_conditions_and_amount_met",
                          "cancelled_flight_certificate_send_conditions_met",
                          "delayed_flight_certificate_send_conditions_met"],
    "scope_transfer": ["request_cannot_be_handled_with_available_tools", "request_cannot_be_handled_within_scope"],
}
VNAME = {True: "true", False: "false", None: "unknown"}


def load_types():
    with open(os.path.join(paths.OUTPUT_DIR, "predicate_types.json"), encoding="utf-8") as f:
        t = json.load(f)
    return {d: {p: v["type"] for p, v in t[d].items()} for d in paths.DOMAINS}


def polarity(rule_set):
    """predicate -> 'true' (required), 'false' (under NOT) or 'both'."""
    pol = collections.defaultdict(set)
    for r in rule_set["rules"]:
        toks = r["logic"].replace("(", " ( ").replace(")", " ) ").split()
        for i, tok in enumerate(toks):
            if tok in rule_set["predicates"]:
                pol[tok].add("false" if i > 0 and toks[i - 1] == "NOT" else "true")
    return {p: (s.pop() if len(s) == 1 else "both") for p, s in pol.items()}


def load_tracker():
    out = collections.defaultdict(dict)
    with open(os.path.join(paths.OUTPUT_DIR, "p6_values.jsonl"), encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            out[r["step_id"]][r["predicate"]] = r["tracker_value"]
    return out


def allows(aspm, rec, vals):
    return decide(aspm, rec, vals)["allowed"]


def pivot_block(aspm, rec, vals, p):
    """A blocked check: does another true/false value of p alone allow it?"""
    return any(allows(aspm, rec, dict(vals, **{p: v})) for v in (True, False) if vals.get(p) is not v)


def allow_rests(aspm, rec, vals, p):
    """An allowed check: would the other true/false value of p alone block it? (only when p has a true/false value)"""
    v = vals.get(p)
    return v is not None and not allows(aspm, rec, dict(vals, **{p: not v}))


def family_allowing(aspm, rec, vals, names, pol):
    new = dict(vals)
    hit = False
    for p in names:
        if p in new and pol.get(p) in ("true", "false"):
            new[p] = pol[p] == "true"
            hit = True
    return hit and allows(aspm, rec, new)


def blank():
    return {"values": collections.Counter(), "checks": 0, "block_causing": 0, "pivot_block_frz": 0,
            "pivot_block_trk": 0, "allow_rests": 0, "cut": 0, "write_checks": 0,
            "online_values": collections.Counter(), "online_pivot_block": 0, "online_allow_rests": 0,
            "by_run": collections.Counter(), "tools": collections.Counter(), "pivot_steps": set(),
            "pivot_convs": set()}


def main():
    t0 = time.time()
    types = load_types()
    tracker = load_tracker()
    res = {"offline": {}, "online": {}, "families": {}, "totals": {}, "polarity": {}, "notes": []}
    per = {d: collections.defaultdict(blank) for d in paths.DOMAINS}
    tot = collections.Counter()
    fam = collections.defaultdict(collections.Counter)
    msg = collections.Counter()
    seen_eps = set()
    acts = collections.defaultdict(collections.Counter)
    dsteps = collections.defaultdict(set)
    dconvs = collections.defaultdict(set)
    for domain in paths.DOMAINS:
        rs = load_rule_set(domain)
        aspm = to_aspm(rs)
        pol = polarity(rs)
        res["polarity"][domain] = pol
        llm = {p for p, t in types[domain].items() if t in LLM_TYPES}
        writes = {a for a in rs["action_names"]} & {
            "cancel_pending_order", "exchange_delivered_order_items", "modify_pending_order_address",
            "modify_pending_order_items", "modify_pending_order_payment", "modify_user_address",
            "return_delivered_order_items", "book_reservation", "cancel_reservation", "update_reservation_flights",
            "update_reservation_baggages", "update_reservation_passengers", "send_certificate"}
        rid_atoms = {rid: aspm.rules[rid].atoms for rid in aspm.rules}
        for run in paths.RUNS:
            for rec in read_steps(run, domain, with_history=False):
                jv = judge_values(rec)
                tv = replaced(jv, tracker.get(rec["step_id"], {}), "b")
                saved = rec["action_allowed"]
                assert allows(aspm, rec, jv) == saved, rec["step_id"]
                trk_allowed = allows(aspm, rec, tv)
                tot["checks"] += 1
                tot["blocked_frozen"] += (not saved)
                tot["blocked_tracker"] += (not trk_allowed)
                viol_atoms = set()
                for vr in rec.get("violated_rules") or []:
                    viol_atoms |= rid_atoms.get(str(vr.get("rule_id")), set())
                llm_here = [p for p in jv if p in llm]
                any_llm_pivot = False
                step_key = (run, domain, rec["task"], rec["trial"], rec["exec_step"])
                acts[f"{domain}:{rec['action']}"]["checks"] += 1
                acts[f"{domain}:{rec['action']}"]["blocked_trk"] += (not trk_allowed)
                if not trk_allowed:
                    dsteps["blocked_trk"].add(step_key)
                    dconvs["blocked_trk"].add(step_key[:4])
                for p in jv:
                    typ = types[domain].get(p)
                    tot["values_" + ("llm" if typ in LLM_TYPES else "code")] += 1
                    if not saved and p in viol_atoms:
                        tot["block_causing_" + ("llm" if typ in LLM_TYPES else "code")] += 1
                for p in llm_here:
                    s = per[domain][p]
                    s["values"][VNAME[jv[p]]] += 1
                    s["checks"] += 1
                    s["by_run"][run] += 1
                    s["tools"][rec["action"]] += 1
                    s["write_checks"] += rec["action"] in writes
                    if not saved and p in viol_atoms:
                        s["block_causing"] += 1
                    if not saved and pivot_block(aspm, rec, jv, p):
                        s["pivot_block_frz"] += 1
                    if not trk_allowed and pivot_block(aspm, rec, tv, p):
                        s["pivot_block_trk"] += 1
                        s["cut"] += bool(rec.get("judge_history_cut"))
                        s["pivot_steps"].add(step_key)
                        s["pivot_convs"].add(step_key[:4])
                        any_llm_pivot = True
                    if trk_allowed and allow_rests(aspm, rec, tv, p):
                        s["allow_rests"] += 1
                if not trk_allowed:
                    tot["blocked_tracker_llm_pivot"] += any_llm_pivot
                    if any_llm_pivot:
                        dsteps["llm_pivot"].add(step_key)
                    all_names = [p for p in llm_here]
                    all_ok = family_allowing(aspm, rec, tv, all_names, pol)
                    tot["blocked_tracker_all_llm_allowing_allows"] += all_ok
                    if all_ok:
                        dsteps["all_llm_allowing"].add(step_key)
                    for fname, names in FAMILIES.items():
                        if any(p in tv for p in names):
                            fam[fname]["blocked_with_family"] += 1
                            ok = family_allowing(aspm, rec, tv, names, pol)
                            fam[fname]["allowed_if_family_allowing"] += ok
                            if ok:
                                dsteps["fam:" + fname].add(step_key)
                                dconvs["fam:" + fname].add(step_key[:4])
                    fam["_all"]["blocked"] += 1
                if not trk_allowed and rec["action"] in writes:
                    tot["blocked_tracker_write"] += 1
                # per-conversation message counts for the cost estimate of narrow questions (design 2)
                ep_key = (run, domain, rec["task"], rec["trial"])
                if ep_key not in seen_eps:
                    seen_eps.add(ep_key)
                    msg["conversations"] += 1
                tot["checks_" + ("respond" if rec["action"] == "respond" else "tool")] += 1
                tot["judge_cost_usd_x1e6"] += int(round(1e6 * ((rec.get("judge_usage") or {}).get("cost_usd") or 0)))
            print(f"offline {run}/{domain} done at {time.time() - t0:.1f} s", flush=True)
        # message counts from the copied episodes (train runs only)
        from state_tracker.load_steps import iter_episodes  # noqa: E402
        for run in paths.RUNS:
            for _, ep in iter_episodes(run, domain):
                ex = ep.get("executed") or []
                msg["episodes"] += 1
                for m in ex:
                    role = m.get("role")
                    c = m.get("content") if isinstance(m.get("content"), str) else ""
                    if role == "user":
                        msg["user_messages"] += 1
                        msg["user_chars"] += len(c)
                    elif role == "assistant" and c.strip() and not m.get("tool_calls"):
                        msg["agent_text_messages"] += 1
                        msg["agent_chars"] += len(c)
                msg["attempts"] += len(ep.get("attempts") or [])
        # online train runs of TGR + tracker (values used by the guard; source judge or tracker)
        for tag in ONLINE_TAGS:
            path = os.path.join(paths.OUTPUT_DIR, "online", tag, domain, "tgr_tracker", "episodes.jsonl")
            kept = {}
            with open(path, encoding="utf-8") as f:
                for line in f:
                    ep = json.loads(line)
                    if ep.get("error"):
                        continue
                    kept.setdefault((ep["task_index"], ep.get("trial")), ep)
            for ep in kept.values():
                for a in ep.get("attempts") or []:
                    g = a.get("guard") or {}
                    if not g.get("judge"):
                        continue
                    used = {p: v.get("value") for p, v in g["judge"].items()}
                    ok = allows(aspm, g, used)
                    tot["online_checks"] += 1
                    tot["online_check_mismatch"] += (ok != g["action_allowed"])
                    tot["online_blocked"] += (not ok)
                    for p, v in g["judge"].items():
                        if p not in llm:
                            continue
                        s = per[domain][p]
                        s["online_values"][VNAME[v.get("value")]] += 1
                        if not ok and pivot_block(aspm, g, used, p):
                            s["online_pivot_block"] += 1
                        if ok and allow_rests(aspm, g, used, p):
                            s["online_allow_rests"] += 1
            print(f"online {tag}/{domain} done at {time.time() - t0:.1f} s", flush=True)
        res["offline"][domain] = {p: {k: (dict(v) if isinstance(v, collections.Counter) else
                                          (len(v) if isinstance(v, set) else v)) for k, v in s.items()}
                                  for p, s in per[domain].items()}
        # predicates of an LLM type that were never judged
        for p in sorted(llm):
            if p not in per[domain]:
                res["offline"][domain][p] = {"values": {}, "checks": 0, "never_judged": True}
    res["totals"] = dict(tot)
    res["families"] = {k: dict(v) for k, v in fam.items()}
    res["messages"] = dict(msg)
    res["actions"] = {k: dict(v) for k, v in sorted(acts.items())}
    res["distinct_steps"] = {k: len(v) for k, v in sorted(dsteps.items())}
    res["distinct_conversations"] = {k: len(v) for k, v in sorted(dconvs.items())}
    res["types_count"] = {d: dict(collections.Counter(types[d].values())) for d in paths.DOMAINS}
    res["seconds"] = round(time.time() - t0, 1)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, sort_keys=True)
    # short readable summary
    print(json.dumps(res["totals"], indent=1, sort_keys=True))
    print(json.dumps(res["families"], indent=1, sort_keys=True))
    print(json.dumps(res["messages"], indent=1, sort_keys=True))
    print(json.dumps(res["actions"], indent=1, sort_keys=True))
    print(json.dumps(res["distinct_steps"], indent=1, sort_keys=True))
    print(json.dumps(res["distinct_conversations"], indent=1, sort_keys=True))
    hdr = ("domain", "predicate", "type", "pol", "checks", "T/F/U", "blk_cause", "piv_frz", "piv_trk", "cut",
           "allow_rests", "online_TFU", "online_piv", "online_rests", "piv_steps", "piv_convs")
    print("\t".join(hdr))
    for d in paths.DOMAINS:
        rows = sorted(res["offline"][d].items(), key=lambda kv: -kv[1].get("pivot_block_trk", 0))
        for p, s in rows:
            v, ov = s.get("values", {}), s.get("online_values", {})
            print("\t".join(str(x) for x in (
                d, p, types[d][p], res["polarity"][d].get(p), s.get("checks", 0),
                f"{v.get('true', 0)}/{v.get('false', 0)}/{v.get('unknown', 0)}", s.get("block_causing", 0),
                s.get("pivot_block_frz", 0), s.get("pivot_block_trk", 0), s.get("cut", 0), s.get("allow_rests", 0),
                f"{ov.get('true', 0)}/{ov.get('false', 0)}/{ov.get('unknown', 0)}", s.get("online_pivot_block", 0),
                s.get("online_allow_rests", 0), s.get("pivot_steps", 0), s.get("pivot_convs", 0))))
    print(f"wrote {OUT_JSON} in {res['seconds']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
