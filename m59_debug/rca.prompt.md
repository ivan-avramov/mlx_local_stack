# Cold second-eyes RCA: is opencode 2.0.20 making local models perform worse than opencode 1.18.15?

You are a skeptical reviewer. Read-only. Do not run opencode, do not contact localhost:8000, do not start or stop any server.
Write nothing outside $STACK_WORKDIR/m59_debug/codex_tmp (STACK_WORKDIR = ~/ws/mlx_local_stack_workdir). Use full model names.

## Question (from the operator)
"I'm reading the conclusion as v2 is not as good as v1 ... it sounds like v2 is causing the model to perform worse. Let's debug this."

## Data (all local)
- Repo ~/ws/mlx_local_stack. Read AGENTS.md (validity rules) and docs/open-questions.md C134–C139 for context.
- 1.18 baseline rows ("1.18 medium", k=1, unseeded, wall-clock 600 s stall gate, opencode 1.18.15, Sept 2026):
  benchmark/results/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-MED/opencode.jsonl (python),
  benchmark/results/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/opencode_go.medium.jsonl (go), and the same two for
  Qwen3.8-27B-mlx-uniform-4bit (-MED/opencode.jsonl, opencode_go.medium.jsonl). Manifests beside them.
- v2 rows (M59, opencode 2.0.20, k=2 sessions s1/s2, seeded, 16K-token first-write gate): benchmark/results/<model>/opencode_v2_{python,go}.m59.{s1,s2}.jsonl
  + manifests; stall re-runs at 48K tokens: *.stall48k.jsonl. Report: $STACK_WORKDIR/m59/M59_REPORT.md.
- v2 transcripts (session exports): paths in each v2 row's transcript_path ($STACK_WORKDIR prefix).
- 1.18 sessions: a COPY of opencode's sqlite DB at $STACK_WORKDIR/m59_debug/ocdb/opencode.db (open read-only, `file:...?mode=ro`).
  Tables session/message/part; 1.18 MED sessions are version '1.18.15' in the arms' time windows.
- Analysis scripts already written (check them for bugs): $STACK_WORKDIR/m59_debug/pair.py (pair.json output), firstwrite.py.
- Mock-server wire captures of the FIRST chat request of each version on python/paasio (no model involved):
  $STACK_WORKDIR/m59_debug/capture/out/{v118,v2}.requests.json, {v118,v2}.system.txt, {v118,v2}.tools.json; capture script
  capture/capture.py (the 1.18 capture replicates the Sept probe invocation: `opencode run --dir <tmp scratch> --pure`, the
  operator's then-personal v1 config, real-home instruction files copied into a fake HOME — check whether that replication is faithful
  by reading the Sept probe source: $STACK_WORKDIR/m59_debug/probe_878d720.py).
- Serving differences between the eras are in the manifests (git.serving_path, kv.kv_bits, runtime.*).

## Tasks
1. Independently reconcile: does the evidence support "v2 makes the models perform worse" — on accuracy (acc_strict@budget), on
   tokens/time, or neither? Separate gate effects, scaffold effects, serving-stack changes, seeding, and noise (k=1 baseline).
   Quantify with the data; say what is and is not distinguishable.
2. Rank candidate mechanisms for any real difference, each with the evidence for/against from the files above.
3. Adversarially verify or refute each of these claims from the lead investigator (cite numbers):
   C-a. Accuracy is not worse on v2: per-model scaffold deltas have opposite signs (Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed down,
        Qwen3.8-27B-mlx-uniform-4bit up) and pooled across both models v2 (with the 48K stall re-run conversions) ≥ 1.18.
   C-b. The 1.18 baseline is contaminated: its prompt carried the operator's personal ~/.claude/CLAUDE.md and ~/AGENTS.md
        (model output shows "P1 —" labels and "one tension to flag"), and the webfetch tool was enabled (one 1.18 session fetched
        exercism's .meta/example.go reference solution for go/matrix).
   C-c. The token increase on v2 is real (≈1.3–1.8x per solved item; first-write tokens ≈1.0–1.3x for the mixed model,
        ≈1.7–1.9x for the uniform model) and is mainly explained by the system prompt: 1.18's ~2K-token prompt demands minimal output
        ("fewer than 4 lines", "minimize output tokens", no summaries) while v2's ~900-token prompt does not; visible text
        is 2–3x longer on v2.
   C-d. Prior-turn reasoning is resent in the history by BOTH versions (next prompt grows by ≈ the previous output tokens), so
        reasoning-history handling is not the difference.
   C-e. Under a fixed first-write allowance, the extra pre-write thinking converts into stalls, which is what made v2 scores look worse.
4. Propose the cheapest decisive experiment(s) to attribute the remaining difference (prompt vs tools vs serving), with cost in box-hours
   (decode ≈24–25 tok/s; per-item time from the rows), and what result would change the conclusion. Point out anything we missed.

Output: ≤ 1000 words, findings first, each claim tagged VERIFIED / REFUTED / UNSUPPORTED with the evidence.
