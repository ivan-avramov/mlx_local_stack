# Open questions & judgement calls — the operator's decision queue

Created 2026-08-13 at operator request. **Purpose:** one place for things that need the operator's
judgement, plus decisions already made so they are not re-litigated. Companions:
`docs/campaign-queue.md` (work state), `docs/campaign-results.md` (results), `AGENTS.md` (rules).

**Rules for this file.** An item is added the moment a judgement call is identified, not when it
becomes urgent. An item is either **OPEN** (needs the operator), **CLOSED** (with the decision and
its date), or **CLOSED-BY-MEASUREMENT** (the question dissolved because data answered it — record
the data, because "we decided" and "we measured" age differently). Nothing is deleted; a closed item
is the record that stops it being re-asked.

---

## OPEN — needs operator judgement

### ~~O17~~ → PARTLY CLOSED (operator, 2026-08-14): **drop the n=40 evalplus job — DONE.** But my scoping was WRONG and the residue is bigger; see O18.
The approved job is removed from `docs/work-queue.json`. ⚠️ **I described it as "the last queued job".
It was not.** The runtime state file only lists jobs the runner has already touched (5 of them), while
the PLAN had 10 — so three gemma jobs and two very large winner jobs were invisible to the check I ran.
Reading runtime state and calling it the backlog is the same class of error as reading a run prefix and
calling it the run. **Lesson: the plan is the backlog; the state file is only what has been attempted.**

### ~~O18 (a)~~ → CLOSED (operator, 2026-08-14): **`gemma-4-26B-A4B-it-OptiQ-4bit evalplus n=100` STOPPED.** Measured 201 s/item ⇒ ~11.2 h for an unpairable row, while blocking free grading. 11 rows kept; resumes via `done_ids`. Requeue at n=40 (~2.2 h) only if second-architecture-class coverage is wanted.
⚠️ **My "it might be cheap, it's a fast MoE" caveat was WRONG, and measuring cost 17 minutes.** The plan
entry carried no ETA, unlike its neighbours; the queue's own rule is SIZE EVERY JOB FROM A 5-ITEM PILOT,
and this job had never been sized. 5 items in 16m47s ⇒ 201 s/item ⇒ ~11.2 h. **The runner was stopped
too, not just the job** — otherwise it would have advanced straight into `ifeval n=200 gemma` (~10 h) and
blocked grading all over again. `O18 (b)` below (the remaining queue) is still OPEN.

### O18 (b). gemma CANNOT be compared to the winners at a matched budget — it is ARITHMETICALLY impossible
Raised 2026-08-14 while executing O17, from the registry rather than from old rows:

