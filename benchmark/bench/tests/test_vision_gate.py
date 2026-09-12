"""M39 vision gate (operator re-scope, 2026-09-12): tests for benchmark/vision_gate.py -- a
pass/fail "can this model do some vision" check, NOT a scored benchmark.

Covers: two-turn message construction (the image rides in turn 1 only; turn 2 carries the full
conversation + the human reference captions as bullets), the strict PASS/FAIL self-verdict
parse, --resume skip-by-id, summary counts, and transport errors escalating (nonzero exit,
never a graded row) rather than being caught and scored.

No network, no :8000: `client.probe` is monkeypatched everywhere via `FakeProbe`
(`bench/tests/conftest.py`); `resolve_image` is monkeypatched to a stub path so the HF cache is
never touched.
"""
import base64
import json
import struct
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # benchmark/ (holds vision_gate.py)
import vision_gate as VG  # noqa: E402

from bench.tests.conftest import FakeProbe, probe_result  # noqa: E402


def _tiny_jpeg_path(tmp_path) -> str:
    """A real (tiny) JPEG-looking file is not needed -- resolve_image is stubbed in every test
    that reaches message-building; this just gives base64-encodable bytes."""
    p = tmp_path / "img.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0fakejpegbytes\xff\xd9")
    return str(p)


def _row(id="cocoval2017-000", captions=None, fmt="JPEG"):
    return {
        "id": id,
        "image_ref": {"dataset": "lmms-lab/COCO-Caption2017",
                      "revision": "deadbeef", "split": "val", "index": 7},
        "captions": captions or ["a man on a beach", "someone surfing", "a person with a board",
                                 "a surfer", "a guy holding a surfboard"],
        "meta": {"image_format": fmt},
    }


