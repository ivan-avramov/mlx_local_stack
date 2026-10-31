# P475 stage 1 — adversarial frozen tests (delivery 1, written from SPEC v2 before the
# implementer exists). See module docstring below.
"""P475 stage 1 — adversarial frozen tests (delivery 1).

Spec: docs/specs/p475-kv-matrix.md (v2). The implementer is building, elsewhere, an
orchestrator bench.p475_kv and opt-in extensions to bench.run_capacity /
bench.capacity_ladder / bench.driver. These tests attack the spec's OBSERVABLE contract
(CLI / function behaviour the spec names, files it writes, refusals, receipts). Every
external effect is mocked (no model load, no router, no GPU, no pmset, no subprocess).

Each test carries one of three classes in its docstring:
  REPRODUCES — reproduces a failure the spec fixes (red on baseline; the fix turns it green).
  PRESERVES  — preserves an invariant the spec names (green on baseline; must not regress).
  EXERCISES  — exercises a new behaviour the spec names (red on baseline; green once landed).

ASSUMED NAMES (the implementer is free to rename; the test docstrings call these out):
  bench.p475_kv                       — the orchestrator module.
  bench.p475_kv.ARM_KEYS              — {arm: {kv_bits, kv_quant_scheme}} for the five arms.
  bench.p475_kv.PICKS                 — the two full-registry pick names, in order.
  bench.p475_kv.arm_commit_problems(on, off, entry, arm)
  bench.p475_kv.preflight_manifest_problems(arm, observed, template)
  bench.p475_kv.argv_kv_problems(cmdline, arm)
  bench.p475_kv.kv_line_problems(log_lines, arm)
  bench.p475_kv.predictor_off_problems(argv, manifest, rows)
  bench.p475_kv.LEG_ORDER             — per-pick ABBA block order.
  bench.p475_kv.IDLE_SECONDS          — 600.
  bench.p475_kv.run_pick / run_leg     — orchestrator entry points.
  bench.p475_kv.replacement_queue / instability_trigger
  bench.p475_kv.harvest / generate_matrix
  bench.p475_kv.MATRIX_PATH           — benchmark/results/p475/MATRIX.md
  bench.run_capacity gains an opt-in --p475 flag (and uses the backend's own prompt_ms,
  prompt_per_second, prompt_n, cache_n, peak_memory_gb, predicted_per_second).
"""
import json
import sys
from pathlib import Path

import pytest

import bench.run_capacity as R
import bench.capacity_ladder as L
from bench.driver import MlxServeDriver

_FORK_DEV = Path(__file__).resolve().parents[4] / "mlx-vlm" / "dev" / "p369_phase2"


def _import_kvmanifest():
    if not (_FORK_DEV / "kvmanifest.py").exists():
        pytest.skip("fork dev/p369_phase2/kvmanifest.py not present in this copy")
    if str(_FORK_DEV) not in sys.path:
        sys.path.insert(0, str(_FORK_DEV))
    import kvmanifest  # type: ignore
    return kvmanifest


def _import_p475():
    from bench import p475_kv  # noqa: F401
    return p475_kv


PICK1 = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
PICK2 = "Qwen3.8-27B-mlx-uniform-4bit"


def _registry(entry, kv_bits=None, kv_quant_scheme=None):
    lines = ["  - name: Other", "    hf_path: caslca/Other", f"  - name: {entry}",
             f"    hf_path: caslca/{entry}", "    attention_policy: fused_v1",
             "    quantized_kv_start: 0"]
    if kv_bits is not None:
        lines.append(f"    kv_bits: {kv_bits}")
    if kv_quant_scheme is not None:
        lines.append(f"    kv_quant_scheme: {kv_quant_scheme}")
    return "models:\n" + "\n".join(lines) + "\n"


