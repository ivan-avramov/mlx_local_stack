"""The `deployed` sampling profile — sourced from main_models.yaml `generation_defaults`.

WHY THIS EXISTS. `model_params.PARAMS` is family-uniform (one GEMMA set, one QWEN set), so
per-model operating temperatures are unrepresentable. Meanwhile FU-2 made
`main_models.yaml`'s per-model `generation_defaults` the actual deployed truth. The two have
drifted badly:

  * QWEN (production) = temp 0.7 / min_p 0.03 / presence_penalty 0.3 / budget 49152
  * deployed Ornith   = temp 0.4 / min_p 0.0  / presence_penalty 0.0 / budget 81920
  * deployed distill  = temp 0.3 / min_p 0.0  / presence_penalty 0.0 / budget 81920

and `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` is not in PARAMS at all — it reaches QWEN only by a
name-substring fallback. Two consequences, both silent:

  1. every new axis built on `params_for(model)` would measure a config we do not ship;
  2. `presence_penalty 0.3` DISABLES suffix decoding (a nonzero one trips the fallback), so the
     serving path under test would differ from production in throughput as well as sampling.

The registry is the single source of truth, so the profile reads it rather than duplicating it.
`deployed` FAILS LOUD when the registry can't answer — silently falling back to a family default
is the exact bug being fixed here.
"""
from pathlib import Path

import pytest
import yaml

import bench.model_params as MP

# Locate the registry from THIS file, not from the cwd: pytest is run from both the repo root
# and benchmark/, and a cwd-relative path silently turns every assertion below into a
# file-not-found. (The production default stays "main_models.yaml", matching provenance.py's
# existing convention that the harness runs from the repo root.)
REGISTRY = str(Path(__file__).resolve().parents[3] / "main_models.yaml")


def _registry_names(path=REGISTRY):
    with open(path) as f:
        doc = yaml.safe_load(f)
    return [e["name"] for e in (doc.get("models") or []) if isinstance(e, dict) and e.get("name")]


# --------------------------------------------------------------- reading the registry
def test_reads_ornith_generation_defaults():
    d = MP.registry_generation_defaults("Ornith-1.0-35B-mlx-uniform-4bit", REGISTRY)
    assert d["temperature"] == 0.4
    assert d["presence_penalty"] == 0.0
    assert d["max_tokens"] == 102400 and d["thinking_budget"] == 81920
    assert d["enable_thinking"] is True


def test_reads_distill_generation_defaults():
    d = MP.registry_generation_defaults("Qwen3.6-27B-Opus-Distill-OptiQ-4bit", REGISTRY)
    assert d["temperature"] == 0.3          # NOT the QWEN production 0.7
    assert d["presence_penalty"] == 0.0     # NOT 0.3 — a nonzero one disables suffix decoding
    assert d["min_p"] == 0.0


def test_unknown_model_returns_none():
    assert MP.registry_generation_defaults("no-such-model", REGISTRY) is None


# --------------------------------------------------------------- the profile
def test_deployed_profile_is_the_registry_block():
    for name in ("Ornith-1.0-35B-mlx-uniform-4bit", "Qwen3.6-27B-Opus-Distill-OptiQ-4bit",
                 "gemma-4-31B-it-qat-6bit"):
        assert MP.params_for(name, "deployed", registry_path=REGISTRY) == \
            MP.registry_generation_defaults(name, REGISTRY)


def test_deployed_differs_from_production_for_both_winners():
    """The regression this profile exists to prevent: production is NOT what we ship."""
    for name in ("Ornith-1.0-35B-mlx-uniform-4bit", "Qwen3.6-27B-Opus-Distill-OptiQ-4bit"):
        dep = MP.params_for(name, "deployed", registry_path=REGISTRY)
        prod = MP.params_for(name, "production")
        assert dep["temperature"] != prod["temperature"]
        assert dep["presence_penalty"] == 0.0 and prod.get("presence_penalty") == 0.3


def test_deployed_gemma_is_the_daily_driver_not_the_coding_profile():
    dep = MP.params_for("gemma-4-31B-it-qat-6bit", "deployed", registry_path=REGISTRY)
    assert (dep["temperature"], dep["top_k"], dep["repetition_penalty"]) == (0.7, 64, 1.08)
    assert dep["thinking_budget"] == 16384          # coding profile lifts this to 32768
    assert dep["max_tokens"] == 32768


def test_deployed_is_a_copy_not_a_shared_mutable():
    a = MP.params_for("Ornith-1.0-35B-mlx-uniform-4bit", "deployed", registry_path=REGISTRY)
    a["temperature"] = 99
    b = MP.params_for("Ornith-1.0-35B-mlx-uniform-4bit", "deployed", registry_path=REGISTRY)
    assert b["temperature"] == 0.4


# --------------------------------------------------------------- failing loud
def test_deployed_raises_for_a_model_absent_from_the_registry(tmp_path):
    reg = tmp_path / "r.yaml"
    reg.write_text(yaml.safe_dump({"models": [{"name": "other", "generation_defaults": {}}]}))
    with pytest.raises(LookupError, match="ghost-model"):
        MP.params_for("ghost-model", "deployed", registry_path=str(reg))


def test_deployed_raises_when_entry_has_no_generation_defaults(tmp_path):
    reg = tmp_path / "r.yaml"
    reg.write_text(yaml.safe_dump({"models": [{"name": "bare", "hf_path": "x"}]}))
    with pytest.raises(LookupError, match="generation_defaults"):
        MP.params_for("bare", "deployed", registry_path=str(reg))


def test_deployed_raises_when_registry_file_is_missing():
    with pytest.raises(LookupError, match="registry"):
        MP.params_for("anything", "deployed", registry_path="/nonexistent/main_models.yaml")


def test_task_model_block_is_not_treated_as_a_served_model(tmp_path):
    """`task_model` is a TOP-LEVEL block, not a `models:` entry (it must never be served by the
    router). A naive parse would pick up its generation_defaults (max_tokens 512)."""
    reg = tmp_path / "r.yaml"
    reg.write_text(yaml.safe_dump({
        "task_model": {"name": "tiny", "generation_defaults": {"max_tokens": 512}},
        "models": [{"name": "real", "generation_defaults": {"temperature": 0.4}}]}))
    assert MP.registry_generation_defaults("tiny", str(reg)) is None
    assert MP.params_for("real", "deployed", registry_path=str(reg))["temperature"] == 0.4


# --------------------------------------------------------------- drift guards
def test_every_registry_model_is_registered_in_PARAMS():
    """The drift guard. Adding a model to the registry without registering its sampling makes
    `_family` fall back on a NAME SUBSTRING — which is how the distill silently ran at QWEN
    production params. This test fails the moment that happens again."""
    missing = [n for n in _registry_names() if n not in MP.PARAMS]
    assert missing == [], f"registry models absent from model_params.PARAMS: {missing}"


def test_deployed_is_listed_as_a_profile():
    assert "deployed" in MP.profile_names()


def test_historical_profiles_are_unchanged():
    """Locks the profiles that historical rows were produced under, so those rows stay
    reproducible. If one of these ever needs to change, the old rows must be relabelled."""
    q = MP.params_for("Ornith-1.0-35B-mlx-uniform-4bit", "official")
    assert (q["temperature"], q["min_p"], q["presence_penalty"], q["thinking_budget"]) == \
        (0.6, 0.0, 0.0, 81920)
    g = MP.params_for("gemma-4-31B-it-qat-6bit", "production")
    assert (g["temperature"], g["top_k"], g["repetition_penalty"], g["thinking_budget"]) == \
        (0.7, 64, 1.08, 16384)
