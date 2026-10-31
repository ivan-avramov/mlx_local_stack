# P585 — cold reviews (opinion round 1, verify round 2; C265)

Member: `sol`, cursor-agent, `gpt-5.6-sol-high`, context `briefed`, user instructions unconfirmed; both exit 0.

**Round 1 (opinion)** on v1 — a `_cmdline(p)` helper at the five `cmdline()` sites only (the narrowing of the approved "every per-process
read" to the failing read, assumption A1 "only `cmdline()` raises it", stated in the brief): NOTHING OF SUBSTANCE. The narrowing was
then flagged (operator side note) and widened to v2 — a `psutil.Process` subclass whose reads convert, the default scan converting
psutil's cached objects in place.

**Round 2 (verify)** on v2:

| # | Finding (sol) | Severity / evidence | Disposition |
|---|---|---|---|
| V1 | `Process.__init__` reads `create_time` before any subclass method; `process_iter()` constructs base objects first: a construction-time SystemError still escapes lookup and scan | major / confirmed (reproduced) | **Adopted (v3)**: the default lookup converts a construction SystemError to AccessDenied; the default scan builds each process from `psutil.pids()` itself and skips one it cannot construct for that tick (as a process mid-exit), never ending the tick. |
| V2 | `psutil.Process().parents()` at guard init is not covered | major / confirmed | **Declined**: the probe's own ancestor chain (stable); an AccessDenied there already ended guard construction before this change — the failure mode is unchanged, not introduced. |
| V3 | caller-supplied `scan` / `get` (the tests' `FamilyScan`) bypass the subclass | major / confirmed | **Adopted by design (v3)**: the conversion now lives in the guard's handlers (`self._denied = (AccessDenied, SystemError)` in all 17 except clauses, SystemError in `_transient`), so it holds for any scan / lookup; production passes none. FamilyScan's internal unguarded read is a test fixture (declined). |
| V4 | the generated wrappers drop psutil's `cache_activate` / `cache_deactivate`; mutating psutil's cached objects breaks `oneshot()`, `repr()` and later `process_iter(attrs=…)` elsewhere | major / confirmed (reproduced) | **Adopted (v3)**: no subclass, no wrapper, no mutation of psutil objects; regression test (`oneshot()`, `repr()`, `type(p) is psutil.Process` after a guard scan). |

v3 was not re-reviewed (the verify is the work item's last dispatch; a defect a verify finds opens no further one): red-first tests
(8; 7 red on HEAD, the eighth a regression guard) and the B2 / T3 / M64 / M62 / guard suites.
