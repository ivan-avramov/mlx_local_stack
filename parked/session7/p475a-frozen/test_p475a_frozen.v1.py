"""P475a (SPEC v2, 2026-10-24): adversarial tests for the fork ``qualify`` KV-format arm — first delivery (red-first).

These tests pin the SPEC v2 interface and acceptance criteria for P475a before any implementation exists. They are
written to FAIL on the baseline (the functions / flag / attention-rule they exercise do not exist yet) and to pass
once the implementation lands. Nothing here loads a model or touches the GPU: every check is pure / mocked (CPU only).

Scope (from ``docs/specs/p475a-qualify-kv-arm.md`` v2):

* ``registry_states.classify_kv_arm(text, fixture, entry) -> (frozenset off, dict kv_delta) | None`` for all five KV
  arms (N16 / AF8 / TQ8 / AF4 / TQ4) x both picks (``Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`` and
  ``Qwen3.8-27B-mlx-uniform-4bit``), built from the pruned sibling registry / the golden fixture; every refusal case;
  the empty-delta == ``classify`` identity.
* ``qualify.py --kv-arm`` refusals (two entries, ``--predictor on``, a non-KV change, ``quantized_kv_start != 0``);
  the report field ``kv_arm``; the reference block ``label`` / ``comparable``; no ``classify`` path left under
  ``--kv-arm`` (the ``mtp_off`` check uses the arm's off set); the no-flag path unchanged.
* The attention rule (affine arms of the ``fused_v1`` entry pass with ``sdpa_forced == 0``; native / TurboQuant arms
  require forced calls) through the real ``request_problems`` function; today's no-flag behaviour unchanged.

Assumptions beyond what the spec fixes (stated here per the brief): the CLI flag is spelled ``--kv-arm`` (a
``store_true`` flag); ``classify_kv_arm`` lives in ``dev/p369_phase2/registry_states.py``; the report's KV-arm block
is recorded under the key ``kv_arm`` at the top level of the report dict with shape ``{"entry": <name>, "delta": <kv_delta>}``;
the reference block's label is the literal string ``"non-comparable: KV arm"``. These names/shapes are the ones the
spec's prose names; any other choice is a deviation the second delivery revisits.

Each test states its class in a leading comment:

* ``reproduces a failure the spec fixes`` — a test that fails on the baseline and is made green by the spec's change.
* ``preserves an invariant`` — a test that pins behaviour the spec requires to stay unchanged.
* ``exercises new behaviour`` — a test that drives a new code path the spec introduces.
"""

import argparse
import json
import sys
from pathlib import Path

import pytest

DEV = Path(__file__).resolve().parents[2] / "dev"
sys.path.insert(0, str(DEV))

from p369_phase2 import qualify  # noqa: E402
from p369_phase2 import registry_states as rs  # noqa: E402
from p369_phase2 import kvmanifest  # noqa: E402

from mlx_vlm.tests import test_p415_qualify as t415  # noqa: E402

FABLE = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
UNIFORM = "Qwen3.8-27B-mlx-uniform-4bit"
PICKS = (FABLE, UNIFORM)
FIXTURE = rs.fixture_text(Path(__file__).resolve().parent / "fixtures")
ALL_OFF = rs.apply(FIXTURE, frozenset(rs.ENTRY_OFF))
VENV_BIN = Path("/stack/.venv/bin")

# The five KV arms (P475 matrix): (name, kv_bits, kv_quant_scheme).
ARMS = (
    ("N16", 0, "turboquant"),  # native16 (kv_bits 0 -> native; scheme inert)
    ("AF8", 8, "uniform"),  # affine 8-bit
    ("TQ8", 8, "turboquant"),  # TurboQuant 8-bit
    ("AF4", 4, "uniform"),  # affine 4-bit
    ("TQ4", 4, "turboquant"),  # TurboQuant 4-bit
)
KV_ARM_KEYS = ("kv_bits", "kv_quant_scheme")


# ------------------------------------------------------------------ helpers
def _set_kv(text, entry, kv_bits, kv_quant_scheme):
    """Return ``text`` with ``entry``'s ``kv_bits`` / ``kv_quant_scheme`` value lines replaced.

    Uses the YAML-structure span (``rs._span``) so only the named entry's block is touched; the rest of the registry
    is preserved byte-for-byte (comments are inert to ``classify``).
    """
    lines = text.split("\n")
    start, end = rs._span(lines, entry)
    for i in range(start, end):
        stripped = lines[i].lstrip()
        indent = lines[i][: len(lines[i]) - len(stripped)]
        if stripped.startswith("kv_bits:"):
            lines[i] = f"{indent}kv_bits: {kv_bits}"
        elif stripped.startswith("kv_quant_scheme:"):
            lines[i] = f"{indent}kv_quant_scheme: {kv_quant_scheme}"
    return "\n".join(lines)


