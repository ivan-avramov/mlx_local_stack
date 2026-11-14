"""M76 B3: the Wave 2 arm-equality pair gate under `lever=kv` (`bench.p426_receipt`), on receipts derived from the committed P426
S′ ON receipt (the real worker argv spelling) with the arm's KV flags inserted where mlx-serve builds them: the pair is accepted
only when the worker argvs differ by exactly `--kv-bits` / `--tq4-attention`, both MTP ON with the same drafter snapshot, and
everything else equal; the `mtp` gate is unchanged (golden: `test_m76_b3_impl_golden_mtp`)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from bench import p426_hooks as ph
from bench import p426_receipt as pr

BENCH = Path(__file__).resolve().parents[2]
P426 = BENCH / "results" / "p426"
MODES = {"x": "m72_exact", "v": "m72_v1"}


@pytest.fixture(scope="module")
def on_receipt():
    return json.loads((P426 / "wave2" / "tg1-p426-on-s1.a1" / "receipt.json").read_text())


def kv_receipt(base, arm, mutate=None):
    doc = copy.deepcopy({k: v for k, v in base.items() if k != "sha256"})
    w = doc["argv"]["worker"]
    if arm != "n16":
        w[w.index("--kv-quant-scheme"):w.index("--kv-quant-scheme")] = ["--kv-bits", "4"]
        at = w.index("fused_v1") + 1
        w[at:at] = ["--tq4-attention", MODES[arm]]
    if mutate:
        mutate(doc)
    return ph.seal(doc)


@pytest.mark.parametrize("pair", [("n16", "x"), ("x", "v"), ("n16", "v")])
def test_the_kv_pair_is_accepted_in_either_order(on_receipt, pair):
    a, b = (kv_receipt(on_receipt, arm) for arm in pair)
    assert pr.gate_problems(a, b, lever="kv") == []
    assert pr.gate_problems(b, a, lever="kv") == []
    assert [pr.kv_arm_of(a), pr.kv_arm_of(b)] == list(pair)


def test_the_observed_kv_difference_is_the_two_flags_only(on_receipt):
    n16, x = kv_receipt(on_receipt, "n16"), kv_receipt(on_receipt, "x")
    diffs = pr.gate_differences(n16, x, lever="kv")
    assert diffs == pr.kv_observed_differences(n16, x)
    assert pr.gate_problems(n16, x, lever="kv") == pr.kv_pair_problems(n16, x) == []
    assert diffs == [dict(process="worker", field="argv.worker", n16="", x="--kv-bits 4 --tq4-attention m72_exact")]
    assert pr.kv_difference_problems(diffs) == []
    assert pr.kv_difference_problems([dict(process="-", field="snapshots.drafter")])


def test_a_kv_pair_is_refused_beyond_the_two_flags(on_receipt):
    def prefill(doc):
        w = doc["argv"]["worker"]
        w[w.index("--prefill-step-size") + 1] = "2048"
    bad = kv_receipt(on_receipt, "x", prefill)
    assert any("beyond" in p for p in pr.gate_problems(kv_receipt(on_receipt, "n16"), bad, lever="kv"))

    def off(doc):
        w = doc["argv"]["worker"]
        i = w.index("--draft-kind")
        del w[i:i + 4]
    assert pr.gate_problems(kv_receipt(on_receipt, "n16"), kv_receipt(on_receipt, "x", off), lever="kv")

    def env(doc):
        doc["env"]["worker"]["MLX_VLM_CACHE_SESSION_MAX"] = "2"
    assert any("env.worker" in p for p in pr.gate_problems(kv_receipt(on_receipt, "n16"), kv_receipt(on_receipt, "x", env),
                                                          lever="kv"))

    def drafter(doc):
        doc["snapshots"]["drafter"] = dict(doc["snapshots"]["drafter"], revision="other")
    assert any("drafter" in p for p in pr.gate_problems(kv_receipt(on_receipt, "n16"), kv_receipt(on_receipt, "x", drafter),
                                                       lever="kv"))


def test_a_kv_pair_needs_two_kv_arms(on_receipt):
    x = kv_receipt(on_receipt, "x")
    assert pr.gate_problems(x, kv_receipt(on_receipt, "x"), lever="kv")
    off = json.loads((P426 / "wave2" / "tg1-p426-off-s1.a1" / "receipt.json").read_text())
    assert pr.gate_problems(off, x, lever="kv")
    assert pr.gate_problems(kv_receipt(on_receipt, "n16"), x) != []        # the mtp gate never accepts a KV pair


def test_a_tampered_receipt_is_refused(on_receipt):
    x = kv_receipt(on_receipt, "x")
    x["probe_entry"] = "<WT>/other.py"
    assert any("sha256" in p for p in pr.gate_problems(kv_receipt(on_receipt, "n16"), x, lever="kv"))


def test_the_kv_worker_argv_check(on_receipt):
    for arm in ("n16", "x", "v"):
        argv = kv_receipt(on_receipt, arm)["argv"]["worker"]
        assert pr.worker_argv_problems(argv, argv, arm, lever="kv") == []
    x = kv_receipt(on_receipt, "x")["argv"]["worker"]
    assert pr.worker_argv_problems(x, x, "v", lever="kv")
    assert pr.worker_argv_problems(x, x, "on") == []                    # the mtp check is unchanged


def test_the_kv_dossier(on_receipt, tmp_path):
    for name, arm in (("a", "n16"), ("b", "x")):
        d = tmp_path / f"tg1-m76-{arm}-s1.a1"
        d.mkdir()
        (d / "receipt.json").write_text(json.dumps(kv_receipt(on_receipt, arm)))
        (d / "HARVEST.json").write_text("{}")
    arms = {arm: dict(attempt=f"tg1-m76-{arm}-s1.a1", receipt=tmp_path / f"tg1-m76-{arm}-s1.a1" / "receipt.json",
                      harvest=tmp_path / f"tg1-m76-{arm}-s1.a1" / "HARVEST.json") for arm in ("n16", "x")}
    path = tmp_path / "pairs" / "s1__n16-a1__x-a1.json"
    doc = pr.write_kv_dossier(path, pair="s1", ref="n16", test="x", arms=arms, differences=[], verdict="PASS")
    assert doc["lever"] == "kv" and sorted(doc["arms"]) == ["n16", "x"] and ph.sealed_ok(json.loads(path.read_text()))
    with pytest.raises(ValueError):
        pr.write_kv_dossier(tmp_path / "pairs" / "s1__off-a1__on-a1.json", pair="s1", ref="n16", test="x", arms=arms,
                            differences=[], verdict="PASS")
    bad = dict(arms, x=dict(arms["x"], receipt=arms["n16"]["receipt"]))
    with pytest.raises(ValueError):
        pr.write_kv_dossier(tmp_path / "pairs" / "s2__n16-a1__x-a1.json", pair="s2", ref="n16", test="x", arms=bad,
                            differences=[], verdict="PASS")
