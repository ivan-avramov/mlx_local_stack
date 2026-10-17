"""P311-lite (iv): per-arm identity from the verified worker argv and the served registry entry (spec 4, test 3)."""
import copy
import json
import os
from pathlib import Path

import pytest

from bench import arm_identity as ai

TARGET = "caslca/Target-4bit"
DRAFT = "caslca/Target-4bit-mtp-drafter"

ARGV = ["/venv/bin/python", "/venv/bin/mlx_vlm.server", "--model", TARGET, "--host", "127.0.0.1", "--port", "8091",
        "--max-kv-size", "262144", "--kv-prealloc-tokens", "262144", "--kv-bits", "4", "--kv-quant-scheme",
        "turboquant", "--prefill-step-size", "512", "--generation-defaults", '{"temperature": 0.6}',
        "--quantized-kv-start", "0", "--memory-limit-frac", "0.85"]
ARGV_ON = ARGV + ["--draft-kind", "mtp", "--draft-model", DRAFT, "--draft-block-size", "4",
                  "--mtp-verify-scan", "joint_v1", "--attention-policy", "fused_v1", "--lazy-prompt-embeddings"]
ENTRY = {"name": "m", "hf_path": TARGET, "kv_bits": 4, "generation_defaults": {"temperature": 0.6},
         "presentation": {"role": "main"}}
ENTRY_ON = {**ENTRY, "draft_kind": "mtp", "draft_model": DRAFT, "draft_block_size": 4}


def cache(tmp_path, repo, files, revision="a" * 40):
    """A HF hub cache for `repo`: refs/main -> revision; snapshot files are symlinks to blobs named `blob`."""
    root = tmp_path / "hub" / ("models--" + repo.replace("/", "--"))
    snap = root / "snapshots" / revision
    (root / "refs").mkdir(parents=True, exist_ok=True)
    (root / "blobs").mkdir(exist_ok=True)
    snap.mkdir(parents=True, exist_ok=True)
    (root / "refs/main").write_text(revision)
    for name, blob in files.items():
        (root / "blobs" / blob).write_text(blob)
        link = snap / name
        link.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(Path("../../blobs") / blob, link) if "/" not in name else os.symlink(
            Path("../../../blobs") / blob, link)
    return tmp_path


@pytest.fixture
def hf(tmp_path):
    cache(tmp_path, TARGET, {"config.json": "c1", "model.safetensors": "w" * 64})
    cache(tmp_path, DRAFT, {"config.json": "d1", "model.safetensors": "v" * 64})
    return tmp_path


APC_OFF = {"router": "0", "worker": "0"}


def sha(argv, entry, hf_home, apc=APC_OFF, retain="on"):
    return ai.arm_identity_sha256(ai.fingerprint(argv, entry, hf_home=hf_home, apc=apc, retain_default=retain))


def with_flag(argv, flag, value):
    out = list(argv)
    if flag in out:
        out[out.index(flag) + 1] = value
    else:
        out += [flag, value]
    return out


def test_parse_known_flags_values_booleans_and_equals_form():
    flags = ai.parse_argv(ARGV_ON + ["--mtp-verify-ab", "--suffix-min-match=3"])
    assert flags["--model"] == TARGET and flags["--lazy-prompt-embeddings"] is True
    assert flags["--mtp-verify-ab"] is True and flags["--suffix-min-match"] == "3"
    assert flags["--generation-defaults"] == '{"temperature": 0.6}'


@pytest.mark.parametrize("bad", [ARGV + ["--surprise-flag", "1"], ARGV + ["--kv-bits", "8"],      # unknown / duplicate
                                 ["/venv/bin/python", "/venv/bin/mlx_vlm.server", "--host", "127.0.0.1"]])
def test_unknown_duplicate_and_modelless_argv_refuse(bad):
    with pytest.raises(ai.ArmIdentityError):
        ai.parse_argv(bad)