def _set_quantized_kv_start(text, entry, value):
    lines = text.split("\n")
    start, end = rs._span(lines, entry)
    for i in range(start, end):
        stripped = lines[i].lstrip()
        indent = lines[i][: len(lines[i]) - len(stripped)]
        if stripped.startswith("quantized_kv_start:"):
            lines[i] = f"{indent}quantized_kv_start: {value}"
    return "\n".join(lines)


def _arm_text(entry, kv_bits, kv_quant_scheme, base=ALL_OFF):
    """An arm registry: ``base`` (an accepted state) with ``entry``'s KV keys set to the arm's values."""
    return _set_kv(base, entry, kv_bits, kv_quant_scheme)


def _fixture_kv(entry):
    """The fixture's (kv_bits, kv_quant_scheme) for ``entry`` (the arm's reference values)."""
    s = rs.settings(FIXTURE)[entry]
    return s.get("kv_bits"), s.get("kv_quant_scheme")


def _expected_delta(entry, kv_bits, kv_quant_scheme):
    """The expected ``kv_delta`` dict ``{key: (fixture value, arm value)}`` for the arm."""
    fb, fs = _fixture_kv(entry)
    delta = {}
    if fb != kv_bits:
        delta["kv_bits"] = (fb, kv_bits)
    if fs != kv_quant_scheme:
        delta["kv_quant_scheme"] = (fs, kv_quant_scheme)
    return delta


# ------------------------------------------------------------------ AC1: classify_kv_arm
class TestClassifyKvArm:
    """AC1: ``classify_kv_arm`` unit tests (red first)."""

    @pytest.mark.parametrize("entry", PICKS, ids=lambda e: e.split("-")[0])
    @pytest.mark.parametrize("arm", ARMS, ids=lambda a: a[0])
    def test_each_arm_for_each_pick_is_accepted_with_the_right_delta(self, entry, arm):
        # reproduces a failure the spec fixes
        # Each of N16/AF8/TQ8/AF4/TQ4 for each of the two picks is accepted with the right delta.
        name, kv_bits, kv_quant_scheme = arm
        text = _arm_text(entry, kv_bits, kv_quant_scheme)
        got = rs.classify_kv_arm(text, FIXTURE, entry)
        assert got is not None, f"{entry}/{name}: classify_kv_arm refused a valid arm"
        off, delta = got
        assert off == frozenset(rs.ENTRY_OFF), f"{entry}/{name}: off={off}"
        assert delta == _expected_delta(entry, kv_bits, kv_quant_scheme), (
            f"{entry}/{name}: delta={delta}"
        )

    @pytest.mark.parametrize("entry", PICKS, ids=lambda e: e.split("-")[0])
    def test_the_empty_delta_arm_equals_classify(self, entry):
        # preserves an invariant
        # The arm whose KV keys match the fixture (empty delta) is identical to ``classify``.
        fb, fs = _fixture_kv(entry)
        text = _arm_text(entry, fb, fs)
        got = rs.classify_kv_arm(text, FIXTURE, entry)
        assert got is not None
        off, delta = got
        assert delta == {}
        assert off == rs.classify(text, FIXTURE)

    def test_a_second_entry_changed_refuses(self):
        # reproduces a failure the spec fixes
        # Two entries' KV keys changed -> None (only the ONE entry under test may differ).
        text = _arm_text(FABLE, 8, "uniform")
        text = _set_kv(text, UNIFORM, 8, "uniform")
        assert rs.classify_kv_arm(text, FIXTURE, FABLE) is None

    def test_a_non_kv_key_changed_refuses(self):
        # reproduces a failure the spec fixes
        # A non-KV key on the entry (prefill_step_size) changed -> None.
        text = _arm_text(FABLE, 8, "uniform")
        lines = text.split("\n")
        start, end = rs._span(lines, FABLE)
        for i in range(start, end):
            if lines[i].lstrip().startswith("prefill_step_size:"):
                lines[i] = lines[i].replace("512", "1024")
        text = "\n".join(lines)
        assert rs.classify_kv_arm(text, FIXTURE, FABLE) is None

    def test_quantized_kv_start_nonzero_refuses(self):
        # reproduces a failure the spec fixes
        # ``quantized_kv_start != 0`` on the entry -> None (the spec: must stay 0).
        text = _arm_text(FABLE, 8, "uniform")
        text = _set_quantized_kv_start(text, FABLE, 5000)
        assert rs.classify_kv_arm(text, FIXTURE, FABLE) is None

    def test_an_mtp_key_plus_kv_change_outside_the_16_states_refuses(self):
        # reproduces a failure the spec fixes
        # A PARTIAL MTP-key change on the entry (some but not all of its MTP keys uncommented — outside the 16 states,
        # which require all-or-none) PLUS a KV change on the same entry: the base is not an accepted state, so
        # ``classify_kv_arm`` returns None. (A FULL MTP-ON + KV change would be an accepted state + KV delta and is
        # accepted; that case is covered by ``test_each_arm_for_each_pick_is_accepted_with_the_right_delta`` with the
        # all-ON base.)
        text = _arm_text(FABLE, 8, "uniform")  # all-OFF base + Fable KV change (an accepted state + KV delta)
        # Partial MTP change: uncomment draft_kind only (leave mtp_verify_scan and draft_model commented).
        lines = text.split("\n")
        start, end = rs._span(lines, FABLE)
        for i in range(start, end):
            if lines[i] == rs.ENTRY_OFF[FABLE][1][1]:  # the commented draft_kind line
                lines[i] = rs.ENTRY_OFF[FABLE][1][0]  # restore the uncommented draft_kind line
                break
        text = "\n".join(lines)
        assert rs.classify(text, FIXTURE) is None  # the partial MTP change is outside the 16 states
        assert rs.classify_kv_arm(text, FIXTURE, FABLE) is None

    def test_an_unknown_entry_refuses(self):
        # reproduces a failure the spec fixes
        # An entry name not in the registry -> None.
        assert rs.classify_kv_arm(ALL_OFF, FIXTURE, "no-such-entry") is None