| model | `thinking_budget` | `max_tokens` | `max_kv_cache_size` |
|---|---|---|---|
| `Ornith-1.0-35B-mlx-uniform-4bit` | 81920 | 102400 | 131072 |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` | 81920 | 102400 | 131072 |
| `gemma-4-31B-it-qat-6bit` | **16384** | 32768 | **49152** |
| `gemma-4-26B-A4B-it-OptiQ-4bit` | **32768** | 49152 | **65536** |

`compare` refuses any comparison differing in `thinking_budget` or `max_tokens`. **And gemma cannot be
raised to match:** the server clamps the budget to `0.8 × (max_kv_cache_size − prompt)`, so
`gemma-4-31B-it-qat-6bit`'s ceiling is `0.8 × 49152 ≈ 39,300` — **less than half** the winners' 81,920.
Matching would require raising its KV cap, i.e. changing the config we ship for it, at which point we are
no longer measuring the deployed model.

**Still queued against that constraint: ~34 h** — `gemma-4-26B-A4B-it-OptiQ-4bit` evalplus n=100,
`ifeval n=200 gemma-4-31B-it-qat-6bit` (~10 h). Plus two large winner jobs whose own names flag them:
`math500 n=100 both winners` (~35 h) and `livecodebench n=100 ×4` (~55 h, "LIKELY TOO EXPENSIVE AS
SPECIFIED").

**The counter-argument, which I think is right and which cuts against a blanket drop:** goal A is to
MEASURE models on dimensions, and a gemma row at gemma's own deployed config measures gemma **as it would
actually be used**. That is legitimate, useful data — it just yields an ABSOLUTE capability number and a
usability verdict, never a paired delta. The refusal is a property of paired statistics, not of the
measurement.

**Options:** (a) **keep the gemma jobs, labelled ABSOLUTE-ONLY** — report them in the scoresheet, never
pair them, and size n from a 5-item pilot; (b) **drop gemma from the coding axis** and spend the ~34 h on
the axes that can resolve something (BFCL, judge-panel reliability, an opencode row for the B pick);
(c) re-run the winners at gemma's budget — rejected, it would misrepresent the winners and cost more.
**Recommendation: (a) for `ifeval n=200`, (b) for `gemma-4-26B-A4B-it-OptiQ-4bit evalplus n=100`.** The
daily-driver dimension has only two models and an absolute third is genuinely informative; the coding
dimension already has an unresolved 2–5pp question between the winners that a ±20pp uncomparable row
cannot help with. **Needs your ruling; nothing is dropped beyond the one job you already approved.**

### ~~O17 (original text, retained)~~ `gemma-4-31B-it-qat-6bit` evalplus is queued at n=40 — but it is UNRANKABLE by construction
The last queued job is `gemma-4-31B-it-qat-6bit evalplus n=40`, deferred earlier today with the note
"10.4h projected for a ±20pp row, 83% of wall in runaways, 1 item lost to a 3600s timeout".

**Two problems, and the second is the decisive one:**
1. **±20pp at n=40** cannot resolve anything the campaign cares about. The winners differ by ~2–5pp on
   coding; resolving that needs 628 matched items.
2. **It runs at `thinking_budget` 16384 while both winners sit at 81920**, and `compare` MECHANICALLY
   REFUSES cross-budget comparisons. So 10.4 h of the single worker buys a row that cannot legally be
   compared to anything already measured. It would sit in the scoresheet as an unrankable cell.

**Options:** (a) **drop it** — 10.4 h back for work that can resolve something; (b) **re-run it at a
matched 81920 budget**, making it comparable but costing more than 10.4 h and re-opening whether gemma
converges at that budget (its `conv%` is already 83% on humanevalplus at 16384); (c) run as-is and
accept an uncomparable row.
**Recommendation: (a) drop it now, and if gemma matters, requeue at a matched budget with an n chosen
from a 5-item pilot.** A row that `compare` refuses is not evidence at any n.

### ~~O16~~ → CLOSED (operator, 2026-08-14): **LEAVE IT.** Deterministic, documented, 0.2% of items. Revisit only if a future axis leans on the affected instruction types.
### O16 (original text, retained). IFEval verifiers INVENT the criterion when a kwarg is absent — leave it, or stop grading those items?
Found and partly fixed 2026-08-14 (`b04030c`). 24 sites in the vendored `instructions.py` fabricate an
**absent kwarg** with `random.choice` / `random.randint` (e.g. `:1350`
`self._frequency = random.randint(1, _LETTER_FREQUENCY)`). Seeding made this **reproducible**; it did not
make it **valid** — for those items the grader checks the response against a threshold it made up.

**Measured scope: 1 verdict of 541 (0.2%), `acc` spread 0.18pp across 8 RNG states.** So this is currently
a hygiene question, not a live number — which is exactly when it is cheap to decide.

**Options:** (a) **leave it** — deterministic, documented, 0.2%; (b) **count those items as verifier
skips** so they leave the numerator AND are counted (the harness already counts skips visibly, so n
would not shrink invisibly) — costs a little n and is the most honest reading; (c) supply the upstream
IFEval defaults explicitly instead of drawing them, if upstream defines any.
**Recommendation: (a) leave it, with the note standing in the lab notebook.** At 0.2% the cure costs more
clarity than the disease, and (b) would make our `acc` non-comparable with published IFEval numbers.
**Revisit if a future axis leans on the affected instruction types** (`keywords:letter_frequency`,
`length_constraints:number_sentences`, and the other threshold-bearing ones).

### O15. Does prealloc actually reserve RAM? — MY EVIDENCE WAS INVALID; the question needs a DEPTH test
⚠️ **I raised this on a measurement that cannot support it, and the operator caught it.** I compared
`mx.get_peak_memory` across prealloc arms (25.35 / 25.50 / 28.18 GB) and inferred the reservation was
"lazy or unwired". **But the probe item generated only ~2,868 tokens, so the KV cache never grew past
~3K of a 131072/262144 capacity.** A virtual allocation that is never touched costs no resident pages,
so those peaks measured weights-plus-a-tiny-cache in all three arms. The ~2.8 GB delta is not evidence
of anything about the reservation.

**Operator datum that outranks my inference: an actual OOM was hit in testing.** So the double-buffer
growth spike is real and the protection matters in practice.

**The test that would actually answer it** — and the only one that should be cited on this — is a
LONG-CONTEXT run that grows the cache to the full cap:
- drive a prompt/generation to >128K so the 128K→256K growth boundary is crossed;
- sample `mx.get_peak_memory` AND resident memory as it grows, prealloc ON vs OFF;
- expect, if prealloc works: a large step at LOAD (or first touch) and NO spike at the boundary; if it
  does not: a small load footprint and a ~1.5× spike at the boundary, i.e. the OOM path.
**Recommendation: do NOT change prealloc, and do not cite peak-memory numbers from short-generation
probes for anything memory-related.** The 46GB gate is defined on the prefill spike for exactly this
reason — a short probe cannot see it.

**Standing lesson: a memory measurement is only valid at the depth it claims.** Every arm of my OFAT
was ~3K tokens deep, so it was a fair test of "is the shipped config slow on a short item" (which is
what the retracted claim was about, and it answered it) and NOT a test of anything at capacity.

### ~~O14~~ → CLOSED-BY-MEASUREMENT. The throughput concern DID NOT REPRODUCE; the rule stands
I reported a **>47× slowdown** at `262144/262144` (a matched item not completing in 19.5 min vs 24.8 s
at `131072/131072`) and wrote it into `AGENTS.md` as a challenge to the prealloc rule. **A 3-arm OFAT
falsifies it.** Same item (`HumanEval/146`), same model/sampling, router restarted per arm:

| cap / prealloc | wall | decode | peak mem | pressure warns |
|---|---|---|---|---|
| 131072 / 131072 | 24.7 s | 98.5 tok/s | 25.35 GB | 0 |
| 262144 / 131072 | 25.0 s | 103.1 tok/s | 25.50 GB | 0 |
| **262144 / 262144** (shipped) | **27.8 s** | **104.5 tok/s** | 28.18 GB | 1 |

**All three are fast.** The shipped config is not slow, peak memory is far under the 46GB gate, and
the operator's rationale — prealloc is what makes 256K reachable at all, because growing 128K→256K
requires holding 384K of KV during the double-buffer — stands unchallenged.

**The original 19.5-minute non-completion is UNATTRIBUTED and treated as a transient.** Most likely
environmental: that run began with ~21GB already in use by other processes and swap already active
(router logged `System memory: 68.7GB total, 47.8GB available`, then
`memory.pressure.warn ram_percent=76.9`), against a cleaner box now.

**Process lesson, worth more than the result:** one dramatic observation, on ONE item, with TWO
variables moved at once, is a hypothesis. I wrote it up as a finding, put a warning into `AGENTS.md`
against a rule that prevents a known OOM, and reduced the registry on that basis. The OFAT cost 4
minutes and should have come first. (The registry change to 131072 is retained for an unrelated and
VALID reason — it is the tightest cap that keeps the declared 81,920 thinking budget in force with no
clamp — but the evalplus H2H therefore ran at a right-sized benchmark cap, not the shipped one, and
peak memory shows there was never a memory reason to reduce it.)

### ~~O13~~ → CLOSED (operator, 2026-08-14). My framing was WRONG; the config is self-consistent
I claimed `max_tokens: 102400` "exceeds the usable context" because at a 250K prompt the resolved
thinking budget collapses to 9,708. **Operator correction: 256K of context is a TOTAL budget — prompt
+ thinking + output — so a 250K prompt was never a supported configuration.**

Working it through with the shipped numbers: `thinking_budget` 81920 is exactly `0.8 × 102400`, and the
clamp yields the full budget while `0.8 × (262144 − prompt) ≥ 81920`, i.e. **prompt ≤ 159,744**. So
~160K is the DESIGNED maximum prompt, `max_tokens` and the 0.8 ratio agree, and **the clamp firing above
~160K is correct, intended behaviour rather than a defect.** Lowering `max_tokens` or `thinking_budget`
(my options 1 and 2) would have solved a non-problem at the cost of capability.

**What remains genuinely wrong is narrower — documentation and guard-rails, not the values:**
1. **The per-model max prompt is written down nowhere.** 159,744 for
   `Ornith-1.0-35B-mlx-uniform-4bit` is derivable but undocumented, and it is LOWER for
   `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, which wants a bigger thinking budget. Nobody can respect a
   limit they cannot look up. **→ record the derived max prompt per model in the registry.**
