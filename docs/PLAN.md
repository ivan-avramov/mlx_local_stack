# THE PLAN — current and authoritative

**Last updated: 2026-08-17.** This file is the plan: the ordered work queue and the standing
constraints. It is deliberately SHORT; when something completes, its row changes and the
narrative goes elsewhere. **The picks, the model field, and the per-model reasoning now live
in `docs/model-ledger.md`** (created 2026-08-17, operator ruling) — this file no longer
carries them.

| file | role | rule |
|---|---|---|
| **`docs/PLAN.md`** (this) | the plan: ordered queue + constraints | keep CURRENT; never let it grow into a narrative |
| **`docs/model-ledger.md`** | CANONICAL: objective, picks, every model + status + dated reasoning | updated daily; nothing deleted |
| `docs/open-questions.md` | the operator's decision queue | nothing is ever deleted |
| `docs/campaign-results.md` | recommendations narrative + the GENERATED scoresheet (sole owner) | scoresheet is generated, never hand-edited |
| `docs/lab-notebook.md` | **THE** history: every retraction, defect, mechanism, and measured result | append-only. `docs/campaign-queue.md` was folded into it and deleted on 2026-08-16 (old driver box, merged 2026-08-18) — ONE history file |
| `docs/work-queue.json` | the EXECUTABLE form of the queue, runnable by the `bench.workqueue` daemon | regenerate when the queue changes (last regenerated 2026-08-17) |
| `docs/handoff.md` | **the ONE handoff** — last session's narrative only | rewritten in place each session; there is never a second one |

## Context (single-box era, 2026-08-17)

The M5 Max 64 GB is the ONLY machine — driver AND worker — and it is the operator's daily
machine, not a dedicated benchmarker. All out-of-repo artifacts live in the dedicated workdir
(`$STACK_WORKDIR`, see `config.sh`). The 2026-08-17 operator rulings (recorded in
`docs/open-questions.md` and the approved session plan) govern everything below.

## The ordered work queue

Phase 2 (harness verification, no model time) runs first; model queue follows. Costs
re-derived from persisted per-item wall-clock after the 2026-08-17 adversarial review found
the previous estimates off by 2–18×.

