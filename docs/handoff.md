# Handoff — 2026-10-31 (session 12 END: C249 → C258 MTP ON CERTIFIED for three entries; B2 ACCEPTED (C259) and landed; local state harvested and cleaned (C260); one end-of-session push)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C260, C259, C258, P551, C257, P550, P547), the PLAN
queue after B2, and `docs/reviews/cleanup-2026-10/dispositions.md` (what was deleted, what was kept, what was lost). Model names: FULL
registry names only, always. Review rounds: 3 per artifact (AGENTS.md).

## FIRST — verify the end of session 12 (each step was done after this file was committed; any "no" is a blocker)

1. `git fetch && git status`: `main` == `origin/main` and `evidence` == `origin/evidence` (one push, `main` at level full after a PASS gate on
   its tip — the receipt in `$STACK_WORKDIR/gate/`; `evidence` at data-only).
2. The 240 C248 exactness arrays are on the HF dataset `caslca/mlx-local-stack-evidence` (C260) with the sha256 of
   `evidence:backfill/2026-10-30-c260a/EXTERNAL_MANIFEST.json`.
3. The `caslca/Qwen3.6-27B-Opus-Distill-OptiQ-4bit-mtp-drafter` card shows the interval `1.74×[1.71,1.77]` (re-uploaded with the push; the
   first upload said 1.78, a hand-rounding the generated scoresheet corrected).
4. `$STACK_WORKDIR` holds only the Keep set (`nltk_data`, `polyglot-benchmark`, `opencode-2.0.20`, `vision_gate_images`, `gate/`,
   `locks/`); `git worktree list` shows only `main`; no local branches besides `main` / `evidence` (stack) and `main` (forks).
   If the cleanup stopped part-way, finish it per `docs/reviews/cleanup-2026-10/dispositions.md` (its preconditions first).

## State — 2026-10-31

- **C249 / C258**: MTP ON CERTIFIED for `Qwen3.8-27B-mlx-uniform-4bit`, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`,
  `Ornith-1.0-35B-mlx-uniform-4bit` (normal-length decode 1.72× / 1.74× / 1.45×, outputs byte-identical; 256K decode −13% / −6% /
  −9%, a flag; 256K peak +0.3–0.5 GB). Numbers: the generated `benchmark/results/c249/scoresheet.json`. Drafter cards updated.
  `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` stays PROVISIONAL (C244) until Wave 2.
- **B2 ACCEPTED (C259) and on `main`** (`97db61da`): the Wave-2 tg1 legs, sequencer, harvest; the independent frozen set (525 / 527; the 2
  baseline-only s0 checks skip after the B2 base, registered in `benchmark/gate/stack.skips.txt`). Build records in
  `docs/reviews/p426-b2/` (+ `build/`).
- **Evidence (C260)**: the P369 / C249 run reports and raw logs, the Wave 1 / S′ raw legs, the remaining opencode transcripts, m62–m65,
  gate receipts and the uncited result dirs on `evidence` (`fc4bf618`, scrubbed, fail-closed); the parked P475 / P475a / P476 code on
  `evidence` (`05161ba0`), its review texts in `docs/reviews/parked/`; P541 / P542 / B2 build records in `docs/reviews/*/build/`.
- Lost by decision (C260, verified twice by sol): PII-bearing opencode DBs, probe working directories, scratch `tmp/`, venvs — the list is
  in the cleanup dispositions.

## Next, in order

1. FIRST 1–4.
2. **Wave 2 per PLAN** (B2 accepted): v8 freeze → rehearsals R1–R3 → pilots → amendment → Wave 2 legs (first pick
   `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`; OFF arm = `main` + revert of the C244 hunk, P525; arms are fresh worktrees from `main`)
   → B8 / B6. Read spec §1, §7, §9, §16.8 before launching; the sequencer as shipped; `bench_watch.py` with `PYTHONPATH=benchmark`, its
   liveness checked after start (P547).
3. Optional (C258): a 128K / 192K `qualify.py` ABBA point per C258 entry (the crossover; needs a fresh fork root at `fd67082a` and C249-style
   worktrees) — descriptive GPU filler, never during a gate or a suite.
4. P503 (load-sensitive stack tests).

## Rules learned (session 12)

- A measurement launcher checks its monitor is alive after start and stops the measurement if it died (P547).
- A replicate claim needs the replicates read (P550). Numbers in docs come from a generated scoresheet, never hand-rounded (C249 1.78 → 1.77).
- Never edit a running bash script. Check a Write succeeded before committing it. Source the machine config in the shell that pushes.
- A wrapper whose default path is `set -- <path>` when `$# = 0` loses it once any flag is passed. A candidate copy without a local `main`
  fails merge-base tests. A new skip needs its line in `benchmark/gate/<repo>.skips.txt`.
- Scratch commits in review copies bypass the public-repo scans: landing them on `main` surfaces naming / PII findings.
- `evidence_backfill --files-from` stages every listed file as a normal file (arrays included, all in memory): list arrays only via the
  directory mode, which sends them to `EXTERNAL_MANIFEST.json`.
- Before deleting local state: inventory by path + hash against `main`, `evidence` and the HF dataset; a hash in a manifest restores
  nothing; file every review / report / brief first; have the table verified cold.

Next decision id C261; discussion ids continue from P562.
