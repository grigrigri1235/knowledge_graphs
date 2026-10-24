"""I1 proposal 'track more facts with code': rough probes of how often simple code (or the partner's gold code) agrees
with the judge on some conversation and mixed predicates. SCORING-STYLE ANALYSIS ONLY.

- Gold code (from_shieldagent/gold/ and from_shieldagent/scoring/policies/gold_v2/checks.py) is loaded here only to
  measure the judge, never as a method input (the same use as scoring/). It is loaded with sys.modules stubs that are
  removed again, as scoring/gold_loader.py does; nothing is written into the copies.
- The other probes (identity strings, reminder phrases) are deliberately crude: they estimate how many checks a code
  path could decide, not how good a final design would be.
Read only. Standard library only. No LLM call, no network (an audit hook refuses every socket connection).
Reads the 4,903 offline step records (frozen TGR, train) with their history. Writes only output/logs/v2_i1_probes.json.

Run from predicate_correctness/:
    python3 -B scoring/idea_v2_i1_probes.py > output/logs/v2_i1_probes.log 2>&1
"""
from __future__ import annotations

import collections
import importlib
import importlib.util
import json
import os
import re
import sys
import time
import types as _types

sys.dont_write_bytecode = True


def _no_network(event, args):
    if event in ("socket.connect", "socket.getaddrinfo", "socket.sendto", "socket.sendmsg"):
        raise RuntimeError(f"network refused by idea_v2_i1_probes.py ({event})")


sys.addaudithook(_no_network)

PC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC not in sys.path:
    sys.path.insert(0, PC)

from state_tracker import paths                                     # noqa: E402
from state_tracker.load_steps import read_steps                     # noqa: E402
from state_tracker.tgr_to_aspm import load_rule_set, to_aspm        # noqa: E402
from state_tracker.decide_again import decide, judge_values, replaced  # noqa: E402
from state_tracker.state import build_state                         # noqa: E402

GOLD_DIR = os.path.join(paths.FROM_SA, "gold")
GOLD_V2 = os.path.join(paths.FROM_SA, "scoring", "policies", "gold_v2", "checks.py")
OUT_JSON = os.path.join(paths.LOGS_DIR, "v2_i1_probes.json")
CFG = {"airline": {"current_time": "2024-05-15T15:00:00"}, "retail": {}}
VN = {True: "T", False: "F", None: "U"}
WRITES = {"retail": {"cancel_pending_order", "exchange_delivered_order_items", "modify_pending_order_address",
                     "modify_pending_order_items", "modify_pending_order_payment", "modify_user_address",
                     "return_delivered_order_items"},
          "airline": {"book_reservation", "update_reservation_flights", "update_reservation_baggages",
                      "update_reservation_passengers", "cancel_reservation"}}
CONF_PRED = {"retail": "user_explicitly_confirmed_pending_action",
             "airline": "pending_database_change_details_listed_and_explicitly_confirmed"}


def load_gold_modules():
    """(gold v1 airline PREDICATES, gold v2 PREDICATES), loaded with temporary stubs (scoring use only)."""
    clash = [m for m in sys.modules if m == "agent" or m.startswith("agent.")]
    if clash:
        raise RuntimeError(f"agent.* already loaded: {clash}")
    try:
        pkg = _types.ModuleType("agent")
        pkg.__path__ = []
        sub = _types.ModuleType("agent.predicates")
        sub.__path__ = [GOLD_DIR]
        pkg.predicates = sub
        sys.modules["agent"], sys.modules["agent.predicates"] = pkg, sub
        v1 = dict(importlib.import_module("agent.predicates.airline").PREDICATES)
        spec = importlib.util.spec_from_file_location("i1_gold_v2_checks", GOLD_V2)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        v2 = dict(mod.PREDICATES)
    finally:
        for m in [m for m in sys.modules if m == "agent" or m.startswith("agent.")]:
            del sys.modules[m]
    return v1, v2


def text(m):
    c = m.get("content")
    return c if isinstance(c, str) else ""


REMIND = re.compile(
    r"(\ball (?:the |of the )?(?:items?|products?)\b|\bany other (?:items?|products?)\b|\bevery item\b|"
    r"\banything else\b.{0,60}\b(?:modif|exchang|chang|includ)|\b(?:other|additional|more) items?\b.{0,60}"
    r"\b(?:modif|exchang|chang|includ)|\bincluded? all\b|\ball (?:items?|changes) (?:you|to be)\b)", re.I | re.S)


