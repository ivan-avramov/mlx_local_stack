"""tg2 image reproducibility inputs (G7, G12): corpus pin verification, staged-context digest, committed lock
artifacts, image metadata."""

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

IMAGE_DIR = Path(__file__).resolve().parents[2] / "m65/tg2_image"


def load(name):
    spec = importlib.util.spec_from_file_location("tg2_image_" + name, IMAGE_DIR / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def corpus(tmp_path):
    repo = tmp_path / "corpus"
    for lang in ("rust", "java", "javascript", "cpp", "python"):
        (repo / lang).mkdir(parents=True)
        (repo / lang / "f.txt").write_text(lang)
    git(repo, "init", "-q")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "add", ".")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "c")
    return repo


def test_verify_corpus_accepts_the_pinned_clean_checkout(corpus):
    sha = git(corpus, "rev-parse", "HEAD")
    assert load("verify_corpus").verify(corpus, sha) == sha


def test_verify_corpus_refuses_wrong_sha_and_dirty_tracked_or_untracked_files(corpus):
    vc = load("verify_corpus")
    sha = git(corpus, "rev-parse", "HEAD")
    with pytest.raises(SystemExit):
        vc.verify(corpus, "0" * 40)
    (corpus / "rust/f.txt").write_text("edited")
    with pytest.raises(SystemExit):
        vc.verify(corpus, sha)
    git(corpus, "checkout", "--", "rust/f.txt")
    (corpus / "java/new.txt").write_text("x")
    with pytest.raises(SystemExit):
        vc.verify(corpus, sha)
    (corpus / "java/new.txt").unlink()
    (corpus / "python/junk.pyc").write_text("x")          # languages the image does not use are ignored
    assert vc.verify(corpus, sha) == sha


def test_pinned_polyglot_sha_is_committed_and_well_formed():
    text = (IMAGE_DIR / "polyglot_sha").read_text().strip()
    assert len(text) == 40 and set(text) <= set("0123456789abcdef")


def test_context_digest_is_deterministic_and_content_sensitive(tmp_path):
    sc = load("stage_context")
    ctx = tmp_path / "ctx"
    (ctx / "a").mkdir(parents=True)
    (ctx / "a/x").write_text("1")
    (ctx / "y").write_text("2")
    d1 = sc.context_digest(ctx)
    assert d1 == sc.context_digest(ctx) and len(d1) == 64
    (ctx / "y").write_text("3")
    assert sc.context_digest(ctx) != d1


def test_committed_lock_artifacts_cover_js_and_every_rust_manifest():
    locks = IMAGE_DIR / "locks"
    pkg = json.loads((locks / "js/package.json").read_text())
    lock = json.loads((locks / "js/package-lock.json").read_text())
    assert lock["lockfileVersion"] >= 2 and lock["packages"][""]["devDependencies"] == pkg["devDependencies"]
    assert "node_modules/jest" in lock["packages"]
    rust = sorted(p.relative_to(locks / "rust").as_posix() for p in (locks / "rust").rglob("Cargo.lock"))
    assert "gigasecond/Cargo.lock" in rust and "macros/tests/invalid/Cargo.lock" in rust and len(rust) >= 31


def test_stage_context_requires_locks_and_matching_js_manifest(tmp_path):
    sc = load("stage_context")
    corpus = tmp_path / "c"
    (corpus / "java/exercises/practice").mkdir(parents=True)
    with pytest.raises(SystemExit):
        sc.main(str(corpus), str(tmp_path / "ctx"))          # fixture corpus has no closures: refuses


def test_image_id_file_records_metadata():
    lines = (IMAGE_DIR / "IMAGE_ID").read_text().splitlines()
    assert lines[0].startswith("sha256:") and len(lines[0]) == 71
    meta = dict(line.split("=", 1) for line in lines[1:])
    assert {"polyglot_sha", "context_sha256", "js_lock_sha256", "cargo_locks_sha256"} <= set(meta)
    assert meta["polyglot_sha"] == (IMAGE_DIR / "polyglot_sha").read_text().strip()


def test_g20_js_lock_digest_is_the_sha256_of_the_lock_file_bytes():
    import hashlib
    meta = dict(line.split("=", 1) for line in (IMAGE_DIR / "IMAGE_ID").read_text().splitlines()[1:])
    assert meta["js_lock_sha256"] == hashlib.sha256((IMAGE_DIR / "locks/js/package-lock.json").read_bytes()).hexdigest()
    assert "shasum -a 256 \"$here/locks/js/package-lock.json\" | shasum" not in (IMAGE_DIR / "build.sh").read_text()


def test_p367_the_allowlist_lock_covers_every_allowlisted_crate_and_the_older_reference_versions():
    import json
    allow = json.loads((IMAGE_DIR / "rust_allowlist.json").read_text())
    text = (IMAGE_DIR / "locks/rust/_allowlist/Cargo.lock").read_text()
    for crate in {c for c, _ in allow["vendor"]}:
        assert 'name = "%s"' % crate in text, crate
    for crate, prefix in (("rand", "0.3."), ("regex", "0.2."), ("itertools", "0.5."), ("permutohedron", "0.2."),
                          ("counter", "0.5."), ("num-bigint", "0.4."), ("thiserror", "1.0."), ("rand", "0.8.")):
        assert 'name = "%s"\nversion = "%s' % (crate, prefix) in text, (crate, prefix)
    assert set(allow["crates"]) <= {c for c, _ in allow["vendor"]}
    assert not ({"permutohedron", "counter"} & set(allow["crates"])) and {"permutohedron", "counter"} <= {
        c for c, _ in allow["vendor"]}


def test_p367_every_cargo_example_dependency_is_allowlisted():
    import json, os, tomllib
    corpus = os.environ.get("POLYGLOT_DIR")
    if not corpus:
        pytest.skip("POLYGLOT_DIR not set")
    allow = {c for c, _ in json.loads((IMAGE_DIR / "rust_allowlist.json").read_text())["vendor"]}
    for path in Path(corpus).glob("rust/exercises/practice/*/.meta/Cargo-example.toml"):
        doc = tomllib.loads(path.read_text())
        for section in ("dependencies", "dev-dependencies", "build-dependencies"):
            assert set(doc.get(section, {})) <= allow, (path, section)
        assert not doc.get("build-dependencies")


def test_p367_staged_context_contains_the_synthetic_allowlist_crate_and_stub_manifests(tmp_path):
    import os
    corpus = os.environ.get("POLYGLOT_DIR")
    if not corpus:
        pytest.skip("POLYGLOT_DIR not set")
    sc = load("stage_context")
    ctx = tmp_path / "ctx"
    sc.main(corpus, str(ctx))
    manifest = (ctx / "rust/_allowlist/Cargo.toml").read_text()
    assert 'package = "regex"' in manifest and 'version = "0.2"' in manifest and (ctx / "rust/_allowlist/src/lib.rs").exists()
    assert "counter" not in (ctx / "rust/poker/Cargo.toml").read_text()                  # stub manifests, no per-item hints