2. **The clamp is silent** while its sibling `max_tokens` clamp logs a warning. That silence is what let
   33 IFEval rows score as converged. **→ one-line fork fix to log it.**
3. **Benchmarks have no preflight against it.** A long-context axis feeding a 200K prompt would silently
   measure a shrunken thinking budget. **→ assert `prompt ≤ documented_max_prompt(model)`.** Unlike the
   `max_tokens ≤ cap` invariant I withheld, this one does NOT fail against the shipped config, so it can
   land honestly.

### ~~O12~~ → CLOSED (operator, 2026-08-14): **RE-RULED AS BUDGET HITS — these are NOT converged responses.**
M1 (2026-08-13) ruled the degenerate-loop rows "NOT a DNF... a valid converged response — converged as
determined by the MODEL", turning on item 2849 sitting at **"64% of budget"** (52,503 / 81,920) with
`finish_reason "stop"`.
**Against the budget actually in force that row is at 100.2%** — `int((65536 - 42) * 0.8) = 52,395`. It
is a budget hit. The model did not determine it was done; `ThinkingBudgetCriteria` force-injected
`</think>` and the model then wrote its answer, which is exactly why `finish_reason` read `"stop"`.
Reclassified: of 40 flagged loops, **25 + 8 are clamped budget hits, 4 + 2 are `max_tokens`
truncations, and 1 is genuinely self-terminating** (Ornith id 3748, 8,228 tokens).
**What is unchanged:** the answers still verify, so `acc` is unaffected (90.0% / 89.9%), and the IFEval
"the two winners are EQUIVALENT" headline survives — both arms moved the same way.
**What changes:** these rows are non-converged, so AGENTS.md's standing rule applies in full — a
persistent budget hit is a FAIL SIGNAL and the knob is temperature. `acc_strict` drops 89.8% → 86.7%
(Ornith) and 88.5% → 85.1% (distill).
**Recommendation: re-rule them as budget hits** (which the harness now does automatically, `aca967b`),
and keep the M1 *principle* — a genuinely self-terminating loop is not a DNF — since it was correct and
now applies to exactly one row. **This also un-blocks O9 in a smaller form:** the judge-panel question
about looped-but-correct answers now has an n of 1, so it is not worth panel time.

