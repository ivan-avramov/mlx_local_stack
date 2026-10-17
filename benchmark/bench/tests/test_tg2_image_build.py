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
