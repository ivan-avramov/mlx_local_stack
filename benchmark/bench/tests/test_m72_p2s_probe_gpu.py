"""M72 P2' stage 1: GPU tests of `benchmark/spikes/m72_tq4_probe.py` (`--mode p2s`; spec
`docs/specs/m72-p2-stage1-scratch.md` v1.1). The probe imports MLX and the fork at load, so this module is skipped in the stack
venv (no MLX) and runs in the fork venv with this copy's fork on the path:

    ./fe_test.sh stack-gpu bench/tests/test_m72_p2s_probe_gpu.py

The probe's own functions for `--mode p2s` are not named by the specification, so the tests go through `main()` (argv) and the JSON
it writes. Gates: the probe's power gate (140 W / 28 V, battery > 20 %) and idle-GPU gate read the box; tests that run `main()`
replace `power_state` and `m72_gates.gpu_idle_ok` so they do not depend on box state or on another helper using the GPU. The
checkpoint loop is shrunk the way the mma probe tests do (`CHECKPOINTS`, `CAP`); the exactness sweep keeps its own 40,960-token
cache and its T list, cut by `--max-t`.

Each test is classed in its comment: [new] new behaviour, [invariant] preserves an invariant, [fix] reproduces a failure the
specification fixes, [threat] strict-mode threat (reading past T, wrong KV head, dtype drift).
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

mx = pytest.importorskip("mlx.core")
pytest.importorskip("mlx_vlm")
pytestmark = pytest.mark.skipif(not mx.metal.is_available(), reason="Metal GPU required")
import mlx_vlm  # noqa: E402

if not (Path(mlx_vlm.__file__).resolve().parents[1] / "dev" / "m72_mma_verify.py").exists():
    pytest.skip("the importable mlx_vlm is not this copy's fork (run: ./fe_test.sh stack-gpu <file>)", allow_module_level=True)

SPIKES = Path(__file__).resolve().parents[2] / "spikes"
GOOD_POWER = {"wattage": "140W", "voltage": "28000mV", "battery": "80%"}
FORWARD = ["native16_fused_v1", "tq4_production", "p1_rotated_bf16", "p2s", "p2s_dequant_only"]
HEADS = {"0", "6", "12", "18"}
SWEEP_T = (1, 511, 512, 4096, 8193, 32768, 40000)


@pytest.fixture(scope="module")
def probe():
    sys.path.insert(0, str(SPIKES))  # the probe imports its sibling m72_gates
    spec = importlib.util.spec_from_file_location("m72_tq4_probe", SPIKES / "m72_tq4_probe.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["m72_tq4_probe"] = mod
    spec.loader.exec_module(mod)
    return mod


def run_main(probe, argv):
    old = sys.argv
    sys.argv = ["m72_tq4_probe.py", *argv]
    try:
        probe.main()
    finally:
        sys.argv = old


def open_gates(probe, mp):
    mp.setattr(probe, "power_state", lambda: dict(GOOD_POWER))
    mp.setattr(probe.m72_gates, "gpu_idle_ok", lambda g: True)


def shrink(probe, mp, checkpoints, cap):
    mp.setattr(probe, "CHECKPOINTS", tuple(checkpoints))
    mp.setattr(probe, "CAP", cap)


@pytest.fixture()
def gates_open(probe, monkeypatch):
    open_gates(probe, monkeypatch)


def forbid(name):
    def boom(*a, **kw):
        raise AssertionError(f"{name} ran: measured work started")
    return boom


# ================================================================== the real parser
# [new] --mode gains p2s, keeps full / mq / mma and the default; --arm-order keeps forward / reverse
def test_parser_has_p2s_mode_and_keeps_the_others(probe, capsys):
    with pytest.raises(SystemExit) as e:
        run_main(probe, ["--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    for word in ("p2s", "full", "mq", "mma", "forward", "reverse"):
        assert word in out, word


# [new] an unknown mode is still rejected (exit 2) while p2s is accepted by the parser (it reaches the gates: exit 3 here)
def test_p2s_is_accepted_and_nope_is_rejected(probe, monkeypatch, capsys):
    monkeypatch.setattr(probe, "power_state", lambda: {"wattage": "60W", "voltage": "20000mV", "battery": "80%"})
    with pytest.raises(SystemExit) as e:
        run_main(probe, ["--mode", "p2s", "--out", "/nonexistent/x.json"])
    assert e.value.code == 3
    with pytest.raises(SystemExit) as e:
        run_main(probe, ["--mode", "nope", "--out", "/nonexistent/x.json"])
    assert e.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


# ================================================================== gates before measured work
# [invariant] the power gate refuses (exit 3) in p2s mode before any cache / kernel work; no output file
@pytest.mark.parametrize("order", ("forward", "reverse"))
def test_p2s_refuses_a_bad_power_state_before_measured_work(probe, monkeypatch, tmp_path, order):
    monkeypatch.setattr(probe, "power_state", lambda: {"wattage": "96W", "voltage": "20000mV", "battery": "80%"})
    monkeypatch.setattr(probe, "TurboQuantKVCache", forbid("TurboQuantKVCache"))
    out = tmp_path / "p2s.json"
    with pytest.raises(SystemExit) as e:
        run_main(probe, ["--mode", "p2s", "--arm-order", order, "--max-t", "512", "--out", str(out)])
    assert e.value.code == 3
    assert not out.exists()


# [invariant] the idle-GPU gate refuses (exit 5) in p2s mode before any cache / kernel work
def test_p2s_refuses_a_busy_gpu_before_measured_work(probe, monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "power_state", lambda: dict(GOOD_POWER))
    monkeypatch.setattr(probe.m72_gates, "gpu_idle_ok", lambda g: False)
    monkeypatch.setattr(probe, "TurboQuantKVCache", forbid("TurboQuantKVCache"))
    out = tmp_path / "p2s.json"
    with pytest.raises(SystemExit) as e:
        run_main(probe, ["--mode", "p2s", "--max-t", "512", "--out", str(out)])
    assert e.value.code == 5
    assert not out.exists()


# ================================================================== one real run: sweep to T = 8193, one checkpoint at T = 1024
@pytest.fixture(scope="module")
def smoke(probe, tmp_path_factory):
    """`--mode p2s --max-t 8193` with a 2,048-token cache and one checkpoint at T = 1024 (the chunk of 512 ends at T, so a read
    past T through the zero-filled preallocation would move the causal alignment and the softmax: it would fail A1)."""
    out = tmp_path_factory.mktemp("p2s") / "p2s.json"
    with pytest.MonkeyPatch.context() as mp:
        open_gates(probe, mp)
        shrink(probe, mp, (1024,), 2048)
        run_main(probe, ["--mode", "p2s", "--max-t", "8193", "--out", str(out)])
    return json.loads(out.read_text())


# [new] meta: mode, provenance, default arm order, kernel description
def test_meta_records_mode_fork_arm_order_and_kernel(smoke):
    m = smoke["meta"]
    assert m["mode"] == "p2s"
    assert isinstance(m["fork"].get("head"), str) and len(m["fork"]["head"]) >= 7
    assert "dirty_paths" in m["fork"] or "dirty" in m["fork"]
    assert m["arm_order"] == FORWARD  # the default order
    assert isinstance(m["p2s_kernel"], dict) and m["p2s_kernel"]
    assert m["mlx"] and m["device"]["architecture"]


# [new] exactness sweep: rows only for T <= max-t, both dtypes for every T, every dequantize row bit-identical; n / n_ok add up
def test_exactness_sweep_rows_and_counts(smoke):
    ex = smoke["meta"]["p2s_exactness"]
    rows = ex["rows"]
    assert rows and ex["n"] == len(rows) and ex["n_ok"] == sum(bool(r["bit_identical"]) for r in rows)
    want_t = {T for T in SWEEP_T if T <= 8193}
    assert {r["T"] for r in rows} == want_t
    for T in want_t:
        dts = {str(r["dtype"]) for r in rows if r["T"] == T}
        assert any("bf" in d for d in dts) and any("16" in d and "bf" not in d for d in dts), (T, dts)
    for r in rows:
        assert set(r) >= {"T", "L", "what", "dtype", "bit_identical"}
        if isinstance(r["L"], int):
            assert r["L"] in (512, 37, 1) and r["L"] <= r["T"], r
    dq = [r for r in rows if not isinstance(r["L"], int)]
    assert dq and all(r["bit_identical"] is True for r in dq), [r for r in dq if not r["bit_identical"]]


# [new] A7: rows above --max-t are skipped and listed as skipped
def test_rows_above_max_t_are_listed_as_skipped(smoke):
    ex = smoke["meta"]["p2s_exactness"]
    assert not {r["T"] for r in ex["rows"]} & {32768, 40000}
    text = json.dumps(ex).lower()
    assert "skip" in text and "32768" in text and "40000" in text


# [new] A2: N1 is present exactly once and fails A1 (it ran: T = 8193 <= max-t)
def test_n1_control_present_once_and_fails(smoke):
    ctl = smoke["meta"]["p2s_exactness"]["controls"]
    n1 = [c for c in ctl if c["name"] == "N1"]
    assert len(n1) == 1, ctl
    assert n1[0]["pass_a1"] is False and n1[0]["rel_err"] > 0.1
    assert len([c["name"] for c in ctl]) == len(set(c["name"] for c in ctl))  # each named control once


# [new] the checkpoint: five timed arms (the five names), TIMING shape, nested under "p2s"
def test_checkpoint_has_the_five_timed_arms(smoke):
    (ck,) = smoke["checkpoints"]
    assert ck["T"] == 1024
    assert set(ck["p2s"]) == set(FORWARD)
    for arm, t in ck["p2s"].items():
        assert t["median_ms"] > 0 and 0 < t["min_ms"] <= t["median_ms"] and t["n"] >= 1, (arm, t)
    assert "chain16" not in ck  # recorded at the 262,144 checkpoint only


# [new] KV append timings are recorded (the projection's append terms), positive, both families
def test_kv_append_chunk_ms_is_recorded(smoke):
    (ck,) = smoke["checkpoints"]
    ap = ck["kv_append_chunk_ms"]
    assert ap["tq4_mean_last64"] > 0 and ap["native16_mean_last64"] > 0


# [new] untimed accuracy at the checkpoint: heads 0 / 6 / 12 / 18 (one per KV head), finite, A1 holds
def test_checkpoint_accuracy_on_one_head_per_kv_head(smoke):
    (ck,) = smoke["checkpoints"]
    acc = ck["p2s_accuracy"]
    assert {str(h) for h in acc} == HEADS
    for h, a in acc.items():
        assert set(a) >= {"rel_err", "prod_rel_err", "allclose", "finite", "pass"}, h
        assert a["finite"] is True and a["allclose"] is True and a["pass"] is True, (h, a)


# [threat] reading exactly [0, T): the references (fp32, production comparator) and p2s all read the prefix of a 2,048-token
# preallocation holding 1,024 tokens. Production's own error against the independent fp32 reference is the ordinary ~bf16 level
# (a comparator that reads the zero-filled tail, or the cap-length mask alignment, is off by O(1)), and p2s is as close.
def test_references_read_exactly_the_prefix(smoke):
    (ck,) = smoke["checkpoints"]
    for h, a in ck["p2s_accuracy"].items():
        assert a["prod_rel_err"] < 8e-3, (h, a)
        assert a["rel_err"] < 8e-3, (h, a)


# [new] the full-path bit-identity diagnostic is recorded as a bool
def test_full_path_bit_identity_is_recorded(smoke):
    (ck,) = smoke["checkpoints"]
    assert isinstance(ck["p2s_vs_reference_bit_identical"], bool)


# [invariant] bookkeeping shared with the other modes
def test_checkpoint_bookkeeping(smoke):
    (ck,) = smoke["checkpoints"]
    assert ck["power"]["wattage"] == "140W"
    assert ck["peak_GB"] > 0
    assert ck["bytes"]["tq4_kv"] > 0 and ck["bytes"]["native16_kv"] > ck["bytes"]["tq4_kv"]
    assert smoke["meta"].get("finished")  # the run reached its end


# ================================================================== arm order: recorded and really the order the arms are timed in
class CountingTimeit:
    """Replaces ``timeit``: no work, TIMING whose ``median_ms`` is the call's sequence number (1, 2, ...)."""

    def __init__(self):
        self.n = 0

    def __call__(self, fn, *a, **kw):
        self.n += 1
        return {"median_ms": float(self.n), "min_ms": float(self.n), "n": 1}


