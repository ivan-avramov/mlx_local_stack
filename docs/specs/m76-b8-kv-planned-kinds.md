# M76 — B8 kv verifies the stage's planned Wave 1 kinds — SPEC v1, 2026-11-16 (four-eyes light; C354, C352)

## Goal

Stage 3a's readout needs B8 (`bench.p426_verify all --lever kv --pair n16,x`) to verify the harvested Wave 1 of build `s3` and emit
its record for the signals. Today it cannot: `verify_wave1_kv` loops every `KV_W1_KINDS` kind including `m1` and indexes
`m76/ids.json[kind]`, which has no `m1` (a qualify leg has no items) → `KeyError`; and a missing tier-1 leg refuses, so with M1 dropped
from stage 3a (C352) B8 would refuse forever. Solving it means: B8 verifies exactly the kinds the stage planned, records every
unplanned kind as `not_run` with its ruling, still refuses any missing leg of a planned kind, and never indexes `ids` for a kind
without items — the mtp lever and every other B8 behaviour unchanged.

## Scope

`benchmark/bench/p426_plan.py` (the planned kinds), `benchmark/bench/p426_verify.py` (`verify_wave1_kv`, `verify_all_kv`),
`benchmark/bench/p426_wave1.py` (the kv sequencer's default `--axes`); tests `benchmark/bench/tests/test_m76_b8_kinds_*.py`. Read-only:
`benchmark/results/m76/ids.json`, `bench/m76_ids.py`, `bench/p426_signals.py`.

## Interfaces

- `p426_plan.kv_w1_kinds(build) -> tuple` and `p426_plan.kv_w1_dropped(build) -> dict[kind, reason]`: for `s3`, kinds
  `("math500","cjudge","vision","reasoning","longctx")` and dropped `{"m1": "C352: M1 dropped from stage 3a (stage 1's matrix certifies
  memory)"}`; any other kv build → `KV_W1_KINDS`, nothing dropped; an unknown build refuses.
- `verify_all_kv(rows_root, repo, pair, kinds=None, build="s3")`: `kinds=None` → `kv_w1_kinds(build)`; the record's `wave1.not_run`
  lists each dropped kind's blocks as `"<kind>/<label>"` and a new `wave1.dropped = {kind: reason}`.
- `verify_wave1_kv`: indexes `ids[kind]` only for kinds that have items in `ids.json`; a kind with no items (`m1`) is verified from its
  leg evidence as today, never through `ids`; a missing leg of a planned kind still refuses (no verdict on incomplete evidence).
- `p426_wave1 --lever kv`: the default `--axes` is `kv_w1_kinds(build)`.

## Acceptance

1. Red first, on the REAL committed `benchmark/results/m76/ids.json` (no mocked ids): today's `verify_wave1_kv` with the default kinds
   raises `KeyError` / refuses on a synthetic harvested s3 tree with every planned leg and no m1 legs; after: the record verifies, lists
   `m1/b1`, `m1/b2` in `not_run`, `dropped.m1` with the reason; a missing planned leg (e.g. `cjudge … b2`) still refuses; an explicit
   `kinds=` including `m1` with m1 legs present still verifies them; the mtp lever's B8 golden unchanged.
2. (Designer) the public CLI over the real harvested stage-3a Wave 1 emits B8 and the signals run on it.
3. The stack suite passes or fails only as on the baseline.
