# Fix round 2 plan (2026-10-24, approved by the user as "fix round 2")

$0 work only. The main chat runs the paid re-runs.

## Problem 1: 64 blocks with no K3 answer
Cause (found by code): the K3 facts in `facts_v4_retail.json` still call v3's `ask_first_yes('K3', ..., items=...)`.
Fix round 1 gave K3 a second choice input (`verb`, filled by code from `items_action`). v3's helper does not know
`follows`, so it checks `items='modified'` against the verb values (`exchange`/`modify`) and raises ValueError ->
fact_error -> block. All 76 K3 fact errors on the 200 dev conversations (52 modify, 24 exchange checks; 64 of them
blocks the stand-in allows) are this one error. The window cut is not the cause.
Fix: a new fact overlay `output/eval_v4/overlays/facts_F2_retail.json` switches both K3 parts to
`ask_first_yes_v4` (same window, same items; adds the D10 re-ask). Rebuild with `scripts.v4_merge_overlays --write`.
Unit test: tests/test_v4_fix2.py runs the real K3 fact expressions with a fake hook.

## Problem 2: 30 K13 blocks on airline transfers
Pattern (counts by code): all 30 are airline; the block message names cancel_reservation 14,
update_reservation_flights 14, update_reservation_baggages 2; basic economy in 24; in 24 the agent's transfer
summary cites a rule / not eligible; in 13 the user asked for a human / supervisor / review.
K13 sees only the user message, so it cannot see that the agent already refused under the rules.
Fix: K13 v5 gets an optional second input: the agent's message just before message A. New rule in the text: if
that agent message (or A) says the rules do not let the agent do this for this user's booking / order, and A still
asks for it (or for a human to review it), answer yes; the refused list (S29-S32) stays no. Window helper
`user_messages_with_agent_before_v4` (helpers_v4.py); K13 fact overlays (A5) use it. Second wording bumped too.

## Problem 3: D2 unclear
14 of 15 are K13 first-wording unclears on long messages with no clear pattern; the new K13 may or may not fix
it. Say so.

## Checks
Full test suite, merge --check, offline eval in standin + count/saved modes, v4_message_check, dry runs.
