# Handoff — 2026-11-05 (session 17 END: P426 shipped MTP ON (C291); P475 stage-1 build ACCEPTED + on the box; next: the C296 fixes, then P658 in the fork)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C296, P659, P658, P656, P655, P654, C295 …
C289), then `docs/specs/p475-stage1-contract.md` (v1.2) and `docs/reviews/p475s1/dispositions.md`. Model names: FULL registry names
only. Review rounds: 3 per artifact. Operator stance: bias for quality; drive to certified picks; ask only at Go / Accept / pushes /
scope changes; lead calls filed as they land; offer a fresh session at clean boundaries.

**Discussion ids restart at P1 in session 18 (operator, 2026-11-05).** In durable records (open-questions, commits, handoff) cite a
new id as `S18-P<n>` so it cannot collide with the historical P1–P659; decision ids continue as C297.

## THE GOAL

Certify the two picks in their ideal config. `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`: DONE — MTP ON `CERTIFIED P426 2026-11-04`
(C291). `Qwen3.8-27B-mlx-uniform-4bit`: its KV format first (P475 stage 1: memory / speed matrix of six arms, MTP ON as shipped; the
operator weighs the table; stage 2 quality only for formats kept), then its MTP ON vs OFF re-certification on the chosen format.

## FIRST — verify (each "no" is a blocker)

1. Nothing running: no router on :8000, no `bench.p475_kv`, no `qualify` / `worker.py` (check by command-line substring in a python
   filter — never put BUSY markers such as `mlx_vlm.server` / `mlx-serve` / `run_capacity` in your own command line: they refuse legs).
