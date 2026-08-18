"""Per-model generation parameters — the SAME params the user runs in production
(opencode.json / aider.model.*). The benchmark measures each model as actually used.

Source of truth: opencode_config/opencode.json + aider_config/aider.model.metadata.json.
Params are family-uniform: one Gemma-4 set (all dense + MoE quants) and one Qwen set.
mlx-serve forwards these straight to mlx_vlm (top_k / min_p / repetition_penalty /
presence_penalty / enable_thinking / thinking_budget are all honored).
"""
from . import paths

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

# CODING-capability profile: each arch's CONVERGING sampling + a thinking_budget large enough
# to not truncate hard-problem reasoning. gemma's daily-driver budget (16384) truncates hard
# LCB items mid-think (measured median ~17K thinking tokens, most <28K) -> all-INVALID
# budget-hits; `coding` lifts gemma to 32768 (max_tokens 49152, clamp-safe at 0.8) so
# convergence is MEASURED, not the cap. Sampling stays at production temp 0.7 (the converging
# config) -- NOT the loop-prone official temp 1.0. Qwen's coding config already meets its
# documented ~81920 need, so QWEN_CODING = QWEN_OFFICIAL (temp 0.6 + 81920 budget).
# NEMOTRON — added 2026-08-14 with the candidate registry entry. VENDOR-VERBATIM and deliberately
# SPARSE: the nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16 card states "Recommended Sampling:
# Temperature 1.0, Top_P 0.95" and specifies NOTHING else, so nothing else is asserted here. No
# invented top_k/min_p — an absent key falls through to the checkpoint, which is honest; a guessed
# one is a measurement of a config nobody chose.
# `presence_penalty: 0.0` is the one addition and is a SERVING requirement, not a sampling opinion:
# a nonzero value trips the suffix-decoding fallback on our stack.
# Budget MATCHES both winners (102400 / 81920) so `compare` will not refuse the pairing.
# ⚠️ temperature 1.0 is where the gemma MoE degenerate-looped, and is far above both winners' tuned
# op-temps (0.4 / 0.3). This is the vendor BASELINE to start a temperature ladder from, not a tuned
# operating point — do not read a convergence failure here as a capability verdict.
NEMOTRON = {
    "temperature": 1.0,
    "top_p": 0.95,
    "presence_penalty": 0.0,
    "max_tokens": 102400,
    "enable_thinking": True,
    "thinking_budget": 81920,
}
# For this family the vendor recommendation IS the official one, and its budget already meets the
# coding need, so all three profiles coincide. Kept as separate names so a future divergence has an
# obvious home rather than being wedged into the shared dict.
NEMOTRON_OFFICIAL = dict(NEMOTRON)
NEMOTRON_CODING = dict(NEMOTRON)

GEMMA_CODING = {**GEMMA, "max_tokens": 49152, "thinking_budget": 32768}
QWEN_CODING = dict(QWEN_OFFICIAL)

# Served-model name (main_models.yaml / GET /v1/models) -> param set.
PARAMS = {
    "gemma-4-26b-a4b-it-8bit": GEMMA,
    "gemma-4-31b-it-6bit": GEMMA,
    "gemma-4-31b-it-UD-MLX-4bit": GEMMA,
    "gemma-4-31B-it-qat-6bit": GEMMA,
    "gemma-4-26B-A4B-it-OptiQ-4bit": GEMMA,
    "gemma-4-26B-A4B-it-QAT-MLX-4bit": GEMMA,
    "Qwen3.6-27B-UD-MLX-6bit": QWEN,
    "Qwen3.6-27B-OptiQ-4bit": QWEN,
    "Qwen3.6-27B-MLX-8bit": QWEN,
    # Registered EXPLICITLY, not by the name-substring fallback: this model reaching QWEN by
    # luck is how it silently ran at production temp 0.7 instead of its deployed 0.3.
    "Qwen3.6-27B-Opus-Distill-OptiQ-4bit": QWEN,
    # Ornith-1.0-35B is qwen3_5_moe arch (hybrid linear-attn MoE) — Qwen sampling,
    # not the gemma name-fallback ("qwen" isn't in the name).
    "Ornith-1.0-35B-mlx-uniform-4bit": QWEN,
    "Ornith-1.0-35B-mlx-uniform-6bit": QWEN,
    # MUST be explicit: `_family`'s substring fallback is `"qwen" if "qwen" in name else "gemma"`,
    # so an unregistered Nemotron would silently receive GEMMA sampling (temp 0.7, top_k 64,
    # repetition_penalty 1.08) — a different arch's daily-driver config. That is the exact class of
    # silent misassignment this table's drift guard exists to catch.
    "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit": NEMOTRON,
    # The three Qwen3.8-27B candidate recipes below (M2, 2026-08-17): qwen3_5 family. <!-- allow-shorthand -->
    # The `deployed`
    # profile they actually screen under reads main_models.yaml generation_defaults
    # (checkpoint-default temp 1.0); this legacy-production mapping exists so the
    # every-registry-model-is-registered drift guard can vouch for the family.
    "Qwen3.8-27B-mlx-uniform-4bit": QWEN,
    "Qwen3.8-27B-static-mixed-4bit": QWEN,
    "Qwen3.8-27B-OptiQ-4.5bpw-mixed": QWEN,
}

