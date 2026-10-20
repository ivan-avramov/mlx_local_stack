# P415 plan — Cursor plan review round 2 of 3 (gpt-5.6-sol-high, `--mode ask`), plan v2

I’m checking the accepted fixes against the actual P369/P400 execution boundaries, especially where the plan still permits a self-derived attestation or an undetected interference window.Q1 — OPEN (High)

`generation_defaults` is serving configuration, not a non-serving allowlist field. The server receives it through `--generation-defaults`, and this request omits temperature, top-p, top-k, min-p, thinking mode, and reasoning effort. If `_build_command` drops or changes the block, sizing and measurement can agree with each other under fallback defaults and still report `COMPLETED` for the wrong served configuration.

Closure requires registry → canonical `--generation-defaults` JSON → live server defaults → resolved request arguments checks.

Q2 — OPEN (High)

The plan permits required fields to remain `argv-only`, and configured values do not prove their behavior was exercised. For example, preallocation may reach the generation kwargs but be ignored by cache allocation; `kvmanifest` records codec properties, not capacity. Similarly, a `fused_v1` model attribute does not prove fused calls occurred, and a lazy-embedding flag does not prove chunked embeddings were used. Memory-limit settings from Q2’s original fix are also absent.

Require behavioral evidence for each peak-relevant field: cache-allocation/preallocation events, actual prefill chunk sizes, fused/automatic attention counters, lazy-embedding path usage, post-retirement shrink behavior, and resolved memory limits. No required field may remain `argv-only` while allowing `COMPLETED`.

Q3 — OPEN (High)

`Capture` observes `ResponseGenerator._preprocess_request`, but the cached-session path then passes the original prompt string to `stream_generate`, whose `_prepare_generation_inputs` tokenizes it again. The captured count and digest therefore describe the first tokenization, not necessarily the IDs actually prefilling the model.

A regression in the second path could prefill different IDs while sizing and `Capture` still agree. Capture the IDs at `_prepare_generation_inputs` or immediately before `generate_step`, and require them to match both the sizing digest and the earlier preprocessing digest.

Q4 — OPEN (High)

The monitor interval remains five minutes. A competing MLX process or power excursion can start and finish between ticks, contaminate a substantial portion of prefill, and remain undetected. The existing `Monitor` also runs ticks in a daemon thread, so implementation must explicitly propagate thread failure; T10 does not currently require that case.

Use ownership-aware interference checks on supervisor polls and request boundaries, add a canonical qualification lock for cooperating runs, and require monitor-thread liveness/error propagation before `COMPLETED`.

Q5 — CLOSED

The supervised process group, extinction checks, atomic state transitions, interruption handling, continuation, malformed-result handling, and final nonzero status address the lifecycle failure modes.

Q6 — CLOSED

Repeated stack/registry guards, clean gitlink-matched `mlx-serve`, imported-module-path validation, fork-ref attestation, version recording, and snapshot revision/blob checks bind the executable and artifacts sufficiently.

Q7 — OPEN (Medium)

“Match every stated field” treats missing historical fields as harmless. A reference lacking its MLX version, attention policy, preallocation, MTP state, or measurement boundary could therefore receive a delta despite comparability being unknown.

Define a mandatory reference schema containing every comparability field. Any absent or unknown required field must make the reference non-comparable; only complete, exactly matching fingerprints may produce deltas.

Q8 — CLOSED

Boot, request, and hard per-entry deadlines now bound each attempt; the 3,600-second job cap includes cleanup, retries are prohibited, and the approximately eight-hour worst case is disclosed separately from the nominal estimate.

Q9
- Severity: High
- Plan section: §1; §2 Q1; §2.1 Q1
- Problem: `type` is classified as non-serving, but the registry itself documents `type: vision` as the backend selector. `worker_argv` discards `_build_command`’s command prefix, while `worker.boot` always starts `mlx_vlm.server.cli`; the mlx-serve routing/process-selection layer is not exercised.
- Failure scenario: `_build_command` selects the wrong executable/backend because of a type-handling regression but emits compatible-looking arguments. The qualification tool strips that selection, boots mlx-vlm directly, and all prompt, manifest, and live checks pass, producing `COMPLETED` for a command shipping would not run.
- Fix: Parse and assert `type`, retain and validate the full `_build_command` command including executable/module prefix, and either launch that exact command or separately exercise mlx-serve routing. Add a test where the backend prefix is wrong while the trailing arguments remain valid.

VERDICT: DISAGREE Q1 Q2 Q3 Q4 Q7 Q9