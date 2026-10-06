"""A1: result and manifest are staged, then published back to back (result first); the manifest
carries the sha256 of the result it describes so a mixed pair is detectable."""
import hashlib
import json
import os

import pytest

import bench.provenance as P
from bench.tests.test_refused_result_drivers import ARGV, CASES, _setup

OLD_RESULT = '{"old": "result"}'
FUSED = ["--attention-policy", "fused_v1"]


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _old_pair(out, name):
    (out / f"{name}.json").write_text(OLD_RESULT)
    old_manifest = json.dumps({"old": "manifest", "result_file": f"{name}.json",
                               "result_sha256": _sha(OLD_RESULT.encode())}).encode()
    (out / f"{name}.manifest.json").write_bytes(old_manifest)
    return old_manifest


def _agree(monkeypatch):
    monkeypatch.setattr(P, "_worker_argvs", lambda doc: [ARGV + FUSED])


def _run(mod):
    return mod.main(["--model", "mymodel", "--sampling-profile", "production", "--grid", "8000"])


def _failing_replace(monkeypatch, fail_on_call, exc=KeyboardInterrupt):
    real, calls = os.replace, {"n": 0}

    def replace(a, b, *x, **k):
        calls["n"] += 1
        if calls["n"] == fail_on_call:
            raise exc("injected")
        return real(a, b, *x, **k)
    monkeypatch.setattr(os, "replace", replace)
    return calls


@pytest.mark.parametrize("name", list(CASES))
def test_interrupt_before_the_first_replace_leaves_the_old_pair_byte_identical(monkeypatch, tmp_path, name):
    mod, ladder, canned = CASES[name]
    out = _setup(monkeypatch, tmp_path, mod, ladder, canned)
    _agree(monkeypatch)
    old_manifest = _old_pair(out, name)
    _failing_replace(monkeypatch, 1)
    with pytest.raises(KeyboardInterrupt):
        _run(mod)
    assert (out / f"{name}.json").read_text() == OLD_RESULT
    assert (out / f"{name}.manifest.json").read_bytes() == old_manifest
    assert P.manifest_matches_result(str(out / f"{name}.manifest.json"), str(out / f"{name}.json")) is True


@pytest.mark.parametrize("name", list(CASES))
def test_interrupt_between_the_two_replaces_is_detectable(monkeypatch, tmp_path, name):
    mod, ladder, canned = CASES[name]
    out = _setup(monkeypatch, tmp_path, mod, ladder, canned)
    _agree(monkeypatch)
    old_manifest = _old_pair(out, name)
    calls = _failing_replace(monkeypatch, 2)
    with pytest.raises(KeyboardInterrupt):
        _run(mod)
    assert calls["n"] == 2                           # result replaced, manifest replace interrupted
    assert (out / f"{name}.manifest.json").read_bytes() == old_manifest   # the OLD manifest remains
    assert (out / f"{name}.json").read_text() != OLD_RESULT               # new result published
    assert P.manifest_matches_result(str(out / f"{name}.manifest.json"), str(out / f"{name}.json")) is False


@pytest.mark.parametrize("name", list(CASES))
def test_any_exception_before_publication_never_leaves_a_half_published_pair(monkeypatch, tmp_path, name):
    mod, ladder, canned = CASES[name]
    out = _setup(monkeypatch, tmp_path, mod, ladder, canned)
    _agree(monkeypatch)
    old_manifest = _old_pair(out, name)

    def boom(*a, **k):
        raise RuntimeError("disk full while preparing the manifest")
    monkeypatch.setattr(P, "result_digest", boom)
    with pytest.raises(RuntimeError):
        _run(mod)
    assert (out / f"{name}.json").read_text() == OLD_RESULT
    assert (out / f"{name}.manifest.json").read_bytes() == old_manifest


@pytest.mark.parametrize("name", list(CASES))
def test_successful_run_publishes_a_matching_pair(monkeypatch, tmp_path, name):
    mod, ladder, canned = CASES[name]
    out = _setup(monkeypatch, tmp_path, mod, ladder, canned)
    _agree(monkeypatch)
    _old_pair(out, name)
    assert _run(mod) == 0
    man = json.loads((out / f"{name}.manifest.json").read_text())
    assert man["result_file"] == f"{name}.json"
    assert man["result_sha256"] == _sha((out / f"{name}.json").read_bytes())
    assert P.manifest_matches_result(str(out / f"{name}.manifest.json"), str(out / f"{name}.json")) is True
    assert not list(out.glob("*pending*")) and not list(out.glob("*refused*"))


