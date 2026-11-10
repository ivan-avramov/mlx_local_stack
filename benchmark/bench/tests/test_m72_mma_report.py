"""M72 1.2 matrix-unit verify: the report generator `benchmark/spikes/m72_mma_report.py` on synthetic `mma-1.json` /
`mma-2.json` (no MLX, no GPU).

Synthetic times are linear in T (u = T / 131072) so every interpolation / extrapolation the generator does is exact and
checkable by hand; pass 2 is 1.1 x pass 1 everywhere, so a means-over-passes bug (pass 1 only, pass 2 only, wrong divisor) and a
ratio-of-means vs mean-of-ratios choice are told apart from the pass-to-pass drift (1.10). The cap checkpoint (T = 262,144) is
ten times slower than the linear law, so a generator that interpolates through it ("sub-cap checkpoints only" violated) gets
visibly different projections.

Per pass, base times in ms per layer (k = verify block size), u = T / 131072:
    native16       k = 1: 0.6 + 0.8 u         k >= 2: (0.4 + 0.2 k) + 0.8 u
    tq4_production (0.5 + 0.9 k) + 1.5 u
    mq_best        (0.45 + 0.5 k) + 0.8 u
    mma_tq4        (0.8 + 0.3 k) + 0.9 u
    mma_n16        (0.2 + 0.2 k) + 0.6 u
At k = 1 `mq_best` < `mma_tq4` and `mma_n16` < `native16` at every T (so "best of" picks different arms for TQ4 and native16).

Hand-derived anchors (means over the two passes, factor 1.05; PICK_BASELINE: e = 2.35, dd_on 24.8 / 16.03, dd_off 13.39):
    T = 131072, k = 3: native16 1.89, tq4_production 4.935, mma_tq4 2.73, mma_n16 1.47
        fixed = 2.35 / 24.8 * 1e3 - 16 * 1.89 = 64.518
        tok/s: TQ4 today 16.38 (0.66x), TQ4 + mma 21.72 (0.88x), native16 + mma 26.69 (1.08x); TQ4 + mma / native16 + mma 0.81
    T = 260096 (extrapolated from the two sub-cap points 8192 / 131072), k = 3:
        fixed = 103.130; TQ4 today 11.36 (0.71x), TQ4 + mma 14.53 (0.91x), native16 + mma 17.21 (1.07x); ratio 0.84
    MTP OFF, T = 260096, k = 1: native16 2.296875, mq_best 2.664375, mma_tq4 3.030234, mma_n16 1.670156
        fixed = 1e3 / 13.39 - 16 * 2.296875 = 37.933; TQ4 best (mq_best) 12.41 (0.93x); native16 best (mma_n16) 15.47 (1.16x)
"""
from __future__ import annotations

import ast
import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SPIKES = Path(__file__).resolve().parents[2] / "spikes"
REPORT = SPIKES / "m72_mma_report.py"
sys.path.insert(0, str(SPIKES))
import m72_probe_report as PR  # noqa: E402  (constants + interp the report must use; no MLX)

TS = (8192, 131072, 262144)  # 262144 = the cap (contiguous layout; excluded from projections)
SUBCAP = (8192, 131072)
KS = ("1", "2", "3", "4", "5")
ARMS = ("native16", "tq4_production", "mq_best", "mma_tq4", "mma_n16")
CAP_FACTOR = 10.0
TOL = 0.0051  # half a unit of the second decimal: accepts any rendering with >= 2 decimals


def test_baseline_constants_the_synthetic_data_assumes():
    assert PR.LAYERS == 16 and PR.VERIFY_K == "3"
    assert PR.PICK_BASELINE["emitted_per_round"] == 2.35
    assert PR.PICK_BASELINE["decode_on_tps"] == {131072: 24.8, 260096: 16.03}
    assert PR.PICK_BASELINE["decode_off_tps"] == {260096: 13.39}


# ---------------------------------------------------------------- synthetic data
def base_ms(arm, k, T):
    u = T / 131072
    k = int(k)
    if arm == "native16":
        return (0.6 + 0.8 * u) if k == 1 else (0.4 + 0.2 * k) + 0.8 * u
    return {
        "tq4_production": (0.5 + 0.9 * k) + 1.5 * u,
        "mq_best": (0.45 + 0.5 * k) + 0.8 * u,
        "mma_tq4": (0.8 + 0.3 * k) + 0.9 * u,
        "mma_n16": (0.2 + 0.2 * k) + 0.6 * u,
    }[arm]


