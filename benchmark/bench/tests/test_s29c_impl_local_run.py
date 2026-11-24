"""S29 acceptance 1 and 3 on ONE item per tg2 language (the draw's pilot item), for real: in the prepared (testable) workspace with
the reference solution, the language's standard full-suite command (`corpus_tg2.FULL_SUITE_COMMANDS`, the host toolchain) runs
exactly the test cases the real grader (`tg2_grade.grade_item`, docker, the pinned image) grades on the same tree — same names,
same count, all passing; after it the production tamper check (`Tg2Corpus.tamper_reasons` on the corpus snapshot) finds
nothing; and a known negative (a solution that compiles but is wrong) fails locally and in the grader. Every other item is
covered without docker by `test_s29c_impl_workspace`. Skipped (with the reason) when docker, the image, a toolchain or the
network the toolchain needs is unavailable."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from bench import tg2_grade as tg

BENCH = Path(__file__).resolve().parents[1].parent
UNIVERSE = json.loads((BENCH / "m65/tg2_universe.json").read_text())
DRAW = json.loads((BENCH / "m65/tg2_draw.json").read_text())
LANGS = ("rust", "javascript", "java", "cpp")
PILOT = {lang: DRAW["languages"][lang]["permutation"][0] for lang in LANGS}
TOOLS = {"rust": ("cargo",), "javascript": ("npm", "node"), "java": ("java",), "cpp": ("cmake", "c++")}
TIMEOUT_S = 1800


def _polyglot():
    from bench import opencode_v2_core as core
    try:
        return core._polyglot_root()
    except SystemExit:
        pytest.skip("the pinned polyglot checkout is not on this box")


def _docker_or_skip():
    try:
        tg.pinned_image_id()
        ok = subprocess.run(["docker", "image", "inspect", tg.IMAGE_TAG], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError, tg.TransportAbort, ValueError) as exc:
        pytest.skip(f"docker / the pinned tg2 grader image is unavailable ({type(exc).__name__})")
    if not ok:
        pytest.skip(f"the pinned tg2 grader image {tg.IMAGE_TAG} is not loaded")


@pytest.fixture
def root():
    from bench.tests.tg2_test_root import tg2_root
    d = tg2_root() / f"s29c-run-{uuid.uuid4().hex[:10]}"
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _env(root):
    env = dict(os.environ)
    env.update(GRADLE_USER_HOME=str(root / "gradle-home"), npm_config_cache=str(root / "npm-cache"), CI="1",
               npm_config_update_notifier="false", npm_config_fund="false", npm_config_audit="false")
    return env


def _sh(command, cwd, env):
    return subprocess.run(["/bin/sh", "-c", command], cwd=cwd, env=env, capture_output=True, text=True, timeout=TIMEOUT_S,
                          stdin=subprocess.DEVNULL)


def _local_leaves(lang, slug, work, root):
    """(rc of the standard full-suite command, {leaf: passed}) of the cases it executed, named as the grader names them."""
    from bench import corpus_tg2
    env = _env(root)
    command = corpus_tg2.FULL_SUITE_COMMANDS[lang]
    if lang == "rust":
        done = _sh(command + " 2>&1", work, env)
        return done.returncode, tg.parse_rust(done.stdout), done.stdout
    if lang == "cpp":
        done = _sh(command + " 2>&1", work, env)
        if not (work / "build" / slug).is_file():
            return done.returncode, {}, done.stdout
        xml = root / "local-cpp.xml"
        _sh(f"./build/{slug} -r junit -o {xml}", work, env)        # the binary the build ran, asked for its case names
        return done.returncode, tg.parse_junit(xml.read_text()), done.stdout
    if lang == "java":
        done = _sh(command + " --console=plain 2>&1", work, env)
        results = sorted((work / "build/test-results/test").glob("*.xml"))
        if not results and ("Could not" in done.stdout or "UnknownHost" in done.stdout):
            pytest.skip("gradle could not fetch its distribution / dependencies (no network and no prefilled home)")
        return done.returncode, tg.merge_leaves(*(tg.parse_junit(p.read_text()) for p in results)), done.stdout
    install = _sh("npm install 2>&1", work, env)
    if install.returncode != 0:
        pytest.skip("npm install failed (no network for the jest / babel dev dependencies): " + install.stdout[-300:])
    out = root / "local-jest.json"
    done = _sh(f"npm test -- --ci --json --outputFile={out} 2>&1", work, env)
    return done.returncode, tg.parse_jest(out.read_text(), str(Path(work).resolve())), done.stdout


def _grade(corpus, prepared, root, tag):
    private = root / f"run-{tag}" / "grading-private"
    private.mkdir(parents=True)
    entry = prepared.entry
    with corpus.snapshot(prepared.work, private, 0) as snap:
        assert snap is not None
        reasons = corpus.tamper_reasons(snap, prepared)
        result = tg.grade_item(prepared.lang, snap.path, prepared.name, private, prepared=prepared.prepared,
                               solutions=entry["solutions"], prepared_cargo_toml=entry.get("prepared_cargo_toml"),
                               extra_crates=tuple(entry.get("reference_extra_crates") or ()) if tag == "reference" else (),
                               timeout=entry["timeout_s"])
    return reasons, result


def _wrong(lang, corpus, prepared):
    """The known negative: a solution that compiles but is wrong (the stub for Rust / Java / JS, whose bodies compile and fail;
    for C++ the reference off by one, since the C++ stub declares nothing)."""
    from bench import tg2_materialize as mat
    if lang != "cpp":
        return
    mat.apply_reference(corpus.polyglot_root(), mat.read_plan(corpus.polyglot_root(), lang, prepared.name), prepared.work)
    src = prepared.work / "spiral_matrix.cpp"
    text = src.read_text()
    assert "matrix_elem(coords) = i;" in text
    src.write_text(text.replace("matrix_elem(coords) = i;", "matrix_elem(coords) = i + 1;"))


@pytest.mark.parametrize("lang", LANGS)
def test_acceptance_1_and_3_the_local_full_suite_is_the_graded_suite(root, lang):
    from bench import corpus_tg2
    from bench import tg2_materialize as mat
    missing = [t for t in TOOLS[lang] if shutil.which(t) is None]
    if missing:
        pytest.skip(f"the {lang} toolchain is not installed ({missing})")
    _docker_or_skip()
    corpus = corpus_tg2.Tg2Corpus(polyglot_root=_polyglot)
    item = PILOT[lang]
    slug = item.split("/", 1)[1]
    entry = UNIVERSE["items"][item]
    universe = set(entry["leaves"])
    optional = set(tg.OPTIONAL_LEAVES.get((lang, slug), ()))
    # -- the reference: every graded case runs locally and passes; the grader grades the same cases on the same tree
    prepared = corpus.prepare(item, root / "ref" / slug)
    mat.apply_reference(corpus.polyglot_root(), mat.read_plan(corpus.polyglot_root(), lang, slug), prepared.work)
    rc, local, out = _local_leaves(lang, slug, prepared.work, root)
    assert rc == 0, out[-3000:]
    reasons, graded = _grade(corpus, prepared, root, "reference")
    assert reasons == []                                                       # acceptance 3: the local build left no tamper
    assert graded.outcome == "parsed", (graded.reason, graded.reason_detail)
    assert set(local) == set(graded.leaves), (sorted(set(local) ^ set(graded.leaves)))
    assert set(local) - optional == universe and len(local) == len(graded.leaves)
    assert all(local[k] for k in universe) and all(graded.leaves[k] for k in universe)
    assert graded.failing(universe) == 0
    # -- the known negative: compiles, fails locally and in the grader
    neg = corpus.prepare(item, root / "neg" / slug)
    _wrong(lang, corpus, neg)
    rc_n, local_n, out_n = _local_leaves(lang, slug, neg.work, root)
    assert rc_n != 0 and local_n, out_n[-3000:]
    assert set(local_n) - optional == universe                                 # it compiled: every graded case ran ...
    assert not all(local_n[k] for k in universe)                               # ... and some failed
    reasons_n, graded_n = _grade(corpus, neg, root, "negative")
    assert reasons_n == [] and graded_n.outcome == "parsed"
    assert graded_n.failing(universe) > 0
    assert {k for k in universe if not local_n[k]} == {k for k in universe if not graded_n.leaves.get(k)}
