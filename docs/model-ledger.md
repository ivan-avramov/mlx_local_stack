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
  (return condition below); `presence_penalty 0.0`; **measure at the EXPECTED DEPLOYMENT
  only — no bf16-KV arms** (operator ruling 2026-08-17): the candidate KV convention is
  **turboquant kv4, `quantized_kv_start 0`** (what both winners ship). Rationale: bf16 KV
  is never the realistic deployment, and its prealloc floor cost 16 GB per retained session
  on `Qwen3.8-27B-mlx-uniform-4bit` (measured 51 GB footprint — lab notebook 2026-08-17).
- **TUNABLE axes**: temperature (per-model ladder), KV bits *within* quantized widths
  (kv3/kv4/kv6 as OFAT arms, never bf16), cache cap.
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
peak / 37.58 GB — the long-cited "43.3 GB" for the pick was REFUTED 2026-08-17: no artifact
carries it, the on-disk ladder says 37.58, and 43.38 belongs to the different model
`Qwen3.6-27B-OptiQ-4bit`; NOTE no capacity artifact in the corpus has a manifest) and retrieval ladders pass, but no coding or
reasoning quality has ever been measured at depth, and the shipped config caps the designed
maximum prompt near **~159,744 tokens** — **acceptable per the operator's 2026-08-18
clarification (256K is a target, not a bar; "I'd take a Fable-class performer with 160K")**.
The live gap is that **no coding/reasoning quality has been measured at depth for ANY model**;
the context requirement is satisfied by assumption in that sense only.

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
certify. Extension to full-bench arms was DECLINED (architect decision, delegated by the
operator 2026-08-17): ~6–8 h of worker time to certify a serving-only 1.27× lever fails the
quality-over-speed priority, and fresh suffix-ON arms would also churn the serving path the
campaign just uniformised. Revisit only if daily-driver latency becomes an operator pain point. Full table in `docs/open-questions.md` O25. Measurement stays suffix-OFF
forever regardless.

## 2. The ledger — every model ever considered

Scores: see the scoresheet in `docs/campaign-results.md` (sole owner). Statuses: pick /
runner-up / candidate / queued / testing / pruned@stage-N (partial, resumable) / excluded /
demoted.

