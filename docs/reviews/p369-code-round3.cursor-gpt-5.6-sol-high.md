F1 — RESOLVED. Continuous batching always builds plain `GenerationBatch`; lockstep B>1 refuses at `speculative/utils.py:423-434`.

F2 — RESOLVED. Batched path is plain; inline first-token termination commits before yielding at `speculative/utils.py:396-404`.

F3 — RESOLVED. Plain `GenerationBatch` retains per-row budgets at `generate/ar.py:2757-2772`.

F4 — RESOLVED. Tests drive production `BatchGenerator`/`generate_step` and structurally forbid speculative construction; they fail on the round-1 implementation.

F5 — RESOLVED on the deployed cached path. The wrapper clears on close, cancellation, `GeneratorExit`, and exceptions—including publication failures—at `generate/dispatch.py:1583-1591`; the server always closes at `server/generation.py:2022-2023`. An abandoned, retained generator cannot be cleared until closed or collected. Batched/uncached requests have no session state.

F6 — RESOLVED for the actual target forward: capture kwargs are gated by effective speculation at `generate/ar.py:2628-2647`. The spy assertion is appropriate because F6 has no token/state difference, but it misses chunked prefill and public `batch_generate`.

Routes — CLOSED. No repository request path reaches MTP `_mtp_rounds_batch`; its branch remains at `speculative/utils.py:278-296` but is unreachable through `BatchGenerator`. Direct low-level calls remain possible.

B==1 cached MTP — CLEARED. Prefix cuts and commits are selected before mutation at `speculative/mtp.py:816-856`; accepted-token, bonus, first-token, length, stop, forced-token, and next-turn state handling match plain decoding. M2–M5 remain intact.

Tests — Production dispatch is exercised, although F5’s claimed raised-exception case is not explicitly tested. Global seeding makes unseeded tests deterministic but reduces them to one fixed random input.

F7 — HIGH — `generate/ar.py:2370-2388`, `models/qwen3_5/language.py:1488-1517`. Batched MTP falls back to plain decoding but is still presented to the chunked-prefill policy as MTP after capture kwargs were removed. Qwen3.5 therefore disables chunking; long prompts can allocate the documented dense N×N mask and OOM. Fix by passing an effective plain configuration (`draft_model=None`, `draft_kind=None`) to the policy for MTP fallback, including `batch_generate`’s preflight at `generate/ar.py:4064-4079`; add a non-None `prefill_step_size` regression test.

F8 — LOW — `generate/dispatch.py:1352-1369,1371-1564,1583-1591`. Publication occurs after the terminal yield. A direct API consumer that reasonably closes on `finish_reason` loses an otherwise valid session and cold-prefills next turn. The server exhausts the generator, so deployed correctness is unaffected. Fix by publishing before exposing the terminal chunk or documenting/draining explicitly.

F9 — LOW — `tests/conftest.py:52-68`, `tests/test_models.py:2217-2264`. Global reseeding removes run-to-run input diversity; the MoE test additionally selects known-passing seeds. Existing explicitly seeded tests are unchanged, but unseeded randomized tests now prove one case only. Use a deterministic seed corpus where diversity matters; P385 can own the known failing MoE seeds.

VERDICT: NOT CLEARED F7

[exited with code 0]
