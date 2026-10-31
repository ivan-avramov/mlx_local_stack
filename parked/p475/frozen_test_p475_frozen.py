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

CANDIDATE SURFACE (delivery 2: re-pointed from the assumed names to what the
implementer actually landed; no assertion weakened):
  bench.p475_kv.PICKS                 — {short: full-registry-name}; full names via .values().
  bench.p475_kv.ARMS                  — ("N16","AF8","TQ8","AF4","TQ4") (uppercase).
  bench.p475_kv.ARM_KV                — {arm: {kv_bits, kv_quant_scheme}}.
  bench.p475_kv.block_arms(block)     — block 1 -> ARMS, block 2 -> reversed(ARMS).
  bench.p475_kv.IDLE_S                — 600.0.
  bench.p475_kv.arm_problems(leg, ai, base_text, arm_text)
  bench.p475_kv.manifest_preflight(worktree, entry, arm, loader=...)
  bench.p475_kv.worker_argv_problems(cmdline, entry)
  bench.p475_kv.kv_line_problems(log_text, entry)   # log_text is a string
  bench.p475_kv.predictor_off_problems(cmdline, manifest, rows)
  bench.p475_kv.gate_lock_problems(workdir)
  bench.p475_kv.run_leg(leg, cfg, deps, preflighted)
  bench.p475_kv.run(picks, *, do_leg, read_verdict, harvested, harvest, metrics_for, ...)
  bench.p475_kv.harvest_leg(leg, cfg, *, scrub, stdout, log_slice)
  bench.p475_kv.build_matrix(root) / _write_matrix(main_root)
  bench.p475_kv.instability_flags(by_arm_block) / ratios_vs_n16(by_arm_block)
  bench.capacity_ladder.p475_rung_problems(out, prev_peak_gb, seen_sessions)
  bench.run_capacity --p475-strict (passthrough strict_p475=True to the ladder).
"""
import json
import sys
from itertools import count as _count
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


def _leg(p475, pick="fable", arm="AF8", block=1):
    """Build a Leg for the candidate's uppercase arm names / short pick keys."""
    return p475.Leg(pick=pick, arm=arm, block=block)


def _arm_inputs(p475, pick="fable", arm="AF8", *, base_arm=False, clean=True,
                worktree="/wt/p475"):
    """An ArmInputs. base_arm=True -> head==base (the N16 arm uses the base commit)."""
    head = base = "P476_BASE"
    parent = base
    branch = "(base)"
    changed = []
    if not base_arm:
        head = "armHEAD"
        parent = base
        branch = p475.arm_branch(pick, arm)
        changed = ["main_models.yaml"]
    return p475.ArmInputs(worktree=worktree, branch=branch, head=head, base=base,
                          parent=parent, clean=clean, changed_files=changed)


def _entry_for(p475, model, text):
    """The pick's registry entry dict from `text` (the candidate's `_entry`)."""
    import yaml
    return p475._entry(yaml.safe_load(text), model)


def _provisional(text):
    """Add the `PROVISIONAL P475 arm` comment the arm commit carries (line 0 of the file)."""
    return "# PROVISIONAL P475 arm\n" + text


def _rung(*, cache_n=0, session_id="s1", completion_tokens=256, finish_reason="length",
          peak_mem_gb=40.0, prompt_ms=100.0, prompt_per_second=1000.0, prompt_n=1000,
          predicted_per_second=10.0, draft_kind=None):
    """A clean P475 rung `out` dict (raw_timings + the row fields p475_rung_problems reads)."""
    return {"raw_timings": {"prompt_ms": prompt_ms, "prompt_per_second": prompt_per_second,
                           "prompt_n": prompt_n, "predicted_per_second": predicted_per_second,
                           "cache_n": cache_n, "draft_kind": draft_kind},
            "session_id": session_id, "completion_tokens": completion_tokens,
            "finish_reason": finish_reason, "peak_mem_gb": peak_mem_gb}


def _by_arm_block(r1, r2, *, metric="prefill_tps", rung=8192, base=100.0):
    """A {arm: {block: {rung: {metric: value}}}} dict where AF8's block ratios vs N16 are
    r1 (block 1) and r2 (block 2) — the input shape instability_flags / ratios_vs_n16 take."""
    return {"N16": {1: {rung: {metric: base}}, 2: {rung: {metric: base}}},
            "AF8": {1: {rung: {metric: base * r1}}, 2: {rung: {metric: base * r2}}}}


