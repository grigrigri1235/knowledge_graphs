#!/usr/bin/env python3
"""Validate aspm/{domain}_aspm.json against the runtime code (agent/tools/aspm_tool.py, certification.py),
the curated rules, the predicate registry and the predicate implementations.

Structural checks (FAIL on violation):
  - loads through the REAL agent.tools.aspm_tool.load_aspm_json (imported, not replicated)
  - every rule passes the REAL aspm_tool.validate_rule_consistency
  - every tree node has a truthy entry in `actions`; every soft_rule_id exists; the REAL get_action_circuit
    succeeds for every tool together with its upstream nodes (as agent.py calls it)
  - rule ids are int-castable and unique (formulate_solution_space sorts with int(rule_id))
  - every curated rule is covered by >= 1 ASPM rule
  - grammar: exactly one IMPLIES at parenthesis depth 0, no temporal operators, left side = the attach node's
    action predicate or a conjunction containing it; snake_case predicate names; logic/predicate-list name consistency
  - action predicates are τ-bench tools, respond_to_user or group nodes; every rule's action predicate is its attach node
  - every condition predicate is in the registry; every Python-typed predicate has an implementation
Logic check: for every rule and every truth assignment, certification.logic_to_python + eval must equal an
  independent recursive-descent evaluator and sympy. Includes a self-test that the checker catches the known
  nested-IMPLIES bug.
Offline firing analysis (--firing): evaluates every Python-evaluable rule on every write-tool call of the recorded
  τ-bench trajectories (no LLM calls) and reports firing rates by reward.

Usage: python scripts/validate_aspm.py [--firing] [--tau-bench-dir ~/refs/tau-bench]
"""
import argparse
import asyncio
import contextlib
import io
import itertools
import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TEMPORAL = {"ALWAYS", "EVENTUALLY", "UNTIL"}
OPERATORS = {"AND", "OR", "NOT", "IMPLIES"}
PY_TYPES = {"state", "tool_log", "structural"}


def _quiet_import(name):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return __import__(name, fromlist=["*"])


# ------------------------------------------------------------------------------------------------ evaluator
class Parser:
    """Independent evaluator. Grammar (lowest to highest precedence):
    expr := impl ; impl := or ('IMPLIES' impl)? ; or := and ('OR' and)* ; and := not ('AND' not)* ;
    not := 'NOT' not | atom ; atom := NAME | '(' expr ')'.  Values are True/False/None (Kleene logic)."""

    def __init__(self, text):
        self.toks = re.findall(r"\(|\)|[A-Za-z_][A-Za-z0-9_]*", text)
        self.i = 0

    def parse(self):
        node = self.impl()
        if self.i != len(self.toks):
            raise ValueError(f"trailing tokens: {self.toks[self.i:]}")
        return node

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else None

    def eat(self, t=None):
        tok = self.peek()
        if t is not None and tok != t:
            raise ValueError(f"expected {t}, got {tok}")
        self.i += 1
        return tok

    def impl(self):
        left = self.or_()
        if self.peek() == "IMPLIES":
            self.eat()
            return ("IMPLIES", left, self.impl())
        return left

    def or_(self):
        node = self.and_()
        while self.peek() == "OR":
            self.eat()
            node = ("OR", node, self.and_())
        return node

    def and_(self):
        node = self.not_()
        while self.peek() == "AND":
            self.eat()
            node = ("AND", node, self.not_())
        return node

    def not_(self):
        if self.peek() == "NOT":
            self.eat()
            return ("NOT", self.not_())
        return self.atom()

    def atom(self):
        tok = self.eat()
        if tok == "(":
            node = self.impl()
            self.eat(")")
            return node
        if tok in OPERATORS or tok in TEMPORAL or tok is None or tok == ")":
            raise ValueError(f"unexpected token {tok}")
        return ("VAR", tok)


def kleene(node, env):
    op = node[0]
    if op == "VAR":
        return env[node[1]]
    if op == "NOT":
        v = kleene(node[1], env)
        return None if v is None else (not v)
    a, b = kleene(node[1], env), kleene(node[2], env)
    if op == "AND":
        if a is False or b is False:
            return False
        return None if (a is None or b is None) else True
    if op == "OR":
        if a is True or b is True:
            return True
        return None if (a is None or b is None) else False
    if op == "IMPLIES":
        return kleene(("OR", ("NOT", node[1]), node[2]), env)
    raise ValueError(op)


