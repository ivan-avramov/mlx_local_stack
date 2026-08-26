"""C32: a bare `--limit 5` was SILENTLY IGNORED — `_parse_kv` only understood
`bench=N` parts and dropped everything else, so a bare integer meant NO CAP and
launched the full corpus (bit the m23c pilot launch 2026-08-26; caught by the
item counter within 20 s). Ruling: bare int broadcasts to ALL requested benches;
anything unparseable REFUSES with a nonzero exit, never a silent no-cap.
"""
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "runmod", Path(__file__).resolve().parents[2] / "run.py")
RUN = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(RUN)


def test_per_bench_specs_unchanged():
    assert RUN._parse_kv("humanevalplus=5,mbppplus=7") == {
        "humanevalplus": 5, "mbppplus": 7}


def test_empty_is_no_caps():
    assert RUN._parse_kv("") == {}
    assert RUN._parse_kv(None) == {}


def test_bare_int_broadcasts_to_all_requested_benches():
    assert RUN._parse_kv("5", benches=["humanevalplus", "mbppplus"]) == {
        "humanevalplus": 5, "mbppplus": 5}


def test_bare_int_mixes_with_per_bench_parts():
    """Later per-bench parts override the broadcast."""
    assert RUN._parse_kv("5,mbppplus=20", benches=["humanevalplus", "mbppplus"]) == {
        "humanevalplus": 5, "mbppplus": 20}


def test_unparseable_part_refuses():
    with pytest.raises(SystemExit):
        RUN._parse_kv("bogus", benches=["humanevalplus"])


def test_bare_int_without_bench_context_refuses():
    """A broadcast needs a bench list; silently returning {} is the C32 shape."""
    with pytest.raises(SystemExit):
        RUN._parse_kv("5")
