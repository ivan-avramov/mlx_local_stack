# B2 design review round 2 of 3 — dispositions (designer: Claude Opus 5.5, 2026-10-24)

Members (fresh sessions): `gpt-5.6-sol-high` (`d8b7b39c…`), `glm-5.2-high` (`7f29c149…`), Claude Sonnet (`34bd9418…`). Spec v2 `1eb81782` → v3.
Verified before judging: the row carries `request_usage` as a list `[message_id, output, prompt, budget]` and
`gate.requests_completed_at_kill` (P456 rehearsal row); `OpencodeArm.transport_cause` returns a cause only in M64 mode; the manifest
`evidence_policy` check in `verify_manifest` is `per_arm`-only.

Ids: S = sol, G = glm, C = Sonnet.

| Finding | Disposition | v3 |
|---|---|---|
| S1 freeze lifecycle circular; no pilot deadline | adopted: rehearsal manifest, v8 base, timeout amendment (hash-linked); pilot deadline in v8 base | §1, §10 |
| G-F11 (scope) pilot timeout | adopted (same) | §10.2 |
| S2 DNF excluded from `acc_strict` vs AGENTS.md "DNF included" | conflict between AGENTS.md and C220 → **operator at Go**; recommendation: count a DNF as a non-success over all planned slots, labelled `transport_dnf`, make-up as sensitivity. B2 records both readings' inputs (round 1's decline of C2 is superseded by this ask) | §5.4 |
| S3 / C1 / C2 failed-line truth table wrong (dropped stream leaves a failed line; kills can leave zero) | adopted: cause- and outcome-aware table; actual field names | §4.3 |
| C2 settle vs disconnect during long prefill | adopted: 900 s bound, 2 s poll | §4.2 |
| S4 overlap not verified | adopted: `in_flight=1` on every start, no overlapping start | §4.3 |
| S5 `invalidate` only after-barrier | adopted: at `ready` and `done` | §3 |
| S6 / C4 no durable ready record; DNF windows | adopted: ready record before `.go`; windows bounded by ready records and settle | §4.2 |
| S7 / G-F2 tg1 stamps no transport cause | adopted: `transport_cause` gate `m64 or p426` named as a probe-code edit; real-adapter test | §2, §13 |
| S8 env equality cannot pass (out-root in `TMPDIR`) | adopted: `<WT>` / `<OUT>` canonicalized; behaviour-affecting allowlist | §6.4 |
| S9 pair equality deferred to B8; lockfile ≠ installed | adopted: sequencer pair gate; package inventory + MLX native-library hashes | §6.4–6.5 |
| S10 unsalted secret digests published | adopted: never recorded; in-memory same / different | §6.4, §11.3 |
| S11 raw logs on `main` vs AGENTS.md | adopted: raw logs / streams → `evidence`; `main` gets parsed records | §4.5, §11.2 |
| S12 closure misses unreferenced and control files | adopted: inventory every file with a rule table; control-file presence rules | §11.2 |
| S13 / G-F4 make-up seeds / occurrence identity | adopted: occurrence records; one invocation per (session, seed) | §5.5 |
| S14 lock check-then-acquire race | adopted: own lock first, then opposing; race test | §9 |
| S15 `draft_n = 0` passes | adopted: integers, `draft_n ≥ 1` | §4.4 |
| G-F1 evidence-policy manifest check `per_arm`-only | adopted: unconditional for `tg1-p426` | §3 |
| G-F3 relaunch loop host; per-item ledger | adopted: own leg loop in the flat layout; per-item ledger | §5.2, §7 |
| G-F5 secret sources unnamed | adopted: sources named; unreadable → refuse | §11.3 |
| G-F6 "both locks" ambiguous; gate → sequencer | adopted (clarified; the gate's opposing locks were in v2 §9) | §9, §10.3 |
| G-F7 `invalidate` vs DNF paths | adopted: separated; tests both ways | §3, §5.2 |
| G-F8 "s2 reversed" wording | adopted | §6.1, §7 |
| G-F9 `ChainOps.overlay` in P426 mode | adopted | §3 |
| G-F10 `request_usage` field | adopted: named (it is on the row today) | §4.1 |
| G-F12 probe live identity per arm | adopted: live `--print-identity` at entry; probe path in the receipt | §3, §6.4 |
| C3 decode time arm-comparability | adapted: estimator `(Σ g − n) / ΔD` (first token excluded, matching `decode_elapsed_s`'s span); same definition both arms | §8 |
| C5 in-load pilot phase rows | adopted: ordinary rows, all checks | §7 |
| C6 barrier changes timing vs earlier chains | adopted as a note: equal in both arms, outside every request; Go deadline allowance | §8, §10.2 |
| C7 log path; rehearsal record; idle unchecked | adopted | §1, §3, §4.1 |
| C8 generic email scan blocks harvests | adopted: operator address / domain refuse; others listed before the `evidence` push | §11.3 |
| C9 scope: shrink the env receipt | declined: S8 / S9 show the equality must be stronger, not weaker |
| C9 scope: drop correction-vs-finish note / token distribution | declined: AGENTS.md requires them in the run daemon |
| C9 scope: defer make-up legs | declined: C220 rules them; deferring needs another strict round later |

Acceptance criteria changed (AC2–AC4) → round 3 (the last).
