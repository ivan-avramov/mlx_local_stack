Cold PLAN review — ROUND 1 OF 3 (at most 3 rounds, then the operator decides open findings). The plan (inline below,
`docs/specs/p426-fable-mtp-recert.md` in this STACK repo at commit `6d281f61`) re-certifies `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`
MTP-ON vs MTP-OFF through the real router before restoring its three C177 registry lines. Governing rules: `AGENTS.md`, rulings
C203 / C204 / C177 in `docs/open-questions.md` (C204: no strict thresholds — per-axis quality / memory / speed signals for an
operator judgement call), `docs/specs/p369-phase2-run-plan.md` §3.1 Restore and §6. Code to check the plan against (read-only):
`benchmark/run.py`, `benchmark/bench/generate.py` (row `draft`, `peak_mem_gb`), `benchmark/bench/compare_predictor.py`,
`benchmark/vision_gate.py`, `benchmark/bench/run_reasoning.py`, `benchmark/bench/run_capacity.py`, `benchmark/chains/c147/`
(`run_tg1_chain.py`, `chain_ops.py`, `chain_core.py`), `benchmark/m1/bench_watch.py`, `bench/run_judge_pairwise.py`,
`main_models.yaml`; the fork at `../mlx-vlm` commit `494aea2c` (`dev/p369_phase2/registry_states.py`,
`mlx_vlm/server/generation.py` `Request completed` line; read with `git -C ../mlx-vlm show 494aea2c:<path>`).

Review adversarially: (1) can a signal be wrong or misleading (arms differing in more than the predictor, a stale or
lifetime-high-water memory number, acceptance pooled wrongly, speed measured under different machine state, the ON overlay
not what would ship); (2) does every step fail closed, and do transport errors abort; (3) consistency with AGENTS.md
measurement rules (k=2 instances for agentic chains, paired seeds, power, idle, monitor, M50, deployed params, smoke first,
no pooling across builds); (4) whether each existing tool can actually run as written (flags, file names, refusals) and what
the plan misses in its builds B1–B6; (5) scope, ordering or estimate problems. Findings ids R1 onward (or say none), each:
severity, plan section, problem, failure scenario, fix. End with exactly one line: `VERDICT: AGREE` or `VERDICT: DISAGREE <ids>`.
OUTPUT RULE: your FINAL message must contain EVERY finding in full, then the VERDICT line.
