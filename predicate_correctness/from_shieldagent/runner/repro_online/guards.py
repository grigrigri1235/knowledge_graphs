"""Guards for the online loop: none, Direct baseline, ShieldAgent (config A), TGR (method_tgr; post-reproduction)."""
from __future__ import annotations

import json
import os
from typing import Optional

from repro_core.taubench_steps import RESPOND, Step, _args

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make_step(executed: list, msg: dict, index: int) -> Step:
    """The agent turn `msg` as a shield step; history = executed messages only (P2-6)."""
    calls = msg.get("tool_calls") or []
    text = msg.get("content") or ""
    if calls and calls[0].get("function") is not None:
        tc = calls[0]
        return Step(index, len(executed), "tool_call", tc["function"]["name"], _args(tc["function"].get("arguments")), text,
                    None, False, tc.get("id"), list(executed))
    return Step(index, len(executed), "respond", RESPOND, {"content": text}, text, None, False, None, list(executed))


class NoGuard:
    name = "none"

    def new_episode(self):
        return None

    def check(self, state, executed, msg, index):
        return None

    def commit(self, state, rec):
        pass


class DirectGuard:
    name = "direct"

    def __init__(self, domain: str, effort: str = "medium"):
        self.policy = open(os.path.join(ROOT, "policy_docs", f"{domain}_wiki.txt"), encoding="utf-8").read()
        self.effort = effort

    def new_episode(self):
        return None

    def check(self, state, executed, msg, index):
        from repro_runtime.direct import direct
        return direct(self.policy, make_step(executed, msg, index), self.effort)

    def commit(self, state, rec):
        pass


class ShieldGuard:
    name = "shield"

    def __init__(self, domain: str, tools_info: list, aux_effort: str = "low", planner_effort: str = "medium",
                 epsilon: float = 0.1):
        from repro_runtime import aspm as A
        from repro_runtime.shield import Shield, ShieldConfig
        man = json.load(open(os.path.join(ROOT, "aspm_repro", domain, "manifest.json")))
        a2 = json.load(open(os.path.join(ROOT, "output", "repro", "aspm_runs", domain, man["run_id"], "alg2.json")))
        aspm = A.load(os.path.join(ROOT, "aspm_repro", domain), type_conflicts=sorted({c["name"] for c in a2["type_conflicts"]}))
        self.config = ShieldConfig(aux_effort=aux_effort, planner_effort=planner_effort, epsilon=epsilon)
        self.shield = Shield(aspm, tools_info, self.config)

    def new_episode(self):
        from repro_runtime.shield import Conversation
        return Conversation()

    def check(self, state, executed, msg, index):
        n = len(state.trace)                      # audit of P2-6: must equal the number of executed steps
        rec = self.shield.step(state, make_step(executed, msg, index))
        rec["trace_len_before"] = n
        return rec

    def commit(self, state, rec):
        self.shield.commit(state, rec)


class TGRGuard:
    """method_tgr runtime. Variants: tgr (A+B+C), tgr_nob (rules built without B), tgr_noc (ShieldAgent's explanation
    feedback instead of C), tgr_noa (rules built without A). The rule set is the build's rule_set.json."""
    VARIANTS = ("tgr", "tgr_nob", "tgr_noc", "tgr_noa")

    def __init__(self, name: str, rules_dir: str, tools_info: list, judge_effort: str = "medium", epsilon: float = 0.1):
        from method_tgr.runtime import TGR, TGRConfig, load_rule_set
        self.name = name
        rs = load_rule_set(os.path.join(rules_dir, "rule_set.json"))
        expect_b, expect_a = name != "tgr_nob", name != "tgr_noa"
        if rs["flags"]["b"] != expect_b or rs["flags"]["a"] != expect_a:
            raise ValueError(f"guard {name} needs a rule set built with A={expect_a}, B={expect_b}; {rules_dir} has {rs['flags']}")
        self.config = TGRConfig(actionable_feedback=name != "tgr_noc", judge_effort=judge_effort, epsilon=epsilon)
        self.tgr = TGR(rs, tools_info, self.config)

    def new_episode(self):
        from method_tgr.runtime import Conversation
        return Conversation()

    def check(self, state, executed, msg, index):
        n = len(state.trace)
        rec = self.tgr.step(state, make_step(executed, msg, index))
        rec["trace_len_before"] = n
        return rec

    def commit(self, state, rec):
        self.tgr.commit(state, rec)


def build(name: str, domain: str, tools_info: list, rules_dir: Optional[str] = None):
    if name == "none":
        return NoGuard()
    if name == "direct":
        return DirectGuard(domain)
    if name == "shield":
        return ShieldGuard(domain, tools_info)
    if name in TGRGuard.VARIANTS:
        variant = "nob" if name == "tgr_nob" else ("noa" if name == "tgr_noa" else "full")
        return TGRGuard(name, rules_dir or os.path.join(ROOT, "tgr_rules", domain, variant), tools_info)
    raise ValueError(name)