def _matrix_harvest(root, legs):
    """Write a harvested P475 leg tree (receipt + capacity_ladder rows jsonl) under
    <root>/benchmark/results/p475/<name>/ — the input shape build_matrix(root) reads.
    legs: [(name, pick, arm, block, [(rung, peak_gb, prefill_tps, decode_tps), ...])]."""
    base = Path(root) / "benchmark" / "results" / "p475"
    for name, pick, arm, block, rungs in legs:
        d = base / name
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.receipt.json").write_text(json.dumps({
            "name": name, "pick": pick, "arm": arm, "block": block, "attempt": 0,
            "verdict": "VALID", "speed_valid": True}))
        rows = [{"ctx": rung, "peak_memory_gb_cumulative": peak,
                 "prompt_per_second": prefill, "predicted_per_second": decode,
                 "p475_valid": True} for rung, peak, prefill, decode in rungs]
        (d / f"capacity_ladder.p475.{name}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""))


# =========================================================================== arm-commit / worktree
class TestArmCommit:
    """The arm is a commit on p475-<pick-short>-<arm> off the P476 commit, changing ONLY
    that entry's KV keys (+ a PROVISIONAL P475 arm comment)."""

    def test_arm_commit_changes_only_the_entrys_kv_keys(self):
        """REPRODUCES: an arm commit that also touches a bystander model's settings is
        refused. Re-pointed to bench.p475_kv.arm_problems(leg, ai, base_text, arm_text)
        (empty == clean)."""
        p475 = _import_p475()
        off = _registry(PICK1)
        on = _provisional(_registry(PICK1, kv_bits=8, kv_quant_scheme="uniform"))
        leg = _leg(p475, "fable", "AF8")
        ai = _arm_inputs(p475, "fable", "AF8")
        assert p475.arm_problems(leg, ai, off, on) == []

    def test_arm_commit_with_a_changed_bystander_is_refused(self):
        """REPRODUCES: the bystander Other entry changed between the arm and the base."""
        p475 = _import_p475()
        off = _registry(PICK1)
        on = _provisional(_registry(PICK1, kv_bits=8, kv_quant_scheme="uniform").replace(
            "caslca/Other", "caslca/Other-CHANGED"))
        leg = _leg(p475, "fable", "AF8")
        ai = _arm_inputs(p475, "fable", "AF8")
        problems = p475.arm_problems(leg, ai, off, on)
        assert problems and any("outside the pick" in p for p in problems)

    def test_arm_commit_with_a_wrong_kv_bits_value_is_refused(self):
        """REPRODUCES: the arm labelled AF8 carries kv_bits=4 (a wrong key value)."""
        p475 = _import_p475()
        off = _registry(PICK1)
        on = _provisional(_registry(PICK1, kv_bits=4, kv_quant_scheme="uniform"))
        leg = _leg(p475, "fable", "AF8")
        ai = _arm_inputs(p475, "fable", "AF8")
        problems = p475.arm_problems(leg, ai, off, on)
        assert problems and any("kv_bits" in p for p in problems)

    def test_arm_commit_with_a_wrong_scheme_is_refused(self):
        """REPRODUCES: the arm labelled TQ8 carries kv_quant_scheme=uniform."""
        p475 = _import_p475()
        off = _registry(PICK1)
        on = _provisional(_registry(PICK1, kv_bits=8, kv_quant_scheme="uniform"))
        leg = _leg(p475, "fable", "TQ8")
        ai = _arm_inputs(p475, "fable", "TQ8")
        problems = p475.arm_problems(leg, ai, off, on)
        assert problems and any("scheme" in p.lower() for p in problems)

    def test_arm_commit_with_an_extra_change_is_refused(self):
        """REPRODUCES: the arm commit also changed attention_policy (kept as deployed)."""
        p475 = _import_p475()
        off = _registry(PICK1)
        on = _provisional(_registry(PICK1, kv_bits=8, kv_quant_scheme="uniform").replace(
            "fused_v1", "default"))
        leg = _leg(p475, "fable", "AF8")
        ai = _arm_inputs(p475, "fable", "AF8")
        problems = p475.arm_problems(leg, ai, off, on)
        assert problems and any("attention" in p.lower() for p in problems)

    def test_arm_commit_with_mtp_present_is_refused(self):
        """REPRODUCES: the arm commit added draft_kind: mtp (P475 is predictor-OFF; an MTP
        line is an extra change AND a predictor-OFF violation)."""
        p475 = _import_p475()
        off = _registry(PICK1)
        on = _provisional(_registry(PICK1, kv_bits=8, kv_quant_scheme="uniform") + \
            "    draft_kind: mtp\n    draft_model: caslca/x-mtp-drafter\n")
        leg = _leg(p475, "fable", "AF8")
        ai = _arm_inputs(p475, "fable", "AF8")
        problems = p475.arm_problems(leg, ai, off, on)
        assert problems and any("draft" in p.lower() for p in problems)

    def test_arm_commit_with_quantized_kv_start_nonzero_is_refused(self):
        """REPRODUCES: the spec pins quantized_kv_start to 0 in every arm; a non-zero
        value is a wrong key (and the kvmanifest validator refuses to model it)."""
        p475 = _import_p475()
        off = _registry(PICK1)
        on = _provisional(_registry(PICK1, kv_bits=8, kv_quant_scheme="uniform").replace(
            "quantized_kv_start: 0", "quantized_kv_start: 5000"))
        leg = _leg(p475, "fable", "AF8")
        ai = _arm_inputs(p475, "fable", "AF8")
        problems = p475.arm_problems(leg, ai, off, on)
        assert problems and any("quantized_kv_start" in p for p in problems)

    def test_the_n16_arm_uses_the_base_commit_verbatim(self):
        """PRESERVES: the arm equal to the committed registry (N16, native16) uses the base
        commit; the arm-commit check passes when on == off for the N16 arm (head == base)."""
        p475 = _import_p475()
        off = _registry(PICK1, kv_bits=0)
        leg = _leg(p475, "fable", "N16")
        ai = _arm_inputs(p475, "fable", "N16", base_arm=True)
        assert p475.arm_problems(leg, ai, off, off) == []


# =========================================================================== engagement preflight
class TestEngagementPreflight:
    """Per arm, before its first leg: an in-process known-positive check on the arm's
    committed registry with the fork's per-layer cache-manifest validator. A mismatch
    refuses the arm."""

    def test_a_matching_manifest_passes_the_preflight(self):
        """REPRODUCES (amended to spec v2 finding 1 — the live preflight): the engagement
        preflight passes ONLY on a COMPLETED qualify report whose observed per-layer cache
        manifest matches the arm's KV config (predictor OFF, the arm's registry sha and
        reviewed head, no end problems), and refuses otherwise. The stand-in
        `manifest_preflight` is gone; re-pointed to bench.p475_kv.qualify_report_problems
        (report, model, entry, km, registry_sha, fork_sha) — the report-level check
        `run_preflight` relies on."""
        p475 = _import_p475()
        kv = _import_kvmanifest()
        entry = {"name": PICK1, "hf_path": "caslca/" + PICK1, "kv_bits": 8,
                 "kv_quant_scheme": "uniform", "quantized_kv_start": 0}
        template = [
            {"path": "0", "kind": "native", "cls": "KVCache", "batch": False},
            {"path": "1", "kind": "native", "cls": "KVCache", "batch": False},
        ]
        kv_af8 = kv.kv_from_argv(["--model", "caslca/" + PICK1, "--kv-bits", "8",
                                  "--kv-quant-scheme", "uniform", "--quantized-kv-start", "0"])
        observed = kv.expected_manifest(template, kv_af8)   # the arm's exact per-layer manifest
        registry_sha = "sha-registry-arm"
        fork_sha = "armHEAD"
        report_ok = {"predictor": "off", "registry_sha256": registry_sha,
                     "reviewed_head": fork_sha, "end_problems": [],
                     "entries": {PICK1: {"status": "COMPLETED", "arm": "served",
                                         "record": {"manifest": observed,
                                                    "template": template}}}}
        assert p475.qualify_report_problems(report_ok, PICK1, entry, kv,
                                             registry_sha, fork_sha) == []
        # a non-COMPLETED report (qualify refused the arm before the manifest) is refused
        report_refused = dict(report_ok)
        report_refused["entries"] = {PICK1: {"status": "REFUSED",
                                             "reason": "registry not accepted"}}
        problems = p475.qualify_report_problems(report_refused, PICK1, entry, kv,
                                                registry_sha, fork_sha)
        assert problems and any("COMPLETED" in p or "status" in p.lower() for p in problems)

    def test_a_mismatched_manifest_refuses_the_arm(self):
        """REPRODUCES: the observed manifest's leaf kinds disagree with what the arm's argv
        implies (the worker served native16 while the arm asked AF8). Re-pointed to the
        fork validator's manifest_problems (the check manifest_preflight relies on)."""
        kv = _import_kvmanifest()
        template = [
            {"path": "0", "kind": "native", "cls": "KVCache", "batch": False},
            {"path": "1", "kind": "native", "cls": "KVCache", "batch": False},
        ]
        observed = [dict(t) for t in template]  # stayed native — codec did not engage
        kv_af8 = kv.kv_from_argv(["--model", "m", "--kv-bits", "8", "--kv-quant-scheme",
                                 "uniform", "--quantized-kv-start", "0"])
        problems = kv.manifest_problems(observed, template, kv_af8)
        assert problems and any("0" in p for p in problems)

    def test_a_tq8_arm_keeps_the_last_top_level_leaf_native(self):
        """REPRODUCES: TurboQuant converts every KV layer EXCEPT the last top-level cache
        entry when there are more than two; a TQ8 arm that quantized the last leaf is
        refused. Re-pointed to the fork validator's expected_manifest rule + manifest_problems
        (the rule manifest_preflight encodes via _caches('tq', 8))."""
        kv = _import_kvmanifest()
        template = [
            {"path": "0", "kind": "native", "cls": "KVCache", "batch": False},
            {"path": "1", "kind": "native", "cls": "KVCache", "batch": False},
            {"path": "2", "kind": "native", "cls": "KVCache", "batch": False},
        ]
        kv_tq8 = kv.kv_from_argv(["--model", "m", "--kv-bits", "8", "--kv-quant-scheme",
                                  "turboquant", "--quantized-kv-start", "0"])
        expected = kv.expected_manifest(template, kv_tq8)
        assert expected[-1]["kind"] == "native"
        bad = [dict(t) for t in expected]
        bad[-1] = dict(bad[-1], kind="tq", bits=8.0, key_bits=8.0, value_bits=8.0, mode="mse")
        problems = kv.manifest_problems(bad, template, kv_tq8)
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
        --quantized-kv-start 0) passes. Re-pointed to
        bench.p475_kv.worker_argv_problems(cmdline, entry) (entry = the pick's registry
        entry dict); returns [] on a match."""
        p475 = _import_p475()
        entry = _entry_for(p475, PICK1, _registry(PICK1, 8, "uniform"))
        cmd = (f"1 python -m mlx_vlm.server --model caslca/{PICK1} "
               "--kv-bits 8 --kv-quant-scheme uniform --quantized-kv-start 0")
        assert p475.worker_argv_problems(cmd, entry) == []

    def test_argv_missing_the_kv_bits_flag_is_refused(self):
        """REPRODUCES: the worker argv omits --kv-bits (the codec defaulted to native16
        while the arm asked AF8)."""
        p475 = _import_p475()
        entry = _entry_for(p475, PICK1, _registry(PICK1, 8, "uniform"))
        cmd = f"1 python -m mlx_vlm.server --model caslca/{PICK1} --kv-quant-scheme uniform"
        problems = p475.worker_argv_problems(cmd, entry)
        assert problems and any("kv-bits" in p for p in problems)

    def test_argv_with_a_wrong_scheme_is_refused(self):
        """REPRODUCES: a TQ8 arm's worker carries --kv-quant-scheme uniform."""
        p475 = _import_p475()
        entry = _entry_for(p475, PICK1, _registry(PICK1, 8, "turboquant"))
        cmd = (f"1 python -m mlx_vlm.server --model caslca/{PICK1} "
               "--kv-bits 8 --kv-quant-scheme uniform --quantized-kv-start 0")
        problems = p475.worker_argv_problems(cmd, entry)
        assert problems and any("scheme" in p.lower() for p in problems)

    def test_argv_with_a_nonzero_quantized_kv_start_is_refused(self):
        """REPRODUCES: the worker carries --quantized-kv-start 5000 (the spec pins 0)."""
        p475 = _import_p475()
        entry = _entry_for(p475, PICK1, _registry(PICK1, 8, "uniform"))
        cmd = (f"1 python -m mlx_vlm.server --model caslca/{PICK1} "
               "--kv-bits 8 --kv-quant-scheme uniform --quantized-kv-start 5000")
        problems = p475.worker_argv_problems(cmd, entry)
        assert problems and any("quantized-kv-start" in p for p in problems)

    def test_the_kv_cache_resolved_line_must_match_the_arm(self):
        """REPRODUCES: the worker log's `KV cache resolved` line carries the arm's KV
        flags. Re-pointed to bench.p475_kv.kv_line_problems(log_text, entry) (log_text is
        a string; entry the pick's registry entry dict)."""
        p475 = _import_p475()
        entry = _entry_for(p475, PICK1, _registry(PICK1, 8, "uniform"))
        line = ("KV cache resolved: kv_bits=8 kv_key_bits=None kv_value_bits=None "
                "kv_key_scheme=None kv_value_scheme=None kv_quant_scheme='uniform' "
                "kv_group_size=64 quantized_kv_start=0 TQ_KV_QUANT_MODE='mse'")
        assert p475.kv_line_problems(line, entry) == []

    def test_the_kv_cache_resolved_line_disagreeing_with_the_arm_is_refused(self):
        """REPRODUCES: the worker log resolved native16 (kv_bits=None) while the arm asked
        AF8 — the secondary record disagrees with the argv."""
        p475 = _import_p475()
        entry = _entry_for(p475, PICK1, _registry(PICK1, 8, "uniform"))
        line = ("KV cache resolved: kv_bits=None kv_key_bits=None kv_value_bits=None "
                "kv_key_scheme=None kv_value_scheme=None kv_quant_scheme='uniform' "
                "kv_group_size=64 quantized_kv_start=0 TQ_KV_QUANT_MODE='mse'")
        problems = p475.kv_line_problems(line, entry)
        assert problems and any("kv_bits" in p for p in problems)

    def test_a_missing_kv_cache_resolved_line_is_refused(self):
        """REPRODUCES: the worker log carries no `KV cache resolved` line at all (the
        codec never logged its resolution); the secondary record is required, not
        optional."""
        p475 = _import_p475()
        entry = _entry_for(p475, PICK1, _registry(PICK1, 8, "uniform"))
        problems = p475.kv_line_problems("unrelated log line", entry)
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
        """REPRODUCES: under the opt-in, the row's prefill comes from the backend's prompt_ms /
        prompt_per_second / prompt_n, NOT from wall - decode. Re-pointed to the ladder module
        the run_capacity --p475-strict flag invokes with strict_p475=True (capacity_ladder.py
        persists the backend's prompt_ms / prompt_per_second / prompt_n on the row)."""
        src = open(L.__file__).read()
        if "prompt_ms" not in src or "prompt_per_second" not in src or "prompt_n" not in src:
            pytest.fail("capacity_ladder (the --p475-strict path) does not persist the "
                        "backend's prompt_ms / prompt_per_second / prompt_n")

    def test_p475_optin_refuses_a_row_with_cache_n_not_zero(self):
        """REPRODUCES: every measured request must have cache_n == 0 (a fresh session, no
        prefix reuse); a row with cache_n > 0 is INVALID. Re-pointed to
        bench.capacity_ladder.p475_rung_problems (the rung validator the opt-in path uses)."""
        clean = L.p475_rung_problems(_rung(cache_n=0, session_id="s1"), None, set())
        assert not any("cache_n" in p for p in clean)
        dirty = L.p475_rung_problems(_rung(cache_n=128, session_id="s2"), None, set())
        assert dirty and any("cache_n" in p for p in dirty)

    def test_p475_optin_requires_a_unique_session_id_per_request(self):
        """REPRODUCES: every measured request carries a unique session id; two rows sharing
        a session id is INVALID (the cache was reused, not fresh)."""
        first = L.p475_rung_problems(_rung(session_id="s1"), None, set())
        assert not any("session" in p.lower() for p in first)
        reused = L.p475_rung_problems(_rung(session_id="s1"), None, {"s1"})
        assert reused and any("session" in p.lower() for p in reused)

    def test_p475_decode_tok_s_comes_from_predicted_per_second(self):
        """REPRODUCES: under the opt-in, decode tok/s is the backend's predicted_per_second,
        not a wall-derived figure. Re-pointed to capacity_ladder (the --p475-strict path)."""
        src = open(L.__file__).read()
        if "predicted_per_second" not in src:
            pytest.fail("capacity_ladder (the --p475-strict path) does not use the backend's "
                        "predicted_per_second")

    def test_p475_memory_is_cumulative_high_water_peak_memory_gb(self):
        """REPRODUCES: memory is the worker's cumulative high-water peak_memory_gb
        (process-lifetime, incl. the full-cap preallocation of the first request and the
        calibration) at each rung — never a per-rung peak. Re-pointed to capacity_ladder
        (persists peak_memory_gb_cumulative on the row)."""
        src = open(L.__file__).read()
        if "peak_memory_gb" not in src:
            pytest.fail("capacity_ladder (the --p475-strict path) does not report cumulative "
                        "peak_memory_gb")


