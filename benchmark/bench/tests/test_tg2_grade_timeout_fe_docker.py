"""M65 tg2 grader: a timeout kill keeps its start evidence -- REAL docker (spec docs/specs/m65-tg2-grade-timeout-evidence.md
v1, acceptance 2 and 3). Skipped, with the reason, when docker / the pinned `tg2-grader` image / the polyglot corpus are absent
(same guard as the existing integration tests in test_tg2_grade.py).

Spin trees are built from the polyglot reference of each item (equivalent to the recorded Rust `spin` and the JavaScript
`while (true) {}` repro; the receipts of the recorded run are under inputs/tg2-grade-trees/*/spin), one per language:
  rust/say              every `pub fn` of src/lib.rs starts with `loop {}`          (compiles; spins when a test calls it)
  javascript/word-search  `while (true) {}` prepended to the solution module         (spins when jest loads it)
  java/zipper           `static { if (System.nanoTime() > 0) { while (true) {} } }` in each top-level class (compiles; spins on class load)  (allow-shorthand: the Java keyword)
  cpp/spiral-matrix     a namespace-scope initialiser that never returns            (compiles; spins at program start)
Every spin compiles, so the kill lands in the EXECUTE step; the marker line of that step was printed before the kill.

STEP TIMEOUTS (spec erratum v1a, G1 / delivery 3): >= 3 x the slowest reference step measured on a quiet box, floor 5 s; never
the smallest passing value. Measured on the quiet box (2026-11-16, OrbStack, pinned image; every step of the reference graded
at a generous timeout, slowest single step over my probe runs, `probe1.txt` / `probe2.txt`):
  rust 0.69 s (compile)   -> 3x = 2.1  -> floor 5 s     javascript 1.06 s (execute) -> 3x = 3.2  -> floor 5 s
  cpp  4.35 s (compile)   -> 3x = 13.0 -> 20 s          java       5.69 s (cold compile) -> 3x = 17.1 -> 18 s
(Delivery 1 used 2 / 2 / 6 / 6 s: the smallest passing values, the flake risk the erratum removes.)

Classes: (a) red on the baseline, (b) green on the baseline, (c) depends on a seam the spec leaves open."""

import json
import re
import shutil
import time
from pathlib import Path

import pytest

from bench import tg2_grade as tg
from bench.tests import test_tg2_grade as base
from bench.tests import tg2_trees
from bench.tests.test_tg2_grade import tmp_path  # noqa: F401  (same non-TMPDIR tree root fixture)

SKIP = dict(reason=base.DOCKER_SKIP or "")
FIXTURE = json.loads((Path(__file__).parent / "fixtures/tg2_grade_timeout_fe/summary_expected.json").read_text())

ITEMS = {"rust": "say", "javascript": "word-search", "java": "zipper", "cpp": "spiral-matrix"}
MEASURED_SLOWEST_STEP_S = {"rust": 0.693, "javascript": 1.058, "java": 5.686, "cpp": 4.346}
SPIN_TIMEOUT = {"rust": 5, "javascript": 5, "java": 18, "cpp": 20}      # cpp 20 s: designer merge amendment (verify GLM F1)
assert all(SPIN_TIMEOUT[k] >= max(5, 3 * v) for k, v in MEASURED_SLOWEST_STEP_S.items())     # the erratum's rule, checked
STEP_TAG = {"compile": "TG2_COMPILE_START", "execute": "TG2_RUNNER_START", "collect": "TG2_COLLECT_START"}


# ------------------------------------------------------------------------------------------------------ tree variants
def _sol_files(lang, ref, sols):
    return [ref / s for s in sols if (lang != "cpp" or s.endswith(".cpp"))]


def make_spin(lang, ref, sols):
    for f in _sol_files(lang, ref, sols):
        text = f.read_text()
        if lang == "rust":
            text = re.sub(r"(pub fn [^{;]*\{)", r"\1 loop {}", text)
        elif lang == "javascript":
            text = "while (true) {}\n" + text
        elif lang == "java":
            text = re.sub(r"(?m)^((?:public |final |abstract )*class \w+[^{]*\{)",
                          r"\1\n    static { if (System.nanoTime() > 0) { while (true) {} } }", text)  # allow-shorthand: the Java / C++ keyword
        else:
            text = "static const int tg2_spin = ([] { volatile bool f = true; while (f) {} return 0; })();\n" + text  # allow-shorthand: the Java / C++ keyword
        assert text != f.read_text(), "spin injection changed nothing in %s" % f
        f.write_text(text)


def make_compile_error(lang, ref, sols):
    for f in _sol_files(lang, ref, sols):
        f.write_text(f.read_text() + ("\n}{ @@ not valid\n" if lang == "javascript" else "\nthis is not valid @@@ ;;\n"))


