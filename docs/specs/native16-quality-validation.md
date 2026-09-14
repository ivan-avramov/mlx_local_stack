# C88 — Shipped-configuration vision qualification

Status2026-09-14: **APPROVED, preparation** (operator after P620, P621). The operator narrowed this to qualification of the selected model as declared by `main_models.yaml`. This supersedes the proposed two-cache210-call study. No TQ4 comparator, depth ladders, calibration calls, visual-quality ranking or external judges are included.

## Exact scope

- Model: `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`.
- Serve the actual `main_models.yaml`; preserve its native16 KV, repaired MTP ON, medium effort and all declared sampling/cache settings. No experimental overlay. Keep local model-path overrides private; record the registry hash and verify declared settings against the committed registry.
- Final installed MLX-VLM522671c4 / MLX-Serveb632280, MLX/Metal0.32.2. One resident model, APC absent, retained sessions2. Verify actual worker flags/environment and source/package provenance before requests.
- Reuse all20 cases in `benchmark/corpora/vision_gate_v1.jsonl`, with their existing cached images and ground truths. Exactly two turns per image: describe the image; then supply the human ground truth in that conversation and ask the same model for PASS/FAIL.
- Use existing `vision_gate.run_one`, `parse_verdict` and `summarize` unchanged. Report every FAIL/null case and total PASS/FAIL/null. Keep the established16/20 aggregate smoke threshold, while explicitly reporting any individual failures. Convergence and truncation are separate diagnostics, not replacement grading. Do not manually grade extraction quality.

## Execution and evidence

Exactly40 generation calls maximum, no retries or extra warmups. A seeded-random five-image pilot (Random88 over sorted corpus IDs) is included in the20; assess its10 calls before continuing the remaining30. A model FAIL remains a valid measurement and does not silently remove an image. Transport/protocol/provenance failure aborts with nonzero status and preserves partial evidence, never a scored model FAIL.

Use deployed request parameters verbatim, with the existing explicit per-image/per-turn seeds. Generation max_tokens102400, thinking_budget81920, thinking enabled; no lowered budget. Derived per-request timeout21080s =102400/5tok/s +600s headroom, not an ETA. No published short-probe memory claim.

Freeze corpus, image bytes, registry, instrument and source hashes before launch. Persist private wire requests/responses and initial/final provenance; verify before each request. Each second-turn history includes the actual first-turn description. Exclusive-create output files protect prior evidence. No edits to code/config while live.

Run detached with an independent300-second daemon assessment, known-positive selftest, completed-case events and a runner-exit event. Report progress, mean/max case time versus historical19.28s/case, error/null/convergence diagnostics and whether correction is warranted. Assess the included pilot before continuing. Historical20-case/two-turn total385.6s (~6.4min) is a planning reference on an older config, not a runtime prediction.

After all20 cases, stop the owned router/model, publish PII-free canonical rows/summary/provenance in the repo, and update README/evidence/handoff with the shipped-config result. Preserve raw private evidence. No automatic config/rank change or push. Longer-context qualification and C77/C78 comparisons remain deferred proposals; this test answers only the specified image smoke question.
