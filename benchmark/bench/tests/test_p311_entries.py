"""P311-lite (ii): the generation core, the separate tg1 entry, provenance trimming."""
import ast
import importlib
import json
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parents[1]
ENTRY = BENCH.parent / "run_tg1_probe.py"

# Everything tg1_runner (and its tests) read from the injected probe module `p`.
TG1_USES = [
    "_sha_of", "NORETRY_PLUGIN", "SCAFFOLD_ENV_POLICY_V2", "_carrier_selection", "_default_opencode_bin",
    "PINNED_OPENCODE_VERSION_V2", "opencode_common", "_stack_workdir", "_require_opencode_bin", "_a4_receipt",
    "_make_run_dir", "_scratch_dir", "_git_init_scratch", "_seed_overlay", "_item_seed", "_opencode_env",
    "_fresh_tmpdir", "_parse_version", "_polyglot_sha", "_polyglot_root", "_scrub_pii", "_scrub_error", "_portable",
    "_item_scratch_dir", "_prepare", "_freeze_mtimes", "_prompt_date", "loop_metrics", "traffic_metrics",
    "_metric_export", "_seed_row_fields", "_worker_load_identity", "TransportAbort",
]


def imports_of(path):
    tree = ast.parse(Path(path).read_text())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:                      # `from . import x` / `from .x import y` inside bench/
                base = "bench" + ("." + base if base else "")
            found |= {base} if base != "bench" else {"bench." + a.name for a in node.names}
            if base and base != "bench":
                found |= {base + "." + a.name for a in node.names}
    return found


def test_core_provides_what_tg1_reads():
    from bench import opencode_v2_core as core
    missing = [n for n in TG1_USES if not hasattr(core, n)]
    assert not missing


def test_tg1_entry_imports_only_core_and_tg1_runner():
    local = {m for m in imports_of(ENTRY) if m.startswith("bench") or m in ("web_audit", "answer_key")}
    assert local == {"bench.opencode_v2_core", "bench.tg1_runner"}


def test_core_has_no_scoring_imports():
    local = imports_of(BENCH / "opencode_v2_core.py")
    for banned in ("bench.answer_key", "bench.web_scan", "bench.generate", "web_audit", "bench.tg1_score"):
        assert banned not in local


def test_tg1_entry_runs_tg1_and_standard_entry_refuses_it(monkeypatch, tmp_path):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    tg1 = importlib.import_module("run_tg1_probe")
    std = importlib.import_module("run_opencode_probe_v2")
    seen = {}
    from bench import tg1_runner
    monkeypatch.setattr(tg1_runner, "main", lambda p, a: seen.update(p=p, scaffold=a.scaffold) or 0)
    argv = ["x", "--model", "m", "--items", "a", "--seed-base", "1", "--scaffold", "opencode-v2-web-tg1"]
    monkeypatch.setattr(sys, "argv", argv)
    assert tg1.main() == 0
    assert seen["p"] is tg1 and seen["scaffold"] == "opencode-v2-web-tg1"
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc:
        std.main()
    assert exc.value.code != 0


def test_tg1_entry_accepts_only_the_tg1_scaffold(monkeypatch, tmp_path):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    tg1 = importlib.import_module("run_tg1_probe")
    monkeypatch.setattr(sys, "argv", ["x", "--model", "m", "--items", "a", "--seed-base", "1",
                                      "--scaffold", "opencode-v2"])
    with pytest.raises(SystemExit) as exc:
        tg1.main()
    assert exc.value.code != 0


def test_standard_entry_print_identity_points_to_tg1_entry(monkeypatch, tmp_path):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    std = importlib.import_module("run_opencode_probe_v2")
    monkeypatch.setattr(sys, "argv", ["x", "--print-identity"])
    with pytest.raises(SystemExit) as exc:
        std.main()
    assert "run_tg1_probe.py" in str(exc.value)


def test_bind_rebinds_core_functions_into_the_entry_namespace(tmp_path):
    from bench import opencode_v2_core as core
    ns = {"__name__": "fake_entry"}
    core.bind(ns)
    assert ns["_scratch_root"] is not core._scratch_root
    assert ns["_scratch_root"].__globals__ is ns
    assert ns["TransportAbort"] is core.TransportAbort          # classes are shared, not copied
    ns["_stack_workdir"] = lambda **k: tmp_path
    assert ns["_scratch_root"]() == str(tmp_path / "scratch/octmp.noindex")


def test_standard_entry_patches_reach_core_functions(monkeypatch, tmp_path):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    std = importlib.import_module("run_opencode_probe_v2")
    monkeypatch.setattr(std, "_stack_workdir", lambda **k: tmp_path / "w")
    assert std._scratch_root() == str(tmp_path / "w/scratch/octmp.noindex")


def test_provenance_no_longer_imports_generate():
    assert "bench.generate" not in imports_of(BENCH / "provenance.py")


def test_provenance_write_uses_the_callers_path(monkeypatch, tmp_path):
    from bench import provenance
    monkeypatch.setattr(provenance, "gather", lambda *a, **k: {"model": a[0]})
    with pytest.raises(ValueError):
        provenance.write("m", "bench")
    target = tmp_path / "m" / "bench.jsonl"
    man = provenance.write("m", "bench", result_path=target)
    assert man == {"model": "m"}
    assert json.loads(target.with_suffix(".manifest.json").read_text()) == man


def test_generate_passes_its_result_path_to_provenance_write(monkeypatch, tmp_path):
    from bench import generate, provenance
    got = {}
    monkeypatch.setattr(generate, "results_root", lambda: tmp_path)
    monkeypatch.setattr(provenance, "write", lambda m, b, **kw: got.update(kw))
    monkeypatch.setattr(provenance, "current_manifest_lite", lambda *a, **k: {"x": 1})
    generate.stamp_manifests([("M", "humanevalplus")], profile="deployed", overrides=None)
    assert Path(got["result_path"]) == generate.result_path("M", "humanevalplus")


def test_standard_entry_still_imports_its_scoring_paths():
    """P311-lite keeps the in-process scoring on the standard v2 entry (rerun policy, web scan)."""
    local = imports_of(BENCH.parent / "run_opencode_probe_v2.py")
    assert {"bench.answer_key", "bench.web_scan", "bench.opencode_v2_core", "bench.deny_rules"} <= local
    for name in ("_rerun_resume", "_web_audit", "_check_resume_v2", "_identity"):
        assert hasattr(importlib.import_module("run_opencode_probe_v2"), name)


def test_carrier_bytes_are_unchanged_by_the_deny_rules_move(tmp_path, monkeypatch):
    """Spec test 2: the deny patterns written into the carrier equal what the pre-move function produced."""
    import hashlib
    from bench.tests import p311_legacy as legacy
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    std = importlib.import_module("run_opencode_probe_v2")
    extra = tmp_path / "extra.json"
    patterns = ["*github.com/owner/repo", "*docs.example.test/page"]
    extra.write_text(json.dumps(patterns))
    got = std._carrier_selection("opencode-v2-web", None, extra_deny_file=extra)
    doc = json.loads(std.BENCH_OPENCODE_WEB_CONFIG.read_bytes())
    for pattern in patterns:
        doc.setdefault("permissions", []).append({"action": "webfetch", "resource": pattern, "effect": "deny"})
    doc["permissions"].extend({"action": "shell", "resource": p, "effect": "deny"}
                              for p in legacy.legacy_shell_deny_patterns(patterns))
    want = json.dumps(doc, sort_keys=True, indent=2).encode()
    assert got["bytes"] == want
    assert got["fields"]["opencode_bench_config_sha256"] == hashlib.sha256(want).hexdigest()
