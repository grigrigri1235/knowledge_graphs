"""VERIFY (Alg. 1 l.13): three-valued LTLf over a trajectory prefix (spec "LTLf on an incomplete trajectory").

Prefix semantics (Kleene values True / False / None = unknown):
  NEXT at the last position → unknown; ALWAYS → false if violated so far, else unknown;
  EVENTUALLY → true if satisfied so far, else unknown; UNTIL → true / false once decided, else unknown.
P2-4: a rule whose root operator is temporal is evaluated at position 0 over the prefix; any other rule is
evaluated at the current (last) position.
P2-2: in the MLN a rule counts as violated only if its value is False.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from repro_core import ltlf
from repro_core.ltlf import _and, _not, _or

Trace = List[Dict[str, Optional[bool]]]


def prefix_eval(n, trace: Trace, i: int) -> Optional[bool]:
    op = n[0]
    last = len(trace) - 1
    if op == "atom":
        return trace[i].get(n[1])
    if op == "const":
        return n[1]
    if op == "NOT":
        return _not(prefix_eval(n[1], trace, i))
    if op == "AND":
        return _and(prefix_eval(n[1], trace, i), prefix_eval(n[2], trace, i))
    if op == "OR":
        return _or(prefix_eval(n[1], trace, i), prefix_eval(n[2], trace, i))
    if op == "IMPLIES":
        return _or(_not(prefix_eval(n[1], trace, i)), prefix_eval(n[2], trace, i))
    if op == "NEXT":
        return None if i >= last else prefix_eval(n[1], trace, i + 1)
    if op == "ALWAYS":
        for j in range(i, last + 1):
            if prefix_eval(n[1], trace, j) is False:
                return False
        return None
    if op == "EVENTUALLY":
        for j in range(i, last + 1):
            if prefix_eval(n[1], trace, j) is True:
                return True
        return None
    if op == "UNTIL":
        prefix = True
        for j in range(i, last + 1):
            if _and(prefix, prefix_eval(n[2], trace, j)) is True:
                return True
            prefix = _and(prefix, prefix_eval(n[1], trace, j))
            if prefix is False:
                return False
        return None
    raise ValueError(op)


def rule_value(formula: ltlf.Formula, trace: Trace) -> Optional[bool]:
    """P2-4 evaluation position."""
    if formula.tree[0] in ltlf.TEMPORAL:
        return prefix_eval(formula.tree, trace, 0)
    return prefix_eval(formula.tree, trace, len(trace) - 1)


def violated(value: Optional[bool]) -> bool:
    """P2-2: only a definitely false rule is violated."""
    return value is False
