# Step 2b: automatic policy → ASPM pipeline, results report

Date: 2026-10-15. Pipeline: `policy_pipeline/` at tag `auto-pipeline-v1` (frozen). Gold standard: Steps 1–2 (`policies/curated/`, `aspm/*_aspm.json`, `policies/predicates/`). Development and tuning were done on **airline**; **retail** is the held-out test, run once with the frozen pipeline.

Related files: `docs/step2b_auto/iteration_log.md` (development history), `docs/step2b_auto/summary_for_pi.md` (one-page summary), `eval/labels/*`, `eval/results/*`.

---

## 0. Summary

| | Airline: original extraction | Airline: auto v1 (dev set) | Airline: auto v1 + addendum | Retail: original extraction | **Retail: auto v1 (held-out)** |
|---|---|---|---|---|---|
| **E2** covered / partial / incorrect / missing | 23 / 31 / 2 / 5 | 49 / 9 / 2 / 1 | 46 / 14 / 0 / 1 | 27 / 11 / 2 / 6 | **36 / 8 / 1 / 1** |
| E2 covered rate | 38 % | 80 % | 75 % | 59 % | **78 %** |
| E1 normative recall / precision | — | 60/61, 45/48 | 60/61, 45/48 (S1 cached) | — | **43/46, 40/51** |
| E3 equivalent (of comparable + non-comparable pairs) | — | 20/45 (0.44) | not mapped | — | **26/34 (0.76)** |
| E4 circuit recall (6–7 write tools) | — | 0.866 | 0.970 | — | **0.899** |
| Auto / gold circuit size, write tools | — | 2.0–4.6× | 2.8–5.8× | — | **1.2–4.6×** |
| E5 enforcement agreement | — | 0.844 | — | — | **0.794** |
| Share of `block` rules (gold) | (70 %) | 78 % | 76 % | (58 %) | **93 %** |
| E6 distinct LLM calls / output tokens | — | 1,598 / 1.78 M | 1,880 / 2.14 M | — | **1,556 / 1.85 M** |
| E6 wall time (fresh) | — | ≈ 25 min (est.) | 22.9 min (S2–S8) | — | **19.9 min** |

What the table says:
- **Clause coverage on the held-out domain holds up.** It is 78 % covered, against 80 % on the development domain, and missing clauses drop from 6 to 1.
- **The automatic ASPMs are not usable as blocking shields as they stand.** The circuits are 2–5× larger than gold. More importantly, several `block` rules fail on *every* policy-compliant call of a tool. That affects 6 of 7 retail write tools and 3 of 6 airline write tools (§6). Per-clause E2 does not show this, because it measures coverage, not precision.
- **The addendum ablation does not show a clean effect.** One of the five notes was reflected, one was ignored, and one retail-only note leaked into airline as an unsatisfiable rule (§3).

---

## 1. Setup

| Item | Value |
|---|---|
| Model | gpt-5-nano (Azure OpenAI Responses API, structured outputs). Temperature and seed are not supported by the deployment. |
| Stages | S0 tool classes → S1 clauses → S2 rules (extract, critic, revise) → S3 dedupe → S3b tool attribution (k = 3 + S2 vote) → S4 logic → S5 vocabulary → S6 tree → S7 predicate specs → S8 enforcement |
| Effort | medium for S0, S1, S2 extract/revise and S4; low elsewhere; k = 3 |
| Runtime predicates | every auto condition predicate is judged by an LLM at runtime (Step 3 builds the judge) |
| Runs evaluated | `output/auto_aspm/airline/v1` (= `aspm_auto/airline`), `output/auto_aspm/airline/v1_addendum`, `output/auto_aspm/retail/v1` (= `aspm_auto/retail`). Byte-identical copies checked with `cmp`. |
| Metrics | E1 clause segmentation (span overlap ≥ 0.5); E2 manual clause-coverage labels (Step 1 rubric) plus a proxy judge; E3 logic equivalence via a manual predicate mapping and an exhaustive truth table; E4 circuit recall per write tool; E5 enforcement and value-source agreement; E6 cost |

**E2 label conventions** (same as `airline_v1_e2.json`):
- over-included tools on an otherwise faithful rule → covered (note `TOOLS+`);
- a missing essential tool → partial (`TOOLS`);
- an extra rule from the same clause that adds restrictive content → partial (`HALL`/`SCOPE`/`MODAL`, as AIR-MOD-03a).

New in this step: `TOOLS+!` marks an over-attachment that makes the rule block compliant calls (circular, or contradicting another clause). For comparability it does **not** change the label. Its effect is shown as a sensitivity row in §2.2.

---

## 2. Integrity checks (T1)

### 2.1 Freeze