### ~~O11~~ → CLOSED-BY-MEASUREMENT. Premise falsified: the loops do not self-terminate
O11 asked whether to chase the degenerate-loop tax (42% / 57% of IFEval wall-clock) ahead of P4, on the
basis that these were "verbatim repetition loops that SELF-TERMINATE under budget and answer
CORRECTLY", i.e. a pure cost problem fixable by sampling.

**Measured 2026-08-14: 39 of the 40 rows are EXTERNAL TRUNCATIONS, not self-terminations.** The server
silently clamped the declared 81,920 thinking budget to ~52,390, and the harness compared against the
declared value — so a forced `</think>` scored as a clean stop. Genuinely self-terminating share of
wall-clock: **0.3% (Ornith) and 0.0% (distill)**, versus the 42% / 57% the item was raised on.

| | Ornith | distill |
|---|---|---|
| clamped budget-hits | 25 | 8 |
| `max_tokens` truncations | 4 | 2 |
| **genuinely self-terminating** | **1** | **0** |

**The cost is still real** (2.5h and 3.6h of wall-clock) — the *attribution* changed, and with it the
intervention. This is no longer "find the sampling setting that stops a self-verification loop"; it is
AGENTS.md's standing case: a model persistently hitting a generous budget → run the TEMPERATURE LADDER
on the offending items. That is a different experiment with a different success criterion, so O11 as
specified is answered rather than deferred. The design constraints attached to it (vary sampling on the
SAME loop-triggering ids; never the untruncated config; no `min_p` cells below temp 0.4) all still hold
for whatever replaces it. Successor questions: **O12** (the ruling), **O13** (the config), **O14** (the
prealloc rule).
⚠️ **Two blockers remain for any successor probe, both unbuilt:** `generate` has **no id filter**, so
"vary sampling on the SAME items" is not executable; and there is no `presence_penalty` /
`repetition_penalty` override (only `--max-tokens`, `--temp`, `--thinking-budget`). Both small, both
free. Also unverified: AGENTS.md claims a nonzero `presence_penalty` disables suffix decoding — I found
no such gate in the fork, only the structured-output one at `generation.py:1750`. Measure before
designing a penalty cell.