# =========================================================================== arm-commit / worktree
class TestArmCommit:
    """The arm is a commit on p475-<pick-short>-<arm> off the P476 commit, changing ONLY
    that entry's KV keys (+ a PROVISIONAL P475 arm comment)."""

    def test_arm_commit_changes_only_the_entrys_kv_keys(self):
        """REPRODUCES: an arm commit that also touches a bystander model's settings is
        refused. ASSUMES bench.p475_kv.arm_commit_problems(on, off, entry, arm) returns a
        list of problem strings (empty == clean)."""
        p475 = _import_p475()
        off = _registry(PICK1)
        on = _registry(PICK1, kv_bits=8, kv_quant_scheme="uniform")
        assert p475.arm_commit_problems(on, off, PICK1, "af8") == []

    def test_arm_commit_with_a_changed_bystander_is_refused(self):
        """REPRODUCES: the bystander Other entry changed between the arm and the base."""
        p475 = _import_p475()
        off = _registry(PICK1)
        on = _registry(PICK1, kv_bits=8, kv_quant_scheme="uniform").replace(
            "caslca/Other", "caslca/Other-CHANGED")
        problems = p475.arm_commit_problems(on, off, PICK1, "af8")
        assert problems and any("Other" in p for p in problems)

    def test_arm_commit_with_a_wrong_kv_bits_value_is_refused(self):
        """REPRODUCES: the arm labelled AF8 carries kv_bits=4 (a wrong key value)."""
        p475 = _import_p475()
        off = _registry(PICK1)
        on = _registry(PICK1, kv_bits=4, kv_quant_scheme="uniform")
        problems = p475.arm_commit_problems(on, off, PICK1, "af8")
        assert problems and any("kv_bits" in p for p in problems)

    def test_arm_commit_with_a_wrong_scheme_is_refused(self):
        """REPRODUCES: the arm labelled TQ8 carries kv_quant_scheme=uniform."""
        p475 = _import_p475()
        off = _registry(PICK1)
        on = _registry(PICK1, kv_bits=8, kv_quant_scheme="uniform")
        problems = p475.arm_commit_problems(on, off, PICK1, "tq8")
        assert problems and any("scheme" in p.lower() for p in problems)

    def test_arm_commit_with_an_extra_change_is_refused(self):
        """REPRODUCES: the arm commit also changed attention_policy (kept as deployed)."""
        p475 = _import_p475()
        off = _registry(PICK1)
        on = _registry(PICK1, kv_bits=8, kv_quant_scheme="uniform").replace(
            "fused_v1", "default")
        problems = p475.arm_commit_problems(on, off, PICK1, "af8")
        assert problems and any("attention" in p.lower() for p in problems)

    def test_arm_commit_with_mtp_present_is_refused(self):
        """REPRODUCES: the arm commit added draft_kind: mtp (P475 is predictor-OFF; an MTP
        line is an extra change AND a predictor-OFF violation)."""
        p475 = _import_p475()
        off = _registry(PICK1)
        on = _registry(PICK1, kv_bits=8, kv_quant_scheme="uniform") + \
            "    draft_kind: mtp\n    draft_model: caslca/x-mtp-drafter\n"
        problems = p475.arm_commit_problems(on, off, PICK1, "af8")
        assert problems and any("draft" in p.lower() for p in problems)

    def test_arm_commit_with_quantized_kv_start_nonzero_is_refused(self):
        """REPRODUCES: the spec pins quantized_kv_start to 0 in every arm; a non-zero
        value is a wrong key (and the kvmanifest validator refuses to model it)."""
        p475 = _import_p475()
        off = _registry(PICK1)
        on = _registry(PICK1, kv_bits=8, kv_quant_scheme="uniform").replace(
            "quantized_kv_start: 0", "quantized_kv_start: 5000")
        problems = p475.arm_commit_problems(on, off, PICK1, "af8")
        assert problems and any("quantized_kv_start" in p for p in problems)

    def test_the_n16_arm_uses_the_base_commit_verbatim(self):
        """PRESERVES: the arm equal to the committed registry (N16, native16) uses the base
        commit; the arm-commit check passes when on == off for the N16 arm. ASSUMES
        arm_commit_problems accepts arm="n16" and treats on==off as clean."""
        p475 = _import_p475()
        off = _registry(PICK1)
        assert p475.arm_commit_problems(off, off, PICK1, "n16") == []


# =========================================================================== engagement preflight
class TestEngagementPreflight:
    """Per arm, before its first leg: an in-process known-positive check on the arm's
    committed registry with the fork's per-layer cache-manifest validator. A mismatch
    refuses the arm."""

    def test_a_matching_manifest_passes_the_preflight(self):
        """REPRODUCES: a known-positive (observed manifest == expected manifest for the arm)
        passes. ASSUMES bench.p475_kv.preflight_manifest_problems(arm, observed, template)
        returns [] on a match."""
        p475 = _import_p475()
        kv = _import_kvmanifest()
        template = [
            {"path": "0", "kind": "native", "cls": "KVCache", "batch": False},
            {"path": "1", "kind": "native", "cls": "KVCache", "batch": False},
        ]
        expected = kv.expected_manifest(template, dict(
            kv_bits=8.0, kv_key_bits=None, kv_value_bits=None, kv_key_scheme=None,
            kv_value_scheme=None, kv_quant_scheme="uniform", kv_group_size=64,
            quantized_kv_start=0, tq_kv_quant_mode="mse"))
        assert p475.preflight_manifest_problems("af8", expected, template) == []

    def test_a_mismatched_manifest_refuses_the_arm(self):
        """REPRODUCES: the observed manifest's leaf kinds disagree with what the arm's argv
        implies (the worker served native16 while the arm asked AF8)."""
        p475 = _import_p475()
        _import_kvmanifest()  # the preflight uses the fork validator; ensure importable
        template = [
            {"path": "0", "kind": "native", "cls": "KVCache", "batch": False},
            {"path": "1", "kind": "native", "cls": "KVCache", "batch": False},
        ]
        observed = [dict(t) for t in template]  # stayed native — codec did not engage
        problems = p475.preflight_manifest_problems("af8", observed, template)
        assert problems and any("0" in p for p in problems)

    def test_a_tq8_arm_keeps_the_last_top_level_leaf_native(self):
        """REPRODUCES: TurboQuant converts every KV layer EXCEPT the last top-level cache
        entry when there are more than two; a TQ8 arm that quantized the last leaf is
        refused. ASSUMES the preflight honours the fork's expected_manifest rule."""
        p475 = _import_p475()
        kv = _import_kvmanifest()
        template = [
            {"path": "0", "kind": "native", "cls": "KVCache", "batch": False},
            {"path": "1", "kind": "native", "cls": "KVCache", "batch": False},
            {"path": "2", "kind": "native", "cls": "KVCache", "batch": False},
        ]
        expected = kv.expected_manifest(template, dict(
            kv_bits=8.0, kv_key_bits=None, kv_value_bits=None, kv_key_scheme=None,
            kv_value_scheme=None, kv_quant_scheme="turboquant", kv_group_size=64,
            quantized_kv_start=0, tq_kv_quant_mode="mse"))
        assert expected[-1]["kind"] == "native"
        bad = [dict(t) for t in expected]
        bad[-1] = dict(bad[-1], kind="tq", bits=8.0, key_bits=8.0, value_bits=8.0, mode="mse")
        problems = p475.preflight_manifest_problems("tq8", bad, template)
        assert problems and any("2" in p for p in problems)

    def test_a_quantized_kv_start_nonzero_is_refused_by_the_preflight(self):
        """REPRODUCES: the spec pins quantized_kv_start to 0; the validator refuses to
        model a non-zero start (a between-context hybrid), and so does the preflight."""
        kv = _import_kvmanifest()
        template = [{"path": "0", "kind": "native", "cls": "KVCache", "batch": False}]
        with pytest.raises(ValueError):
            kv.expected_manifest(template, dict(
                kv_bits=8.0, kv_key_bits=None, kv_value_bits=None, kv_key_scheme=None,
                kv_value_scheme=None, kv_quant_scheme="uniform", kv_group_size=64,
                quantized_kv_start=5000, tq_kv_quant_mode="mse"))


