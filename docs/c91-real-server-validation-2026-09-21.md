# C91 — real-server validation of cached-path token accounting (2026-09-21)

Status: spec items 4–5 DONE. Cold review PASS-WITH-GAPS (findings below); bounded live validation PASS on
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` in the shipped daily-driver configuration.

## What ran

- Stack brought up with `runserver.sh` (the operator's path, unchanged): router `mlx-serve` with
  `MLX_SERVE_CONFIG=main_models.yaml`, `MLX_VLM_CACHE_SESSION_MAX=2`, `APC_ENABLED` absent (verified on the
  router and worker pids). Worker imported the bumped fork `4d4575a7` (venv resolves `mlx_vlm` from
  `src/mlx-vlm`). Model served MTP-ON, native16 KV, deployed sampling for every omitted field.
- Six chat-completions requests through the router (`:8000`), non-stream and stream, temperature 0.0,
  every other sampling field omitted (deployed defaults). Private wire captures:
  `$STACK_WORKDIR/scratch/c91-validation-20260921/run1/` (`*.raw`, `*.request.json`, `summary.json`,
  `provenance.txt`). Four extra requests direct to the worker (`:8091`) for the two endpoints the cold
  review flagged (`run1-endpoints-worker8091/`).
- Tear-down afterwards: 0 listeners on 8000/8091/8092/3000, no `mlx` processes, stack containers down.

## Results (all six matched their pre-registered expectation)

| case | mode | finish | reported completion_tokens | expected | offline text tokens (reasoning + content) |
|---|---|---|---|---|---|
| calibration shape (FILLER×200, `max_tokens 1`), prompt 3210 | non-stream | length | **1** | 1 | 1 (`The` in reasoning) |
| same | stream | length | **1** | 1 | 1 |
| bounded (`max_tokens 64`) | non-stream | length | **64** | 64 | 61 |
| same | stream | length | **64** | 64 | 63 |
| normal stop ("reply OK") | non-stream | stop | **27** | = stream | 23 |
| same | stream | stop | **27** | = non-stream | 25 |

- The C89 calibration shape now reports one token, not two, in both modes. Prompt tokens unchanged (3210,
  matching the C89 offline tokenization).
- Stream and non-stream agree on every count; their texts are identical after whitespace normalisation
  (the stream path keeps boundary newlines around `</think>` that the non-stream message strips, which is
  why the offline text counts differ by 1–2 while usage is equal).
- Offline text counts are a plausibility check only: usage additionally counts the generated
  `</think>` wrapper and EOS tokens, which are real generated tokens, so usage − text ≈ 2–3 as observed.
  The `tokenizers` count of the text is not the fork's count and was not expected to match exactly.
- `/v1/responses` and `/v1/messages` (worker-direct, router does not expose them): calibration shape
  reports `output_tokens 1` in both modes.

## Cold review (independent, cold context) — verdict PASS-WITH-GAPS

Criteria 1–3 of `docs/specs/c91-terminal-token-accounting.md`: C1 PASS (mechanism verified against the
producer, `dispatch.py` finalization repeats `n` on length and carries `n+1` for a real EOS on stop; end-to-end
via TestClient 1/1/1 on chat, completions, stream). C2 PASS-WITH-GAPS. C3 mixed. 1217 fork tests green across
the seam, endpoint, diffusion/MTP and fork-guard suites; nothing needs reverting. Findings, with the
live-server disposition added:

1. `/v1/responses` and `/v1/messages` non-stream sum `+1` per chunk and ignore `token_count`
   (`server/openai.py:1722`, `server/anthropic.py:936`); driven through the cached bridge in a TestClient
   they reproduce the C89 defect (2 for max-1/length). **Latent on the live server**: only chat completions
   pass a `session_id`, so only chat completions take the cached path; both endpoints reported 1 live. Fix is
   reading the field (`getattr(tok, "token_count", 1)`), inside the spec's fence.
2. Mixed chunk sequences (cumulative → no-cumulative → cumulative) double-count: the `None` branch emits 1
   without advancing `counted_tokens` (`generation.py:1812-1813`). Not reachable from today's
   `stream_generate`; a silent inflation path if a producer ever mixes shapes.
3. Non-stream chat thinking-tag subtraction is unclamped (`openai.py:2651`) while the stream sibling and both
   Anthropic sites clamp. No realistic reaching case found; pre-existing.
4. Cached-path log telemetry (`generation.py:1838`, `tel_n += 1`) counts chunks, so the periodic tok/s line
   over-reports by one on length termination. Log only.
5. No endpoint-level regression guards the repair; the existing endpoint tests hand-build `StreamingToken`s.
   Two body-level assertions in `test_cached_tokens_reporting.py` would have caught finding 1.

Disposition: C99 (operator decision) — a small hardening commit in the fork covering 1, 2, 4 and the tests in
5 (3 optional); or close C91 as-is with the findings recorded. Historical C84/C89 counts stay as recorded.
