"""P426 B11 / B12: `vision_gate.py --ids` runs exactly a committed block (refusing unknown / duplicate ids before any request,
and `--ids` with `--limit`), records the membership in the manifest, and each row carries the image reference + the image's
sha256 for the blind panel (never a local cache path: no absolute home paths in committed rows).
"""

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # benchmark/ (holds vision_gate.py)
import vision_gate as VG  # noqa: E402
from bench.tests.conftest import FakeProbe, probe_result  # noqa: E402
from bench.tests.test_vision_gate import _row, _tiny_jpeg_path, _write_jsonl  # noqa: E402

pytestmark = pytest.mark.usefixtures("pin_mtp_scan")

IDS = ["cocoval2017-000", "cocoval2017-001", "cocoval2017-002"]


def _setup(tmp_path, monkeypatch, n_calls):
    corpus = tmp_path / "corpus.jsonl"
    _write_jsonl(corpus, [_row(id=i) for i in IDS])
    monkeypatch.setattr(VG, "resolve_image", lambda row, cache: _tiny_jpeg_path(tmp_path))
    fp = FakeProbe(
        script=[
            r
            for _ in range(n_calls)
            for r in (
                probe_result(content="desc", completion_tokens=10),
                probe_result(content="PASS", completion_tokens=1),
            )
        ]
    )
    monkeypatch.setattr(VG.client, "probe", fp)
    monkeypatch.setattr(
        VG.model_params,
        "params_for",
        lambda model, profile: {"thinking_budget": 1000, "max_tokens": 2000},
    )
    monkeypatch.setattr(VG.model_params, "registry_context_limit", lambda model: None)
    monkeypatch.setattr(VG.generate, "rows_for_rate", lambda model, bench: [])
    return corpus, fp


def test_ids_runs_exactly_that_block_and_records_membership(tmp_path, monkeypatch):
    corpus, fp = _setup(tmp_path, monkeypatch, 2)
    out = tmp_path / "r" / "m" / "vision_gate.p426-off-b1.jsonl"
    rc = VG.main(["--model", "m", "--corpus", str(corpus), "--out", str(out), "--ids", f"{IDS[2]}:{IDS[0]}"])
    assert rc == 0 and fp.n_calls == 4
    rows = [json.loads(line) for line in out.read_text().splitlines() if line.strip()]
    assert [r["id"] for r in rows] == [IDS[0], IDS[2]]  # corpus order
    manifest = json.loads(VG.manifest_path_for(out).read_text())
    assert manifest["runtime"]["ids"] == [IDS[0], IDS[2]]


@pytest.mark.parametrize(
    "ids, why",
    [
        (f"{IDS[0]}:cocoval2017-999", "unknown"),
        (f"{IDS[0]}:{IDS[0]}", "duplicate"),
        ("", "empty"),
    ],
)
def test_bad_ids_refuse_before_any_request(tmp_path, monkeypatch, capsys, ids, why):
    corpus, fp = _setup(tmp_path, monkeypatch, 0)
    out = tmp_path / "r" / "m" / "vision_gate.x.jsonl"
    rc = VG.main(["--model", "m", "--corpus", str(corpus), "--out", str(out), "--ids", ids])
    assert rc == 2 and fp.n_calls == 0
    assert why in capsys.readouterr().err.lower()
    assert not out.exists()


def test_ids_and_limit_are_exclusive(tmp_path, monkeypatch, capsys):
    corpus, fp = _setup(tmp_path, monkeypatch, 0)
    out = tmp_path / "r" / "m" / "vision_gate.x.jsonl"
    with pytest.raises(SystemExit):
        VG.main(["--model", "m", "--corpus", str(corpus), "--out", str(out), "--ids", IDS[0], "--limit", "1"])
    assert fp.n_calls == 0