# ------------------------------------------------------------------ AC2: qualify --kv-arm driver
def _good_arm_job(entry, kv_bits, kv_quant_scheme):
    """A ``run_job`` whose record matches the arm's expected manifest and sdpa-forced rule (so the entry COMPLETED)."""
    def run_job(job, *a, **k):
        rec, _ = _arm_record(entry, kv_bits, kv_quant_scheme,
                             sdpa_forced=_arm_forced(entry, kv_bits, kv_quant_scheme))
        return dict(requests=[dict(qualify=rec)])
    return run_job


def _arm_forced(entry, kv_bits, kv_quant_scheme):
    """The sdpa_forced value the arm's attention rule requires (for fused_v1: >0 iff a native-KV leaf)."""
    if entry != FABLE:
        return 0  # default attention: never forced
    manifest = _arm_manifest(entry, kv_bits, kv_quant_scheme)
    has_native = any(o.get("kind") == "native" for o in manifest)
    return 640 if has_native else 0


def _drive_kv_arm(tmp_path, monkeypatch, *, entry, kv_bits, kv_quant_scheme,
                  classify_kv_arm_return, run_job=None, refs=None):
    """Drive ``qualify`` with ``--kv-arm`` for one entry, mocking the world like ``t415._drive``.

    ``classify_kv_arm_return`` is what the mocked ``rs.classify_kv_arm`` returns (``None`` for refusal tests). The live
    registry is the arm text (the all-OFF base with the entry's KV keys changed); ``classify`` is mocked too so we can
    assert it is NOT called under ``--kv-arm``. ``refs`` (optional) pins ``load_references`` to a fixed table. Returns
    ``(exit_code, report, classify_calls)``.
    """
    from p369_phase2 import orchestrate

    block = dict(t415.FABLE_ENTRY if entry == FABLE else t415.STATIC_ENTRY,
                 name=entry, hf_path=f"caslca/{entry}")
    block["kv_bits"] = kv_bits
    block["kv_quant_scheme"] = kv_quant_scheme
    block["quantized_kv_start"] = 0
    if entry == FABLE:
        block["attention_policy"] = "fused_v1"

    registry = _arm_text(entry, kv_bits, kv_quant_scheme)
    classify_calls = []

    if run_job is None:
        def run_job(job, *a, **k):
            rec = t415._record()
            return dict(requests=[dict(qualify=rec)])

    def _classify(text, fx):
        classify_calls.append(text)
        return frozenset(rs.ENTRY_OFF)

    def _classify_kv_arm(text, fx, ent):
        assert ent == entry
        return classify_kv_arm_return

    for name, value in dict(
        acquire_lock=lambda lock: 3,
        release_lock=lambda fd: None,
        lock_path=lambda env: tmp_path / ".lock",
        preflight=lambda args, out: dict(problems=[]),
        read_registry=lambda p: registry,
        sha256_file=lambda p: "s",
        fork_versions=lambda f: {"mlx": "0.32.3"},
        overlay_registry=lambda text, name, fixture: (text, True),
        weights_record=lambda m: dict(revision="r", files={}),
        worker_env=lambda env: env,
        run_job=run_job,
    ).items():
        monkeypatch.setattr(orchestrate, name, value)
    monkeypatch.setattr(orchestrate, "Monitor", t415._NullMonitor)
    monkeypatch.setattr(rs, "fixture_text", lambda d: FIXTURE)
    monkeypatch.setattr(rs, "classify", _classify)
    monkeypatch.setattr(rs, "classify_kv_arm", _classify_kv_arm, raising=False)
    if refs is None:
        monkeypatch.setattr(qualify, "load_references", lambda p, **k: {})
    else:
        monkeypatch.setattr(qualify, "load_references", lambda p, **k: refs)
    monkeypatch.setattr(qualify, "_resolve_ref", lambda path, ref: "a" * 40)
    monkeypatch.setattr(
        qualify, "_tree_state",
        lambda fork, stack: dict(fork_head="a" * 40, fork_clean=True, stack_head="s" * 40),
    )
    monkeypatch.setattr(
        qualify, "console_script_info",
        lambda stack: dict(shebang=str(Path(stack) / ".venv" / "bin" / "python"),
                           entry="mlx_vlm.server:main", stack_mlx_vlm="x"),
    )
    monkeypatch.setattr(qualify, "_last_tick_age", lambda p: 1.0)
    monkeypatch.setattr(qualify, "_pmset_log", lambda: (0, t415.PMSET))
    monkeypatch.setattr(qualify, "interference", lambda o: dict(ok=True, why=None))
    monkeypatch.setattr(qualify, "binding_problems", lambda *a: [])
    monkeypatch.setattr(qualify, "_git_head", lambda p: "h")

    def full_command(stack, path, name):
        cmd = t415._cmd(block)
        return [str(Path(stack) / ".venv" / "bin" / "mlx_vlm.server"), *cmd[1:]], "m"

    monkeypatch.setattr(qualify, "full_command", full_command)
    monkeypatch.setattr("yaml.safe_load", lambda text: dict(models=[block]))
    monkeypatch.setattr("time.sleep", lambda s: None)

    args = argparse.Namespace(
        stack_root=str(tmp_path / "stack"),
        fork_root=str(tmp_path / "fork"),
        out=str(tmp_path / "run"),
        entry=[entry],
        p369_summary=None,
        idle_s=600.0,
        reviewed_head="a" * 40,
        predictor="off",
        kv_arm=True,
    )
    (tmp_path / "stack" / ".venv" / "bin").mkdir(parents=True)
    code = qualify.drive(args)
    return code, json.loads((tmp_path / "run" / "report.json").read_text()), classify_calls