def sympy_eval(logic, env):
    import sympy
    from sympy.logic.boolalg import Implies, And, Or, Not

    def conv(n):
        if n[0] == "VAR":
            return sympy.Symbol(n[1])
        if n[0] == "NOT":
            return Not(conv(n[1]))
        f = {"AND": And, "OR": Or, "IMPLIES": Implies}[n[0]]
        return f(conv(n[1]), conv(n[2]))
    expr = conv(Parser(logic).parse())
    return bool(expr.subs({sympy.Symbol(k): v for k, v in env.items()}))


def runtime_eval(cert, logic, env):
    """Exactly what certification.verify_fol_rules does."""
    scope = dict(env)
    return bool(eval(cert.logic_to_python(logic), {"__builtins__": {"True": True, "False": False}}, scope))


# ------------------------------------------------------------------------------------------------ structure
def tree_nodes(tree):
    out = []

    def walk(node, level, parents):
        name = node["name"] if isinstance(node, dict) else node
        out.append((name, level, parents))
        if isinstance(node, dict):
            for key in ("L2_children", "L3_children"):
                for child in node.get(key, []):
                    walk(child, level + 1, parents + [name])
    for l1 in tree["L1_actions"]:
        walk(l1, 1, [])
    return out


def check_domain(domain, aspm_tool, cert, report):
    """Gold (hand-written) ASPM of a domain."""
    return check_aspm(
        f"{ROOT}/aspm/{domain}_aspm.json", f"{ROOT}/policies/predicates/{domain}_predicates.json",
        {t["name"] for t in json.load(open(f"{ROOT}/policies/tau_bench/{domain}_tools.json"))["tools"]},
        aspm_tool, cert, report,
        curated=[r["rule_id"] for r in json.load(open(f"{ROOT}/policies/curated/{domain}_curated_rules.json"))["rules"]],
        impl=__import__(f"agent.predicates.{domain}", fromlist=["PREDICATES"]).PREDICATES)


def check_auto(run_dir, tools_raw, aspm_tool, cert, report):
    """Automatic ASPM (policy_pipeline output): every predicate has type 'judge'; no curated coverage or Python checks."""
    tools = {(t.get("function", t))["name"] for t in json.load(open(tools_raw))}
    return check_aspm(os.path.join(run_dir, "aspm.json"), os.path.join(run_dir, "predicates.json"), tools,
                      aspm_tool, cert, report, curated=None, impl=None)


