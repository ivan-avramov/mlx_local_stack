# Campaign results — RECOMMENDATIONS + the SCORESHEET

**Structure of this doc, and why.** The top section is **my recommendations** — judgement, hand-written,
for the two picks the campaign exists to make. Below it is **the scoresheet** — pure measurement,
**generated from the persisted rows by a command**, never hand-maintained. The narrative record (every
retraction, defect, mechanism and process lesson) moved to **`docs/lab-notebook.md`** on 2026-08-14;
nothing was deleted.

The split exists because the two layers have different failure modes and must be auditable separately:
a recommendation can be wrong because I reasoned badly, a scoresheet cell can be wrong because the
measurement was bad. When they live in one hand-written narrative, every corrected number becomes a new
`RETRACTED` / `SUPERSEDES` section and ordinary measurement corrections read as churn.

**The harness (goal A) measures. It does not pick.** The picks below are mine, derived from the table,
and they are point-in-time: when a new model is run through the same suite, the table changes and these
paragraphs get rewritten.

---

# ⭐ RECOMMENDATIONS

## B — coding across a repo-sized context

> ### Pick: `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`
> **Runner-up:** `Ornith-1.0-35B-mlx-uniform-4bit` — and pick the runner-up instead if turn latency
> matters to you more than task success rate.

**What it rests on.** The one powered capability result in the entire corpus: aider polyglot at
**n=110 matched**, `final` **73.6% vs 50.0%**, McNemar **p=1.3e-05**. The mechanism is identified and it
is not raw generation ability — it is **repair**: 60.8% vs 33.7% success on the second, test-informed
attempt. That is exactly the ability an agentic coding loop consumes.

**Confidence: HIGH on capability. Two caveats that are not small:**
1. **It is aider-scaffold-specific.** There is **zero** evidence from opencode, which is the primary
   agentic driver we actually ship. A scaffold change can plausibly move a repair-driven result.
2. **`Ornith-1.0-35B-mlx-uniform-4bit` wins every latency statistic** — median 18 s vs 21 s, p95 106 s
   vs 126 s, decode **107.6 vs 28.6 tok/s** (3.8×). It emits 3.1× more tokens per item and still
   finishes first. For an interactive edit loop that is a real, measured argument for the runner-up.

