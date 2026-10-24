"""Tracker v3, part 7: the message view, the value matching, the helpers and the screens (state_tracker/v3/
message_view.py). Tiny conversations are built with τ-bench's own tool outputs (state.run_tool on a fresh database
copy), so the state replays them exactly. No LLM call, no network.

Run from predicate_correctness/:  python3 -B -m unittest tests.test_v3_message_view -v
"""
from __future__ import annotations

import copy
import json
import sys
import unittest

sys.dont_write_bytecode = True

from state_tracker import state as S                     # noqa: E402
from state_tracker.v3 import message_view as MV          # noqa: E402

OLIVIA = "olivia_ito_3591"            # retail: gift_card_7794233 (balance 56), paypal_8049766, visa 9182
OLIVIA_EMAIL = "olivia.ito5204@example.com"
MIA = "mia_moore_8366"                # retail: another user
ORDER = "#W5442520"                   # Olivia's pending order


def build(domain, steps, pending=None):
    """(history, state, view) of a tiny conversation. steps: ("user", text) | ("agent", text) |
    ("call", tool, args); a call's output comes from τ-bench's own tool code."""
    db = S.load_db(domain)
    hist = [{"role": "system", "content": "policy"}]
    for i, s in enumerate(steps):
        if s[0] == "user":
            hist.append({"role": "user", "content": s[1]})
        elif s[0] == "agent":
            hist.append({"role": "assistant", "content": s[1], "tool_calls": None})
        else:
            tool, args = s[1], s[2]
            out = S.run_tool(domain, db, tool, copy.deepcopy(args))
            cid = f"call_{i}"
            hist.append({"role": "assistant", "content": None, "tool_calls": [
                {"id": cid, "type": "function", "function": {"name": tool, "arguments": json.dumps(args)}}]})
            hist.append({"role": "tool", "tool_call_id": cid, "name": tool, "content": out})
    st = S.build_state(hist, pending, domain=domain)
    return hist, st, MV.build_view(hist, pending, st, domain)


class Ctx:
    def __init__(self, st, view, args=None):
        self.state, self.view = st, view
        self.args = args if args is not None else (view.pending_args or {})
        self.domain = st.domain if st is not None else view.domain
        self.notes = []

    def need_view(self):
        return self.view

    def arg(self, k):
        from state_tracker.v3 import facts_format_v3 as F
        if k not in self.args:
            raise F.MissingArgument(k)
        return self.args[k]

    def note(self, x):
        self.notes.append(x)


def ctx_of(domain, steps, pending=None):
    hist, st, view = build(domain, steps, pending)
    return Ctx(st, view)


class TestNormalize(unittest.TestCase):
    def test_accents_and_case(self):
        self.assertEqual(MV.normalize("José MÜLLER Ñandú"), "jose muller nandu")

    def test_curly_quotes_and_dashes(self):
        self.assertEqual(MV.normalize("I don’t “want” it — thanks"), "i don't \"want\" it - thanks")

    def test_markdown_removed_ids_kept(self):
        t = "### Order\n> **#W5442520** has `gift_card_7794233` and [link](http://x.y)\n---\n__done__"
        self.assertEqual(MV.normalize(t), "order #w5442520 has gift_card_7794233 and link done")

    def test_spaces_collapsed(self):
        self.assertEqual(MV.normalize("  a \n\n b\t c "), "a b c")


