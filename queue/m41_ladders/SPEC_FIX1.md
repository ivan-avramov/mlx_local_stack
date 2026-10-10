# M41 runner fix round 1 (from cold review; agent-facing; rules, not rationale)

Edit `run.py`, `helpers.py`, `README.md`, `test_run_dry.py` in this directory only. No commits. Never launch anything but `--dry-run` and the tests.

## R1 Heartbeat must show progress (defect 1, BLOCKER)
For every ladder the HEARTBEAT line reports: `driver_log_bytes=<size of <tag>.log>`, `driver_log_age_s=<now − mtime>`, `progress=<last "[capacity] rung"/"[retrieval] ctx="/"[reasoning] ctx=" line from the driver log, or "none">`, `worker_cmdline_present`, `driver_alive`. The tooling fix adds per-trial progress prints to all three ladders; the heartbeat greps the LAST such line. Also: if `driver_log_age_s` exceeds 5400 (90 min) log `WARN <tag>: no driver output for <n> s (a 262K prefill or a runaway may legitimately take this long; check GPU util before acting)` — never kill on it.

## R2 Capacity read (defect 2)
The peaks tuple gains `error_kind`/`error`: `(ctx, server_peak_gb, fits, prefill_s, decode_tps, acceptance, error_kind)`. If any record has an error: log `TRANSPORT-OR-OOM capacity ctx=<> kind=<> err=<>`; log `GATE-FAIL capacity` ONLY when a record has `fits: False` with NO error. Pass `--request-timeout 7200` on the capacity command (the tooling fix adds the flag; the flag precheck must include it).

## R3 Teardown honesty (defect 4)
`helpers.stop_router`: after the wait loop, if a worker pid is still present log `WARN router stopped but worker STILL ALIVE pid=<pids> — kill by PID and verify` instead of "worker gone"; only log "worker gone" when pgrep is empty. FATAL handler: attempt `h.unload()` (guarded, logged) BEFORE `h.stop_router()`.

## R4 Flag precheck runs under --dry-run too (defect 5)
`check_cli_flags` runs `<python> -m <module> --help` in dry-run as well (no server needed) and FATALs naming the missing flag. Required flags: capacity `--sampling-profile --out-tag --request-timeout`; retrieval `--sampling-profile --out-tag --request-timeout`; reasoning `--sampling-profile --out-tag --request-timeout --deep-from --deep-samples`.

## R5 Dry-run marker (defect 6)
Dry-run ends with `=== M41 DRY-RUN DONE ===` (never the live marker). Update test_run_dry.py.

## R6 Provenance paths (defect 7)
`write_provenance` replaces the literal values of `$STACK_WORKDIR` and then `$STACK_REPO` (in that order) with the placeholder strings `$STACK_WORKDIR` / `$STACK_REPO` in every string field before writing. Test with a fake cmdline string.

## R7 Resume (defect 8)
`--from-step reasoning` (or a FATAL-then-restart) adds `--resume` to the reasoning command when `reasoning.m41on.partial.jsonl` exists; log that it did. README documents the restart recipe: `run.py --from-step <step>`.

## R8 Signals (defect 9)
Install SIGTERM/SIGINT handlers that: log `FATAL signal <n>`, kill+wait the live driver subprocess if any, run the R3 teardown, exit 1.

## R9 Manifest presence (defect 11)
After each ladder assert `<out>.m41on.manifest.json` exists; if not, log `FATAL <tag>: provenance manifest missing (C35 tripwire or gather failure — rows are UNGRADED until provenance is established)` and stop.

## Acceptance
`run.py --dry-run` exit 0 with the flag precheck lines visible; test_run_dry.py green (update for R2/R4/R5); README updated (heartbeat fields, restart recipe, teardown WARN meaning). Report the dry-run output and test result.
