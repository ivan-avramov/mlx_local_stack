# P426 T3 — the serving build S′ and the Wave-1 rerun on committed arms — SPEC v2.1, 2026-10-27 (four-eyes STRICT, C236)

Strict because it changes the P426 evidence namespace, the frozen-build record and how arms are served (isolation between S and S′
evidence; C218) and the serving dependency set. v1 → v2: the design opinion (`docs/reviews/p426-t3/`, round 1 of 3); v2 → v2.1: the
delta review of the [o1] changes (round 2 of 3); changes marked [r2] are NOT re-reviewed.

## Goal

Move the stack's serving build to S′ — the fork's current `main` (`c688e722`), mlx-serve v0.3.0 (`e6a7a5a`) and mlx 0.32.4 — so that
P426 certifies the build that will ship (C236, C218): the stack, its venvs and its gates work on S′ as they did on S, the P426 plan
names S′ as its one serving build, and Wave 1 can rerun on S′ from the same reviewed sequencer into names that can neither overwrite
nor be confused with S's Wave-1 evidence, which stays in the repository untouched.

## Settled (operator)

- C236: P426 moves to the fork's current main and mlx 0.32.4; Wave 1 reruns on S′; Wave 2 runs on S′; S's Wave-1 rows are retained and
  never pooled with S′ rows.
- C218: every arm is a stack commit served as shipped — OFF = the frozen commit, ON = it + exactly the P426 plan's §11 restore (the three
  C177 lines, the `PROVISIONAL P426` note, the seeding test) on a local branch, two frozen worktrees, their diff asserted, no overlay
  files. P471 exempted Wave 1 on S only; the S′ rerun is a new run and follows C218 [o1]. P472: M1 stays in-process and reads the ON
  registry from the ON commit.
- AGENTS.md: forks are edited in `../mlx-vlm` / `../mlx-serve`, never `src/*`; transport failures abort; no pooling across differing
  fingerprints; `.venv-bench` is rebuilt only from `benchmark/requirements-bench.lock`.
- The fork is not changed by T3 (its own session owns it); a fork defect T3 finds is reported, not fixed here.

## Assumptions (designer; not settled)

- A1. The fork's MTP / verifier exactness tests pass on mlx 0.32.4 on this box: measured 2026-10-27 in a scratch venv with transformers
  5.14.1 (1124 passed, 1 skipped, 1 xfailed); S′ resolves transformers 5.15.0, so acceptance 3 supersedes A1 [o1].
- A2. `uv lock` from the merged tree resolves mlx 0.32.4, mlx-metal 0.32.4, mlx-audio 0.6.2, datasets 5.0.1, transformers 5.15.0,
  huggingface-hub 1.12.0 (scratch clone, P499); the provisional S′ serves both picks draft-OFF (P499 rehearsal).
- A3. No stack code uses the renamed runtime knobs `spec_draft_model` / `spec_draft_kind` (only committed result rows and one doc row).

## Supported conditions

This box (`m5max-128`), Python 3.12 managed venvs, the committed `main_models.yaml`, the P426 entry
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, the committed `benchmark/results/p426/ids.json` (unchanged), Wave-1 axes math500,
cjudge, vision, reasoning, m1; build labels `s` (S, historical) and `s2` (S′).

## 1. The merge (designer, before the implementer)

