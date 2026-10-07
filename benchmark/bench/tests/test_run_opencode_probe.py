"""Retained 1.18 environment/provenance unit tests; shared tests moved to test_opencode_common."""
import run_opencode_probe as P



def test_opencode_env_redirects_only_the_data_home(tmp_path):
    env = P._opencode_env(tmp_path / "xdg")
    assert env["XDG_DATA_HOME"] == str(tmp_path / "xdg")
    assert "XDG_CACHE_HOME" not in env or env["XDG_CACHE_HOME"] == __import__("os").environ.get("XDG_CACHE_HOME")


def test_opencode_env_disables_external_skill_trees(tmp_path):
    """opencode lists every skill it finds under ~/.claude/skills (incl. synced/ and .trash/) and
    ~/.agents/skills in its system prompt, with file paths. Measured 2026-09-27: 17 skills, half the
    system prompt, paths that change between processes. The probe's scaffold must not depend on what
    Claude Code happens to have synced on this machine."""
    env = P._opencode_env(tmp_path / "xdg")
    assert env["OPENCODE_DISABLE_EXTERNAL_SKILLS"] == "true"


def test_manifest_runtime_records_the_skill_policy_and_config_hash(monkeypatch, tmp_path):
    cfg = tmp_path / "opencode.json"; cfg.write_text('{"model": "x"}')
    monkeypatch.setattr(P, "SHIPPED_OPENCODE_CONFIG", cfg)
    rt = P._scaffold_runtime()
    assert rt["skill_policy"] == ("OPENCODE_DISABLE_CLAUDE_CODE_PROMPT=true,"
                                  "OPENCODE_DISABLE_EXTERNAL_SKILLS=true")   # C121/R8 adds the first
    import hashlib
    assert rt["opencode_config_sha256"] == hashlib.sha256(cfg.read_bytes()).hexdigest()
    assert rt["opencode_config"] == "opencode_config/opencode.json"
