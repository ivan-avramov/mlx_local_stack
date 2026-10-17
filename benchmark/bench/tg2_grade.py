"""M65 tg2 phase-typed grader for Rust / Java / JavaScript / C++ (spec docs/specs/m65-tg2-corpus.md).

New module: imports tg1 modules, edits none (T14). Each grade is a sequence of `docker run --pull=never --network none
--memory 4g --memory-swap 4g` steps (setup, compile, execute) plus a host-side parse, each with its own exit code,
stdout/stderr and timing retained by sha256. Outcome classes:

* parsed          every collected leaf is classified (failure wins; skipped / missing leaf = failed)
* compile_failure compile phase failed: every leaf failed (model outcome)
* timeout / oom / mem_kill / crash   resource-cap exhaustion or a crash after a successful launch: every leaf failed
* TransportAbort  setup failure, docker/runtime-level failure, unresolvable offline dependency, image digest drift,
                  or a missing / malformed report after a clean execute phase (infrastructure; never graded)
"""

from __future__ import annotations
from dataclasses import dataclass, field
import fnmatch
import json
import os
from pathlib import Path
import posixpath
import re
import secrets
import shutil
import subprocess
import tarfile
import tempfile
import time
import io
import uuid
import xml.etree.ElementTree as ET
from .structured_grade import _sha256, _write_index, manifest, protected_manifest, write_receipt
from .token_turn_gate import TransportAbort

VERSION = "m65-tg2-v1"
IMAGE_TAG = "tg2-grader:m65-v1"
REPO = Path(__file__).resolve().parents[2]
IMAGE_ID_FILE = REPO / "benchmark/m65/tg2_image/IMAGE_ID"
LANGS = ("rust", "java", "javascript", "cpp")
TIMEOUT_FLOOR = 180
JEST = "/opt/tg2/js/node_modules/.bin/jest"
BABEL = "/opt/tg2/js/node_modules/@babel/core"
SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
MARKER = "TG2_RUNNER_START"
COLLECT_MARKER = "TG2_COLLECT_START"
OWNER_LABEL = "mlxbench.tg2=1"
OWNER_FILTER = "label=" + OWNER_LABEL
CREATED_LABEL = "mlxbench.tg2.created"
NONCE_LABEL = "mlxbench.tg2.nonce"
REGISTRY_DIR = ".tg2-registry"
COMPILE_MARKER = "TG2_COMPILE_START"
# Agent-created build outputs: top-level dirs absent from the prepared tree are stripped before tamper and grading.
STRIP_TOP_LEVEL = ("build", "target", "node_modules", ".gradle")
# Resource bounds (G15): process count, open files, single-file size, captured output and report size.
PIDS_LIMIT = 512
NOFILE_LIMIT = 4096
FSIZE_LIMIT = 1 << 30
OUTPUT_CAP = 16_000_000
REPORT_CAP = 32_000_000
MAX_JUNIT_FILES = 2000
# G19: the host tree is only a read-only stage source; build outputs and reports live on per-grade size-limited tmpfs
# volumes (quota-bounded, memory-backed in the container VM, never host disk).
TREE_CAP = 1_500_000_000
WORK_VOLUME_SIZE = "2g"
REPORT_VOLUME_SIZE = "64m"
# JS `test.skip` leaves are Exercism's optional expensive tests: frozen exclusions from scoring (listed by id).
OPTIONAL_LEAVES = {
    ("javascript", "palindrome-products"): frozenset(
        {"palindrome-products.spec.js::Palindromes largest palindrome from four digit factors"}),
    ("javascript", "robot-name"): frozenset({"robot-name.spec.js::Robot all the names can be generated"}),
}


class ReportError(ValueError):
    """A report that cannot be parsed into leaves."""


# ----------------------------------------------------------------------------------------------------- parsers
def merge_leaves(*parts):
    """Union of {leaf id: passed}; failure wins across duplicate events."""
    merged = {}
    for part in parts:
        for key, ok in part.items():
            merged[key] = merged.get(key, True) and bool(ok)
    return merged


_RUNNING = re.compile(r"^\s+Running (.+?)(?: \(.*\))?\s*$")
_DOCTEST = re.compile(r"^\s+Doc-tests (.+?)\s*$")
_RUST_TEST = re.compile(r"^test (.+) \.\.\. (ok|FAILED|ignored(?:, .*)?|bench: .*)$")
_FAILURE_OUTPUT = re.compile(r"^---- .+ (?:stdout|stderr) ----$")


def parse_rust(text):
    """libtest text -> {`<test binary>::<path::name>`: passed}. `Running <label>` headers qualify the leaf so that
    equal names in different binaries never merge; captured failure output (`---- x stdout ----` sections) is not
    scanned for test lines."""
    leaves = {}
    binary = "?"
    in_output = False
    seen = False
    for line in text.splitlines():
        m = _RUNNING.match(line)
        if m:
            binary, in_output = m.group(1), False
            continue
        m = _DOCTEST.match(line)
        if m:
            binary, in_output = "doc-tests " + m.group(1), False
            continue
        if _FAILURE_OUTPUT.match(line):
            in_output = True
            continue
        if line.startswith(("failures:", "test result:")):
            in_output = False
            continue
        m = _RUST_TEST.match(line)
        if m and not in_output:
            seen = True
            key = binary + "::" + m.group(1)
            leaves[key] = leaves.get(key, True) and m.group(2) == "ok"
    if not seen:
        raise ReportError("no libtest result lines")
    return leaves


