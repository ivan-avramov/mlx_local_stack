1. **Location:** §2, §6; premise “P426 `ChainHooks`” and “probe identity unchanged”  
   **Severity:** blocker  
   **Problem:** tg1 hard-codes `item_barrier="off"` in `benchmark/bench/tg1_runner.py`; therefore `.done` barriers and P426 hooks never run. Enabling the barrier requires changing the probe closure, contradicting the unchanged-identity claim. The fake-probe topology test can miss this.  
   **Scenario:** all legs complete without per-item reconciliation or engagement checks, yet mocked tests pass.  
   **Change:** define an explicit P426-only evidence policy with the item barrier enabled, preserve `off` for older modes, freeze the resulting new probe identity equally across arms, and add a real probe-policy contract test.

2. **Location:** §2 “missing engagement … systemic”; §6 hook reconciliation  
   **Severity:** blocker  
   **Problem:** the current hook receives only `slot` and a `.done` payload that omits `session_id` and `request_usage`. Moreover, `chain_core.py` rejects any non-accept disposition for flat tg1 before writing `.stop`.  
   **Scenario:** the hook cannot perform the required join; if it returns `block`, the probe remains waiting for `.continue` while the chain aborts.  
   **Change:** pass the full row, log cursor, load/A4 context, and invocation context to the hook; add a persisted P426 `invalidate_leg` disposition that writes `.stop`, verifies cleanup, and exits deterministically.

3. **Location:** §3 “transport_dnf … never graded … no retry”; “reuses … M64”  
   **Severity:** blocker  
   **Problem:** the existing M64 policy retries, reloads the worker, and emits DNF only after two incidents. Its DNF row has `passed:false, acc:0` and is a strict scored failure. tg1’s current policy instead archives and restarts the whole load. Neither implements P426.  
   **Scenario:** an isolated connection failure is retried/reloaded, restarts completed work, or lowers strict accuracy, all contrary to C220.  
   **Change:** define a separate P426 policy and DNF schema: one incident, healthy unchanged router/worker, certain cleanup, ungraded DNF, relaunch only the remaining items on the same worker. Define completion as ordered `successful rows + DNF outcomes == plan`.

4. **Location:** §3 “reuses chain_incident classification”; systemic worker/router death  
   **Severity:** major  
   **Problem:** `chain_incident.classify_incident_cause` classifies missing/replaced workers and routers as incidents, while C220 requires them to be systemic. tg1 also currently suppresses structured client transport causes outside M64.  
   **Scenario:** a worker replacement is treated as an item DNF and the run continues, or a genuine healthy-worker transport incident cannot be identified.  
   **Change:** require exact router and worker identity before classifying a P426 item incident; identity failure is immediately systemic. Expose structured client causes in P426 without changing legacy tg1 behavior.

5. **Location:** §3 client-inactivity strict fail; §6 exact reconciliation  
   **Severity:** major  
   **Problem:** a valid `client_inactivity` outcome deliberately has an interrupted trailing request with no `request_usage`. The specification only reconciles completed records and requires zero failures, without accounting for that started, uncharged request or proving it drained.  
   **Scenario:** the outcome is incorrectly made systemic, or it passes reconciliation while an in-flight request later contaminates the next item’s log window.  
   **Change:** specify outcome-aware reconciliation: match charged completions exactly, separately record the one evidenced uncharged trailing request, and require terminal worker `in_flight == 0` before continuing.

6. **Location:** §6 ON engagement  
   **Severity:** major  
   **Problem:** the normative bullet requires only `draft_kind=mtp` and bounded accepted/proposed counts; “rounds > 0” is described as derived and pilot-confirmed, not explicitly required for every full-run request.  
   **Scenario:** the pilot engages, but later requests report zero rounds/proposals and are accepted as ON.  
   **Change:** require every eligible completed ON request to have `draft_rounds > 0` and `draft_n > 0`; pilot confirmation validates the instrument but does not replace per-request checks.

7. **Location:** §6–§7; B6 decode-rate input  
   **Severity:** major  
   **Problem:** current `Request completed` lines contain generated tokens and a decode rate rounded to 0.1 tok/s, not raw `decode_elapsed_s`. Exact “total tokens ÷ summed decode time” cannot be computed from the promised slice. Failed lines also lack session IDs.  
   **Scenario:** B6 silently reconstructs biased times from rounded rates while presenting them as the specified estimator.  
   **Change:** either add raw decode elapsed time and session attribution to terminal log records—revising the “no new server code” premise—or explicitly define and label a rounded-rate approximation.

8. **Location:** §4 arm proof and v8 freeze  
   **Severity:** major  
   **Problem:** commit/registry comparison does not prove equality of effective untracked `.env`, inherited `MLX_*`/`TQ_*`/`KV_*` variables, installed environments, or complete worker argv outside the three predictor flags. `ChainOps.env_base()` consumes those values.  
   **Scenario:** ON receives a KV or sampling override from its `.env`, or OFF carries an extra non-draft flag, while all stated arm checks pass.  
   **Change:** freeze and pair-compare normalized effective environments and complete worker argv, allowing only the three MTP arguments and unavoidable identities to differ. Record hashes rather than sensitive values.