def order_run(probe, tmp_path, argv, name="p2s.json"):
    out = tmp_path / name
    with pytest.MonkeyPatch.context() as mp:
        open_gates(probe, mp)
        shrink(probe, mp, (512,), 1024)
        counter = CountingTimeit()
        mp.setattr(probe, "timeit", counter)
        run_main(probe, ["--mode", "p2s", "--max-t", "512", "--out", str(out), *argv])
    return json.loads(out.read_text()), counter


# [new] meta.arm_order records the requested order (default forward); the timed arms ran in exactly that order
@pytest.mark.parametrize("argv,want", [([], FORWARD), (["--arm-order", "forward"], FORWARD),
                                       (["--arm-order", "reverse"], list(reversed(FORWARD)))])
def test_timed_arms_run_in_the_requested_order(probe, tmp_path, argv, want):
    data, counter = order_run(probe, tmp_path, argv)
    assert data["meta"]["arm_order"] == want
    (ck,) = data["checkpoints"]
    seq = {arm: ck["p2s"][arm]["median_ms"] for arm in FORWARD}  # sequence numbers of the timeit calls
    assert sorted(seq, key=seq.get) == want, seq
    assert counter.n >= 5


# [new] the timed arms come first at a checkpoint: none of the untimed measurements calls timeit (every call belongs to an arm)
def test_every_timeit_call_belongs_to_a_timed_arm_at_a_sub_cap_checkpoint(probe, tmp_path):
    data, counter = order_run(probe, tmp_path, [])
    (ck,) = data["checkpoints"]
    assert counter.n == len(ck["p2s"]) == 5


