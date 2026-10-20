"""Build a TGR rule set (method_tgr.rules.build_rules) for one τ-bench domain with a model profile.

Inputs: the Domain-Basic-filtered policy (output/tgr/policy_input/<env>_wiki.rulebuild.txt, exp_core/policy_filter.py)
and the environment's tool schemas (τ-bench env.tools_info, the agent's own tool interface). Never a gold file.
Output: output/tgr/tgr_rules/<profile>/<env>/<run_id>/
  rule_set.json (what the guard loads), raw.json (the model's outputs), rules.md (readable tables), manifest.json.
Resumable / reproducible: every LLM call is cached (output/tgr/_llmcache), so a re-run replays it.

  python -m exp_core.tgr_build --profile luna-dev --env retail --run-id it1 [--no-a] [--no-b]
Final line: "[tgr-build] <profile>/<env>/<run_id> DONE".
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def env_tools(env: str) -> list:
    from tau_bench.envs import get_env
    with contextlib.redirect_stdout(io.StringIO()):
        e = get_env(env, user_strategy="human", user_model="none", task_split="test", task_index=0)
    return e.tools_info


def rules_md(rs: dict, title: str) -> str:
    out = [f"# {title}", "", f"Flags: {rs['flags']['label']}. Rules: {len(rs['rules'])}. Predicates: {len(rs['predicates'])}.", ""]
    out += ["## Rules", "", "| id | action(s) | logic | description | sentences |", "|---|---|---|---|---|"]
    for r in rs["rules"]:
        out.append(f"| {r['id']} | {', '.join(r['actions'])} | `{r['logic']}` | {r['description']} | {', '.join(r['sentences'])} |")
    out += ["", "## Predicates", "", "| name | description | source |", "|---|---|---|"]
    for n, p in sorted(rs["predicates"].items()):
        out.append(f"| {n} | {p['description']} | {', '.join(p['source'])} |")
    out += ["", "## Background facts for the judge", ""] + [f"- [{b['id']}] {b['text']}" for b in rs.get("background", [])]
    if rs["dispositions"]:
        sent = {s["id"]: s for s in rs["sentences"]}
        out += ["", "## Dispositions (coverage check)", "", "| sentence | section | text | disposition | rules | reason |",
                "|---|---|---|---|---|---|"]
        for d in sorted(rs["dispositions"], key=lambda d: int(d["sentence"][1:]) if d["sentence"][1:].isdigit() else 0):
            s = sent.get(d["sentence"], {})
            out.append(f"| {d['sentence']} | {s.get('heading', '')} | {s.get('text', '?')} | {d['disposition']} | "
                       f"{', '.join(d['rule_ids'])} | {d['reason']} |")
    v = rs["validation"]
    out += ["", "## Validation", "", f"- repair rounds: {len(v['repair_rounds'])}",
            f"- remaining errors: {v['remaining_errors'] or 'none'}",
            f"- invalid rules dropped: {v['invalid_rules_dropped'] or 'none'}",
            f"- exact duplicates dropped: {v['duplicates_dropped'] or 'none'}",
            f"- declared but unused predicates: {v['unused_predicates'] or 'none'}"]
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--env", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--no-a", action="store_true", help="free action predicates (mapped to tools at runtime)")
    ap.add_argument("--no-b", action="store_true", help="general LTLf rules, no dispositions")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--timeout", type=int, default=1800, help="request timeout (s) of the rule-writing calls")
    a = ap.parse_args(argv)
    import repro_runtime.calls  # noqa: F401  (loaded before activate so its seams are re-pointed)
    from exp_core import models
    act = models.activate(a.profile, "rulebuild")
    import policy_pipeline.llm as v1
    v1._client = models.base_client().with_options(timeout=a.timeout)   # one long call; the default 420 s is too short
    from method_tgr.rules import Flags, build_rules
    policy_path = os.path.join(ROOT, "output", "tgr", "policy_input", f"{a.env}_wiki.rulebuild.txt")
    filt = json.load(open(policy_path + ".filter.json"))
    policy = open(policy_path, encoding="utf-8").read()
    tools = env_tools(a.env)
    flags = Flags(a=not a.no_a, b=not a.no_b)
    out = os.path.join(ROOT, "output", "tgr", "tgr_rules", a.profile, a.env, a.run_id)
    os.makedirs(out, exist_ok=True)
    print(f"[tgr-build] {a.profile}/{a.env}/{a.run_id} start: {act['structured_model']}, flags {flags.label}", flush=True)
    t0 = time.time()
    rs = build_rules(policy, tools, flags, effort=a.effort)
    raw = rs.pop("raw")
    json.dump(rs, open(os.path.join(out, "rule_set.json"), "w"), indent=1, ensure_ascii=False)
    json.dump(raw, open(os.path.join(out, "raw.json"), "w"), indent=1, ensure_ascii=False)
    open(os.path.join(out, "rules.md"), "w").write(rules_md(rs, f"TGR rules: {a.env} ({a.profile}, {a.run_id})"))
    sha = lambda s: hashlib.sha256(s.encode()).hexdigest()
    man = {"profile": a.profile, "env": a.env, "run_id": a.run_id, "flags": rs["flags"], "model": act["structured_model"],
           "effort": a.effort, "input": {"policy": [os.path.relpath(policy_path, ROOT), sha(policy)], "filter": filt,
                                         "tools_sha256": sha(json.dumps(tools, sort_keys=True))},
           "prompt_hashes": rs["prompt_hashes"], "usage": rs["usage"], "wall_seconds": round(time.time() - t0, 1),
           "counts": {"sentences": len(rs["sentences"]), "rules": len(rs["rules"]), "predicates": len(rs["predicates"]),
                      "actions_with_rules": len(rs["circuits"]),
                      "dispositions": {k: sum(d["disposition"] == k for d in rs["dispositions"])
                                       for k in ("rule", "exception", "fact", "not_enforceable")},
                      "repair_rounds": len(rs["validation"]["repair_rounds"]),
                      "invalid_dropped": len(rs["validation"]["invalid_rules_dropped"]),
                      "duplicates_dropped": len(rs["validation"]["duplicates_dropped"])},
           "finished": time.strftime("%Y-%m-%dT%H:%M:%S")}
    json.dump(man, open(os.path.join(out, "manifest.json"), "w"), indent=1)
    print(f"[tgr-build] counts {json.dumps(man['counts'])} cost ${rs['usage']['cost_usd']:.4f}", flush=True)
    print(f"[tgr-build] {a.profile}/{a.env}/{a.run_id} DONE: {out}", flush=True)


if __name__ == "__main__":
    main()
