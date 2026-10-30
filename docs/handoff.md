# Handoff — 2026-10-30 (session 11 END: all four MTP entries exact on S′; P541 / P542 built + pushed; C249 part 1 done, part 2 RUNNING; B2 after its 3-round strict verify → fix5 → Accept)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C256, C255, P546, P545, C254, C253, P541, P539,
C252, P537, P536, P535, P534, C251, P533, C250–C247), `docs/specs/p426-b2-tg1-wave2.md` (v3.2; §16.8 to the end — the newest pins are
last), `docs/specs/p541-push-levels.md`, `docs/specs/p542-qualify-any.md`. Model names: FULL registry names only, always. Review rounds:
3 per artifact (AGENTS.md); B2's strict verify used all 3 (C256).

## FIRST, before anything else

1. **C249 part (2) may still be running** (GPU, started 2026-10-30T10:04Z): `$STACK_WORKDIR/p369/run_c249_part2.sh`, PID in
   `$STACK_WORKDIR/p369/phase2/c249-part2.pid`, log `$STACK_WORKDIR/p369/phase2/c249-part2.log`, per arm
   `c249p2-<entry>-<on|off>.{generate,watch,stop}.log`. Check by PID / port / log lines only (never a BUSY string on a command line).
   While it runs: start NO process — no tests, no helpers, no git commit (hooks run Python): it is a decode-speed measurement.
   When it ends: verify :8000 is free and no router / worker survives; read the rows' `decode_tps` per arm
   (`<worktree>/benchmark/results/<entry>/math500.c249-mtp{on,off}-20261030.jsonl`, worktrees `stack-c249` = ON, `stack-c249-off` = OFF).
2. **Commit the uncommitted docs** on `main` (this handoff, `docs/open-questions.md` C255 / C256 / P546, the B2 spec §16.8 pins "after
   the strict verify round 1 / round 2", `docs/specs/p542-qualify-any.md` v1.4) — after part (2) ends. Then copy this session's review
   outputs into `docs/reviews/` (P541: `$STACK_WORKDIR/reviews/p541-code-r1/`, P542: `…/p542-code-r1/`, B2 strict verify rounds 1–3:
   `…/p426-b2-verify/` — `{sol,glm}.out`, `*.verify*.out`, `sonnet*.json` `result`; per-line `allow-shorthand` markers for severity words
   / test constants as before; no home paths) with a dispositions file per review; commit. Pushes: docs-only level, ask the operator.

## State — 2026-10-30 ~10:30Z

- **Pushed (all through the P541 hook):** stack `main` `e3c70a79` (level full), fork `../mlx-vlm` `main` `fd67082a` (level full).
  `main` has uncommitted docs only (see FIRST 2).
- **P369 full on S′ (C248): all four MTP entries PASS** — `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`,
  `Ornith-1.0-35B-mlx-uniform-4bit` (fork `1cce312f`, all-OFF stack root), `Qwen3.8-27B-mlx-uniform-4bit` (rerun on fork `a4cd07e0`:
  T = 8K valid at straddle offset 65, P537). README rows record them. MTP ON PROVISIONAL for all four (C244 / C247).
- **C249 part (1) DONE** (256K `qualify.py` ABBA, fork `fd67082a`, `$STACK_WORKDIR/p369/phase2/20261030-fd67082a-c249-*`; all 12 arms
  COMPLETED): peak OFF → ON `Qwen3.8-27B-mlx-uniform-4bit` 25.18 → 26.06 GB, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` 28.14 → 29.60,
  `Ornith-1.0-35B-mlx-uniform-4bit` 31.80 → 32.28; **decode at 256K ON is SLOWER** — 11.92 → 10.38 tok/s (−13%), 10.73 → 10.09 (−6%),
  45.57 → 41.59 (−9%) (replicates tight). Hypothesis: at 256K the verify block's extra full-context attention outweighs accepted drafts.
  Not yet recorded in README / open-questions — do it with part (2).
- **C249 part (2) RUNNING** (C255, P546 lead call n = 20 per arm, seed 1355, deployed sampling, lean router per arm worktree, pairs
  `Qwen3.8-27B-mlx-uniform-4bit` ON→OFF, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` OFF→ON, `Ornith-1.0-35B-mlx-uniform-4bit` ON→OFF, 10 min idle). It decides whether MTP helps at normal length for these three.
  Then: the CERTIFIED-or-OFF call per entry is the operator's (P523 / C249: memory + speed ON vs OFF + P369 exactness).
