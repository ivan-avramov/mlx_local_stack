Status: I checked the spec against the fork's metrics and logging code and the chain's barrier code. I've read enough to report findings.

**Findings (design review round 2 of 3)**

1. **§5.1 Item DNF and §4.3 — blocker. The DNF path contradicts the server's own behaviour, so DNF is mostly unreachable and a healthy leg stops.**
   - The DNF rule requires "zero server `Request failed` in the window". Yet the fork records a failure with `error=stream_closed_before_completion` whenever a streaming client goes away mid-request (`mlx_vlm/server/openai.py:2090`, `:3121`, `:3751`).
   - Every client-side `dropped_stream` or `timeout` abort of an in-flight request therefore leaves a failed line, plus `requests_failed` +1 and a started ≠ completed delta. Only `connection` (never connected) can leave none.
   - Failure scenario: an item hits a client timeout mid-stream, the log shows one failed line, and §5.1 calls that "any server-side `Request failed` outside §4.3's rule" and makes it systemic. The leg stops on exactly the isolated incident the policy is meant to survive. The §13 tests (a mocked fake probe) would pass, and the real server would fail.
   - Fix: extend the §4.3 trailing-failed-line rule to the DNF causes `dropped_stream` and `timeout`, with the same last-request, exactly-one and `stream_closed_before_completion` checks. Say which causes yield zero failed lines (`connection` only). Add a real-server-shaped fixture, not only a fake probe.

2. **§4.3 kill case — major. The "exactly one failed line" rule races with server-side disconnect detection.**
   - The failed line is written when the server notices the disconnect, not when the probe kills. A kill that lands after the server finished generating gives a completed request and no failed line. A kill during prefill, or before the request is accepted, may give none, or a started line with no terminal line until the abandoned generation ends.
   - Failure scenario: a stall kill gives zero or two failed lines, or the settle exceeds 60 s. The result is systemic `INVALID`, even though the item was an ordinary scored strict fail.
   - Fix: define the allowed set explicitly (0 or 1 trailing failed line, with the matching started/completed/failed arithmetic and `requests_at_kill`). Keep the 60 s settle and state whether the cancelled generation can still finish after the disconnect. Get the rehearsal to exercise at least one real kill.

3. **§4.1 and §12 decode time `D` — major. The ON and OFF decode rates may not be comparable.**
   - `D` is reconstructed as `generated_tokens_total / avg_decode_tok_s`, which equals the server's `_decode_time_total_s`. That total sums `decode_elapsed_s` per request, and `_decode_elapsed_from_metrics` (`server/generation.py:752`) defines it as `token_times[-1] − token_times[0]` when at least two timestamps exist. Otherwise it falls back to `generated_tokens / generation_tps`.
   - The numerator counts all N tokens, including the first one from prefill. The denominator spans N−1 inter-token intervals. Under MTP, one round emits several tokens, so how `token_times` are stamped (per token or per round) differs from OFF. Requests also switch between the two branches.
   - Failure scenario: the per-item "Σ generated ÷ Σ D" ratio carries an arm-dependent bias. B6 would read it as MTP speed-up or slow-down.
   - Fix: state the definition B8 / B6 use. Prefer an arm-neutral wall measure (item wall, or request elapsed minus prefill). Document the `token_times` semantics for MTP and mark the decode-rate field as arm-dependent if it stays. Also read `decode_elapsed_s` from the per-request `recent` envelopes instead of reconstructing it by division.

4. **§4.3 DNF item reconciliation — major. The text does not say how a DNF'd item's log slice and counters are reconciled, or where the next item's window starts.**
   - `p426_dnf` records the log slice. But after the relaunch, what is the next item's `ready` cursor and counter baseline? The aborted invocation never reaches `done`. Partial `request_usage` may be absent.
   - Failure scenario: orphan lines from the DNF item fall into the next item's window, and its reconciliation fails as "unattributable".
   - Fix: define a DNF reconciliation (the slice is checked against the stamp, and the counters are re-baselined after settle). Test it with a DNF followed by a normal item.

5. **§1 / §7 session legs — major (ambiguity). The in-load pilot phase inside a session leg is undefined.**
   - "A session leg's first invocation is the in-load pilot phase (first 5 items of its first language) as today". Does this replace the barrier or reconciliation for those 5? Do those rows count in pairs, even though "pilot rows never enter pairs" applies to legs 1–2? For s2, the first language is Go, so the "pilot" is Go items that were never piloted.
   - Fix: say that the rows count, that the barrier applies to all of them, and what the phase changes (probably nothing but the invocation split).

6. **§3 / §2 barrier on in P426 only — major. A behaviour change is not covered by a ruling.**
   - The barrier adds idle gaps and a settle poll of up to 60 s between items. The `tg1` chain ran with the barrier off. The spec's own §1 admits this is the barrier's first production run on real hardware.
   - Scenario: barrier waits change thermal state and wall times compared with M63 rows, which feed the Go timeout input in §10.2. The Go timeout `w_lang` is taken from M63 and P456 rows that were measured without barrier waits. The effect is bounded because both arms get the same barrier.
   - Fix: state that the Go `w_lang` is conservative (the 1.5× factor plus 1800 s), or label the barrier waits as part of the arm-equal environment.

7. **§6.4 and §3 entry — minor. Some locations and checks are ambiguous.**
   - Which `logs/mlx_vlm.log` path does the chain read (worktree or `$STACK_WORKDIR`), and is it truncated or per-leg? The log is appended across legs.
   - The rehearsal needs `--frozen-record`, but v8 does not exist yet (§2 refuses a missing one). Say what the rehearsal passes.
   - The ≥ 600 s idle is a sequencer duty and no chain check verifies it.

8. **§11.3 secret gate — minor. Over-broad email-address scan.**
   - A bare "email addresses" match will hit commit authorship, git config and upstream URLs inside rows or transcripts. That quarantines files and fails harvests of VALID legs. Only transcripts on `evidence` are likely affected, but the failure blocks the whole leg.
   - Fix: scope the email match to the operator's own address and domain (as `SCRUB_MANIFEST.json` already does) and make the generic match a warning.

9. **Scope requests (no severity).**
   - Could drop: the full normalized environment receipt could be reduced to an equality check on the router and worker env plus a hash.
   - Could drop: `bench_watch`'s correction-vs-finish note and its token distribution, if AGENTS.md's daemon requirement is already met by the existing watcher fields.
   - Could simplify: §5.5 make-up legs are only on the operator's call, so specify them when they are first needed instead of in this build.

**Sensitive areas:** the §11.3 secret gate and scrub (a data boundary), the lock handling in §9, and the new `p426_continue` policy in `chain_core`.