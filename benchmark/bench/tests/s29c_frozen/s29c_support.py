"""S29c (tg2 testable, spec docs/specs/s29-tg2-testable.md v1.1) test support: pure helpers, no assertions about the implementation.

Contents
* the carrier's permission evaluation (T3 / T4): a faithful POSIX port of opencode 2.0.20 `util/wildcard.ts` (the same port
  `tests/test_m61_round7.py` carries, verified there against the pinned binary) over the carrier's own `permissions` list. The repo
  exposes no matcher from production code, so the rule set is evaluated here "as opencode documents it": a rule applies when its
  action equals the tool's permission name and its resource wildcard matches the tool's resource; no matching rule = allow (the
  carrier has no `shell allow` rule and shell commands run, so the unmatched default is allow). Because the engine's order
  semantics and its handling of a compound shell command are not exposed to the repo, every verdict is taken under ALL readings:
  {last matching rule wins, any deny wins} x {the whole command string is the resource, each command node is a resource}.
  "denied" must hold under every reading; "allowed" must hold under every reading.
* the stated test command (T2): the command(s) in backticks in the prompt's helper tail (after "Do NOT modify ...").
* static enumeration of the tests a prepared tree enables under that command (T1 without docker). (allow-shorthand: a C++ / English word, not a model name)
* a container runner for the stated command in the pinned tg2-grader image (docker tests only).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
CARRIER = REPO / "benchmark/opencode_bench_v2_web_tg2.json"
UNIVERSE = REPO / "benchmark/m65/tg2_universe.json"
SHAPE = Path(__file__).resolve().parent / "fixtures/s29_p16_shape.json"
BASELINE = "cd334f773e6bc6d1e2f9f1344755e4df787b4fef"
LANGS = ("rust", "javascript", "java", "cpp")


# ---------------------------------------------------------------------------------------------------- the universe
def universe_doc():
    return json.loads(UNIVERSE.read_text())


def universe_items():
    doc = universe_doc()
    return sorted(i for i, e in doc["items"].items() if e.get("status") == "valid")


def items_of(lang):
    return [i for i in universe_items() if i.split("/", 1)[0] == lang]


def optional_of(item):
    from bench import tg2_grade as tg
    lang, slug = item.split("/", 1)
    return set(tg.OPTIONAL_LEAVES.get((lang, slug), frozenset()))


def graded_leaves(item):
    """The leaves the grader grades: the item's frozen leaves minus the grader's frozen optional leaves."""
    return set(universe_doc()["items"][item]["leaves"]) - optional_of(item)


# --------------------------------------------------------------------------------------------------------- corpus
def polyglot_root():
    base = os.environ.get("POLYGLOT_DIR") or str(Path(os.environ.get("STACK_WORKDIR", "")) / "polyglot-benchmark")
    root = Path(base)
    if not (root / "rust/exercises/practice").is_dir():
        pytest.skip("polyglot corpus not found (set POLYGLOT_DIR / STACK_WORKDIR)")
    return root


def make_corpus():
    from bench import corpus_tg2 as ct
    return ct.Tg2Corpus(polyglot_root=polyglot_root())


def prepare(corpus, item, dest):
    """The production preparation (`Tg2Corpus.prepare`). A corpus that is not the pinned one skips (environment); any other
    failure of the preparation is the implementation's and propagates."""
    from bench.token_turn_gate import TransportAbort
    try:
        corpus.verify_source(item)
    except TransportAbort as exc:
        pytest.skip(f"the polyglot checkout is not the pinned one: {exc}")
    return corpus.prepare(item, dest)


def apply_reference(prepared_work, lang, slug):
    from bench import tg2_materialize as mat
    root = polyglot_root()
    return mat.apply_reference(root, mat.read_plan(root, lang, slug), prepared_work)


def prompt_of(corpus, prepared):
    return corpus.prompt(prepared)


# ------------------------------------------------------------------------------------------ the stated command (T2)
TOOL = {
    "rust": r"\bcargo\b",
    "java": r"\bgradlew?\b|\./gradlew\b",
    "javascript": r"\bnpm\b|\bnpx\b|\byarn\b|\bjest\b",
    "cpp": r"\bcmake\b|\bctest\b|\bmake\b|\./build/",
}
CANONICAL = {            # the language's standard test command with no flag the agent was told about
    "rust": "cargo test",
    "java": "./gradlew test",
    "javascript": "npm test",
    "cpp": "cmake -S . -B build && cmake --build build && ./build/{slug}",
}


