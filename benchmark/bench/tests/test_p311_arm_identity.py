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


def sha(argv, entry, hf_home):
    return ai.arm_identity_sha256(ai.fingerprint(argv, entry, hf_home=hf_home))


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
    fp = ai.fingerprint(ARGV_ON, ENTRY_ON, hf_home=hf)
    text = json.dumps(fp)
    assert "/Users/" not in text and str(hf) not in text
    assert fp["target"]["repo"] == TARGET and fp["draft"]["repo"] == DRAFT
    assert fp["target"]["revision"] == "a" * 40
