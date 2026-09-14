# aider config for mlx_local_stack

**aider was retired as a benchmark harness on 2026-08-16.** These client configs remain maintained; no new aider benchmark arms are implied.

`aider.model.metadata.json`, `aider.model.settings.yml`, and `aider.conf.yml` are generated from [main_models.yaml](../main_models.yaml). Regenerate with `uv run python -m configgen generate` and check with `uv run python -m configgen check`. Keep personal additions outside the generated files.

The main provider uses `http://localhost:8000/v1` and lists the seven registry models with `presentation.role: main`. Candidates are excluded from these client files. The default is `openai/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`; the second approved pick is `openai/Qwen3.8-27B-mlx-uniform-4bit`. See the root README for current ranking and evidence.

## Files and installation

| Repository file | Installed file | Purpose |
|---|---|---|
| `aider.model.metadata.json` | `~/.aider.model.metadata.json` | Input/output limits and vision capabilities |
| `aider.model.settings.yml` | `~/.aider.model.settings.yml` | Edit format, sampling, thinking, and weak-model route |
| `aider.conf.yml` | `~/.aider.conf.yml` | Default model and router endpoint |

Copy or merge these files into your personal configuration, adding the leading dot. Alternatively, pass them with aider's `--model-metadata-file`, `--model-settings-file`, and `--config` options. The local API key is `not-needed`.

Start the stack when you intend to use the client, then run `aider` from your project. Switch with `/model openai/<full-registry-name>`. Model IDs and routes must match the generated files exactly.

## Model roles and capabilities

The weak model is `openai/mlx-community/Qwen2.5-1.5B-Instruct-4bit` on `http://localhost:8092/v1`, for lightweight summaries and commit messages. The editor model is unset, so architect mode uses the selected main model for both roles. Architect mode is not enabled by this configuration.

`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` is text-only; its metadata disables vision and PDF input. The other six main registrations advertise vision. Edit formats come from each model's registry presentation settings.

## Sampling and limits

Main-model `extra_params` carry the registry's family-supported sampling, with thinking controls under `extra_body`. For both approved picks, the input budget is 159744 tokens, output ceiling 102400, and thinking budget 81920; temperatures are 0.5 and 0.6 respectively. Other models keep their own limits and tuning.

The server accepts `reasoning_effort`; the two approved picks inherit `medium` from registry defaults when this client omits it. The older claim that mlx-serve ignores effort settings is obsolete. Explicit client overrides can change the measured configuration, so preserve the registry tune when comparing results.

KV format, MTP, full-cap allocation, and cache retirement are server settings. The generated aider settings retain their existing 5400-second request timeout. This audit did not measure aider transport behavior or certify a new harness run.