- **P541 (push levels) DONE + pushed** (stack `e3c70a79`): the pre-push hook requires full (PASS gate receipt for the exact tip) /
  docs-only / data-only per ref and prints the level. Rule: a push means its level passed (operator); docs-only pushes need no gate.
- **P542 (`qualify.py` for any registry entry) DONE + pushed** (fork `fd67082a`): any registry entry, arms derived from the registry,
  MTP-ON gated on a P369 FULL PASS + full-sha production + the certified `argv_on`, one registry snapshot, safe ids, rates per entry.
- **B2** (copy `$STACK_WORKDIR/b2/arm-rebased/mlx_local_stack`, branch `b2-rebased`, scratch commits up to `608a9d47` fix round 4):
  s1–s9 + fix rounds 2–4; independent frozen set 501 / 503 at fix3 (2 = baseline-only s0 by design); full suite 8361 passed at fix2d;
  strict verify (review-panel, 3 members, checkout context) rounds 1–3 done → C256: fix5 for 5 items, then the test-writer's final
  fixture amendment, frozen set, full suite, designer verification, **Accept to the operator**. The test-writer session
  `44568a2b-2638-419f-8c1d-17b471a74c5e` (cwd `b2/tw2/mlx_local_stack`; scripts `b2/tw2/bin/run_candidate_final_tests.sh`,
  `sync_to_final.sh`, eval copy `b2/eval-final`); the implementer session (fix rounds) `bc1647f9-4024-42cb-9edb-d850dd5d900b`
  (launch pattern `b2/runs/launch_fix4.sh`, brief style `b2/briefs/fix4.md`). Sync the spec and the frozen set into `arm-rebased`
  before each run (see `b2/runs/` launchers).

## Next, in order

1. FIRST 1–2 above.
2. Record C249 parts (1) + (2) (README, open-questions; per entry: memory, decode at 256K and at normal length, P369) and put the
   CERTIFIED-or-OFF call per entry to the operator (a recommendation per entry; `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` waits
   for Wave 2).
3. B2 per C256: fix5 brief (the five items in C256) → implementer (resume `bc1647f9…`) → sync frozen set → test-writer final fixture
   amendment (resume `44568a2b…`) → frozen set → full suite (quiet box) → designer verification → B2 Accept to the operator.
4. After B2 Accept: v8 freeze → pilots → amendment → Wave 2 (first pick; OFF arm = `main` + revert of the C244 hunk, P525) → B8 / B6.
5. P503 (load-sensitive tests) — the fork's ring-port flake is root-caused (`417bfaa0`); the stack ones remain.

## Copies to resolve

Worktrees (never push their branches): `stack-c249` (ON, detached `e3c70a79`), `stack-c249-off` (`0a0d8023`, all OFF), `stack-p369-full-off`
(branch `p369-full-off`), `stack-p426-s2-{off,on}` (branch `p426-on-s2`, until Wave 2's freeze). Harvest part (2)'s rows from
`stack-c249*/benchmark/results/` into `main` (a data commit) before removing them. Fork roots `$STACK_WORKDIR/p369/fork-{1cce312f,a4cd07e0,fd67082a}`
(keep until C249 is recorded). `$STACK_WORKDIR/p541`, `p542`, `reviews/*` (copy into docs/reviews, then delete), `$STACK_WORKDIR/b2/*`
(harvest at B2 Accept), `$STACK_WORKDIR/t3/*` (delete).

## Rules learned (session 11)

- A push means its stated level passed (operator, P541): read a gate verdict BEFORE pushing, never chain them (P539).
- No process while a GPU measurement runs — tests, helpers, git hooks (qualify / orchestrate censuses refuse foreign Python; speed
  runs need a quiet box). Remote review panels (node) are fine.
- A P369 full run is authorized only by a smoke on the same reviewed head and stack root (overlay bytes, `benchmark/bench` tree); a
  stack-root worktree needs `.venv` AND `.venv-bench`; the OFF arm is the stack root's registry (use an all-OFF worktree, P527).
- The fork gate's audits (9) read STAGED content; run them all locally before a gate; new fork code needs `# Fork:` markers and the
  upstream call shapes; the pre-push naming scan refuses shorthand test constants on added lines — use neutral aliases.
- A resumed helper's CLI `total_cost_usd` is cumulative; per-job cost is the increment.
- zsh: split lists with `${=var}`; never redirect to a `/tmp/../$HOME` path.
- 256K is a worst case for MTP decode: measure speed at normal length too before calling MTP.

Next decision id C257; discussion ids continue from P546.