@pytest.mark.parametrize("flag,value", [
    ("--max-kv-size", "131072"), ("--kv-prealloc-tokens", "131072"), ("--kv-bits", "8"),
    ("--kv-quant-scheme", "uniform"), ("--prefill-step-size", "2048"), ("--quantized-kv-start", "128"),
    ("--generation-defaults", '{"temperature": 0.5}'), ("--draft-block-size", "8"), ("--mtp-verify-scan", "per_query"),
    ("--attention-policy", "auto"), ("--draft-kind", "suffix"),
])
def test_arm_identity_changes_for_each_output_determining_flag(hf, flag, value):
    base = sha(ARGV_ON, ENTRY_ON, hf)
    changed = with_flag(ARGV_ON, flag, value)
    if flag == "--draft-kind":
        changed = with_flag(ARGV_ON, flag, "suffix")
        entry = {**ENTRY_ON, "draft_kind": "suffix"}
        assert sha(changed, entry, hf) != base
    else:
        assert sha(changed, ENTRY_ON, hf) != base


def test_arm_identity_changes_for_added_boolean_and_draft_flags(hf):
    base = sha(ARGV_ON, ENTRY_ON, hf)
    assert sha(ARGV_ON + ["--mtp-verify-ab"], ENTRY_ON, hf) != base
    assert sha([a for a in ARGV_ON if a != "--lazy-prompt-embeddings"], ENTRY_ON, hf) != base
    assert sha(ARGV_ON + ["--suffix-min-match", "3"], ENTRY_ON, hf) != base
    assert sha(ARGV_ON + ["--draft-cooldown", "2"], ENTRY_ON, hf) != base


@pytest.mark.parametrize("flag,value", [("--host", "0.0.0.0"), ("--port", "9999"), ("--memory-limit-frac", "0.5")])
def test_inert_flags_do_not_change_the_arm_identity(hf, flag, value):
    assert sha(with_flag(ARGV_ON, flag, value), ENTRY_ON, hf) == sha(ARGV_ON, ENTRY_ON, hf)


def test_a_changed_draft_artifact_changes_the_arm(hf):
    base = sha(ARGV_ON, ENTRY_ON, hf)
    cache(hf, DRAFT, {"config.json": "d1", "model.safetensors": "u" * 64}, revision="b" * 40)
    (hf / "hub/models--caslca--Target-4bit-mtp-drafter/refs/main").write_text("b" * 40)
    assert sha(ARGV_ON, ENTRY_ON, hf) != base


def test_a_changed_target_artifact_changes_the_arm(hf):
    base = sha(ARGV, ENTRY, hf)
    link = hf / "hub/models--caslca--Target-4bit/snapshots" / ("a" * 40) / "model.safetensors"
    link.unlink()
    os.symlink(Path("../../blobs") / ("z" * 64), link)
    assert sha(ARGV, ENTRY, hf) != base


def test_draft_off_arm_ignores_draft_artifacts(hf):
    """A draft-OFF worker has no draft artifact; the draft repo need not even be cached."""
    import shutil
    shutil.rmtree(hf / "hub/models--caslca--Target-4bit-mtp-drafter")
    assert len(sha(ARGV, ENTRY, hf)) == 64


def test_an_uncached_artifact_refuses(hf):
    import shutil
    shutil.rmtree(hf / "hub/models--caslca--Target-4bit-mtp-drafter")
    with pytest.raises(ai.ArmIdentityError, match="not in the local cache|no snapshot"):
        sha(ARGV_ON, ENTRY_ON, hf)


def test_a_local_directory_artifact_is_content_hashed(tmp_path):
    model = tmp_path / "local-model"
    model.mkdir()
    (model / "config.json").write_text("{}")
    (model / "w.safetensors").write_bytes(b"1234")
    argv = with_flag(ARGV, "--model", str(model))
    entry = {**ENTRY, "hf_path": str(model)}
    base = sha(argv, entry, tmp_path)
    (model / "w.safetensors").write_bytes(b"1235")
    assert sha(argv, entry, tmp_path) != base


def test_argv_must_agree_with_the_served_entry(hf):
    with pytest.raises(ai.ArmIdentityError, match="--model"):
        sha(with_flag(ARGV, "--model", "other/model"), ENTRY, hf)
    with pytest.raises(ai.ArmIdentityError, match="draft"):
        sha(ARGV_ON, ENTRY, hf)                                           # worker has a drafter the entry lacks
    with pytest.raises(ai.ArmIdentityError, match="draft-model"):
        sha(ARGV_ON, {**ENTRY_ON, "draft_model": "x/y"}, hf)
    with pytest.raises(ai.ArmIdentityError, match="draft"):
        sha([a for a in ARGV_ON if a not in ("--draft-model", DRAFT)], ENTRY_ON, hf)


