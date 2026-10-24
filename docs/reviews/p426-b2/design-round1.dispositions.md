# B2 design review round 1 of 3 — dispositions (designer: Claude Opus 5.5, 2026-10-24)

Members: `gpt-5.6-sol-high` (cursor-agent; first attempt truncated in transit to findings 26–33, re-dispatched in a fresh session
`ed8eb8de…`, both kept), `glm-5.2-high` (cursor-agent), Claude Sonnet (`claude -p`, session `93300222…`). Same model as the designer:
none; same vendor: Claude Sonnet. Spec v1 `be32d962` → v2.

Verified against code before judging: tg1 `item_barrier="off"` (`tg1_runner.py:42`) so the v1 hook never fires; tg1 `abort_restart`
archives the load; `transport_dnf` rows exist only in the per-arm M64 path after a retry (`chain_incident.MAX_INCIDENTS = 2`); flat
layout raises on any non-accept after-disposition (`chain_core.pump_barrier`); the item barrier has never run in production (M64 never
launched, P372); opencode's env is already an allowlist (`opencode_v2_core.SCAFFOLD_ENV_POLICY_V2`); a client kill of a live stream
logs `Request failed … error=stream_closed_before_completion`; the worker `/metrics` summary allows the exact decode time
(`generated_tokens_total / avg_decode_tok_s`); MTP counters are null when no round ran and the first token comes from prefill.

Ids: S = sol re-dispatch, S′ = sol first-attempt tail, G = glm, C = Sonnet.

| Finding | Disposition | v2 |
|---|---|---|
| S1 / G-B1 barrier inert for tg1 | adopted (problem); mechanism: a P426 evidence policy, probe flag `--evidence p426`, the default untouched | §3 |
| S2 / G-B3 hook lacks row / cursor; no systemic disposition | adopted: hook context + `invalidate` disposition | §3, §5.2 |
| S3 / G-B2 / C1 no DNF-continue path; M64 DNF is a scored fail after a retry | adopted: `p426_continue` policy, `p426_dnf` record (ungraded) | §5.2–5.3 |
| S4 worker / router death classified as incident | adopted: identity first, systemic | §5.1, §5.4 |
| S5 / S′26 client-kill trailing failed request | adopted: outcome-aware rule | §4.3 |
| S6 rounds > 0 per request not normative | adapted: required for `generated_tokens ≥ 2` (code-read basis); 1-token requests listed | §4.4 |
| C4 rounds may legitimately be 0; settle; unknown sessions | adopted: same rule; settle poll; unattributable line systemic | §4.2–4.4 |
| S7 decode time not exact from log | adapted: exact from worker `/metrics` deltas, no server code (C225 kept) | §4.1, §12 |
| S8 / C5 / G-B7 arms may differ outside the registry (env, argv, install) | adopted: arm-equality receipt; B8 requires equality | §6.4 |
| S9 power systemic vs speed-only | adopted: entry → NOT_STARTED, in-run → speed-invalid. Interpretation of C220's "power gate" item; shown to the operator at Go | §5.1, §8 |
| S10 / C8 VALID undefined; invalid legs unharvested | adopted | §5.1, §11.1 |
| S11 harvest closure not transitive; no resolver | adopted: typed closure + `HARVEST.json` | §11.2 |
| G-B6 Wave-2 harvester undescribed | adopted: `p426_harvest wave2` | §11.1 |
| S12 overrun ownership; timeout formula | adopted: `OVERRUN_PAUSED`, formula | §10.2–10.3 |
| C6 timeouts per arm | adopted: one value per session for both arms | §10.2 |
| S13 / S′33 / G-B15 make-up undefined | adopted: union, one leg per arm, original seeds | §1, §5.5 |
| S14 drift checked only per invocation | adopted: re-verified at every barrier | §3 |
| S15 / S′30 / C7 public data boundary, secrets | adapted: secret gate before compression, quarantine, no automatic push. Declined: a dedicated credential / minimal env for opencode (its env is already an allowlist; no credential reaches it) | §11.3–11.4 |
| S16 `--models` semantics | adopted | §6.1 |
| S′27 / G-B13 schedule not frozen; order not checked | adopted: frozen schedule + ordered ledger | §7 |
| S′28 / G-B4 / C10 watcher cannot read chain.json; death | adopted: watcher contract, fail closed | §8 |
| S′29 speed-invalid not paired | adopted: per-session pair rule | §8 |
| S′31 pilot gate vague; Go not piloted | adopted: zero-DNF gate; Go timeout from historical walls (residual named) | §1, §10.2 |
| S′32 / C9 / G-B5 census and locks | adopted: owned-identity exemption; locks both directions; close-on-exec | §9 |
| C2 DNF excluded from accuracy biases ON | declined (C220 ruling). The bias channel is closed: any server-side failure is systemic, so an MTP-caused server error cannot become a DNF; DNF counts per arm are reported beside `acc_strict`; an ON-only DNF is an attention flag; make-up legs | §5 |
| C3 DNF vs strict-fail boundary | adopted: cause table | §5.1, §5.4 |
| C11 pilot vs chain relation | adopted | §1, §7 |
| C12 / G-B9 legacy schedules; s2 language order | adopted: goldens; `p426=True` only | §2, §7 |
| G-B8 `--predictor` selector vs assertion | adopted | §6.2 |
| G-B10 commit diff vs served diff | adopted | §6.5 |
| G-B11 P469 undescribed | adopted: red test named | §8 |
| G-B12 `request_usage` field | adopted: named | §4.1 |
| G-B14 (scope) harness reuse for later entries | adopted as a non-goal note | §15 |
| C scope: B8 / B6 input contract | adopted (within the goal) | §12 |
| C scope: pre-launch census receipt | folded into the entry checkpoint | §3 |
| C simplification: fold the dry leg into the pilot gate | adapted: replaced by a pre-freeze rehearsal (catches integration bugs before v8 instead of after) | §1 |

Acceptance criteria changed (v1 had none) → round 2.
