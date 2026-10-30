# P426 B2 (the whole candidate) — strict change review rounds 1–3 of 3, dispositions

Material: a read-only checkout of the B2 candidate (stack `main` `61d31bcd` + the B2 commits; `CHANGE.diff` against the base; rounds 2–3
add `REPAIR.diff` since the previous snapshot), spec `docs/specs/p426-b2-tg1-wave2.md` v3.2 with §16.1–§16.8. Context: `checkout`
(each member in its own copy). Mode: strict (review-panel), the three-round cap of AGENTS.md — all three used; what remains open after
round 3 goes to fix round 5 under C256 with designer verification, no fourth round.

| Member | Runtime | Model (reported) | Session | Context | R1 | R2 | R3 |
|---|---|---|---|---|---|---|---|
| sol | cursor-agent 2026.10.22 | `gpt-5.6-sol-high` (requested; not reported) | not reported (fresh each round) | checkout, user instructions unconfirmed | 7 blockers, 3 majors | 10 / 12 resolved; 2 not fully + 2 new | 6 / 6 resolved; 4 new |
| glm | cursor-agent 2026.10.22 | `glm-5.2-high` (requested; not reported) | not reported (fresh each round) | checkout, user instructions unconfirmed | 2 majors, 1 minor | 12 / 12 resolved; 1 minor; NOTHING OF SUBSTANCE | 6 / 6 resolved; 1 minor hardening; NOTHING OF SUBSTANCE (ran `test_b2_fix4.py` 29 / 29 in its copy) |
| sonnet | claude CLI | `claude-sonnet-5-5` | `3164b152-20bd-4032-8065-0ec0d34c606c` (resumed each round) | checkout, project settings loaded; same vendor as the driver | 4 minors (read harvest / secrets / reconcile / part of freeze only) | its 2 resolved; 1 minor | its parts resolved; NOTHING OF SUBSTANCE (did not read sequencer / locks / hooks / receipt) |

Coverage note: sonnet stated a partial reading every round; sol and glm traced the sequencer, freeze, hooks and harvest. Fix rounds 3 and 4
(implementer session `bc1647f9-4024-42cb-9edb-d850dd5d900b`) carried the repairs; the spec pins are §16.8 "after the strict verify round 1 /
round 2".

## Round 1 ledger

| # | Finding | Raised by | Disposition |
|---|---|---|---|
| 1 | `p426_dnf.load` swallowed by a comment; `attempt` = the per-stem counter, not `<leg>.a<n>` | glm (major ×2), sol P8 (major) | Adopted (fix3): `load` restored; `attempt` parsed from the out-root name. |
| 2 | A resumed pair dossier trusted by its stored verdict | sol P1 (blocker) | Adopted: re-verified against the current receipts / harvests. |
| 3 | `KV_*` / `TQ_*` prefix exemption leaks e.g. `KV_API_KEY` into the public receipt | sol P2 (blocker) | Adopted: exact committed allowlist. |
| 4 | DNF requests never engagement-checked; ON items with only ≤ 1-token requests pass | sol P3 (blocker), sonnet F3 (scope) | Adopted: DNF records engagement-checked and re-validated; an ON item / leg with no judgeable request is `unengaged`. |
| 5 | In-flight DNF cases accepted without in-flight evidence; kills hard-code `inflight_possible` | sol P4 (blocker) | Adopted: the structured in-flight marker required; kills derive it. |
| 6 | The pilot gate bypassable via `amend` / an existing amendment | sol P5 (blocker) | Adopted: `write_amendment` runs the full gate and records `pilot_dossier_sha256`; an existing amendment is re-verified. |
| 7 | R1–R3 roots not bound to the rehearsal manifest | sol P6 (blocker) | Adapted: each root must be a leg run under that manifest (`frozen_record`, `inject`, leg name); the manifest's commits are not compared with the v8 arms (§1: rehearsals run on other commits). |
| 8 | Harvest: missing self-hash passes; `leg.json` not checked; DNF sidecars not cross-checked | sol P7 (blocker) | Adopted: every immutable record needs a present valid self-hash; `chain.json` DNF entries equal their sidecars. |
| 9 | Run-file publication failure exits 0 | sol P9 (major) | Adopted: exit 4. |
| 10 | A manifest run id resolving to no directory passes | sol P10 (major) | Adopted: none or several → the harvest fails. |
| 11 | `ready_sha256` is the file hash, not the self-hash | glm F3 (minor) | Adopted. |
| 12 | Secrets parsing: shell comments, JSON `Bearer` form, non-UTF-8 evidence | sonnet F1, F2, F4 (minor) | Adopted: shell-style parsing (an unparseable credential line refuses), quoted / JSON bearer form, `surrogateescape` decode marked `lossy_decode`. |

