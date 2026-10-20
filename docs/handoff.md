# Handoff — 2026-10-19 (session 3, in progress): C185 review rounds 1–3 used (round 3 NOT CLEARED E6 E7 → fixed test-first, ESCALATED, awaiting the operator); smoke 4 = Fable PASS / uniform E1c FAIL on a PRODUCTION defect (P400); Fable-only smoke 6 running on the candidate reviewed head 0d06bb0c

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P400, P399, P398, P397, P396, C186, C185 …),
then `docs/specs/p369-phase2-run-plan.md` (**v9**), `docs/specs/p387-build-note.md` (v2), `docs/specs/p383-build-plan.md` (v4).

## State of the world

- **Box `m5max-128`.** 140 W / 28 V adapter attached. **No `.env` on this box** (the shell carries `HF_TOKEN`; never `. ./.env`).
  Machine config: `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`.
- **Fork `p369-mtp` at `0d06bb0c`** (worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p369`; side worktree `…/mlx-vlm-p369-r2`, branch
  `p369-r2` = same head, for edits while a smoke owns the main worktree). **origin has `a44a8070`** (pushed with the operator's
  go); local is ahead — push only with a new go. Production diff vs `4e6d0e03` EMPTY. Green at `0d06bb0c`: fork suite
  **6412 / 17 / 0 twice**, identical skips; eight audits green (268 / 675 / 34 / 50 / 16).
- **Smoke 6** (Fable only, `--pick Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, no `--reviewed-head`):
  `$STACK_WORKDIR/p369/phase2/20261019-0d06bb0c-smoke6-fable`.
- **Smoke 4** (`…-8d1cf115-smoke4`, both picks): Fable E1c PASS (T 1,024 + 65,536: 158 sampled rows bit-identical, forced
  [129, 130] excluded, states equal at every commit, C1 identical, cross-load identical, all positives fired), E2 PASS, E7b
  OBSERVED (continuity, 2 × M4a), wall 1,590 s; **uniform E1c FAIL** (P400: terminal width-2 block on TQ4 KV; T 65,536 a1 rows
  @159 TV ≈ 0.009 + final state), positives incomplete (`tq_norm` / `old_prefix_k` never fired — harness TurboQuant leaf
  detection bug, unfixed), E2 / E7 skipped; gate projection 18,348 s (both picks) > 3.5 h. Smokes 5 (`…-fa89d19b-smoke5-fable`)
  and 3 were stopped early (INTERRUPTED) when a newer head superseded them.
- **Escalated to the operator (C186 table, in the session):** (1) accept the round-3 E6 / E7 / E1 fixes without a 4th round so
  `0d06bb0c` is the `--reviewed-head` (lead: accept); (2) P400 — uniform stays MTP-OFF behind its own production-fix proposal,
  Fable's phase 2 proceeds (lead) vs hold all; (3) full run Fable-only (≈ 2.65 h projected) once smoke 6 passes on `0d06bb0c`.
- **Stack `main` ≈ 50 commits ahead of origin** (docs only). Push needs the operator's in-turn go.
- Daily driver MTP-OFF (C177) until P369 ships + re-certification.

## Smoke-found bugs (fixed test-first; P394: smoke iterations need no review round)

- Smoke 1: requests carried the registry name; mlx-serve's router rewrites `body["model"] = hf_path` (`router.py:483`) → the
  worker unloaded its target and tried an offline load. Fix: `routed()` in `post` / `prompt_ids` (`f0bfce29`).
- Smoke 2: the dry-run `DryRun(BaseException)` unwound through `@app.middleware("http")` as a `BaseExceptionGroup` and killed the
  TestClient portal (reproduced on CPU). Fix: plain `Exception`, ids recorded on the side (`7b87192e`).
- Smoke 3: **P398** — E1c compared a stale ON row at a thinking-budget forced position (E1c `max_tokens` 160 → budget 128 →
  forced `\n</think>`). Fix: rows cut at each block's emission decision, forced positions proven and excluded (`8d1cf115`).
