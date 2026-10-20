Cold CODE review — ROUND 3 OF 3 (the LAST round; afterwards open findings go to the operator). Fork `mlx-vlm` branch
`p405-kv-scheme` HEAD `79914344`; your round 2 (inline below) returned NOT CLEARED K7 K8 K9 on `fbefe877..4e2f864c`. Workspace
`../mlx-vlm` at `24551869`; read with `git show 79914344:<path>` (read-only). Diff `4e2f864c..79914344` inline below (red
then green). Production code unchanged since round 2 (`git diff 7207179b 79914344 -- mlx_vlm ':!mlx_vlm/tests'` must be empty —
verify). Context for K8: operator ruling C184 (2026-10-19) set NO default campaign wall limit; the operator-accepted P369
run plan v13 (C193, later) introduces an authorized wall cap per campaign = nominal projection + one reserved tail; C193's
ruling carries 20,400 s (13,140 s nominal from smoke 12b + 7,200 s).

First verify K7–K9 per id, then review the diff afresh. Only findings that must be fixed before the
`Qwen3.8-27B-mlx-uniform-4bit` TurboQuant full run (C193) or the codec ABBA (R5) should block.

Findings ids K10 onward, each: severity, file:line, problem, failure scenario, fix. End with exactly one line:
`VERDICT: CLEARED` or `VERDICT: NOT CLEARED <ids>`. OUTPUT RULE: your FINAL message must contain EVERY finding in full, then the
VERDICT line.
