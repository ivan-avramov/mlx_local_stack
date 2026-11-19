# Judge subagent instructions

You have been assigned one or more `batchNN/` directories under your judge directory, each containing packet files named `pNNNN.md`.

For EACH `.md` packet file in your assigned batch directory:

1. Read ONLY that packet file. Never open, read, or modify any other file in this directory tree — in particular, never read `manifest.jsonl` (it names the models and would un-blind you), and never modify the packet `.md` file itself.
2. Use the `# SYSTEM` block as your rubric and the `# USER` block as the task; judge exactly as instructed there.
3. Write your verdict to the `.verdict.json` file named at the bottom of the packet, in the same directory, containing EXACTLY one JSON object: {"choice": "A"|"B"|"tie", "rationale": "<one paragraph>"}. No other content.
