# Delivery 1f (same session): amend the frozen set for C238 and the round-2 review, and fix your own three test defects

Two specification changes since the freeze (`.b2-spec-c238-d2.diff` in this directory; the copy's spec is updated):
- **C238 (operator):** the cross-pair credential comparison is dropped — the receipt records credential KEYS per process (`credential_keys: {router, worker, probe}`), never values or hashes; no HMAC, no key pipe, no `--hmac-fd`; a sequencer restart between the two legs of a pair resumes the pair from the first leg's persisted receipt; no `voided/` records.
- **Round 2 of the design review ([d2]):** the pair gate's allowed list is closed in §6.5 (R1 only confirms a subset); pair dossiers are per pair attempt (`pairs/<pair>__off-a<n>__on-a<m>.json`), keyed by arm, published by `p426_harvest.publish_dossier`; run records by `publish_run_files`; three record classes (§16 intro); a single harvest commit point (§11.2); typed `HARVEST.json` sources; portable paths in `main` records; `p426_dnf` fields defined (`attempt` from the out-root name `<leg>.a<n>`); hooks `context=None`; `invalidate` has no slot disposition; `ops.harvest` returns `{rc, harvest_json, harvest_sha256}`; the occurrences file is unordered.

Do:
1. Amend every frozen and `add_` test and fixture that these changes contradict (e.g. drop `--hmac-fd` from every argv; the receipt's credential-key shape; the dossier name and shape; resume instead of voiding; the harvest return value and source keys), keeping what the specification supports, and add tests for the new rules (closed allowed list with R1 as a subset check, record classes, the commit point and retry, typed sources, portable records, the `p426_dnf` fields, `publish_dossier` / `publish_run_files`).
2. Fix your three test defects from the s1–s3 review: the s2 `drop` / `refuse` fixtures (the leading `not json` line), the s3 test that builds an invalid `tg1-p426` config, and the s0 check that missed the malformed fixture.
3. Run everything on the baseline (`../bin/run_stack_tests.sh`) — every support check must pass — and the frozen s1–s3 files on the s1–s3 candidate (`../bin/run_candidate_tests.sh`).

Report: the list of amended tests (file::test) with the reason for each; new tests; commands and summary lines verbatim; anything in the specification still wrong or contradictory.