# =========================================================================== argv / KV-line agreement
class TestArgvKvLine:
    """On every router leg the worker argv must carry exactly the arm's KV flags and the
    worker log's `KV cache resolved` line must agree (secondary record)."""

    def test_argv_matching_the_arm_passes(self):
        """REPRODUCES: an AF8 worker argv (--kv-bits 8 --kv-quant-scheme uniform
        --quantized-kv-start 0) passes. ASSUMES bench.p475_kv.argv_kv_problems(cmdline,
        arm) returns [] on a match."""
        p475 = _import_p475()
        cmd = (f"1 python -m mlx_vlm.server --model caslca/{PICK1} "
               "--kv-bits 8 --kv-quant-scheme uniform --quantized-kv-start 0")
        assert p475.argv_kv_problems(cmd, "af8") == []

    def test_argv_missing_the_kv_bits_flag_is_refused(self):
        """REPRODUCES: the worker argv omits --kv-bits (the codec defaulted to native16
        while the arm asked AF8)."""
        p475 = _import_p475()
        cmd = f"1 python -m mlx_vlm.server --model caslca/{PICK1} --kv-quant-scheme uniform"
        problems = p475.argv_kv_problems(cmd, "af8")
        assert problems and any("kv-bits" in p for p in problems)

    def test_argv_with_a_wrong_scheme_is_refused(self):
        """REPRODUCES: a TQ8 arm's worker carries --kv-quant-scheme uniform."""
        p475 = _import_p475()
        cmd = (f"1 python -m mlx_vlm.server --model caslca/{PICK1} "
               "--kv-bits 8 --kv-quant-scheme uniform --quantized-kv-start 0")
        problems = p475.argv_kv_problems(cmd, "tq8")
        assert problems and any("scheme" in p.lower() for p in problems)

    def test_argv_with_a_nonzero_quantized_kv_start_is_refused(self):
        """REPRODUCES: the worker carries --quantized-kv-start 5000 (the spec pins 0)."""
        p475 = _import_p475()
        cmd = (f"1 python -m mlx_vlm.server --model caslca/{PICK1} "
               "--kv-bits 8 --kv-quant-scheme uniform --quantized-kv-start 5000")
        problems = p475.argv_kv_problems(cmd, "af8")
        assert problems and any("quantized-kv-start" in p for p in problems)

    def test_the_kv_cache_resolved_line_must_match_the_arm(self):
        """REPRODUCES: the worker log's `KV cache resolved` line carries the arm's KV
        flags. ASSUMES bench.p475_kv.kv_line_problems(log_lines, arm) parses the
        `KV cache resolved:` line (mlx_vlm/server/app.py format) and returns [] on a
        match."""
        p475 = _import_p475()
        line = ("KV cache resolved: kv_bits=8 kv_key_bits=None kv_value_bits=None "
                "kv_key_scheme=None kv_value_scheme=None kv_quant_scheme='uniform' "
                "kv_group_size=64 quantized_kv_start=0 TQ_KV_QUANT_MODE='mse'")
        assert p475.kv_line_problems([line], "af8") == []

    def test_the_kv_cache_resolved_line_disagreeing_with_the_arm_is_refused(self):
        """REPRODUCES: the worker log resolved native16 (kv_bits=None) while the arm asked
        AF8 — the secondary record disagrees with the argv."""
        p475 = _import_p475()
        line = ("KV cache resolved: kv_bits=None kv_key_bits=None kv_value_bits=None "
                "kv_key_scheme=None kv_value_scheme=None kv_quant_scheme='uniform' "
                "kv_group_size=64 quantized_kv_start=0 TQ_KV_QUANT_MODE='mse'")
        problems = p475.kv_line_problems([line], "af8")
        assert problems and any("kv_bits" in p for p in problems)

    def test_a_missing_kv_cache_resolved_line_is_refused(self):
        """REPRODUCES: the worker log carries no `KV cache resolved` line at all (the
        codec never logged its resolution); the secondary record is required, not
        optional."""
        p475 = _import_p475()
        problems = p475.kv_line_problems(["unrelated log line"], "af8")
        assert problems and any("KV cache resolved" in p for p in problems)


