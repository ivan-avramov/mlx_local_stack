Reviewed current `main` at `459ee908`, a docs-only descendant of `50ee82ae`; relevant benchmark code remains unchanged from `4849a2ae`.

## Round 1 closure

- R1 — NOT CLOSED. §2 correctly splits P389 and locates the gate after hydration, but its predicate misses F9 accepted/exhausted stops, and missing-receipt recovery is undefined (R11–R12).
- R2 — CLOSED. §1 records orphan evidence and a canonical receipt hash in ordinary incidents, backfills pre-spawn incidents, and avoids redundant attempt fields.
- R3 — CLOSED. §1 blocks every reason-bearing record independently of `uncertain` and specifies the actual reasonless record keys. Numeric strictness still needs R10.
- R4 — CLOSED. The allowance is policy-specific; default and tg1 behavior remain unchanged, with A7 documentation updated.
- R5 — CLOSED. §1 now covers resume, pre-spawn backfill, DNF/sidecar/archive propagation, malformed records, tg1, and exact evidence assertions. Add R10–R12 cases.
- R6 — CLOSED. §3 honestly abandons the inadequate short-cycle study.
- R7 — CLOSED. No IID rule-of-three or chain-risk inference remains. The unsupported “thousands” estimate should nevertheless be removed (R14).
- R8 — CLOSED as a reframing. §3 no longer claims that a post-hoc classifier can validate a study; it accepts the residual risk. Its proposed recurrence snapshot still overclaims attribution (R13).
- R9 — CLOSED. §3 correctly separates path-only attribution, immediate `TransportAbort`, reconciled unreadability/vanished children, and convergence/overflow; it also removes the file-indexing misconception.

## New findings

R10 — Severity: MEDIUM; Section: §1 validator/tests  
Problem: The production reasonless shape does match the plan: the sole emitter in `proc_guard.py:1069–1072` produces exactly `pid`, `create_time`, and `argv`; all other orphan paths add `reason`. But “create_time: number” could admit booleans, non-finite values, zero, or negatives, and the tests do not reject non-string `argv` members.  
Fix: Require `type(pid) is int and pid > 0`; `type(create_time) in (int, float)`, finite and positive; and `type(argv) is list` with every element exactly `str`. Hash with an explicit canonical recipe using sorted keys, compact separators, and `allow_nan=False`. Test each rejected form.

R11 — Severity: BLOCKER; Section: §2 P389 predicate and placement  
Problem: The proposed “stop that implies rerun/retry” predicate covers pre-spawn and cheat, but misses F9 accepted/exhausted stops. `salvage_hook_stops()` can turn a partial accepted/exhausted stop into `hook_stopped`, after which the tail launches in another invocation; a complete one permits the next leg. Both can therefore bypass A7. Waiting until salvage succeeds is also wrong: quarantine preserves cheat/pre-spawn effects and still leads to another launch.  
Fix: After `hydrate_running()` and before `salvage_hook_stops()`, gate every persisted stop except `unclear`; include pre-spawn, cheat, accepted, and exhausted, regardless of whether row-prefix salvage later succeeds. Add F9 partial/full and unsalvageable-prefix tests.

Placement should be:

- Ordinary incident: validate and add evidence inside `record_incident()` before append/write.
- Live pre-spawn: backfill after `require_certain_cleanup()` at approximately line 1777 and before `recover()` at line 1778.
- Resume pre-spawn: gate and backfill after hydration at line 1023, before salvage at line 1026; assert exactly one matching incident by invocation, slot, load, generation, and `pre_spawn=True`.

R12 — Severity: HIGH; Section: §2 missing receipt  
Problem: Refusing automatic resume on a missing receipt is correct: cleanup cannot be inferred. It does not break every crash—ordinary unsalvaged crashes still quarantine—but it permanently blocks persisted-stop crashes in that out-root. “Verify the box and clear by hand” names no state transition or supported command; checking the box cannot manufacture the missing receipt.  
Fix: Pre-register one explicit outcome: either the out-root must be abandoned, or add an operator-authorized clearance transaction that durably records the invocation identity, missing receipt, leftover/lineage snapshot, and acknowledgement before allowing continuation. Never silently treat absence as clean.

R13 — Severity: HIGH; Section: §3 P388 snapshot  
Problem: A chain-side snapshot occurs after cleanup. The uncertain process may already be gone, or its PID reused, so it cannot guarantee that “a recurrence is attributable.” Reading lineage from a reused PID could actively misattribute it.  
Fix: Record receipt identity plus current identity state: `same`, `gone`, `reused`, `unreadable`, or `sentinel`; only capture ppid/session/cwd/argv when create-time proves the same process. Describe this as best-effort evidence, and reopen P388 on any recurrence, including indeterminate ones.

R14 — Severity: LOW; Section: §3 study estimate  
Problem: “Thousands of item-equivalents” has no stated chain-risk threshold, effective sample-size assumption, or correlation model—the exact omissions identified by R7.  
Fix: Remove the estimate, or label it as a hypothetical calculation with explicit assumptions. The fail-closed operational argument is sufficient for recommending no study.

VERDICT: AGREE WITH CHANGES R1,R10,R11,R12,R13,R14