### ~~O11 (original text, retained)~~ Investigate the degenerate-loop tax BEFORE P4? (largest unclaimed speed win on the board)
Measured on IFEval 2026-08-13, and it is not a small effect:

| | `Ornith-1.0-35B-mlx-uniform-4bit` | `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` |
|---|---|---|
| loops | 30/541 (5.5% of items) | 10/148 (6.8%) |
| **share of wall-clock** | **42%** (2.5h of 6.0h) | **57%** (3.6h of 6.3h) |
| healthy → loop, mean wall | 25s → 303s (**12×**) | 71s → 1,283s (**18×**) |
| healthy → loop, mean tokens | 2,655 → 52,911 | 2,028 → 55,274 |
| **recoverable if fixed** | **2.3h of 6.0h (~38%)** | **3.4h of 6.3h (~54%)** |

`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` is worse not because it loops more often (6.8% vs 5.5%) but
because it decodes at **28 tok/s against Ornith's 106**, so the same ~53K-token loop costs ~21 min
instead of ~5.

**For scale:** every Phase-2 speed lever combined was ~1.27× (suffix) plus ~2–7% (GQA kernel). This is
potentially **1.6–2.2× on real workloads** — larger than everything Phase 2 shipped, and the Tier-0
machinery to test it already exists.

**Mechanistic hint, which the test must respect:** loops concentrate on *counting* instructions
(`change_case:capital_word_frequency` **33%** vs a 4.5% base rate) — the model enumerates candidates to
verify its own output. That is the same pathology AGENTS.md records for the synthetic `aggregation`
word-tally task, now seen on a published benchmark. So it may be **prompt-triggered rather than purely a
sampling artifact**, and a temperature sweep alone cannot distinguish those. Design the probe to vary
sampling on the SAME loop-triggering items (the 30 + 10 ids are recorded in `degenerate_eosed_ids`).

⚠️ **Do not conflate with quality.** These answers are CORRECT — item 2849 passed both verifiers after
52,503 tokens of a two-line cycle. This is a COST question; the ruling that they are not DNFs stands (M1).

**Recommendation: yes, ahead of P4.** It is cheap, reuses existing tooling, targets the campaign's
stated speed goal, and P4's own cost estimate (~28h) is inflated by exactly this tax — so fixing it first
makes P4 cheaper too.


### ~~O10~~ → CLOSED (operator, 2026-08-14): **option 3.** `acc` keeps its historical meaning so published rows stay comparable; `acc_strict` carries the don't-grade-a-truncation semantics.
Raised by the operator's instruction to "call it DNF and **not grade it**" (2026-08-13). Half of that is
implemented, half is not:
- `converged: False` ✓ — the row IS marked, and a budget hit already fails the ratified formula.
- **but `acc` still includes it.** AGENTS.md fixes `acc` as "correctness over generated items
  (historical meaning)". The metric that zeroes truncated draws is `acc_strict` — and AGENTS.md
  explicitly forbids `acc_strict` as the ranking key, because it rises monotonically with
  `thinking_budget`, so a 5× budget spread would masquerade as capability.

So "don't grade it" collides with a ratified rule, and there are three coherent options:
1. **Status quo:** `acc` includes it, `acc_strict` zeroes it, both reported. (What AGENTS.md says now.)
2. **Drop from the denominator:** exclude non-converged rows from `acc` entirely. Cleanest reading of
   the operator's principle — but it makes `acc` non-comparable with every historical row, and a model
   that truncates often would be scored on a smaller, easier subset (the same bias that the nltk
   `punkt_tab` skip produced: 21% dropped moved acc 93.3% → 90.2%).
3. **Report `acc` over converged items only, as a NAMED metric** (`pass@1|converged` already exists and
   is computed), keeping `acc` historical.
**Recommendation: option 3.** It gives the operator's semantics an honest name without silently
redefining a metric that historical rows are published under, and it avoids option 2's
smaller-easier-subset bias. **NOTE:** no row in the IFEval run exceeded the thinking budget (0 of 220),
so this is currently a rule-hygiene question rather than one affecting a live number.


