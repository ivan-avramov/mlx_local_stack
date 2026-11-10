"""M72 1.2 (spec v1.2): GPU tests of `benchmark/spikes/m72_tq4_probe.py` (`--mode mma`). The probe imports MLX and the fork at
load, so this module is skipped in the stack venv (no MLX) and runs in the fork venv with this copy's fork on the path:

    ./fe_test.sh stack-gpu bench/tests/test_m72_mma_probe_gpu.py

Gates: the probe's power gate (140 W / 28 V, battery > 20 %) and idle-GPU gate read the box; tests that call `main()` replace
`power_state` and `m72_gates.gpu_idle_ok` so they do not depend on box state or on another helper using the GPU. Nothing else in
`main()` is patched except where a test says so (the accuracy sweep and the checkpoint measurement are stubbed or made to raise).
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import numpy as np
import pytest

mx = pytest.importorskip("mlx.core")
pytest.importorskip("mlx_vlm")
pytestmark = pytest.mark.skipif(not mx.metal.is_available(), reason="Metal GPU required")
import mlx_vlm  # noqa: E402

if not (Path(mlx_vlm.__file__).resolve().parents[1] / "dev" / "m72_mma_verify.py").exists():
    pytest.skip("the importable mlx_vlm is not this copy's fork (run: ./fe_test.sh stack-gpu <file>)", allow_module_level=True)

SPIKES = Path(__file__).resolve().parents[2] / "spikes"
NQ, NKV, D = 24, 4, 256
R = NQ // NKV
DT = mx.bfloat16
FORWARD = ("native16", "tq4_production", "mq_best", "mma_tq4", "mma_n16")
GOOD_POWER = {"wattage": "140W", "voltage": "28000mV", "battery": "80%"}


@pytest.fixture(scope="module")
def probe():
    sys.path.insert(0, str(SPIKES))  # the probe imports its sibling m72_gates
    spec = importlib.util.spec_from_file_location("m72_tq4_probe", SPIKES / "m72_tq4_probe.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["m72_tq4_probe"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mv(probe):
    probe.fork_dev_module()  # puts the fork's dev/ on sys.path
    return probe.fork_mma_module()


# ------------------------------------------------------------------ independent reference
def ref_np(Kn, Vn, q, lengths, scale):
    qn = np.array(q.astype(mx.float32)) * np.float32(scale)
    out = np.zeros(qn.shape, np.float32)
    for h in range(NKV):
        for j, L in enumerate(lengths):
            s = (qn[0, h * R:(h + 1) * R, j, :] @ Kn[0, h, :L].T).astype(np.float64)
            s -= s.max(axis=-1, keepdims=True)
            p = np.exp(s)
            p /= p.sum(axis=-1, keepdims=True)
            out[0, h * R:(h + 1) * R, j, :] = p.astype(np.float32) @ Vn[0, h, :L]
    return out


def rel(out, ref):
    return float(np.max(np.abs(np.array(out.astype(mx.float32)) - ref)) / np.max(np.abs(ref)))


def planted_layout(probe, T, k, seed=0):
    """A TQ4 cache holding T + 1 tokens (the planted layout): token T is a bait key aligned with the queries, ~64 in norm,
    visible to no query of the block ending at T. A production read of T + 1 tokens is dominated by it."""
    lens = [T - k + 1 + j for j in range(k)]
    key = mx.random.key(seed)
    q = mx.random.normal((1, NQ, k, D), key=key).astype(DT)
    Kn = np.array(mx.random.normal((1, NKV, T + 1, D), key=mx.random.key(seed + 1)))
    Vn = np.array(mx.random.normal((1, NKV, T + 1, D), key=mx.random.key(seed + 2)))
    u = np.array(q.astype(mx.float32)).reshape(1, NKV, R, k, D).sum(axis=(2, 3))
    Kn[:, :, T, :] = 64.0 * u / np.linalg.norm(u, axis=-1, keepdims=True)
    K, V = mx.array(Kn).astype(DT), mx.array(Vn).astype(DT)
    cap = T + 255
    tq = probe.TurboQuantKVCache(bits=4, max_kv_size=cap, prealloc_tokens=cap)
    tq.update_and_fetch(K, V)
    mx.eval(tq.keys, tq.values)
    assert tq.offset == T + 1
    K16 = mx.concatenate([K, mx.zeros((1, NKV, cap - (T + 1), D), dtype=DT)], axis=2)
    V16 = mx.concatenate([V, mx.zeros((1, NKV, cap - (T + 1), D), dtype=DT)], axis=2)
    mx.eval(K16, V16)
    st = probe.tq_mod
    Kd = tq.key_codec.dequantize(st._slice_state(tq.keys, tq.offset)).astype(mx.float32)
    Vd = tq.value_codec.dequantize(st._slice_state(tq.values, tq.offset)).astype(mx.float32)
    mx.eval(Kd, Vd)
    return types.SimpleNamespace(q=q, lens=lens, tq=tq, K16=K16, V16=V16, Kd=np.array(Kd), Vd=np.array(Vd),
                                 K16n=np.array(K16.astype(mx.float32)), V16n=np.array(V16.astype(mx.float32)))


T_PLANT = 8193  # > 2048: the 2-pass decode path; not a multiple of any tile


# ================================================================== 1. production comparison reads exactly [0, lengths[j])
# [instrument positive] the bait is visible to a read of T + 1 tokens: the fp32 reference over lengths + 1 differs from the one
# over lengths by O(1) (so a production path that reads the extra token cannot look right)
@pytest.mark.parametrize("k", (1, 3))
def test_the_planted_bait_is_visible_to_an_over_read(probe, k):
    c = planted_layout(probe, T_PLANT, k)
    true = ref_np(c.Kd, c.Vd, c.q, c.lens, probe.SCALE)
    over = ref_np(c.Kd, c.Vd, c.q, [L + 1 for L in c.lens], probe.SCALE)
    assert np.max(np.abs(over - true)) / np.max(np.abs(true)) > 0.1


# [reproduces a failure the spec fixes] the TQ4 production reference, on a cache holding more tokens than lengths[-1], has
# rel error ~ bf16 rounding against the independent fp32 reference (the v1.1 candidate had ~1.7 at k = 1)
@pytest.mark.parametrize("k", (1, 2, 3, 4, 5))
def test_tq4_production_reference_reads_exactly_the_prefix(probe, k):
    c = planted_layout(probe, T_PLANT, k)
    ref = ref_np(c.Kd, c.Vd, c.q, c.lens, probe.SCALE)
    err = rel(probe.tq_production(c.tq, c.q, c.lens), ref)
    assert err < 8e-3, f"TQ4 production rel error {err:.3g} (k={k}): it read tokens beyond lengths[-1]"


# [preserves an invariant] the native16 production reference slices K / V to lengths[j] (full-cap arrays holding more)
@pytest.mark.parametrize("k", (1, 3))
def test_native16_production_reference_reads_exactly_the_prefix(probe, k):
    c = planted_layout(probe, T_PLANT, k)
    ref = ref_np(c.K16n, c.V16n, c.q, c.lens, probe.SCALE)
    err = rel(probe.n16_production(c.q, c.K16, c.V16, c.lens), ref)
    assert err < 8e-3, f"native16 production rel error {err:.3g} (k={k})"


# [instrument validation] the probe's own fp32 reference agrees with the independent numpy one
@pytest.mark.parametrize("k", (1, 3))
def test_probe_reference_agrees_with_the_independent_reference(probe, k):
    c = planted_layout(probe, T_PLANT, k)
    ref = ref_np(c.Kd, c.Vd, c.q, c.lens, probe.SCALE)
    mine = probe.ref_attention(c.q, mx.array(c.Kd), mx.array(c.Vd), c.lens)
    assert rel(mine, ref) < 1e-4


# [reproduces a failure the spec fixes, end to end] the recorded rows: production rel error and A1 on the planted layout, k = 1
@pytest.mark.parametrize("k", (1, 3))
def test_recorded_accuracy_uses_a_sane_production_error_on_the_planted_layout(probe, mv, k):
    c = planted_layout(probe, T_PLANT, k)
    ref_tq = probe.ref_attention(c.q, mx.array(c.Kd), mx.array(c.Vd), c.lens)
    ref16 = probe.ref_attention(c.q, c.K16, c.V16, c.lens)
    acc = probe.mma_both_arms(mv, c.tq, c.K16, c.V16, c.q, c.lens, ref_tq, ref16)
    for arm in ("mma_tq4", "mma_n16"):
        a = acc[arm]
        assert a["prod_rel_err"] < 8e-3, (arm, a)
        assert a["finite"] and a["pass"], (arm, a)


# ================================================================== A1 floor 2^-12 in the probe's judge (spec v1.2)
def _a1_case(probe, delta, prod_rel):
    ref = mx.random.uniform(-0.9, 0.9, (1, NQ, 1, D), key=mx.random.key(5))
    ref[0, 0, 0, 0] = 1.0  # max |ref| = 1: rel error = the perturbation
    out = ref + 0.0
    out[0, 1, 0, 3] = ref[0, 1, 0, 3] + delta
    return probe.a1(out, ref, prod_rel)


def test_a1_floor_is_two_to_the_minus_twelve(probe):
    assert probe.A1_FLOOR == 2.0 ** -12


# bound = 2 x max(prod, 2^-12): with a (near) exact production path the bound is 2 x 2^-12, not 2 x 2^-8
@pytest.mark.parametrize("c,ok", [(1.8, True), (2.3, False), (8.0, False)])
def test_a1_bound_uses_the_two_to_the_minus_twelve_floor(probe, c, ok):
    assert _a1_case(probe, c * 2.0 ** -12, 0.0)["pass"] is ok
    assert _a1_case(probe, c * 2.0 ** -12, 2.0 ** -14)["pass"] is ok  # still under the floor: same bound


# above the floor the production error sets the bound
@pytest.mark.parametrize("c,ok", [(1.8, True), (2.3, False)])
def test_a1_bound_scales_with_the_production_error(probe, c, ok):
    prod = 2.0 ** -9
    assert _a1_case(probe, c * prod, prod)["pass"] is ok


# ================================================================== 3. --arm-order / --mode on the real parser
def run_main(probe, argv):
    old = sys.argv
    sys.argv = ["m72_tq4_probe.py", *argv]
    try:
        probe.main()
    finally:
        sys.argv = old


# Behaviour, not help text (amended for the p2s mode): every mode (full / mq / mma stay; p2s added) and both arm orders are
# accepted by the parser (a bad power state then refuses with exit 3 before any work, so exit 3 proves the arguments parsed),
# and an unknown mode or order exits 2 (also in test_parser_rejects_unknown_choices below).
@pytest.mark.parametrize("mode", ("full", "mq", "mma", "p2s"))
@pytest.mark.parametrize("order", ("forward", "reverse"))
def test_parser_choices(probe, monkeypatch, mode, order):
    monkeypatch.setattr(probe, "power_state", lambda: {"wattage": "60W", "voltage": "20000mV", "battery": "80%"})
    with pytest.raises(SystemExit) as e:
        run_main(probe, ["--out", "/nonexistent/x.json", "--mode", mode, "--arm-order", order])
    assert e.value.code == 3


@pytest.mark.parametrize("argv", [["--arm-order", "sideways"], ["--mode", "nope"]])
def test_parser_rejects_unknown_choices(probe, argv, capsys):
    with pytest.raises(SystemExit) as e:
        run_main(probe, ["--out", "/nonexistent/x.json", *argv])
    assert e.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


# ================================================================== gates for tests that run main()
@pytest.fixture()
def gates_open(probe, monkeypatch):
    monkeypatch.setattr(probe, "power_state", lambda: dict(GOOD_POWER))
    monkeypatch.setattr(probe.m72_gates, "gpu_idle_ok", lambda g: True)


def forbid(name):
    def boom(*a, **kw):
        raise AssertionError(f"{name} ran: measured work started")
    return boom


# ================================================================== 4. exit 6 when the fragment-mapping self-check fails
# [new] spec v1.2: aborts with exit 6 before any measured work
@pytest.mark.parametrize("order", ("forward", "reverse"))
def test_probe_exits_6_before_measured_work_when_the_fragment_mapping_fails(probe, mv, gates_open, monkeypatch, tmp_path, order):
    monkeypatch.setattr(mv, "fragment_mapping_ok", lambda: False)
    monkeypatch.setattr(probe, "mma_accuracy_sweep", forbid("mma_accuracy_sweep"))
    monkeypatch.setattr(probe, "measure_checkpoint_mma", forbid("measure_checkpoint_mma"))
    monkeypatch.setattr(probe, "TurboQuantKVCache", forbid("TurboQuantKVCache"))  # the checkpoint loop's cache
    out = tmp_path / "mma.json"
    with pytest.raises(SystemExit) as e:
        run_main(probe, ["--mode", "mma", "--arm-order", order, "--max-t", "8192", "--out", str(out)])
    assert e.value.code == 6
    assert not out.exists()


# [preserves an invariant] the other modes do not run the mapping self-check (it is an mma-mode gate)
def test_fragment_mapping_gate_is_specific_to_mma_mode(probe, mv, gates_open, monkeypatch, tmp_path):
    monkeypatch.setattr(mv, "fragment_mapping_ok", lambda: False)
    monkeypatch.setattr(probe, "mq_exactness_sweep", lambda m: {"rows": [], "n": 0, "n_bit_identical": 0, "negative_controls": {}})
    monkeypatch.setattr(probe, "CHECKPOINTS", (512,))
    monkeypatch.setattr(probe, "CAP", 1024)
    monkeypatch.setattr(probe, "measure_checkpoint_mq", lambda *a, **kw: {"T": 512})
    run_main(probe, ["--mode", "mq", "--max-t", "512", "--out", str(tmp_path / "mq.json")])  # no SystemExit(6)
    assert json.loads((tmp_path / "mq.json").read_text())["meta"]["mode"] == "mq"


# ================================================================== 3 + 4. arm order and mapping result recorded in the JSON
def stub_main_run(probe, mv, monkeypatch, tmp_path, argv):
    monkeypatch.setattr(probe, "CHECKPOINTS", (512,))
    monkeypatch.setattr(probe, "CAP", 1024)
    monkeypatch.setattr(probe, "mma_accuracy_sweep", lambda m: {"rows": [], "controls": [], "n": 0, "n_pass": 0})
    monkeypatch.setattr(probe, "measure_checkpoint_mma", lambda *a, **kw: {"T": 512})
    out = tmp_path / "mma.json"
    run_main(probe, ["--mode", "mma", "--max-t", "512", "--out", str(out), *argv])
    return json.loads(out.read_text())


# [new] meta.arm_order records the order (default forward) and meta.mma_kernel.fragment_mapping_ok records the (real) self-check
@pytest.mark.parametrize("argv,want", [([], list(FORWARD)), (["--arm-order", "forward"], list(FORWARD)),
                                       (["--arm-order", "reverse"], list(reversed(FORWARD)))])
def test_meta_records_arm_order_and_mapping_result(probe, mv, gates_open, monkeypatch, tmp_path, argv, want):
    data = stub_main_run(probe, mv, monkeypatch, tmp_path, argv)
    assert data["meta"]["mode"] == "mma"
    assert data["meta"]["arm_order"] == want
    assert data["meta"]["mma_kernel"]["fragment_mapping_ok"] is True


# ================================================================== the timed arms really run in that order
def labelled_events(probe, mv, mqm, monkeypatch):
    events, inside = [], [False]

    def wrap(obj, name, label):
        orig = getattr(obj, name)

        def f(*a, **kw):
            if inside[0]:
                events.append(label(kw))
            return orig(*a, **kw)

        monkeypatch.setattr(obj, name, f)

    wrap(probe, "joint_attention", lambda kw: "native16")
    wrap(probe, "per_query_attention", lambda kw: "tq4_production")
    wrap(probe, "scaled_dot_product_attention", lambda kw: "native16" if kw.get("cache") is None else "tq4_production")
    wrap(mqm, "mq_decode_attention", lambda kw: "mq_best")
    wrap(mv, "mma_verify_tq4", lambda kw: "mma_tq4")
    wrap(mv, "mma_verify_native16", lambda kw: "mma_n16")
    real = probe.timeit

    def timeit(fn, **kw):
        events.append("|")
        inside[0] = True
        try:
            return real(fn, min_iters=1, min_s=0.0, warmup=1, max_iters=1)
        finally:
            inside[0] = False

    monkeypatch.setattr(probe, "timeit", timeit)
    return events


# [new] spec v1.2: --arm-order forward = native16, tq4_production, mq_best, mma_tq4, mma_n16; reverse = the reverse. The order
# of the first instrumented call inside each timed region, per k, collapsed over mq_best's two groupings.
@pytest.mark.parametrize("order", ("forward", "reverse"))
def test_timed_arms_run_in_the_requested_order(probe, mv, monkeypatch, order):
    mqm = probe.fork_dev_module()
    T = 4096
    mx.random.seed(3)
    Kc = mx.random.normal((1, NKV, T, D)).astype(DT)
    Vc = mx.random.normal((1, NKV, T, D)).astype(DT)
    tq = probe.TurboQuantKVCache(bits=4, max_kv_size=T, prealloc_tokens=T)
    tq.update_and_fetch(Kc, Vc)
    mx.eval(tq.keys, tq.values, Kc, Vc)
    events = labelled_events(probe, mv, mqm, monkeypatch)
    res = probe.measure_checkpoint_mma(T, tq, Kc, Vc, probe.FusedV1Policy(), mqm, mv, arm_order=order)
    assert sorted(res["mma"], key=int) == ["1", "2", "3", "4", "5"]
    firsts, cur = [], None
    for e in events:
        if e == "|":
            cur = None
        elif cur is None:
            cur = e
            firsts.append(e)
    collapsed = [a for i, a in enumerate(firsts) if i == 0 or a != firsts[i - 1]]
    want = list(FORWARD if order == "forward" else reversed(FORWARD))
    assert collapsed == want * 5, collapsed
    for k in range(1, 6):  # every arm still measured: the JSON carries all five timings per k
        row = res["mma"][str(k)]
        assert all(a in row and row[a]["median_ms"] > 0 for a in FORWARD)
