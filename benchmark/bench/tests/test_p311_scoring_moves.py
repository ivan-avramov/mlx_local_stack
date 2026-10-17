"""P311-lite (i): `deny_rules` (generation) and `web_scan` (scoring) are byte-equal moves (spec test 2)."""
import copy
import json

import pytest

from bench import answer_key
from bench.tests import p311_legacy as legacy


DENY_INPUTS = [
    [],
    ["*github.com/owner/repo"],
    ["github.com/owner/repo/*", "*gitlab.com/g/p*", "https://example.test/a/b"],
    ["*example.test/path/page", "*raw.githubusercontent.com/o/r/*", "x*"],
    ["*github.com/o/r.git*", "*docs.example.test/x#*", "*api.github.com/repos/o/r"],
]


@pytest.mark.parametrize("patterns", DENY_INPUTS)
def test_deny_rules_equal_legacy(patterns):
    from bench import deny_rules
    assert deny_rules.shell_deny_patterns(patterns) == legacy.legacy_shell_deny_patterns(patterns)


def test_answer_key_reexports_deny_rules():
    from bench import deny_rules
    assert answer_key.shell_deny_patterns is deny_rules.shell_deny_patterns


def test_deny_rules_is_generation_only():
    """It must not pull scoring code: only `re` and the stdlib."""
    import ast
    from pathlib import Path
    from bench import deny_rules
    tree = ast.parse(Path(deny_rules.__file__).read_text())
    mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert mods <= {"re", "__future__"}


def part(name, inputs=None, *, content=None, status=None, rejected=False):
    state = {"input": inputs or {}, "status": "error" if rejected else (status or "completed"), "content": content}
    if rejected:
        state["error"] = {"type": "permission.rejected", "message": "Permission rejected: fixture"}
    return {"type": "tool", "name": name, "state": state}


REFERENCE = "def secret_solution(values):\n    total = sum(values) * 3\n    return total + len(values) * 17\n" * 3


def cases():
    text = [{"type": "text", "text": REFERENCE}]
    return {
        "empty": [],
        "webfetch_completed": [part("webfetch", {"url": "https://example.test/doc"}, content="hello docs")],
        "webfetch_denied": [part("webfetch", {"url": "https://example.test/x"}, rejected=True)],
        "shell_net_and_plain": [part("shell", {"command": "curl https://example.test/a"}, content=text),
                                part("shell", {"command": "ls -la"}, content="ignored"),
                                part("shell", {"command": "curl -o out.txt https://example.test/b"}, content="x")],
        "contact": [part("webfetch", {"url": "https://example.test/sol"}, content=text)],
        "subagent": [part("subagent"), part("subagent"), part("webfetch", {"url": "https://e.test"}, content="x")],
        "surrogate_and_null": [part("webfetch", content="\ud800"), part("webfetch"),
                               {"type": "tool", "name": "webfetch", "state": {"status": "completed"}}],
        "non_tool_parts": [{"type": "text", "text": "hi"}, "stray"],
    }


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    item = tmp_path / "item"
    (item / ".meta").mkdir(parents=True)
    (item / ".meta/example.py").write_text(REFERENCE)
    return tmp_path, item


@pytest.mark.parametrize("scaffold", ["opencode-v2-web", "opencode-v2", "opencode-v2-web-tg1"])
@pytest.mark.parametrize("name", list(cases()))
def test_web_scan_equals_legacy_bytes(world, scaffold, name):
    from bench import web_scan
    tmp, item = world
    export = {"messages": [{"content": cases()[name]}]}
    old_target = tmp / "opencode_transcripts/old/item.json"
    new_target = tmp / "opencode_transcripts/new/item.json"
    old = legacy.legacy_web_audit(copy.deepcopy(export), item, old_target, scaffold=scaffold)
    new = web_scan.web_audit(copy.deepcopy(export), item, new_target, scaffold=scaffold)
    norm = lambda doc: json.dumps(doc, sort_keys=False).replace("/old/", "/X/").replace("/new/", "/X/")  # noqa: E731
    assert norm(new) == norm(old)
    old_files = sorted(p.relative_to(old_target.parent) for p in old_target.parent.rglob("*") if p.is_file())
    new_files = sorted(p.relative_to(new_target.parent) for p in new_target.parent.rglob("*") if p.is_file())
    assert new_files == old_files
    for rel in old_files:
        assert (new_target.parent / rel).read_bytes() == (old_target.parent / rel).read_bytes()


def test_web_scan_error_path_equals_legacy(world, monkeypatch):
    from bench import web_scan
    tmp, item = world
    export = {"messages": [{"content": [part("webfetch", {"url": "https://e.test"}, content="x")]}]}

    def boom(*a):
        raise RuntimeError("detector failure")
    monkeypatch.setattr(answer_key, "contact", boom)
    old = legacy.legacy_web_audit(copy.deepcopy(export), item, tmp / "opencode_transcripts/o/i.json")
    new = web_scan.web_audit(copy.deepcopy(export), item, tmp / "opencode_transcripts/n/i.json")
    norm = lambda doc: json.dumps(doc).replace("/o/", "/X/").replace("/n/", "/X/")  # noqa: E731
    assert norm(new) == norm(old) and "detector failure" in new["web_audit_error"]


def test_standard_probe_wrapper_unchanged(world):
    """`probe._web_audit` keeps its signature and result (the standard v2 entry still scores in-process)."""
    import importlib
    probe = importlib.import_module("run_opencode_probe_v2")
    tmp, item = world
    export = {"messages": [{"content": cases()["contact"]}]}
    got = probe._web_audit(copy.deepcopy(export), item, tmp / "opencode_transcripts/p/i.json")
    want = legacy.legacy_web_audit(copy.deepcopy(export), item, tmp / "opencode_transcripts/l/i.json")
    assert json.dumps(got).replace("/p/", "/X/") == json.dumps(want).replace("/l/", "/X/")
    assert got["answer_key_contact"] is True