def parse_junit(text):
    """JUnit XML (Gradle, Catch2) -> {`<classname>#<name>`: passed}; failure / error / skipped = not passed."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ReportError("unparseable JUnit XML: %s" % exc) from None
    leaves = {}
    cases = list(root.iter("testcase"))
    if not cases:
        raise ReportError("JUnit XML has no test cases")
    for case in cases:
        key = "%s#%s" % (case.get("classname", ""), case.get("name", ""))
        ok = not any(case.find(tag) is not None for tag in ("failure", "error", "skipped"))
        leaves[key] = leaves.get(key, True) and ok
    return leaves


def parse_jest(text, root):
    """jest `--json` -> {`<test file relative to root>::<fullName>`: passed}. The complete schema is validated (every
    shape error is a ReportError); a suite whose status is not `passed`, or a run whose `success` is false, always
    yields a counted failure even when every assertion passed (afterAll / environment errors)."""
    try:
        doc = json.loads(text)
    except ValueError as exc:
        raise ReportError("unparseable jest JSON: %s" % exc) from None
    if not isinstance(doc, dict) or not isinstance(doc.get("success"), bool):
        raise ReportError("jest JSON lacks a boolean success")
    results = doc.get("testResults")
    if not isinstance(results, list) or not results:
        raise ReportError("jest JSON has no testResults")
    prefix = root.rstrip("/") + "/"
    leaves = {}
    for suite in results:
        if (not isinstance(suite, dict) or not isinstance(suite.get("name"), str)
                or not isinstance(suite.get("status"), str)):
            raise ReportError("jest suite without a string name and status")
        assertions = suite.get("assertionResults")
        if not isinstance(assertions, list):
            raise ReportError("jest suite assertionResults is not a list")
        name = suite["name"]
        rel = name[len(prefix):] if name.startswith(prefix) else name
        all_passed = True
        for a in assertions:
            if (not isinstance(a, dict) or not isinstance(a.get("fullName"), str)
                    or not isinstance(a.get("status"), str)):
                raise ReportError("jest assertion without a string fullName and status")
            key = rel + "::" + a["fullName"]
            ok = a["status"] == "passed"
            all_passed = all_passed and ok
            leaves[key] = leaves.get(key, True) and ok
        if not assertions:
            leaves[rel + "::<suite failed to run>"] = False
        elif suite["status"] != "passed" and all_passed:
            leaves[rel + "::<suite failed>"] = False
    if not doc["success"] and all(leaves.values()):
        leaves["<run failed>"] = False
    return leaves


# ---------------------------------------------------------------------------------------------- docker plumbing
class LocalDocker:
    """Guard-less fallback with the guard API the grader needs (production passes the proc_guard instance)."""

    grader_mem_kill = False

    def __init__(self, prefix="mlxbench-tg2"):
        self.prefix = prefix

    def container_name(self):
        return "%s-%s" % (self.prefix, uuid.uuid4().hex[:12])

    def register_container(self, name):
        pass

    def run_grader(self, cmd, *, timeout=None, **kwargs):
        return subprocess.run(cmd, timeout=timeout, **kwargs)

    def remove_container(self, name):
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, text=True, timeout=30)
        out = subprocess.run(["docker", "ps", "-a", "--filter", "name=^/" + name + "$", "--format", "{{.Names}}"],
                             capture_output=True, text=True, timeout=15)
        if out.returncode or out.stdout.strip():
            raise TransportAbort("container cleanup uncertain")

    def leftover(self):
        out = subprocess.run(["docker", "ps", "-a", "--filter", "name=^/" + self.prefix, "--format", "{{.Names}}"],
                             capture_output=True, text=True, timeout=15)
        return out.stdout.split()

    def leftover_holders(self):
        out = subprocess.run(["docker", "ps", "-a", "--filter", OWNER_FILTER, "--format", "{{.Names}}"],
                             capture_output=True, text=True, timeout=15)
        return out.stdout.split()

    def leftover_volumes(self):
        out = subprocess.run(["docker", "volume", "ls", "-q", "--filter", OWNER_FILTER], capture_output=True,
                             text=True, timeout=15)
        return out.stdout.split()


class _NullOps:
    """Used when a caller injects `run` without a guard (fixtures): no docker bookkeeping."""

    grader_mem_kill = False

    def container_name(self):
        return "fixture-tg2-" + uuid.uuid4().hex[:12]

    def register_container(self, name):
        pass

    def remove_container(self, name):
        pass


def pinned_image_id():
    """The image id pinned by `benchmark/m65/tg2_image/build.sh`: first line of IMAGE_ID (later lines are metadata)."""
    try:
        value = IMAGE_ID_FILE.read_text().splitlines()[0].strip()
    except (OSError, IndexError) as exc:
        raise TransportAbort("tg2 image id pin missing: %s" % exc) from exc
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise TransportAbort("tg2 image id pin malformed")
    return value


def _mount(kind, src, dst, *, readonly=False):
    if "," in str(src) or '"' in str(src):
        raise TransportAbort("unsafe mount source path")
    return "type=%s,src=%s,dst=%s%s" % (kind, src, dst, ",readonly" if readonly else "")


def _docker_run(name, image_id, slug, mounts, inner, *, extra=(), nonce=None):
    cmd = [
        "docker", "run", *extra, "--name", name, "--pull=never", "--network", "none",
        "--memory", "4g", "--memory-swap", "4g",
        "--pids-limit", str(PIDS_LIMIT),
        "--ulimit", "nofile=%d:%d" % (NOFILE_LIMIT, NOFILE_LIMIT), "--ulimit", "fsize=%d:%d" % (FSIZE_LIMIT, FSIZE_LIMIT),
    ]
    for spec in mounts:
        cmd += ["--mount", spec]
    if nonce and "--label" not in extra:
        cmd += ["--label", OWNER_LABEL, "--label", "%s=%s" % (NONCE_LABEL, nonce)]
    return cmd + ["-w", "/work/" + slug, image_id, *inner]


def refuse_tmp_source(path):
    """P361: OrbStack bind mounts whose source is under $TMPDIR (/var/folders/...) serve stale file sizes after an
    in-place host overwrite; refuse any such mount source (resolved path)."""
    path = Path(path).resolve()
    roots = [Path("/var/folders"), Path("/private/var/folders"), Path(tempfile.gettempdir()).resolve()]
    if os.environ.get("TMPDIR"):
        roots.append(Path(os.environ["TMPDIR"]).resolve())
    for root in roots:
        if path == root or root in path.parents:
            raise TransportAbort("mount source %s is under TMPDIR/var/folders (stale bind-mount attributes, P361)" % path)


def _bounded(script):
    """stdout+stderr of a phase through a size cap; the phase's own exit status is preserved."""
    return '{ %s; } 2>&1 | head -c %d; exit ${PIPESTATUS[0]}' % (script, OUTPUT_CAP)


def _raw_commands(lang, slug):
    if lang == "rust":
        return ("cargo test --frozen --offline --no-run 2>&1",
                "cargo test --frozen --offline --no-fail-fast -- --include-ignored 2>&1")
    if lang == "java":
        return ("bash ./gradlew --offline --no-daemon compileTestJava",
                "bash ./gradlew --offline --no-daemon --rerun-tasks test")
    if lang == "javascript":
        transform = ("const b=require('%s');for(const f of require('fs').readFileSync('/report/tests.list','utf8')"
                     ".split('\\n').filter(Boolean)){b.transformFileSync(f)}" % BABEL)
        return ("%s --ci --listTests > /report/tests.list && node -e \"%s\"" % (JEST, transform),
                "%s --ci --json --outputFile=/report/jest.json" % JEST)
    return ("cmake -S . -B build -DEXERCISM_RUN_ALL_TESTS=ON && cmake --build build --target %s" % slug,
            "./build/%s -r junit -o /report/cpp.xml" % slug)


def _commands(lang, slug, nonce="0"):
    """(compile script, execute script) per the spec's grader table, each printing its own per-grade nonce marker
    immediately before invoking the compiler / test runner, with output bounded."""
    compile_script, execute_script = _raw_commands(lang, slug)
    return (_bounded('echo "%s %s"; %s' % (COMPILE_MARKER, nonce, compile_script)),
            _bounded('echo "%s %s"; %s' % (MARKER, nonce, execute_script)))


STAGE_SCRIPT = "# TG2_STAGE\nset -e\ncp -a /src/. .\n"


def _collect_script(lang, slug, nonce):
    """tar of the report files, bounded; the start marker goes to stderr so stdout is the pure tar stream."""
    if lang == "java":
        src = "-C /work/%s/build/test-results --exclude=test/binary test" % slug
    else:
        src = "-C /report %s" % ("jest.json" if lang == "javascript" else "cpp.xml")
    return 'echo "%s %s" >&2; tar -cf - %s 2>/dev/null | head -c %d; exit ${PIPESTATUS[0]}' % (
        COLLECT_MARKER, nonce, src, REPORT_CAP + 1)


