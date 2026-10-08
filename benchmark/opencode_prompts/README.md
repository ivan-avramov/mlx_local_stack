# Benchmark system prompts

`opencode-1.18.15-default.txt` is a verbatim copy from https://github.com/anomalyco/opencode,
tag `v1.18.15`, commit `d7b115f623760e68a4749d16508a9eca350f246f`,
path `packages/opencode/src/session/prompt/default.txt`.
License: MIT; `Copyright (c) 2025 opencode`. Full license: [LICENSE](LICENSE).

Use `--agent-system-file benchmark/opencode_prompts/opencode-1.18.15-default.txt` with the v2 probe.
The base prompt is replaced; opencode keeps its environment, skills and date instructions.
The source bytes and written carrier are hashed independently, and the scaffold label gains `+sys:<sha8>`.