| model | status | dated reasoning |
|---|---|---|
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` | **B pick** | 2026-08-16: aider n=110 repair result (above). he+/mbpp+ n=100, ifeval n=148, math500 n=30, lcb n=15. **2026-08-18 (decode-rate datum, from the `Qwen3.8-27B` family correction):** <!-- allow-shorthand --> this model decodes at **23.3 tok/s median** on its guard-clean humanevalplus rows (suffix-OFF) — i.e. the daily driver has served at ~23 tok/s since the 2026-08-16 suffix withdrawal. Architecture is `qwen3_5_text` 48/64 hybrid, identical to the `Qwen3.8-27B` family; <!-- allow-shorthand --> the overhead-bound decode mechanism (kernel-internal, powermetrics-probed on a sibling) applies HERE, and the checkpoint ships the same native 1-layer MTP sidecar (`mtp.safetensors`, int4-prequantized, 29 tensors) — so the M6 native-MTP probe is a lever for the CURRENT winner, not just candidates. |
| `Ornith-1.0-35B-mlx-uniform-4bit` | **B runner-up** | 2026-08-16: loses aider final 50.0 vs 73.6; faster per turn. he+/mbpp+ n=100, ifeval n=541, math500 n=30, lcb n=15. |
| `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` | **candidate** | 2026-08-16: ties every measured capability axis at 26.0 GB peak and ~2× speed; he+ 89/mbpp+ 81/ifeval 90.5 all n≥100 (suffix-OFF serving path, so its rows are guard-clean). Held back by: no reasoning row, no BFCL, aider edit-protocol contrast (3.75 malformed/case) which is serving-path-unmatched and untested under opencode (Run B queued). ifeval comparisons vs winners are ABSOLUTE-ONLY (ruling 4a — cap/sha mismatch, no three-way re-run). |
| `Qwen3.8-27B-mlx-uniform-4bit` | **testing — Stage-1 PASS** | 2026-08-17 evening: Stage 0 pass (load, MTP sidecar inert, worker flags verified). Checkpoint temp 1.0 AND recipe-grid 0.7 both ran away >3600s on HumanEval/146; the CAPPED FINE SCAN (now in AGENTS.md ladder recipe) found **t0.6** in ~25 min. n=15 rung at t0.6: **conv 15/15, pass@1 = 1.00, median 528 reasoning tokens** (n=15 MDE ±32pp — "no dramatic problem", not a ranking). Standing concern: **decode ~24 tok/s at every temp (0.2–1.0), 3–4× slower than both winners** — ⚠️ **the "both winners" half is CORRECTED 2026-08-18 (operator challenge)**: the checkpoint configs are STRUCTURALLY IDENTICAL to `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (`qwen3_5_text`, 64 layers, 48 linear-attention + 16 full-attention, same head geometry, both with the 1-layer MTP head + `mtp.safetensors` sidecar), and on matched guard-clean rows (same box, humanevalplus, fork `0c1c8b1`, suffix-OFF, rows >200 completion tokens) the median decode is `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` **23.3 tok/s** vs `Qwen3.8-27B-mlx-uniform-4bit` **26.0** vs `Ornith-1.0-35B-mlx-uniform-4bit` **76.2**. So the family is ~3× slower than `Ornith-1.0-35B-mlx-uniform-4bit` ONLY, and matches the incumbent qwen3_5-architecture winner exactly — the ~24 tok/s is the ARCHITECTURE's cost on this runtime, across both generations and both quant styles (the OptiQ recipe <!-- allow-shorthand --> runs `linear_attn.in_proj_a`/`out_proj` at 8-bit vs uniform 4-bit and lands within 3 tok/s — an independent cross-generation confirmation of "not quant-specific"). The stale impression came from the suffix-ON era: the winner's speed reputation predates the 2026-08-16 suffix withdrawal and nobody re-read its rate after (cross-era comparison — the apples-to-apples class). Mechanism investigation below stands unchanged; it describes the architecture we already ship. Original mechanism note: mechanism narrowed 2026-08-18 (code read, not yet profiled): decode DOES take the fused Metal path (`gated_delta.py` `use_kernel=True`, grid ≈196K threads, fp32 state traffic ~0.3 ms/token — neither occupancy nor bandwidth explains it), and ~15 GB of weights puts the bandwidth-bound ceiling near 80 tok/s, so the 3.3× gap is **overhead-bound decode**: 64 hybrid layers × many small dispatches per token (conv1d update + projections + compiled gating + custom kernel + norms on each of 48 linear-attention layers). Fits the rate being temp-independent and identical across all three quant recipes (fixed per-token cost). Discriminating probe (supervised, ~30 min): `powermetrics` GPU-idle% during decode — high idle = dispatch/CPU-bound (confirmed), busy = kernel-internal. **PROBE RUN 2026-08-18 (operator-supervised sudo, 30×1s samples during a live `Qwen3.8-27B-static-mixed-4bit` t0.4-rung decode, ~23 tok/s): GPU active residency 94.8–95.8% (idle 4–5%), so the pre-registered read is KERNEL-INTERNAL — the per-token cost is spent ON the GPU, not in CPU dispatch starvation.** Supporting signature: GPU clock ~1.12 GHz mean with the 1.62 GHz top bin never touched, GPU power ~21 W, CPU ~3.3 W with P0 at ~60% of low clock and P1 idle — the GPU is continuously occupied but neither frequency-boosted nor power-saturated, i.e. serialized small kernels / latency-bound work inside the 64-hybrid-layer per-token chain, not throughput-saturated compute or bandwidth. The M6 MTP probe remains the lever — it amortizes the per-token fixed cost regardless of which side owns it (`mtp_num_hidden_layers: 1` is in the checkpoint config) — but MTP is a SERVING-ONLY lever under the same ±5pp OFAT gate as suffix, never for measurement. Resolve before any Stage-3 spend. Earlier notes (self-converted 4.0 bpw group 64, hub-uploaded `caslca/…`, hybrid attention 16/64 full-attn layers) stand. **Capacity+retrieval ladder DONE overnight 2026-08-18: gate PASS (33.9 GB peak @256K) and — the quality signal — retrieval 1.0 at EVERY rung (160/192/224/256K), measured not assumed.** (Operator correction same day: footprint is a GATE, never a ranking advantage — the low peak and flat ladder, ~10 KiB/token via the 16/64 full-attention layers, buy only co-residency comfort on the shared box.) The cost is SPEED at depth: decode 14.7→11.1 tok/s across the rungs and **prefill ~196 tok/s (802 s @160K, 1,968 s ≈ 33 min @256K)** — a full-context agentic turn pays half an hour of prefill, so the overhead-bound serving concern now covers prefill too. |
| `Qwen3.8-27B-OptiQ-4.5bpw-mixed` | **testing — Stage-1 PASS** | 2026-08-17 evening: screened directly at the family t0.6: **conv 14/14 + HumanEval/146 capped-probe converged, pass@1 = 1.00 (n=14, MDE ±33pp)**. Tightest token distribution of the family (median ~430, max 6,673). Same 24 tok/s decode concern as `Qwen3.8-27B-mlx-uniform-4bit`. **Capacity ladder DONE 2026-08-18: 33.7 GB peak @256K (gate PASS), retrieval 1.0 at every rung; decode 13.3→10.5 tok/s at depth, prefill ~1,976 s @256K** — same flat ladder, same speed concern. 4.501 bpw mixed-sensitivity recipe + `optiq_vision.safetensors` + `sensitivity.json`. |
| `Qwen3.8-27B-static-mixed-4bit` | **PARKED — Stage-1 FAIL (convergence), 2026-08-18** | **t0.4 rung n=15 COMPLETE 2026-08-18: conv 13/15 with TWO >3600s timeout-DNFs (HumanEval/94, HumanEval/71) — and the one item the capped scan certified (HumanEval/67) converged fine, while HumanEval/146 "converged" at 66,171 tokens / 48 min and produced a WRONG answer (base+plus fail).** Scores: acc 92.3% over 13 generated (12/13), `acc_strict@81920` **0.80** (12/15, DNFs as failures per O31), median converged completion 913 tok, MDE ±35pp. The read: lowering temp 0.6→0.4 did not fix the meander, it MOVED it — the runaway item set is temp-dependent roulette (t0.6: 146+67; t0.4: 94+71), so the single-draw capped scan certifies only the item it probed. Convergence is not established at any scanned temp, and the same weights are available with a CLEAN Stage-1 in `Qwen3.8-27B-mlx-uniform-4bit` (conv 15/15, pass@1 1.00 at t0.6). **Decision: PARK — no further temp-hunting unless the passing recipes fall at Stage 2** (fail-fast funnel; partial + resumable, rows committed). Prior context: | 2026-08-17 evening: two consecutive hour-scale meanders at t0.6 (HumanEval/146 full 3600s DNF; HumanEval/67 >40 min — the same items `Qwen3.8-27B-mlx-uniform-4bit` does in 90s/37s at the same temp). **Quant moves the meander boundary** — quant sensitivity is a CONVERGENCE effect here, not just recall (cf. the gemma-4-26B-A4B-it-OptiQ-4bit recall lesson). Capped scan on HumanEval/67: 0.4 converged (892 tok), 0.5/0.3 cap-hit, 0.2 converged → candidate **t0.4**; n=15 rung queued. Quant recipe `mixed_3_6`, 3.966 bpw. **Capacity ladder DONE 2026-08-18: 31.6 GB peak @256K — the lightest of the family (gate PASS), retrieval 1.0 at every rung; decode 14.3→11.0 tok/s at depth, prefill ~1,979 s @256K.** Memory is NOT what fails this recipe; convergence is. |
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

