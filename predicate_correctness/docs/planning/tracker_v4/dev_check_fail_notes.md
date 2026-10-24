# Dev check on 200 dev conversations: FAIL notes (2026-10-24)

Run `v4dev_real_20261024T080806Z`, spend about $0.075 (dev total about $0.15 of $2).

| mark | result | pass |
|---|---|---|
| D1 tiny blocks ≤ 1.5× stand-in | 120 vs 32 (3.75×) | FAIL |
| D2 unclear ≤ 2 % | 15 / 703 (2.1 %; 14 allowed) | FAIL (by 1) |
| D3 two-key disagreements 0 | 0 | PASS |
| D4 state errors 0 | 0 | PASS |
| D5 fixable messages 100 % | 120 / 120 | PASS |

## Where the 120 blocks come from
- **64 blocks with no question** (modify_pending_order_items 43, exchange_delivered_order_items 21).
  Seen on one row: fact `agent_reminded_user_to_include_all_items_for_modification` is a **fact_error**
  (no value). K3 was never asked; only K1 was. The stand-in judge said true. So the guard blocks because
  the fact got no value, not because the answer was no. Likely cause: the K3 window cut finds no candidate
  message, and "no candidate" becomes an error, not an ask or a "no". This is a **code / wiring gap**, not a definition.
- **30 blocks from K13** (transfer_to_human_agents): tiny says "can't do it with tools = no", stand-in allows.
  K13 is the question the user already accepted as failing on cases (in the lenient direction there;
  here it is too strict).
- The other ~26 are spread out (K16 6, K1 5, K12 3, …) and look normal.
- Without the 64: 56 vs 32 = 1.75×, still over 1.5×. Without the 64 and the K13 30: 26 vs 32, a pass.

## Rule
Prereg §14: one fix round is used up (K3/K4/K13 definitions). A second fail means **stop and ask the user**.

## Options
1. Second fix round (needs approval): fix the K3 "no candidate" wiring (code), retune K13 to stop
   over-blocking on transfers, re-run the cases for K3/K13 and the 200 conversations (about $0.10).
   Log it in the change log as a second round beyond the prereg.
2. Accept the fail and go live. Risk: about 2× more blocks than the stand-in on item changes and
   transfers, which will likely cost task success in B2'/B3'.
3. Stop.