def parse_collect(lang, data):
    """Report files from the collect step's tar stream: {member name: bytes}. Only plain regular files with the
    expected names are accepted; symlinks, FIFOs, devices, odd paths and over-cap archives are ReportErrors (no
    model-created path is ever opened on the host)."""
    if not data:
        raise ReportError("no report data collected")
    if len(data) > REPORT_CAP:
        raise ReportError("report archive exceeds the %d byte cap" % REPORT_CAP)
    try:
        tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:")
        members = tf.getmembers()
    except tarfile.TarError as exc:
        raise ReportError("unreadable report archive: %s" % exc) from None
    out, total, seen = {}, 0, set()
    want = {"javascript": "jest.json", "cpp": "cpp.xml"}.get(lang)
    for m in members:
        name = m.name.rstrip("/")
        parts = name.split("/")
        if name.startswith("/") or ".." in parts or "" in parts:
            raise ReportError("unsafe report member path %r" % m.name)
        if name in seen:
            raise ReportError("duplicate report member %r" % m.name)
        seen.add(name)
        if lang == "java":
            if parts == ["test"]:
                if not m.isdir():
                    raise ReportError("report member 'test' is not a directory")
                continue
            if len(parts) != 2 or parts[0] != "test":
                raise ReportError("unexpected report member %r" % m.name)
            if not m.isreg():
                raise ReportError("non-regular report member %r" % m.name)
            if not parts[1].endswith(".xml"):
                continue
            key = parts[1]
        else:
            if parts != [want] or not m.isreg():
                raise ReportError("unexpected or non-regular report member %r" % m.name)
            key = want
        total += m.size
        if total > REPORT_CAP or len(out) >= MAX_JUNIT_FILES:
            raise ReportError("cumulative report size / count exceeds the cap")
        body = tf.extractfile(m).read(m.size)
        if len(body) != m.size:
            raise ReportError("extracted size differs from the declared size for %r" % m.name)
        out[key] = body
    if not out:
        raise ReportError("no report files in the archive")
    return out


_PREFLIGHT_PY_RUST = """
import os, re, sys
vendor = "/opt/tg2/cargo-vendor"
locks = [os.path.join(d, f) for d, ds, fs in os.walk(".") if "target" not in d.split(os.sep) for f in fs if f == "Cargo.lock"]
if not locks:
    sys.exit("no Cargo.lock in the tree")
for lock in locks:
    for block in open(lock).read().split("[[package]]")[1:]:
        name = re.search(r'^name = "([^"]+)"', block, re.M).group(1)
        version = re.search(r'^version = "([^"]+)"', block, re.M).group(1)
        if 'source = "registry' in block and not (os.path.isdir(os.path.join(vendor, name)) or os.path.isdir(os.path.join(vendor, name + "-" + version))):
            sys.exit("crate %s %s missing from the image vendor dir" % (name, version))
"""
_PREFLIGHT_PY_JAVA = """
import os, re, sys
ro = os.environ["GRADLE_RO_DEP_CACHE"] + "/modules-2/files-2.1"
coords = re.findall(r'["\\'"]([\\w.-]+):([\\w.-]+)(?::([\\w.-]+))?["\\'"]', open("build.gradle").read())
if not coords:
    sys.exit("no dependency coordinates in build.gradle")
for group, artifact, version in coords:
    path = os.path.join(ro, group, artifact, version) if version else os.path.join(ro, group, artifact)
    if not os.path.isdir(path):
        sys.exit("dependency %s:%s:%s missing from GRADLE_RO_DEP_CACHE" % (group, artifact, version))
"""


def _preflight(lang):
    """Fixed per-language preflight, run before the compile marker: runner executables and the dependency closure
    exist inside the image. Any failure is infrastructure; afterwards compile / execute failures are the model's."""
    head = "# TG2_PREFLIGHT\nset -e\n"
    if lang == "rust":
        return (head + "command -v cargo rustc >/dev/null\ngrep -q cargo-vendor /root/.cargo/config.toml\n"
                "python3 - <<'PY'\n" + _PREFLIGHT_PY_RUST + "PY\n")
    if lang == "java":
        return (head + "command -v java javac >/dev/null\nls /root/.gradle/wrapper/dists/gradle-8.7-bin/*/gradle-8.7/bin/gradle"
                " >/dev/null\ntest -d \"$GRADLE_RO_DEP_CACHE/modules-2/files-2.1\"\n"
                "python3 - <<'PY'\n" + _PREFLIGHT_PY_JAVA + "PY\n")
    if lang == "javascript":
        return (head + "test -x %s\nnode -e \"for (const m of ['@babel/core','babel-jest','@exercism/babel-preset-javascript',"
                "'core-js']) require.resolve(m)\"\n" % JEST)
    return (head + "command -v cmake g++ >/dev/null\ntest -f /usr/include/boost/version.hpp\n"
            "ls /usr/lib/*/libboost_date_time* >/dev/null\n")


# ----------------------------------------------------------------------------------------------------- skip forms
JS_SKIP = re.compile(r"\b(?:xtest|xit|xdescribe)\s*\(")
JAVA_SKIP = re.compile(r"@Disabled\b")
_JS_TEST = re.compile(r"\.(?:spec|test)\.[cm]?js$", re.I)


def strip_build_outputs(work, prepared):
    """Remove top-level build/dependency directories the agent created (absent from the prepared tree, matched
    case-insensitively); returns the stripped names as found. Nested ones (e.g. src/build) are untouched and stay
    subject to the default-deny tamper check."""
    work = Path(work)
    prepared_tops = {p.split("/")[0].casefold() for p in prepared}
    order = {n: i for i, n in enumerate(STRIP_TOP_LEVEL)}
    found = sorted((e for e in os.listdir(work) if e.casefold() in order and e.casefold() not in prepared_tops),
                   key=lambda e: (order[e.casefold()], e))
    for name in found:
        path = work / name
        if path.is_symlink() or path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)
    return found


def skip_form_violations(work, lang):
    """Test files that still contain a skip form the freeze rewrites (`xtest`/`xit`/`xdescribe`, `@Disabled` in both
    forms); the grader refuses such a tree. JS `test.skip` is an optional leaf (OPTIONAL_LEAVES), not a violation."""
    work = Path(work)
    bad = []
    for dirpath, dirs, files in os.walk(work):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "build", "target", ".git")]
        for name in files:
            rel = (Path(dirpath) / name).relative_to(work).as_posix()
            if lang == "javascript" and _JS_TEST.search(name):
                pattern = JS_SKIP
            elif lang == "java" and name.endswith(".java") and rel.startswith("src/test/"):
                pattern = JAVA_SKIP
            else:
                continue
            if pattern.search((Path(dirpath) / name).read_text(errors="replace")):
                bad.append(rel)
    return sorted(bad)


