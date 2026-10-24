"""Tests for state_tracker/v3/facts_format_v3.py (tracker v3, part 5): the v3 fact validator and the one evaluator.

  - the combine parser (AND / OR / NOT / parentheses) and its value, also with parts not known yet;
  - the validator on a good file and on one bad entry per problem type; the real rule set and rule table;
  - the extension registry: a registered helper is accepted, an unregistered name is rejected, the frozen lookup
    format itself is not changed;
  - the evaluator: two values only; a missing argument takes the blocking value and is counted; a missing field of an
    existing object is counted; a nonexistent id takes the part's if_nonexistent value; NotDefinedYet on a null expr
    or a name not registered yet; reads are recorded; question parts run only when combine needs them.
States are built from tiny hand-made conversations (each tool output made by τ-bench's tool code on a separate copy
of the data, as tests/test_lookup_format.py does), never from saved data. No LLM call, no network.

Run from predicate_correctness/:  python3 -B -m unittest tests.test_v3_facts_format -v
"""
from __future__ import annotations

import contextlib
import copy
import io
import itertools
import json
import os
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
PC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PC_DIR not in sys.path:
    sys.path.insert(0, PC_DIR)

from state_tracker import lookup_format as L            # noqa: E402
from state_tracker import paths                          # noqa: E402
from state_tracker import state as S                    # noqa: E402
from state_tracker import tau_copy                       # noqa: E402
from state_tracker.v3 import facts_format_v3 as F       # noqa: E402

KINDS = ["order", "payment_method", "product", "product_type", "user", "variant"]


# ----------------------------------------------------------------------------------------------- builders