### ~~O1~~ → CLOSED, see C10
Not a design question so much as "may I fix these", but both mislead a reader on every run:
- **`grade.py` prints a retracted decision rule.** `CONV_GATE = 0.90` is still live and the scoreboard
  footer prints *"DECISION RULE (pre-registered): conv% >= 90 is a GATE; pass@1|conv RANKS within it."*
  AGENTS.md records that gate as **WITHDRAWN — unratified and unsound** (quantized in n; a point
  estimate against a hard threshold; ~10× too lenient on cost grounds). So every run prints a
  withdrawn rule while calling it pre-registered, and `conv_gate_pass` is still computed from it.
- **`run.py` mislabels its own sampling.** It prints `[params] using per-model production params
  (model_params.py)` immediately before `[generate] sampling profile = deployed`. The manifest proves
  `deployed` is what is used, so this is a stale log line — but "production" vs "deployed" is exactly
  the distinction that decides whether a run measured what we ship, so it is a dangerous thing to
  print wrongly.
**Recommendation:** fix both; replace the footer with the vector-reporting language AGENTS.md
actually ratifies. **Cost:** small, TDD-able, no model time.

### ~~O2~~ → CLOSED, see C11
P3 asks whether the cheap convergence screen predicts the agentic axis. Two measured problems:
- **`conv%` has no variance to correlate.** Tier-0 rev A: 33/33 converged. Rev B: 66/66. Spearman ρ on
  a constant vector is *undefined*, not weak.
- **The other half of the correlation does not exist.** P3 correlates the screen against per-config
  *agentic* results, and P4 has not run.
A ρ on median reasoning tokens is still computable — but see O3.
**Recommendation:** cancel P3 as specified; if a proxy is wanted, re-specify it on reasoning-token
cost and run it *after* P4 produces the other half. **Needs:** operator ruling, since P3 is in the
ratified plan.

