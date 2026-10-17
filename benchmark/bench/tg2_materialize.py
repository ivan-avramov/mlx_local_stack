"""M65 tg2 step 2: per-language reference materializer (spec docs/specs/m65-tg2-corpus.md, T4 / T17 / T24 / T27).

Reads each exercise's `.meta/config.json` and builds (a) the prepared stub tree with the freeze-time skip rewrites and
(b) a separate reference overlay by a per-language path mapping (never copy-by-index). An ambiguous or missing
destination is a `FreezeError`. Pure host-side; no docker."""

from __future__ import annotations
from dataclasses import dataclass, field
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tomllib

LANGS = ("rust", "java", "javascript", "cpp")
JAVA_REFERENCE_ROOT = ".meta/src/reference/java/"
_JS_SKIP = re.compile(r"\b(xtest|xit|xdescribe)\(")
_JAVA_DISABLED = re.compile(r"@Disabled(?:\([^)]*\))?[ \t]*\n?")
_DEPRECATED = re.compile(r"(?i)\b(?:this|the) exercise (?:is|has been)\b[^.\n]{0,40}\bdeprecated\b|\binverted exercise\b")
_MENTION = re.compile(r"(?i)\b(?:deprecated|inverted)\b")


class FreezeError(ValueError):
    """An item that cannot be materialized unambiguously (excluded with this reason; never a model outcome)."""


@dataclass
class Plan:
    lang: str
    slug: str
    solutions: list                 # editable implementation paths (solution + editor, Cargo.toml excluded)
    tests: list
    mapping: list                   # [(source rel under the exercise, destination rel in the tree)]
    config: dict = field(default_factory=dict)


@dataclass
class Prepared:
    tree: Path
    rewrites: dict                  # {test file: skip forms rewritten}


_DEP_SECTIONS = ("dependencies", "dev-dependencies", "build-dependencies")


def _toml_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join("%s = %s" % (k, _toml_value(x)) for k, x in v.items()) + " }"
    raise FreezeError("unsupported TOML value %r" % (v,))


def merge_cargo_dependencies(stub_text, example_text):
    """P366: the protected Cargo.toml is the union of the stub's and `.meta/Cargo-example.toml`'s dependencies, so the
    crates the reference needs are declared (and vendored offline) and a model may use exactly those. A crate declared
    differently in both is a conflict (FreezeError)."""
    stub, example = tomllib.loads(stub_text), tomllib.loads(example_text)
    text = stub_text
    for section in _DEP_SECTIONS:
        have, want = stub.get(section, {}), example.get(section, {})
        for name, spec in want.items():
            if name in have and have[name] != spec:
                raise FreezeError("conflicting %s entry %s: stub %r vs example %r" % (section, name, have[name], spec))
        missing = {k: v for k, v in want.items() if k not in have}
        if not missing:
            continue
        lines = "".join("%s = %s\n" % (k, _toml_value(v)) for k, v in missing.items())
        header = re.search(r"^\[%s\][ \t]*\n" % re.escape(section), text, re.M)
        if header:
            text = text[:header.end()] + lines + text[header.end():]
        else:
            text = text.rstrip("\n") + "\n\n[%s]\n%s" % (section, lines)
    merged = tomllib.loads(text)
    for section in _DEP_SECTIONS:
        if merged.get(section, {}) != {**stub.get(section, {}), **example.get(section, {})}:
            raise FreezeError("dependency union did not round-trip for [%s]" % section)
    return text


def exercise_dir(corpus, lang, slug):
    return Path(corpus) / lang / "exercises/practice" / slug


def list_items(corpus):
    return {lang: sorted(p.name for p in (Path(corpus) / lang / "exercises/practice").iterdir() if p.is_dir())
            for lang in LANGS}


def _safe(rel, what):
    p = PurePosixPath(rel)
    if not isinstance(rel, str) or not rel or p.is_absolute() or ".." in p.parts:
        raise FreezeError("unsafe %s path %r" % (what, rel))
    return p.as_posix()


