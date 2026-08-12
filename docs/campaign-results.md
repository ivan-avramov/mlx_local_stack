# Campaign Results & Rankings (living)

Tracks results and rankings for every candidate (model, config) in the local-LLM selection campaign: picking the best LOCAL LLM + config for 256K-context agentic coding on a 64GB Apple-Silicon Mac. Evaluation is breadth-first across escalating tiers — LIGHT (humanevalplus N=10, mbppplus N=10, aime N=5) across all archs → MID (livecodebench per-difficulty, ifeval, math500) on survivors → HEAVY (full sets, gpqa, agentic axes Aider / SWE-40, judge panel). Thinking is ENABLED for all tests. NO model/arch is pruned on partial results; ranking is decided only across the full suite.

**Current phase: light-tier broad sweep.**

**⚠️ BOX TOPOLOGY CHANGED 2026-08-11 — the M2 Max 64GB laptop is GONE**, replaced by an **M4 Pro,
48GB**. Every `M2` row and note below is HISTORICAL and NOT re-measurable: the apples-to-apples rule
bars cross-box baselines and that box no longer exists, so anything still needing a LIVE baseline
must be re-run on M5. The M4 Pro driver hosts **NO campaign models at all** (~26GB headroom after the
AI session) and is a different chip class, so it is never a valid speed-comparison box — ALL model
runs are M5 runs. See `AGENTS.md` → Operating rules.

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
   aime (80%) — while the distill and gemma-qat-6bit clear it everywhere. Under the old rule those
   runs were "INVALID" and read anyway with asterisks; under the vector the statement is precise:
   *among items it converged on* Ornith is fine (math500 85.7%, LCB 91.7%), it just does not
   self-terminate reliably. That is a real, ranked deficiency for a daily driver, and it is the
   first axis on which the current pick looks worse than the alternative.
2. **The campaign's own scoreboard UNDERSTATES its best evidence.** Ornith's evalplus rows are
   **n=100**, not the n=10 recorded below — 95.0% [90,99] and 87.0% [80,93] at ±13pp are the
   best-powered quality numbers the campaign owns, and they sat unreported.
3. **"AIME 100% (5/5)" was never a differentiator.** At n=5 the MDE is ±56pp (n=4 → ±63pp). The
   gemma-qat-6bit standout and the distill's 100% are indistinguishable from each other and from
   Ornith's 80%.
4. **The distill's mbpp+ 60%** is n=10, ±40pp — also not a ranking, despite looking alarming next
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

## HARNESS V2 — measurement findings (2026-08-11)

Plan: `docs/superpowers/plans/2026-08-11-harness-v2-reliability-and-agentic-axes.md`. These are
HARNESS results, not model results — no candidate ranking changes. Three of them bear on how the
existing rows should be read.

### 1. Unseeded requests are DETERMINISTIC — every historical single-sample row is a fixed replay
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
and the distill was **not registered in PARAMS at all** (it reached QWEN by a name substring).
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
they ran the distill at its checkpoint **temp 1.0** and Ornith at hardcoded **greedy 0.0**; now they get
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

During this run, a second 29GB model (gemma-4-31B-it-qat-6bit) was accidentally downloaded + briefly started on M5, co-resident with the live Qwen worker (~08:27) → a soft `memory.pressure.warn` (ram_available 16.2GB) + ~1.6GB swap; one in-flight item was swap-slowed. Verdict: **NOT tainted.** The worker never crashed/restarted (etime continuous), no allocation failure occurred (soft WARNING only), and swap is byte-identical on restore (deterministic compute → tokens unchanged, only latency). Confirmed empirically: HE+ and MBPP+ converged 100%, and the single AIME non-convergence (`aime25-14`) is a model-intrinsic hard item that also loops for gemma-31b-6bit and the distill — not swap-induced. A swap/memory event taints SPEED/latency/memory measurements, never QUALITY (pass@1/convergence).

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
**The DNF was 100% a temperature artifact.** At t0.3 the distill converges perfectly (15/15, no runaways,
healthy median) — same knee as Ornith, one notch lower (Ornith op-temp 0.4, distill 0.3; op-temp is
model/quant-specific). **Distill op-temp = 0.3.** So it was prematurely dismissed. It is now a genuinely
strong candidate: Opus-reasoning distillation + BFCL **0.94** (tool-calling, tied with the gemma-MoE leader) +
clean LCB convergence. CAVEAT vs the pick: it's a DENSE 27B → slower decode than Ornith's sparse MoE, so for
the 256K *agentic* goal Ornith's speed likely still wins; the distill is the strongest ALTERNATIVE / a
single-shot-reasoning contender. LCB pass@1 pending the datasets-grade fix (convergence is decision-grade on
its own here). Full characterization at t0.3 (light / math500 / BFCL n=1000) running.