def test_a_row_carries_the_image_reference_and_sha_not_a_path(tmp_path, monkeypatch):
    corpus, fp = _setup(tmp_path, monkeypatch, 1)
    out = tmp_path / "r" / "m" / "vision_gate.p426-on-b1.jsonl"
    assert VG.main(["--model", "m", "--corpus", str(corpus), "--out", str(out), "--ids", IDS[1]]) == 0
    row = json.loads(out.read_text().splitlines()[0])
    assert row["image_ref"] == _row(id=IDS[1])["image_ref"]
    image = Path(_tiny_jpeg_path(tmp_path)).read_bytes()
    assert row["image_sha256"] == hashlib.sha256(image).hexdigest()
    assert str(tmp_path) not in json.dumps(row)


def test_a_row_carries_each_turns_draft_counters(tmp_path, monkeypatch):
    """B12 / B10 S3: the leg wrapper's engagement gate reads every axis's rows; vision rows carry both turns' counters
    (None under plain decode)."""
    corpus = tmp_path / "corpus.jsonl"
    _write_jsonl(corpus, [_row(id=IDS[0])])
    monkeypatch.setattr(VG, "resolve_image", lambda row, cache: _tiny_jpeg_path(tmp_path))
    on = dict(draft_kind="mtp", draft_rounds=4, draft_n=8, draft_n_accepted=6)
    fp = FakeProbe(
        script=[
            probe_result(content="desc", completion_tokens=10, raw_timings=on),
            probe_result(content="PASS", completion_tokens=1, raw_timings={}),
        ]
    )
    monkeypatch.setattr(VG.client, "probe", fp)
    monkeypatch.setattr(
        VG.model_params, "params_for", lambda model, profile: {"thinking_budget": 1000, "max_tokens": 2000}
    )
    monkeypatch.setattr(VG.model_params, "registry_context_limit", lambda model: None)
    monkeypatch.setattr(VG.generate, "rows_for_rate", lambda model, bench: [])
    out = tmp_path / "r" / "m" / "vision_gate.p426-on-b1.jsonl"
    assert VG.main(["--model", "m", "--corpus", str(corpus), "--out", str(out), "--ids", IDS[0]]) == 0
    row = json.loads(out.read_text().splitlines()[0])
    assert row["draft"] == on
    assert row["turn2"]["draft"] == dict.fromkeys(on)


def test_k4_a_row_records_both_turn_seeds(tmp_path, monkeypatch):
    """Stack code round 1 K4: the leg wrapper checks every row's seeds against the plan; vision rows record them."""
    from bench.rowschema import sample_seed

    corpus, fp = _setup(tmp_path, monkeypatch, 1)
    out = tmp_path / "r" / "m" / "vision_gate.p426-off-b1.jsonl"
    assert VG.main(["--model", "m", "--corpus", str(corpus), "--out", str(out), "--ids", IDS[0]]) == 0
    row = json.loads(out.read_text().splitlines()[0])
    assert row["seed"] == sample_seed(IDS[0], 0) and row["turn2"]["seed"] == sample_seed(IDS[0], 1)


def test_k5_a_row_records_both_turn_session_ids(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus.jsonl"
    _write_jsonl(corpus, [_row(id=IDS[0])])
    monkeypatch.setattr(VG, "resolve_image", lambda row, cache: _tiny_jpeg_path(tmp_path))
    fp = FakeProbe(script=[dict(probe_result(content="desc"), session_id="s-1"), dict(probe_result(content="PASS"), session_id="s-2")])
    monkeypatch.setattr(VG.client, "probe", fp)
    monkeypatch.setattr(VG.model_params, "params_for", lambda model, profile: {"thinking_budget": 1000, "max_tokens": 2000})
    monkeypatch.setattr(VG.model_params, "registry_context_limit", lambda model: None)
    monkeypatch.setattr(VG.generate, "rows_for_rate", lambda model, bench: [])
    out = tmp_path / "r" / "m" / "vision_gate.p426-on-b1.jsonl"
    assert VG.main(["--model", "m", "--corpus", str(corpus), "--out", str(out), "--ids", IDS[0]]) == 0
    row = json.loads(out.read_text().splitlines()[0])
    assert row["session_id"] == "s-1" and row["turn2"]["session_id"] == "s-2"
