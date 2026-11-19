Cold read, round 1 of 3. Read-only. The commit hook benchmark/bench/modelnames.py blocks prose naming a model by shorthand; it exempts
verbatim data by path. A frozen judge-panel export (benchmark/bench/p426_panel.py kv_export / _kv_write_packets / kv_freeze; layout
<panel>/<member>/<judge label>/batchNN/pNNNN.md plus manifest.jsonl, FROZEN.json, README_JUDGE.md per member; verdicts written beside
packets as pNNNN.verdict.json) holds the verbatim model answers a judge sees, and 423 lines ("the uniform distribution", "the quantized <!-- allow-shorthand -->
model") blocked its commit. The fix adds _PANEL_PACKET exempting only batchNN/pNNNN.{md,verdict.json,failed.txt} under
benchmark/results/{p426,m76}/panel/. Diff: fix.diff here. Question: can it exempt prose that should stay checked, or miss a real packet
/ verdict path the panel writes? Numbered findings with severity, file:line, scenario; "no findings" if none. Do not modify files.