**On the "256K" part of B — NOT MEASURED as a task, and the shipped config cannot do 256K anyway.**
Both models clear the memory gate at 262K context (32.4 GB / 43.3 GB peak), and retrieval ladders pass.
But **no coding or reasoning quality has ever been measured at depth**, and the config imposes a
ceiling well below 256K: `max_tokens` 102400 with a `0.8 × (cap − prompt)` thinking-budget clamp means
the **designed maximum prompt is ~159,744 tokens** for `Ornith-1.0-35B-mlx-uniform-4bit`, and lower for
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` which wants a larger thinking budget. Above that the model silently
gets less room to think. So B's context requirement is currently satisfied *by assumption*, and the
measurement that would settle it is the depth condition listed under "what would change these picks".

## C — everyday driver for research, brainstorming and design

> ### No recommendation is supported by the evidence. Provisional lean only.
> **If you want one today:** `Ornith-1.0-35B-mlx-uniform-4bit` for interactive feel (3.8× faster decode,
> and the two are equivalent on the only axis measured); `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` for
> reasoning-heavy sessions, where it does not burn its budget.

**I am not going to dress this up: C's construct has never been measured.** What exists:

- **IFEval, n=148 paired: `equivalent`** (89.9% vs 89.9%, CI inside the ±5pp TOST margin). This is a
  legitimate equivalence verdict — but IFEval measures compliance with *short mechanical constraints*
  ("all caps", "exactly 3 bullets", "use word X four times"). It is close to worthless as a proxy for
  whether a model is a good research or design partner. **Reporting it as C's basis overstates what is
  known**, which earlier revisions of this doc did at MEDIUM confidence.
  ✅ Its grader was non-deterministic until 2026-08-14 and is now reproducible; the verdict did not
  change (see defect note 2 on the scoresheet).
- **math500** (supporting, reasoning): at a matched 81,920 budget, `acc` is a tie (83.3% vs 81.5%) but
  **`acc_strict` splits 60.0% vs 81.5%**, because `Ornith-1.0-35B-mlx-uniform-4bit` hits the thinking
  budget on **9 of 30** items. Suggestive and mechanistically attributable — but n=30/27, unmatched
  items, MDE ±23pp, so the 21pp gap is at the edge of resolvable. Not a verdict.
- **BFCL** (tool calling): harness repaired, smoke passed, **never run at n**.
- **The judge panel** — the only instrument that could measure C's actual construct — is on record as
  **NOT RELIABLE ENOUGH TO RANK** (55% self-consistent at v2). A v3 extractor is built and never run.
- **No deep-research axis exists at all.**

**So C is blocked on instrumentation, not on worker time**, and that is the single most important thing
on this page. Building a research/synthesis axis and making the judge panel reliable are prerequisites
to C having an answer at all.

## What would change these picks, in order of value

1. **Make the judge panel reliable, then run it.** It is the only instrument that can speak to C, and C
   currently has none. Cheap in model time.
2. **A depth condition on B** — re-run a coding subset with a realistic repo-sized prompt (~128K, inside
   the no-clamp regime for both). Turns B's context requirement from an assumption into a measurement.
3. **opencode agentic evidence.** The B pick is aider-specific and opencode is what we ship.
4. **BFCL at n.** Fills an empty dimension and is the cheapest powered axis the suite owns.
5. **math500 at n≈100.** The 21pp `acc_strict` split is real-looking and currently unresolvable.
6. **The runaway-tax temperature ladder, measuring pass@1 alongside convergence.** ~40% of wall-clock on
   both models; a 3-item pilot showed temperature moves it, but **pass@1 is unmeasured** and AGENTS.md
   makes pass@1 the hard constraint with convergence strictly secondary.

---

# 📋 THE SCORESHEET — generated, do not hand-edit

**Regenerate with** (must run where the rows live — currently the M5 worker):

```bash
PYTHONPATH=benchmark .venv-bench/bin/python benchmark/m1/scoreboard.py --md
```

**Provenance of the table below:** generated 2026-08-14 on the **M5 Max 64GB worker** at repo HEAD
`1ce8178`, over 19 result directories. `acc` / `acc_strict` are read from the per-pair
`results/<model>/<bench>.score.json` written by `grade_all` — one file per (model, bench), so grading one
model can no longer erase another's record.

### ⚠️ TWO THINGS TO KNOW BEFORE READING A CELL

**1. `ungraded` is not a zero and not a blank — it means the grader has not been run for that pair.**
Every `humanevalplus` / `mbppplus` / `livecodebench` cell is currently `ungraded`, for a deliberate
reason: those graders need Docker (evalplus) or `lcb_runner`, both CPU-heavy, and **a timed generation
run is in flight on the same box**. Running them now would contaminate the live latency and decode-rate
measurements. They are graded once the run completes.

**2. ✅ THE IFEVAL GRADER WAS NON-DETERMINISTIC — FOUND AND FIXED 2026-08-14 (`2a27d21`, `b04030c`).**
Re-grades of *identical* rows returned different scores. **Two independent causes, and finding the
first one masked the second:**

| # | mechanism | evidence |
|---|---|---|
| 1 | **`langdetect` unseeded.** Three verifiers call `langdetect.detect()` (`instructions.py:158` `response_language`, `:1416` `english_capital`, `:1448` `english_lowercase`); `DetectorFactory.seed` was set nowhere, so it samples randomly. | distill `acc` 0.8986 / 0.8986 / **0.8919** over 3 re-grades |
| 2 | **`random` unseeded in the verifiers.** 24 sites in `instructions.py` fabricate an **absent kwarg** with `random.choice`/`random.randint` (e.g. `:1350` `self._frequency = random.randint(1, _LETTER_FREQUENCY)`) — so for those items the grader **invents the threshold it checks against**. | after fixing #1, Ornith began wobbling: 0.9002 / 0.9002 / **0.8983** / **0.9020** |

**Scope of #2, measured over 8 RNG states rather than assumed: 1 verdict of 541 (0.2%), `acc` spread
90.02–90.20% = 0.18pp.** Immaterial to every published verdict; fatal to reproducibility. Ruled out by
measurement: `PYTHONHASHSEED` (pinning to 0 still wobbled) and concurrency (`grade.py` has none).

**Fixes:** langdetect seeded at `_load_ifeval_lib`, the one seam every IFEval grade loads through; and
the verifiers reseeded **per item** from a `crc32` of the item id — not once per batch, because a batch
seed leaves each verdict dependent on how many draws preceded it, so a resume, a different `--limit` or
a reordered queue would silently change verdicts. **Verified: six independent processes, both arms,
bit-identical.**

⚠️ **What this changed about the published numbers: nothing, and that is the point.** The canonical
figures are `Ornith-1.0-35B-mlx-uniform-4bit` **90.0% / 86.7%** and
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` **89.9% / 85.1%** — i.e. exactly what was already published. The
`equivalent` verdict stands. What was broken was not the value but the *guarantee* that reading it twice
gives the same answer.

