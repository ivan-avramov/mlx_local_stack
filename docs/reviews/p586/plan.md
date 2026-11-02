# P586–P593 — Wave 2 relaunch plan v2 (C267; plan review round 1 of 3 applied — `plan-r1.*`, dispositions below; a fresh session builds it)

## Situation

Wave 2 (`bench.p426_wave2 run`, v8 `af0711cf…`, arms OFF `5fd3c972` / ON `2a173f8b`) stopped at leg 3 `tg1-p426-off-s1.a1` after 2 h 49 min:
legs 1–2 (pilots) VALID + pilot dossier PASS + amendment written; leg 3 ran 22 Python + 1 Go items, then INVALID at the done barrier of
`go/crypto-square`; its harvest refused. Every fix below changes chain code inside the frozen arms → new arms, a re-freeze (new v8), the
pilots again.

## Fixes (each red-first; fixtures from leg 3's real records where they exist)

**P586 — reconciliation of a client-aborted request (REVISED after review r1).** Diagnosis corrected: request 3 of `go/crypto-square`
was a 77,500-token generation streamed for 61 min (worker stream telemetry every ≈ 20 s, 19–24 tok/s, prompt 5366; a thinking runaway under
the 81,920 budget); at ≈ 3645 s opencode aborted its own step (export: last assistant message `error={"type":"aborted","message":"Step
interrupted"}`, `info.outcome=interrupted`, completed 09:17:02 UTC); the worker then logged `Request failed … stream_closed_before_completion
in_flight=0` (local 01:17:02 PST — the second 01:17 of the DST fall-back day, P590). No harness kill: gate stop None,
`requests_completed_at_kill` None, termination empty. The row's `client_inactivity` came after. Change: case `kill_client_aborted` (and
`kill_client_aborted_completed_unaccounted`, the variant where the worker completed the request after the client closed: `|C| =
len(request_usage) + 1`, trailing completion) accepted ONLY with ALL of: (a) affirmative client provenance — the item's opencode export,
re-verified by its sha256, has its last assistant message with `error.type == "aborted"` and that message's end within a few seconds of the
failed (or trailing completed) line, both in UTC; (b) the worker's stream telemetry for that request continuous until the close (no gap above
a small bound); (c) no harness kill marker of any kind (`requests_completed_at_kill`, `termination.reason` / `in_flight_at_kill` / `killed`,
an abort manifest); (d) `requests_observed == |S|`, every completed line paired with `request_usage`, the session's lines contiguous; (e) the
probe exited normally. The item is a scored strict fail (`client_inactivity`, as today). Everything else keeps its current verdict (systemic).
Spec §4.3 / §5.1 gain the two cases. Red-first from the real item (scrubbed fixture), plus one negative test per condition (a)–(e) and the
completed-unaccounted variant both ways.

**P587 — Go grader stderr.** `p426_harvest.classify` has no rule for `<item>.grades/seq-N/go.stderr` (7 files in leg 3). Change: route it to
`evidence` beside `go.jsonl` (the grader's raw stream). Then a dry classifier run over leg 3's whole tree (run + evidence dirs) until no
problem remains (the first dry run stopped early, "2 files classified").

**P588 — web evidence after a barrier invalidation.** The item barrier extracted `go__crypto-square.web.jsonl`; the slot was invalidated, so
no accepted slot attempt is recorded and `after_invocation` / `abandoned_web_evidence` extract it again → `WebEvidenceError: web evidence is
immutable` → a chain abort instead of a clean INVALID end. Change (revised, review r1 P4): the barrier records an explicit invalidated-slot TOMBSTONE (slot, path, sha256) that both later passes skip —
never reuse into an accepted attempt; tests assert the final `slot_attempts` holds no accepted entry for the slot; a differing sha256 is an error.

**P589 — rehearsals exercise Go.** R1 (and R2 / R3, which share the schedule) runs `1 + 2` Python items (`SMOKE_PILOT_N`, `SMOKE_FULL_N`).
Change: the rehearsal schedule adds the first 2 Go items of s1's Go order (seed 1001) after the Python ones (spec §1 table: R1 `1 + 2 + 2 Go`);
the R3 stall-kill stays on the first Python item; R2's injected mismatch MOVES to the first Go item, after its web extraction, so P588's path
(an invalidated Go slot with extracted web evidence) runs to a clean INVALID (review r1 P5). Cost ≈ +20–30 min per rehearsal.

**P590 — DST (found in the diagnosis).** The worker log carries local timestamps; 2026-11-01 01:00–02:00 local occurred twice. The build
verifies that no B2 logic (reconciliation windows, settle, A4 window, watcher, harvest) orders or windows by log timestamps rather than by
byte cursor / UTC; any that does is fixed red-first (P586's (a) compares in UTC).

**P591 — the client's step cap (found in the diagnosis).** opencode aborted the step after ≈ 3645 s. The build establishes its source
(opencode 2.0.20 default / the generated carrier / a probe policy) and records it in the spec; a fixed WALL cap is arm-asymmetric (ON decodes
faster, so it writes more tokens before the cap) — a residual for B6 / the ship call, not a fix.

**P592 — the client's wall cap (C268; replaces P591's "residual").** opencode cut `go/crypto-square`'s request 3 at ≈ 3645 s of wall time;
neither the generated v2 carrier nor the adapter sets a request / step timeout, so the cap is most likely opencode 2.0.20's default (P591
pins it down). M63: `client_inactivity` appeared ONLY in OFF arms (3 × across the two picks, never ON) — a wall cap cuts the slower arm
first, so it is not a matched budget (AGENTS: rank at a matched budget; client timeouts = max generation / floor decode rate + headroom:
102,400 / ≈ 18 tok/s ≈ 5,700 s + headroom). Change: set opencode's request / step timeout explicitly in the generated v2 carrier, identical
in both arms, to the AGENTS-derived bound (recorded with its derivation), so the thinking budget — not the clock — ends a runaway in both
arms. A scaffold change: the carrier hash and the policy sha change (Wave 2 is fresh; never pooled with M63). Red-first: the carrier
generator emits the bound; a test pins it to the formula. P586's `kill_client_aborted` stays for a cap that still fires.

