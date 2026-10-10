"""M62 fixed reference universes, consistency-checked snapshots and structured grades."""

from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import uuid
import xml.etree.ElementTree as ET
from .token_turn_gate import TransportAbort

VERSION = "m62-structured-v2"
TIMEOUTS = {"python": 300, "go": 180}
REPO = Path(__file__).resolve().parents[2]
EXCLUDED = {".git", "__pycache__", ".pytest_cache"}
PY_FORBIDDEN = {
    "conftest.py",
    "pytest.ini",
    "pyproject.toml",
    "setup.cfg",
    "tox.ini",
    "sitecustomize.py",
    "usercustomize.py",
}


def manifest(root):
    root = Path(root)
    result = {}

    def walk(directory):
        for path in sorted(directory.iterdir()):
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise ValueError("symlink in snapshot")
            if stat.S_ISDIR(mode):
                if path.name not in EXCLUDED:
                    walk(path)
            elif not stat.S_ISREG(mode):
                raise ValueError("non-regular input")
            elif not path.name.endswith(".pyc"):
                result[path.relative_to(root).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()

    walk(root)
    return result


@dataclass
class Snapshot:
    path: Path
    boundary: int
    manifest: dict


@contextmanager
def snapshot(work, private, *, boundary):
    """Never put captures in the model's scratch or TMPDIR."""
    with tempfile.TemporaryDirectory(prefix="snapshot-", dir=private) as tmp:
        dest = Path(tmp) / "tree"
        accepted = None
        for _ in range(3):
            try:
                a = manifest(work)
                shutil.copytree(
                    work,
                    dest,
                    symlinks=True,
                    ignore=shutil.ignore_patterns(*EXCLUDED, "*.pyc"),
                )
                copied = manifest(dest)
                b = manifest(work)
                if a == copied == b:
                    accepted = Snapshot(dest, boundary, a)
                    break
            except (OSError, ValueError):
                pass
            shutil.rmtree(dest, ignore_errors=True)
        yield accepted


def protected_manifest(prepared, solutions):
    return {
        p: h
        for p, h in prepared.items()
        if p not in solutions and not p.startswith(".docs/")
    }


def tampered(work, protected, prepared, lang):
    try:
        current = manifest(work)
    except (OSError, ValueError):
        return True
    if any(current.get(p) != h for p, h in protected.items()):
        return True
    if lang == "go":
        for path in [Path(work) / "vendor"]:
            rel = path.relative_to(work).as_posix() + "/"
            if path.is_dir() and not any(p.startswith(rel) for p in prepared):
                return True
        for rel in current:
            if (
                Path(rel).parent == Path(".")
                and rel.endswith(".go")
                and current[rel] != prepared.get(rel)
                and re.search(
                    r"\bfunc\s+TestMain\s*\(",
                    (Path(work) / rel).read_text(errors="replace"),
                )
            ):
                return True
    for rel in current.keys() - prepared.keys():
        p = Path(rel)
        if lang == "python" and (p.name in PY_FORBIDDEN or p.suffix == ".pth"):
            return True
        if lang == "go" and (
            rel in ("go.mod", "go.work") or p.parts[0] == "vendor"
        ):
            return True
        if (
            lang == "go"
            and p.parent == Path(".")
            and p.suffix == ".go"
            and re.search(
                r"\bfunc\s+TestMain\s*\(", (Path(work) / p).read_text(errors="replace")
            )
        ):
            return True
    return False


@dataclass
class Grade:
    passing: set = field(default_factory=set)
    collected: set = field(default_factory=set)
    returncode: int | None = None
    timed_out: bool = False
    grader_mem_kill: bool = False
    grader_oom: bool = False
    tail: str = ""

    def failing(self, universe):
        return len(set(universe) - self.passing)


def parse_python(xml, rc, test, *, stderr="", timed_out=False):
    result = Grade(returncode=rc, timed_out=timed_out, tail=stderr[-600:])
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        if timed_out or (
            rc == 2 and re.search("collect|SyntaxError|ImportError", stderr, re.I)
        ):
            return result
        raise TransportAbort(
            "unreadable Python report without collection error"
        ) from None
    for case in root.iter("testcase"):
        ident = (
            case.get("file") or test,
            case.get("classname", ""),
            case.get("name", ""),
        )
        result.collected.add(ident)
        if not any(case.find(t) is not None for t in ("failure", "error", "skipped")):
            result.passing.add(ident)
    if not result.collected and not timed_out:
        raise TransportAbort("Python report has no test events")
    return result


GO_PLAIN_FAIL = re.compile(r"^FAIL\t\S+ \[(?:build|setup) failed\]$")


def parse_go(text, rc, *, stderr="", timed_out=False):
    if rc in (125, 126, 127) or re.search(
        r"Cannot connect to the Docker daemon|daemon.*(?:error|not running)|"
        r"Unable to find image|pull access denied|Error response from daemon",
        stderr,
        re.I,
    ):
        raise TransportAbort("Docker infrastructure failure: " + stderr[-300:])
    result = Grade(returncode=rc, timed_out=timed_out, tail=(text + stderr)[-600:])
    for line in text.splitlines():
        # go1.21 prints a build/setup failure as plain text on stdout even under -json.
        if GO_PLAIN_FAIL.match(line):
            continue
        try:
            e = json.loads(line)
        except ValueError:
            raise TransportAbort("malformed Go report") from None
        if e.get("Test") and e.get("Package"):
            key = (e["Package"], e["Test"])
            result.collected.add(key)
            if e.get("Action") == "pass":
                result.passing.add(key)
    leaves = {
        key
        for key in result.collected
        if not any(
            k[0] == key[0] and k[1].startswith(key[1] + "/") for k in result.collected
        )
    }
    result.passing &= leaves
    result.collected = leaves
    if (
        not leaves
        and not timed_out
        and not re.search(r"build failed|setup failed|syntax error|panic:", text + stderr, re.I)
    ):
        raise TransportAbort("Go report has no test events or build error")
    return result


def grade(lang, work, test, private, *, run=None, guard=None, timeout=None):
    work = Path(work).resolve()
    private = Path(private).resolve()
    if lang not in ("python", "go"):
        raise TransportAbort("unsupported structured grader")
    timeout = TIMEOUTS[lang] if timeout is None else timeout
    if run is None:
        run = guard.run_grader if guard else subprocess.run
    name = (
        guard.container_name()
        if guard and hasattr(guard, "container_name")
        else "mlxbench-fixture-grade-" + uuid.uuid4().hex
    )
    with tempfile.TemporaryDirectory(prefix="grade-", dir=private) as tmp:
        report = Path(tmp) / "report.xml"
        if lang == "python":
            cmd = [
                str(REPO / ".venv-bench/bin/python"),
                "-m",
                "pytest",
                str(test),
                "-q",
                "--rootdir=" + str(work),
                "-p",
                "no:cacheprovider",
                "--junitxml=" + str(report),
            ]
        else:
            if guard is None:
                raise TransportAbort("Go grader requires a process/container guard")
            guard.register_container(name)
            cmd = [
                "docker",
                "run",
                "--name",
                name,
                "--memory",
                "4g",
                "--memory-swap",
                "4g",
                "-v",
                str(work) + ":/work",
                "-w",
                "/work",
                "aider-benchmark",
                "go",
                "test",
                "-json",
                "./...",
            ]
        timed_out = False
        oom = False
        full = Path(tmp) / "go.jsonl"
        errors = Path(tmp) / "go.stderr"
        # A fresh grade-specific memory marker; the guard also retains aggregate diagnostics.
        if guard:
            guard.grader_mem_kill = False
        try:
            try:
                kwargs = dict(
                    cwd=work,
                    text=True,
                    timeout=timeout,
                    stdin=subprocess.DEVNULL,
                    env={
                        **os.environ,
                        "TMPDIR": tmp,
                        "PYTHONDONTWRITEBYTECODE": "1",
                        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                    },
                )
                if lang == "go":
                    with full.open("w") as stdout, errors.open("w") as stderr:
                        p = run(cmd, stdout=stdout, stderr=stderr, **kwargs)
                else:
                    p = run(cmd, capture_output=True, **kwargs)
            except subprocess.TimeoutExpired as exc:
                timed_out = True

                def decode(s):
                    return (
                        s.decode(errors="replace") if isinstance(s, bytes) else s or ""
                    )

                p = subprocess.CompletedProcess(
                    cmd, None, decode(exc.stdout), decode(exc.stderr)
                )
            except OSError as exc:
                raise TransportAbort(
                    "missing grader interpreter/runtime: " + str(exc)
                ) from exc
            if lang == "go":
                oom = guard.container_oom(name)
            mem = bool(guard and guard.grader_mem_kill)
            if oom or mem:
                return Grade(
                    returncode=p.returncode, grader_mem_kill=mem, grader_oom=oom
                )
            # Keep full Go JSON through parsing; no tail-based test accounting.
            if lang == "go":
                result = parse_go(
                    full.read_text(),
                    p.returncode,
                    stderr=errors.read_text(),
                    timed_out=timed_out,
                )
            else:
                result = parse_python(
                    report.read_text() if report.exists() else "",
                    p.returncode,
                    str(test),
                    stderr=(p.stdout or "") + (p.stderr or ""),
                    timed_out=timed_out,
                )
            return result
        finally:
            if lang == "go":
                guard.remove_container(name)
