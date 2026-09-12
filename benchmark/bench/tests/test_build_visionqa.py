"""Determinism + selection-rule tests for benchmark/corpora/build_visionqa_v1.py (M39,
docs/vision-smoke-m39.md). All `datasets.load_dataset` calls are mocked -- no network, no real
HF cache reads. Tests never touch the real committed corpus files: OUT_JSONL/OUT_PROV are
monkeypatched to tmp_path before `main()` runs.
"""
import importlib.util
import json
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "build_visionqa_v1",
    Path(__file__).resolve().parents[3] / "benchmark" / "corpora" / "build_visionqa_v1.py")
BUILD = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BUILD)


class FakeImage:
    def __init__(self, size, fmt, tag):
        self.size = size
        self.format = fmt
        self._tag = tag

    def load(self):
        pass

    def tobytes(self):
        return self._tag.encode()


class FakeDataset:
    """Mimics enough of `datasets.Dataset` for the builder: column access (`ds["col"]` ->
    list) AND row access (`ds[i]` -> dict), which is exactly what HF's own Dataset supports."""

    def __init__(self, rows):
        self.rows = rows

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, key):
        if isinstance(key, str):
            return [r[key] for r in self.rows]
        return self.rows[key]


def _chartqa_rows(n=25):
    rows = []
    for i in range(n):
        q, label, img = f"chart question {i}", [str(i)], FakeImage((100, 100), "PNG", f"chart-{i}")
        if i == 5:
            img = FakeImage((100, 100), "PNG", "chart-0")  # duplicate of row 0's image
        if i == 6:
            label = [""]                                   # empty answer -> filtered
        if i == 7:
            img = FakeImage((2000, 2000), "PNG", "chart-oversize")  # 4 MP -> filtered
        if i == 8:
            q = " ".join(["word"] * 61)                    # over the 60-word cap -> filtered
        rows.append({"query": q, "label": label, "human_or_machine": 0, "image": img})
    return FakeDataset(rows)


def _screenqa_rows(n=25):
    rows = []
    for i in range(n):
        q, gt, img = f"screen question {i}", [f"answer {i}"], FakeImage((100, 100), "JPEG", f"screen-{i}")
        fn = f"images/rico/{i}.jpg"
        if i == 5:
            fn = "images/rico/0.jpg"                       # duplicate file_name
        if i == 6:
            gt = []
        if i == 7:
            img = FakeImage((2000, 2000), "JPEG", "screen-oversize")
        if i == 8:
            q = " ".join(["word"] * 61)
        rows.append({"question": q, "ground_truth": gt, "file_name": fn, "image": img})
    return FakeDataset(rows)


def _ai2d_rows(n=25):
    rows = []
    for i in range(n):
        q = f"ai2d question {i}"
        opts, ans, img = ["a", "b", "c", "d"], "1", FakeImage((100, 100), "PNG", f"ai2d-{i}")
        if i == 5:
            img = FakeImage((100, 100), "PNG", "ai2d-0")
        if i == 6:
            ans = "9"                                      # out of range -> filtered
        if i == 7:
            img = FakeImage((2000, 2000), "PNG", "ai2d-oversize")
        if i == 8:
            q = " ".join(["word"] * 61)
        rows.append({"question": q, "options": opts, "answer": ans, "image": img})
    return FakeDataset(rows)


def _textvqa_rows(n=15):
    rows = []
    for i in range(n):
        q = f"textvqa question {i}"
        ans, img = [f"ans{i}"] * 10, FakeImage((100, 100), "JPEG", f"textvqa-{i}")
        iid = f"img-{i}"
        if i == 5:
            iid = "img-0"                                  # duplicate image_id
        if i == 6:
            ans = [""] * 10                                # all empty -> filtered
        if i == 7:
            img = FakeImage((2000, 2000), "JPEG", "textvqa-oversize")
        if i == 8:
            q = " ".join(["word"] * 61)
        rows.append({"question": q, "answers": ans, "image_id": iid, "image": img})
    return FakeDataset(rows)


_FAKE_BY_REPO = {
    "HuggingFaceM4/ChartQA": _chartqa_rows,
    "rootsautomation/RICO-ScreenQA-Short": _screenqa_rows,
    "lmms-lab/ai2d": _ai2d_rows,
    "lmms-lab/textvqa": _textvqa_rows,
}