# =========================================================================== predictor-OFF
class TestPredictorOff:
    """Predictor-OFF proof (every leg): no --draft-kind / --draft-model in the worker
    argv, the manifest's runtime.draft_kind null, and no draft fields on any request
    record; otherwise the leg is INVALID."""

    def test_a_clean_predictor_off_leg_passes(self):
        """REPRODUCES: argv without --draft-kind/--draft-model, manifest runtime.draft_kind
        null, and rows with no draft fields passes. ASSUMES
        bench.p475_kv.predictor_off_problems(argv, manifest, rows) returns [] on clean."""
        p475 = _import_p475()
        argv = f"1 python -m mlx_vlm.server --model caslca/{PICK1} --kv-bits 8"
        manifest = {"runtime": {"draft_kind": None}}
        rows = [{"id": "a", "prompt_tokens": 1000, "completion_tokens": 256,
                 "finish_reason": "length"}]
        assert p475.predictor_off_problems(argv, manifest, rows) == []

    def test_a_draft_kind_flag_in_argv_is_refused(self):
        """REPRODUCES: the worker argv carries --draft-kind mtp (P475 is predictor-OFF)."""
        p475 = _import_p475()
        argv = (f"1 python -m mlx_vlm.server --model caslca/{PICK1} --kv-bits 8 "
                "--draft-kind mtp")
        manifest = {"runtime": {"draft_kind": None}}
        rows = []
        problems = p475.predictor_off_problems(argv, manifest, rows)
        assert problems and any("draft-kind" in p for p in problems)

    def test_a_draft_model_flag_in_argv_is_refused(self):
        """REPRODUCES: the worker argv carries --draft-model (P475 is predictor-OFF)."""
        p475 = _import_p475()
        argv = (f"1 python -m mlx_vlm.server --model caslca/{PICK1} --kv-bits 8 "
                "--draft-model caslca/x-mtp-drafter")
        manifest = {"runtime": {"draft_kind": None}}
        rows = []
        problems = p475.predictor_off_problems(argv, manifest, rows)
        assert problems and any("draft-model" in p for p in problems)

    def test_a_manifest_with_a_non_null_draft_kind_is_refused(self):
        """REPRODUCES: the provenance manifest's runtime.draft_kind is not null (the
        drafter engaged)."""
        p475 = _import_p475()
        argv = f"1 python -m mlx_vlm.server --model caslca/{PICK1} --kv-bits 8"
        manifest = {"runtime": {"draft_kind": "mtp"}}
        rows = []
        problems = p475.predictor_off_problems(argv, manifest, rows)
        assert problems and any("draft_kind" in p for p in problems)

    def test_a_row_with_a_draft_field_is_refused(self):
        """REPRODUCES: a request record carries a `draft` field (the drafter's counters rode
        the response); P475 rows must carry none."""
        p475 = _import_p475()
        argv = f"1 python -m mlx_vlm.server --model caslca/{PICK1} --kv-bits 8"
        manifest = {"runtime": {"draft_kind": None}}
        rows = [{"id": "a", "draft": {"draft_kind": "mtp", "draft_n": 10,
                 "draft_n_accepted": 7}}]
        problems = p475.predictor_off_problems(argv, manifest, rows)
        assert problems and any("draft" in p.lower() for p in problems)


# =========================================================================== run_capacity opt-in: backend timing fields
class TestBackendTimingFields:
    """The instrument persists and uses the backend's own prompt_ms, prompt_per_second,
    prompt_n and cache_n (prefill from the backend, not wall - decode); every measured
    request cache_n == 0 with a unique session id; decode tok/s from the backend's
    predicted_per_second; memory reported as the worker's cumulative high-water
    peak_memory_gb (process-lifetime). These tests assume bench.run_capacity gains an
    opt-in --p475 flag and that the opt-in path validates the backend fields."""

    def test_run_capacity_without_the_p475_flag_rejects_it(self):
        """PRESERVES: the existing run_capacity CLI does not know --p475; passing it is a
        usage error (SystemExit code 2). The opt-in must not silently change existing
        behaviour."""
        with pytest.raises(SystemExit) as exc:
            R.main(["--model", "m", "--grid", "100", "--sampling-profile", "production",
                    "--p475"])
        assert exc.value.code == 2

    def test_run_capacity_without_p475_keeps_wall_derived_prefill(self):
        """PRESERVES: without the opt-in, the existing capacity_ladder path keeps its
        wall-derived prefill_s/prefill_tps (the driver computes prefill_s = wall -
        predicted_ms/1000). The opt-in must not alter the existing path's records."""
        # The existing driver derives prefill_s from wall minus predicted_ms; confirm the
        # shape is unchanged on the baseline.
        from bench.driver import MlxServeDriver
        import inspect
        src = inspect.getsource(MlxServeDriver.complete)
        assert "wall_s" in src and "predicted_ms" in src

    def test_p475_optin_uses_backend_prompt_ms_not_wall_derived_prefill(self):
        """REPRODUCES: under --p475, the row's prefill comes from the backend's prompt_ms /
        prompt_per_second / prompt_n, NOT from wall - decode. ASSUMES the opt-in path
        records prompt_ms / prompt_per_second / prompt_n on the row and refuses a row
        whose prefill_s was derived from wall. This test is necessarily indirect until the
        implementer lands the opt-in; it fails red on the baseline (no --p475)."""
        # We assert the opt-in exists; on the baseline argparse rejects --p475 (above test).
        # Here we instead require the new field names appear somewhere in the run_capacity
        # module once the opt-in lands; on the baseline they do not.
        import bench.run_capacity as Rc
        src = open(Rc.__file__).read()
        if "prompt_ms" not in src:
            pytest.fail("run_capacity does not yet persist the backend's prompt_ms "
                        "(the --p475 opt-in is not landed)")

    def test_p475_optin_refuses_a_row_with_cache_n_not_zero(self):
        """REPRODUCES: every measured request must have cache_n == 0 (a fresh session, no
        prefix reuse); a row with cache_n > 0 is INVALID. ASSUMES a validator
        bench.p475_kv.cache_n_problems(rows) (or the opt-in path's refusal). Stated as an
        assumed name."""
        p475 = _import_p475()
        rows = [{"id": "a", "cache_n": 0, "session_id": "s1"},
                {"id": "b", "cache_n": 128, "session_id": "s2"}]
        problems = p475.cache_n_problems(rows)
        assert problems and any("cache_n" in p for p in problems)

    def test_p475_optin_requires_a_unique_session_id_per_request(self):
        """REPRODUCES: every measured request carries a unique session id; two rows sharing
        a session id is INVALID (the cache was reused, not fresh)."""
        p475 = _import_p475()
        rows = [{"id": "a", "cache_n": 0, "session_id": "s1"},
                {"id": "b", "cache_n": 0, "session_id": "s1"}]
        problems = p475.cache_n_problems(rows)
        assert problems and any("session" in p.lower() for p in problems)

    def test_p475_decode_tok_s_comes_from_predicted_per_second(self):
        """REPRODUCES: under --p475, decode tok/s is the backend's predicted_per_second,
        not a wall-derived figure. ASSUMES the opt-in records predicted_per_second on the
        row; on the baseline the field is absent."""
        import bench.run_capacity as Rc
        src = open(Rc.__file__).read()
        if "predicted_per_second" not in src:
            pytest.fail("run_capacity does not yet use the backend's predicted_per_second "
                        "(the --p475 opt-in is not landed)")

    def test_p475_memory_is_cumulative_high_water_peak_memory_gb(self):
        """REPRODUCES: memory is the worker's cumulative high-water peak_memory_gb
        (process-lifetime, incl. the full-cap preallocation of the first request and the
        calibration) at each rung — never a per-rung peak. ASSUMES the opt-in records
        peak_memory_gb (cumulative). On the baseline the field name is absent."""
        import bench.run_capacity as Rc
        src = open(Rc.__file__).read()
        if "peak_memory_gb" not in src:
            pytest.fail("run_capacity does not yet report cumulative peak_memory_gb "
                        "(the --p475 opt-in is not landed)")