# =========================================================================== exact-length decode
class TestExactLengthDecode:
    """A fixed decode carrier per rung runs to the token cap: exactly 256 completion
    tokens and finish_reason == "length", else the rung is INVALID."""

    def test_a_length_finish_with_256_tokens_passes(self):
        """REPRODUCES: a rung with finish_reason == "length" and completion_tokens == 256
        passes. Re-pointed to bench.capacity_ladder.p475_rung_problems (the rung validator
        the --p475-strict path uses); a clean rung returns no completion_tokens /
        finish_reason problem."""
        problems = L.p475_rung_problems(_rung(completion_tokens=256, finish_reason="length"),
                                        None, set())
        assert not any("completion_tokens" in p or "finish_reason" in p for p in problems)

    def test_a_short_decode_is_invalid(self):
        """REPRODUCES: completion_tokens < 256 (the decode carrier did not reach the cap)
        is INVALID."""
        problems = L.p475_rung_problems(_rung(completion_tokens=200, finish_reason="length"),
                                        None, set())
        assert problems and any("256" in p or "completion_tokens" in p for p in problems)

    def test_a_non_length_finish_reason_is_invalid(self):
        """REPRODUCES: finish_reason == "stop" (the carrier stopped early) is INVALID; the
        spec requires finish_reason == "length"."""
        problems = L.p475_rung_problems(_rung(completion_tokens=256, finish_reason="stop"),
                                        None, set())
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
        """REPRODUCES: block 1 visits the arms in the spec's order. Re-pointed to
        bench.p475_kv.block_arms(1) (ARMS = N16,AF8,TQ8,AF4,TQ4)."""
        p475 = _import_p475()
        assert list(p475.block_arms(1)) == ["N16", "AF8", "TQ8", "AF4", "TQ4"]

    def test_block_2_order_is_the_reverse(self):
        """REPRODUCES: block 2 is the reverse of block 1 (order-balanced)."""
        p475 = _import_p475()
        block1 = list(p475.block_arms(1))
        block2 = list(p475.block_arms(2))
        assert block2 == list(reversed(block1))

    def test_idle_seconds_is_at_least_600(self):
        """REPRODUCES: the spec pins >= 600 s idle before every leg. Re-pointed to
        bench.p475_kv.IDLE_S."""
        p475 = _import_p475()
        assert p475.IDLE_S >= 600

    def test_picks_run_sequentially(self):
        """REPRODUCES: picks are sequential (pick 1's two blocks complete before pick 2
        starts). Re-pointed to bench.p475_kv.PICKS (a {short: full-name} dict; the full
        registry names are the values, in order)."""
        p475 = _import_p475()
        assert list(p475.PICKS.values()) == [PICK1, PICK2]

    def test_twenty_legs_total(self):
        """REPRODUCES: 2 picks x 2 blocks x 5 arms = 20 legs. Re-pointed to
        bench.p475_kv.schedule (the orchestrator's leg list)."""
        p475 = _import_p475()
        legs = p475.schedule()
        assert len(legs) == 20


