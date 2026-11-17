# Brainstorm: a steadier rule build for the TGR guard

Written 2026-11-17. Read only: no code run, no LLM call, $0. Web search used (sources at the end).
Status: ideas only. Nothing is planned or approved yet.

**SCOPE (user, 2026-11-17): only the rule build changes. The 66 facts and v4's way of setting their values stay
exactly as they are.** Sections 1-7 are the first round and partly out of scope (ideas 2 and 4 change the facts).
Section 8 is the current version.

## 1. Where the randomness is today

The guard has three steps. Only two are still random.

| step | when | today | random? |
|---|---|---|---|
| A. build the rules and facts from the policy | once, offline | 1 LLM call per domain (+ up to 2 repairs), no temperature, no seed | yes, on every fresh build |
| B. set each fact's value | every check | v4: 40 facts by code, 26 by code + a tiny question | only the 26 question facts |
| C. apply the rules to the values | every check | TGR's decision code | no |

Step A is the target here. Facts from the notes (`reading_notes/tgr_build_method.md`):
- A re-run on the same input replays the cache. So the frozen rule set is already fixed at run time.
- A fresh build is a new random sample. Rule counts moved between builds: airline 38/31/34/35/34, retail
  58/42/42/61/64. Part is prompt changes, part is sampling (it2 and it3 folded the same exceptions differently).
- The partner's protocol: one build is the result. No picking among samples, no rule edits.

So "deterministic" needs a sharper word. Three different things:
1. **Repeatable**: same input, same output. The cache already gives this.
2. **Stable across samples**: a fresh build gives the same rules. Not true today, and never measured.
3. **Stable across small edits**: one changed policy sentence changes only its own rules. Not true today: the
   whole policy is one call, so everything is re-sampled.

The goal should be 2 and 3. Goal 1 alone is cheap and proves little.

## 2. Two things already in our hands

- **Sentence ids are made by code.** The policy is split into `[S1]..[Sn]` by a regex, before the LLM sees it.
  Every build must give each sentence exactly one label (rule, exception, fact, not enforceable) and its rule ids.
  So two builds can be compared sentence by sentence, with no fuzzy matching.
- **The rule table.** v3 lists every true/false combination of every rule. So rule logic can be compared as truth
  tables, not as text.

The hard part is fact names. Two builds name the same fact differently ("order_is_pending" vs
"order_status_checked_pending"). Any vote across builds must solve that first. Ideas 2 and 4 remove the problem
instead of solving it.

## 3. Ten ideas

| # | idea | how it works | gain | cost / risk |
|---|---|---|---|---|
| 1 | **Measure it first** | Build N times (N = 5 to 10) into separate caches. Per sentence: do the builds agree on the label, the gated tools, and the number of facts? Report an agreement score. | Gives the baseline number. Shows which sentences are unstable. About $0.02 per build. | Measures, fixes nothing. Needs a small change so `sample` is not fixed to 0. |
| 2 | **Fixed fact list, rules built on top** | Stage 1 fixes the fact list. Stage 2 writes rules that may use only those names (an enum in the JSON schema). First test: use the frozen 66 facts as the list. | Removes the naming problem. Builds become comparable by truth table. v4's fact code runs unchanged on any rebuild. | The fact list itself is still one sample, unless voted or approved by a person. |
| 3 | **One small call per sentence** | Each sentence gets its own call, with the headings and the tool list as context. A second pass links exceptions to their rule. | Small outputs vary less. A policy edit re-builds only the touched sentences (goal 3). Also fixes the 32k output limit for long policies. | Breaks the partner's choice T8 (exceptions sit in other sections). The linking pass is new code and new risk. |
| 4 | **Typed facts tied to the schema** | A code fact is not a free name. It is a typed reference: `db: order.status == "pending"`, `arg: len(passengers) <= 5`, `log: get_order_details ran`. Fields come from an enum of the tool and database schemas. | Two builds that mean the same thing write the same thing. The fact's code can be generated, not hand-written. Extends v4's "code or question" sorting into the build. | Needs a small expression language. The 26 meaning facts still need free text. |
| 5 | **Rule templates** | A rule must be one of a few shapes: needs-before, limit, user-must-confirm, identity, never, or-exception. The LLM picks a shape and fills slots. | Much less freedom, so much less variance. Easy to check and to read. | Some policy lines fit no shape. Needs an "other" shape, which brings the freedom back. |
| 6 | **Sample and vote** | Build N times. Per sentence, keep the majority label and the majority rule (by truth table). No majority means: flag the sentence for a person. | The standard fix for sampling noise. The flags find vague policy lines for free. | Needs idea 2 or 4 first, else the samples cannot be matched. N times the cost (still cents). |
| 7 | **Canonical form and solver clean-up** | Put every rule in one normal form. Use a solver to drop rules that another rule already implies, and to find contradictions. | Different samples shrink to the same minimal set. Catches broken builds. | Only helps when the samples differ in form, not in meaning. |
| 8 | **Test cases per sentence** | Per sentence, write a few made-up allowed and forbidden cases (as v4 did for questions, 720 cases). A build passes only if its rules decide every case right. Rebuild failed sentences. | Ties the rules to behavior, not wording. Two builds that pass the same cases act the same on them. | The cases come from an LLM too. Who checks the cases? Selection by test is not "one build is the result". |
| 9 | **Pick the middle build** | Build N times. Keep the one build that agrees most with all the others. No outcome data is used. | Tiny change. The rule set is still a single real build, close to the partner's method. | Still one sample's quirks. Selection among samples breaks the partner's protocol as written. |
| 10 | **A model with a seed** | Run the build on a model that takes temperature 0 and a seed, or on open weights with greedy decoding. | Repeatable without a cache. Cheapest of all. | Goal 1 only. One changed word in the policy can still flip everything. A different model than the rest of the study. |

