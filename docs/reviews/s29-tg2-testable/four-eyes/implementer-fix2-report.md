# Implementer report, fix round 2 — S29 tg2 testable, K1 binding on real worker logs

Baseline `cd334f773e6bc6d1e2f9f1344755e4df787b4fef`. Candidate 3: `out/candidate-3.diff` (the brief's export). Nothing committed.
The task was the round-1 report's F1: K1 did nothing on real worker logs because the fork's `Request started` / `Request failed`
lines carry no uid and no session.

## Findings first

- **F1 — the real S29-P16 window now reconciles as `accounting`.** I ran the reconciler on the real n16 s2 a1 worker log: 41
  starts, 40 completions and 1 failure, with no uid or session on the start / failure lines. It binds through the serial in-flight
  evidence, and the only check that fails is `kill_trailing_failed`.
- **F2 — the real-window test makes assumptions that the recorded shape does not hold.** These are the same ones the frozen
  fixture makes:
  - the row's `session_id` is the session that the window's completed lines name (`ses_df8f707b0ffeUkNCqiP31QY1xq`);
  - `gate` and `event_types_seen` both count 40;
  - the per-item `before` snapshot is the kill-time `after` summary minus the window's own requests and tokens.

  The window boundary is my choice: it starts at the line after the previous item's last `Request completed` (log line 13121)
  and runs to the end of the file (line 14076). The hook's real window may start a few bytes earlier or later. Those bytes hold
  no request lines, so the verdict does not depend on the exact start.
- **F3 — the dead request's processing is recorded, not counted.** After the failure line, the worker still queued and prefilled
  the request (`Prompt Delta: 842`). The K1 facts now carry `trailing_processing: "descriptive"`. Nothing states that this
  processing is zero. The item totals hold only the completed requests; the dead request's prefill is not added to them because
  no `Request` line reports it. I replaced the old docstring, which said "nothing to prove zero".
- **F4 — what decides a request's lifecycle.** "The next line of the request lifecycle" means the next `Request
  started/completed/failed` line, because that is all `parse_log` keeps. Other lines between them (`resolved sampling`,
  shrink-on-retire, telemetry, and the queued / prefill lines after the failure) are ignored. If the designer wants `Generation
  queued` / `Prefill started` to count as lifecycle lines, that is a design change.
- **F5 — a uid on only one of the two lines → INTEGRITY.** If exactly one of the two lines carries a uid, the result is integrity
  (the brief's "anything else"). If both carry one, candidate 2's rule applies unchanged: the uids must be equal, and any
  `session` field must equal the item's. The serial evidence is not also required in that case; I followed the brief literally.
- **F6 — a new test fixture of 180 KB.** `benchmark/bench/tests/fixtures/s29c_p16_worker_window.log` is lines 13121–14076 of
  `.fe-material/p16-worker-log.log`, copied byte for byte. I scanned it for home paths, usernames, emails, hostnames and the
  `@` character: no matches. It contains model names, `ses_…` ids and local timestamps.

## What changed (`benchmark/bench/p426_reconcile.py`)

- `_k1_bound(lines, session)` now returns the binding facts, or `None` for integrity:
  - **No session:** the row needs a `session_id`. A `session` field on the started or failed line must equal it.
  - **Both lines carry a uid:** the uids must be equal → `binding="uid"`, `request_uid=<uid>`.
  - **Neither line carries a uid:** the line before the pair (`lines[-3]`) must be a `Request completed` that names the item's
    session. The in_flight values of that line, the start and the failure must be present and equal 0, 1 and 0 →
    `binding="serial_in_flight"`, `request_uid=None`, `prior_completed_offset`. Because the window holds only lifecycle lines,
    "adjacent" rules out any other start, completion or failure in between.
  - **Only one line carries a uid:** `None`.
- `_trailing_failed_at_kill` keeps its existing checks unchanged: started +1 / failed +1 / completed +0, in flight 0 at the
  pre-signal sample, one failure and it is the last line, STREAM_CLOSED, |S| = |C|+1, failure at or after the signal. On top of
  those it spreads the binding facts into the record and adds `trailing_processing="descriptive"`.

## Tests (`benchmark/bench/tests/test_s29c_impl_k1.py`, 45 tests; plus the fixture)

| test | red on candidate 2 | green now |
|---|---|---|
| real window → `accounting`, binding `serial_in_flight`, session, failure ≥ signal | red (integrity) | yes |
| real window: trailing processing recorded descriptive, totals hold only the 40 completed requests | red (`late_record` None) | yes |
| synthetic no-uid P16 shape → K1 by serial evidence | red | yes |
| uid shape records `binding="uid"` | red (KeyError) | yes |
| instrument: the fixture is the real format and the recorded item (41/40/1, pairs equal `request_usage`, no uid/session, in_flight 0/1/0, `Prompt Delta: 842` after the failure) | [INV] | yes |
| INTEGRITY, no uid, synthetic: foreign session on the last completed line; last completed in_flight=1; last completed without in_flight; failure in_flight=1; trailing start in_flight=2; interleaved foreign request before the trailing start; interleaved start before the failure; no completed line before the pair; trailing pair names another session | see below | yes |
| INTEGRITY, no uid, counts / signal: started +2, failed +2, completed +1, failure before the signal, in flight at the pre-signal sample | see below | yes |
| INTEGRITY on the real bytes: failure in_flight=1; foreign session on the last completed line; interleaved foreign request | see below | yes |
| the earlier "no uid on either line → integrity" case | moved: that shape is now K1, so the case became "no uid, trailing pair names another session" | yes |

**About "red" for the INTEGRITY cases.** Candidate 2 refused every uid-less pair, so all INTEGRITY cases were already green on
it. To show that each test actually discriminates, I ran them against a deliberately naive binding: a scratch monkeypatch that
accepts any uid-less pair (`impl/scratch/red/test_red_fix2_k1.py`, not in the diff).

- **Red under the naive binding (11):** the 7 synthetic serial-evidence cases other than the interleaved start, all 3 real-byte
  cases, and the foreign-session pair.
- **Green under the naive binding:** the interleaved start before the failure, and the 5 count / signal cases. Checks that
  already existed (serial, |S| = |C|+1, worker delta, signal) refuse those shapes, so they are guards, not red-first tests.

## Commands and results (all `../fe_test.sh stack …`, cwd = the copy)

| run | result |
|---|---|
| `bench/tests/s29c_frozen` run alone (`out/fix2-frozen-solo.txt`, `.xml`) | **720 tests: 720 passed, 0 failed, 0 skipped.** The docker JS case ran; it was not skipped for network. |
| the related set = `out/related-args.txt` (all `test_s29c_impl_*`, `configgen/tests`, the module files, the s26/s29/s29b/p586 frozen dirs, p613s3/s4), `--basetemp=/private/tmp/s29c-fix2-bt` (`out/fix2-related.txt`, `.xml`) | **4632 tests: 4629 passed, 2 failed, 1 skipped.** The skip is configgen schema capture (the bench opencode 2.0.20 binary is not installed). The 2 failures are `test_s29c_impl_local_run[java]` and `[cpp]`. |
| `test_s29c_impl_local_run.py` rerun alone (`out/fix2-localrun-solo.txt`, `.xml`) | **4 passed** |
| tg1 carrier vs baseline | byte-identical |

**Why the 2 related failures, and the first frozen run's failures, don't count against the code.** They came from my own mistake:
I ran the frozen dir and the related set at the same time. The first frozen run (`out/fix2-frozen.txt`) had 718 passed and 2
failed (rust and java docker). In both runs the grader correctly refused with `TransportAbort: tg2 leftover storage from an
earlier grade`, because the other run's grade containers and volumes were live. When each was rerun alone, everything passed.
I removed no containers or volumes. Afterwards `docker ps -a` showed no containers. I did not list volumes: that command needed
approval. The solo runs' clean starts show none were left in the way.

Not run this round: the `GATE_PUSHED_BASE` arm-closure test (environment, as in rounds 0 and 1). No real opencode session was
run (no 2.0.20 binary on this box).

## Export note

The brief's `git add -A -- benchmark configgen` also staged the refrozen frozen-test files, including the previously untracked
`test_s29c_adopted_defects.py`. The pathspec leaves that directory out of the diff, and I changed nothing in it.
