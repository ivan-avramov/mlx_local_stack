"""M72 1.3: `benchmark/spikes/m72_e2e_prefill.py` gains `--capacity` (default = --tokens) and the `tq4_m72` variant (the
production mode as served: `maybe_quantize_kv_cache`, so the last full-attention layer stays native16). The driver parts
(argv, leg command) run in any venv; the variant's cache / stamp construction needs MLX and this copy's fork, so it
skips in the stack venv (run with the fork first on the path: `./fe_py.sh -m pytest <this file>`). The real model is
never loaded here."""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

SPIKES = Path(__file__).resolve().parents[2] / "spikes"


@pytest.fixture(scope="module")
def spike():
    sys.path.insert(0, str(SPIKES))
    try:
        spec = importlib.util.spec_from_file_location("m72_e2e_prefill", SPIKES / "m72_e2e_prefill.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001 — the harness imports a macOS footprint helper at load
        pytest.skip(f"harness import unavailable here: {type(e).__name__}: {e}")
    return mod


def _args(spike, argv):
    seen = {}

    def run_leg(a):
        seen["a"] = a

    def run_all(a):
        seen["a"] = a

    old = (spike.run_leg, spike.run_all, sys.argv)
    spike.run_leg, spike.run_all = run_leg, run_all
    sys.argv = ["m72_e2e_prefill.py", *argv]
    try:
        spike.main()
    finally:
        spike.run_leg, spike.run_all, sys.argv = old
    return seen["a"]


def test_capacity_defaults_to_none_meaning_tokens(spike):
    a = _args(spike, ["--leg", "--variant", "native16", "--tokens", "4096"])
    assert a.capacity is None


@pytest.mark.parametrize("variant", ["native16", "tq4_prod", "tq4_p2s", "tq4_m72"])
def test_variants_and_capacity_parse(spike, variant):
    a = _args(spike, ["--leg", "--variant", variant, "--tokens", "131072", "--capacity", "262144"])
    assert a.variant == variant and a.capacity == 262144


def test_driver_passes_capacity_to_every_leg(spike, monkeypatch, tmp_path):
    cmds = []

    def fake_run(cmd, **kw):
        cmds.append(cmd)
        row = {"prefill_s": 1.0, "tok_per_s": 1.0, "os_peak_GB": 1.0, "os_peak_delta_GB": 0.1,
               "last_logit_top5": [1, 2, 3, 4, 5]}
        return types.SimpleNamespace(returncode=0, stdout=json.dumps(row) + "\n", stderr="")

    monkeypatch.setattr(spike.subprocess, "run", fake_run)
    monkeypatch.setattr(spike, "gates", lambda: ({}, {}, True))
    out = tmp_path / "e2e.json"
    a = types.SimpleNamespace(legs=["tq4_p2s:layer", "tq4_m72"], idle=0, tokens=131072, capacity=262144,
                              out=str(out))
    spike.run_all(a)
    assert len(cmds) == 2
    for cmd in cmds:
        assert cmd[cmd.index("--capacity") + 1] == "262144"
    assert cmds[1][cmds[1].index("--variant") + 1] == "tq4_m72"
    assert json.loads(out.read_text())["meta"]["capacity"] == 262144


def test_driver_without_capacity_keeps_todays_leg_command(spike, monkeypatch):
    cmds = []
    monkeypatch.setattr(spike.subprocess, "run", lambda cmd, **kw: cmds.append(cmd) or types.SimpleNamespace(
        returncode=0, stdout=json.dumps({"prefill_s": 1, "tok_per_s": 1, "os_peak_GB": 1, "os_peak_delta_GB": 0,
                                         "last_logit_top5": []}), stderr=""))
    monkeypatch.setattr(spike, "gates", lambda: ({}, {}, True))
    spike.run_all(types.SimpleNamespace(legs=["native16"], idle=0, tokens=4096, capacity=None, out=None))
    assert "--capacity" not in cmds[0]


# ------------------------------------------------------------------ the tq4_m72 construction (MLX + the fork)
def _fork():
    mx = pytest.importorskip("mlx.core")
    pytest.importorskip("mlx_vlm")
    try:
        import mlx_vlm.tq4_attention  # noqa: F401
    except ImportError:
        pytest.skip("the importable mlx_vlm is not this copy's fork (run: ./fe_py.sh -m pytest <this file>)")
    if not mx.metal.is_available():
        pytest.skip("Metal GPU required")
    return mx


def _lm24():
    from mlx_vlm.models.qwen3_5.config import ModelConfig, TextConfig, VisionConfig
    from mlx_vlm.models.qwen3_5.language import LanguageModel

    import mlx.core as mx

    mx.random.seed(0)
    cfg = TextConfig(model_type="qwen3_5_text", hidden_size=128, intermediate_size=256,
                     linear_num_value_heads=4, linear_num_key_heads=2, linear_key_head_dim=16,
                     linear_value_head_dim=16, linear_conv_kernel_dim=4, num_hidden_layers=8,
                     num_attention_heads=24, rms_norm_eps=1e-6, vocab_size=64, num_key_value_heads=4,
                     max_position_embeddings=1 << 20, full_attention_interval=4, head_dim=256,
                     tie_word_embeddings=False)
    vision = VisionConfig(model_type="qwen3_5", depth=1, hidden_size=8, intermediate_size=16,
                          out_hidden_size=128, num_heads=1, in_channels=3, patch_size=4,
                          temporal_patch_size=2, spatial_merge_size=1, num_position_embeddings=4)
    lm = LanguageModel(cfg, config=ModelConfig(text_config=cfg, vision_config=vision, model_type="qwen3_5"))
    lm.set_dtype(mx.bfloat16)
    mx.eval(lm.parameters())
    return types.SimpleNamespace(config=lm.config, language_model=lm)


def test_tq4_m72_builds_the_served_layout_and_stamps(spike):
    mx = _fork()
    from mlx_vlm import tq4_fast

    model = _lm24()
    lm = model.language_model
    caches = lm.make_cache()
    extra = spike._production_mode(model, caches, 4096)
    assert extra["tq4_layers"] == [3] and extra["native_layers"] == [7]  # the last layer stays native16
    assert extra["cache_classes"][3] == "TurboQuantKVCache"
    assert extra["cache_classes"][7] == "PreallocKVCache"
    assert extra["r1_max_q_bound"] == pytest.approx(16.0) and extra["r1_max_codebook"] <= 1.0
    assert extra["self_test_cells"] >= 7
    for i in (3, 7):
        attn = lm.layers[i].self_attn
        assert attn.attention_policy.name == "fused_v1"
        assert attn.mtp_verify_policy.name == "joint_v1"
        assert attn.tq4_attention.name == "m72_v1"
    before = tq4_fast.route_counts()
    ids = mx.array([[(7 * i) % 60 + 1 for i in range(1024)]], dtype=mx.int32)
    for s in range(0, 1024, 512):
        mx.eval(lm(ids[:, s:s + 512], cache=caches).logits)
    after = tq4_fast.route_counts()
    delta = {k: v - before.get(k, 0) for k, v in after.items() if v != before.get(k, 0)}
    assert delta == {"p2s": 2, "native:prefill": 2}
    rec = spike._layer_bytes(caches, extra["tq4_layers"], extra["native_layers"])
    assert rec["tq4_layer_capacity"] == 4096
    assert rec["tq4_layer_bytes"] == 2 * (4 * 4096 * 2 + 4 * 4096 * 32 * 4)
    assert rec["native_layer_bytes"] >= 2 * 4 * 4096 * 256 * 2
    assert rec["a5_layer63_allowance_GB"] > 0
