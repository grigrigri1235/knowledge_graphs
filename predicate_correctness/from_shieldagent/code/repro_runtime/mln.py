"""MLN inference (Eq. 4) and the safety condition (Eq. 5) for one invoked action predicate.

score(µ) = Σ_r θ_r 𝟙[µ ∼ r], with 𝟙 = 0 iff the rule's prefix value is False (P2-2), positions per P2-4.
P(µ_a = v) = Σ_{µ: µ_a = v} e^{score(µ)} / Σ_µ e^{score(µ)}.
P2-1: worlds vary the invoked action predicate a and the UNKNOWN condition predicates of the connected group of
rules that touch a through shared unknown predicates; other invoked action predicates are observed true, non-invoked
ones observed false. Rules outside the group cancel in Eq. 4 (exact; tests/repro/test_mln_decomposition.py).
Exact enumeration up to `gibbs_threshold` unknowns, Gibbs sampling above (fixed seed).
Eq. 5 (decided sign convention, spec "ε sign"): allowed iff P(µ_a=1) − P(µ_a=0) ≥ −ε.
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Sequence, Set

from repro_runtime.aspm import ASPM
from repro_runtime.verify import Trace, rule_value


def connected_group(aspm: ASPM, rule_ids: Sequence[str], action: str, unknown: Set[str]):
    keep, frontier = [], {action}
    changed = True
    while changed:
        changed = False
        for rid in rule_ids:
            if rid in keep:
                continue
            atoms = aspm.rules[rid].atoms
            if atoms & frontier:
                keep.append(rid)
                frontier |= atoms & unknown
                changed = True
    return sorted(keep, key=int), sorted(frontier & unknown)


def _values(aspm, rids, past, current):
    trace = list(past) + [current]
    return {rid: rule_value(aspm.rules[rid].formula, trace) for rid in rids}


def _score(aspm, action, rids, vals):
    return sum(aspm.weight(action, rid) for rid in rids if vals[rid] is not False)


def decide(aspm: ASPM, rule_ids: Sequence[str], action: str, current: Dict[str, Optional[bool]], past: Trace,
           epsilon: float = 0.1, gibbs_threshold: int = 16, gibbs_samples: int = 10000, gibbs_burn: int = 1000,
           seed: int = 0) -> dict:
    """current: observed values at the decision step (conditions True/False/None, action predicates set);
    the entry for `action` is ignored (it is enumerated)."""
    atoms = set().union(*(aspm.rules[r].atoms for r in rule_ids)) if rule_ids else set()
    unknown = {n for n in atoms if n != action and current.get(n) is None and n not in aspm.action_predicates}
    group, unk = connected_group(aspm, list(rule_ids), action, unknown)
    base = dict(current)
    worlds = []                                   # (a, assignment, score, values)
    if len(unk) <= gibbs_threshold:
        method = "exact"
        mass = {0: 0.0, 1: 0.0}
        for va in (0, 1):
            for k in range(2 ** len(unk)):
                bits = [bool(k >> j & 1) for j in range(len(unk))]
                cur = dict(base, **dict(zip(unk, bits)), **{action: bool(va)})
                vals = _values(aspm, group, past, cur)
                s = _score(aspm, action, group, vals)
                mass[va] += math.exp(s)
                worlds.append((va, dict(zip(unk, bits)), s, vals))
        z = mass[0] + mass[1]
        p1, p0 = mass[1] / z, mass[0] / z
    else:
        method = "gibbs"
        rnd = random.Random(seed)
        names = unk + [action]
        state = {n: rnd.random() < 0.5 for n in names}

        def score_of(st):
            vals = _values(aspm, group, past, dict(base, **st))
            return _score(aspm, action, group, vals), vals

        acc, n_acc = 0.0, 0
        for sweep in range(gibbs_burn + gibbs_samples):
            for n in names:
                s1, v1 = score_of(dict(state, **{n: True}))
                s0, v0 = score_of(dict(state, **{n: False}))
                p = 1.0 / (1.0 + math.exp(s0 - s1))
                if n == action and sweep >= gibbs_burn:          # Rao-Blackwellised estimate of P(µ_a = 1)
                    acc += p
                    n_acc += 1
                    worlds.append((1, {k: state[k] for k in unk}, s1, v1))
                    worlds.append((0, {k: state[k] for k in unk}, s0, v0))
                state[n] = rnd.random() < p
        p1 = acc / max(n_acc, 1)
        p0 = 1.0 - p1
    margin = p1 - p0
    best1 = max((w for w in worlds if w[0] == 1), key=lambda w: w[2])
    best0 = next((w for w in worlds if w[0] == 0 and w[1] == best1[1]), None)
    by_action = [rid for rid in group if best1[3][rid] is False and (best0 is None or best0[3][rid] is not False)]
    # P(r is violated by the action | µ_a = 1): over paired worlds (1, u) / (0, u), weighted by P(u | µ_a = 1)
    pairs = [(worlds[i], worlds[i + 1]) for i in range(0, len(worlds), 2)] if method == "gibbs" else \
        list(zip(worlds[len(worlds) // 2:], worlds[:len(worlds) // 2]))
    wsum, risk = 0.0, {rid: 0.0 for rid in group}
    for w1, w0 in pairs:
        wt = 1.0 / (1.0 + math.exp(w0[2] - w1[2])) if method == "gibbs" else math.exp(w1[2])
        wsum += wt
        for rid in group:
            if w1[3][rid] is False and w0[3][rid] is not False:
                risk[rid] += wt
    at_risk = {rid: round(v / wsum, 4) for rid, v in sorted(risk.items(), key=lambda kv: -kv[1]) if v > 0} if wsum else {}
    false_in_best = [rid for rid in group if best1[3][rid] is False]
    return {"action": action, "group_rules": group, "group_unknowns": unk, "method": method,
            "p_execute": p1, "p_non_execute": p0, "margin": margin, "epsilon": epsilon,
            "allowed": margin >= -epsilon, "allowed_eps0": margin >= 0.0,
            "violated_by_action": by_action, "false_in_best_world": false_in_best, "at_risk": at_risk,
            "best_world_unknowns": best1[1], "rule_values_execute": best1[3],
            "rule_values_non_execute": best0[3] if best0 else None}
