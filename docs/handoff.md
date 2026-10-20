# Handoff — 2026-10-20 (session 4): v13 code review rounds 2–3 done (escalated, P414); `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` regression smoke PASS on `7207179b`; GPU work BLOCKED — AC adapter detached

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P415, P414, P413, P412, P411, P409 closed,
P408 / P407 deferred C190, P406 → C191, P405, C195–C189), then `docs/specs/p369-phase2-run-plan.md` (v13, accepted C193;
V17 wall cap withdrawn C194) and `docs/specs/p405-kv-scheme-precedence.md` (v4, accepted C192).
Model names: FULL registry names only, always.

## State of the world (2026-10-20 14:30)

- **Box `m5max-128`. POWER: `pmset -g ac` = "No adapter attached" since some time after 14:02 (battery 77 %, discharging).**
  Every remaining GPU run (R4, R5, R7, v13 smokes) needs 140 W / 28 V — reattach the adapter and verify before any launch.
  GPU IDLE. **No `.env`**. ALWAYS `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"` first.
- **Results today (session 4):** `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` regression smoke 15 on the reviewed P405 head
  `64afc7dd` (production `7207179b`, `--reviewed-head 64afc7dd`): SMOKE_PASS — E1c both cells, E2, C1 / C2 identical,
  `verify_blocks_per_query = 0`, native KV → the C188 carry-over holds; no full rerun owed
  (`$STACK_WORKDIR/p369/phase2/20261020-64afc7dd-smoke15-fable-regression`; open-questions P369 + campaign-results).
  Earlier today: `Qwen3.8-27B-mlx-uniform-4bit` P369 full run PASS on TurboQuant.
