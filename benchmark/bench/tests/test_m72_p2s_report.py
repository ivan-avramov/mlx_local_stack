"""M72 P2' stage 1: the report generator `benchmark/spikes/m72_p2s_report.py` on synthetic `p2s-1.json` / `p2s-2.json`
(no MLX, no GPU; spec `docs/specs/m72-p2-stage1-scratch.md` v1.1).

Synthetic times are linear in T (u = T / 131072), so every interpolation / extrapolation the generator does is exact and the
projection can be checked by hand; pass 2 is 1.1 x pass 1 for every arm and checkpoint (mean factor 1.05). Base times, ms per
512-token chunk per layer, pass 1:
    native16_fused_v1 4 + 40 u     tq4_production 2 + 300 u     p1_rotated_bf16 5 + 50 u
    p2s 4.5 + 46 u                 p2s_dequant_only 2 + 10 u
The cap checkpoint (T = 262,144) is ten times slower than the linear law (the table must show it; the projection must not
use it). The tq4_production slope is large so that a flat (instead of linearly extrapolated) cost below the first checkpoint is
visible in the projection (about 2 s).

KV append (`kv_append_chunk_ms`, ms per 512-token chunk): at the 260,096 checkpoint pass 1 has tq4 0.30 / native16 0.05 and
pass 2 has 0.60 / 0.25 (means 0.45 / 0.15); every other checkpoint carries decoys (9.0 / 9.0, 7.0 / 7.0 at the cap), so a
generator that reads another checkpoint, one pass only, or the wrong field, is off by seconds.

Hand-derived anchors (spec projection: attn_X(N) = sum_{j=1..N/512} interp(X, 512 j) / 1000 seconds per layer;
fixed = prefill_s(N) - 16 attn_native16(N) - 16 (N/512) append_native16; t_X(N) = fixed + 16 attn_X(N) + 16 (N/512) append_X;
means over the passes; n = N / 512; sum_{j=1..n} j / 256 = n (n + 1) / 512):
    N = 131072 (n = 256, prefill_s 294.0): attn_native16 = 1.05 (256 * 4 + 40 * 128.5) / 1000 = 6.4722 s; fixed = 189.830
        t_tq4_production = 847.9 (0.35x)   t_p1_rotated_bf16 = 321.1 (0.92x)   t_p2s = 310.3 (0.95x)
    N = 260096 (n = 508, prefill_s 260096 / 383.5 = 678.2): attn_native16 = 23.3446 s; fixed = 303.484
        t_tq4_production = 2869.5 (0.24x)  t_p1_rotated_bf16 = 774.0 (0.88x)   t_p2s = 735.8 (0.92x)
    decoys at N = 260096 for p2s: no append term 732.2; native16's append instead of tq4's 733.4; milliseconds instead of seconds.
Per-chunk means over the two passes (factor 1.05): T = 8192: 6.825 / 21.7875 / 8.5312 / 7.7438 / 2.7563;
    T = 131072: 46.2 / 317.1 / 57.75 / 53.025 / 12.6; T = 262144 (x 10): 882.0 / 6321.0 / 1102.5 / 1013.25 / 231.0.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SPIKES = Path(__file__).resolve().parents[2] / "spikes"
REPORT = SPIKES / "m72_p2s_report.py"
sys.path.insert(0, str(SPIKES))
import m72_probe_report as PR  # noqa: E402  (constants the report must use; no MLX)

TS = (8192, 32768, 131072, 196608, 260096, 262144)  # the probe's CHECKPOINTS; 262144 = the cap
CAP = 262144
ARMS = ("native16_fused_v1", "tq4_production", "p1_rotated_bf16", "p2s", "p2s_dequant_only")
FORWARD, REVERSE = list(ARMS), list(reversed(ARMS))
LAW = {"native16_fused_v1": (4.0, 40.0), "tq4_production": (2.0, 300.0), "p1_rotated_bf16": (5.0, 50.0),
       "p2s": (4.5, 46.0), "p2s_dequant_only": (2.0, 10.0)}
CAP_FACTOR = 10.0
HEADS = ("0", "6", "12", "18")
SWEEP_T = (1, 511, 512, 4096, 8193, 32768, 40000)
TOL_MS, TOL_S, TOL_R = 0.051, 0.51, 0.0051  # table ms (>= 1 decimal), projection seconds (>= 0 decimals), ratios (2 decimals)
APPEND = {  # (tq4, native16) ms per chunk, per pass, at the 260,096 checkpoint; elsewhere decoys
    "p2s-1": (0.30, 0.05), "p2s-2": (0.60, 0.25)}


def test_constants_the_synthetic_data_assumes():
    assert PR.LAYERS == 16 and PR.CHUNK == 512
    assert PR.PICK_BASELINE["prefill_s"] == {131072: 294.0, 260096: 260096 / 383.5}


# ---------------------------------------------------------------- synthetic data
def law_ms(arm, T):
    a, b = LAW[arm]
    return a + b * T / 131072


def timing(ms):
    return {"median_ms": ms, "min_ms": 0.9 * ms, "n": 20}


ACC_OK = {"rel_err": 0.004, "prod_rel_err": 0.0035, "allclose": True, "finite": True, "pass": True}
ACC_BAD = {"rel_err": 0.2, "prod_rel_err": 0.0035, "allclose": False, "finite": True, "pass": False}
GOOD_POWER = {"wattage": "140W", "voltage": "28000mV", "battery": "80%"}


def exactness(fail_row=None):
    rows = []
    for T in SWEEP_T:
        for name in ("dequant_K", "dequant_V"):
            for dtype in ("float16", "bfloat16"):
                rows.append({"T": T, "L": None, "what": name, "dtype": dtype, "bit_identical": True})
        for L in (512, 37, 1):
            if L <= T:
                rows.append({"T": T, "L": L, "what": "prefill", "dtype": "float16", "bit_identical": True})
    if fail_row is not None:
        rows[fail_row]["bit_identical"] = False
    controls = [{"name": "N1", "rel_err": 0.93, "pass_a1": False}]
    return {"rows": rows, "controls": controls, "n": len(rows), "n_ok": sum(r["bit_identical"] for r in rows)}


def row_index(T, what, dtype):
    rows = exactness()["rows"]
    return next(i for i, r in enumerate(rows) if (r["T"], r["what"], r["dtype"]) == (T, what, dtype))


def make_pass(scale, order, *, fail_row=None, bad_head=None, controls=None, bit_identical_at=None):
    """One `--mode p2s` JSON. bad_head = (T, head): that checkpoint head fails A1; bit_identical_at = T whose full-path
    bit-identity diagnostic is False; controls = replacement list for meta.p2s_exactness.controls."""
    name = "p2s-1" if scale == 1.0 else "p2s-2"
    ex = exactness(fail_row)
    if controls is not None:
        ex["controls"] = controls
    cks = []
    for T in TS:
        f = CAP_FACTOR if T == CAP else 1.0
        arms = {a: timing(law_ms(a, T) * scale * f) for a in ARMS}
        if T == 260096:
            tq4_app, n16_app = APPEND[name]
        else:
            tq4_app = n16_app = 7.0 if T == CAP else 9.0
        acc = {h: dict(ACC_OK) for h in HEADS}
        if bad_head and bad_head[0] == T:
            acc[bad_head[1]] = dict(ACC_BAD)
        ck = {"T": T, "bytes": {"tq4_kv": 1000 * T, "native16_kv": 4000 * T}, "power": dict(GOOD_POWER), "peak_GB": 12.5,
              "p2s": arms, "p2s_vs_reference_bit_identical": bit_identical_at != T, "p2s_accuracy": acc,
              "kv_append_chunk_ms": {"tq4_mean_last64": tq4_app, "native16_mean_last64": n16_app}}
        if T == CAP:
            ck["chain16"] = {"lazy": timing(300.0 * scale), "per_layer_eval": timing(330.0 * scale)}
        cks.append(ck)
    meta = {"probe": "m72_tq4_probe", "mlx": "0.32.4", "mode": "p2s",
            "device": {"device_name": "Test GPU", "architecture": "applegpu_g17s"},
            "fork": {"head": "0123456789abcdef", "dirty_paths": []}, "arm_order": list(order),
            "p2s_kernel": {"thread_mapping": "one thread per (head, token, 8 dims)", "codebook": "registers",
                           "dtype": "float16"},
            "p2s_exactness": ex}
    return {"meta": meta, "checkpoints": cks}


def two_passes(**kw1):
    return {"p2s-1": make_pass(1.0, FORWARD, **kw1), "p2s-2": make_pass(1.1, REVERSE)}


def write_run(tmp_path, passes):
    d = tmp_path / "run"
    d.mkdir()
    for name, data in passes.items():
        (d / f"{name}.json").write_text(json.dumps(data))
    return d


def run_report(run_dir):
    return subprocess.run([sys.executable, str(REPORT), str(run_dir)], capture_output=True, text=True, timeout=120)


def refusal(tmp_path, passes):
    """Run the generator on ``passes`` after proving it accepts the unedited two-pass data (so a nonzero exit below is the
    generator's own refusal, never a missing script or a broken fixture)."""
    ok_dir = tmp_path / "control"
    ok_dir.mkdir()
    assert generate(write_run(ok_dir, two_passes())).strip()
    return run_report(write_run(tmp_path, passes))


def generate(run_dir):
    r = run_report(run_dir)
    assert r.returncode == 0, f"generator exit {r.returncode}\nstderr:\n{r.stderr}"
    assert "Traceback" not in r.stderr
    return r.stdout


@pytest.fixture()
def report(tmp_path):
    return generate(write_run(tmp_path, two_passes()))


# ---------------------------------------------------------------- parsing helpers
NUM = re.compile(r"-?\d+(?:\.\d+)?")


def table_rows(lines):
    for ln in lines:
        s = ln.strip()
        if s.startswith("|") and not re.fullmatch(r"\|[\s:|-]+\|?", s):
            yield [c.strip() for c in s.strip("|").split("|")]


def as_int(cell):
    c = cell.replace(",", "").replace("_", "").strip("` ")
    return int(c) if re.fullmatch(r"\d+", c) else None


def first_float(cell):
    m = NUM.search(cell.replace(",", ""))
    return float(m.group()) if m else None


def close(a, b, tol):
    return a is not None and abs(a - b) <= tol


def chunk_row_matches(text, T, means, ratios):
    """True when some table row starts with T and carries, in order after it, the five arm means and the three ratios."""
    for cells in table_rows(text.splitlines()):
        if len(cells) >= 9 and as_int(cells[0]) == T:
            vals = [first_float(c) for c in cells[1:9]]
            if all(close(v, w, TOL_MS) for v, w in zip(vals[:5], means)) and all(
                    close(v, w, TOL_R) for v, w in zip(vals[5:], ratios)):
                return True
    return False


def numbers_for(text, N):
    """Every number in every table row that has a cell equal to the integer N (the projection row(s) for that N)."""
    out = []
    for cells in table_rows(text.splitlines()):
        if any(as_int(c) == N for c in cells):
            out += [float(x) for x in NUM.findall(" ".join(cells).replace(",", ""))]
    assert out, f"no table row for N={N}"
    return out


def has(nums, want, tol):
    return any(abs(n - want) <= tol for n in nums)


def region_lines(text, pat):
    return [ln for ln in text.splitlines() if re.search(pat, ln, re.I)]


# ---------------------------------------------------------------- expected values (independent of the generator)
def mean_factor(s2=1.1):
    return (1.0 + s2) / 2


def mean_ms(arm, T, m=1.05):
    return law_ms(arm, T) * m * (CAP_FACTOR if T == CAP else 1.0)


def attn_s(arm, N, m):
    """Seconds of attention per layer over a cold N-token prefill (spec: sum of per-chunk costs at each chunk's end key)."""
    return sum(law_ms(arm, 512 * j) * m for j in range(1, N // 512 + 1)) / 1000


def projection(N, m, tq4_app=0.45, n16_app=0.15):
    n = N // 512
    pref = PR.PICK_BASELINE["prefill_s"][N]
    fixed = pref - 16 * attn_s("native16_fused_v1", N, m) - 16 * n * n16_app / 1000
    return pref, {x: fixed + 16 * attn_s(x, N, m) + 16 * n * tq4_app / 1000
                  for x in ("tq4_production", "p1_rotated_bf16", "p2s")}


# ================================================================ tests
# class: new behaviour
def test_generated_header_and_stdout_markdown(report):
    first = report.lstrip().splitlines()[0]
    assert first.startswith("#")
    assert "GENERATED" in first and "m72_p2s_report.py" in first
    assert "never hand-edit" in first.lower()


# class: new behaviour (the hand-derived literal anchors of the module docstring agree with the independent formula)
def test_the_synthetic_anchors_are_what_the_docstring_says():
    pref, t = projection(131072, 1.05)
    assert abs(pref - 294.0) < 1e-9
    assert abs(t["tq4_production"] - 847.915) < 5e-3 and abs(t["p1_rotated_bf16"] - 321.118) < 5e-3
    assert abs(t["p2s"] - 310.332) < 5e-3
    pref, t = projection(260096, 1.05)
    assert abs(t["tq4_production"] - 2869.528) < 5e-3 and abs(t["p1_rotated_bf16"] - 774.033) < 5e-3
    assert abs(t["p2s"] - 735.828) < 5e-3


# class: new behaviour (per-chunk table: T, the five arms, p2s / native16_fused_v1, p2s / tq4_production, p2s / p1; means over
# the passes; the cap checkpoint is shown, ten times slower)
@pytest.mark.parametrize("T", TS)
def test_per_chunk_table_means_over_passes_and_ratios(report, T):
    m = {a: mean_ms(a, T) for a in ARMS}
    means = [m[a] for a in ARMS]
    ratios = [m["p2s"] / m["native16_fused_v1"], m["p2s"] / m["tq4_production"], m["p2s"] / m["p1_rotated_bf16"]]
    assert chunk_row_matches(report, T, means, ratios), (T, means, ratios)


# class: new behaviour (literal anchors, hand-derived in the docstring: t_X(N) in seconds and prefill_s(N) / t_X(N))
def test_projection_hand_derived_literals(report):
    n = numbers_for(report, 131072)
    for want in (294.0, 847.9, 321.1, 310.3):
        assert has(n, want, TOL_S), (want, n)
    for want in (0.35, 0.92, 0.95):
        assert has(n, want, TOL_R), (want, n)
    n = numbers_for(report, 260096)
    for want in (678.2, 2869.5, 774.0, 735.8):
        assert has(n, want, TOL_S), (want, n)
    for want in (0.24, 0.88, 0.92):
        assert has(n, want, TOL_R), (want, n)


# class: new behaviour (the formula on a second data set: pass 2 at 1.5 x, mean factor 1.25; the same append values)
@pytest.mark.parametrize("s2", (1.1, 1.5))
@pytest.mark.parametrize("N", (131072, 260096))
def test_projection_matches_the_formula(tmp_path, s2, N):
    passes = {"p2s-1": make_pass(1.0, FORWARD), "p2s-2": make_pass(1.1, REVERSE)}
    if s2 != 1.1:  # rescale pass 2's timings to s2 x pass 1's
        for c in passes["p2s-2"]["checkpoints"]:
            for a in ARMS:
                for k in ("median_ms", "min_ms"):
                    c["p2s"][a][k] *= s2 / 1.1
    out = generate(write_run(tmp_path, passes))
    pref, t = projection(N, mean_factor(s2))
    n = numbers_for(out, N)
    assert has(n, pref, TOL_S)
    for x, v in t.items():
        assert has(n, v, TOL_S), (x, v, n)
        assert has(n, pref / v, TOL_R), (x, pref / v, n)


# class: reproduces a failure the specification fixes (units: attention is ms, the projection is seconds; the 16 layers; the
# append terms with the right field per arm family and the 260,096 checkpoint's two-pass mean)
def test_projection_units_and_append_terms_are_the_specified_ones(report):
    pref, t = projection(260096, 1.05)
    n = numbers_for(report, 260096)
    wrong = {
        "milliseconds instead of seconds": t["p2s"] * 1000,
        "no append term": t["p2s"] - 16 * 508 * 0.45 / 1000,
        "native16's append instead of tq4's": t["p2s"] - 16 * 508 * (0.45 - 0.15) / 1000,
        "pass 1's append only": t["p2s"] - 16 * 508 * (0.45 - 0.30) / 1000,
        "pass 2's append only": t["p2s"] + 16 * 508 * (0.60 - 0.45) / 1000,
        "another checkpoint's append (9.0 ms)": t["p2s"] + 16 * 508 * (9.0 - 0.45) / 1000,
    }
    for what, v in wrong.items():
        assert abs(v - t["p2s"]) > 2 * TOL_S, what  # the instrument can tell it apart
        assert not has(n, v, TOL_S), f"the projection used {what}: {v:.1f}"


# class: reproduces a failure the specification fixes (linear extrapolation below the first checkpoint, not a flat cost)
def test_projection_extrapolates_linearly_below_the_first_checkpoint(report):
    flat_below = sum((law_ms("tq4_production", max(512 * j, 8192)) * 1.05) for j in range(1, 509)) / 1000
    true = attn_s("tq4_production", 260096, 1.05)
    assert abs(16 * (flat_below - true)) > 2 * TOL_S  # distinguishable
    _, t = projection(260096, 1.05)
    flat_t = t["tq4_production"] + 16 * (flat_below - true)
    assert has(numbers_for(report, 260096), t["tq4_production"], TOL_S)
    assert not has(numbers_for(report, 260096), flat_t, TOL_S)


# class: new behaviour (the chain16 line: lazy, per-layer evaluation, ratio; means over the passes 315.0 / 346.5, ratio 1.10)
def test_chain16_line(report):
    lines = [ln for ln in report.splitlines() if "chain" in ln.lower() and NUM.search(ln)]
    assert lines, "no chain16 line"
    nums = [float(x) for ln in lines for x in NUM.findall(ln.replace(",", ""))]
    assert has(nums, 315.0, TOL_MS) and has(nums, 346.5, TOL_MS), nums
    assert has(nums, 1.10, TOL_R) or has(nums, 1 / 1.10, TOL_R), nums  # per-layer / lazy (or its inverse)


# class: new behaviour (pass-to-pass drift for two passes: p2s-2 / p2s-1 = 1.10 for every arm)
def test_pass_to_pass_drift_line(report):
    lines = region_lines(report, "drift")
    assert lines, "no pass-to-pass drift line"
    assert any(re.search(r"1\.1(0|00)?\b", ln) for ln in lines), lines


# class: new behaviour (arm order is recorded per pass in the report)
def test_arm_orders_are_reported(report):
    assert ARMS[0] in report and "native16_fused_v1" in report
    assert "p2s-1" in report and "p2s-2" in report
    assert re.search(r"forward|native16_fused_v1\s*(→|->)\s*tq4_production", report, re.I)
    assert re.search(r"reverse|p2s_dequant_only\s*(→|->)\s*p2s\b", report, re.I)


# class: new behaviour (exactness / accuracy section: counts per pass)
def test_exactness_counts_per_pass(tmp_path):
    p1 = make_pass(1.0, FORWARD, fail_row=3)
    p2 = make_pass(1.1, REVERSE)
    n = p1["meta"]["p2s_exactness"]["n"]
    assert p1["meta"]["p2s_exactness"]["n_ok"] == n - 1 == p2["meta"]["p2s_exactness"]["n_ok"] - 1
    out = generate(write_run(tmp_path, {"p2s-1": p1, "p2s-2": p2}))
    assert re.search(rf"\b{n - 1}\s*/\s*{n}\b", out), f"no {n - 1} / {n}"
    assert re.search(rf"\b{n}\s*/\s*{n}\b", out), f"no {n} / {n}"


# class: new behaviour (a non-bit-identical dequantize row must not be silent: it names its T)
def test_failed_exactness_row_is_visible(tmp_path):
    ok = generate(write_run(tmp_path, two_passes()))
    d2 = tmp_path / "bad"
    d2.mkdir()
    bad = generate(write_run(d2, two_passes(fail_row=row_index(40000, "dequant_K", "float16"))))
    assert bad != ok
    new = set(bad.splitlines()) - set(ok.splitlines())
    assert any("40000" in ln or "40,000" in ln for ln in new), new


# class: new behaviour (A1 per checkpoint head: counts, and a failing head is visible)
def test_checkpoint_accuracy_counts_and_failures(tmp_path):
    ok = generate(write_run(tmp_path, two_passes()))
    assert re.search(r"\b24\s*/\s*24\b", ok), "6 checkpoints x 4 heads = 24 / 24"
    d2 = tmp_path / "bad"
    d2.mkdir()
    bad = generate(write_run(d2, two_passes(bad_head=(131072, "12"))))
    assert re.search(r"\b23\s*/\s*24\b", bad)
    new = set(bad.splitlines()) - set(ok.splitlines())
    assert any("131072" in ln or "131,072" in ln for ln in new), new


# class: new behaviour (the p2s vs reference_prefill bit-identity diagnostic is reported, and a False is visible)
def test_full_path_bit_identity_diagnostic_is_reported(tmp_path):
    ok = generate(write_run(tmp_path, two_passes()))
    d2 = tmp_path / "bad"
    d2.mkdir()
    bad = generate(write_run(d2, two_passes(bit_identical_at=32768)))
    assert bad != ok
    assert any("32768" in ln or "32,768" in ln for ln in set(bad.splitlines()) - set(ok.splitlines()))


# class: new behaviour (A2: N1 must fail A1; a control that passes A1, a missing N1 and a duplicated N1 are not a shown control)
@pytest.mark.parametrize("what,controls", [
    ("N1 passed A1", [{"name": "N1", "rel_err": 0.001, "pass_a1": True}]),
    ("N1 missing", []),
    ("N1 duplicated", [{"name": "N1", "rel_err": 0.93, "pass_a1": False}, {"name": "N1", "rel_err": 0.93, "pass_a1": False}]),
])
def test_a2_control_defects_change_the_report(tmp_path, what, controls):
    ok = generate(write_run(tmp_path, two_passes()))
    d2 = tmp_path / "bad"
    d2.mkdir()
    bad = generate(write_run(d2, two_passes(controls=controls)))
    new = set(bad.splitlines()) - set(ok.splitlines())
    assert new, f"{what}: the report is unchanged"
    assert any(re.search(r"N1|control|A2", ln, re.I) for ln in new), (what, new)


# class: new behaviour ("extra named controls allowed")
def test_extra_named_control_is_allowed_and_listed(tmp_path):
    controls = [{"name": "N1", "rel_err": 0.93, "pass_a1": False}, {"name": "N9", "rel_err": 0.5, "pass_a1": False}]
    out = generate(write_run(tmp_path, two_passes(controls=controls)))
    assert "N9" in out and "N1" in out


# class: preserves an invariant (generated output is a pure function of the run dir)
def test_generator_is_deterministic(tmp_path):
    d = write_run(tmp_path, two_passes())
    assert generate(d) == generate(d)


# class: preserves an invariant (a pass is a pass: passes given in the other file order give the same tables)
def test_swapping_which_pass_is_forward_does_not_change_the_means(tmp_path):
    a = generate(write_run(tmp_path, {"p2s-1": make_pass(1.0, FORWARD), "p2s-2": make_pass(1.1, REVERSE)}))
    d2 = tmp_path / "swap"
    d2.mkdir()
    b = generate(write_run(d2, {"p2s-1": make_pass(1.0, REVERSE), "p2s-2": make_pass(1.1, FORWARD)}))  # orders swapped
    m = {x: mean_ms(x, 131072) for x in ARMS}
    for out in (a, b):
        assert chunk_row_matches(out, 131072, [m[x] for x in ARMS],
                                 [m["p2s"] / m["native16_fused_v1"], m["p2s"] / m["tq4_production"],
                                  m["p2s"] / m["p1_rotated_bf16"]])


# ================================================================ refusals (spec: provenance and arm orders)
def mismatch_edits():
    """name -> function that edits a pass's JSON in place so its provenance differs from make_pass()'s."""
    def head(d):
        d["meta"]["fork"]["head"] = "fedcba9876543210"

    def mlx(d):
        d["meta"]["mlx"] = "0.99.0"

    def arch(d):
        d["meta"]["device"]["architecture"] = "applegpu_g16s"

    def kernel(d):
        d["meta"]["p2s_kernel"]["thread_mapping"] = "a simdgroup per token row"

    def kernel_dtype(d):
        d["meta"]["p2s_kernel"]["dtype"] = "bfloat16"

    def ts_dropped(d):
        d["checkpoints"] = [c for c in d["checkpoints"] if c["T"] != 131072]

    def ts_changed(d):
        d["checkpoints"][1]["T"] = 32769

    return {"fork.head": head, "mlx": mlx, "device.architecture": arch, "p2s_kernel.thread_mapping": kernel,
            "p2s_kernel.dtype": kernel_dtype, "checkpoint-T-dropped": ts_dropped, "checkpoint-T-changed": ts_changed}


# class: new behaviour (refuse to combine passes with differing provenance: nonzero exit, a message, no tables)
@pytest.mark.parametrize("which", list(mismatch_edits()))
@pytest.mark.parametrize("edited", ("p2s-1", "p2s-2"))
def test_report_refuses_passes_with_differing_provenance(tmp_path, which, edited):
    passes = two_passes()
    mismatch_edits()[which](passes[edited])
    r = refusal(tmp_path, passes)
    assert r.returncode != 0, "combined passes with different provenance"
    assert "Traceback" not in r.stderr
    assert r.stderr.strip(), "a refusal needs a message"
    assert "|" not in r.stdout  # no table was printed


# class: new behaviour (a refusal names the field that differs)
@pytest.mark.parametrize("which,field", [("fork.head", "fork"), ("mlx", "mlx"), ("device.architecture", "architecture"),
                                         ("p2s_kernel.thread_mapping", "p2s_kernel")])
def test_refusal_names_the_differing_field(tmp_path, which, field):
    passes = two_passes()
    mismatch_edits()[which](passes["p2s-2"])
    r = refusal(tmp_path, passes)
    assert r.returncode != 0 and field in r.stderr + r.stdout


# class: new behaviour (arm orders must be one forward and one reverse; any other pair refuses)
@pytest.mark.parametrize("o1,o2", [(FORWARD, FORWARD), (REVERSE, REVERSE), (FORWARD, FORWARD[1:] + FORWARD[:1]),
                                   (FORWARD, None), (None, REVERSE), (FORWARD, sorted(ARMS))])
def test_report_refuses_arm_orders_that_are_not_one_forward_one_reverse(tmp_path, o1, o2):
    passes = {"p2s-1": make_pass(1.0, FORWARD), "p2s-2": make_pass(1.1, REVERSE)}
    for name, order in (("p2s-1", o1), ("p2s-2", o2)):
        if order is None:
            del passes[name]["meta"]["arm_order"]
        else:
            passes[name]["meta"]["arm_order"] = list(order)
    r = refusal(tmp_path, passes)
    assert r.returncode != 0, (o1, o2)
    assert "Traceback" not in r.stderr and r.stderr.strip()


# class: new behaviour (either pass may carry the forward order)
@pytest.mark.parametrize("o1,o2", [(FORWARD, REVERSE), (REVERSE, FORWARD)])
def test_report_accepts_one_forward_and_one_reverse_in_either_assignment(tmp_path, o1, o2):
    out = generate(write_run(tmp_path, {"p2s-1": make_pass(1.0, o1), "p2s-2": make_pass(1.1, o2)}))
    assert out.strip()


# class: preserves an invariant (equal provenance does not refuse even when the unrelated meta differs)
def test_unrelated_meta_differences_do_not_refuse(tmp_path):
    passes = two_passes()
    passes["p2s-2"]["meta"]["started"] = "2026-11-11T00:00:00+0000"
    passes["p2s-2"]["meta"]["power_start"] = {"wattage": "140W", "voltage": "28000mV", "battery": "70%"}
    for c in passes["p2s-2"]["checkpoints"]:
        c["peak_GB"] = 13.1
    assert generate(write_run(tmp_path, passes)).strip()


# class: preserves an invariant (the inputs are not modified by the generator)
def test_generator_does_not_modify_its_inputs(tmp_path):
    d = write_run(tmp_path, two_passes())
    before = {p.name: p.read_bytes() for p in d.iterdir()}
    generate(d)
    assert {p.name: p.read_bytes() for p in d.iterdir()} == before and set(before) == {"p2s-1.json", "p2s-2.json"}


# ================================================================ third delivery: the fix round's adopted defects
# class: reproduces a failure the fix round corrects (defect 2: the report produced tables from a single pass)
@pytest.mark.parametrize("only", ("p2s-1", "p2s-2"))
def test_report_refuses_a_single_pass(tmp_path, only):
    full = two_passes()
    r = refusal(tmp_path, {only: full[only]})  # the control run proves the generator accepts the two-pass data
    assert r.returncode != 0, f"a report was produced from {only} alone"
    assert "Traceback" not in r.stderr and r.stderr.strip(), "a refusal needs a message"
    assert "|" not in r.stdout  # no table printed


# class: reproduces a failure the fix round corrects (defect 2: a single pass with a valid arm order is still refused)
@pytest.mark.parametrize("order", (FORWARD, REVERSE))
def test_report_refuses_a_single_pass_whatever_its_order(tmp_path, order):
    r = refusal(tmp_path, {"p2s-1": make_pass(1.0, order)})
    assert r.returncode != 0 and "|" not in r.stdout


def shrunk(*, chain=True, shapes_cap=65536):
    """Two passes whose largest checkpoint is T = 65,536 (this run's cache cap), not 262,144; chain16 there (or nowhere)."""
    passes = two_passes()
    for p in passes.values():
        keep = []
        for c in p["checkpoints"]:
            if c["T"] in (8192, 32768, CAP):
                if c["T"] == CAP:
                    c["T"] = 65536
                    if not chain:
                        c.pop("chain16", None)
                keep.append(c)
        p["checkpoints"] = keep
        if shapes_cap is not None:
            p["meta"]["shapes"] = {"cap": shapes_cap, "chunk": 512}
    return passes


# class: reproduces a failure the fix round corrects (defect 4: no hard-coded 262,144 when the run's cap / chain T differs)
@pytest.mark.parametrize("chain,shapes_cap", [(True, 65536), (False, 65536), (True, None), (False, None)])
def test_report_does_not_hard_code_the_262144_cap(tmp_path, chain, shapes_cap):
    out = generate(write_run(tmp_path, shrunk(chain=chain, shapes_cap=shapes_cap)))
    assert not re.search(r"262,?144", out), [ln for ln in out.splitlines() if re.search(r"262,?144", ln)]


# class: new behaviour (defect 4: the chain16 line and the header take T / the cap from the data)
def test_chain16_line_and_header_use_the_runs_own_numbers(tmp_path):
    out = generate(write_run(tmp_path, shrunk()))
    chain = [ln for ln in out.splitlines() if "chain" in ln.lower() and NUM.search(ln)]
    assert chain and any(re.search(r"65,?536", ln) for ln in chain), chain
    header = out.split("## 1.")[0]
    assert re.search(r"65,?536", header), header
