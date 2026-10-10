# M41 tooling fix round 1 (from cold review; agent-facing; rules, not rationale)

Same rules as TOOLING.md (TDD, additive, no commits, only `benchmark/bench/**`). Keep the full suite green (the one
pre-existing docs failure excepted).

## F1 Per-rung / per-trial progress lines (review defect 1)
- `bench/capacity_ladder.py::run_ladder`: after each rung append, `print(f"[capacity] rung ctx={ctx} server_peak_gb={...} fits={...} prefill_s={...} error={...}", flush=True)`.
- `bench/retrieval.py::run_retrieval_ladder`: after EACH trial `print(f"[retrieval] ctx={ctx_len} trial={trial}/{samples} hits={sum(h)}/{n_dep} prefill_s={...} decode_tps={...}", flush=True)`; keep the existing per-rung print in `run_retrieval.py`.
- `bench/reasoning.py::run_reasoning_ladder`: after EACH draw `print(f"[reasoning] ctx={ctx} trial={trial} score={sc} completion_tokens={ct} budget_hit={hit} prefill_s={...}", flush=True)`.
  Tests: capture stdout (capsys) in the existing fake-driver tests and assert one line per trial/rung.

## F2 Capacity request timeout (defect 2)
- `run_capacity.py`: add `--request-timeout` (float, default 7200.0; help: "per-request HTTP timeout, DERIVED not SDK-default (O41): 262K prefill precedent ~2200 s, with headroom"); thread through `capacity_ladder.run_ladder(..., request_timeout=)` → `driver.complete(..., timeout=request_timeout)`. Test: timeout reaches the fake driver.
- The OOM/disconnect catch in `run_ladder` stays (capacity is the one ladder where an OOM is a legitimate non-fitting result) BUT the recorded row must carry `"error_kind"`: `"timeout"` when the exception is a timeout type (`socket.timeout`, `TimeoutError`, `requests.exceptions.Timeout`, `httpx.TimeoutException` — whichever the client raises; inspect `bench/client.py`), else `"oom_or_disconnect"`. Test both.

## F3 Retrieval transport failures ESCALATE (defect 3, O41)
- `bench/retrieval.py::run_retrieval_ladder`: remove the per-trial `except Exception` grading path. A driver exception propagates (mirror `bench/reasoning.py`'s comment). Remove the now-dead `errors` accumulation only if no other reader depends on the key — otherwise keep `errors: 0` in the record for schema stability. Update/replace the existing test that asserted the graded-zero path; add a test that a raising fake driver propagates.

## F4 Reasoning manifest overrides = CLI deltas only (defect 10)
- `run_reasoning.py`: pass `overrides={k: v for k, v in (("max_tokens", args.max_tokens), ("thinking_budget", args.thinking_budget), ("temperature", args.temp)) if v is not None}` instead of the full params dict. Test asserts the manifest's overrides for a run with `--temp 0.7` only.

## Acceptance
Full suite green; red-run evidence per F-item; `git status --short` shows only `benchmark/bench/**`.
