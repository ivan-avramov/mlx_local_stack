"""M65 tg2 grader, a timeout kill keeps its start evidence (spec docs/specs/m65-tg2-grade-timeout-evidence.md v1),
acceptance 2 in the real pinned image: a spinning solution per language is outcome `timeout`, its runner-start marker read
back from the report-volume file (the killed docker CLI leaves the host-side stream empty), its partial output retained.

Items are the draw's pilot items the recorded trees use (rust/say, javascript/word-search, java/zipper, cpp/spiral-matrix).
Rust spin = the recorder's `zz_spin` test appended to the reference (equivalent to the recorded tree, which kept only the
grader outputs); JavaScript spin = the recorded repro's solution file (sha-pinned fixture) over the prepared stub; Java / C++
spin = the reference with a spinning static (allow-shorthand: the language keyword) initializer. Skipped with the reason when docker / the image / the corpus is absent."""

import hashlib
import json
import re
import shutil
import time
from pathlib import Path

import pytest

from bench import tg2_grade as tg
from bench.tests.test_tg2_grade import DOCKER_SKIP, POLYGLOT, _docker_env, tmp_path  # noqa: F401
from bench.token_turn_gate import TransportAbort  # noqa: F401

FIXTURES = Path(__file__).parent / "fixtures" / "tg2_grade_timeout_impl"
ITEMS = dict(rust="say", javascript="word-search", java="zipper", cpp="spiral-matrix")
# Step timeout (s) per item, spec erratum v1a (S25-P5): >= 3 x the slowest reference step measured on a quiet box, floor 5 s;
# never the smallest passing value. Measured 2026-11-16 (OrbStack, pinned image), reference graded three times (one run at a
# 300 s timeout, two at the then-spin timeouts); slowest step seen per item (MEASURED_MAX, s):
#   rust  compile 0.532 -> 3x = 1.6  -> floor 5        javascript execute 0.843 -> 3x = 2.5 -> floor 5
#   cpp   compile 4.232 -> 3x = 12.7 -> 20             java       execute 4.487 -> 3x = 13.5 -> 18
# test_the_reference_still_compiles_and_passes_at_the_spin_timeout re-proves each value on every run.
MEASURED_MAX = dict(rust=0.532, javascript=0.843, cpp=4.232, java=4.487)
SPIN_TIMEOUT = dict(rust=5, javascript=5, cpp=20, java=18)      # cpp 20 s: designer merge amendment (verify GLM F1, ~4.7x)
assert all(SPIN_TIMEOUT[k] >= max(5, 3 * MEASURED_MAX[k]) for k in SPIN_TIMEOUT)
RUST_SPIN = "\n#[cfg(test)]\nmod zz_inject {\n    #[test]\n    fn zz_spin() { loop { std::hint::spin_loop(); } }\n}\n"
# The recorded JavaScript repro (`$STACK_WORKDIR/m76/tg2-record-scratch/js-spin/tree`): only its solution differs from the
# prepared stub; every other recorded file is pinned here and checked against the stub the test builds.
JS_SPIN_TREE = {
    "word-search.spec.js": "249296d2fbde7bc3949782468353968ef42120980f5a283967cf1cbf6cc8e65b",
    "LICENSE": "e52f804e74f0fbd34e8927962319df346166b8194094309a0aee318693df44df",
    ".eslintrc": "77e1a47bf248ee8ac2f88bb7a68458b36f1c11beff01b081c481c053b163ff75",
    ".npmrc": "6542f3e59455afe3a988ac72da0d2f92ce61666ad2c258e2c7847b5a75b6743a",
    "babel.config.js": "76d07c91b23ee54d8064fae124c8937f9d02a6f758a63446e137f62923e0e8fa",
    "package.json": "3e9207714da156cd681c9a8e84d780705a3d066a9477f28b724febf6f9378be2",
    "word-search.js": "826d156cfd6d195717cfc8cc209f1204f9077cf3325b90b48b36de5d863eddcc",
}

pytestmark = [pytest.mark.docker, pytest.mark.skipif(DOCKER_SKIP is not None, reason=DOCKER_SKIP or "")]


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _stub(tmp_path, lang):
    from bench.tests import tg2_trees
    slug = ITEMS[lang]
    stub = tg2_trees.stub_tree(POLYGLOT, lang, slug, tmp_path / "stub")
    return stub, tg.manifest(stub), tg2_trees.solutions(POLYGLOT, lang, slug)


def _reference(tmp_path, lang, stub):
    from bench.tests import tg2_trees
    ref = tmp_path / "ref"
    shutil.copytree(stub, ref)
    return tg2_trees.apply_reference(POLYGLOT, lang, ITEMS[lang], ref)


