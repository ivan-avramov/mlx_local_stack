from __future__ import annotations
from dataclasses import dataclass
import yaml

_REQUIRED = ("role", "display_name", "context", "output")
_FAMILIES = {"qwen", "gemma"}
# `candidate` = registered for BENCHMARKING but NOT advertised to any client. The registry is the
# bench harness's source of truth, so a model must be servable long before it is a daily-driver
# option; without this role the only choices were failing `configgen check` (which gates
# runserver.sh) or mislabelling an unvetted model as `main`, which publishes it to opencode, aider,
# OWUI, vscode and zed. All five emitters already filter on role == "main", so no emitter changes
# are needed — the invariant is pinned by
# test_candidate_role_is_accepted_and_never_emitted_to_clients.
_ROLES = {"main", "task", "candidate"}

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

def _parse_model_entry(entry: dict, seen: set[str]) -> ModelSpec | None:
    """Parse one `models:`-shaped entry (name / hf_path / presentation / optional
    generation_defaults) into a ModelSpec, or None if it has no presentation block
    (a router-only entry, not exposed to clients). Shared by `models:` and
    `task_model:` parsing so both follow identical validation."""
    pres = entry.get("presentation")
    if not pres:
        return None  # router-only entry, not exposed to clients
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
    if family is not None and family not in _FAMILIES:
        raise ValueError(f"model {name!r} has invalid family {family!r}")
    if role == "main" and family is None:
        raise ValueError(f"model {name!r} (role=main) requires a family")
    edit_format = pres.get("edit_format") or ("diff" if family == "qwen" else "whole")
    return ModelSpec(
        name=name, hf_path=entry.get("hf_path", ""), role=role, family=family,
        display_name=pres["display_name"], context=int(pres["context"]),
        output=int(pres["output"]), capabilities=list(pres.get("capabilities", [])),
        sampling=dict(entry.get("generation_defaults", {})),
        edit_format=edit_format, port=8092 if role == "task" else None,
    )

def load_source(path: str) -> Source:
    with open(path) as f:
        doc = yaml.safe_load(f) or {}
    models: list[ModelSpec] = []
    seen: set[str] = set()
    for entry in doc.get("models", []):
        spec = _parse_model_entry(entry, seen)
        if spec is not None:
            models.append(spec)
    # `task_model:` is a top-level block (NOT a `models:` entry): the task model
    # lives on :8092 (mlx_vlm), not the :8000 router, so it must never be served
    # by mlx-serve or auto-listed by OWUI as a router model. It is parsed with
    # the same per-entry logic and folded into Source.models for the emitters.
    task_model = doc.get("task_model")
    if task_model:
        spec = _parse_model_entry(task_model, seen)
        if spec is not None:
            models.append(spec)
    names = {m.name for m in models}
    agent_defaults = dict(doc.get("agent_defaults", {}))
    for agent, mid in agent_defaults.items():
        if mid not in names:
            raise ValueError(f"agent_defaults[{agent!r}] = {mid!r} is not a known model")
    return Source(models=models, agent_defaults=agent_defaults)
