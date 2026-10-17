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
import subprocess
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from .structured_grade import _sha256, _write_index, manifest
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
# Exit codes after which a missing report is the instrument's fault, not the model's (spec: "clean execute").
CLEAN_EXIT = {
    "rust": lambda rc: rc in (0, 101),
    "java": lambda rc: rc in (0, 1),
    "javascript": lambda rc: rc in (0, 1),
    "cpp": lambda rc: 0 <= rc < 128,         # Catch2: exit code = number of failed cases; 128+n = signal
}
CRASH = {
    "rust": re.compile(r"didn't exit successfully|\(signal: \d+"),
    "java": re.compile(r"Gradle Test Executor \d+'? finished with non-zero exit value|OutOfMemoryError|StackOverflowError"),
    "javascript": re.compile(r"JavaScript heap out of memory|process\.exit called"),
    "cpp": re.compile(r"Segmentation fault|core dumped|terminate called"),
}
# A dependency that cannot be resolved offline is an image defect (manifests are protected), never a model outcome.
OFFLINE_DEP = re.compile(
    r"attempting to make an HTTP request, but --offline|failed to get `[^`]+` as a dependency|"
    r"no matching package named|Could not resolve [\w.:-]+|No cached version .* available for offline mode|"
    r"Could not GET|Could not HEAD|UnknownHostException|ENOTFOUND|getaddrinfo",
    re.I)
INFRA_RC = (125, 126, 127)                    # docker run failure / command not invocable inside the image


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
    """jest `--json` -> {`<test file relative to root>::<fullName>`: passed}; only status `passed` passes."""
    try:
        doc = json.loads(text)
    except ValueError as exc:
        raise ReportError("unparseable jest JSON: %s" % exc) from None
    results = doc.get("testResults") if isinstance(doc, dict) else None
    if not isinstance(results, list) or not results:
        raise ReportError("jest JSON has no testResults")
    prefix = root.rstrip("/") + "/"
    leaves = {}
    for suite in results:
        if not isinstance(suite, dict) or not isinstance(suite.get("name"), str):
            raise ReportError("jest suite without a name")
        name = suite["name"]
        rel = name[len(prefix):] if name.startswith(prefix) else name
        assertions = suite.get("assertionResults") or []
        if not assertions:
            key = rel + "::<suite failed to run>"
            leaves[key] = False
        for a in assertions:
            key = rel + "::" + str(a.get("fullName"))
            leaves[key] = leaves.get(key, True) and a.get("status") == "passed"
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

    def container_oom(self, name):
        out = subprocess.run(["docker", "inspect", "--format", "{{.State.OOMKilled}}", name], capture_output=True,
                             text=True, timeout=15)
        return out.returncode == 0 and out.stdout.strip() == "true"

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


class _NullOps:
    """Used when a caller injects `run` without a guard (fixtures): no docker bookkeeping."""

    grader_mem_kill = False

    def container_name(self):
        return "fixture-tg2-" + uuid.uuid4().hex[:12]

    def register_container(self, name):
        pass

    def container_oom(self, name):
        return False

    def remove_container(self, name):
        pass


def pinned_image_id():
    """The image id pinned by `benchmark/m65/tg2_image/build.sh` (committed in the policy)."""
    try:
        value = IMAGE_ID_FILE.read_text().strip()
    except OSError as exc:
        raise TransportAbort("tg2 image id pin missing: %s" % exc) from exc
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise TransportAbort("tg2 image id pin malformed")
    return value


def _docker_run(name, image_id, slug, work, report, inner):
    return [
        "docker", "run", "--name", name, "--pull=never", "--network", "none",
        "--memory", "4g", "--memory-swap", "4g",
        "-v", "%s:/work/%s" % (work, slug), "-v", "%s:/report" % report,
        "-w", "/work/" + slug, image_id, *inner,
    ]


def _commands(lang, slug):
    """(compile script, execute script) per the spec's grader table."""
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


# ----------------------------------------------------------------------------------------------------- skip forms
JS_SKIP = re.compile(r"\b(?:xtest|xit|xdescribe)\s*\(|\b(?:test|it|describe)\.skip\b")
JAVA_SKIP = re.compile(r"@Disabled\b")
_JS_TEST = re.compile(r"\.(?:spec|test)\.[cm]?js$")