# ------------------------------------------------------------------------------------------------------- tamper
# Every pattern below is matched against the CASE-FOLDED path (APFS is case-insensitive: `Jest.config.js` IS
# `jest.config.js`), so all constants are lowercase.
DENY_ANY_DEPTH = {".cargo", "node_modules", "__mocks__", "catch2", "jest"}
DENY_TOP_LEVEL = {"build", "target", ".gradle", "buildsrc", "boost"}
DENY_NAMES = ("build.rs", "jest.config.*", "babel.config.*", ".babelrc*", "settings.gradle*", "gradle.properties",
              "cmakelists.txt", "*.cmake", "init.gradle*")
RUST_ALWAYS_PROTECTED = ("cargo.toml", "cargo.lock")
JAVA_DENIED_NAMESPACES = ("org.junit", "org.assertj", "org.json", "io.reactivex", "java", "javax", "org.opentest4j",
                          "org.apiguardian", "org.reactivestreams", "jdk", "sun")
_RUST_NEW = re.compile(r"^src/(?:[^/]+/)*[^/]+\.rs$")
_JS_NEW = re.compile(r"^[a-z0-9_][\w.-]*\.js$")


def case_collisions(paths):
    """Pairs of paths that differ only by case (one file on a case-insensitive filesystem)."""
    seen, out = {}, []
    for path in sorted(paths):
        key = path.casefold()
        if key in seen:
            out.append((seen[key], path))
        else:
            seen[key] = path
    return out


def _denied(rel):
    parts = rel.casefold().split("/")
    if parts[0] in DENY_TOP_LEVEL or any(p in DENY_ANY_DEPTH for p in parts[:-1]):
        return "build/dependency/framework directory"
    if any(fnmatch.fnmatchcase(parts[-1], pat) for pat in DENY_NAMES):
        return "build or test configuration file"
    if parts[-1].startswith("catch") and parts[-1].endswith((".hpp", ".h")):
        return "framework header shadow"
    return None


def _denied_namespace(package):
    return next((ns for ns in JAVA_DENIED_NAMESPACES if package == ns or package.startswith(ns + ".")), None)


def _unescape_unicode(text):
    """Java translates \\uXXXX (any number of u's, even run of preceding backslashes) before lexing."""
    out, i, n, backslashes = [], 0, len(text), 0
    while i < n:
        c = text[i]
        if c == "\\" and backslashes % 2 == 0 and text[i + 1:i + 2] == "u":
            j = i + 1
            while j < n and text[j] == "u":
                j += 1
            digits = text[j:j + 4]
            if re.fullmatch(r"[0-9a-fA-F]{4}", digits):
                out.append(chr(int(digits, 16)))
                i, backslashes = j + 4, 0
                continue
        out.append(c)
        backslashes = backslashes + 1 if c == "\\" else 0
        i += 1
    return "".join(out)


_JAVA_TOKEN = re.compile(r"(?:[^\W\d]|\$)(?:\w|\$)*|\d\w*|\S")


def _java_tokens(text):
    """Token list with comments dropped and string / char / text-block literals collapsed to `<lit>`."""
    text = _unescape_unicode(text)
    tokens, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c in "\"'":
            quote = '"""' if text.startswith('"""', i) else c
            i += len(quote)
            while i < n and not text.startswith(quote, i):
                i += 2 if text[i] == "\\" else 1
                if quote != '"""' and i < n and text[i] == "\n":
                    break
            i += len(quote)
            tokens.append("<lit>")
        else:
            m = _JAVA_TOKEN.match(text, i)
            tokens.append(m.group())
            i = m.end()
    return tokens


def _java_decl(text):
    """(declared package or '', top-level type names) of a Java source, lexically (comments / escapes / spacing)."""
    tokens = _java_tokens(text)
    i = 0
    while i < len(tokens) - 1 and tokens[i] == "@" and tokens[i + 1] != "interface":      # package annotations
        i += 2
        while i + 1 < len(tokens) and tokens[i] == "." :
            i += 2
        if i < len(tokens) and tokens[i] == "(":
            depth = 0
            while i < len(tokens):
                depth += tokens[i] == "("
                depth -= tokens[i] == ")"
                i += 1
                if depth == 0:
                    break
    package = ""
    if i < len(tokens) and tokens[i] == "package":
        j = i + 1
        parts = []
        while j < len(tokens) and tokens[j] != ";":
            parts.append(tokens[j])
            j += 1
        package = "".join(parts)
    types, depth = [], 0
    for k, token in enumerate(tokens):
        if token == "{":
            depth += 1
        elif token == "}":
            depth = max(0, depth - 1)
        elif (depth == 0 and token in ("class", "interface", "enum", "record") and k + 1 < len(tokens)
              and re.fullmatch(r"(?:[^\W\d]|\$)(?:\w|\$)*", tokens[k + 1])):
            types.append(tokens[k + 1])
    return package, types


def _java_fqns(work, rel):
    package, types = _java_decl((Path(work) / rel).read_text(errors="replace"))
    stem = posixpath.basename(rel)[:-len(".java")]
    names = {stem, *types}
    return package, {(package + "." if package else "") + n for n in names}


def _new_file_reason(work, rel, lang, solution_dirs, existing_fqns):
    folded = rel.casefold()
    name = posixpath.basename(folded)
    parent = posixpath.dirname(folded)
    if lang == "rust":
        if _RUST_NEW.match(folded) and folded != "src/main.rs" and not folded.startswith("src/bin/"):
            return None
        return "rust: only src/*.rs helper modules may be added"
    if lang == "java":
        if not name.endswith(".java") or name == "module-info.java":
            return "java: only .java helpers under the solution package roots may be added"
        root = next((r for r in solution_dirs if folded.startswith(r.casefold() + "/")), None)
        if root is None:
            return "java: new file outside the solution package roots"
        source_root = "src/main/java/"
        if not folded.startswith(source_root):
            return "java: new file outside src/main/java"
        path_pkg = ".".join(p for p in posixpath.dirname(rel)[len(source_root):].split("/") if p)
        declared, fqns = _java_fqns(work, rel)
        for package in (path_pkg, declared):
            if package and _denied_namespace(package):
                return "java: framework/dependency namespace %s" % _denied_namespace(package)
        if declared != path_pkg:
            return "java: declared package %r disagrees with path %r" % (declared, path_pkg)
        clash = sorted(fqns & existing_fqns)
        if clash:
            return "java: duplicates test-visible class %s" % clash[0]
        existing_fqns |= fqns
        return None
    if lang == "javascript":
        if parent in {d.casefold() for d in solution_dirs} and _JS_NEW.match(name) and not _JS_TEST.search(name):
            return None
        return "javascript: only non-test .js helpers beside the solution may be added"
    if (parent in {d.casefold() for d in solution_dirs} and name.endswith((".h", ".hpp", ".cpp"))
            and not name.endswith("_test.cpp") and not name.startswith("tests-main")):
        return None
    return "cpp: only .h/.cpp helpers beside the solution (named in no CMake test glob) may be added"