def helper_tail(prompt):
    at = prompt.rfind("Do NOT modify")
    return prompt[at:] if at >= 0 else prompt


def stated_commands(lang, prompt):
    """The backtick-quoted commands of the prompt's helper tail that start / contain the language's build or test tool."""
    spans = re.findall(r"`([^`\n]+)`", helper_tail(prompt))
    return [s.strip() for s in spans if re.search(TOOL[lang], s)]


def stated_or_canonical(lang, slug, prompt):
    found = stated_commands(lang, prompt)
    return " && ".join(found) if found else CANONICAL[lang].format(slug=slug)


# ------------------------------------------------------------------------------- static enumeration (T1, no docker)  # allow-shorthand
def _strip_strings(text):
    return re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)


def rust_tests(text):
    """[(fn name, ignored)] of the `#[test]` functions cargo compiles by default: attributes may span lines; `#[ignore]` /
    `#[ignore = ".."]`. A test (or a `mod` holding tests) under `#[cfg(feature = ..)]` is not compiled without the feature, so it
    is not a test of the default run and is not listed (delivery 3: wordy / xorcism / doubly-linked-list)."""
    out, attrs, cur, adepth = [], [], "", 0
    depth, gates = 0, []                 # brace depth; the depths at which a feature-gated `mod` opened
    if re.search(r"(?m)^\s*#!\[\s*cfg\s*\(\s*feature\b", text):
        return []

    def gated(joined):
        return re.search(r"#\[\s*cfg\s*\(\s*feature\b", joined) is not None

    for line in text.splitlines():
        s = _strip_strings(line.strip())
        if adepth > 0 or s.startswith("#["):
            cur += " " + s
            adepth += s.count("[") - s.count("]")
            if adepth > 0:
                continue
            attrs.append(cur)
            cur, adepth = "", 0
            m = re.search(r"\bfn\s+(\w+)\s*[<(]", s)
            if not m:
                continue
        else:
            if not s or s.startswith("//"):
                continue
            m = re.match(r"(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)", s)
            if re.match(r"(?:pub(?:\([^)]*\))?\s+)?mod\s+\w+\s*\{", s) and attrs and gated(" ".join(attrs)):
                gates.append(depth)
            if not m:
                attrs = []
                depth += s.count("{") - s.count("}")
                while gates and depth <= gates[-1]:
                    gates.pop()
                continue
        joined = " ".join(attrs)
        if re.search(r"#\[\s*(?:\w+::)*test\b", joined) and not gates and not gated(joined):
            out.append((m.group(1), re.search(r"\bignore\b", joined) is not None))
        attrs = []
        depth += s.count("{") - s.count("}")
        while gates and depth <= gates[-1]:
            gates.pop()
    return out


def rust_enabled(work, command):
    """{(file, name)} of the top-level integration tests `command` runs: ignored ones only with `--include-ignored`."""
    include = "--include-ignored" in command
    out, ignored = set(), set()
    for path in sorted(Path(work).glob("tests/*.rs")):
        for name, is_ignored in rust_tests(path.read_text(errors="replace")):
            key = ("tests/" + path.name, name)
            (ignored if is_ignored else out).add(key)
    return (out | ignored if include else out), ignored


def rust_graded(item):
    out = set()
    for leaf in graded_leaves(item):
        if leaf.startswith("tests/"):
            file, rest = leaf.split("::", 1)
            out.add((file, rest.split("::")[-1]))
    return out