def test_entry_presentation_does_not_matter_but_other_entry_keys_do(hf):
    base = sha(ARGV, ENTRY, hf)
    assert sha(ARGV, {**ENTRY, "presentation": {"role": "other"}}, hf) == base
    assert sha(ARGV, {**ENTRY, "kv_bits": 8}, hf) != base


def test_fingerprint_is_json_and_home_normalised(hf):
    fp = ai.fingerprint(ARGV_ON, ENTRY_ON, hf_home=hf, apc=APC_OFF, retain_default="on")
    text = json.dumps(fp)
    assert "/Users/" not in text and str(hf) not in text
    assert fp["target"]["repo"] == TARGET and fp["draft"]["repo"] == DRAFT
    assert fp["target"]["revision"] == "a" * 40


# ---- review L1: every flag mlx-serve's _build_command emits is classified
FIXTURE = Path(__file__).parent / "fixtures/p311_worker_argv.json"


def test_the_recorded_argv_of_both_picks_off_and_mtp_parses():
    """Generated from mlx-serve's own `_build_command` over main_models.yaml (both picks, predictor OFF and MTP);
    `--cache-session-shrink` (deployed on the first pick) is classified inert: it compacts idle KV padding and restores
    the full floor on active reuse (main_models.yaml C85; provenance.registry_kv: retirement changes resource use, not
    stored KV values; AGENTS.md: honour shrink only while idle). Unknown flags still refuse."""
    recorded = json.loads(FIXTURE.read_text())
    assert len(recorded) == 4
    for key, argv in recorded.items():
        flags = ai.parse_argv(argv)
        assert "--model" in flags, key
        assert ("--draft-kind" in flags) == key.endswith("|mtp"), key
    first = ai.parse_argv(recorded["Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed|off"])
    assert first["--cache-session-shrink"] == "on"


def test_cache_session_shrink_is_inert_and_every_emitted_flag_is_classified():
    shrink = with_flag(ARGV, "--cache-session-shrink", "on")
    assert "--cache-session-shrink" in ai.INERT_VALUE_FLAGS
    assert ai.parse_argv(shrink)["--cache-session-shrink"] == "on"
    for flag in ("--max-tokens", "--max-kv-cache-size", "--kv-quant-mode", "--reasoning-parser", "--tool-call-parser"):
        assert flag in ai.OUTPUT_VALUE_FLAGS, flag
    for bad in ("--surprise", "--cache-session-shrunk"):
        with pytest.raises(ai.ArmIdentityError):
            ai.parse_argv(ARGV + [bad, "1"])


def test_shrink_does_not_change_the_arm_identity(hf):
    assert sha(with_flag(ARGV, "--cache-session-shrink", "on"), ENTRY, hf) == sha(ARGV, ENTRY, hf)


# ---- review L2: APC state from the verified router / worker environment
def test_apc_state_is_part_of_the_arm_identity(hf):
    base = sha(ARGV, ENTRY, hf)
    assert sha(ARGV, ENTRY, hf, apc={"router": "1", "worker": "0"}) != base
    assert sha(ARGV, ENTRY, hf, apc={"router": "0", "worker": "1"}) != base


@pytest.mark.parametrize("apc", [None, {}, {"router": "0"}, {"router": None, "worker": "0"}, {"router": "0", "worker": ""}])
def test_unreadable_apc_state_refuses(hf, apc):
    with pytest.raises(ai.ArmIdentityError, match="APC"):
        sha(ARGV, ENTRY, hf, apc=apc)


