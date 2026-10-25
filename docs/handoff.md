# Handoff — 2026-10-24 (session 8 CHECKPOINT, mid-run): P476 done; B2 build in progress (four-eyes STRICT, Go C235); GPU OFF rehearsal running (P486)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P486, C235, P481, C234, C233 …), then
`docs/specs/p426-b2-tg1-wave2.md` (v3.1, round-3 changes not re-reviewed, C235 rulings folded in), `docs/reviews/p426-b2/` (design
rounds 1–3 + dispositions). Model names: FULL registry names only, always (chat included).

## Goal and path (C218, C232, C234, C235)

MTP blessing for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` first: B2 build (in progress) → pre-freeze rehearsal R1–R3 → v8 base
(`bench.p426_freeze`) → pilots → timeout amendment → Wave 2 → B8 / B6 → operator ship call. P475 / P475a stay PARKED.

## State of the world (checkpoint time ≈ 2026-10-25T00:35Z)

- Box `m5max-128`, AC 140 W. **GPU BUSY: P486 OFF rehearsal** — `run_tg1_chain.py chain s1` (both historical picks, predictor OFF,
  pruned registry), chain pid 56610 (router 56637, worker 56721), out-root `$STACK_WORKDIR/p426/tg1-rehearsal-20261024`, stdout
  `….chain.out`, 5-min monitor `….monitor.log` (my session-local tick loop dies with the session; the chain's own WATCH lines in
  `RUNLOG.md` continue). Stop cooperatively: `touch $STACK_WORKDIR/p426/tg1-rehearsal-20261024/STOP`; afterwards verify `:8000`
  free / no worker (`scripts/stack_stop.sh` if anything survives). Rows are never graded / paired (P279); harvest the per-item walls
  for the B2 §10.2 Go deadline and the Wave-2 estimate (label: concurrent CPU load from B2 helpers).
- Stack `main` = `77ed5853` (47 commits not pushed, incl. P476 `2e258b99` / `45dd68d2`, bump `f1e47df9`). **Fork pushed**
  (`08cdd08e..282fb009`, merge of origin's 7 production commits from 2026-10-22/23 with P476 `c9543fc4`); the stack pins `c9543fc4`
  (serving production unchanged — the merge's other production commits are NOT in the stack).
- **P476 DONE** (four-eyes light, accepted): stack suite after the bump 7340 passed / 0 failed (incl. K3); fork suite 6911 / 0 failed +
  8 audits green on the merge. Records `docs/reviews/p476/` (change round 4, test-writer round 3, frozen tests under `run/`).

## B2 build (four-eyes STRICT; cast per C235 Go)

Everything lives under `$STACK_WORKDIR/b2/` (scratch; NOT in the repo). Slices `SLICES.md` (s1 cli … s9 harvest), briefs `briefs/`,
run outputs `runs/`. Operator-approved cast: implementer arm A = a low-tier worker (session-local evaluation the operator is running;
notes `b2/sous-agent-observations.md`, do not turn into rules), control arm B = Claude Sonnet (`claude -p`), test-writer `glm-5.2-high`
(cursor chat id in `b2/tw.chat_id`), change review `gpt-5.6-sol-high` + `glm-5.2-high`. Arms run in LOCKSTEP (P485): each slice starts
both arms from the chosen reference of the previous slices.

- **References so far: s1 = Sonnet (`runs/s1.sonnet.diff`), s2 = Sonnet (`runs/s2.sonnet.diff`)**, committed locally in
  `arm-sonnet/mlx_local_stack` as "scratch: s1 / s2 reference". Every frozen-test failure on them was triaged as a frozen-test defect.
- **In flight at checkpoint:** s3 (core) both arms — `arm-sous-s3` and `arm-sonnet` (results `runs/s3.*.json`, rc files); side
  experiment s2b (pre-digested plan) in `arm-sous-s2b` (`runs/s2b.*`). Arm-A runs so far: 7 runs, zero edits (see the notes file).
- **Frozen tests: v6** in `b2/frozen/` (190 tests, SHA256, `FROZEN_AT`, `POST_REVEAL_TAGS.json`). v1 had 75 placeholder skips; v2–v6
  amendments were designer rulings from baseline code (the test-writer saw no candidate) — still contains test defects (fixture misuse,
  invented interfaces such as `OpencodeArm(p426=…)` / `abort_manifest`, a C221-incompatible self-test, `p1` vs `p01`). Decision: frozen
  at v6; every failure triaged by hand for both arms; list the defects in the four-eyes report; the test-writer's second delivery is on
  the final candidate.
- **OPEN for the operator: P487** — replace the test-writer before Accept (lead rec: `gpt-5.6-sol-high` as a fresh blind test-writer, change review `glm-5.2-high` + a third family); ask at the start of the next session.
- Clean evaluation copy: `b2/eval/mlx_local_stack` (baseline + s1 + s2 Sonnet + frozen v6).
- Next: score s3 (functional + 1–5 non-functional per arm; blind judges `blind-judge` agent + `gpt-5.6-sol-high` on anonymized X/Y
  diffs, per the operator's evaluation request), pick the s3 reference, continue s4 … s9 in lockstep, then the full stack suite on the
  final candidate, test-writer second delivery (cursor `--resume`), strict change review (sensitive hunks: harvest / scrub / secret gate,
  pair gate, chain-core policy / ledger / dispositions, locks, probe edits), Accept. While a GPU run is active, cursor-agent helpers get
  a one-line argv pointing at a brief file (P454 / P486).

## Worktrees / copies to resolve

`$STACK_WORKDIR/b2/{tw,arm-sous,arm-sous-s2,arm-sous-s2b,arm-sous-s3,arm-sonnet,eval}` — scratch clones for B2; resolve by harvesting
the accepted candidate into the repo at Accept, then delete. No git worktrees of the main checkout.

## Rules learned (session 8)

- Harvesters waiting on helpers must key on PIDs / rc files, not `pgrep` patterns (the session-7 harvester fired early).
- Never copy ignored files (`.env`) into helper copies; helper copies need the venv symlinks excluded via `.git/info/exclude`.
- Frozen tests must be standing-suite quality and validated on the baseline through every fixture path before freezing.
- The fork's pre-push gate checks naming per pushed commit: fix hits in the commit itself (allow-shorthand / full names), not in a follow-up.
- GPU is the bottleneck: always look for useful GPU work (memory `gpu-is-the-bottleneck`).

Next decision id C236; discussion ids continue from P487.
