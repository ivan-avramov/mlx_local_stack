# P426 T3 — design opinion (review-panel opinion, the one per work item) — dispositions

Spec v1 `863fb081` → v2 (changes marked [o1], not re-reviewed). Panel 2026-10-27 15:53–15:57Z, context `checkout` (read-only copy at
`863fb081` + the S′ fork at `c688e722` + the relocked lock under `review_material/`):

| Member | Runtime | Model | Session | Status |
|---|---|---|---|---|
| sol | cursor-agent `--mode ask` (user instructions unconfirmed) | `gpt-5.6-sol-high` | `9ef6227e-a8bb-410c-8e20-7c4f8b4379c1` | returned |
| glm | cursor-agent `--mode ask` (user instructions unconfirmed) | `glm-5.2-high` | `c8083af0-ef66-46d0-b5f1-d388c5be88a6` | returned |
| sonnet | claude `-p`, `--setting-sources project,local`, tools Read/Grep/Glob | `claude-sonnet-5-5` | `501c8ca3-c370-4c96-8afe-29a989f881bf` | returned |

Shared: Claude Sonnet shares the designer's vendor; it is not the T3 implementer's session (a fresh one implements).

| # | Finding (raised by) | Disposition | Why |
|---|---|---|---|
| 1 | The S′ rerun serves ON from an overlay, against C218 (sol P1, blocker) | **adopted** (§4 arms as commits) | C218 requires committed arms with no overlay; P471 exempted only Wave 1 on S. The rerun is a new run. Original. |
| 2 | The label is matched only to a self-declared field, not the build (sol P2, sonnet F2) | **adopted** (expected build per label in code) | A self-consistent record of the wrong build would label S evidence as S′, which is the confusion the goal forbids. |
| 3 | `--out`, leg names, receipts and the session prefix are not labelled (sol P3, glm F5, sonnet F1) | **adopted** (labelled leg names, `.build` marker) | Receipts would be named the same under both builds, and a reused `--out` mixes the runs. |
| 4 | The local gate cannot gate S′'s fork: 8 audits vs 9, ref file moved (sol P4) | **adopted** (§3, acceptance 5) | Confirmed: `local_gate.AUDITS` lists 8, and the fork at `c688e722` runs 9 and keeps the ref in `.upstream-sync-ref`. Without this the stack cannot be released on S′. |
| 5 | No smoke in acceptance, although C236 asks for one (sol P5) | **adopted** (acceptance 6, OFF and ON, from committed arms) | The goal is serving S′; P499 covers OFF on a provisional build only. |
| 6 | The fork suite cannot run in the serving `.venv` (no pytest or test extras) (sol P6) | **adopted** (§2 fork-suite environment) | Confirmed: the root project does not install the fork's `test` extra. |
| 7 | Strict instead of the light mode in C236 (sol P7, scope request) | **declined**; shown to the operator | The four-eyes rule puts isolation (S vs S′ evidence), C218 arm serving and data-model changes under strict. "Light" in C236 was the designer's wording, not an operator setting. |
| 8 | The frozen worktrees' venvs are neither specified nor checked (glm F1, sonnet F3) | **adopted** (fresh venvs, versions in the record, K2 check) | A worktree on mlx 0.32.3 would fail or silently measure another dependency set. |
| 9 | The box-notes correction would erase the S-scoped observation (glm F2) | **adopted** (keep it verbatim, add a separate note) | The S-scoped fact stays true for that fork. |
| 10 | A1 was measured on transformers 5.14.1 (glm F3, sonnet F8) | **adopted** (A1 superseded by acceptance 3) | Labelling. |
| 11 | The read path for `frozen.<b>.json` is not stated (glm F4) | **adopted** | Its own failure mode: missing file vs build mismatch. |
| 12 | Consumers hard-code S names: the naming exemption and the panel tunes (sonnet F4) | **adopted** (both take the label) | Confirmed: `modelnames.py` exempts only `wave1/`, and `p426_panel.py:18` fixes `p426-off`/`p426-on`. |
| 13 | The run files are harvested before the record is checked (sonnet F5) | **adopted** (validate first) | A rejected record would otherwise reach `wave1.s2/run/`. |
| 14 | The default label `s` is silent (sonnet F6) | **adopted** for the sequencer (required); the leg keeps its default | The leg is launched only by the sequencer, and its legacy argv must stay byte-identical. |
| 15 | #2545's default temperature may reach M1 (sonnet F7) | **adopted** (acceptance 6) | M1 runs fork Python generation in-process. |
| SR | Record the label and lock shas in each receipt and manifest (sonnet); a test that `wave1/run/` is untouched (glm S2); a worktree-venv acceptance check (glm S1) | glm S1 and S2 **adopted** (into §4 and §6); sonnet's SR **declined** | Receipts already carry `frozen_sha`, and the record now holds the lock shas and versions, so the build is identified transitively. |