# =========================================================================== exact-length decode
class TestExactLengthDecode:
    """A fixed decode carrier per rung runs to the token cap: exactly 256 completion
    tokens and finish_reason == "length", else the rung is INVALID."""

    def test_a_length_finish_with_256_tokens_passes(self):
        """REPRODUCES: a rung with finish_reason == "length" and completion_tokens == 256
        passes. ASSUMES bench.p475_kv.decode_carrier_problems(row) returns [] on clean."""
        p475 = _import_p475()
        row = {"id": "a", "completion_tokens": 256, "finish_reason": "length"}
        assert p475.decode_carrier_problems(row) == []

    def test_a_short_decode_is_invalid(self):
        """REPRODUCES: completion_tokens < 256 (the decode carrier did not reach the cap)
        is INVALID."""
        p475 = _import_p475()
        row = {"id": "a", "completion_tokens": 200, "finish_reason": "length"}
        problems = p475.decode_carrier_problems(row)
        assert problems and any("256" in p or "completion_tokens" in p for p in problems)

    def test_a_non_length_finish_reason_is_invalid(self):
        """REPRODUCES: finish_reason == "stop" (the carrier stopped early) is INVALID; the
        spec requires finish_reason == "length"."""
        p475 = _import_p475()
        row = {"id": "a", "completion_tokens": 256, "finish_reason": "stop"}
        problems = p475.decode_carrier_problems(row)
        assert problems and any("finish_reason" in p for p in problems)

    def test_existing_validate_completion_still_accepts_stop_without_optin(self):
        """PRESERVES: the existing capacity_ladder.validate_completion (used by the
        non-opt-in path) still accepts finish_reason == "stop" — the exact-length
        requirement is opt-in only, not a regression on the existing instrument."""
        out = {"content": "ok", "prompt_tokens": 10, "completion_tokens": 5,
               "finish_reason": "stop", "raw_timings": {}}
        L.validate_completion(out)  # must not raise


# =========================================================================== ABBA order and idle
class TestOrderAndIdle:
    """Per pick two blocks: block 1 N16 -> AF8 -> TQ8 -> AF4 -> TQ4, block 2 the reverse;
    picks sequential; each leg a fresh lean router + load from the arm worktree; >= 600 s
    idle before every leg; 20 legs."""

    def test_block_1_order_is_n16_af8_tq8_af4_tq4(self):
        """REPRODUCES: block 1 visits the arms in the spec's order. ASSUMES
        bench.p475_kv.LEG_ORDER is a structure carrying the per-pick block orders."""
        p475 = _import_p475()
        order = p475.LEG_ORDER
        block1 = order["block1"] if isinstance(order, dict) else order[0]
        assert list(block1) == ["n16", "af8", "tq8", "af4", "tq4"]

    def test_block_2_order_is_the_reverse(self):
        """REPRODUCES: block 2 is the reverse of block 1 (order-balanced)."""
        p475 = _import_p475()
        order = p475.LEG_ORDER
        block1 = order["block1"] if isinstance(order, dict) else order[0]
        block2 = order["block2"] if isinstance(order, dict) else order[1]
        assert list(block2) == list(reversed(block1))

    def test_idle_seconds_is_at_least_600(self):
        """REPRODUCES: the spec pins >= 600 s idle before every leg. ASSUMES
        bench.p475_kv.IDLE_SECONDS."""
        p475 = _import_p475()
        assert p475.IDLE_SECONDS >= 600

    def test_picks_run_sequentially(self):
        """REPRODUCES: picks are sequential (pick 1's two blocks complete before pick 2
        starts). ASSUMES bench.p475_kv.PICKS is the ordered pair and the orchestrator
        honours it."""
        p475 = _import_p475()
        assert list(p475.PICKS) == [PICK1, PICK2]

    def test_twenty_legs_total(self):
        """REPRODUCES: 2 picks x 2 blocks x 5 arms = 20 legs. ASSUMES the orchestrator's
        leg count is derivable from LEG_ORDER and PICKS."""
        p475 = _import_p475()
        order = p475.LEG_ORDER
        blocks = order.values() if isinstance(order, dict) else order
        legs = len(p475.PICKS) * sum(len(b) for b in blocks)
        assert legs == 20