def tamper_reasons(work, protected, prepared, lang, *, solutions=()):
    """Reasons the tree must not be graded as the model's work; [] = clean."""
    work = Path(work)
    try:
        current = manifest(work)
    except (OSError, ValueError) as exc:
        return ["unreadable or non-regular (symlink) tree entry: %s" % exc]
    reasons = ["case-colliding paths: %s vs %s" % pair for pair in case_collisions(current)]
    for rel, digest in sorted(protected.items()):
        if current.get(rel) != digest:
            reasons.append("protected file %s: %s" % ("missing" if rel not in current else "modified", rel))
    if lang == "rust":
        for rel in sorted(set(current) | set(prepared)):
            if posixpath.basename(rel).casefold() in RUST_ALWAYS_PROTECTED and current.get(rel) != prepared.get(rel):
                reasons.append("rust: %s is protected (changed or added): %s" % (posixpath.basename(rel), rel))
    solution_dirs = {posixpath.dirname(s) for s in solutions}
    existing = set()
    if lang == "java":
        solution_dirs = {posixpath.dirname(s) for s in solutions if s.endswith(".java")}
        for rel in prepared:
            if rel.endswith(".java") and rel in current:
                existing |= _java_fqns(work, rel)[1]
    for rel in sorted(current.keys() - prepared.keys()):
        why = _denied(rel) or _new_file_reason(work, rel, lang, solution_dirs, existing)
        if why:
            reasons.append("new file %s: %s" % (rel, why))
    return reasons


def tampered(work, protected, prepared, lang, *, solutions=()):
    return bool(tamper_reasons(work, protected, prepared, lang, solutions=solutions))


# --------------------------------------------------------------------------------------------------------- grade
@dataclass
class Tg2Grade:
    lang: str = ""
    outcome: str = "parsed"
    leaves: dict = field(default_factory=dict)
    all_failed: bool = False
    phases: list = field(default_factory=list)
    artifacts: dict = field(default_factory=dict)
    image_id: str = ""
    version: str = VERSION
    reason: str = ""
    reason_detail: str = ""
    stripped: list = field(default_factory=list)
    cleanup_problems: list = field(default_factory=list)
    tamper_reasons: list = field(default_factory=list)
    optional: frozenset = frozenset()

    @property
    def collected(self):
        return set(self.leaves)

    @property
    def passing(self):
        return set() if self.all_failed else {k for k, ok in self.leaves.items() if ok}

    def failing(self, universe):
        """Counted failures: expected leaves that are missing or failed, plus every collected failure outside the
        universe (initialisation / teardown / suite-level events). Only frozen optional ids are excluded."""
        expected = set(universe) - self.optional
        count = len(expected - self.passing)
        if not self.all_failed:
            count += sum(1 for k, ok in self.leaves.items() if not ok and k not in universe and k not in self.optional)
        return count


def _disjoint(work, *others):
    for other in others:
        if other is None:
            continue
        other = Path(other).resolve()
        if other == work or work in other.parents or other in work.parents:
            raise TransportAbort("private/keep paths must be disjoint from the mounted work tree: %s" % other)


def grade_item(lang, work, slug, private, *, prepared, solutions, **kw):
    """The production entry point: strip agent build outputs, tamper-check, then grade. A tampered tree is never
    mounted; it returns outcome `tampered` (every leaf failed) and, with `keep`, writes the typed receipt."""
    work = Path(work).resolve()
    _disjoint(work, private, kw.get("keep"))
    stripped = strip_build_outputs(work, prepared)
    reasons = tamper_reasons(work, protected_manifest(prepared, solutions), prepared, lang, solutions=solutions)
    if reasons:
        result = Tg2Grade(lang=lang, outcome="tampered", all_failed=True, stripped=stripped, tamper_reasons=reasons,
                          reason="tampered", reason_detail="; ".join(reasons)[:2000])
        if kw.get("keep") is not None:
            result.artifacts = write_receipt(kw["keep"], kw["seq"], kw["boundary"], kw.get("final", False), "tampered")
        return result
    result = grade(lang, work, slug, private, prepared=prepared, **kw)
    result.stripped = stripped + result.stripped
    return result


def grade(lang, work, slug, private, *, prepared=None, image_id=None, image_tag=IMAGE_TAG, run=None, guard=None,
          timeout=None, keep=None, seq=None, boundary=None, final=False):
    """Grade one prepared/snapshotted tree in the tg2 image (production callers use `grade_item`, which strips and
    tamper-checks first). `slug` is the exercise directory name (C++ CMake derives its project and sources from it,
    so the tree is mounted at /work/<slug>). With `keep`, raw outputs are written to `<keep>/seq-NNNN/` from launch
    and indexed by sha256 on every exit path."""
    if lang not in LANGS:
        raise TransportAbort("unsupported tg2 grader language: %s" % lang)
    if not SLUG.match(slug):
        raise TransportAbort("unsafe exercise slug")
    work = Path(work).resolve()
    private = Path(private).resolve()
    _disjoint(work, private, keep)
    refuse_tmp_source(work)
    image_id = image_id or pinned_image_id()
    timeout = TIMEOUT_FLOOR if timeout is None else timeout
    ops = guard if guard is not None else (LocalDocker() if run is None else _NullOps())
    if run is None:
        run = ops.run_grader
    directory = None
    if keep is not None:
        keep = Path(keep)
        directory = keep / ("seq-%04d" % seq)
        try:
            directory.mkdir(parents=True)
        except FileExistsError:
            raise TransportAbort("immutable grade report path exists: " + directory.name) from None
    private.mkdir(parents=True, exist_ok=True)
    result = Tg2Grade(lang=lang, image_id=image_id, optional=OPTIONAL_LEAVES.get((lang, slug), frozenset()))
    # `prepared` = the prepared-tree manifest (callers always pass it); without it nothing is stripped.
    result.stripped = strip_build_outputs(work, prepared) if prepared is not None else []

    def index(outcome):
        if directory is None:
            return {}
        names = sorted(p.name for p in directory.iterdir() if p.is_file() and p.name != "index.json"
                       and not p.name.startswith(".index"))
        doc = dict(version=VERSION, lang=lang, slug=slug, image_id=image_id, outcome=outcome, phases=result.phases,
                   reason=result.reason, reason_detail=result.reason_detail, stripped=result.stripped)
        (directory / "phases.json").write_text(json.dumps(doc, indent=1, sort_keys=True))
        names = sorted(set(names) | {"phases.json"})
        return _write_index(keep, directory, seq, boundary, final, outcome, names)

    try:
        with tempfile.TemporaryDirectory(prefix="grade-tg2-", dir=private) as tmp:
            tmp = Path(tmp)
            outputs = directory if directory is not None else tmp / "out"
            outputs.mkdir(exist_ok=True)
            _grade(result, lang, work, slug, run, ops, image_id, image_tag, timeout, outputs, index,
                   private / REGISTRY_DIR)
            return result
    except BaseException:
        # Every escaping exception is an infrastructure outcome; the receipt index exists before it propagates.
        if directory is not None:
            index("infrastructure")
        raise


def _container_oom(run, name, outputs, step):
    """Tri-state OOM inspection: True / False, or TransportAbort when the container state cannot be verified."""
    path = outputs / (step + ".inspect")
    try:
        with path.open("w") as out, (outputs / (step + ".inspect.err")).open("w") as err:
            p = run(["docker", "inspect", "--format", "{{.State.OOMKilled}}", name], stdout=out, stderr=err,
                    text=True, timeout=30, stdin=subprocess.DEVNULL, env={**os.environ})
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise TransportAbort("container state unverifiable (%s): %s" % (step, exc)) from exc
    value = path.read_text(errors="replace").strip()
    if p.returncode != 0 or value not in ("true", "false"):
        raise TransportAbort("container state unverifiable (%s): rc=%s %r" % (step, p.returncode, value[:80]))
    return value == "true"