**AGENTIC (Aider, dockerized, diff @ t0.3, 2026-07-07):** distill = **80% pass_rate_2 (4/5, n=5)**, well-formed
100%, **0 loops / 0 context-exhaustion**, ~14.5 min/case — a CLEAN, strong agentic run (contrast the gemma-MoE
which over-reasoned to INVALID; the distill's diff-format edits apply fine, qwen-arch like Ornith). Provisional
agentic ranking: **distill 80% (n=5) > Ornith 61.8% (n=34) > dense-gemma 60% (n=5) ≫ gemma-MoE INVALID.** TWO
big caveats before over-reading: (1) small-sample — but a higher-n re-run **CONFIRMED it HOLDS: 75% pass_rate_2
@ n=16 (12/16), well-formed 100%** (the n=34 run stalled at case 17 on a router-timeout retry loop — harness, not
model; cases 1–16 clean). So the distill did NOT regress to Ornith-like ~62%; it's genuinely ~75–80% agentic.
NB the 75%@16 vs Ornith 61.8%@34 isn't fully matched-n (the distill's first-16 vs Ornith's harder 34-set), but
the distill clearly holds a strong agentic score. (2) It's a DENSE 27B, so
decode is slower than Ornith's sparse MoE — though ~14.5 min/case (diff + tight t0.3 convergence) is agentic-
viable, NOT prohibitive (and faster than dense-gemma's ~56min/case whole-format). NET: the distill is a
genuinely strong agentic candidate we'd wrongly dismissed — but Ornith remains the pick on **validated (n=34)
agentic + faster MoE decode + PROVEN 256K capacity** (distill 256K capacity unmeasured). If the distill holds
~70%+ at higher n, it becomes the top single-shot-reasoning + agentic ALTERNATIVE; worth a 256K-capacity probe.

**256K CAPACITY (the capstone, 2026-07-07) — VALIDATES THE THESIS.** The distill CLEARS 256K: mx-peak ladder
160/192/224/256K = **31.9 / 35.3 / 39.8 / 43.3 GB**, retrieval **1.00 at every rung**, GATE_PASS (≤46). So a
dense-27B qwen3_5 (linear-attn) IS 256K-viable. BUT the numbers decide the 256K-agentic goal for Ornith:
- **Memory headroom:** distill **43.3GB @256K = only 2.7GB under the gate** (near the ceiling; no room for a
  browser/other apps) vs **Ornith 32.4GB = 13.6GB headroom** (comfortable). Distill KV grows +11.4GB over
  96K tokens vs Ornith's +4.2GB — the dense-27B's bigger full-attn KV (5120-hidden, 16 full-attn layers) vs
  the MoE's lighter footprint (2048-hidden, 10 full-attn).
- **Decode speed:** distill **9.4 tps @256K** vs **Ornith 37 tps** — **~4× slower**. For the agentic loop
  (decode-heavy over long context) this is decisive: a 24K-token reasoning turn is ~43 min on the distill vs
  ~11 min on Ornith.
**CONCLUSION — the distill exploration STRENGTHENS the verdict, it doesn't overturn it.** The distill is the
stronger *raw-quality* model on several single-shot axes (he+ 100, aime 100, BFCL 0.94) and it clears 256K —
yet for **256K AGENTIC coding** Ornith wins decisively on the two axes that matter at long context: **decode
speed (4×) and memory headroom (5×)**. This is the campaign thesis fully evidenced: *sparse-MoE + linear-attn
(Ornith) is the right architecture for local 256K agentic coding* — even a strong dense alternative that clears
256K is too slow + too memory-tight there. `Ornith-1.0-35B-mlx-uniform-4bit` remains the pick; the distill is
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