def check_aspm(path, registry_path, tools, aspm_tool, cert, report, curated=None, impl=None):
    fails, notes = [], []
    with contextlib.redirect_stdout(io.StringIO()):
        res = aspm_tool.load_aspm_json(path)
    if res.get("status") != "success":
        fails.append(f"load_aspm_json: {res}")
    aspm = json.load(open(path))
    rules = aspm["rule_list"]
    registry = {p["name"]: p for p in json.load(open(registry_path))["predicates"]}
    nodes = tree_nodes(aspm["action_tree"])
    node_names = {n for n, _, _ in nodes}
    groups = {n for n, lvl, _ in nodes if n not in tools and n != "respond_to_user"}

    # loader-level facts
    if len(aspm_tool.aspm_rules) != len(rules):
        fails.append("loader rule count differs (duplicate rule ids?)")
    if set(aspm_tool.aspm_tree.nodes) != node_names:
        fails.append("loader tree nodes differ from the JSON tree")

    # ids
    ids = [r["rule_id"] for r in rules]
    try:
        [int(i) for i in ids]
    except ValueError:
        fails.append("non-integer rule id")
    if len(set(ids)) != len(ids):
        fails.append("duplicate rule ids")
    by_id = {r["rule_id"]: r for r in rules}

    # actions / circuits
    for n in node_names:
        entry = aspm["actions"].get(n)
        if not entry:
            fails.append(f"tree node {n} missing or falsy in actions")
            continue
        for sid in entry.get("soft_rule_ids", []):
            if sid not in by_id:
                fails.append(f"{n}: soft_rule_id {sid} does not exist")
    for n, lvl, parents in nodes:
        if n in groups:
            continue
        with contextlib.redirect_stdout(io.StringIO()):
            up = aspm_tool.aspm_tree.get_upstream_actions(n)
        grounded = sorted({n, *[p for lst in up.values() for p in lst]})
        out = asyncio.run(aspm_tool.get_action_circuit(grounded))
        if out.get("status") != "success":
            fails.append(f"get_action_circuit({grounded}) failed: {out.get('message')}")
        else:
            report.setdefault("circuits", {})[n] = sorted({rid for c in out["action_circuits"].values() for rid in c["rule_ids"]}, key=int)

    # per rule
    covered = set()
    name_re = re.compile(r"^[a-z][a-z0-9_]*$")
    for r in rules:
        rid, logic = r["rule_id"], r["logic"]
        if curated is not None:
            covered.add(r.get("curated_rule_id"))
        ok, msg = aspm_tool.validate_rule_consistency({"grounded_predicates": r["predicates"], "rule_logic": logic})
        if not ok:
            fails.append(f"rule {rid}: validate_rule_consistency: {msg}")
        if any(len(p) != 4 or p[2] != "" or p[3] not in ("action", "condition") for p in r["predicates"]):
            fails.append(f"rule {rid}: predicate entries must be [name, description, '', action|condition]")
        toks = re.findall(r"\(|\)|[A-Za-z_][A-Za-z0-9_]*", logic)
        if set(toks) & TEMPORAL:
            fails.append(f"rule {rid}: temporal operator")
        depth, top = 0, []
        for k, t in enumerate(toks):
            depth += (t == "(") - (t == ")")
            if t == "IMPLIES":
                top.append((k, depth))
        if len(top) != 1 or top[0][1] != 0:
            fails.append(f"rule {rid}: needs exactly one top-level IMPLIES (found {top})")
            continue
        left = toks[:top[0][0]]
        names = [t for t in toks if t not in OPERATORS and t not in "()"]
        for nm in set(names):
            if not name_re.match(nm):
                fails.append(f"rule {rid}: predicate name {nm!r} is not lower snake_case")
        actions = [p[0] for p in r["predicates"] if p[3] == "action"]
        conds = [p[0] for p in r["predicates"] if p[3] == "condition"]
        for a in actions:
            if a not in tools and a != "respond_to_user" and a not in groups:
                fails.append(f"rule {rid}: unknown action predicate {a}")
            if a not in left or "OR" in left or "NOT" in left:
                fails.append(f"rule {rid}: action predicate {a} must be on the left of IMPLIES, in a conjunction")
        node = r.get("attached_to")
        if actions != [node] or rid not in (aspm["actions"].get(node) or {}).get("soft_rule_ids", []):
            fails.append(f"rule {rid}: action predicate {actions} is not its attach node {node!r}, or the node does not list the rule")
        for c in conds:
            if c not in registry:
                fails.append(f"rule {rid}: condition {c} not in registry")
            elif impl is not None and registry[c]["type"] in PY_TYPES and c not in impl:
                fails.append(f"rule {rid}: Python predicate {c} has no implementation")
            elif registry[c]["type"] not in PY_TYPES | {"dialogue", "judge"}:
                fails.append(f"rule {rid}: predicate {c} has invalid type {registry[c]['type']}")
        # logic check
        tree = Parser(logic).parse()
        disagreements = 0
        for vals in itertools.product([False, True], repeat=len(set(names))):
            env = dict(zip(sorted(set(names)), vals))
            ref, rt, sy = kleene(tree, env), runtime_eval(cert, logic, env), sympy_eval(logic, env)
            if not (ref == rt == sy):
                disagreements += 1
        report.setdefault("logic_assignments", 0)
        report["logic_assignments"] += 2 ** len(set(names))
        if disagreements:
            fails.append(f"rule {rid}: logic_to_python disagrees with the reference on {disagreements} assignments")
    if curated is not None:
        missing = [c for c in curated if c not in covered]
        if missing:
            fails.append(f"curated rules not covered: {missing}")
    for name, p in registry.items():
        if impl is not None and p["type"] in PY_TYPES and name not in impl:
            fails.append(f"registry predicate {name} has no implementation")
        if p["type"] == "judge" and not (p.get("judge", {}).get("question") and p.get("value_source")):
            fails.append(f"judge predicate {name} lacks judge.question or value_source")
    report.update(rules=len(rules), nodes=len(node_names), curated=len(curated or []), covered=len(set(curated or []) & covered),
                  predicates=Counter(p["type"] for p in registry.values()),
                  enforcement=Counter(r.get("enforcement") for r in rules), api=Counter(str(r.get("api_enforced")) for r in rules))
    return fails


def logic_self_test(cert):
    """The checker must detect the known runtime bug (nested IMPLIES)."""
    bad = "(a IMPLIES b) AND c"
    env = {"a": False, "b": False, "c": False}
    return runtime_eval(cert, bad, env) != kleene(Parser(bad).parse(), env)