Two more, kept out of the ten:
- **Rules mined from the tool code.** Some policy lines are already enforced by the tools. Static reading of the
  tool code gives those rules with no LLM at all. Narrow, but fully deterministic.
- **Process, not method.** Freeze the build, have a person approve it, and show a diff on each policy change. This
  is what products do (policy as code). It is what we already do with the freeze.

## 4. The best three

Chosen because they build on each other, cost cents, and keep v4 usable.

### Pick 1: measure stability first (idea 1)
- Nobody has the number. Not the partner, not us, and no paper I found.
- Sentence ids make it easy: agreement per sentence on label, gated tools and fact count.
- It decides whether the other two are worth building. If 9 of 10 builds already agree, the work is small.
- Cost: about 10 builds × 2 domains × $0.02 = about $0.40.

### Pick 2: a fixed, typed fact list (ideas 2 + 4)
- This is where most of the freedom is. Free fact names are why builds cannot even be compared.
- Step one is nearly free: rebuild the rules N times with the frozen 66 facts as the only allowed names. v4's
  fact code then works on every rebuild, so each rebuild can be run offline on saved conversations.
- Step two is the real method: facts as typed references into the tool and database schemas. That also turns
  v4's manual step "write the code facts" into something a build can produce.

### Pick 3: vote per sentence, flag the rest (ideas 6 + 7)
- With a fixed fact list, each sample's rule is a truth table. A majority vote is then well defined.
- Sentences with no majority are flagged for a person. These are likely the vague policy lines, like
  "another person" in v4. That is a useful output on its own.
- The result is a rule set with a stated agreement level per rule.

Why not the others first:
- Idea 3 (per sentence calls) is the right answer for long policies and policy edits. It is the natural step 4,
  but it adds the linking problem. Do it after the vote exists to check it.
- Idea 5 (templates) overlaps with pick 2. Typed facts already cut most of the freedom.
- Idea 8 (test cases) is good as a check, weak as a build rule: the cases are as random as the rules.
- Ideas 9 and 10 give a repeatable build, not a stable one.

## 5. One hard constraint

The partner's method says: one build, no selection, no rule edits. Any of the three picks is a **new build
method**, not frozen TGR. It must be its own arm, with its own name, compared against frozen TGR.
And a new rule set with new facts would need new fact code. Pick 2, step one, avoids that by keeping the 66 facts.

## 6. Has it been done? Is the direction new?

Short search, not a full review. Several items are 2026 preprints that I saw only as summaries.

**The direction "a deterministic guard for agents" is not new.** Close work:

