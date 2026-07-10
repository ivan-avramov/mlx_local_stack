from __future__ import annotations
from dataclasses import dataclass
import yaml

_REQUIRED = ("role", "display_name", "context", "output")
_FAMILIES = {"qwen", "gemma"}
_ROLES = {"main", "task"}

@dataclass(frozen=True)
class ModelSpec:
    name: str
    hf_path: str
    role: str
    family: str | None
    display_name: str
    context: int
    output: int
    capabilities: list[str]
    sampling: dict
    edit_format: str
    port: int | None

@dataclass(frozen=True)
class Source:
    models: list[ModelSpec]
    agent_defaults: dict[str, str]

def load_source(path: str) -> Source:
    with open(path) as f:
        doc = yaml.safe_load(f) or {}
    models: list[ModelSpec] = []
    seen: set[str] = set()
    for entry in doc.get("models", []):
        pres = entry.get("presentation")
        if not pres:
            continue  # router-only entry, not exposed to clients
        name = entry["name"]
        if name in seen:
            raise ValueError(f"duplicate model name {name!r}")
        seen.add(name)
        for k in _REQUIRED:
            if k not in pres:
                raise ValueError(f"model {name!r} presentation missing required field {k!r}")
        role = pres["role"]
        if role not in _ROLES:
            raise ValueError(f"model {name!r} has invalid role {role!r}")
        family = pres.get("family")
        if role == "main" and family not in _FAMILIES:
            raise ValueError(f"model {name!r} has invalid/missing family {family!r}")
        edit_format = pres.get("edit_format") or ("diff" if family == "qwen" else "whole")
        models.append(ModelSpec(
            name=name, hf_path=entry.get("hf_path", ""), role=role, family=family,
            display_name=pres["display_name"], context=int(pres["context"]),
            output=int(pres["output"]), capabilities=list(pres.get("capabilities", [])),
            sampling=dict(entry.get("generation_defaults", {})),
            edit_format=edit_format, port=8092 if role == "task" else None,
        ))
    names = {m.name for m in models}
    agent_defaults = dict(doc.get("agent_defaults", {}))
    for agent, mid in agent_defaults.items():
        if mid not in names:
            raise ValueError(f"agent_defaults[{agent!r}] = {mid!r} is not a known model")
    return Source(models=models, agent_defaults=agent_defaults)
