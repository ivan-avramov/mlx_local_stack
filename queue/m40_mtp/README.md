# M40 MTP-ON certification chain

Spec: `SPEC.md`. Picks: A = `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, B = `Qwen3.8-27B-mlx-uniform-4bit`. A runs to completion, then B.

## Arm

```
source "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
cd "$STACK_WORKDIR/queue/m40_mtp"
nohup "$STACK_REPO/.venv-bench/bin/python" run.py >/dev/null 2>&1 </dev/null &
```

Preconditions checked at start (FATAL otherwise, run for real even under `--dry-run` — all read-only):
no `run.py generate`, no `mlx_vlm.server`, 0 listeners on :8000; `docker info` succeeds and
`docker image inspect mlx-evalplus-native:recovery` succeeds (the box runs OrbStack, not Docker
Desktop — `orb start` if down). The docker check exists because the pick-B coding legs (steps 5/7)
grade through `resolution/native_grade.py`, which needs both; better to FATAL in the first second
than after hours of generation.

Flags:
- `--dry-run` — build+assert both picks' overlays, print the full command plan to **stdout and
  `queue.log`**, exit 0. Launches nothing (no router, no GPU work). Ignores `--pick` (acceptance
  requires overlays+plan for BOTH picks).
- `--pick A|B` — restrict a real run to one pick (reruns).
- `--from-step N` — resume a pick from step N (1..7, §3 of the spec); earlier steps log `SKIP`.

## Steps per pick (§3 + cold-review NEW)

1. math500 ON (100 ids from `resolution/ids.json`, pilot 5 → full). OFF pair = existing `math500.m37med` (not regenerated).
2. cjudge ON (40, pilot 5 → full, no explicit ids — matches m38). OFF pair = existing `cjudge.m38` (not regenerated).
3. vision_gate ON (`benchmark/vision_gate.py`, 20-item corpus, bound 2h). OFF pair = **step 6b** (NEW, see below), not the old `vision_gate.v1` (no recorded predictor state).
4. reasoning depth 128K ON (`bench.run_reasoning`, `--out-tag m40on-d128k`, bound 8h).
5. **pick B only**: humanevalplus + mbppplus ON (100 ids each, pilot 5 → full; native ARM64 grading via `resolution/native_grade.py`, per C58 — no matched OFF row exists at the deployed medium tune).
6. reasoning depth 128K OFF (`--out-tag m40off-d128k`, bound 8h).
6b. **NEW (cold review), both picks**: vision_gate OFF on the OFF overlay → `vision_gate.m40off.jsonl` + `vision_gate.m40off.provenance.json`. Bundled with step 6 (same `--from-step` threshold): the existing `vision_gate.v1` rows have no recorded predictor state, so they were never a real OFF pair for step 3's ON run.
7. **pick B only**: humanevalplus + mbppplus OFF, same recipe as step 5.

Router: one `ensure_router(on_<pick>.yaml)` before steps 1-5, `unload()`+`stop_router()` after; one `ensure_router(off_<pick>.yaml)` before steps 6/6b/7, `unload()`+`stop_router()` after. The runner only calls `stop_router()` in its top-level FATAL handler if **it** actually started the router (module flag, set in `router_start()`/cleared in `router_stop()`) — a lock or precheck failure, which happen before any router is touched, never kills a router this process doesn't own.

## Reading `queue.log`

Same line vocabulary as `queue/m38_cjudge/helpers.py` (this dir's `helpers.py` is a copy — diff below).
Under `--dry-run` every line below also prints to stdout (D13), not just `queue.log`.
- `PRECHECK ...` — the docker/OrbStack checks at start (idle precheck extension, coordinator addendum).
- `RUN <tag>: <cmd>` — a generation about to launch (or, under `--dry-run`, the `--dry-run`'d command).
- `overlay <name> sha256=<sha>` — logged every time an overlay is used (build + each `run_generate` call).
- `C35 check <model> <tag>: ...` — provenance fingerprint check (draft_kind/registry sha/temperature) against the live manifest.
- `worker cmdline: draft=<bool> ...` — `--draft-kind` presence check against `expect_draft`. For vision_gate/depth this is preceded by a "worker not yet loaded; forcing via POST /v1/models/load" line if the router hadn't lazily loaded the worker yet (D3 — an empty cmdline read is never treated as "no draft flags").
- `END <tag> rc=<rc>` — a subprocess finished.
- `SUMMARY <tag>: {...}` — row count/errors/convergence for a just-finished generation leg.
- `PILOT projected lower-bound seconds=<mean*N> max=<max>` — after every 5-item pilot, followed by `WARN pilot projects <x> h vs bound <y> h` if the projection exceeds 60% of that leg's `bound_h` (FATAL instead if it exceeds 100% — D8).
- `SCORE <tag>: acc=... acc_strict=... n=... conv=... errors=...` — emitted by `helpers.grade()` (math500/cjudge legs only; coding legs go through `resolution/native_grade.py` instead and do not emit this line). `grade()` now raises (StageFail) on a non-zero grading rc instead of silently falling through (D7).
- `RESULT <model> <bench> <tune> {...}` — a completed, validated grade.
- `HEARTBEAT <tag>: ...` — 5-min liveness line for vision_gate (if `bench_watch` rejects the tune label) and for the two depth-128K legs (`bench_watch` is not used for depth at all — see spec §3.4).
- `WARN <tag>: no reachable draft/speculative-decode counter ...` — logged once per vision_gate/depth arm (D11): neither mlx-serve's `/metrics` nor mlx_vlm's per-worker `/metrics` gives this runner a reachable cumulative draft-acceptance counter (see `draft_counter_probe()`'s docstring for what was actually checked); those arms' provenance json carries `"draft_counters": null` and certification rests on the `--draft-kind` cmdline check alone.
- `PLAN <tag>: ...` — `--dry-run` only: what would have launched.
- `=== M40 <pick> DONE ===`, `=== M40 MTP QUEUE DONE ===` — completion markers.
- `FATAL <repr>` + traceback — any exception. The router is stopped before re-raising **only if this process actually started it** (D2) — never on a `flock`/idle-precheck failure.

`queue.lock` (flock) + `queue.pid` guard against a second concurrent invocation, as in `m38_cjudge`. Every subprocess this runner launches (`run.py generate`, `bench_watch`, `vision_gate.py`, `bench.run_reasoning`, `run.py grade`, `native_grade.py`) writes a `<tag>.pid` file in this directory (D12).

### Re-running a coding grade (pick B, steps 5/7)

`resolution/native_grade.py` does `archive.mkdir(parents=True, exist_ok=False)` — a second grade
attempt for the same `(model, bench, tune)` crashes with a raw `FileExistsError` instead of a clean
message. `run.py` detects this up front (`check_no_stale_archive`, D6b) and FATALs with the fix:
delete `queue/resolution/native_grade_archive/<model>/<bench>.<tune>/` first, then re-run.

## `helpers.py` diff vs `queue/m38_cjudge/helpers.py`

- `OUT` points at this directory instead of `m38_cjudge`.
- `OFF_OVERLAY` constant removed: M40 has two overlays per pick (`on_<pick>.yaml`, `off_<pick>.yaml`), built and asserted in `run.py`, not one fixed native overlay.
- `run_generate(...)` gained a `dry_run=False` parameter: when true, it still logs the `RUN`/`overlay sha256` lines (so the plan output is byte-identical to what a real run would log) and returns `0` immediately instead of `Popen`-ing the driver/watcher.
- `grade(model, bench, tune, tag, overlay)` gained an explicit `overlay` parameter (was hardcoded to the removed `OFF_OVERLAY`) — needed because M40 grades ON arms against `on_<pick>.yaml` and OFF arms against `off_<pick>.yaml`.
- `make_overlay()` (unused dead code in the m38 copy too — grep confirms neither `m38_cjudge/run.py` nor `resolution/run.py` call it) removed: it hard-referenced the now-gone `OFF_OVERLAY` global, so keeping it would leave a broken, uncallable stub.
- Cold review: `sh()` now defaults `stdin=subprocess.DEVNULL` (D12); `log()` also prints to stdout when `ECHO_STDOUT` is set (D13, set by `run.py --dry-run`); `run_generate`'s `bench_watch` call uses `--driver-pattern '[r]un.py generate'` instead of the self-matching `'run.py generate'` (D14); every `.kill()` is followed by `.wait()` (D15); `grade()` is rewritten from a blocking `sh()` call to an explicit `Popen` so it can write a `<tag>.pid` file and `fail()` (raise `StageFail`) on a non-zero grading rc instead of silently continuing (D7/D12).

## Cold review fixes (file:line as of this delivery; re-check after any further edit)

| id | fix | where |
|---|---|---|
| D1 | `native_grade.py` launched with `PYTHONPATH=$STACK_REPO/benchmark` (it has no self sys.path insertion, unlike `run.py`/`vision_gate.py`; verified `ModuleNotFoundError: bench` under `env -i` without it) | `run.py:235` (env dict in `arm_ids`) |
| D2 | `_router_owned` module flag; FATAL handler only calls `h.stop_router()` if this process started it | `run.py:35` (flag), `run.py:446` (set True), `run.py:456` (cleared), `run.py:595-603` (guarded cleanup) |
| D3 | `worker_cmdline_for_check()` forces a load via `POST /v1/models/load` before trusting an empty cmdline read as "no draft flags"; FATAL if still empty after the forced load | `run.py:165-183` (def), `run.py:305`/`392` (call sites, vision/depth) |
| D4 | vision_gate arm bounded (was a bare `d.wait()`), same poll+bound loop as depth, bound 2h | `run.py:339-354` |
| D5 | depth bound 4h → 8h (`3 * 9600s request-timeout` headroom) | `run.py:27` (`BOUND_H['depth']`) |
| D6a | `vision_gate.py` gets `--resume` when its out-file already has rows | `run.py:292-295` |
| D6b | `check_no_stale_archive()` FATALs before a coding re-grade if `native_grade_archive/<model>/<bench>.<tune>/` already exists, naming the `rm -rf` fix | `run.py:130-138` (def), `run.py:192` (call site) |
| D7 | `helpers.grade()` raises (`fail()`/`StageFail`) on a non-zero grading rc instead of silently falling through | `helpers.py:191-192` |
| D8 | `check_pilot_projection()`: WARN at 60% of `bound_h`, FATAL over 100% | `run.py:115-126` (def), `run.py:217`/`271` (call sites) |
| D11 | `draft_counter_probe()` — verified no reachable cumulative draft counter exists (mlx-serve `/metrics` has no draft field; mlx_vlm's per-worker `/metrics` needs a management API key and isn't proxied through :8000); returns `None`, callers log a WARN and record `"draft_counters": null` | `run.py:142-155` (def + rationale), `run.py:310`/`361`/`397`/`427` (before/after calls) |
| NEW | vision_gate OFF arm, step 6b, both picks | `run.py:289` (docstring marker), `run.py:502-504` (call site in `run_pick`) |
| D12 | `sh()` defaults `stdin=DEVNULL`; every grade subprocess (`helpers.grade()`, `native_grade.py` launch) now writes a `<tag>.pid` file | `helpers.py:14` (sh), `helpers.py:181-192` (grade), `run.py:236-238` (native_grade Popen) |
| D13 | `--dry-run` prints the plan to stdout as well as `queue.log` (`h.ECHO_STDOUT = True`) | `helpers.py:6-11` (`log()`), `run.py:562` (set) |
| D14 | `bench_watch --driver-pattern` uses the `[x]` self-match-breaking form in both call sites | `helpers.py:125` (`'[r]un.py generate'`), `run.py:322` (`'[v]ision_gate.py'`) |
| D15 | every `.kill()` followed by `.wait()` (driver and watcher) | `helpers.py:144-166`; `run.py:330`, `run.py:347`, `run.py:354`, `run.py:417` |
| D16 | load-bearing bare `assert`s replaced with explicit `if not ...: h.fail(...)` | `run.py:43-55` (`assert_pick_defaults`), `run.py:93` (`build_overlays`), `run.py:108,110` (`load_ids`), `run.py:197` (`arm_ids` existing-rows check) |
| — | docker/OrbStack precheck (coordinator addendum): `docker info` + `docker image inspect mlx-evalplus-native:recovery`, FATAL before any GPU work, run for real under `--dry-run` too | `run.py:519-534` (`docker_precheck`), `run.py:543` (call site in `idle_precheck`) |

Nit not applicable: none skipped. All D-items plus the docker addendum are implemented above.

## Known ambiguities / assumptions resolved (see also the delivery report)

- Spec §3.4/§3.6 literally invoke `benchmark/bench/run_reasoning.py` as a script; that script uses
  a relative import (`from .driver import ...`) and fails immediately with
  `ImportError: attempted relative import with no known parent package` when run that way (verified
  empirically). `run.py` invokes it as `-m bench.run_reasoning` instead (cwd `$STACK_REPO/benchmark`),
  matching the module's own docstring.
- Coding-grade recipe (§3 step 5/7) replicates `resolution/run.py`'s `arm()` exactly: one subprocess
  call to `resolution/native_grade.py <model> <bench> <tune>` (which internally calls `run.py grade`
  to produce the `.score.json`) — not a separate `run.py grade` call. This means those two legs write
  their `*_native_diff.json` / archive artifacts into `queue/resolution/`, not `queue/m40_mtp/`; that
  is the existing, shared, standing coding-grade path (C58), not an M40-private copy.
- Invariant "Exceptions → FATAL + traceback, router stopped, non-zero exit" is enforced in
  `run.py`'s `__main__` guard (calls `h.stop_router()` in the `except` block before re-raising) —
  stricter than `m38_cjudge`/`resolution`'s `run.py`, which only log-and-reraise without stopping
  the router.
- `--pick`/`--from-step` semantics (not specified beyond "optional filter"/"optional resume"):
  `--pick` restricts real runs to one pick; under `--dry-run` both picks are always planned
  regardless of `--pick` (acceptance explicitly requires "2 overlays × 2 picks"). `--from-step N`
  applies per pick (steps renumber 1-7 for each pick); steps below N are logged as `SKIP` rather
  than silently omitted.
- `vision_gate.py` has no `--sampling-profile` flag (its profile is hardcoded to `"deployed"`
  internally) — the acceptance criterion "every launched command carries `--sampling-profile
  deployed`" is satisfied for the `run.py generate` and `bench.run_reasoning` legs; the vision_gate
  leg's `RUN` log line notes this explicitly instead.

## Analysis pre-registration (F4)
`bench/compare.py` refuses across `draft_kind` by design; NO M40 ON-vs-OFF pairing goes through it. The verdict tool is
`benchmark/bench/compare_predictor.py` (committed 9450670): `python -m bench.compare_predictor --model <pick> --bench <bench>
--tune-a <off-tune> --tune-b m40on` (pairs: math500 m37med/m40on, humanevalplus+mbppplus m40off/m40on for pick B, cjudge via
`run_judge_pairwise --pair-tunes m38 m40on`, vision m40off/m40on by pass counts + provenance jsons, depth m40off-d128k/m40on-d128k).
