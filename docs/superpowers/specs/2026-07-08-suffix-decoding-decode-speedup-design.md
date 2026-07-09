# #4 — Suffix (prompt-lookahead) decoding: quality-neutral decode speedup

**Date:** 2026-07-08. **Status:** design, approved (pending spec review). Phase-2 build #4.
Parent program: `docs/superpowers/specs/2026-07-07-phase2-optimization-program-design.md`.

## Goal & context

Re-open **drafter-free suffix decoding** (n-gram / prompt-lookup speculative decoding — the
fork's `--draft-kind suffix`) as a **decode-speed** lever for the distill, gated on
**quality preservation**. The selection campaign ran suffix OFF because it is not
bit-identical to greedy autoregressive decode (bf16 verify-vs-decode kernel numerics flip
argmaxes; *gemma* cascaded — see [[project_suffix_decoding_nonlossless]]) and explicitly
**deferred the speed question to Phase 2**. This is that evaluation, under the daily-driver
**sampling** config (not greedy), where the criterion is distribution quality, not bit-identity.

Target: **distill's slow decode** (9.6 tok/s @256K). Mechanism: drafts the next span by copying
from the prompt/context (no draft model), verifies a block in one forward. Coding output reuses
in-context identifiers/signatures/lines verbatim → high n-gram acceptance exactly where it pays.

## Enable mechanism (registry-driven, already plumbed)

Suffix is turned on per-model in `main_models.yaml`; the router (`mlx_serve/config.py:79–85`)
reads it and the worker spawn (`process_manager.py:106–116`) passes it through:
```yaml
    draft_kind: suffix        # engages drafter-free n-gram / prompt-lookup
    draft_block_size: <N>     # max proposal length (optional; default from worker)
    suffix_min_match: <N>     # min n-gram match length (default 2)
    draft_cooldown: <N>       # pause after N zero-accept rounds (0=off)
```
Experiment uses **variant registry entries** (`…-suffix`), same OFAT pattern as the #2 `-kv3`
variant — baseline (suffix off) and variant (suffix on) coexist, uncommitted.

## Subject & config

- **distill (primary).** Dense qwen3_5 → block-verify is one extra dense forward (suffix-friendly);
  and it's the decode-slow winner. Config = the shipped daily-driver one (temp 0.3, top_p 0.95,
  top_k 20, min_p 0.0, **presence_penalty 0.0** → no logits-processor fallback, suffix engages).
- **Ornith (spot-check, verify-before-discarding).** Ornith is MoE (256/8 experts): a batched
  block-verify activates the *union* of experts across the draft window (≫8) → verify is expected
  to be disproportionately expensive, plus its decode is already fast (37–72 tok/s). Hypothesis:
  net-neutral-to-negative. **Do not pre-discard — measure a short suffix-on decode + acceptance
  on Ornith and let the harness confirm** before ruling it out (per campaign discipline).

## §1 Correctness audit (make-or-break for the gate)

Before measuring, confirm the verify/accept path **applies the sampler** (temperature, top_p,
top_k, min_p) at each drafted position so accepted tokens are drawn from the *same* distribution
as plain decode. The code note says verify "samples raw target logits" — if "raw" omits
temperature, accepted blocks follow a different (hotter) distribution → guaranteed gate failure,
and the fix is to apply the sampler inside the block verify (stateless per-position transforms:
temp/top_p/top_k/min_p — feasible). Deliverable: a one-line verdict (sampler applied Y/N) + the
fix if N. (Stateful penalties already fall back to plain decode; our config has none, so N/A.)

## §2 Quality gate (A — quality must be preserved)

- **LCB pass@1 + convergence**, distill @t0.3, **suffix-ON vs suffix-OFF, same items, OFAT.**
- Suffix is non-bit-identical, so per-item outputs differ; the gate is **aggregate pass@1 +
  convergence within noise** (no dramatic drop, convergence intact) — NOT item-identical.
- Grading via the M5 LCB grader (`.venv-lcbgrade`); quality is box-independent.
- **Ship only if it holds.** If it regresses despite a correct sampler → the bf16 verify-numerics
  issue bites qwen-arch under sampling too → keep suffix off (documented, expected outcome logged).

## §3 Speed measurement

- **decode tok/s (ON vs OFF)** + **acceptance rate** + **mean accepted block length**, same-box (M5),
  fixed context — report net effective decode tok/s and the mechanism numbers.
- Two workload points (acceptance is workload-dependent):
  1. **edit-heavy probe** (synthetic: supply a file, request a small edit → output the file with
     the change; high verbatim reuse = suffix best case; fast to run).
  2. **generation-heavy** (LCB-style novel solution; lower reuse = conservative case).
- Report the win as a function of context reuse; flag that novel reasoning gets little.

## §4 Light param sweep

Sweep `suffix_min_match` (2 vs 3) and `draft_block_size` for the acceptance/speedup knee. Small
OFAT on the edit-heavy probe (fast). Pick the setting that maximizes net tok/s without lowering
acceptance-quality.

## §5 Decision & ship

If distill is **quality-neutral (§2) AND net-faster (§3)** → add `draft_kind: suffix` (+ tuned
params) to distill's registry + opencode config; record acceptance mechanism + workload caveat in
`campaign-results.md`. Ornith: ship only if the spot-check shows a real net win (expected not to).
Otherwise keep off and log the negative result so it is not re-chased.

## Risks / known
- **Non-bit-identical (bf16 verify numerics)** — inherent; §2 is the safety net. gemma cascaded
  under *greedy*; qwen-arch under *sampling* is the open question §2 answers.
- **MoE verify cost (Ornith)** — the reason Ornith is spot-check-only.
- **Workload dependence** — the win tracks context reuse; edit-heavy agentic = best, novel
  reasoning = least. Report honestly, don't generalize one number.

## Testing
The execution-gated LCB quality gate (§2) IS the correctness test. The correctness audit (§1) is a
code read + a small distribution spot-check (suffix-on vs off logits at fixed seed). Speed (§3) is
measured, not asserted.
