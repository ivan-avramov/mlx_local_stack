1. Location: §1, §2, §10.1–10.3, acceptance criterion 3  
Severity: blocker  
Problem: The freeze lifecycle is circular. The pre-freeze rehearsal must use `--p426`, but `--p426` refuses a missing frozen record and only v8 is defined. Pilots likewise require v8, while v8’s timeout amendment is derived from those pilots. No pilot deadline exists before that amendment.  
Failure scenario: A literal implementation cannot launch the rehearsal, or creates an incomplete v8 that acceptance criterion 3 rejects. A wedged pilot has no overrun transition.  
Proposed change: Define three immutable, hash-linked artifacts: a rehearsal manifest, `v8-base` accepted by pilots, and a timeout amendment required by later legs. Define an independent pilot deadline.

2. Location: §5.1, §5.3, §12  
Severity: blocker  
Problem: `p426_dnf` is excluded from scoring, contradicting AGENTS.md’s overriding requirement that `acc_strict@budget` include DNF. Reporting DNF counts beside a completed-only accuracy does not remove the bias.  
Failure scenario: ON completes 41 stronger items and has two DNFs while OFF completes all 43; ON’s primary accuracy uses the smaller denominator and can incorrectly support shipping.  
Proposed change: Compute the ranking metric over every planned slot, counting DNF as a non-success without fabricating a normal row or labelling it a strict failure. Otherwise obtain an explicit operator-approved exception to AGENTS.md.

3. Location: §4.3, §5.1–5.4  
Severity: major  
Problem: The `Request failed` truth table misclassifies both valid strict failures and eligible DNFs. A healthy `dropped_stream` normally produces trailing `stream_closed_before_completion`, but DNF requires zero failed lines. Conversely, a gate kill can occur between requests and produce zero failed lines, while the spec requires exactly one. `client_inactivity` also does not set `requests_at_kill`, and the serialized field is actually `gate.requests_completed_at_kill`.  
Failure scenario: A genuine dropped-stream incident stops the run systemically; a normal budget/loop stop at a request boundary also becomes systemic.  
Proposed change: Define exact cases from structured termination evidence: allow zero failures at a request boundary; allow one trailing stream-close failure when an active stream was terminated, including eligible transport DNFs; use the actual row field and exact outcome vocabulary.

4. Location: §4.2–4.4, §15 assumptions  
Severity: major  
Problem: The specification assumes serial requests but never verifies non-overlap. Per-request MTP counters are derived from drafter-global snapshots and are not trustworthy if requests overlap. Counts and token totals can still reconcile.  
Failure scenario: Two requests from one item overlap; both log records and worker totals match, but draft counters are double-counted or assigned to the wrong request, corrupting engagement and acceptance signals.  
Proposed change: Require every `Request started` line to show `in_flight=1`, prohibit a second start before the preceding terminal line, and add an overlap red test.

5. Location: §3 ready checkpoint, §5.2  
Severity: major  
Problem: Systemic failures are checked at `ready`, but `invalidate(reason)` is after-barrier only. The existing before-hook vocabulary can only accept or declare a transport incident.  
Failure scenario: Lifecycle or registry drift is detected at `ready`; a helper either misclassifies it as DNF or raises while the probe remains blocked waiting for `.go`/`.stop`.  
Proposed change: Permit a persisted systemic `invalidate(reason)` at both ready and done barriers, always emitting `.stop` and completing verified cleanup.

6. Location: §3, §4.1–4.5, §5.2–5.4  
Severity: major  
Problem: DNF classification needs the ready-time log cursor and worker snapshot, but no durable ready record is required. A transport-aborted item never reaches `done`, where `items/<slot>.json` is written.  
Failure scenario: The probe aborts mid-item; the chain continues using in-memory state, but the resulting DNF dossier cannot independently prove its log window or worker delta. A crash loses the baseline entirely.  
Proposed change: Persist an immutable ready record before `.go`; finalize it into the item/DNF record after settle. Missing ready evidence must be systemic.

7. Location: §5.4, §13 tests  
Severity: major  
Problem: Real tg1 currently does not stamp transport causes: `OpencodeArm.transport_cause` only returns one in M64 mode. The proposed topology test uses a fake probe, so all specified tests can pass while real P426 transport failures lack a cause and become systemic.  
Failure scenario: A real connection failure has certain cleanup and a healthy worker but no `transport_abort.cause`; the chain stops instead of recording DNF and continuing.  
Proposed change: Specify the concrete P426 adapter mode/flag that enables cause stamping and test a real tg1-adapter failure through manifest creation.

