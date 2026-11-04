# P475a — fork `qualify` accepts a KV-format arm — SPEC v4, 2026-11-04 (four-eyes light; C230; v2 = design review round 1 of 1, `docs/reviews/p475a/`; v3 = C233; v4 = C280: rebuild on S′ with the parked change-review findings as requirements)

## Goal

P475's live-cache engagement preflight runs the fork's reviewed in-process R7 tool `dev/p369_phase2/qualify.py --predictor off` from
each arm's worktree. `qualify` refuses any registry outside the 16 accepted states (`registry_states.classify`: equal to the pinned
golden fixture except each MTP-certified entry's MTP keys), so it serves only the two committed KV formats and refuses 8 of the 10
P475 cells. Solving it means: `qualify`, when explicitly asked, accepts a registry that differs from an accepted state in EXACTLY the
KV-format keys of the ONE entry under test, and then runs unchanged — the live per-layer cache manifest checked against the arm's own
expected manifest, phase peaks recorded — so every P475 arm gets real engagement proof; without the flag nothing changes.

## Settled constraints

C218 / C230 (operator); fork production code (`mlx_vlm/` outside `mlx_vlm/tests/`) untouched; test-first; no push without approval; the
golden fixture and the 16-state design (C203) unchanged; full registry names.

## Interface

- `registry_states.classify_kv_arm(text, fixture, entry) -> (frozenset off, dict kv_delta) | None`: `None` unless `text`'s settings equal
  an accepted state (as `classify`) except that `entry` may ALSO differ in keys of `KV_ARM_KEYS = ("kv_bits", "kv_quant_scheme")` only
  (values valid for `kvmanifest.expected_manifest`; `quantized_kv_start` must stay 0); `kv_delta` = `{key: (fixture value, arm value)}`
  for the keys that differ (may be empty → identical to `classify`). Any other difference, a second entry differing, an unknown entry →
  `None`.
- `qualify.py --kv-arm`: requires exactly one `--entry`; `--predictor off` as before, or `--predictor on` ONLY when the arm commit's
  registry already serves the entry MTP-ON (its MTP keys present, i.e. the entry is not in the `off` set) — then no overlay is built and the
  committed arm registry is served as is (C233); any other `on` case refuses; replaces EVERY `classify` use with `classify_kv_arm(registry, fixture, entry)` — the gate AND the `off_entries` the
  `mtp_off` check reads (no separate `classify` call remains under `--kv-arm`);
  refuses on `None`; records `kv_arm: {entry, delta}` in the report; the entry's expected per-layer manifest is derived from the ARM
  registry (as today, from the live entry); the attention assertion follows the arm's EXPECTED manifest: under `attention_policy: fused_v1`, `sdpa_forced > 0`
  is required iff the expected manifest has a native-KV attention leaf (N16; TurboQuant's retained native layer), and `sdpa_forced == 0`
  otherwise (affine arms take the quantized-attention path) — the same rule applied without `--kv-arm`, where it reduces to today's;
  the report's reference block gains `label: "non-comparable: KV arm"` and `comparable: false` (C199), never a refusal. Without `--kv-arm`: byte-for-byte today's behaviour (tests pin it).

## Acceptance criteria

0. The attention rule: AF8 / AF4 for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (`fused_v1`) pass the full `request_problems` path with
   `sdpa_forced == 0`; N16 / TQ8 / TQ4 still require forced calls; today's no-flag behaviour unchanged for the committed registries.
1. `classify_kv_arm` unit tests (red first): each of N16 / AF8 / TQ8 / AF4 / TQ4 for each of the two picks accepted with the right
   delta; a second entry changed, a non-KV key changed, `quantized_kv_start != 0`, an MTP-key + KV change outside the 16 states, an
   unknown entry → `None`; empty delta == `classify`.
2. `qualify --kv-arm` tests: refusal paths; `--predictor on` on an arm registry that serves the entry MTP-ON runs without an overlay (the
   served argv carries the MTP flags and the expected manifest includes the drafter's cache), and refuses when the entry is MTP-OFF; report field; expected manifest from the arm; reference comparison labelled; the
   no-flag path unchanged.
3. Fork suite ×2 identical skip lists, 0 failed; eight audits green; production diff empty.

## v4 — rebuild (C280, P626)

The v3 candidate was lost (P626). v4 = v3 plus the following; where they differ, v4 wins.

- **Base:** the fork at the stack's current gitlink (S′, `1c7c8fa166582ac1a1c23ae9063527b2b5215b11`); work in a fork worktree on a local
  branch `p475a-kv-arm` (never a session scratchpad); the stack bumps the gitlink only after the fork commit is pushed (approval).
- **Entries:** `--kv-arm` and `classify_kv_arm` accept ONLY `Qwen3.8-27B-mlx-uniform-4bit` and `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`;
  any other entry → `None` / refusal (Sol r1-1).
- **Arm values:** the KV keys must form one of the five arm rows of `docs/specs/p475-kv-matrix.md` (N16, AF8, TQ8, AF4, TQ4) exactly —
  integer widths only; a fractional, non-finite or other width / scheme → `None` (Sol r1-2, r1-3). `expected_config` keeps the exact
  numeric width it serves (no `int()` truncation).
- **Robust `None`:** malformed YAML structure (`models: [null]`, non-mapping entries) and non-finite numbers return `None`, never raise
  (Sol r1-3).
- **Attention rule:** `native_attention` defaults to unset; a missing manifest / template yields only the manifest problem, never a
  spurious `sdpa_forced` problem (GLM r1-4).
- **No dead guard:** the `quantized_kv_start` rule is enforced in one place (the settings comparison); no unreachable second check (GLM r1-5).
- **Base state:** an arm built on ANY of the 16 accepted states (incl. one where a non-tested entry is MTP-ON) is accepted (GLM SR2).

## v4 acceptance additions

4. Driver tests without mocking `classify` / `classify_kv_arm`: a real arm registry as the live `main_models.yaml` for every arm × pick
   (10), asserting the report's `kv_arm`, the served argv built by mlx-serve's real `_build_command` spelling (`command_problems == []`),
   the expected manifest, and the attention counters (GLM r1-1, r1-2, SR1; Sol r1-4).
5. A driver test whose worker record has the WRONG `sdpa_forced` for the arm (e.g. > 0 for AF8 under `fused_v1`) → the entry is not
   completed, with the `sdpa_forced` problem (GLM r1-3).
6. Refusal tests: a third entry; a fractional width; `.inf`; `models: [null]`.

## Non-goals

Changing `classify`, the fixture or the 16-state rule; split key / value widths; non-zero `quantized_kv_start`; other entries. `kv_quant_mode` (TurboQuant mode) and `kv_group_size` stay at the fixture / CLI defaults; `--kv-arm --predictor on` building an overlay.

Declined: the claim that `guard_problems` refuses arm worktrees — it checks the FORK head (unchanged: P475 arms are stack commits on the same
fork commit) and an unmoved stack head. Changes after the round are not re-reviewed (light).
