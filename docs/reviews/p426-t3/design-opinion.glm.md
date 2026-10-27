I have enough to report. Let me write the findings.

---

# Cold design review: `docs/specs/p426-t3-serving-build.md` (SPEC v1)

Findings only. Labels: **blocker / major / minor / scope-request**. Evidence marked confirmed (traced in source) or hypothesis.

---

## F1 — major: the frozen worktree's venvs are not required to be synced from the new locks, so an S′ leg can run on mlx 0.32.3

**Location:** spec §4 "success path" and §3 AC1; `benchmark/bench/p426_plan.py:46-58` (M1 `driver_argv` uses `repo/.venv/bin/python`); `benchmark/bench/p426_wave1.py:62-66` (leg `driver_argv` uses `repo/.venv-bench/bin/python`).

**Evidence:** confirmed. AC1 verifies only the *main* checkout's `.venv` (`uv sync --frozen`) and a *fresh* `.venv-bench` from the bench lock. The §4 success path says "the designer … builds the frozen worktree, writes `frozen.s2.json` … runs `bench.p426_wave1 --build s2 …` from the frozen worktree" but never states that the frozen worktree's own `.venv` and `.venv-bench` are synced from the new locks, nor lists it as an acceptance check. The M1 leg's qualify runs on the frozen worktree's `.venv` (`p426_plan.py:50`), and every other leg's driver runs on the frozen worktree's `.venv-bench` (`p426_wave1.py:62`).

**Problem:** The fork's exact verifier kernels now require mlx 0.32.4 (spec §5; fork handoff `review_material/fork-main-c688e722/handoff.md:60-63`). If the designer "builds the frozen worktree" by checking out S′ and copying the old `.venv`/`.venv-bench` (mlx 0.32.3), the M1 qualify leg fails 138 verifier-exactness tests, and every leg runs on the wrong mlx. The K2 `frozen_sha`/`mlx_vlm` pin check catches a *gitlink* drift, not a *venv* drift — the worktree's gitlinks can be `c688e722` while its `.venv` still has mlx 0.32.3.

**Failure scenario:** Designer creates `$STACK_WORKDIR/worktrees/stack-p426-s2`, checks out S′, writes `frozen.s2.json` with `mlx_vlm=c688e722`, but reuses the worktree's existing `.venv` (mlx 0.32.3) because the spec never says to sync it. `bench.p426_wave1 --build s2` launches; the first M1 smoke leg's qualify runs on mlx 0.32.3 and fails the verifier kernels; the leg is receipted INVALID; the sequencer stops. S's evidence is untouched (good), but S′ Wave 1 never produces a single VALID leg, and the failure mode is not signposted by the spec.

**Proposed change:** add to §4 success path and to AC1: the frozen worktree's `.venv` is `uv sync --frozen`'d from the new `uv.lock` and its `.venv-bench` from the new `benchmark/requirements-bench.lock`, and the sequencer's pre-launch harvest (or a precondition) asserts `import mlx.core; mlx.__version__ == "0.32.4"` from *that worktree's* `.venv` and `.venv-bench` before the first leg.

---

## F2 — major: the box-notes P369 correction reverses the 2026-10-17 observation without preserving it as fork-scoped

**Location:** spec §5; `docs/box-notes.md:22-24`.

**Evidence:** confirmed. The current note (2026-10-17) says mlx 0.32.4 *breaks* 138 quantized-verifier exactness tests and 0.32.3 *passes* — true for the fork at S (`src/mlx-vlm` `c9543fc4`/production `7207179b`). The spec §5 instructs a "dated correction (2026-10-27): the fork's exact verifier kernels now require mlx 0.32.4 and fail on 0.32.3" and that "the rule stays." The correction inverts the old observation's direction.

**Problem:** If the correction rewrites the note in place, the S-specific evidence (138 tests fail on 0.32.4 with the S fork) is destroyed. A future operator who reverts to the S fork (or any fork between `282fb009` and `c688e722`) and bumps mlx to 0.32.4 would no longer be warned by box-notes that 0.32.4 breaks that fork's verifier kernels. The surviving rule ("re-run the fork's verifier exactness tests on any mlx bump") mechanically covers it, but the specific known-failure mode is lost, and the rule is only as good as the next operator following it.

