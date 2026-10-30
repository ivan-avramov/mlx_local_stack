I read `BRIEF.md` and `VERIFY3.md`, then traced each round-2 finding through `REPAIR.diff` and the current source (`p426_harvest.py`, `p426_secrets.py`, `p426_wave2.py`, `p426_freeze.py`, `p426_receipt.py`, `p426_hooks.py`) and ran the targeted suite for the changed code.

Note on the test run: this review checkout has its submodules uninitialized (`src/mlx-vlm`, `src/mlx-serve`) and I built a minimal venv (pytest + pyyaml + requests only), so the frozen set and the s8/s9/fix3 suites that touch `mlx_serve`, `psutil`, or `src/mlx-vlm/dev/p369_phase2/pins.json` fail here purely from missing modules/submodules — environmental, not regressions. The suite that exercises only the changed code, `test_b2_fix4.py`, is green (29 passed).

## Round-2 findings — dispositions

**1. Publication ran the gate without the exact credential values; `sequence.json` carries operator text — RESOLVED.**
`_publish_records` now builds `Gate(scrub, scrub.secrets)` (`p426_harvest.py:959`); `BoxSeqOps._scrub` forwards `secrets=self._credentials()` into the `Scrub` for both `publish_dossier` and `publish_run_files` (`p426_wave2.py:899-905`); `_credentials` loads via the new `load_credentials` (`p426_harvest.py:1018`), which raises `HarvestError` on a `SecretsError` so an unreadable source refuses rather than publishing unscanned. A configured secret placed in `sequence.json` is caught by `exact_hits` and the whole publish raises before any rename. Confirmed by `test_b2_fix4.py::test_1_*`.

**2. `publish_run_files` did not require self-hashes — RESOLVED.**
`publish_run_files` now calls `_publish_records(..., require_self_hash=True, exempt=("sequence.json",))` (`p426_harvest.py:1040`); `_immutable_problem` (`:216`) requires a present, valid `sha256` for every non-exempt file, and `sequence.json` (a state file carrying `previous_sha256`, never a self-hash — `write_sequence`, `p426_wave2.py:259`) falls through to the lenient `_self_hash_problem` branch. The sequencer only ever writes sealed `v8_base.json`/`amendment.json` into `record_dir` (`p426_freeze.py:539`, `:638`), so the new requirement matches what is produced. Confirmed by `test_2_*`.

**3. `makeup` used an existing amendment without re-verifying it — RESOLVED.**
`Sequencer.verify_existing_amendment` (`p426_wave2.py:669`) is invoked from `run()` for `cmd in ("run","makeup")` (`:759`) before any leg; it re-derives the selected pilots, refuses (Stop 1) if they are not recorded, and calls `verify_amendment` which re-checks self-hash, kind, `v8_base_sha256`, the PASS pilot pair, and `pilot_dossier_sha256` against the actual dossier file. Confirmed by `test_3_*`.

**4. Dossier publication not idempotent on resume; failure not exit 4 — RESOLVED.**
In `ensure_dossier` (`p426_wave2.py:588-599`) the new dossier is published via `publish_dossier_or_stop` *before* the pair record is appended/saved, so a publish failure leaves no pair record and raises `Stop(4)`; the `published` flag is set on success. `republish_dossiers` (`:617`) runs at the start of every `run()` and republishes any recorded-but-unpublished dossier idempotently (same bytes = done by `_publish_records`), also via `publish_dossier_or_stop` (exit 4 on failure). Confirmed by `test_4_*` (order, resume, idempotency, exit-4-on-failure).

**5. `$VAR`/`$(…)`/backtick in a credential value silently disabled the exact match — RESOLVED.**
`_expands` (`p426_secrets.py:80`) tracks single/double quoting and backslash escapes and returns true for an unquoted `$` or backtick; `parse_assignments` (`:97`) raises `SecretsError` (naming the key only) for a credential-keyed value that would expand. I traced the quoted/escaped/double-quoted cases: single-quoted and backslash-escaped values are taken literally (no refusal), unquoted/`"…$…"`/backtick values refuse. Environ values are added directly (already expanded by the shell), correctly bypassing the check. Confirmed by `test_5_*`.

**6. An ON DNF item with only ≤1-token requests not flagged `unengaged` per item — DECLINED, correctly.**
The per-item rule is gated by `item=not dnf` at `p426_freeze.py:156`, so a DNF item is not per-item engagement-checked; the leg-level rule (`p426_freeze.py:158`) still fires when no ON request of the whole leg is judgeable. This matches the spec clarification (§16.8 last bullet: "The per-item `unengaged` rule applies to completed items; a DNF item is covered by the leg-level rule"). No change required.

## Anything else the diff breaks or leaves failing

One residual narrow gap (hypothesis, not a defect introduced by this diff — the diff *improved* coverage here):

- **Location:** `p426_wave2.py:977-979` (`ops.env_files` from CLI `--worktree-off/on`) vs `p426_harvest.py:1060-1085` (`leg_worktrees` from the frozen `v8_base.json`).
- **Severity:** minor (hypothesis).
- **Problem:** The leg harvest derives the arm worktrees (and thus which `<WT>/.env` files it scans) from the frozen `v8_base.json`; publication derives them from the sequencer's current `--worktree-off/on` CLI args. Both still scan the machine `config.sh` and `environ`, so primary credential sources are shared. They diverge only if the operator relaunches the sequencer with `--worktree-off/on` pointing at different worktrees than `v8_base.json` recorded — at which point a credential that lives *only* in a worktree `.env` and appears *only* in a published dossier/run file (and matches no credential *format*) would be hit by the leg harvest's exact-match but missed by publication's exact-match (the format scan still runs).
- **Failure scenario:** operator reruns `p426_wave2 run` with swapped worktree args after the pilots; a token present only in the original worktree's `.env` is pasted into a `--rerun-reason` that lands in `sequence.json`; the leg harvest refused it but publication's exact-match does not see that `.env`.
- **Proposed change:** have `_credentials` use the frozen `v8_base.json` worktrees (the same source `leg_worktrees` uses) instead of the live CLI args, so publication and the leg harvest scan an identical `.env` set. This is a hardening, not a fix for a demonstrated leak.

NOTHING OF SUBSTANCEThe background frozen-set run completed (220 failed / 283 passed) — but as I noted in the review, every failure here is environmental: the submodules (`src/mlx-vlm`, `src/mlx-serve`) aren't initialized in this read-only checkout and my minimal venv lacks `psutil`/`mlx_serve`, and several frozen tests read `src/mlx-vlm/dev/p369_phase2/pins.json`. None are regressions from `REPAIR.diff`. The suite that covers only the changed code (`test_b2_fix4.py`) passed 29/29. No follow-up actions needed; the review conclusion stands.
