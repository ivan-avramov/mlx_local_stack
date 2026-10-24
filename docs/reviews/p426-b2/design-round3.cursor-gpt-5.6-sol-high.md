1. **Location:** §2, §4.1–§4.3, §5.2–§5.3  
   **Severity:** blocker  
   **Problem:** DNF items lack the client-side request evidence required for reconciliation. Current tg1 sets `OpencodeArm.report_gate_on_abort` only for M64, and even that gate report omits the full `request_usage` list. The listed probe edits add only P426 cause stamping and barrier policy.  
   **Failure scenario:** A `dropped_stream` abort occurs after two completed requests. The manifest has a cause but no per-request client usage, so the chain either accepts an unreconciled DNF or incorrectly makes it systemic.  
   **Change:** Require P426 abort manifests to persist `request_usage`, gate state, active request/message state, session ID, and kill-time termination evidence. Add real-adapter tests for boundary and in-flight aborts.

2. **Location:** §6.4–§6.5  
   **Severity:** blocker  
   **Problem:** Hashing each distribution’s raw `RECORD` cannot reliably compare these worktrees. `mlx-vlm` and `mlx-serve` are editable relative-path installs; editable metadata contains worktree-specific paths whose digests propagate into `RECORD`. Conversely, an installed file can be modified without changing `RECORD` itself.  
   **Failure scenario:** Correctly synchronized OFF and ON venvs fail every pair gate because their editable metadata differs; alternatively, mutated installed code passes because both retain the same `RECORD` file.  
   **Change:** Replace raw `RECORD` hashes with a canonical verified-content inventory: validate every recorded file digest, normalize editable metadata, and hash imported source trees, locks, and native libraries.

3. **Location:** §9  
   **Severity:** blocker  
   **Problem:** The own-lock-first protocol cannot satisfy the required “exactly one runs” race test.  
   **Failure scenario:** The gate acquires `RUNNING` while the sequencer acquires `SEQUENCER.lock`; each observes the other lock, releases its own, and both refuse. A barrier synchronized after acquisition deterministically yields zero winners.  
   **Change:** Add a shared arbitration lock that serializes acquisition, or permit zero winners. Define sequencer-to-chain lock ownership explicitly.

4. **Location:** §1 rehearsal requirements; §10.1  
   **Severity:** major  
   **Problem:** The positive rehearsal and injected-negative rehearsal are conflated. Only two rehearsal legs are defined, yet the pair must pass while one injected reconciliation mismatch must stop its leg.  
   **Failure scenario:** The injected arm is INVALID and incomplete, while v8 creation requires the rehearsal to have passed all listed checks.  
   **Change:** Define separate fresh-root runs: a valid OFF/ON pair, an expected-systemic mismatch run, and a real-kill run. Exclude negative runs from the positive pair gate.

5. **Location:** §3 entry checks; §6.4; §10.1  
   **Severity:** major  
   **Problem:** The specification verifies `pins.json` but not the live model artifacts it identifies. Wave 1 already rehashes target and drafter snapshots per leg.  
   **Failure scenario:** The target snapshot or tokenizer mutates between OFF and ON. Commits, registry, argv, and pair receipts still match although the arms execute different model bytes.  
   **Change:** At freeze and every leg, resolve the actual target/drafter snapshots and verify revisions and pinned file hashes.

6. **Location:** §6.4  
   **Severity:** major  
   **Problem:** Environment equality checks the full key set but values for only selected prefixes. `ChainOps.env_base()` passes the entire parent environment plus each worktree’s `.env`.  
   **Failure scenario:** Equal key sets carry different `HF_HOME`, `HOME`, proxy, certificate, locale, or `DYLD_*` values, changing artifacts or runtime behavior while the pair gate passes.  
   **Change:** Compare every non-secret value after canonicalization, with a closed list of permitted volatile differences.

7. **Location:** §6.5; §11.1; §12  
   **Severity:** major  
   **Problem:** The pair gate runs only after the second leg, too late for a systemic mismatch to stop at once, and no immutable pair-record lifecycle is defined.  
   **Failure scenario:** All 43 items in arm two run before its receipt mismatch is noticed. Arm one may already be harvested immutable, but §12 requires the pair verdict through each leg’s `HARVEST.json`.  
   **Change:** Compare receipts before item one of arm two. Create a separate immutable pair dossier referencing both leg-harvest hashes; B6/B8 should consume that rather than rewriting either leg.