**Failure scenario:** After T3 ships, a regression re-pins the fork to `c9543fc4` for a hotfix and bumps mlx to 0.32.4 for an unrelated reason. The corrected box-note now says 0.32.4 is required and 0.32.3 fails — the opposite of the truth for that fork — so the operator skips the verifier-exactness re-run, ships MTP, and serves broken quantized verification.

**Proposed change:** keep the 2026-10-17 observation verbatim and *fork-scoped* ("true for the fork at `c9543fc4`/`7207179b`; 0.32.4 fails 138 verifier-exactness tests there"), and add the 2026-10-27 correction as a separate dated note ("for the fork at `c688e722` and later, the kernels require 0.32.4 and fail on 0.32.3"). The rule stays and is now correct for both forks.

---

## F3 — minor: A1's verifier-exactness evidence is on transformers 5.14.1, but S′ ships transformers 5.15.0

**Location:** spec §"Assumptions" A1; §2 (relock resolves transformers 5.15.0); §3 AC3.

**Evidence:** confirmed. A1 states "1124 passed … scratch venv, transformers 5.14.1". `review_material/uv.lock.relocked` resolves `transformers 5.15.0` (confirmed by grep). AC3 requires the MTP/verifier subset pass "in the stack's `.venv` on S′" — i.e. on transformers 5.15.0 — so the re-run is required and covers the gap. But A1 is presented as the *precondition evidence* that the bump is safe; its measurement environment differs from S′'s shipped environment in the transformers pin, and the fork handoff (`review_material/fork-main-c688e722/handoff.md:64-68`) explicitly warns that `datasets`/`transformers`/`huggingface-hub` interact (installing `datasets` alone pulls `huggingface-hub` 2.x, which `transformers` 5.14 rejects).

**Problem:** A1 is being relied on as the "fork's MTP/verifier exactness tests pass on mlx 0.32.4" signal, but it was not measured against the dependency set S′ actually ships. AC3 re-runs it, so this is not a hole in the deliverable — but the assumption overstates what was measured.

**Failure scenario:** A reviewer treats A1 as covering AC3 and waves the re-run through; a transformers-5.15-specific verifier-test regression goes uncaught until a leg fails.

**Proposed change:** narrow A1 to "measured 2026-10-27 on a scratch venv on mlx 0.32.4 and transformers 5.14.1; AC3 re-runs the subset on the S′ `.venv` (transformers 5.15.0)."

---

## F4 — minor: the `--build` label is not explicitly wired into the leg's frozen-record read path, leaving the isolation guarantee to the implementer's inference

**Location:** spec §4 ("frozen record `<workdir>/p426/frozen.<b>.json`", "A leg under `b` never reads … a path of another label"); `benchmark/bench/p426_leg.py:687` (`FROZEN = "p426/frozen.json"` hardcoded), `p426_leg.py:718` (`frozen_path = Path(args.workdir).resolve() / FROZEN`); `benchmark/bench/p426_wave1.py:170` (`frozen_json = workdir / "p426" / "frozen.json"`).

**Evidence:** confirmed. The spec states the *name* of the frozen record (`frozen.<b>.json`) and the *isolation* requirement, but never says "the leg and sequencer read `frozen.<b>.json` when `--build b`." The existing code hardcodes `frozen.json` in three places. The §6 test list ("the frozen-record build check … match proceeds") covers the *field* check, not the *path* selection.

**Problem:** An implementer could add a `build` field check against a `frozen.json` they read by the hardcoded path, satisfy the literal §6 tests (pass `frozen.s2.json` content with `build: "s2"` through the check), and still have the leg read `frozen.json` (S's record) when launched under `s2` — violating isolation and failing the build mismatch (which is the intended refusal, but the leg would refuse on S's record rather than reading its own). The spec's isolation guarantee ("never reads a path of another label") is not testable from the §6 test list alone.