class TestQualifyKvArmRefusals:
    """AC2: ``qualify --kv-arm`` refusal paths."""

    def test_two_entries_refuses(self, tmp_path, monkeypatch):
        # reproduces a failure the spec fixes
        # ``--kv-arm`` requires EXACTLY one ``--entry``; two entries must be refused before any work runs. Today's
        # ``drive`` has no ``--kv-arm`` check, so it does not raise SystemExit (the test is red); the implementation
        # adds the early refusal.
        from p369_phase2 import orchestrate
        for name, value in dict(
            acquire_lock=lambda lock: 3, release_lock=lambda fd: None,
            lock_path=lambda env: tmp_path / ".lock",
            preflight=lambda args, out: dict(problems=[]),
        ).items():
            monkeypatch.setattr(orchestrate, name, value)
        monkeypatch.setattr(qualify, "_resolve_ref", lambda path, ref: "a" * 40)
        # Mock the tree-state read so today's drive() does not crash on git before the (missing) refusal check.
        monkeypatch.setattr(
            qualify, "_tree_state",
            lambda fork, stack: dict(fork_head="a" * 40, fork_clean=True, stack_head="s" * 40),
        )
        args = argparse.Namespace(
            stack_root=str(tmp_path / "stack"), fork_root=str(tmp_path / "fork"),
            out=str(tmp_path / "run"), entry=[FABLE, UNIFORM], p369_summary=None,
            idle_s=600.0, reviewed_head="a" * 40, predictor="off", kv_arm=True,
        )
        with pytest.raises(SystemExit):
            qualify.drive(args)

    def test_predictor_on_refuses(self, tmp_path, monkeypatch):
        # reproduces a failure the spec fixes
        # ``--kv-arm`` with ``--predictor on`` is refused (the spec: requires ``--predictor off``). Today's ``drive``
        # has no ``--kv-arm`` check, so it does not raise SystemExit (the test is red).
        from p369_phase2 import orchestrate
        for name, value in dict(
            acquire_lock=lambda lock: 3, release_lock=lambda fd: None,
            lock_path=lambda env: tmp_path / ".lock",
            preflight=lambda args, out: dict(problems=[]),
        ).items():
            monkeypatch.setattr(orchestrate, name, value)
        monkeypatch.setattr(qualify, "_resolve_ref", lambda path, ref: "a" * 40)
        monkeypatch.setattr(
            qualify, "_tree_state",
            lambda fork, stack: dict(fork_head="a" * 40, fork_clean=True, stack_head="s" * 40),
        )
        args = argparse.Namespace(
            stack_root=str(tmp_path / "stack"), fork_root=str(tmp_path / "fork"),
            out=str(tmp_path / "run"), entry=[FABLE], p369_summary=None,
            idle_s=600.0, reviewed_head="a" * 40, predictor="on", kv_arm=True,
        )
        with pytest.raises(SystemExit):
            qualify.drive(args)

    def test_a_non_kv_change_refuses(self, tmp_path, monkeypatch):
        # reproduces a failure the spec fixes
        # ``classify_kv_arm`` returns None (a non-KV key changed) -> the run refuses at the gate (SystemExit). Today's
        # ``drive`` does not call ``classify_kv_arm``, so it does not refuse early (the test is red).
        with pytest.raises(SystemExit):
            _drive_kv_arm(
                tmp_path, monkeypatch, entry=FABLE, kv_bits=8, kv_quant_scheme="uniform",
                classify_kv_arm_return=None,
            )

    def test_quantized_kv_start_nonzero_refuses(self, tmp_path, monkeypatch):
        # reproduces a failure the spec fixes
        # ``classify_kv_arm`` returns None (quantized_kv_start != 0) -> the run refuses at the gate (SystemExit).
        with pytest.raises(SystemExit):
            _drive_kv_arm(
                tmp_path, monkeypatch, entry=FABLE, kv_bits=8, kv_quant_scheme="uniform",
                classify_kv_arm_return=None,
            )


