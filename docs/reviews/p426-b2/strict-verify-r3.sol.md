P1 — Prior finding 1: Resolved. Publication loads the configured credential sources into `Scrub.secrets`, and both publication paths pass them to `Gate`.

P2 — Prior finding 2: Resolved. All run files except `sequence.json` now require a present, valid self-hash.

P3 — Prior finding 3: Resolved narrowly. `run` and `makeup` call `verify_existing_amendment` before launching legs.

P4 — Prior finding 4: Resolved narrowly. Dossiers publish before state is saved; retries are byte-idempotent; publication exceptions produce exit 4.

P5 — Prior finding 5: Resolved. Credential assignments containing expandable `$` or backticks refuse without exposing the value.

P6 — Prior finding 6: Resolved by the settled clarification. DNF requests are counter-validated without a per-item engagement floor; the ON leg still requires at least one judgeable request.

P7 — Location: `benchmark/bench/p426_wave2.py:612-619,669-703,749-761`  
Severity: blocker  
Evidence: confirmed  
Problem: `republish_dossiers` publishes recorded dossiers without re-verifying them against current receipts and harvests. Amendment verification checks only the dossier’s file hash and the stored `sequence.json` PASS verdict.  
Failure scenario: after an earlier publication failure, a receipt changes while the dossier and amendment remain unchanged. `makeup` accepts the amendment, publishes the stale dossier, marks it published, and launches both legs. Unlike `run`, `makeup` never later calls `ensure_dossier` for the pilot pair. Public evidence can therefore certify records that no longer match the source receipts.  
Proposed change: before every resumed dossier publication, reconstruct its pair roots and recompute the receipt/harvest hashes, differences, and verdict using `verify_dossier`. Make amendment verification require that validated current dossier, especially for `makeup`.

P8 — Location: `benchmark/bench/p426_freeze.py:124-160`; `benchmark/bench/p426_harvest.py:638-659`  
Severity: major  
Evidence: confirmed  
Problem: DNF ledger entries do not require their corresponding ready record. Normal rows do, but the DNF branches only require the `.dnf.json` item record and sidecar.  
Failure scenario: a DNF ready record is lost after reconciliation. `classify_leg` can still grade the leg `VALID_WITH_DNF`, and the harvest can publish it without the worker-before snapshot and log cursor required to prove reconciliation.  
Proposed change: require and validate `items/<slot>.ready.json` for every ledger entry. For DNF entries, also compare the item record’s `ready_sha256` to the ready record’s self-hash.

P9 — Location: `benchmark/bench/p426_harvest.py:1002-1014`  
Severity: major  
Evidence: confirmed  
Problem: record publication follows a pre-existing `<destination>.stage` symlink. It writes through the link, verifies through it, then renames the symlink itself into the public destination.  
Failure scenario: `v8_base.json.stage` points to another file. Publication truncates that target and publishes a symlink instead of the validated JSON while reporting success.  
Proposed change: create staging files exclusively with `O_NOFOLLOW`, refuse any existing non-regular stage, verify with `lstat`, and verify the final destination is a regular file after rename.

P10 — Location: `benchmark/bench/p426_wave2.py:987-999`  
Severity: major  
Evidence: confirmed  
Problem: run-file publication failure only changes the exit code to 4 on the success path. If the sequence is already stopping with exit 1 or 3, the `finally` block logs publication failure but preserves the earlier code.  
Failure scenario: a pair gate stops with exit 1, while a configured secret in `sequence.json` makes run-file publication fail. The command returns 1, concealing that the run records were not published and violating the pinned exit-code contract.  
Proposed change: make any attempted run-file publication failure set the final result to exit 4 while retaining the original stop reason in the log.