def cpp_cases(text):
    """[(TEST_CASE name, guarded by EXERCISM_RUN_ALL_TESTS)] of a Catch2 test file."""
    def kind(rest):
        if "EXERCISM_RUN_ALL_TESTS" in rest and "!" not in rest:
            return "all"
        return "other" if "EXERCISM_INCLUDE_BENCHMARK" in rest else None       # benchmarks: not run, not graded

    text = re.sub(r"(?m)^[ \t]*//.*$", "", text)            # comment-only lines (`// clang-format off` between `TEST_CASE(` and its name)
    text = re.sub(r"\b(TEST_CASE|SCENARIO)\s*\(\s*\n\s*", r"\1(", text)
    text = re.sub(r'"[ \t]*\r?\n[ \t]*"', "", text)       # adjacent string literals across lines are one literal (delivery 3)
    stack, out = [], []
    for line in text.splitlines():
        m = re.match(r"\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b(.*)", line)
        if m:
            kw, rest = m.groups()
            if kw in ("if", "ifdef"):
                stack.append(kind(rest))
            elif kw == "ifndef":
                stack.append(None)
            elif kw == "elif":
                if stack:
                    stack[-1] = kind(rest)
            elif kw == "else":
                if stack:
                    stack[-1] = None
            elif kw == "endif" and stack:
                stack.pop()
            continue
        for name, tags in re.findall(r'\b(?:TEST_CASE|SCENARIO)\s*\(\s*"((?:[^"\\]|\\.)*)"(?:\s*,\s*"((?:[^"\\]|\\.)*)")?', line):
            if re.search(r"\[(?:\.[^\]]*|!benchmark|!hide)\]", tags) or "other" in stack:
                continue                       # hidden by Catch2 itself or behind a benchmark macro: not run by default, not graded
            out.append((name, "all" in stack))
    return out


def cpp_default_on(cmake_text, command):
    """Does the build define EXERCISM_RUN_ALL_TESTS under `command` (a -D flag, an ON default, or an unconditional define)?"""
    if re.search(r"-D\s*EXERCISM_RUN_ALL_TESTS(?::\w+)?=(?:ON|1|TRUE|YES|Y)\b", command, re.I):
        return True
    if re.search(r"(?im)^\s*option\s*\(\s*EXERCISM_RUN_ALL_TESTS\b[^)]*\bON\b", cmake_text):
        return True
    if re.search(r"(?im)^\s*set\s*\(\s*EXERCISM_RUN_ALL_TESTS\s+(?:ON|TRUE|1)\b", cmake_text):
        return True
    rest = re.sub(r"(?is)\bif\s*\([^)]*EXERCISM_RUN_ALL_TESTS[^)]*\).*?\bendif\s*\(\s*\)", "", cmake_text)
    return bool(re.search(r"EXERCISM_RUN_ALL_TESTS", rest)
                and re.search(r"add_definitions|target_compile_definitions|add_compile_definitions|CMAKE_CXX_FLAGS", rest))


def cpp_enabled(work, slug, command):
    """(enabled names, guarded-and-disabled names, all names) of the item's `<name>_test.cpp` under `command`."""
    work = Path(work)
    tests = sorted(work.glob("*_test.cpp"))
    on = cpp_default_on((work / "CMakeLists.txt").read_text(errors="replace"), command)
    enabled, disabled, every = set(), set(), set()
    for path in tests:
        for name, guarded in cpp_cases(path.read_text(errors="replace")):
            every.add(name)
            (disabled if guarded and not on else enabled).add(name)
    return enabled, disabled, every


def cpp_cover(enabled, leaf_names):
    """(graded leaves no enabled TEST_CASE produces, enabled TEST_CASEs no graded leaf comes from). A Catch2 JUnit leaf is the
    case name, or `<case>/<section>` when the case has SECTIONs."""
    def from_case(leaf, name):
        return leaf == name or leaf.startswith(name + "/")
    unmatched = sorted(leaf for leaf in leaf_names if not any(from_case(leaf, n) for n in enabled))
    uncovered = sorted(n for n in enabled if not any(from_case(leaf, n) for leaf in leaf_names))
    return unmatched, uncovered


JS_SKIP_FORMS =re.compile(r"\b(?:xtest|xit|xdescribe|(?:test|it|describe)\.(?:skip|todo))\s*\(")
JS_FILE = re.compile(r"\.(?:spec|test)\.[cm]?js$", re.I)


def js_skips(work):
    """{file: skip-form count} of the JavaScript test files."""
    out = {}
    for path in sorted(Path(work).glob("*.js")):
        if JS_FILE.search(path.name):
            n = len(JS_SKIP_FORMS.findall(path.read_text(errors="replace")))
            if n:
                out[path.name] = n
    return out


def java_skips(work):
    out = {}
    for path in sorted(Path(work).glob("src/test/**/*.java")):
        n = len(re.findall(r"@Disabled\b|@Ignore\b", path.read_text(errors="replace")))
        if n:
            out[path.relative_to(work).as_posix()] = n
    return out