def _remove_container(run, name, nonce, outputs, tag):
    """Remove a container only when its nonce label proves this grade created it; every rm return code is checked and
    absence is verified. Returns a list of problems (a foreign / unverifiable object is listed, never deleted)."""
    found = _nonce_of(run, "container", name, outputs, tag + "-n")
    if found is None:
        return []
    if found != nonce:
        return ["container %s not provably ours; left in place" % name]
    rc, _ = _plain(run, ["docker", "rm", "-f", name], outputs, tag + "-rm")
    problems = ["container %s: docker rm failed (rc=%s)" % (name, rc)] if rc != 0 else []
    if _exists(run, "container", name, outputs, tag + "-v"):
        problems.append("container %s still present after removal" % name)
    return problems


def _step(result, step, cmd, run, ops, outputs, timeout, work, container=None, nonce=None, outputs_tag=None):
    """One launched step: output to files from launch, timing, hashes, OOM / memory-kill markers. Returns a record."""
    stdout_path, stderr_path = outputs / (step + ".stdout"), outputs / (step + ".stderr")
    if container and _exists(run, "container", container, outputs, step + "-pre"):
        raise TransportAbort("tg2 container name %s already exists; refusing (not touched)" % container)
    if hasattr(ops, "grader_mem_kill"):
        ops.grader_mem_kill = False
    started = time.monotonic()
    timed_out = False
    oom = False
    rc = None
    try:
        try:
            with stdout_path.open("w") as out, stderr_path.open("w") as err:
                p = run(cmd, stdout=out, stderr=err, cwd=work, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                        env={**os.environ})
            rc = p.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
        except OSError as exc:
            raise TransportAbort("missing docker runtime: %s" % exc) from exc
        if container:
            oom = _container_oom(run, container, outputs, step)
    except BaseException as exc:
        flight = exc
        raise
    finally:
        if container:
            problems = _remove_container(run, container, nonce, outputs, step)
            if problems:
                note = "tg2 step %s container cleanup uncertain: %s" % (step, "; ".join(problems))
                if "flight" in locals():
                    flight.add_note(note)
                else:
                    raise TransportAbort(note)
    rec = dict(step=step, rc=rc, seconds=round(time.monotonic() - started, 3), timed_out=timed_out, oom=oom,
               mem_kill=bool(getattr(ops, "grader_mem_kill", False)),
               stdout_sha256=_sha256(stdout_path), stderr_sha256=_sha256(stderr_path),
               stdout=stdout_path, stderr=stderr_path)
    result.phases.append({k: v for k, v in rec.items() if k not in ("stdout", "stderr")})
    return rec


def _text(rec):
    return rec["stdout"].read_text(errors="replace") + rec["stderr"].read_text(errors="replace")


def _marker_seen(rec, tag, nonce, stream="stdout"):
    return ("%s %s" % (tag, nonce)) in rec[stream].read_text(errors="replace").splitlines()


def _resource(rec, cap="default"):
    cap = OUTPUT_CAP if cap == "default" else cap
    for key, outcome in (("timed_out", "timeout"), ("oom", "oom"), ("mem_kill", "mem_kill")):
        if rec[key]:
            return outcome
    if cap is not None and rec["stdout"].stat().st_size >= cap:
        return "output_cap"
    return None


def _tree_bytes(work):
    total = 0
    for dirpath, dirs, files in os.walk(work):
        for name in files:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                pass
    return total


def _plain(run, cmd, outputs, tag, timeout=60):
    """A docker bookkeeping command (volume create/rm/ls, detached holder): (rc, stdout text)."""
    path = outputs / (tag + ".out")
    try:
        with path.open("w") as out, (outputs / (tag + ".err")).open("w") as err:
            p = run(cmd, stdout=out, stderr=err, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                    env={**os.environ})
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise TransportAbort("docker command failed (%s): %s" % (tag, exc)) from exc
    return p.returncode, path.read_text(errors="replace").strip()


def _exists(run, kind, name, outputs, tag):
    """Whether an object exists; a failed listing is uncertainty, never absence."""
    if kind == "volume":
        cmd = ["docker", "volume", "ls", "-q", "--filter", "name=^%s$" % name]
    else:
        cmd = ["docker", "ps", "-a", "--filter", "name=^/%s$" % name, "--format", "{{.Names}}"]
    rc, text = _plain(run, cmd, outputs, tag)
    if rc != 0:
        raise TransportAbort("tg2 cannot verify whether %s %s exists (docker listing rc=%s)" % (kind, name, rc))
    return name in text.split()


def _nonce_of(run, kind, name, outputs, tag):
    """The ownership nonce label of an existing object ('' when unlabelled), or None when it does not exist."""
    if kind == "volume":
        cmd = ["docker", "volume", "inspect", "--format", '{{index .Labels "%s"}}' % NONCE_LABEL, name]
    else:
        cmd = ["docker", "inspect", "--format", '{{index .Config.Labels "%s"}}' % NONCE_LABEL, name]
    rc, text = _plain(run, cmd, outputs, tag)
    if rc == 0:
        return text
    if _exists(run, kind, name, outputs, tag + "-x"):
        raise TransportAbort("tg2 cannot inspect %s %s (rc=%s)" % (kind, name, rc))
    return None


