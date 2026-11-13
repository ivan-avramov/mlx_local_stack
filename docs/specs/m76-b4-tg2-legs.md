# M76 B4 — tg2 legs in P426 lever `kv` (A8) — SPEC v1, 2026-11-13 (four-eyes light; C325, C169 GPU go via C323)

## Goal

M76 stage 3 / 4 (`docs/specs/m76-tq4-certification.md` v1.2 §7, A8) needs the harder agentic corpus tg2
(`docs/specs/m65-tg2-corpus.md` v5: Rust / JavaScript / Java / C++, draw `benchmark/m65/tg2_draw.json`, graders `bench.tg2_grade` /
`bench.tg2_materialize`) run through the same per-leg discipline as tg1's P426 Wave 2 (`benchmark/chains/c147/run_tg1_chain.py
--p426`: frozen record, reconciliation, engagement, fail-closed transport policy, pair gate, harvest) for the arm pairs of B3's lever
`kv`. tg2 has never run on the GPU and has no P426-mode leg. Solving it means: a tg2 SCREEN leg (40 items, 10 / language, k = 1) and
DECIDER legs (80 items, 20 / language, sessions s1 / s2 + a same-seed reload) for one M76 arm, with every P426 Wave 2 check, its
injected positives (C169) and a 4-item smoke VALID before any measured leg, and per-item records the B6-style signals and the panel
consume — tg1's legs unchanged.

## Scope (files)

`benchmark/chains/c147/run_tg1_chain.py` (a corpus selector, or a sibling `run_tg2_chain.py` sharing its core — implementer's choice,
stated), `benchmark/bench/p426_wave2.py` (sequencing tg2 tiers), `benchmark/bench/p426_reconcile.py` / `p426_harvest.py` only where
tg2's grader output differs; tests `benchmark/bench/tests/test_m76_b4_*.py`. Read-only: the tg2 graders and draw, tg1's corpus and
legs, the forks.

## Settled constraints

- (C168 / C169 / C323 / C324) SCREEN = diagnostic trigger only (no PASS / REJECT); DECIDER = one formal look at 95 %; a material screen
  finding (macro-average point < −5 pp or any language < −15 pp) triggers the decider; tier prefixes nested (screen = the first 10 per
  language of the decider's 20); the draw's sha256 verified at every leg start.
- (P426 B2 / C220 / C235) the per-leg discipline and failure classes of tg1's Wave 2, unchanged in substance.
- Docker graders (the `aider-benchmark` image) with OrbStack running; grading never in `$TMPDIR` mounts (box-notes).

## Interfaces

- `--corpus tg1|tg2` (default `tg1` = today, byte-identical) on the chain's P426 mode and the Wave 2 sequencer; under `tg2`:
  `--tier screen|decider`; the item list = the draw's tier prefix per language in the draw's permutation order; s1 / s2 seeds 1001 /
  2002 with s2's language order reversed (as tg1); reload = the first 5 items of s1's first language at seed 1001.
- Grading through `bench.tg2_grade` per item (exit-status pass / fail, the strict convergence rule); the item record carries the
  same fields tg1's does (final tree, transcript summary, decode counters, DNF class) plus the language.
- Leg names `tg2-m76-<arm>-{smoke,screen,s1,s2,reload}`; results under `benchmark/results/m76/wave2-tg2/`; the frozen record names the
  draw sha256 and the tier.
- Injected positives (C169) before any measured leg: a known-failing item variant graded FAIL, a known-passing reference graded
  PASS, per language.

## Acceptance criteria

1. Red-first tests (mocked chain ops, the real draw file): tier prefixes and order (s2 reversed), the reload items, sha refusal on a
   modified draw, grader-result mapping to item records, the leg names / paths, `--corpus tg1` byte-identical (golden of today's tg1
   P426 plan and argv).
2. (Designer, GPU) the injected positives and the 4-item smoke VALID on N16 before the screen legs.
3. Existing tg1 / P426 Wave 2 suites unchanged; the stack suite passes or fails only as on the baseline.

## Non-goals

New tg2 items or graders; tg2 outside M76.
