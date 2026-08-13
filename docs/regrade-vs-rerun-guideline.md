# When to RE-GRADE vs RE-BENCHMARK — the decision rule

Created 2026-08-13. The harness changed materially in one day (six defects fixed, two new metrics), so
"which recorded numbers are still true?" became a standing question rather than a one-off. This is the
rule for answering it without either trusting stale rows or burning the single worker re-running
everything.

**The governing asymmetry:** re-grading costs ZERO worker time and re-running costs hours on a
single-worker campaign. So the default is always "re-grade first, and only re-run what re-grading
provably cannot recover."

---

## The rule, in order

### 1. Is the defect in GRADING or in GENERATION?
This is the whole question, and it is decidable by asking: **does the fix change what we would have
ASKED the model, or only what we CONCLUDE from what it said?**

| defect is in… | example | action | cost |
|---|---|---|---|
| **the grader** | LCB `-1`/`-2` sentinels scored as passes; IFEval `punkt_tab` missing; `_finalize` clobbering `acc` | **RE-GRADE** | zero |
| **a metric definition** | `acc_strict` promoted to ranking key; degeneracy detector added | **RE-GRADE** | zero |
| **the request** | wrong sampling profile; `presence_penalty` disabling suffix; thinking disabled; wrong prompt/template | **RE-RUN** | hours |
| **the serving path** | APC state, KV bits, suffix on/off, `max_kv_cache_size` | **RE-RUN** | hours |
| **the item set** | different languages/subset; contaminated items | **RE-RUN** | hours |

The two-phase harness (`generate` → `grade`) exists precisely so the first two rows are free. Use it.

### 2. Does the persisted row carry what the new metric needs?
A re-grade can only recover a metric whose INPUTS were persisted. Check before promising it:

- `acc_strict` needs `finish_reason` + `completion_tokens` + `thinking_budget` → present since v1. ✅
- The degeneracy detector needs `reasoning_stats` → **only 1% of the corpus has it** (arrived with
  harness v2, 2026-08-11; `benchmark/m1/stats_coverage.py` measures this). ❌ for old rows.
- Per-item CI/MDE needs an `items` list from the grader → some graders emit none (IFEval did not until
  today). Fixable in the grader, then re-grade. ✅

**If the input is missing, the answer is UNKNOWN — not "clean".** An audit that reports 0.0% while
blind to 99% of the corpus is not evidence of absence, and saying so is the difference between a
finding and a false reassurance.

### 3. Do the raw rows still EXIST?
Results are gitignored and per-box. The retired M2 Max took its `benchmark/results/` with it, so
anything measured only there is **not re-gradable at any price** — e.g. `gemma-4-31b-it-6bit` and
`gemma-4-31b-it-UD-MLX-4bit` LiveCodeBench at 86.7%, the two highest LCB numbers the campaign ever
recorded. Those need a fresh run or they stay unusable.

### 4. Is the number DECISION-RELEVANT, and is it RESOLVABLE at the n we have?
Re-running to refresh a row that changes no decision is waste. Re-running at an n that cannot resolve
the difference is worse — it manufactures a number that looks like evidence. Check the MDE first
(`stats.mde`): n=15 → ±32pp, n=40 → ±20pp, n=100 → ±12.5pp.

**The live example:** re-grading LCB showed three models tied at `acc` 80% but spread **60–80% on
`acc_strict`**. That 20pp spread is *inside* the ±32pp MDE at n=15 — so the re-grade did not settle it,
it turned a settled tie into a live question that needs n≈100. That is a legitimate reason to spend
worker time; "the number is old" is not.

### 5. Prefer an OFAT re-run over a full re-characterisation
If a re-run is warranted, change one thing. A model whose verdict rests on a retired convergence rule
needs the same items at the same sampling, not a fresh sweep.

---

## Verdicts that are OBSOLETE BY POLICY (no re-measurement needed to distrust them)

~20 rows are labelled `INVALID` under the **run-level convergence invalidation** rule that AGENTS.md
**RETIRED on 2026-08-11** in favour of the per-item convergence vector. Those labels are void by
policy, not by measurement. `acc_strict` is their proper replacement: it charges truncation per item
instead of voiding a whole run, which is what the old flag was reaching for.

Likewise, any verdict of the form "DNF-MEANDER" predates the distinction between **meander** (high
novelty, over-exploration — a temperature-ladder case) and **degenerate_repetition** (near-zero
novelty — a sampling/quant defect). Those are different mechanisms with different fixes, and the old
classifier could not tell them apart. ⚠️ Distinguishing them retroactively needs `reasoning_stats`,
which those rows lack — so the correct status is **UNKNOWN mechanism**, not "meander".

---

## Applying it: what to re-grade and re-run now

**RE-GRADE (free, do first):**
1. ✅ **LiveCodeBench — DONE 2026-08-13.** All 7 persisted runs re-graded under the fixed grader. The
   previously-re-graded three were unchanged, confirming the "three-way tie at 80%"; and `acc_strict`
   opened a 60–80% spread that `acc` hid.
2. **`humanevalplus` / `mbppplus` across all 17 model dirs** — never re-graded under the convergence
   vector or `acc_strict`. Zero worker time.
3. **`aime` / `math500`** — same.

**RE-RUN (worker time, ranked by decision value):**
1. **LCB at n≈100 on the three D1 candidates.** The only cheap thing that could change the campaign:
   `acc` says tie, `acc_strict` says 20pp spread, n=15 cannot resolve it. MDE ±12.5pp at n=100.
2. **`gemma-4-31b-it-6bit` + `gemma-4-31b-it-UD-MLX-4bit` LCB** — highest recorded LCB (86.7%), files
   gone with the M2 Max, numbers predate the sentinel fix. Re-run or drop the claim.
3. **Nothing else.** The four gemma MoEs are dominated on every axis; `Qwen3.6-27B-MLX-8bit` cannot fit
   ≤46GB @256K (a config fact, not a verdict); `Ornith-1.0-35B-mlx-uniform-6bit` is settled as no-gain
   and `acc_strict` makes it worse (40% vs 4-bit's 60%).