| # | work | what it buys | cost | state |
|---|---|---|---|---|
| V1 | ~~Adversarial verification~~ | **DONE 2026-08-17**: 43.3 GB REFUTED (37.58 on disk); retraction upheld but mislabelled (non-convergence, not degeneracy; the significant cell favours suffix-ON); divergence/speed confirmed exactly; ON-arm suffix state physics-corroborated but documentarily unverifiable; guard gap = 18 unguarded keys — full report in `docs/lab-notebook.md` | — | done |
| V2 | ~~Grade the suffix OFAT~~ | **DONE 2026-08-17**: `p_d` 0.04–0.06; gate NOT met at n=100 (3/4 CIs past ±5pp); suffix stays OFF — see O25 | — | done |
| V3 | ~~Guard-parity~~ | **DONE 2026-08-17** (`9675957`): fingerprint v4 (`hf_path`/`kv_quant_scheme`/`quantized_kv_start`/`prefill_step_size` join the resume guard; `kv_prealloc_tokens` recorded, hardware-refused only; registry sha256+dirty recorded per ruling 5; `_box()` reads config.sh so the box label finally lands); `compare` classifies every fingerprint key into REFUSE / tune-WARN / hardware-only tiers, cap gets ruling 7's binding rule (checked against actual row prompts), parity pytest reds the suite on any future unclassified key; `peak_mem_gb` refusal landed earlier same day. Corpus verified non-stale; guard-clean inventory published in the ledger §3 | — | done |
| V4 | ~~opencode provenance~~ | **DONE 2026-08-17**: version pinned (1.18.15, refuses drift), recorded per row + in a real manifest (deployed profile, polyglot sha, `edit_format: tools`); `_polyglot_root` now honors `$POLYGLOT_DIR` (both old hardcoded paths were dead after the workdir move) | — | done; M3/M4 unblocked |
| M1 | ~~Re-draw test~~ | **DONE-EARLY 2026-08-17, killed at 11/39 draws with a sharper verdict than designed**: sample-0 sweep complete — 5/10 canonically-degenerate items re-degenerate deterministically (~82K tok each), 5 converge clean; the remaining draws were byte-copies because **the per-draw seed is INERT on the non-speculative path** (O30 — `row_ids=[0]*B`, one sampler per BatchGenerator keyed by the FIRST request). Full entry in the lab notebook; `--samples` designs void until O30 is ruled | — | done; O28 opened |
| M2 | **`Qwen3.8-27B` recipes through funnel Stages 0–1** <!-- allow-shorthand --> (load smoke incl. MTP-sidecar inertness, capacity ladder, convergence screen) | turns three stranded checkpoints into candidates; harness acceptance test begins | ~1–2 h | **2026-08-17 evening: Stages 0–1 DONE for 2 of 3** — `Qwen3.8-27B-mlx-uniform-4bit` PASS (t0.6, conv 15/15, pass@1 1.00), `Qwen3.8-27B-OptiQ-4.5bpw-mixed` PASS (t0.6, conv 14/14 + 146 probe, pass@1 1.00), `Qwen3.8-27B-static-mixed-4bit` FAIL at t0.6 → capped scan gives candidate t0.4, n=15 rung pending. Capacity ladders DONE overnight 2026-08-18: all three gate PASS; retrieval 1.0 at every rung (the quality signal). Footprint is a gate, not an advantage (operator, 2026-08-18). Decode 11–15 tok/s and prefill ~33 min at 256K — speed/usability is the family's gating question for Stage 3. See model-ledger rows + the CAPPED FINE SCAN recipe in AGENTS.md. Next: Stage-2 paired screens (n≈30–50) for the two passers; the 24 tok/s decode mechanism (or M6) gates Stage 3 |
| M3 | **opencode Run A** — 22 python × both winners, DIRECTIONAL, pre-registered extension rule | whether the B pick survives without aider | ~1.7 h | blocked on V4 |
| M4 | **opencode Run B** — `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` | third model on the agentic axis | ~0.7 h | blocked on M3 (registry cap restored 2026-08-17) |
| M5 | **DNF re-runs at shipped cap 262144** (ruling 7). **INVENTORY DONE 2026-08-17 — 45 rows**, dominated by the ifeval SILENT-CLAMP class the raw `nonconv_kind` cannot see (`Ornith-1.0-35B-mlx-uniform-4bit` ifeval 28 + `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` ifeval 10, both at cap 65536; plus 6 coding budget-hits: `Ornith-1.0-35B-mlx-uniform-4bit` humanevalplus 3 @131072, `gemma-4-26B-A4B-it-OptiQ-4bit` humanevalplus 1 @65536, `gemma-4-31B-it-qat-6bit` humanevalplus 2 @49152). Over the n=40 pilot threshold and rows are LONG (~15 min each) → **PILOT = the 6 coding rows + the 10 `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` ifeval rows (~4 h); extend to the 28 only if the pilot's flip-rate is decision-relevant.** Procedure per (model,bench): back up jsonl → delete the DNF rows → restore that model's registry cap to 262144 → resume WITHOUT `--clean-stale` (the 65536-manifest hazard) → restamp → re-grade → converged survivors marked promoted-to-shipped-cap. | closes the cap-provenance gap | pilot ~4 h, full ~11 h | **PILOT DONE 2026-08-18** (6h36m wall): 4/10 `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` ifeval rows recovered (converge at 1.9-3.6K tokens under the true 81,920 budget), 6 are persistent >3600s runaways (error-stubbed, retryable). **Extension to the 28 `Ornith-1.0-35B-mlx-uniform-4bit` rows DECLINED** (architect call: ~18 h to move an n=541 axis whose equivalence verdict cannot flip). The 6 coding budget-hit rows remain open, cheap, supervised-window work. O31 filed on the error-row denominator question |
| M6 | **`Qwen3.8-27B` family native-MTP probe** (operator-requested 2026-08-17): <!-- allow-shorthand --> the fork's `qwen3_5_mtp` drafter already discovers this checkpoint's sidecar (`mtp_file: optiq/mtp.safetensors`, 29 tensors, 1 layer, prequantized int4). Smoke `draft_kind: mtp` on one recipe (verify `--draft-kind mtp` at the worker cmdline), then a paired one-item ON/OFF speed probe for acceptance + tok/s. The "MTP is a net slowdown" pitfall was measured on bolt-on heads for other families — it does not pre-decide a NATIVE trained head. Serving-only lever: measurement stays MTP-OFF; a quality OFAT (O25-style ±5pp gate, measured-`p_d` sizing) only if the recipe survives the funnel AND the speedup is real | a real perf lever if acceptance is high | ~15 min smoke; hours only if promoted | queued behind M2 |
| D1 | ~~BFCL vendored handler~~ | **CODE DONE 2026-08-17** (`1c2d91f`, Sonnet worker, architect-reviewed): native-FC passthrough via `bench/bfcl_handler.py` + `bench/run_bfcl_fc.py` — raw `messages`+`tools` to `/v1/chat/completions`, server-side template, deployed sampling, 4096-cap structurally unreachable, 17 mocked tests. **Live smoke PASSED 2026-08-17**: first pass 2/5 exposed `underscore_to_dot=False` (model called `math_factorial` exactly as the wire schema named it; checker wanted the dotted original); fixed -> **5/5** on simple_python for `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`. Ready for the first recorded run. Open architect call: retire the legacy `bfcl_shim/` prompt-mode path (its 2 tests fail on import, pre-existing) | driver-side | done |
| D2 | ~~Judge-panel reliability spec~~ | **SPEC DONE 2026-08-17**: `docs/superpowers/specs/2026-08-17-judge-panel-reliability-design.md` — pre-registered reliability gate (anchor accuracy ≥0.85, position-flip ≤0.30, Krippendorff α ≥0.5, length-bias and identity checks) that must pass on ~30 anchor pairs before any candidate ranking is admissible; pairwise forced-choice, blind, mixed-family, both orders. Execution stays parked until the B queue drains (operator ruling) | — | spec done; execution parked |
| D3 | Tune-encoding migration | **SPEC DONE 2026-08-17** (`docs/superpowers/specs/2026-08-17-tune-encoding-migration-design.md`): `tune` label in manifest + `<bench>.<tune>.jsonl` filenames, dirs stay pure registry names, idempotent migration script for the six pseudo-model dirs, isolation invariant tested. **IMPLEMENTED + COMMITTED (`2e7dbd3`)**: 67 tests; real-tree dry-run 52 moves, 8 real collisions refused (`Ornith-1.0-35B-mlx-uniform-4bit-suffix` vs the kept `.suffixon` files) — `--apply` HELD until the collision lineage is resolved | driver-side | done; apply held |
| D4 | ~~Registry-hash-into-manifest~~ | **DONE 2026-08-17 inside V3** (`9675957`): `gather()` records registry sha256 + git-dirty state, record-only | — | done |
| D5 | Regenerate `docs/work-queue.json` from this table; extend `bench/workqueue.py` with PAUSE/STOP/SKIP; per-item `bench_watch` + status aggregator | utilization + operator pause/redirect | driver-side | queued |
| D6 | **Session-cache × prealloc audit** (from the 51 GB incident, 2026-08-17): the prealloc floor materializes full-cap KV arrays PER RETAINED SESSION (`MLX_VLM_CACHE_SESSION_MAX` default 8) — even the deployed winners at TQ4/131072 can hold 8 × 2 GB of floors on top of weights. Audit the daily-driver config; consider a fork fix flooring only the ACTIVE session; decide the right session cap for `runserver.sh` | daily-driver memory headroom | driver-side + fork | queued |