8. Location: §6.4  
Severity: major  
Problem: Literal pair equality cannot pass. Only worktree roots are normalized, while each arm deliberately has a different out-root and `ChainOps.env_base()` places that path in `TMPDIR`. Interpreter/import paths are also not uniformly normalized.  
Failure scenario: Correct ON and OFF legs differ only by MTP plus their evidence namespaces, yet B8 rejects every pair because their `TMPDIR` values differ.  
Proposed change: Canonicalize `<WT>` and `<OUT>` in every path-valued field and define the complete allowed delta as flag/value pairs. Compare an explicit behavior-affecting environment allowlist rather than the full inherited environment.

9. Location: §6.4, §12–§15  
Severity: major  
Problem: Runtime arm equality is deferred to B8, which is a non-goal of B2; the sequencer has no stated pair gate. Lockfile hashes and import paths also do not prove equal installed package contents.  
Failure scenario: One arm’s ignored venv file or installed package differs. Both legs are marked VALID and later sessions run; only a future B8 invocation notices, contrary to systemic-stop-at-once.  
Proposed change: Compare paired receipts immediately after the second arm and stop on mismatch. Include executable/package inventories or use one verified immutable environment shared by both arms.

10. Location: §6.4, §11.2–11.3  
Severity: major — sensitive data boundary  
Problem: Publishing unsalted SHA-256 values of secret environment values creates offline verifiers for passwords or other low-entropy secrets. The secret scanner will not reject those hashes.  
Failure scenario: A password-valued environment variable lands on public `main` as a stable SHA-256 digest and can be dictionary-tested.  
Proposed change: Compare secret values only in memory and publish key names plus same/different verdicts, never value digests. Scan both original and scrubbed bytes.

11. Location: §4.5, §11.2  
Severity: major — sensitive data boundary  
Problem: The destination policy puts raw A4/server logs, `RUNLOG.md`, stdout, and item JSON containing raw log lines on `main`. AGENTS.md requires raw transcripts and logs on `evidence`.  
Failure scenario: A scrubbed but still raw operational log is committed publicly to `main`, violating the repository’s overriding data-boundary rule even without a detected secret.  
Proposed change: Put all raw logs and stdout on `evidence`; retain only parsed structured summaries, hashes, and verdicts on `main`.

12. Location: §11.2, §13 harvest tests  
Severity: major  
Problem: A reference-driven closure can silently omit unreferenced crash artifacts and does not name barrier/control files such as `.ready`, `.go`, `.done`, `.continue`, `.stop`, `.ACK`, and `.CANCEL`. Those files prove barrier and stop behavior.  
Failure scenario: A crash leaves partial events or a `.stop` payload not referenced by `chain.json`; harvest succeeds while citable incident evidence remains only in scratch.  
Proposed change: Inventory every regular file under the leg root, require an explicit destination or exclusion reason, and define state-dependent presence rules for all barrier/control artifacts.

13. Location: §5.5, §7  
Severity: major  
Problem: Makeup input cannot represent the specified workload unambiguously. One makeup leg may contain duplicate item occurrences from s1 and s2, but each probe invocation has one `--seed-base`, and a plain item list cannot preserve occurrence identity.  
Failure scenario: The same item DNFs in both sessions; one occurrence is deduplicated or both run with the wrong seed.  
Proposed change: Define structured records `(session, language, item, seed, occurrence)` with duplicates allowed and deterministic partitioning into single-session/seed probe invocations.

14. Location: §9, §13 lock tests  
Severity: major  
Problem: Cross-lock acquisition order is unstated. Sequential “both directions” tests do not detect the check-then-acquire race.  
Failure scenario: The local gate checks `LEG.lock` before taking `RUNNING` while the chain checks `RUNNING` before taking `LEG.lock`; both checks pass and both workloads start.  
Proposed change: Require each actor to acquire its own lock first, hold it while checking opposing locks, and add a simultaneous-start race test.

15. Location: §4.4, §13 engagement tests  
Severity: major  
Problem: Engagement permits `draft_rounds >= 1`, `draft_n=0`, `draft_n_accepted=0`, which proves no proposal occurred. Integer types are also unstated.  
Failure scenario: Corrupt or degraded ON telemetry reports one round and zero proposed tokens; every engagement check passes although MTP did no work.  
Proposed change: Require integer `draft_rounds >= 1`, integer `draft_n > 0`, and integer `0 <= draft_n_accepted <= draft_n`, with a zero-proposal red test.