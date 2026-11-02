"""Retained 1.18 helper unit tests; runner and binary integrations are frozen."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import run_opencode_probe as P
from bench import provenance

import hashlib

MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
SHIPPED = Path(P.BENCH_OPENCODE_CONFIG)



def test_pin_and_binary_install_dir_name_the_same_version():
    assert P.PINNED_OPENCODE_VERSION == "1.18.30"
    assert f"opencode-{P.PINNED_OPENCODE_VERSION}/" in P.OPENCODE_BIN_RELPATH


def test_opencode_bin_defaults_under_stack_workdir(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENCODE_PROBE_BIN", raising=False)
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    assert P._opencode_bin() == tmp_path / "opencode-1.18.30/node_modules/.bin/opencode"


def test_opencode_bin_env_override(monkeypatch):
    monkeypatch.setenv("OPENCODE_PROBE_BIN", "/x/opencode")
    assert P._opencode_bin() == Path("/x/opencode")


def test_opencode_version_refuses_a_missing_binary(tmp_path):
    with pytest.raises(SystemExit) as e:
        P._opencode_version(tmp_path / "nope")
    assert "nope" in str(e.value) or "missing" in str(e.value)


def _exe(path, body="#!/bin/sh\nexit 0\n", mode=0o755):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body); path.chmod(mode)
    return path


def test_require_opencode_bin_returns_the_exact_absolute_executable(monkeypatch, tmp_path):
    b = _exe(tmp_path / "x" / "opencode")
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(b))
    assert P._require_opencode_bin() == str(b)


def test_require_opencode_bin_refuses_relative_missing_and_non_executable(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCODE_PROBE_BIN", "opencode")           # bare name would be a PATH lookup
    with pytest.raises(SystemExit, match="absolute"):
        P._require_opencode_bin()
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(tmp_path / "gone" / "opencode"))
    with pytest.raises(SystemExit, match="gone"):
        P._require_opencode_bin()
    nx = _exe(tmp_path / "nx" / "opencode", mode=0o644)
    monkeypatch.setenv("OPENCODE_PROBE_BIN", str(nx))
    with pytest.raises(SystemExit, match="executable"):
        P._require_opencode_bin()


def test_overlay_is_the_seed_plus_title_and_snapshot_switches_and_nothing_else():
    assert P._seed_overlay(MODEL, 123) == {
        "provider": {"mlx-local": {"models": {MODEL: {"options": {"seed": 123}}}}},
        "agent": {"title": {"disable": True}}, "snapshot": False}


def test_write_overlay_writes_json_and_returns_sha(tmp_path):
    sha = P._write_seed_overlay(tmp_path, MODEL, 123)
    raw = (tmp_path / "opencode.json").read_bytes()
    assert json.loads(raw) == P._seed_overlay(MODEL, 123)
    assert sha == hashlib.sha256(raw).hexdigest()


def _receipt_env(monkeypatch, tmp_path):
    """A fake pinned install + config + test file, all under tmp_path."""
    b = _exe(tmp_path / "opencode-1.18.30" / "node_modules" / ".bin" / "opencode", "#!/bin/sh\necho 1.18.30\n")
    cfg = tmp_path / "shipped.json"; cfg.write_text('{"a": 1}')
    tf = tmp_path / "the_test.py"; tf.write_text("# test v1")
    monkeypatch.delenv("OPENCODE_PROBE_BIN", raising=False)
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    monkeypatch.setattr(P, "BENCH_OPENCODE_CONFIG", cfg)
    monkeypatch.setattr(P, "SEED_TEST_FILE", tf)
    return b, cfg, tf


def test_manifest_runtime_records_seed_provenance(monkeypatch, tmp_path):
    b, cfg, tf = _receipt_env(monkeypatch, tmp_path)
    rt = P._seed_runtime(7)
    assert rt["seed_base"] == 7 and rt["overlay_schema"].startswith("provider.mlx-local.models.<model>.options.seed")
    assert rt["opencode_bin"] == "$STACK_WORKDIR/opencode-1.18.30/node_modules/.bin/opencode"
    assert str(tmp_path) not in json.dumps(rt)
    assert rt["seed_propagation"] == "unverified"          # no receipt yet
    P._record_seed_propagation_verified(b)
    assert P._seed_runtime(7)["seed_propagation"] == "verified-by-test"


def test_receipt_is_bound_to_exe_config_and_test_hashes(monkeypatch, tmp_path):
    b, cfg, tf = _receipt_env(monkeypatch, tmp_path)
    P._record_seed_propagation_verified(b)
    r = json.loads(P._seed_marker_path(b).read_text())
    assert set(r) == {"version", "exe_sha256", "bench_config_sha256", "test_sha256"}
    ok = lambda: P._seed_runtime(7)["seed_propagation"]   # noqa: E731
    assert ok() == "verified-by-test"
    cfg.write_text('{"a": 2}')
    assert ok() == "unverified"
    cfg.write_text('{"a": 1}')
    assert ok() == "verified-by-test"
    tf.write_text("# test v2")
    assert ok() == "unverified"
    tf.write_text("# test v1")
    b.write_text("#!/bin/sh\necho 1.18.30 # rebuilt\n")
    assert ok() == "unverified"


def test_legacy_text_marker_reads_unverified(monkeypatch, tmp_path):
    b, cfg, tf = _receipt_env(monkeypatch, tmp_path)
    P._seed_marker_path(b).write_text(P.PINNED_OPENCODE_VERSION)
    assert P._seed_runtime(7)["seed_propagation"] == "unverified"


def test_env_disables_claude_code_prompt_loading(tmp_path):
    env = P._opencode_env(tmp_path / "xdg")
    assert env["OPENCODE_DISABLE_CLAUDE_CODE_PROMPT"] == "true"
    assert env["OPENCODE_DISABLE_EXTERNAL_SKILLS"] == "true"


def test_scaffold_policy_hash_changes_with_the_policy(monkeypatch):
    h0 = P._scaffold_runtime()["scaffold_policy_sha256"]
    monkeypatch.setattr(P, "SCAFFOLD_ENV_POLICY",
                        {"OPENCODE_DISABLE_EXTERNAL_SKILLS": "true"})   # the pre-C121 policy
    assert P._scaffold_runtime()["scaffold_policy_sha256"] != h0


def test_scaffold_runtime_names_both_switches_and_claude_md_state(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    rt = P._scaffold_runtime()
    assert "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT=true" in rt["skill_policy"]
    assert "OPENCODE_DISABLE_EXTERNAL_SKILLS=true" in rt["skill_policy"]
    assert rt["claude_md_present"] is False
    (tmp_path / ".claude").mkdir(); (tmp_path / ".claude" / "CLAUDE.md").write_text("x")
    assert P._scaffold_runtime()["claude_md_present"] is True


def _maybe_stamp_receipt(binary):
    """The operator opt-in branch of the AC3 test (OPENCODE_PROBE_RECORD_VERIFIED=1)."""
    if os.environ.get("OPENCODE_PROBE_RECORD_VERIFIED") == "1":
        P._record_seed_propagation_verified(binary)


@pytest.fixture
def _manifest_without_workers(monkeypatch, tmp_path):
    """Use the real registry without observing live processes or cached model weights."""
    monkeypatch.delenv("MLX_SERVE_CONFIG", raising=False)
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    monkeypatch.setattr(provenance, "_worker_argvs", lambda doc: [])
    monkeypatch.setattr(provenance, "apc_state", lambda: {"apc_enabled": "0", "source": "test"})
    monkeypatch.setattr(provenance, "session_retention_state", lambda: {})
    monkeypatch.setattr(provenance, "_resolve_snapshot", lambda hf_path: None)
    monkeypatch.setattr(provenance, "_git_shas", lambda: {})
    monkeypatch.setattr(provenance, "_box", lambda: "test")


def test_probe_manifest_records_real_registry_mtp_scan(_manifest_without_workers):
    assert provenance.paths.registry_path() == Path(P.REPO) / "main_models.yaml"
    man = provenance.gather(MODEL, profile="deployed", runtime={"client": "opencode"}, router={})
    assert man["runtime"]["mtp_verify_scan"] == "joint_v1"
    assert man["runtime"]["mtp_verify_scan_source"] == "registry"


def test_probe_manifest_refuses_unresolved_fake_model_scan(_manifest_without_workers):
    # No fake_model_mtp_scan fixture: the real resolver must leave this model unresolved.
    with pytest.raises(provenance.ServingStateError, match="M58: build_manifest needs a RESOLVED mtp_verify_scan"):
        provenance.gather("m", profile="deployed", runtime={"client": "opencode"}, router={})


def test_scaffold_runtime_folds_scratch_git_init_into_the_policy_hash(monkeypatch):
    rt = P._scaffold_runtime()
    assert rt["scratch_git_init"] is True
    monkeypatch.setattr(P, "SCRATCH_GIT_INIT", False)
    rt2 = P._scaffold_runtime()
    assert rt2["scratch_git_init"] is False
    assert rt2["scaffold_policy_sha256"] != rt["scaffold_policy_sha256"]


def test_ancestor_instruction_files_are_hashed_with_portable_paths(monkeypatch, tmp_path):
    home = tmp_path / "home"; scratch = home / "wd" / "scratch" / "octmp"
    scratch.mkdir(parents=True)
    (home / "AGENTS.md").write_text("operator instructions")
    (home / "wd" / "CLAUDE.md").write_text("claude")
    (home / "wd" / "CONTEXT.md").write_text("ctx")
    (home / "wd" / ".cursor").mkdir(); (home / "wd" / ".cursor" / "rules").write_text("r")   # never read by 1.18.30
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "isolated-workdir"))   # not the caller's
    got = P._ancestor_instruction_files(scratch)
    import hashlib
    assert got["~/AGENTS.md"] == hashlib.sha256(b"operator instructions").hexdigest()
    assert "~/wd/CLAUDE.md" in got and "~/wd/CONTEXT.md" in got
    assert "~/wd/.cursor/rules" not in got
    assert str(home) not in json.dumps(got)


def test_instruction_inventory_is_observation_only_never_in_the_policy_hash(monkeypatch, tmp_path):
    """E4: editing a (git-init-blocked) ancestor instruction file changes the recorded inventory hash but
    neither the scaffold-policy hash nor the receipt."""
    home = tmp_path / "home"; scratch = home / "scratch"; scratch.mkdir(parents=True)
    (home / "AGENTS.md").write_text("v1")
    monkeypatch.setenv("HOME", str(home)); monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "wd"))
    h1 = P._instruction_sources_sha256(P._instruction_sources(scratch)); p1 = P._scaffold_runtime()["scaffold_policy_sha256"]
    (home / "AGENTS.md").write_text("v2")
    h2 = P._instruction_sources_sha256(P._instruction_sources(scratch)); p2 = P._scaffold_runtime()["scaffold_policy_sha256"]
    assert h1 != h2 and p1 == p2


def test_policy_hash_changes_with_each_effective_input(monkeypatch):
    base = P._scaffold_runtime(opencode_version="1.18.30", exe_sha="e1")["scaffold_policy_sha256"]
    assert P._scaffold_runtime(opencode_version="1.18.31", exe_sha="e1")["scaffold_policy_sha256"] != base
    assert P._scaffold_runtime(opencode_version="1.18.30", exe_sha="e2")["scaffold_policy_sha256"] != base
    monkeypatch.setattr(P, "BENCH_HOME_ISOLATION", False)
    assert P._scaffold_runtime(opencode_version="1.18.30", exe_sha="e1")["scaffold_policy_sha256"] != base


def test_bench_config_home_holds_only_a_verbatim_copy_of_the_shipped_config(tmp_path):
    home = P._make_bench_config_home(tmp_path, "run1")
    assert sorted(p.name for p in home.rglob("*") if p.is_file()) == ["opencode.json"]
    assert (home / "opencode" / "opencode.json").read_bytes() == SHIPPED.read_bytes()
    assert P._sha_of(home / "opencode" / "opencode.json") == P._scaffold_runtime()["opencode_bench_config_sha256"]


def test_env_redirects_the_config_home_when_given(tmp_path):
    assert P._opencode_env(tmp_path / "d", tmp_path / "cfg")["XDG_CONFIG_HOME"] == str(tmp_path / "cfg")


def test_every_bench_role_registry_model_has_a_block_in_the_bench_config():
    import yaml
    reg = yaml.safe_load((Path(P.REPO) / "main_models.yaml").read_text())
    blocks = json.loads(SHIPPED.read_text())["provider"]["mlx-local"]["models"]
    need = [m["name"] for m in reg["models"] if (m.get("presentation") or {}).get("role") in ("main", "candidate")]
    assert need and [n for n in need if n not in blocks] == []


def test_bench_config_is_the_default_source_of_the_config_home(tmp_path):
    home = P._make_bench_config_home(tmp_path, "r")
    assert (home / "opencode" / "opencode.json").read_bytes() == Path(P.BENCH_OPENCODE_CONFIG).read_bytes()


def test_child_env_drops_every_parent_opencode_variable_then_applies_the_switches(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENCODE_DISABLE_CLAUDE_CODE_SKILLS", "true")
    monkeypatch.setenv("OPENCODE_SOMETHING_ELSE", "1")
    monkeypatch.setenv("OPENCODE_DISABLE_CLAUDE_CODE_PROMPT", "false")     # even a conflicting policy var
    env = P._opencode_env(tmp_path / "d")
    assert "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS" not in env and "OPENCODE_SOMETHING_ELSE" not in env
    assert env["OPENCODE_DISABLE_CLAUDE_CODE_PROMPT"] == "true"
    assert {k: v for k, v in env.items() if k.startswith("OPENCODE_")} == P.SCAFFOLD_ENV_POLICY


def test_bench_home_redirects_home_and_pins_the_real_cache_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    env = P._opencode_env(tmp_path / "d", tmp_path / "c", tmp_path / "s", tmp_path / "t", tmp_path / "home")
    assert env["HOME"] == str(tmp_path / "home")
    assert env["XDG_CACHE_HOME"] == str(Path(os.path.expanduser("~")) / ".cache")     # the REAL cache dir


def test_the_opt_in_receipt_branch_writes_a_readable_receipt(monkeypatch, tmp_path):
    b, cfg, tf = _receipt_env(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENCODE_PROBE_RECORD_VERIFIED", "1")
    monkeypatch.setenv("OPENCODE_PROBE_RECEIPT", str(tmp_path / "receipt.json"))
    assert P._seed_runtime(7)["seed_propagation"] == "unverified"
    _maybe_stamp_receipt(b)
    assert (tmp_path / "receipt.json").is_file()
    assert P._seed_runtime(7)["seed_propagation"] == "verified-by-test"
    monkeypatch.delenv("OPENCODE_PROBE_RECORD_VERIFIED")
    (tmp_path / "receipt.json").unlink()
    _maybe_stamp_receipt(b)                       # not opted in: nothing written
    assert not (tmp_path / "receipt.json").exists()


@pytest.mark.parametrize("planted", [".opencode", "AGENTS.md", "CLAUDE.md", ".claude"])
def test_bench_home_must_stay_clean(tmp_path, planted):
    home = tmp_path / "home"; home.mkdir()
    P._assert_bench_home_clean(home)                       # clean passes
    (home / planted).mkdir() if planted.startswith(".") else (home / planted).write_text("x")
    with pytest.raises(SystemExit, match=planted.replace(".", r"\.")):
        P._assert_bench_home_clean(home)


def test_config_home_may_hold_only_the_carrier_copy_and_gitignore(tmp_path):
    home = P._make_bench_config_home(tmp_path, "r7")
    P._assert_config_home_clean(home)
    (home / "opencode" / ".gitignore").write_text("node_modules\n")        # opencode's own file is fine
    P._assert_config_home_clean(home)
    (home / "opencode" / "AGENTS.md").write_text("x")
    with pytest.raises(SystemExit, match="AGENTS.md"):
        P._assert_config_home_clean(home)
    (home / "opencode" / "AGENTS.md").unlink()
    (home / "opencode" / "agent").mkdir()
    with pytest.raises(SystemExit, match="agent"):
        P._assert_config_home_clean(home)