9. **Location:** §2–§3 versus §7 power handling  
   **Severity:** major  
   **Problem:** §3 calls a power-gate failure systemic, while §7/C224 says an authoritative watcher failure only invalidates speed and quality continues.  
   **Scenario:** one bad watcher tick causes the next invocation pre-check to abort a quality-valid leg that should continue.  
   **Change:** distinguish entry/before-launch failure (`NOT_STARTED` or systemic) from an in-run watcher deviation (`SPEED_INVALID`, continue quality) and cleanup/orphan failure (systemic).

10. **Location:** §2 exit; §9 harvest; §10 resume  
    **Severity:** major  
    **Problem:** `chain.json` uses `status="finished"` even after abort, and current teardown return codes are ignored. The specification does not explicitly require `rc == 0`. Its harvest appears gated on full realized order, so systemic/partial legs may never be harvested.  
    **Scenario:** a teardown survivor yields `finished` with success-like rows, or an engagement failure strands the diagnostic slice because `check_realized` cannot pass.  
    **Change:** define VALID as `rc==0`, exact terminal inventory, no running/quarantined records, successful verified teardown and free port. Always harvest attempted-leg incident evidence after quiescence, using separate completeness rules for invalid legs.

11. **Location:** §9 completeness-checked harvest  
    **Severity:** major  
    **Problem:** “every file a row/manifest cites” is not a transitive closure. Final-tree manifests reference content-addressed objects indirectly; copied rows retain scratch paths while evidence files may be renamed `.xz` on another branch. No resolver mapping is specified.  
    **Scenario:** a dossier contains the final-tree manifest but misses an object, or B8 cannot locate a compressed transcript after scratch cleanup.  
    **Change:** define a typed recursive closure over rows, manifests, grade artifacts, final trees, incidents and web evidence, with original hash, published hash, destination and compression mapping; make downstream tools resolve through that manifest.

12. **Location:** §9 timeout/overrun; §8 sequencer lock  
    **Severity:** major  
    **Problem:** “never killed; stops for operator” does not define process ownership. A sequencer that returns on timeout releases its flock while the chain/router remains live and evidence remains mutable. “Heavy-tail allowance” also has no executable formula.  
    **Scenario:** a second sequencer or local gate begins while the overrun leg is still running, or the eventual output is never harvested.  
    **Change:** persist an `OVERRUN_PAUSED` state while a supervisor remains alive, holds both exclusion locks, monitors the child, and harvests after exit. Specify and test the exact pilot-based timeout formula.

13. **Location:** §3 make-up leg  
    **Severity:** major  
    **Problem:** the state machine is incomplete: “BOTH arms on a fresh load” does not say whether this means two legs, whether inputs are the union of arm DNFs, their order/session labels, or how make-up incidents count.  
    **Scenario:** only the arm that DNFed is rerun, or both commits are incorrectly attempted on one load, eliminating the diagnostic pair.  
    **Change:** define one fresh labelled leg per arm over the ordered union of DNF items, original session seeds, separate receipts, and explicit repeat-DNF handling.

14. **Location:** §2 frozen/build checks  
    **Severity:** major  
    **Problem:** frozen record and build drift are checked before invocations and at exit, not necessarily at every item barrier. A multi-item probe can continue long after tracked files or the committed registry change.  
    **Scenario:** the registry changes after invocation launch; many items run before exit detects it, violating “systemic problems stop at once.”  
    **Change:** reverify the frozen record, registry hash, lifecycle and owned process identities at every ready/done checkpoint.

15. **Location:** §9–§10 public evidence publication  
    **Severity:** major — sensitive data boundary  
    **Problem:** “scrubbed” is underspecified for public transcripts, stderr and fetched pages. Existing scrubbing mainly replaces known local paths/user/host markers and does not comprehensively detect emails, bearer tokens, private keys, environment secrets or third-party personal data; compression reduces review visibility.  
    **Scenario:** model-emitted shell output containing a credential is committed and pushed to the public `evidence` branch.  
    **Change:** define a pre-compression secret/PII policy, scan configured secret values and common credential formats, quarantine uncertain files, and require reviewed scrub manifests before commit/push.

16. **Location:** §4 `--models a[,b…]`  
    **Severity:** minor  
    **Problem:** the allowed list length is arbitrary, but scheduling is defined only by the legacy pair and the current request’s singleton. Reload ownership, duplicate names and ordering for three or more models are unspecified.  
    **Scenario:** a helper accepts three models but silently reloads only the first or duplicates one, while basic singleton/two-pick tests pass.  
    **Change:** define generic iteration and reload semantics, reject duplicates/empty names, and add a three-model schedule test.