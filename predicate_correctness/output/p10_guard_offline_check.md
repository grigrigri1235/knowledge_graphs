# Part 10: the guard offline on the saved steps

Written by `guard/offline.py`. No LLM call: a fake judge answers each judge call with the judge's saved values. The real guard (`guard/tgr_tracker.py` with the copied TGR runtime) runs on every Part 2 record and builds the state from the saved history.

| run, domain | records | decision = Part 8 (b) | margin = recomputed (b) | part 8 changed records | blocked (saved) | blocked (guard) | judge skipped | values replaced | values changed | records where the tracker agrees (or is unknown) | agreeing records with the saved decision and margin | lookup errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| luna_train_v5 airline | 321 | 321 | 321 | 1 | 12 | 13 | 0 | 222 | 5 | 316 | 316 | 0 |
| nano_train airline | 531 | 531 | 531 | 5 | 94 | 89 | 0 | 748 | 62 | 484 | 484 | 0 |
| luna_train_v5 retail | 1,729 | 1,729 | 1,729 | 7 | 54 | 51 | 0 | 2,180 | 25 | 1,704 | 1,704 | 0 |
| nano_train retail | 2,322 | 2,322 | 2,322 | 82 | 416 | 384 | 0 | 3,539 | 169 | 2,165 | 2,165 | 0 |
| **all** | 4,903 | 4,903 | 4,903 | 95 | 576 | 537 | 0 | 6,689 | 261 | 4,669 | 4,669 | 0 |

Problems: 0.


Checks:
- the decision equals Part 8 version (b) (`output/p8_changes.jsonl`; other steps keep the saved decision);
- the margin equals TGR's formula on the judge's values with Part 6's tracker values put in (version b);
- the tracker values equal Part 6 (`output/p6_values.jsonl`);
- where the tracker agrees with the judge (or gives unknown), the decision and the margin are the saved ones;
- the judge is called once with the same predicates as the saved judge call, or not at all when every predicate is a code type with a known value.

Time: 200 s.
