Reviewed read-only at commit `017768f4af5f95483f974645439c4a3ad811821b`.

The P297 review and fixture are absent from that commit; I read them from the parked local branch `p297-uncertain-gone`, as directed by `docs/handoff.md`.

## Findings

P1 — blocker — Proposal 2’s rescan does not close P297 U1  
Evidence: `benchmark/bench/proc_guard.py:344-351`, `687-715`; parked review `benchmark/chains/c147/reviews/p297/round1.cursor-gpt-5.6-sol-high.md:1`.

Scenario: an unreadable parent forks, exits, and the child reparents to PID 1. The extra scan may find the child, but `cleanup()` merely records a young untracked PID-1 process as a reasonless orphan at `712-715`; it neither kills it nor sets `uncertain`. That child can affect the next attempt, exactly the silent contamination U1 identified. `_processes()` can also omit it entirely on `AccessDenied`.

Recommended change: preserve parent-child edges from the listing that saw the unreadable PID. Do not clear if a listed child remains live unless it is independently proven protected/pre-existing, killed as tracked/path-attributed, or gone. A reasonless orphan is not sufficient clearance.

P2 — blocker — uncertainty is sticky, so the proposed immediate recheck only fixes one timing  
Evidence: `benchmark/bench/proc_guard.py:685-698`, `763-781`.

Scenario: the unreadable process still exists during the immediate recheck, so `uncertain=True` and an orphan are recorded. It exits milliseconds later. Subsequent passes cannot remove that reason or clear the aggregate Boolean, producing the same false abort.

Recommended change: track structured unresolved reasons keyed by PID/identity and reconcile them immediately before publishing `_status`. Remove only the vanished process’s reason; do not infer safety from the aggregate Boolean.

P3 — should-fix — the analogous handlers are not semantically interchangeable  
Evidence: `benchmark/bench/proc_guard.py:703-729`, `736-765`.

Scenario: the outer `TransportAbort`/`AccessDenied` handlers cover failures while reading identity, path, command line, order, or liveness. A successful `get(pid)` does not resolve all those failures. Conversely, tracked-process clearance is already independently determined by `_identity_state`.

Recommended change:
- Apply disappearance clearing only to a definitively identified per-process failure.
- For tracked identities, let the final `_identity_state` audit decide.
- Preserve global/persistent ordering failures such as C151 R12 as uncertain.
- Do not treat “fresh `Process` object constructed” as proof of existence.

P4 — should-fix — PID plus create time is sufficient only under a narrower contract  
Evidence: `benchmark/bench/proc_guard.py:335-339`, `581-593`; `docs/box-notes.md:22`.

Scenario: the PID is reused between listing and recheck. PID existence alone confuses the replacement with the vanished process; clearing it without rescanning may ignore the replacement.

Recommended change: capture the original `(pid, start_time(p))`, then compare it with a freshly validated process using the existing `start_time()` helper. A mismatch proves only that the original identity is gone; the replacement must still pass through a new normal scan. If the original identity was never readable, only definitive `NoSuchProcess` can clear it.

P5 — should-fix — one extra pass is not a defined convergence rule  
Evidence: `benchmark/bench/proc_guard.py:687-733`.

Scenario: another PID vanishes during the extra pass. A literal “one extra pass” can terminate without ever observing a clean snapshot.

Recommended change: require one clean pass after the last vanished candidate, with a small bounded retry count. Exhaustion remains uncertain. This still cannot prove that no process forked after the snapshot; the module already acknowledges that residual at `proc_guard.py:1-5`.

P6 — should-fix — monitor precedence needs the complete ordering contract tested  
Evidence: `benchmark/bench/proc_guard.py:766-785`; parked P297 review line 3.

Moving `self.failure` before the uncertainty raise is correct. The required final order should be:
1. Publish `_status`.
2. Raise `container_failure` as today.
3. Raise process-monitor failure.
4. Raise remaining cleanup uncertainty.
5. Raise surviving attributed processes.

