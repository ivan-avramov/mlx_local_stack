# Handoff — 2026-10-25 (session 8 END): P476 done; B2 build mid-way (s1–s2 references, s3 unscored); asks first: P488, P487

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P487, P486, C235, P481, C234 …), then
`docs/specs/p426-b2-tg1-wave2.md` (v3.1; round-3 changes not re-reviewed; C235 rulings folded in) and `docs/reviews/p426-b2/`
(design rounds 1–3 + dispositions). Model names: FULL registry names only, always (chat included).

## Goal and path (C218, C232, C234, C235)

MTP blessing for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` first: finish the B2 build → pre-freeze rehearsal R1–R3 → v8 base
(`bench.p426_freeze`) → pilots → timeout amendment → Wave 2 → B8 / B6 → operator ship call. P475 / P475a stay PARKED.

## First asks of the next session

1. **P488 (new, operator): stack `main` and `origin/main` have diverged** — local ≈ 53 commits unpushed; origin has 4 from the other box
   (`da94479e` m5max close-up docs, `d5508b32` bump `src/mlx-serve` to v0.3.0, `d7451d8f` C182 docs, `fd5ef108` bump `src/mlx-vlm` to
   `08cdd08e`). Both bumps change the serving build (mlx-vlm `08cdd08e` carries production commits — tokenizer serialization, mistral3
   embedding load, reranker / modernbert fixes; mlx-serve v0.3.0), and the gitlinks conflict with ours (mlx-vlm `c9543fc4`, mlx-serve
   `86921f02`). Options: (a) merge and take the fork merge `282fb009` + mlx-serve v0.3.0 as the new serving build — Wave 2 then runs on a
   build Wave 1 did not (both arms equal; cross-wave comparisons need a note; v8 records it); (b) merge keeping our two gitlinks for the
   P426 campaign and re-apply the other box's bumps after the ship call; (c) hold the push. Lead rec: (a) if the other box's production
   fixes are wanted in the shipped stack (C218: certify what ships), with a smoke on the new build before v8; counterpoint: "one serving
   build across waves" (plan v4 §2) is broken. No push without the operator's in-turn approval.
2. **P487: replace the B2 test-writer before Accept** (below).

## State of the world

- Box `m5max-128`, AC 140 W. **GPU IDLE** since 2026-10-25T08:26Z; no router / worker; `:8000` free. OrbStack running (docker grader).
- **Fork pushed** (`08cdd08e..282fb009`: a merge of origin's 7 production commits of 2026-10-22/23 with P476 `c9543fc4`); the stack
  pins `c9543fc4` (serving production unchanged vs Wave 1).
- **P476 DONE** (four-eyes light, accepted): stack suite after the bump 7340 passed / 0 failed (incl. K3); fork suite 6911 / 0 + 8 audits
  green on the merge. Records `docs/reviews/p476/`.
- **P486 rehearsal DONE** (2026-10-24T22:59Z → 2026-10-25T08:26Z): OFF `chain s1`, both picks, pruned registry; 86 rows, every
  invocation rc 0, conv 100 %, 140 W throughout; box torn down. Out-root `$STACK_WORKDIR/p426/tg1-rehearsal-20261024` (+ `.chain.out`,
  `.monitor.log`). Never graded / paired (P279). TODO: extract per-item walls (both picks, both languages) for the B2 §10.2 Go deadline
  and the Wave-2 estimate (label: taken under concurrent CPU load from B2 helpers).

## B2 build (four-eyes STRICT; Go C235)

All build state is scratch under `$STACK_WORKDIR/b2/` (not in the repo): `SLICES.md` (s1 cli … s9 harvest), `briefs/`, `runs/`
(per-run JSON, rc, start / end, diffs). Arms run in LOCKSTEP (P485): each slice starts both arms from the chosen reference.
Cast (C235 Go): arm A = the low-tier worker under the operator's session-local evaluation (notes `b2/sous-agent-observations.md`;
not a rule, not for the repo), arm B = Claude Sonnet (`claude -p`), test-writer `glm-5.2-high` (cursor chat `b2/tw.chat_id`),
change review `gpt-5.6-sol-high` + `glm-5.2-high` — the test-writer is under review (P487).

- **References:** s1 = Sonnet (`runs/s1.sonnet.diff`), s2 = Sonnet (`runs/s2.sonnet.diff`); committed locally in
  `arm-sonnet/mlx_local_stack` as "scratch: s1 / s2 reference". Arm A produced no s1 / s2 candidate (7 runs, zero edits; a
  pre-digested plan run wrote one test file only).
- **s3 finished, NOT yet scored:** `runs/s3.sonnet.diff` (complete; stated gaps: entry not wired in `run_tg1_chain.py` — outside its
  file list; settle / ready record / DNF row left to s4 via an injectable check; method-level tests only) and `runs/s3.sous.diff`
  (arm A timed out at 5400 s but made its first production edits; partial, no report). Next: score both (functional + 1–5
  non-functional: maintainability, testability, documentation, naming, design / cohesion, error handling, codebase consistency, scope
  discipline, security; blind judges = the `blind-judge` agent + `gpt-5.6-sol-high` on anonymized X / Y diffs), pick the s3 reference,
  fold the `run_tg1_chain.py` entry wiring into s4's scope.
- **Frozen tests v6** `b2/frozen/` (190 tests, SHA256, `FROZEN_AT`, `POST_REVEAL_TAGS.json`): still defective (fixture misuse,
  invented interfaces `OpencodeArm(p426=…)` / `abort_manifest`, a C221-incompatible self-test, `p1` vs `p01`); failures triaged by hand,
  all so far test defects. **P487: replace the test-writer before Accept** — lead rec `gpt-5.6-sol-high` as a fresh blind test-writer
  (spec + baseline only, every fixture path validated on the baseline before freezing), change review `glm-5.2-high` + a third family
  available in Cursor; counterpoint: sol leaves the change review it was strongest in; ≈ 1–2 h.
- Clean evaluation copy `b2/eval/mlx_local_stack` = baseline + s1 + s2 (Sonnet) + frozen v6.
- After s9: full stack suite on the final candidate, test-writer second delivery, strict change review (sensitive hunks: harvest / scrub /
  secret gate, pair gate, chain-core policy / ledger / dispositions, locks, probe edits), Accept. While a GPU run is active, cursor-agent
  helpers get a one-line argv pointing at a brief file (P454 / P486). If P488 changes the serving build, B2's baseline moves with it.
- **Pending deliverable to the operator:** the end-of-experiment feedback list on the arm-A worker (source: `b2/sous-agent-observations.md`
  — per-run outcomes, the multi-turn follow-ups with root causes, the progress-visibility suggestions, nudges A / B results).

## Other open items

- **P478** (historical one-off tools targeting pruned / gone models): lead rec retire them as a class into `benchmark/archive/` behind a
  refusal naming their last commit; fix `mem_decompose.lookup_yaml`'s silent 262,144 fallback if kept. After B2; operator decision.
- GPU: nothing citable can run before B2's rehearsal; optional OFF `chain s2 reload` rehearsal (≈ 9 h) only if the operator wants the GPU
  busy (walls for the s2 order; small marginal value).

## Copies to resolve

`$STACK_WORKDIR/b2/{tw,arm-sous,arm-sous-s2,arm-sous-s2b,arm-sous-s3,arm-sonnet,eval}` — scratch clones for B2; harvest the accepted
candidate into the repo at Accept, then delete. No git worktrees of the main checkout.

## Rules learned (session 8)

- Harvesters waiting on helpers key on PIDs / rc files, never `pgrep` patterns.
- Never copy ignored files (`.env`) into helper copies; exclude the venv symlinks via `.git/info/exclude`.
- Frozen tests must be standing-suite quality and validated on the baseline through every fixture path before freezing.
- The fork's pre-push gate checks naming per pushed commit: fix hits in the commit itself.
- Fetch `origin` before planning a push: the other box pushes too.
- GPU is the bottleneck: always look for useful GPU work (memory `gpu-is-the-bottleneck`).

Next decision id C236; discussion ids continue from P488.
