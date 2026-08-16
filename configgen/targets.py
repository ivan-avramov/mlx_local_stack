from .emitters.opencode import emit_opencode, emit_opencode_bench
from .emitters.aider import emit_aider, emit_aider_bench
from .emitters.vscode import emit_vscode
from .emitters.zed import emit_zed
from .emitters.owui import emit_owui

# Each entry: (target_name, emitter_fn, output_path)
# output_path is a str (single-file emitters) or a dict[str, str] mapping the
# emitter's dict keys (e.g. aider's "settings"/"metadata"/"conf") to output paths.
# All paths are relative to the repo root.
TARGETS: list[tuple[str, callable, str | dict]] = [
    ("opencode", emit_opencode, "opencode_config/opencode.json"),
    ("aider", emit_aider, {
        "settings": "aider_config/aider.model.settings.yml",
        "metadata": "aider_config/aider.model.metadata.json",
        "conf": "aider_config/aider.conf.yml",
    }),
    ("vscode", emit_vscode, "vscode_config/chatLanguageModels.json"),
    ("zed", emit_zed, "zed_config/settings.snippet.jsonc"),
    ("owui", emit_owui, "openwebui-init/models_config.json"),
]

# BENCH targets are generated and drift-checked exactly like TARGETS, but are NOT client configs.
# Kept in a separate list so "a role=candidate model never appears in TARGETS output" stays a
# mechanically enforceable invariant (test_candidate_role_is_accepted_and_never_emitted_to_clients
# loops TARGETS). The bench carrier exists precisely to include candidates.
BENCH_TARGETS: list[tuple[str, callable, str | dict]] = [
    ("aider-bench", emit_aider_bench, "benchmark/aider_bench.model.settings.yml"),
    ("opencode-bench", emit_opencode_bench, "benchmark/opencode_bench.json"),
]
