# M54 — AgentBench OS (multi-step shell-tool agent axis)

Status 2026-09-30: **QUEUED, build pending operator confirmation of C107 design choices.** Proposed after P2 (2026-09-30): the only axis the B ladder lacks is a multi-step tool loop with self-correction; BFCL is single-step, polyglot is edit-via-instruction, the SWE-bench probe never ran at scale.

## Corpus

- Source: `THUDM/AgentBench` `os-std` split, Apache-2.0: `data/os_interaction/data/{1..7}/*.json` + `scripts/{1..7}/`, 144 tasks (quanteval.ai scores 114 of them; their 30-item exclusion list is unpublished — we derive our own, see C107 D2).
- Task fields: `description`, `create.local` (image: `default|packages|ubuntu`), `create.init` (setup script), `start` (background process), `evaluation.match` (string, stripped) or `evaluation.check` (script list; gold answer produced by running `evaluation.example.code` in a fresh container), `labels`. <!-- allow-pii-pattern: upstream JSON field name, not a hostname -->
- Images built locally aarch64 from `res/dockerfiles/{default,packages,ubuntu}` as `local-os/<name>`; build sha recorded in the corpus manifest. Vendored as `benchmark/corpora/agentbench_os_v1.jsonl` with corpus sha.

## Protocol (upstream-faithful)

- Tools exactly as upstream `configs/tasks/os.yaml`: `bash_action(script)`, `finish_action(thought)`, `answer_action(answer)`; native function calling; upstream system prompt verbatim.
- `round_limit` 8 (upstream). A turn-cap exit is a scored FAIL with outcome `turn_cap`, never excluded.
- Each task: fresh container → `init` → `start` → loop → evaluate inside the same container → `docker rm -f`. One container at a time.
- Agent: `bench.agent_loop.run_agent` over the Driver; `bash_action` runs `docker exec` with a per-command timeout; outcomes labelled per `bench.agent_outcomes`.
- Grading inside the generate pass (the container must be live): row carries `passed`, `outcome`, `turns`, `completion_tokens` per turn, convergence vector, `labels`.

## Arms and reads

- Models: `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, `Qwen3.8-27B-mlx-uniform-4bit`; shortlist models only on operator request.
- `--sampling-profile deployed`, thinking ON, budget unchanged, predictor state per C107 D3. k=1, seeds `(item, 0)`.
- Pre-registered read: `acc_strict@budget` per model, paired difference with cluster-bootstrap CI, nominal MDE at n=144 ≈ ±10pp (paired, binary); exclusive-solve sets; per-label breakdown is DIAGNOSTIC only; tokens per task and wall per task reported beside. Outcome mix (`turn_cap`, `no_submit`, `tool_error_loop`, `deadline`) reported as counts.
- No ladder change without operator approval.

## Cost

- Seeded random 5-item pilot first (never the first items). Size from pilot MEAN and MAX; budget heavy tails (8 thinking turns × long reasoning). Rough prior: 2–5 min per task → 5–12 h per arm. Lower bound until the pilot.

## Deliverables

- `benchmark/bench/run_agentbench_os.py` (driver: M50/C106 guard, manifest, resumable rows, `--limit`, `--pilot-seed`), `bench/agentbench_adapter.py` (corpus load, container lifecycle, evaluation), `scripts/build_agentbench_images.sh`, tests mocked (no docker in CI), `benchmark/README.md` section.
