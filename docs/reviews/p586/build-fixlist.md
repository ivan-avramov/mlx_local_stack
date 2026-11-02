# Fix round 1 — the adopted findings (and nothing else)

Each red-first: a failing test first (in `benchmark/bench/tests/test_p586_fix_*.py`), then the minimal fix.

X1 (sol-1, blocker; adapted) — condition (b)'s close gap must not come from local log stamps: a pause of ≥ 1 h that spans the DST
fall-back reads as `true − 3600` s (e.g. telemetry at 01:59:59 PDT, close at 02:00:21 PST = 3622 s real, 22 s naive) and is accepted.
Change: `close_gap_s = wall_s − last.elapsed_s`, where `wall_s` = the aborted (or, completed variant, trailing) assistant message's
`(time.completed − time.created) / 1000` from the export (UTC epoch ms, client side) and `last.elapsed_s` = the last telemetry line's
`elapsed` (the worker's monotonic clock since the request's start). Accept only `−ABORT_MATCH_S ≤ close_gap_s ≤ TELEMETRY_GAP_S`.
No local log stamp enters any condition (`TelemetryLine.stamp` may stay as diagnostic text only). The real leg-3 item gives
3645.065 − 3643.5 = 1.565 s. Tests: sol-1's scenario (one telemetry line, then a 3622-s pause across the fall-back) → `ok=False`;
`wall_s` absent → `ok=False`.

X2 (sol-2, major) — the export must belong to the row: (a) also requires `export.info.id == row.session_id`, and every
`request_usage` message id appears among the export's assistant message ids, in order, before the aborted message. Test: a foreign
export (the leg-3 export with another `info.id`, sha recomputed) → `ok=False` on the failed variant.

X3 (sol-3 + test-writer F2, major) — (a) requires `time.created` and `time.completed` both ints with `created ≤ completed`; the
`client_abort` block is built only from validated values. Tests: missing / non-numeric / reversed `created` → `ok=False`, never an
exception out of `reconcile_item` or the hook.

X4 (sol-4 + test-writer F3, major) — `p426_freeze`'s R3 check uses its own probe-kill tuple
`("kill_boundary", "kill_inflight_failed", "kill_completed_unaccounted")`, not `p426_reconcile.KILL_CASES`. Test: an R3 tree whose only
kill case is `kill_client_aborted` is refused.

X5 (sol-6 + test-writer F1 + driver, major) — `p426_leg.battery_window` must resolve `subprocess.run` at call time (`run=None` →
`run or subprocess.run`), so a monkeypatch of `subprocess.run` reaches it. Test: patch `subprocess.run`, call through `main`'s battery
closure / `battery_window`, assert the fake ran and no real process started. Then
`bench/tests/test_t3_frozen_record.py -k live_venv_that_differs` runs in ≈ baseline time (≈ 12 s).

X6 (driver P598, hazard) — the leg receipt's `started` / `ended` stamps become UTC: they must carry an explicit marker so committed
receipts never mix two meanings in one format: `utc_stamp()` → `YYYY-MM-DDTHH:MM:SSZ`; `stamp_epoch` reads that form and epoch numbers;
an unmarked `YYYY-MM-DD HH:MM:SS` text raises `ValueError` (never guessed). Update the callers and the tests that pin the old format.

X7 (driver P599, blocker for every Go leg's harvest; found by the dry run over leg 3's real tree) — the Go toolchain writes telemetry
counters into the probe's run HOME (the run's private `home` dir, `Library/Application Support/go/telemetry/local/compile@go1.27.3-go1.27.3-darwin-arm64-2026-11-01.v1.count`
and the same for `asm`, `go`, `link`, `vet`); they classify `excluded` (`private_state`) but `HARVEST.json` lists each excluded source
name and the main-bound email gate reads `compile@go1.27.3-…` as a foreign address → `HARVEST.json: quarantined or not portable
(email)`, rc 4. Change: `HARVEST.json` records `private_state` exclusions as ONE entry per private run directory
(`source = "run:<id>/<dir>/"`, `destination = "excluded"`, `reason = "private_state"`, `files` = count, `sha256` = sha256 of the sorted
`"<relpath>\t<sha256>\n"` lines); the per-file list (relpath, sha256) goes to the evidence stage as
`<attempt>/excluded_private_state.json` (the evidence scrub applies to it as to any evidence file). Every other exclusion (e.g.
`uv-<hex>.lock`) stays per file. The email gate is unchanged. Tests: those five real names under a run HOME → the harvest (and
`--dry-run`) is clean; a foreign address in a main-bound record still refuses.

X8 (driver P600, spec gap — the plan's "Records" step) — `harvest_wave2(..., namespace="wave2")`, CLI `--namespace`, allowed `wave2` or
`wave2.<label>` with `<label>` matching `[a-z0-9][a-z0-9.-]*`; it replaces the hard-coded `WAVE2` in the main and evidence destinations,
the published paths, and `publish_records` (`run/`, `pairs/`). Default unchanged. Tests: `--namespace wave2.v8-af0711cf` publishes
under `benchmark/results/p426/wave2.v8-af0711cf/<attempt>/`; an invalid namespace (`../x`, `wave3`, `wave2/`) is refused.

Declined (not to be changed): sol-5 (dry-run stopping at a structural leg.json error — it still refuses, nothing published; residual),
sol-7 (`ItemReport.client_abort` field — nothing serialises `ItemReport`; item records verified unchanged), the hook's `"."` fallback
without `ops.wd` (fails safe).