def skip_form_violations(work, lang):
    """Test files that still contain a skip form the freeze rewrites (`xtest`/`xit`/`xdescribe`, `@Disabled` in both
    forms); the grader refuses such a tree."""
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
DENY_ANY_DEPTH = {".cargo", "node_modules", "__mocks__", "catch2", "jest"}
DENY_TOP_LEVEL = {"build", "target", ".gradle", "buildSrc", "boost"}
DENY_NAMES = ("build.rs", "jest.config.*", "babel.config.*", ".babelrc*", "settings.gradle*", "gradle.properties",
              "CMakeLists.txt", "*.cmake", "init.gradle*")
RUST_ALWAYS_PROTECTED = ("Cargo.toml", "Cargo.lock")
JAVA_DENIED_NAMESPACES = ("org.junit", "org.assertj", "org.json", "io.reactivex", "java", "javax", "org.opentest4j",
                          "org.apiguardian", "org.reactivestreams", "jdk", "sun")
_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)
_RUST_NEW = re.compile(r"^src/(?:[^/]+/)*[^/]+\.rs$")
_JS_NEW = re.compile(r"^[A-Za-z0-9_][\w.-]*\.js$")


def _denied(rel):
    parts = rel.split("/")
    if parts[0] in DENY_TOP_LEVEL or any(p in DENY_ANY_DEPTH for p in parts[:-1]):
        return "build/dependency/framework directory"
    if any(fnmatch.fnmatchcase(parts[-1], pat) for pat in DENY_NAMES):
        return "build or test configuration file"
    if parts[-1].lower().startswith("catch") and parts[-1].lower().endswith((".hpp", ".h")):
        return "framework header shadow"
    return None


def _denied_namespace(package):
    return next((ns for ns in JAVA_DENIED_NAMESPACES if package == ns or package.startswith(ns + ".")), None)


def _java_fqn(work, rel):
    text = (Path(work) / rel).read_text(errors="replace")
    m = _PACKAGE.search(text)
    package = m.group(1) if m else ""
    stem = posixpath.basename(rel)[:-len(".java")]
    return package, (package + "." if package else "") + stem


def _new_file_reason(work, rel, lang, solution_dirs, existing_fqns):
    name = posixpath.basename(rel)
    parent = posixpath.dirname(rel)
    if lang == "rust":
        if _RUST_NEW.match(rel) and rel != "src/main.rs" and not rel.startswith("src/bin/"):
            return None
        return "rust: only src/*.rs helper modules may be added"
    if lang == "java":
        if not name.endswith(".java") or name == "module-info.java":
            return "java: only .java helpers under the solution package roots may be added"
        root = next((r for r in solution_dirs if rel.startswith(r + "/")), None)
        if root is None:
            return "java: new file outside the solution package roots"
        path_pkg = ".".join(posixpath.dirname(rel)[len(root):].strip("/").split("/")).strip(".")
        declared, fqn = _java_fqn(work, rel)
        for package in (path_pkg, declared):
            if package and _denied_namespace(package):
                return "java: framework/dependency namespace %s" % _denied_namespace(package)
        if fqn in existing_fqns:
            return "java: duplicates test-visible class %s" % fqn
        existing_fqns.add(fqn)
        return None
    if lang == "javascript":
        if (parent in solution_dirs and _JS_NEW.match(name) and not _JS_TEST.search(name)):
            return None
        return "javascript: only non-test .js helpers beside the solution may be added"
    if (parent in solution_dirs and name.endswith((".h", ".hpp", ".cpp")) and not name.endswith("_test.cpp")
            and not name.startswith("tests-main")):
        return None
    return "cpp: only .h/.cpp helpers beside the solution (named in no CMake test glob) may be added"


def tamper_reasons(work, protected, prepared, lang, *, solutions=()):
    """Reasons the tree must not be graded as the model's work; [] = clean."""
    work = Path(work)
    try:
        current = manifest(work)
    except (OSError, ValueError) as exc:
        return ["unreadable or non-regular (symlink) tree entry: %s" % exc]
    reasons = []
    for rel, digest in sorted(protected.items()):
        if current.get(rel) != digest:
            reasons.append("protected file %s: %s" % ("missing" if rel not in current else "modified", rel))
    if lang == "rust":
        for rel in sorted(set(current) | set(prepared)):
            if posixpath.basename(rel) in RUST_ALWAYS_PROTECTED and current.get(rel) != prepared.get(rel):
                reasons.append("rust: %s is protected (changed or added): %s" % (posixpath.basename(rel), rel))
    solution_dirs = {posixpath.dirname(s) for s in solutions}
    if lang == "java":
        solution_dirs = {posixpath.dirname(s) for s in solutions if s.endswith(".java")}
    existing = set()
    if lang == "java":
        for rel in prepared:
            if rel.endswith(".java") and rel in current:
                existing.add(_java_fqn(work, rel)[1])
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

    @property
    def collected(self):
        return set(self.leaves)

    @property
    def passing(self):
        return set() if self.all_failed else {k for k, ok in self.leaves.items() if ok}

    def failing(self, universe):
        return len(set(universe) - self.passing)


