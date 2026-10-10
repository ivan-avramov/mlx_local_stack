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


def has_go_testmain(source):
    """Lex Go declarations, excluding comments, literals and method receivers."""
    tokens = []
    pattern = r'//[^\n]*|/\*[\s\S]*?\*/|`[^`]*`|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[\w]+|[^\s]'
    for match in re.finditer(pattern, source):
        token = match.group()
        if token.startswith(("//", "/*")):
            continue
        tokens.append("<literal>" if token[0] in "\"'`" else token)
    depth = 0
    for i, token in enumerate(tokens):
        if depth == 0 and tokens[i:i + 3] == ["func", "TestMain", "("]:
            return True
        if token == "{":
            depth += 1
        elif token == "}":
            depth = max(0, depth - 1)
    return False


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
                and has_go_testmain((Path(work) / rel).read_text(errors="replace"))
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
    artifacts: dict = field(default_factory=dict)
    outcome: str = "parsed"

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


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write_index(keep, directory, seq, boundary, final, outcome, names):
    """Atomic `index.json` beside the artifacts; returns {name: {path (relative to keep), sha256}}."""
    artifacts = {
        name: {"path": (directory / name).relative_to(keep).as_posix(), "sha256": _sha256(directory / name)}
        for name in names
        if (directory / name).is_file()
    }
    doc = dict(boundary=boundary, seq=seq, final=bool(final), outcome=outcome, artifacts=artifacts)
    tmp = directory / ".index.json.tmp"
    with tmp.open("w") as fp:
        fp.write(json.dumps(doc, indent=1, sort_keys=True))
        fp.flush()
        os.fsync(fp.fileno())
    os.replace(tmp, directory / "index.json")
    return artifacts


def write_receipt(keep, seq, boundary, final, outcome):
    """An index-only report for a boundary where no grader ran (e.g. outcome 'tampered'), so every row has a final
    receipt. Same layout and immutability as a grade."""
    directory = Path(keep) / ("seq-%04d" % seq)
    try:
        directory.mkdir(parents=True)
    except FileExistsError:
        raise TransportAbort("immutable grade report path exists: " + directory.name) from None
    return _write_index(Path(keep), directory, seq, boundary, final, outcome, ())


def grade(lang, work, test, private, *, run=None, guard=None, timeout=None,
          keep=None, seq=None, boundary=None, final=False):
    """Grade one snapshot. With `keep`, the grader's raw output is redirected to files under
    `<keep>/seq-NNNN/` from launch and an `index.json` is written before parsing and on every early return or
    abort (C147 §5)."""
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
    directory = None
    if keep is not None:
        keep = Path(keep)
        directory = keep / ("seq-%04d" % seq)
        try:
            directory.mkdir(parents=True)
        except FileExistsError:
            raise TransportAbort("immutable grade report path exists: " + directory.name) from None
    names = ("report.xml", "stdout.txt", "stderr.txt") if lang == "python" else ("go.jsonl", "go.stderr")
    state = dict(outcome="infrastructure")

    def index(outcome):
        state["outcome"] = outcome
        if directory is None:
            return {}
        return _write_index(keep, directory, seq, boundary, final, outcome, names)

    try:
        with tempfile.TemporaryDirectory(prefix="grade-", dir=private) as tmp:
            result = _grade(lang, work, test, run, guard, timeout, name, Path(tmp), directory, index, boundary)
            return result
    except BaseException:
        # Every escaping exception is an infrastructure outcome; the report index must exist before it propagates.
        if directory is not None:
            index("infrastructure")
        raise


def _grade(lang, work, test, run, guard, timeout, name, tmp, directory, index, boundary):
    outputs = directory if directory is not None else tmp
    report = outputs / "report.xml"
    stdout_path = outputs / ("stdout.txt" if lang == "python" else "go.jsonl")
    stderr_path = outputs / ("stderr.txt" if lang == "python" else "go.stderr")
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
                    "TMPDIR": str(tmp),
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                },
            )
            # Output goes to files from launch (no capture_output): a timeout kill loses nothing.
            with stdout_path.open("w") as stdout, stderr_path.open("w") as stderr:
                p = run(cmd, stdout=stdout, stderr=stderr, **kwargs)
        except subprocess.TimeoutExpired as exc:
            timed_out = True

            def decode(s):
                return s.decode(errors="replace") if isinstance(s, bytes) else s or ""

            p = subprocess.CompletedProcess(cmd, None, decode(exc.stdout), decode(exc.stderr))
        except OSError as exc:
            raise TransportAbort("missing grader interpreter/runtime: " + str(exc)) from exc
        if lang == "go":
            oom = guard.container_oom(name)
        mem = bool(guard and guard.grader_mem_kill)
        if oom or mem:
            artifacts = index("oom" if oom else "mem_kill")
            return Grade(returncode=p.returncode, grader_mem_kill=mem, grader_oom=oom,
                         outcome="oom" if oom else "mem_kill", artifacts=artifacts)
        # Keep full output through parsing; no tail-based test accounting.
        out_text = stdout_path.read_text(errors="replace")
        err_text = stderr_path.read_text(errors="replace")
        if lang == "python":
            provisional = "timeout" if timed_out else "parsed" if report.exists() else "missing_report"
        else:
            provisional = "timeout" if timed_out else "parsed"
        artifacts = index(provisional)
        if lang == "go":
            result = parse_go(out_text, p.returncode, stderr=err_text, timed_out=timed_out)
        else:
            result = parse_python(
                report.read_text() if report.exists() else "",
                p.returncode,
                str(test),
                stderr=(p.stdout or "") + out_text + (p.stderr or "") + err_text,
                timed_out=timed_out,
            )
        outcome = provisional
        if lang == "python" and provisional == "missing_report":
            # parse_python accepted a missing XML only for a collection/import error: a scored failure, typed.
            outcome = "collection_error"
            artifacts = index(outcome)
        result.outcome = outcome
        result.artifacts = artifacts
        return result
    finally:
        if lang == "go":
            guard.remove_container(name)


