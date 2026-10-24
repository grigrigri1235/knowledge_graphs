"""R3 reference for the Part 4 audit (eval v2), parts B and C: the frozen TGR guard and the TGR + tracker guard.

Independent of the wrapper: guard/run_online.py and the new eval-v2 code are not read or imported. Uses only the
copied runner (from_shieldagent/runner/, through guard/runner_path.py) and the frozen rule set
(from_shieldagent/rules/<domain>/). No LLM call: the judge's LLM call is replaced by a capture function that records
the prompt and returns the values saved in the guard record; any other LLM call fails; the network is blocked.

B (frozen TGR): every guard check of the partner's saved runs from_shieldagent/runs/{luna_train_v5,nano_train,luna_val}
  /<domain>/tgr/episodes.jsonl is run again through the copied runner's own TGR guard, built as
  exp_core/run_online.py builds it, on the executed history before the check:
  1. the judge prompt is rebuilt; its hashes are recorded, and the runner's judge cache key is looked up in the
     partner's judge cache (~/ShieldAgent/output/tgr/_llmcache/structured, read only): the cached prompt must equal
     the rebuilt one, and the cached answer must equal the saved judge values;
  2. decision, margin, MLN details, violated rules and feedback text are recomputed from the saved judge values and
     compared with the saved record.
C (TGR + tracker): the same for every guard check of output/online/{p10_luna_train,p10_nano_train,p10_luna_val}/
  <domain>/tgr_tracker/: decision from the used values (guard.judge) must equal the saved record; the decision from
  the judge's own values (guard.tracker.judge_values) is the alternative; the prompt is looked up in our judge cache
  output/_llmcache/<tag>/structured. Also the frozen inputs' sha256.

Run from predicate_correctness/ (standard library only):
  PYTHONDONTWRITEBYTECODE=1 /home/azureuser/miniconda3/bin/python3 -B tests/audit_v2_ref_guards.py
Outputs (output/eval_v2/checks/ref/): ref_guards.md, ref_guards_build.json, ref_guards_frozen.jsonl (sample, full
detail), ref_guards_frozen_all.jsonl (every check, short), ref_guards_tracker.jsonl, ref_guards_tracker_all.jsonl.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import random
import socket
import subprocess
import sys
import time
import types
from collections import Counter, defaultdict

sys.dont_write_bytecode = True


def _no_network(*_a, **_k):
    raise RuntimeError("network blocked in the R3 reference (no LLM call allowed)")


socket.socket.connect = _no_network                                  # type: ignore[assignment]
socket.socket.connect_ex = _no_network                               # type: ignore[assignment]
socket.create_connection = _no_network                               # type: ignore[assignment]

PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from guard import runner_path                                        # noqa: E402  (only the path helper)

RUNNER_DIR = runner_path.setup()

from repro_runtime import calls                                      # noqa: E402  (runner copy)


class _NoLLM:
    """Any structured LLM call that is not the captured judge fails (never a client, never a cache write)."""
    model, max_output_tokens = "no-llm", 16000
    cache_dir = os.path.join(PC_DIR, "output", "_r3_no_llm_never_written")

    def call(self, **_):
        raise AssertionError("an LLM call was attempted in the R3 reference")


calls._llm = _NoLLM()

import exp_core.run_online as runner_run_online                      # noqa: E402  (runner copy; main() not run)
import method_tgr.llm as tgr_llm                                     # noqa: E402
import method_tgr.runtime as tgr_runtime                             # noqa: E402
from method_tgr import prompts as tgr_prompts                        # noqa: E402
from method_tgr.runtime import JUDGE_SCHEMA, VALUE                   # noqa: E402
from repro_core.llm import llm_config                                # noqa: E402
from repro_core.taubench_steps import render_history                 # noqa: E402
from repro_online.guards import TGRGuard                             # noqa: E402

from state_tracker import tau_copy                                   # noqa: E402  (copied tool schemas only)

OUT_DIR = os.path.join(PC_DIR, "output", "eval_v2", "checks", "ref")
FS_DIR = os.path.join(PC_DIR, "from_shieldagent")
RULES_DIR = os.path.join(FS_DIR, "rules")
DOMAINS = ("airline", "retail")
FROZEN_RUNS = ("luna_train_v5", "nano_train", "luna_val")
TRACKER_TAGS = ("p10_luna_train", "p10_nano_train", "p10_luna_val")
PARTNER_CACHE = os.path.expanduser("~/ShieldAgent/output/tgr/_llmcache/structured")      # read only
OUR_CACHE = os.path.join(PC_DIR, "output", "_llmcache")                                   # <tag>/structured
GUARD_MODEL = "gpt-6-luna"           # profiles luna-dev and nano-agent-luna: guard role (model_profiles.json)
SEED = 20261022
FIELDS = ["step_index", "kind", "name", "action_text", "matched", "trace_position", "circuit", "judge", "mln",
          "margin", "allowed_eps0", "violated_rules", "unknown_predicates", "feedback_text", "action_allowed",
          "epsilon", "reason", "trace_len_before"]
NOT_SAVED = "(judge evidence not saved: the guard used the tracker's value)"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_text(s: str) -> str:
    return sha256_bytes(s.encode("utf-8"))


def sha256_file(path: str) -> str:
    with open(path, "rb") as f:
        return sha256_bytes(f.read())


def norm(x):
    return json.loads(json.dumps(x, ensure_ascii=False, default=str))


def out_path(name: str) -> str:
    p = os.path.abspath(os.path.join(OUT_DIR, name))
    if os.path.dirname(p) != OUT_DIR or not name.startswith("ref_guards"):
        raise RuntimeError(f"refusing to write {p}")
    return p


# ------------------------------------------------------------------------------------------------ the captured judge
class CaptureJudge:
    """Stands in for method_tgr.llm.structured: records the prompt, returns the given values (as the LLM would)."""

    INV = {True: "true", False: "false", None: "unknown"}

    def __init__(self):
        self.values, self.calls = {}, []

    def __call__(self, meter, *, stage, system, user, schema, schema_name, effort, max_output_tokens=None):
        self.calls.append({"stage": stage, "system": system, "user": user, "schema": schema,
                           "schema_name": schema_name, "effort": effort, "max_output_tokens": max_output_tokens})
        return {"predicates": [{"name": n, "value": self.INV[v["value"]], "evidence": v["evidence"]}
                               for n, v in self.values.items()]}


CAPTURE = CaptureJudge()
tgr_llm.structured = CAPTURE                                         # TGR._judge calls llm.structured(...)
tgr_runtime.time = types.SimpleNamespace(time=time.time, sleep=lambda s: None)   # no 10 s retry sleeps
MAX_OUT = llm_config()["max_output_tokens"]


def build_guard(domain: str):
    """The TGR guard exactly as the copied runner builds it (exp_core/run_online.py main -> build_guard ->
    repro_online.guards.build -> TGRGuard), with --guard tgr and --rules-dir = the frozen rule set."""
    tools_info = tau_copy.tools_info(domain)
    rules_dir = os.path.join(RULES_DIR, domain)
    g = runner_run_online.build_guard("tgr", domain, tools_info, None, rules_dir)
    assert type(g) is TGRGuard, type(g)
    return g, tools_info, rules_dir


def recheck(guard, prefix, msg, n_exec, past, values):
    """One guard check again, the way run_episode calls it: guard.check(state, executed, msg, n_exec)."""
    CAPTURE.values = values
    CAPTURE.calls = []
    state = guard.new_episode()
    state.trace = copy.deepcopy(past)
    rec = guard.check(state, list(prefix), copy.deepcopy(msg), n_exec)
    return norm(rec), list(CAPTURE.calls)


def prompt_info(call) -> dict:
    s, u = call["system"], call["user"]
    params = {"model": GUARD_MODEL, "effort": call["effort"], "max_output_tokens": call["max_output_tokens"] or MAX_OUT,
              "schema_name": call["schema_name"], "schema": call["schema"], "sample": 0}
    key = sha256_bytes(json.dumps({"system": s, "user": u, "params": params}, sort_keys=True).encode())
    return {"prompt_sha256": sha256_bytes(json.dumps({"system": s, "user": u}, sort_keys=True).encode()),
            "system_sha256": sha256_text(s), "user_sha256": sha256_text(u), "system_len": len(s), "user_len": len(u),
            "judge_cache_key": key, "model": GUARD_MODEL, "effort": call["effort"], "schema_name": call["schema_name"],
            "max_output_tokens": params["max_output_tokens"], "stage": call["stage"]}


def cache_lookup(root: str, key: str, call: dict, names: list) -> dict:
    path = os.path.join(root, key[:2], key + ".json")
    if not os.path.exists(path):
        return {"found": False}
    with open(path, encoding="utf-8") as f:
        r = json.load(f)
    got = {p["name"]: {"value": VALUE[p["value"]], "evidence": p["evidence"]} for p in r["parsed"]["predicates"]
           if p["name"] in names}
    for n in names:
        got.setdefault(n, {"value": None, "evidence": "(not returned by the judge)"})
    return {"found": True, "system_equal": r.get("system") == call["system"], "user_equal": r.get("user") == call["user"],
            "model": r.get("params", {}).get("model"), "stage": r.get("stage"), "got": got}


def load_episodes(path: str):
    eps, seen, n_err, n_dup = [], set(), 0, 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            ep = json.loads(line)
            if ep.get("error") is not None:
                n_err += 1
                continue
            k = (ep["task_index"], ep["trial"])
            if k in seen:
                n_dup += 1
                continue
            seen.add(k)
            eps.append(ep)
    return eps, n_err, n_dup


def compare(saved: dict, rebuilt: dict, strip_source: bool) -> list:
    bad = []
    for f in FIELDS:
        a, b = saved.get(f), rebuilt.get(f)
        if f == "judge" and strip_source and a is not None:
            a = {n: {k: v for k, v in d.items() if k != "source"} for n, d in a.items()}
        if a != b:
            bad.append(f)
    return bad


def rule_ids(rec: dict) -> list:
    return [v["rule_id"] for v in rec.get("violated_rules") or []]


def summary_of(rec: dict) -> dict:
    fb = rec.get("feedback_text")
    return {"action_allowed": rec.get("action_allowed"), "margin": rec.get("margin"), "violated_rule_ids": rule_ids(rec),
            "unknown_predicates": rec.get("unknown_predicates"), "feedback_sha256": sha256_text(fb) if fb else None}


def judge_called_saved(g: dict) -> bool:
    return any(c.get("stage") == "tgr_judge" for c in g.get("calls") or [])


def names_of(guard, rec: dict) -> list:
    aspm = guard.tgr.aspm
    return sorted({n for r in rec.get("circuit") or [] for n in aspm.rules[r].atoms} - aspm.action_predicates)


# ------------------------------------------------------------------------------------------------ one source file
def run_source(kind: str, run: str, domain: str, guard, rng: random.Random):
    """kind 'frozen' (partner tgr) or 'tracker' (our tgr_tracker). Returns (all rows, sample rows, stats)."""
    if kind == "frozen":
        path = os.path.join(FS_DIR, "runs", run, domain, "tgr", "episodes.jsonl")
        cache_root = PARTNER_CACHE
    else:
        path = os.path.join(PC_DIR, "output", "online", run, domain, "tgr_tracker", "episodes.jsonl")
        cache_root = os.path.join(OUR_CACHE, run, "structured")
    src = os.path.relpath(path, PC_DIR)
    eps, n_err, n_dup = load_episodes(path)
    st = Counter()
    st["episodes"], st["error_lines_dropped"], st["duplicate_lines_dropped"] = len(eps), n_err, n_dup
    rows, details, cats = [], {}, defaultdict(list)
    for ep in eps:
        atts = ep["attempts"]
        if len(ep["messages"]) != 2 + 2 * len(atts):
            st["index_rule_broken"] += 1
        for i, a in enumerate(atts):
            g = a.get("guard")
            if g is None:
                st["attempts_without_guard_record"] += 1
                continue
            st["checks"] += 1
            prefix = ep["executed"][:a["executed_prefix_len"]]
            msg = ep["messages"][2 + 2 * i]
            past = [x["guard"]["trace_position"] for x in atts[:i] if not x["blocked"]]
            used = g.get("judge") or {}
            values = {n: {"value": v["value"], "evidence": v["evidence"]} for n, v in used.items()}
            try:
                rec, cl = recheck(guard, prefix, msg, a["exec_step"], past, values)
            except Exception as e:  # noqa: BLE001 - counted and listed, never hidden
                st["recheck_errors"] += 1
                rows.append({"src": src, "task": ep["task_index"], "trial": ep["trial"], "i": i,
                             "error": f"{type(e).__name__}: {e}"})
                continue
            bad = compare(g, rec, strip_source=(kind == "tracker"))
            hist_len = len(render_history(prefix))
            names = names_of(guard, rec)
            tr = g.get("tracker") or {}
            skipped = bool(tr.get("judge_skipped"))
            saved_called = judge_called_saved(g)
            row = {"src": src, "task": ep["task_index"], "trial": ep["trial"], "i": i, "exec_step": a["exec_step"],
                   "attempt": a["attempt"], "kind": g.get("kind"), "name": g.get("name"),
                   "blocked": a["blocked"], "cap_override": a["cap_override"], "allowed": g.get("action_allowed"),
                   "judge_saved": saved_called, "judge_rebuilt": bool(cl), "fields_ok": not bad, "bad": bad}
            st["past_len_ok"] += len(past) == g.get("trace_len_before")
            st["fields_equal"] += not bad
            st["judge_called_saved"] += saved_called
            st["judge_call_rebuilt"] += bool(cl)
            st["truncated_history"] += hist_len > 24000
            if kind == "frozen" and saved_called != bool(cl):
                st["judge_called_mismatch"] += 1
            if kind == "tracker" and saved_called != (bool(cl) and not skipped):
                st["judge_called_mismatch"] += 1
            pinfo, cinfo = None, None
            if cl:
                pinfo = prompt_info(cl[0])
                row["psha"], row["key"] = pinfo["prompt_sha256"], pinfo["judge_cache_key"]
                if len(cl) != 1:
                    st["more_than_one_judge_call"] += 1
            if cl and saved_called:
                c = cache_lookup(cache_root, pinfo["judge_cache_key"], cl[0], names)
                if kind == "frozen":
                    want = values
                else:
                    jv = tr.get("judge_values") or {}
                    want = {n: {"value": jv.get(n), "evidence": used[n]["evidence"]} for n in used}
                if c["found"]:
                    got = c.pop("got")
                    c["values_equal"] = all(got[n]["value"] is (want.get(n) or {}).get("value") for n in names) \
                        and set(want) == set(names)
                    jv0 = tr.get("judge_values") or {}
                    same = [n for n in names if kind == "frozen"
                            or (n in used and used[n]["value"] is jv0.get(n))]
                    c["evidence_equal"] = all(n in want and got[n]["evidence"] == want[n]["evidence"] for n in same)
                    ok = c["system_equal"] and c["user_equal"] and c["values_equal"] and c["evidence_equal"]
                    st["cache_found"] += 1
                    st["cache_prompt_equal"] += c["system_equal"] and c["user_equal"]
                    st["cache_values_equal"] += c["values_equal"]
                    st["cache_evidence_equal"] += c["evidence_equal"]
                    st["cache_all_equal"] += ok
                    row["cache"] = "equal" if ok else "DIFF"
                else:
                    st["cache_missing"] += 1
                    row["cache"] = "missing"
                cinfo = c
            alt = None
            if kind == "tracker":
                jv = tr.get("judge_values")
                cons = []
                for n, d in used.items():
                    if (d.get("source") == "tracker") != (n in (tr.get("replaced") or [])):
                        cons.append(f"{n}: source vs replaced")
                    if jv is not None and ((n in (tr.get("changed") or []))
                                           != (d.get("source") == "tracker" and d["value"] is not jv.get(n))):
                        cons.append(f"{n}: changed list")
                if cons:
                    st["tracker_lists_inconsistent"] += 1
                if used and jv is not None:
                    alt_vals = {n: {"value": jv.get(n),
                                    "evidence": d["evidence"] if d["value"] is jv.get(n) else NOT_SAVED}
                                for n, d in used.items()}
                    rec_alt, cl_alt = recheck(guard, prefix, msg, a["exec_step"], past, alt_vals)
                    if cl and cl_alt and prompt_info(cl_alt[0])["prompt_sha256"] != pinfo["prompt_sha256"]:
                        st["alt_prompt_differs"] += 1
                    change = "none"
                    if g["action_allowed"] and not rec_alt["action_allowed"]:
                        change = "block removed"
                    elif not g["action_allowed"] and rec_alt["action_allowed"]:
                        change = "block added"
                    st["checks_with_judge_values"] += 1
                    st["checks_with_changed_value"] += bool(tr.get("changed"))
                    st["decision_" + change.replace(" ", "_")] += 1
                    alt = {**summary_of(rec_alt), "decision_change": change}
                    row["alt_allowed"], row["change"] = rec_alt["action_allowed"], change
                if skipped:
                    st["judge_skipped"] += 1
                row["changed_values"] = tr.get("changed") or []
            rows.append(row)
            # categories for the detailed sample
            judged = bool(cl) and saved_called
            if a["cap_override"]:
                cats["cap_override"].append(len(rows) - 1)
            elif a["blocked"]:
                cats["blocked_retry" if a["attempt"] >= 2 else "blocked_first"].append(len(rows) - 1)
            elif not g.get("circuit"):
                cats["allowed_no_rules"].append(len(rows) - 1)
            elif judged:
                cats["allowed_after_block" if a["attempt"] >= 2 else "allowed_judge"].append(len(rows) - 1)
            if judged and g.get("kind") == "respond":
                cats["respond_judge"].append(len(rows) - 1)
            if judged and hist_len > 24000:
                cats["long_history"].append(len(rows) - 1)
            if alt is not None and alt["decision_change"] == "block removed":
                cats["block_removed"].append(len(rows) - 1)
            if alt is not None and alt["decision_change"] == "block added":
                cats["block_added"].append(len(rows) - 1)
            if alt is not None and row["changed_values"] and alt["decision_change"] == "none":
                cats["value_changed_same_decision"].append(len(rows) - 1)
            details[len(rows) - 1] = {
                "src": src, "run": run, "domain": domain, "guard": "tgr" if kind == "frozen" else "tgr_tracker",
                "task_index": ep["task_index"], "trial": ep["trial"], "attempt_index": i, "exec_step": a["exec_step"],
                "attempt": a["attempt"], "kind": g.get("kind"), "name": g.get("name"), "blocked": a["blocked"],
                "cap_override": a["cap_override"], "executed_prefix_len": a["executed_prefix_len"],
                "trace_len_before": g.get("trace_len_before"), "past_trace_len": len(past),
                "history_rendered_chars": hist_len, "history_truncated": hist_len > 24000,
                "judge_called_saved": saved_called, "judge_called_rebuilt": bool(cl), "predicates": names,
                "prompt": pinfo, "cache": cinfo, "saved": summary_of(g), "rebuilt": summary_of(rec),
                "fields_equal": not bad, "mismatched_fields": bad,
                **({"tracker": {"code_predicates": tr.get("code_predicates"), "replaced": tr.get("replaced"),
                                "changed": tr.get("changed"), "judge_skipped": tr.get("judge_skipped"),
                                "judge_values": tr.get("judge_values"),
                                "used_values": {n: [d["value"], d.get("source")] for n, d in used.items()}},
                    "alternative_from_judge_values": alt} if kind == "tracker" else {}),
            }
    # the sample: fixed seed, per category
    want = ({"allowed_judge": 2, "allowed_no_rules": 1, "blocked_first": 2, "blocked_retry": 2, "cap_override": 3,
             "respond_judge": 1, "long_history": 1, "allowed_after_block": 1} if kind == "frozen" else
            {"allowed_judge": 2, "allowed_no_rules": 1, "blocked_first": 1, "blocked_retry": 1, "cap_override": 2,
             "respond_judge": 1, "long_history": 1, "block_removed": 1, "block_added": 1,
             "value_changed_same_decision": 1})
    picked, sample = set(), []
    for cat, k in want.items():
        pool = [x for x in cats.get(cat, []) if x not in picked]
        for x in rng.sample(pool, min(k, len(pool))):
            picked.add(x)
            sample.append(dict(details[x], category=cat))
    st["sample"] = len(sample)
    st["category_pool_sizes"] = {c: len(v) for c, v in sorted(cats.items())}
    return rows, sample, st


# ------------------------------------------------------------------------------------------------ build info + frozen
def build_info(guards_by_domain: dict) -> dict:
    info = {"how_the_copied_runner_builds_the_tgr_guard": [
        "exp_core/run_online.py main(): models.activate(<profile>, 'guard') -> the guard role's model "
        "(gpt-6-luna in luna-dev and nano-agent-luna); structured calls go to policy_pipeline.llm.LLM("
        "cache_dir=exp_core.models.CACHE_ROOT/structured, model=<guard model>, max_output_tokens=repro_core/config.json "
        "llm.max_output_tokens)",
        "probe = get_env(<env>, user_strategy='llm', user_model=<user model>, user_provider='azure', task_split='test', "
        "task_index=0); tools_info, wiki = probe.tools_info, probe.wiki  (this probe makes 1 user-simulator call)",
        "guard = build_guard(a.guard, a.env, tools_info, a.aspm_dir, a.rules_dir)  -> repro_online.guards.build(name, "
        "domain, tools_info, rules_dir=rules_dir)",
        "guards.build('tgr', ...) -> TGRGuard('tgr', rules_dir or ROOT/tgr_rules/<domain>/full, tools_info) with the "
        "defaults judge_effort='medium', epsilon=0.1",
        "TGRGuard.__init__: rs = load_rule_set(rules_dir/rule_set.json); requires rs.flags a=True, b=True for 'tgr'; "
        "config = TGRConfig(actionable_feedback=True, judge_effort='medium', epsilon=0.1); tgr = TGR(rs, tools_info, "
        "config)  (with flags.a = True, tools_info is not used by TGR)",
        "ONE guard object per process, shared by all worker threads; per conversation state = guard.new_episode() = "
        "method_tgr.runtime.Conversation(trace=[])",
        "episode.run_episode(env, agent_completion, tools_info, wiki, guard, t, max_num_steps=a.max_steps (default 30)), "
        "cap=3 (default); guard.check(state, executed, msg, n_exec) at every agent message; guard.commit(state, rec) "
        "on a cap override",
        "partner runs: --guard tgr; --rules-dir output/tgr/tgr_rules/luna-dev/<domain>/it5 (luna_train_v5) or "
        "tgr_rules/<domain>/frozen (nano_train, luna_val); both byte-identical with from_shieldagent/rules/<domain>/ "
        "(from_shieldagent/PROVENANCE.md, rule_set.json sha256 below)"],
        "judge_call": {"function": "method_tgr.llm.structured(meter, stage='tgr_judge', system, user, "
                                   "schema=JUDGE_SCHEMA, schema_name='predicate_values', effort=config.judge_effort)",
                       "model": GUARD_MODEL, "max_output_tokens": MAX_OUT, "sample": 0,
                       "judge_schema_sha256": sha256_bytes(json.dumps(JUDGE_SCHEMA, sort_keys=True).encode()),
                       "judge_template": "method_tgr/prompts/judge.md",
                       "judge_template_sha256": sha256_file(os.path.join(RUNNER_DIR, "method_tgr", "prompts", "judge.md")),
                       "judge_template_hash16 (prompts.hashes)": tgr_prompts.hashes()["judge"],
                       "history": "render_history(executed[:executed_prefix_len], max_chars=config.history_chars); "
                                  "policy system message left out; '…' + last 24000 chars if longer",
                       "cache_key": "sha256(json.dumps({'system', 'user', 'params': {model, effort, max_output_tokens, "
                                    "schema_name, schema, sample: 0}}, sort_keys=True))"},
        "prompt_hash_definitions": {
            "prompt_sha256": "sha256(json.dumps({'system': system, 'user': user}, sort_keys=True).encode())",
            "system_sha256 / user_sha256": "sha256 of the text, utf-8",
            "judge_cache_key": "the runner's own judge cache key with model gpt-6-luna (file <cache>/<key[:2]>/<key>.json)"},
        "domains": {}}
    for d, (g, tools_info, rules_dir) in guards_by_domain.items():
        rs_path = os.path.join(rules_dir, "rule_set.json")
        aspm = g.tgr.aspm
        man = json.load(open(os.path.join(rules_dir, "manifest.json"), encoding="utf-8"))
        info["domains"][d] = {
            "guard_class": f"{type(g).__module__}.{type(g).__name__}", "guard_name": g.name,
            "tgr_class": f"{type(g.tgr).__module__}.{type(g.tgr).__name__}",
            "config": dataclasses.asdict(g.config), "rules_dir": os.path.relpath(rules_dir, PC_DIR),
            "rule_set_sha256": sha256_file(rs_path), "flags": g.tgr.rule_set["flags"], "grounded": g.tgr.grounded,
            "n_rules": len(aspm.rules), "n_predicates": len(g.tgr.predicates),
            "n_background_facts": len(g.tgr.rule_set.get("background", [])),
            "circuits": {a: len(v) for a, v in sorted(aspm.circuits.items())},
            "all_weights_1": all(aspm.weight(a, r) == 1.0 for a, ids in aspm.circuits.items() for r in ids),
            "tools_info_sha256 (copied tools, json sort_keys)": sha256_text(json.dumps(tools_info, sort_keys=True)),
            "rule_set_manifest_tools_sha256": man["input"]["tools_sha256"],
            "manifest_prompt_hash_judge": man["prompt_hashes"]["judge"]}
    # the copied runner files used here, against from_shieldagent/SHA256SUMS
    sums = {}
    with open(os.path.join(FS_DIR, "SHA256SUMS"), encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2:
                sums[parts[1]] = parts[0]
    files = ["runner/method_tgr/runtime.py", "runner/method_tgr/feedback.py", "runner/method_tgr/llm.py",
             "runner/method_tgr/prompts.py", "runner/method_tgr/prompts/judge.md", "runner/method_tgr/rules.py",
             "runner/repro_online/guards.py", "runner/repro_online/episode.py", "runner/exp_core/run_online.py",
             "runner/exp_core/models.py", "runner/exp_core/model_profiles.json", "runner/repro_runtime/mln.py",
             "runner/repro_runtime/verify.py", "runner/repro_runtime/aspm.py", "runner/repro_runtime/shield.py",
             "runner/repro_runtime/calls.py", "runner/repro_core/taubench_steps.py", "runner/repro_core/ltlf.py",
             "runner/repro_core/config.json", "runner/repro_core/llm.py", "runner/policy_pipeline/llm.py"]
    info["runner_files_sha256"] = {f: {"sha256": sha256_file(os.path.join(FS_DIR, f)),
                                       "equals_SHA256SUMS": sums.get(f) == sha256_file(os.path.join(FS_DIR, f))
                                       if f in sums else "not listed"} for f in files}
    return info


def frozen_inputs() -> dict:
    from guard import tgr_tracker                                    # the audited Part 10 guard (only its constants)
    sums = {}
    with open(os.path.join(FS_DIR, "SHA256SUMS"), encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) == 2:
                sums[parts[1]] = parts[0]
    recorded = {os.path.relpath(p, PC_DIR): h for p, h in tgr_tracker.FROZEN_SHA256.items()}
    current = {p: sha256_file(os.path.join(PC_DIR, p)) for p in recorded}
    rules = {}
    for d in DOMAINS:
        for fn in sorted(os.listdir(os.path.join(RULES_DIR, d))):
            rel = f"rules/{d}/{fn}"
            h = sha256_file(os.path.join(RULES_DIR, d, fn))
            rules["from_shieldagent/" + rel] = {"sha256": h, "SHA256SUMS": sums.get(rel), "equal": sums.get(rel) == h}
    tt = os.path.join(PC_DIR, "guard", "tgr_tracker.py")
    try:
        rc = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", tt], cwd=PC_DIR, capture_output=True,
                            env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"), timeout=60).returncode
        git_state = {0: "same as git HEAD", 1: "differs from git HEAD"}.get(rc, f"git exit {rc}")
    except Exception as e:  # noqa: BLE001
        git_state = f"git not run: {e}"
    return {"FROZEN_SHA256_in_guard_tgr_tracker_py": recorded, "current_sha256": current,
            "all_equal": all(current[p] == recorded[p] for p in recorded), "rules": rules,
            "rules_all_equal_SHA256SUMS": all(v["equal"] for v in rules.values()),
            "guard_tgr_tracker_py": {"sha256": sha256_file(tt),
                                     "mtime_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(os.path.getmtime(tt))),
                                     "git": git_state}}


# ------------------------------------------------------------------------------------------------ negative controls
def negative_controls(guards: dict, sample: list, k: int = 6) -> dict:
    """Show that the comparison can fail: on k sampled frozen checks with a judge call, change one input and count
    how often the change is caught. (1) history without its last two messages: the prompt must differ from the
    cached one; (2) one judge value flipped: the recomputed record must differ; (3) on blocked checks, one evidence
    text changed: the feedback text must differ."""
    picks = [r for r in sample if r["judge_called_saved"] and r["prompt"]][:k]
    blocked = [r for r in sample if r["judge_called_saved"] and r["blocked"]][:k]
    out = Counter()
    by_src = {}
    for r in picks + blocked:
        by_src.setdefault(r["src"], None)
    for src in by_src:
        eps, _, _ = load_episodes(os.path.join(PC_DIR, src))
        by_src[src] = {(e["task_index"], e["trial"]): e for e in eps}

    def setup(r):
        ep = by_src[r["src"]][(r["task_index"], r["trial"])]
        i = r["attempt_index"]
        a, g = ep["attempts"][i], ep["attempts"][i]["guard"]
        prefix = ep["executed"][:a["executed_prefix_len"]]
        past = [x["guard"]["trace_position"] for x in ep["attempts"][:i] if not x["blocked"]]
        vals = {n: {"value": v["value"], "evidence": v["evidence"]} for n, v in g["judge"].items()}
        return ep["messages"][2 + 2 * i], a["exec_step"], prefix, past, vals, g, guards[r["domain"]][0]

    for r in picks:
        msg, n_exec, prefix, past, vals, g, guard = setup(r)
        if len(prefix) > 4:
            out["history_cut_tried"] += 1
            rec, cl = recheck(guard, prefix[:-2], msg, n_exec, past, vals)
            key = prompt_info(cl[0])["judge_cache_key"] if cl else None
            c = cache_lookup(PARTNER_CACHE, key, cl[0], names_of(guard, rec)) if cl else {"found": False}
            out["history_cut_caught"] += key != r["prompt"]["judge_cache_key"] and not (
                c.get("found") and c["system_equal"] and c["user_equal"])
        n0 = sorted(vals)[0]
        flipped = dict(vals, **{n0: {"value": not vals[n0]["value"] if vals[n0]["value"] is not None else True,
                                     "evidence": vals[n0]["evidence"]}})
        rec, _ = recheck(guard, prefix, msg, n_exec, past, flipped)
        out["value_flip_tried"] += 1
        out["value_flip_caught"] += bool(compare(g, rec, strip_source=False))
    for r in blocked:
        msg, n_exec, prefix, past, vals, g, guard = setup(r)
        aspm = guard.tgr.aspm
        in_rule = sorted((aspm.rules[g["violated_rules"][0]["rule_id"]].atoms - aspm.action_predicates) & set(vals)) \
            if g.get("violated_rules") else []
        if not in_rule:
            continue
        n0 = in_rule[0]
        changed = dict(vals, **{n0: {"value": vals[n0]["value"], "evidence": vals[n0]["evidence"] + " (changed)"}})
        rec, _ = recheck(guard, prefix, msg, n_exec, past, changed)
        out["evidence_change_tried"] += 1
        out["evidence_change_caught"] += rec.get("feedback_text") != g.get("feedback_text")
    return dict(out)


# ------------------------------------------------------------------------------------------------ main + report
def main() -> int:
    t0 = time.time()
    os.makedirs(OUT_DIR, exist_ok=True)
    guards = {d: build_guard(d) for d in DOMAINS}
    binfo = build_info(guards)
    finfo = frozen_inputs()
    binfo["frozen_inputs"] = finfo
    results = {"frozen": {}, "tracker": {}}
    samples = {"frozen": [], "tracker": []}
    alls = {"frozen": [], "tracker": []}
    for kind, runs in (("frozen", FROZEN_RUNS), ("tracker", TRACKER_TAGS)):
        for run in runs:
            for d in DOMAINS:
                rng = random.Random(f"{SEED}:{kind}:{run}:{d}")
                rows, sample, st = run_source(kind, run, d, guards[d][0], rng)
                results[kind][f"{run}/{d}"] = dict(st)
                samples[kind] += sample
                alls[kind] += rows
                print(f"[r3] {kind} {run}/{d}: {dict(st)}", flush=True)
    neg = negative_controls(guards, samples["frozen"])
    binfo["negative_controls"] = neg
    print(f"[r3] negative controls: {neg}", flush=True)
    with open(out_path("ref_guards_build.json"), "w", encoding="utf-8") as f:
        json.dump({**binfo, "results": results, "seconds": round(time.time() - t0, 1)}, f, indent=1, ensure_ascii=False)
    for kind, name in (("frozen", "ref_guards_frozen"), ("tracker", "ref_guards_tracker")):
        with open(out_path(name + ".jsonl"), "w", encoding="utf-8") as f:
            for r in samples[kind]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        with open(out_path(name + "_all.jsonl"), "w", encoding="utf-8") as f:
            for r in alls[kind]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    write_md(binfo, results, samples, finfo)
    tot = {k: Counter() for k in results}
    for k, per in results.items():
        for st in per.values():
            for kk, v in st.items():
                if isinstance(v, int):
                    tot[k][kk] += v
    print(json.dumps({k: dict(v) for k, v in tot.items()}, indent=1), flush=True)
    print(f"[r3] done in {time.time() - t0:.0f}s", flush=True)
    return 0


def _sum(per: dict, key: str) -> int:
    return sum(st.get(key, 0) for st in per.values())


def write_md(binfo, results, samples, finfo) -> None:
    fz, tr = results["frozen"], results["tracker"]
    sf, stt = samples["frozen"], samples["tracker"]
    L = ["# R3 reference: frozen TGR and TGR + tracker guard checks", "",
         f"Date {time.strftime('%Y-%m-%d', time.gmtime())}. Made by `tests/audit_v2_ref_guards.py` (standard library, "
         "network blocked, no LLM call). It uses only the copied runner (`from_shieldagent/runner/`, through "
         "`guard/runner_path.py`) and the frozen rule set. The wrapper (`guard/run_online.py`) and the new eval-v2 "
         "code were not read.", "",
         "Files (same folder): `ref_guards_build.json` (how the runner builds the guard, file hashes, all counts), "
         "`ref_guards_frozen.jsonl` and `ref_guards_tracker.jsonl` (the samples, full detail), "
         "`ref_guards_frozen_all.jsonl` and `ref_guards_tracker_all.jsonl` (every check, short).", "",
         "## 1. How the copied runner builds the TGR guard", ""]
    for s in binfo["how_the_copied_runner_builds_the_tgr_guard"]:
        L.append(f"- {s}")
    L += ["", "| | airline | retail |", "|---|---|---|"]
    da, dr = binfo["domains"]["airline"], binfo["domains"]["retail"]
    for label, key in (("guard class", "guard_class"), ("guard name", "guard_name"), ("rules dir", "rules_dir"),
                       ("rule_set.json sha256", "rule_set_sha256"), ("rules / predicates / background facts", None),
                       ("all weights θ = 1", "all_weights_1"), ("judge prompt hash (manifest)", "manifest_prompt_hash_judge")):
        if key is None:
            L.append(f"| {label} | {da['n_rules']} / {da['n_predicates']} / {da['n_background_facts']} | "
                     f"{dr['n_rules']} / {dr['n_predicates']} / {dr['n_background_facts']} |")
        else:
            L.append(f"| {label} | `{da[key]}` | `{dr[key]}` |")
    L.append(f"| TGRConfig | `{json.dumps(da['config'])}` | same: {da['config'] == dr['config']} |")
    jc = binfo["judge_call"]
    L += ["", f"Judge call: model `{jc['model']}`, effort `{da['config']['judge_effort']}`, max_output_tokens "
          f"{jc['max_output_tokens']}, schema `predicate_values` (sha256 `{jc['judge_schema_sha256'][:16]}…`), template "
          f"`judge.md` (hash16 `{jc['judge_template_hash16 (prompts.hashes)']}`, the manifest says "
          f"`{dr['manifest_prompt_hash_judge']}`). History: `render_history(executed prefix, max_chars=24000)`.",
          f"Decision: ε = {da['config']['epsilon']}, allowed iff P(execute) − P(not) ≥ −ε, exact enumeration up to "
          f"{da['config']['gibbs_threshold']} unknowns; feedback: component C (`method_tgr/feedback.py`).", "",
          "Runner files used, against `from_shieldagent/SHA256SUMS`: "
          f"{dict(Counter(str(v['equals_SHA256SUMS']) for v in binfo['runner_files_sha256'].values()))} "
          "(True = equal; per file in `ref_guards_build.json`).", "",
          "**Prompt hashes** (to compare our `tgr_frozen` guard's prompt for the same history):",
          "- `prompt_sha256` = sha256 of `json.dumps({\"system\": system, \"user\": user}, sort_keys=True)`;",
          "- `judge_cache_key` = the runner's own judge cache key with model gpt-6-luna (the cache file name);",
          "- also `system_sha256`, `user_sha256` (utf-8 text) and the lengths.", "",
          "How a check is redone: `guard.check(state, executed[:executed_prefix_len], messages[2 + 2i], exec_step)`, "
          "with `state.trace` = the saved `trace_position` of every executed attempt before (cap overrides included), "
          "and the judge's LLM call replaced by a function that records the prompt and returns the saved values.", "",
          "## 2. Frozen TGR (partner runs): prompt and decision", "",
          "| run / domain | conv. | checks | judge calls | prompt found in partner cache | cached prompt = rebuilt | "
          "cached answer = saved values | all saved fields = recomputed | history > 24,000 chars |",
          "|---|---|---|---|---|---|---|---|---|"]
    for k, st in fz.items():
        L.append(f"| {k} | {st['episodes']} | {st['checks']:,} | {st['judge_called_saved']:,} | {st.get('cache_found', 0):,} | "
                 f"{st.get('cache_prompt_equal', 0):,} | {st.get('cache_values_equal', 0):,} | {st['fields_equal']:,} | "
                 f"{st.get('truncated_history', 0)} |")
    L.append(f"| **all** | {_sum(fz, 'episodes')} | {_sum(fz, 'checks'):,} | {_sum(fz, 'judge_called_saved'):,} | "
             f"{_sum(fz, 'cache_found'):,} | {_sum(fz, 'cache_prompt_equal'):,} | {_sum(fz, 'cache_values_equal'):,} | "
             f"{_sum(fz, 'fields_equal'):,} | {_sum(fz, 'truncated_history')} |")
    L += ["", f"Other counts (all runs): checks that failed to run again {_sum(fz, 'recheck_errors')}; "
          f"judge called in the record but not rebuilt (or the reverse) "
          f"{_sum(fz, 'judge_called_mismatch')}; past trace length = saved `trace_len_before` "
          f"{_sum(fz, 'past_len_ok'):,} of {_sum(fz, 'checks'):,}; prompt missing from the cache "
          f"{_sum(fz, 'cache_missing')}; cached evidence = saved evidence {_sum(fz, 'cache_evidence_equal'):,}; "
          f"error lines dropped {_sum(fz, 'error_lines_dropped')}, duplicate lines dropped "
          f"{_sum(fz, 'duplicate_lines_dropped')}.", "",
          f"Fields compared: {', '.join('`' + f + '`' for f in FIELDS)}.", "",
          "Negative controls (the comparison can fail): history without its last two messages, prompt no longer "
          f"matches the cache: {binfo['negative_controls'].get('history_cut_caught', 0)} of "
          f"{binfo['negative_controls'].get('history_cut_tried', 0)} caught; one judge value flipped, record differs: "
          f"{binfo['negative_controls'].get('value_flip_caught', 0)} of {binfo['negative_controls'].get('value_flip_tried', 0)}; "
          "one evidence text changed on a blocked check, feedback differs: "
          f"{binfo['negative_controls'].get('evidence_change_caught', 0)} of "
          f"{binfo['negative_controls'].get('evidence_change_tried', 0)}.", "",
          f"**Sample** (`ref_guards_frozen.jsonl`): {len(sf)} checks, fixed seed {SEED}, both domains, 3 runs. By "
          f"category: {dict(Counter(r['category'] for r in sf))}. All fields equal: "
          f"{sum(r['fields_equal'] for r in sf)} of {len(sf)}; cache prompt and answer equal: "
          f"{sum(bool(r['cache'] and r['cache'].get('found') and r['cache']['system_equal'] and r['cache']['user_equal'] and r['cache']['values_equal']) for r in sf)}"
          f" of {sum(bool(r['prompt']) and r['judge_called_saved'] for r in sf)} with a judge call.", "",
          "## 3. TGR + tracker (our p10 runs): decision from the used values and from the judge's values", "",
          "| tag / domain | conv. | checks | judge calls | all saved fields = recomputed (used values) | prompt found in "
          "our cache | cached prompt = rebuilt | cached answer = `tracker.judge_values` | changed a value | block "
          "removed | block added |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, st in tr.items():
        L.append(f"| {k} | {st['episodes']} | {st['checks']:,} | {st['judge_called_saved']:,} | {st['fields_equal']:,} | "
                 f"{st.get('cache_found', 0):,} | {st.get('cache_prompt_equal', 0):,} | {st.get('cache_values_equal', 0):,} | "
                 f"{st.get('checks_with_changed_value', 0)} | {st.get('decision_block_removed', 0)} | "
                 f"{st.get('decision_block_added', 0)} |")
    L.append(f"| **all** | {_sum(tr, 'episodes')} | {_sum(tr, 'checks'):,} | {_sum(tr, 'judge_called_saved'):,} | "
             f"{_sum(tr, 'fields_equal'):,} | {_sum(tr, 'cache_found'):,} | {_sum(tr, 'cache_prompt_equal'):,} | "
             f"{_sum(tr, 'cache_values_equal'):,} | {_sum(tr, 'checks_with_changed_value')} | "
             f"{_sum(tr, 'decision_block_removed')} | {_sum(tr, 'decision_block_added')} |")
    L += ["", f"Other counts: checks that failed to run again {_sum(tr, 'recheck_errors')}; judge skipped "
          f"{_sum(tr, 'judge_skipped')}; judge called in the record but not rebuilt "
          f"(or the reverse) {_sum(tr, 'judge_called_mismatch')}; `source` / `replaced` / `changed` lists "
          f"inconsistent {_sum(tr, 'tracker_lists_inconsistent')}; prompt with the judge's values ≠ prompt with the "
          f"used values {_sum(tr, 'alt_prompt_differs')}; past trace length = saved {_sum(tr, 'past_len_ok'):,} of "
          f"{_sum(tr, 'checks'):,}; prompt missing from the cache {_sum(tr, 'cache_missing')}.", "",
          "For comparison, `output/p10_metrics.md` (sections 3 and 4) gives 6,523 guard checks, 5,774 with a judge call, "
          "258 with a changed value, 68 blocks removed and 9 added.", "",
          f"**Sample** (`ref_guards_tracker.jsonl`): {len(stt)} checks, fixed seed {SEED}. By category: "
          f"{dict(Counter(r['category'] for r in stt))}. All fields equal (used values): "
          f"{sum(r['fields_equal'] for r in stt)} of {len(stt)}. Each line also has the alternative decision "
          "(`alternative_from_judge_values`). The judge's evidence is not saved where the guard used the tracker's "
          "value, so the alternative's feedback text is not exact there (only its decision is).", "",
          "## 4. Frozen inputs", "", "| file | `FROZEN_SHA256` in `guard/tgr_tracker.py` | current sha256 | equal |",
          "|---|---|---|---|"]
    for p, h in finfo["FROZEN_SHA256_in_guard_tgr_tracker_py"].items():
        c = finfo["current_sha256"][p]
        L.append(f"| `{p}` | `{h}` | `{c}` | {c == h} |")
    L += ["", "| file | sha256 | = `from_shieldagent/SHA256SUMS` |", "|---|---|---|"]
    for p, v in finfo["rules"].items():
        L.append(f"| `{p}` | `{v['sha256']}` | {v['equal']} |")
    gt = finfo["guard_tgr_tracker_py"]
    L += ["", f"`guard/tgr_tracker.py`: sha256 `{gt['sha256']}`, modified {gt['mtime_utc']} (before the p10 runs, "
          f"which started 05:26–06:41 UTC), {gt['git']}.", "",
          "## 5. For the auditor", "",
          "- To check `tgr_frozen`: for a line of `ref_guards_frozen.jsonl` (run, domain, task, trial, attempt index), "
          "run our `tgr_frozen` guard's check on the same executed history and pending message with a fake judge that "
          "records the prompt and returns the saved values. Its `prompt_sha256` (or `judge_cache_key`) and its decision "
          "summary (`rebuilt`) must equal the line. `ref_guards_frozen_all.jsonl` has the hashes for every check.",
          "- The prompt in this reference equals the prompt the partner's runs really sent wherever the cache has it "
          "(see section 2); so equality with this reference means equality with frozen TGR.",
          "- `tgr_frozen` should be built as in section 1: `TGRGuard('tgr', <from_shieldagent/rules/<domain>>, "
          "tools_info)` with the defaults (judge effort medium, ε 0.1, actionable feedback, 24,000 history chars), "
          "guard model gpt-6-luna, max_output_tokens 16000, its own judge cache folder.",
          "- For `tgr_tracker`, the same prompt hashes apply (the tracker calls TGR's judge unchanged), and "
          "`ref_guards_tracker*.jsonl` give the used and the alternative decision per check."]
    with open(out_path("ref_guards.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    sys.exit(main())
