Cold PLAN review — ROUND 1 OF 3 (at most 3 rounds, then the operator decides open findings; prioritise what must change
before implementation). P405: a production configuration defect in the fork `mlx-vlm` — the server ignores
`--kv-quant-scheme turboquant` and serves affine 4-bit KV. Workspace: the `mlx-vlm` fork checkout at `24551869`; the relevant
code is in this repository's object store at `p400-tq-width2` HEAD `78c9f99d` — read with `git show 78c9f99d:<path>`
(read-only; modify nothing). Key files: `mlx_vlm/server/runtime.py` (`ServerRuntime.config` default_factory),
`mlx_vlm/server/runtime_config.py` (`RuntimeConfig.from_env`, `_env_defaults`, `apply_changes`), `mlx_vlm/server/cli.py`
(`main`: the env writes ~743–811, `uvicorn.run`), `mlx_vlm/server/__init__.py`, `mlx_vlm/server/app.py` (~924–985: the
model-load path; ~1270–1300 `/v1/settings`), `mlx_vlm/server/generation.py` (`ResponseGenerator`, `get_configured_context_limit`),
`mlx_vlm/generate.py` / `mlx_vlm/models/cache.py` / `mlx_vlm/turboquant.py` (how the scheme selects the cache class).

The plan (inline below) records the operator's decision (fix so TurboQuant engages), the fix F1/F2, a knob audit, the
red-first tests T1–T5, and the rollout / re-measurement R1–R7.

Review adversarially: (1) is the mechanism right and is F1 complete — any other path where the import-time config, or any
other import-time env snapshot (module globals, caches, `lru_cache` getters), still wins over the CLI (e.g. other server
modules, the APC manager, `--reload`, router-launched workers, `/v1/settings` replace / fingerprint / reload)? Is the knob
audit table complete and correct? (2) Is F1 the best fix vs alternatives (blast radius, upstream divergence, ordering hazards:
anything reading `runtime.config` between import and `uvicorn.run`)? (3) Would T1–T5 be red today for the right reason, and do
they catch the defect class (a CLI flag silently not reaching the served state), not only this instance? (4) Is the rollout /
re-measurement scope right and sufficient: what TurboQuant engagement invalidates (memory, quality, MTP exactness, perf), the
PROVISIONAL handling, the P404 re-measurement design (both arms with P405), the evidence relabelling, and the unaffected
entry? (5) Anything missing.

Findings ids T1 onward, each: severity (BLOCKER / HIGH / MEDIUM / LOW), the problem, a concrete failure scenario, the change to
the plan. End with exactly one line: `VERDICT: AGREE` or `VERDICT: DISAGREE <ids of blocking findings>`.
OUTPUT RULE: your FINAL message must contain EVERY finding in full, then the VERDICT line.
