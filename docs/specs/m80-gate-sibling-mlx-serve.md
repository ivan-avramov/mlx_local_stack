# M80 — the local fork gate provides a sibling mlx-serve (S22-P17) — SPEC v1, 2026-11-12 (four-eyes light; C329)

## Goal

The local pre-push gate (`bench.local_gate run --repo mlx-vlm`, P434) clones the fork alone into a scratch directory, so every fork
test that needs mlx-serve's real `_build_command` beside it — today the M76 B2 tests (`mlx_vlm/tests/test_m76_b2_fe_*`, ≈ 146) —
skips there, and a PASS receipt does not show they ran; the M76 B2 push carried them as temporary skip-baseline entries. Make the
mlx-vlm gate clone `../mlx-serve` beside the fork clone at a pinned commit, build its venv, run the suite with it present, record the
pairing in the receipt, and fail when a test marked as needing a runnable mlx-serve skips. Solving it means: after this change the
B2 tests run (pass) in the gate, the temporary baseline entries are removed, a receipt names the mlx-serve commit the fork was tested
against, and no marked test can skip silently.

## Scope (files)

`benchmark/bench/local_gate.py`; `benchmark/gate/mlx-vlm.skips.txt` (remove the M76 B2 entries added by the temporary commit);
tests `benchmark/bench/tests/test_m80_*.py`. Fork side (a fork commit, push ask): register a pytest marker `requires_mlx_serve` in the
fork's pytest config and mark the B2 tests that call mlx-serve's real `_build_command` (`real_command` / `make_stack_root` consumers).

## Interfaces

- Layout: for mlx-vlm the run's scratch becomes a per-run directory holding the fork clone and its sibling —
  `gate/scratch/<repo>-<sha12>-<ns>/mlx-vlm` and `gate/scratch/<repo>-<sha12>-<ns>/mlx-serve` — because the tests locate the
  sibling as `FORK.parent / "mlx-serve"`; both are removed at the end as today's scratch is.
- `steps_for("mlx-vlm", …)` gains, after `clone` and before `sync`: `sibling` (clone `<live>.parent / "mlx-serve"` at the pinned
  sha into the sibling path) and `sibling-sync` (`uv sync --frozen --all-extras` in the sibling clone, so `mlx_serve` and its
  dependencies import).
- The pinned sha: `--mlx-serve-sha <sha>` if given, else the `src/mlx-serve` gitlink of the stack repository's HEAD
  (`_stack_repo()`); refuse (GateError) when that sha is not a commit in `../mlx-serve`.
- Receipt: `paired: {"mlx-serve": <sha>}` (mlx-vlm only); the policy digest covers the pairing rule (gate source), not the sha.
- After pytest: every test id carrying the `requires_mlx_serve` marker (collected from the junit file's properties or a
  `--collect-only -m requires_mlx_serve` listing in the same scratch) must have passed; a skipped / missing marked test → problem
  `requires_mlx_serve tests skipped: [...]` → FAIL.
- The pre-push check (`check_lines` / `push_level`) is unchanged for the stack and mlx-serve; for mlx-vlm a PASS receipt is accepted
  regardless of its paired sha (the pairing is evidence, not a key) — a later stack bump's own gate re-runs the stack against both.

## Acceptance criteria

1. Red-first tests (fake runner / ops as the existing gate tests): the step list for mlx-vlm includes `sibling` / `sibling-sync` with the
   per-run parent layout; the pinned sha from the stack HEAD gitlink and from `--mlx-serve-sha`; refusal for an absent sha; the
   receipt's `paired`; a skipped `requires_mlx_serve` test → FAIL; stack and mlx-serve step lists byte-identical to today.
2. A real gate run of the current fork HEAD passes with the B2 tests ran and passed, the temporary skip-baseline entries removed.
3. The existing gate tests pass unchanged.

## Non-goals

Pairing for the stack gate (it already clones both gitlinks); remote CI.