class TestMatching(unittest.TestCase):
    def test_whole_tokens_only(self):
        self.assertTrue(MV.text_has_value("order w123 is here", "W123"))
        self.assertFalse(MV.text_has_value("order w1234 is here", "W123"))
        self.assertFalse(MV.text_has_value("id mia_li_36689", "mia_li_3668"))
        self.assertTrue(MV.text_has_value("id mia_li_3668.", "mia_li_3668"))

    def test_order_id_with_and_without_hash(self):
        self.assertTrue(MV.text_has_value(MV.normalize("my order is W5442520"), "#W5442520"))
        self.assertTrue(MV.text_has_value(MV.normalize("order #W5442520 please"), "W5442520"))
        self.assertTrue(MV.text_has_value(MV.normalize("order#W5442520"), "#W5442520"))

    def test_zip_plus_four(self):
        self.assertTrue(MV.text_has_value(MV.normalize("ZIP 80218-1234"), "80218"))
        self.assertFalse(MV.text_has_value(MV.normalize("ZIP 802181"), "80218"))

    def test_six_date_forms(self):
        for typed in ("1990-04-05", "4/5/1990", "04/05/1990", "05/04/1990", "April 5, 1990", "5 April 1990",
                      "Apr. 5th, 1990", "5th of April 1990", "04-05-1990", "4/5/90"):
            self.assertTrue(MV.text_has_value(MV.normalize(f"born {typed} ok"), "1990-04-05"), typed)

    def test_wrong_date_not_matched(self):
        self.assertFalse(MV.text_has_value(MV.normalize("born April 5, 1990"), "1990-04-06"))
        self.assertFalse(MV.text_has_value(MV.normalize("born April 5, 1991"), "1990-04-05"))

    def test_multiword_name_and_accents(self):
        self.assertTrue(MV.text_has_value(MV.normalize("I am Mary   Ann Lee"), "Mary Ann"))
        self.assertTrue(MV.text_has_value(MV.normalize("I am Jose"), "José"))

    def test_empty_and_none_values(self):
        self.assertFalse(MV.text_has_value("anything", ""))
        self.assertFalse(MV.text_has_value("anything", None))


class TestView(unittest.TestCase):
    def test_view_equals_history(self):
        hist, st, view = build("retail", [("user", "Hi, my email is " + OLIVIA_EMAIL),
                                          ("call", "find_user_id_by_email", {"email": OLIVIA_EMAIL}),
                                          ("agent", "Found you."), ("user", "thanks")],
                               {"tool": "respond", "args": {"content": "bye"}})
        self.assertEqual([e.role for e in view.entries], ["user", "tool", "agent", "user"])
        self.assertEqual(view.entries[1].tool, "find_user_id_by_email")
        self.assertEqual(view.entries[1].args, {"email": OLIVIA_EMAIL})
        self.assertEqual(view.entries[1].text, OLIVIA)
        self.assertTrue(view.entries[1].ok)
        rec = MV.reconstruct(view)
        self.assertEqual([m["content"] for m in rec], [hist[1]["content"], OLIVIA, "Found you.", "thanks"])
        self.assertEqual(view.pending_ref, 4)
        self.assertEqual(view.text(view.pending_ref), "bye")
        self.assertEqual(view.role(view.pending_ref), "agent")
        self.assertEqual(view.problems, [])

    def test_never_cut(self):
        long = "x " * 20000 + "the end W5442520"
        _, _, view = build("retail", [("user", long)])
        self.assertEqual(view.entries[0].text, long)
        self.assertTrue(MV.text_has_value(view.norm(0), ORDER))

    def test_prefix_view(self):
        hist, st, view = build("retail", [("user", "a"), ("agent", "b"), ("user", "c")])
        p = view.prefix(3)
        self.assertEqual([e.text for e in p.entries], ["a", "b"])

    def test_failed_call_not_ok(self):
        _, _, view = build("retail", [("call", "find_user_id_by_email", {"email": "nobody@example.com"})])
        self.assertFalse(view.entries[0].ok)
        self.assertEqual(view.data_tool_refs(), [])