def make_tampered(lang, ref, sols):
    pattern = {"rust": "tests/*.rs", "javascript": "*.spec.js", "java": "src/test/java/**/*.java", "cpp": "*_test.cpp"}[lang]
    victim = sorted(ref.glob(pattern))[0]
    victim.write_text(victim.read_text() + "\n// tampered\n")


def make_alloc(lang, ref, sols):                 # rust only: grabs memory until the 4g container cap kills it
    for f in _sol_files(lang, ref, sols):
        f.write_text(re.sub(r"(pub fn [^{;]*\{)", r"\1 let mut tg2_v: Vec<Vec<u8>> = Vec::new(); "
                            r"loop { tg2_v.push(vec![1u8; 1 << 28]); }", f.read_text()))


def make_flood(lang, ref, sols):                 # rust only: raw writes to fd 1 (print! is captured by libtest)
    for f in _sol_files(lang, ref, sols):
        f.write_text(re.sub(r"(pub fn [^{;]*\{)", r"\1 { use std::io::Write; let o = std::io::stdout(); let mut l = o.lock(); "
                            r"loop { l.write_all(&[b'x'; 65536]).unwrap(); } }", f.read_text()))


MAKERS = {"compile": make_compile_error, "tampered": make_tampered, "alloc": make_alloc, "flood": make_flood}


def prepare(tmp_path, lang):
    base._docker_env()
    slug = ITEMS[lang]
    guard = tg.LocalDocker()
    stub, prepared, sols = base._item(tmp_path, lang, slug, guard)
    ref = base._ref_of(tmp_path, stub, lang, slug)
    pct = (stub / "Cargo.toml").read_text() if lang == "rust" else None
    extra = tg2_trees.extra_crates(base.POLYGLOT, lang, slug)
    return dict(guard=guard, slug=slug, stub=stub, prepared=prepared, sols=sols, ref=ref, pct=pct, extra=extra)


def grade(tmp_path, ctx, lang, tree, **kw):
    return tg.grade_item(lang, tree, ctx["slug"], tmp_path / "private", prepared=ctx["prepared"], solutions=ctx["sols"],
                         guard=ctx["guard"], prepared_cargo_toml=ctx["pct"], extra_crates=ctx["extra"], **kw)


def variant_tree(tmp_path, ctx, name):
    dest = tmp_path / ("v-" + name)
    shutil.copytree(ctx["ref"], dest)
    return dest


# --------------------------------------------------------------------------------- acceptance 2: spin -> timeout
@pytest.mark.docker
@pytest.mark.skipif(base.DOCKER_SKIP is not None, **SKIP)
@pytest.mark.parametrize("lang", sorted(ITEMS))
def test_a2_a_solution_that_spins_in_execute_is_a_timeout_with_the_marker_read_back_from_the_file(tmp_path, lang):
    """(a) red on the baseline: TransportAbort('tg2 execute: runner-start marker absent (rc=None)').
    (c) for the artifact names/keys only through the spec'd `<step>.marker` / `<step>.out` beside the step outputs."""
    ctx = prepare(tmp_path, lang)
    spin = variant_tree(tmp_path, ctx, "spin")
    make_spin(lang, spin, ctx["sols"])
    started = time.monotonic()
    result = grade(tmp_path, ctx, lang, spin, timeout=SPIN_TIMEOUT[lang], keep=tmp_path / "keep", seq=0, boundary=0)
    print("WALL spin %s: %.1fs" % (lang, time.monotonic() - started))
    assert result.outcome == "timeout", (result.outcome, result.reason_detail)
    assert result.all_failed and result.passing == set() and result.failing({"x", "y"}) == 2
    steps = {p["step"]: p for p in result.phases}
    assert steps["compile"]["rc"] == 0 and not steps["compile"]["timed_out"]         # the spin compiled; the kill is in execute
    assert steps["execute"]["timed_out"] and steps["execute"]["rc"] is None
    assert "collect" not in steps                                                    # nothing ran after the kill
    d = tmp_path / "keep/seq-0000"
    assert (d / "execute.marker").read_text().splitlines()[0:1] and re.fullmatch(
        r"TG2_RUNNER_START [0-9a-f]{16}", (d / "execute.marker").read_text().strip())
    assert (d / "execute.out").is_file()                                             # partial output retained (may be tiny)
    if lang == "rust":                                                               # cargo prints `Running ...` before the test spins
        assert "Running" in (d / "execute.out").read_text()
    assert not ctx["guard"].leftover() and not ctx["guard"].leftover_volumes()       # container and volume cleanup unchanged


