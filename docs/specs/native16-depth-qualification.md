# C89 — Approved shipped-config depth qualification

Status2026-09-14: **APPROVED, PREPARING** (operator approved P648 with “proceed”; P649). This is qualification of the selected shipped configuration. It is not a model-selection or alternate-KV comparison.

## One model/configuration

Target `caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, served using the actual `main_models.yaml`. Repaired companion `caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter`, `draft_kind: mtp`. Model and drafter weights remain unchanged.

| Setting | Value |
|---|---|
| KV | `kv_bits: 0` (native16); declared `kv_quant_scheme: turboquant` inactive at zero bits; `quantized_kv_start: 0` |
| Context cap / active preallocation | `262144` / `262144` |
| Prefill step | `512` |
| Idle cache retirement | `cache_session_shrink: true` |
| Sampling | temperature0.5, top_p0.95, top_k20, min_p0.0, presence_penalty0.0 |
| Thinking | enabled, reasoning_effort medium, thinking_budget81920 |
| Maximum generated tokens |102400|
| Runtime | MLX-VLM522671c4, MLX-Serveb632280, MLX/Metal0.32.2 |
| Sessions / APC |2 retained sessions, APC absent |

Freeze the actual registry and verify all values against it before launch; if it changes, revise this proposal rather than silently testing stale settings. Local weight-path overrides stay private. No other model, KV state, predictor-OFF arm or old runtime is included.

## Tests and fixed request ceiling

| Test | Nominal prompt-token grid | Trials | Requests | Historical request time |
|---|---|---|---:|---:|
| Multi-needle retrieval |8000,32000,64000,96000,128000|Five independently seeded prompts per rung; five codes at10/30/50/70/90% depths within each prompt|25|5140.4s ≈1h26m|
| Chain-4 variable tracking |8000,16000,24000,32000,48000,64000,96000,128000,156000|Five seeded prompts per rung through64000; three at96000/128000/156000|39|6628.2s ≈1h50m|
| Calibration |One fixed ASCII-filler tokenization calibration before each test|Generation limited only for calibration; excluded from quality scoring|2|Additional overhead|

**64 scored requests +2 calibration requests =66 calls maximum.** Retrieval asks for all five embedded codes; score exact recovered codes and report each depth separately. Reasoning follows four linked variable assignments distributed through filler and asks for the final numeric value; exact-match grading. This tests retention and simple multi-step tracking at depth, not difficult reasoning or repository editing quality.

Use the existing builders/scorers and M41 prompt-generation seeds. Freeze a separate explicit sampler seed per `(axis, ctx, trial)` before generation; prompt randomization is not sampler seeding. Each request receives deployed full budgets, with no lower thinking cap or tuning changes. Record actual prompt lengths and resolved budgets. Enforce actual prompt_tokens≤159744 (=262144−102400) before claiming the full output allowance; a larger prompt is a protocol/budget mismatch to resolve, not an intended-budget quality result. The156000 top leaves space for the full102400-token output allowance inside the262144 total context; the full-capacity probe at261449 prompt tokens is already complete and is not repeated here.

An included five-prompt pilot per test runs first: retrieval selects one seeded trial at each of its five rungs; reasoning selects five seeded-random task instances from its complete39-task set. Freeze this selection offline before any output is inspected. Pilot calls are part of the66 maximum, never added or replaced. Assess mean/max runtime, completion behavior, correctness and source/config checks before queuing each test's remaining prompts. Run one test at a time, one resident model, and unload between tests.

## Qualification and supervision

Report ordinary accuracy and strict resolved-budget success, convergence and failure kinds for each rung. Use the existing0.85 effective-context threshold; report every miss, per-depth retrieval result and budget hit rather than hiding them in one overall average. Unknown/invalid responses are not passes. Preserve genuine model failures; do not substitute easier cases, lower the budget or automatically change the registry. Any unexpected quality/convergence failure receives inspection before expansion; do not broaden the study automatically. Findings are bounded to these prompts, not a population-equivalence claim.

Real HTTP/protocol/provenance failures abort unscored, with no retries. Verify actual endpoint/listener ownership, model/drafter paths, worker flags, package/import paths and registry fingerprints. Use exclusive-create outputs and preserve full requests/responses privately. Validate the instrument with fake-only tests and cold review before launch. Require a known-positive daemon,300-second critical assessments, completed-prompt progress, mean/max forecasts and runner-exit records. Memory remains a rough48GB guideline, not a numeric stop rule.

Derive request timeouts from the full generation allowance and a conservative decode floor plus prefill headroom; the4–5hour planning window is not a timeout. A legitimate runaway may take much longer. Operator approval covers this66-call scope; no expanded or alternate-configuration study is authorized.

## Estimate and Phase 2 implication

The recorded M41 request walls sum to **11768.6s =3h16m09s** for the64 scored requests. These are historical TQ4/older-runtime measurements used only to budget work, not a comparison arm or a prediction of native16 speed. Reserve **4–5hours** including loading, calibration, instrumentation and tail headroom. Re-estimate after the included pilots; no assumed native16 speedup is deducted. Source: the per-model `retrieval.m41on.json` and `reasoning.m41on.json` rows (39 reasoning draws, corrected C76).

This is the remaining shipped-native16 depth check proposed before Phase2 closure. MTP/KV selection, runtime/cache repairs, capacity and bounded code/vision checks are already complete. C77/C78 historical comparisons remain deferred and are not proposed closure blockers. On successful completion, recommend closing Phase2 at the measured scope, preserving all coverage limits; do not imply universal quality certification or unlimited prompt-plus-output length.

## Instrument amendment — 2026-09-14, after the first calibration

The first retrieval calibration returned3210prompttokens, exactly matching the offline tokenizer, but the instrument rejected null final-answer content and2reportedcompletiontokens for a `max_tokens:1` thinking-only response. No scored request ran. The saved C84 capacity calibration also requested1token and reported2, so this was an existing response shape that the new instrument should have covered. Preserve the failed instrument run and raw response; this is not a failed model-quality case.

The reviewed v2 instrument adopts that one already-spent calibration with pinned original request/response/protocol/registry hashes, verifies the exact original request and zero prior scored rows, and journals its provenance. It must not issue another retrieval calibration. Retrieval still consumes at most26calls across both versions; reasoning40; total66. The source runtime, model weights, deployed settings, prompts/seeds and budgets remain unchanged. The sole registry amendment redirects monitoring logs to the private work directory; compare all other parsed values exactly.

Calibration accepts1–2reportedcompletiontokens and null final content; it remains excluded from quality. Cached-path source inspection explains the extra length-terminal count: the finalization chunk receives a default one-token count before the endpoint sums chunks (C91, deferred reporting repair). A quality response with valid length termination and null content is preserved as an empty-answer, nonconverged measurement. A reported102401tokens is accepted only for length termination, annotated as the one-token reporting overrun and retained as a budget failure; no requested budget is raised and no raw count is rewritten. Other malformed/transport/provenance failures still abort unscored. Tests and cold review precede a new freeze and launch.