def _fake_load_dataset(repo, split=None, revision=None):
    return _FAKE_BY_REPO[repo]()


def _run_build(monkeypatch, tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    out_jsonl, out_prov = tmp_path / "visionqa_v1.jsonl", tmp_path / "visionqa_v1.provenance.json"
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
    this fails loudly instead of the suite quietly clobbering the real 40-row corpus."""
    real_jsonl = Path(__file__).resolve().parents[3] / "benchmark" / "corpora" / "visionqa_v1.jsonl"
    before = real_jsonl.read_bytes()
    _run_build(monkeypatch, tmp_path)
    assert real_jsonl.read_bytes() == before


def test_builder_produces_40_rows_with_spec_per_source_counts(monkeypatch, tmp_path):
    rows, prov = _run_build(monkeypatch, tmp_path)
    assert len(rows) == 40
    counts = {}
    for r in rows:
        counts[r["source_kind"]] = counts.get(r["source_kind"], 0) + 1
    assert counts == {"chartqa": 15, "screenqa": 10, "ai2d": 10, "textvqa": 5}
    assert prov["rows"] == 40
    assert prov["selection_seed"] == 39


def test_builder_is_deterministic_given_the_seed(monkeypatch, tmp_path):
    rows_a, _ = _run_build(monkeypatch, tmp_path / "a")
    rows_b, _ = _run_build(monkeypatch, tmp_path / "b")
    assert rows_a == rows_b


def test_builder_excludes_oversized_images(monkeypatch, tmp_path):
    rows, _ = _run_build(monkeypatch, tmp_path)
    for r in rows:
        assert r["meta"]["image_width"] * r["meta"]["image_height"] <= BUILD.MAX_PIXELS


def test_builder_excludes_duplicate_images_within_a_source(monkeypatch, tmp_path):
    rows, _ = _run_build(monkeypatch, tmp_path)
    chartqa_ids = [r["source_id"] for r in rows if r["source_kind"] == "chartqa"]
    # candidate index 5 shares chartqa-0's image bytes with index 0 -- at most one may be picked
    assert not ({"0", "5"} <= set(chartqa_ids))


def test_builder_excludes_overlong_questions(monkeypatch, tmp_path):
    rows, _ = _run_build(monkeypatch, tmp_path)
    for r in rows:
        assert len(r["question"].split()) <= BUILD.MAX_QUESTION_WORDS


def test_builder_rows_have_required_shape(monkeypatch, tmp_path):
    rows, _ = _run_build(monkeypatch, tmp_path)
    ids = [r["id"] for r in rows]
    assert len(set(ids)) == 40
    for r in rows:
        for key in ("id", "source", "source_kind", "source_id", "image_ref", "question",
                    "answer", "choices", "meta"):
            assert key in r
        assert set(r["image_ref"]) == {"dataset", "revision", "split", "index"}
    ai2d_rows = [r for r in rows if r["source_kind"] == "ai2d"]
    assert all(r["answer"] in "ABCD" and r["choices"] == ["a", "b", "c", "d"] for r in ai2d_rows)
    textvqa_rows = [r for r in rows if r["source_kind"] == "textvqa"]
    assert all(len(r["answer"]) == 10 for r in textvqa_rows)
    chartqa_rows = [r for r in rows if r["source_kind"] == "chartqa"]
    assert all("answer_numeric" in r for r in chartqa_rows)


def test_builder_raises_when_a_source_cannot_reach_its_target_count(monkeypatch, tmp_path):
    monkeypatch.setattr(BUILD, "OUT_JSONL", tmp_path / "v.jsonl")
    monkeypatch.setattr(BUILD, "OUT_PROV", tmp_path / "v.provenance.json")

    def scarce(repo, split=None, revision=None):
        if repo == "HuggingFaceM4/ChartQA":
            return FakeDataset(_chartqa_rows(3).rows[:3])   # far fewer than the target of 15
        return _FAKE_BY_REPO[repo]()

    import datasets
    monkeypatch.setattr(datasets, "load_dataset", scarce)
    with pytest.raises(SystemExit):
        BUILD.main()