def _conv(domain, calls):
    """System, user, then per call an assistant tool call and its output (τ-bench's code on a separate copy)."""
    db = S.load_db(domain)
    msgs = [{"role": "system", "content": tau_copy.policy_text(domain)}, {"role": "user", "content": "hi"}]
    for i, (name, args) in enumerate(calls):
        out = S.run_tool(domain, db, name, copy.deepcopy(args))
        msgs.append({"role": "assistant", "content": None, "tool_calls": [
            {"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "name": name, "content": out})
    return msgs


def _state(domain, calls, tool=None, args=None):
    return S.build_state(_conv(domain, calls), None if tool is None else {"tool": tool, "args": args or {}},
                         domain=domain)


def part(source, expr, question=None, about=None, plain="a part", **extra):
    out = {"source": source, "plain": plain, "expr": expr, "question": question, "about": about}
    out.update(extra)
    return out


def entry(parts, combine, blocking=False, sources=None, rules=("1",), policy=("S1",), **extra):
    srcs = sources or sorted({p["source"] for p in parts.values()}, key=F.SOURCES.index)
    out = {"sources": list(srcs), "parts": parts, "combine": combine, "start": False, "update": "how it changes",
           "who": "agent", "evidence": "what the message shows", "policy": list(policy), "rules": list(rules),
           "blocking_value": blocking, "missing": "what a missing value gives", "reading": None, "fixed": [],
           "reason": "why", "v2": "what v2 did"}
    out.update(extra)
    return out


TINY_RULE_SET = {
    "predicates": {"fact_a": {"name": "fact_a"}, "fact_b": {"name": "fact_b"}},
    "sentences": [{"id": "S1", "text": "one"}, {"id": "S2", "text": "two"}],
}
TINY_TABLE = {"rules": [
    {"id": "1", "facts": ["fact_a"], "blocking_values": {"fact_a": [False]}},
    {"id": "2", "facts": ["fact_a", "fact_b"], "blocking_values": {"fact_a": [False], "fact_b": [True]}},
    {"id": "10", "facts": ["fact_b"], "blocking_values": {"fact_b": [True]}},
]}

SEEN = "len(events(tool='get_order_details', ok=True)) > 0"
PENDING = "db('order', args['order_id'])['status'] == 'pending'"


def good_doc():
    return {"_about": "test file", "domain": "retail", "schema_version": 1, "facts": {
        "fact_a": entry({"seen": part("event", SEEN), "pending": part("database", PENDING)}, "seen AND pending",
                        blocking=False, rules=["1", "2"]),
        "fact_b": entry({"other": part("arguments", "args['user_id'] != 'nobody'")}, "other", blocking=True,
                        rules=["2", "10"], policy=["S1", "S2"]),
    }}


def V(doc, **kw):
    return F.validate(doc, "retail", rule_set=TINY_RULE_SET, rule_table=TINY_TABLE, kinds=KINDS, **kw)


def doc_from_rule_table(domain):
    """A complete fact file for the real rule set: one arguments part per fact, expr not written yet."""
    with open(paths.rule_set_path(domain), encoding="utf-8") as f:
        rs = json.load(f)
    with open(F.rule_table_path(domain), encoding="utf-8") as f:
        info = F.fact_rules(json.load(f))
    first = rs["sentences"][0]["id"]
    facts = {n: entry({"a": part("arguments", None)}, "a", blocking=info[n]["blocking"][0], rules=info[n]["rules"],
                      policy=[first]) for n in rs["predicates"]}
    return {"_about": "generated for a test", "domain": domain, "schema_version": 1, "facts": facts}


@contextlib.contextmanager
def registered(name, func, lo, hi, keywords=(), source="structure"):
    F.register_name(name, func, lo, hi, keywords, source=source)
    try:
        yield
    finally:
        F.unregister_name(name)


def _restore_registry(saved):
    for n in list(F.registered_names()):
        F.unregister_name(n)
    for h in saved.values():
        F.register_name(h.name, h.func, h.min_args, h.max_args, h.keywords, source=h.source, doc=h.doc)


class RegistryIsolated(unittest.TestCase):
    """Each test starts with an empty registry. What other modules registered on import (code_helpers.py,
    message_view.py, questions.py) is put back after the test, so these tests do not depend on what else is imported
    in the same process."""

    def setUp(self):
        saved = F.registered_names()
        for n in saved:
            F.unregister_name(n)
        self.addCleanup(_restore_registry, saved)


# ----------------------------------------------------------------------------------------------- combine

class TestCombine(RegistryIsolated):

    def test_shapes(self):
        self.assertEqual(F.parse_combine("a"), ("ID", "a"))
        self.assertEqual(F.parse_combine(" a AND b AND c "), ("AND", [("ID", "a"), ("ID", "b"), ("ID", "c")]))
        self.assertEqual(F.parse_combine("NOT a"), ("NOT", ("ID", "a")))
        self.assertEqual(F.parse_combine("NOT NOT a"), ("NOT", ("NOT", ("ID", "a"))))
        self.assertEqual(F.parse_combine("(a OR b) AND NOT c"),
                         ("AND", [("OR", [("ID", "a"), ("ID", "b")]), ("NOT", ("ID", "c"))]))
        self.assertEqual(F.parse_combine("a AND\n(b OR c)"),
                         ("AND", [("ID", "a"), ("OR", [("ID", "b"), ("ID", "c")])]))
        self.assertEqual(F.parse_combine("((a))"), ("ID", "a"))
        self.assertEqual(F.parse_combine("NOT a OR b"), ("OR", [("NOT", ("ID", "a")), ("ID", "b")]))
        self.assertEqual(F.combine_ids(F.parse_combine("b AND (a OR b) AND NOT c")), ["b", "a", "c"])

    def test_errors(self):
        for bad in ("", "   ", "a AND", "AND a", "(a", "a)", "a b", "a & b", "a and b", "a AND b OR c",
                    "a OR b AND c", "()", "NOT", "a OR", "a AND (b", "not a", None, 3):
            with self.subTest(bad=bad), self.assertRaises(F.CombineError):
                F.parse_combine(bad)

    def test_value_equals_python(self):
        formulas = {"a AND b": lambda a, b, c: a and b, "a OR NOT b": lambda a, b, c: a or not b,
                    "(a AND b) OR c": lambda a, b, c: (a and b) or c,
                    "NOT (a OR b) AND c": lambda a, b, c: (not (a or b)) and c,
                    "a AND (b OR NOT c)": lambda a, b, c: a and (b or not c)}
        for text, fn in formulas.items():
            tree = F.parse_combine(text)
            for a, b, c in itertools.product((False, True), repeat=3):
                with self.subTest(text=text, a=a, b=b, c=c):
                    self.assertIs(F.combine_value(tree, {"a": a, "b": b, "c": c}), fn(a, b, c))

    def test_value_with_unknown_parts(self):
        t = F.parse_combine("a AND q")
        self.assertIs(F.combine_value(t, {"a": False}), False)
        self.assertIsNone(F.combine_value(t, {"a": True}))
        t = F.parse_combine("a OR q")
        self.assertIs(F.combine_value(t, {"a": True}), True)
        self.assertIsNone(F.combine_value(t, {"a": False}))
        self.assertIsNone(F.combine_value(F.parse_combine("NOT q"), {}))


# ----------------------------------------------------------------------------------------------- validator

class TestValidator(RegistryIsolated):

    def assertProblem(self, doc, fragment, **kw):
        probs = V(doc, **kw)
        self.assertTrue(any(fragment in p for p in probs), f"{fragment!r} not in {probs}")

    def mutate(self, fn):
        doc = good_doc()
        fn(doc)
        return doc

    def test_good_doc_has_no_problem(self):
        self.assertEqual(V(good_doc()), [])
        doc = good_doc()
        doc["part"] = 1                                  # the split airline file: accepted and ignored
        self.assertEqual(V(doc), [])
        doc["facts"]["fact_a"]["parts"]["pending"]["if_nonexistent"] = True
        doc["facts"]["fact_a"]["reading"] = {"q": "Q4", "default": "the default", "other": "the other"}
        doc["facts"]["fact_a"]["fixed"] = ["a fixed reading"]
        self.assertEqual(V(doc), [])

    def test_top_level(self):
        self.assertEqual(F.validate([], "retail", rule_set=TINY_RULE_SET, rule_table=TINY_TABLE, kinds=KINDS),
                         ["the file is not a JSON object"])
        self.assertProblem(self.mutate(lambda d: d.pop("_about")), "missing top field '_about'")
        self.assertProblem(self.mutate(lambda d: d.update(extra=1)), "unknown top field 'extra'")
        self.assertProblem(self.mutate(lambda d: d.update(domain="airline")), "expected 'retail'")
        self.assertProblem(self.mutate(lambda d: d.update(schema_version=2)), "schema_version must be 1")
        self.assertProblem(self.mutate(lambda d: d.update(schema_version=True)), "schema_version must be 1")
        self.assertProblem(self.mutate(lambda d: d.update(facts=[])), "facts must be an object")

    def test_every_fact_and_no_extra(self):
        self.assertProblem(self.mutate(lambda d: d["facts"].pop("fact_b")), "missing fact 'fact_b'")
        self.assertProblem(self.mutate(lambda d: d["facts"].update(fact_c=d["facts"]["fact_b"])),
                           "unknown fact 'fact_c'")
        doc = self.mutate(lambda d: d["facts"].pop("fact_b"))
        self.assertEqual(V(doc, partial=True), [])
        self.assertProblem(self.mutate(lambda d: d["facts"].update(fact_c={})), "unknown fact 'fact_c'", partial=True)

    def test_fields_types_and_enums(self):
        a = lambda fn: self.mutate(lambda d: fn(d["facts"]["fact_a"]))
        self.assertProblem(self.mutate(lambda d: d["facts"].update(fact_a=[])), "the entry is not an object")
        self.assertProblem(a(lambda e: e.pop("who")), "fact_a: missing field 'who'")
        self.assertProblem(a(lambda e: e.update(note="x")), "fact_a: unknown field 'note'")
        self.assertProblem(a(lambda e: e.update(sources="event")), "sources must be a non-empty list")
        self.assertProblem(a(lambda e: e.update(sources=["event", "database", "judge"])), "'judge' is not one of")
        self.assertProblem(a(lambda e: e.update(sources=["event", "database", "event"])), "listed twice")
        self.assertProblem(a(lambda e: e.update(start=True)), "start must be false")
        self.assertProblem(a(lambda e: e.update(start=None)), "start must be false")
        self.assertProblem(a(lambda e: e.update(update="")), "update must be a non-empty text")
        self.assertProblem(a(lambda e: e.update(v2=None)), "v2 must be a non-empty text")
        self.assertProblem(a(lambda e: e.update(who="judge")), "who must be one of")
        self.assertProblem(a(lambda e: e.update(fixed="x")), "fixed must be a list")
        self.assertProblem(a(lambda e: e.update(reading="Q4")), "reading must be null or")
        self.assertProblem(a(lambda e: e.update(reading={"q": "Q5", "default": "d", "other": "o"})),
                           "reading: q must be one of")
        self.assertProblem(a(lambda e: e.update(reading={"q": "Q6", "default": "d"})), "reading: missing field 'other'")
        self.assertProblem(a(lambda e: e.update(reading={"q": "Q6", "default": "d", "other": "o", "x": 1})),
                           "reading: unknown field 'x'")
        self.assertProblem(a(lambda e: e.update(reading={"q": "Q7", "default": "", "other": "o"})),
                           "reading: default must be a non-empty text")

    def test_parts(self):
        p = lambda fn: self.mutate(lambda d: fn(d["facts"]["fact_a"]["parts"]))
        self.assertProblem(self.mutate(lambda d: d["facts"]["fact_a"].update(parts={})), "parts must be a non-empty")
        self.assertProblem(p(lambda ps: ps["seen"].pop("plain")), "part 'seen': missing field 'plain'")
        self.assertProblem(p(lambda ps: ps["seen"].update(weight=1)), "part 'seen': unknown field 'weight'")
        self.assertProblem(p(lambda ps: ps["seen"].update(source="judge")), "source must be one of")
        self.assertProblem(p(lambda ps: ps["seen"].update(source="structure")), "is not in the fact's sources")
        self.assertProblem(p(lambda ps: ps["seen"].update(plain=" ")), "plain must be a non-empty text")
        self.assertProblem(p(lambda ps: ps["seen"].update(expr="")), "expr must be null or a non-empty text")
        self.assertProblem(p(lambda ps: ps["seen"].update(about="")), "about must be null or a non-empty text")
        self.assertProblem(p(lambda ps: ps["seen"].update(if_nonexistent="yes")), "if_nonexistent must be")
        doc = self.mutate(lambda d: d["facts"]["fact_a"].update(sources=["event", "database", "structure"]))
        self.assertProblem(doc, "source 'structure' is in sources, but no part has it")
        for bad_id in ("AND", "not", "1x", "a-b"):
            doc = self.mutate(lambda d: d["facts"]["fact_a"]["parts"].update({bad_id: part("event", SEEN)}))
            self.assertProblem(doc, f"part id {bad_id!r}")

    def test_question_ids(self):
        def q(d, **kw):
            e = d["facts"]["fact_a"]
            e["sources"].append("question")
            e["parts"]["ok"] = part("question", None, **kw)
            e["combine"] = "seen AND pending AND ok"
        self.assertEqual(V(self.mutate(lambda d: q(d, question="K1", about="the listing and the reply"))), [])
        self.assertEqual(V(self.mutate(lambda d: q(d, question="K15"))), [])     # a new K id: shape only
        self.assertProblem(self.mutate(lambda d: q(d)), "a question part must name its question")
        for bad in ("K0", "Q1", "k1", "K1a", 1):
            self.assertProblem(self.mutate(lambda d: q(d, question=bad)), "question must be null or a question id")
        doc = self.mutate(lambda d: d["facts"]["fact_a"]["parts"]["seen"].update(question="K2"))
        self.assertProblem(doc, "only a question part names a question")

    def test_combine(self):
        c = lambda text: self.mutate(lambda d: d["facts"]["fact_a"].update(combine=text))
        self.assertProblem(c("seen AND"), "combine: unexpected end")
        self.assertProblem(c(""), "combine: combine must be a non-empty text")
        self.assertProblem(c("seen AND pending AND other"), "combine uses 'other', which is not a declared part")
        self.assertProblem(c("seen"), "part 'pending' is declared but combine does not use it")
        self.assertProblem(c("seen AND pending OR seen"), "AND and OR mixed without parentheses")
        self.assertEqual(V(c("(seen AND pending) OR NOT seen")), [])

    def test_policy_rules_blocking(self):
        a = lambda fn: self.mutate(lambda d: fn(d["facts"]["fact_a"]))
        self.assertProblem(a(lambda e: e.update(policy=[])), "policy must be a non-empty list")
        self.assertProblem(a(lambda e: e.update(policy=["S9"])), "policy: S9 is not a sentence of the rule set")
        self.assertProblem(a(lambda e: e.update(policy=["line 3"])), "is not a sentence id")
        self.assertProblem(a(lambda e: e.update(policy=["S1", "S1"])), "policy: a sentence id is listed twice")
        self.assertProblem(a(lambda e: e.update(rules=["1"])), "rules: missing ['2']")
        self.assertProblem(a(lambda e: e.update(rules=["1", "2", "10"])), "not in the rule table for this fact: ['10']")
        self.assertProblem(a(lambda e: e.update(rules=[1, 2])), "rules must be a list of rule ids")
        self.assertProblem(a(lambda e: e.update(rules=["1", "2", "2"])), "rules: a rule id is listed twice")
        self.assertProblem(a(lambda e: e.update(blocking_value=True)), "the rule table says false")
        self.assertProblem(a(lambda e: e.update(blocking_value=None)), "blocking_value must be true or false")
        self.assertProblem(a(lambda e: e.update(blocking_value=0)), "blocking_value must be true or false")
        table = copy.deepcopy(TINY_TABLE)
        table["rules"][0]["blocking_values"]["fact_a"] = [True]
        probs = F.validate(good_doc(), "retail", rule_set=TINY_RULE_SET, rule_table=table, kinds=KINDS)
        self.assertTrue(any("blocking values [False, True]" in p for p in probs), probs)
        rs = copy.deepcopy(TINY_RULE_SET)
        rs["predicates"]["fact_c"] = {"name": "fact_c"}
        doc = good_doc()
        doc["facts"]["fact_c"] = copy.deepcopy(doc["facts"]["fact_b"])
        probs = F.validate(doc, "retail", rule_set=rs, rule_table=TINY_TABLE, kinds=KINDS)
        self.assertTrue(any("fact_c: the fact is in no rule" in p for p in probs), probs)

    def test_expressions(self):
        e = lambda expr: self.mutate(lambda d: d["facts"]["fact_a"]["parts"]["seen"].update(expr=expr))
        self.assertProblem(e("len(events()) + 1 > 0"), "arithmetic")
        self.assertProblem(e("max(1, 2) > 1"), "unknown name 'max'")
        self.assertProblem(e("user_typed(args['email'])"), "unknown name 'user_typed'")
        self.assertProblem(e("__import__('os') is None"), "unknown name '__import__'")
        self.assertProblem(e("db('flight', 'x') is None"), "unknown kind 'flight'")
        self.assertProblem(e("args['x'][0:1] == []"), "slices are not allowed")
        self.assertProblem(e("args.keys() == []"), "method .keys() is not allowed")
        self.assertProblem(e("lambda: True"), "Lambda is not allowed")
        self.assertProblem(e("x == 1"), "unknown name 'x'")
        self.assertEqual(V(e("not any(o['status'] == 'x' for o in db_all('order'))")), [])

    def test_registered_helpers_in_the_validator(self):
        e = lambda src, expr: self.mutate(lambda d: d["facts"]["fact_b"].update(
            sources=[src], parts={"other": part(src, expr, question="K1" if src == "question" else None)}))
        doc = e("structure", "user_typed(args['user_id'])")
        self.assertProblem(doc, "unknown name 'user_typed'")
        with registered("user_typed", lambda ctx, v, exact=False: True, 1, 1, ("exact",), source="structure"):
            self.assertEqual(V(doc), [])
            self.assertEqual(V(e("structure", "user_typed(args['user_id'], exact=True)")), [])
            self.assertProblem(e("structure", "user_typed()"), "user_typed() takes 1 positional arguments")
            self.assertProblem(e("structure", "user_typed(1, 2)"), "user_typed() takes 1 positional arguments")
            self.assertProblem(e("structure", "user_typed(1, loose=True)"), "user_typed() has no keyword 'loose'")
            self.assertProblem(e("structure", "user_typed == 1"), "may only be called")
            self.assertProblem(e("structure", "any(user_typed for user_typed in [1])"), "cannot be used as a loop")
            self.assertProblem(e("arguments", "user_typed(args['user_id'])"),
                               "user_typed() is a structure helper; a part with source 'arguments' may not call it")
            with registered("asked", lambda ctx, k, m: True, 2, 2, source="question"):
                self.assertEqual(V(e("question", "asked('K1', user_typed(args['user_id']))")), [])
                self.assertProblem(e("database", "asked('K1', 1)"),
                                   "asked() is a question helper; a part with source 'database' may not call it")
                self.assertProblem(e("question", "user_typed(args['user_id'])"),
                                   "a question part must call a registered question helper")
        self.assertProblem(doc, "unknown name 'user_typed'")                         # unregistered again

    def test_real_rule_sets(self):
        for domain in ("retail", "airline"):
            with self.subTest(domain=domain):
                doc = doc_from_rule_table(domain)
                self.assertEqual(F.validate(doc, domain), [])
                n = len(doc["facts"])
                self.assertEqual(n, {"retail": 24, "airline": 42}[domain])
                one = next(iter(doc["facts"]))
                doc["facts"][one]["blocking_value"] = not doc["facts"][one]["blocking_value"]
                doc["facts"][one]["parts"]["a"]["expr"] = "db('order', args['id']) is None"
                probs = F.validate(doc, domain)
                self.assertTrue(any("the rule table says" in p for p in probs), probs)
                if domain == "airline":
                    self.assertTrue(any("unknown kind 'order'" in p for p in probs), probs)


# ----------------------------------------------------------------------------------------------- registry

class TestRegistry(RegistryIsolated):

    def test_refused_names_and_limits(self):
        f = lambda ctx: True
        for name in ("db", "args", "today", "len", "get", "events", "item", "_hidden", "class", "a-b", "", None, "AND",
                     "or"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                F.register_name(name, f, 0, 0, source="structure")
        for lo, hi in ((-1, 0), (2, 1), (True, 1), (0, "1")):
            with self.subTest(lo=lo, hi=hi), self.assertRaises(ValueError):
                F.register_name("helper_x", f, lo, hi, source="structure")
        for kws in (("a-b",), ("x", "x"), ("class",)):
            with self.subTest(kws=kws), self.assertRaises(ValueError):
                F.register_name("helper_x", f, 0, 0, kws, source="structure")
        with self.assertRaises(ValueError):
            F.register_name("helper_x", f, 0, 0, source="judge")
        with self.assertRaises(ValueError):
            F.register_name("helper_x", f, 0, 0)                            # source is required
        with self.assertRaises(ValueError):
            F.register_name("helper_x", "not callable", 0, 0, source="structure")
        self.assertNotIn("helper_x", F.registered_names())

    def test_register_twice_and_unregister(self):
        f = lambda ctx: True
        h = F.register_name("helper_y", f, 0, 0, source="database", doc="test")
        try:
            self.assertIs(F.register_name("helper_y", f, 0, 0, source="database", doc="test"), h)   # same: no change
            with self.assertRaises(ValueError):
                F.register_name("helper_y", lambda ctx: False, 0, 0, source="database", doc="test")
            with self.assertRaises(ValueError):
                F.register_name("helper_y", f, 0, 1, source="database", doc="test")
            self.assertEqual(F.registered_names()["helper_y"].source, "database")
            self.assertEqual(F.validate_expr("helper_y()")["helpers"], ["helper_y"])
        finally:
            F.unregister_name("helper_y")
        with self.assertRaises(F.UnknownName):
            F.validate_expr("helper_y()")
        with self.assertRaises(KeyError):
            F.unregister_name("helper_y")

    def test_tests_do_not_depend_on_other_registrations(self):
        """A name registered outside (as p7's message_view.py registers user_typed on import) is hidden during an
        isolated test and put back after it; what the test registers is removed."""
        outside = lambda ctx, v: True
        F.register_name("user_typed", outside, 1, 1, source="structure", doc="from outside")
        seen = {}

        class Inner(RegistryIsolated):
            def test_inner(self):
                seen["names"] = sorted(F.registered_names())
                F.register_name("t5_inner", lambda ctx: True, 0, 0, source="event")

        result = unittest.TestResult()
        unittest.defaultTestLoader.loadTestsFromTestCase(Inner).run(result)
        self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
        self.assertEqual(seen["names"], [])
        self.assertEqual(sorted(F.registered_names()), ["user_typed"])
        self.assertIs(F.registered_names()["user_typed"].func, outside)

    def test_frozen_format_is_not_changed(self):
        functions, values = dict(L.FUNCTIONS), tuple(L.VALUES)
        with registered("helper_z", lambda ctx: True, 0, 0, source="event"):
            self.assertEqual(F.validate_expr("helper_z() and len(events()) > 0")["helpers"], ["helper_z"])
            with self.assertRaises(L.LookupFormatError):                    # the frozen validator still refuses it
                L.validate("helper_z()")
            self.assertEqual(L.FUNCTIONS, functions)
            self.assertEqual(L.VALUES, values)
        self.assertEqual(F.validate_expr(PENDING, KINDS), {"calls": ["db"], "kinds": ["order"], "helpers": [],
                                                           "values": []})


# ----------------------------------------------------------------------------------------------- evaluator

class TestEvaluator(RegistryIsolated):

    @classmethod
    def setUpClass(cls):
        db = S.load_db("retail")
        cls.pending = next(o for o in db["orders"].values() if o["status"] == "pending")
        cls.delivered = next(o for o in db["orders"].values() if o["status"] == "delivered")
        cls.user = db["users"][cls.pending["user_id"]]
        cls.state = _state("retail", [("find_user_id_by_email", {"email": cls.user["email"]}),
                                      ("get_order_details", {"order_id": cls.pending["order_id"]})])
        cls.fact_a = good_doc()["facts"]["fact_a"]

    def ev(self, e, args, **kw):
        r = F.evaluate(e, self.state, args, name="t", **kw)
        self.assertIs(type(r["value"]), bool)                               # two values only, always
        for p in r["parts"].values():
            self.assertIn(p["value"], (True, False, None))
            if p["how"] in ("value", "nonexistent"):
                self.assertIs(type(p["value"]), bool)
            else:
                self.assertIsNone(p["value"])
        return r

    def test_true_and_false(self):
        r = self.ev(self.fact_a, {"order_id": self.pending["order_id"]})
        self.assertIs(r["value"], True)
        self.assertEqual((r["how"], r["problems"], r["source"]), ("combine", [], ["database", "event"]))
        self.assertEqual({k: (p["value"], p["how"], p["source"]) for k, p in r["parts"].items()},
                         {"seen": (True, "value", "event"), "pending": (True, "value", "database")})
        self.assertEqual(r["evidence"], {"text": "what the message shows", "notes": []})
        r = self.ev(self.fact_a, {"order_id": self.delivered["order_id"]})
        self.assertIs(r["value"], False)
        self.assertEqual((r["parts"]["seen"]["value"], r["parts"]["pending"]["value"]), (True, False))
        empty = S.build_state(_conv("retail", []), domain="retail")
        r = F.evaluate(self.fact_a, empty, {"order_id": self.pending["order_id"]})
        self.assertEqual((r["value"], r["parts"]["seen"]["value"], r["parts"]["pending"]["value"]), (False, False, True))

    def test_reads_are_recorded(self):
        oid = self.pending["order_id"]
        r = self.ev(self.fact_a, {"order_id": oid})
        db_read = {"read": "db", "kind": "order", "id": oid, "found": True}
        self.assertEqual(r["parts"]["pending"]["reads"], [db_read])
        ev_read = r["parts"]["seen"]["reads"]
        self.assertEqual([(x["read"], x["tool"], x["ok"], x["indices"]) for x in ev_read],
                         [("events", ["get_order_details"], True, [1])])
        self.assertEqual(r["reads"], ev_read + [db_read])
        r = self.ev(self.fact_a, {"order_id": "#W0000000"})
        self.assertIn({"read": "db", "kind": "order", "id": "#W0000000", "found": False}, r["reads"])

    def test_args_default_to_the_pending_call(self):
        st = _state("retail", [("get_order_details", {"order_id": self.pending["order_id"]})],
                    tool="cancel_pending_order", args={"order_id": self.pending["order_id"], "reason": "x"})
        self.assertIs(F.evaluate(self.fact_a, st, None)["value"], True)

    def test_missing_argument_takes_the_blocking_value(self):
        for blocking in (False, True):
            with self.subTest(blocking=blocking):
                e = dict(self.fact_a, blocking_value=blocking)
                r = self.ev(e, {})
                self.assertIs(r["value"], blocking)
                self.assertEqual(r["how"], "blocking_value")
                self.assertEqual([(p["kind"], p["part"]) for p in r["problems"]], [("missing_argument", "pending")])
                self.assertEqual(r["parts"]["pending"]["how"], "problem")
                self.assertIs(r["parts"]["seen"]["value"], True)            # the other code part still ran
        e = entry({"n": part("arguments", "args['user_id'] == 'x'")}, "NOT n", blocking=True)
        r = self.ev(e, {})
        self.assertEqual((r["value"], [p["kind"] for p in r["problems"]]), (True, ["missing_argument"]))

    def test_missing_argument_inside_a_list(self):
        e = entry({"n": part("arguments", "args['item_ids'][3] == 'x'")}, "n", blocking=False)
        r = self.ev(e, {"item_ids": ["1"]})
        self.assertEqual([p["kind"] for p in r["problems"]], ["missing_argument"])
        e = entry({"n": part("arguments", "args['passengers'][0]['dob'] == 'x'")}, "n", blocking=True)
        r = self.ev(e, {"passengers": [{"first_name": "A"}]})
        self.assertEqual((r["value"], [p["kind"] for p in r["problems"]]), (True, ["missing_argument"]))
        e = entry({"n": part("arguments", "args.get('reason', 'none') == 'none'")}, "n")
        self.assertEqual(self.ev(e, {})["problems"], [])                   # .get: the expression handles it

    def test_missing_field_of_an_existing_object_is_counted(self):
        oid = self.pending["order_id"]
        for expr in ("db('order', args['order_id'])['no_such_field'] == 1",
                     "db('order', args['order_id'])['payment_history'][99]['amount'] > 0",
                     "db('user', db('order', args['order_id'])['user_id'])['no_such_field'] == 1"):
            for blocking in (False, True):
                with self.subTest(expr=expr, blocking=blocking):
                    e = entry({"p": part("database", expr)}, "NOT p", blocking=blocking)
                    r = self.ev(e, {"order_id": oid})
                    self.assertIs(r["value"], blocking)
                    self.assertEqual([p["kind"] for p in r["problems"]], ["missing_field"])
                    self.assertIn("existing", r["problems"][0]["detail"])

    def test_type_error_is_counted(self):
        e = entry({"p": part("database", "db('order', args['order_id']).get('no_such_field') > 5")}, "p",
                  blocking=True)
        r = self.ev(e, {"order_id": self.pending["order_id"]})
        self.assertEqual((r["value"], [p["kind"] for p in r["problems"]]), (True, ["type_error"]))

    def test_nonexistent_id(self):
        args = {"order_id": "#W0000000"}
        r = self.ev(entry({"p": part("database", PENDING)}, "p", blocking=True), args)
        self.assertEqual((r["value"], r["how"], r["problems"]), (False, "combine", []))
        self.assertEqual(r["parts"]["p"]["how"], "nonexistent")
        r = self.ev(entry({"p": part("database", PENDING, if_nonexistent=True)}, "p"), args)
        self.assertIs(r["value"], True)
        r = self.ev(entry({"p": part("database", PENDING)}, "NOT p"), args)
        self.assertIs(r["value"], True)                                     # the part is false, not the fact
        r = self.ev(entry({"p": part("database", "db('user', 'nobody_1').get('email') == 'x'")}, "p"), {})
        self.assertEqual((r["value"], r["parts"]["p"]["how"]), (False, "nonexistent"))
        r = self.ev(entry({"p": part("database", "db('order', args['order_id']) is None")}, "p"), args)
        self.assertEqual((r["value"], r["parts"]["p"]["how"]), (True, "value"))   # the expression handles None
        r = self.ev(entry({"p": part("database", PENDING)}, "p"), {"order_id": 12345})   # not even a text id
        self.assertEqual(r["parts"]["p"]["how"], "nonexistent")

    def test_two_values_only(self):
        for expr in ("len(events())", "db('order', args['order_id'])", "db('order', 'none_such')",
                     "args['order_id']", "[True]"):
            with self.subTest(expr=expr), self.assertRaises(F.FactEvalError):
                F.evaluate(entry({"p": part("database", expr)}, "p"), self.state,
                           {"order_id": self.pending["order_id"]})

    def test_not_defined_yet(self):
        e = entry({"seen": part("event", SEEN), "later": part("structure", None)}, "seen AND later")
        with self.assertRaises(F.NotDefinedYet) as cm:
            F.evaluate(e, self.state, {}, name="fact_x")
        self.assertIn("fact_x: part 'later' (structure) has no expression yet", str(cm.exception))
        e = entry({"seen": part("event", SEEN), "q": part("question", None, question="K1")}, "seen OR q")
        with self.assertRaises(F.NotDefinedYet):                            # even when q would not be needed
            F.evaluate(e, self.state, {})
        e = entry({"t": part("structure", "user_typed(args['email'])")}, "t")
        with self.assertRaises(F.NotDefinedYet) as cm:
            F.evaluate(e, self.state, {"email": "x"})
        self.assertIn("'user_typed', which is not registered", str(cm.exception))
        with registered("user_typed", lambda ctx, v: v == "x", 1, 1):
            self.assertIs(self.ev(e, {"email": "x"})["value"], True)
        with self.assertRaises(F.NotDefinedYet):
            F.evaluate(e, self.state, {"email": "x"})

    def test_registered_helper_gets_the_context(self):
        seen = {}

        def owner_is(ctx, oid, user=None, strict=False):
            seen.update(fact=ctx.fact, part=ctx.part_id, domain=ctx.domain, view=ctx.need_view(), args=dict(ctx.args))
            ctx.note({"owner_checked": oid})
            o = ctx.state.db_get("order", oid)                              # a read through the recording state
            return o is not None and o["user_id"] == (user or ctx.arg("user_id"))

        e = entry({"o": part("structure", "owner_is(args['order_id'], strict=True)")}, "o", blocking=True)
        with registered("owner_is", owner_is, 1, 2, ("strict",), source="structure"):
            args = {"order_id": self.pending["order_id"], "user_id": self.pending["user_id"]}
            r = self.ev(e, args, view=["a view"])
            self.assertIs(r["value"], True)
            self.assertEqual(seen, {"fact": "t", "part": "o", "domain": "retail", "view": ["a view"], "args": args})
            self.assertEqual(r["evidence"]["notes"], [{"part": "o", "item": None,
                                                       "note": {"owner_checked": args["order_id"]}}])
            self.assertEqual(r["parts"]["o"]["reads"],
                             [{"read": "db", "kind": "order", "id": args["order_id"], "found": True}])
            r = self.ev(e, {"order_id": self.pending["order_id"]}, view=["a view"])
            self.assertEqual((r["value"], [p["kind"] for p in r["problems"]]), (True, ["missing_argument"]))
            with self.assertRaises(F.MissingInput):
                F.evaluate(e, self.state, args)                             # no view given

    def test_helper_errors(self):
        def unclear(ctx, k):
            raise F.UseBlockingValue("the answer was unclear", kind="unclear")

        def broken(ctx):
            return {}["x"]

        def missing(ctx):
            raise F.MissingObject("no such object")

        with registered("unclear_k", unclear, 1, 1, source="question"), \
                registered("broken_h", broken, 0, 0, source="database"), \
                registered("missing_h", missing, 0, 0, source="database"):
            r = self.ev(entry({"q": part("question", "unclear_k('K1')", question="K1")}, "q", blocking=True), {})
            self.assertEqual((r["value"], r["problems"]), (True, [{"kind": "unclear", "part": "q", "item": None,
                                                                   "detail": "the answer was unclear"}]))
            r = self.ev(entry({"b": part("database", "broken_h()")}, "b"), {})
            self.assertEqual([p["kind"] for p in r["problems"]], ["missing_field"])
            r = self.ev(entry({"m": part("database", "missing_h()", if_nonexistent=True)}, "m"), {})
            self.assertEqual((r["value"], r["parts"]["m"]["how"]), (True, "nonexistent"))
            with self.assertRaises(L.LookupFormatError):                   # a question helper in a database part
                F.evaluate(entry({"q": part("database", "unclear_k('K1')")}, "q"), self.state, {})

    def test_question_parts_run_only_when_needed(self):
        calls = []

        def asked(ctx, k):
            calls.append(k)
            return ctx.need_answers()[k]

        with registered("asked_k", asked, 1, 1, source="question"):
            q = part("question", "asked_k('K1')", question="K1")
            code_true, code_false = part("arguments", "args['n'] == 1"), part("arguments", "args['n'] == 2")
            for combine, code, want_calls, want in (("c AND q", code_false, 0, False), ("c AND q", code_true, 1, True),
                                                    ("c OR q", code_true, 0, True), ("c OR q", code_false, 1, True),
                                                    ("q AND c", code_false, 0, False), ("NOT c AND q", code_true, 0,
                                                                                        False)):
                with self.subTest(combine=combine, code=code["expr"]):
                    calls.clear()
                    r = self.ev(entry({"c": code, "q": q}, combine), {"n": 1}, answers={"K1": True})
                    self.assertEqual((len(calls), r["value"]), (want_calls, want))
                    self.assertEqual(r["parts"]["q"]["how"], "value" if want_calls else "not_needed")
            calls.clear()
            r = self.ev(entry({"c": part("arguments", "args['m'] == 1"), "q": q}, "c OR q", blocking=True), {"n": 1},
                        answers={"K1": False})
            self.assertEqual((calls, r["value"], r["parts"]["q"]["how"]), ([], True, "not_run"))   # problem first
            q2 = part("question", "asked_k('K2')", question="K2")
            calls.clear()
            r = self.ev(entry({"c": code_false, "a": q, "b": q2}, "(c AND a) OR b"), {"n": 1},
                        answers={"K1": True, "K2": False})
            self.assertEqual((calls, r["value"]), (["K2"], False))         # a does not matter once c is false
            with self.assertRaises(F.MissingInput):
                F.evaluate(entry({"q": q}, "q"), self.state, {})

    def test_state_is_not_changed(self):
        before = json.dumps(self.state.db, sort_keys=True)
        n_events = len(self.state.events)
        self.ev(self.fact_a, {"order_id": self.pending["order_id"]})
        self.ev(self.fact_a, {})
        self.assertEqual(json.dumps(self.state.db, sort_keys=True), before)
        self.assertEqual(len(self.state.events), n_events)

    def test_bad_blocking_value_is_refused(self):
        with self.assertRaises(ValueError):
            F.evaluate(dict(self.fact_a, blocking_value=None), self.state, {})


# ----------------------------------------------------------------------------------------------- schema additions

FIRST = "db('user', args['user_id'])['name']['first_name']"


def per_passenger(**extra):
    """a OR b for each passenger of the call: a = the passenger's dob is 1990-01-01 (arguments), b = the passenger's
    first name is the user's own (database)."""
    return entry({"a": part("arguments", "item['dob'] == '1990-01-01'"),
                  "b": part("database", f"item['first_name'] == {FIRST}")}, "a OR b",
                 for_each={"arg": "passengers", "if_empty": False}, **extra)


class TestPartWho(RegistryIsolated):

    def test_validator(self):
        doc = good_doc()
        doc["facts"]["fact_a"]["parts"]["pending"]["who"] = "none"
        doc["facts"]["fact_a"]["parts"]["seen"]["who"] = None
        self.assertEqual(V(doc), [])
        for bad in ("judge", "", 1, True):
            doc["facts"]["fact_a"]["parts"]["pending"]["who"] = bad
            probs = V(doc)
            self.assertTrue(any("part 'pending': who must be null or one of" in p for p in probs), probs)

    def test_effective_who_in_the_result(self):
        e = good_doc()["facts"]["fact_a"]                  # fact who: agent
        e["parts"]["pending"]["who"] = "none"
        db = S.load_db("retail")
        o = next(x for x in db["orders"].values() if x["status"] == "pending")
        st = _state("retail", [("get_order_details", {"order_id": o["order_id"]})])
        r = F.evaluate(e, st, {"order_id": o["order_id"]})
        self.assertEqual({k: p["who"] for k, p in r["parts"].items()}, {"seen": "agent", "pending": "none"})
        r = F.evaluate(e, st, {})                          # a problem: every part still says its who
        self.assertEqual({k: p["who"] for k, p in r["parts"].items()}, {"seen": "agent", "pending": "none"})
        b = F.blocking_result(e, "replay_mismatch", "event 3 differs", name="fact_a")
        self.assertEqual({k: p["who"] for k, p in b["parts"].items()}, {"seen": "agent", "pending": "none"})


class TestForEach(RegistryIsolated):

    @classmethod
    def setUpClass(cls):
        db = S.load_db("retail")
        cls.uid, cls.user = next(iter(db["users"].items()))
        cls.first = cls.user["name"]["first_name"]
        cls.state = _state("retail", [])

    def ev(self, e, args, **kw):
        r = F.evaluate(e, self.state, args, name="t", **kw)
        self.assertIs(type(r["value"]), bool)
        return r

    def test_validator(self):
        doc = good_doc()
        doc["facts"]["fact_b"] = per_passenger(blocking=True, rules=["2", "10"], policy=["S1"])
        self.assertEqual(V(doc), [])
        fb = lambda fn: (lambda d: (d["facts"].update(fact_b=per_passenger(blocking=True, rules=["2", "10"])),
                                    fn(d["facts"]["fact_b"])))
        for fn, fragment in (
                (lambda e: e.update(for_each="passengers"), "for_each must be null or"),
                (lambda e: e["for_each"].pop("if_empty"), "for_each: missing field 'if_empty'"),
                (lambda e: e["for_each"].update(each=1), "for_each: unknown field 'each'"),
                (lambda e: e["for_each"].update(arg="passengers[0]"), "for_each: arg must be an argument path"),
                (lambda e: e["for_each"].update(arg=""), "for_each: arg must be an argument path"),
                (lambda e: e["for_each"].update(if_empty=None), "for_each: if_empty must be true or false"),
                (lambda e: e["parts"]["a"].update(expr="args['x'] == 1") or e["parts"]["b"].update(expr="args['y'] == 1"),
                 "for_each is set, but no part expression reads item"),
                (lambda e: e["parts"]["a"].update(expr="any(item for item in args['passengers'])"),
                 "cannot be used as a loop variable"),
                (lambda e: e.pop("for_each"), "unknown name 'item' (not in the lookup format and not registered) (item: "
                                              "only in a fact with for_each)")):
            with self.subTest(fragment=fragment):
                d = good_doc()
                fb(fn)(d)
                probs = V(d)
                self.assertTrue(any(fragment in p for p in probs), probs)
        d = good_doc()
        d["facts"]["fact_b"] = per_passenger(blocking=True, rules=["2", "10"])
        d["facts"]["fact_b"]["for_each"]["arg"] = "flights.legs"            # a nested path is fine
        d["facts"]["fact_b"]["parts"]["a"]["expr"] = None                    # not written yet: counts as reading item
        d["facts"]["fact_b"]["parts"]["b"]["expr"] = "args['y'] == 1"
        self.assertEqual(V(d), [])

    def test_every_item_must_hold(self):
        e = per_passenger()
        ok_dob = {"first_name": "Zed", "dob": "1990-01-01"}
        ok_name = {"first_name": self.first, "dob": "2000-02-02"}
        bad = {"first_name": "Zed", "dob": "2000-02-02"}
        r = self.ev(e, {"user_id": self.uid, "passengers": [ok_dob, ok_name]})
        self.assertEqual((r["value"], r["how"], r["deciding_item"]), (True, "combine", 1))
        self.assertEqual([(i["index"], i["value"]) for i in r["items"]], [(0, True), (1, True)])
        self.assertEqual({k: p["value"] for k, p in r["items"][0]["parts"].items()}, {"a": True, "b": False})
        self.assertEqual({k: p["value"] for k, p in r["items"][1]["parts"].items()}, {"a": False, "b": True})
        r = self.ev(e, {"user_id": self.uid, "passengers": [ok_dob, bad, ok_name]})
        self.assertEqual((r["value"], r["deciding_item"]), (False, 1))
        self.assertIs(r["parts"], r["items"][1]["parts"])                     # the deciding item's parts
        self.assertEqual([i["value"] for i in r["items"]], [True, False, None])   # item 2 not resolved
        self.assertIn({"read": "db", "kind": "user", "id": self.uid, "found": True}, r["reads"])

    def test_empty_missing_and_bad_lists(self):
        for if_empty in (False, True):
            e = per_passenger()
            e["for_each"]["if_empty"] = if_empty
            r = self.ev(e, {"user_id": self.uid, "passengers": []})
            self.assertEqual((r["value"], r["how"], r["items"], r["parts"], r["problems"]),
                             (if_empty, "combine", [], {}, []))
        for blocking in (False, True):
            e = per_passenger(blocking=blocking)
            r = self.ev(e, {"user_id": self.uid})
            self.assertEqual((r["value"], r["how"]), (blocking, "blocking_value"))
            self.assertEqual([(p["kind"], p["part"], p["item"]) for p in r["problems"]],
                             [("missing_argument", None, None)])
            r = self.ev(e, {"user_id": self.uid, "passengers": "Zed"})
            self.assertEqual((r["value"], [p["kind"] for p in r["problems"]]), (blocking, ["type_error"]))
            r = self.ev(e, {"user_id": self.uid, "passengers": [{"first_name": self.first, "dob": "1990-01-01"},
                                                                 {"first_name": "Zed"}]})
            self.assertEqual((r["value"], r["deciding_item"]), (blocking, 1))
            self.assertEqual([(p["kind"], p["part"], p["item"]) for p in r["problems"]],
                             [("missing_argument", "a", 1)])                 # a missing field of the item
        e = per_passenger(blocking=True)
        e["for_each"]["arg"] = "trip.passengers"
        r = self.ev(e, {"user_id": self.uid, "trip": {"passengers": [{"first_name": self.first, "dob": "x"}]}})
        self.assertEqual((r["value"], r["how"]), (True, "combine"))
        for trip in ("a text", None, ["a list"]):
            with self.subTest(trip=trip):
                r = self.ev(e, {"user_id": self.uid, "trip": trip})
                self.assertEqual((r["value"], r["how"]), (True, "blocking_value"))
                self.assertIn(r["problems"][0]["kind"], ("type_error", "missing_argument"))

    def test_questions_per_item_only_when_needed(self):
        calls = []

        def asked(ctx, k):
            calls.append((k, ctx.item["first_name"]))
            return ctx.need_answers()[ctx.item["first_name"]]

        with registered("asked_item", asked, 1, 1, source="question"):
            e = entry({"a": part("arguments", "item['dob'] == '1990-01-01'"),
                       "q": part("question", "asked_item('K1')", question="K1")}, "a OR q",
                      for_each={"arg": "passengers", "if_empty": False})
            ps = [{"first_name": "P0", "dob": "1990-01-01"}, {"first_name": "P1", "dob": "x"},
                  {"first_name": "P2", "dob": "x"}, {"first_name": "P3", "dob": "x"}]
            r = self.ev(e, {"passengers": ps}, answers={"P1": True, "P2": False, "P3": True})
            self.assertEqual(r["value"], False)
            self.assertEqual(calls, [("K1", "P1"), ("K1", "P2")])            # P0 needs no question; P3 not reached
            self.assertEqual([i["parts"]["q"]["how"] for i in r["items"]],
                             ["not_needed", "value", "value", "not_needed"])
            self.assertEqual(r["deciding_item"], 2)
            calls.clear()
            r = self.ev(e, {"passengers": ps[:2]}, answers={"P1": True})
            self.assertEqual((r["value"], calls), (True, [("K1", "P1")]))


class TestBlockingResult(RegistryIsolated):

    def test_shape(self):
        e = good_doc()["facts"]["fact_b"]
        r = F.blocking_result(e, "replay_mismatch", "event 2 differs", name="fact_b")
        self.assertEqual((r["fact"], r["value"], r["how"], r["reads"], r["items"]),
                         ("fact_b", True, "blocking_value", [], None))
        self.assertEqual(r["problems"], [{"kind": "replay_mismatch", "part": None, "item": None,
                                          "detail": "event 2 differs"}])
        self.assertEqual(r["parts"]["other"]["how"], "not_run")
        self.assertEqual(F.blocking_result(per_passenger(), "parse_problem")["items"], [])
        same = F.evaluate(e, _state("retail", []), {}, name="fact_b")       # same keys as evaluate()
        self.assertEqual(set(r), set(same))
        with self.assertRaises(ValueError):
            F.blocking_result(dict(e, blocking_value=None), "x")


# ----------------------------------------------------------------------------------------------- the CLI

class TestCli(RegistryIsolated):

    def test_check_good_and_bad_file(self):
        with tempfile.TemporaryDirectory(prefix="v3_facts_test_") as tmp:
            path = os.path.join(tmp, "facts.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(doc_from_rule_table("retail"), f)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(F.main(["--check", "retail", "--file", path]), 0)
            self.assertIn("retail: ", out.getvalue())
            self.assertIn("0 problems", out.getvalue())
            doc = doc_from_rule_table("retail")
            doc["facts"].pop("user_authenticated")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(doc, f)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(F.main(["--check", "retail", "--file", path]), 1)
                self.assertEqual(F.main(["--check", "retail", "--file", path, "--partial"]), 0)
            self.assertIn("PROBLEM: missing fact 'user_authenticated'", out.getvalue())


if __name__ == "__main__":
    unittest.main()
