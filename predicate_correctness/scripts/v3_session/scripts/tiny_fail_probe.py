import json, sys, time
pc = sys.argv[1]
sys.path.insert(0, pc)
sys.dont_write_bytecode = True
from state_tracker.v3 import questions as Q
Q.block_network()
from fork import offline_v3 as O
from guard import tgr_tracker_v3 as G, run_online_v3 as R
def pol(qid, inputs, norm):
    raise Q.RealCallFailed(f"{qid}: 3 attempts failed: RateLimitError 429")
b = Q.FakeBackend(pol)
m = R.TinyMeter(b)
hook = Q.Questions(b, Q.MemoryStore())
G.register()
guards, found, n = {}, None, 0
t0 = time.time()
for conv in O.iter_conversations(["stage_a.luna.tgr_tracker"]):
    if conv.side != O.DEV:
        continue
    g = guards.get(conv.domain) or guards.setdefault(conv.domain, G.build(conv.domain, facts="v3", meaning="tiny", messages="rule", answers=hook))
    for ch in conv.checks():
        n += 1
        m.start_check()
        rec = O.run_guard(g, ch.history, ch.msg, ch.n_exec, ch.past, {})
        fe = (rec.get("v3") or {}).get("fact_errors") or []
        if m.check_failed() or fe:
            try:
                R.finish_v3_check(rec, m)
                raised = None
            except R.TinyQuestionCallFailed as e:
                raised = str(e)[:200]
            found = {"checks_tried": n, "meter_failed": m.check_failed(), "fact_errors": fe[:2],
                     "api_fact_errors": sum(R.is_api_fact_error(x) for x in fe), "raised": raised,
                     "state_error_checks_if_saved": R.v3_state_error_checks({"attempts": [{"guard": rec}]})}
            break
    if found or n > 400:
        break
print(json.dumps({"found": found, "checks": n, "seconds": round(time.time() - t0, 1)}, default=str))
