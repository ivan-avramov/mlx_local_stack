Cold adversarial review of ONE uncommitted change in this repository (working tree of the main checkout). You have no prior context; everything you need is below. Read-only: do not modify, stage, commit or revert anything. CPU only. A live model server owns localhost:8000 — never send it a request, never start or stop servers or docker containers. Do not read other review files or logs you may find on disk; form your own view from the code.

## The change (decision C125 item 1)
`benchmark/bench/run_agentbench_os.py` drives the AgentBench OS shell-agent benchmark. Until now every item was seeded with `rowschema.sample_seed(task["id"], 0)` — seed base 0 always — so two "independent" sessions of a chain replayed the identical seed schedule. Project rule (AGENTS.md, "Benchmark validity"): agentic chains run k=2 independent loaded instances with DISTINCT paired seed schedules plus a same-seed reload control; accuracy is paired per session.

Intended behaviour of the change:
1. New `--seed-base` (int, no default), required in generate mode, not for `--prepare` / `--migrate-exclusions`. Missing or negative → exit 2 before any router check, HTTP request, docker call or file write.
2. Item seed = `rowschema.sample_seed(task["id"], 0, base=seed_base)`; base 0 must reproduce the pre-change seeds exactly.
3. Manifest `runtime.seed_base`; every new row carries `seed_base` and `sampler_seed`.
4. `seed_base` joins `RESUME_IDENTITY_KEYS`: a resume with a different base is refused; a manifest lacking the key (all pre-change manifests) cannot be resumed ("new rows only", deliberate).
5. `benchmark/bench/agentbench_compare.py`: arms must agree on the effective seed base; a manifest without `runtime.seed_base` counts as 0.
6. Usage docs updated (`benchmark/README.md`, `docs/specs/m54-agentbench-os.md`, module docstring).

The diff is the working-tree diff of exactly these files: `benchmark/bench/run_agentbench_os.py`, `benchmark/bench/agentbench_compare.py`, `benchmark/bench/tests/test_run_agentbench_os.py`, `benchmark/bench/tests/test_agentbench_compare.py`, `benchmark/README.md`, `docs/specs/m54-agentbench-os.md` (`git diff -- <those paths>`). Other modified files in the tree (`benchmark/bench/session_cache_probe.py`, its test, `scripts/session_pinning_gate.py`, `docs/proposal-transport-abort.md`) belong to unrelated work in progress — ignore them.

## What to establish (answer each; say VERIFIED-BY-RUNNING, VERIFIED-BY-READING or ASSUMPTION)
1. Does the seed that reaches the model request really change with the base on EVERY turn of an item, or only on the first? Trace `item_params["seed"]` through `AB.run_task` → the agent loop → the driver's request body (`benchmark/bench/agentbench_adapter.py`, `bench/agent_loop.py`, the driver module). Is any later turn, retry, no-tool-call reprompt or gold-preparation call unseeded or seeded independently of the base?
2. Any path that generates rows without the flag or with an unrecorded base: `--resume`, existing rows without `--resume`, `--limit`, `--pilot-seed`, the pilot-twice / rate-derivation helpers, `agentbench_live_smoke.py`, `agentbench_watch.py`, any other caller of `run_generate`/`main` in the repo (`grep -rn run_agentbench_os`).
3. Resume identity: can a continuation mix two bases in one row file by any route (manifest missing, manifest unreadable, `done_ids` empty but rows present, a manifest whose `runtime.seed_base` is null)? Is refusing every pre-change manifest consistent with how the other identity keys behave?
4. Compare gate: is "missing counts as 0" sound given how pre-change rows were seeded? Can two arms with different bases be compared or pooled by any other tool that reads these rows (`bench/agentbench_compare.py` pooled/descriptive paths, `m1/scoreboard.py`, `bench/compare.py`, anything computing the per-session pairing)? Does the gate treat `seed_base: null` and `seed_base: "0"` (string) sensibly?
5. Ordering: is the refusal truly before anything is read from or written to disk and before the M50 router check? What does `--prepare` do with a supplied `--seed-base`?
6. Test quality: for each new test (names contain `C125`), would it still pass if the implementation were subtly wrong? Name at least two concrete mutations of the implementation (e.g. base ignored in the request but recorded in the row; row records the wrong seed; resume key present in the tuple but not written to the manifest) and state, by actually applying each mutation in a scratch COPY of the two source files outside the repo tree or by reasoning from the test code, whether a test catches it. A known positive you actually ran is worth more than any amount of reading.
7. Anything in the docs changes that is wrong or contradicts the code.
8. Anything else that would let a row be attributed to the wrong seed schedule.

Running tests is allowed and encouraged: `cd benchmark && ../.venv-bench/bin/python -m pytest bench/tests/test_run_agentbench_os.py bench/tests/test_agentbench_compare.py -q` (mocked; ~60 s; set TMPDIR to a writable directory you are given if the default is not writable; never interrupt a pytest run mid-flight — some tests use real ptys).

## Output
Verdict: BLOCKING / SHIP-WITH-RESIDUALS / SHIP. Then findings F1, F2, … each with severity (blocking / should-fix / note), `path:line`, the concrete failure scenario (inputs → wrong outcome), the minimal fix, and the evidence label. Then the list of checks you actually ran with their output lines. Terse; no praise; no restating of this prompt.