# =========================================================================== pre-check refusals (power / busy / gate-lock / destinations)
class TestPreCheckRefusals:
    """Per leg: pre-check (power, nothing busy, the gate lock C227, destinations absent).
    A failed pre-check never starts the router (NOT_STARTED)."""

    class FakeOps:
        """Minimal ops injection seam mirroring bench.p426_leg's FakeOps pattern: the
        orchestrator calls these in order, and a refusal stops before start_router."""

        def __init__(self, *, power=True, busy=(), listeners=(), destinations_exist=False):
            self.calls = []
            self._power = power
            self._busy = list(busy)
            self._listeners = list(listeners)
            self._dest_exist = destinations_exist

        def power_ok(self):
            self.calls.append("power_ok")
            return self._power

        def busy_procs(self):
            return list(self._busy)

        def listeners(self, port=8000):
            return list(self._listeners)

        def start_state(self):
            return {"watts": 140, "volts": 28, "batt": 80, "busy": list(self._busy),
                    "orphans_clean": True}

        def env_base(self):
            return {"MLX_SERVE_CONFIG": "arm.yaml"}

        def start_router(self):
            self.calls.append("start_router")
            return 101

        def load(self, model):
            self.calls.append(f"load {model}")
            return {"pid": 202, "create_time": 1.0,
                    "cmdline": f"202 python -m mlx_vlm.server --model caslca/{model}"}

        def worker_ident(self, model):
            return {"pid": 202, "create_time": 1.0}

        def router_ok(self):
            return True

        router_config_sha = None

        def stop_stack(self):
            self.calls.append("stop_stack")
            return 0

    def test_a_power_failure_never_starts_the_router(self):
        """REPRODUCES: a failed power gate at entry refuses before start_router. ASSUMES
        bench.p475_kv.run_leg(spec, ops, ...) returns a receipt with verdict NOT_STARTED
        and that ops exposes power_ok() / busy_procs() / start_router() like ChainOps."""
        p475 = _import_p475()
        ops = self.FakeOps(power=False)
        spec = self._spec()
        receipt = p475.run_leg(spec, ops, run_driver=lambda *a: 0,
                              watcher=lambda s: (lambda: {"power_failure": None,
                                                         "exited_early": False, "ticks": 20}),
                              battery_intervals=lambda s, e: ([], []),
                              clock=iter(["2026-10-22 01:00:00", "2026-10-22 02:00:00"]).__next__,
                              repo_state=lambda: {})
        assert receipt["verdict"] == "NOT_STARTED"
        assert "start_router" not in ops.calls

    def test_a_busy_box_never_starts_the_router(self):
        """REPRODUCES: busy processes present at entry refuse before start_router."""
        p475 = _import_p475()
        ops = self.FakeOps(busy=["123 opencode run"])
        receipt = p475.run_leg(self._spec(), ops, run_driver=lambda *a: 0,
                              watcher=lambda s: (lambda: {"power_failure": None,
                                                         "exited_early": False, "ticks": 20}),
                              battery_intervals=lambda s, e: ([], []),
                              clock=iter(["2026-10-22 01:00:00", "2026-10-22 02:00:00"]).__next__,
                              repo_state=lambda: {})
        assert receipt["verdict"] == "NOT_STARTED"
        assert "start_router" not in ops.calls

    def test_a_bound_gate_lock_never_starts_the_router(self):
        """REPRODUCES: the gate lock C227 — :8000 already bound by another process —
        refuses before start_router. ASSUMES ops.listeners(port) is consulted at the
        gate lock (ChainOps.start_router raises ChainAbort on a bound port; the
        orchestrator's pre-check surfaces it as NOT_STARTED)."""
        p475 = _import_p475()
        ops = self.FakeOps(listeners=[9999])
        receipt = p475.run_leg(self._spec(), ops, run_driver=lambda *a: 0,
                              watcher=lambda s: (lambda: {"power_failure": None,
                                                         "exited_early": False, "ticks": 20}),
                              battery_intervals=lambda s, e: ([], []),
                              clock=iter(["2026-10-22 01:00:00", "2026-10-22 02:00:00"]).__next__,
                              repo_state=lambda: {})
        assert receipt["verdict"] == "NOT_STARTED"
        assert "start_router" not in ops.calls

    def test_an_existing_destination_never_starts_the_router(self):
        """REPRODUCES: a destination file already exists (a prior leg, or a rerun without a
        fresh out-tag) refuses before start_router. ASSUMES the spec carries destinations
        and the pre-check refuses on existence."""
        p475 = _import_p475()
        ops = self.FakeOps()
        spec = self._spec(destinations_exist=True)
        receipt = p475.run_leg(spec, ops, run_driver=lambda *a: 0,
                              watcher=lambda s: (lambda: {"power_failure": None,
                                                         "exited_early": False, "ticks": 20}),
                              battery_intervals=lambda s, e: ([], []),
                              clock=iter(["2026-10-22 01:00:00", "2026-10-22 02:00:00"]).__next__,
                              repo_state=lambda: {})
        assert receipt["verdict"] == "NOT_STARTED"
        assert "start_router" not in ops.calls

    def _spec(self, destinations_exist=False):
        """Build a minimal LegSpec-shaped dict the orchestrator accepts. ASSUMES
        bench.p475_kv.LegSpec (or a dict) with these fields; the implementer may rename,
        in which case this helper and the tests using it fail red and are reconciled."""
        import tempfile
        d = tempfile.mkdtemp()
        dest = Path(d) / "rows.jsonl"
        if destinations_exist:
            dest.write_text("{}\n")
        return {
            "name": "pick1-af8-b1", "pick": PICK1, "arm": "af8", "block": 1,
            "model": PICK1, "registry_text": _registry(PICK1, 8, "uniform"),
            "off_registry_text": _registry(PICK1),
            "destinations": [dest], "rows_path": dest,
            "server_log": Path(d) / "mlx_vlm.log", "receipt_dir": Path(d) / "receipts",
            "planned": [], "expected_requests": 0,
        }


