Two findings, both on the `served_on` path; I didn't read the last ~400 lines of the new test file, so test coverage there is unreviewed. They follow from checking the three assumptions: A1 holds in the code I read, and A2 and A3 each fail in one respect.

**1. `served_on` measures MTP-ON without checking the entry's settings against what P369 certified (A3 fails)**
- **Location:** `qualify.py.txt` `drive()` lines 961–1000 and `_drive_locked()` lines 1119–1137; the old `_drive_locked` classified the registry on every arm.
- **Severity:** major. **Evidence:** confirmed by tracing the source.
- **Problem:**
  - Before the change, `_drive_locked` ran `registry_states.classify` for every arm. It refused any registry whose entry settings differed from the pinned fixture, other than the 16 MTP-key states.
  - Now `classify()` is called only when `predictor == "on"` and the entry has no MTP keys.
  - A committed entry that carries MTP keys is `served_on`. Its gate needs only a summary that is a FULL PASS for that name at that production. The summary is not tied to the entry's block.
- **Failure scenario:** someone commits a changed `draft_model`, `mtp_verify_scan: per_query`, or a different `kv_bits` or `prefill_step_size` for a P369 pick. `--predictor` omitted, or `on`, then measures it as `served_on`. The old table path refused this. The report shows an MTP-ON measurement backed by a P369 pass for a different configuration. This also makes A2 false in effect: for the old three entries the gate is stricter on production but weaker on configuration.
- **Spec note:** spec v1 item 4 requires the lazy classification, so this goes to the operator.
- **Proposed change:**
  - For an arm in `MTP_ON_ARMS` whose name is in `registry_states.ENTRY_OFF`, also require `classify()` to be non-None and the entry to be ON in that state. That is the old check, narrowed to the entries it can apply to.
  - For other entries, record the entry's settings hash in the report.
  - Better, have P369 bind its summary to the entry's settings hash and check it here.

**2. Arms and gate come from a registry read that the run does not re-verify**
- **Location:** `qualify.py.txt` `drive()` lines 945–1000; `_drive_locked()` lines 1055–1056 re-reads `registry` and `registry_sha`.
- **Severity:** minor. **Evidence:** hypothesis (traced, not reproduced).
- **Problem:** `arms` and `entry_problems` use `registry_text` read before the lock and `preflight`. `_drive_locked` then reads the file again and checks only against that second sha, not against `registry_text`.
- **Failure scenario:** the registry is committed between the two reads. The arm is `served_off` (no gate), but the file now carries MTP keys, so the run serves MTP-ON with no P369 gate. `guard_problems` doesn't catch it because `start` is taken after the change.
- **Proposed change:** in `_drive_locked`, refuse if `registry != registry_text`. Alternatively, pass `registry_text` in and use it throughout.

**3. `serves_mtp` is key presence, not what is actually served**
- **Location:** `qualify.py.txt` lines 64–66, 69–88, 123–145.
- **Severity:** minor. **Evidence:** hypothesis.
- **Problem:** `serves_mtp` is true if any MTP key is present, but `expected_config` sets `drafter` only for `draft_kind == "mtp"` plus a non-empty `draft_model`.
- **Failure scenario:**
  - An entry with only `mtp_verify_scan`, or `draft_kind: ""`, is labelled `served_on` while it measures with no drafter. If it isn't a pick, it is refused with a PICKS message.
  - A new candidate with a non-MTP `draft_kind` (a different speculative decoder) is refused as served. With `--predictor off`, `mtp_off` strips its non-MTP draft keys. The spec lists those three keys, so that follows the spec, but "OFF" then silently changes a non-MTP setting.
- **Proposed change:** derive `on` from `expected_config(entry)["drafter"]`, or refuse an entry with a partial or non-MTP draft block.

**4. Style slip**
- **Location:** `qualify.py.txt` line 1050.
- **Severity:** minor.
- **Problem:** `pre =orchestrate.preflight(args, out)` is missing a space.