8. **Location:** §6.4; §11.3  
   **Severity:** major — sensitive data boundary  
   **Problem:** Secret-key matching conflicts with recorded behavior keys and causes false positives. `TOKENIZERS_*` must be recorded verbatim but also matches `*TOKEN*`; values such as `false` or an empty credential placeholder would match ubiquitous output.  
   **Failure scenario:** `TOKENIZERS_PARALLELISM=false` makes harvest reject every JSON file containing `false`, or secret precedence silently removes a required equality value.  
   **Change:** Use a vetted credential-key classifier with explicit exclusions, ignore empty/placeholding values, and define secret precedence unambiguously.

9. **Location:** §4.3 failed-line table; §5.1  
   **Severity:** major  
   **Problem:** The DNF truth table assumes `connection` always occurs before a server request. The adapter maps every `provider.transport` error to `connection`, including established-stream resets. It also cannot represent a server completion lost before client accounting.  
   **Failure scenario:** The server starts or completes a request, then the socket resets. The healthy isolated incident has either a trailing failed line or one extra completion absent from `request_usage`; the specification incorrectly makes it systemic.  
   **Change:** Base classification on observed started/completed/failed state, or refine causes using whether the request reached the server. Permit one explicitly reconciled trailing terminal request for a DNF.

10. **Location:** §4.2; §11.1–§11.2  
    **Severity:** major  
    **Problem:** There is no durable whole-leg boundary for append-only logs. Ready cursors begin only at item barriers, while router stdout (`logs/main_model.log`) and pre-item server output live outside the leg root.  
    **Failure scenario:** A crash or failure during load/A4 loses the exact log range; harvest either omits diagnostic bytes or includes bytes from prior legs.  
    **Change:** Before router launch, exclusive-create boundaries containing path, device/inode, and offset for both logs; finalize after teardown and reject truncation or replacement.

11. **Location:** §11.2–§11.3  
    **Severity:** major — sensitive data boundary  
    **Problem:** Symlink handling is unspecified. Existing tg1 final-tree collection uses `is_file()` and `read_bytes()`, which dereference model-created symlinks before harvest sees them.  
    **Failure scenario:** An editable solution becomes a symlink to a local file; its target bytes enter a content-addressed object and can be published if they do not match known secret patterns.  
    **Change:** Use `lstat`, refuse symlinks and non-regular files, and require resolved sources to remain within explicit evidence roots.

12. **Location:** §3 checkpoints; §5.1; §8  
    **Severity:** major  
    **Problem:** In-run power failure is speed-only here, while C220 explicitly classifies a power-gate failure as systemic. “Before every invocation” also includes power, without saying whether failure stops or merely marks speed invalid.  
    **Failure scenario:** A battery event occurs between invocations; one implementation continues, another invalidates the leg, and both can claim conformance.  
    **Change:** Resolve at Go with an explicit ruling. Either make all in-run power failures systemic or record a clear override of C220 and make P426’s invocation check non-stopping.

13. **Location:** §5.5  
    **Severity:** major  
    **Problem:** Make-up invocations are grouped by `(session, seed)`, but the tg1 probe and chain invocation are single-language.  
    **Failure scenario:** One session has both Python and Go DNFs. The required group cannot be represented by one probe invocation.  
    **Change:** Group by `(session, seed, language)` while preserving each occurrence’s original order.

14. **Location:** §2, §3, §6, §8; C221  
    **Severity:** major  
    **Problem:** C221’s generic tg1 changes are not specified consistently. §3 scopes committed-registry serving to P426, and the specification never explicitly retires `chain_core.PRED_S`, although C221 requires no per-pick table.  
    **Failure scenario:** P426 passes while generic tg1 still generates overlays, enforces both historical picks, or uses stale hard-coded ETA predictions for a new `--models` list.  
    **Change:** State that all tg1 modes serve committed `main_models.yaml`, skip overlay generation, assert predictor state, and derive predictions from pilot means or a recorded generic default. Test non-P426 dynamic models.

15. **Location:** §6.4–§6.5; §13 resume rule  
    **Severity:** major — sensitive data boundary  
    **Problem:** Secret equality exists only in sequencer memory and is therefore not crash-resumable.  
    **Failure scenario:** The sequencer crashes after arm one, a secret rotates, and resume skips the harvested first leg. Arm two cannot be compared with what arm one actually used.  
    **Change:** Treat a crash between paired arms as an incomplete pair requiring a fresh pair, or define a protected local pair transaction that preserves comparison capability without publishing secret verifiers.

16. **Location:** §8 decode-rate estimator  
    **Severity:** minor  
    **Problem:** `(Σ generated_tokens − n_requests) / ΔD` becomes negative when a completed request generates zero tokens.  
    **Failure scenario:** An immediate-stop request contributes `−1` token and corrupts the item’s speed estimate.  
    **Change:** Use `Σ max(generated_tokens_i − 1, 0) / ΔD`.