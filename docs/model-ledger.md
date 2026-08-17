# THE MODEL LEDGER — canonical, live, updated daily

**Created 2026-08-17 (operator ruling 11).** This is the single canonical record of the model
competition: the objective, today's picks, every model ever considered with its status and the
dated reasoning, and the queue of contenders. Nothing is ever deleted from the ledger — a
demotion keeps its reasons so the question is never re-asked. Update this file whenever
anything runs; the generated scoresheet lives SOLELY in `docs/campaign-results.md` (linked
below, never duplicated here). The work queue lives in `docs/PLAN.md`.

## 0. Objective and taxonomy

**The #1 deliverable is the HARNESS, not any pick: DONE = a benchmark harness that can take a
new model and produce a defensible ranking with no hand-holding** (operator, 2026-08-17).
Model picks are perpetual and revised as contenders arrive — there is no "done" for testing.

**A recommendation is a (model, tune) pair, per goal — B and C separately.**
- **MODEL** = core weights + quantization + quant algorithm. A fine-tune is a separate model.
- **CONFIG (tune)** = what the harness varies: sampling (temperature, top_p, top_k, min_p,
  penalties), KV quant scheme/bits, cache cap, speculative decoding, thinking budget.
- **RULED axes** (fixed by standing policy, never searched): thinking always ON; budget =
  generous fixed headroom, never a knob; APC off; suffix decoding OFF for all measurement
  (return condition below); `presence_penalty 0.0`.
- **TUNABLE axes**: temperature (per-model ladder), KV bits, cache cap.
- Tune encoding (ruling 6): a `tune` field in the manifest + `--tune` filename suffix;
  result directories are pure registry names. Migration of the legacy encodings (`-kv4`-style
  directory suffixes, `.suffixon`/`.t03` file suffixes) is queued driver-side work.

**Goals:** **B** — coding across a repo-sized context (the 256K agentic-coding pick).
**C** — everyday driver for research, brainstorming, design.

## 1. Today's picks (2026-08-17)

### B — `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` @ tune `deployed`; runner-up `Ornith-1.0-35B-mlx-uniform-4bit` @ `deployed`

Take the runner-up if turn latency matters more than task success rate.

**What it rests on, stated precisely:** one harness. aider polyglot n=110 matched, `final`
**73.6% vs 50.0%**, McNemar **p=1.3e-05**. **The mechanism is REPAIR, not raw generation**:
matched on the 65 items *both* models failed at attempt 1, repair is **29.2% vs 56.9%,
McNemar exact p=0.00053**. Attempt 1 alone is **inconclusive** (27/110 vs 36/110, p=0.12),
so **the entire pick is a repair result** — do not read it as a general capability claim.

**Confidence: high on capability, single-instrument.** aider is retired as a harness (rows
kept, no new arms), so this evidence base is frozen until the opencode axis replaces it
(Run A, queued). The protocol-conflation objection that retired aider does NOT undermine this
comparison — both winners are fluent under `diff` (0.036 and 0.009 malformed per case, and 0
malformed across all 22 go items each).

**On the "256K" part: NOT measured as a task.** Both clear the memory gate at 262K (32.4 GB
peak; the runner's-up companion figure of "43.3 GB" for the pick is UNDER VERIFICATION —
it matches no field in its own capacity ladder) and retrieval ladders pass, but no coding or
reasoning quality has ever been measured at depth, and the shipped config caps the designed
maximum prompt near **~159,744 tokens** anyway. **B's context requirement is currently
satisfied *by assumption*.**

**Cap provenance (ruling 7):** the n=100 coding corpus is generated at cap **131072**, not
the shipped 262144. The cap is an external ceiling: every row that CONVERGED under its
resolved thinking budget is cap-invariant and is marked **promoted-to-shipped-cap**; only
DNF/truncated rows need re-runs at 262144 (queued).

### C — NO recommendation is supported by the evidence