| model | bench | n | acc | strict | conv% | degen | degenWall% | budget |
|---|---|---|---|---|---|---|---|---|
| Ornith-1.0-35B-mlx-uniform-4bit | aime | 5 | 80.0% | 60.0% | 80 | - | - | 81920 |
| Ornith-1.0-35B-mlx-uniform-4bit | capacity_ladder | 2 | ungraded | ungraded | 100 | - | - | - |
| Ornith-1.0-35B-mlx-uniform-4bit | humanevalplus | 100 | ungraded | ungraded | 98 | 4 | 40 | 81920 |
| Ornith-1.0-35B-mlx-uniform-4bit | ifeval | 541 | 90.0% | 86.7% | 99 | 30 | 42 | 81920 |
| Ornith-1.0-35B-mlx-uniform-4bit | livecodebench | 15 | ungraded | ungraded | 80 | - | - | 81920 |
| Ornith-1.0-35B-mlx-uniform-4bit | math500 | 30 | 83.3% | 60.0% | 70 | - | - | 81920 |
| Ornith-1.0-35B-mlx-uniform-4bit | mbppplus | 100 | ungraded | ungraded | 96 | 4 | 63 | 81920 |
| Ornith-1.0-35B-mlx-uniform-4bit-kv4 | capacity_ladder | 4 | ungraded | ungraded | 100 | - | - | - |
| Ornith-1.0-35B-mlx-uniform-4bit-suffix | humanevalplus | 100 | ungraded | ungraded | 95 | - | - | 81920 |
| Ornith-1.0-35B-mlx-uniform-4bit-suffix | livecodebench | 15 | ungraded | ungraded | 87 | - | - | 81920 |
| Ornith-1.0-35B-mlx-uniform-4bit-suffix | mbppplus | 100 | ungraded | ungraded | 99 | - | - | 81920 |
| Ornith-1.0-35B-mlx-uniform-6bit | humanevalplus | 10 | ungraded | ungraded | 90 | - | - | 81920 |
| Ornith-1.0-35B-mlx-uniform-6bit | livecodebench | 15 | ungraded | ungraded | 47 | - | - | 81920 |
| Ornith-1.0-35B-mlx-uniform-6bit | mbppplus | 10 | ungraded | ungraded | 100 | - | - | 81920 |
| Qwen3.6-27B-MLX-8bit | aime | 5 | 80.0% | 60.0% | 80 | - | - | 81920 |
| Qwen3.6-27B-MLX-8bit | humanevalplus | 6 | ungraded | ungraded | 100 | - | - | 81920 |
| Qwen3.6-27B-MLX-8bit | mbppplus | 6 | ungraded | ungraded | 67 | - | - | 81920 |
| Qwen3.6-27B-OptiQ-4bit | aime | 5 | 80.0% | 80.0% | 80 | - | - | 81920 |
| Qwen3.6-27B-OptiQ-4bit | capacity_ladder | 1 | ungraded | ungraded | 100 | - | - | - |
| Qwen3.6-27B-OptiQ-4bit | humanevalplus | 10 | ungraded | ungraded | 100 | - | - | 81920 |
| Qwen3.6-27B-OptiQ-4bit | livecodebench | 1 | ungraded | ungraded | 0 | - | - | 49152 |
| Qwen3.6-27B-OptiQ-4bit | mbppplus | 10 | ungraded | ungraded | 100 | - | - | 81920 |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | aime | 4 | 100.0% | 100.0% | 100 | - | - | 81920 |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | capacity_ladder | 4 | ungraded | ungraded | 100 | - | - | - |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | humanevalplus | 64 | ungraded | ungraded | 98 | 1 | 54 | 81920 |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | ifeval | 148 | 89.9% | 85.1% | 99 | 10 | 57 | 81920 |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | livecodebench | 15 | ungraded | ungraded | 100 | - | - | 81920 |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | math500 | 27 | 81.5% | 81.5% | 100 | - | - | 81920 |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit-kv3 | capacity_ladder | 5 | ungraded | ungraded | 100 | - | - | - |
| Qwen3.6-27B-UD-MLX-6bit | capacity_ladder | 4 | ungraded | ungraded | 100 | - | - | - |
| Qwen3.6-27B-UD-MLX-6bit | humanevalplus | 3 | ungraded | ungraded | 100 | - | - | 49152 |
| Qwen3.6-27B-UD-MLX-6bit | livecodebench | 1 | ungraded | ungraded | 0 | - | - | 81920 |
| Qwen3.6-27B-UD-MLX-6bit | mbppplus | 3 | ungraded | ungraded | 100 | - | - | 49152 |
| Qwen3.6-27B-UD-MLX-6bit-kv16 | aime | 5 | 80.0% | 60.0% | 80 | - | - | 81920 |
| Qwen3.6-27B-UD-MLX-6bit-kv16 | humanevalplus | 10 | ungraded | ungraded | 100 | - | - | 81920 |
| Qwen3.6-27B-UD-MLX-6bit-kv16 | livecodebench | 3 | ungraded | ungraded | 67 | - | - | 49152 |
| Qwen3.6-27B-UD-MLX-6bit-kv16 | mbppplus | 10 | ungraded | ungraded | 100 | - | - | 81920 |
| gemma-4-26B-A4B-it-OptiQ-4bit | aime | 3 | 66.7% | 66.7% | 67 | - | - | 16384 |
| gemma-4-26B-A4B-it-OptiQ-4bit | capacity_ladder | 1 | ungraded | ungraded | 100 | - | - | - |
| gemma-4-26B-A4B-it-OptiQ-4bit | humanevalplus | 3 | ungraded | ungraded | 100 | - | - | 16384 |
| gemma-4-26B-A4B-it-OptiQ-4bit | mbppplus | 3 | ungraded | ungraded | 100 | - | - | 16384 |
| gemma-4-26B-A4B-it-QAT-MLX-4bit | aime | 3 | 66.7% | 33.3% | 33 | - | - | 16384 |
| gemma-4-26B-A4B-it-QAT-MLX-4bit | capacity_ladder | 4 | ungraded | ungraded | 100 | - | - | - |
| gemma-4-26B-A4B-it-QAT-MLX-4bit | humanevalplus | 3 | ungraded | ungraded | 100 | - | - | 16384 |
| gemma-4-26B-A4B-it-QAT-MLX-4bit | mbppplus | 3 | ungraded | ungraded | 100 | - | - | 16384 |
| gemma-4-26b-a4b-it-8bit | aime | 3 | 100.0% | 33.3% | 33 | - | - | 16384 |
| gemma-4-26b-a4b-it-8bit | capacity_ladder | 4 | ungraded | ungraded | 100 | - | - | - |
| gemma-4-26b-a4b-it-8bit | humanevalplus | 4 | ungraded | ungraded | 100 | - | - | 16384 |
| gemma-4-26b-a4b-it-8bit | mbppplus | 4 | ungraded | ungraded | 75 | - | - | 16384 |
| gemma-4-31B-it-qat-6bit | aime | 5 | 100.0% | 100.0% | 100 | - | - | 16384 |
| gemma-4-31B-it-qat-6bit | humanevalplus | 12 | ungraded | ungraded | 83 | - | - | 16384 |
| gemma-4-31B-it-qat-6bit | livecodebench | 15 | ungraded | ungraded | 93 | - | - | 16384 |
| gemma-4-31B-it-qat-6bit | math500 | 30 | 83.3% | 83.3% | 100 | - | - | 16384 |
| gemma-4-31b-it-6bit | aime | 5 | 80.0% | 80.0% | 80 | - | - | 16384 |
| gemma-4-31b-it-6bit | humanevalplus | 10 | ungraded | ungraded | 100 | - | - | 16384 |
| gemma-4-31b-it-6bit | mbppplus | 10 | ungraded | ungraded | 90 | - | - | 16384 |
| gemma-4-31b-it-6bit-kv16 | livecodebench | 20 | ungraded | ungraded | 75 | - | - | 16384 |
| gemma-4-31b-it-UD-MLX-4bit | aime | 5 | 60.0% | 60.0% | 100 | - | - | 16384 |
| gemma-4-31b-it-UD-MLX-4bit | capacity_ladder | 1 | ungraded | ungraded | 100 | - | - | - |
| gemma-4-31b-it-UD-MLX-4bit | humanevalplus | 10 | ungraded | ungraded | 100 | - | - | 16384 |
| gemma-4-31b-it-UD-MLX-4bit | mbppplus | 10 | ungraded | ungraded | 100 | - | - | 16384 |

