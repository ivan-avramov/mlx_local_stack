**Nothing has run.** The only check was `py_compile` on all 7 files, which passed. I did not read any implementation of this change. Every test file is in `benchmark/bench/tests/s26_frozen/`.

## Files and tests

| File | Tests | What it checks |
|---|---|---|
| `s26_support.py` | helpers | `HostWorld` (a temp host the real fingerprint reads); `HostSeqOps` (the frozen `SeqOps` plus a `host_env` seam); `PosOps` and a hybrid ops class that uses the real `BoxSeqOps.positive_inject` / `inject_verify`; `GradleWorld` (a real executable fake `./gradlew` behind the real `Tg2Corpus` / `tg2_materialize` seams). |
| `test_s26_host_env.py` | 28 | §1: determinism, each `diff` kind, unreadable entries, `fingerprint_for_run`. |
| `test_s26_sequencer.py` | 19 | §2 baseline, pre-launch refusal, post-leg INVALID, exception path, end-of-run check, publication, seam. |
| `test_s26_positives.py` | 55 | §2 `cmd_positives`, §4 pass rule, v8 `positives_problems`. |
| `test_s26_gradle_home.py` | 25 | §3 prefill and check. |
| `test_s26_arm_identity.py` | 15 | §3 `build_env` and identity, tg1 invariants. |

- **`test_s26_host_env.py`**
  - **[NEW]:** 14 tools, tool entries (realpath + sha256), no process spawned, `fingerprint_for_run`, unreadable cases (each records `error: <ExceptionName>` and never raises).
  - **[FIX]:** each diff kind — tool added / removed / changed in place / relinked, Cellar added / removed / bumped, bin-dir add / remove / symlink retarget, npm global, and the 7 home toolchain dirs including `Library/Python`.
  - **[INV]:** `diff == []` iff equal, and the contents of an existing `~/.gradle` are not hashed.
- **`test_s26_sequencer.py`**
  - **[NEW]:** baseline written before the first leg, kept byte-for-byte on resume, an unreadable baseline gives rc 1, exception in the leg region logged and re-raised, `host_env.json` published on `run`, `BoxSeqOps.host_env` delegates to `fingerprint_for_run`.
  - **[FIX]:** exact pre-launch STOP message, post-leg INVALID with class `systemic` and the exact reason (joined with `; `, `(prior: …)` kept, a DNF leg not spared), rerun refused until the host is restored, resumed run on a changed host, end-of-run check on both the `DONE` and `--through` exits (the diff is already in the published `sequence.json`).
  - **[INV]:** power refusal comes before the host refusal, a clean run adds no reason, a rehearsal keeps `host_env.json` and publishes nothing, a fake without the seam behaves as before.