class TestQualifyKvArmReport:
    """AC2: the report fields and the no-classify-path invariant."""

    def test_the_report_records_kv_arm_with_entry_and_delta(self, tmp_path, monkeypatch):
        # exercises new behaviour
        # The report gains ``kv_arm: {entry, delta}`` at the top level. Uses TQ8 (non-empty delta) with a matching record.
        delta = {"kv_bits": (0, 8)}
        code, report, _ = _drive_kv_arm(
            tmp_path, monkeypatch, entry=FABLE, kv_bits=8, kv_quant_scheme="turboquant",
            classify_kv_arm_return=(frozenset(rs.ENTRY_OFF), delta),
            run_job=_good_arm_job(FABLE, 8, "turboquant"),
        )
        assert code == 0, report
        assert report.get("kv_arm") == {"entry": FABLE, "delta": delta}

    def test_no_classify_call_remains_under_kv_arm(self, tmp_path, monkeypatch):
        # reproduces a failure the spec fixes
        # Under ``--kv-arm`` the gate AND the ``mtp_off`` check use ``classify_kv_arm``; ``classify`` is never called.
        delta = {"kv_bits": (0, 8)}
        code, report, classify_calls = _drive_kv_arm(
            tmp_path, monkeypatch, entry=FABLE, kv_bits=8, kv_quant_scheme="turboquant",
            classify_kv_arm_return=(frozenset(rs.ENTRY_OFF), delta),
            run_job=_good_arm_job(FABLE, 8, "turboquant"),
        )
        assert code == 0, report
        assert classify_calls == [], "classify was called under --kv-arm"

    def test_the_mtp_off_check_uses_the_arms_off_set(self, tmp_path, monkeypatch):
        # reproduces a failure the spec fixes
        # The ``mtp_off`` check reads the off set from ``classify_kv_arm`` (the arm's off set), not a separate
        # ``classify`` call. With the entry OFF in the arm's off set, the ``--predictor off`` arm passes; with it
        # absent, the run refuses.
        code, report, _ = _drive_kv_arm(
            tmp_path, monkeypatch, entry=FABLE, kv_bits=8, kv_quant_scheme="uniform",
            classify_kv_arm_return=(frozenset(rs.ENTRY_OFF), {"kv_bits": (0, 8)}),
            run_job=_good_arm_job(FABLE, 8, "uniform"),
        )
        assert code == 0, report["entries"][FABLE]["status"]

        code, report, _ = _drive_kv_arm(
            tmp_path, monkeypatch, entry=FABLE, kv_bits=8, kv_quant_scheme="uniform",
            classify_kv_arm_return=(frozenset(rs.ENTRY_OFF) - {FABLE}, {"kv_bits": (0, 8)}),
            run_job=_good_arm_job(FABLE, 8, "uniform"),
        )
        assert code != 0
        assert any("serves" in p and "MTP-ON" in p
                   for p in report["entries"][FABLE].get("problems", []))

    def test_the_reference_block_is_labelled_non_comparable(self, tmp_path, monkeypatch):
        # exercises new behaviour
        # The reference block gains ``label: "non-comparable: KV arm"`` and ``comparable: false`` (C199), never a refusal.
        refs = {
            FABLE: dict(
                peak_gb=37.97, source="x", source_path="docs/x.md",
                source_blob="0" * 40, fingerprint={},
            )
        }
        delta = {"kv_bits": (0, 8)}
        code, report, _ = _drive_kv_arm(
            tmp_path, monkeypatch, entry=FABLE, kv_bits=8, kv_quant_scheme="turboquant",
            classify_kv_arm_return=(frozenset(rs.ENTRY_OFF), delta),
            run_job=_good_arm_job(FABLE, 8, "turboquant"), refs=refs,
        )
        assert code == 0, report
        ref = report["entries"][FABLE].get("reference")
        assert ref is not None, report["entries"][FABLE]
        assert ref.get("comparable") is False
        assert ref.get("label") == "non-comparable: KV arm"