**Failure scenario:** Implementer adds `--build` parsing and a `build`-field check but leaves `FROZEN` hardcoded. An `s2` leg reads S's `frozen.json`, sees `build` missing (→ `s`), refuses with NOT_STARTED. The sequencer stops (rc 1), S is untouched — but no S′ Wave-1 leg ever runs, and the failure reads as "build mismatch" rather than "wrong frozen path."

**Proposed change:** add to §4 an explicit requirement: "a leg launched with `--build b` reads `<workdir>/p426/frozen.<b>.json` and no other frozen record; the sequencer reads the same path for its pre-launch harvest and resume." Add a §6 test that an `s2` leg with only `frozen.json` present (no `frozen.s2.json`) refuses for the *missing* file, not for a build mismatch.

---

## F5 — minor: the `--out` (receipts/sequence.log) directory is not label-scoped, so the spec's isolation guarantee depends on label-qualified leg names alone

**Location:** spec §4 (isolation); `benchmark/bench/p426_wave1.py:166-169` (`receipts = out / "receipts"`; `frozen_json` harvested from `--out`).

**Evidence:** confirmed. The spec scopes the *harvest dossiers* (`wave1.<b>/`) and the *frozen record* (`frozen.<b>.json`) by label, but says nothing about the `--out` directory that holds receipts, per-leg stdout, and `sequence.log`. Leg names are label-qualified (`p426s2-*` vs `p426-*`), so no overwrite occurs even if `--out` is shared — but the spec's isolation statement ("never reads, writes … a path of another label") is stronger than what the naming enforces at `--out`.

**Problem:** If an operator runs `--build s2 --out <s-out-dir>` (reusing S's out dir), the s2 run's receipts and stdout coexist with S's in the same directory. The resume rule reads only label-qualified names, so it is safe — but the spec claims isolation, and a future tool that lists or cleans `--out` by stem-prefix could touch another label's receipts. This is a latent hazard the spec introduces by not constraining `--out`.

**Failure scenario:** A cleanup helper globs `<s-out>/receipts/*.receipt.json` and archives them all; S's receipts are swept into an s2 evidence bundle, confusing the labels at the scratch layer (not in the repo, so S's committed evidence is safe, but the run's provenance is muddled).

**Proposed change:** either require `--out` to be label-distinct (e.g. the sequencer refuses if `--out`'s `receipts/` already contains receipts whose names match a different label), or weaken the isolation claim to "no committed evidence and no frozen-record path crosses labels; the `--out` scratch dir is shared-safe by leg-name qualification."

---

## Scope requests (no severity)

- **S1:** Add an AC that the frozen worktree's `.venv` and `.venv-bench` import mlx 0.32.4 (the same check AC1 makes for the main checkout), so the venv-sync gap of F1 is closed by an acceptance criterion, not just the success-path prose.
- **S2:** Add to §6 a test that the sequencer's pre-launch `harvest_run_files` publishes `frozen.s2.json` to `wave1.s2/run/` and does *not* create or touch `wave1/run/frozen.json` — the current `test_p426_harvest.py::test_run_files_are_copied_once_and_must_match_on_resume` exercises only the `s` path.

---

Nothing else of substance: the label grammar admits `s`/`s2`; the `s`-default argv byte-identity is consistent with the existing `test_p426_wave1.py::test_leg_argv_is_exact`; the `registry_states.py` and fixtures are byte-identical between S (`c9543fc4`) and S′ (`c688e722`) (confirmed by `diff`), so the ON overlay sha is stable and the `registry_on_sha` pin does not confound the build check; `ids.json` axes (`cjudge,math500,reasoning,vision`) and the `m1` special-case in `p426_plan.plan_leg` are consistent with the spec's "supported conditions"; A3's "no stack code uses `spec_draft_model`/`spec_draft_kind`" is confirmed (only `docs/specs/p405-kv-scheme-precedence.md:60` mentions them).