def _spin(tmp_path, lang, stub, sols):
    if lang == "javascript":
        tree = tmp_path / "spin"
        shutil.copytree(stub, tree)
        assert _sha(FIXTURES / "js-spin/word-search.js") == JS_SPIN_TREE["word-search.js"]
        shutil.copyfile(FIXTURES / "js-spin/word-search.js", tree / "word-search.js")
        assert {p.relative_to(tree).as_posix(): _sha(p) for p in tree.rglob("*") if p.is_file()} == JS_SPIN_TREE
        return tree
    tree = _reference(tmp_path, lang, stub)
    if lang == "rust":
        sol = tree / "src/lib.rs"
        sol.write_text(sol.read_text() + RUST_SPIN)
    elif lang == "java":
        sol = tree / next(s for s in sols if s.endswith(".java"))
        text = sol.read_text()
        m = re.search(r"\bclass\s+%s\b[^{]*\{" % re.escape(sol.stem), text)
        sol.write_text(text[:m.end()] + "\n    static { while (System.nanoTime() != 0L) { } }\n" + text[m.end():])  # allow-shorthand: the Java / C++ keyword
    else:
        sol = tree / next(s for s in sols if s.endswith(".cpp"))
        sol.write_text(sol.read_text() + "\nnamespace {\nstruct ZzSpin { ZzSpin() { volatile bool f = true; while (f) {} } };"
                                         "\nZzSpin zz_spin_instance;\n}\n")
    return tree


def _grade(lang, tree, tmp_path, stub, prepared, sols, timeout, name):
    from bench.tests import tg2_trees
    guard = tg.LocalDocker()
    started = time.monotonic()
    result = tg.grade_item(lang, tree, ITEMS[lang], tmp_path / ("private-" + name), prepared=prepared, solutions=sols,
                           prepared_cargo_toml=(stub / "Cargo.toml").read_text() if lang == "rust" else None,
                           extra_crates=tg2_trees.extra_crates(POLYGLOT, lang, ITEMS[lang]), guard=guard, image_id=None,
                           timeout=timeout, keep=tmp_path / ("keep-" + name), seq=1, boundary=0, final=True)
    wall = round(time.monotonic() - started, 1)
    print("TG2_TIMING %s" % json.dumps(dict(lang=lang, case=name, timeout=timeout, wall_s=wall, outcome=result.outcome,
                                            phases={p["step"]: p["seconds"] for p in result.phases})))
    assert not guard.leftover() and not guard.leftover_volumes()
    return result, tmp_path / ("keep-" + name) / "seq-0001"


@pytest.mark.parametrize("lang", sorted(ITEMS))
def test_the_reference_still_compiles_and_passes_at_the_spin_timeout(tmp_path, lang):
    _docker_env()
    stub, prepared, sols = _stub(tmp_path, lang)
    ref = _reference(tmp_path, lang, stub)
    result, _ = _grade(lang, ref, tmp_path, stub, prepared, sols, SPIN_TIMEOUT[lang], "ref")
    assert result.outcome == "parsed" and result.collected and result.passing == result.collected, result.phases


@pytest.mark.parametrize("lang", sorted(ITEMS))
def test_a_spinning_solution_is_a_timeout_with_its_marker_read_back_from_the_file(tmp_path, lang):
    _docker_env()
    stub, prepared, sols = _stub(tmp_path, lang)
    spin = _spin(tmp_path, lang, stub, sols)
    result, d = _grade(lang, spin, tmp_path, stub, prepared, sols, SPIN_TIMEOUT[lang], "spin")
    assert result.outcome == "timeout" and result.all_failed and result.passing == set(), (result.outcome, result.reason)
    steps = [p["step"] for p in result.phases]
    assert steps[-2:] == ["execute", "execute-readback"], steps                   # compile finished; execute was killed
    exe = result.phases[-2]
    assert exe["timed_out"] and exe["rc"] is None and exe["marker_source"] == "file"
    marker = (d / "execute.marker").read_text()
    assert re.fullmatch(r"TG2_RUNNER_START [0-9a-f]{16}\n", marker)
    assert exe["marker_sha256"] == _sha(d / "execute.marker")
    out = (d / "execute.out").read_text(errors="replace")
    assert exe["out_sha256"] == _sha(d / "execute.out") and out.startswith(marker)  # partial output retained
    if lang == "rust":
        assert "running" in out                                                  # libtest got as far as the spin
    index = json.loads((d / "index.json").read_text())
    assert index["outcome"] == "timeout" and {"execute.marker", "execute.out"} <= set(index["artifacts"])


def _stream_lost(monkeypatch, tag):
    """Make the grader see the step's stream marker as lost (the box fact a kill produces), so its read-back runs."""
    seen = tg._marker_seen

    def patched(rec, t, nonce, stream="stdout"):
        return False if (t == tag and stream != "stderr") else seen(rec, t, nonce, stream=stream)
    monkeypatch.setattr(tg, "_marker_seen", patched)


