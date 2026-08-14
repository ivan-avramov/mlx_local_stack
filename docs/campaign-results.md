# Campaign Results — the USE-CASE LEADERBOARD (living)

**WHAT THIS IS.** A **reusable benchmark suite** and its current standings. The deliverable is not a
verdict about which model is best — it is apples-to-apples comparisons that stay valid as new models
arrive. This is never "done": models ship constantly, get run through the same suite, and take their
place in the table below. **Selection happens per USE CASE**, at the moment someone asks "what should I
use for coding?" or "what should I use for deep research?" — so that is how the standings are organised.

Thinking is ENABLED for all tests. No model is pruned on partial results.

---

## ⭐ CURRENT STANDINGS BY USE CASE — updated 2026-08-14

**How to read this.** A pick is a recommendation on CURRENT EVIDENCE at the stated n, not a claim of
superiority. Where the capability comparison is unresolved, the pick is made on a secondary axis and
that is stated. **NOT MEASURED means exactly that** — never inferred from a neighbouring axis.

| use case | winner | runner-up | decided on | confidence |
|---|---|---|---|---|
| **Agentic coding** (multi-turn, edits a repo) | `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` | `Ornith-1.0-35B-mlx-uniform-4bit` | aider polyglot n=110: `final` **73.6% vs 50.0%**, McNemar **p=1.3e-05**; mechanism is REPAIR (60.8% vs 33.7%), not raw capability | **HIGH** — the campaign's only powered result. ⚠️ aider-scaffold-specific; ZERO opencode evidence |
| **Single-shot code generation** (write one function) | `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` | `Ornith-1.0-35B-mlx-uniform-4bit` | humanevalplus n=100 matched: `acc_strict` **95.0% vs 90.0%**; `acc` delta −2.0pp CI [−5.0,+0.0] **INCONCLUSIVE** | **LOW** — capability unresolved (628 items needed). Picked on `acc_strict`, whose gap IS attributable: Ornith forfeits 3.0pp to truncation |
| **Interactive daily driver** (chat, follows instructions) | **TIE — either** | — | IFEval paired n=148: 89.9% vs 89.9%, gap **+0.0pp**, `equivalent` | **MEDIUM** — a real equivalence verdict, not an inconclusive one. Pick on latency: Ornith is 3.8× faster to decode |
| **Fast interactive feel** (lowest latency per turn) | `Ornith-1.0-35B-mlx-uniform-4bit` | `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` | humanevalplus n=100: median **18 s vs 21 s**, p95 **106 s vs 126 s**, decode **107.6 vs 28.6 tok/s** | **HIGH** — same box, same session, matched items |
| **Math / symbolic reasoning** | ⚠️ **UNRESOLVED** | — | math500 n=30: `acc` 83.3% vs 81.5% (tie) but `acc_strict` **60.0% vs 81.5%** at a matched budget — Ornith hits the budget on 9/30 | **LOW** — n=30 is ±23pp. The `acc_strict` split is large and mechanistic; needs n≈100 |
| **Long-context work** (>128K prompts) | ⚠️ **NOT MEASURED as a task** | — | Capacity/retrieval ladders only. `Ornith-1.0-35B-mlx-uniform-4bit` 262K @32.4GB, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` 262K @43.3GB — both CLEAR the memory gate | **NONE** for task quality. ⚠️ And see the thinking-budget clamp: at a 250K prompt the resolved budget collapses to 9,708 |
| **Deep research** (long multi-source synthesis) | ⚠️ **NOT MEASURED** | — | no axis exists | **NONE** — needs a benchmark built. Nearest proxies: long-context retrieval + instruction retention, neither run at depth |
| **Tool calling / function calling** | ⚠️ **NOT MEASURED** | — | BFCL harness repaired but NEVER RUN | **NONE** — cheapest powered axis available (0.94 vs 0.749 at n=1000 is ~12σ) |
| **Repo-scale engineering** (SWE-bench-like) | ⚠️ **NOT MEASURED** | — | harness built, never run | **NONE** |

### Cross-cutting cost finding that applies to EVERY use case
**~40% of wall-clock is lost to turns that never self-terminate**, on BOTH models, measured at a
genuinely-in-force budget: `Ornith-1.0-35B-mlx-uniform-4bit` 3/100 items = **42%** of wall-clock;
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` 1/100 = **39%**. The rates differ 3× but the cost is the same,
because the slower decoder loses as much to one 33-minute item as the faster one loses to three
10-minute items. **This is the largest single lever the campaign has measured** — bigger than everything
Phase 2 shipped (1.27× suffix + 2–7% GQA) — and it is not model-specific, so it is a property of the
suite's operating point, not a tiebreaker between candidates.

### What would move these standings, in order of value
1. **The runaway-tax probe** (temperature ladder on the known runaway items) — ~40% of wall-clock, ~90 min.
2. **BFCL** — fills an empty use case, and is the only powered axis the suite owns.
3. **math500 at n≈100** — the `acc_strict` split is 21pp and currently unresolvable at ±23pp.
4. **A deep-research axis** — an entire declared use case with no benchmark behind it.
5. **opencode agentic evidence** — the agentic pick is aider-scaffold-specific.

### ⚠️ COMPARABILITY RULES THAT GOVERN EVERY ROW ABOVE
- **BOX TOPOLOGY CHANGED 2026-08-11 — the M2 Max 64GB is GONE**, replaced by an M4 Pro 48GB DRIVER
  that hosts NO models. **All model runs are M5 Max runs.** Every `M2` row further down is HISTORICAL
  and NOT re-measurable (apples-to-apples bars cross-box baselines and the box no longer exists), so
  it can inform a hypothesis but never a use-case pick.
- **A pick requires: same box, same session, matched items, matched `thinking_budget`, and the
  `deployed` sampling profile.** `compare` mechanically refuses comparisons that differ in
  `thinking_budget` or `max_tokens`.
- **Every delta carries its interval and the axis MDE.** "Inconclusive" is a valid and expected
  answer; it is NOT evidence of a tie.

### Candidates measured so far
17 model directories, but only three are measured beyond n=10:
`Ornith-1.0-35B-mlx-uniform-4bit`, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, `gemma-4-31B-it-qat-6bit`.
Everything else is n=3–10 (±40–72pp) and cannot support any use-case pick. Per-model coverage:
`PYTHONPATH=benchmark .venv-bench/bin/python benchmark/m1/scoreboard.py`.

⚠️ **`gemma-4-31B-it-qat-6bit` is excluded from every pick above on comparability, not on quality:** it
runs at `thinking_budget` 16384 vs the others' 81920, and `compare` refuses cross-budget comparisons.
Its 192K context ceiling is a config fact, not a zero.

---

## 🏁 THE H2H — humanevalplus n=100, BOTH winners, matched items, `deployed`, current box (2026-08-14)

The campaign's first matched, current-box, `deployed`-profile, execution-gated coding comparison.
Same 100 items in the same order, same box, same session, cap 131072 so the declared 81,920 thinking
budget is genuinely in force. Reported as AGENTS.md requires — four separately-interpretable numbers,
no composites.

### 1. Capability — INCONCLUSIVE

| | `Ornith-1.0-35B-mlx-uniform-4bit` | `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` |
|---|---|---|
| `acc` | 93.0% [87,98] | **95.0%** [90,99] |
| **`acc_strict`@81920** (ranking key) | 90.0% | **95.0%** |
| `conv%` | 97% | **99%** |
| `nonconv_kinds` | `degenerate_repetition:3` | `degenerate_repetition:1` |

**`compare` paired on all 100 items: delta −2.0pp, 95% CI [−5.0, +0.0]pp, VERDICT `INCONCLUSIVE`.**
Not a tie — too little data. Resolving a 2pp difference needs **628 matched items**. Axis MDE ±13pp.
⚠️ `compare` flags that temperature differs (0.4 vs 0.3) — expected, each model at its own tuned
operating point, but it means this is a (model × tuned-config) comparison, not a pure model contrast.

**The `acc_strict` gap of 5.0pp is MECHANISTICALLY ATTRIBUTABLE, and it is the more decision-relevant
number:** Ornith loses 3.0pp between `acc` and `acc_strict` because 3 of its passing items were
externally truncated; `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` loses nothing, because its one degenerate
item self-terminated. At a matched budget, Ornith forfeits capability to non-termination that the other
model does not.

### 2. Edit competence
0 errors, 0 harness failures, both arms. Not separable on this axis.

### 3. Latency

| | Ornith | distill |
|---|---|---|
| **total wall-clock** | **69.4 min** | 85.1 min |
| mean / item | **42 s** | 51 s |
| median / item | **18 s** | 21 s |
| p95 | **106 s** | 126 s |
| max | 622 s | **1,999 s (33 min)** |
| median completion tokens | 1,850 | **606** |
| decode rate | **107.6 tok/s** | 28.6 tok/s |

**⇒ Ornith is faster on EVERY latency statistic at n=100** — total, mean, median and p95 — despite
emitting 3.1× more tokens per item, because it decodes 3.8× faster.

### 4. Runaway tax — ~40% of wall-clock for BOTH, which is the headline

| | Ornith | distill |
|---|---|---|
| non-self-terminating rate | 3/100 = **3%** | 1/100 = **1%** |
| **share of WALL-CLOCK** | **42%** | **39%** |
| share of tokens | 49% | 49% |
| mechanism | 3 items × ~10 min | **1 item × 33 min** |

**⇒ The tax is NOT model-specific: both winners lose ~40% of wall-clock to turns that never
self-terminate.** The rates differ 3× but the cost lands in the same place, because
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` decodes 3.8× slower, so ONE runaway item costs it what three cost
Ornith. This is the single largest performance lever the campaign has measured — larger than everything
Phase 2 shipped (1.27× suffix + 2–7% GQA).

### ⚠️ THIS SUPERSEDES A PROVISIONAL n=36 FINDING OF MINE THAT WAS WRONG
At n=36 the prefix showed `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` finishing in 19.2 min against Ornith's
34.5 — a 1.8× advantage — and I recorded that "Ornith is the fast one" is statistic-dependent. **It does
not survive to n=100 and the direction reverses.** The stated caveat is exactly what happened: the item
in flight at the time WAS a budget-runner, and at 1,999 s it single-handedly flipped the totals. Kept
here as a record, because it is a clean demonstration that **a prefix of a run whose cost distribution
is dominated by rare runaway items is not a reliable estimate of that run's total** — the tail is the
measurement, not noise around it. Per-item medians were stable (17→18 s, 23→21 s); only the totals moved.

## ✅ FIRST `deployed`-PROFILE, CURRENT-BOX CODING ROW — and the runaway tax is REAL at a true budget (2026-08-14)

`Ornith-1.0-35B-mlx-uniform-4bit / humanevalplus`, **n=100**, M5, `deployed`, `max_kv_cache_size`
131072 so the declared **81,920 thinking budget is genuinely in force** (no clamp), APC absent,
0 errors.

| | |
|---|---|
| `acc` | **93.0%** [87,98], MDE ±13pp |
| **`acc_strict`@81920** | **90.0%** |
| `conv%` | **97%** — 3 non-converged, `nonconv_kinds = degenerate_repetition:3` |
| self-terminating loops (`degen`) | 1 (wall 2%, tok 2%) |
| latency | total 69 min · mean 42 s · median 18 s · p95 106 s · max 622 s |
| decode | median **108 tok/s** · median 1,850 tokens · max 82,101 |

**⇒ THE RUNAWAY TAX IS REAL, AND THIS IS THE FIRST CLEAN MEASUREMENT OF IT.**

| non-self-terminating turns | |
|---|---|
| rate | **3 / 100 = 3%** |
| **share of WALL-CLOCK** | **42%** (29 min of 69) |
| share of tokens | **49%** (247K of 504K) |
| the three items | `HumanEval/94` 10.4 min / 82,101 tok · `HumanEval/83` 9.5 min / 82,005 tok · `HumanEval/144` 9.1 min / 81,995 tok |

All three ran to ~82,000 tokens against a **genuinely in-force** 81,920 budget and were classified
`degenerate_repetition`. So this is NOT the clamp artifact that contaminated the IFEval measurement —
it is 3% of items consuming 42% of wall-clock, measured at the config we intend.

**This VINDICATES O11's cost claim while replacing its evidence.** O11 cited 42% of IFEval wall-clock,
which turned out to be 39/40 external truncations at a clamped budget (see below). The tax is
nevertheless real, it is the same ~42%, and here the mechanism is genuine.

⚠️ **It also weakens O11's "prompt-triggered by COUNTING instructions" hypothesis.** The loops were
concentrated on `change_case:capital_word_frequency` in IFEval, which suggested self-verification of a
tally. But they appear on plain HumanEval code generation too, with no counting instruction in sight.
That points at a model/sampling property rather than a prompt trigger — which is what the successor
probe should test.

**The successor probe is now WELL-POSED AND EXECUTABLE**, which it was not this morning:
- the offending ids are known exactly (`HumanEval/94`, `HumanEval/83`, `HumanEval/144`);
- `generate --ids` exists (`78de435`), so a ladder can vary ONE knob on EXACTLY those items;
- the budget is genuinely in force, so a temperature ladder measures the MODEL, not the config.
Cost: 3 items × 3 temps ≈ **90 min worst case**, far less if a rung converges (a fixed item drops from
~10 min to ~20 s). **QUEUED** — not run, because it would evict the resident model mid-run.

⚠️ **Cross-check, NOT a comparison:** the retired-M2 `official` row was `acc` 95.0% / strict 90.0% /
conv 95%. The new row is 93.0% / 90.0% / 97%. Reassuringly close (−2pp on `acc`, well inside ±13pp;
`acc_strict` identical) — but cross-box AND cross-profile, so per AGENTS.md it is not a valid
comparison and must not be reported as one.

## ✅ RETRACTED — "`kv_prealloc_tokens: 262144` destroys decode throughput" DID NOT REPRODUCE (2026-08-14)

**This section previously reported a >47× slowdown at the shipped `262144/262144` config. That was
wrong and is retracted.** A 3-arm OFAT on the same item (`HumanEval/146`,
`Ornith-1.0-35B-mlx-uniform-4bit`, `deployed`, router restarted per arm for a clean peak-memory mark):

| cap / prealloc | wall | decode | `mx.get_peak_memory` | pressure warns |
|---|---|---|---|---|
| 131072 / 131072 | 24.7 s | 98.5 tok/s | 25.35 GB | 0 |
| 262144 / 131072 | 25.0 s | 103.1 tok/s | 25.50 GB | 0 |
| **262144 / 262144** (shipped) | **27.8 s** | **104.5 tok/s** | 28.18 GB | 1 |

**All three are fast**, peak memory is far under the 46GB gate in every arm, and the prealloc rule —
which exists because growing a cache 128K→256K requires holding 384K of KV during the double-buffer,
and that measurably OOMed — **stands unchallenged**.

**The original 19.5-minute non-completion is UNATTRIBUTED and treated as a transient.** Most likely
environmental: that run started with ~21GB already held by other processes and swap already active
(`System memory: 68.7GB total, 47.8GB available`, then `memory.pressure.warn ram_percent=76.9`),
versus a cleaner box for the OFAT.

⚠️ **What the OFAT DID surface, and it is now `docs/open-questions.md` O15:** doubling the prealloc
moved peak memory by only **~2.8 GB**, not the ~16 GB that materialising twice the fp16 KV up front
implies. So for a `kv_bits: 0` model the reservation looks lazy or unwired — and if it is not actually
committed, it may not be preventing the OOM it exists to prevent. Untested either way; do not change
prealloc before measuring.

**Process note kept deliberately:** one dramatic observation, on one item, with two variables moved at
once, is a hypothesis. It was written up as a finding, put into `AGENTS.md` as a warning against a rule
that prevents a known OOM, and used to justify reducing the registry. The OFAT that falsified it took
four minutes and should have come first.

## ⚠️ THE DECLARED THINKING BUDGET WAS NOT THE ONE IN FORCE — 33 IFEval rows were FALSE PASSES (2026-08-14)

**Mechanism, confirmed to the token, not inferred.** `mlx-vlm`'s `_apply_generation_budget`
(`server/generation.py:585-601`) resolves a request's budget in two steps, and the second is
**SILENT**:

```
effective       = min(max_tokens, context_limit - prompt_tokens)   # logs a WARNING
thinking_budget = min(thinking_budget, int(effective * 0.8))       # logs NOTHING
```
(`THINKING_BUDGET_CLAMP_RATIO = 0.8` at `generation.py:535`.)

The IFEval runs declared `max_tokens: 102400` and `thinking_budget: 81920` against
`max_kv_cache_size: 65536`. So the budget ACTUALLY IN FORCE was `int((65536 - prompt) * 0.8)` ≈
**52,390 — not 81,920**. `ThinkingBudgetCriteria` force-injected `\n</think>` at that cap, the model
then wrote its (correct) answer, and `finish_reason` came back `"stop"`.

`convergence.is_converged` compared `completion_tokens` to the **requested** 81,920, so it returned
True. **That is precisely the FALSE PASS the convergence rule exists to catch** — AGENTS.md:
"`finish=="stop"` alone is a FALSE PASS (budget-hits force an EOS)." It slipped through because the
clamp is invisible to the harness, not because the rule was wrong.

**Arithmetic reproduces every observed stop point exactly:**
- 26 Ornith + 8 distill loop rows stop in a razor-thin band, each matching `int((65536 - prompt)*0.8)`
  for its own prompt length — which is why the band was identical across two different architectures.
- The six `finish_reason=="length"` rows land on `prompt + completion == 65537` **exactly**.

### Corrected IFEval — `acc` unchanged, convergence and `acc_strict` were wrong

| | `Ornith-1.0-35B-mlx-uniform-4bit` (n=541) | `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (n=148) |
|---|---|---|
| `acc` (answers still verify) | 90.0% | 89.9% |
| `conv%` published → **resolved** | 99.3% → **94.6%** | 98.6% → **93.2%** |
| `acc_strict` published → **resolved** | 89.8% → **86.7%** | 88.5% → **85.1%** |
| passing rows that were actually DNFs | **17** | **5** |