# ------------------------------------------------------------------------------------- permissions (T3 / T4)
def wildcard_match(text, pattern):
    """Faithful POSIX port of opencode 2.0.20 util/wildcard.ts (as in tests/test_m61_round7.py)."""
    e = re.sub(r"[.+^${}()|\[\]\\]", lambda m: "\\" + m.group(0), pattern.replace("\\", "/"))
    e = e.replace("*", ".*").replace("?", ".")
    if e.endswith(" .*"):
        e = e[:-3] + "( .*)?"
    return re.match("^" + e + "$", text.replace("\\", "/"), re.S) is not None


def carrier_rules():
    return json.loads(CARRIER.read_text())["permissions"]


def _decision(rules, action, resource, semantic):
    hits = [r["effect"] for r in rules
            if r["action"] in (action, "*") and wildcard_match(resource, r["resource"])]
    if not hits:
        return "allow"
    if semantic == "last":
        return hits[-1]
    return "deny" if "deny" in hits else hits[-1]


NODE_SPLIT = re.compile(r"\s*(?:&&|\|\||;|\||\n)\s*")


def command_nodes(command):
    """The command's simple-command nodes: split at `&&`, `||`, `;`, `|` and newlines; `$( ... )` / backtick bodies are
    extracted as nodes of their own."""
    nodes = []
    for part in NODE_SPLIT.split(command):
        part = part.strip()
        if part:
            nodes.append(part)
        nodes.extend(n.strip() for n in re.findall(r"\$\(([^()]*)\)", part) + re.findall(r"`([^`]*)`", part) if n.strip())
    return nodes


def readings(rules, action, resource):
    """Every verdict of one tool call: {(engine, semantic): 'allow' | 'deny'}. A shell command is evaluated whole and node by node."""
    out = {}
    for semantic in ("last", "deny_wins"):
        out[("whole", semantic)] = _decision(rules, action, resource, semantic)
        if action == "shell":
            verdicts = [_decision(rules, action, n, semantic) for n in command_nodes(resource)] or ["allow"]
            out[("nodes", semantic)] = "deny" if "deny" in verdicts else "allow"
    return out


def denied_everywhere(action, resource, rules=None):
    return all(v == "deny" for v in readings(rules or carrier_rules(), action, resource).values())


def allowed_everywhere(action, resource, rules=None):
    return all(v == "allow" for v in readings(rules or carrier_rules(), action, resource).values())


def explain(action, resource, rules=None):
    return f"{action} {resource!r}: " + ", ".join(f"{e}/{s}={v}" for (e, s), v in sorted(readings(rules or carrier_rules(), action, resource).items()))


def case_variants(text):
    """The text as written, with every `exercism` / `problem-specifications` in Title and UPPER case."""
    title = re.sub("exercism", "Exercism", text, flags=re.I)
    title = re.sub("problem-specifications", "Problem-Specifications", title, flags=re.I)
    upper = re.sub("exercism", "EXERCISM", text, flags=re.I)
    upper = re.sub("problem-specifications", "PROBLEM-SPECIFICATIONS", upper, flags=re.I)
    return list(dict.fromkeys([text, title, upper]))


# --------------------------------------------------------------------------------------------- container (docker)
def docker_skip_reason():
    from bench import tg2_grade as tg
    docker = shutil.which("docker") or str(Path.home() / ".orbstack/bin/docker")
    if not Path(docker).exists():
        return "docker CLI not available"
    try:
        pinned = tg.pinned_image_id()
        out = subprocess.run([docker, "image", "inspect", "--format", "{{.Id}}", pinned], capture_output=True, text=True,
                             timeout=30)
    except Exception as exc:  # noqa: BLE001
        return f"docker unavailable: {exc}"
    if out.returncode:
        return f"the tg2-grader image {tg.IMAGE_TAG} is not built locally"
    root = os.environ.get("POLYGLOT_DIR") or str(Path(os.environ.get("STACK_WORKDIR", "")) / "polyglot-benchmark")
    if not (Path(root) / "rust/exercises/practice").is_dir():
        return "polyglot corpus not found (set POLYGLOT_DIR / STACK_WORKDIR)"
    return None


