
## Fix round 2 (approved by the user; $0 part done by a sub-agent, 2026-10-24)
Plan: `fix_round2_plan.md`.
- **64 no-question blocks: a wiring bug, not the window.** The K3 facts still called v3's `ask_first_yes`; fix round 1
  gave K3 a second choice input (`verb`, filled by code), which v3's helper cannot fill, so every K3 ask raised
  ValueError -> fact_error -> block. All 76 K3 fact errors on the 200 conversations (52 modify, 24 exchange checks;
  64 where the stand-in allows, 12 where both block) are this one error. Fixed by overlay `facts_F2_retail.json`
  (K3 parts call `ask_first_yes_v4`). Test: `tests/test_v4_fix2.py`.
- **K13 v5**: asked with message B, the agent's message just before each user message (context only), and a yes
  when B says the policy rules do not let the agent do the task for this user and the user still asks for it or for
  a person to look at it; never for the refused list. All 30 K13 blocks were airline; 24 transfer summaries name a
  rule / not eligible; basic economy in 24.
- Policy text on transfer (both wikis): "transfer ... if and only if the request cannot be handled within the scope
  of your actions". The "user explicitly asks for a human" clause is only in the transfer tool's description, not
  in the wiki; the hard-no cases (human + in-scope task) follow the wiki, so it was not added.
