# M54 — AgentBench OS (multi-step shell-tool agent axis)

Status 2026-09-30: **BUILD IN PROGRESS** (C107 ruled: own loop, mechanical exclusion, predictor OFF, round limit 8). Proposed after P2 (2026-09-30): the only axis the B ladder lacks is a multi-step tool loop with self-correction; BFCL is single-step, polyglot is edit-via-instruction, the SWE-bench probe never ran at scale.

## Corpus

- Source: `THUDM/AgentBench` `os-std` split, Apache-2.0: `data/os_interaction/data/{1..7}/*.json` + `scripts/{1..7}/`, 144 tasks (quanteval.ai scores 114 of them; their 30-item exclusion list is unpublished — we derive our own, see C107 D2).
- Task fields: `description`, `create.local` (image: `default|packages|ubuntu`), `create.init` (setup script), `start` (background process), `evaluation.match` (string, stripped) or `evaluation.check` (script list; gold answer produced by running `evaluation.example.code` in a fresh container), `labels`. <!-- allow-pii-pattern: upstream JSON field name, not a hostname -->
- Images built locally aarch64 from `res/dockerfiles/{default,packages,ubuntu}` as `local-os/<name>`; build sha recorded in the corpus manifest. Vendored as `benchmark/corpora/agentbench_os_v1.jsonl` with corpus sha.

## Protocol (upstream-faithful)

- Tools exactly as upstream `configs/tasks/os.yaml`: `bash_action(script)`, `finish_action(thought)`, `answer_action(answer)`; native function calling; upstream system prompt verbatim.
- `round_limit` 8 (upstream). A turn-cap exit is a scored FAIL with outcome `turn_cap`, never excluded.
- Each task: fresh container → `init` → `start` → loop → evaluate inside the same container → `docker rm -f`. One container at a time.
- Agent: `bench.agent_loop.run_agent` over the Driver; one persistent `bash --login` shell per task container (upstream-faithful; C107 amendment 2026-09-30): `start` and every `bash_action` go through it, 30 s per-command timeout ends the episode as upstream does; first tool call of a turn only; a tool-less turn gets the upstream re-prompt and continues; output clipped at 800 chars with the upstream wrapper; container `-w /root`, 1 GiB memory, swap off, 2 vCPU; loop guard off, repeats counted; outcomes labelled per `bench.agent_outcomes`.
- Transport/HTTP failures abort the run (nonzero exit, no row); docker setup/evaluate failures are labelled rows excluded from the `acc` denominator and reported as `setup_error`.
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

## Pre-registered acceptance criteria (cold review checks each)

- AC1 corpus: loader yields all 144 `os-std` tasks with upstream fields preserved; vendored data + scripts carry the upstream sha and Apache-2.0 notice; corpus sha in the manifest.
- AC2 exclusion (D2): before any model call, each task's `evaluation.example.code` runs twice in fresh containers with DIFFERENT placeholder answers; a task with no gold, an empty gold, or disagreeing golds is excluded (reason recorded); the list is a CORPUS artifact (`benchmark/corpora/agentbench_os_v1.exclusions.json`, keyed by corpus sha + image ids, `complete` only over the whole corpus) and generate refuses on mismatch or an incomplete list. Tasks with `match` evaluation are never excluded by this step.
- AC3 protocol: three upstream tools and the upstream system prompt verbatim; `round_limit` 8; `bash_action` runs `docker exec` with a per-command timeout; outcomes labelled via `bench.agent_outcomes`; `turn_cap`/`no_submit`/`deadline` are scored FAIL rows, never dropped.
- AC4 driver discipline: `provenance.assert_served_config` before the first request and `assert_served_config_unchanged` at exit (C106); manifest via `provenance.gather`; `--sampling-profile deployed` via `model_params.params_for`; seed `rowschema.sample_seed(item, 0)`; resumable (completed ids skipped); `--limit`; `--pilot-seed` draws a seeded random subset, never the first items; derived client timeout, retries 0; transport failures escalate.
- AC5 evaluation: `match` (stripped) and `check` scripts run inside the task container with the gold from the reference; row carries `passed`, `outcome`, `turns`, per-turn completion tokens, per-turn finish reasons and decode rate, convergence judged per turn with `tool_calls` treated as a terminal finish, `gold`, `labels`, `image`.
- AC6 tests: docker, driver and router mocked; no network, docker or model calls in the suite; failing-test-first visible in history.
- AC7 degrade: missing docker/images/corpus → `skipped: true` with note, exit 0, never a crash.
- AC8 hygiene: full registry model names, no PII, hooks pass; `benchmark/README.md` section; nothing written outside the repo except under `$STACK_WORKDIR`.
- AC9 cleanup: every container removed on success, failure, timeout and KeyboardInterrupt; one container at a time.
