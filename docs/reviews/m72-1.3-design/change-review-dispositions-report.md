# M72 1.3 — four-eyes strict: test-writer review + panel verify (round 2 of 3) of candidate 1, designer's dispositions

Candidate 1: implementer `claude -p` Claude Opus (`claude-opus-5-5`, session `628dc743-9c21-4fd4-821d-57faf30ee7c1`), patches against
fork `608e33ac`, mlx-serve `1ddf6f84`, stack `01a31db0`. Test-writer: `claude -p` Claude Sonnet (`claude-sonnet-5-5`, session
`0ca8cd04-c24d-491f-bcf9-5a7fc548b3be`, continued over three deliveries); tests frozen 2026-11-11 09:16:18, candidate revealed
10:31:53, amended tests re-frozen 10:54:12. Panel verify: cursor-agent `--mode ask` `gpt-5.6-sol-high` and `glm-5.2-high` (fresh
sessions — the design-review sessions cannot be continued; briefed; user instructions unconfirmed), raw
`opinion-verify-gpt-5.6-sol-high.md`, `opinion-verify-glm-5.2-high.md`. Both: design-ledger rows 1–15 resolved.

## Frozen tests judged invalid (shown to the operator; amended by the test-writer, delivery 3)

| tests | reason |
|---|---|
| A7 violation rows (3) | planted γ = 1025 rounds to 1024 in bf16 (exactly the accepted bound); codebook scaled from 0.17 never exceeds 1 |
| A4(c) seeded rows (6) | spec error (erratum v1.1b): speculative sampling preserves the distribution, not the samples — the test-writer's control diverges with the mode absent |
| p2s prefill logits, 5 % (2) | tolerance not pinned by the spec; replaced by the 2× rule vs mode-off TQ4's own deviation from native16 |
| `/health` (1), load order (7) | test setup (no loaded generator; stub loader without the ledger-15 stamps) |
| stack box-notes wording (1) | over-specific |

Kept frozen (valid; candidate fix): legacy flag spelled off (3), kernels refuse a batch cache (1).

## Findings

| # | finding | by | severity (designer) | disposition | reason / change |
|---|---|---|---|---|---|
| 1 | legacy flag refused when set to `0` / `false` / `no` | test-writer F4, GLM D2 | minor | adopted (fix) | refuse only when production's parse enables legacy (erratum v1.1c) |
| 2 | kernel entry points do not assert the cache class | test-writer F3, Sol P19, GLM D3 | minor | adopted (fix) | assert `type(cache) is TurboQuantKVCache` |
| 3 | `kv_quant_mode: prod` accepted by mlx-serve, refused by the worker (and read from an env the CLI may not set) | Sol P17, GLM D8, test-writer F2 | minor | adapted (fix) | refuse consistently: mlx-serve with a mode, the worker from the value the cache is built with |
| 4 | explicit falsey `tq4_attention` values read as absent | Sol P18, GLM D5 | minor | adopted (fix) | refuse values outside absent / `m72_v1` / `m72_exact` |
| 5 | manifest route counters gathered once, at creation | test-writer F6, GLM D6 | minor | adopted (fix) | also at exit, with the router re-verification |
| 6 | four stack tests pin fingerprint v8 / mock three controls | implementer I3, Sol P21 | minor | adopted (fix; scope extended to those four tests) | the spec requires the v9 bump |
| 7 | unregistered `pytest.mark.slow`; instrument entry points widen `tq4_fast`'s surface | Sol P22, GLM, test-writer F8 | minor | adopted (fix) | remove the marks; document the instruments as test instruments |
| 8 | multi-query `mask=None` falls back instead of p2s | GLM D1 (major), D7 | — | declined | `mask=None` with L > 1 means full (non-causal) attention; p2s is causal only, so the fallback is correct; the model passes `"causal"` for N > 1 (`base.create_attention_mask`), and the synthetic-model routing tests show `p2s` > 0 through the real forward |
| 9 | `require_policy_stamps` beyond the load-order line | GLM D4 | — | adopted as spec clarification | erratum v1.1c adds it; supported by ledger row 15 |
| 10 | p2s at L 6–8 not forced fused | Sol P20 | minor | adapted (spec) | MLX has no forced kernel for those shapes (I2); erratum v1.1c |
| 11 | real-model A4 (b) / A5 / A6 / A7 unrun; seeded v1.1b test missing | Sol P16 (major) | — | adopted (process) | the designer runs the real-model criteria before Accept; seeded rows amended (delivery 3, pass) |
| 12 | verifier's local rebinding of `scaled_dot_product_attention` fragile | test-writer F5 | — | declined — residual | correct today (bound before use; A3 goldens and the mode-off suites guard it) |
| 13 | I1: MLX fused SDPA reads stale scratch rows up to its key-block boundary; NaN in a recycled buffer poisons the output | implementer | — | adopted in candidate 1 | zero-filled tail to a 128-row boundary; verified by the test-writer under NaN / ±Inf poisoning (the prototype fails); `dev/m72_scratch_prefill.py` keeps the hazard — residual, dev only |

Test-miss notes: none beyond rows 8 and 11.

## Fix rounds, real-model criteria, residuals (2026-11-11)

- Fix round 1 (fresh implementer `claude -p` Claude Opus, session `21231aa0-bf17-4ed7-b7ba-d3bdc7667320`): findings 1–7 applied;
  test-writer delivery 4: each of 1–5 has a test failing on candidate 1 and passing on candidate 2; full fork suite 10,729 passed,
  mlx-serve 347 passed + 1 known layout failure. Left open: two stack reasoning-resume tests failing under fingerprint 9.
- Fix round 2 (operator C320; fresh implementer session `610dbeb5-aad0-4d11-943a-0ecca1124491`): the test-writer's experiment refuted
  the designer's stated cause (the `pin_mtp_scan` fixture) and located it (`stub_manifest_lite` in `test_run_reasoning.py`); the
  misdirected first dispatch was stopped after 15 s before any edit (exit 143); the corrected round added `tq4_attention: off` to the
  stub; test-writer delivery 5: the two tests fail on candidate 2 and pass on candidate 3; verdict merge.
- Real-model criteria (designer, `benchmark/results/m72/m72-13/`): A4 (a) / (b) / (c), A5, A6 (both arms), A7 pass; divergence
  diagnostic recorded. Designer instrument error found and fixed on the way: the first A4 run passed no temperature (unseeded
  sampling, not greedy); superseded, kept locally, not cited.
- Frozen tests at merge: formatted by the repositories' own tools (black / isort / ruff), AST-identical modulo isort order and
  docstring whitespace; one comment reworded for a naming-hook false positive ("the 16-bit patterns" → "fp16 / bf16 bit patterns").
- A6 deviation: `Request completed … backend=` is not in the worker log at its level; the served-path proof is the route counters
  (the batching path would count `fallback:batch_cache`).

Residuals (recorded once): the stale `_TQ4_MANIFESTS` entry per router port and the exit snapshot existing only in the process that
gathered the manifest (test-writer, minor); the verifier's local rebinding (row 12); `dev/m72_scratch_prefill.py` keeps the I1 stale-row
hazard (dev only); continuous-batching requests (session cache off / anonymous sessions off / message-less requests) take today's TQ4
path (S21-P10, for 1.4).
- Merge-time docstring edit (non-semantic) in the frozen `benchmark/bench/tests/test_m72_13_harness.py`: "load the 27B model" →
  the full registry name (naming hook).