Tests must assert both the exception and the written status. Also retain a container-plus-monitor test so the requested existing container precedence is not accidentally changed.

P7 — should-fix — the proposed fixture “replay” cannot reproduce the race  
Evidence: `docs/handoff.md:35-43`; the fixture is absent from commit `017768f4` and contains only the resulting manifest.

Scenario: a test loads the JSON and validates fields, but never exercises list → unreadable read → exit → recheck → child reparenting. It passes while `ProcessGuard` remains wrong.

Recommended change: land the fixture for receipt regression, but add an event-script fake for the actual process-observation sequence. Do not call the JSON-only test a replay of `cleanup()`.

P8 — should-fix — `--retry-errors` can silently discard an operator resolution under Proposal 1  
Evidence: `benchmark/bench/answer_key.py:113-125`; `benchmark/web_audit.py:168-170`.

Scenario: an `audit_error` has a valid operator resolution to `generic`. Its stored label remains `audit_error`, so `--retry-errors` re-audits it. If the new-version retry errors or returns a different label, the latest record replaces the resolved result and changes `strict_n` or cheat handling.

Recommended change: retry only unresolved `audit_error` records. Require a separate explicit option to re-audit an operator-resolved record.

P9 — should-fix — version-probe failure still exits successfully with unusable records  
Evidence: `benchmark/web_audit.py:159-164`, `176-203`, `208-215`; `benchmark/bench/answer_key.py:92-102`.

Scenario: the auditor version probe fails. `audit_rows` appends `audit_error` records with `auditor_version=None` and exits successfully, but `_valid_audit` rejects them. Scoring reports `missing`, hiding that the audit command itself failed.

Recommended change: fail nonzero before auditing or appending anything when the version cannot be obtained. The proposed “empty recorded version rejected” rule otherwise makes these records intentionally unusable.

P10 — nit — use separate lookup and full-record keys  
Evidence: `benchmark/bench/answer_key.py:105-132`; `benchmark/web_audit.py:168-183`.

Using one helper named `audit_record_key` after removing version obscures that version remains part of provenance and resolution matching.

Recommended change: introduce `audit_lookup_key` without version and retain an explicit full provenance key or explicit `record["auditor_version"] == base["auditor_version"]` check for resolutions.

## Open-question answer

PID plus `start_time()` is adequate for this repository’s process-identity contract if the original identity was captured and the replacement is rescanned. Raw PID existence is not adequate.

The proposed extra rescan is not sufficient for U1. Cleanup should refuse when a vanished unreadable PID had a previously listed child that remains unaccounted for. It need not refuse if every such child is independently proven gone, protected/pre-existing, or cleaned.

## Verdicts

Proposal 1: **cleared after fixes P8, P9**.

Proposal 2: **not cleared** because P1 and P2 can respectively permit silent cross-attempt contamination and retain false aborts.

## Tests to add

Proposal 1:
- Resolved `audit_error` is not retried by `--retry-errors`.
- Version-probe failure exits nonzero and appends nothing.
- Two versions with different labels select the latest deterministically.
- Correct-version resolution accepted; mismatched-version resolution ignored.
- CLI bump causes no auditor call.
- Probe functions raise on web-bearing rows, yet historical audits score.
- Real P223 cells remain final with every CLI absent.

Proposal 2:
- Immediate `NoSuchProcess` clears only that reason.
- Process alive at first recheck but gone before final reconciliation clears.
- Still-existing unreadable process remains uncertain.
- PID reuse rescans and classifies the replacement.
- Previously listed child reparents to PID 1 and remains live: cleanup refuses.
- Tracked reparented child is killed and reported.
- Repeated vanish events require a clean pass or end uncertain.
- Monitor failure plus uncertainty raises monitor failure after publishing status.
- Container failure still precedes monitor failure.
- Deterministic event-script reproduction of the P297 race, plus fixture receipt validation.