# [invariant] the order does not change what is measured: the same five keys either way
def test_both_orders_record_the_same_arms(probe, tmp_path):
    a, _ = order_run(probe, tmp_path, [], "a.json")
    b, _ = order_run(probe, tmp_path, ["--arm-order", "reverse"], "b.json")
    assert set(a["checkpoints"][0]["p2s"]) == set(b["checkpoints"][0]["p2s"]) == set(FORWARD)


# [new] a max-t below the sweep's smallest rows still records the sweep rows that fit and lists the rest as skipped
def test_small_max_t_lists_the_skipped_rows(probe, tmp_path):
    data, _ = order_run(probe, tmp_path, [])
    ex = data["meta"]["p2s_exactness"]
    assert {r["T"] for r in ex["rows"]} == {1, 511, 512}
    assert re.search(r"skip", json.dumps(ex).lower())


# ================================================================== third delivery: the fix round's adopted defects
def head_acc(rel, prod):
    """A per-head ACC whose ``pass`` is that head's own A1 verdict (rel <= 2 max(prod, 2^-12))."""
    return {"rel_err": rel, "prod_rel_err": prod, "allclose": True, "finite": True,
            "pass": rel <= 2 * max(prod, 2.0 ** -12)}


def a1_all_with(probe, monkeypatch, per_head):
    monkeypatch.setattr(probe, "p2s_a1_heads", lambda tq, q, T, out, prod, heads=None: per_head)
    return probe.p2s_a1_all(None, None, 0, None, None, heads=tuple(int(h) for h in per_head))


