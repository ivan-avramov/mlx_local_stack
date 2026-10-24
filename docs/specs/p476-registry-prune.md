# P476 — prune the unpublished registry entries — SPEC v3, 2026-10-24 (four-eyes light; v2 = design review round 1 of 1 applied; v3 = change-review fixes + the operator-approved OWUI tombstones, C222; `docs/reviews/p476/`)

## Goal

`main_models.yaml` serves 11 entries but the stack publishes 5: the README's B ladder (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`,
`Qwen3.8-27B-mlx-uniform-4bit`, `Ornith-1.0-35B-mlx-uniform-4bit`, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`) and the C shortlist's
`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`. Six experiment entries remain registered and partly exposed to clients:
`gemma-4-31B-it-qat-6bit`, `gemma-4-26B-A4B-it-OptiQ-4bit`, `Qwen3.8-27B-static-mixed-4bit`, `Qwen3.8-27B-OptiQ-4.5bpw-mixed`,
`Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`, `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit`. Solving it means: the registry and every
configgen-generated client / bench carrier name exactly the published entries, the five remaining entries serve byte-identically,
every harness that reads the registry keeps working on the pruned file, and nothing historical (rows, results, docs, frozen
harnesses) is rewritten — so the P426 Wave-2 freeze (v8) qualifies the registry as it will ship (C218).

## Settled constraints

- Operator ruling P476 ("prune as you see fit"); C218 (arms are stack commits served as shipped); AGENTS.md (configgen for OWUI
  files, never hand-edited; the four sampling carriers stay in sync; full registry names; public repo PII rules; tests first for
  behaviour changes; edit forks in `../mlx-vlm`, never `src/*`; no push without in-turn approval).
- Production code of both forks is untouched (`git diff <base> -- mlx_vlm ':!mlx_vlm/tests'` empty in the fork).

## Scope (exact)

**S1 — registry** `main_models.yaml`: delete the six entry blocks, each with the comment lines that belong only to it (including
the `# QAT / optimized-quant experiments …` section header if no remaining entry sits under it). Comment blocks that document no pruned entry (e.g. the `RETIRED 2026-08-26 (C33 …)` note on the
removed `Qwen3.8-27B-4bit`) stay. No other byte changes: the five remaining entry blocks, the header comments and every top-level non-`models` key stay byte-identical.

**S2 — generated carriers**: every client and bench carrier is generated from the registry by `configgen` (`configgen/targets.py`:
opencode, aider, vscode, zed, OWUI settings / models, and the bench carriers `opencode_bench.json`, `opencode_bench_v2.json`,
`opencode_bench_v2_web.json`, `opencode_bench_v2_web_tg1.json`, `aider_bench.model.settings.yml`). Regenerate with
`.venv-bench/bin/python -m configgen generate`; never hand-edit. The tg1 carrier is one of the probe's generation data files
(`arm_opencode.GENERATION_DATA`), so the runner-computed `probe_code_sha256` moves (expected; Wave 2 is a new epoch) — no field in
the carrier itself changes beyond the removals; the frozen 1.18 / aider harnesses never run again; their historical carrier bytes stay reachable in git history (rows record the commit). Baseline
`configgen check` rc 0 (2026-10-23).

**S2b — OWUI tombstones (C222)**: `main_models.yaml` gains `openwebui.retired_model_ids` listing the six pruned names; the OWUI
emitter folds them into `excluded_model_ids`, so `openwebui-init/reconcile_models.py` keeps flagging an unmanaged saved registration
of a pruned id as stale on every box. Tests: the emitter output contains them; reconcile flags an unmanaged saved registration of a
retired id (dry-run lists it; `--apply` without `--prune` refuses).

**S3b — carrier-derived pins (v3)**: regenerating the carriers moves pinned identities — the tg1 campaign policy hash
(`test_c147_inject.py`), the v2 carrier fixture (`test_m61_web_audit.py` / `fixtures/m59_policy.json`) and the P371 goldens
(`test_p371_baseline.py`, `test_p371_hermetic_scan.py`). Each is refreshed by its own procedure (P371: `P371_REGEN_GOLDEN=1`), never
loosened; the old → new values are recorded in the test / fixture comments (the old tg1 campaign hash = the C144 / M63 epoch); only
carrier-derived fields may move (verified by diffing the regenerated goldens).

**S3 — stack tests**: tests that assume a pruned entry is in the LIVE registry (e.g. `test_deployed_profile.py`'s
`params_for("gemma-4-31B-it-qat-6bit", "deployed", registry_path=REGISTRY)`) keep the PROPERTY they test: a test whose literals are
entry-specific (e.g. the `gemma-4-31B-it-qat-6bit` deployed values) reads a fixture registry holding that entry's baseline block; others retarget to a
remaining entry. New tests (red first): (a) the `models:` entry names of the live registry == exactly the five names in the Goal
(an explicit list, not scraped from the README; `task_model` is not a `models:` entry); (b) every model id in every configgen output
⊆ registry `models:` names ∪ {`task_model`}, and the OWUI menu == `openwebui.models` (unchanged, four entries).

**S1b — OWUI saved registrations (read-only pre-check)**: the OWUI policy's `excluded_model_ids` is derived from the registry, so
after the prune an unmanaged saved registration of a pruned id would no longer be flagged stale by `reconcile_models.py`. Before S1,
if the OWUI data volume exists: start only the OWUI service, run the reconcile dry-run under the CURRENT policy and record any saved
registration among the six; none → proceed; any → stop and show the operator (removal is the existing `publish_models.py --prune`
flow with a backup, the operator's call). OWUI is stopped afterwards. **Result on m5max-128 (2026-10-23): no `open-webui-data/` on this box — nothing
saved, nothing to check.** Residual: a box that has OWUI data (e.g. `m5max`) runs the same read-only check on a DB copy before
its first OWUI start after pulling the prune.

**S4 — fork (dev / tests only)**, after the stack commit of S1–S3 exists: regenerate
`mlx_vlm/tests/fixtures/stack_registry_golden.yaml` by its header procedure from the pruned registry (all four MTP-certified
entries' ENTRY_OFF substitutions reversed), update `registry_states.FIXTURE_SHA256`, `test_mtp_verify_scan.FIXTURE_SHA256` /
`FIXTURE_SOURCE` and the header's source commit; drop the four pruned entries from `dev/p369_phase2/qualify.py` `ENTRIES` (it keeps the three MTP entries; no entry is
added — R7's scope is not widened) AND their rows from `dev/p415_reference_peaks.json` (`load_references` refuses a reference for an
entry outside `ENTRIES`; the rows stay in git history); `mlx_vlm/tests/test_p415_qualify.py`: the seven-entry set / `len == 7`
assertions become the three-entry set, and the `served`-arm coverage (today via the test constant bound to `Qwen3.8-27B-static-mixed-4bit`,
≈ 20 sites) moves to a SYNTHETIC served entry injected into `ENTRIES` and a synthetic registry in the test (monkeypatch), so the served
code path stays tested (also in `mlx_vlm/tests/test_p426_qualify_predictor.py`); `qualify.py` docstrings say three, not seven; new test: `load_references` on the REAL `dev/p415_reference_peaks.json` against the real `ENTRIES` passes.

**S5 — submodule bump** of `src/mlx-vlm` to the S4 commit after the fork commit is published (operator approval for the push).

## Interfaces / traces

- Success: stack S1–S3 commit → stack suite green → fork S4 commit → fork suite ×2 + eight audits green, production diff empty →
  (approved) fork push → stack bump → K3 real-entry-point test + stack suite green; `MLX_REQUIRE_STACK_REGISTRY=1` live check in
  the fork classifies the pruned live registry as all four entries OFF; `registry_states.overlay_on` round-trips each entry.
- Failure: any S1 byte change outside the six blocks, a remaining entry whose parsed settings differ, `configgen check` failing,
  a carrier still naming a pruned entry, or the fork live check refusing → the change is not accepted.

## Acceptance criteria

1. Registry entry names == {the five}; parsed settings of every remaining entry and all top-level keys identical to the baseline
   except the added `openwebui.retired_model_ids`; the textual diff of `main_models.yaml` is deletions plus that one list.
2. `configgen check` rc 0 after `generate`; no generated file names a pruned entry; every generated-file diff is the removal of
   pruned entries only (no other line changes).
3. Untouched: `benchmark/results/`, `docs/` (except this spec and the decision record), README, `benchmark/bench/model_params.py`,
   scripts, `configgen/` code except the S2b emitter change and its tests.
4. Stack suite with `STACK_WORKDIR` set: 0 failed, skip list unchanged except tests removed / retargeted, listed.
5. Fork: fixture regenerated per its header; suite ×2 identical skip lists, 0 failed; eight audits green; production diff empty;
   the opt-in live check passes against the pruned registry; `load_references(REFERENCES)` on the real file passes.
7. S1b recorded (no OWUI volume / none saved / the operator's ruling).
6. After the bump: the stack's K3 test (real fork entry points) and the stack suite pass.

## Non-goals

Historical one-off tools that target non-registry models (`benchmark/mem_decompose.py`, `benchmark/run_bfcl_h2h.sh`,
`benchmark/w0_gemma_*.sh`, `benchmark/bfcl_shim/sitecustomize.py`): a pre-existing class (they already name long-gone entries) —
residual of P476, handled as P478.

mlx-serve's own `tests/fixtures/stack_registry_golden.yaml` (warn-only drift; refreshed at the planned mlx-serve v0.3.0 bump);
deleting weights or HF repos; editing historical docs / results / rows; retiring `model_params` knowledge; README text.

## Assumptions

- A1: no runtime path resolves a pruned name from the registry except the carriers listed (survey `git grep`, 2026-10-23).
- A2: `configgen generate` is deterministic and emits only registry-derived content (no hard-coded entry names in `configgen/`, checked).

## Open questions (designer's recommendation)

- Q1: keep `model_params.py` entries for the six (recommended: keep — per-model knowledge used by regrading old rows, harmless).
- Q2: RESOLVED in v2 (review F1): the four rows are removed (the loader refuses them); history stays in git.

Changes after the last review round (v2 → v3) are not re-reviewed by a design round (light mode; no architecture change).
