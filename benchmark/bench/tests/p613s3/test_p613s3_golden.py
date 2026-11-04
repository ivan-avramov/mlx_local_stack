"""Golden counts on the committed data (marker `p613s3_golden`): the packet set of the contract's "Golden" section.

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.

Reads `benchmark/results/p426/` (B8.json, wave2/), `benchmark/m62/universe.json`, the `evidence` commit `b6ec7819` through the
shared git objects, and the exercise start trees under `$POLYGLOT_DIR` (read-only; the value is never printed). The export golden
also reads the box's judges file. A missing input skips with the reason (never a silent pass).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from bench.tests.p613s3 import s3world as S
from bench.tests.p613s3.test_p613s3_export import numbers
from bench.tests.p613s3.test_p613s3_select import exc, ids_of, n_of, pairs

pytestmark = pytest.mark.p613s3_golden

EVIDENCE_REF = "b6ec7819"
RESULTS = S.BENCH_DIR / "results" / "p426"


@pytest.fixture(scope="module")
def real():
    top = S.git(S.BENCH_DIR, "rev-parse", "--show-toplevel")
    try:
        S.git(top, "cat-file", "-e", f"{EVIDENCE_REF}^{{commit}}")
    except RuntimeError:
        pytest.skip("evidence commit b6ec7819 is not in this repository's objects")
    poly = os.environ.get("POLYGLOT_DIR")
    if not poly or not (Path(poly) / "python" / "exercises" / "practice").is_dir():
        pytest.skip("POLYGLOT_DIR is not set to the exercise start trees")
    return dict(top=top, poly=Path(poly), b8=json.loads((RESULTS / "B8.json").read_text()),
                universe=S.BENCH_DIR / "m62" / "universe.json")


def judges_file():
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "mlx_local_stack" / "judges.json"


# class: new-behaviour (A7 packet set on the committed B8: s1 11, s2 10)
def test_golden_a7_select(real, panel):
    items, excluded = panel.a7_select(RESULTS, real["b8"])
    got = pairs(items)
    assert len(got) == 21
    assert sum(1 for s, _ in got if s == "s1") == 11 and sum(1 for s, _ in got if s == "s2") == 10


# class: new-behaviour (exclusions: identical s1 30 / s2 31; one-arm-pass s1 go/bottle-song, s2 python/pov + python/book-store;
# neither-pass s1 1 / s2 0; no rejected key)
def test_golden_a7_excluded(real, panel):
    _, excluded = panel.a7_select(RESULTS, real["b8"])
    assert n_of(exc(excluded, "s1", "identical")) == 30 and n_of(exc(excluded, "s2", "identical")) == 31
    assert ids_of(exc(excluded, "s1", "one-arm-pass")) == {"go/bottle-song"}
    assert ids_of(exc(excluded, "s2", "one-arm-pass")) == {"python/pov", "python/book-store"}
    assert n_of(exc(excluded, "s1", "neither-pass")) == 1 and n_of(exc(excluded, "s2", "neither-pass")) == 0
    assert n_of(exc(excluded, "s1", "rejected key")) == 0 and n_of(exc(excluded, "s2", "rejected key")) == 0


# class: invariant (both-pass = identical + packets = 41 / 41; go/crypto-square is the s1 neither-pass key, never a packet)
def test_golden_both_pass_totals(real, panel):
    items, excluded = panel.a7_select(RESULTS, real["b8"])
    assert n_of(exc(excluded, "s1", "identical")) + sum(1 for s, _ in pairs(items) if s == "s1") == 41
    assert n_of(exc(excluded, "s2", "identical")) + sum(1 for s, _ in pairs(items) if s == "s2") == 41
    assert ("s1", "go/crypto-square") not in pairs(items)


# class: new-behaviour (all 21 real packets build against the evidence commit and the real start trees; every hash verifies)
def test_golden_every_real_packet_builds(real, panel):
    items, _ = panel.a7_select(RESULTS, real["b8"])
    for item in sorted(pairs(items)):
        p = panel.a7_packet(RESULTS, real["b8"], item, EVIDENCE_REF, real["poly"], real["universe"], real["top"])
        assert p["len_off"] > 0 and p["len_on"] > 0
        assert "both solutions pass every test" in (p["task"] + p["off"] + p["on"]).lower()


# class: new-behaviour (export on the real data: 21 packets x 2 judges x 2 orders = 84, FROZEN.json, no leak, Wave 1 eligible identical 162, A1 96)
def test_golden_export_84_verdicts_planned(real, tmp_path):
    judges = judges_file()
    if not judges.is_file():
        pytest.skip("the box's judges.json is not present")
    out = tmp_path / "panel"
    proc = S.run_cli("bench.p426_panel", ["a7-export", "--results-root", RESULTS, "--b8", RESULTS / "B8.json", "--evidence-ref",
                                          EVIDENCE_REF, "--repo", real["top"], "--polyglot-root", real["poly"], "--universe",
                                          real["universe"], "--judges", judges, "--out", out])
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert len(S.packets_of(out)) == 84 and len(S.manifest_of(out)) == 84
    nums = list(numbers(json.loads((out / "FROZEN.json").read_text())))
    assert 84 in nums and 162 in nums and 96 in nums          # E3: Wave 1 eligible identical 162 = A1 96 + A2 40 + A3 20 + A4 6
    frozen = json.loads((out / "FROZEN.json").read_text())
    assert frozen["wave1"]["not_both_correct"] == 4 and frozen["wave1"]["per_axis"]["A1"]["not_both_correct"] == 4
    assert frozen["counts"]["wave1_not_both_correct"] == 4
    for packet in S.packets_of(out):
        text = packet.read_text().lower()
        for needle in ("p426", "drafter", "caslca/", "/users/", "/private/", "qwen3.8"):  # allow-shorthand: a leak-scan needle
            assert needle not in text, (needle, packet.name)
        assert not re.search(r"\bmtp\b", text), packet.name
    assert {p.parent.parent.name for p in S.packets_of(out)} == {j["label"] for j in json.loads(judges.read_text())["text"]}