# [fix] defect 1: head errors (candidate / production) 0.006 / 0.001 and 0.004 / 0.004: the maxima taken independently
# (0.006 vs 2 x 0.004) would pass, but head 0 breaks its own bound (0.006 > 2 x 0.001): the row must fail
@pytest.mark.parametrize("order", ("ab", "ba"))
def test_a1_over_heads_fails_when_one_head_breaks_its_own_bound(probe, monkeypatch, order):
    a, b = head_acc(0.006, 0.001), head_acc(0.004, 0.004)
    assert a["pass"] is False and b["pass"] is True
    assert 0.006 <= 2 * max(0.004, 2.0 ** -12)  # the instrument: the independent maxima would have passed
    per = {"0": a, "6": b} if order == "ab" else {"6": b, "0": a}
    assert a1_all_with(probe, monkeypatch, per)["pass"] is False


# [invariant] the aggregate still passes when every head is within its own bound, and fails on a non-finite / not-close head
def test_a1_over_heads_passes_when_every_head_passes(probe, monkeypatch):
    res = a1_all_with(probe, monkeypatch, {"0": head_acc(0.0015, 0.001), "6": head_acc(0.004, 0.004)})
    assert res["pass"] is True and res["finite"] is True and res["allclose"] is True


@pytest.mark.parametrize("defect", ("finite", "allclose"))
def test_a1_over_heads_fails_on_a_nonfinite_or_not_close_head(probe, monkeypatch, defect):
    bad = head_acc(0.001, 0.001)
    bad[defect] = False
    bad["pass"] = False
    assert a1_all_with(probe, monkeypatch, {"0": head_acc(0.001, 0.001), "6": bad})["pass"] is False


