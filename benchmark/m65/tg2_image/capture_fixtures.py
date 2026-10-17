"""Capture real raw grader outputs from the built image as committed test fixtures (G9).

Expected leaf sets are derived INDEPENDENTLY of the parsers, from the exercise test sources (regex / indentation
scans of the corpus files), and stored beside the raw output as expected.json. Run once; the unit tests then parse the
committed raw files and compare."""
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

BENCH = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BENCH))
from bench import structured_grade as sg  # noqa: E402
from bench import tg2_grade as tg  # noqa: E402
from bench.tests import tg2_trees  # noqa: E402

OUT = BENCH / "bench/tests/fixtures/tg2"


def expected_rust(corpus, slug):
    src = (Path(corpus) / "rust/exercises/practice" / slug / "tests" / (slug + ".rs")).read_text()
    names = re.findall(r"#\[test\]\s*(?:#\[ignore[^\]]*\]\s*)*fn (\w+)", src)
    return sorted("tests/%s.rs::%s" % (slug, n) for n in names)


def expected_java(corpus, slug):
    tests = list((Path(corpus) / "java/exercises/practice" / slug / "src/test/java").glob("*.java"))
    out = []
    for path in tests:
        text = path.read_text()
        out += ["%s#%s()" % (path.stem, n) for n in re.findall(r"@Test\s*(?:@Disabled(?:\([^)]*\))?\s*)*(?:public\s+)?void (\w+)\(", text)]
    return sorted(out)


def expected_js(corpus, slug):
    text = (Path(corpus) / "javascript/exercises/practice" / slug / (slug + ".spec.js")).read_text()
    stack, out = [], []
    for line in text.splitlines():
        m = re.match(r"^(\s*)(describe|xdescribe|test|xtest|it|xit)\((['\"])(.*?)\3", line)
        if not m:
            continue
        depth = len(m.group(1)) // 2
        del stack[depth:]
        if m.group(2).endswith("describe"):
            stack.append(m.group(4))
        else:
            out.append("%s.spec.js::%s" % (slug, " ".join(stack + [m.group(4)])))
    return sorted(out)


def expected_cpp(corpus, slug):
    text = (Path(corpus) / "cpp/exercises/practice" / slug / (slug.replace("-", "_") + "_test.cpp")).read_text()
    return sorted("%s.global#%s" % (slug, n) for n in re.findall(r'TEST_CASE\("([^"]+)"', text))


def capture(corpus, lang, slug, name, expected, tweak=None, extra=None):
    guard = tg.LocalDocker()
    tmp = Path(tempfile.mkdtemp(prefix="tg2-fixture-"))
    try:
        stub = tg2_trees.stub_tree(corpus, lang, slug, tmp / "stub")
        if lang == "rust":
            tg.generate_cargo_locks(stub, slug, tmp / "private", guard=guard)
        prepared = sg.manifest(stub)
        ref = tmp / "ref"
        shutil.copytree(stub, ref)
        tg2_trees.apply_reference(corpus, lang, slug, ref)
        if tweak:
            tweak(ref)
        sols = tg2_trees.solutions(corpus, lang, slug)
        result = tg.grade_item(lang, ref, slug, tmp / "private", prepared=prepared, solutions=sols, guard=guard,
                               timeout=900, keep=tmp / "keep", seq=0, boundary=0, final=True)
        raw = tmp / "keep/seq-0000"
        dest = OUT / name
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True)
        source = {"rust": "execute.stdout", "java": "junit-000.xml", "javascript": "report.json",
                  "cpp": "report.xml"}[lang]
        shutil.copy(raw / source, dest / source)
        doc = dict(lang=lang, slug=slug, raw=source, outcome=result.outcome, expected_all_pass=sorted(expected),
                   method="derived from the exercise test sources, independent of the parsers",
                   leaves=dict(sorted(result.leaves.items())))
        doc.update(extra or {})
        (dest / "expected.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
        print(name, result.outcome, len(result.leaves), "expected", len(expected))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(corpus):
    capture(corpus, "rust", "gigasecond", "rust-gigasecond", expected_rust(corpus, "gigasecond"))
    capture(corpus, "java", "affine-cipher", "java-affine-cipher", expected_java(corpus, "affine-cipher"))
    capture(corpus, "javascript", "affine-cipher", "javascript-affine-cipher", expected_js(corpus, "affine-cipher"))
    capture(corpus, "cpp", "gigasecond", "cpp-gigasecond", expected_cpp(corpus, "gigasecond"))

    def teardown(ref):
        body = (ref / "affine-cipher.js").read_text()
        (ref / "affine-cipher.js").write_text("afterAll(() => { throw new Error('teardown boom'); });\n" + body)

    capture(corpus, "javascript", "affine-cipher", "javascript-affine-cipher-suite-failure",
            expected_js(corpus, "affine-cipher"), tweak=teardown,
            extra=dict(extra_failures=["affine-cipher.spec.js::<suite failed>"]))


if __name__ == "__main__":
    main(sys.argv[1])
