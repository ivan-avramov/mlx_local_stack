# P426 T3 — the serving build S′ and the Wave-1 rerun namespace — SPEC v1, 2026-10-27 (four-eyes STRICT, C236)

Strict because it changes the P426 evidence namespace and the frozen-build record (isolation between S and S′ evidence) and the
serving dependency set.

## Goal

Move the stack's serving build to S′ — the fork's current `main` (`c688e722`), mlx-serve v0.3.0 (`e6a7a5a`) and mlx 0.32.4 — so that
P426 certifies the build that will ship (C236, C218): the stack, its venvs and its gates work on S′ as they did on S, the P426 plan
names S′ as its one serving build, and Wave 1 can rerun on S′ from the same reviewed sequencer into names that can neither overwrite
nor be confused with S's Wave-1 evidence, which stays in the repository untouched.

## Settled (operator)

- C236: P426 moves to the fork's current main and mlx 0.32.4; Wave 1 reruns on S′; Wave 2 runs on S′; S's Wave-1 rows are retained and
  never pooled with S′ rows.
- C218: arms are stack commits served as committed; the frozen worktree runs router and driver (P426 plan §2, R11).
- AGENTS.md: forks are edited in `../mlx-vlm` / `../mlx-serve`, never `src/*`; transport failures abort; no pooling across differing
  fingerprints; `.venv-bench` is rebuilt only from `benchmark/requirements-bench.lock`.
- The fork is not changed by T3 (its own session owns it); a fork defect T3 finds is reported, not fixed here.

## Assumptions (designer; not settled)

- A1. The fork's MTP / verifier exactness tests pass on mlx 0.32.4 on this box (measured 2026-10-27: 1124 passed, 1 skipped, 1
  xfailed, scratch venv, transformers 5.14.1), and the fork's full gate passed on the other box (9205 passed).
- A2. `uv lock` from the merged tree resolves mlx 0.32.4, mlx-metal 0.32.4, mlx-audio 0.6.2, datasets 5.0.1, transformers 5.15.0,
  huggingface-hub 1.12.0 (measured in a scratch clone, P499); the provisional S′ serves both picks (P499 rehearsal, running).
- A3. No stack code uses the renamed runtime knobs `spec_draft_model` / `spec_draft_kind` (only committed result rows and one doc row
  mention them).

## Supported conditions

This box (`m5max-128`), Python 3.12 managed venvs, the committed `main_models.yaml` (unchanged by T3), the P426 entry
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, the committed `benchmark/results/p426/ids.json` (unchanged), Wave-1 axes math500,
cjudge, vision, reasoning, m1.

## 1. The merge (designer, before the implementer)

The designer merges GitHub `main` (4 commits from the other box: `da94479e`, `d5508b32`, `d7451d8f`, `fd5ef108`) into local `main` and
resolves: `src/mlx-vlm` → `c688e722`, `src/mlx-serve` → `e6a7a5a`, the docs by content (the other box's text kept, our handoff
remains the one handoff). That commit is the implementer's baseline B0. The change review sees B0's diff against local `main` as
part of the candidate.

## 2. Dependencies and venvs

- `uv.lock` re-resolved with `uv lock` (no `--upgrade`); the only intended version changes are those the fork's requirements force
  (A2). Any further change is listed with its cause.
- `benchmark/requirements-bench.lock` regenerated as the exact pins of a `.venv-bench` that runs the green suite on S′: mlx /
  mlx-metal 0.32.4 (equal to `uv.lock`), the fork's new requirements satisfied (`datasets>=4.0.0`, `mlx-audio>=0.6.2`), everything else
  unchanged unless a requirement forces it; the header comment updated (date, cause). `uv pip sync` of the lock into a fresh venv
  succeeds and the venv imports `mlx.core`, `mlx_vlm`, `mlx_serve`, `pytest`.
- `scripts/bootstrap_machine.sh` needs no change unless the lock regeneration shows it must; if it changes, its own tests cover it.

## 3. Stack code on S′

Whatever the stack suite shows broken by the new dependencies is fixed in the stack (never in `src/*`), each fix the smallest that
restores the documented behaviour, each named with the failing test that shows it. No behaviour change beyond that. A failure caused by
the fork is reported with the failing test and left failing.

## 4. The Wave-1 build label

The Wave-1 tooling (`bench.p426_wave1`, `bench.p426_leg`, `bench.p426_plan`, `bench.p426_harvest`) takes a build label so the same
reviewed sequencer runs Wave 1 again on S′.

- **Label.** `--build <label>` on `bench.p426_wave1` and `bench.p426_leg`; grammar `^[a-z][a-z0-9]{0,7}$`; default `s`. Under `s` every
  name, path, argv, record and receipt is byte-identical to today's (the existing tests pass unchanged). The leg argv the sequencer
  builds carries `--build` only when the label is not `s`.
