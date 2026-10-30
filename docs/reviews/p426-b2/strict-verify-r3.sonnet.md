**Round-2 findings**

1. **Resolved.** `Scrub` now has a `secrets` field (`p426_harvest.py:56`, `repr=False`, `compare=False`). `_publish_records` builds `Gate(scrub, scrub.secrets)` (line 959). `BoxSeqOps.publish_dossier` and `publish_run_files` pass `_credentials()` into the scrub (`p426_wave2.py:885-905`). `_credentials()` calls the same `load_credentials` as the leg harvest. The sources are the machine config, the two worktrees' `.env` files (set in `main` at line 979), the environment and the token files. An unreadable or unparseable source raises `HarvestError`, so nothing is published unscanned. I traced the code and did not run it.
2. **Resolved.** `_publish_records` is called with `require_self_hash=True` for run files, and only `sequence.json` is exempt (`p426_harvest.py:974, 1040-1041`).
3. **Not verified.** I did not read `verify_existing_amendment` itself. I did confirm that `run` and `makeup` call it before any leg (`p426_wave2.py:759-760`).
4. **Resolved.** `republish_dossiers` runs on resume (line 761). It skips records already marked `published`, so republishing is idempotent. `publish_dossier_or_stop` turns any failure into `Stop(4)`. A rehearsal publishes nothing.
5. **Resolved.** `_expands` (`p426_secrets.py:55-75`) treats `$` and a backtick as expanding unless single-quoted or backslash-escaped, and stops at a real comment. A credential-keyed assignment that expands raises `SecretsError` naming the key only (lines 94-96). A literal `$` inside double quotes also refuses, which fails closed and is acceptable.
6. **Declined, and I accept it.** A DNF item is already scored a failure. The leg-level rule (`p426_freeze.py:159`) still requires at least one judgeable request on the leg, so a short-request DNF cannot make an ON leg look engaged without evidence.

I found no new defects in the parts I read: the secrets and publication path, plus the sequencer's publish and exit-code handling. I did not read `verify_existing_amendment`, the pilot gate, locks, hooks, the receipt or the legacy goldens, so I make no claim about them.

NOTHING OF SUBSTANCE
