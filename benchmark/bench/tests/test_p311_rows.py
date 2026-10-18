"""P311-lite (iv): rows and manifests carry the composite and the arm identity; prompt_date is the SPAWN date; pairing
refuses date-mismatched and cross-epoch rows (spec tests 3, 6, 7)."""
import json

import pytest

from bench import tg1_pairing
from bench.tests.test_opencode_v2_probe import tg1_probe as probe, MODEL        # noqa: F401
from bench.tests.test_tg1_integration import tg_fixture, FROZEN


def test_manifest_and_rows_carry_the_composite_and_the_arm_identity(probe, monkeypatch, tmp_path):
    f = tg_fixture(probe, monkeypatch, tmp_path)
    assert f["run"]("one,two", extra=["--sampling-profile", "deployed"]) == 0
    man = json.loads(f["mp"].read_text())
    rt = man["runtime"]
    assert len(rt["generation_identity_sha256"]) == 64 and rt["arm_identity_sha256"] == f["arm"][1]
    assert rt["arm_identity"] == f["arm"][0]
    from bench import tg1_runner
    assert rt["generation_identity_sha256"] == tg1_runner.generation_identity_sha256(rt)
    rows = [json.loads(line) for line in f["out"].read_text().splitlines()]
    assert len(rows) == 2
    for row in rows:
        assert row["generation_identity_sha256"] == rt["generation_identity_sha256"]
        assert row["arm_identity_sha256"] == f["arm"][1]
        assert not {"web_fetches", "net_shell", "answer_key_contact", "web_audit_incomplete"} & set(row)


def test_an_unidentifiable_worker_refuses_before_the_manifest(probe, monkeypatch, tmp_path):
    from bench import arm_identity, arm_runner
    f = tg_fixture(probe, monkeypatch, tmp_path)

    def boom(*a):
        raise arm_identity.ArmIdentityError("unknown worker flag --surprise")
    monkeypatch.setattr(arm_runner, "arm_identity_of", boom)
    with pytest.raises(SystemExit, match="REFUSED.*unknown worker flag"):
        f["run"]("one")
    assert not f["mp"].exists() and not f["out"].exists()


def test_resume_refuses_a_changed_arm_identity(probe, monkeypatch, tmp_path):
    from bench import arm_runner
    f = tg_fixture(probe, monkeypatch, tmp_path)
    assert f["run"]("one") == 0
    monkeypatch.setattr(arm_runner, "arm_identity_of", lambda *a: ({"flags": {}}, "d" * 64))
    with pytest.raises(SystemExit, match="REFUSED"):
        f["run"]("one,two")


def test_prompt_date_is_captured_at_spawn_not_after_generation(probe, monkeypatch, tmp_path):
    """An item spawned before midnight and finished after records the spawn date (spec test 7). P364: `prompt_date` is
    now the FROZEN date the model is shown; the real spawn-time date is the covariate `prompt_date_real`."""
    f = tg_fixture(probe, monkeypatch, tmp_path)
    dates = iter(["Fri Oct 16 2026"] + ["Sat Oct 17 2026"] * 50)
    monkeypatch.setattr(probe, "_prompt_date", lambda: next(dates))
    assert f["run"]("one") == 0
    row = json.loads(f["out"].read_text())
    assert row["prompt_date_real"] == "Fri Oct 16 2026" and row["prompt_date"] == FROZEN
    assert row["prompt_date_update_removed"] is False


# ---- pairing (spec 5)
def row(i, *, gen="g", arm="a", date="Fri Oct 16 2026", sample=0):
    r = {"id": i, "sample": sample, "prompt_date": date}
    if gen is not None:
        r["generation_identity_sha256"] = gen
    if arm is not None:
        r["arm_identity_sha256"] = arm
    return r


def test_pairing_pairs_equal_generation_and_date_and_lists_the_rest():
    a = [row("python/x", arm="A"), row("python/y", arm="A", date="Fri Oct 16 2026"), row("python/z", arm="A"),
         row("python/w", arm="A")]
    b = [row("python/x", arm="B"), row("python/y", arm="B", date="Sat Oct 17 2026"),
         row("python/z", arm="B", gen="other"), row("python/v", arm="B")]
    got = tg1_pairing.pair_rows(a, b)
    assert [(x["id"], y["id"]) for x, y in got["paired"]] == [("python/x", "python/x")]
    assert [(x["id"], y["id"]) for x, y in got["date_mismatch"]] == [("python/y", "python/y")]
    assert [(x["id"], y["id"]) for x, y in got["generation_mismatch"]] == [("python/z", "python/z")]
    assert [r["id"] for r in got["unpaired_a"]] == ["python/w"] and [r["id"] for r in got["unpaired_b"]] == ["python/v"]
    assert got["legacy"] == []