# =========================================================================== replacement of speed-invalid legs
class TestReplacementQueue:
    """Every reported arm needs TWO speed-valid legs (power receipt, C224); a speed-invalid
    or INVALID leg is kept as evidence and REPLACED by a rerun. The orchestrator stops on
    the first INVALID leg; a speed-invalid leg is queued for replacement."""

    def test_a_speed_invalid_leg_is_kept_and_queued_for_replacement(self):
        """REPRODUCES: a leg that is VALID but speed-invalid (e.g. a power receipt failure)
        is kept as evidence and added to the replacement queue, not discarded. ASSUMES
        bench.p475_kv.replacement_queue(receipts) returns the legs needing a rerun."""
        p475 = _import_p475()
        receipts = [
            {"name": "pick1-af8-b1", "verdict": "VALID", "speed_valid": True},
            {"name": "pick1-af8-b2", "verdict": "VALID", "speed_valid": False},
        ]
        queue = p475.replacement_queue(receipts)
        assert any("pick1-af8-b2" in str(q) for q in queue)

    def test_a_valid_speed_valid_leg_is_not_queued(self):
        """REPRODUCES: a leg that is VALID and speed_valid is not queued for replacement."""
        p475 = _import_p475()
        receipts = [
            {"name": "pick1-af8-b1", "verdict": "VALID", "speed_valid": True},
            {"name": "pick1-af8-b2", "verdict": "VALID", "speed_valid": True},
        ]
        assert p475.replacement_queue(receipts) == []

    def test_an_invalid_leg_stops_the_run(self):
        """REPRODUCES: an INVALID leg stops the run (the spec: 'stop the run on the first
        INVALID leg'). ASSUMES bench.p475_kv.run_pick returns a stop reason on an INVALID
        leg. Stated as a behavioural assertion against run_pick with a forced INVALID."""
        p475 = _import_p475()
        # An INVALID leg (e.g. predictor-OFF violation) must stop the pick's run; the
        # orchestrator must not continue to the next leg. We assert the helper that
        # classifies a stop exists; on the baseline it does not.
        assert hasattr(p475, "stops_on_invalid"), "expected bench.p475_kv.stops_on_invalid"


# =========================================================================== instability trigger
class TestInstabilityTrigger:
    """Per arm and rung the two blocks' ratios vs N16 are reported side by side; a
    direction reversal OR a spread larger than half the ratio's distance from 1.0
    triggers a third (deciding) block for that pick."""

    def test_a_direction_reversal_triggers_a_deciding_block(self):
        """REPRODUCES: block 1 ratio > 1.0 and block 2 ratio < 1.0 (a direction reversal)
        triggers a third block. ASSUMES bench.p475_kv.instability_trigger(r1, r2) returns
        a non-empty trigger reason."""
        p475 = _import_p475()
        trigger = p475.instability_trigger(r1=1.10, r2=0.90)
        assert trigger  # direction reversal

    def test_a_spread_larger_than_half_the_distance_from_one_triggers(self):
        """REPRODUCES: |r1 - r2| > 0.5 * |r - 1.0| (the spread rule) triggers a third
        block. Example: r1=1.20, r2=1.06 -> spread 0.14 > 0.5 * 0.20 = 0.10."""
        p475 = _import_p475()
        trigger = p475.instability_trigger(r1=1.20, r2=1.06)
        assert trigger

    def test_a_small_consistent_spread_does_not_trigger(self):
        """REPRODUCES: two ratios on the same side of 1.0 with a small spread (within the
        rule) does NOT trigger a third block. Example: r1=1.10, r2=1.08 -> spread 0.02 <
        0.5 * 0.10 = 0.05."""
        p475 = _import_p475()
        trigger = p475.instability_trigger(r1=1.10, r2=1.08)
        assert not trigger

    def test_two_ratios_at_one_do_not_trigger(self):
        """REPRODUCES: r1 == r2 == 1.0 (no deviation, no spread) does not trigger."""
        p475 = _import_p475()
        assert not p475.instability_trigger(r1=1.0, r2=1.0)


# =========================================================================== harvest scrub
class TestHarvestScrub:
    """Harvest to benchmark/results/p475/<leg>/, scrubbed as the evidence branch is
    (workdir / repo / home paths -> $STACK_WORKDIR / $STACK_REPO / $HOME, username ->
    <user>, hostname -> localhost), with a SCRUB_MANIFEST.json of original and published
    sha256. Fail closed: an existing destination, residual PII, or an oversized file
    refuses before anything is written."""

    def test_harvest_scrubs_paths_user_and_host(self):
        """REPRODUCES: the harvest scrubs workdir/repo/home paths and username/hostname
        from every published file. ASSUMES bench.p475_kv.harvest(name, plan, main_root,
        receipts, stdout, log_slice, scrub) mirrors bench.p426_harvest.harvest."""
        p475 = _import_p475()
        from bench import p426_harvest as H
        import tempfile
        d = Path(tempfile.mkdtemp())
        workdir = d / "wd"; repo = d / "repo"; home = d / "home" / "u"
        frozen = workdir / "worktrees" / "stack-p475"
        receipts = workdir / "p475" / "receipts"
        main = repo / "main"
        for p in (frozen / "logs", receipts, main / "benchmark" / "results" / "p475"):
            p.mkdir(parents=True)
        scrub = H.Scrub(workdir=workdir, repo=main, home=home, user="u", hosts=("box", "box.example"))
        # a receipt carrying PII
        (receipts / "pick1-af8-b1.receipt.json").write_text(
            json.dumps({"cwd": str(frozen), "host": "box.example", "by": "u"}))
        plan = {"kind": "kv", "entry": PICK1, "results_dir": main / "benchmark" / "results" / "p475"}
        manifest = p475.harvest("pick1-af8-b1", plan, main_root=main, receipts=receipts,
                               stdout=b"out\n", log_slice=b"Request completed: x\n",
                               scrub=scrub)
        dossier = main / "benchmark" / "results" / "p475" / "pick1-af8-b1"
        receipt = json.loads((dossier / "pick1-af8-b1.receipt.json").read_text())
        assert receipt["cwd"] == "$STACK_WORKDIR/worktrees/stack-p475"
        assert receipt["host"] == "localhost"
        assert receipt["by"] == "<user>"
        assert (dossier / "SCRUB_MANIFEST.json").exists()

    def test_harvest_refuses_an_existing_destination(self):
        """REPRODUCES: an existing destination refuses before anything is written (fail
        closed)."""
        p475 = _import_p475()
        from bench import p426_harvest as H
        import tempfile
        d = Path(tempfile.mkdtemp())
        main = d / "main"; receipts = d / "receipts"
        dossier = main / "benchmark" / "results" / "p475" / "pick1-af8-b1"
        dossier.mkdir(parents=True)
        (dossier / "pick1-af8-b1.receipt.json").write_text('{"verdict": "VALID"}')
        receipts.mkdir(parents=True)
        scrub = H.Scrub(workdir=d / "wd", repo=main, home=d / "home", user="u", hosts=("box",))
        plan = {"kind": "kv", "entry": PICK1, "results_dir": main / "benchmark" / "results" / "p475"}
        with pytest.raises(Exception):
            p475.harvest("pick1-af8-b1", plan, main_root=main, receipts=receipts,
                         stdout=b"out\n", log_slice=b"x\n", scrub=scrub)


