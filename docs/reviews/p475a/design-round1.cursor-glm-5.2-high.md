I have enough to report. Let me write the findings concisely.

## Findings

### 1. MAJOR — `guard_problems` still refuses the arm worktree (or the guarantee is weakened)

**Location:** Spec "Interface" / "Without `--kv-arm`: byte-for-byte today's behaviour"; `qualify.py` `guard_problems` (lines 496–504) and its call sites (911, 979, 1018).

**Problem:** The spec says `--kv-arm` "replaces the `classify` gate" and "then runs unchanged". But `guard_problems` is a separate gate that requires `fork_head == reviewed` (`--reviewed-head`). P475's arms are provisional commits on `p475-<pick>-<arm>` branches in a temporary worktree, so `fork_head` is the arm commit, not the reviewed head. The spec never addresses this gate. Either `--reviewed-head` is the real reviewed head → `guard_problems` refuses every arm (goal fails), or P475 passes the arm commit as `--reviewed-head` → the "fork at the reviewed head" guarantee is satisfied by an unreviewed provisional commit, weakening that guarantee.

**Failure scenario:** Run `qualify --predictor off --kv-arm --entry <pick> --reviewed-head 3ae8770e` from the arm worktree. `fork_head` = arm commit ≠ `3ae8770e` → `refused: fork at <arm>, not the reviewed head 3ae8770e`. No arm is measured.