def main():
    t0 = time.time()
    v1, v2 = load_gold_modules()
    with open(os.path.join(paths.OUTPUT_DIR, "p6_values.jsonl"), encoding="utf-8") as f:
        tracker = collections.defaultdict(dict)
        for line in f:
            r = json.loads(line)
            tracker[r["step_id"]][r["predicate"]] = r["tracker_value"]
    res = collections.defaultdict(collections.Counter)
    examples = collections.defaultdict(list)
    for domain in paths.DOMAINS:
        aspm = to_aspm(load_rule_set(domain))
        for run in paths.RUNS:
            for rec in read_steps(run, domain, with_history=True):
                jv = judge_values(rec)
                tv = replaced(jv, tracker.get(rec["step_id"], {}), "b")
                blocked_trk = not decide(aspm, rec, tv)["allowed"]
                hist, act, kw = rec["history"], rec["action"], rec["kwargs"] or {}
                tc = {"name": act, "arguments": kw, "turn": None}
                cut = bool(rec.get("judge_history_cut"))
                users = [text(m) for m in hist if m.get("role") == "user"]
                agents = [text(m) for m in hist if m.get("role") == "assistant" and text(m).strip()]
                # 1. explicit confirmation: judge vs gold v2 (write checks)
                cp = CONF_PRED[domain]
                if act in WRITES[domain]:
                    g = v2["explicit_user_confirmation"](tc, hist, CFG[domain])
                    if cp in jv:
                        key = f"{domain}:{cp}"
                        res[key][f"judge{VN[jv[cp]]}_gold{VN[g]}"] += 1
                        if blocked_trk:
                            res[key + ":blocked_trk"][f"judge{VN[jv[cp]]}_gold{VN[g]}"] += 1
                        if jv[cp] is not None and g is not None and jv[cp] != g and len(examples[key]) < 6:
                            examples[key].append({"step_id": rec["step_id"], "judge": jv[cp], "gold_v2": g,
                                                  "last_user": (users[-1] if users else "")[:200], "cut": cut})
                    if domain == "retail" and "consequential_action_details_listed" in jv:
                        res["retail:consequential_action_details_listed"][
                            f"judge{VN[jv['consequential_action_details_listed']]}_gold{VN[g]}"] += 1
                # 2. cancellation: judge vs gold (v1 booked_within_24h, v2 dialogue checks) and the database fact
                if act == "cancel_reservation":
                    pairs = (("cancellation_is_within_24_hours", v1["booked_within_24h"]),
                             ("airline_cancelled_flight_confirmed", v2["airline_cancelled_flight"]),
                             ("insured_cancellation_condition_met", v2["cancellation_reason_is_health_or_weather"]))
                    for jp, gf in pairs:
                        if jp in jv:
                            g = gf(tc, hist, CFG[domain])
                            res[f"airline:{jp}"][f"judge{VN[jv[jp]]}_gold{VN[g]}"] += 1
                            if blocked_trk:
                                res[f"airline:{jp}:blocked_trk"][f"judge{VN[jv[jp]]}_gold{VN[g]}"] += 1
                    st = build_state(hist, (act, kw), domain="airline")
                    resv = st.db_get("reservation", kw.get("reservation_id"))
                    fact = None
                    if resv:
                        fact = False
                        for fl in resv.get("flights") or []:
                            fo = st.db_get("flight", fl.get("flight_number")) or {}
                            stt = ((fo.get("dates") or {}).get(fl.get("date")) or {}).get("status")
                            if stt == "cancelled":
                                fact = True
                    res["airline:airline_cancelled_flight_confirmed:db_fact"][
                        f"judge{VN[jv.get('airline_cancelled_flight_confirmed')]}_fact{VN[fact]}"] += 1
                # 3. identity given by the user: plain string match in the user's messages
                if act == "find_user_id_by_email" and "email_identity_provided_by_user" in jv:
                    e = str(kw.get("email") or "").lower()
                    found = bool(e) and any(e in u.lower() for u in users)
                    res["retail:email_identity_provided_by_user"][
                        f"judge{VN[jv['email_identity_provided_by_user']]}_code{VN[found]}" + ("_cut" if cut else "")] += 1
                if act == "find_user_id_by_name_zip" and "name_and_zip_identity_provided_by_user" in jv:
                    parts = [str(kw.get(k) or "").lower() for k in ("first_name", "last_name", "zip")]
                    ut = " ".join(users).lower()
                    found = all(p and p in ut for p in parts)
                    res["retail:name_and_zip_identity_provided_by_user"][
                        f"judge{VN[jv['name_and_zip_identity_provided_by_user']]}_code{VN[found]}" + ("_cut" if cut else "")] += 1
                # 4. reminder: a crude phrase probe over ALL earlier agent messages (no 24,000-character cut)
                for rp in ("agent_reminded_user_to_include_all_items_for_modification",
                           "agent_reminded_user_to_include_all_items_for_exchange"):
                    if rp in jv:
                        found = any(REMIND.search(a) for a in agents)
                        k = f"judge{VN[jv[rp]]}_probe{VN[found]}" + ("_cut" if cut else "")
                        res[f"retail:{rp}"][k] += 1
                        if blocked_trk:
                            res[f"retail:{rp}:blocked_trk"][k] += 1
                        if jv[rp] is False and found and len(examples[rp]) < 5:
                            hit = next(REMIND.search(a) for a in agents if REMIND.search(a))
                            examples[rp].append({"step_id": rec["step_id"], "cut": cut,
                                                 "match": hit.group(0)[:120]})
            print(f"{run}/{domain} done at {time.time() - t0:.1f} s", flush=True)
    out = {"counts": {k: dict(v) for k, v in sorted(res.items())}, "examples": dict(examples),
           "seconds": round(time.time() - t0, 1)}
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
