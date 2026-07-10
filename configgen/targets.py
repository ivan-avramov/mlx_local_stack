from .emitters.opencode import emit_opencode
from .emitters.aider import emit_aider
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
