"""D3: the tune-encoding migration (docs/superpowers/specs/2026-08-17-tune-encoding-migration-design.md).

Result directories stay PURE registry model names; a `tune` (a short label naming the delta from
the `deployed` config — `kv4`, `t0.3`, `suffixon`, or a `+`-composed axis like `kv4+t0.3`) is
encoded in filenames as `<bench>.<tune>.<ext>` and stamped as `manifest["tune"]`. An ABSENT tune
means the `deployed` tune and must resolve to exactly today's byte-compatible path — that is the
whole point of the encoding: the existing base-name corpus keeps its meaning without a rewrite.
"""
import pytest

import bench.generate as G


# --------------------------------------------------------------------- result_path round-trip
def test_result_path_with_no_tune_is_byte_compatible_with_today(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    assert G.result_path("Ornith-1.0-35B-mlx-uniform-4bit", "humanevalplus") == \
        tmp_path / "Ornith-1.0-35B-mlx-uniform-4bit" / "humanevalplus.jsonl"
    # explicit tune=None must be identical to omitting it
    assert G.result_path("m", "aime", tune=None) == G.result_path("m", "aime")


def test_result_path_with_a_tune_infixes_the_label(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    assert G.result_path("Ornith-1.0-35B-mlx-uniform-4bit", "humanevalplus", tune="kv4") == \
        tmp_path / "Ornith-1.0-35B-mlx-uniform-4bit" / "humanevalplus.kv4.jsonl"


def test_result_path_composed_tune_label(tmp_path, monkeypatch):
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    assert G.result_path("m", "aime", tune="kv4+t0.3") == \
        tmp_path / "m" / "aime.kv4+t0.3.jsonl"


def test_result_path_matches_the_already_shipped_suffixon_convention(tmp_path, monkeypatch):
    """The `.suffixon.jsonl` files already on disk are the ad-hoc precedent this generalizes —
    `result_path(model, bench, tune="suffixon")` must reproduce that exact filename."""
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    p = G.result_path("Ornith-1.0-35B-mlx-uniform-4bit", "humanevalplus", tune="suffixon")
    assert p.name == "humanevalplus.suffixon.jsonl"


def test_secondary_artifact_paths_infix_the_tune_too(tmp_path, monkeypatch):
    """.with_suffix(...) on a tuned result_path must land on <bench>.<tune>.<ext>, exactly the
    pattern the manifest/score writers already use."""
    monkeypatch.setattr(G, "RESULTS", tmp_path)
    base = G.result_path("m", "humanevalplus", tune="kv4")
    assert base.with_suffix(".manifest.json").name == "humanevalplus.kv4.manifest.json"
    assert base.with_suffix(".score.json").name == "humanevalplus.kv4.score.json"


# --------------------------------------------------------------------- --tune label validation
@pytest.mark.parametrize("label", ["kv4", "t0.3", "suffixon", "suffixoff", "cap16",
                                   "kv4+t0.3", "a.b-c_d"])
def test_validate_tune_accepts_the_canonical_grammar(label):
    assert G.validate_tune(label) == label


def test_validate_tune_accepts_none_as_the_deployed_tune():
    assert G.validate_tune(None) is None


@pytest.mark.parametrize("label", ["Bad_Label", "", "KV4", "kv4 ", " kv4", ".kv4", "kv4.",
                                   "kv4+", "+kv4", "kv4+.t3", "kv/4", "kv4,t3"])
def test_validate_tune_rejects_malformed_labels(label):
    with pytest.raises(ValueError):
        G.validate_tune(label)
