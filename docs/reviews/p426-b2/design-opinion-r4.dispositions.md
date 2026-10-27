# P426 B2 — design opinion after the review reset (operator, 2026-10-27) — dispositions

Spec v3.1 + C235 + C236 (`50ec18d1`) → v3.2 (changes marked [o4], not re-reviewed). Panel 2026-10-27 15:49–15:56Z, context `checkout`
(read-only copy at `50ec18d1`):

| Member | Runtime | Model | Session | Status |
|---|---|---|---|---|
| sol | cursor-agent `--mode ask` (user instructions unconfirmed) | `gpt-5.6-sol-high` | `be4b1213-4b9e-44b5-8bb6-feafd71ec3b0` | returned |
| glm | cursor-agent `--mode ask` (user instructions unconfirmed) | `glm-5.2-high` | `213f9785-e940-42f6-b739-909d8f9bba3c` | returned |
| sonnet | claude `-p`, `--setting-sources project,local`, Read/Grep/Glob | `claude-sonnet-5-5` | `f3204c69-5043-4d31-ae41-d90d34fde90a` | returned |

Shared: Claude Sonnet is the designer's vendor and arm B's implementer model. It reviewed the specification, not its own code.

| # | Finding (raised by) | Disposition | Why |
|---|---|---|---|
| 1 | Transcripts and run directories live under `$STACK_WORKDIR/opencode_transcripts`, outside the leg root that the harvest requires (sol P1, blocker) | **adapted**: the inventory roots are the attempt's leg root plus the run and evidence directories its own manifests name | Confirmed in `arm_runner.py:1038–1056` and `arm_opencode.evidence_root`. With the spec as written, every leg's harvest would fail. Fixing it on the harvest side leaves the probe unchanged. Original. |
| 2 | The pair dossier is written after both harvests and harvested by none (sol P2, blocker) | **adopted**: published through the harvest to `wave2/pairs/` | B8 / B6 need it, and AGENTS.md requires citable files to be committed. Original. |
| 3 | §4.3's count-and-order equality contradicts `completed_unaccounted`; a DNF has no row session; the pairing key is unnamed (sol P3, glm F5) | **adopted**: positional pairing named, per-outcome equality, DNF session from the abort manifest | Without it a supported DNF case is ruled systemic. |
| 4 | A kill or `client_inactivity` with an in-flight request the server completed has no row (sonnet F2) | **adopted**: symmetric `completed_unaccounted` row | The same timing occurs for scored strict fails; otherwise a legitimate item stops the leg. |
| 5 | The cross-pair credential comparison has no mechanism (sol P4, sonnet F1) | **adapted**: HMAC-SHA256 under a per-pair random key held only by the sequencer and passed through an inherited pipe | "Compared in memory" across two processes could not be built. A discarded random key keeps the recorded values non-invertible and unlinkable, so the protection holds. **Shown to the operator** (it changes "not even hashed"). |
| 6 | A restart between paired legs collides with fixed roots and destinations; a voided first leg is orphaned (sol P5, glm F4) | **adopted**: attempts `<leg>.a<n>`, dossier-bound pairs, harvested `voided/`, pushes per pair | Without it the specified restart rule cannot run, and B6 / B8 could consume an orphan. |
| 7 | The harvest is not crash-atomic or resumable (sol P6) | **adopted**: staged, rename-published, `HARVEST.json` last, idempotent | A crash mid-harvest would otherwise block the leg's evidence permanently. |
| 8 | A standalone chain can run during the sequencer's idle gap (sol P7, against the settled C227) | **declined** as a residual; **shown to the operator** | It needs a hand-launched chain during a wave, which is outside the supported conditions. C227 is settled. |
| 9 | A single engagement miss invalidates the leg (sonnet F3) | **adapted**: the rule is kept; R1 records `(generated_tokens, draft_rounds)` for every ON request, and a miss there stops v8 | glm confirmed the code basis, and the designer re-checked it at S′ `c688e722` (`mtp.py:716`, `common.py:399–401`). A miss on real traffic means the ON arm did not engage, which the goal treats as systemic. R1 provides the calibration. |
| 10 | An abort before the slot's `ready` is ambiguous (sonnet F4) | **adopted**: systemic | There is no window to reconcile. |
| 11 | Environment differences the pair gate does not list could halt the first pair (sonnet F5) | **adopted**: R1's full environment diff freezes the lists in v8 | They are measured once rather than guessed. |
| 12 | Dangling references: §6.6 vs §6.7, "§11 restore" (sonnet F6) | **adopted** | The restore is the P426 plan's §11. |
| 13 | The settle bound is derived from Python pilots only, and Go is never piloted (glm F1) | **adopted**: the bound includes the S′ rehearsal (P499) and the M63 / P456 Go walls | A long Go prefill would otherwise be a false systemic. |
| 14 | Symlinks in a model's final tree fail the harvest (glm F2) | **adapted**: recorded and excluded inside final trees; failure elsewhere | Model output may legitimately contain links. The r3 protection (no following, no copying) holds. |
| 15 | The make-up union includes INVALID legs; an early-stopped make-up leg is undefined (glm F3) | **adopted**: VALID-with-DNF legs only; `not_run` recorded | An INVALID leg is rerun, not made up. |
| 16 | `D` divides by zero (glm F6, sonnet F7 caveat) | **adopted** | Literal-implementation hazard. |
| 17 | `lsof` does not list loaded images (glm F7) | **adopted**: `vmmap` | Same reason. |
| 18 | The generic prediction default is unnamed (glm F8) | **adopted**: `generic_pred_s` = 250 s in `chain.json` | Two implementers would otherwise pick different values. |
| SR | Drop the full volatile key set (glm SR1); drop the duplicate client-sum comparison (glm SR2); record distributions (sonnet) | SR2 **adopted** (removal); SR1 **declined** (key names are diagnostics, not secrets); sonnet's request is covered by #9 | Removing a redundant mechanism is preferred to keeping one. |
