# M76 B2 — fork dev tools accept the TQ4 `tq4_attention` arms (`qualify`, `registry_states`, P369 tuple) — SPEC v1, 2026-11-11 (four-eyes light; C325)

## Goal

M76 (`docs/specs/m76-tq4-certification.md`) preflights its stage-1 arms with the fork's reviewed in-process tool
`dev/p369_phase2/qualify.py --kv-arm` (live per-layer cache manifest, phase peaks), measures M1 memory with `qualify`, and runs its
stage-2 exactness instrument with `dev/p369_phase2/orchestrate.py` (P369 phase 2 E1c + E2). None of them accepts an entry carrying
the 1.3 registry key `tq4_attention`: `qualify` refuses it as an unknown key (`SERVING`), `registry_states.classify_kv_arm` only
knows the five P475 rows (no mode), the `--kv-arm` OFF derivation leaves a registry mlx-serve refuses (fixed by M77 = B0), a full
MTP-ON `--kv-arm` qualification is refused for any KV delta, the fingerprint cannot tell the modes apart, and P369's `PICKS` holds one
native16 tuple per model whose preparation requires an all-OFF stack root and builds ON through `overlay_on`. Make the three tools
accept exactly M76's arms of `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` — X (`kv_bits: 4`, `tq4_attention: m72_exact`),
V (`m72_v1`), XO (X with MTP OFF) — with every check they apply today, while every existing pick, arm, state, fingerprint and
report stays byte-identical. Solving it means: `qualify --kv-arm --entry <pick> --predictor off` and `--predictor on
--engagement-only` pass on X / V / XO arm commits; `qualify --kv-arm --predictor on` (certifying) runs on X only when bound to X's
stage-2 PASS record; `orchestrate.py` runs E1c + E2 for a new campaign tuple `m76-x` with ON from the X commit and the cross-load
OFF from the XO commit; and the existing tests and goldens pass unchanged.

## Scope (files)

Fork `../mlx-vlm` `dev/p369_phase2/`: `qualify.py`, `registry_states.py`, `orchestrate.py`, `worker.py`, `kvmanifest.py` (only if
needed); tests `mlx_vlm/tests/test_m76_b2_*.py`. No production file (`mlx_vlm/` outside `tests/`) changes.

## Settled constraints

- (C325) M76 arms and stages as specified there; B0 (M77) makes XO servable; this build depends on M77's fork commit as its base.
- (P475a, C199, C203) The 16 accepted states and the golden fixture are unchanged; the certified-argv binding is never waived.
- (P369 v13) Same-instance triple, C1 / C2, verdict precedence unchanged.

## Interfaces

**`registry_states`.**
- `KV_ARM_KEYS = ("kv_bits", "kv_quant_scheme", "tq4_attention")`; existing rows require `tq4_attention` absent.
- `KV_ARM_ROWS` gains `TQ4X = (4, "turboquant", "m72_exact")` and `TQ4V = (4, "turboquant", "m72_v1")`, accepted only for
  `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`; a mode on any other entry, a mode with another row's bits / scheme, or any other
  mode string → None.
- `classify_kv_arm` restores all three keys from the fixture (absent stays absent); `kv_delta` includes `tq4_attention` when it
  differs (`(None, mode)`). The OFF state of the entry (its three MTP lines commented, as `ENTRY_OFF`) with a TQ4X / TQ4V row is
  accepted (XO), exactly as today's OFF states are.
- `classify`, `overlay_on`, `ENTRY_OFF` unchanged.

**`qualify.py`.**
- `SERVING["tq4_attention"] = ("", "--tq4-attention", "nonempty")` (mlx-serve passes it only for `type: vision`; the entry is vision).
- The `--kv-arm` OFF derivation (`mtp_off_registry`) strips the three MTP keys and keeps `tq4_attention` (servable after M77).
- `--kv-arm --predictor on` with a non-empty delta: refused as today, unless `--certified-by <path>` names a stage-2 record that
  (a) is a P369 phase-2 `m76-x` report with E1c and E2 verdict PASS, (b) records the same stack root commit (the arm commit) and
  fork head as this run, and (c) whose ON worker argv equals this run's served argv exactly; then the run proceeds as a certifying
  ON run with `certified_by` (path + sha256) in the report. `--engagement-only` unchanged.