| Check | Result |
|---|---|
| Tag `auto-pipeline-v1` | Exists: annotated tag → commit `72a4dab` (2026-10-14 16:27:02), created with a temporary index; no branch moved. |
| `git diff auto-pipeline-v1 -- policy_pipeline/` | Shows every file as deleted. **This is misleading.** `policy_pipeline/` is untracked on `main`, so `git diff` sees no working-tree files. |
| Blob comparison (`git hash-object` vs the tag's blobs) | All 24 files in `policy_pipeline/`, plus `utility/utils.py`, `agent/utils.py`, `agent/tools/aspm_tool.py`, `scripts/validate_aspm.py` and `tests/policy_pipeline/*`, are **identical** to the tag. There are no untracked extra files in `policy_pipeline/`. |
| Manifest of `retail/v1` | **No commit hash is recorded** (the manifest has no such field). The 11 prompt-template hashes **all match** the tag. |
| Timing | Last code change `stages.py` 16:25:43 → `airline/v1` started 16:25:54 → tag 16:27:02 → `retail/v1` started 16:27:12. No pipeline file was modified after that. |
| LLM cache | The cache key = hash(system, user, params), so a hit is valid only for an identical prompt. `retail/v1` had 9 hits out of 1,561 calls: identical prompts within the run. |

**Verdict: the held-out retail run used exactly the frozen code. No re-run was needed.**

### 2.2 Tests and no-gold-leakage

`python -m unittest discover -s tests -t .` → **28 tests, OK** (66 s). This includes:
- `NoGoldLeakage.test_pipeline_never_references_gold_paths`: a static scan of `policy_pipeline/**/*.{py,md,txt,json}` for gold paths;
- `test_prompts_are_domain_agnostic`;
- `test_leak_detector_detects`: a self-test of the scanner;
- `test_error_messages_deterministic_across_hash_seeds`.

The leakage test is static. It proves that no gold path is referenced, not that no gold information entered the prompts by hand. The iteration log states that no gold text was pasted.

### 2.3 `scripts/validate_aspm.py --auto` (re-run, one process per ASPM)

| ASPM | Tree nodes | Rules | Truth-table assignments | Result |
|---|---|---|---|---|
| `output/auto_aspm/retail/v1` | 20 | 290 (271 block / 19 warn) | 6,104 | **PASS** |
| `aspm_auto/retail` (identical copy) | 20 | 290 | 6,104 | **PASS** |
| `aspm_auto/airline` (= `airline/v1`) | 18 | 277 (215 / 62) | 2,932 | **PASS** |
| `output/auto_aspm/airline/v1_addendum` | 18 | 369 (281 / 88) | 1,315,128 | **PASS** (about 60 CPU-min, single core) |

The addendum run is slow because of one 18-variable rule (S3-C07-R1, "rules S3-C01 … S3-C17 satisfied"), which is replicated five times. That rule alone is 1.3 M assignments, × 3 evaluators.

The validator checks the **structure and logic grammar** against the real runtime code. It does not check whether the rules are satisfiable by compliant calls (§6).

### 2.4 Spot-check of airline v1 E2 labels

I re-checked 12 labels: both `incorrect`, the one `missing`, and 9 `covered` (GEN-02a, GEN-05b, DOM-04c, BOOK-01a, BOOK-01b, MOD-02b, MOD-04a, CAN-02d, COMP-01c).

**No status changed.** The findings are recorded in the labels file (`spot_check_2026-10-15` fields):
- **AIR-BOOK-04b/04c (incorrect):** confirmed, but the recorded reason was only half right.
  - The descriptions say "only if silver/gold", but the logic is tier → allowance (an "if").
  - The logic is still contradictory: the per-cabin rules have no cabin antecedent. For example, for silver, S2-C09-R1 demands free bags = #basic-economy and S2-C09-R2 demands free bags = 2 × #economy.
- **AIR-BOOK-05b (missing):** confirmed. No rule or predicate mentions the $30 price.
- **AIR-BOOK-01a (covered, TOOLS+):** one extra tool is `respond_to_user` with `block`. "respond_to_user IMPLIES user_id_obtained" would block the agent's first message asking for the id.
- **AIR-GEN-05b (covered):** questionable. The iff rule sits on `transfer_to_human_agents`, where only the *only-if* direction can be enforced. The same structure was labelled partial (TOOLS) in AIR-CAN-03b. I kept the label for comparability and labelled RET-GEN-07b the same way; see open questions.

**Sensitivity of E2 to harmful over-attachment on write tools** (`TOOLS+!` counted as partial):
- retail: 36/8/1/1 → **34/10/1/1** (RET-MOD-01a, RET-MOD-02);
- airline v1: 49/9/2/1 → **48/10/2/1** (AIR-MOD-02a: its rule S3-C02-R1 also blocks basic-economy *bookings*).

The airline figure comes from the audited rules only; I did not re-audit every covered airline label for this.

### 2.5 Discrepancies with the hand-over state (§2 of the resume brief)

Every number in the hand-over for airline v1 was reproduced: `eval.collect` re-run gives a byte-identical `airline_v1_all.json`. Additional findings:
1. The Step 2b brief itself is **not saved** in `docs/`.
2. The manifest has no commit hash; the freeze was verified as in §2.1.
3. `E6.wall_seconds_total` = 47 s for `airline/v1` is a **cache replay** (1,575 of 1,605 hits), not a fresh run. The fresh-time estimate is in §5.
4. `retail/v1` and `airline/v1_addendum` started at the same second (16:27:12) and **ran concurrently** on the same deployment, so both wall times are contended.
5. In `retail/v1`, the S1 section "Exchange delivered order" failed validation after 3 attempts and was **accepted anyway**, without one sentence (RET-EXC-01c, §4).

---

## 3. Retail held-out evaluation (T2)

### E1: clauses

- Normative recall: **43/46 (0.935)**; 45/46 (0.978) if the kind is ignored.
- Normative precision: **40/51 (0.784)**. Kind accuracy: **0.778** (airline 0.867).

Misses:
- **RET-DOM-04b** ("product ids and item ids … should not be confused") and **RET-DOM-05b** ("Generally, you can only take action on pending or delivered orders") were segmented but labelled `fact`.
- **RET-EXC-01c** ("remind the customer to confirm they have provided all items to be exchanged") was **dropped by S1**: all 3 repair attempts left it uncovered, and the invalid section was kept.

The 11 unaligned auto normative clauses are gold **facts** labelled normative: "After user confirmation, the order status will be changed to …", the refund timing, "There is no need to place a new order", plus the scope sentence. This reverse error is the root of the most harmful retail rules (§4, P1).

### E2: rule coverage (manual, `eval/labels/retail_v1_e2.json`)

**36 covered / 8 partial / 1 incorrect / 1 missing.** Original extraction: 27 / 11 / 2 / 6.

| Status | Clauses |
|---|---|
| incorrect | RET-MITEM-01c: the trigger "after items were modified" was dropped, so the rules forbid modifying or cancelling *any* pending order. |
| missing | RET-DOM-04b (S1 fact). |
| partial (TOOLS) | GEN-01a (no authentication rule on `modify_user_address`); MITEM-03a and EXC-03a (price-difference payment rules attached to cancel/payment instead of modify-items/exchange); EXC-03b (no gift-card rule on exchange); RTN-02 and RTN-03 (refund-method confirmation and destination attached only to `cancel_pending_order`). |
| partial (other) | DOM-06a (SCOPE: "once only" extended to address/payment; per-interaction count incl. returns); MITEM-01a (HALL: post-state "status becomes pending (items modifed)" as a block obligation on six tools). |

Issue tags: TOOLS 6, MERGE 2, DROP 1, SCOPE 1, HALL 1, COND 1, INV 1.

`TOOLS+!` notes (label unchanged):
- GEN-01b and GEN-02: authentication rules also on the `find_user_id_*` tools (circular);
- MOD-01a: "modify only if pending" also on return/exchange (contradiction);
- MOD-01b: the status-check rule also on `get_order_details` (circular);
- MOD-02: "only item options change" on cancel.

Two notable recoveries:
- **RET-EXC-01c** was lost in S1, but the clause is covered: S3b attached the modify-items reminder (S5-C02-R5) to `exchange_delivered_order_items` as well.
- **RET-DOM-05b** is covered by the per-tool status rules, as in gold.

**Proxy** (`eval/results/retail_v1_proxy.json`): 33/12/0/1.
- Agreement with the manual labels: **accuracy 0.652, κ 0.114**, covered-vs-not 0.674.
- Of the 16 disagreements, the proxy misses wrong tool attachment (RTN-02, RTN-03, EXC-03b, MITEM-01a → covered). It also penalises allowed transformations: should → must (GEN-07a), merged confirmations (GEN-04b, CAN-02a), "to be modified" for exchange (EXC-01c).

### E3: logic equivalence (manual mapping, `eval/labels/retail_v1_e3.json`)

34 pairs, one per covered clause:
- **26 equivalent (0.765)**, 1 auto stricter, 0 auto weaker, 3 not equivalent, 4 not comparable;
- airline: 20/45 equivalent (0.444).

| Pair | Verdict | Why |
|---|---|---|
| RET-GEN-04a, RET-GEN-04b ↔ S0-C06-R1 | not equivalent | auto applies only to *cancellable* orders (antecedent narrowing) and bundles the confirmation |
| RET-MITEM-02a ↔ S5-C02-R6 | not equivalent | antecedent restricted to confirmed first calls; consequent bundles same product, different option and available |
| RET-EXC-02a ↔ S7-C03-R2 | auto stricter | conjunction of five gold rules |
| RET-GEN-03a, RET-GEN-07b, RET-MOD-02, RET-CAN-02a | not comparable | initiator vs target; message-level vs action-level; order-id-only confirmation |

E3 scores only *covered* clauses' best rule. That is why retail looks better than airline here, and why E3 does not see the harmful extra rules of §6.

### E4: circuit recall

| Write tool | Recalled / gold curated rules | Missed | Gold / auto circuit size |
|---|---|---|---|
| cancel_pending_order | 10/10 | — | 10 / 46 |
| exchange_delivered_order_items | 14/17 | R012, R028, R029 | 17 / 42 |
| modify_pending_order_address | 8/8 | — | 8 / 27 |
| modify_pending_order_items | 15/17 | R012, R028 | 17 / 41 |
| modify_pending_order_payment | 10/10 | — | 10 / 38 |
| modify_user_address | 5/6 | R001 (authentication) | 6 / 7 |
| return_delivered_order_items | 9/11 | R012, R031 | 11 / 33 |
| **micro** | **0.899** | | |

### E5: enforcement and value sources

- Enforcement agreement on the 34 pairs: **0.794** (block→block 23, warn→block 7, warn→warn 4; no block→warn).
- Value-source agreement: **0.744** (n = 39).
- Overall, the auto retail ASPM is **93 % block** (271/290); gold is 58 %. The S8 criterion ("can a violation change persistent state?") marks almost every write-tool rule as block, including the dialogue-ordering rules that gold sets to warn.

### E6: cost (retail)

1,556 distinct calls; 1.91 M input / 1.85 M output tokens, of which 1.61 M are reasoning tokens. Wall time **19.9 min** (concurrent with the addendum run).

| Stage | Calls | Input tokens | Output tokens |
|---|---|---|---|
| S7 specs | 414 | 950 k | 276 k |
| S4 logic | 124 | 138 k | 553 k |
| S3b tools | 324 | 326 k | 187 k |
| S8 enforcement | 324 | 103 k | 142 k |
| S2 (extract, critic, revise) | 168 | 296 k | 506 k |
| S0, S1, S3, S5 | 202 | 102 k | 189 k |

---

## 4. Addendum ablation, airline (T3)

**Method.** For each gold clause, if every v1-matched auto rule exists unchanged in `v1_addendum` (same description, tools and logic), the v1 label is carried over. This held for 4 clauses: GEN-02b, GEN-04, BOOK-02b, CAN-02e. The addendum enters S2, so S2 onward re-ran without a seed, and **57 of 61 clauses had changed rules**. These were labelled manually (`eval/labels/airline_v1_addendum_e2.json`).

**Caveat:** with one run per arm and no seed, the difference conflates the addendum with run-to-run variance. Between dev iterations 2 and 3 the S2 rule count moved from 94 to 120 with no prompt change.

| | v1 | v1 + addendum |
|---|---|---|
| E2 covered / partial / incorrect / missing | 49 / 9 / 2 / 1 | **46 / 14 / 0 / 1** |
| E1 | 60/61, 45/48 | identical (S1 cached) |
| E4 micro recall | 0.866 | **0.970** (book 19/20, cancel 9/9) |
| ASPM rules / predicates | 277 / 163 | 369 / 213 |
| Circuit size, write tools | 19–41 | 22–58 |
| Judged predicates per write call | 50.5 | 84.0 |

Changes, clause by clause:
- **Better:**
  - BOOK-04b/04c are now "if" (incorrect → covered); no note concerns bags, so this is variance;
  - BOOK-04d and BOOK-05a now include `book_reservation`;
  - the COMP-01a operator scope is fixed.
- **Worse:**
  - BOOK-01a gained a leaked retail rule (see note 5 below);
  - BOOK-01b became an ordering-only rule;
  - MOD-02d: meta-reference unresolved;
  - MOD-04a: the permission "can add bags" became an obligation with a post-state;
  - MOD-06b narrowed to cabin changes;
  - CAN-02a/02b: the exceptions became the only allowed cases;
  - CAN-02d: "cancel only business";
  - CAN-03a: leaked rule.

**Were the five interpretation decisions reflected?**

| Note | Expected | Observed |
|---|---|---|
| 1. Book only if status is "available", incl. a flight added to an existing reservation | an "available" requirement on `book_reservation` and `update_reservation_flights` | **Not reflected.** Rules stay literal ("not delayed / on time", "not flying"); nothing on `update_reservation_flights`. |
| 2. Transfer if out of scope OR explicit request; the request case does not cover requests to deny or passenger-count changes | the disjunct plus two exceptions | **Partly.** The disjunct is present (it already was in v1, from the tool description). Neither exception is encoded. |
| 3. Confirmation also applies to cancellation | list + confirm on `cancel_reservation` | **Reflected.** S0-C03-R1 and S0-C02-R2/R6 include cancel. v1 followed the literal parenthetical. E4: AIR-R002 on cancel is now recalled. |
| 4. "Exchange or modify order tools … once" means item tools only | (retail note; no airline effect) | No effect, as expected. |
| 5. Authenticate via email or name + zip, even if the user gave an id | (retail note) | **Leaked into airline.** S0-C02-R7, S2-C01-R1 and S4-C08-R1 require locating the user id "via email or name + zip" (block) on every airline write tool and `respond_to_user`. τ-bench airline has no such lookup, so these rules can never be satisfied. |

The addendum file mixes airline notes (1–3) and retail notes (4–5) and was run only on airline. The pipeline injects it into every S2/S3b/S4 prompt without any domain or tool filter. The ablation therefore says less about "do interpretation notes help" than about "the pipeline applies notes indiscriminately". A clean re-test needs a per-domain addendum and ≥ 2 runs per arm.

---

## 5. Cost (E6)

| Run | Distinct calls | Input tokens | Output tokens (reasoning) | Wall time |
|---|---|---|---|---|
| airline v1 | 1,598 | 1.46 M | 1.78 M (1.54 M) | ≈ 25 min fresh (estimate)¹ |
| airline v1 + addendum | 1,880 | 1.82 M | 2.14 M (1.85 M) | 22.9 min for S2–S8 (S0/S1 cached), concurrent |
| retail v1 | 1,556 | 1.91 M | 1.85 M (1.61 M) | 19.9 min, concurrent |

¹ The `v1` manifest is a cache replay (47 s). The estimate is the addendum run's S2–S8 time (22.9 min) plus S0/S1 (≈ 2 min in retail). The earlier fresh dev runs took 56 min (it0) and 26 min (it1).

**S3b**, which had no exact timing before: 76.0 s (airline, addendum run, fresh) and 91.6 s (retail), about 320 calls (≈ 20 % of calls, ≈ 10 % of output tokens). `dev_it4` shows 0.2 s for S3b because it was cached from the S3b trial run on iteration 3. Reasoning tokens are 86–87 % of output in every run.

---

## 6. Failure patterns (T4, both domains)

Ordered by runtime harm. For each pattern: the stage where it arises, examples, and a proposed fix (**not implemented**).

### P1. Outcome statements and permissions become blocking constraints (S1 kind → S2 → S4)
- **What happens.**
  - Gold facts describing *what the system does after the call* are labelled normative (retail E1: 11 such clauses). S2 then writes "must change the status to 'return requested'". S4 formalises the effect as the consequent.
  - Permissions ("can", "may") become obligations at S2, and at S4 they take the form `action IMPLIES case`, which makes the permitted case the *only* allowed one.
- **Examples.**
  - Retail S6-C05-R1: `(return AND confirmed AND delivered AND checked) IMPLIES order_status_return_requested`, which is false before every compliant return.
  - Retail S5-C06-R3: status "pending (items modifed)" required on six tools.
  - Airline S4-C07-R4: "may cancel business flights" → `cancel IMPLIES reservation_is_business`.
  - Airline S3-C08-R1: "must allow cabin changes" → `update_reservation_flights IMPLIES flights_unchanged`.
  - Addendum S3-C11-R2: the "can add bags" permission plus a post-state.
- **Fix.**
  1. S7 records for each predicate whether it describes the state *before* or *after* the call. S6 rejects rules whose consequent is an after-state of the constrained action.
  2. A deterministic S4 check: a `may` rule never becomes `action IMPLIES X`. Instead it is dropped, or used to *weaken* the restriction it is an exception to (`… AND NOT permission_case`).
  3. S1: "a sentence stating what happens after an action is a fact" as a generic rule, with a k-vote on the kind.

### P2. Over- and mis-attachment: large, contradictory or circular circuits (S3b vote, S6 groups, weak S3 dedupe)
- **What happens.** Auto circuits are 2–4.6× gold (retail `cancel_pending_order` 46 vs 10; airline `cancel_reservation` 35 vs 9). There are three causes:
  - broad S3b attributions are inherited through S6 group nodes;
  - the same constraint survives 3–6 times (e.g. the retail "check status first" rules S2-C02-R1, S2-C05-R1, S3-C01-R2, S3-C02-R1, S3-C05-R1, S6-C02-R2), because S3's 0.88 embedding threshold merges only near-verbatim rules;
  - some rules are attached to the wrong tool altogether.
- **Harmful cases.**
  - Retail S3-C02-R2 ("modify only if pending") on return/exchange contradicts "delivered".
  - Authentication rules on `find_user_id_*`, and the status-check rule on `get_order_details`, are circular.
  - Price-difference payment rules sit on `cancel_pending_order` / `modify_pending_order_payment` instead of modify-items/exchange. These are missed attachments: 6 of the 8 retail partials.
  - Airline S3-C02-R1 on `book_reservation` blocks basic-economy bookings; S3-C04-R1 ("keep a segment") on `cancel_reservation`.
- **Fix.**
  1. Schema check at S3b: a rule whose predicates read call arguments may attach only to tools that have those arguments (e.g. `payment_method_id` is not on `cancel_pending_order`).
  2. Do not attach a precondition rule to the tool that establishes it (lookups).
  3. A per-circuit **satisfiability check** after S8: ask whether one compliant scenario satisfies all block rules of the tool (LLM scenario generation plus the existing Kleene evaluator), and flag rules that are never satisfiable.
  4. A second S3 merge pass with an LLM equivalence vote below the embedding threshold.

### P3. Dropped triggers and invented conditions (S2 splitting, S4 antecedents)
- **What happens.** When S2 splits a compound sentence, a rule loses its anaphoric trigger ("anymore", "the condition", "instead"). S4 also drops cabin/tier antecedents or adds "only if".
- **Examples.**
  - Retail RET-MITEM-01c: "will not be able to modify or cancel the order anymore" became `action IMPLIES NOT order_modifiable` and `cancel IMPLIES NOT order_cancellable`, which forbid every pending-order write (the only retail *incorrect*).
  - Airline BOOK-04b/04c: "only if silver/gold"; no cabin antecedent in the logic.
  - Airline CAN-02c: "the condition" grounded as a cancellation window instead of health/weather.
  - Addendum CAN-02a/02b: exceptions became the only allowed cases.
- **Fix.**
  1. An S4 back-translation check: every conditional word in the S2 description (if/after/unless/only if/when) must appear as an antecedent predicate, and none may be added.
  2. The S2 critic at medium effort for clauses with anaphora (cheap: about 10 clauses).
  3. Reject rules containing unresolved references (`anymore`, `instead`, `S3-C15`, "these rules"), deterministically.

### P4. Normative content classified as a fact, or dropped (S1)
- **Examples.**
  - AIR-BOOK-05b ($30 per passenger) and RET-DOM-04b (product vs item ids) were labelled `fact`, so no S2 rule was ever written.
  - RET-EXC-01c was dropped after 3 failed S1 repairs, and the invalid section was accepted.
  - RET-DOM-05b was also a fact, but its content was recovered from other clauses.
- **Fix.**
  1. When S1 repairs fail, add the uncovered sentence verbatim as its own clause rather than dropping it.
  2. Let S2 see fact clauses that contain numbers, prices or "should/must" words, with the instruction "emit a rule only if it constrains an action".

### P5. Predicates not comparable to gold, or ungrounded (S4/S7)
- **Not comparable:** airline 13/45 pairs, retail 4/34. The causes are different decomposition (per-field or per-cabin splits vs gold's pooled predicates), literal vs interpreted readings (flight status), and message-level vs action-level rules.
- **Ungrounded concepts** that τ-bench does not have:
  - retail `user_authenticated` ("login, session token"), `modification_freeze_active` (its text says it is true), `fees_accepted`, cancellation windows;
  - addendum `s3_c01_satisfied … s3_c17_satisfied` and `rules_check_passed`.
  
  At runtime these force the judge to guess.
- **Fix.** An S7 grounding check: each predicate must name the tool-schema field or dialogue fact it reads. Reject references to pipeline clause ids and to concepts absent from the tool schemas, then repair.

### P6. Addendum applied without scope (S2/S3b/S4 prompt injection)
The retail authentication note became airline rules (§4). **Fix:** per-domain addenda; deterministically drop notes whose concepts (tools, identifiers) do not occur in the domain's tool schema.

---

## 7. Runtime implications for Step 3 (T5)

### 7.1 Judge load (`python -m eval.runtime_load` → `eval/results/judge_load.json`)

Distinct condition predicates per write-tool circuit. All auto predicates go to the LLM judge; for gold, only `dialogue` predicates do (the rest are Python).

| Domain | Write tool | Auto rules (block) | Auto judged predicates | Gold rules (block) | Gold predicates (judged) |
|---|---|---|---|---|---|
| airline | book_reservation | 41 (38) | 61 | 20 (16) | 21 (5) |
| | cancel_reservation | 35 (31) | 48 | 9 (7) | 13 (5) |
| | send_certificate | 19 (14) | 35 | 8 (7) | 13 (4) |
| | update_reservation_baggages | 34 (30) | 55 | 10 (9) | 11 (2) |
| | update_reservation_flights | 39 (34) | 58 | 13 (11) | 15 (3) |
| | update_reservation_passengers | 32 (28) | 46 | 7 (6) | 7 (2) |
| retail | cancel_pending_order | 46 (44) | 67 | 10 (8) | 10 (3) |
| | exchange_delivered_order_items | 42 (40) | 44 | 17 (12) | 19 (5) |
| | modify_pending_order_address | 27 (26) | 38 | 8 (7) | 8 (2) |
| | modify_pending_order_items | 41 (40) | 62 | 17 (12) | 19 (5) |
| | modify_pending_order_payment | 38 (37) | 57 | 10 (9) | 11 (2) |
| | modify_user_address | 7 (7) | 9 | 6 (5) | 6 (2) |
| | return_delivered_order_items | 33 (29) | 41 | 11 (9) | 11 (3) |

- **Expected predicates per judge call** (one batched call per shielded write call): auto **≈ 50 (airline 50.5, retail 45.4; addendum 84)**, gold **≈ 3 (3.5 / 3.1)**. That is about 15× more judge items.
- Auto predicate descriptions average about 30 words, and the full S7 judge spec (question + context + unknown hint) about 94 words. Fifty predicates therefore add roughly 1.5 k (descriptions only) to 4.7 k words (full specs) to every judge prompt, before the trajectory. Whether gpt-5-nano answers about 50 batched questions reliably is untested. Smaller batches (e.g. 10–15) should be evaluated against a single call.

### 7.2 False-positive risk

**(a) E3 auto-stricter pairs whose auto rule is `block`.** These are the formal list asked for.
- airline:
  - S3-C02-R1: any flight update of a basic-economy reservation, *and* basic-economy bookings;
  - S3-C16-R1: the "flights changed" trigger dropped;
  - S3-C07-R7: gold warn; its predicate also requires the call to carry no `payment_id`;
  - S4-C01-R1 ×3 clauses: one conjunction of user id, reservation id and reason; gold sets the reason to warn;
  - S4-C07-R4: cancel only business;
  - S5-C01-R1: operator scope plus a $100 amount;
  - S5-C02-R1: delayed-flight eligibility;
  - not equivalent: S5-C02-R2 ($50 amount not tied to a delay).
- retail:
  - S7-C03-R2: five gold rules in one conjunction, including confirmation;
  - not equivalent: S0-C06-R1 (only for cancellable orders), S5-C02-R6.

**(b) Structural false blocks** (`eval/labels/false_block_audit.json`, manual, assuming a literal judge). These are block rules that fail on a **policy-compliant** call of the tool. They are more serious than (a), because E3 never sees them.

| Domain | Write tool | Always-failing block rules | Cause |
|---|---|---|---|
| retail | cancel_pending_order | 10 | post-states (S2-C05-R6, S2-C06-R2, S4-C03-R1, S5-C06-R3); dropped trigger (S5-C02-R3, S5-C03-R2, S5-C03-R1); attachment (S3-C01-R3, S3-C06-R1, S5-C08-R1) |
| | return_delivered_order_items | 7 | post-states (S4-C03-R1, S5-C06-R3, S6-C05-R1, S6-C06-R2, S7-C07-R3), S5-C03-R1, S3-C02-R2 ("pending") |
| | exchange_delivered_order_items | 6 | post-states (S4-C03-R1, S5-C06-R3, S7-C07-R1, S7-C08-R3), S5-C03-R1, S3-C02-R2 |
| | modify_pending_order_items | 4 | S5-C06-R3, S7-C08-R3, S5-C02-R3, S5-C03-R1 |
| | modify_pending_order_address, modify_pending_order_payment | 3 each | S5-C06-R3, S5-C02-R3, S5-C03-R1 |
| | modify_user_address | 0 | — |
| airline | cancel_reservation | 1 unconditional + 3 conditional | S3-C04-R1 ("keep a segment"); S4-C07-R4 (non-business), S4-C02-R1/S4-C05-R3 (business/insured outside 24 h) |
| | send_certificate | 2 (contradictory pair) | S5-C01-R1 (100 × N) and S5-C02-R4 (50 × N) both fire on every call |
| | update_reservation_flights | 1 | S3-C08-R1 (`flights_unchanged`) |
| | book_reservation, update_reservation_baggages | conditional | tier bag rules without a cabin antecedent (silver; gold business/basic economy); S3-C02-R1 (basic-economy booking) |

So in a direct Step 4 run, the auto retail ASPM would block every cancel, modify, return and exchange call. Only `modify_user_address` would pass. Airline would block every cancellation, every certificate and every flight change. Enforcement also skews towards blocking: retail auto is 93 % block (gold 58 %), and E5 shows warn→block flips (airline 5, retail 7) and almost no block→warn.

### 7.3 Gold or auto first?

**Use the gold ASPM first** to build and debug the Step 3 runtime:
- Its predicates are deterministic Python with unit tests, plus a small judge (2–5 dialogue predicates per call).
- Its firing behaviour on recorded trajectories is already known (Step 2 firing analysis).
- Its rules are satisfiable by construction. Runtime bugs (grounding, `None` handling, judge batching, decision logic) can then be told apart from ASPM defects.

Once the runtime is stable, run the auto ASPMs as the *experimental* condition. The clean way to measure them as produced is to keep them unmodified and also report a `block`→advisory (warn-only) variant, which separates "would have blocked" from "harmed the task". Any automatic repair (P1–P2 fixes) would be a pipeline v2 and needs a new held-out test.

---

## 8. Limitations
- **Airline was the development set.** Prompts and validators were tuned on it over 5 iterations, so its numbers are optimistic. Retail is the only held-out measurement, and it is now used up for that purpose.
- **One run per configuration, no seed.** Run-to-run variance is large: S2 rule counts of 94 vs 120, and 57/61 clauses with changed rules between v1 and the addendum run. Differences of a few clauses are within noise.
- **Single labeller** (Claude), so there is no inter-annotator agreement. Labels judge rule descriptions and constrained tools. Logic is judged only through E3, and only for covered clauses.
- **E2 measures coverage, not precision.** Harmful extra rules appear only in notes (`TOOLS+!`), in the sensitivity row, and in the §6/§7.2 audits. E4 counts partial matches as recalled and does not penalise extra rules.
- **The false-block audit is a manual reading under a literal-judge assumption.** A lenient judge might pass some of these rules; that is a Step 3 question.
- **The proxy judge is unreliable per clause** (κ ≈ 0.11–0.14). It is blind to tool attachment and biased against allowed transformations. Use it only for coarse trends.
- **Wall times** for retail and the addendum come from concurrent runs. Airline v1's fresh time is an estimate.
- **The addendum mixed domains** and the ablation has one run per arm.
- **The gold standard embodies interpretation choices** (e.g. narrow "once", exact bag equality, "available" status); some disagreements are interpretation, not error.

## 9. Open questions
1. **Fix the pipeline before Step 3/4?** P1 and P2 are cheap and largely deterministic fixes, and they would remove most structural false blocks. But a v2 needs a fresh held-out policy, since retail is spent. Candidates: another τ-bench-style domain or a rewritten policy.
2. **How should the auto ASPM enter Step 4:** as is (expect near-total blocking in retail), warn-only, or after an automatic satisfiability filter (which is part of a v2)?
3. **Labelling convention:** should harmful over-attachment (`TOOLS+!`) count as partial? This changes retail 36→34 covered and airline 49→48. Should AIR-GEN-05b and RET-GEN-07b (the "must transfer" direction on the transfer tool) be partial, consistent with AIR-CAN-03b?
4. **Addendum:** re-run with a per-domain addendum and ≥ 2 runs per arm, to separate the note effect from variance?
5. **Judge batching:** one call with about 50 predicates, or several smaller batches? This needs a small accuracy test on recorded trajectories in Step 3.
6. **The two gold-vs-benchmark conflicts from Step 2** (NQNU5R; same-item exchanges) remain open and will also affect any auto-ASPM comparison.

---

## Changelog (this step)

No changes to `policy_pipeline/`, the gold artefacts, `agent/tools/`, `output/deep_policy/` or the Azure configuration.

| File | Change | Reason |
|---|---|---|
| `eval/labels/retail_v1_e2.json` | new | T2 manual E2 labels |
| `eval/labels/retail_v1_e3.json` | new | T2 manual predicate mapping |
| `eval/labels/retail_v1_worksheet.md`, `retail_v1_e3_worksheet.txt` | new (generated) | labelling aids (`eval.e2_rules worksheet`, `eval.e3_worksheet`) |
| `eval/labels/airline_v1_addendum_e2.json`, `airline_v1_addendum_worksheet.md` | new | T3 labels and worksheet |
| `eval/labels/airline_v1_e2.json` | added `spot_check_2026-10-15` fields on 12 labels and a top-level `spot_check` block; **no status changed** | T1.4 |
| `eval/labels/false_block_audit.json` | new | T5 manual audit |
| `eval/results/retail_v1_proxy.json`, `retail_v1_all.json` | new | T2 (`eval.e2_rules proxy`, `eval.collect`) |
| `eval/results/airline_v1_addendum_all.json` | new | T3 (`eval.collect`; no E3 mapping, so no E3/E5) |
| `eval/results/judge_load.json`, `eval/runtime_load.py` | new | T5 judge-load computation (eval code only) |
| `output/auto_aspm/proxy_retail_v1.log` | new | log of the proxy run |
| `eval/results/airline_v1_all.json` | unchanged (re-collected: byte-identical) | reproducibility check |