class TestHelpers(unittest.TestCase):
    def test_id_typed_only_by_the_agent(self):
        c = ctx_of("retail", [("user", "I need help with an order"), ("agent", "Is it order #W5442520?")])
        self.assertFalse(MV.user_typed(c, ORDER))
        self.assertTrue(MV.agent_wrote(c, ORDER))

    def test_user_echoes_the_agent(self):
        c = ctx_of("retail", [("agent", "Is your email " + OLIVIA_EMAIL + "?"), ("user", OLIVIA_EMAIL + ", yes")])
        self.assertTrue(MV.user_typed(c, OLIVIA_EMAIL))

    def test_obtained_from_tool_output_not_call_args(self):
        c = ctx_of("airline", [("user", "my reservation is 4WQ150"),
                               ("call", "get_reservation_details", {"reservation_id": "4WQ150"})])
        self.assertTrue(MV.obtained(c, "chen_jackson_3290"))           # the user_id field of the output
        c2 = ctx_of("airline", [("user", "hi"), ("call", "get_user_details", {"user_id": "chen_jackson_3290"})])
        self.assertFalse(MV.obtained(c2, "chen_jackson_3290"))         # only in the call's arguments

    def test_reply_is_no(self):
        c = ctx_of("retail", [("user", "x")])
        for t in ("No, wait.", "no", "Wait, also add the blue shirt", "Don't do it yet", "not yet please",
                  "Hold on a second", "nope"):
            self.assertTrue(MV.reply_is_no(c, t), t)
        for t in ("Yes", "No problem, go ahead", "No, that's fine, please proceed", "ok", "Sure, no rush",
                  "I think so", "No worries", "No other items. Please use gift card 9450778.", "No, that's all",
                  "No more changes", "No, nothing else"):
            self.assertFalse(MV.reply_is_no(c, t), t)

    def test_reply_after_and_no_after(self):
        c = ctx_of("retail", [("agent", "list #W5442520"), ("user", "yes"), ("agent", "more?"), ("user", "No, wait")])
        self.assertEqual(MV.reply_after(c, 0), 1)
        self.assertTrue(MV.no_after(c, 1))
        self.assertIsNone(MV.reply_after(c, 3))

    def test_me_first_login_and_no_switch(self):
        c = ctx_of("retail", [("user", OLIVIA_EMAIL), ("call", "find_user_id_by_email", {"email": OLIVIA_EMAIL}),
                              ("user", "now my friend mia.moore8091@example.com"),
                              ("call", "find_user_id_by_email", {"email": "mia.moore8091@example.com"})])
        self.assertEqual(MV.me(c), OLIVIA)

    def test_me_failed_login_is_not_me(self):
        c = ctx_of("retail", [("call", "find_user_id_by_email", {"email": "nobody@example.com"}),
                              ("call", "find_user_id_by_email", {"email": OLIVIA_EMAIL})])
        self.assertEqual(MV.me(c), OLIVIA)

    def test_me_airline_typed_and_existing(self):
        c = ctx_of("airline", [("user", "I am chen_jackson_3299, sorry, chen_jackson_3290"),
                               ("call", "get_user_details", {"user_id": "mia_li_3668"})])
        self.assertEqual(MV.me(c), "chen_jackson_3290")
        c2 = ctx_of("airline", [("user", "hi"), ("call", "get_user_details", {"user_id": "mia_li_3668"})])
        self.assertIsNone(MV.me(c2))                                    # never the call's own arguments

    def test_messages_naming_newest_first_and_limit(self):
        c = ctx_of("retail", [("agent", "a #W5442520"), ("user", "u"), ("agent", "b W5442520"), ("user", "u"),
                              ("agent", "c")])
        self.assertEqual(MV.messages_naming(c, ORDER), [2, 0])
        self.assertEqual(MV.messages_naming(c, ORDER, "agent", 1), [2])

    def test_confirm_pairs_and_strict_no(self):
        c = ctx_of("retail", [("agent", "Cancel #W5442520 (no longer needed)?"), ("user", "Yes please")],
                   {"tool": "cancel_pending_order", "args": {"order_id": ORDER, "reason": "no longer needed"}})
        self.assertEqual(MV.confirm_pairs(c, MV.call_key_ids(c)), [[0, 1]])
        c2 = ctx_of("retail", [("agent", "Cancel #W5442520?"), ("user", "Yes"), ("user", "No, wait")],
                    {"tool": "cancel_pending_order", "args": {"order_id": ORDER, "reason": "no longer needed"}})
        self.assertEqual(MV.confirm_pairs(c2, [ORDER]), [])

    def test_reminder_candidates_after_first_mention(self):
        c = ctx_of("retail", [("agent", "Please list all items."), ("user", "order W5442520"),
                              ("agent", "Are these all the items to modify?"), ("user", "yes"), ("agent", "ok")])
        self.assertEqual(MV.reminder_candidates(c, ORDER), [2])

    def test_listing_without_the_order_id_found_by_call_details(self):
        pend = {"tool": "modify_pending_order_items", "args": {
            "order_id": ORDER, "item_ids": ["3330317167"], "new_item_ids": ["2193628750"],
            "payment_method_id": "paypal_8049766"}}
        c = ctx_of("retail", [("user", "order #W5442520"), ("agent", "Which item?"),
                              ("user", "the mouse"),
                              ("agent", "I will change the Gaming Mouse to the wireless one, paid by PayPal. Confirm?"),
                              ("user", "yes")], pend)
        self.assertEqual(MV.listing_candidates(c, MV.call_key_ids(c)), [])      # the agent never wrote the order id
        self.assertEqual(MV.listing_candidates(c, MV.call_details(c)), [3])

    def test_payment_gift_card_named_by_number_in_id(self):
        for typed in ("use gift card 7794233", "the gift card ending in 4233", "gift_card_7794233 please"):
            c = ctx_of("retail", [("user", typed)])
            self.assertTrue(MV.payment_named_exactly(c, "gift_card_7794233", OLIVIA), typed)

    def test_payment_card_last_four_and_kind_words(self):
        c = ctx_of("retail", [("user", "charge my visa ending 9182")])
        self.assertTrue(MV.payment_named_exactly(c, "credit_card_9753331", OLIVIA))
        c2 = ctx_of("retail", [("user", "use my credit card")])                 # a kind word only
        self.assertFalse(MV.payment_named_exactly(c2, "credit_card_9753331", OLIVIA))

    def test_payment_negation_and_latest_message(self):
        c = ctx_of("retail", [("user", "not the 9182 card, please")])
        self.assertFalse(MV.payment_named_exactly(c, "credit_card_9753331", OLIVIA))
        c2 = ctx_of("retail", [("user", "use card 9182"), ("agent", "ok"), ("user", "actually use PayPal")])
        self.assertFalse(MV.payment_named_exactly(c2, "credit_card_9753331", OLIVIA))

    def test_payment_confirm_pairs(self):
        c = ctx_of("retail", [("agent", "The difference goes to your PayPal. OK?"), ("user", "Yes")])
        self.assertEqual(MV.payment_confirm_pairs(c, "paypal_8049766", OLIVIA), [[0, 1]])
        c2 = ctx_of("retail", [("agent", "The difference goes to your PayPal. OK?"), ("user", "Yes"),
                               ("user", "hmm, rather the gift card")])
        self.assertEqual(MV.payment_confirm_pairs(c2, "paypal_8049766", OLIVIA), [])

    def test_payment_other_method_named_negatively(self):
        c = ctx_of("retail", [("user", "Apply the difference to my gift card ending in 7794233, not the Visa.")])
        self.assertTrue(MV.payment_named_exactly(c, "gift_card_7794233", OLIVIA))
        c2 = ctx_of("retail", [("user", "Apply it to gift card 7794233 and the rest to my Visa.")])
        self.assertFalse(MV.payment_named_exactly(c2, "gift_card_7794233", OLIVIA))

    def test_payment_dont_have_negation(self):
        """RC11 m3 (stage_a.nano.tgr_frozen|retail/333/0|10): "I don't have a gift card or credit card ID" names
        neither method; the PayPal id typed before it is the choice."""
        t = "Yes, I confirm the exchange using paypal_8049766. I don't have a gift card or credit card ID to provide."
        c = ctx_of("retail", [("user", t)])
        self.assertTrue(MV.payment_named_exactly(c, "paypal_8049766", OLIVIA))
        ex, lo, neg = MV._methods_mentioned(MV.normalize(t), MV._user_methods(c, OLIVIA))
        self.assertEqual((ex, lo, neg), ({"paypal_8049766"}, {"paypal_8049766"},
                                         {"gift_card_7794233", "credit_card_9753331"}))
        for t2 in ("I do not have the gift card anymore. Charge my visa ending 9182.",
                   "We don't use PayPal or the gift card, charge the visa ending 9182."):
            self.assertTrue(MV.payment_named_exactly(ctx_of("retail", [("user", t2)]), "credit_card_9753331",
                                                     OLIVIA), t2)
        # "or" joins only to a negative mention: a positive list still names both
        c3 = ctx_of("retail", [("user", "Use the gift card 7794233 or the visa 9182, whichever works.")])
        self.assertFalse(MV.payment_named_exactly(c3, "gift_card_7794233", OLIVIA))

    def test_last_four_names_the_card_not_another_id_tail(self):
        """RC11 m3: a 4-digit number that is a card's last_four names that card only, even when another method's id
        number ends in it; the id tail still names a method when no card has that last_four."""
        def ctx(text):
            c = ctx_of("retail", [("user", text)])
            c.state.db["users"][OLIVIA]["payment_methods"]["credit_card_1111111"] = {
                "source": "credit_card", "brand": "mastercard", "last_four": "4233", "id": "credit_card_1111111"}
            return c
        c = ctx("Please charge the card ending in 4233.")
        self.assertTrue(MV.payment_named_exactly(c, "credit_card_1111111", OLIVIA))
        self.assertFalse(MV.payment_named_exactly(c, "gift_card_7794233", OLIVIA))
        self.assertTrue(MV.payment_named_exactly(ctx("use gift card 7794233"), "gift_card_7794233", OLIVIA))
        c2 = ctx_of("retail", [("user", "the gift card ending in 4233")])          # no card has last_four 4233
        self.assertTrue(MV.payment_named_exactly(c2, "gift_card_7794233", OLIVIA))

    def test_two_methods_for_two_actions_is_still_not_exact(self):
        """RC11's stage_a.luna.tgr_tracker|retail/424/0|7 shape: one message names the card for the payment change
        and the gift card for the price difference of another change. Code cannot tell which method is for which
        action, so part a stays false (a known limit, not changed by the m3 fix: the cause is not the number form)."""
        c = ctx_of("retail", [("user", "Yes, change the order's payment to the card ending in 9182. For the item "
                                       "change, charge the difference to the gift card ending in 4233 instead.")])
        self.assertFalse(MV.payment_named_exactly(c, "credit_card_9753331", OLIVIA))

    def test_only_card_named_as_my_card(self):
        c = ctx_of("retail", [("agent", "Shall I charge $2.55?"), ("user", "Yes, charge my card on file, not PayPal.")])
        self.assertEqual(MV.payment_confirm_pairs(c, "credit_card_2641784", MIA), [])          # Mia has two cards
        c2 = ctx_of("retail", [("agent", "Shall I charge $2.55?"), ("user", "Yes, charge my card on file, not PayPal.")])
        self.assertEqual(MV.payment_confirm_pairs(c2, "credit_card_8105988", "sofia_li_9219"), [])  # two credit cards
        c3 = ctx_of("retail", [("agent", "Shall I charge $2.55?"), ("user", "Yes, charge my card on file, not PayPal.")])
        self.assertEqual(MV.payment_confirm_pairs(c3, "credit_card_7815826", "noah_brown_6181"), [[0, 1]])  # one card
        self.assertEqual(MV.payment_confirm_pairs(c3, "paypal_5727330", "noah_brown_6181"), [])

    def test_payment_named_in_the_reply(self):
        c = ctx_of("retail", [("agent", "The kettle change refunds $5.56 to the original method. Yes?"),
                              ("user", "Yes, and refund the $5.56 to PayPal.")])
        self.assertEqual(MV.payment_confirm_pairs(c, "paypal_8049766", OLIVIA), [[0, 1]])
        self.assertFalse(MV.payment_named_exactly(c, "paypal_8049766", OLIVIA))     # a kind word: not exact

    def test_name_inside_a_typed_user_id(self):
        c = ctx_of("retail", [("user", "My name is daiki_johnson_9523, zip 80273")])
        self.assertTrue(MV.user_typed(c, "Daiki"))
        self.assertTrue(MV.user_typed(c, "Johnson"))
        self.assertFalse(MV.user_typed(c, "9523"))           # a number inside an id is not typed alone

    def test_payment_named_by_balance_when_unique(self):
        c = ctx_of("airline", [("agent", "You have gift cards of $245. Use it?"), ("user", "Yes, the $245 one")])
        self.assertEqual(MV.payment_confirm_pairs(c, "gift_card_3576581", "chen_jackson_3290"), [[0, 1]])

    def test_shown_forms(self):
        c = ctx_of("retail", [("user", "x")])
        f = MV.shown_forms(c, "credit_card_9753331")
        self.assertIn("9182", f)
        self.assertIn("credit card", f)
        self.assertIn("visa 9182", f)
        self.assertEqual(MV.shown_forms(c, "#W5442520"), ["#w5442520", "w5442520"])
        self.assertIn("basic economy", MV.shown_forms(c, "basic_economy"))


