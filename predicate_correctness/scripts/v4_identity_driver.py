"""Tracker v4 identity check, the Python part (scripts/v4_identity_check.sh runs it; do not run it by hand).

From scripts/v3_session/b3/tools/identity_check.sh, scripts/v3_session/... fake_b3_driver (the scripted user) and the
equality-check driver of tests/test_v3_run_online.py. Question: do the three arms that v4 does not change (none,
direct, tgr_frozen) give the same records under the v4 runner (guard/run_online_v4.py) as under the v3 runner
(guard/run_online_v3.py)?

  run <v3|v4> <sandbox predicate_correctness> <out root>
      Inside a SANDBOX COPY of predicate_correctness (made by the shell script; never the real tree): the network is
      blocked (questions.block_network), the runner's sandbox write guard is on (writes only under the copy's
      output/eval_v<3|4>/dryrun/), a FAKE Azure client is behind every LLM seam (agent, judge, Direct; no real client
      is ever built), the tiny questions get the runner's sandbox fake answers, and the user simulator is SCRIPTED:
      tau_bench.envs.get_env is wrapped so every env is built with user_strategy="human" and its user is replaced by a
      stand-in (no LLM user is ever built). Step B1 (v3) / B1v4 (v4) with --task-ids retail:4,airline:4, 1 try; v3:
      all five arms of its runner; v4: the sandbox-only --arms V4_ARMS (the P10 arm plan runs only direct_facts_v4
      and tgr_tracker_v4 in B1v4, so the compared arms are asked for by name). Writes <out root>/driver_result.json.
  compare <v3 out root> <v4 out root> <summary.json>
      Standard library only. For each of none, direct, tgr_frozen and each (domain, task, trial): the v4 episode line
      equals the v3 one, byte for byte after the timing fields (TIMING_KEYS) are left out and the v4-only top fields
      (V4_ADDED_KEYS: the conversation id) are set aside; the judge cache records (system, user, params) of each arm
      are equal too (none has none). step / run_id (LABEL_KEYS) differ by design: they are checked to be B1 / B1v4 and
      each driver's own run id, then set aside. Also: both drivers saw 0 LLM-user calls, 0 unknown calls, at most the
      one refused urllib3 IPv6 probe (ALLOWED_NET_EVENTS) and 0 writes outside the copy's dry-run folder. Exit 1 if
      anything differs.
No real LLM call, no network, no gold code (the sandbox copy has no gold folder).
"""
from __future__ import annotations

import json
import os
import sys

sys.dont_write_bytecode = True
TIMING_KEYS = ("seconds", "api_seconds", "latency", "seconds_facts")      # as run_online_v3 / v4 TIMING_KEYS
SAME_ARMS = ("none", "direct", "tgr_frozen")
# P10: v4's B1v4 runs only direct_facts_v4 + tgr_tracker_v4; the identity run asks for the compared arms and the two
# v4 arms with the runner's sandbox-only --arms
V4_ARMS = "none,direct,tgr_frozen,direct_facts_v4,tgr_tracker_v4"
V4_ADDED_KEYS = ("conversation_id",)        # code_change_map.md / run_online_v4.py: new on every v4 episode line
LABEL_KEYS = ("step", "run_id")             # differ by design (B1 vs B1v4, fresh run ids): checked apart, not compared
# urllib3's import-time IPv6 probe (socket.socket(AF_INET6), refused by the block before any connect): the one
# allowed event, as tests/test_v3_run_online.py:1092-1094 and tests/test_v4_run_online.py:965
ALLOWED_NET_EVENTS, MAX_NET_EVENTS = {"socket.__new__"}, 1
STEP = {"v3": "B1", "v4": "B1v4"}
TASK_IDS = "retail:4,airline:4"


