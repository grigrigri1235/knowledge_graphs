"""Builds tests/fixtures_v4/questions_v4_fixture.json: a small v4 questions file for the v4 question tests only.

It is NOT the real questions_v4.json (the main chat builds that from overlays). Texts here are short made-up
stand-ins written from the predicate table's shapes; K4, K10 and K12 are copied unchanged from questions_v3.json
(system 1) so the tests can prove that unchanged questions keep v3's keys and prompts.

    cd predicate_correctness && ~/venvs/tau-bench/bin/python -B -m tests.fixtures_v4.build_questions_fixture_v4
"""
from __future__ import annotations

import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from state_tracker.v3 import questions as Q          # noqa: E402

OUT = os.path.join(HERE, "questions_v4_fixture.json")
SYSTEM_2_EXTRA = (" If the question names a default or defines a word, use it. With a no, \"missing\" says in a few "
                  "words what is missing; else it is empty.")


def _seal(q: dict) -> dict:
    q = {k: v for k, v in q.items() if k != "text_sha256"}
    q["text_sha256"] = Q.question_hash(q)
    return q


def build() -> dict:
    v3 = Q.load_questions()
    s1 = {"system": v3["system"], "schema": v3["schema"], "schema_name": v3["schema_name"],
          "system_sha256": v3["system_sha256"]}
    schema2 = copy.deepcopy(v3["schema"])
    schema2["properties"]["missing"] = {"type": "string"}
    schema2["required"] = ["answer", "quote", "missing"]
    s2 = {"system": v3["system"] + SYSTEM_2_EXTRA, "schema": schema2, "schema_name": "tiny_answer_v2"}
    s2["system_sha256"] = Q.system_hash(dict(s2, system_version=2))
    qs = {}
    for qid, mode in (("K4", "allow"), ("K10", "block"), ("K12", "block")):
        q = copy.deepcopy(v3["questions"][qid])
        q.update(system_version=1, on_unclear=mode,
                 second=_seal({"id": qid + "b", "version": 1,
                               "question": f"Second wording of {qid}: is it so in message A?"}))
        qs[qid] = _seal(q)
    user = {"label": "Message A, from the user", "name": "message", "type": "message", "who": "user"}
    qs["K1"] = _seal({
        "id": "K1", "version": 4, "system_version": 2, "on_unclear": "block",
        "facts": {"retail": ["user_explicitly_confirmed_pending_action"]},
        "inputs": [{"label": "Message A, from the agent", "name": "listing", "type": "message", "who": "agent"},
                   {"label": "Messages B, from the user (after message A, oldest first)", "name": "replies",
                    "type": "messages", "who": "user"},
                   {"from": "call", "label": "The action", "name": "action", "render": "action_line",
                    "type": "text"}],
        "question": "Do the user's messages B tell the agent to go ahead with what message A proposes (all of it, "
                    "or at least this action: {action})?",
        "quote_from": ["replies"],
        "second": {"version": 1, "question": "Has the user agreed that the agent should now carry out {action}?"},
        "few_shot": [
            {"inputs": {"listing": "I can cancel the pending order with the kettle. Shall I?",
                        "replies": ["That sounds right, please take care of it."]},
             "answer": "yes", "quote": "please take care of it"},
            {"inputs": {"listing": "I will exchange the jacket for size L. Go ahead?",
                        "replies": ["Could you use my credit card instead?"]},
             "answer": "no", "quote": "", "missing": "the user asked to change the card"}]})
    qs["K3"] = _seal({
        "id": "K3", "version": 2, "system_version": 2, "on_unclear": "block",
        "facts": {"retail": ["agent_reminded_user_to_include_all_items_for_exchange"]},
        "inputs": [{"label": "Message A, from the agent", "name": "message", "type": "message", "who": "agent"},
                   {"label": "The items", "name": "items_action", "type": "choice",
                    "values": ["exchanged", "modified"]},
                   {"label": "The verb", "name": "verb", "type": "choice", "values": ["exchange", "modify"],
                    "follows": {"input": "items_action", "map": {"exchanged": "exchange", "modified": "modify"}}}],
        "question": "Does message A ask the user to check that the list of items to be {items_action} is "
                    "complete? For example: 'Are these all the items you want to {verb}?'",
        "quote_from": ["message"],
        "second": {"version": 1, "question": "Does message A ask whether there are more items to {verb}?"},
        "few_shot": [{"inputs": {"message": "Is the desk lamp the only item you'd like to change?",
                                 "items_action": "modified", "verb": "modify"},
                      "answer": "yes", "quote": "Is the desk lamp the only item"},
                     {"inputs": {"message": "Please confirm you want me to exchange both items."},
                      "answer": "no", "quote": ""}]})
    qs["K8"] = _seal({
        "id": "K8", "version": 2, "system_version": 2, "on_unclear": "block",
        "facts": {"airline": ["user_complained_about_relevant_flight_situation"]}, "inputs": [dict(user)],
        "question": "Does message A complain about a problem with a flight of the user's trip, such as the flight "
                    "being delayed or cancelled?",
        "quote_from": ["message"],
        "second": {"version": 1, "question": "Is the user in message A unhappy that their flight was delayed or "
                                             "cancelled?"}})
    qs["K13"] = _seal({
        "id": "K13", "version": 3, "system_version": 2, "on_unclear": "allow",
        "facts": {"airline": ["request_cannot_be_handled_with_available_tools"],
                  "retail": ["request_cannot_be_handled_within_scope"]},
        "inputs": [dict(user), {"from": "domain", "label": "What the agent's tools can do", "name": "tools",
                                "type": "text"}],
        "question": "Does message A ask for something that the agent's tools listed below cannot do?",
        "quote_from": ["message"],
        "second": {"version": 1, "question": "Could none of the tools listed below do what message A asks for?"}})
    qs["K16"] = _seal({
        "id": "K16", "version": 2, "system_version": 2, "on_unclear": "allow",
        "facts": {"airline": ["request_cannot_be_handled_with_available_tools"]}, "inputs": [dict(user)],
        "question": "Does message A ask to cancel a reservation or a trip (all of it or a part of it)?",
        "quote_from": ["message"],
        "second": {"version": 1, "question": "Does the user in message A want a booking cancelled?"}})
    qs["K17"] = _seal({
        "id": "K17", "version": 1, "system_version": 2, "on_unclear": "block",
        "accepted_answers": ["added", "not_added", "not_said", "unclear"],
        "facts": {"airline": ["booking_insurance_decision_established_and_matched"]},
        "inputs": [{"label": "Message A, from the agent", "name": "agent_message", "optional": True,
                    "type": "message", "who": "agent"},
                   {"label": "Message B, from the user", "name": "user_message", "optional": True,
                    "type": "message", "who": "user"}],
        "question": "What do messages A and B say together about travel insurance for this booking?",
        "quote_from": ["agent_message", "user_message"],
        "second": {"version": 1, "question": "Is travel insurance part of this booking?"},
        "few_shot": [{"inputs": {"agent_message": "Would you like to add travel insurance for $30 per passenger?",
                                 "user_message": "Yes."}, "answer": "added", "quote": "Yes."}]})
    qs["K18"] = _seal({
        "id": "K18", "version": 1, "system_version": 2, "on_unclear": "block",
        "facts": {"retail": ["consequential_action_details_listed"]},
        "inputs": [{"label": "Message A", "name": "message", "type": "message", "who": "any"},
                   {"from": "call", "label": "The reason", "name": "reason", "type": "choice",
                    "values": ["no longer needed", "ordered by mistake"]},
                   {"label": "The meaning of the reason", "name": "gloss", "type": "choice",
                    "values": ["the user does not need or want the item any more",
                               "the order was placed by accident"],
                    "follows": {"input": "reason", "map": {
                        "no longer needed": "the user does not need or want the item any more",
                        "ordered by mistake": "the order was placed by accident"}}}],
        "question": "Does message A give this reason for cancelling the order: '{reason}' ({gloss})?",
        "quote_from": ["message"],
        "second": {"version": 1, "question": "Is the reason for cancelling in message A '{reason}' in meaning?"}})
    return {"_about": "TEST FIXTURE ONLY (tests/fixtures_v4): not the real questions_v4.json.",
            "domain_texts": copy.deepcopy(v3["domain_texts"]), "effort": v3["effort"], "model": v3["model"],
            "price": copy.deepcopy(v3["price"]), "schema_version": 2, "systems": {"1": s1, "2": s2},
            "questions": qs}


def main() -> int:
    doc = build()
    from state_tracker.v4 import questions_v4 as Q4
    problems = Q4.check_doc_v4(doc) + Q4.v3_identity_problems_v4(doc, Q.load_questions())
    if problems:
        print("\n".join(problems))
        return 1
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    print(f"wrote {OUT}: {len(doc['questions'])} questions")
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.exit(main())