def test_observe_reads_apc_from_the_router_and_worker_environments(monkeypatch, tmp_path, hf):
    from bench import provenance
    reg = tmp_path / "reg.yaml"
    reg.write_text("mlx_port: 8091\nmanager_port: 8000\nmodels:\n  - name: m\n    hf_path: " + TARGET + "\n")
    monkeypatch.setattr(provenance, "_port_listener_pids", lambda port: [777])
    monkeypatch.setattr(provenance, "_worker_argvs", lambda doc: [ARGV])
    monkeypatch.setattr(provenance, "_descends_from", lambda pid, anc: True)
    envs = {111: {"PATH": "x"}, 777: {"APC_ENABLED": "1"}}
    fp, sha_on = ai.observe("m", {"pid": 111}, registry_path=reg, hf_home=hf, env_reader=lambda pid: envs[pid],
                            retain_default_reader=lambda: "on")
    assert fp["apc"] == {"router": "0", "worker": "1"}
    envs[777] = {}
    assert ai.observe("m", {"pid": 111}, registry_path=reg, hf_home=hf, env_reader=lambda pid: envs[pid],
                      retain_default_reader=lambda: "on")[1] != sha_on

    def denied(pid):
        raise PermissionError("environ")
    with pytest.raises(ai.ArmIdentityError, match="APC"):
        ai.observe("m", {"pid": 111}, registry_path=reg, hf_home=hf, env_reader=denied, retain_default_reader=lambda: "on")


def test_every_flag_literal_in_mlx_serve_build_command_is_classified():
    """Drift guard when the fork source is available (MLX_SERVE_SRC=<mlx-serve>/src, or the src/mlx-serve submodule)."""
    import re
    root = Path(os.environ.get("MLX_SERVE_SRC") or Path(__file__).resolve().parents[3] / "src/mlx-serve/src")
    source = root / "mlx_serve/process_manager.py"
    if not source.is_file():
        pytest.skip("mlx-serve source not available (set MLX_SERVE_SRC)")
    text = source.read_text()
    body = text[text.index("def _build_command"):]
    body = body[:body.index("\ndef ", 10)] if "\ndef " in body[10:] else body
    literals = set(re.findall(r'"(--[a-z][a-z0-9-]*)"', body))
    known = set(ai.OUTPUT_VALUE_FLAGS) | set(ai.OUTPUT_BOOL_FLAGS) | set(ai.INERT_VALUE_FLAGS)
    assert literals and literals <= known, sorted(literals - known)


# ---- confirmation L10: the EFFECTIVE session-retain-prompt-end is part of the identity
def test_omitted_retain_flag_resolves_to_the_default_and_equals_the_explicit_value(hf):
    explicit_on = with_flag(ARGV, "--cache-session-retain-prompt-end", "on")
    assert sha(ARGV, ENTRY, hf, retain="on") == sha(explicit_on, ENTRY, hf, retain="off")   # explicit wins, default unused
    assert sha(ARGV, ENTRY, hf, retain="on") != sha(ARGV, ENTRY, hf, retain="off")          # omitted: the default counts
    assert sha(ARGV, ENTRY, hf, retain="off") == sha(with_flag(ARGV, "--cache-session-retain-prompt-end", "off"), ENTRY, hf)
    assert sha(ARGV, ENTRY, hf, retain="on") != sha(with_flag(ARGV, "--cache-session-retain-prompt-end", "off"), ENTRY, hf)


@pytest.mark.parametrize("bad", [None, "", "maybe"])
def test_unreadable_or_malformed_retain_default_refuses_when_the_flag_is_omitted(hf, bad):
    with pytest.raises(ai.ArmIdentityError, match="retain"):
        sha(ARGV, ENTRY, hf, retain=bad)
    sha(with_flag(ARGV, "--cache-session-retain-prompt-end", "on"), ENTRY, hf, retain=bad)     # explicit: not needed


def test_observe_refuses_when_the_fork_default_cannot_be_read(monkeypatch, tmp_path, hf):
    from bench import provenance
    reg = tmp_path / "reg.yaml"
    reg.write_text("mlx_port: 8091\nmanager_port: 8000\nmodels:\n  - name: m\n    hf_path: " + TARGET + "\n")
    monkeypatch.setattr(provenance, "_port_listener_pids", lambda port: [777])
    monkeypatch.setattr(provenance, "_worker_argvs", lambda doc: [ARGV])
    monkeypatch.setattr(provenance, "_descends_from", lambda pid, anc: True)

    def unreadable():
        raise ImportError("mlx_vlm")
    with pytest.raises(ai.ArmIdentityError, match="retain"):
        ai.observe("m", {"pid": 111}, registry_path=reg, hf_home=hf, env_reader=lambda pid: {},
                   retain_default_reader=unreadable)