- Smoke 4: P399 (rejected attempts' evidence dropped) and P400 (production defect) — open-questions.
- Observed, not a bug: Fable T = 1,024 seed a0 had no observed key-length straddle (a block boundary landed on 1,024) while the
  production counter read 16 → that cell retries the next seed (by design). T = 65,536 E1c cell > 11 min (hash cost).

## Next work, in order

1. **Operator rulings on the escalation** (above). On "accept": `0d06bb0c` is the reviewed head; if smoke 6 SMOKE_PASSes on it, the
   full run: `nohup .venv/bin/python <worktree>/dev/p369_phase2/orchestrate.py --stack-root . --fork-root <worktree> --out
   $STACK_WORKDIR/p369/phase2/<date>-0d06bb0c-full-fable --phase full --pick Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed
   --smoke-summary <smoke6>/summary.json --reviewed-head <full sha of 0d06bb0c> > <out>.log 2>&1 < /dev/null &` (detached; waiter;
   5-min check-ins). Report Fable E1c (pair, C1, C2, forced positions, rejected attempts), E2 (verdict, C1-E2, cross_load), E7a
   (Clopper–Pearson), E7b (descriptive) → P369 + handoff.
2. **P400 (uniform production defect)** — own proposal per the operator's ruling: localise the TurboQuant width-2 verify branch
   (repro scripts: the scratchpad `tq_repro.py` / `tq_map.py` / `tq_width.py` pattern — uniform `_quantized_pair` + `kv_bits=4,
   kv_quant_scheme="turboquant", quantized_kv_start=0`, scripted full-accept drafter; block forced to 2 via
   `test_mtp_stop_state.BLOCK = 2`), red test incl. TQ KV in the E1a / E1c fixtures (both picks), fix, Cursor review, re-pin
   PRODUCTION, rerun uniform phase 2 (+ the harness `tq_norm` leaf-detection fix).
3. Smoke-fix bookkeeping: index the new review dir `docs/reviews/p369-c185/` in `docs/README.md`.
4. Then: fork main merge + submodule bump (suites in both repos) → per-pick re-certification (own plan, operator GPU go) → restore
   MTP-ON (C177 lines = `test_mtp_verify_scan.INTERIM_LINES` reversed) → P368 layers 2–3; P383 build (+P389, P388 snapshot); P385
   with Cursor; tg2 steps 3–4; M64.

## Known gaps / owed

- Residuals (disclosed): a helper that spawns and escapes between two ps polls; pid reuse within one lstart second; a cache
  symlink swap during model load restored before the re-hash; H37 (total ps failure after a setsid helper); H12 (CI oracle
  `fetch-depth: 0` + `MLX_REQUIRE_P369_ORACLE=1`) with the fork main merge. E2/E7 link to the original C84 runs is count-only.
  `tq_norm` positive and the kernel coverage set unproven on real weights until the smoke. E7 tool-session exposure not measured.
- `docs/README.md` index additions (P311 v4, P364, P369, P371, m65 tg2, M65 pilot, `docs/reviews/p371/`, `docs/reviews/p369-harness/`,
  `docs/reviews/p369-c185/`, `docs/reviews/p387/`, the phase-2 plan, the P387 note); one pre-existing pyflakes note in
  `test_mtp_verify_scan.py` (`harness`).

## Rules learned

- Suites: fork `(cd mlx_vlm && ../.venv/bin/python -m pytest -q ./tests --ignore=tests/test_smoke.py -rs -p no:cacheprovider)` ≈ 2.5 min;
  stack from `benchmark/`: `../.venv-bench/bin/python -m pytest bench/tests -q -p no:cacheprovider -o faulthandler_timeout=600 -rs`.
  Never two suites at once; never edit a worktree while its suite runs. Audits: the 8 `dev/check_*.py --upstream-ref 952d4f6b`
  (`--strict` for deletions) from the worktree with `.venv/bin/python`.
- **Cursor:** `cursor-agent -p --output-format stream-json --model gpt-5.6-sol-high --mode ask --sandbox enabled --force --trust
  --workspace ~/ws/mlx-vlm "<prompt>" > out.jsonl`, review text = the `type=="result"` event's `result`. One run at a time; state
  "round k of 3".
- Formatting: `uvx --offline black@26.3.1` (its "Python 3.12 cannot parse" warning is harmless), `isort@5.13.2 --profile=black`,
  `pyflakes`. BSD sed chokes on the em dash — use Python for exact-line edits.
- A deadline-capped `ps` (H33) needs a margin wherever a loop's own deadline bounds it (P396); a test that flakes is a bug report.
- Tests that start processes own them in fixtures that kill the PGID and any self-recorded child pid at teardown.
- Zero flakes; red-first honesty (say "helper absent" vs behavioural); check `git show --stat` after every commit.

Next decision id C187; discussion ids continue from P401.
