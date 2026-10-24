# P475a — fork `qualify` accepts a KV-format arm — SPEC v1, 2026-10-24 (four-eyes light; C230)

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
- `qualify.py --kv-arm`: requires exactly one `--entry`; replaces the `classify` gate with `classify_kv_arm(registry, fixture, entry)`;
  refuses on `None`; records `kv_arm: {entry, delta}` in the report; the entry's expected per-layer manifest is derived from the ARM
  registry (as today, from the live entry); a reference-peak comparison for that entry is reported labelled
  `non-comparable: KV arm` (C199), never a refusal. Without `--kv-arm`: byte-for-byte today's behaviour (tests pin it).

## Acceptance criteria

1. `classify_kv_arm` unit tests (red first): each of N16 / AF8 / TQ8 / AF4 / TQ4 for each of the two picks accepted with the right
   delta; a second entry changed, a non-KV key changed, `quantized_kv_start != 0`, an MTP-key + KV change outside the 16 states, an
   unknown entry → `None`; empty delta == `classify`.
2. `qualify --kv-arm` tests: refusal paths; report field; expected manifest from the arm; reference comparison labelled; the
   no-flag path unchanged.
3. Fork suite ×2 identical skip lists, 0 failed; eight audits green; production diff empty.

## Non-goals

Changing `classify`, the fixture or the 16-state rule; split key / value widths; non-zero `quantized_kv_start`; other entries.
