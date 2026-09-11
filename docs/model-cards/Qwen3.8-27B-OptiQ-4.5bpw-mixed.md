---
license: apache-2.0
base_model: unsloth/Qwen3.8-27B  # allow-shorthand
library_name: mlx
tags:
- mlx
- unsloth
- qwen3_5
pipeline_tag: image-text-to-text
---
# Qwen3.8-27B-OptiQ-4.5bpw-mixed

**27B (VLM parameters — vision tower retained)** — note: Hugging Face's size badge undercounts packed low-bit MLX
weights (it counts the packed uint32 tensors), so the number shown beside this repo is wrong;
the figure here is the true parameter count.

MLX **OptiQ sensitivity-mixed** quant (data-driven KL-sensitivity 4/8-bit) of <!-- allow-shorthand -->
[unsloth/Qwen3.8-27B](https://huggingface.co/unsloth/Qwen3.8-27B). Sibling: the uniform 4-bit <!-- allow-shorthand -->
[caslca/Qwen3.8-27B-mlx-uniform-4bit](https://huggingface.co/caslca/Qwen3.8-27B-mlx-uniform-4bit).

| measured | value |
|---|---|
| effective bits/weight | **4.98** (152 of 498 quantized layers at 8-bit, 346 at 4-bit) |
| weights footprint | 18.44 GB (this build's own serving manifest) |
| quantized-layer bit histogram | 8-bit: 152, 4-bit: 346 |

**The "4.5bpw" in this repo's name is a misnomer.** The conversion tool's own intermediate <!-- allow-shorthand -->
print for this recipe's `optiq_mixed` phase showed 5.485 bpw / 17.6 GB before final packaging;
the shipped artifact's serving manifest records **effective_bits 4.98** (152 layers at 8-bit,
346 at 4-bit) as the number that actually describes what is loaded. Cite the manifest's
`effective_bits`, never the repo name.

## Capacity gate + retrieval ladder (256K context)

Gate metric is `mx.get_peak_memory` (the prefill spike) against a 46 GB hard gate; retrieval is
a needle-style accuracy check at each rung.

| context | peak (server) | retrieval acc | prefill | decode |
|---|---|---|---|---|
| 160K | 32.75 GB | 1.00 | 856 s (184 tok/s) | 13.33 tok/s |
| 192K | 33.07 GB | 1.00 | 1,179 s (160 tok/s) | 12.27 tok/s |
| 224K | 33.39 GB | 1.00 | 1,554 s (142 tok/s) | 11.25 tok/s |
| 256K | 33.72 GB | 1.00 | 1,977 s ≈ 33 min (128 tok/s) | 10.53 tok/s |

**Capacity gate: PASS** (33.72 GB peak at 256K). **Retrieval effective context: 256K** —
essentially the same flat ladder as the uniform-4bit sibling; footprint is a pass/fail gate <!-- allow-shorthand -->
here, not a ranking edge between the two recipes.

## Stage-1 screening and Stage-2 convergence-gated pass@1

**Stage-1** (2026-08-17): screened directly at the family's t0.6; convergence 14/14 plus one
capped-probe convergence (`HumanEval/146`), pass@1 **1.00** (n=14, nominal MDE ±33pp). Tightest
token distribution of the family (median ~430, max 6,673).

**Stage-2**, HumanEvalPlus / MBPPPlus at t0.6, thinking ON, budget 81,920, predictor OFF:

| bench | attempted | graded | acc (of graded) | acc_strict@81920 (of attempted) | convergence | nominal MDE |
|---|---|---|---|---|---|---|
| HumanEvalPlus | 50 | 48 | 87.5% (42/48) | 84.0% (42/50) | 2 items (`HumanEval/146`, `HumanEval/39`) timed out and were not graded — the pre-C28 client-timeout artifact described below; 0 in-budget meander loops among the 48 graded, of which 2 (`HumanEval/2`, `/47`) showed a degenerate-EOS pattern | ±18.1pp |
| MBPPPlus | 50 | 50 | 80.0% (40/50) | 80.0% (40/50) | 0 timeout loops; 1 item showed a degenerate-EOS pattern | ±17.7pp |

Both rows were measured 2026-08-17 (HumanEvalPlus) and 2026-08-19 (MBPPPlus), before a
since-fixed harness defect: an abandoned generation's successor could be starved into a false
non-convergence, fixed 2026-08-26. The project's results log flags this recipe's paired t0.6
HumanEvalPlus/MBPPPlus rows from that window as carrying cascade-inflated upper bounds on the
error/DNF counts. This card previously stated that this recipe produced "0/50 non-converging
items where the uniform 4-bit sibling produced 7/51" as evidence that precision drives the <!-- allow-shorthand -->
runaway class in this family; **that claim is retracted** after a dedicated causal test on the
sibling `Qwen3.8-27B-Fable-Distill` lineage (2026-09-02) found precision is NOT the runaway <!-- allow-shorthand -->
driver for this family — three precisions of that base (uniform 4-bit, an equivalent 4.98 bpw
sensitivity-mixed recipe, and a uniform int8 control) all converged on all 50 items. No post-fix
shallow HumanEvalPlus/MBPPPlus re-run of this exact recipe exists; the acc/acc_strict numbers
above are the only ones on file and should not be read as evidence this recipe suppresses
runaways relative to its sibling.

## Agentic (opencode, 22-item Python/Go, t0.6/xhigh, predictor OFF)

2026-08-29 (M25, CLOSED): Python 18/22, Go 16/22. Paired against
`Qwen3.8-27B-mlx-uniform-4bit` at the same tune (20/22 Python, 16/22 Go): discordant 0:2
(Python) / 1:1 (Go), pooled p=.625 — a statistical tie. Equivalent stall profile (8 vs 8
gate-kills) and wall-clock (3.6 h vs 4.2 h). **Pre-registered verdict: WASH** — recipe choice is
not the differentiator for this family on the agentic axis; no further quant variants were
queued for it (a ~6bpw rung, the official `mlx-community/Qwen3.8-27B-OptiQ-4bit`, and a DWQ
variant all stay dormant per that ruling).

## Recommended sampling (screened at t0.6; never re-certified at medium reasoning effort)

| param | value |
|---|---|
| temperature | **0.6** |
| top_p / top_k / min_p | 0.95 / 20 / 0.0 |
| presence_penalty | 0.0 |
| reasoning_effort | not set — runs the family's chat-template default (xhigh); this recipe was never run through the medium-effort screen its sibling passed |
| max_tokens / thinking_budget | 102400 / 81920 (thinking ON) |

## Predictor (MTP sidecar)

**Not measured / not certified.** The registry entry for this recipe carries no `draft_kind`
(serving-only, draft OFF). This recipe never went through an M6d-style speculative-decoding
OFAT; the checkpoint's `optiq/mtp.safetensors` sidecar has not been split or probed here, unlike <!-- allow-shorthand -->
the uniform 4-bit sibling's certified drafter. <!-- allow-shorthand -->

## Serving caveat: decode speed is architecture, not quant

This recipe's own capacity-ladder decode falls 13.3 → 10.5 tok/s from 160K to 256K context —
the same ~24 tok/s-class shallow-decode range reported for the uniform 4-bit sibling and for <!-- allow-shorthand -->
the rest of this family. The family-wide mechanism (serialized per-token kernel overhead across
64 hybrid attention/linear-attention layers, confirmed GPU-bound rather than dispatch-starved
via a `powermetrics` probe run on a sibling recipe of this family) is expected to apply here by
architecture, but whether this recipe's 8-bit linear-attention projections shift the rate at all
has **not been separately measured on this recipe**. At 256K, prefill is **~33 minutes (1,977 s)
to first token**.

## Status

Registry role: **candidate** (bench-only; not shipped to daily-client configs). **Not a current
B or C pick** — the 2026-08-29 agentic comparison against the uniform-4bit sibling closed as a <!-- allow-shorthand -->
WASH, so this recipe stays a screened, published alternative rather than a promoted pick.
Methodology and full results:
[https://github.com/ivan-avramov/mlx_local_stack](https://github.com/ivan-avramov/mlx_local_stack).

<!-- ============================================================================
NOT PART OF THE CARD — SOURCES (strip before publishing to Hugging Face)
============================================================================

Footprint / bpw / quant table front matter, superseded "0/50 vs 7/51" claim being retracted:
current live HF README for caslca/Qwen3.8-27B-OptiQ-4.5bpw-mixed (fetched 2026-09-11 via
huggingface_hub, cached at
models--caslca--Qwen3.8-27B-OptiQ-4.5bpw-mixed/snapshots/368011bc8d24.../README.md). Tags
(mlx, unsloth) same README front matter; qwen3_5 tag from this repo's config.json `model_type`
field, fetched via huggingface_hub this session.

27B (VLM parameters — vision tower retained): main_models.yaml:390 (`type: vision` on this
registry entry) and :426 (`capabilities: [tools, vision, thinking]`); docs/model-ledger.md:207
(lists `optiq_vision.safetensors` as part of this build).

18.44 GB footprint / effective_bits 4.98 (152 layers 8-bit, 346 at 4-bit): this build's own
serving manifest,
benchmark/results/Qwen3.8-27B-OptiQ-4.5bpw-mixed/humanevalplus.t0.6.manifest.json (`quant`
block: `effective_bits: 4.983526659518471`, `footprint_gb: 18.44`, `bit_histogram: {8:152,
4:346}`), cross-checked against docs/PLAN.md:99 ("OptiQ-mixed 18 GB / 4.98 eff. bpw, identical
152-layer 8-bit set to the plain Qwen3.8-27B-OptiQ-4.5bpw-mixed build"). "4.5bpw is a misnomer" <!-- allow-shorthand -->
/ 5.485 bpw / 17.6 GB intermediate print: docs/lab-notebook.md:3706-3709 ("the `optiq_mixed`
phase of the `Qwen3.8-27B-OptiQ-4.5bpw-mixed` build printed 5.485 bpw / 17.6 GB, and its
manifest records `effective_bits` 4.98 ... the '4.5bpw' in that registry name is a misnomer <!-- allow-shorthand -->
... Cite the manifest's `effective_bits`, never the name.").

Capacity gate + retrieval ladder table: benchmark/results/Qwen3.8-27B-OptiQ-4.5bpw-mixed/capacity_retrieval.json
(records array, ctx 160000/192000/224000/256000, server_peak_gb/retrieval_acc/prefill_s/
prefill_tps/decode_tps fields verbatim); gate_gb 46.0, capacity_gate_pass true,
retrieval_effective_ctx 256000 (same file).

Stage-1 screening (n=14, t0.6, conv 14/14 + capped probe, pass@1 1.00, median ~430 tok, max
6,673, MDE ±33pp): docs/model-ledger.md:207.

Stage-2 HumanEvalPlus (attempted 50, graded 48, acc 87.5%=42/48, acc_strict 84.0%=42/50,
conv_rate 100%, n_degenerate_eosed 2, errors 2, mde 18.08pp): score fields from
benchmark/results/Qwen3.8-27B-OptiQ-4.5bpw-mixed/humanevalplus.t0.6.score.json. The 2 ungraded
items and their error reason: benchmark/results/Qwen3.8-27B-OptiQ-4.5bpw-mixed/humanevalplus.t0.6.jsonl
lines 15 and 26 (`{"id": "HumanEval/146", ..., "error": "timed out"}`,
`{"id": "HumanEval/39", ..., "error": "timed out"}`). The 2 degenerate-EOS items
(`HumanEval/2`, `/47`) among the 48 graded: humanevalplus.t0.6.score.json
`degenerate_eosed_ids`. Manifest timestamp 1787032556 = 2026-08-17 local (America/Los_Angeles,
UTC-7/-8; UTC read is 2026-08-18 05:55, matching docs/model-ledger.md:207's and PLAN.md:58's
"2026-08-17 evening" Stage-1/Stage-2 dating) from
benchmark/results/Qwen3.8-27B-OptiQ-4.5bpw-mixed/humanevalplus.t0.6.manifest.json.
Stage-2 MBPPPlus (attempted/graded 50, acc/acc_strict 80.0%=40/50, n_degenerate_eosed 1, errors
0, mde 17.72pp): benchmark/results/Qwen3.8-27B-OptiQ-4.5bpw-mixed/mbppplus.t0.6.score.json;
manifest timestamp 1787173306 = 2026-08-19 local, from
benchmark/results/Qwen3.8-27B-OptiQ-4.5bpw-mixed/mbppplus.t0.6.manifest.json.

Pre-C28 cascade caveat on these two rows: docs/campaign-results.md:944-952 ("C46 leg 2 CLOSED
WITHOUT RUNNING" entry, 2026-09-03 — "the two entries that cited the four Qwen3.8-27B-mlx-uniform-4bit
/ Qwen3.8-27B-OptiQ-4.5bpw-mixed hep+mbpp t0.6 rows ... are superseded by M12/M26 and by M21's
closure ... their DNF counts ... are cascade-inflated UPPER BOUNDS"). Original "0/50 vs 7/51"
claim and its "precision drives runaways" framing: docs/campaign-results.md:394-398 (D13 entry,
2026-08-20/22).

Retraction / negative causal result — CORRECTED this round: M21's three tested arms were the
`Qwen3.8-27B-Fable-Distill` lineage, NOT this checkpoint: docs/campaign-results.md:618-628 (M21 <!-- allow-shorthand -->
CLOSED header + arm table: `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` @t0.6-r2 reference,
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` 4.98 eff. bpw 152-layer-8-bit recipe, and
`Qwen3.8-27B-Fable-Distill-mlx-uniform-8bit` diagnostic control — all 50/50 converged, 0 DNF,
strict 88.0/88.0/86.0) and docs/PLAN.md:99 (M21 row, "CLOSED 2026-09-02: NEGATIVE for the
precision hypothesis ... Both conversions ran (int8 28 GB / 8.63 bpw; OptiQ-mixed 18 GB / 4.98
eff. bpw, identical 152-layer 8-bit set to the plain `Qwen3.8-27B-OptiQ-4.5bpw-mixed` build)
... The motivating 10% DNF was a pre-C28 client-timeout cascade"). Note the "identical
152-layer 8-bit set" language is PLAN.md's own basis for calling the M21 OptiQ-mixed arm
"equivalent" to this checkpoint's recipe — the two are different builds on different base
checkpoints (`TeichAI/Qwen3.8-27B-Fable-Distill` vs `unsloth/Qwen3.8-27B`) that share the same <!-- allow-shorthand -->
sensitivity-layer selection, not the same weights. C28 defect discovery/fix date (2026-08-26):
docs/PLAN.md:105 (M23 row).

Agentic M25 python/go counts, discordant splits, WASH verdict: docs/campaign-results.md:1211-1223.

Recommended sampling table (no reasoning_effort field, temperature 0.6 comment on the M25 prep
rationale): main_models.yaml:389-416.

Predictor absence: main_models.yaml:389-426 (no draft_kind field in this entry, contrast with
the sibling's main_models.yaml:337-338); cross-checked docs/PLAN.md:102 (M6c closure lists only
"C51/M36 (the two Qwen3.8-27B picks)" as predictor-settled, i.e. the sibling + Fable-Distill-OptiQ-mixed, <!-- allow-shorthand -->
not this recipe).

Serving caveat (13.3->10.5 tok/s, ~24 tok/s family concern, 33 min prefill @256K):
docs/model-ledger.md:207 ("Same 24 tok/s decode concern as Qwen3.8-27B-mlx-uniform-4bit ...
decode 13.3->10.5 tok/s at depth, prefill ~1,976 s @256K"); this recipe's own capacity ladder
cross-checked against benchmark/results/Qwen3.8-27B-OptiQ-4.5bpw-mixed/capacity_retrieval.json
(same source as the capacity table above). Mechanism (powermetrics probe, GPU 95% active) was
run on `Qwen3.8-27B-static-mixed-4bit`, a sibling recipe of this family, per
docs/model-ledger.md:206 — NOT measured on this recipe, hence "not been separately measured on
this recipe" in the card body (F7). The 8-bit-linear-attention-projections-within-~3-tok/s
comparison previously on this card described `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, a different
checkpoint (also docs/model-ledger.md:206's parenthetical), and has been removed.

Status / not in README B or C tables: README.md (full B and C tables, lines 9-12 and 41-44) —
searched, no row for `Qwen3.8-27B-OptiQ-4.5bpw-mixed` in either table as of 2026-09-11.
============================================================================ -->