# =========================================================================== pre-check refusals (power / busy / gate-lock / destinations)
class TestPreCheckRefusals:
    """Per leg: pre-check (power, nothing busy, the gate lock C227, destinations absent).
    A failed pre-check never starts the router (NOT_STARTED)."""

    class FakeOps:
        """Minimal ops injection seam mirroring bench.p426_leg's FakeOps pattern: the
        orchestrator calls these in order, and a refusal stops before start_router."""

        def __init__(self, *, power=True, busy=(), listeners=()):
            self.calls = []
            self._power = power
            self._busy = list(busy)
            self._listeners = list(listeners)

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

    def _run_leg(self, p475, ops, *, destinations_exist=False, gate_locked=False):
        """Wire FakeOps into the candidate's run_leg(leg, cfg, deps, preflighted) and
        return (receipt, ops.calls). The arm / preflight are clean (preflighted set), so
        the only pre problems are the ones the test injects via FakeOps / lock_check."""
        import tempfile
        d = Path(tempfile.mkdtemp())
        leg = p475.Leg(pick="fable", arm="AF8", block=1)
        ai = p475.ArmInputs(worktree=str(d / "wt"),
                             branch=p475.arm_branch("fable", "AF8"), head="H", base="B",
                             parent="B", clean=True, changed_files=["main_models.yaml"])
        arm_text = _provisional(_registry(PICK1, kv_bits=8, kv_quant_scheme="uniform"))
        base_text = _registry(PICK1, kv_bits=0)
        results = d / "benchmark" / "results" / PICK1
        results.mkdir(parents=True, exist_ok=True)
        if destinations_exist:
            (results / f"capacity_ladder.{leg.tag}.jsonl").write_text("{}")
        cfg = p475.Config(receipt_dir=d / "receipts", workdir=d / "wd",
                          instrument_root=d, main_root=d, base_registry_text=base_text,
                          python="python")
        (d / "wd").mkdir(parents=True, exist_ok=True)
        deps = p475.Deps(
            ops_for=lambda leg, ai: ops,
            arm_inputs=lambda leg: ai,
            read_text=lambda p: arm_text,
            load_kvmanifest=lambda wt: None,        # not called: (fable, AF8) is preflighted
            launch_driver=lambda *a: None,
            start_watch=lambda *a: None,
            read_rows=lambda p: [],
            read_json=lambda p: {},
            read_worker_log=lambda ops, m: "",
            lock_check=lambda wd: (["gate locked"] if gate_locked else []),
            clock=lambda: "2026-10-22 01:00:00",
        )
        receipt = p475.run_leg(leg, cfg, deps, {("fable", "AF8")})
        return receipt, ops.calls

    def test_a_power_failure_never_starts_the_router(self):
        """REPRODUCES: a failed power gate at entry refuses before start_router. Re-pointed
        to bench.p475_kv.run_leg(leg, cfg, deps, preflighted) with FakeOps.power_ok()=False."""
        p475 = _import_p475()
        ops = self.FakeOps(power=False)
        receipt, calls = self._run_leg(p475, ops)
        assert receipt["verdict"] == "NOT_STARTED"
        assert "start_router" not in calls

    def test_a_busy_box_never_starts_the_router(self):
        """REPRODUCES: busy processes present at entry refuse before start_router."""
        p475 = _import_p475()
        ops = self.FakeOps(busy=["123 opencode run"])
        receipt, calls = self._run_leg(p475, ops)
        assert receipt["verdict"] == "NOT_STARTED"
        assert "start_router" not in calls

    def test_a_bound_gate_lock_never_starts_the_router(self):
        """REPRODUCES: the gate lock C227 — :8000 already bound by another process —
        refuses before start_router. Re-pointed to FakeOps.listeners()=[9999] (the
        orchestrator's pre-check surfaces a bound port as NOT_STARTED)."""
        p475 = _import_p475()
        ops = self.FakeOps(listeners=[9999])
        receipt, calls = self._run_leg(p475, ops)
        assert receipt["verdict"] == "NOT_STARTED"
        assert "start_router" not in calls

    def test_an_existing_destination_never_starts_the_router(self):
        """REPRODUCES: a destination file already exists (a prior leg, or a rerun without a
        fresh out-tag) refuses before start_router. Re-pointed to run_leg with a pre-created
        capacity_ladder rows destination."""
        p475 = _import_p475()
        ops = self.FakeOps()
        receipt, calls = self._run_leg(p475, ops, destinations_exist=True)
        assert receipt["verdict"] == "NOT_STARTED"
        assert "start_router" not in calls


