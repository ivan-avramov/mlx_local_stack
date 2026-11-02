# P603 — opencode session-export capture to a file — SPEC v0 (draft, 2026-11-02; build after Wave 2b, four-eyes light)

## Goal

Wave 2b leg 4 `tg1-p426-on-s1.a1` went INVALID because the probe's capture of `opencode session export <id> --standalone` for
`go/bottle-song` ended at exactly 65,536 bytes, mid-string (rc 0, empty stderr) → `unparsable session export` → a systemic abort. The
probe reads the export through a pipe (`arm_opencode.transcript` → `ProcessGuard.run_grader(capture_output=True)` →
`communicate()`, which reads to EOF), so the bytes are lost on the client side: the client exits with output still queued for a full
64-KiB pipe. Across every stored export of `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, 1 of 44 exports ≥ 64 KiB was cut (≈ 2 %; ≈ 10–15 %
per leg). Solving it means an export is captured whole whenever the client wrote it whole, and a truncated capture never aborts a leg
when a re-read would have succeeded; a genuinely unparsable export still aborts.

## Change

- `arm_opencode.transcript`: the export's stdout goes to a regular file (opened write-exclusive in the item's work directory,
  `<work>/.export.<attempt>.json`), stderr stays piped; after the process exits, the file is read and parsed. The file is removed after
  a successful parse (the stored transcript is still written by `raw_sink`, unchanged).
- One re-export on an unparsable capture: if the bytes do not parse as a JSON object, the export is run once more (a fresh file) and
  parsed; the item record notes `export_attempts` (1 or 2) and, for a retry, the first capture's byte count and sha256. A second
  unparsable capture raises `TransportAbort("unparsable session export")` as today. The P273 lock retry is unchanged and composes
  (each attempt may itself retry on a logged lock).
- The probe's identity changes (`probe_code_sha256`): a new v8 for the next wave; never pooled with Wave 2b's rows.

## Tests (red-first)

1. A fake export whose first capture is the real truncated `go/bottle-song` bytes (65,536, scrubbed fixture) and whose second is the
   whole export → parsed, `export_attempts == 2`, the first capture's size / sha recorded.
2. Two truncated captures → `TransportAbort("unparsable session export")`.
3. stdout is a regular file, not a pipe (the fake asserts `os.fstat(1)` is `S_ISREG`).
4. An export > 64 KiB written in one burst by a fake client that exits immediately is captured whole through the file path.
5. Non-zero rc, the P273 lock retry and every existing export test behave as before.

## Non-goals

A change to opencode; any change to what is graded or how rows reconcile.