# ------------------------------------------------------------------------------------------------ firing analysis
def firing_analysis(domain, tau_dir, out_md, out_json):
    from agent.predicates.context import tool_events  # noqa: F401  (import check)
    impl = __import__(f"agent.predicates.{domain}", fromlist=["PREDICATES"]).PREDICATES
    aspm = json.load(open(f"{ROOT}/aspm/{domain}_aspm.json"))
    registry = {p["name"]: p for p in json.load(open(f"{ROOT}/policies/predicates/{domain}_predicates.json"))["predicates"]}
    config = json.load(open(f"{ROOT}/policies/curated/{domain}_config.json"))
    writes = {t["name"] for t in json.load(open(f"{ROOT}/policies/tau_bench/{domain}_tools.json"))["tools"] if t["writes_db"]}
    nodes = {n: parents for n, _, parents in tree_nodes(aspm["action_tree"])}
    python_rules = [r for r in aspm["rule_list"]
                    if all(registry[p[0]]["type"] in PY_TYPES for p in r["predicates"] if p[3] == "condition")]
    parsed = {r["rule_id"]: Parser(r["logic"]).parse() for r in python_rules}
    stats = defaultdict(lambda: Counter())
    examples = defaultdict(list)
    calls = Counter()
    for fname in sorted(os.listdir(f"{tau_dir}/historical_trajectories")):
        if domain not in fname:
            continue
        model = fname.replace(f"-{domain}.json", "")
        for run in json.load(open(f"{tau_dir}/historical_trajectories/{fname}")):
            reward = "r1" if run["reward"] == 1 else "r0"
            traj = run["traj"]
            for i, msg in enumerate(traj):
                if msg.get("role") != "assistant":
                    continue
                for tc in msg.get("tool_calls") or []:
                    name = tc["function"]["name"]
                    if name not in writes:
                        continue
                    calls[reward] += 1
                    # did the API accept it?
                    result = next((m for m in traj[i + 1:] if m.get("role") == "tool" and m.get("tool_call_id") == tc.get("id")), None)
                    api_error = bool(result and str(result.get("content", "")).startswith("Error"))
                    call = {"name": name, "arguments": tc["function"]["arguments"], "turn": msg}
                    active = {name, *nodes.get(name, [])}
                    prefix = traj[:i]
                    blocked = False
                    for r in python_rules:
                        acts = [p[0] for p in r["predicates"] if p[3] == "action"]
                        if not set(acts) <= active:
                            continue
                        env = {a: True for a in acts}
                        for p in r["predicates"]:
                            if p[3] == "condition":
                                env[p[0]] = impl[p[0]](call, prefix, config)
                        v = kleene(parsed[r["rule_id"]], env)
                        key = r["rule_id"]
                        stats[key][f"{reward}_evaluated"] += 1
                        if v is None:
                            stats[key][f"{reward}_not_evaluable"] += 1
                        elif v is False:
                            stats[key][f"{reward}_fired"] += 1
                            blocked |= r["enforcement"] == "block"
                            if api_error:
                                stats[key][f"{reward}_fired_api_rejected"] += 1
                            if len(examples[key]) < 12:
                                examples[key].append({"model": model, "task_id": run["task_id"], "trial": run.get("trial"), "reward": run["reward"],
                                                      "tool": name, "args": json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"],
                                                      "api_error": api_error, "predicates": {k: v2 for k, v2 in env.items()}})
                    calls[f"{reward}_{'rejected' if api_error else 'accepted'}"] += 1
                    if blocked:
                        calls[f"{reward}_{'rejected' if api_error else 'accepted'}_blocked"] += 1
    rules_by_id = {r["rule_id"]: r for r in python_rules}
    lines = [f"### {domain}", "",
             f"Write-tool calls analysed: {calls['r1']} in reward-1 runs, {calls['r0']} in reward-0 runs. "
             f"Python-evaluable rules: {len(python_rules)} of {len(aspm['rule_list'])}. Kleene logic: a rule is 'not evaluable' (n/e) only if "
             f"a None predicate leaves its value undetermined.", "",
             f"Calls a `block` rule would stop: reward-1 runs: {calls['r1_accepted_blocked']} of {calls['r1_accepted']} API-accepted "
             f"(+{calls['r1_rejected_blocked']} of {calls['r1_rejected']} API-rejected); reward-0 runs: {calls['r0_accepted_blocked']} of "
             f"{calls['r0_accepted']} API-accepted (+{calls['r0_rejected_blocked']} of {calls['r0_rejected']} API-rejected).", "",
             "| Rule | Curated | Enf. | API | Logic | r1 eval | r1 fired | r1 n/e | r0 eval | r0 fired | r0 n/e | fired & API-rejected (r1/r0) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for rid in sorted(stats, key=int):
        s, r = stats[rid], rules_by_id[rid]
        lines.append(f"| {rid} | {r['curated_rule_id']} | {r['enforcement']} | {'yes' if r['api_enforced'] else 'no'} | `{r['logic']}` | "
                     f"{s['r1_evaluated']} | {s['r1_fired']} | {s['r1_not_evaluable']} | {s['r0_evaluated']} | {s['r0_fired']} | {s['r0_not_evaluable']} | "
                     f"{s['r1_fired_api_rejected']}/{s['r0_fired_api_rejected']} |")
    open(out_md, "a").write("\n".join(lines) + "\n\n")
    json.dump({"domain": domain, "calls": calls, "stats": {k: dict(v) for k, v in stats.items()}, "examples": examples},
              open(out_json, "w"), indent=1, default=str)
    return stats, calls


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--domains", nargs="+", default=["airline", "retail"])
    ap.add_argument("--firing", action="store_true", help="run the offline firing analysis on recorded τ-bench trajectories")
    ap.add_argument("--tau-bench-dir", default=os.path.expanduser("~/refs/tau-bench"))
    ap.add_argument("--firing-out", default=f"{ROOT}/output/step2_firing")
    ap.add_argument("--auto", nargs=2, action="append", metavar=("RUN_DIR", "TOOLS_RAW_JSON"),
                    help="validate an automatic ASPM (policy_pipeline output: aspm.json + predicates.json in RUN_DIR) instead of the gold ones")
    args = ap.parse_args()
    if args.auto:
        aspm_tool = _quiet_import("agent.tools.aspm_tool")
        cert = _quiet_import("agent.tools.certification")
        ok = logic_self_test(cert)
        for run_dir, tools_raw in args.auto:
            report = {}
            fails = check_auto(run_dir, tools_raw, aspm_tool, cert, report)
            print(f"[auto {run_dir}] tree_nodes={report['nodes']} aspm_rules={report['rules']} logic_assignments_checked={report.get('logic_assignments', 0)}")
            print(f"  predicates by type: {dict(report['predicates'])}; rules by enforcement: {dict(report['enforcement'])}")
            for f in fails:
                print(f"  FAIL {f}")
            print(f"  => {'PASS' if not fails else 'FAIL'} ({len(fails)} failures)")
            ok &= not fails
        print("OVERALL:", "PASS" if ok else "FAIL")
        sys.exit(0 if ok else 1)
    aspm_tool = _quiet_import("agent.tools.aspm_tool")
    cert = _quiet_import("agent.tools.certification")
    print("aspm_tool / certification: imported from agent/tools (real runtime code, not replicated)")
    self_ok = logic_self_test(cert)
    print(f"logic self-test (checker detects the nested-IMPLIES bug in logic_to_python): {'PASS' if self_ok else 'FAIL'}")
    ok = self_ok
    for d in args.domains:
        report = {}
        fails = check_domain(d, aspm_tool, cert, report)
        print(f"[{d}] tree_nodes={report['nodes']} aspm_rules={report['rules']} curated_covered={report['covered']}/{report['curated']} "
              f"logic_assignments_checked={report['logic_assignments']}")
        print(f"  predicates by type: {dict(report['predicates'])}")
        print(f"  rules by enforcement: {dict(report['enforcement'])}; api_enforced: {dict(report['api'])}")
        for f in fails:
            print(f"  FAIL {f}")
        print(f"  => {'PASS' if not fails else 'FAIL'} ({len(fails)} failures)")
        ok &= not fails
    if args.firing:
        os.makedirs(args.firing_out, exist_ok=True)
        md = os.path.join(args.firing_out, "firing_tables.md")
        open(md, "w").write("")
        for d in args.domains:
            stats, calls = firing_analysis(d, args.tau_bench_dir, md, os.path.join(args.firing_out, f"{d}_firing.json"))
            fired1 = sum(s["r1_fired"] for s in stats.values())
            print(f"[{d}] firing analysis: {calls['r1']} write calls in reward-1 runs, {calls['r0']} in reward-0 runs; "
                  f"rule firings r1={fired1} r0={sum(s['r0_fired'] for s in stats.values())} -> {md}")
    print("OVERALL:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