The designer merged GitHub `main` (4 commits from the other box) into a copy of local `main` as B0 (`1a4187e6`): `src/mlx-vlm` →
`c688e722`, `src/mlx-serve` → `e6a7a5a`; `docs/handoff.md` ours (the other box's 2026-10-18 section is closed); the other box's
`C182` (an id already in use) renumbered `C237`. The change review sees B0's diff against local `main` as part of the candidate.

## 2. Dependencies and venvs

- `uv.lock` re-resolved with `uv lock` (no `--upgrade`); the only intended version changes are those the fork's requirements force
  (A2). Any further change is listed with its cause.
- `benchmark/requirements-bench.lock` regenerated as the exact pins of a `.venv-bench` that runs the green suite on S′: mlx /
  mlx-metal 0.32.4 (equal to `uv.lock`), the fork's new requirements satisfied (`datasets>=4.0.0`, `mlx-audio>=0.6.2`), everything else
  unchanged unless a requirement forces it; the header comment updated (date, cause). `uv pip sync` of the lock into a fresh venv
  succeeds and the venv imports `mlx.core`, `mlx_vlm`, `mlx_serve`, `pytest`.
- `scripts/bootstrap_machine.sh` needs no change unless the lock regeneration shows it must; if it changes, its own tests cover it.
- The fork-suite environment [o1]: a scratch venv whose `mlx`, `mlx-metal`, `transformers`, `huggingface-hub`, `datasets` and
  `mlx-audio` equal `uv.lock`'s, plus the fork's `test` extra and `bench.local_gate.FORK_EXTRAS`; never the serving `.venv`.

## 3. Stack code on S′

Whatever the stack suite shows broken by the new dependencies is fixed in the stack (never in `src/*`), each fix the smallest that
restores the documented behaviour, each named with the failing test that shows it. No behaviour change beyond that. A failure caused by
the fork is reported with the failing test and left failing.

**The local gate on S′** [o1] [r2] — a code change to `bench.local_gate`: `current_parity` reads the upstream ref from
`.upstream-sync-ref` at the sha when present, else from `.github/workflows/upstream-parity.yml`; the audit list is the fork's own
`dev/ci.py` `AUDITS` at that sha (S′: nine, incl. `check_upstream_test_copies.py`), derived per sha, not a fixed tuple. A PASS receipt
for the stack, `c688e722` and `e6a7a5a` is part of acceptance.

## 4. The Wave-1 rerun on S′

The Wave-1 tooling (`bench.p426_wave1`, `bench.p426_leg`, `bench.p426_plan`, `bench.p426_harvest`, `bench.p426_panel`) takes a build
label so the same reviewed sequencer runs Wave 1 again on S′, with each arm served from its own committed worktree.

- **Label.** `--build <label>`, grammar `^[a-z][a-z0-9]{0,7}$`. `bench.p426_wave1` requires it [o1] (the one existing test that calls the
  sequencer without it, `test_main_refuses_a_workdir_that_is_not_stack_workdir`, gains `--build s` and keeps its assertion [r2]); `bench.p426_leg` defaults to `s` and
  the sequencer passes `--build` only when the label is not `s`. Under `s` every name, path, argv, record and receipt is byte-identical
  to today's (the existing tests pass unchanged).
- **Expected build per label, in code** [o1]: `s2` → `mlx_vlm` `c688e7223ac83f8060fde15a19e48a6c5186d239`, `mlx_serve`
  `e6a7a5a6f589b5e11872c731443acc2301a49060`, `production_ref` `b26fa7c9faf23bc3167db3419504ef0b2b82a8e6` (the fork's `qualify` requires a
  STRICT ancestor of the reviewed head; `b26fa7c9..c688e722` changes `handoff.md` only) [r2], mlx 0.32.4 in both venvs; `s` → the values its record
  already holds (no new check). A record whose pins differ from its label's expected build refuses (NOT_STARTED), even when
  self-consistent with the tree.
- **Names under a label `b` ≠ `s`** (S′ uses `s2`):
  - frozen record `<workdir>/p426/frozen.<b>.json`; a leg and the sequencer under `b` read that path and no other; a missing file refuses
    for the missing file [o1];
  - tunes `p426<b>-<arm>-b<n>`, `p426<b>-<arm>-smoke`; every row, manifest and sidecar follows from the tune;
  - leg names `<axis>-p426<b>-<arm>-…` [o1], hence the receipt, `.refused-*`, `.stdout`, `.watch.log`, `.power.json` files and the
    per-request session prefix `MLX_BENCH_SESSION_PREFIX=p426-<leg name>`;
  - M1 qualify directory `<workdir>/p426/<b>/m1/<tune>`;
    - harvest dossiers `benchmark/results/p426/wave1.<b>/<leg>/` and run files `benchmark/results/p426/wave1.<b>/run/`; a code change to
    `bench.modelnames`: its exemption for harvested Wave-1 evidence matches `benchmark/results/p426/wave1(\.[a-z][a-z0-9]{0,7})?/` [o1] [r2];
  - the sequencer's `--out`: it writes a `.build` marker on first start; an `--out` whose marker names another label, or that holds
    receipts or a `sequence.log` without a marker, refuses [o1].
- **Arms as commits** [o1]. Under `b` ≠ `s` the ON overlay is retired: `--registry-on` is refused; the sequencer takes
  `--stack-root-off <WT_off>` and `--stack-root-on <WT_on>`; every leg runs (cwd, router, driver, server log) from its arm's worktree and
  serves that worktree's committed `main_models.yaml`. `WT_on`'s HEAD is `WT_off`'s HEAD + one commit whose diff is exactly the restore
  paths (`main_models.yaml`: the entry's three C177 lines and the `PROVISIONAL P426` note; `benchmark/bench/tests/test_opencode_probe_seeding.py`);
  the sequencer asserts that diff at patch level — exactly the entry's three C177 lines and the `PROVISIONAL P426` note in
  `main_models.yaml`, and exactly the P426 plan's §11 changes in the seeding test (`per_query` → `joint_v1`, source `registry`), no
  other hunk, mode or metadata change [r2] — both trees clean (no tracked change: `git status --porcelain --untracked-files=no`, as K2
  does today; generated outputs are checked by the stem refusal) [r2] and both heads equal to the record before the first leg, and the
  leg re-asserts its own tree at entry and exit: under `b` its live head is compared with `stack_head_off` (OFF) or `stack_head_on` (ON)
  of its own arm worktree, never a missing `stack_head` [r2]. M1 runs from its arm's worktree (P472); the fork's `qualify` writes the
  ON registry it serves as `overlay-<entry>.yaml` even when the committed registry is already ON — the leg asserts that file's sha256 ==
  the ON worktree's `main_models.yaml` and records both (operator ask P504) [r2].
- **The frozen record under `b`** carries `build`, both heads (`stack_head_off`, `stack_head_on`), both trees clean, `mlx_vlm`,
  `mlx_serve`, `production_ref`, both registry shas (each worktree's `main_models.yaml`), the sha256 of `uv.lock` and
  `benchmark/requirements-bench.lock`, and per worktree and venv (`.venv`, `.venv-bench`) the installed versions of mlx, mlx-metal,
  transformers, huggingface-hub, datasets, mlx-audio [o1]. Every K2 check compares the live state with it at leg entry and exit; a
  difference refuses (entry: NOT_STARTED) or invalidates (exit).
- **Order of checks** [o1]: the sequencer validates the record (label, expected build, both trees, venvs) before it harvests the run files.
- **Isolation.** A leg under `b` never reads, writes, renames or deletes a path of another label; the "no output of the leg's stem may
  exist" refusal applies to its own stems; the resume rule reads only its own label's receipts and dossiers.
- **The panel** [o1]: `bench.p426_panel` takes the label; its OFF / ON tunes are `p426<b>-off` / `p426<b>-on` (`s` unchanged).
- Out of the tooling (designer): the frozen worktrees `$STACK_WORKDIR/worktrees/stack-p426-s2-off` and `…-s2-on`, each with `.venv` from
  `uv sync --frozen` and `.venv-bench` from `uv pip sync` of the bench lock, built fresh (never copied) [o1]; S's worktree is kept until
  its removal is separately justified.

Success path: the designer cuts S′ (the accepted T3 commit), creates `p426-on-s2` = S′ + the restore commit, builds both worktrees and
their venvs, writes `frozen.s2.json`, runs `bench.p426_wave1 --build s2 --stack-root-off … --stack-root-on … --out
$STACK_WORKDIR/p426/wave1.s2 …`; the 10 smokes then the 20 legs write `p426s2-*` rows and `wave1.s2/` dossiers; S's files are
byte-unchanged.

Failure paths: (1) `frozen.json` copied as `frozen.s2.json` → refused for the expected-build mismatch before any harvest, nothing
launched, rc 1, nothing of S touched. (2) `WT_on` with an extra change beyond the restore → refused before the first leg. (3) a worktree
whose `.venv` has mlx 0.32.3 → the leg refuses NOT_STARTED.

**Stack code changed by T3** [r2]: `uv.lock`, `benchmark/requirements-bench.lock`, `bench.local_gate`, `bench.modelnames`,
`bench.p426_wave1`, `bench.p426_leg`, `bench.p426_plan`, `bench.p426_harvest`, `bench.p426_panel`, their tests, and what §3's suite run
shows broken.

## 5. Documents

- P426 plan (`docs/specs/p426-fable-mtp-recert.md`) §2: R11 names S′ (C236) with its pins and the two committed arms; S's Wave 1 is
  recorded as superseded, retained, never pooled.
- `docs/box-notes.md` [o1]: the 2026-10-17 P369 note stays verbatim and is scoped to the fork at S (0.32.4 broke its verifier
  exactness); a separate 2026-10-27 note: for the fork at `c688e722` and later the exact verifier kernels require 0.32.4 and fail on
  0.32.3; the rule "re-run the fork's verifier exactness tests on any mlx bump before serving MTP" stays.
- `docs/specs/p405-kv-scheme-precedence.md:60`: the renamed knobs (`draft_model` / `draft_kind`).
- `benchmark/README.md` where it states the bench venv's mlx version or the Wave-1 names, if it does.

## 6. Tests

- Behaviour tests of §4: the label grammar; `--build` required by the sequencer; `s` byte-identical names and argv (existing tests);
  `s2` names for every axis, the smoke, the leg name, the session prefix and the M1 directory; the expected-build refusal (a
  self-consistent record of another build); the frozen-record path per label (missing `frozen.s2.json` refuses for the missing file);
  the `--out` marker; arms as commits (the restore-diff assertion, `--registry-on` refused under `s2`, each arm's leg runs from its
  worktree); the venv-version check; validation before the run-file harvest; resume per label; isolation (a run under `s2` in a tree
  holding `s` outputs neither refuses on them nor touches them); harvest paths per label and the naming exemption; the panel tunes.
- The local gate's audit list and upstream ref per fork sha (fixtures of both layouts).

## 7. Acceptance criteria

1. `uv lock --check` passes; `uv sync --frozen` gives mlx 0.32.4; a fresh `.venv-bench` from the new bench lock imports `mlx.core`
   0.32.4, `mlx_vlm`, `mlx_serve`, `pytest`.
2. The stack suite on S′ (`cd benchmark && env -u STACK_WORKDIR ../.venv-bench/bin/python -m pytest -q -p no:cacheprovider
   bench/tests/`): 0 failed, or fails only as on B0's parent (local `main`), each listed.
3. In the §2 fork-suite environment: the fork's MTP / verifier exactness tests pass, and the fork's full suite fails only as the fork's
   own gate records (`KNOWN_UPSTREAM_FAILURES` / strict xfails).
4. §4's tests pass; the existing P426 tests pass unchanged.
5. `bench.local_gate` PASS receipts for the candidate stack commit, `c688e722` and `e6a7a5a`.
6. Smoke on the candidate [o1] (designer, GPU): from scratch OFF and ON worktrees of the candidate (ON = + the restore commit), a lean
   router serving each committed registry loads the P426 entry, completes 3 requests; ON requests with ≥ 2 generated tokens carry the
   `draft_*` counters, OFF requests none; teardown verified. The fork's #2545 default-temperature change is shown not to reach the M1
   qualify path (explicit sampling) or is reported [o1].
7. §5's documents updated.
8. No change to the client carriers, `ids.json`, B2's files, or any committed result row; `main_models.yaml` changes only on `p426-on-s2`.

## 8. Non-goals and residuals

- Non-goals: fork changes; registry / sampling / KV changes on `main`; B2 (it rebases onto S′ separately); B8 / B6 (they take the label
  when built); deleting S's evidence or worktree; the probe-only drafter of `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` (served
  draft-OFF; the fork's handoff says it no longer loads).
- Residuals: the fork syncs weekly; S′ is fixed at `c688e722` for P426 and later fork commits enter only through a certification
  (P498, not ruled). Wave 1 on S and on S′ differ in code; any comparison across them is descriptive only. A hand-launched process
  outside the sequencer is outside the supported conditions.
