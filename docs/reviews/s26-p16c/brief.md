Cold read, round 1 of 3. Read-only. Two commit hooks (benchmark/bench/piicheck.py: PII; benchmark/bench/modelnames.py: model-name
shorthand) blocked committing a frozen judge-panel export under benchmark/results/m76/panel/. (1) PII: four packets quote a
model-written Linux path `/home/dev/projects/*`. Precedent S24-P17 (both boxes are macOS; a real home is /Users/<name>/) suppresses <!-- allow-pii-pattern -->
ONLY the `/home/` pattern on anchored model-output row paths; the fix adds the panel packet layout <!-- allow-pii-pattern -->
(<member>/<judge>/batchNN/pNNNN.md) to that list — /Users/, tokens, hostnames stay enforced. (2) Names: each KV member's generated,
sha-bound FROZEN.json embeds every item's task prompt verbatim ("static" in an exercise text); the fix exempts m76 panel <!-- allow-shorthand -->
<member>/FROZEN.json and manifest.jsonl (P426's FROZEN stays checked per an existing rule; its records embed no prompts).
Diff: fix.diff here. Question: can either exemption let a real home path, username, token or hostname, or real prose, through? Numbered
findings with severity, file:line, scenario; "no findings" if none. Do not modify files.