## Dimension coverage — what is measured and what is missing

The suite's dimensions, as encoded in `benchmark/m1/scoreboard.py`:

| dimension | benches |
|---|---|
| **reasoning** | `aime`, `math500`, `gpqa` |
| **coding** | `humanevalplus`, `mbppplus`, `livecodebench`, `aider` |
| **daily** | `ifeval`, `bfcl` |

**Only three of 19 result directories have any dimension above n=40**, and the two winners are the only
models with a `daily` cell at all. Full per-model coverage verdicts come from the same command as the
table above. The headline gaps:

- **`gpqa` has NEVER been run** for any model — reasoning is 2/3 axes at best.
- **`bfcl` has never been run at n** — `daily` is 1/2 axes for the two winners, `NOT MEASURED` for
  everything else.
- **`aider` is missing from every row of this table**, because it runs through a separate scaffold
  (`benchmark/run_aider_docker.sh`) and does not write into this results tree. **The n=110 result that
  the B pick rests on is therefore NOT in the scoresheet** — a real gap in the record, and the next
  thing to wire into the generator.
- **`gemma-4-31B-it-qat-6bit` cannot be compared to the winners at all**: it runs at `thinking_budget`
  16384 vs their 81920, and `compare` mechanically refuses cross-budget comparisons. Its 192K context
  ceiling is a config fact, not a zero.