REPORT_OUTCOMES = ("parsed", "timeout", "oom", "mem_kill", "missing_report", "collection_error", "tampered")
FINAL_OUTCOMES = ("parsed", "timeout", "oom", "mem_kill", "collection_error", "tampered")
# Every grade that RAN carries its launch outputs; a parsed Python grade also carries the junit XML.
REQUIRED_ARTIFACTS = {
    "python": ("stdout.txt", "stderr.txt"),
    "go": ("go.jsonl", "go.stderr"),
}
PARSED_EXTRA_ARTIFACTS = {"python": ("report.xml",), "go": ()}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def validate_reports(reports, lang, test_modified):
    """Schema of a row's `grade_reports` (C147 Q15, shared by inject_verify and chain validate_leg).

    Returns reasons; [] means valid. Every row needs a typed final receipt: exactly one `final`, with a permitted
    outcome (never infrastructure/missing_report); `parsed` receipts carry the language's required artifacts;
    `tampered` (no grader ran) carries none and needs `test_modified`; every other receipt carries the language's
    launch-output artifacts (plus report.xml when a Python grade parsed), each with a path + 64-hex sha256."""
    reasons = []
    if not isinstance(reports, list) or not reports:
        return ["grade_reports absent or empty"]
    seen = set()
    finals = []
    for n, r in enumerate(reports):
        tag = f"report[{n}]"
        if not isinstance(r, dict):
            reasons.append(tag + " is not an object")
            continue
        if not _is_int(r.get("boundary")) or r["boundary"] < 0:
            reasons.append(tag + " boundary must be an int >= 0")
        if not _is_int(r.get("seq")) or r["seq"] < 0:
            reasons.append(tag + " seq must be an int >= 0")
        elif r["seq"] in seen:
            reasons.append(tag + f" duplicate seq {r['seq']}")
        else:
            seen.add(r["seq"])
        if not isinstance(r.get("final"), bool):
            reasons.append(tag + " final must be a bool")
        elif r["final"]:
            finals.append(r)
        outcome = r.get("outcome")
        if outcome not in REPORT_OUTCOMES:
            reasons.append(tag + f" outcome {outcome!r} not permitted")
        artifacts = r.get("artifacts")
        if not isinstance(artifacts, dict):
            reasons.append(tag + " artifacts must be an object")
            continue
        for name, meta in artifacts.items():
            if (not isinstance(meta, dict) or not isinstance(meta.get("path"), str) or not meta["path"]
                    or not isinstance(meta.get("sha256"), str) or not _HEX64.match(meta["sha256"])):
                reasons.append(tag + f" artifact {name!r} needs a path and a 64-hex sha256")
        if outcome == "tampered":
            if artifacts:
                reasons.append(tag + " tampered receipt must have no artifacts")
            if test_modified is not True:
                reasons.append(tag + " tampered receipt requires test_modified")
        else:
            if not artifacts:
                reasons.append(tag + " has no artifacts")
            need = REQUIRED_ARTIFACTS.get(lang, ()) + (PARSED_EXTRA_ARTIFACTS.get(lang, ())
                                                        if outcome == "parsed" else ())
            missing = [a for a in need if a not in artifacts]
            if missing:
                reasons.append(tag + f" {outcome} receipt lacks {missing}")
    if len(finals) != 1:
        reasons.append(f"exactly one final receipt required, found {len(finals)}")
    elif finals[0].get("outcome") not in FINAL_OUTCOMES:
        reasons.append(f"final receipt outcome {finals[0].get('outcome')!r} not permitted")
    return reasons
