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
| `docs/campaign-queue.md` | HISTORY: per-session state, superseded plans | append-only; `[RUNNING]` markers are historical |
| `docs/lab-notebook.md` | HISTORY: every retraction, defect, mechanism | append-only |
| `docs/work-queue.json` | the EXECUTABLE form of the queue | regenerate when the queue changes — **stale (2026-08-14)** |

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
| M1 | ~~Re-draw test~~ | **DONE-EARLY 2026-08-17, killed at 11/39 draws with a sharper verdict than designed**: sample-0 sweep complete — 5/10 canonically-degenerate items re-degenerate deterministically (~82K tok each), 5 converge clean; the remaining draws were byte-copies because **the per-draw seed is INERT on the non-speculative path** (O28 — `row_ids=[0]*B`, one sampler per BatchGenerator keyed by the FIRST request). Full entry in the lab notebook; `--samples` designs void until O28 is ruled | — | done; O28 opened |
| M2 | **`Qwen3.8-27B` recipes through funnel Stages 0–1** (load smoke incl. MTP-sidecar inertness, capacity ladder, convergence screen) | turns three stranded checkpoints into candidates; harness acceptance test begins | ~1–2 h | queued; hub upload **RUNNING** (ruling 5) |
| M3 | **opencode Run A** — 22 python × both winners, DIRECTIONAL, pre-registered extension rule | whether the B pick survives without aider | ~1.7 h | blocked on V4 |
| M4 | **opencode Run B** — `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` | third model on the agentic axis | ~0.7 h | blocked on M3 (registry cap restored 2026-08-17) |
| M5 | **DNF re-runs at shipped cap 262144** — only rows whose nonconv kind is `budget_hit`/`max_tokens` at a lower cap; converged rows are promoted-to-shipped-cap (ruling 7) | closes the cap-provenance gap cheaply | inventory first; pilot rule if >n=40 | queued |
| D1 | ~~BFCL vendored handler~~ | **CODE DONE 2026-08-17** (`1c2d91f`, Sonnet worker, architect-reviewed): native-FC passthrough via `bench/bfcl_handler.py` + `bench/run_bfcl_fc.py` — raw `messages`+`tools` to `/v1/chat/completions`, server-side template, deployed sampling, 4096-cap structurally unreachable, 17 mocked tests. **Live smoke PASSED 2026-08-17**: first pass 2/5 exposed `underscore_to_dot=False` (model called `math_factorial` exactly as the wire schema named it; checker wanted the dotted original); fixed -> **5/5** on simple_python for `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`. Ready for the first recorded run. Open architect call: retire the legacy `bfcl_shim/` prompt-mode path (its 2 tests fail on import, pre-existing) | driver-side | done |
| D2 | ~~Judge-panel reliability spec~~ | **SPEC DONE 2026-08-17**: `docs/superpowers/specs/2026-08-17-judge-panel-reliability-design.md` — pre-registered reliability gate (anchor accuracy ≥0.85, position-flip ≤0.30, Krippendorff α ≥0.5, length-bias and identity checks) that must pass on ~30 anchor pairs before any candidate ranking is admissible; pairwise forced-choice, blind, mixed-family, both orders. Execution stays parked until the B queue drains (operator ruling) | — | spec done; execution parked |
| D3 | Tune-encoding migration | **SPEC DONE 2026-08-17** (`docs/superpowers/specs/2026-08-17-tune-encoding-migration-design.md`): `tune` label in manifest + `<bench>.<tune>.jsonl` filenames, dirs stay pure registry names, idempotent migration script for the six pseudo-model dirs, isolation invariant tested. Sonnet worker implementing to spec | driver-side | worker running |
| D4 | Registry-hash-into-manifest hardening | provenance describes the registry actually in force | driver-side | queued |
| D5 | Regenerate `docs/work-queue.json` from this table; extend `bench/workqueue.py` with PAUSE/STOP/SKIP; per-item `bench_watch` + status aggregator | utilization + operator pause/redirect | driver-side | queued |

**Removed by ruling (2026-08-17):** ifeval three-way re-runs (4a — `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`
ifeval stays absolute-only); math500/lcb suffix-OFF re-runs (4b — O23 stays closed).

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
`docs/campaign-queue.md` / `docs/lab-notebook.md`; ledger updates go to
`docs/model-ledger.md`. Regenerate `docs/work-queue.json` whenever the queue changes.
Do not add narrative here.