def test_pairing_never_pairs_a_legacy_row_with_a_current_one():
    legacy = {"id": "python/x", "sample": 0, "prompt_date": "Fri Oct 16 2026"}
    got = tg1_pairing.pair_rows([legacy], [row("python/x")])
    assert got["paired"] == [] and [r["id"] for r in got["legacy"]] == ["python/x"]
    both = tg1_pairing.pair_rows([legacy], [dict(legacy)])
    assert both["paired"] == [] and len(both["legacy"]) == 2
    assert tg1_pairing.pair_rows([row("python/x", arm=None)], [row("python/x")])["paired"] == []


def test_pair_identity_is_the_composite_each_arm_and_the_date():
    pair = tg1_pairing.pair_identity(row("python/x", arm="A"), row("python/x", arm="B"))
    assert pair == ("g", "A", "B", "Fri Oct 16 2026")


# ---- review L5: the reports gate current-epoch rows through the pairing
def test_gate_items_is_a_passthrough_on_legacy_rows():
    ia, ib = {"python/x": [1]}, {"python/x": [0]}
    legacy_rows = [{"id": "python/x", "sample": 0}]
    a, b, report = tg1_pairing.gate_items(ia, legacy_rows, ib, legacy_rows)
    assert a is ia and b is ib and report is None


def test_gate_items_keeps_only_equal_generation_and_date_pairs_and_lists_the_rest():
    ra = [row("python/x", arm="A"), row("python/y", arm="A"), row("python/z", arm="A")]
    rb = [row("python/x", arm="B"), row("python/y", arm="B", date="Sat Oct 17 2026"), row("python/z", arm="B", gen="o")]
    ia = {"python/x": [1], "python/y": [1], "python/z": [1]}
    ib = {"python/x": [0], "python/y": [0], "python/z": [0]}
    a, b, report = tg1_pairing.gate_items(ia, ra, ib, rb)
    assert list(a) == list(b) == ["python/x"]
    assert report["date_mismatch"] == ["python/y"] and report["generation_mismatch"] == ["python/z"]
    assert "date mismatch: ['python/y']" in tg1_pairing.gate_note("s1 python", report)


@pytest.mark.parametrize("script", ["p223_tg1/tg1_report.py", "m63_mtp/m63_report.py", "c144_base/c144base_report.py"])
def test_every_report_script_gates_through_the_pairing(script):
    from pathlib import Path
    text = (Path(__file__).resolve().parents[2] / "results" / script).read_text()
    assert "tg1_pairing.gate_items" in text and "tg1_pairing.gate_note" in text


# ---- confirmation L5: the FULL pair identity, never pooled across arm tuples
def test_gate_items_never_pools_across_arm_identity_tuples():
    ra = [row("python/x", arm="A1"), row("python/y", arm="A2")]
    rb = [row("python/x", arm="B"), row("python/y", arm="B")]
    ia, ib = {"python/x": [1], "python/y": [1]}, {"python/x": [0], "python/y": [0]}
    a, b, report = tg1_pairing.gate_items(ia, ra, ib, rb)
    assert a == {} and b == {}                                   # two (arm A, arm B) tuples: nothing is pooled
    groups = report["multiple_pair_identities"]
    assert sorted(groups.values()) == [["python/x"], ["python/y"]]
    assert all(k.startswith("('g', 'A") for k in groups)
    assert "multiple pair identities" in tg1_pairing.gate_note("s1 python", report)


def test_gate_items_with_one_arm_tuple_is_unchanged_and_uses_pair_identity(monkeypatch):
    seen = []
    real = tg1_pairing.pair_identity
    monkeypatch.setattr(tg1_pairing, "pair_identity", lambda a, b: seen.append(1) or real(a, b))
    ra, rb = [row("python/x", arm="A"), row("python/y", arm="A")], [row("python/x", arm="B"), row("python/y", arm="B")]
    a, b, report = tg1_pairing.gate_items({"python/x": [1], "python/y": [1]}, ra, {"python/x": [0], "python/y": [0]}, rb)
    assert sorted(a) == sorted(b) == ["python/x", "python/y"] and seen and "multiple_pair_identities" not in report