def _plain_grade(lang, tree, tmp_path, prepared, timeout, name):
    """`grade` without the tamper gate (a `build.rs` is tamper-denied; this exercises the compile step itself)."""
    guard = tg.LocalDocker()
    started = time.monotonic()
    try:
        result = tg.grade(lang, tree, ITEMS[lang], tmp_path / ("private-" + name), prepared=prepared, guard=guard,
                          timeout=timeout, keep=tmp_path / ("keep-" + name), seq=1, boundary=0, final=True)
        print("TG2_TIMING %s" % json.dumps(dict(lang=lang, case=name, timeout=timeout, outcome=result.outcome,
                                                wall_s=round(time.monotonic() - started, 1),
                                                phases={p["step"]: p["seconds"] for p in result.phases})))
        return result, tmp_path / ("keep-" + name) / "seq-0001"
    finally:
        assert not guard.leftover() and not guard.leftover_volumes()


RUST_FILL = ("\n#[cfg(test)]\nmod zz_inject {\n    use std::io::Write;\n    #[test]\n    fn zz_fill() {\n"
             "        let mut o = std::io::stdout();\n        let line = [b'x'; 4096];\n"
             "        for _ in 0..4200 { let _ = o.write_all(&line); }\n        let _ = o.flush();\n"
             "        loop { std::hint::spin_loop(); }\n    }\n}\n")


@pytest.mark.parametrize("cap", ["shipped", "too_small_control"])
def test_g2_a_full_out_is_read_back_whole_on_the_box(tmp_path, monkeypatch, cap):
    """G2: a solution fills OUTPUT_CAP then spins; with its stream marker treated as lost, the real read-back tars a full
    `.out` and exits 0. Control: READBACK_CAP = OUTPUT_CAP cannot hold that tar -> TransportAbort, the G2 hazard. On the
    box (2026-11-16) the overflow (~13 KB) fit the pipe buffer, so tar exited 0 and the size check refused the archive;
    a larger overflow takes the tar-SIGPIPE (rc 141) path. Both are `read-back` TransportAborts."""
    _docker_env()
    stub, prepared, sols = _stub(tmp_path, "rust")
    tree = _reference(tmp_path, "rust", stub)
    (tree / "src/lib.rs").write_text((tree / "src/lib.rs").read_text() + RUST_FILL)
    _stream_lost(monkeypatch, tg.MARKER)
    if cap == "too_small_control":
        monkeypatch.setattr(tg, "READBACK_CAP", tg.OUTPUT_CAP)
        with pytest.raises(TransportAbort, match="read-back"):
            _plain_grade("rust", tree, tmp_path, prepared, SPIN_TIMEOUT["rust"], "fill-control")
        return
    result, d = _plain_grade("rust", tree, tmp_path, prepared, SPIN_TIMEOUT["rust"], "fill")
    assert result.outcome == "timeout" and result.phases[-1]["step"] == "execute-readback", result.phases
    assert (d / "execute.out").stat().st_size == tg.OUTPUT_CAP
    assert (d / "execute.out").read_bytes().startswith((d / "execute.marker").read_bytes())


BUILD_RS_LOOP = "fn main() { loop { std::hint::spin_loop(); } }\n"


@pytest.mark.parametrize("evidence", ["shipped", "stream_only_control"])
def test_g4_a_looping_build_script_is_a_compile_timeout_on_the_box(tmp_path, monkeypatch, evidence):
    """G4: a Rust `build.rs` that never returns hangs the compile step; at a 5 s step timeout it is `timeout`, the compile
    marker read back from the file. Control: stream-only marker evidence (the baseline rule) -> TransportAbort, i.e. the
    killed compile step's stream really is empty on the box."""
    _docker_env()
    stub, prepared, sols = _stub(tmp_path, "rust")
    tree = _reference(tmp_path, "rust", stub)
    (tree / "build.rs").write_text(BUILD_RS_LOOP)
    if evidence == "stream_only_control":
        def stream_only(rec, step, tag, nonce, stream="stdout", **kw):
            return tg._marker_seen(rec, tag, nonce, stream=stream)
        monkeypatch.setattr(tg, "_marker_evidence", stream_only)
        with pytest.raises(TransportAbort, match="compile: start marker absent"):
            _plain_grade("rust", tree, tmp_path, prepared, 5, "buildrs-control")
        return
    result, d = _plain_grade("rust", tree, tmp_path, prepared, 5, "buildrs")
    assert result.outcome == "timeout" and result.all_failed, (result.outcome, result.reason_detail)
    assert [p["step"] for p in result.phases][-2:] == ["compile", "compile-readback"]
    comp = result.phases[-2]
    assert comp["timed_out"] and comp["marker_source"] == "file"
    assert re.fullmatch(r"TG2_COMPILE_START [0-9a-f]{16}\n", (d / "compile.marker").read_text())