### ~~O3~~ → CLOSED (delegated), see C14
Rev A's Ornith arm used `aggregation`@8K; rev B used `vartrack` (the swap that made a cell 2m04s
instead of >2h). Rev B is internally consistent across both models, which is what P2 needed, but the
two revisions cannot be pooled.
**Recommendation:** accept rev B as the record and leave rev A as a superseded row — its answer ("no
knee for Ornith") is unchanged by the task swap. Re-running rev A on vartrack costs ~4 min if you want
strict comparability. **Needs:** a ruling on whether the campaign record keeps both.

### ~~O4~~ → CLOSED (delegated), see C15
40 matches your stated failure ("turn 40, 180K context"). Session cost is O(turns) — measured, since
the session cache prefills only new tokens — so 40 turns is ~6 min/session on Ornith and ~21 min on
Qwen3.6-27B-Opus-Distill-OptiQ-4bit.
**Recommendation:** pilot at 12 turns, measure, then choose from data rather than from the prior.

### ~~O5~~ → CLOSED (delegated), see C16
The dependent-task sequence keeps a **mechanical** oracle (accumulated tests re-run every turn). One
realistic feature is more lifelike but partial credit becomes a judgement call, and the judge panel is
already recorded as not reliable enough to rank.
**Recommendation:** dependent-task sequence, for the mechanical oracle.

### ~~O6~~ → CLOSED, see C12
The fused GQA tile-reuse decode kernel is on by default and its precondition holds for both winners
(even `n_repeats`), but `_decode_2pass_use_legacy` occurs in exactly **one** place in the fork — the
`getattr` that reads it. Nothing sets it, so the claimed "1.3× over legacy TQ, +2–7% end-to-end"
**cannot be A/B'd at runtime**.
**Recommendation:** add the hook (parent fork + submodule bump). It is the only way this lever is ever
auditable, and the APC episode is the argument for doing it. **Cost:** small fork change, needs a
submodule bump and a redeploy.

### ~~O7~~ → CLOSED (delegated), see C17
`configgen/emitters/vscode.py:11` emits `_generated` into a JSON **array element** for a different
consumer (VS Code Copilot BYOK / Roo Code). The opencode case was fatal; this one is untested. Not
assumed broken.
**Recommendation:** verify against the actual consumer before touching it — a needless change to a
working carrier is its own risk.

### ~~O8~~ → CLOSED, see C13
All ready, none run: **judge panel v3** (`judge_extract.py`, dry-run clean at 43 both-solve pairs),
**BFCL live smoke** (request fix landed; whether `<think>` appears needs verifying, since that path
posts a pre-formatted prompt to `/v1/completions` and bypasses the chat template), **SWE-bench**
(built, never run). Plus P4/Tier-1 agentic tuning.
**Recommendation:** BFCL live smoke first — cheapest, and it is the only powered axis the campaign owns
(0.94 vs 0.749 at n=1000 is ~12σ). Then judge panel v3. SWE-bench last; it is the largest build.

### ~~O9~~ → CLOSED (operator, 2026-08-14): **DROPPED.** After the O12 reclassification exactly ONE row is genuinely looped-then-correct, so there is nothing to compare and no panel time is warranted.
Falls out of M1. Four rows on the IFEval run are execution-passing but reached the answer through a
degenerate loop (ids 2849, 279, 3608 line/content-level; 3188 also truncated). They are eligible for
the judge panel by the campaign's own rule — execution-passing outputs — and `is_degenerate` marks them
for attention.
**Why it is worth asking:** a 2,071x loop plausibly correlates with a worse ANSWER even when the
verifier passes; if it does not, that is equally informative, because it would mean reasoning-trace
pathology is invisible in output quality and is therefore purely a cost concern after all.
**Blocked on:** the panel's reliability (recorded as "NOT RELIABLE ENOUGH TO RANK" at v2), so this needs
the panel-reliability work first — or it can only ever be suggestive.
**Recommendation:** hold until the panel is trustworthy; do not spend model time on a comparison whose
instrument cannot carry it.

---

## CLOSED-BY-MEASUREMENT

### M1. Should `converged` absorb self-terminating repetition loops? — **NO** (2026-08-13, operator-confirmed)
**Operator ruling: this is NOT a DNF. It is a valid converged response — converged as determined by the
MODEL — and it is recorded and evaluated for quality like any other row: correctness AND subjective
quality.**

The operator's principle — *exhausting the thinking budget is a failed run, because we interrupted the
model rather than it deciding it was done* — is correct **and already the implemented rule**:
`converged = finish_reason=="stop" AND completion_tokens < thinking_budget`, so a budget hit is already
not converged, and AGENTS.md already calls it a fail signal. (Terminology: **EOS = end-of-SEQUENCE**,
the model's own stop token — not end-of-session. My jargon caused the confusion.)

Item 2849 was **not** a budget exhaustion: 52,503 tokens at **64% of budget** with `finish_reason
"stop"`, i.e. the model stopped itself, and its answer **PASSED both strict and loose** verifiers
(`benchmark/m1/inspect_item.py`) — a valid 276-char answer. The work was complete by the model's own
decision, so marking it DNF would **discard a valid result**, the opposite error to the one the budget
rule guards against.

⚠️ **REFINEMENT (2026-08-13, correcting my own framing).** I called this "a COST defect, not a
correctness one". That is accurate but INCOMPLETE, and the incompleteness matters: what was actually
measured is only the cost half (271 s and 52,503 tokens for 276 chars). Whether a model that loops
2,071 times before answering produced *good work* is a question the instrumentation cannot answer, and
"correctness passed, so it is fine apart from the tokens" must not stand in for it. Per the campaign's
instrumentation rule, subjective quality belongs to the blind mixed-family JUDGE PANEL over
execution-PASSING outputs — and this row is exactly such an output, so it is **eligible, not exempt**.

**So `is_degenerate` is a FLAG FOR THE JUDGE PANEL'S ATTENTION, not a verdict.** Consequences:
- These rows stay in `acc` and in the item set. **No exclusion, no reweighting, no DNF.**
- `degenerate_wall_share` / `degenerate_token_share` remain reasoning-token COST, reported beside
  capability and never folded into it.
- The open question becomes **O9** below: does the panel rate looped-then-correct answers differently
  from directly-correct ones? Better question, and answerable.
- ⚠️ Caveat: the judge panel is on record as **"NOT RELIABLE ENOUGH TO RANK"** (v2, two runs). It can
  raise a signal here; it cannot settle it, and a panel result on this must not be presented as
  decisive.

### M2. How do APC and session caching compose? — **THEY DON'T** (2026-08-13)
Mutually exclusive per request: `generation.py:2455-2464` dispatches any request with a
`prompt_cache_state` to `_process_cached_request` and `continue`s past the BatchGenerator, the only
site passed `apc_manager`. Anonymous requests resolve to a session by chained message hashes, so all
of our traffic takes the session path and APC is never consulted (measured: 0 lookups, 0 stores, 0
resident bytes; peak memory bit-identical to APC-absent). Session caching is what makes multi-turn
cheap (measured: cost per NEW token flat, cost per TOTAL token −17×).

### M3. Does APC cost memory that could disqualify a candidate? — **NO** (2026-08-13)
It consumes nothing because it does nothing (see M2). Constraint satisfied, for the wrong reason.

---

## CLOSED — operator decisions

| # | question | decision | date |
|---|---|---|---|
| C1 | Push the local commits, and how to keep boxes in sync | **Push; git is the ONLY cross-box transport** (rule in AGENTS.md; scp banned except throwaway `/tmp` diagnostics) | 2026-08-13 |
| C2 | Keep APC enabled for the daily driver? | **No — off everywhere**, including `runserver.sh`. Guarded by a test | 2026-08-13 |
| C3 | Drop the `_generated` key from opencode's config? | **Yes** — done TDD-first; the unmodified generated config now loads on M5 | 2026-08-13 |
| C4 | Fix `run.py`'s CWD fragility? | **Yes** — `bench/paths.py`, same absolute paths as before, verified from the wrong CWD | 2026-08-13 |
| C5 | Derive the request timeout from the decode rate? | **Yes**, with a hard ceiling and loop/meander detection | 2026-08-13 |
| C6 | Re-verify Phase-2 suffix / GQA claims? | **Yes** — suffix confirmed real (1.27×); GQA on-by-default but unfalsifiable (see O6) | 2026-08-13 |
| C7 | Trim the IFEval distill arm for time? | **No — run it full**; timing is not a constraint | 2026-08-13 |
| C8 | Cadence for benchmark runs | **Report AND critically evaluate every 5 min** (rule in AGENTS.md, four required questions) | 2026-08-13 |
| C9 | Multi-turn eval: one benchmark or two? | **Two targeted benchmarks**, coder + daily driver, one shared spine | 2026-08-13 |
| C10 | Fix the two stale outputs (O1)? | **Yes** — DONE. Footer now states AGENTS.md's ratified four-number rule; conv% labelled a DIAGNOSTIC; the `gate PASS/FAIL` COLUMN removed (it contradicted the footer above it); `run.py` now names the actual sampling profile | 2026-08-13 |
| C11 | Cancel P3, the ρ proxy validation (O2)? | **CANCELLED.** ρ on `conv%` is undefined (66/66 converged = a constant vector), and the agentic half does not exist until P4 runs. If a proxy is wanted later, re-specify on reasoning-token cost AFTER P4 | 2026-08-13 |
| C12 | Add the `TQ_DECODE_2PASS_LEGACY` hook (O6)? | **Yes** — DONE. Fork `8b7100b8` + submodule bump `3f85279`, deployed and verified live on M5 (default False, env=1 True). Default behaviour unchanged; the A/B itself is separate worker time and not yet run | 2026-08-13 |
| C13 | Axis sequencing after IFEval (O8)? | **P4 → BFCL → judge panel → SWE-bench** | 2026-08-13 |
| C14 | Tier-0 rev A vs rev B record (O3)? | Delegated → **accept rev B as the record, rev A marked superseded.** Its answer ("no knee for Ornith") is unchanged by the task swap, so a 4-min re-run buys only strict poolability | 2026-08-13 |
| C15 | Multi-turn B depth: 40 or 24 (O4)? | Delegated → **pilot at 12 turns, choose from measured cost.** Sizing from a prior is what killed Tier-0 rev A | 2026-08-13 |
| C16 | Multi-turn A construct (O5)? | Delegated → **dependent-task sequence**, to keep a mechanical oracle; one realistic feature makes partial credit a judgement call the judge panel cannot yet carry | 2026-08-13 |
| C17 | `vscode.py` `_generated` (O7)? | Delegated → **verify against the real consumer before changing anything.** A needless change to a working carrier is its own risk | 2026-08-13 |
| C18 | Judge panel on looped answers (O9)? | Delegated → **HELD** until the panel is reliable ("NOT RELIABLE ENOUGH TO RANK" at v2). Do not spend model time on a comparison whose instrument cannot carry it | 2026-08-13 |
