"""Determinism + selection-rule tests for benchmark/corpora/build_vision_gate_v1.py (M39
vision-gate re-scope, 2026-09-12). `datasets.load_dataset` is mocked -- no network, no real HF
cache reads. Tests never touch the real committed corpus files: OUT_JSONL/OUT_PROV are
monkeypatched to tmp_path before `main()` runs.
"""
import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "build_vision_gate_v1",
    Path(__file__).resolve().parents[3] / "benchmark" / "corpora" / "build_vision_gate_v1.py")
BUILD = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BUILD)


class FakeImage:
    def __init__(self, size, fmt, tag):
        self.size = size
        self.format = fmt
        self._tag = tag
        self.saved = None

    def load(self):
        pass

    def save(self, path, format=None):
        self.saved = (path, format)
        Path(path).write_bytes(self._tag.encode())


class FakeDataset:
    """Mimics enough of `datasets.Dataset` for the builder: column access (`ds["col"]` -> list)
    AND row access (`ds[i]` -> dict) AND `len(ds)`."""

    def __init__(self, rows):
        self.rows = rows

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, key):
        if isinstance(key, str):
            return [r[key] for r in self.rows]
        return self.rows[key]


def _caption_rows(n=200):
    """Synthetic COCO-caption-shaped rows. Captions are built so the first word of the first
    caption ("first noun" heuristic) repeats across groups of 5 -- enough duplicate-scene
    collisions to exercise the dedupe at N=20 without needing thousands of rows."""
    rows = []
    for i in range(n):
        g = i // 5                        # 5 consecutive rows per "scene" -> forces dedupe
        # ALPHABETIC-only scene tag: `_first_noun_key`'s regex drops digits, so a digit-suffixed
        # tag (e.g. "scene0") would collapse every group to the same "scene" key and defeat the
        # dedupe test. Base-26 two-letter tag keeps every group's tag distinct and letters-only.
        tag = chr(97 + g % 26) + chr(97 + (g // 26) % 26)
        scene = f"scene{tag}"
        captions = [f"a {scene} with detail {j}" for j in range(5)]
        h, w = 400, 300
        rows.append({
            "height": h, "width": w, "answer": captions, "id": 1000 + i,
            "file_name": f"{i:012d}.jpg", "coco_url": f"http://example/{i}.jpg",
            "date_captured": "2013-11-01 00:00:00", "license": 1 + (i % 8),
            "image": FakeImage((w, h), "JPEG", f"img-{i}"),
        })
    # A few rows that must be filtered out:
    rows.append({"height": 2000, "width": 2000, "answer": ["a big scene with something"] * 5,
                "id": 9001, "file_name": "oversize.jpg", "coco_url": "http://example/oversize.jpg",
                "date_captured": "2013-11-01 00:00:00", "license": 4,
                "image": FakeImage((2000, 2000), "JPEG", "oversize")})
    rows.append({"height": 300, "width": 300, "answer": ["only", "two"],
                "id": 9002, "file_name": "toofewcaps.jpg", "coco_url": "http://example/x.jpg",
                "date_captured": "2013-11-01 00:00:00", "license": 4,
                "image": FakeImage((300, 300), "JPEG", "toofewcaps")})
    return FakeDataset(rows)


def _fake_load_dataset(repo, split=None, revision=None):
    assert repo == BUILD.REPO and split == BUILD.SPLIT and revision == BUILD.REVISION
    return _caption_rows()


def _run_build(monkeypatch, tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    out_jsonl, out_prov = tmp_path / "vision_gate_v1.jsonl", tmp_path / "vision_gate_v1.provenance.json"
    monkeypatch.setattr(BUILD, "OUT_JSONL", out_jsonl)
    monkeypatch.setattr(BUILD, "OUT_PROV", out_prov)
    import datasets
    monkeypatch.setattr(datasets, "load_dataset", _fake_load_dataset)
    BUILD.main()
    rows = [json.loads(l) for l in out_jsonl.read_text().splitlines() if l.strip()]
    prov = json.loads(out_prov.read_text())
    return rows, prov


def test_builder_never_touches_the_real_committed_corpus(monkeypatch, tmp_path):
    """Guards the whole test module: if OUT_JSONL/OUT_PROV monkeypatching ever silently no-ops,
    this fails loudly instead of the suite quietly clobbering the real 20-row corpus."""
    real_jsonl = Path(__file__).resolve().parents[3] / "benchmark" / "corpora" / "vision_gate_v1.jsonl"
    before = real_jsonl.read_bytes()
    _run_build(monkeypatch, tmp_path)
    assert real_jsonl.read_bytes() == before


def test_builder_produces_20_rows(monkeypatch, tmp_path):
    rows, prov = _run_build(monkeypatch, tmp_path)
    assert len(rows) == 20
    assert prov["rows"] == 20
    assert prov["selection_seed"] == BUILD.SELECTION_SEED


def test_builder_is_deterministic_given_the_seed(monkeypatch, tmp_path):
    rows_a, _ = _run_build(monkeypatch, tmp_path / "a")
    rows_b, _ = _run_build(monkeypatch, tmp_path / "b")
    assert rows_a == rows_b


def test_builder_rows_have_required_shape(monkeypatch, tmp_path):
    rows, _ = _run_build(monkeypatch, tmp_path)
    ids = [r["id"] for r in rows]
    assert len(set(ids)) == 20
    for r in rows:
        for key in ("id", "image_ref", "captions", "meta"):
            assert key in r
        assert set(r["image_ref"]) == {"dataset", "revision", "split", "index"}
        assert r["image_ref"]["dataset"] == BUILD.REPO
        assert r["image_ref"]["revision"] == BUILD.REVISION
        assert len(r["captions"]) == BUILD.CAPTIONS_PER_ROW
        for key in ("image_width", "image_height", "image_format", "coco_image_id",
                    "file_name", "coco_url", "date_captured", "license_id", "license_name",
                    "license_url", "first_noun_key"):
            assert key in r["meta"], f"meta missing {key!r}"


def test_builder_excludes_oversized_images(monkeypatch, tmp_path):
    rows, _ = _run_build(monkeypatch, tmp_path)
    for r in rows:
        assert r["meta"]["image_width"] * r["meta"]["image_height"] <= BUILD.MAX_PIXELS
    assert "oversize.jpg" not in {r["meta"]["file_name"] for r in rows}


def test_builder_excludes_rows_with_too_few_captions(monkeypatch, tmp_path):
    rows, _ = _run_build(monkeypatch, tmp_path)
    assert "toofewcaps.jpg" not in {r["meta"]["file_name"] for r in rows}
    for r in rows:
        assert len(r["captions"]) >= BUILD.MIN_CAPTIONS


def test_builder_diversity_heuristic_dedupes_by_first_noun_key(monkeypatch, tmp_path):
    """Every 5 consecutive source rows share a scene ('scene0'..'scene39') and hence the same
    `first_noun_key`; the builder must select at most one row per scene."""
    rows, _ = _run_build(monkeypatch, tmp_path)
    keys = [r["meta"]["first_noun_key"] for r in rows]
    assert len(keys) == len(set(keys)), f"duplicate first_noun_key across selected rows: {keys}"


def test_builder_license_lookup_matches_coco_codes(monkeypatch, tmp_path):
    rows, _ = _run_build(monkeypatch, tmp_path)
    for r in rows:
        name, url = BUILD.COCO_LICENSES[r["meta"]["license_id"]]
        assert r["meta"]["license_name"] == name
        assert r["meta"]["license_url"] == url


def test_provenance_records_license_and_source(monkeypatch, tmp_path):
    _, prov = _run_build(monkeypatch, tmp_path)
    assert prov["license"]["annotations"] == "CC BY 4.0"
    assert "Flickr" in prov["license"]["images"]
    assert prov["source"]["repo"] == BUILD.REPO
    assert prov["source"]["revision"] == BUILD.REVISION
    assert prov["source"]["split"] == BUILD.SPLIT
    assert set(prov["license"]["coco_license_codes"]) == {str(k) for k in BUILD.COCO_LICENSES}


def test_builder_raises_when_too_few_eligible_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(BUILD, "OUT_JSONL", tmp_path / "v.jsonl")
    monkeypatch.setattr(BUILD, "OUT_PROV", tmp_path / "v.provenance.json")

    def scarce(repo, split=None, revision=None):
        return FakeDataset(_caption_rows(n=3).rows[:3])   # far fewer than N=20

    import datasets
    monkeypatch.setattr(datasets, "load_dataset", scarce)
    with pytest.raises(SystemExit):
        BUILD.main()


def test_first_noun_key_skips_leading_stopwords():
    assert BUILD._first_noun_key("A man standing on a beach.") == "man"
    assert BUILD._first_noun_key("Two dogs running in a field.") == "dogs"
    assert BUILD._first_noun_key("") == ""