- **Fork branches (all LOCAL, unpushed; operator: "no push yet"):**
  - `p369-mtp` `3a92943d` (= origin) — worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p369`, the GPU runs' fork root (chain scripts
    detach it to the run head and restore it; currently restored).
  - `p400-tq-width2` `abbbfc84` (C192); `p405-kv-scheme` `64afc7dd` (C195; production pin `7207179b`).
  - `p369-v13` **`3ae8770e`** (worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p405`): v13 harness after code rounds 1–3.
    Round 2 (`docs/reviews/p369-v13/code-round2.*`): NOT CLEARED M1 M2 M3 M5 M7 N1–N4 → fixed `d4256803` red / `a2808acf` green
    (N1 not changed: C194 keeps an explicit `--wall-limit-s`). Found while fixing: P412 (JSON list vs tuple → Ornith refused at
    every boot), P413 (telemetry renamed target modules after a bound drafter) — both fixed in the same commits. Before round 2:
    `d36d33c5` fixed a stale H23 test (first full suite on `3e3cec09`). Round 3: M1–M10 + N1–N4 CLOSED; **NOT CLEARED R1 R2**
    → fixed test-first after the last round (`5f15d641` red / `3ae8770e` green) → **P414, operator decision**. Suites ×2
    (6673 / 17 skipped, identical) + 8 audits green on `3ae8770e`; production diff vs `64afc7dd` empty.
  - `p404-arm-a` `e12780d0` (worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p404a`, clean) = R4 arm A.
- **Registry:** unchanged — four MTP-certified entries MTP-OFF (C177 + C191). Stack `main` ≈ 135 commits ahead of origin.

## Waiting on the operator

- **P414** — accept v13 code-round-3 R1 / R2 as fixed without a fourth round (lead rec: yes) → `3ae8770e` is the reviewed v13 head.
- **P415** — the R7 qualification tool (plan in the entry; lead rec: build after P414, test-first, Cursor plan + code review).
- **P411** (lead call, may overrule): R5 for `Qwen3.8-27B-mlx-uniform-4bit` now; `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` after v13.
- AC power back on. Pushes when wanted.

## Next work, in order

1. Verify AC (`pmset -g ac` 140 W / 28 V, battery > 20 %).
2. **R4** — P404 TurboQuant ABBA, ready: `$S/chain_r4.sh` (scratchpad of session `060ea786…`; recreate if gone: detach the p369
   worktree to `64afc7dd`, `.venv/bin/python <p369 wt>/dev/p400_perf_probe.py drive --stack-root . --old-tree <p404a wt> --old-ref
   e12780d0 --new-tree <p369 wt> --new-ref 64afc7dd --pick Qwen3.8-27B-mlx-uniform-4bit --python <p369 wt>/.venv/bin/python --out
   $STACK_WORKDIR/p400/perf/20261020-r4-e12780d0-vs-64afc7dd`, plus the 5-min watcher `$S/perf_watch.py <out> <pid> 4 2400` — the
   probe has no monitor of its own; restore the worktree to `p369-mtp`). ≈ 40 min (prior: 2.2 min / leg + 3 × 10 min idle).
   Then decide P404 with the operator against the C188 bounds.
3. **R5** — codec ABBA for `Qwen3.8-27B-mlx-uniform-4bit` (`p400_perf_probe.py codec --tree <p369 wt at 64afc7dd> --ref 64afc7dd
   --python …`; short + long 261,120-token schedules; same watcher). Then (P411) `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` after v13.
4. After P414: `--phase panel` for `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` and `Ornith-1.0-35B-mlx-uniform-4bit` on `3ae8770e` →
   review + commit `dev/p369_phase2/borrowed_panel.json` → their campaigns (smoke with `--reviewed-head 3ae8770e`, then full).
   Watch the first real ON boot for the R1 live-reset checks (`drafter_live_checks`) and the P412 / P413 fixes.
5. R7 (after P415), R6 (own plan), router-chain re-certification; then fork main merge (P400 → P405 → v13) + candidate stack
   worktree bump → re-certification → per-entry MTP-ON restore. Then P383, P385, tg2, M64; remove stale worktree `mlx-vlm-p369-r2`.

## Known gaps / owed

- R2's fused-path negative is unit-level (the drafter decodes one token per draft step, so its `SwitchGLU` never takes the fused
  branch on the served path).
- Earlier residuals unchanged (ps-poll escape, pid reuse within one lstart second, cache symlink swap, H37, H12 with the fork main
  merge; E2/E7 C84 link count-only; E7 tool-session exposure unmeasured). `docs/README.md` index additions still owed (list in
  the previous handoff: P311 v4, P364, P369, P371, m65 tg2, M65 pilot, review dirs incl. `docs/reviews/p369-v13/`).

## Rules learned

- Suites: fork `(cd mlx_vlm && PYTHONPATH=<wt> <p369 wt>/.venv/bin/python -m pytest -q ./tests --ignore=tests/test_smoke.py -rs
  -p no:cacheprovider)` ≈ 2.9 min; stack from `benchmark/` after sourcing the machine config. Never two suites at once; never
  edit a worktree while its suite runs; no pytest while a campaign runs (some fork tests use Metal). Audits: the 8
  `dev/check_*.py --upstream-ref 952d4f6b` (`--strict` for deletions).
- **Cursor:** `cursor-agent -p --output-format stream-json --model gpt-5.6-sol-high --mode ask --sandbox enabled --force --trust
  --workspace ~/ws/mlx-vlm "<prompt>" > out.jsonl`; review text = the `type=="result"` event's `result`. One at a time; "round k of 3".
- Launch GPU chains with `nohup … &` + a separate waiter (a `run_in_background` shell is not detached); `chmod +x` first.
- `SwitchGLU`'s exact fused path is inference-only (`not self.training`): fixtures must `.eval()` to reach it.
- isort and black disagree on `# noqa` placement in wrapped imports — run black last; check the diff for import churn.
- Red-first honesty: say which red tests are behavioural, helper-absent, or green-on-current (strengthening); mutation-check a
  regression guard whose fix already landed.

Next decision id C196; discussion ids continue from P415.
