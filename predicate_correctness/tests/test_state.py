"""Tests for state_tracker/state.py (Part 4). Standard library only, no LLM calls.

Run from predicate_correctness/:  python3 -B -m unittest tests.test_state -v

The conversations are hand-made. The saved tool outputs in them are made the way the real run made them: by running
τ-bench's tool code on a separate copy of the data (`_conv`). The expected values are plain facts of the input
(an order's status in the data files, the ids in a search output), not judgements.
"""
from __future__ import annotations

import copy
import datetime
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from state_tracker import paths, tau_copy  # noqa: E402
from state_tracker import state as S  # noqa: E402


def _conv(domain: str, calls, outputs=None):
    """A conversation in chat format: system (the policy), user, then per call an assistant message with one tool
    call and its tool message. The tool message holds the output of τ-bench's code on a separate copy of the data
    (as in the real run), unless `outputs` gives one ({call index: text})."""
    db = S.load_db(domain)
    msgs = [{"role": "system", "content": tau_copy.policy_text(domain)}, {"role": "user", "content": "hi"}]
    for i, (name, args) in enumerate(calls):
        out = S.run_tool(domain, db, name, copy.deepcopy(args))
        if outputs and i in outputs:
            out = outputs[i]
        msgs.append({"role": "assistant", "content": None, "tool_calls": [
            {"id": f"call_{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]})
        msgs.append({"role": "tool", "tool_call_id": f"call_{i}", "name": name, "content": out})
    return msgs


def _find_key(obj, key):
    """The value of `key` anywhere in a nested dict, or None."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            found = _find_key(v, key)
            if found is not None:
                return found
    return None


class RetailFacts:
    """Facts of the retail data files used by the tests."""
    db = None

    @classmethod
    def get(cls):
        if cls.db is None:
            cls.db = S.load_db("retail")
        return cls.db

    @classmethod
    def order(cls, status: str) -> str:
        return next(oid for oid, o in cls.get()["orders"].items() if o["status"] == status)


class TestToolTable(unittest.TestCase):
    def test_every_tool_is_in_the_table(self):
        table = S.tool_table()["domains"]
        for d in paths.DOMAINS:
            self.assertEqual(set(tau_copy.tools(d)), set(table[d]["tools"]), d)

    def test_every_kind_in_the_table_is_known(self):
        table = S.tool_table()["domains"]
        for d in paths.DOMAINS:
            for t, spec in table[d]["tools"].items():
                if spec.get("kind"):
                    self.assertIn(spec["kind"], table[d]["kinds"], f"{d}/{t}")


class TestDatabaseCopy(unittest.TestCase):
    def test_cancel_changes_the_copy(self):
        oid = RetailFacts.order("pending")
        st = S.build_state(_conv("retail", [("get_order_details", {"order_id": oid}),
                                            ("cancel_pending_order", {"order_id": oid, "reason": "no longer needed"})]))
        self.assertEqual(st.db_get("order", oid)["status"], "cancelled")
        self.assertEqual(st.db_get("order", oid)["cancel_reason"], "no longer needed")
        ev = st.events[-1]
        self.assertTrue(ev["ok"])
        self.assertTrue(ev["changes_db"])
        self.assertTrue(ev["match"])
        self.assertEqual(S.load_db("retail")["orders"][oid]["status"], "pending")   # the files are not changed

    def test_failed_call_is_logged_as_failed_and_changes_nothing(self):
        oid = RetailFacts.order("pending")
        done = RetailFacts.order("delivered")
        st = S.build_state(_conv("retail", [("cancel_pending_order", {"order_id": oid, "reason": "too expensive"}),
                                            ("cancel_pending_order", {"order_id": done, "reason": "no longer needed"}),
                                            ("get_order_details", {"order_id": "#W0"})]))
        self.assertEqual([e["ok"] for e in st.events], [False, False, False])
        self.assertEqual([e["output"] for e in st.events],
                         ["Error: invalid reason", "Error: non-pending order cannot be cancelled",
                          "Error: order not found"])
        self.assertEqual(json.dumps(st.db), json.dumps(S.load_db("retail")))
        self.assertEqual(st.shown, {})

    def test_exception_becomes_error_like_env_step(self):
        st = S.build_state(_conv("retail", [("get_order_details", {})]))
        self.assertFalse(st.events[0]["ok"])
        self.assertTrue(st.events[0]["output"].startswith("Error: "))

    def test_unknown_tool(self):
        st = S.build_state(_conv("retail", [("get_order_details", {"order_id": RetailFacts.order("pending")}),
                                            ("delete_everything", {})]))
        self.assertEqual(st.events[1]["output"], "Unknown action delete_everything")
        self.assertFalse(st.events[1]["ok"])

    def test_each_conversation_starts_from_a_fresh_copy(self):
        oid = RetailFacts.order("pending")
        first = S.build_state(_conv("retail", [("cancel_pending_order",
                                                {"order_id": oid, "reason": "ordered by mistake"})]))
        second = S.build_state(_conv("retail", [("get_order_details", {"order_id": oid})]))
        self.assertEqual(first.db_get("order", oid)["status"], "cancelled")
        self.assertEqual(second.db_get("order", oid)["status"], "pending")
        self.assertEqual(second.shown_get("order", oid)["status"], "pending")
        self.assertIsNot(first.db, second.db)
        self.assertEqual(len(second.events), 1)

    def test_load_db_gives_separate_copies(self):
        a, b = S.load_db("airline"), S.load_db("airline")
        rid = next(iter(a["reservations"]))
        a["reservations"][rid]["status"] = "changed"
        self.assertNotIn("status", b["reservations"][rid])
        self.assertNotIn("status", S.load_db("airline")["reservations"][rid])

    def test_pending_action_is_not_replayed(self):
        oid = RetailFacts.order("pending")
        rec = {"action": "cancel_pending_order", "kwargs": {"order_id": oid, "reason": "no longer needed"},
               "kind": "tool_call"}
        st = S.build_state(_conv("retail", [("get_order_details", {"order_id": oid})]), rec)
        self.assertEqual(st.db_get("order", oid)["status"], "pending")
        self.assertEqual(st.pending, {"tool": "cancel_pending_order", "args": rec["kwargs"], "kind": "tool_call"})


class TestShownSet(unittest.TestCase):
    def test_shown_set_keeps_the_newest_version(self):
        oid = RetailFacts.order("pending")
        st = S.build_state(_conv("retail", [("get_order_details", {"order_id": oid}),
                                            ("cancel_pending_order", {"order_id": oid, "reason": "no longer needed"})]))
        self.assertEqual(json.loads(st.events[0]["output"])["status"], "pending")
        self.assertEqual(st.shown_get("order", oid)["status"], "cancelled")
        self.assertEqual(st.shown_meta["order"][oid]["event"], 1)
        self.assertEqual(len(st.shown_all("order")), 1)

    def test_not_shown_gives_none(self):
        oid = RetailFacts.order("pending")
        st = S.build_state(_conv("retail", [("find_user_id_by_email", {"email": "nobody@example.com"})]))
        self.assertIsNone(st.shown_get("order", oid))
        self.assertIsNotNone(st.db_get("order", oid))
        self.assertEqual(st.shown_all("order"), [])

    def test_shown_version_is_what_was_shown(self):
        """If the saved output differs from the database (a mismatch), the shown set holds the saved output."""
        oid = RetailFacts.order("pending")
        fake = dict(RetailFacts.get()["orders"][oid], status="delivered")
        st = S.build_state(_conv("retail", [("get_order_details", {"order_id": oid})], {0: json.dumps(fake)}))
        self.assertEqual(st.shown_get("order", oid)["status"], "delivered")
        self.assertEqual(st.db_get("order", oid)["status"], "pending")
        self.assertEqual(len(st.mismatches), 1)
        self.assertFalse(st.events[0]["match"])
        with self.assertRaises(S.ReplayMismatch):
            S.build_state(_conv("retail", [("get_order_details", {"order_id": oid})], {0: json.dumps(fake)}),
                          strict=True)

    def test_list_output_adds_every_flight(self):
        db = S.load_db("airline")
        # a route and date with at least 2 available direct flights (a fact of flights.json)
        groups = {}
        for f in db["flights"].values():
            for date, day in f["dates"].items():
                if day["status"] == "available":
                    groups.setdefault((f["origin"], f["destination"], date), []).append(f["flight_number"])
        (orig, dest, date), numbers = next((k, v) for k, v in sorted(groups.items()) if len(v) >= 2)
        st = S.build_state(_conv("airline", [("search_direct_flight",
                                               {"origin": orig, "destination": dest, "date": date})]))
        self.assertEqual(sorted(f["flight_number"] for f in st.shown_all("flight")), sorted(numbers))
        for n in numbers:
            shown = st.shown_get("flight", n)
            self.assertEqual(shown["dates"][date]["status"], "available")
            self.assertEqual(shown["dates"][date]["prices"], db["flights"][n]["dates"][date]["prices"])
            self.assertEqual(list(shown["dates"]), [date])

    def test_flight_dates_are_merged(self):
        db = S.load_db("airline")
        f = next(f for f in db["flights"].values()
                 if sum(d["status"] == "available" for d in f["dates"].values()) >= 2)
        d1, d2 = [d for d, x in f["dates"].items() if x["status"] == "available"][:2]
        st = S.build_state(_conv("airline", [
            ("search_direct_flight", {"origin": f["origin"], "destination": f["destination"], "date": d1}),
            ("search_direct_flight", {"origin": f["origin"], "destination": f["destination"], "date": d2})]))
        shown = st.shown_get("flight", f["flight_number"])
        self.assertEqual(sorted(shown["dates"]), sorted([d1, d2]))
        self.assertEqual(st.shown_meta["flight"][f["flight_number"]]["dates"], {d1: 0, d2: 1})

    def test_onestop_output_adds_both_legs(self):
        st = None
        db = S.load_db("airline")
        # find a one-stop search with a result: try routes from the data until one gives a non-empty list
        for f1 in db["flights"].values():
            for date in sorted(f1["dates"]):
                for f2 in db["flights"].values():
                    if f2["origin"] == f1["destination"] and f2["destination"] != f1["origin"]:
                        out = S.run_tool("airline", db, "search_onestop_flight",
                                         {"origin": f1["origin"], "destination": f2["destination"], "date": date})
                        if out.startswith("[[") and "Error" not in out:
                            st = S.build_state(_conv("airline", [("search_onestop_flight", {
                                "origin": f1["origin"], "destination": f2["destination"], "date": date})]))
                            break
                if st:
                    break
            if st:
                break
        self.assertIsNotNone(st)
        pairs = json.loads(st.events[0]["output"])
        for leg in (x for p in pairs for x in p):
            self.assertIn(leg["date"], st.shown_get("flight", leg["flight_number"])["dates"])

    def test_product_list_adds_every_product_type(self):
        st = S.build_state(_conv("retail", [("list_all_product_types", {})]))
        self.assertEqual(len(st.shown_all("product_type")), len(RetailFacts.get()["products"]))
        self.assertIsNone(st.shown_get("product", next(iter(RetailFacts.get()["products"]))))

    def test_nested_objects_payment_methods_and_variants(self):
        db = RetailFacts.get()
        uid = next(iter(db["users"]))
        pid = next(iter(db["products"]))
        st = S.build_state(_conv("retail", [("get_user_details", {"user_id": uid}),
                                            ("get_product_details", {"product_id": pid})]))
        self.assertEqual(st.shown_get("user", uid), db["users"][uid])
        for pm_id, pm in db["users"][uid]["payment_methods"].items():
            self.assertEqual(st.shown_get("payment_method", pm_id), dict(pm, user_id=uid))
            self.assertEqual(st.db_get("payment_method", pm_id), dict(pm, user_id=uid))
        for item_id, v in db["products"][pid]["variants"].items():
            self.assertEqual(st.shown_get("variant", item_id), dict(v, product_id=pid))
            self.assertEqual(st.db_get("variant", item_id), dict(v, product_id=pid))

    def test_text_outputs_add_no_objects(self):
        db = RetailFacts.get()
        uid, u = next(iter(db["users"].items()))
        st = S.build_state(_conv("retail", [("find_user_id_by_email", {"email": u["email"]}),
                                            ("calculate", {"expression": "2 + 2"}),
                                            ("think", {"thought": "x"})]))
        self.assertEqual([e["output"] for e in st.events], [uid, "4.0", ""])
        self.assertTrue(all(e["ok"] for e in st.events))
        self.assertEqual(st.shown, {})
        self.assertEqual(st.parse_problems, [])


class TestEvents(unittest.TestCase):
    def test_event_fields_and_filter(self):
        db = RetailFacts.get()
        uid, u = next(iter(db["users"].items()))
        st = S.build_state(_conv("retail", [("find_user_id_by_email", {"email": "nobody@example.com"}),
                                            ("find_user_id_by_email", {"email": u["email"]}),
                                            ("get_user_details", {"user_id": uid})]))
        self.assertEqual([e["step"] for e in st.events], [0, 1, 2])
        self.assertEqual(len(st.events_where(tool="find_user_id_by_email")), 2)
        self.assertEqual(len(st.events_where(tool="find_user_id_by_email", ok=True)), 1)
        self.assertEqual(st.events_where(tool="find_user_id_by_email", ok=False)[0]["output"], "Error: user not found")
        self.assertEqual(len(st.events_where(tool=["find_user_id_by_email", "get_user_details"], ok=True)), 2)
        self.assertEqual(st.events[2]["args"], {"user_id": uid})

    def test_reply_messages_count_as_steps_but_not_events(self):
        msgs = _conv("retail", [("think", {"thought": "a"})])
        msgs += [{"role": "assistant", "content": "Hello"}, {"role": "user", "content": "bye"}]
        msgs += _conv("retail", [("think", {"thought": "b"})])[2:]
        msgs[-2]["tool_calls"][0]["id"] = msgs[-1]["tool_call_id"] = "call_x"
        st = S.build_state(msgs)
        self.assertEqual([e["step"] for e in st.events], [0, 2])
        self.assertEqual(st.n_steps, 3)

    def test_arguments_are_kept_as_sent(self):
        """book_reservation stores its payment_methods list in the database; a later cancel appends to it. The
        event's args must still be the arguments as sent."""
        db = S.load_db("airline")
        uid, user = next((k, u) for k, u in db["users"].items()
                         if any(p["source"] == "credit_card" for p in u["payment_methods"].values()))
        card = next(p for p, m in user["payment_methods"].items() if m["source"] == "credit_card")
        fn, f = next((n, f) for n, f in db["flights"].items()
                     if any(d["status"] == "available" for d in f["dates"].values()))
        date = next(d for d, x in f["dates"].items() if x["status"] == "available")
        price = f["dates"][date]["prices"]["economy"]
        book = {"user_id": uid, "origin": f["origin"], "destination": f["destination"], "flight_type": "one_way",
                "cabin": "economy", "flights": [{"flight_number": fn, "date": date}],
                "passengers": [{"first_name": "A", "last_name": "B", "dob": "1990-01-01"}],
                "payment_methods": [{"payment_id": card, "amount": price}], "total_baggages": 0,
                "nonfree_baggages": 0, "insurance": "no"}
        st = S.build_state(_conv("airline", [("book_reservation", book),
                                             ("cancel_reservation", {"reservation_id": "HATHAT"})]))
        self.assertTrue(st.events[0]["ok"], st.events[0]["output"])
        self.assertEqual(st.events[0]["args"]["payment_methods"], [{"payment_id": card, "amount": price}])
        self.assertEqual(len(st.db_get("reservation", "HATHAT")["payment_history"]), 2)
        self.assertEqual(st.db_get("reservation", "HATHAT")["status"], "cancelled")
        self.assertIn("HATHAT", st.db_get("user", uid)["reservations"])
        self.assertTrue(all(e["match"] for e in st.events))

    def test_tool_output_without_call_is_a_problem(self):
        msgs = _conv("retail", [("think", {"thought": "a"})])
        msgs.append({"role": "tool", "tool_call_id": "nope", "name": "think", "content": ""})
        st = S.build_state(msgs)
        self.assertEqual(len(st.problems), 1)
        self.assertEqual(len(st.events), 1)


class TestTodayAndDomain(unittest.TestCase):
    def test_today_from_the_policy(self):
        st = S.build_state(_conv("airline", []))
        self.assertEqual(st.today, datetime.datetime(2024, 5, 15, 15, 0, 0))
        self.assertEqual(st.today_text, "2024-05-15 15:00:00 EST")
        st = S.build_state(_conv("retail", []))
        self.assertIsNone(st.today)

    def test_parse_date(self):
        self.assertEqual(S.parse_date("2024-05-01"), datetime.datetime(2024, 5, 1))
        self.assertEqual(S.parse_date("2024-05-02T03:10:19"), datetime.datetime(2024, 5, 2, 3, 10, 19))
        self.assertEqual(S.parse_date("2024-05-15 15:00:00"), datetime.datetime(2024, 5, 15, 15))
        self.assertIsNone(S.parse_date("next week"))
        self.assertIsNone(S.parse_date(None))

    def test_domain_from_the_system_message_or_the_tools(self):
        self.assertEqual(S.infer_domain(_conv("airline", [])), "airline")
        msgs = _conv("retail", [("get_order_details", {"order_id": RetailFacts.order("pending")})])
        msgs[0] = {"role": "system", "content": "another policy"}
        self.assertEqual(S.infer_domain(msgs), "retail")
        with self.assertRaises(ValueError):
            S.infer_domain([{"role": "system", "content": "x"}])

    def test_walk_gives_the_same_states_as_build_state(self):
        oid = RetailFacts.order("pending")
        msgs = _conv("retail", [("get_order_details", {"order_id": oid}),
                                ("cancel_pending_order", {"order_id": oid, "reason": "no longer needed"}),
                                ("get_order_details", {"order_id": oid})])
        stops = [2, 4, 6, 8]
        for n, st in S.walk(msgs, stops=stops):
            ref = S.build_state(msgs[:n])
            self.assertEqual(len(st.events), len(ref.events))
            self.assertEqual(json.dumps(st.shown, sort_keys=True), json.dumps(ref.shown, sort_keys=True))
            self.assertEqual(json.dumps(st.db), json.dumps(ref.db))


class TestLoader(unittest.TestCase):
    def test_no_heavy_packages_and_no_stub_left(self):
        tau_copy.tools("retail")
        tau_copy.tools("airline")
        self.assertNotIn("litellm", sys.modules)
        self.assertNotIn("pydantic", sys.modules)
        mod = sys.modules.get("tau_bench")
        self.assertTrue(mod is None or getattr(mod, "__file__", None) is not None)   # no empty stub left behind

    def test_tool_schemas_match_the_rule_set_manifest(self):
        """The tool schemas loaded from the copy are the ones the rule sets were built for (manifest tools_sha256)."""
        import hashlib
        for d in paths.DOMAINS:
            with open(os.path.join(paths.RULES_DIR, d, "manifest.json"), encoding="utf-8") as f:
                manifest = json.load(f)
            want = _find_key(manifest, "tools_sha256")
            got = hashlib.sha256(json.dumps(tau_copy.tools_info(d), sort_keys=True).encode()).hexdigest()
            self.assertEqual(got, want, d)


if __name__ == "__main__":
    unittest.main()
