#!/usr/bin/env python3
"""D9 gold scorer for P6 episodes (SCORING ONLY: gold artefacts never feed the method).

The same evaluation as the Step-2 firing analysis (`scripts/validate_aspm.py --firing`, whose Parser / kleene /
tree_nodes are reused unchanged): for a write-tool call, every Python-evaluable gold rule whose action predicates are
active is evaluated on (call, history before the call); a **violation** is a `block` rule evaluating False
(Kleene: None = not evaluable, not a violation).
Scored per episode:
  - every EXECUTED write call, on the executed history (what actually happened);
  - every guard-BLOCKED (or cap-overridden) write attempt, on the executed history at that moment (block precision proxy).
Reads, respond and think steps have no gold Python rules: blocks on them are "not scorable".
python scripts/reproduction/p6_gold_score.py <tag> [--gold v1|v2]
   v1 (default) → output/repro/p6/<tag>/<env>/<guard>/gold.jsonl      (the scorer used in p6_report.md)
   v2           → .../gold_v2.jsonl: v1 plus the dialogue checks of policies/gold_v2/checks.py, which make AIR-R002 /
                  RET-R005 (explicit confirmation) and AIR-R042 (cancellation eligibility) scorable (README there)
"""
import argparse
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
_spec = importlib.util.spec_from_file_location("validate_aspm", os.path.join(ROOT, "scripts", "validate_aspm.py"))
V = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(V)
_spec2 = importlib.util.spec_from_file_location("gold_v2_checks", os.path.join(ROOT, "policies", "gold_v2", "checks.py"))
GOLD_V2 = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(GOLD_V2)


class GoldScorer:
    def __init__(self, domain, version="v1"):
        self.impl = dict(__import__(f"agent.predicates.{domain}", fromlist=["PREDICATES"]).PREDICATES)
        extra = set()
        if version == "v2":
            self.impl.update(GOLD_V2.PREDICATES)
            extra = set(GOLD_V2.PREDICATES)
        aspm = json.load(open(f"{ROOT}/aspm/{domain}_aspm.json"))
        registry = {p["name"]: p for p in json.load(open(f"{ROOT}/policies/predicates/{domain}_predicates.json"))["predicates"]}
        self.config = json.load(open(f"{ROOT}/policies/curated/{domain}_config.json"))
        self.writes = {t["name"] for t in json.load(open(f"{ROOT}/policies/tau_bench/{domain}_tools.json"))["tools"] if t["writes_db"]}
        self.nodes = {n: parents for n, _, parents in V.tree_nodes(aspm["action_tree"])}
        self.rules = [r for r in aspm["rule_list"] if r["enforcement"] == "block" and
                      all(registry[p[0]]["type"] in V.PY_TYPES or p[0] in extra
                          for p in r["predicates"] if p[3] == "condition")]
        self.parsed = {r["rule_id"]: V.Parser(r["logic"]).parse() for r in self.rules}

    def score_call(self, name, arguments, turn, prefix):
        """List of violated gold block rules (curated ids) for one write call; None if the tool is not a write."""
        if name not in self.writes:
            return None
        call = {"name": name, "arguments": arguments, "turn": turn}
        active = {name, *self.nodes.get(name, [])}
        out = []
        for r in self.rules:
            acts = [p[0] for p in r["predicates"] if p[3] == "action"]
            if not set(acts) <= active:
                continue
            env = {a: True for a in acts}
            for p in r["predicates"]:
                if p[3] == "condition":
                    env[p[0]] = self.impl[p[0]](call, prefix, self.config)
            if V.kleene(self.parsed[r["rule_id"]], env) is False:
                out.append(r["curated_rule_id"])
        return out

    def score_episode(self, ep):
        executed = ep.get("executed") or []
        calls = []
        for i, msg in enumerate(executed):
            if msg.get("role") != "assistant":
                continue
            for tc in (msg.get("tool_calls") or [])[:1]:
                fn = tc.get("function") or {}
                res = next((m for m in executed[i + 1:] if m.get("role") == "tool" and m.get("tool_call_id") == tc.get("id")), None)
                v = self.score_call(fn.get("name"), fn.get("arguments"), msg, executed[:i])
                if v is not None:
                    calls.append({"msg_index": i, "name": fn.get("name"), "violations": v,
                                  "api_rejected": bool(res and str(res.get("content", "")).startswith("Error"))})
        blocks = []
        for a in ep.get("attempts") or []:
            if not (a.get("blocked") or a.get("cap_override")):
                continue
            prefix = executed[:a["executed_prefix_len"]]
            if a["action"] == "respond":
                blocks.append({"exec_step": a["exec_step"], "action": "respond", "scorable": False, "cap_override": a["cap_override"]})
                continue
            turn = {"role": "assistant", "content": a.get("agent_text") or "",
                    "tool_calls": [{"id": "blocked", "type": "function", "function": {"name": a["action"], "arguments": json.dumps(a["kwargs"])}}]}
            v = self.score_call(a["action"], a["kwargs"], turn, prefix)
            blocks.append({"exec_step": a["exec_step"], "action": a["action"], "scorable": v is not None,
                           "gold_violations": v, "cap_override": a["cap_override"]})
        return {"write_calls": calls, "n_violations": sum(len(c["violations"]) for c in calls),
                "n_violating_calls": sum(bool(c["violations"]) for c in calls),
                "n_violating_calls_api_accepted": sum(bool(c["violations"]) and not c["api_rejected"] for c in calls),
                "blocks": blocks}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--gold", choices=("v1", "v2"), default="v1")
    a = ap.parse_args()
    out_name = "gold.jsonl" if a.gold == "v1" else f"gold_{a.gold}.jsonl"
    base = f"{ROOT}/output/repro/p6/{a.tag}"
    for env in ("airline", "retail"):
        if not os.path.isdir(f"{base}/{env}"):
            continue
        scorer = GoldScorer(env, a.gold)
        for guard in sorted(os.listdir(f"{base}/{env}")):
            path = f"{base}/{env}/{guard}/episodes.jsonl"
            if not os.path.exists(path):
                continue
            with open(f"{base}/{env}/{guard}/{out_name}", "w") as f:
                for line in open(path):
                    ep = json.loads(line)
                    g = scorer.score_episode(ep) if ep.get("error") is None else None
                    f.write(json.dumps({"task_index": ep["task_index"], "trial": ep["trial"], "reward": ep["reward"],
                                        "error": ep.get("error"), "gold": g}) + "\n")
            print(f"scored {env}/{guard} ({a.gold})")


if __name__ == "__main__":
    main()