def read_plan(corpus, lang, slug):
    src = exercise_dir(corpus, lang, slug)
    try:
        files = json.loads((src / ".meta/config.json").read_text())["files"]
        solution, editor = list(files["solution"]), list(files.get("editor", []))
        tests, examples = list(files["test"]), list(files["example"])
    except (OSError, ValueError, KeyError) as exc:
        raise FreezeError("unreadable .meta/config.json: %s" % exc) from exc
    if not solution or not tests or not examples:
        raise FreezeError("config needs at least one solution, test and example file")
    for rel in solution + editor + tests + examples:
        _safe(rel, "config")
    solutions = [s for s in solution + editor if s != "Cargo.toml"]
    for rel in solutions + tests:
        if not (src / rel).is_file():
            raise FreezeError("declared file %s is missing from the prepared tree" % rel)
    for rel in examples:
        if not (src / rel).is_file():
            raise FreezeError("example %s is missing" % rel)
    if lang == "rust":
        if len(examples) != 1 or "src/lib.rs" not in solutions:
            raise FreezeError("rust needs exactly one example and src/lib.rs as a solution")
        mapping = [(examples[0], "src/lib.rs")]
    elif lang == "javascript":
        if len(examples) != 1 or len(solutions) != 1:
            raise FreezeError("javascript needs exactly one example and one solution file")
        mapping = [(examples[0], solutions[0])]
    elif lang == "java":
        mapping = []
        roots = {PurePosixPath(s).parent.as_posix() for s in solutions}
        for ex in examples:
            if not ex.startswith(JAVA_REFERENCE_ROOT):
                raise FreezeError("java example %s is outside %s" % (ex, JAVA_REFERENCE_ROOT))
            dest = "src/main/java/" + ex[len(JAVA_REFERENCE_ROOT):]
            inside_roots = any(dest.startswith(r + "/") for r in roots)
            if dest not in solutions and not inside_roots:
                raise FreezeError("java example %s maps to %s, which is neither declared nor under a package root"
                                  % (ex, dest))
            mapping.append((ex, dest))
    elif lang == "cpp":
        mapping = []
        for ex in examples:
            suffix = PurePosixPath(ex).suffix
            matches = [s for s in solutions if PurePosixPath(s).suffix == suffix]
            if len(matches) != 1:
                raise FreezeError("cpp example %s has %d candidate destinations %s" % (ex, len(matches), matches))
            mapping.append((ex, matches[0]))
    else:
        raise FreezeError("unsupported language %s" % lang)
    dests = [d for _, d in mapping]
    if len(set(dests)) != len(dests):
        raise FreezeError("two examples map to one destination")
    return Plan(lang, slug, solutions, tests, mapping, files)


def prepare_tree(corpus, lang, slug, dest):
    """The prepared (untouched stub) tree in a fresh directory: `.docs`/`.meta` removed, skip forms rewritten
    (JS `xtest`/`xit`/`xdescribe`, Java `@Disabled` in both forms); the rewrite counts are recorded."""
    src = exercise_dir(corpus, lang, slug)
    dest = Path(dest)
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".docs", ".meta"))
    rewrites = {}
    if lang == "javascript":
        for path in sorted(dest.glob("*.spec.js")):
            text, n = _JS_SKIP.subn(lambda m: m.group(1)[1:] + "(", path.read_text())
            if n:
                path.write_text(text)
                rewrites[path.relative_to(dest).as_posix()] = n
    if lang == "java" and (dest / "src/test").is_dir():
        for path in sorted((dest / "src/test").rglob("*.java")):
            text, n = _JAVA_DISABLED.subn("", path.read_text())
            if n:
                path.write_text(text)
                rewrites[path.relative_to(dest).as_posix()] = n
    if lang == "rust":
        # P367: the model-facing manifest is the stub's; every Rust item discloses the same single crates line.
        from bench import tg2_grade
        (dest / "OFFLINE_CRATES.md").write_text(tg2_grade.rust_disclosure_line() + "\n")
    return Prepared(dest, rewrites)


def apply_reference(corpus, plan, tree):
    """Overlay the reference solution onto a prepared tree (in a fresh directory, never an in-place edit of a tree a
    container has mounted)."""
    src, tree = exercise_dir(corpus, plan.lang, plan.slug), Path(tree)
    for source, dest in plan.mapping:
        target = (tree / dest).resolve()
        if tree.resolve() not in target.parents:
            raise FreezeError("destination %s escapes the tree" % dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src / source, target)
    example_toml = src / ".meta/Cargo-example.toml"
    if plan.lang == "rust" and example_toml.is_file():
        # freeze-time only (never shown to a model): the reference gets the example's dependencies
        manifest = tree / "Cargo.toml"
        manifest.write_text(merge_cargo_dependencies(manifest.read_text(), example_toml.read_text()))
    return tree


def deprecated_scan(corpus, lang, slug):
    """`deprecated: ...` for an exercise that declares itself deprecated / inverted (C145), `mention: ...` when the
    words only occur in prose, None otherwise."""
    src = exercise_dir(corpus, lang, slug)
    texts = [p for p in (src / ".docs").glob("*.md")] if (src / ".docs").is_dir() else []
    mention = None
    for path in sorted(texts):
        text = path.read_text(errors="replace")
        m = _DEPRECATED.search(text)
        if m:
            return "deprecated: %s (%s)" % (m.group(0), path.name)
        m = _MENTION.search(text)
        mention = mention or ("mention: %s (%s)" % (m.group(0), path.name) if m else None)
    return mention