def _grade(result, lang, work, slug, run, ops, image_id, image_tag, timeout, outputs, index, registry=None):
    # Refuse first: any labelled leftover from an earlier grade blocks everything else (no automatic deletion).
    leftovers = list_leftovers(run, registry.parent if registry is not None else outputs)
    if leftovers["containers"] or leftovers["volumes"]:
        raise TransportAbort("tg2 leftover storage from an earlier grade must be removed first (no automatic deletion): "
                             "containers %s, volumes %s; remove with `python benchmark/m65/tg2_cleanup.py --remove "
                             "<private>/.tg2-registry/<file>.json`" % (leftovers["containers"], leftovers["volumes"]))
    for violation in skip_form_violations(work, lang):
        raise TransportAbort("tree contains a rewritten skip form (refused): " + violation)
    if _tree_bytes(work) > TREE_CAP:
        result.reason_detail = "input tree exceeds the %d byte cap" % TREE_CAP
        return _all_failed(result, "storage_cap", index)
    inspect = _step(result, "setup-image", ["docker", "image", "inspect", "--format", "{{.Id}}", image_tag], run, ops,
                    outputs, 60, work)
    seen = _text(inspect).strip()
    if inspect["rc"] != 0 or seen != image_id:
        raise TransportAbort("tg2 image %s does not match the pinned id (found %r)" % (image_tag, seen[:80]))
    nonce = secrets.token_hex(16)                       # 128-bit per-grade ownership proof
    base = "mlxbench-tg2-" + uuid.uuid4().hex[:12]
    vol_work, vol_report = base + "-w", base + "-r"
    holder = ops.container_name()
    entry = _registry_write(registry, base, [vol_work, vol_report], holder, nonce)      # exclusive; before anything else
    for kind, name in (("volume", vol_work), ("volume", vol_report), ("container", holder)):
        if _exists(run, kind, name, outputs, "plan-" + name):
            if entry is not None:
                entry.unlink(missing_ok=True)
            raise TransportAbort("tg2 planned %s name %s already exists; refusing (not touched)" % (kind, name))
    label = ["--label", OWNER_LABEL, "--label", "%s=%d" % (CREATED_LABEL, int(time.time())),
             "--label", "%s=%s" % (NONCE_LABEL, nonce)]
    failure = None
    owned_volumes, owns_holder, unverified = [], False, []
    try:
        for name, size in ((vol_work, WORK_VOLUME_SIZE), (vol_report, REPORT_VOLUME_SIZE)):
            rc, text = _plain(run, ["docker", "volume", "create", "--driver", "local", "--opt", "type=tmpfs", "--opt",
                                    "device=tmpfs", "--opt", "o=size=%s,mode=1777" % size, *label, name], outputs,
                              "volume-" + name)
            if rc != 0:
                raise TransportAbort("tg2 volume create failed: %s" % text[-200:])
            if _nonce_of(run, "volume", name, outputs, "own-" + name) != nonce:
                unverified.append(name)
                raise TransportAbort("tg2 volume %s is not provably ours (nonce label mismatch); left in place" % name)
            owned_volumes.append(name)
        vols = [_mount("volume", vol_work, "/work/" + slug), _mount("volume", vol_report, "/report")]
        # A tmpfs volume only keeps its contents while some container has it mounted: a tiny holder keeps both alive;
        # it self-expires (bounded by the step timeouts) if the grader dies before cleaning up.
        # (not registered with the ProcessGuard: its cleanup removes registered names unconditionally)
        rc, text = _plain(run, _docker_run(holder, image_id, slug, vols, ["sleep", str(5 * timeout + 300)],
                                           extra=("-d", *label)), outputs, "holder")
        if rc != 0:
            raise TransportAbort("tg2 volume holder failed to start: %s" % text[-200:])
        if _nonce_of(run, "container", holder, outputs, "own-holder") != nonce:
            unverified.append(holder)
            raise TransportAbort("tg2 holder %s is not provably ours (nonce label mismatch); left in place" % holder)
        owns_holder = True
        return _grade_steps(result, lang, work, slug, run, ops, image_id, timeout, outputs, index, vols, nonce)
    except BaseException as exc:
        failure = exc
        raise
    finally:
        problems = _cleanup(run, ops, outputs, holder if owns_holder else None, owned_volumes, nonce)
        problems += ["%s not provably ours; left in place" % n for n in unverified]
        result.cleanup_problems = problems
        if problems:
            note = "tg2 cleanup uncertain: " + "; ".join(problems)
            if failure is None:
                raise TransportAbort(note)
            failure.add_note(note)
        elif entry is not None:
            entry.unlink(missing_ok=True)


def _cleanup(run, ops, outputs, holder, volumes, nonce):
    """Remove the holder and every volume THIS grade provably created (nonce label re-verified immediately before each
    removal), continuing past each failure and verifying absence. Returns the problems."""
    problems = []
    if holder is not None:
        try:
            if nonce is not None:
                problems += _remove_container(run, holder, nonce, outputs, "cl-holder")
        except Exception as exc:  # noqa: BLE001 -- cleanup must reach the volumes whatever happened to the holder
            problems.append("holder %s: %s" % (holder, exc))
    for name in volumes:
        try:
            found = _nonce_of(run, "volume", name, outputs, "cl-" + name)
            if found is None:
                continue
            if found != nonce:
                problems.append("volume %s not provably ours; left in place" % name)
                continue
            rc, _ = _plain(run, ["docker", "volume", "rm", "-f", name], outputs, "rm-" + name)
            if rc != 0:
                problems.append("volume %s rm rc=%s" % (name, rc))
            if _exists(run, "volume", name, outputs, "ls-" + name):
                problems.append("volume %s still present" % name)
        except Exception as exc:  # noqa: BLE001
            problems.append("volume %s: %s" % (name, exc))
    return problems


def _registry_write(registry, base, volumes, holder, nonce):
    if registry is None:
        return None
    registry.mkdir(parents=True, exist_ok=True)
    path = registry / (base + ".json")
    body = json.dumps(dict(base=base, volumes=volumes, holder=holder, nonce=nonce, created=int(time.time())))
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise TransportAbort("tg2 registry file %s already exists; refusing (not touched)" % path.name) from None
    with os.fdopen(fd, "w") as fh:
        fh.write(body)
    return path


def list_leftovers(run, private):
    """List (never delete) tg2-labelled containers and volumes: {'containers': [...], 'volumes': [...]}."""
    outputs = Path(private) / ".tg2-list"
    outputs.mkdir(parents=True, exist_ok=True)
    rc, text = _plain(run, ["docker", "ps", "-a", "--filter", OWNER_FILTER, "--format", "{{.Names}}"], outputs, "ls-ps")
    if rc != 0:
        raise TransportAbort("tg2 leftover check: cannot list containers")
    rc2, vtext = _plain(run, ["docker", "volume", "ls", "-q", "--filter", OWNER_FILTER], outputs, "ls-vol")
    if rc2 != 0:
        raise TransportAbort("tg2 leftover check: cannot list volumes")
    return dict(containers=sorted(l.split()[0] for l in text.splitlines() if l.strip()),
                volumes=sorted(l.split()[0] for l in vtext.splitlines() if l.strip()))


_REGISTERED_BASE = re.compile(r"^mlxbench-tg2-[0-9a-f]{12}$")
_REGISTERED_HOLDER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_NONCE = re.compile(r"^[0-9a-f]{32}$")


def remove_registered(run, registry_file, private):
    """Explicit recovery: remove exactly the volumes and holder recorded in one grade registry file that lives in
    `<private>/.tg2-registry`, and ONLY objects whose nonce label proves this grade created them. Everything else is
    listed and left in place (TransportAbort); every removal is verified; the registry is retired only when every
    recorded object is verifiably gone."""
    private = Path(private)
    registry_file = Path(registry_file)
    if registry_file.resolve().parent != (private / REGISTRY_DIR).resolve():
        raise TransportAbort("tg2 registry file %s is outside %s; nothing removed" % (registry_file, private / REGISTRY_DIR))
    try:
        doc = json.loads(registry_file.read_text())
        base, volumes, holder, nonce = doc["base"], doc["volumes"], doc["holder"], doc["nonce"]
        ok = (isinstance(base, str) and _REGISTERED_BASE.match(base) and volumes == [base + "-w", base + "-r"]
              and isinstance(holder, str) and _REGISTERED_HOLDER.match(holder)
              and isinstance(nonce, str) and _NONCE.match(nonce))
    except (OSError, ValueError, KeyError, TypeError):
        ok = False
    if not ok:
        raise TransportAbort("tg2 registry file %s is malformed or names foreign objects; nothing removed" % registry_file)
    outputs = private / ".tg2-cleanup"
    outputs.mkdir(parents=True, exist_ok=True)
    removed, foreign, problems = dict(containers=[], volumes=[]), [], []
    objects = [("container", holder)] + [("volume", v) for v in volumes]
    for kind, name in objects:
        if not _exists(run, kind, name, outputs, "cl-find"):
            continue
        if _nonce_of(run, kind, name, outputs, "cl-nonce") != nonce:
            foreign.append(name)
            continue
        cmd = ["docker", "rm", "-f", name] if kind == "container" else ["docker", "volume", "rm", "-f", name]
        rc, _ = _plain(run, cmd, outputs, "cl-rm")
        if rc != 0:
            problems.append("%s %s: removal command failed (rc=%s)" % (kind, name, rc))
        if _exists(run, kind, name, outputs, "cl-verify"):
            problems.append("%s %s still present after removal" % (kind, name))
        else:
            removed["containers" if kind == "container" else "volumes"].append(name)
    if foreign or problems:
        raise TransportAbort("tg2 removal incomplete: not provably ours (left in place, listed): %s; unverified "
                             "removals: %s" % (foreign or "none", problems or "none"))
    registry_file.unlink(missing_ok=True)
    return removed


