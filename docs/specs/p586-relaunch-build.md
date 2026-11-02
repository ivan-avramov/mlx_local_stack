# P586–P593 — Wave 2 relaunch build — SPEC v1.1, 2026-11-01 (four-eyes light → strict from the fix round: X7 touches the harvest data boundary; plan `docs/reviews/p586/plan.md` v2, C267 / C268)

## Goal (verbatim in every brief)

Wave 2 (`bench.p426_wave2 run`, v8 `af0711cf…`) stopped at leg 3 `tg1-p426-off-s1.a1`: `go/crypto-square` ended with opencode's own
60-minute step cut (`client_inactivity`) while the worker streamed a 77,500-token thinking runaway, and B2's reconciliation had no
accepted case for a client-aborted in-flight request, so the leg went INVALID; the harvest then refused the Go grader's `go.stderr`, and
a re-extraction of the invalidated slot's web evidence turned the clean INVALID into a chain abort. Solving it means: a client-aborted
in-flight request with affirmative client provenance reconciles as a scored strict fail (everything else stays systemic); every file a
Go leg writes has a harvest rule; an invalidated slot ends as a clean INVALID; the rehearsal exercises Go items and that Go failure
path; no B2 logic orders or windows by local log timestamps; and how each ending and each speed was obtained is recorded per item.

## Scope

Files (implementer): `benchmark/bench/p426_reconcile.py`, `p426_hooks.py`, `chain_core.py`, `p426_harvest.py`, `schedules.py`,
`p426_freeze.py`, `p426_leg.py`, and only where a listed change requires it `p426_wave2.py`; the spec text
`docs/specs/p426-b2-tg1-wave2.md` (§1 table, §4.3, §4.5, §5.1, §11, §12, §16.3, §16.8). Tests: a new directory of the test-writer's.
Fixtures: `benchmark/bench/tests/fixtures/p586/` (below).

## Settled constraints

- (operator, C267) P586 only with ALL of (a)–(e); every other shape keeps its current verdict. Red-first; fixtures from leg 3's real records.
- (operator, C154) opencode 2.0.20's step cut is `LocationActivity` `timeToLive ?? "60 minutes"`, built with no arguments: not
  configurable; no binary patches. (Driver, verified 2026-11-01 in the pinned binary and in opencode 2.1.4.)
- (AGENTS) never pool / change deployed sampling; tests never read live registry state; no PII / absolute home paths in fixtures.
- Not changed: receipt / pair-gate equality rules; pilot / amendment logic; deadlines; anything a VALID leg measures.

## P586 — `kill_client_aborted` (+ `kill_client_aborted_completed_unaccounted`)

Today `reconcile_item` treats `nonconv_kind == "client_inactivity"` as a kill and, for one trailing failed line, requires
`termination.in_flight_at_kill >= 1` (`inflight_evidence`), which only a probe kill writes. Spec §4.3's table already allows the
in-flight case for `client_inactivity`; the provenance below replaces `in_flight_at_kill` as its in-flight evidence.