class TestQualifyNoFlagUnchanged:
    """AC2: the no-flag path is byte-for-byte today's behaviour (tests pin it)."""

    def test_the_no_flag_path_uses_classify_not_classify_kv_arm(self, tmp_path, monkeypatch):
        # preserves an invariant
        # Without ``--kv-arm`` the gate uses ``classify`` (today's behaviour); ``classify_kv_arm`` is never called,
        # and the report carries no ``kv_arm`` block. Uses the MTP-OFF block + OFF record (predictor=off -> arm
        # mtp_off) so the entry completes today exactly as in ``test_p426_qualify_predictor._drive_off``.
        from p369_phase2 import orchestrate
        kv_arm_calls = []

        off_entry = {
            k: v for k, v in t415.FABLE_ENTRY.items()
            if k not in ("draft_kind", "draft_model", "mtp_verify_scan")
        }
        on_cmd = t415._cmd(t415.FABLE_ENTRY)
        drafter_flags = {"--mtp-verify-scan", "--draft-kind", "--draft-model"}
        off_cmd = [
            a for i, a in enumerate(on_cmd)
            if a not in drafter_flags and (i == 0 or on_cmd[i - 1] not in drafter_flags)
        ]
        registry = rs.apply(FIXTURE, frozenset(rs.ENTRY_OFF))

        def _classify_kv_arm(text, fx, ent):
            kv_arm_calls.append(ent)
            return (frozenset(rs.ENTRY_OFF), {})

        def run_job(job, *a, **k):
            rec = t415._record(drafter_live_checks=None)
            return dict(requests=[dict(qualify=rec)])

        for name, value in dict(
            acquire_lock=lambda lock: 3, release_lock=lambda fd: None,
            lock_path=lambda env: tmp_path / ".lock",
            preflight=lambda args, out: dict(problems=[]),
            read_registry=lambda p: registry,
            sha256_file=lambda p: "s",
            fork_versions=lambda f: {"mlx": "0.32.3"},
            overlay_registry=lambda text, name, fixture: (text, True),
            weights_record=lambda m: dict(revision="r", files={}),
            worker_env=lambda env: env,
            run_job=run_job,
        ).items():
            monkeypatch.setattr(orchestrate, name, value)
        monkeypatch.setattr(orchestrate, "Monitor", t415._NullMonitor)
        monkeypatch.setattr(rs, "fixture_text", lambda d: FIXTURE)
        monkeypatch.setattr(rs, "classify", lambda text, fx: frozenset(rs.ENTRY_OFF))
        monkeypatch.setattr(rs, "classify_kv_arm", _classify_kv_arm, raising=False)
        monkeypatch.setattr(qualify, "load_references", lambda p, **k: {})
        monkeypatch.setattr(qualify, "_resolve_ref", lambda path, ref: "a" * 40)
        monkeypatch.setattr(
            qualify, "_tree_state",
            lambda fork, stack: dict(fork_head="a" * 40, fork_clean=True, stack_head="s" * 40),
        )
        monkeypatch.setattr(
            qualify, "console_script_info",
            lambda stack: dict(shebang=str(Path(stack) / ".venv" / "bin" / "python"),
                               entry="mlx_vlm.server:main", stack_mlx_vlm="x"),
        )
        monkeypatch.setattr(qualify, "_last_tick_age", lambda p: 1.0)
        monkeypatch.setattr(qualify, "_pmset_log", lambda: (0, t415.PMSET))
        monkeypatch.setattr(qualify, "interference", lambda o: dict(ok=True, why=None))
        monkeypatch.setattr(qualify, "binding_problems", lambda *a: [])
        monkeypatch.setattr(qualify, "_git_head", lambda p: "h")
        monkeypatch.setattr(
            qualify, "full_command",
            lambda stack, path, name: ([str(Path(stack) / ".venv" / "bin" / "mlx_vlm.server"),
                                       *off_cmd[1:]], "m"),
        )
        monkeypatch.setattr("yaml.safe_load", lambda text: dict(models=[off_entry]))
        monkeypatch.setattr("time.sleep", lambda s: None)

        args = argparse.Namespace(
            stack_root=str(tmp_path / "stack"), fork_root=str(tmp_path / "fork"),
            out=str(tmp_path / "run"), entry=[FABLE], p369_summary=None,
            idle_s=600.0, reviewed_head="a" * 40, predictor="off", kv_arm=False,
        )
        (tmp_path / "stack" / ".venv" / "bin").mkdir(parents=True)
        code = qualify.drive(args)
        report = json.loads((tmp_path / "run" / "report.json").read_text())
        assert code == 0, report
        assert kv_arm_calls == [], "classify_kv_arm was called without --kv-arm"
        assert "kv_arm" not in report, report

