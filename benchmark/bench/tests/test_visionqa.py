"""visionqa (M39, docs/vision-smoke-m39.md): loader, message builder, and the depth-wrapper guard.
Grading rules live in test_grade_visionqa.py. No network: `_resolve_visionqa_images` (the one seam
that touches the HF cache) is monkeypatched to a no-op everywhere here.
"""
import base64
import io
import struct
import zlib

import pytest

import bench.benchmarks as B
import bench.depth as D
import bench.generate as G


def _stub_resolve(monkeypatch):
    """Bypass the HF-cache resolution seam: point every row's image_path at a fixed stub path
    without touching the network or the real ~/.cache/huggingface tree."""
    def _fake(rows):
        for r in rows:
            r["meta"]["image_path"] = f"/tmp/visionqa-test-stub/{r['id']}.{r['meta']['image_format'].lower()}"
    monkeypatch.setattr(B, "_resolve_visionqa_images", _fake)


def _tiny_png(rgb=(10, 20, 30), size=4) -> bytes:
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(rgb) * size
    idat = zlib.compress(row * size)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat)
            + chunk(b"IEND", b""))


# --------------------------------------------------------------------------- registry + loader
def test_visionqa_spec_entry():
    assert B.SPECS["visionqa"] == {"kind": "vision", "answer_type": "visionqa", "gated": False}


def test_visionqa_loads_40_unique_items_with_image_paths(monkeypatch):
    _stub_resolve(monkeypatch)
    items = B.load("visionqa", limit=None, seed=0)
    assert len(items) == 40
    ids = [it["id"] for it in items]
    assert len(set(ids)) == 40
    for it in items:
        assert it["prompt"].strip()
        assert it["meta"]["image_path"]
        assert it["meta"]["source_kind"] in ("chartqa", "screenqa", "ai2d", "textvqa")


def test_visionqa_limit_and_seed_is_a_seeded_subsample(monkeypatch):
    _stub_resolve(monkeypatch)
    a = B.load("visionqa", limit=5, seed=0)
    b = B.load("visionqa", limit=5, seed=0)
    assert len(a) == 5
    assert [it["id"] for it in a] == [it["id"] for it in b]        # same seed -> same draw
    c = B.load("visionqa", limit=5, seed=1)
    assert [it["id"] for it in a] != [it["id"] for it in c]        # different seed -> different draw


def test_visionqa_ai2d_items_carry_choices_and_letter_answer(monkeypatch):
    _stub_resolve(monkeypatch)
    items = B.load("visionqa", limit=None, seed=0)
    ai2d = [it for it in items if it["meta"]["source_kind"] == "ai2d"]
    assert ai2d
    for it in ai2d:
        assert it["answer"] in "ABCD"
        assert it["options"] and len(it["options"]) == 4


# --------------------------------------------------------------------------- build_messages
def _visionqa_item(source_kind="chartqa", image_path=None, options=None, answer="42",
                   fmt="PNG"):
    return {"id": "x", "prompt": "What is shown?", "answer": answer, "options": options,
            "meta": {"source_kind": source_kind, "image_path": image_path,
                     "image_format": fmt}}


def test_build_messages_visionqa_emits_a_valid_data_url(tmp_path):
    png = _tiny_png()
    p = tmp_path / "img.png"
    p.write_bytes(png)
    item = _visionqa_item(image_path=str(p))
    msgs = B.build_messages("visionqa", item)
    assert len(msgs) == 1 and msgs[0]["role"] == "user"
    content = msgs[0]["content"]
    assert isinstance(content, list) and len(content) == 2
    text_part, image_part = content
    assert text_part["type"] == "text"
    assert "What is shown?" in text_part["text"]
    assert "\\boxed{}" in text_part["text"]
    assert image_part["type"] == "image_url"
    url = image_part["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    decoded = base64.b64decode(url.split(",", 1)[1])
    assert decoded == png


def test_build_messages_visionqa_uses_jpeg_mime_for_jpeg_rows(tmp_path):
    p = tmp_path / "img.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0fakejpegbytes")
    item = _visionqa_item(source_kind="textvqa", image_path=str(p), fmt="JPEG")
    msgs = B.build_messages("visionqa", item)
    assert msgs[0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_build_messages_visionqa_ai2d_lists_lettered_options(tmp_path):
    p = tmp_path / "img.png"
    p.write_bytes(_tiny_png())
    item = _visionqa_item(source_kind="ai2d", image_path=str(p),
                          options=["cat", "dog", "bird", "fish"], answer="C")
    msgs = B.build_messages("visionqa", item)
    text = msgs[0]["content"][0]["text"]
    assert "A) cat" in text and "B) dog" in text and "C) bird" in text and "D) fish" in text


# --------------------------------------------------------------------------- depth-wrapper guard
def test_depth_wrapper_is_never_applied_to_vision_items():
    msgs = [{"role": "user", "content": [{"type": "text", "text": "q"}]}]
    out = G._wrap_for_generation("visionqa", msgs, None, "chartqa-000")
    assert out == msgs


def test_depth_wrapper_raises_if_depth_tokens_requested_for_vision():
    msgs = [{"role": "user", "content": [{"type": "text", "text": "q"}]}]
    with pytest.raises(ValueError, match="vision"):
        G._wrap_for_generation("visionqa", msgs, 4000, "chartqa-000")


def test_depth_wrapper_still_applies_normally_to_text_benchmarks():
    msgs = [{"role": "user", "content": "task"}]
    out = G._wrap_for_generation("aime", msgs, 4000, "aime24-1")
    assert out != msgs                                  # padding WAS applied
    assert out[0]["content"].endswith("task")
    # zero/None depth is still identity for text benchmarks
    assert G._wrap_for_generation("aime", msgs, 0, "aime24-1") == msgs
