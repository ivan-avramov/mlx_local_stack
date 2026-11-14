"""M76 B7 (spec v1.1) — simulation properties: `bench.m76_sim` CLI / `calibrate` / `recheck`, and the §8 rule's realised
false-PASS at a 10 pp loss.

Reduced replications throughout (the spec's 20,000-replication runs take up to an hour); every statistical bound here is
correspondingly TOLERANT and says so. Class (c) = the specification does not name the argument / return shape; those
tests discover it from `--help` / `inspect.signature` and fail with a clear message if it cannot be found.
"""
import inspect
import json
import random
import re
import subprocess
import sys
from pathlib import Path

import pytest

BENCH_DIR = Path(__file__).resolve().parents[2]          # .../benchmark
PY = sys.executable
_CANDIDATES = (0.025, 0.02, 0.015, 0.0125, 0.01, 0.0075, 0.005, 0.0035, 0.0025, 0.001)


# ----------------------------------------------------------------------------- the §8 rule at A1's final look
def test_a1_final_look_false_pass_at_10pp_loss_reduced_replications():  # (b) own data model; tolerant bound
    """§8 rule = PASS iff point >= -5 pp and the lower end of the 95 % two-sided interval (one-sided alpha 0.025) >= -10 pp,
    composed from `paired_delta` (interval_alpha 0.05) and `m76_rule.verdict`. Data: 300 items, N16 passes every
    item; the TQ4 arm fails a random 10 % of items (true loss 10 pp, discordance 10 %). 150 replications, 600 bootstrap
    iterations each. The pre-registered upper MC bound is 0.025 at 20,000 replications; with 150 replications the
    tolerant bound used here is 0.025 + 3 * sqrt(0.025 * 0.975 / 150) = 0.063."""
    from bench.m76_rule import verdict
    from bench.stats import paired_delta
    rng = random.Random(426)
    reps, false_pass = 150, 0
    for r in range(reps):
        n16 = {i: [1] for i in range(300)}
        x = {i: [0 if rng.random() < 0.10 else 1] for i in range(300)}
        d = paired_delta(x, n16, iters=600, seed=426 + r, interval_alpha=0.05)
        v = verdict(d["delta"], d["lo"], d["hi"])
        name = (v[0] if isinstance(v, (tuple, list)) else v.get("verdict") if isinstance(v, dict) else v)
        false_pass += str(name).upper().startswith("PASS")
    assert false_pass / reps <= 0.063, false_pass / reps


def test_a1_final_look_power_at_no_loss_reduced_replications():  # (b) own data model; tolerant bound
    """Same composition at true loss 0 (base rate 0.5, symmetric 6 % flips): PASS must be the typical outcome (>= 0.5 is
    the §8 look-keeping bar; tolerant bound 0.5 with 60 replications)."""
    from bench.m76_rule import verdict
    from bench.stats import paired_delta
    rng = random.Random(7)
    reps, passes = 60, 0
    for r in range(reps):
        n16, x = {}, {}
        for i in range(300):
            p = 1 if rng.random() < 0.5 else 0
            n16[i] = [p]
            x[i] = [1 - p if rng.random() < 0.06 else p]
        # base rate 0.5 and a symmetric 6 % flip => true loss 0
        d = paired_delta(x, n16, iters=600, seed=r)
        v = verdict(d["delta"], d["lo"], d["hi"])
        name = (v[0] if isinstance(v, (tuple, list)) else v.get("verdict") if isinstance(v, dict) else v)
        passes += str(name).upper().startswith("PASS")
    assert passes / reps >= 0.5, passes / reps


# ----------------------------------------------------------------------------- CLI end to end
def _flag(helptext, *patterns):
    for pat in patterns:
        m = re.search(pat, helptext)
        if m:
            return m.group(0)
    return None


def _help():
    out = subprocess.run([PY, "-m", "bench.m76_sim", "--help"], cwd=BENCH_DIR, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-800:]
    return out.stdout


def _run_cli(out_dir, reps, seed=426, extra=()):
    h = _help()
    rep_flag = _flag(h, r"--(?:n[-_])?rep(?:lication)?s?\b", r"--replications?\b", r"--reps?\b")
    assert rep_flag, f"cannot find a replications option in --help:\n{h[:1500]}"
    cmd = [PY, "-m", "bench.m76_sim", "--out", str(out_dir), rep_flag, str(reps)]
    if "--seed" in h:
        cmd += ["--seed", str(seed)]
    cmd += list(extra)
    res = subprocess.run(cmd, cwd=BENCH_DIR, capture_output=True, text=True, timeout=3000)
    assert res.returncode == 0, res.stderr[-1500:]
    return Path(out_dir)


