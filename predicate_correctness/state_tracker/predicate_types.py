"""Predicate types (Part 3): load and check output/predicate_types.json, and write the review table.

The types themselves are written by hand in output/predicate_types.json (domain -> predicate -> {type, reason}, plus
a '_review' key with the review status). The independent agent's verdicts are in output/p3_agent_review.json.
This module only reads them, checks them against the frozen rule sets, and renders output/predicate_types.md.

Run:  python3 -m state_tracker.predicate_types            (check only)
      python3 -m state_tracker.predicate_types --write-md (check, then write the table; refuses to overwrite)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "state_tracker"

from state_tracker.paths import DOMAINS, OUTPUT_DIR, rule_set_path

TYPES = ("argument", "database fact", "event", "conversation", "mixed")
CODE_TYPES = ("argument", "database fact", "event")          # set by code (Parts 4-5)
TYPES_JSON = os.path.join(OUTPUT_DIR, "predicate_types.json")
TYPES_MD = os.path.join(OUTPUT_DIR, "predicate_types.md")
AGENT_REVIEW_JSON = os.path.join(OUTPUT_DIR, "p3_agent_review.json")   # independent agent's verdicts (Part 3, subtask 2)
META_KEY = "_review"          # review status in predicate_types.json; not a domain


def load_types(path: str = TYPES_JSON) -> dict:
    """domain -> predicate -> {type, reason}. Keys that start with '_' (review status) are left out."""
    with open(path, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def load_meta(path: str = TYPES_JSON) -> dict:
    """The review status stored in predicate_types.json under '_review' ({} if none)."""
    with open(path, encoding="utf-8") as f:
        return json.load(f).get(META_KEY, {})


def load_agent_review(path: str = AGENT_REVIEW_JSON) -> dict:
    """The independent agent's review: {status, date, changes, details, airline: {pred: verdict}, retail: {...}}."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check_agent_review(review: dict, types: dict) -> list[str]:
    """Every typed predicate has a verdict, and every verdict is 'agree...' or 'change to <type>...'."""
    problems = []
    for domain in DOMAINS:
        got = review.get(domain, {})
        for name in types.get(domain, {}):
            v = got.get(name, "")
            if not (v.startswith("agree") or any(v.startswith(f"change to {t}") for t in TYPES)):
                problems.append(f"{domain}: {name} has no valid agent verdict ({v!r})")
        for name in got:
            if name not in types.get(domain, {}):
                problems.append(f"{domain}: verdict for unknown predicate {name}")
    return problems


def load_rule_set(domain: str) -> dict:
    with open(rule_set_path(domain), encoding="utf-8") as f:
        return json.load(f)


def is_code_type(t: str) -> bool:
    return t in CODE_TYPES


def check_types(types: dict) -> list[str]:
    """Return a list of problems (empty if every frozen predicate has exactly one valid type and a reason)."""
    problems = []
    if set(types) != set(DOMAINS):
        problems.append(f"domains {sorted(types)} != {sorted(DOMAINS)}")
    for domain in DOMAINS:
        preds = load_rule_set(domain)["predicates"]
        got = types.get(domain, {})
        for name in preds:
            if name not in got:
                problems.append(f"{domain}: {name} has no type")
        for name, entry in got.items():
            if name not in preds:
                problems.append(f"{domain}: {name} is not a frozen predicate")
                continue
            if set(entry) != {"type", "reason"}:
                problems.append(f"{domain}: {name} keys {sorted(entry)} != ['reason', 'type']")
            if entry.get("type") not in TYPES:
                problems.append(f"{domain}: {name} type {entry.get('type')!r} not in {TYPES}")
            if not str(entry.get("reason", "")).strip():
                problems.append(f"{domain}: {name} has no reason")
    return problems


def rule_tools(rule_set: dict) -> dict[str, list[str]]:
    """Predicate -> sorted tools whose rules use it (token match on the rule logic)."""
    out: dict[str, set] = {}
    for rule in rule_set["rules"]:
        tokens = set(rule["logic"].replace("(", " ").replace(")", " ").split())
        for name in rule_set["predicates"]:
            if name in tokens:
                out.setdefault(name, set()).add(rule["action"])
    return {k: sorted(v) for k, v in out.items()}