**Removed by ruling (2026-08-17):** ifeval three-way re-runs (4a — `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`
ifeval stays absolute-only); math500/lcb suffix-OFF re-runs (4b — O23 stays closed).

**Merged 2026-08-18 from the old driver box's queue (items its final session held that this box's
queue did not):**

| # | work | what it buys | cost | state |
|---|---|---|---|---|
| M7 | **presence_penalty mechanism check** — 5 reachable `Ornith-1.0-35B-mlx-uniform-4bit` ifeval runaways (cycle periods 2–11 tok, measured), via the merged `--presence-penalty` override; endpoints cycle-disappearance (`bench.cycles.describe`) → tokens/wall → `non_latin_rate` → pass@1 LAST | closes the "can the penalty break a verbatim cycle at all" question. NOTE: the old box's O28 close already rules the lever a deployment NO-GO on its merits — this is mechanism-only | ~40 min | queued, LOW priority |
| M8 | **`reasoning_effort` OFAT** (`xhigh` default / `medium` / `low`) on known `Qwen3.8-27B` runaway items <!-- allow-shorthand --> — the first NATIVE reasoning-depth control any candidate has offered (every lever we have is external truncation or sampling); also settle **`preserve_thinking`** (ON by default — retains reasoning across turns; interacts with the session cache) before designing the agentic axis | a candidate answer to the runaway tax; pass@1 is the HARD constraint per the ladder rule | ~1 h | queued behind M2 Stage 2 |
| M9 | **opencode Run C** — 88 items (4 non-python languages) × winners, five per-language rankings never one blended number; **blocked on multi-language grading inside the `aider-benchmark` container** (`run_opencode_probe.py` has only `_grade_python`) | the agentic axis beyond python | ~3.5 h/model + driver work | blocked on M3 + container grading |
| M10 | **Re-open the `gemma-4-31B-it-qat-6bit` / `gemma-4-26B-A4B-it-OptiQ-4bit` agentic verdicts** (undoes two protocol artifacts) | fairness to two demoted candidates | ~2 h UNPILOTED | queued, LOW priority |
| D7 | **Add `opencode` to `ROLES["coding"]`** in `benchmark/m1/scoreboard.py` (demote aider to a diagnostic column) + **progress-gated bound for opencode sessions** (replace the flat 900 s timeout; design in `docs/handoff.md`) | without these, Runs A/B/C publish under the wrong role and a wedged session burns an hour | driver-side | queued, gates M3 publication |
| D8 | **Acquire the unfetched `Qwen3.8-27B` comparison arms** <!-- allow-shorthand -->: `WaveCut/Qwen3.8-27B-MLX-4bit-DWQ` (16.07 GB) for a matched A/B vs `Qwen3.8-27B-mlx-uniform-4bit`, plus the shortlisted `mlx-community/Qwen3.8-27B-4bit` / `lmstudio-community/Qwen3.8-27B-MLX-6bit` | external recipes vs our conversions on the same base | 16 GB+ downloads | queued, after M2 resolves |