def test_cli_end_to_end_small_reps_writes_report(tmp_path):  # (c) options unspecified; discovered from --help
    out = _run_cli(tmp_path / "o", reps=100)
    md, js = out / "REPORT.md", out / "report.json"
    assert md.is_file() and js.is_file()
    data = json.loads(js.read_text())
    text = md.read_text()
    for ax in ("A1", "A5", "A7", "A8"):
        assert ax in text, ax
    blob = json.dumps(data)
    assert "100" in blob, "report records its replication count"
    assert "426" in blob, "report records its seed"


def test_cli_report_regenerates_byte_identically(tmp_path):  # (c) acceptance 2 / 8
    a = _run_cli(tmp_path / "a", reps=100)
    b = _run_cli(tmp_path / "b", reps=100)
    assert (a / "REPORT.md").read_bytes() == (b / "REPORT.md").read_bytes()
    assert (a / "report.json").read_bytes() == (b / "report.json").read_bytes()


def test_cli_different_seed_changes_report(tmp_path):  # (c)
    if "--seed" not in _help():
        pytest.fail("no --seed option in --help (cannot test seed dependence)")
    a = _run_cli(tmp_path / "a", reps=100, seed=426)
    b = _run_cli(tmp_path / "b", reps=100, seed=427)
    assert (a / "report.json").read_bytes() != (b / "report.json").read_bytes()


def test_report_states_a5_n_alpha_star_and_plan(tmp_path):  # (c) acceptance 8: keywords only, schema unspecified
    out = _run_cli(tmp_path / "o", reps=100)
    text = (out / "REPORT.md").read_text()
    lowered = text.lower()
    assert re.search(r"α\*|alpha\*|alpha_star|alpha-star", lowered)
    assert "plan" in lowered
    assert re.search(r"A5[^\n]*\bn\b|\bn\b[^\n]*A5", text)


def test_report_false_pass_of_every_kept_look_within_alpha(tmp_path):  # (c) acceptance 2; schema walked generically
    """AMENDED (delivery 3). Walk report.json: every mapping that marks a final look kept / safe (a key `kept`, `keep`,
    `look_kept` or `final_safe` whose value is exactly True) and carries a false-PASS-at-10 upper MC bound must have that
    bound within alpha. Delivery 2's walker counted the string `"final": "single"` as "kept" and ran at 100 replications,
    where the Wilson bound of even 0 successes is ~0.037. Now: 3,000 replications and a TOLERANT bound
    0.025 + 2 * sqrt(0.025 * 0.975 / 3000) = 0.0307 (the pre-registered 0.025 applies at the 20,000-replication run)."""
    reps = 3000
    out = _run_cli(tmp_path / "o", reps=reps)
    data = json.loads((out / "report.json").read_text())
    tol = 0.025 + 2 * (0.025 * 0.975 / reps) ** 0.5
    seen = []

    def walk(o):
        if isinstance(o, dict):
            keys = {k.lower(): k for k in o}
            kept = any(o[keys[k]] is True for k in keys if k in ("kept", "keep", "look_kept", "final_safe"))
            ub = next((o[keys[k]] for k in keys if re.search(r"false.?pass.*(10).*(upper|ub|hi)|(upper|ub).*false.?pass.*10", k)), None)
            if kept and isinstance(ub, (int, float)) and not isinstance(ub, bool):
                seen.append(ub)
                assert ub <= tol, (ub, tol)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    assert seen, "no kept/safe look with a false-PASS(10) upper bound found in report.json (schema not discoverable)"


# ----------------------------------------------------------------------------- calibrate / recheck
def _kw_for(fn, reps):
    sig = inspect.signature(fn)
    for name in sig.parameters:
        if re.fullmatch(r"(n_?)?rep(lication)?s?|n_?reps?|replications", name):
            return {name: reps}
    pytest.fail(f"{fn.__name__} has no replications parameter in {sig}")


def _alpha_of(res):
    if isinstance(res, dict):
        for k in ("alpha_star", "alpha", "alpha_applied", "alpha_star_applied"):
            if k in res:
                return res[k]
    if isinstance(res, (int, float)):
        return res
    if hasattr(res, "alpha_star"):
        return res.alpha_star
    raise AssertionError(f"cannot read alpha* from {res!r}")


