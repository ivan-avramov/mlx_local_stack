# Handoff — rewritten 2026-08-23 ~19:15 (SESSION-END CHECKPOINT: M3+M4 scored, vision restored ×3, submodule bumped+smoked, AGENTS.md slimmed; nothing running)

Single box (M5 Max 64 GB), SINGLE attended session owns everything. If generate/opencode
processes you didn't launch appear, investigate ownership before acting. **NOTHING is running
at this checkpoint** — no generate, no opencode, router up (lean) with
`Ornith-1.0-35B-mlx-uniform-4bit` resident from the bump smoke.

## Done today (all committed)

- **M3 opencode Run A (`e3c682b`)**: `Ornith-1.0-35B-mlx-uniform-4bit` 19/22,
  `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` 12/22, `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`
  13/22 (all 9 fails xhigh stall-kills). **Direction INVERTS the aider B evidence**
  (single-attempt vs repair; McNemar 8:1, p=0.039 nominal, NOT Holm-surviving at n=22).
  Mechanism: the B pick mis-copies random scratch suffixes when reconstructing ABSOLUTE
  paths (5/10 fails = ~25 s reject-give-ups on nonexistent paths). Harness exonerated
  (TMPDIR fix verified against the opencode session store). Rows born PII-clean now
  (`e883ebf`). Full analysis: ledger §1 "Run A".
- **M4 Run B (`3f0ef21`)**: `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` 9/22, last place;
  11/13 fails ≤15 s path-infidelity give-ups — the aider malformed-edit deficiency
  reproduced on a MATCHED serving path. Only model to solve `dominoes`. vs
  `Ornith-1.0-35B-mlx-uniform-4bit` p=0.0063 (Holm-surviving). Its jsonl carries 4 legacy
  2026-08-16 rows first — segment by `opencode_version`.
- **Vision restoration COMPLETE (steps 4a+4b)**: all three blind models now SEE, each with a
  TWO-LEVEL trunk certification (shards md5-identical + `scripts/graft_logit_check.py`
  logit-BIT-identical) and a post-graft `benchmark/probe_vision.py` SEES:
  `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (8-bit g64 tower, rev `eee677f5`),
  `Qwen3.8-27B-mlx-uniform-4bit` (bf16 tower, rev `393413e9`),
  `Qwen3.8-27B-static-mixed-4bit` (bf16 tower, rev `be1aa462`). Registry notes committed
  (`0f10e97`, `58a2198`). `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` = architecturally
  text-only, not fixable. O38's vision strike on the C 1st pick is CLEARED.
- **Submodule bump DONE + SMOKED (`111bb53`)**: `src/mlx-vlm` 0c1c8b17 → `0be496bf`.
  Verified at runtime: worker cmdline carries full `--generation-defaults` (t0.4 tune), NO
  draft flags, kv 262144/262144; `THINKING_BUDGET_CLAMP_RATIO` still 0.8 (generation.py:537);
  5-item generate smoke 5/5 `finish=stop` (4/5 converged; HumanEval/94 budget-hit at 82072 —
  n=1 right-tail, not a regression signal), manifest carries the new sha. Smoke rows
  ARCHIVED OUT-OF-TREE (`$STACK_WORKDIR/status/bump_smoke/smoke_archive/`), results tree
  byte-clean vs HEAD. ⚠️ Remember: rows across the sha never pool.
- **AGENTS.md slimmed 124KB → 17KB** (`bf817bc`,`fb5e7f3`,`c9a99d6`): rules terse, essays in
  `docs/metrics.md` / `docs/serving-path.md` / `docs/box-notes.md` /
  `docs/two-box-archive.md`; 28KB size-guard test. Codified: `run.py generate` REQUIRES
  `--sampling-profile` (`2636af1`); `scripts/registry_commit.sh` = the registry dance
  (`656eb06`); workqueue refuses n≥40 generation entries without a `pilot` field (`a1c62c0`).
- **NEW FACT (docs/metrics.md seeds section)**: unseeded byte-determinism holds WITHIN a
  server session only — same-artifact control diverged across 3 router restarts. HTTP
  sentinels can't certify cross-restart equivalence; in-process logit comparison is the
  pattern. Mechanism attribution OPEN.

## Decisions waiting on the operator

- **O39**: does the M3 inversion trigger M9 now? Session recommends a go-language
  replication first (~40 min/model, n=44 paired).
- **Two pre-existing test failures** (not today's work): `test_pii_check` reads the working
  tree so the intentional registry dirt keeps it red; `test_deployed_profile` PARAMS misses
  the three committed `Qwen3.8-27B`-family registry entries <!-- allow-shorthand -->
  (fails on clean checkout).
- 12+15 local-only commits await push approval.

## Next per PLAN §3 (fresh session starts here)

1. **M6a/M6c** predictor probes — UNBLOCKED by the bump (nemotron_h_mtp + qwen3_dspark
   drafters now deployed); M6a = smoke + paired one-item ON/OFF speed probe on
   `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` + one `Qwen3.8-27B` recipe <!-- allow-shorthand -->;
   ≥1.3× gate.
2. **M18 BFCL** (~1 h box) — `bench/bfcl_adapter.py` path, NOT `run.py generate`.
3. **M23** conversion-bias A/B → **M24** effort diagnostic (effort joins the fingerprint
   FIRST — O36-class hazard) → M9 (pending O39).

## Standing footguns

- opencode probe APPENDS rows — dedupe/segment before re-running partial arms.
- `Qwen3.8-27B` family chat templates default `reasoning_effort=xhigh` <!-- allow-shorthand -->
  — whole 3.8 corpus at MAX effort; xhigh is the TARGET, medium diagnostic only.
- Full registry names EVERYWHERE incl. chat prose (hooks cover staged lines + commit msgs).
- zsh does not glob on variable expansion; and NEVER retype a truncated hash — resolve refs
  programmatically (this session fabricated a snapshot-hash tail; caught by FileNotFound).
- Background-waiter pgrep patterns must not self-match; hourly assessment wakeups + 300s
  watcher daemons for every run; keep the box busy.

## Push state

origin/main = `bcc6d37` (12 pre-session local commits 43fb0ca…715bbf9). Today adds:
e3c682b, e883ebf, b7fbcd1, 3f0ef21, bf817bc, fb5e7f3, c9a99d6, 2636af1, 656eb06, a1c62c0,
04cc3de, 0f10e97, 312990f, e5cda13, 58a2198, 111bb53 + this handoff. **NO push without
explicit in-turn approval.** Registry dirt = exactly 3 local `hf_path` lines (commit via
`scripts/registry_commit.sh`). `transcript.md` + NVSY stay untracked.

**Order of resumption: this file → `docs/PLAN.md` → `$STACK_WORKDIR/status/` (live runs).**
