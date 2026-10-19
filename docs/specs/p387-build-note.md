# P387 build note — fork P369 tests deterministic against the pinned fixture + an opt-in live-registry check — v2, 2026-10-19

Parent: `docs/specs/p369-phase2-run-plan.md` v7 §5 (Q26, Q34; Cursor plan rounds 1–7); ruling C183 (3). Fork branch `p369-mtp`
(worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p369`), test-only: `git diff 4e6d0e03 -- mlx_vlm ':!mlx_vlm/tests'` stays empty.
This note records what the build adds to §5 (P392). v1 → Cursor plan round 1 `AGREE WITH CHANGES K1–K4`
(`docs/reviews/p387/plan-round1.cursor-gpt-5.6-sol-high.md`), all applied here (no further plan round; the code review verifies).

## 1. Measured facts (2026-10-19)

- Against the live C177 registry (`MLX_STACK_REGISTRY=<stack>/main_models.yaml`) the registry-reading modules give 56 failed
  + 9 errors + 1 collection error (`test_mtp_session_cancel.py`, module-level `deployed_sampling`), because
  `test_mtp_exactness.deployed_sampling()` reads `_stack_registry()` (env, else sibling, else fixture) and asserts
  `draft_kind == mtp`.
- **P392 — the pinned fixture is stale.** `tests/fixtures/stack_registry_golden.yaml` (sha `323ee54a…`) is the stack registry
  at `d92c7419` (M57, 2026-10-05), BEFORE M58. Parsed, it differs from the last MTP-ON registry (stack `7021bdbb`, the last
  commit changing it before C177 `78a730fe`; byte-identical to `78a730fe^` = `98a14f2e`; sha `1d07c9dd…`) in exactly one field: Fable's `mtp_verify_scan: joint_v1` is absent (every other difference is
  comment text). So the fixture does not hold the certified Fable tuple, and the plan's "identical" state is unreachable
  after the C177 restore (live would carry `joint_v1`, the fixture not).
- Textually, the live registry = `7021bdbb:main_models.yaml` with exactly five lines changed: each pick's `draft_kind: mtp`
  → `# draft_kind: mtp  # P369 INTERIM (C177 …`, the next line `draft_model: …` → `# draft_model: …` (same content, no
  marker), Fable's `mtp_verify_scan: joint_v1` → `# mtp_verify_scan: joint_v1  # P369 INTERIM (C177 …`.
- Both picks' `generation_defaults` values are identical in the old fixture, `7021bdbb` and the live registry (only
  comments differ), so the sampling every existing test uses does not change.

## 2. Build (red first)

1. **Fixture refresh:** the verbatim part := `7021bdbb:main_models.yaml` byte for byte; the header names the source commit
   and the rule "the fixture is the last MTP-ON registry (the shipped-when-ON tuple)"; `FIXTURE_SHA256` → `1d07c9dd…`.
2. **Ordinary tests read only the fixture.** One helper `certified_registry()` (parsed fixture, never env or sibling);
   `deployed_sampling()` uses it (its `draft_kind == mtp` assertion now checks the fixture). The golden first-pick test reads
   the tuple `(kv_bits, kv_quant_scheme, draft_kind, mtp_verify_scan)` = `(0, turboquant, mtp, joint_v1)` from the fixture and
   sets `MLX_VLM_MTP_VERIFY_SCAN` from it (was a literal); it loses the `requires_stack_registry` marker (no live registry
   needed). `MLX_STACK_REGISTRY` and the sibling are read ONLY by the opt-in tests.
3. **Opt-in live tests** (marker `requires_stack_registry`, re-documented): skip with one fixed reason unless
   `MLX_REQUIRE_STACK_REGISTRY=1`; when set, live = `MLX_STACK_REGISTRY` (set-but-absent FAILS) else the sibling, else FAIL.
   One classifier `live_registry_state(text)` → `"mtp_on"` iff the live text equals the fixture verbatim, `"c177_interim"`
   iff it equals the EXPECTED INTERIM byte for byte — the fixture with exactly the five lines of §1 replaced by their
   complete verbatim interim lines, held as constants in the test (K2: no prefix match; a changed marker suffix or a
   changed trailing comment on a commented `draft_model` fails) — else FAIL with "refresh the fixture". The
   parsed-minus-five-keys equality of the interim is asserted once as a consistency check of the constants.
4. **Sibling-dependent tests:** `test_golden_sibling_registry_drift_warns_but_does_not_fail` is removed (superseded by 3);
   the phase-2 `test_overlay_on_the_live_stack_registry` moves under the same opt-in gate and resolution and branches on the
   classifier (K1): `c177_interim` → `overlay_registry` restores, per pick, exactly the fixture's parsed entry;
   `mtp_on` → the live text equals the fixture and `overlay_registry` refuses (nothing to restore). New always-run test:
   `overlay_registry` applied to the expected interim restores, per pick, exactly the fixture's parsed entry (links the
   phase-2 ON argv to the certified tuple).
5. **Tests** (K4: red vs guard stated honestly; the red commit lists the failing ids). RED today: `deployed_sampling`
   returns the fixture's values (a) with `MLX_STACK_REGISTRY` → the expected interim and the sibling absent, and (b) with
   the env unset and `SIBLING_REGISTRY` → the expected interim (K3: two separate poison channels; today both fail "no longer
   ships MTP"); the fixture holds Fable `joint_v1` and names its source commit; the classifier accepts the full interim
   (today require mode refuses anything but verbatim); the overlay restores the fixture entry from the expected interim.
   GUARDS (pass before and after; characterize the classifier): verbatim fixture → `mtp_on`; four of five lines, an
   unmarked `draft_kind`, a changed marker suffix, a changed commented `draft_model` (path or trailing comment), a
   non-adjacent `draft_model`, any other edited line, CRLF, a missing trailing newline, env set-but-absent, no live
   registry → fail; without the env every opt-in test skips with the fixed reason whatever the sibling and
   `MLX_STACK_REGISTRY` say.

## 3. Acceptance

- The registry-reading modules (+ `test_p369_phase2_*`) with `MLX_STACK_REGISTRY=<stack>/main_models.yaml`: 0 failed, 0
  errors; the same with `MLX_REQUIRE_STACK_REGISTRY=1`: 0 failed (interim accepted); the same with `MLX_STACK_REGISTRY` →
  a copy of the fixture verbatim (the MTP-ON state, K1): 0 failed; with a planted extra edit: the opt-in tests fail.
- Fork suite twice back to back: 0 failed, identical skip lists; expected skips 17 (the sibling-drift skip disappears, the
  opt-in live test adds one, the orchestrate live-registry skip changes its reason). Eight audits green, exclusion counts
  unchanged. Production diff vs `4e6d0e03` empty. Then a cold Cursor code review naming the commit.