2. `origin/main` = local `main` (session-17 tip); forks `../mlx-vlm` = `d94e38a9`, `../mlx-serve` = `1ddf6f84`, both = their origin.
3. Arm worktrees `$STACK_WORKDIR/worktrees/p475-u4-{n16,af8,tq8,af4,tq4,tq4-off}` on local branches `p475-u4-*` off base `1554bfe1`
   (each diff = exactly its registry keys + `# PROVISIONAL P475 arm` comment; each has `.venv`, `.venv-bench` and a hand-built fork
   venv `src/mlx-vlm/.venv` pinned to the arm `.venv`'s versions).

## State at session end

- **P475 stage 1 code** (`1554bfe1`, gate PASS 11,870, pushed): `bench.p475_kv` + `bench.kv_line` + `run_capacity --p475-strict` +
  `bench_watch` capacity mode; frozen tests `bench/tests/p475s1` (537). Four-eyes light, two fix rounds (C294), accepted C295.
- **On the box:** `prepare` done (with the full sha; P655). **All six MTP-OFF preflights PASS** (records `$STACK_WORKDIR/p475/preflight/
  <ARM>.json`, bound to base `1554bfe1`): N16 16 native; AF8 / AF4 16 affine (gs 64); TQ8 / TQ4 / TQ4-OFF 15 TurboQuant + layer 63
  native; all 48 Gated DeltaNet `ArraysCache` leaves untouched (P654: the KV path never converts them — no state-dtype instrumentation
  needed). False records from environmental refusals are kept aside as `*.p656-*.json` / `preflight/archive/`.
- **Smoke `u4-n16-smoke.a1` INVALID** (P659: `run_capacity` writes into the arm worktree, R1 exit-clean fails) — everything else held
  live: KV line native, `prompt_n == prompt_tokens`, prefill rate re-derived 0.0 % off (GLM F3 resolved), drafter counters present, N16
  worker env clean, teardown proven. Its dossier is committed under `benchmark/results/p475/u4-n16-smoke.a1/` (evidence). A resume
  STOPS at it by design: archive `$STACK_WORKDIR/p475/legs/u4-n16-smoke.a1` (move aside) before the next smoke.
- **Not yet answered:** D1 (does psutil show the worker's in-process `KV_BITS` on a quantized arm?) — the TQ4 smoke records it.

## Next, in order (C296)

1. **Stack fixes, designer-small, red tests first, one commit** (P659, P655, P656 items 1–5): exit identity tolerates exactly the leg's
   three capacity outputs; `--base` resolved to a full sha before use / record; environmental preflight refusals (lease / busy / port /
   leftover out dir) are `NOT_STARTED`, consume no attempt, never final; `prepare` creates `$STACK_WORKDIR/p369/phase2/` and the fork
   venv (`uv venv --python 3.12` in `src/mlx-vlm`, `uv pip install -e . -c <freeze of the arm .venv minus mlx-vlm/mlx-serve/stack>`);
   the preflight record keeps `qualify`'s stderr tail and reaps its process group on timeout. Commit (no gate yet — one gate later).
2. **Smokes on the current base** with the fixed orchestrator (D1 + a VALID pipeline): archive the INVALID smoke leg dir, then
   `nohup …/.venv-bench/bin/python -m bench.p475_kv run --smoke` (detached; wait on the pid; see FIRST 1).
3. **P658 (a), fork four-eyes light** (`../mlx-vlm`, `dev/` only, production byte-identical): `qualify --kv-arm --predictor on
   --engagement-only` (build the served MTP-ON path; target + drafter manifests vs expectation; no exactness / certification legs) +
   P656 item 6 (the quiet-box scan, `orchestrate.REFUSED_MODULES` incl. `bench`, exempts the caller's own ancestor chain — today the CLI
   `preflight` refuses itself; workaround: call `bench.p475_kv.preflight()` from a stdin-launched `python -`). Cast as P475a
   (implementer Claude Opus 5.5, test-writer Claude Sonnet 5.5 via `claude -p`; panel GPT-5.6 Sol High + GLM 5.2 read-only). Fork gate
   `dev/ci.py`; **fork push needs its own ask** (the session-17 approval covered that turn's pushes only).
4. **Stack gitlink bump** to the fork commit + `LIVE_GITLINKS` in `bench/tests/b2_frozen_support.py` (P632: never move
   `BASE_GITLINKS`); the stack `p475_kv` wired to call the ON engagement check for ON arms; **one full gate** for 1 + 4; **push ask**.
5. Re-`prepare` on the new base (fresh arm worktrees; old ones removed after archiving), OFF preflights + ON engagement checks, the two
   smokes (N16, TQ4), then the full run (12 legs, ≈ 13 h GPU; ≥ 600 s idle; 140 W / 28 V). Harvest → generated
   `MATRIX.Qwen3.8-27B-mlx-uniform-4bit.md` → operator; push ask for results + scrubbed logs to `evidence`.

Push points (advised in C296): the fork after its gate; the stack once (fixes + bump, one gate); the results after harvest.

Open, lower priority: P643 (a load-sensitive timing test, C261 route), P642's two process gaps (the gate keeps no failure detail; an
approved fix went unqueued — C209 sat two weeks).

## Worktrees / scratch (resolve each)

- Keep: the six `p475-u4-*` arm worktrees + branches (until re-prepared on the new base in step 5; their legs' outputs are harvested).
- Carried from P426: `stack-p426-off`, `stack-p426-on`, `stack-c258x-off` (+ local `archive/p426-*` branches), `$STACK_WORKDIR/p426/*`
  — P426 is done: propose their resolution (harvest check → remove).
- Session-17 removals archived in `$STACK_WORKDIR/archive/session17-worktrees/` (p613s*, p624*, p627*, p475a-*, p632-diag,
  p613s4-verify, p475s1-*).

## Rules learned (session 17)

- Before amending a shared pin, list every reader and run their suites (P631 → P632); split two roles that share one constant.
- `gate/RUNNING` is a persistent flock file: wait on the previous receipt's appearance, never on the file's absence.
- A flake is a mechanism: reproduce under load (8-core busy loop) with `--showlocals` and full logs; check `open-questions` — the
  P642 race was P433, approved and never built.
- Fakes miss real-box facts: short vs full shas, real commit hooks, real files written into worktrees, the fork's quiet-box scan
  matching the caller. Run the accepted tool on the box early (smoke-sized) and expect a short list of fail-closed integration bugs.
- `subprocess.run(timeout=…)` kills only the child: reap the group (an orphaned `qualify` worker refused the next run).
- Engagement proof and exactness certification are different questions; check the proof covers the state you measure (MTP ON).
- zsh does not word-split: pass file lists with `--pathspec-from-file` or arrays.

Next decision id C297; discussion ids restart at P1 (cite as `S18-P<n>` in durable records).