- The expected manifest for TQ4X / TQ4V / XO = today's TQ4 manifest (15 TQ4 layers + the native last layer; the mode does not change
  cache classes); the `sdpa_forced` rule unchanged (the native leaf requires forced calls under `fused_v1`).
- `fingerprint_of` adds `tq4_attention: <mode>` ONLY when the expected config has a mode (absent ⇒ byte-identical); the report's
  `kv_arm` block records the mode.

**`orchestrate.py` / `worker.py` (P369).**
- `TUPLES = {"m76-x": dict(pick="Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", kv="tq4", verify_policy="joint_v1",
  tq4_attention="m72_exact", drafter=_DENSE, items_from_kv="native16", production=<M77 fork commit's production ref>)}`; `PICKS`
  unchanged; `--tuple m76-x` (mutually exclusive with `--pick`) selects it.
- Under a tuple: `--stack-root` = the X arm worktree (its committed registry serves the pick MTP-ON; validated by
  `classify_kv_arm` with delta `{kv_bits, tq4_attention}`), `--off-stack-root` = the XO arm worktree (validated the same way, pick
  MTP-OFF); ON argv from the X registry and OFF argv from the XO registry, both through mlx-serve `_build_command`; no overlay; the
  all-OFF-root rule (`registry_off_problems`) and `classify` are not applied to a tuple run. `argv_scan_problems` expects
  `--mtp-verify-scan joint_v1` and `--tq4-attention m72_exact` on ON, neither on OFF.
- E2 items come from the native16 C84 bundles of the pick (`items_from_kv`); the token-count check unchanged.
- The production pin of a tuple run is the tuple's `production`; `PRODUCTION` for the existing picks unchanged.
- The same-instance triple additionally asserts the target's `tq4_attention` hook object (identity and `name`) unchanged across
  ON / OFF1 / OFF2, and ON-trajectory engagement adds: the `d2_verify` route counter moved and every `fallback:*` stayed 0 (read
  from `tq4_fast.route_counts()` before / after the trajectory).
- E1c cells for the tuple: the TQ4 thresholds (verify `lengths[0]` straddling 2,048; a block straddling the D2 block-count tier
  above 65,536) and the native-layer MLX thresholds (1,024 / 8,192 / 32,768 / 65,536) plus scale cells at 131,072 and 260,096,
  sized by the existing prompt sizer.

## Acceptance criteria

1. Red-first, no GPU (fixture and synthetic registries): `classify_kv_arm` accepts X / V / XO for the pick with the right delta and
   refuses a mode on `Qwen3.8-27B-mlx-uniform-4bit`, a mode with AF4 / TQ8 values, an unknown mode, `false` / `0` / `null` as a mode;
   every existing row and refusal unchanged.
2. `qualify` (driver tests with the real arm registries and mlx-serve's real `_build_command` spelling, as P475a v4 criterion 4):
   X / V / XO argv carry `--tq4-attention`; OFF derivation of X has no MTP flags and keeps the mode; `--predictor on` with a delta
   refused without `--certified-by`, refused with a record failing (a) / (b) / (c), accepted with a matching record; fingerprints
   differ between X and V and equal today's for every existing pick (golden, green before the change).
3. `orchestrate` tuple: plan-only (`--plan-only`) for `m76-x` produces the ON / OFF argv pair, the cell list and the item list;
   refuses a stack root that is not an X commit or an off root that is not an XO commit; the existing picks' plans are
   byte-identical (golden).
4. Fork suite ×2 with identical skip lists, 0 failed; the fork's audits clean; production diff empty.
5. (Designer, GPU, after Accept) one `qualify --kv-arm --predictor off` per arm X / V / XO passes on the real model; the P369 smoke
   for `m76-x` (T = 1,024 and 65,536, injected positives) passes before stage 2's full run.

## Non-goals

Production code; the native16 tuple's behaviour; other entries; changing the 16-state rule or the fixture.

## Open questions

None.
