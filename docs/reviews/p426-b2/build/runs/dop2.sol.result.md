P1 — Location: §6.5; §16.1 `allowed_env_differences`  
Severity: blocker  
Evidence: confirmed (spec trace)  
Problem: R1’s observed environment diff becomes the allowed-difference list without any rule restricting it to known non-behavioural differences. This makes the proof circular: an unintended arm difference observed during rehearsal is automatically permitted in production pairs.  
Failure scenario: R1’s ON probe inherits `FEATURE_X=1` while OFF does not. The difference is frozen as allowed, every later pair passes, yet the arms differ by more than MTP state.  
Proposed change: define a closed, reviewed allowlist in the specification. R1 must prove its observed diff is a subset of that list; it must never generate permissions from observations.

P2 — Location: §6.4–§6.5; §16.1 arm-equality receipt  
Severity: major  
Evidence: confirmed (schema trace)  
Problem: C238 requires credential-key presence to be compared per process, but `credential_keys: [key]` records only a global list. It loses whether each key appeared in the router, worker, or probe.  
Failure scenario: arm A has `API_TOKEN` only in the router and arm B only in the probe. Both receipts contain `["API_TOKEN"]`, so the pair passes despite unequal process environments.  
Proposed change: use `credential_keys: {router: [...], worker: [...], probe: [...]}`, or retain each key in its process environment with a `"<credential>"` sentinel.

P3 — Location: §6.5; §16.1 pair dossier; §16.5–§16.6  
Severity: blocker  
Evidence: confirmed (spec trace)  
Problem: attempts are versioned as `.a<n>`, but the immutable dossier remains `pairs/<pair>.json`. A completed INVALID pair consumes that path, so an operator-authorized rerun cannot publish a dossier binding the replacement attempts.  
Failure scenario: the second s1 leg fails its pair gate and an INVALID dossier is written. Attempts `.a2` then pass, but exclusive creation of the same dossier path fails; B8/B6 can never consume the valid pair.  
Proposed change: version dossiers by pair attempt, such as `<pair>.p<n>.json` or a name derived from both attempt IDs, and have `sequence.json` identify the selected dossier.

P4 — Location: §16 introduction, §16.1 `log_bounds.json`, §16.5 `sequence.json`, watcher receipt  
Severity: major  
Evidence: confirmed (literal contract contradiction)  
Problem: “all records” are exclusive-created and self-hashed, but several specified records must mutate or append. `log_bounds.json` starts with null end offsets and is finalized later; `sequence.json` changes after every leg; `watch.jsonl` appends. Their schemas also omit `sha256`.  
Failure scenario: a literal implementation exclusive-creates `sequence.json` before leg one and cannot persist subsequent state, making resume select or relaunch the wrong attempt. Another implementation overwrites it and violates the stated immutability contract.  
Proposed change: explicitly classify immutable self-hashed records versus mutable atomic state files and append-only journals. Define integrity and crash-recovery rules for each, and include `sha256` in every schema that is actually self-hashed.

P5 — Location: §11.2 staged publication  
Severity: major  
Evidence: confirmed (crash sequence traced)  
Problem: destination directories are renamed into final locations before `HARVEST.json` is written, but retry only discards an incomplete staging directory. A crash can therefore leave an incomplete final destination that is neither a valid completed harvest nor a discardable stage.  
Failure scenario: `main` is renamed into place, the process crashes before publishing evidence or `HARVEST.json`, and retry encounters an existing final destination with no defined resume or cleanup rule.  
Proposed change: define an attempt-level publication marker and require retry to verify and remove or resume only that attempt’s incomplete final directories. Specify publication order and the single durable commit point.

P6 — Location: §11.2; §16.4 Harvest  
Severity: major  
Evidence: confirmed against `arm_runner.py` and the specified schema  
Problem: inventory now includes run/evidence directories outside the leg root, but `HARVEST.json.source` must be relative to the leg root. The contract cannot name those sources unambiguously. It also omits the frozen-record directory, although legs depend on v8/amendment records outside the allowed roots.  
Failure scenario: two external roots both contain `manifest.json`; either they collide in `source`, or absolute paths are used contrary to §16.4. A referenced timeout amendment lies outside every permitted root and makes harvest fail or remain unharvested.  
Proposed change: use typed source identities such as `leg:<rel>`, `run:<run-id>/<rel>`, `evidence:<run-id>/<rel>`, and `record:<rel>`. Add the frozen-record directory to the sequencer-level harvest and publish it under a defined run destination.

P7 — Location: §11.3; §16 introduction and §16.1 record schemas  
Severity: major  
Evidence: confirmed (spec trace)  
Problem: every staged file is scrubbed, while structured records are self-hashed over their pre-scrub JSON. Several schemas contain machine-local paths (`off_worktree`, `on_worktree`, `out_root`, log paths). Scrubbing changes their bodies without updating their embedded self-hashes.  
Failure scenario: the published v8 record replaces an absolute worktree path with `$STACK_WORKDIR`; B8 recomputes its self-hash and rejects it, although `HARVEST.json` verifies the published bytes.  
Proposed change: require portable/canonical paths when records are first created so structured main artifacts are byte-preserving under scrub. Alternatively, define a published self-hash recomputation scheme while preserving the original hash in `HARVEST.json`.

P8 — Location: §16.1 pair dossier  
Severity: major  
Evidence: confirmed (schema ambiguity)  
Problem: parallel arrays `attempts`, `receipts_sha256`, and `harvest_sha256` have no arm labels or specified ordering. Chronological order differs by session: s1 runs OFF→ON, while s2 runs ON→OFF.  
Failure scenario: a verifier interprets array position zero as OFF. That is correct for s1 and reversed for s2, causing the reported ON−OFF delta to have the wrong sign.  
Proposed change: key dossier members by arm, for example `arms: {off: {attempt, receipt_sha256, harvest_sha256}, on: {...}}`.
