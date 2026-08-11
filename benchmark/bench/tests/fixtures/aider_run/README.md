# Fixture: an aider polyglot benchmark run directory

Layout and field names are TRANSCRIBED FROM AIDER'S SOURCE, not guessed:
`benchmark/benchmark.py` in Aider-AI/aider (checked at tag `v0.86.2` — the version installed on
this box — and at `main`; the per-case `results = dict(...)` block and `summarize_results()` are
byte-identical between the two).

* run dir      `<AIDER_BENCHMARK_DIR>/<YYYY-MM-DD-HH-MM-SS>--<run_name>`  (`resolve_dirname`)
* per case     `<run_dir>/<lang>/exercises/practice/<exercise>/.aider.results.json`
               (`load_results` globs exactly `*/exercises/practice/*/.aider.results.json`)

The five cases deliberately cover the shapes that broke real campaign runs:

| case | shape | why it is here |
|---|---|---|
| `python/.../anagram` | `tests_outcomes: [true]` | passes on try 1 → counts for pass_rate_1 AND pass_rate_2 |
| `python/.../bowling` | `tests_outcomes: [false, true]` | pass_rate_2 only — the semantics a naive "any(outcomes)" gets wrong |
| `rust/.../clock` | `[false, false]` + `test_timeouts: 1` | a genuine failure with a test timeout |
| `rust/.../grep` | `[false, false]` + `num_exhausted_context_windows: 2`, huge `completion_tokens` | the 2026-07-06 gemma-4-26B-A4B-it-OptiQ-4bit contamination: input ~2,283 of 98,304 was FINE; the OUTPUT budget was consumed by thinking. Aider's counter name says "context window" and MISLEADS. |
| `go/.../two-fer` | `{"exception": ...}` only | aider writes this shape when a case crashes (`benchmark.py:675-676`) — it still counts toward `completed_tests`, so it must land in the denominator without crashing the parser |

No real model/host/user identifiers appear here (repo is public): the model name is a served
registry name, and `testdir` uses the container-side `/benchmarks/...` path the docker runner mounts.