**⇒ THE IFEVAL HEADLINE SURVIVES.** Both arms moved the same way, so "the two winners are
EQUIVALENT on instruction-following" stands. The defect corrupted the convergence DIAGNOSTICS
materially, not the comparative verdict. (The 86.7 vs 85.1 above is UNPAIRED — different n — so it is
not itself a verdict; the paired-on-148 comparison is what ranks.)

### It falsifies O11's premise: the loops are not self-terminating

O11 described "verbatim repetition loops that SELF-TERMINATE under budget and answer CORRECTLY,"
costing 42% / 57% of wall-clock. Reclassified against the resolved budget:

| | Ornith | distill |
|---|---|---|
| flagged loops | 30 | 10 |
| → clamped budget-hits (mis-scored as converged) | **25** | **8** |
| → `max_tokens` truncations (`fr=length`) | 4 | 2 |
| → **genuinely self-terminating** | **1** (id 3748, 8,228 tok) | **0** |
| loop wall share | 42% | 57% |
| — of which genuinely self-terminating | **0.3%** | **0.0%** |

**The cost figure stands (2.5h and 3.6h are real); the attribution changes.** 39 of 40 items are
external truncations, so this is AGENTS.md's standing "persistent budget hit → run the temperature
ladder" case, NOT a "purely a cost" question. ⚠️ **The M1 ruling needs revisiting** — it turned on
item 2849 sitting at "64% of budget" (52,503/81,920); against the budget in force that is **100.2%**,
a budget hit. See `docs/open-questions.md` O12.

### Scope: which rows are affected, and which are NOT