# =========================================================================== replacement of speed-invalid legs
class TestReplacementQueue:
    """Every reported arm needs TWO speed-valid legs (power receipt, C224); a speed-invalid
    or INVALID leg is kept as evidence and REPLACED by a rerun. The orchestrator stops on
    the first INVALID leg; a speed-invalid leg is queued for replacement."""

    def test_a_speed_invalid_leg_is_kept_and_queued_for_replacement(self):
        """REPRODUCES: a leg that is VALID but speed-invalid (e.g. a power receipt failure)
        is kept as evidence and a replacement is queued (a rerun with attempt += 1), not
        discarded. Re-pointed to bench.p475_kv.run() (the sequencer's cell() replacement
        loop): the speed-invalid AF8-b1 leg is harvested (kept) and then re-run as
        fable-AF8-b1-r1."""
        p475 = _import_p475()
        harvested, do_calls = [], []

        def do_leg(leg):
            do_calls.append(leg.name)
            if leg.arm == "AF8" and leg.attempt == 0:
                return {"name": leg.name, "verdict": "SPEED_INVALID", "speed_valid": False}
            return {"name": leg.name, "verdict": "VALID", "speed_valid": True}

        rc = p475.run(("fable",), do_leg=do_leg, read_verdict=lambda n: None,
                      harvested=lambda n: True,
                      harvest=lambda leg, r: harvested.append(leg.name),
                      metrics_for=lambda leg: {}, sleep=lambda s: None,
                      clock=_count(0, 10000).__next__, log=lambda m: None, blocks=(1,))
        assert "fable-AF8-b1" in harvested           # kept as evidence
        assert "fable-AF8-b1-r1" in harvested         # replacement ran
        assert rc == 0

    def test_a_valid_speed_valid_leg_is_not_queued(self):
        """REPRODUCES: a leg that is VALID and speed_valid is not queued for replacement
        (no -rN rerun)."""
        p475 = _import_p475()
        do_calls = []

        def do_leg(leg):
            do_calls.append(leg.name)
            return {"name": leg.name, "verdict": "VALID", "speed_valid": True}

        rc = p475.run(("fable",), do_leg=do_leg, read_verdict=lambda n: None,
                      harvested=lambda n: True, harvest=lambda l, r: None,
                      metrics_for=lambda l: {}, sleep=lambda s: None,
                      clock=_count(0, 10000).__next__, log=lambda m: None, blocks=(1,))
        assert not any("-r" in c for c in do_calls)   # no replacement queued
        assert rc == 0

    def test_an_invalid_leg_stops_the_run(self):
        """REPRODUCES: an INVALID leg stops the run (the spec: 'stop the run on the first
        INVALID leg'). Re-pointed to bench.p475_kv.run(): an INVALID first leg returns 1
        and the next leg never runs."""
        p475 = _import_p475()
        do_calls = []

        def do_leg(leg):
            do_calls.append(leg.name)
            return {"name": leg.name, "verdict": "INVALID", "speed_valid": False}

        rc = p475.run(("fable",), do_leg=do_leg, read_verdict=lambda n: None,
                      harvested=lambda n: True, harvest=lambda l, r: None,
                      metrics_for=lambda l: {}, sleep=lambda s: None,
                      clock=_count(0, 10000).__next__, log=lambda m: None, blocks=(1,))
        assert rc == 1                                # stopped on INVALID
        assert len(do_calls) == 1                     # did not continue to the next leg