**Change:** The spec must state how `--kv-arm` interacts with `guard_problems` — e.g. that `--reviewed-head` for a KV-arm run is the arm commit's *base* (the reviewed head the arm branches from), and `guard_problems` is adjusted to check the fork is at *a commit containing the reviewed head* (as `summary_artifact_problems` already does via `_is_ancestor`), not equality. Otherwise state that `--kv-arm` requires the arm worktree's HEAD to be the reviewed head itself (which contradicts P475's per-arm branch model).

---

### 2. MAJOR — the `mtp_off` check refuses every arm unless `off` from `classify_kv_arm` is wired in

**Location:** Spec "Interface" ("replaces the `classify` gate with `classify_kv_arm`"); `qualify.py` lines 917–919 (gate) vs. 983–984 (`mtp_off` check).

**Problem:** `classify` is used in two places: the gate (917–919) and `if arms[name] == "mtp_off" and name not in (off_entries or ())` (983–984). The spec only says it "replaces the `classify` gate". A literal implementation that swaps only lines 917–919 leaves line 983 calling `classify` (or reading an `off_entries` that is `None` for the arm registry). Since the arm registry differs from the 16 states in KV keys, `classify` returns `None`, so `name not in (None or ())` → `name not in ()` → True → `--predictor off: the committed registry serves <name> MTP-ON` appended → every arm refused.

**Failure scenario:** Implement exactly "replace the classify gate" (the None-check) with `classify_kv_arm`, leave the `mtp_off` check reading `off_entries` from a `classify` call. Run `--kv-arm --predictor off --entry <pick>`: `off_entries` is `None` → refused.

**Change:** State explicitly that the `off` returned by `classify_kv_arm` is the `off_entries` used by the existing `mtp_off` check (line 983), and that no separate `classify` call remains under `--kv-arm`.

---

### 3. MAJOR — `sdpa_forced` / `fused_v1` gate may refuse pick 1's quantized arms

**Location:** Spec "Interface" ("then runs unchanged"); `qualify.py` `request_problems` lines 408–411; fixture pick 1 `attention_policy: fused_v1` (line 528), M57 comment "force MLX's fused SDPA kernel for native-KV full attention".

**Problem:** Pick 1 ships `attention_policy: fused_v1`, kept by every arm (P475: "kept as deployed"; `attention_policy` is not in `KV_ARM_KEYS`). `request_problems` refuses when `fused != (sdpa_forced > 0)`. The M57 certification was for native16 KV; whether the server still forces SDPA under `fused_v1` when KV is quantized (AF8/TQ8/AF4/TQ4) is not established by the spec. If the server's `sdpa_forced` counter is 0 for quantized KV + `fused_v1`, `request_problems` refuses 4 of 5 arms for pick 1 — a gate the spec does not touch and does not name.

**Failure scenario:** Pick 1, AF8 arm. Server receives `--attention-policy fused_v1 --kv-bits 8 --kv-quant-scheme uniform`. If the fused SDPA kernel only engages for native KV, the worker records `sdpa_forced=0` while `expected["attention_policy"]=="fused_v1"` → `refused: sdpa_forced 0 (attention fused_v1)`.

**Change:** The spec must either (a) show evidence that `fused_v1` engages for quantized KV (so `sdpa_forced > 0` holds), or (b) add `attention_policy` to the arm-allowed delta so a quantized arm can drop/override it, or (c) explicitly scope `--kv-arm` to entries whose deployed `attention_policy` is `auto`. As written the goal ("every arm gets engagement proof") can fail at this gate.

---

### 4. MAJOR — `overlay_registry` refuses the arm registry under `--kv-arm --predictor on`

**Location:** Spec "Interface" (no restriction on `--predictor`); `qualify.py` lines 987–989; `registry_states.overlay_on` lines 262–264.

**Problem:** For `arm == "mtp_on"` the driver calls `orchestrate.overlay_registry(registry, name, fixture)`, which calls `classify(text, fixture)` and raises "the live registry is not one of the 16 accepted states" for the arm registry (it differs in KV keys). The spec restricts neither `--kv-arm` to `--predictor off` nor `overlay_registry` to use `classify_kv_arm`. P475 only uses `--predictor off`, but the spec's claim "without the flag nothing changes" leaves `--kv-arm --predictor on` as a path that always refuses.

**Failure scenario:** `qualify --kv-arm --predictor on --entry <pick>` (a path the spec permits) → `overlay_registry` → `classify` returns `None` → ValueError → arm refused.

**Change:** Either state `--kv-arm` requires `--predictor off` (and reject the combination), or specify that `overlay_registry` is replaced by a KV-arm-aware overlay when `--kv-arm` is set.

---

### 5. MINOR — the "non-comparable: KV arm" label mechanism is unspecified

**Location:** Spec "Interface" ("a reference-peak comparison … reported labelled `non-comparable: KV arm` (C199), never a refusal"); acceptance criterion 2 ("reference comparison labelled"); `qualify.py` `reference_comparison` (568–582) and `fingerprint_of` (1219–1251).

**Problem:** The existing `reference_comparison` returns `comparable=not differs` with `differs` listing every fingerprint field that differs; there is no "label" field and no "KV arm" string anywhere. The spec does not say whether the label is a new field, an override of `comparable`, an entry in `differs`, or a wrapper. A red-first test cannot pin the shape, so "labelled" is untestable as written.

**Failure scenario:** Implementer adds `comparable=False` unconditionally under `--kv-arm` (one reasonable reading) → the test "reference comparison labelled" passes trivially without ever producing the string "non-comparable: KV arm"; the operator never sees the KV-arm reason.

**Change:** Specify the exact report shape — e.g. `reference` gains `label: "non-comparable: KV arm"` (and `comparable: False`) under `--kv-arm`, with the test asserting the string.

---

### 6. MINOR — `kv_quant_mode` interacts with TQ arms but is excluded from `KV_ARM_KEYS`

**Location:** Spec "Interface" `KV_ARM_KEYS = ("kv_bits", "kv_quant_scheme")`; `kvmanifest.expected_manifest` `mode` field (lines 162, 173); `qualify.expected_kv` line 463.

**Problem:** For TQ8/TQ4 arms the per-layer manifest's `mode` is `tq_kv_quant_mode`, sourced from the registry's `kv_quant_mode` (unchanged by the arm). Both picks omit `kv_quant_mode` in the fixture, so expected and served agree at `DEFAULT_TQ_MODE="mse"`. But the spec gives no reason `kv_quant_mode` is excluded from `KV_ARM_KEYS` while `kv_quant_scheme` is included — a future TQ-mode arm is silently impossible. Not a P475 defect, but an under-justified scope line that the acceptance criteria ("each of N16/AF8/TQ8/AF4/TQ4") does not exercise.

**Change:** Add a non-goal line: "`kv_quant_mode` (TQ mode) is held to the fixture value" so the exclusion is explicit rather than incidental.

---

### Scope request (no severity) — `kv_group_size` and `quantized_kv_start` are pinned by the fixture, not by the arm

The arm can vary only `kv_bits`/`kv_quant_scheme`; `kv_group_size` (always CLI default 64, not a registry key) and `quantized_kv_start` (fixture 0, guarded to 0) are fixed. P475's five arms don't vary these, so this is in scope for P475. Raising it only because the spec's "EXACTLY the KV-format keys" phrasing implies the full KV-format surface when in fact two interacting KV keys (`kv_group_size`, `quantized_kv_start`) are out of reach. If a later campaign needs them, this interface won't serve it without extension. No change requested for P475; flagging the boundary.
