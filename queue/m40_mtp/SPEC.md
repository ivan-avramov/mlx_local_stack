# M40 runner spec — MTP-ON certification chain (agent-facing; rules, not rationale)

Deliverables in `$STACK_WORKDIR/queue/m40_mtp/`: `helpers.py` (copied from `queue/m38_cjudge/helpers.py`,
`OUT` → this dir, `OFF_OVERLAY` → `f"{OUT}/off_<model>.yaml"` is NOT a constant any more — see §2), `run.py`,
`README.md` (how to arm, how to read queue.log). No repo files change. No GPU work is launched by the worker:
`run.py --dry-run` must build overlays, run every assertion, and print the full command plan, then exit 0.

## 1. Picks and order
PICKS = [A, B]; A = `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, B = `Qwen3.8-27B-mlx-uniform-4bit`. Run A completely, then B.
EXPECT_TEMP = {A: 0.5, B: 0.6}; EXPECT_EFFORT = {A: 'medium', B: 'medium'}. Assert both from the overlay's
`generation_defaults`, plus `enable_thinking is True`, `thinking_budget == 81920`, `max_tokens == 102400`,
`kv_prealloc_tokens == max_kv_cache_size == 262144`. Re-read `$STACK_REPO/main_models.yaml` per pick (it is the record).

## 2. Overlays (per pick, from the CURRENT worktree registry)
- `on_<pick>.yaml`: strip `draft_*` and `moe_expand` from EVERY entry EXCEPT the pick; the pick MUST keep
  `draft_kind: mtp` and `draft_model: <path>`; assert `draft_kind == 'mtp'` and `os.path.isdir(draft_model)`
  (both picks carry local sidecar dirs in the worktree registry). FATAL otherwise.
- `off_<pick>.yaml`: strip `draft_*` and `moe_expand` from every entry (the m38 `fresh_overlay` recipe).
- Write both with `yaml.safe_dump(sort_keys=False)`; log sha256 of each; `run_generate(..., expect_draft='mtp'|'off')`
  already performs the C35 manifest check + worker-cmdline check — use it unchanged.

## 3. Arms per pick (tune labels: ON = `m40on`, OFF = `m40off`; math ids from `$STACK_WORKDIR/queue/resolution/ids.json`)
Seeded 5-item pilot precedes every n≥40 arm (pilot ids = `resolution/ids.json[<bench>]['pilot']`; cjudge pilot =
`--limit cjudge=5 --seed 0`, as m38). After each pilot log `PILOT projected lower-bound seconds=mean*N max=...`.
A `full` arm resumes if rows exist (assert existing ids ⊆ target ids, as m38 `run_math_leg`).

Router on `on_<pick>.yaml` (`ensure_router`), then:
1. math500 ON: pilot 5 → full 100 via `--limit math500=0 --ids math500=<colon-joined ids>` (m38 recipe); grade; RESULT line.
   OFF pair = existing `math500.m37med` (verified: same 100 ids, medium, draft off) — do NOT regenerate.
2. cjudge ON: pilot 5 → full 40; grade (acc=None is expected, kind=open); RESULT line.
   OFF pair = existing `cjudge.m38`.
3. vision gate ON: `$STACK_REPO/.venv-bench/bin/python $STACK_REPO/benchmark/vision_gate.py --model <pick>
   --out $STACK_REPO/benchmark/results/<pick>/vision_gate.m40on.jsonl` (env: MLX_SERVE_CONFIG=<on overlay>,
   no APC_ENABLED). Before launch log `worker cmdline: ...` and assert `--draft-kind` present; after, log the
   summary json's pass count. Write `vision_gate.m40on.provenance.json` next to it: {overlay, overlay_sha256,
   worker_cmdline, started, finished}. OFF pair = existing `vision_gate.v1`. Watcher: bench_watch with
   `--bench vision_gate --tune m40on --total 20` (it reads `{bench}.{tune}.jsonl`); if bench_watch rejects the
   label, fall back to a 5-min heartbeat thread logging row count + worker cmdline presence.
4. depth 128K ON: `$STACK_REPO/.venv-bench/bin/python $STACK_REPO/benchmark/bench/run_reasoning.py --model <pick>
   --grid 128000 --samples 3 --chain-len 4 --threshold 0.85 --sampling-profile deployed --out-tag m40on-d128k`
   (cwd `$STACK_REPO/benchmark`, PYTHONPATH `$STACK_REPO/benchmark`, same env). Log + assert worker cmdline
   `--draft-kind` present before launch; write `reasoning.m40on-d128k.provenance.json` (same fields); 5-min
   heartbeat thread (partial jsonl size, worker alive). Bound 4 h.
5. pick B ONLY, coding at the deployed medium tune (no matched OFF rows exist at medium):
   humanevalplus ON pilot 5 → full 100 (`--ids humanevalplus=<resolution ids>`), mbppplus ON pilot 5 → full 100
   (`--ids mbppplus=...`); grade both (docker EvalPlus path via `run.py grade`); RESULT lines.
Then `unload()`, `stop_router()`, assert 0 listeners. Router on `off_<pick>.yaml`, then:
6. depth 128K OFF: same as 4 with `--out-tag m40off-d128k`, assert `--draft-kind` ABSENT. (Both picks: pick B's
   M11 128K draws were at effort None — not a matched pair.)
7. pick B ONLY: humanevalplus OFF + mbppplus OFF, tune `m40off`, same ids/pilots as 5; grade; RESULT lines.
Then `unload()`, `stop_router()`, assert 0 listeners. Log `=== M40 <pick> DONE ===`. After both picks:
`=== M40 MTP QUEUE DONE ===`.

## 4. Invariants
- Idle precheck at start (m38 `main` recipe: no `run.py generate|mlx_vlm.server`, 0 listeners) — FATAL otherwise.
- Never edit `$STACK_REPO/main_models.yaml`. Never `|| true`. Every subprocess: `stdin=DEVNULL`, stdout/stderr to a
  log in OUT, pid file in OUT. `queue.lock` + `queue.pid` as m38. Exceptions → `FATAL <repr>` + traceback in queue.log,
  router stopped, non-zero exit.
- Every `RUN`, `C35 check`, `worker cmdline`, `END`, `SUMMARY`, `SCORE`, `RESULT`, `PILOT`, `DONE`, `FATAL` line format as
  in the m38 helpers (the session Monitor greps them).
- Per-arm `bound_h`: math 12, cjudge 8, coding 6, depth 4. Probe timeout stays the helper's 7800 s.
- `--dry-run`: build + assert overlays for BOTH picks, print every command that would run (with env deltas), touch
  nothing else, exit 0. `--pick A|B` optional filter for reruns. `--from-step N` optional resume.

## 5. Acceptance (the reviewer checks these)
- `run.py --dry-run` exits 0 on this box and prints 2 overlays × 2 picks with correct draft fields and shas.
- Every launched command carries `--sampling-profile deployed` and `MLX_SERVE_CONFIG` in env (grep the dry-run plan).
- ON arms assert `--draft-kind` in the worker cmdline; OFF arms assert its absence (both via run_generate for
  run.py benches AND explicitly for vision/depth).
- Pilot-before-full for math/cjudge/coding; ids from resolution/ids.json; resume-safe.
- No path outside `$STACK_WORKDIR`/`$STACK_REPO/benchmark/results` is written.
