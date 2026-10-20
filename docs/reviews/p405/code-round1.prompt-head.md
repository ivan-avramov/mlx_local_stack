Cold CODE review — ROUND 1 OF 3 (at most 3 rounds, then the operator decides open findings). Fork `mlx-vlm` branch
`p405-kv-scheme` HEAD `fbefe877`, on top of `p400-tq-width2` `abbbfc84`. Workspace `../mlx-vlm` at `24551869`; read with
`git show fbefe877:<path>` (read-only; modify nothing). Diff `abbbfc84..fbefe877` inline below; the approved-pending plan (v4, after
3 plan rounds) inline after it.

What changed: P405 — the server ignored `--kv-quant-scheme turboquant` because `runtime.config` is built at server-package
import, before `cli.main` writes the env. F1: `cli.main` rebuilds `runtime.config` from the final env before
`uvicorn.run` (production). F2: `get_cached_model` logs the codec it hands `ResponseGenerator`; the env-derived lifespan
log line is removed (production). F3 (dev harness): `dev/p369_phase2/kvmanifest.py` — the argv's KV codec under the CLI's
defaults, every resolved generator KV field + the TurboQuant mode, and an exact per-layer leaf manifest under the served
path's policy (`generate/common.py` `maybe_quantize_kv_cache`); wired into the worker's served state / `assert_served`,
every orchestrator job's expectation, the E1c entry, the smoke gate, and the P400 perf probe. Tests red-first (T1–T6).

Review adversarially: (1) correctness and completeness of F1 / F2 (any path where a stale config or env snapshot still wins;
ordering hazards; the removed log line's consumers); (2) does F3 model the served path exactly — the TurboQuant last-entry
exemption, the uniform branch, prealloc variants, nested CacheList paths, the MTP drafter's caches, quantized_kv_start —
and can any gate pass without its evidence (a manifest or KV expectation that can be absent, wrong, or self-referential:
expected derived from the observed); (3) do the tests prove what their docstrings say and are they red on the base for the
right reason; (4) anything that must change before the TurboQuant GPU runs (plan R3–R5, R7).

Findings ids K1 onward, each: severity, file:line, problem, failure scenario, fix. End with exactly one line:
`VERDICT: CLEARED` or `VERDICT: NOT CLEARED <ids>`. OUTPUT RULE: your FINAL message must contain EVERY finding in full,
then the VERDICT line.