# [fix] defect 3: the causal-alignment diagnostic exercises scratch_prefill_tq4 itself (the full path)
class FullPathProxy:
    """The fork module with ``scratch_prefill_tq4`` spied (or replaced)."""

    def __init__(self, pm, replacement=None):
        self._pm, self._rep, self.calls = pm, replacement, 0

    def __getattr__(self, name):
        return getattr(self._pm, name)

    def scratch_prefill_tq4(self, cache, queries, scale, **kw):
        self.calls += 1
        if self._rep is not None:
            return self._rep(self._pm, cache, queries, scale)
        return self._pm.scratch_prefill_tq4(cache, queries, scale, **kw)


def top_left_prefill(pm, cache, queries, scale):
    """A full path misaligned on purpose: query i sees keys j <= i (top-left) instead of j <= i + T - L."""
    T, L = int(cache.offset), queries.shape[2]
    k = pm.reference_dequant_rotated(cache.keys, T, cache.key_codec, mx.float16)
    v = pm.reference_dequant_rotated(cache.values, T, cache.value_codec, mx.float16)
    qr = cache.key_codec.prepare_queries(queries).astype(mx.float16)
    i, j = mx.arange(L)[:, None], mx.arange(T)[None, :]
    o = mx.fast.scaled_dot_product_attention(qr, k, v, scale=scale, mask=(j <= i))
    return cache.value_codec._rotate_inverse(o.astype(mx.float32)).astype(queries.dtype)


def test_causal_alignment_diagnostic_calls_the_full_path_and_passes_when_aligned(probe):
    pm = probe.fork_p2s_module()
    tq = probe.fill_cache(2048, 700)
    proxy = FullPathProxy(pm)
    res = probe.p2s_causal_alignment(proxy, tq, 700, 37)
    assert proxy.calls >= 1, "scratch_prefill_tq4 was never called by the causal-alignment diagnostic"
    assert res["pass"] is True and res["rel_vs_top_left"] > 0.1


def test_causal_alignment_diagnostic_fails_a_misaligned_full_path(probe):
    pm = probe.fork_p2s_module()
    tq = probe.fill_cache(2048, 700)
    res = probe.p2s_causal_alignment(FullPathProxy(pm, top_left_prefill), tq, 700, 37)
    assert res["pass"] is False, res
