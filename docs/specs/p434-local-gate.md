# P434 — local pre-push gate (replaces GitHub Actions) — PLAN v1, 2026-10-22

Authority: C210 (operator: "proceed across the board"). GitHub Actions minutes are exhausted: the stack has no workflows; the
fork's `tests.yml` / `upstream-parity.yml` and mlx-serve's `ci.yml` cannot run. Nothing remote checks a push.

## 1. Rules

- One tool, `benchmark/bench/local_gate.py`, two verbs: `run` (executes a repo's gate, writes a receipt) and `check` (the
  pre-push hook: verifies receipts only, never runs a suite).
- `run` never touches a live tree's files: every step executes in a scratch detached worktree at the exact sha
  (`$STACK_WORKDIR/gate/wt/<repo>-<sha12>`), removed after; the live tree's own suite rule (never edit / test a tree while its
  suite runs) is therefore untouched by the gate.
- `run` refuses when the GPU is busy: any `chain_ops.BUSY` process, a `p426_wave1` sequencer whose `PAUSE` hold is not in
  effect, or a listener on :8000. Operator override: none (wait for a window).
- Receipt: `$STACK_WORKDIR/gate/<repo>-<sha40>.json` — `{repo, sha, verdict: PASS|FAIL, steps: [{name, argv, rc, seconds,
  summary}], python, lock_sha256, skipped_tests (node ids), baseline_skips_sha, started, ended, gate_code_sha}`; exclusive
  create; a FAIL is kept (a rerun writes `-<n>`). PASS requires every step rc 0 and the skip list equal to the recorded
  per-repo baseline (`benchmark/gate/<repo>.skips.txt`, committed; a change to it is its own commit).
- `check` (stdin = git's pre-push lines `<local ref> <local sha> <remote ref> <remote sha>`): for every non-delete line, a
  PASS receipt for `<local sha>`; for the stack, also PASS receipts for the `src/mlx-vlm` and `src/mlx-serve` gitlinks at that
  sha (`git ls-tree`). Missing / FAIL / unreadable → refuse (exit 1) naming the command to run. Tags: same rule on the tagged
  commit.
- Hooks: tracked `githooks/pre-push` (stack) calls `check --repo stack`; the forks get `core.hooksPath` pointing at a
  stack-tracked `githooks/forks/` holding only `pre-push` (`check --repo mlx-vlm|mlx-serve`; no fork file added).
  `bootstrap_machine.sh` sets all three `core.hooksPath`. `--no-verify` is never used by the agent.
- Pushes still need in-turn operator approval; the gate is a precondition, not an authorization.

## 2. Steps per repo (mirroring the dead CI)

- **stack:** `.venv-bench` pytest `bench/tests/` with `STACK_WORKDIR` set (P445) and `NLTK_DATA`; the naming / PII scan over
  `<remote sha>..<local sha>` is the hooks' job (already per commit) — `check` re-runs `bench.piicheck` over the pushed range
  as a cheap belt (no suite).
- **mlx-vlm:** (1) `uvx pre-commit run --all-files` then `git diff --quiet` (the fork's `tests.yml` style step); (2) the eight
  `dev/check_*.py --upstream-ref <UPSTREAM_SYNC_REF>`, the ref parsed from `.github/workflows/upstream-parity.yml` (one
  source), after `git fetch upstream` of that ref (remote added if absent, push URL `no_push`); (3) the fork suite
  `pytest -q mlx_vlm/tests` in a venv built by `uv sync --python 3.12 --extra test` + the box-notes extras
  (`pytest-subtests pytest-asyncio "cryptography>=43.0.0"`). Python 3.10 (CI's) is NOT covered — recorded in the receipt.
- **mlx-serve:** `uv sync --locked --extra dev --extra all`; `ruff check src/`; `ruff format --check src/ tests/`;
  `pytest tests/`; Python 3.12 only (CI matrix 3.11–3.13 not covered; recorded).

## 3. Tests (test-first, mocked runner; no real suite in the unit tests)

Receipt write / exclusive create / FAIL kept; skip-list mismatch → FAIL; busy box → refuse before any step; scratch worktree
created at the exact sha and removed on success and failure; the parity ref parsed from a workflow fixture (missing → refuse);
`check`: PASS / missing / FAIL / unreadable / sha mismatch / delete line / tag / stack gitlinks missing receipts; a step's
nonzero rc never masked (no pipelines); hooks call `check` with the right repo; bootstrap sets the three hooks paths.

## 4. Out of scope

The fork's P440 style debt (fixed after P426; its first gated push will carry it); Python-version matrices; any remote CI.
