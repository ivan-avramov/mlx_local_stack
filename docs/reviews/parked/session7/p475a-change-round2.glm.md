I have enough to write findings.

---

## Findings

### 1. MAJOR — Tests: the served argv is never proven to follow the arm through the real `full_command`; round-1 finding #2 is only partially resolved.

**Location:** `mlx_vlm/tests/test_p475a_qualify_kv_arm.py:789-810` (`test_the_arm_entry_carries_exactly_the_arms_kv_flags_and_mlx_serves_argv_passes`), `_drive_cell` at `:989` (`monkeypatch.setattr(qualify, "full_command", lambda stack, path, name: (_serve_argv(block, ...), "m"))`), `_drive_arm` at `:568` (`monkeypatch.setattr(t415, "_cmd", lambda e: off_cmd)`).

**Problem:** Every `--kv-arm` driver test replaces `qualify.full_command` (which runs mlx-serve's `process_manager._build_command` via subprocess) with a hand-spelled `_serve_argv` helper built from the source. The implementer's report concedes this is "source-read, not machine-verified." The spec's AC2 explicitly names "the served argv ... follow the arm" as a check, and the question calls it out. The no-flag suite exercises the real `full_command` only for the committed registries — Fable `kv_bits: 0` and Uniform `kv_bits: 4, scheme: turboquant`. The kv-arm cells that introduce a KV combination the committed registries never hold — AF8/TQ8 (`kv_bits: 8`, both picks), AF4 (`kv_bits: 4, scheme: uniform`, both picks), and TQ8 for Fable — never reach the real `_build_command` in any test. So 6 of the 10 arms' served argv is asserted only against a hand-built command, not the gate the orchestrator hits. <!-- allow-shorthand: verbatim reviewer output -->

**Failure scenario:** `qualify --kv-arm --predictor off --entry <pick>` on a real AF8 worktree. mlx-serve's `_build_command` emits `--kv-bits 8 --kv-quant-scheme uniform` but with a spelling `_serve_argv` got wrong (e.g., it omits `--kv-quant-scheme` when the scheme equals the CLI default, or spells `--kv-bits` for a value the real builder treats as absent). `command_problems(expected, cmd, ...)` refuses the arm with "argv lacks/--kv-...". The 10-cell tests passed because `_serve_argv` and `expected_config` agree by construction; the field run never starts a leg.

**Proposed change:** Add one test per KV combination that does NOT mock `full_command` — let it run the real `process_manager._build_command` on the arm registry (or, if a subprocess is too heavy, call the real `full_command` and assert `command_problems(expected, cmd, venv_bin) == []` for each of the 10 cells). At minimum, drop the `full_command` mock in `_drive_cell` for one AF8 and one TQ8 cell.

---

### 2. MAJOR — Candidate: the `native_attention = None` change alters the no-flag diagnosis for a fused_v1 entry with a missing manifest, deviating from "without the flag nothing changes / reduces to today's."

**Location:** `dev/p369_phase2/qualify.py:382` (`native_attention = None`), `:405-409` (the `if native_attention is not None or ... fused_v1` guard).

**Problem:** The change is unconditional — it applies with and without `--kv-arm`. The spec's interface says the attention rule is "the same rule applied without `--kv-arm`, where it reduces to today's," and AC0 says "today's no-flag behaviour unchanged." Today's behaviour for a fused_v1 entry whose record lacks a manifest/template was: `native_attention` defaulted to `True`, so `fused = True`, and `sdpa_forced == 0` was reported as a second problem alongside "no leaf manifest." The candidate now skips the sdpa check entirely when the manifest is absent, so a no-flag fused_v1 run with a missing manifest reports only the manifest problem. The pass/fail outcome is preserved (the manifest problem is fatal), but the recorded diagnosis changes, and no test pins the no-flag missing-manifest case — `test_a_missing_manifest_or_template_reports_only_that_problem` exercises `request_problems` directly with `FABLE_ENTRY` but does not route it through the no-flag driver, and `test_p415_qualify.py:337` (`(dict(sdpa_forced=0), "sdpa_forced")`) uses `_record()` which always supplies a manifest.

**Failure scenario:** A future regression where a fused_v1 worker loses the manifest on a no-flag run. The operator reads a report with only "no leaf manifest" and chases the recording path, never learning that sdpa was also unfused; the old report would have named both. The spec's "nothing changes" pin is silently broken for this corner.

**Proposed change:** Either scope the skip to `--kv-arm` (compute `native_attention` from the expected manifest even when the observed one is absent, so the no-flag path keeps today's double-problem), or add a no-flag driver test that pins the new single-problem diagnosis and record the deviation from "reduces to today's" in the spec.

---

### 3. MINOR — Candidate: the `int()` removal in `expected_config` is dead for the path the implementer cites.

**Location:** `dev/p369_phase2/qualify.py:195` (`kv_bits=values["kv_bits"] or None`), `registry_states.py:289-292` (`_kv_arm_valid` requires `type(bits) is int`).

**Problem:** The implementer's report justifies the change with "kv_bits 4.5 stays 4.5 and the flag reads `--kv-bits 4.5`." But `_kv_arm_valid` rejects any non-int `kv_bits` before `expected_config` is reached under `--kv-arm`, and the committed registries (the only no-flag inputs) hold int `kv_bits`. So `expected_config` never sees a fractional width; the `int()` removal changes no reachable behaviour. The rationale describes an unreachable path, and a reader may trust that fractional widths are served.

**Failure scenario:** A maintainer reads the comment, believes fractional `kv_bits` is a supported arm, and later loosens `_kv_arm_valid` to allow `4.5`, expecting `expected_config` to pass it through — but `expected_kv` does `float(expected["kv_bits"])` and the manifest codec may not model a 4.5-bit leaf, producing a confusing manifest mismatch rather than a clean refusal.

**Proposed change:** Drop the `int()` removal (restore `int(values["kv_bits"]) or None`) since the classifier already gates widths to the int set, or keep it and correct the comment to state the change is a no-op given `_kv_arm_valid`.

---

### Scope requests (requirements I would add beyond the request; no severity)

- **SR1:** A single `--kv-arm` driver test per attention class that does not mock `full_command` or `run_job` beyond the worker boundary, so the real mlx-serve argv and the real `request_problems` are exercised on an arm registry. This is the only test that would catch a real `_build_command`/`expected_config` drift for the quantized arms. <!-- allow-shorthand: verbatim reviewer output -->

- **SR2:** The candidate tightens `classify_kv_arm`'s refusal boundary beyond the spec. The spec says values "valid for `kvmanifest.expected_manifest`"; `_kv_arm_valid` instead requires the exact P475 arm set (int `0/4/8`, scheme `uniform`/`turboquant`). This is sound for the ten P475 arms but is stricter than the spec — a future arm at a width `expected_manifest` would accept (e.g., `kv_bits: 6` if the codec modelled it) is refused without the spec being amended. If the operator wants the tool locked to the P475 arm set, this should be recorded in the spec; if not, `_kv_arm_valid` should delegate to `kvmanifest.expected_manifest` for validity.

- **SR3:** A `classify_kv_arm` test on a full 16-state base where a *different* entry is MTP-ON (others-OFF + pick-ON for a different pick's arm), to close the "any accepted state" half of the refusal boundary. The existing `test_an_arm_on_top_of_an_mtp_off_state_is_accepted` covers pick-OFF + others-ON; the symmetric corner is untested.

---

Nothing else of substance: the `mtp_off` check correctly reads `off_entries` from `classify_kv_arm` (`qualify.py:1010`); `report["kv_arm"]` is recorded before the per-entry loop and survives entry failure (`:936-937`); the reference label is added only on a COMPLETED entry and never refuses (`:585-589`, guarded at `:1076`); the `--kv-arm` validation refuses `predictor != "off"` and `len(entry) != 1` and non-`KV_ARM_ENTRIES` names (`:836-844`); the refusal boundary for a second entry, a non-KV key, `quantized_kv_start != 0`, an MTP-key+KV change outside the 16 states, an unknown entry, and malformed/unparseable documents is correctly `None`; the 10-cell driver test drives the real `classify_kv_arm` through a delegating spy with `classify` forbidden, proving the classifier-to-driver contract; and the attention rule is proven through the driver for all 10 cells with a wrong `sdpa_forced`.