- **`test_s26_positives.py`**
  - **[FIX]:**
    - host change at the grade, inject or session exit → sealed FAIL, one problem per change;
    - an exception in an inject, a grade or session enter → sealed FAIL record, message cut at 300 characters;
    - 19 matrix rows covering DECLINED vs FAIL vs PASS. These include a marker in text only, a marker in any tool's input, `FAIL:rss` with no marker staying FAIL, stall never DECLINED, and tampered events / datefreeze / missing row not declined;
    - `TRANSPORT_ABORT` stays a FAIL;
    - v8 accepts DECLINED only for loop / alloc with valid evidence.
  - **[NEW]:** the record carries `host_env` / `host_env_after`.
  - **[INV]:** a clean run passes, an all-PASS record is still accepted by v8, one abort then a decline on the retry is a decline.
  - **Hybrid:** three tests run the real `m62/inject_verify.py` over real-shaped rows (decline passes; a model that ran the command but wasn't observed fails; `inject_verify` returns the verdict, not `FAIL (rc N)`).
- **`test_s26_gradle_home.py`**
  - **[NEW]:**
    - prefill covers exactly the valid Java items, with the exact `PREFILL.json` content and manifest (only `wrapper/dists` and `files-2.1`);
    - online → `--stop` → `--offline` ordering;
    - the spawn env is the V2 policy fields + `HOME` / `TMPDIR` / `GRADLE_USER_HOME` only, with a sentinel env var that must not leak;
    - scratch trees removed;
    - a non-empty folder refused, an empty one accepted, `--force` removes only the folder.
  - **[FIX]:** an offline failure gives rc ≠ 0, and `check` refuses 12 kinds of damage.
  - **[INV]:** extra cache files are fine, `check` is read-only.
- **`test_s26_arm_identity.py`**
  - **[FIX]:** tg2 `build_env` refuses without a folder and re-checks on every item (4 damage kinds).
  - **[NEW]:**
    - `GRADLE_USER_HOME` is set when the folder is prefilled;
    - the policy field is omitted when None and changes the hash otherwise;
    - the tg2 policy carries `{path, properties_sha256, prefill_sha256}`;
    - the real tg2 `--print-identity` moves with the prefill.
  - **[INV]:** tg1 / M64 env has no Gradle home and equals `opencode_v2_core._opencode_env`; the tg1 policy has no Gradle block and its hash is independent of the folder.

## Expected on the baseline

- **Fail:** everything in host_env, gradle_home, sequencer and the new positives tests (ImportError or missing behaviour), plus most of the arm/identity tests.
- **Pass:** these tests, because nothing has changed yet.
  - `test_inv_v8_still_accepts_an_all_pass_record`
  - `test_inv_tg1_env_is_exactly_the_core_hermetic_env`
  - the tg1 / M64 no-Gradle-home env test
  - `test_inv_the_tg1_policy_is_untouched_by_the_gradle_home`
  - the sequencer's fakes-without-the-seam test (the one nominal baseline pass in the sequencer file)
- **Phase B:** the B4b-1 tg1 golden (`test_m76_b4b1_impl_golden_tg1.py`) has not been run and must pass unmodified on the candidate.

## Ambiguities and untestable points

- **P1. Module interface.** The spec never names `bench.tg2_gradle_home.main(argv) -> rc` or the fingerprint's inner structure. I assumed:
  - `bin_dirs` is `{dir: [entries]}`;
  - `npm_global` is keyed by `@scope/pkg` for scoped packages;
  - a `PREFILL.json` item is `{"id", rc, rc}`;
  - the manifest paths are relative to the folder;
  - the policy key is `gradle_user_home`.

  A mismatch will show up as a failure that looks like a bug.
- **P2. `ops.inject_verify` return value.** The spec compares verdict strings (`not_observed*`, `FAIL:no_shell_part`) but never says what the seam returns. I assumed a bare verdict string. The baseline box version returns `FAIL (inject_verify rc N)`, and one test requires the real verdict. How `verify_result` is recorded is also unspecified. I only assert it is a non-empty string, and only in the hybrid test. <!-- allow-shorthand -->
- **P3. `declined_evidence` keys.** The spec lists "events sha256, marker, verify verdict" without key names. I match by value, not by key.
- **P4. Finalization order.** On an end-of-run STOP, `main()`'s `finally` still calls `publish_run_files`. "BEFORE publishing" is therefore only testable as "`sequence.json` already holds `host_env_after_last_leg` at publish time." Whether anything should be published after that STOP is unclear.
- **P5. Resume message.** For a resumed run the "next leg" in the message is not fully defined. I assert it only for the unambiguous case (the first leg already done).
- **P6. Prefill order.** The spec doesn't say whether passes go item by item or all online first. I assert only per-item online-before-offline and that one `--stop` falls between the first online and first offline pass. Whether one failing offline pass aborts the rest is also unspecified, so I don't test it.
- **P7. Environment dependencies.** The prefill tests need `java` on the agent PATH if the implementation resolves its realpath. The identity tests make the same read-only calls the existing `--print-identity` tests make (the docker image-id pin file), with no docker daemon needed.
- **P8. Sequencer coverage.** I tested the tg1 (`mtp`) sequencer only. The tg2 / kv sequencer path shares `Sequencer.run`, but I wrote no separate test for it.
- **P9. Untestable.** The `bootstrap_machine.sh` step 5b is not in acceptance 1. I wrote no test for it, and the rest of the spec is covered except those two non-goals.