# Handoff — rewritten 2026-08-23 ~18:15 (M3+M4 DONE & committed; vision restored on the pick; AGENTS.md slimmed + guards; O39 filed)

Single box (M5 Max 64 GB), SINGLE attended session owns everything. If generate/opencode
processes you didn't launch appear, investigate ownership before acting.

## Where things stand (all committed unless noted)

- **M3 opencode Run A DONE + committed (`e3c682b`)**: `Ornith-1.0-35B-mlx-uniform-4bit` 19/22,
  `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` 12/22, `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`
  13/22 (all 9 fails = xhigh stall-kills). **Direction INVERTS the aider B evidence**
  (single-attempt vs repair; McNemar 8:1 p=0.039 nominal, not Holm-surviving at n=22).
  **O39 (OPEN)**: does the inversion trigger M9 now? Session recommends a go-language
  replication first (~40 min/model). Mechanism finding: the B pick mis-copies random scratch
  suffixes when reconstructing ABSOLUTE paths (5/10 fails were ~25 s reject-give-ups on
  nonexistent paths). Harness exonerated — TMPDIR fix verified against the opencode session
  store; rows born PII-clean now (`e883ebf`).
- **M4 Run B DONE + committed (`3f0ef21`)**: `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`
  9/22, last place; 11/13 fails are ≤15 s boundary give-ups — the aider malformed-edit
  deficiency reproduced on a MATCHED serving path (old confound resolved). Only model to
  solve `dominoes`. vs `Ornith-1.0-35B-mlx-uniform-4bit` p=0.0063, Holm-surviving.
  Its rows APPEND after 4 legacy 2026-08-16 rows — segment by `opencode_version`.
- **Vision restoration 4a DONE**: `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` was BLIND
  (tower reshape crash); `scripts/graft_vision_tower.py` grafted the parent's tower (8-bit
  g64, 57 modules, +0.74 GB). **Trunk certified at two levels** (shards md5-identical;
  `scripts/graft_logit_check.py` logit-BIT-identical). Post-graft probe SEES. Uploaded
  `caslca` rev `eee677f5`; registry note committed (`0f10e97`). `benchmark/probe_vision.py`
  is the standing SEES/BLIND probe (known-positive-validated against
  `Ornith-1.0-35B-mlx-uniform-4bit`).
- **4b IN FLIGHT**: bf16 tower grafts for `Qwen3.8-27B-mlx-uniform-4bit` +
  `Qwen3.8-27B-static-mixed-4bit` from `unsloth/Qwen3.8-27B` (upstream repo) <!-- allow-shorthand --> (graft ≥ re-conversion: trunk
  identity by file copy). Their checkpoints are DOWNLOADING to HF cache
  (log: `$STACK_WORKDIR/status/vision_graft/downloads.log`). Then per model: graft
  `--bits 16` → logit check → temp registry swap → probe SEES → upload → restore registry.
  `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` is architecturally text-only — NOT fixable.
- **NEW MEASUREMENT FACT (recorded in `docs/metrics.md` seeds section)**: unseeded-request
  byte-determinism holds WITHIN a server session only — a same-artifact control produced 3
  distinct outputs across 3 router restarts. HTTP sentinels cannot certify cross-restart
  equivalence; in-process logit comparison is the pattern. Mechanism attribution OPEN.
- **AGENTS.md slimmed 124KB → 17KB** (`bf817bc`+`fb5e7f3`+`c9a99d6`): rules terse, rationale
  moved to `docs/metrics.md`, `docs/serving-path.md`, `docs/box-notes.md`,
  `docs/two-box-archive.md`; size-guard test (28KB). Codified guards: `run.py generate`
  REQUIRES `--sampling-profile` (`2636af1`); `scripts/registry_commit.sh` mechanizes the
  registry dance (`656eb06`, used for real in `0f10e97`); workqueue refuses n≥40 generation
  entries without a `pilot` field (`a1c62c0`).

## Next (per PLAN §3 and the approved sequence)

1. Finish 4b (downloads → grafts → probes → uploads).
2. **Submodule bump** 0c1c8b17 → 0be496bf (operator: "soon"): pointer commit →
   `git submodule update --force` → router restart → `--limit 5` smoke + resolved-sampling
   readback (value ≠ registry default) + worker cmdline check. `THINKING_BUDGET_CLAMP_RATIO`
   still 0.8.
3. **M6a/M6c/M6d** predictor probes (nemotron_h_mtp + dspark need the bump) interleaved with
   **M18 BFCL** → **M23** conversion-bias A/B → **M24** effort diagnostic (effort joins the
   fingerprint FIRST) → M9 (pending O39 ruling).

## Known pre-existing test failures (flagged, untouched — need operator ruling)

- `test_pii_check::test_the_committed_corpus_is_clean` reads the WORKING TREE, so the
  intentional 3-line registry dirt keeps it permanently red on this box. Options: exempt
  `main_models.yaml` working-tree state, or have it read `git show HEAD:`.
- `test_deployed_profile::test_every_registry_model_is_registered_in_PARAMS`: the three <!-- allow-shorthand -->
  committed registry entries of the `Qwen3.8-27B` family were never added to `model_params.py` <!-- allow-shorthand -->
  PARAMS (fails on a clean checkout too).

## Standing footguns (unchanged)

- The opencode probe APPENDS rows — dedupe/segment before re-running partial arms.
- Background-waiter pgrep patterns must not self-match; `run_m3.sh`-style drivers +
  `driver.pid` files under `$STACK_WORKDIR/status/<milestone>/`.
- `Qwen3.8-27B` family templates default `reasoning_effort=xhigh` <!-- allow-shorthand --> —
  the whole 3.8 corpus is at MAX effort (M24); xhigh is the TARGET, medium diagnostic only.
- Full registry names EVERYWHERE incl. chat prose; hooks cover staged lines + commit msgs only.
- zsh does not glob on variable expansion (`GLOB_SUBST` off) — `ls $VAR_WITH_STAR` fails
  where python `glob` works.

## Push state

origin/main = `bcc6d37`. Local-only: 43fb0ca…715bbf9 (12 from before) + today's e3c682b,
e883ebf, b7fbcd1, 3f0ef21, bf817bc, fb5e7f3, c9a99d6, 2636af1, 656eb06, a1c62c0, 04cc3de,
0f10e97. **NO push without explicit in-turn approval.** Registry dirt = exactly 3 local
`hf_path` lines (commit via `scripts/registry_commit.sh`). `transcript.md` + NVSY stay
untracked.

**Order of resumption: this file → `docs/PLAN.md` → `$STACK_WORKDIR/status/` (live runs).**
