# M41 capacity + depth ladder chain

Spec: `SPEC.md`. Tooling spec (parallel worker, delivers the new bench CLI flags):
`TOOLING.md`. Pick: `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, predictor-ON
(registry `draft_kind: mtp`, M40-certified). Tune / out-tag for all three ladders:
`m41on`. Sampling profile: `deployed`. One router session for the whole chain — the
worker stays loaded across all three ladders.

## Launch

Detached, from a clean shell (the box must be idle: no router, no worker, no other
`run.py generate`/`bench.run_*` driver):

```
source "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
cd "$STACK_WORKDIR/queue/m41_ladders"
nohup "$STACK_REPO/.venv-bench/bin/python" run.py >/dev/null 2>&1 </dev/null &
```

Flags:
- `--dry-run` — print the full three-ladder command plan to **stdout and queue.log**,
  exit 0. Launches nothing for real: no router, no GPU work, no ladder subprocess. **R4
  (SPEC_FIX1) exception**: the per-ladder flag precheck (`check_cli_flags`) DOES run
  `<python> -m <module> --help` even under `--dry-run` — it needs no server and no GPU
  work, and FATALs naming the missing flag if `TOOLING.md`'s flags haven't landed yet.
  That `--help` subprocess is the only bench-module invocation `--dry-run` performs.
- `--from-step {capacity,retrieval,reasoning}` — resume from this ladder. Ladders
  *before* it are skipped **only if already complete** (both `<out>.m41on.json` and
  `<out>.m41on.provenance.json` exist for that ladder) — otherwise the runner FATALs
  rather than silently skip real, incomplete state. The ladder at `--from-step` itself,
  and every ladder after it, always (re)runs.

Order: capacity (gate) → retrieval depth → reasoning depth → unload → stop router.

## Restart recipe

`run.py --from-step <step>` is the restart recipe for every case below — a fresh
attempt, a resume after a completed prefix, or a resume after a mid-ladder FATAL
(TIMEOUT or rc≠0). See "Resuming" for what counts as complete and what reasoning does
differently.

## Resuming

`--from-step retrieval` (capacity already produced both its `.json` and
`.provenance.json`): retrieval and reasoning run. `--from-step reasoning`: only
reasoning runs. There is no per-ladder resume finer than this for capacity/retrieval —
a TIMEOUT or rc≠0 mid-ladder means that ladder is re-run from scratch.

**Reasoning is the one ladder with its own internal resume.** `bench.run_reasoning`
reads `reasoning.m41on.partial.jsonl` when given `--resume`. R7 (SPEC_FIX1): this
runner now decides `--resume` for you — `do_reasoning` checks whether
`reasoning.m41on.partial.jsonl` already exists on disk (regardless of whether you got
here via `--from-step reasoning` or a FATAL-then-restart of the same command) and, if
so, appends `--resume` to the reasoning command itself, logging `RESUME reasoning: ...
exists -- adding --resume to the reasoning command`. A first, clean attempt (no partial
file yet) runs without `--resume` as before. If the reasoning ladder FATALs mid-run, its
FATAL line still says it's resumable; the next `run.py --from-step reasoning` will pick
up the partial file automatically.

## Reading the log

**Where things land**: `helpers.py` here is the M40 helpers module with `OUT` edited to this directory, so
`queue.log`, per-tag `.log`/`.pid` files and the `m41_queue.lock`/`m41_queue.pid` pair are all under
`$STACK_WORKDIR/queue/m41_ladders/`. Benchmark outputs go to `$STACK_REPO/benchmark/results/<model>/`.

**Heartbeat fields** (R1, SPEC_FIX1) — every 5 minutes, for whichever ladder is currently
running, `queue.log` gets one `HEARTBEAT <tag>: ...` line with:
- `driver_log_bytes` — current size of `<tag>.log` (the driver's own stdout+stderr).
- `driver_log_age_s` — seconds since `<tag>.log`'s mtime; this is the actual "is it
  stuck" signal, not `driver_log_bytes` alone (a ladder can go quiet between rungs
  without being stuck).
- `progress` — the LAST line in `<tag>.log` containing that ladder's per-trial progress
  marker (`[capacity] rung ...`, `[retrieval] ctx=...`, or `[reasoning] ctx=...`, added
  by the TOOLING_FIX1 F1 change), or `none` if no such line has appeared yet.
- `worker_cmdline_present` — whether `pgrep -f mlx_vlm.server` currently resolves.
- `driver_alive` — whether the ladder subprocess is still running.

If `driver_log_age_s` exceeds 5400 s (90 min), the same heartbeat cycle also logs a
`WARN <tag>: no driver output for <n> s (a 262K prefill or a runaway may legitimately
take this long; check GPU util before acting)` line. **This WARN is informational only
— the runner never kills the driver on it**; only the ladder's own bound (2/5/10 h)
does that.

## Rerun hazards

- **Never change serving config mid-run.** The overlay is read once at startup and its
  sha logged; if the file on disk changes between ladders, the sha logged before each
  `RUN` line will differ from the startup line — treat that as a hard stop, not a
  resume point.
- **Re-running capacity after a GATE-FAIL**: `bench.run_capacity` is not idempotent
  across `--out-tag` — a second invocation at the same tag overwrites
  `capacity_retrieval.m41on.json` / `capacity_ladder.m41on.jsonl`. There is no
  `check_no_stale_archive`-style guard here (unlike M40's coding legs) because these
  three benches have no docker/archive side effect; overwriting is intentional and
  safe as long as the operator wants a fresh capacity read.
- **Retrieval has no `--resume`.** A TIMEOUT or rc≠0 mid-ladder means the entire
  retrieval ladder must be re-run from scratch (the FATAL line does not claim
  resumability for it, only for reasoning).
- **Reasoning's `--resume` is keyed on the full design** (grid, profile, samples,
  chain_len, threshold, and — for deep rungs — `deep_from`/`deep_samples`/
  `early_stop_budget_hits`; see `bench/run_reasoning.py::key_for`). Re-running with
  `--resume` after changing ANY of those (e.g. a different grid) will not reuse the old
  partial rungs — they simply won't match the new key and will be recomputed. R7
  (SPEC_FIX1): you no longer need to add `--resume` by hand — see "Resuming" above.
- **`--from-step`'s completion check only looks at file presence**, not content
  validity (e.g. `capacity_gate_pass`, `retrieval_effective_ctx` being sane). A
  corrupted or hand-edited `.json`/`.provenance.json` pair would satisfy `step_complete`
  and be skipped silently — if in doubt, delete the pair and re-run that ladder instead
  of trusting `--from-step`.
- **`draft_counters` is always `null`** in every provenance json (see `WARN` above) —
  this is expected, not a bug; it is not evidence of an OFF worker.
- **The `--help`-based flag precheck (`check_cli_flags`) runs on every invocation, dry
  or real** (R4, SPEC_FIX1), once per ladder, immediately before that ladder's `RUN`
  line (or, under `--dry-run`, before its `PLAN` line). If `TOOLING.md`'s flags haven't
  landed yet, the run FATALs naming the exact missing flag(s) and the module, e.g.
  `bench.run_retrieval --help is missing required flag(s) ['--request-timeout'] --
  tooling not ready yet (see TOOLING.md); refusing to launch retrieval` — this can now
  happen even under `--dry-run`.
- **A per-ladder manifest is asserted present after that ladder finishes** (R9,
  SPEC_FIX1): `capacity_ladder.m41on.manifest.json` / `retrieval.m41on.manifest.json` /
  `reasoning.m41on.manifest.json`. Its absence FATALs (`provenance manifest missing (C35
  tripwire or gather failure — rows are UNGRADED until provenance is established)`) —
  the ladder's rows exist but are not certified, so this stops the chain rather than
  writing this runner's own `.provenance.json` over an ungraded result.
- **Teardown honesty** (R3, SPEC_FIX1): `helpers.stop_router` only logs `router stopped;
  0 listeners; worker gone` when a final `pgrep` for `mlx_vlm.server`/`mlx_vlm/server`
  comes back empty. If the worker subprocess is still alive after the router stopped
  listening, it logs `WARN router stopped but worker STILL ALIVE pid=<pids> — kill by
  PID and verify` instead — **treat that WARN as an operator action item** (kill the pid
  by hand and confirm via `pgrep`), not as "teardown succeeded, worker will exit on its
  own." The FATAL cleanup path (`__main__`'s except block) and the SIGTERM/SIGINT
  handler (R8) both attempt `h.unload()` before `h.stop_router()`, same order as the
  normal-path `router_stop()`.

## Known ambiguities / assumptions resolved

- **`helpers.py` `OUT`** was edited (one line) from the M40 copy to point at `queue/m41_ladders`, so all
  runner bookkeeping lands in this directory. Benchmark result files are built from absolute paths under
  `$STACK_REPO/benchmark/results/`.
- **Exact JSON field names for the three ladder outputs** were not fully pinned down by
  SPEC.md/TOOLING.md's log-line templates alone, so they were verified against the
  current source (`bench/capacity_ladder.py`, `bench/scorecard.py::capacity_retrieval_scorecard`,
  `bench/retrieval.py::run_retrieval_ladder`, `bench/reasoning.py::run_reasoning_ladder`,
  `bench/run_capacity.py`/`run_retrieval.py`/`run_reasoning.py`) before writing the
  `RESULT`-line parsers: `capacity_retrieval.<tag>.json` has top-level `max_fitting_ctx`,
  `capacity_gate_pass`, `records` (each with `ctx`, `server_peak_gb`, `fits`, `prefill_s`,
  `decode_tps`, `error_kind`/`error` per TOOLING_FIX1 F2, plus `acceptance`/`draft` once
  TOOLING.md T2 lands); `retrieval.<tag>.json`
  has `retrieval_effective_ctx`, `records` (each with `ctx`, `accuracy`, `errors`, plus
  `decode_tps_mean`/`prefill_s_mean`/`acceptance_pooled` once T1 lands); `reasoning.<tag>.json`
  has `reasoning_effective_ctx`, `records` (each with `ctx`, `accuracy`, `budget_hits`,
  `samples`, `rows` (each with `budget_hit`/`completion_tokens`), plus
  `decode_tps_mean`/`prefill_s_mean`/`acceptance_pooled` once T3 lands). All field reads
  use `.get()` defensively since the additive T1/T2/T3 keys are not live yet.
- **`--from-step`'s "complete" test**: SPEC.md §4 says a ladder "counts as complete only
  if its `<out>.m41on.json` AND `.provenance.json` exist" but doesn't say what happens
  if `--from-step` names a ladder whose *predecessors* are missing those files. Resolved
  conservatively: FATAL naming the missing file(s), rather than silently skipping
  (real) incomplete state — consistent with this campaign's general bias toward FATAL
  over silent data loss (see M40's D6b/D16 precedents).
- **capacity's "log idle_precheck + system-used GB" line (SPEC.md §2.1)**: the general
  `idle_precheck()` already runs once at startup for the whole chain (SPEC.md §4); read
  the capacity-specific mention as "also log a quiet-box system-used-GB record right
  before capacity launches" rather than a second idle-driver/worker/router check.
  Implemented via `bench.instrument.system_used_gb()` (the same helper
  `bench.run_capacity` itself uses for its own idle baseline), invoked through a
  one-line `python -c` subprocess rather than re-implemented from `vm_stat`.
- **The three required-flags-per-module lists** (`check_cli_flags`/`CLI_FLAGS` in
  `run.py`) were scoped to exactly the new flags TOOLING.md assigns to each module
  (`run_capacity`: `--sampling-profile`, `--out-tag`; `run_retrieval`: those two plus
  `--request-timeout`) rather than re-verifying every pre-existing flag. `run_reasoning`
  is checked too (`--sampling-profile`, `--out-tag`, `--request-timeout`, `--deep-from`,
  `--deep-samples`) even though TOOLING.md says its `--request-timeout` "already
  exists" (verified true by reading `bench/run_reasoning.py` directly) — the
  "before launching each ladder" rule in the task instructions is unconditional across
  all three ladders, so reasoning gets the same precheck for consistency and defense in
  depth.