# ================================================================================================ run (venv)
def run(mode: str, pc: str, out: str) -> int:
    import contextlib
    import hashlib
    import io
    import types
    pc = os.path.realpath(pc)
    out = os.path.realpath(out)
    sys.path.insert(0, pc)
    writes = []

    def _writes(event, args):
        if event == "open" and len(args) >= 3 and isinstance(args[0], (str, bytes)):
            m, fl = args[1], args[2]
            if (isinstance(m, str) and any(c in m for c in "wax+")) or (isinstance(fl, int) and fl & (
                    os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC)):
                writes.append(os.path.realpath(os.fsdecode(args[0])))

    sys.addaudithook(_writes)
    from state_tracker.v3 import questions as Q
    Q.block_network()
    if mode == "v3":
        from guard import run_online_v3 as R
    else:
        from guard import run_online_v4 as R
    if not os.path.realpath(R.__file__).startswith(pc + os.sep):
        raise SystemExit(f"the runner is not the sandbox copy's: {R.__file__}")
    if not (out + os.sep).startswith(os.path.realpath(R.DRYRUN_ROOT) + os.sep):
        raise SystemExit(f"{out} is not under the copy's {R.DRYRUN_ROOT}")
    R.install_sandbox()
    from guard import runner_path
    runner_path.setup()
    from exp_core import models

    O = types.SimpleNamespace
    log = {"judge": 0, "direct": 0, "agent": 0, "user_llm": 0, "user_scripted": 0, "other": 0}

    def usage():
        return O(input_tokens=1000, output_tokens=100, output_tokens_details=O(reasoning_tokens=7),
                 input_tokens_details=O(cached_tokens=0))

    class Resp:
        def __init__(self, text, output=()):
            self.output_text, self.output, self.usage, self.status = text, list(output), usage(), "completed"

        def model_dump(self, mode=None, **_):
            return {"output_text": self.output_text, "fake": True}

    def preds(user):
        s = user.rfind("\nPredicates to decide:\n")
        e = user.find("\n\nFor every predicate return", s)
        if s < 0 or e < 0:
            return []
        return [ln[2:].split(":", 1)[0].strip() for ln in user[s:e].splitlines()[2:]
                if ln.startswith("- ") and ":" in ln]

    read = {"retail": ("find_user_id_by_email", {"email": "nobody@example.com"}),
            "airline": ("get_user_details", {"user_id": "nobody_1234"})}
    write = {"retail": ("cancel_pending_order", {"order_id": "#W0000000", "reason": "no longer needed"}),
             "airline": ("cancel_reservation", {"reservation_id": "ZZZ999"})}

    class Responses:
        def create(self, **kw):
            items = kw.get("input") or []
            if "text" in kw:
                name = kw["text"]["format"]["name"]
                user = items[1]["content"]
                if name == "predicate_values":
                    log["judge"] += 1
                    return Resp(json.dumps({"predicates": [{"name": n, "value": "true", "evidence": "fake"}
                                                           for n in preds(user)]}))
                if name == "direct_decision":
                    log["direct"] += 1
                    act = user.rsplit("next action", 1)[-1]
                    unsafe = "cancel_pending_order" in act or "cancel_reservation" in act
                    return Resp(json.dumps({"safe": not unsafe, "violated_policy_statements":
                                            ["fake: confirm first"] if unsafe else [], "explanation": "fake"}))
                log["other"] += 1
                raise RuntimeError(f"unexpected structured call {name}")
            if kw.get("tools"):
                log["agent"] += 1
                names = {t["name"] for t in kw["tools"]}
                dom = "retail" if "cancel_pending_order" in names else "airline"
                first = next((i.get("content") for i in items if i.get("role") == "user"), "") or ""
                n_fc = sum(1 for i in items if i.get("type") == "function_call")
                cid = f"call_{n_fc}_{hashlib.sha256(first.encode()).hexdigest()[:8]}"
                if n_fc >= 2:
                    return Resp("Done. Anything else?", [O(type="message")])
                tool, args = (read if n_fc == 0 else write)[dom]
                return Resp("", [O(type="function_call", call_id=cid, name=tool, arguments=json.dumps(args))])
            log["user_llm"] += 1                       # must stay 0: the user is scripted
            raise RuntimeError("an LLM user call reached the fake client (the user should be scripted)")

    class Client:
        def __init__(self):
            self.responses = Responses()

        def with_options(self, **_):
            return self

    models._base_client = Client()

    class ScriptedUser:
        """Stands in for the user simulator: no LLM."""

        def reset(self, instruction=None):
            log["user_scripted"] += 1
            return "Hi, please cancel my booking for me."

        def step(self, content):
            log["user_scripted"] += 1
            return "###STOP###"

        def get_total_cost(self):
            return 0.0

    import tau_bench.envs as tenvs
    orig_get_env = tenvs.get_env
    strategies = []

    def get_env_scripted(env_name, user_strategy, user_model, task_split, user_provider=None, task_index=None):
        strategies.append([env_name, user_strategy, task_split, task_index])
        env = orig_get_env(env_name, user_strategy="human", user_model=user_model, task_split=task_split,
                           user_provider=user_provider, task_index=task_index)
        env.user = ScriptedUser()
        return env

    tenvs.get_env = get_env_scripted
    step = STEP[mode]
    rid = R.new_run_id(step)
    so = io.StringIO()
    err = None
    with contextlib.redirect_stdout(so):
        try:
            R.main(["run", "--step", step, "--run-id", rid, "--shard", "0/1", "--workers", "2", "--task-ids", TASK_IDS,
                    "--out-root", out, "--approval", "identity check with fake LLMs, no money"]
                   + (["--arms", V4_ARMS] if mode == "v4" else []))
        except BaseException as e:  # noqa: BLE001 (reported in the result)
            err = f"{type(e).__name__}: {e}"
    dry = os.path.realpath(R.DRYRUN_ROOT)
    res = {"mode": mode, "step": step, "run_id": rid, "runner": os.path.realpath(R.__file__), "error": err,
           "calls": log, "network_events": Q.network_events(), "get_env_calls": strategies,
           "writes_outside_dryrun": sorted({w for w in writes if not (w == dry or w.startswith(dry + os.sep))
                                            and not w.startswith("/dev/")}),
           "dryrun_root": dry, "stdout_tail": so.getvalue()[-4000:]}
    with open(os.path.join(out, "driver_result.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, default=str)
    return 0 if err is None else 1


# ================================================================================================ compare (stdlib)
def _strip(x):
    if isinstance(x, dict):
        return {k: _strip(v) for k, v in x.items() if k not in TIMING_KEYS}
    if isinstance(x, list):
        return [_strip(v) for v in x]
    return x


def _dump(x) -> str:
    return json.dumps(_strip(x), ensure_ascii=False, sort_keys=False, default=str)


def _lines(path: str) -> list:
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def diff_paths(a, b, path="", out=None, limit=20):
    """Up to `limit` paths where two JSON values differ (after _strip)."""
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in list(a) + [k for k in b if k not in a]:
            if k not in a or k not in b:
                out.append(f"{path}/{k}: only in {'v4' if k in b else 'v3'}")
            else:
                diff_paths(a[k], b[k], f"{path}/{k}", out, limit)
        if list(a) != list(b) and set(a) == set(b):
            out.append(f"{path}: key order differs")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: length {len(a)} vs {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diff_paths(x, y, f"{path}[{i}]", out, limit)
    elif json.dumps(a, default=str) != json.dumps(b, default=str):
        out.append(f"{path}: {json.dumps(a, default=str)[:120]} != {json.dumps(b, default=str)[:120]}")
    return out[:limit]


def cache_records(folder: str) -> list:
    """(system, user, params) of every judge cache record under folder, canonical JSON, sorted."""
    out = []
    if not os.path.isdir(folder):
        return out
    for dp, dns, fns in os.walk(folder):
        dns.sort()
        for fn in sorted(fns):
            if fn.endswith(".json"):
                with open(os.path.join(dp, fn), encoding="utf-8") as f:
                    rec = json.load(f)
                out.append(json.dumps({"system": rec.get("system"), "user": rec.get("user"),
                                       "params": rec.get("params")}, sort_keys=True, ensure_ascii=False))
    return sorted(out)


def episodes(out_root: str, mode: str, rid: str) -> dict:
    run_dir = os.path.join(out_root, STEP[mode], rid)
    got = {}
    for arm in SAME_ARMS:
        for rec in _lines(os.path.join(run_dir, arm, "episodes_shard0of1.jsonl")):
            got[(arm, rec.get("env"), rec.get("task_index"), rec.get("trial"))] = rec
    return got


def compare(v3_out: str, v4_out: str, summary_path: str) -> int:
    r3 = json.load(open(os.path.join(v3_out, "driver_result.json"), encoding="utf-8"))
    r4 = json.load(open(os.path.join(v4_out, "driver_result.json"), encoding="utf-8"))
    e3, e4 = episodes(v3_out, "v3", r3["run_id"]), episodes(v4_out, "v4", r4["run_id"])
    checks = []
    for key in sorted(set(e3) | set(e4), key=str):
        a, b = e3.get(key), e4.get(key)
        c = {"arm": key[0], "env": key[1], "task": key[2], "trial": key[3]}
        if a is None or b is None:
            c.update(equal=False, detail="missing in " + ("v3" if a is None else "v4"))
        else:
            added = [k for k in b if k not in a]
            labels_ok = (a.get("step"), a.get("run_id"), b.get("step"), b.get("run_id")) == (
                STEP["v3"], r3["run_id"], STEP["v4"], r4["run_id"])
            a2 = {k: v for k, v in a.items() if k not in LABEL_KEYS}
            b2 = {k: v for k, v in b.items() if k not in V4_ADDED_KEYS and k not in LABEL_KEYS}
            c.update(equal=_dump(a2) == _dump(b2), v4_added_keys=added, labels_ok=labels_ok,
                     unexpected_added_keys=[k for k in added if k not in V4_ADDED_KEYS],
                     attempts=len(a.get("attempts") or []), blocks=a.get("n_blocks"), error_v3=a.get("error"),
                     error_v4=b.get("error"), differences=diff_paths(_strip(a2), _strip(b2)))
            c["equal"] = c["equal"] and labels_ok and not c["unexpected_added_keys"]
        checks.append(c)
    cache_checks = []
    for arm in SAME_ARMS:
        a_ = cache_records(os.path.join(v3_out, "_llmcache", f"v3_{r3['run_id']}", arm, "structured"))
        b_ = cache_records(os.path.join(v4_out, "_llmcache", f"v4_{r4['run_id']}", arm, "structured"))
        cache_checks.append({"arm": arm, "records_v3": len(a_), "records_v4": len(b_), "equal": a_ == b_,
                             "want_records": arm != "none", "has_records_if_wanted": (len(a_) > 0) == (arm != "none")})
    safety = {}
    for name, r in (("v3", r3), ("v4", r4)):
        safety[name] = {"error": r.get("error"), "user_llm_calls": r["calls"].get("user_llm"),
                        "unknown_calls": r["calls"].get("other"), "network_events": len(r.get("network_events") or []),
                        "network_event_kinds": sorted(set(r.get("network_events") or [])),
                        "writes_outside_dryrun": r.get("writes_outside_dryrun"),
                        "get_env_strategies": sorted({x[1] for x in r.get("get_env_calls") or []}),
                        "fake_calls": r["calls"]}
    safe = all(s["error"] is None and s["user_llm_calls"] == 0 and s["unknown_calls"] == 0
               and s["network_events"] <= MAX_NET_EVENTS and set(s["network_event_kinds"]) <= ALLOWED_NET_EVENTS
               and not s["writes_outside_dryrun"] for s in safety.values())
    want_lines = len(SAME_ARMS) * 2
    ok = (safe and len(checks) == want_lines and all(c["equal"] for c in checks)
          and all(c["equal"] and c["has_records_if_wanted"] for c in cache_checks))
    summary = {"all_equal": ok, "n_checks": len(checks), "want_checks": want_lines, "checks": checks,
               "cache_checks": cache_checks, "safety": safety, "real_llm_calls": 0,
               "note": "fake Azure client and scripted user in a sandbox copy; network blocked",
               "timing_keys_left_out": list(TIMING_KEYS), "v4_added_keys_set_aside": list(V4_ADDED_KEYS),
               "run_ids": {"v3": r3["run_id"], "v4": r4["run_id"]}}
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1, default=str)
    print(f"identity check: {'PASS' if ok else 'FAIL'}: {sum(c['equal'] for c in checks)}/{len(checks)} episode "
          f"checks, {sum(c['equal'] for c in cache_checks)}/{len(cache_checks)} cache checks, safety "
          f"{'ok' if safe else 'NOT ok'}; {summary_path}")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) == 5 and sys.argv[1] == "run" and sys.argv[2] in STEP:
        sys.exit(run(sys.argv[2], sys.argv[3], sys.argv[4]))
    if len(sys.argv) == 5 and sys.argv[1] == "compare":
        sys.exit(compare(sys.argv[2], sys.argv[3], sys.argv[4]))
    sys.exit("usage: v4_identity_driver.py run <v3|v4> <sandbox pc> <out root> | compare <v3 out> <v4 out> <summary>")
