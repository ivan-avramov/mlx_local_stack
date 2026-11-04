"""Golden numbers on the COMMITTED data (benchmark/results, read-only; every output goes to tmp_path).

Marked `p613s2_golden` (registered in this directory's conftest.py). Class of every test is stated above it.
The contract's golden numbers (counted 2026-11-03) are asserted twice where possible: re-derived straight from the committed rows
(independent of the code under test) and read out of B8 / the sheet. The rule-6 / registry checks need the repository's object
store to hold the Wave 1 heads and the Wave 2 OFF commit; when a commit is not in this checkout the dependent tests SKIP with
the missing sha named (never pass silently).
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path

import pytest

from bench.tests.p613 import sigview as SV
from bench.tests.p613s2 import w1view as V

pytestmark = pytest.mark.p613s2_golden

BENCH = Path(__file__).resolve().parents[3]
RESULTS = BENCH / "results"
P426 = RESULTS / "p426"
W1 = P426 / "wave1.s2"
REPO = Path(__file__).resolve().parents[4]
ENTRY = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
EDIR = RESULTS / ENTRY
BENCH_OF = {"math500": "math500", "cjudge": "cjudge", "vision": "vision_gate", "reasoning": "reasoning"}


def jl(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def rows(kind, arm, block):
    t = f"p426s2-{arm}-{block}"
    if kind == "reasoning":
        return json.loads((EDIR / f"reasoning.{t}.json").read_text())["records"][0]["rows"]
    return jl(EDIR / f"{BENCH_OF[kind]}.{t}.jsonl")


def sha(x):
    return hashlib.sha256(x.encode("utf-8")).hexdigest()


def commits_present():
    frozen = json.loads((W1 / "run" / "frozen.s2.json").read_text())
    v8 = json.loads((P426 / "wave2" / "run" / "v8_base.json").read_text())
    return [frozen["stack_head_off"], frozen["stack_head_on"], v8["off_commit"]]


def missing_commits():
    out = []
    for c in commits_present():
        r = subprocess.run(["git", "cat-file", "-e", f"{c}^{{commit}}"], cwd=REPO, capture_output=True)
        if r.returncode != 0:
            out.append(c)
    return out


@pytest.fixture(scope="module")
def gold():
    """A thunk (built inside the test body, so a missing interface FAILS the test); the result is cached per module."""
    cache = []

    def build():
        if not cache:
            miss = missing_commits()
            if miss:
                pytest.skip(f"commit(s) {miss} are not in this checkout's object store (rule 2b / rule 6 need them)")
            import importlib
            verify = importlib.import_module("bench.p426_verify")
            signals = importlib.import_module("bench.p426_signals")
            try:
                with pytest.MonkeyPatch.context() as mp:
                    from bench import generate
                    mp.setattr(generate, "RESULTS", RESULTS)
                    b8 = verify.verify_all(P426, RESULTS, REPO)
                    sig = signals.compute_all(P426, RESULTS, b8)
                cache.append((b8, sig))
            except BaseException as exc:      # noqa: BLE001
                cache.append(exc)
        if isinstance(cache[0], BaseException):
            raise cache[0]
        return cache[0]
    return build


# ============================================================================================ independent counts (committed data)
# class: invariant (the contract's golden counts, re-derived from the committed rows)
def test_committed_counts_content_sha_and_scrub():
    n_content = 0
    for kind in ("math500", "cjudge"):
        for arm in ("off", "on"):
            for block in ("b1", "b2"):
                for r in rows(kind, arm, block):
                    assert r["content_sha256"] == sha(r["content"])
                    n_content += 1
    assert n_content == 280
    n_files = n_smoke = 0
    for leg in sorted(p for p in W1.iterdir() if p.is_dir() and p.name not in ("archive", "run")):
        files = json.loads((leg / "SCRUB_MANIFEST.json").read_text())["files"]
        for path, d in files.items():
            assert path.startswith("benchmark/results/")
            assert hashlib.sha256((RESULTS / path[len("benchmark/results/"):]).read_bytes()).hexdigest() == d["published_sha256"]
            if "smoke" in leg.name:
                n_smoke += 1
            else:
                n_files += 1
    # the contract's "249 / 249" is the count over ALL wave1.s2 legs including the smoke legs (166 pair-leg files + 83 smoke files);
    # only the 166 belong to the 20 pair members (smokes are never read as members): this test pins both numbers
    assert (n_files, n_smoke, n_files + n_smoke) == (166, 83, 249)


# class: invariant (A1 strict == lenient on the committed rows: 49/50, 49/50, 47/50, 47/50, every row converged, identical outputs)
def test_committed_a1_counts():
    import re
    want = {("off", "b1"): 49, ("on", "b1"): 49, ("off", "b2"): 47, ("on", "b2"): 47}
    for (arm, block), n in want.items():
        rs = rows("math500", arm, block)
        assert len(rs) == 50 and all(r["converged"] is True for r in rs)
        score = json.loads((EDIR / f"math500.p426s2-{arm}-{block}.score.json").read_text())
        assert score["correct"] == n and score["acc_strict"] == score["acc"] == n / 50 and score["nonconv_kinds"] == {}
    for block in ("b1", "b2"):
        on = {r["id"]: r["content_sha256"] for r in rows("math500", "on", block)}
        off = {r["id"]: r["content_sha256"] for r in rows("math500", "off", block)}
        assert on == off


def geomean(xs):
    return math.exp(sum(math.log(x) for x in xs) / len(xs))


def ratios(kind, block, key):
    on = {key(r): r["decode_tps"] for r in rows(kind, "on", block)}
    off = {key(r): r["decode_tps"] for r in rows(kind, "off", block)}
    return [on[k] / off[k] for k in sorted(on)]


# class: invariant (the contract's golden decode / acceptance / M1 numbers, re-derived from the committed rows alone)
def test_committed_decode_acceptance_and_m1_numbers():
    ident = lambda r: r["id"]
    for kind, want in (("math500", (1.736, 1.729)), ("cjudge", (1.606, 1.543)), ("vision", (1.775, 1.727))):
        for block, x in zip(("b1", "b2"), want):
            assert round(geomean(ratios(kind, block, ident)), 3) == x, (kind, block)
    per_draw = [r for b in ("b1", "b2") for r in ratios("reasoning", b, lambda r: r["seed"])]
    # the contract says "A4 per draw 1.584-1.656"; the six committed draws are 1.615 1.623 1.584 | 1.656 1.634 1.528: both quoted
    # endpoints are real draws, but the minimum over all six is 1.528 (the quoted range is the b1 minimum to the b2 maximum)
    assert sorted(round(x, 3) for x in per_draw) == [1.528, 1.584, 1.615, 1.623, 1.634, 1.656]

    def frac(kind, block):
        rs = rows(kind, "on", block)
        return sum(r["draft"]["draft_n_accepted"] for r in rs), sum(r["draft"]["draft_n"] for r in rs)
    for kind, want in (("math500", (0.7490, 0.8038, 0.7666)), ("cjudge", (0.5869, 0.6128, 0.6015)), ("vision", (0.6343, 0.5996, 0.6168))):
        (a1, n1), (a2, n2) = frac(kind, "b1"), frac(kind, "b2")
        assert tuple(round(x, 4) for x in (a1 / n1, a2 / n2, (a1 + a2) / (n1 + n2))) == want, kind
    assert tuple(map(sum, zip(frac("math500", "b1"), frac("math500", "b2")))) == (106153, 138464)
    assert (frac("reasoning", "b1"), frac("reasoning", "b2")) == ((634, 708), (604, 680))
    for arm, block, peaks in (("off", "b1", (37658578482, 37557075522, 37935199774)), ("off", "b2", (37658578482, 37557075522, 37935199774)),
                              ("on", "b1", (37972876142, 37926799772, 38251713408)), ("on", "b2", (37972876142, 37926799772, 38251715456))):
        res = json.loads((W1 / f"m1-p426s2-{arm}-{block}" / "m1" / ENTRY / "result.json").read_text())
        q = res["requests"][0]["qualify"]["peaks"]
        assert (q["prefill"], q["decode"], q["retire"]) == peaks
    assert 37972876142 - 37658578482 == 314297660


# ================================================================================================================== B8 golden
# class: reproduces-failure (spec fixes it: 10 / 10 Wave 1 pairs accepted, all speed_valid)
def test_golden_b8_ten_pairs_accepted(gold):
    b8, _ = gold()
    w1 = V.wave1(b8)
    assert len(w1["pairs"]) == 10 and all(p["accepted"] for p in w1["pairs"]), [p["reasons"] for p in w1["pairs"] if not p["accepted"]]
    assert all(p["speed_valid"] is True for p in w1["pairs"])
    assert [p["accepted"] for p in b8["axes"]["A7"]["pairs"] if p.get("role") == "pair"] == [True, True]


# class: reproduces-failure (keys A1 50 + 50, A2 20 + 20, A3 10 + 10, A4 3 + 3, M1 1 + 1)
def test_golden_b8_key_counts(gold):
    b8, _ = gold()
    want = {"math500": 50, "cjudge": 20, "vision": 10, "reasoning": 3, "m1": 1}
    for kind, n in want.items():
        for block in ("b1", "b2"):
            p = V.pair(b8, kind, block)
            assert p["keys_accepted"] == n and p["keys_rejected"] == [], (kind, block)


# class: reproduces-failure (identical A1 50/50 x2, A2 20/20 x2, A3 10/10 x2, A4 3/3 x2: 166 / 166)
def test_golden_b8_identical_counts(gold):
    b8, _ = gold()
    n = of = 0
    for kind in ("math500", "cjudge", "vision", "reasoning"):
        for block in ("b1", "b2"):
            p = V.pair(b8, kind, block)
            assert p["identical"]["n"] == p["identical"]["of"] == p["keys_accepted"], (kind, block)
            n += p["identical"]["n"]
            of += p["identical"]["of"]
    assert (n, of) == (166, 166)


# class: reproduces-failure (SCRUB: all 249 files are re-verified (they are inputs of B8), content_sha256 280 / 280 recomputed)
def test_golden_b8_inputs_include_every_scrub_file(gold):
    b8, _ = gold()
    inputs = V.wave1(b8)["inputs"]
    n = 0
    for leg in sorted(p for p in W1.iterdir() if p.is_dir() and "smoke" not in p.name and p.name not in ("archive", "run")):
        for path in json.loads((leg / "SCRUB_MANIFEST.json").read_text())["files"]:
            rel = path[len("benchmark/results/"):]
            assert rel in inputs, rel
            n += 1
    assert n == 166     # the pair legs' SCRUB files (the contract's 249 also counts the 83 smoke-leg files; see the sibling test)
    assert not [k for k in inputs if "smoke" in k or "/archive/" in k or k.startswith("p426/wave1/")]


# class: reproduces-failure (rule 6: files == [main_models.yaml], flag true, entry_equal true, globals_equal true, 34 closure files, gitlinks equal)
def test_golden_cross_wave(gold):
    b8, _ = gold()
    c = b8["cross_wave"]
    assert c["files"] == ["main_models.yaml"] and c["flag"] is True
    assert c["entry_equal"] is True and c["globals_equal"] is True
    assert len(c["closure_files"]) == 34
    assert "src/mlx-vlm" not in c["files"] and "src/mlx-serve" not in c["files"]
    frozen = json.loads((W1 / "run" / "frozen.s2.json").read_text())
    v8 = json.loads((P426 / "wave2" / "run" / "v8_base.json").read_text())
    assert c["wave1_off"] == frozen["stack_head_off"] and c["wave2_off"] == v8["off_commit"]
    assert hashlib.sha256((W1 / "run" / "frozen.s2.json").read_bytes()).hexdigest().startswith("3c155062")


# ================================================================================================================== B6 golden
# class: reproduces-failure (A1: acc = acc_strict, .98 / .98 / .94 / .94, both blocks .96, conv 100 %, no exclusive solves)
def test_golden_a1_accuracy(gold):
    _, sig = gold()
    pool = V.axis_pool(sig, "A1")
    for x in (0.98, 0.94, 0.96, 1.0):
        assert V.has(pool, x, 1e-4), x
    assert "budget_hit" not in V.axis_text(sig, "A1")


# class: reproduces-failure (paired delta 0, CI [0, 0], loss bound 5.82 pp (n 50) and 2.95 pp (n 100), mde(50) .1772, mde(100) .1253)
def test_golden_a1_zero_discordance(gold):
    from bench import stats
    _, sig = gold()
    pool = V.axis_pool(sig, "A1")
    assert V.has(pool, 1 - 0.05 ** (1 / 50), 1e-4) and V.has(pool, 1 - 0.05 ** (1 / 100), 1e-4)
    assert round(1 - 0.05 ** (1 / 50), 4) == 0.0582 and round(1 - 0.05 ** (1 / 100), 4) == 0.0295
    assert V.has(pool, 0.1772, 1e-4) and V.has(pool, 0.1253, 1e-4)
    assert round(stats.mde(50), 4) == 0.1772 and round(stats.mde(100), 4) == 0.1253
    assert V.has(pool, 0.0)
    strs = SV.strings(V.axis_tree(sig, "A1"))
    assert SV.wash(strs) and not SV.shown(strs)


# class: reproduces-failure (permutation p 1.0; Holm over {A1, A7-s1, A7-s2}: m 3, every adjusted p 1.0)
def test_golden_family(gold):
    _, sig = gold()
    fam = SV.subtree(sig, "family")
    pool = SV.numbers(fam)
    assert V.has(pool, 3.0) and sum(1 for p in pool if abs(p - 1.0) < 1e-9) >= 3
    assert "complete" in SV.text(fam).lower() and "incomplete" not in SV.text(fam).lower()


# class: reproduces-failure (decode geomean ratio points: A1 1.736 / 1.729, A2 1.606 / 1.543, A3 1.775 / 1.727; A4 per draw 1.584-1.656)
def test_golden_decode_ratio_points(gold):
    _, sig = gold()
    ident = lambda r: r["id"]
    for axis, kind, want in (("A1", "math500", (1.736, 1.729)), ("A2", "cjudge", (1.606, 1.543)), ("A3", "vision", (1.775, 1.727))):
        for block, x in zip(("b1", "b2"), want):
            assert round(geomean(ratios(kind, block, ident)), 3) == x, (axis, block)
            assert V.axis_has(sig, axis, x, 1e-3), (axis, block, x)
    per_draw = [r for b in ("b1", "b2") for r in ratios("reasoning", b, lambda r: r["seed"])]
    assert round(min(per_draw), 3) == 1.528 and round(max(per_draw), 3) == 1.656      # see the sibling data test: the contract's lower end is 1.584
    for r in per_draw:
        assert V.axis_has(sig, "A4", r, 1e-3), r


# class: reproduces-failure (acceptance: A1 .7490 / .8038 / both .7666 (106153 / 138464); A2 .5869 / .6128 / .6015; A3 .6343 / .5996 / .6168;
#   A4 634/708 = .8955, 604/680 = .8882 = acceptance_pooled)
def test_golden_acceptance(gold):
    _, sig = gold()

    def frac(kind, block, top=lambda r: r["draft"]):
        rs = rows(kind, "on", block)
        return sum(top(r)["draft_n_accepted"] for r in rs), sum(top(r)["draft_n"] for r in rs)
    for axis, kind, want in (("A1", "math500", (0.7490, 0.8038, 0.7666)), ("A2", "cjudge", (0.5869, 0.6128, 0.6015)),
                             ("A3", "vision", (0.6343, 0.5996, 0.6168))):
        a1, n1 = frac(kind, "b1")
        a2, n2 = frac(kind, "b2")
        got = (a1 / n1, a2 / n2, (a1 + a2) / (n1 + n2))
        assert tuple(round(g, 4) for g in got) == want, (axis, got)
        for x in want:
            assert V.axis_has(sig, axis, x, 1e-4), (axis, x)
    a1, n1 = frac("math500", "b1")
    a2, n2 = frac("math500", "b2")
    assert (a1 + a2, n1 + n2) == (106153, 138464)
    for block, (k, n) in (("b1", (634, 708)), ("b2", (604, 680))):
        assert frac("reasoning", block) == (k, n)
        doc = json.loads((EDIR / f"reasoning.p426s2-on-{block}.json").read_text())
        assert doc["records"][0]["acceptance_pooled"] == round(k / n, 4)
        assert V.axis_has(sig, "A4", k / n, 1e-4)


# class: reproduces-failure (A2 conv 20/20 each arm and block; A3 self-PASS 10/10; A4 strict draws 3/3, budget hits 0)
def test_golden_a2_a3_a4_counts(gold):
    _, sig = gold()
    for arm in ("off", "on"):
        for block in ("b1", "b2"):
            assert all(r["converged"] is True for r in rows("cjudge", arm, block))
            assert all(r["verdict"] == "PASS" for r in rows("vision", arm, block))
            rs = rows("reasoning", arm, block)
            assert len(rs) == 3 and all(r["score"] == 1.0 and r["budget_hit"] is False and r["finish_reason"] == "stop" for r in rs)
    assert V.axis_has(sig, "A2", 20.0, 1e-9) and V.axis_has(sig, "A3", 10.0, 1e-9) and V.axis_has(sig, "A4", 3.0, 1e-9)
    assert "panel only (step 3)" in V.axis_text(sig, "A2")


# class: reproduces-failure (M1 peaks: OFF b1 = b2 prefill 37658578482 / decode 37557075522 / retire 37935199774; ON b1 ...; ON - OFF prefill +314297660)
def test_golden_m1(gold):
    _, sig = gold()
    pool = V.axis_pool(sig, "M1")
    want = [37658578482, 37557075522, 37935199774, 37972876142, 37926799772, 38251713408, 38251715456, 314297660]
    for v in want:
        assert any(abs(p - v) < 0.5 for p in pool), v
    for block, (on, off) in (("b1", (16.019, 13.361)), ("b2", (16.041, 13.412))):
        res = json.loads((W1 / f"m1-p426s2-on-{block}" / "m1" / ENTRY / "result.json").read_text())
        assert round(res["requests"][0]["qualify"]["rates"]["decode_tps"], 3) == on
        assert any(abs(p - on / off) < 2e-3 for p in pool), (block, on / off)
    assert any(abs(p - 0.314) < 6e-4 for p in pool)


# class: reproduces-failure (Wave 1 flags: acceptance < 0.70 for A2 (b1, b2, both) and A3 (b1, b2, both); cross-wave; NO other Wave 1 flag)
def test_golden_flags(gold):
    b8, sig = gold()
    pool = SV.flag_numbers(sig)
    txt = SV.flag_text(sig)
    for x in (0.5869, 0.6128, 0.6015, 0.6343, 0.5996, 0.6168):
        assert V.has(pool, x, 1e-4), x
    for x in (0.7490, 0.8038, 0.7666, 0.8955, 0.8882, 1.736, 1.729, 0.314):
        assert not V.has(pool, x, 1e-3), f"{x} must not be flagged"
    assert "main_models.yaml" in txt and b8["cross_wave"]["flag"] is True


# class: invariant (the A7 part of the sheet is the step-1 golden: s1 and s2 accepted, noise floor flips 0 / 5 in both arms)
def test_golden_a7_unchanged(gold):
    b8, sig = gold()
    assert [p["pair"] for p in b8["axes"]["A7"]["pairs"] if p.get("role") == "pair" and p["accepted"]] == ["s1", "s2"]
    nf = SV.subtree(sig, "noise")
    assert nf and V.has(SV.numbers(nf), 5.0, 1e-9) and V.has(SV.numbers(nf), 0.0, 1e-9)


# ====================================================================================================================== CLI
@pytest.fixture(scope="module")
def cli_runs(tmp_path_factory):
    miss = missing_commits()
    if miss:
        pytest.skip(f"commit(s) {miss} are not in this checkout's object store")

    class W:
        p426, rows_root, repo = P426, RESULTS, REPO
    out = {}
    for name in ("a", "b"):
        out[name] = V.all_cli(W, tmp_path_factory.mktemp("goldcli") / name)
    return out


# class: reproduces-failure (`all` on the committed data exits 0 and writes all three files)
def test_golden_all_cli_rc0(cli_runs):
    for name, (r1, r2, b8, md, js) in cli_runs.items():
        assert r1.returncode == 0, r1.stderr
        assert r2 is not None and r2.returncode == 0, r2.stderr if r2 else "not run"
        assert b8.is_file() and md.is_file() and js.is_file()


# class: reproduces-failure (byte-identical regeneration from the same committed inputs)
def test_golden_all_cli_byte_identical(cli_runs):
    a, b = cli_runs["a"], cli_runs["b"]
    for i in (2, 3, 4):
        assert a[i].read_bytes() == b[i].read_bytes(), a[i].name


# class: invariant (once the step-2 outputs are committed, `all` reproduces them byte for byte; before that the committed sheet is the step-1 sheet)
def test_golden_committed_outputs_are_the_all_outputs(cli_runs):
    committed_md = P426 / "SIGNALS.md"
    if "p613-step2" not in committed_md.read_text():
        pytest.skip("committed SIGNALS.md is still the step-1 (a7) sheet; this check starts to bind when step 2 commits its outputs")
    r1, r2, b8, md, js = cli_runs["a"]
    for name, path in (("B8.json", b8), ("SIGNALS.md", md), ("SIGNALS.json", js)):
        assert (P426 / name).read_bytes() == path.read_bytes(), name
