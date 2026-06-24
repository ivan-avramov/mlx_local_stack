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

# OFFICIAL recommended sampling (quality-first eval profile) — diverges from production:
# gemma-4 (Google): temp 1.0, rep_pen 1.0, "high temp best for coding".
# Qwen3.6 (model card, coding): temp 0.6, min_p 0.0, presence_penalty 0.0.
# thinking_budget kept generous (a hard cap = headroom; convergence happens well below it).
GEMMA_OFFICIAL = {
    "temperature": 1.0,
    "top_p": 0.95,
    "top_k": 64,
    "repetition_penalty": 1.0,
    "max_tokens": 32768,
    "enable_thinking": True,
    "thinking_budget": 16384,
}

QWEN_OFFICIAL = {
    "temperature": 0.6,
    "top_p": 0.95,
    "top_k": 20,
    "min_p": 0.0,
    "presence_penalty": 0.0,
    # Qwen3.6's documented rec for HARD programming problems is ~81,920 generation tokens, and
    # our investigation confirmed hard LCB items need ~80K to genuinely converge. The budget
    # must MEET that (not the daily-driver 49152) or the convergence guard falsely flags
    # genuine-but-long reasoning as a loop (ct >= thinking_budget). The harness clamps
    # thinking_budget to 0.8*max_tokens, so max_tokens=102400 keeps the 81920 budget at face
    # value (98304 would shrink it to 78643) while still leaving ~20K for the answer.
    "max_tokens": 102400,
    "enable_thinking": True,
    "thinking_budget": 81920,
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

_PROFILES = {
    "gemma": {"production": GEMMA, "official": GEMMA_OFFICIAL},
    "qwen": {"production": QWEN, "official": QWEN_OFFICIAL},
}


def _family(model: str) -> str:
    base = PARAMS.get(model)
    if base is QWEN:
        return "qwen"
    if base is GEMMA:
        return "gemma"
    return "qwen" if "qwen" in model.lower() else "gemma"


def params_for(model: str, profile: str = "production") -> dict:
    """Return a copy of the model's generation params.

    profile='production' (default) = the daily-driver opencode.json config.
    profile='official' = the family's published recommended sampling (quality-first eval).
    New Gemma-family models default to the Gemma set; non-Gemma fall back to Qwen by name."""
    return dict(_PROFILES[_family(model)][profile])