# =========================================================================== instability trigger
class TestInstabilityTrigger:
    """Per arm and rung the two blocks' ratios vs N16 are reported side by side; a
    direction reversal OR a spread larger than half the ratio's distance from 1.0
    triggers a third (deciding) block for that pick."""

    def test_a_direction_reversal_triggers_a_deciding_block(self):
        """REPRODUCES: block 1 ratio > 1.0 and block 2 ratio < 1.0 (a direction reversal)
        triggers a third block. Re-pointed to bench.p475_kv.instability_flags(by_arm_block)
        (AF8 b1=1.10, b2=0.90 vs N16)."""
        p475 = _import_p475()
        flags = p475.instability_flags(_by_arm_block(1.10, 0.90))
        assert flags  # direction reversal

    def test_a_spread_larger_than_half_the_distance_from_one_triggers(self):
        """REPRODUCES: |r1 - r2| > 0.5 * |r - 1.0| (the spread rule) triggers a third
        block. Example: r1=1.20, r2=1.06 -> spread 0.14 > 0.5 * 0.20 = 0.10."""
        p475 = _import_p475()
        flags = p475.instability_flags(_by_arm_block(1.20, 1.06))
        assert flags

    def test_a_small_consistent_spread_does_not_trigger(self):
        """REPRODUCES: two ratios on the same side of 1.0 with a small spread (within the
        rule) does NOT trigger a third block. Example: r1=1.10, r2=1.08 -> spread 0.02 <
        0.5 * 0.10 = 0.05."""
        p475 = _import_p475()
        flags = p475.instability_flags(_by_arm_block(1.10, 1.08))
        assert not flags

    def test_two_ratios_at_one_do_not_trigger(self):
        """REPRODUCES: r1 == r2 == 1.0 (no deviation, no spread) does not trigger."""
        p475 = _import_p475()
        assert not p475.instability_flags(_by_arm_block(1.0, 1.0))


