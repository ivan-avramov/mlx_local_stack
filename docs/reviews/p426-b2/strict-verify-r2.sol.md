P1 — Resolved: `p426_dnf` now records `load`, and `attempt` comes from the `<leg>.a<n>` out-root.

P2 — Resolved: existing dossiers are recomputed and checked against current receipts and harvests.

P3 — Resolved: KV/TQ exemptions use an exact committed allowlist.

P4 — Resolved: DNF requests are engagement-checked; unjudgeable ON items/legs become `unengaged`.

P5 — Resolved: in-flight failed/unaccounted cases require structured in-flight evidence.

P6 — Not fully resolved  
Location: `benchmark/bench/p426_wave2.py:333-360,632-680,713-733`  
Severity: major  
Evidence: confirmed  
Problem: Existing amendments are reverified only while replaying pilot legs in `run`. The `makeup` command loads and uses an existing amendment without checking its `pilot_dossier_sha256` against the selected pilot dossier.  
Scenario: A resealed amendment with a stale dossier link or altered timeout values is accepted by `makeup`, producing evidence under an amendment that the current pilot pair never authorized.  
Proposed change: Reverify the amendment against the selected pilot attempts and dossier before every command that consumes it, including `makeup`.

P7 — Resolved: R1-off, R1-on, R2 and R3 are bound to the current rehearsal manifest, expected names and injections.

P8 — Not fully resolved  
Location: `benchmark/bench/p426_harvest.py:950-1024`  
Severity: major  
Evidence: confirmed  
Problem: Leg-root immutable records and DNF sidecars are now checked, but `publish_run_files` calls `_publish_records(..., require_self_hash=False)`. Consequently, frozen immutable records without `sha256` are accepted alongside `sequence.json`.  
Scenario: A v8 base or amendment loses its hash before final publication; the public run directory receives a non-self-hashed immutable record that consumers cannot verify.  
Proposed change: Require valid self-hashes for every run file except the explicitly mutable `sequence.json`.

P9 — Resolved: successful sequencing now depends on run-file publication; failure exits 4.

P10 — Resolved: a manifest run ID resolving to zero or multiple directories fails harvest.

P11 — Resolved: `ready_sha256` is now the ready record’s self-hash.

P12 — Resolved: shell comments/quoting, quoted or JSON bearer headers, and non-UTF-8 evidence are handled as specified.

P13 — Additional finding  
Location: `benchmark/bench/p426_wave2.py:567-595,937-953`  
Severity: major  
Evidence: confirmed  
Problem: Pair-dossier publication occurs only when the sequence has no pair record, and the pair record is saved before publication. Publication exceptions are not converted to exit 4.  
Scenario: The first publication fails transiently. The process crashes after recording the pair; on resume, the dossier is verified locally but never published because the pair record already exists. Sequencing can finish with `sequence.json` naming a missing or stale public dossier.  
Proposed change: Idempotently publish every verified dossier on resume, publish before committing the pair state, and map publication failures to exit 4.

P14 — Additional finding  
Location: `benchmark/bench/p426_harvest.py:950-1024`; `benchmark/bench/p426_wave2.py:684-704,756-760`  
Severity: blocker  
Evidence: confirmed  
Problem: Run-file and dossier publication instantiate `Gate(scrub, {})`, omitting the required exact credential-value scan. `sequence.json` includes unrestricted operator text such as `--rerun-reason`.  
Scenario: A rerun reason contains a private token without a recognized prefix. Leg harvest would reject that exact configured value, but run-file publication does not know it and publishes the token to the public repository.  
Proposed change: Supply the same in-memory credential values and sources used by leg harvest to dossier/run-file publication, scanning original and scrubbed bytes before staging.