def timing(ms):
    return {"median_ms": ms, "min_ms": 0.9 * ms, "n": 20}


ACC_OK = {"rel_err": 0.004, "prod_rel_err": 0.003, "allclose": True, "finite": True, "pass": True}
ACC_BAD = {"rel_err": 0.2, "prod_rel_err": 0.003, "allclose": False, "finite": True, "pass": False}


def make_pass(scale, *, sweep_fail=0, bad_checkpoint=None, bad_control=None):
    """One `--mode mma` JSON. bad_checkpoint = (T, k, arm) whose accuracy fails A1; bad_control = (name, arm) whose control
    wrongly PASSES A1 (a negative control that did not fail)."""
    rows = []
    for T in (4096, 9000, 33025, 40000):
        for k in (1, 3, 5):
            for arm in ("mma_tq4", "mma_n16"):
                rows.append({"T": T, "k": k, "arm": arm, "case": "random", **ACC_OK})
    rows = rows[:20] if len(rows) >= 20 else rows
    for r in rows[:sweep_fail]:
        r.update(ACC_BAD)
    controls = [{"name": n, "arm": a, "rel_err": 0.9, "pass": False} for n in ("N1", "N2", "N3") for a in ("mma_tq4", "mma_n16")]
    if bad_control:
        for c in controls:
            if (c["name"], c["arm"]) == bad_control:
                c.update(rel_err=0.001, **{"pass": True})
    cks = []
    for T in TS:
        f = CAP_FACTOR if T == 262144 else 1.0
        mma = {}
        for k in KS:
            lens = [T - int(k) + 1 + j for j in range(int(k))]
            cell = {"lengths": lens, **{a: timing(base_ms(a, k, T) * scale * f) for a in ARMS}}
            cell["mq_best"]["G"] = 2
            acc = {"mma_tq4": dict(ACC_OK), "mma_n16": dict(ACC_OK)}
            if bad_checkpoint == (T, int(k), "mma_tq4"):
                acc["mma_tq4"] = dict(ACC_BAD)
            cell["accuracy"] = acc
            mma[k] = cell
        cks.append({"T": T, "bytes": {"tq4_kv": 1000 * T, "native16_kv": 4000 * T}, "plan": {"blocks": 64, "tokens_per_block": T // 64},
                    "power": {"wattage": "140W", "voltage": "28000mV", "battery": "80%"}, "peak_GB": 12.5, "mma": mma})
    meta = {"probe": "m72_tq4_probe", "mlx": "0.32.4", "device": {"device_name": "Test GPU", "architecture": "applegpu_g17s"},
            "mode": "mma", "fork": {"head": "0123456789abcdef", "dirty_paths": []},
            "mma_accuracy": {"rows": rows, "controls": controls, "n": len(rows), "n_pass": sum(r["pass"] for r in rows)}}
    return {"meta": meta, "checkpoints": cks}


def write_run(tmp_path, passes):
    """passes: {"mma-1": json_dict, ...}"""
    d = tmp_path / "run"
    d.mkdir()
    for name, data in passes.items():
        (d / f"{name}.json").write_text(json.dumps(data))
    return d


def generate(run_dir):
    r = subprocess.run([sys.executable, str(REPORT), str(run_dir)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"generator exit {r.returncode}\nstderr:\n{r.stderr}"
    assert "Traceback" not in r.stderr
    return r.stdout


@pytest.fixture()
def two_pass_report(tmp_path):
    return generate(write_run(tmp_path, {"mma-1": make_pass(1.0), "mma-2": make_pass(1.1)}))


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


def timing_rows(text):
    """{(T, k): [floats after the first two cells]} for table rows that begin with integer T and integer k."""
    out = {}
    for cells in table_rows(text.splitlines()):
        if len(cells) >= 10 and as_int(cells[0]) in TS and as_int(cells[1]) in (1, 2, 3, 4, 5):
            vals = [first_float(c) for c in cells[2:]]
            if sum(v is not None for v in vals) >= 8:
                out.setdefault((as_int(cells[0]), as_int(cells[1])), []).append(vals)
    return out


def region(text, start_pat, end_pat=None):
    lines = text.splitlines()
    heads = [i for i, ln in enumerate(lines) if ln.lstrip().startswith("#")]
    s = next((i for i in heads if re.search(start_pat, lines[i], re.I)), None)
    assert s is not None, f"no heading matching {start_pat!r}"
    level = len(lines[s].lstrip()) - len(lines[s].lstrip().lstrip("#"))
    if end_pat:
        e = next((i for i in heads if i > s and re.search(end_pat, lines[i], re.I)), len(lines))
    else:  # up to the next heading of the same or a higher level
        e = next((i for i in heads if i > s and len(lines[i].lstrip()) - len(lines[i].lstrip().lstrip("#")) <= level), len(lines))
    return lines[s:e]


def row_numbers(lines, T):
    for cells in table_rows(lines):
        if as_int(cells[0]) == T:
            return [float(x) for x in NUM.findall(" ".join(cells[1:]).replace(",", ""))]
    pytest.fail(f"no table row for T={T} in region:\n" + "\n".join(lines))


def has(nums, want):
    return any(abs(n - want) <= TOL for n in nums)


# ---------------------------------------------------------------- expected values (independent of the generator)
def mean_ms(arm, k, T, s):
    f = CAP_FACTOR if T == 262144 else 1.0
    return base_ms(arm, k, T) * s * f


def sub(arm, k, s, T, ts=SUBCAP):
    return PR.interp({x: mean_ms(arm, k, x, s) for x in ts}, T)


def on_expected(T, s, ts=SUBCAP):
    dd = PR.PICK_BASELINE["decode_on_tps"][T]
    e = PR.PICK_BASELINE["emitted_per_round"]
    fixed = e / dd * 1e3 - 16 * sub("native16", "3", s, T, ts)
    tps = {a: e / (fixed + 16 * sub(a, "3", s, T, ts)) * 1e3 for a in ("tq4_production", "mma_tq4", "mma_n16")}
    return dd, tps


def off_expected(s, T=260096):
    dd = PR.PICK_BASELINE["decode_off_tps"][T]
    fixed = 1e3 / dd - 16 * sub("native16", "1", s, T)
    tq = min(sub("mq_best", "1", s, T), sub("mma_tq4", "1", s, T))
    n16 = min(sub("native16", "1", s, T), sub("mma_n16", "1", s, T))
    return dd, 1e3 / (fixed + 16 * tq), 1e3 / (fixed + 16 * n16)


# ================================================================ tests
# class: new behaviour
def test_generated_header_and_stdout_markdown(two_pass_report):
    first = two_pass_report.lstrip().splitlines()[0]
    assert first.startswith("#")
    assert "GENERATED" in first and "m72_mma_report.py" in first
    assert "never hand-edit" in first.lower()


# class: new behaviour
@pytest.mark.parametrize("T", TS)
@pytest.mark.parametrize("k", (1, 2, 3, 4, 5))
def test_per_layer_table_means_over_passes(two_pass_report, T, k):
    rows = timing_rows(two_pass_report).get((T, k))
    assert rows, f"no per-layer row for T={T} k={k}"
    s = 1.05
    want = [mean_ms(a, k, T, s) for a in ARMS]
    assert any(all(abs(r[i] - want[i]) <= TOL for i in range(5)) for r in rows), (T, k, want, rows)


# class: new behaviour
@pytest.mark.parametrize("T,k", [(8192, 1), (131072, 3), (262144, 5)])
def test_per_layer_table_ratios(two_pass_report, T, k):
    s = 1.05
    m = {a: mean_ms(a, k, T, s) for a in ARMS}
    want = [m["mma_tq4"] / m["tq4_production"], m["mma_tq4"] / m["native16"], m["mma_n16"] / m["native16"]]
    rows = timing_rows(two_pass_report)[(T, k)]
    assert any(all(abs(r[5 + i] - want[i]) <= TOL for i in range(3)) for r in rows), (want, rows)


# class: new behaviour (the projection formulas, numbers derived by hand in the module docstring)
def test_mtp_on_projection_hand_derived_literals(two_pass_report):
    sec = region(two_pass_report, r"MTP\s+ON", r"MTP\s+OFF")
    n = row_numbers(sec, 131072)
    for want in (24.8, 16.38, 0.66, 21.72, 0.88, 26.69, 1.08, 0.81):
        assert has(n, want), (want, n)
    n = row_numbers(sec, 260096)
    for want in (16.03, 11.36, 0.71, 14.53, 0.91, 17.21, 1.07, 0.84):
        assert has(n, want), (want, n)


# class: new behaviour
@pytest.mark.parametrize("T", (131072, 260096))
def test_mtp_on_projection_matches_formula(two_pass_report, T):
    dd, tps = on_expected(T, 1.05)
    n = row_numbers(region(two_pass_report, r"MTP\s+ON", r"MTP\s+OFF"), T)
    wants = [dd, *tps.values(), *(v / dd for v in tps.values()), tps["mma_tq4"] / tps["mma_n16"]]
    for w in wants:
        assert has(n, w), (T, w, n)


# class: new behaviour (OFF is k = 1; TQ4 best = mq_best here, native16 best = mma_n16 here)
def test_mtp_off_projection_best_of(two_pass_report):
    dd, tq, n16 = off_expected(1.05)
    assert abs(tq - 12.4127) < 1e-3 and abs(n16 - 15.4667) < 1e-3  # the hand-derived anchors
    n = row_numbers(region(two_pass_report, r"MTP\s+OFF"), 260096)
    for w in (dd, 12.41, 12.41 / dd, 15.47, 15.47 / dd):
        assert has(n, w), (w, n)
    # the losing candidate of the TQ4 min (mma_tq4) must not have been used
    fixed = 1e3 / dd - 16 * sub("native16", "1", 1.05, 260096)
    wrong_tq = 1e3 / (fixed + 16 * sub("mma_tq4", "1", 1.05, 260096))
    assert abs(wrong_tq - tq) > 0.1  # the instrument can tell them apart
    assert not has(n, wrong_tq)


# class: reproduces a failure the specification fixes ("interpolating over sub-cap checkpoints only")
def test_projection_ignores_the_cap_checkpoint(two_pass_report):
    s = 1.05
    _, with_cap = on_expected(260096, s, ts=TS)
    _, sub_cap = on_expected(260096, s, ts=SUBCAP)
    assert abs(with_cap["mma_tq4"] - sub_cap["mma_tq4"]) > 1.0  # the instrument can tell them apart
    n = row_numbers(region(two_pass_report, r"MTP\s+ON", r"MTP\s+OFF"), 260096)
    assert has(n, sub_cap["mma_tq4"]) and not has(n, with_cap["mma_tq4"])


# class: new behaviour ("whichever exist")
@pytest.mark.parametrize("which,scale", [("mma-1", 1.0), ("mma-2", 1.1)])
def test_single_pass_uses_that_pass_only(tmp_path, which, scale):
    out = generate(write_run(tmp_path, {which: make_pass(scale)}))
    rows = timing_rows(out)[(131072, 3)]
    want = [mean_ms(a, 3, 131072, scale) for a in ARMS]
    assert any(all(abs(r[i] - want[i]) <= TOL for i in range(5)) for r in rows)
    dd, tps = on_expected(131072, scale)
    n = row_numbers(region(out, r"MTP\s+ON", r"MTP\s+OFF"), 131072)
    assert has(n, tps["mma_tq4"]) and has(n, tps["mma_n16"])
    # nothing to compare a single pass with: no drift ratio is printed
    assert not [ln for ln in out.splitlines() if "drift" in ln.lower() and NUM.search(ln)]


# class: new behaviour
def test_pass_to_pass_drift_reported_for_two_passes(two_pass_report):
    lines = [ln for ln in two_pass_report.splitlines() if "drift" in ln.lower()]
    assert lines, "no pass-to-pass drift line"
    assert any(re.search(r"1\.1(0|00)?\b", ln) for ln in lines), lines  # mma-2 / mma-1 = 1.10 for every arm


# class: new behaviour
def test_accuracy_section_counts_per_pass(tmp_path):
    p1 = make_pass(1.0, sweep_fail=2)  # 18 / 20
    p2 = make_pass(1.1)  # 20 / 20
    assert (p1["meta"]["mma_accuracy"]["n"], p1["meta"]["mma_accuracy"]["n_pass"]) == (20, 18)
    out = generate(write_run(tmp_path, {"mma-1": p1, "mma-2": p2}))
    sec = "\n".join(region(out, r"accura"))
    assert re.search(r"\b18\s*/\s*20\b", sec) and re.search(r"\b20\s*/\s*20\b", sec), sec
    for name in ("N1", "N2", "N3"):
        assert name in sec


# class: new behaviour ("report failed controls": a control that passes A1 is a failed control)
def test_accuracy_section_reports_a_failed_control(tmp_path):
    ok = generate(write_run(tmp_path, {"mma-1": make_pass(1.0), "mma-2": make_pass(1.1)}))
    d2 = tmp_path / "bad"
    d2.mkdir()
    bad = generate(write_run(d2, {"mma-1": make_pass(1.0, bad_control=("N3", "mma_n16")), "mma-2": make_pass(1.1)}))
    sec_ok, sec_bad = "\n".join(region(ok, r"accura")), "\n".join(region(bad, r"accura"))
    assert sec_ok != sec_bad
    n3_bad = [ln for ln in sec_bad.splitlines() if "N3" in ln]
    n3_ok = [ln for ln in sec_ok.splitlines() if "N3" in ln]
    assert n3_bad != n3_ok
    assert any("true" in ln.lower() for ln in n3_bad), n3_bad  # the control's pass value (True = control failed to fail)
    assert not any("true" in ln.lower() for ln in sec_ok.splitlines() if re.search(r"\bN[123]\b", ln))


# class: new behaviour (checkpoint accuracy failures must not be silent)
def test_accuracy_section_reports_a_failing_checkpoint(tmp_path):
    ok = generate(write_run(tmp_path, {"mma-1": make_pass(1.0), "mma-2": make_pass(1.1)}))
    d2 = tmp_path / "bad"
    d2.mkdir()
    bad = generate(write_run(d2, {"mma-1": make_pass(1.0, bad_checkpoint=(131072, 4, "mma_tq4")), "mma-2": make_pass(1.1)}))
    assert "\n".join(region(bad, r"accura")) != "\n".join(region(ok, r"accura"))


# class: preserves an invariant (generated output is a pure function of the run dir)
def test_generator_is_deterministic(tmp_path):
    d = write_run(tmp_path, {"mma-1": make_pass(1.0), "mma-2": make_pass(1.1)})
    assert generate(d) == generate(d)


# ================================================================ spec v1.2 additions
FORWARD = list(ARMS)
REVERSE = list(reversed(ARMS))


def with_order(data, order):
    data = copy.deepcopy(data)
    data["meta"]["arm_order"] = list(order)
    return data


def run_report(run_dir):
    return subprocess.run([sys.executable, str(REPORT), str(run_dir)], capture_output=True, text=True, timeout=120)


def mismatch_edits():
    """name -> function that edits a pass's JSON in place so its provenance differs from make_pass()'s."""
    def head(d):
        d["meta"]["fork"]["head"] = "fedcba9876543210"

    def mlx(d):
        d["meta"]["mlx"] = "0.99.0"

    def arch(d):
        d["meta"]["device"]["architecture"] = "applegpu_g16s"

    def ts_dropped(d):
        d["checkpoints"] = [c for c in d["checkpoints"] if c["T"] != 131072]

    def ts_changed(d):
        d["checkpoints"][1]["T"] = 131584

    return {"fork.head": head, "mlx": mlx, "device.architecture": arch, "checkpoint-T-dropped": ts_dropped,
            "checkpoint-T-changed": ts_changed}


# class: new behaviour (spec v1.2: refuse to combine passes with differing provenance; nonzero exit and a message)
@pytest.mark.parametrize("which", list(mismatch_edits()))
@pytest.mark.parametrize("edited", ("mma-1", "mma-2"))
def test_report_refuses_passes_with_differing_provenance(tmp_path, which, edited):
    passes = {"mma-1": with_order(make_pass(1.0), FORWARD), "mma-2": with_order(make_pass(1.1), REVERSE)}
    mismatch_edits()[which](passes[edited])
    r = run_report(write_run(tmp_path, passes))
    assert r.returncode != 0, f"combined passes that differ in {which}"
    assert (r.stderr + r.stdout).strip(), "refused without a message"
    assert "Traceback" not in r.stderr, "the refusal must be a deliberate message, not a crash"


# class: new behaviour (the message names what differs)
@pytest.mark.parametrize("which,word", [("fork.head", "fork"), ("mlx", "mlx"), ("device.architecture", "architecture"),
                                        ("checkpoint-T-dropped", "checkpoint")])
def test_report_refusal_names_the_differing_field(tmp_path, which, word):
    passes = {"mma-1": make_pass(1.0), "mma-2": make_pass(1.1)}
    mismatch_edits()[which](passes["mma-2"])
    r = run_report(write_run(tmp_path, passes))
    assert r.returncode != 0 and word in (r.stderr + r.stdout).lower()


# class: preserves an invariant (identical provenance, different timings and arm orders still combine)
def test_report_combines_passes_with_identical_provenance(tmp_path):
    d = write_run(tmp_path, {"mma-1": with_order(make_pass(1.0), FORWARD), "mma-2": with_order(make_pass(1.1), REVERSE)})
    assert run_report(d).returncode == 0


# class: new behaviour (a single pass has nothing to differ from)
def test_report_single_pass_is_not_refused(tmp_path):
    assert run_report(write_run(tmp_path, {"mma-2": make_pass(1.1)})).returncode == 0


def order_segments(text):
    """{pass name: text following its first mention on any line up to the next pass name on that line}."""
    segs = {}
    for ln in text.splitlines():
        parts = re.split(r"(mma-[12])\b", ln)
        for i in range(1, len(parts) - 1, 2):
            segs.setdefault(parts[i], []).append(parts[i + 1])
    return segs


def in_order(seg, names):
    pos = 0
    for n in names:
        j = seg.find(n, pos)
        if j < 0:
            return False
        pos = j + len(n)
    return True


# class: new behaviour (spec v1.2: the report prints each pass's meta.arm_order)
def test_report_prints_each_passes_arm_order(tmp_path):
    out = generate(write_run(tmp_path, {"mma-1": with_order(make_pass(1.0), FORWARD),
                                        "mma-2": with_order(make_pass(1.1), REVERSE)}))
    segs = order_segments(out)
    assert any(in_order(s, FORWARD) for s in segs["mma-1"]), "pass mma-1's forward order is not printed after its name"
    assert any(in_order(s, REVERSE) for s in segs["mma-2"]), "pass mma-2's reverse order is not printed after its name"
    assert not any(in_order(s, REVERSE) for s in segs["mma-1"]), "pass mma-1's order printed reversed"
    assert not any(in_order(s, FORWARD) for s in segs["mma-2"]), "pass mma-2's order printed forward"


# class: new behaviour (a pass whose order is not recorded does not crash the report)
def test_report_tolerates_a_pass_without_arm_order(tmp_path):
    assert "arm_order" not in make_pass(1.0)["meta"]
    generate(write_run(tmp_path, {"mma-1": make_pass(1.0)}))


def a3_count(out):
    return len(re.findall(r"A3\W+holds", out, re.I))


def controls_variant(edit):
    d = make_pass(1.0)
    edit(d["meta"]["mma_accuracy"]["controls"])
    return d


def drop_one(c):
    c.pop()  # N3 mma_n16 missing


def duplicate_one(c):
    c.append(dict(c[0]))  # seven rows: N1 mma_tq4 twice


def replace_with_duplicate(c):
    c[-1] = dict(c[0])  # six rows, but N1 mma_tq4 twice and N3 mma_n16 missing


def one_passes(c):
    c[2]["pass"] = True  # N2 mma_tq4 did not fail A1


def extra_control(c):
    c.append({"name": "N4", "arm": "mma_tq4", "rel_err": 0.9, "pass": False})


def no_controls(c):
    c.clear()


A3_BAD = {"missing": drop_one, "duplicated-seven": duplicate_one, "duplicated-six": replace_with_duplicate,
          "one-passing": one_passes, "unexpected-extra": extra_control, "none": no_controls}


# class: new behaviour (spec v1.2: A3 is stated to hold only with exactly the six controls, none duplicated, each pass False)
def test_report_states_a3_holds_for_exactly_the_six_failing_controls(tmp_path):
    assert len(make_pass(1.0)["meta"]["mma_accuracy"]["controls"]) == 6
    out = generate(write_run(tmp_path, {"mma-1": make_pass(1.0), "mma-2": make_pass(1.1)}))
    assert a3_count(out) == 2  # one statement per pass


# class: new behaviour (A3 not shown for a pass whose controls are incomplete / duplicated / unexpected / one passing)
@pytest.mark.parametrize("variant", list(A3_BAD))
def test_report_does_not_state_a3_holds_for_a_bad_control_set(tmp_path, variant):
    bad = controls_variant(A3_BAD[variant])
    out = generate(write_run(tmp_path, {"mma-1": bad, "mma-2": make_pass(1.1)}))
    assert a3_count(out) == 1, f"A3 stated for {2 - a3_count(out)} bad pass(es) ({variant})"  # only pass mma-2's good set


# class: new behaviour (the same for a single bad pass alone: no A3 statement at all)
@pytest.mark.parametrize("variant", list(A3_BAD))
def test_report_single_bad_pass_states_no_a3(tmp_path, variant):
    out = generate(write_run(tmp_path, {"mma-1": controls_variant(A3_BAD[variant])}))
    assert a3_count(out) == 0