_PROFILES = {
    "gemma": {"production": GEMMA, "official": GEMMA_OFFICIAL, "coding": GEMMA_CODING},
    "qwen": {"production": QWEN, "official": QWEN_OFFICIAL, "coding": QWEN_CODING},
    "nemotron": {"production": NEMOTRON, "official": NEMOTRON_OFFICIAL,
                 "coding": NEMOTRON_CODING},
}

# The `deployed` profile is NOT in _PROFILES: it is per-MODEL, not per-family, and it is not
# duplicated here at all. It is read from main_models.yaml's `generation_defaults` — the FU-2
# source of truth that mlx-serve actually forwards to the worker. Family-uniform tables cannot
# express per-model operating temperatures (Ornith 0.4 vs distill 0.3), and every copy of a
# config is a copy that can drift.
DEPLOYED = "deployed"
_REGISTRY_CACHE: dict = {}


def _registry_models(registry_path: str | None = None) -> dict:
    """{name: entry} for `models:` entries only, parsed once per path.

    `task_model` is a TOP-LEVEL block (it must never be served by the router), so it is
    deliberately NOT included — a naive parse would hand out its max_tokens 512.

    ``registry_path=None`` resolves to the repo's `main_models.yaml` independent of the CWD. The
    old bare-string default made the `deployed` profile — the FU-2 source of truth for what we
    actually ship — unreadable from any CWD but the repo root, which is not merely a missing file:
    it decides whether a run measures the sampling we deploy.
    """
    registry_path = str(paths.registry_path()) if registry_path is None else registry_path
    if registry_path in _REGISTRY_CACHE:
        return _REGISTRY_CACHE[registry_path]
    import yaml                      # lazy: keeps model_params importable without pyyaml
    try:
        with open(registry_path) as f:
            doc = yaml.safe_load(f) or {}
    except OSError as e:
        raise LookupError(f"cannot read the model registry {registry_path!r}: {e}") from e
    entries = doc.get("models") or [] if isinstance(doc, dict) else []
    out = {e["name"]: e for e in entries if isinstance(e, dict) and e.get("name")}
    _REGISTRY_CACHE[registry_path] = out
    return out


def registry_generation_defaults(model: str, registry_path: str | None = None):
    """The model's deployed `generation_defaults` block, or None if the model isn't a served
    registry entry. Raises LookupError only if the registry itself is unreadable."""
    entry = _registry_models(registry_path).get(model)
    if entry is None:
        return None
    gd = entry.get("generation_defaults")
    return dict(gd) if isinstance(gd, dict) else None


def _family(model: str) -> str:
    base = PARAMS.get(model)
    if base is QWEN:
        return "qwen"
    if base is GEMMA:
        return "gemma"
    if base is NEMOTRON:
        return "nemotron"
    return "qwen" if "qwen" in model.lower() else "gemma"


def profile_names():
    """All defined sampling-profile names (union across families) plus `deployed`. The CLI's
    --sampling-profile choices derive from this so the two can't drift out of sync."""
    return sorted({p for fam in _PROFILES.values() for p in fam} | {DEPLOYED})


def params_for(model: str, profile: str = "production",
               registry_path: str | None = None) -> dict:
    """Return a copy of the model's generation params.

    profile='deployed'   = main_models.yaml `generation_defaults` — what mlx-serve actually
                           forwards to the worker. PER-MODEL (Ornith 0.4 vs distill 0.3), and
                           the only profile that reflects production. Use it for new axes.
    profile='production' = the historical daily-driver table in THIS file. Kept because
                           existing results rows were produced under it; it has since drifted
                           from what we ship (see test_deployed_profile.py).
    profile='official'   = the family's published recommended sampling (quality-first eval).
    profile='coding'     = official + a budget large enough not to truncate hard reasoning.

    `deployed` FAILS LOUD (LookupError) when the registry cannot answer. Falling back to a
    family default there would silently reintroduce exactly the drift this profile fixes.
    The family tables keep their name-substring fallback for the historical profiles.
    """
    if profile == DEPLOYED:
        gd = registry_generation_defaults(model, registry_path)
        if gd is None:
            known = sorted(_registry_models(registry_path))
            raise LookupError(
                f"no deployed generation_defaults for {model!r} in {registry_path!r}: the model "
                f"is absent from `models:` or its entry has no generation_defaults block. "
                f"Registry models: {known}")
        return gd
    return dict(_PROFILES[_family(model)][profile])