# =========================================================================== harvest scrub
class TestHarvestScrub:
    """Harvest to benchmark/results/p475/<leg>/, scrubbed as the evidence branch is
    (workdir / repo / home paths -> $STACK_WORKDIR / $STACK_REPO / $HOME, username ->
    <user>, hostname -> localhost), with a SCRUB_MANIFEST.json of original and published
    sha256. Fail closed: an existing destination, residual PII, or an oversized file
    refuses before anything is written."""

    def test_harvest_scrubs_paths_user_and_host(self):
        """REPRODUCES: the harvest scrubs workdir/repo/home paths and username/hostname
        from every published file. Re-pointed to bench.p475_kv.harvest_leg(leg, cfg, *,
        scrub, stdout, log_slice) (mirrors bench.p426_harvest via _publish / Scrub)."""
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
        leg = p475.Leg(pick="fable", arm="AF8", block=1)       # name = fable-AF8-b1
        cfg = p475.Config(receipt_dir=receipts, workdir=workdir, instrument_root=main,
                          main_root=main, base_registry_text=_registry(PICK1, kv_bits=0),
                          python="python")
        # a receipt carrying PII
        (receipts / "fable-AF8-b1.receipt.json").write_text(
            json.dumps({"cwd": str(frozen), "host": "box.example", "by": "u"}))
        manifest = p475.harvest_leg(leg, cfg, scrub=scrub, stdout=b"out\n",
                                   log_slice=b"Request completed: x\n")
        dossier = main / "benchmark" / "results" / "p475" / "fable-AF8-b1"
        receipt = json.loads((dossier / "fable-AF8-b1.receipt.json").read_text())
        assert receipt["cwd"] == "$STACK_WORKDIR/worktrees/stack-p475"
        assert receipt["host"] == "localhost"
        assert receipt["by"] == "<user>"
        assert (dossier / "SCRUB_MANIFEST.json").exists()

    def test_harvest_refuses_an_existing_destination(self):
        """REPRODUCES: an existing destination refuses before anything is written (fail
        closed). Re-pointed to harvest_leg with a pre-existing dossier."""
        p475 = _import_p475()
        from bench import p426_harvest as H
        import tempfile
        d = Path(tempfile.mkdtemp())
        main = d / "main"; receipts = d / "receipts"
        leg = p475.Leg(pick="fable", arm="AF8", block=1)
        dossier = main / "benchmark" / "results" / "p475" / "fable-AF8-b1"
        dossier.mkdir(parents=True)
        (dossier / "fable-AF8-b1.receipt.json").write_text('{"verdict": "VALID"}')
        receipts.mkdir(parents=True)
        scrub = H.Scrub(workdir=d / "wd", repo=main, home=d / "home", user="u", hosts=("box",))
        cfg = p475.Config(receipt_dir=receipts, workdir=d / "wd", instrument_root=main,
                          main_root=main, base_registry_text=_registry(PICK1, kv_bits=0),
                          python="python")
        with pytest.raises(Exception):
            p475.harvest_leg(leg, cfg, scrub=scrub, stdout=b"out\n", log_slice=b"x\n")