**P593 — record how every ending and speed was obtained (C268).** The scaffold policy record carries the client's effective cap and its
source; each client-aborted item records its wall at the abort, its generated tokens and the decode rate of that request (server
telemetry); B6 reports client-aborted endings as their own runaway-tax category per arm (beside budget-hit / turn-cap / exec-timeout), so a
quality delta is never read without them.

## Before relaunch

1. An offline replay of leg 3: every item record through the fixed reconciliation (all 24 item records reconcile; `crypto-square` = `kill_client_aborted`)
   and the dry harvest classifier over the whole tree (no problem).
2. One cold review of the code change (another model family), then the B2 / T3 / M64 / M62 / guard suites.
3. Re-cut both arms on the new `main` tip (P564 form), a new rehearsal manifest, R1–R3 with the Go items: R1 VALID ×2 + dossier PASS, R2
   INVALID (injected), R3 VALID with a kill case.
4. The gate on the new OFF commit (quiet box), new build inputs, `p426_freeze v8` into a NEW record directory and out-base
   (`$STACK_WORKDIR/p426/wave2b/`; the first v8 and its legs stay as the superseded attempt), then `p426_wave2 run` legs 1–8 (≈ 13 h).

## Records

- Harvest the first v8's attempts (pilots VALID + leg 3 INVALID) with the P587 rule through `bench.p426_harvest` directly (spec §11.1) into
  their OWN namespace `benchmark/results/p426/wave2.v8-af0711cf/<attempt>/` (precedent `wave1.s2/`; review r1 P6: the new run reuses the
  attempt names `<leg>.a1` under `wave2/`), dossiers included, BEFORE the new run publishes; never paired (B8 / B6 consume only
  dossier-named attempts of the new v8). If the harvest CLI has no destination root, a small option, red-first.
- The leg-3 Python rows (22 items, OFF) are recorded but not used: the leg is INVALID.

## Not changed

The equality rules of the receipt / pair gate; the pilot / amendment logic; the deadlines; anything a VALID leg measures.

## Plan review round 1 (sol, cursor `gpt-5.6-sol-high`, briefed) — dispositions

| # | Finding | Disposition |
|---|---|---|
| 1 | blocker: the P586 predicate (a server failed line alone) cannot tell a client close from a crash / disconnect / server abort / lost kill record | **Adopted (adapted)**: the diagnosis was wrong (a 61-min runaway the client aborted, not a 45-s close); P586 now requires affirmative client provenance (the export's `aborted` message, time-matched in UTC), continuous worker telemetry, no kill marker, a normal probe exit |
| 2 | the predicate omits `requests_completed_at_kill` and never checks `requests_observed` | **Adopted**: both required, with red tests |
| 3 | the completed-after-close race (`|C| = n + 1`) stays systemic | **Adopted**: `kill_client_aborted_completed_unaccounted` under the same provenance |
| 4 | reusing the barrier's extraction can turn an invalidated slot into an accepted attempt | **Adopted**: an explicit tombstone; no accepted entry (tested) |
| 5 | R2 stops on its first Python item, so P588's Go path is never rehearsed | **Adopted**: R2's injection moves to the first Go item, after web extraction |
| 6 | the superseded and new runs collide on attempt names / harvest paths | **Adopted (adapted)**: the superseded run is harvested under `wave2.v8-af0711cf/` first; the new run keeps `wave2/` |

Driver additions: P590 (DST, local log timestamps), P591 (the client's step cap); operator additions (C268): P592 (an explicit, derived client timeout), P593 (ending / speed provenance per arm). Rounds 2–3 remain for the built change.
