"""Per-model generation parameters — the SAME params the user runs in production
(opencode.json / aider.model.*). The benchmark measures each model as actually used.

Source of truth: opencode_config/opencode.json + aider_config/aider.model.metadata.json.
Params are family-uniform: one Gemma-4 set (all dense + MoE quants) and one Qwen set.
mlx-serve forwards these straight to mlx_vlm (top_k / min_p / repetition_penalty /
presence_penalty / enable_thinking / thinking_budget are all honored).
"""

GEMMA = {
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 64,
    "repetition_penalty": 1.08,
    "max_tokens": 32768,
    "enable_thinking": True,
    "thinking_budget": 16384,
}

QWEN = {
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 20,
    "min_p": 0.03,
    "presence_penalty": 0.3,
    "max_tokens": 81920,
    "enable_thinking": True,
    "thinking_budget": 49152,
}

# Served-model name (main_models.yaml / GET /v1/models) -> param set.
PARAMS = {
    "gemma-4-26b-a4b-it-8bit": GEMMA,
    "gemma-4-31b-it-6bit": GEMMA,
    "gemma-4-31b-it-UD-MLX-4bit": GEMMA,
    "gemma-4-31B-it-qat-6bit": GEMMA,
    "gemma-4-26B-A4B-it-OptiQ-4bit": GEMMA,
    "gemma-4-26B-A4B-it-QAT-MLX-4bit": GEMMA,
    "Qwen3.6-27B-UD-MLX-6bit": QWEN,
}


def params_for(model: str) -> dict:
    """Return a copy of the model's generation params. New Gemma-family models default
    to the Gemma set; add non-Gemma models to PARAMS explicitly."""
    base = PARAMS.get(model)
    if base is None:
        base = QWEN if "qwen" in model.lower() else GEMMA
    return dict(base)