| M11 | **Reasoning-depth ladder for the winners** — `bench/run_reasoning.py` (vartrack, ≥0.85 threshold) has NEVER run on `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` or `Ornith-1.0-35B-mlx-uniform-4bit` (only three retired early candidates, grid ≤64K). Extend `REASONING_GRID` to 96/128/160K (cap-aware) and run both winners + `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` | closes the reasoning-depth half of the effective-context methodology, at the operator's target range | ~1–2 h/model | queued — operator-requested 2026-08-18 |
| D9 | **Build the coding-at-depth axis** (tooling MISS, identified 2026-08-18): embed real repair/coding tasks in ~100–160K-token repo context, execution-gated grading — the measurement that settles goal B's context requirement instead of assuming it. Architect spec first, then build | quality-at-depth for goal B — the decisive unmeasured axis | driver-side spec + build | queued — operator-requested 2026-08-18 |
| M12 | **Run coding-at-depth** on both winners + surviving candidates once D9 lands | the goal-B verdict at depth | sized by D9's spec | blocked on D9 |

(The old box's other queue items are all executed or superseded here: suffix OFAT+grading = V2/O25,
Qwen3.8 smokes/ladders = M2, cap-sensitive ifeval re-runs = M5's inventory+pilot, compare cap guard <!-- allow-shorthand -->
= V3, BFCL = D1, judge panel = D2, opencode pinning = V4. Its vendor-temp-1.0 warning is confirmed
by M2's ladder — 1.0 runs away — and its native-MTP note lives in M6.)

## The fail-fast funnel (how any new candidate is processed)

- **Stage 0 (minutes):** load smoke + capacity gate (`mx.get_peak_memory` ≤46 GB @ cap),
  scheduled for a quiet box; record the concurrent-process baseline with every peak row;
  suspect co-residency stomping before blaming the model.
- **Stage 1 (~1 h):** convergence screen at default tune, n=15. Temperature ladder only on
  non-convergence; it selects a tune only on a DRAMATIC knee — no knee ⇒ keep the default
  (n=15 cannot see a <32pp pass@1 regression).
- **Stage 2 (~1–2 h):** paired screen vs the leader on GUARD-CLEAN axes only (today:
  humanevalplus/mbppplus n=100 suffix-OFF, cap 131072). Endpoints are COUNT/RATE metrics
  (budget-hit rate, degeneracy counts, malformed-edit rate — they resolve at n≈30 where
  binary pass@1 needs n≈100); pass@1 prunes only at n≥50 for a ~20pp deficit. The
  between-models `p_d≈0.20` applies — never import the within-model low-`p_d` argument.
- **Stage 3 (hours):** full n=100 axes + agentic for survivors.
- **Verdicts:** prune (CI upper < −5pp) / park (partial, resumable) / continue. Holm per
  candidate-per-stage. **Promotion is a holistic architect judgement** recorded in the
  ledger (ruling 2). Leader baselines are k=1 — a shared error term, standing caveat.

## Standing constraints

- ONE resident model, always. Unload between models.
- Suffix decoding OFF for all measurement; verify at the WORKER CMDLINE, never the yaml.
- Match the cap before resuming any arm; converged rows are cap-invariant (ruling 7), DNF
  rows are not.
- Items buy power; samples buy reliability. Never a delta without its interval and MDE;
  "inconclusive" is a valid answer. No job at n≥40 without a 5-item pilot sized from the
  pilot's MEAN including runaways.
- Capability ranks; throughput is reported beside it.
- Full registry model names everywhere, including chat prose and commit bodies.
- Propose before fixing; commit when the work calls for it; never push without being asked.

## How to maintain this file

When a queue row completes: change or delete the row; narrative goes to
`docs/lab-notebook.md`; ledger updates go to `docs/model-ledger.md`. Regenerate
`docs/work-queue.json` whenever the queue changes. Do not add narrative here.
