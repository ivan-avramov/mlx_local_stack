"""params_for gains an `official` profile = each family's published recommended sampling
(quality-first eval). The default `production` profile (the daily-driver opencode.json
config) is unchanged.

Official: gemma-4 temp 1.0 / rep_pen 1.0 (Google); Qwen3.6 coding temp 0.6 / min_p 0.0 /
presence_penalty 0.0 (Qwen card). Our production temp-0.7 + Qwen min_p 0.03 / presence 0.3
diverge from these.
"""
import bench.model_params as MP


def test_production_profile_is_default_and_unchanged():
    g = MP.params_for("gemma-4-31b-it-6bit")
    assert g["temperature"] == 0.7                      # daily-driver baseline preserved
    q = MP.params_for("Qwen3.6-27B-UD-MLX-6bit")
    assert q["min_p"] == 0.03 and q["presence_penalty"] == 0.3


def test_official_profile_gemma():
    g = MP.params_for("gemma-4-31b-it-6bit", profile="official")
    assert g["temperature"] == 1.0
    assert g["repetition_penalty"] == 1.0
    assert g["top_k"] == 64
    assert g["enable_thinking"] is True


def test_official_profile_qwen_coding():
    # Qwen3.6-27B-MLX-8bit is not in PARAMS -> resolves to the Qwen family.
    q = MP.params_for("Qwen3.6-27B-MLX-8bit", profile="official")
    assert q["temperature"] == 0.6
    assert q["min_p"] == 0.0
    assert q["presence_penalty"] == 0.0
    assert q["top_k"] == 20
