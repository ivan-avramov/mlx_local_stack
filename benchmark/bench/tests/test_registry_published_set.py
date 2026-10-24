"""P476: the live registry names exactly the published entries, and every configgen output
names only registry entries.

The expected set is an explicit list (NOT scraped from the README): changing what the stack
publishes is a deliberate edit of this list in the same commit as the registry.
"""
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "main_models.yaml"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from configgen.__main__ import _render  # noqa: E402
from configgen.source import load_source  # noqa: E402

PUBLISHED = {
    "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed",
    "Qwen3.8-27B-mlx-uniform-4bit",
    "Ornith-1.0-35B-mlx-uniform-4bit",
    "Qwen3.6-27B-Opus-Distill-OptiQ-4bit",
    "NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit",
}

# Model ids are read from the fields each emitter writes model names into (structurally), never recognised by family prefix:
# an id of ANY family that is neither a registry entry nor the task model fails. Registry names carry no "/"; the task model
# is "org/name". Provider prefixes that wrap a reference are stripped by the field that carries them.
_REF_PREFIXES = ("mlx-local/", "mlx-task/", "openai/")


def _bare(ref):
    for prefix in _REF_PREFIXES:
        if ref.startswith(prefix):
            return ref[len(prefix):]
    return ref


def _opencode_ids(doc):
    """opencode.json and the bench carriers: `models` keys of every provider, `model`, `small_model`, `agents.*.model`."""
    ids = set()
    for providers in (doc.get("providers"), doc.get("provider")):
        for prov in (providers or {}).values():
            ids |= set(prov.get("models") or {})
    ids |= {_bare(doc[k]) for k in ("model", "small_model") if k in doc}
    ids |= {_bare(a["model"]) for a in (doc.get("agents") or {}).values() if "model" in a}
    return ids


def _aider_settings_ids(doc):
    return {_bare(e["name"]) for e in doc} | {_bare(e["weak_model_name"]) for e in doc if "weak_model_name" in e}


def _owui_settings_ids(doc):
    ids = set(doc["main_model_ids"]) | set(doc["hidden_model_ids"]) | set(doc["excluded_model_ids"]) | {doc["task_model_id"]}
    ids |= set(doc["defaults"]["MODEL_ORDER_LIST"])
    for key in ("DEFAULT_MODELS", "DEFAULT_PINNED_MODELS"):
        ids |= {i for i in doc["defaults"][key].split(",") if i}
    return ids


# target -> function(parsed document) -> the model ids that emitter writes
EXTRACTORS = {
    "opencode": _opencode_ids,
    "opencode-bench": _opencode_ids,
    "opencode-bench-v2": _opencode_ids,
    "opencode-bench-v2-web": _opencode_ids,
    "opencode-bench-v2-web-tg1": _opencode_ids,
    "aider:settings": _aider_settings_ids,
    "aider-bench": _aider_settings_ids,
    "aider:metadata": lambda doc: {_bare(k) for k in doc},
    "aider:conf": lambda doc: {_bare(doc["model"])},
    "vscode": lambda doc: {m["id"] for prov in doc for m in prov["models"]},
    "zed": lambda doc: {m["name"] for prov in doc["language_models"]["openai_compatible"].values()
                        for m in prov["available_models"]},
    "owui": lambda doc: {m["id"] for m in doc},
    "owui-settings": _owui_settings_ids,
}


def _doc():
    return yaml.safe_load(REGISTRY.read_text())


def _parse(path, text):
    if path.endswith((".yml", ".yaml")):
        return yaml.safe_load(text)
    if path.endswith(".jsonc"):
        text = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("//"))
    return json.loads(text)


def _ids(target, path, text):
    assert target in EXTRACTORS, f"no model-id extractor for configgen target {target!r} ({path}): add one"
    ids = EXTRACTORS[target](_parse(path, text))
    assert ids, f"the {target!r} extractor found no model ids in {path}"
    return ids


def test_live_registry_names_exactly_the_published_entries():
    names = [e["name"] for e in _doc()["models"]]
    assert len(names) == len(set(names))
    assert set(names) == PUBLISHED
    assert "task_model" not in _doc()["models"] and _doc()["task_model"]["name"] not in names


def test_every_model_id_in_every_configgen_output_is_a_registry_entry():
    doc = _doc()
    allowed = {e["name"] for e in doc["models"]} | {doc["task_model"]["name"]}
    rendered = _render(load_source(str(REGISTRY)))
    assert rendered
    seen = set()
    retired = set(doc["openwebui"]["retired_model_ids"])    # S2b tombstones: allowed ONLY in the OWUI policy's excluded list
    for target, path, content in rendered:
        ids = _ids(target, path, content)
        seen |= ids
        if path == "openwebui-init/model_settings.json":
            policy = json.loads(content)
            assert retired <= set(policy["excluded_model_ids"])
            assert not retired & (set(policy["main_model_ids"]) | {policy["task_model_id"]} | set(policy["defaults"]["MODEL_ORDER_LIST"]))
            ids -= retired
        else:
            assert not ids & retired, f"{path} ({target}) names retired ids: {sorted(ids & retired)}"
        assert ids <= allowed, f"{path} ({target}) names non-registry ids: {sorted(ids - allowed)}"
    # the extractor must actually see the published entries, or the subset check proves nothing
    assert PUBLISHED <= seen


def test_owui_menu_is_the_openwebui_models_list():
    menu = _doc()["openwebui"]["models"]
    assert len(menu) == 4
    rendered = {path: content for _, path, content in _render(load_source(str(REGISTRY)))}
    settings = json.loads(rendered["openwebui-init/model_settings.json"])
    assert settings["main_model_ids"] == menu
    task = _doc()["task_model"]["name"]
    listed = [m["id"] for m in json.loads(rendered["openwebui-init/models_config.json"])]
    assert [i for i in listed if i != task] == menu


def test_a_non_registry_id_of_a_new_family_is_found_in_every_output():
    # no family list anywhere: a published entry renamed to an id of a family the stack has never used must be extracted
    # from the same field of the same output and rejected by the subset check
    doc = _doc()
    allowed = {e["name"] for e in doc["models"]} | {doc["task_model"]["name"]}
    foreign = "Zephyr-9-70B-instruct-4bit"
    assert foreign not in allowed
    rendered = _render(load_source(str(REGISTRY)))
    assert {target for target, _, _ in rendered} <= set(EXTRACTORS)
    for target, path, content in rendered:
        victims = [n for n in sorted(PUBLISHED) if n in content]
        assert victims, f"{path} ({target}) names no published entry to rename"
        for victim in victims:
            ids = _ids(target, path, content.replace(victim, foreign))
            assert foreign in ids, f"{path} ({target}): extractor missed a renamed {victim}"
            assert foreign in ids - allowed - set(doc["openwebui"]["retired_model_ids"])