def _grade_steps(result, lang, work, slug, run, ops, image_id, timeout, outputs, index, vols, gnonce):
    stage_mounts = [_mount("bind", work, "/src", readonly=True), *vols]
    launch = _launch(result, "setup-launch", ["bash", "-c", STAGE_SCRIPT], run, ops, image_id, slug, stage_mounts,
                     outputs, timeout, gnonce)
    if launch["rc"] != 0 or launch["timed_out"]:
        raise TransportAbort("tg2 stage failed (rc=%s timeout=%s): %s" % (launch["rc"], launch["timed_out"],
                                                                         _text(launch)[-300:]))
    pre = _launch(result, "preflight", ["bash", "-c", _preflight(lang)], run, ops, image_id, slug, vols, outputs,
                  timeout, gnonce)
    if pre["rc"] != 0 or pre["timed_out"] or pre["oom"]:
        raise TransportAbort("tg2 preflight failed (rc=%s): %s" % (pre["rc"], _text(pre)[-300:]))
    nonce = secrets.token_hex(8)
    compile_script, execute_script = _commands(lang, slug, nonce)
    # The per-grade nonce marker proves the shell reached the compiler / runner invocation; it is checked BEFORE any
    # timeout / OOM / exit-status classification, and its absence is always infrastructure.
    comp = _launch(result, "compile", ["bash", "-c", compile_script], run, ops, image_id, slug, vols, outputs, timeout, gnonce)
    if not _marker_seen(comp, COMPILE_MARKER, nonce):
        raise TransportAbort("tg2 compile: start marker absent (rc=%s): %s" % (comp["rc"], _text(comp)[-300:]))
    kind = _resource(comp)
    if kind:
        return _all_failed(result, kind, index)
    if comp["rc"] != 0:
        return _all_failed(result, "compile_failure", index)
    exe = _launch(result, "execute", ["bash", "-c", execute_script], run, ops, image_id, slug, vols, outputs, timeout, gnonce)
    if not _marker_seen(exe, MARKER, nonce):
        raise TransportAbort("tg2 execute: runner-start marker absent (rc=%s): %s" % (exe["rc"], _text(exe)[-300:]))
    kind = _resource(exe)
    if kind:
        return _all_failed(result, kind, index)
    try:
        if lang == "rust":
            leaves = parse_rust(_text(exe))
        else:
            col = _launch(result, "collect", ["bash", "-c", _collect_script(lang, slug, nonce)], run, ops, image_id, slug,
                          vols, outputs, timeout, gnonce)
            if not _marker_seen(col, COLLECT_MARKER, nonce, stream="stderr"):
                raise TransportAbort("tg2 collect: start marker absent (rc=%s): %s" % (col["rc"], _text(col)[-300:]))
            kind = _resource(col, cap=None)
            if kind:
                return _all_failed(result, kind, index)
            if col["rc"] != 0:
                raise ReportError("report collection failed (rc=%s)" % col["rc"])
            leaves = _parse_reports(lang, slug, parse_collect(lang, col["stdout"].read_bytes()), outputs)
    except (ReportError, KeyError, TypeError, AttributeError, ValueError) as exc:
        result.reason = "runner_crash_after_start"
        result.reason_detail = str(exc)
        return _all_failed(result, "crash", index)
    result.leaves = leaves
    result.outcome = "parsed"
    result.artifacts = index("parsed")
    return result


def _launch(result, step, inner, run, ops, image_id, slug, mounts, outputs, timeout, nonce):
    name = ops.container_name()
    return _step(result, step, _docker_run(name, image_id, slug, mounts, inner, nonce=nonce), run, ops, outputs,
                 timeout, None, container=name, nonce=nonce)


def _all_failed(result, outcome, index):
    result.outcome, result.all_failed = outcome, True
    result.reason = result.reason or outcome
    result.artifacts = index(outcome)
    return result


def _parse_reports(lang, slug, files, outputs):
    if lang == "java":
        parts = []
        for n, name in enumerate(sorted(files)):
            (outputs / ("junit-%03d.xml" % n)).write_bytes(files[name])
            parts.append(parse_junit(files[name].decode(errors="replace")))
        return merge_leaves(*parts)
    data = files["jest.json" if lang == "javascript" else "cpp.xml"]
    (outputs / ("report.json" if lang == "javascript" else "report.xml")).write_bytes(data)
    if lang == "javascript":
        return parse_jest(data.decode(errors="replace"), "/work/" + slug)
    return parse_junit(data.decode(errors="replace"))


def generate_cargo_locks(work, slug, private, *, image_id=None, run=None, guard=None, timeout=None):
    """Offline `cargo generate-lockfile` for every manifest (incl. nested ones such as macros/tests/invalid) from the
    image's vendored crate cache, in the same network-less container shape as a grade. Returns the lock paths."""
    work = Path(work).resolve()
    private = Path(private).resolve()
    _disjoint(work, private)
    refuse_tmp_source(work)
    private.mkdir(parents=True, exist_ok=True)
    image_id = image_id or pinned_image_id()
    ops = guard if guard is not None else (LocalDocker() if run is None else _NullOps())
    run = run or ops.run_grader
    script = r"find . -name Cargo.toml -not -path '*/target/*' -execdir cargo generate-lockfile --offline \;"
    with tempfile.TemporaryDirectory(prefix="locks-tg2-", dir=private) as tmp:
        tmp = Path(tmp)
        result = Tg2Grade(lang="rust", image_id=image_id)
        rec = _launch(result, "locks", ["bash", "-c", script], run, ops, image_id, slug,
                      [_mount("bind", work, "/work/" + slug)], tmp, TIMEOUT_FLOOR if timeout is None else timeout,
                      secrets.token_hex(16))
        if rec["rc"] != 0 or rec["timed_out"]:
            raise TransportAbort("cargo lock generation failed: %s" % _text(rec)[-300:])
    return sorted(p.relative_to(work).as_posix() for p in work.rglob("Cargo.lock") if "target" not in p.parts)
