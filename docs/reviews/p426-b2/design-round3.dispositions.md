# B2 design review round 3 of 3 (the last) — dispositions (designer: Claude Opus 5.5, 2026-10-24)

Members (fresh sessions): `gpt-5.6-sol-high` (`649b9f9d…`), `glm-5.2-high` (`c88b4107…`), Claude Sonnet (`acc26733…`). Spec v3 `996e2f8a` →
v3.1, NOT re-reviewed (AGENTS.md: three rounds per artifact, then the operator).

Verified before judging: the `Request completed` line DOES carry the draft counters — `_build_metrics_envelope` does
`envelope.update(draft_counters)` and `_format_verify_counters` appends every `draft_*` key (fork `0f30522c`, `server/generation.py`).

Ids: S = sol, G = glm, C = Sonnet.

| Finding | Disposition | v3.1 |
|---|---|---|
| S1 (blocker) DNF abort manifests lack `request_usage` | adopted: P426 abort manifests carry the gate report with `request_usage`, session, in-flight message, termination | §2 |
| S2 (blocker) raw `RECORD` hashes vs editable installs | adopted: verified content inventory; editable dists identified by their source tree | §6.4 |
| S3 (blocker) own-lock-first gives zero winners | adopted: acquisition arbiter | §9 |
| S4 positive / negative rehearsal conflated | adopted: R1 / R2 / R3 on fresh roots | §1, AC2 |
| S5 / C-F5 model snapshot identity not checked per leg | adopted: snapshot revisions + file hashes vs `pins.json` | §3, §6.4 |
| S6 env values compared only for prefixes | adopted: every non-secret value, closed volatile list | §6.4 |
| S7 / C-F4 pair gate after the second leg | adopted: comparison before item one of the second leg + immutable pair dossier | §3, §6.5 |
| S8 / C-F3 credential classifier false positives | adopted: allowlist + length / placeholder floor | §11.3 |
| S9 `connection` covers established-stream resets; lost completions | adopted: DNF rows by observed state; `completed_unaccounted` case | §4.3 |
| S10 no whole-leg log boundary | adopted: `log_bounds.json` (path, device, inode, offset) | §4.2 |
| S11 symlinks in final trees | adopted: `lstat`, never followed, harvest fails | §11.2 |
| S12 power: C220 vs speed-only | open → **operator at Go** (unchanged recommendation); "before every invocation" power made speed-only | §3, §8 |
| S13 make-up groups must be single-language | adopted: (session, seed, language) | §5.5 |
| S14 C221 applies to every tg1 mode; `PRED_S` | adopted | §2 |
| S15 in-memory secret equality not crash-resumable | adopted: a restart between paired legs voids the pair | §6.5 |
| S16 decode estimator negative on 0-token requests | adopted: `max(g − 1, 0)` | §8 |
| G1 make-up should run only the DNF-ing arm's occurrences | **declined** (major): C220 says the DNF items rerun "for BOTH arms" so each has a pair; the union runs in both legs, now stated | §5.5 |
| G2 engagement source unnamed | adopted: the `Request completed` line (verified) | §4.1, §4.4 |
| G3 A4 window engagement scope | adopted: item requests judged, A4 recorded | §4.4 |
| G4 loaded `libmlx` unobservable | adopted: loaded paths from the live worker | §6.4 |
| G5 DNF scoring contract unpinned | adopted: operator rules at Go; §12 states it | §5.4, §12 |
| G6 watcher death in overrun | adopted: pid poll per tick | §8 |
| G7 one or two venvs | adopted: per distinct interpreter resolved from pids | §6.4 |
| G8 make-up legs operator-triggered | adopted | §1 |
| G9 rotated secret; record source digests | partly: unreadable → refuse (already); recording secret-file digests **declined** (S10: no secret verifiers in outputs); harvest right after each leg; rotation residual named | §11.3 |
| G10 (scope) drop the env key set | declined (S6 needs every value) |
| C-F1 (blocker) no source carries `draft_*` | **declined** (factually wrong: the completed line carries them, code above); the source is now named | §4.1 |
| C-F2 policy branch sites / hook vocabulary / infra errors | adopted: enumerated, one test per site; infra errors systemic | §2 |
| C-F6 ON-only timeout DNFs | adopted: per-arm DNF causes + attention flag | §5.4 |
| C-F7 settle bound unsupported | adopted: raised in the amendment from pilot request walls | §4.2 |
| C-F8 harvest reads credential files | shown to the operator at Go (sensitive area) | §11.3 |
| C-F9 reload phase wording; duplicate sums | wording adopted; the duplicate comparison kept (cheap, a second independent check) | §7 |

Not converged by the four-eyes rule (round 3 changed AC2 and added mechanisms); the round cap is reached → the operator decides at Go
whether v3.1 builds as is or gets one more design round.
