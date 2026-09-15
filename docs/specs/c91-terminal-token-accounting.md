# C91 — Cached terminal-token accounting repair proposal

Status: proposed, not armed. C89 is complete; preserve its frozen runtime and historical counts. No new model calls or fork edits are authorized by this document.

## Observed defect

The C89 calibration requested `max_tokens: 1` and received one text token in reasoning, `finish_reason: length`, null final content and two reported completion tokens. The saved C84 calibration has the same shape. Prompt usage is correct at3210; C89 retains the raw response and excludes calibration from quality.

`generate/dispatch.py` emits a finalization chunk after the last non-EOS token. On length termination, its cumulative `generation_tokens` repeats the previous value. The cached bridge in `server/generation.py` gives every `StreamingToken` the default `token_count: 1`; `server/openai.py` sums these increments. On EOS/stop, the final chunk can represent a newly counted EOS. Do not subtract one universally or rewrite historical results.

## Proposed change

- Edit the parent MLX-VLM fork only. Derive each cached wrapper's `token_count` from the increment in cumulative `GenerationResult.generation_tokens`, following the existing diffusion emitter's accounting pattern.
- Keep the change at the cached conversion seam. Preserve text, reasoning, terminal reasons, sampling, cache ownership, predictor execution and source model numerics. Avoid endpoint-specific compensation.
- Update test fixtures to represent real token and finalization sequences. Assess whether a helper reduces duplication; introduce one only if it reduces the maintenance burden.

## Acceptance criteria

1. Watch a failing regression reproduce the saved max1/length case; the repaired wrapper reports one token and preserves the original text/terminal metadata.
2. Cover multiple non-EOS tokens followed by repeated-count finalization, newly counted EOS/stop, zero generated tokens, and thinking-tag subtraction at the endpoint boundary.
3. Verify streaming/non-streaming consumers and cached cold/reuse paths. Existing diffusion accounting and MTP counters must remain correct; malformed or decreasing cumulative counts must not become fabricated successful usage.
4. Run the relevant cached-reporting, generation and endpoint suites, then the required fork checks. Obtain cold review against these criteria.
5. Propose a bounded real-server validation with exact requests before arming it: the saved calibration shape plus normal-stop and bounded-length controls on shipped `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`. Include the normal daemon/lifecycle checks. Do not rerun the completed C89 ladder automatically.

Commit a coherent repair after review. Push the fork only with explicit in-turn approval, fetch it through the stack submodule's GitHub origin, then commit the submodule bump. Record the new runtime separately from C89. Preserve all original C84/C89 counts and provenance.