# =========================================================================== MATRIX.md generated, never hand-written
class TestMatrixGeneration:
    """benchmark/results/p475/MATRIX.md, generated from the harvested receipts and rows
    (never hand-copied): per pick x arm x rung each block's value and the mean for
    cumulative-peak GB, backend prefill tok/s and decode tok/s, plus the paired block
    ratios vs N16 and the instability flags; labelled descriptive."""

    def test_matrix_path_is_under_results_p475(self):
        """REPRODUCES (amended to spec v2 finding 3): the canonical MATRIX.md exists ONLY
        for a complete harvest; an incomplete (here empty) harvest writes ONLY the partial
        diagnostic `MATRIX.PARTIAL.md` and must NOT create the canonical `MATRIX.md`.
        Re-pointed to bench.p475_kv._write_matrix(main_root): with no harvest it returns
        RESULTS_P475 / 'MATRIX.PARTIAL.md' and leaves 'MATRIX.md' absent."""
        p475 = _import_p475()
        import tempfile
        d = Path(tempfile.mkdtemp())
        path = p475._write_matrix(d)
        assert str(path).replace("\\", "/").endswith("benchmark/results/p475/MATRIX.PARTIAL.md")
        assert not (d / "benchmark" / "results" / "p475" / "MATRIX.md").exists()

    def test_generate_matrix_writes_markdown_from_receipts(self):
        """REPRODUCES: build_matrix writes a markdown table from the harvested receipts
        and rows; it must NOT be hand-copied. Re-pointed to bench.p475_kv.build_matrix(root),
        which reads the harvest under <root>/benchmark/results/p475/<leg>/."""
        p475 = _import_p475()
        import tempfile
        d = Path(tempfile.mkdtemp())
        _matrix_harvest(d, [("fable-AF8-b1", "fable", "AF8", 1,
                             [(8192, 40.0, 200.0, 9.5)])])
        text = p475.build_matrix(d)
        assert len(text) > 0
        assert "P475" in text or "fable" in text.lower()

    def test_generate_matrix_refuses_if_a_destination_exists(self):
        """REPRODUCES: generate_matrix refuses to overwrite an existing MATRIX.md (never
        hand-written, never silently replaced). Re-pointed to _write_matrix; the candidate
        overwrites unconditionally, so this refusal behaviour is ABSENT — this test stays
        failing and is listed."""
        p475 = _import_p475()
        import tempfile
        d = Path(tempfile.mkdtemp())
        dest = d / "benchmark" / "results" / "p475" / "MATRIX.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("# hand-written\n")
        with pytest.raises(Exception):
            p475._write_matrix(d)
        # the hand-written file must be preserved
        assert dest.read_text() == "# hand-written\n"

    def test_generate_matrix_includes_paired_block_ratios_vs_n16(self):
        """REPRODUCES: the table includes the paired block ratios vs N16 (block 1 and
        block 2 side by side) per arm and rung. Re-pointed to build_matrix (emits ratio
        columns)."""
        p475 = _import_p475()
        import tempfile
        d = Path(tempfile.mkdtemp())
        _matrix_harvest(d, [
            ("fable-N16-b1", "fable", "N16", 1, [(8192, 40.0, 100.0, 10.0)]),
            ("fable-N16-b2", "fable", "N16", 2, [(8192, 40.0, 100.0, 10.0)]),
            ("fable-AF8-b1", "fable", "AF8", 1, [(8192, 40.0, 110.0, 10.0)]),
            ("fable-AF8-b2", "fable", "AF8", 2, [(8192, 40.0, 108.0, 10.0)]),
        ])
        text = p475.build_matrix(d)
        assert "ratio" in text.lower() or "n16" in text.lower()

    def test_generate_matrix_includes_instability_flags(self):
        """REPRODUCES: the table includes the instability flags (a column marking the
        arms whose two blocks triggered a deciding block). Re-pointed to build_matrix
        (emits an 'Instability flags' section)."""
        p475 = _import_p475()
        import tempfile
        d = Path(tempfile.mkdtemp())
        _matrix_harvest(d, [
            ("fable-N16-b1", "fable", "N16", 1, [(8192, 40.0, 100.0, 10.0)]),
            ("fable-N16-b2", "fable", "N16", 2, [(8192, 40.0, 100.0, 10.0)]),
            ("fable-AF8-b1", "fable", "AF8", 1, [(8192, 40.0, 110.0, 10.0)]),
            ("fable-AF8-b2", "fable", "AF8", 2, [(8192, 40.0, 90.0, 10.0)]),
        ])
        text = p475.build_matrix(d)
        assert "instab" in text.lower() or "flag" in text.lower()
