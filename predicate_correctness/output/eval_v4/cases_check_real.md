# Tracker v4: made-up cases through the tiny questions (real)

Written by `scoring/v4_cases.py` on 2026-10-24 07:49 UTC. Pass mark: at least 28 of 30 right on the yes side and on the hard-no side, per question (preregistration_v4.md §14). Cases 720; bad lines 0.

## Overall: **FAIL**

| question | yes side right | hard-no side right | unclear (yes / no) | not asked | first wording only (yes / no) | pass |
|---|---|---|---|---|---|---|
| K1 | 30 / 30 | 28 / 30 | 0 / 0 | 0 | 30 / 28 | PASS |
| K3 | 29 / 30 | 24 / 30 | 0 / 0 | 0 | 29 / 24 | **FAIL** |
| K4 | 27 / 30 | 29 / 30 | 0 / 0 | 0 | 27 / 29 | **FAIL** |
| K6 | 30 / 30 | 28 / 30 | 0 / 0 | 0 | 30 / 28 | PASS |
| K7 | 30 / 30 | 30 / 30 | 0 / 0 | 0 | 30 / 30 | PASS |
| K8 | 29 / 30 | 30 / 30 | 0 / 0 | 0 | 29 / 30 | PASS |
| K10 | 28 / 30 | 30 / 30 | 2 / 0 | 0 | 28 / 30 | PASS |
| K12 | 30 / 30 | 30 / 30 | 0 / 0 | 0 | 30 / 30 | PASS |
| K13 | 30 / 30 | 26 / 30 | 0 / 1 | 0 | 30 / 26 | **FAIL** |
| K16 | 30 / 30 | 30 / 30 | 0 / 0 | 0 | 29 / 30 | PASS |
| K17 | 30 / 30 | 30 / 30 | 0 / 0 | 0 | 30 / 30 | PASS |
| K18 | 29 / 30 | 30 / 30 | 0 / 0 | 0 | 29 / 30 | PASS |

## Wrong cases by kind (patterns, not single cases)

- K1: hard_no: question_price_refund 1, hard_no: changed_detail 1
- K3: hard_no: different_order_window_edge 5, yes: statement_plus_question 1, hard_no: right_item_question 1
- K4: yes: indirect_under_name 3, hard_no: gift_bought_for_someone 1
- K6: hard_no: health_mentioned_other_reason 1, hard_no: insurance_rules_question 1
- K8: yes: complaint + request for compensation 1
- K10: yes: "what will you give me for this" 2
- K13: hard_no: escalate_wording_in_scope 3, hard_no: refused_list 1
- K18: yes: paraphrase_ordered_by_mistake 1

Spend: {"usd": 0.05401550000000002, "calls": 733}