def type_counts(types: dict) -> dict[str, dict[str, int]]:
    counts = {}
    for domain in DOMAINS:
        c = {t: 0 for t in TYPES}
        for entry in types[domain].values():
            c[entry["type"]] += 1
        counts[domain] = c
    return counts


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def render_md(types: dict, review: dict | None = None) -> str:
    counts = type_counts(types)
    review = load_agent_review() if review is None else review
    if review:
        status = [
            f"Draft 2026-10-21. **{review['status']}** Type changes from the review: {review['changes']}",
            f"(details: `{review['details']}`).",
        ]
    else:
        status = ["Date 2026-10-21. Status: **draft**. Agent review: pending. Person review: pending."]
    lines = [
        "# Predicate types (Part 3)",
        "",
        *status,
        "",
        "Source: `output/predicate_types.json` (machine-readable). This table is written from it by",
        "`state_tracker/predicate_types.py --write-md`. The column \"agent review\" comes from",
        "`output/p3_agent_review.json`.",
        "",
        "## How the types were chosen",
        "- Input: the predicate's description and its declared sources in the frozen rule set, and what the τ-bench",
        "  tools return. The judge's values were not looked at.",
        "- Questions, in this order (`overview.md`, \"How we decide what is a predicate\"):",
        "  1. Does the value need the meaning of a user or agent message? Only that: **conversation**. That plus a",
        "     separate fact code can check: **mixed**.",
        "  2. Does it need objects from tool outputs or the database? **database fact**.",
        "  3. Does it need only which tool calls ran before, and whether they worked? **event**.",
        "  4. Does it need only the pending call's arguments? **argument**.",
        "- **Conversation or mixed.** A predicate is **mixed** only if its description holds a separate fact that code",
        "  can decide alone (from arguments, shown objects, the database or events). If the arguments only say what",
        "  a message must match (\"the user confirmed the order id in the arguments\"), comparing them is part of",
        "  reading the message, so the predicate is **conversation**. This follows brainstorm A2 (\"listed,",
        "  confirmed, reminded, chose\" are conversation facts).",
        "- **\"Tool outputs or user messages establish X\".** If the description accepts a user message as evidence,",
        "  the predicate needs message meaning, so it is **mixed**, even when the tool-output part is plain code.",
        "- The free text of `respond` and the `summary` of `transfer_to_human_agents` are arguments, but their value",
        "  needs their meaning, so predicates on them are **conversation**.",
        "",
        "## Counts",
        "| domain | argument | database fact | event | conversation | mixed | code types | total |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for domain in DOMAINS:
        c = counts[domain]
        code = sum(c[t] for t in CODE_TYPES)
        lines.append(f"| {domain} | " + " | ".join(str(c[t]) for t in TYPES) + f" | {code} | {sum(c.values())} |")
    tot = {t: sum(counts[d][t] for d in DOMAINS) for t in TYPES}
    lines.append("| all | " + " | ".join(str(tot[t]) for t in TYPES)
                 + f" | {sum(tot[t] for t in CODE_TYPES)} | {sum(tot.values())} |")
    lines.append("")
    for domain in DOMAINS:
        rs = load_rule_set(domain)
        tools = rule_tools(rs)
        lines += [
            f"## {domain.capitalize()} ({len(rs['predicates'])} predicates)",
            "Order: as in the rule set. \"tools\" lists the actions whose rules use the predicate.",
            "",
            "| # | predicate | description | sources | tools | type | reason | agent review |",
            "|---|---|---|---|---|---|---|---|",
        ]
        verdicts = review.get(domain, {}) if review else {}
        for i, (name, p) in enumerate(rs["predicates"].items(), 1):
            e = types[domain][name]
            lines.append(
                f"| {i} | `{name}` | {_cell(p['description'])} | {', '.join(p['source'])} | "
                f"{', '.join(tools.get(name, []))} | **{e['type']}** | {_cell(e['reason'])} | "
                f"{_cell(verdicts.get(name, ''))} |"
            )
        lines.append("")
    if review:
        lines += [
            "## Agent review",
            f"{review['status']}",
            "",
            "The reviewer did not write the draft. It checked each type against the description,",
            "the declared sources, the type table in `p3.md` and the questions in `overview.md`, and checked the facts the",
            "borderline types rest on in the copied τ-bench tool code and data. It did not look at judge values or gold",
            f"data. Result: {review['changes']} type changes. Notes and checks: `{review['details']}`.",
            "",
        ]
    lines += [
        "## Cases for the reviewer to look at first",
        "These are the choices the draft author was least sure about. Each one could reasonably go the other way.",
        "The agent's verdict on each is in the column \"agent review\" of the tables above.",
        "",
        "| domain | predicate | draft type | other choice | why it matters |",
        "|---|---|---|---|---|",
        "| airline | `cancellation_is_within_24_hours` | mixed | database fact | The description accepts user messages."
        " If only tool outputs should count (policy: \"the agent must make sure the rules apply\"), the tracker"
        " sets it from `created_at` and the current time. This is a rule the tools do not check. |",
        "| airline | `airline_cancelled_flight_confirmed` | mixed | database fact | Same as above. Note: no tool output"
        " shows a cancelled flight (search tools return only available flights), so as a database fact it must use"
        " the *fact* value from the flight data. |",
        "| airline | `compensation_is_prohibited_for_relevant_reservation` | mixed | database fact | `send_certificate`"
        " and `respond` name no reservation, so \"the relevant reservation\" comes from the conversation. A lookup"
        " could instead use every reservation shown. |",
        "| airline | `regular/silver/gold_member_booking_baggage_counts_correct` | argument | database fact | The"
        " sources list tool outputs, but membership is a separate predicate in the same rule, and the allowance is"
        " a fixed table in the policy. |",
        "| airline | `all_booking_passengers_share_flights_and_cabin`, `all_pending_flight_segments_have_one_cabin` |"
        " argument | - | The tool takes one cabin (and one flight list) for the whole call, so any well-formed call"
        " gives true. |",
        "| airline | `insured_cancellation_condition_met` | conversation | mixed | The sources list tool outputs, but"
        " no tool output shows a health or weather reason. |",
        "| airline, retail | `request_cannot_be_handled_with_available_tools`, `request_cannot_be_handled_within_scope`"
        " | conversation | mixed | Tool outputs (for example a flown segment) can be part of the reason, but there is"
        " no fixed fact for code to check. |",
        "| retail | `user_chose_pending_payment_method` | conversation | mixed | `overview.md` gives it as a mixed"
        " example. Its description has no fact code can check alone; the argument only says what the user's words"
        " must match. |",
        "| retail | `payment_method_is_gift_card` | argument | database fact | The id prefix `gift_card_` gives the"
        " kind. The user profile's `source` field would give the same. |",
        "",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write-md", action="store_true", help="write output/predicate_types.md")
    ap.add_argument("--force", action="store_true", help="overwrite an existing table (the agent review column is rebuilt from "
                    "p3_agent_review.json; hand edits to the table are lost)")
    a = ap.parse_args(argv)
    types = load_types()
    problems = check_types(types)
    review = load_agent_review()
    if review:
        problems += check_agent_review(review, types)
    for p in problems:
        print("PROBLEM:", p)
    counts = type_counts(types) if not problems else {}
    for domain, c in counts.items():
        print(domain, c, "total", sum(c.values()))
    if problems:
        return 1
    if a.write_md:
        if os.path.exists(TYPES_MD) and not a.force:
            print(f"{TYPES_MD} exists; use --force to overwrite (review notes would be lost)")
            return 1
        with open(TYPES_MD, "w", encoding="utf-8") as f:
            f.write(render_md(types))
        print("wrote", TYPES_MD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
