from __future__ import annotations
import sys
from pathlib import Path

from .source import Source, load_source
from .targets import BENCH_TARGETS, TARGETS


def _render(source: Source) -> list[tuple[str, str, str]]:
    """Run every target's emitter and flatten to a list of (target_name, path, content).

    Covers BENCH_TARGETS as well as client TARGETS: a generated file that nothing regenerates or
    drift-checks is a file that silently goes stale, which is the failure mode `check` exists for.
    """
    rendered: list[tuple[str, str, str]] = []
    for name, emit, paths in [*TARGETS, *BENCH_TARGETS]:
        output = emit(source)
        if isinstance(paths, dict):
            for key, path in paths.items():
                rendered.append((f"{name}:{key}", path, output[key]))
        else:
            rendered.append((name, paths, output))
    return rendered


def _generate(source: Source, root: Path) -> int:
    for _, path, content in _render(source):
        dest = root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
    return 0


def _check(source: Source, root: Path) -> int:
    drifted = []
    for name, path, content in _render(source):
        dest = root / path
        if not dest.exists() or dest.read_text() != content:
            drifted.append((name, path))
    if drifted:
        for name, path in drifted:
            print(f"drift: {name} -> {path}")
        return 1
    return 0


def run(argv: list[str], source: Source | None = None, root: str = ".") -> int:
    root_path = Path(root)
    if not argv:
        print("usage: configgen <generate|check>", file=sys.stderr)
        return 2
    command = argv[0]
    if command not in {"generate", "check"}:
        print(f"unknown command: {command!r}", file=sys.stderr)
        return 2
    if source is None:
        source = load_source(str(root_path / "main_models.yaml"))
    if command == "generate":
        return _generate(source, root_path)
    return _check(source, root_path)


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