Provisional lean only: `Ornith-1.0-35B-mlx-uniform-4bit` for interactive feel,
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` for reasoning-heavy sessions. **C is blocked on
INSTRUMENTATION, not worker time**: the blind mixed-family judge panel is on record as not
reliable enough to rank (order consistency 71/42/62%, Krippendorff α=0.517); BFCL has never
run at n under a valid handler; IFEval measures short mechanical compliance, a poor proxy;
no deep-research axis exists. C-tuning is deferred until the instrument exists — tuning
against an unreliable judge optimizes noise (ruling, 2026-08-17).

### Promotion rule (ruling 2)

Promotion to pick/runner-up is a **holistic architect judgement across all axes** — leader,
runner-up and candidate together — recorded here with its reasoning, never a single-metric
trigger. The funnel's CI rules are inputs. An ambiguous picture MAY open targeted
disambiguation testing on the incumbents. Stage verdicts per candidate: *prune* (paired-delta
CI upper bound < −5pp vs leader), *park* (point negative, CI straddles), *continue*. Holm per
candidate-per-stage (ruling 10).

### Suffix return condition (O25 — ruled AND measured 2026-08-17: stays OFF)

The ruled condition — paired ON/OFF accuracy CI inside ±5pp on both winners and both benches —
is **NOT met at n=100**: measured `p_d` 0.04–0.06, deltas −1.0/0.0/+2.0/+2.0pp, three of four
CIs poke past ±5pp (one cell `equivalent`). No evidence of harm, insufficient precision to
certify. A powered demonstration needs ~126–191 items per cell; extending is an open operator
call, nothing queued. Full table in `docs/open-questions.md` O25. Measurement stays suffix-OFF
forever regardless.

## 2. The ledger — every model ever considered

Scores: see the scoresheet in `docs/campaign-results.md` (sole owner). Statuses: pick /
runner-up / candidate / queued / testing / pruned@stage-N (partial, resumable) / excluded /
demoted.

| model | status | dated reasoning |
|---|---|---|
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` | **B pick** | 2026-08-16: aider n=110 repair result (above). he+/mbpp+ n=100, ifeval n=148, math500 n=30, lcb n=15. |
| `Ornith-1.0-35B-mlx-uniform-4bit` | **B runner-up** | 2026-08-16: loses aider final 50.0 vs 73.6; faster per turn. he+/mbpp+ n=100, ifeval n=541, math500 n=30, lcb n=15. |
| `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` | **candidate** | 2026-08-16: ties every measured capability axis at 26.0 GB peak and ~2× speed; he+ 89/mbpp+ 81/ifeval 90.5 all n≥100 (suffix-OFF serving path, so its rows are guard-clean). Held back by: no reasoning row, no BFCL, aider edit-protocol contrast (3.75 malformed/case) which is serving-path-unmatched and untested under opencode (Run B queued). ifeval comparisons vs winners are ABSOLUTE-ONLY (ruling 4a — cap/sha mismatch, no three-way re-run). |
| `Qwen3.8-27B-mlx-uniform-4bit` | **queued** | 2026-08-17: self-converted 2026-08-15 (4.0 bpw, group 64), reference baseline. Hub upload in progress (ruling 5). Highest-upside family: same `qwen3_5` family as both winners; hybrid attention (16/64 full-attn layers, ~64 KiB/token KV → 262K ≈ 17.2 GB KV, clears the gate with no KV quant); vendor claims large gains on exactly goal-B axes — a HYPOTHESIS, the suite is the arbiter. Blocker: MTP-NATIVE sidecars (15 tensors, ~300 MB, in config.json) — whether `sanitize` renders them inert must be VERIFIED. |
| `Qwen3.8-27B-OptiQ-4.5bpw-mixed` | **queued** | 2026-08-17: same weights, mixed-sensitivity quantization recipe, 4.501 bpw + `optiq_vision.safetensors` + `sensitivity.json`. |
| `Qwen3.8-27B-static-mixed-4bit` | **queued** | 2026-08-17: same, static recipe `mixed_3_6`, 3.966 bpw — the one that hits the 4.0 target. |
| `gemma-4-31B-it-qat-6bit` | **demoted** | 2026-08-16: cannot be compared at all — its rows run `thinking_budget` 16384 vs the winners' 81920 and `compare` mechanically refuses cross-budget comparisons. Re-opening its agentic verdict is queued behind Run A (protocol artifact suspected). |
| `gemma-4-26B-A4B-it-OptiQ-4bit` | **demoted** | 2026-08-16: evalplus dropped by ruling O18a; he+ n=11 only. Positive note kept: its recall is QUANT-robust where the `gemma-4-26B-A4B-it-QAT-MLX-4bit` sibling's is not. Non-convergent at temp 1.0, converges at 0.7 (the temp-ladder precedent). |
| `gemma-4-26B-A4B-it-QAT-MLX-4bit` | **excluded** | 2026-08: recall fails where `gemma-4-26B-A4B-it-OptiQ-4bit` recalls (quant sensitivity is real, not architectural); tiny-n screens only. |
| `gemma-4-26b-a4b-it-8bit` | **pruned@screen (partial, resumable)** | 2026-08: early small-n screening rounds (n=3–4); family superseded by the `gemma-4-26B-A4B-it-OptiQ-4bit` representative. |
| `gemma-4-31b-it-6bit` | **pruned@screen (partial, resumable)** | 2026-08: small-n screens (he+ n=10 100%, mbpp+ 70%); family represented by `gemma-4-31B-it-qat-6bit`, which is itself demoted. |
| `gemma-4-31b-it-UD-MLX-4bit` | **pruned@screen (partial, resumable)** | 2026-08: small-n screens; aime 60% was the family's weakest reasoning row. |
| `Ornith-1.0-35B-mlx-uniform-6bit` | **pruned@screen (partial, resumable)** | 2026-08: lcb strict 40% at conv 47% vs `Ornith-1.0-35B-mlx-uniform-4bit`'s 60%/80% — the latter is the family representative; 6-bit buys no quality for +RAM. |
| `Qwen3.6-27B-MLX-8bit` | **pruned@screen (partial, resumable)** | 2026-08: small-n screens; family superseded by `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`. |
| `Qwen3.6-27B-OptiQ-4bit` (base, non-distill) | **pruned@screen (partial, resumable)** | 2026-08: small-n screens; the `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` fine-tune (a SEPARATE model by taxonomy) beat it to the shortlist. |
| `Qwen3.6-27B-UD-MLX-6bit` | **pruned@screen (partial, resumable)** | 2026-08: small-n screens, some at budget 49152 (not comparable to 81920 rows). |