def docker_env():
    docker_bin = shutil.which("docker") or str(Path.home() / ".orbstack/bin/docker")
    os.environ["PATH"] = str(Path(docker_bin).parent) + os.pathsep + os.environ["PATH"]


_PRE = {
    "rust": "find . -name Cargo.toml -not -path './target/*' -execdir sh -c 'rm -f Cargo.lock && cargo generate-lockfile --offline' \\; ; ",
    "javascript": "[ -e node_modules ] || ln -s /opt/tg2/js/node_modules node_modules; ",
    "java": "chmod +x gradlew 2>/dev/null; ",
    "cpp": "",
}


def container_script(lang, command):
    """The stated command as the agent would type it, plus only what the network-less grader container needs: offline flags, the
    lock file / node_modules the agent's host would have fetched."""
    cmd = command
    if lang == "rust":
        cmd = re.sub(r"\bcargo (test|build|check|run)\b", r"cargo \1 --offline", cmd)
    elif lang == "java":
        cmd = re.sub(r"(\./gradlew|\bgradlew|\bgradle)\b", r"\1 --offline --no-daemon", cmd)
    if lang == "javascript" and re.search(r"\bnpm (?:install|i|ci)\b", cmd):
        return cmd                                        # the agent's own install: no pre-linked node_modules (delivery 3)
    return _PRE[lang] + cmd


NETWORK_FAILURE = re.compile(r"EAI_AGAIN|ENOTFOUND|ETIMEDOUT|ECONNREFUSED|ECONNRESET|network", re.I)


def run_in_container(work, slug, lang, command, timeout=900):
    """Run `command` in the pinned tg2 image over `work` (bind-mounted writable; no network, except javascript, whose stated
    `npm install` needs the registry exactly as the agent's host has it - delivery 3). -> (rc, output)."""
    from bench import tg2_grade as tg
    name = "s29c-" + uuid.uuid4().hex[:12]
    network = [] if lang == "javascript" else ["--network", "none"]
    argv = ["docker", "run", "--rm", "--name", name, "--pull=never", *network, "--memory", "4g", "--memory-swap", "4g",
            "--mount", f"type=bind,src={Path(work).resolve()},dst=/work/{slug}", "-w", f"/work/{slug}",
            tg.pinned_image_id(), "bash", "-c", container_script(lang, command)]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        subprocess.run(["docker", "kill", name], capture_output=True, timeout=60)
        return 124, (exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else str(exc.stdout or "")
    return proc.returncode, proc.stdout + proc.stderr


def parse_local(lang, work, out):
    """What a local run executed: {passed, failed, skipped, names (java only)} from the tool's own output / report files."""
    if lang == "rust":
        rows = re.findall(r"test result: \w+\. (\d+) passed; (\d+) failed; (\d+) ignored", out)
        if not rows:
            return None
        return dict(passed=sum(int(r[0]) for r in rows), failed=sum(int(r[1]) for r in rows), skipped=sum(int(r[2]) for r in rows))
    if lang == "java":
        from bench import tg2_grade as tg
        files = sorted(Path(work).glob("build/test-results/test/*.xml"))
        if not files:
            return None
        leaves = tg.merge_leaves(*(tg.parse_junit(f.read_text(errors="replace")) for f in files))
        return dict(passed=sum(leaves.values()), failed=sum(1 for v in leaves.values() if not v), skipped=0, names=set(leaves))
    if lang == "javascript":
        m = re.findall(r"Tests:\s+(?:(\d+) failed, )?(?:(\d+) skipped, )?(?:(\d+) todo, )?(?:(\d+) passed, )?(\d+) total", out)
        if not m:
            return None
        failed, skipped, _todo, passed, _total = m[-1]
        return dict(passed=int(passed or 0), failed=int(failed or 0), skipped=int(skipped or 0))
    ok = re.findall(r"All tests passed \(\d+ assertions? in (\d+) test cases?\)", out)
    bad = re.findall(r"test cases: (\d+) \|(?: (\d+) passed \|)?(?: (\d+) failed)?", out)
    if ok and not bad:
        return dict(passed=int(ok[-1]), failed=0, skipped=0)
    if bad:
        total, passed, failed = bad[-1]
        return dict(passed=int(passed or 0), failed=int(failed or 0), skipped=0)
    if ok:
        return dict(passed=int(ok[-1]), failed=0, skipped=0)
    return None