# ------------------------------------------------------------------ AC0: the attention rule through request_problems
def _arm_entry(entry, kv_bits, kv_quant_scheme):
    """A registry entry dict for the arm (in ``expected_config``'s shape)."""
    base = dict(t415.FABLE_ENTRY if entry == FABLE else t415.STATIC_ENTRY)
    base["name"] = entry
    base["hf_path"] = f"caslca/{entry}"
    base["kv_bits"] = kv_bits
    base["kv_quant_scheme"] = kv_quant_scheme
    base["quantized_kv_start"] = 0
    return base


def _arm_expected(entry, kv_bits, kv_quant_scheme):
    return qualify.expected_config(_arm_entry(entry, kv_bits, kv_quant_scheme))


def _arm_template():
    """A 4-leaf template with 2 native KV leaves at paths 1 and 3 (> 2 top-level entries, so TurboQuant retains the
    last native leaf at path 3)."""
    return [
        dict(path="0", kind="ArraysCache", cls="ArraysCache", batch=False),
        dict(path="1", kind="native", cls="KVCache", batch=False),
        dict(path="2", kind="ArraysCache", cls="ArraysCache", batch=False),
        dict(path="3", kind="native", cls="KVCache", batch=False),
    ]


def _arm_manifest(entry, kv_bits, kv_quant_scheme):
    """The expected per-layer manifest for the arm (what ``kvmanifest.expected_manifest`` builds)."""
    expected = _arm_expected(entry, kv_bits, kv_quant_scheme)
    return kvmanifest.expected_manifest(_arm_template(), qualify.expected_kv(expected))


def _arm_record(entry, kv_bits, kv_quant_scheme, *, sdpa_forced):
    """A measured-request record for the arm, with the arm's expected manifest and the given ``sdpa_forced``."""
    expected = _arm_expected(entry, kv_bits, kv_quant_scheme)
    manifest = _arm_manifest(entry, kv_bits, kv_quant_scheme)
    template = _arm_template()
    # capacities: every KV leaf at the registry floor
    caps = {o["path"]: expected["prealloc"] for o in manifest
            if o.get("kind") in ("tq", "affine", "native")}
    rec = t415._record(
        sdpa_forced=sdpa_forced,
        manifest=manifest,
        template=template,
        capacities_by_path=caps,
    )
    # The arm's prompt_tokens / cache-limit must match the arm's expected (cap and prefill step are the same as the
    # fixture's for these entries, so the defaults in _record already match; keep the memory cache limit aligned).
    rec["memory"] = dict(
        rec["memory"],
        set_cache_limit=[qualify.expected_cache_limit(24, expected)],
    )
    return rec, expected


