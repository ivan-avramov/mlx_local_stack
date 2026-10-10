# M41 tooling spec — ladder tools carry the deployed profile, tags, timeouts, per-draw perf (agent-facing; rules, not rationale)

Repo: `$STACK_REPO` (`benchmark/bench/`). Venv: `$STACK_REPO/.venv-bench/bin/python`. Run tests with
`cd $STACK_REPO/benchmark && ../.venv-bench/bin/python -m pytest bench/tests -q -k "retrieval or capacity or reasoning"`.
TDD: write/extend the failing test first, run it, watch it fail, then the minimal change. Do NOT commit. Do NOT touch
`main_models.yaml`, `src/*`, or any file outside `benchmark/bench/` + `benchmark/bench/tests/`. Keep every existing
test green. Additive changes only: no existing output field renamed or removed; no existing default behaviour changed
except where stated.

## T1 `bench/run_retrieval.py`
1. Add `--sampling-profile` (REQUIRED; `choices=` from `model_params.profile_names()`; help text as in
   `run_reasoning.py`). Pass it as `params_for(args.model, profile=args.sampling_profile)`.
2. Add `--out-tag` (default None): write `retrieval.<tag>.json` instead of `retrieval.json` when given.
3. Add `--request-timeout` (float, default 9600.0, same help text as `run_reasoning.py`) and thread it to
   `run_retrieval_ladder(..., request_timeout=...)` → `driver.complete(model, messages, params, timeout=request_timeout)`.
4. In `bench/retrieval.py::run_retrieval_ladder` add a per-trial `rows` list to each rung record (additive key
   `"rows"`), one dict per trial: `{"trial", "seed", "hits": [bool per depth], "prompt_tokens", "completion_tokens",
   "finish_reason", "prefill_s", "prefill_tps", "decode_tps", "wall_s", "draft": {draft_kind, draft_rounds,
   draft_n, draft_n_accepted} or None, "error": str|None}`. `draft` comes from `result["raw_timings"]` (keys as
   named; missing → None). On the exception path the row has `"error"` set and the perf fields None.
5. Add a rung-level `"decode_tps_mean"`, `"prefill_s_mean"`, `"acceptance_pooled"` (sum draft_n_accepted / sum
   draft_n over rows with counters, else None) — additive keys.
6. Write a provenance manifest next to the output (`retrieval.<tag>.manifest.json` / `retrieval.manifest.json`)
   exactly the way `run_capacity.py` does (`provenance.gather(model, profile=<the chosen profile>, overrides=..., runtime={"probe": "retrieval", "grid": [...], "samples": n})`), best-effort (never lose a finished ladder to provenance).
   Tests: mirror `tests/test_run_reasoning_profile.py` (profile required → exit 2; profile reaches `params_for`;
   `--request-timeout` reaches `driver.complete`; `--out-tag` changes the filename; rows carry `prefill_s` and
   `draft` from a fake driver whose `complete` returns `raw_timings` with the four draft keys).

## T2 `bench/run_capacity.py`
1. Add `--sampling-profile` (REQUIRED, same choices/help). `params = {**params_for(args.model, profile=args.sampling_profile), "max_tokens": 256, "thinking_budget": 256}`.
   The provenance `gather(...)` call uses the chosen profile (today it hard-codes `"production"`).
2. Add `--out-tag`: `capacity_retrieval.<tag>.json`, `capacity_ladder.<tag>.jsonl`, `capacity_ladder.<tag>.manifest.json`.
3. Add a per-rung `"draft"` dict (same four keys from `out["raw_timings"]`) and `"acceptance"` (accepted/n or None)
   to each record in `capacity_ladder.run_ladder` (additive; `PerfRecord` untouched — add the keys to the row dict).
   Tests: extend `tests/test_run_capacity.py` / `tests/test_capacity_ladder.py` (profile required; profile reaches
   `params_for`; tag changes filenames; draft dict present when the fake driver returns raw_timings).

## T3 `bench/reasoning.py` + `bench/run_reasoning.py`
1. Per-draw rows gain additive keys: `"prompt_tokens"`, `"prefill_s"`, `"prefill_tps"`, `"draft"` (four-key dict or
   None) — from the same `result` already in hand. Rung records gain `"decode_tps_mean"`, `"prefill_s_mean"`,
   `"acceptance_pooled"` (as in T1.5). The persistence key (`--resume` matching) MUST NOT change (the new fields are
   values, not key inputs). Tests: extend `tests/test_run_reasoning.py` (FakeDriver returns `raw_timings` with the
   draft keys and `prefill_s`; assert they land in `records[0]["rows"][0]` and the rung means) and keep
   `test_reasoning_persistence.py` green unchanged.
2. `run_reasoning.py` writes a provenance manifest `reasoning.<tag>.manifest.json` the same way as T1.6
   (`runtime={"probe": "reasoning", "grid": [...], "samples": n, "chain_len": k}`), best-effort.

## T4 `tests/test_run_cli_help.py`
Add the two new modules' `--help` to whatever pattern that file uses (they must import and print help without a
server).

## Acceptance (the reviewer checks these)
- `pytest bench/tests -q` fully green; new tests fail before the change (show the red run in the report).
- `python -m bench.run_retrieval --help`, `--model M --no-preload` (no profile) → exit code 2 for both new CLIs.
- No file outside `benchmark/bench/**` modified (`git status --short` in the report).
- Report: list of files changed, test counts before/after, the exact new CLI flags.