- **`--samples k` is k BYTE-COPIES on the current (suffix-OFF) serving path** (O30 — raised as O28, renumbered in the 2026-08-18 merge; measured
  2026-08-17): the declared per-draw seed is recorded in every row and never in force — draws
  key off the batch generator's first-request seed at row 0. No k=1 corpus row is harmed and
  the suffix-OFAT pairing is unaffected, but no multi-sample reliability figure is valid until
  the fork fix lands. RULED 2026-08-17: `--samples > 1` is now REFUSED by `run.py` (O30);
  the fork seed fix is queued for the next fork-opening.

- **Guard-clean baseline inventory (PUBLISHED — parity enforced in code since `9675957`,
  2026-08-17):** fingerprint v4 + `compare` tier parity are live, with a pytest that reds the
  suite if a fingerprint key ever lacks a documented tier again. Under full parity, the leader
  baselines a new candidate can be DIRECTLY compared against are the winners'
  humanevalplus/mbppplus n=100 suffix-OFF rows (cap 131072, `src/mlx-vlm 0c1c8b1`). The ifeval
  corpus spans three fork shas and two caps — absolute readings only (ruling 3). Two rules
  soften what "clean" demands: per-model TUNE axes (temperature, top_p/top_k/min_p, penalties,
  kv_bits/scheme) WARN rather than refuse — a (model, tune) pair legitimately differs there —
  and a cap difference refuses only when it could have BOUND (ruling 7's binding rule, checked
  against actual row prompts; the winners-vs-`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`
  humanevalplus caps 131072 vs 262144 verified non-binding, so that pairing is now admissible
  once its remaining draft-state warning is accepted as pre-v3 UNOBSERVED).
- **The single box (M5 Max 64 GB) is the operator's daily machine** (ruling 8): capacity runs
  are scheduled for quiet moments, every peak-memory row records the concurrent-process
  baseline, and memory anomalies are suspected of co-residency stomping BEFORE being
  attributed to a model. Pre-2026-08-17 speed/memory rows are cross-config vs post-move rows.
- **O23 stays closed** (ruling 4b): no math500/lcb suffix-OFF re-runs — those winner rows are
  suffix-ON serving-path composites and are read as within-winner evidence only.
- **Run A power note:** at n=22 the paired MDE is ±27pp against an aider `final` gap of
  23.6pp — Run A is DIRECTIONAL, with a pre-registered extension rule (extend to ~157 items
  iff the point delta exceeds +5pp for either model but the CI straddles zero).
