# M65 tg2 grader — a timeout kill keeps its start evidence — SPEC v1 + errata v1a, v1b, 2026-11-16 (four-eyes light; C355 (1), S24-P22)

## Goal

`bench.tg2_grade` classifies a solution that runs past its step timeout as `timeout` (a model outcome: every leaf failed), never as
infrastructure. Today it raises `TransportAbort("tg2 execute: runner-start marker absent")`. When `subprocess.run` times out it
kills the docker CLI, and the step's host-side stdout file is empty, nonce marker included (recorded on the box: Rust spin
`execute.stdout` 0 B, `rc=None`; JavaScript `while (true) {}` likewise). The OOM and output-cap variants classify correctly. Stage 3b
needs this fixed: each runaway solution becomes a transport DNF, and more than `MAX_DNF` (2) in a leg makes the leg INVALID.

## Rule (unchanged in intent)

The per-grade nonce marker proves the shell reached the compiler / runner. It is checked BEFORE any timeout / OOM / exit-status
classification, and its absence stays infrastructure. Only where the evidence lives changes, so it survives a kill.

## Fix

- Each marked step (compile, execute, collect) writes its marker line `"<TAG> <nonce>"` to the step's stream as today AND to a
  per-step file in the grade's private report volume (`/report/.tg2-marker-<step>-<nonce>`), before invoking the compiler / runner.
- The step's bounded output (`_bounded`) is also written to `/report/.tg2-out-<step>-<nonce>` (same cap), so a killed step keeps its
  partial output as evidence.
- After a step whose stdout lacks the marker, the grader reads back both files with one bounded read-back step on the same volumes
  (collect's pattern: its own marker on stderr, its own timeout), stores them beside the step's outputs (`<step>.marker`,
  `<step>.out`, both sha256 in the step record) and decides `marker seen` from the stream OR the file. No file and no stream marker
  → `TransportAbort` as today.
- A failed read-back step (launch error, its own timeout, missing read-back marker) is `TransportAbort`, never a model outcome.
- Unchanged: outcome classes, the OOM / mem-kill / output-cap paths, the forged-marker rule (the exact nonce only), container and
  volume cleanup, `VERSION` bumped (grader identity changes; `m65-tg2-v3`).

## Scope

`benchmark/bench/tg2_grade.py`; tests `benchmark/bench/tests/test_tg2_grade_timeout_*.py`; the fake docker harness in
`benchmark/bench/tests/test_tg2_grade.py` may gain the real-box fact (below) without changing any existing assertion. Read-only:
`benchmark/m65/` (universe, image), `bench/structured_grade.py`.

## Acceptance

1. Red first, fake harness: the fake reproduces the box fact first. A timed-out step leaves its stdout EMPTY, and the marker
   file exists in the report volume iff the script got past its marker line. Today `compile` / `execute` timeouts with the marker
   only in the file raise `TransportAbort`; after the fix → `timeout`, all failed. The existing G13 cases (no marker anywhere →
   `TransportAbort`, forged marker) stay green unchanged. A failed read-back → `TransportAbort`.
2. Red first, real docker (`@pytest.mark.docker`, skipped with its reason when docker / the pinned image are absent, as the existing
   integration tests): the recorded spin trees (Rust `$STACK_WORKDIR/fe-m76b4b1/inputs/tg2-grade-trees/rust/spin`, the JavaScript
   repro `$STACK_WORKDIR/m76/tg2-record-scratch/js-spin`), committed as sha-pinned fixtures, plus one spin per remaining language
   (Java, C++) → outcome `timeout`, the marker read back from the file, partial output retained. Erratum v1a (S25-P5, zero
   flakes): each spin test's step timeout is ≥ 3 × the slowest reference step measured on a quiet box, floor 5 s (rust / javascript
   5 s, cpp 15 s, java 18 s), stated with its measurement in the test; never the smallest passing value. Report the wall time per test.
3. The reference / stub / compile-failure / tampered / oom / flood recorded trees classify as before (re-graded on the box,
   compared to `SUMMARY.json`).
4. The stack suite passes or fails only as on the baseline (gate).

## Deviation rule

Behaviour and named seams are binding; code shape is the implementer's. State any needed deviation in the report with the code fact
that forces it.

## Known limit (recorded, not fixed)

Solution code runs after the marker inside the same container and could delete or forge the marker file (it can read the nonce
from its parent's argv). That is the same exposure as the stdout marker today, and agentic outputs are not adversarial.

## Erratum v1b (2026-11-16, change review G6)

- Collect writes only its marker file, no `.tg2-out-collect-*`: its stdout is the report tar, not `_bounded` output (teeing it would
  double the report volume's use); its read-back records `out_sha256: null`.
- The existing `VERSION` pin in `test_tg2_grade.py` follows the bump to `m65-tg2-v3` (the Fix requires it).
- The read-back cap is a named invariant: `READBACK_CAP` covers the tar of a full `.out` (`OUTPUT_CAP`) plus the marker and tar overhead with
  margin, asserted at import (G2).

