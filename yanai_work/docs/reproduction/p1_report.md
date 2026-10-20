# P1 report: faithful ShieldAgent extraction (Stage A), airline and retail

Pipeline: `repro_pipeline/` frozen at git tag **`repro-p1-v1`** (commit `98d029c`). gpt-5-nano (reasoning effort medium); embeddings bge-large-en-v1.5 in bf16 (D1); Alg. 2 with M_it = 10, N_b = 3 × #E2 rules, per-lineage cap 3, τ_RP = 0.80; Alg. 3 with θ = 0.80 and k by eigengap. Implementation history: `p1_log.md` (I1–I8). Rule tables: `aspm_repro/airline/rules.md`, `docs/reproduction/retail_v1_rules.md`.

## Airline (v4, published to `aspm_repro/airline/`)

| | |
|---|---|
| Policy blocks → E2 rules → final rules | 43 → 105 → **58** (103 predicates: 34 action / 69 condition; 23 physical; 38 temporal) |
| Alg. 2 stop | convergence at iteration 8; VR budget exhausted in iteration 2 (316/315); iterations 3–8 RP only |
| Repairs | 105/1,155 (9.1 %): 70 declaration (67 ok), 35 syntax (15 ok); 23 rules dropped; 0 meaning-changing |
| Circuits | 34 → 24 clusters after merge; max 26 predicates (3 circuits > 20); median 4; 7 rules in no circuit |
| MLN groups under P2-1 (worst case, all conditions unknown) | max 21 unknowns; 3 groups > 16, so Gibbs sampling is needed |
| Rules chaining IMPLIES (P2-5) | 1, and its parse differs from its description (rule 44: parses as a tautology; the description says "equivalence") |
| Inconsistent predicate types (P2-3) | 1 |
| Never block / can block / block every step (P2-2 + P2-4, 2-step prefixes, 44 rule–action pairs) | 13 / 29 / 2 |
| Cost (fresh-equivalent) | 661 calls, 1.19 M in / 2.88 M out ≈ $1.21; Alg. 2 ≈ 1 h (bf16, mostly fresh in v4) |

Per-iteration table, typical problems and content check: `p1_log.md` → "Airline v4 results" and "Airline findings". In short:
- cancellation eligibility, compensation restrictions, the basic-economy flight-change ban and origin/destination/trip-type preservation are **missing or not enforceable**; rule 58 obliges a certificate offer;
- rule 4 will likely cause false blocks;
- the action predicates are abstract, so runtime mapping is needed (p2_design.md §3).

## Retail (v1, frozen code; not published)

Run `output/repro/aspm_runs/retail/v1`. The code matches tag `repro-p1-v1` blob-for-blob; params, prompt hashes and embedding config match airline v4. No implementation bug; 6 transient API errors, all retried.

| | |
|---|---|
| Policy blocks → E2 rules → final rules | 34 → 74 → **43** (56 predicates: 15 action / 41 condition; 19 physical; 26 temporal) |
| Alg. 2 stop | iteration 10 = M_it, with no merge in its RP (convergence and the cap coincide); VR budget exhausted in iteration 2 (223/222); iterations 3–10 RP only |
| Repairs | 45/728 (6.2 %): 19 declaration (19 ok), 26 syntax (9 ok); 17 rules dropped; 0 meaning-changing |
| Circuits | 23 → 22 clusters after merge; max 5 predicates, median 4; 12 distinct circuits over 15 actions; **18 rules in no circuit** (all physical) |
| MLN groups under P2-1 (worst case) | max 4 unknowns; 0 groups > 16, so exact enumeration always |
| Rules chaining IMPLIES (P2-5) | 2; 1 parse differs from its description (rule 39 loses "modify only if pending"; rule 29 is parenthesised) |
| Inconsistent predicate types (P2-3) | 0 |
| Never block / can block / block every step (P2-2 + P2-4, 2-step prefixes, 26 rule–action pairs) | 6 / 20 / 0 (plain LTLf: 1 / 24 / 1) |
| Cost | 558 calls (493 distinct), 0.89 M in / 2.19 M out ≈ **$0.92** (fresh-equivalent $0.91); wall 66 min (Alg. 2 62 min) |

Per-iteration table, typical problems and the full content check: `p1_log.md` → "Retail v1 results" and "Retail findings". In short:
- **Typical problems:**
  - unenforceable schema facts plus unpruned exact duplicates (rules 14 ≡ 15, 24 ≡ 26 ≡ 28, 25 ≡ 27, 33 ≡ 34);
  - over-generalisation likely to cause false blocks (rule 32 forbids every tool call after the first order tool call; rule 30 consecutive tool calls; rule 16 turns an example into a requirement);
  - abstract or obligation-only action predicates (8 obligations, 6 can never block).
- **Critical content:**
  - authentication only gates information disclosure (rule 21), not write actions;
  - status preconditions: only modify requires pending (rule 36); cancel-pending and return/exchange-delivered are absent;
  - only-once: partial (rule 39), plus the over-general rule 32;
  - return refund destination: wrong scope (rule 17, original payment method only; the gift-card option is missing);
  - cancellation reasons: absent (no cancellation rule at all);
  - gift-card balance: present for price differences (rule 40), absent for payment-method changes;
  - explicit confirmation before writes: absent.

## Cross-domain summary

| | airline v4 | retail v1 |
|---|---|---|
| final rules / predicates | 58 / 103 | 43 / 56 |
| rules in no circuit | 7 | 18 |
| max circuit predicates / MLN groups > 16 | 26 / 3 | 5 / 0 |
| IMPLIES chaining (parse ≠ description) | 1 (1) | 2 (1) |
| P2-3 type conflicts | 1 | 0 |
| never / can / every step (2-step, runtime) | 13 / 29 / 2 | 6 / 20 / 0 |
| cost / Alg. 2 wall | $1.21 / ≈ 1 h | $0.92 / 62 min |