## Round 2 ledger

Round-1 items: all resolved per glm (12 / 12); sol: 6 and 8 not fully (→ R2-3, R2-2); sonnet verified its own (4, 12) and 3.

| # | Finding | Raised by | Disposition |
|---|---|---|---|
| R2-1 | Publication (`publish_dossier`, `publish_run_files`) ran the gate without the exact credential values; `sequence.json` carries operator text | sol P14 (blocker) | Adopted (fix4): the same in-memory credential values as the leg harvest; a configured secret in `sequence.json` refuses, nothing published. |
| R2-2 | `publish_run_files` did not require self-hashes | sol P8 (major) | Adopted: every run file except `sequence.json`. |
| R2-3 | `makeup` used an existing amendment without re-verifying it | sol P6 (major) | Adopted: `run` and `makeup` re-verify before any leg. |
| R2-4 | Dossier publication not idempotent on resume; failure not exit 4 | sol P13 (major) | Adopted: published before the pair record is saved; `published` flag; resume republishes; failure = exit 4. |
| R2-5 | `$VAR` / `$(…)` / backticks in a credential value silently disable the exact match | sonnet (minor) | Adopted: such a value refuses (`SecretsError`, names the key only). |
| R2-6 | An ON DNF item with only ≤ 1-token requests is not flagged `unengaged` per item | glm F-A (minor) | Declined, spec-clarified (§16.8): the per-item rule applies to completed items; a DNF item is covered by the leg-level rule. Accepted by all three in round 3. |

## Round 3 ledger (the last round)

Round-2 items: all six resolved per glm and sol; sonnet resolved 1, 2, 4, 5, 6, did not read 3. New, all → fix round 5 (C256), red-first,
verified by the designer against their tests and the full suite (no fourth round):

| # | Finding | Raised by | Disposition |
|---|---|---|---|
| R3-1 | `republish_dossiers` publishes recorded dossiers without re-verifying them; amendment verification checks only the dossier's file hash (stale dossier certified via `makeup`) | sol P7 (blocker) | fix5: republished dossiers re-verified via `verify_dossier`; amendment verification requires the freshly verified dossier. |
| R3-2 | DNF ledger entries do not require their ready record | sol P8 (major) | fix5: every ledger entry (DNF included) requires and validates its ready record; the DNF record's `ready_sha256` checked. |
| R3-3 | Record publication follows a pre-existing `<dest>.stage` symlink | sol P9 (major) | fix5: stage with `O_EXCL | O_NOFOLLOW`, refuse a non-regular stage, `lstat` the destination after rename. |
| R3-4 | A run-file publication failure keeps an earlier exit 1 / 3 instead of 4 | sol P10 (major) | fix5: any failed run-file publication sets exit 4; the original stop reason kept in the log. |
| R3-5 | Publication's `.env` set comes from the live `--worktree-*` args, the leg harvest's from `v8_base.json` | glm (minor, hardening) | fix5: publication sources the `.env` files from `v8_base.json`, like the leg harvest. |
