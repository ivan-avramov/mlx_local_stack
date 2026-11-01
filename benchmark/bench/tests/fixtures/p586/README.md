# P586 fixtures — Wave 2 leg 3 `tg1-p426-off-s1.a1`, item `go/crypto-square` (first v8 `af0711cf…`, superseded)

Real records, scrubbed: the absolute workdir prefix is replaced by `$STACK_WORKDIR`.

- `row.json` — the probe row as written; `transcript_path` set to `<FIXTURE>/export.json` and `evidence_sha256.export` recomputed
  for the scrubbed export (`e95b107f…`; the original export's sha256 was `261b808dc42d39102af7077ac72241de80b1b1c22b21fc2b5b4b8a2eb876aa3c`).
- `export.json` — the opencode export (scrubbed).
- `ready.json` — the slot's ready record (log cursor 1583963).
- `item_record_baseline.json` — the item record the baseline code wrote (`verdict: invalid`, `inflight_evidence`); its
  `worker_before` / `worker_after` are the reconciliation's `/metrics` snapshots.
- `window.log` — the worker log bytes `[1583963, 1618437)` of `<WT>/logs/mlx_vlm.log` (sha256 `5c0c6e40…` = the item record's
  `log_range.sha256`); 207 lines, 155 `Stream Telemetry` lines, local time across the 2026-11-01 DST fall-back.
- `leg3_tree.tsv` — `<root kind>\t<relative path>` of every file in the leg root (`leg`) and the Go evidence directory (`evidence`).