| work | what it does | how it differs from us |
|---|---|---|
| ToolGuard, IBM (EMNLP 2025 industry) | Compiles policy text into Python guard code per tool, offline. Tested on τ-bench airline. | Closest. Guards are generated code. A person curates the policy-to-tool mapping. Reports that code errors, not logic, were the main failure. No dialogue facts. |
| "Reason Less, Verify More" (arXiv, July 2026) | Four hand-written gates that read the database before a write. No LLM. τ²-bench airline. | Hand-written, 4 rules, no rule build, no dialogue facts. Found little gain on retail. |
| AgentSpec (ICSE 2026) | A rule language for agent actions. Rules can be written by an LLM, then reviewed. | General language. Not about a policy document or τ-bench. |
| Autoformalization into policy-as-code, Sondera (ICML 2026 workshop) | LLM drafts Cedar policies from instructions. Deterministic critics and a prover check them. | Access-control style rules. Tested on a medical benchmark. |
| Policy in Amazon Bedrock AgentCore | Natural language to Cedar, checked by automated reasoning. Enforced at the gateway. | A product. The translation is still an LLM step. |
| PolicyLLM (ICML 2026), "Executable Governance" (P2T, arXiv 2512.04408) | Policy text to rules, with schema checks, deduping and solver checks. | Guards model outputs or governance rules, not agent tool calls on a benchmark. |
| ShieldAgent (ICML 2025) | Extracts rules into probabilistic circuits, checks by LLM. | The paper TGR grew from. LLM sets the facts. |
| PolicyGuard (arXiv 2606.29225) | An LLM sub-agent reads the whole dialogue and checks a checklist. τ²-bench airline. | The opposite bet: it argues code facts are brittle for dialogue. v4 sits between it and ToolGuard. |

**What I did not find, so what may be new:**
1. **A measured stability of the rule build.** Papers build rules once and evaluate that build. The nearest are
   AWS's "redundant autoformalization" and a preprint that clusters translations by meaning. I found no paper that
   reports how much an agent guard's rule set changes between builds, or a vote to steady it.
2. **The v4 split itself.** Code sets what code can know. An LLM answers one narrow question on messages picked by
   code, with two keys. On τ-bench I found pure code guards and pure LLM verifiers, not this middle.
3. **The controlled comparison.** Same rules, only the fact values change, with pass marks fixed in advance, and a
   measured judge-versus-code error rate.

Honest reading: the goal is shared with several groups, and ToolGuard is close enough that it must be cited and,
if possible, compared. The new parts are the stability measurement of the build and the code-plus-tiny-question
split. A claim of "first deterministic guard" would not hold. A claim of "first to measure and reduce the
randomness of the rule build itself" might, after a proper literature check.

## 7. Open questions for the user

1. Is the target stable across samples (goal 2), stable across policy edits (goal 3), or both?
2. May we break "one build is the result" in a new, separately named arm?
3. Keep the frozen 66 facts as the fixed list for the first test?
4. Is a ToolGuard comparison arm wanted? Its code is public.

## 8. Round 2: rules only, facts fixed

### 8.1 What changes
- Fixed: the 66 facts, their meanings, and v4's code and tiny questions that set them.
- Rebuilt: only the rules, meaning which tool each rule gates and the logic over the 66 facts.
- So the build input becomes: the numbered policy, the tool list, and the 66 facts as a closed list (names plus
  meanings). The LLM may use no other fact name. That is enforced by an enum in the JSON schema.

This makes the problem much smaller:
- Every rule is a formula over known facts, so it is a truth table.
- Two builds can be compared exactly, per tool, by their truth tables. The largest tool, book_reservation, has 14
  facts, so 2^14 = 16,384 rows: cheap to compare in full.
- "Deterministic" gets a clear test: N fresh builds give the same truth table per tool.

### 8.2 Ideas still in scope
Ideas 2 and 4 are dropped, since they change the facts. Idea 2's core, a fixed fact list, is now the frame for all
the others.