Interface: `reconcile_item(row, lines, before, after, *, client=None) -> ItemReport`. `client` is `ClientEvidence` (a frozen dataclass:
`export` = the parsed opencode export, `export_sha_ok` = bool, `telemetry` = list of `TelemetryLine`, `close_gap_s` = float | None)
built by the done hook; `None` when the row is not `client_inactivity`. New pure parser
`parse_telemetry(data: bytes) -> list[TelemetryLine]` (`uid`, `tokens`, `rolling_tps`, `avg_tps`, `elapsed_s`, `offset`, `stamp` =
the line's leading `YYYY-MM-DD HH:MM:SS,mmm` text), reading the worker's lines
`… - mlx_vlm.server - INFO - Stream Telemetry | uid=<int> | tokens=<int> | rolling_tps=<f> | avg_tps=<f> | elapsed=<f>s | cached`;
a `Stream Telemetry` line that does not parse raises `LogParseError`.

The hook (`P426Hooks.after_attempt`) builds `client` for a `client_inactivity` row: the export from `row.transcript_path` (resolved
like `chain_core.web_record` does), its sha256 compared with `row.evidence_sha256.export`; the telemetry lines of the window strictly
between the trailing request's `Request started` line and its terminal (failed / trailing completed) line; `close_gap_s` per v1.1 X1
(the export's wall time minus the last telemetry `elapsed`; v1's local-stamp difference was unsafe). An unreadable export is a problem, never an
exception.

Accepted ONLY when every condition holds (each a named check in `ItemReport.checks`, `client_abort_<x>`):
- (a) provenance: `export_sha_ok`; the export's last `type == "assistant"` message has `error == {"type": "aborted", "message":
  "Step interrupted"}` and `finish == "error"`; and `|time.completed / 1000 − T| ≤ ABORT_MATCH_S` (5.0), where `T` (UTC epoch) is
  `after.last_error.timestamp_unix` with `after.last_error.error == "stream_closed_before_completion"` for the failed variant, and
  `after.last_request_at` for the completed variant. No local log timestamp enters (a).
- (b) continuity: `≥ 1` telemetry line; one `uid`; `tokens` and `elapsed_s` strictly increasing; every consecutive `elapsed_s` gap
  `≤ TELEMETRY_GAP_S` (120.0); `0 ≤ close_gap_s ≤ TELEMETRY_GAP_S` [superseded by v1.1 X1]. The first line's `elapsed_s` is not bounded (it includes prefill; residual R1).
- (c) no kill marker: `gate.requests_completed_at_kill`, `termination.reason`, `termination.in_flight_at_kill`,
  `termination.killed_verified`, `termination.client_stop` all null and `termination.killed` empty.
- (d) accounting: `row.requests_observed == |S|`; failed variant `|F| == 1`, `|C| == len(request_usage) == gate.requests_completed`;
  completed variant `|F| == 0`, `|C| == len(request_usage) + 1`, `C[:-1]` pairs, the trailing line's session == the row's; plus every
  existing check (serial, session_backend, worker_deltas, started_terminated, pairing).
- (e) normal client ending (adapted from "the probe exited normally": at the done barrier the probe is still running): the row's
  `stop_reason == "completed"`, `opencode_rc == 1`, `client_exit_hang is False`, `torn_tail is False`,
  `reconciliation.trailing == "interrupted"`.

Cases: failed variant → `kill_client_aborted`; completed variant → `kill_client_aborted_completed_unaccounted`; `client_inactivity` at a
request boundary (`|F| == 0`, `|C| == len(request_usage)`) stays `kill_boundary` unchanged. Any failed condition → `ok=False`
(invalidate, systemic). Rows without `client_inactivity` reconcile exactly as today (byte-identical reports on the fixtures of the
existing suites). The item stays a scored strict fail (`client_inactivity`); `KILL_CASES` gains both names.

## P593 — ending and speed provenance

- Item record (§4.5) of the two P586 cases gains `client_abort = {request_index, wall_s, generated_tokens_at_last_telemetry,
  decode_tok_s, rolling_tps, telemetry_elapsed_s, telemetry_lines, telemetry_interval_tokens, cap_s, cap_source}`: `wall_s` = the
  aborted message's `(time.completed − time.created) / 1000`; the four rates / counts from the last telemetry line (a lower bound on
  tokens, labelled so); `telemetry_interval_tokens` = 500 (the fork default `MLX_VLM_STREAM_TELEMETRY_INTERVAL`); `cap_s` 3600,
  `cap_source` `"opencode 2.0.20 LocationActivity timeToLive default (C154); not configurable"`.
- Every item record gains `totals.decode_rate_source = "completed requests (spec 8)"` (the worker counts no tokens or decode time for a
  failed request, so the aborted request is outside `ΔD`).
- The v8 base record (`p426_freeze`) gains `client_step_cap = {seconds: 3600, source: <as above>, bound_by: "opencode_exe_sha256"}`.
  `scaffold_policy_sha256` does not change (the cap is a property of the pinned binary, already bound by its sha).
- Spec §12: B6 reports `client_inactivity` endings per arm as their own runaway-tax category beside budget-hit / turn-cap /
  exec-timeout, and the strict delta with and without the pairs where either arm has one (sensitivity, pre-registered). Text only (B6
  is not built here).

## P587 — Go grader stderr

`classify("evidence", "<item>.grades/seq-<NNNN>/go.stderr")` → `("evidence", None)` (exact shape: three parts, the first ending
`.grades`, the second `seq-\d+`, name `go.stderr`); nothing else changes. `harvest_wave2` gains `dry_run=True` (CLI `--dry-run`):
inventory, classify, scrub and secret checks run over the whole tree and every problem is collected and printed (it does not stop at
the first); nothing is written; rc 0 when clean, 4 otherwise.

## P588 — invalidated-slot tombstone

When the done barrier invalidates a slot after extracting its web evidence, the `p426_invalid` entry carries
`web_evidence = {slot, rerun_index, path, sha256}` (the barrier's extraction record; `None` when it extracted none). `after_invocation`
and `abandoned_web_evidence` skip a tombstoned `(slot, rerun_index)` after checking the file's sha256 equals the tombstone's (a
difference or a missing file → `ChainAbort`); they never append a `slot_attempts` entry for it. The leg ends INVALID (rc 2) — no
`ChainAbort` on the leg-3 shape.

## P589 — the rehearsal runs Go

`schedules.tg1(..., rehearsal=True)` keeps both languages: Python 1 pilot + 2 full (unchanged), then Go = the first
`REHEARSAL_GO_N = 2` items of s1's seeded Go order (seed 1001), one `full` invocation. R3's stall-kill stays on the first Python item.
R2's `reconcile-mismatch` perturbs the first `done` whose item is `go/*` (after its web extraction), so R2 ends INVALID on a Go slot
through P588's path. `p426_freeze`'s rehearsal-manifest check requires R2's invalidated slot to be a Go slot and R1's legs to hold
the `1 + 2 + 2` items. Spec §1 table and §16.3 / §16.8 updated.

## P590 — DST

Audit every B2 module (reconciliation, settle, A4 window, watcher, harvest, leg / qualify receipts) for ordering or windowing by local
timestamps; report each use found. Known: `p426_leg.watch_problems` and the qualify `battery()` window convert naive local
`strftime` stamps with `time.mktime` (ambiguous across the fall-back hour). Fix each red-first (stamps in UTC or epoch). P586's only
local-stamp use is (b)'s short close gap, which fails safe.

## P591 / P592 — the client's step cap

P591: the source is recorded (above; spec §15 residual R2). P592 (an explicit carrier timeout) is **not buildable** on 2.0.20 — see
open question P594; this build carries no carrier change unless the operator rules otherwise.

## Fixtures (`benchmark/bench/tests/fixtures/p586/`)

From leg 3 `go/crypto-square`: the row (as written), the ready record, the item record's `worker_before` / `worker_after`, the worker log
window `[1583963, 1618437)` (207 lines; no PII found), the export with `info.location.directory` replaced by
`$STACK_WORKDIR/scratch/…` and the row's `evidence_sha256.export` recomputed for the scrubbed bytes (recorded in a `README` with the
original sha `261b808d…`). Plus leg 3's tree listing (relative paths only) for the dry classifier test.

## Acceptance criteria

1. The fixture item reconciles `ok=True`, case `kill_client_aborted`, with the `client_abort` block; red on the baseline.
2. One negative test per condition (a)–(e), each flipping exactly one fact of the fixture → `ok=False` naming that check; the completed
   variant passes on its synthetic shape and fails when (a) or (c) fails.
3. Non-`client_inactivity` rows: reports unchanged (the existing B2 / T3 / M64 / M62 / guard suites pass as on the baseline).
4. `classify` of every leg-3 path has a rule; `--dry-run` over a fixture tree reports all problems at once.
5. The leg-3 shape through the chain (fake ops): INVALID rc 2, no `ChainAbort`, no accepted `slot_attempts` entry for the slot; a
   tombstone sha mismatch → `ChainAbort`.
6. The rehearsal schedule is `1 + 2` Python then 2 Go; R2 injects on the first Go item; the freeze refuses an R2 invalidated on Python.
7. A test with `TZ=America/Los_Angeles` and a leg spanning 2026-11-01 01:00–02:00 local: watcher ticks need and the battery window
   are correct (red on the baseline).
8. Offline replay: all 23 leg-3 items reconcile through the new code (`crypto-square` = `kill_client_aborted`), the dry classifier is
   clean on leg 3's real tree (driver step, after the build).

## Non-goals

A carrier / plugin change (P594); B6 / B8 code; server changes; the harvest of the superseded run (an operational step after the build).

## Residuals

R1 a stall during prefill before the first telemetry line is not detected by (b). R2 the 60-min cap is arm-asymmetric (OFF decodes
slower and is cut at ≈ 76K tokens of an 81,920 budget): reported per arm (P593), not removed (P594).

## v1.1 — fix round 1 (supersedes v1 where they differ; reviews `docs/reviews/p586/build-r2.*`, `build-r3.*`, dispositions `build-fixlist.md`)

- X1 (sol r2 P1, blocker): v1's close gap by local log stamps was NOT fail-safe — a pause of ≥ 1 h across the DST fall-back reads as
  `true − 3600` s. Now `close_gap_s = wall_s − last.elapsed_s` (the export's `(time.completed − time.created) / 1000` of the aborted /
  trailing assistant message, minus the last telemetry `elapsed`), accepted in `[−ABORT_MATCH_S, TELEMETRY_GAP_S]`; no local log stamp
  enters any condition (`TelemetryLine.stamp` diagnostic only).
- X2 (sol r2 P2): (a) also requires `export.info.id == row.session_id` and every `request_usage` message id among the export's assistant
  ids, in order, before the aborted one.
- X3: (a) requires `time.created` / `time.completed` ints with `created ≤ completed`; the `client_abort` block uses validated values only.
- X4: `p426_freeze`'s R3 check keeps its own probe-kill tuple (a client abort is not R3's injected kill).
- X5: `p426_leg.battery_window` resolves `subprocess.run` at call time (test fakes reach it).
- X6: leg stamps are `YYYY-MM-DDTHH:MM:SSZ`; `stamp_epoch` refuses unmarked text.
- X7 (driver P599): `HARVEST.json` folds `private_state` exclusions to one entry per private run directory; the per-file listing goes to the
  evidence stage only (Go's telemetry counters `compile@go1.27.3-…count` read as addresses to the main-bound email gate).
- X8 (driver P600): `harvest_wave2(namespace=…)` / `--namespace` (`wave2` or `wave2.<label>`).
- Acceptance criterion 3 reads: the item RECORDS of non-`client_inactivity` rows are unchanged apart from `totals.decode_rate_source`; the
  in-memory `ItemReport` gains the optional `client_abort` field (None for them) — nothing serialises `ItemReport` (sol r2 P7).
- Residuals added: sol r2 P5 — `--dry-run` stops at a structural `leg.json` / state / attempt-name error before the inventory (it still
  refuses and publishes nothing); the close gap includes client→server latency (≈ 1.6 s on leg 3).

## Open questions

P594 (operator): the client cap — (A) keep it, record + report per arm + sensitivity (this spec); (B) a spike on a probe plugin that
emits a durable session event during long steps to refresh the TTL (unverified; a scaffold change; its own validation).
