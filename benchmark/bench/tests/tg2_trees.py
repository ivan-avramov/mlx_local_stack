"""Test/acceptance helper: build a reference or untouched-stub work tree for one polyglot exercise (minimal stand-in
for the step-2 materializer; applies the spec's skip rewrites so reference runs exercise every test)."""

import json
from pathlib import Path
import re
import shutil

from bench import structured_grade as sg  # noqa: F401  (re-exported for the acceptance script)

_LANG_DIR = {"rust": "rust", "java": "java", "javascript": "javascript", "cpp": "cpp"}
_JS_SKIP = re.compile(r"\b(xtest|xit|xdescribe)\(")
_JAVA_DISABLED = re.compile(r"@Disabled(?:\([^)]*\))?[ \t]*\n?")


def _config(corpus, lang, slug):
    src = Path(corpus) / _LANG_DIR[lang] / "exercises/practice" / slug
    return src, json.loads((src / ".meta/config.json").read_text())["files"]


def solutions(corpus, lang, slug):
    """Editable implementation paths of the prepared tree (Rust Cargo.toml stays protected)."""
    _, config = _config(corpus, lang, slug)
    # Exercism `editor` files (e.g. Java connect's Winner.java) are student-editable and the reference overwrites them.
    return [s for s in config["solution"] + config.get("editor", []) if s != "Cargo.toml"]


def stub_tree(corpus, lang, slug, dest):
    """The prepared (untouched stub) tree: `.docs`/`.meta` removed, skip forms rewritten."""
    src, _ = _config(corpus, lang, slug)
    dest = Path(dest)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".docs", ".meta"))
    if lang == "javascript":
        for path in dest.glob("*.spec.js"):
            path.write_text(_JS_SKIP.sub(lambda m: m.group(1)[1:] + "(", path.read_text()))
    if lang == "java":
        for path in (dest / "src/test").rglob("*.java"):
            path.write_text(_JAVA_DISABLED.sub("", path.read_text()))
    return dest


def apply_reference(corpus, lang, slug, tree):
    """Overlay the reference solution onto a prepared tree (per-language path mapping)."""
    src, config = _config(corpus, lang, slug)
    solutions_, examples = config["solution"], config["example"]
    tree = Path(tree)
    if lang == "rust":
        shutil.copy(src / examples[0], tree / "src/lib.rs")
    elif lang == "javascript":
        shutil.copy(src / examples[0], tree / solutions_[0])
    elif lang == "java":
        base = ".meta/src/reference/java/"
        for example in examples:
            assert example.startswith(base), example
            target = tree / "src/main/java" / example[len(base):]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src / example, target)
    else:
        for example in examples:
            suffix = Path(example).suffix
            match = [s for s in solutions_ if Path(s).suffix == suffix]
            assert len(match) == 1, (example, solutions_)
            shutil.copy(src / example, tree / match[0])
    return tree


def reference_tree(corpus, lang, slug, dest):
    return apply_reference(corpus, lang, slug, stub_tree(corpus, lang, slug, dest))