---

## ⚠️ COMPARABILITY RULES THAT GOVERN EVERY CELL ABOVE

- **BOX TOPOLOGY CHANGED 2026-08-11 — the M2 Max 64GB is GONE**, replaced by an M4 Pro 48GB DRIVER that
  hosts NO models. **All model runs are M5 Max runs.** Every pre-2026-08-11 result in the lab notebook is
  HISTORICAL and NOT re-measurable, so it can inform a hypothesis but never a pick.
- **A pick requires: same box, same session, matched items, matched `thinking_budget`, and the
  `deployed` sampling profile.** `compare` mechanically refuses comparisons differing in
  `thinking_budget` or `max_tokens`.
- **Every delta carries its interval and the axis MDE.** Paired binary, α=.05, power .80:
  **n=15 → ±32pp, n=40 → ±20pp, n=100 → ±12.5pp, n=164 → ±9.8pp, n=378 → ±6.4pp.** Resolving 10pp needs
  157 matched items; 5pp needs 628. **"Inconclusive" is a valid and expected answer, and is NOT evidence
  of a tie.**
- **`acc_strict`@budget is the ranking key** at a matched budget: a truncated draw scores 0 with the
  denominator intact. `acc` keeps its historical meaning so published rows stay comparable.
  `pass@1|converged` is a DIAGNOSTIC and must never rank — it conditions on convergence and shrinks the
  denominator.
- **`conv%` and `nonconv_kinds` are DIAGNOSTICS, not a gate.** The `conv% ≥ 0.90` gate is WITHDRAWN.
- **`acc` measures one thing:** the provided tests pass within the harness's attempt budget. It says
  nothing about maintainability, readability, idiom or review-acceptability — those belong to the judge
  panel, which is not yet reliable enough to rank.

## Where everything else went

| doc | holds |
|---|---|
| **`docs/lab-notebook.md`** | the full chronological record — mechanisms, retractions, defect write-ups, superseded findings, process lessons. Read it to learn WHY a number is what it is. |
| **`docs/open-questions.md`** | the operator's decision queue: OPEN / CLOSED / CLOSED-BY-MEASUREMENT |
| **`docs/campaign-queue.md`** | live work state and reboot recovery |
| **`AGENTS.md`** | rules, gates, measurement discipline, traps |