@pytest.mark.docker
@pytest.mark.skipif(base.DOCKER_SKIP is not None, **SKIP)
def test_a2_the_marker_in_the_retained_file_carries_the_nonce_of_the_grades_own_scripts(tmp_path):
    """(c) seam: retained receipts expose the executed script only through the step's own artifacts; the test compares the
    nonce of `compile.marker` and `execute.marker` (one nonce per grade) and checks both step records carry their sha256.
    Red on the baseline (no .marker files)."""
    ctx = prepare(tmp_path, "rust")
    spin = variant_tree(tmp_path, ctx, "spin")
    make_spin("rust", spin, ctx["sols"])
    result = grade(tmp_path, ctx, "rust", spin, timeout=SPIN_TIMEOUT["rust"], keep=tmp_path / "keep", seq=0, boundary=0)
    assert result.outcome == "timeout"
    d = tmp_path / "keep/seq-0000"
    # Delivery 2: compile finished with its marker on the stream, so no read-back ran for it (spec: read back only after
    # a step whose stdout lacks the marker): no compile.marker / compile.out is stored.
    assert not (d / "compile.marker").exists() and not (d / "compile.out").exists()
    import hashlib
    phase = next(p for p in json.loads((d / "phases.json").read_text())["phases"] if p["step"] == "execute")
    values = {str(v) for v in phase.values()}
    assert hashlib.sha256((d / "execute.marker").read_bytes()).hexdigest() in values
    assert hashlib.sha256((d / "execute.out").read_bytes()).hexdigest() in values
    assert result.version == tg.VERSION == "m65-tg2-v3"


# -------------------------------------------------------------------- acceptance 3: other recorded variants unchanged
def _expected_rows(lang):
    return {v: row for v, row in FIXTURE["%s/%s" % (lang, ITEMS[lang])].items()}


@pytest.mark.docker
@pytest.mark.skipif(base.DOCKER_SKIP is not None, **SKIP)
@pytest.mark.parametrize("lang", sorted(ITEMS))
def test_a3_recorded_variants_classify_as_in_summary_json(tmp_path, lang):
    """(b) green on the baseline (their outcomes are the baseline's recorded ones); must stay green after the fix.
    Variants per item exactly as in inputs/tg2-grade-trees/SUMMARY.json minus `spin`: reference, stub, compile, tampered
    (+ rust: alloc -> oom, flood -> output_cap). The step timeout is generous: only the classes are under test."""
    ctx = prepare(tmp_path, lang)
    started = time.monotonic()
    universe = None
    mismatches = []
    for variant, want in _expected_rows(lang).items():
        if variant == "reference":
            tree = ctx["ref"]
        elif variant == "stub":
            tree = ctx["stub"]
        else:
            tree = variant_tree(tmp_path, ctx, variant)
            MAKERS[variant](lang, tree, ctx["sols"])
        got = grade(tmp_path, ctx, lang, tree, timeout=300)
        if variant == "reference":
            universe = got.collected
        row = dict(outcome=got.outcome, reason=got.reason, leaves=len(got.leaves), failing=got.failing(universe))
        if row != want:
            mismatches.append((variant, row, want))
    print("WALL variants %s: %.1fs" % (lang, time.monotonic() - started))
    assert not mismatches, mismatches
    assert not ctx["guard"].leftover() and not ctx["guard"].leftover_volumes()


# ------------------------------------------------------------------------------- delivery 3, G4: a hung COMPILE step
@pytest.mark.docker
@pytest.mark.skipif(base.DOCKER_SKIP is not None, **SKIP)
def test_g4_a_compile_step_that_hangs_is_a_timeout_with_its_marker_read_back(tmp_path):
    """(a) red on the baseline (a killed compile step: 'tg2 compile: start marker absent', recorded on the baseline with
    java 4 s / cpp 3 s). Rust reference + a `build.rs` that loops: cargo runs it in the COMPILE step. `build.rs` is
    tamper-denied by `grade_item`, so this goes through `tg.grade` (the compile-step mechanism is what is under test)."""
    ctx = prepare(tmp_path, "rust")
    tree = variant_tree(tmp_path, ctx, "buildrs")
    (tree / "build.rs").write_text("fn main() { loop { std::hint::spin_loop(); } }\n")
    started = time.monotonic()
    result = tg.grade("rust", tree, ctx["slug"], tmp_path / "private", prepared=ctx["prepared"], guard=ctx["guard"],
                      timeout=SPIN_TIMEOUT["rust"], keep=tmp_path / "keep", seq=0, boundary=0)
    print("WALL g4 compile-hang: %.1fs" % (time.monotonic() - started))
    assert result.outcome == "timeout" and result.all_failed and result.passing == set()
    steps = [p["step"] for p in result.phases]
    assert steps[-2:] == ["compile", "compile-readback"] and "execute" not in steps, steps
    comp = next(p for p in result.phases if p["step"] == "compile")
    assert comp["timed_out"]
    d = tmp_path / "keep/seq-0000"
    assert re.fullmatch(r"TG2_COMPILE_START [0-9a-f]{16}", (d / "compile.marker").read_text().strip())
    assert (d / "compile.out").is_file()
    assert not ctx["guard"].leftover() and not ctx["guard"].leftover_volumes()