- **Names under a label `b` ≠ `s`** (S′ uses `s2`):
  - frozen record `<workdir>/p426/frozen.<b>.json` (S keeps `frozen.json`);
  - tunes `p426<b>-<arm>-b<n>` and `p426<b>-<arm>-smoke` (S keeps `p426-<arm>-b<n>`, `p426-<arm>-smoke`); every row, manifest and
    sidecar of a leg follows from its tune;
  - M1 qualify directory `<workdir>/p426/<b>/m1/<tune>` (S keeps `<workdir>/p426/m1/<tune>`);
  - harvest dossiers `benchmark/results/p426/wave1.<b>/<leg>/` and run files `benchmark/results/p426/wave1.<b>/run/` (S keeps
    `benchmark/results/p426/wave1/…`).
- **The frozen record** gains a `build` field (the label). A record without it is build `s`. A leg or sequencer started with label `b`
  refuses (NOT_STARTED receipt, as for any K2 failure) when the record's build is not `b`. All other K2 checks are unchanged.
- **Isolation.** A leg under `b` never reads, writes, renames or deletes a path of another label; the existing "no output of the
  leg's stem may exist" refusal applies to its own stems. The resume rule (skip a VALID, harvested leg) reads only its own label's
  receipts and dossiers.
- **The ON overlay** for `b` is generated by `bench.p426_overlay` from S′'s registry into `<workdir>/p426/registry-on.<b>.yaml` (S keeps
  `registry-on.yaml`); its sha goes into `frozen.<b>.json` as for S.
- Out of the tooling: the frozen worktree for S′ is `$STACK_WORKDIR/worktrees/stack-p426-s2` (designer; S's worktree is kept until its
  removal is separately justified).

Success path: the designer cuts S′ (the accepted T3 commit), builds the frozen worktree, writes `frozen.s2.json` (`stack_head`,
`stack_clean`, `mlx_vlm` = `production_ref` = `c688e722`, `mlx_serve`, both registry shas, `build: "s2"`), generates
`registry-on.s2.yaml`, runs `bench.p426_wave1 --build s2 …` from the frozen worktree; the 10 smokes then the 20 legs write `p426s2-*`
rows and `wave1.s2/` dossiers; S's files are byte-unchanged.

Failure path: `bench.p426_wave1 --build s2` with `frozen.json` copied as `frozen.s2.json` (no `build`, or `build: "s"`): the first leg
refuses with a NOT_STARTED receipt naming the build mismatch, nothing is launched, the sequencer stops (rc 1), nothing of S is touched.

## 5. Documents

- P426 plan (`docs/specs/p426-fable-mtp-recert.md`) §2: R11 names S′ (C236) with its pins; S's Wave 1 is recorded as superseded,
  retained, never pooled.
- `docs/box-notes.md`: the 2026-10-17 P369 note gets a dated correction (2026-10-27): the fork's exact verifier kernels now require
  mlx 0.32.4 and fail on 0.32.3; the rule "re-run the fork's verifier exactness tests on any mlx bump before serving MTP" stays.
- `docs/specs/p405-kv-scheme-precedence.md:60`: the renamed knobs (`draft_model` / `draft_kind`).
- `benchmark/README.md` where it states the bench venv's mlx version or the Wave-1 names, if it does.

## 6. Tests

- Behaviour tests of §4: the label grammar; `s` byte-identical names and argv (existing tests); `s2` names for every axis and the
  smoke; the frozen-record build check (missing field = `s`, mismatch refuses with NOT_STARTED, match proceeds); the resume rule per
  label; isolation (a run under `s2` in a tree holding `s` outputs neither refuses on them nor touches them); harvest paths per label.
- The stack suite on S′, and the fork suite run with the stack's `.venv` (`PYTHONPATH=src/mlx-vlm`).

## 7. Acceptance criteria

1. `uv lock --check` passes; `uv sync --frozen` gives mlx 0.32.4; a fresh `.venv-bench` from the new bench lock imports `mlx.core`
   0.32.4, `mlx_vlm`, `mlx_serve`, `pytest`.
2. The stack suite on S′ (`cd benchmark && env -u STACK_WORKDIR ../.venv-bench/bin/python -m pytest -q -p no:cacheprovider
   bench/tests/`): 0 failed, or fails only as on B0's parent (local `main`), each listed.
3. The fork's MTP / verifier exactness tests pass in the stack's `.venv` on S′ (the A1 selection), and the fork's full suite in the
   stack's `.venv` fails only as the fork's own gate records (`KNOWN_UPSTREAM_FAILURES` / strict xfails).
4. §4's tests pass; the existing P426 tests pass unchanged.
5. §5's documents updated.
6. No change to `main_models.yaml`, the client carriers, `ids.json`, B2's files, or any committed result row.

## 8. Non-goals and residuals

- Non-goals: fork changes; registry / sampling / KV changes; B2 (it rebases onto S′ separately); B8 / B6 (they take the label when
  built); deleting S's evidence or worktree; the probe-only drafter of `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` (served draft-OFF; the fork's handoff says it no longer loads).
- Residuals: the fork syncs weekly; S′ is fixed at `c688e722` for P426 and later fork commits enter only through a certification
  (P498, not ruled). Wave 1 on S and on S′ differ in code; any comparison across them is descriptive only.
