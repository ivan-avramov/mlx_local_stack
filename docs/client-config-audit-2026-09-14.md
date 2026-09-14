# Shipped client configuration audit — 2026-09-14

The registry remains the source of truth. Audited OpenCode, aider, Zed, VS Code and OpenWebUI against current model names, routes, capabilities, context/output limits and sampling/thinking defaults. Seven main registrations and the task model are consistent; the two benchmark-only candidates remain confined to that carrier. The first approved/default pick remains `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`; the second approved pick remains `Qwen3.8-27B-mlx-uniform-4bit`.

## Corrections

- OpenCode now derives `attachment` from registry vision capability. `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` and the task model remain text-only.
- OpenCode now explicitly declares text/image input for vision models and text-only input otherwise, with text output. In installed OpenCode1.18.30, attachment support and image-input capability are separate: omitted modalities can replace image content with an unsupported-input error. [Schema](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/core/src/v1/config/provider.ts#L52-L59), [capability mapping](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/provider/provider.ts#L1427-L1447), [image handling](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/provider/transform.ts#L385-L416).
- OpenCode's `limit.context` now declares the full model window, with a separate `limit.input` and unchanged `limit.output`. For both approved picks:262144 total,159744 input,102400 output. Previously context already subtracted output, and OpenCode's overflow logic reserved output again. The explicit input branch still retains OpenCode's own extra compaction reserve. [Installed-version overflow rule](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/session/overflow.ts).
- Regenerated the main and benchmark OpenCode files. Updated all four client READMEs: current seven-model inventory/defaults, supported effort inheritance, aider's retired-harness status, and current VS Code installation guidance.

Aider, Zed, VS Code and OpenWebUI generated files already matched the registry. Registration-only carriers correctly inherit omitted sampling from server `generation_defaults`; KV precision, MTP, preallocation and idle retirement remain server-side settings. No registry values were changed.

## Validation and limits

Eight new regressions failed before their corresponding fixes. All52 configgen tests now pass; `configgen check` and independent semantic carrier checks pass. Cold review verified the OpenCode context and resolved modality behavior against installed-version source. Usage/routing settings remain tied to the registry.

This is a configuration and generation audit, not a new end-to-end client benchmark. Historical client runtime evidence remains labelled historical in the READMEs. No installed personal client configs were overwritten, no OpenWebUI publication/restart was performed, and no model was loaded for this audit. Aider's existing5400-second timeout is unchanged; it is not newly certified for every possible long generation.
