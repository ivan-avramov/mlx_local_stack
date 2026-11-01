# P586–P589 — Wave 2 relaunch plan (C267; for one cold review, then a fresh session builds it)

## Situation

Wave 2 (`bench.p426_wave2 run`, v8 `af0711cf…`, arms OFF `5fd3c972` / ON `2a173f8b`) stopped at leg 3 `tg1-p426-off-s1.a1` after 2 h 49 min:
legs 1–2 (pilots) VALID + pilot dossier PASS + amendment written; leg 3 ran 22 Python + 1 Go items, then INVALID at the done barrier of
`go/crypto-square`; its harvest refused. Every fix below changes chain code inside the frozen arms → new arms, a re-freeze (new v8), the
pilots again.

## Fixes (each red-first; fixtures from leg 3's real records where they exist)

**P586 — reconciliation of a client-closed stream.** `go/crypto-square`: row `nonconv_kind=client_inactivity`, `gate.requests_completed=2`,
`requests_observed=3`, `termination` all None (no kill record); the worker log ends the session with `Request failed …
error=stream_closed_before_completion in_flight=0` ≈ 45 s into request 3 (opencode closed its own stream), then the client sat idle until the
item ended (wall 3663 s). `p426_reconcile.reconcile_item` already treats `client_inactivity` as a kill; `_reconcile` then takes the
`inflight_failed` branch and requires `inflight_possible` (`termination.in_flight_at_kill ≥ 1`) → `inflight_evidence` fails → systemic.
Change: a distinct case `kill_client_closed` when the row is `client_inactivity`, the termination records no kill (`in_flight_at_kill` /
`reason` / `killed` empty), exactly one failed line which is the last of the window with `error=stream_closed_before_completion`,
`|S| = |C| + 1`, `|C| = gate.requests_completed`, and the completed lines pair with `request_usage`; the item is a scored strict fail as
today (`client_inactivity`). Every other combination keeps its current verdict. Spec §4.3 / §5.1 gain the case. Tests: the real item's row +
its window (scrubbed fixture) passes as `kill_client_closed`; each single deviation (a second failed line, a non-trailing failed line, another
error string, `|C|` ≠ the gate count, a termination that does record a kill with `in_flight_at_kill = 0`) still invalidates.

**P587 — Go grader stderr.** `p426_harvest.classify` has no rule for `<item>.grades/seq-N/go.stderr` (7 files in leg 3). Change: route it to
`evidence` beside `go.jsonl` (the grader's raw stream). Then a dry classifier run over leg 3's whole tree (run + evidence dirs) until no
problem remains (the first dry run stopped early, "2 files classified").

**P588 — web evidence after a barrier invalidation.** The item barrier extracted `go__crypto-square.web.jsonl`; the slot was invalidated, so
no accepted slot attempt is recorded and `after_invocation` / `abandoned_web_evidence` extract it again → `WebEvidenceError: web evidence is
immutable` → a chain abort instead of a clean INVALID end. Change: the barrier records its extraction (path + sha256) for an invalidated slot,
and the later passes reuse it after re-verifying the sha256; a file whose sha256 differs is still an error.

**P589 — rehearsals exercise Go.** R1 (and R2 / R3, which share the schedule) runs `1 + 2` Python items (`SMOKE_PILOT_N`, `SMOKE_FULL_N`).
Change: the rehearsal schedule adds the first 2 Go items of s1's Go order (seed 1001) after the Python ones (spec §1 table: R1 `1 + 2 + 2 Go`);
the R3 stall-kill stays on the first Python item; R2's injected mismatch stays on the first item. Cost ≈ +20–30 min per rehearsal.

## Before relaunch

1. An offline replay of leg 3: every item record through the fixed reconciliation (all 23 reconcile; `crypto-square` = `kill_client_closed`)
   and the dry harvest classifier over the whole tree (no problem).
2. One cold review of the code change (another model family), then the B2 / T3 / M64 / M62 / guard suites.
3. Re-cut both arms on the new `main` tip (P564 form), a new rehearsal manifest, R1–R3 with the Go items: R1 VALID ×2 + dossier PASS, R2
   INVALID (injected), R3 VALID with a kill case.
4. The gate on the new OFF commit (quiet box), new build inputs, `p426_freeze v8` into a NEW record directory and out-base
   (`$STACK_WORKDIR/p426/wave2b/`; the first v8 and its legs stay as the superseded attempt), then `p426_wave2 run` legs 1–8 (≈ 13 h).

## Records

- Harvest the first v8's attempts (pilots VALID + leg 3 INVALID) with the P587 rule through `bench.p426_harvest` directly (spec §11.1), as
  superseded attempts: on `main` / `evidence`, never paired (B8 / B6 consume only dossier-named attempts).
- The leg-3 Python rows (22 items, OFF) are recorded but not used: the leg is INVALID.

## Not changed

The equality rules of the receipt / pair gate; the pilot / amendment logic; the deadlines; anything a VALID leg measures.
