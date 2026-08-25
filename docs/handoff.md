# Handoff — rewritten 2026-08-24 ~19:45 (M18 COMPLETE + committed; O40 smoke verdict in; nothing running)

Single box (M5 Max 64 GB). **NO WORK RUNNING.** Daily lean router :8000 up (pid may
recycle — verify with `lsof -nP -iTCP:8000 -sTCP:LISTEN`), NO resident model (unloaded
for the smoke). M18 watcher and surgical driver are done and gone; smoke routers on
:8093 stopped.

## M18 BFCL native-FC — COMPLETE, FINAL, COMMITTED

Trees committed `76f5017` (fully clean: 0 poisoned rows, 0 PII, 200/200 per category);
docs committed `7a75a84`. Final overall (n=1000, budget 81920, deployed params,
draft-OFF):

| model | overall | runaways /1000 | per-event |
|---|---|---|---|
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` | **0.929** | 4 | 78–81 min (~17 tok/s) |
| `Ornith-1.0-35B-mlx-uniform-4bit` | **0.914** | 2 | ~21 min |
| `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` | **0.860** | 1 | ~12 min |

1.5 pp gap on accuracy is INSIDE the ~±4 pp MDE — inconclusive; **the runaway-tax
ranking number favors `Ornith-1.0-35B-mlx-uniform-4bit`** (~3.8× cheaper per event at
the same ~2% parallel-category rate). Full story + corrections: lab-notebook
2026-08-24 entries.

## O40 smoke verdict (lab-notebook entry + open-questions C24–C26)

- **Batched path PASSES** (mtp engaged, 148 rounds / 87% acceptance, budget honored).
- **Cached path ENGAGES** — probe measured 1.93× decode with the drafter — **but
  reports NULL draft counters** (reporting gap: batched computes them via
  `speculative_stats_since`; cached telemetry reads chunks that never carry them).
  **M6b's engagement tripwire needs cached-path counters (benchmark traffic decodes
  there) → C24 is the gate for M6b.**
- Phase A (fail-loud) inconclusive: the refusal WORKS (model unservable, chat errors)
  but the smoke greps the wrong log at the wrong time — smoke-harness bug, not fork.
- NEW: C25 penalties + inline mtp silently drop the penalty (no live impact,
  deployed profiles pin 0.0); C26 seeds may be ignored on the cached path
  (length-identical outputs across 3 seeds — byte-compare check is seconds).

## Operator decisions PENDING (surface, don't act)

1. **PUSH**: the stack is 5 commits ahead of origin (`d016b05` piicheck corpus-path
   fix, `5d4c3df` modelnames bfcl-row fix, `76f5017` M18 data, `7a75a84` M18 docs,
   and the O40-smoke/handoff docs commit at HEAD — count verified with
   `git status --short --branch`). Needs fresh in-turn approval.
2. **C24** — fund cached-path draft-counter reporting in `../mlx-vlm` (blocks M6b's
   tripwire). Design plan first per the O40 rule.
3. **C25** — fix the penalties+inline-mtp gate alongside C24?
4. **C26** — run the seed byte-compare check before M6b paired draws.

## NEXT (C20 sequencing, updated)

1. C24 fork work (after GO + design plan) → re-run the smoke (fix its phase A while
   in there) → M6b quality OFAT (MTP ON vs OFF at deployed params, engagement
   tripwire on every arm).
2. O39 (C21): go-language M3 replication (~40 min/model) BEFORE any M9 spend.
3. M23 (~4 h, both arms fresh), M24 (harness committed `de2d6d8`).

## Standing footguns (unchanged + new)

- **rtk condenses git output — a REJECTED commit prints what looks like success.**
  Verify `rc` + `git log -1` after every commit. Both guard hooks fired real
  rejections this session (piicheck: corpus `/user/home/datasets/` path; modelnames:
  corpus row value + the fix's own commit message) — all false positives, all fixed
  TDD rather than bypassed with `--no-verify`.
- `mlx-serve start` takes `--port` as a CLI flag; a yaml `port:` key is silently
  ignored. Worker stderr goes to `~/.mlx-serve/logs/<model>.log`, stdout to DEVNULL.
- The M18 watcher did NOT self-exit when its driver died (ticked 7 min past the
  death); killed by PID. If reusing `m18_watch.py`, fix its driver-death check.
- `MLX_VLM_CACHE_SESSION_MAX=2` on every router start; APC off, verified at worker;
  `os.setsid` for anything long-lived; one resident model; full registry names
  everywhere incl. chat prose; never `git push` without explicit in-turn approval.
- `main_models.yaml` working-tree diff (local hf_path overrides, `/Users/…`) is
  INTENTIONAL and must never be committed.

**Order of resumption: this file → `docs/PLAN.md` → `docs/open-questions.md`
(C24–C26 are the fresh decision queue).**
