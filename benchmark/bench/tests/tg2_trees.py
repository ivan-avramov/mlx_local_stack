"""Test/acceptance helper: build a reference or untouched-stub work tree for one polyglot exercise (minimal stand-in
for the step-2 materializer; applies the spec's skip rewrites so reference runs exercise every test)."""

import json
from pathlib import Path
import re
import shutil

_LANG_DIR = {"rust": "rust", "java": "java", "javascript": "javascript", "cpp": "cpp"}
_JS_SKIP = re.compile(r"\b(xtest|xit|xdescribe)\(")
_JAVA_DISABLED = re.compile(r"@Disabled(?:\([^)]*\))?[ \t]*\n?")


def _prepare(corpus, lang, slug, dest):
    src = Path(corpus) / _LANG_DIR[lang] / "exercises/practice" / slug
    dest = Path(dest)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".docs"))
    config = json.loads((dest / ".meta/config.json").read_text())["files"]
    if lang == "javascript":
        for path in dest.glob("*.spec.js"):
            path.write_text(_JS_SKIP.sub(lambda m: m.group(1)[1:] + "(", path.read_text()))
    if lang == "java":
        for path in (dest / "src/test").rglob("*.java"):
            path.write_text(_JAVA_DISABLED.sub("", path.read_text()))
    return dest, config


def _overlay(dest, lang, config):
    solutions, examples = config["solution"], config["example"]
    if lang == "rust":
        shutil.copy(dest / examples[0], dest / "src/lib.rs")
    elif lang == "javascript":
        shutil.copy(dest / examples[0], dest / solutions[0])
    elif lang == "java":
        base = ".meta/src/reference/java/"
        for example in examples:
            assert example.startswith(base), example
            target = dest / "src/main/java" / example[len(base):]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(dest / example, target)
    else:
        for example in examples:
            suffix = Path(example).suffix
            match = [s for s in solutions if Path(s).suffix == suffix]
            assert len(match) == 1, (example, solutions)
            shutil.copy(dest / example, dest / match[0])


def reference_tree(corpus, lang, slug, dest):
    dest, config = _prepare(corpus, lang, slug, dest)
    _overlay(dest, lang, config)
    shutil.rmtree(dest / ".meta")
    return dest


def stub_tree(corpus, lang, slug, dest):
    dest, _ = _prepare(corpus, lang, slug, dest)
    shutil.rmtree(dest / ".meta")
    return dest
