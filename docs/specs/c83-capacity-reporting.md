# C83 — Capacity reporting and supervision

Operator approved the C83/C76 cleanup on2026-09-14. CPU-only; no new model measurements, fork changes or registry settings.

## New capacity schema

Schema2 separates `execution_status`, `within_memory_target` and `retrieval_acc`. The default `memory_target_gb` is48, a descriptive guideline. A completed above-target request continues the approved grid and keeps its retrieval co-score. Missing/invalid MLX telemetry is null, not a pass or failure. Request completion alone does not establish sustained memory-pressure stability.

The scorecard reports `max_completed_ctx`, `max_within_memory_target_ctx` and `retrieval_coscore_max_passing_ctx`. Context values are requested nominal rungs; inspect `prompt_tokens` for attained lengths. These are bounded-generation co-scores, not dedicated retrieval-depth certification. Schema2 does not emit the misleading legacy `fits`, `capacity_gate_pass`, `max_fitting_ctx` or memory-conditioned `retrieval_effective_ctx` fields. The Python `gate_gb` parameter is replaced by `memory_target_gb`; the CLI retains `--gate-gb` only as a deprecated spelling for the descriptive target.

Historical JSON/JSONL, source snapshots and private wrappers remain immutable. Old flags describe the original threshold calculation. The scorecard can derive a new summary from old records without mutating them; save it separately with the input hash and recorded original threshold. The old bulk in-place `benchmark/rescore.py` is retired.

## Failure and persistence contract

Timeouts, request exceptions and malformed terminal responses produce one unscored error row and stop the ladder. HTTP500 alone does not diagnose OOM. A legitimate `length` response is completed but nonconverged; preserve its co-score. Convergence uses the resolved budget when known, otherwise remains unknown. Calibration requires valid usage and a plausible chars/token ratio for its fixed ASCII filler before constructing large contexts.

Rung requests carry explicit `--seed` (default0), recorded in the manifest; deployed sampling and bounded256-token limits remain unchanged.

The CLI refuses existing ladder/scorecard/manifest destinations before model calls, creates outputs exclusively, and flushes each rung. Use a fresh `--out-tag`; never rewrite a historical run. Incomplete grids and provenance failures return nonzero. The sequence wrapper stops on run or unload failure; it cannot label a failed queue `ALL_DONE`.

## Capacity daemon

`bench.run_capacity` automatically starts a daemon thread while its detached driver runs. Redirect stdout/stderr to the run log. It emits a labelled synthetic known-positive `SELFTEST`, periodic300-second assessments and a `runner-exit` record. A failed monitor propagates failure and cannot certify successful completion. Abrupt process termination cannot emit an exit record; absence of that record requires PID/exit-status investigation.

Pass `--expected-rung-seconds` with one matched baseline duration per grid entry. Forecasts scale the remaining baseline by observed total duration divided by expected duration for completed rungs; report observed mean and maximum separately. Baselines are estimates, never deadlines. Overdue unfinished rungs get an unknown ETA and a review recommendation. Without a baseline, the monitor explicitly reports rate/ETA unavailable rather than extrapolating short contexts into larger ones. Preload, calibration and reporting are named separately; rung ETA excludes those overheads.

Progress counts completed rungs, not process busyness or failed attempts. Non-streaming prefill can legitimately produce no new completion between assessments. Output assessment includes errors, convergence/unknown counts, completion lengths and retrieval co-scores. Numeric memory flags alone do not stop or reject a run; real failures and slowdowns require inspection. Do not reuse the frozen C84 generic-smoke wrapper as a capacity monitor.

## Verification

Fake-only regressions cover above-target continuation, memory-independent retrieval, failure/unknown classification, malformed responses, calibration bounds, resolved-budget reporting, exclusive-create outputs, sequence failure propagation and standard JSON. A real short-interval daemon test exercises selftest, periodic and terminal events; a failing sink proves monitor failure propagates. Validation:94 relevant CPU tests pass, including neighboring retrieval/convergence/generic-monitor checks; independent cold review passed48 focused tests with model/network/subprocess access blocked. No model was loaded for these tests.
