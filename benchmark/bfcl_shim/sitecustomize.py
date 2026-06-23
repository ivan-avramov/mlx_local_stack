"""bfcl-eval custom ModelConfig registration shim (no site-packages edit).

Python auto-imports ``sitecustomize`` at interpreter startup if it is found on
``sys.path``. Put this dir on ``PYTHONPATH`` when invoking the ``bfcl`` CLI and it
registers our locally-served mlx-serve models into bfcl_eval's MODEL_CONFIG_MAPPING
(the single source of truth that ``--model`` is validated against).

Why this is the correct wiring (vs. reusing a stock key like ``google/gemma-3-27b-it``):
  * bfcl's OSS handler sends ``model=<ModelConfig.model_name>`` to /v1/completions
    (base_oss_handler.py: ``self.client.completions.create(model=self.model_path_or_id, ...)``
    where ``model_path_or_id`` falls back to ``model_name``).
  * mlx-serve's /completions proxy is multi-model and routes by the registered name
    → hf_path. It 404s an unregistered model field. So bfcl MUST send our *registered*
    name for deterministic routing; reusing a gated stock key (google/gemma-3-27b-it)
    404s/403s. Hence model_name == our mlx-serve registry name.

Tokenizer (for prompt templating + max_position_embeddings) is loaded from
``REMOTE_OPENAI_TOKENIZER_PATH`` (set per-run to the model's HF snapshot/repo id) —
required because ``model_name`` here is our registry name, not a resolvable HF id.
That branch also needs ``REMOTE_OPENAI_BASE_URL`` set (base_oss_handler.py gates it on
``bool(os.getenv("REMOTE_OPENAI_BASE_URL"))``).

Keys deliberately contain NO underscores: bfcl round-trips result dirs via
``model_name.replace("_", "/")`` (eval_runner_helper.py:300); hyphens/dots are safe.
"""
import sys


def _register():
    from bfcl_eval.constants.model_config import MODEL_CONFIG_MAPPING, ModelConfig

    # Thinking-stripping handler subclasses (template-fidelity fix): our served models emit a
    # reasoning preamble before the call list, which breaks the stock parser. Each model runs in
    # its NATIVE mode (published-comparable): gemma-4 = prompt (no gemma FC handler); Qwen-family
    # = FC (native <tool_call> format). Thinking stays ON; the handlers raise the 4096 token cap.
    from local_handlers import GemmaEpiHandler, QwenFCEpiHandler

    custom = {
        "gemma-4-26B-A4B-it-OptiQ-4bit": ModelConfig(
            model_name="gemma-4-26B-A4B-it-OptiQ-4bit",
            display_name="gemma-4-26B-A4B-it-OptiQ-4bit (mlx-serve local, Prompt)",
            url="https://huggingface.co/mlx-community/gemma-4-26B-A4B-it-OptiQ-4bit",
            org="local",
            license="gemma-terms-of-use",
            model_handler=GemmaEpiHandler,
            input_price=None,
            output_price=None,
            is_fc_model=False,
            underscore_to_dot=False,
        ),
        "Qwen3.6-27B-OptiQ-4bit": ModelConfig(
            model_name="Qwen3.6-27B-OptiQ-4bit",
            display_name="Qwen3.6-27B-OptiQ-4bit (mlx-serve local, FC)",
            url="https://huggingface.co/mlx-community/Qwen3.6-27B-OptiQ-4bit",
            org="local",
            license="apache-2.0",
            model_handler=QwenFCEpiHandler,
            input_price=None,
            output_price=None,
            is_fc_model=True,
            underscore_to_dot=False,
        ),
        # Locally-converted Opus-reasoning distill (qwen3_5 arch -> Qwen handler). M5-only;
        # tokenizer resolved via REMOTE_OPENAI_TOKENIZER_PATH (its local snapshot dir).
        "Qwen3.6-27B-Opus-Distill-OptiQ-4bit": ModelConfig(
            model_name="Qwen3.6-27B-Opus-Distill-OptiQ-4bit",
            display_name="Qwen3.6-27B-Opus-Distill-OptiQ-4bit (mlx-serve local, FC)",
            url="local",
            org="local",
            license="apache-2.0",
            model_handler=QwenFCEpiHandler,
            input_price=None,
            output_price=None,
            is_fc_model=True,
            underscore_to_dot=False,
        ),
    }
    added = []
    for key, cfg in custom.items():
        if key not in MODEL_CONFIG_MAPPING:
            MODEL_CONFIG_MAPPING[key] = cfg
            added.append(key)
    if added:
        print(f"[bfcl_shim] registered local models: {added}", file=sys.stderr)


try:
    _register()
except Exception as e:  # noqa: BLE001 — never break the interpreter if bfcl_eval absent
    print(f"[bfcl_shim] registration skipped: {type(e).__name__}: {e}", file=sys.stderr)