def grade(lang, work, slug, private, *, image_id=None, image_tag=IMAGE_TAG, run=None, guard=None, timeout=None,
          keep=None, seq=None, boundary=None, final=False):
    """Grade one prepared/snapshotted tree in the tg2 image. `slug` is the exercise directory name (C++ CMake derives
    its project and sources from it, so the tree is mounted at /work/<slug>). With `keep`, raw outputs are written to
    `<keep>/seq-NNNN/` from launch and indexed by sha256 on every exit path."""
    if lang not in LANGS:
        raise TransportAbort("unsupported tg2 grader language: %s" % lang)
    if not SLUG.match(slug):
        raise TransportAbort("unsafe exercise slug")
    work = Path(work).resolve()
    private = Path(private).resolve()
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
    result = Tg2Grade(lang=lang, image_id=image_id)
    state = dict(outcome="infrastructure")

    def index(outcome):
        state["outcome"] = outcome
        if directory is None:
            return {}
        names = sorted(p.name for p in directory.iterdir() if p.is_file() and p.name != "index.json"
                       and not p.name.startswith(".index"))
        doc = dict(version=VERSION, lang=lang, slug=slug, image_id=image_id, outcome=outcome, phases=result.phases)
        (directory / "phases.json").write_text(json.dumps(doc, indent=1, sort_keys=True))
        names = sorted(set(names) | {"phases.json"})
        return _write_index(keep, directory, seq, boundary, final, outcome, names)

    try:
        with tempfile.TemporaryDirectory(prefix="grade-tg2-", dir=private) as tmp:
            tmp = Path(tmp)
            report = tmp / "report"
            report.mkdir()
            outputs = directory if directory is not None else tmp / "out"
            outputs.mkdir(exist_ok=True)
            _grade(result, lang, work, slug, run, ops, image_id, image_tag, timeout, report, outputs, index)
            return result
    except BaseException:
        # Every escaping exception is an infrastructure outcome; the receipt index exists before it propagates.
        if directory is not None:
            index("infrastructure")
        raise


def _step(result, step, cmd, run, ops, outputs, timeout, work, container=None):
    """One launched step: output to files from launch, timing, hashes, OOM / memory-kill markers. Returns a record."""
    stdout_path, stderr_path = outputs / (step + ".stdout"), outputs / (step + ".stderr")
    if container:
        ops.register_container(container)
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
        oom = bool(container and ops.container_oom(container))
    finally:
        if container:
            ops.remove_container(container)
    rec = dict(step=step, rc=rc, seconds=round(time.monotonic() - started, 3), timed_out=timed_out, oom=oom,
               mem_kill=bool(getattr(ops, "grader_mem_kill", False)),
               stdout_sha256=_sha256(stdout_path), stderr_sha256=_sha256(stderr_path),
               stdout=stdout_path, stderr=stderr_path)
    result.phases.append({k: v for k, v in rec.items() if k not in ("stdout", "stderr")})
    return rec


def _text(rec):
    return rec["stdout"].read_text(errors="replace") + rec["stderr"].read_text(errors="replace")


def _resource(rec):
    for key, outcome in (("timed_out", "timeout"), ("oom", "oom"), ("mem_kill", "mem_kill")):
        if rec[key]:
            return outcome
    return None