| # | idea | in scope? |
|---|---|---|
| 1 | measure stability | yes |
| 3 | one small call per sentence (or per tool) | yes |
| 5 | rule templates | yes |
| 6 | sample and vote | yes, now well defined (truth tables) |
| 7 | canonical form and solver | yes |
| 8 | test cases per sentence | yes |
| 9 | pick the middle build | yes |
| 10 | a model with a seed | yes |
| new | compare every rebuild with the frozen TGR rules | yes: frozen TGR is the reference |
| new | replay old checks offline: same fact values, new rules, compare the allow/block decisions | yes, $0 if the fact values of each check were saved (to verify) |

### 8.3 The best three, in order

**1. Measure first.**
- Build the rules N = 10 times per domain, with the 66 facts fixed.
- Report three numbers:
  - per tool, the share of builds whose truth table equals the majority;
  - per policy sentence, label agreement (rule, exception, fact, not enforceable);
  - per tool, agreement with frozen TGR.
- Also run 3 free builds (TGR as is) for a baseline. Fixing the facts alone may already remove most of the
  variance.
- Cost: about 26 builds at about $0.02 each, so about $0.50.

**2. Vote by truth table, flag the rest.**
- Per tool, take the majority truth table over the N builds, and write it back as a short rule (a canonical form).
- A tool or sentence with no clear majority (for example below 70 %) goes to a person, with the competing
  versions side by side.
- Check that the result does not drift: a second set of N builds must give the same voted rule set.
- The output is one rule set, plus a stated agreement level per rule.

**3. Small calls with rule shapes.**
- One call per policy sentence, with the headings and the full fact list as context.
- The answer must be one of a few rule shapes, for example "needs fact X before tool T", "never T when X", or
  "T needs (X or Y)". Exceptions are linked in a second pass.
- Small, closed answers vary less. A policy edit rebuilds only the touched sentences.
- Do this only if pick 2 still leaves unstable tools: it is the most new code.

Why not the others:
- Idea 10 (a seed) and idea 9 (the middle build) give repeatable output, not stable output.
- Idea 8 (test cases) is a good extra check, but the cases are as random as the rules.
- Idea 7 (solver clean-up) is folded into pick 2 as the canonical form.

### 8.4 Limits of this scope
- The fact list must exist first. On a new policy it still comes from one TGR build plus a person's approval, as in
  v4's step 3. Only the rules become stable.
- A policy line that needs a fact not on the list cannot become a rule. The build should report such lines
  ("needs a new fact"), not silently drop them.
- The frozen facts were written together with the frozen rules. So rebuilt rules will lean toward the frozen ones.
  That is fine as a reference, but it is not an independent check of rule quality.
- Any rebuilt rule set is a new arm, not frozen TGR (section 5).

### 8.5 Novelty, for this scope
Unchanged from section 6. I found no paper that measures, or votes to steady, the rule build of an agent guard. A
deterministic guard as a goal is shared with ToolGuard and others.

### 8.6 Open questions
1. Is "N fresh builds give the same truth table per tool" the right definition of deterministic?
2. Does a person check the flagged rules, or are they dropped?
3. Is a $0 offline replay enough to judge new rules, or do you want live runs too?

## Sources

- ToolGuard: https://arxiv.org/abs/2507.16459v2 , https://aclanthology.org/2025.emnlp-industry.41 , https://pypi.org/project/toolguard/
- Reason Less, Verify More: https://arxiv.org/pdf/2607.07405
- AgentSpec: https://arxiv.org/abs/2503.18666v1
- Autoformalization into policy-as-code: https://arxiv.org/pdf/2606.26649 , https://icml.cc/virtual/2026/67916
- Policy in Amazon Bedrock AgentCore: https://aws.amazon.com/blogs/security/why-policy-in-amazon-bedrock-agentcore-chose-cedar-for-securing-agentic-workflows/
- PolicyLLM: https://icml.cc/virtual/2026/78632
- Executable Governance (P2T): https://arxiv.org/html/2512.04408v1
- ShieldAgent: https://arxiv.org/abs/2503.22738
- PolicyGuard (dialogue verifier): https://arxiv.org/abs/2606.29225
- PolicyGuard (neuro-symbolic compliance review): https://arxiv.org/pdf/2606.32004
- Stratified Consistency Distillation: https://arxiv.org/pdf/2608.30258
- Policy Loopholes in Agent Evaluation: https://arxiv.org/pdf/2609.14400