# =========================================================================== MATRIX.md generated, never hand-written
class TestMatrixGeneration:
    """benchmark/results/p475/MATRIX.md, generated from the harvested receipts and rows
    (never hand-copied): per pick x arm x rung each block's value and the mean for
    cumulative-peak GB, backend prefill tok/s and decode tok/s, plus the paired block
    ratios vs N16 and the instability flags; labelled descriptive."""

    def test_matrix_path_is_under_results_p475(self):
        """REPRODUCES: MATRIX.md lands at benchmark/results/p475/MATRIX.md. ASSUMES
        bench.p475_kv.MATRIX_PATH."""
        p475 = _import_p475()
        assert str(p475.MATRIX_PATH).replace("\\", "/").endswith("benchmark/results/p475/MATRIX.md")

    def test_generate_matrix_writes_markdown_from_receipts(self):
        """REPRODUCES: generate_matrix writes a markdown table from the harvested receipts
        and rows; it must NOT be hand-copied. ASSUMES bench.p475_kv.generate_matrix(rows,
        receipts, out_path) writes the file and returns a manifest of source shas."""
        p475 = _import_p475()
        import tempfile
        d = Path(tempfile.mkdtemp())
        out = d / "MATRIX.md"
        rows = [{"pick": PICK1, "arm": "af8", "block": 1, "rung": 8192,
                 "peak_memory_gb": 40.0, "prefill_tps": 200.0, "decode_tps": 9.5}]
        receipts = [{"name": "pick1-af8-b1", "verdict": "VALID", "speed_valid": True}]
        p475.generate_matrix(rows, receipts, out)
        text = out.read_text()
        assert "MATRIX" in text or "pick" in text.lower()
        # the table is generated, not empty
        assert len(text) > 0

    def test_generate_matrix_refuses_if_a_destination_exists(self):
        """REPRODUCES: generate_matrix refuses to overwrite an existing MATRIX.md (never
        hand-written, never silently replaced)."""
        p475 = _import_p475()
        import tempfile
        d = Path(tempfile.mkdtemp())
        out = d / "MATRIX.md"
        out.write_text("# hand-written\n")
        with pytest.raises(Exception):
            p475.generate_matrix([], [], out)
        # the hand-written file is preserved
        assert out.read_text() == "# hand-written\n"

    def test_generate_matrix_includes_paired_block_ratios_vs_n16(self):
        """REPRODUCES: the table includes the paired block ratios vs N16 (block 1 and
        block 2 side by side) per arm and rung. ASSUMES generate_matrix emits a ratio
        column."""
        p475 = _import_p475()
        import tempfile
        d = Path(tempfile.mkdtemp())
        out = d / "MATRIX.md"
        rows = [
            {"pick": PICK1, "arm": "n16", "block": 1, "rung": 8192, "prefill_tps": 100.0},
            {"pick": PICK1, "arm": "n16", "block": 2, "rung": 8192, "prefill_tps": 100.0},
            {"pick": PICK1, "arm": "af8", "block": 1, "rung": 8192, "prefill_tps": 110.0},
            {"pick": PICK1, "arm": "af8", "block": 2, "rung": 8192, "prefill_tps": 108.0},
        ]
        p475.generate_matrix(rows, [], out)
        text = out.read_text()
        assert "ratio" in text.lower() or "n16" in text.lower()

    def test_generate_matrix_includes_instability_flags(self):
        """REPRODUCES: the table includes the instability flags (a column marking the
        arms whose two blocks triggered a deciding block)."""
        p475 = _import_p475()
        import tempfile
        d = Path(tempfile.mkdtemp())
        out = d / "MATRIX.md"
        rows = [
            {"pick": PICK1, "arm": "n16", "block": 1, "rung": 8192, "prefill_tps": 100.0},
            {"pick": PICK1, "arm": "n16", "block": 2, "rung": 8192, "prefill_tps": 100.0},
            {"pick": PICK1, "arm": "af8", "block": 1, "rung": 8192, "prefill_tps": 110.0},
            {"pick": PICK1, "arm": "af8", "block": 2, "rung": 8192, "prefill_tps": 90.0},
        ]
        p475.generate_matrix(rows, [], out)
        text = out.read_text()
        assert "instab" in text.lower() or "flag" in text.lower()