# --------------------------------------------------------------------------- turn 1 messages
def test_turn1_messages_has_text_and_image_parts(tmp_path):
    img = _tiny_jpeg_path(tmp_path)
    msgs = VG.turn1_messages(_row(), img)
    assert len(msgs) == 1 and msgs[0]["role"] == "user"
    content = msgs[0]["content"]
    assert isinstance(content, list) and len(content) == 2
    text_part, image_part = content
    assert text_part == {"type": "text", "text": "Describe this image in detail."}
    assert image_part["type"] == "image_url"
    url = image_part["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    decoded = base64.b64decode(url.split(",", 1)[1])
    assert decoded == Path(img).read_bytes()


def test_turn1_messages_uses_png_mime_for_png_rows(tmp_path):
    p = tmp_path / "img.png"

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00" + bytes((1, 2, 3)) * 2 + b"\x00" + bytes((4, 5, 6)) * 2)
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b""))
    msgs = VG.turn1_messages(_row(fmt="PNG"), str(p))
    assert msgs[0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")


# --------------------------------------------------------------------------- turn 2 messages
def test_turn2_messages_carries_the_full_turn1_conversation_plus_the_description():
    msgs1 = [{"role": "user", "content": [{"type": "text", "text": "Describe this image in detail."},
                                          {"type": "image_url", "image_url": {"url": "data:x"}}]}]
    msgs2 = VG.turn2_messages(msgs1, "A man on a beach.", ["a man on a beach"])
    assert msgs2[0] == msgs1[0]                          # turn-1 user message (WITH the image) preserved
    assert msgs2[1] == {"role": "assistant", "content": "A man on a beach."}
    assert msgs2[2]["role"] == "user"
    assert "A man on a beach." not in msgs2[2]["content"]  # the new turn is the compare prompt, not an echo


def test_turn2_prompt_lists_captions_as_bullets_and_asks_for_one_word():
    text = VG.turn2_prompt(["cap one", "cap two"])
    assert "- cap one" in text and "- cap two" in text
    assert "PASS or FAIL" in text
    assert "ground-truth description" in text.lower() or "ground truth" in text.lower()


# --------------------------------------------------------------------------- strict verdict parse
@pytest.mark.parametrize("text,expected", [
    ("PASS", "PASS"),
    ("FAIL", "FAIL"),
    ("pass.", "PASS"),
    ("FAIL!", "FAIL"),
    ("  pass\n", "PASS"),
    ("I think PASS", None),          # first word is "I", not PASS/FAIL -- decided rule
    ("Pass, I believe", "PASS"),     # first word IS pass (punctuation-stripped)
    ("", None),
    (None, None),
    ("Maybe", None),
])
def test_parse_verdict_strict_first_word_rule(text, expected):
    assert VG.parse_verdict(text) == expected


# --------------------------------------------------------------------------- convergence wiring
def test_converged_true_when_stop_and_under_declared_budget():
    assert VG._converged("stop", 100, 500, 2000, None, None) is True


def test_converged_false_on_length_finish():
    assert VG._converged("length", 2000, 500, 2000, None, None) is False


def test_converged_uses_resolved_budget_when_context_limit_and_max_tokens_known():
    # declared thinking_budget 1000, but context_limit(2000) - prompt(1900) = 100 effective,
    # clamped budget = int(100*0.8) = 80; completion_tokens=90 >= 80 -> NOT converged even
    # though 90 < the DECLARED 1000 and finish_reason is "stop".
    out = VG._converged("stop", 90, 1900, 1000, 2000, 2000)
    assert out is False


# --------------------------------------------------------------------------- run_one (end-to-end, mocked)
def test_run_one_builds_two_turns_and_records_a_verdict(tmp_path, monkeypatch):
    monkeypatch.setattr(VG, "resolve_image", lambda row, cache: _tiny_jpeg_path(tmp_path))
    fp = FakeProbe(script=[
        probe_result(content="A man surfing.", completion_tokens=20, prompt_tokens=300,
                    finish_reason="stop", decode_tps=40.0, wall_s=1.2),
        probe_result(content="PASS", completion_tokens=1, prompt_tokens=340,
                    finish_reason="stop", wall_s=0.3),
    ])
    monkeypatch.setattr(VG.client, "probe", fp)
    params = {"temperature": 0.5, "thinking_budget": 1000, "max_tokens": 2000}
    out = VG.run_one("some-model", params, None, 300.0, _row(), {})
    assert fp.n_calls == 2
    assert out["description"] == "A man surfing."
    assert out["verdict"] == "PASS"
    assert out["verdict_raw"] == "PASS"
    assert out["completion_tokens"] == 20
    assert out["converged"] is True
    assert out["turn2"]["completion_tokens"] == 1
    # turn 1 carries the image; turn 2 does not re-send it (it rides in the conversation history)
    call2_msgs = fp.calls[1]["messages"]
    assert call2_msgs[0]["content"][1]["type"] == "image_url"
    assert call2_msgs[1] == {"role": "assistant", "content": "A man surfing."}
    # every draw carries an explicit seed (AGENTS.md), and the two turns use DIFFERENT seeds
    assert fp.calls[0]["params"]["seed"] != fp.calls[1]["params"]["seed"]


def test_run_one_null_verdict_when_reply_does_not_start_with_pass_or_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(VG, "resolve_image", lambda row, cache: _tiny_jpeg_path(tmp_path))
    fp = FakeProbe(script=[
        probe_result(content="A dog running.", completion_tokens=10),
        probe_result(content="I'm not sure.", completion_tokens=5),
    ])
    monkeypatch.setattr(VG.client, "probe", fp)
    out = VG.run_one("m", {"thinking_budget": 1000, "max_tokens": 2000}, None, 300.0, _row(), {})
    assert out["verdict"] is None
    assert out["verdict_raw"] == "I'm not sure."


# --------------------------------------------------------------------------- summary
def test_summarize_counts_pass_fail_null_and_means():
    rows = [
        {"id": "a", "verdict": "PASS", "completion_tokens": 10, "wall_s": 1.0},
        {"id": "b", "verdict": "FAIL", "completion_tokens": 20, "wall_s": 2.0},
        {"id": "c", "verdict": None, "completion_tokens": 30, "wall_s": 3.0},
    ]
    s = VG.summarize(rows)
    assert s["n"] == 3 and s["pass"] == 1 and s["fail"] == 1 and s["null"] == 1
    assert s["pass_rate"] == pytest.approx(1 / 3, abs=1e-3)  # summarize() rounds to 3 places
    assert s["turn1_tokens_mean"] == 20.0
    assert s["turn1_wall_s_mean"] == 2.0
    assert set(s["fail_or_null_ids"]) == {"b", "c"}


def test_summarize_empty_rows_is_well_defined():
    s = VG.summarize([])
    assert s == {"n": 0, "pass": 0, "fail": 0, "null": 0, "pass_rate": None,
                "turn1_tokens_mean": None, "turn1_wall_s_mean": None, "fail_or_null_ids": []}


def test_summary_path_for_replaces_jsonl_suffix_only():
    out = Path("/x/y/vision_gate.v1.jsonl")
    assert VG.summary_path_for(out) == Path("/x/y/vision_gate.v1.summary.json")


# --------------------------------------------------------------------------- resume
def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_main_without_resume_refuses_a_nonempty_out(tmp_path, monkeypatch, capsys):
    out = tmp_path / "results" / "m" / "vision_gate.v1.jsonl"
    _write_jsonl(out, [{"id": "cocoval2017-000", "verdict": "PASS"}])
    corpus = tmp_path / "corpus.jsonl"
    _write_jsonl(corpus, [_row()])
    rc = VG.main(["--model", "m", "--corpus", str(corpus), "--out", str(out)])
    assert rc == 2
    assert "resume" in capsys.readouterr().err.lower()


def test_main_with_resume_skips_already_done_ids(tmp_path, monkeypatch):
    out = tmp_path / "results" / "m" / "vision_gate.v1.jsonl"
    _write_jsonl(out, [{"id": "cocoval2017-000", "verdict": "PASS", "completion_tokens": 5,
                       "wall_s": 1.0}])
    corpus = tmp_path / "corpus.jsonl"
    _write_jsonl(corpus, [_row(id="cocoval2017-000"), _row(id="cocoval2017-001")])

    monkeypatch.setattr(VG, "resolve_image", lambda row, cache: _tiny_jpeg_path(tmp_path))
    fp = FakeProbe(script=[
        probe_result(content="desc", completion_tokens=10),
        probe_result(content="PASS", completion_tokens=1),
    ])
    monkeypatch.setattr(VG.client, "probe", fp)
    monkeypatch.setattr(VG.model_params, "params_for",
                        lambda model, profile: {"thinking_budget": 1000, "max_tokens": 2000})
    monkeypatch.setattr(VG.model_params, "registry_context_limit", lambda model: None)
    monkeypatch.setattr(VG.generate, "rows_for_rate", lambda model, bench: [])

    rc = VG.main(["--model", "m", "--corpus", str(corpus), "--out", str(out), "--resume"])
    assert rc == 0
    assert fp.n_calls == 2                              # only the NEW id (cocoval2017-001) ran
    rows = [json.loads(l) for l in out.read_text().splitlines() if l.strip()]
    assert {r["id"] for r in rows} == {"cocoval2017-000", "cocoval2017-001"}
    summary = json.loads((out.parent / "vision_gate.v1.summary.json").read_text())
    assert summary["n"] == 2


# --------------------------------------------------------------------------- transport failures escalate
def test_main_propagates_transport_error_and_never_writes_a_row_for_that_item(tmp_path, monkeypatch):
    """AGENTS.md: transport/HTTP failures ESCALATE, they are never graded. `main()` must raise
    (the __main__ wrapper is what turns that into a nonzero exit); no row for the failing item
    may land in --out."""
    import urllib.error
    out = tmp_path / "results" / "m" / "vision_gate.v1.jsonl"
    corpus = tmp_path / "corpus.jsonl"
    _write_jsonl(corpus, [_row(id="cocoval2017-000")])

    monkeypatch.setattr(VG, "resolve_image", lambda row, cache: _tiny_jpeg_path(tmp_path))

    def boom(*a, **kw):
        raise urllib.error.URLError("connection refused")
    monkeypatch.setattr(VG.client, "probe", boom)
    monkeypatch.setattr(VG.model_params, "params_for",
                        lambda model, profile: {"thinking_budget": 1000, "max_tokens": 2000})
    monkeypatch.setattr(VG.model_params, "registry_context_limit", lambda model: None)
    monkeypatch.setattr(VG.generate, "rows_for_rate", lambda model, bench: [])

    with pytest.raises(urllib.error.URLError):
        VG.main(["--model", "m", "--corpus", str(corpus), "--out", str(out)])
    assert not out.exists() or out.read_text().strip() == ""


def test_cli_help_does_not_crash():
    import subprocess
    from bench import paths
    r = subprocess.run([sys.executable, str(paths.BENCHMARK_DIR / "vision_gate.py"), "--help"],
                       capture_output=True, text=True, cwd=str(paths.repo_root()),
                       env={"PYTHONPATH": str(paths.BENCHMARK_DIR), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0
    assert "--resume" in r.stdout