def _grade(result, lang, work, slug, run, ops, image_id, image_tag, timeout, report, outputs, index):
    # --- setup: pinned image present by id, mounts and runtime launch
    for violation in skip_form_violations(work, lang):
        raise TransportAbort("tree contains a rewritten skip form (refused): " + violation)
    inspect = _step(result, "setup-image", ["docker", "image", "inspect", "--format", "{{.Id}}", image_tag], run, ops,
                    outputs, 60, work)
    seen = _text(inspect).strip()
    if inspect["rc"] != 0 or seen != image_id:
        raise TransportAbort("tg2 image %s does not match the pinned id (found %r)" % (image_tag, seen[:80]))
    launch = _launch(result, "setup-launch", ["true"], run, ops, image_id, slug, work, report, outputs, timeout)
    if launch["rc"] != 0 or launch["timed_out"]:
        raise TransportAbort("tg2 setup failed (rc=%s timeout=%s): %s" % (launch["rc"], launch["timed_out"],
                                                                          _text(launch)[-300:]))
    compile_script, execute_script = _commands(lang, slug)
    # --- compile
    comp = _launch(result, "compile", ["bash", "-c", compile_script], run, ops, image_id, slug, work, report, outputs,
                   timeout)
    kind = _resource(comp)
    if kind:
        return _all_failed(result, kind, index)
    _infra_check(comp, lang, "compile", offline=True)
    if comp["rc"] != 0:
        return _all_failed(result, "compile_failure", index)
    # --- execute
    exe = _launch(result, "execute", ["bash", "-c", execute_script], run, ops, image_id, slug, work, report, outputs,
                  timeout)
    kind = _resource(exe)
    if kind:
        return _all_failed(result, kind, index)
    _infra_check(exe, lang, "execute", offline=False)
    # --- parse (host side)
    rc = exe["rc"]
    text = _text(exe)
    clean = CLEAN_EXIT[lang](rc)
    try:
        leaves = _parse(lang, slug, work, report, outputs, exe)
    except ReportError as exc:
        if clean and not CRASH[lang].search(text):
            raise TransportAbort("missing or malformed %s report after a clean execute (rc=%s): %s" % (lang, rc, exc)) from None
        return _all_failed(result, "crash", index)
    result.leaves = leaves
    result.outcome = "parsed"
    result.artifacts = index("parsed")
    return result


def _launch(result, step, inner, run, ops, image_id, slug, work, report, outputs, timeout):
    name = ops.container_name()
    return _step(result, step, _docker_run(name, image_id, slug, work, report, inner), run, ops, outputs, timeout,
                 work, container=name)


def _infra_check(rec, lang, phase, *, offline):
    if rec["rc"] in INFRA_RC:
        raise TransportAbort("tg2 %s: docker/runtime failure rc=%s: %s" % (phase, rec["rc"], _text(rec)[-300:]))
    # Offline resolution happens at compile (manifests are protected); execute-phase text can be solution output.
    if offline and rec["rc"] and lang in ("rust", "java") and OFFLINE_DEP.search(_text(rec)):
        raise TransportAbort("tg2 %s: dependency not available offline in the image: %s" % (phase, _text(rec)[-300:]))


def _all_failed(result, outcome, index):
    result.outcome, result.all_failed = outcome, True
    result.artifacts = index(outcome)
    return result


def _parse(lang, slug, work, report, outputs, exe):
    if lang == "rust":
        return parse_rust(_text(exe))
    if lang == "java":
        files = sorted((work / "build/test-results/test").glob("*.xml"))
        if not files:
            raise ReportError("no JUnit XML under build/test-results/test")
        parts = []
        for n, path in enumerate(files):
            data = path.read_bytes()
            (outputs / ("junit-%03d.xml" % n)).write_bytes(data)
            parts.append(parse_junit(data.decode(errors="replace")))
        return merge_leaves(*parts)
    name, parser = ("jest.json", lambda t: parse_jest(t, "/work/" + slug)) if lang == "javascript" else (
        "cpp.xml", parse_junit)
    path = report / name
    if not path.is_file():
        raise ReportError("report %s was not written" % name)
    data = path.read_bytes()
    (outputs / ("report.json" if lang == "javascript" else "report.xml")).write_bytes(data)
    return parser(data.decode(errors="replace"))


def generate_cargo_locks(work, slug, private, *, image_id=None, run=None, guard=None, timeout=None):
    """Offline `cargo generate-lockfile` for every manifest (incl. nested ones such as macros/tests/invalid) from the
    image's vendored crate cache, in the same network-less container shape as a grade. Returns the lock paths."""
    work = Path(work).resolve()
    private = Path(private).resolve()
    private.mkdir(parents=True, exist_ok=True)
    image_id = image_id or pinned_image_id()
    ops = guard if guard is not None else (LocalDocker() if run is None else _NullOps())
    run = run or ops.run_grader
    script = r"find . -name Cargo.toml -not -path '*/target/*' -execdir cargo generate-lockfile --offline \;"
    with tempfile.TemporaryDirectory(prefix="locks-tg2-", dir=private) as tmp:
        tmp = Path(tmp)
        (tmp / "report").mkdir()
        result = Tg2Grade(lang="rust", image_id=image_id)
        rec = _launch(result, "locks", ["bash", "-c", script], run, ops, image_id, slug, work, tmp / "report", tmp,
                      TIMEOUT_FLOOR if timeout is None else timeout)
        if rec["rc"] != 0 or rec["timed_out"]:
            raise TransportAbort("cargo lock generation failed: %s" % _text(rec)[-300:])
    return sorted(p.relative_to(work).as_posix() for p in work.rglob("Cargo.lock") if "target" not in p.parts)
