Cold PLAN review — ROUND 1 OF 3 (at most 3 rounds, then the operator decides open findings). The plan (inline below,
`docs/specs/p415-r7-qualification.md` in the STACK repo) adds a `qualify` subcommand to the fork's `dev/p400_perf_probe.py` (branch
`p369-v13`, HEAD `3ae8770e`; read with `git show 3ae8770e:<path>` in the workspace `../mlx-vlm`, read-only) for P405 plan v4 §5 R7
(its text inline below): the 256K operational qualification of the six P405-affected TurboQuant registry entries plus
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (native KV, the operator's primary pick). Relevant existing code to check the plan
against: `dev/p400_perf_probe.py` (`leg`, `served_check`, `drive_codec`, `codec_request_problems`), `dev/p369_phase2/orchestrate.py`
(`worker_argv`, `Monitor`, the process / power preflight), `dev/p369_phase2/kvmanifest.py`, `dev/p369_phase2/worker.py`
(`boot`, `size_prompt`, `served_state`, `assert_served`). The stack registry `main_models.yaml` is inline (the seven entries'
blocks).

Review adversarially: (1) can the run pass for the wrong reason (an entry not served as registered, the wrong codec, a prompt
shorter than claimed, a peak not covering the prefill, a self-referential expectation); (2) does it fail closed on every error
path, and do transport errors abort; (3) is the design consistent with AGENTS.md's measurement rules (capacity = `mx.get_peak_memory`
prefill spike on a quiet box, 48 GB = guidance; power; idle; monitor; no pytest during runs); (4) gaps in the tests; (5) scope or
estimate problems. Findings ids Q1 onward (or say none), each: severity, plan section, problem, failure scenario, fix. End with
exactly one line: `VERDICT: AGREE` or `VERDICT: DISAGREE <ids>`. OUTPUT RULE: your FINAL message must contain EVERY finding in
full, then the VERDICT line.