**Not models (legacy tune-probe directories, to be migrated to the `tune` encoding):**
`Ornith-1.0-35B-mlx-uniform-4bit-suffix` (suffix-ON serving-path arm),
`Ornith-1.0-35B-mlx-uniform-4bit-kv4`, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit-kv3`,
`Qwen3.6-27B-MLX-8bit-kv16`, `Qwen3.6-27B-UD-MLX-6bit-kv16`, `gemma-4-31b-it-6bit-kv16` —
these are (model, tune) rows filed under mangled model names; the model column above is the
registry name, the suffix was the tune.

## 3. Standing caveats that govern reading any number here

- **Guard-clean baseline inventory (pending Phase-2 publication):** under full fingerprint
  parity, the only leader baselines a new candidate can be DIRECTLY compared against are the
  winners' humanevalplus/mbppplus n=100 suffix-OFF rows (cap 131072, `src/mlx-vlm 0c1c8b1`).
  The ifeval corpus spans three fork shas and two caps — absolute readings only (ruling 3).
- **The single box (M5 Max 64 GB) is the operator's daily machine** (ruling 8): capacity runs
  are scheduled for quiet moments, every peak-memory row records the concurrent-process
  baseline, and memory anomalies are suspected of co-residency stomping BEFORE being
  attributed to a model. Pre-2026-08-17 speed/memory rows are cross-config vs post-move rows.
- **O23 stays closed** (ruling 4b): no math500/lcb suffix-OFF re-runs — those winner rows are
  suffix-ON serving-path composites and are read as within-winner evidence only.
- **O27 open (operator action):** the pre-PII-scrub commit is still fetchable by sha on the
  GitHub remote; ruling = delete/recreate the repo if nothing there is worth keeping.
- **Run A power note:** at n=22 the paired MDE is ±27pp against an aider `final` gap of
  23.6pp — Run A is DIRECTIONAL, with a pre-registered extension rule (extend to ~157 items
  iff the point delta exceeds +5pp for either model but the CI straddles zero).