The clamp fires only when `max_tokens` exceeds `max_kv_cache_size - prompt`. Verified per manifest:
- **AFFECTED: the IFEval runs only** (`max_kv_cache_size: 65536`). 33 rows.
- **NOT affected: every evalplus / math500 / aime / LCB row** — those ran at `max_kv_cache_size`
  262144 (or gemma's 196608), where 102,400 fits with room to spare, so their budget WAS the declared
  81,920 and their published convergence numbers stand. Ornith's `budget_hit:9` on math500 and
  `budget_hit:5` on humanevalplus are GENUINE hits.
- **M1 — CHECKED 2026-08-14, and its recorded numbers have three problems.** Raw rows found and read
  (`~/ws/aider/benchmark/tmp.benchmarks/*m1{f,g}*`, 221 cases with non-empty `tests_outcomes`).
  1. **`completion_tokens` in `.aider.results.json` is a PER-CASE SUM ACROSS TURNS, not per-turn.** So
     the recorded "max completion 62,083 / 59,974 against an 81,920 budget" compared a multi-turn sum
     to a per-turn budget. Actual max per-case sum: **148,908** (Ornith), 60,528 (distill) — and **2
     Ornith cases exceed 81,920 outright**. This error is independent of the clamp.
  2. **"context-exhaustion 0 for both, a genuine tie" is WRONG.** `num_exhausted_context_windows > 0`
     in **2 Ornith and 1 distill** cases. Small, but it is one of the four ranked numbers.
  3. **"0 of 284 turns hit the budget" is UNVERIFIABLE from the persisted data**, not merely wrong —
     per-turn tokens are not recorded. And M1's resolved per-turn ceiling was
     `0.8 * (65536 - prompt)` = **~46,600 at the median prompt, ~27,100 at the largest** — never
     81,920. With ~1.75 turns/case, a 148,908-token case implies ~74K per turn, comfortably over even
     the most generous resolved ceiling.
  **⇒ "the runaway tax has nothing to charge" must not be relied on.** ⚠️ Turn counts also do not
  reconcile: AGENTS.md says 284 (213 Ornith / 71 distill); `len(tests_outcomes)` gives 193 / 185. The
  distill gap is probably the `m1g` java re-run now being counted, and `tests_outcomes` counts test
  runs rather than LLM turns — so this needs the per-turn source to settle, and is FLAGGED rather than
  corrected. **What is NOT affected: the M1 capability verdict.** `final` 50.0% vs 73.6%,
  p=1.3e-05 rests on pass/fail per case, which none of this touches.

### Latent in the SHIPPED config too

Committed registry pairs `max_kv_cache_size: 262144` with `max_tokens: 102400`. Fine at short
prompts — but past a ~160K prompt the clamp starts firing, and at a 250K prompt the resolved thinking
budget is **9,708**, silently. That directly undercuts any "256K agentic" claim: deep into a session
the model's thinking allowance is a fraction of what every carrier declares.

**Fix landed (`aca967b`, driver):** `convergence.resolved_thinking_budget` /
`backfill_resolved_budget` mirror the fork constant; `grade._rows` annotates from the run manifest at
the one seam every grader loads through, so `conv%` / `nonconv_kinds` / `acc_strict` are all corrected
at once. Rows from unclamped runs keep their verdicts by construction (guarded by test). Real IFEval
rows are pinned as a regression corpus in `benchmark/bench/tests/test_resolved_budget.py`.

## RE-GRADE UNDER THE CONVERGENCE VECTOR — M5, existing data, zero model time (2026-08-11)

All 83 existing M5 result files re-graded with harness v2 (`grade` at `eddc082`). **No new
generation** — this is the same data the scoreboard below already reports, read under the
pre-registered rule (`conv% ≥ 0.90` GATES, `pass@1|converged` RANKS within it) and with intervals.
Box: M5 (all rows). Backed up off-box to `~/mlx_bench_snapshots/m5-results-2026-08-11/`.

| model | bench | n | acc | 95% CI | MDE | conv% | gate | pass@1\|conv | strict@budget | nonconv |
|---|---|---|---|---|---|---|---|---|---|---|
| Ornith-1.0-35B-mlx-uniform-4bit | humanevalplus | **100** | 95.0% | [90,99] | ±13pp | 95 | PASS | 94.7% (n=95) | 90.0%@81920 | budget_hit:5 |
| Ornith-1.0-35B-mlx-uniform-4bit | mbppplus | **100** | 87.0% | [80,93] | ±13pp | 100 | PASS | 87.0% (n=100) | 87.0%@81920 | — |
| Ornith-1.0-35B-mlx-uniform-4bit | math500 | 30 | 83.3% | [70,97] | ±23pp | **70** | **FAIL** | 85.7% (n=21) | 60.0%@81920 | budget_hit:9 |
| Ornith-1.0-35B-mlx-uniform-4bit | aime | 5 | 80.0% | [40,100] | ±56pp | 80 | FAIL | 75.0% (n=4) | 60.0%@81920 | budget_hit:1 |
| Ornith-1.0-35B-mlx-uniform-4bit | livecodebench | 15 | **80.0%** ⁽ᴬ⁾ | [60,100] | ±32pp | **80** | **FAIL** | 75.0% (n=12) | 60.0%@81920 | budget_hit:3 |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | humanevalplus | 36 | 91.7% | [81,100] | ±21pp | 100 | PASS | 91.7% (n=36) | 91.7%@81920 | — |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | mbppplus | 10 | 60.0% | [30,90] | ±40pp | 100 | PASS | 60.0% (n=10) | 60.0%@81920 | — |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | math500 | 27 | 81.5% | [67,96] | ±24pp | 100 | PASS | 81.5% (n=27) | 81.5%@81920 | — |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | aime | 4 | 100% | [100,100] | ±63pp | 100 | PASS | 100% (n=4) | 100%@81920 | — |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | livecodebench | 15 | **80.0%** ⁽ᴬ⁾ | [53,100] | ±32pp | 100 | PASS | 80.0% (n=15) | 80.0%@81920 | — |
| gemma-4-31B-it-qat-6bit | humanevalplus | 10 | 100% | [100,100] | ±40pp | 100 | PASS | 100% (n=10) | 100%@16384 | — |
| gemma-4-31B-it-qat-6bit | mbppplus | 10 | 80.0% | [50,100] | ±40pp | 100 | PASS | 80.0% (n=10) | 80.0%@16384 | — |
| gemma-4-31B-it-qat-6bit | math500 | 30 | 83.3% | [70,97] | ±23pp | 100 | PASS | 83.3% (n=30) | 83.3%@16384 | — |
| gemma-4-31B-it-qat-6bit | aime | 5 | 100% | [100,100] | ±56pp | 100 | PASS | 100% (n=5) | 100%@16384 | — |
| gemma-4-31B-it-qat-6bit | livecodebench | 15 | **80.0%** ⁽ᴬ⁾ | [60,100] | ±32pp | 93 | PASS | 78.6% (n=14) | 73.3%@16384 | budget_hit:1 |

⁽ᴬ⁾ **LCB rows CORRECTED 2026-08-12 (re-graded at `d214bf9`).** The three values first published here
(93.3 / 93.3 / 86.7) were inflated by a grading bug, not measured: `grade_lcb` read lcb_runner's
per-test verdicts by truthiness, and lcb_runner encodes **-1 = timeout** and **-2 = runtime/compile
error**, both of which are truthy in Python — so every timeout and every crash scored as a PASS, and
`_finalize` then overwrote the official `acc` with the mean of those inflated items. Re-graded with
the fix, all three models land on **acc = pass@1 = 0.800**, and `acc == mean(by_difficulty)` now
holds for each (it did not before). **LCB is a THREE-WAY TIE at 80%**, n=15, MDE ±32pp, with
massively overlapping intervals — it is not a differentiator in either direction, and the **"LCB
6.7pp delta" that the plan and queue cite as the live gap does not exist.** The more informative
number is `acc_graded` (per-test pass FRACTION, which carries partial credit): distill **0.965**
[0.915,1.0] > gemma **0.944** [0.861,1.0] > Ornith **0.928** [0.839,1.0] — still overlapping, but
the ordering is at least real. Blast radius is LCB only: the exact-match graders compare values
(`str(pred)==str(gold)`, `_math_eq`) and evalplus compares `== "pass"`, so no other axis is touched
and Ornith's n=100 evalplus rows stand.

**What the vector changes about the reading of this data:**

1. **Ornith fails the convergence gate on three axes** — math500 (70%, 9 budget-hits), LCB (80%),
   aime (80%) — while Qwen3.6-27B-Opus-Distill-OptiQ-4bit and gemma-qat-6bit clear it everywhere. Under the old rule those
   runs were "INVALID" and read anyway with asterisks; under the vector the statement is precise:
   *among items it converged on* Ornith is fine (math500 85.7%, LCB 91.7%), it just does not
   self-terminate reliably. That is a real, ranked deficiency for a daily driver, and it is the
   first axis on which the current pick looks worse than the alternative.
2. **The campaign's own scoreboard UNDERSTATES its best evidence.** Ornith's evalplus rows are
   **n=100**, not the n=10 recorded below — 95.0% [90,99] and 87.0% [80,93] at ±13pp are the
   best-powered quality numbers the campaign owns, and they sat unreported.
3. **"AIME 100% (5/5)" was never a differentiator.** At n=5 the MDE is ±56pp (n=4 → ±63pp). The
   gemma-qat-6bit standout and Qwen3.6-27B-Opus-Distill-OptiQ-4bit's 100% are indistinguishable from each other and from
   Ornith's 80%.
4. **Qwen3.6-27B-Opus-Distill-OptiQ-4bit's mbpp+ 60%** is n=10, ±40pp — also not a ranking, despite looking alarming next
   to Ornith's 87% (n=100). Note `compare` REFUSES this pair: different item sets and different n.
5. LCB aggregate acc is the official evaluator's `pass@1`; see the by-difficulty bug below.

✅ **QUARANTINE LIFTED 2026-08-12 — `by_difficulty` was never the bug; `acc` was.** The fault is
diagnosed and fixed (`d214bf9`, see ⁽ᴬ⁾ above): the breakdown had been correct the whole time and
`acc` was the inflated number. After the fix `mean(by_difficulty) == acc == pass@1 == 0.800` for all
three models, and the identical E100/M86/H60 breakdown is simply CORRECT — all three genuinely solve
the same 12 of the same 15 fixed problems, whose difficulty split is 3/7/5. **Every historical
`E../M../H..` figure in this document is sound**; all nine reconcile exactly with their own run's
aggregate (12/15, 10/15 and 13/15 all check out). The reasoning below was wrong in one specific way,
recorded because the error is instructive: it compared a HISTORICAL breakdown against a RE-GRADE
aggregate — two different grading runs — and then declared the contradiction impossible. When two
numbers disagree, check that they came from the same computation before concluding one is impossible.
The proposed diagnostic grading run with `num_process_evaluate=1` was **not needed** and was not run.

<details><summary>original (incorrect) quarantine reasoning, kept for the audit trail</summary>

⚠️ **BUG — LCB `by_difficulty` is not reportable (found 2026-08-11).** All three models print an
identical breakdown (EASY 100% n=3 / MEDIUM 86% n=7 / HARD 60% n=5) which averages to 12/15 = 80%,
while their aggregate accs are 93.3 / 93.3 / 86.7. Identical per-difficulty rates across three
models with differing aggregates is impossible, and the breakdown contradicts the aggregate within
a single run. The aggregate comes straight from `codegen_metrics`' `pass@1` and is trusted; the
breakdown is **quarantined** until diagnosed. This matters because the per-difficulty split is
exactly what the campaign cites as the LCB differentiator (e.g. "E100/M86/H60"), so **every
historical `E../M../H..` figure is now suspect too.**

Narrowed so far (2026-08-11), ruling out the cheap explanations:
- **Not a duplicate-rows artifact.** Each `livecodebench.jsonl` holds exactly 15 rows / 15 distinct
  ids / no `sample` field, so the new per-sample grouping sees k=1 per problem — it cannot be
  collapsing appended runs into multi-sample items.
- **Not our index alignment or key typing.** Two new invariant tests
  (`test_by_difficulty_is_consistent_with_the_aggregate`, `..._survives_string_keyed_detail`) pass
  against fake evaluator output, including the int-vs-str `detail` key hazard.
- **lcb_runner says the two MUST agree.** `compute_metrics_from_results` builds
  `pass@k = estimate_pass_at_k(total, correct, k).mean()` and
  `detail[pass@k] = dict(zip(task_ids, estimate_pass_at_k(total, correct, k)))` from the same
  array, keyed by problem index — so the aggregate is by construction the mean of the detail.
- Suspicious coincidence worth chasing: Ornith's printed breakdown (12/15 = 80%, E100/M86/H60) is
  EXACTLY its historical t0.4 row, while its aggregate here (93.3%) matches the suffix-ON run.
- **Next step:** one real grading run that dumps the raw `metrics` dict (use
  `num_process_evaluate=1` — the pool dies under an ssh heredoc). Deliberately NOT run yet: it
  would contend for CPU with the M1 wall-clock measurements now in flight.

Why the above missed it: the two invariant tests DID pass, and that was taken as clearing our own
code — but `_install_fake_lcb` supplies `results={}`, which routes `grade_lcb` down its `frac`
fallback and never exercises the per-test-verdict path at all. A test that cannot fail on the faulty
line is not evidence. The bullet "lcb_runner says the two MUST agree" was also right, and should have
been read as proof that our POST-processing diverged from the evaluator — instead of trusting `acc`
and doubting the breakdown, which is the number the evaluator hands over most directly.
</details>

## ▶M1 GATE — INTERIM (2026-08-12, run `m1f`, 3 of 5 languages): Qwen3.6-27B-Opus-Distill-OptiQ-4bit wins, p=0.0042

⚠️ **INTERIM — rust and java are still generating.** Ornith's arm is COMPLETE (110/110); Qwen3.6-27B-Opus-Distill-OptiQ-4bit
has python + javascript complete plus part of go. Recorded now because the result already crosses
significance and it REVERSES the campaign's standing pick. Config: run tag `m1f`, box M5, APC OFF,
`deployed` sampling, **`max_kv_cache_size` 65536** (right-sized for this axis — see the handover;
memory/speed numbers from this run are NOT comparable to any 256K row), aider `diff` format both
arms, 2 attempts, items pinned BY NAME so both arms see byte-identical exercises.

**Paired on 48 byte-identical exercises:**

| metric | Ornith-1.0-35B-mlx-uniform-4bit | Qwen3.6-27B-Opus-Distill-OptiQ-4bit | delta | McNemar exact |
|---|---|---|---|---|
| **final (≤2 attempts)** | 26/48 = **54.2%** | 38/48 = **79.2%** | **+25.0pp** | **p = 0.0042** ✅ |
| attempt-1 only | 12/48 = 25.0% | 19/48 = 39.6% | +14.6pp | p = 0.092 (n.s.) |

Exclusive solves on `final`: **only-Ornith 2** (`python/forth`, `javascript/list-ops`) vs
**only-distill 14**. The `final` result survives Holm across the two tests (0.0042×2 = 0.0084).
This is the campaign's FIRST matched agentic measurement — the historical "13.2pp" came from two
unrelated unseeded random subsets with different language mixes and was never a measured gap.

**The three-number decomposition (report all three; `final` alone is not a model property):**

```
final = attempt-1 + (1 − attempt-1) × repair_rate
```

| | attempt-1 | repair rate | → final | languages |
|---|---|---|---|---|
| Ornith-1.0-35B-mlx-uniform-4bit | 24.5% | **33.7%** (28/83) | 50.0% | all 5 |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | 39.6% | **65.5%** (19/29) | 79.2% | 3 |

The identity is exact (Ornith 0.245+0.755×0.337=0.499; distill 0.396+0.604×0.655=0.792). **Repair
rate — does it fix its own failure when shown the failing test — is the sharpest discriminator we
own, and Qwen3.6-27B-Opus-Distill-OptiQ-4bit is ~2× better on it.** Both models draw about half their `final` from repair, so
the scaffold contributes about equally to both; Qwen3.6-27B-Opus-Distill-OptiQ-4bit simply exploits it far better.

**WHAT `final` MEASURES — a (model × scaffold × config) composite, not a model property.** Verified:
the repair turn receives the pytest traceback, which INCLUDES the failing test's source lines and
expected values (e.g. `expected = [True]` / `AssertionError: Lists differ: [] != [True]`). So `final`
means "converges when shown the failing assertions", a weaker claim than "writes correct code from a
spec". The paired design still licenses the COMPARISON, because the scaffold is held constant across
arms — and the constant is not silently handicapping either model: **well-formed 100% / 0 malformed /
0 context-exhaustion for BOTH across 158 cases**, so the `diff` edit format fits both. But the result
does **NOT transfer across scaffolds**: this is an *aider* result, and the campaign still has ZERO
evaluation through `opencode`, the declared primary driver.

**Per-language (Ornith complete) — a language gradient, not a complexity one:**

| lang | Ornith a1 / final / repair | distill a1 / final / repair |
|---|---|---|
| python | 31.8 / 72.7 / 60.0% | 40.9 / 86.4 / 76.9% |
| javascript | 18.2 / 36.4 / 22.2% | 31.8 / 72.7 / 60.0% |
| go | 45.5 / 63.6 / 33.3% | (partial) |
| rust | 18.2 / 31.8 / 16.7% | pending |
| java | 9.1 / 45.5 / 40.0% | pending |

Ornith collapses outside python/go. Note polyglot has NO difficulty stratification (unlike LCB's
E/M/H), so this is a language axis we stumbled into; a real complexity gradient is an open gap.

**Runaway tax: ZERO.** 284 turns (213 Ornith / 71 distill), 0 budget-hits, 0 `max_tokens` hits, max
completion 62,083 / 59,974 against an 81,920 budget, wasted wall-clock **0.0%**, agentic conv%
**100% for both**. Speed: Ornith ~2.2 min/case vs distill ~6.3 (≈2.9×).

## JUDGE PANEL v2 — 3 roles x 2 orders, reference-guided (2026-08-12): NOT RELIABLE ENOUGH TO RANK

Second panel, rebuilt on the LLM-as-judge literature after v1 (below) came back only 55%
self-consistent. **Result: still no quality difference, and the panel's own inter-rater reliability
is too low to license a ranking even if there had been one.**

**Design.** 24 BOTH-SOLVE paired exercises (15 python, 7 javascript, 2 go). 3 judges x 2 orders = 6
passes/item. Judges: **Opus** (holistic "would I merge this"), **Sonnet** (maintainability role:
naming / readability / cognitive_load / ease_of_safe_change), **Sonnet** (architecture role:
decomposition / cohesion_coupling / error_handling_structure / idiom_api_fit). Analytic rubrics,
1-5 with anchors, one role per prompt. **Reference-guided:** every exercise ships `.meta/example.py`
(83/83), supplied as a calibration anchor with explicit instruction not to reward mere similarity.
Blind A/B from a blake2b of the exercise name (11/24 A=Ornith), key withheld from all judges.

**Order-consistency, per judge — the role decomposition HURT:**

| judge | model | order-consistent | hard reversals |
|---|---|---|---|
| holistic | Opus | **17/24 (71%)** | 4 |
| architecture | Sonnet | 15/24 (62%) | 4 |
| maintainability | Sonnet | **10/24 (42%)** | 8 |

Reference-guided holistic Opus judging is the best configuration measured (71%, up from v1's 55%),
but the narrow role prompts are *worse* — maintainability at 42% is indistinguishable from a coin.
Plausible mechanism: forcing a narrow lens onto near-identical 20-60 line solutions manufactures
distinctions that are not there.

**Panel verdict (majority over each judge's order-consistent calls):** distill 9, Ornith 7,
no-majority 4, tie 2 — sign test on 16 decided items **p = 0.804**.

**INTER-RATER RELIABILITY: Krippendorff alpha (ordinal, 15 units, 3 raters) = 0.517**, below the
~0.667 usually required for even tentative conclusions. Pairwise: holistic-vs-maintainability 75%
(n=8), holistic-vs-architecture 60% (n=10), maintainability-vs-architecture 7/7. **The three roles
do not agree enough to pool, so the panel verdict above should not be used to rank anything.**

**Per-dimension means (all 6 passes) — every delta is noise on a 1-5 scale:**

| dimension | Ornith | distill | delta |
|---|---|---|---|
| readability | 3.58 | 3.69 | +0.10 |
| naming | 3.52 | 3.50 | −0.02 |
| cognitive_load | 3.35 | 3.54 | +0.19 |
| ease_of_safe_change | 3.42 | 3.50 | +0.08 |
| decomposition | 3.27 | 3.35 | +0.08 |
| cohesion_coupling | 3.21 | 3.42 | +0.21 |
| error_handling_structure | 3.10 | 3.00 | −0.10 |
| idiom_api_fit | 3.27 | 3.38 | +0.10 |
| overall_quality | 3.35 | 3.52 | +0.17 |

**Verbosity bias: not driving anything.** Mean solution length 1149 vs 1157 chars (no asymmetry to
exploit); the panel picked the longer solution in 10/16 decided items (62%, binomial p≈0.45).

**Interpretation.** Two readings fit equally well and the data cannot separate them: either the
instrument is too noisy at this scale, or there is genuinely nothing to discriminate between two
sets of test-passing 20-60 line exercises. Either way **the quality axis does not differentiate
these two models**, and the decision therefore rests on the capability axis, where the M1 gate above
is unambiguous (+25.0pp final, p=0.0042). A useful pipeline check survives both readings: all six
judges independently called `javascript/binary` a high-confidence tie because the two models emitted
token-for-token identical code.

**If this is run again:** reference-guided *holistic* Opus, drop the narrow role prompts, and spend
the budget on more ITEMS instead of more roles. Still single-family (Opus+Sonnet are both Claude),
so AGENTS.md's mixed-family requirement remains unmet. Artifacts: `benchmark/results/_judge2/`.

## JUDGE PANEL v1 — first run ever (2026-08-12): no code-quality difference detected

The blind quality panel was built long ago and had **never been run**. Run now on m1f's
both-solve set, because execution-gated `acc` measures only "the provided tests pass" and says
nothing about maintainability — the gap that motivated the panel in the first place.

**Design.** Judges: 4 × Opus subagents. Items: the **22 BOTH-SOLVE paired exercises** (15 python,
7 javascript) — exercises where BOTH models produced test-passing code. That restriction is the
point: AGENTS.md forbids the judge as a correctness oracle, and pitting a passing solution against
a failing one would smuggle correctness back into a "quality" score. Solution files only, taken
from each exercise's `.meta/config.json` → `files.solution`; test files withheld so the judge
cannot grade against them. Blinding: A/B per exercise from a blake2b of the exercise name
(reproducible, no RNG), landing 11/22 A=Ornith; the key was in a file no judge saw. Dimensions:
readability / idiom / simplicity / structure, 1–5. **Every item was judged TWICE by different
judges with A/B swapped**, so position bias — the best-documented failure mode of pairwise LLM
judging — becomes a measurement instead of an assumption.

**RESULT — the instrument is the headline.** Order-consistency was only **12/22 (55%)**. Decomposed:
only **3 HARD reversals** (model → other model: `javascript/bottle-song`, `javascript/ocr-numbers`,
`python/hangman`, all distill→Ornith) and **7 SOFT flips** across the tie boundary. Raw position
preference is mild (label-A won 18 vs label-B 15 of 33 decided), so instability is concentrated at
the tie boundary, not in a gross left/right bias. **The judge's own confidence is well calibrated:**
consistent 1/1 at `high`, 2/2 at `medium`, but only **9/19 (47%) at `low`** — so `confidence` is a
usable filter, and a single-order panel would have produced a confident-looking answer with a coin's
reliability. The counterbalancing paid for itself.

**On the defensible (order-consistent) set, n=12: Ornith 6 / distill 4 / tie 2**, sign test on the 10
decided pairs **two-sided p = 0.754**. Mean dimension scores over all 44 judgments are flat:

| model | readability | idiom | simplicity | structure | overall |
|---|---|---|---|---|---|
| Ornith-1.0-35B-mlx-uniform-4bit | 3.77 | 3.89 | 3.66 | 3.66 | **3.74** |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | 3.80 | 3.70 | 3.82 | 3.84 | **3.79** |

**Reading: NO code-quality difference detected — and this is INCONCLUSIVE, not a demonstrated tie.**
A sign test on 10 decided pairs needs **9/10 (90%)** in one direction to reach p≤.05, so this panel
could only ever have detected a landslide; 0.05 of a point on a 1–5 scale is noise. What it does
establish is a **separation of concerns**: Qwen3.6-27B-Opus-Distill-OptiQ-4bit's advantage over Ornith is in **how many**
exercises it solves at all (exclusive-solve 7 vs 1, McNemar p=0.070), **not** in the quality of the
code when both succeed. Also a useful sanity check on the whole pipeline: the panel independently
flagged `javascript/binary` as a high-confidence tie because the two models emitted
**token-for-token identical** code.

**Scope limits.** python + javascript only (the languages both arms had finished); go/rust/java
should roughly double the both-solve set when m1f completes. Single judge FAMILY (Opus) — AGENTS.md
specifies a **mixed-family** panel, so cross-family agreement is still unmeasured and this run does
not satisfy that requirement. Raw verdicts + key + aggregator: `benchmark/results/_judge/`.

## P2 TIER-0 SAMPLING GRID — Ornith arm COMPLETE (2026-08-12, graded/audited 2026-08-13)

Box M5, APC absent (router env `APC=` count 0, verified on the pid), `deployed` sampling profile,
`max_kv_cache_size` 65536, suffix decoding ON as shipped, `presence_penalty` 0.0 throughout.
Grid = 3 temps {0.2, 0.4, 0.6} x 3 `min_p` {0.0, 0.02, 0.05} plus 2 collapse-test cells, at
`--samples 2 --coding-samples 1`; `top_k=0 / top_p=1.0` in the 9 grid cells (min_p is the one
scale-free truncation knob), deployed `top_k 20 / top_p 0.95` in the `collapse_3knob` cell.
Archived off volatile `/tmp` to `~/mlx_bench_snapshots/tier0-2026-08-12/` (11 result JSONs +
per-cell logs), all 11 verified distinct by md5 — the stale-copy failure mode did NOT recur.

### Result: there is no convergence knee for Ornith at these settings — an ANSWER, not a null
**`converged_rate` 1.0 and `budget_hit_rate` 0.0 in ALL 11 cells**, on both the aggregation and
coding halves. Audited per-draw rather than from the summaries: **33/33 draws converged**, 33/33
`finish_reason == "stop"`, **0 budget hits**, max `completion_tokens` **40,607** against the 81,920
budget (~50% headroom). Aggregation median completion ranged 32,685–40,607 tokens across cells;
coding 2,562–3,819. Label-vs-recorded-param audit: **0 mismatches** in the 9 labelled cells.

**Consequence for P3 — the ρ proxy analysis cannot use `conv%` for Ornith.** A constant vector has
no rank correlation, so Spearman ρ on convergence is *undefined*, not merely weak. If the screen is
to predict anything for this model it must be on a metric that actually varies (median reasoning
tokens does: 6,287 → 40,607). Note also that P3 correlates the screen against per-config **agentic**
results that **do not exist yet** (P4 has not run), so the second half of that correlation is
currently unmeasured.

### Two design defects in the grid, both measured
- **`min_p` is inert across the chosen spacing, and so are `top_p`/`top_k`.** Grouping cells by
  per-draw output signature gives **8 distinct signatures across 11 cells**:
  `t0.2_mp0.02 ≡ t0.2_mp0.05`, and `t0.4_mp0.02 ≡ t0.4_mp0.05 ≡ collapse_3knob`. The last identity
  is the informative one: `collapse_3knob` runs the **deployed 3-knob** truncation (top_p 0.95 /
  top_k 20 / min_p 0.0) and is byte-equal to **min_p-only** cells at min_p 0.02 and 0.05. So the
  three truncation knobs are **mutually redundant in this range** — the only distinction the model
  resolves is truncation ON vs OFF. Effective distinct configs ≈ **6 (3 temps × 2 truncation
  states)**, not 9. Widen the `min_p` spacing (e.g. 0.0 / 0.05 / 0.15) or drop it as an axis.
- **The collapse test is mis-specified.** `collapse_minp_only` was intended as the min_p-only
  comparator but is set to `min_p 0.0, top_p 1.0, top_k 0` — i.e. **nothing active**, making it an
  *exact duplicate* of `t0.4_mp0.0` (params verified equal field-by-field). As written the test
  compares "deployed truncation vs no truncation", not "3-knob vs min_p-only". The collapse claim
  is nevertheless **supported** — by the accidental `collapse_3knob ≡ t0.4_mp0.02 ≡ t0.4_mp0.05`
  identity above. A correctly-specified comparator needs `min_p > 0`.
  That duplication had one lucky payoff: it gave a free same-config replicate, which is how the
  determinism defect below was found.

## P2 TIER-0 REV B — 22/22 cells, BOTH models, 50 min total, zero failures (2026-08-13)

`benchmark/m1/tier0b_grid.sh`. M5, APC absent, `deployed` profile, kv 65536, suffix ON, task
**vartrack**, truncation held at deployed `top_p 0.95 / top_k 20`, `min_p` {0.0, 0.05, 0.15},
temps {0.2, 0.4, 0.6}, `--samples 2 --coding-samples 1`, all 22 archives md5-distinct, all params
verified against the request by `tier0b_check.py` (which checks all four truncation knobs plus
`presence_penalty`, `thinking_budget` and `max_tokens`). Durable archive:
`~/mlx_bench_snapshots/tier0b-2026-08-13/`. **Total worker time 50 min for both models** — against
rev A, whose distill arm produced zero cells in over an hour.

### The determinism fix is CONFIRMED by an independent route
Rev B contains a duplicate-config pair by construction (`collapse_3knob` and `t0.4_mp0.0` are
identical field-by-field). In rev A the equivalent pair **diverged**. In rev B, with truncation held
at the deployed values, both models produce **byte-identical per-draw outputs** for that pair. So
holding `top_p`/`top_k` at deployed values does fix reproducibility, verified on two models in a
separate grid rather than only in the 2x2 probe.

### Convergence is SATURATED for both winners — and `conv%` is therefore the wrong screen metric
**33/33 draws converged for EACH model** (66/66 total), **0 budget hits**, every
`finish_reason == "stop"`, in all 22 cells. So neither winner has a convergence knee anywhere in
temp 0.2–0.6 × min_p 0.0–0.15. `conv%` = 1.0 everywhere.

But convergence being pinned at 1.0 hides an enormous cost spread, and only in one model:

| coding-prompt draw | t0.2 | t0.4 | t0.6 (mp 0.0 / 0.05 / 0.15) |
|---|---|---|---|
| **Ornith** tokens | 2,921 | 2,830 | 2,180 / 2,019 / 2,016 |
| **Ornith** wall | 31.2 s | 30.1 s | 24.1 / 23.3 / 23.6 s |
| **distill** tokens | 1,322 | 1,122 | 4,921 / **52,833** / 1,632 |
| **distill** wall | 48.1 s | 40.8 s | 179 s / **999 s** / 64 s |

**Ornith is flat and mildly *decreasing* in temperature** (2,921 → ~2,016 tokens; 31 s → 24 s) — no
instability anywhere, which extends rev A's "no knee" from one temp to the whole range.
**Qwen3.6-27B-Opus-Distill-OptiQ-4bit is stable at 0.2–0.4 and unstable at 0.6**: one draw ran **52,833 tokens / 16.6 min**
on the *same* small meeting-rooms problem it solves in 1,122 tokens / 41 s at temp 0.4 — a **47×
token and 24× wall-clock blowup** that `conv%` scores as a clean pass, because it did self-terminate
under the 81,920 budget.

Two conclusions:
- **Independently confirms Qwen3.6-27B-Opus-Distill-OptiQ-4bit's op-temp 0.3** and the recorded finding that its earlier LCB
  "DNF" was a temperature artifact, from a different task and a different harness path.
- **Rank the screen on reasoning-token cost, not `conv%`.** `conv%` has no variance to offer for
  either winner (66/66), while cost varies 47× within one model. This is the same lesson AGENTS.md
  already applies to `acc_strict` — a metric pinned by construction cannot discriminate.

### `min_p` is inert at low temperature and only bites at high temperature
Distinct per-draw output signatures: **6 of 11 cells for EACH model** (identically for both, which
is itself notable). The structure:
- **temp 0.2 — `min_p` 0.0 ≡ 0.05 ≡ 0.15**, byte-identical. Wholly inert, even at 0.15.
- **temp 0.4 — 0.0 ≡ 0.05**, while 0.15 differs.
- **temp 0.6 — all three differ.**

Mechanistically consistent: `min_p` prunes below `min_p × p_max`, so on a peaked (low-temperature)
distribution `top_p 0.95 / top_k 20` has already removed everything `min_p` would have taken. It
only becomes a distinct knob once temperature flattens the distribution. **So a `min_p` axis is only
meaningful above ~0.4**, and rev A's inertness was not just a spacing problem.

### The collapse test now PASSES, properly specified
With a genuine min_p-only comparator (`collapse_minp_only` = `min_p 0.05`, `top_p 1.0`, `top_k 0`),
it is **byte-identical to the deployed 3-knob cell** on both models. **The 4D→2D collapse is
VALIDATED**: either truncation mechanism alone yields the same token stream. Caveat to carry: at
temp 0.4 `min_p 0.05` is itself inert, so this establishes equivalence in the regime tested, not at
temp 0.6 where the knobs do separate.

### ⚠️ HARNESS DEFECT — on slow models a genuine `budget_hit` is UNOBSERVABLE
`run_convergence.run_one` calls `driver.complete` at its **default 3600 s** timeout while
`thinking_budget` is 81,920. On Qwen3.6-27B-Opus-Distill-OptiQ-4bit's long-prompt cells decode is **10–16 tok/s**, so the
budget needs **85–136 min** to reach but the client abandons at 60 min (~37–58K tokens). The request
can therefore never be scored as a budget hit — instead the client gives up and, as rev A proved,
**the worker keeps generating**. That is not hypothetical: rev A's aggregation cell ran
**3,802 s > 3,600 s**, so the client timed out ~200 s before the worker finished, which is exactly
what orphaned the generation and cascaded into every later cell's 120 s `calibrate_cpt`.
Rev B came within range of it again — the 52,833-token draw took 999 s of the 3,600 s budget.
**Fix (proposed, not applied):** derive the per-request timeout from
`thinking_budget ÷ measured decode rate` with a margin, or fail the cell loudly when the timeout is
below that ratio, so the harness cannot silently convert a budget hit into an orphaned generation.

## IFEVAL — LIVE (2026-08-13) + two defects the 5-minute evaluation rule caught

Ornith-1.0-35B-mlx-uniform-4bit, M5, `deployed` sampling (temp 0.4, `presence_penalty` 0.0, stamped
in the manifest), APC absent (`apc_enabled: '0'`, detected per-pid), fingerprint v2, 541 items.
Driver `benchmark/m1/ifeval_run.sh`. **Interim at n=107: `prompt_strict 86.0% / prompt_loose 89.7%`, conv 99.1%, 0 errors, 0 verifier skips.** Full run in progress (~22 s/item
measured; Ornith ~3 h, distill ~10.7 h).

### ⚠️ DEFECT 1 — a missing nltk corpus was BIASING acc upward by ~3pp
`n_verifier_skipped = 8 of 38` completions — **21% of items silently dropped** — from
`LookupError: Resource 'punkt_tab' not found`. `_load_ifeval_lib` did try to ensure the tokenizer but
checked only `tokenizers/punkt`, while nltk ≥ 3.8.2 needs `punkt_tab`; its `except Exception: pass`
was annotated "verifiers that need it will fail closed", and they do not — they raise **per item**,
inside a loop that swallowed them with a bare `continue`.

**The dropped items were HARDER than average, so the skip inflated the headline:** re-grading after
downloading the corpora moved acc **93.3% (n=30) → 90.2% (n=41)**. A silent skip does not merely
shrink the denominator, it biases the number. Fixed to fail LOUD (whole-bench `acc:null` + an
actionable note) rather than report a clean-looking figure over a biased 79% subset. **Cost of the
correction: zero model time** — grading is a separate phase, so the persisted rows just re-graded.

### ⚠️ DEFECT 2 — self-terminating repetition loops scored as CONVERGED (4 of 107 items)
Two independent loop SIGNATURES, both invisible to the shipped convergence rule, and the second one
also invisible to my first attempt at detecting the first:

| id | tokens | wall | lines | uniq_line | max_repeat | ngram8_uniq | finish | signature |
|---|---|---|---|---|---|---|---|---|
| 2849 | 52,503 | 272 s | 4,179 | **0.0093** | **2,071** | 0.0123 | stop | LINE-level |
| 279 | 52,409 | 446 s | **22** | 1.0000 | 1 | **0.0104** | stop | CONTENT-level |
| 3608 | 54,702 | 285 s | **29** | 0.8966 | 2 | **0.0323** | stop | CONTENT-level |
| 3188 | 65,450 | 335 s | **12** | 1.0000 | 1 | **0.0077** | length | CONTENT-level |
| *healthy, for scale* | 9,875 | 94 s | 483 | 0.8116 | 3 | **0.7285** | stop | — |

`2849` repeats one line 2,071 times. The other three cycle **near-identical phrasings**, so every line
is technically unique and line-repetition detection sees nothing — but their 8-gram uniqueness is
**0.008–0.032 against ~0.73 for healthy items**, a 20–90× gap. Item 2849 ran at **193 tok/s** because
suffix decoding accelerates verbatim repetition.

`traces._is_repetition` existed and was correct for the line-level case; `classify` never reached it,
early-returning `None` for anything `convergence.is_converged` accepts. **The harness had the evidence
and did not use it.**

⚠️ **Two of my own thresholds were wrong before the data corrected them, which is worth recording:**
first I detected only line-level repetition (caught 1 of 4); then I added a content-level rule guarded
on `lines >= 100`, which caught **0** of the three it was written for — because the loops live inside
one giant paragraph (id 279 is 52,409 tokens in **22 lines**, ~2,400 tokens per line) while healthy
long traces are 385–483 lines for ~9.5K tokens. **Line count measures formatting, not length.** Guarded
on `chars >= 20000` instead. The lesson generalises: fixture values invented to look plausible let a
wrong guard pass its own tests.

**Cost, which is why a row count understates this ~7×:** the three EOS'd loops are 2.8% of items but
**26% of wall-clock and 33% of completion tokens**. `3188` is separately a genuine non-convergence and
is now labelled `degenerate_repetition` rather than `max_tokens` — the classifier docstring already
argues for acting on the mechanism, since "max_tokens" hides the sampling/quant defect.

⚠️ **THIS REVISES "the runaway tax has nothing to charge."** That finding (0/284 turns, 0.0% wasted
wall-clock) was measured on **budget-hits and `max_tokens` truncations only** — three of these four are
neither. The instrument was blind to loops cheap enough to self-terminate. The tax is not zero.

**The ratified convergence formula is deliberately unchanged** — it exists to stop a budget-hit's
forced EOS from false-passing, and it still does. Added instead as additive diagnostics:
`traces.is_degenerate` + `n_degenerate_eosed` / `degenerate_wall_share` / `degenerate_token_share`.
**OPERATOR-CONFIRMED, and this is the scoring rule (see `docs/open-questions.md` M1): NOT a DNF.** It is
a valid converged response — converged as determined by the MODEL — and it is recorded and evaluated for
quality like any other row, on BOTH correctness and subjective quality. Item 2849 **passed both strict
and loose verifiers** (a valid 276-char answer), and that pass counts in `acc`. Contrast a
thinking-budget hit, where the answer IS produced from work we truncated.

⚠️ **Do not read this as "correctness passed, so only the tokens were wasted."** What is measured here is
only the COST half (271 s / 52,503 tokens for 276 chars). Whether a model that loops 2,071 times before
answering produced *good work* is a question this instrumentation cannot answer. Per the campaign's
instrumentation rule that belongs to the blind mixed-family JUDGE PANEL over execution-PASSING outputs —
and these rows are exactly such outputs, so they are **eligible, not exempt**. `is_degenerate` is
therefore a **flag for the panel's attention, not a verdict**: the rows stay in `acc` and in the item set
with no exclusion or reweighting, while `degenerate_wall_share` / `degenerate_token_share` stay as
reasoning-token cost reported beside capability, never folded into it. The follow-up question is O9
(does the panel rate looped-then-correct answers differently?), which is blocked on the panel's own
reliability — recorded as "NOT RELIABLE ENOUGH TO RANK" at v2.

### The historical record CANNOT be checked for this — 1% audit coverage
`traces.is_degenerate` reads persisted `reasoning_stats`, so old rows are re-classifiable with no
model time. Running it over the whole tree found **1 EOS'd loop in 5,835 rows**, which looks
reassuring and **is not**: `reasoning_stats` only arrived with harness v2 (2026-08-11), and
`benchmark/m1/stats_coverage.py` measures the audit's real reach:

| bench | rows | with stats | coverage |
|---|---|---|---|
| mbppplus_samples | 3,402 | 0 | 0% |
| humanevalplus_samples | 1,476 | 0 | 0% |
| humanevalplus / mbppplus / livecodebench / math500 / aime / capacity | 869 | 0 | 0% |
| **ifeval** | 50 | 50 | **100%** |
| **TOTAL** | **5,835** | **50** | **1%** |

So the finding is **1 loop in 50 AUDITABLE rows = 2%**, with **99% of the corpus UNKNOWN, not
clean**. Whether past `conv%` figures were over-optimistic is **unknowable from the persisted data** —
it can only be established by re-running an axis under the v2 harness. Every new run is auditable
(the generate path persists stats), so this closes going forward but not backward.

## PHASE-2 RE-VERIFY (operator-authorised 2026-08-13): #4 suffix CONFIRMED, #5 GQA kernel UNFALSIFIABLE

Prompted by the APC finding — a shipped, documented Phase-2 "win" that turned out absent. If one of
three evaporated silently, the others needed checking.

### #4 suffix (prompt-lookahead) decoding — **CONFIRMED, real**
Measured incidentally by the determinism 2x2: same box, same session, same truncated config, 3 reps
each — **23.8 s mean wall with suffix ON vs 30.3 s OFF = 1.27×** on a novel coding prompt (recorded
claim: 2.41× verbatim / 1.09× novel; a novel-ish prompt with repeated structure landing between them
is consistent). Also confirmed ACTIVE at the worker cmdline (`--draft-kind suffix --draft-block-size
16 --suffix-min-match 2`). **Keep.**

### #5 fused quantized-KV GQA tile-reuse decode kernel — **cannot be re-verified at runtime**
| check | result |
|---|---|
| Is the fused kernel the default? | **Yes.** `turboquant.py:6332` reads `getattr(self, "_decode_2pass_use_legacy", False)` → default `False` → fused path. |
| Can it be A/B'd? | **NO.** `_decode_2pass_use_legacy` appears in **exactly one place in the whole fork — the `getattr` that reads it.** Nothing ever sets it: no env var, no CLI flag, no test. It served a one-off micro-bench and is now **dead code**. |
| Does its precondition hold? | **Yes for both winners.** The kernel sets `heads_per_group = 2 if n_repeats % 2 == 0 else 1`, and at `G=1` the tile-reuse **degenerates to the legacy R-redundant read, i.e. no benefit at all**. Distill: 24 q-heads / 4 kv-heads → `n_repeats 6` → **G=2**. Ornith: 16 / 2 → `n_repeats 8` → **G=2**. |
| Does it apply to Ornith? | **No** — it is the *quantized*-KV 2-pass path, and Ornith ships fp16 KV (`kv_bits: 0`). Consistent with the Phase-2 record ("does NOT beat native fp16 → Ornith stays fp16"). It is a **distill-only** lever. |

**So the recorded "lossless, ~1.3× over legacy TQ, +2–7% end-to-end" is UNFALSIFIABLE as shipped** —
structurally the same problem as APC: an optimization we cannot check is running well. The difference
is that this one is at least *on the path* by default and its precondition is satisfied, whereas APC
was measurably inert.
**Fix proposed, NOT applied:** add an env hook (e.g. `TQ_DECODE_2PASS_LEGACY=1`) in the parent fork so
the toggle is reachable and the claim can be A/B'd same-box/same-session. Small change; without it the
lever is permanently unauditable.
**Note for the speed question:** since the kernel is already the default and its precondition holds,
there is no *unbanked* speed win here. Qwen3.6-27B-Opus-Distill-OptiQ-4bit remains the campaign's wall-clock bottleneck
(3.9× Ornith per aider case) with this lever already engaged.

### ⚠️ GENERAL LESSON — a perf lever with no runtime toggle is unauditable by construction
Three Phase-2 wins, three different verification states: #4 re-verified and real; #5 on-by-default but
with its A/B path deleted; #1 (APC) **absent**. Any future lever should ship with an env-toggle *and* a
counter/stat that proves it engaged (APC's own `/metrics` block is what made its inertness provable —
that part of the design was right).

## ⚠️ APC IS INERT ON THE DEPLOYED STACK — zero memory cost AND zero benefit (2026-08-13)

Operator question: APC is acceptable if it buys TTFT for free, but not if it eats memory that pushes
a candidate out of consideration against the ≤46GB @256K gate. **Measured answer: it currently costs
nothing, because it does nothing.** `benchmark/bench/probe_apc_memory.py` (+12 tests).

### The memory measurement: identical to nine decimal places
M5, Ornith-1.0-35B-mlx-uniform-4bit, kv 65536, router restarted before each arm so
`mx.get_peak_memory` is a clean high-water mark. 5 requests with **mutually unique** prefixes
(unique marker at the FRONT — APC matches on prefixes, so a shared head would hit instead of store),
44,945 prompt tokens prefilled vs the pool's 32,768-token capacity, i.e. enough to force the
**ceiling** rather than sample a light session:

| arm | router env | max `peak_mem_gb` | prefill |
|---|---|---|---|
| APC absent | no `APC*` vars (verified per-pid) | **22.957264336** | ~2,990 tok/s |
| APC on | `APC_ENABLED=1 APC_NUM_BLOCKS=2048` (verified in **worker** env too) | **22.957264336** | ~2,990 tok/s |

Bit-identical across a router restart. That is not "APC is cheap" — it is a signal that nothing was
cached, and it was treated as such rather than reported as a convenient null.

### Confirmed: APC is enabled but NEVER CONSULTED
The worker's own `/metrics` (`server.apc`, worker :8091) reports:

```
enabled: true, num_blocks: 2048, block_size: 16
pool_used: 0   lookups_hit: 0   lookups_miss: 0   stores: 0
matched_tokens: 0   rejects: 0   rejects_by_reason: {}   resident_bytes: 0
```

**`lookups_miss: 0` is the smoking gun.** A rejected or missed lookup would still be *counted*; zero
lookups means APC is never asked. And functionally, the same 9K-token prefix served three times shows
no reuse at all — prefill **3.10 → 3.00 → 3.00 s** (~1.03×) against the recorded **34–147×**.

### ✅ MECHANISM RESOLVED (2026-08-13, later the same day) — session caching SHADOWS APC by construction
Earlier this entry recorded the mechanism as OPEN. It is not. `server/generation.py:2455-2464`:

```python
if prompt_cache_state is not None:
    self._process_cached_request(...)      # session-cache path, runs inline
    continue                               # <-- skips everything below
if batch_gen is None:
    batch_gen = BatchGenerator(..., apc_manager=self.apc_manager, ...)   # the ONLY apc call site
```

**`apc_manager` is passed at exactly one place — the BatchGenerator — and any request that resolves to
a session `continue`s past it.** `_process_cached_request` never receives `apc_manager` at all. The
fork's own comment says so: cached requests "run inline on this daemon thread … and skip continuous
batching — single-chat semantics, snapshot rewind, prefix reuse."

So APC and session caching are **mutually exclusive per request**, and session caching wins whenever a
session exists. The measured 0 lookups were not a bug — they are the design. And since the campaign's
own probe traffic all resolves to sessions (anonymous requests route by chained message hashes), APC
was structurally unreachable throughout.

**This also reconciles the two measurements that looked contradictory:**
- *growing conversation* (append) → session cache hits → **incremental prefill, 17× cheaper per total
  token** (measured; see the multi-turn design spec §1.1).
- *identical repeated request* (my APC functional test) → after turn 1 the session's history is
  `[user + assistant]`, so re-sending only `[user]` does not EXTEND it — it is a **rewind**, and
  `PromptCacheState`'s docstring notes that for hybrid GatedDeltaNet models (Qwen 3.5/3.6, i.e. both
  our winners) rewinds fall back to full re-prefill unless the snapshot ring restores them. Hence no
  speed-up on the repeat, no APC lookups, and no contradiction.

### Three candidate mechanisms tested, all ELIMINATED (superseded by the resolution above)
1. **Env not reaching the worker** — ruled out: `APC_ENABLED=1`/`APC_NUM_BLOCKS=2048` are present in
   the *worker* process env (`ps -Eww` on the worker pid), not just the router's.
2. **Suffix decoding conflicts with APC** — plausible from
   `server/generation.py:2487-2493`, whose comment says suffix "is single-sequence and only wired on
   the cached/inline path" and force-sets `draft_model=None` on the batch path. **Falsified:** with
   suffix commented out of the registry and the router restarted, APC still reports 0 lookups /
   0 stores / 0 resident bytes.
3. **The mlx-serve router mangles the request** — ruled out: calling the worker **directly on :8091**,
   router bypassed, also yields 0 lookups and no reuse (3.25 → 3.08 s).

Those three were the right eliminations but the wrong family of hypothesis — see the resolution above.
Deployed submodule was verified to match the parent fork on the relevant lines, so this was never
fork/submodule skew.

### 🔑 HOW APC AND SESSION CACHING COMPOSE — they don't, and that settles the config question
| | **session caching** (`PromptCacheState`) | **APC** (`APCManager`) |
|---|---|---|
| what it holds | the LIVE KV cache + token history for one conversation | a pool of content-hashed KV *blocks* (16 tokens each), any-to-any |
| keyed by | `chat_id`, or chained per-message sha256 for anonymous clients | hash of block content |
| reuse case | the **same conversation growing** (turn N+1 extends turn N) | **different** requests sharing a prefix |
| request path | inline handler, `continue`s past the batch generator | batch generator only |
| can both serve one request? | **NO — mutually exclusive by construction** | |

**Overlap:** they solve the same problem (skip re-prefill of a shared prefix) for *disjoint* traffic
shapes. Session caching covers the growing conversation; APC covers cross-conversation sharing.
**Coexist:** they can both be *enabled*, but never both *apply* — the session path always wins, so
APC's reachable share of our traffic is only requests with **no** session match.

**In our deployment, APC's entire remaining value is one narrow case:** a *new* conversation reusing
the ~18K-token system prompt a previous conversation already paid for (opencode sends ~18,050 prompt
tokens for a four-word request). At ~2,990 tok/s that is roughly **6 s saved per new conversation
start**, and nothing at all within a conversation.

**RECOMMENDATION — turn APC OFF for the daily driver too (`runserver.sh`), not just for benchmarks:**
1. **Zero measured benefit today** (0 lookups, 0 stores) and, even repaired, a ceiling of ~6 s per new
   conversation — while the mechanism that actually matters, session caching, is entirely independent
   of it.
2. **Non-zero demonstrated risk:** at the old `APC_NUM_BLOCKS=16384` it cost ~33GB and took the stack
   to 54.2GB / 4.1GB free with a Metal OOM, and those failures were being scored as MODEL failures.
   The pool is now bounded at 2048, but the risk class is real and the reward is ~6 s.
3. **It collapses a documented measurement hazard.** `runserver.sh` setting `APC_ENABLED=1` while the
   benchmark recipe omits it is exactly why "past benchmark runs silently differed from the daily
   driver" is on the record. Turning it off in both places makes the served configuration and the
   measured configuration **identical**, which is worth more than 6 s.
4. Keep the code, the `/metrics` counters and the ≤4096 pool guard: the counters are precisely what
   made the inertness provable, and a future multi-tenant deployment could want it.

Operator instruction already stands that APC is never used for benchmarking; this extends the same
conclusion to the daily driver on measured grounds rather than policy.

### What this means for the decision
- **APC cannot cost any candidate its gate.** It consumes zero bytes, so the ≤46GB @256K admissibility
  of every candidate is untouched. The operator's constraint is satisfied — trivially, and for the
  wrong reason.
- **The daily driver is NOT getting the win it is documented to get.** `runserver.sh:80` ships
  `APC_ENABLED=1 APC_NUM_BLOCKS=2048`, and Phase-2 recorded "**#1 APC prefix caching = DONE → SHIP**,
  agentic multi-turn TTFT 54.5×@7.5K → 147×@25K". On the current stack that win is **absent**. Either
  the Phase-2 measurement ran on a configuration we no longer ship, or a regression has landed since.
  **That recorded result should be treated as UNRELIABLE until re-measured.**
- **The 2048-block pool fix is still correct** and should stay: it bounds the ceiling if APC is ever
  repaired, and the guard test keeps it ≤4096.
- **The benchmark policy is unaffected** — runs keep APC absent, which is now known to be
  indistinguishable from APC present anyway.
- **Ornith was the right model to measure** as the conservative case: fp16 KV gives it the *larger*
  per-block cost, while Qwen3.6-27B-Opus-Distill-OptiQ-4bit (4-bit KV, ~4× smaller blocks) has the *tighter* headroom
  (43.3GB vs the 46GB gate). A zero on Ornith is a zero on Qwen3.6-27B-Opus-Distill-OptiQ-4bit. If APC is repaired, the
  ceiling to re-check is "the KV of 32,768 extra tokens for that model" — blocks × block_size is a
  token capacity, so the cost is `kv_bits`-dependent and must be re-measured per model, not assumed.

## P1a — opencode GO/NO-GO: **GO**, after fixing a blocker in our own shipped config (2026-08-13)

`benchmark/m1/p1a_opencode_smoke.sh` + manual gate runs, M5, opencode **1.18.15**, Ornith resident.

### ⚠️ BLOCKER FOUND AND CONFIRMED — the shipped `opencode.json` does not load at all
`configgen/emitters/opencode.py:17` emits a top-level **`_generated`** provenance key.
opencode 1.18.15 validates its config strictly and **rejects the whole file**:

```
Error: Configuration is invalid at ~/.config/opencode/opencode.json
  ↳ Unrecognized key: _generated
```

Every gate failed with `rc=1` and **zero requests reached :8000** — not because of #5674, but
because our own generated config is invalid for this version. Confirmed by removing only that key:
the config loads and all four `mlx-local` models resolve, including both winners. **This is a live
defect in a shipped carrier, and it would have been read as "#5674 confirmed, opencode unusable" —
the wrong conclusion, and one that would have cancelled a harness the plan calls the primary
driver.** (`configgen/emitters/vscode.py:11` emits `_generated` too, but into a JSON *array* element
for a different consumer — needs its own check, not assumed broken.)

### With that fixed, all three gates PASS — #5674 does NOT affect 1.18.15
| gate | test | result |
|---|---|---|
| **(a) endpoint reach** | tuned config as shipped | **PASS** — `200`, `model=Ornith-1.0-35B-mlx-uniform-4bit`, reply `OK`, `completion=45` |
| **(b) standard params forward** | `options.max_tokens: 7` (registry default 102400) | **PASS** — `completion=8`, vs 45 baseline |
| **(c) non-standard extras forward** | `options.thinking_budget: 16` (default 81920) | **PASS** — `completion=261` vs **740** baseline, same 18,093-token prompt |
| **(c′) extras, independent probe** | `options.enable_thinking: false` | **PASS** — `completion=200`, and `prompt` shifts 18,093 → **18,095**, i.e. the flag reached the worker and changed the CHAT TEMPLATE |
| **(d) scriptable** | `opencode run [message..]` | **PASS** — real non-interactive mode |

Gates (b) and (c) exercise **different mechanisms** — the AI SDK maps `max_tokens` itself, while
`thinking_budget`/`enable_thinking`/`min_p` must ride through as pass-through body params — so
(b) passing would not have implied (c). Both pass, so **the tuned sampling genuinely lands** and
opencode is a valid carrier for tuned comparisons. The `prompt` token count shifting under
`enable_thinking: false` is the strongest single piece of evidence: only the worker's chat template
could change it.

**Why the readback is behavioural rather than log-based:** there is **no resolved-sampling log line**
to read. AGENTS.md/FU-2 says "resolved sampling is logged at INFO", but the fork logs no merged
params, mlx-serve sends worker **stdout to DEVNULL** and only stderr to
`$TMPDIR/mlx-manager-logs/<model>.log` (`process_manager.py:387`, truncated per load), and those
files contain no sampling fields. **And such a line could not answer the question anyway:** under
FU-2 the registry fills every omitted field and opencode's values are IDENTICAL to the registry's,
so `temperature=0.4` would appear whether opencode forwarded it or sent nothing. The readback must
use values that DIFFER from the registry default — which is what the gates above do.

### Cost fact for the harness gradient (measured, not estimated)
opencode sends **~18,050 prompt tokens for a four-word request** (system prompt + tool schemas).
That is the "heavy" end of the gradient quantified: every opencode turn pays ~18K prefill before the
task, against pi's target of <1K. Budget the gradient accordingly — and note `pi` is **absent from
both boxes**, so it remains unbudgeted engineering, not a ready arm.

### Carried caveats
- **Version skew:** driver box runs opencode **1.18.0**, M5 runs **1.18.15**. #5674 is
  version-dependent; these results are 1.18.15 only. Run harness work on M5.
- **`small_model` points at :8092**, which the lean bench router does not start. It did not break
  these single-turn gates, but title/summary calls in longer sessions will hit a dead endpoint —
  the same class of hazard already documented for aider's `weak_model_name`.
- M5's deployed config is currently the repo config **minus `_generated`** (a temporary local
  deployment for validation), pending the configgen fix.

## DETERMINISM IS CONFIG-DEPENDENT — suffix decoding is the source, truncation masks it (2026-08-13)

**This AMENDS "Unseeded requests are DETERMINISTIC" (HARNESS V2 §1 below), which is true only
under a condition that was not stated.**

The Tier-0 audit turned up a contradiction: `t0.4_mp0.0` and `collapse_minp_only` have
**byte-identical params** yet produced **2,941 vs 2,841** completion tokens on `run_convergence`'s
**hardcoded** `CODING_PROMPT` — a constant string, so neither the live-measured `cpt` (4.61 in all
11 cells) nor a task seed can account for it. Meanwhile three cells differing only in inert knobs
were exactly equal. So determinism held in some cells and failed in others.

Every cell that reproduced had a truncation knob active; the pair that diverged had all three off.
That makes the naive isolation test ("one config twice with suffix ON, twice with OFF")
**confounded** — at the deployed config truncation is active, so it reproduces under both suffix
states and would have *falsely exonerated* suffix decoding. Truncation has to be a factor:

**2x2, Ornith-1.0-35B-mlx-uniform-4bit, M5, same box/session, APC absent, temp 0.4,
`presence_penalty` 0.0, 3 reps per cell, byte-identity decided on sha256 of the returned
reasoning + content** (`bench/probe_determinism.py`; suffix toggled in the registry with a
router restart between arms, and verified **at the worker cmdline** — the suffix-OFF worker
carries no `--draft-*` argument — not merely assumed from the yaml):

| | truncation ON (deployed 0.95 / 20) | truncation OFF (1.0 / 0 / 0.0) |
|---|---|---|
| **suffix ON** (shipped) | byte-identical, 1 sig/3 (ct 2,364 ×3) | **DIVERGENT, 3 sigs/3** (ct 2,825 / 4,467 / 3,736) |
| **suffix OFF** | byte-identical, 1 sig/3 (ct 2,318 ×3) | byte-identical, 1 sig/3 (ct 3,127 ×3) |

**Suffix decoding is the source of the nondeterminism, and tail truncation masks it.** With the
tail unclipped the sampler ranges over the full vocabulary, where suffix decoding's kernel numerics
flip sampled tokens — and the effect is not marginal: a **1.6× spread** in generated length
(2,825 → 4,467) at a fixed config. Clip the tail and it vanishes; turn suffix off and it vanishes
even unclipped. This is the mechanism behind AGENTS.md's "inherently non-lossless — kernel numerics
flip greedy argmaxes", now localized to the untruncated path and measured at the byte level.

**What this does and does not change:**
- **The deployed config is SAFE.** All four sampling carriers ship `top_p 0.95 / top_k 20`, so every
  client and every `deployed`-profile benchmark row runs on the truncated, reproducible path. The
  HARNESS V2 §1 conclusion stands **for the deployed config**; it does not generalize to arbitrary
  sampling, and the qualifier now needs to travel with it.
- **The Tier-0 `min_p = 0.0` column was measured on a nondeterministic path** (4 of 11 cells:
  `t0.2_mp0.0`, `t0.4_mp0.0`, `t0.6_mp0.0`, `collapse_minp_only`), because the grid deliberately set
  `top_k 0 / top_p 1.0`. At `--samples 2` those cells are largely noise, and any ρ built on them
  correlates noise with noise. **Fix: hold `top_p`/`top_k` at the deployed values and vary `min_p`**
  — which also makes the grid measure the path we actually serve.
- **Suffix ON and OFF are different fixed points, not the same output.** At the same truncated
  config they disagree (ct 2,364 vs 2,318, different hashes) while each is internally reproducible.
  So the shipped "quality-neutral" finding is an *aggregate* claim (he+/mbpp+/LCB within noise), and
  remains one; it never implied identical text, and these rows confirm it does not hold at the byte
  level.
- **KEEP suffix ON.** The operator's stated reason is latency and it holds here: same box, same
  session, same truncated config, 3 reps each — **23.8s mean wall with suffix ON vs 30.3s OFF, a
  1.27× speedup** on a novel coding prompt (consistent with the recorded 1.09× novel / 2.41×
  verbatim). Disabling it to buy reproducibility would be paying a real latency cost to fix
  something the deployed truncation already prevents.

## HARNESS V2 — measurement findings (2026-08-11)

Plan: `docs/superpowers/plans/2026-08-11-harness-v2-reliability-and-agentic-axes.md`. These are
HARNESS results, not model results — no candidate ranking changes. Three of them bear on how the
existing rows should be read.

### 1. Unseeded requests are DETERMINISTIC — every historical single-sample row is a fixed replay
⚠️ **AMENDED 2026-08-13 — true only when the sampler TRUNCATES the tail.** With suffix decoding ON
(shipped on both winners) and `top_p 1.0 / top_k 0 / min_p 0.0`, three identical unseeded requests
returned **three different** outputs spanning 1.6× in length. The deployed config truncates
(`top_p 0.95 / top_k 20`), so everything below holds for it — but the qualifier must travel with the
claim. See "DETERMINISM IS CONFIG-DEPENDENT" above for the 2x2 that isolates it.

Measured on the live stack: with no `seed` in the request, three draws of one prompt at
temperature 0.8 returned **byte-identical** text; `seed=7` twice is identical, `seed=8` differs.
The worker keys its sampler per request (`DEFAULT_SEED = 0`) and the suffix-decoding path shipped
on both winners keys off `(seed, row_id, position)`. The router forwards the whole body with no
allowlist (`router.py:514`), so a request-level seed reaches the worker unchanged.

Two consequences:
- **For NEW multi-sample work:** `--samples k` without per-draw seeds would have produced k
  IDENTICAL rows — pass^k would collapse to pass@1 and reliability would report perfect stability
  for every model while appearing to work. Every draw now carries
  `rowschema.sample_seed(item_id, sample)` (blake2b, not `hash()`, which is salted per process).
- **For the EXISTING rows:** they are unaffected as estimates (one draw per item, each item a
  different prompt), but they are **deterministic replays, not resampleable draws**. So the
  reproducibility of a re-run at the same config was never evidence of low variance — re-running
  the same items at the same temperature reproduces the same answers by construction. AGENTS.md's
  "temp 0.7 means single-sample runs carry variance" holds ACROSS items; it does not mean a re-run
  would have landed differently. Any past claim that a repeated run "confirmed" a number needs
  re-reading in that light.

### 2. `model_params.py` had drifted from what we deploy (would have mis-measured every new axis)
`PARAMS` is family-uniform, so per-model operating temperatures were unrepresentable, while FU-2
made `main_models.yaml` `generation_defaults` the deployed truth. Audited: QWEN `production` =
temp 0.7 / min_p 0.03 / **presence_penalty 0.3**, but deployed `Ornith-1.0-35B-mlx-uniform-4bit` =
temp 0.4 and `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` = temp 0.3, both at `presence_penalty 0.0` —
and Qwen3.6-27B-Opus-Distill-OptiQ-4bit was **not registered in PARAMS at all** (it reached QWEN by a name substring).
A nonzero `presence_penalty` also DISABLES suffix decoding, so the old profile would have measured
a different serving path too. New `deployed` profile reads the registry; verified live (rows carry
temperature 0.4). A drift-guard test now fails if a registry model is added without its sampling.

### 3. Benchmark runs and the daily driver differed on APC
`runserver.sh:74` sets `APC_ENABLED=1`; the AGENTS.md benchmarking router recipe omits it. So runs
launched per the recipe had prefix caching OFF while the daily driver had it ON — a knob worth
34–147× on TTFT. APC state is now recorded in every manifest (fingerprint v2) and `compare`
refuses a speed/memory comparison across differing APC state. APC itself is **not** benchmarked
(operator decision: it is a serving-layer cache, not a model capability).

### 4. Edit-format probe — first real row (measured on the 48GB M4 Pro DRIVER box)
`preflight.check_edit_format` (5 min/model, replaces the 2-hour gemma stuck-run discovery):

| model | diff | whole | recommended | note |
|---|---|---|---|---|
| `Ornith-1.0-35B-mlx-uniform-4bit` (19GB) | ✅ | ✅ | **diff** | emits a clean SEARCH/REPLACE block that applies; confirms its shipped `edit_format: diff` on evidence, and confirms `whole` is a known-good fallback |
| `gemma-4-31B-it-qat-6bit` (29GB) | — | — | — | **NOT MEASURED** — `probe_error`; see below. NOT a model verdict |

**BOX ATTRIBUTION, corrected 2026-08-11:** both probes ran on the **48GB M4 Pro driver box**, not on
the retired M2 Max — `hw.memsize` read 51.5GB (= 48GiB) at the time, so the swap had already
happened and I should have caught it. What survives the correction:
- **The Ornith row STANDS.** Edit-format adherence is a capability property and is box-independent.
  Likewise the deployed-profile plumbing validated in §2 (rows carrying `temperature: 0.4`) and the
  seed determinism in §1 — all config/plumbing facts, not hardware facts.
- **Nothing about speed or memory from that box is usable at all** — different chip class, far less
  bandwidth. It is never a valid speed-comparison box, independently of RAM.
- **The gemma `probe_error` was the driver box dying, not a model result.** Loading the 29GB model
  drove available RAM to 2.7GB and took the whole local stack down (orderly `server.shutdown`, then
  the task model and the OWUI containers). Under the topology in force from 2026-08-11 that is just
  the documented policy — the driver box hosts NO campaign models — so it is **not** new evidence
  about gemma and does **not** bear on D1. It is recorded only as a caution: a 29GB load on the 48GB
  driver takes the stack with it. gemma's arms run on M5, like every model run now does.
- Ornith (19GB) did load and probe cleanly on the driver box in 10s, but per the new rule that was
  out of policy too; the probe will be re-run on M5 alongside gemma's so both arms share a box.

### Also fixed (would have produced wrong numbers)
- `grade_evalplus` keyed solutions by `task_id`, so with k samples the **last one silently won**:
  pass@1 from 1/k of the data while CIs were reported over k. Now keyed by `(task_id, sample)`.
- `grade_lcb` emitted one evaluator entry per ROW, which would have reported each draw as its own
  problem. Now one entry per problem with its k generations.
- Loop-recovery returned the post-restart retry as the item's datum — an extra draw granted
  selectively to failures, inflating `conv%` for exactly the loop-prone models under investigation.
  The first probe is now the datum, the retry is nested, and the row is marked `contaminated` and
  excluded from correctness with a reported count.
- Convergence is now scored PER ITEM as a vector `(pass@1|converged, conv%, nonconv_kinds)` with a
  pre-registered rule (`conv% ≥ 0.90` gates, `pass@1|converged` ranks). Run-level INVALID is
  retired; `acc` keeps its historical meaning. `acc_strict@<budget>` is derived and never the
  ranking key, because it rises with `thinking_budget` and the campaign holds rows at
  16384/32768/81920. **The ~40 legacy INVALID rows below still need relabelling under this rule.**
- Statistical core: items buy power, samples buy reliability. MDE (paired binary, α=.05, power .80)
  is **±32pp at N=15** and ±20pp at N=40, so the live deltas (LCB 6.7pp, aider 13pp) need ~100–470
  matched items. Intervals come from a two-stage cluster bootstrap (a pooled Wilson over N·k trials
  is ~2× too tight at k=5). `compare` refuses unmatched item sets and reports
  `inconclusive` rather than implying a tie.

## PHASE 2 — OPTIMIZATION RESULTS (perf + KV memory on the two winners) — 2026-07-08

Winners: `Ornith-1.0-35B-mlx-uniform-4bit` (pick) + `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`
(alternative). Spec: `docs/superpowers/specs/2026-07-07-phase2-optimization-program-design.md`.
Metric = `mx.get_peak_memory` (= `server_peak_gb`); prefill/decode reported separately; M5 = all
speed/mem (single-box), M2 = quality gates. Baselines are same-box (M5).

### Baselines (M5, shipped config)
| model | KV | 256K mx-peak | prefill@256K | decode@256K | retrieval |
|---|---|---|---|---|---|
| Ornith-1.0-35B-mlx-uniform-4bit | fp16 | 32.6 GB | 794 tps | 37.9 tps | 1.0 (128K 0.2 was a FLAKE — re-probe=1.0) |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | turboquant 4-bit | 37.9 GB* | 124 tps | 9.6 tps | 1.0 |

*distill 256K = 37.9 GB here vs an older 43.3 GB reading (same kv4/step-512 config); ~8 GB
headroom either way. Ornith is 3–4× faster than distill on both prefill and decode (MoE + linear-attn).

### #1 APC prefix caching — **SHIP** (lossless, flag-flip `APC_ENABLED=1`)
Agentic multi-turn (growing conversation, warm turn reuses `[sys+history]` prefix):
| model | ~7.5K | ~25K | warm TTFT |
|---|---|---|---|
| distill | 54.5× | 147× | ~2 s (flat) |
| Ornith | — | 34.3× (9.1s→0.27s) | ~0.3 s (flat) |

Warm TTFT is ~constant; speedup scales linearly with context (256K cold prefill → warm ~0.3–2 s).
**Ornith APC-on @256K mx-peak = 32.6 GB = identical to APC-off** (warm reuses live cache, not
duplicated; pool metadata cheap) → **no memory/speed cost, fits the gate.** Single-shot benches
do NOT show APC (needs a growing conversation). Mechanism note: hybrid linear-attn uses a
snapshot-rewind/replay restore, effective only at prefix-boundary reuse (the agentic pattern);
independent divergent queries get no reuse (a 1.04× false-null cost me one bad test).

### #2 quant-KV bit-width — turboquant KV is a memory-for-SPEED trade (not a free decode win)
| model | change | 256K mx-peak | decode@256K | prefill@256K | verdict |
|---|---|---|---|---|---|
| Ornith | fp16 → turboquant 4-bit | 32.6 → 26.9 GB (−5.7) | 37.9 → 27.5 (−27%) | 794 → 319 (−60%) | **KEEP fp16** (faster + lossless; memory not needed) |
| distill | turboquant 4-bit → 3-bit | 37.9 → 35.0 GB (−2.9) | 9.6 → 9.8 (flat) | 124 → 124 (flat) | **PROVISIONAL — do NOT adopt yet.** he+ **96.5%** (kv3) vs **95.7%** (kv4) is a WEAK gate: short-chain coding, ceiling'd, does NOT stress KV fidelity. Low-bit KV degrades in **multi-step math / precise long-context retrieval** (compounding attention errors) — untested. GATE PENDING: math500 + aime + multi-needle retrieval, kv3 vs kv4, OFAT. **PARKED 2026-07-08** — low memory value (−2.9 GB on the alternative model, no speed gain); revisit the reasoning/retrieval gate later before any adoption. |

**APC ships for BOTH winners (256K gate):** Ornith APC-on @256K = 32.6 GB (= APC-off);
distill APC-on @256K = 30.8 GB — both well under 46 GB. (distill 256K peak has ~±6 GB run-to-run
variance in the prefill spike — 43.3/37.9/30.8 across runs, all fit; likely Metal pool retention.)

Mechanism (transfers to B200): quantized-KV attention kernel (dequant + RHT) is slower than fp16
SDPA, so KV bit-reduction saves memory but does NOT speed decode — which is exactly what **#5
(fused MMA quantized-attention kernel)** would fix, potentially making Ornith 4-bit KV free.

### #4 suffix (prompt-lookahead) decoding — SHIP both winners 2026-07-09

Drafter-free n-gram / prompt-lookup ("suffix") speculative decoding (`draft_kind: suffix`, registry-side; engages because the carriers send `presence_penalty 0.0`). Sampler-applied → distribution-preserving under sampling (the selection-phase "non-lossless" verdict was greedy-only; empirically confirmed here). Quality gate OFF vs ON, op-temp, OFAT:

| model | he+ ON/OFF | mbpp+ ON/OFF | LCB ON/OFF | decode speedup |
|---|---|---|---|---|
| distill (dense, t0.3) | 94.0 / ~95.7* | 77.1(N35) / — | 80% (kv4) | 1.2–2.7× edit-heavy |
| Ornith (MoE, t0.4) | 93.0 / 95.0 | 86.0 / 87.0 | 93.3 / 80.0 | 2.41× verbatim / 1.09× novel |

Both **QUALITY-NEUTRAL** — every delta within N=100/15 single-sample noise, convergence intact, loops item-intrinsic (same hard items both arms, not suffix). The **MoE-hostile prior was WRONG**: Ornith's ~30/40 **linear-attn** backbone keeps the batched block-verify cheap, so suffix nets positive even on *novel* text (not just reuse). **NO `draft_cooldown`** (phase-1: cooldown hurts reuse, 2.01× vs 2.41×). Shipped on both winners (`main_models.yaml`, commit a16dbb6). *(*distill OFF he+ = the N=117 production-profile baseline, not a clean official OFAT — the OFF official arm DNF'd on the meander tax; byte-identical-@t0.3 audit + ON numbers carry the verdict.)