def test_calibrate_deterministic_and_candidate_valued():  # (c) reduced replications; parameter discovered
    """AMENDED (delivery 4). At 150 replications no candidate can be proved safe, so alpha* may legitimately be None
    (A8 on the v1.2 capped grid gives None at 150 and 0.005 at 20,000). Asserted: alpha* is None or one of the ten
    candidates, and the whole result is deterministic."""
    from bench import m76_sim
    kw = _kw_for(m76_sim.calibrate, 150)
    r1 = m76_sim.calibrate("A8", **kw)
    r2 = m76_sim.calibrate("A8", **kw)
    assert r1 == r2
    a = _alpha_of(r1)
    assert a is None or any(abs(a - c) < 1e-12 for c in _CANDIDATES), a


def test_calibrate_more_replications_never_hides_unsafety_a7_a8_candidates():  # (c)
    """AMENDED (delivery 3; the name is kept). Delivery 2 asserted that A7 at 150 replications returns a candidate. At 150
    replications the Wilson upper bound of any non-zero count exceeds 0.025, so a legitimate result is "no candidate
    provable" (alpha* None). The property the specification supports: alpha* is None or one of the ten candidates, and
    the v1.2 capped A8 grid and the A7 grid both obey it; the answer is deterministic."""
    from bench import m76_sim
    kw = _kw_for(m76_sim.calibrate, 150)
    for ax in ("A7", "A8"):
        r1 = m76_sim.calibrate(ax, **kw)
        a = _alpha_of(r1)
        assert a is None or any(abs(a - c) < 1e-12 for c in _CANDIDATES), (ax, a)
        assert _alpha_of(m76_sim.calibrate(ax, **kw)) == a


def _rows(rate, disc, direction, n=80, sessions=("s1", "s2"), seed=3):
    """N16 rows fixed by (rate, seed); X = N16 except `int(disc * cells)` discordant item-sessions, drawn from the
    N16-pass cells (direction 'loss': X worse) or the N16-fail cells (direction 'gain': X better)."""
    rng = random.Random(seed)
    n16 = {i: {s: int(rng.random() < rate) for s in sessions} for i in range(n)}
    x = {i: dict(n16[i]) for i in n16}
    want = 1 if direction == "loss" else 0
    pool = [(i, s) for i in n16 for s in sessions if n16[i][s] == want]
    k = int(disc * n * len(sessions))
    assert len(pool) >= k, "test data cannot realise this discordance"
    rng.shuffle(pool)
    for (i, s) in pool[:k]:
        x[i][s] = 1 - want
    return n16, x


def _recheck(n16, x, tmp_path, reps=150):
    from bench import m76_sim
    sig = inspect.signature(m76_sim.recheck)
    kw = {}
    for name in sig.parameters:
        if re.fullmatch(r"(n_?)?rep(lication)?s?|n_?reps?|replications", name):
            kw[name] = reps
        if re.fullmatch(r"out(_?dir)?|output(_?dir)?|dest(ination)?|path|results_dir", name):
            kw[name] = str(tmp_path)
    return m76_sim.recheck("A8", n16, x, **kw)


def test_recheck_never_reads_arm_effect(tmp_path):  # (c) spec criterion 6; record shape unspecified -> deep equality
    """Identical N16 rows and discordance count; X worse in one pair, X better in the other: identical record."""
    n16, x_loss = _rows(0.5, 0.20, "loss")
    n16b, x_gain = _rows(0.5, 0.20, "gain")
    assert n16 == n16b
    ra = _recheck(n16, x_loss, tmp_path / "a")
    rb = _recheck(n16, x_gain, tmp_path / "b")
    assert ra == rb


def test_recheck_inside_hull_keeps_committed_alpha_and_outside_never_loosens(tmp_path):  # (c) criterion 6
    n16, x = _rows(0.5, 0.20, "loss", seed=4)
    inside = _alpha_of(_recheck(n16, x, tmp_path / "in"))
    n16o, xo = _rows(0.05, 0.02, "gain", seed=4)             # pass rate 0.05 and discordance 0.02: outside the A8 grid hull
    outside = _alpha_of(_recheck(n16o, xo, tmp_path / "out"))
    assert outside <= inside + 1e-12
    assert any(abs(inside - c) < 1e-12 for c in _CANDIDATES)
    assert any(abs(outside - c) < 1e-12 for c in _CANDIDATES)


def test_recheck_writes_json_record(tmp_path):  # (c) criterion 6: JSON record under recheck-<axis>.json
    n16, x = _rows(0.5, 0.20, "loss", seed=4)
    _recheck(n16, x, tmp_path / "r")
    files = list((tmp_path / "r").glob("recheck-*.json")) if (tmp_path / "r").exists() else []
    assert files, "recheck did not write recheck-<axis>.json under the output location passed to it"
    json.loads(files[0].read_text())
