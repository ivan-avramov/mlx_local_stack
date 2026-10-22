# P434 — local pre-push gate (replaces GitHub Actions) — PLAN v2, 2026-10-22

Authority: C210 (operator: "proceed across the board"). GitHub Actions minutes are exhausted: the stack has no workflows; the
fork's `tests.yml` / `upstream-parity.yml` and mlx-serve's `ci.yml` cannot run. Nothing remote checks a push.

Reviews: `docs/reviews/p434/plan-round1.*` (G1–G11, all accepted in v2).

## 1. Threat model (G1)

The gate stops ACCIDENTAL pushes of unchecked code by the agent or operator. Same-user tampering (editing a receipt, deleting
the shim, `--no-verify`) is out of scope and equivalent to `--no-verify`; the agent never does any of these. No signing.

## 2. Rules

- One tool, `benchmark/bench/local_gate.py`: `run --repo stack|mlx-vlm|mlx-serve --sha <sha>` executes the gate and writes a
  receipt; `check --repo …` is the pre-push hook (receipt + cheap scans; never a suite).
- **Isolation (G3, G11):** `run` works in a disposable local CLONE (`git clone --quiet --no-hardlinks <live> <scratch>`, never a
  linked worktree) under `$STACK_WORKDIR/gate/scratch/<repo>-<sha12>-<ts>`, checked out detached at `<sha>`; all remotes /
  fetched refs (e.g. the fork's `upstream`) live only in that clone; removed after (success or failure). Stack: its
  submodules are cloned the same way from the local sibling fork clones at the EXACT gitlinks (refuse if a gitlink is absent
  locally); a fresh `.venv-bench` is built in the scratch from `benchmark/requirements-bench.lock` (`uv venv --python 3.12
  --python-preference only-managed` + `uv pip sync`); before pytest, `mlx_vlm.__file__` and `mlx_serve.__file__` must
  resolve inside the scratch (refuse otherwise).
- **Environments (G10):** explicit managed Python 3.12 everywhere; locked syncs where a lock is authoritative (mlx-serve `uv
  sync --locked`; the fork `uv sync --locked` if its `uv.lock` is tracked, else recorded as unlocked); after every setup and
  test step, `git status --porcelain --untracked-files=no` in the scratch must be empty (else FAIL naming the step).
- **Busy box (G4):** `run` refuses unless (a) no `chain_ops.BUSY` process and no listener on :8000, and (b) no
  `bench.p426_wave1` sequencer is alive, OR one is alive and its `sequence.log` shows `PAUSE: holding` as its last line with
  the `PAUSE` file present. The hold is re-verified before every step; a lost hold → FAIL receipt. Interim procedure (until
  the reservation below ships): the agent never removes `PAUSE` while a gate runs. Durable fix, in the NEXT sequencer build
  (picked up at the next sequencer launch, never mid-run): the sequencer treats any `PAUSE*` file as a hold, and the gate
  creates and removes its own `PAUSE.gate-<pid>`; both take an `flock` on `$STACK_WORKDIR/gate/box.lock` around the check.
- **Receipt (G2):** `$STACK_WORKDIR/gate/<repo>-<sha40>-<policy12>.json`, exclusive create, a FAIL kept (a rerun adds
  `-<n>`): `{repo, sha, verdict, steps: [{name, argv, rc, seconds, summary}], python, lock_sha256, skipped_tests,
  policy_digest, started, ended}`. `policy_digest` = sha256 over: `local_gate.py`, the per-repo skip baseline
  (`benchmark/gate/<repo>.skips.txt`, committed), the parsed parity ref + the eight audit argvs, the step argv list, and the
  repo identity (canonical origin URL). PASS = every step rc 0, every cleanliness check empty, skip list == baseline.
- **check (G5, G7):** stdin = git's pre-push lines. For each non-delete line: the introduced commits = `git rev-list <local>
  --not --remotes=origin` (covers new branch, force push, tags; a missing object → refuse). Require a PASS receipt for
  `<local sha>` under the CURRENT `policy_digest`. Scan every introduced commit's added lines (`git show --format=
  --unified=0 <c>`) with `piicheck.diff_violations` and `modelnames.diff_violations`, and its message with
  `modelnames.message_violations`. Stack only: for each gitlink at `<local sha>`, a PASS receipt for that fork sha, AND the
  gitlink reachable from the fork's `origin/main` after `git fetch origin` in that fork (network failure / not reachable →
  refuse). Any failure → exit 1 naming the `run` command.
- **Hooks (G6):** a machine-local shim directory `${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/hooks/` (installed by
  `bootstrap_machine.sh`, never branch-controlled) holds `pre-push`, `pre-commit`, `commit-msg`. `pre-push` runs
  `$STACK_REPO/.venv-bench/bin/python -m bench.local_gate check --repo <identity>` with the repo identity derived from the
  pushing repo's origin URL (unknown origin → refuse); if `bench.local_gate` is not importable (an old stack branch) →
  refuse. `pre-commit` / `commit-msg` delegate to the repo's own `githooks/` when present (stack), else exit 0 (forks).
  `core.hooksPath` = the shim for the stack and both sibling fork clones (`$STACK_REPO/../mlx-vlm`, `../mlx-serve`; bootstrap
  verifies their origin URLs, warns when a sibling is absent). The agent never uses `--no-verify`.
- Pushes still need in-turn operator approval; the gate is a precondition, not an authorization.

## 3. Steps per repo (mirroring the dead CI)

- **stack:** scratch `.venv-bench` pytest `bench/tests/` with `STACK_WORKDIR` set (P445) and `NLTK_DATA`.
- **mlx-vlm (G8):** (1) `uvx pre-commit run --all-files` then cleanliness; (2) the eight audits, exact argvs:
  `dev/check_upstream_parity.py`, `check_upstream_symbols.py`, `check_upstream_deletions.py … --strict`,
  `check_fork_markers.py`, `check_dead_helpers.py`, `check_body_divergence.py`, `check_upstream_registries.py`,
  `check_call_arguments.py`, each `--upstream-ref <UPSTREAM_SYNC_REF>` parsed from `.github/workflows/upstream-parity.yml`
  (missing → refuse), after `git fetch upstream` in the scratch clone; (3) the fork suite `pytest -q mlx_vlm/tests` (venv:
  `uv sync --python 3.12 --extra test` + `pytest-subtests pytest-asyncio "cryptography>=43.0.0"`). Python 3.10 not covered
  (recorded).
- **mlx-serve (G9):** `uv sync --python 3.12 --locked --extra dev --extra all`; `ruff check src/`; `ruff format --check src/
  tests/`; `pytest tests/`; `uv build` + the wheel and sdist present. 3.11 / 3.13 not covered (recorded).

## 4. Tests (test-first, mocked runner; no real suite in the unit tests)

Receipt exclusive create / FAIL kept / policy digest changes with each input; skip mismatch → FAIL; busy box, live
sequencer without hold, hold lost mid-run → refuse / FAIL; scratch is a clone (no shared config / refs; a fetch leaves the
live repo's refs and config untouched), removed on success and failure; stack scratch imports resolve inside it; the parity
ref parsed from a workflow fixture, missing → refuse; the eight exact argvs incl. `--strict`; cleanliness after a step that
dirties → FAIL; `check`: PASS / missing / FAIL / stale policy / unreadable / delete line / new branch (zero remote sha) / tag
/ force push / add-then-remove leak across two commits / message violation / gitlink without receipt / gitlink unreachable /
fetch failure; shim: unknown origin and missing gate module refuse, delegation to repo hooks; bootstrap installs the shim and
the three `core.hooksPath`.

## 5. Out of scope

The fork's P440 style debt (fixed after P426; its first gated push carries it); Python-version matrices; remote CI;
signed receipts (§1).