class TestAttentionRuleFusedV1:
    """AC0: the attention rule for the ``fused_v1`` entry (Fable) through the real ``request_problems``."""

    @pytest.mark.parametrize("arm", [a for a in ARMS if a[0] in ("AF8", "AF4")],
                             ids=lambda a: a[0])
    def test_affine_arms_pass_with_sdpa_forced_zero(self, arm):
        # reproduces a failure the spec fixes
        # AF8 / AF4 of the fused_v1 entry: the expected manifest has NO native-KV attention leaf, so sdpa_forced == 0
        # passes the full request_problems path. Today's rule (fused_v1 -> forced > 0) fails this.
        _, kv_bits, kv_quant_scheme = arm
        rec, expected = _arm_record(FABLE, kv_bits, kv_quant_scheme, sdpa_forced=0)
        problems = qualify.request_problems(rec, expected)
        assert not any("sdpa_forced" in p for p in problems), (
            f"{arm[0]}: affine arm must pass with sdpa_forced==0; problems={problems}")

    @pytest.mark.parametrize("arm", [a for a in ARMS if a[0] in ("AF8", "AF4")],
                             ids=lambda a: a[0])
    def test_affine_arms_refuse_forced_calls(self, arm):
        # reproduces a failure the spec fixes
        # AF8 / AF4 of the fused_v1 entry: sdpa_forced > 0 is now a problem (the affine arms take the quantized-attention
        # path, which must not force the native SDPA kernel).
        _, kv_bits, kv_quant_scheme = arm
        rec, expected = _arm_record(FABLE, kv_bits, kv_quant_scheme, sdpa_forced=640)
        problems = qualify.request_problems(rec, expected)
        assert any("sdpa_forced" in p for p in problems), (
            f"{arm[0]}: affine arm must refuse sdpa_forced>0; problems={problems}")

    @pytest.mark.parametrize("arm", [a for a in ARMS if a[0] in ("N16", "TQ8", "TQ4")],
                             ids=lambda a: a[0])
    def test_native_and_turboquant_arms_require_forced_calls(self, arm):
        # preserves an invariant
        # N16 / TQ8 / TQ4 of the fused_v1 entry: the expected manifest has a native-KV attention leaf, so sdpa_forced > 0
        # is required; sdpa_forced == 0 fails. Today's rule (fused_v1 -> forced > 0) agrees; the new rule keeps it.
        _, kv_bits, kv_quant_scheme = arm
        rec, expected = _arm_record(FABLE, kv_bits, kv_quant_scheme, sdpa_forced=0)
        problems = qualify.request_problems(rec, expected)
        assert any("sdpa_forced" in p for p in problems), (
            f"{arm[0]}: native/TQ arm must require sdpa_forced>0; problems={problems}")

    @pytest.mark.parametrize("arm", [a for a in ARMS if a[0] in ("N16", "TQ8", "TQ4")],
                             ids=lambda a: a[0])
    def test_native_and_turboquant_arms_pass_with_forced_calls(self, arm):
        # preserves an invariant
        # N16 / TQ8 / TQ4 of the fused_v1 entry pass the full request_problems path with sdpa_forced > 0 (today and after).
        _, kv_bits, kv_quant_scheme = arm
        rec, expected = _arm_record(FABLE, kv_bits, kv_quant_scheme, sdpa_forced=640)
        problems = qualify.request_problems(rec, expected)
        assert not any("sdpa_forced" in p for p in problems), (
            f"{arm[0]}: native/TQ arm must pass with sdpa_forced>0; problems={problems}")


class TestAttentionRuleNoFlagUnchanged:
    """AC0: today's no-flag behaviour is unchanged for the committed registries."""

    def test_the_committed_fable_registry_requires_forced_calls(self):
        # preserves an invariant
        # The committed Fable registry (N16, fused_v1): the expected manifest has native leaves, so sdpa_forced > 0
        # is required (today's rule, unchanged under the new rule).
        rec, expected = _arm_record(FABLE, 0, "turboquant", sdpa_forced=0)
        problems = qualify.request_problems(rec, expected)
        assert any("sdpa_forced" in p for p in problems), problems
        rec, expected = _arm_record(FABLE, 0, "turboquant", sdpa_forced=640)
        problems = qualify.request_problems(rec, expected)
        assert not any("sdpa_forced" in p for p in problems), problems

    def test_the_committed_uniform_registry_requires_no_forced_calls(self):
        # preserves an invariant
        # The committed Uniform registry (TQ4, default attention): not fused_v1, so sdpa_forced == 0 is required
        # (today's rule, unchanged).
        rec, expected = _arm_record(UNIFORM, 4, "turboquant", sdpa_forced=0)
        problems = qualify.request_problems(rec, expected)
        assert not any("sdpa_forced" in p for p in problems), problems
        rec, expected = _arm_record(UNIFORM, 4, "turboquant", sdpa_forced=640)
        problems = qualify.request_problems(rec, expected)
        assert any("sdpa_forced" in p for p in problems), problems