class TestScreens(unittest.TestCase):
    def test_screen_hits(self):
        self.assertTrue(MV.screen_text("health", "I have been feeling unwell since Monday"))
        self.assertTrue(MV.screen_text("health", "a blizzard is coming"))
        self.assertTrue(MV.screen_text("other_person", "Can you check my brother's order?"))
        self.assertTrue(MV.screen_text("other_person", "What did John's order ship with?"))
        self.assertTrue(MV.screen_text("offer", "As an apology we can give you 50 dollars"))
        self.assertTrue(MV.screen_text("offer", "I can issue a $100 travel voucher"))
        self.assertTrue(MV.screen_text("delay", "my flight is 5 hours late"))
        self.assertTrue(MV.screen_text("cancel", "the airline scrapped my flight"))
        self.assertTrue(MV.screen_text("compensation_request", "I think I deserve something for this"))

    def test_screen_misses_plain_text(self):
        self.assertFalse(MV.screen_text("health", "I want to change my seat"))
        self.assertFalse(MV.screen_text("offer", "Your booking is confirmed for May 20."))

    def test_screened_user_messages_newest_first(self):
        c = ctx_of("airline", [("user", "I am sick"), ("agent", "sorry"), ("user", "and there is a storm")])
        self.assertEqual(MV.screened_user_messages(c, "health"), [2, 0])

    def test_screens_removed_after_set3_always_hit(self):
        for name in ("cancel", "delay", "complaint"):
            self.assertTrue(MV.screen_text(name, "Hello, I would like a window seat."), name)
        c = ctx_of("retail", [("user", "hi")], {"tool": "respond", "args": {"content": "Your order shipped."}})
        self.assertTrue(MV.other_person_screen(c))                      # K5 asked on every reply
        self.assertFalse(MV.screen_text("health", "I would like a window seat."))   # kept screens still screen
        self.assertFalse(MV.screen_text("other_person", "I want a gaming mouse"))  # K4 keeps it

    def test_unknown_screen(self):
        with self.assertRaises(ValueError):
            MV.screen_text("nope", "x")


if __name__ == "__main__":
    unittest.main()