### #5 fused quantized-KV DECODE kernel (GQA tile-reuse) — BUILT + VALIDATED 2026-07-08

Spec: `docs/superpowers/specs/2026-06-17-…-design.md`; plan: `docs/superpowers/plans/2026-07-08-fused-quantized-kv-decode-kernel.md`. Fixed the R×=6 GQA-redundant DRAM read in the 2-pass MSE decode kernel (G≈2 heads/threadgroup, occupancy-preserving block split; spike-C2 port). Single-pass left legacy (tile-reuse regresses short-T occupancy-bound). Numerically fp32-exact (diff 0.0000; 45 tests).

**Speed — kernel micro-bench vs full-model (the important distinction):**
- **Kernel micro-bench (attention op isolated):** ~1.3–1.47× over legacy TQ on both boxes; on M5 it beat the micro-bench's fp16 bar (3-bit @256K 1.07×, 4-bit 1.16×). ⚠ **BUT that fp16 bar was `mx.fast.SDPA` on *dequantized* KV, NOT native fp16 KV** — an unfair comparison (dequant overhead). It overstated the win.
- **Full-model (M5, clean box, the real numbers):**
  - **Ornith @256K decode:** native fp16 **37.9** > 4-bit new-kernel **29.5** > 4-bit legacy **27.5** tps. New kernel narrows the 4-bit penalty (−27% → **−22%** vs native fp16) but does NOT flip it. mx-peak 26.8 GB (saves 5.8 GB vs fp16's 32.6).
  - **distill @256K decode:** 4-bit new **9.8** vs legacy 9.6 (**+2%**).
- **Why small end-to-end:** attention is only ~10/40 layers of these hybrid linear-attn models, so the kernel's ~1.3× on the attention op dilutes to +2–7% overall; and native fp16 (no dequant) beats tile-reuse-4-bit.

**Corrected implication:** quantized KV is **still a memory-for-speed trade** — the new kernel is a real but modest improvement to the TQ decode path (mainly a transferable technique), NOT a flip. **Ornith STAYS fp16** (native fp16 decode wins; the "free 4-bit" prize is NOT achieved). distill's forced-quantized decode gains a marginal +2%. The parked kv3 memory lever does NOT revive on decode-speed grounds. Follow-on (deferred): prefill MMA (M5 TensorOps / M2 simdgroup), Prod codec, gemma4 generality — but prefill is amortized by APC, so #5's remaining ROI is low for this deployment.

### FU-2 — registry-side default sampling — **SHIPPED 2026-07-09** (config-consistency, not a quality lever)
Per-model `generation_defaults` in `main_models.yaml` → mlx-serve forwards it opaquely as one
`--generation-defaults <json>` arg (no per-param names) → mlx-vlm applies each entry only when the
request omits it (**precedence request > yaml > checkpoint > hardcoded**; unknown key fails loud at
startup; resolved sampling logged at INFO). Closes the config hole where **vscode/zed carry no sampling**:
they ran Qwen3.6-27B-Opus-Distill-OptiQ-4bit at its checkpoint **temp 1.0** and Ornith at hardcoded **greedy 0.0**; now they get
the tuned op-temps + `presence_penalty 0.0` (suffix engages). `enable_thinking` moved into the block.
**Runtime-verified on M2+M5**: a no-sampling distill request resolves to `temperature=0.3 top_p=0.95
top_k=20 min_p=0.0 presence_penalty=0.0 max_tokens=102400 thinking_budget=81920 enable_thinking=True`
(the yaml, not the checkpoint's 1.0); an explicit `temperature=0.9` wins. Forks: mlx-serve 8333436,
mlx-vlm 9f087c2. Spec: `docs/superpowers/specs/2026-07-09-registry-default-sampling-design.md`.

### Remaining levers (assessment)
- **#3 eviction** — arch-limited: both winners are hybrid linear-attn (only ~10/40 layers grow a
  KV to evict); sinks+window risk retrieval. Low expected value.
- **#4 prompt-lookahead (build)** / **#5 TQ fused kernel (build)** — the real decode/prefill
  builds; each needs its own brainstorm→spec. #5 is well-motivated by the #2 finding above.
- **#6 MTP self-spec (distill)** — proven-negative prior (net slowdown); one honest shot at most.

## Sampling config (per-arch)

Sampling is per-ARCH, not unified. Each model runs at its own arch's config.

### gemma (dense + MoE) — PRODUCTION sampling

`temperature 0.7, top_p 0.95, top_k 64, repetition_penalty 1.08`

The "official" gemma rec (temp 1.0, rep_pen 1.0) causes degenerate repetition loops. Confirmed by a controlled 2×2 on HumanEval/146: temp 1.0 loops at both rep_pen 1.0 and 1.08; temp 0.7 converges at both. Temperature is the lever; rep_penalty is irrelevant and backfires. The earlier "restart fixes the stale router" was an RNG-reroll lottery, not causal — see root-cause note below.

### Qwen3.6 (incl. the Opus-distill, Qwen-arch) — OFFICIAL coding sampling

`temperature 0.6, top_p 0.95, top_k 20, min_p 0, presence_penalty 0`

Qwen converges fine at official params; its issue is genuine verbosity, not loops. Penalties are avoided for Qwen: the vendor card warns `presence_penalty` causes language-mixing, and an N=1 production-presence-0.3 sample looped it. A verbosity hill-climb is planned (top_k 20→10→5, then temp / top_p / min_p), measuring tokens AND pass@1.

## Results scoreboard

Light tier, each model at its per-arch sampling above. Graded via the official EvalPlus evaluator run in docker. `conv%` = convergence rate (`finish=stop AND completion < thinking_budget`); a run with any non-convergence is marked INVALID regardless of pass@1.

| Model | Sampling | Benchmark | Tier | N | pass@1 | conv% | valid? |
|---|---|---|---|---|---|---|---|
| gemma-4-26B-A4B-it-OptiQ-4bit (MoE) | production t0.7 | humanevalplus | light | 10 | 100% (10/10) | 100% | VALID |
| gemma-4-26B-A4B-it-OptiQ-4bit (MoE) | production t0.7 | mbppplus | light | 10 | 80% (8/10) | 90% (1 loop Mbpp/610) | INVALID |
| gemma-4-26B-A4B-it-OptiQ-4bit (MoE) | production t0.7 | aime | light | 5 | 80% (4/5) | 60% (2 loops) | INVALID |
| Qwen3.6-27B-UD-MLX-6bit-kv16 (dense) | official t0.6 | humanevalplus | light | 10 | 90% (9/10) | 100% | VALID |
| Qwen3.6-27B-UD-MLX-6bit-kv16 (dense) | official t0.6 | mbppplus | light | 10 | 80% (8/10) | 100% | VALID |
| Qwen3.6-27B-UD-MLX-6bit-kv16 (dense) | official t0.6 | aime | light | 5 | 80% (4/5) | 80% (1 loop aime25-3) | INVALID |
| gemma-4-26b-a4b-it-8bit (MoE) | production t0.7 | humanevalplus | light | 10 | 100% (10/10) | 100% | VALID |
| gemma-4-26b-a4b-it-8bit (MoE) | production t0.7 | mbppplus | light | 10 | 80% (8/10) | 80% (2 loops) | INVALID |
| gemma-4-26b-a4b-it-8bit (MoE) | production t0.7 | aime | light | 5 | 40% (2/5) | 0% (all 5 loop) | INVALID |
| gemma-4-26b-a4b-it-4bit (MoE, vanilla-4bit) | production t0.7 | humanevalplus | light | 10 | 100% (10/10) | 100% | VALID |
| gemma-4-26b-a4b-it-4bit (MoE, vanilla-4bit) | production t0.7 | mbppplus | light | 10 | 80% (8/10) | 90% (1 loop) | INVALID |
| gemma-4-26b-a4b-it-4bit (MoE, vanilla-4bit) | production t0.7 | aime | light | 5 | 60% (3/5) | 20% | INVALID |
| gemma-4-26B-A4B-it-QAT-MLX-4bit (MoE) | production t0.7 | humanevalplus | light | 10 | 90% (9/10) | 60% (4 loops) | INVALID |
| gemma-4-26B-A4B-it-QAT-MLX-4bit (MoE) | production t0.7 | mbppplus | light | 10 | 70% (7/10) | 40% (6 loops) | INVALID |
| gemma-4-26B-A4B-it-QAT-MLX-4bit (MoE) | production t0.7 | aime | light | 5 | 40% (2/5) | 20% | INVALID |
| gemma-4-26B-A4B-it-OptiQ-4bit (MoE) | production t0.7 | **livecodebench** | **mid** | 15 | 80% (E100/M86/H60) | 73% (4 loops) | INVALID |
| gemma-4-26b-a4b-it-8bit (MoE) | production t0.7 | **livecodebench** | **mid** | 15 | 80% (E100/M86/H60) | 80% (3 loops) | INVALID |
| gemma-4-26b-a4b-it-4bit (MoE, vanilla-4bit) | production t0.7 | **livecodebench** | **mid** | 15 | 66.7% (E100/M71/H40) | 7% (14 budget-hit) | INVALID |
| gemma-4-26B-A4B-it-QAT-MLX-4bit (MoE) | production t0.7 | **livecodebench** | **mid** | 15 | 66.7% (E100/M57/H60) | 33% (10 budget-hit) | INVALID |
| gemma-4-31b-it-6bit (dense) | production t0.7 | **livecodebench** | **mid** | 15 | **86.7% (E100/M86/H80)** | 80% (3 budget-hit) | INVALID |
| gemma-4-31b-it-UD-MLX-4bit (dense) | production t0.7 | **livecodebench** | **mid** | 15 | **86.7% (E100/M86/H80)** | 93% (1 budget-hit) | INVALID |
| gemma-4-31B-it-qat-6bit (dense) | production t0.7 | **livecodebench** | **mid** | 15 | 80% (E100/M86/H60) | 93% (1 budget-hit) | INVALID |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit (Qwen-arch) | official t0.6 | **livecodebench** | **mid** | 8/15 | — | DNF (3/8 conv; median 82,855 > budget) | DNF-MEANDER |
| Qwen3.6-27B-UD-MLX-6bit (dense, prod-KV) | official t0.6 | **livecodebench** | **mid** | 1/15 | — | DNF (item1 id3496 ct=82507 > 81920 budget, ~114min/item, ETA 26h) | DNF-MEANDER |
| gemma-4-31b-it-6bit (dense) | production t0.7 | **math500** | **mid** | 30 | **83.3%** | 100% (median 2000 tok) | VALID |
| gemma-4-31B-it-qat-6bit (dense) | production t0.7 | **math500** | **mid** | 30 | **83.3%** | 100% (median 2409 tok) | VALID |
| gemma-4-31b-it-UD-MLX-4bit (dense) | production t0.7 | **math500** | **mid** | 30 | 83.3%* | 67% (10 loops/budget-hit; median 8165 tok) | INVALID |
| Ornith-1.0-35B-mlx-uniform-4bit (qwen3_5_moe) | official t0.4 | **math500** | **mid** | 30 | 83.3%* | 70% (9 loops; median 23150) | INVALID |
| Ornith-1.0-35B-mlx-uniform-4bit (qwen3_5_moe) | aider t0.4 diff (dockerized) | **aider-polyglot** | **agentic** | 34 | **61.8% (pass_rate_2; pr1 17.6%; well-formed 94.1%)** | n/a | VALID |
| gemma-4-31b-it-6bit (dense) | aider t0.7 whole (dockerized) | **aider-polyglot** | **agentic** | 5 | **60% (pass_rate_2; pr1 20%; well-formed 100%)** | n/a | VALID* |
| gemma-4-26B-A4B-it-OptiQ-4bit (MoE) | production t0.7 whole (dockerized) | **aider-polyglot** | **agentic** | 5 | 20% (pr2 1/5) — **contaminated** | n/a | **INVALID** (5/5 output-token-limit: thinking ate the 32768 budget → ~0 answer) |
| Ornith-1.0-35B-mlx-uniform-4bit (qwen3_5_moe, hybrid linear-attn) | official t0.6 | humanevalplus | light | 10 | **90.0%** | 100% (median 1562 tok) | VALID |
| Ornith-1.0-35B-mlx-uniform-4bit (qwen3_5_moe, hybrid linear-attn) | official t0.6 | mbppplus | light | 10 | **80.0%** | 100% (median 943 tok) | VALID |
| Ornith-1.0-35B-mlx-uniform-4bit (qwen3_5_moe, hybrid linear-attn) | official t0.6 | aime | light | 5 | 80.0%* | 80% (1 loop aime25-3 ct82528>budget) | INVALID |
| Ornith-1.0-35B-mlx-uniform-6bit (qwen3_5_moe, 6.622bpw) | official t0.6 | humanevalplus | light | 10 | **90.0%** (=4bit) | 90% (1 loop HumanEval/67; med 1478) | INVALID |
| Ornith-1.0-35B-mlx-uniform-6bit (qwen3_5_moe, 6.622bpw) | official t0.6 | mbppplus | light | 10 | **80.0%** (=4bit) | 100% (med 1214) | VALID |
| Ornith-1.0-35B-mlx-uniform-6bit (qwen3_5_moe, 6.622bpw) | official t0.4 | **livecodebench** | **mid** | 15 | 86.7% RAW (E100/M86/H80) — **INVALID** (over-reasoned to it) | **47% (7/15; med 82130 budget-saturating)** vs 4bit's 80%@80%conv | INVALID |
| gemma-4-31b-it-6bit (dense) | BFCL prompt-mode (no-think) | bfcl-AST | tool | 1000 | **79.4%** (s74/m93.5/p71/pm84.5) | n/a (FC, no think) | VALID* |
| Ornith-1.0-35B-mlx-uniform-4bit (qwen3_5_moe) | BFCL native-FC (qwen `<tool_call>`; think~off, 3/400) | bfcl-AST | tool | 1000 | **74.9%** (s77.75/m85/p70/pm64) | n/a | VALID |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit (qwen3_5 dense, self-OptiQ 3.97bpw) | official t0.6 FC | bfcl-AST | tool | 200 | **94.0%** (s96/m96/p94/pm90) | n/a | VALID* (N=200, not the std N=1000) |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit (qwen3_5 dense) | t0.4 (temp-ladder) | **livecodebench** | **mid** | 15 | pass@1 grade-blocked (lcb datasets bug) | 9/15 (60%) converged (+1 err abc358_e), median 25713 | INVALID (conv) |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit (qwen3_5 dense) | t0.3 (temp-ladder, **op-temp**) | **livecodebench** | **mid** | 15 | **80.0% (E100/M86/H60)** | **15/15 (100%) converged, median 24406** | VALID |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit (qwen3_5 dense) | t0.3 diff (dockerized) | **aider-polyglot** | **agentic** | 16 | **75% (pass_rate_2 12/16; pr1 18.8%; well-formed 100%)** | n/a | VALID (n=5's 80% HELD @ n=16; n=34 stalled on a router-timeout loop @ case 17 — harness, not model) |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit (qwen3_5 dense) | official t0.3 | humanevalplus | light | 10 | **100%** (10/10) | 100% (median 475) | VALID |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit (qwen3_5 dense) | official t0.3 | mbppplus | light | 10 | 60% (6/10, N=10 noise) | 100% (median 366) | VALID |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit (qwen3_5 dense) | official t0.3 | aime | light | 5 | **100%** (4/4 graded; 1 err aime25-14) | 100% | VALID |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit (qwen3_5 dense) | official t0.3 | **math500** | **mid** | 30 | **81.5%** (22/27 graded; sleep-errs regenerated; ~3 hard items intrinsically error/meander) | 100% | VALID |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit (qwen3_5 dense, kv_bits4) | capacity | **256K capacity** | **gate** | — | ✅ GATE PASS 256K: mx-peak **43.3GB** (≤46, only 2.7GB headroom), retrieval **1.00** all rungs; decode **9.4 tps** @256K | ladder 160/192/224/256K = 31.9/35.3/39.8/43.3GB | VALID |
| gemma-4-31b-it-6bit (dense) | production t0.7 | humanevalplus | light | 10 | 100% (10/10) | 100% | VALID |
| gemma-4-31b-it-6bit (dense) | production t0.7 | mbppplus | light | 10 | 70% (7/10) | 90% (1 loop) | INVALID |
| gemma-4-31b-it-6bit (dense) | production t0.7 | aime | light | 5 | 80% (4/5) | 80% (1 loop) | INVALID |
| gemma-4-31b-it-UD-MLX-4bit (dense) | production t0.7 | humanevalplus | light | 10 | 100% (10/10) | 100% | VALID |
| gemma-4-31b-it-UD-MLX-4bit (dense) | production t0.7 | mbppplus | light | 10 | 80% (8/10) | 100% | VALID |
| gemma-4-31b-it-UD-MLX-4bit (dense) | production t0.7 | aime | light | 5 | 60% (3/5) | 100% | VALID |
| gemma-4-31B-it-qat-6bit (dense) | production t0.7 | humanevalplus | light | 10 | 100% (10/10) | 100% | VALID |
| gemma-4-31B-it-qat-6bit (dense) | production t0.7 | mbppplus | light | 10 | 80% (8/10) | 100% | VALID |
| gemma-4-31B-it-qat-6bit (dense) | production t0.7 | aime | light | 5 | **100% (5/5)** | 100% | VALID |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit (Qwen-arch) | official t0.6 | humanevalplus | light | 10 | 90% (9/10) | 100% | VALID |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit (Qwen-arch) | official t0.6 | mbppplus | light | 10 | 80% (8/10) | 100% | VALID |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit (Qwen-arch) | official t0.6 | aime | light | 5 | 80% (4/5) | 40% (3 loops) | INVALID |
| Qwen3.6-27B-OptiQ-4bit (Qwen-arch) | official t0.6 | humanevalplus | light | 10 | 100% (10/10) | 100% | VALID |
| Qwen3.6-27B-OptiQ-4bit (Qwen-arch) | official t0.6 | mbppplus | light | 10 | 80% (8/10) | 100% | VALID |
| Qwen3.6-27B-OptiQ-4bit (Qwen-arch) | official t0.6 | aime | light | 5 | 80% (4/5) | 80% (1 loop aime25-14) | INVALID |

Quant ladder still to run: Qwen MLX-8bit / OptiQ-4bit / oMLX-6bit; gemma dense qat-6bit.

## Methodology & validation notes

- Graded via the official EvalPlus evaluator in docker: code extraction → official docker evalplus execution → per-test results. Pipeline verified working 2026-06-24 (it discriminates correct vs subtly-buggy code — see below).
- `conv%` is enforced as a hard validity gate. A run that hits the `thinking_budget` (or truncates mid-`<think>`) is a FAIL signal to investigate, never lowered to "pass." Several light runs are INVALID on convergence even at high pass@1; rerun before they count.
- Two boxes, one model each (M2 local, M5 remote). Light-tier assignment is by arch to parallelize. Sampling, KV scheme, and box are recorded per row for auditability.
- N=10 / N=5 light samples carry variance; treat differences as relative signal, not leaderboard parity.
- MoE quant sensitivity (light, production t0.7): OptiQ-4bit, 8bit, and vanilla-4bit all converge cleanly on easy coding (HumanEval+ 100% conv); **QAT-MLX-4bit is loop-prone** (HumanEval+ conv 60%, MBPP+ conv 40% — 4-6 loops) even at production temp — a quant-specific defect, not the temp-1.0 issue. ALL MoE quants loop on hard reasoning (aime conv 0-60%) — the 4B-active arch limit. Coding pass@1 is similar across the non-QAT MoE quants (HE+ 90-100% / MBPP+ 70-80%).
- **DENSE converges where MoE loops (emerging differentiator).** The dense gemma-4-31B candidates converge cleanly on hard reasoning where every MoE quant loops: gemma-4-31B-it-**qat-6bit** is the leader — light HE+ 100% / MBPP+ 80% / **AIME 100% (5/5) at 100% convergence**, the best reasoning result + cleanest convergence in the campaign. dense 6bit & UD-4bit are also ~clean. And the dense BEATS the MoE on LCB itself — both gemma-4-31b-it-6bit and gemma-4-31b-it-UD-MLX-4bit score **86.7% (E100/M86/H80)** vs the MoE's 80% (E100/M86/**H60**), with the gap on HARD (80% vs 60%) AND cleaner convergence (UD-4bit 14/15=93%, 6bit 12/15=80% vs MoE 73–80%) — all at the SAME production budget 16384. Mechanism: the 4B-active MoE over-reasons/loops on hard items; the full-dense models reason concisely, self-terminate, and solve more. This favors the dense candidates on BOTH coding accuracy and convergence (the MoE's only edge is decode speed).
- IFEval axis currently UNAVAILABLE: the `datasets` load fails with "Feature type 'List' not found" (a datasets-version incompatibility with the google/IFEval schema). Needs a fix before instruction-following can run; the sweep skips it gracefully (acc:null, no crash).
- **MoE quant thinking-efficiency on LCB (apples-to-apples, all at production t0.7 / thinking_budget 16384 / max_tokens 32768):** the three MoE quants diverge sharply in *reasoning verbosity*, which drives both convergence and accuracy. 8bit is the most efficient (median 8031 thinking tokens, 12/15 converged), OptiQ-4bit close behind (median 11563, 11/15), but **vanilla-4bit's median (17116) EXCEEDS the budget** → 14/15 budget-hit, conv 1/15. The over-thinking costs accuracy precisely on the harder problems (pass@1 66.7% E100/M71/H40 vs 80% E100/M86/H60 for the calibrated quants) — truncated reasoning forces premature answers. This is a genuine quant defect (uncalibrated 4-bit degrades reasoning efficiency), confirmed apples-to-apples (identical budget/max_tokens/profile; not a harness artifact, not the sleep). Conclusion for the MoE: **OptiQ calibration is worth it — 8bit ≈ OptiQ-4bit ≫ vanilla-4bit**; lowering the budget would NOT "fix" vanilla-4bit (the discipline forbids it), the budget is appropriate (the better quants fit inside it).
- LCB grading requires `PYTHONPATH=$HOME/.cache/livecodebench/LiveCodeBench` (the checkout); without it `grade_lcb` degrades gracefully to `lcb_runner not available` / acc:null (so a forgotten PYTHONPATH is a visible skip, not a silent wrong number). LCB grading (mid tier) runs via `lcb_runner` directly and DOES work on macOS (no docker needed — unlike evalplus); validated on the gemma-MoE-OptiQ-4bit LCB run. The per-difficulty breakdown (Easy/Medium/Hard) is where archs are expected to separate — light-tier coding clustered at ~70-100% with no separation, but LCB already shows a gradient (OptiQ-4bit: E100/M86/H60). LCB still flags loops on AtCoder/stdin (the over-thinking trigger) -> INVALID until investigated, but the converged per-difficulty pass@1 is the differentiating signal.

### EvalPlus validation (2026-06-24)

Qwen's 90% vs gemma-MoE's 100% on HumanEval+ is an N=10, single-item difference, NOT a ranking. The one Qwen miss is HumanEval/97 (`multiply` = product of unit digits): its `(a%10)*(b%10)` is correct on base HumanEval but wrong for negatives (Python `-6%10==4`, not 6), so it fails the HumanEval+ extra test `[-6,-9]` (base=pass, plus=fail) — exactly what HumanEval+ is designed to catch; gemma handled the negative case. Magnitude matches published: the Qwen3.6 family scores ~90.2% HumanEval+ pass@1 on full EvalPlus (35B-A3B sibling, EvalPlus leaderboard issue #299). The eval discriminates correct vs subtly-buggy code (Qwen fail vs gemma pass on the same problem). Both archs are strong on easy coding (~90–100%); they do NOT separate at the light tier — differentiation is expected at mid (LCB per-difficulty) / heavy (agentic).

### Qwen3.6-27B-OptiQ-4bit light — swap-overlap provenance (2026-06-25)

During this run, a second 29GB model (gemma-4-31B-it-qat-6bit) was accidentally downloaded + briefly started on M5, co-resident with the live Qwen worker (~08:27) → a soft `memory.pressure.warn` (ram_available 16.2GB) + ~1.6GB swap; one in-flight item was swap-slowed. Verdict: **NOT tainted.** The worker never crashed/restarted (etime continuous), no allocation failure occurred (soft WARNING only), and swap is byte-identical on restore (deterministic compute → tokens unchanged, only latency). Confirmed empirically: HE+ and MBPP+ converged 100%, and the single AIME non-convergence (`aime25-14`) is a model-intrinsic hard item that also loops for gemma-31b-6bit and Qwen3.6-27B-Opus-Distill-OptiQ-4bit — not swap-induced. A swap/memory event taints SPEED/latency/memory measurements, never QUALITY (pass@1/convergence).

### Temperature ladder — gemma-4-26B-A4B-it-OptiQ-4bit LCB (2026-06-25)

First application of the AGENTS.md temperature-ladder recipe (OFAT `--temp` at fixed 32768 budget headroom, same 15 items). Result: **lowering temperature makes convergence WORSE, not better** — the curve is hump-shaped and production temp 0.7 is near its peak.

| temp | converged | budget-hit | median thinking tokens |
|---|---|---|---|
| 0.7 | 8/15 (53%) | 7 | 14,146 |
| 0.5 | 2/9 (22%) | 7 | 33,497 (> budget) |

Dropping 0.7→0.5 doubled the reasoning length and halved convergence (large effect, decision-grade despite n=9). Likely mechanism: the reasoning-exit token isn't the argmax, so lower/greedier temp keeps extending the most-probable "more reasoning" continuation and rarely samples the exit. temp 0.3 was NOT run (the descent was counterproductive). **DECISION: operate this model at production temp 0.7** (recorded LCB pass@1 80% E100/M86/H60 @ production budget). Combined with the budget finding (16384→32768 didn't help — see the THINKING-BUDGET rule in AGENTS.md), gemma-MoE's hard-LCB over-reasoning is INTRINSIC — not tunable via temp-down or budget-up. Raw rungs archived: `livecodebench.t07.jsonl` (15), `.t05.jsonl` (10, partial).

### Qwen3.6-27B-MLX-8bit light — DNF (non-convergence: MEANDERING) (2026-06-25)

**STOPPED at 16/25, marked DNF/INVALID** for non-convergence. Multiple items saturate the
81920 thinking budget generating ~82K-token traces — including an EASY coding item
(`Mbpp/596` ct=81,946) and `aime24-89` (ct=82,763) — at ~12 tok/s that's ~2h/item, projecting
~10–30h for the light tier alone. The big items HIT the budget (ct ≥ 81,920) → non-converged.

**Non-convergence TYPE = MEANDERING (over-exploration), NOT degenerate repetition.** Confirmed
via a capped-budget probe (aime24-72): the reasoning is coherent step-by-step math with
8-gram/20-gram uniqueness ≈1.00 (no verbatim loops, only one repeated expression) and
backtracking markers ("wait"×7, "actually"×3) — it re-derives and re-checks at length without
concluding. Consistent with the saved final answers being coherent (boxed) despite the
budget-saturated think. This is the `meandering` non-convergence class (vs gemma's temp-1.0
`degenerate-repetition`).

Anomalous vs the OTHER Qwen quants (OptiQ-4bit + UD-6bit converge cleanly), so suspect the
unsloth 8bit checkpoint (template/thinking handling) or genuine 8bit verbosity — not the other
Qwen results. **DEPRIORITIZED** (heaviest quant; 8-bit weights don't fit ≤46GB@256K anyway).
Harness gap surfaced: the `generate` path persists only the post-`</think>` answer, not the
thinking text, so the DNF *type* required a live probe — capture thinking for future DNF triage.

### Qwen3.6-27B-arch MEANDERS on LCB (pattern, 2026-06-26)

The Qwen3.6-27B candidates largely fail to self-terminate on hard LCB at the official 81920
budget — same MEANDERING signature as `Qwen3.6-27B-MLX-8bit` (DNF): `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`
LCB hit conv 3/8, median 82,855 (> budget), max 102,401 (hit max_tokens) → DNF (stopped at 8/15,
archived `livecodebench.DNF-meander.jsonl`). The ONLY Qwen that converged on LCB is the base
`Qwen3.6-27B-OptiQ-4bit`. `Qwen3.6-27B-UD-MLX-6bit` LCB was then run to confirm (2026-06-26):
item 1 (id 3496) `finish=stop` but `ct=82507 > 81920` budget = NON-CONVERGED (false-pass), and it
took ~114 min for that single item (driver ETA ~26h for 15) → cut at N=1 + recorded DNF-MEANDER,
making it the **3rd Qwen3.6-27B-arch model to DNF on LCB**. Net: the Qwen3.6-27B-arch is an
UNRELIABLE converger on hard coding at the official budget (a temp-ladder fix is unexplored), whereas
every dense gemma-4-31B converges cleanly (80–93%) and scores 80–87% — the dense gemma-4-31B is the
coding + convergence front-runner.

### math500 — dense-gemma reasoning + a 4-bit convergence split (2026-06-26)

All three dense gemmas score the SAME raw math500 acc (83.3%, N=30), but convergence splits
them: `gemma-4-31b-it-6bit` (median 2000 tok) and `gemma-4-31B-it-qat-6bit` (median 2409) are
both 100%-converged / VALID, while `gemma-4-31b-it-UD-MLX-4bit` OVER-REASONS (median 8165, max
17157) and the grader flags 10 looped/budget-hit items → 67% conv / **INVALID** (acc not reported).
Same box + harness, so it is genuine 4-bit tail-fragility (the same over-reasoning seen on LCB),
not stale router. Reinforces the front-runner: the 6-bit dense gemmas converge reliably; the
UD-MLX-4bit is the cheaper-but-flakier sibling. NB measurement: convergence MUST use each item's
recorded thinking_budget (gemma's, not a hardcoded 81920) — the grader's conv% is authoritative.

### Ornith-1.0-35B uniform-4bit — a converging, fast, memory-light candidate (2026-06-26)

`deepreinforce-ai/Ornith-1.0-35B` is qwen3_5_moe (HYBRID linear-attention MoE: 30/40 layers
Gated-DeltaNet linear-attn with constant state, 10 full-attn; 256 experts/8 active + shared
expert). Converted to uniform-4bit (≈19GB, 4.649bpw) via the patched fork loader (unfused-expert
sanitize, [[commit f0d50c9]]). Light tier @ official **temp 0.6**: humanevalplus **90%**, mbppplus
**80%** (both 100% conv / VALID), aime 80% (4/5 conv; one budget-hit on the known-hard aime25-3 →
INVALID). It CONVERGES on coding where its same-generation Qwen3.6-27B siblings (8bit / distill /
UD-6bit) all DNF-meandered — and these are **qwen3_5, DENSE** (verified from config: model_type
`qwen3_5`, `n_experts=None`, `Qwen3_5ForConditionalGeneration` on the 8bit + UD-6bit), NOT the
`qwen3_5_moe` an earlier draft called them. They share Ornith's *hybrid linear-attn backbone*
(identical `full_attention_interval=4`, 3:1 linear:full GatedDeltaNet layout, linear-attn dims) but
are the DENSE variant — Ornith adds MoE sparsity (256 experts / 8 active + shared expert) on top of
that RL post-training. So Ornith's convergence edge over these siblings reflects BOTH its MoE arch
AND its RL, not training alone — the comparison is a dense-vs-Ornith ablation, not same-arch.
But only at temp 0.6: the preflight canary @ production temp 0.7 saturated the
49152 budget on a trivial is_palindrome (sharp temp knee; eval at official 0.6). Decode is FAST,
**~72 tok/s** (~5-7x the dense gemmas — the linear-attn payoff).

**CAPACITY (measured 2026-06-26, fp16 KV upper-bound):** GATE PASS — 256K MLX-peak = **32.4GB** (vs 46GB
gate, 13.6GB headroom); ladder 160K/192K/224K/256K = 28.2 / 29.6 / 31.0 / 32.4GB (peak grows only +4.2GB
over 96K tokens — the linear-attn payoff in action). **Perfect needle retrieval (acc 1.00) at EVERY rung
incl. 256K → effective_ctx = full 256K.** Decode stays fast (48→37 tok/s as ctx→256K). RSS steady ~21GB
(under-counts Metal — 32.4GB is the real peak). **FIRST candidate to clear TRUE 256K**: the dense gemmas
hit the ~58GB backstop and were capped at 192K; 4-bit KV would drop Ornith's peak further still.
**LCB TEMP-LADDER (ran 2026-06-27, model-specific per recipe):** the hard-LCB meander IS temperature-tunable
for Ornith — a DRAMATIC KNEE at temp 0.3:
| rung | pass@1 | convergence | runaways (finish=length) | median tok |
|---|---|---|---|---|
| 0.6 (official baseline) | (lost*) | 3/9 (~33%) | 3+ (→102401 max_tokens) | high |
| 0.5 | (lost*) | 1/5 (~20%) | 0 (budget-sat ~82K) | ~82K |
| 0.3 | 80% (E100/M71/H80) | 11/15 (73%) | 0 | 26873 |
| **0.4** | **80% (E100/M86/H60)** | **12/15 (80%)** | **0** | **31704** |
0.3 and 0.4 BOTH hit 80% pass@1 (per-difficulty differs — M71/H80 vs M86/H60 — but n=5–7 is ±13pp noise); 0.4
converges slightly BETTER (12/15 vs 11/15) at a HIGHER temp. Per the recipe (highest temp that holds pass@1 +
converges; 0.5/0.6 meander), **operating temp for Ornith coding = 0.4.** So Ornith is NOT a hard-LCB DNF — it
needs a lower op-temp than official 0.6, and at 0.4 it's competitive with dense gemma (86.7%) / gemma-MoE (80%).
*Caveats: 0.6/0.5 raw pass@1 lost (/tmp cleanup); n=15 pass@1 noisy; some hard items still budget-hit (strict-
INVALID) but 80% pass@1 is strong; the CONVERGENCE knee (20–33%→73–80%, runaways 3+→0 by 0.4/0.3) is dramatic +
decision-grade. NEXT: agentic axes (Aider/SWE-40) @ op-temp 0.4 — Ornith's self-scaffolding differentiator.
Ornith math500 @ t0.4 launched to gauge its reasoning axis while the agentic run is set up.

### Ornith uniform-6bit — bit-width OFAT: NO quality gain over uniform-4bit (2026-07-06)

Converted `Ornith-1.0-35B-mlx-uniform-6bit` ourselves (`mlx_vlm.convert --q-bits 6`, 6.622bpw, 27G,
verified clean; router gates auto-kept at 8-bit). Ran the SAME config as uniform-4bit (fp16 KV, official
sampling) to isolate WEIGHT bit-width. Result — **higher fidelity does not help Ornith, and hurts
convergence:**
- **Light coding IDENTICAL:** he+ 90% / mbpp+ 80% (exactly the 4bit numbers). No pass@1 gain.
- **LCB @ t0.4 WORSE convergence:** apples-to-apples (both t0.4, both budget 81920) — 6bit **conv 7/15 (47%),
  median 82,130 tok (budget-saturating)** vs 4bit **12/15 (80%), median 31,704**. The 6bit meanders MORE at
  the shared op-temp — op-temp is quant-specific. **NB (graded 2026-07-07 via the fixed py3.11 pipeline):** the
  6bit's RAW LCB pass@1 is 86.7% (E100/M86/H80) — nominally *higher* than the 4bit's 80% — but it's **INVALID**:
  it got there by NOT self-terminating (8/15 budget-saturated), i.e. trading convergence for a couple more
  correct-by-the-budget answers. Per the convergence discipline that's a BAD trade, not a clean gain; the
  4bit's clean **80% @ 80% conv** is the right pick.
- **Mechanism/conclusion:** uniform-4bit is already at Ornith's quality ceiling — the RL-trained model is
  quant-robust, so MORE bits buy nothing (and shift reasoning-exit dynamics unfavorably at t0.4). **Keep
  uniform-4bit** (19G, faster, cleaner convergence). By extension, OptiQ (≈6-bit quality at 4-bit size) is
  unlikely to raise pass@1 — its value for Ornith, if any, would be SMALLER SIZE at equal quality (3.97 vs
  4.649 bpw), not a quality boost. (We still run the OptiQ convert to confirm empirically.)
- **HARNESS BUG surfaced (LCB pass@1 grading):** `grade livecodebench` now fails to load the dataset —
  `livecodebench/code_generation_lite couldn't be found on HF Hub` / "remove trust_remote_code" — even with
  `HF_DATASETS_OFFLINE=1` (cached). A datasets-version incompatibility (same class as the blocked IFEval),
  NOT network and NOT the model. Convergence still grades (from the jsonl). This blocks LCB pass@1 for the
  6bit run AND the upcoming distill / Ornith-OptiQ ladders until fixed — the jsonls persist, so pass@1 is
  re-gradable once the loader is fixed. Queued as a bug.

### OptiQ-convert Ornith — mixed recipe UNSUPPORTED on the fused-expert MoE (2026-07-06)

We DO have a local OptiQ tool (`.venv-optiq` = `mlx_optiq` 0.2.6, CLI `optiq`; we self-converted the dense
Opus-distill with it). Ran `optiq convert <Ornith bf16> --target-bpw 4.0 --reference auto`. The MoE **loaded
fine** in `mlx_lm` (native `qwen3_5_moe`, no patch needed) and the KL sensitivity/calibration pass ran — but
the mixed-precision APPLY step FAILED: `Static mixed recipe failed (may not support this model): Received
30720 parameters not in model`. **30,720 = 256 experts × 40 layers × 3 proj(gate/up/down)** — OptiQ's recipe
allocates bits per UNFUSED expert, but `mlx_lm` loads the experts FUSED (3D `switch_mlp` tensors), so the
30,720 per-expert assignments can't map. It fell back → the saved `optiq_mixed` is **8.376 bpw / 34G**
(config claims 4-bit experts but the weights are ~8-bit — config/weight inconsistent = broken), not a usable
4-bit OptiQ. (The dense distill OptiQ worked precisely because it has NO experts.)
**Conclusion:** OptiQ's mixed recipe does not support the `qwen3_5_moe` fused-expert layout, and — crucially —
the **6bit OFAT already showed there's no quality headroom to recover** (uniform-4bit is Ornith's ceiling). So
BOTH "better quant" avenues are now closed: more bits don't help (6bit), and OptiQ can't produce a valid
4-bit MoE (and wouldn't help if it could). **`Ornith-1.0-35B-mlx-uniform-4bit` is the definitive config.**
The 52G broken artifact (`~/models/Ornith-1.0-35B-OptiQ-4bit/`, optiq_mixed + uniform_4bit baseline) is
reclaimable. (A workaround would need patching `mlx_optiq` to handle fused experts — not worth it given zero
expected quality gain.)

### Distill temp-ladder — REHABILITATED: its LCB "DNF" was a temperature artifact (2026-07-06)

`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (dense `qwen3_5`, TeichAI Opus-reasoning distill, self-OptiQ 3.97bpw)
was recorded DNF-MEANDER on LCB — but ONLY ever run at official t0.6, and NEVER given the temp-ladder that
rescued its same-family cousin Ornith. Ran the ladder (same item set, budget 81920, vary only temp):
| temp | convergence | median tokens | verdict |
|---|---|---|---|
| 0.6 (official) | 3/8 | >82K (budget-saturating) | DNF-meander (as recorded) |
| 0.4 | **9/15 (60%)** (+1 sleep-error abc358_e) | 25,713 | shaky |
| **0.3** | **15/15 (100%)** | **24,406** | **CLEAN — 0 runaway** |
**The DNF was 100% a temperature artifact.** At t0.3 Qwen3.6-27B-Opus-Distill-OptiQ-4bit converges perfectly (15/15, no runaways,
healthy median) — same knee as Ornith, one notch lower (Ornith op-temp 0.4, distill 0.3; op-temp is
model/quant-specific). **Distill op-temp = 0.3.** So it was prematurely dismissed. It is now a genuinely
strong candidate: Opus-reasoning distillation + BFCL **0.94** (tool-calling, tied with the gemma-MoE leader) +
clean LCB convergence. CAVEAT vs the pick: it's a DENSE 27B → slower decode than Ornith's sparse MoE, so for
the 256K *agentic* goal Ornith's speed likely still wins; Qwen3.6-27B-Opus-Distill-OptiQ-4bit is the strongest ALTERNATIVE / a
single-shot-reasoning contender. LCB pass@1 pending the datasets-grade fix (convergence is decision-grade on
its own here). Full characterization at t0.3 (light / math500 / BFCL n=1000) running.

**AGENTIC (Aider, dockerized, diff @ t0.3, 2026-07-07):** distill = **80% pass_rate_2 (4/5, n=5)**, well-formed
100%, **0 loops / 0 context-exhaustion**, ~14.5 min/case — a CLEAN, strong agentic run (contrast the gemma-MoE
which over-reasoned to INVALID; Qwen3.6-27B-Opus-Distill-OptiQ-4bit's diff-format edits apply fine, qwen-arch like Ornith). Provisional
agentic ranking: **distill 80% (n=5) > Ornith 61.8% (n=34) > dense-gemma 60% (n=5) ≫ gemma-MoE INVALID.** TWO
big caveats before over-reading: (1) small-sample — but a higher-n re-run **CONFIRMED it HOLDS: 75% pass_rate_2
@ n=16 (12/16), well-formed 100%** (the n=34 run stalled at case 17 on a router-timeout retry loop — harness, not
model; cases 1–16 clean). So Qwen3.6-27B-Opus-Distill-OptiQ-4bit did NOT regress to Ornith-like ~62%; it's genuinely ~75–80% agentic.
NB the 75%@16 vs Ornith 61.8%@34 isn't fully matched-n (Qwen3.6-27B-Opus-Distill-OptiQ-4bit's first-16 vs Ornith's harder 34-set), but
Qwen3.6-27B-Opus-Distill-OptiQ-4bit clearly holds a strong agentic score. (2) It's a DENSE 27B, so
decode is slower than Ornith's sparse MoE — though ~14.5 min/case (diff + tight t0.3 convergence) is agentic-
viable, NOT prohibitive (and faster than dense-gemma's ~56min/case whole-format). NET: Qwen3.6-27B-Opus-Distill-OptiQ-4bit is a
genuinely strong agentic candidate we'd wrongly dismissed — but Ornith remains the pick on **validated (n=34)
agentic + faster MoE decode + PROVEN 256K capacity** (distill 256K capacity unmeasured). If Qwen3.6-27B-Opus-Distill-OptiQ-4bit holds
~70%+ at higher n, it becomes the top single-shot-reasoning + agentic ALTERNATIVE; worth a 256K-capacity probe.

**256K CAPACITY (the capstone, 2026-07-07) — VALIDATES THE THESIS.** Qwen3.6-27B-Opus-Distill-OptiQ-4bit CLEARS 256K: mx-peak ladder
160/192/224/256K = **31.9 / 35.3 / 39.8 / 43.3 GB**, retrieval **1.00 at every rung**, GATE_PASS (≤46). So a
dense-27B qwen3_5 (linear-attn) IS 256K-viable. BUT the numbers decide the 256K-agentic goal for Ornith:
- **Memory headroom:** distill **43.3GB @256K = only 2.7GB under the gate** (near the ceiling; no room for a
  browser/other apps) vs **Ornith 32.4GB = 13.6GB headroom** (comfortable). Distill KV grows +11.4GB over
  96K tokens vs Ornith's +4.2GB — the dense-27B's bigger full-attn KV (5120-hidden, 16 full-attn layers) vs
  the MoE's lighter footprint (2048-hidden, 10 full-attn).
- **Decode speed:** distill **9.4 tps @256K** vs **Ornith 37 tps** — **~4× slower**. For the agentic loop
  (decode-heavy over long context) this is decisive: a 24K-token reasoning turn is ~43 min on Qwen3.6-27B-Opus-Distill-OptiQ-4bit vs
  ~11 min on Ornith.
**CONCLUSION — Qwen3.6-27B-Opus-Distill-OptiQ-4bit exploration STRENGTHENS the verdict, it doesn't overturn it.** Qwen3.6-27B-Opus-Distill-OptiQ-4bit is the
stronger *raw-quality* model on several single-shot axes (he+ 100, aime 100, BFCL 0.94) and it clears 256K —
yet for **256K AGENTIC coding** Ornith wins decisively on the two axes that matter at long context: **decode
speed (4×) and memory headroom (5×)**. This is the campaign thesis fully evidenced: *sparse-MoE + linear-attn
(Ornith) is the right architecture for local 256K agentic coding* — even a strong dense alternative that clears
256K is too slow + too memory-tight there. `Ornith-1.0-35B-mlx-uniform-4bit` remains the pick; Qwen3.6-27B-Opus-Distill-OptiQ-4bit is
the documented strongest ALTERNATIVE / best single-shot-reasoning+tool-calling option, not the agentic pick.
(Caveat: distill capacity @ kv_bits4 vs Ornith @ kv_bits0/fp16 — different KV scheme; both clear the gate, and
the speed gap is architecture-driven, not KV. Distill aider n=34 still confirming the 80%→? small-sample.)

### BFCL tool-calling — gemma-4-31b-it-6bit + an N caveat (2026-06-26)

`gemma-4-31b-it-6bit` BFCL-AST (non-live, prompt-mode via GemmaEpiHandler — gemma has no
native FC handler): **79.4% on n=1000** (FULL category set: simple 0.74/400, multiple 0.935/200,
parallel 0.71/200, parallel_multiple 0.845/200). TWO caveats: (1) **N mismatch** — the prior
`gemma-4-26B-A4B-it-OptiQ-4bit` (MoE) scored 0.93 on **n=200** (50/cat), so the two are NOT
directly comparable. (2) **No-think**: BFCL prompt-mode emits direct function calls (~28-tok
completions, no reasoning trace) — comparable to the prior MoE protocol but NOT the daily-driver
thinking-on reality. Going forward, standardize BFCL N.

**PARITY H2H (matched full-N=1000, resolved 2026-06-27):** re-ran the MoE at full-N →
`gemma-4-26B-A4B-it-OptiQ-4bit` (MoE) = **0.94** (simple 0.96 / multiple 0.95 / parallel 0.915 /
parallel_multiple 0.915) vs `gemma-4-31b-it-6bit` (dense) = **0.794** (0.74/0.935/0.71/0.845). At
matched N the **MoE clearly WINS tool-calling** (+0.15) — notably on simple_python (0.96 vs 0.74) and
parallel (0.915 vs 0.71). So: dense gemma-4-31B leads on LCB/reasoning + convergence, but the gemma-MoE
leads on BFCL tool-calling. (The MoE's earlier n=200 0.93 held up at full-N 0.94 — robust.)

**3-WAY at matched full-N=1000, incl. Ornith (2026-07-06):** `Ornith-1.0-35B-mlx-uniform-4bit` BFCL-AST
(native FC — the model emits qwen `<tool_call>` text; thinking effectively off, only 3/400 traces carried
`<think>`, so comparable to the gemmas' no-think FC protocol) = **74.9%** (simple_python 0.7775/400,
multiple 0.85/200, parallel 0.70/200, parallel_multiple 0.64/200). Final BFCL-AST ranking:
**gemma-4-26B-A4B-it-OptiQ-4bit (MoE) 0.94 ≫ gemma-4-31b-it-6bit (dense) 0.794 > Ornith-1.0-35B (MoE) 0.749.**
Ornith is LAST on structured single-turn tool-calling — the inverse of its agentic-coding standing (Aider
61.8% pr2, where it leads). Not a harness artifact: outputs are well-formed qwen `<tool_call>` calls and the
per-category gradient (0.78→0.85→0.70→0.64) tracks difficulty, not a parse collapse. Mechanism: Ornith's RL
specialization is MULTI-TURN agentic self-scaffolding (the Aider edit loop), not single-shot API-selection;
BFCL-AST rewards the latter, which the gemma-MoE is tuned for. Takeaway: **tool-calling and agentic-coding are
distinct axes** — the gemma-MoE is the tool-calling pick, Ornith the agentic-coding + 256K-capacity pick.

### Agentic axis (Aider polyglot, dockerized) — Ornith standout; dense gemma edit-loop (2026-07-06)

**Ornith-1.0-35B uniform-4bit @ op-temp 0.4 = 61.8% pass_rate_2 (n=34; the n=10 80% was small-sample
optimism; well-formed 94.1%)** — solid agentic-edit result, and FAST (~384s/case vs the dense gemmas' ~24 min/req). Its self-scaffolding RL differentiator
shows on the axis it was built for. **Dense gemma-4-31b-it-6bit @ diff format STUCK** — looped on
exercise 1 (0 done in 2h, repeated identical 8126-tok generations): its SEARCH/REPLACE diffs don't apply
(the aider README's "misapplies edits" case) → retry loop. Fix: switched gemma served entries to
`edit_format: whole` (Ornith stays `diff`); re-running. Also fixed a litellm timeout (default 600s <
gemma's ~20min/req → timeout-retry loop) via `timeout: 3600` in the aider settings. NET so far: Ornith's
speed + lightness (19GB, 75 tok/s) make it the PRACTICAL agentic candidate; the dense gemmas are strong
single-shot but slow + finicky for the 2-attempt agentic loop.

**3-WAY agentic H2H COMPLETE (2026-07-06):** `Ornith-1.0-35B` (diff) **61.8% pr2 (n=34, VALID)** ≫
`gemma-4-31b-it-6bit` (dense, whole) **60% pr2 (n=5, VALID; ~56 min/case)** ≫ `gemma-4-26B-A4B-it-OptiQ-4bit`
(MoE, whole) **INVALID** (n=5). The MoE run is CONTAMINATED, not a clean 20%: it hit the output-token
limit on 5/5 cases — `Input ~2,283 of 98,304` (input-context FINE) but `Output ~0 of 32,768` after long
thinking = its reasoning consumed the entire 32,768 output budget, leaving ~0 for the whole-file answer
(`exhausted_context_windows` is aider's mislabel for output-limit hits). This is the SAME over-reasoning
pathology documented on LCB (the 4B-active MoE meanders/loops, conv 73%), now fatal in whole-format agentic:
whole requires emitting the full file AFTER thinking, and the MoE's thinking never leaves room. The dense
gemma reasons concisely and left budget for the file (hence 60% clean). **Mechanism, not a fluke** — but a
larger `max_tokens` (e.g. 49152–65536, within the 98K context) could disambiguate config-vs-capability;
a clean MoE re-run is BACKLOG (does not change the verdict — Ornith already wins agentic, is faster + 256K).
NET: Ornith is the PRACTICAL agentic-coding pick; dense gemma is viable-but-slow; the gemma-MoE's
over-reasoning makes it unsuitable for the whole-format agentic loop at the standard budget.

### Provenance

Grading detail and the stale-router / temp-1.0 root cause live in git history (commits through acad470) and `AGENTS.md`.