def test_helper_returns_none_for_a_manifest_without_a_digest(tmp_path):
    (tmp_path / "r.json").write_text("x")
    (tmp_path / "m.json").write_text(json.dumps({"model": "m"}))
    assert P.manifest_matches_result(str(tmp_path / "m.json"), str(tmp_path / "r.json")) is None


def test_helper_true_false_and_unreadable(tmp_path):
    (tmp_path / "r.json").write_bytes(b"abc")
    (tmp_path / "m.json").write_text(json.dumps({"result_sha256": _sha(b"abc"), "result_file": "r.json"}))
    assert P.manifest_matches_result(str(tmp_path / "m.json"), str(tmp_path / "r.json")) is True
    (tmp_path / "r.json").write_bytes(b"abd")
    assert P.manifest_matches_result(str(tmp_path / "m.json"), str(tmp_path / "r.json")) is False
    (tmp_path / "m2.json").write_text(json.dumps({"result_sha256": _sha(b"abc"), "result_file": "other.json"}))
    assert P.manifest_matches_result(str(tmp_path / "m2.json"), str(tmp_path / "r.json")) is False
    (tmp_path / "bad.json").write_text("{not json")
    assert P.manifest_matches_result(str(tmp_path / "bad.json"), str(tmp_path / "r.json")) is False
    assert P.manifest_matches_result(str(tmp_path / "gone.json"), str(tmp_path / "r.json")) is False


# --------------------------------------------------------------------------- Codex review 10 residuals B2/B3
def test_helper_treats_a_non_object_manifest_as_damaged_not_legacy(tmp_path):
    """B2: valid JSON that is not an object (`[]`, `"x"`) is damage, not a digestless legacy manifest."""
    (tmp_path / "r.json").write_text("x")
    for body in ("[]", '"s"', "null", "3"):
        (tmp_path / "m.json").write_text(body)
        assert P.manifest_matches_result(str(tmp_path / "m.json"), str(tmp_path / "r.json")) is False


def test_helper_digestless_manifest_beside_a_missing_result_is_damaged(tmp_path):
    """B2: `None` means 'legacy pair, cannot judge'; it must not be returned when there is no
    result to judge at all."""
    (tmp_path / "m.json").write_text(json.dumps({"model": "m"}))
    assert P.manifest_matches_result(str(tmp_path / "m.json"), str(tmp_path / "gone.json")) is False


@pytest.mark.parametrize("name", list(CASES))
def test_manifest_write_failure_leaves_the_old_pair_and_only_pending_files(monkeypatch, tmp_path, name):
    """B3: a failure while WRITING the staged manifest (after gather succeeded) must publish
    nothing — the old pair stays byte-identical and the new result stays `.pending-<pid>`."""
    mod, ladder, canned = CASES[name]
    out = _setup(monkeypatch, tmp_path, mod, ladder, canned)
    _agree(monkeypatch)
    old_manifest = _old_pair(out, name)
    real_dump = json.dump

    def dump(obj, fp, *a, **k):
        if isinstance(obj, dict) and "result_sha256" in obj:
            raise OSError("injected manifest write failure")
        return real_dump(obj, fp, *a, **k)
    monkeypatch.setattr(json, "dump", dump)
    with pytest.raises(OSError, match="injected"):
        _run(mod)
    assert (out / f"{name}.json").read_text() == OLD_RESULT
    assert (out / f"{name}.manifest.json").read_bytes() == old_manifest
    assert [p.name for p in out.iterdir() if ".pending-" in p.name]


@pytest.mark.parametrize("name", list(CASES))
def test_ordinary_gather_failure_never_publishes_a_result_beside_the_old_manifest(monkeypatch, tmp_path, name):
    """B1/B3: an ordinary `gather` exception used to fall through to a result-only publication,
    leaving NEW result / OLD manifest under canonical names — exactly the mixed pair the digest
    exists to prevent. Now nothing is published: the new result stays `.pending-<pid>`, the old
    pair is untouched, and the run exits nonzero."""
    mod, ladder, canned = CASES[name]
    out = _setup(monkeypatch, tmp_path, mod, ladder, canned)
    _agree(monkeypatch)
    old_manifest = _old_pair(out, name)

    real, n = P.gather, {"calls": 0}

    def boom_after_preflight(*a, **k):
        n["calls"] += 1
        if n["calls"] == 1:
            return real(*a, **k)            # the entry preflight passes
        raise RuntimeError("registry unreadable")
    monkeypatch.setattr(P, "gather", boom_after_preflight)
    rc = _run(mod)
    assert rc == 3
    assert (out / f"{name}.json").read_text() == OLD_RESULT
    assert (out / f"{name}.manifest.json").read_bytes() == old_manifest
    pending = [p.name for p in out.iterdir() if ".pending-" in p.name]
    assert pending and all(p.startswith(f"{name}.json") for p in pending)
