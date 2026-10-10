**BLOCKING.** 110 focused tests passed, including the real pinned-v1 mock capture. No live-router requests or repository edits.

- **B1 — HIGH · VERIFIED:** `benchmark/run_opencode_probe.py:363,737,763`. PATH-first is not fail-closed: a missing/non-executable pin falls through to brew during discovery, **before M50 and version validation**. A differently named `OPENCODE_PROBE_BIN` also validates one executable while spawning another named `opencode`. Confirmed missing-pin fallback without executing brew. **Fix:** pass the exact absolute executable to every spawn, including provenance discovery; missing executable must refuse directly.

- **B2 — HIGH · VERIFIED:** `benchmark/run_opencode_probe.py:782,807,816,889`. Continuation checks router attribution only. Changing `--seed-base` appends mixed schedules and replaces the manifest with the newest base. Repeating an item appends duplicate `(id, sample=0)` rows; there is no completed-item resume handling. **Fix:** validate seed/scaffold compatibility before overwriting/appending; skip completed keys or require a fresh output.

- **B3 — HIGH · VERIFIED:** `benchmark/bench/provenance.py:293`, `benchmark/bench/compare.py:61,260`. **Nothing consumes `scaffold_policy_sha256` for comparison/pooling.** Neither fingerprint nor comparison checks the new hash; differing hashes produced identical fingerprints. AC5 and the notebook’s “never pool” claim are unsupported. **Fix:** enforce scaffold identity in comparison and resume, including legacy missing-field handling.

- **B4 — HIGH · VERIFIED:** `docs/open-questions.md:18`, `docs/PLAN.md:173` on main (deleted), `docs/handoff.md:25`. The branch deletes C123’s ruling and M59’s queued migration, and changes verified M57 startup evidence to “still unverified.” This violates decision retention and loses authorized queue state. **Fix:** restore these main-branch records and reconcile the C121 handoff.

- **B5 — MEDIUM · VERIFIED:** `benchmark/run_opencode_probe.py:406–425`. Verification is a version-string marker beside the installation, unbound to executable contents, config, or test revision. Reinstalling/replacing the binary—or a subsequent failing test—leaves “verified-by-test” intact. **Fix:** use a receipt bound to executable/config/test hashes; mismatches become unverified.

- **B6 — MEDIUM · VERIFIED:** `benchmark/run_opencode_probe.py:433–448`. The overlay check ignores subprocess status. A mocked exit **1** with matching JSON passed. **Fix:** reject nonzero exit before parsing; test exit failure, timeout and malformed output.

- **B7 — MEDIUM · VERIFIED:** `README.md:59`, `docs/campaign-results.md:145`, `docs/open-questions.md:20`. AC7 is incomplete: published evidence still lacks the unseeded qualification; C121 still says `CLAUDE.md` is absent and conflates M54 with opencode. **Fix:** propagate the scoped retraction. The notebook and M54 annotation correctly identify AgentBench’s per-item **base-0 schedule repeated across sessions**.

- **B8 — HIGH, inherited · VERIFIED:** `benchmark/run_opencode_probe.py:847,865,870,889`. Nonzero opencode exits proceed to grading and row append; there is no transport-failure abort gate. A failed request after an edit can become a scored row. **Fix:** distinguish transport/session errors from intentional progress-gate termination and abort without scoring. This predates C121 but violates AGENTS.md.

- **B9 — LOW · VERIFIED:** `benchmark/run_opencode_probe.py:419,807,887`. `overlay_sha256` appears in rows only, contrary to AC1’s row **and manifest** requirement. **Fix:** record per-item overlay hashes in the manifest.

**Other verified checks:** entry export/PATH construction adds no filesystem I/O itself; discovery uses the supplied child environment, with no parent `shutil.which`. Seeds correctly use `sample_seed(language/item, 0, base)` and reproduce for identical inputs; absolute uniqueness is not guaranteed by the 31-bit hash. Overlay writing occurs after copying and before execution; solution/test checks ignore it.

The overlay remains model-writable. A mock tool changed it from seed `424242` to `987654`, but the following request retained `424242`. **Mid-session seed switching was not reproduced**; assuming it happens would be unjustified.

Real v1 parsing passed (~0.4 s in the isolated check). There are **two debug subprocesses per item**, each with a 120-second timeout. Parse/base/seed failures refuse before that item’s row. `~/.claude/CLAUDE.md` exists; a temporary sentinel was absent from captured requests with the switches enabled.

**Test limitation:** the integration test explicitly selects the binary and repairs PATH itself (`test_opencode_probe_seeding.py:242–244`), so it passes with broken production PATH wiring. The deep-merge test exercises its own merge implementation; stubbed debug tests do not establish real executable selection. Resume mismatch, comparison refusal, stale receipts and nonzero debug exits lack regression coverage.


